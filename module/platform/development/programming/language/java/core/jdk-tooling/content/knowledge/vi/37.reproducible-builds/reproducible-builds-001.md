# Build tái lập (Reproducible Build) với Java và Maven

Build tái lập là khả năng tạo lại cùng một artifact nhị phân từ cùng mã nguồn và các đầu vào build đã xác định. Khi hai lần build độc lập tạo ra file JAR/WAR có cùng từng byte, ta có thể so sánh SHA-256 để xác nhận kết quả. Điều này giúp kiểm tra tính toàn vẹn của release, phát hiện thay đổi ngoài dự kiến trong build pipeline và hỗ trợ điều tra sự cố supply chain.

Với Maven, build tái lập cần kiểm soát nhiều đầu vào: source revision, JDK, Maven, plugin, dependency, repository, timestamp, encoding, locale, timezone, hệ điều hành và công cụ sinh mã. Chỉ thêm một thuộc tính timestamp vào POM là chưa đủ. Bài này hướng dẫn cách cố định đầu vào, chuẩn hóa output, kiểm tra bằng Maven Artifact Plugin và so sánh artifact độc lập.

## 1. Build tái lập là gì?

Một build được xem là tái lập khi bên thứ ba có thể lấy cùng source code, môi trường build và hướng dẫn build, sau đó tạo ra bản sao bit-for-bit giống với artifact tham chiếu.

Ví dụ:

- Lần build A tạo application-1.0.0.jar.
- Lần build B chạy độc lập từ cùng commit và cấu hình.
- Hai file có cùng kích thước và SHA-256.
- Khi giải nén, nội dung, thứ tự entry và metadata cần thiết cũng giống nhau.

Build tái lập không chỉ có nghĩa là chương trình chạy giống nhau. Hai JAR có thể thực thi cùng hành vi nhưng khác byte vì timestamp, manifest, thứ tự file hoặc metadata khác nhau. Mục tiêu của reproducible build là tạo ra artifact nhị phân giống hệt.

## 2. Phân biệt repeatable build, reproducible build và deterministic build

Các thuật ngữ đôi khi được dùng thay thế nhau. Trong bài này, ta dùng cách phân biệt thực hành sau:

| Thuật ngữ | Ý nghĩa |
|---|---|
| Deterministic build | Cùng một tập đầu vào được xử lý theo cách xác định và tạo cùng output |
| Repeatable build | Có thể chạy lại build trong cùng môi trường và nhận kết quả ổn định |
| Reproducible build | Một môi trường độc lập có thể tái tạo artifact giống từng byte từ đầu vào và hướng dẫn đã công bố |

Một build có thể repeatable trên máy developer nhưng không reproducible trên CI vì đường dẫn, timezone hoặc JDK khác nhau. Reproducible build yêu cầu xác định rõ các đầu vào và kiểm chứng độc lập.

Một container giúp kiểm soát môi trường, nhưng chỉ dùng container chưa tự động làm build tái lập. Image, architecture, toolchain, dependency và các nguồn không xác định bên ngoài container vẫn có thể làm output thay đổi.

## 3. Vì sao build tái lập quan trọng?

Build tái lập mang lại các lợi ích:

- **Xác minh artifact:** người khác có thể build lại và so sánh với bản phát hành.
- **Phát hiện thay đổi bất thường:** nếu cùng source nhưng artifact khác, có thể có đầu vào ẩn hoặc thay đổi trong build pipeline.
- **Tăng độ tin cậy của release:** binary phát hành có thể được đối chiếu với source revision đã công bố.
- **Hỗ trợ audit:** có bằng chứng rõ hơn về đường đi từ source đến artifact.
- **Điều tra regression:** khác biệt giữa hai lần build có thể chỉ ra plugin, dependency hoặc môi trường đã thay đổi.
- **Tăng khả năng bảo trì CI:** build ổn định giúp giảm lỗi chỉ xảy ra trên một máy.

Reproducibility là một thuộc tính của quy trình tạo artifact. Nó hỗ trợ kiểm tra nguồn gốc và tính toàn vẹn, nhưng không tự chứng minh source code an toàn hoặc không có lỗ hổng.

## 4. Những đầu vào có thể làm artifact thay đổi

Một build Maven có nhiều đầu vào hơn các file Java:

| Nhóm đầu vào | Ví dụ có thể gây khác biệt |
|---|---|
| Source | Commit khác, file chưa commit, generated source, line ending |
| JDK | Vendor, major/patch version, javac, annotation processor |
| Maven | Maven distribution, core extension, Maven Wrapper |
| Plugin | Plugin version, plugin dependency, default configuration |
| Dependency | Version range, SNAPSHOT, artifact bị thay thế trên repository |
| Archive | Timestamp, entry order, manifest, compression |
| Environment | OS, architecture, locale, timezone, encoding, path |
| Build script | Profile tự kích hoạt, environment variable, property động |
| Generator | Random seed, thời gian hiện tại, thứ tự duyệt file |
| Native tool | C/C++ compiler, linker, system library và build flags |

Hãy xem build như một hàm có nhiều đầu vào. Nếu một đầu vào không được ghi nhận hoặc cố định, kết quả có thể thay đổi dù source không đổi.

## 5. Cố định source revision và trạng thái repository

Bắt đầu bằng một source tree sạch và xác định commit cụ thể.

Các nguyên tắc:

- Build từ một commit đã xác định, không build từ working tree có thay đổi chưa commit.
- Kiểm tra file untracked và ignored có tham gia vào build hay không.
- Khóa version của submodule nếu dự án dùng Git submodules.
- Đưa generated source vào quy trình tạo có thể tái lập.
- Không lấy version từ tên branch hoặc thời gian hiện tại.
- Nếu cần ghi revision vào artifact, dùng commit ID của source revision.
- Không để build tự lấy file tùy ý từ thư mục làm việc bên ngoài repository.

Kiểm tra trạng thái Git:

~~~bash
git status --short
git rev-parse HEAD
git submodule status
~~~

git status --short giúp phát hiện thay đổi chưa commit. git rev-parse HEAD xác định commit đang build. git submodule status hiển thị revision của submodule.

Build từ hai thư mục checkout sạch của cùng commit giúp phát hiện các phụ thuộc vô tình vào đường dẫn tuyệt đối, tên user hoặc nội dung còn sót trong workspace.

## 6. Cố định JDK và Maven runtime

Compiler, annotation processor, Javadoc, plugin và một số generator có thể tạo output khác nhau theo JDK.

Nên xác định:

- JDK vendor.
- JDK major và patch version cần dùng.
- Maven version.
- Hệ điều hành và architecture nếu chúng ảnh hưởng artifact.
- Native toolchain nếu build có thành phần native.

Kiểm tra runtime:

~~~powershell
java -version
javac -version
mvn -version
~~~

mvn -version hiển thị Maven version, Java version và Java home mà Maven process đang sử dụng.

Nếu dùng Maven Toolchains, hãy cố định toolchain JDK mà Compiler Plugin hoặc plugin khác sử dụng. Maven runtime JDK và compiler toolchain JDK có thể khác nhau; cần ghi nhận cả hai.

### 6.1. Dùng Maven Enforcer để kiểm tra điều kiện

Maven Enforcer Plugin có thể làm build thất bại sớm khi Maven hoặc Java runtime không đáp ứng version range.

Ví dụ yêu cầu Maven 3.9.9 và JDK 17:

~~~xml
<plugin>
  <groupId>org.apache.maven.plugins</groupId>
  <artifactId>maven-enforcer-plugin</artifactId>
  <version>3.6.3</version>
  <executions>
    <execution>
      <id>enforce-build-environment</id>
      <goals>
        <goal>enforce</goal>
      </goals>
      <configuration>
        <rules>
          <requireMavenVersion>
            <version>[3.9.9,4.0.0)</version>
          </requireMavenVersion>
          <requireJavaVersion>
            <version>[17,18)</version>
          </requireJavaVersion>
        </rules>
      </configuration>
    </execution>
  </executions>
</plugin>
~~~

Version range trong ví dụ là chính sách của dự án. Nếu tổ chức dùng JDK hoặc Maven khác, điều chỉnh range và đồng bộ với Maven Wrapper/CI.

Enforcer kiểm tra phiên bản runtime nhưng không tự cài JDK, Maven hoặc bảo đảm JDK đến từ một nguồn đáng tin cậy.

## 7. Pin Maven bằng Maven Wrapper

Maven Wrapper giúp mọi developer và CI runner dùng cùng Maven distribution mà không phụ thuộc Maven cài toàn cục.

Khởi tạo wrapper, ví dụ chọn Maven 3.9.9:

~~~powershell
mvn wrapper:wrapper -Dmaven=3.9.9
~~~

Sau đó dùng wrapper:

~~~powershell
mvnw.cmd -version
mvnw.cmd clean verify
~~~

Trên Linux/macOS:

~~~bash
./mvnw -version
./mvnw clean verify
~~~

File .mvn/wrapper/maven-wrapper.properties chứa distributionUrl chỉ tới Maven distribution đã chọn. Commit các wrapper script và file cấu hình cần thiết vào source control để mọi người dùng cùng phiên bản.

Maven Wrapper pin Maven distribution, không tự pin JDK runtime. Dùng Enforcer, CI image hoặc toolchain để kiểm soát JDK riêng.

### 7.1. Xác minh checksum của Wrapper và Maven distribution

Maven Wrapper hỗ trợ checksum SHA-256 cho file wrapper JAR và Maven distribution:

- wrapperSha256Sum: checksum của wrapper JAR.
- distributionSha256Sum: checksum của Maven distribution.

Lấy checksum từ nguồn phân phối chính thức đáng tin cậy, lưu cùng cấu hình wrapper và cập nhật khi nâng version. Không tự tạo checksum từ một file tải về không rõ nguồn rồi coi đó là xác minh độc lập.

## 8. Pin dependency và quản lý repository

Dependency động là một trong những nguồn gây build không tái lập.

Nên:

- Khai báo version cụ thể cho dependency trực tiếp.
- Dùng dependencyManagement hoặc BOM đã pin version.
- Kiểm tra dependency bắc cầu bằng mvn dependency:tree.
- Tránh version range nếu cần output ổn định.
- Tránh SNAPSHOT, LATEST và RELEASE trong release build.
- Dùng repository manager có chính sách không ghi đè release artifact.
- Cố định mirror/repository và thứ tự resolution.
- Kiểm tra checksum artifact tải về.
- Ghi nhận BOM và dependency graph của release.

Xem dependency graph:

~~~powershell
mvn dependency:tree
~~~

Xem POM hiệu lực sau khi kế thừa parent và profile:

~~~powershell
mvn help:effective-pom
~~~

Hai lệnh giúp phát hiện version hoặc cấu hình khác với điều mà POM ngắn gọn thể hiện.

### 8.1. Kiểm tra checksum khi tải artifact

Có thể yêu cầu Maven thất bại khi checksum không khớp:

~~~powershell
mvn -C clean verify
~~~

Tùy chọn -C bật strict checksum checking. Checksum cần đến từ repository hoặc nguồn được tin cậy. Nếu repository cho phép thay thế cả artifact lẫn checksum, checksum đơn lẻ từ cùng nguồn không chứng minh nguồn gốc artifact.

Không dùng repository mutable để lưu release version. Một tọa độ Maven như groupId/artifactId/version nên luôn trỏ tới cùng nội dung trong suốt vòng đời release.

## 9. Pin Maven plugin, parent POM và extension

Plugin cũng là đầu vào của build. Nếu không khai báo version, Maven có thể dùng version mặc định từ Super POM hoặc version được giải quyết theo cơ chế khác.

Cần cố định:

- Parent POM version.
- Build plugin version.
- Reporting plugin version nếu report được phát hành.
- Maven extension version trong .mvn/extensions.xml.
- Annotation processor version.
- Plugin dependency version.
- Code generator và schema compiler version.

Có thể dùng pluginManagement trong parent POM để quản lý version chung. Plugin vẫn phải được khai báo trong build/plugins ở module cần kích hoạt; pluginManagement chỉ định cấu hình mặc định, không tự chạy mọi plugin.

Không chỉ pin plugin trực tiếp. Hãy kiểm tra dependency mà plugin kéo theo và version thực tế được resolve.

## 10. Chuẩn hóa timestamp của archive

JAR, WAR, ZIP và các archive khác thường lưu timestamp cho từng entry. Nếu timestamp lấy từ thời điểm build, hai lần build ở hai thời điểm khác nhau có thể tạo file khác byte dù nội dung class giống nhau.

Maven hỗ trợ thuộc tính:

~~~xml
<properties>
  <project.build.outputTimestamp>2024-01-01T00:00:00Z</project.build.outputTimestamp>
</properties>
~~~

Đây là timestamp cố định dùng cho output archive của các plugin hỗ trợ reproducible output. Trong dự án thực tế, chọn một giá trị ổn định gắn với source revision hoặc release policy; mọi lần rebuild cùng source phải dùng cùng giá trị.

Một số plugin cũng chấp nhận số nguyên biểu diễn giây kể từ Unix epoch, tương tự quy ước SOURCE_DATE_EPOCH.

Không dùng maven.build.timestamp để ghi thời gian hiện tại vào manifest, resource hoặc generated source nếu mục tiêu là artifact giống byte-for-byte. Giá trị này đại diện thời điểm bắt đầu build nên thay đổi giữa các lần chạy.

Từ Maven 3.10.0 và Maven 4.0.0-beta-5, reproducible mode được kích hoạt mặc định theo hướng dẫn Maven hiện tại. Việc khai báo project.build.outputTimestamp trong POM vẫn hữu ích để đặt timestamp cố định rõ ràng và ghi đè giá trị mặc định được kế thừa.

## 11. Dùng plugin hỗ trợ reproducible archive

Không phải mọi phiên bản plugin đều chuẩn hóa archive giống nhau. Nâng cấp lên phiên bản có hỗ trợ reproducible build và cấu hình timestamp thống nhất.

Ví dụ cấu hình JAR Plugin:

~~~xml
<plugin>
  <groupId>org.apache.maven.plugins</groupId>
  <artifactId>maven-jar-plugin</artifactId>
  <version>3.5.0</version>
  <configuration>
    <archive>
      <manifest>
        <mainClass>demo.App</mainClass>
      </manifest>
    </archive>
  </configuration>
</plugin>
~~~

JAR Plugin hỗ trợ outputTimestamp và mặc định lấy từ project.build.outputTimestamp. Các archive plugin khác như WAR, EAR, Assembly, Source và Shade cần được kiểm tra theo version và tài liệu riêng.

Maven cung cấp lệnh:

~~~powershell
mvn artifact:check-buildplan
~~~

Goal này kiểm tra build plan và chỉ ra plugin nào cần nâng cấp để có hỗ trợ reproducible build. Danh sách yêu cầu phụ thuộc plugin đang được dùng; xử lý từng cảnh báo thay vì giả định tất cả plugin đều đã hỗ trợ.

## 12. Chuẩn hóa encoding, locale, timezone và thứ tự file

Các giá trị môi trường có thể ảnh hưởng đến generated resource, report, tên file và nội dung archive.

Nên xác định rõ:

- Source/resource encoding, thường dùng UTF-8.
- Timezone, thường chọn UTC cho dữ liệu build.
- Locale/language/country nếu generator format số hoặc ngày.
- Line ending của source và resource.
- Cách sắp xếp file và entry trong archive.
- Quy tắc viết hoa/thường của đường dẫn.
- File permission nếu tạo archive trên hệ thống khác nhau.

Ví dụ .mvn/jvm.config:

~~~text
-Dfile.encoding=UTF-8
-Duser.timezone=UTC
-Duser.language=en
-Duser.country=US
~~~

Trong POM:

~~~xml
<properties>
  <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  <project.reporting.outputEncoding>UTF-8</project.reporting.outputEncoding>
</properties>
~~~

Không dựa vào thứ tự duyệt file từ filesystem nếu thứ tự đó có thể khác giữa OS hoặc filesystem. Generator nên sắp xếp input bằng một comparator xác định trước khi ghi output.

Có thể dùng .gitattributes để thống nhất line ending cho các loại file văn bản:

~~~text
*.java text eol=lf
*.xml text eol=lf
*.properties text eol=lf
~~~

Chọn chính sách line ending phù hợp với repository. Quan trọng là source và resource được checkout theo một quy tắc nhất quán.

## 13. Loại bỏ dữ liệu không xác định khỏi generated output

Một số plugin hoặc script có thể ghi thông tin môi trường vào artifact:

- Thời điểm hiện tại.
- Username hoặc hostname.
- Đường dẫn workspace tuyệt đối.
- Tên branch hoặc trạng thái working tree.
- Random UUID hoặc random seed không cố định.
- Kết quả truy vấn mạng tại thời điểm build.
- Thứ tự file phụ thuộc filesystem.
- Version dependency được lấy động.
- Giá trị environment variable không được kiểm soát.

Nếu cần đưa build metadata vào artifact, chọn dữ liệu ổn định như commit ID, version release hoặc source revision. Tránh ghi dữ liệu cá nhân và đường dẫn máy cục bộ.

Với generator dùng random, cung cấp seed cố định và bảo đảm thuật toán không phụ thuộc thứ tự iteration. Nếu random là một phần có chủ đích của sản phẩm, cần tách nó khỏi quá trình tạo artifact hoặc xác định seed theo source revision.

## 14. Kiểm soát profile, test và code generation

Maven profile có thể được kích hoạt bởi OS, JDK, property, file hoặc environment variable. Hai máy có thể chạy hai profile khác nhau dù dùng cùng POM.

Để build tái lập:

- Khai báo rõ profile cần dùng trong CI.
- Tránh profile tự kích hoạt dựa trên môi trường không được ghi nhận.
- Ghi lại các property -D ảnh hưởng artifact.
- Pin annotation processor và plugin code generation.
- Dùng cùng schema, OpenAPI, protobuf hoặc nguồn codegen.
- Kiểm soát thứ tự input cho generator.
- Dùng fixed clock hoặc fixed seed cho test và generator khi phù hợp.

Test flakiness có thể khiến build pass/fail khác nhau dù artifact compile giống nhau. Với test liên quan thời gian, random hoặc concurrency, dùng clock giả lập, seed cố định và đồng bộ hóa rõ ràng.

Nếu plugin tạo file report chứa thời gian chạy, username hoặc absolute path, artifact report đó cũng có thể không reproducible dù JAR chính đã ổn định.

## 15. Kiểm soát CI và môi trường build

CI cần tái tạo cùng tập đầu vào trên mỗi runner.

Các thực hành hữu ích:

1. Dùng Maven Wrapper để pin Maven.
2. Dùng JDK image hoặc toolchain có version rõ ràng.
3. Pin container image bằng digest thay vì chỉ dùng tag có thể thay đổi.
4. Cố định OS và CPU architecture khi build phụ thuộc native tool.
5. Dùng cùng Maven settings, mirror và repository policy.
6. Không để build phụ thuộc file có sẵn trong cache local.
7. Tạo workspace sạch từ commit xác định.
8. Khóa environment variable và Maven profiles ảnh hưởng output.
9. Ghi lại tool versions và dependency graph.
10. Chạy build độc lập trên runner khác để xác minh.

Container giúp tái tạo môi trường gần giống nhau. Tuy nhiên, cần pin image digest, architecture và toolchain bên trong. Native library hoặc compiler có thể phụ thuộc kernel, linker, system package và CPU architecture của runner.

## 16. Ví dụ Maven hoàn chỉnh tạo JAR có timestamp cố định

Ví dụ này tạo một JAR Java 17. Maven, lifecycle plugin, compiler và JAR plugin đều được pin version; encoding và archive timestamp được khai báo tường minh.

Cấu trúc:

~~~text
reproducible-demo/
  pom.xml
  src/
    main/
      java/
        demo/
          App.java
~~~

Tạo pom.xml:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>

  <groupId>com.example</groupId>
  <artifactId>reproducible-demo</artifactId>
  <version>1.0.0</version>
  <name>Reproducible Demo</name>

  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    <project.reporting.outputEncoding>UTF-8</project.reporting.outputEncoding>
    <project.build.outputTimestamp>2024-01-01T00:00:00Z</project.build.outputTimestamp>
  </properties>

  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-clean-plugin</artifactId>
        <version>3.4.0</version>
      </plugin>

      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-resources-plugin</artifactId>
        <version>3.3.1</version>
      </plugin>

      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.13.0</version>
        <configuration>
          <release>17</release>
          <encoding>UTF-8</encoding>
        </configuration>
      </plugin>

      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-jar-plugin</artifactId>
        <version>3.5.0</version>
        <configuration>
          <archive>
            <manifest>
              <mainClass>demo.App</mainClass>
            </manifest>
          </archive>
        </configuration>
      </plugin>
    </plugins>
  </build>
</project>
~~~

Tạo src/main/java/demo/App.java:

~~~java
package demo;

public final class App {
    private App() {
    }

    public static void main(String[] args) {
        System.out.println("Reproducible Maven build.");
    }
}
~~~

Chạy build:

~~~powershell
mvn clean package
~~~

Chạy JAR:

~~~powershell
java -jar target/reproducible-demo-1.0.0.jar
~~~

Stdout của ứng dụng:

~~~text
Reproducible Maven build.
~~~

Ví dụ cố định timestamp của archive entry và pin các plugin tạo artifact chính. Khi chạy trên cùng JDK 17 và cùng Maven/runtime inputs, hai lần build sạch có thể tạo JAR giống byte-for-byte.

POM này minh họa cấu hình archive. Để chứng minh độc lập giữa hai môi trường, cần kiểm tra thêm dependency, JDK patch/vendor, Maven distribution, OS/architecture, environment và các plugin/extension khác mà dự án thực tế sử dụng.

## 17. Kiểm tra reproducibility bằng Maven Artifact Plugin

Maven có maven-artifact-plugin để so sánh artifact hiện tại với bản tham chiếu.

Cách kiểm tra hai lần build trong cùng local Maven repository:

~~~powershell
mvn clean install
mvn clean verify org.apache.maven.plugins:maven-artifact-plugin:3.7.0:compare
~~~

Lần đầu build và install artifact tham chiếu. Lần thứ hai clean và build lại, sau đó goal compare đối chiếu output mới với artifact đã install.

Goal compare có thể tạo file .buildcompare chứa kết quả. Nếu khác biệt, log sẽ chỉ ra artifact cần điều tra. Goal này không thread-safe; tránh chạy nó trong parallel Maven build.

Có thể dùng artifact:check-buildplan để phát hiện plugin cần nâng cấp và artifact:buildinfo để ghi thông tin về build/artifact.

Kiểm tra trong cùng máy là bước sàng lọc hữu ích nhưng chưa chứng minh third party có thể tái tạo artifact. Hai lần chạy vẫn có thể chia sẻ cùng cache, path, OS, user và JDK.

## 18. So sánh độc lập bằng SHA-256

Để kiểm tra giữa hai môi trường:

1. Checkout cùng một commit vào hai workspace sạch.
2. Dùng cùng Maven Wrapper và JDK đã xác định.
3. Dùng cùng dependency repository và build arguments.
4. Chạy clean package ở cả hai workspace.
5. Tính SHA-256 của artifact.
6. So sánh hai digest.

Trên Windows PowerShell:

~~~powershell
Get-FileHash target\reproducible-demo-1.0.0.jar -Algorithm SHA256
~~~

Trên Linux:

~~~bash
sha256sum target/reproducible-demo-1.0.0.jar
~~~

Nếu SHA-256 giống nhau, hai file có nội dung byte-for-byte giống nhau với độ tin cậy rất cao. Nếu hash khác, cần tìm phần khác biệt thay vì chỉ kiểm tra lại source.

Hash chỉ xác nhận hai file giống nhau; nó không tự chứng minh cả hai được build từ source đáng tin cậy. Muốn kiểm chứng độc lập, bên thứ ba cần tự lấy source revision, tái tạo môi trường và chạy build.

## 19. Điều tra artifact khác nhau bằng diffoscope

Khi hash khác, dùng diffoscope để xem khác biệt bên trong JAR, ZIP, TAR hoặc các định dạng nhị phân được hỗ trợ.

Ví dụ:

~~~bash
diffoscope build-a/target/reproducible-demo-1.0.0.jar build-b/target/reproducible-demo-1.0.0.jar
~~~

Những khác biệt thường gặp:

- Timestamp entry trong archive.
- Thứ tự file trong JAR.
- Manifest hoặc pom.properties.
- Nội dung generated resource.
- Build metadata có username, path hoặc thời gian.
- Class file khác do JDK/compiler/annotation processor.
- Dependency hoặc plugin khác version.
- Compression hoặc native tool khác version.

Quy trình điều tra:

1. So sánh file size và danh sách entry.
2. Dùng diffoscope để xác định entry khác.
3. Xác định plugin hoặc generator tạo entry đó.
4. Kiểm tra version/configuration của plugin.
5. Kiểm tra source input và environment variable.
6. Sửa nguồn nondeterminism.
7. Build lại trong hai workspace độc lập và so sánh hash.

Không nên loại bỏ file khác khỏi phép so sánh chỉ để làm báo cáo pass. Nếu một artifact được phát hành, cần giải thích mọi khác biệt có ý nghĩa.

## 20. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| JAR khác hash sau mỗi lần build | Archive entry timestamp thay đổi | Đặt project.build.outputTimestamp và dùng plugin hỗ trợ |
| Máy local và CI tạo JAR khác nhau | JDK, Maven, plugin hoặc OS khác | Pin toolchain, Maven Wrapper và CI image |
| Manifest khác | Build metadata hoặc plugin tạo manifest không ổn định | Kiểm tra archive/manifest configuration |
| Resource khác nội dung | Filtering dùng timestamp, environment hoặc encoding khác | Dùng property cố định và UTF-8 |
| Generated source khác | Generator dùng random, thời gian hoặc thứ tự file | Cố định seed, clock và sort input |
| Dependency graph khác | SNAPSHOT, version range hoặc repository mutable | Pin version và dùng repository bất biến |
| Build pass local nhưng fail CI | Cache, profile hoặc environment khác | Build từ workspace sạch và so sánh effective POM |
| Maven version khác | Developer gọi mvn toàn cục | Dùng mvnw/mvnw.cmd |
| artifact:compare báo khác | Có entry không reproducible hoặc build environment khác | Đọc .buildcompare, dùng diffoscope |
| Hai hash khác nhưng class giống | Khác timestamp, manifest, archive order hoặc compression | So sánh nội dung archive và metadata |

## 21. Bảo mật và giới hạn của reproducible build

Reproducible build tăng khả năng kiểm chứng supply chain, nhưng cần hiểu giới hạn:

- Hai lần build giống nhau không chứng minh source không có lỗ hổng.
- Cùng một dependency độc hại có thể được build lại một cách hoàn toàn reproducible.
- Artifact đã ký có thể chứa timestamp hoặc chữ ký phụ thuộc thời điểm và quy trình ký.
- Build có native output thường phụ thuộc OS, architecture, compiler và linker.
- Plugin không hỗ trợ reproducible output có thể làm một phần artifact khác nhau.
- Container không loại bỏ mọi yếu tố bên ngoài như kernel, architecture hoặc network dependency.

Nên tách bước build artifact không ký và bước ký/phát hành nếu quy trình ký có timestamp hoặc dữ liệu biến động. Ghi lại source revision, toolchain, dependency graph, checksum và build environment để người khác có thể xác minh.

## 22. Quy trình triển khai build tái lập

1. Chọn source commit sạch và cố định revision.
2. Pin Maven bằng Wrapper và xác minh checksum distribution.
3. Pin JDK vendor/version và xác định architecture.
4. Dùng Enforcer để kiểm tra Maven/JDK runtime.
5. Pin parent POM, dependency, BOM, plugin, extension và annotation processor.
6. Tránh SNAPSHOT, version range và repository mutable trong release build.
7. Đặt project.build.outputTimestamp cố định.
8. Nâng cấp archive plugin và chạy artifact:check-buildplan.
9. Chuẩn hóa encoding, locale, timezone, line ending và thứ tự file.
10. Loại timestamp, username, absolute path và random data khỏi generated output.
11. Build trong CI workspace sạch, image và toolchain đã pin.
12. Chạy artifact:compare để sàng lọc khác biệt giữa hai lần build.
13. Build độc lập từ cùng commit ở workspace/máy khác.
14. So sánh SHA-256 và dùng diffoscope khi khác.
15. Lưu build metadata, checksum và kết quả xác minh cùng release.

## 23. Checklist build tái lập

- [ ] Source commit được xác định và working tree sạch.
- [ ] Submodule và generated source được kiểm soát.
- [ ] Maven Wrapper pin đúng Maven distribution.
- [ ] Wrapper JAR/distribution có checksum được xác minh.
- [ ] JDK vendor, version và architecture được xác định.
- [ ] Maven Enforcer kiểm tra Maven/JDK runtime.
- [ ] Parent POM, dependency và BOM có version cụ thể.
- [ ] Không dùng SNAPSHOT hoặc dynamic dependency version trong release build.
- [ ] Maven plugin, extension và annotation processor đã pin version.
- [ ] Repository không thay thế nội dung release artifact.
- [ ] Strict checksum checking được dùng khi phù hợp.
- [ ] project.build.outputTimestamp được cố định.
- [ ] Archive plugin hỗ trợ reproducible output.
- [ ] Không nhúng build timestamp, username hoặc absolute path vào artifact.
- [ ] Encoding, locale, timezone và line ending được chuẩn hóa.
- [ ] Generator có thứ tự input và random seed xác định.
- [ ] CI image/toolchain và environment variable được kiểm soát.
- [ ] Build từ hai workspace sạch đã được so sánh.
- [ ] SHA-256 của artifact khớp giữa các lần build.
- [ ] Khác biệt được điều tra bằng .buildcompare hoặc diffoscope.
- [ ] Build metadata và checksum được lưu cùng release.

Build tái lập yêu cầu kiểm soát toàn bộ đầu vào tạo artifact, không chỉ source code. Trong Maven, hãy pin Maven/JDK/dependency/plugin, chuẩn hóa timestamp bằng project.build.outputTimestamp, dùng plugin hỗ trợ reproducible archive và kiểm soát environment. Sau đó build lại từ workspace độc lập, so sánh SHA-256 và điều tra khác biệt bằng Maven Artifact Plugin hoặc diffoscope. Đây là cách tạo bằng chứng có thể kiểm tra độc lập rằng artifact phát hành thực sự tương ứng với source revision đã công bố.

## Tài liệu tham khảo

- Apache Maven, Configuring for Reproducible Builds: https://maven.apache.org/guides/mini/guide-reproducible-builds.html
- Apache Maven, Guide to Configuring Archive Plugins: https://maven.apache.org/guides/mini/guide-archive-configuration.html
- Apache Maven, Maven Wrapper: https://maven.apache.org/tools/mavenwrapper.html
- Apache Maven Wrapper, Checksum Verification: https://maven.apache.org/tools/wrapper/
- Apache Maven Artifact Plugin, artifact:compare: https://maven.apache.org/plugins/maven-artifact-plugin/compare-mojo.html
- Apache Maven Artifact Plugin, artifact:check-buildplan: https://maven.apache.org/plugins/maven-artifact-plugin/plugin-issues.html
- Apache Maven Enforcer Plugin, Require Maven Version: https://maven.apache.org/components/enforcer/enforcer-rules/requireMavenVersion.html
- Apache Maven JAR Plugin, jar:jar: https://maven.apache.org/plugins-archives/maven-jar-plugin-3.5.0/jar-mojo.html
- Reproducible Builds Project: https://reproducible-builds.org/
