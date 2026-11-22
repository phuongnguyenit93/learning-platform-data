# distributionManagement và địa chỉ kho nhận bản phát hành trong Maven

## 1. Vấn đề: build thành công nhưng artifact phải được gửi tới đâu?

Khi chạy `mvn package`, Maven tạo JAR/WAR/POM hoặc artifact khác trong thư mục build. Khi chạy `mvn install`, Maven **cài** artifact vào **local repository** trên máy đang build. Nhưng khi chạy `mvn deploy`, Maven cần biết **kho nhận artifact được xuất bản**, cách kết nối tới kho đó, phiên bản đang là **release hay snapshot**, và nếu cần thì dùng credentials nào.

Trong POM, cấu hình đầu mối để công bố artifact là **`<distributionManagement>`**. Nó mô tả đích phân phối của **artifact do chính project tạo ra** — không phải danh sách kho để tải dependencies.

Tình huống điển hình:

~~~text
Dự án: vn.example:release-target-demo:1.0.0-SNAPSHOT
                  |
                  v
           mvn clean verify
                  |
             JAR + POM
                  |
         Chỉ khi được phép:
               mvn deploy
                  |
                  v
  distributionManagement.snapshotRepository
                  |
                  v
  Kho Maven Snapshots của tổ chức
~~~

Khi version thành `1.0.0` (không có hậu tố `-SNAPSHOT`), Maven chọn **release repository** khác nếu được cấu hình.

**Ba câu hỏi chính của bài:**

1. Maven phân biệt **`install`**, **`deploy`**, `<repositories>` và `<distributionManagement>` như thế nào?
2. Maven Deploy Plugin quyết định **URL nhận release/snapshot**, chọn `<server>` trong `settings.xml` và upload những file nào?
3. Làm sao **thử nghiệm an toàn trên filesystem**, rồi kiểm chứng repository thật trong CI mà không lộ credentials hoặc ghi nhầm production?

Bài có một dự án **Java 17 + JUnit 5** chạy được; POM cố ý dùng các URL `example.invalid` để không vô tình gửi artifact lên mạng. Phần thực hành dùng **repository kiểu `file:` trong thư mục `target`**. Không cần một Nexus/Artifactory server thật để hiểu lifecycle.

## 2. Bốn khái niệm không được đánh đồng

| Khái niệm | Cấu hình/vị trí | Mục đích | Có ghi remote? |
| --- | --- | --- | --- |
| **Build/package** | `mvn package` và build plugins | Tạo JAR/WAR/POM cùng files đi kèm. | Không. |
| **Local install** | `mvn install`, `maven-install-plugin` | Đưa artifact vào local `.m2/repository` hoặc local repo được cấu hình. | Không ghi remote Maven repository. |
| **Remote deploy** | `mvn deploy`, `maven-deploy-plugin` và `distributionManagement` | Gửi artifact của project lên **kho nhận bản phát hành**. | **Có thể ghi remote**; cần phê duyệt. |
| **Dependency resolution** | `<repositories>`, `<pluginRepositories>`, settings mirrors | **Tải** dependency/plugin từ repositories để build. | Bình thường là đọc/tải, không phải đích publish. |

**`mvn install` không tương đương `mvn deploy`.** Việc người phát triển thấy file JAR trong `.m2` không có nghĩa đồng nghiệp/CI có thể tải artifact đó từ repository công ty.

**`<repositories>` không phải địa chỉ upload.** Dù POM có:

~~~xml
<repositories>
    <repository>
        <id>company-dependencies</id>
        <url>https://repo.example.invalid/repository/maven-public/</url>
    </repository>
</repositories>
~~~

Maven vẫn cần một **deployment target** trong `distributionManagement` hoặc một tham số deploy thay thế. Đoạn trên chỉ **minh họa download repository** (URL `.invalid` không dùng được), không phải cấu hình của dự án runnable.

## 3. distributionManagement chứa những thành phần nào?

Một POM có thể khai báo:

~~~xml
<distributionManagement>
    <repository>
        <id>company-releases</id>
        <name>Company Maven Releases</name>
        <url>https://repo.example.invalid/repository/maven-releases/</url>
    </repository>
    <snapshotRepository>
        <id>company-snapshots</id>
        <name>Company Maven Snapshots</name>
        <url>https://repo.example.invalid/repository/maven-snapshots/</url>
    </snapshotRepository>
</distributionManagement>
~~~

Đây là **đoạn cấu hình minh họa**; `example.invalid` là domain dành cho ví dụ, **không phải kho có thật**. Khi áp dụng dự án thật, thay bằng URLs do người quản trị repository cung cấp và được phê duyệt.

Trong `distributionManagement` còn có thể thấy:

| Phần tử | Vai trò | Có phải nơi upload JAR chính? |
| --- | --- | --- |
| `<repository>` | **Kho phát hành release**; đồng thời là fallback cho snapshot nếu không khai báo snapshotRepository. | **Có**. |
| `<snapshotRepository>` | Kho nhận snapshot riêng. | **Có**, khi version snapshot. |
| `<site>` | Địa chỉ xuất bản **website tài liệu Maven Site**. | **Không**, đó là site HTML. |
| `<downloadUrl>` | URL tải/phân phối mang tính thông tin/metadata của project. | **Không**, không thay deployment repository. |
| `<relocation>` | Metadata thông báo artifact đã được chuyển GAV. | **Không**. |
| `<status>` | Trạng thái phân phối mang tính metadata cũ trong POM. | Không dùng làm upload URL. |

**Không cần khai báo mọi phần tử.** Thông thường, với một project phát hành JAR, cấu hình `<repository>` và `<snapshotRepository>` là phần quan trọng nhất.

### Vì sao cần cả repository và snapshotRepository?

Release và snapshot có chính sách khác nhau: release thường **không được ghi đè**, yêu cầu ký/duyệt/staging; snapshot cho phép nhiều bản build của một version phát triển và cơ chế timestamp metadata. Tách kho giúp enforce policy ở repository manager và giảm nguy cơ CI đẩy snapshot vào kho immutable.

**Nếu thiếu `<snapshotRepository>`**, theo POM reference Maven có thể dùng `<repository>` để nhận snapshot. Đây là **hành vi fallback**, không phải khuyến nghị trộn hai loại artifact trong production. Repo server vẫn có thể từ chối snapshot theo chính sách của nó.

## 4. Maven nhận diện release và snapshot như thế nào?

Ví dụ GAV:

~~~text
groupId    = vn.example
artifactId = release-target-demo
version    = 1.0.0-SNAPSHOT
packaging  = jar
~~~

Maven coi project version có hậu tố **`-SNAPSHOT`** là một snapshot version. Khi deploy:

~~~text
1.0.0-SNAPSHOT
   -> distributionManagement.snapshotRepository

1.0.0
   -> distributionManagement.repository
~~~

Nếu snapshotRepository không có, Maven có thể rơi về repository thông thường. Cần phân biệt **lựa chọn target bởi Maven** với **chính sách chấp nhận upload do repository manager thực thi**: server có thể cấm snapshot trên release repo, cấm redeploy release, yêu cầu token riêng hoặc bảo vệ branch.

**Đừng nhầm release với một snapshot đã được build thành công.** Đổi `1.0.0-SNAPSHOT` thành `1.0.0` làm thay tọa độ artifact, nơi deploy và yêu cầu bất biến, nhưng không tự thực hiện tag SCM, release approval, signature hay staging/promotion.

### GAV trong đường dẫn repository

Repository layout kiểu Maven 2 thường có:

~~~text
vn.example:release-target-demo:1.0.0
    |
    v
vn/example/release-target-demo/1.0.0/
    release-target-demo-1.0.0.jar
    release-target-demo-1.0.0.pom
~~~

Với snapshot:

~~~text
vn.example:release-target-demo:1.0.0-SNAPSHOT
    |
    v
vn/example/release-target-demo/1.0.0-SNAPSHOT/
    maven-metadata.xml
    release-target-demo-1.0.0-<timestamp>-<buildnumber>.jar
    release-target-demo-1.0.0-<timestamp>-<buildnumber>.pom
~~~

`<timestamp>` và `<buildnumber>` là **ký hiệu giải thích**, không phải tên file literal phải có. Tên file thực tế và checksum/metadata do Deploy Plugin/repository manager quyết định. Một snapshot timestamped có thể giữ nhiều phiên bản vật lý trong cùng thư mục version logical.

Không tự tạo hoặc sửa `maven-metadata.xml` bằng tay khi repository manager có cơ chế quản lý metadata; có thể làm hỏng version resolution cho consumers.

## 5. Ba giá trị id, name và url có vai trò khác nhau

Trong mỗi repository declaration:

~~~xml
<repository>
    <id>company-releases</id>
    <name>Company Maven Releases</name>
    <url>https://repo.example.invalid/repository/maven-releases/</url>
</repository>
~~~

- **`id`**: định danh logic để Maven phối hợp với các cấu hình khác, đặc biệt **tìm credentials** trong `settings.xml`. Với remote upload cần match chính xác server ID.
- **`name`**: nhãn để con người đọc log và quản trị cấu hình. Không thay cho id, và không dùng làm URL.
- **`url`**: nơi repository/transport nhận dữ liệu. Với HTTPS, thường là URL **hosted repository hỗ trợ upload**; không nhất thiết là URL xem artifact trên website hoặc URL group/proxy chỉ dành cho download.

**Lỗi điển hình:** copy URL của repository group dùng để tải dependency vào `<distributionManagement>`, rồi `mvn deploy` bị HTTP 405/403 vì endpoint đó không cho upload. Nhiều repository manager phân biệt **hosted releases**, **hosted snapshots**, **proxy**, **group/virtual**; cần lấy đúng URL publish do admin cấp.

Định danh `id` có thể khác nhau giữa release và snapshot để tách secrets/permissions; cũng có cấu hình dùng chung ID nếu cùng server credential, nhưng phải tuân thủ chính sách repository.

## 6. Credentials không thuộc về POM hoặc tài liệu nguồn

**POM nên chứa URL và ID, không chứa password/token**. Maven thường tìm secret trong `~/.m2/settings.xml` (Linux/macOS) hoặc `%USERPROFILE%\.m2\settings.xml` (Windows), hay một file settings riêng qua `mvn -s`.

Đoạn `settings.xml` **minh họa**, chỉ dùng khi đã có CI secret injection:

~~~xml
<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0">
    <servers>
        <server>
            <id>company-releases</id>
            <username>${env.CI_MAVEN_RELEASE_USER}</username>
            <password>${env.CI_MAVEN_RELEASE_TOKEN}</password>
        </server>
        <server>
            <id>company-snapshots</id>
            <username>${env.CI_MAVEN_SNAPSHOT_USER}</username>
            <password>${env.CI_MAVEN_SNAPSHOT_TOKEN}</password>
        </server>
    </servers>
</settings>
~~~

**Đây không phải file settings để đưa vào Git**; biến môi trường chưa được cấp sẽ làm authentication thất bại. Maven settings interpolation hỗ trợ tham chiếu biến môi trường trong những trường hợp phù hợp, nhưng tổ chức có thể ưu tiên password encryption, settings do CI runner tạo, workload identity hoặc cơ chế credential provider an toàn hơn.

Điều kiện then chốt:

~~~text
distributionManagement.repository.id = company-releases
                  |
                  v
settings.servers.server.id            = company-releases
                  |
                  v
Maven cung cấp credential cho remote transport tương ứng
~~~

ID phải **khớp chính xác**; `name` không được dùng để match credentials. **Không cần cấu hình `<server>` với username/password khi thử deploy vào file repository cục bộ**.

### Nguyên tắc giữ an toàn secret

- Không commit `settings.xml` có credentials thật hoặc đưa password vào POM, README hay URL.
- Dùng token/identity **có quyền deploy hạn chế**, tách snapshots và releases nếu policy yêu cầu.
- Chỉ cấp secrets cho jobs/branches/tags đã được duyệt; không đưa deploy token vào workflow chạy PR không tin cậy.
- Không log toàn bộ `settings.xml`, HTTP authorization headers hoặc `System.getenv()`.
- Nếu URL deploy có thể bị điều khiển bởi input PR hoặc biến CI chưa kiểm soát, có nguy cơ **chuyển credential tới host ngoài ý muốn**. Kiểm tra **cả ID và URL**, không chỉ ID.
- Dùng TLS certificate chain hợp lệ; không tắt xác minh TLS chỉ để “cho deploy xanh”.
- Định kỳ rotate/revoke token; nếu đã lộ secret, cần xử lý sự cố và thu hồi.

## 7. Ví dụ Java 17 có thể build được mà không cần server phát hành

Dự án mẫu tên `release-target-demo` có:

- POM hoàn chỉnh với `distributionManagement` minh họa.
- Java main class và một JUnit Jupiter test.
- Maven Compiler Plugin, Surefire, Jar và Deploy Plugin versions cố định.
- Hai lệnh học an toàn: `mvn clean verify`, `mvn install`.
- Một **bài tập local deployment** có dùng `-DaltDeploymentRepository` để **không gửi artifact tới URL example.invalid**.

Yêu cầu: **Maven 3.9+**, **JDK 17+**, và kết nối Maven repository được phép để tải plugin/JUnit. Các version trong bài được pin phục vụ ví dụ, không khẳng định mới nhất hoặc đã được organization phê duyệt cho mọi môi trường.

Cấu trúc:

~~~text
release-target-demo/
├── pom.xml
└── src/
    ├── main/java/vn/example/deploy/ReleaseApp.java
    └── test/java/vn/example/deploy/ReleaseAppTest.java
~~~

### 7.1. pom.xml hoàn chỉnh

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>vn.example</groupId>
    <artifactId>release-target-demo</artifactId>
    <version>1.0.0-SNAPSHOT</version>
    <packaging>jar</packaging>

    <name>Release Target Demo</name>
    <description>Demo Java 17 về Maven distributionManagement</description>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.10.2</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <distributionManagement>
        <repository>
            <id>company-releases</id>
            <name>Company Maven Releases</name>
            <url>https://repo.example.invalid/repository/maven-releases/</url>
        </repository>
        <snapshotRepository>
            <id>company-snapshots</id>
            <name>Company Maven Snapshots</name>
            <url>https://repo.example.invalid/repository/maven-snapshots/</url>
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
                <version>3.2.5</version>
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

### Vì sao POM cố ý dùng `.invalid`?

Hai URLs trong `<distributionManagement>` là **địa chỉ minh họa, không tồn tại**. Vì vậy:

- `mvn clean verify` vẫn có thể build và test bình thường; không cố ghi vào URL đó.
- `mvn install` cài artifact vào local repository và không cần credentials cho `.invalid`.
- **Không gọi `mvn deploy` trần** khi còn URL `.invalid` rồi chờ upload thành công.
- Để học deploy thực tế, dùng **override local file repository** được chỉ dẫn ở mục 10; sau đó đọc tree output.
- Trong dự án tổ chức, thay URLs bằng hosted repository đã được phê duyệt, không copy nguyên URL demo.

**Cấu hình xuất bản không làm cho `mvn verify` tự deploy.** Chỉ khi default lifecycle chạy đến phase `deploy` hoặc một goal deploy được gọi có chủ đích, Maven mới gửi artifact đến đích đã chọn.

### 7.2. src/main/java/vn/example/deploy/ReleaseApp.java

~~~java
package vn.example.deploy;

public final class ReleaseApp {
    private ReleaseApp() {
    }

    public static String status() {
        return "RELEASE DEMO: READY";
    }

    public static void main(String[] args) {
        System.out.println(status());
    }
}
~~~

### 7.3. src/test/java/vn/example/deploy/ReleaseAppTest.java

~~~java
package vn.example.deploy;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class ReleaseAppTest {
    @Test
    void returnsStableStatus() {
        assertEquals("RELEASE DEMO: READY", ReleaseApp.status());
    }
}
~~~

JUnit có scope `test`, không được đưa vào runtime dependencies của project artifact. `ReleaseApp` chỉ dùng JDK nên có thể chạy mà không cần copy thêm JAR.

## 8. Chạy build, test và local install

Ở thư mục root `release-target-demo`:

~~~bash
mvn --version
mvn -B -ntp clean verify
java -cp target/classes vn.example.deploy.ReleaseApp
~~~

Khi môi trường phù hợp, Surefire chạy **một unit test** và Maven tạo:

~~~text
target/release-target-demo-1.0.0-SNAPSHOT.jar
target/surefire-reports/...
~~~

Stdout **chính xác của riêng lệnh Java cuối cùng**:

~~~text
RELEASE DEMO: READY
~~~

`mvn verify` không gọi `ReleaseApp.main`; dòng stdout ở trên đến từ lệnh `java -cp` cuối. Dòng log Maven có thể khác nhau theo môi trường.

### Local install

Nếu được phép ghi vào local Maven repository của môi trường demo:

~~~bash
mvn -B -ntp install
~~~

Maven tiếp tục default lifecycle tới `install` và lưu artifacts vào local repository. Đường dẫn mặc định trên nhiều hệ thống thường dạng:

~~~text
~/.m2/repository/vn/example/release-target-demo/1.0.0-SNAPSHOT/
~~~

Với Windows, local repository thường nằm dưới thư mục `.m2\repository` của người dùng; vị trí có thể **được override trong settings**. Đường dẫn trên là mẫu, không khẳng định mọi máy dùng đúng chỗ đó.

`install` **không đọc** `distributionManagement.repository.url` để upload. Do đó URL `.invalid` không cản việc cài artifact vào local repository nếu dependencies/plugins resolve bình thường.

## 9. Khi nào Maven dùng Deploy Plugin?

`maven-deploy-plugin` cung cấp goal **`deploy:deploy`**. Với packaging chuẩn `jar`, Maven binding mặc định đặt goal này ở **phase `deploy`** của default lifecycle.

Chuỗi rút gọn:

~~~text
validate -> compile -> test -> package -> verify -> install -> deploy
                                                        |         |
                                                        v         v
                                                local repo    remote repo
~~~

Chạy:

~~~bash
mvn -B -ntp deploy
~~~

là **một thao tác có side effects ngoài máy**, nếu repository URL trỏ tới server thật và credentials/quyền hợp lệ. Nó đi qua các phase trước đó, bao gồm test/package/install, trừ khi POM hoặc flags/profile thay đổi lifecycle.

**Không gọi riêng `mvn deploy:deploy` để thay một release pipeline đầy đủ.** Goal trực tiếp có thể chỉ cố upload các artifact đã được build/sẵn có; không thay cho compile/test/package/verify. Với phát hành, dùng lifecycle và gates thích hợp.

Deploy Plugin phiên bản demo là **`3.1.4`**. Đây là plugin của Maven 3; syntax option và các tính năng có thể khác ở 2.x/4.x. Luôn kiểm tra plugin version trong effective POM khi chẩn đoán.

### Maven upload những gì?

Với project packaging `jar` như demo, một deployment bình thường thường gồm:

- **Artifact chính**: `release-target-demo-<version>.jar`.
- **POM artifact**: thông tin GAV, dependencies, build metadata liên quan.
- **Repository metadata** như `maven-metadata.xml` khi cần, đặc biệt snapshot/version listing.
- **Attached artifacts** nếu có, ví dụ `-sources.jar`, `-javadoc.jar`, test JAR hoặc Assembly ZIP có classifier và được gắn vào project trước deploy.
- **Checksum/signature files** tùy cơ chế, repository manager và plugins/policies được cấu hình.

**Không phải mọi file trong `target/` đều được deploy.** Report logs, arbitrary ZIP hoặc file copy vào target không tự động là Maven project artifact. Muốn deploy một artifact phụ, phải được gắn vào project qua plugin phù hợp hoặc dùng một workflow deployment riêng.

Cũng không nên coi một checksum file tồn tại là bằng chứng artifact được ký số. **Hash/checksum** và **cryptographic signature** có ý nghĩa khác nhau.

## 10. Thực hành deploy an toàn chỉ tới thư mục local

POM mẫu có remote URLs `.invalid` để tránh upload ngoài ý muốn. Ta **override deployment target** bằng **`altDeploymentRepository`** trỏ tới filesystem trong chính project.

**Chỉ thực hiện trong bản demo đã tạo riêng**, không chạy lệnh này trên repository dự án chưa được duyệt. Từ root:

~~~bash
mvn -B -ntp clean deploy "-DaltDeploymentRepository=local-lab::file:./target/lab-repository"
~~~

Với Maven Deploy Plugin **3.x**, cú pháp là:

~~~text
-DaltDeploymentRepository=<id>::<url>
~~~

Trong lệnh demo:

~~~text
id  = local-lab
url = file:./target/lab-repository
~~~

Dấu `::` là một phần cú pháp của plugin. **Không dùng cú pháp cũ `id::default::url` của plugin 2.x** trong Deploy Plugin 3.x; phần `layout` đã bị loại khỏi định dạng tham số.

`file:./target/lab-repository` là kiểu URL **file repository tương đối** được dùng trong hướng dẫn deployment transport của Apache Maven. Nó chỉ ghi vào filesystem của workspace demo; không sử dụng credentials của `company-releases` hoặc `company-snapshots` vì override dùng ID riêng `local-lab`.

### Cần hiểu rõ override

- `altDeploymentRepository` **thay đích được định nghĩa trong distributionManagement** cho lần gọi đó.
- Khi dùng mục tiêu local này, **không thử deploy tới `example.invalid`**.
- Với local file repository không có authentication, không cần một `<server id="local-lab">` mang credentials.
- Lệnh **vẫn chạy phase `deploy`**, ghi file và metadata trong `target/lab-repository`, không phải chỉ dry-run; đây là lý do phải giới hạn trong demo.
- **`mvn clean deploy`** dọn `target` trước rồi mới build/deploy, nên đừng dùng nếu `target` đang chứa dữ liệu cần giữ.
- Vị trí đường dẫn tương đối và file URL có thể cần điều chỉnh theo môi trường/CI; hãy đọc output để kiểm tra thực tế.

### Kiểm tra kết quả trên Linux/macOS

~~~bash
find target/lab-repository -type f
~~~

Trên Windows PowerShell:

~~~powershell
Get-ChildItem -Recurse -File target\lab-repository
~~~

Với project version `1.0.0-SNAPSHOT`, tìm đường dẫn logic:

~~~text
target/lab-repository/
└── vn/example/release-target-demo/1.0.0-SNAPSHOT/
    ├── maven-metadata.xml
    ├── release-target-demo-1.0.0-<timestamp>-<buildnumber>.jar
    └── release-target-demo-1.0.0-<timestamp>-<buildnumber>.pom
~~~

Đây là **cây rút gọn minh họa**; số build/timestamp, tên metadata và checksum files cụ thể do Maven/Wagon/repository quyết định. Không so cứng chính xác timestamp hoặc build number.

Để kiểm tra JAR vừa deploy trong file repository, tìm đúng file `.jar` thực tế và dùng `jar tf <path-to-jar>`; không tự khẳng định nó đã tới remote repository công ty.

### Thực hành release tương tự

Trong **bản sao riêng của dự án demo**, đổi đúng `<project><version>` thành `1.0.0` (không có SNAPSHOT), build và deploy **vẫn dùng local override**, rồi quan sát đường dẫn `.../1.0.0/release-target-demo-1.0.0.jar`.

**Không deploy cùng `1.0.0` lặp đi lặp lại tới một hosted release repository thật.** Nhiều repository được cấu hình immutable và từ chối release redeploy; nếu cần sửa lỗi sau phát hành, hãy tạo version mới theo quy trình của tổ chức.

## 11. Hai tham số override riêng cho release và snapshot

Deploy Plugin 3.x còn có:

~~~text
-DaltReleaseDeploymentRepository=id::url
-DaltSnapshotDeploymentRepository=id::url
~~~

- **`altReleaseDeploymentRepository`** dành cho project có **release version**.
- **`altSnapshotDeploymentRepository`** dành cho project có **snapshot version**.
- **`altDeploymentRepository`** là override chung cho deployment target.

Ví dụ **minh họa dành riêng cho file repository local**; chỉ chạy nếu bạn muốn tạo local release/snapshot directories khác nhau:

~~~bash
mvn -B -ntp deploy "-DaltSnapshotDeploymentRepository=local-snaps::file:./target/demo-snapshots"
~~~

Vì POM demo đang có version **`1.0.0-SNAPSHOT`**, tham số snapshot có hiệu lực cho mục đích thử nghiệm. Nếu chuyển project sang version `1.0.0`, phải dùng tham số `altReleaseDeploymentRepository` phù hợp.

**Không dùng tham số override để lách security rules của repository manager**. Một override có thể đưa artifact tới host khác; chỉ chấp nhận endpoints có owner/quyền cụ thể. Với CI có deploy credentials, dùng allowlist URL và protected environment variables.

### Cạm bẫy bảo mật của `id::url`

ID dùng để tìm credentials trong `settings.xml`, còn URL là endpoint đích. Nếu một dòng CLI/biến build trỏ tới **URL không tin cậy** nhưng tái sử dụng **ID có credentials**, token có thể bị gửi sai nơi. Các phiên bản plugin mới hơn có cơ chế kiểm tra bổ sung trong một số tình huống, nhưng **không thay việc review**.

Vì vậy: khi override, **không chỉ hỏi “ID có đúng không?” mà phải hỏi “URL có đúng repository đã được duyệt không?”**. Đừng dùng token production cho bài tập local.

## 12. Vì sao không đặt URL nhận bản phát hành dưới repositories?

So sánh hai cấu hình:

**Nơi Maven tìm và tải dependency:**

~~~xml
<repositories>
    <repository>
        <id>company-read</id>
        <url>https://repo.example.invalid/repository/maven-public/</url>
    </repository>
</repositories>
~~~

**Nơi Maven gửi artifact của chính project:**

~~~xml
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
~~~

Cấu hình download repo có thể nằm trong POM, active settings profiles hoặc settings mirrors. Một repository manager có thể cung cấp **group URL dùng cho đọc**, **hosted URL dùng cho ghi**. Chúng có thể khác domain/path/protocol.

**Maven không tự suy distributionManagement từ `<repositories>`**. Khi chạy deploy mà không có upload target và không có alternative target, plugin có thể báo thiếu repository cho deployment.

### Maven Central và upload

Maven Central thường là nguồn tải dependencies. Xuất bản lên một hệ sinh thái release công cộng không phải cứ đặt URL download của Maven Central trong distributionManagement; cần workflow publisher, namespace ownership, signing/staging/validation phù hợp theo nhà cung cấp dịch vụ.

Không dùng `https://repo.maven.apache.org/maven2/` làm URL upload chỉ vì Maven tải được artifacts từ đó.

## 13. `settings.xml` mirrors cũng không phải đích upload

Đoạn settings mirror thường gặp:

~~~xml
<mirrors>
    <mirror>
        <id>company-mirror</id>
        <mirrorOf>*</mirrorOf>
        <url>https://repo.example.invalid/repository/maven-public/</url>
    </mirror>
</mirrors>
~~~

**Đây là đoạn cấu hình download mirror minh họa**, không phải cấu hình đầy đủ `settings.xml`. Mirror giúp Maven chuyển các yêu cầu **resolution** tới repository được chỉ định, thường để cache/kiểm soát dependencies.

**Không được suy rằng `mirrorOf=*` làm `mvn deploy` upload lên `company-mirror`.** Upload chọn theo distributionManagement hoặc override của Deploy Plugin; thông tin credentials đọc bằng server ID phù hợp.

Một organization có thể yêu cầu mọi dependency downloads đi qua một mirror được duyệt và artifact uploads đi vào hosted releases/snapshots cùng hệ thống quản lý; đó vẫn là **hai vai trò khác nhau**.

## 14. Hosted, proxy và group repository

Một repository manager như Nexus hoặc Artifactory thường cung cấp các loại kho chức năng:

| Loại kho | Ý tưởng | Phù hợp với `distributionManagement`? |
| --- | --- | --- |
| **Hosted releases** | Lưu bản release do tổ chức publish. | **Có**, nếu cho phép upload và account có quyền. |
| **Hosted snapshots** | Lưu snapshot phát triển. | **Có**, khi được cấu hình cho snapshot. |
| **Proxy** | Cache artifacts từ Maven Central/nguồn ngoài. | Thường **không phải** nơi upload artifact nội bộ. |
| **Group/virtual** | Tổng hợp nhiều kho cho download. | Thường là endpoint đọc; chỉ ghi nếu repository manager/documentation xác nhận hỗ trợ. |
| **Local file repository** | Thư mục filesystem tuân layout Maven. | Phù hợp cho demo/staging có kiểm soát, không tự là remote collaboration repo. |

Tên loại kho và khả năng upload cụ thể khác nhau giữa repository managers. **Đừng đoán endpoint từ giao diện người dùng**: lấy deployment URL, release/snapshot policy và credentials từ tài liệu/admin đúng hệ thống.

Khi server từ chối redeploy release, **không cố xóa artifact và deploy lại** nếu không có quy trình phục hồi đặc biệt; điều đó phá tính bất biến và có thể ảnh hưởng consumers đã cache.

## 15. Maven Site deployment là một mục tiêu riêng

`distributionManagement` cũng có:

~~~xml
<distributionManagement>
    <site>
        <id>company-docs</id>
        <url>scp://docs.example.invalid/var/www/project</url>
    </site>
</distributionManagement>
~~~

Đây là URL **minh họa cho website tĩnh**, không phải URL JAR repository. Maven Site Plugin dùng site target thông qua site lifecycle (như `mvn site-deploy` hoặc site deploy goal), còn Maven Deploy Plugin dùng `repository` hoặc `snapshotRepository`.

| Lệnh | Nội dung chính | Đích |
| --- | --- | --- |
| `mvn deploy` | JAR/WAR/POM cùng attached artifacts của project. | Distribution repository. |
| `mvn site` | Sinh website tài liệu dưới `target/site`. | File local. |
| `mvn site-deploy` | Sinh/đẩy HTML site theo site lifecycle. | `distributionManagement.site` nếu cấu hình phù hợp. |

**Không thêm `<site>` để sửa lỗi upload JAR**, và không thay `<repository>` bằng địa chỉ website. Hai hệ thống có thể cần secrets khác nhau, với server IDs và protocol khác nhau.

## 16. POM inheritance: nơi đặt distributionManagement trong multi-module

Trong reactor đa module, thường có:

~~~text
company-parent/                 packaging pom
├── pom.xml                      parent + aggregator
├── api/
│   └── pom.xml                  packaging jar
└── service/
    └── pom.xml                  packaging jar
~~~

Nếu cả `api` và `service` cùng publish tới repository company và cùng chính sách, **parent có thể khai báo `distributionManagement`**, các children kế thừa cấu hình qua POM inheritance. Tuy nhiên:

- **Aggregation `<modules>` khác với inheritance `<parent>`**. Child chỉ thừa hưởng khi có parent relationship đúng.
- Những module **không được phép deploy** (demo, test fixtures, chỉ dùng nội bộ) cần chính sách skip/deploy module phù hợp.
- Nếu parent POM được publish như artifact, chính parent cũng có thể deploy POM của nó.
- Module có thể override distributionManagement nếu policy có lý do cụ thể; phải kiểm tra effective POM của từng module.
- Không copy cùng URLs/credentials vào mọi module nếu parent inheritance đã đáp ứng và organization muốn quản lý tập trung.
- Với nhiều project độc lập cùng version, cần biết module nào là artifact chính, module nào là aggregator, và files attachments có bị mất không.

### Tại sao `<modules>` không quyết định nơi deploy?

`<modules>` chỉ cho Maven Reactor biết **project nào tham gia build**. Mỗi project có GAV, POM effective model và artifacts riêng. DistributionManagement quyết định **đích deploy của từng project** (sau inheritance/override), không đơn giản là “lấy URL từ root và upload một lần cho toàn repository”.

## 17. `deployAtEnd` và tính nhất quán nhiều module

Deploy Plugin có tham số:

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

Đây là **đoạn cấu hình plugin minh họa**, không phải POM độc lập. Mục đích: hoãn gửi artifacts của reactor tới **cuối toàn bộ multimodule build** thay vì deploy ngay ở mỗi module. Điều này giảm trường hợp các module đầu đã được publish nhưng module cuối fail lúc compile/test.

**Cảnh báo quan trọng từ tài liệu Deploy Plugin:** `deployAtEnd` **không làm toàn bộ batch trở thành một giao dịch nguyên tử**. Nếu quá trình upload giữa chừng fail, repository có thể đã nhận **một phần** artifacts. Maven không tự rollback những file đã publish trước khi lỗi.

Một chiến lược mạnh hơn cho release quan trọng là **staging repository** trên repository manager: upload vào khu vực staging, kiểm thử/đối chiếu artifacts, rồi **promote/close/release** theo khả năng và chính sách của hệ thống. Cơ chế đó nằm ngoài một `mvn deploy` đơn thuần.

### Với reactor chạy song song

`mvn -T ... deploy` có thể xử lý modules đồng thời khi graph cho phép; không nên để nhiều modules sửa cùng file/metadata bên ngoài theo assumptions không an toàn. Reactor vẫn dựa trên dependency relationships thật, nhưng repository manager/transport và build plugins phải được đánh giá về concurrency.

Cần giám sát kết quả từng module, tập artifact cuối, staged repository và số lượng files; không coi một log upload thành công là dấu hiệu **toàn reactor** đã phát hành đủ.

## 18. Credentials, quyền và chính sách phát hành trong CI

Một pipeline an toàn thường tách **build/test** và **deploy**:

~~~text
Pull request / branch thường
    |
    v
mvn -B -ntp clean verify
    |
    v
Reports + artifacts để review
    |
    +--- Không cấp deploy token cho PR không tin cậy

Protected tag / release branch đã được duyệt
    |
    v
Verify lại source/commit và dependency lock/policy
    |
    v
Cấp credentials có phạm vi tối thiểu
    |
    v
mvn -B -ntp deploy
    |
    v
Kiểm tra repository nhận đúng POM/JAR/GAV/hash
    |
    v
Promotion/release announcement nếu phù hợp
~~~

Điều kiện deploy cần dựa trên **quyền/phê duyệt của CI**, không chỉ dựa vào version có đuôi `-SNAPSHOT` hay một biến boolean dễ bị thay từ PR.

### Nguy cơ từ POM của PR

POM có thể chứa URL deployment, plugin executions hoặc profiles. Nếu một PR chưa được tin cậy có quyền thay POM và chạy job có deploy credentials, kẻ tấn công có thể **đổi URL/ID hoặc script** để thu thập secrets. Nên:

1. Chỉ chạy deploy trên protected branch/tag đã review.
2. Không cấp deploy secrets cho build PR từ fork hoặc nội dung chưa kiểm tra.
3. Giữ repo URLs và IDs trong allowlist được quản trị, hạn chế overrides qua CI inputs.
4. Áp môi trường CI có quyền ghi hạn chế, logs được redacted.
5. Dùng token ngắn hạn, phân tách releases và snapshots.
6. So khớp commit/GAV/hash trước và sau upload.

**Không tự dùng personal developer token trong CI** nếu organization có service identity riêng.

## 19. Profile cho môi trường: dùng khi có lý do, không làm đích bí ẩn

Một số nhóm cần staging/prod repositories khác nhau. POM có thể dùng profile hoặc CI variables để điều chỉnh distributionManagement, nhưng phải bảo đảm **effective model** rõ và không cho PR tự đổi đích tùy ý.

Ví dụ một project có **profile được duyệt** tên `publish-staging` định nghĩa deployment URL staging, còn release environment chọn một cấu hình khác. Điều quan trọng không phải tên profile mà là:

- Profile nào đang active?
- URL nào thực sự xuất hiện trong **effective POM**?
- Server ID nào sẽ được dùng để tìm credentials?
- Artifacts thuộc version release/snapshot nào?
- Job CI có quyền publish tới target đó không?
- Có confirmation/promotion gate không?

Để quan sát profiles:

~~~bash
mvn -B -ntp help:active-profiles
~~~

Để xem effective POM **không ghi gì lên remote**:

~~~bash
mvn -B -ntp help:effective-pom -Doutput=effective-pom.xml
~~~

Tìm:

~~~text
project/version
project/distributionManagement/repository/id
project/distributionManagement/repository/url
project/distributionManagement/snapshotRepository/id
project/distributionManagement/snapshotRepository/url
build/plugins/plugin[maven-deploy-plugin]
~~~

Đây là **sơ đồ vị trí XML**, không phải XPath runnable. File `effective-pom.xml` là **output quan sát**; không cần commit nó vào source control.

**Không dùng `mvn -X` rồi đăng nguyên log công khai** khi build có secret; debug logs có thể chứa URL nội bộ và thông tin nhạy cảm. Redact và giới hạn quyền xem.

## 20. Snapshot metadata và vì sao consumers thấy bản mới

Khi deploy snapshot, Maven/repository lưu metadata để consumers biết snapshot timestamped nào tương ứng với logical version, chẳng hạn:

~~~text
1.0.0-SNAPSHOT
   |
   +-- bản timestamped A
   +-- bản timestamped B
   +-- maven-metadata.xml chỉ dẫn resolution
~~~

Những bản snapshot có thể được upload nhiều lần, tùy repository policy. Nếu một consumer vẫn thấy mã cũ, nguyên nhân có thể là:

- Dependency repository **chỉ cho đọc release** mà không bật snapshot resolution.
- Maven local cache/update policy chưa kiểm tra lại metadata.
- Mirror/CI repository group đang trỏ tới hosted repo khác.
- Snapshot upload chưa hoàn tất hoặc metadata bị lỗi.
- Consumer dùng version khác (`1.0.0` thay vì `1.0.0-SNAPSHOT`).
- CI dùng local `.m2` cache khác với máy của developer.

Các repository **để tải** snapshot được cấu hình riêng dưới `<repositories>` hoặc settings profiles/mirrors; việc publisher upload thành công **không tự cập nhật POM consumers** để dùng snapshot đó.

Trong trường hợp cần refresh snapshot metadata khi phân tích (và tổ chức cho phép), Maven có option:

~~~bash
mvn -U -B -ntp dependency:tree
~~~

`-U` yêu cầu kiểm tra cập nhật snapshots/releases bị thiếu theo semantics của Maven, nhưng **không sửa sai GAV, credential hoặc repository policy**. Với build reproducibility, cân nhắc khóa release versions thay vì dựa vào snapshots dài hạn.

## 21. Release repository bất biến và vấn đề redeploy

Một release GAV như `vn.example:release-target-demo:1.0.0` thường được mong đợi đại diện cho **một bộ bytes duy nhất**. Nhiều repository managers chặn việc ghi đè release artifacts.

**Nếu `1.0.0` đã publish mà phát hiện lỗi:**

- Không đổi nội dung JAR rồi cố upload lại cùng GAV khi policy cấm redeploy.
- Phát hành **version mới** (`1.0.1` hoặc version phù hợp release policy) và liên kết changelog.
- Nếu lỗi nghiêm trọng về an ninh, dùng quy trình deprecate/quarantine/revoke artifacts của repository manager và thông báo consumers.
- Nếu repository manager có promotion/staging, xác định artifact đã thật sự release hay vẫn còn trong staging trước khi xử lý.
- Đảm bảo tag/commit/build provenance xác định được source của từng release.

Snapshot không nên bị coi là bản release immutable; release cũng không nên được dùng như snapshot viết lại nhiều lần.

## 22. Cách kiểm tra repository đã nhận đúng artifact

Sau deploy được **ủy quyền và xác nhận thành công**, kiểm tra:

1. **GAV đúng**: groupId/artifactId/version/classifier/packaging đúng với release record.
2. **Destination đúng**: hosted releases hoặc hosted snapshots, không phải proxy/group read-only.
3. **Các file đủ**: main JAR/WAR, POM, attached sources/javadoc/distribution nếu có; repository metadata nhất quán.
4. **Bytes đúng**: so checksum SHA-256 của file local và artifact tải lại (khi backend hỗ trợ), hoặc dùng digest/provenance của pipeline.
5. **Download thử như consumer**: từ một environment được phép, giải quyết artifact với GAV và repository được tổ chức cấu hình; tránh dùng file trong `.m2` cũ để kiểm chứng.
6. **Quyền truy cập**: nhóm tiêu thụ hợp lệ đọc được artifact, tài khoản upload không có quyền xóa/overwrite quá phạm vi.
7. **Chính sách**: release signing, license/SBOM, vulnerabilities, retention và audit log theo yêu cầu của tổ chức.

### Tính checksum

**Linux/macOS:**

~~~bash
shasum -a 256 target/release-target-demo-1.0.0-SNAPSHOT.jar
~~~

**Windows PowerShell:**

~~~powershell
Get-FileHash target\release-target-demo-1.0.0-SNAPSHOT.jar -Algorithm SHA256
~~~

Hash thực tế **không thể dự đoán từ bài viết**: nó phụ thuộc vào bytes của artifact tạo ở mỗi môi trường. Một số build có timestamps hoặc metadata không reproducible. Không coi hai SHA khác nhau là cùng artifact chỉ vì tên GAV giống nhau.

**Kiểm tra tải lại** phải dùng đúng repository/credential được phép và tránh thay đổi local cache làm che lỗi. Một cách mạnh là dùng local Maven repository tạm trong consumer smoke test để chắc chắn artifact đến từ remote.

## 23. Phân biệt thiếu cấu hình, thiếu quyền và sai endpoint

| Triệu chứng | Nguyên nhân có thể | Hành động kiểm tra |
| --- | --- | --- |
| Maven báo thiếu deployment repository | Không có distributionManagement hợp lệ hoặc `altDeploymentRepository`. | Kiểm tra effective POM và deploy plugin config. |
| HTTP `401 Unauthorized` | Thiếu token, sai server ID hoặc credential không hợp lệ. | So `<id>` và settings `<server><id>`, secret injection, token validity. |
| HTTP `403 Forbidden` | Account không có quyền upload hoặc policy server từ chối. | Kiểm tra role/permission ở repository manager. |
| HTTP `404 Not Found` | Repository path sai, server không có endpoint được yêu cầu. | Xác minh URL hosted repo với admin. |
| HTTP `405 Method Not Allowed` | Endpoint không hỗ trợ upload, thường nhầm URL đọc/group/proxy. | Dùng đúng deploy URL, không tự đổi HTTP method. |
| HTTP `409 Conflict` | Release version đã tồn tại, snapshot/release policy hoặc metadata conflict. | Kiểm tra immutable release và version target. |
| HTTP `413 Payload Too Large` | Giới hạn upload của proxy/server. | Kiểm tra max upload, artifact size, network policy. |
| `PKIX path building failed` | Certificate chain/truststore có vấn đề. | Xác minh CA/truststore, không tắt TLS verification. |
| `Connection refused` / timeout | Host/port/network/proxy/VPN sai hoặc outage. | Xem DNS/TLS/network giữa CI runner và repository. |
| `No connector available` | Protocol không có Wagon/provider tương thích. | Kiểm tra URL scheme, plugin/transport configuration. |
| Snapshot bị gửi vào releases | Version/override hoặc repository config sai. | Xem project version và cả hai deployment URLs. |
| Local install OK nhưng deploy fail | Local `.m2` khác remote target và cần auth/policy. | Đừng dùng `install` làm bằng chứng remote deploy. |
| Artifact deploy rồi nhưng consumer không tải | Repository consumer config, credential hoặc metadata/cache khác. | Kiểm tra download repo và GAV từ consumer sạch. |
| Some modules missing | Partial multi-module deploy hoặc failed attachment packaging. | Kiểm tra từng module, deployAtEnd/staging và logs. |

**Lỗi 401 khác 403; 404 không luôn do artifact không tồn tại; 409 không luôn do network.** Xem HTTP response và policy của đúng repository manager trước khi thử lại.

**Không retry vô điều kiện** đối với `409` release conflict hoặc một deploy timeout mơ hồ: có thể artifact **đã được ghi** dù client không nhận được response. Xác minh remote state trước khi quyết định có cần deploy lại, đặc biệt với release immutable.

## 24. `deploy:deploy-file` là trường hợp đặc biệt

Thông thường `mvn deploy` xuất bản artifacts của **project hiện tại** đã được Maven build. Nhưng đôi khi cần công bố một JAR bên thứ ba hoặc file do công cụ khác tạo. Deploy Plugin có goal **`deploy:deploy-file`** cho trường hợp đó, ví dụ khi được **cho phép** và đã chuẩn bị artifact hợp pháp:

~~~bash
mvn org.apache.maven.plugins:maven-deploy-plugin:3.1.4:deploy-file \
    -Dfile=path/to/example.jar \
    -DgroupId=vn.example.external \
    -DartifactId=example \
    -Dversion=1.0.0 \
    -Dpackaging=jar \
    -DrepositoryId=approved-repo \
    -Durl=https://repo.example.invalid/repository/maven-releases/
~~~

**Đây là lệnh minh họa**, không thể chạy khi chưa có JAR thật và URL `.invalid`; chỉ dùng trong môi trường đã được phép. Cú pháp shell Bash dùng `\` để xuống dòng; trên PowerShell nên viết lệnh trên **một dòng** hoặc sử dụng cú pháp tiếp dòng PowerShell riêng.

Khác biệt:

- `deploy:deploy-file` nhận đường dẫn file/GAV và repositoryId/url bằng parameters riêng; không phải cách phát hành chuẩn của một project có POM/attached artifacts đầy đủ.
- Có thể dùng `-DpomFile` nếu có POM đã được kiểm chứng, hoặc generate POM tùy cấu hình goal; cần đảm bảo dependency metadata đúng.
- Không upload một JAR bất kỳ như artifact nội bộ nếu license/provenance/authorization chưa rõ.
- Không dùng `deploy-file` để “bù” cho việc project build thiếu main artifact/classifier do cấu hình sai; hãy sửa build packaging trước.

Với một Maven project bình thường, **ưu tiên `mvn deploy` trong lifecycle đã kiểm thử**.

## 25. `maven.deploy.skip`: bỏ qua upload có nghĩa gì?

Deploy Plugin 3.x có parameter **`maven.deploy.skip`**, với giá trị tùy phiên bản như `true`, `releases`, `snapshots` hoặc `false`.

Ví dụ nếu mục tiêu chỉ là xác minh default lifecycle đến phase `deploy` nhưng **chủ đích không upload**:

~~~bash
mvn -B -ntp deploy -Dmaven.deploy.skip=true
~~~

Lệnh có thể chạy nhiều phase như compile/test/package/install, **nhưng goal deploy bỏ upload**; vì vậy **không chứng minh remote repository đã nhận artifact**.

Trong bài học, lệnh `mvn clean verify` còn rõ ràng hơn nếu không muốn xuất bản. Đừng bật skip trong CI release rồi coi `BUILD SUCCESS` là deploy thành công.

Nếu một parent/profile đã đặt skip, hãy kiểm tra effective POM và logs — một build xanh có thể do deploy goal bị bỏ qua.

## 26. Không phải tất cả artifacts đều được publish như một JAR duy nhất

Maven có khái niệm **main artifact** và **attached artifacts**. Một project có thể tạo:

~~~text
product-2.0.0.jar
product-2.0.0.pom
product-2.0.0-sources.jar
product-2.0.0-javadoc.jar
product-2.0.0-all.jar
product-2.0.0-dist.zip
~~~

Tùy plugin settings, không phải file nào trong thư mục `target/` cũng **được attached vào project**. Để Deploy Plugin gửi đúng tất cả:

- Maven Source Plugin có thể attach sources JAR.
- Maven Javadoc Plugin có thể attach Javadoc JAR.
- Maven Shade Plugin có thể attach shaded JAR dưới classifier như `all`.
- Maven Assembly Plugin có thể attach distribution artifact dưới classifier như `dist`.
- Những outputs phải được tạo trước phase deploy, và kiểm tra classifier/type trong repository.

**Phải phân biệt** `product-2.0.0.jar` (main artifact) với `product-2.0.0-all.jar` (attached shaded variant) và ZIP (distribution). Nếu CI chỉ scan/upload `target/*.jar` bằng shell, có thể lẫn JAR chưa được quản lý Maven metadata hoặc bỏ POM/attached artifacts.

Một release tốt công bố **đúng GAV, classifier và type** mà consumer cần, không chỉ là một file JAR bất kỳ.

## 27. Dữ liệu nào không nên đưa vào repository?

Artifact upload là hành động **chia sẻ lâu dài**, kể cả khi repository là “internal”:

- Không nhúng `.env`, API keys, private keys, database password, personal data hoặc credentials vào JAR/ZIP.
- Không publish test fixtures chứa thông tin nhạy cảm hoặc logs/dumps từ CI.
- Kiểm tra `src/main/resources`, resource filtering và assembly descriptors trước phát hành.
- Chạy secret scanning, license/SBOM và vulnerability checks theo policy trước deploy.
- Tránh publish artifact có manifest chứa token/URL tạm nếu không cần.
- Dùng reproducible build settings khi tổ chức yêu cầu; xác minh checksum/provenance sau deploy.
- Với các artifact dùng nhiều teams, lưu changelog, release notes và compatibility constraints.

**Không dùng repository như một thư mục backup tùy tiện**. Repository manager quản lý metadata, access control, retention và chính sách version; chép file trực tiếp vào storage backend mà bỏ qua API của repository manager có thể phá metadata.

## 28. Khi nào staging/promotion phù hợp hơn direct deploy?

Với dự án quan trọng, `mvn deploy` trực tiếp tới immutable release repository có thể quá sớm. Một workflow chuyên nghiệp thường là:

~~~text
1. Build từ protected tag/commit
2. Verify/test trên source đã chốt
3. Scan, sign, attach sources/Javadoc/SBOM nếu cần
4. Upload vào repository staging hoặc release candidate area
5. Đối chiếu toàn bộ artifacts và POM metadata
6. Approval/close stage theo repository manager
7. Promote/release để consumers nhìn thấy bản chính thức
8. Xác minh download, checksum và audit trail
~~~

**Staging/promote là khả năng của repository manager hoặc release tooling**, không tự được cung cấp chỉ bằng `<distributionManagement>` hay `deployAtEnd=true`. Cần chọn API/workflow đúng nhà cung cấp và kiểm soát rollback.

Nếu không có staging, có thể dùng một hosted release repository chỉ cho publishing qua CI protected job, nhưng vẫn cần **kiểm tra trước khi deploy** vì nhiều release repositories không cho ghi đè sau này.

## 29. Kiểm thử cấu hình trước khi có quyền deploy thật

Nhiều lỗi có thể phát hiện **không cần credentials và không ghi remote**.

### Kiểm tra POM model

~~~bash
mvn -B -ntp validate
mvn -B -ntp help:effective-pom -Doutput=effective-pom.xml
~~~

Đọc `project.version`, `distributionManagement.repository` và `snapshotRepository`. Nếu dùng parent/profile, kiểm tra đúng effective configuration thay vì chỉ một file root POM.

### Kiểm tra build và artifact

~~~bash
mvn -B -ntp clean verify
jar tf target/release-target-demo-1.0.0-SNAPSHOT.jar
~~~

`jar tf` chỉ kiểm tra archive entries, không thay runtime smoke test. Với demo:

~~~bash
java -cp target/classes vn.example.deploy.ReleaseApp
~~~

Stdout:

~~~text
RELEASE DEMO: READY
~~~

### Kiểm tra upload không ra mạng

Dùng **local override** đã mô tả ở mục 10, rồi đọc tree của `target/lab-repository`. Điều đó xác minh Deploy Plugin có thể xây Maven repository layout và metadata bằng file transport trong môi trường demo.

**Local test không chứng minh server thật sẽ nhận artifact.** Authentication, TLS, permissions, content policy, quota, staging và proxy routing vẫn cần test trong môi trường release được phép.

## 30. Kiểm tra version và đích để tránh phát hành nhầm

Checklist trước khi chạy remote `mvn deploy`:

1. **`mvn --version`** có Maven/JDK phù hợp.
2. `git status --short` không có thay đổi chưa được duyệt.
3. GAV và project version khớp tag/release plan.
4. Version là release/snapshot đúng ý định.
5. `distributionManagement.repository` và `snapshotRepository` có IDs/URLs chính xác.
6. Đích là **hosted write repository**, không phải group/proxy read-only.
7. `settings.xml` server IDs khớp và token có quyền tối thiểu.
8. Không đưa secret vào POM, CLI URL hoặc source.
9. Các flags `altDeploymentRepository`, `altReleaseDeploymentRepository`, `altSnapshotDeploymentRepository` (nếu có) là các targets đã được duyệt.
10. CI không cấp secrets cho PR chưa được tin cậy.
11. `mvn clean verify` đã pass cùng source/commit.
12. Artifact main và attachments cần publish đã được tạo.
13. License/SBOM/secret/security checks phù hợp đã pass.
14. Release repository policy cho phép GAV này (không trùng immutable release).
15. Multi-module publication đã đánh giá partial failure; nếu dùng `deployAtEnd` hiểu rằng nó **không atomic**.
16. Có audit trail, khả năng đối chiếu file hash và quy trình rollback/quarantine.
17. Khi upload timeout, biết cách kiểm tra remote state trước khi retry.
18. Chỉ chạy remote deploy sau quyền/phê duyệt chính thức.

## 31. Bài tập tự luyện

**Bài 1 — Phân biệt lifecycle.** Chạy `mvn clean verify`, `mvn install` trên demo. Giải thích file nào ở `target`, file nào ở local repo, vì sao không có remote publication.

**Bài 2 — Snapshot target.** Đọc root POM, chỉ ra `company-snapshots` ID/URL. Nếu version vẫn là `1.0.0-SNAPSHOT`, Maven sẽ chọn entry nào khi không có override?

**Bài 3 — Deploy local.** Thực thi lệnh `-DaltDeploymentRepository=local-lab::file:./target/lab-repository` trên project demo. Liệt kê file trong local repository và tìm đường dẫn GAV.

**Bài 4 — Release path.** Trong bản sao demo, đổi project version từ `1.0.0-SNAPSHOT` thành `1.0.0`, deploy lại vào local file repository. So đường dẫn và filenames; vì sao release thường không timestamp kiểu snapshot?

**Bài 5 — ID và credentials.** Trên giấy, viết một `settings.xml` có `<server><id>company-snapshots</id>...` nhận credentials từ environment. Giải thích vì sao `name` không match auth và không nên commit password.

**Bài 6 — Đọc vs ghi.** So một URL dưới `<repositories>` với `<distributionManagement>`. Vì sao download mirror không tự quyết định đích deploy?

**Bài 7 — Site vs artifact.** Thiết kế thêm `<distributionManagement><site>` nhưng không chạy `site-deploy`. Giải thích tại sao nó không sửa lỗi `mvn deploy` của JAR.

**Bài 8 — CI protection.** Lập pipeline: PR chỉ `verify`; release tag có approval mới cấp deploy token. Nêu rủi ro nếu PR được sửa `distributionManagement` URL trong khi chạy cùng token.

**Bài 9 — Multi-module.** Thiết kế parent và hai JAR modules cùng kế thừa distributionManagement. Nếu bật deployAtEnd, hãy mô tả trường hợp upload module đầu thành công nhưng upload module sau thất bại; làm sao stage/promote để giảm rủi ro?

**Bài 10 — Troubleshooting.** Dùng bảng lỗi ở mục 23 để phân loại `401`, `403`, `405`, `409`, TLS error, missing URL và stale snapshot. Đề xuất bước chẩn đoán an toàn cho từng lỗi, tránh retry overwrite mù.

### Tổng kết

**`distributionManagement` là cấu hình của Maven để biết artifact do project tạo sẽ được phân phối đến đâu.** `<repository>` thường nhận release, `<snapshotRepository>` nhận snapshot; nếu không có snapshotRepository, Maven có thể dùng repository làm fallback. `id` phục vụ định danh và tra credentials trong `settings.xml`, `url` chỉ ra nơi upload, còn `name` là nhãn. Đây **không phải** `<repositories>` hay settings mirrors dùng để **tải dependency**.

`mvn install` chỉ lưu artifact vào local repository; `mvn deploy` đi qua default lifecycle đến bước có thể **ghi lên repository được cấu hình**. Maven Deploy Plugin 3.x hỗ trợ các alternative targets dạng **`id::url`** để thử local file repository hoặc chọn đúng môi trường đã được phép. Với release thực tế, cần kiểm tra GAV, repo type, credentials, checksums, attachments, policy và bảo vệ CI; `deployAtEnd` không biến multi-module deploy thành giao dịch nguyên tử.

### Tài liệu chính thức

- [Apache Maven — POM Reference: Distribution Management](https://maven.apache.org/pom.html#distribution-management)
- [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Apache Maven — Introduction to Repositories](https://maven.apache.org/guides/introduction/introduction-to-repositories.html)
- [Apache Maven — Settings Reference](https://maven.apache.org/settings.html)
- [Apache Maven — Deploy Plugin](https://maven.apache.org/plugins/maven-deploy-plugin/)
- [Apache Maven — Deploy Plugin 3.1.4 deploy:deploy Parameters](https://maven.apache.org/plugins/maven-deploy-plugin/deploy-mojo.html)
- [Apache Maven — Deploy Plugin project deployment](https://maven.apache.org/plugins/maven-deploy-plugin/examples/deploy-network-issues.html)
- [Apache Maven — Deploy over HTTP, FTP and SSH](https://maven.apache.org/guides/mini/guide-deployment-transports.html)
- [Apache Maven — Maven Deploy Plugin deploy:deploy-file](https://maven.apache.org/plugins/maven-deploy-plugin/deploy-file-mojo.html)
- [Apache Maven — Repository Metadata](https://maven.apache.org/repositories/metadata.html)
- [Apache Maven — Maven Repositories and Mirrors](https://maven.apache.org/guides/mini/guide-mirror-settings.html)
