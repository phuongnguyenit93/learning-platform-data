# Chạy kiểm thử trên đúng JDK mục tiêu

Khi một ứng dụng hoặc thư viện tuyên bố “chạy được trên Java X”, phải **chạy bộ kiểm thử bằng JVM của Java X thực tế**. Việc biên dịch thành công, đặt `--release X` hoặc nhìn thấy `java -version` trên máy lập trình chưa chứng minh điều đó. Mục tiêu bài này là chọn đúng JDK cho khâu chạy test, xác minh bằng chứng và tái lập kết quả trên máy lập trình lẫn CI.

**Bối cảnh Java 15:** Java 15 phát hành tháng 9/2020, là bản **non-LTS** đã bị thay thế và kết thúc chu kỳ hỗ trợ cập nhật thông thường từ tháng 3/2021. Năm 2026, chỉ kiểm thử trên Java 15 khi còn **cam kết tương thích với hệ thống đã tồn tại**; không chọn Java 15 cho triển khai sản xuất mới. Với dự án mới, ưu tiên một phiên bản LTS đang được nhà phân phối hỗ trợ, chẳng hạn Java 21 hoặc 25. Cách dùng `--release`, toolchain, kiểm thử nhiều JDK và CI bên dưới vẫn áp dụng cho các phiên bản Java đang được hỗ trợ.

## 1. “Đúng JDK mục tiêu” nghĩa là gì?

Một pipeline Java có thể liên quan đến nhiều JVM khác nhau:

| Thành phần | Vai trò | Điều phải xác nhận |
| --- | --- | --- |
| JDK khởi động Maven hoặc Gradle | Chạy chính công cụ build | `mvn -version` hoặc `./gradlew --version`; Gradle daemon còn có JVM riêng |
| JDK biên dịch | Chạy `javac` qua compiler/toolchain | Phiên bản compiler, các option và nguồn API |
| Mức phát hành (`--release X`) | Giới hạn cú pháp, API chuẩn và bytecode mà compiler tạo ra | Có đặt đúng X hay chưa |
| **JVM chạy bài kiểm thử** | Thực thi test và lớp ứng dụng dưới test | **Phiên bản JVM được test runner thật sự khởi chạy** |
| JVM khi triển khai | Chạy ứng dụng trong container, máy chủ hoặc môi trường người dùng | JDK/JRE, bản vá, hệ điều hành và cấu hình gần môi trường thật |

**Quy tắc:** `--release 15` không tự chuyển tiến trình test sang Java 15; `JAVA_HOME` không bảo đảm thắng cấu hình toolchain; JVM chạy Gradle daemon không nhất thiết là JVM được task `test` sử dụng. Các cơ chế phải được cấu hình và quan sát riêng.

Ví dụ, có thể chạy Gradle bằng JDK 25, biên dịch mã với `--release 15`, rồi chạy test trên **JDK 15**. Phương án này hợp lệ khi dự án thực sự còn hỗ trợ 15, và chỉ khi bộ compiler, test framework cùng dependencies tương thích với JVM 15.

## 2. Vì sao chỉ biên dịch thành công là chưa đủ?

- **Bytecode quá mới:** JVM Java 15 hỗ trợ class file đến **major version 59**. Nếu mã hoặc thư viện phụ thuộc được biên dịch cho Java mới hơn, chạy trên 15 có thể ném `UnsupportedClassVersionError`.
- **API và liên kết lúc chạy:** `--release 15` phát hiện việc gọi trực tiếp API chuẩn xuất hiện sau Java 15 trong mã biên dịch; nó không kiểm tra toàn bộ thư viện bên thứ ba, cấu hình reflection, lời gọi nạp động hay mọi đường đi của ứng dụng. Khi chạy thật vẫn có thể gặp `NoSuchMethodError`, `NoClassDefFoundError` hoặc lỗi khởi tạo.
- **Khác biệt hành vi JVM:** Thay đổi truy cập module, thư viện bảo mật/TLS, múi giờ, charset, native library hoặc garbage collector có thể chỉ lộ ra khi chạy.
- **Sai bản JDK của test runner:** IDE, Maven Surefire, Gradle test worker và CI có thể lựa chọn JVM khác nhau, dù kết quả hiện ra là “BUILD SUCCESS”.

Vì thế cần **hai hàng rào**: (1) giới hạn API/bytecode lúc biên dịch; (2) chạy unit test và integration test dưới JVM đúng với cam kết tương thích. Test về tính năng ứng dụng vẫn quan trọng hơn một phép kiểm tra phiên bản đơn lẻ.

## 3. Xác nhận môi trường và kiểm tra JVM đang chạy

Trước khi chạy, ghi nhận phiên bản và nơi công cụ tìm thấy Java:

~~~bash
java --version
javac --version
mvn --version
./gradlew --version
~~~

Lệnh `mvn --version` cho biết JVM khởi động Maven; `./gradlew --version` cho biết môi trường của Gradle, nhưng **không đủ** để xác nhận JVM chạy test nếu cấu hình toolchain/fork riêng. Nếu dùng Windows, chạy `gradlew.bat --version`. Khi dùng Maven Wrapper, thay `mvn` bằng `./mvnw` (hoặc `mvnw.cmd` trên Windows) nếu dự án có wrapper.

Có thể tự kiểm tra phiên bản JVM bằng chương trình Java độc lập sau. Lưu dưới tên **TargetJdkProbe.java**:

~~~java
public final class TargetJdkProbe {
    public static void main(String[] args) {
        if (args.length != 1) {
            throw new IllegalArgumentException("Cần một phiên bản Java mong đợi");
        }

        int expected = Integer.parseInt(args[0]);
        int actual = Runtime.version().feature();

        if (actual != expected) {
            throw new IllegalStateException(
                "Cần Java " + expected + ", nhưng JVM hiện tại là Java " + actual
            );
        }

        System.out.println("OK: test JVM = Java " + actual);
    }
}
~~~

Với JDK có `javac` hỗ trợ target 15, biên dịch:

~~~bash
javac --release 15 TargetJdkProbe.java
~~~

**Sau đó dùng lệnh `java` thuộc chính JDK 15 đã cài** để chạy `java TargetJdkProbe 15`. Chỉ khi JVM thực sự là Java 15, stdout sẽ là:

~~~text
OK: test JVM = Java 15
~~~

Nếu dùng Java 21 để chạy cùng class file, chương trình **phải thất bại** với thông báo về việc mong đợi Java 15 nhưng nhận Java 21. Đây là kiểm tra có chủ đích, không phải lỗi của `--release`. Ví dụ không cần JUnit hoặc thư viện ngoài và sử dụng API có sẵn từ Java 9.

Trong test framework, đặt một phép kiểm tra tương tự **bên trong tiến trình test** (không chỉ ở shell trước khi test). Ví dụ với **JUnit Jupiter 5.x** trong dự án đã cấu hình dependency phù hợp, lưu ở `src/test/java/TargetJdkTest.java`:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

class TargetJdkTest {
    @Test
    void mustRunOnJava15() {
        assertEquals(
            15,
            Runtime.version().feature(),
            () -> "Test JVM: " + System.getProperty("java.runtime.version")
                + " at " + System.getProperty("java.home")
        );
    }
}
~~~

Đây là **một class test trong dự án JUnit**, không phải chương trình chạy độc lập bằng `java`. Chỉ kích hoạt phép kiểm tra cố định “15” ở job có mục tiêu Java 15; khi chạy ma trận nhiều phiên bản, truyền phiên bản kỳ vọng theo từng job. **Lưu ý cập nhật:** JUnit **6** yêu cầu Java **17+**; nếu phải chạy test thật trên Java 15, dùng nhánh framework còn tương thích, chẳng hạn **JUnit 5.x**, và đánh giá chính sách bảo trì dependencies. Không coi việc chạy JUnit 6 trên Java 21 để test code `--release 15` là đã xác nhận JVM 15.

## 4. Maven: tách mục tiêu biên dịch và JVM của Surefire

Trong Maven 3, có thể dùng `maven.compiler.release` để yêu cầu compiler tạo code đúng với Java 15. Trích đoạn dưới nằm **bên trong `<project>` của `pom.xml`**; dự án còn phải có dependency test tương ứng:

~~~xml
<properties>
    <maven.compiler.release>15</maven.compiler.release>
</properties>

<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.14.1</version>
        </plugin>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-surefire-plugin</artifactId>
            <version>3.6.0</version>
            <configuration>
                <jdkToolchain>
                    <version>15</version>
                </jdkToolchain>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

- `maven.compiler.release=15` giới hạn việc **biên dịch**; nó **không** quyết định JVM chạy test.
- `maven-surefire-plugin` chạy unit test ở pha `test`. Cấu hình `jdkToolchain` yêu cầu Surefire chọn JVM đúng phiên bản từ **Maven Toolchains**. Nếu không tìm được toolchain tương ứng, cần xử lý lỗi cấu hình thay vì âm thầm chấp nhận chạy test trên JVM khác.
- Cần khai báo JDK 15 thật trong `~/.m2/toolchains.xml` hoặc cơ chế phát hiện/cấp toolchain mà phiên bản plugin của dự án hỗ trợ. Ví dụ trên Linux, nếu JDK 15 **thực sự được cài ở `/opt/jdks/jdk-15`**, cấu hình dạng:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<toolchains>
    <toolchain>
        <type>jdk</type>
        <provides>
            <version>15</version>
        </provides>
        <configuration>
            <jdkHome>/opt/jdks/jdk-15</jdkHome>
        </configuration>
    </toolchain>
</toolchains>
~~~

Hãy thay đường dẫn theo vị trí JDK thực tế và bảo đảm công cụ đọc đúng file. Tùy phiên bản Maven/plugin, có thể dùng cơ chế toolchain tự phát hiện được hỗ trợ; luôn xác minh JDK mà Surefire chọn.

Chạy các bài test khi JDK và dependencies đã sẵn sàng:

~~~bash
mvn --version
mvn --batch-mode test
mvn --batch-mode verify
~~~

`test` chạy các unit test do Surefire khám phá; `verify` chạy đến pha xác minh của Maven, nhưng **integration test chỉ được thực thi khi dự án đã cấu hình plugin/binding tương ứng**, thường là Failsafe. Kiểm tra số lượng test và báo cáo trong `target/surefire-reports/`. Một test “pass” trên JVM sai vẫn chưa đạt yêu cầu tương thích.

Nếu không cần tách các JDK, cách đơn giản là khởi chạy Maven trực tiếp bằng JDK mục tiêu và xác nhận JVM trong test. Khi cần compile và test trên hai JDK khác nhau, dùng toolchain thay vì dựa vào thứ tự biến môi trường trên từng máy.

## 5. Gradle: chọn JDK cho compiler và task Test

Gradle có **Java toolchains**: `javaCompiler` dùng cho compile, `javaLauncher` dùng cho Test/JavaExec. Với Gradle hiện đại, JVM khởi chạy **Gradle daemon** có thể khác JVM mà các task sử dụng. Chẳng hạn Gradle 9 yêu cầu JVM **17+ để chạy daemon**, nhưng vẫn có thể dùng toolchain để chạy test trên Java 15.

Trích đoạn **build.gradle.kts** sau minh họa rõ việc *biên dịch bằng JDK 25 hướng đến Java 15, nhưng chạy test bằng JDK 15*. Dự án dùng plugin Java và đã khai báo test framework hỗ trợ Java 15 (nếu dùng JUnit Jupiter thì dùng nhánh 5.x):

~~~kotlin
plugins {
    java
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(25)
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(15)
}

tasks.withType<Test>().configureEach {
    useJUnitPlatform()
    javaLauncher.set(javaToolchains.launcherFor {
        languageVersion = JavaLanguageVersion.of(15)
    })
}
~~~

Cần cài **cả JDK 25 và JDK 15** để ví dụ này chạy, hoặc cấu hình cơ chế cấp toolchain có khả năng lấy đúng phiên bản; Gradle không tự tải JDK khi không có kho cấp toolchain được thiết lập. Không nhầm `options.release.set(15)` với cấu hình `javaLauncher`: cái đầu ràng buộc đầu ra compiler, cái sau quyết định JVM chạy test. Nếu toàn bộ ứng dụng nhắm Java 21, thay cấu hình phù hợp về 21, không giữ cứng 15.

Các lệnh hữu ích:

~~~bash
./gradlew javaToolchains
./gradlew clean test
./gradlew check
~~~

`javaToolchains` giúp kiểm tra JDK Gradle phát hiện; `test` mới thực thi test, và `check` bao gồm các tác vụ xác minh đã cấu hình. Đọc báo cáo ở `build/reports/tests/test/index.html` và kiểm tra tính đúng đắn của JVM test. Nếu thiếu JDK yêu cầu, sửa cấu hình cấp toolchain hoặc cài phiên bản đúng; không hạ mức kiểm tra để làm build xanh.

## 6. CI: chạy trên phiên bản thực sự cần hỗ trợ

Xây dựng **ma trận phiên bản** từ hợp đồng hỗ trợ của sản phẩm:

- **Ứng dụng triển khai trên một JDK:** test tối thiểu trên đúng JDK của môi trường triển khai (kể cả bản cập nhật quan trọng); chạy thêm phiên bản mới hơn để phát hiện lỗi trước khi nâng cấp.
- **Thư viện hỗ trợ nhiều JDK:** chạy test trên **phiên bản tối thiểu được cam kết** và các phiên bản được quảng bá là hỗ trợ, thay vì chỉ test JDK mới nhất.
- **Dự án còn cam kết Java 15:** phải có một job chạy test **trên JVM 15 thực sự**, với bản phân phối cũ được xác minh nguồn gốc và môi trường kiểm thử phù hợp. Vì Java 15 đã hết vòng đời hỗ trợ, ưu tiên lên kế hoạch loại bỏ cam kết này; một job chạy Java 21 không thay thế được job Java 15.
- **Sản phẩm mới năm 2026:** ví dụ có thể test Java 21 và 25 nếu hai phiên bản này nằm trong phạm vi hỗ trợ thực tế. Java 17 hoặc phiên bản khác chỉ nên thêm theo yêu cầu của sản phẩm, không suy diễn từ tên module.

Ví dụ `.github/workflows/java-tests.yml` dành cho dự án Maven được cấu hình để **để JVM test đi theo JDK của từng job**, và có dependency tương thích với các phiên bản trong ma trận:

~~~yaml
name: Java compatibility tests

on:
  push:
  pull_request:

jobs:
  tests:
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        java: ['21', '25']

    steps:
      - uses: actions/checkout@v7
      - uses: actions/setup-java@v6
        with:
          distribution: temurin
          java-version: ${{ matrix.java }}
          cache: maven
      - name: Inspect build JVM
        run: |
          java --version
          javac --version
          mvn --version
      - name: Run Maven verification
        run: mvn --batch-mode --no-transfer-progress verify
~~~

**Bẫy quan trọng:** Nếu `pom.xml` đang khóa `maven-surefire-plugin/jdkToolchain` ở phiên bản 15, hoặc task `Test` của Gradle khóa `javaLauncher` ở 15, thì chỉ đổi `setup-java` thành 21/25 **không làm test chạy trên 21/25**. Muốn ma trận thật, phải để launcher của test theo từng job (hoặc thiết lập toolchain cho mỗi job) và xác nhận từ bên trong test. Tương tự, `setup-java` cài Java 21 không tự thay đổi JVM của một service/container mà integration test gọi đến.

Lưu báo cáo số test chạy, failures, phiên bản JDK, bản phân phối, hệ điều hành và kiến trúc khi chúng ảnh hưởng đến hành vi. Với ứng dụng đóng gói container, hãy kiểm thử cả image/chạy thực tế, đặc biệt khi base image dùng JRE khác với JVM chạy test.

## 7. Những tình huống sai và cách xử lý

| Hiện tượng | Nguyên nhân cần kiểm tra | Cách xử lý |
| --- | --- | --- |
| `UnsupportedClassVersionError` trên JDK mục tiêu | Một class của ứng dụng hoặc dependency có bytecode mới hơn JVM | Xem dependency, mức `--release` và toolchain; chọn bản dependency còn chạy được trên target; chạy test lại trên target |
| `NoSuchMethodError` hoặc `NoClassDefFoundError` | Lệch phiên bản jar, API/runtime hoặc cấu hình classpath/module path | Kiểm tra dependency tree, phiên bản runtime và đường đi gây lỗi; tái hiện trên JVM mục tiêu |
| `mvn -version`/`java --version` đúng nhưng test vẫn chạy sai JDK | Surefire fork/toolchain hoặc IDE override JDK | Ghi `Runtime.version().feature()` và `java.home` ngay **trong test**, kiểm tra `jdkToolchain` |
| Gradle daemon trên JDK 25, test bất ngờ chạy JDK khác | `javaLauncher` ở task `Test` đang chọn toolchain riêng | Xem `javaToolchains` và cấu hình task; kiểm chứng bằng test probe |
| Gradle báo không tìm thấy matching toolchain | JDK chưa cài hoặc resolver/toolchain repository chưa cấu hình | Cài JDK phù hợp hoặc cấu hình nguồn cấp rõ ràng; không giả định tự tải |
| Unit test pass nhưng integration test lỗi ở môi trường thật | Chỉ test logic, chưa chạy database/HTTP/native libs/runtime image tương ứng | Thêm integration/smoke test trên runtime triển khai; kiểm tra plugin thực sự chạy test |
| CI “xanh” với 0 test | Test bị skip, task không chạy, filter hoặc test framework không được khám phá | Xem log/số lượng test và XML/HTML reports; bỏ cờ skip, sửa cấu hình test discovery |
| Chạy được trên JDK mới nhưng hỏng trên JDK cũ đã cam kết | Chỉ test phiên bản mới hoặc thư viện test/dependency yêu cầu Java mới | Thêm job JDK tối thiểu thật sự, kiểm tra bytecode và mức Java tối thiểu của cả test framework |

Đặc biệt tránh dùng `-DskipTests`, `-Dmaven.test.skip=true` hay `-x test` trong job được coi là bằng chứng kiểm thử. Khi đổi JDK, nên kiểm tra lại các đường đi quan trọng như TLS, reflection, serialization, các driver kết nối, lớp native và mọi test phụ thuộc hệ điều hành.

## 8. Checklist hoàn thành

1. **Định nghĩa rõ cam kết:** JDK tối thiểu, JDK sản xuất, những phiên bản bổ sung cần hỗ trợ và môi trường quan trọng. Phân biệt yêu cầu tương thích lịch sử Java 15 với lựa chọn JDK được bảo trì hiện nay.
2. **Khóa mức biên dịch:** dùng `--release` hoặc cấu hình tương đương; không dựa riêng vào `sourceCompatibility`/`targetCompatibility` để bảo vệ khỏi API mới.
3. **Cấu hình runner:** Maven Surefire `jdkToolchain` hoặc Gradle `Test.javaLauncher` chọn JVM cần kiểm tra; nếu có matrix, dùng giá trị theo từng job.
4. **Tạo bằng chứng thực thi:** kiểm tra `Runtime.version().feature()` và `java.home` **trong test process**; không suy luận chỉ từ shell/Gradle daemon/Maven process.
5. **Chạy đủ test:** unit và integration/smoke test thích hợp; xác nhận số lượng test thực tế > 0, không skip và lưu báo cáo.
6. **Đối chiếu môi trường triển khai:** runtime/container, dependencies, vendor, patch level và hệ điều hành khi ảnh hưởng tương thích.
7. **Cài lại toàn bộ khi đổi target:** cập nhật phiên bản compiler, test framework, plugin, toolchain và CI nhất quán; đừng để test trên JDK mới “che” một cam kết JDK cũ.

**Tình huống kết luận:** Nếu bytecode được build bằng JDK 25 với `--release 15`, nhưng test chỉ chạy bằng JDK 25, kết quả mới chứng minh mã được biên dịch theo giới hạn Java 15 và chạy tốt trên JVM 25. Muốn khẳng định “chạy được trên Java 15”, bắt buộc phải thực thi bộ kiểm thử phù hợp **trên JVM 15 thật**. Với dự án hiện đại, áp dụng cùng nguyên tắc này cho JDK LTS thực sự được chọn.

## Tài liệu chính thức tham khảo

- [Oracle `javac --release` và giới hạn API/bytecode](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javac.html)
- [Oracle Java SE Support Roadmap: Java 15 non-LTS, các bản LTS hiện hành](https://www.oracle.com/technetwork/java/javase/tech/eol-135779.html)
- [Maven Compiler Plugin: target release](https://maven.apache.org/plugins/maven-compiler-plugin/examples/set-compiler-release.html)
- [Maven Surefire: chạy test bằng JDK toolchain](https://maven.apache.org/surefire/maven-surefire-plugin/examples/toolchains)
- [Gradle Java Toolchains và Test.javaLauncher](https://docs.gradle.org/current/userguide/toolchains.html)
- [Gradle Compatibility Matrix (phiên bản JVM chạy Gradle và toolchain)](https://docs.gradle.org/current/userguide/compatibility.html)
- [GitHub Actions setup-java: matrix, distribution và phiên bản Java](https://github.com/actions/setup-java)
- [JUnit 6: yêu cầu Java 17+; đối chiếu với JUnit 5](https://github.com/junit-team/junit-framework/wiki/Upgrading-to-JUnit-6.0)
