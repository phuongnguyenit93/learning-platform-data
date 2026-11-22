# Biên dịch và chạy kiểm thử bằng toolchain được chỉ định

Khi một dự án Java cần hỗ trợ nhiều phiên bản JDK, kết quả build chỉ đáng tin cậy khi nhóm biết chính xác compiler nào đã biên dịch mã nguồn và JVM nào đã chạy các bài kiểm thử. Một máy phát triển có thể cài nhiều JDK; CI có thể chạy Gradle hoặc Maven bằng một JDK nhưng dùng JDK khác để biên dịch; production lại chạy bằng một phiên bản thứ ba. Nếu để các công cụ tự chọn theo `PATH` hoặc `JAVA_HOME` mà không kiểm soát, kết quả giữa các môi trường có thể khác nhau.

Java toolchain cho phép chỉ định rõ JDK mà một tác vụ cần dùng. Trong Gradle và Maven, toolchain giúp chọn compiler hoặc runtime theo phiên bản, và trong một số trường hợp có thể chọn thêm vendor. Khi kết hợp toolchain với cấu hình mức phát hành như `--release`, nhóm có thể tách bạch ba câu hỏi:

1. Công cụ build đang chạy trên JDK nào?
2. Mã nguồn được biên dịch bằng compiler JDK nào và nhắm đến phiên bản Java nào?
3. Bài kiểm thử được thực thi bằng JVM nào?

Tách rõ các câu hỏi này là nền tảng để kiểm tra tương thích đa phiên bản và tái tạo kết quả build giữa máy cá nhân, CI và môi trường triển khai.

## 1. Toolchain là gì và giải quyết vấn đề nào?

Toolchain là tập hợp công cụ và runtime được chọn có chủ đích cho một công việc phát triển. Trong dự án Java, toolchain thường chỉ một bản JDK cụ thể mà compiler, test runner hoặc công cụ Javadoc sử dụng.

Nếu không chỉ định toolchain, một build có thể phụ thuộc vào JDK đang nằm đầu tiên trong `PATH`, `JAVA_HOME` hoặc cấu hình cục bộ của máy. Ví dụ:

```text
Máy lập trình viên A: JAVA_HOME -> JDK 17
Máy lập trình viên B: JAVA_HOME -> JDK 21
CI:                  JAVA_HOME -> JDK 21
Production:          runtime -> JDK 17
```

Nếu build không quy định rõ compiler và runtime cho test, cùng một commit có thể được biên dịch hoặc kiểm thử trong những môi trường khác nhau. Một số lỗi chỉ xuất hiện trên một phiên bản JDK, khiến việc tái hiện trở nên khó khăn.

Toolchain cho phép khai báo yêu cầu rõ ràng, ví dụ “dùng JDK 21 để biên dịch” hoặc “chạy test trên JDK 17”. Build tool sẽ tìm một JDK đáp ứng yêu cầu đó và dùng nó cho tác vụ được cấu hình.

### 1.1. Phân biệt JDK chạy build, compiler và test runtime

Ba vai trò này thường bị nhầm lẫn:

| Vai trò | Nhiệm vụ | Cách xác định |
|---|---|---|
| Build JVM | Chạy chính Gradle hoặc Maven và các plugin của build tool | `./gradlew -version`, `mvn -version` hoặc log của CI. |
| Java compiler | Biên dịch source và test source thành bytecode | Toolchain/compiler được cấu hình cho compile task. |
| Test JVM | Thực thi test và mã ứng dụng trong quá trình kiểm thử | Launcher/runtime được cấu hình cho test task hoặc test plugin. |

Ví dụ, Gradle có thể chạy trên JDK 21, dùng compiler JDK 21 để tạo bytecode tương thích Java 17 và chạy test trên JDK 17. Ba lựa chọn này phục vụ ba mục tiêu khác nhau.

### 1.2. Toolchain không đồng nghĩa với `JAVA_HOME`

`JAVA_HOME` thường giúp chọn JDK cho tiến trình shell hoặc build tool khởi động. Nhưng khi dự án dùng toolchain, một tác vụ có thể được giao cho JDK khác với JDK chạy Gradle/Maven.

Ví dụ, `./gradlew -version` cho biết JVM chạy Gradle. Nó không tự chứng minh mọi `JavaCompile` task cũng dùng đúng JVM đó. Tương tự, `mvn -version` cho biết JDK chạy Maven; Maven Compiler Plugin có thể dùng compiler được chọn qua toolchain.

Vì vậy, khi điều tra build đa phiên bản, cần xem cả build JVM và JDK được chọn cho từng tác vụ. Chỉ kiểm tra `JAVA_HOME` là chưa đủ.

## 2. Phân biệt toolchain với source/target và `--release`

Đây là điểm quan trọng nhất khi thiết lập build đa phiên bản. Toolchain chọn JDK thực thi công cụ; `source`, `target` và `--release` xác định mức Java mà mã nguồn được phép sử dụng hoặc bytecode được tạo ra.

### 2.1. `sourceCompatibility` và `targetCompatibility`

Hai cấu hình này thường được dùng để chỉ định mức ngôn ngữ và phiên bản bytecode đích trong build Java. Tuy nhiên, chúng không tự chọn JDK compiler và không giới hạn đầy đủ API chuẩn mà mã nguồn có thể tham chiếu.

Ví dụ, nếu dùng JDK 21 để biên dịch nhưng chỉ đặt `targetCompatibility = 17`, compiler có thể tạo class file ở mức Java 17 trong khi mã nguồn vẫn tham chiếu một API chỉ có từ Java 21. Khi chạy trên Java 17, ứng dụng có thể gặp lỗi thiếu method hoặc class.

### 2.2. `--release` giới hạn cả ngôn ngữ, bytecode và API chuẩn

Tùy chọn `javac --release N` yêu cầu compiler biên dịch theo mức phát hành Java N được hỗ trợ. Nó kết hợp việc giới hạn mức ngôn ngữ, định dạng class file và tập API Java SE được phép sử dụng cho phiên bản đó.

Ví dụ, dùng JDK 21 compiler nhưng nhắm Java 17:

```bash
javac --release 17 -d out src/com/example/App.java
```

Compiler sẽ từ chối việc sử dụng API chuẩn chỉ xuất hiện sau Java 17. Điều này giúp phát hiện sớm một số lỗi tương thích với runtime Java 17.

`--release` không tự kiểm tra mọi dependency bên ngoài, thư viện native, hành vi runtime hoặc cấu hình triển khai. Nó cũng không chọn JVM để chạy test. Những phần đó cần toolchain và kiểm thử riêng.

### 2.3. Bảng phân biệt

| Cấu hình | Quyết định điều gì? | Không quyết định điều gì? |
|---|---|---|
| Build JVM / `JAVA_HOME` | JDK chạy Gradle hoặc Maven | Không nhất thiết quyết định compiler/test launcher khi có toolchain. |
| Java toolchain | JDK được dùng bởi tác vụ compile, test hoặc công cụ tương ứng | Không tự giới hạn API/bytecode xuống phiên bản thấp hơn. |
| `sourceCompatibility` | Mức cú pháp/ngôn ngữ Java | Không tự chọn JDK và không giới hạn đầy đủ API chuẩn. |
| `targetCompatibility` | Mức class file đích | Không tự bảo đảm API được dùng có mặt trên runtime đích. |
| `--release` | Mức ngôn ngữ, class file và API Java chuẩn | Không bao phủ dependency ngoài JDK hoặc hành vi runtime. |
| Test launcher/toolchain | JVM thực thi test | Không thay đổi compiler đã biên dịch source. |

Một cấu hình đáng tin cậy thường chọn toolchain cho compiler, dùng `--release` nếu cần nhắm API/bytecode thấp hơn compiler, rồi chọn runtime tương ứng để chạy kiểm thử.

## 3. Chọn JDK cho tác vụ bằng Gradle Java Toolchains

Gradle hỗ trợ Java toolchains cho các tác vụ như compile, test và Javadoc. Có thể khai báo phiên bản JDK mong muốn trong build script để tránh phụ thuộc vào JDK mặc định của máy.

### 3.1. Khai báo toolchain chung cho project

Với Groovy DSL trong `build.gradle`:

```groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}
```

Khai báo này yêu cầu Gradle chọn một JDK có ngôn ngữ Java phiên bản 21 cho các tác vụ Java hỗ trợ toolchain. Các task như `JavaCompile`, `Test` và `Javadoc` có thể sử dụng toolchain tương ứng theo cấu hình của Gradle.

Nếu cần giới hạn vendor, có thể bổ sung điều kiện:

```groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
        vendor = JvmVendorSpec.ADOPTIUM
    }
}
```

Chỉ đặt vendor khi dự án thực sự cần một bản phân phối cụ thể. Nếu không có yêu cầu đó, chỉ định language version thường giúp build linh hoạt hơn giữa các máy và CI.

### 3.2. Chỉ định compiler rõ ràng cho tác vụ compile

Gradle cũng cho phép chọn compiler trực tiếp:

```groovy
tasks.withType(JavaCompile).configureEach {
    javaCompiler = javaToolchains.compilerFor {
        languageVersion = JavaLanguageVersion.of(21)
    }
}
```

Cách này hữu ích khi một project có nhiều nhóm tác vụ hoặc cần tách compiler theo từng source set. Hãy kiểm tra các tác vụ compile main, test và generated source để chắc rằng tất cả đều dùng JDK dự kiến.

### 3.3. Chọn runtime riêng cho test

Có thể chạy test trên JDK khác với compiler:

```groovy
tasks.withType(Test).configureEach {
    javaLauncher = javaToolchains.launcherFor {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
```

Trong ví dụ này, test task được chạy bằng JDK 17. Nếu compiler dùng JDK 21, cần đảm bảo bytecode và API được sử dụng có thể chạy trên JDK 17, thường bằng cách đặt `options.release = 17` cho các compile task thích hợp.

Ví dụ kết hợp:

```groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}

tasks.withType(Test).configureEach {
    javaLauncher = javaToolchains.launcherFor {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
```

Đây là cấu hình minh họa cho trường hợp dùng JDK 21 compiler nhưng giữ tương thích Java 17 và chạy test trên JDK 17. Với project thực tế, cần xác nhận các test source, annotation processor, plugin và dependency cũng hỗ trợ cấu hình này.

### 3.4. Kiểm tra JDK mà Gradle đã phát hiện

Gradle cung cấp task `javaToolchains` để liệt kê các JDK mà nó phát hiện:

```bash
./gradlew javaToolchains
```

Có thể dùng log chi tiết khi chạy build:

```bash
./gradlew clean test --info
```

Đọc log để xác nhận compiler và launcher được chọn. `./gradlew -version` vẫn hữu ích để xác định JVM chạy Gradle, nhưng cần xem thông tin toolchain của các task để xác nhận JDK thực thi chúng.

### 3.5. Toolchain chưa có trên máy

Gradle cần tìm thấy một JDK đáp ứng yêu cầu. Tùy cấu hình, JDK có thể được phát hiện từ cài đặt hiện có hoặc được tải qua một toolchain resolver đã cấu hình. Nếu không có JDK phù hợp và không có cơ chế tải, task có thể thất bại với lỗi không tìm thấy toolchain.

Trong CI, nên chuẩn bị JDK được yêu cầu hoặc cấu hình resolver/download một cách có kiểm soát. Không nên để build phụ thuộc vào một đường dẫn JDK chỉ tồn tại trên máy của một lập trình viên.

Lưu ý rằng toolchain không làm cho phiên bản Gradle cũ tự động chạy được trên JDK mới. Gradle daemon vẫn phải chạy trên một JDK mà phiên bản Gradle wrapper hỗ trợ. Cần kiểm tra ma trận tương thích của Gradle trước khi đổi JVM chạy build.

## 4. Chọn JDK cho compiler và test bằng Maven Toolchains

Maven cũng có cơ chế toolchain để các plugin hỗ trợ có thể sử dụng JDK được chọn, độc lập với JDK chạy Maven. Cấu hình thường gồm hai phần: khai báo các JDK có sẵn trên máy và yêu cầu toolchain trong project.

### 4.1. Khai báo JDK cài đặt trong `toolchains.xml`

File toolchain thường nằm tại `~/.m2/toolchains.xml` của người dùng hoặc vị trí cấu hình Maven tương ứng. Ví dụ:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<toolchains>
    <toolchain>
        <type>jdk</type>
        <provides>
            <version>21</version>
            <vendor>temurin</vendor>
        </provides>
        <configuration>
            <jdkHome>/opt/jdks/temurin-21</jdkHome>
        </configuration>
    </toolchain>
</toolchains>
```

Đường dẫn trên chỉ là ví dụ; thay bằng đường dẫn JDK thực tế trên máy hoặc agent CI. File này mô tả những toolchain có sẵn cho Maven, không nên commit đường dẫn cục bộ của một máy vào repository nếu các máy khác có cấu trúc khác.

### 4.2. Yêu cầu toolchain trong project

Có thể dùng Maven Toolchains Plugin để yêu cầu JDK phù hợp:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-toolchains-plugin</artifactId>
    <version>3.2.0</version>
    <executions>
        <execution>
            <goals>
                <goal>toolchain</goal>
            </goals>
        </execution>
    </executions>
    <configuration>
        <toolchains>
            <jdk>
                <version>21</version>
                <vendor>temurin</vendor>
            </jdk>
        </toolchains>
    </configuration>
</plugin>
```

Plugin tìm một toolchain khớp với yêu cầu trong `toolchains.xml` và đặt nó vào Maven session. Những plugin hỗ trợ Maven Toolchains có thể sử dụng JDK đã chọn.

### 4.3. Cấu hình compiler và mức phát hành

Maven Compiler Plugin có thể dùng toolchain được chọn để gọi compiler. Đồng thời, đặt `release` để giới hạn API và bytecode đích:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <version>3.13.0</version>
    <configuration>
        <release>17</release>
    </configuration>
</plugin>
```

Trong ví dụ, toolchain có thể chọn JDK 21 làm compiler, còn `release` yêu cầu biên dịch theo Java 17. Cần bảo đảm phiên bản compiler đủ mới để hỗ trợ `--release 17`.

### 4.4. Chạy test bằng JDK đã chọn

Maven Surefire và Failsafe có thể sử dụng Maven toolchain khi plugin/provider tương ứng hỗ trợ. Cần xác nhận cấu hình thực tế của phiên bản plugin đang dùng và kiểm tra JVM fork để chạy test. Nếu test cần chạy trên nhiều phiên bản JDK, có thể tạo các job CI riêng, mỗi job chuẩn bị toolchain/runtime tương ứng.

Không nên suy ra JVM chạy test chỉ từ `mvn -version`. Lệnh này cho biết JDK chạy Maven; test có thể được fork bằng JDK do toolchain hoặc cấu hình plugin lựa chọn. Dùng log debug của Maven và thông tin runtime in ra trong test để xác nhận.

## 5. Biên dịch đa phiên bản: compiler và runtime có thể khác nhau

Trong dự án hỗ trợ nhiều phiên bản Java, thường cần tách mục tiêu biên dịch khỏi môi trường chạy test. Có ba tình huống phổ biến.

### 5.1. Build bằng JDK mới, phát hành bytecode cho JDK thấp hơn

Ví dụ, nhóm dùng JDK 21 để build nhưng sản phẩm vẫn hỗ trợ runtime Java 17. Có thể dùng toolchain JDK 21 kết hợp `--release 17` (hoặc cấu hình tương đương trong build tool).

```text
JDK 21 compiler
       |
       v
--release 17
       |
       v
Bytecode và API Java SE mức 17
       |
       v
Chạy kiểm thử trên JDK 17
```

`--release 17` giúp compiler từ chối API chuẩn chỉ có ở Java 18 trở lên. Tuy nhiên, nếu dependency bên ngoài được build cho Java 21 hoặc yêu cầu API không có ở Java 17, ứng dụng vẫn có thể lỗi khi chạy. Cần kiểm tra class file version và yêu cầu JDK tối thiểu của toàn bộ dependency.

### 5.2. Biên dịch và test trên cùng một JDK

Đây là cấu hình đơn giản khi sản phẩm chỉ hỗ trợ một phiên bản runtime. Chọn một toolchain thống nhất cho compile và test để giảm khác biệt môi trường.

```text
JDK 21 compiler ---> bytecode Java 21
       |
       v
JDK 21 test runtime ---> test suite
```

Tình huống này xác nhận ứng dụng hoạt động trên JDK mục tiêu, nhưng chưa chứng minh ứng dụng còn chạy trên các JDK cũ nếu sản phẩm vẫn tuyên bố hỗ trợ chúng.

### 5.3. Chạy cùng bộ test trên nhiều runtime

Nếu sản phẩm hỗ trợ Java 17 và Java 21, có thể compile theo mức API thấp nhất được hỗ trợ rồi chạy test trên cả hai runtime:

```text
                Compile một lần
                 --release 17
                      |
              Artifact tương thích 17
                 /          \
                v            v
          Test trên 17    Test trên 21
```

Việc chạy trên cả hai phiên bản giúp phát hiện khác biệt về thư viện chuẩn, bảo mật, charset, timezone, GC và các hành vi runtime. Nếu sản phẩm chỉ hỗ trợ runtime mới, ma trận test có thể tập trung vào phiên bản đích và các bản cập nhật được triển khai.

## 6. Thiết kế ma trận toolchain cho CI

Một ma trận CI nên thể hiện rõ compiler, mức phát hành và runtime test. Ví dụ:

| Job | Build JVM | Compiler toolchain | Release target | Test runtime | Mục đích |
|---|---|---|---|---|---|
| Compatibility 17 | JDK 21 | JDK 21 | 17 | JDK 17 | Xác nhận bytecode và hành vi trên runtime tối thiểu. |
| Runtime 21 | JDK 21 | JDK 21 | 21 | JDK 21 | Xác nhận môi trường JDK mục tiêu. |
| Runtime update | JDK 21 | JDK 21 | 21 | Bản cập nhật JDK 21 được triển khai | Xác nhận bản build/vendor thực tế. |

Đây là ma trận minh họa. Dự án cần chọn các phiên bản theo chính sách hỗ trợ đã công bố. Nếu cần hỗ trợ nhiều phiên bản JDK, nên kiểm tra ít nhất phiên bản tối thiểu và phiên bản mục tiêu; các phiên bản trung gian chỉ cần thêm khi có yêu cầu sản phẩm hoặc rủi ro cụ thể.

### 6.1. Giữ compiler và test runtime độc lập

Một job CI có thể build artifact một lần rồi chạy test trên nhiều runtime, miễn là artifact được tạo theo mức bytecode/API phù hợp. Cách này giúp phân biệt lỗi do compiler với lỗi do runtime.

Nếu mỗi runtime job tự build lại artifact, cần ghi nhận compiler và dependency được sử dụng. Nếu không, khác biệt kết quả có thể đến từ artifact khác nhau chứ không chỉ do JVM.

### 6.2. Kiểm tra các tác vụ ngoài compile và test

Toolchain có thể ảnh hưởng đến nhiều tác vụ khác:

- Javadoc: phiên bản công cụ có thể hiểu tag, module và API khác nhau.
- Annotation processor: chạy trong môi trường compiler và có thể phụ thuộc phiên bản JDK.
- Code generator: có thể gọi API JDK hoặc tạo source/bytecode theo phiên bản cụ thể.
- Test integration: có thể khởi động JVM con hoặc tiến trình ngoài, cần xác định JDK riêng.
- Công cụ phân tích bytecode: có thể chưa hiểu class file version mới.
- Packaging và signing: có thể dùng công cụ JDK như `jar`, `jarsigner` hoặc `jlink`.

Không nên cho rằng chọn toolchain cho compile đã tự động cấu hình mọi tiến trình con hoặc mọi plugin. Cần kiểm tra tài liệu của plugin và log thực tế.

## 7. Xác minh toolchain thực sự được sử dụng

Khai báo cấu hình chỉ là yêu cầu. Cần xác nhận build tool đã tìm được đúng JDK và giao nó cho đúng tác vụ.

### 7.1. Kiểm tra trong Gradle

Chạy:

```bash
./gradlew -version
./gradlew javaToolchains
./gradlew clean test --info
```

Ba lệnh này cung cấp ba góc nhìn:

- `-version`: JVM chạy Gradle và phiên bản Gradle wrapper.
- `javaToolchains`: các JDK Gradle phát hiện được.
- `clean test --info`: log chi tiết khi compile và chạy test, giúp xem compiler/launcher được chọn.

Nếu toolchain không được tìm thấy, kiểm tra JDK đã cài, đường dẫn phát hiện, vendor và cấu hình resolver tải toolchain. Không nên tự ý đổi `JAVA_HOME` cho đến khi hiểu task đang dùng toolchain nào.

### 7.2. Kiểm tra trong Maven

Chạy:

```bash
mvn -version
mvn -X clean verify
```

`mvn -version` cho biết JVM chạy Maven. Log debug giúp xem toolchain và các plugin chọn compiler/test runtime ra sao. Có thể in `java.version`, `java.vendor` và `java.home` từ trong test để xác nhận JVM thực thi test.

Ví dụ:

```java
import org.junit.jupiter.api.Test;

class RuntimeInfoTest {
    @Test
    void printRuntime() {
        System.out.println("java.version=" + System.getProperty("java.version"));
        System.out.println("java.vendor=" + System.getProperty("java.vendor"));
        System.out.println("java.home=" + System.getProperty("java.home"));
    }
}
```

Trong dự án thực tế, có thể ghi thông tin này ở đầu log của test job thay vì giữ một test chỉ để in phiên bản. Mục tiêu là có bằng chứng rõ ràng về JVM đang chạy test.

### 7.3. Xác nhận class file và mức API

Có thể dùng `javap -verbose` để xem major version của class file:

```bash
javap -verbose -classpath build/classes/java/main com.example.App
```

Trong output, tìm `major version`. Một số mức phổ biến:

| Java | Class file major version |
|---|---:|
| Java 8 | 52 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |

Thông tin class file giúp xác nhận bytecode được tạo cho mức Java nào. Nó không chứng minh dependency hoặc API bên ngoài tương thích; vẫn cần chạy trên runtime đích.

## 8. Các lỗi thường gặp khi dùng toolchain

### 8.1. Build tool chạy trên JDK không được hỗ trợ

Toolchain chọn compiler/test runtime cho task, nhưng Gradle daemon hoặc Maven vẫn cần một JDK mà phiên bản build tool hỗ trợ. Nếu chạy Gradle wrapper cũ trên một JDK mới chưa được hỗ trợ, build có thể thất bại trước khi task Java toolchain được thực hiện.

Hãy kiểm tra ma trận tương thích của Gradle/Maven và nâng build tool khi cần. Đừng nhầm lỗi khởi động Gradle daemon với lỗi không tìm thấy Java toolchain.

### 8.2. Chỉ đặt target version mà không giới hạn API

Đặt `targetCompatibility = 17` không tự bảo đảm source chỉ dùng API Java 17. Nếu compiler JDK 21 cho phép gọi API mới, bytecode có thể được tạo nhưng lỗi khi chạy trên JDK 17.

Khi cần hỗ trợ runtime cũ, dùng `--release` hoặc cấu hình `options.release` tương ứng, sau đó chạy test trên runtime cũ nhất được hỗ trợ.

### 8.3. Compiler đúng nhưng test chạy sai JDK

Build có thể compile bằng JDK 17 nhưng test task lại dùng JDK 21 mặc định, hoặc ngược lại. Điều này khiến test xanh nhưng production chạy một phiên bản khác.

Hãy cấu hình test launcher/toolchain riêng và kiểm tra `java.version` trong tiến trình test. Với integration test khởi chạy process con, cần kiểm tra cả JDK của process đó.

### 8.4. Toolchain yêu cầu JDK chưa được cài hoặc chưa thể tải

Khi không tìm thấy JDK phù hợp, build tool có thể báo không có toolchain khớp yêu cầu. Cần chuẩn bị JDK trên agent hoặc cấu hình cơ chế tải toolchain. Với CI, nên xác định trước nguồn tải, vendor và version để tránh phụ thuộc vào môi trường ngẫu nhiên.

### 8.5. Vendor hoặc bản cập nhật không được cố định

Chỉ yêu cầu language version có thể cho phép các máy chọn những bản phân phối khác nhau. Điều này thường linh hoạt và phù hợp với nhiều dự án. Nhưng nếu production yêu cầu một vendor/build cụ thể, cần cố định điều kiện tương ứng và kiểm tra agent CI đã cài đúng JDK.

Không nên cố định đường dẫn tuyệt đối đến thư mục JDK trong build script dùng chung. Hãy dùng toolchain criteria và chuẩn bị cài đặt theo môi trường.

### 8.6. Annotation processor hoặc plugin dùng JDK khác

Một số plugin và annotation processor chạy trong tiến trình compiler, số khác tạo process riêng. Chọn toolchain cho `JavaCompile` không có nghĩa mọi plugin trong build đều dùng cùng JDK.

Khi có lỗi chỉ xuất hiện ở code được sinh, kiểm tra phiên bản processor, plugin và JVM của tiến trình tương ứng. Nâng plugin hoặc cấu hình toolchain riêng nếu plugin hỗ trợ.

## 9. Quy trình triển khai toolchain cho dự án

Một cách triển khai có kiểm soát gồm các bước sau:

1. **Lập danh sách JDK cần hỗ trợ.** Ghi rõ phiên bản tối thiểu, phiên bản build, phiên bản test và runtime production.
2. **Kiểm tra build tool.** Xác nhận Gradle wrapper hoặc Maven và các plugin hỗ trợ JDK chạy build.
3. **Cấu hình compiler toolchain.** Chọn JDK và vendor nếu cần; không phụ thuộc vào `PATH` của từng máy.
4. **Cấu hình mức phát hành.** Dùng `--release` khi cần biên dịch trên JDK mới nhưng phát hành cho runtime thấp hơn.
5. **Cấu hình test runtime.** Chọn launcher/toolchain cho unit test, integration test và process con.
6. **Chuẩn bị JDK trên CI.** Cài đặt hoặc cấu hình resolver tải toolchain; ghi lại phiên bản và build.
7. **Xác minh bằng log và class file.** Kiểm tra build JVM, compiler, test JVM và major version của bytecode.
8. **Chạy ma trận test.** Test trên runtime tối thiểu được hỗ trợ và runtime mục tiêu; mở rộng khi có rủi ro cụ thể.
9. **Ghi lại kết quả.** Lưu cấu hình, output xác minh và kết quả test để có thể tái tạo build.

## 10. Checklist trước khi chấp nhận build đa phiên bản

- [ ] Đã xác định JDK chạy Gradle/Maven và kiểm tra build tool hỗ trợ phiên bản đó.
- [ ] Đã khai báo compiler toolchain trong build script hoặc Maven toolchains.
- [ ] Đã xác định mức API/bytecode đích bằng `--release` nếu cần hỗ trợ runtime thấp hơn.
- [ ] Đã cấu hình test launcher/runtime riêng cho từng phiên bản cần kiểm tra.
- [ ] Đã xác nhận annotation processor, generator, plugin và process con dùng JDK phù hợp.
- [ ] CI chuẩn bị đúng JDK hoặc toolchain resolver; không phụ thuộc cài đặt cá nhân.
- [ ] Đã kiểm tra log toolchain và `java.version` trong tiến trình test.
- [ ] Đã xác nhận class file version của artifact.
- [ ] Đã chạy test trên runtime tối thiểu và runtime mục tiêu theo chính sách hỗ trợ.
- [ ] Đã lưu cấu hình và bằng chứng để tái tạo kết quả build.

## 11. Kết luận

Toolchain giúp dự án Java chọn rõ JDK cho compiler, test và các tác vụ hỗ trợ. Nó giải quyết sự phụ thuộc vào JDK mặc định của từng máy và giúp CI, máy phát triển và môi trường kiểm thử sử dụng cùng quy tắc.

Để build đa phiên bản chính xác, cần phân biệt JDK chạy build, compiler toolchain, mức phát hành bytecode/API và JVM chạy test. Toolchain chọn công cụ; `--release` giới hạn ngôn ngữ, class file và API chuẩn; test launcher xác định runtime thực thi. Kết hợp các cấu hình này với kiểm tra log, class file và ma trận test sẽ tạo ra bằng chứng rõ ràng rằng artifact được biên dịch và chạy trên đúng phiên bản JDK đã chỉ định.
