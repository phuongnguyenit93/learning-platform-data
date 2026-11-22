# Phiên bản release và SNAPSHOT trong phát triển nhiều mô-đun Maven

## 1. Mục tiêu và vấn đề thực tế

Một reactor Maven có parent/aggregator, thư viện và ứng dụng:

~~~text
hello-parent  1.3.0-SNAPSHOT   packaging=pom
hello-api     1.3.0-SNAPSHOT   packaging=jar
hello-cli     1.3.0-SNAPSHOT   packaging=jar
  └── depends on hello-api:1.3.0-SNAPSHOT
~~~

Khi phát hành `1.3.0`, không chỉ root `<version>` cần thay đổi: hai child `<parent><version>` cũng cần trỏ đúng parent mới, còn CLI phải yêu cầu đúng phiên bản API. Nếu CLI tiếp tục yêu cầu `hello-api:1.3.0-SNAPSHOT`, nó có thể tải một SNAPSHOT cũ trong local/remote repository, thậm chí khi module API `1.3.0` vừa được build.

Một vòng đời minh họa:

~~~text
1.3.0-SNAPSHOT (development) -> 1.3.0 (release) -> 1.4.0-SNAPSHOT (next development)
~~~

Phiên bản sau release có thể là `1.3.1-SNAPSHOT`, `1.4.0-SNAPSHOT` hoặc `2.0.0-SNAPSHOT` theo kế hoạch; **Maven không tự bắt buộc nâng minor/patch như trong ví dụ**.

**Quy tắc cốt lõi:** project version là một phần của **Maven artifact coordinates**. Reactor không tự thay thế dependency có sai version chỉ vì hai artifactIds nằm trong cùng `<modules>`. Bài này hướng dẫn chiến lược phát triển/phát hành, mô hình POM nhất quán và cách kiểm chứng thực tế trên Maven 3 + Java 17.

## 2. Maven coordinates và phiên bản

Một POM có:

~~~xml
<groupId>org.example.versions</groupId>
<artifactId>hello-api</artifactId>
<version>1.3.0-SNAPSHOT</version>
<packaging>jar</packaging>
~~~

Tọa độ chính của artifact:

~~~text
org.example.versions:hello-api:1.3.0-SNAPSHOT
~~~

Trong khi đó release tương ứng là một tọa độ **khác**:

~~~text
org.example.versions:hello-api:1.3.0
~~~

Maven có thể resolve hai artifacts khác nhau, đặt ở những repository folders khác nhau. Artifact coordinates gồm groupId, artifactId, version và có thể xét thêm type/extension, classifier. `packaging` nói về loại sản phẩm/lifecycle, `build.finalName` ảnh hưởng tên file được đóng gói trong `target/`, nhưng **đổi filename bằng shell không đổi version GAV**.

Những khái niệm version khác nhau:

- `project.version=1.3.0-SNAPSHOT`: định danh Maven artifact.
- `maven.compiler.release=17`: cấu hình Java language/API/bytecode target.
- `maven-compiler-plugin:3.13.0`: version của build plugin.
- `junit-jupiter:5.11.4`: version của một test dependency.
- `hello-api:1.3.0-SNAPSHOT`: version của dependency nội bộ.

Đừng dùng một con số phiên bản cho tất cả chỉ vì chúng cùng được ghi trong POM.

## 3. Release và SNAPSHOT khác nhau về hợp đồng

| Thuộc tính | SNAPSHOT | Release |
| --- | --- | --- |
| Ví dụ | `1.3.0-SNAPSHOT` | `1.3.0` |
| Ý nghĩa | Phiên bản đang phát triển. | Phiên bản đã được công bố. |
| Tính ổn định bytes | Có thể thay đổi sau mỗi lần deploy snapshot mới. | **Nên bất biến** theo repository policy. |
| Nơi phân phối thường gặp | Snapshot repository. | Release repository. |
| File remote | Có thể mang timestamp/build number. | Thường tên `artifactId-version.jar`. |
| Cache | Metadata/updatePolicy ảnh hưởng phiên bản snapshot đang resolve. | Consumer kỳ vọng cùng coordinates là cùng bytes. |
| Rủi ro | Hai build cùng source/POM có thể tải binary khác. | Repo cho overwrite có thể phá tính bất biến. |

Tài liệu Apache Maven Getting Started coi SNAPSHOT là một bản đang phát triển, không cam kết nội dung không đổi. Bản release thể hiện mốc phát hành đáng tin cậy hơn, nhưng **không có nghĩa tự động không còn bug**.

Không có suffix `-SNAPSHOT` **không tự khóa quyền ghi repository**. Cần cấu hình release repo chặn overwrite, lưu artifact checksum, source tag và provenance nếu muốn bảo đảm có thể kiểm toán và tái lập.

## 4. Parent, aggregator và dependency không phải một

Trong multi-module Maven có ba mối quan hệ:

1. **Parent inheritance:** child khai báo `<parent>` để kế thừa `groupId`, `version`, properties, dependency/plugin management.
2. **Aggregator:** root khai báo `<modules>` để Maven reactor thu thập/build những project con.
3. **Dependency:** CLI khai báo `<dependencies>` để thực sự dùng API JAR.

Ví dụ aggregator:

~~~xml
<modules>
    <module>hello-api</module>
    <module>hello-cli</module>
</modules>
~~~

Ví dụ dependency trong CLI:

~~~xml
<dependency>
    <groupId>org.example.versions</groupId>
    <artifactId>hello-api</artifactId>
    <version>1.3.0-SNAPSHOT</version>
</dependency>
~~~

Maven reactor sắp build API trước CLI nếu dependency thật trỏ đúng artifact/module API đang có trong reactor. Nếu CLI yêu cầu API `1.2.0-SNAPSHOT` trong khi API reactor đang là `1.3.0-SNAPSHOT`, hai tọa độ không khớp; Maven có thể dùng artifact cũ từ repository hoặc fail. Đổi thứ tự danh sách modules **không khắc phục** lỗi GAV.

`dependencyManagement` quản lý version nhưng không tự tạo dependency. `pluginManagement` quản lý plugin configuration nhưng không tự tạo mọi custom execution. Reactor ưu tiên những quan hệ project đã được khai báo thực sự.

## 5. Unified versions so với independent versions

| Tiêu chí | Unified/lockstep | Independent |
| --- | --- | --- |
| Ví dụ | Parent/API/CLI cùng `1.3.0-SNAPSHOT`. | Parent `3.2.0`, API `2.1.0-SNAPSHOT`, CLI `5.0.0-SNAPSHOT`. |
| Phù hợp | Một sản phẩm, cùng release cadence. | Các thư viện phát hành riêng/ownership riêng. |
| Dependency giữa child | Có thể dùng `${project.version}` nếu đúng là đồng version. | Phải chỉ version API cụ thể hoặc property/BOM phù hợp. |
| Ưu điểm | Bump và release đồng loạt đơn giản. | Không nâng module không đổi chỉ vì app release. |
| Đánh đổi | Tất cả modules tăng version cùng nhau. | Quản lý dependency graph phức tạp hơn. |
| Sai lầm | Quên cập nhật parent reference của child. | Nhầm consumer version thành provider version. |

Maven hỗ trợ cả hai mô hình. **Chọn trước khi chạy công cụ đổi version hàng loạt**. Ví dụ runnable sau dùng **unified versions** để dễ quan sát SNAPSHOT → release.

## 6. Cấu trúc ví dụ Java 17 runnable

~~~text
snapshot-reactor-demo/
├── pom.xml
├── hello-api/
│   ├── pom.xml
│   ├── src/main/java/org/example/versions/api/Greeting.java
│   └── src/test/java/org/example/versions/api/GreetingTest.java
└── hello-cli/
    ├── pom.xml
    └── src/main/java/org/example/versions/cli/Main.java
~~~

Yêu cầu JDK 17+, Maven 3.9.x tương thích, các Maven plugins/JUnit artifacts có thể được tải hoặc đã nằm trong cache. Root là **parent + aggregator**, API là library, CLI dùng API và cả hai child thừa kế version `1.3.0-SNAPSHOT`.

Ví dụ này không dùng Java Platform Module System `module-info.java`; “module” trong bài là **Maven project module**.

## 7. Root pom.xml hoàn chỉnh

`snapshot-reactor-demo/pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>org.example.versions</groupId>
    <artifactId>hello-parent</artifactId>
    <version>1.3.0-SNAPSHOT</version>
    <packaging>pom</packaging>

    <modules>
        <module>hello-api</module>
        <module>hello-cli</module>
    </modules>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.junit.jupiter</groupId>
                <artifactId>junit-jupiter</artifactId>
                <version>5.11.4</version>
                <scope>test</scope>
            </dependency>
        </dependencies>
    </dependencyManagement>

    <build>
        <pluginManagement>
            <plugins>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-compiler-plugin</artifactId>
                    <version>3.13.0</version>
                </plugin>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-surefire-plugin</artifactId>
                    <version>3.5.2</version>
                </plugin>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-jar-plugin</artifactId>
                    <version>3.4.2</version>
                </plugin>
            </plugins>
        </pluginManagement>
    </build>
</project>
~~~

Phân tích:

- Root version `1.3.0-SNAPSHOT` là version parent POM dùng để xác định parent coordinates.
- Packaging `pom` có nghĩa root **không tự tạo một main JAR**.
- `<modules>` gom hai child; ở đây root cũng là parent do các child sẽ có `<parent>` trỏ tới.
- `dependencyManagement` chỉ quản lý JUnit version; child cần khai báo JUnit trong `<dependencies>` nếu có tests.
- `pluginManagement` giúp pin versions của các plugin được Maven jar lifecycle sử dụng.
- Không cần một dependency root → API/CLI: root chỉ cấu hình/build aggregator.

## 8. hello-api/pom.xml hoàn chỉnh

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.example.versions</groupId>
        <artifactId>hello-parent</artifactId>
        <version>1.3.0-SNAPSHOT</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>hello-api</artifactId>
    <packaging>jar</packaging>

    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
~~~

Child không khai báo `groupId`, `version` của chính nó vì kế thừa từ parent. Nhưng **`<parent><version>1.3.0-SNAPSHOT</version>` vẫn là một tham chiếu có version cần quản lý** khi root parent đổi version.

JUnit Jupiter có version `5.11.4` do parent dependencyManagement quy định; nếu bỏ dependency khỏi child hoàn toàn, compiler test không tự import JUnit chỉ nhờ management.

## 9. hello-cli/pom.xml hoàn chỉnh

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.example.versions</groupId>
        <artifactId>hello-parent</artifactId>
        <version>1.3.0-SNAPSHOT</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>hello-cli</artifactId>
    <packaging>jar</packaging>

    <dependencies>
        <dependency>
            <groupId>org.example.versions</groupId>
            <artifactId>hello-api</artifactId>
            <version>${project.version}</version>
        </dependency>
    </dependencies>
</project>
~~~

Dependency `hello-api` **có thật** trong CLI. Vì hai modules kế thừa cùng version từ parent, `${project.version}` khi resolve ở CLI có giá trị `1.3.0-SNAPSHOT`, khớp API reactor.

Nếu nhóm dùng independent versions, cần **không dùng công thức này** khi API và CLI version khác nhau; mục 22 giải thích trường hợp đó.

## 10. Java 17 source và unit test

`hello-api/src/main/java/org/example/versions/api/Greeting.java`:

~~~java
package org.example.versions.api;

public final class Greeting {
    private Greeting() {
    }

    public static String greet(String rawName) {
        String name = rawName.strip();
        if (name.isEmpty()) {
            name = "guest";
        }
        return "Hello, " + name + "!";
    }
}
~~~

`hello-api/src/test/java/org/example/versions/api/GreetingTest.java`:

~~~java
package org.example.versions.api;

import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

class GreetingTest {
    @Test
    void formatsNames() {
        assertEquals("Hello, Maven!", Greeting.greet(" Maven "));
        assertEquals("Hello, guest!", Greeting.greet("   "));
    }
}
~~~

`hello-cli/src/main/java/org/example/versions/cli/Main.java`:

~~~java
package org.example.versions.cli;

import org.example.versions.api.Greeting;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        System.out.println("message=" + Greeting.greet(" Maven "));
    }
}
~~~

Ba tệp source trên **hoàn chỉnh**. `String.strip()` có trong Java 11+ và chạy được trên JDK 17. Test JUnit Jupiter `GreetingTest` có 1 method, 2 assertions; tên class khớp quy tắc Surefire `*Test`. `Greeting.greet` giả định input không null vì đây là ví dụ đơn giản.

## 11. Build SNAPSHOT và chạy chương trình

Tại root có parent `pom.xml`:

~~~bash
mvn --version
java --version
javac --version
mvn -B -ntp clean verify
~~~

Maven thu thập root và hai child, build API trước CLI vì dependency CLI → API. Main JAR output được kỳ vọng:

~~~text
hello-api/target/hello-api-1.3.0-SNAPSHOT.jar
hello-cli/target/hello-cli-1.3.0-SNAPSHOT.jar
hello-api/target/surefire-reports/
~~~

Danh sách trên là **các output trọng tâm**, không phải tất cả files được Maven tạo. Parent packaging POM không tạo main JAR. Build pass nếu các plugins/JUnit resolve được và test có kết quả đúng như source.

Linux/macOS:

~~~bash
java -cp "hello-cli/target/hello-cli-1.3.0-SNAPSHOT.jar:hello-api/target/hello-api-1.3.0-SNAPSHOT.jar" org.example.versions.cli.Main
~~~

Windows PowerShell/CMD:

~~~powershell
java -cp "hello-cli\target\hello-cli-1.3.0-SNAPSHOT.jar;hello-api\target\hello-api-1.3.0-SNAPSHOT.jar" org.example.versions.cli.Main
~~~

**Stdout chính xác của riêng chương trình Java:**

~~~text
message=Hello, Maven!
~~~

Không dùng `java -jar hello-cli-...jar` theo mẫu này: JAR chưa khai báo `Main-Class` và chưa bundle API. Cách chạy là `java -cp` với **cả hai** JAR. Suffix SNAPSHOT không làm đổi Java runtime behavior; đó là Maven artifact version.

## 12. Kiểm effective versions và dependency graph

Kiểm từng module từ root:

~~~bash
mvn -B -ntp -pl :hello-api org.apache.maven.plugins:maven-help-plugin:3.5.1:evaluate -Dexpression=project.version -q -DforceStdout
mvn -B -ntp -pl :hello-cli org.apache.maven.plugins:maven-help-plugin:3.5.1:evaluate -Dexpression=project.version -q -DforceStdout
~~~

**Mỗi lệnh riêng** có kết quả mong đợi:

~~~text
1.3.0-SNAPSHOT
~~~

Kiểm CLI có thật sự yêu cầu API version đúng:

~~~bash
mvn -B -ntp -pl :hello-cli org.apache.maven.plugins:maven-dependency-plugin:3.8.1:tree
~~~

Trong dependency graph cần có dòng ý nghĩa tương tự:

~~~text
org.example.versions:hello-api:jar:1.3.0-SNAPSHOT:compile
~~~

Đây là **dòng trích ý nghĩa**, không phải log Maven toàn bộ. Nó quan trọng hơn việc chỉ nhìn `<modules>`: nếu CLI yêu cầu API version cũ, Maven có thể resolve từ repository chứ không tự chuyển sang API reactor.

## 13. Local SNAPSHOT install

Chạy:

~~~bash
mvn -B -ntp clean install
~~~

Lệnh đi qua lifecycle và cài parent POM + child artifacts/POMs vào **local Maven repository**. Đường dẫn mặc định cho API thường giống:

~~~text
~/.m2/repository/org/example/versions/hello-api/1.3.0-SNAPSHOT/
    hello-api-1.3.0-SNAPSHOT.jar
    hello-api-1.3.0-SNAPSHOT.pom
~~~

Nếu dùng `settings.xml` hoặc `-Dmaven.repo.local`, local repository path có thể khác. `mvn install` **không tự publish cho đồng đội**.

So sánh:

- `mvn package`: tạo file trong `target/`.
- `mvn install`: đặt artifact trong local repository trên máy build.
- `mvn deploy`: công bố lên remote repository được cấu hình bằng `distributionManagement`/settings/credentials.

Khi build cả reactor từ source, không cần `install` riêng chỉ để CLI tìm API trong chính reactor.

## 14. Timestamped SNAPSHOT trong remote repository

Một remote SNAPSHOT repository có thể lưu:

~~~text
org/example/versions/hello-api/1.3.0-SNAPSHOT/
    hello-api-1.3.0-20261110.142530-1.jar
    hello-api-1.3.0-20261110.142530-1.pom
    maven-metadata.xml
~~~

**Timestamp và build number ở đây chỉ là ví dụ minh họa**, không có artifact thật được tạo trong bài. Trong POM consumer vẫn dùng `1.3.0-SNAPSHOT` là **baseVersion**, còn repository có thể lưu các **unique timestamped snapshot versions**.

Maven version-level `maven-metadata.xml` cung cấp thông tin snapshot/time/build và mapping artifacts theo extension/classifier để resolver chọn file phù hợp.

Điều này giải thích vì sao **cùng một dependency version string** có thể tải binary mới hơn sau khi nhóm deploy một SNAPSHOT khác. Hai bản timestamped có thể khác source commit hoặc dependencies, nên bản SNAPSHOT không mang hợp đồng bất biến.

Khi cần điều tra một build, lưu Git commit ID, resolved snapshot timestamp, checksum, remote repository và CI run ID. Chỉ ghi “đã dùng 1.3.0-SNAPSHOT” có thể không đủ.

## 15. Update policy, -U và offline mode

Mảnh cấu hình repository minh họa:

~~~xml
<repository>
    <id>development-snapshots</id>
    <url>https://repo.example.invalid/snapshots</url>
    <releases><enabled>false</enabled></releases>
    <snapshots>
        <enabled>true</enabled>
        <updatePolicy>daily</updatePolicy>
    </snapshots>
</repository>
~~~

`example.invalid` là URL giả để đào tạo, không dùng nguyên trong production. Repo thực thường được quy định bởi công ty trong settings/mirror.

Maven hỗ trợ các giá trị policy như:

| Giá trị | Ý nghĩa |
| --- | --- |
| `always` | Thử kiểm update theo policy mỗi lần thích hợp. |
| `daily` | Kiểm theo chu kỳ ngày. |
| `interval:X` | Kiểm sau X phút. |
| `never` | Không tự cập nhật theo policy. |

Lệnh:

~~~bash
mvn -B -ntp -U clean verify
~~~

buộc Maven **kiểm cập nhật snapshots** theo resolver/repository policies; không đổi `<dependency><version>` trong POM và không chắc vượt qua mọi caching layer/mirror.

Lệnh:

~~~bash
mvn -B -ntp -o clean verify
~~~

chạy offline; có thể dùng cached snapshot cũ nếu đã tồn tại hoặc fail khi thiếu artifact. `-o` không thể bảo đảm “bản mới nhất remote”.

**Sai lầm phổ biến:** lạm dụng `-U` để chữa version mismatch giữa CLI và API. Phải sửa GAV hoặc chọn đúng reactor modules, không chỉ tăng tần suất kiểm cache.

## 16. Vì sao SNAPSHOT gây build không tái lập?

Giả sử remote snapshot repo có hai lần publish:

~~~text
Build A: hello-api-1.3.0-20261110.100000-1.jar
Build B: hello-api-1.3.0-20261110.160000-2.jar
~~~

Hai file có thể được tạo từ hai source revisions khác nhau nhưng cùng base GAV `hello-api:1.3.0-SNAPSHOT`. CLI source/POM không đổi, song test ở thời điểm khác nhau có thể dùng A hoặc B.

Trong multi-module, còn có thể xảy ra **version skew**: core được lấy từ SNAPSHOT mới, integration adapter vẫn lấy SNAPSHOT cũ, dẫn tới lỗi API/binary compatibility không xuất hiện khi build cả graph cùng commit.

Cách giảm rủi ro:

1. Build project dependencies trong cùng một reactor từ source commit thống nhất.
2. Dùng `-pl :hello-cli -am` khi chỉ kiểm một downstream module.
3. Ghi resolved artifacts + checksums trong CI.
4. Không dùng external SNAPSHOT mutable cho bản release cần audit.
5. Nếu buộc dùng một snapshot cụ thể, dùng quản lý version/timestamp lock có chủ đích và kiểm repository policy.
6. Giữ artifact publication/CI provenance để biết source nào sinh ra từng binary.

SNAPSHOT hữu ích cho phát triển nhanh, nhưng **không thay thế reproducible build policy**.

## 17. Release repository không được bị overwrite tùy tiện

Sau khi publish `hello-api:1.3.0`, consumer kỳ vọng cùng tọa độ là cùng binary. Một repository manager nếu cho overwrite release có thể tạo tình huống:

~~~text
Máy A: tải 1.3.0 với checksum X
Máy B: tải 1.3.0 sau khi bị overwrite -> checksum Y
Cả hai đều gọi artifact "1.3.0"
~~~

Điều này phá khả năng truy vết/rollback. Vì vậy quy trình release nên:

- Khóa overwrites/redeploy release trong repository manager.
- Sửa bug bằng version mới, không thay bytes của cùng GAV.
- Lưu source tag, artifact checksum, CI run ID và license/provenance.
- Kiểm cả JAR, POM, attached classifiers/sources/javadoc nếu chúng là một phần release set.
- Thử consumer resolve dependencies và parent POM từ environment sạch.

**Lưu ý:** Một release không tự trở nên “ổn định” về chất lượng nếu test thiếu; bất biến là **quản trị artifact**, không phải chứng nhận không có lỗi.

## 18. Bump version bằng Versions Maven Plugin

MojoHaus Versions Maven Plugin có goal `versions:set` để thay project version và cập nhật các references cần thiết theo module matching/layout của plugin.

Từ root của demo, khi team quyết định phát hành `1.3.0`:

~~~bash
mvn -B -ntp org.codehaus.mojo:versions-maven-plugin:2.22.0:set -DnewVersion=1.3.0 -DgenerateBackupPoms=false
~~~

Lệnh này **sửa POM trên working tree**. Nó **không** tự tạo Git tag, không deploy lên remote repository và không bảo đảm mọi module trong mọi layout đã được cập nhật hoàn hảo.

Sau lệnh, review mục tiêu:

~~~text
root/pom.xml
    <version>1.3.0</version>

hello-api/pom.xml
    <parent><version>1.3.0</version></parent>

hello-cli/pom.xml
    <parent><version>1.3.0</version></parent>
    <dependency><artifactId>hello-api</artifactId>
                <version>${project.version}</version></dependency>
~~~

`${project.version}` trong CLI dependency **vẫn để nguyên** vì nó sẽ resolve thành effective version `1.3.0`. Các parent references trong child POMs phải được cập nhật. Nếu chúng còn `1.3.0-SNAPSHOT`, **chưa đạt** release consistency.

### Tách invocation sửa POM và build

~~~bash
git diff -- pom.xml hello-api/pom.xml hello-cli/pom.xml
mvn -B -ntp clean verify
~~~

Hãy chạy `versions:set` **trước, ở Maven invocation riêng**, rồi chạy `clean verify`. Maven đã load project model ở đầu invocation và không bảo đảm tự reload sau khi Versions Plugin sửa file trên disk.

`processAllModules=true` là một option cho Versions Plugin khi cần xử lý các modules không match theo GAV mặc định. **Đừng bật bừa bãi** trong reactor có modules dùng independent versions. Luôn review docs của plugin version đang pin và `git diff`.

### Backup và rollback

Lệnh demo đặt `-DgenerateBackupPoms=false` nên **không tạo file `pom.xml.versionsBackup`**. Không dùng `versions:revert` rồi mong plugin tìm được backup không tồn tại. Dùng Git để review/rollback an toàn theo quy trình nhóm, không chạy `git reset --hard` trên workspace có thay đổi chưa commit của người khác.

## 19. Verify release build sau khi đổi version

Sau khi root và child references đã chuyển sang release `1.3.0`, chạy:

~~~bash
mvn -B -ntp clean verify
~~~

Output theo default finalName:

~~~text
hello-api/target/hello-api-1.3.0.jar
hello-cli/target/hello-cli-1.3.0.jar
~~~

Linux/macOS:

~~~bash
java -cp "hello-cli/target/hello-cli-1.3.0.jar:hello-api/target/hello-api-1.3.0.jar" org.example.versions.cli.Main
~~~

**Stdout vẫn chính xác:**

~~~text
message=Hello, Maven!
~~~

Đổi Maven artifact version không tự nhúng version vào Java runtime output.

Quality gate trước khi publish: root/child effective versions đúng, inter-module dependency tree đúng, không còn SNAPSHOT ngoại lai trái policy, tests pass, source release/tag/commit xác định, checksum và repository publication policy đã sẵn sàng.

Lệnh `mvn deploy` là hành động remote publication đòi quyền/credentials; ví dụ không yêu cầu thực thi nó.

## 20. Bump next development version

Sau khi release `1.3.0` được chốt, một chiến lược phát triển tiếp theo có thể dùng `1.4.0-SNAPSHOT`:

~~~bash
mvn -B -ntp org.codehaus.mojo:versions-maven-plugin:2.22.0:set -DnewVersion=1.4.0-SNAPSHOT -DgenerateBackupPoms=false
~~~

Kiểm lại trong invocation riêng:

~~~bash
git diff -- pom.xml hello-api/pom.xml hello-cli/pom.xml
mvn -B -ntp clean verify
~~~

Mục tiêu của unified reactor:

~~~text
hello-parent = 1.4.0-SNAPSHOT
hello-api    = 1.4.0-SNAPSHOT
hello-cli    = 1.4.0-SNAPSHOT
hello-cli -> hello-api:1.4.0-SNAPSHOT
~~~

Không chỉnh version của release đã được tag/publish để mô phỏng next development. Version tiếp theo cần dựa trên release plan, không dựa vào giả định “Maven tự tăng patch/minor”.

## 21. Maven Release Plugin: khác với versions:set

Release Plugin hỗ trợ SCM-integrated release workflow:

- `release:prepare` kiểm những điều kiện release như source/SCM state, snapshot dependencies, biến đổi project versions, chạy kiểm thử/verify theo cấu hình, commit và tag source, rồi chuyển working copy sang next development version.
- `release:perform` checkout một release tag và build/deploy theo release configuration.

Với unified multi-module có thể cấu hình tùy chọn:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-release-plugin</artifactId>
    <version>3.3.1</version>
    <configuration>
        <autoVersionSubmodules>true</autoVersionSubmodules>
    </configuration>
</plugin>
~~~

Đây là **mảnh plugin config tùy chọn**, không thuộc POM runnable của demo. `autoVersionSubmodules=true` giúp xử lý các child versions theo cùng release/development version của parent trong một release plan lockstep.

Các lệnh là **tài liệu tham khảo**, không chạy tùy tiện trên repository có quyền publish:

~~~bash
mvn -B -ntp release:prepare -DdryRun=true
mvn -B -ntp release:prepare
mvn -B -ntp release:perform
~~~

Prepare thực tế có thể sửa POM/commit/tag; perform có thể deploy remote artifact. Dry run có thể sinh file tạm và cần review, nhưng không thực hiện SCM commit/tag thật theo semantics của plugin.

Maven Release Plugin thường kiểm SNAPSHOT dependencies, đặc biệt những dependency bên ngoài chưa thành release; không bỏ qua policy này chỉ để build xanh. Nếu nhóm đã dùng Versions Plugin + Git/CI publish tùy biến, không tự chạy Release Plugin tiếp như một bước máy móc gây double bump/tag.

## 22. Independent versions: lỗi project.version trong dependency

Mô hình độc lập:

~~~text
company-build-parent:3.2.0
hello-api:2.1.0-SNAPSHOT
hello-cli:5.0.0-SNAPSHOT
hello-cli -> hello-api:2.1.0-SNAPSHOT
~~~

Nếu CLI ghi:

~~~xml
<dependency>
    <groupId>org.example.versions</groupId>
    <artifactId>hello-api</artifactId>
    <version>${project.version}</version>
</dependency>
~~~

thì Maven yêu cầu API `5.0.0-SNAPSHOT` vì đó là **version của CLI**, không phải `2.1.0-SNAPSHOT` của API.

Cách quản lý phù hợp hơn trong independent release plan:

~~~xml
<properties>
    <hello-api.version>2.1.0-SNAPSHOT</hello-api.version>
</properties>

<dependencies>
    <dependency>
        <groupId>org.example.versions</groupId>
        <artifactId>hello-api</artifactId>
        <version>${hello-api.version}</version>
    </dependency>
</dependencies>
~~~

Đây chỉ là **mảnh minh họa chiến lược khác**; không thay POM runnable unified. Có thể dùng parent dependencyManagement hoặc BOM nếu tổ chức muốn quản lý versions tập trung. Reactor vẫn yêu cầu **dependency GAV chính xác**, dù modules cùng aggregator.

## 23. CI-friendly versions trong Maven 3

Maven 3 hỗ trợ đặc biệt các placeholders version:

~~~text
revision
sha1
changelist
~~~

Mảnh cấu hình **CI-friendly alternative**:

~~~xml
<version>${revision}${changelist}</version>
<properties>
    <revision>1.3.0</revision>
    <changelist>-SNAPSHOT</changelist>
</properties>
~~~

Default effective version là `1.3.0-SNAPSHOT`. CI có thể build release hiệu lực bằng:

~~~bash
mvn -B -ntp -Drevision=1.3.0 -Dchangelist= clean verify
~~~

Trong Maven 3 multi-module, child parent version có thể khai báo:

~~~xml
<parent>
    <groupId>org.example.versions</groupId>
    <artifactId>hello-parent</artifactId>
    <version>${revision}${changelist}</version>
    <relativePath>../pom.xml</relativePath>
</parent>
~~~

Còn inter-module dependency dùng:

~~~xml
<version>${project.version}</version>
~~~

Theo tài liệu CI Friendly Maven, không thay `${project.version}` bằng `${revision}` ở dependency inter-module một cách tùy tiện. Trong Maven 3, để **install/deploy published POM consumable**, tài liệu chính thức hướng dẫn dùng **Flatten Maven Plugin** để resolve CI-friendly placeholders, ví dụ với mode `resolveCiFriendliesOnly`.

Mảnh config tham khảo (không thuộc demo chính):

~~~xml
<plugin>
    <groupId>org.codehaus.mojo</groupId>
    <artifactId>flatten-maven-plugin</artifactId>
    <version>1.6.0</version>
    <configuration>
        <updatePomFile>true</updatePomFile>
        <flattenMode>resolveCiFriendliesOnly</flattenMode>
    </configuration>
    <executions>
        <execution>
            <id>flatten</id>
            <phase>process-resources</phase>
            <goals><goal>flatten</goal></goals>
        </execution>
        <execution>
            <id>flatten-clean</id>
            <phase>clean</phase>
            <goals><goal>clean</goal></goals>
        </execution>
    </executions>
</plugin>
~~~

Khi dùng, phải cấu hình đúng parent/child inheritance, plugin lifecycle và xác minh published POM từ một consumer sạch. **Đừng coi build bằng `-Drevision` là đã phát hành release**, cũng không trộn một cách máy móc chiến lược CI-friendly với Versions/Release Plugin workflow. Maven 4 có thay đổi riêng về version resolution và subprojects; bài tập này dành cho Maven 3.

## 24. External SNAPSHOT dependencies trong một release

Dù tất cả modules trong reactor đã chuyển sang `1.3.0`:

~~~text
hello-cli:1.3.0
  └── hello-api:1.3.0
        └── org.example.common:utils:4.0.0-SNAPSHOT
~~~

một **external SNAPSHOT** vẫn khiến build có thể tải bytes khác nhau trong các lần chạy khác nhau.

Trước release cần review:

- Direct project dependencies ở từng child.
- Resolved transitive graph bằng Maven Dependency Plugin.
- BOM và `dependencyManagement` versions.
- Build plugin dependencies/extensions theo release policy.
- Test-only snapshots nếu ảnh hưởng QA reproducibility.
- Repo metadata, update policy và remote mirrors.

Lệnh:

~~~bash
mvn -B -ntp -pl :hello-cli org.apache.maven.plugins:maven-dependency-plugin:3.8.1:tree
~~~

giúp thấy dependency coordinates, nhưng **không tự xác nhận** binary đã ký hoặc reproducible. Nên lưu resolved artifact checksums và thông tin build provenance nếu cần audit.

## 25. Khi chạy child độc lập, cache dễ che version skew

Từ root:

~~~bash
mvn -B -ntp -pl :hello-cli -am clean verify
~~~

Maven có thể build API cùng CLI vì API là reactor dependency của CLI.

Nhưng khi vào riêng thư mục `hello-cli/` và chạy:

~~~bash
mvn -B -ntp clean verify
~~~

Maven không tự tạo full reactor từ root chỉ vì CLI có parent ở `../pom.xml`. Nếu local repo còn cached `hello-api:1.3.0-SNAPSHOT` cũ, CLI có thể dùng binary khác API source bạn vừa sửa; nếu không có artifact phù hợp, build có thể fail.

**Ưu tiên:** build từ aggregator root với `-pl/-am` hoặc có quy trình install/deploy rõ ràng. Không tin rằng `-U` tự compile source module bạn chưa chọn.

## 26. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| CLI vẫn dùng API `1.2.0-SNAPSHOT`. | Dependency version hard-code cũ. | Kiểm CLI POM và effective dependency tree. |
| `Non-resolvable parent POM` sau bump. | Child parent refs hoặc relativePath còn version cũ/sai. | Sửa đúng GAV của parent. |
| Root build pass, build riêng CLI fail. | API chưa có ở repository, không chạy `-am`. | Build từ root `-pl :hello-cli -am`. |
| SNAPSHOT hôm nay khác hôm qua. | Remote timestamped SNAPSHOT mới. | Xem metadata, checksum, source SHA. |
| `-U` không đổi API version. | Option update snapshots không sửa POM. | Đồng bộ dependency GAV bằng release/version policy. |
| Offline build fail. | Thiếu cached artifact/plugin. | Bảo đảm cache hoặc chạy online qua repo đúng. |
| `mvn install` pass, máy khác không resolve. | Local install không phải remote deploy. | Dùng release/snapshot repo theo chính sách. |
| Remote từ chối deploy lại version release. | Release repo immutable. | Tăng version, không overwrite. |
| `versions:set` chỉ đổi vài POM. | GAV matching/scope plugin khác kỳ vọng. | Review `git diff` và goal options. |
| `versions:set clean verify` không thấy model mới. | Maven invocation không reload POM. | Chạy hai lệnh Maven riêng. |
| Release Plugin yêu cầu SCM/tag. | Workflow SCM-integrated. | Config SCM và dùng dry run trước. |
| Release bị chặn vì external snapshot. | Mutable dependency trái quality gate. | Chuyển sang release/giải quyết policy. |
| Maven 3 CI-friendly deploy POM không consumable. | Chưa flatten version placeholders. | Flatten và test consumer sạch. |
| Module A và CLI version khác nhau. | Có thể là independent versioning hợp lệ. | Kiểm chính sách và GAV, không ép bằng nhau máy móc. |
| Java version khác Maven artifact version. | Hai hệ thống version độc lập. | Kiểm compiler/toolchain và GAV riêng. |

**Thứ tự điều tra:** root + child effective versions → parent refs → internal GAV → reactor selection → local/remote metadata/cache → source tests và binaries → published POM/tag/checksum.

## 27. Checklist release/SNAPSHOT nhiều mô-đun

- [ ] Đã chọn **unified** hay **independent** versions và có lý do rõ.
- [ ] Root parent và child effective versions đúng release plan.
- [ ] Child `<parent><version>` trỏ đúng parent version.
- [ ] Inter-module dependency GAV khớp producer artifact.
- [ ] `${project.version}` chỉ được dùng cho producer và consumer cùng version.
- [ ] Test và app runnable từ source trong một reactor build.
- [ ] Build riêng modules dùng `-pl/-am` nếu cần upstream source.
- [ ] `dependency:tree` và `help:evaluate` xác nhận graph/version.
- [ ] External mutable SNAPSHOTs được kiểm trước release.
- [ ] `-U`/offline/updatePolicy được hiểu đúng, không dùng để che POM mismatch.
- [ ] Release repository có policy không overwrite.
- [ ] Source tag, checksum, CI run ID và artifact version có thể truy vết.
- [ ] `versions:set` được review với Git diff trước khi build tiếp.
- [ ] Dùng Release Plugin thì hiểu prepare/perform và quyền SCM/deploy.
- [ ] Maven 3 CI-friendly project được flatten thành published POM consumable.
- [ ] Java/compiler/plugin versions không bị nhầm với project GAV.
- [ ] Test consumer resolution từ local repository sạch khi publish ra bên ngoài.
- [ ] Next development version được tăng sau khi release hoàn tất.

## 28. Câu hỏi tự kiểm tra

1. **`1.3.0-SNAPSHOT` và `1.3.0` có phải một Maven version?** Không; chúng là hai GAV khác nhau.
2. **SNAPSHOT có bảo đảm nội dung bất biến?** Không; remote snapshot repository có thể công bố các timestamped builds mới.
3. **Release có tự bất biến chỉ bằng việc bỏ SNAPSHOT?** Không; cần repository policy.
4. **Chỉ thêm `<module>hello-api</module>` thì CLI tự import được API?** Không; cần dependency thật với đúng GAV.
5. **Dùng `${project.version}` ở CLI dependency khi nào?** Khi API/CLI cùng effective version theo unified strategy.
6. **API `2.1.0-SNAPSHOT` nhưng CLI `5.0.0-SNAPSHOT` có nên dùng `${project.version}` để tham chiếu API?** Không; phải dùng version của API.
7. **Sau khi bump root POM, child parent refs có tự cập nhật trên disk?** Không nếu không dùng tool/sửa phù hợp; phải kiểm chúng.
8. **`mvn install` có xuất bản lên remote repo không?** Không; chỉ local install.
9. **Timestamped SNAPSHOT được resolve nhờ gì?** Maven repository metadata và resolver policy.
10. **`-U` có đổi dependency version trong POM?** Không.
11. **`versions:set` có tạo SCM tag và deploy remote release?** Không.
12. **Vì sao tách `versions:set` và `verify` thành invocations riêng?** Vì Maven project model không tự reload sau khi plugin sửa POM.
13. **`autoVersionSubmodules` thuộc plugin nào?** Maven Release Plugin.
14. **CI-friendly Maven 3 có placeholders nào?** `revision`, `sha1`, `changelist`.
15. **Vì sao CI-friendly Maven 3 cần xem Flatten Plugin khi deploy?** Để published POM có versions đã resolve, consumer đọc được.
16. **Maven `maven.compiler.release=17` có quyết định SNAPSHOT/release không?** Không; đó là Java target.
17. **Build xanh có đủ công bố release?** Không; còn versions, tests, repository policy và artifact provenance.

## 29. Tài liệu chính thức

- [Apache Maven — Getting Started Guide](https://maven.apache.org/guides/getting-started/index.html) — ý nghĩa SNAPSHOT và artifact versions.
- [Apache Maven — Guide to Working with Multiple Modules](https://maven.apache.org/guides/mini/guide-multiple-modules.html) — reactor sort và `-pl/-am`.
- [Apache Maven — Maven Metadata](https://maven.apache.org/repositories/metadata.html) — timestamped SNAPSHOT mapping.
- [Apache Maven — POM Reference](https://maven.apache.org/pom.html) — version, parent, modules và dependency management.
- [Apache Maven — Settings Reference](https://maven.apache.org/settings.html) — snapshot/release policies và updatePolicy.
- [Apache Maven — CI Friendly Versions](https://maven.apache.org/guides/mini/guide-maven-ci-friendly.html) — `revision`/`sha1`/`changelist`, multi-module, Flatten Plugin.
- [MojoHaus — Versions Maven Plugin, versions:set](https://www.mojohaus.org/versions/versions-maven-plugin/set-mojo.html) — version-change goal options.
- [MojoHaus — Versions Maven Plugin Usage](https://www.mojohaus.org/versions/versions-maven-plugin/usage.html) — backups và separate invocations.
- [Apache Maven Release Plugin — Prepare Release](https://maven.apache.org/maven-release/maven-release-plugin/usage/prepare-release.html) — release prepare và autoVersionSubmodules.
- [Apache Maven Release Plugin — Introduction](https://maven.apache.org/components/maven-release/maven-release-plugin/) — release prepare/perform.
- [Apache Maven Dependency Plugin — dependency:tree](https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html) — resolved dependency graph.
- [Apache Maven Help Plugin — help:evaluate](https://maven.apache.org/plugins/maven-help-plugin/evaluate-mojo.html) — effective child project versions.

**Kết luận:** `-SNAPSHOT` là development version có thể được deploy nhiều lần với remote timestamped snapshots; release cần repository policy bất biến. Trong multi-module, kiểm version đồng bộ của parent/children và Maven dependency GAV; dùng reactor để build đúng source, Versions Plugin để đổi POM có review, Release Plugin cho quy trình SCM và Flatten Maven Plugin khi công bố Maven 3 CI-friendly versions. Đừng coi `BUILD SUCCESS` hoặc tên JAR là bằng chứng đủ cho một release đúng.
