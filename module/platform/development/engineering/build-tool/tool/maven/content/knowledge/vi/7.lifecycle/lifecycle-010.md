
# Maven install, deploy và sự khác nhau giữa kho cục bộ với kho từ xa

## 1. Vì sao install và deploy tồn tại?

Khi một dự án Java được biên dịch và kiểm thử thành công, Maven có thể tạo ra một **artifact** (sản phẩm xây dựng, ví dụ JAR, WAR hoặc POM). Tuy nhiên, việc có một tệp JAR trong thư mục `target/` chưa đủ để dự án khác tự lấy nó làm thư viện. Maven cần một cơ chế lưu trữ artifact bằng tọa độ và một cơ chế chia sẻ chúng.

**`install` đưa artifact vào kho Maven cục bộ (local repository) trên máy đang chạy. `deploy` xuất bản artifact tới kho Maven từ xa (remote repository) để các hệ thống khác có thể sử dụng theo quyền truy cập.** Đây là hai phase liên tiếp của vòng đời build mặc định, phục vụ hai phạm vi khác nhau.

```text
                 pom.xml + src/
                       |
                    compile
                       |
                      test
                       |
                     package
                       |     -> target/math-kit-1.0.0-SNAPSHOT.jar
                     verify
                       |
                     install
                       |     -> ~/.m2/repository/.../math-kit/
                     deploy
                             -> remote repository (Nexus, Artifactory, ...)
                                         |
                                   máy khác / CI
```

Sơ đồ biểu thị đường đi của sản phẩm và thứ tự phase. Deploy Plugin nhận artifact của bản build và thông tin dự án để xuất bản; không nên hiểu nó đơn giản là sao chép thủ công một tệp từ `~/.m2/repository` lên máy chủ.

Cần phân biệt ngay: **Maven `deploy` mặc định công bố artifact vào kho Maven, không phải đưa một ứng dụng đang chạy lên production.** Quy trình triển khai runtime lên VM, Kubernetes hay hệ thống máy chủ thường sử dụng công cụ riêng sau khi đã có artifact.

## 2. Mối liên hệ của install, deploy với lifecycle

Default lifecycle của Maven có nhiều phase. Những mốc chính là:

```text
validate -> compile -> test -> package -> verify -> install -> deploy
```

Maven còn các phase trung gian, ví dụ `process-resources`, `test-compile`, `integration-test` và `post-integration-test`. Chúng vẫn được xét theo đúng thứ tự, dù sơ đồ trên lược bỏ để dễ nhớ.

| Lệnh | Hoạt động chính sau các phase phía trước | Đích kết quả |
| --- | --- | --- |
| `mvn compile` | Biên dịch mã Java chính | `target/classes` |
| `mvn test` | Biên dịch và chạy unit test theo cấu hình | `target/test-classes`, báo cáo test |
| `mvn package` | Đóng gói các lớp và tài nguyên | JAR/WAR trong `target/` |
| `mvn verify` | Kiểm tra các kết quả bằng những plugin goal đã cấu hình | Mốc kiểm tra chất lượng |
| `mvn install` | Cài artifact cùng POM và attached artifacts nếu có | Local Maven repository |
| `mvn deploy` | Xuất bản artifact/POM và metadata liên quan | Remote Maven repository |

Với kiểu đóng gói `jar` thông thường, Maven gắn `install:install` vào phase `install` và `deploy:deploy` vào phase `deploy`. Maven thực thi các phase cho đến **phase cuối mà người dùng yêu cầu**. Vì vậy:

- `mvn install` đã chạy những bước trước nó, bao gồm `package` và `verify`.
- `mvn deploy` đã chạy cả `install` trong cùng lần thực thi lifecycle.
- Không cần chạy liên tiếp `mvn compile`, `mvn test`, `mvn package`, `mvn install` rồi `mvn deploy` để có một lần phát hành: một lệnh `mvn deploy` là đủ khi cấu hình sẵn sàng.
- `mvn clean deploy` chạy `clean` thuộc lifecycle riêng trước khi chạy đến `deploy`. `clean` xóa đầu ra dự án như `target/`; nó không có nghĩa xóa local repository.
- Nếu test hoặc một kiểm tra gắn vào `verify` thất bại, quá trình build bình thường dừng, nên chưa đến `install` hoặc `deploy`.

**Phase khác với plugin goal.** `mvn install` chạy lifecycle đến phase đó; `mvn install:install` gọi trực tiếp một goal và không bảo đảm rằng mã đã được biên dịch/đóng gói trong chính lệnh ấy. Khi thực hành, hãy gọi phase phù hợp.

## 3. Kho cục bộ là gì?

**Local Maven repository** là nơi Maven giữ các artifact đã tải để phân giải dependency/plugin và những artifact do dự án cài bằng `mvn install`. Trên cấu hình Maven 3.x thông dụng, nó nằm tại:

```text
Linux/macOS: ~/.m2/repository/
Windows: C:\Users\<tai-khoan>\.m2\repository\
```

Đường dẫn thực tế có thể thay đổi bởi cấu hình `<localRepository>` trong `settings.xml` hoặc đối số dòng lệnh `-Dmaven.repo.local=...`. Nếu cần kiểm chứng, hãy đọc effective settings và log Maven thay vì mặc định kho luôn nằm trong home.

Artifact có **tọa độ Maven** gồm `groupId:artifactId:version`. Ví dụ:

```text
dev.example:math-kit:1.0.0-SNAPSHOT
```

Đường dẫn trong local repository theo cấu trúc này có dạng:

```text
~/.m2/repository/
└── dev/
    └── example/
        └── math-kit/
            └── 1.0.0-SNAPSHOT/
                ├── math-kit-1.0.0-SNAPSHOT.jar
                ├── math-kit-1.0.0-SNAPSHOT.pom
                └── các tệp metadata/phụ trợ nếu có
```

Ở đó, dấu chấm trong `groupId` tương ứng các cấp thư mục. Maven lưu cả POM vì bên tiêu thụ cần metadata để hiểu dependency, phiên bản và cấu hình liên quan. Với dự án có `<packaging>pom</packaging>`, không có JAR chính; artifact là POM.

Kho cục bộ có **hai vai trò riêng**:

1. Cache các dependency và plugin Maven đã tải từ repository từ xa, giúp hạn chế truy cập mạng ở lần build sau.
2. Nhận artifact tự build qua `install`, để những dự án độc lập khác **trên cùng máy và cùng cấu hình kho** có thể dùng.

Đây là kho riêng của máy hoặc môi trường chạy Maven. Một dự án trên máy đồng nghiệp **không tự thấy artifact bạn vừa install**. Và thư mục `target/` không phải là local repository: `target/` chứa lớp biên dịch, báo cáo test và sản phẩm tạm của một lần build dự án.

## 4. Kho từ xa là gì?

**Remote Maven repository** là kho truy cập qua mạng, thường bằng HTTPS và có thể được quản lý bằng Maven Central, Nexus Repository, Artifactory hoặc một hệ thống hỗ trợ định dạng kho Maven. Một kho từ xa có thể cho phép tải artifact, nhận artifact được xuất bản hoặc cả hai tùy chính sách.

| Tiêu chí | Local repository | Remote repository |
| --- | --- | --- |
| Vị trí | Máy đang chạy Maven | Máy chủ có thể truy cập qua mạng |
| Mục đích | Cache và cài artifact phục vụ build cục bộ | Chia sẻ artifact cho nhiều máy/nhóm |
| Artifact được ghi bằng | `mvn install` | `mvn deploy` |
| Cần kết nối mạng khi ghi | Không cần để ghi artifact đã build; build vẫn có thể tải dependency | Thường cần mạng và quyền ghi |
| Người có thể sử dụng | Các lần build dùng chung local repository | Những client có cấu hình và quyền truy cập |
| Liên quan đến phát hành | Dùng thử và build dự án cục bộ | Công bố artifact cho CI, các nhóm và hệ thống khác |

Một remote repository dùng để tải phụ thuộc không nhất thiết cho phép publish. Cấu hình **đọc** và **ghi** cần được phân biệt rõ:

- `<repositories>` trong POM: các nguồn có thể tải dependency.
- `<pluginRepositories>`: nguồn có thể tải plugin Maven.
- `<mirrors>` trong `settings.xml`: chuyển hướng các repository được chỉ định khi tải.
- `<distributionManagement>` trong POM: khai báo **đích xuất bản** dự án cho Deploy Plugin.
- `<servers>` trong settings: khai báo thông tin xác thực liên kết với ID của máy chủ/kho.

Đổi đường dẫn local repository hoặc cấu hình mirror không tự biến kho đó thành nơi nhận `deploy`. Muốn xuất bản phải có đích upload rõ ràng và quyền phù hợp.

## 5. Dự án Java 17 thực hành install

Tạo thư mục với những tệp sau:

```text
math-kit/
├── pom.xml
└── src/
    ├── main/java/dev/example/MathKit.java
    └── test/java/dev/example/MathKitTest.java
```

Tạo `pom.xml` hoàn chỉnh cho Maven 3.9.x và JDK 17+:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.example</groupId>
    <artifactId>math-kit</artifactId>
    <version>1.0.0-SNAPSHOT</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.4</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

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
                <version>3.5.2</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-install-plugin</artifactId>
                <version>3.1.4</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-deploy-plugin</artifactId>
                <version>3.1.4</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Tệp `src/main/java/dev/example/MathKit.java`:

```java
package dev.example;

public final class MathKit {
    private MathKit() {
    }

    public static int add(int left, int right) {
        return Math.addExact(left, right);
    }

    public static void main(String[] args) {
        System.out.println(add(7, 5));
    }
}
```

Tệp `src/test/java/dev/example/MathKitTest.java`:

```java
package dev.example;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class MathKitTest {
    @Test
    void addsTwoNumbers() {
        assertEquals(12, MathKit.add(7, 5));
    }

    @Test
    void reportsOverflow() {
        assertThrows(ArithmeticException.class,
                () -> MathKit.add(Integer.MAX_VALUE, 1));
    }
}
```

Ở thư mục chứa `pom.xml`, chạy:

```bash
mvn -version
mvn clean verify
java -cp target/classes dev.example.MathKit
mvn install
```

Lệnh Java in **chính xác**:

```text
12
```

Khi `mvn clean verify` thành công, hai kiểm thử của `MathKitTest` phải đạt và JAR được tạo trong `target/math-kit-1.0.0-SNAPSHOT.jar`. Khi `mvn install` thành công, Maven cài JAR và POM vào local repository. Nếu dùng đường dẫn mặc định, kiểm tra:

```bash
ls "$HOME/.m2/repository/dev/example/math-kit/1.0.0-SNAPSHOT/"
```

Trên Windows PowerShell:

```powershell
Get-ChildItem (Join-Path $env:USERPROFILE ".m2/repository/dev/example/math-kit/1.0.0-SNAPSHOT")
```

Các lệnh kiểm tra giả định local repository chưa bị thay đổi bởi settings hoặc tham số Maven. `pom.xml` trên **chưa khai báo nơi deploy**, vì mục này chỉ hướng dẫn cài vào kho cục bộ.

## 6. Dự án khác sử dụng artifact vừa install

Một dự án thứ hai trên cùng máy có thể khai báo đoạn sau **bên trong `<dependencies>` của POM**:

```xml
<dependency>
    <groupId>dev.example</groupId>
    <artifactId>math-kit</artifactId>
    <version>1.0.0-SNAPSHOT</version>
</dependency>
```

Nếu hai dự án dùng cùng local repository, Maven có thể tìm artifact vừa install và cho phép lớp trong dự án thứ hai gọi `dev.example.MathKit.add(2, 3)`.

Nhưng có ba trường hợp cần nhận biết:

1. **Máy khác:** local repository của đồng nghiệp không có artifact đó; nếu chưa có bản được publish lên một remote repository họ truy cập được, Maven có thể báo thiếu dependency.
2. **Hai kho local khác nhau trên cùng máy:** lệnh `mvn "-Dmaven.repo.local=$HOME/.m2/repo-a" install` cài vào kho `repo-a`; build dùng `repo-b` sẽ không tự nhìn thấy bản đó.
3. **Multi-module reactor:** khi build các module liên quan trong cùng một Maven reactor, Maven có thể giải quyết dependency giữa những module trong reactor mà không cần install chúng từng cái trước. `install` đặc biệt có ích khi build hai dự án độc lập trên cùng máy.

Đó là lý do `install` không phải là một cách phát hành cho toàn bộ nhóm, dù nó rất thuận tiện khi phát triển thư viện cục bộ.

## 7. Khai báo đích xuất bản trong distributionManagement

Muốn dùng `mvn deploy`, trước hết phải có một kho artifact thực sự và được cấp quyền ghi. Trong POM, thêm đoạn sau **cùng cấp với `<build>` bên trong `<project>`**:

```xml
<distributionManagement>
    <repository>
        <id>team-releases</id>
        <name>Team releases</name>
        <url>https://repo.example.org/repository/maven-releases/</url>
    </repository>
    <snapshotRepository>
        <id>team-snapshots</id>
        <name>Team snapshots</name>
        <url>https://repo.example.org/repository/maven-snapshots/</url>
    </snapshotRepository>
</distributionManagement>
```

Đoạn này chỉ **minh họa cú pháp**. Miền `repo.example.org` không phải địa chỉ repository để thực hành xuất bản. Hãy dùng URL thực được cung cấp bởi hệ thống quản trị artifact khi có quyền; đừng thử deploy vào một địa chỉ đoán.

Hai mục tiêu khác nhau:

- `repository` thường nhận phiên bản phát hành ổn định như `1.0.0`.
- `snapshotRepository` thường nhận phiên bản đang phát triển như `1.0.0-SNAPSHOT`.

Nếu `snapshotRepository` không được khai báo, Maven có thể dùng `repository` làm đích cho SNAPSHOT; kho đích vẫn có thể từ chối nếu chính sách chỉ cho phép release. Tách riêng hai kho giúp việc quản lý phiên bản rõ ràng hơn.

**Không dùng `<repositories>` để khai báo đích upload.** `<repositories>` mô tả nơi Maven tìm các thư viện cần tải, còn `<distributionManagement>` chỉ ra nơi xuất bản artifact do dự án xây dựng.

## 8. Ghép repository ID với credential trong settings.xml

Maven đọc thông tin xác thực môi trường từ `settings.xml`, thường tại `~/.m2/settings.xml`, hoặc từ tệp được chọn bằng `mvn -s <path>`. Cấu hình phía máy không nên đưa vào repository mã nguồn.

Ví dụ **đoạn nằm bên trong thẻ `<settings>`**:

```xml
<servers>
    <server>
        <id>team-releases</id>
        <username>${env.MAVEN_REPO_USER}</username>
        <password>${env.MAVEN_REPO_TOKEN}</password>
    </server>
    <server>
        <id>team-snapshots</id>
        <username>${env.MAVEN_REPO_USER}</username>
        <password>${env.MAVEN_REPO_TOKEN}</password>
    </server>
</servers>
```

Đây **không phải toàn bộ tệp `settings.xml`**. Ví dụ giả định các biến môi trường `MAVEN_REPO_USER` và `MAVEN_REPO_TOKEN` đã được thiết lập an toàn bởi hệ điều hành hoặc CI; Maven có thể nội suy các biến `env.*` trong settings. Không ghi giá trị token thật vào POM, tệp README, log hoặc commit Git.

Maven ghép `<id>` của đích trong `distributionManagement` với `<server><id>` trong settings. Hai ID phải khớp. Nếu POM dùng `team-snapshots` còn settings chỉ có `team-snapshot`, Maven không tự biết hai tên đó tương đương. Tùy tình huống, kho có thể trả `401 Unauthorized` hoặc `403 Forbidden`.

Chỉ cấp credential có quyền ghi cho job thật sự được phép phát hành; job kiểm thử PR chỉ cần quyền tải. Có thể dùng token ngắn hạn và kho bí mật của nền tảng CI. Không commit một tệp settings cá nhân có username/password.

## 9. Chạy deploy đúng quy trình

Khi POM đã chứa đích thực, credential đã được cấu hình và nhóm cho phép xuất bản, lệnh trong pipeline có thể là:

```bash
mvn -B -ntp clean deploy
```

Giải thích:

- `-B` chạy batch mode, phù hợp môi trường không có tương tác.
- `-ntp` hạn chế dòng tiến độ tải trong log.
- `clean` làm sạch thư mục đầu ra `target/`.
- `deploy` thực hiện những phase đến `deploy`, gồm compile, test, package, verify, install, rồi công bố artifact lên remote repository.

Deploy Plugin thường xuất bản artifact chính, POM và các attached artifacts đã được tạo (ví dụ sources, javadoc nếu có plugin tương ứng), cùng metadata cần thiết của repository.

**Không cần chạy `mvn install` rồi `mvn deploy` liên tiếp chỉ để publish một bản.** Lệnh sau đã bao gồm phase trước. Nếu kiểm thử thất bại, việc ép chạy trực tiếp plugin goal để bỏ qua kiểm tra có thể phát hành sản phẩm chưa đạt chất lượng; quy trình chuẩn nên yêu cầu `verify` đạt trước.

Trong CI, cách phân chia phổ biến là: nhánh/PR chạy `mvn clean verify`; job phát hành được cấp quyền mới chạy `mvn clean deploy` sau khi đáp ứng điều kiện review, version và bảo mật. Có thể dùng Maven Wrapper (`./mvnw` hoặc `mvnw.cmd`) nếu dự án đã cung cấp.

## 10. SNAPSHOT khác release và ảnh hưởng tới deploy

Một phiên bản `1.0.0-SNAPSHOT` là **bản đang phát triển**; nhiều build có thể sử dụng cùng tọa độ SNAPSHOT nhưng nội dung thay đổi. Repository hỗ trợ SNAPSHOT có thể lưu bản xuất bản thực tế với thông tin thời gian và số build, kết hợp metadata để chỉ tới các bản tương ứng.

Phiên bản `1.0.0` thường là **release** đã công bố. Nhiều repository manager chặn việc xuất bản lại cùng phiên bản release nhằm giữ nguyên nội dung được tham chiếu bởi các hệ thống tiêu thụ.

| Tiêu chí | SNAPSHOT | Release |
| --- | --- | --- |
| Ví dụ | `1.0.0-SNAPSHOT` | `1.0.0` |
| Mục đích | Tích hợp thử trong quá trình phát triển | Phát hành có kiểm soát |
| Kho thường dùng | `snapshotRepository` | `repository` |
| Có thể có bản mới cùng tọa độ? | Thường có, theo quy tắc snapshot | Thường không, theo chính sách bất biến |
| Máy tiêu thụ cập nhật khi nào? | Theo metadata và chính sách kiểm tra cập nhật | Khi chọn version release mới |

Một bản SNAPSHOT mới xuất bản **không chắc lập tức xuất hiện ở mọi máy**, vì Maven có cache và chính sách cập nhật metadata. Trong tình huống thích hợp có thể dùng `mvn -U` để yêu cầu kiểm tra lại cập nhật SNAPSHOT; nó không khắc phục URL sai, credential thiếu hoặc artifact chưa tồn tại.

Khi cần phát hành sửa lỗi cho thư viện, hãy tăng version release, không sửa nội dung của một version đã công bố. Như vậy mỗi bản có thể được nhận diện và truy vết qua tọa độ.

## 11. Xác minh install và deploy bằng bằng chứng nào?

### Xác minh install

Với một dự án `jar`:

1. Xác nhận lệnh `mvn install` kết thúc thành công.
2. Xác định local repository thực tế, xét cả `<localRepository>` và `-Dmaven.repo.local`.
3. Kiểm tra thư mục `groupId/artifactId/version` chứa JAR/POM tương ứng.
4. Thử dự án tiêu thụ khác trên cùng máy dùng dependency đó.

Một cách cách ly kho lab với kho cá nhân (Bash/zsh):

```bash
mvn "-Dmaven.repo.local=$HOME/.m2/math-kit-lab" clean install
ls "$HOME/.m2/math-kit-lab/dev/example/math-kit/1.0.0-SNAPSHOT/"
```

Một kho local mới có thể tải lại thư viện và plugin nên cần mạng khi cache trống. Nếu build dùng kho riêng, việc chỉ kiểm tra `~/.m2/repository` mặc định có thể dẫn tới kết luận sai.

### Xác minh deploy

1. Xác nhận lệnh xuất bản kết thúc thành công, không có lỗi trong giai đoạn upload.
2. Kiểm tra trong giao diện/API của repository manager được cấp rằng JAR, POM và metadata đúng version đã xuất hiện tại **remote repository đích**.
3. Từ một máy khác hoặc một môi trường có **local repository sạch** và cấu hình đọc phù hợp, thử phân giải dependency đó. Cách này tránh nhầm artifact chỉ tồn tại do `install` tại máy phát hành.
4. Ghi nhận version, commit mã nguồn, pipeline và nơi lưu artifact để truy vết.

Một dấu hiệu **không đủ** là thấy JAR trong `target/` hoặc `~/.m2/repository` sau `mvn deploy`; các bước `package` và `install` đã đi trước, nên không chứng minh bước upload từ xa thành công.

## 12. Chẩn đoán những lỗi hay gặp

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Có JAR ở `target/` nhưng dự án khác không tìm thấy | Mới chạy `package`, chưa `install` hoặc chưa publish | Xác định local repository và kiểm tra install |
| `install` thành công nhưng CI khác không thấy bản mới | CI ở máy/kho local khác | Publish vào remote repository rồi cấu hình client đọc |
| `deploy` báo thiếu đích | Chưa có `distributionManagement` hay thiết lập deploy thay thế | Xem effective POM và repository được cấp |
| `401 Unauthorized` | Sai ID server, thiếu credential hoặc token không hợp lệ | Đối chiếu IDs và settings đang được dùng |
| `403 Forbidden` | Quyền ghi bị từ chối hoặc chính sách repository không cho publish | Kiểm tra quyền và loại kho |
| SNAPSHOT bị kho releases từ chối | Chọn nhầm đích hoặc thiếu snapshot repository hợp lệ | Cấu hình `snapshotRepository` phù hợp |
| Publish release cùng version bị từ chối | Kho cấm ghi đè bản release | Dùng version release mới |
| Bản ở local repository đúng nhưng remote chưa có | `install` đã thành công, `deploy` lỗi mạng/quyền | Đọc log Deploy Plugin và xác minh trên máy chủ |
| Unit test thất bại trước deploy | Lifecycle dừng ở `test` hoặc `verify` | Sửa lỗi kiểm thử thay vì vô hiệu hóa |
| Máy khách vẫn thấy SNAPSHOT cũ | Metadata/cache/policy kiểm tra cập nhật | Kiểm tra repository, dùng `-U` nếu phù hợp |
| `clean` không xóa cache Maven | `clean` chỉ dọn đầu ra build | Không xóa kho local khi chưa rõ nguyên nhân |

Để xem POM sau khi kế thừa/cấu hình, dùng `mvn help:effective-pom`. Để xem settings hợp nhất, dùng `mvn help:effective-settings`. Tránh chia sẻ log debug hoặc effective settings đầy đủ nếu chúng chứa địa chỉ nội bộ hay thông tin nhạy cảm.

## 13. Câu hỏi và bài tập tự kiểm tra

1. Chạy `mvn clean package` cho `math-kit`. Hãy xác định JAR ở đâu và vì sao lệnh này **chưa đồng nghĩa** với install.
2. Chạy `mvn install`. Kiểm tra đường dẫn artifact theo tọa độ `dev.example:math-kit:1.0.0-SNAPSHOT`.
3. Một đồng nghiệp tải cùng Git repository nhưng không dùng được `math-kit` vừa install trên máy bạn. Giải thích vì sao và cần thêm bước nào để chia sẻ.
4. So sánh `<repositories>`, `<pluginRepositories>`, `<distributionManagement>`, `<mirrors>` và `<servers>` về mục đích, hướng dữ liệu và quyền truy cập.
5. Nếu POM dùng ID `team-snapshots` nhưng settings có server ID `team-snapshot`, dự đoán lỗi và sửa cấu hình bằng cách nào.
6. Khi `mvn deploy` đạt `BUILD SUCCESS`, bạn kiểm tra ở đâu để biết artifact thật sự đã có trên kho từ xa? Vì sao chỉ nhìn `~/.m2/repository` là chưa đủ?
7. Nếu một bản phát hành mới chỉ đổi mã nguồn mà giữ nguyên version release đã có trên remote, những rủi ro gì xảy ra? Bạn sẽ đặt version thế nào?
8. Vì sao `mvn deploy` không chứng minh dịch vụ đã chạy trên production? Hãy nêu bước bổ sung để một hệ thống runtime nhận và chạy artifact.

Bạn hiểu chủ đề khi có thể phân biệt chính xác **đầu ra build `target/`**, **artifact đã install vào local repository** và **artifact đã deploy lên remote repository**, đồng thời biết chọn phase, version và repository cho từng mục tiêu.

## 14. Tài liệu tham khảo

- [Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Maven — Introduction to Repositories](https://maven.apache.org/guides/introduction/introduction-to-repositories.html)
- [Maven Install Plugin](https://maven.apache.org/plugins/maven-install-plugin/)
- [Maven Deploy Plugin — Usage](https://maven.apache.org/plugins/maven-deploy-plugin/usage.html)
- [Maven — Settings Reference](https://maven.apache.org/settings.html)
- [Maven — Security and Deployment Settings](https://maven.apache.org/guides/mini/guide-deployment-security-settings.html)
