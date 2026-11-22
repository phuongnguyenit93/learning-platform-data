# Java 10 – Mô hình phiên bản: Xác định yêu cầu JDK của thư viện và công cụ xây dựng

> **Ngữ cảnh:** Java 10 → **Mô hình phiên bản** → **Xác định yêu cầu JDK của thư viện và công cụ xây dựng**. Bài học hướng dẫn cách xác định một dự án cần **JDK nào để chạy Maven/Gradle**, **JDK nào để biên dịch và test**, và **phiên bản Java tối thiểu mà sản phẩm/thư viện có thể chạy**. Java 10 là mốc minh họa cụ thể: class-file major version **54**, `var` cục bộ và `List.copyOf` từ Java 10. Các phương pháp `javac --release`, Java toolchains, bytecode inspection, dependency validation và CI matrix vẫn đang được sử dụng trên Java 17+ và các JDK hiện đại. **Không khuyến nghị bắt đầu dự án mới trên một JDK không còn được nhà cung cấp hỗ trợ; lựa chọn bản JDK hiện hành có hỗ trợ và phù hợp yêu cầu triển khai.**

## 1. Mục tiêu và câu trả lời cốt lõi

Sau bài này, bạn có thể:

1. Nêu sự khác nhau giữa **JDK chạy build tool**, **JDK mà compiler/toolchain sử dụng**, **Java language/API target**, **JDK chạy test** và **JDK chạy sản phẩm**.
2. Xác định yêu cầu JDK từ tài liệu chính thức, version của framework, build tool wrapper, plugin, thư viện trực tiếp và **dependency bắc cầu**.
3. Kiểm tra class-file version bằng `javap -verbose`; hiểu Java 10 ứng với **major 54**, Java 17 với **major 61**, và vì sao đó mới là điều kiện cần.
4. Dùng `javac --release 10` để kiểm tra **cú pháp Java 10 + API nền tảng Java 10 + bytecode đích 10**, thay vì chỉ chỉnh `source`/`target`.
5. Biết vì sao một library xây bằng JDK 17 **vẫn có thể** phát hành class chạy trên JDK 10 nếu nó được cross-compile đúng, nhưng không thể suy ra điều đó từ `Build-Jdk` trong manifest.
6. Đọc cấu hình `maven.compiler.release`, Gradle `java.toolchain` và `options.release`; phân biệt JDK chạy Maven/Gradle với compiler được chọn.
7. Hiểu Maven/Gradle plugins và annotation processors có thể đòi một JDK **cao hơn** target runtime của artifact.
8. Xử lý multi-release JAR (`META-INF/versions/N`), module metadata và những điểm mà một lần đọc classfile không xác minh hết.
9. Xác minh run trên JVM thấp nhất được sản phẩm hỗ trợ và kiểm tra lỗi `UnsupportedClassVersionError`, `NoSuchMethodError`, `ClassNotFoundException`/`NoClassDefFoundError`, `InaccessibleObjectException` theo đúng nguyên nhân.
10. Tổ chức build tái lập được với Maven Wrapper/Gradle Wrapper, toolchains, dependency versions, CI matrix và thử nghiệm trên runtime thực tế.
11. Biết kiểm tra yêu cầu JDK khi nâng version thư viện, plugin, framework, Gradle/Maven hoặc JDK.
12. Biên dịch, chạy demo Java 10 bằng compiler hiện đại để thấy class major 54 và cơ chế `--release` kiểm soát Java API.

**Nguyên tắc đầu tiên:** **Không có một “Java version” duy nhất cho mọi phần của dự án.** Một dự án có thể **chạy Gradle trên JDK 17**, dùng **compiler toolchain JDK 17**, biên dịch code bằng **`--release 10`**, rồi **chạy integration test trên JDK 17**. Tuy nhiên điều này **không chứng minh** thư viện và toàn bộ dependency chạy được trên Java 10; để cam kết Java 10 runtime phải kiểm tra các dependency và **thử trực tiếp trên JVM Java 10** hoặc một môi trường kiểm chứng tương thích thích hợp.

## 2. Năm “phiên bản Java” cần tách bạch

| Lớp quyết định | Câu hỏi cần trả lời | Nơi xác định |
| --- | --- | --- |
| **Build tool runtime JDK** | Maven/Gradle daemon đang chạy **bằng JVM nào**, phiên bản tool/plugin yêu cầu JVM tối thiểu nào? | `mvn -version`, `./gradlew --version`, compatibility matrix |
| **Build/compiler toolchain JDK** | Task `JavaCompile` hoặc `maven-compiler-plugin` thực sự chạy compiler từ JDK nào? | Gradle `java.toolchain`, `javaToolchains`, Maven Toolchains |
| **Language/API/bytecode target** | Code được phép dùng cú pháp/API Java phiên bản nào và tạo classfile version nào? | `javac --release N`, `options.release`, `maven.compiler.release` |
| **Test JVM** | Unit/integration tests chạy trên JVM nào? | Gradle Test launcher, Maven Surefire/Failsafe toolchain/fork settings, CI jobs |
| **Production runtime JDK** | Server/container/function thật dùng JVM nào? Nó có chạy được mọi class và dependency không? | Docker image, deployment manifest, `java -version` trên runtime, startup/functional tests |

Một mục tiêu triển khai chính xác nên có **bộ ràng buộc**, không phải một con số:

~~~text
Build tool: Gradle bản X (đối chiếu compatibility matrix của X)
Build JVM: JDK 17 (ví dụ)
Compiler JDK: JDK 17 thông qua toolchain
Source/API target: --release 10 (chỉ là mục tiêu minh họa)
Test JVMs: 10 và 17 nếu thực sự cam kết hỗ trợ Java 10
Deploy JVM: một phiên bản đang được nhà cung cấp hỗ trợ
Library A: minimum runtime JDK do release cụ thể công bố
Library B / plugin C: requirement riêng, có thể khác Library A
~~~

**Không nhầm các khái niệm:**

- **“Built with JDK 17”** không đồng nghĩa **“requires Java 17 to run”**.
- **“Bytecode 54”** không đồng nghĩa toàn bộ chương trình đã chứng minh an toàn trên Java 10.
- **“Source compatibility 10”** không đồng nghĩa platform API thực sự giới hạn ở Java 10.
- **“IDE Project SDK 17”** không bảo đảm Gradle daemon/test/toolchain cũng dùng 17.
- **“JDK 10 library”** không có nghĩa các bản phát hành mới nhất của chính library vẫn còn hỗ trợ JDK 10.

## 3. Bắt đầu từ yêu cầu sản phẩm, rồi truy ngược

Trước khi sửa `pom.xml` hoặc `build.gradle.kts`, xác định:

1. **Runtime thấp nhất mà sản phẩm buộc hỗ trợ là bao nhiêu?** Đây là yêu cầu của khách hàng/hạ tầng hoặc hợp đồng thư viện. Nếu không có yêu cầu backward compatibility, chọn một JDK được hỗ trợ hiện nay và version được framework khuyến nghị, thay vì giữ Java 10 như target mặc định chỉ vì đang học Java 10.
2. **Framework/app server/servlet container yêu cầu phiên bản nào?** Ví dụ các major version của một framework có thể nâng baseline JDK. Kiểm tra release notes và bảng hỗ trợ **đúng major/minor version sử dụng**.
3. **Các dependency trực tiếp và bắc cầu có baseline nào?** Một dependency đã nâng tối thiểu Java 17 có thể khiến toàn bộ ứng dụng không thể chạy Java 10.
4. **Build tool và plugins có đủ mới để chạy với JDK build đã chọn?** Gradle có bảng tương thích **theo từng Gradle version**; Maven core, compiler plugin, test plugin và static analyzers có yêu cầu khác nhau.
5. **Compiler có hỗ trợ target `--release N` không?** Một JDK hiện đại chỉ hỗ trợ một số release cũ giới hạn; kiểm tra `javac --help` thực tế.
6. **Tests, plugins và tooling có hỗ trợ toolchain/run JVM khác nhau không?** Một số plugin hoặc code generation task dùng JVM của build tool.
7. **Sản phẩm phân phối dạng gì?** Executable JAR, library JAR, module/JMOD, image tạo bởi `jlink`, Android, native image hoặc Docker có ràng buộc khác nhau.

### 3.1. Ma trận thông tin cần ghi lại cho một quyết định

| Nguồn | Điều cần trích xuất | Ràng buộc suy ra |
| --- | --- | --- |
| README/docs của thư viện đúng bản | Minimum Java/JDK, supported releases | Runtime baseline được **nhà phát hành cam kết** |
| Release notes/migration guide | Yêu cầu tăng JDK khi nâng version | Rủi ro của dependency update |
| `pom.xml`/POM được publish | Dependency versions, plugin/config có liên quan | Bằng chứng hỗ trợ điều tra, chưa đủ để cam kết runtime |
| Gradle module metadata | Variant/capability hoặc Java compatibility attribute khi có | Giúp Gradle chọn variant phù hợp; cần kiểm chứng |
| Class files trong JAR | Major/minor, preview marker, class entries | Giới hạn bytecode ít nhất của các class được tải |
| `META-INF/versions/N` | Class variant cho JDK ≥N | Có thể chạy baseline thấp hơn **một số variant mới** |
| Test suite trên runtime thấp nhất | Linkage, API, ServiceLoader, code path thực tế | Bằng chứng vận hành đáng tin |
| CI/build log | Toolchain thực tế, lệnh compiler, test JVM | Chứng minh build không bị “vô tình” chạy bằng JDK khác |

**Thứ tự ưu tiên:** tài liệu chính thức và compatibility matrix của **phiên bản đang dùng** → cấu hình build/metadata → kiểm tra classfile/JAR → chạy thử với runtime thật. Không dừng ở một suy đoán từ classfile hoặc README chung.

## 4. Kiểm tra môi trường thực tế trước khi đoán

Trong terminal dự án:

~~~bash
java -version
javac -version
echo "$JAVA_HOME"
./mvnw -version
./gradlew --version
~~~

Đây là các **lệnh minh họa**: chỉ chạy wrapper nào dự án có (`mvnw` cho Maven, `gradlew` cho Gradle). Không cần và thường không có cả hai. Trên Windows PowerShell:

~~~powershell
java -version
javac -version
$env:JAVA_HOME
.\mvnw.cmd -version
.\gradlew.bat --version
~~~

Các bản in cần so sánh:

- `java -version`: launcher đầu tiên trên `PATH`, có thể khác compiler hoặc daemon.
- `javac -version`: compiler mà terminal tìm thấy; nếu project dùng toolchains, compiler của task **có thể khác**.
- `JAVA_HOME`: default mà nhiều công cụ tham khảo, nhưng **không đủ chứng minh** Maven/Gradle/test/IDE sẽ dùng JDK đó.
- `mvnw -version`/`mvn -version`: Maven version và Java runtime Maven đang chạy.
- `gradlew --version`: Gradle version, JVM/daemon/runtime thông tin liên quan. Cần xem log/task configuration để biết compiler toolchain.
- `gradlew -q javaToolchains`: liệt kê những Java toolchains Gradle phát hiện, nếu plugin/task phù hợp.
- Image/container có thể dùng JDK khác với máy phát triển; kiểm tra **bên trong runtime container** hoặc CI chứ không chỉ laptop.

### 4.1. Wrapper là một phần của tính tái lập

- **Gradle Wrapper** (`gradlew`, `gradle-wrapper.properties`) xác định Gradle distribution mà project dùng. Chạy lệnh bằng wrapper thay vì tin bản `gradle` global không kiểm soát.
- **Maven Wrapper** (`mvnw`, `maven-wrapper.properties`) đóng vai trò tương tự đối với Maven version.
- Wrapper **không tự cố định compiler JDK**, Java runtime của wrapper và tất cả dependencies/plugins; toolchains, CI image và dependency version vẫn cần cấu hình.
- Trên CI, cố định/discover JDK theo chính sách dự án, log runtime/versions và phát hiện khác biệt sớm.

**Thực tiễn:** Một dự án build thành công trong IDE nhưng thất bại trên CI thường là do Gradle JVM/Maven JVM, compiler toolchain hoặc plugin khác phiên bản — không phải Java “biên dịch ngẫu nhiên”.

## 5. Class-file major version: bước chẩn đoán nhanh

Mỗi `.class` chứa header nhị phân với magic `0xCAFEBABE`, **minor version** và **major version**. JVM kiểm tra class format version trước khi load. Class được biên dịch cho release mới hơn runtime có thể tạo `UnsupportedClassVersionError`.

| Java SE release | Class-file major (thông dụng) |
| --- | ---: |
| 8 | 52 |
| 9 | 53 |
| **10** | **54** |
| 11 | 55 |
| 17 | 61 |
| 21 | 65 |
| 25 | 69 |
| 26 | 70 |

Với các Java release **từ Java 5 trở lên**, quy tắc major cơ bản là:

~~~text
class-file major = 44 + Java feature version
Java 10 → 44 + 10 = 54
Java 17 → 44 + 17 = 61
~~~

Đây là quy tắc thuận tiện để nhận diện classfile **thông thường**, không phải công thức bảo đảm chạy được mọi class/feature trên mọi runtime. Classfile từ **preview features** của các Java release áp dụng có thể dùng minor `65535`; khi đó có thêm ràng buộc với release **đúng phiên bản** và `--enable-preview`. Đừng chỉ lấy major rồi kết luận preview bytecode hoạt động trên mọi JVM mới hơn.

### 5.1. Kiểm tra `.class` đã biên dịch

~~~bash
javap -verbose -classpath target/classes com.example.App
~~~

Trong output:

~~~text
minor version: 0
major version: 54
~~~

Trên Windows có thể lọc:

~~~powershell
javap -verbose -classpath target/classes com.example.App |
  Select-String "major version"
~~~

Trên POSIX:

~~~bash
javap -verbose -classpath target/classes com.example.App |
  grep "major version"
~~~

Nếu `major version: 54`, class đã được phát hành theo format Java 10. Nhưng hãy nhớ:

- Nó vẫn có thể gọi code của dependency Java 17 mà không hiện trong **chính class** đó.
- Nó có thể dùng Java API không có ở Java 10 nếu biên dịch sai cách chỉ với `-target`.
- Nó có thể dùng reflection, JNI, native library hay resource không phù hợp runtime.
- Một số class của library có thể có **major cao hơn** class bạn đã kiểm tra.
- Multi-release JAR có cơ chế chọn class variant theo runtime.
- Tool classfile cũ quá có thể không parse class format mới dù JVM có thể chạy; cập nhật công cụ kiểm tra khi cần.

### 5.2. Kiểm tra một class bên trong library JAR

~~~bash
jar --list --file my-library.jar
javap -verbose -classpath my-library.jar com.example.lib.PublicApi
~~~

`com.example.lib.PublicApi` phải thay bằng **tên class thật được biết trước** trong JAR. Các lệnh không có tác dụng tự tìm tất cả class Java requirements. Để kiểm toàn bộ library cần quét các `.class` liên quan, phụ thuộc trực tiếp/bắc cầu và các class runtime có thể được nạp.

**Bẫy:** Nếu thư viện chứa nhiều class, `javap` trên đúng một class có major 54 chỉ chứng minh thông tin của **class đó**. Không đủ để tuyên bố tất cả classes trong JAR và toàn bộ dependency graph chạy trên JDK 10.

## 6. `UnsupportedClassVersionError`: chẩn đoán đúng

Một thông báo thường có dạng:

~~~text
java.lang.UnsupportedClassVersionError:
  ... has been compiled by a more recent version of the Java Runtime
  (class file version 61.0), this version of the Java Runtime only
  recognizes class file versions up to 54.0
~~~

Đây là **ví dụ cấu trúc lỗi**, không phải stdout của demo cuối bài.

Giải thích:

- `61.0` nghĩa class được phát hành theo **Java 17 class-file format**.
- JVM chỉ nhận đến `54.0` tương ứng **Java 10**.
- Lỗi là về **khả năng đọc format class**, không trực tiếp nói mọi dòng nguồn dùng tính năng Java 17.
- Giải pháp đúng là dùng runtime được sản phẩm/library hỗ trợ, hoặc chọn phiên bản dependency tương thích rồi rebuild/release đúng target nếu có quyền và yêu cầu.

### 6.1. Không áp dụng “sửa số byte major” như một bản vá

Classfile hiện đại có thể chứa các cấu trúc/semantic/API mà JVM cũ không hiểu. Không mở class binary và đổi `major 61` thành `54` để “hạ JDK”, cũng không chỉ chỉnh metadata của JAR rồi coi là tương thích. Cần **biên dịch bằng toolchain và target thích hợp** rồi kiểm tra API, dependencies và runtime.

### 6.2. Khi major hợp lệ nhưng vẫn lỗi

| Lỗi | Nguyên nhân thường gặp | Hướng điều tra |
| --- | --- | --- |
| `UnsupportedClassVersionError` | Classfile mới hơn JVM hoặc class preview không hợp lệ | Xem major/minor, JVM chạy thật, target compile |
| `NoSuchMethodError` | Runtime có class nhưng thiếu method/signature cần; lệch API hoặc dependency version | Kiểm dependency graph, method tồn tại trên runtime? |
| `NoClassDefFoundError` | Class không tải/khởi tạo được, dependency thiếu hoặc lỗi khởi tạo | Đọc cause, classpath/module path, runtime logs |
| `ClassNotFoundException` | Dynamic lookup không tìm class | Kiểm classpath/module path, service loader, shading |
| `IllegalAccessError` | Vi phạm quyền truy cập ở liên kết runtime | Kiểm API/module exports và binary compatibility |
| `InaccessibleObjectException` | Reflection bị encapsulation/modules chặn | Dùng public API được hỗ trợ, cập nhật thư viện |
| `UnsupportedOperationException` | API/tính năng không hỗ trợ trong điều kiện hiện tại | Kiểm behavior/runtime contract, không coi luôn là lỗi JDK |
| Compiler `cannot find symbol` trên API mới | `--release N` không có API trong release N | Tăng target khi được phép hoặc thay API tương thích |

Không quy tất cả lỗi khởi động thành “cài sai Java”. Đọc **class name, stack trace, dependency provenance**, kiểm JDK thực thi và API cụ thể.

## 7. `javac --release`: kiểm soát Java language + API + bytecode

Trên compiler JDK 9+ có hỗ trợ release đích, cú pháp:

~~~bash
javac --release 10 -encoding UTF-8 Example.java
~~~

`--release 10` yêu cầu compiler:

1. Áp dụng quy tắc ngôn ngữ cho **Java 10**.
2. Tạo classfile target **Java 10** (major 54).
3. Chỉ cho code dùng các **API nền tảng được cung cấp công khai cho Java 10** theo bộ API release target trong compiler.

Đây là điểm vượt trội so với `-source 10 -target 10`: `-source` chủ yếu giới hạn cú pháp, `-target` giới hạn classfile, nhưng **không tự bảo đảm** code không tham chiếu API của JDK mới hơn đang chạy compiler.

### 7.1. Ví dụ API Java 11 không có trong Java 10

~~~java
public class NeedsJava11 {
    public static void main(String[] args) {
        System.out.println("a".repeat(2));
    }
}
~~~

`String.repeat(int)` được bổ sung từ **Java 11**. Nếu compiler đang dùng là JDK 17, chạy:

~~~bash
javac --release 10 NeedsJava11.java
~~~

sẽ **thất bại** vì `String.repeat` không thuộc API Java 10. Đây là **kiểm thử được kỳ vọng thất bại**, không phải lỗi phải sửa bằng cách bỏ `--release`. Trên hệ thống thử, compiler báo `cannot find symbol` đối với `repeat`.

~~~bash
javac --release 17 NeedsJava11.java
java NeedsJava11
~~~

với JDK 17+ cho output:

~~~text
aa
~~~

**Bài học:** Biên dịch một source Java 10 bằng **JDK 17** chưa đủ. Nếu không dùng `--release 10`, code có thể vô tình gọi API Java 11+ trong khi lại yêu cầu hỗ trợ Java 10.

### 7.2. Giới hạn thực tế của `--release`

- Chỉ các giá trị `--release` mà **compiler hiện có hỗ trợ** mới dùng được. Kiểm `javac --help`, không giả định JDK tương lai vẫn cho build mọi phiên bản cũ.
- `--release` không thể được kết hợp đồng thời với `-source`/`-target` trong cùng lệnh.
- Nó bảo vệ **API JDK/nền tảng được biên dịch theo release target**; không tự kiểm soát tất cả **thư viện ngoài JDK**, reflection, JNI, native image, OS packages, configuration hoặc annotation processor behavior.
- Nó không tự chuyển một library Java 17 đã compile thành library Java 10 tương thích. Mọi dependency cần được kiểm tra riêng.
- Nếu phiên bản Java target quá cũ để compiler hiện tại hỗ trợ, dùng một toolchain/compiler được hỗ trợ phù hợp hoặc nâng target theo quyết định sản phẩm; không bỏ giới hạn API bằng `-target` chỉ để build “trông thành công”.

### 7.3. So sánh các công tắc compile

| Công cụ | Chọn compiler JDK? | Giới hạn language? | Giới hạn classfile? | Giới hạn JDK API target? |
| --- | --- | --- | --- | --- |
| `javac --release 10` | Không | Có | Có | **Có** |
| `javac -source 10 -target 10` | Không | Có | Có | **Không đầy đủ** |
| Gradle `java.toolchain = 17` | **Có** | Thường mặc định theo toolchain | Thường mặc định theo toolchain | **Không tự đặt 10** |
| Gradle `options.release = 10` | Không | Có | Có | **Có** |
| Maven `maven.compiler.release=10` | Không | Có | Có | **Có** với compiler/plugin hỗ trợ |
| Maven/Gradle/JAVA_HOME chạy JDK 17 | Chọn/default JVM điều khiển build | Không trực tiếp | Không trực tiếp | Không trực tiếp |

**Thiết kế chuẩn:** Chọn JDK compiler bằng toolchain và chọn target bằng `--release`. Hai quyết định bổ sung cho nhau, không thay thế nhau.

## 8. Ví dụ Java 10 vẫn biên dịch trên JDK hiện đại

Java 10 có `var` cho biến cục bộ và `List.copyOf` để tạo list unmodifiable từ collection hiện có:

~~~java
var fields = java.util.List.copyOf(
        java.util.Arrays.asList("var", "copyOf"));

System.out.println(fields); // [var, copyOf]
~~~

Đoạn này dùng Java 10 API đúng phạm vi. Khi compile với `--release 10` trên compiler tương thích, output classfile là **major 54**.

**Phân biệt:** `List.of` có từ **Java 9**, còn `List.copyOf` từ **Java 10**. `var` là **suy luận kiểu biến cục bộ**, không phải dynamic type, không tự làm List bất biến và không được phép làm type của field/return method. Chi tiết này giúp nhận diện một lý do nguồn thực sự đòi Java 10 nhưng không tự quyết định min JDK của các dependency.

## 9. Multi-release JAR: vì sao quét JAR phải có ngữ cảnh

Một **multi-release JAR** được chuẩn hóa từ Java 9 có thể chứa:

~~~text
META-INF/MANIFEST.MF
com/example/Api.class
META-INF/versions/11/com/example/Api.class
META-INF/versions/17/com/example/Api.class
~~~

Nếu manifest bật `Multi-Release: true`, runtime Java hỗ trợ multi-release JAR có thể chọn class variant phù hợp với **version JVM đang chạy** (ưu tiên variant cao nhất không vượt runtime), thay vì luôn dùng base class.

Điều này ảnh hưởng cách xác định minimum JDK:

- Base `com/example/Api.class` có thể được compile cho một Java version cũ.
- Variant trong `META-INF/versions/11` có thể dùng Java 11 features.
- Variant trong `META-INF/versions/17` có thể dùng Java 17 features.
- **Không thể kết luận min JDK = 17 chỉ vì trong JAR có class major 61** nếu nó chỉ là optional version-specific variant và base variant chạy được trên JDK thấp hơn.
- Ngược lại, nếu **base class** hoặc dependency chung bắt buộc tải một class Java 17, baseline của toàn ứng dụng có thể vẫn là 17.
- Muốn biết behavior ở Java 10, phải kiểm tra **đúng class variant JVM 10 sẽ chọn**, manifest và toàn bộ đường nạp class cần thiết.

Các lệnh hữu ích:

~~~bash
jar --list --file library.jar
javap --multi-release 10 -verbose -classpath library.jar com.example.Api
javap --multi-release 17 -verbose -classpath library.jar com.example.Api
~~~

`javap --multi-release` cho phép phân tích class variant tương ứng release, khi JAR và tool hỗ trợ. Kiểm thử trên JVM tương ứng vẫn là xác nhận cuối cùng. Không tự quét **major lớn nhất trong tất cả entries** rồi dùng làm min runtime cho multi-release JAR.

### 9.1. Một vài tín hiệu có thể gây nhầm

- `Multi-Release: true` là manifest attribute, không phải cứ có thư mục `META-INF/versions` là runtime tự dùng mọi variant trong mọi tình huống.
- `Automatic-Module-Name` hay module descriptor giúp module naming, nhưng **không nói rõ** minimum Java runtime cho cả artifact.
- `Build-Jdk` hoặc `Build-Jdk-Spec` trong manifest thường cho biết một phần môi trường build; **không phải cam kết** runtime minimum vì artifact có thể cross-compile với `--release`.
- Một JAR được publish bằng CI chạy JDK 21 có thể chứa class major 54; ghi JDK 21 vào manifest **không đổi** classfile major 54.
- Versioned service/resource behavior và runtime API vẫn cần kiểm tra theo implementation.

## 10. Xác định yêu cầu JDK của thư viện

### 10.1. Từ tài liệu và release notes **đúng version**

Khi muốn thêm hoặc nâng thư viện:

1. Chốt tọa độ và version chính xác: Maven `groupId:artifactId:version` hoặc Gradle dependency notation.
2. Đọc trang **system requirements/minimum Java**, release notes và migration guide của đúng version, không chỉ README của nhánh main.
3. Nếu là framework, kiểm compatibility với **JDK, servlet container, bytecode enhancement, annotation processors**, build tool và plugins.
4. Kiểm các artifact/module phụ có baseline khác nhau, ví dụ core library và optional integrations.
5. Kiểm version được resolve thực tế và các transitive dependencies (có thể khác version bạn khai báo trực tiếp).
6. Khi có metadata variant (`org.gradle.jvm.version`, v.v.), xem xét điều kiện lựa chọn variant; **không coi tất cả module metadata đều có thuộc tính này**.
7. Kiểm classfile của các class code thực sự load; lưu ý multi-release JAR và dynamic loading.
8. Chạy smoke/integration tests trên **runtime mục tiêu thấp nhất được hỗ trợ**.

**Tại sao phải đúng release?** Nhà cung cấp có thể tăng minimum JDK ở **major release mới**. Library X bản A chạy Java 10 không cho phép suy ra bản B phát hành sau cũng như vậy.

### 10.2. Quét dependency graph

Với Maven:

~~~bash
./mvnw dependency:tree
./mvnw help:effective-pom
~~~

Với Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency some-library --configuration runtimeClasspath
~~~

Đây là **lệnh minh họa**, cần thay `some-library` bằng tên thực. Dependency resolution dùng BOM/platform, dependency constraints, profiles, scopes và conflict resolution có thể chọn khác version bạn nhìn thấy trong một dòng file build.

**Luôn kiểm tra ít nhất:**

- `compileClasspath`: các classes cần để compile.
- `runtimeClasspath`: các classes cần khi thực thi; có thể gồm dependency mà compile không trực tiếp thấy.
- Test dependencies/annotation processors: có JDK yêu cầu riêng.
- Plugin/buildscript dependencies: chạy trong JVM của build tool hoặc worker khác, không giống runtime của library thành phẩm.

Không chỉ chạy `dependency:tree` rồi kết luận baseline từ version name; cần tra requirements và/hoặc inspect classes.

### 10.3. Metadata có thể hữu ích, không phải bảo đảm tuyệt đối

Maven POM có thể chứa `maven.compiler.release`, plugin Enforcer rules hoặc properties nói về Java target. Nhưng POM phát hành không nhất thiết trùng chính xác cách artifact đã được build; một parent profile hoặc build hệ thống có thể override. Gradle metadata có thể công bố JVM compatibility của variant, nhưng tùy cách library được publish. Hãy xem metadata như **một nguồn bằng chứng**, không phải thay thế test trên runtime thật.

### 10.4. Thư viện dùng reflection, JNI và classpath scanning

Ngay cả khi classfile major phù hợp và compiler dùng `--release`, runtime có thể thiếu:

- Module/JDK service/provider mà thư viện cần.
- Public method bị gọi bằng reflection hoặc `MethodHandle` mà kiểm tra static không thấy rõ.
- Native library tương thích OS/architecture/JNI.
- Resource files/ServiceLoader implementations.
- Runtime dependencies được tải theo cấu hình/feature flags.
- Quyền truy cập reflective bị module encapsulation hạn chế.
- Các behavior khác nhau theo JDK/tzdb/locale/security configuration.

Vì vậy kết luận “tương thích Java 10” cần **kiểm thử đường chạy thực**, không chỉ đọc `major version: 54`.

## 11. Gradle: JDK chạy Gradle khác Java toolchain

Gradle có **Java compatibility matrix theo từng phiên bản Gradle**, gồm hai khả năng khác nhau:

1. JVM được phép dùng để **chạy Gradle**.
2. JDK có thể được dùng làm **toolchain để compile/test**.

Một JDK có thể được Gradle hỗ trợ làm toolchain trước/sau thời điểm nó được hỗ trợ làm JVM chạy chính Gradle daemon. Đừng coi version cao nhất có thể dùng để compile là version daemon có thể chạy.

### 11.1. Xác minh Gradle wrapper và runtime

~~~bash
./gradlew --version
./gradlew -q javaToolchains
~~~

Với Windows dùng `.\gradlew.bat`. Lệnh thứ nhất cho biết Gradle đang thực thi như thế nào; lệnh thứ hai liệt kê JDKs được phát hiện/cấu hình làm toolchains (khi áp dụng Java plugin).

Trước khi nâng JDK build hoặc Gradle wrapper, tra:

- [Gradle Compatibility Matrix](https://docs.gradle.org/current/userguide/compatibility.html) cho **version Gradle đã chọn**.
- Release notes/migration guide của Gradle và các plugins quan trọng.
- Cách thiết lập Gradle daemon JVM, Gradle toolchains, Gradle Test launchers và IDE Gradle JVM.
- Yêu cầu JDK chạy các plugin Groovy/Kotlin/Android/annotation processors có liên quan.

Không dùng một câu tĩnh kiểu “Gradle lúc nào cũng cần Java 8/11/17” cho mọi phiên bản Gradle. Baseline **thay đổi theo Gradle release**. Đọc bảng tương thích **hiện hành ứng với wrapper version**, không dùng số trong bài blog cũ.

### 11.2. Gradle Kotlin DSL: compiler JDK 17, target Java 10

Ví dụ **`build.gradle.kts`**:

~~~kotlin
plugins {
    java
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release = 10
}
~~~

Đây là **cấu hình ví dụ**; project thực cần bảo đảm Gradle wrapper đang dùng hỗ trợ JVM chạy Gradle và toolchain JDK 17, cài/provision JDK thích hợp, rồi đặt test JVM theo mục tiêu hỗ trợ.

Ý nghĩa:

- `toolchain.languageVersion=17`: yêu cầu Gradle Java compile tasks dùng compiler từ toolchain 17.
- `options.release=10`: yêu cầu `javac` nhắm cú pháp/JDK APIs/classfile Java 10.
- **Không** có nghĩa Gradle daemon tự chạy JDK 10 hoặc production JVM phải là 17.
- **Không** có nghĩa mọi library/annotation processor classfile đều target Java 10.
- Nếu target Java 10 thực sự là hợp đồng, cần test trên JVM 10 đúng version (hoặc hạ/loại bỏ cam kết đó nếu không còn được hỗ trợ trong sản phẩm).

### 11.3. `sourceCompatibility`/`targetCompatibility` không thay `--release`

~~~kotlin
// Chỉ minh họa: KHÔNG đủ để ngăn gọi JDK API mới.
java {
    sourceCompatibility = JavaVersion.VERSION_10
    targetCompatibility = JavaVersion.VERSION_10
}
~~~

Cấu hình này **không tự đảm bảo** compile chống lại platform APIs của Java 10; compiler chạy trên JDK 17 vẫn có nguy cơ thấy API mới nếu không kiểm soát API level. Dùng `options.release` và toolchain khi cần compatibility nghiêm ngặt.

### 11.4. Gradle Test JVM có thể cần điều chỉnh riêng

Toolchain của Java plugin thường áp dụng các task Java đã biết, nhưng các task custom, plugin hoặc test launcher riêng có thể không theo mặc định. Với test matrix:

~~~kotlin
tasks.register<Test>("testOn17") {
    javaLauncher = javaToolchains.launcherFor {
        languageVersion = JavaLanguageVersion.of(17)
    }
    useJUnitPlatform()
}
~~~

Đây là **đoạn minh họa**: cần dependency JUnit Platform/thiết lập `testClassesDirs` và `classpath` phù hợp nếu tạo test task riêng ngoài chuẩn project; không giả định copy nguyên vào mọi build script sẽ chạy đầy đủ. Mục đích là chỉ ra `Test.javaLauncher` có thể khác Java toolchain mặc định.

### 11.5. Chú ý Kotlin/Scala/Android plugin

Kotlin/JVM, Scala, Groovy, annotation processors, Android Gradle Plugin và các plugin bytecode enhancement có thể có yêu cầu chạy/compile riêng. Đừng suy `options.release=10` áp dụng đầy đủ cho mọi `kotlinc`/`scalac` task hoặc mọi generated class. Xem tài liệu compiler/plugin từng ngôn ngữ và kiểm final artifacts.

## 12. Maven: JVM chạy Maven khác JDK được Compiler Plugin chọn

Maven cũng có hai cấp quyết định:

- JVM dùng chạy **Maven core và plugins**.
- JDK compiler/toolchain được một plugin **toolchain-aware** sử dụng.

Maven Toolchains giúp chọn JDK để compile/test độc lập với JDK dùng chạy Maven, nếu plugins liên quan hỗ trợ toolchains.

### 12.1. Cấu hình Maven 3 Compiler Plugin target Java 10

Trong `pom.xml`, với Maven 3 và Maven Compiler Plugin hỗ trợ `release`:

~~~xml
<project>
  <!-- Các thông tin project thông thường -->
  <properties>
    <maven.compiler.release>10</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>
</project>
~~~

Đây là **đoạn cấu hình minh họa**, chưa phải một POM đầy đủ để build ngay; cần groupId/artifactId/version, plugin management và dependencies của project thực.

Tùy Maven major/Compiler Plugin version, syntax khuyến nghị có thể thay; xem trang [Maven Compiler Plugin – Set Compiler Release](https://maven.apache.org/plugins/maven-compiler-plugin/examples/set-compiler-release.html) cùng tài liệu đúng **phiên bản plugin**. Đừng đặt một property rồi giả định plugin cũ không hỗ trợ sẽ tự làm điều cần thiết.

### 12.2. Maven toolchains

Maven có plugin/toolchains mechanism để một build yêu cầu JDK compiler riêng (ví dụ 17), khác runtime của Maven. Tùy Maven/plugin version, có thể cấu hình `maven-toolchains-plugin`/toolchain selection trong POM, cùng toolchains được cài hoặc được phát hiện.

Tài liệu chính thức: [Maven – Guide to Using Toolchains](https://maven.apache.org/guides/mini/guide-using-toolchains).

**Điểm cần xác minh:**

1. `./mvnw -version` cho biết Maven core đang chạy với Java nào.
2. Compiler plugin version đã chọn, `release` và toolchain requirements hiện hành.
3. Compiler thực sự được sử dụng ở task, không chỉ `JAVA_HOME`.
4. Surefire/Failsafe/test fork JVM có dùng phiên bản được yêu cầu không.
5. Các plugins Maven khác như shading, static analysis, codegen, formatter, annotation processors đòi JDK nào.
6. `effective-pom` và build logs có cấu hình bị override bởi parent/plugin management/profiles không.

**Không có luật “Maven chạy JDK 17 thì mọi artifact build ra buộc Java 17”.** Target và toolchain quyết định việc biên dịch; dependencies và runtime testing quyết định mức hỗ trợ thực tế.

### 12.3. Enforcer rules và kiểm soát environment

Nếu dự án muốn fail fast khi Maven JVM không đạt ràng buộc, Maven Enforcer Plugin có rule như `requireJavaVersion`. Đây là **cơ chế bảo vệ môi trường build**, không phải bằng chứng rằng output library đã target cùng Java version. Cần cấu hình thêm Compiler Plugin release, toolchains và test runtime.

Không nhầm “Maven itself phải chạy JDK N” với “artifact cần JDK N”. Một plugin Enforcer có thể đòi Maven JVM cao hơn app runtime một cách hợp lệ.

## 13. Plugin, annotation processor và code generator cũng là phụ thuộc JDK

Khi đánh giá yêu cầu JDK, thường bỏ sót các thành phần **không nằm trong compile/runtime dependencies** thông thường:

| Thành phần | Có thể chạy ở đâu | Vấn đề hay gặp |
| --- | --- | --- |
| Gradle plugin | JVM của Gradle daemon | Plugin mới nâng minimum JVM và build dừng từ lúc cấu hình |
| Maven plugin | JVM chạy Maven hoặc fork/toolchain | Plugin không nạp được dù project target thấp |
| Annotation processor | JVM/compiler process | Processor cần JDK cao hơn compiler toolchain |
| Kotlin/Scala/Groovy compiler | Toolchain/daemon/worker riêng | Java target và plugin JVM yêu cầu khác |
| Unit test engine/runner | Test JVM riêng | Không chạy được test trên JVM cũ dù code app chạy được |
| Code generator | Build process hoặc executable ngoài | Generated source/API/bytecode đòi target khác |
| Bytecode transformer/shader | Build tool process | Công cụ không parse classfile version mới |
| Coverage/test instrumentation | Test JVM, agents hoặc build plugins | Agent không hỗ trợ JVM/bytecode đã chọn |
| Docker/base image | Deployment runtime | JVM thật của container thấp hơn artifact |
| JNI/native libraries | Runtime theo OS/architecture | Java bytecode đúng nhưng native binding sai |

Các thành phần trên có **version compatibility matrices riêng**; không chỉ cần Java compiler hỗ trợ `--release 10`. Một lỗi kiểu “Unsupported class file major version” trong Gradle/Groovy/bytecode parser có thể là lỗi **công cụ phân tích classfile cũ** chứ không phải JVM chạy artifact không đủ; đọc stack trace để phân biệt.

### 13.1. Tại sao annotation processor cần xem riêng?

Code của sản phẩm compile bằng `--release 10` nhưng annotation processor chạy trong **compiler process hiện đại**, có thể cần API của JDK 17. Nó không nhất thiết được đóng vào runtime artifact; điều đó có thể hoàn toàn hợp lệ. Ngược lại, generated classes/sources do processor tạo ra có thể gọi library API không tồn tại trên runtime mục tiêu. Phải kiểm tra cả output và test.

### 13.2. Đừng “nâng cả JDK runtime” chỉ để chữa mọi plugin issue

Nếu plugin build yêu cầu JDK cao hơn nhưng app vẫn cần target thấp, đôi khi có thể nâng **JDK của build tool hoặc compiler** và giữ `--release` để xây artifact cho target thấp. Nhưng chỉ làm như vậy khi phiên bản Gradle/Maven/plugin hỗ trợ cách kết hợp, và có tests thực tế trên runtime target. Không dùng một Java version cho mọi công cụ chỉ vì đơn giản hóa sơ đồ.

## 14. `jdeps` giúp tìm phụ thuộc tĩnh, không thể tự chứng minh minimum runtime

`jdeps` là công cụ phân tích dependency Java class/archive. Ví dụ:

~~~bash
jdeps --multi-release 10 --jdk-internals library.jar
jdeps --multi-release 10 --print-module-deps library.jar
~~~

Giải thích:

- `--multi-release 10` yêu cầu phân tích multi-release JAR theo version tương ứng, khi JAR và tool hỗ trợ.
- `--jdk-internals` hỗ trợ phát hiện phụ thuộc vào **JDK internal APIs** ở mức tĩnh.
- `--print-module-deps` có thể giúp xác định các module cần thiết cho một phân tích hợp lệ; nó **không cam kết** lắp đủ toàn bộ runtime động.
- Với dependencies bên ngoài, có thể cần `--class-path`/`--module-path` phù hợp để kết quả không đầy unresolved references.
- Code dùng reflection/ServiceLoader, dynamic proxy, native code, dependency loading theo condition và configuration có thể không hiện hết qua static analyzer.

Không lấy kết quả `jdeps` như một chứng nhận “đã tương thích Java 10” hoặc thay integration tests. Dùng nó để thu hẹp phần cần điều tra, nhất là khi migrate modularization hoặc JDK internals.

### 14.1. Module path và JDK internals

Java Platform Module System có từ Java 9. Một library có classfile major 54 nhưng lại sử dụng non-exported JDK APIs có thể gặp lỗi access trên runtime khác. `--release` giúp ngăn sử dụng những APIs nền tảng không công khai trong quá trình compile theo target, nhưng code cũ, reflection và library bên thứ ba vẫn cần kiểm tra.

Tránh xem các tùy chọn `--add-exports`/`--add-opens` để mở internals là giải pháp lâu dài cho thư viện mới; ưu tiên nâng/migrate sang public supported APIs. Tùy module/runtime, việc dùng tùy chọn này có thể bị hạn chế hoặc không phù hợp với việc compile theo `--release`.

## 15. Xây ma trận CI để xác thực tuyên bố hỗ trợ

Một quy trình tốt cho library hoặc ứng dụng:

1. **Xây trên JDK build được hỗ trợ**, với wrapper/plugin versions cố định.
2. Cài/chọn **compiler toolchain** tường minh và `--release` theo baseline đã công bố.
3. Xác minh classfile major của artifact xuất ra.
4. Phân tích direct/transitive dependencies và multi-release JAR.
5. Chạy unit và integration tests trên **runtime thấp nhất được cam kết** (nếu vẫn có môi trường hợp lệ để hỗ trợ).
6. Chạy thêm trên một hoặc vài JVM mới hơn mà sản phẩm hỗ trợ.
7. Thử startup, class loading/ServiceLoader, serialization, reflection, database drivers, network/TLS, time zones, Unicode và native integrations khi liên quan.
8. Lưu ma trận kết quả trong CI thay vì chỉ ghi “works on my machine”.

### 15.1. Ví dụ ma trận có chủ đích

| Job | Build JDK | Compiler target | Test JVM | Ý nghĩa |
| --- | --- | --- | --- | --- |
| Compile baseline | 17 | `--release 10` | 17 | Chứng minh source + Java platform API của target và tạo major 54 |
| Runtime compatibility | 17 | Dùng artifact đã build | 10 **nếu được cam kết và được tổ chức chấp nhận hỗ trợ** | Xác nhận dependency và code path trên JVM thấp nhất |
| Newer runtime | 17 | Dùng artifact đã build | 17 | Kiểm tính tương thích xuôi lên JVM mới |
| Tooling verification | Theo Gradle/Maven matrix | Theo build file | Theo yêu cầu plugin | Xác minh build tool/plugins hoạt động với JDK được chọn |

**Lưu ý:** Java 10 là release cũ không phải bản bảo trì dài hạn. Ma trận Java 10 chỉ phù hợp làm **ví dụ đào tạo** hoặc dự án có hợp đồng rõ về nền tảng cũ và phương án bảo mật được phê duyệt. Với dự án mới, nên đặt minimum runtime là **một bản JDK còn được hỗ trợ** và đưa chính phiên bản đó vào CI.

### 15.2. Tại sao thử trên JDK 17 không chứng minh chạy được Java 10?

JDK 17 có thể tải class major 54, nhưng JDK 10 có thể không tải dependency major 61 hoặc không có một method JDK được một thư viện gọi động. Test “chạy được trên JDK mới” chỉ chứng minh trường hợp JVM mới trong matrix, **không** chứng minh backward compatibility.

Ngược lại, một số vấn đề chỉ xảy ra trên JDK mới vì module encapsulation, thay đổi policy bảo mật, TLS defaults, tzdb hoặc code xử lý reflection cũ. Vì thế nếu thư viện công bố hỗ trợ nhiều JVM, phải test cả **min** và **các phiên bản cao hơn quan trọng**.

## 16. Phát hành library: công bố minimum JDK tường minh

Khi bạn là tác giả thư viện, nên:

1. Công bố trong README/release notes: **Minimum supported Java runtime** và các JVM được test.
2. Ghi rõ compiler/target language và toolchain trong build config, không chỉ trong tài liệu.
3. Pin/plugin-manage Gradle/Maven versions để CI tái lập được.
4. Xác minh artifact thực tế sau build (`javap`/bytecode scanner/gradle metadata).
5. Kiểm dependencies không vượt baseline đã hứa, kể cả khi dependency resolution đổi phiên bản.
6. Ghi thay đổi minimum Java như **breaking change/migration requirement** khi nâng major/minor version.
7. Với multi-release JAR, công bố base runtime baseline và các enhanced implementations theo version.
8. Kiểm runtime integrations và system requirements không thuộc classfile như OS/architecture/JNI.
9. Không đưa `Build-Jdk-Spec` vào README dưới dạng “bằng chứng Java runtime tối thiểu”.
10. Không quảng cáo Java 10 compatibility nếu không còn test hoặc không thể hỗ trợ security requirements.

Ví dụ tuyên bố tốt:

~~~text
Library 2.x:
- minimum runtime: JDK N (theo chính sách hỗ trợ của thư viện)
- compiled/tested using: compiler/toolchain JDK M, --release N
- tested JVMs: N, ... [versions thực tế trong CI]
- build requires: Gradle/Maven + JDK đáp ứng compatibility matrix tương ứng
- special requirements: modules/native support/Android/etc. nếu có
~~~

Đây là **mẫu tài liệu**, không phải tuyên bố về một library thật. Tránh dùng một số Java version mơ hồ “Java 10+” mà không nói rõ plugin/framework/runtime matrix và không duy trì test cho baseline.

## 17. Demo Java 10 chạy trên JDK hiện đại: đọc version của chính class

Ví dụ này dùng:

- `var` và `List.copyOf` — hai điểm nhận diện Java 10.
- `DataInputStream` đọc 8 byte đầu classfile (`CAFEBABE`, minor, major).
- `Class.getResourceAsStream` mở bytecode của chính class được load.
- `Runtime.version().feature()` kiểm JVM hiện tại thuộc Java 10+ mà **không in số JDK môi trường tùy biến**, giúp stdout ổn định.
- Một phép so sánh mô phỏng: JVM Java 10 không thể nạp class major 61, còn JVM Java 17 có thể nhận format major 54. **Mô phỏng này chỉ xét giới hạn class-file major**, không tự bảo đảm API/dependency compatibility.

Lưu file **`JdkRequirementDemo.java`**:

~~~java
import java.io.DataInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.util.Arrays;
import java.util.List;
import java.util.Objects;

public class JdkRequirementDemo {
    static int majorOf(Class<?> type) throws IOException {
        String resource = type.getSimpleName() + ".class";
        try (InputStream raw = type.getResourceAsStream(resource)) {
            if (raw == null) {
                throw new IOException("Missing class resource: " + resource);
            }
            DataInputStream data = new DataInputStream(raw);
            if (data.readInt() != 0xCAFEBABE) {
                throw new IOException("Invalid class-file magic");
            }
            data.readUnsignedShort(); // minor version
            return data.readUnsignedShort(); // major version
        }
    }

    static int majorForJava(int javaVersion) {
        if (javaVersion < 5) {
            throw new IllegalArgumentException("Use Java 5 or later");
        }
        return javaVersion + 44;
    }

    static boolean supportsClass(int jdkFeature, int classMajor) {
        return classMajor <= majorForJava(jdkFeature);
    }

    public static void main(String[] args) throws Exception {
        var features = List.copyOf(Arrays.asList("var", "copyOf"));
        int major = majorOf(JdkRequirementDemo.class);
        System.out.println("features=" + features);
        System.out.println("self-class-major=" + major);
        System.out.println("self-minimum-java=" + (major - 44));
        System.out.println("java-10-major=" + majorForJava(10));
        System.out.println("java-11-major=" + majorForJava(11));
        System.out.println("java-17-major=" + majorForJava(17));
        System.out.println("jdk10-loads-class54=" + supportsClass(10, 54));
        System.out.println("jdk10-loads-class61=" + supportsClass(10, 61));
        System.out.println("jdk17-loads-class54=" + supportsClass(17, 54));
        System.out.println("running-jdk-at-least-10=" +
                (Runtime.version().feature() >= 10));
        System.out.println("java10-list-copy=" +
                Objects.equals(features, List.of("var", "copyOf")));
    }
}
~~~

Biên dịch bằng **JDK 17+ có hỗ trợ `--release 10`**:

~~~bash
javac --release 10 -encoding UTF-8 JdkRequirementDemo.java
java JdkRequirementDemo
javap -verbose JdkRequirementDemo
~~~

Nếu compile vào thư mục riêng, dùng `javac --release 10 -d out ...` và `java -cp out JdkRequirementDemo`; `javap -verbose -classpath out JdkRequirementDemo`.

**Stdout của chương trình, đã được kiểm thử:**

~~~text
features=[var, copyOf]
self-class-major=54
self-minimum-java=10
java-10-major=54
java-11-major=55
java-17-major=61
jdk10-loads-class54=true
jdk10-loads-class61=false
jdk17-loads-class54=true
running-jdk-at-least-10=true
java10-list-copy=true
~~~

Với `javap -verbose`, phần đầu metadata có:

~~~text
minor version: 0
major version: 54
~~~

### 17.1. Giải thích từng nhóm stdout

1. `features=[var, copyOf]`: code dùng local-variable inference và immutable list factory phù hợp Java 10.
2. `self-class-major=54`: compiler đã phát hành bytecode target Java 10.
3. `self-minimum-java=10`: lấy `54-44`. Đây là **giới hạn từ classfile của chính demo**, không phải một bản phân tích runtime dependency.
4. `java-10-major=54`, `java-11-major=55`, `java-17-major=61`: mỗi Java feature release mới hơn tăng major theo quy tắc classfile.
5. `jdk10-loads-class54=true`: chỉ mô phỏng **điều kiện phiên bản bytecode** để load.
6. `jdk10-loads-class61=false`: JVM Java 10 không hiểu classfile Java 17.
7. `jdk17-loads-class54=true`: Java 17 có thể hiểu classfile Java 10 thông thường.
8. `running-jdk-at-least-10=true`: chương trình đang chạy trên JDK >=10, phù hợp việc dùng các API nguồn.
9. `java10-list-copy=true`: `List.copyOf` đã hoạt động theo logic ví dụ.

### 17.2. Giới hạn của detector demo

`majorOf` đọc đúng class có thể tìm qua `getResourceAsStream`, nhưng:

- Không quét mọi class của ứng dụng hay dependency transitive.
- Không kiểm `minor=65535`/preview feature.
- Không xử lý mọi packaging như JMOD/nested JAR/fat JAR.
- Không đọc release-specific variant cho multi-release JAR một cách tổng quát.
- Không chứng minh không tham chiếu API Java 11/17, reflection, JNI hoặc module runtime restrictions.
- Không dùng để xác định chính xác “min JDK của một sản phẩm” chỉ bằng công thức `major-44`.

Với ứng dụng thực, kết hợp **metadata → classfile scan → source/API target → dependency graph → CI runtime**.

## 18. Ví dụ kiểm thử biên dịch API: Java 11 `String.repeat`

File phụ dùng để kiểm compiler target, không trộn vào demo chạy Java 10:

~~~java
public class NeedsJava11 {
    public static void main(String[] a) {
        System.out.println("a".repeat(2));
    }
}
~~~

Kết quả kiểm chứng thực tế:

| Lệnh | Kết quả |
| --- | --- |
| `javac --release 10 NeedsJava11.java` | **FAIL đúng kỳ vọng**: compiler không tìm thấy method `String.repeat(int)` |
| `javac --release 17 NeedsJava11.java` | **PASS** |
| `java NeedsJava11` sau khi compile target 17 trên JVM >=17 | In `aa` |

Không cần sửa code Java 10 bằng cách vô hiệu hóa `--release`. Nếu cần runtime Java 10 thật, đổi `String.repeat` sang API sẵn có trong Java 10; nếu sản phẩm đã quyết định Java 17 là baseline, hãy nâng target theo policy và kiểm tất cả dependencies.

**Ranh giới quan trọng:** `javac --release 10` kiểm API **JDK** ở compile time, nhưng một thư viện Java 17 được tham chiếu gián tiếp vẫn có thể gây runtime linkage errors trên JDK 10. Cần kiểm toàn dependency graph và test đúng runtime.

## 19. Quy trình điều tra sự cố từ symptom đến quyết định

### Tình huống A – Ứng dụng build được nhưng chạy báo `UnsupportedClassVersionError`

1. Ghi lại JVM **thực sự chạy ứng dụng** (Docker/container, service launcher, CI test JVM).
2. Đọc lỗi class major/minor và **tên class cụ thể**.
3. Xác định class đến từ project output hay dependency JAR nào.
4. Kiểm build target `--release` và plugin/compiler toolchain.
5. Nếu là dependency: tra minimum JDK của version đang resolve, classfile/MR-JAR variants.
6. Chọn runtime được hỗ trợ hoặc dependency compatible; không hex-edit classfile.
7. Chạy integration tests trên runtime đã chọn.

### Tình huống B – Gradle/Maven khởi động không được sau khi đổi JDK

1. Chạy wrapper version và xem yêu cầu JDK **chạy build tool**, khác yêu cầu app runtime.
2. Đọc compatibility matrix đúng Gradle/Maven version.
3. Kiểm plugins/annotation processors đã tương thích JDK mới không.
4. Kiểm `JAVA_HOME`, daemon JVM, IDE Gradle JVM, Maven JVM, toolchains.
5. Cập nhật wrapper/plugin theo kế hoạch có test; không chỉ chỉnh `sourceCompatibility`.
6. Nếu product target thấp, vẫn có thể giữ `--release` và runtime test cho baseline.

### Tình huống C – Chạy được trên JDK 17, lỗi `NoSuchMethodError` trên JDK thấp

1. Xem method/class bị thiếu có thuộc Java Platform API mới hơn target hay dependency bên ngoài.
2. Kiểm source có bị compile bằng `-source/-target` mà không có `--release` không.
3. Nếu dependency ngoài JDK, kiểm version/variant ở runtime classpath.
4. Cần rebuild source đúng target và chọn library hỗ trợ runtime đó.
5. Test trên JVM minimum trước khi phát hành.

### Tình huống D – Build plugin báo không hiểu classfile major mới

1. Xác định ai ném lỗi: JVM loader, Groovy/ASM/Javassist/Byte Buddy/test agent hay compiler.
2. So sánh parser/tool/plugin version với classfile Java version được nó hỗ trợ.
3. Nâng công cụ/agent tương thích hoặc dùng toolchain/target phù hợp.
4. Đừng kết luận source code ứng dụng sai chỉ vì plugin instrumentation cũ không đọc bytecode mới.

### Tình huống E – Plugin mới yêu cầu JDK 17 nhưng ứng dụng target Java 10

Có thể hoàn toàn hợp lệ khi **plugin chạy trên build JVM 17**, compiler target `--release 10`, miễn là plugin/toolchain có thể build và tests trên Java 10 thành công. Nếu có JDK/Gradle/Maven constraint xung đột, cần quyết định version combinations được support chính thức. Không hứa một plugin build trên JDK 17 biến mọi dependency runtime thành Java 10-compatible.

## 20. Các lỗi suy luận phổ biến

| Kết luận sai | Tại sao sai | Cách làm đúng |
| --- | --- | --- |
| “Chạy `java -version` thấy 17 nên compiler cũng là 17” | PATH, toolchain và build daemon có thể khác | Kiểm JavaCompile/Maven compiler thực tế |
| “`mvn -version` thấy 17 tức artifact target 17” | Maven JVM khác compiler target | Kiểm `maven.compiler.release` và toolchain |
| “`sourceCompatibility=10` bảo đảm không dùng API 11” | Source compatibility không giới hạn JDK API đủ nghiêm | `options.release=10` |
| “`-target 10` là Java 10 compatible hoàn toàn” | Bytecode target không chặn API mới | `--release 10` và runtime tests |
| “Major 54 chứng minh toàn bộ library Java 10 compatible” | Dependency/reflection/native/MR-JAR có thể khác | Scan artifact graph + CI runtime |
| “Có class Java 17 ở META-INF/versions/17 thì min Java=17” | Multi-release JAR có base variant thấp | Kiểm manifest và variant theo runtime |
| “Manifest Build-Jdk-Spec là minimum runtime” | Mô tả môi trường build, không phải public runtime contract | Docs + target + runtime tests |
| “Một dependency trực tiếp hỗ trợ Java 10 là đủ” | Transitive dep có thể nâng baseline | Kiểm runtimeClasspath/graph |
| “Maven/Gradle mới lúc nào cũng chạy trên mọi Java” | Tool version có support range | Xem compatibility matrix phiên bản cụ thể |
| “JDK compiler cao thì không thể build target thấp” | `--release` và toolchains hỗ trợ cross-compile | Phân biệt build JDK với target |
| “Plugin chạy JDK cao bắt buộc app runtime cũng cao” | Plugin thường không đóng vào artifact | Phân biệt plugin/build classpath với runtime classpath |
| “Test trên JDK 17 chứng minh hỗ trợ Java 10” | JVM mới có API/bytecode hỗ trợ rộng hơn | Test JVM baseline |
| “Compiler `--release` chắc chắn kiểm tất cả native/reflection” | Chỉ kiểm JDK APIs/language/classfile | Integration test và dependency audit |
| “JDK 10 cũ thì cứ deploy mới ở Java 10 để học” | Bản JDK cũ có rủi ro maintenance/security | Học semantics Java 10, deploy JDK đang được hỗ trợ |
| “Tự đổi major binary đủ để hạ runtime” | Format/API semantic có thể không tương thích | Recompile đúng target |
| “Gradle Java toolchain tự sửa target runtime API” | Toolchain chọn compiler, không giới hạn API target khác | Dùng `options.release` |
| “Một con số Java version giải quyết mọi constraint” | Build JVM, compiler, test JVM, runtime và plugin độc lập | Lập ma trận ràng buộc |

## 21. Bài tập tự kiểm tra và đáp án

**Bài 1.** Một JAR có class `major 54`. Nó được compile cho Java nào ở mức classfile?

**Đáp án:** Java 10. Đây là thông tin bytecode format, **không phải** một bằng chứng tự động về toàn bộ dependency runtime.

**Bài 2.** Class `major 61` có thể chạy trên JVM Java 10 không?

**Đáp án:** Không. Java 10 nhận class format tối đa major 54; thường báo `UnsupportedClassVersionError`.

**Bài 3.** `javac --release 10` có giới hạn Java 10 API trong code nguồn không?

**Đáp án:** Có, đối với các Java/JDK platform APIs hỗ trợ cho target, cùng cú pháp và classfile version; không tự kiểm soát mọi thư viện bên thứ ba/dynamic code.

**Bài 4.** Vì sao `javac -source 10 -target 10` chưa đủ?

**Đáp án:** Nó có thể biên dịch code sử dụng API mới hơn từ JDK đang chạy compiler vì không giới hạn JDK platform API như `--release`.

**Bài 5.** Một ứng dụng build bằng JDK 17, artifact major 54. Nó **chắc chắn** chạy JDK 10 chứ?

**Đáp án:** Không. Cần kiểm runtime dependencies, API calls, multi-release entries, reflection/JNI và integration tests trên JVM Java 10 nếu đó là baseline được cam kết.

**Bài 6.** `String.repeat` (Java 11) có được gọi trong code target `--release 10` không?

**Đáp án:** Không. Compiler từ chối reference API Java 11 khi target 10.

**Bài 7.** `mvn -version` cho thấy JDK nào?

**Đáp án:** JVM dùng chạy Maven, không nhất thiết là compiler JDK hoặc product runtime.

**Bài 8.** `gradlew --version` cho thấy JDK nào? Có đủ để suy JDK Test task không?

**Đáp án:** Cho runtime/build tool information, nhưng Java toolchains hoặc Test Java launcher có thể khác; cần kiểm task/toolchain config.

**Bài 9.** Gradle `java.toolchain.languageVersion=17` nhưng `options.release=10` nghĩa gì?

**Đáp án:** Compiler toolchain Java 17, source/API/classfile target Java 10. Không tự chứng minh dependencies chạy được trên JVM Java 10.

**Bài 10.** Multi-release JAR có class major 61 trong `META-INF/versions/17`. Base class major 54. Min JDK chắc chắn 17 không?

**Đáp án:** Không. Runtime Java 10 có thể dùng base variant nếu JAR có cấu hình MR hợp lệ và các dependency khác phù hợp. Cần kiểm toàn bộ JAR/runtime behavior.

**Bài 11.** Gradle 9.x/JDK version mới có chắc khởi động được trên mọi JDK không?

**Đáp án:** Không. Xem compatibility matrix **đúng Gradle wrapper version**. Khả năng chạy Gradle khác khả năng dùng JDK làm toolchain compile/test.

**Bài 12.** Plugin Maven yêu cầu build JVM Java 17, còn artifact target Java 10. Có thể hợp lệ không?

**Đáp án:** Có, nếu compiler/toolchain/plugins hỗ trợ cách kết hợp và artifact cùng dependencies được test đúng baseline runtime.

**Bài 13.** `Build-Jdk-Spec: 17` trong manifest có đủ kết luận minimum runtime Java 17 không?

**Đáp án:** Không. Nó có thể chỉ mô tả JDK tạo artifact; `--release 10` vẫn có thể xuất class major 54.

**Bài 14.** `jdeps` có chứng minh không còn lỗi reflection/JNI hoặc dynamic service loading không?

**Đáp án:** Không. Nó phân tích static dependencies; dynamic behavior và native libraries vẫn cần kiểm tra.

**Bài 15.** Vì sao cần xem `runtimeClasspath` ngoài `compileClasspath`?

**Đáp án:** Runtime có thể chọn dependency/version khác hoặc bổ sung thư viện mà compile không dùng trực tiếp; runtime min JDK phải xét cả dependency thực tế.

**Bài 16.** Có thể chạy các test Java 17 và tuyên bố hỗ trợ Java 10 không?

**Đáp án:** Không. Nếu cam kết Java 10, cần chạy trên Java 10 hoặc dùng quy trình tương thích có phạm vi/chứng cứ đủ, không chỉ test JDK mới.

**Bài 17.** Class major 54 nhưng dùng preview minor 65535 thì sao?

**Đáp án:** Preview classfile có ràng buộc chặt về đúng JVM feature release và bật preview theo quy tắc của release áp dụng. Đừng chỉ kiểm major; lưu ý Java 10 không có preview features theo cơ chế các release sau, ví dụ này là cảnh báo tổng quát về minor=65535.

**Bài 18.** Nếu source vẫn cần Java 10 semantics để học, có nên triển khai production JDK 10 ngay hôm nay không?

**Đáp án:** Không chỉ vì mục đích học. Chạy/vận hành bằng một JDK được nhà cung cấp hỗ trợ và kiểm policy bảo mật; Java 10 là ví dụ về mô hình phiên bản/bytecode.

**Bài 19.** Khi một plugin bytecode parser báo “Unsupported class file major version”, có chắc runtime Java không tải được class không?

**Đáp án:** Không. Cần xác định lỗi do JVM loader hay công cụ bên thứ ba như ASM/Groovy/agent. Parser cũ có thể không hiểu classfile mới dù JVM đích hỗ trợ.

**Bài 20.** Điều kiện nào giúp tuyên bố tối thiểu Java N trở nên đáng tin?

**Đáp án:** Docs/release notes đúng version; build target `--release N`; compiler/toolchain và plugin phù hợp; kiểm classfile/dependency graph/multi-release; và CI test trên runtime N cùng các phiên bản khác được hỗ trợ.

## 22. Checklist dùng khi thêm thư viện hoặc nâng build tool

1. **Sản phẩm cần chạy tối thiểu JDK nào?** Đây có phải version đang được hỗ trợ an toàn để vận hành?
2. **Thư viện đúng version yêu cầu runtime JDK nào?** Đã đọc release notes/migration guide của version đó?
3. **Framework/app server/driver/plugin có yêu cầu cao hơn không?**
4. **Các transitive dependencies đang resolve là gì?** Có artifact runtime-only nào nâng min Java?
5. **Có multi-release JAR không?** Đã kiểm base/variant theo JVM thực không?
6. **Classfile major/minor của artifact và dependencies phù hợp không?** Có preview marker không?
7. **Compiler thật dùng JDK nào?** Toolchain và `javac -version` có khớp expectation không?
8. **Build tool thật chạy JVM nào?** `mvnw -version`/`gradlew --version` trả gì?
9. **Gradle wrapper/Maven core/plugin versions có support JVM đó không?**
10. **Target language/API có dùng `--release` không?** Nếu không, lý do và biện pháp thay thế là gì?
11. **Có annotation processors/code generators/bytecode agents nào dùng JDK riêng không?**
12. **Test JVM có đang dùng đúng phiên bản min được công bố không?**
13. **Có integration tests cho reflection/ServiceLoader/JNI/TLS/database/native resources không?**
14. **Có container/base image và serverless/runtime configuration phù hợp không?**
15. **Có framework/tool version bị ghi ngầm bởi CI/IDE profile không?**
16. **Có lỗi `UnsupportedClassVersionError`/`NoSuchMethodError` bị che bởi test trên JDK mới không?**
17. **Có kiểm OS/CPU architecture và container libc/JNI khi native dependency hiện diện không?**
18. **Có ghi rõ minimum runtime JDK trong README và changelog của thư viện không?**
19. **Có lock/version quản lý dependency/wrapper để kết quả build tái lập không?**
20. **Có kế hoạch nâng baseline và bỏ các JVM không còn được hỗ trợ thay vì phụ thuộc mãi vào Java 10 không?**

## 23. Nguồn chính thức để kiểm chứng khi áp dụng

1. [Oracle – `javac` command, `--release`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html): khác `-source`/`-target`; giới hạn API nền tảng của target.
2. [OpenJDK – javac command hiện hành](https://github.com/openjdk/jdk/blob/master/src/jdk.compiler/share/man/javac.md): compiler chỉ hỗ trợ một số release target giới hạn; kiểm `javac --help` của toolchain thực.
3. [Oracle JDK 10 Release Notes – Class File Version 54.0](https://www.oracle.com/java/technologies/javase/10all-relnotes.html): xác minh Java 10 classfile major **54**.
4. [Java SE 17 – JVM Specification `4.1, ClassFile Structure](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.1): magic, minor và major version.
5. [Java SE 17 – `UnsupportedClassVersionError`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/UnsupportedClassVersionError.html): classfile version JVM không hỗ trợ.
6. [Java SE 17 – `javap`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html): xem thông tin classfile với `-verbose`.
7. [Java SE 17 – `jar`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jar.html): tạo/liệt kê/multi-release JAR và manifest.
8. [Java SE 17 – `jdeps`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jdeps.html): phân tích dependencies và multi-release variant.
9. [Gradle – Java Compatibility Matrix](https://docs.gradle.org/current/userguide/compatibility.html): phân biệt JVM chạy Gradle với compile/test toolchain, cập nhật theo từng Gradle release.
10. [Gradle – Java Toolchains](https://docs.gradle.org/current/userguide/toolchains.html): kết hợp toolchain JDK và `options.release`, kiểm JavaCompile/Test launchers, phát hiện toolchains.
11. [Gradle – Building Java & JVM Projects](https://docs.gradle.org/current/userguide/building_java_projects.html): target Java bằng toolchains/release.
12. [Apache Maven – Compiler Plugin `--release`](https://maven.apache.org/plugins/maven-compiler-plugin/examples/set-compiler-release.html): giới hạn language/platform API/bytecode và cấu hình plugin.
13. [Apache Maven – Guide to Using Toolchains](https://maven.apache.org/guides/mini/guide-using-toolchains): chọn JDK compiler khác JVM chạy Maven.
14. [Apache Maven – Enforcer requireJavaVersion](https://maven.apache.org/enforcer/enforcer-rules/requireJavaVersion.html): kiểm điều kiện JDK của môi trường build.
15. [Java SE 17 – Runtime.Version](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Runtime.Version.html): `feature()` và versioning runtime.
16. [Java SE 17 – `String.repeat`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html#repeat(int)): API từ Java 11, dùng để chứng minh `--release 10` không cho truy cập API mới.
17. [Java SE 17 – `List.copyOf`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)): API từ Java 10, dùng trong ví dụ chạy được.

**Tóm tắt cuối:** Để **xác định yêu cầu JDK của thư viện và công cụ xây dựng**, phải phân biệt **JVM chạy Maven/Gradle**, **compiler toolchain**, **Java language/API/bytecode target**, **test JVM** và **runtime JVM thật**. Với Java 10, classfile major là **54**; `javac --release 10` giúp phát hành code theo cú pháp/API Java 10, nhưng **không tự chứng minh** mọi dependency/reflective/native path chạy được trên JVM 10. Hãy lấy yêu cầu từ tài liệu của đúng phiên bản thư viện và build tool, kiểm JAR/multi-release/dependency graph, thiết lập toolchains/`--release` rõ, rồi **kiểm thử trên những JDK thực tế được sản phẩm cam kết hỗ trợ**. Với dự án mới, ưu tiên một JDK còn được hỗ trợ thay vì dùng Java 10 làm lựa chọn triển khai chỉ vì nó là chủ đề bài học.
