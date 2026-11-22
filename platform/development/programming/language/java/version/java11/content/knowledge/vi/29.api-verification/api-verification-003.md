# Kiểm tra dependency, compiler plugin và công cụ bytecode — Kiểm chứng API Java 11+

## 1. Vấn đề cần giải quyết

Khi một dự án tuyên bố **“hỗ trợ Java 11”**, việc chương trình **biên dịch thành công trên JDK mới** hoặc có file `.class` mang version Java 11 **chưa đủ chứng minh** ứng dụng thật sự chạy được trên Java 11.

Có ít nhất ba lớp độc lập phải kiểm chứng:

1. **Nguồn Java và API nền tảng:** source code có dùng cú pháp hoặc Java SE APIs xuất hiện sau Java 11 không? Hãy kiểm tra bằng `javac --release 11`.
2. **Dependency, compiler plugin và build-time tools:** tất cả thư viện trực tiếp, phụ thuộc bắc cầu, plugin, annotation processors, test tools và bytecode transformers có tương thích với JDK chạy build và JDK chạy ứng dụng không? Phiên bản nào thực sự được resolve?
3. **Classfile và runtime behavior:** các class trong application artifact, transitive JAR, shaded/fat JAR, multi-release JAR và generated classes có major version và API phù hợp với môi trường runtime dự kiến không? Có lỗi linkage, reflection, module access hoặc ServiceLoader lúc chạy không?

Ví dụ quan trọng đã kiểm chứng trên JDK mới:

```text
App.class    : major 55  (Java 11 bytecode)
Library.class: major 61  (Java 17 bytecode)

App vẫn có thể được javac --release 11 biên dịch thành công
khi trỏ vào Library.class được compiler mới hiểu.

=> Runtime Java 11 vẫn không thể nạp Library.class major 61.
```

Do đó, **`--release 11` bảo vệ API nền tảng mà source Java sử dụng, nhưng không tự biến các third-party JAR thành thư viện tương thích Java 11**.

Bài này hướng dẫn kiểm chứng thực tế với **Maven, Gradle, javac, javap, jar, jdeps, jdeprscan**, giải thích vai trò của compiler plugins và bytecode tools như **ASM, Byte Buddy, JaCoCo**, đồng thời xây một checklist CI có thể dùng tiếp cho các phiên bản Java hiện đại.

**Phạm vi phiên bản:** mục tiêu tương thích **Java 11**, nhưng dùng JDK mới để build khi thích hợp. Chỉ giới thiệu công cụ và quy tắc vẫn áp dụng hiện nay; những flags cũ hoặc hack nội bộ không được xem là cách kiểm chứng chính.

## 2. Định nghĩa rõ “tương thích” trước khi chọn công cụ

### 2.1. Compile JDK, target release và runtime JDK

| Thành phần | Nó quyết định điều gì? | Ví dụ |
| --- | --- | --- |
| **Build JVM** | JVM đang chạy Maven/Gradle/plugins | JDK 24 |
| **Compiler JDK / toolchain** | `javac` thực sự dùng để biên dịch source | JDK 24 |
| **Language/API target** | Cú pháp và Java SE APIs được cho phép | `--release 11` |
| **Output classfile** | Major/minor version của bytes đã tạo | Major 55 |
| **Dependency bytecode** | Version các class của thư viện được nạp | Có thể là 55, 61, 65... |
| **Runtime JVM** | JVM thực chạy ứng dụng/đơn vị triển khai | JDK 11 |
| **Instrumentation JVM/tools** | Agent/compiler plugin xử lý classfile với khả năng riêng | JaCoCo/ASM/Byte Buddy phiên bản tương thích |

Những số này **không tự động trùng nhau**. Dùng Maven trên JDK 24 nhưng xuất Java 11 bytecode là một cấu hình hợp lệ. Nhưng nếu deployment chỉ có **JRE/JDK 11**, runtime vẫn phải đọc được **mọi class mà nó nạp**, kể cả thư viện và mã sinh.

**Không nhầm “Maven chạy trên JDK 24” thành “ứng dụng bắt buộc Java 24”**, hoặc “sourceCompatibility=11” thành “mọi dependency chạy được trên Java 11”.

### 2.2. Các cấp độ xác minh

| Kết quả kiểm tra | Đã chứng minh | Chưa chứng minh |
| --- | --- | --- |
| `javac --release 11` thành công | Source không dùng Java SE API/cú pháp sau Java 11 mà compiler kiểm tra được | Dependencies và runtime reflection/linkage đều an toàn |
| `javap -verbose` báo major 55 | Một classfile có format Java 11 | Runtime APIs, tất cả class khác và behavior đều đúng |
| `jdeps --jdk-internals` không có cảnh báo | Không phát hiện static dependencies tới JDK internals trong phạm vi quét | Không có reflection, dynamic class loading hay mọi API lỗi |
| Dependency tree đã resolve | Biết artifact và versions được lựa chọn | Mọi artifact compatible/security-safe |
| Maven/Gradle build xanh | Build tasks đã chạy thành công | Ứng dụng chạy tốt trên Java 11, nếu tests chỉ chạy JDK mới |
| Test thật bằng JDK 11 thành công | Những code paths trong tests chạy trên JVM 11 | Mọi integration path, OS/native dependency, cấu hình prod đều đúng |

**Chiến lược đúng là nhiều lớp kiểm tra, không phải chọn một lệnh duy nhất.**

## 3. Classfile version: dấu hiệu đầu tiên cần đọc

### 3.1. Mapping thường gặp

Java classfile lưu `major_version` và `minor_version` trong header sau magic bytes `CAFEBABE`.

| Java release | Classfile major |
| --- | ---: |
| Java 8 | 52 |
| Java 9 | 53 |
| Java 10 | 54 |
| **Java 11** | **55** |
| Java 17 | 61 |
| Java 21 | 65 |
| Java 24 | 68 |
| Java 25 | 69 |

Công thức `major = release + 44` dùng cho những Java release hiện đại trong bảng, nhưng khi phân tích file thật cần dùng tool chuẩn thay vì suy đoán từ tên artifact.

Ví dụ:

```bash
javap -verbose ApiCheckDemo
```

Đầu ra trọng tâm với class biên dịch theo Java 11:

```text
major version: 55
```

Lưu ý: `javap` đọc **một class được chỉ định**. Nếu một JAR có 500 class, việc kiểm tra riêng main class **không chứng minh** cả 500 class đều có major ≤55. Phải kiểm tra tất cả những class có thể được nạp trong runtime Java 11, đặc biệt là các thư viện transitively resolved và mã được tạo/biến đổi sau compilation.

### 3.2. Khi gặp UnsupportedClassVersionError

Nếu runtime Java 11 gặp classfile major 61 (Java 17), lỗi thường ở dạng:

```text
java.lang.UnsupportedClassVersionError:
  ... has been compiled by a more recent version of the Java Runtime
```

Đây là **mẫu lỗi minh họa**, không phải exception đã cố tình chạy trên JDK 11 trong bài test. Nó xảy ra khi JVM không hỗ trợ version class mà nó cần nạp.

**Cách chẩn đoán:**

1. Ghi chính xác tên class từ exception.
2. Tìm JAR thực đang cung cấp class đó trên runtime classpath/module path.
3. Kiểm tra bằng `javap -verbose -classpath library.jar package.ClassName`.
4. So version classfile với runtime JDK đã triển khai.
5. Chọn **bản thư viện còn hỗ trợ Java 11** hoặc thay runtime target theo chính sách ứng dụng.
6. Không chỉnh sửa hai byte major trong classfile bằng hex editor để “ép chạy”. Bytecode có thể dùng features/APIs không có trên Java 11.

### 3.3. Minor version và preview features

Những classfile dùng preview features có thể mang **minor version đặc biệt** và yêu cầu đúng JDK release/preview mode tương ứng. Một file major 55 với yêu cầu đặc biệt không có nghĩa nó tự động hợp lệ trên mọi Java 11 runtime.

**Đừng chỉ đọc major number rồi bỏ qua minor version và các classfile attributes.** Kiểm tra bằng `javap -verbose` và, nếu cần, một bytecode parser được bảo trì. Không dùng preview features làm chuẩn tương thích Java 11 production nếu chính sách deployment không hỗ trợ.

## 4. Compiler: vì sao phải dùng --release 11?

### 4.1. Source và target không kiểm tra đầy đủ API chuẩn

Trong `javac`:

- `-source 11`: giới hạn **cú pháp Java source** theo mức 11.
- `-target 11`: yêu cầu tạo classfile tương ứng Java 11.
- `--release 11`: giới hạn **cú pháp, classfile target và các Java SE platform APIs được Java 11 công bố**.

Lệnh nên dùng khi compile bằng JDK mới nhưng muốn hỗ trợ Java 11:

```bash
javac --release 11 ApiCheckDemo.java
```

**Không cần** bổ sung `-source 11` hay `-target 11` vào cùng lệnh; `--release` đã mang đủ ngữ nghĩa liên quan. Các flag cấu hình khác như `-encoding UTF-8` vẫn có ích khi muốn kiểm soát encoding.

### 4.2. Counterexample thật: source/target 11 vẫn dùng API Java mới

Tạo file **`TooNewApi.java`**:

```java
import java.util.stream.Stream;

public class TooNewApi {
    public static void main(String[] args) {
        System.out.println(Stream.of("a", "b").toList().size());
    }
}
```

`Stream.toList()` chỉ có từ **Java 16**, không thuộc Java 11 standard library.

Trên JDK 24, lệnh:

```bash
javac -Xlint:-options -source 11 -target 11 TooNewApi.java
javap -verbose TooNewApi
```

**Đã kiểm chứng:** compile thành công và `javap` vẫn cho:

```text
major version: 55
```

Điều đó có nghĩa compiler đã tạo **bytecode Java 11** chứa lời gọi tới một API **không có trong Java 11**. `-Xlint:-options` ở đây chỉ tắt cảnh báo command-line options trong ví dụ so sánh; **không khuyến nghị tắt warnings trong dự án thật**.

Nếu thay bằng:

```bash
javac --release 11 TooNewApi.java
```

Compiler JDK 24 **đã từ chối**, với phần chẩn đoán:

```text
TooNewApi.java:4: error: cannot find symbol
        System.out.println(Stream.of("a", "b").toList().size());
                                              ^
  symbol:   method toList()
  location: interface Stream<String>
1 error
```

**Kết luận:** major version 55 **không tự chứng minh class chỉ gọi các API Java 11**. Phải biên dịch source với `--release 11` hoặc kiểm tra theo phương pháp tương đương có ràng buộc platform API.

### 4.3. Một số bẫy khác khi target Java 11

- `String.isBlank()`, `String.strip()`, `Files.readString/writeString`, `Optional.isEmpty()` và `java.net.http.HttpClient` là API Java 11, dùng được.
- `Stream.toList()` (Java 16), `String.formatted()` (Java 15) và nhiều API hiện đại khác **không** dùng được khi target Java 11.
- `var` cho biến cục bộ đã có từ Java 10, có thể dùng trong Java 11; **không** suy ra mọi feature Java 17+ đều có.
- Source compiler có thể kiểm tra APIs chuẩn nhưng **không tự kiểm tra tuổi của third-party API**.
- Annotation processors, source generators, compiler plugins có thể dùng JDK APIs mới ngay cả khi **mã đích** là Java 11. Phải phân biệt **build-time JDK** và **runtime JDK**.

## 5. Chương trình chuẩn Java 11 đã biên dịch/chạy thật

Tạo file **`ApiCheckDemo.java`**:

```java
import java.net.http.HttpClient;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Optional;

public class ApiCheckDemo {
    public static void main(String[] args) throws Exception {
        Path temp = Files.createTempFile("api-check-", ".txt");
        try {
            Files.writeString(temp, "  Java 11  ");
            String text = Files.readString(temp);
            boolean works = text.strip().equals("Java 11")
                    && " \t".isBlank()
                    && Optional.empty().isEmpty()
                    && HttpClient.newHttpClient() != null;

            if (!works) {
                throw new AssertionError("API check failed");
            }
            System.out.println("Java 11 APIs = OK");
        } finally {
            Files.deleteIfExists(temp);
        }
    }
}
```

Chương trình dùng `String.strip/isBlank`, `Files.readString/writeString`, `Optional.isEmpty` và `HttpClient`; không gọi network. `try/finally` dọn tệp tạm ngay cả khi có exception.

```bash
javac --release 11 ApiCheckDemo.java
java ApiCheckDemo
javap -verbose ApiCheckDemo
```

**Đầu ra chính đã kiểm chứng trên JDK 24 khi biên dịch `--release 11`:**

```text
Java 11 APIs = OK
major version: 55
```

Hai dòng trên là **trích kết quả từ hai công cụ khác nhau**, không phải hai dòng stdout liên tiếp của một lệnh. `java` in dòng thứ nhất; `javap` cung cấp dòng major version trong output dài hơn.

**Giới hạn kiểm thử:** chạy chương trình trên **JDK 24** với target Java 11 **chưa phải thử nghiệm chạy trên JVM Java 11 thật**. CI vẫn cần job dùng JDK 11 nếu production hoặc thư viện tuyên bố hỗ trợ runtime này.

## 6. Maven: kiểm tra compiler plugin và release thực sự

### 6.1. Một POM Maven 3 rõ ràng

Ví dụ **`pom.xml`** dùng Maven 3, cấu hình compiler release rõ ràng:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>edu.example</groupId>
  <artifactId>api-check</artifactId>
  <version>1.0.0</version>
  <properties>
    <maven.compiler.release>11</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>
  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.16.0</version>
      </plugin>
    </plugins>
  </build>
</project>
```

**Phiên bản `maven-compiler-plugin 3.16.0` có trong tài liệu chính thức tại thời điểm viết**. Đây là POM Maven 3 được kiểm thử với Maven **3.9.12**, JDK **24.0.2**: đặt một source Java 11 tối giản tại `src/main/java/ApiCheckDemo.java`, chạy:

```bash
mvn -B -q -DskipTests package
java -cp target/classes ApiCheckDemo
javap -verbose -classpath target/classes ApiCheckDemo
```

**Kết quả kiểm thử Maven:**

```text
Maven release 11 = OK
major version: 55
MAVEN CHECKS PASSED
```

Chương trình tối giản trong phép thử Maven chỉ dùng `String.isBlank` và in dòng `Maven release 11 = OK`, khác với demo nhiều API ở mục 5. Dòng `MAVEN CHECKS PASSED` là thông báo từ script kiểm thử sau khi xác minh compile và major version, không phải từ Maven plugin.

**Không cần chỉ định một version plugin khác theo thói quen khi nâng JDK:** luôn tra release notes/plugin system requirements cho Maven/JDK hiện tại, rồi pin version phù hợp. Maven Compiler Plugin dòng 4.x có cấu hình mới cho Maven 4; **không đem cấu trúc Maven 4 thay nguyên vào POM Maven 3**.

### 6.2. property release và plugin declaration

`<maven.compiler.release>11</maven.compiler.release>` truyền target release cho Compiler Plugin tương thích. Có thể cấu hình ngay trên plugin:

```xml
<configuration>
  <release>11</release>
</configuration>
```

Đây là **mảnh POM**, phải đặt trong phần `maven-compiler-plugin` hợp lệ. Nếu có parent POM/profile/module configuration override, phải kiểm tra **effective POM** chứ không chỉ đọc một file con.

**Nên xác minh bằng:**

```bash
mvn -version
mvn -B help:effective-pom
mvn -B -DskipTests package
javap -verbose -classpath target/classes ApiCheckDemo
```

`mvn -version` cho biết **Java runtime của Maven**. Nó **không tự chứng minh compiler dùng đúng JDK target**, nhất là khi project đã cấu hình Maven toolchains, forked compiler hay parent plugins.

`help:effective-pom` cho biết cấu hình có hiệu lực sau inheritance/profiles/plugin management. Nhưng **effective POM không thay thế kiểm tra bytes cuối cùng**.

### 6.3. Compiler plugin và Maven toolchains

Maven có thể chạy trên một JDK, trong khi compiler sử dụng JDK từ **toolchain**. Điều này hữu ích khi:

- Maven hoặc một plugin cần JDK mới để chạy.
- Ứng dụng phải build/test cho Java 11.
- CI có nhiều JDK side by side.
- Muốn tách build JVM khỏi JVM được dùng bởi một plugin cụ thể.

Cần đối chiếu **Maven Toolchains Plugin**, file toolchains/config của CI, `maven-compiler-plugin` và các task test. `maven.compiler.release` chỉ ràng buộc output của compiler, **không tự điều khiển JVM chạy integration tests hoặc sản phẩm**.

Không tự hardcode một đường dẫn JDK cục bộ vào POM rồi cho rằng mọi CI/developer đều dùng được. Dùng toolchains hoặc environment configuration có kiểm soát.

### 6.4. Kiểm tra Maven dependency graph

Các lệnh hữu ích:

```bash
mvn -B dependency:tree
mvn -B dependency:tree -Dscope=runtime
mvn -B dependency:analyze
```

- `dependency:tree` cho thấy dependency paths, versions, scope và phụ thuộc bắc cầu được Maven lựa chọn.
- `-Dscope=runtime` giúp tập trung vào dependencies trên runtime path, nhưng test/compile/plugin paths có thể cần kiểm tra riêng.
- `dependency:analyze` hỗ trợ nhận diện trường hợp dùng dependencies không khai báo trực tiếp hoặc khai báo mà không dùng, dựa trên phân tích bytecode; **không phát hiện mọi dynamic/reflection usage**.

Maven giải quyết xung đột version theo dependency mediation (thường dùng **nearest definition**, với quy tắc hòa khi cùng độ sâu), `dependencyManagement` và BOM có thể ảnh hưởng phiên bản. Không chỉ nhìn dòng `<dependency>` trực tiếp rồi bỏ qua graph đã resolve.

**Một trường hợp thường gặp:** thư viện A và B cùng phụ thuộc thư viện C ở các version khác nhau. Build có thể xanh nhưng runtime gọi method chỉ tồn tại trong version C khác, dẫn tới `NoSuchMethodError` hoặc `NoSuchFieldError`. Cần xem **version C thực sự được chọn**, không suy diễn version từ POM của A.

### 6.5. Dependency không giống plugin dependency

Maven có nhiều classpaths:

| Nơi khai báo | Vai trò |
| --- | --- |
| `<dependencies>` trong project | Library của source/tests và runtime tùy scope |
| `<dependencyManagement>` | Quản lý versions/scopes theo mô hình Maven, không tự thêm dependency |
| `<build><plugins>` | Build plugins chạy trong Maven |
| `<pluginManagement>` | Quản lý cấu hình/phiên bản plugin, không tự có nghĩa mọi plugin đều được thực thi |
| `annotationProcessorPaths` hoặc cơ chế processor mới tương ứng | Classpath của annotation processors/compiler extensions |
| Surefire/Failsafe test providers | Thành phần test execution và JVM chạy tests |

Ví dụ Lombok hoặc một annotation processor có thể cần cập nhật để chạy trên **compiler JDK 24**, dù source project nhắm Java 11; nó **không nhất thiết** là thư viện cần xuất hiện trong runtime artifact.

Khi xảy ra lỗi `IllegalAccessError` trong annotation processor, phải kiểm tra **processor version và build JDK internals**, không lập tức kết luận ứng dụng Java 11 code sai.

## 7. Gradle: toolchain, options.release và dependencyInsight

### 7.1. Cấu hình Gradle Kotlin DSL đã được kiểm thử

Ví dụ **`build.gradle.kts`** với Gradle hiện đại:

```kotlin
plugins {
    java
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(24)
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(11)
}
```

Và **`settings.gradle.kts`**:

```kotlin
rootProject.name = "toolchain-demo"
```

**Đây là cấu hình đã kiểm thử** với Gradle **9.2.1** và Java toolchain **24** được cài tại máy thử. Project có `src/main/java/ToolchainDemo.java`:

```java
public class ToolchainDemo {
    public static void main(String[] args) {
        if (!"  Java 11  ".strip().equals("Java 11")) {
            throw new AssertionError("Invalid Java 11 API");
        }
        System.out.println("Gradle release 11 = OK");
    }
}
```

Chạy `gradle --no-daemon -q classes`, rồi `java -cp build/classes/java/main ToolchainDemo` và `javap -verbose -classpath build/classes/java/main ToolchainDemo` cho kết quả:

```text
Gradle release 11 = OK
major version: 55
GRADLE CHECKS PASSED
```

Dòng cuối là thông báo từ script kiểm thử sau khi kiểm tra bytecode, không phải output của Java class.

**Tại sao toolchain là 24 nhưng release là 11?** Gradle chọn **JDK 24 để compile**, còn compiler được yêu cầu phát Java 11 bytecode và kiểm tra Java 11 platform APIs. Nếu project có toolchain JDK 17 hoặc 21, có thể chọn phiên bản phù hợp đã cài/được cấp phát, nhưng vẫn giữ `options.release.set(11)` khi cần target Java 11.

**Cực kỳ quan trọng:** build Gradle trên JDK 24 **không chứng minh** runtime Java 11 hoạt động. Gradle itself có thể yêu cầu JVM mới hơn Java 11; hãy dùng job CI riêng hoặc cấu hình test launcher với JDK 11 để chạy app/tests theo target thật.

### 7.2. Gradle wrapper và reproducibility

Trong dự án có Gradle wrapper, sử dụng:

```bash
./gradlew --version
./gradlew clean test
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency example-library --configuration runtimeClasspath
./gradlew -q javaToolchains
```

`example-library` ở lệnh `dependencyInsight` là **tên thư viện cần điều tra**, phải thay bằng dependency thực trong dự án; nó không phải một artifact đặc biệt của Gradle.

Trên Windows PowerShell/`cmd`, lệnh wrapper thường là `gradlew.bat` thay vì `./gradlew`.

Dùng **Gradle wrapper** để pin Gradle distribution của dự án; không phụ thuộc máy dev có bản Gradle global nào. Đặc biệt, khi plugin yêu cầu Gradle/JDK mới, wrapper version và JDK chạy daemon là hai thông tin cần kiểm tra riêng.

### 7.3. Compile classpath, runtime classpath và processor classpath

Gradle Java plugin có những configurations khác nhau:

- `implementation`: dependencies cần cho source; thường tham gia runtime của component.
- `api` (với `java-library` plugin): public API dependencies được export đến downstream consumers theo semantics của Gradle.
- `compileOnly`: compile có thể dùng nhưng runtime không tự có; cần đặc biệt cẩn thận nếu ứng dụng thật cần class đó.
- `runtimeOnly`: chỉ có ở runtime, ví dụ JDBC driver.
- `testImplementation`/`testRuntimeOnly`: dependencies cho tests.
- `annotationProcessor`: classpath của Java annotation processors, **khác** với application runtime.
- `compileClasspath` và `runtimeClasspath`: **resolved** graphs để kiểm tra, không chỉ những dependency được khai báo trực tiếp.

Nếu `./gradlew classes` xanh nhưng `./gradlew test` hoặc runtime thất bại, kiểm tra **khác biệt giữa compileClasspath và runtimeClasspath**. Một dependency bị bỏ khỏi runtime, chọn version khác hoặc nằm nhầm `compileOnly` đều có thể là nguyên nhân.

### 7.4. Phân tích conflict với dependencyInsight

```bash
./gradlew dependencyInsight --dependency jackson-databind --configuration runtimeClasspath
```

Đây là **lệnh minh họa để tìm dependency có tên jackson-databind** trong dự án nào dùng Jackson. `dependencyInsight` giải thích **đường phụ thuộc và lý do chọn phiên bản**, bao gồm version conflicts và constraints.

Đừng giả định Gradle luôn có cơ chế mediation giống Maven. Gradle hỗ trợ rich versions, platforms/BOMs, constraints, capabilities và resolution strategies; phải đọc **actual resolution result**.

### 7.5. Locking và verification

Khi reproducibility và supply-chain security quan trọng, Gradle cung cấp:

```kotlin
dependencyLocking {
    lockAllConfigurations()
}
```

Đoạn trên là **mảnh cấu hình** cần nằm trong `build.gradle.kts` phù hợp. Các lệnh tạo/cập nhật lock state:

```bash
./gradlew dependencies --write-locks
```

Sau khi review dependency graph, commit lockfiles và bảo đảm CI kiểm tra graph được resolve. Tránh sử dụng không kiểm soát các dynamic versions như `1.+` hoặc changing snapshots trong build phát hành.

Gradle còn có cơ chế **dependency verification** bằng checksum/signature với `gradle/verification-metadata.xml`; điều này hỗ trợ phát hiện artifact thay đổi trái kỳ vọng, **không** tự chứng minh artifact tương thích Java 11 hoặc không có CVE.

## 8. Bẫy lớn: --release 11 không kiểm tra bytecode của third-party JAR

### 8.1. Thí nghiệm với một thư viện Java 17

Tạo file **`NewLibrary.java`**:

```java
package libpkg;

public class NewLibrary {
    public static String version() {
        return "Compiled as Java 17";
    }
}
```

Tạo file **`DependsOnNewLibrary.java`**:

```java
public class DependsOnNewLibrary {
    public static void main(String[] args) {
        System.out.println(libpkg.NewLibrary.version());
    }
}
```

Biên dịch thư viện thành classfile Java 17 rồi đóng gói:

```bash
javac --release 17 -d libout NewLibrary.java
jar --create --file newlib.jar -C libout .
javap -verbose -classpath newlib.jar libpkg.NewLibrary
```

**Đã kiểm chứng:** class trong `newlib.jar` có:

```text
major version: 61
```

Tiếp theo biên dịch ứng dụng tham chiếu thư viện đó, nhưng yêu cầu Java 11:

```bash
javac --release 11 -cp newlib.jar DependsOnNewLibrary.java
javap -verbose DependsOnNewLibrary
```

Trên **JDK 24**, `javac` **vẫn biên dịch thành công**; class ứng dụng có:

```text
major version: 55
```

**Vì sao compiler chấp nhận?** `--release 11` kiểm tra source, cú pháp và **Java SE platform API** ở Java 11, nhưng nó không tự yêu cầu mọi class trên **user classpath** có major ≤55. Compiler chạy JDK 24 có thể đọc bytecode major 61 của third-party JAR. Khi JVM Java 11 thật nạp `libpkg.NewLibrary` major 61, nó sẽ gặp lỗi compatibility.

**Đây là kết quả kiểm thử biên dịch, không phải claim đã chạy trên JVM Java 11**; môi trường thử sử dụng JDK 24. Cơ chế Java 11 từ chối major 61 được xác định bởi JVM classfile compatibility.

### 8.2. Checklist sau thí nghiệm

- Kiểm tra **tất cả direct và transitive JARs**, không chỉ `target/classes` hoặc `build/classes`.
- Kiểm tra các class trong `BOOT-INF/lib`, `WEB-INF/lib`, shaded/fat JAR hoặc container runtime image tùy cách đóng gói.
- Đọc release notes và minimum Java version của dependency.
- Kiểm tra **các module runtime-only** không được load trong unit tests.
- Chạy smoke/integration tests bằng **JDK 11 thật** nếu đó là runtime đích.
- Nếu build có bytecode post-processing/obfuscation, kiểm tra **artifact cuối**, không chỉ output của `javac`.
- Kiểm tra cả source generators, annotation processors và instrumentation agents với JDK dùng để build/test.

Đừng sửa major 61 thành 55 bằng cách patch bytecode header. Java 17 class có thể sử dụng format, API và semantics Java 11 không hỗ trợ.

## 9. Dùng javap, jar và jdeps đúng mục đích

### 9.1. javap: xem classfile, method descriptors và instructions

Các lệnh thường dùng:

```bash
javap -verbose -classpath newlib.jar libpkg.NewLibrary
javap -c -p -classpath newlib.jar libpkg.NewLibrary
javap -v ApiCheckDemo
```

- `-verbose` / `-v`: thấy classfile major/minor, constant pool, methods, attributes, module/nest metadata khi có.
- `-c`: disassemble bytecode instructions.
- `-p`: gồm cả private members.
- `-classpath`: chọn đúng JAR/class directory, tránh vô tình dùng một class trùng tên từ nơi khác.

**Đừng đọc output `javap` rồi suy ra full runtime behavior.** Reflection, native calls, configuration-driven class loading, invokedynamic bootstrap và service loading có thể không hiển thị đầy đủ như static call graph.

Nếu gặp `NoSuchMethodError`, hãy dùng `javap -p -s -classpath selected.jar package.Class` để xem **method name + descriptor thực**, bao gồm tham số/return type; một method có tên giống nhưng descriptor khác vẫn có thể không tương thích binary.

### 9.2. jar: kiểm tra những gì thật sự được đóng gói

```bash
jar --list --file newlib.jar
jar --describe-module --file newlib.jar
```

`jar --list` (tương đương `jar tf`) cho thấy entries; dùng để xác minh có đúng `.class`, service metadata, manifest, versioned classes và dependencies đã dự kiến không.

`jar --describe-module` giúp xem module descriptor hoặc thông tin automatic module suy ra theo trường hợp. **Một JAR không có module-info.class vẫn có thể được dùng ở classpath**, và khi đặt trên module path có quy tắc automatic module; kiểm tra behavior thực tế.

Một class trên build classpath không tự đồng nghĩa nó sẽ có trong fat JAR hoặc deployment container. Với Spring Boot/repackaged JAR hay shaded assemblies, hãy kiểm tra **artifact sau packaging** bằng tool thích hợp.

### 9.3. jdeps: đồ thị phụ thuộc static và JDK internals

Ví dụ:

```bash
jdeps --multi-release 11 --jdk-internals app11.jar
jdeps --multi-release 11 --summary app11.jar
jdeps --multi-release 11 --verbose:class app11.jar
```

`jdeps` giúp xem **static class/module dependencies** trong bytecode và phát hiện tham chiếu tới một số **internal JDK APIs**. Với các dependencies bên ngoài, cung cấp đúng `--class-path` hoặc `--module-path` để phân giải, ví dụ:

```bash
jdeps --multi-release 11 --class-path newlib.jar --summary app11.jar
```

Trong thử nghiệm, `jdeps --multi-release 11 --jdk-internals app11.jar` chạy thành công và không phát hiện JDK internal reference trong ứng dụng mẫu.

**Cảnh báo quan trọng:**

- `--multi-release 11` quy định **cách chọn phiên bản class trong multi-release JAR**, **không** phải một kiểm tra rằng tất cả class chỉ dùng Java 11 APIs.
- `--jdk-internals` chỉ tìm những **static references** mà tool nhận biết. Dùng reflection/string-based class loading có thể không xuất hiện.
- `jdeps` không thực thi chương trình; không chứng minh startup, service loading hay module access thành công.
- Nếu có lỗi missing dependency, thêm classpath/module path đúng thực tế trước khi kết luận application binary bị hỏng.
- `--print-module-deps` hữu ích khi chuẩn bị runtime image `jlink`, nhưng không bảo đảm mọi dynamic modules được sử dụng đều đã xuất hiện trong graph tĩnh.

### 9.4. jdeprscan: tìm Java SE APIs bị deprecated

```bash
jdeprscan --release 11 app11.jar
```

`jdeprscan` đọc bytecode và báo usages của APIs được đánh dấu deprecated theo tập APIs của release chọn. Thử nghiệm với ứng dụng mẫu chạy thành công; tool in thông tin JAR và không báo API deprecated.

Có thể kết hợp compiler warnings:

```bash
javac --release 11 -Xlint:deprecation ApiCheckDemo.java
```

**Không nhầm deprecated với removed**: có API deprecated mà Java 11 vẫn hỗ trợ; có API bị loại ở các JDK mới; có internal APIs không được đảm bảo tương thích. `jdeprscan` **không** phải dependency vulnerability scanner, bytecode major checker hay test đảm bảo runtime compatibility.

### 9.5. Bảng chọn tool

| Tool | Trả lời tốt | Không trả lời hoàn toàn |
| --- | --- | --- |
| `javac --release 11` | Source có tuân Java 11 platform APIs/cú pháp không | Third-party JAR version |
| `javap -verbose` | Major/minor, attributes, constant pool, method signatures của class | Toàn bộ dependency graph/runtime |
| `jar --list` | Artifact chứa entries nào | API compatibility của các class |
| `jdeps` | Static dependencies, JDK internals, module graph | Reflection/dynamic loading/đầy đủ API compatibility |
| `jdeprscan` | Static references đến deprecated JDK APIs trong phạm vi quét | Mọi API sẽ thất bại trên runtime |
| Maven `dependency:tree` | Resolved dependency graph theo scopes | Classfile major và Java 11 runtime behavior |
| Gradle `dependencies/dependencyInsight` | Selected versions và đường dependency | Đầy đủ binary compatibility |
| Test trên JDK 11 | Behavior của code paths thực thi | Mọi code path chưa test |
| ASM/Byte Buddy/JaCoCo | Đọc/biến đổi/instrument bytecode | Tương thích Java đích nếu không kiểm tra version/tool |

## 10. Multi-release JAR: cùng tên class nhưng nhiều implementations

Từ Java 9, **multi-release JAR** có thể chứa class phiên bản cơ sở và các variant đặt dưới `META-INF/versions/<release>/` với manifest `Multi-Release: true`.

Ví dụ cấu trúc:

```text
multi-release-library.jar
  META-INF/MANIFEST.MF
  com/example/Feature.class             // Base implementation
  META-INF/versions/11/com/example/Feature.class
  META-INF/versions/17/com/example/Feature.class
```

**Java 11 runtime** cần chọn một entry phù hợp theo quy tắc multi-release, không tự chạy variant Java 17 chỉ vì JAR chứa nó. Vì thế:

- **Đừng tự động đánh dấu mọi multi-release JAR là không hỗ trợ Java 11** khi thấy thư mục `versions/17`.
- Nhưng **base/versions ≤11 phải hợp lệ** và có những classes cần thiết trên runtime Java 11.
- Kiểm tra `Multi-Release: true` trong manifest; nếu thiếu, layout `versions` có thể không có semantics runtime như kỳ vọng.
- Khi dùng `jdeps --multi-release 11`, tool chọn view tương ứng Java 11 cho quá trình phân tích multi-release JAR.
- Nếu build tool shade/repackage JAR, cần bảo toàn hoặc xử lý đúng manifest và versioned entries; sai manifest có thể làm runtime nạp implementations khác với ý định.

**Thử nghiệm runtime Java 11 là bằng chứng quan trọng** khi phụ thuộc nhiều vào multi-release packaging hoặc các thư viện có native components.

## 11. Plugin biên dịch, annotation processors và generated code

Các tool “chạy trong build” có những vấn đề tương thích **khác** với thư viện runtime.

### 11.1. Java compiler plugin

Maven `maven-compiler-plugin` và Gradle JavaCompile phải:

- Được hỗ trợ bởi **Maven/Gradle version hiện tại**.
- Có thể chạy trên **JDK dùng để build**.
- Truyền đúng `--release 11` hoặc cấu hình tương đương.
- Có compile settings nhất quán cho main/test/generated source sets.
- Không bị parent POM, Gradle convention plugins hay CI overrides vô tình đổi target.
- Khi dùng toolchains, phải biết JDK **thực** dùng cho từng compilation task.

**Kiểm tra cả test compiler**. Nếu main code compiled Java 11 nhưng test code hoặc helper artifacts compiled Java 21, những helper đó có thể thất bại khi tests được chạy trên Java 11.

### 11.2. Annotation processors

Các công cụ như Lombok, MapStruct, Dagger, QueryDSL code generators hoặc custom processors có thể tạo source và classfiles trong build.

Cần kiểm tra:

1. Processor version có hỗ trợ **compiler JDK đang chạy** không?
2. Processor có phụ thuộc `com.sun.tools.javac` internals bị thay đổi qua JDK không?
3. Processor được đặt vào **annotation processor classpath** hay bị kéo lẫn vào runtime một cách không cần thiết?
4. Generated Java có dùng API chỉ có trên JDK mới, dù source chính đang target 11 không?
5. Có bước post-compile transform nào tạo major version cao hơn 55 không?

Khi annotation processor báo lỗi Java module access hoặc missing field từ compiler internals, đừng giải quyết bằng `--add-opens` vĩnh viễn rồi coi là tương thích. Trước tiên kiểm tra version processor/plugin được duy trì và hỗ trợ JDK build.

### 11.3. Shading/relocation, obfuscation và bytecode post-processors

Một project có thể:

```text
Java source
   -> javac --release 11
   -> classes major 55
   -> enhancement / shading / instrumentation / obfuscation
   -> packaged JAR / container
```

Nếu tool post-processor thay classfile format, thêm methods gọi API mới hoặc đóng gói dependency Java 17, **artifact sau cùng** có thể không còn chạy được Java 11.

Vì vậy cần chạy `javap`, dependency scan và runtime smoke test trên **final artifact**, không chỉ trên `target/classes` hay `build/classes` trước biến đổi.

## 12. ASM, Byte Buddy, JaCoCo: đọc và biến đổi bytecode đúng version

### 12.1. ASM

**ASM** là thư viện phổ biến để đọc/ghi classfile, phân tích methods và tạo bytecode. Khi một JDK mới ra mắt, các classfile attributes/tags/major versions có thể yêu cầu ASM version được bảo trì tương ứng.

Ví dụ features Java 11 ở classfile:

- **NestHost / NestMembers** (nest-based access).
- **`CONSTANT_Dynamic`** (condy).
- Classfile **major 55**.

Nếu tool cũ không hiểu attributes hoặc constant-pool tags, lỗi có thể là:

```text
java.lang.IllegalArgumentException: Unsupported class file major version ...
```

Đây là **mẫu lỗi**, số major phụ thuộc classfile thực. Không suy ra chỉ đổi compiler `--release 11` sẽ sửa được mọi tooling incompatibility. Hãy kiểm tra **ASM version được dùng trực tiếp lẫn version transitively bundled bên trong plugin**; nhiều plugins relocate/shade ASM nên `dependency:tree` của project có thể không hiển thị một bản ASM bên trong plugin JAR.

### 12.2. Byte Buddy

**Byte Buddy** tạo hoặc biến đổi classes ở compile time/runtime thông qua agents, proxies và frameworks. Các thư viện mocks, agents hoặc observability có thể dùng Byte Buddy nội bộ.

Cần kiểm tra:

- Byte Buddy version hỗ trợ **JDK chạy agent** và **major version classfiles mà agent sẽ đọc**.
- Target classfile có hợp lệ với Java 11 runtime không.
- Module encapsulation, `Instrumentation`/agent attachment và permissions phù hợp.
- Có dùng Java APIs/bytecode features quá mới cho Java 11 không.
- Sau transformation, class thật có thể nạp và verify trên runtime mục tiêu.

Không chọn một bản Byte Buddy thật cũ chỉ vì code source chỉ dùng Java 11 syntax; cách agent đọc lớp JDK mới có thể yêu cầu bản thư viện khác.

### 12.3. JaCoCo

**JaCoCo** dùng agent/instrumentation để thu code coverage; nó thường phụ thuộc phiên bản **ASM** phù hợp với classfile mới.

Khi nâng JDK:

- Xem **JaCoCo release notes** để biết support matrix cho classfile versions.
- Kiểm tra version agent trong Maven/Gradle test task và plugin version tạo report.
- Không dùng coverage failure do major version không hỗ trợ làm bằng chứng source không hợp lệ.
- Chạy tests với đúng JDK và có thể kiểm tra riêng báo cáo coverage khi nâng.
- Nếu code có generated classes, Kotlin bytecode, records hoặc compiler-specific constructs, xem các filter/compatibility notes của bản JaCoCo đang dùng.

Theo release notes hiện hành, JaCoCo tiếp tục phát hành các bản mới để hỗ trợ classfiles mới. **Luôn tra bản được duy trì khi cấu hình**, thay vì khóa một bản quá cũ từ tutorial Java 8.

### 12.4. Công cụ xử lý bytecode của JDK mới

Các JDK hiện đại có thêm công cụ/API xử lý classfile, trong đó **`java.lang.classfile`** được chuẩn hóa trên JDK mới (từ JDK 24). Đây là API dành cho **môi trường JDK hỗ trợ nó**, **không phải Java 11 API** để sử dụng trong module runtime phải chạy trên Java 11.

Có thể dùng tool JDK 24+ để **phân tích** Java 11 classfile, nhưng bản thân chương trình tool gọi `java.lang.classfile` cần runtime hỗ trợ API đó.

**Đừng nhầm JDK chạy công cụ với JDK chạy ứng dụng đích.**

## 13. Các loại lỗi cần phân biệt

| Lỗi/triệu chứng | Nguyên nhân điển hình | Hướng điều tra |
| --- | --- | --- |
| `cannot find symbol: method ...` khi `--release 11` | Source gọi Java API sau release 11 hoặc thiếu dependency | Kiểm tra API since, `--release` và classpath |
| `UnsupportedClassVersionError` | Runtime không hiểu major/minor classfile | `javap -verbose` trên JAR thực; hạ version dependency hoặc nâng runtime có chủ đích |
| `NoSuchMethodError` | Method descriptor ở runtime khác với lúc compile; dependency version skew hoặc JDK API không có | Kiểm tra actual runtime JAR, `javap -s`, tree/insight |
| `NoSuchFieldError` | Field binary descriptor không còn đúng | So sánh classfile API của dependency compile/runtime |
| `NoClassDefFoundError` | Class không load được lúc runtime, có thể thiếu dependency hoặc lỗi khởi tạo | Đọc cause đầy đủ, runtime classpath/module path |
| `ClassNotFoundException` | Lookup động không tìm class | Kiểm tra classloader, reflection, resources, artifact packaging |
| `IllegalAccessError` | Class/method/field access không hợp lệ ở linkage runtime | Kiểm tra access, package/module exports, compiler/tool output |
| `InaccessibleObjectException` | Reflection bị JPMS encapsulation chặn | Cập nhật library/agent, kiểm tra `opens` và runtime policy |
| `ServiceConfigurationError` | ServiceLoader provider metadata/class không hợp lệ | Kiểm tra `META-INF/services`, providers, runtime dependencies |
| `Unsupported class file major version` từ ASM/plugin | Bytecode tool không hỗ trợ format class được phân tích | Nâng tool/plugin tương thích, không sửa bytes thủ công |
| Maven/Gradle compile xanh nhưng app startup lỗi | Chỉ kiểm tra source chính, không kiểm tra dependencies hoặc runtime path | Audit toàn graph và chạy trên runtime đích |
| Coverage agent crash khi nâng JDK | JaCoCo/ASM/agent support matrix chưa phù hợp | Nâng agent/plugin, đối chiếu release notes |
| Java plugin chạy JDK mới nhưng generated code lỗi | Annotation processor/compiler internals mismatch | Kiểm tra processor version, toolchain, output release |
| Test chỉ chạy JDK 24, production JDK 11 lỗi | Thiếu runtime compatibility job | Bổ sung test Java 11 thực tế |
| `jdeps --jdk-internals` sạch nhưng reflection lỗi | Static analyzer không thấy reflective accesses | Integration tests/runtime observability và module verification |
| Version conflict bắc cầu | Hai nhánh dependency chọn khác version mong muốn | Maven tree/Gradle insight, BOM/constraints, pin/lock và test |

**Đừng gộp mọi lỗi thành “Java 11 không hỗ trợ dependency”**. Phải phân biệt compiler error, classfile version, API linkage, missing class, module access, processor/agent incompatibility và configuration issues.

## 14. JPMS, classpath, module path và các dependency vô hình

Từ Java 9, **Java Platform Module System (JPMS)** có thể ảnh hưởng hành vi dependency loading.

- **Classpath:** cách truyền thống nạp JARs; không tự áp module readability/exports giống module path.
- **Module path:** dùng module descriptors/automatic modules, cần đánh giá `requires`, `exports`, `opens`.
- **JDK modules:** ví dụ `java.net.http` cung cấp HttpClient trong Java 11.
- **ServiceLoader:** dùng provider metadata và reflective/dynamic loading, có thể không hiện đầy đủ trong `jdeps` static graph.
- **Reflection frameworks:** dùng runtime lookup và có thể cần module opens được cấu hình chính đáng.

Các công cụ:

```bash
jar --describe-module --file app11.jar
jdeps --multi-release 11 --print-module-deps app11.jar
```

có ích để hiểu module info và graph tĩnh; không chứng minh mọi runtime/reflective usage đã có đủ quyền.

Đừng vội thêm `--add-opens ALL-UNNAMED` hàng loạt làm giải pháp lâu dài cho mọi lỗi. Cần kiểm tra dependency được bảo trì, API truy cập được hỗ trợ và security implications. Nếu dự án dùng reflection thật sự hợp lệ, cấu hình `opens` có chủ đích và test trên runtime thực tế.

## 15. Supply chain và version reproducibility

Kiểm tra version Java không chỉ có classfile. Dependency trực tiếp/transitive và build plugins **đều có thể thay đổi theo thời gian**, ảnh hưởng security và reproducibility.

### 15.1. Những gì cần giữ có thể tái lập

- **Pin Maven/Gradle versions** qua project wrapper/CI config.
- **Pin plugin versions** đã review, tránh phụ thuộc default plugin version ngầm.
- **Review direct và transitive dependencies**, kể cả runtime-only.
- **Kiểm soát BOMs, constraints, dependency management và lockfiles**.
- **Kiểm tra SHA-256/signatures** khi có cơ chế dependency verification.
- **Theo dõi CVEs và license policies** cho artifacts thực sự dùng.
- **Ghi rõ JDK vendor/version** của build/test/runtime.
- **Không tin blindly vào cached artifact** khi checksum/signature thay đổi; điều tra nguyên nhân.
- **Tạo SBOM** nếu quy trình yêu cầu theo dõi chuỗi cung ứng.

**Một dependency có major 55 vẫn có thể có lỗi bảo mật.** Ngược lại, một dependency mới an toàn về bảo mật nhưng major 61 vẫn không chạy được trên Java 11. Hai chiều kiểm tra cần kết hợp.

### 15.2. Vì sao tránh dynamic versions trong bản phát hành?

Ví dụ Gradle `1.+` hoặc Maven `-SNAPSHOT` có thể resolve code khác giữa hai lần build. Khi nâng dependency, các JAR bắc cầu, annotation processor hay bytecode agent có thể đổi mà developer không chú ý.

Version locking và verification giúp reproducibility, nhưng **không thay thế runtime Java 11 test**. Luôn review dependencies mới trước khi cập nhật lock/checksum.

## 16. CI checklist để tuyên bố hỗ trợ Java 11

Một workflow kiểm chứng nhiều lớp:

### Gate A — cấu hình và source

1. `mvn -version` hoặc `./gradlew --version`: ghi build JVM/tool version.
2. Xác nhận compiler plugin/task **thực sự** sử dụng `--release 11`; lưu cấu hình có hiệu lực.
3. Build toàn bộ modules, source sets và generated sources với target phù hợp.
4. Bật compiler warnings có ích: deprecation, unchecked, module-related warnings.
5. Không cho phép build chạy trôi theo một JDK trên máy developer không được định nghĩa trong CI.

### Gate B — resolved dependency graphs

1. Xuất Maven dependency tree hoặc Gradle runtimeClasspath/dependencyInsight.
2. Xác minh direct, transitive, compile/runtime/test/processor scopes.
3. Chọn phiên bản library còn hỗ trợ Java 11 ở **runtime**, không chỉ hỗ trợ JDK dùng để compile.
4. Kiểm tra conflict, duplicates, BOM/constraints và dependency lock.
5. Kiểm tra các artifact sau shade/repackage.

### Gate C — classfile và bytecode tools

1. Dùng `javap -verbose` kiểm tra output ứng dụng major 55.
2. **Quét các class cần load trong toàn bộ dependencies**, không chỉ main class.
3. Với multi-release JAR, phân tích view của Java 11, không báo nhầm `versions/17` là lỗi nếu Java 11 không load.
4. Dùng `jdeps --jdk-internals` và `jdeprscan --release 11` theo phạm vi phù hợp.
5. Kiểm tra ASM/Byte Buddy/JaCoCo/compiler plugin version hỗ trợ compiler JDK và classfile được xử lý.
6. Với generated/instrumented bytecode, kiểm tra artifact cuối cùng.

### Gate D — runtime Java 11 thật

1. Chạy unit tests và smoke startup trên một **JDK/JRE 11** đúng deployment environment.
2. Chạy integration tests với database, HTTP, TLS, serialization, reflection, ServiceLoader và agents được bật thực tế.
3. Đọc `UnsupportedClassVersionError`, `NoSuchMethodError`, module errors ngay lúc startup; đừng ignore.
4. Nếu hỗ trợ nhiều JVM vendors/OS/architectures, thêm matrix phù hợp chính sách.
5. Khi Java 11 chỉ còn là compatibility target của thư viện, kiểm tra cả consumer projects và published API signatures.

### Gate E — security và release

1. Review dependency/plugin updates, vulnerabilities, licenses, checksums.
2. Xác nhận versions/lockfiles/wrappers khớp artifact release.
3. Kiểm tra deployed classpath/module path, container image và Java runtime version **sau packaging**.
4. Ghi lại command, JDK, dependency graph và test result có thể tái lập.

**Một dòng CI “build xanh” không đủ để thay cả năm gates**. Với một thư viện công bố Java 11 minimum runtime, test Java 11 thực tế nên là điều kiện phát hành, không phải kiểm tra tùy chọn.

## 17. Ma trận kiểm chứng và cách đọc kết quả

| Trường hợp | Compile `--release 11` | App major | Lib major | Runtime Java 11 | Kết luận |
| --- | --- | ---: | ---: | --- | --- |
| Source chỉ dùng Java 11 API, dependencies tương thích | Thành công | 55 | ≤55 | Cần test thật | Có cơ sở để hỗ trợ |
| Source gọi `Stream.toList()` | **Bị từ chối** | Không tạo | — | — | Source dùng API sau Java 11 |
| Dùng `-source 11 -target 11` với `Stream.toList()` trên JDK 24 | **Không dùng --release; compile thành công** | 55 | — | Lỗi khi gọi API không có | Bytecode version không đủ |
| App `--release 11` nhưng library Java 17 | Thành công trên compiler JDK mới | 55 | 61 | **Không thể nạp lib major 61** | Sai compatibility dependency |
| Main class major 55 nhưng agent không hiểu JDK bytecode mới | App có thể compile | 55 | Tùy | Agent có thể fail | Kiểm tra bytecode tool |
| Multi-release JAR có variant 17 nhưng base/11 hợp lệ | Có thể thành công | 55 | Versioned | Cần test view Java 11 | Không đánh dấu sai từ variant 17 |

**Không dùng bảng này như kết quả test của một hệ thống chưa chạy.** Nó thể hiện logic kiểm chứng và phản ví dụ đã thử trong project mẫu.

## 18. Bài tập tự kiểm tra

**Câu 1.** Một file `.class` có major 55 có chắc không dùng API Java 17?  
**Đáp án:** Không. `-source 11 -target 11` trên JDK mới có thể sinh major 55 mà vẫn tham chiếu API xuất hiện sau Java 11.

**Câu 2.** Vì sao `--release 11` nên được ưu tiên?  
**Đáp án:** Nó ràng buộc language features, classfile version và **Java SE platform APIs** của Java 11.

**Câu 3.** `--release 11` có đảm bảo mọi dependency JAR major ≤55 không?  
**Đáp án:** Không. Thí nghiệm với Java 17 library major 61 được compiler JDK 24 chấp nhận dù app target major 55.

**Câu 4.** Muốn biết Maven thực sử dụng compiler plugin/release nào làm sao?  
**Đáp án:** Đọc effective POM, cấu hình toolchains và plugin version, rồi kiểm tra classfile output thật.

**Câu 5.** Muốn tìm nguyên nhân Gradle chọn một version transitive library nào?  
**Đáp án:** Dùng `dependencyInsight` với dependency và configuration đúng, đối chiếu `dependencies` và constraints/lock.

**Câu 6.** `mvn -version` chứng minh runtime ứng dụng là Java 11 không?  
**Đáp án:** Không. Nó cho biết JVM của Maven; app runtime và compiler toolchain có thể khác.

**Câu 7.** `jdeps --multi-release 11` có phải full Java 11 compatibility test không?  
**Đáp án:** Không. Nó chọn đúng view của multi-release JAR trong phân tích; không tự thực thi app hay chặn mọi API/binary mismatch.

**Câu 8.** `jdeps --jdk-internals` sạch có chứng minh ứng dụng không dùng reflection vào JDK internals?  
**Đáp án:** Không. Static analysis có thể bỏ qua reflection/string-based dynamic access.

**Câu 9.** Lỗi `UnsupportedClassVersionError` thường giải thích điều gì?  
**Đáp án:** JVM không hiểu classfile version của một class nó cần nạp; phải xác định JAR và class major thực.

**Câu 10.** `NoSuchMethodError` thường khác `UnsupportedClassVersionError` ở đâu?  
**Đáp án:** Nó thường là binary API/linkage mismatch: class nạp được nhưng method descriptor đang gọi không tồn tại theo binary API runtime.

**Câu 11.** Tại sao cần kiểm tra JaCoCo/ASM khi nâng JDK?  
**Đáp án:** Bytecode tools cần hiểu classfile versions/attributes mới; processor hoặc agent cũ có thể crash dù app Java source hợp lệ.

**Câu 12.** Có phải multi-release JAR chứa `META-INF/versions/17` luôn không chạy được Java 11?  
**Đáp án:** Không. Java 11 chọn view phù hợp; cần kiểm tra base/versions ≤11 và manifest semantics.

**Câu 13.** Một annotation processor chạy trên JDK 24 có nhất thiết chạy được trong JVM Java 11 production?  
**Đáp án:** Không nhất thiết và cũng không cần nếu processor chỉ là build-time tool; nhưng **generated output** phải tương thích target Java 11.

**Câu 14.** Thế nào là kiểm chứng đủ mạnh trước phát hành thư viện Java 11?  
**Đáp án:** `--release 11`, bytecode audit của app và dependencies, Maven/Gradle resolved graph, plugin/processor/agent compatibility, API/static scans và **tests trên runtime Java 11 thật**.

**Câu 15.** Có thể chỉ sửa classfile major 61 xuống 55 bằng hex editor không?  
**Đáp án:** Không. Runtime format, bytecode instructions, attributes và APIs có thể không tương thích; cần dùng phiên bản thư viện phù hợp hoặc build lại đúng target.

## 19. Tổng kết

```text
                     "Hỗ trợ Java 11?"
                             |
               +-------------+--------------+
               |                            |
      Source Java + JDK APIs          Build/dependency graph
               |                            |
       javac --release 11           Maven / Gradle tools
               |                            |
        major 55 classfile          Resolved JAR versions
               |                            |
               +-------------+--------------+
                             |
                     Artifact cuối cùng
                             |
          +------------------+------------------+
          |                  |                  |
     javap / jar          jdeps / scan      ASM/agents/plugins
     version/layout       static deps       transformation compat
          |                  |                  |
          +------------------+------------------+
                             |
                   Test trên JVM Java 11
                             |
                  Startup + integration
                             |
                      Release có căn cứ
```

**Những điều phải nhớ:**

- **`--release 11` mạnh hơn `-source 11 -target 11`** khi cần giới hạn Java SE API.
- **Major 55 không đủ chứng minh compatibility**: thư viện major 61, reflection và API linkage vẫn có thể làm runtime Java 11 thất bại.
- **Maven/Gradle plugins và annotation processors** phải tương thích với compiler/build JVM; **mã được sinh** phải tương thích runtime đích.
- **Bytecode tools** như `javap`, `jdeps`, `jdeprscan`, ASM, Byte Buddy, JaCoCo trả lời những câu hỏi khác nhau; không cái nào thay thế mọi kiểm chứng.
- **Dependency graph thực đã resolve** quan trọng hơn danh sách dependencies được viết trong POM/build file.
- **Đừng bỏ qua multi-release JAR**, runtime path và artifact sau shading/instrumentation.
- **CI trên JDK 11 thật** là bước xác minh hành vi không thể thay bằng build trên JDK mới.
- **Security và reproducibility** cũng cần được kiểm tra: tương thích Java không đồng nghĩa dependency an toàn.

Những cách làm trên **vẫn áp dụng với Java 11 và JDK hiện đại**. Khi cập nhật JDK, build tools và bytecode agents, hãy kiểm chứng lại tương thích từ source tới final artifact thay vì chỉ nhìn trạng thái “BUILD SUCCESS”.

### Tài liệu tham khảo chính thức và đang được duy trì

- [Oracle JDK 11 — javac tool và --release](https://docs.oracle.com/en/java/javase/11/tools/javac.html)
- [Oracle JDK 11 — javap, jdeps, jar, jdeprscan command reference](https://docs.oracle.com/en/java/javase/11/tools/index.html)
- [Oracle Java SE 11 — JVM Specification `4: classfile format và versions](https://docs.oracle.com/javase/specs/jvms/se11/html/jvms-4.html)
- [Apache Maven Compiler Plugin — Setting --release](https://maven.apache.org/plugins/maven-compiler-plugin/examples/set-compiler-release.html)
- [Apache Maven Compiler Plugin — Maven 3/Maven 4 release configuration](https://maven.apache.org/plugins-archives/maven-compiler-plugin-LATEST-4.x/examples/set-compiler-release.html)
- [Apache Maven Compiler Plugin — Toolchains / different JDK](https://maven.apache.org/plugins/maven-compiler-plugin/examples/compile-using-different-jdk.html)
- [Apache Maven Dependency Plugin — dependency:tree](https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html)
- [Gradle — JVM Toolchains và options.release](https://docs.gradle.org/current/userguide/toolchains.html)
- [Gradle — Building Java projects](https://docs.gradle.org/current/userguide/building_java_projects.html)
- [Gradle — dependencyInsight và dependency graph](https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html)
- [Gradle — Dependency Locking](https://docs.gradle.org/current/userguide/dependency_locking.html)
- [Gradle — Securing Dependencies](https://docs.gradle.org/current/userguide/securing_dependencies.html)
- [Oracle — jdeps tool: --multi-release và --jdk-internals](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jdeps.html)
- [JaCoCo — Release Notes và Java support matrix](https://www.jacoco.org/jacoco/trunk/doc/changes.html)
- [ASM — Project / current releases](https://asm.ow2.io/)
- [Byte Buddy — Project và documentation](https://bytebuddy.net/)
- [OpenJDK JEP 484 — Class-File API (JDK mới, không phải Java 11 API)](https://openjdk.org/jeps/484)
