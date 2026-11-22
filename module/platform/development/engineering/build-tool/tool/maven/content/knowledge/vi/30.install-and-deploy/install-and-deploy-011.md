# Phân biệt Maven deploy với triển khai ứng dụng lên máy chủ

## 1. Hai chữ “deploy” dễ gây nhầm lẫn

Trong công việc phát triển Java, cụm từ **“deploy ứng dụng”** thường có nghĩa đưa một phiên bản phần mềm lên môi trường chạy (VM, server, container, Kubernetes, application server…), khởi động hoặc cập nhật tiến trình, kiểm tra health và quản lý rollback.

Nhưng **`mvn deploy` trong Maven default lifecycle có nghĩa khác**: xuất bản **Maven project artifacts** (thường gồm JAR/WAR/POM và attached artifacts) lên một **Maven repository** được cấu hình. Repository là nơi để các build khác **tải và resolve dependency hoặc bản phát hành**; không phải bản thân tiến trình ứng dụng đang phục vụ người dùng.

Ví dụ:

~~~bash
mvn -B -ntp clean deploy
~~~

mặc định là một lệnh **build + publication**. Nó có thể biên dịch, chạy test, đóng gói, install local, rồi upload artifacts tới kho Maven từ xa. Nó **không mặc nhiên** SSH vào server, chép JAR vào `/opt/app`, khởi động `java -jar`, cập nhật Docker/Kubernetes hay kiểm tra HTTP endpoint.

Ngược lại, một pipeline CD có thể triển khai ứng dụng bằng việc tải artifact đã xuất bản, kiểm tra checksum/provenance, tạo container image, cập nhật workload, rồi chạy smoke test và rollback. Những bước ấy **không phải hành vi mặc định của Maven Deploy Plugin**.

Sau bài học, bạn sẽ:

1. Phân biệt **Maven artifact publication** với **application deployment**.
2. Giải thích `install`, `deploy` và Maven Deploy Plugin trong default lifecycle.
3. Cấu hình `distributionManagement`, `settings.xml` và chọn release/SNAPSHOT repository.
4. Hiểu phiên bản 3.x của `altDeploymentRepository=id::url` và `deploy:deploy-file`.
5. Tạo một **ứng dụng HTTP Java 17 chỉ dùng JDK**, chạy JAR thực sự bằng `java -jar`.
6. Xuất bản chính JAR/POM ấy vào một **Maven file repository thử nghiệm**, không đụng môi trường production.
7. Mô phỏng việc **triển khai JAR sang thư mục server** và chạy health check riêng.
8. Biết cách thiết kế CI/CD với artifact promotion, credentials, approvals, health checks và rollback.
9. Chẩn đoán lỗi “mvn deploy thành công nhưng website vẫn chạy phiên bản cũ”.

Bài dùng **JDK 17+**, **Maven 3.9.x**, Maven Deploy Plugin **3.1.4** (ghim để tái lập ví dụ). Phiên bản plugin 3.1.4 không nhất thiết là bản mới nhất tại thời điểm bạn học; hãy xem tài liệu đúng version trong dự án.

## 2. Một bảng phân biệt nhanh

| Tiêu chí | Maven `deploy` | Triển khai ứng dụng (application deployment) |
| --- | --- | --- |
| Mục đích | Công bố artifact để các build/consumer tải được | Làm phiên bản phần mềm hoạt động trong môi trường mục tiêu |
| Nơi đến | Maven artifact repository | VM, host, container runtime, Kubernetes, application server, serverless… |
| Đối tượng | JAR, WAR, POM, source/javadoc JAR, metadata… | JAR đang chạy, image, process/service, configuration, traffic |
| Công cụ | Maven Deploy Plugin, repository transport | CI/CD, SSH, systemd, Docker, Kubernetes, Helm, GitOps, cloud deploy service… |
| Lệnh minh họa | `mvn deploy` | `java -jar app.jar`, `systemctl restart service`, `kubectl rollout…` |
| Kiểm chứng thành công | Repository lưu artifact và POM ở đúng GAV | Process/endpoint khỏe, traffic hoạt động, metrics và smoke tests đạt |
| Cần credentials gì? | Quyền publish vào Maven repository | Quyền truy cập môi trường/app runtime |
| Có đổi phiên bản đang chạy ngay không? | Không, **theo mặc định** | Có, khi rollout thành công |
| Có thể rollback bằng gì? | Publish version mới/chính sách repository; không xóa tùy tiện bản cũ | Chuyển lại artifact/image phiên bản trước, rollback workload |
| Liên quan local Maven repo? | Default lifecycle thường đi qua `install` trước `deploy` | Không nhất thiết dùng local Maven repo |
| Cần POM? | Maven publish thường gửi POM cùng artifact | Runtime Java thường không cần POM để chạy một JAR đầy đủ |

**Chú ý ngoại lệ:** Maven là công cụ gọi plugin goals. Nếu bạn cố ý bind một plugin SSH/container/deployment vào lifecycle phase `deploy`, lệnh `mvn deploy` **có thể** gây side effects lên server theo cấu hình riêng. Khi nói “`mvn deploy` không triển khai ứng dụng” ở đây, ý là **hành vi mặc định của Maven Deploy Plugin**, không phải mọi plugin tùy biến có thể chạy ở phase đó.

## 3. Hãy hình dung hai đường đi khác nhau

~~~text
                    Source code Java + POM
                              |
                              v
                     Maven clean verify
                              |
                              v
                  JAR/WAR + POM + tests
                              |
               +--------------+--------------+
               |                             |
               v                             v
      Maven deploy phase           Application delivery
               |                             |
               v                             v
     Maven artifact repository      Download/copy immutable artifact
       releases / snapshots                  |
               |                             v
               |                     Prepare config/secrets
               |                             |
               v                             v
        Other builds resolve          Start/update process
        groupId:artifactId:version            |
                                             v
                                      Health / smoke / metrics
                                             |
                                             v
                                       Traffic / rollback
~~~

Hai luồng **có thể nối với nhau**:

~~~text
Build + Maven deploy → Repository lưu artifact → CD tải artifact ấy → Server chạy artifact
~~~

Nhưng bước **publication** và bước **rollout** vẫn là hai trách nhiệm khác nhau. Một CI pipeline có thể báo `mvn deploy BUILD SUCCESS` và dừng lại ở repository; không có lý do tự động để sản phẩm ngoài production thay đổi.

## 4. Maven default lifecycle: deploy đến sau install

Maven có default lifecycle gồm nhiều phase. Các mốc quan trọng:

~~~text
validate
   |
compile
   |
test
   |
package
   |
verify
   |
install
   |
deploy
~~~

Sơ đồ đã rút gọn, không liệt kê tất cả phase trung gian. Khi chạy:

~~~bash
mvn deploy
~~~

Maven thực thi các phase trước `deploy` cần thiết theo lifecycle/packaging bindings, bao gồm những checks mà POM đã cấu hình, sau đó thực hiện deploy.

Với một project `<packaging>jar</packaging>` thông thường:

1. Compile Java source.
2. Chạy tests theo plugin cấu hình.
3. Tạo JAR trong `target/`.
4. Thực hiện các quality checks đã bind vào phase thích hợp.
5. `install` artifact và POM vào **local Maven repository**.
6. `deploy` artifact và POM lên **Maven deployment repository** được chọn.

Không phải lệnh nào cũng có cùng plugins/tests: đó là do POM, inherited configuration và active profiles. Muốn bảo đảm quality gate, phải xem actual plugin executions, không chỉ ghi `mvn deploy`.

### package, verify, install, deploy

| Lệnh | Điều chứng minh chủ yếu |
| --- | --- |
| `mvn package` | Có thể tạo artifact đóng gói ở `target/` |
| `mvn verify` | Chạy các checks được cấu hình đến `verify` |
| `mvn install` | Tạo/cài artifact và POM vào local repository |
| `mvn deploy` | Tạo/cài rồi publish artifact/POM lên Maven deployment repository |

**`deploy` không phải “install lên một Linux server”.** “Install” trong Maven cũng có nghĩa cài vào local Maven repository, **không phải cài ứng dụng thành system service**.

## 5. Maven artifact repository là gì?

Maven repository tổ chức artifacts theo coordinates, ví dụ:

~~~text
groupId:    dev.learning.release
artifactId: hello-service
version:    1.0.0
packaging:  jar
~~~

Đường dẫn release artifact theo Maven repository layout:

~~~text
dev/learning/release/hello-service/1.0.0/
├── hello-service-1.0.0.jar
└── hello-service-1.0.0.pom
~~~

Tùy repository/transport, có thể có thêm checksum files, metadata và các attached artifacts. Chỉ nêu hai file cốt lõi để hiểu trách nhiệm.

- **JAR** chứa Java classes/resources.
- **POM** mô tả project coordinates và metadata/dependency declarations để Maven consumers resolve.
- **Repository** lưu phiên bản theo GAV và phục vụ nhiều build jobs/consumers.
- **Application server** chạy code và xử lý requests/jobs; nó không nhất thiết hiểu Maven coordinates hay POM.

Artifact repository có thể là Maven Central, một Nexus/Artifactory riêng của tổ chức, một repository service trên cloud hoặc một repository local-file dùng **chỉ cho lab**.

Không trộn khái niệm **local Maven repository** (thường `~/.m2/repository`, dùng bởi Maven Resolver) với **remote/deployment repository** (điểm publication cho team). Một deployment repository có thể có URL `file://` khi thử nghiệm, nhưng vai trò trong lifecycle vẫn là **đích publish**, tách biệt khỏi local resolver cache.

## 6. Maven Deploy Plugin làm gì?

Apache Maven Deploy Plugin cung cấp hai goal quan trọng:

- **`deploy:deploy`**: xuất bản artifacts của **Maven project hiện tại** cùng POM, các attached artifacts và metadata theo cơ chế plugin/repository.
- **`deploy:deploy-file`**: xuất bản một file artifact có sẵn, khi file được xây ngoài Maven project hoặc cần publish riêng.

Với project JAR và Maven default lifecycle, goal `deploy:deploy` được bind vào phase `deploy`. Vì vậy thường gọi:

~~~bash
mvn -B -ntp clean deploy
~~~

không phải tự gõ `mvn deploy:deploy` trên một project sạch; gọi goal trực tiếp khi chưa có artifact từ `package` có thể báo không có main artifact để deploy.

### Bản thân Deploy Plugin không làm các việc sau

- Không đăng nhập vào server ứng dụng để chạy `java -jar`.
- Không tạo hoặc nâng cấp Kubernetes Deployment object.
- Không tự cấp/revoke secrets cho runtime process.
- Không đảm bảo HTTP endpoint trả 200.
- Không xoay traffic, thực hiện blue/green/canary rollout.
- Không rollback một service nếu latency tăng.
- Không có nghĩa publication đã được kiểm thử trên production.

Đây là nhiệm vụ của **application deployment/CD** hoặc plugin đặc thù được chủ động cấu hình bổ sung.

## 7. Chọn repository đích bằng distributionManagement

Trong Maven POM, vùng `<distributionManagement>` cho biết **nơi publish project artifacts**.

Ví dụ production-like (URL dùng tên miền **minh họa**, không phải server thật):

~~~xml
<distributionManagement>
    <repository>
        <id>company-releases</id>
        <name>Company Maven Releases</name>
        <url>https://repo.example.org/maven-releases</url>
    </repository>

    <snapshotRepository>
        <id>company-snapshots</id>
        <name>Company Maven Snapshots</name>
        <url>https://repo.example.org/maven-snapshots</url>
    </snapshotRepository>
</distributionManagement>
~~~

Ý nghĩa:

- `<repository>` là nơi publish **release** versions, ví dụ `1.0.0`.
- `<snapshotRepository>` là nơi publish **SNAPSHOT** versions, ví dụ `1.1.0-SNAPSHOT`.
- `<id>` là khóa nhận diện repository, liên kết credentials ở Maven `settings.xml`.
- `<url>` là endpoint của **artifact repository**, không phải endpoint `https://app.example.org/health`.
- `distributionManagement` có thể được kế thừa từ parent POM, vì thế không phải mọi module đều cần copy lại.

**Không nhầm `<repositories>` với `<distributionManagement>`:**

- `<repositories>` chủ yếu cho biết **download/resolve project dependencies** từ đâu.
- `<pluginRepositories>` phục vụ **download/resolve Maven plugins**.
- `<distributionManagement>` cho biết **publish current project artifacts** đi đâu.

Một repository có thể dùng cho cả download và publish nếu cấu hình/quyền cho phép, nhưng khai báo ở những phần này phục vụ các **mục đích khác nhau**.

## 8. Credentials nằm trong settings.xml, không hard-code trong POM

Nếu repository cần xác thực, không đặt password/token trực tiếp trong POM được commit lên Git.

Trong user Maven settings, ví dụ `~/.m2/settings.xml`:

~~~xml
<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0">
    <servers>
        <server>
            <id>company-releases</id>
            <username>ci-publisher</username>
            <password>${env.MAVEN_RELEASE_TOKEN}</password>
        </server>
        <server>
            <id>company-snapshots</id>
            <username>ci-publisher</username>
            <password>${env.MAVEN_SNAPSHOT_TOKEN}</password>
        </server>
    </servers>
</settings>
~~~

Đây là **mẫu cấu hình**, không phải credentials thật. Giá trị biến môi trường phải được cung cấp bởi secret manager của CI hoặc môi trường an toàn.

Điểm mấu chốt: ***server ID trong settings phải khớp repository ID trong distributionManagement***. Nếu POM dùng `company-releases` nhưng settings khai báo `company-release` (thiếu chữ s), Maven không tự dùng nhầm credentials.

### Security checklist của publisher

- Dùng **least-privilege credentials**: chỉ ghi đúng repository cần publish.
- Cấu hình token trong secret store, không ghi trực tiếp ở source/POM.
- Không in `settings.xml` có secrets vào logs hoặc issue tracker.
- Dùng HTTPS/TLS khi publish qua mạng.
- Tách token SNAPSHOT và release nếu hệ thống repository hỗ trợ.
- Xác minh repository ID và URL tương ứng trước khi dùng alternate deployment target; không dùng ID có credentials dành cho một URL rồi trỏ sang URL không tin cậy.
- Kết hợp approval/protected branches và khóa versioning trước release.

**Bẫy:** Maven có thể dùng credentials theo `server.id`. Trong những cấu hình alternate URLs hoặc custom repository managers, phải kiểm tra rằng credentials không bị chuyển tới host khác. Đừng coi một chuỗi repository ID là phép chứng minh endpoint an toàn.

## 9. Release khác SNAPSHOT khi Maven deploy

Có hai loại version thường gặp:

~~~xml
<version>1.0.0</version>
~~~

và:

~~~xml
<version>1.1.0-SNAPSHOT</version>
~~~

### Release 1.0.0

Được dùng như một phiên bản ổn định. Một tổ chức nên coi published release artifact là **immutable**: cùng một tọa độ GAV phải đại diện một binary đã được kiểm soát. Nhiều repository managers có policy ngăn redeploy cùng release version.

Nếu một release 1.0.0 có lỗi, thông thường phát hành **1.0.1**, không lặng lẽ thay file của 1.0.0 ở remote repository.

### SNAPSHOT

Maven snapshots có thể được publish nhiều lần với cùng logical SNAPSHOT version; remote repository có thể dùng timestamped unique snapshots và `maven-metadata.xml` để Maven Resolver chọn bản tương ứng.

**Điều cần nhớ:**

- `mvn deploy` với version SNAPSHOT thường chọn `snapshotRepository` khi được cấu hình.
- Cấu trúc filename có thể khác một release JAR do timestamp/build number.
- SNAPSHOT không đại diện cho một bản phát hành immutable giống release.
- Consumer dùng SNAPSHOT có thể resolve lại bản khác theo update policy/cache.
- CI/CD không nên dùng chữ “SNAPSHOT” làm bằng chứng đã deploy đúng source revision: cần lưu artifact coordinates, checksums và provenance.

**Không** lấy bản SNAPSHOT mới nhất một cách ngầm định để triển khai production nếu quy trình yêu cầu tái lập và rollback.

## 10. Một CI/CD pipeline thường có hai công đoạn độc lập

Ví dụ policy đơn giản:

~~~text
Commit
  |
  v
CI build: mvn clean verify
  |
  +-- tests / static checks / artifact validation
  |
  v
Publish: mvn deploy
  |
  v
Artifact repository: hello-service:1.0.0
  |
  v
Approval / release decision
  |
  v
CD: lấy đúng hello-service:1.0.0 + checksum
  |
  v
Prepare runtime config / secrets
  |
  v
VM / Container / Kubernetes rollout
  |
  v
Health check / smoke test / observability
  |
  +-- healthy -> continue traffic
  |
  +-- unhealthy -> rollback
~~~

Đây là **luồng mẫu**, không phải bắt buộc mọi team phải dùng hai hệ thống khác nhau. Có nơi CI/CD tích hợp một workflow liên tục; nhưng việc phân tách **trách nhiệm publication và rollout** vẫn quan trọng.

CI publish thành công = artifact có thể được consumer lấy từ Maven repository. CD deploy thành công = phần mềm thực sự được đưa vào môi trường và **được kiểm chứng hoạt động**.

## 11. Lab Java 17: một JAR có HTTP health endpoint

Để phân biệt hai khái niệm, ta tạo **một project Java 17 runnable thật**. Nó dùng `com.sun.net.httpserver.HttpServer` từ module JDK `jdk.httpserver`; không cần Spring Boot hoặc thư viện runtime ngoài JDK.

Kết quả:

- Maven tạo executable **plain JAR** với manifest Main-Class.
- `java -jar` khởi động HTTP server trên `127.0.0.1:18080`.
- `GET /health` trả `OK`.
- `GET /hello` trả một chuỗi message có version.
- Maven Deploy Plugin có thể publish JAR/POM vào repository thử nghiệm mà **không khởi động server**.
- Bước application deployment mô phỏng việc copy JAR sang một thư mục khác rồi chạy `java -jar`.

Project:

~~~text
deploy-distinction-lab/
├── pom.xml
└── src/
    ├── main/
    │   └── java/dev/learning/release/HelloService.java
    └── test/
        └── java/dev/learning/release/HelloServiceTest.java
~~~

Khi học, đứng tại thư mục `deploy-distinction-lab` chứa `pom.xml` trừ khi lệnh chỉ rõ đường dẫn khác.

### 11.1. pom.xml đầy đủ

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.learning.release</groupId>
    <artifactId>hello-service</artifactId>
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
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
                <configuration>
                    <archive>
                        <manifest>
                            <mainClass>dev.learning.release.HelloService</mainClass>
                        </manifest>
                    </archive>
                </configuration>
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

**Tại sao POM không có distributionManagement trong lab?**

Vì chúng ta muốn **không vô tình publish tới repository doanh nghiệp/production**. Phần lab sẽ truyền `-DaltDeploymentRepository=lab::file:///...` trực tiếp khi chạy Maven `deploy`. Điều này làm đích đến có chủ đích và dễ kiểm soát.

Các đoạn `distributionManagement` trong mục 7 là ví dụ khi xây pipeline thực, **không** được tự ý chép vào lab rồi chạy deploy lên URL không thuộc quyền của bạn.

**POM này tạo plain executable JAR**:

- Maven JAR Plugin đặt manifest `Main-Class`.
- Ứng dụng runtime chỉ dùng JDK, không cần fat JAR/nested dependencies.
- JUnit Jupiter là `test` scope, không cần nằm trong runtime JAR.
- `maven-deploy-plugin` được pin version, nhưng chỉ publish khi đến phase `deploy` và có repository target.

### 11.2. HelloService.java

File `src/main/java/dev/learning/release/HelloService.java`:

~~~java
package dev.learning.release;

import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;

import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;

public final class HelloService {

    private HelloService() {
    }

    public static String message() {
        return "hello-service version=1.0.0";
    }

    public static String health() {
        return "OK";
    }

    private static void respond(
            HttpExchange exchange,
            int status,
            String body) throws IOException {

        byte[] data = body.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set(
                "Content-Type", "text/plain; charset=utf-8");
        exchange.sendResponseHeaders(status, data.length);

        try (OutputStream output = exchange.getResponseBody()) {
            output.write(data);
        }
    }

    public static void main(String[] args) throws IOException {
        String host = System.getProperty("app.host", "127.0.0.1");
        int port = Integer.parseInt(
                System.getProperty("app.port", "18080"));

        HttpServer server = HttpServer.create(
                new InetSocketAddress(host, port), 0);

        server.createContext("/health", exchange -> {
            if (!"GET".equals(exchange.getRequestMethod())) {
                respond(exchange, 405, "Method Not Allowed\n");
                return;
            }
            respond(exchange, 200, health() + "\n");
        });

        server.createContext("/hello", exchange -> {
            if (!"GET".equals(exchange.getRequestMethod())) {
                respond(exchange, 405, "Method Not Allowed\n");
                return;
            }
            respond(exchange, 200, message() + "\n");
        });

        server.start();

        System.out.println(
                "LISTENING http://" + host + ":" + port);
    }
}
~~~

**Giải thích:**

1. `HttpServer` là API có trong JDK 17; khi biên dịch/chạy với JDK đầy đủ phù hợp, không cần dependency bên ngoài.
2. Host mặc định là `127.0.0.1`, chỉ cho phép kết nối từ chính máy đang chạy. Đây là default an toàn cho lab.
3. Port mặc định `18080`, có thể đổi bằng system property `-Dapp.port=...`.
4. `GET /health` trả body `OK\n`, `GET /hello` trả `hello-service version=1.0.0\n`.
5. Những HTTP methods khác nhận status 405. Đây là logic cố ý để behavior kiểm chứng được.
6. `respond` ghi response bằng UTF-8 và đóng response body đúng cách.
7. `server.start()` khởi động HTTP server và chương trình tiếp tục chạy để nhận requests.
8. Dòng `LISTENING ...` được in khi HTTP server đã start; nó **không phải** bằng chứng hệ thống load balancer hay external clients đã kết nối được.
9. `app.host=0.0.0.0` có thể dùng khi muốn container tiếp nhận kết nối từ bên ngoài namespace, nhưng cần cấu hình firewall/network và authentication phù hợp. Không mở service rộng trong production chỉ vì chạy được.
10. Nếu port đang bận hoặc không có quyền bind, startup có thể báo lỗi. Đó là runtime issue, **khác với Maven repository publication**.

### 11.3. HelloServiceTest.java

File `src/test/java/dev/learning/release/HelloServiceTest.java`:

~~~java
package dev.learning.release;

import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;

class HelloServiceTest {

    @Test
    void exposesVersionMessage() {
        assertEquals(
                "hello-service version=1.0.0",
                HelloService.message());
    }

    @Test
    void exposesHealthyPayload() {
        assertEquals("OK", HelloService.health());
    }
}
~~~

Hai tests này kiểm tra business strings, **không khởi động HTTP server** và không mở cổng mạng. Chúng minh họa unit tests tại Maven `test` phase. Bước `curl` phía dưới sẽ là smoke/integration test của application process thật.

**Điều cần phân biệt:** JUnit PASS **không tự bảo đảm** Maven repository publication thành công, và cũng không tự bảo đảm deployed process healthy.

## 12. Build + kiểm tra artifact trước khi publish

Từ project root:

~~~bash
mvn -version
java -version
mvn -B -ntp clean verify
~~~

Với JDK 17+ và Maven/Artifact repositories hoạt động bình thường:

- Java source được biên dịch.
- Hai JUnit tests PASS.
- Maven tạo `target/hello-service-1.0.0.jar`.
- Vì goal Jar Plugin đã cấu hình Main-Class, JAR có thể được chạy bằng `java -jar`.
- Maven kết thúc `BUILD SUCCESS`.

Kiểm tra các classes:

~~~bash
jar tf target/hello-service-1.0.0.jar
~~~

Entry trọng yếu:

~~~text
dev/learning/release/HelloService.class
META-INF/MANIFEST.MF
~~~

Dòng trên là **hai entries cần tìm**, không phải toàn bộ listing.

### Kiểm tra manifest

Ở một thư mục kiểm tra riêng, dùng JDK:

~~~bash
mkdir inspect
cd inspect
jar --extract --file ../target/hello-service-1.0.0.jar META-INF/MANIFEST.MF
~~~

Đọc `inspect/META-INF/MANIFEST.MF` (working directory hiện là `inspect`) để thấy:

~~~text
Main-Class: dev.learning.release.HelloService
~~~

Manifest còn có thể có attributes khác, thứ tự không cố định. Đừng nhầm jar executable ở đây với Spring Boot executable JAR: demo này không có `BOOT-INF/lib` hoặc Spring Boot Loader.

Quay lại project root trước khi chạy các lệnh dưới:

~~~bash
cd ..
~~~

Bước trên là ví dụ shell Unix-like. Trên Windows PowerShell, `mkdir inspect` và `cd inspect` cũng thường hoạt động, nhưng cách đọc file bằng shell tùy hệ điều hành; JDK `jar --extract` là công cụ chính.

## 13. Chạy ứng dụng local trước: đây chưa phải Maven deploy

Lệnh:

~~~bash
java -jar target/hello-service-1.0.0.jar
~~~

khởi động HTTP server. Dòng được Java main in (giả sử port mặc định rảnh):

~~~text
LISTENING http://127.0.0.1:18080
~~~

Process sẽ **tiếp tục chạy**, không kết thúc ngay sau khi in dòng này. Trong terminal khác, gọi:

~~~bash
curl --fail --silent http://127.0.0.1:18080/health
curl --fail --silent http://127.0.0.1:18080/hello
~~~

HTTP body tương ứng, mỗi body kết thúc bằng newline:

~~~text
OK
hello-service version=1.0.0
~~~

Lệnh `curl --fail` giúp trả exit code khác 0 với nhiều HTTP error statuses; tuy nhiên một health check production cần thêm timeout, TLS, DNS/reachability và kiểm tra dependency readiness.

Để kết thúc lab process, nhấn `Ctrl+C` ở terminal chạy Java. **Chưa có artifact nào được publish lên Maven deployment repository** chỉ vì bạn đã chạy `java -jar`.

## 14. Maven deploy vào một file repository thử nghiệm

Đây là bài tập **publication**, không phải server rollout. Sử dụng `file://` để tránh cần tài khoản repository công ty.

### 14.1. Chuẩn bị trên Linux/macOS

Tạo thư mục riêng bên ngoài Maven local repository:

~~~bash
mkdir -p /tmp/maven-publication-lab
~~~

Từ root Maven project:

~~~bash
mvn -B -ntp clean deploy \
  -DaltDeploymentRepository=lab-repo::file:///tmp/maven-publication-lab
~~~

Dòng trên sử dụng dấu `\` của shell Unix để nối lệnh; có thể viết một dòng:

~~~bash
mvn -B -ntp clean deploy -DaltDeploymentRepository=lab-repo::file:///tmp/maven-publication-lab
~~~

Trong Maven Deploy Plugin **3.x**, format là:

~~~text
id::url
~~~

Không phải format cũ `id::layout::url` của Deploy Plugin 2.x.

### 14.2. Chuẩn bị trên Windows PowerShell

Tạo thư mục:

~~~powershell
New-Item -ItemType Directory -Force -Path "C:\maven-publication-lab"
~~~

Chạy trong thư mục project:

~~~powershell
mvn -B -ntp clean deploy "-DaltDeploymentRepository=lab-repo::file:///C:/maven-publication-lab"
~~~

Sử dụng absolute file URI dạng `file:///C:/...`, không phải ghép `file://C:\...` một cách tùy ý. Khi đường dẫn chứa khoảng trắng, cần bảo đảm URI encoding/quoting hợp lệ.

### Điều lệnh Maven thực hiện

Với POM lab có Maven Deploy Plugin 3.1.4:

1. Maven chạy toàn default lifecycle tới deploy.
2. Compiler/JUnit/JAR Plugin tạo artifact đã kiểm thử.
3. Install phase đưa artifact/POM vào **local Maven repository**.
4. Deploy Plugin publish artifact/POM vào đường dẫn `file:///tmp/maven-publication-lab` hoặc đường dẫn Windows đã chỉ định.
5. Không có Java web server nào được launch hoặc restart bởi Deploy Plugin ở POM này.

**Quan trọng:** mặc dù đích ở local filesystem, ở đây nó được chỉ định cho **deploy repository**, khác vai trò mặc định của `~/.m2/repository`. File repository này chỉ mô phỏng một Maven artifact repository từ xa, không phải một production application server.

## 15. Kiểm tra kết quả Maven publication

Trên Linux/macOS, sau khi publish:

~~~bash
ls -l /tmp/maven-publication-lab/dev/learning/release/hello-service/1.0.0/
~~~

Trên Windows PowerShell:

~~~powershell
Get-ChildItem "C:\maven-publication-lab\dev\learning\release\hello-service\1.0.0"
~~~

Những file chính:

~~~text
hello-service-1.0.0.jar
hello-service-1.0.0.pom
~~~

Có thể còn checksum/metadata do Maven repository transport/plugin tạo. Không nên kiểm tra “chỉ được phép có đúng hai files”.

**Lúc này Java HTTP service không tự xuất hiện ở cổng 18080.** Maven repository chứa file. Bạn vẫn cần **một quá trình application deployment** để chạy file trên môi trường mục tiêu.

### Phân biệt hai câu “deploy thành công”

- “Maven deploy thành công”: có artifact/POM đúng GAV ở Maven publication repository.
- “Ứng dụng deploy thành công”: JAR/image đúng version được đưa lên runtime và process/health/traffic được kiểm tra.

Nếu log Maven báo `BUILD SUCCESS` và `Uploading ...`, đó là bằng chứng publication. Nếu bạn cần chứng minh ứng dụng đã chạy, hãy kiểm tra runtime/process, không chỉ Maven output.

## 16. Mô phỏng application deployment mà không cần server thật

Sau khi đã build, mô phỏng một máy chủ ứng dụng bằng **thư mục độc lập**.

Linux/macOS:

~~~bash
mkdir -p /tmp/hello-server/releases/1.0.0
cp target/hello-service-1.0.0.jar \
   /tmp/hello-server/releases/1.0.0/hello-service.jar
~~~

Chạy bản trong “server folder” ở terminal thứ nhất:

~~~bash
java -Dapp.port=18080 \
     -jar /tmp/hello-server/releases/1.0.0/hello-service.jar
~~~

Một dòng stdout của app:

~~~text
LISTENING http://127.0.0.1:18080
~~~

Trong terminal thứ hai:

~~~bash
curl --fail --silent http://127.0.0.1:18080/health
curl --fail --silent http://127.0.0.1:18080/hello
~~~

Responses:

~~~text
OK
hello-service version=1.0.0
~~~

**Bây giờ** đã có bước gần với application deployment: chép binary đến vị trí runtime, khởi động process và kiểm tra endpoint. Vì dùng thư mục `/tmp` trên **cùng máy**, đây chỉ là **mô phỏng**, không phải một ứng dụng production được triển khai trên host khác.

### Windows PowerShell

~~~powershell
New-Item -ItemType Directory -Force -Path "C:\hello-server\releases\1.0.0"
Copy-Item "target\hello-service-1.0.0.jar" "C:\hello-server\releases\1.0.0\hello-service.jar"
java -Dapp.port=18080 -jar "C:\hello-server\releases\1.0.0\hello-service.jar"
~~~

Chạy `curl.exe http://127.0.0.1:18080/health` trong terminal khác. Nếu PowerShell alias `curl` trỏ vào cmdlet riêng, `curl.exe` rõ ràng hơn.

**Không chạy hai ứng dụng cùng listen port 18080 trên cùng host.** Dừng process cũ bằng `Ctrl+C` trước khi start phiên bản khác, hoặc chọn port khác có chủ đích.

## 17. Mô phỏng khác biệt bằng hai câu kiểm chứng

### Trường hợp A: chỉ Maven publish

~~~bash
mvn -B -ntp clean deploy -DaltDeploymentRepository=lab-repo::file:///tmp/maven-publication-lab
~~~

Kiểm tra:

~~~bash
ls /tmp/maven-publication-lab/dev/learning/release/hello-service/1.0.0/
~~~

Câu trả lời: **JAR/POM tồn tại trong repository**, nhưng **không đủ bằng chứng** rằng một service đang chạy.

### Trường hợp B: chỉ chạy application

~~~bash
java -jar target/hello-service-1.0.0.jar
~~~

Kiểm tra:

~~~bash
curl --fail http://127.0.0.1:18080/health
~~~

Câu trả lời: **service process chạy**; lệnh này **không tự publish JAR/POM** lên Maven repository.

### Trường hợp C: ghép thành CI/CD

~~~text
mvn clean verify
      |
      v
mvn deploy (publish artifact)
      |
      v
CD lấy đúng artifact phiên bản
      |
      v
Copy / image / rollout
      |
      v
Health check + traffic + rollback
~~~

Đây là cách ghép có kiểm soát, thay vì nghĩ một lệnh Maven mặc định thực hiện tất cả.

## 18. Server thật thường cần những gì ngoài một file JAR?

Khi triển khai application lên VM/Linux server, các bước bổ sung có thể gồm:

1. **Chọn artifact đã kiểm thử**: version, checksum, provenance, chữ ký khi có.
2. **Tải artifact** từ Maven repository hoặc artifact store của CI theo policy.
3. **Đặt binary** vào vị trí thuộc release cụ thể, không ghi đè lẫn lộn.
4. **Cấu hình runtime**: JDK/JRE tương thích, environment variables, JVM args, config files và secrets.
5. **Cấu hình permissions**: user/group chạy dịch vụ, file ownership, directories.
6. **Cấu hình process supervision**: `systemd`, container runtime hoặc process manager phù hợp.
7. **Kiểm soát port/network**: firewall, reverse proxy, TLS, authentication, service discovery.
8. **Graceful restart/rollout**: tránh downtime nếu yêu cầu availability cao.
9. **Health/readiness**: kiểm tra HTTP, database connectivity hoặc tác vụ nghiệp vụ phù hợp.
10. **Quan sát sau deploy**: logs, metrics, traces, alerts, error rates.
11. **Rollback**: giữ release trước và switch traffic nếu bản mới lỗi.

Maven repository **không đảm nhận** những nhiệm vụ này. Một release artifact được lưu đúng chỉ là nguyên liệu đầu vào cho bước rollout.

## 19. Ví dụ systemd: khởi chạy ứng dụng trên VM

Đây là **mẫu khái niệm dành cho Linux server có systemd**, không phải script tự chạy trên máy học. Trước khi dùng thật, cần provision user/app directories, cài JDK và cấu hình permissions.

Giả sử binary đã được CD đặt ở:

~~~text
/opt/hello-service/releases/1.0.0/hello-service.jar
~~~

Mẫu systemd unit:

~~~ini
[Unit]
Description=Hello Service Java 17
After=network.target

[Service]
Type=simple
User=helloapp
Group=helloapp
WorkingDirectory=/opt/hello-service
ExecStart=/usr/bin/java -Dapp.host=127.0.0.1 -Dapp.port=18080 -jar /opt/hello-service/releases/1.0.0/hello-service.jar
Restart=on-failure
RestartSec=5
SuccessExitStatus=143

[Install]
WantedBy=multi-user.target
~~~

Điều cần hiểu:

- `User/Group` phải tồn tại và chỉ có quyền tối thiểu.
- `ExecStart` trỏ tới **JAR đã được chuyển đến môi trường runtime**, không phải Maven repository remote URL.
- Ứng dụng demo bind loopback; muốn đưa ra ngoài máy, cần reverse proxy/network policy hoặc bind có chủ đích.
- `Restart=on-failure` là process management, không phải Maven Deploy Plugin behavior.
- `SuccessExitStatus=143` là một lựa chọn khi Java process kết thúc với code này; cần quan sát cách JVM/process wrapper thực tế xử lý SIGTERM.
- Systemd unit không tự biết GAV; CD phải quyết định chính xác release path.

Khi cấu hình trên server thuộc quyền quản trị, các thao tác có thể gồm:

~~~bash
sudo systemctl daemon-reload
sudo systemctl enable --now hello-service
sudo systemctl status hello-service
curl --fail http://127.0.0.1:18080/health
~~~

**Không coi các lệnh trên là lab cần chạy** nếu bạn không sở hữu/có quyền quản lý service đó. Người học chỉ thực hành an toàn với thư mục `/tmp/hello-server` trước.

### Rollback dưới dạng release path

Thực tế nên giữ:

~~~text
/opt/hello-service/releases/
├── 1.0.0/hello-service.jar
└── 1.0.1/hello-service.jar
~~~

Một pipeline rollback có thể chuyển systemd unit/symlink hoặc release pointer về bản trước rồi restart/health check. Việc xóa version 1.0.1 khỏi Maven repository **không** thay thế việc rollback process đã chạy.

## 20. Container/Kubernetes là application deployment, không phải Maven repository deploy

Một pipeline khác có thể:

~~~text
Maven build → executable JAR → Docker image → Container registry
                                                |
                                                v
                                           Kubernetes rollout
                                                |
                                                v
                                           Health/readiness
~~~

Maven Deploy Plugin **publish JAR/POM tới Maven repository**. Còn:

- `docker build` tạo OCI/container image.
- `docker push` xuất bản image lên **container registry**, không phải Maven artifact repository.
- `kubectl apply`/`kubectl set image`/Helm/GitOps thay đổi resources trong cluster.
- `kubectl rollout status` đánh giá trạng thái rollout của workload; cần thêm application smoke/functional checks nếu yêu cầu.

### Dockerfile minh họa cho JAR Java 17 của lab

~~~dockerfile
FROM eclipse-temurin:17-jre
WORKDIR /app
COPY target/hello-service-1.0.0.jar /app/hello-service.jar
EXPOSE 18080
ENTRYPOINT ["java", "-Dapp.host=0.0.0.0", "-Dapp.port=18080", "-jar", "/app/hello-service.jar"]
~~~

Đây là **ví dụ Dockerfile**, không phải file có sẵn trong project mặc định của lab. Dùng khi project đã qua `mvn clean package`, tại Docker build context chứa thư mục `target/`.

Build/run local ví dụ:

~~~bash
docker build -t hello-service:1.0.0 .
docker run --rm -p 18080:18080 hello-service:1.0.0
~~~

Trong terminal khác:

~~~bash
curl --fail http://127.0.0.1:18080/health
~~~

Vì app bind `0.0.0.0` trong container, Docker port mapping mới đưa request từ host vào được. **EXPOSE** là metadata, không tự publish port; tham số `-p` mới tạo port mapping ở demo Docker.

**Bảo mật:** `0.0.0.0` làm server chấp nhận trên các interfaces trong container. Production cần network policies, reverse proxy, TLS và authentication tùy ứng dụng. Image tag `17-jre` là tag có thể thay đổi; release nghiêm ngặt nên pin digest và scan image.

**Không thể nói** `mvn deploy` tự làm Docker steps chỉ vì Maven project có thể tạo JAR dùng để build image.

## 21. DistributionManagement không phải nơi chỉ định server chạy app

Một lỗi cấu hình ý niệm:

~~~xml
<distributionManagement>
    <repository>
        <id>prod-web</id>
        <url>https://app.example.org/health</url>
    </repository>
</distributionManagement>
~~~

Đây là **phản ví dụ**. URL `/health` là HTTP endpoint của ứng dụng, không phải Maven repository transport endpoint để upload artifacts và metadata theo repository layout. Deploy Plugin sẽ không tự hiểu đó là vị trí phải chạy code.

Đúng hơn:

~~~xml
<distributionManagement>
    <repository>
        <id>company-releases</id>
        <url>https://repo.example.org/maven-releases</url>
    </repository>
</distributionManagement>
~~~

và ứng dụng production dùng **deployment configuration riêng**, ví dụ Kubernetes manifests, VM release scripts hoặc managed deployment service.

Hai URLs có thể cùng thuộc một tổ chức nhưng phục vụ hoàn toàn khác nhau.

## 22. altDeploymentRepository: phù hợp cho lab và CI

Trong Deploy Plugin 3.x, bạn có thể thay đích publication mà không đổi POM:

~~~bash
mvn deploy -DaltDeploymentRepository=lab-repo::file:///tmp/maven-publication-lab
~~~

Format:

~~~text
<repository-id>::<repository-url>
~~~

Ý nghĩa:

- ID là tên repository dùng để nhận diện và (nếu có) map tới Maven settings server credentials.
- URL là đích artifact publication.
- Không có segment `layout` như Deploy Plugin 2.x.

Có các user properties riêng trong plugin:

- `altDeploymentRepository`: alternative repository chung.
- `altReleaseDeploymentRepository`: alternative repository dành cho release.
- `altSnapshotDeploymentRepository`: alternative repository dành cho snapshot.

Khi có nhiều loại, phải hiểu thứ tự ưu tiên được tài liệu plugin mô tả cho version đang dùng. Một policy CI có thể dùng riêng URLs releases/snapshots để ngăn snapshots làm bẩn release repository.

**Lưu ý an toàn:** Đừng truyền một server ID có credentials production cùng một URL không đáng tin. Ngoài việc cấu hình đúng, cần giới hạn nơi CI cho phép publish.

## 23. deploy:deploy-file khác deploy:deploy

Một JAR bên ngoài Maven build, ví dụ:

~~~text
third-party/vendor-tool-1.0.jar
~~~

có thể được publish bằng goal:

~~~bash
mvn org.apache.maven.plugins:maven-deploy-plugin:3.1.4:deploy-file \
    -Dfile=third-party/vendor-tool-1.0.jar \
    -DgroupId=dev.vendor \
    -DartifactId=vendor-tool \
    -Dversion=1.0.0 \
    -Dpackaging=jar \
    -DrepositoryId=lab-repo \
    -Durl=file:///tmp/maven-publication-lab
~~~

Đây là **lệnh minh họa Unix-like**, chỉ chạy nếu file vendor JAR thật sự tồn tại. Nó không thuộc lab Java 17 chính.

Tác dụng:

- Publication một file artifact theo coordinates/URL được chỉ định.
- Nếu vendor cung cấp POM đúng, dùng `-DpomFile=...` để giữ dependency metadata thật.
- Nếu không có POM, plugin có thể tạo một POM tối thiểu theo option/default thích hợp; nó **không thể tự suy ra đầy đủ** các transitive dependencies của binary.
- `deploy-file` **vẫn không khởi động ứng dụng trên VM**.

**Không gọi `deploy-file` cho project Maven bình thường khi `mvn deploy` đã có thể xử lý main artifact, POM và attached artifacts nhất quán.**

## 24. Deploy Plugin hỗ trợ nhiều tham số, nhưng không thay CD

| Tham số | Ý nghĩa thực tế |
| --- | --- |
| `altDeploymentRepository` | Thay đích Maven publication |
| `altReleaseDeploymentRepository` | Thay đích cho bản release |
| `altSnapshotDeploymentRepository` | Thay đích cho SNAPSHOT |
| `maven.deploy.skip` | Bỏ qua goal publication theo mode được hỗ trợ |
| `deployAtEnd` | Hoãn publication cho multi-module build để giảm partial deploy |
| `retryFailedDeploymentCount` | Số lần thử lại nếu repository transfer lỗi, theo giới hạn plugin |
| `allowIncompleteProjects` | Cho phép một số project không có main artifact (chỉ dùng khi hiểu packaging) |

Trong plugin 3.x, `skip` có thể nhận:

~~~text
true
releases
snapshots
false
~~~

Tùy phiên bản cụ thể, giá trị không hợp lệ có thể làm build fail; không ghi `-Dmaven.deploy.skip=something` rồi cho rằng nó chắc chắn là false.

### Ví dụ kiểm tra không publish

~~~bash
mvn -B -ntp deploy -Dmaven.deploy.skip=true
~~~

Bước build/test/install trước `deploy` vẫn có thể diễn ra; nhưng goal upload artifacts được skip. **BUILD SUCCESS lúc này không chứng minh artifact mới đã có trên repository**.

Vì vậy CI release không nên lặng lẽ dùng `skip=true` hoặc `skip=releases` khi mục tiêu là publish một release.

## 25. deployAtEnd không phải transaction

Trong multi-module Maven reactor, nếu từng module deploy ngay khi tới phase `deploy`, một module sau fail có thể để lại **một số artifacts đã publish**.

Maven Deploy Plugin hỗ trợ:

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

Đây là một **POM fragment** đặt trong `<build><plugins>` hoặc cấu hình kế thừa phù hợp của multi-module project.

Ý tưởng: hoãn publication đến cuối reactor để giảm khả năng chỉ vài modules đã được upload trong khi những module khác còn chưa pass.

**Nhưng:** `deployAtEnd=true` không có nghĩa publication là một database transaction với atomic commit/rollback. Nếu upload nhiều artifacts/repositories rồi lỗi giữa chừng, một số remote uploads có thể đã tồn tại. Hành vi chi tiết phụ thuộc plugin version, reactor modules và repository manager.

Production release có thể cần staging repository, release promotion và kiểm soát immutable coordinates, không chỉ một cờ Maven.

## 26. Maven local repo, Maven remote repo và server runtime

Ba nơi khác nhau:

~~~text
1. Local Maven repository:
   ~/.m2/repository/...
   Dùng để resolve/install artifacts trên môi trường build.

2. Maven remote/deployment repository:
   https://repo.example.org/maven-releases/...
   Dùng để publish/share artifacts cho các consumer builds.

3. Application runtime:
   /opt/hello-service/releases/1.0.0/hello-service.jar
   hoặc container image đang chạy trong cluster.
   Dùng để phục vụ requests/jobs cho người sử dụng.
~~~

Sự khác nhau này cũng giải thích vì sao:

- Developer chạy `mvn install` trên laptop không làm production thay đổi.
- CI chạy `mvn deploy` upload thành công không tự khởi động process trên server.
- SRE chạy `systemctl restart` không tự publish Maven artifact.
- Kubernetes rollout image không nhất thiết sử dụng Maven Deploy Plugin.
- Consumer Maven tải dependency từ remote repository không đồng nghĩa **deploy application**.

## 27. “Deploy thành công” phải có tiêu chí chấp nhận riêng

### Maven artifact publication checks

- Repository endpoint có đúng path GAV?
- JAR/WAR/POM có đầy đủ không?
- Version đúng loại release/SNAPSHOT?
- Attached source/javadoc artifacts (nếu policy yêu cầu) có được publish?
- Checksum/digest có khớp artifact đã build?
- Maven log có upload thành công?
- Consumer build từ một môi trường clean có resolve được tọa độ đó?
- Repository policies (immutability, signature, provenance, retention) được tuân thủ?

### Application deployment checks

- Đúng **artifact version/digest** được đưa vào runtime?
- Process/container thực sự chạy?
- Config/secrets đúng môi trường?
- Port, DNS, TLS và routing hoạt động?
- HTTP health/readiness endpoints đạt?
- Smoke tests và critical workflows đạt?
- Error rate/latency/resource usage sau rollout bình thường?
- Rollback artifact/image trước được giữ và có thể kích hoạt?
- Deployment events/metrics được ghi để truy vết?

Một Maven build report không thay thế được health/readiness report của production.

## 28. Tại sao dùng cùng artifact cho các môi trường?

Một anti-pattern phổ biến:

~~~text
Build 1.0.0 trên máy developer → publish
Build lại cùng GAV 1.0.0 ở CI staging → deploy staging
Build lại cùng GAV 1.0.0 ở CI production → deploy production
~~~

Nếu ba lần build tạo bytecode/dependency graph khác nhau, cùng version label `1.0.0` không còn đủ để chứng minh “bản đã test là bản đang chạy”.

Chiến lược tốt hơn:

~~~text
Build once → test → record checksum/digest
     |
     v
Publish immutable artifact
     |
     +-- deploy staging từ chính binary đó
     |
     +-- promote/deliver production từ chính binary đó
     |
     +-- rollback bằng artifact/version đã biết
~~~

Đây là **artifact promotion**. Trên container images, dùng digest thay vì chỉ mutable tag khi yêu cầu tính bất biến.

Maven Deploy Plugin góp phần ở nhánh **publish Maven artifact**, nhưng không tự hoàn thành toàn bộ deployment governance.

## 29. Maven coordinates không đủ để nhận diện một process đang chạy

Maven dependency coordinates:

~~~text
dev.learning.release:hello-service:1.0.0
~~~

xác định Maven artifact được yêu cầu. Nhưng khi một service chạy trên host, bạn còn cần thông tin:

- JAR/image digest được thực thi.
- Runtime Java version.
- Startup flags và environment configuration.
- Instance/host/pod identity.
- Deployment timestamp, release commit/build provenance.
- Health checks, traffic và runtime metrics.

Nếu version text trong code là `1.0.0` nhưng process thực tế vẫn dùng JAR cũ, request `GET /hello` có thể in output cũ. Vì vậy demo vừa kiểm tra **file repository**, vừa kiểm tra **HTTP endpoint** theo hai bước tách biệt.

Khi triển khai production, nên expose một endpoint read-only chứa release metadata an toàn và đối chiếu với artifact manifest/digest mà CD đã chọn. **Không lộ secrets hoặc thông tin nội bộ nhạy cảm** qua endpoint.

## 30. Maven Deploy Plugin không thay Docker/Helm/Cargo/Jib goals

Một số tools dùng chữ “deploy” cho hành vi khác:

- Maven Cargo Plugin có thể thao tác container/application server theo goal/config riêng.
- Một số plugins có goals upload hoặc restart server.
- Maven Jib Plugin build/push container image theo cấu hình.
- Spring Boot Maven Plugin có thể build OCI image qua buildpacks.
- Docker CLI có `docker push` để publish image lên registry.
- Kubernetes controllers thực hiện rollout khi desired state thay đổi.

Những hoạt động này **không đồng nhất** với Maven Deploy Plugin `deploy:deploy`. Mỗi plugin có goals riêng, lifecycle bindings riêng, permissions riêng và output khác nhau.

**Đọc đúng goal name trong Maven log**, ví dụ `maven-deploy-plugin:3.1.4:deploy`, thay vì chỉ tìm chữ “deploy”.

## 31. Giải thích những thông báo Maven thường gặp

Một build thành công có thể có những dòng theo ý nghĩa:

~~~text
... compiler:compile ...
... surefire:test ...
... jar:jar ...
... install:install ...
... deploy:deploy ...
BUILD SUCCESS
~~~

Đây là **sơ đồ goals rút gọn**, không phải output cụ thể của một lần chạy. Version/goal execution IDs và thứ tự log chi tiết phụ thuộc Maven configuration.

Trong Deploy Plugin, log có thể cho thấy:

~~~text
Uploading to lab-repo: file:///tmp/maven-publication-lab/...
Uploaded to lab-repo: file:///tmp/maven-publication-lab/...
~~~

Đó là bằng chứng publication, **không phải log của Java HTTP process**.

Ngược lại dòng:

~~~text
LISTENING http://127.0.0.1:18080
~~~

do code `HelloService.main` in khi process start, không phải dấu hiệu POM đã publish lên Maven repository.

## 32. Bảng lỗi phổ biến và hướng xử lý

| Triệu chứng | Nguyên nhân có khả năng | Cách xác minh |
| --- | --- | --- |
| `mvn deploy` báo thiếu repository | Chưa có distributionManagement/altDeploymentRepository | Xem POM effective model và CLI properties |
| Repository báo 401/403 | Credentials hoặc quyền publish sai | So server ID, token scopes và URL thật |
| Maven dùng sai release/snapshot repository | POM version hoặc distributionManagement sai | Kiểm tra `version` và snapshotRepository |
| Lỗi `altDeploymentRepository` syntax | Dùng cú pháp `id::layout::url` của plugin 2.x | Với plugin 3.x dùng `id::url` |
| Maven deploy thành công nhưng service vẫn version cũ | Artifact publish nhưng không rollout | Kiểm tra CD job, process/image digest và endpoint |
| Server đang dùng JAR khác bản publish | CD chọn nhầm file/tag/cache | So checksum/digest và release path |
| Tests PASS, server không chạy | Port bận, runtime/config missing, permission lỗi | Chạy artifact trong environment mục tiêu, xem process logs |
| Docker port mapping không truy cập được | App bind loopback trong container | Dùng host binding phù hợp và kiểm soát network |
| Artifact có trong local `.m2` nhưng không có remote | Mới `install`, chưa `deploy`, hoặc skip deploy | Đọc Deploy Plugin log, remote repository listing |
| JAR/POM remote đúng nhưng consumer không resolve | repositories/mirror/credentials/metadata khác | Xem effective settings, Maven Resolver diagnostics |
| Deploy file repo được nhưng HTTPS repo fail | URL/auth/TLS/network/policy khác nhau | Điều tra đúng remote transport và server credentials |
| 409 hoặc repository từ chối release | Immutable/version redeploy policy | Dùng version mới theo release process |
| SNAPSHOT được publish nhưng runtime cũ | Không có CD trigger hoặc rollout chưa hoàn thành | Xem deployment events và image/JAR digest |
| CI `BUILD SUCCESS` nhưng không upload | `maven.deploy.skip=true` hoặc goal không chạy như mong | Xem actual execution log |
| Một vài modules publish, module khác fail | Multi-module partial deployment | Cân nhắc deployAtEnd/staging và repository governance |
| `deploy-file` không chạy | File vendor path không tồn tại hoặc metadata thiếu | Kiểm tra file path/pomFile và goal arguments |
| Không tìm thấy Main-Class khi `java -jar` | JAR không executable hoặc manifest sai | Kiểm tra JAR manifest |
| Ứng dụng trả 503 sau rollout | Runtime dependency chưa sẵn sàng | Xem readiness/dependencies và rollback policy |
| Health check chỉ trả 200 nhưng nghiệp vụ lỗi | Health quá nông, smoke tests thiếu | Kiểm tra critical endpoints và metrics |
| Rollback nhưng process vẫn cũ | Deployment pointer/restart/traffic chưa chuyển | Xác nhận release path, instance/image và load balancer |

**Không tự suy đoán** một lỗi `HTTP 403` là quyền ứng dụng server: nếu lỗi xuất hiện ở Maven Upload step, có thể là quyền **Maven repository**; nếu xuất hiện khi gọi `/health`, đó là vấn đề của **runtime endpoint**. Cần đọc nơi phát sinh và HTTP host.

## 33. Quy trình debug: Maven deploy xanh nhưng app không cập nhật

Nếu người vận hành nói “chạy `mvn deploy` rồi nhưng production chưa thay đổi”, xử lý như sau:

1. Đọc actual Maven log: Maven Deploy Plugin goal có chạy hay bị skip?
2. Xác định repository URL nhận artifacts, GAV và timestamp/version.
3. Kiểm tra artifact JAR/POM có trên repository đúng không.
4. Xác minh CI/CD trigger: publication có kích hoạt application deployment pipeline không?
5. Nếu có trigger, xem CD đã tải artifact nào và digest/checksum nào.
6. So sánh digest của artifact được publish với binary/image đang chạy.
7. Kiểm tra environment/namespace/host mục tiêu; có thể bạn deploy staging thay vì production.
8. Kiểm tra rollout events, systemd logs hoặc Kubernetes deployment/pod status.
9. Gọi health/readiness và một endpoint phiên bản/feature an toàn.
10. Đọc logs/metrics để biết lỗi startup/permission/port/secrets.
11. Nếu unhealthy, rollback theo policy; đừng tự chạy lại Maven deploy một cách mù quáng.
12. Ghi nguyên nhân: lỗi publication, pipeline handoff, artifact selection hay runtime rollout.

Nhờ phân tách như vậy, không phải cứ “app không lên” là sửa POM `distributionManagement`; có thể lỗi hoàn toàn ở CD runtime configuration.

## 34. Bảo mật và quản trị release

### 34.1. Artifact repository

- Token publish riêng; không dùng admin credentials.
- Bảo vệ release repo, tránh overwrite releases.
- Scan dependencies/SBOM và malware/vulnerability phù hợp.
- Ký/ghi provenance nếu release pipeline cần supply-chain assurance.
- Bảo đảm chỉ protected branch/tag được publish bản release.
- Không dùng snapshots trong production khi policy cần immutable artifact.
- Giữ retention và quyền đọc phù hợp cho consumers.
- Khi alternate repository URL thay đổi, review endpoint và credential binding.

### 34.2. Application runtime

- Dùng service account riêng, không chạy Java process bằng root nếu không cần.
- Secrets qua vault/secret manager, không gói password trong JAR/POM.
- JDK/JRE versions được pin/cập nhật an toàn.
- Network policies, firewall, TLS và authentication đúng workload.
- Liveness khác readiness: process sống chưa chắc sẵn sàng nhận traffic.
- Log/metrics không được chứa token, dữ liệu cá nhân hoặc toàn bộ environment.
- Rolling/canary/blue-green có smoke tests và rollback plan.
- Giới hạn người/quy trình có quyền deploy production.

**Maven deploy lên repo không cần quyền quản trị application server.** Ngược lại, người deploy application không nhất thiết cần quyền publish Maven artifacts. Tách quyền giúp giảm tác hại khi credential bị lộ.

## 35. Ứng dụng web khác WAR deploy lên Tomcat thế nào?

Cần phân biệt ba trường hợp:

1. **`mvn deploy`**: publish `my-app.war` và `my-app.pom` lên Maven artifact repository theo Maven Deploy Plugin.
2. **Deploy WAR vào Tomcat**: copy/upload WAR tới một Tomcat instance hoặc dùng Tomcat/Cargo plugin/API để server load ứng dụng; đây là **application deployment**.
3. **Spring Boot executable JAR**: build executable JAR rồi chạy `java -jar` trên VM/container hoặc image; đây cũng là **application deployment**.

Cùng chữ “deploy” nhưng **destination và success criteria khác nhau**.

Một Spring Boot JAR có thể được xuất bản vào Maven repository rồi vài giờ sau mới được CD rollout. Một WAR có thể được cài vào Tomcat theo pipeline mà không bao giờ được publish vào Maven repository (dù thường vẫn nên lưu artifact release được kiểm soát).

Đừng định nghĩa khái niệm chỉ dựa trên đuôi `.jar` hay `.war`.

## 36. Tự kiểm tra sau từng bước của lab

| Bước | Lệnh | Dấu hiệu thành công | Điều không chứng minh |
| --- | --- | --- | --- |
| Build/test | `mvn clean verify` | Tests PASS, JAR ở target | Chưa publish repository |
| Chạy local | `java -jar target/...jar` | `/health` trả `OK` | Không có remote publication |
| Maven publish | `mvn clean deploy -DaltDeploymentRepository=...` | Repository có JAR/POM | Chưa khởi động runtime service |
| Deploy mô phỏng | Copy JAR vào thư mục server và `java -jar` | Process chạy từ release folder | Không tự xác nhận repository auth |
| Runtime smoke | `curl /health` và `curl /hello` | Endpoint đáp ứng | Chưa chứng minh tất cả nghiệp vụ |
| Production release | CD chọn artifact/digest rồi rollout | Health/traffic/metrics và policy PASS | Không thể suy từ Maven BUILD SUCCESS đơn thuần |

Kết quả lab phụ thuộc môi trường: port 18080 phải rảnh; JDK và Maven phải có khả năng chạy; plugins/JUnit được Maven resolve từ repository hợp lệ. Không khẳng định mình đã chạy những lệnh này trên máy của người đọc; các đoạn output được trình bày là **dự kiến theo mã và cấu hình đã cung cấp**.

## 37. Bài tập có đáp án

1. **`mvn deploy` mặc định gửi artifact đến đâu?**  
   **Đáp án:** Maven deployment repository được cấu hình, không phải VM ứng dụng.

2. **Maven deploy có tự khởi động JVM trên server không?**  
   **Đáp án:** Không theo Maven Deploy Plugin mặc định.

3. **Khi gọi Maven deploy, phase install có nằm trước deploy không?**  
   **Đáp án:** Có trong default lifecycle.

4. **Mục đích của `distributionManagement`?**  
   **Đáp án:** Chỉ định đích publication artifacts, gồm release/snapshot repositories.

5. **Credentials repository đặt ở đâu?**  
   **Đáp án:** Maven settings `<servers>`/secret manager, không hard-code POM.

6. **Server ID ở settings phải khớp giá trị nào?**  
   **Đáp án:** Repository ID của đích publish.

7. **`<repositories>` khác `<distributionManagement>`?**  
   **Đáp án:** Repositories chủ yếu tải dependencies; distributionManagement publish project artifacts.

8. **Có thể Maven deploy thành công nhưng app production vẫn cũ không?**  
   **Đáp án:** Có; CD rollout là bước riêng.

9. **Release repository nên cho phép overwrite GAV cũ không?**  
   **Đáp án:** Thông thường không; cần immutable release policy.

10. **SNAPSHOT artifact có thể đổi nội dung ở logical version không?**  
    **Đáp án:** Có, theo snapshot publishing/resolution policy.

11. **Maven Deploy Plugin goal chính cho Maven project?**  
    **Đáp án:** `deploy:deploy`.

12. **Goal cho binary được tạo ngoài Maven?**  
    **Đáp án:** `deploy:deploy-file`.

13. **Tại sao deploy-file với generated minimal POM có thể thiếu thông tin?**  
    **Đáp án:** Nó không tự suy ra transitive dependencies.

14. **Cú pháp altDeploymentRepository của plugin 3.x?**  
    **Đáp án:** `id::url`.

15. **Dùng format plugin 2.x `id::layout::url` trên plugin 3.x có đúng không?**  
    **Đáp án:** Không; format đã thay đổi.

16. **Một repository `file://` có phải server ứng dụng không?**  
    **Đáp án:** Không; đó là cách mô phỏng đích Maven artifact publication.

17. **Trong lab, endpoint health trả gì?**  
    **Đáp án:** HTTP body `OK\n` với status 200 cho GET.

18. **Endpoint hello trả gì?**  
    **Đáp án:** `hello-service version=1.0.0\n`.

19. **Lệnh chạy JAR sau build trong lab?**  
    **Đáp án:** `java -jar target/hello-service-1.0.0.jar`.

20. **Lệnh `java -jar` có publish Maven POM không?**  
    **Đáp án:** Không.

21. **Tại sao POM lab có cấu hình Main-Class?**  
    **Đáp án:** Để plain JAR có thể chạy bằng `java -jar` mà không cần fat packaging.

22. **JAR demo cần Spring Boot ở runtime không?**  
    **Đáp án:** Không; nó dùng JDK HttpServer.

23. **Trong container, vì sao ví dụ dùng `app.host=0.0.0.0`?**  
    **Đáp án:** Để app lắng nghe interface container, cho port mapping vào được.

24. **Docker EXPOSE có tự mở host port không?**  
    **Đáp án:** Không; `docker run -p` thực hiện port mapping trong ví dụ.

25. **`docker push` publish tới đâu?**  
    **Đáp án:** Container registry, không phải Maven repository.

26. **`kubectl rollout` liên quan điều gì?**  
    **Đáp án:** Trạng thái thay đổi workload trong Kubernetes cluster.

27. **`maven.deploy.skip=true` có thể khiến publication không diễn ra?**  
    **Đáp án:** Có; BUILD SUCCESS không có nghĩa artifacts đã upload.

28. **`deployAtEnd=true` có đảm bảo atomic transaction cho mọi artifact không?**  
    **Đáp án:** Không.

29. **Nếu runtime health thất bại, có nên chỉ chạy lại `mvn deploy`?**  
    **Đáp án:** Không; phải điều tra CD/runtime và rollback theo policy.

30. **Để chứng minh đã publish artifact, cần gì?**  
    **Đáp án:** Repository có đúng JAR/POM/GAV và transfer thành công.

31. **Để chứng minh app đã triển khai, cần gì?**  
    **Đáp án:** Runtime version/digest đúng, process chạy và health/smoke checks đạt.

32. **Vì sao cần artifact promotion?**  
    **Đáp án:** Đảm bảo cùng binary đã kiểm thử được chuyển qua staging/production.

33. **Cùng GAV có đủ chứng minh runtime binary đúng không?**  
    **Đáp án:** Không; nên đối chiếu checksum/digest và deployment metadata.

34. **Maven Repo 401/403 có nhất thiết là lỗi HTTP endpoint app không?**  
    **Đáp án:** Không; xem host và bước nào phát sinh lỗi.

35. **Nếu dùng application deployment plugin được bind vào Maven phase deploy, điều gì xảy ra?**  
    **Đáp án:** Có thể có side effects server riêng do plugin ấy; không phải hành vi mặc định của Maven Deploy Plugin.

36. **Khi nào nên dùng release repository thay snapshot repository?**  
    **Đáp án:** Khi xuất bản version release ổn định/immutable.

37. **Maven deploy có quản lý systemd service không?**  
    **Đáp án:** Không theo plugin mặc định.

38. **Health endpoint trả 200 có chứng minh mọi nghiệp vụ hoạt động không?**  
    **Đáp án:** Không; cần smoke/integration tests/metrics thích hợp.

39. **Cách xử lý app chưa cập nhật sau Maven publication?**  
    **Đáp án:** Kiểm tra CD trigger, artifact digest, environment, rollout và health.

40. **Thông điệp quan trọng nhất bài học?**  
    **Đáp án:** Maven `deploy` = **publish artifact**, application deployment = **đưa bản chạy vào môi trường và xác minh nó hoạt động**.

## 38. Checklist kiểm chứng trước khi release

### Publication phía Maven

- [ ] Chạy Maven/JDK/Plugin versions được dự án phê duyệt.
- [ ] Chạy đủ test/quality gates trước publication.
- [ ] Biết artifact coordinates gồm groupId/artifactId/version/packaging/classifier.
- [ ] Kiểm tra `distributionManagement` hoặc alternate repository URL đúng môi trường.
- [ ] Release đi repository releases, SNAPSHOT đi snapshots theo policy.
- [ ] Server IDs của settings khớp repository IDs.
- [ ] Không commit token/password vào Git hoặc ghi secrets vào logs.
- [ ] Không dùng `maven.deploy.skip=true` ngoài ý muốn.
- [ ] Không nhầm `install` local với `deploy` remote.
- [ ] Kiểm tra JAR/WAR/POM và attached artifacts ở repository.
- [ ] Kiểm tra checksum/digest/signature/provenance khi release yêu cầu.
- [ ] Không overwrite release version đã published.
- [ ] Khi multi-module, kiểm soát partial deploy và hiểu giới hạn `deployAtEnd`.
- [ ] Khi dùng alternate repo, review ID/URL/credential binding.
- [ ] Lưu Maven build logs và publication metadata.

### Rollout phía application

- [ ] CD chọn chính xác artifact/image version/digest đã kiểm thử.
- [ ] JDK/JRE/runtime version phù hợp môi trường mục tiêu.
- [ ] Đường dẫn binary/image trong runtime đúng.
- [ ] Config/secret/service account theo principle of least privilege.
- [ ] Startup command, port và network binding đúng.
- [ ] Health/readiness/smoke tests đạt.
- [ ] Logs/metrics/error rates được giám sát.
- [ ] Có lịch sử deployment và rollback plan.
- [ ] Tách staging và production endpoints/credentials.
- [ ] Không xem Maven BUILD SUCCESS thay thế health check.
- [ ] Khi dùng Docker, lưu image digest, không chỉ tag.
- [ ] Khi dùng VM/systemd, giữ release directories có thể rollback.
- [ ] Khi rollout thất bại, phân biệt publication error với runtime error.
- [ ] Chỉ cấp quyền môi trường production cho automation/người được ủy quyền.
- [ ] Ghi rõ nguồn binary và target environment trong báo cáo deploy.

## 39. Nguồn chính thức để học tiếp

- [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html): thứ tự `package`, `verify`, `install`, `deploy`.
- [Apache Maven — Maven Deploy Plugin](https://maven.apache.org/plugins/maven-deploy-plugin/): mục đích publication artifacts.
- [Apache Maven — Deploy Plugin Usage](https://maven.apache.org/plugins/maven-deploy-plugin/usage.html): `deploy:deploy`, `deploy:deploy-file`, `distributionManagement`.
- [Apache Maven — deploy:deploy Goal](https://maven.apache.org/plugins/maven-deploy-plugin/deploy-mojo.html): `altDeploymentRepository`, skip, deployAtEnd, retries. Chú ý trang này có thể mô tả version plugin mới hơn bản 3.1.4 được ghim trong lab.
- [Apache Maven — deploy:deploy-file Goal](https://maven.apache.org/plugins/maven-deploy-plugin/deploy-file-mojo.html): publication third-party artifacts/POM.
- [Apache Maven — Deploying Using Alternative Repository](https://maven.apache.org/plugins/maven-deploy-plugin/examples/deploying-with-alt-deployment-repository.html): `id::url` ở plugin 3.x.
- [Apache Maven — Guide to Deployment and Security Settings](https://maven.apache.org/guides/mini/guide-deployment-security-settings.html): `distributionManagement` và `settings.xml/servers`.
- [Apache Maven — Deploying over HTTP, FTP and SSH](https://maven.apache.org/guides/mini/guide-deployment-transports.html): repository transport và file staging.
- [Apache Maven — Maven Settings Reference](https://maven.apache.org/settings.html): cấu hình server credentials và mirrors.
- [Apache Maven — Introduction to Repositories](https://maven.apache.org/guides/introduction/introduction-to-repositories.html): local/remote repository roles.
- [Apache Maven — Maven JAR Plugin](https://maven.apache.org/plugins/maven-jar-plugin/): tạo executable JAR manifest trong lab.
- [Oracle Java 17 — HttpServer API](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html): HTTP server chạy bằng JDK.
- [Oracle Java 17 — jar Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jar.html): đọc entries/manifest để kiểm tra artifact.
- [Kubernetes — Deployments](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/): rollout ứng dụng trong cluster.
- [Kubernetes — Probes](https://kubernetes.io/docs/concepts/configuration/liveness-readiness-startup-probes/): liveness/readiness/startup checks.

**Ghi nhớ:** Khi thấy `mvn deploy`, hãy hỏi **“Artifact được publish đến Maven repository nào?”** Khi thấy “deploy ứng dụng”, hãy hỏi **“Bản chạy nào đã đến môi trường nào, khởi động ra sao, kiểm chứng health và rollback thế nào?”** Hai câu trả lời có thể nằm trong cùng một pipeline, nhưng không thể thay thế cho nhau.
