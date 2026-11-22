# Ma trận tương thích giữa phiên bản công cụ build và JDK

Khi Java migration từ JDK 8 hoặc 11 lên JDK 17, 21, 25 hay phiên bản mới hơn, một dự án có thể gặp lỗi ngay trước khi chạy một dòng source code: Gradle daemon không khởi động, Maven plugin yêu cầu Java mới hơn, Groovy hoặc ASM không đọc được class-file version, compiler tạo bytecode vượt runtime đích, hoặc test chạy trên JDK khác với ứng dụng production.

Nguyên nhân thường nằm ở việc xem “dự án dùng Java 21” như một cấu hình duy nhất. Trên thực tế, **công cụ build, compiler, test JVM, plugin, runtime sản phẩm và toolchain của CI có thể sử dụng các phiên bản Java khác nhau**. Chúng phải tương thích với nhau, nhưng không nhất thiết phải giống nhau.

Bài học này xây dựng **ma trận tương thích giữa Maven/Gradle và JDK**, giải thích cách đọc ma trận chính thức, cách khóa cấu hình để build tái lập được và quy trình nâng cấp có thể rollback. Các mốc phiên bản trong phần ma trận là ảnh chụp tham chiếu tại **tháng 11/2026**, không phải cam kết rằng mọi plugin của một dự án đều hoạt động với tổ hợp đó. Luôn đối chiếu release note và compatibility matrix của đúng bản công cụ, JDK vendor/build và plugin đang sử dụng.

## 1. Một dự án Java có nhiều vai trò JDK

Xem sơ đồ một build thực tế:

~~~text
             Developer / CI / Build agent
                         |
             +-----------+-----------+
             |                       |
       Maven launcher           Gradle Wrapper
             |                       |
         Maven JVM               Gradle JVM/Daemon
             |                       |
             +-----------+-----------+
                         |
                Build lifecycle / plugins
                         |
       +-----------------+-----------------+
       |                 |                 |
  Java compiler      Test JVM         Javadoc/Codegen
  JDK 17/21/...      JDK 17/21/...   JDK hoặc plugin riêng
       |
   class files / JAR
       |
       v
 Application runtime ở staging/production
 JDK 17/21/... và dependency graph tương ứng
~~~

Có thể có thêm JDK cho Kotlin compiler daemon, annotation processor, bytecode instrumentation, native image và công cụ phân tích. Trong mọi trường hợp, cần phân biệt các vai trò chính:

| Vai trò | Ý nghĩa | Thiết lập thường gặp |
|---|---|---|
| **Build tool runtime** | JVM chạy Maven core hoặc Gradle daemon | `JAVA_HOME`, Gradle daemon JVM criteria, cấu hình IDE |
| **Compiler JDK** | `javac` thực tế tạo class file | Gradle toolchain, Maven toolchains, compiler plugin |
| **Language/API target** | Syntax, class-file format và Java SE API mà artifact được phép dùng | `--release`, compiler options |
| **Test JVM** | JVM thực thi unit/integration test | Gradle `Test.javaLauncher`, Maven Surefire/Failsafe toolchain |
| **Application runtime** | JVM chạy artifact đã phát hành | Container image, service runtime, Kubernetes deployment |
| **Plugin runtime** | JVM mà plugin thực thi trong hoặc compiler/service do plugin khởi tạo | Version plugin, Gradle/Maven API, JDK |
| **CI/IDE JVM** | Môi trường launch build trên máy và runner | GitHub Actions/Jenkins tool configuration, Gradle JVM của IDE |

Một build chạy bằng Gradle 9 trên JDK 21 có thể **biên dịch code Java 17** bằng toolchain 17 và thử artifact trên JDK 17. Tương tự, Maven chạy bằng JDK 21 có thể gọi compiler JDK 17 thông qua toolchain. Ngược lại, việc Maven báo Java 21 trong `mvn -version` **không** chứng minh plugin compiler hoặc test runner cũng dùng Java 21 khi toolchains đã được cấu hình.

### 1.1. Các quan hệ tương thích cần kiểm tra

Một ma trận thực tế phải trả lời nhiều câu hỏi:

1. **Build tool có chạy trên JDK được chọn không?**
2. **Build tool có tìm và điều khiển toolchain JDK mục tiêu không?**
3. **Plugin có hỗ trợ version build tool đó không?**
4. **Plugin có hỗ trợ class-file format và API của JDK đó không?**
5. **Compiler có tạo artifact đúng baseline runtime được công bố không?**
6. **Test có chạy trên JDK thấp nhất và JDK mới nhất cần hỗ trợ không?**
7. **Dependency runtime có bytecode và hành vi tương thích với JDK triển khai không?**

Nếu chỉ kiểm tra câu 1, kết quả có thể là “Gradle khởi động được” nhưng `compileJava` hoặc `test` vẫn lỗi. Nếu chỉ kiểm tra compile, code vẫn có thể ném `UnsupportedClassVersionError` hoặc `NoSuchMethodError` ở production.

## 2. Ma trận chính thức của Gradle: phân biệt toolchain và Gradle runtime

Gradle có **hai cột Java compatibility quan trọng**:
- **Support for toolchains:** phiên bản Gradle đầu tiên có hỗ trợ dùng một JDK Java tương ứng qua cơ chế toolchain để thực hiện các task phù hợp.
- **Support for running Gradle:** phiên bản Gradle đầu tiên được xác nhận có thể **chạy Gradle** trên JVM Java tương ứng.

Hai cột có thể khác nhau. Ví dụ, Gradle 8.4 có hỗ trợ Java 21 qua toolchain, nhưng **Gradle 8.5 mới hỗ trợ chạy Gradle trên Java 21**.

### 2.1. Ma trận Gradle – Java (tham chiếu tháng 11/2026)

Bảng dưới đây rút từ trang [Gradle Compatibility Matrix](https://docs.gradle.org/current/userguide/compatibility.html), trong đó các mốc liên quan cần được đọc theo chính version release khi triển khai:

| Java/JDK | Gradle tối thiểu hỗ trợ **toolchain** | Gradle tối thiểu hỗ trợ **chạy Gradle** | Ghi chú |
|---:|---|---|---|
| 8 | N/A trong bảng toolchain lịch sử | 2.0; Gradle 9 daemon không hỗ trợ JDK 8 | Legacy build, không chọn JDK 8 làm Gradle daemon trên Gradle 9 |
| 11 | N/A trong bảng toolchain lịch sử | 5.0; Gradle 9 daemon không hỗ trợ JDK 11 | Có thể tiếp tục target Java 11 bằng JDK phù hợp |
| 17 | 7.3 | 7.3 | Mốc phù hợp để bắt đầu xem xét nâng từ JDK 11 |
| 18 | 7.5 | 7.5 | Kiểm tra plugin và build script |
| 19 | 7.6 | 7.6 | Kiểm tra plugin và build script |
| 20 | 8.1 | 8.3 | Toolchain sớm hơn runtime Gradle |
| 21 | 8.4 | 8.5 | Mốc thường gặp khi nâng JDK 17 → 21 |
| 22 | 8.7 | 8.8 | Toolchain sớm hơn runtime Gradle |
| 23 | 8.10 | 8.10 | Hai mốc trùng nhau |
| 24 | 8.14 | 8.14 | Không suy từ hỗ trợ Java 23 |
| 25 | 9.1.0 | 9.1.0 | Cần Gradle 9.x tương ứng |
| 26 | 9.4.0 | 9.4.0 | Cần Gradle 9.x tương ứng |
| 27 | 9.8.0 | 9.8.0 | Kiểm tra JDK 27 và plugin ở release cụ thể |

**Cách hiểu đúng N/A:** đây là ký hiệu của bảng compatibility ở cột toolchains cho các JDK cũ, không có nghĩa Gradle mới không thể biên dịch code có target 8/11. Khả năng hỗ trợ compile/test với toolchain còn phụ thuộc task, JDK có thể được tìm thấy và bản Gradle đang chạy; đọc thêm ghi chú trong tài liệu version cụ thể.

**Giới hạn quan trọng của Gradle 9:** từ Gradle 9.0, **Gradle daemon cần JVM 17 trở lên**. Điều này không buộc artifact ứng dụng phải chạy trên Java 17; Gradle có thể dùng toolchain/`--release` để tạo code hỗ trợ Java thấp hơn khi build và plugin cho phép. Một số thành phần client/wrapper có yêu cầu JVM khác với daemon, nên không được kết luận bằng cách chỉ xem executable wrapper.

Những mốc trong bảng là **mức hỗ trợ theo Gradle core**. Một Spring Boot plugin, Kotlin Gradle plugin, Android Gradle plugin, annotation processor hoặc code quality plugin có thể yêu cầu Gradle cao hơn, thấp hơn hay chỉ hỗ trợ một dải cụ thể. Do đó, tổ hợp “Gradle core hỗ trợ Java 25” chưa chứng minh toàn bộ build của sản phẩm hỗ trợ Java 25.

### 2.2. Ví dụ chọn sai và chọn đúng Gradle/JDK

**Tình huống A:** Dự án vẫn dùng Gradle 7.6 nhưng đặt `JAVA_HOME` thành JDK 21.

- Gradle 7.6 không nằm trong dải chính thức chạy trên Java 21.
- Lệnh `./gradlew --version` hoặc lúc cấu hình project có thể lỗi do Gradle/Groovy/class-file support.
- Sửa bằng nâng Gradle Wrapper tới release hỗ trợ **chạy trên Java 21** (từ 8.5), và nâng plugin tương ứng.
- Không chỉ sửa `sourceCompatibility = 21`, vì cấu hình compiler không giải quyết runtime của Gradle.

**Tình huống B:** Muốn dùng JDK 21 để compile, nhưng Gradle 8.4 đang chạy trên JDK 17.

- Gradle 8.4 có hỗ trợ Java 21 qua toolchain.
- Gradle runtime vẫn là JDK 17, còn compiler được chọn từ JDK 21.
- Điều này hợp lệ với những task/toolchain được Gradle version đó hỗ trợ.
- Cần kiểm tra test JVM và runtime production riêng; không mặc định test đang chạy trên 21 chỉ vì compiler dùng 21.

**Tình huống C:** Dự án dùng Gradle 9 và app phải chạy trên Java 11.

- Gradle daemon chạy JDK 17+.
- Java source có thể được biên dịch với release 11 nếu JDK compiler và plugin đáp ứng.
- Test phải chạy trên Java 11 nếu đây là baseline được hỗ trợ.
- Nếu dependency chứa bytecode Java 17 hoặc dùng API chỉ có trên JDK 17, artifact vẫn không chạy Java 11 dù code dự án được target 11.

### 2.3. Ma trận không phải dự đoán tương lai

Cách các cột được công bố có thể thay đổi khi Gradle ra phiên bản mới. Đối với JDK mới phát hành hoặc early-access release, có thể **Gradle hỗ trợ dùng làm toolchain trước khi hỗ trợ chạy daemon**. Không suy đoán từ xu hướng của các mốc trước. Lấy bảng của **đúng Gradle version** mà wrapper đang pin làm nguồn xác nhận và cập nhật hồ sơ migration khi thay version.

## 3. Ma trận Apache Maven – JDK: không giống Gradle

Maven không công bố cùng một bảng “toolchains vs running Maven” theo kiểu Gradle. Điều cần tách:
- **Maven core** yêu cầu JDK tối thiểu để chạy `mvn`.
- **Maven plugin** được phát hành độc lập với Maven core và có yêu cầu Maven/JDK riêng.
- **Toolchains** cho phép compiler, Surefire, Javadoc và các plugin hỗ trợ dùng JDK khác với JVM chạy Maven.
- **JDK release target** có thể thấp hơn JDK chạy Maven/`javac`.

### 3.1. Ma trận các nhánh Maven tham chiếu tháng 11/2026

| Nhánh Maven | JDK tối thiểu để chạy Maven | Ý nghĩa khi migration |
|---|---|---|
| Maven 3.9.x | Java 8 | Có thể chạy trên JVM mới khi plugin/dependency tương thích; không tự bảo đảm plugin hỗ trợ mọi JDK mới |
| Maven 3.10.x | Java 8 | Nhánh Maven 3 mới hơn; vẫn phải xác minh plugin và transport |
| Maven 4.0.0 RC (trước GA tại thời điểm tham chiếu) | Java 17 | Đây là chuyển đổi lớn về Maven core; cần kiểm tra plugin compatibility và readiness trước khi chọn production |

Theo [Apache Maven Releases History](https://maven.apache.org/docs/history) và [Apache Maven Download](https://maven.apache.org/download.cgi), các release cuối của nhánh Maven 3 có JDK baseline là 8; nhánh Maven 4 RC yêu cầu 17+. **Việc Maven 3 chạy được trên JDK 21 không mặc nhiên có nghĩa mọi plugin vốn viết cho JDK 8 sẽ chạy đúng trên JDK 21.**

Không nên tạo một ma trận kiểu “Maven 3.9 hỗ trợ đến Java X, Maven 3.10 hỗ trợ đến Java Y” nếu tài liệu Maven core không có cam kết đó. Kết quả thực tế phụ thuộc vào:
- JVM mà Maven đang chạy.
- Maven Plugin API tối thiểu và dependency của từng plugin.
- JDK mà compiler/test/instrumentation sử dụng.
- JDK/bytecode của thư viện dự án và plugin.
- Framework, build extension và hệ điều hành.

### 3.2. Đừng suy luận Maven 4 chỉ là Maven 3 đổi số version

Maven 4 mang thay đổi core/model/CLI/API và quá trình chuyển từ Maven 3 cần tài liệu migration riêng. Một plugin có thể chạy với Maven 3.9 nhưng chưa hỗ trợ Maven 4 RC; một core extension hoặc plugin custom có thể dựa vào API Maven cũ.

Vì vậy, đối với nhiệm vụ nâng JDK, nên quyết định có cần nâng major Maven trong cùng đợt hay không. Nếu Maven 3.x đang hỗ trợ JDK đích và plugin đã đủ mới, việc nâng Maven 4 cùng lúc có thể làm tăng diện tích thay đổi không cần thiết.

### 3.3. Maven Wrapper và Maven version thực tế

Nếu project có `mvnw`/`mvnw.cmd`, dùng wrapper thay vì Maven cài toàn cục. Kiểm tra cấu hình wrapper và version nó tải, không chỉ chạy `mvn -version` của máy local.

~~~bash
./mvnw -version
~~~

Windows PowerShell:

~~~powershell
.\mvnw.cmd -version
~~~

`mvn -version` và `./mvnw -version` có thể báo **hai Maven version khác nhau**. Cần ghi riêng khi làm inventory. Wrapper kiểm soát Maven distribution nhưng không tự pin đầy đủ JDK, plugin, dependency hoặc truststore.

## 4. Ma trận đầy đủ hơn: core, plugin, compiler, test, runtime

Ma trận Gradle/Maven ↔ JDK mới chỉ là lớp ngoài. Trong một dự án Java thực tế, nên lập bảng quyết định theo những trục sau:

| Trục | Giá trị ví dụ | Cần xác nhận |
|---|---|---|
| Build tool | Gradle 9.x hoặc Maven 3.9/3.10 | Có hỗ trợ JVM chạy build không |
| Build runtime | Temurin JDK 21 | Daemon/Maven core có dùng đúng binary không |
| Java compiler | JDK 21 toolchain | Plugin compiler có chọn đúng JDK không |
| Java SE target | `--release 17` | Không gọi nhầm API Java 21 |
| Unit tests | JDK 17 | Artifact hoạt động trên baseline không |
| Integration tests | JDK 17 và JDK 21 | Runtime, TLS, DB driver, module system đúng không |
| Framework/plugin | Spring Boot, Kotlin, JaCoCo, annotation processor | Version hỗ trợ build tool/JDK/class-file target không |
| Application runtime | JDK 17 hoặc 21 image | Bytecode/dependency và cấu hình runtime tương thích không |
| Artifact | JAR/WAR/container | Đường đóng gói, manifest, classpath không kéo nhầm thư viện |
| CI agent | Linux/Windows/macOS | Có toolchain/JDK đúng vendor/architecture không |

### 4.1. Tool plugin có vòng đời riêng

Các plugin thông dụng cần kiểm tra độc lập:
- **Gradle plugins:** Java/Kotlin/Groovy/Scala, Spring Boot, Android Gradle Plugin, protobuf, Shadow, SpotBugs, Checkstyle, JaCoCo, OpenRewrite.
- **Maven plugins:** Compiler, Surefire, Failsafe, Javadoc, Shade, Enforcer, Toolchains, JaCoCo, Dependency, WAR/JAR plugin.
- **Compiler integrations:** Lombok, MapStruct, Dagger, annotation processors, Kotlin KAPT/KSP, Error Prone.
- **Runtime/codegen tools:** Byte Buddy, ASM, Mockito, test engines, OpenAPI/gRPC generators, Kotlin compiler.

Một plugin build có thể lỗi trước khi biên dịch application source, hoặc chỉ lỗi sau khi gặp class file của JDK mới. Khi nâng JDK, cần pin hoặc nâng từng plugin tới version công bố tương thích; không chạy theo `latest.release` không có kiểm soát.

### 4.2. Spring Boot và Android là lớp ràng buộc bổ sung

Một project dùng Spring Boot plugin có **ít nhất ba ma trận**:
1. Java baseline của Spring Boot version.
2. Gradle/Maven version hỗ trợ bởi Spring Boot plugin.
3. JVM dùng chạy Gradle/Maven và JDK toolchain.

Dự án Android có thêm ma trận của Android Gradle Plugin, Gradle và JDK chạy AGP; không thể suy từ Gradle core một mình. Khi xây build matrix cho Android, lấy compatibility policy của AGP chính xác đang sử dụng.

Một tổ hợp chỉ nên đánh dấu “đã hỗ trợ” khi **mọi ràng buộc giao nhau đều thỏa mãn**.

## 5. Kiểm tra JDK và build tool thực tế trong dự án

Đừng bắt đầu sửa `pom.xml` hoặc `build.gradle` trước khi có inventory.

### 5.1. Gradle

Trên Linux/macOS:

~~~bash
./gradlew --version
java -version
javac -version
echo "$JAVA_HOME"
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat --version
java -version
javac -version
$env:JAVA_HOME
Get-Command java -All
Get-Command javac -All
~~~

`./gradlew --version` giúp biết Gradle distribution và JVM mà nó chọn. Nếu dùng Gradle daemon JVM criteria hoặc cấu hình IDE riêng, kiểm tra **JVM của daemon thực hiện build**, không chỉ client/wrapper. Với các Gradle version hiện đại, có thể liệt kê JDK toolchain đã phát hiện:

~~~bash
./gradlew javaToolchains
~~~

Nếu task `javaToolchains` không có ở phiên bản dự án, xem tài liệu và task của đúng Gradle version; không tự tạo kết luận JDK đang thiếu chỉ vì một lệnh không tồn tại.

### 5.2. Maven

~~~bash
./mvnw -version
java -version
javac -version
~~~

Hoặc nếu dự án không có wrapper:

~~~bash
mvn -version
~~~

Kiểm tra POM hiệu lực:

~~~bash
./mvnw help:effective-pom
~~~

Với multi-module, parent POM, pluginManagement, profile và property có thể thay đổi version cuối của plugin hoặc compiler settings. Đừng kết luận chỉ bằng một đoạn của POM con.

### 5.3. Kiểm tra artifact sau build

Nếu nghi ngờ bytecode không đúng Java release:
 
~~~bash
javap -verbose -classpath build/libs/app.jar com.example.Main
~~~

Hoặc với JAR Maven:

~~~bash
javap -verbose -classpath target/app.jar com.example.Main
~~~

Tìm `major version`:
 
| Java | Class-file major |
|---:|---:|
| 8 | 52 |
| 11 | 55 |
| 17 | 61 |
| 21 | 65 |
| 25 | 69 |
| 26 | 70 |
| 27 | 71 |

Đối với một JAR có nhiều class, cần kiểm tra tất cả class cần chạy trên runtime đích, kể cả dependency. Multi-release JAR có thể chứa class với major cao hơn bên dưới `META-INF/versions/N` mà không phá runtime cũ nếu được đóng gói đúng quy tắc; không đánh dấu tất cả entry vượt mức như một lỗi tự động.

## 6. Gradle Wrapper: khóa version build tool

Gradle Wrapper gồm script launcher và cấu hình distribution, thường nằm trong:

~~~text
gradlew
gradlew.bat
gradle/wrapper/gradle-wrapper.properties
gradle/wrapper/gradle-wrapper.jar
~~~

Một property thường gặp:

~~~properties
distributionUrl=https\://services.gradle.org/distributions/gradle-9.1.0-bin.zip
~~~

Đây là ví dụ version, **không phải yêu cầu project nào cũng phải dùng Gradle 9.1.0**. Version thực tế phải được chọn theo JDK và plugin compatibility của dự án. Với distribution được tải từ bên ngoài, nên dùng checksum verification và repository/distribution URL đáng tin cậy theo chính sách supply chain.

### 6.1. Nâng Wrapper có kiểm soát

Ví dụ khi đã quyết định phiên bản phù hợp:

~~~bash
./gradlew wrapper --gradle-version 9.1.0
~~~

Một số quy trình Gradle khuyến nghị chạy wrapper task lần thứ hai bằng wrapper mới để cập nhật wrapper scripts/JAR theo distribution vừa chọn. Sau thay đổi, kiểm tra file cấu hình, các script được version control và checksum nếu áp dụng.

Nếu Gradle cũ **không chạy được trên JDK mới**, đừng đặt `JAVA_HOME` sang JDK mới rồi hy vọng task wrapper vẫn chạy. Có thể:
1. Chạy Gradle cũ với **JDK mà nó hỗ trợ**.
2. Nâng wrapper lên version được chọn.
3. Chạy wrapper mới dưới JDK đích.
4. Mới tiếp tục sửa plugin/build script và chạy verification.

Khi chuyển Gradle 8 sang 9, kiểm tra deprecations và plugin API vì đây là nâng major build tool độc lập với nâng JDK.

### 6.2. JVM chạy Gradle khác toolchain được khai báo

Với Gradle hiện đại, Java toolchain của dự án không nhất thiết điều khiển JVM chạy daemon. Mỗi loại có cơ chế riêng:
- `JAVA_HOME`, `PATH`, cấu hình IDE hoặc daemon JVM criteria ảnh hưởng JVM chạy build.
- `java.toolchain.languageVersion` ảnh hưởng JVM/JDK mà JavaCompile, Test, Javadoc và một số task hỗ trợ sử dụng.
- `options.release` ảnh hưởng ngữ nghĩa source/API/bytecode mà compiler cho phép.

Do đó, khi dùng Gradle 9:
 
~~~text
Gradle daemon: JDK 21
Java toolchain: JDK 17
Artifact target: Java 17
Test runtime: JDK 17
Production runtime: Java 17 hoặc 21 theo support statement
~~~

Tổ hợp này có thể hợp lệ; không cần mọi dòng là JDK 21.

## 7. Gradle Java Toolchains và --release

### 7.1. Cấu hình toolchain trong Groovy DSL

Ví dụ `build.gradle`:

~~~groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
~~~

Diễn giải:
- Gradle chạy trên daemon JVM riêng và phải thỏa ma trận Gradle/JDK.
- `java.toolchain` yêu cầu một compiler JDK 21 cho những task được cấu hình phù hợp.
- `options.release = 17` yêu cầu compiler tuân theo ngôn ngữ, API Java SE và class-file target của Java 17.
- Artifact **không được phép dùng API Java SE chỉ có trên Java 21** nếu dùng `--release 17` đúng cách.

Đây là cách phân biệt **JDK dùng để biên dịch** với **runtime floor của artifact**.

### 7.2. Cấu hình tương đương trong Kotlin DSL

Ví dụ `build.gradle.kts`:

~~~kotlin
plugins {
    java
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(17)
}
~~~

Hai DSL dùng các API cú pháp khác nhau; không copy Groovy DSL trực tiếp sang Kotlin DSL. Tên API có thể thay đổi theo Gradle release, vì vậy thực hiện ví dụ với chính build tool đang dùng.

### 7.3. --release khác sourceCompatibility/targetCompatibility

Ví dụ cấu hình cổ điển:

~~~groovy
java {
    sourceCompatibility = JavaVersion.VERSION_17
    targetCompatibility = JavaVersion.VERSION_17
}
~~~

Điều này điều khiển source syntax và class-file target nhưng **không hoàn toàn ngăn code gọi một số API chỉ xuất hiện trên JDK mới** nếu compiler/classpath cung cấp những API đó.

Ví dụ khi compile với JDK 21 và chỉ đặt source/target Java 17, code có thể vô tình dùng `SequencedCollection` vốn không có trên Java 17, dẫn tới lỗi ở runtime cũ. Sử dụng `--release 17` giúp compiler kiểm tra API Java SE của target release, giảm kiểu sai sót này.

Tuy nhiên, `--release` chỉ ràng buộc Java SE API do compiler hiểu; nó **không tự xác nhận dependency bên thứ ba** có hỗ trợ Java 17. Một JAR dependency chứa class file major 65 vẫn có thể khiến consumer/runtime Java 17 thất bại. Cần kiểm tra dependency graph và chạy test trên JDK đích.

### 7.4. Test trên JDK khác compiler

Nếu muốn compile bằng JDK 21 nhưng chạy test trên JDK 17:

~~~groovy
def java17Launcher = javaToolchains.launcherFor {
    languageVersion = JavaLanguageVersion.of(17)
}

tasks.withType(Test).configureEach {
    javaLauncher = java17Launcher
}
~~~

Đây là ví dụ Gradle Java plugin, cần đảm bảo JDK 17 có thể được tìm thấy hoặc provisioning theo cấu hình. Với các task custom JavaExec, integration test plugin, forked test worker hoặc Kotlin compiler, cần kiểm tra từng task có áp dụng toolchain hay không; không suy đoán tất cả forked process dùng cùng JVM.

### 7.5. Toolchain không luôn tự tải được JDK

Gradle có khả năng phát hiện JDK đã cài và, khi được cấu hình repository provisioning phù hợp, có thể tải toolchain. Nhưng:
- Môi trường offline/air-gapped có thể không tải được.
- Version Gradle/plugin có thể yêu cầu cấu hình repository cung cấp JDK.
- Proxy, certificate, checksum và policy license có thể chặn download.
- Vendor/implementation/architecture specification có thể không khớp với JDK có sẵn.
- CI cần reproducibility; nên pin hoặc ghi nguồn JDK và image nếu dự án yêu cầu.

Nếu hiện thông báo “No matching toolchains found”, đừng sửa `options.release` trước; hãy kiểm tra JVM đã cài, path và resolver toolchain.

## 8. Maven Compiler Plugin: --release và toolchains

### 8.1. Biên dịch code hỗ trợ Java 17

Ví dụ `pom.xml` với phiên bản Compiler Plugin được pin:

~~~xml
<project>
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>orders-service</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
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
~~~

Bản Plugin 3.16.0 ở đây minh họa một version có tham số `release`; dự án thực tế cần xác minh version plugin hỗ trợ core Maven và JDK được chọn. Theo tài liệu Compiler Plugin, dùng `maven.compiler.release` được ưu tiên hơn chỉ dựa vào `source` và `target`.

Với javac từ JDK 9+, `--release 17` chỉ có ý nghĩa khi compiler hỗ trợ target Java 17; JDK 8 không thể compile source theo Java 17. Một JDK compiler mới cũng chỉ hỗ trợ một tập target release được phép, không nhất thiết mọi Java lịch sử.

### 8.2. Maven chạy JDK 21, compiler chọn JDK 17

Maven Toolchains Plugin hỗ trợ tách Java runtime của Maven khỏi JDK do plugin biết dùng toolchain lựa chọn. Có thể khai báo toolchain requirement trong POM. Ví dụ truyền toolchain riêng cho Compiler Plugin:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <version>3.16.0</version>
    <configuration>
        <release>17</release>
        <jdkToolchain>
            <version>17</version>
        </jdkToolchain>
    </configuration>
</plugin>
~~~

Để hoạt động, một JDK khớp toolchain phải được Maven/plugin tìm thấy hoặc khai báo trong cấu hình toolchain. Ví dụ này yêu cầu compiler JDK 17 và release 17, trong khi JVM chạy Maven có thể là JDK 21.

Không đồng nhất `<jdkToolchain>` với `<release>`:
- `jdkToolchain` chọn **JDK compiler**.
- `release` chọn **Java SE API/bytecode target** của phép biên dịch.

### 8.3. Toolchains Plugin và toolchains.xml

Một cách cổ điển là khai báo `~/.m2/toolchains.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<toolchains>
  <toolchain>
    <type>jdk</type>
    <provides>
      <version>17</version>
    </provides>
    <configuration>
      <jdkHome>/opt/jdks/jdk-17</jdkHome>
    </configuration>
  </toolchain>
  <toolchain>
    <type>jdk</type>
    <provides>
      <version>21</version>
    </provides>
    <configuration>
      <jdkHome>/opt/jdks/jdk-21</jdkHome>
    </configuration>
  </toolchain>
</toolchains>
~~~

Đường dẫn trong ví dụ là placeholder Linux; trên Windows phải thay bằng đường dẫn JDK thật. Tệp này thường là cấu hình máy/CI, không nên chứa secret hoặc commit path máy cá nhân vào repository chung.

Từ Maven Toolchains Plugin 3.2.0 có cơ chế tự khám phá JDK và goal `toolchains:select-jdk-toolchain`. Các version plugin mới hơn có goal in JDK được tìm thấy:

~~~bash
./mvnw toolchains:display-discovered-jdk-toolchains
~~~

Sau khi thêm cấu hình plugin goal `select-jdk-toolchain` vào lifecycle, các plugin toolchain-aware có thể dùng JDK đã chọn. Tuy nhiên, **không phải mọi Maven plugin đều tự động hỗ trợ toolchain**; plugin custom có thể vẫn dùng `java.home` của Maven process hoặc tự gọi executable từ `PATH`.

### 8.4. Test JVM riêng với Surefire/Failsafe

Maven Surefire/Failsafe có thể cấu hình JDK toolchain cho test fork trong các version hỗ trợ. Một ví dụ cấu hình ý định chạy unit test bằng JDK 17:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-surefire-plugin</artifactId>
    <version>3.5.4</version>
    <configuration>
        <jdkToolchain>
            <version>17</version>
        </jdkToolchain>
    </configuration>
</plugin>
~~~

Đây là ví dụ về vị trí cấu hình; khi đưa vào dự án cần kiểm tra version cụ thể có sẵn trong repository và tài liệu của plugin. Nếu Surefire không fork JVM trong một cấu hình nào đó hoặc plugin custom điều khiển test runtime khác, cần xem effective configuration thực tế. Đối với integration test, kiểm tra Failsafe và external service/container JDK riêng.

Một Maven build dùng JDK 21 cho process Maven, 17 cho compiler và 17 cho test có thể hoàn toàn có chủ đích, miễn toàn bộ plugin, classpath và artifact version đều đáp ứng.

## 9. Ma trận plugin phải được kiểm tra riêng

### 9.1. Maven plugin version có thể nâng yêu cầu JDK tối thiểu

Một phiên bản mới của Compiler, Surefire, JaCoCo hoặc plugin khác có thể yêu cầu Maven core cao hơn hay JDK cao hơn. Ngược lại, một plugin cũ có thể dùng thư viện nội bộ hoặc API bị hạn chế trên JDK mới.

Các nguồn xác nhận:
- Trang “System Requirements” của đúng Maven plugin version.
- Release notes và compatibility page của plugin.
- POM và transitive dependency của plugin.
- `mvn help:effective-pom` để biết phiên bản plugin thật sự đang chạy.

Trong multi-module project, plugin version có thể đến từ parent `pluginManagement`, corporate BOM/parent, profile hoặc cấu hình module; không chỉ từ phần XML đang nhìn thấy.

### 9.2. Gradle plugin binary/API compatibility

Gradle major version mới có thể xóa/deprecate API build tool mà plugin cũ dựa vào. Nếu plugin được viết bằng Groovy/Kotlin, các thay đổi compiler/embedded runtime hoặc Kotlin DSL cũng có thể ảnh hưởng. Các plugin xử lý bytecode (JaCoCo, SpotBugs, bytecode enhancer, instrumentation) cần hỗ trợ class-file version mà compiler mới tạo.

Khi nâng Gradle 8 lên 9:
- Xem changelog Gradle về API breaking.
- Xem compatibility range của từng plugin.
- Kiểm tra deprecation warnings trước khi chuyển major.
- Cập nhật wrapper và plugin theo các bước nhỏ, ghi lại diff/version.
- Không mặc định plugin hỗ trợ Java toolchain chỉ vì Gradle core hỗ trợ.

### 9.3. Kotlin, Groovy, Scala và annotation processor

Trong dự án đa ngôn ngữ, cần ít nhất:
- Gradle/Maven version.
- Kotlin/Groovy/Scala compiler và plugin version.
- Compiler JDK/JVM target.
- Annotation processors (Lombok, MapStruct, Dagger, v.v.).
- Bytecode visitor và test instrumentation.

Một Kotlin Gradle plugin có thể yêu cầu phiên bản Gradle tối thiểu hoặc chỉ xác minh một dải Gradle cụ thể. Build có thể chạy Java compilation thành công nhưng fail ở Kotlin compilation. Một annotation processor có thể dùng compiler internals và fail khi nâng JDK dù Java source hợp lệ.

**Một build tool matrix đúng nhưng compiler plugin matrix sai vẫn là tổ hợp không được hỗ trợ**.

## 10. Chẩn đoán lỗi theo tầng tương thích

| Triệu chứng | Tầng nghi ngờ đầu tiên | Điều cần xem |
|---|---|---|
| Gradle không khởi động trên JDK mới | Gradle runtime vs JDK | `./gradlew --version`, compatibility matrix |
| `Unsupported class file major version ...` khi Gradle cấu hình project | Groovy/ASM/Gradle/plugin không đọc class bytecode | Gradle & plugin version, JDK dùng build, JAR plugin |
| Maven báo plugin yêu cầu Java cao hơn | Maven plugin JVM requirements | `mvn -version`, plugin dependency/JDK requirement |
| `No matching toolchains found` | JDK toolchain discovery/provisioning | `javaToolchains`, toolchains.xml, JDK path/vendor |
| `invalid source release: 21` | Compiler JDK quá cũ | `javac -version` thật sự được task dùng |
| `release version 17 not supported` | Compiler không hỗ trợ `--release 17` | JDK compiler và plugin options |
| `cannot find symbol` với API mới/cũ | Source/API target hoặc dependency | `--release`, classpath, dependency tree |
| `UnsupportedClassVersionError` khi chạy ứng dụng | Artifact/dependency bytecode cao hơn JVM runtime | `javap -verbose`, runtime `java -version` |
| `NoSuchMethodError` trong test | Dependency conflict hoặc API binary incompatibility | Dependency graph và class đang nạp |
| `InaccessibleObjectException` trên JDK mới | JPMS reflection, framework/plugin cũ | Stack trace, version framework, module access |
| `No tests found` / test engine crash | Test framework/plugin/JDK mismatch | Surefire/Gradle Test/JUnit runner configuration |
| Build local thành công nhưng CI fail | JDK/OS/architecture khác, plugin cache khác | Wrapper, Java vendor/build, toolchain, effective options |
| Test chạy JDK 21, production JDK 17 bị lỗi | Test runtime không đúng baseline | Ma trận runtime và class-file/API checks |
| Lỗi TLS/truststore sau nâng JDK | Runtime JDK và bảo mật, không chỉ build tool | Cipher, certificate, truststore, network protocol |

### 10.1. Không lạm dụng JVM flags để che lỗi build tool

Ví dụ, thêm `--add-opens` có thể giúp một framework dùng deep reflection trong ngắn hạn, nhưng không làm Gradle cũ hỗ trợ class-file version mới hoặc sửa một compiler quá cũ. Tương tự, `--enable-preview` không được dùng để thay một thiết lập `--release` sai, và thay `JAVA_HOME` không tự cập nhật dependency plugin.

Chọn giải pháp ở đúng tầng có lỗi:
- Gradle runtime thiếu hỗ trợ JDK: nâng Gradle Wrapper hoặc đổi JVM chạy Gradle.
- Compiler quá cũ: chọn JDK toolchain mới.
- Plugin không tương thích: nâng plugin/version hoặc thay plugin.
- Bytecode artifact vượt mức runtime: sửa release target/dependency hoặc nâng runtime floor.
- JPMS/API behavior: sửa code/framework và kiểm tra runtime.

### 10.2. Khi `./gradlew --version` cũng không chạy

Nếu Gradle được pin quá cũ để khởi động dưới JDK hiện tại, có thể dùng một JDK cũ vẫn được Gradle đó hỗ trợ chỉ để chạy wrapper task và bước migration build tool. Không dùng JDK cũ không còn bản vá cho workload production chỉ vì build cũ yêu cầu; đây là việc tách **build migration environment** khỏi **target production runtime**.

Với build có ràng buộc security nghiêm ngặt, JDK cũ cần chạy trong môi trường cô lập phù hợp với chính sách tổ chức, và được loại bỏ khi hoàn thành nâng wrapper.

## 11. Ví dụ thiết kế một ma trận project khả thi

Giả sử ứng dụng công bố hỗ trợ runtime Java 17 và Java 21, nhưng CI đang nâng build tool.

| Tầng | Cấu hình dự kiến | Vì sao |
|---|---|---|
| Build tool | Gradle 9.x đã được chọn theo plugin matrix | Gradle daemon dùng JDK 17+ |
| Gradle daemon | JDK 21 | Thuận tiện cho build CI, nằm trong dải hỗ trợ |
| Compiler toolchain | JDK 21 | Compiler được pin |
| Target source/API/bytecode | `--release 17` | Giữ runtime floor Java 17 |
| Test lane A | JDK 17 | Phát hiện API/dependency không chạy baseline |
| Test lane B | JDK 21 | Phát hiện khác biệt runtime mới |
| App runtime image A | JDK 17 | Release phải tiếp tục hỗ trợ |
| App runtime image B | JDK 21 | Đích migration |
| Code quality/instrumentation | Plugin version có hỗ trợ JDK 21 và Gradle 9 | Tránh lỗi build giữa chừng |
| Dependency graph | Pin version, kiểm tra bytecode/transitive | Tránh JAR chỉ chạy trên Java 21 |

Nếu thay bằng Maven, có thể giữ Maven 3.9/3.10 chạy trên JDK 21, compiler toolchain 21 + release 17 và test toolchain 17/21 tương ứng. Điểm quan trọng không phải mọi tool cùng version, mà là **tổ hợp đã được xác minh và version hóa**.

### 11.1. Một build với nhiều Java release targets

Thư viện có thể cần phát hành artifact Java 8 để giữ consumer cũ, trong khi server mới dùng Java 21. Không nên đặt cùng một release target cho mọi module nếu contract khác nhau.

Ví dụ:
 
~~~text
legacy-client-api   -> Java 8 bytecode / API
shared-protocol     -> Java 11 bytecode / API
orders-service      -> Java 21 bytecode / API
migration-tools     -> Java 21 build utility
~~~

Khi đó build tool/daemon có thể dùng JDK 21, nhưng mỗi module/task compile cần toolchain/release phù hợp. Đồng thời test từng module trên **runtime tối thiểu được công bố**. Nếu một module Java 8 phụ thuộc trực tiếp vào artifact Java 21, thiết lập `--release 8` cho source của module đó không làm dependency magically trở nên tương thích.

## 12. Ma trận thử nghiệm trong CI

Một build pipeline đáng tin cậy thường có hai tầng:

**Tầng A: Build compatibility**
- Gradle/Maven version đã pin có khởi động trên JDK build đã pin?
- Plugin và toolchain có resolve đúng không?
- Build artifact có class-file/API target đúng không?

**Tầng B: Runtime compatibility**
- Test JDK thấp nhất có chạy được artifact không?
- Test JDK mới nhất có thay đổi behavior không?
- Dependency, TLS, serialization, reflection và class loading có hoạt động không?

Ví dụ ý tưởng pipeline:

~~~text
Checkout repository
       |
       v
Verify wrapper distribution + checksum
       |
       v
Select build JVM (e.g., JDK 21)
       |
       v
Resolve plugins/dependencies + toolchains
       |
       v
Compile with --release 17
       |
       +-------> Unit + integration tests on JDK 17
       |
       +-------> Unit + integration tests on JDK 21
       |
       v
Inspect artifact class-file/dependencies
       |
       v
Package + smoke test in target runtime image
       |
       v
Publish artifact with toolchain provenance
~~~

### 12.1. Không dùng ma trận quá rộng mà thiếu chủ đích

Nếu dự án chỉ tuyên bố hỗ trợ Java 17/21, không cần chạy mọi JDK 8–27. Một ma trận rộng không được duy trì có thể tốn chi phí mà không mang lại bằng chứng đúng contract. Thay vào đó:
- Chọn runtime floor và các LTS/các JDK có đối tượng sử dụng thật.
- Dùng exact JDK vendor/patch image cho release path.
- Duy trì lane thử candidate JDK cho migration tiếp theo.
- Chạy plugin/toolchain upgrade lane riêng nếu cần.
- Ghi kết quả, không chỉ một badge “build green” chung.

### 12.2. Build reproducibility và nguồn gốc artifact

Cần lưu:
- Wrapper version và checksum/distribution source.
- JVM dùng build: vendor, release, build number.
- Compiler toolchain/JDK: version/vendor/path hoặc image digest.
- `--release` và các compiler flags có ảnh hưởng ABI.
- Gradle/Maven plugin versions đã resolve.
- Dependency lockfile hoặc resolved dependency tree.
- Test runtime JDK và container image.
- Build logs, artifact checksum và SBOM khi thuộc chính sách.
- Thông tin hệ điều hành/architecture nếu có native dependency.

Nếu chỉ ghi “Java 21” trong README, rất khó điều tra vì Gradle 8.4 chạy JDK 17 dùng toolchain Java 21 khác với Gradle 8.5 chạy trực tiếp JDK 21, và plugin có thể cư xử khác.

## 13. Quy trình nâng cấp từ JDK cũ sang JDK mới

### Bước 1: Chụp baseline

Ghi:
 
~~~bash
java -version
javac -version
./gradlew --version
# hoặc
./mvnw -version
~~~

Thu Gradle Wrapper/Maven Wrapper, plugin versions, compiler flags và container image. Tạo một build baseline có kết quả kiểm thử và artifact checksum.

### Bước 2: Chọn JDK runtime mục tiêu và support window

Đặt câu hỏi:
- Sản phẩm chỉ chuyển lên JDK 21 hay tiếp tục chạy Java 17?
- Consumer bên ngoài có dùng thư viện đã publish dưới Java 8/11 không?
- CI/build host có thể nâng JDK khác với production không?
- Framework/plugin nào giới hạn version JDK hoặc build tool?
- Có app server, Android, JNI/native library hay custom JDK image không?

Mục tiêu là một ma trận được phê duyệt, không đơn thuần một Java version mới.

### Bước 3: Chọn build tool version có hỗ trợ JDK build

Với Gradle, lấy cột **running Gradle** đúng JDK dự kiến chạy daemon. Với Maven, lấy yêu cầu JDK core và plugin. Không nâng tất cả plugin đồng thời nếu không cần thiết; có thể tách nâng tool khỏi nâng JDK application.

### Bước 4: Cập nhật wrapper và plugin theo nhóm

- Nâng Gradle Wrapper hoặc Maven distribution được pin.
- Nâng plugin đang chặn compatibility theo support matrix.
- Xem release notes để xử lý deprecation/build DSL changes.
- Giữ riêng commits hoặc PRs khi có thể để dễ khoanh vùng.
- Không bỏ qua các kiểm tra dependency/security khi nâng version.

### Bước 5: Cấu hình toolchain và --release

Chọn JDK compiler, Java SE target và test runtime rõ ràng. Nếu cần giữ Java 17, đặt release 17 và chạy test trên JVM 17 thực tế. Nếu sản phẩm nâng runtime floor lên Java 21, cập nhật support statement và dependency constraints thay vì lặng lẽ đổi target.

### Bước 6: Chạy matrix test

Chạy build trên JDK build được hỗ trợ, test trên các runtime đích, smoke test artifact ở môi trường tương đương production. Đặc biệt kiểm tra:
- Java reflection/module access.
- Serialization và JSON/Protobuf.
- TLS/truststore.
- Annotation processors và instrumentation.
- Dependency bytecode cao hơn runtime floor.
- Scheduled jobs, timezone và thay đổi mặc định của JDK.
- Container startup và JVM flags.

### Bước 7: Rollout/rollback có ranh giới rõ

Rollback build tool và rollback application runtime là hai thao tác khác nhau. Một JAR có class-file major Java 21 không thể được chạy lại trên JVM Java 17 chỉ vì rollback wrapper từ Gradle 9 xuống Gradle 8. Nếu có migration dữ liệu/giao thức, phải kiểm tra cả consumer cũ và rollback path của ứng dụng.

### Bước 8: Duy trì ma trận sau migration

Mỗi khi nâng JDK patch, Gradle/Maven version hoặc plugin quan trọng:
- Cập nhật ma trận đã pin.
- Kiểm tra compatibility chính thức theo release.
- Chạy các test lane được cam kết.
- Ghi artifact provenance.
- Xóa những cấu hình toolchain cũ không còn được hỗ trợ theo chính sách dự án.

## 14. Các lỗi suy luận thường gặp

- **“Java version trong `gradlew --version` là target bytecode”:** sai; đó là JVM chạy Gradle, không thay compiler release.
- **“Gradle hỗ trợ toolchain Java 21 nên Gradle 8.4 chạy trên JDK 21”:** sai; running Gradle Java 21 bắt đầu từ Gradle 8.5.
- **“Maven 3.9 chạy với JDK 21 nên mọi Maven plugin đều hỗ trợ JDK 21”:** sai; plugin có yêu cầu riêng.
- **“Gradle 9 không chạy trên Java 8 nên không thể build thư viện Java 8”:** sai; daemon runtime và compiler target khác nhau.
- **“Đặt source/target 17 là đủ để cấm API Java 21”:** sai; ưu tiên `--release 17`.
- **“Compiler có target 17 thì dependency chắc chắn chạy được Java 17”:** sai; kiểm tra bytecode/API của dependency.
- **“Đã cấu hình toolchain thì test chắc chắn chạy đúng JDK”:** cần kiểm tra task/plugin và test fork thực tế.
- **“Chuyển JAVA_HOME sang JDK mới sẽ tự cập nhật Gradle Wrapper”:** sai; wrapper version vẫn là version đã pin.
- **“Cập nhật Gradle/Maven core là đã cập nhật plugin”:** sai; plugin version có vòng đời độc lập.
- **“Build thành công ở IDE nghĩa CI đã tương thích”:** sai nếu Gradle JVM, toolchain, vendor hoặc plugin cache khác.
- **“JDK mới hơn luôn chạy mọi plugin cũ”:** không đúng khi plugin dựa vào JDK internals hoặc bytecode tooling cũ.
- **“Có thể nâng Gradle major mà không xem deprecation”:** dễ làm build script hoặc plugin custom hỏng.
- **“Thử mọi JDK là tốt nhất”:** nên chọn dải runtime có cam kết và track results.
- **“Maven Toolchains tự điều khiển mọi plugin”:** chỉ plugin toolchain-aware dùng toolchain tương ứng.
- **“Java 21 là cùng một runtime ở mọi nơi”:** vendor/patch/build, image, tzdb và security settings có thể khác.

## 15. Checklist trước khi chấp nhận ma trận build/JDK

- [ ] Đã xác định JDK runtime được sản phẩm hỗ trợ và JDK compiler mục tiêu.
- [ ] Đã ghi JDK vendor/patch/build cùng OS/architecture cho build/test/runtime.
- [ ] Đã biết Gradle Wrapper hoặc Maven Wrapper/distribution thực tế.
- [ ] Đã kiểm tra Gradle **running** compatibility với JDK daemon.
- [ ] Đã kiểm tra Gradle **toolchain** compatibility với JDK compiler/test.
- [ ] Nếu dùng Maven, đã xác minh core JVM requirement và từng plugin quan trọng.
- [ ] Đã pin Gradle/Maven version và checksum/source khi cần.
- [ ] Đã pin/kiểm tra plugin của framework, Kotlin/Groovy, annotation processor, bytecode tooling.
- [ ] Có cấu hình toolchain rõ, không dựa hoàn toàn vào JAVA_HOME ngẫu nhiên.
- [ ] Có `--release` phù hợp với runtime floor; không chỉ source/target.
- [ ] Đã kiểm tra bytecode class-file version và dependency graph sau build.
- [ ] Đã chạy test trên JDK thấp nhất được công bố hỗ trợ.
- [ ] Đã chạy test trên JDK mới mục tiêu, bao gồm integration và runtime behavior.
- [ ] Đã kiểm tra wrapper/IDE/CI/container không dùng JVM khác ngoài dự kiến.
- [ ] Đã ghi test kết quả theo version toolchain, không chỉ “build green”.
- [ ] Đã có kế hoạch nâng/rollback build tool và application runtime riêng.
- [ ] Ma trận được cập nhật khi nâng JDK hoặc Gradle/Maven/plugin version.

## 16. Tài liệu chính thức để cập nhật ma trận

Các mốc trong bài cần được kiểm tra lại tại thời điểm triển khai, nhất là khi một JDK/Gradle/Maven mới phát hành:

- [Gradle — Compatibility Matrix](https://docs.gradle.org/current/userguide/compatibility.html): JDK làm toolchain và JDK chạy Gradle.
- [Gradle — Toolchains for JVM Projects](https://docs.gradle.org/current/userguide/toolchains.html): JDK compiler/test, `--release`, nguồn toolchain và lựa chọn JDK.
- [Gradle — Upgrading to Gradle 9](https://docs.gradle.org/current/userguide/upgrading_major_version_9.html): thay đổi runtime floor, DSL/API/plugin.
- [Gradle — Releases](https://gradle.org/releases/): release notes và version distribution.
- [Apache Maven — Download](https://maven.apache.org/download.cgi): nhánh Maven hiện tại và JDK baseline.
- [Apache Maven — Releases History](https://maven.apache.org/docs/history): lịch sử release, trạng thái support, JDK minimum.
- [Apache Maven Compiler Plugin — Setting --release](https://maven.apache.org/components/plugins/maven-compiler-plugin/examples/set-compiler-release.html): phân biệt compiler release và source/target.
- [Apache Maven — Guide to Using Toolchains](https://maven.apache.org/guides/mini/guide-using-toolchains): JDK toolchains và plugin tích hợp.
- [Apache Maven Toolchains Plugin](https://maven.apache.org/plugins/maven-toolchains-plugin/): JDK discovery và toolchain selection.

Khi dùng link “current”, nội dung sẽ thay đổi theo release mới. Đối với báo cáo audit hoặc migration lâu dài, nên lưu ngày truy cập, version Gradle/Maven cụ thể và đường dẫn tài liệu theo version để có thể tái lập quyết định.

## 17. Kết luận

**Ma trận tương thích Maven/Gradle với JDK là một ma trận nhiều chiều, không phải bảng thay JDK rồi chạy lại lệnh build.** Với Gradle, luôn đọc riêng hai cột **toolchain support** và **running Gradle support**; với Maven, phân biệt yêu cầu JVM của Maven core với yêu cầu độc lập của từng plugin và JDK do toolchains chọn. Trong cả hai trường hợp, compiler target, test JVM, artifact dependency và production runtime vẫn là các lớp tương thích riêng.

Một quy trình Java migration bền vững là **kiểm kê wrapper/tool/plugin → chọn JDK build tương thích → cấu hình toolchain và --release → kiểm thử trên runtime floor và runtime mới → ghi provenance và cập nhật ma trận**. Khi các lớp được pin và xác minh độc lập, nhóm có thể nâng JDK hoặc build tool từng bước, phát hiện lỗi ở đúng tầng và tránh phát hành artifact chỉ chạy trên máy build nhưng không chạy ở môi trường khách hàng.
