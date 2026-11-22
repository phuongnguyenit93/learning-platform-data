# `deploy`: xuất bản artifact cho các dự án, máy hoặc nhóm khác

## 1. Bài toán và mục tiêu

Một nhóm phát triển Java library `greetings-lib` muốn cho nhóm khác ở máy tính, Git repository hoặc CI runner độc lập dùng thư viện này. Việc copy thủ công file `target/greetings-lib-1.0.0.jar` không phải một quy trình phát hành Maven đáng tin: thiếu tọa độ phiên bản, POM dependency metadata, quyền truy cập, khả năng truy vết, cơ chế cập nhật và kiểm chứng artifact.

Maven giải quyết bằng **`deploy`**, phase cuối của default build lifecycle: publish main artifact, POM và những attached artifacts đã được đăng ký vào một **Maven deployment repository**. Consumer dùng dependency GAV (groupId/artifactId/version) và cấu hình repository để Maven tải đúng phiên bản.

Trong ví dụ, consumer chỉ cần:

~~~xml
<dependency>
    <groupId>demo.publish</groupId>
    <artifactId>greetings-lib</artifactId>
    <version>1.0.0</version>
</dependency>
~~~

Bài học thuộc chủ đề **Install và Deploy**. Bạn sẽ học:

1. Phân biệt `package`, `install`, `deploy` với triển khai ứng dụng runtime.
2. Hiểu local repository, deployment repository, dependency-resolution repository, GAV, Maven layout và POM metadata.
3. Cấu hình `distributionManagement`, release/snapshot repositories và `settings.xml` credentials theo repository ID.
4. Tạo và publish Java 17/JUnit 5 library bằng Maven Deploy Plugin.
5. Dựng consumer độc lập để lấy artifact từ một kho `file:` mô phỏng remote repository, tránh nhầm local `install`.
6. Hiểu snapshots timestamp, release immutability, plugin goal `deploy:deploy` so với `deploy:deploy-file`.
7. Cấu hình `altDeploymentRepository`, đính kèm sources/Javadocs và multi-module `deployAtEnd`.
8. Triển khai CI/CD bảo mật, chẩn đoán 401/403/404/409, sai GAV, thiếu POM, lệch dependency và cache.
9. Chứng minh deployment bằng **build log + repository content + consumer từ cache riêng**.

Ví dụ dựa trên Maven 3.x, JDK 17, Maven Deploy Plugin `3.1.4`, Compiler Plugin `3.13.0`, Surefire Plugin `3.5.4`, Exec Maven Plugin `3.3.0` và JUnit Jupiter `5.11.4`. Đây là các version ghim cho bài tập, không phải khẳng định phiên bản mới nhất.

## 2. Ba phase quan trọng: `package`, `install` và `deploy`

| Lệnh | Làm gì? | Phạm vi artifact |
| --- | --- | --- |
| `mvn package` | Biên dịch, kiểm thử theo lifecycle và đóng gói. | `target/*.jar`/WAR/archive trong project. |
| `mvn install` | Đi qua `package` rồi cài artifact/POM vào local Maven repository. | Mặc định `~/.m2/repository` của máy hiện tại. |
| `mvn deploy` | Đi qua `install` rồi publish artifact/POM vào deployment repository. | Các consumers có thể truy cập repository đó. |

Lifecycle rút gọn của project `packaging=jar`:

~~~text
validate → compile → test → package → verify → install → deploy
                                 │         │          │
                                 ▼         ▼          ▼
                              target/   ~/.m2/      shared/release
~~~

Đây chỉ là những phase tiêu biểu, không phải danh sách đầy đủ. Nếu unit test fail ở `test`, Maven thường dừng trước khi có publish. Nếu một plugin không được bind vào lifecycle, `mvn deploy` không tự chạy goal đó; build artifact cần được tạo bởi packaging và executions phù hợp.

### `deploy` không khởi động ứng dụng production

Tên này dễ gây nhầm. Maven `deploy` là **publication tới artifact repository**, khác:

- Docker image push tới container registry.
- Kubernetes apply/Helm upgrade để rollout service.
- SSH copy WAR/JAR rồi restart process.
- Database migrations.
- `mvn site:deploy` để publish project website.

Một pipeline có thể chạy các bước runtime rollout sau Maven publish, nhưng đó là các bước riêng có quyền và cơ chế rollback khác nhau.

### Vì sao `mvn install` chưa đủ để chia sẻ?

Local repository là cache trên **một môi trường Maven cụ thể**. Bạn chạy `install` thành công trên laptop A không khiến Maven trên laptop B hoặc CI container tải được JAR. Để chia sẻ bền vững, cần một kho phát hành mà các môi trường khác có thể đọc.

## 3. Maven coordinates và repository layout

Giả sử producer có:

~~~xml
<groupId>demo.publish</groupId>
<artifactId>greetings-lib</artifactId>
<version>1.0.0</version>
<packaging>jar</packaging>
~~~

Main artifact của phiên bản release này trong Maven 2 repository layout sẽ thường ở:

~~~text
demo/publish/greetings-lib/1.0.0/
    greetings-lib-1.0.0.jar
    greetings-lib-1.0.0.pom
~~~

Có thể thêm `maven-metadata.xml`, checksum và signature files tùy plugin/repository manager. `groupId` đổi dấu chấm thành đường dẫn; `artifactId` và `version` tạo các tầng còn lại.

POM được publish quan trọng như JAR: khi consumer yêu cầu dependency, Maven đọc POM để hiểu transitive dependencies, scopes, parent POM, dependencyManagement và thông tin khác. Chỉ copy binary JAR vào thư mục không đủ để bảo đảm repository metadata hợp lệ.

### Main và attached artifacts

Nếu project có những plugin phù hợp, `mvn deploy` còn có thể đưa lên:

~~~text
greetings-lib-1.0.0-sources.jar
greetings-lib-1.0.0-javadoc.jar
greetings-lib-1.0.0-tests.jar
greetings-lib-1.0.0-all.jar
~~~

Những file có classifier `sources`, `javadoc`, `tests`, `all` chỉ trở thành **attached artifacts** khi plugin thực sự attach chúng vào Maven project. File `target/custom-fat.jar` nằm trên đĩa không tự động được publish. Consumer muốn variant phải khai báo đúng `<classifier>` và `<type>` khi cần.

## 4. Ba loại repository không giống nhau

| Repository | Được dùng để | Cấu hình chủ yếu |
| --- | --- | --- |
| **Local repository** | Cache artifact tải về, plugin và artifacts đã install. | `~/.m2/repository`, `settings.xml/localRepository`, `-Dmaven.repo.local`. |
| **Deployment repository** | **Đích ghi** của `mvn deploy`. | `distributionManagement` hoặc `altDeploymentRepository`. |
| **Resolution repository** | **Nguồn đọc** cho dependency consumers. | `<repositories>`, active profiles trong `settings.xml`, parent/Super POM. |

`<pluginRepositories>` điều khiển nguồn plugin artifacts, không phải đích publish của library.

**Producer muốn ghi:**

~~~xml
<distributionManagement>
    <repository>
        <id>team-releases</id>
        <url>https://repo.example.org/repository/releases</url>
    </repository>
</distributionManagement>
~~~

**Consumer muốn đọc:**

~~~xml
<repositories>
    <repository>
        <id>team-releases</id>
        <url>https://repo.example.org/repository/releases</url>
    </repository>
</repositories>
~~~

`repo.example.org` là domain minh họa, không phải hệ thống cụ thể để đăng nhập. Hai sections khác chức năng: `distributionManagement` **không tự** thêm một read repository cho mọi consumer; `<repositories>` **không chỉ định** đích Deploy Plugin mặc định.

Trong công ty, repository manager như Nexus hoặc Artifactory thường có hosted release, hosted snapshots và proxy read repositories. Consumer thường dùng một group/virtual read URL, publisher dùng hosted write URL được phân quyền riêng.

## 5. `distributionManagement`: đích publish release/SNAPSHOT

Một POM có thể cấu hình:

~~~xml
<distributionManagement>
    <repository>
        <id>team-releases</id>
        <name>Hosted Releases</name>
        <url>https://repo.example.org/repository/releases</url>
    </repository>
    <snapshotRepository>
        <id>team-snapshots</id>
        <name>Hosted Snapshots</name>
        <url>https://repo.example.org/repository/snapshots</url>
    </snapshotRepository>
</distributionManagement>
~~~

- `repository`: đích ghi release như `1.0.0`.
- `snapshotRepository`: đích ghi SNAPSHOT như `1.1.0-SNAPSHOT` khi được khai báo.
- `id`: định danh repository, dùng để khớp với `settings.xml` server credentials.
- `url`: URI thực của repository; HTTPS phổ biến với server, `file:` phù hợp demo/local.
- Nếu không có `snapshotRepository`, plugin có thể dùng repository mặc định để publish SNAPSHOT, nhưng server có thể từ chối theo policy. Nên tách rõ trong dự án production.

Parent POM có thể cung cấp chung `distributionManagement` cho modules. Khi release multi-module, phải xác minh parent được kế thừa và cấu hình đích viết đúng cho từng project cần publish.

### Không lưu credentials trong `pom.xml`

POM thường được chia sẻ/commit và có thể được publish cùng artifact. Username/password/token không thuộc phần Git-tracked POM. Dùng `settings.xml` hoặc settings file được CI tạo từ secret manager.

## 6. `settings.xml` và repository server ID

Nếu POM ghi `team-releases` và `team-snapshots`, `~/.m2/settings.xml` hoặc file settings CI dùng qua `mvn -s ...` có thể chứa:

~~~xml
<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0"
          xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
          xsi:schemaLocation="http://maven.apache.org/SETTINGS/1.2.0
                              https://maven.apache.org/xsd/settings-1.2.0.xsd">
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

**Mẫu minh họa:** environment variables phải được CI thiết lập từ secret store, không dùng giá trị rỗng hoặc commit secrets. Maven settings hỗ trợ interpolation environment/system properties theo Maven version; trong môi trường thật nên kiểm chứng cấu hình và secret injection.

Lỗi thường gặp: POM có repository ID `team-releases` nhưng settings `server` lại có ID `team-release` (thiếu chữ s). Maven có thể không tìm đúng credentials; server trả 401/403. Khắc phục bằng cách kiểm tra **ID, quyền, URL và token scope**, không thêm secret vào POM.

**Nguyên tắc bảo mật:** HTTPS/TLS, quyền deploy tối thiểu, secret rotation, không xuất token qua Maven debug logs. Một số phiên bản Maven mới giới hạn việc tái sử dụng credential ID sang origins khác; không dùng một ID tin cậy với tùy ý host qua `altDeploymentRepository`.

Consumer chỉ cần quyền **read**; publisher mới cần quyền **write**.

## 7. Bài lab an toàn: hai Maven projects và một file repository

Thay vì publish lên kho thật, ta tạo Maven repository trong filesystem để mô phỏng giao thức repository layout và kiểm tra consumer resolution.

Cây thư mục:

~~~text
maven-deploy-lab/
├── producer/
│   ├── pom.xml
│   └── src/
│       ├── main/java/demo/publish/Greeter.java
│       └── test/java/demo/publish/GreeterTest.java
├── consumer/
│   ├── pom.xml
│   └── src/main/java/demo/client/Main.java
├── repository/                # Được Maven deploy tạo/ghi
├── snapshot-repository/       # Chỉ dùng với SNAPSHOT
└── consumer-local-repo/       # Cache riêng cho consumer
~~~

**Điều kiện:** Maven 3.x, JDK 17, kết nối tới dependency/plugin repositories trong lần chạy đầu, quyền ghi các thư mục lab.

**Nền tảng:** POM bên dưới dùng `file://${project.basedir}/../repository` để tạo file URI tuyệt đối thuận tiện trên **Linux/macOS** khi hai projects nằm cạnh nhau. Trên **Windows**, đặt lab tại `C:\maven-deploy-lab` và thay URL trong **cả hai POM** thành `file:///C:/maven-deploy-lab/repository`. Snapshot URL tương ứng `file:///C:/maven-deploy-lab/snapshot-repository`. Đừng dùng backslash trong URI.

`file:` repository ở cùng máy chỉ là thử nghiệm publication semantics; nó không kiểm chứng HTTP authentication, mạng hay cross-machine access. Với production, thay bằng hosted repository URL được quản trị.

## 8. Producer: POM hoàn chỉnh của Java library

Tạo `producer/pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo.publish</groupId>
    <artifactId>greetings-lib</artifactId>
    <version>1.0.0</version>
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

    <distributionManagement>
        <repository>
            <id>demo-releases</id>
            <name>Demo Release File Repository</name>
            <url>file://${project.basedir}/../repository</url>
        </repository>
        <snapshotRepository>
            <id>demo-snapshots</id>
            <name>Demo Snapshot File Repository</name>
            <url>file://${project.basedir}/../snapshot-repository</url>
        </snapshotRepository>
    </distributionManagement>

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
                <version>3.5.4</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-deploy-plugin</artifactId>
                <version>3.1.4</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Cấu hình này làm những gì?

- Định danh artifact `demo.publish:greetings-lib:1.0.0`.
- `maven.compiler.release=17` đặt Java bytecode/API target.
- JUnit Jupiter `test` scope phục vụ test, không là runtime dependency của consumers.
- `distributionManagement/repository` chỉ vào `maven-deploy-lab/repository` khi chạy trên Unix từ cây thư mục đã mô tả.
- `snapshotRepository` phục vụ phần mở rộng SNAPSHOT.
- Ghim plugin versions để tránh Maven plugin defaults thay đổi bất ngờ.
- Không cần bind `deploy:deploy` bằng `<executions>` trong project JAR thông thường vì Deploy Plugin đã có lifecycle binding cho `deploy` phase.

### `producer/src/main/java/demo/publish/Greeter.java`

~~~java
package demo.publish;

import java.util.Objects;

public final class Greeter {
    private Greeter() {
    }

    public static String hello(String name) {
        Objects.requireNonNull(name, "name");
        return "Hello " + name + " from published library";
    }
}
~~~

Đây là class độc lập chỉ dùng Java 17 standard library. Runtime consumer không cần external Java library ngoài producer artifact.

### `producer/src/test/java/demo/publish/GreeterTest.java`

~~~java
package demo.publish;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class GreeterTest {
    @Test
    void producesGreeting() {
        assertEquals(
                "Hello Maven from published library",
                Greeter.hello("Maven"));
    }

    @Test
    void rejectsNull() {
        assertThrows(
                NullPointerException.class,
                () -> Greeter.hello(null));
    }
}
~~~

Có **hai** JUnit 5 test methods. Surefire nhận lớp `*Test` và chúng phải PASS trước khi Maven đi tới phase publish trong default lifecycle.

## 9. Chạy producer: từ source tới repository

Trên Linux/macOS, mở terminal ở `maven-deploy-lab/producer`:

~~~bash
mvn --version
java -version
mvn -B -ntp clean deploy
~~~

Trên Windows PowerShell sau khi đổi đúng file URI ở POM:

~~~powershell
Set-Location C:\maven-deploy-lab\producer
mvn -B -ntp clean deploy
~~~

Kỳ vọng với JDK/Maven/repositories hợp lệ:

1. Compiler biên dịch `Greeter.java`.
2. Surefire chạy `GreeterTest` với 2 tests PASS.
3. JAR Plugin tạo `target/greetings-lib-1.0.0.jar`.
4. Install phase cài JAR/POM vào local repository của Maven.
5. Deploy Plugin upload JAR/POM vào `repository` của lab.
6. Maven in `BUILD SUCCESS`.

Đây là **kết quả dự đoán từ POM/code**, không phải khẳng định đã chạy thật tại một máy cụ thể.

Thư mục đích cần có ít nhất:

~~~text
repository/
└── demo/
    └── publish/
        └── greetings-lib/
            ├── maven-metadata.xml
            └── 1.0.0/
                ├── greetings-lib-1.0.0.jar
                └── greetings-lib-1.0.0.pom
~~~

Maven/repository có thể tạo các checksum và metadata files bổ sung. Đây là cây rút gọn.

### Phân biệt hai nơi artifact xuất hiện

~~~text
producer/target/greetings-lib-1.0.0.jar     # package output
~/.m2/repository/.../greetings-lib-1.0.0.jar # install vào local cache
repository/demo/publish/.../greetings-lib-1.0.0.jar # deploy output
~~~

Hai file sau thuộc các kho khác chức năng, dù trong bài lab chúng cùng nằm trên một máy.

### Kiểm tra binary sau publish

Ở `producer` (Linux/macOS):

~~~bash
jar tf ../repository/demo/publish/greetings-lib/1.0.0/greetings-lib-1.0.0.jar
~~~

Trong listing cần thấy `demo/publish/Greeter.class`. Nếu JAR tồn tại nhưng class thiếu, có thể đã publish nhầm archive hoặc packaging sai.

Không nhận định deploy PASS chỉ vì thấy JAR ở `target`. Cần Maven phase log, repository content và consumer resolution.

## 10. Consumer: project riêng tải `greetings-lib` từ repo

Tạo `consumer/pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo.client</groupId>
    <artifactId>greetings-client</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <repositories>
        <repository>
            <id>demo-releases</id>
            <url>file://${project.basedir}/../repository</url>
            <releases>
                <enabled>true</enabled>
            </releases>
            <snapshots>
                <enabled>false</enabled>
            </snapshots>
        </repository>
    </repositories>

    <dependencies>
        <dependency>
            <groupId>demo.publish</groupId>
            <artifactId>greetings-lib</artifactId>
            <version>1.0.0</version>
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
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**Không có `distributionManagement` trong consumer**: consumer chỉ muốn **đọc**, không publish. Khi thử Windows, thay `<url>` ở consumer bằng cùng URL đã dùng ở producer, ví dụ `file:///C:/maven-deploy-lab/repository`.

### `consumer/src/main/java/demo/client/Main.java`

~~~java
package demo.client;

import demo.publish.Greeter;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        System.out.println(Greeter.hello("Maven"));
    }
}
~~~

Consumer import từ JAR được resolve qua dependency GAV; nó **không** nằm trong cùng Maven Reactor với producer.

### Chạy với local repository riêng

Linux/macOS từ `maven-deploy-lab/consumer`:

~~~bash
mvn -q -Dmaven.repo.local=../consumer-local-repo compile exec:java -Dexec.mainClass=demo.client.Main
~~~

Windows PowerShell:

~~~powershell
mvn -q "-Dmaven.repo.local=../consumer-local-repo" compile exec:java "-Dexec.mainClass=demo.client.Main"
~~~

**Stdout ứng dụng chính xác khi thành công:**

~~~text
Hello Maven from published library
~~~

Tham số `-q` giảm Maven INFO logs; network/warnings vẫn có thể xuất hiện, nên đây là stdout của **chương trình Java**, không phải tất cả output terminal cố định.

### Tại sao tách local cache cho consumer?

`mvn deploy` bao gồm `install` nên producer đã cài library vào local cache mặc định. Nếu consumer chạy với **cùng cache**, nó có thể PASS ngay cả khi deployment repository bị thiếu artifact. `-Dmaven.repo.local=../consumer-local-repo` giúp Maven phải resolve producer dependency vào cache riêng. Maven vẫn cần plugins và các external artifacts của nó, nên cache mới có thể khiến lần chạy đầu lâu hơn và đòi network.

Để kiểm chứng mạnh hơn, chạy consumer trên CI runner/máy khác và đọc từ remote repository manager có quyền. File repository cùng máy chỉ chứng minh cơ chế publication và resolution, không chứng minh TCP/HTTPS/TLS/auth.

## 11. Vì sao publish cả POM và dependencies metadata?

Giả sử thư viện `greetings-lib` sau này dùng:

~~~xml
<dependency>
    <groupId>org.apache.commons</groupId>
    <artifactId>commons-lang3</artifactId>
    <version>3.14.0</version>
</dependency>
~~~

Đây là **mảnh dependency minh họa, không nằm trong POM runnable ở mục 8**. Khi publish, consumer thường nhận được POM khai báo `commons-lang3` và Maven resolver tải transitive dependency đúng scope.

Nếu copy JAR mà không publish POM hợp lệ, consumer dễ gặp `ClassNotFoundException`/`NoClassDefFoundError` hoặc phải tự quản lý jars. Maven coordinates, dependency scopes và POM metadata chính là khác biệt giữa phát hành Maven-native và chia sẻ file binary thủ công.

Chú ý:

- `scope=test` không thông thường truyền transitively vào consumer runtime.
- `optional=true`/`provided` và exclusions có những quy tắc riêng.
- Parent POM/BOM được tham chiếu cũng cần có khả năng resolve bên ngoài source checkout.
- Một POM chứa repository credentials hoặc absolute local filesystem path có thể không phù hợp để publish.
- Nếu ký artifact hay yêu cầu license/SCM metadata, cấu hình chúng theo policy của repository đích.

## 12. Release khác SNAPSHOT như thế nào?

| Version | Loại | Tính chất |
| --- | --- | --- |
| `1.0.0` | Release | Nên bất biến; gắn với commit/tag/kiểm thử đã duyệt. |
| `1.0.1-SNAPSHOT` | Snapshot | Phát hành nhiều bản phát triển, metadata có thể trỏ timestamp/build mới. |

Trong POM producer demo, `<version>1.0.0</version>` khiến Maven chọn `<repository>` release. Nếu chuyển thành:

~~~xml
<version>1.0.1-SNAPSHOT</version>
~~~

và chạy:

~~~bash
mvn -B -ntp clean deploy
~~~

Maven dùng `snapshotRepository` đã khai báo.

Repository snapshot có thể chứa:

~~~text
snapshot-repository/demo/publish/greetings-lib/1.0.1-SNAPSHOT/
    greetings-lib-1.0.1-20261110.123456-1.jar
    greetings-lib-1.0.1-20261110.123456-1.pom
    maven-metadata.xml
~~~

**Timestamp `20261110.123456-1` chỉ là ví dụ để hiểu tên file**, không phải giá trị sẽ có trên máy thật. Consumer vẫn khai báo `<version>1.0.1-SNAPSHOT</version>`, không tự gõ timestamp vào GAV. Maven resolver dùng snapshot metadata và update policy để tìm phiên bản phù hợp.

### Consumer đọc SNAPSHOT

Một mảnh `<repositories>` dành cho SNAPSHOT:

~~~xml
<repositories>
    <repository>
        <id>demo-snapshots</id>
        <url>file://${project.basedir}/../snapshot-repository</url>
        <releases>
            <enabled>false</enabled>
        </releases>
        <snapshots>
            <enabled>true</enabled>
            <updatePolicy>always</updatePolicy>
        </snapshots>
    </repository>
</repositories>
~~~

Đây là **mảnh cấu hình thay thế** cho repository release trong consumer khi bạn đổi dependency sang SNAPSHOT, không phải một POM thứ hai hoàn chỉnh. Nếu cần cả hai, đặt hai `<repository>` entries dưới **một** `<repositories>`.

`updatePolicy=always` phù hợp bài lab muốn kiểm tra snapshot mới thường xuyên; môi trường CI cần cân nhắc reproducibility/caching. `mvn -U` có thể yêu cầu kiểm tra updates theo cơ chế Maven; nó không chữa version mismatch, lỗi quyền hoặc thiếu metadata trên server.

**Release immutability:** một file repo local có thể cho phép overwrite `1.0.0`, nhưng repository manager production thường chặn redeploy cùng release coordinate. Không dùng việc file repo chấp nhận overwrite làm quy trình xuất bản release.

## 13. Chỉ định đích khác bằng `altDeploymentRepository`

Maven Deploy Plugin 3.x cho phép truyền:

~~~bash
mvn -B -ntp deploy -DaltDeploymentRepository=demo-override::file:///tmp/maven-demo-override
~~~

Cú pháp `id::url`:

- `demo-override` là repository ID.
- `file:///tmp/maven-demo-override` là file URI đích thử nghiệm trên Unix.
- Nếu URL cần authentication, `id` phải có cấu hình `server` phù hợp trong settings.

**Không dùng cú pháp Deploy Plugin 2.x cũ `id::layout::url`** cho plugin 3.x. Cũng có các tham số `altReleaseDeploymentRepository` và `altSnapshotDeploymentRepository` để override riêng theo version type.

Trên Windows có thể dùng file URI `file:///C:/maven-deploy-lab/override-repository` nếu đã chuẩn bị thư mục phù hợp.

### Rủi ro override

Một người có thể dùng cùng repository ID nhưng thay URL sang server khác. Điều này rất rủi ro nếu môi trường tự gán credentials theo ID. Trong CI:

- Danh sách đích publish phải được phê duyệt.
- Hạn chế token publish theo host/repository/path.
- Không lấy URL từ biến môi trường không tin cậy.
- Log đích publish và GAV, không log token.
- Dùng kiểm soát credentials/origin hỗ trợ bởi Maven/runtime phù hợp.

Override hữu ích cho staging/lab, không phải lý do để bỏ qua quy trình release.

## 14. `deploy:deploy` so với `deploy:deploy-file`

Deploy Plugin có hai nhóm use case:

| Goal | Nguồn artifact | Use case |
| --- | --- | --- |
| `deploy:deploy` | Main/attached artifacts và POM của Maven project hiện tại. | Lệnh `mvn deploy` trong producer đã có POM. |
| `deploy:deploy-file` | Một binary đã có bên ngoài Maven lifecycle. | Publish artifact do vendor cung cấp hoặc được build bằng công cụ khác, khi có quyền. |

Với project của bạn, thường chọn `mvn deploy`. Không cần `deploy-file` để tự viết lại GAV mà POM đã chứa.

Ví dụ cú pháp minh họa cho một file vendor được phép publish vào **repo thử nghiệm**:

~~~bash
mvn org.apache.maven.plugins:maven-deploy-plugin:3.1.4:deploy-file -Dfile=vendor-tool-1.0.jar -DgroupId=demo.vendor -DartifactId=vendor-tool -Dversion=1.0 -Dpackaging=jar -DrepositoryId=demo-override -Durl=file:///tmp/maven-demo-override -DgeneratePom=true
~~~

Lệnh này chỉ chạy nếu `vendor-tool-1.0.jar` thật sự tồn tại và bạn có quyền phân phối. `generatePom=true` tạo metadata tối thiểu; nếu vendor có POM chính thức với dependencies/licensing, hãy xem `-DpomFile` phù hợp thay vì tự tạo metadata thiếu.

### Phát hành files đính kèm

Các artifacts như `-sources.jar` và `-javadoc.jar` thường được Maven Source/Javadoc plugins tạo và **attach trước deploy**. Deploy Plugin không tự sản xuất sources hoặc Javadoc. Đừng chỉ nhìn `target` và giả định mọi JAR đều được publish.

## 15. Parent POM và multi-module Reactor

Trong một project có:

~~~text
parent/
├── pom.xml                # packaging=pom
├── api/pom.xml             # packaging=jar
└── service/pom.xml         # phụ thuộc api
~~~

`mvn clean deploy` từ root có thể publish:

- Parent `pom.xml` như POM artifact.
- Main JAR/POM của `api`.
- Main JAR/POM của `service`.
- Các attached artifacts thực sự có trong những modules.

Việc publish parent rất quan trọng nếu POM của `api`/`service` tham chiếu một parent POM chỉ có trên máy producer: consumer ở máy B sẽ không resolve được POM chain.

### `-pl` và `-am` mở rộng phạm vi publish

~~~bash
mvn -pl :service -am clean deploy
~~~

`-pl` chọn module `service`, `-am` đưa các upstream reactor projects cần thiết vào cùng build. **Lệnh trên có thể deploy cả prerequisites**, không chỉ service. Trước khi phát hành thật, xem Reactor Build Order, parent relationships và các module được chọn.

Nếu chỉ cần xác minh build, dùng `mvn -pl :service -am clean verify` để không ghi vào repository.

### `deployAtEnd` không phải atomic transaction

Ví dụ cấu hình:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-deploy-plugin</artifactId>
    <version>3.1.4</version>
    <configuration>
        <deployAtEnd>true</deployAtEnd>
    </configuration>
</plugin>
~~~

Đây là **mảnh plugin config** dành cho multi-module. Khi bật, plugin hoãn việc publish của những modules phù hợp tới giai đoạn cuối hơn, nhằm giảm trường hợp module A đã publish mà module B fail trước khi tới deploy.

Nhưng **không bảo đảm all-or-nothing**: nếu upload thứ ba lỗi, hai artifacts trước có thể đã tồn tại ở repository, hoặc một module dùng `deployAtEnd=false` vẫn publish sớm. Release cần nhất quán cao nên cân nhắc staging/promote repository manager và kiểm tra các thành phần trước khi promotion.

## 16. CI/CD: publish có kiểm soát, không chỉ một lệnh

Một pipeline đáng tin:

~~~text
Checkout commit/tag
       │
       ▼
JDK/Maven versions + build inputs
       │
       ▼
Unit/integration tests + quality gates
       │
       ▼
Validate version, POM dependencies, artifact contents
       │
       ▼
Credentialed publish job
       │
       ▼
mvn -B -ntp clean deploy
       │
       ▼
Repository integrity + consumer check
       │
       ▼
Release/promotion/audit/notification
~~~

`mvn deploy` thường chạy các phase trước đó, nhưng có thể bị biến đổi bởi profiles, `skipTests`, `maven.deploy.skip` hay plugin configuration. CI phải kiểm tra cổng chất lượng **thật sự chạy**, không chỉ đọc một dòng BUILD SUCCESS.

### Quyền tối thiểu

Consumer cần read; publish bot cần write vào đúng hosted repository. Không cho các PR từ nguồn không tin cậy lấy release token. CI secret store nên cấp token chỉ ở approved release jobs, không in qua command line/log, không đưa vào POM hoặc artifacts.

### Provenance và immutable releases

Một artifact release nên có:

- GAV không mơ hồ.
- Source commit/tag, run ID.
- Compiler/JDK/OS/runtime inputs quan trọng được ghi nhận.
- Unit/integration test report.
- Checksums/signatures nếu chính sách yêu cầu.
- Sources/Javadocs/license/SCM nếu repository đích yêu cầu.
- Consumer smoke test.
- Phương án thu hồi khi phát hiện lỗi sau publish.

**`mvn deploy` không tự tạo Git release tag, không tự ký JAR, không tự scan security và không tự rollout service.** Những bước đó thuộc công cụ/pipeline khác.

### Maven Release Plugin khác Maven Deploy Plugin

`release:prepare` có thể đổi versions, commit/tag trong SCM; `release:perform` thường build từ release tag và thực hiện deploy theo release process. Không chạy release goals trên repository thật chỉ để thử một ví dụ vì chúng có thể tác động Git/SCM. `mvn deploy` chỉ publish project artifacts của build/lifecycle hiện tại tới repository được cấu hình.

## 17. Đọc kết quả publish: ba tầng kiểm chứng

Một lần deploy được xác nhận tốt khi có:

**Tầng 1 — build log:** đúng goal `maven-deploy-plugin:deploy`, version và đích repository, không bị skip, Maven exit code thành công.

**Tầng 2 — repository:** JAR/POM và metadata/checksums khi áp dụng nằm dưới đường dẫn đúng GAV, nội dung JAR đúng class/resources, các classifiers được attach thực sự có file tương ứng.

**Tầng 3 — consumer:** một project **không thuộc Reactor** resolve artifact từ repository bằng local Maven cache tách biệt hoặc runner khác, compile và chạy đúng chức năng.

Với demo, chạy consumer:

~~~bash
mvn -q -Dmaven.repo.local=../consumer-local-repo compile exec:java -Dexec.mainClass=demo.client.Main
~~~

**Đầu ra chương trình:**

~~~text
Hello Maven from published library
~~~

Điều này mạnh hơn chỉ nhìn `producer/target`, nhưng muốn kiểm chứng việc chia sẻ giữa **nhiều máy** thì phải chạy consumer trên máy/runner khác trỏ tới repo HTTPS/shared thật.

## 18. Lỗi phổ biến khi `mvn deploy` và cách xử lý

| Triệu chứng | Nguyên nhân thường gặp | Hướng xác minh |
| --- | --- | --- |
| Thiếu deployment repository. | POM không có `distributionManagement` và không có alternative URL. | Xem effective POM, chọn đích hợp lệ. |
| HTTP `401 Unauthorized`. | Không gửi credentials hoặc token sai/hết hạn. | So `repository/id` và `settings.xml/server/id`, secret injection. |
| HTTP `403 Forbidden`. | Tài khoản không có quyền write hoặc repository policy từ chối. | Kiểm tra role và server audit log. |
| HTTP `404 Not Found`. | URL đích sai endpoint/path. | Xem đúng hosted Maven repository URL. |
| HTTP `409 Conflict`. | Artifact/version đã có hoặc release immutable policy. | Không ghi đè; dùng release version mới theo quy trình. |
| Timeout/5xx. | Mạng hoặc repository manager lỗi; publish có thể đã một phần. | Kiểm tra server state/logs trước retry. |
| `mvn package` PASS nhưng không có artifact trong shared repo. | Mới chạy `package` hoặc `install`. | Chạy `deploy` với target hợp lệ. |
| `BUILD FAILURE` ở test phase. | Test/quality gate fail trước deploy. | Sửa lỗi, không tự ý skip tests. |
| JAR có nhưng POM không có. | Upload thủ công hoặc `deploy-file` metadata sai. | Publish với project POM chính xác. |
| Consumer báo missing dependency. | Sai GAV, repo URL, version hoặc POM không đầy đủ. | Kiểm tra repository layout, dependency tree, parent/BOM. |
| Consumer lấy artifact cũ. | Local repository cache/metadata. | Dùng cache riêng, kiểm tra SNAPSHOT policy hoặc `-U`. |
| SNAPSHOT bị kho releases từ chối. | Sai `snapshotRepository`/server policy. | Tách đúng repo cho snapshot. |
| Release bị kho snapshots từ chối. | Repo policy không chấp nhận releases. | Chọn `repository` đúng. |
| Consumer `NoClassDefFoundError`. | Transitive dependency metadata thiếu hoặc scope không phù hợp. | Kiểm tra published POM và runtime classpath. |
| `Non-resolvable parent POM`. | Parent POM không được publish hoặc không thể đọc. | Publish parent/BOM và kiểm tra repository. |
| `-DaltDeploymentRepository` bị bỏ qua/sai. | Sai cú pháp 2.x/3.x, override priority hoặc config. | Với plugin 3.x dùng `id::url`. |
| Windows file repository lỗi. | URI dùng `C:\...` thay vì `file:///C:/...`. | Đổi sang URI hợp lệ trong cả POM. |
| CI cùng file repo trên máy A, nhóm B không truy cập được. | `file:` không phải mạng chia sẻ. | Dùng HTTPS repository manager/shared storage. |
| Source/Javadoc JAR không publish. | Plugin chưa attach hoặc execution chưa chạy. | Xem plugin goals và repository content. |
| `deployAtEnd` vẫn xuất bản một phần. | Không phải atomic transaction. | Dùng staging/promotion khi cần. |
| Maven nói success nhưng repo không đổi. | Deploy bị skip qua `maven.deploy.skip` hoặc sai đích. | Xem active profiles, goal logs và URL thực. |

### Trình tự điều tra

1. Xác nhận Maven đi tới **phase deploy** hay dừng ở phase sớm.
2. Lấy GAV/version/packaging và plugin version từ build đang lỗi.
3. Xác định deployment target bằng `distributionManagement` hoặc override.
4. Kiểm tra repository ID và auth credentials trên CI.
5. Đọc HTTP status/server audit log.
6. Kiểm tra repository đã nhận JAR/POM/metadata chưa trước khi retry upload mơ hồ.
7. Tạo consumer với local cache riêng, resolve GAV.
8. Ghi kết luận: build status, publish status, consumer status là ba thông tin riêng.

**Không lặp lại upload mù đối với một release đã tồn tại hoặc lỗi không rõ trạng thái**. Một số repository managers không cho phép redeploy và một số có thể nhận thành công một phần.

## 19. Các trường hợp đặc biệt

### `packaging=pom`

Một parent/aggregator không tạo JAR vẫn có thể publish **POM artifact**. Consumer cần parent POM để resolve inherited metadata. Ngược lại, project `packaging=jar` nhưng không có main artifact mà chỉ có classified attachments có thể gặp `allowIncompleteProjects` enforcement; đừng bật cờ bỏ qua nếu thiết kế project sai, cân nhắc `packaging=pom` khi thực sự không có main binary.

### `maven.deploy.skip`

Deploy Plugin 3.x hỗ trợ giá trị skip như `true`, `releases`, `snapshots`. Build có thể chạy đến deploy phase nhưng không publish. Nếu release pipeline yêu cầu xuất bản, phải kiểm tra skip values và artifact state; **BUILD SUCCESS không tự chứng minh đã publish**.

### Source và Javadoc

Maven Source/Javadoc plugins cần tạo/attach JARs vào build. Deploy Plugin publish những artifacts đã được Maven project đăng ký, không tự tạo sources/Javadoc chỉ vì chính sách repository yêu cầu chúng.

### Mirrors và proxy

Maven `settings.xml/mirrors` chủ yếu ảnh hưởng **dependency/plugin resolution**, không thay cho nơi `deploy` upload. Có thể dùng repository manager cho cả đọc và ghi, nhưng read group URL và hosted write URL thường khác. Khi debug, phân biệt read repository IDs và deployment target.

### Môi trường offline

Upload vào `file:` repo không cần mạng, nhưng Maven vẫn có thể tải compiler/Surefire/JUnit/plugins nếu local cache chưa có. `mvn -o` có thể fail sớm do thiếu artifact từ cache; đó không chứng minh file deployment sai.

## 20. Checklist publish cho nhóm khác

- [ ] Biết đúng GAV, version, packaging và classifiers dự định phát hành.
- [ ] Release không còn `-SNAPSHOT` ngoài ý muốn.
- [ ] Tests, integration tests và quality gates thật sự chạy/đạt.
- [ ] POM đủ dependency, parent, BOM metadata; không có machine-specific URLs/secrets.
- [ ] Main/attached JAR contents đúng; sources/Javadoc/signatures có nếu repo yêu cầu.
- [ ] `distributionManagement` hoặc alternative URL hợp lệ, đúng snapshot/release.
- [ ] `settings.xml/server/id` khớp repository ID và token có quyền tối thiểu.
- [ ] Không in credentials ra logs/POM/CI artifacts.
- [ ] Repository manager có policy immutability, staging/retention phù hợp.
- [ ] Đã thấy goal `deploy:deploy` chạy, không bị skip.
- [ ] Đã kiểm tra JAR/POM và metadata dưới đúng repository layout.
- [ ] Đã thử consumer độc lập với local repo riêng; đọc từ published repository.
- [ ] Đã ghi commit/tag/run ID/checksum và kết quả QA.
- [ ] Có quy trình xử lý failure sau khi publish (không giả định rollback tự động).
- [ ] Không chạy deploy vào production chỉ để thử nghiệm bài học.

## 21. Bài tập thực hành

### Bài A — chọn phase đúng

Cho tình huống:

1. Chỉ tạo JAR để chạy local.
2. Dùng library từ Maven local cache trên cùng máy.
3. Cho team khác trên máy riêng lấy library bằng GAV.
4. Restart một ứng dụng chạy trên Kubernetes.

Chọn công cụ tương ứng. **Đáp án:** (1) `package`, (2) `install`, (3) `deploy`, (4) công cụ triển khai runtime khác Maven Deploy Plugin.

### Bài B — producer/consumer

1. Tạo đầy đủ producer `pom.xml`, `Greeter.java`, `GreeterTest.java` theo mục 8.
2. Chạy `mvn -B -ntp clean deploy`; 2 JUnit tests cần PASS.
3. Mở `repository/demo/publish/greetings-lib/1.0.0` và xác nhận JAR/POM.
4. Dùng `jar tf` kiểm tra `demo/publish/Greeter.class`.
5. Tạo consumer POM và `Main.java` ở mục 10.
6. Chạy consumer với `-Dmaven.repo.local=../consumer-local-repo`.
7. Đối chiếu stdout `Hello Maven from published library`.
8. Thử đổi dependency version thành `1.0.2` chưa tồn tại để hiểu 404/resolve failure, sau đó khôi phục `1.0.0`.
9. Giải thích tại sao consumer dùng local cache mặc định chưa phải bằng chứng mạnh về deploy.
10. Nêu vì sao phải dùng repository manager shared nếu muốn máy khác tải.

### Bài C — SNAPSHOT

1. Đổi producer `version` thành `1.0.1-SNAPSHOT`.
2. Deploy vào `snapshot-repository` của lab.
3. Xem timestamped JAR/POM và `maven-metadata.xml`.
4. Đổi consumer dependency sang `1.0.1-SNAPSHOT`.
5. Dùng `<repository><snapshots><enabled>true</enabled>` và URL đúng.
6. Chạy với cache riêng; kiểm tra SNAPSHOT metadata resolution.
7. Giải thích tại sao dependency vẫn dùng base `-SNAPSHOT` thay vì tên timestamped.
8. Nêu rủi ro khi dùng snapshot cho production release ổn định.

### Bài D — xử lý lỗi xác thực

Producer POM có:

~~~xml
<distributionManagement>
    <repository>
        <id>team-releases</id>
        <url>https://repo.example.org/repository/releases</url>
    </repository>
</distributionManagement>
~~~

CI settings chỉ có:

~~~xml
<server>
    <id>team-snapshots</id>
    <username>ci-bot</username>
</server>
~~~

Hỏi: IDs có khớp không? 401 khác 403 thế nào trong từng repository manager? Có nên hardcode token vào POM? Cần kiểm tra role, URL, secret injection và policy ra sao? Nếu 409 vì version đã tồn tại, nên làm gì?

**Gợi ý:** IDs không khớp; sửa settings mapping và quyền thay vì lộ secret. Không kết luận nguyên nhân duy nhất dựa vào status code; dùng server audit logs. Không overwrite release mà cần version mới có provenance.

### Bài E — nhiều modules

Reactor: `parent → api → service`. Chạy `mvn -pl :service -am deploy`.

Hãy giải thích:

- Những modules nào có thể được chọn và publish?
- Vì sao parent POM có thể cần publish?
- Điều gì xảy ra nếu `api` test FAIL?
- Có thể có partial publication khi module sau fail không?
- `deployAtEnd` giúp gì, giới hạn gì?
- Khi nào dùng staging/promotion thay vì upload trực tiếp?

## 22. Tổng kết

**`mvn deploy` là publish Maven artifacts để các projects/máy/nhóm khác resolve được bằng GAV**, không phải chỉ lưu file trên máy producer, cũng không phải rollout ứng dụng runtime.

~~~text
Producer source + pom.xml
        │
        ▼
mvn clean deploy
        │
        ├── compile + test + package
        ├── install (local Maven repository)
        └── deploy (JAR + POM + attached artifacts)
                         │
                         ▼
                Deployment repository
                         │
                         ▼
                Consumer POM + repositories
                         │
                         ▼
                   Maven resolve JAR
                         │
                         ▼
                 Compile/run consumer
~~~

Các quy tắc quan trọng:

- `package` tạo output, `install` đưa vào local Maven repo, `deploy` đưa tới deployment repository được chọn.
- `distributionManagement` là **đích ghi**; `repositories` là **nguồn đọc**.
- `settings.xml` quản lý secrets theo repository server ID, không đưa mật khẩu vào POM.
- SNAPSHOT và release có version policies và metadata khác nhau.
- Deploy Plugin không tự tạo attachments hay tự publish mọi file trong `target`.
- `altDeploymentRepository` hữu ích cho thử nghiệm nhưng cần kiểm soát URL/credentials.
- `deployAtEnd` có thể giảm partial publish trong multi-module nhưng **không bảo đảm transaction nguyên tử**.
- Sau deploy, phải xác minh Maven logs, repository content và **consumer độc lập**; nếu thiếu một trong ba, kết luận publication còn chưa đủ bằng chứng.

## Tài liệu chính thức

- Apache Maven — Introduction to the Build Lifecycle: https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html
- Apache Maven — Maven Deploy Plugin Usage: https://maven.apache.org/plugins/maven-deploy-plugin/usage.html
- Apache Maven — `deploy:deploy`: https://maven.apache.org/plugins/maven-deploy-plugin/deploy-mojo.html
- Apache Maven — `deploy:deploy-file`: https://maven.apache.org/plugins/maven-deploy-plugin/deploy-file-mojo.html
- Apache Maven — POM Reference, Distribution Management: https://maven.apache.org/pom.html#Distribution_Management
- Apache Maven — Security and Deployment Settings: https://maven.apache.org/guides/mini/guide-deployment-security-settings.html
- Apache Maven — Settings Reference: https://maven.apache.org/settings.html
- Apache Maven — Multiple Repositories: https://maven.apache.org/guides/mini/guide-multiple-repositories.html
- Apache Maven — Deploying via HTTP(S): https://maven.apache.org/guides/mini/guide-deployment-transports.html
- Apache Maven — Maven Install Plugin: https://maven.apache.org/plugins/maven-install-plugin/
- Apache Maven — Introduction to Dependency Mechanism: https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html
