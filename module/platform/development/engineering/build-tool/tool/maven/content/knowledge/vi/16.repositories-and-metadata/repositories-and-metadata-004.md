# Maven repositories và pluginRepositories: hai mục đích khác nhau

## 1. Câu hỏi cốt lõi

Maven dùng **remote repository** để tải các artifact phục vụ quá trình build. Tuy nhiên, artifact có thể đóng hai vai trò khác nhau:

- **Dependency của project**: thư viện mà mã ứng dụng hoặc mã test sử dụng, chẳng hạn `org.apache.commons:commons-lang3` hay `org.junit.jupiter:junit-jupiter`.
- **Maven plugin**: công cụ thực thi các goal của Maven, chẳng hạn `maven-compiler-plugin`, `maven-surefire-plugin`, `maven-resources-plugin` hoặc plugin riêng của công ty.

Vì vậy, Maven có **hai nhóm khai báo repository** trong POM:

1. `<repositories><repository>...</repository></repositories>` — nơi Maven tìm **project dependencies**.
2. `<pluginRepositories><pluginRepository>...</pluginRepository></pluginRepositories>` — nơi Maven tìm **Maven plugins** và những artifact phục vụ việc thực thi plugin.

Đây không phải hai loại định dạng server bắt buộc khác nhau. Một Maven repository manager có thể lưu cả thư viện lẫn plugin trên **cùng URL**; khác biệt nằm ở **vai trò repository trong quá trình Maven resolution**, tức Maven quyết định hỏi danh sách nào khi đang tìm một artifact.

**Quy tắc cần nhớ:** Chỉ thêm `<repositories>` không bảo đảm Maven tìm được plugin riêng; chỉ thêm `<pluginRepositories>` không bảo đảm Maven tìm được thư viện ứng dụng riêng.

Maven Central là trường hợp đặc biệt dễ che giấu nhầm lẫn này: Super POM thông thường cung cấp cấu hình Central cho **cả dependencies lẫn plugins**. Vì vậy dự án chỉ dùng plugin và thư viện có trên Central thường build được dù không khai báo thủ công hai phần trên.

## 2. Bản đồ: một lần Maven build cần resolve những gì?

Giả sử chạy:

~~~bash
mvn clean verify
~~~

Một chuỗi hoạt động giản lược:

~~~text
                    Maven đọc mô hình build
                            |
                project POM / parent / settings
                            |
          +-----------------+-------------------+
          |                                     |
    Project dependencies                    Build plugins
          |                                     |
    <repositories>                       <pluginRepositories>
          |                                     |
    commons-lang3.jar                  maven-compiler-plugin.jar
    junit-jupiter.jar                  maven-surefire-plugin.jar
    POM transitive deps                 plugin descriptor/metadata
          |                                     |
          +-----------------+-------------------+
                            |
                Artifact được cache trong
                    Maven local repository
                            |
                Plugin chạy goal phù hợp
                            |
              compile / test / package / verify
~~~

Sơ đồ này không có nghĩa Maven tải tất cả từ mạng ở mọi build: nếu local cache đã có artifact phù hợp, Maven có thể dùng bản cục bộ theo chính sách kiểm tra update và nguồn repository đã được cấu hình.

Một **Maven plugin bản thân cũng là một artifact** có tọa độ `groupId:artifactId:version`, POM và thường là JAR. Điểm khác là Maven cần **plugin descriptor**, cấu hình goal và tập phụ thuộc của plugin để chạy nó trong plugin realm. Thư viện của ứng dụng và thư viện nội bộ của plugin không mặc nhiên nằm trên cùng Java classpath.

## 3. Bảng so sánh hai phần tử quan trọng nhất

| Câu hỏi | `repositories` | `pluginRepositories` |
| --- | --- | --- |
| Mục đích chính | Tìm dependency của project | Tìm Maven plugins phục vụ build/report |
| Phần tử con | `<repository>` | `<pluginRepository>` |
| Nơi đặt trong POM | `<project><repositories>` | `<project><pluginRepositories>` |
| Có thể ở settings profile? | Có | Có |
| Artifact ví dụ | Commons Lang, JUnit, JDBC driver | Compiler, Surefire, Checkstyle, plugin nội bộ |
| Có thể dùng cùng URL vật lý? | Có | Có |
| Cần ID riêng? | Mỗi entry có ID, dùng trong cấu hình/metadata và xác thực | Tương tự; ID tương ứng với repository hoặc mirror thực tế |
| Có release/snapshot policy? | Có | Có |
| Ảnh hưởng classpath mã ứng dụng? | Các dependency được chọn theo scope và graph | Plugin chạy trong realm riêng; không tự đưa JAR plugin vào app |
| Có dùng để upload artifact? | Không phải khai báo đích deploy | Không phải khai báo đích deploy |

**Quan trọng:** Đừng nhầm `<pluginRepositories>` với `<build><plugins>`.

- `<build><plugins>` khai báo **plugin nào sẽ được sử dụng** và cách cấu hình nó.
- `<pluginRepositories>` khai báo **Maven được phép tìm plugin ở những repository nào**.
- `<build><pluginManagement>` quản lý version/configuration của plugin khi phù hợp; nó không thay thế plugin repository.
- `<dependencies>` khai báo **thư viện project sử dụng**.
- `<dependencyManagement>` quản lý version/scope của project dependencies; nó không tự khai báo repository.

## 4. Cú pháp POM: repository cho dependencies

Đoạn sau đặt trực tiếp trong phần tử `<project>` của `pom.xml`:

~~~xml
<repositories>
    <repository>
        <id>company-libraries</id>
        <name>Company Libraries</name>
        <url>https://repo.example.org/repository/maven-libraries</url>
        <releases>
            <enabled>true</enabled>
        </releases>
        <snapshots>
            <enabled>false</enabled>
        </snapshots>
    </repository>
</repositories>
~~~

Ý nghĩa:

- `id=company-libraries`: định danh logic; có thể dùng để liên kết với credential trong `settings.xml` hoặc xác định nguồn trong log và cache metadata.
- `url`: địa chỉ repository; ở đây là **URL minh họa**, không phải server hoạt động.
- `releases.enabled=true`: cho phép dùng repository này cho release artifacts.
- `snapshots.enabled=false`: không tra snapshot artifacts tại repository này.

Một dependency trông như:

~~~xml
<dependencies>
    <dependency>
        <groupId>com.example.internal</groupId>
        <artifactId>business-client</artifactId>
        <version>1.2.0</version>
    </dependency>
</dependencies>
~~~

Maven chỉ tải được `com.example.internal:business-client:1.2.0` nếu artifact thật tồn tại tại một repository phù hợp, được phép truy cập và không bị mirror/chính sách khác ngăn cản. Đây là **tọa độ minh họa**; không giả định có trên Maven Central.

**Nếu POM chỉ có repository này trong `repositories`**, Maven không mặc nhiên dùng `company-libraries` như một plugin repository để tìm plugin riêng của tổ chức. Plugin vẫn được tìm theo danh sách plugin repositories hiệu lực.

## 5. Cú pháp POM: repository cho Maven plugins

Đoạn đặt ở cùng cấp với `<repositories>` trong `<project>`:

~~~xml
<pluginRepositories>
    <pluginRepository>
        <id>company-build-tools</id>
        <name>Company Maven Plugins</name>
        <url>https://repo.example.org/repository/maven-build-tools</url>
        <releases>
            <enabled>true</enabled>
        </releases>
        <snapshots>
            <enabled>false</enabled>
        </snapshots>
    </pluginRepository>
</pluginRepositories>
~~~

Maven dùng khai báo này khi cần resolve plugin phù hợp, chẳng hạn một plugin nội bộ được project sử dụng:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>com.example.build</groupId>
            <artifactId>quality-maven-plugin</artifactId>
            <version>1.4.0</version>
            <executions>
                <execution>
                    <id>run-quality-check</id>
                    <phase>verify</phase>
                    <goals>
                        <goal>audit</goal>
                    </goals>
                </execution>
            </executions>
        </plugin>
    </plugins>
</build>
~~~

Đây là **cấu hình minh họa cho một plugin giả định**: `com.example.build:quality-maven-plugin:1.4.0` và goal `audit` chỉ chạy khi tổ chức thật sự phát hành plugin có tọa độ và goal tương ứng. Không copy nguyên rồi kỳ vọng build thành công từ Maven Central.

Nếu plugin chỉ có trong `company-build-tools`, thêm URL ấy vào `<repositories>` **mà không khai báo plugin repository tương ứng** thường không giải quyết được lỗi tải chính plugin đó.

Ngược lại, nếu `business-client` chỉ nằm trong `company-libraries`, thêm riêng `<pluginRepositories>` trỏ tới một kho chứa plugin không khiến dependency ứng dụng tự được tìm thấy.

## 6. Cùng một server cho cả hai mục đích: có cần khai báo hai lần?

**Có, nếu muốn một remote repository cụ thể tham gia cả hai danh sách resolution và không có cơ chế khác như mirror/configuration tập trung đã làm việc đó.** Ví dụ cùng một Maven repository manager phục vụ cả thư viện và plugins:

~~~xml
<repositories>
    <repository>
        <id>team-maven</id>
        <url>https://repo.example.org/repository/maven-all</url>
    </repository>
</repositories>

<pluginRepositories>
    <pluginRepository>
        <id>team-maven</id>
        <url>https://repo.example.org/repository/maven-all</url>
    </pluginRepository>
</pluginRepositories>
~~~

Hai đoạn có **cùng URL và cùng ID nhưng thuộc hai loại danh sách khác nhau**. Điều đó có thể hợp lệ; đừng nhầm với việc khai báo hai repository trùng ID trong **cùng một** danh sách hiệu lực.

Vì sao lại trùng nội dung? Bởi vì đây là **hai nơi Maven tìm kiếm khác nhau**. Một kho vật lý có thể chứa mọi loại artifact, nhưng khi resolve project dependencies Maven tra danh sách repositories, còn khi resolve plugins Maven tra plugin repositories.

Trong doanh nghiệp, không nhất thiết nên lặp cấu hình này ở hàng trăm POM. Một **repository manager + mirror trong user/global settings** thường phù hợp để tập trung URL, quyền truy cập và cache. Phải kiểm tra hành vi mirror thực tế thay vì tuyên bố rằng mọi cấu hình `mirrorOf` đều tương đương mọi khai báo riêng lẻ.

## 7. Thực hành Java 17 chạy được: nhìn thấy cả hai loại artifact

Để minh họa mà không cần private repository có thật, ta tạo ứng dụng dùng **Commons Lang** làm dependency và **Compiler/Surefire/Exec Plugin** làm công cụ build. Các artifact này có trên Maven Central nên có thể chạy với Maven/JDK 17+, quyền truy cập mạng phù hợp.

### 7.1. Cấu trúc project

~~~text
repository-lab/
├── pom.xml
└── src/
    ├── main/
    │   └── java/example/App.java
    └── test/
        └── java/example/AppTest.java
~~~

Bản thực hành sử dụng Maven Central mặc định. **Không thêm URL `repo.example.org` vào POM này**, vì đó là URL giả và có thể khiến việc resolve thất bại hoặc chậm.

### 7.2. `pom.xml` đầy đủ

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>repository-lab</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-lang3</artifactId>
            <version>3.14.0</version>
        </dependency>

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
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.2.5</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>example.App</mainClass>
                    <classpathScope>runtime</classpathScope>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Phân tích các artifact cần tải:

- `commons-lang3`: dependency project scope `compile` mặc định; Maven tra project repositories.
- `junit-jupiter`: dependency project scope `test`; Maven cũng tra project repositories khi resolve test dependencies.
- `maven-compiler-plugin`, `maven-surefire-plugin`, `exec-maven-plugin`: **Maven plugins** được Maven tìm qua plugin repositories.
- Các dependency **của bản thân plugin** phục vụ việc plugin thực thi thuộc phần resolution của plugin realm, không đồng nhất với dependency runtime của app.

Để build tái lập, ví dụ đã ghim version các plugin quan trọng. Một phiên bản Maven khác có thể mang Super POM/lifecycle defaults khác; việc khai báo version tường minh giảm rủi ro do plugin version không được cố định.

### 7.3. `src/main/java/example/App.java`

~~~java
package example;

import org.apache.commons.lang3.StringUtils;

public final class App {
    private App() {
    }

    public static String title(String source) {
        return StringUtils.capitalize(StringUtils.trimToEmpty(source));
    }

    public static void main(String[] args) {
        System.out.println(title("  maven repositories  "));
    }
}
~~~

Mã chính dùng `StringUtils`, nên `commons-lang3` cần hiện diện ở compile classpath và runtime classpath của ứng dụng. Maven không “đưa plugin compiler vào mã” chỉ vì compiler plugin được tải để biên dịch.

### 7.4. `src/test/java/example/AppTest.java`

~~~java
package example;

import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

class AppTest {
    @Test
    void formatsTitle() {
        assertEquals("Maven repositories", App.title("  maven repositories  "));
    }

    @Test
    void handlesNull() {
        assertEquals("", App.title(null));
    }
}
~~~

Surefire Plugin chạy JUnit tests, còn dependency `junit-jupiter` cung cấp API/test engine cần thiết. **Plugin Surefire và thư viện JUnit có vai trò khác nhau**: `<build><plugins>` chọn công cụ thực thi; `<dependencies>` chọn thư viện mà test code dùng.

### 7.5. Build và chạy

Ở thư mục chứa POM:

~~~bash
mvn -B -ntp clean verify
mvn -B -ntp exec:java
~~~

Với các file như trên và Maven/JDK tương thích, Maven biên dịch mã Java 17, chạy hai bài test và build JAR. Lệnh thứ hai dùng Exec Plugin, được cấu hình `classpathScope=runtime`, để chạy app với Commons Lang trong classpath.

**Một dòng do `App.main` in ra:**

~~~text
Maven repositories
~~~

Đây là stdout của ứng dụng, không phải toàn bộ log của Maven. Maven còn in thông báo plugin và thông tin build. Không sử dụng `java -cp target/classes example.App` để chứng minh runtime Maven bị lỗi, bởi lệnh ấy **không thêm dependency Commons Lang** vào classpath thủ công.

### 7.6. Nhìn phần dependencies Maven chọn

Chạy:

~~~bash
mvn -B -ntp org.apache.maven.plugins:maven-dependency-plugin:3.11.0:tree
~~~

Đây là lệnh **gọi một Maven plugin**, nhưng nội dung nó phân tích là **project dependency graph**. Kết quả dự kiến có `commons-lang3`, `junit-jupiter` và các transitive test dependencies. Đừng ngạc nhiên khi những plugin như Compiler, Surefire hay Exec **không xuất hiện như project dependencies thông thường** trong cây này: chúng được khai báo/resolve như plugins.

Ngược lại, POM có các plugin ở `<build><plugins>`. Không vì chúng không xuất hiện trong cây dependency ứng dụng mà nghĩ Maven đã không tải hoặc thực thi chúng.

## 8. Tại sao Maven Central có sẵn dù POM không khai báo repository?

Maven hình thành **effective POM** từ project POM, parent POM, Super POM và các profile đang active. Super POM thường chứa khai báo Maven Central trong cả:

~~~xml
<repositories>
    <repository>
        <id>central</id>
        <!-- URL Central do Maven/Super POM cấu hình -->
    </repository>
</repositories>
~~~

và:

~~~xml
<pluginRepositories>
    <pluginRepository>
        <id>central</id>
        <!-- URL Central do Maven/Super POM cấu hình -->
    </pluginRepository>
</pluginRepositories>
~~~

Hai đoạn trên là **trích đoạn giải thích cấu trúc**, không phải khai báo copy trực tiếp vì comment được dùng thay URL. Maven Central có địa chỉ chính thức `https://repo.maven.apache.org/maven2`, nhưng URL hiệu lực có thể được điều chỉnh bởi cấu hình Maven, settings hoặc mirror.

Kiểm tra mô hình hiệu lực của project thực hành:

~~~bash
mvn -B -ntp help:effective-pom -Doutput=effective-pom.xml
~~~

Trong file kết quả, tìm cả `<repositories>` **và** `<pluginRepositories>`. Nếu có mirror của `central`, effective POM có thể vẫn hiển thị ID gốc, trong khi request thực tế đi tới mirror URL. Vì vậy effective POM cho biết **danh sách trong mô hình**, chưa phải chứng cứ cuối về endpoint mạng.

Maven Central có thể lưu cả dependency lẫn plugin, nhưng điều đó không xóa ranh giới hai loại repository trong Maven.

## 9. Settings profile: khai báo repository theo môi trường

Không phải URL nội bộ nào cũng nên commit vào từng POM. Các thông tin phụ thuộc môi trường có thể nằm trong `~/.m2/settings.xml` hoặc settings do CI cấp với `-s`.

Ví dụ **settings.xml** dùng profile chủ động:

~~~xml
<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0"
          xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
          xsi:schemaLocation="http://maven.apache.org/SETTINGS/1.2.0 https://maven.apache.org/xsd/settings-1.2.0.xsd">
    <profiles>
        <profile>
            <id>team-repositories</id>

            <repositories>
                <repository>
                    <id>team-libraries</id>
                    <url>https://repo.example.org/repository/libraries</url>
                    <releases>
                        <enabled>true</enabled>
                    </releases>
                    <snapshots>
                        <enabled>false</enabled>
                    </snapshots>
                </repository>
            </repositories>

            <pluginRepositories>
                <pluginRepository>
                    <id>team-build-plugins</id>
                    <url>https://repo.example.org/repository/plugins</url>
                    <releases>
                        <enabled>true</enabled>
                    </releases>
                    <snapshots>
                        <enabled>false</enabled>
                    </snapshots>
                </pluginRepository>
            </pluginRepositories>
        </profile>
    </profiles>

    <activeProfiles>
        <activeProfile>team-repositories</activeProfile>
    </activeProfiles>
</settings>
~~~

Các URL `repo.example.org` là ví dụ; cấu hình này **không dùng để chạy project thực hành cho tới khi thay URL bằng repository có thật**. Trong dự án nội bộ, profile này chỉ được sử dụng nếu thực sự active, ví dụ do `<activeProfiles>` hoặc activation khác.

Settings profile chỉ hỗ trợ một tập phần tử liên quan môi trường: `repositories`, `pluginRepositories`, `properties` và `activation`. Không nên chép nguyên `<build><plugins>` từ POM vào settings profile rồi cho rằng Maven chấp nhận.

**Phân biệt:**

- Cấu hình trong **POM** đi cùng source, thuận tiện để người nhận dự án biết các repository đặc thù.
- Cấu hình trong **settings.xml** do người dùng/CI quản lý, phù hợp với repository manager, mirror, network, credentials, chính sách của tổ chức.
- Một cấu hình repository trong settings có thể áp dụng cho nhiều dự án, nhưng nếu không có cùng settings ở CI thì build không nhất thiết tái lập.

Để chỉ định settings cho một lần chạy:

~~~bash
mvn -B -ntp -s path/to/settings.xml clean verify
~~~

Không đặt bản settings chứa token thật vào Git. Nếu muốn chia sẻ template, dùng biến môi trường và hướng dẫn cấp secret an toàn.

## 10. Mirroring: một URL thay cho nhiều repository

Trong doanh nghiệp, mirror thường là cơ chế được ưu tiên để bảo đảm các kết nối Maven đi qua repository manager tập trung, thay vì để mỗi POM tự chỉ định endpoint.

Ví dụ phần settings:

~~~xml
<mirrors>
    <mirror>
        <id>company-mirror</id>
        <mirrorOf>external:*</mirrorOf>
        <url>https://repo.example.org/repository/maven-group</url>
    </mirror>
</mirrors>
~~~

`external:*` áp dụng cho các repository không thuộc nhóm file/localhost theo cú pháp mirror Maven, vì vậy Maven có thể dùng mirror cho nhiều remote repositories cả khi chúng ban đầu được khai báo trong project POM.

Ý nghĩa:

1. Maven tạo danh sách repository/plugin repository hiệu lực.
2. Trước khi thực hiện remote request, Maven xét quy tắc mirror.
3. Nếu mirror được chọn, request đi qua URL và ID của **mirror**, không nhất thiết là URL của repository gốc.
4. Repository manager nhận request và có thể proxy/cache hoặc định tuyến tới hosted repositories tùy cấu hình của nó.

`<mirrorOf>*</mirrorOf>` dùng phạm vi rộng hơn, bao gồm cả những repository mà bạn có thể muốn giữ riêng cho integration test hoặc local file repositories. `external:*` thường phù hợp hơn khi mục tiêu là mirror remote external repositories, nhưng vẫn phải kiểm tra ngoại lệ và chính sách nội bộ. Ví dụ:

~~~xml
<mirrorOf>external:*,!special-integration-repo</mirrorOf>
~~~

ID `special-integration-repo` được loại khỏi nhóm mirror ở ví dụ. Cú pháp `mirrorOf` là biểu thức chọn repository **theo ID/quy tắc**, không phải đường dẫn URL.

**Điểm cần nắm:** Mirror có thể tác động đến **cả resolution của dependencies lẫn plugins** khi các repository tương ứng match. Điều này khác với việc chỉ khai báo một entry trong `<repositories>`.

### Một mirror không tự gộp nội dung của các repository

Maven không tự ghép nội dung từ nhiều remote repository chỉ vì chúng cùng trỏ về một `mirror`. Repository manager phía sau URL mirror phải được cấu hình để phục vụ những artifact cần thiết. Nếu mirror chứa libraries nhưng không chứa company plugins, việc bật mirror cho mọi remote repository có thể khiến plugin resolution thất bại.

Nên kiểm tra repository manager của công ty có proxy Maven Central và các hosted repositories phù hợp hay không; tránh “sửa” bằng cách thêm một kho HTTP không được kiểm soát vào POM.

## 11. Credential theo repository ID và mirror ID

Các URL repository có thể cần xác thực. Maven dùng phần `<servers>` trong settings để liên kết credential với ID của endpoint mà Maven thực sự chọn.

Ví dụ một phần trong `settings.xml`:

~~~xml
<servers>
    <server>
        <id>team-libraries</id>
        <username>${env.MAVEN_LIB_USER}</username>
        <password>${env.MAVEN_LIB_TOKEN}</password>
    </server>

    <server>
        <id>team-build-plugins</id>
        <username>${env.MAVEN_PLUGIN_USER}</username>
        <password>${env.MAVEN_PLUGIN_TOKEN}</password>
    </server>
</servers>
~~~

Đây là **mẫu cấu hình**; biến môi trường phải được CI hoặc người dùng cấp theo chính sách an toàn. Maven hỗ trợ interpolation từ `env.*` trong settings khi phù hợp. Nếu hai repository dùng cùng một credential cũng nên xem xét nguyên tắc quyền tối thiểu và không dùng token có quyền deploy khi chỉ cần quyền read.

Khi mirror `company-mirror` thay repository gốc, credential thường phải khớp **mirror ID**:

~~~xml
<servers>
    <server>
        <id>company-mirror</id>
        <username>${env.MAVEN_MIRROR_USER}</username>
        <password>${env.MAVEN_MIRROR_TOKEN}</password>
    </server>
</servers>
~~~

Nếu chỉ có server ID `central`, nhưng Maven thực sự kết nối `company-mirror`, không nên mong credential của `central` tự động được dùng. ID là cơ chế liên kết logic, còn URL là endpoint, **không tra secret chỉ theo hostname**.

**Lưu ý Maven mới:** các Maven phiên bản có ràng buộc credential theo origin (scheme, host, port) còn kiểm tra phạm vi host hợp lệ, không chỉ khớp ID. Khi dùng Maven 3.10+/4.0, hãy xem Settings Reference về `repositoryOrigins` và cách bật strict mode; đừng mở rộng origin tùy tiện để vượt qua lớp bảo vệ.

Không xuất giá trị token trong log, không commit settings chứa password/token, không dùng `-Dpassword=...secret...` nếu có nguy cơ lộ qua shell history hoặc process listing.

## 12. Metadata: vì sao Maven cần hơn một file JAR?

Maven repository lưu artifact và metadata để hỗ trợ resolution. Cấu trúc ví dụ:

~~~text
repository/
└── org/
    └── apache/
        └── commons/
            └── commons-lang3/
                ├── maven-metadata.xml
                └── 3.14.0/
                    ├── commons-lang3-3.14.0.pom
                    └── commons-lang3-3.14.0.jar
~~~

Sơ đồ chỉ minh họa layout; repository thực có thể chứa checksum/signature và nhiều version. Maven dùng **POM** của một artifact để tìm dependencies bắc cầu, không chỉ tải JAR rồi tự đoán những thư viện đi kèm.

`maven-metadata.xml` phục vụ những tác vụ cần metadata như khám phá version/snapshot, prefix plugin và chính sách update. Các file metadata có những mức khác nhau: theo groupId, theo artifactId hoặc theo version.

### 12.1. Plugin prefix mapping cần group-level metadata

Lệnh gọn:

~~~bash
mvn compiler:compile
~~~

dùng prefix `compiler` để tìm `org.apache.maven.plugins:maven-compiler-plugin`. Nếu gọi plugin tùy chỉnh chỉ bằng prefix, Maven có thể cần **plugin prefix metadata** trong repository, tên `maven-metadata.xml` tại đường dẫn groupId của plugin, để ánh xạ prefix → artifactId.

Ví dụ *cấu trúc minh họa*:

~~~xml
<metadata>
    <groupId>com.example.build</groupId>
    <plugins>
        <plugin>
            <name>Quality Plugin</name>
            <prefix>quality</prefix>
            <artifactId>quality-maven-plugin</artifactId>
        </plugin>
    </plugins>
</metadata>
~~~

Đây là metadata group-level dành cho plugin prefix discovery, **không phải POM của ứng dụng**. Maven sẽ dùng các plugin group mà nó tìm kiếm; `<pluginRepositories>` cung cấp remote repository cho plugin metadata/plugin artifact, còn `pluginGroups` trong settings cho Maven biết những **groupId** khác cần tìm prefix khi gọi dạng `mvn quality:audit`.

### 12.2. Nếu plugin prefix không được tìm thấy

Thông báo có thể gần dạng:

~~~text
No plugin found for prefix 'quality' in the current project
and in the plugin groups ...
~~~

Với plugin tùy chỉnh, có ba đường kiểm tra:

1. Plugin artifact và metadata prefix thực sự có trong plugin repository hiệu lực chưa?
2. GroupId plugin đã được Maven tìm kiếm chưa, hoặc plugin đã được khai báo trong POM chưa?
3. Có thể gọi **tọa độ đầy đủ** thay vì chỉ dùng prefix để phân biệt lỗi prefix lookup với lỗi artifact resolution không?

Dạng goal đầy đủ:

~~~bash
mvn com.example.build:quality-maven-plugin:1.4.0:audit
~~~

Lệnh là **minh họa** cho plugin giả định; nếu plugin/goal không tồn tại sẽ thất bại như dự kiến. Gọi đầy đủ groupId:artifactId:version:goal giúp không phụ thuộc bước tìm prefix theo metadata, **nhưng vẫn phải resolve được plugin artifact** từ plugin repositories và phải có goal tương ứng.

## 13. pluginGroups không phải pluginRepositories

Trong settings có thể khai báo:

~~~xml
<pluginGroups>
    <pluginGroup>com.example.build</pluginGroup>
</pluginGroups>
~~~

Điều này yêu cầu Maven xem groupId `com.example.build` khi tra prefix plugin. Nó **không thêm URL repository**, không tải plugin thay cho `<pluginRepositories>`, và không khiến project tự chạy goal.

Phân biệt ba nhiệm vụ:

| Thiết lập | Công việc |
| --- | --- |
| `pluginGroups` | Những groupId nào Maven có thể tìm khi bạn gọi goal bằng prefix |
| `pluginRepositories` | Maven tìm plugin artifact và metadata ở repository nào |
| `build.plugins` | Project sử dụng plugin nào, phiên bản/configuration/execution gì |

Có thể có plugin repository đúng nhưng vẫn nhận `No plugin found for prefix` vì groupId không nằm trong các group tìm kiếm hoặc metadata prefix không tồn tại. Ngược lại, `pluginGroups` đúng nhưng URL plugin repository sai thì vẫn không tải được artifact.

Đừng thay `pluginRepositories` bằng `pluginGroups` để chữa lỗi `PluginResolutionException`.

## 14. Plugin dependencies có thuộc repositories không?

Đây là điểm thường gây hiểu nhầm. Một Maven plugin có thể cần thư viện của **chính plugin** để chạy goal. Chẳng hạn Compiler Plugin, Surefire hoặc plugin nội bộ có thể có transitive dependencies riêng.

Tổng quát:

- Maven resolve plugin artifact từ **plugin repositories**.
- Maven resolve các **plugin dependencies** phục vụ plugin realm theo cơ chế plugin resolution, sử dụng nguồn repository phù hợp với plugin.
- Project dependencies được resolve từ **project repositories** theo scope, graph và chính sách của chúng.
- Một plugin goal có thể được thiết kế để chủ động resolve **project dependencies** — khi đó plugin có thể tương tác với danh sách project repositories để làm đúng chức năng. Điều này **không xóa** ranh giới plugin artifact resolution và project dependency resolution.

Ví dụ Maven Dependency Plugin là **plugin** nhưng goal `dependency:tree` của nó trình bày **project dependencies**. Việc một plugin phân tích/tải dependency của project không có nghĩa plugin artifact ban đầu được tải từ `<repositories>`.

Nếu log lỗi chỉ rõ **plugin dependency** không resolve được, hãy xem plugin artifact/POM, plugin repositories, quyền truy cập endpoint và vấn đề truyền dependency của plugin. Không sửa project dependency scope một cách mù quáng.

## 15. Release, Snapshot và chính sách truy cập repository

Cả hai loại repository entry đều hỗ trợ những chính sách phổ biến:

~~~xml
<releases>
    <enabled>true</enabled>
    <updatePolicy>daily</updatePolicy>
    <checksumPolicy>warn</checksumPolicy>
</releases>
<snapshots>
    <enabled>false</enabled>
</snapshots>
~~~

Ý nghĩa:

- `releases.enabled`: repository có được sử dụng cho release artifacts?
- `snapshots.enabled`: repository có được sử dụng cho SNAPSHOT artifacts?
- `updatePolicy`: Maven kiểm tra cập nhật theo `always`, `daily`, `interval:X` hoặc `never` theo quy tắc Maven.
- `checksumPolicy`: cách xử lý checksum thiếu hoặc không phù hợp; có thể là `fail`, `warn` hoặc `ignore`.

Nếu project dùng **snapshot dependency**, nhưng repository `<repositories>` không cho phép snapshot, dependency đó có thể không tải được. Nếu **Maven plugin** có version `1.4.0-SNAPSHOT`, phải kiểm tra chính sách snapshot của **plugin repositories**, không chỉ `repositories`.

Không vì “plugin có artifact type JAR” mà nghĩ snapshot của plugin tuân theo chính sách của project dependency repository. Kiểm tra đúng loại repository và đúng plugin version.

Cẩn trọng với `updatePolicy=never`: metadata có thể thay đổi theo thời gian, nhất là snapshot. `mvn -U` thường được dùng để yêu cầu Maven kiểm tra lại các bản snapshot/negative cache theo cơ chế hỗ trợ, nhưng nó **không sửa URL sai, credential sai, mirror sai hoặc dependency không tồn tại**.

## 16. Local repository là cache dùng chung, không phải hai thư mục mặc định tách biệt

Local repository của Maven thường nằm ở `~/.m2/repository`. Cả project dependency JAR và plugin JAR thường được cache dưới cấu trúc tọa độ GAV ở đó.

Ví dụ:

~~~text
~/.m2/repository/
├── org/apache/commons/commons-lang3/3.14.0/
├── org/junit/jupiter/junit-jupiter/5.11.4/
├── org/apache/maven/plugins/maven-compiler-plugin/3.13.0/
└── org/codehaus/mojo/exec-maven-plugin/3.5.0/
~~~

Đây là **một local repository logic** mặc định, không phải `~/.m2/dependencies` và `~/.m2/plugins`. Hai danh sách remote repository cho Maven biết **nơi có thể tải những loại artifact đó** khi cần; sau khi resolve, chúng vẫn dùng hệ thống cache/repository metadata ở máy.

Do cache, bạn có thể thấy một plugin chạy thành công trên laptop dù cấu hình plugin repository thiếu, vì artifact đã được tải từ trước. Trên CI sạch hoặc `mvn -o`, tình trạng khác ngay. Khi debug “chỉ một máy bị lỗi”, cần ghi nhận local repository, version plugin và settings nhưng **không xóa toàn bộ cache không cần thiết**.

## 17. Cách chẩn đoán: dependency tải được nhưng plugin thất bại

Tình huống: project lấy được `business-client`, nhưng `mvn verify` dừng ở goal một plugin riêng.

Thông điệp thường có dạng:

~~~text
Plugin com.example.build:quality-maven-plugin:1.4.0
or one of its dependencies could not be resolved
~~~

Các bước:

1. **Đọc chính xác tọa độ plugin** trong error: groupId, artifactId, version.
2. Xem `<build><plugins>`/`<pluginManagement>` và `help:effective-pom`: plugin thật được khai báo và version đúng chưa?
3. Kiểm tra `<pluginRepositories>` hiệu lực (POM, parent, settings profile và Super POM), không chỉ `<repositories>`.
4. Nếu có mirror, xem ID/URL mirror mà Maven dùng thực tế.
5. Nếu cần đăng nhập, kiểm tra `servers.server.id` so với repository/mirror ID; không in password.
6. Kiểm tra plugin artifact tồn tại tại repository thật và có loại packaging/descriptor hợp lệ.
7. Nếu plugin artifact có nhưng **plugin dependency** thiếu, đọc cause chain và repository manager/log tương ứng.
8. Chạy lại sau khi chỉnh đúng URL/permission/version, không thử nhiều repository không tin cậy cho đến khi “tình cờ tải được”.

Đừng đổi tất cả dependency scopes hoặc nâng JDK khi lỗi xảy ra **trước bước compile** do Maven chưa tải được Compiler Plugin. Lỗi plugin resolution là vấn đề build tooling, không nhất thiết là code Java.

## 18. Cách chẩn đoán: plugin chạy được nhưng dependency ứng dụng không tải được

Tình huống: `maven-compiler-plugin` đã được tải, nhưng build báo:

~~~text
Could not resolve dependencies for project ...
Could not find artifact com.example.internal:business-client:jar:1.2.0
~~~

Các bước:

1. Xác định **tọa độ dependency** và version trong `<dependencies>`.
2. Dùng `help:effective-pom` xác minh project dependency, dependency management và repositories sau kế thừa/profile.
3. Kiểm tra `<repositories>` hiệu lực và policy release/snapshot.
4. Kiểm tra mirror và server credential phù hợp, bao gồm host/origin khi Maven phiên bản hỗ trợ ràng buộc.
5. Kiểm tra chính artifact/POM thực sự đã được publish trong repository manager chưa.
6. Nếu artifact **tồn tại nhưng version khác**, sửa version hoặc publish đúng artifact theo quy trình, không gõ URL tùy ý.
7. Nếu 401/403, phân biệt thiếu xác thực với thiếu quyền; nếu TLS lỗi, xử lý certificate/truststore đúng thay vì tắt xác minh.
8. Nếu plugin vẫn chạy thành công, đừng lấy đó làm bằng chứng `repositories` đã đúng. Central/plugin repository có thể đang hoạt động riêng.

Lỗi `Could not find artifact` cũng có thể đến từ metadata, negative cache, mirror chỉ chứa một phần hoặc POM dependency tham chiếu artifact không còn sẵn. Đọc message đầy đủ trước khi kết luận.

## 19. Cách chẩn đoán: lệnh plugin prefix không được nhận ra

Ví dụ:

~~~bash
mvn quality:audit
~~~

Nếu Maven báo `No plugin found for prefix 'quality'`, có thể do:

- Plugin chưa được khai báo trong POM hiện tại và Maven không thể suy ra prefix từ những group mặc định.
- `com.example.build` chưa có trong `<pluginGroups>` của settings (nếu dùng plugin nội bộ).
- Metadata ánh xạ `quality → quality-maven-plugin` không có/không tải được ở plugin repositories.
- Plugin repository/mirror không cho phép truy cập hoặc artifact không tồn tại.
- Prefix được khai báo khác với tên bạn sử dụng.

Để tách vấn đề **prefix mapping** khỏi vấn đề **artifact resolution**, thử goal đầy đủ (chỉ với plugin/goal được tổ chức cấp thật):

~~~bash
mvn com.example.build:quality-maven-plugin:1.4.0:audit
~~~

Nếu tọa độ đầy đủ resolve được mà `quality:audit` không resolve, tập trung vào plugin group/prefix metadata. Nếu cả hai đều không tải được plugin, tập trung vào pluginRepositories, mirror, URL, credential và artifact.

Một số plugin có version/goal được khai báo trong POM nhưng prefix lookup có thể còn phụ thuộc context; không suy ra duy nhất một nguyên nhân từ dòng báo lỗi ngắn.

## 20. Trình tự repository và tác động của settings

Trong cấu hình Maven thực tế, repositories có thể được đóng góp từ nhiều nơi:

- User/global `settings.xml` và các profiles đang active.
- POM của project hiện tại và profiles.
- Parent POM và Super POM.
- POM của các dependency trên đường resolve, tùy quy tắc build/resolver.

Maven có thứ tự lựa chọn repository được định nghĩa; cùng một ID giữa settings và POM có thể chịu quy tắc ưu tiên/ghi đè khác với việc khai báo trùng ID trong cùng một nguồn. **Đừng cố đoán repository nào “thắng” chỉ bằng việc nó xuất hiện trước trong một file**, vì mirror và effective settings còn tham gia.

Các lệnh giúp quan sát:

~~~bash
mvn -B -ntp help:active-profiles
mvn -B -ntp help:effective-pom -Doutput=effective-pom.xml
mvn -B -ntp help:effective-settings
~~~

Nếu CI dùng settings riêng:

~~~bash
mvn -B -ntp -s path/to/ci-settings.xml help:active-profiles
mvn -B -ntp -s path/to/ci-settings.xml help:effective-pom -Doutput=ci-effective-pom.xml
mvn -B -ntp -s path/to/ci-settings.xml help:effective-settings
~~~

**Bảo mật:** effective settings có thể chứa các URL nội bộ, thông tin server và username. Mặc dù một số output mặc định che password, vẫn phải rà soát trước khi chia sẻ, và không bật tùy chọn hiển thị password.

Nếu thật sự cần biết Maven đang kết nối tới host nào, có thể dùng log debug `mvn -X ...` trong môi trường cho phép, nhưng phải lọc dữ liệu nhạy cảm trước khi đưa vào issue hoặc tài liệu công khai.

## 21. Không nhầm download với deploy

Hai nhóm `<repositories>` và `<pluginRepositories>` mô tả **nguồn để Maven download/resolve** artifact phục vụ build. Chúng **không phải** cách khai báo repository đích cho `mvn deploy`.

Đích upload artifact của project thường được chỉ định qua `<distributionManagement>`:

~~~xml
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
~~~

Đây chỉ là một **đoạn POM minh họa**, không dùng để chạy deploy vào URL giả. Credential upload phải liên kết server ID phù hợp trong settings và tài khoản phải có quyền deploy. `mvn install` cài artifact vào local repository, còn `mvn deploy` phát hành tới remote repository theo cấu hình deploy.

Với một **Maven plugin do tổ chức phát triển**, chính plugin cũng là một artifact được publish bằng quy trình Maven tương ứng. Khi consumer tải plugin ấy, nguồn download của plugin là `pluginRepositories`, không phải `distributionManagement` của consumer.

## 22. Ranh giới quyền hạn và an toàn khi chọn repository

Việc thêm một remote repository không chỉ là thay URL cho build chạy. Repository là **nguồn cung cấp mã thực thi** dưới dạng thư viện và plugin. Một plugin còn được Maven thực thi trong quá trình build; do đó rủi ro supply-chain cần đặc biệt được chú ý.

Nguyên tắc:

1. **Ưu tiên Maven Central và repository manager được tổ chức kiểm soát**, không thêm URL trên diễn đàn chỉ vì thiếu artifact.
2. **Chỉ dùng HTTPS** và thiết lập TLS/truststore đúng; không tắt xác minh certificate để né lỗi.
3. **Kiểm soát plugin version** và lý do nâng cấp; plugin là mã được chạy trên máy/runner.
4. **Giới hạn quyền đọc/ghi** của token: job build thường chỉ cần read dependencies/plugins, còn publish job cần quyền write riêng.
5. **Không chứa credential trong POM**, URL kiểu `https://user:token@...` hoặc script được commit.
6. **Thận trọng với snapshots**: chúng có thể thay đổi theo thời gian và dẫn đến build không tái lập.
7. **Không chỉnh `checksumPolicy` sang `ignore` chỉ để bỏ qua cảnh báo về integrity** nếu chưa hiểu nguồn artifact.
8. **Rà soát mirrorOf**: mirror phạm vi rộng khiến nhiều request gửi đến một endpoint; endpoint ấy cần được kiểm soát và đáp ứng cả dependencies lẫn plugins.
9. **Chú ý repository ID và credential scope** theo Maven phiên bản mới; trùng ID không có nghĩa được phép gửi token tới host khác.
10. **Xác minh artifact thật**: Maven build thành công là điều kiện cần, không tự bảo đảm dependency/plugin an toàn; kết hợp provenance, checksum/signature và chính sách kiểm soát nguồn.

Khi dùng plugin nội bộ, người vận hành nên quản lý quy trình phát hành plugin tương tự thư viện thông thường, bao gồm versioning, binary compatibility, kiểm thử và rollback. Một plugin bị nâng cấp ngầm có thể thay đổi toàn bộ hành vi build dù mã nguồn ứng dụng không đổi.

## 23. Những nhầm lẫn phổ biến

| Nhận định sai | Giải thích chính xác |
| --- | --- |
| “`repositories` là đủ cho cả library và plugin.” | Maven có danh sách plugin repositories riêng; nếu plugin chỉ có ở kho nội bộ, phải bảo đảm kho ấy nằm trong danh sách plugin resolution |
| “`pluginRepositories` chỉ dùng khi phát triển Maven plugin.” | Nó cần khi **bất kỳ project nào phải tải Maven plugin** từ nguồn không sẵn có mặc định |
| “Cả hai có cùng URL là cấu hình trùng thừa vô nghĩa.” | Một remote có thể tham gia hai danh sách resolution khác nhau |
| “`build.plugins` thêm URL tải plugin.” | `build.plugins` chỉ định plugin/version/execution; nơi tìm plugin do plugin repositories/mirror quyết định |
| “`dependencyManagement` thêm repository.” | Nó quản lý project dependencies, không chỉ định nguồn tải |
| “`pluginManagement` là repository plugin.” | Nó quản lý plugin versions/configuration, không phải URL |
| “Plugin artifact phải xuất hiện trong `dependency:tree` project.” | Plugin có realm/resolution riêng; cây project dependencies không phải danh sách Maven plugins |
| “Central chỉ tải libraries, không tải plugins.” | Central chứa cả hai; Super POM thường khai báo Central cho cả hai mục đích |
| “Thêm mirror chỉ thay dependency downloads.” | Mirror phù hợp có thể được áp dụng cả với plugin repository requests |
| “Một `<server>` khớp hostname bất kỳ là đủ.” | Credential được liên kết theo repository/mirror ID và còn bị giới hạn origin ở Maven mới |
| “`pluginGroups` cho Maven biết URL plugin.” | Nó cho biết các groupId cần dò prefix; URL đến từ plugin repositories |
| “`distributionManagement` dùng để tải dependencies.” | Nó chủ yếu xác định nơi **deploy/publish** artifact |
| “Offline build thành công chứng minh URL repository đúng.” | Cache cục bộ có thể đã có mọi artifact, cần thử môi trường sạch/kiểm soát khi chẩn đoán |
| “Maven tải được plugin thì dependencies chắc chắn tải được.” | Hai quá trình có danh sách repository và chính sách khác nhau |

## 24. Bài tập tự kiểm tra có đáp án

1. **Project muốn dùng `com.example.internal:business-client:1.2.0` chỉ có trong kho riêng. Nên khai báo gì?**  
   **Đáp án:** Repository phù hợp trong `<repositories>` hoặc settings profile/mirror được tổ chức cấp. Ngoài ra phải khai báo dependency thực sự dùng trong `<dependencies>`.

2. **Project dùng `com.example.build:quality-maven-plugin:1.4.0` chỉ có trong kho plugin riêng. Khai báo gì?**  
   **Đáp án:** Plugin trong `<build><plugins>` hoặc gọi goal trực tiếp, và kho chứa plugin phải có trong `<pluginRepositories>` hiệu lực (hoặc mirror đáp ứng).

3. **Một URL `https://repo.example.org/repository/maven-all` chứa cả thư viện và plugin. Có thể dùng cùng URL trong cả hai phần tử?**  
   **Đáp án:** Có. Chúng đại diện cho hai danh sách resolution logic khác nhau.

4. **Vì sao dự án không khai báo repository vẫn có thể build bằng Commons Lang và Compiler Plugin?**  
   **Đáp án:** Maven Central thường có trong Super POM cho cả dependency và plugin resolution, nếu không bị cấu hình khác thay đổi.

5. **Trong cây `dependency:tree` không thấy Maven Compiler Plugin, có nghĩa nó chưa chạy?**  
   **Đáp án:** Không. Cây đó chủ yếu mô tả project dependencies; plugin được quản lý ở phần build.

6. **Thêm `<pluginRepositories>` có tự kích hoạt plugin `quality` không?**  
   **Đáp án:** Không. Còn cần khai báo/gọi plugin và goal có thật.

7. **Plugin prefix lookup không tìm được nhưng gọi goal bằng tọa độ đầy đủ thì chạy. Nghi gì?**  
   **Đáp án:** Plugin group/prefix metadata hoặc cách gọi prefix, không nhất thiết là thiếu plugin artifact.

8. **Server có ID `company-mirror`; mirror thay `central`. Credential nên liên kết ID nào?**  
   **Đáp án:** Thông thường là `company-mirror`, tức ID của endpoint mà Maven thực tế dùng.

9. **Một plugin version `2.0-SNAPSHOT` không tải được. Policy nào cần kiểm tra?**  
   **Đáp án:** Snapshot policy ở **plugin repositories** hiệu lực hoặc mirror; không chỉ ở project `repositories`.

10. **`mvn -o` chạy thành công có chứng minh URL repo đang online không?**  
    **Đáp án:** Không. Offline chỉ dùng những artifact cần thiết đã có trong local repository.

11. **Muốn publish artifact release lên remote nên thêm `distributionManagement` hay `pluginRepositories`?**  
    **Đáp án:** `distributionManagement` hoặc cơ chế deploy tương ứng; `pluginRepositories` dành cho tải plugin.

12. **Maven Dependency Plugin được tải từ đâu, và nó phân tích gì khi chạy `dependency:tree`?**  
    **Đáp án:** Chính plugin được resolve qua plugin repositories, còn goal `tree` phân tích project dependency graph.

13. **Plugin không tải được nhưng project dependencies resolve bình thường. Đổi scope `compile` sang `runtime` có giải quyết đúng nguyên nhân không?**  
    **Đáp án:** Không. Scope của project dependency không sửa URL/permission của plugin repository.

14. **Nếu tất cả request đều đi qua mirror nhưng plugin riêng không có trong proxy group, phải làm gì?**  
    **Đáp án:** Đề nghị quản trị repository manager cung cấp plugin hoặc điều chỉnh quy tắc mirror được cho phép; không thêm URL không tin cậy để né kiểm soát.

15. **Có thể commit token trong `pom.xml` vì repository ID chỉ dùng nội bộ không?**  
    **Đáp án:** Không. Credentials phải quản lý bằng settings/secret store và quyền tối thiểu.

## 25. Checklist cấu hình và chẩn đoán

- [ ] Đã xác định artifact cần resolve là **project dependency** hay **Maven plugin**.
- [ ] Project dependencies được khai báo trong `<dependencies>`, plugin trong `<build><plugins>` hoặc goal phù hợp.
- [ ] Đã phân biệt `repositories` và `pluginRepositories`; nếu dùng chung kho, cấu hình tham gia cả hai danh sách hoặc mirror thực sự đáp ứng.
- [ ] Đã kiểm tra Maven Central/Super POM, parent, profiles và settings hiệu lực.
- [ ] Đã xác định đúng URL, repository ID, release/snapshot policy.
- [ ] Nếu có mirror, đã kiểm tra `mirrorOf` và endpoint thực tế, không chỉ ID/URL trong POM.
- [ ] Nếu có auth, `servers.server.id` khớp repository/mirror ID mà Maven dùng và token đúng phạm vi.
- [ ] Đã kiểm tra plugin prefix/metadata và `pluginGroups` nếu gọi plugin bằng prefix.
- [ ] Đã xác nhận plugin version rõ ràng và plugin artifact/goal có thật.
- [ ] Đã phân biệt **plugin dependencies** với **project dependencies**.
- [ ] Đã đọc `help:effective-pom`, `help:effective-settings` và active profiles trong ngữ cảnh đúng.
- [ ] Đã chạy thử clean build với đúng settings/CI flags, không dựa hoàn toàn vào cache local.
- [ ] Đã rà soát log, không đưa password/token hoặc host nội bộ nhạy cảm ra công khai.
- [ ] Đã phân biệt repository để **download** với `distributionManagement` để **deploy**.

## Tài liệu Maven chính thức

- [Apache Maven — POM Reference: Repositories and Plugin Repositories](https://maven.apache.org/pom.html): cú pháp, release/snapshot policy, `pluginRepositories` và cấu hình trong Super POM.
- [Apache Maven — Introduction to Repositories](https://maven.apache.org/guides/introduction/introduction-to-repositories.html): remote/local repository và cách Maven lấy dependencies.
- [Apache Maven — Settings Reference](https://maven.apache.org/settings.html): settings profiles, `repositories`, `pluginRepositories`, `servers`, mirrors và credential origin scope.
- [Apache Maven — Using Mirrors for Repositories](https://maven.apache.org/guides/mini/guide-mirror-settings.html): `mirrorOf`, `external:*`, ID/URL và mirror resolution.
- [Apache Maven — Guide to Configuring Plug-ins](https://maven.apache.org/guides/mini/guide-configuring-plugins.html): plugin coordinates, version và vị trí `<build><plugins>`.
- [Apache Maven — Introduction to Plugin Prefix Resolution](https://maven.apache.org/guides/introduction/introduction-to-plugin-prefix-mapping.html): cơ chế `pluginGroups`, prefix và metadata.
- [Apache Maven — Maven Metadata](https://maven.apache.org/repositories/metadata.html): metadata ở cấp group/artifact/version và plugin prefix mapping.
- [Apache Maven — Guide to Multiple Repositories](https://maven.apache.org/guides/mini/guide-multiple-repositories.html): repository precedence, effective POM/settings và mirrors.

**Kết luận:** `<repositories>` trả lời “**mã ứng dụng/test lấy dependency ở đâu?**”, còn `<pluginRepositories>` trả lời “**Maven lấy công cụ build ở đâu?**”. Hai loại artifact có thể cùng nằm trên một server, thậm chí cùng URL, nhưng Maven sử dụng **hai nhóm repository resolution riêng**. Hãy kiểm tra đúng nhóm, đúng ID/mirror và đúng quyền trước khi chỉnh POM; đừng nhầm URL tải artifact với cấu hình `distributionManagement` để phát hành artifact.
