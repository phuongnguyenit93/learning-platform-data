# Dùng java, javac và javap để xác minh runtime và class file

Trong một cuộc migration Java, thông tin “máy đã cài JDK 21” chưa đủ để chứng minh ứng dụng thực sự chạy bằng JDK 21 hoặc các class file được biên dịch cho đúng phiên bản. Máy có thể cài nhiều JDK; shell, service manager, container và pipeline có thể chọn các executable khác nhau. Compiler cũng có thể tạo bytecode cho một release khác với phiên bản của chính compiler.

Ba công cụ `java`, `javac` và `javap` giúp kiểm tra ba phần liên quan nhưng khác nhau:

- **`java`** khởi chạy ứng dụng và cho biết runtime đang thực thi chương trình.
- **`javac`** biên dịch source code thành class file; các tùy chọn source, target và release quyết định ngôn ngữ cùng API và bytecode mục tiêu.
- **`javap`** đọc class file hoặc class đã đóng gói để xem phiên bản class file, cấu trúc lớp, descriptor và bytecode.

Kết hợp ba công cụ này cho phép trả lời các câu hỏi quan trọng: executable nào thực sự được chọn; JVM đang chạy thuộc JDK nào; compiler nào đã tạo class file; class file yêu cầu mức runtime nào; ứng dụng đang nạp class từ vị trí nào; và lỗi tương thích xuất hiện ở bước biên dịch, liên kết hay thực thi.

## 1. Phân biệt runtime, compiler và class file

JDK là bộ công cụ phát triển Java, thường bao gồm Java launcher/runtime, compiler và các công cụ chẩn đoán. Trong một môi trường có nhiều JDK, ba lệnh có thể đến từ ba vị trí khác nhau nếu `PATH`, `JAVA_HOME` hoặc script cấu hình không nhất quán.

| Thành phần | Vai trò | Câu hỏi cần xác minh |
|---|---|---|
| `java` | Chạy class, module hoặc executable JAR | Process đang dùng runtime vendor/version nào? |
| `javac` | Biên dịch `.java` thành `.class` | Compiler thuộc JDK nào và target release là gì? |
| `javap` | Phân tích class file/bytecode | Class file có major version, descriptor và instruction nào? |

Phiên bản của compiler không nhất thiết bằng phiên bản bytecode được tạo ra. Ví dụ, `javac` từ JDK 21 có thể biên dịch với `--release 17`, tạo class file tương thích với Java 17 nếu source và dependency cũng đáp ứng giới hạn đó. Ngược lại, `javac` có thể tạo class file Java 21 mà runtime Java 17 không nạp được.

Vì vậy cần phân biệt:

1. **JDK dùng để biên dịch:** phiên bản và nhà cung cấp của `javac`.
2. **Mức source/API mục tiêu:** ngôn ngữ và Java SE API mà compiler được phép sử dụng.
3. **Class-file version:** phiên bản định dạng bytecode được ghi vào file `.class`.
4. **JVM dùng để chạy:** runtime thực tế của process.

Đây là bốn thông tin có liên quan nhưng không thể thay thế cho nhau.

## 2. Xác định executable Java mà hệ thống đang chọn

Trước khi chạy kiểm tra phiên bản, hãy xác định lệnh `java`, `javac` và `javap` được phân giải thành file nào. Chỉ nhìn `JAVA_HOME` không đủ vì shell có thể tìm executable khác trước nó trong `PATH`, script có thể dùng đường dẫn tuyệt đối hoặc service/container có môi trường riêng.

### 2.1. Trên Windows PowerShell

```powershell
Get-Command java -All
Get-Command javac -All
Get-Command javap -All
where.exe java
where.exe javac
where.exe javap
$env:JAVA_HOME
```

`Get-Command` cho biết PowerShell sẽ chọn lệnh nào và liệt kê các kết quả tìm thấy. `where.exe` tìm executable theo `PATH`. Hai lệnh có thể trả về nhiều vị trí nếu máy cài nhiều JDK.

### 2.2. Trên Linux hoặc macOS

```bash
command -v java
command -v javac
command -v javap
type -a java
type -a javac
type -a javap
printf '%s\n' "$JAVA_HOME"
readlink -f "$(command -v java)"
readlink -f "$(command -v javac)"
```

`command -v` cho biết lệnh được shell phân giải; `type -a` có thể cho thấy alias, function hoặc nhiều executable; `readlink -f` trên Linux giúp tìm đích thực của symlink. Trên macOS, `readlink -f` không có sẵn mặc định; có thể kiểm tra symlink bằng `ls -l` và truy vết đường dẫn theo công cụ của hệ điều hành.

Nếu shell đã được mở trước khi thay đổi `PATH`, hãy mở shell mới hoặc cập nhật môi trường trước khi kiểm tra lại. Với service, container hoặc pipeline, phải kiểm tra trong chính môi trường tạo process đó; kết quả từ terminal cá nhân không đại diện cho production.

### 2.3. Gọi công cụ qua JAVA_HOME để loại bỏ sự mơ hồ

Khi muốn kiểm tra một JDK cụ thể, gọi executable bằng đường dẫn rõ ràng.

PowerShell:

```powershell
& "$env:JAVA_HOME\bin\java.exe" --version
& "$env:JAVA_HOME\bin\javac.exe" --version
& "$env:JAVA_HOME\bin\javap.exe" --version
```

Linux/macOS:

```bash
"$JAVA_HOME/bin/java" --version
"$JAVA_HOME/bin/javac" --version
"$JAVA_HOME/bin/javap" --version
```

Cách gọi này xác nhận bộ công cụ ở thư mục `JAVA_HOME`. Nó không chứng minh ứng dụng production cũng dùng thư mục đó; cần kiểm tra command line và executable của process runtime riêng.

## 3. Dùng java để xác minh runtime

### 3.1. Kiểm tra phiên bản Java

```bash
java -version
java --version
```

`java -version` là cách gọi quen thuộc và tương thích với nhiều đời JDK. `java --version` hiển thị định dạng phiên bản mới trên các JDK hỗ trợ, bắt đầu từ JDK 9. Kết quả thường cho biết phiên bản, nhà cung cấp hoặc build của runtime.

Ví dụ minh họa:

```text
openjdk version "21.0.5" 2024-10-15
OpenJDK Runtime Environment Temurin-21.0.5+11
OpenJDK 64-Bit Server VM Temurin-21.0.5+11
```

Thông tin trên cho biết lệnh `java` vừa gọi là một bản OpenJDK 21 thuộc distribution Temurin. Nó chưa chứng minh process của ứng dụng đang chạy cùng binary, cũng chưa cho biết class file ứng dụng được biên dịch ở release nào.

### 3.2. Kiểm tra các system property của runtime mới

```bash
java -XshowSettings:properties -version
```

Lệnh này tạo một JVM mới, in một số system property rồi kết thúc. Các property thường hữu ích khi khảo sát gồm:

| Property | Ý nghĩa |
|---|---|
| `java.version` | Phiên bản Java runtime |
| `java.vendor` | Nhà cung cấp runtime |
| `java.home` | Thư mục runtime được JVM sử dụng |
| `java.vm.name` | Tên VM |
| `java.vm.version` | Phiên bản VM |
| `java.class.version` | Phiên bản class file mà runtime hỗ trợ theo đặc tả của VM |
| `os.name`, `os.arch` | Hệ điều hành và kiến trúc |
| `file.encoding` | Charset mặc định của JVM |
| `user.timezone` | Timezone mặc định nếu đã được xác định |

Có thể lọc output theo hệ điều hành để tìm property cần quan sát, nhưng không nên lưu toàn bộ output vào ticket nếu nó chứa đường dẫn nội bộ hoặc thông tin nhạy cảm.

Lưu ý: `java -XshowSettings:properties -version` quan sát JVM mới do lệnh này tạo. Nó không đọc property của một process ứng dụng đang chạy. Để kiểm tra process hiện hữu, cần dùng công cụ attach như `jcmd`, JMX hoặc một endpoint chẩn đoán được ứng dụng cung cấp và được bảo vệ phù hợp.

### 3.3. Kiểm tra module runtime

Với JDK 9 trở lên, có thể liệt kê module có trong runtime image:

```bash
java --list-modules
```

Kết quả giúp xác định runtime có module nền tảng cần thiết hay không. Điều này hữu ích nếu ứng dụng được chạy bằng custom runtime image tạo qua `jlink`, vì image rút gọn có thể không chứa mọi module của một JDK đầy đủ.

Khi chạy ứng dụng module, có thể dùng:

```bash
java --show-module-resolution --module-path mods --module com.example.app/com.example.Main
```

`--show-module-resolution` in thông tin quá trình phân giải module. Nó hữu ích khi migration làm thay đổi module path, module descriptor hoặc quan hệ `requires`. Cú pháp module phải phù hợp với cấu trúc module thực tế của ứng dụng.

### 3.4. Xác minh runtime của process đang chạy

Lệnh `java -version` chỉ cho biết runtime của lệnh vừa gọi. Để xác minh ứng dụng đang chạy, cần xác định PID và truy vấn chính process đó. Với HotSpot/OpenJDK, có thể dùng:

```bash
jps -lv
jcmd <pid> VM.version
jcmd <pid> VM.command_line
jcmd <pid> VM.system_properties
```

Các lệnh này giúp nhận diện JVM, phiên bản VM, command line và system properties của process tại thời điểm truy vấn. `jcmd` cần quyền attach phù hợp; có thể không hoạt động nếu khác user, khác container namespace, process đã tắt attach hoặc runtime không hỗ trợ công cụ tương ứng.

Nếu không thể attach, có thể ghi nhận phiên bản từ log khởi động của ứng dụng hoặc một endpoint chẩn đoán được kiểm soát. Không suy luận runtime production từ phiên bản cài trên máy build.

## 4. Dùng javac để xác minh compiler và mức tương thích mục tiêu

### 4.1. Xác định phiên bản compiler

```bash
javac -version
javac --version
```

Hai dạng trên được hỗ trợ theo phiên bản JDK; `--version` là cú pháp hiện đại. Output cho biết compiler được gọi, nhưng chưa cho biết compiler tạo class file ở release nào. Mức mục tiêu được xác định bởi tùy chọn khi biên dịch, ví dụ `--release`, `-source` và `-target`.

Nếu `java --version` và `javac --version` cho kết quả khác major version, máy đang phân giải runtime và compiler từ các JDK khác nhau hoặc đang dùng một cấu hình toolchain riêng. Điều này có thể có chủ đích, nhưng phải được ghi nhận và kiểm soát.

### 4.2. Phân biệt source, target và release

Các tùy chọn biên dịch có ý nghĩa khác nhau:

| Tùy chọn | Kiểm soát điều gì? | Giới hạn |
|---|---|---|
| `-source N` | Cú pháp/ngôn ngữ Java được chấp nhận | Không tự giới hạn API JDK được sử dụng |
| `-target N` | Phiên bản class file được tạo | Không tự bảo đảm code chỉ dùng API có trong release N |
| `--release N` | Source level, target class file và Java SE API công khai của release N | Có từ JDK 9; chỉ hỗ trợ các release mà compiler hiện tại có dữ liệu tương ứng |

Khi dùng JDK 9 trở lên để biên dịch cho một release cũ hơn, ưu tiên `--release`. Chỉ đặt `-source 17 -target 17` trên compiler JDK 21 chẳng hạn, vẫn có thể vô tình tham chiếu API mới của JDK 21; class file tạo ra có thể không chạy trên JDK 17 vì thiếu method hoặc class API.

Không kết hợp `--release` với `-source` hoặc `-target` trong cùng lệnh. Chọn một cách cấu hình nhất quán.

### 4.3. Biên dịch cho release đích

Giả sử ứng dụng cần chạy trên Java 17 nhưng môi trường build dùng JDK 21:

```bash
mkdir -p out
javac --release 17 -d out src/main/java/com/example/Main.java
```

`--release 17` yêu cầu compiler dùng mức ngôn ngữ và API Java SE của release 17, đồng thời tạo class file theo định dạng phù hợp với Java 17. `-d out` đặt file `.class` vào thư mục output.

Chạy bằng runtime đích để kiểm tra:

```bash
/path/to/jdk-17/bin/java -cp out com.example.Main
```

Trong thực tế, cần biên dịch toàn bộ source set với classpath/module path và dependency đúng, không chỉ một file đơn lẻ. Nếu dùng thư viện ngoài, `--release` chỉ kiểm soát API Java SE; nó không bảo đảm các thư viện bên thứ ba cũng tương thích với runtime đích.

### 4.4. Kiểm tra cấu hình compiler khi build project

Với build tool, cần tìm cấu hình compiler thực tế chứ không chỉ xem `javac` mặc định trong terminal. Gradle có thể dùng Java toolchain, `options.release`, `sourceCompatibility`, `targetCompatibility`, compiler fork hoặc task-specific setting. Maven có thể cấu hình `maven-compiler-plugin` với `release`, `source` và `target`.

Các cấu hình này có thể khác nhau giữa main source, test source, generated source hoặc module con. Hãy xác nhận task nào đã chạy và compiler nào được task đó sử dụng. `javac -version` ở terminal không chứng minh Gradle/Maven đã gọi đúng compiler nếu build tool chọn toolchain riêng.

## 5. Dùng javap để đọc class file

`javap` là disassembler của Java class file. Nó có thể hiển thị cấu trúc lớp, method, field, descriptor, constant pool, annotation và bytecode. Công cụ này rất hữu ích khi cần biết một file `.class` được tạo ra ở mức nào và code đã biên dịch chứa những gì.

### 5.1. Xem phiên bản công cụ

```bash
javap -version
```

Lệnh này cho biết phiên bản `javap` đang chạy. Đây là phiên bản công cụ phân tích, không phải phiên bản class file đang kiểm tra. Muốn biết class file version, cần dùng `-verbose` trên class cụ thể.

### 5.2. Xem cấu trúc lớp

```bash
javap -classpath build/classes/java/main com.example.Main
```

Lệnh tìm class `com.example.Main` trong thư mục class output và hiển thị public/protected member cùng chữ ký ở dạng Java-like. `-classpath` chỉ định nơi tìm class; tên lớp được truyền theo dạng fully qualified name, không kèm `.class`.

Muốn xem cả member private:

```bash
javap -p -classpath build/classes/java/main com.example.Main
```

Muốn xem descriptor JVM của method và field:

```bash
javap -s -classpath build/classes/java/main com.example.Main
```

Descriptor giúp xác minh chữ ký ở cấp bytecode, bao gồm kiểu tham số, kiểu trả về và representation của primitive/reference. Điều này hữu ích khi điều tra lỗi linkage giữa thư viện đã biên dịch và API runtime.

### 5.3. Xem class-file version và metadata

```bash
javap -verbose -classpath build/classes/java/main com.example.Main
```

Trong output, tìm các dòng như:

```text
minor version: 0
major version: 61
```

`major version` là trường phiên bản chính trong header class file. Một số mốc thường gặp:

| Java release | Class-file major version |
|---|---:|
| Java 8 | 52 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |
| Java 25 | 69 |

Các số trên là mốc phiên bản class file, không phải số phiên bản của `javap`. Nếu thấy major version 65, class file được tạo theo định dạng Java 21; nó không tự chứng minh compiler là JDK 21 vì compiler mới hơn cũng có thể tạo target Java 21.

Với class dùng preview feature, `minor version` có thể có giá trị đặc biệt `65535`. Class file preview chỉ được chạy bằng runtime cùng release có bật preview, thường qua `--enable-preview`; không thể coi class file preview là bytecode portable sang release kế tiếp.

### 5.4. Đọc bytecode

```bash
javap -c -classpath build/classes/java/main com.example.Main
```

`-c` hiển thị JVM instruction của từng method. Ví dụ, một lời gọi method trong source có thể trở thành `invokevirtual`, `invokestatic`, `invokeinterface` hoặc `invokespecial`. Bytecode giúp kiểm tra compiler đã tạo lời gọi và luồng điều khiển nào, đặc biệt khi điều tra bridge method, lambda, method reference, boxing/unboxing hoặc khác biệt do compiler.

Kết hợp các tùy chọn:

```bash
javap -p -s -c -verbose -classpath build/classes/java/main com.example.Main
```

Output chi tiết có thể gồm:

- Access flags, superclass và interface.
- Field, method và JVM descriptor.
- Constant pool và symbolic reference.
- Bytecode instruction và operand.
- Line number table, local variable table nếu class được biên dịch kèm debug information.
- Annotation và attribute được lưu trong class file.

Không phải mọi metadata đều có mặt. Ví dụ, tên biến local có thể không được lưu nếu compiler không tạo debug information tương ứng. `javap` phân tích artifact đã biên dịch, không tái dựng đầy đủ source code gốc.

### 5.5. Phân tích class trong JAR

Có thể chỉ định JAR làm classpath:

```bash
javap -verbose -classpath app.jar com.example.Main
javap -c -classpath app.jar com.example.service.OrderService
```

Điều này giúp kiểm tra class đã đóng gói trong artifact thay vì chỉ xem thư mục output trước packaging. Hai file cùng tên có thể tồn tại trong nhiều thư mục hoặc JAR; `javap` sẽ phân giải theo classpath được cung cấp. Hãy chỉ định rõ artifact và classpath để tránh kiểm tra nhầm bản.

Với multi-release JAR, có thể yêu cầu `javap` chọn view theo release:

```bash
javap --multi-release 17 -verbose -classpath library.jar com.example.LibraryType
```

Điều này quan trọng vì multi-release JAR có thể chứa class nền và các bản class thay thế trong `META-INF/versions/<N>/`. Runtime chọn bản phù hợp với release đang chạy; phân tích sai view có thể dẫn đến kết luận sai về bytecode thực tế.

## 6. Xác minh class file có chạy được trên runtime đích

Một class file thông thường chỉ có thể được JVM hỗ trợ khi class-file version của nó không vượt quá mức mà JVM hiểu. Nếu ứng dụng nạp class file mới hơn runtime, thường xuất hiện `UnsupportedClassVersionError`.

Ví dụ: Java 21 tạo class file major 65; runtime Java 17 chỉ hỗ trợ đến major 61. Nếu chạy class major 65 trên Java 17, JVM không thể nạp class đó. Việc đổi tên JAR, tăng heap hoặc thêm dependency không giải quyết được lỗi định dạng bytecode này.

### 6.1. Kiểm tra nhanh bằng javap và java

Giả sử class nằm trong `build/classes/java/main`:

```bash
javap -verbose -classpath build/classes/java/main com.example.Main
java -version
java -cp build/classes/java/main com.example.Main
```

Đọc `major version` từ `javap`, sau đó đối chiếu runtime thực tế. Lệnh chạy cuối cùng là phép xác minh trực tiếp, vì ngoài class-file version, ứng dụng còn có thể thất bại do thiếu class, thiếu method, module access hoặc dependency runtime.

### 6.2. Phân biệt lỗi version với lỗi linkage và classpath

| Lỗi | Ý nghĩa thường gặp | Hướng điều tra |
|---|---|---|
| `UnsupportedClassVersionError` | JVM không hỗ trợ class-file version hoặc preview metadata của class | Kiểm tra major/minor version bằng `javap -verbose`, xác minh runtime thực tế |
| `ClassNotFoundException` | Code yêu cầu nạp một class nhưng class loader không tìm thấy | Kiểm tra classpath/module path và artifact |
| `NoClassDefFoundError` | Class cần thiết không có sẵn lúc linkage/runtime, hoặc khởi tạo class trước đó thất bại | Kiểm tra dependency, class loader và exception gốc |
| `NoSuchMethodError` | Bytecode tham chiếu method mà class được nạp lúc runtime không cung cấp | Kiểm tra version thư viện và descriptor bằng `javap -s` |
| `NoSuchFieldError` | Bytecode tham chiếu field không có trong class runtime | Kiểm tra API và artifact thực tế được nạp |
| `IllegalAccessError` | Quyền truy cập ở cấp bytecode/module không đáp ứng | Kiểm tra access flags, module và dependency |
| `InaccessibleObjectException` | Reflection bị module system chặn | Kiểm tra reflective access, `--add-opens` và thư viện liên quan |

Không nên gom mọi lỗi runtime thành “sai Java version”. `UnsupportedClassVersionError` chỉ ra vấn đề định dạng class file; `NoSuchMethodError` thường là lệch phiên bản API giữa compile-time và runtime; `ClassNotFoundException` thường liên quan classpath hoặc module path. Chẩn đoán đúng loại lỗi giúp chọn đúng cách sửa.

## 7. Xác minh class mà JVM thực sự nạp

Một dự án có thể chứa nhiều bản class cùng fully qualified name: trong thư mục build cũ, nhiều JAR, thư mục plugin hoặc thư viện do application server cung cấp. `javap` kiểm tra class ở classpath do bạn chỉ định; điều đó chưa chứng minh runtime đã nạp đúng file đó.

Với HotSpot/OpenJDK trên JDK 9 trở lên, có thể bật unified logging:

```bash
java -Xlog:class+load=info -cp app.jar com.example.Main
```

Log class loading thường cho biết tên lớp và nguồn nạp, giúp tìm class đến từ JAR hoặc thư mục nào. Với JDK cũ hơn, `-verbose:class` là lựa chọn quen thuộc:

```bash
java -verbose:class -cp app.jar com.example.Main
```

Các tùy chọn logging tạo nhiều output; khi chạy production cần chọn mức log, thời gian và nơi lưu phù hợp. Không nên bật log class loading lâu dài trên hệ thống tải lớn nếu chưa đánh giá chi phí và dung lượng log.

Khi đã tìm ra nguồn class, kiểm tra đúng artifact đó:

```bash
javap -verbose -classpath path/to/the-loaded-library.jar com.example.LibraryType
```

Nếu runtime dùng custom class loader, plugin loader hoặc module layer, nguồn nạp có thể phức tạp hơn classpath đơn giản. Khi đó cần kết hợp log, cấu hình class loader và bằng chứng runtime của ứng dụng.

## 8. Kiểm tra classpath và module path

Ngay cả khi class file có major version phù hợp, runtime vẫn có thể nạp nhầm dependency hoặc không tìm được class cần thiết.

### 8.1. Classpath

Ví dụ chạy ứng dụng với thư mục class và thư viện:

```bash
java -cp "build/classes/java/main:lib/*" com.example.Main
```

Trên Windows, dấu phân tách classpath là dấu chấm phẩy:

```powershell
java -cp "build/classes/java/main;lib/*" com.example.Main
```

Thứ tự classpath có thể ảnh hưởng class nào được tìm thấy trước khi có nhiều bản cùng tên. Hãy kiểm tra thứ tự và nội dung thư mục/JAR thực tế, đặc biệt khi migration thay đổi dependency resolution hoặc packaging.

### 8.2. Module path

Ứng dụng modular sử dụng module path và module name:

```bash
java --module-path mods --module com.example.app/com.example.Main
```

`javac` cũng có các tùy chọn module path như `--module-path` và `--module-source-path`; `javap` có thể phân tích module qua `--module-path` và `--module`. Nếu chuyển ứng dụng từ classpath sang module path, cần xác minh module descriptor, exported package, required module và reflective access.

### 8.3. Class trong multi-release JAR

Một multi-release JAR có thể cung cấp implementation khác nhau cho các JDK khác nhau. Vì vậy, một lệnh `javap` không chỉ định release có thể hiển thị view khác với class mà runtime cụ thể chọn. Dùng `javap --multi-release N` để phân tích view tương ứng và kiểm tra cấu trúc JAR khi cần.

## 9. Một quy trình xác minh thực tế cho Java migration

Có thể dùng quy trình sau cho mỗi ứng dụng hoặc module cần chuyển sang JDK mới.

### Bước 1: Ghi nhận runtime hiện tại và runtime mục tiêu

Chạy `java --version` trong môi trường tương ứng, ghi vendor, version, build và `java.home`. Xác định executable mà service/container thực sự gọi. Ghi riêng JDK hiện tại và JDK đích; không suy luận từ máy phát triển.

### Bước 2: Ghi nhận compiler thực tế

Chạy `javac --version` và kiểm tra đường dẫn executable. Với Gradle/Maven, xác minh toolchain/compiler mà task sử dụng. Ghi lại release mục tiêu trong build configuration, bao gồm cấu hình khác nhau giữa main, test và generated source nếu có.

### Bước 3: Kiểm tra class file được tạo ra

Sau build sạch, dùng `javap -verbose` với class đại diện ở output và trong artifact đã đóng gói. Kiểm tra `major version`, preview marker nếu có, descriptor và các API/method mà bytecode tham chiếu khi cần.

### Bước 4: Chạy artifact trên runtime đích

Dùng đường dẫn `java` rõ ràng của JDK đích, classpath/module path đúng với cách triển khai. Chạy smoke test và luồng chức năng đại diện. Lưu lại runtime identity và kết quả thực thi.

### Bước 5: Xác minh nguồn class runtime

Nếu có lỗi linkage hoặc nghi ngờ nạp nhầm dependency, bật class loading log trong môi trường kiểm thử. Xác định JAR/thư mục cung cấp class và dùng `javap` phân tích chính artifact đó.

### Bước 6: Đối chiếu khác biệt và xử lý

Phân loại khác biệt là runtime version, class-file version, compiler target, API Java SE, dependency linkage, classpath/module path hay module access. Điều chỉnh build/toolchain/dependency hoặc cấu hình runtime theo đúng nguyên nhân rồi chạy lại kiểm tra liên quan.

### Bước 7: Lưu bằng chứng

Lưu command đã chạy, phiên bản công cụ, release mục tiêu, major version của class đại diện, artifact checksum hoặc build id, runtime được dùng và kết quả test. Che đường dẫn hoặc tham số nhạy cảm trước khi chia sẻ log.

## 10. Ví dụ đầu cuối: biên dịch bằng JDK mới, chạy trên JDK cũ hơn

Giả sử đội phát triển dùng JDK 21 để build nhưng sản phẩm cần hỗ trợ Java 17. Có thể thực hiện:

```bash
# 1. Xác nhận compiler
javac --version

# 2. Biên dịch với API và class-file target của Java 17
javac --release 17 -d out src/main/java/com/example/Main.java

# 3. Kiểm tra class file
javap -verbose -classpath out com.example.Main

# 4. Chạy bằng runtime Java 17
/opt/jdk-17/bin/java -version
/opt/jdk-17/bin/java -cp out com.example.Main
```

Kết quả mong đợi của `javap` là major version 61 cho class Java 17 thông thường. Runtime Java 17 có thể nạp class đó nếu dependency, module và các điều kiện runtime khác cũng tương thích.

Nếu thay `--release 17` bằng `-source 17 -target 17` khi compiler là JDK 21, compiler vẫn có thể cho phép tham chiếu API chỉ tồn tại ở JDK 21. Khi chạy trên Java 17, class file có thể qua được kiểm tra major version nhưng thất bại với `NoSuchMethodError` hoặc `NoClassDefFoundError`. Đây là lý do cần kiểm soát API target cùng bytecode target.

## 11. Checklist xác minh runtime và class file

- [ ] Đã xác định đường dẫn thực tế của `java`, `javac` và `javap`.
- [ ] Đã ghi vendor, version, build và `java.home` của runtime cần khảo sát.
- [ ] Đã xác minh runtime của process đang chạy, không chỉ runtime của terminal.
- [ ] Đã xác định compiler thực tế mà build tool hoặc pipeline sử dụng.
- [ ] Đã ghi rõ source level, API release và target class-file version.
- [ ] Đã dùng `javap -verbose` kiểm tra class đại diện từ output và artifact đóng gói.
- [ ] Đã kiểm tra preview class file nếu dự án bật preview feature.
- [ ] Đã chạy artifact bằng đúng runtime đích.
- [ ] Đã kiểm tra classpath/module path và nguồn class được JVM nạp khi có nghi ngờ.
- [ ] Đã phân biệt lỗi class-file version với lỗi API linkage, class loading và module access.
- [ ] Đã lưu bằng chứng theo build id/release và che dữ liệu nhạy cảm.

## 12. Kết luận

`java`, `javac` và `javap` cung cấp ba góc nhìn bổ sung để xác minh một ứng dụng Java: runtime thực sự được chọn, compiler và release mục tiêu, cùng định dạng và nội dung class file đã tạo. Khi migration, hãy xác định đúng executable trong môi trường triển khai, dùng `--release` để ràng buộc cả API và bytecode khi phù hợp, phân tích artifact bằng `javap`, rồi chạy chính artifact đó trên runtime đích. Nếu xảy ra lỗi, phân loại theo class-file version, linkage, classpath hoặc module access để xử lý đúng nguyên nhân.
