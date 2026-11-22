# Xác minh POM, checksum và các tệp đi kèm sau xuất bản Maven

## 1. Mục tiêu: “deploy thành công” chưa đủ để kết luận phát hành đúng

Một lần chạy `mvn deploy` trả `BUILD SUCCESS` chỉ cho biết Maven đã hoàn thành các bước mà cấu hình và plugin yêu cầu trong lượt build ấy. Nó **không tự chứng minh** rằng một người dùng ở môi trường độc lập có thể tải đúng phiên bản, rằng POM chứa đúng dependency, rằng nguồn/Javadoc/chữ ký đầy đủ, hoặc rằng bytes trên repository giống những gì nhóm đã duyệt.

Sau khi xuất bản một thư viện, cần hậu kiểm ít nhất **năm hợp đồng**:

1. **Đúng tọa độ và tệp:** `groupId:artifactId:version` ánh xạ đến đúng đường dẫn repository; có POM và binary/artifacts được kỳ vọng.
2. **POM có thể dùng được:** metadata, dependencies, parent/BOM và versions đúng; consumer không cần source checkout của tác giả.
3. **Bytes toàn vẹn:** checksum của từng file đã tải khớp giá trị kiểm tra đáng tin cậy; nhận biết checksum sidecars có/không.
4. **Nguồn gốc xác thực:** nếu có chữ ký OpenPGP (`.asc`), chữ ký verify thành công bằng public key có fingerprint được xác minh độc lập.
5. **Consumer kiểm chứng được:** một project mới tải artifact từ repository đích, compile, resolve transitive dependencies và chạy được trên Java/JDK mục tiêu.

Ví dụ artifact:

~~~text
org.example.release:release-audit-lib:1.0.0
~~~

Một release repository theo Maven layout thường lưu:

~~~text
org/example/release/release-audit-lib/1.0.0/
    release-audit-lib-1.0.0.pom
    release-audit-lib-1.0.0.jar
    release-audit-lib-1.0.0-sources.jar
    release-audit-lib-1.0.0-javadoc.jar
    ... checksum sidecars/signatures tùy repository và quy trình xuất bản ...
~~~

Tên `-sources.jar` và `-javadoc.jar` ở đây là **classifier artifacts**, không phải Java runtime dependencies. Chữ ký và checksum cũng là các file riêng; chúng không được Maven tạo đầy đủ chỉ vì người viết đã khai báo `<packaging>jar</packaging>`.

**Phạm vi ví dụ:** Maven 3.9.x, JDK 17+, một thư viện Java 17 và một repository demo kiểu `file://`. Đó là **phát hành thử trong kho cục bộ**, không phải upload lên Maven Central. Mọi yêu cầu Central được tách thành phần riêng để không đánh đồng demo với release public.

## 2. Trình tự hậu kiểm theo thời gian

Một release workflow hợp lý:

~~~text
Source commit + release plan
    |
    v
Build, test, generate sources/Javadoc (+ sign nếu policy yêu cầu)
    |
    v
Review artifact set: JAR, POM, classifiers, signature/checksum policy
    |
    v
Upload/stage vào repository đích
    |
    v
Repository xác nhận publication/validation và artifacts đã có thể tải
    |
    v
Download/check tất cả file cùng GAV
    |
    +--> POM/metadata: đúng GAV, dependencies, parent và license
    +--> SHA-256/SHA-512 hoặc checksum sidecars theo policy
    +--> GPG: verify .asc, xác minh khóa ký
    +--> JAR: main bytecode, sources, Javadoc
    |
    v
Consumer build/test từ kho mới, tránh cache tình cờ
    |
    v
Ghi release evidence: Git SHA, GAV, repository, checksums, key ID,
                      test results, publication URL và approval
~~~

**Không bắt đầu từ bước cuối bằng cách chỉ kiểm có file `.jar`**. Một Maven library còn cần POM descriptor để consumer resolve dependencies. Tương tự, không chỉ kiểm `.pom` mà bỏ qua khả năng JAR bị cắt/nguyên liệu bị sai.

Hậu kiểm nên làm **trước khi thông báo đã phát hành tới người dùng**. Với staging repository hoặc Central Portal, upload và việc release bundle được xác nhận/được publish có thể là **hai trạng thái khác nhau**; phải chờ workflow của nhà cung cấp xác nhận trạng thái published, không suy từ stdout của công cụ upload.

## 3. Ba loại metadata: POM, Maven metadata và manifest

| Thành phần | Vai trò | Điều cần kiểm |
| --- | --- | --- |
| `artifactId-version.pom` | Maven Project Object Model được publish. | GAV/packaging, metadata, dependencies, parent/BOM, exclusions/scopes. |
| `maven-metadata.xml` | Repository-level/group/artifact/version metadata. | Version discovery, snapshot timestamps/build numbers; không thay POM. |
| `META-INF/MANIFEST.MF` trong JAR | Manifest của Java archive. | Main-Class/Implementation-Version/module-related information nếu project cấu hình. |
| `META-INF/maven/groupId/artifactId/pom.properties` trong JAR | Thông tin dự án có thể được Maven Archiver thêm. | Tọa độ để hỗ trợ nhận diện, không thay published POM. |
| External release manifest/attestation | Bằng chứng release của tổ chức. | Git commit, hashes, signatures, CI run, approver, build environment. |

**POM ≠ metadata.xml ≠ JAR manifest.** Các dependencies mà consumer Maven nhận được nằm trong POM/effective model (có thể kế thừa từ parent hoặc import BOM), không nằm trong `maven-metadata.xml` hay `MANIFEST.MF`.

Khi debug dependency resolution, đừng cố “sửa” thiếu `<dependencies>` bằng cách thêm một dòng vào JAR manifest. Khi debug SNAPSHOT timestamp, đừng tìm mọi thông tin trong `artifactId-version.pom`; repository metadata mới giúp resolver ánh xạ base snapshot đến các file timestamped.

## 4. Kiểm repository layout dựa trên GAV

Với `groupId=org.example.release`, `artifactId=release-audit-lib`, `version=1.0.0`, Maven chuẩn hóa groupId thành thư mục bằng cách thay dấu chấm bằng dấu gạch chéo:

~~~text
groupId:    org.example.release       -> org/example/release/
artifactId: release-audit-lib         -> release-audit-lib/
version:    1.0.0                     -> 1.0.0/
~~~

Vậy đường dẫn chính:

~~~text
org/example/release/release-audit-lib/1.0.0/release-audit-lib-1.0.0.pom
org/example/release/release-audit-lib/1.0.0/release-audit-lib-1.0.0.jar
~~~

Các artifact cùng GAV nhưng khác classifier được lưu chung folder với hậu tố filename:

~~~text
release-audit-lib-1.0.0-sources.jar
release-audit-lib-1.0.0-javadoc.jar
~~~

Không được diễn giải `-sources` hay `-javadoc` thành **version mới**. Chúng là classifier gắn với cùng version `1.0.0`.

Nếu `packaging=pom`, project có thể **không có main JAR**: parent POM/BOM dùng tệp POM làm artifact chính. Nếu `packaging=war`, main artifact là WAR; release checklist phải dựa trên packaging và attached artifacts thực tế, không bắt buộc `.jar` cho mọi project.

Một file xuất hiện ở đúng path **chưa đủ**: cần đối chiếu bytes và POM content bên trong.

## 5. Ví dụ runnable: thư viện Java 17 có main JAR, sources JAR, Javadoc JAR

Tạo project:

~~~text
release-audit-lib/
├── pom.xml
├── src/
│   ├── main/java/org/example/release/ReleaseGreeting.java
│   └── test/java/org/example/release/ReleaseGreetingTest.java
└── target/          # tạo khi build
~~~

Thư viện công khai một static method `ReleaseGreeting.greet(String)`. Plugin cấu hình trong POM sẽ:

- Biên dịch Java 17.
- Chạy JUnit Jupiter test.
- Đóng gói main JAR.
- Attach sources JAR bằng `maven-source-plugin:jar-no-fork`.
- Attach Javadoc JAR bằng `maven-javadoc-plugin:jar`.
- Dùng Maven Deploy Plugin khi chạy `deploy`.
- **Không** tự ký PGP trong demo; phần GPG được trình bày riêng vì cần private key và release policy.

Điều này giúp kiểm tra thực tế sự khác biệt giữa **file bắt buộc cho ví dụ local** và **những file thêm theo yêu cầu public repository**.

## 6. pom.xml hoàn chỉnh của release-audit-lib

Tạo `release-audit-lib/pom.xml` với nội dung:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>org.example.release</groupId>
    <artifactId>release-audit-lib</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <name>Release Audit Library Example</name>
    <description>Java 17 library for learning Maven publication audits.</description>
    <url>https://example.org/release-audit-lib/</url>

    <licenses>
        <license>
            <name>Apache License, Version 2.0</name>
            <url>https://www.apache.org/licenses/LICENSE-2.0.txt</url>
            <distribution>repo</distribution>
        </license>
    </licenses>

    <developers>
        <developer>
            <id>demo-maintainer</id>
            <name>Example Maintainer</name>
        </developer>
    </developers>

    <scm>
        <connection>scm:git:https://example.org/release-audit-lib.git</connection>
        <url>https://example.org/release-audit-lib/source</url>
    </scm>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <project.reporting.outputEncoding>UTF-8</project.reporting.outputEncoding>
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
                <version>3.5.2</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-source-plugin</artifactId>
                <version>3.3.1</version>
                <executions>
                    <execution>
                        <id>attach-sources</id>
                        <phase>verify</phase>
                        <goals>
                            <goal>jar-no-fork</goal>
                        </goals>
                    </execution>
                </executions>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-javadoc-plugin</artifactId>
                <version>3.11.2</version>
                <executions>
                    <execution>
                        <id>attach-javadoc</id>
                        <phase>verify</phase>
                        <goals>
                            <goal>jar</goal>
                        </goals>
                    </execution>
                </executions>
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

**Những điều phải hiểu trước khi chạy:**

1. `1.0.0` là **release version** trong ví dụ. Không nên redeploy cùng version vào kho thật nếu release đó đã công bố.
2. Các URL `example.org`, tên developer và namespace `org.example.release` **chỉ là thông tin đào tạo**. Không dùng để đăng ký/publish một package thực trên Maven Central. Một public release phải có SCM, license, developer và URL **đúng quyền sở hữu/thực tế**.
3. JUnit dependency có `scope=test`, nên không đi bắc cầu vào application runtime như một production dependency.
4. Source Plugin goal `jar-no-fork` tạo file classifier `sources`, còn Javadoc Plugin goal `jar` tạo classifier `javadoc`. Hai executions được gắn phase `verify` (trước `install` và `deploy`) để các files đã được attach khi publication.
5. `maven-deploy-plugin` trong POM **không tự biết repository đích**. Lúc thử nghiệm ta truyền `-DaltDeploymentRepository` tới một **file repository cục bộ**.
6. Không có Maven GPG Plugin trong POM runnable. Vì vậy **không kỳ vọng `.asc` xuất hiện** sau lệnh deploy demo; thiếu `.asc` trong demo local không phải nội dung QA fail, nhưng sẽ không đạt các yêu cầu Central.

## 7. Java source hoàn chỉnh và Javadoc metadata

Tạo `release-audit-lib/src/main/java/org/example/release/ReleaseGreeting.java`:

~~~java
package org.example.release;

/**
 * Một thư viện ví dụ để kiểm tra bộ artifact phát hành của Maven.
 */
public final class ReleaseGreeting {

    private ReleaseGreeting() {
    }

    /**
     * Trả về lời chào, loại khoảng trắng ở hai đầu tên.
     *
     * @param name tên cần chào, không được null
     * @return lời chào đã định dạng
     */
    public static String greet(String name) {
        return "Hello, " + name.strip() + "!";
    }
}
~~~

Hàm sử dụng `String.strip()` từ Java 11 trở lên, nên tương thích Java 17. Với đầu vào `" Maven "`, kết quả chính xác là:

~~~text
Hello, Maven!
~~~

Vì class/phương thức có Javadoc comment, Javadoc Plugin có thể tạo `org/example/release/ReleaseGreeting.html` trong Javadoc JAR. Sources JAR phải chứa `org/example/release/ReleaseGreeting.java`, còn main JAR phải chứa `org/example/release/ReleaseGreeting.class`.

Một lỗi dễ gặp sau publication là source JAR chứa file của **commit khác** với binary JAR dù cùng GAV. Cả ba artifacts cần được tạo từ **cùng pipeline/revision**, không chép bằng tay từ nhiều build khác nhau.

## 8. JUnit test để xác minh hành vi trước khi xuất bản

Tạo `release-audit-lib/src/test/java/org/example/release/ReleaseGreetingTest.java`:

~~~java
package org.example.release;

import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

class ReleaseGreetingTest {
    @Test
    void greetingStripsWhitespace() {
        assertEquals("Hello, Maven!", ReleaseGreeting.greet(" Maven "));
    }
}
~~~

Test này có một method, một assertion. Maven Surefire 3.5.2 nhận dạng file theo hậu tố `Test` và thực thi bằng JUnit Platform theo dependencies đã khai báo.

Tại thư mục `release-audit-lib/`:

~~~bash
mvn -B -ntp clean verify
~~~

Lệnh compile Java, chạy test và tạo attached source/Javadoc artifacts vì hai plugin executions được gắn vào `verify`.

Kết quả trọng tâm dự kiến:

~~~text
target/release-audit-lib-1.0.0.jar
target/release-audit-lib-1.0.0-sources.jar
target/release-audit-lib-1.0.0-javadoc.jar
target/surefire-reports/
~~~

Có thể còn nhiều files/classes/generated docs khác. **Chưa có tệp PGP `.asc` chỉ từ `mvn verify` trong demo này.**

## 9. Kiểm trước khi deploy: artifact inventory

Từ thư mục project root trên Linux/macOS:

~~~bash
ls -l target/release-audit-lib-1.0.0.jar
ls -l target/release-audit-lib-1.0.0-sources.jar
ls -l target/release-audit-lib-1.0.0-javadoc.jar
~~~

Những file này cần **tồn tại và không rỗng** theo cấu hình POM ở mục 6.

Kiểm main JAR:

~~~bash
jar tf target/release-audit-lib-1.0.0.jar
~~~

Trong danh sách cần thấy:

~~~text
org/example/release/ReleaseGreeting.class
~~~

Kiểm sources JAR:

~~~bash
jar tf target/release-audit-lib-1.0.0-sources.jar
~~~

Trong danh sách cần thấy:

~~~text
org/example/release/ReleaseGreeting.java
~~~

Kiểm Javadoc JAR:

~~~bash
jar tf target/release-audit-lib-1.0.0-javadoc.jar
~~~

Trong đó cần có `index.html` và trang API của class, thường là:

~~~text
org/example/release/ReleaseGreeting.html
~~~

Các câu lệnh `jar tf` có thể in thêm manifest, thư mục, module-level assets. Những khối trên chỉ liệt kê **entry quan trọng để QA**. `jar tf` dùng JDK launcher tool; không cần thêm một Maven plugin để đọc ZIP/JAR container.

Nếu sources/Javadoc không được attach, hãy kiểm plugin executions và lifecycle phase. Đừng giải quyết bằng cách rename main JAR thành `-sources.jar` hoặc `-javadoc.jar`: classifier artifacts phải chứa **nội dung tương ứng**.

## 10. Deploy thử vào repository file:// trên Linux/macOS

Để luyện hậu kiểm mà không công bố gì lên Internet, dùng một Maven repository demo trên filesystem. Từ thư mục `release-audit-lib/`:

~~~bash
mkdir -p /tmp/maven-release-audit-repo
mvn -B -ntp clean deploy "-DaltDeploymentRepository=audit::file:///tmp/maven-release-audit-repo"
~~~

**Ý nghĩa chính xác:**

- `-DaltDeploymentRepository=id::url` dùng cú pháp của Maven Deploy Plugin 3.x; ở đây `id=audit` và URL là `file:///tmp/maven-release-audit-repo`.
- Không có `distributionManagement` remote trong POM; tham số CLI chọn repository đích cho lần thử này.
- `file://` ghi vào **một thư mục local repo-format** trên máy bạn; nó không phải Maven Central hay server của đồng đội.
- `clean deploy` chạy các phases đến `deploy`, gồm compile/test, các executions attach sources/Javadoc và upload/copy artifacts + POM sang file repository.
- Repository file có thể không thực thi immutable-release policy như một repository manager chuyên dụng. **Không chạy lặp mãi để chứng minh overwrite release là hợp lệ**; dùng một thư mục demo riêng hoặc tăng version khi làm thử nghiệm tiếp.

Với shell Windows, đường dẫn repository nên được biến thành **file URI tuyệt đối hợp lệ** (ví dụ `file:///C:/.../maven-release-audit-repo`), không đặt chuỗi `C:\...` trực tiếp sau `id::` rồi kỳ vọng Maven tự suy ra URI. Lệnh Unix ở trên dành cho Linux/macOS có `/tmp`.

**Nếu một kho thật dùng credentials**, cẩn trọng với `altDeploymentRepository`: id có thể khớp entry trong `settings.xml`; các phiên bản Deploy Plugin mới có quy tắc chống gửi credentials sang URL khác. Trong ví dụ dùng id `audit` và file URI, không lưu server credentials cho id này. Không đổi id/URL sang production tùy tiện.

## 11. Kiểm bộ tệp sau khi deploy vào repository demo

Sau lệnh thành công, kiểm folder:

~~~bash
ls -l /tmp/maven-release-audit-repo/org/example/release/release-audit-lib/1.0.0/
~~~

Những tệp **chính** cần có:

~~~text
release-audit-lib-1.0.0.pom
release-audit-lib-1.0.0.jar
release-audit-lib-1.0.0-sources.jar
release-audit-lib-1.0.0-javadoc.jar
~~~

Các file checksum sidecar như `.sha1`/`.md5` có thể được tạo theo Maven transport/repository policy. **Đừng khẳng định file:// demo luôn tạo đúng bộ checksum và chữ ký của Maven Central.** Không có `.asc` trong demo vì POM chưa ký.

Cần xác minh cả **tên file, byte length, khả năng đọc** và nội dung:

- POM phải có GAV `org.example.release:release-audit-lib:1.0.0`.
- POM không có `<parent>` private/missing của một source tree khác.
- JAR chứa class `ReleaseGreeting.class`.
- Sources JAR chứa source class `ReleaseGreeting.java`.
- Javadoc JAR chứa tài liệu API.
- Mọi file được lấy từ **cùng lần release** và đã qua test.
- Không có file thử nghiệm ngoài plan (ví dụ một `tests.jar` do plugin attach tình cờ) bị publish mà không được review.

Một tệp có đúng tên nhưng `0 bytes`, bị truncate hoặc chứa sai nội dung phải được coi là release defect chứ không phải warning có thể bỏ qua.

## 12. POM được công bố: kiểm GAV và hợp đồng của consumer

Đường dẫn POM trong demo:

~~~text
/tmp/maven-release-audit-repo/org/example/release/release-audit-lib/1.0.0/release-audit-lib-1.0.0.pom
~~~

Kiểm các field:

~~~xml
<groupId>org.example.release</groupId>
<artifactId>release-audit-lib</artifactId>
<version>1.0.0</version>
<packaging>jar</packaging>
~~~

Đồng thời kiểm:

- `<name>`, `<description>` và `<url>`.
- `<licenses>` có đúng license mà source/binary được phép phân phối.
- `<developers>` và `<scm>` trỏ người/địa chỉ thực tế khi chuẩn bị publication công khai.
- `<dependencies>` và các scopes đúng. Ví dụ chỉ có `junit-jupiter:5.11.4` với scope test, không truyền như runtime dependency của consumer.
- `<parent>` và `<dependencyManagement>`/BOM (nếu thư viện thực có dùng) đều resolve được từ nơi consumer truy cập.
- Mọi placeholder dùng `revision/changelist` của Maven 3 CI-friendly đã được publish theo cơ chế POM consumable, không để model gây lỗi cho consumer.

**Sự hiện diện của XML đúng GAV chỉ là bước đầu.** Nếu POM thiếu một dependency compile/runtime bắt buộc, consumer có thể build sai hoặc gặp `NoClassDefFoundError`, dù main JAR có checksum hợp lệ. Checksum chứng minh bytes nhất quán với checksum expected, **không chứng minh POM semantically đúng**.

Một lỗi khác: POM trong repo nói `version=1.0.1` nhưng folder/artifact name là `1.0.0`, hoặc POM chứa parent artifact không tồn tại. Đây là lỗi phát hành metadata, cần ngăn consumer tiếp tục dùng release chưa được xác minh.

## 13. Checksum là gì, và nó chứng minh được điều gì?

Checksum/digest là kết quả áp dụng hàm băm lên bytes của một file. Với SHA-256, kết quả thường biểu diễn dưới dạng **64 ký tự hex**. Nếu đổi dù chỉ một byte, giá trị hash thay đổi với xác suất cực cao.

Các đuôi thường gặp trong Maven repository:

| Đuôi | Thuật toán | Cách sử dụng hợp lý |
| --- | --- | --- |
| `.md5` | MD5 | Tương thích các repository/protocol đời cũ; **không** là bảo đảm bảo mật chống kẻ chủ đích. |
| `.sha1` | SHA-1 | Kiểm dữ liệu theo quy trình legacy; **không** đủ tin cậy để chống tấn công chủ động. |
| `.sha256` | SHA-256 | Ưu tiên dùng để đối chiếu tính toàn vẹn hiện đại. |
| `.sha512` | SHA-512 | Tương tự, với digest dài hơn. |

Theo **Sonatype Central Publishing Requirements** đang được tài liệu hóa, bundle cần checksum files `.md5` và `.sha1`; `.sha256` và `.sha512` được hỗ trợ nhưng không bắt buộc. Điều này là **quy định tương thích của repository**, không có nghĩa MD5/SHA-1 mạnh hơn SHA-256. Central Publishing Maven Plugin có thể tạo checksums theo bundling workflow của nó; không suy rằng mọi Maven Deploy Plugin file repository sẽ sinh đúng cùng tập.

**Phân biệt:**
- **Digest tự tính trên file vừa tải** chỉ là fingerprint của bytes bạn có.
- **Digest so sánh với expected từ nguồn tin cậy** cho biết bytes khớp với bản được tuyên bố.
- **Hai file + checksum cùng bị thay bởi một attacker** vẫn có thể khớp; checksum đơn thuần không chứng minh danh tính publisher.

Vì vậy phải kết hợp checksum với signature/provenance và nguồn kênh đáng tin cậy khi yêu cầu security cao.

## 14. Tính SHA-256 trên Linux, macOS và Windows

Sau khi lấy JAR và POM từ repository, đối chiếu hash đã được lưu trong release manifest/trusted checksum record.

Linux (GNU coreutils):

~~~bash
sha256sum release-audit-lib-1.0.0.jar
sha256sum release-audit-lib-1.0.0.pom
sha256sum release-audit-lib-1.0.0-sources.jar
sha256sum release-audit-lib-1.0.0-javadoc.jar
~~~

macOS (tool phổ biến):

~~~bash
shasum -a 256 release-audit-lib-1.0.0.jar
shasum -a 256 release-audit-lib-1.0.0.pom
~~~

Windows PowerShell:

~~~powershell
Get-FileHash -LiteralPath .\release-audit-lib-1.0.0.jar -Algorithm SHA256
Get-FileHash -LiteralPath .\release-audit-lib-1.0.0.pom -Algorithm SHA256
Get-FileHash -LiteralPath .\release-audit-lib-1.0.0-sources.jar -Algorithm SHA256
Get-FileHash -LiteralPath .\release-audit-lib-1.0.0-javadoc.jar -Algorithm SHA256
~~~

**Không bịa ra giá trị hash cụ thể**: SHA-256 phụ thuộc đúng bytes được tạo (và có thể khác khi build timestamp/archive order khác). Output phải được đọc **sau khi có file thật**.

Nếu repository cung cấp sidecar `release-audit-lib-1.0.0.jar.sha256` chứa một digest hex, so với SHA-256 vừa tính. Nếu sidecar không có, kiểm một **manifest có hash do release pipeline tạo và được bảo vệ/được ký**, hoặc dùng checksum từ một nguồn độc lập đã được xác minh.

Lưu ý định dạng sidecar: một số hệ thống lưu chỉ hex, số khác có cả tên file hoặc whitespace; hãy parse đúng theo repository policy. Không dùng `sha256sum -c somefile.sha256` một cách máy móc nếu file chỉ chứa hex mà không có tên file theo định dạng của công cụ.

## 15. So sánh bytes của local build và bản đã deploy

Ví dụ `mvn deploy` qua `file://` đã tạo:

~~~text
release-audit-lib/target/release-audit-lib-1.0.0.jar
/tmp/maven-release-audit-repo/org/example/release/release-audit-lib/1.0.0/release-audit-lib-1.0.0.jar
~~~

Từ thư mục `release-audit-lib/` có thể kiểm:

~~~bash
sha256sum target/release-audit-lib-1.0.0.jar
sha256sum /tmp/maven-release-audit-repo/org/example/release/release-audit-lib/1.0.0/release-audit-lib-1.0.0.jar
~~~

Nếu đây chính xác là **cùng artifact bytes** vừa deploy, hai giá trị SHA-256 phải giống nhau. Làm tương tự cho sources/Javadoc JARs.

Trên Linux/macOS, có thể kiểm equality trực tiếp:

~~~bash
cmp -s target/release-audit-lib-1.0.0.jar /tmp/maven-release-audit-repo/org/example/release/release-audit-lib/1.0.0/release-audit-lib-1.0.0.jar
~~~

Lệnh `cmp -s` trả exit code 0 nếu giống nhau, khác 0 nếu khác/lỗi; nó **không nhất thiết in chữ “PASS”**. Một cách bền vững hơn là ghi digest/sizes vào release evidence. Với remote HTTPS repository, phải **download artifact từ URL đã public** rồi so với hash tin cậy; kiểm file còn trong workspace build chưa chứng minh remote publication.

**Đừng mặc định POM được deploy phải byte-for-byte giống `pom.xml` trong source** nếu pipeline có bước flatten, resolve versions, transform descriptor hoặc inject metadata. Khi đó kiểm **published POM chính là bản consumer nhìn thấy**, đồng thời đối chiếu metadata semantically và release policy.

## 16. Kiểm chữ ký detached .asc: khác checksum

Chữ ký GPG/PGP detached thường có tên:

~~~text
release-audit-lib-1.0.0.pom.asc
release-audit-lib-1.0.0.jar.asc
release-audit-lib-1.0.0-sources.jar.asc
release-audit-lib-1.0.0-javadoc.jar.asc
~~~

Theo yêu cầu Maven Central được công bố, các tệp chính được tải lên cần chữ ký `.asc` tương ứng; **signature không tự sinh từ hash sidecar**, và không nên nhầm `.asc` với file checksum hex.

Khi đã có public key của publisher **được xác minh fingerprint qua kênh đáng tin cậy**, chạy từ thư mục chứa artifact:

~~~bash
gpg --verify release-audit-lib-1.0.0.jar.asc release-audit-lib-1.0.0.jar
gpg --verify release-audit-lib-1.0.0.pom.asc release-audit-lib-1.0.0.pom
gpg --verify release-audit-lib-1.0.0-sources.jar.asc release-audit-lib-1.0.0-sources.jar
gpg --verify release-audit-lib-1.0.0-javadoc.jar.asc release-audit-lib-1.0.0-javadoc.jar
~~~

**Điều kiện đạt:** lệnh verify trả thành công cho file tương ứng, chữ ký gắn với **đúng nội dung**, và fingerprint của key signer khớp với identity đã được phê duyệt. Một dòng “Good signature” từ key chưa xác minh danh tính **không đủ** cho supply-chain trust.

Để kiểm fingerprint key trong keyring:

~~~bash
gpg --list-keys --fingerprint
~~~

Đừng import khóa công khai **chỉ** từ cùng website không đáng tin đang cung cấp artifact rồi tự coi đã xác minh publisher. Public key và fingerprint cần được đối chiếu với thông báo/chuỗi tin cậy của nhà phát hành.

**Demo `file://` ở mục 10 không tạo `.asc`**, nên không chạy những lệnh verify này đối với demo mà giả định file tồn tại. Để phát hành thật, phải tích hợp signing workflow có key management theo chính sách.

## 17. Cấu hình Maven GPG Plugin: ví dụ chỉ dành cho release pipeline

Apache Maven GPG Plugin có goal `gpg:sign` ký project POM, main artifact và attached artifacts để deploy. Một phần cấu hình ví dụ (không phải POM runnable local ở mục 6):

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-gpg-plugin</artifactId>
    <version>3.2.8</version>
    <executions>
        <execution>
            <id>sign-release</id>
            <phase>verify</phase>
            <goals>
                <goal>sign</goal>
            </goals>
        </execution>
    </executions>
</plugin>
~~~

Giải thích:

- `gpg:sign` cần GnuPG/key hoặc signer được cấu hình đúng và sẽ tạo attached signatures phục vụ deploy.
- Trong release pipeline, nên chạy `gpg:sign` **sau khi** main JAR, sources và Javadoc đã attach; nếu cùng phase `verify`, kiểm thứ tự plugin executions và mọi artifact được ký.
- Maven GPG Plugin 3.2.x có các lựa chọn best-practices để tránh ghi passphrase trực tiếp trong POM/settings/CLI. Ưu tiên GPG agent, CI secret environment và chính sách key handling của tổ chức.
- Không lưu private key, passphrase, server password hay token trong Git/POM mẫu.
- Nếu producer dùng các signing mechanisms khác, kiểm định dạng chữ ký/repository acceptance trước khi chọn công cụ.

**Ranh giới nhiệm vụ:** ví dụ local không cần GPG key để học hậu kiểm bộ file; phần GPG mô tả release pipeline có quyền, không cung cấp lệnh “đăng ký public key mới” hay tự publish lên Central.

## 18. Vì sao Central yêu cầu MD5/SHA-1 dù SHA-256 mạnh hơn?

Các hệ thống Maven truyền thống sử dụng `.md5` và `.sha1` sidecars trong repository layout để hỗ trợ checksum validation. Sonatype Central Publishing Requirements hiện nêu:

- `.md5` và `.sha1` là những checksum filenames **bắt buộc trong bộ file upload** theo yêu cầu công bố của họ.
- `.sha256` và `.sha512` được hỗ trợ nhưng không bắt buộc.
- `.asc` signatures được yêu cầu cho các primary files; **không cần tạo thêm `.asc.asc` hoặc checksum sidecars của chính chữ ký**, theo tài liệu Central.
- Central Publishing Maven Plugin có thể tạo checksums cho bundle, nhưng nó không tự tạo đầy đủ sources/Javadoc/signatures hoặc metadata đúng nếu project không cấu hình.

Đây là **yêu cầu bundle format của một nhà cung cấp repository**, không phải khuyến nghị dùng MD5 làm căn cứ an ninh. Để kiểm tính toàn vẹn theo tiêu chuẩn bảo mật hiện đại, **ưu tiên SHA-256/SHA-512 và xác minh chữ ký/nguồn**. Không bỏ việc kiểm chữ ký chỉ vì `.sha1` khớp.

Mỗi repository manager có policy riêng. Ví dụ file repo local không nhất thiết có mọi sidecar theo Central; một Nexus/Artifactory nội bộ có thể tạo/hiển thị checksums dưới hình thức khác. Vì vậy checklist cần có **mục tiêu repository cụ thể**, không áp một chuẩn duy nhất cho mọi kho.

## 19. POM metadata công khai: những trường cần rà soát

Với một public Java library, người dùng và repository policy thường cần:

| Trường POM | Điều cần xác minh |
| --- | --- |
| `modelVersion` | Mô hình hợp lệ, phổ biến là `4.0.0`. |
| `groupId` | Namespace có quyền sử dụng, khớp repository path. |
| `artifactId` | Đúng tên artifact, không vô tình trùng project khác. |
| `version` | Release version đã phê duyệt; không có `-SNAPSHOT` nếu kho chỉ nhận releases. |
| `packaging` | Đúng main artifact type (jar/pom/war...). |
| `name` | Tên project người dùng nhận biết. |
| `description` | Diễn giải chức năng cụ thể. |
| `url` | Trang dự án/tài liệu thực có thể truy cập. |
| `licenses` | License đúng với quyền phân phối thực tế. |
| `developers` | Người/nhóm phát triển có thể liên hệ. |
| `scm` | URL source repository và read-only connection đúng. |
| `dependencies` | Direct dependencies thực sự cần cho compile/runtime/test. |
| `parent` | Parent POM đúng GAV và có thể resolve khi consumer tải. |
| `dependencyManagement`/BOM | Versions management không che dependency thiếu hoặc BOM không publish. |

**Không tuyên bố demo POM với `example.org` đạt yêu cầu Maven Central.** Nó chỉ biểu diễn cấu trúc hợp lệ để học. Những field về license, developer và SCM **phải được thay bằng dữ liệu chính xác của dự án** trước một lần xuất bản công khai.

Ngoài POM, Central thường yêu cầu main artifact, sources JAR, Javadoc JAR, chữ ký và checksums đúng. Những yêu cầu có thể thay đổi; khi triển khai pipeline production, đối chiếu chính tài liệu repository được dùng ở thời điểm release.

## 20. Kiểm dependencies: POM đúng GAV nhưng graph vẫn có thể sai

Giả sử library compile nhờ dependency:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.example.utils</groupId>
        <artifactId>text-core</artifactId>
        <version>2.0.0</version>
        <scope>compile</scope>
    </dependency>
</dependencies>
~~~

Đây là **mảnh POM giả định**, không thuộc runnable demo; `org.example.utils:text-core` không tồn tại trong bài học.

Nếu tác giả build có `text-core` trong local cache nhưng **published POM thiếu dependency này**, consumer ngoài source tree có thể compile hoặc run lỗi. POM descriptor mới là nguồn Maven dùng cho transitive graph, không phải bytecode JAR tự chứng minh.

Khi hậu kiểm, cần xác nhận:

1. **Compile/runtime dependencies** có đúng GAV/version.
2. **test dependencies** không vô tình bị biến thành transitive production dependencies.
3. **provided/optional** được chọn có chủ đích; không làm thiếu classes tại runtime nếu không có container cung cấp.
4. **exclusions** không loại bỏ module thực sự cần thiết.
5. Parent/BOM/CI-friendly versions được resolve ở **consumer context**.
6. Consumer dependency mediation không âm thầm chọn một version khác do graph conflict.

Chạy `dependency:tree` trên **consumer tách biệt** là phép thử mạnh hơn chỉ nhìn POM tác giả vì nó mô phỏng những dependencies mà người dùng thực nhận.

## 21. Parent POM và BOM phải thực sự resolve được

Một published library POM có thể ghi:

~~~xml
<parent>
    <groupId>org.example.build</groupId>
    <artifactId>company-parent</artifactId>
    <version>3.0.0</version>
</parent>
~~~

Hoặc import BOM:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.example.platform</groupId>
            <artifactId>release-bom</artifactId>
            <version>2.0.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Đây là **hai mảnh riêng minh họa**, không thuộc demo single-module. Consumer cần resolve `company-parent:3.0.0` hoặc `release-bom:2.0.0` nếu POM đã publish tham chiếu chúng. Một `relativePath` trỏ tới source tree máy tác giả không đủ cho consumer ở máy khác.

Nếu parent chỉ có trong private repository mà public consumer không có quyền, artifact main JAR có thể tải được nhưng Maven vẫn báo `Non-resolvable parent POM`. Nếu imported BOM không tồn tại, consumer có thể gặp `Non-resolvable import POM`.

**Hậu kiểm đúng:** tạo consumer ngoài reactor và chỉ trỏ tới repository thực. Không cài tay parent/BOM vào local cache rồi kết luận remote publication đã đầy đủ.

## 22. Maven 3 CI-friendly và POM flatten sau xuất bản

Khi dùng Maven 3 CI-friendly versions, POM source có thể viết:

~~~xml
<version>${revision}${changelist}</version>
~~~

Maven reactor source có thể build đúng nhờ `revision` và `changelist` được cung cấp trong properties/CI. Nhưng **published POM** phải consumable từ repository; nếu vẫn còn version placeholders trong những vị trí không được resolver downstream xử lý như dự kiến, consumer có thể không resolve được parent/dependency graph.

Theo Apache Maven CI Friendly Versions, thường dùng **Flatten Maven Plugin** với `flattenMode=resolveCiFriendliesOnly` và `updatePomFile=true` để tạo POM xuất bản chứa coordinates đã được resolve. Hãy kiểm **POM thực trên repository**, không chỉ source POM trong Git.

Đừng chọn flatten mode quá mạnh khiến published POM **mất các dependencies** cần cho transitive resolution. Khi bước phát hành thay POM, phép kiểm **byte-for-byte source POM vs remote POM** không còn hợp lý; thay bằng so sánh effective metadata và chứng minh consumer có thể build/run.

Một published POM không tương thích là lỗi phát hành ngay cả khi main JAR hash khớp expected.

## 23. Check signature của POM quan trọng ngang signature JAR

Một library phụ thuộc nhiều modules thông qua POM. Kẻ tấn công không nhất thiết thay bytecode JAR: chỉ sửa POM dependency để thêm một artifact độc hại cũng làm consumer tải code không mong muốn.

Do đó trong supply-chain verification:

- Kiểm checksum của **POM** chứ không chỉ main JAR.
- Kiểm detached signature của **POM** khi repository/publisher cung cấp.
- Kiểm parent/BOM POMs quan trọng nếu chúng nằm trong trust boundary.
- Kiểm transitive dependencies và repository provenance.
- Không coi “JAR signature good” là bằng chứng rằng POM cùng GAV không bị sửa.

Một release evidence tốt gồm hash của main JAR, POM, sources, Javadoc và signer fingerprint cho từng file được yêu cầu ký. Nếu có SBOM/attestation/provenance files, cần kiểm chúng theo schema/chữ ký/chính sách riêng thay vì giả định Maven đọc chúng tự động.

## 24. Sources JAR: kiểm có source thật và khớp version

Sources JAR giúp IDE duyệt mã; khi cung cấp cho người dùng, nó phải tương ứng với binary đang chạy. File dự kiến:

~~~text
release-audit-lib-1.0.0-sources.jar
~~~

Kiểm:

~~~bash
jar tf release-audit-lib-1.0.0-sources.jar
~~~

Cần có:

~~~text
org/example/release/ReleaseGreeting.java
~~~

**Các lỗi thường gặp:**

- Sources JAR là archive rỗng hoặc chỉ có `README` mà release policy không cho phép.
- Sources được build từ commit khác với main binary.
- Sources chứa generated code chưa khớp class files được publish.
- Source package path khác `.class` package path.
- Không có `-sources.jar` dù repository yêu cầu.

Một số repository cho phép sources/Javadoc placeholder archives theo hướng dẫn đặc biệt, nhưng **không khuyến khích giả vờ đó là tài liệu đầy đủ**. Với thư viện Java thông thường, attach source thực tế là lựa chọn hữu ích cho consumer.

## 25. Javadoc JAR: tệp có mặt chưa bảo đảm tài liệu tốt

File dự kiến:

~~~text
release-audit-lib-1.0.0-javadoc.jar
~~~

Kiểm:

~~~bash
jar tf release-audit-lib-1.0.0-javadoc.jar
~~~

Thông thường phải có những tệp như:

~~~text
index.html
org/example/release/ReleaseGreeting.html
~~~

Những điều cần kiểm thêm:

- Javadoc build từ **đúng source revision**.
- API pages mô tả đúng public classes/methods.
- Internal/private APIs không bị công bố ngoài ý muốn.
- Không có links tới tài liệu nội bộ chưa được phép chia sẻ.
- Java version đúng API/bytecode target; nếu Java 17 trở lên, consumer dùng JDK thấp hơn không chạy được binary.
- HTML có thể mở trong trình duyệt và không lỗi encoding/resource paths.

Maven Central yêu cầu Javadoc JAR theo chính sách xuất bản; một file `-javadoc.jar` chứa sai nội dung vẫn là vấn đề chất lượng, dù validator có thể chỉ kiểm file tồn tại.

## 26. GPG signing khác jarsigner và Java manifest

Có nhiều dạng “ký” dễ bị nhầm:

- **OpenPGP detached signature `.asc`**: thường dùng khi publish Maven artifacts lên Central; ký bytes của `.jar`/`.pom`/`-sources.jar`/`-javadoc.jar`.
- **JAR signing (Jarsigner)**: các entries và metadata signature nằm **bên trong JAR** theo cơ chế Java; không tự tạo `.jar.asc` theo Maven Central convention.
- **Git tag signature**: xác minh SCM tag/commit, **không thay thế** chữ ký bytes của từng file đã publish.
- **Checksum sidecar**: không có private key; chỉ biểu diễn digest.

Công cụ `jarsigner -verify release-audit-lib-1.0.0.jar` không thay `gpg --verify release-audit-lib-1.0.0.jar.asc release-audit-lib-1.0.0.jar`. Nếu repository policy yêu cầu OpenPGP signatures, dùng đúng loại.

Git tag ký có ích cho source provenance, nhưng artifact bytes có thể vẫn sai nếu pipeline build từ source khác. Hậu kiểm nên kết nối Git SHA → build job → artifact hashes → signatures → repository coordinates.

## 27. SNAPSHOT publication khác release publication

Với `1.0.1-SNAPSHOT`, Maven remote snapshot repository có thể lưu:

~~~text
release-audit-lib/1.0.1-SNAPSHOT/
    release-audit-lib-1.0.1-20261110.103020-1.jar
    release-audit-lib-1.0.1-20261110.103020-1.pom
    maven-metadata.xml
~~~

Timestamp là **minh họa**, không phải bản đã deploy. `maven-metadata.xml` ở version-level giúp Maven resolve base snapshot tới timestamped artifacts. Kiểm SNAPSHOT publication cần đối chiếu **metadata timestamp/buildNumber, extensions/classifiers và file mà consumer thực resolve**.

Với release `1.0.0`, tên file thường cố định theo version và repository policy nên chặn overwrite. **Không dùng `-U` như cách xác nhận release file vừa thay**, vì release không nên bị thay bytes dưới cùng GAV.

Nếu phát hiện release có POM sai hoặc checksum/signature mismatch sau khi đã immutable, thường **phát hành version mới** (ví dụ `1.0.1`) theo policy thay vì sửa lại `1.0.0` trong repository. Điều này giữ tính tin cậy của cache và artifact coordinates.

## 28. Một consumer độc lập để xác minh từ file repository

Sau khi deploy demo vào `/tmp/maven-release-audit-repo`, tạo consumer project **ngoài thư mục source release-audit-lib**, ví dụ:

~~~text
release-audit-consumer/
├── pom.xml
└── src/main/java/org/example/consumer/AuditMain.java
~~~

Consumer cần trỏ đúng repository file URL và chỉ khai báo main library.

Tạo `release-audit-consumer/pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>org.example.consumer</groupId>
    <artifactId>release-audit-consumer</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <repositories>
        <repository>
            <id>audit</id>
            <url>file:///tmp/maven-release-audit-repo</url>
            <releases><enabled>true</enabled></releases>
            <snapshots><enabled>false</enabled></snapshots>
        </repository>
    </repositories>

    <dependencies>
        <dependency>
            <groupId>org.example.release</groupId>
            <artifactId>release-audit-lib</artifactId>
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
        </plugins>
    </build>
</project>
~~~

POM này là **consumer demo đầy đủ**, dùng path Unix khớp lệnh deployment ở mục 10. Nó không cần parent từ source library. `<repositories>` trỏ file repository dùng để lấy **project dependencies**, không phải `<distributionManagement>` (đích deploy), và không phải Maven local cache.

Trong ứng dụng thật, nên quản lý repositories qua corporate settings/mirror hoặc standard Central thay vì hard-code một path local vào POM được share.

## 29. Mã Java consumer và chạy trên môi trường khác source tree

Tạo `release-audit-consumer/src/main/java/org/example/consumer/AuditMain.java`:

~~~java
package org.example.consumer;

import org.example.release.ReleaseGreeting;

public final class AuditMain {
    private AuditMain() {
    }

    public static void main(String[] args) {
        System.out.println(ReleaseGreeting.greet(" Maven "));
    }
}
~~~

Từ `release-audit-consumer/` chạy trên Linux/macOS:

~~~bash
mvn -B -ntp "-Dmaven.repo.local=/tmp/maven-audit-consumer-cache" clean verify
~~~

`-Dmaven.repo.local` chỉ định local cache riêng; do đó consumer không dùng `release-audit-lib` tình cờ được install trong local repository mặc định của tác giả. Các Maven plugins/third-party dependencies cũng cần resolve từ repository được Maven/CI cho phép, nên môi trường cần có kết nối hoặc cache chuẩn.

Sau build, JAR library từ file repository được cache ở:

~~~text
/tmp/maven-audit-consumer-cache/org/example/release/release-audit-lib/1.0.0/release-audit-lib-1.0.0.jar
~~~

Chạy Java:

~~~bash
java -cp "target/classes:/tmp/maven-audit-consumer-cache/org/example/release/release-audit-lib/1.0.0/release-audit-lib-1.0.0.jar" org.example.consumer.AuditMain
~~~

**Stdout chính xác của chương trình Java:**

~~~text
Hello, Maven!
~~~

Với Windows, phải dùng file URI đúng và `;` thay `:` làm classpath separator. Consumer này là thí nghiệm local, không kiểm upload Maven Central. Tuy nhiên nó minh họa nguyên tắc mạnh: **download/copy từ repository đích rồi chạy trong consumer ngoài reactor**, không dựa vào source tree của library.

## 30. Kiểm dependency graph của consumer sạch

Trong `release-audit-consumer/`:

~~~bash
mvn -B -ntp "-Dmaven.repo.local=/tmp/maven-audit-consumer-cache" org.apache.maven.plugins:maven-dependency-plugin:3.8.1:tree
~~~

Một phần graph dự kiến:

~~~text
org.example.consumer:release-audit-consumer:jar:1.0.0
\- org.example.release:release-audit-lib:jar:1.0.0:compile
~~~

Library có JUnit Jupiter với `scope=test` trong POM của tác giả, nên consumer **không** nhận nó như production transitive dependency chỉ vì library có unit test.

Nếu library thực dùng dependencies compile/runtime, chúng phải xuất hiện theo Maven scope/optional/exclusion rules khi consumer resolve. Đó là lý do đọc **published POM thực tế**, không chỉ xem source `pom.xml` ở máy tác giả.

Kết quả consumer pass cho thấy Maven tìm và dùng artifact theo tọa độ; không thay việc verify signatures/checksums nếu threat model yêu cầu supply-chain authenticity.

## 31. Phân loại bộ tệp phụ trong một release phức tạp

Các dự án có thể attach nhiều file hơn demo:

| File hoặc classifier | Vai trò | Lưu ý hậu kiểm |
| --- | --- | --- |
| Main `.jar`/`.war` | Binary chính của artifact. | Nội dung/manifest/classpath tương thích. |
| `-sources.jar` | Nguồn Java tương ứng. | Source paths và revision khớp main JAR. |
| `-javadoc.jar` | API docs. | Chứa pages hợp lệ, không lộ tài liệu private. |
| `-tests.jar` | Test classes (khi dùng Test JAR Plugin). | Không xuất hiện nếu project không attach; consumers thường cần type/classifier tương ứng. |
| `-native-*.jar` | Binaries theo OS/architecture. | Classifier, runtime platform và checksum chính xác. |
| `-all.jar`/`-shaded.jar` | Bundled artifact. | Review dependency-reduced POM/class conflicts. |
| `.asc` | Chữ ký OpenPGP detached. | Verify từng file được ký, kiểm signer fingerprint. |
| `.md5`/`.sha1`/`.sha256`/`.sha512` | Checksum sidecars. | So bytes, không coi là authenticated identity. |
| SBOM (CycloneDX/SPDX) | Danh sách thành phần và dependencies, nếu dự án tạo. | Kiểm version, schema, provenance và signing policy. |
| Provenance/attestation | Bằng chứng build nguồn gốc. | Xác minh signer/trust policy, build identity và source commit. |
| `maven-metadata.xml` | Repository metadata. | Release version discovery hoặc snapshot resolution. |

**Không có quy tắc “mọi Maven library phải có tất cả những loại file trên”.** Tập required phụ thuộc packaging, classifiers đã attach và yêu cầu repository (Central hay kho nội bộ). Hậu kiểm nên bắt đầu từ **artifact inventory expected**, không bắt đầu từ một danh sách file cố định có nguy cơ tạo báo động giả.

Ngoài ra, đừng nhầm `-sources.jar` với `-test-sources.jar`, `-tests.jar` với JUnit runtime dependency hoặc SBOM với POM dependency graph. Chúng phục vụ các mục tiêu khác nhau.

## 32. Cách xử lý khi một file bị thiếu hoặc checksum mismatch

**Trường hợp A: thiếu `-sources.jar`.** Kiểm `maven-source-plugin`, execution phase, `attach` và thông báo deploy. Nếu repository đích yêu cầu sources, coi release chưa sẵn sàng.

**Trường hợp B: thiếu `-javadoc.jar`.** Kiểm plugin/goal, JDK toolchain, Javadoc warnings/errors; không đổi tên main JAR để giả lập.

**Trường hợp C: POM khác expectation.** Kiểm flatten/revision/parent/dependencyManagement/exclusions; xây consumer sạch. Nếu production release đã immutable, không cập nhật âm thầm POM của cùng GAV.

**Trường hợp D: checksum mismatch.** Đừng chỉ retry vô hạn rồi công bố pass. Xác nhận expected hash đến từ nguồn tin cậy, kiểm file tải chưa hoàn tất/proxy/cache, so với release manifest, cách tải (binary mode) và ghi nhận incident. Không chấp nhận file sai digest để tiếp tục publish.

**Trường hợp E: chữ ký `.asc` không verify.** Kiểm bạn dùng đúng file, đúng public key/fingerprint, signature bị hỏng hay data bị sửa. Nếu vẫn không xác định được, dừng release và xử lý như vấn đề provenance; **không bỏ qua `gpg --verify` chỉ vì checksum tự tính khớp sidecar**.

**Trường hợp F: consumer không resolve được.** Kiểm repository URL/visibility, namespace/GAV, published POM, parent/BOM, credentials/mirror, và các transitive dependencies. Maven local cache có thể che thiếu file ở remote nên thử một cache riêng.

Một lỗi hậu kiểm nghiêm trọng cần được ghi cụ thể: artifact coordinate, file name, expected/actual checksum, repository endpoint, job ID, thời điểm và người chịu trách nhiệm xử lý.

## 33. Checklist release gate sau xuất bản

- [ ] Có một bản release plan: GAV, packaging, target repository và expected attached classifiers.
- [ ] Publication service đã xác nhận trạng thái **published/released**, không chỉ “uploaded/staged”.
- [ ] POM và binary đã có thể tải từ URL mà consumer được phép dùng.
- [ ] Tên và folder của các tệp đúng Maven repository layout theo GAV.
- [ ] Published POM có GAV, license, developer, SCM, description/url chính xác.
- [ ] Published POM có đúng direct compile/runtime/test dependencies, scopes/optional/exclusions.
- [ ] Parent POM và imported BOM (nếu có) có thể resolve từ consumer environment.
- [ ] Maven 3 CI-friendly placeholders được xử lý trong published POM theo release config.
- [ ] Main JAR chứa đúng Java packages/classes, manifest hợp lý.
- [ ] Sources JAR chứa source khớp binary và release revision.
- [ ] Javadoc JAR chứa documentation cho public API.
- [ ] Checksum sidecars có/không đúng theo **policy repository cụ thể**.
- [ ] SHA-256/SHA-512 hoặc digest tin cậy của từng file được so với expected checksum.
- [ ] Chữ ký `.asc` của những files phải ký verify và signer fingerprint đáng tin.
- [ ] Không nhầm checksum match với xác minh danh tính tác giả.
- [ ] Không có file đính kèm ngoài release plan gây tốn dung lượng hoặc rò rỉ dữ liệu.
- [ ] Nếu có SBOM/attestation, schema/nội dung/chữ ký đúng release artifact set.
- [ ] Consumer ngoài source reactor tải được từ repository đích, không dựa local install cache.
- [ ] Consumer compile/test/runtime smoke pass trên JDK được hỗ trợ.
- [ ] Ghi release evidence: Git SHA, CI run ID, GAV, file hashes, signatures, repository URL, approval.
- [ ] Release repository bảo đảm immutability; lỗi post-publish được xử lý bằng version mới theo policy.
- [ ] Không để credentials/private keys hoặc source secrets trong POM/Sources/Javadoc/release bundle.

## 34. Bảng chẩn đoán nhanh

| Triệu chứng | Nguyên nhân khả dĩ | Hành động đúng |
| --- | --- | --- |
| Maven báo `BUILD SUCCESS` nhưng Central không có GAV. | Upload/staging chưa release hoặc sai repository endpoint. | Xác minh status từ Portal/repository; không suy từ build log. |
| Có JAR, không có `.pom`. | Publish bằng thao tác copy JAR thay Maven artifact set. | Publish POM descriptor đúng GAV. |
| POM có, consumer báo missing parent. | Parent POM private/missing/wrong version. | Publish/fix parent reference; thử consumer sạch. |
| Consumer báo missing BOM. | Imported BOM chưa có trong accessible repository. | Kiểm BOM GAV và repository visibility. |
| Có `-sources.jar` nhưng chỉ chứa main class bytecode. | Attach nhầm JAR hoặc rename file. | Dùng Source Plugin, kiểm `jar tf`. |
| Javadoc JAR rỗng/sai API. | Javadoc plugin build sai source/inclusion. | Tạo lại docs và xác minh output. |
| SHA-256 khác expected. | Tải nhầm file, corruption, proxy/cache hoặc artifact khác build. | Dừng release, so dữ liệu tin cậy và điều tra. |
| SHA-1 khớp nhưng GPG signature fail. | File/key/signature không hợp lệ hoặc có sự cố trust. | Không lấy SHA-1 làm bằng chứng thay chữ ký. |
| `gpg: Good signature` nhưng fingerprint không được biết. | Khóa chưa xác thực identity. | Đối chiếu fingerprint qua kênh độc lập. |
| Không có `.asc` trong demo `file://`. | Chưa cấu hình signing. | Đúng với demo; production Central cần signing. |
| Chữ ký của main JAR pass, POM bị sửa. | POM không cùng trust level được verify. | Kiểm hash/signature của POM riêng. |
| Maven tree có JUnit như runtime transitive. | Test scope bị khai báo sai. | Kiểm published dependency scopes. |
| Consumer chỉ pass trên laptop tác giả. | Local install cache che thiếu remote artifact. | Chạy fresh consumer local repo. |
| `.pom` khác source POM byte-for-byte. | Có thể do flatten/transform publication. | So semantic metadata và graph, không ép byte equality mù quáng. |
| `maven-metadata.xml` báo snapshot timestamp khác. | Snapshot được deploy lại hoặc cache policy. | Kiểm snapshotVersions, resolved files, checksums. |
| Có file `-shaded.jar` và dependencies bị trùng class. | Shade/POM publication chưa đồng bộ. | Kiểm classifier và dependency-reduced POM. |
| Release POM sai sau khi đã immutable. | Defect metadata của bản đã phát hành. | Phát hành version mới và thông báo; không lặng lẽ overwrite. |
| SHA-256 không khớp sidecar nhưng file `.jar` vẫn mở được. | Tính toàn vẹn không được xác nhận. | Dừng, không dùng khả năng mở JAR làm tiêu chí pass. |

**Trình tự debug:** tọa độ/URL → inventory → POM/parent/BOM → checksum → signature → source/Javadoc archive content → consumer test → release provenance và immutability.

## 35. Câu hỏi tự kiểm tra

1. **`mvn deploy` thành công có chứng minh release đã được Central Portal public chưa?** Không; cần xác nhận publication workflow/status.
2. **Maven metadata và POM có giống nhau không?** Không; POM là artifact descriptor, metadata.xml hỗ trợ version/snapshot resolution.
3. **Vì sao phải verify POM checksum/signature, không chỉ JAR?** POM quyết định transitive dependency graph và có thể bị thay để làm consumer tải mã khác.
4. **Bản `-sources.jar` và `-javadoc.jar` có phải Java runtime dependencies?** Không; chúng là attached classifier artifacts.
5. **Có bắt buộc mọi packaging `pom` đều có main JAR không?** Không; parent POM/BOM dùng POM làm artifact chính.
6. **SHA-256 tự tính trên file có chứng minh file do tác giả chính thức tạo không?** Không; cần expected digest tin cậy hoặc signature/provenance.
7. **“Good signature” đã đủ xác thực tác giả chưa?** Chưa; phải xác minh fingerprint và trust của public key.
8. **MD5/SHA-1 sidecars có thay SHA-256/SHA-512 khi cần chống tấn công chủ động không?** Không; đó là compatibility/legacy requirements.
9. **Maven Central hiện yêu cầu nguồn/Javadoc/PGP signatures cho Java library như thế nào?** Theo tài liệu Sonatype Central, phải cung cấp sources/Javadoc artifacts và detached `.asc` signatures cùng các tệp bắt buộc; cần kiểm policy ở thời điểm release.
10. **Khi repo cung cấp `.sha256` chỉ chứa hash, có luôn dùng trực tiếp `sha256sum -c file.sha256` được không?** Không; định dạng của lệnh cần filename/hash đúng chuẩn.
11. **Vì sao cần consumer tách khỏi reactor với local cache mới?** Để không dùng parent/JAR cache tình cờ từ máy tác giả và kiểm đúng published artifacts.
12. **Nếu một child POM cần private parent mà consumer không truy cập được, JAR vẫn đúng hash có đủ?** Không; Maven có thể không resolve effective model.
13. **Có nên lặng lẽ overwrite một release POM đã sai trên immutable repository?** Không; cần version mới và quy trình khắc phục.
14. **`gpg:sign` trong demo local có được chạy không?** Không; demo thiếu key/signing plugin, phần signing là ví dụ release pipeline riêng.
15. **Maven Release Plugin prepare/tag có thay việc xác minh file trên repo sau deploy không?** Không; source tag và repository artifacts có thể lệch nếu pipeline sai.
16. **Một `javadoc.jar` chứa file bất kỳ có chứng minh API documentation đầy đủ không?** Không; phải xem entry và mở docs đối chiếu source/public API.
17. **Vì sao checksum phải được ghi theo từng file?** Main, POM, sources và Javadoc là bytes khác nhau; mỗi artifact cần đối chiếu độc lập.
18. **Vì sao `-DaltDeploymentRepository=audit::file:///tmp/...` an toàn hơn để học?** Vì chỉ ghi một repository-format folder cục bộ, không dùng server production, nhưng vẫn cho phép kiểm layout và consumer resolution.
19. **Có nên giữ token/repository password trong POM để chạy deploy nhanh?** Không; dùng settings/CI secret store và chính sách quyền.
20. **Sau publication nên lưu những bằng chứng gì?** GAV, file manifest/hashes, chữ ký/fingerprint, Git SHA, CI run, repository URL/status và consumer test results.

## 36. Tài liệu chính thức và đọc thêm

- [Apache Maven — Guide to Uploading Artifacts to the Central Repository](https://maven.apache.org/repository/guide-central-repository-upload): artifact, POM, signatures, sources/Javadoc và publication.
- [Apache Maven — POM Reference](https://maven.apache.org/pom.html): GAV, packaging, metadata, dependencies, parent và distributionManagement.
- [Apache Maven — Maven Repository Layout](https://maven.apache.org/repositories/layout.html): tọa độ artifact thành đường dẫn file.
- [Apache Maven — Maven Metadata](https://maven.apache.org/repositories/metadata.html): thông tin version/artifact/snapshot metadata.
- [Apache Maven — Maven Deploy Plugin Usage](https://maven.apache.org/plugins/maven-deploy-plugin/usage.html): deploy lifecycle, `altDeploymentRepository` và `deploy-file`.
- [Apache Maven — Deploy Plugin 3.1.4](https://maven.apache.org/plugins-archives/maven-deploy-plugin-3.1.4/deploy-mojo.html): tham số/phase của phiên bản demo.
- [Apache Maven — Source Plugin: jar-no-fork](https://maven.apache.org/plugins-archives/maven-source-plugin-3.3.1/jar-no-fork-mojo.html): tạo attached sources JAR.
- [Apache Maven — Javadoc Plugin](https://maven.apache.org/plugins/maven-javadoc-plugin/): tạo Javadoc JAR và tài liệu API.
- [Apache Maven — GPG Plugin](https://maven.apache.org/plugins/maven-gpg-plugin/): ký POM và attached artifacts.
- [Apache Maven — Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html): transitive graph và scope semantics.
- [Apache Maven — CI Friendly Versions](https://maven.apache.org/guides/mini/guide-maven-ci-friendly.html): `revision/changelist` và POM publish.
- [Sonatype Central — Publishing Requirements](https://central.sonatype.org/publish/requirements/): POM metadata, sources/Javadoc, checksums và OpenPGP signatures.
- [Sonatype Central — Publishing via Maven Plugin](https://central.sonatype.org/publish/publish-portal-maven/): Central Publisher Portal và việc tạo bundle/checksums.
- [Sonatype Central — Working with PGP Signatures](https://central.sonatype.org/publish/requirements/gpg/): ký/kiểm `.asc` và quản lý public keys.
- [Sonatype Central — Immutability](https://central.sonatype.org/publish/requirements/immutability/): không ghi đè/xóa artifacts đã public và cách xử lý lỗi bằng version mới.
- [Sonatype Central — Reducing Publishing Usage](https://central.sonatype.org/publish/reducing-publishing-usage/): rà soát artifact set và các file đi kèm không cần thiết.

**Kết luận:** Một Maven release chỉ có thể được tin dùng khi **artifact files, published POM và các dependencies đều đúng; checksum đối chiếu được; chữ ký/identity được xác minh nếu policy yêu cầu; và consumer ngoài source tree tải/chạy thành công**. `BUILD SUCCESS` là tín hiệu build, không thay thế QA của repository. Hãy hậu kiểm cả `.pom`, main binary, `-sources.jar`, `-javadoc.jar`, checksum sidecars, `.asc` và release provenance theo từng loại file; đối với release đã immutable, sửa lỗi bằng version mới thay vì âm thầm thay cùng tọa độ.
