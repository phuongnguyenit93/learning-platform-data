# Liên kết ID kho với server trong settings.xml khi Maven Install và Deploy

## 1. Bài toán: Maven biết URL kho nhưng không biết dùng tài khoản nào

Một dự án Java chạy `mvn clean package` thành công, thậm chí `mvn install` cũng thành công, nhưng khi chạy `mvn deploy` lên Nexus, Artifactory hoặc Maven repository nội bộ thì gặp `401 Unauthorized`, `403 Forbidden` hoặc lỗi không có thông tin xác thực. Một nguyên nhân phổ biến là **ID của remote deployment repository trong POM không khớp ID của cấu hình `server` trong `settings.xml`**.

Quy tắc thiết yếu:

**ID là khóa dùng để liên kết, URL là địa chỉ mạng.** Maven Deploy Plugin lấy repository cần upload từ `distributionManagement` (hoặc từ tùy chọn deploy thay thế), sau đó tìm cấu hình xác thực trong `settings.xml` theo ID. Với Maven truyền thống, hai giá trị `<id>` phải **trùng chính xác**. URL repository không được dùng như mật khẩu, và Maven không tự lựa chọn thông tin đăng nhập bằng cách so `<url>` với username.

Ví dụ một cặp khớp:

~~~xml
<!-- pom.xml: nơi deploy -->
<distributionManagement>
    <repository>
        <id>company-releases</id>
        <url>https://repo.example.invalid/repository/maven-releases/</url>
    </repository>
</distributionManagement>
~~~

~~~xml
<!-- settings.xml: cấu hình xác thực tại máy build -->
<servers>
    <server>
        <id>company-releases</id>
        <username>${env.MAVEN_REPO_USER}</username>
        <password>${env.MAVEN_REPO_TOKEN}</password>
    </server>
</servers>
~~~

`company-releases` là **ID logic**; nó không bắt buộc là hostname, không phải username và không phải `artifactId`. `https://repo.example.invalid/...` trong toàn bộ bài là **địa chỉ minh họa cố ý không dùng được** (miền `.invalid`), phải thay bằng repository thật mới deploy được. Không chạy thử với credentials production khi chưa được cấp quyền.

### Bạn sẽ nắm được

1. Phân biệt `mvn install` với `mvn deploy` và vai trò repository manager.
2. Hiểu `distributionManagement.repository.id`, `snapshotRepository.id`, `settings.servers.server.id`.
3. Biết cách Maven chọn release vs SNAPSHOT destination và đối chiếu đúng server.
4. Phân biệt **deployment repository**, **dependency repository** và **mirror**.
5. Sử dụng `settings.xml` user/global, `-s` và `-gs` một cách đúng và an toàn.
6. Dùng env vars hoặc secrets manager thay vì commit password vào `pom.xml`.
7. Biết `deploy:deploy`, `deploy:deploy-file` và `altDeploymentRepository` lấy server ID thế nào.
8. Hiểu nâng cấp bảo mật `repositoryOrigins` và `credentialScope` trên Maven 3.10+/Maven 4.
9. Chạy Java 17 lab có POM chuẩn, settings mẫu và chương trình kiểm tra ID **không đọc/hiển thị mật khẩu**.
10. Chẩn đoán lỗi 401, 403, 404, URL sai, version policy, SSL/proxy và mirror IDs.
11. Xây dựng quy trình deploy CI có scope tối thiểu, không rò rỉ token.
12. Phân biệt xác thực deploy với thông tin xác thực cho download dependencies.

## 2. Bốn khái niệm thường bị lẫn

| Khái niệm | Định nghĩa | Thường cấu hình tại |
| --- | --- | --- |
| Local repository | Cache và kho artifacts cài trên máy developer/CI | `${user.home}/.m2/repository` hoặc `settings.localRepository` |
| Remote repository để **tải** dependency | Nơi Maven resolve dependency/plugin artifacts | `repositories`, `pluginRepositories`, active settings profiles; có thể được mirror |
| Remote repository để **deploy** | Đích ghi/đẩy artifact producer tạo | `pom.xml` → `distributionManagement.repository` / `snapshotRepository` |
| Server credentials | Username/password/token/private key dùng khi kết nối một repository/server ID | `settings.xml` → `servers/server` |

Quan hệ khi deploy bình thường:

~~~text
Project pom.xml
  groupId/artifactId/version
             |
             v
   distributionManagement
      repository id = company-releases
      repository url = https://repo.example.invalid/.../maven-releases/
             |
             | id dùng để tra cứu
             v
   ~/.m2/settings.xml
      servers/server/id = company-releases
      username/password (or token)
             |
             v
 Maven Deploy Plugin / Resolver
             |
             v
  HTTP(S) PUT / upload artifact + POM + metadata
~~~

Đường download dependency:

~~~text
<repositories> hoặc <pluginRepositories>
             |
             v
       mirror selection (nếu có)
             |
             v
       effective repository ID
             |
             v
       matching <server><id>
             |
             v
       GET dependency/plugin
~~~

**Hai luồng dùng cùng khái niệm `server.id` nhưng không nhất thiết dùng cùng repository ID hoặc URL.** Trong hệ thống phổ biến, kho group/proxy được dùng để đọc, kho hosted releases/snapshots được dùng để deploy.

## 3. mvn install khác mvn deploy

`mvn install` ghi artifact vào **local Maven repository**, thường `~/.m2/repository`. Với project JAR:

~~~bash
mvn -B -ntp clean install
~~~

kết quả có thể là:

~~~text
~/.m2/repository/dev/example/deploy-id-demo/1.0.0-SNAPSHOT/
    deploy-id-demo-1.0.0-SNAPSHOT.jar
    deploy-id-demo-1.0.0-SNAPSHOT.pom
    ...
~~~

`install` thường **không cần credentials của remote repository để ghi local artifact**, mặc dù Maven vẫn có thể cần mạng/xác thực để tải dependencies và plugins khi build.

`mvn deploy` chạy lifecycle đến phase `deploy`, dùng Deploy Plugin upload artifact/POM và metadata tới remote destination:

~~~bash
mvn -B -ntp clean deploy
~~~

Nếu POM không cấu hình đích, không có `altDeploymentRepository` hợp lệ hoặc thiếu quyền, Maven có thể fail ở deploy. **Thành công của `install` không chứng minh `deploy` có quyền ghi.**

### 3.1. URL repository không được chỉ định tùy tiện

Trong Nexus/Artifactory thường có:

- Hosted releases repo: chỉ cho phiên bản release bất biến, ví dụ `1.0.0`.
- Hosted snapshots repo: nhận phiên bản `1.0.0-SNAPSHOT` và metadata snapshot.
- Proxy/cache: dùng để tải artifacts từ Maven Central hoặc upstream.
- Group/virtual repo: tập hợp nhiều repos cho **download**, thường không phải upload destination.

Vì vậy phải dùng URL hosted **được admin cho phép deploy**, không tự dùng group/proxy URL vì URL ấy trả được `mvn dependency:resolve`. `repo.example.invalid` trong ví dụ chỉ là chỗ minh họa và sẽ không kết nối được.

## 4. POM đặt repository ID ở đâu?

Đối với Maven Deploy Plugin, `distributionManagement` là nơi khai remote deploy targets:

~~~xml
<distributionManagement>
    <repository>
        <id>company-releases</id>
        <name>Company Hosted Releases</name>
        <url>https://repo.example.invalid/repository/maven-releases/</url>
    </repository>
    <snapshotRepository>
        <id>company-snapshots</id>
        <name>Company Hosted Snapshots</name>
        <url>https://repo.example.invalid/repository/maven-snapshots/</url>
    </snapshotRepository>
</distributionManagement>
~~~

Khi version của project là:

- `1.0.0` → Maven chọn `distributionManagement.repository`, tức ID `company-releases`.
- `1.0.0-SNAPSHOT` → Maven chọn `snapshotRepository` khi được khai, tức ID `company-snapshots`.
- Nếu `snapshotRepository` không được khai, Maven có thể dùng `repository` cho cả snapshots theo cơ chế plugin và policy đích. Không dựa vào fallback đó nếu tổ chức quản lý riêng snapshots và releases.

`<id>` là chuỗi logic; `<url>` chỉ endpoint. Hai cặp `id/url` khác nhau có thể trỏ tới cùng một host nhưng khác repository path. Maven không tự đoán server ID bằng URL.

**Chú ý:** chọn snapshot/release phụ thuộc **phiên bản của artifact đang deploy**, không dựa vào môi trường dev/prod hoặc branch Git mà Maven không biết.

### 4.1. Tại sao một POM có hai IDs?

Để tách quyền và chính sách: CI có thể được phép deploy snapshots tự động nhưng releases chỉ được deploy sau approval. Nếu settings có credential cho `company-snapshots` nhưng không có `company-releases`, `mvn deploy` cho `1.0.0-SNAPSHOT` có thể thành công còn bản `1.0.0` thất bại. Đó là một cấu hình có thể chủ ý, không nhất thiết là lỗi.

### 4.2. distributionManagement khác repositories

~~~xml
<repositories>
    <repository>
        <id>company-read</id>
        <url>https://repo.example.invalid/repository/maven-public/</url>
    </repository>
</repositories>
~~~

`repositories` được Maven dùng để **resolve/download dependencies**. Nó **không** thay thế `distributionManagement` cho việc deploy project hiện tại. Cũng không nhầm `pluginRepositories` (nơi tải Maven plugins) với đích deploy.

Một repository ID xuất hiện trong `repositories` có thể có server credentials trong settings để download thư viện private. Một ID ở `distributionManagement` có thể có credential khác cho upload. Tránh cấp write token cho workflow chỉ cần read.

## 5. Vị trí settings.xml và quy tắc ghép server.id

Các vị trí chuẩn:

~~~text
Global Maven settings:
  ${maven.home}/conf/settings.xml

User Maven settings:
  ${user.home}/.m2/settings.xml
~~~

Trên Linux/macOS, user settings thường là `~/.m2/settings.xml`; trên Windows là `%USERPROFILE%\.m2\settings.xml` (tùy profile/môi trường). Khi cả hai tồn tại, Maven merge settings và user-specific settings thường có mức ưu tiên cao hơn đối với phần cấu hình trùng.

Có thể chỉ định tệp khác bằng:

~~~bash
mvn -s path/to/settings.xml -B -ntp clean package
~~~

` -s ` hay `--settings` thay đường user settings Maven sử dụng. Nếu cần đường global settings riêng, dùng `-gs` hoặc `--global-settings` phù hợp CLI. Trong CI, hãy dùng đường file được tạo bảo mật bởi pipeline, không phải phỏng đoán user home.

### 5.1. Cấu trúc settings chuẩn

~~~xml
<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0"
          xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
          xsi:schemaLocation="http://maven.apache.org/SETTINGS/1.2.0
                              https://maven.apache.org/xsd/settings-1.2.0.xsd">

    <servers>
        <server>
            <id>company-releases</id>
            <username>${env.MAVEN_REPO_USER}</username>
            <password>${env.MAVEN_REPO_TOKEN}</password>
        </server>
        <server>
            <id>company-snapshots</id>
            <username>${env.MAVEN_REPO_USER}</username>
            <password>${env.MAVEN_REPO_TOKEN}</password>
        </server>
    </servers>

</settings>
~~~

Maven Settings Reference cho phép nội suy system properties và environment variables (dạng `${env.NAME}`), nhưng **không cho phép dùng properties định nghĩa trong settings profiles để nội suy chính settings file**. `MAVEN_REPO_USER` và `MAVEN_REPO_TOKEN` phải được cấp bởi máy/CI; ví dụ này không tự cấp token.

Không đưa một settings file chứa password/token thật vào Git. `settings.xml` là cấu hình **người dùng/máy/CI**, không phải nội dung của public POM. Nếu bạn cần truyền settings từ CI, tạo file tạm với permission hạn chế và xóa an toàn theo policy sau job.

### 5.2. Khớp ID phải chính xác

| POM deployment ID | settings server ID | Kết quả tra cứu |
| --- | --- | --- |
| `company-releases` | `company-releases` | Khớp |
| `company-releases` | `company-release` | Không khớp |
| `company-releases` | `Company-Releases` | Không giả định tương đương chữ hoa/thường |
| `company-snapshots` | `company-releases` | Không khớp |
| `company-releases` | `https://repo.example.invalid/...` | Không khớp; URL không phải ID |

Mỗi ID dùng làm khóa truy cập server configuration. Nếu sử dụng hai repositories với hai ID, khai riêng hai `server` entries hoặc dùng cơ chế aliases phù hợp với **phiên bản Maven hỗ trợ**. Không “sửa nhanh” bằng việc cho tất cả repositories dùng một write credential rộng quyền.

### 5.3. servers không nằm bên trong profile

Maven Settings Model có `servers` ở cấp con trực tiếp của `settings`. Settings profiles thường chứa activation, repositories, pluginRepositories và properties; không nhét:

~~~xml
<profiles>
    <profile>
        <id>publish</id>
        <servers>...</servers>
    </profile>
</profiles>
~~~

rồi kỳ vọng Maven đọc các server credentials. Đây không phải layout `settings.xml` hợp lệ cho `servers`.

### 5.4. Server ID không phải Maven coordinates

ID `company-releases` không cần trùng `groupId=dev.example`, `artifactId=deploy-id-demo`, `distributionManagement.name`, hostname hoặc server username. Hãy chọn ID ngắn, nhất quán, có tài liệu và phân biệt rõ quyền.

## 6. Lab có thể chạy: Java 17 + Maven Deploy Plugin + settings IDs

Lab tạo **một JAR Java 17** build được ngay tại máy (với Maven/JDK và repository tải plugins). Sau đó chạy chương trình Java kiểm tra **ID snapshot/release trong POM có xuất hiện trong settings hay không**, không cần token thật. Bước upload remote chỉ thực hiện khi bạn có repository thật và được cấp quyền.

### 6.1. Cấu trúc

~~~text
deploy-id-lab/
├── pom.xml
├── settings-example.xml
├── tools/
│   └── RepoIdCheck.java
└── src/
    ├── main/java/dev/example/deploy/HelloPublisher.java
    └── test/java/dev/example/deploy/HelloPublisherTest.java
~~~

Điều kiện:

- Java 17+; Maven 3.9.x cho lab cơ bản (hoặc bản Maven mới tương thích).
- Maven Central/mirror để tải plugins lần đầu.
- Không cần Nexus, Artifactory, token hoặc server thật để chạy `package` và `RepoIdCheck`.
- Các URL `repo.example.invalid` cố ý không hoạt động; lệnh `deploy` chỉ là hướng dẫn khi thay URL và có quyền.
- Không chạy `mvn deploy` vào endpoint lạ chỉ để xem lỗi xác thực; thử với environment staging được phép.

### 6.2. POM đầy đủ

Tạo `deploy-id-lab/pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.example</groupId>
    <artifactId>deploy-id-demo</artifactId>
    <version>1.0.0-SNAPSHOT</version>
    <packaging>jar</packaging>
    <name>Deploy ID Demo</name>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <distributionManagement>
        <repository>
            <id>company-releases</id>
            <url>https://repo.example.invalid/repository/maven-releases/</url>
        </repository>
        <snapshotRepository>
            <id>company-snapshots</id>
            <url>https://repo.example.invalid/repository/maven-snapshots/</url>
        </snapshotRepository>
    </distributionManagement>

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
                <version>3.14.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.4</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-deploy-plugin</artifactId>
                <version>3.1.4</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-clean-plugin</artifactId>
                <version>3.4.1</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`distributionManagement` tách release và snapshot. `maven-deploy-plugin:3.1.4` sẽ được Maven lifecycle gọi ở `deploy` (vì project là `jar` packaging), nhưng `mvn package` sẽ chỉ build JAR. Không có credentials trong POM. `<url>` trỏ `.invalid` nên không thể dùng để upload thật.

### 6.3. Java main

Tạo `src/main/java/dev/example/deploy/HelloPublisher.java`:

~~~java
package dev.example.deploy;

public final class HelloPublisher {
    private HelloPublisher() {
    }

    public static String message() {
        return "DEPLOY ID LAB OK";
    }

    public static void main(String[] args) {
        System.out.println(message());
    }
}
~~~

Class này không cần external runtime dependencies, chỉ JDK 17. Sẽ giúp xác minh build JAR/Java code độc lập với mọi remote deployment.

### 6.4. JUnit 5 test

Tạo `src/test/java/dev/example/deploy/HelloPublisherTest.java`:

~~~java
package dev.example.deploy;

import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

class HelloPublisherTest {
    @Test
    void printsExpectedMessage() {
        assertEquals("DEPLOY ID LAB OK", HelloPublisher.message());
    }
}
~~~

Test kiểm tra behavior Java, không chạm network hoặc repository authentication.

### 6.5. settings-example.xml

Tạo `settings-example.xml` ở project root (chỉ chứa tham chiếu env vars, **không chứa credential thật**):

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0"
          xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
          xsi:schemaLocation="http://maven.apache.org/SETTINGS/1.2.0
                              https://maven.apache.org/xsd/settings-1.2.0.xsd">
    <servers>
        <server>
            <id>company-releases</id>
            <username>${env.MAVEN_REPO_USER}</username>
            <password>${env.MAVEN_REPO_TOKEN}</password>
        </server>
        <server>
            <id>company-snapshots</id>
            <username>${env.MAVEN_REPO_USER}</username>
            <password>${env.MAVEN_REPO_TOKEN}</password>
        </server>
    </servers>
</settings>
~~~

File này được dùng ở bước kiểm tra ID tĩnh. **Không cần set env vars để chạy checker** vì checker chỉ so `<id>` và không đọc mật khẩu. Khi dùng để deploy thật với `mvn -s settings-example.xml`, hai biến env phải có giá trị thực được cấp an toàn; nếu không, xác thực có thể thất bại.

### 6.6. Build và chạy Java

Trong `deploy-id-lab`:

~~~bash
java -version
mvn -version
mvn -B -ntp clean package
~~~

Khi Maven hoạt động và dependencies có thể tải, tìm những dòng log dự kiến:

~~~text
Tests run: 1, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
~~~

Đây chỉ là những dấu hiệu kỳ vọng trong Maven log, **không phải stdout thực đã chạy tại đây**. Artifact:

~~~text
target/deploy-id-demo-1.0.0-SNAPSHOT.jar
~~~

Chạy compiled Java main từ `target/classes`:

~~~bash
java -cp target/classes dev.example.deploy.HelloPublisher
~~~

**Stdout chính xác của chương trình:**

~~~text
DEPLOY ID LAB OK
~~~

Cách này không cần Main-Class trong JAR manifest. Nếu muốn `java -jar`, phải bổ sung Main-Class bằng Maven JAR Plugin hoặc framework launcher; bài này tập trung deploy credentials, nên không thêm cấu hình ngoài phạm vi.

### 6.7. Chuyển release/snapshot

POM version hiện tại `1.0.0-SNAPSHOT` nghĩa là deploy chọn `snapshotRepository.id = company-snapshots`. Nếu đổi thành `1.0.0`, deploy chọn `repository.id = company-releases`. Cả hai IDs đều có server entries trong settings mẫu.

**Không thực hiện upload chỉ để xác minh lựa chọn ID.** Ta có thể đọc cấu hình hoặc dùng chương trình Java an toàn ở mục 7.

## 7. Checker Java 17: đối chiếu ID mà không lộ mật khẩu

Lệnh Maven có thể fail ở network hoặc credentials; trước khi deploy, ta muốn kiểm tra cấu hình cơ bản một cách **offline**. Một Java 17 command-line tool có thể đọc `pom.xml` và `settings-example.xml`, xác định POM version snapshot/release, chọn repository ID tương ứng và xem ID đó có trong `servers` hay không.

**Checker chỉ chứng minh ID match.** Nó không kiểm tra username/password/token đúng, secret đã được nội suy, ACL, hostname, HTTPS, origin policy hay khả năng kết nối. Không coi `Matching settings server: YES` là quyền deploy được xác minh.

### 7.1. Mã RepoIdCheck.java đầy đủ

Tạo `tools/RepoIdCheck.java`:

~~~java
import java.io.File;
import javax.xml.XMLConstants;
import javax.xml.parsers.DocumentBuilderFactory;
import org.w3c.dom.Document;
import org.w3c.dom.Element;
import org.w3c.dom.Node;
import org.w3c.dom.NodeList;

public final class RepoIdCheck {
    private RepoIdCheck() {
    }

    private static Document readXml(String path) throws Exception {
        DocumentBuilderFactory factory = DocumentBuilderFactory.newInstance();
        factory.setNamespaceAware(true);
        factory.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
        factory.setFeature(
                "http://apache.org/xml/features/disallow-doctype-decl",
                true);
        factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");
        return factory.newDocumentBuilder().parse(new File(path));
    }

    private static Element child(Element parent, String name) {
        for (Node n = parent.getFirstChild();
             n != null;
             n = n.getNextSibling()) {
            if (n instanceof Element e
                    && name.equals(e.getLocalName())) {
                return e;
            }
        }
        throw new IllegalArgumentException(
                "Missing XML element: " + name);
    }

    private static String content(Element e) {
        return e.getTextContent().trim();
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            System.err.println(
                    "Usage: RepoIdCheck pom.xml settings.xml");
            System.exit(2);
        }

        Document pom = readXml(args[0]);
        Document settings = readXml(args[1]);

        Element project = pom.getDocumentElement();
        String version = content(child(project, "version"));
        boolean snapshot = version.endsWith("-SNAPSHOT");
        Element dm = child(project, "distributionManagement");
        String repoName = snapshot
                ? "snapshotRepository" : "repository";
        Element repository = child(dm, repoName);
        String repositoryId = content(child(repository, "id"));

        NodeList servers =
                settings.getElementsByTagNameNS("*", "server");
        boolean found = false;
        for (int i = 0; i < servers.getLength(); i++) {
            if (servers.item(i) instanceof Element server) {
                String id = content(child(server, "id"));
                if (repositoryId.equals(id)) {
                    found = true;
                    break;
                }
            }
        }

        System.out.println("Artifact version: " + version);
        System.out.println(
                "Deployment repository id: " + repositoryId);
        System.out.println("Matching settings server: "
                + (found ? "YES" : "NO"));
        System.out.println(
                "Credential values: not inspected");

        if (!found) {
            System.exit(3);
        }
    }
}
~~~

Giải thích:

- `DocumentBuilderFactory` có namespace awareness để đọc cả POM/Settings XML có default namespace.
- `FEATURE_SECURE_PROCESSING`, disable DOCTYPE và external DTD/schema giúp tránh XML parser vô tình truy cập external entities khi nhận XML không tin cậy.
- `child` chọn direct child, thay vì vô tình lấy `<version>` hoặc `<id>` từ dependency ở cấp sâu khác.
- Checker chọn `snapshotRepository` khi version kết thúc chính xác bằng `-SNAPSHOT`; ví dụ đơn giản không xử lý Maven expressions như `${revision}` hoặc remote deployment overrides.
- Chỉ dùng `<server><id>`, không đọc `username`/`password` và không in secrets.
- Nếu thiếu ID hoặc XML sai, Java ném lỗi và exit không thành công; đó là tín hiệu kiểm tra cấu trúc, không phải xác thực remote.

**Giới hạn:** Với POM sử dụng parent, profiles, CI-friendly versions, `altDeploymentRepository` hoặc effective model phức tạp, checker nguồn XML này **không thay thế Maven effective POM/deploy plugin**. Nó phù hợp chính xác với lab đã trình bày.

### 7.2. Biên dịch và chạy

Tại `deploy-id-lab` sau khi `mvn package` đã tạo `target/`:

~~~bash
javac -d target/id-check tools/RepoIdCheck.java
java -cp target/id-check RepoIdCheck pom.xml settings-example.xml
~~~

**Stdout chính xác cho POM/settings ví dụ:**

~~~text
Artifact version: 1.0.0-SNAPSHOT
Deployment repository id: company-snapshots
Matching settings server: YES
Credential values: not inspected
~~~

Khi đổi version trong `pom.xml` từ `1.0.0-SNAPSHOT` thành `1.0.0` mà giữ settings:

~~~text
Artifact version: 1.0.0
Deployment repository id: company-releases
Matching settings server: YES
Credential values: not inspected
~~~

Nếu xóa `server` ID `company-snapshots` trong file settings thử nghiệm, checker in `NO` và exit code `3`. **Không sửa settings production chỉ để tạo lỗi demo**.

### 7.3. Tại sao đây là kiểm tra hữu ích nhưng chưa đủ?

Nó tránh sai sót `company-snapshot` vs `company-snapshots` hoặc `Company-Releases` vs `company-releases` trước khi CI thử upload. Nhưng credential có thể chưa được cấp, hết hạn, không có quyền write, bị origin restriction hoặc URL có lỗi; chỉ một **deploy thật trong môi trường được phép** mới kiểm tra được đủ những điều kiện đó.

## 8. Cách Maven chọn server khi download dependencies

Một project có thể khai dependency repo:

~~~xml
<repositories>
    <repository>
        <id>public-internal</id>
        <url>https://repo.example.invalid/repository/maven-public/</url>
    </repository>
</repositories>
~~~

Nếu repository cần read authentication và không có mirror, Maven tìm `settings.servers.server.id=public-internal` để kết nối. Đây là **download repository**, không phải đích `distributionManagement` của `mvn deploy`.

### 8.1. Mirror có ID riêng

Một cấu hình mirror cho Maven Central trong `settings.xml`:

~~~xml
<mirrors>
    <mirror>
        <id>company-read-mirror</id>
        <mirrorOf>central</mirrorOf>
        <url>https://repo.example.invalid/repository/maven-public/</url>
    </mirror>
</mirrors>

<servers>
    <server>
        <id>company-read-mirror</id>
        <username>${env.MAVEN_READ_USER}</username>
        <password>${env.MAVEN_READ_TOKEN}</password>
    </server>
</servers>
~~~

**Khi Maven dùng mirror**, credentials được tra theo **mirror ID** (`company-read-mirror`), không phải mặc định `central` của repository gốc. `mirrorOf=central` xác định **repository nào được thay thế**, không phải tên server credentials. Mirror `id` cũng không nên trùng `mirrorOf`.

`mirrorOf=*` hoặc `external:*` có thể ảnh hưởng rất nhiều dependency repositories; cấu hình sai có thể khiến build không tải được plugin/dependency. Maven chọn **tối đa một mirror matching** cho một repository, không tự gộp nhiều mirrors thành một kho aggregate. Muốn kết hợp nhiều upstream, dùng repository manager.

### 8.2. Deploy và mirror không có cùng mục đích

Dùng mirror đọc `company-read-mirror` **không làm deploy plugin tự upload vào URL mirror**. `distributionManagement`/deploy overrides vẫn chọn upload destination. Đừng dùng token download cho upload; quyền tối thiểu là nguyên tắc quan trọng.

### 8.3. Một server ID có thể dùng cho nhiều repository?

Về kỹ thuật, nhiều repository definitions có thể cùng `id`, nhưng đó là cấu hình dễ gây nhầm lẫn hoặc chuyển credentials sai nơi. Với Maven 3.10+ và Maven 4, server credentials còn có origin binding (mục 11). Nên dùng **mỗi quyền/đích riêng một ID rõ ràng**, hoặc cấu hình aliases mới nếu thực sự chia sẻ credentials theo policy.

## 9. Deploy:deploy-file và alternate deployment repository

### 9.1. deploy:deploy-file

Khi có sẵn JAR bên ngoài Maven project, Maven Deploy Plugin hỗ trợ:

~~~bash
mvn -B -ntp org.apache.maven.plugins:maven-deploy-plugin:3.2.0:deploy-file -Dfile=vendor-lib-1.0.0.jar -DgroupId=dev.example.vendor -DartifactId=vendor-lib -Dversion=1.0.0 -Dpackaging=jar -DrepositoryId=company-releases -Durl=https://repo.example.invalid/repository/maven-releases/
~~~

Đây là **cú pháp minh họa**, không chạy được nếu file JAR không tồn tại, URL vẫn là `.invalid` hoặc không có credentials. Điểm chính: `-DrepositoryId=company-releases` phải trùng `settings.servers.server.id`; `-Durl` là endpoint upload độc lập. Nếu có POM đầy đủ của artifact, `-DpomFile=...` giúp phát hành dependency metadata chính xác hơn thay vì một POM tối giản được tự sinh.

**Không nhập username/password vào command line.** CLI args có thể lộ qua shell history, process listing hoặc CI logs.

### 9.2. altDeploymentRepository với Maven Deploy Plugin 3.x

Bạn có thể override upload destination cho project:

~~~bash
mvn -B -ntp clean deploy -DaltDeploymentRepository=company-staging::https://repo.example.invalid/repository/staging/
~~~

Trong Deploy Plugin **3.x**, format là:

~~~text
id::url
~~~

Ở đây `company-staging` là repository ID để Maven tra settings `server.id`; URL là đích staging. Cần thêm `<server><id>company-staging</id>...` với credentials hợp lệ nếu staging yêu cầu authentication.

Trong Deploy Plugin **2.x** cũ, syntax thường là `id::layout::url` (ví dụ `id::default::url`); từ 3.0 đã bỏ thành phần layout vì chỉ còn Maven 2 repository layout. **Đừng trộn hai cú pháp**.

Có hai overrides liên quan:

~~~text
-DaltReleaseDeploymentRepository=id::url
-DaltSnapshotDeploymentRepository=id::url
~~~

Chúng có thể thay riêng release/snapshot destinations. Với những overrides đó, ID thực sự dùng để tìm credentials là ID **sau override**, không nhất thiết ID trong `distributionManagement`. Đây là lý do đọc POM thôi có thể không đủ khi CI đang truyền `-DaltDeploymentRepository`.

### 9.3. Các cảnh báo bảo mật khi override URL

Một người có thể cấu hình alternate repository với ID đã có credentials nhưng URL khác. Điều này tiềm ẩn rủi ro gửi token tới host không mong muốn. Các bản Maven/Deploy Plugin mới có cơ chế hạn chế việc tái sử dụng credentials khác origin. **Không tắt cơ chế bảo vệ bằng các flag override bảo mật chỉ để làm cho lệnh chạy qua**; xem mục 11 và kiểm tra URL đúng repository được ủy quyền.

## 10. Quản lý credentials: tránh đưa secrets vào source hoặc logs

### 10.1. Cấp credentials cho Maven settings

Settings reference cho phép hai nhóm:

- HTTP(S) username/password hoặc token trong phần `username`/`password` theo quy định của repository manager.
- SSH/private key/passphrase khi transport phù hợp; nếu dùng private key, không cấu hình password theo cách khiến Maven bỏ qua key.

Không phải mọi hệ thống dùng cùng trường/token syntax. Một số repository managers nhận token như password với username thật hoặc service account; phải tuân theo hướng dẫn của nhà cung cấp. Không tự giả định user là `token` trong mọi hệ thống.

### 10.2. Environment variable interpolation

Ví dụ:

~~~xml
<server>
    <id>company-snapshots</id>
    <username>${env.MAVEN_REPO_USER}</username>
    <password>${env.MAVEN_REPO_TOKEN}</password>
</server>
~~~

Maven có thể nội suy các env vars khi đọc settings. Trong CI, pipeline cần inject token tại runtime. Nếu env var vắng mặt, chuỗi chưa giải hoặc giá trị rỗng có thể dẫn tới lỗi xác thực; **không coi settings XML hợp lệ là bằng chứng secret đã được cấp**.

Environment variables là cơ chế truyền secrets tiện lợi nhưng không tự an toàn tuyệt đối: người có quyền đọc process/environment hoặc log/debugging sai có thể thu được. Giới hạn người truy cập CI jobs, dùng masked/protected secret variables, short-lived tokens, rotation và phân tách scope read/write.

### 10.3. Maven 3 password encryption

Maven 3 có cơ chế mã hóa mật khẩu `settings.xml` dùng `settings-security.xml` và master password. Hướng dẫn chính thức thừa nhận đây ở mức **obfuscation-grade**, không thay thế secret manager; người có được file liên quan có thể giải mã. Với Maven 4, hệ mã hóa thay đổi và có công cụ `mvnenc`; không dùng chỉ dẫn Maven 3 nguyên xi cho Maven 4.

Không ghi literal token, encrypted master password hoặc secrets vào README, bug report, screenshot hoặc Git. Giữ permissions của user settings hạn chế, ví dụ `chmod 600 ~/.m2/settings.xml` trên POSIX nếu phù hợp.

### 10.4. Phân quyền

- **Read token** dùng để tải dependencies/build.
- **Snapshot deploy token** được phép ghi hosted snapshots.
- **Release deploy token** chỉ dùng trong release workflow được phê duyệt.
- Token CI không nên có quyền admin repository manager.
- Server credentials do `settings.xml` cung cấp; URL và ID repository được cấu hình công khai theo policy, **nhưng không chứa secret trên URL/query string**.

### 10.5. Logging và debug an toàn

`mvn -X` và `help:effective-settings` có thể tạo output nhạy cảm hoặc ít nhất phơi bày cấu trúc repository/settings. Khi debug:

1. Dùng log bình thường trước; kiểm tra `repositoryId` và URL **đã được cho phép**.
2. Nếu cần effective-settings, chỉ chạy trong môi trường bảo mật và **không publish nguyên output**.
3. Không đặt token trong `-Dpassword=...`, `curl -u ...` hoặc CLI args được log.
4. Khi cần chia sẻ logs, redaction usernames, tokens, host nội bộ và proxy data.
5. Nếu token vô tình lộ, thu hồi/rotate theo quy trình và đánh giá phạm vi truy cập.

## 11. Maven 3.10+/Maven 4: credentials còn được giới hạn theo origin

Một điểm bảo mật cần biết khi nâng phiên bản Maven: theo tài liệu Maven Settings hiện hành, **từ Maven 3.10.0 và Maven 4.0.0**, các server credentials dùng bởi Maven Resolver có thể bị ràng buộc theo **origin** của repository, tức `scheme://host[:port]`.

Ở các phiên bản trước, việc tìm credentials chủ yếu dựa trên matching ID. Điều này có nguy cơ khiến một POM không tin cậy khai repository ID giống server có token rồi chuyển URL sang host khác. Cơ chế mới giúp giảm rủi ro đó.

### 11.1. repositoryOrigins trong settings model 1.3.0

Với Maven **3.10.0+ hoặc Maven 4 tương thích**, cấu hình user settings có thể khai rõ origin được phép:

~~~xml
<settings xmlns="http://maven.apache.org/SETTINGS/1.3.0"
          xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
          xsi:schemaLocation="http://maven.apache.org/SETTINGS/1.3.0
                              https://maven.apache.org/xsd/settings-1.3.0.xsd">
    <servers>
        <server>
            <id>company-releases</id>
            <username>${env.MAVEN_REPO_USER}</username>
            <password>${env.MAVEN_REPO_TOKEN}</password>
            <repositoryOrigins>
                <repositoryOrigin>https://repo.example.invalid</repositoryOrigin>
            </repositoryOrigins>
        </server>
    </servers>
</settings>
~~~

Đây là **ví dụ riêng dành cho Maven versions hỗ trợ schema 1.3.0**, không copy vào settings 1.2.0 của lab Maven 3.9.x. `repositoryOrigin` là **origin**, không phải full URL: chỉ scheme, host và port nếu cần; không thêm `/repository/maven-releases/`, query hay fragment.

Tài liệu Maven nói `repositoryOrigins` được cộng vào origins Maven biết từ active settings profile repositories/mirrors, không thay thế chúng. Maven 3.9.16 và cũ hơn có thể không nhận tag này (báo unrecognized tag) và giữ hành vi ID matching cũ.

### 11.2. credentialScope

Maven cung cấp property `maven.repository.credentialScope`:

| Giá trị | Ý nghĩa |
| --- | --- |
| `origin` (mặc định mới) | Chỉ dùng credentials tại origins đã biết; trường hợp server chưa xác định origin có thể cảnh báo và dùng behavior tương thích |
| `strict` | Không dùng credentials khi không xác định được origin hợp lệ |
| `id` | Quay về matching theo ID kiểu cũ, giảm bảo vệ |

Không khuyến khích đặt `-Dmaven.repository.credentialScope=id` chỉ để “chữa 401”; đó là **hạ cấp bảo vệ credentials**. Thay vào đó, xác nhận server ID, đích URL đúng, cập nhật Maven/settings model và khai `repositoryOrigins` theo origin được ủy quyền nếu cần.

### 11.3. Vì sao distributionManagement trong POM có thể gây warning?

Maven khởi tạo session trước khi đọc đầy đủ tất cả POMs. Origins từ repositories trong `settings.xml` active profiles và mirrors có thể được biết sớm; URL `distributionManagement` trong source POM thì không nhất thiết có sẵn ở thời điểm ấy. Trong mode `strict`, credentials cho một repository chưa có trusted origin có thể bị từ chối. `repositoryOrigins` trong user settings là cách mô tả host được tin cậy mà **không thay đổi POM**.

Chú ý cơ chế này áp dụng **Maven Resolver credentials**, không nhất thiết tới plugin nào tự đọc `settings.xml` rồi làm custom authentication (ví dụ một số trường hợp SCM credentials). Hãy đọc tài liệu plugin tương ứng.

## 12. CI/CD: cấp settings đúng mà không commit password

Một pipeline an toàn thường làm theo trình tự:

1. Checkout source và xác định version là release hay SNAPSHOT.
2. Cấu hình JDK/Maven được pin; ưu tiên Maven Wrapper khi repo có.
3. Secrets manager cấp read token/deploy token được scope theo job/branch/environment.
4. CI tạo/cấp `settings.xml` bên ngoài repository với `server.id` khớp đích deploy thật. File chứa env interpolation hoặc secret do runner quản lý, không được đưa vào artifact.
5. Chạy `mvn -B -ntp -s <path> clean verify` trước, không bypass test.
6. Kiểm tra POM effective/version/repository ID và quyền project trước khi deploy.
7. Chạy `mvn -B -ntp -s <path> deploy` trong job được phê duyệt.
8. Kiểm tra repository manager hiển thị đúng GAV, POM, checksums, metadata, version policy.
9. Log không chứa token, archive logs/artifacts theo retention policy, rotate/thu hồi secrets nếu bị lộ.
10. Với release version immutable, không dùng lại GAV cho bytecode khác.

Ví dụ CLI chỉ minh họa đường settings được CI quản lý:

~~~bash
mvn -B -ntp -s ./ci-settings.xml clean verify
mvn -B -ntp -s ./ci-settings.xml deploy
~~~

`ci-settings.xml` trong ví dụ là **file do pipeline cấp**, không nhất thiết commit cùng source. Người dùng phải thay bằng path thực và chỉ chạy deploy khi đã xác minh URL/ACL. Không tự tạo `ci-settings.xml` rỗng rồi coi như đã có credentials.

### 12.1. Repositories có quyền download/private plugins

Nếu Maven phải tải plugin/dependency từ kho private trước khi chạy `deploy`, settings cũng cần authentication cho download repository IDs hoặc mirror IDs. Lỗi xảy ra **trước phase deploy** có thể không liên quan credential của upload destination, dù cùng Maven command `mvn deploy`.

## 13. Chẩn đoán lỗi theo triệu chứng

### 13.1. 401 Unauthorized

Khả năng:

- `server.id` sai hoặc settings không được load.
- Username/token sai, hết hạn, không được inject từ CI.
- Token có format/header khác với yêu cầu repository manager.
- Origin restriction của Maven mới ngăn gửi credentials.
- Proxy/auth gateway làm thay đổi request.

Cách xử lý: xác định upload repository ID thực tế sau overrides; kiểm tra settings user/global hoặc `-s` path, env var tồn tại (không in giá trị), host được phép và repo auth policy. Đừng lập tức yêu cầu admin cấp toàn quyền.

### 13.2. 403 Forbidden

Có thể đã authentication thành công nhưng không có quyền deploy vào repo/path đó; hoặc repository policy chặn hành động. Ví dụ token snapshots chỉ được ghi snapshots, không được ghi releases. Kiểm tra ACL/roles, hosted repo và version policy cùng admin.

401 và 403 **không phải quy tắc tuyệt đối** để phân biệt thiếu credentials hay thiếu quyền vì proxy/repository manager có thể trả codes khác nhau.

### 13.3. 404 Not Found

URL path repository sai, endpoint là UI page thay vì Maven deploy endpoint, reverse proxy route sai hoặc repo đã đổi tên. Một download URL `/repository/maven-public/` có thể tồn tại nhưng không phải upload URL `/repository/maven-releases/`.

### 13.4. 405 Method Not Allowed hoặc 409 Conflict

Có thể gửi PUT tới endpoint không hỗ trợ deploy, repo read-only, version policy hoặc artifact immutable đã tồn tại. Không dùng retry vô hạn hoặc “xóa bản release cũ” khi chưa được policy cho phép.

### 13.5. 400 Bad Request

Repository manager có thể từ chối vì snapshot/release mismatch, metadata/POM chưa hợp lệ, artifact coordinates/filename không phù hợp hoặc rule validation. Xem response chi tiết đã được redaction và server logs.

### 13.6. SSL/TLS hoặc proxy error

`PKIX path building failed`, certificate truststore, hostname mismatch, proxy authentication hoặc DNS timeout không sửa được bằng đổi `server.id` tùy tiện. Kiểm tra HTTPS certificate chain, truststore/JDK, VPN/proxy settings, server hostname và network policy. **Không tắt xác thực SSL để “thử tạm” trên CI/prod**.

### 13.7. Missing distributionManagement

Lỗi kiểu “repository element was not specified” xuất hiện khi `deploy` không có đích. Khai `distributionManagement` trong POM (hoặc cấu hình alternate deployment repository có chủ đích), không thêm `<repositories>` rồi kỳ vọng nó được dùng làm upload.

### 13.8. Cấu hình alternate repository nhưng server ID không khớp

Command:

~~~bash
mvn deploy -DaltDeploymentRepository=staging-repo::https://repo.example.invalid/repository/staging/
~~~

sẽ dùng ID `staging-repo`, **không phải** `company-releases` trong POM. Nếu settings chỉ có `company-releases`, Maven không tự chuyển credentials. Thêm đúng server ID/credential theo permission được cấp hoặc sửa override cho khớp đích hợp lệ.

### 13.9. SNAPSHOT sang releases hoặc release sang snapshots

Kiểm tra `project.version` và `distributionManagement`; repository manager có thể từ chối một `-SNAPSHOT` trong hosted releases hoặc release bất biến trong snapshots. Đừng sửa version của JAR sau build rồi chỉ đổi `<url>`; GAV, POM, artifact contents và metadata phải nhất quán.

### 13.10. Parent POM, profiles và property override

`distributionManagement` có thể được kế thừa từ parent hoặc cấu hình khác thay đổi deploy parameters. Nếu POM con không khai repo, hãy xem **effective POM** và active profiles. Nhưng nhớ `help:effective-pom` là thông tin build; đừng in effective-settings có secrets trong log công khai.

### 13.11. Build thành công trên laptop nhưng CI lỗi

CI có thể dùng một user home khác, không có `~/.m2/settings.xml` của developer, dùng `-s` path khác, env vars chưa được inject, branch không có quyền truy cập protected secrets, Maven/JDK version khác hoặc network firewall. Tập trung kiểm tra **CI runtime identity** và selected repository ID.

### 13.12. Config servers đúng nhưng vẫn không upload

Một ID khớp chỉ là điều kiện cấu hình, không phải xác nhận quyền. Cần xét URL endpoint, permissions, repo type, certificate, network, token scope, snapshot/release policy, origin restrictions, transport và deploy plugin version.

### 13.13. MirrorOf trỏ central nhưng download vẫn 401

Nếu mirror ID là `company-read-mirror`, settings server phải khai ID đó; chỉ có server `central` không phải lúc nào được dùng. Kiểm tra `mirrors` được merge từ user/global settings và active profiles; tránh tạo mirror ID trùng ID repo gốc.

### 13.14. Server credential ở nhầm XML cấp

`servers` phải là child của `settings`. Nếu đặt trong `profile`, Maven settings parser có thể bỏ qua hoặc báo invalid/unrecognized. Kiểm tra XML schema và cấu trúc thay vì thử nhiều passwords khác nhau.

### 13.15. settings.xml được tải nhưng env var chưa có

Một XML `<password>${env.MAVEN_REPO_TOKEN}</password>` có thể được parse bình thường trong khi token thực tế không tồn tại ở job. Kiểm tra **sự tồn tại** của env var bằng cơ chế CI an toàn mà không echo value, và kiểm tra branch/PR restrictions. Không log username/token để “xem đã nội suy chưa”.

## 14. Công cụ kiểm tra Maven config không phát tán secrets

Có thể dùng Help Plugin để xem **deploy repository ID** trong effective project model:

~~~bash
mvn -q -DforceStdout help:evaluate -Dexpression=project.version
mvn -q -DforceStdout help:evaluate -Dexpression=project.distributionManagement.repository.id
mvn -q -DforceStdout help:evaluate -Dexpression=project.distributionManagement.snapshotRepository.id
~~~

Các lệnh này hữu ích nhưng cần lưu ý: `help:evaluate` có thể phản ánh model/profiles khác với lựa chọn cuối sau alternate-deploy overrides; và Maven vẫn có thể in warnings hoặc download logs. Không in raw settings passwords.

Nếu muốn xem setting ID có thực sự tồn tại, chương trình `RepoIdCheck` của lab là công cụ tối giản **đọc XML ở phạm vi hai file nguồn**. Với settings merge từ nhiều nguồn, aliases mới, profiles và Maven 4, nó không thay thế `effective-settings` hoặc chính Resolver.

`help:effective-settings` hỗ trợ điều tra cấu hình Maven, nhưng trong môi trường chứa secrets hãy chỉ sử dụng nội bộ, giữ logs riêng tư, không paste output đầy đủ lên issue tracker. Một số versions/plugins có cơ chế masking; **không phụ thuộc masking là tuyệt đối**.

## 15. Multi-module, inherited deploy URL và quyền theo module

Trong multi-module Maven reactor:

~~~text
workspace/
├── pom.xml             (parent/aggregator)
├── core/pom.xml        (packaging=jar)
└── api/pom.xml         (packaging=jar)
~~~

Parent có thể định nghĩa `distributionManagement`. Những child modules có thể kế thừa và deploy từng artifact tới cùng repo sau reactor build. Các lưu ý:

- Tất cả modules deploy phải có version/GAV phù hợp repository policy.
- Có thể một module snapshot và một module release khác nhau? Trong một reactor thông thường nên thống nhất policy, nhưng xét POM/version thực tế từng module.
- `maven-deploy-plugin` có `deployAtEnd` để điều phối deploy ở cuối reactor; cấu hình sai không sửa được credential errors.
- Nếu một child override `distributionManagement` hoặc build dùng `-DaltDeploymentRepository`, hãy kiểm tra **repository ID thực sự** mà plugin chọn.
- Không khai server credentials ở parent POM rồi hy vọng Maven dùng: chúng thuộc `settings.xml`.
- Một CI agent build các modules nhưng chỉ được cấp quyền snapshots có thể build thành công rồi fail ở release deploy; đó là security policy cần được thiết kế, không phải bug Maven.

## 16. Các bài tập tình huống có đáp án

**1.** `distributionManagement.repository.id=corp-release`, `settings.server.id=corp-releases`. Vì sao deploy có thể 401?

**Đáp án:** ID khác nhau; Maven không tự so sánh “gần giống” hoặc URL để lấy credential. Phải khớp đúng ID được khai và được quyền.

**2.** POM dùng `1.2.0-SNAPSHOT`, khai release ID `corp-release` và snapshot ID `corp-snapshot`. Maven dùng server nào?

**Đáp án:** `corp-snapshot` nếu snapshotRepository được khai và không có override; settings server cùng ID cần tồn tại.

**3.** `mvn clean install` thành công, `mvn clean deploy` thất bại. Có nhất thiết JAR bị lỗi?

**Đáp án:** không. Install ghi local repository, deploy cần remote destination và quyền; kiểm tra phase/lỗi thực tế.

**4.** POM có `<repositories>` trỏ tới Nexus. Vậy `mvn deploy` tự dùng đó?

**Đáp án:** không. Deploy dùng `distributionManagement` hoặc override của Deploy Plugin.

**5.** Mirror có `id=corp-proxy` và `mirrorOf=central`. Credentials trong settings đặt `central` có chắc được dùng?

**Đáp án:** không. Khi mirror được chọn, credentials thường được tra theo mirror ID `corp-proxy`.

**6.** `-DaltDeploymentRepository=stage::https://...` có dùng credentials của `company-releases` trong POM không?

**Đáp án:** không theo ID đó. Cần `settings.server.id=stage` (hoặc cơ chế aliases hợp lệ được cấu hình), và URL được phép.

**7.** Tại sao Maven Deploy Plugin 3.x dùng `id::url`?

**Đáp án:** từ bản 3.0 bỏ phần layout cũ của `id::layout::url` vì Maven 3 dùng repository layout hiện hành.

**8.** Có nên ghi `-Dpassword=mytoken` vào CI command line để sửa 401?

**Đáp án:** không. Dễ lộ qua shell history/logs/process listing; dùng settings và secret manager.

**9.** `server.id` đúng nhưng Maven 3.10+ ở `credentialScope=strict` vẫn từ chối gửi token. Cần làm gì?

**Đáp án:** kiểm tra origin được phép và `repositoryOrigins` trong user settings model 1.3.0; không hạ cấp sang `id` vô điều kiện.

**10.** Tại sao `repositoryOrigin` chỉ ghi `https://repo.example.invalid`, không ghi `/repository/releases/`?

**Đáp án:** origin gồm scheme, host và port, không gồm URL path/query/fragment.

**11.** Vì sao `RepoIdCheck` báo YES nhưng deploy thực vẫn lỗi 403?

**Đáp án:** checker chỉ kiểm ID trong XML; token có thể không có quyền upload hoặc repository policy chặn.

**12.** `settings.xml` có thể sử dụng `${env.MAVEN_REPO_TOKEN}` không?

**Đáp án:** có theo Maven Settings Reference; env phải thực sự được inject, không nên lưu token literal vào POM.

**13.** Nếu repository URL là `repo.example.invalid`, có thể dùng token thật để xác minh id match không?

**Đáp án:** không cần và không nên. Miền `.invalid` cố ý không hoạt động; dùng offline checker rồi đổi sang endpoint được phép.

**14.** Khi `deploy-file` bên ngoài project, tham số chọn settings credential là gì?

**Đáp án:** `-DrepositoryId`, còn `-Durl` là upload destination.

**15.** Với Maven 3, mã hóa password trong settings.xml có thay thế secret manager không?

**Đáp án:** không; tài liệu Maven mô tả encryption cũ là obfuscation-grade. Dùng quyền file, CI secret manager và rotation.

## 17. Checklist trước khi bật job deploy

- [ ] Đã phân biệt install local và deploy remote.
- [ ] `distributionManagement.repository.id` đúng cho release.
- [ ] `distributionManagement.snapshotRepository.id` đúng cho SNAPSHOT.
- [ ] Repository URLs chỉ tới hosted upload endpoints được admin cho phép.
- [ ] `settings.servers.server.id` khớp chính xác ID được chọn.
- [ ] Với CLI override, ID trong `altDeploymentRepository` hoặc `repositoryId` được dùng thật.
- [ ] `settings.xml` được load từ đúng user/global path hoặc `-s` trong CI.
- [ ] `servers` nằm đúng cấp trong XML, không đặt trong settings profile.
- [ ] Env vars/token đã được inject qua secret manager, không echo giá trị.
- [ ] Không chứa credentials trong `pom.xml`, Git, CLI flags hoặc URL.
- [ ] Quyền read/write được phân tách và giới hạn theo environment.
- [ ] Mirror download dùng mirror ID thích hợp, không nhầm deploy ID.
- [ ] Java/Maven/plugin versions và profiles được kiểm soát.
- [ ] Nếu dùng Maven 3.10+/4, đã kiểm tra credential origin/strict settings.
- [ ] HTTPS, certificate chain và network/proxy hoạt động an toàn.
- [ ] Artifact version phù hợp release/snapshot policy và immutable release rules.
- [ ] POM/artifact metadata và checksum được repo nhận đúng.
- [ ] Không phụ thuộc build package PASS để kết luận deploy credentials đúng.
- [ ] Logs/settings không bị chia sẻ công khai khi chứa thông tin nhạy cảm.
- [ ] CI có quy trình rotate/revoke token khi hết hạn hoặc lộ.
- [ ] Sau deploy, xác minh artifact/POM có thể download bởi consumer được phép.

## 18. Tài liệu tham khảo chính thức

1. [Apache Maven — Settings Reference](https://maven.apache.org/settings.html): `servers`, `server.id`, user/global settings, mirrors, env interpolation, password encryption, aliases và `repositoryOrigins`.
2. [Apache Maven — Security and Deployment Settings](https://maven.apache.org/guides/mini/guide-deployment-security-settings.html): repository ID trong `distributionManagement` phải khớp ID của server credentials.
3. [Apache Maven — Deploying over HTTP, FTP and SSH](https://maven.apache.org/guides/mini/guide-deployment-transports.html): khai deployment destination và server authentication.
4. [Maven Deploy Plugin 3.1.4 — deploy:deploy](https://maven.apache.org/plugins/maven-deploy-plugin/deploy-mojo.html): `altDeploymentRepository`, snapshot/release alternatives, deployAtEnd.
5. [Maven Deploy Plugin — deploy:deploy-file](https://maven.apache.org/plugins/maven-deploy-plugin/deploy-file-mojo.html): `repositoryId`, `url`, `file` và `pomFile`.
6. [Apache Maven — Using Mirrors for Repositories](https://maven.apache.org/guides/mini/guide-mirror-settings): `mirror.id`, `mirrorOf` và selection logic.
7. [Apache Maven — Password Encryption](https://maven.apache.org/guides/mini/guide-encryption.html): Maven 3 password handling và giới hạn obfuscation.
8. [Apache Maven 3.10 Settings Model](https://maven.apache.org/ref/3.10.0/maven-settings/settings.html): schema `1.3.0`, `repositoryOrigins` và server aliases.
9. [Apache Maven — What's New in Maven 4](https://maven.apache.org/whatsnewinmaven4.html): cơ chế encryption mới và khác biệt Maven 4.
10. [Apache Maven — Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html): phase install/deploy.
11. [Maven Help Plugin — help:evaluate](https://maven.apache.org/plugins/maven-help-plugin/evaluate-mojo.html): đọc `project.version` và effective model properties.
12. [Maven Deploy Plugin — Troubleshooting Network Issues](https://maven.apache.org/plugins/maven-deploy-plugin/examples/deploy-network-issues.html): phân biệt network errors và cấu hình deploy.
