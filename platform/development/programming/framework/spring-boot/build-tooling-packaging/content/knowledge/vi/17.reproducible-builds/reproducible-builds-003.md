# Kiểm soát SNAPSHOT, phiên bản động và phụ thuộc có thể bị thay thế

Một bản dựng Spring Boot chỉ thật sự **có thể tái lập** khi cùng một tập đầu vào được kiểm soát cho ra cùng dependency graph và artifact theo chính sách đã đặt. Ngay cả khi mã nguồn và `pom.xml`/`build.gradle` không thay đổi, kết quả có thể khác giữa hai máy hoặc hai ngày vì dependency `1.4.0-SNAPSHOT` được xuất bản lại, biểu thức phiên bản động `1.+` chọn bản mới hơn, repository thay thế một file theo cùng tọa độ, hoặc cache Maven/Gradle đang giữ metadata khác nhau.

Bài học này trình bày cách **nhận biết và kiểm soát ba nguồn biến động**: **Maven SNAPSHOT**, **Gradle dynamic/changing dependencies**, và **phụ thuộc/metadata có thể bị thay thế khi resolution**. Bạn sẽ xây một ví dụ Spring Boot Java 17 dùng dependency release cố định; học dùng Maven Enforcer, Maven repository policies, Gradle dependency locking, fail-on-nonreproducible resolution, dependency verification, dependency reports và các quy tắc CI/CD. Mục tiêu không phải chặn mọi bản cập nhật, mà là **biến việc cập nhật thành một quyết định có chủ đích, có log/diff/kiểm thử và có thể rollback**.

Các ví dụ dùng **Spring Boot 3.3.13, Java 17, Gradle 8.x và Maven 3.9.x** như một cấu hình minh họa, không hàm ý đó là các phiên bản mới nhất hoặc là chính sách hỗ trợ hiện tại của nhà cung cấp. Khi triển khai, cần dùng phiên bản plugin/công cụ tương thích với tổ chức và tham chiếu tài liệu đúng nhánh.

## 1. Vì sao cùng commit có thể cho ra hai bản build khác nhau?

Giả sử ứng dụng có dependency:

```text
com.acme:policy-client:1.4.0-SNAPSHOT
```

Ở 09:00, repository nội bộ cung cấp nội dung JAR A. Đến 15:00, nhóm `policy-client` publish một bản SNAPSHOT mới mang cùng base coordinate, nhưng có nội dung JAR B. Nếu developer X dùng cache đã có A còn CI dùng metadata mới và tải B, **cùng `pom.xml` hoặc `build.gradle` có thể biên dịch/chạy test ra kết quả khác nhau**.

Một tình huống khác:

```groovy
dependencies {
    implementation 'org.example:codec-lib:2.+'
}
```

Ở thời điểm 1, Gradle resolve `2.+` thành `2.4.1`; ở thời điểm 2, repository phát hành `2.5.0` và Gradle có thể chọn bản mới khi cache hết hiệu lực hoặc được refresh. Dù module đã có **tọa độ phiên bản cụ thể** lúc chạy (`2.4.1` hay `2.5.0`), **selector trong build script vẫn động**.

Trường hợp thứ ba nguy hiểm hơn: một repository hoặc mirror cho phép **ghi đè artifact release** `com.acme:policy-client:1.4.0` bằng byte khác mà không đổi version. Khi ấy, **pin một version string không đủ**; cần chính sách immutability và xác thực nội dung/nguồn phát hành.

**Ba tình huống khác nhau nhưng có triệu chứng giống nhau:** lỗi chỉ tái hiện trên CI, máy A pass nhưng máy B fail, một hotfix bị “biến mất”, checksum JAR khác dù source không đổi, hoặc runtime gặp `NoSuchMethodError`/`ClassNotFoundException` sau lần build mới.

## 2. Phân biệt fixed, dynamic và changing dependencies

| Khái niệm | Ví dụ | Điều gì có thể thay đổi? | Cách kiểm soát |
| --- | --- | --- | --- |
| **Release version cố định** | `com.acme:policy-client:1.4.0` | Thông thường version đã rõ; **byte vẫn có thể bị thay thế nếu repository cho overwrite** | Repository immutable, dependency verification/checksum, CI logs |
| **Maven SNAPSHOT** | `com.acme:policy-client:1.4.0-SNAPSHOT` | Nội dung artifact sau cùng có thể đổi dù base version giữ nguyên | Tránh trong release; pin/promotion artifact immutable; Enforcer, snapshot repository policy |
| **Gradle dynamic version** | `com.acme:policy-client:1.+`, `[1.0,2.0)`, `latest.release` | **Version được chọn** có thể đổi theo metadata mới | Đổi sang version release tường minh hoặc dependency locking |
| **Gradle changing module** | `1.4.0-SNAPSHOT`, hoặc dependency `changing = true` | **Artifact/metadata của cùng coordinate** có thể đổi | Không dùng cho release, kiểm soát TTL khi develop, chuyển thành immutable release |
| **Maven version range** | `[1.4,2.0)` | Resolver có thể chọn version hợp lệ khác khi repository thay đổi | Tránh range mở trong release; quản lý version cụ thể qua parent/BOM |
| **Substitution/replacement rule** | Thay external module bằng project/local module | **Nguồn/target module được chọn** có thể đổi do rule/configuration | Review substitution, xem dependency graph, dùng lock/CI guard phù hợp |
| **Transitive dependency** | Library A kéo library B | Version B có thể bị thay đổi bởi graph conflict/BOM/repository | Dependency tree/insight và lock tất cả resolved versions khi cần |

Điều quan trọng là phân biệt **dynamic** và **changing**:
- **Dynamic**: selector chưa cố định *version cuối*, ví dụ `2.+` có thể chọn một version mới.
- **Changing**: version string đã cố định nhưng **nội dung JAR/POM/metadata** dưới coordinate đó có thể thay đổi.
- Một dependency có thể có **cả hai đặc tính**, ví dụ dùng một selector động dẫn đến một snapshot module.
- **Dependency locking** giúp pin version của dynamic dependencies, **không** đảm bảo byte của changing module không đổi.

Đối với Maven, cách viết `-SNAPSHOT` là tín hiệu quen thuộc về khả năng thay đổi nội dung; đối với Gradle, khái niệm changing là khả năng rộng hơn, bao gồm artifact được đánh dấu `changing = true`.

## 3. Bản dựng “tái lập” cần ổn định những lớp nào?

Không nên coi `version = '1.0.0'` hoặc `<version>1.0.0</version>` là đủ. Các yếu tố độc lập gồm:

1. **Mã nguồn:** commit, submodule, generated sources, build scripts, file config.
2. **Version selection:** version trực tiếp và transitive của Java dependencies, plugin/parent/BOM, JDK/toolchain.
3. **Artifact identity:** cùng group:artifact:version nhưng **byte của JAR/POM có thể khác** nếu nguồn được phép thay thế.
4. **Repository metadata và thứ tự repository:** mirror, repository policy, artifact publication và cache.
5. **Resolution logic:** Gradle constraints, platforms, forced versions, substitutions, Maven dependencyManagement và scopes.
6. **Build environment:** JDK/Gradle/Maven versions, hệ điều hành/locale/time zone, environment variables, profiles.
7. **Đầu ra archive:** timestamps, file order, filtered resources và build-info metadata có thể khiến hash khác dù code tương đương.

Định nghĩa thực dụng:

```text
reproducible output
  = fixed source + controlled resolved graph + immutable/verified inputs
    + controlled build tools/environment + deterministic packaging
```

Nếu chỉ áp dụng dependency locking mà vẫn dùng một SNAPSHOT bị publish lại, bạn chỉ cố định **phiên bản logic**, không khóa nội dung. Nếu chỉ có SHA-256 của JAR đầu ra mà không giữ nguồn dependency và toolchain, rất khó giải thích vì sao hash thay đổi.

## 4. Maven SNAPSHOT thực sự hoạt động thế nào?

### 4.1. `-SNAPSHOT` là một phiên bản đang phát triển

Dependency Maven:

```xml
<dependency>
    <groupId>com.acme</groupId>
    <artifactId>policy-client</artifactId>
    <version>1.4.0-SNAPSHOT</version>
</dependency>
```

Đây là **đoạn minh họa cho dependency nội bộ giả định**, chỉ chạy được khi tổ chức thực sự có artifact `com.acme:policy-client` và repository tương ứng. Không thêm vào project mẫu runnable ở phần sau.

Trong remote Maven snapshot repository, `1.4.0-SNAPSHOT` có thể được ánh xạ qua `maven-metadata.xml` tới một **timestamped snapshot** như:

```text
policy-client-1.4.0-20261109.031522-7.jar
```

Đây chỉ là hình thức minh họa của version timestamp/build number, **không phải tên file có thật**. Hai lần publish có thể tạo snapshot builds khác nhau trong cùng base version. Consumer vẫn khai báo `1.4.0-SNAPSHOT`; repository metadata quyết định bản phù hợp khi cập nhật.

**Snapshot không phải release:** việc một ngày trước dùng A và hôm sau dùng B **không** có nghĩa source repository bị sửa ngầm; đó có thể chính là hành vi mong đợi của snapshot policy. Vấn đề xảy ra khi muốn build release hoặc debug lịch sử nhưng không ghi nhận/cố định artifact cụ thể.

### 4.2. Local repository và metadata

Maven lưu artifact đã tải trong `~/.m2/repository` (hoặc vị trí cấu hình ở settings). Cùng một base snapshot có thể có metadata/local copy được cập nhật ở các thời điểm khác nhau. Build tool không tự kiểm tra remote mọi lần nếu repository policy/cache chưa yêu cầu.

Hai máy có:
- cùng source commit,
- cùng `pom.xml`,
- cùng JDK,
- **nhưng khác thời điểm nhận snapshot metadata**

vẫn có thể chạy dependency khác nhau. Vì vậy “local chạy tốt” chưa chứng minh CI sẽ lặp lại đúng bit-level inputs.

### 4.3. Phân biệt snapshot dependency và project version

`<version>1.0.0-SNAPSHOT</version>` của **chính project** là khác với dependency `1.4.0-SNAPSHOT`. Có hai chính sách release riêng:
- Không cho publish project dưới SNAPSHOT khi xây bản release chính thức.
- Không cho project release kéo bất kỳ SNAPSHOT dependency nào (trực tiếp **hoặc transitive**).

Maven Enforcer có các rule riêng cho hai mục tiêu này: `requireReleaseVersion` và `requireReleaseDeps`.

## 5. Maven repository policy: `snapshots`, `updatePolicy` và `checksumPolicy`

Maven cho cấu hình repository đối với release/snapshot riêng. Ví dụ **một repository snapshot nội bộ giả định**, đặt trong `<repositories>` của POM, hoặc quản lý tương đương bằng profile/settings phù hợp tổ chức:

```xml
<repositories>
    <repository>
        <id>internal-snapshots</id>
        <url>https://repo.example.invalid/maven-snapshots</url>
        <releases>
            <enabled>false</enabled>
        </releases>
        <snapshots>
            <enabled>true</enabled>
            <updatePolicy>daily</updatePolicy>
            <checksumPolicy>fail</checksumPolicy>
        </snapshots>
    </repository>
</repositories>
```

**Đây là đoạn POM minh họa; `repo.example.invalid` cố ý không phải endpoint hoạt động.** Không chèn nó vào project runnable, và trong môi trường thực dùng repository URL/credentials của tổ chức qua cơ chế an toàn.

`updatePolicy` có các giá trị:
- `always`: kiểm tra metadata cập nhật thường xuyên, phù hợp tác vụ phát triển muốn theo snapshot mới.
- `daily`: mặc định phổ biến, kiểm tra theo ngày.
- `interval:X`: kiểm tra theo khoảng `X` phút.
- `never`: không chủ động kiểm tra cập nhật theo policy thông thường; **không tạo cơ chế version pin hay checksum bất biến**.

`checksumPolicy` có thể là `fail`, `warn` hoặc `ignore`. Đặt `fail` yêu cầu Maven nghiêm hơn với checksum remote nhưng **không thay thế** việc đối chiếu hash tham chiếu tin cậy: một publisher có quyền ghi đè cả artifact **và checksum** vẫn có thể làm đầu vào thay đổi.

Hai namespace cần lưu ý:
- `<repositories>` cung cấp **project dependencies**.
- `<pluginRepositories>` cung cấp **Maven plugins**. Quản trị plugin cũng là một phần của reproducibility; không chỉ pin thư viện Java.

**Release repository nên là bất biến sau khi publish.** Repository manager có thể cấu hình chặn redeploy/overwrite release coordinate, dùng provenance/signature và chính sách promotion. POM consumer không thể tự bảo vệ hoàn toàn nếu tổ chức cho phép thay artifact đã phát hành.

## 6. Maven flags `-U` và `-o`: hữu ích nhưng không phải khóa

Lệnh:

```bash
./mvnw -U dependency:tree
```

`-U` yêu cầu Maven chủ động kiểm tra cập nhật snapshots/metadata theo semantics của phiên bản Maven; nó hữu ích khi nghi máy local đang giữ snapshot cũ. **Nó không bảo đảm reproducibility**: chính nó có thể dẫn tới việc nhận **bản SNAPSHOT mới hơn** so với lần build trước.

Chế độ offline:

```bash
./mvnw -o test
```

`-o` chỉ dùng nội dung đã có trong local repository; nếu dependency/plugin chưa được cache thì build có thể fail. **Offline không chứng minh artifact bất biến**, cũng không đảm bảo hai máy có local repository giống nhau.

Khi debug, so sánh:
- thời điểm/nguồn snapshot,
- Maven repository config và mirror,
- version thực đã resolve,
- POM và JAR bytes/checksum,
- Maven/JDK version.

Không sửa lỗi bằng cách yêu cầu mọi người chạy `-U` hay `-o` vĩnh viễn. Đó là công cụ điều tra, không phải chính sách release.

## 7. Maven dự án mẫu dùng phiên bản release cố định

Để có ví dụ **runnable không cần repository private**, tạo project Spring Boot nhỏ dùng dependency release công khai của Apache Commons Lang3.

Cấu trúc:

```text
repro-demo/
├── pom.xml                       (phương án Maven)
├── settings.gradle               (phương án Gradle)
├── build.gradle                  (phương án Gradle)
└── src/
    ├── main/java/com/example/repro/
    │   └── ReproApplication.java
    └── test/java/com/example/repro/
        └── ReproApplicationTest.java
```

Dùng **Maven hoặc Gradle** làm build tool cho một lần thực hành, không cần cấu hình cả hai. Mã Java bên dưới dùng chung.

### 7.1. Ứng dụng Java 17

`src/main/java/com/example/repro/ReproApplication.java`:

```java
package com.example.repro;

import org.apache.commons.lang3.StringUtils;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;

@SpringBootApplication
public class ReproApplication {

    public static void main(String[] args) {
        try (ConfigurableApplicationContext context =
                     SpringApplication.run(ReproApplication.class, args)) {
            System.out.println("result=" + StringUtils.reverse("repro"));
        }
    }
}
```

Ở ví dụ này, `spring-boot-starter` (không có web starter) chạy application context non-web. Sau khi gọi hàm Commons Lang và đóng context, JVM kết thúc. Dòng do code ứng dụng in ra:

```text
result=orper
```

Những log Spring Boot khác có thể xuất hiện; đừng coi toàn bộ stdout chỉ có một dòng. `StringUtils.reverse("repro")` trả `"orper"` một cách xác định khi dùng Commons Lang phù hợp.

### 7.2. JUnit Jupiter test

`src/test/java/com/example/repro/ReproApplicationTest.java`:

```java
package com.example.repro;

import static org.junit.jupiter.api.Assertions.assertEquals;

import org.apache.commons.lang3.StringUtils;
import org.junit.jupiter.api.Test;

class ReproApplicationTest {

    @Test
    void dependencyHasExpectedBehavior() {
        assertEquals("orper", StringUtils.reverse("repro"));
    }
}
```

Đây là **unit test không cần Spring context**, vì mục tiêu chỉ xác minh hành vi thư viện đã resolve. Test được chạy bằng Maven Surefire/JUnit Jupiter hoặc Gradle `useJUnitPlatform()` ở các cấu hình tương ứng. Nó không phải kiểm tra checksum của dependency, nhưng là một smoke test hữu ích nếu version update làm thay đổi API/hành vi.

### 7.3. POM đầy đủ, dependency release tường minh

`pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>repro-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-lang3</artifactId>
            <version>3.14.0</version>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

POM dùng Spring Boot starter parent để quản lý starter versions và plugin build phù hợp. Dependency Commons Lang `3.14.0` được pin **trực tiếp** để minh họa fixed release; trong dự án khác có thể quản lý tập trung bằng `dependencyManagement` và đồng bộ với BOM, nhưng vẫn phải xác minh **resolved version** thực tế.

Chạy:

```bash
./mvnw clean verify
./mvnw dependency:tree
java -jar target/repro-demo-1.0.0.jar
```

Dùng `mvn` nếu project không có Maven Wrapper. Trên Windows PowerShell dùng `.\mvnw.cmd`. Khi test và build thành công, Maven `package`/`verify` tạo executable JAR với `spring-boot-maven-plugin` và ứng dụng in `result=orper`.

**Hạn chế:** pin Commons Lang trực tiếp không tự khóa mọi transitive dependency, parent, plugin hay byte của một artifact đã bị remote overwrite. Cần các kiểm soát tiếp theo.

## 8. Maven Enforcer: cấm SNAPSHOT khi phát hành

Maven Enforcer có ít nhất hai rule hữu ích:
- `requireReleaseVersion`: dự án hiện tại (và theo mặc định parent) **không** dùng version SNAPSHOT.
- `requireReleaseDeps`: **không** để SNAPSHOT dependencies trong dependency graph, theo mặc định có kiểm tra transitive.

Ví dụ một profile dùng riêng cho release. **Đoạn sau được thêm vào bên trong `<project>` của POM mục 7**, không tạo file POM thứ hai:

```xml
<profiles>
    <profile>
        <id>release-check</id>
        <build>
            <plugins>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-enforcer-plugin</artifactId>
                    <version>3.6.3</version>
                    <executions>
                        <execution>
                            <id>block-snapshot-release</id>
                            <phase>validate</phase>
                            <goals>
                                <goal>enforce</goal>
                            </goals>
                            <configuration>
                                <rules>
                                    <requireReleaseVersion/>
                                    <requireReleaseDeps>
                                        <searchTransitive>true</searchTransitive>
                                    </requireReleaseDeps>
                                </rules>
                                <fail>true</fail>
                            </configuration>
                        </execution>
                    </executions>
                </plugin>
            </plugins>
        </build>
    </profile>
</profiles>
```

Kiểm tra release build:

```bash
./mvnw -Prelease-check clean verify
```

Nếu project version là `1.0.0-SNAPSHOT`, hoặc dependency graph chứa `1.4.0-SNAPSHOT`, quy tắc tương ứng có thể làm build fail ở phase validate. Nếu muốn policy áp dụng **mọi** build, đặt Enforcer plugin/execution dưới `<build><plugins>` không cần profile. Đừng quên bật profile trong **CI release job** nếu bạn dùng cách có profile.

**Chú ý:** `requireReleaseDeps` cấm SNAPSHOT theo quy tắc Maven, nhưng **không tự chứng minh mọi release JAR bất biến** hoặc chặn mọi Maven version ranges. Với release phải kết hợp: fixed versions, immutable repository, plugin/parent version quản lý, checksum/provenance và phát hành chỉ khi CI đạt.

Trong multi-module reactor, profile/rule cần có mặt ở đúng các module được release, thường quản lý tại parent để không bỏ sót module con.

## 9. Maven dependencyManagement, version ranges và BOM

### 9.1. Quản lý version tập trung không đồng nghĩa khóa bytes

Ví dụ trong parent POM:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-lang3</artifactId>
            <version>3.14.0</version>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Module con sau đó khai báo dependency không cần version:

```xml
<dependency>
    <groupId>org.apache.commons</groupId>
    <artifactId>commons-lang3</artifactId>
</dependency>
```

Khi dependency thực sự được dùng, version do management quản lý. **Không** nhầm dependencyManagement với dependency declaration: phần management **không tự đưa thư viện vào classpath**. Nó cũng không thể bảo đảm repository sẽ không thay byte dưới coordinate `3.14.0`.

### 9.2. Maven version ranges

Ví dụ mang tính giải thích, **không dùng cho release của bài thực hành**:

```xml
<dependency>
    <groupId>com.acme</groupId>
    <artifactId>policy-client</artifactId>
    <version>[1.4,2.0)</version>
</dependency>
```

Maven có thể chọn version khác trong khoảng hợp lệ khi repository có release mới. Các cách khai báo mơ hồ như `LATEST`, `RELEASE` (không phù hợp/chịu hạn chế tùy Maven version) cũng nên tránh; đừng áp dụng cú pháp hoặc kỳ vọng giống Gradle `latest.release`. **Đơn giản nhất cho release:** chọn một version cụ thể rồi nâng có kiểm soát qua pull request, dependency report và kiểm thử.

### 9.3. BOM Spring Boot giải quyết vấn đề nào?

`spring-boot-dependencies` BOM cho phép các thư viện trong hệ Spring Boot được đồng bộ theo một tập version tương thích đã kiểm tra. Nó là **quản lý version**, không phải byte lock và không bảo vệ khỏi SNAPSHOT/transitive artifact bị thay thế tại repository.

Nếu chỉ **import BOM** mà không kế thừa `spring-boot-starter-parent`, phải kiểm soát thêm plugin versions/executions (compiler, Surefire, Boot Maven Plugin). Một build không tái lập cũng có thể do Maven plugin được resolve ở version khác, không chỉ Java dependency.

## 10. Maven: tìm dependency nào thực sự đã được chọn

Tại root project:

```bash
./mvnw dependency:tree
./mvnw help:effective-pom -Doutput=target/effective-pom.xml
./mvnw help:effective-settings
```

- `dependency:tree`: xem **direct và transitive dependencies**, những version đã được chọn theo Maven conflict mediation.
- `help:effective-pom`: xem POM sau inheritance, profiles và plugin/dependencyManagement; rất cần khi dùng Spring Boot parent hoặc corporate parent.
- `help:effective-settings`: xem thông tin repository/mirror/profile settings thực tế (cẩn trọng vì output có thể chứa chi tiết môi trường/nội bộ).

Muốn nhắm một nhóm module, Maven Dependency Plugin hỗ trợ filters như:

```bash
./mvnw dependency:tree -Dincludes=org.apache.commons:commons-lang3
```

Kết quả có thể cho biết version thực được chọn và đường phụ thuộc đến nó. Khi điều tra:
- Xác minh `pom.xml` nguồn và effective POM.
- Xem dependency tree và repository mirror.
- So sánh byte/checksum của file trong local repository với giá trị tham chiếu đáng tin.
- Kiểm tra Maven Wrapper và JDK version.
- Tìm SNAPSHOT/range trong cả POM con và POM do parent/imported BOM quản lý.

Không kết luận reproducibility chỉ vì `mvn dependency:tree` hôm nay ra một kết quả; ngày mai khi snapshot metadata/range/repo thay đổi, graph có thể không còn giống.

## 11. Gradle dynamic version là selector, không phải version cụ thể

Một số cách khai báo:

```groovy
dependencies {
    implementation 'com.acme:policy-client:1.+'
    implementation 'com.acme:policy-client:[1.4,2.0)'
    implementation 'com.acme:policy-client:latest.release'
}
```

**Đây là ba ví dụ selector thay thế nhau**, không phải ba dependency nên thêm đồng thời. `com.acme:policy-client` là một **artifact nội bộ giả định**, không thể chạy từ Maven Central theo ví dụ này.

Giải thích:
- `1.+` chọn một version thuộc nhánh 1.x theo thông tin Gradle thấy trong repository.
- `[1.4,2.0)` biểu thị range với 1.4 bao gồm và 2.0 loại trừ.
- `latest.release` là selector status-based của Gradle, **không** tương đương một lệnh “luôn lấy mới nhất bất kể mọi metadata”.
- Sau khi resolve, Gradle dùng version cụ thể, nhưng lựa chọn đó có thể thay đổi khi repository metadata mới được quan sát.

Dynamic versions có thể tiện cho **kênh integration/nightly thử tương thích**. Với production release, chúng có thể khiến hai build từ cùng commit kéo hai versions khác nhau; hãy pin release hoặc tạo/commit **lock state** có quản lý. Phải biết rằng Gradle version constraints/BOM có thể ảnh hưởng version cuối.

## 12. Gradle changing dependencies: cùng version nhưng bytes có thể khác

Ví dụ:

```groovy
dependencies {
    implementation 'com.acme:policy-client:1.4.0-SNAPSHOT'
}
```

Gradle thông thường nhận biết Maven `-SNAPSHOT` là **changing dependency**: cùng base version nhưng remote artifact/metadata có thể được publish lại.

Cũng có thể đánh dấu **một module không có hậu tố SNAPSHOT** là changing khi publisher thực sự cho phép thay đổi:

```groovy
dependencies {
    implementation('com.acme:mutable-client:1.4.0') {
        changing = true
    }
}
```

Đây là cấu hình minh họa cho **nguồn nội bộ có artifact thật**; không dùng với một release đã được tổ chức quy định immutable. `changing = true` chỉ thay **cách Gradle cache/revalidate dependency**, **không** biến dependency thành an toàn hay cố định bytes.

Một số nguồn biến động khác:
- **Version range/direct dependency** từ external metadata thay đổi.
- **Transitive changing dependencies** được thư viện khác kéo vào.
- **Composite build/included build** thay external module bằng project local.
- **Resolution rules** như `dependencySubstitution`, `force` và `eachDependency` làm graph chọn thành phần khác với điều khai báo ban đầu.
- **Repository ordering/mirror** chọn metadata/artifact từ nguồn khác.

Khác biệt cốt lõi: changing dependency là **cùng tọa độ nhưng mutable contents**; substitution là **đổi module/provider được chọn**. Cả hai đều đáng giám sát, nhưng cơ chế kiểm soát khác nhau.

## 13. Gradle dependency cache và `--refresh-dependencies`

Gradle cache riêng:
- Metadata về **dynamic version resolution**, ví dụ `1.+` đang map thành `1.4.2`.
- Metadata và artifacts của **changing module**.
- Tệp binary artifacts tải về, với cơ chế cache dựa trên metadata/checksum phù hợp.

Mặc định điển hình của Gradle cho dynamic/changing là **24 giờ**, có thể điều chỉnh TTL. Vì vậy:
- Máy A đã resolve `1.+` hôm qua còn giữ version cũ.
- Máy B mới build lần đầu thấy version mới.
- CI chạy với cache bị xóa hoặc revalidated có thể chọn graph khác.

Ví dụ điều chỉnh TTL **chỉ trong kênh dev/integration**, không dùng làm chính sách tái lập release:

```groovy
configurations.configureEach {
    resolutionStrategy.cacheDynamicVersionsFor 10, 'minutes'
    resolutionStrategy.cacheChangingModulesFor 0, 'seconds'
}
```

`cacheDynamicVersionsFor` quản lý tuổi cache của **kết quả version selector động**; `cacheChangingModulesFor` quản lý tuổi cache cho **changing module metadata/artifacts**. TTL ngắn làm nhiều remote requests và có thể tăng chi phí/thời gian build.

Tùy chọn:

```bash
./gradlew --refresh-dependencies dependencies
```

yêu cầu Gradle revalidate cached dependency resolution và artifacts phù hợp; **không nhất thiết tải lại mọi JAR nếu artifact được xác minh không đổi**. Nó không khóa version mới nhận được, cũng không thay cho dependency lockfile.

`--offline` chỉ sử dụng nội dung cache đang có; nó giúp làm việc khi không có mạng nhưng **không chứng minh hai máy đang dùng cùng dependency bits**.

## 14. Gradle dự án mẫu dùng phiên bản fixed release

Tạo `settings.gradle`:

```groovy
rootProject.name = 'repro-demo'
```

Tạo `build.gradle` đầy đủ (Groovy DSL) dùng **cùng file Java của mục 7**:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.apache.commons:commons-lang3:3.14.0'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

springBoot {
    mainClass = 'com.example.repro.ReproApplication'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Lưu ý:
- Spring Boot Gradle plugin và dependency management plugin đã được **pin version**.
- Starter dependencies resolve qua BOM phù hợp, và Commons Lang3 được khai báo `3.14.0` tường minh.
- Java toolchain cần Java 17 compiler. JVM chạy Gradle, toolchain và runtime của artifact không nhất thiết giống nhau nếu bạn chưa kiểm soát.
- Không có `1.+`, `latest.release` hay SNAPSHOT trong ví dụ.
- `useJUnitPlatform()` cần cho Gradle chạy JUnit Jupiter tests.
- Cấu hình này tạo executable JAR từ `bootJar`, không yêu cầu thêm một main class nào.

Chạy:

```bash
./gradlew clean test bootJar
./gradlew dependencies --configuration runtimeClasspath
java -jar build/libs/repro-demo-1.0.0.jar
```

Với Java 17 sample, dòng do app in ra là `result=orper`; Gradle có thể in log build và Spring Boot log ngoài dòng này. Trên Windows PowerShell dùng `.\gradlew.bat` khi có Gradle Wrapper. Với project khác tên/version, tìm artifact thật trong `build/libs` thay vì đoán filename.

Cấu hình này **dễ dự đoán hơn** dynamic versions, nhưng chưa phải bảo đảm tuyệt đối về content immutability hoặc deterministic archive. Các bước dưới đây bổ sung kiểm soát.

## 15. Gradle: phát hiện dynamic/changing dependencies bằng fail-fast

Khi muốn một **release build tuyệt đối không chứa dynamic/changing resolution**, có thể đặt quy tắc ở project phù hợp:

```groovy
configurations.configureEach {
    resolutionStrategy {
        failOnNonReproducibleResolution()
    }
}
```

Đây là **đoạn bổ sung** vào `build.gradle` hoặc convention plugin của **release module** có những configurations cần kiểm tra. Gradle `ResolutionStrategy.failOnNonReproducibleResolution()` tương đương:
- `failOnDynamicVersions()`;
- `failOnChangingVersions()`.

Nếu dependency graph có dynamic selector hoặc changing module khiến resolution được đánh giá không ổn định, Gradle fail khi resolve. Đây là một **guardrail**, không cần chạy thủ công danh sách dependency để phát hiện mọi trường hợp.

Hai chế độ chọn policy:

```groovy
// Chỉ phát hiện dynamic version selection:
configurations.configureEach {
    resolutionStrategy.failOnDynamicVersions()
}
```

```groovy
// Chỉ phát hiện changing version/artifact:
configurations.configureEach {
    resolutionStrategy.failOnChangingVersions()
}
```

Ba đoạn này là **các lựa chọn** (đoạn đầu đã bao gồm hai guard riêng), không cần đặt cả ba chồng lên nhau.

**Phạm vi:** áp dụng cho configurations được xử lý trong project. Nó **không tự quét mọi plugin classpath của settings, mọi included build, mọi artifact tải bằng script bên ngoài hoặc mọi CI image**. Vì vậy cần kiểm soát plugin versions, buildscript dependencies, toolchain và repositories riêng.

**Không nhầm `failOnVersionConflict()`:** đó là chính sách xử lý *hai version khác nhau của cùng module*, không phải guard chuyên dụng chống SNAPSHOT/dynamic versions. Một graph có thể không có conflict nhưng vẫn dùng `1.+` và không ổn định.

## 16. Gradle dependency locking: cố định resolved versions

Nếu dự án cần dùng dynamic selectors trong một giai đoạn phát triển nhưng vẫn muốn build ổn định, Gradle có **dependency locking**: lưu lại **versions đã resolve**, kể cả transitive, trong lock state.

Thêm vào `build.gradle`:

```groovy
dependencyLocking {
    lockAllConfigurations()
}
```

**Bước 1 — tạo lock state** bằng cách resolve những configurations cần khóa. Với project đơn:

```bash
./gradlew dependencies --write-locks
```

Gradle tạo `gradle.lockfile` ở project tương ứng cho các configurations đã resolve, với các dòng mang dạng:

```text
org.apache.commons:commons-lang3:3.14.0=compileClasspath,runtimeClasspath
...
```

Đây là **trích đoạn minh họa**; file thực chứa nhiều modules và configurations tùy project. **Commit lockfile vào Git**, review diff như với source code. Không chỉnh lockfile thủ công theo cảm tính.

**Bước 2 — build bình thường:**

```bash
./gradlew clean test bootJar
```

Khi lock state đã có, Gradle dùng các ràng buộc version để đảm bảo graph không âm thầm chuyển sang version mới ngoài lock. Nếu khai báo dependency thay đổi không tương thích với lock, resolution có thể fail và yêu cầu cập nhật lock có chủ đích.

**Bước 3 — cập nhật có kiểm soát:**

```bash
./gradlew dependencies --update-locks org.apache.commons:commons-lang3
```

Lệnh này cho Gradle cập nhật module chỉ định trong lock state trong chừng mực dependency graph yêu cầu; các module liên quan vẫn có thể bị ảnh hưởng. Review **toàn bộ diff lockfile** và chạy lại test/build/smoke test. Nếu project có nhiều configurations, đảm bảo chúng thật sự được resolve khi sinh/cập nhật lock.

**Trong multi-project:** `./gradlew dependencies --write-locks` không nhất thiết resolve **mọi subproject**; gọi các task project cụ thể, ví dụ `./gradlew :app:dependencies --write-locks` hoặc quy trình resolver chung được thiết kế rõ. Đừng xem lockfile root là bằng chứng toàn repository đã được khóa.

### 16.1. Lockfile không giữ nguyên byte của SNAPSHOT

Đây là giới hạn quan trọng nhất của dependency locking:

```text
locked coordinate:
com.acme:policy-client:1.4.0-SNAPSHOT

Ngày 1: JAR sha256 = A...
Ngày 2: JAR sha256 = B... (cùng coordinate)
```

Một lock state ghi **cùng version string `1.4.0-SNAPSHOT`**, nên **không bảo đảm giữ byte của artifact**. Gradle cũng cảnh báo khi persist lock cho changing dependencies. Đối với production, chuyển sang **release immutable** hoặc artifact content-addressed/được promotion có policy tương đương, sau đó dùng dependency verification/checksum ở nơi phù hợp.

**Lockfile giải quyết version selection**, không tự quản lý toàn bộ artifact provenance. Đây là lý do nên phối hợp lock và kiểm soát repository publishing, thay vì nghĩ “đã có `gradle.lockfile` nên SNAPSHOT an toàn”.

## 17. Gradle dependency verification: kiểm tra file đã nhận có đúng không?

Gradle cung cấp **dependency verification** dựa trên checksums hoặc chữ ký để kiểm tra artifact và metadata nhận được. File metadata thường nằm ở:

```text
gradle/verification-metadata.xml
```

Có thể bootstrap thông tin checksum SHA-256:

```bash
./gradlew --write-verification-metadata sha256 dependencies
```

Gradle sẽ resolve dependencies tương ứng và tạo/cập nhật metadata kiểm tra. **Quan trọng:** quá trình bootstrap dùng artifact repository hiện đang cung cấp, **không tự xác minh nguồn đó đáng tin**. Phải review file tạo ra, đối chiếu publisher/repository tin cậy và commit metadata sau khi được phê duyệt.

Ví dụ cấu trúc **minh họa một phần, không phải file metadata hoàn chỉnh**:

```xml
<components>
    <component group="org.apache.commons" name="commons-lang3" version="3.14.0">
        <artifact name="commons-lang3-3.14.0.jar">
            <sha256 value="CHECKSUM_DUOC_XAC_MINH"/>
        </artifact>
    </component>
</components>
```

`CHECKSUM_DUOC_XAC_MINH` chỉ là **ký hiệu giải thích**, **không phải hash hợp lệ để copy vào file dùng thật**. Hãy để Gradle sinh metadata, kiểm tra các hash và dùng schema đầy đủ của Gradle. Không chép đoạn XML rút gọn này làm file `verification-metadata.xml`.

**Giới hạn đặc biệt:** Gradle dependency verification **không xác minh changing dependencies như SNAPSHOT** theo cách kiểm tra immutable modules thông thường, vì nội dung của chúng có thể đổi liên tục; cũng không xác minh các artifact được build local theo cơ chế dependency verification này. Không dùng tính năng verification như lý do để chấp nhận SNAPSHOT trong release.

Checksum và chữ ký có tác dụng khác nhau:
- **Checksum SHA-256:** phát hiện byte khác với giá trị tham chiếu.
- **Chữ ký:** có thể chứng minh provenance dựa trên key/trust được cấu hình đúng.
- Kết hợp chúng giúp giảm rủi ro, nhưng không thay thế code review, vulnerability scanning hay chính sách phát hành.

Khi checksum mismatch, **không tự xóa metadata rồi ghi lại hash mới để cho CI xanh**; phải xác minh xem publisher đã thay đổi artifact hợp lệ, cache lỗi, mirror thay nguồn hay có nguy cơ bị tấn công.

## 18. Gradle substitutions, version conflicts và “phụ thuộc bị thay thế”

Ngoài mutable artifacts, một số build thay **đối tượng dependency** bằng rules:

```groovy
// Chỉ là ví dụ khi cùng build CÓ subproject ':policy-client'.
configurations.configureEach {
    resolutionStrategy.dependencySubstitution {
        substitute module('com.acme:policy-client') using project(':policy-client')
    }
}
```

Đây là một **snippet có điều kiện**, không chèn vào project mẫu `repro-demo` vì project đó không có subproject `:policy-client`. Trong một multi-project/composite build hợp lệ, rule có thể khiến consumer dùng **local project output** thay cho Maven repository module. Chúng là **hai nguồn byte khác nhau**, ngay cả khi tên dependency mà developer nhập ban đầu không đổi.

Những tình huống tương tự:
- `includeBuild(...)` trong composite build có thể áp dụng **dependency substitution** theo coordinates của included build, tùy settings.
- `resolutionStrategy.force(...)` ép một version có thể che mâu thuẫn giữa thư viện.
- `eachDependency` rules và component selection rules có thể thay selected version/module.
- `platform(...)`, BOM, version constraints và Gradle variant-aware selection có thể thay graph cuối so với các dependency strings khai báo đơn lẻ.

**Không đánh đồng substitution với SNAPSHOT:** substitution là chọn **producer/module khác**, changing dependency là một producer/coordinate có **bytes thay đổi**. Cả hai đều tác động độ tái lập, nhưng phải nhìn vào **resolved component graph**, không chỉ đọc một dòng `implementation`.

Lệnh chẩn đoán:

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency commons-lang3 --configuration runtimeClasspath
./gradlew buildEnvironment
```

`dependencies` cho biết graph; `dependencyInsight` giúp xem vì sao version được chọn; `buildEnvironment` giúp kiểm tra buildscript dependencies ở phạm vi phù hợp. Nếu dùng multi-project, chạy trên đúng module, ví dụ `:boot-app:dependencies`, không tự suy luận root project đã đại diện tất cả.

## 19. Fixed version, BOM, version catalog và lockfile khác nhau thế nào?

| Công cụ/kỹ thuật | Giải quyết vấn đề gì? | Không giải quyết được gì? |
| --- | --- | --- |
| **Fixed version literal** | Chọn tọa độ version tường minh ở một dependency | Byte bị overwrite, transitive conflicts, plugin environment |
| **Maven dependencyManagement / BOM** | Quản lý/alignment các versions theo một tập | Không khóa bytes hoặc chặn repository mutable |
| **Gradle version catalog** | Đặt alias/versions tập trung cho team, giảm copy/paste | Không tự khóa transitive graph hay artifact contents |
| **Gradle dependency locking** | Pin **resolved module versions**, kể cả transitive trong locked configurations | Không pin bytes của changing modules |
| **Gradle dependency verification** | So sánh hash/chữ ký của immutable dependencies/artifacts trong phạm vi hỗ trợ | Không xác minh changing snapshots như immutable artifacts; không chọn version thay bạn |
| **Maven Enforcer release rules** | Fail khi project/dependency chứa SNAPSHOT theo policy | Không chứng minh release JAR remote không bị overwrite |
| **Immutable artifact repository** | Ngăn thay byte của một tọa độ release đã publish | Không tự chọn version ổn định nếu build vẫn dùng `1.+` |
| **Java toolchain/Wrapper + deterministic packaging** | Giảm khác biệt môi trường và đầu ra archive | Không tự pin đầy đủ dependency graph |

**Không có nút duy nhất “bật reproducible builds”.** Cần kết hợp versioning, artifact immutability, resolution policy và kiểm thử chính output được deploy.

## 20. Quy trình nâng cấp dependency an toàn

Thay vì dùng `1.+` để tự lấy release mới mỗi ngày, tổ chức có thể áp dụng chu trình:

1. **Phát hiện bản cập nhật** qua tooling/renovation bot hoặc danh sách release chính thức.
2. **Tạo PR** đổi một version tường minh hoặc nhóm versions do BOM quản lý.
3. **Giữ nguyên phiên bản base/plugin/JDK** ngoài phạm vi thay đổi nếu không có lý do nâng cấp.
4. **Cập nhật Gradle lockfiles** nếu đang dùng locking; không tự sửa file để lừa resolver.
5. **Cập nhật dependency verification metadata** theo cơ chế được chấp nhận; review checksum/signature từ nguồn tin cậy.
6. **Kiểm tra dependency graph diff**: direct và transitive, giải thích thay đổi version bất ngờ.
7. **Chạy unit/integration tests, smoke test executable JAR**, kiểm tra manifest và nested libraries.
8. **Review SBOM/provenance** và security scan nếu policy yêu cầu.
9. **Promote immutable release artifact** tới registry triển khai, lưu checksum, build ID và commit reference.
10. **Cho phép rollback** về artifact đã phát hành, không phải rebuild lại từ một SNAPSHOT mutable.

Với một dependency nội bộ chưa phát hành release ổn định, có thể dùng SNAPSHOT trong **integration/dev pipeline** để phát hiện vấn đề sớm. Nhưng **đầu vào production** nên là một version/content immutable được promotion hoặc một revision được kiểm soát bằng quy trình tương đương.

### 20.1. Không dùng `--refresh-dependencies` hoặc `-U` để thay quy trình nâng cấp

Hai tùy chọn có thể buộc resolver nhìn metadata mới, nhưng không tạo PR, không giữ báo cáo về version cũ, không gắn checksum đáng tin và không kiểm tra regression. Khi có lỗi khó tái hiện, chính thao tác “refresh” ngẫu nhiên còn có thể làm mất bản snapshot gây lỗi trong cache.

## 21. CI: phân biệt integration nightly với release

Một policy rõ ràng nên có ít nhất hai chế độ:

| Môi trường | Có thể dùng SNAPSHOT/dynamic? | Mục tiêu |
| --- | --- | --- |
| **Developer sandbox** | Có kiểm soát, nếu cần tích hợp với module đang phát triển | Phản hồi nhanh, chấp nhận thay đổi đầu vào |
| **Integration/nightly** | Có thể thử latest/snapshot, với logs đầy đủ | Phát hiện không tương thích sớm; thất bại không trực tiếp phát hành |
| **Pull request validation** | Ưu tiên resolved versions cố định/lockfile | Re-run tương đối ổn định và review thay đổi dependency |
| **Release candidate/production** | **Không** dùng mutable SNAPSHOT/dynamic selector | Có bằng chứng version, checksum/provenance và artifact immutable |

Đối với **Maven release job**:

```bash
./mvnw -B -Prelease-check clean verify
./mvnw dependency:tree
```

Đảm bảo Enforcer profile `release-check` đã tồn tại như mục 8. Những lệnh này không tự cấm repository overwrite; cần repository policy và artifact verification ngoài.

Đối với **Gradle release job**:

```bash
./gradlew clean test bootJar
./gradlew dependencies --configuration runtimeClasspath
```

Dùng `failOnNonReproducibleResolution()` và/hoặc dependency locking, verification metadata theo policy đã commit. Với các module có source riêng, cần thực thi đúng tasks/configurations; **chỉ chạy root `dependencies` không chứng minh mọi subproject đều sạch**.

Trong cả hai, ghi nhận:
- Source commit và build ID.
- Version JDK/Maven/Gradle Wrapper và Spring Boot plugin/parent.
- Resolved dependency graph/SBOM.
- Artifact filename và SHA-256.
- Test reports và thông tin về resource/packaging.
- Repository/mirror policy dùng lúc build (không ghi secret).
- Đường dẫn artifact mà deployment thực nhận.

Cảnh báo trong pipeline nếu có snapshot dependency, dynamic version, snapshot plugin hoặc dependency substitution ngoài policy. Không đưa secret repository vào log.

## 22. Kiểm tra Spring Boot executable JAR đã nhận đúng dependency

Ngay cả khi build pass, hãy kiểm tra **artifact thật**. Với Gradle demo:

```bash
jar tf build/libs/repro-demo-1.0.0.jar
```

Với Maven demo:

```bash
jar tf target/repro-demo-1.0.0.jar
```

Một Spring Boot executable JAR bình thường sẽ có:
- `META-INF/MANIFEST.MF`;
- `BOOT-INF/classes/com/example/repro/ReproApplication.class`;
- `BOOT-INF/lib/commons-lang3-3.14.0.jar`;
- các Spring Boot runtime dependencies cần thiết trong `BOOT-INF/lib`.

**Tên các file trên là kỳ vọng của ví dụ**, không phải kết quả đo thực tế. Dùng `jar tf` để xác minh. Java runtime classpath của Boot JAR được Boot launcher dựng từ ứng dụng và nested JARs.

Nếu artifact thiếu Commons Lang:
1. Kiểm tra Gradle `runtimeClasspath` hoặc Maven `dependency:tree`.
2. Xác minh dependency scope/configuration và exclusions.
3. Kiểm tra bạn đã chọn đúng `bootJar` / Maven repackage output chứ không phải plain JAR.
4. Nếu có dependency substitution, xem có chuyển dependency thành project khác không.
5. Chạy `java -jar` để tái hiện và xem root cause.

Đối với Gradle:

```bash
./gradlew dependencyInsight --dependency commons-lang3 --configuration runtimeClasspath
```

Đối với Maven:

```bash
./mvnw dependency:tree -Dincludes=org.apache.commons:commons-lang3
```

Lưu ý **sự hiện diện của một nested JAR không bảo đảm version của mọi transitive dependency tương thích**. Kiểm tra graph, chạy test và lưu checksum của artifact deploy.

## 23. Giữ đầu ra archive cũng có thể tái lập

Phụ thuộc có version ổn định chưa chắc tạo ra **JAR byte-identical** nếu quá trình package chèn timestamps, build host/user, đường dẫn tuyệt đối hoặc thứ tự tệp khác nhau.

Những nguyên tắc bổ sung:
- Dùng Java toolchain/Wrapper và plugin versions cố định.
- Kiểm soát locale/timezone/time source khi chương trình sinh resource phụ thuộc môi trường.
- Chọn các chế độ **reproducible file order** và **normalized entry timestamps** theo archive plugin hiện dùng; không bật tùy tiện khi archive có chữ ký/định dạng đặc thù.
- Nếu Maven plugin hỗ trợ `project.build.outputTimestamp` / reproducible build features, xem tài liệu đúng version và thiết lập rõ khi cần byte-identical outputs.
- Tránh nhúng `Instant.now()`, hostname, đường dẫn máy vào resource build theo cách không ổn định, trừ khi đó là metadata được thiết kế có chủ đích.
- Kiểm tra checksum SHA-256 giữa **hai build có môi trường và inputs được chuẩn hóa**; không mặc định chỉ cần `mvn clean` hay `gradle clean` thì bytes sẽ giống.

Ví dụ checksum Linux/macOS:

```bash
sha256sum build/libs/repro-demo-1.0.0.jar
sha256sum target/repro-demo-1.0.0.jar
```

Đây là lệnh cho **hai phương án build khác nhau**, không kỳ vọng Maven JAR và Gradle JAR có cùng SHA-256, vì plugin/layout/metadata có thể khác. Chỉ so sánh hai bản của **cùng toolchain, cùng cấu hình, cùng source/input set**.

Windows PowerShell:

```powershell
Get-FileHash -Algorithm SHA256 .\build\libs\repro-demo-1.0.0.jar
```

Checksum của executable JAR khác checksum của một dependency JAR. Để biết dependency bị thay byte, cần kiểm tra chính dependency artifact hoặc metadata trust đã lưu, không chỉ nhìn hash của JAR cuối rồi phỏng đoán.

## 24. Những lỗi và ngộ nhận thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Cùng commit, hôm qua pass hôm nay fail | Snapshot được republish, dynamic selector chọn release mới, repository/mirror thay | Xem resolved graph, snapshot metadata, cache policy, checksums |
| `1.+` hôm nay ra `1.5` | Version selector động, TTL/cache metadata hết hạn | Pin version hoặc commit lockfile đã review |
| `1.4.0-SNAPSHOT` giữ version nhưng chạy khác | Changing module có artifact bytes mới | Không dùng cho release, promote immutable release |
| Maven `-U` làm build đổi dependency | Resolver kiểm tra metadata/snapshots mới | Dùng để debug có chủ đích, không dùng như pin |
| Maven `-o` chạy được chỉ trên máy A | Local repository/cache không giống CI | Cố định inputs và repo, không dựa vào offline alone |
| Maven Enforcer không fail khi release có snapshot | Profile chưa bật, rule không có ở module, policy chưa áp dụng | Bật `-Prelease-check`, kiểm tra effective POM |
| `requireReleaseVersion` pass nhưng còn snapshot dependency | Nó chỉ kiểm tra project version | Bổ sung `requireReleaseDeps` |
| `requireReleaseDeps` pass nhưng release artifact bị overwrite | Rule phát hiện SNAPSHOT, không chứng minh immutability | Release repository no-redeploy + checksum/trust |
| Gradle có lockfile nhưng SNAPSHOT vẫn khác | Lock giữ version, không giữ bytes changing module | Loại SNAPSHOT khỏi release, quản trị artifact registry |
| Gradle `--refresh-dependencies` bị hiểu là tải lại tất cả | Nó revalidate metadata/cache và chỉ tải khi cần | Dùng đúng mục đích điều tra |
| Gradle `failOnDynamicVersions()` không cấm SNAPSHOT cố định | Dynamic và changing là hai điều kiện riêng | Dùng `failOnNonReproducibleResolution()` hoặc guard cả hai |
| Gradle verification không phát hiện SNAPSHOT đổi | Changing deps nằm ngoài phạm vi checksum verification thường | Không coi verification là khóa SNAPSHOT |
| Version catalog chứa `3.14.0` nhưng transitive đổi | Catalog quản lý khai báo, không khóa tất cả resolved graph | Lock dependencies và xem insight |
| BOM Spring Boot có mà module khác version | BOM/constraints/conflict/substitution tác động resolution | Xem Gradle dependencyInsight / Maven dependency tree |
| Build chạy local khác CI dù pin versions | Plugin, JDK, repository, environment, generated metadata khác | Pin Wrapper/toolchain và đối chiếu logs |
| `NoSuchMethodError` xuất hiện ở runtime | Version conflict/incompatible dependency hoặc artifact bị thay | Xem graph và nội dung nested JAR, chạy tests |
| Gradle project local thay remote module | Dependency substitution/composite build | Review `includeBuild`, substitution rules, selected component |
| Release manifest/metadata bị thay đổi ở mỗi lần build | Timestamp, build-info, file order không được chuẩn hóa | Sử dụng reproducible archive settings phù hợp |
| Maven dependency tree hôm nay ổn nhưng tháng sau khác | Snapshot, version range, repository mutable | Chốt fixed versions, enforcer/repository policy |
| CI chọn nhầm `-plain.jar` | Wildcard artifact selection | Chỉ định đúng executable Boot JAR và kiểm tra `java -jar` |

## 25. Checklist cho pull request và bản phát hành

- [ ] Không khai báo `-SNAPSHOT`, version range/dynamic selector hoặc `latest.*` trong **release dependency graph** nếu chính sách không cho phép.
- [ ] Maven release job bật `requireReleaseVersion` và `requireReleaseDeps` ở đúng module/POM.
- [ ] Maven parent/BOM/plugin versions được quản lý và kiểm tra qua `help:effective-pom`.
- [ ] Repository release chặn overwrite/redeploy cùng tọa độ; snapshot repository tách riêng và có TTL/policy rõ ràng.
- [ ] Maven `-U`/`-o` chỉ được dùng có chủ đích, không được coi là bằng chứng reproducibility.
- [ ] Gradle release có guard `failOnNonReproducibleResolution()` **hoặc** quy trình locking/policy kiểm soát dynamic/changing phù hợp.
- [ ] Gradle lockfile đã được tạo từ các configurations thật, commit và review toàn bộ diff.
- [ ] Không dùng Gradle lockfile như cơ chế pin **bytes** của `-SNAPSHOT`.
- [ ] Dependency verification metadata/checksums được review từ nguồn tin cậy; không tự chấp nhận hash mới khi mismatch.
- [ ] Mọi dependency substitutions/composite build và Gradle resolution rules ảnh hưởng release đã được review.
- [ ] JDK, Gradle/Maven Wrapper, Spring Boot plugin/parent và BOM version được ghi nhận.
- [ ] Dependency tree/insight, test reports và artifact checksum được lưu cùng build provenance.
- [ ] JAR triển khai thật có đúng `BOOT-INF/classes`, `BOOT-INF/lib` và được chạy smoke test.
- [ ] Khi cập nhật version, dùng PR/CI với quyền rollback, không thay đổi artifact cũ dưới cùng release coordinate.
- [ ] Kết quả build từ cùng inputs và môi trường được chuẩn hóa có thể đối chiếu/giải thích khi checksum khác.

**Ghi nhớ:** **Phiên bản cố định** giúp giữ *chọn version*, **lockfile** giúp giữ *resolved dependency graph*, **immutable repository + checksum/provenance** giúp giữ *nội dung artifact*, còn **toolchain và deterministic packaging** giúp giữ *đầu ra*. SNAPSHOT, dynamic selectors và substitution có thể hữu ích trong phát triển, nhưng **không được âm thầm chảy vào release pipeline** nếu mục tiêu là tái lập và rollback đáng tin.

## Tài liệu tham khảo chính thức

- [Apache Maven — Settings Reference, repositories/snapshots/updatePolicy/checksumPolicy](https://maven.apache.org/settings.html)
- [Apache Maven Enforcer — Require Release Dependencies](https://maven.apache.org/enforcer/enforcer-rules/requireReleaseDeps.html)
- [Apache Maven Enforcer — Require Release Version](https://maven.apache.org/enforcer/enforcer-rules/requireReleaseVersion.html)
- [Apache Maven — Guide to Working with Multiple Modules](https://maven.apache.org/guides/mini/guide-multiple-modules.html)
- [Gradle — Declaring Versions and Ranges](https://docs.gradle.org/current/userguide/dependency_versions.html)
- [Gradle — Dependency Caching](https://docs.gradle.org/current/userguide/dependency_caching.html)
- [Gradle — Locking Versions](https://docs.gradle.org/current/userguide/dependency_locking.html)
- [Gradle — Dependency Verification](https://docs.gradle.org/current/userguide/dependency_verification.html)
- [Gradle — ResolutionStrategy](https://docs.gradle.org/current/dsl/org.gradle.api.artifacts.ResolutionStrategy.html)
- [Gradle — Resolution Rules and Dependency Substitution](https://docs.gradle.org/current/userguide/resolution_rules.html)
- [Spring Boot 3.3 — Gradle Plugin Packaging](https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging.html)
- [Spring Boot 3.3 — Maven Plugin Packaging](https://docs.spring.io/spring-boot/3.3/maven-plugin/packaging.html)