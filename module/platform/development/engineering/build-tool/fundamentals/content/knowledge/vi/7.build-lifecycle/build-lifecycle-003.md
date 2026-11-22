# Kiểm chứng chất lượng trước khi coi artifact là hợp lệ

Một lệnh build kết thúc với mã thoát thành công cho biết các tác vụ được yêu cầu đã hoàn tất theo hợp đồng mà build tool đang biết. Điều đó chưa đủ để kết luận tệp JAR, WAR hoặc ZIP vừa tạo có thể phát hành và sử dụng an toàn. Artifact có thể thiếu tài nguyên, chứa nhầm cấu hình, bỏ sót lớp được sinh, tham chiếu thư viện không có ở môi trường chạy hoặc không tương thích với JDK mục tiêu.

Vì vậy, cần có bước **kiểm chứng artifact** trước khi coi sản phẩm build là hợp lệ. Việc kiểm chứng xác nhận rằng artifact đáp ứng các điều kiện đã định nghĩa: được tạo từ đúng nguồn và cấu hình, chứa đúng nội dung, vượt qua các kiểm thử cần thiết, có thể chạy hoặc được tiêu thụ theo mục đích, và có thông tin đủ để xác định tính toàn vẹn cũng như nguồn gốc.

## 1. Build thành công và artifact hợp lệ là hai kết luận khác nhau

Build tool thực hiện các tác vụ theo task graph hoặc lifecycle. Nếu mọi tác vụ nằm trong phạm vi lệnh chạy đều thành công, build tool có thể trả về trạng thái thành công. Phạm vi đó phụ thuộc vào lệnh được gọi và cấu hình của dự án.

Ví dụ:

- Một lệnh chỉ biên dịch có thể thành công dù chưa chạy kiểm thử.
- Một lệnh đóng gói có thể tạo JAR dù chưa chạy kiểm thử tích hợp.
- Kiểm thử có thể chạy trên class directory nhưng không phát hiện tài nguyên bị thiếu trong JAR cuối.
- Một artifact có thể tồn tại và có kích thước lớn hơn 0 nhưng chứa nhầm cấu hình môi trường.
- Build trên máy phát triển có thể thành công nhưng artifact không chạy được trên JRE/JDK hoặc container của môi trường đích.

Do đó, cần phân biệt ba trạng thái:

| Trạng thái | Ý nghĩa |
|---|---|
| Build task thành công | Các tác vụ được yêu cầu đã hoàn thành mà không báo lỗi. |
| Artifact đã được tạo | Tệp đầu ra tồn tại ở vị trí dự kiến. |
| Artifact được xác nhận hợp lệ | Artifact vượt qua các điều kiện kiểm chứng đã định nghĩa cho mục đích sử dụng hoặc phát hành. |

Một artifact hợp lệ luôn cần một **hợp đồng chấp nhận** (*acceptance contract*). Hợp đồng này mô tả sản phẩm cần có gì, phải tương thích với môi trường nào, phải vượt qua loại kiểm thử nào và bằng chứng nào cần được lưu lại. Không có một danh sách kiểm tra duy nhất phù hợp với mọi loại artifact: JAR thư viện, ứng dụng Spring Boot, WAR triển khai lên application server và ZIP chứa mã nguồn có các yêu cầu khác nhau.

## 2. Xác định điều kiện chấp nhận trước khi build

Trước khi chạy build, hãy xác định artifact sẽ được dùng vào việc gì và những điều kiện nào chứng minh nó sẵn sàng.

Với một JAR ứng dụng Java, các điều kiện có thể gồm:

- Build sử dụng đúng commit, phiên bản và cấu hình được yêu cầu.
- Mã nguồn biên dịch thành công bằng JDK phù hợp.
- Các kiểm tra tĩnh và kiểm thử bắt buộc đều đạt.
- JAR có manifest và entry point phù hợp nếu đây là ứng dụng chạy độc lập.
- Các lớp, tài nguyên và metadata cần thiết có mặt trong archive.
- Ứng dụng khởi động được trong môi trường tương đương môi trường triển khai.
- Các phụ thuộc runtime có thể được phân giải.
- Artifact có checksum, phiên bản và thông tin nguồn gốc để truy xuất.

Với một thư viện Java, điều kiện có thể khác: JAR phải chứa API công khai dự kiến, không đóng gói nhầm test class, có metadata cần thiết cho consumer, và một dự án thử nghiệm độc lập phải biên dịch hoặc chạy được khi dùng thư viện đó.

Với một ZIP mã nguồn, cần kiểm tra cấu trúc thư mục, tệp build cần thiết, phiên bản JDK mục tiêu, các thư viện nội bộ được đóng gói và khả năng build độc lập theo hợp đồng của gói.

Điều kiện chấp nhận nên cụ thể và có thể kiểm chứng. Câu “build phải tốt” không thể tự động hóa; câu “JAR phải có `com/example/App.class`, có manifest với `Main-Class`, và smoke test phải nhận được HTTP 200 ở endpoint health” có thể chuyển thành các bước kiểm tra rõ ràng.

## 3. Các lớp kiểm chứng trong vòng đời build

Một quy trình kiểm chứng thường gồm nhiều lớp. Mỗi lớp tìm một nhóm lỗi khác nhau.

```text
Xác định nguồn, JDK và cấu hình
             |
             v
       Biên dịch mã nguồn
             |
             v
       Kiểm tra tĩnh
             |
             v
       Unit tests
             |
             v
    Integration / contract tests
             |
             v
        Đóng gói artifact
             |
             v
    Kiểm tra cấu trúc và metadata
             |
             v
       Runtime smoke tests
             |
             v
  Integrity / provenance / policy
             |
             v
      Chấp nhận và phát hành
```

Không phải dự án nào cũng cần mọi lớp ở cùng mức độ. Tuy nhiên, nếu một lớp là điều kiện bắt buộc, nó phải được nối vào quy trình kiểm chứng và có khả năng làm build thất bại khi không đạt.

### Kiểm tra môi trường và đầu vào

Ghi nhận commit, phiên bản ứng dụng, JDK, build tool, dependency lock hoặc dependency constraints, profile và các tham số ảnh hưởng đến sản phẩm. Nếu build phụ thuộc biến môi trường, hãy xác định biến nào là bắt buộc và cách xử lý khi thiếu.

Kiểm tra đầu vào giúp tránh tình trạng build thành công từ nhầm nhánh, nhầm JDK, profile sai hoặc dữ liệu cũ còn sót trong workspace. Một artifact được tạo từ môi trường không xác định rất khó tái tạo khi có sự cố.

### Biên dịch

Compiler kiểm tra cú pháp, kiểu dữ liệu, symbol và các ràng buộc ngôn ngữ. Biên dịch thành công cho thấy mã nguồn trong phạm vi compiler xử lý có thể chuyển thành bytecode với cấu hình hiện tại.

Biên dịch không chứng minh logic chạy đúng. Nó cũng không nhất thiết xác nhận tất cả tài nguyên hoặc phụ thuộc runtime đều có mặt.

### Kiểm tra tĩnh

Các công cụ kiểm tra tĩnh có thể phát hiện quy ước code style, lỗi tiềm ẩn, API nguy hiểm, dependency không phù hợp hoặc lỗ hổng đã biết. Ví dụ gồm Checkstyle, PMD, SpotBugs, Error Prone và dependency vulnerability scanners.

Mỗi công cụ có phạm vi riêng. Checkstyle tập trung vào quy tắc định dạng và phong cách; SpotBugs phân tích bytecode để tìm một số mẫu lỗi; công cụ quét dependency đối chiếu thư viện với dữ liệu lỗ hổng. Kết quả của một công cụ không thay thế các lớp kiểm chứng khác.

### Unit tests

Unit test kiểm tra các thành phần nhỏ trong điều kiện được kiểm soát. Chúng hữu ích để phát hiện lỗi logic nhanh và xác định chính xác vị trí sai.

Unit test thường không chứng minh ứng dụng có thể kết nối database thật, đọc cấu hình từ artifact đã đóng gói hoặc hoạt động đúng khi chạy trong container triển khai.

### Integration và contract tests

Integration test xác nhận các thành phần phối hợp với nhau, ví dụ service với database, ứng dụng với message broker hoặc module với API bên ngoài. Contract test kiểm tra sự tương thích của giao tiếp giữa consumer và provider.

Các kiểm thử này cần môi trường và dữ liệu gần với điều kiện sử dụng. Nếu một dịch vụ phụ thuộc vào PostgreSQL, chạy kiểm thử trên H2 có thể không phát hiện khác biệt về SQL, transaction hoặc kiểu dữ liệu. Chọn môi trường kiểm thử theo rủi ro thực tế của ứng dụng.

### Kiểm chứng artifact sau đóng gói

Đây là bước quan trọng vì sản phẩm người dùng nhận được là archive cuối cùng, không phải thư mục lớp đã biên dịch trong workspace. Cần kiểm tra trực tiếp JAR/WAR/ZIP sau khi đóng gói.

### Kiểm thử runtime

Khởi chạy artifact trong môi trường tương đương môi trường triển khai và xác nhận hành vi quan trọng. Với service HTTP, có thể kiểm tra ứng dụng khởi động, endpoint health, kết nối phụ thuộc và một luồng nghiệp vụ đại diện.

## 4. Kiểm chứng trong Gradle: check, assemble và build

Với dự án Java dùng Gradle, Java plugin cung cấp các task lifecycle quen thuộc:

| Task | Vai trò |
|---|---|
| `compileJava` | Biên dịch mã nguồn chính. |
| `processResources` | Xử lý tài nguyên chính. |
| `test` | Chạy unit test qua test framework được cấu hình. |
| `check` | Task lifecycle gom các kiểm tra chất lượng được nối vào nó. |
| `jar` | Đóng gói lớp và tài nguyên thành JAR. |
| `assemble` | Task lifecycle dành cho việc tạo artifact. |
| `build` | Kết hợp các bước kiểm tra và tạo artifact. |

Với Java plugin, `check` phụ thuộc vào `test`. Các plugin kiểm tra bổ sung thường nối task của chúng vào `check`. `assemble` phụ thuộc vào các task tạo sản phẩm như `jar`. Task `build` kết hợp `check` và `assemble`.

Điều này dẫn đến khác biệt thực tế:

```powershell
.\gradlew.bat assemble
```

Lệnh này tạo artifact theo cấu hình nhưng không yêu cầu task lifecycle `check` chạy. Nó hữu ích khi chỉ muốn tạo sản phẩm, nhưng không đủ làm cổng chất lượng nếu kiểm thử và static checks là điều kiện bắt buộc.

```powershell
.\gradlew.bat check
```

Lệnh này chạy các kiểm tra được nối vào lifecycle `check`, nhưng không nhất thiết tạo JAR cuối cùng.

```powershell
.\gradlew.bat clean build
```

Đây thường là lệnh phù hợp cho cổng kiểm chứng cơ bản của một dự án Java dùng plugin chuẩn: xóa đầu ra cũ, chạy các kiểm tra đã được cấu hình và tạo artifact. Tuy nhiên, nó chỉ kiểm tra những task thực sự nằm trong task graph. Nếu integration test, kiểm tra archive hoặc smoke test chưa được nối vào `check`/`build`, chúng sẽ không tự chạy.

Trên Linux hoặc macOS, dùng wrapper tương ứng:

```bash
./gradlew clean build
```

### Mở rộng task `check`

Giả sử dự án có một task integration test riêng. Có thể nối nó vào lifecycle `check`:

```groovy
sourceSets {
    integrationTest {
        compileClasspath += sourceSets.main.output
        runtimeClasspath += sourceSets.main.output
    }
}

configurations {
    integrationTestImplementation.extendsFrom testImplementation
    integrationTestRuntimeOnly.extendsFrom testRuntimeOnly
}

tasks.register('integrationTest', Test) {
    description = 'Runs integration tests.'
    group = 'verification'
    useJUnitPlatform()
    testClassesDirs = sourceSets.integrationTest.output.classesDirs
    classpath = sourceSets.integrationTest.runtimeClasspath
    shouldRunAfter tasks.named('test')
}

tasks.named('check') {
    dependsOn tasks.named('integrationTest')
}
```

Đây là ví dụ rút gọn về quan hệ lifecycle. Dự án thực tế thường khai báo source set `integrationTest` riêng để tách classpath, dependency và thư mục mã nguồn của integration test khỏi unit test. Điều quan trọng là task kiểm thử bổ sung phải được đưa vào graph của `check` nếu đó là điều kiện chấp nhận bắt buộc.

### Thêm bước kiểm tra artifact

Có thể tạo một task xác nhận JAR tồn tại, không rỗng và chứa một lớp bắt buộc. Ví dụ Groovy DSL:

```groovy
def jarTask = tasks.named('jar', Jar)

tasks.register('verifyJarContents') {
    dependsOn jarTask
    inputs.file(jarTask.flatMap { it.archiveFile })

    doLast {
        def archive = jarTask.get().archiveFile.get().asFile
        if (!archive.isFile() || archive.length() == 0) {
            throw new GradleException("JAR is missing or empty: ${archive}")
        }

        new java.util.jar.JarFile(archive).withCloseable { jarFile ->
            if (jarFile.getEntry('com/example/App.class') == null) {
                throw new GradleException('Required application class is missing')
            }
        }
    }
}

tasks.named('check') {
    dependsOn tasks.named('verifyJarContents')
}
```

Task này kiểm tra một điều kiện cấu trúc đơn giản. Nó không thay thế smoke test hoặc kiểm tra hành vi. Trong một dự án lớn, nên đưa logic vào custom task có kiểu rõ ràng, khai báo input/output bằng property phù hợp và kiểm tra đúng các entry theo hợp đồng artifact.

Không nên tạo một task kiểm tra rồi quên nối nó vào lifecycle. Nếu không có `dependsOn` hoặc quan hệ task tương đương từ task được gọi, task đó sẽ không tự chạy khi gọi `build`.

## 5. Kiểm chứng trong Maven: package và verify

Maven tổ chức build theo các lifecycle phase. Với default lifecycle, các phase liên quan gồm:

```text
validate
   |
compile
   |
test
   |
package
   |
integration-test
   |
verify
   |
install
   |
deploy
```

Khi yêu cầu một phase, Maven thực hiện các phase trước đó trong cùng lifecycle. Vì vậy, `mvn verify` đi qua compile, test, package, integration-test và verify theo các plugin execution được cấu hình.

```powershell
mvn clean package
```

Lệnh này chạy đến phase `package`. Nó tạo artifact và chạy các goal đã gắn vào những phase trước đó, bao gồm unit test theo cấu hình mặc định của Surefire. Các kiểm thử integration được cấu hình ở phase `integration-test` và `verify` của Maven Failsafe nằm sau `package`, nên không được bảo đảm chạy chỉ vì đã gọi `package`.

```powershell
mvn clean verify
```

Đây thường là cổng kiểm chứng phù hợp hơn trước khi phát hành. Nó chạy tới phase `verify`, do đó bao gồm các goal đã được cấu hình ở `integration-test` và `verify`.

```powershell
mvn clean install
```

Lệnh này đi tiếp qua `verify` rồi cài artifact vào local Maven repository. `install` hữu ích khi module khác trên máy cần sử dụng artifact vừa build. Việc cài vào local repository không tự chứng minh artifact đủ điều kiện phát hành lên repository dùng chung.

### Surefire và Failsafe

Maven Surefire thường chạy unit test ở phase `test`. Maven Failsafe thường được dùng cho integration test và có các goal `integration-test` cùng `verify`.

Ví dụ cấu hình Failsafe:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-failsafe-plugin</artifactId>
    <version>3.5.2</version>
    <executions>
        <execution>
            <goals>
                <goal>integration-test</goal>
                <goal>verify</goal>
            </goals>
        </execution>
    </executions>
</plugin>
```

Failsafe được thiết kế để ghi nhận lỗi integration test trong phase `integration-test` và báo kết quả thất bại ở phase `verify`, giúp các bước teardown có cơ hội chạy. Vì vậy, nếu integration test là điều kiện phát hành, hãy gọi `mvn verify` hoặc phase cao hơn thay vì chỉ `mvn package`.

Lưu ý: `verify` chỉ chạy những kiểm tra đã được plugin hoặc dự án gắn vào lifecycle. Một dự án chưa cấu hình integration test, static analysis hoặc artifact validation thì `mvn verify` không tự phát minh ra các kiểm tra đó.

## 6. Kiểm tra trực tiếp nội dung archive

Artifact đóng gói là một cấu trúc có thể kiểm tra. Với JAR, có thể dùng `jar` để liệt kê nội dung:

```powershell
jar tf build\libs\application.jar
```

Trên Linux/macOS:

```bash
jar tf build/libs/application.jar
```

Một số mục nên kiểm tra:

- Lớp entry point hoặc các package bắt buộc có trong archive.
- Tài nguyên như `application.yml`, file template, schema hoặc metadata có mặt đúng vị trí.
- Manifest chứa các thuộc tính cần thiết.
- Không có test class, file tạm hoặc dữ liệu môi trường phát triển không được phép phát hành.
- Các file được sinh tự động có phiên bản hoặc nội dung đúng.
- Dependency được đóng gói đúng theo loại artifact.

Để đọc manifest trong JAR:

```powershell
jar xf build\libs\application.jar META-INF\MANIFEST.MF
Get-Content META-INF\MANIFEST.MF
```

Với JAR chạy độc lập, cần xác nhận `Main-Class` hoặc cơ chế launcher tương ứng. Với Spring Boot executable JAR, cấu trúc và manifest có thể do Spring Boot Gradle/Maven plugin tạo, vì vậy cần kiểm tra theo loại archive mà plugin đó quy định. Một library JAR không nhất thiết phải có `Main-Class`.

Không chỉ kiểm tra tên tệp. Nếu một tài nguyên phải chứa giá trị cụ thể, hãy đọc nội dung sau khi giải nén và so sánh với giá trị kỳ vọng. Kiểm tra trực tiếp artifact sẽ phát hiện lỗi trong bước copy, filtering, relocation hoặc packaging mà unit test chạy từ class directory có thể bỏ sót.

## 7. Smoke test: chạy chính artifact đã đóng gói

Smoke test là một kiểm tra runtime ngắn để xác nhận sản phẩm có thể khởi động và thực hiện một số hành vi thiết yếu. Đây là lớp kiểm chứng bổ sung sau khi artifact được tạo.

Với một JAR executable đơn giản:

```powershell
java -jar build\libs\application.jar
```

Nếu ứng dụng là service HTTP, quy trình có thể:

1. Khởi động JAR với profile kiểm thử và các dependency cần thiết.
2. Chờ ứng dụng báo sẵn sàng.
3. Gọi endpoint health hoặc một endpoint nghiệp vụ đại diện.
4. Kiểm tra HTTP status và một phần response có ý nghĩa.
5. Thu thập log khi lỗi và dừng tiến trình sau kiểm thử.

Ví dụ kiểm tra HTTP bằng PowerShell:

```powershell
$response = Invoke-WebRequest -Uri 'http://localhost:8080/actuator/health' -UseBasicParsing
if ($response.StatusCode -ne 200) {
    throw "Health check failed: $($response.StatusCode)"
}
```

Đối với service cần database hoặc message broker, smoke test cần môi trường kiểm thử phù hợp hoặc dependency test được quản lý rõ ràng. Chỉ kiểm tra endpoint health có thể chưa đủ nếu health endpoint không xác nhận những phụ thuộc bắt buộc.

Nếu artifact là thư viện, không dùng `java -jar` làm tiêu chí. Hãy tạo một consumer fixture độc lập, thêm artifact vào classpath hoặc dependency repository thử nghiệm, sau đó biên dịch và chạy một đoạn sử dụng API công khai. Điều này xác nhận sản phẩm có thể được tiêu thụ theo cách người dùng thư viện sẽ sử dụng.

## 8. Kiểm tra dependency và tương thích runtime

Một artifact có thể biên dịch thành công nhưng thất bại khi chạy vì thiếu dependency hoặc dùng API không có trong runtime mục tiêu.

Các câu hỏi cần xác nhận:

- Artifact có chứa dependency cần đóng gói hay yêu cầu consumer cung cấp?
- Phiên bản dependency có tương thích với các thư viện khác trong ứng dụng không?
- Java bytecode và API được dùng có phù hợp JDK runtime tối thiểu không?
- Có thư viện native hoặc cấu hình hệ điều hành phụ thuộc môi trường không?
- Có dependency nào bị loại trừ nhầm hoặc scope sai không?

Với Gradle, có thể xem dependency graph của configuration phù hợp:

```powershell
.\gradlew.bat dependencies --configuration runtimeClasspath
```

Hoặc xem vì sao một dependency được chọn:

```powershell
.\gradlew.bat dependencyInsight --dependency jackson-databind --configuration runtimeClasspath
```

Với Maven:

```powershell
mvn dependency:tree
```

Dependency tree giúp hiểu thư viện nào được đưa vào và thông qua nhánh phụ thuộc nào. Nó không chứng minh toàn bộ dependency đều an toàn hoặc tương thích; cần kết hợp với kiểm tra runtime, dependency policy và dữ liệu lỗ hổng phù hợp.

Đối với JAR độc lập, `jdeps` có thể hỗ trợ phân tích phụ thuộc ở mức bytecode:

```powershell
jdeps build\libs\application.jar
```

Kết quả có thể chỉ ra module hoặc package được tham chiếu. Đây là bằng chứng phân tích tĩnh, không thay thế việc chạy ứng dụng trong runtime đích.

## 9. Kiểm tra checksum, chữ ký và nguồn gốc artifact

Kiểm tra nội dung và kiểm thử runtime trả lời câu hỏi “artifact có hoạt động theo yêu cầu không?”. Một nhóm kiểm tra khác trả lời “artifact có bị thay đổi và có đúng nguồn đã công bố không?”.

### Checksum

Checksum là giá trị băm tính từ byte của tệp. Ví dụ SHA-256:

Trên Windows PowerShell:

```powershell
Get-FileHash build\libs\application.jar -Algorithm SHA256
```

Trên Linux:

```bash
sha256sum build/libs/application.jar
```

Nếu hai bản sao có cùng SHA-256, có bằng chứng mạnh rằng nội dung byte của chúng giống nhau. Checksum hữu ích để phát hiện tệp bị hỏng khi tải lên, tải xuống hoặc sao chép.

Tuy nhiên, checksum **không chứng minh artifact an toàn, đúng chức năng hoặc do đúng tổ chức phát hành tạo ra**. Nếu kẻ tấn công thay cả artifact lẫn file checksum ở cùng một nơi không đáng tin, việc so sánh hai tệp đó không xác nhận được nguồn gốc.

### Chữ ký số

Chữ ký số gắn với artifact hoặc checksum giúp xác nhận rằng dữ liệu được ký bởi chủ thể giữ khóa riêng tương ứng và chưa bị thay đổi kể từ khi ký. Người xác minh vẫn cần tin cậy đúng public key/certificate và kiểm tra trạng thái, phạm vi, thời hạn cũng như chính sách của khóa.

Chữ ký chứng minh nguồn gốc theo khóa được tin cậy và tính toàn vẹn; nó không tự chứng minh mã nguồn không có lỗi hoặc không có lỗ hổng.

### Provenance và SBOM

Provenance mô tả artifact được tạo từ nguồn nào, commit nào, công cụ và workflow nào, với những tham số hoặc môi trường nào. Nó giúp truy xuất đường đi từ source revision đến sản phẩm phát hành.

SBOM (*Software Bill of Materials*) liệt kê các thành phần phần mềm được sử dụng hoặc đóng gói trong artifact. SBOM hỗ trợ kiểm kê dependency và đối chiếu khi có thông báo lỗ hổng mới. Có SBOM không đồng nghĩa mọi dependency đều an toàn; dữ liệu cần được phân tích theo phiên bản và mức độ ảnh hưởng.

## 10. Tái lập build và tính nhất quán của artifact

Một build có thể tạo artifact khác nhau dù source code không đổi, do timestamp, thứ tự entry trong archive, phiên bản dependency không cố định, biến môi trường hoặc dữ liệu sinh từ thời điểm chạy.

**Reproducible build** hướng tới việc tạo ra cùng kết quả byte từ cùng đầu vào và môi trường đã xác định. Để đạt điều đó, dự án thường cần:

- Khóa hoặc cố định phiên bản dependency và plugin.
- Xác định phiên bản JDK và build tool.
- Sắp xếp dữ liệu theo thứ tự ổn định.
- Chuẩn hóa timestamp trong archive nếu công cụ hỗ trợ.
- Không đưa đường dẫn máy cá nhân hoặc dữ liệu ngẫu nhiên vào artifact.
- Khai báo đầy đủ đầu vào ảnh hưởng đến task output.

Nếu hai build độc lập từ cùng source revision và cùng điều kiện tạo ra cùng SHA-256, đó là bằng chứng mạnh về khả năng tái lập. Nếu hash khác nhau, cần điều tra khác biệt về byte; chưa thể kết luận ngay sản phẩm sai vì timestamp hoặc metadata có thể khác trong khi nội dung logic tương đương.

Reproducibility giúp phát hiện build phụ thuộc môi trường ẩn và hỗ trợ kiểm tra chuỗi cung ứng phần mềm. Nó là thuộc tính của quy trình tạo sản phẩm, không phải phép thử chức năng thay thế unit test hoặc integration test.

## 11. Kiểm tra bảo mật trước khi phát hành

Kiểm chứng chất lượng thường cần các kiểm tra bảo mật tương ứng với mức rủi ro của sản phẩm:

- Quét dependency để phát hiện phiên bản có lỗ hổng đã biết.
- Kiểm tra license theo chính sách sử dụng của tổ chức.
- Kiểm tra secret để tránh đóng gói token, password hoặc private key.
- Kiểm tra file cấu hình để tránh phát hành thông tin môi trường nội bộ.
- Kiểm tra quyền và nội dung của script hoặc binary được đóng gói.
- Kiểm tra container image nếu artifact được phát hành dưới dạng image.

Một lần quét không tìm thấy lỗ hổng không phải bằng chứng tuyệt đối rằng phần mềm an toàn. Cơ sở dữ liệu có thể chưa biết một lỗ hổng mới, công cụ có thể không phân tích được một dependency hoặc cấu hình scan có thể bỏ sót phạm vi.

Nên xác định chính sách rõ ràng: mức severity nào chặn phát hành, ngoại lệ nào được phép, ai phê duyệt ngoại lệ và khi nào phải xem xét lại. Không nên chỉ in cảnh báo rồi vẫn phát hành như thể mọi kiểm tra đều đạt.

## 12. Cổng chất lượng trong CI/CD

CI/CD giúp thực hiện cùng một quy trình kiểm chứng trên môi trường được kiểm soát. Một pipeline có thể được tổ chức như sau:

```text
Commit / Pull Request
        |
        v
   Compile + Static checks
        |
        v
      Unit tests
        |
        v
   Integration tests
        |
        v
  Package artifact once
        |
        v
 Inspect archive + Smoke test
        |
        v
 Dependency / Security / Policy
        |
        v
 Hash + Provenance + Store
        |
        v
  Approval / Release gate
        |
        v
 Publish the verified bytes
```

Các bước có thể chạy trên nhiều job hoặc runner, nhưng artifact cần được truyền bằng cơ chế lưu trữ artifact có kiểm soát và xác định rõ phiên bản. Nếu job kiểm thử tạo một JAR, còn job phát hành build lại JAR từ một workspace khác, sản phẩm được phát hành có thể không phải sản phẩm đã được kiểm thử.

Một nguyên tắc quan trọng là **kiểm thử và phát hành cùng một artifact**. Sau khi artifact đã vượt qua các bước kiểm chứng, hãy tính digest và phát hành đúng những byte đó. Nếu phải build lại, cần chạy lại các kiểm tra tương ứng và xác nhận digest mới.

### Điều kiện chặn phát hành

Pipeline nên dừng nếu một điều kiện bắt buộc không đạt, ví dụ:

- Compiler thất bại.
- Unit hoặc integration test thất bại.
- Artifact thiếu file bắt buộc hoặc manifest sai.
- Smoke test không thể khởi động sản phẩm.
- Dependency vi phạm chính sách bảo mật hoặc license.
- Checksum/provenance không khớp với artifact đang chuẩn bị phát hành.

Các kiểm tra không bắt buộc có thể được báo cáo riêng, nhưng cần phân biệt rõ `PASS`, `FAIL`, `SKIPPED` và `NOT CONFIGURED`. Một bước bị bỏ qua không được trình bày như một bước đã đạt.

## 13. Ví dụ một cổng kiểm chứng tối thiểu cho JAR

Giả sử dự án Gradle tạo JAR ứng dụng. Một quy trình tối thiểu có thể gồm:

```powershell
.\gradlew.bat clean build
jar tf build\libs\application.jar
Get-FileHash build\libs\application.jar -Algorithm SHA256
```

Ba lệnh trả lời các câu hỏi khác nhau:

1. `clean build`: các task build và các kiểm tra được nối vào `build` có thành công không?
2. `jar tf`: archive có thể đọc được và chứa những entry nào?
3. `Get-FileHash`: digest của đúng tệp artifact là gì để lưu lại hoặc so sánh?

Sau đó cần smoke test phù hợp với loại ứng dụng. Nếu ứng dụng là Spring Boot executable JAR, có thể khởi động bằng `java -jar` trong profile kiểm thử, chờ health endpoint sẵn sàng, kiểm tra kết quả và dừng tiến trình. Nếu đây là library JAR, thay smoke test bằng một consumer test độc lập.

Đối với Maven:

```powershell
mvn clean verify
jar tf target\application-1.0.0.jar
Get-FileHash target\application-1.0.0.jar -Algorithm SHA256
```

Đường dẫn và tên artifact cần lấy theo cấu hình thực tế của dự án. Nếu dùng classifier, profile hoặc packaging khác, tên tệp sẽ thay đổi.

Các lệnh trên là ví dụ kiểm tra, không phải cam kết rằng mọi artifact Java đều nằm ở cùng một đường dẫn hoặc có cùng tên. Hãy lấy đường dẫn từ cấu hình archive của build tool hoặc từ output được công bố bởi task.

## 14. Phân biệt kiểm tra đã đạt với kiểm tra bị bỏ qua

Một pipeline có thể trả về mã thoát thành công dù một số kiểm thử không chạy, ví dụ do tham số skip, task bị loại khỏi task graph, điều kiện `onlyIf` không thỏa mãn hoặc không tìm thấy test source. Vì vậy, chỉ nhìn dòng `BUILD SUCCESSFUL` hoặc `BUILD SUCCESS` là chưa đủ để biết mọi điều kiện đã được thực hiện.

Trong Gradle, lệnh sau loại task `test` khỏi lần chạy:

```powershell
.\gradlew.bat build -x test
```

Trong Maven, `-DskipTests` bỏ qua việc chạy test nhưng thường vẫn biên dịch test; `-Dmaven.test.skip=true` bỏ qua cả biên dịch và chạy test. Những tùy chọn này có thể hữu ích cho một số công việc phát triển, nhưng không nên âm thầm được dùng ở cổng phát hành nếu test là điều kiện bắt buộc.

Hãy xem test report và trạng thái từng task/phase. Một báo cáo nên phân biệt ít nhất:

- `PASSED`: kiểm tra đã thực thi và đạt.
- `FAILED`: kiểm tra đã thực thi và không đạt.
- `SKIPPED`: kiểm tra được nhận diện nhưng bị bỏ qua.
- `NO-SOURCE` hoặc không có test: không có đầu vào kiểm thử để thực thi.
- `NOT CONFIGURED`: dự án chưa cấu hình loại kiểm tra đó.

Nếu điều kiện chấp nhận yêu cầu có integration test, trạng thái `SKIPPED`, `NO-SOURCE` hoặc `NOT CONFIGURED` không thể được coi là `PASSED`. Cần kiểm tra số lượng test hoặc nội dung report theo kỳ vọng của dự án, tránh trường hợp test task chạy thành công nhưng thực tế không có test nào được thực thi.

## 15. Báo cáo kiểm chứng cần lưu bằng chứng gì?

Một kết quả kiểm chứng có ích cần cho người đọc biết artifact nào đã được kiểm tra và những điều kiện nào thực sự được chạy.

Thông tin thường nên lưu:

| Nhóm | Bằng chứng |
|---|---|
| Nhận diện nguồn | Repository, commit SHA, branch/tag, phiên bản ứng dụng |
| Môi trường | JDK/vendor/version, Gradle hoặc Maven version, OS/container image |
| Cấu hình | Profile, tham số build, dependency lock hoặc thông tin dependency resolution |
| Kiểm tra | Task/phase đã chạy, kết quả unit/integration/static/security checks |
| Artifact | Tên, loại, kích thước, đường dẫn hoặc artifact identifier |
| Nội dung | Kết quả kiểm tra archive, manifest và các entry bắt buộc |
| Runtime | Môi trường smoke test, endpoint hoặc hành vi đã xác nhận |
| Toàn vẹn | SHA-256, chữ ký và trạng thái xác minh nếu có |
| Nguồn gốc | Build run, workflow, provenance hoặc liên kết đến log |

Không cần lưu mọi dòng log vào một báo cáo duy nhất. Có thể lưu report của từng công cụ và tạo một bản tổng hợp liên kết đến chúng. Điều quan trọng là có thể truy ngược từ artifact đã phát hành đến lần build và bằng chứng kiểm chứng của chính nó.

## 16. Xử lý khi kiểm chứng thất bại

Khi một bước kiểm chứng thất bại, cần giữ lại bằng chứng đủ để tái hiện và xác định lớp bị lỗi.

Ví dụ:

- **Compile fail:** lưu compiler output, JDK và cấu hình source/target/release.
- **Unit test fail:** lưu test report, tên test, log và dữ liệu đầu vào liên quan.
- **Integration test fail:** lưu log ứng dụng, log dependency và thông tin môi trường test.
- **Archive invalid:** lưu danh sách entry, manifest và đường dẫn artifact.
- **Smoke test fail:** lưu startup log, response, exit code và cấu hình runtime.
- **Checksum mismatch:** giữ bản gốc đáng tin cậy, bản nhận được và các digest để điều tra quá trình truyền hoặc lưu trữ.
- **Security policy fail:** ghi rõ dependency, phiên bản, advisory, mức độ và quyết định xử lý.

Không nên đổi trạng thái thành `PASS` chỉ vì một bước chạy lại thành công nếu chưa hiểu vì sao lần đầu thất bại. Nếu lỗi do môi trường tạm thời, cần ghi lại nguyên nhân và bằng chứng của lần chạy đạt sau đó. Nếu lỗi phản ánh artifact sai, cần sửa nguồn hoặc cấu hình, build lại và kiểm chứng artifact mới.

Khi artifact không đạt điều kiện bắt buộc, không đưa nó vào luồng phát hành. Nếu tổ chức có cơ chế ngoại lệ, ngoại lệ phải có phạm vi, người chịu trách nhiệm, lý do và thời hạn rõ ràng.

## 17. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| `assemble` thành công nghĩa là mọi test đã chạy | `assemble` tập trung vào tạo artifact; các task kiểm tra thuộc lifecycle `check`. |
| `mvn package` tương đương `mvn verify` | `verify` chạy thêm các phase sau `package`, trong đó có integration-test và verify goals đã cấu hình. |
| Unit test xanh chứng minh JAR cuối đúng | Unit test có thể chạy từ class directory; cần kiểm tra trực tiếp archive và runtime khi điều kiện yêu cầu. |
| Tệp JAR tồn tại nghĩa là artifact hợp lệ | Tệp có thể rỗng, thiếu entry, sai manifest hoặc không khởi động được. |
| Checksum đúng chứng minh phần mềm an toàn | Checksum xác nhận byte giống với digest được so sánh; nó không chứng minh chức năng hay nguồn gốc đáng tin nếu digest không được xác thực. |
| Có SBOM nghĩa là không có lỗ hổng | SBOM liệt kê thành phần; cần đối chiếu advisory, phiên bản và chính sách bảo mật. |
| Build lại ở bước release là luôn an toàn | Artifact mới có thể khác artifact đã kiểm thử; nên phát hành đúng byte đã được xác nhận. |
| `verify` tự chạy mọi loại kiểm tra | Chỉ các goal/task đã được cấu hình và nối vào lifecycle mới chạy. |
| Smoke test thay thế integration test | Smoke test xác nhận một số hành vi tối thiểu; integration test kiểm tra phối hợp giữa các thành phần theo phạm vi rộng hơn. |
| Build thành công nghĩa là mọi test đã chạy | Test có thể bị skip, bị loại khỏi task graph hoặc không có source; cần đọc trạng thái và report. |

## 18. Thiết kế cổng chất lượng phù hợp với từng loại artifact

Không phải mọi sản phẩm đều cần cùng một pipeline. Hãy chọn kiểm tra theo cách artifact sẽ được sử dụng.

### JAR ứng dụng độc lập

- Compile và static checks.
- Unit test và integration test cần thiết.
- Kiểm tra manifest, main class và tài nguyên bắt buộc.
- Khởi động bằng JDK/runtime mục tiêu.
- Smoke test endpoint hoặc hành vi quan trọng.
- Quét dependency, kiểm tra secret và lưu digest/provenance.

### Spring Boot executable JAR

- Xác nhận plugin đóng gói tạo đúng loại executable archive.
- Kiểm tra `BOOT-INF/classes`, `BOOT-INF/lib` và manifest theo cấu trúc của Spring Boot.
- Khởi động JAR với cấu hình kiểm thử.
- Xác nhận ứng dụng có thể đọc resource, phân giải dependency và kết nối các dịch vụ cần thiết.
- Chạy health check và một luồng HTTP đại diện.

### Library JAR

- Kiểm tra API và nội dung archive.
- Kiểm tra metadata dependency và publication descriptor nếu phát hành cho Maven/Gradle consumer.
- Chạy consumer fixture độc lập với classpath tương tự người dùng thư viện.
- Kiểm tra tương thích nhị phân/API nếu thư viện cần duy trì backward compatibility.
- Xác nhận checksum và metadata phiên bản.

### WAR hoặc container image

- Kiểm tra cấu trúc archive/image và cấu hình runtime.
- Chạy trên application server hoặc container runtime tương đương môi trường triển khai.
- Kiểm tra port, health endpoint, quyền filesystem và biến môi trường.
- Quét dependency và image layers theo chính sách.
- Ghi lại image digest hoặc artifact digest, không chỉ tag dễ thay đổi.

## 19. Checklist trước khi chấp nhận artifact

Trước khi đánh dấu artifact là hợp lệ, hãy xác nhận:

1. Đúng source revision, version và build configuration đã được sử dụng.
2. JDK và build tool đáp ứng yêu cầu của dự án.
3. Compile và các static checks bắt buộc đã đạt.
4. Unit tests và integration/contract tests bắt buộc đã chạy và đạt.
5. Artifact được tạo ở đúng loại và vị trí.
6. Archive có các lớp, tài nguyên, manifest và metadata cần thiết.
7. Không đóng gói nhầm test data, secret hoặc cấu hình không được phép.
8. Artifact chạy được hoặc được consumer sử dụng thành công theo đúng mục đích.
9. Dependency và security policy được kiểm tra theo yêu cầu phát hành.
10. Digest, provenance và bằng chứng kiểm chứng được lưu cùng artifact.
11. Chính artifact đã kiểm thử là artifact được đưa vào bước phát hành.

Trạng thái `VALID` chỉ nên được gán khi mọi điều kiện bắt buộc của hợp đồng chấp nhận đều có bằng chứng đạt. Nếu một kiểm tra bị bỏ qua, chưa cấu hình hoặc chưa có dữ liệu, báo cáo cần thể hiện chính xác trạng thái đó để người chịu trách nhiệm không nhầm lẫn giữa “chưa kiểm tra” và “đã đạt”.

Khi các điều kiện chấp nhận được xác định rõ, build lifecycle trở thành một quy trình có thể kiểm soát: mỗi bước tạo bằng chứng cho một loại chất lượng, artifact được kiểm tra trực tiếp sau khi đóng gói, và chỉ những byte đã vượt qua cổng bắt buộc mới được phát hành.
