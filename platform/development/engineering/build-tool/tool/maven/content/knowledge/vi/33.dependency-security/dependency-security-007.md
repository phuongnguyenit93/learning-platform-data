# Rà soát giấy phép và phạm vi phân phối thư viện kèm ứng dụng

## 1. Vấn đề cần giải quyết

Một dependency Maven có thể giúp `mvn clean verify` báo `BUILD SUCCESS`, nhưng Maven không tự cấp phép cho doanh nghiệp sử dụng hoặc phân phối phần mềm đó. Maven Resolver xác định tọa độ, phiên bản và các đường dẫn dependency; nó **không quyết định** liệu sản phẩm phải đi kèm LICENSE, NOTICE, attribution, source offer hay đã đáp ứng điều khoản thương mại.

Bài này tập trung vào **hai câu hỏi phải giải quyết đồng thời**:

1. **Thành phần bên thứ ba đang chịu license nào, theo bằng chứng nào?** Kiểm tra đúng artifact/version, LICENSE/COPYING, NOTICE, license headers, thông tin upstream, POM metadata và các exceptions.
2. **Thành phần có thực sự được giao kèm ứng dụng không và theo hình thức nào?** Chỉ dùng trong build/test, copy cạnh thin JAR, nhúng vào fat JAR, đưa vào WAR, Docker image, SDK, installer hay chỉ chạy nội bộ trên server.

Trả lời câu thứ hai giúp xác định điều khoản nào cần đánh giá trong trường hợp cụ thể. Tuy nhiên **không** được kết luận “không nằm trong main JAR thì không có nghĩa vụ gì”, vì thành phần có thể nằm trong image, thư mục `lib` hoặc một gói khác.

Sau bài học, bạn có thể:

- Đọc Maven scopes và transitive dependency graph đúng ngữ cảnh.
- Lập inventory theo coordinates, version, digest, license evidence và packaging location.
- Dùng Maven Dependency Plugin, MojoHaus License Maven Plugin và CycloneDX SBOM.
- Phân biệt POM license metadata với điều khoản upstream đã xác minh.
- Hiểu các nhóm license MIT/BSD/Apache-2.0, MPL/LGPL/GPL/AGPL và các trường hợp dual/commercial.
- Tạo lab Java 17 đóng gói thin JAR + thư viện Commons Lang, chứng minh JUnit chỉ nằm trong test dependency graph.
- Tạo checklist LICENSE/NOTICE và cổng kiểm tra trước release.

**Bài là hướng dẫn kỹ thuật và quy trình quản trị, không phải tư vấn pháp lý cho một sản phẩm hoặc khu vực pháp luật cụ thể.** Khi gặp license copyleft, ngoại lệ, license tùy biến hoặc điều khoản thương mại, chuyển hồ sơ cho người có thẩm quyền và áp dụng đúng văn bản license, cách tích hợp và mô hình phân phối thực tế.

## 2. Vì sao phải tách bảo mật và tuân thủ giấy phép?

Dependency governance có nhiều trục:

| Trục | Ví dụ | Công cụ/kiểm tra |
| --- | --- | --- |
| Bảo mật | Lỗ hổng trong một phiên bản JAR | CVE scan, dependency upgrade |
| License | Thiếu attribution/NOTICE hoặc nghĩa vụ source | License text và policy review |
| Supply chain | Artifact giả hoặc không rõ nguồn gốc | Repository policy, digest, provenance |
| Runtime | Exclusion làm thiếu class khi chạy | Integration tests và artifact inspection |

Một thư viện Apache-2.0 vẫn có thể có CVE, và một thư viện chưa có CVE vẫn có license không phù hợp với mô hình phân phối cụ thể. `dependency:tree` cho biết resolved graph, **không phải kết quả rà soát pháp lý**.

## 3. Ba tập hợp: declared, resolved và delivered

Maven project thường có ba danh sách khác nhau:

- **Declared:** dependencies được khai báo ở POM, chưa tính tất cả transitive paths.
- **Resolved:** các artifacts Maven đã chọn theo dependency mediation, scopes, exclusions, optional, active profiles và management.
- **Delivered:** bytes/classes thực nằm trong gói được phát hành.

Ví dụ:

~~~text
pom.xml
├── commons-lang3:3.14.0    compile
├── logging-api:x.y.z       compile
├── logging-provider:x.y.z  runtime
├── servlet-api:x.y.z       provided
└── junit-jupiter:5.11.4    test

dist/
├── application.jar
├── lib/
│   ├── commons-lang3-3.14.0.jar
│   ├── logging-api-x.y.z.jar
│   └── logging-provider-x.y.z.jar
└── legal/
    ├── THIRD-PARTY-NOTICES.md
    └── licenses/
~~~

Đây là sơ đồ khái niệm; `x.y.z` chỉ là tên version tượng trưng, không phải cấu hình runnable. JUnit được dùng để test nhưng thường không nằm trong gói runtime; servlet API có thể do server cung cấp.

Nếu application dùng Shade Plugin, Commons Lang có thể đi vào `application-all.jar` dưới dạng classes, không còn file riêng trong `lib`. **Không được dùng danh sách tên file JAR đơn thuần để bỏ qua thành phần đã nhúng.**

## 4. Tọa độ và bằng chứng cần ghi

Một artifact Maven có thể được xác định theo:

~~~text
groupId : artifactId : version : type : classifier
~~~

Ví dụ:

~~~text
org.apache.commons:commons-lang3:3.14.0:jar
~~~

Một bản ghi kiểm kê nên chứa:

| Trường | Ví dụ |
| --- | --- |
| Coordinates | `org.apache.commons:commons-lang3:3.14.0` |
| Artifact SHA-256 | Digest tính từ binary cụ thể |
| Dependency path | Direct compile; hoặc qua library khác |
| Delivery location | `dist/lib/commons-lang3-3.14.0.jar` |
| License evidence | POM + upstream LICENSE/NOTICE |
| SPDX license | `Apache-2.0` |
| Modified | Có/không, thay đổi nào |
| Distribution | On-prem thin JAR |
| Required notices | Bản license và NOTICE nếu điều khoản yêu cầu |
| Status | Approved / Review required / Blocked |
| Owner | OSS/legal reviewer, ngày review |

Ghi đúng version để phân biệt những release khác nhau của cùng artifact. Gắn decision với **đúng binary/digest và kiểu phân phối**, không chỉ tên groupId.

## 5. POM license metadata có thể sai hoặc thiếu

Một POM có thể có:

~~~xml
<licenses>
    <license>
        <name>Apache License, Version 2.0</name>
        <url>https://www.apache.org/licenses/LICENSE-2.0</url>
        <distribution>repo</distribution>
    </license>
</licenses>
~~~

Đây là một fragment minh họa. Nó chứa metadata hữu ích nhưng **không phải một chứng chỉ pháp lý**. Có trường hợp POM thiếu `<licenses>`, URL không còn hoạt động, license name không chuẩn, hoặc source files/binary đi kèm thành phần có giấy phép khác.

Nguồn cần đối chiếu:

1. LICENSE/COPYING/NOTICE trong đúng source hoặc binary release.
2. Copyright/permission headers trong source files.
3. Official upstream website/release tag.
4. Maven POM metadata.
5. SPDX/SBOM/third-party license databases như bằng chứng hỗ trợ.

**Thiếu license metadata không phải bằng chứng public domain.** Nếu nguồn mâu thuẫn, ghi `REVIEW_REQUIRED` và escalate thay vì chọn tên license dễ chấp thuận nhất.

## 6. Phân biệt LICENSE và NOTICE

- **LICENSE** ghi điều khoản quyền sử dụng/sao chép/sửa đổi/phân phối.
- **NOTICE** có thể chứa attribution, copyright, thông báo quyền và nội dung cần giữ khi phân phối theo license hoặc project release.

Với Apache License 2.0, việc phân phối thường kèm yêu cầu cung cấp bản license, giữ các notices phù hợp, đánh dấu modified files và chuyển tiếp các attribution notices từ NOTICE khi điều khoản áp dụng.

Không phải mọi JAR Apache-2.0 có cùng nội dung NOTICE. Hãy lấy file thực từ đúng version của upstream, **không tự tạo một file NOTICE chung** rồi khẳng định đã hoàn thành.

MIT/BSD cũng thường yêu cầu giữ copyright/license/disclaimer text. Một đường link không mặc nhiên thay việc cung cấp bản văn khi license yêu cầu recipient nhận bản sao.

## 7. Maven scope không phải giấy phép phân phối

| Scope | Tác dụng kỹ thuật thường gặp | Liên quan packaging |
| --- | --- | --- |
| `compile` | Compile và runtime | Có thể copy cạnh thin JAR hoặc nhúng vào fat JAR |
| `runtime` | Runtime/test | Thư viện provider/driver có thể nằm trong gói |
| `provided` | Compile/test, runtime do môi trường cung cấp | Không vào WAR lib mặc định, nhưng nếu giao cả container vẫn phải review |
| `test` | Chỉ cần cho tests | Không vào main JAR thông thường, có thể được giao cùng test harness |
| `system` | Binary từ path cục bộ | Dễ bị bỏ khỏi Maven inventory; không khuyến nghị |
| `import` | BOM POM trong dependencyManagement | Quản lý versions, không phải runtime JAR |

**Scope mô tả Maven classpath, không trao quyền dùng hay miễn nghĩa vụ license.** Có thể một dependency `provided` đi kèm Docker image qua server base layer; một dependency `test` cũng có thể được phân phối nếu gửi source/tests/tooling cho bên khác.

`optional=true` thay đổi tính transitive đối với consumers, không làm license của thành phần ấy biến mất trong project trực tiếp dùng nó.

## 8. Transitive dependencies và exclusions

Ví dụ:

~~~text
my-app
└── api-client:1.0
    └── http-core:2.0
        └── utility-lib:3.0
~~~

Dù POM trực tiếp chỉ khai báo `api-client`, những dependencies còn lại vẫn có thể có mặt trong runtime bundle theo cách đóng gói.

Nếu một exclusion loại `utility-lib` khỏi một dependency path, thư viện vẫn có thể đến từ path khác. Sau khi thay dependencies, phải chạy `dependency:tree`, xem các JAR đã copy, xem fat JAR/WAR/image và chạy integration tests.

Không nên dùng exclusions để **làm sạch báo cáo license trên giấy** khi ứng dụng cần library ở runtime.

## 9. Các hình thức phân phối cần phân biệt

| Sản phẩm/hoạt động | Câu hỏi kỹ thuật |
| --- | --- |
| Chỉ build/test nội bộ | Artifacts/tests có được chuyển giao ra ngoài không? |
| Giao JAR + `lib/*.jar` cho khách hàng | Có những JAR, LICENSE/NOTICE nào trong bundle? |
| Giao fat/shaded JAR | Những classes/resources từ library nào đã được merge? |
| Giao WAR | Thư viện nào ở `WEB-INF/lib`, container nào được cung cấp? |
| Xuất bản SDK/JAR lên Maven repository | Recipient sẽ resolve dependency/POM nào? |
| Giao Docker image | Base image, JRE, OS packages, native libs, Maven components? |
| Chạy SaaS | Thành phần nào được sửa, điều khoản network tương tác có liên quan không? |
| Giao source/tests | Có third-party code, test tools, scripts, assets nào kèm theo? |

Tình huống chỉ vận hành phần mềm nội bộ khác với việc **chuyển giao binary/image cho khách hàng**. Nhưng không thể kết luận tất cả nghĩa vụ đã hết trong mô hình SaaS; AGPL là một ví dụ cần đánh giá riêng.

## 10. MIT, BSD và Apache-2.0

| SPDX ID | Điểm cần kiểm tra |
| --- | --- |
| `MIT` | Copyright và permission notice khi phân phối bản sao/phần đáng kể |
| `BSD-2-Clause` | Điều khoản giữ copyright/disclaimer |
| `BSD-3-Clause` | Thêm non-endorsement condition |
| `Apache-2.0` | Cung cấp license, notices phù hợp, thay đổi source files và các điều kiện khác |
| `ISC` | Copyright/permission/disclaimer theo chính văn bản |

**“Permissive” không có nghĩa bỏ LICENSE/NOTICE hoặc có quyền dùng nhãn hiệu upstream.** Đọc nguyên văn và giữ chính xác những thông báo được yêu cầu.

### Riêng Apache-2.0

Khi phân phối thành phần theo Apache License 2.0:

- Cung cấp bản license theo điều khoản.
- Giữ các copyright, patent, trademark, attribution notices liên quan.
- Nếu sửa files, đánh dấu nổi bật những files đã sửa.
- Nếu upstream có NOTICE, giữ các attribution notices phù hợp ở hình thức readable.
- Không tạo ấn tượng dự án upstream chứng thực sản phẩm khi không có quyền.

Apache-2.0 nhìn chung cho phép dùng trong proprietary app nếu đáp ứng điều kiện; nó không tự yêu cầu phát hành toàn bộ proprietary source chỉ vì thư viện được sử dụng. Nhưng xem thêm điều khoản của mọi component khác trong deliverable.

Official text: https://www.apache.org/licenses/LICENSE-2.0.

## 11. MPL, LGPL, GPL, AGPL và giấy phép thương mại

Những nhóm giấy phép này có yêu cầu khác nhau:

- **MPL-2.0:** copyleft thường ở cấp file; cần xem source files covered, modifications và việc phân phối.
- **LGPL-2.1/LGPL-3.0:** cần xem linking, replacement/relinking, license notices, sửa library và source obligations theo điều khoản.
- **GPL:** cần xem combined work/derivative work, conveying, exceptions và corresponding source.
- **AGPL:** có quy định network interaction liên quan modified AGPL-covered programs; không thể nói SaaS mặc nhiên miễn mọi nghĩa vụ.
- **Commercial/dual-license:** có thể cấp quyền theo hợp đồng thay thế, nhưng cần xác minh điều kiện/thời hạn/khách hàng/kênh phân phối.

Không có quy tắc chính xác kiểu “mọi thư viện LGPL đều bị cấm trong proprietary product” hoặc “dynamic linking luôn tự động an toàn”. Khi gặp license cần phân tích, ghi rõ binary packaging, modifications, linking mode và distribution model rồi đưa người review có thẩm quyền.

## 12. SPDX license IDs và expressions

SPDX IDs thường gặp:

~~~text
Apache-2.0
MIT
BSD-3-Clause
EPL-2.0
MPL-2.0
LGPL-2.1-only
GPL-3.0-or-later
AGPL-3.0-only
~~~

SPDX expressions:

~~~text
MIT OR Apache-2.0
MIT AND Apache-2.0
GPL-2.0-only WITH Classpath-exception-2.0
LicenseRef-Vendor-Custom
NOASSERTION
NONE
~~~

- `OR` thể hiện lựa chọn khi upstream thực sự cấp quyền lựa chọn.
- `AND` biểu thị các điều khoản cùng áp dụng.
- `WITH` gắn license exception.
- `LicenseRef-*` dành cho license không có SPDX ID chuẩn, cần bản văn và evidence.
- `NOASSERTION` biểu thị thiếu thông tin để khẳng định; **không có nghĩa miễn phí hoặc public domain**.
- `NONE` có ý nghĩa cụ thể trong SPDX schema; không suy ngay thành quyền sử dụng.

POM liệt kê hai `<license>` elements **không tự** chứng minh quan hệ `OR` hoặc `AND`. Xác minh từ upstream.

## 13. Maven Dependency Plugin: thấy graph thật

Tại project Maven:

~~~bash
mvn -version
mvn -B -ntp org.apache.maven.plugins:maven-dependency-plugin:3.8.1:tree
~~~

Hiển thị thêm omitted nodes khi goal hỗ trợ:

~~~bash
mvn -B -ntp org.apache.maven.plugins:maven-dependency-plugin:3.8.1:tree -Dverbose
~~~

Chỉ runtime scope:

~~~bash
mvn -B -ntp org.apache.maven.plugins:maven-dependency-plugin:3.8.1:tree -Dscope=runtime
~~~

Ghi report:

~~~bash
mvn -B -ntp org.apache.maven.plugins:maven-dependency-plugin:3.8.1:tree -DoutputFile=target/dependency-tree.txt
~~~

Tree cho thấy module, coordinates và dependency paths. Nó **không phải danh sách classes thực đã được Shade Plugin đưa vào một JAR**, cũng không chứa mọi OS package trong image. Với multi-module, cần xem trees của modules có artifacts được phát hành.

## 14. Copy runtime dependencies theo Maven scope filtering

~~~bash
mvn -B -ntp org.apache.maven.plugins:maven-dependency-plugin:3.8.1:copy-dependencies -DincludeScope=runtime -DoutputDirectory=target/audit-runtime
~~~

Tài liệu chính thức nêu `includeScope=runtime` lấy **runtime và compile dependencies** theo Maven classpath scope filtering. Nó không chỉ lấy dependencies có khai báo literal `<scope>runtime</scope>`.

`copy-dependencies` là phép thử kỹ thuật tốt để quan sát dependency JARs, nhưng **không thể thay** việc inspect final `dist/lib`, shaded JAR, WAR hoặc Docker image.

## 15. MojoHaus License Maven Plugin

Để lấy danh sách third-party licenses:

~~~bash
mvn -B -ntp org.codehaus.mojo:license-maven-plugin:2.7.1:add-third-party
~~~

Báo cáo thường nằm ở:

~~~text
target/generated-sources/license/THIRD-PARTY.txt
~~~

Để tải license texts được metadata nhắc tới:

~~~bash
mvn -B -ntp org.codehaus.mojo:license-maven-plugin:2.7.1:download-licenses
~~~

Plugin có thể xét transitive/test dependencies, theo cấu hình. Report có thể thiếu license hoặc dựa vào URL đã chết; không tự động xác minh mọi license text trong actual JAR.

**Goal báo thành công không phải quyết định legal approval.** Một `missingFile`/metadata override chỉ nên dùng sau khi kiểm tra nguồn gốc và lưu bằng chứng. Không tự sửa license của binary bằng việc đổi nhãn report.

## 16. Multi-module license reporting

MojoHaus hỗ trợ aggregate goal:

~~~bash
mvn -B -ntp org.codehaus.mojo:license-maven-plugin:2.7.1:aggregate-add-third-party
~~~

Nó có cơ chế tổng hợp trên các modules/leaf projects theo plugin rules; cần kiểm tra Maven reactor selection và output của version thực tế.

Các lưu ý:

- `-N` từ root aggregator có thể bỏ qua children.
- Root POM `packaging=pom` không chứa toàn bộ runtime libraries của children.
- Một module test harness và một module phát hành app có footprints khác nhau.
- Có thể cùng artifact trong nhiều modules, nhưng phải biết nó thực sự được giao trong deliverable nào.
- Nếu final product là container, Maven aggregate report vẫn chưa bao gồm toàn bộ base image layers.

Dùng cả per-module inventory và product-level inventory.

## 17. CycloneDX SBOM bổ sung cho rà soát

~~~bash
mvn -B -ntp org.cyclonedx:cyclonedx-maven-plugin:2.9.3:makeBom
~~~

Với multi-module:

~~~bash
mvn -B -ntp org.cyclonedx:cyclonedx-maven-plugin:2.9.3:makeAggregateBom
~~~

Plugin có thể tạo các file như `bom.xml` và `bom.json` trong build directory; tên/định dạng phụ thuộc version và config.

SBOM hữu ích để ghi component/version, dependency relationships, hashes và license metadata (khi có). Nhưng Maven SBOM **không tự** bao phủ JavaScript bundles, fonts, native libs hay OS/JRE packages. Một SBOM với `NOASSERTION` cũng không phải license approval.

## 18. Lab Java 17: kiểm tra runtime JAR thật

Ta tạo một project có hai dependencies với phạm vi khác nhau:

- `org.apache.commons:commons-lang3:3.14.0` — compile; dùng ở runtime, Apache-2.0.
- `org.junit.jupiter:junit-jupiter:5.11.4` — test; chỉ phục vụ unit tests.

Maven Dependency Plugin sẽ copy runtime libraries vào `target/dist/lib`. Maven JAR Plugin sẽ tạo **thin executable JAR** có manifest trỏ tới `lib`.

~~~text
license-review-lab/
├── pom.xml
├── src/
│   ├── main/java/dev/learning/license/App.java
│   └── test/java/dev/learning/license/AppTest.java
└── target/
    ├── license-review-lab-1.0.0.jar
    └── dist/
        └── lib/
            └── commons-lang3-3.14.0.jar
~~~

Đây là cấu trúc dự kiến sau build. Legal files chưa được tự tạo trong lab; cần bổ sung và review trước khi coi gói sẵn sàng cho distribution.

## 19. POM Java 17 hoàn chỉnh

File `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.learning.license</groupId>
    <artifactId>license-review-lab</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <project.build.outputTimestamp>2024-01-01T00:00:00Z</project.build.outputTimestamp>
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
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
                <configuration>
                    <archive>
                        <manifest>
                            <addClasspath>true</addClasspath>
                            <classpathPrefix>lib/</classpathPrefix>
                            <mainClass>dev.learning.license.App</mainClass>
                        </manifest>
                    </archive>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-dependency-plugin</artifactId>
                <version>3.8.1</version>
                <executions>
                    <execution>
                        <id>stage-runtime-dependencies</id>
                        <phase>prepare-package</phase>
                        <goals>
                            <goal>copy-dependencies</goal>
                        </goals>
                        <configuration>
                            <includeScope>runtime</includeScope>
                            <excludeTransitive>false</excludeTransitive>
                            <outputDirectory>${project.build.directory}/dist/lib</outputDirectory>
                        </configuration>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**Giải thích:**

1. Compiler sử dụng Java 17 API/classfile target.
2. `commons-lang3` không khai báo scope nên mặc định `compile`.
3. JUnit Jupiter dùng `test` scope.
4. `copy-dependencies` ở `prepare-package` chọn runtime+compile dependencies và copy vào `target/dist/lib`.
5. `excludeTransitive=false` giữ các runtime transitive dependencies nếu được resolved.
6. JAR Plugin cấu hình `Main-Class` và `Class-Path` tương đối `lib/` trong manifest.
7. Build tạo thin JAR, không nhúng Commons Lang classes vào main artifact.
8. `outputTimestamp` phục vụ reproducible archives, không phải kiểm tra license.
9. Version của các Maven plugins đã được ghim cho lab.

## 20. App.java

File `src/main/java/dev/learning/license/App.java`:

~~~java
package dev.learning.license;

import org.apache.commons.lang3.StringUtils;

public final class App {
    private App() {
    }

    public static String message() {
        return "Hello, " + StringUtils.capitalize("maven")
                + " | runtime libs reviewed";
    }

    public static void main(String[] args) {
        System.out.println(message());
    }
}
~~~

Mã gọi `StringUtils.capitalize` từ Commons Lang 3; runtime cần JAR thư viện trong classpath.

Dòng do Java main in chính xác:

~~~text
Hello, Maven | runtime libs reviewed
~~~

## 21. AppTest.java

File `src/test/java/dev/learning/license/AppTest.java`:

~~~java
package dev.learning.license;

import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

class AppTest {
    @Test
    void formatsMessage() {
        assertEquals(
                "Hello, Maven | runtime libs reviewed",
                App.message());
    }
}
~~~

Surefire phát hiện `AppTest` và chạy JUnit Jupiter. `AppTest.class` nằm ở test output, không phải main JAR. Thư viện JUnit ở scope test không được copy vào `dist/lib` của lab cơ sở.

## 22. Lệnh build và chạy

Đứng tại thư mục project:

~~~bash
mvn -version
java -version
mvn -B -ntp clean verify
~~~

Nếu JDK17+, Maven và dependency repositories hoạt động:

- Source compile thành công.
- Unit test PASS.
- `target/dist/lib/commons-lang3-3.14.0.jar` được copy.
- `target/license-review-lab-1.0.0.jar` được đóng gói.

**Linux/macOS**:

~~~bash
mkdir -p target/dist
cp target/license-review-lab-1.0.0.jar target/dist/
java -jar target/dist/license-review-lab-1.0.0.jar
~~~

**Windows PowerShell**:

~~~powershell
New-Item -ItemType Directory -Force -Path "target\dist"
Copy-Item "target\license-review-lab-1.0.0.jar" "target\dist\"
java -jar "target\dist\license-review-lab-1.0.0.jar"
~~~

Stdout:

~~~text
Hello, Maven | runtime libs reviewed
~~~

Main JAR phải nằm cạnh thư mục `lib/`, vì manifest Class-Path được resolve theo vị trí JAR. Nếu chỉ chép main JAR sang một máy khác, ứng dụng sẽ thiếu Commons Lang khi gọi `App.message()`.

## 23. Kiểm tra đúng files được phân phối

Sau khi copy main JAR:

~~~text
target/dist/
├── license-review-lab-1.0.0.jar
└── lib/
    └── commons-lang3-3.14.0.jar
~~~

Kiểm tra trên Unix-like:

~~~bash
find target/dist -type f
jar tf target/dist/license-review-lab-1.0.0.jar
jar tf target/dist/lib/commons-lang3-3.14.0.jar
~~~

Windows PowerShell:

~~~powershell
Get-ChildItem -Recurse -File "target\dist"
jar tf "target\dist\license-review-lab-1.0.0.jar"
jar tf "target\dist\lib\commons-lang3-3.14.0.jar"
~~~

Cần xác nhận:

- Main JAR có `dev/learning/license/App.class`.
- Commons Lang JAR có `org/apache/commons/lang3/StringUtils.class`.
- Không có JUnit JAR trong `dist/lib` theo POM baseline.
- Main JAR không shade classes Commons Lang vào binary.
- Manifest có entry point và relative classpath đúng.

**Các JARs trong `~/.m2/repository` nhưng không nằm trong deliverable chưa chắc được chuyển giao cho khách hàng.** Hãy phân biệt artifact đã resolve và artifact đã copy/giao.

## 24. Đối chiếu legal report với gói lab

Chạy:

~~~bash
mvn -B -ntp org.codehaus.mojo:license-maven-plugin:2.7.1:add-third-party
mvn -B -ntp org.apache.maven.plugins:maven-dependency-plugin:3.8.1:tree
~~~

Báo cáo third-party thường ở:

~~~text
target/generated-sources/license/THIRD-PARTY.txt
~~~

Bảng phân loại:

| Thành phần | Scope | Có trong dist/lib? | Review |
| --- | --- | --- | --- |
| `commons-lang3:3.14.0` | compile | Có | Apache-2.0; lấy LICENSE/NOTICE đúng upstream version |
| `junit-jupiter:5.11.4` | test | Không | Phân loại build/test-only; xét lại nếu phát hành tests |
| `license-review-lab:1.0.0` | own | Main JAR | Xác định license của mã do bạn sở hữu |

Số mục trong THIRD-PARTY report có thể lớn hơn số file `dist/lib`, do plugin có thể xem test/transitive graph. **Không coi report đó là danh sách đóng gói thực tế nếu chưa so files.**

## 25. Tìm LICENSE/NOTICE bên trong JAR

Linux/macOS:

~~~bash
jar tf target/dist/lib/commons-lang3-3.14.0.jar | grep -Ei '(^|/)(LICENSE|NOTICE)([._-]|$)'
~~~

Windows PowerShell:

~~~powershell
jar tf "target\dist\lib\commons-lang3-3.14.0.jar" | Select-String -Pattern '(^|/)(LICENSE|NOTICE)([._-]|$)'
~~~

Tên entry có thể nằm ở `META-INF/` hoặc nơi khác tùy upstream. Chỉ sau khi xác nhận hai entries dưới đây **có thật**, mới dùng ví dụ trích xuất:

~~~bash
jar --extract --file path/to/commons-lang3-3.14.0.jar META-INF/LICENSE.txt META-INF/NOTICE.txt
~~~

Lệnh này có **đường dẫn minh họa** và cần chạy trong một working directory riêng để không ghi đè files đang có. Nếu release dùng entry names khác, thay theo listing thực hoặc lấy source distribution chính thức.

Một gói đã thêm legal docs có thể tổ chức:

~~~text
dist/
├── license-review-lab-1.0.0.jar
├── lib/commons-lang3-3.14.0.jar
└── legal/
    ├── THIRD-PARTY-NOTICES.md
    └── commons-lang3-3.14.0/
        ├── LICENSE.txt
        └── NOTICE.txt
~~~

File LICENSE/NOTICE phải chứa **nguyên văn đúng release** và được reviewer xác minh. Tạo file trống hoặc chỉ ghi link là chưa đủ để khẳng định hoàn tất nghĩa vụ.

## 26. Mẫu THIRD-PARTY-NOTICES.md

~~~markdown
# Third-party components: license-review-lab 1.0.0

## Runtime components

| Name | Version | License | Delivered path |
| --- | --- | --- | --- |
| Apache Commons Lang | 3.14.0 | Apache-2.0 | lib/commons-lang3-3.14.0.jar |

Upstream: https://commons.apache.org/proper/commons-lang/
License copy: legal/commons-lang3-3.14.0/LICENSE.txt
Attributions: legal/commons-lang3-3.14.0/NOTICE.txt

## Test-only dependencies

JUnit Jupiter 5.11.4 is used in tests but not included
in the thin-JAR runtime package illustrated here.

## Evidence

- Maven dependency tree and SBOM for release 1.0.0
- Actual runtime file inventory of dist/
- Human review recorded in release approval system
~~~

Đây là **mẫu hồ sơ**, không phải bản đã được phê duyệt. Tất cả paths được tham chiếu phải thực sự tồn tại trong deliverable; terms và notices phải được xác minh.

## 27. Test scope và provided scope không miễn license review

Trong lab:

~~~xml
<dependency>
    <groupId>org.junit.jupiter</groupId>
    <artifactId>junit-jupiter</artifactId>
    <version>5.11.4</version>
    <scope>test</scope>
</dependency>
~~~

JUnit phục vụ build/test và không có trong `dist/lib`. Tuy nhiên nếu doanh nghiệp phân phối test harness hoặc SDK source với test dependencies, inventory cần được mở rộng.

Tương tự, trong WAR project:

~~~xml
<dependency>
    <groupId>jakarta.servlet</groupId>
    <artifactId>jakarta.servlet-api</artifactId>
    <version>6.0.0</version>
    <scope>provided</scope>
</dependency>
~~~

Servlet API thường do container cung cấp, không vào WAR `WEB-INF/lib` mặc định. Nhưng nếu sản phẩm giao **cả container image hoặc application server**, các thành phần runtime ấy vẫn nằm trong phạm vi rà soát tổng thể.

## 28. Fat/shaded JAR cần kiểm tra class contents

Một fat JAR có thể chứa:

~~~text
my-app-all.jar
├── dev/example/app/App.class
├── org/apache/commons/lang3/StringUtils.class
└── META-INF/...
~~~

Không thấy `lib/commons-lang3.jar` không có nghĩa Commons Lang không được phân phối. Khi Shade Plugin merge classes/resources, một số LICENSE/NOTICE files có thể bị loại hoặc ghi đè.

Cần:

- Biết input artifacts chính xác.
- Kiểm tra packaged classes/resources và relocations.
- Giữ bản license/notice của các thành phần đã bundled.
- Tạo accurate SBOM, attribution bundle và release manifest.
- Xác nhận scanner thấy thành phần dù filename JAR ban đầu không còn.

Không dùng thay đổi Maven scope để “giấu” mã đã được đưa vào binary.

## 29. Docker image và thành phần ngoài Maven

Docker/OCI image có thể chứa:

~~~text
Base OS packages
JDK/JRE distribution
Application JAR
Runtime Maven dependency JARs
Native tools/libraries
Frontend assets/fonts
~~~

Một Maven SBOM không tự liệt kê hết các thành phần của base image. Cần kết hợp Maven inventory và image filesystem/layer scan.

~~~text
Maven tree + Maven SBOM
            |
            v
Build JAR/WAR, then OCI image
            |
            v
Inspect image layers and create image SBOM
            |
            v
Reconcile components/licenses/notices
            |
            v
OSS/legal review gate
            |
            v
Publish reviewed artifact
~~~

Việc chạy image nội bộ và chuyển giao image cho đối tác có thể có nghĩa vụ khác nhau; phải ghi rõ distribution channel và recipient.

## 30. SaaS và AGPL: phân tích tình huống thật

Có trường hợp phần mềm chỉ chạy trên server công ty, không giao binary. Điều này có thể ảnh hưởng cách áp dụng một số license. Tuy nhiên AGPLv3 có điều khoản liên quan network interaction với modified covered program.

Vì vậy:

- Không suy “chỉ SaaS nên copyleft không liên quan”.
- Không suy “một dependency AGPL thì mọi source của service chắc chắn phải công bố”.
- Kiểm tra exact program, license version, modifications, combining/linking và user interaction.
- Ghi evidence và chuyển người review pháp lý trước khi đưa ra quyết định.

Maven coordinates không thể thay thế legal analysis.

## 31. Quy trình khi license thiếu, custom hoặc mâu thuẫn

1. Đánh dấu `REVIEW_REQUIRED`.
2. Ghi coordinates, digest, dependency path, release và kiểu phân phối.
3. Tìm LICENSE/COPYING/NOTICE/source headers của đúng version.
4. Kiểm tra POM và upstream release notes.
5. Nếu có dual license, xác minh `OR`/`AND` và exceptions.
6. Nếu là commercial license, kiểm tra hợp đồng ở hệ thống bảo mật.
7. Nếu thiếu chứng cứ, liên hệ upstream/legal owner.
8. Nếu không được duyệt, chặn release hoặc thay dependency.
9. Lưu quyết định có owner, lý do và ngày xem lại.
10. Khi update version/packaging/kênh phân phối, review lại.

**Không sửa POM metadata trong local cache để ngụy tạo kết quả.** Override report chỉ có ý nghĩa sau khi có evidence đáng tin.

## 32. CI release gate mẫu

~~~text
Checkout pinned source
        |
        v
Maven clean verify
        |
        v
Generate tree + license report + SBOM
        |
        v
Package final thin/fat/WAR/image
        |
        v
Inspect delivered files and embedded code
        |
        v
Reconcile components and legal files
        |
    +---+---+
    |       |
    v       v
 APPROVED  REVIEW/BLOCK
    |       |
    v       v
 Publish  Stop / remediation
~~~

Checks tự động có thể phát hiện:

- Unknown license hoặc version chưa được review.
- Runtime file không có trong inventory.
- Required LICENSE/NOTICE bị thiếu.
- JAR trong final bundle khác GAV/digest đã review.
- Image contains components ngoài Maven SBOM.
- Exceptions hết hạn.
- Dependency upgrade chưa regenerate reports.

**Một SPDX label không đủ để tự quyết định mọi legal compatibility.** Một policy tốt phân biệt approved theo context với review-required và blocked.

## 33. Allowlists, denylists, exceptions

| Status | Ý nghĩa |
| --- | --- |
| Approved | License evidence và use case đã được duyệt |
| Review required | Unknown/new license, package mode mới hoặc thiếu docs |
| Blocked | Tình huống vi phạm policy/kết luận pháp lý |
| Exception approved | Có owner, scope, reason, expiry và supporting evidence |

Một organization có thể có policy khác nhau cho source-only distribution, on-prem binary và SaaS. Không gắn một nhãn “an toàn tuyệt đối” cho một license khi chưa xét context.

## 34. Phụ thuộc không nằm trong Maven graph

Các thành phần có thể bị bỏ sót:

- JAR được copy thủ công.
- SDK vendor nằm trong `src/main/resources`.
- Native DLL/so/dylib.
- Frontend JS/CSS, fonts, icons và media.
- Base OS/JRE packages trong container.
- Generated code/templates của bên thứ ba.
- Runtime file tải từ CDN.
- Test tooling/source được gửi cho khách hàng.
- Application server được bundle.

Đây là lý do Maven-only inventory phải được bổ sung bằng **final artifact inspection**.

## 35. Nâng version library phải rà soát lại

Khi đổi `commons-lang3:3.14.0` sang một release mới:

1. Xem upstream LICENSE/NOTICE/source release.
2. So POM metadata và transitive dependencies.
3. Build final artifact, inspect files/classes.
4. Regenerate SBOM/license report.
5. Xem obligations có đổi không.
6. Chạy unit/integration tests và security scan.
7. Cập nhật legal bundle và record review.
8. Chỉ publish khi approval đúng version và binary.

Không mặc định một approval của 3.14.0 bao phủ tất cả các version tương lai.

## 36. Troubleshooting

| Triệu chứng | Nguyên nhân có thể | Cách khắc phục |
| --- | --- | --- |
| POM không khai license | Metadata thiếu | Tìm primary upstream LICENSE/NOTICE |
| Report liệt kê JUnit nhưng dist không có | Test scope được scan | Phân loại test-only |
| Dist có JAR không có trong report | Copy thủ công, vendor binary | Inspect final files và thêm vào inventory |
| Fat JAR không có thư mục lib | Shading | Kiểm tra bundled classes |
| Docker image có thêm packages | OS/JRE/base layers | Image SBOM |
| License plugin chạy PASS nhưng gói thiếu LICENSE | Report không phải packaging proof | Bổ sung legal files đúng release |
| POM nói MIT, source nói Apache | Metadata conflicting | Review upstream evidence |
| `NOASSERTION` bị hiểu là approved | Dữ liệu chưa xác định | Block/review |
| Exclusion gây NoClassDefFoundError | Library cần ở runtime | Sửa graph và test |
| Wrong NOTICE version | Copy nhầm file | Đối chiếu coordinates/digest |
| License URL bị lỗi | Upstream metadata cũ | Tải từ trusted source release |
| Provided scope trong Docker image | Container vẫn có component | Review entire image |
| AGPL component trong SaaS | Network terms cần kiểm tra | OSS/legal review |
| License report chỉ root POM | Bỏ qua children | Per-module/aggregate inventory |
| CI chỉ scan dependencies, không scan product | Thiếu final bundle reconciliation | Thêm packaging inspection |

## 37. Checklist phát hành

- [ ] Đã xác định sản phẩm, version và kênh phân phối.
- [ ] Có dependency tree cho đúng module/profiles.
- [ ] Có direct và transitive inventory.
- [ ] Phân loại scope compile/runtime/test/provided/optional.
- [ ] Đã inspect thin/fat JAR/WAR/image thực.
- [ ] Đã tính đến binary copy thủ công, native assets và OS/JRE.
- [ ] Có SBOM và license report cùng release.
- [ ] POM license metadata được đối chiếu primary source.
- [ ] Unknown/custom/multiple licenses đã review.
- [ ] SPDX IDs/expressions phản ánh đúng upstream grant.
- [ ] LICENSE/NOTICE được cung cấp đúng điều khoản.
- [ ] Nếu đã sửa covered files, đã xét yêu cầu thông báo/source.
- [ ] Copyleft/commercial licensing được chuyển người có thẩm quyền.
- [ ] Các files ghi trong THIRD-PARTY-NOTICES thực sự tồn tại.
- [ ] Artifact digests liên kết với hồ sơ.
- [ ] Test scope không bị nhầm với distributed code.
- [ ] Security scanning tách khỏi legal compliance.
- [ ] Có owner, review date, reason và exception expiry.
- [ ] CI chặn khi thiếu approval.
- [ ] Rebuild/repackage sau khi thay exclusions/dependencies.
- [ ] Legal notices được version cùng release.
- [ ] Không đưa secrets/hợp đồng nhạy cảm vào public artifacts.

## 38. Bài tập và đáp án

1. **Maven BUILD SUCCESS là license approval?** Không.
2. **Scope compile chắc chắn được phân phối?** Không, phải xem final package.
3. **includeScope=runtime lấy gì?** Compile và runtime dependencies.
4. **JUnit test JAR có mặt trong dist của lab?** Không.
5. **POM thiếu licenses có nghĩa public domain?** Không.
6. **Maven goal xem resolved graph?** `dependency:tree`.
7. **Tool tạo THIRD-PARTY.txt?** `license:add-third-party`.
8. **Tool tạo Maven SBOM?** CycloneDX Maven Plugin.
9. **SBOM tự xác minh legal compliance?** Không.
10. **Vì sao cần transitive inventory?** Dependencies có thể đến từ thư viện khác.
11. **Apache-2.0 có thể bỏ license text?** Không mặc nhiên; phải tuân theo điều khoản.
12. **MIT yêu cầu gì thường gặp?** Giữ copyright và permission notice khi phân phối.
13. **BSD-3-Clause khác BSD-2-Clause?** Có non-endorsement condition.
14. **NOTICE dùng để làm gì?** Ghi các thông báo/attribution liên quan.
15. **GPL và LGPL giống nhau hoàn toàn?** Không.
16. **SaaS luôn miễn AGPL?** Không.
17. **MIT OR Apache-2.0 giống AND?** Không.
18. **NOASSERTION nghĩa là free-to-use?** Không.
19. **Fat JAR có embedded class vẫn là phân phối component đó?** Có.
20. **Provided scope loại component khỏi mọi image?** Không.
21. **Vì sao lab cần target/dist/lib?** Chứa Commons Lang cho runtime thin JAR.
22. **Output Java main lab?** `Hello, Maven | runtime libs reviewed`.
23. **File runtime bên thứ ba của lab?** `commons-lang3-3.14.0.jar`.
24. **Nếu copy main JAR không có lib?** Có thể `NoClassDefFoundError`.
25. **Có nên tự sửa cached POM license metadata?** Không.
26. **Khi tăng version dependency cần làm gì?** Regenerate/review inventory, NOTICE, SBOM.
27. **Cần scan gì thêm ở Docker image?** OS/JRE/native/base layers.
28. **Có thể approve chỉ theo SPDX ID không?** Không; xét use case và evidence.
29. **Ai duyệt exception?** Người có thẩm quyền trong OSS/legal policy.
30. **Nguyên tắc quan trọng nhất?** Xác minh license evidence và thành phần thực sự được phân phối.

## 39. Tài liệu tham khảo chính thức

- [Maven Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html): scopes, optional, transitivity.
- [Maven POM Reference](https://maven.apache.org/pom.html): licenses, dependencies và model.
- [Maven Dependency Plugin — tree](https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html).
- [Maven Dependency Plugin — copy-dependencies](https://maven.apache.org/plugins/maven-dependency-plugin/copy-dependencies-mojo.html): includeScope semantics.
- [Maven JAR Plugin](https://maven.apache.org/plugins/maven-jar-plugin/).
- [Maven Archiver Classpath](https://maven.apache.org/shared/maven-archiver/examples/classpath.html).
- [MojoHaus License Maven Plugin](https://www.mojohaus.org/license-maven-plugin/).
- [MojoHaus License add-third-party](https://www.mojohaus.org/license-maven-plugin/add-third-party-mojo.html).
- [MojoHaus License download-licenses](https://www.mojohaus.org/license-maven-plugin/download-licenses-mojo.html).
- [MojoHaus License aggregate-add-third-party](https://www.mojohaus.org/license-maven-plugin/aggregate-add-third-party-mojo.html).
- [CycloneDX Maven Plugin](https://cyclonedx.github.io/cyclonedx-maven-plugin/).
- [SPDX License List](https://spdx.org/licenses/).
- [SPDX License Expressions](https://spdx.github.io/spdx-spec/v2.2.2/SPDX-license-expressions/).
- [Apache License 2.0](https://www.apache.org/licenses/LICENSE-2.0).
- [Commons Lang 3.14.0 Maven Central](https://central.sonatype.com/artifact/org.apache.commons/commons-lang3/3.14.0).
- [GNU GPL FAQ](https://www.gnu.org/licenses/gpl-faq.html).
- [GNU AGPLv3](https://www.gnu.org/licenses/agpl-3.0.html).

**Kết luận:** Maven giúp xác định dependency graph và tạo binary; license compliance đòi hỏi xác minh điều khoản của đúng component version **và** đối chiếu thành phần thực tế trong sản phẩm được giao. Kết hợp Maven dependency tree, license report, SBOM, final package inspection và một review có trách nhiệm trước khi phát hành.
