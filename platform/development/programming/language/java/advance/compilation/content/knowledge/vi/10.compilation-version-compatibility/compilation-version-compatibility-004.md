# Vì sao -target đơn lẻ không bảo đảm dùng được API trên Java cũ

## 1. Vấn đề thật sự nằm ở đâu?

Giả sử dự án phải chạy trên **Java 8**, nhưng lập trình viên dùng JDK 21 để biên dịch. Họ thấy compiler tạo được file `.class` có **major version 52** (định dạng class file tương ứng Java 8), rồi kết luận chương trình chắc chắn chạy được trên Java 8.

Kết luận đó sai nếu mã nguồn đã gọi một API chỉ xuất hiện ở Java mới hơn, ví dụ `String.repeat(int)` được bổ sung từ **Java 11**. JVM Java 8 hiểu được định dạng class file major 52, nhưng `java.lang.String` trong Java 8 **không có phương thức `repeat(int)`** để liên kết và gọi. Chương trình có thể thất bại tại runtime với `NoSuchMethodError`.

Cần phân biệt ba điều kiện:

1. **Ngữ pháp/ngôn ngữ được phép dùng**: `-source`/`--source`.
2. **Định dạng class file mà JVM cũ có thể nạp**: `-target`/`--target`.
3. **API nền tảng hiện diện trong Java release đích**: thư viện Java SE/JDK được đưa vào môi trường kiểm tra kiểu lúc compile, hoặc được giới hạn bằng `--release`.

`-target` giải quyết chủ yếu câu hỏi **số 2**, không tự giải quyết câu hỏi **số 3**. Trên JDK hiện đại, cách thường được khuyến nghị khi nhắm đến Java cũ là **`javac --release <phiên-bản>`**, đồng thời quản lý phiên bản các thư viện ngoài Java SE/JDK và chạy test trên runtime thực sự được hỗ trợ.

Sau bài này, bạn có thể giải thích vì sao major version đúng vẫn gặp lỗi linkage, tái hiện lỗi bằng code Java 8 hợp lệ, chọn đúng tùy chọn `javac` và kiểm chứng toàn bộ chuỗi compile–package–run.

## 2. Ba trục tương thích: source, bytecode và API

| Trục | Tùy chọn/nguồn quy tắc | Trả lời câu hỏi | Không bảo đảm |
| --- | --- | --- | --- |
| **Source language level** | `--source N` | Mã có dùng cú pháp/tính năng ngôn ngữ hợp lệ cho Java N không? | API được gọi có tồn tại trong Java N hay không |
| **Class file version** | `--target N` | File `.class` được tạo theo version mà JVM đích có thể nhận không? | Các phương thức/lớp được gọi có ở runtime Java N hay không |
| **Platform API level** | `--release N`, hoặc cấu hình platform classes cũ phù hợp | Compiler kiểm tra source theo ngôn ngữ N, tạo class file N và chỉ nhìn thấy tập API nền tảng tương ứng N | Các JAR bên thứ ba hoặc runtime environment chắc chắn tương thích |

Ví dụ `List.of(...)` là API được bổ sung trong Java 9; `String.repeat(int)` có từ Java 11; `String.formatted(Object...)` có từ Java 15. Những lời gọi này có thể được viết bằng cú pháp Java rất cũ: lỗi của chúng khi nhắm đến Java cũ xuất phát từ **API không tồn tại**, không phải từ cú pháp lambda, record hay switch expression.

**Định dạng bytecode không ghi “mọi API được tham chiếu đều có trên Java 8”.** Class file chứa các symbolic references đến class, field và method. Máy ảo cần giải quyết các reference đó khi liên kết hoặc khi thực thi thao tác liên quan. Một reference có thể hợp lệ trong file class nhưng không tìm được method trên runtime cũ.

## 3. Chính xác -target kiểm soát điều gì?

Ví dụ trên JDK 21:

```bash
javac --source 8 --target 8 -d out-target ApiLeak.java
```

- `--source 8` yêu cầu phân tích nguồn theo quy tắc ngôn ngữ Java 8.
- `--target 8` yêu cầu tạo class file cho Java 8, thường có **major version 52**.
- Nếu không khóa API nền tảng, compiler đang chạy trên JDK 21 vẫn có thể thấy các phương thức API từ JDK 21 khi phân tích và liên kết lời gọi trong source.

Điều này **không** có nghĩa riêng `-target 8` luôn là lệnh hợp lệ. Trên một bản `javac` hiện đại mà mức `--source` mặc định mới hơn Java 8, `--target 8` đơn lẻ có thể bị từ chối vì **target không được thấp hơn source level**. Việc thêm `--source 8` giúp lệnh vượt qua ràng buộc phiên bản source/target nhưng **vẫn chưa giải quyết kiểm soát API**.

Một bảng class file version hay gặp:

| Java release | Major version của class file |
| --- | ---: |
| Java 8 | 52 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |

Bảng này giúp xác định khả năng JVM đọc định dạng class file. Nó không nói gì về sự tồn tại của `String.repeat`, `java.net.http.HttpClient` hay API bên thứ ba trên máy sẽ chạy chương trình.

Lệnh `javap -verbose` có thể đọc `major version` và các symbolic references. Nhưng kể cả khi major version đúng, cần kiểm tra tiếp API dependencies.

## 4. Ví dụ hoàn chỉnh: Java 8 bytecode gọi nhầm API Java 11

Tạo một file tên đúng **`ApiLeak.java`**:

```java
public class ApiLeak {
    public static void main(String[] args) {
        System.out.println("ha".repeat(3));
    }
}
```

Không có cú pháp mới như record hay text block trong ví dụ. Phần đáng chú ý là **lời gọi `String.repeat(int)`**, được thêm trong Java 11.

### 4.1. Biên dịch bằng JDK 21 với source và target 8

```bash
javac --source 8 --target 8 -d out-target ApiLeak.java
```

Trên JDK 21, lệnh này có thể biên dịch thành công: compiler phân tích cú pháp ở mức Java 8, tạo class file Java 8, nhưng tìm method `repeat(int)` trong Java SE API mà JDK 21 đang cung cấp cho compilation. `javac` có thể in cảnh báo về lựa chọn source/target cũ hoặc bootstrap classpath; **không dùng nguyên văn cảnh báo làm quy tắc cố định**.

Thử chạy với Java 21:

```bash
java -cp out-target ApiLeak
```

**Stdout khi chạy trên Java 21:**

```text
hahaha
```

Bởi vì runtime Java 21 có `String.repeat(int)`.

### 4.2. Quan sát class file: version cũ, reference mới

```bash
javap -verbose -classpath out-target ApiLeak
```

Tìm phần liên quan trong output. Bạn sẽ thấy cấu trúc tương tự:

```text
major version: 52
...
Methodref ... java/lang/String.repeat:(I)Ljava/lang/String;
```

Đây là **trích diễn giải các dòng liên quan**, không phải output đầy đủ: constant-pool index và instruction offsets có thể khác. Cặp dữ liệu này chứng minh điều quan trọng:

- File class có version **52**, tương thích format Java 8.
- Nội dung vẫn chứa symbolic reference đến `java/lang/String.repeat(int)`, một method không tồn tại trong Java 8.

`javap` chỉ đọc class file, nên nó không tự xác minh method sẽ được runtime Java 8 cung cấp.

### 4.3. Chạy trên JRE/JDK 8 thực sự

Nếu máy có runtime Java 8, hãy dùng **đường dẫn cụ thể tới executable `java` của Java 8**, không đoán rằng `java` trên `PATH` là Java 8:

```bash
/path/to/jdk8/bin/java -cp out-target ApiLeak
```

Đường dẫn ở đây là ký hiệu minh họa, phải thay bằng executable Java 8 thật. Class file version 52 có thể được JVM Java 8 nạp, nhưng khi lời gọi `String.repeat(int)` được giải quyết, runtime không tìm được method tương ứng. **Loại lỗi kỳ vọng** là:

```text
java.lang.NoSuchMethodError
```

Thông điệp chi tiết, cách hiển thị stack trace và thời điểm liên kết có thể khác giữa các JVM; không nên yêu cầu đúng một chuỗi stderr tuyệt đối. Điểm chính: đây **không phải `UnsupportedClassVersionError`**, vì định dạng file class vốn đã phù hợp Java 8. Nó là vấn đề **thiếu method ở API runtime**.

Nếu chỉ có JDK 21, bạn vẫn có thể xác minh được class major 52 và method reference. Nhưng **muốn tuyên bố đã kiểm thử hành vi trên Java 8**, phải thật sự chạy chương trình bằng Java 8 hoặc môi trường tương đương; không được coi việc chạy trên Java 21 là bằng chứng đủ.

## 5. Cùng source, dùng --release 8 để bắt lỗi sớm

Biên dịch lại source ở trên bằng compiler JDK 21:

```bash
javac --release 8 -d out-release ApiLeak.java
```

Lệnh này phải **thất bại ở compile time** vì `String.repeat(int)` không có trong tập API Java 8 mà `--release 8` cho compiler thấy. Dạng chẩn đoán sẽ liên quan đến việc không tìm thấy method `repeat(int)` trên `String`; chi tiết câu chữ tùy bản `javac`.

Đây là khác biệt mong muốn:

| Lệnh chạy trên JDK 21 | Compile | Vì sao |
| --- | --- | --- |
| `javac --source 8 --target 8 -d out-target ApiLeak.java` | Có thể thành công | Khóa source/target 8 nhưng mặc định chưa khóa API nền tảng Java 8 |
| `javac --release 8 -d out-release ApiLeak.java` | Thất bại | Compiler kiểm tra `String` theo API Java 8, không có `repeat(int)` |

Với đoạn code tương thích Java 8 thật sự, chẳng hạn thay lời gọi `repeat` bằng phép nối chuỗi cổ điển:

```java
public class CompatibleEight {
    public static void main(String[] args) {
        System.out.println("ha" + "ha" + "ha");
    }
}
```

Biên dịch và chạy:

```bash
javac --release 8 -d out-eight CompatibleEight.java
java -cp out-eight CompatibleEight
```

**Stdout:**

```text
hahaha
```

Bản `CompatibleEight` biên dịch thành công theo API/ngôn ngữ Java 8. Muốn hoàn tất xác nhận tương thích Java 8, chạy bản đó trên runtime Java 8 và chạy test phù hợp.

## 6. --release thực sự kiểm soát những gì?

Theo tài liệu `javac`, `--release N` kết hợp ba điều kiện:

1. Áp dụng quy tắc Java language tương ứng release N.
2. Phát class files nhắm tới release N.
3. Biên dịch dựa trên **API Java SE/JDK được hỗ trợ và được công bố** của release N.

Ví dụ:

```bash
javac --release 11 -d out11 Main.java
```

Lệnh đặt mục tiêu Java 11 về ngôn ngữ, định dạng class file và tập API nền tảng được nhìn thấy. Không có nghĩa chương trình sẽ chạy trên Java 8, hoặc dependency ngoài JDK đương nhiên tương thích Java 11.

`--release` không được kết hợp với `--source` hoặc `--target` trong cùng một lời gọi:

```bash
# Sai: hai cách cấu hình nguồn/target loại trừ nhau
javac --release 8 --source 8 ApiLeak.java
```

```bash
# Đúng: một tùy chọn chọn cả release
javac --release 8 ApiLeak.java
```

Cũng không phải mọi bản JDK đều hỗ trợ cùng danh sách release cũ. Kiểm tra:

```bash
javac --help
javac -version
```

Danh sách các giá trị hợp lệ được công bố theo từng compiler. Đừng thiết kế build bằng cách giả định JDK mới nhất có thể target mọi Java version từ trước đến nay; các release rất cũ có thể không còn được hỗ trợ.

### 6.1. Vì sao --release đáng tin cậy hơn chỉ source/target?

Một bản `javac` có thể biên dịch mã Java 8 dựa trên API của JDK đang chạy nếu chỉ có `--source 8 --target 8`. Với `--release 8`, compiler dùng dữ liệu API nền tảng cho Java 8, nên loại bỏ khả năng vô tình gọi `String.repeat`, `List.of` hoặc API Java SE mới khác.

Điều này quan trọng vì “cú pháp Java 8 hợp lệ” chưa đồng nghĩa “chương trình dùng API Java 8”. Một lệnh gọi method được viết theo cú pháp bình thường có thể không tồn tại trong release cũ.

### 6.2. Những gì --release không kiểm soát

`--release` không đảm bảo toàn bộ ứng dụng hoàn toàn chạy được trên runtime cũ nếu có các yếu tố khác:

- **Thư viện bên thứ ba:** JAR được build cho Java mới hơn có thể có class file version quá cao hoặc gọi API thiếu trên runtime mục tiêu.
- **Reflection:** code có thể tải lớp/gọi method bằng tên chuỗi; compiler không xác minh đầy đủ đường đi phản chiếu đó.
- **ServiceLoader, plugin, dynamic class loading:** các implementation được load lúc chạy có thể cần API/runtime khác.
- **Native code/JNI:** thư viện native, kiến trúc OS hoặc phiên bản DLL/SO có thể không sẵn.
- **Behavioral compatibility:** API cùng tồn tại nhưng có thay đổi hành vi, bug fix hoặc điều kiện môi trường khác.
- **Packaging và runtime config:** classpath/module path, resource, security policy hoặc entry point có thể sai.
- **Multi-release JAR và bytecode sinh động:** cần kiểm tra class được chọn trên runtime đích, không chỉ module app chính.

Vì vậy **`--release` là điều kiện build quan trọng, không phải một chứng chỉ tương thích end-to-end**. Kết hợp nó với dependency constraints và test thực tế trên JRE/JDK mục tiêu.

## 7. Những lỗi runtime cần phân biệt

| Lỗi | Điển hình khi nào | Liên hệ với -target và API |
| --- | --- | --- |
| `UnsupportedClassVersionError` | JVM cũ gặp class file có major version quá mới | `-target`/`--release` tác động trực tiếp đến class file do compiler phát |
| `NoSuchMethodError` | Method đã được tham chiếu trong bytecode nhưng không tồn tại với tên/descriptor mong đợi khi link/run | Class file format có thể hoàn toàn hợp lệ; API/runtime binary không khớp |
| `NoSuchFieldError` | Trường mà bytecode tham chiếu không có trong class runtime | Có thể do API version hoặc binary không tương thích |
| `NoClassDefFoundError` | JVM không thể tìm/định nghĩa một lớp cần thiết khi thực thi | Có thể do classpath/runtime module thiếu hoặc lỗi khi định nghĩa lớp |
| `ClassNotFoundException` | Code chủ động yêu cầu tìm class (ví dụ `Class.forName`) nhưng classloader không tìm được | Thường liên quan dynamic loading, reflection, plugin |
| `AbstractMethodError` | Dispatch tới implementation thiếu method cần thiết ở binary hierarchy | Có thể do binary incompatibility giữa các phiên bản thư viện |

Đừng nhầm `NoSuchMethodError` với một lỗi **compile-time** kiểu “cannot find symbol”: khi compile bằng `--release 8`, compiler từ chối sớm; khi compile nhầm bằng API JDK mới hơn, runtime cũ mới phát hiện thiếu method.

### 7.1. Vì sao JVM chấp nhận version 52 mà vẫn lỗi?

Class file chứa constant pool và symbolic references. Ví dụ `javap -verbose` cho thấy tham chiếu đến `java/lang/String.repeat:(I)Ljava/lang/String;`. Phiên bản major 52 chỉ cho JVM biết cấu trúc class file được viết theo định dạng Java 8. Nó không ép API của Java 8 phải có method tên `repeat`; khi JVM cần resolve tham chiếu đó, runtime Java 8 không có implementation phù hợp.

### 7.2. Vì sao không sửa bằng cách “chỉ thêm -target 8”?

Nếu compile đang dùng source level mới (ví dụ JDK 21 mặc định), `-target 8` đơn lẻ có thể gây lỗi cấu hình do target thấp hơn source. Khi thêm `-source 8` thì đã giải quyết xung đột cấp ngôn ngữ, nhưng lỗi thiếu API vẫn còn. Giải pháp đúng khi muốn Java 8 compatibility là đặt **`--release 8`** (nếu JDK hỗ trợ), hoặc một toolchain/bootclasspath phù hợp với API Java 8 và kiểm chứng runtime đích.

## 8. Tại sao -source/-target cộng platform classes là cách cũ khó quản lý?

Trước khi có `--release`, để cross-compile đúng, người ta thường phải cấu hình cả:

- `-source` để giới hạn tính năng ngôn ngữ;
- `-target` để giới hạn định dạng bytecode;
- **platform classes** đúng của JDK đích để compiler không thấy nhầm API mới.

Với mục tiêu **Java 8 trở về trước**, một số cấu hình cũ dùng `-bootclasspath` trỏ đến các platform class libraries của JDK đích (và cấu hình liên quan). Lưu ý: không được đơn giản lấy `rt.jar` từ một JDK bất kỳ rồi cho rằng có môi trường chuẩn; classpath còn có thể liên quan các thư viện nền tảng khác và toàn bộ toolchain.

Với **Java 9 trở lên**, nền tảng dùng JPMS và system modules; cấu hình platform khác với bootclasspath thời Java 8. Tài liệu `javac` mô tả `--system` khi dùng `-source`/`-target` trong các tình huống target JDK 9+ cần bộ platform classes thích hợp.

**Trong dự án hiện đại, nếu không có yêu cầu đặc biệt, ưu tiên `--release`.** Nó giảm đáng kể khả năng dùng nhầm API mới do compiler đang chạy trên một JDK mới hơn runtime mục tiêu.

Không chỉnh bootclasspath hoặc dùng cờ phá encapsulation một cách tùy tiện chỉ để làm một chương trình “compile pass”. Nếu code dựa vào API nội bộ JDK, hãy xác định hợp đồng hỗ trợ và thay bằng API công khai thích hợp khi có thể.

## 9. Hướng dẫn kiểm chứng từng tầng bằng javac, javap và java

Một quy trình có thể tái hiện:

1. **Chọn runtime tối thiểu:** ví dụ Java 8.
2. **Khóa toolchain build:** ghi `javac -version`, compiler vendor/build, địa chỉ executable và cách build tool chọn JDK.
3. **Khóa ngôn ngữ và API:** dùng `--release 8` thay cho `--target 8` đơn lẻ.
4. **Ghi nguồn và dependency:** phiên bản thư viện, hash JAR, annotation processors, generated source, compile classpath/module path.
5. **Build vào thư mục sạch:** tránh class files từ các lần biên dịch khác; kiểm tra exit code và stderr.
6. **Dùng `javap -verbose`:** xem major version và các method references nghi ngờ.
7. **Chạy trên runtime thật sự:** xác minh `java -version` của môi trường mục tiêu rồi chạy chương trình và test.
8. **So sánh kết quả:** lỗi compiler, lỗi class format, lỗi linkage hoặc lỗi logic xảy ra ở các tầng khác nhau; ghi rõ tầng nào đã vượt qua.

### 9.1. Kiểm tra major version

```bash
javap -verbose -classpath out-target ApiLeak
```

Tìm dòng `major version: 52` và tham chiếu tới `String.repeat`. Nếu dùng `javap` của JDK mới, nó có thể đọc một class file hướng đến JDK cũ; **không có nghĩa runtime cũ chắc chắn có API mà class đang gọi**.

### 9.2. Kiểm tra API từ JDK mục tiêu

Chạy `javac --release 8` sẽ khiến lời gọi API Java mới bị phát hiện trước khi tạo class file. Đây là kiểm tra tĩnh hữu ích nhất khi nhắm đến API Java SE chuẩn. Với dependency bên ngoài, kiểm tra riêng binary compatibility của chúng.

### 9.3. Kiểm tra runtime thật

Dùng `java -version` và, nếu có nhiều JDK, chạy bằng đường dẫn executable cụ thể. Trong CI, tốt nhất có một job compile với `--release 8` và một job test sử dụng runtime Java 8 (nếu Java 8 còn nằm trong danh sách nền tảng được hỗ trợ của dự án).

Việc chạy trên Java 21 **không thay thế** test Java 8: Java 21 có nhiều API hơn và nạp được nhiều class file cũ.

## 10. Áp dụng trong Gradle và Maven

### 10.1. Gradle (Groovy DSL)

Ví dụ dự án dùng Gradle Java plugin, compiler là JDK 21 nhưng đích chạy Java 8:

```groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 8
    options.encoding = 'UTF-8'
}
```

Đây là **cấu hình build**, không phải file Java độc lập. `toolchain` chọn một JDK phù hợp cấp 21 cho các Java tool tasks; `options.release = 8` yêu cầu compiler kiểm tra source/class format/API nền tảng theo Java 8. Cần đảm bảo bản JDK đã được resolve thực sự hỗ trợ `--release 8`.

**Đừng thay `options.release` bằng việc chỉ đặt `targetCompatibility = '1.8'` rồi mặc định cho rằng API Java 8 đã được khóa**. Với build có toolchain và nhiều source sets, kiểm tra các compile tasks khác nhau như main/test, processor paths và dependencies đã resolve.

### 10.2. Maven Compiler Plugin

Ví dụ cấu hình (cần Maven Compiler Plugin có hỗ trợ tham số `release`):

```xml
<project>
  ...
  <properties>
    <maven.compiler.release>8</maven.compiler.release>
  </properties>
  ...
</project>
```

Đây là **đoạn cấu hình minh họa** trong `pom.xml` của một dự án Maven; dấu `...` là vị trí các phần XML khác của POM, không phải một file POM hoàn chỉnh có thể chạy độc lập. Cần ghi phiên bản Maven/plugin, JDK/compiler thực tế và các dependencies. Với build chạy trên JDK rất cũ, khả năng hỗ trợ `release` của compiler/plugin cần được kiểm tra theo phiên bản cụ thể.

Cả Gradle lẫn Maven đều không biến thư viện bên thứ ba đã compile cho Java mới thành binary Java 8 chỉ nhờ đặt release cho source của ứng dụng.

## 11. Thư viện bên thứ ba: lỗ hổng còn lại của --release

Giả sử thư viện `lib/modern.jar` được build bằng Java 17 nhưng ứng dụng nhắm đến Java 8. Dù `javac --release 8` làm application classes có major 52, JAR có thể vẫn chứa class major 61. Java 8 khi phải load class đó có thể ném `UnsupportedClassVersionError`.

Một trường hợp khác: JAR cũng dùng class format Java 8 nhưng bên trong gọi API chỉ có từ Java 11. Khi chạy trên Java 8, nó có thể gặp `NoSuchMethodError` tương tự ví dụ `ApiLeak`. `--release` của **bản compile ứng dụng** không kiểm chứng lại mọi binary reference nằm bên trong JAR ngoài.

Vì vậy cần:

- Chọn **đúng version thư viện hỗ trợ Java tối thiểu** của dự án; kiểm tra tài liệu và chính sách dependency.
- Kiểm tra JAR mà runtime sẽ dùng, bao gồm transitive dependencies.
- Dùng công cụ phân tích binary/class-file version khi cần; đừng coi version number trong tên JAR là bằng chứng đủ.
- Chạy integration tests trên runtime cũ thực tế, nhất là các đường đi reflection, service loader, plugin hoặc native.

**`jdeps`** có thể giúp nhận diện phụ thuộc package/module, nhưng không thay thế kiểm tra method-level availability theo từng Java release và kiểm thử runtime. Không dùng mỗi kết quả `jdeps` để tuyên bố mọi API đều tương thích Java 8.

## 12. Cạm bẫy trong thực tế

| Cạm bẫy | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Chỉ cấu hình `-target 8` | Có thể xung đột source level, hoặc vẫn dùng API mới | Ưu tiên `--release 8` |
| Dùng `-source 8 -target 8` với JDK mới | Source/class format cũ nhưng API nền tảng hiện tại | Thêm ràng buộc API bằng `--release 8` |
| Chỉ xem `major version 52` | Không phát hiện tham chiếu đến API Java 11 | Kiểm tra `--release` và thử trên Java 8 |
| Chỉ test trên JDK 21 | Không thấy lỗi thiếu method trên Java 8 | Test trên runtime tối thiểu được hỗ trợ |
| Dùng `--release 8` nhưng phụ thuộc JAR Java 17 | Class application hợp lệ nhưng dependency có major mới | Khóa và kiểm tra tất cả runtime dependencies |
| Dùng reflection hoặc plugin động | Compiler không quan sát được mọi class/method được gọi lúc chạy | Test các đường code dynamic trên runtime đích |
| Chạy class file cũ từ output directory | Thấy kết quả bất ngờ, khó xác định lần compile nào đã tạo file | Build sạch, kiểm tra classpath và artifact hashes |
| Lẫn `java` với `javac` | Compiler và runtime thực tế khác bản mong đợi | Ghi đường dẫn executable và `-version` cả hai |
| Gộp lỗi compile với lỗi linkage | Chữa sai tầng, ví dụ sửa source khi chỉ thiếu runtime dependency | Phân biệt diagnostic compile, class-format, symbol resolution |
| Kết luận từ một runtime mới | Che các lỗi Java cũ không có API | Kiểm thử runtime cũ, môi trường deploy thật |

## 13. Bài tập tự kiểm tra

**Bài 1.** JDK 21 biên dịch `ApiLeak.java` bằng `--source 8 --target 8` và `javap` cho thấy major 52. Vậy có chắc chạy được trên Java 8 không?

**Đáp án:** Không. Class còn tham chiếu `String.repeat(int)` từ Java 11. JVM Java 8 đọc được major 52 nhưng không có method đó, nên khi lời gọi được liên kết sẽ dẫn đến `NoSuchMethodError`.

**Bài 2.** Dùng riêng `--target 8` trên JDK 21, không có `--source`, có bảo đảm tạo class Java 8 thành công không?

**Đáp án:** Không. Source level mặc định theo compiler mới hơn, target 8 có thể thấp hơn source level và bị từ chối. Ngay cả khi kết hợp với `--source 8` để compile thành công, API nền tảng Java 8 vẫn chưa được bảo đảm.

**Bài 3.** Vì sao `javac --release 8 ApiLeak.java` thất bại, còn `javac --source 8 --target 8 ApiLeak.java` có thể thành công trên JDK 21?

**Đáp án:** `--release 8` giới hạn cả API Java SE/JDK tương ứng Java 8; còn source/target chủ yếu giới hạn ngôn ngữ và class-file version, vẫn có thể cho compiler thấy API của JDK đang chạy.

**Bài 4.** Ứng dụng compile với `--release 8` nhưng phụ thuộc một JAR chứa class major 61. Có chắc chạy trên Java 8 không?

**Đáp án:** Không. Java 8 không nạp được class version 61 khi cần, có thể ném `UnsupportedClassVersionError`. Release của phần source ứng dụng không hạ version của JAR ngoài.

**Bài 5.** Nếu class major 52 load thành công nhưng gọi method thiếu ở runtime, lỗi thuộc nhóm nào?

**Đáp án:** Lỗi binary linkage như `NoSuchMethodError`, không phải lỗi class file version.

**Bài 6.** Chỉ cần `javap -verbose` thấy major 52 và không có syntax Java mới, có thể bỏ qua runtime test không?

**Đáp án:** Không. Phải xét symbolic references, dependency JARs, reflection/dynamic loading, runtime configuration và chạy test trên Java 8 nếu đó là nền tảng phải hỗ trợ.

## 14. Tài liệu tham khảo

- **Oracle JDK 21 — The javac Command:** https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html — ý nghĩa `--source`, `--target`, `--release`, phần *Compiling for Earlier Releases of the Platform*.
- **Oracle JDK 21 — The javap Command:** https://docs.oracle.com/en/java/javase/21/docs/specs/man/javap.html — `-verbose` và class-file metadata.
- **Java SE 21 JVMS, Chapter 4:** https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html — class file version, constant pool, method references.
- **Java SE 21 JVMS, Chapter 5:** https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html — loading, linking, resolution và runtime errors.
- **Java SE 11 String API:** https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/lang/String.html#repeat(int) — `String.repeat(int)` có từ Java 11.
- **Gradle Java compilation/toolchains:** https://docs.gradle.org/current/userguide/toolchains.html — compiler/toolchain và Java compile options.

**Ghi nhớ:** **`-target` chỉ kiểm soát định dạng `.class`; nó không làm biến mất API mới khỏi JDK dùng để compile.** Dùng `--release` để chặn API Java SE/JDK không thuộc release đích, kiểm soát binary dependencies và chạy test trên runtime thấp nhất phải hỗ trợ để xác nhận khả năng chạy thực tế.