# Thư mục đầu ra: lớp đã biên dịch, báo cáo và artifact

Trong một dự án Java, mã nguồn và những tệp được tạo ra trong quá trình build có vai trò khác nhau. Mã nguồn là đầu vào mà lập trình viên duy trì. Trình biên dịch, bộ kiểm thử và các tác vụ build tạo ra những kết quả trung gian hoặc sản phẩm có thể sử dụng ở các bước tiếp theo. Build tool thường gom những kết quả này vào một thư mục đầu ra riêng để dự án dễ tổ chức, kiểm tra, đóng gói và làm sạch.

Khi nhìn vào một thư mục như `build/` của Gradle hoặc `target/` của Maven, bạn có thể bắt gặp ba nhóm nội dung chính:

1. **Lớp và tài nguyên đã xử lý:** bytecode `.class`, tài nguyên được sao chép hoặc xử lý để chương trình có thể chạy.
2. **Báo cáo:** kết quả kiểm thử, phân tích mã nguồn, kiểm tra chất lượng hoặc tài liệu được build tool tạo ra.
3. **Artifact:** sản phẩm được đóng gói để chạy, chia sẻ hoặc triển khai, chẳng hạn JAR và WAR.

```text
Mã nguồn và tài nguyên                 Cấu hình build
       |                                     |
       +------------------+------------------+
                          |
                          v
                     Build tool
                          |
             +------------+-------------+
             |            |             |
             v            v             v
       Lớp đã biên dịch  Báo cáo     Artifact
       và tài nguyên     kiểm thử    JAR / WAR
             |            |             |
             v            v             v
        Chạy ứng dụng   Kiểm tra     Phân phối /
                       kết quả      triển khai
```

Nắm được cấu trúc thư mục đầu ra giúp bạn biết build đã tạo ra gì, tìm đúng kết quả khi có lỗi và tránh nhầm lẫn giữa tệp nguồn với tệp sinh tự động.

## 1. Vì sao dự án cần thư mục đầu ra riêng?

Một dự án Java không chỉ gồm các tệp `.java`. Để tạo ra ứng dụng có thể chạy, build tool phải thực hiện nhiều bước: biên dịch mã nguồn, xử lý tài nguyên, biên dịch mã kiểm thử, chạy kiểm thử, tạo báo cáo và đóng gói kết quả.

Nếu ghi tất cả kết quả vào cạnh mã nguồn, cây thư mục sẽ nhanh chóng lẫn lộn giữa tệp do con người viết và tệp do công cụ tạo. Một lần biên dịch có thể tạo hàng trăm hoặc hàng nghìn tệp `.class`; mỗi lần chạy kiểm thử có thể tạo thêm báo cáo HTML, XML và dữ liệu kết quả. Các tệp này có thể được tạo lại từ đầu vào nên không cần duy trì thủ công như mã nguồn.

Thư mục đầu ra riêng mang lại một số lợi ích:

- **Tách đầu vào khỏi đầu ra:** mã nguồn, tài nguyên gốc và cấu hình build có vị trí rõ ràng; kết quả sinh tự động nằm ở nơi khác.
- **Dễ chạy và đóng gói:** các tác vụ tiếp theo biết nơi tìm bytecode, tài nguyên và kết quả đã biên dịch.
- **Dễ kiểm tra:** có thể mở báo cáo kiểm thử hoặc xem nội dung JAR mà không phải tìm trong thư mục nguồn.
- **Dễ làm sạch:** có thể xóa kết quả cũ rồi build lại từ đầu mà không xóa mã nguồn.
- **Hỗ trợ build tăng dần:** build tool theo dõi đầu vào và đầu ra của tác vụ để quyết định khi nào có thể dùng lại kết quả trước đó.
- **Giữ repository gọn:** các tệp sinh tự động thường được loại khỏi Git, giúp lịch sử phiên bản tập trung vào nội dung cần review.

Một cây thư mục Java điển hình có thể trông như sau:

```text
my-app/
├── src/
│   ├── main/
│   │   ├── java/                 # Mã nguồn ứng dụng
│   │   └── resources/            # Tài nguyên ứng dụng
│   └── test/
│       ├── java/                 # Mã nguồn kiểm thử
│       └── resources/            # Tài nguyên kiểm thử
├── build.gradle                 # Hoặc pom.xml
├── build/                        # Gradle: kết quả sinh tự động
│   ├── classes/
│   ├── resources/
│   ├── reports/
│   ├── test-results/
│   └── libs/
└── .gitignore
```

`src/` là nơi lưu đầu vào của dự án. `build/` trong ví dụ là thư mục đầu ra mặc định của Gradle; nếu dùng Maven, thư mục đầu ra mặc định thường là `target/`. Cấu trúc con thực tế phụ thuộc plugin, tác vụ và cấu hình của dự án.

## 2. Lớp đã biên dịch và tài nguyên đã xử lý

### Từ `.java` đến `.class`

Trình biên dịch Java đọc mã nguồn `.java` và tạo bytecode trong tệp `.class`. Bytecode là đầu vào để JVM nạp và thực thi. Mỗi lớp được biên dịch thường tạo một tệp `.class`; lớp lồng nhau hoặc một số cấu trúc ngôn ngữ khác có thể tạo thêm các tệp lớp riêng.

Ví dụ, dự án có:

```text
src/main/java/com/example/app/
├── Application.java
└── GreetingService.java
```

Sau khi biên dịch, Gradle Java plugin thường đặt kết quả tại:

```text
build/classes/java/main/
└── com/example/app/
    ├── Application.class
    └── GreetingService.class
```

Đường dẫn bên trong thư mục đầu ra phản ánh package của lớp. `build/classes/java/main` là nơi chứa lớp đã biên dịch của source set `main` theo cấu trúc mặc định của Gradle Java plugin.

Các lớp kiểm thử được biên dịch riêng, thường nằm tại:

```text
build/classes/java/test/
```

Việc tách `main` và `test` giúp ứng dụng chính không bị trộn với mã kiểm thử. Khi đóng gói ứng dụng thông thường, build tool lấy lớp từ phần `main`; lớp kiểm thử được dùng cho tác vụ test và không tự động trở thành nội dung của JAR ứng dụng.

### Tài nguyên được sao chép hoặc xử lý

Không phải mọi đầu vào đều là mã Java. Ứng dụng thường có tệp cấu hình, mẫu HTML, ảnh, dữ liệu khởi tạo hoặc các tài nguyên khác trong `src/main/resources`.

Ví dụ:

```text
src/main/resources/
├── application.yml
├── messages.properties
└── templates/
    └── welcome.html
```

Gradle Java plugin thường sao chép các tài nguyên này vào:

```text
build/resources/main/
├── application.yml
├── messages.properties
└── templates/
    └── welcome.html
```

Các tệp tài nguyên có thể được xử lý trong quá trình build, chẳng hạn thay thế giá trị placeholder nếu dự án cấu hình tác vụ tương ứng. Vì vậy, đầu ra không phải lúc nào cũng là bản sao byte-for-byte của đầu vào. Hãy kiểm tra cấu hình tác vụ nếu ứng dụng sử dụng filtering hoặc sinh tài nguyên.

Tài nguyên kiểm thử từ `src/test/resources` được xử lý riêng và thường nằm tại `build/resources/test`. Điều này giúp môi trường kiểm thử có dữ liệu riêng mà không đưa dữ liệu đó vào ứng dụng chính.

### Vì sao không chạy trực tiếp từ `src/`?

JVM thường nạp lớp từ bytecode đã biên dịch, chẳng hạn trong thư mục `build/classes/java/main` hoặc trong JAR. Thư mục `src/main/java` chứa mã nguồn mà trình biên dịch sử dụng. Nếu bạn vừa sửa mã nguồn nhưng chưa chạy tác vụ biên dịch tương ứng, bytecode trong thư mục đầu ra có thể vẫn là kết quả của lần build trước.

Đó là lý do khi chạy ứng dụng bằng classpath thủ công, bạn cần trỏ đến thư mục chứa `.class` đã biên dịch và bảo đảm nó đã được cập nhật. Build tool tự quản lý quan hệ giữa tác vụ biên dịch và tác vụ chạy để giảm nguy cơ dùng kết quả cũ.

## 3. Báo cáo được tạo trong quá trình build

Báo cáo là kết quả giúp con người quan sát và đánh giá quá trình build. Chúng thường không phải thành phần cần thiết để JVM chạy ứng dụng, nhưng rất quan trọng khi phát triển và tích hợp liên tục.

### Báo cáo kiểm thử

Khi chạy kiểm thử tự động, build tool ghi nhận test nào thành công, thất bại, bị bỏ qua và thời gian thực thi. Với Gradle Java plugin, sau khi chạy tác vụ `test`, bạn thường tìm thấy:

```text
build/
├── reports/
│   └── tests/
│       └── test/
│           └── index.html
└── test-results/
    └── test/
        ├── TEST-com.example.UserServiceTest.xml
        └── binary/
```

`build/reports/tests/test/index.html` là báo cáo HTML để mở trong trình duyệt. Thư mục `build/test-results/test` chứa dữ liệu kết quả máy có thể đọc, thường gồm các tệp XML theo định dạng tương thích với công cụ CI. Tệp trong `binary/` là dữ liệu nội bộ của Gradle, không phải báo cáo HTML dành cho người đọc.

Với Maven Surefire, kết quả kiểm thử đơn vị thường nằm trong `target/surefire-reports/`. Tên và nội dung báo cáo phụ thuộc phiên bản plugin cùng cấu hình dự án. Nếu dự án dùng plugin kiểm thử khác, đường dẫn có thể khác.

### Báo cáo chất lượng và các báo cáo khác

Ngoài kiểm thử, dự án có thể tạo báo cáo từ các tác vụ phân tích mã nguồn hoặc kiểm tra chất lượng, ví dụ:

- Báo cáo cảnh báo compiler hoặc lint.
- Báo cáo độ bao phủ kiểm thử (test coverage).
- Báo cáo kiểm tra dependency hoặc lỗ hổng nếu dự án tích hợp công cụ tương ứng.
- Báo cáo API hoặc tài liệu được sinh tự động.
- Báo cáo kết quả đóng gói và kiểm tra artifact.

Không phải dự án nào cũng có đầy đủ các loại báo cáo này. Chúng chỉ xuất hiện khi plugin hoặc tác vụ tương ứng được cấu hình và chạy. Vị trí đầu ra có thể tùy chỉnh.

### Đọc báo cáo để tìm lỗi

Khi một tác vụ test thất bại, log Terminal thường cho biết tên test hoặc một phần stack trace. Báo cáo HTML có thể cung cấp ngữ cảnh dễ đọc hơn: test nào thất bại, thông báo assertion, stack trace và các test liên quan. Báo cáo XML thường phù hợp để CI thu thập kết quả và hiển thị trạng thái build.

Ví dụ, nếu lệnh build kết thúc với trạng thái thất bại:

```shell
./gradlew test
```

Trên Windows:

```powershell
.\gradlew.bat test
```

Hãy xem log để tìm tác vụ thất bại, sau đó mở báo cáo kiểm thử tại đường dẫn được Gradle thông báo hoặc theo vị trí mặc định `build/reports/tests/test/index.html`. Một tác vụ thất bại có thể không tạo báo cáo đầy đủ nếu lỗi xảy ra trước khi kiểm thử bắt đầu.

## 4. Artifact là gì?

Artifact là tệp đầu ra có thể được sử dụng ở bước tiếp theo, chẳng hạn để chạy, phân phối, triển khai hoặc làm đầu vào cho một hệ thống khác. Trong dự án Java, artifact thường là:

- **JAR:** gói chứa bytecode, tài nguyên và metadata. JAR có thể là thư viện hoặc ứng dụng.
- **WAR:** gói ứng dụng web theo định dạng WAR, thường được triển khai lên servlet container hoặc môi trường hỗ trợ WAR.
- **ZIP hoặc TAR:** gói phân phối chứa nhiều tệp, script chạy và cấu hình cần thiết.
- **Artifact phụ trợ:** tệp sinh tự động phục vụ một bước build hoặc triển khai khác.

Artifact được tạo từ các đầu vào và kết quả trung gian. Ví dụ, một JAR ứng dụng thường chứa các lớp đã biên dịch, tài nguyên và metadata trong thư mục `META-INF`.

### Artifact của Gradle

Với Gradle Java plugin, JAR chính thường được tạo trong:

```text
build/libs/
└── my-app-1.0.0.jar
```

Tên cụ thể phụ thuộc `project.name`, `version`, loại archive và cấu hình. Tác vụ `jar` tạo JAR từ output của source set `main`. Trong một dự án Spring Boot sử dụng plugin Spring Boot, tác vụ `bootJar` thường tạo JAR ứng dụng có thể chạy trong `build/libs/`; tác vụ `jar` thông thường có thể tạo một JAR khác. Đừng giả định mọi dự án Gradle đều có `bootJar`: tác vụ đó chỉ có khi plugin phù hợp được áp dụng.

Các lệnh thường dùng:

```shell
./gradlew jar
./gradlew build
```

Trên Windows:

```powershell
.\gradlew.bat jar
.\gradlew.bat build
```

`jar` yêu cầu tạo archive JAR. `build` là tác vụ tổng hợp của Java plugin, thường phụ thuộc vào các bước kiểm thử và đóng gói cần thiết. Plugin và cấu hình của dự án có thể mở rộng hoặc thay đổi những gì `build` thực hiện.

### Artifact của Maven

Với Maven, thư mục đầu ra mặc định là `target/`. Sau khi chạy giai đoạn `package`, bạn thường thấy:

```text
target/
├── classes/
├── test-classes/
├── surefire-reports/
└── my-app-1.0.0.jar
```

Tên artifact phụ thuộc `artifactId`, `version` và `packaging` trong `pom.xml`. Với dự án đóng gói WAR, kết quả thường có đuôi `.war`.

Các lệnh thường dùng:

```shell
mvn package
mvn verify
```

`package` thực hiện các bước trước đó trong lifecycle rồi tạo gói. `verify` tiếp tục chạy các bước kiểm tra sau package được cấu hình trong lifecycle. Các plugin của Maven có thể bổ sung thêm báo cáo hoặc artifact.

## 5. So sánh cấu trúc đầu ra Gradle và Maven

Hai build tool có cùng mục đích tổng quát nhưng dùng tên thư mục và cách tổ chức khác nhau.

| Nội dung | Gradle (Java plugin, mặc định) | Maven (mặc định) |
|---|---|---|
| Thư mục đầu ra gốc | `build/` | `target/` |
| Lớp ứng dụng đã biên dịch | `build/classes/java/main/` | `target/classes/` |
| Lớp kiểm thử đã biên dịch | `build/classes/java/test/` | `target/test-classes/` |
| Tài nguyên ứng dụng | `build/resources/main/` | `target/classes/` sau quá trình xử lý resource |
| Báo cáo test | `build/reports/tests/test/` và `build/test-results/test/` | `target/surefire-reports/` với Maven Surefire |
| JAR/WAR | Thường trong `build/libs/` | Thường trực tiếp trong `target/` |
| Tác vụ làm sạch | `clean` | `clean` |

Đây là các vị trí mặc định thường gặp, không phải quy tắc bất biến. Dự án có thể đổi thư mục build, đổi output của plugin, thêm source set hoặc cấu hình nhiều loại artifact. Khi tìm một tệp cụ thể, hãy xem cấu hình và log của tác vụ thực tế.

## 6. Quan sát thư mục đầu ra sau khi build

Bạn nên thực hành đọc cây thư mục thay vì chỉ nhìn thông báo `BUILD SUCCESSFUL`. Thông báo thành công cho biết tác vụ hoàn tất; việc kiểm tra output giúp xác nhận kết quả mong muốn đã được tạo ở đâu.

### Chạy build

Với dự án Gradle có wrapper:

```shell
./gradlew clean build
```

Trên Windows:

```powershell
.\gradlew.bat clean build
```

Với dự án Maven:

```shell
mvn clean package
```

`clean` xóa thư mục đầu ra do build tool quản lý; tác vụ phía sau sẽ tạo lại những kết quả cần thiết. Trong Gradle, `clean` xóa thư mục build của project. Trong Maven, `clean` xóa thư mục `target` mặc định. Hãy kiểm tra cấu hình nếu dự án đã tùy chỉnh vị trí đầu ra.

### Liệt kê các tệp được tạo

PowerShell có thể liệt kê cây thư mục Gradle như sau:

```powershell
Get-ChildItem -Path build -Recurse -File |
    Select-Object FullName, Length
```

Để tìm các tệp JAR:

```powershell
Get-ChildItem -Path build/libs -Filter *.jar
```

Trên Linux hoặc macOS:

```shell
find build -type f
find build/libs -maxdepth 1 -name '*.jar'
```

Với Maven, thay `build` bằng `target` và `build/libs` bằng `target` khi liệt kê artifact.

### Xem nội dung JAR

JAR là một định dạng archive dựa trên ZIP. Công cụ `jar` đi kèm JDK có thể liệt kê nội dung mà không cần giải nén:

```shell
jar --list --file build/libs/my-app-1.0.0.jar
```

Hoặc dùng dạng rút gọn:

```shell
jar tf build/libs/my-app-1.0.0.jar
```

Trên Windows, lệnh tương tự được chạy trong PowerShell hoặc Command Prompt nếu thư mục `bin` của JDK có trong `PATH`. Hãy thay tên tệp bằng artifact thực tế của dự án.

Khi xem nội dung, hãy kiểm tra các package `.class`, tài nguyên cần thiết và `META-INF/MANIFEST.MF`. Nếu một lớp hoặc tài nguyên không xuất hiện, hãy xem source set, cấu hình đóng gói và output của tác vụ trước đó.

## 7. Làm sạch đầu ra và build lại

Trong quá trình phát triển, thư mục đầu ra có thể chứa kết quả từ nhiều lần build. Build tool thường chỉ cập nhật những tác vụ cần chạy dựa trên đầu vào, đầu ra và trạng thái của chúng. Cơ chế này giúp build nhanh hơn, nhưng đôi khi bạn cần xóa kết quả cũ để kiểm tra một lần build sạch.

Với Gradle:

```shell
./gradlew clean build
```

Với Maven:

```shell
mvn clean package
```

`clean` là tác vụ/giai đoạn làm sạch do build tool cung cấp. Nó xóa thư mục đầu ra được cấu hình cho project, sau đó build tool tạo lại những gì cần thiết. Vì thế, không đặt mã nguồn duy nhất hoặc dữ liệu người dùng cần giữ bên trong `build/` hay `target/`.

### Khi nào cần clean?

Bạn có thể cân nhắc build sạch khi:

- Muốn kiểm tra kết quả có thể tái tạo từ đầu vào hiện tại.
- Nghi ngờ đang chạy bytecode hoặc resource cũ.
- Thay đổi cấu hình đầu ra hoặc cấu trúc project và muốn loại bỏ kết quả cũ không còn phù hợp.
- Điều tra một lỗi chỉ xuất hiện sau nhiều lần build.
- Chuẩn bị xác nhận build trên môi trường CI sạch.

Không cần chạy `clean` trước mọi tác vụ trong quá trình phát triển. Build tăng dần là một tính năng hữu ích; xóa toàn bộ đầu ra mỗi lần có thể làm mất lợi ích về tốc độ. Hãy dùng clean khi có lý do kiểm tra hoặc làm mới trạng thái build.

## 8. Đầu ra trong dự án nhiều module

Một dự án Gradle nhiều module thường có thư mục đầu ra riêng cho từng subproject. Ví dụ:

```text
workspace/
├── settings.gradle
├── app/
│   ├── build.gradle
│   └── build/
│       ├── classes/
│       └── libs/
├── domain/
│   ├── build.gradle
│   └── build/
│       └── classes/
└── infrastructure/
    ├── build.gradle
    └── build/
        └── classes/
```

Khi chạy tác vụ ở root project, Gradle có thể thực hiện tác vụ tương ứng trong các subproject theo quan hệ phụ thuộc. Mỗi module giữ output riêng để tránh ghi đè lớp hoặc artifact của module khác.

Trong dự án nhiều module, hãy xác định artifact thuộc project nào. Ví dụ, `app/build/libs/` có thể chứa ứng dụng có thể chạy, trong khi `domain/build/libs/` có thể chứa thư viện domain. Không nên giả định chỉ có một thư mục `build/` ở root chứa toàn bộ kết quả.

Maven cũng hỗ trợ multi-module. Mỗi module thường có `target/` riêng; project cha có thể đóng vai trò aggregator và không nhất thiết tạo JAR riêng.

## 9. Khai báo và tùy chỉnh đầu ra

Build tool cần biết tác vụ đọc những đầu vào nào và tạo ra những đầu ra nào. Khi dùng plugin chuẩn, nhiều đường dẫn đã được thiết lập sẵn. Với tác vụ tùy chỉnh, khai báo đầu vào và đầu ra rõ ràng giúp build tool theo dõi thay đổi, tránh chạy lại không cần thiết và hỗ trợ build cache khi tác vụ đáp ứng các điều kiện tương ứng.

### Thư mục build của Gradle

Gradle mặc định dùng thư mục `build` trong project. Có thể cấu hình thư mục build của project trong build script, ví dụ:

```groovy
layout.buildDirectory = layout.projectDirectory.dir('out')
```

Sau cấu hình này, các tác vụ dùng `layout.buildDirectory` làm vị trí đầu ra sẽ đặt kết quả bên dưới `out/`. Một plugin hoặc tác vụ tự viết có thể dùng một đường dẫn khác nếu nó được cấu hình riêng. Vì vậy, không phải cứ đổi `buildDirectory` là mọi tệp do mọi công cụ bên ngoài tạo ra đều tự chuyển vị trí.

### Output của một tác vụ tùy chỉnh

Trong Gradle, tác vụ có thể khai báo thư mục đầu ra thông qua các thuộc tính như `DirectoryProperty` được đánh dấu `@OutputDirectory`. Ví dụ minh họa:

```groovy
import org.gradle.api.DefaultTask
import org.gradle.api.file.DirectoryProperty
import org.gradle.api.tasks.OutputDirectory
import org.gradle.api.tasks.TaskAction

abstract class GenerateInfoTask extends DefaultTask {
    @OutputDirectory
    abstract DirectoryProperty getOutputDirectory()

    @TaskAction
    void generate() {
        File output = outputDirectory.get().asFile
        output.mkdirs()
        new File(output, 'build-info.txt').text = 'Generated by Gradle'
    }
}

tasks.register('generateInfo', GenerateInfoTask) {
    outputDirectory = layout.buildDirectory.dir('generated/info')
}
```

Trong ví dụ này, tác vụ tạo `build/generated/info/build-info.txt`. Annotation `@OutputDirectory` giúp Gradle nhận biết thư mục là đầu ra của tác vụ. Khi viết tác vụ thực tế, cũng cần khai báo đầu vào nếu kết quả phụ thuộc vào tệp hoặc cấu hình bên ngoài để Gradle có thể đánh giá tính hợp lệ của output.

Đối với dự án Maven, các plugin thường cho phép cấu hình thư mục đầu ra qua phần cấu hình plugin hoặc các thuộc tính dự án. Ví dụ, `project.build.directory` là thuộc tính Maven biểu diễn thư mục build, mặc định là `${project.basedir}/target`. Hãy tham khảo cấu hình của plugin đang tạo kết quả vì từng plugin có thể có tùy chọn riêng.

## 10. Quản lý thư mục đầu ra trong Git

Thông thường, thư mục `build/` của Gradle và `target/` của Maven chứa kết quả sinh tự động. Các dự án thường thêm chúng vào `.gitignore`:

```gitignore
# Gradle
.gradle/
build/

# Maven
target/
```

`.gradle/` là thư mục trạng thái/cache cục bộ của Gradle ở cấp project; nó cũng thường không cần đưa vào Git. Cấu hình ignore thực tế nên phù hợp với repository. Nếu dự án cố ý lưu một artifact đã phát hành hoặc một báo cáo được dùng làm tài liệu, hãy xác định rõ yêu cầu trước khi áp dụng quy tắc ignore rộng.

Không nên đưa mọi tệp có đuôi `.jar` vào ignore một cách máy móc. Dự án có thể chủ động quản lý một thư viện nội bộ hoặc công cụ cần thiết trong `libs/`. Hãy phân biệt thư viện đầu vào được quản lý có chủ đích với JAR đầu ra được tạo lại trong `build/libs/` hoặc `target/`.

### Kiểm tra trạng thái Git

Sau khi build, chạy:

```shell
git status --short
```

Nếu thư mục đầu ra xuất hiện trong danh sách thay đổi dù đã được ignore, hãy kiểm tra `.gitignore` và xem tệp có đang được Git theo dõi từ trước hay không. Quy tắc ignore mới không tự bỏ theo dõi những tệp đã được commit. Trường hợp đó cần được xử lý có chủ đích để tránh thay đổi dữ liệu của repository ngoài ý muốn.

## 11. Một số nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| `build/` hoặc `target/` là nơi viết mã nguồn | Đây thường là thư mục kết quả sinh tự động. Mã nguồn nên nằm trong `src/` hoặc vị trí nguồn được cấu hình. |
| Mọi tệp trong thư mục đầu ra đều là artifact để triển khai | Thư mục này còn có lớp trung gian, tài nguyên đã xử lý, báo cáo và dữ liệu nội bộ của plugin. |
| Có `.class` nghĩa là đã có JAR chạy được | `.class` chỉ là lớp đã biên dịch. Còn cần classpath, tài nguyên, phụ thuộc và cấu hình chạy phù hợp. |
| Báo cáo kiểm thử nằm bên trong JAR ứng dụng | Báo cáo thường nằm trong thư mục reports riêng và không phải nội dung JAR. |
| `build/` luôn là thư mục đầu ra của mọi build tool | Gradle mặc định dùng `build/`; Maven mặc định dùng `target/`. Cả hai đều có thể được tùy chỉnh. |
| Build thành công đồng nghĩa artifact đúng như mong muốn | Cần kiểm tra tác vụ đã chạy và nội dung artifact, nhất là khi dự án có nhiều loại gói hoặc nhiều module. |
| Có thể xóa bất kỳ thư mục nào trong repository để làm sạch | Chỉ xóa thư mục đầu ra đã xác định. Không xóa thư mục chứa đầu vào hoặc dữ liệu cần giữ. |

## 12. Quy trình tìm một kết quả build

Khi cần tìm một lớp, báo cáo hoặc artifact, hãy đi theo thứ tự sau:

1. Xác định build tool và project/module tạo ra kết quả.
2. Xác định tác vụ đã tạo kết quả, chẳng hạn `compileJava`, `test`, `jar`, `bootJar` hoặc lifecycle Maven tương ứng.
3. Đọc log để xem tác vụ có chạy thành công và có thông báo đường dẫn đầu ra hay không.
4. Kiểm tra thư mục đầu ra của đúng project, ví dụ `module/build/` hoặc `module/target/`.
5. Phân loại tệp cần tìm: `.class`, resource, báo cáo hay artifact.
6. Nếu là JAR, liệt kê nội dung bằng `jar tf` để xác nhận lớp và tài nguyên mong muốn có trong gói.
7. Nếu kết quả cũ hoặc không còn khớp với đầu vào, chạy tác vụ phù hợp hoặc clean rồi build lại.

Ví dụ, khi cần tìm báo cáo test của Gradle, chạy `test`, sau đó mở `build/reports/tests/test/index.html`. Khi cần tìm JAR, chạy `jar` hoặc `build`, rồi xem `build/libs/`. Với Maven, chạy `test` hoặc `package`, rồi kiểm tra `target/surefire-reports/` hoặc JAR/WAR trực tiếp trong `target/`.

## 13. Bài thực hành

Thực hiện bài tập với một dự án Java nhỏ có Gradle hoặc Maven. Nếu chưa có dự án, tạo một dự án Java tối giản bằng build tool mà bạn đang học.

1. Xác định thư mục mã nguồn ứng dụng và mã nguồn kiểm thử.
2. Chạy tác vụ biên dịch, sau đó tìm một tệp `.class` trong thư mục đầu ra. Đối chiếu đường dẫn của nó với package khai báo trong mã nguồn.
3. Thêm một tệp vào `src/main/resources`, build lại và tìm tệp đó trong output tài nguyên.
4. Chạy kiểm thử và mở báo cáo HTML hoặc báo cáo do plugin test tạo ra. Xác định test thành công, thất bại và tổng thời gian nếu báo cáo cung cấp.
5. Tạo JAR của ứng dụng. Dùng `jar tf` để xem các lớp, tài nguyên và manifest bên trong.
6. Chạy tác vụ `clean`, kiểm tra thư mục đầu ra mặc định đã được xóa, rồi build lại để quan sát các kết quả được tạo mới.
7. Kiểm tra `git status --short` và `.gitignore`. Xác định thư mục nào là output sinh tự động và thư mục nào chứa đầu vào cần commit.
8. Nếu dự án có nhiều module, tìm output của từng module và xác định artifact nào là thư viện, artifact nào là ứng dụng.

Sau khi hoàn thành, bạn cần phân biệt được bytecode với artifact, báo cáo với sản phẩm triển khai, hiểu vì sao lớp chính và lớp kiểm thử có thư mục riêng, biết nơi tìm kết quả mặc định của Gradle/Maven và giải thích được tác dụng của tác vụ `clean`. Đây là nền tảng để đọc cấu hình build, điều tra lỗi biên dịch và hiểu các bước đóng gói trong những dự án Java lớn hơn.
