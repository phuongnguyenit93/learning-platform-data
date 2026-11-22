# Kiểm tra khả năng hỗ trợ JDK 21 của plugin, thư viện và annotation processor

Một dự án chỉ thực sự hỗ trợ JDK 21 khi toàn bộ chuỗi build và chạy ứng dụng hoạt động trên JDK này. Việc đặt `source` hoặc `target` thành 21 chưa đủ: plugin build có thể không chạy được trên JVM của Gradle hoặc Maven, thư viện có thể yêu cầu bytecode hay API mới hơn Java 21, và annotation processor có thể không tương thích với phiên bản `javac` đang dùng.

Bài này trình bày cách kiểm tra từng lớp, cách đọc các lỗi thường gặp và cách xác nhận kết quả bằng một lần build sạch trên JDK 21.

## 1. Phân biệt các lớp tương thích

Khi đánh giá một dự án, cần tách ít nhất bốn câu hỏi sau:

| Thành phần | Điều cần xác nhận | JVM hoặc môi trường thực thi |
|---|---|---|
| Build tool và plugin | Maven/Gradle cùng các plugin có thể khởi động và thực hiện tác vụ trên JDK 21 không? | JVM chạy Maven hoặc Gradle daemon |
| Compiler và toolchain | Mã nguồn được biên dịch bằng JDK nào, và đầu ra có đúng mức Java 21 không? | JDK được chọn cho compiler |
| Thư viện và dependency | Bytecode, API Java và hành vi runtime của từng dependency có tương thích JDK 21 không? | JVM chạy ứng dụng hoặc bài kiểm thử |
| Annotation processor | Processor có thể được nạp, chạy và sinh mã đúng với compiler đang dùng không? | JVM chạy `javac` |

Các môi trường này có thể khác nhau. Ví dụ, Gradle daemon chạy bằng một JDK nhưng Java toolchain dùng JDK 21 để biên dịch và chạy test. Tương tự, Maven có thể chạy bằng một JDK rồi chọn compiler JDK khác thông qua toolchain hoặc cấu hình fork. Vì vậy, luôn xác định JVM thực tế của từng bước trước khi kết luận tương thích.

## 2. Xác định JDK đang được sử dụng

Chạy các lệnh sau trong môi trường build thực tế, ưu tiên wrapper được lưu cùng dự án:

```bash
java -version
javac -version
mvn -version
./mvnw -version
./gradlew --version
```

Trên Windows, dùng `mvnw.cmd` và `gradlew.bat`. Các lệnh `mvn -version` và `./gradlew --version` cho biết JVM đang chạy Maven hoặc Gradle. Đối chiếu kết quả với `JAVA_HOME`, `PATH` và cấu hình CI để phát hiện trường hợp máy cá nhân dùng JDK 21 nhưng pipeline lại dùng JDK khác.

Với Gradle, có thể xem các JDK được phát hiện cho toolchain bằng:

```bash
./gradlew javaToolchains
```

Với Maven, kiểm tra thêm cấu hình Maven Toolchains nếu dự án dùng compiler JDK riêng. JDK dùng để chạy Maven plugin vẫn là JVM của Maven; việc chọn compiler toolchain không tự chuyển JVM thực thi plugin.

### Cấu hình toolchain và mức biên dịch Java 21

Với Gradle Kotlin DSL (`build.gradle.kts`), khai báo toolchain và mức API đích:

```kotlin
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release = 21
}
```

Toolchain chọn JDK cho các tác vụ Java có hỗ trợ toolchain. Nó không thay đổi JVM đang chạy Gradle daemon; vì vậy plugin Gradle vẫn phải tương thích với JVM của daemon. Đối chiếu phiên bản Gradle Wrapper với bảng tương thích Java hiện hành. Theo bảng của Gradle, JDK 21 được hỗ trợ làm toolchain từ Gradle 8.4 và có thể chạy Gradle từ Gradle 8.5; hãy kiểm tra lại bảng khi nâng wrapper vì giới hạn hỗ trợ thay đổi theo phiên bản.

Với Maven, đặt mức phát hành trong cấu hình Maven Compiler Plugin đang được dự án quản lý:

```xml
<properties>
    <maven.compiler.release>21</maven.compiler.release>
</properties>
```

Đảm bảo dự án sử dụng phiên bản Maven Compiler Plugin còn được hỗ trợ và tương thích với Maven/JDK của dự án. Nếu dùng Maven Toolchains hoặc compiler fork, xác minh compiler thực tế được chọn. `maven.compiler.release` tương ứng với tùy chọn `javac --release 21`.

`--release 21` kiểm tra cú pháp ngôn ngữ, API Java SE và định dạng bytecode theo Java 21. Đây là lựa chọn phù hợp để khóa mức nền tảng khi build bằng JDK 21 hoặc JDK mới hơn. Nó không kiểm tra khả năng tương thích của thư viện bên thứ ba, plugin build hay annotation processor; các thành phần đó cần được kiểm tra riêng.

## 3. Kiểm tra plugin của Maven và Gradle

Plugin build là mã Java (hoặc ngôn ngữ JVM khác) được nạp và thực thi bên trong tiến trình build. Do đó, một plugin có thể thất bại trước cả khi mã nguồn ứng dụng được biên dịch.

Với mỗi plugin đang được dùng, kiểm tra:

1. Phiên bản plugin còn được duy trì và có ghi nhận hỗ trợ JDK 21 trong tài liệu hoặc release notes hay không.
2. Phiên bản tối thiểu của Maven/Gradle mà plugin yêu cầu có phù hợp với wrapper của dự án hay không.
3. Plugin có dependency riêng nào yêu cầu bytecode, API hoặc JVM mới hơn Java 21 hay không.
4. Plugin có phụ thuộc API nội bộ của JDK, API nội bộ của Gradle/Maven hoặc hành vi phản chiếu không được hỗ trợ hay không.
5. Tất cả tác vụ plugin được dùng trong build, test, đóng gói và kiểm tra chất lượng có chạy được trên cấu hình JDK 21 hay không.

Với Gradle, xem danh sách plugin và phiên bản trong `plugins` block, version catalog và các script build dùng chung. Kiểm tra tài liệu tương thích của từng plugin cùng với [bảng tương thích Java của Gradle](https://docs.gradle.org/current/userguide/compatibility.html). Bảng này phân biệt rõ Java dùng để chạy Gradle với Java dùng làm toolchain.

Với Maven, xem `build/plugins`, `pluginManagement` và các plugin được kế thừa từ parent POM. Có thể dùng `mvn help:effective-pom` để xem cấu hình hiệu lực. Kiểm tra release notes của từng Maven plugin; việc Maven khởi động thành công không chứng minh mọi plugin đều tương thích.

Không kết luận plugin hỗ trợ JDK 21 chỉ vì nó khai báo `source` hoặc `target` là 21. Điều cần xác nhận là chính mã plugin và các dependency của plugin có thể chạy trong JVM thực thi build, đồng thời plugin gọi được API của phiên bản build tool đang dùng.

## 4. Kiểm tra thư viện và dependency

### Xem toàn bộ dependency được phân giải

Trước hết, lấy dependency tree thực tế thay vì chỉ đọc khai báo trực tiếp trong file build:

```bash
# Maven
./mvnw dependency:tree

# Gradle
./gradlew dependencies
```

Khi cần tìm lý do một phiên bản cụ thể được chọn, dùng `dependency:tree` với filter phù hợp của Maven hoặc `dependencyInsight` của Gradle. Kiểm tra cả dependency bắc cầu, dependency tùy chọn, runtime classpath và test classpath. Hai thư viện cùng cung cấp một API nhưng khác phiên bản có thể khiến build biên dịch được rồi thất bại khi chạy.

Đối với mỗi thư viện quan trọng, đối chiếu tài liệu hỗ trợ và release notes để xác nhận:

- Phiên bản đó hỗ trợ chạy trên Java 21, không chỉ hỗ trợ biên dịch mã ứng dụng với `--release 21`.
- Artifact được chọn có bytecode mà JVM 21 đọc được.
- Thư viện không yêu cầu API Java chỉ xuất hiện sau Java 21.
- Các dependency bắc cầu, module tùy chọn, driver và thư viện native đi kèm cũng hỗ trợ môi trường triển khai.
- Nếu dùng Java Platform Module System, module descriptor và các yêu cầu module có thể được giải quyết trên JDK 21.

### Kiểm tra bytecode và API JDK

Java 21 dùng class-file major version `65`. Có thể xem phiên bản bytecode của một lớp bằng `javap`:

```bash
javap -verbose -classpath path/to/library.jar com.example.SomeType
```

Trong kết quả, tìm dòng `major version`. Giá trị lớn hơn `65` cho biết lớp đó được biên dịch cho một định dạng class file mới hơn Java 21 và không thể được JVM 21 nạp trực tiếp. Với JAR đa phiên bản (multi-release JAR), cần xét đúng phần lớp dành cho Java 21; một JAR có thể chứa các lớp riêng cho nhiều phiên bản Java.

Dùng `jdeps` của JDK 21 để tìm tham chiếu đến API nội bộ của JDK:

```bash
jdeps --multi-release 21 --jdk-internals path/to/library.jar
```

Có thể bổ sung `--missing-deps` và `--class-path` khi cần tìm dependency bị thiếu:

```bash
jdeps --multi-release 21 --missing-deps --recursive \
  --class-path "path/to/dependencies/*" path/to/application.jar
```

`jdeps` giúp phát hiện dependency tĩnh và tham chiếu đến API nội bộ, nhưng không thể chứng minh toàn bộ hành vi runtime. Các đường gọi được tạo bằng reflection, service loading, cấu hình bên ngoài hoặc mã native vẫn cần được kiểm tra bằng test thực tế.

## 5. Kiểm tra annotation processor

Annotation processor được chạy trong tiến trình compiler, không phải trong JVM chạy ứng dụng. Vì vậy, cần xác nhận processor tương thích với JDK thực thi `javac`, đồng thời xử lý đúng mã nguồn ở mức Java 21.

Kiểm tra từng processor theo các điểm sau:

- Phiên bản processor và các dependency của nó có thể được nạp trên JDK đang chạy compiler.
- Processor hỗ trợ các cấu trúc mã nguồn Java 21 mà dự án sử dụng và khai báo `SourceVersion` phù hợp.
- Processor được khai báo trên processor path riêng hoặc được chỉ định rõ ràng; không phụ thuộc vào việc tình cờ có mặt trên compile classpath.
- Tệp service provider `META-INF/services/javax.annotation.processing.Processor` có tên lớp processor hợp lệ nếu dựa vào cơ chế tự phát hiện.
- Mã được sinh ra có thể biên dịch và chạy trên Java 21, không tham chiếu API chỉ có ở JDK mới hơn.

Một số processor dựa vào chi tiết triển khai nội bộ của `javac`, chẳng hạn các lớp trong `com.sun.tools.javac`. Những processor này có thể bị ảnh hưởng khi thay đổi JDK hoặc compiler. Ưu tiên processor được duy trì và sử dụng API chuẩn `javax.annotation.processing` cùng `javax.lang.model`; luôn kiểm tra release notes của phiên bản cụ thể.

### Lưu ý về thay đổi discovery từ JDK 23

Từ JDK 23, `javac` không còn tự động chạy annotation processor chỉ vì tìm thấy processor trên classpath. Việc xử lý annotation phải được yêu cầu rõ ràng bằng cách chỉ định processor, processor path/module path hoặc tùy chọn xử lý tương ứng. Trên JDK 21 và 22, `javac` đã phát thông báo khi phát hiện dự án đang dựa vào cơ chế implicit này.

Điểm này vẫn quan trọng với dự án nhắm tới Java 21 nhưng build bằng JDK mới hơn: `--release 21` không làm compiler quay lại hành vi của JDK 21. Hãy khai báo processor tường minh để build ổn định giữa các JDK.

Với Gradle, khai báo processor bằng configuration `annotationProcessor`:

```kotlin
dependencies {
    annotationProcessor("com.example:example-processor:<version>")
}
```

Với Maven và Maven Compiler Plugin 3.x, khai báo processor trong `annotationProcessorPaths`:

```xml
<configuration>
    <release>21</release>
    <annotationProcessorPaths>
        <path>
            <groupId>com.example</groupId>
            <artifactId>example-processor</artifactId>
            <version>${example.processor.version}</version>
        </path>
    </annotationProcessorPaths>
</configuration>
```

Đặt phiên bản processor trong dependency management hoặc property dùng chung để có thể kiểm soát và cập nhật nhất quán. Nếu dự án dùng Maven 4 cùng Compiler Plugin 4.x, làm theo cú pháp khai báo processor dependency của dòng plugin đó; cấu hình processor path của plugin 3.x đã được thay thế trong dòng 4.x.

Khi cần chẩn đoán trực tiếp, có thể yêu cầu `javac` hiển thị các vòng xử lý và processor được gọi:

```bash
javac --release 21 \
  --processor-path path/to/processor.jar \
  -processor com.example.ExampleProcessor \
  -XprintRounds -XprintProcessorInfo \
  -d out src/main/java/com/example/App.java
```

Sau build, kiểm tra thư mục generated sources, xác nhận lớp được sinh ra có nội dung mong đợi và được đưa vào compile/test. Build thành công nhưng processor không chạy vẫn có thể tạo ra artifact thiếu mã sinh tự động.

## 6. Xác nhận bằng build và test trên JDK 21

Sau khi đã kiểm tra cấu hình và phiên bản, thực hiện một lần build sạch bằng wrapper trong môi trường được cấu hình rõ ràng với JDK 21:

```bash
# Maven
./mvnw clean verify

# Gradle
./gradlew clean check
```

Trên Windows, thay bằng `mvnw.cmd clean verify` hoặc `gradlew.bat clean check`. Build sạch giúp tránh kết quả dương tính giả do class file, mã sinh tự động hoặc cache được tạo từ JDK khác.

Tiếp tục chạy ứng dụng và các integration test quan trọng trên JVM 21. Ưu tiên kiểm tra các luồng thực tế có dùng reflection, serialization, service loading, JDBC/driver, thư viện native, module hoặc tác vụ plugin tùy chỉnh. Nếu sản phẩm được đóng gói thành container, kiểm tra cả JDK/JRE trong image triển khai vì môi trường đó có thể khác môi trường build.

Trong CI, ghim JDK và build wrapper có chủ đích, ghi lại vendor, phiên bản cập nhật, hệ điều hành và kiến trúc. Chạy cùng các bước build/test trên JDK 21 giúp phát hiện sớm khác biệt giữa máy phát triển và pipeline.

## 7. Đọc lỗi để khoanh vùng nguyên nhân

| Dấu hiệu | Nguyên nhân thường gặp | Hướng kiểm tra |
|---|---|---|
| `UnsupportedClassVersionError` | Một lớp được biên dịch với class-file version mới hơn JVM đang chạy. | Xem `major version`, xác định artifact chứa lớp đó và chọn bản hỗ trợ Java 21. |
| `NoSuchMethodError` hoặc `NoSuchFieldError` | Phiên bản thư viện lúc chạy khác với phiên bản mà mã đã biên dịch dựa vào. | Kiểm tra dependency tree và runtime classpath; đồng bộ phiên bản tương thích. |
| `ClassNotFoundException` hoặc `NoClassDefFoundError` | Thiếu dependency, sai scope/classpath hoặc module không được đưa vào runtime. | Kiểm tra dependency bắc cầu, scope, module path và cấu hình đóng gói. |
| `InaccessibleObjectException` hoặc `IllegalAccessError` | Plugin/thư viện truy cập phản chiếu hoặc API nội bộ không còn được phép truy cập. | Cập nhật thành phần lên phiên bản hỗ trợ JDK 21 và kiểm tra cách dùng API; không xem tùy chọn mở module rộng là cách sửa mặc định. |
| Không có mã nguồn được sinh | Processor chưa được nạp, không được kích hoạt hoặc không xử lý annotation đang dùng. | Kiểm tra processor path, khai báo processor, service provider và thay đổi discovery từ JDK 23. |
| Plugin build lỗi trước bước compile | Plugin hoặc dependency của plugin không tương thích với JVM chạy Maven/Gradle hay API build tool. | Xác định JVM của build daemon, kiểm tra compatibility matrix và release notes của plugin. |

Không nên quy mọi lỗi runtime cho JDK 21. Hãy xác định lớp lỗi thuộc build tool, plugin, compiler, processor, dependency hay ứng dụng trước khi nâng cấp hoặc thay cấu hình.

## 8. Checklist kết luận

Chỉ đánh dấu dự án đã được xác nhận hỗ trợ JDK 21 khi các mục liên quan đều đạt:

- [ ] Đã xác định JVM chạy Maven/Gradle và JDK toolchain thực tế.
- [ ] Wrapper và toàn bộ plugin build hỗ trợ JVM chạy build cùng phiên bản Maven/Gradle đang dùng.
- [ ] Compiler được cấu hình với `--release 21` hoặc cấu hình tương đương đã được xác minh.
- [ ] Dependency tree đã được kiểm tra, gồm cả dependency bắc cầu và runtime/test classpath.
- [ ] Bytecode của các dependency có thể nạp trên JDK 21; các tham chiếu JDK nội bộ đã được đánh giá.
- [ ] Annotation processor được khai báo rõ ràng, tương thích với JVM compiler và sinh mã hợp lệ cho Java 21.
- [ ] Build sạch, test và các tác vụ plugin quan trọng chạy thành công trên JDK 21.
- [ ] Ứng dụng hoặc artifact cuối đã được chạy thử trên đúng môi trường JDK/JRE 21 dự kiến triển khai.

Nếu một mục chưa được kiểm chứng, ghi rõ thành phần, phiên bản, môi trường và lỗi quan sát được. Không suy ra toàn bộ dự án hỗ trợ JDK 21 chỉ từ việc biên dịch thành công một module.

## Tài liệu tham khảo

- [The `javac` Command — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html): tùy chọn `--release`, processor path và môi trường thực thi annotation processor.
- [The `jdeps` Command — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jdeps.html): phân tích dependency, dependency bị thiếu và tham chiếu JDK nội bộ.
- [JDK 23 Release Notes](https://www.oracle.com/java/technologies/javase/23-relnote-issues.html): thay đổi chính sách bật annotation processing trong `javac`.
- [Gradle Compatibility Matrix](https://docs.gradle.org/current/userguide/compatibility.html): phân biệt JDK dùng chạy Gradle và JDK dùng làm toolchain.
- [Apache Maven Compiler Plugin — Compile Goal](https://maven.apache.org/plugins/maven-compiler-plugin/compile-mojo.html): cấu hình compiler, release và annotation processor cho Maven.
- [Apache Maven Compiler Plugin 4.x — Compile Goal](https://maven.apache.org/plugins/maven-compiler-plugin-4.x/compile-mojo.html): cách khai báo processor trong dòng plugin 4.x.
