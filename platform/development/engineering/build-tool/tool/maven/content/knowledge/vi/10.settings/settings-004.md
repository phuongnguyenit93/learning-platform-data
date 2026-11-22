# Maven Settings: servers và liên kết thông tin xác thực qua ID

## 1. Vì sao Maven cần `<servers>`?

Một dự án Maven thường tải dependency và plugin từ **remote repository**, hoặc xuất bản artifact lên repository dùng chung. Một số repository là công khai, số khác cần tài khoản hoặc token.

Thông tin về **địa chỉ repository** và thông tin **đăng nhập** có vai trò khác nhau:

- `pom.xml` có thể khai báo **repository ID, URL và chính sách** dùng để tải artifact, hoặc `distributionManagement` mô tả nơi phát hành artifact.
- `settings.xml` chứa **cấu hình của môi trường/người dùng**, trong đó có `<servers>` với các thông tin xác thực riêng cho những repository cần đăng nhập.
- Maven chọn cấu hình `<server>` bằng cách so khớp **`<id>`** với ID repository hoặc mirror mà Maven thực sự sử dụng.

Đây là cơ chế cơ bản: **repository ID là khóa liên kết logic, còn URL là địa chỉ kết nối**.

Ví dụ, trong POM có repository để deploy mang ID `team-releases`, và trong `settings.xml` có `<server><id>team-releases</id>...`. Maven có cơ sở liên kết credential tương ứng khi gửi artifact tới repository đó.

Không đặt mật khẩu hoặc token trực tiếp trong `pom.xml` được commit vào Git. POM phải có khả năng chia sẻ cho người khác mà không vô tình phân phát bí mật. Cấu hình `settings.xml` chứa thông tin nhạy cảm cần được phân quyền và quản lý theo môi trường.

## 2. `settings.xml` nằm ở đâu và được dùng khi nào?

Hai vị trí thường gặp:

| Loại settings | Vị trí thông dụng | Phạm vi |
| --- | --- | --- |
| User settings | `~/.m2/settings.xml` trên Unix-like; thường là `%USERPROFILE%\.m2\settings.xml` trên Windows | Dành riêng cho tài khoản chạy Maven |
| Global settings | `${maven.home}/conf/settings.xml` trong nơi cài Maven | Thiết lập chung của bản cài Maven |

Maven hợp nhất cấu hình global và user khi sử dụng; các thiết lập ở user settings được ưu tiên trong quá trình hợp nhất tương ứng. Khi dùng Maven Wrapper, bản Maven được Wrapper chọn cũng đọc các settings theo quy tắc Maven, trừ khi lệnh chỉ định tệp thay thế.

Muốn chủ động chỉ định tệp user settings cho một lần chạy, dùng `-s` hoặc `--settings`:

~~~bash
mvn -B -ntp -s path/to/settings.xml clean verify
~~~

Trên Windows, thay `path/to/settings.xml` bằng đường dẫn hợp lệ, có thể đặt trong dấu nháy kép nếu chứa khoảng trắng. Tùy chọn `-gs` hoặc `--global-settings` chỉ định global settings riêng khi thực sự cần. **Tệp settings dùng trong CI nên được cấp từ secret store hoặc được tạo trong không gian làm việc an toàn**, không đặt một bản chứa bí mật trong repository nguồn.

Kiểm tra Maven/JDK đang dùng:

~~~bash
mvn -version
~~~

Hành vi liên quan mã hóa credential và các quy tắc an toàn bổ sung phụ thuộc phiên bản Maven; kiểm tra phiên bản thực tế trước khi áp dụng hướng dẫn mã hóa.

## 3. Các phần tử chính của `<servers>`

Mỗi `<server>` là một bản ghi thông tin kết nối và xác thực được định danh bằng `<id>`.

| Phần tử | Ý nghĩa | Khi nào cần |
| --- | --- | --- |
| `<id>` | Khóa để Maven tìm bản ghi server tương ứng với repository/mirror | Thiết yếu khi muốn Maven ghép đúng credential |
| `<username>` | Tên tài khoản đăng nhập | Repository yêu cầu username và password/token |
| `<password>` | Password, access token hoặc giá trị đã mã hóa theo cơ chế Maven đang dùng | Tùy phương thức xác thực của repository |
| `<privateKey>` | Đường dẫn tới khóa riêng cho transport SSH phù hợp | Khi transport dùng SSH public-key authentication |
| `<passphrase>` | Passphrase bảo vệ private key | Nếu private key có passphrase |
| `<filePermissions>`, `<directoryPermissions>` | Quyền file/thư mục khi transport có hỗ trợ thao tác tạo file | Một số phương thức upload qua filesystem/SCP; không phải tùy chọn HTTP phổ thông |
| `<configuration>` | Cấu hình bổ sung do transport/plugin hỗ trợ | Chỉ khi tài liệu của transport yêu cầu |

`id` **không phải tên người dùng**. Ví dụ `team-releases` là ID logic, còn `ci-publisher` mới là tên đăng nhập. Maven không tự suy ra tài khoản chỉ từ chuỗi URL hoặc artifactId.

Maven có thể dùng cùng một kiểu server entry để xác thực **tải xuống** và **upload**; khác nhau chủ yếu là nơi repository được khai báo và thao tác đang thực hiện. Việc một server được khai báo không tự động bật repository hay cho phép upload: repository phải được cấu hình, reachable và tài khoản phải có quyền.

**Lưu ý:** Nếu dùng xác thực bằng private key, không điền đồng thời password theo cách khiến transport ưu tiên password và bỏ qua key. Chi tiết còn tùy loại transport; với HTTPS repository manager phổ biến, cấu hình username/token thường là đường dễ hiểu hơn.

## 4. Nguyên tắc ghép ID: điều quan trọng nhất

Một cặp khai báo cơ bản:

**Trong `pom.xml`** — một phần của `<project>`:

~~~xml
<distributionManagement>
    <repository>
        <id>team-releases</id>
        <url>https://repo.example.org/repository/releases</url>
    </repository>
</distributionManagement>
~~~

**Trong `settings.xml`** — một phần của `<settings>`:

~~~xml
<servers>
    <server>
        <id>team-releases</id>
        <username>${env.MAVEN_REPO_USER}</username>
        <password>${env.MAVEN_REPO_TOKEN}</password>
    </server>
</servers>
~~~

Ở hai đoạn trên, hai ID cùng là `team-releases`. Các biến môi trường `MAVEN_REPO_USER` và `MAVEN_REPO_TOKEN` chỉ là tên biến ví dụ; chúng phải được cấp giá trị thực bởi môi trường đáng tin cậy. **Không dùng token thật trong bài hướng dẫn, POM, ảnh chụp hoặc log công khai**.

Ví dụ sai:

~~~xml
<!-- settings.xml: ID KHÔNG khớp POM -->
<server>
    <id>release-storage</id>
    <username>${env.MAVEN_REPO_USER}</username>
    <password>${env.MAVEN_REPO_TOKEN}</password>
</server>
~~~

Nếu POM chỉ định ID `team-releases` nhưng settings lại dùng `release-storage`, Maven không lấy entry đó chỉ vì hai URL có vẻ thuộc cùng công ty. Kết quả có thể là lỗi xác thực hoặc Maven không gửi credential. URL hợp lệ, token đúng và quyền repository đầy đủ vẫn không thay thế được việc **ID phải khớp**.

Cần phân biệt các trường:

~~~text
groupId / artifactId / version   → tọa độ của artifact
repository URL                  → địa chỉ máy chủ/đường dẫn repository
repository/mirror id            → khóa liên kết với <servers><server><id>
username/token                  → danh tính và bí mật xác thực
~~~

ID không có nhiệm vụ mã hóa mật khẩu. **Chỉ ghép ID không bảo đảm truy cập thành công**: host, quyền, chính sách repository, TLS, proxy, token và giới hạn phạm vi credential của Maven hiện đại cũng phải phù hợp.

## 5. Ví dụ hoàn chỉnh: ứng dụng Java 17 được phát hành vào repository

Ta dựng một dự án JAR tối giản, sau đó cấu hình nơi phát hành và server credentials **tách biệt**.

Cấu trúc:

~~~text
publish-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── example/
                └── Hello.java
~~~

Tệp `pom.xml` đầy đủ:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>publish-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
        </plugins>
    </build>

    <distributionManagement>
        <repository>
            <id>team-releases</id>
            <url>https://repo.example.org/repository/releases</url>
        </repository>
        <snapshotRepository>
            <id>team-snapshots</id>
            <url>https://repo.example.org/repository/snapshots</url>
        </snapshotRepository>
    </distributionManagement>
</project>
~~~

Địa chỉ `https://repo.example.org/...` là **URL ví dụ, không phải repository Maven đang hoạt động**. Thay bằng URL repository do tổ chức cấp khi triển khai thật. POM được phép mô tả nơi phát hành nhưng **không chứa username hoặc password**.

Tệp `src/main/java/example/Hello.java`:

~~~java
package example;

public final class Hello {
    private Hello() {
    }

    public static void main(String[] args) {
        System.out.println("Hello Maven settings");
    }
}
~~~

Lệnh build chạy từ thư mục `publish-demo`:

~~~bash
mvn -B -ntp clean package
java -cp target/classes example.Hello
~~~

Khi JDK 17+ và Maven được cài đúng, `mvn clean package` tạo `target/publish-demo-1.0.0.jar`; lệnh Java riêng in **chính xác**:

~~~text
Hello Maven settings
~~~

Lệnh `java` không cần credential vì nó chỉ đọc class đã biên dịch trên máy. `mvn package` có thể cần truy cập repository để tải plugin/dependency lần đầu, nhưng không dùng `distributionManagement` để upload artifact.

### 5.1. User settings chứa credential cho hai đích phát hành

Ví dụ tệp user `~/.m2/settings.xml`:

~~~xml
<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0"
          xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
          xsi:schemaLocation="http://maven.apache.org/SETTINGS/1.2.0 https://maven.apache.org/xsd/settings-1.2.0.xsd">
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
</settings>
~~~

Maven có hỗ trợ nội suy `${env.NAME}` trong `settings.xml` để lấy biến môi trường của tiến trình Maven. Trong ví dụ, cả hai endpoint sử dụng cùng tài khoản/token **chỉ để minh họa**; thực tế nên dùng hai credential khác nhau nếu chính sách yêu cầu quyền tách biệt. Có thể để cấu hình settings quản lý tập trung ở CI thay vì buộc lập trình viên đặt token vào file.

- Khi version là `1.0.0` (release), Maven Deploy Plugin dùng `<distributionManagement><repository>`: ID `team-releases`.
- Nếu đổi version thành `1.0.1-SNAPSHOT`, Maven thường dùng `<snapshotRepository>`: ID `team-snapshots`.
- Hai repository URL này có thể nằm trên cùng hostname, nhưng **hai ID vẫn khác nhau** để ánh xạ và phân tách quyền. Maven chọn repository theo loại version; không nhìn tên server rồi tự quyết định release hay snapshot.
- Artifact có thể không được phép upload nếu server từ chối redeploy release đã tồn tại hoặc token chỉ có quyền đọc. Việc khớp ID không vượt qua policy của repository manager.

### 5.2. Build và xuất bản là hai bước khác nhau

Sau khi mọi test/quality gate bắt buộc đạt, lệnh phát hành theo Maven lifecycle là:

~~~bash
mvn -B -ntp deploy
~~~

Lệnh `deploy` chạy những pha trước nó rồi dùng `distributionManagement` và server entry tương ứng để upload artifact/POM. Với URL ví dụ `repo.example.org`, **lệnh deploy không thể phát hành thành công cho tới khi thay URL bằng repository thật và cung cấp credential hợp lệ**. Không nên thử một lệnh upload trên hạ tầng không được cấp quyền.

Cũng cần phân biệt `mvn install` đưa artifact vào `~/.m2/repository` trên máy, **không cần server credential để cài artifact cục bộ**. `mvn deploy` cần remote repository được cấu hình và có thể cần xác thực. Deploy tới artifact repository **không đồng nghĩa** khởi chạy ứng dụng trên Tomcat, Kubernetes hoặc production.

## 6. Dùng `<servers>` để tải dependency từ repository riêng

`<servers>` không chỉ dành cho deploy. Một dự án có thể cần tải dependency hoặc plugin từ repository nội bộ yêu cầu đăng nhập.

Ví dụ đoạn nằm trong `<project>` của POM:

~~~xml
<repositories>
    <repository>
        <id>team-dependencies</id>
        <url>https://repo.example.org/repository/internal</url>
    </repository>
</repositories>
~~~

User settings tương ứng:

~~~xml
<servers>
    <server>
        <id>team-dependencies</id>
        <username>${env.MAVEN_READ_USER}</username>
        <password>${env.MAVEN_READ_TOKEN}</password>
    </server>
</servers>
~~~

Trong ví dụ này, repository ID để tải dependency là `team-dependencies` chứ **không phải** `team-releases`. Maven chọn ID của repository đang được kết nối. Với plugin được lấy từ repository riêng, còn có phần `<pluginRepositories><pluginRepository>...</pluginRepository></pluginRepositories>` sử dụng cơ chế ID tương tự.

**Không bắt buộc mỗi URL phải có credential.** Maven Central và những repository public có thể không cần username/password; đừng tạo server entry vô ích hoặc gửi credential tới endpoint không tin cậy. Cũng không nhầm Maven local repository `~/.m2/repository` với remote repository: local repository là cache/kho artifact trên máy, không phải endpoint HTTP cần `<server>`.

Trong dự án team, có thể cấu hình repository qua profile trong `settings.xml` thay vì hardcode các endpoint nội bộ vào POM. Dù repository được định nghĩa ở đâu, ID và quy tắc xác thực của kết nối thực tế vẫn cần đúng.

## 7. Khi có mirror: credential phải khớp ID của mirror

Mirror là điểm dễ nhầm nhất. Maven có thể chuyển một repository sang URL mirror theo quy tắc `<mirrorOf>`. Khi đó **repository mà Maven thực sự kết nối** là mirror, và server credential thường được tra bằng **ID của mirror**, không phải ID repository gốc.

Ví dụ settings có mirror của Maven Central:

~~~xml
<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0">
    <mirrors>
        <mirror>
            <id>team-mirror</id>
            <mirrorOf>central</mirrorOf>
            <url>https://repo.example.org/repository/maven-proxy</url>
        </mirror>
    </mirrors>

    <servers>
        <server>
            <id>team-mirror</id>
            <username>${env.MAVEN_READ_USER}</username>
            <password>${env.MAVEN_READ_TOKEN}</password>
        </server>
    </servers>
</settings>
~~~

Ý nghĩa:

- `<mirrorOf>central</mirrorOf>`: quy tắc nói rằng mirror được dùng thay cho repository ID `central`.
- `<mirror><id>team-mirror</id>`: định danh của endpoint mirror.
- `<server><id>team-mirror</id>`: credential tương ứng **để đăng nhập vào mirror**.

Nếu server chỉ có ID `central`, nhưng yêu cầu thực tế đi qua `team-mirror`, credential của `central` không tự được dùng cho mirror. `mirrorOf` là **quy tắc chọn repository được thay thế**, không phải ID để tra password.

Mirror ở ví dụ có URL giả. Với repository manager thực, cần đảm bảo URL mirror thực sự phục vụ các artifact cần thiết; một mirror không hoạt động có thể khiến cả dependency công khai không resolve được.

### Bảng ghi nhớ ba tình huống

| Mục tiêu | ID của nơi Maven kết nối | ID của `<server>` cần ghép |
| --- | --- | --- |
| Upload release | `distributionManagement.repository.id = team-releases` | `team-releases` |
| Upload snapshot | `distributionManagement.snapshotRepository.id = team-snapshots` | `team-snapshots` |
| Tải dependency qua mirror | `mirrors.mirror.id = team-mirror` | `team-mirror` |
| Tải từ repository riêng không bị mirror thay thế | `repositories.repository.id = team-dependencies` | `team-dependencies` |

**Không lấy URL làm khóa tra credential.** Hai repository khác ID có thể dùng chung hostname; hai ID giống nhau nhưng nhắm tới host khác là một cấu hình cần kiểm tra cẩn thận về bảo mật.

## 8. Giới hạn phạm vi credential theo origin trong Maven mới

Lịch sử Maven chủ yếu liên kết server credential theo **repository ID**. Cơ chế này có rủi ro: một POM bên ngoài có thể khai báo repository trùng ID với một server nhạy cảm nhưng trỏ tới hostname khác, dẫn đến nguy cơ sử dụng credential không đúng nơi.

Theo Settings Reference hiện hành, **từ Maven 3.10.0 và Maven 4.0.0**, thông tin xác thực của server được ràng buộc thêm theo **origin** (scheme, host, port) của những repository/mirror được Maven biết khi khởi tạo. Cơ chế này hạn chế khả năng credential bị gửi tới origin khác chỉ vì ID trùng.

Hệ quả thực hành:

1. **ID vẫn cần đúng**, nhưng ID đúng **chưa đủ** nếu origin của URL không nằm trong phạm vi được Maven chấp thuận.
2. Maven có thể chỉ biết repository/mirror được khai báo trong settings ở lúc khởi tạo; một repository chỉ xuất hiện sau đó từ POM hoặc profile chưa kích hoạt có thể cần xử lý thêm.
3. Các cấu hình Maven mới có thể đưa ra cảnh báo hoặc, với chế độ `maven.repository.credentialScope=strict`, không sử dụng credential ngoài origin hợp lệ.
4. `repositoryOrigins` trong server settings có thể dùng để khai báo bổ sung origin đã được tổ chức cho phép, **không phải danh sách URL bất kỳ để vượt qua bảo vệ**.

Một ví dụ **chỉ dành cho phiên bản hỗ trợ thuộc tính này**, nằm trong `<server>` khi có lý do rõ ràng:

~~~xml
<server>
    <id>team-releases</id>
    <username>${env.MAVEN_REPO_USER}</username>
    <password>${env.MAVEN_REPO_TOKEN}</password>
    <repositoryOrigins>
        <repositoryOrigin>https://repo.example.org</repositoryOrigin>
    </repositoryOrigins>
</server>
~~~

`repositoryOrigin` là **origin**, không phải đường dẫn đầy đủ như `/repository/releases`. Chỉ khai báo hostname đáng tin cậy do đội hạ tầng quản lý; tránh mở rộng phạm vi credential một cách mù quáng. Nếu build dùng Maven 3.x cũ hơn, cần xem tài liệu chính xác của phiên bản đó; không sao chép cấu trúc mới sang phiên bản không hỗ trợ rồi giả định nó sẽ được thực thi.

**Với người mới học:** ưu tiên ghi nhớ cơ chế ghép ID, sau đó kiểm tra URL/host và version Maven khi debug xác thực. Tính năng origin scope là lớp bảo vệ bổ sung, không phải lý do để bỏ việc quản lý token/permission.

## 9. Không nhầm `<servers>`, `<mirrors>`, `<proxies>` và `<repositories>`

Những cấu hình này thường xuất hiện gần nhau nhưng **không thay thế cho nhau**:

| Cấu hình | Trả lời câu hỏi | Ví dụ |
| --- | --- | --- |
| POM `<repositories>` | Tải dependency từ repository nào? | `team-dependencies` và URL |
| POM `<pluginRepositories>` | Tải Maven plugin từ đâu? | Repository plugin riêng |
| POM `<distributionManagement>` | Phát hành artifact tới đâu? | `team-releases`, `team-snapshots` |
| settings `<mirrors>` | Repo nào được thay bằng mirror endpoint nào? | `central → team-mirror` |
| settings `<servers>` | Dùng credential/config transport nào cho ID đang kết nối? | `team-mirror → user/token` |
| settings `<proxies>` | Kết nối outbound cần đi qua proxy nào? | Proxy host/port và credential proxy riêng |

Proxy credential thường nằm trong phần `<proxies><proxy>` của settings, không được tự ghép bằng `<servers><server><id>` của repository. Khi chẩn đoán lỗi mạng, cần phân biệt **HTTP 407 Proxy Authentication Required** với **HTTP 401** do repository yêu cầu đăng nhập.

Nếu Maven sử dụng nhiều mirror, nên kiểm tra ID nào đã được chọn từ các quy tắc `mirrorOf`. Một server entry đúng cho repository gốc có thể không được sử dụng khi request thực tế đã bị chuyển qua mirror. Với một repository manager tích hợp proxy và hosted repository, đội hạ tầng có thể cung cấp một ID và URL riêng cho từng vai trò.

## 10. Xem settings hiệu lực mà không làm lộ secret

Trước khi kết luận Maven đã đọc đúng `settings.xml`, hãy kiểm tra lệnh chạy và settings được chỉ định.

Maven Help Plugin có goal:

~~~bash
mvn help:effective-settings
~~~

Nó hiển thị cấu hình settings sau khi hợp nhất để hỗ trợ chẩn đoán. Có thể chỉ định file output trong môi trường riêng:

~~~bash
mvn help:effective-settings -Doutput=effective-settings.xml
~~~

Help Plugin có tham số `showPasswords` mặc định là `false` trong các phiên bản tài liệu liên quan; **điều này không có nghĩa toàn bộ output an toàn để công khai**. File có thể chứa URL nội bộ, tên user, path, profile và metadata cần bảo vệ. Không bật `showPasswords=true` để chụp minh chứng.

Nếu có custom settings, hãy dùng cùng `-s` khi kiểm tra:

~~~bash
mvn -s path/to/settings.xml help:effective-settings
~~~

Để hiểu hoạt động kết nối, có thể bật `-e` cho exception hoặc `-X` cho debug trong môi trường được kiểm soát, nhưng **log debug có thể tiết lộ endpoint, path, cấu hình hoặc secret do plugin in ra**. Rà soát và ẩn dữ liệu trước khi gửi issue hoặc nhờ người khác hỗ trợ.

Một quy trình kiểm tra an toàn:

1. Xác nhận `mvn -version` và file settings thực sự được dùng.
2. So sánh ID trong `distributionManagement`, `repositories` hoặc `mirrors` với `servers.server.id` tương ứng.
3. Kiểm tra biến môi trường được CI/terminal cung cấp **mà không in giá trị bí mật**.
4. Kiểm tra origin/host, TLS, proxy và quyền tài khoản đối với endpoint thật.
5. Chỉ dùng các lệnh có thể upload khi ở môi trường được cấp quyền. Với sự cố tải dependency, có thể thử một build/resolve thông thường rồi xem error code và repository ID.

## 11. Mật khẩu, token và mã hóa trong Maven 3 so với Maven 4

Maven hỗ trợ cơ chế lưu credential đã được mã hóa, nhưng **cách thiết lập khác giữa các thế hệ**:

- **Maven 3:** tài liệu Password Encryption mô tả việc tạo master password và mã hóa giá trị dùng cho `settings.xml`, liên quan file `settings-security.xml`. Cơ chế cũ có giới hạn bảo mật, nên không xem một chuỗi mã hóa trong file đã bị lộ là tương đương credential không thể bị lấy.
- **Maven 4:** có cơ chế mã hóa mới với công cụ `mvnenc`, hỗ trợ nhiều nguồn master key/dispatcher. Theo tài liệu chính thức, các thao tác thiết lập, kiểm tra và mã hóa có thể dùng `mvnenc init`, `mvnenc diag`, `mvnenc encrypt`. Cấu hình bảo mật Maven 4 thường nằm ở `settings-security4.xml`.
- **Cả hai:** phải bảo vệ file settings, nơi chứa key, tài khoản CI, quyền truy cập hệ thống và nhật ký. Mã hóa/obfuscation **không thay thế** phân quyền, secret rotation, TLS và nguyên tắc quyền tối thiểu.

Trong CI, thường nên đưa token từ secret manager vào tiến trình hoặc tạo settings tạm được phân quyền hợp lý rồi xóa theo chính sách runner, thay vì commit credentials vào repo. Nếu dùng token trong password field, repository manager có thể yêu cầu username cụ thể hoặc chấp nhận token như password; luôn theo hợp đồng xác thực do hệ thống repository quy định.

Tuyệt đối tránh cách thử nhanh như truyền `-Dpassword=...TOKEN...` trên dòng lệnh, vì shell history, danh sách tiến trình và log automation có thể ghi lại. Khi chia sẻ log hoặc cấu hình, phải ẩn token thật, kể cả dạng URL-encoded hoặc nằm trong header.

## 12. Các lỗi xác thực và cách chẩn đoán

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| `401 Unauthorized` khi tải/upload | Thiếu credential, server ID sai, token hết hạn hoặc không hợp lệ | Kiểm tra ID đang kết nối, giá trị biến môi trường có tồn tại, credential và repository auth scheme |
| `403 Forbidden` | Tài khoản được nhận diện nhưng thiếu quyền, hoặc policy/server từ chối | Kiểm tra quyền read/write/deploy, policy release/snapshot và tài khoản CI |
| `407 Proxy Authentication Required` | Proxy cần xác thực | Kiểm tra `<proxies>` thay vì chỉ đổi server ID |
| `Could not find artifact` hoặc HTTP 404 | Sai tọa độ/version, URL repository, policy, mirror hoặc artifact chưa publish | Xác minh repository đang được dùng và artifact có tồn tại |
| Deploy báo thiếu `distributionManagement` | POM chưa khai báo đích upload, hoặc lệnh không cấp đích phù hợp | Khai báo repository/snapshotRepository đúng theo quy trình phát hành |
| Maven thử endpoint khác dự kiến | `<mirrors>` hoặc profile/repository order | Kiểm tra mirror ID và quy tắc `mirrorOf` |
| ID settings đúng nhưng Maven mới từ chối credential | Origin chưa được phép hoặc chỉ biết repo từ POM được xử lý sau | Kiểm tra version Maven, repository origin scope và cấu hình cho phép chính xác |
| `PKIX path building failed` | TLS trust chain/certificate không được tin cậy | Kiểm tra chứng chỉ, Java truststore và hạ tầng TLS; không tắt xác minh TLS để né lỗi |
| Lỗi SSH authentication | Private key, passphrase, agent hoặc transport không phù hợp | Kiểm tra cơ chế SSH được plugin/transport hỗ trợ và quyền file khóa |
| Upload release bị chặn dù token đúng | Repository không cho ghi đè version đã phát hành hoặc chính sách staging | Kiểm tra version artifact và chính sách immutability, không tự cấp quyền quá rộng |
| `mvn package` OK nhưng `mvn deploy` FAIL | Package không cần upload; deploy cần đích và quyền ghi | Kiểm tra `distributionManagement`, ID, URL và quyền deploy |
| Tải dependency được nhưng deploy lỗi | Credential read khác credential write hoặc endpoint khác | Kiểm tra đúng ID và quyền cho thao tác cụ thể |

**Không suy ra nguyên nhân duy nhất chỉ từ mã HTTP.** Ví dụ một repository manager có thể trả 404 khi người dùng không có quyền xem artifact, nên cần kết hợp log, thông tin từ quản trị repository và quyền hiện hành.

Một vài quy tắc chẩn đoán:

- **Không thay đổi ID ngẫu nhiên trong nhiều file cùng lúc**. Trước hết xác định Maven đang nối tới repository/mirror nào rồi sửa một chỗ có chủ đích.
- **Không bật `-X` và gửi nguyên log lên nơi công khai**. Ghi lại tên goal, ID, mã HTTP, phần URL có thể công bố và thông điệp đã che.
- **Không tắt TLS verification** để “thử cho chạy” trong pipeline chính thức. Lỗi TLS là sự cố cấu hình/bảo mật cần xử lý đúng.
- **Không dùng credential có quyền admin** khi một token read-only hoặc deploy-only là đủ.

## 13. Quy trình thực hành: từ ID đến request

Với ví dụ trên, ta có thể kiểm tra theo chuỗi:

~~~text
POM: distributionManagement.repository.id = team-releases
                           |
                           v
Maven chạy pha deploy và chọn repository release
                           |
                           v
Endpoint https://repo.example.org/repository/releases
                           |
                           v
Tra server id = team-releases trong settings hiệu lực
                           |
                           v
Kiểm tra origin, loại transport và giá trị credential
                           |
                           v
Nếu hợp lệ, gửi request upload tới repository
                           |
                           v
Repository xác thực + kiểm tra quyền + policy
                           |
                           v
Thành công hoặc phản hồi lỗi có thể chẩn đoán
~~~

Nếu cùng dự án cần tải một dependency private khi build, đó là chuỗi **riêng** với repository ID/URL của dependency hoặc mirror. Nó có thể dùng credential read-only, trong khi deploy sử dụng credential write-only. Mục tiêu là tạo **phân tách quyền** và giảm tác động nếu một token bị lộ.

Trong CI đa môi trường:

1. Dùng một `settings.xml` template không chứa secret và lưu trữ quyền truy cập phù hợp.
2. Cung cấp user/token thông qua secret store theo **job và môi trường** được cấp quyền.
3. Khi cần publish, xác minh version/repository ID tương ứng với release hoặc snapshot; đảm bảo source/artifact đã vượt gate kiểm chứng.
4. Thực thi với settings được chọn tường minh bằng `-s` nếu CI dùng file riêng.
5. Thu thập thông tin không nhạy cảm (repository ID, build run ID, artifact coordinates, trạng thái) thay vì xuất toàn bộ settings hay request header.
6. Thu hồi/rotate secret khi có nghi ngờ lộ; áp dụng chính sách lưu trữ log/runner tạm thời phù hợp.

Các bước này vẫn không bảo đảm quyền deploy nếu repository manager chưa cấp quyền. **Maven chỉ gửi yêu cầu đúng cấu hình; hệ thống repository mới quyết định cho phép hay từ chối.**

## 14. Những nhầm lẫn phổ biến cần tránh

**Nhầm 1 — “Username là ID server.”** Sai. `id` là khóa nối Maven với repository/mirror; `username` là danh tính đăng nhập.

**Nhầm 2 — “URL giống nhau thì Maven tự tìm đúng password.”** Sai. Cơ chế liên kết dựa trên **ID**; Maven hiện đại còn có ràng buộc origin để bảo vệ credential.

**Nhầm 3 — “Khai báo `<servers>` là Maven biết repository để download.”** Sai. `<servers>` chứa credentials, còn repo/mirror phải được định nghĩa qua nơi thích hợp. Không có repository definition hợp lệ thì server entry một mình không tạo ra endpoint.

**Nhầm 4 — “`<mirrorOf>central</mirrorOf>` thì server ID phải là `central`.”** Sai khi Maven thực sự truy cập `team-mirror`; credentials phải khớp ID của mirror được chọn.

**Nhầm 5 — “POM có `distributionManagement` thì chạy `package` tự upload.”** Sai. Đóng gói và deploy là các pha khác nhau.

**Nhầm 6 — “Đã mã hóa mật khẩu thì có thể commit `settings.xml` và master key lên Git.”** Sai. Bảo vệ file, khóa và token vẫn bắt buộc.

**Nhầm 7 — “`mvn install` cần repository server password.”** Không đúng với thao tác cài artifact vào local repository. Nhưng các bước tải dependency/plugin **trước đó** có thể vẫn cần credential nếu nguồn tải là private.

**Nhầm 8 — “HTTP 403 cứ đổi password là sửa được.”** Không chắc. Có thể là thiếu quyền deploy hoặc policy không cho publish artifact/version đó.

## 15. Bài tập tự kiểm tra

1. POM khai báo `<repository><id>private-libs</id>...</repository>`. Settings có `<server><id>private-libs</id>`. **Maven chọn credential theo gì?** Theo repository ID `private-libs`, cùng các quy tắc an toàn/transport liên quan.
2. POM phát hành với ID `team-releases` nhưng settings chỉ có ID `team-dependencies`. **Điều gì sai?** ID không khớp với endpoint deploy, nên server entry đó không phải credential được tra cho deploy release.
3. Mirror có `id=team-mirror`, `mirrorOf=central`. **Server nào dùng để auth tới mirror?** Entry `<server><id>team-mirror</id>`.
4. Có thể commit token trong `pom.xml` rồi chỉ giới hạn quyền đọc Git không? **Không nên.** Token dễ bị lộ qua lịch sử, fork, log, backup và tăng nguy cơ phát tán.
5. `mvn package` thành công nhưng `mvn deploy` nhận HTTP 401. **Bước đầu kiểm tra gì?** ID của distributionManagement repository, ID của server, settings thực dùng, token/biến môi trường và endpoint thực tế.
6. Khai báo `<snapshotRepository><id>team-snapshots</id>`. Version `1.0.0-SNAPSHOT` sẽ dùng entry server ID nào? **`team-snapshots`** khi plugin deploy chọn snapshot repository.
7. `<repositoryOrigins>` có liên quan gì trong Maven mới? **Giới hạn origin** có thể nhận credential, không phải nơi chứa password hay URL artifact.
8. `settings.xml` có `<server><id>team-releases</id>` nhưng không có URL. Maven có tự biết nơi deploy không? **Không**; URL deploy đến từ distributionManagement hoặc cấu hình deploy phù hợp.
9. `mvn help:effective-settings` có an toàn để đăng công khai không? **Không mặc nhiên**; dù password có thể được ẩn, các dữ liệu khác vẫn có thể nhạy cảm.
10. Điểm khác nhau giữa `install` và `deploy` về xác thực là gì? **Install** chủ yếu ghi local artifact; **deploy** cần remote destination và quyền upload, nhưng cả hai vẫn có thể cần credential cho bước resolve dependency từ nguồn private.

## 16. Checklist cấu hình `<servers>` an toàn

- [ ] Đã xác định đúng mục đích: download dependency, download plugin hay upload artifact.
- [ ] Repository hoặc mirror đã được khai báo với URL đúng và ID rõ ràng.
- [ ] `servers.server.id` khớp **ID của endpoint Maven thực sự kết nối**, không phải tên username hay artifactId.
- [ ] Nếu dùng mirror, đã kiểm tra `mirrorOf` và ID của mirror.
- [ ] Nếu dùng Maven phiên bản có origin binding, credential được giới hạn đúng các origin đáng tin cậy.
- [ ] Username/token hoặc SSH key được cấp theo nguyên tắc quyền tối thiểu.
- [ ] Password/token không nằm trong `pom.xml`, commit Git, log, hình chụp hoặc lệnh shell công khai.
- [ ] CI cấp secret qua secret manager và quản lý vòng đời file settings tạm.
- [ ] `mvn -version` và user/global settings hoặc `-s` được xác nhận.
- [ ] Nếu dùng encryption, áp dụng đúng hướng dẫn Maven 3 hay Maven 4; không chia sẻ khóa giải mã.
- [ ] Bài build/verify đã đạt yêu cầu trước khi thao tác deploy.
- [ ] Khi gặp 401/403/407/TLS, tìm nguyên nhân theo đúng endpoint, quyền và tầng mạng.
- [ ] Sau publish, xác nhận artifact/POM truy xuất được theo đúng tọa độ, không chỉ thấy lệnh kết thúc.

## Tài liệu chính thức

- [Apache Maven — Settings Reference](https://maven.apache.org/settings.html): user/global settings, `servers`, `mirrors`, interpolation và origin binding.
- [Apache Maven — Security and Deployment Settings](https://maven.apache.org/guides/mini/guide-deployment-security-settings.html): ghép ID của `distributionManagement` với server credential.
- [Apache Maven — Deploying over HTTP, FTP and SSH](https://maven.apache.org/guides/mini/guide-deployment-transports.html): cấu hình endpoint upload và xác thực tùy transport.
- [Apache Maven — Password Encryption (Maven 3)](https://maven.apache.org/guides/mini/guide-encryption.html): mô hình master password và `settings-security.xml`.
- [Apache Maven — Password Encryption (Maven 4)](https://maven.apache.org/guides/mini/guide-encryption-4.html): `mvnenc` và các dispatcher/master key source.
- [Apache Maven Help Plugin — effective-settings](https://maven.apache.org/plugins/maven-help-plugin/effective-settings-mojo.html): xem settings hiệu lực, tham số ẩn password.

**Kết luận:** Maven không lưu thông tin đăng nhập trong POM để mỗi dự án tự mang theo mật khẩu. POM/settings xác định **repository hoặc mirror nào được dùng**, còn `<servers><server><id>` liên kết endpoint đó với cách xác thực phù hợp. **Khớp ID là bước đầu tiên; đúng origin, đúng quyền và bảo vệ secret là điều kiện bắt buộc để truy cập an toàn.**
