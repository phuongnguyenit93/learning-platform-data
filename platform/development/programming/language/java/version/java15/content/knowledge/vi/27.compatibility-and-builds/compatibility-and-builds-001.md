# Mức nguồn, `--release` và API có sẵn khi biên dịch (Java 15+)

## 1. Bài toán tương thích: build được chưa chắc chạy được

Giả sử nhóm phát triển dùng **JDK 24** để biên dịch ứng dụng nhưng phải chạy trên **Java 15**. Hai cách viết sau thoạt nhìn giống nhau:

~~~bash
javac -source 15 -target 15 Release15Demo.java
javac --release 15 Release15Demo.java
~~~

Chúng **không tương đương**:

- `-source 15` yêu cầu cú pháp/quy tắc ngôn ngữ Java 15.
- `-target 15` yêu cầu sinh **class file format** dành cho Java 15 (major version **59**).
- **`--release 15`** yêu cầu **cả cú pháp Java 15, bytecode Java 15 và tập API nền tảng được công bố/hỗ trợ trong Java 15**.

Đó là lý do một class file **major 59** có thể vẫn gọi một class/method của **JDK 17** và bị lỗi trên runtime Java 15: chỉ hạ bytecode version **chưa đủ**.

**Phạm vi cập nhật:** `--release`, Java toolchains, kiểm thử với runtime đích và việc tách API level khỏi source level là các cơ chế **còn áp dụng trong JDK hiện hành**, không phải mẹo lỗi thời. Java 15 là bối cảnh của bài học, **không phải lời khuyên dùng Java 15 không còn được hỗ trợ cho sản phẩm triển khai mới**. Với sản phẩm, chọn một runtime được nhà cung cấp và tổ chức tiếp tục hỗ trợ, rồi thay release target tương ứng.

Bài gồm lý thuyết, ba file Java chạy/biên dịch được, trường hợp compiler cố ý thất bại, hướng dẫn Maven/Gradle, cách kiểm tra JAR và giới hạn bảo đảm của `--release`.

## 2. Phân biệt bốn phiên bản thường bị trộn lẫn

| Khái niệm | Câu hỏi | Điều khiển |
| --- | --- | --- |
| **Build JDK** | Bộ `javac` thật đang chạy ở phiên bản nào? | `javac -version`, Maven/Gradle toolchain |
| **Source level** | Source code được phép sử dụng cú pháp/ngôn ngữ Java nào? | `-source` hoặc `--source` |
| **Bytecode target** | `.class` được tạo ở định dạng dành cho JVM nào? | `-target` hoặc `--target` |
| **Platform API level** | Source có gọi class/method JDK chỉ xuất hiện sau release đích không? | **`--release`** |

Ví dụ:

~~~text
JDK dùng để biên dịch: JDK 24
Câu lệnh: javac -source 15 -target 15 App.java

  Java syntax:        15
  Class file major:   59
  JDK APIs compiler thấy: có thể là JDK 24

Câu lệnh: javac --release 15 App.java

  Java syntax:        15
  Class file major:   59
  API Java SE/JDK:    theo release 15 được hỗ trợ
~~~

Không suy ra `javac` version chỉ từ `java -version`: CI/IDE có thể cài nhiều JDK, Maven/Gradle daemon hoặc toolchains cũng có thể dùng JDK khác terminal.

**Điều kiện chọn target:** dựa trên **minimum runtime version** mà artifact **cam kết** hỗ trợ, không dựa đơn giản vào JDK mới nhất đang có trên máy build.

## 3. `-source` — ngôn ngữ Java được phép viết

`javac -source N`/`--source N` yêu cầu javac dùng **các quy tắc ngôn ngữ của Java N**:

~~~bash
javac -source 15 Release15Demo.java
~~~

Nó kiểm soát việc chấp nhận cú pháp như record, switch expressions, pattern matching và các quy tắc ngữ nghĩa theo release tương ứng, **không tự giới hạn Java platform APIs hiện diện trong JDK đang build**.

### Một ví dụ cú pháp mới: `record`

~~~java
public record ModernSyntaxProbe(int id, String label) {
    public static void main(String[] args) {
        System.out.println(new ModernSyntaxProbe(1, "ok"));
    }
}
~~~

Record trở thành **tính năng final từ Java 16**. Java 15 từng có record **preview**, không phải cú pháp final được `--release 15` bật mặc định. Trên JDK 24 đã kiểm chứng:

~~~bash
javac --release 15 ModernSyntaxProbe.java
~~~

Kết quả biên dịch **thất bại**; diagnostic quan trọng:

~~~text
error: records are not supported in -source 15
(use -source 16 or higher to enable records)
~~~

Khi đổi sang release có hỗ trợ:

~~~bash
javac --release 17 ModernSyntaxProbe.java
java ModernSyntaxProbe
~~~

Stdout:

~~~text
ModernSyntaxProbe[id=1, label=ok]
~~~

**Đừng đánh đồng preview với cú pháp Java ổn định.** Preview features có thể thay đổi hoặc bị loại bỏ; compiler/runtime của phiên bản phát hành preview thường phải phù hợp với nhau. Không kỳ vọng một JDK mới có thể bật lại mọi preview của Java 15 bằng `--enable-preview --release 15`. Trong ứng dụng dài hạn nên dùng feature đã final tại runtime tối thiểu.

## 4. `-target` — class-file major version

`-target N`/`--target N` chủ yếu điều khiển **định dạng `.class`** mà compiler sinh ra.

| Java release | Class-file major |
| --- | ---: |
| Java 8 | 52 |
| Java 11 | 55 |
| Java 15 | **59** |
| Java 17 | **61** |
| Java 21 | **65** |
| Java 24 | 68 |
| Java 25 | 69 |
| Java 26 | 70 |

Kiểm tra trực tiếp bytecode:

~~~bash
javap -verbose -classpath out15 Release15Demo
~~~

Tìm dòng:

~~~text
major version: 59
~~~

Class format major **59** cho biết JVM Java 15 về nguyên tắc có thể **đọc định dạng class đó**. Nó **không chứng minh** Java 15 có đủ class/method mà bytecode tham chiếu, đủ module, đủ dependencies, native libraries hoặc cấu hình để chạy chương trình.

Nếu runtime quá cũ so với major version, một triệu chứng điển hình là `UnsupportedClassVersionError`. Nếu major phù hợp nhưng API thiếu, có thể gặp `NoClassDefFoundError`, `NoSuchMethodError` hoặc lỗi linkage khác. Hai nhóm lỗi có nguyên nhân và hướng sửa khác nhau.

### Vì sao `-target` một mình chưa an toàn?

Trên JDK mới, `-source 15 -target 15` **có thể biên dịch thành công** source sử dụng API Java 17 như `java.util.HexFormat`, trong khi nó vẫn tạo bytecode major 59. Khi đem sang JDK 15, class/method có thể không tồn tại.

Compiler JDK 24 trong ví dụ đã cảnh báo `system modules path` không được đặt tương ứng với `-source 15`, nên **có thể sinh class không chạy trên JDK 15**; đồng thời đề nghị dùng `--release 15`. Không nên bỏ qua cảnh báo này.

## 5. `--release` — source, target và **API nền tảng**

Trong javac JDK hiện đại:

~~~bash
javac --release 15 -encoding UTF-8 -d out15 Release15Demo.java
~~~

tương ứng ba tầng kiểm soát:

1. **Source language rules:** các cú pháp và quy tắc ngôn ngữ được phép trong Java 15.
2. **Target class format:** output major version 59 cho Java 15.
3. **Java SE/JDK platform API signatures:** hạn chế class, constructor và method theo API của Java 15.

Compiler dùng thông tin symbols/API tương ứng release đích, thay vì mặc định cho source truy cập tất cả platform API của build JDK mới. Đây là cơ chế được javac chính thức hỗ trợ để **cross-compile**.

**Giới hạn/điều kiện quan trọng:**

- `--release 15` **không cài JDK 15** và không biến runtime hiện tại thành Java 15.
- JDK compiler **phải hỗ trợ** release yêu cầu. Chạy `javac --help` để xem các release cụ thể được hỗ trợ: JDK hiện tại chỉ giữ **một phạm vi** release cũ, không bảo đảm mọi release từ trước tới nay.
- **JDK 15 không thể biên dịch cho Java 17** bằng `--release 17`; javac cần hỗ trợ target.
- Một số API `jdk.*` công khai/export được hỗ trợ trong release đích vẫn có thể hợp lệ; `--release` không đơn giản là “chỉ cho phép `java.*`”.
- Các **internal/unexported JDK APIs** không thuộc contract ổn định. Với target module-system Java 9+, không dùng `--add-exports` để mở rộng exports của Java SE/JDK/standard modules khi `--release` đang được dùng.
- `--release` **không kiểm tra phiên bản thực tế của tất cả third-party JAR** hoặc phương thức truy cập động dùng reflection/JNI.
- `--release` **không tự xác nhận** kết quả chạy trên JVM version thấp nhất: test runtime là bước riêng.

### Không được kết hợp `--release` với `-source`/`-target`

Sai:

~~~bash
javac --release 15 -source 15 Release15Demo.java
javac --release 15 -target 15 Release15Demo.java
~~~

Trên JDK 24, lệnh thứ nhất trả:

~~~text
error: option --source cannot be used together with --release
~~~

**Chỉ dùng `--release N` cho một cấu hình biên dịch**. Nếu Maven/Gradle/IDE đồng thời truyền source/target, cần sửa cấu hình thay vì bỏ qua lỗi.

## 6. Ma trận lựa chọn cho JDK 24 và Java 15 target

| Câu lệnh | Ngôn ngữ | Bytecode | JDK API compiler nhìn thấy | Kết luận |
| --- | --- | --- | --- | --- |
| `javac App.java` | Theo JDK 24 | Mặc định JDK 24 | JDK 24 | Không cam kết chạy Java 15 |
| `javac -source 15 -target 15 App.java` | Java 15 | major 59 | **Có thể gồm API mới từ JDK 24** | **Không đủ** bảo đảm API compatibility |
| `javac --release 15 App.java` | **Java 15** | **major 59** | **API nền tảng Java 15** | **Ưu tiên nếu cam kết chạy Java 15** |
| `javac --release 17 App.java` | Java 17 | major 61 | API nền tảng Java 17 | Dùng khi min runtime là 17 |

Một source có thể dùng **cú pháp class bình thường** nhưng gọi API chỉ có từ Java 17. Ngược lại, source dùng `record` có thể chỉ gọi API rất cũ nhưng vẫn đòi Java 16+ do **ngôn ngữ/bytecode**. Vì vậy không thể dùng “source viết trông cũ” để suy ra “chạy được Java cũ”.

Lưu ý: nếu chỉ dùng `-source` mà không chỉ định target, có quy tắc default và compatibility riêng theo compiler. Để cross-compile không phụ thuộc default, **dùng `--release`**.

## 7. Chương trình đầy đủ A — API đã có trong Java 15

Tạo file **`Release15Demo.java`** (UTF-8):

~~~java
import java.util.List;

public class Release15Demo {
    public static void main(String[] args) {
        String message = "Java %d; items=%d"
                .formatted(15, List.of("one", "two").size());
        System.out.println(message);
        System.out.println("check=" + message.equals("Java 15; items=2"));
    }
}
~~~

`String.formatted(...)` có trong Java 15; `List.of(...)` xuất hiện trước đó. Không dùng Java 17 API hay preview feature.

Các lệnh đã kiểm chứng **trên JDK 24**:

~~~bash
javac --release 15 -encoding UTF-8 -d out15 Release15Demo.java
java -cp out15 Release15Demo
~~~

Stdout:

~~~text
Java 15; items=2
check=true
~~~

Xem class format:

~~~bash
javap -verbose -classpath out15 Release15Demo
~~~

Dòng kết quả:

~~~text
major version: 59
~~~

Cùng source, biên dịch cho Java 17:

~~~bash
javac --release 17 -encoding UTF-8 -d out17 Release15Demo.java
javap -verbose -classpath out17 Release15Demo
~~~

Class format lúc này:

~~~text
major version: 61
~~~

**Bằng chứng:** source giữ nguyên, compiler mới sinh bytecode khác theo release đích. Cả `--release 15` và `--release 17` đều biên dịch thành công trên JDK 24.

**Giới hạn xác nhận:** các lệnh trên đã chạy bằng JDK 24, **không phải JVM 15**. Nếu artifact hứa hỗ trợ runtime 15, vẫn cần test trực tiếp trên runtime đó theo khả năng/quy trình an toàn của tổ chức. Bài học không khuyến nghị tiếp tục vận hành runtime Java 15 không được hỗ trợ cho hệ thống mới.

## 8. Chương trình đầy đủ B — mã sai API level khi target Java 15

Tạo **`NewerApiProbe.java`**:

~~~java
import java.util.HexFormat;

public class NewerApiProbe {
    public static void main(String[] args) {
        String text = HexFormat.of().formatHex(new byte[]{0x0A, 0x2B});
        System.out.println("hex=" + text);
    }
}
~~~

`java.util.HexFormat` là public API **từ Java 17** (Javadoc ghi `Since: 17`). Đây là API hiện hành hợp lệ, nhưng **không có trong Java 15**.

### 8.1. Biên dịch đúng mục tiêu Java 15 — phải FAIL

~~~bash
javac --release 15 -encoding UTF-8 NewerApiProbe.java
~~~

JDK 24 từ chối biên dịch, thông báo quan trọng (rút gọn bỏ đường dẫn máy):

~~~text
error: cannot find symbol
import java.util.HexFormat;
                ^
symbol:   class HexFormat
location: package java.util
~~~

Đây **không phải lỗi compiler**. Đó là hành vi có lợi: phát hiện code dùng API sau release đích **trước khi deploy**.

### 8.2. Dùng `-source/-target` trên JDK 24 — có thể SUCCESS nhưng nguy hiểm

~~~bash
javac -source 15 -target 15 -encoding UTF-8 -d outWeak NewerApiProbe.java
javap -verbose -classpath outWeak NewerApiProbe
java -cp outWeak NewerApiProbe
~~~

Trên JDK 24 trong lần kiểm chứng:

- Biên dịch **thành công nhưng phát cảnh báo** `system modules path` không được giới hạn theo Java 15.
- `javap` báo **major version 59**.
- Chạy trên **JDK 24** cho:

~~~text
major version: 59
hex=0a2b
~~~

Chương trình vẫn phụ thuộc `HexFormat` của Java 17; **class major 59 không làm API Java 17 xuất hiện trong JVM 15**. Trên Java 15, có nguy cơ lỗi nạp/link class như `NoClassDefFoundError`. Không được quảng cáo rằng chạy thành công trên JDK 24 chứng minh tương thích Java 15.

### 8.3. Nếu min runtime thật là Java 17 — biên dịch thành công

~~~bash
javac --release 17 -encoding UTF-8 -d out17 NewerApiProbe.java
java -cp out17 NewerApiProbe
~~~

Stdout:

~~~text
hex=0a2b
~~~

**Quyết định thiết kế:** nếu thư viện **bắt buộc** hỗ trợ Java 15, thay `HexFormat` bằng giải pháp tương thích với Java 15 hoặc tách implementation cho các version. Nếu nâng minimum runtime lên Java 17, thay đổi là một **điều khoản tương thích công khai**, phải điều chỉnh tài liệu, build, tests và release notes.

## 9. Chương trình đầy đủ C — syntax level khác API level

File **`ModernSyntaxProbe.java`** đã giới thiệu ở mục 3:

~~~java
public record ModernSyntaxProbe(int id, String label) {
    public static void main(String[] args) {
        System.out.println(new ModernSyntaxProbe(1, "ok"));
    }
}
~~~

Chạy:

~~~bash
javac --release 15 ModernSyntaxProbe.java
~~~

bị từ chối vì records chưa final ở Java 15. Chạy:

~~~bash
javac --release 17 ModernSyntaxProbe.java
java ModernSyntaxProbe
~~~

thành công:

~~~text
ModernSyntaxProbe[id=1, label=ok]
~~~

**So sánh B và C:**

- Ví dụ B dùng cú pháp class rất thông thường nhưng **sai API release**.
- Ví dụ C không cần API JDK mới phức tạp, nhưng **sai language level**.
- `--release` chặn đúng **cả hai** loại không tương thích.

## 10. Build JDK, compiler toolchain và runtime đích là ba lựa chọn khác nhau

~~~text
Máy dev / CI:
  Maven / Gradle / IDE
          │
          ▼
   Chọn JDK cho javac (ví dụ JDK 21/24)
          │
          ▼
   javac --release 15
      ├─ syntax Java 15
      ├─ class major 59
      └─ API nền tảng Java 15
          │
          ▼
     app.jar / lib.jar
          │
          ▼
  Test trên runtime thấp nhất đã cam kết
~~~

`--release` **không chọn, tải hay thay đổi phiên bản JDK được dùng để chạy compiler**. Java toolchain là cơ chế chọn JDK tương ứng cho compile/test/javadoc theo build tool; `--release` áp dụng giới hạn lên kết quả biên dịch.

**Điểm cần xác minh trong thực tế:**

~~~bash
javac -version
java -version
javac --help
~~~

`javac --help` cho biết release đích mà javac hiện tại hỗ trợ. Cùng một dự án có thể được build bằng JDK 21 trên CI và JDK 24 ở máy cá nhân; nếu không cấu hình toolchain, kết quả và cảnh báo có thể khác.

Cần ghi lại cả phiên bản **Maven/Gradle, plugin compiler và JDK thực chạy compile**. Không suy đoán tất cả từ biến `JAVA_HOME` khi Gradle daemon/IDE có toolchain khác.

## 11. Maven: đặt `maven.compiler.release`

Với **Maven 3 và phiên bản Maven Compiler Plugin hỗ trợ `release`**, cấu hình điển hình trong `pom.xml`:

~~~xml
<project>
  <!-- Đây là đoạn minh họa; các phần khai báo Maven khác được lược bỏ. -->
  <properties>
    <maven.compiler.release>15</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>
</project>
~~~

Thuộc tính `maven.compiler.release` yêu cầu compiler sử dụng release target (syntax, class file, platform API) thay vì chỉ hạ class-file format.

**Không đặt đồng thời** những property dùng để cấu hình riêng `source`/`target` theo cách khiến plugin truyền cả ba option cho javac:

~~~xml
<!-- Chỉ minh họa điều nên tránh khi đã dùng release. -->
<maven.compiler.source>15</maven.compiler.source>
<maven.compiler.target>15</maven.compiler.target>
~~~

Maven Compiler Plugin và JDK phải hỗ trợ target. Với dự án mới, thay `15` bằng mức runtime thấp nhất **đang được hỗ trợ** (ví dụ bản được tổ chức chọn) chứ không lấy Java 15 làm khuyến nghị.

**Maven Toolchains** có thể chỉ định JDK compiler khác với JDK chạy Maven. Cần kiểm tra thực tế khi build với `mvn -version` và thông tin compiler/toolchain plugin, thay vì dựa vào IDE.

Nếu Maven project có nhiều modules/executions, hãy kiểm tra mọi execution của source chính dùng đúng target; một module vô tình build với compiler mặc định có thể nâng minimum runtime của toàn artifact.

## 12. Gradle: kết hợp toolchain với `options.release`

Ví dụ **Gradle Kotlin DSL `build.gradle.kts`**:

~~~kotlin
plugins {
    java
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(21))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(15)
}
~~~

Giải thích:

- `languageVersion.set(JavaLanguageVersion.of(21))` chọn **compiler toolchain JDK 21**, nếu có sẵn hoặc resolver được cấu hình.
- `options.release.set(15)` khiến `JavaCompile` kiểm tra Java 15 syntax, class-file version và platform API.
- **Toolchain 21 không làm test tự chạy trên JVM 15.** Test JVM và matrix runtime cần cấu hình riêng khi cam kết tương thích.
- Đây là cấu hình minh họa; khả năng cài đặt/toolchain resolver phụ thuộc bản Gradle đang chạy.

**Không nhầm với:**

~~~kotlin
java {
    sourceCompatibility = JavaVersion.VERSION_15
    targetCompatibility = JavaVersion.VERSION_15
}
~~~

Các thuộc tính này tương ứng `-source`/`-target` và không có cùng bảo đảm giới hạn platform API như `--release`. Tài liệu Gradle hiện hành cũng phân biệt rõ toolchain và release flag, khuyến nghị kết hợp khi cần **strict cross-compilation**.

Với dự án hỗn hợp Java/Kotlin, `options.release` áp dụng cho **JavaCompile**; cấu hình Kotlin `jvmTarget` là vấn đề riêng cần đồng bộ và kiểm chứng.

## 13. Các ranh giới mà `--release` không tự kiểm tra

### 13.1. Third-party libraries

`--release 15` giới hạn Java platform API được javac cho phép khi biên dịch code của bạn, **không tự hạ toàn bộ dependency bên ngoài**. Một JAR third-party có thể:

- Được compile với major 61 (Java 17) nên JVM 15 không nạp được.
- Chứa bytecode major 59 nhưng gọi một class Java 17 qua code nội bộ.
- Dùng reflection/JNI hoặc plugins chỉ có ở runtime mới.

**Cần kiểm tra dependency compatibility**, BOM/transitive dependencies và chạy integration tests trên minimum runtime thực tế.

### 13.2. Reflection, dynamic loading và modules

Những lời gọi như `Class.forName("...")`, `ServiceLoader`, reflective access, JNI hoặc các plugin khám phá class động không nhất thiết được compiler phân tích đầy đủ qua `--release`.

Module availability, exports/opens, `jlink` runtime image và danh sách packages của OS/JDK đích vẫn phải được kiểm tra. **Không nên lách API compatibility bằng `sun.*`, `jdk.internal.*` hoặc `--add-exports` cho internal platform classes.**

Với `--release` nhắm Java 9+ (bao gồm Java 15), compiler còn có hạn chế **`--add-exports` không được mở rộng exports của các platform modules** thuộc release đích. Đây là cơ chế bảo vệ sự tương thích, không phải phiền toái cần né.

### 13.3. Hành vi runtime và môi trường

Ngay cả khi class loads thành công:

- GC/JIT khác nhau theo runtime.
- Charset, locale, timezone, file system và network provider có thể khác.
- Native libraries và OS ABI có thể không có.
- Quyền truy cập, module config, TLS/certificates hoặc file paths có thể khác.
- Đường xử lý không được test có thể mới chạm đến class/method thiếu.

`--release` không phải **bản chứng nhận chức năng/performance**. Cần test trên runtime và hạ tầng thật, kể cả failure paths.

## 14. CI/CD: kiểm tra compatibility tới khi chạy được artifact cuối

Một pipeline đáng tin:

~~~text
1. Công bố minimum supported runtime.
2. Chọn compiler JDK/toolchain nhất quán (có hỗ trợ release đích).
3. Biên dịch source chính với javac --release N.
4. Chạy unit tests, kiểm tra generated sources/annotation processors.
5. Kiểm tra class major và dependencies của artifact cuối.
6. Chạy smoke/integration tests trên runtime thấp nhất đã công bố.
7. Test thêm các runtime mới hơn trong compatibility matrix.
8. Đóng gói và chạy JAR/container/jlink image cuối cùng.
9. Kiểm tra reflection, module-path, plugins, native libraries.
10. Công bố build JDK/release/tests và chỉ phát hành khi đạt.
~~~

**Tách bạch tests với main artifact:** một dự án có thể biên dịch source chính `--release 15` nhưng test sources hoặc test framework chạy trên JDK 21. Điều này có thể hợp lý cho build, nhưng **chưa chứng minh main artifact chạy Java 15**. Chỉ test thật trên min runtime mới xác nhận các đường chạy đó.

### Java 15 và phiên bản được hỗ trợ

Java 15 **không phải một runtime còn được hỗ trợ để bắt đầu phát triển sản phẩm mới**. Bài dùng release 15 để mô tả cơ chế lịch sử đã dẫn tới `--release` và phần tương thích hiện vẫn quan trọng. Nếu dự án nâng minimum Java lên bản hiện hành được hỗ trợ, hãy cập nhật release target, toolchains, dependency versions và CI matrix có kiểm soát.

### Multi-release JAR là trường hợp chuyên biệt

Một **multi-release JAR** có thể cung cấp các class variants cho nhiều runtime Java. Khi cần, mỗi variant phải được compile đúng release và test trong runtime matrix. Không dùng multi-release JAR chỉ để che một dependency không tương thích: cấu hình và lựa chọn class theo runtime có thêm độ phức tạp.

## 15. Các lỗi thường gặp khi build và chạy

| Lỗi/triệu chứng | Ý nghĩa chính | Cách điều tra |
| --- | --- | --- |
| `cannot find symbol HexFormat` với `--release 15` | API chỉ có ở Java 17+ | Dùng API tương thích hoặc nâng min runtime có kiểm soát |
| `records are not supported in -source 15` | Syntax final sau Java 15 | Đổi cú pháp hoặc release target |
| `--source cannot be used together with --release` | Cờ compiler xung đột | Chỉ chọn một `--release` |
| `release version N not supported` | Compiler không hỗ trợ release N | Xem `javac --help` và build toolchain |
| `invalid target release` | Compiler JDK quá cũ hoặc target sai | Kiểm tra `javac -version`/Maven/Gradle |
| `UnsupportedClassVersionError` | JVM không hiểu class-file major | Hạ release output hoặc dùng runtime mới hơn |
| `NoClassDefFoundError` | Class/API/dependency thiếu khi chạy | Kiểm tra runtime, classpath, modulepath |
| `NoSuchMethodError` | Signature khác giữa compile/runtime | Kiểm tra phiên bản platform/dependencies |
| `ClassNotFoundException` | Dynamic loading không tìm thấy class | Kiểm tra packaging và module/classpath |
| `InaccessibleObjectException` | Reflection bị module encapsulation hạn chế | Dùng public API, cấu hình module đúng contract |
| CI fail nhưng IDE pass | JDK/toolchain/plugin version khác | Chốt và kiểm tra versions thực chạy |
| Major 59 nhưng Java 15 lỗi | Bytecode phù hợp, API/dependency lại không | Dùng `--release` và min-runtime tests |

**Không so sánh cố định nguyên văn error message giữa mọi OS/JDK**, vì compiler diagnostics có thể khác; nên nhận diện loại lỗi và quyết định cấu hình.

## 16. Công cụ chẩn đoán và các điều nên kiểm tra

~~~bash
javac -version
java -version
javac --help
javap -verbose -classpath out15 Release15Demo
~~~

- `javac -version`: kiểm tra compiler thực.
- `java -version`: kiểm tra Java runtime đang chạy lệnh.
- `javac --help`: liệt kê các release được compiler hiện tại hỗ trợ.
- `javap -verbose`: kiểm tra class-file major version.

Dùng `jdeps` để tìm một số internal JDK references khi có JAR:

~~~bash
jdeps --jdk-internals application.jar
~~~

Đây là lệnh **minh họa**, cần file `application.jar` có thật. `jdeps` không phát hiện mọi dynamic/reflection access và **không chứng nhận hoàn toàn runtime compatibility**.

### Checklist trước khi phát hành

- [ ] Đã định nghĩa minimum runtime **được hỗ trợ** cho từng artifact/module.
- [ ] `--release N` khớp minimum runtime, không thêm `-source/-target` xung đột.
- [ ] Build JDK/toolchains đồng nhất giữa local, IDE và CI.
- [ ] Compiler hỗ trợ release N; `javac --help` được kiểm tra.
- [ ] Mã không vô tình dùng Java platform APIs mới hơn release đích.
- [ ] Đã kiểm tra class major, dependency tree và min runtime của dependencies.
- [ ] Đã chạy smoke/integration tests trên JVM thấp nhất công bố.
- [ ] Reflection, modules, native libraries và packaging được kiểm tra.
- [ ] Không phụ thuộc preview feature cũ hoặc JDK internal API ngoài contract.
- [ ] Ghi build/runtime versions và xử lý compiler warnings có ý nghĩa.

## 17. Câu hỏi tự kiểm tra

**Câu 1.** `-source 15` có chặn gọi `java.util.HexFormat` trên JDK 24 không?  
**Không.** Nó kiểm tra cú pháp, không tự chặn Java platform API mới.

**Câu 2.** `-target 15` có đủ bảo đảm chạy trên Java 15?  
**Không.** Nó chỉ điều khiển class-file format.

**Câu 3.** `--release 15` kiểm tra những gì?  
**Source syntax Java 15, class-file major 59 và Java 15 supported platform API.**

**Câu 4.** Class-file major 59 nhưng vẫn lỗi `NoClassDefFoundError` có thể do đâu?  
Do class/method hoặc dependency thiếu ở JVM runtime, dù class-file format được hỗ trợ.

**Câu 5.** Được đặt `--release 15 -source 15` cùng lúc không?  
**Không.** javac từ chối cặp option đó.

**Câu 6.** Toolchain JDK 21 và `options.release.set(15)` có tự chạy tests trên JDK 15?  
**Không.** Toolchain chọn JDK build; test JVM cần thiết kế riêng.

**Câu 7.** Muốn dùng `HexFormat` nhưng phải hỗ trợ Java 15 thì làm gì?  
Dùng phương án encode hex tương thích Java 15, tách implementation theo runtime, hoặc nâng **minimum runtime contract** một cách công khai.

**Câu 8.** Vì sao record trong Java 15 và record trong Java 17 khác nhau ở `--release`?  
Vì record ở Java 15 chỉ preview, còn từ Java 16 là tính năng final.

**Câu 9.** Vì sao vẫn phải test trên minimum runtime sau khi `--release` đã build PASS?  
Vì runtime behavior, dependencies, reflection, JNI, module configuration và packaging không được compiler bảo đảm toàn diện.

**Câu 10.** Nên chọn `--release` theo compiler JDK hay theo runtime khách hàng?  
Theo **minimum runtime thực sự cam kết hỗ trợ**, với compiler JDK có khả năng target release đó.

## 18. Tài liệu chính thức còn áp dụng

- Oracle Java SE 26 — **The javac Command**: `--source`, `--target`, `--release`, API restrictions và cross-compilation. https://docs.oracle.com/en/java/javase/26/docs/specs/man/javac.html
- Oracle Java SE 25 — **The javac Command**: options và quy tắc kết hợp cờ. https://docs.oracle.com/en/java/javase/25/docs/specs/man/javac.html
- Java Virtual Machine Specification — **Java SE 27 class-file major version table**: Java 15=59, 17=61, 21=65, 24=68. https://docs.oracle.com/javase/specs/jvms/se27/html/jvms-1.html
- Oracle Java SE 17 — **`java.util.HexFormat`**, documented `Since: 17`. https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HexFormat.html
- Oracle Java SE 15 — **`String.formatted`**. https://docs.oracle.com/en/java/javase/15/docs/api/java.base/java/lang/String.html
- Apache Maven — **Guide to Targeting a Java Version**: compiler release property. https://maven.apache.org/guides/mini/guide-java-target.html
- Maven Compiler Plugin — **Setting the --release of the Java Compiler**. https://maven.apache.org/plugins/maven-compiler-plugin-4.x/examples/set-compiler-release.html
- Gradle — **Toolchains for JVM Projects**: compiler toolchain và strict `--release`. https://docs.gradle.org/current/userguide/toolchains.html
- Gradle — **Building Java & JVM Projects**: target compatibility và API restrictions. https://docs.gradle.org/current/userguide/building_java_projects.html
- Oracle Java SE 25 — **Language updates and preview features**: feature preview cần compiler/runtime phù hợp. https://docs.oracle.com/en/java/javase/25/language/java-se-language-updates.pdf