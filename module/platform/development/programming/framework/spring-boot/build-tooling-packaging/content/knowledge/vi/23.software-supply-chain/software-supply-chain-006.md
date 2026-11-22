# Kiểm tra giấy phép và thành phần được phép phân phối trong ứng dụng Spring Boot

## 1. Mục tiêu: biết chính xác những gì đang được phát hành

Một ứng dụng Spring Boot có thể build thành công và chạy đúng, nhưng chưa chắc đã đủ điều kiện phát hành. File executable JAR thường chứa nhiều thư viện trực tiếp và gián tiếp; container image còn chứa JRE, hệ điều hành và các gói nền. Dự án cũng có thể phân phối font, icon, ảnh, JavaScript, native libraries, scripts, tài liệu và mã nguồn được copy từ nơi khác. Mỗi thành phần có thể mang điều khoản cấp phép và nghĩa vụ phân phối riêng.

**Kiểm tra giấy phép** (*license review*) phải trả lời được:

- Thành phần nào thực sự xuất hiện trong bản phát hành?
- Ai là chủ sở hữu hoặc bên cấp phép? Phiên bản và nguồn lấy ở đâu?
- Điều khoản nào áp dụng cho chính component/file đó?
- Dự án được quyền sử dụng, sửa đổi, đóng gói, cung cấp lại hoặc phân phối component theo kênh dự định hay không?
- Có cần giữ copyright/license text, NOTICE, ghi attribution, cung cấp source code hoặc đáp ứng điều kiện khác không?
- Có component chưa rõ giấy phép, không có bằng chứng, bị policy cấm hoặc có hợp đồng thương mại cần kiểm tra không?

Bài thuộc mục **Chuỗi cung ứng** của chủ đề **Spring Boot Build Tooling Packaging**. Sau bài này, bạn có thể:

1. Lập inventory cho mã nguồn, dependency Maven trực tiếp/gián tiếp và những file thực sự được đóng gói.
2. Phân biệt license metadata trong POM với license text và điều khoản pháp lý thực tế.
3. Dùng SPDX identifiers/expressions để biểu diễn một license, lựa chọn giữa nhiều license và ngoại lệ.
4. Cấu hình License Maven Plugin để tạo `THIRD-PARTY.txt`, phát hiện metadata còn thiếu và áp dụng policy allowlist/denylist.
5. Tạo CycloneDX SBOM từ Maven dependency graph và hiểu phạm vi mà SBOM chưa bao quát.
6. Dùng Maven Enforcer để chặn các artifact coordinates bị cấm theo policy.
7. Tạo executable JAR Java 17/Spring Boot có project LICENSE và third-party notice, rồi kiểm tra các file trong archive bằng một chương trình Java độc lập.
8. Mở rộng kiểm kê sang Docker base image, OS packages, fonts, icons, native libraries và frontend assets.
9. Tổ chức CI gates, evidence, phê duyệt và phát hành đúng artifact đã được review.

**Ví dụ minh họa:** Java `17`, Spring Boot `3.5.16`, Maven, `license-maven-plugin 2.7.1` và `cyclonedx-maven-plugin 2.9.3`. Dự án demo giả định tự chọn Apache License 2.0 để minh họa metadata. Không suy ra đây là giấy phép của bất kỳ dự án thực tế nào; khi áp dụng phải thay bằng quyết định và hồ sơ quyền thực sự của dự án.

## 2. “Được phép phân phối” phụ thuộc component và kênh phát hành

Một component có thể được phép dùng trong môi trường nội bộ nhưng có điều kiện khác khi đưa vào binary công khai, container image, SDK, source bundle, sản phẩm OEM hoặc dịch vụ hosted. Đừng dùng một cột `license` để trả lời thay cho mọi tình huống.

| Kênh phát hành | Thành phần cần kiểm tra |
| --- | --- |
| Executable JAR | Application classes/resources, mọi nested dependency JAR, license/NOTICE files, native resources |
| WAR | Application classes, `WEB-INF/lib`, `WEB-INF/lib-provided`, JSP/taglibs, servlet/container dependencies theo cách deploy |
| Source archive | Source code, copied snippets, generated sources, vendored files, tests, docs, examples và build scripts |
| Docker/OCI image | JAR, JRE, base OS, OS packages, CA certificates, fonts, native libraries, startup scripts và image metadata |
| SDK/library | Main JAR, transitive dependencies được phân phối, source/Javadoc, examples và API docs |
| Marketplace/OEM distribution | Tất cả thành phần được chuyển cho khách hàng cùng điều khoản vendor, sublicensing và redistribution rights |
| SaaS/hosted service | Source/runtime components, network-use clauses và nghĩa vụ theo license cụ thể; không mặc định giống binary redistribution |

Một Maven dependency được tải từ Maven Central **không tự động đồng nghĩa** tổ chức có quyền phân phối lại nó trong mọi sản phẩm. Tương tự, một dependency có POM khai báo `Apache-2.0` chưa đủ chứng minh JAR tải về đúng là bản phát hành được cấp phép đó; cần kiểm tra nguồn, phiên bản, artifact integrity và license text.

**Phân biệt ba quyết định:**

1. **Technical inventory:** component nào được build, bundle hoặc ship?
2. **License evidence:** license nào áp dụng, có text/notice/source chứng minh không?
3. **Distribution approval:** điều khoản có phù hợp với sản phẩm, cách tích hợp và kênh phát hành cụ thể không?

Công cụ build hỗ trợ phần 1 và thu thập bằng chứng cho phần 2. Phê duyệt phần 3 cần policy của tổ chức và người có thẩm quyền đánh giá điều khoản. Không có một Maven flag nào tự đưa ra kết luận pháp lý cho mọi trường hợp.

## 3. Xác định phạm vi component trong Maven/Spring Boot

### 3.1. Dependency tree và artifact cuối không phải một danh sách giống nhau

Maven quản lý dependencies theo coordinates, version, transitivity và scope. Một project có thể có:

- Direct dependencies khai báo trong `<dependencies>`.
- Transitive dependencies được kéo vào qua thư viện khác.
- Optional dependencies.
- Provided dependencies được container/runtime cung cấp.
- Test-only dependencies.
- System-scoped JAR lấy từ một đường dẫn local.
- Maven plugins và plugin dependencies chỉ dùng khi build.

Lệnh đầu tiên:

~~~bash
mvn dependency:tree
~~~

Xuất cây dependency ra file để review:

~~~bash
mvn dependency:tree -DoutputFile=target/dependency-tree.txt
mvn dependency:tree -Dscope=runtime -DoutputFile=target/runtime-dependencies.txt
~~~

`dependency:tree` hiển thị cây đã được Maven resolve, bao gồm direct/transitive dependencies. Lệnh với scope `runtime` giúp nhìn các thành phần phục vụ runtime theo Maven classpath. **Đừng chỉ dựa vào lệnh runtime để kết luận executable Spring Boot JAR đã đóng gói những gì**, bởi Boot repackage có quy tắc riêng.

### 3.2. Maven scopes

| Scope | Ý nghĩa Maven | Cách xử lý trong license review |
| --- | --- | --- |
| `compile` | Có trong compile, test và runtime classpaths; mặc định nếu không khai báo | Thường là dependency được ship trong executable JAR |
| `runtime` | Không cần compile nhưng cần khi chạy | Thường được ship trong executable JAR |
| `provided` | Có cho compile/test; dự kiến được runtime/container cung cấp | Kiểm tra kỹ: Spring Boot repackage mặc định vẫn include provided dependencies trong executable JAR |
| `test` | Chỉ dùng cho test compile/run | Thường không nằm trong executable JAR; review riêng nếu phát hành source/test bundle hoặc build environment |
| `system` | Lấy từ file local được chỉ định bằng `systemPath` | Khó tái lập và khó truy vết; cần xác minh binary, nguồn và quyền phân phối riêng |
| `import` | Import dependency management từ BOM trong `<dependencyManagement>` | Không phải dependency runtime độc lập; kiểm tra dependencies thực tế được quản lý |

Một điểm dễ bỏ sót: Spring Boot Maven Plugin `repackage` mặc định đưa cả các dependency `provided` vào executable JAR; các dependency optional và system scope có cấu hình include riêng. Vì thế không nên lấy quy tắc Maven runtime classpath rồi tự kết luận package contents. Kiểm tra effective plugin configuration và **JAR thực tế**.

Với POM ví dụ trong bài, inventory của executable JAR được đặt tương ứng với cấu hình Boot:

- License Maven Plugin: `includedScopes=compile,provided,runtime`, `includeOptional=false`, `includeTransitiveDependencies=true`.
- Spring Boot repackage: mặc định include provided dependencies; optional/system có thể được cấu hình khác.
- CycloneDX: compile/provided/runtime được bật; test/system được tắt trong ví dụ.

Nếu thay `includeOptional`, `includeSystemScope` hoặc exclude rules ở Boot plugin, phải cập nhật scope của license report/BOM và kiểm tra lại archive.

### 3.3. Những thứ dependency tree không thể nhìn thấy

`mvn dependency:tree` không tự inventory đầy đủ:

- Các JAR được copy thủ công vào resource folders hoặc shaded/embedded theo custom plugin.
- JavaScript/CSS/font/icon/ảnh tải về hoặc vendor trong repository.
- Native `.so`, `.dll`, `.dylib`, command-line binaries và data files.
- Source snippets, generated code, schemas, documentation, sample datasets.
- Các gói hệ điều hành và JRE trong Docker base image.
- Maven plugins, plugin dependencies và CI build images nếu không phát hành cùng ứng dụng.

Do đó inventory cuối phải so sánh **dependency graph với contents của sản phẩm phát hành** và rà soát các nguồn component ngoài Maven.

## 4. License metadata, license text và bằng chứng

Một dependency POM có thể khai báo:

~~~xml
<licenses>
    <license>
        <name>Apache License, Version 2.0</name>
        <url>https://www.apache.org/licenses/LICENSE-2.0</url>
        <distribution>repo</distribution>
    </license>
</licenses>
~~~

Đây là metadata do publisher ghi vào POM. Nó hữu ích để thu thập và lập báo cáo, nhưng không tự chứa toàn bộ điều khoản và không bảo đảm publisher khai báo đúng. Hãy đối chiếu:

1. License file trong source release hoặc repository chính thức.
2. Copyright headers, NOTICE và các file attribution của component.
3. POM/metadata của **đúng version artifact** đang resolve.
4. Release page, upstream repository và hash/signature nếu có.
5. Các file thực sự được đưa vào sản phẩm và những sửa đổi đã thực hiện.

Không gộp mọi dependency thành “Apache” chỉ vì phần lớn dự án Spring Boot sử dụng Apache 2.0. Một dependency có thể có license khác, dual-license, exception hoặc metadata không đầy đủ.

### 4.1. POM licenses chỉ nói về project hiện tại

Khối `<licenses>` ở POM mô tả giấy phép của **project phát hành POM đó**. Nó không tự thay đổi license của Spring, Tomcat, Jackson hoặc những transitive dependencies.

Nếu project demo được cấp phép theo Apache-2.0, nên có:

~~~text
LICENSE
src/main/resources/META-INF/LICENSE
src/main/resources/META-INF/NOTICE   (nếu dự án có NOTICE cần phân phối)
~~~

`LICENSE` ở repository giúp người đọc biết license của source project. Bản dưới `src/main/resources/META-INF/LICENSE` được đóng gói vào executable JAR. Nếu license yêu cầu giữ NOTICE hoặc upstream component cung cấp NOTICE cần chuyển tiếp, hãy đưa nội dung cần thiết vào distribution theo điều khoản áp dụng.

Không tự tạo một file LICENSE chỉ để làm build xanh. Nội dung phải là văn bản license thực sự được tổ chức lựa chọn và áp dụng.

## 5. SPDX identifiers và expressions

SPDX duy trì danh sách identifier chuẩn để biểu diễn license và exceptions. Ví dụ:

| SPDX ID | Tên |
| --- | --- |
| `Apache-2.0` | Apache License 2.0 |
| `MIT` | MIT License |
| `BSD-2-Clause` | BSD 2-Clause License |
| `BSD-3-Clause` | BSD 3-Clause License |
| `MPL-2.0` | Mozilla Public License 2.0 |
| `GPL-3.0-only` | GNU General Public License v3.0 only |
| `GPL-3.0-or-later` | GNU General Public License v3.0 or later |
| `LGPL-2.1-only` | GNU Lesser General Public License v2.1 only |

SPDX License List còn có exceptions. Không tự đặt một identifier gần giống tên license rồi coi đó là SPDX ID hợp lệ; tra đúng danh sách và đúng version.

### 5.1. OR, AND và WITH có nghĩa khác nhau

SPDX license expression cho phép mô tả tình huống phức tạp hơn một license đơn:

| Expression | Ý nghĩa tổng quát |
| --- | --- |
| `Apache-2.0` | Một license áp dụng |
| `MIT OR Apache-2.0` | Có lựa chọn giữa hai license; xác định lựa chọn và đáp ứng điều kiện của license đã chọn |
| `Apache-2.0 AND MIT` | Cần tuân thủ cả hai license |
| `GPL-2.0-or-later WITH Bison-exception-2.2` | GPL với exception cụ thể được gắn bằng toán tử WITH |
| `LicenseRef-Internal-Asset-License` | License riêng/chưa có SPDX ID chuẩn, được định nghĩa và đính kèm evidence trong tài liệu SPDX |

**OR không có nghĩa** tự động được chọn license thuận tiện nhất mà không đọc điều khoản. **AND không phải** hai lựa chọn thay thế. **WITH** chỉ rõ một exception; exception không phải license độc lập.

Hai special values cũng cần phân biệt:

- `NONE`: thể hiện không có license áp dụng theo khai báo.
- `NOASSERTION`: chưa đưa ra kết luận về license.

`NOASSERTION` không có nghĩa “đã được duyệt”. Nếu component chưa rõ license, trạng thái phát hành nên là **review required** cho đến khi có evidence.

Ví dụ header trong source khi dự án thực sự áp dụng Apache-2.0:

~~~java
/*
 * SPDX-License-Identifier: Apache-2.0
 */
package demo;
~~~

Header SPDX là cách ghi nhận license cho file/source theo policy; nó không thay thế LICENSE file, NOTICE, attribution hoặc các nghĩa vụ phân phối khác.

## 6. License Maven Plugin: tạo inventory third-party

`org.codehaus.mojo:license-maven-plugin` hỗ trợ:

- Sinh `THIRD-PARTY.txt` liệt kê dependencies và license metadata.
- Tải license files từ URL trong POM dependency.
- Báo dependencies thiếu license metadata.
- Dùng missing-file/override metadata có kiểm chứng.
- Áp dụng included/excluded license names để fail build theo policy.
- Kiểm tra headers và license file của project.

Plugin hiện hành trong ví dụ là `2.7.1`. Goal `license:add-third-party` tạo báo cáo dependencies; theo cấu hình, nó có thể thêm output directory vào resources để file notice được đưa vào artifact. Nó đọc license name/URL từ POM và có cơ chế xử lý metadata thiếu, vì vậy **đừng coi output là một kết luận pháp lý tự động**.

### 6.1. Cấu hình tạo THIRD-PARTY.txt

Fragment sau được dùng trong POM ở mục 11:

~~~xml
<plugin>
    <groupId>org.codehaus.mojo</groupId>
    <artifactId>license-maven-plugin</artifactId>
    <version>2.7.1</version>
    <executions>
        <execution>
            <id>third-party-notices</id>
            <phase>generate-resources</phase>
            <goals>
                <goal>add-third-party</goal>
            </goals>
            <configuration>
                <includeTransitiveDependencies>true</includeTransitiveDependencies>
                <includeOptional>false</includeOptional>
                <includedScopes>compile,provided,runtime</includedScopes>
                <useMissingFile>true</useMissingFile>
                <missingFile>${project.basedir}/src/license/THIRD-PARTY.properties</missingFile>
                <failOnMissing>true</failOnMissing>
                <generateBundle>true</generateBundle>
                <bundleThirdPartyPath>META-INF/THIRD-PARTY.txt</bundleThirdPartyPath>
                <addOutputDirectoryAsResourceDir>true</addOutputDirectoryAsResourceDir>
                <encoding>UTF-8</encoding>
            </configuration>
        </execution>
    </executions>
</plugin>
~~~

Giải thích:

- `add-third-party` lấy dependencies theo Maven project và tạo danh sách third-party licenses.
- `includeTransitiveDependencies=true` yêu cầu rà cả dependency gián tiếp.
- `includedScopes` trong ví dụ khớp nhóm scope được dùng cho executable JAR: compile, provided, runtime.
- `includeOptional=false` khớp mặc định Boot repackage không include optional dependencies; nếu dự án bật includeOptional thì cần thay đổi inventory.
- `useMissingFile=true` cho phép bổ sung metadata đã được kiểm tra thủ công khi POM dependency thiếu license.
- `failOnMissing=true` làm build fail nếu còn license metadata chưa giải quyết.
- `generateBundle=true` tạo bản notice ở resource path `META-INF/THIRD-PARTY.txt`.
- `addOutputDirectoryAsResourceDir=true` giúp resource sinh ra được đưa vào package; vẫn phải kiểm tra archive cuối.

License plugin mặc định xử lý dependency graph rộng hơn một danh sách direct dependencies. Việc lọc scope/optional phải được chọn theo **thành phần thực tế phát hành**. Nếu thay cách package, phải điều chỉnh và so lại với file cuối.

### 6.2. Lần đầu phát hiện dependency thiếu license

Không nên đoán license cho một thư viện chỉ từ tên artifact. Trong lần khảo sát đầu, có thể tạm cho phép báo cáo thiếu metadata để tạo danh sách cần xử lý:

~~~bash
mvn license:add-third-party \
  -Dlicense.useMissingFile=true \
  -Dlicense.failOnMissing=false
~~~

Plugin có thể tạo hoặc cập nhật file:

~~~text
src/license/THIRD-PARTY.properties
~~~

Ví dụ một dòng **minh họa định dạng**:

~~~properties
com.example.vendor--legacy-component--1.2.3=Apache License, Version 2.0
~~~

Các trường trong key là `groupId--artifactId--version`. Giá trị license chỉ được điền sau khi người review xác nhận đúng version, source release và license text của component. Không dùng ví dụ trên làm giấy phép mặc định cho một artifact bất kỳ.

Sau khi xử lý toàn bộ entries:

1. Lưu nguồn bằng chứng và lý do cho từng override.
2. Kiểm tra tên/license URL trong POM dependency; nếu sai, xem upstream release và dùng cơ chế override có quản lý.
3. Chạy lại với `failOnMissing=true`.
4. Review nội dung `THIRD-PARTY.txt` và archive cuối.

Một dependency có license metadata nhưng metadata sai vẫn có thể làm báo cáo “đẹp”. Vì vậy cần rà cả **unknown/missing** lẫn **incorrect declaration**.

### 6.3. Tải license files

Có thể dùng goal:

~~~bash
mvn license:download-licenses
~~~

Theo mặc định, plugin tải các license files vào `target/licenses` từ URL được khai báo trong dependency POM. URL có thể thiếu, lỗi hoặc trỏ tới một tài liệu không phải license text chính xác; mỗi file cần được xem lại.

`THIRD-PARTY.txt` là **danh sách thông tin dependencies và license names**, không tự chứa đầy đủ mọi license text. Nếu điều khoản yêu cầu phân phối license text/copyright notices, hãy đưa các file cần thiết vào package, chẳng hạn dưới `META-INF/third-party/`, theo cách được dự án kiểm soát. Đừng giả định lệnh download tự động đáp ứng tất cả nghĩa vụ.

## 7. Áp dụng allowlist/denylist theo policy

License Maven Plugin hỗ trợ `includedLicenses`, `excludedLicenses` và `failOnBlacklist`. Khi `failOnBlacklist=true`:

- License không thuộc allowlist `includedLicenses` có thể làm build fail.
- License nằm trong `excludedLicenses` làm build fail.
- Giá trị so khớp là **license names** mà plugin đọc từ dependency POM/metadata, không phải lúc nào cũng là SPDX identifiers.

Ví dụ policy fragment:

~~~xml
<configuration>
    <includedLicenses>
        <includedLicense>The Apache Software License, Version 2.0</includedLicense>
        <includedLicense>Apache License, Version 2.0</includedLicense>
        <includedLicense>MIT License</includedLicense>
        <includedLicense>BSD 3-Clause License</includedLicense>
    </includedLicenses>
    <excludedLicenses>
        <excludedLicense>Example Restricted License</excludedLicense>
    </excludedLicenses>
    <failOnBlacklist>true</failOnBlacklist>
</configuration>
~~~

Đây là **allowlist minh họa**, không phải danh sách được khuyến nghị cho mọi công ty. Các POM có thể dùng tên khác nhau cho cùng license, khai báo dual-license hoặc metadata không đầy đủ. Trước khi bật enforcement, hãy tạo report, normalize names theo policy có kiểm chứng và được phê duyệt.

Không coi `OSI Approved` là tiêu chí duy nhất để cho phép phân phối. Một license được OSI approve vẫn có thể không phù hợp với một sản phẩm, phương thức linking, mô hình kinh doanh hoặc nghĩa vụ phân phối cụ thể.

### 7.1. Maven Enforcer chặn component theo coordinates

Maven Enforcer `bannedDependencies` có thể fail build nếu một dependency coordinates nằm trong danh sách cấm:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-enforcer-plugin</artifactId>
    <version>3.6.3</version>
    <executions>
        <execution>
            <id>block-unapproved-component</id>
            <goals>
                <goal>enforce</goal>
            </goals>
            <configuration>
                <rules>
                    <bannedDependencies>
                        <searchTransitive>true</searchTransitive>
                        <excludes>
                            <exclude>com.example.policy:blocked-component</exclude>
                        </excludes>
                    </bannedDependencies>
                </rules>
                <fail>true</fail>
            </configuration>
        </execution>
    </executions>
</plugin>
~~~

`com.example.policy:blocked-component` là coordinate giả để minh họa; thay bằng artifact thực sự được policy cấm. Rule kiểm tra direct/transitive dependency coordinates theo pattern. Nó **không đọc license text và không quyết định license compatibility**. Dùng Enforcer cho component blacklist riêng; dùng inventory/license review để đánh giá quyền phân phối.

## 8. CycloneDX SBOM: ghi nhận component và license metadata

SBOM (*Software Bill of Materials*) là danh sách component trong một sản phẩm, kèm định danh/version và những metadata có sẵn như license, hashes, supplier, dependency relationships. Nó hỗ trợ security, license review, incident response và supply-chain traceability.

`CycloneDX Maven Plugin` sinh BOM từ dependency graph Maven:

- `makeBom` tạo BOM cho từng Maven module.
- `makeAggregateBom` tạo BOM tổng hợp cho multi-module reactor.
- `makePackageBom` hỗ trợ module có packaging WAR/EAR.
- BOM thường được tạo dạng XML/JSON và có thể attach classifier `cyclonedx` khi install/deploy.

Trong ví dụ, version `2.9.3` hỗ trợ CycloneDX schema `1.6`. Cấu hình:

~~~xml
<plugin>
    <groupId>org.cyclonedx</groupId>
    <artifactId>cyclonedx-maven-plugin</artifactId>
    <version>2.9.3</version>
    <executions>
        <execution>
            <id>create-application-bom</id>
            <phase>package</phase>
            <goals>
                <goal>makeBom</goal>
            </goals>
        </execution>
    </executions>
    <configuration>
        <projectType>application</projectType>
        <schemaVersion>1.6</schemaVersion>
        <includeCompileScope>true</includeCompileScope>
        <includeProvidedScope>true</includeProvidedScope>
        <includeRuntimeScope>true</includeRuntimeScope>
        <includeSystemScope>false</includeSystemScope>
        <includeTestScope>false</includeTestScope>
        <outputFormat>all</outputFormat>
        <outputName>bom</outputName>
    </configuration>
</plugin>
~~~

Với `outputName=bom` và `outputFormat=all`, output thường gồm:

~~~text
target/bom.json
target/bom.xml
~~~

Cả hai BOM là **tài liệu riêng** được tạo từ project dependencies; chúng không tự trở thành file nằm trong executable JAR. Plugin có thể attach chúng dưới classifier `cyclonedx` khi Maven install/deploy.

### 8.1. SBOM không phải giấy phép phê duyệt

BOM có thể ghi license metadata mà dependency publisher khai báo. Nó không chứng minh metadata đó đúng, không diễn giải mọi điều khoản, không quyết định một cách tích hợp có tạo nghĩa vụ bổ sung hay không và không thay thế việc kiểm tra LICENSE/NOTICE files.

Cần đối chiếu BOM với:

- `mvn dependency:tree` đã resolve.
- Nested libraries trong `BOOT-INF/lib` của executable JAR.
- Resources và file được copy/nhúng thủ công.
- Dependencies trong container base image và OS packages nếu sản phẩm là Docker/OCI image.

Một BOM Maven không tự inventory mọi package có trong base OS/JRE layer. Khi phát hành image, tạo **image-level SBOM** bằng scanner/tool được tổ chức phê duyệt và rà license của những packages trong image riêng.

## 9. SPDX document và vai trò của SPDX Maven Plugin

CycloneDX là một định dạng SBOM. SPDX là một chuẩn khác có mô hình thể hiện license, copyright, package, file, relationships và document provenance. Tùy policy của khách hàng/registry, có thể cần một hoặc cả hai định dạng.

`spdx-maven-plugin` có goal `spdx:createSPDX` để tạo SPDX document từ thông tin artifact/POM và cấu hình file-level. Ví dụ khai báo plugin theo tài liệu của project:

~~~xml
<plugin>
    <groupId>org.spdx</groupId>
    <artifactId>spdx-maven-plugin</artifactId>
    <version>1.0.4</version>
    <executions>
        <execution>
            <id>build-spdx-document</id>
            <goals>
                <goal>createSPDX</goal>
            </goals>
        </execution>
    </executions>
</plugin>
~~~

Lệnh gọi trực tiếp:

~~~bash
mvn spdx:createSPDX
~~~

Plugin tạo document dưới `target/site/` với filename dựa trên groupId/artifactId/version và output format. Cần cấu hình SPDX package/file fields, source information, license và custom license references theo tài liệu plugin.

**Không suy luận** rằng chỉ thêm plugin là đã quét toàn bộ binary hoặc đã kết luận mọi component. Cần xem SPDX document thật, kiểm tra package/file scope và bổ sung thông tin không thể suy ra từ POM. Khi license không nằm trong SPDX License List, dùng `LicenseRef-...` và kèm license text/evidence đúng cách, không bịa SPDX ID.

## 10. POM hoàn chỉnh: Spring Boot, license notices và BOM

Project demo giả định tự chọn Apache-2.0. POM dưới đây:

- Build executable JAR bằng Spring Boot Maven Plugin.
- Sinh `THIRD-PARTY.txt` từ dependency metadata.
- Fail khi thiếu license metadata chưa được giải quyết.
- Sinh CycloneDX XML/JSON BOM.
- Đặt Java target 17.

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>example.learning</groupId>
    <artifactId>distribution-audit-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <name>Distribution Audit Demo</name>
    <description>Spring Boot packaging and license inventory example</description>

    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <licenses>
        <license>
            <name>Apache License, Version 2.0</name>
            <url>https://www.apache.org/licenses/LICENSE-2.0</url>
            <distribution>repo</distribution>
        </license>
    </licenses>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>

            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>license-maven-plugin</artifactId>
                <version>2.7.1</version>
                <executions>
                    <execution>
                        <id>third-party-notices</id>
                        <phase>generate-resources</phase>
                        <goals>
                            <goal>add-third-party</goal>
                        </goals>
                        <configuration>
                            <includeTransitiveDependencies>true</includeTransitiveDependencies>
                            <includeOptional>false</includeOptional>
                            <includedScopes>compile,provided,runtime</includedScopes>
                            <useMissingFile>true</useMissingFile>
                            <missingFile>${project.basedir}/src/license/THIRD-PARTY.properties</missingFile>
                            <failOnMissing>true</failOnMissing>
                            <generateBundle>true</generateBundle>
                            <bundleThirdPartyPath>META-INF/THIRD-PARTY.txt</bundleThirdPartyPath>
                            <addOutputDirectoryAsResourceDir>true</addOutputDirectoryAsResourceDir>
                            <encoding>UTF-8</encoding>
                        </configuration>
                    </execution>
                </executions>
            </plugin>

            <plugin>
                <groupId>org.cyclonedx</groupId>
                <artifactId>cyclonedx-maven-plugin</artifactId>
                <version>2.9.3</version>
                <executions>
                    <execution>
                        <id>create-application-bom</id>
                        <phase>package</phase>
                        <goals>
                            <goal>makeBom</goal>
                        </goals>
                    </execution>
                </executions>
                <configuration>
                    <projectType>application</projectType>
                    <schemaVersion>1.6</schemaVersion>
                    <includeCompileScope>true</includeCompileScope>
                    <includeProvidedScope>true</includeProvidedScope>
                    <includeRuntimeScope>true</includeRuntimeScope>
                    <includeSystemScope>false</includeSystemScope>
                    <includeTestScope>false</includeTestScope>
                    <outputFormat>all</outputFormat>
                    <outputName>bom</outputName>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**Điểm cần hiểu trước khi dùng POM:**

- `<licenses>` mô tả license của **project demo**, không phải của dependencies.
- `spring-boot-maven-plugin` được quản lý bởi Boot parent và tạo executable JAR trong package lifecycle.
- License plugin dùng scope compile/provided/runtime để inventory dependencies có khả năng xuất hiện trong executable JAR; transitive được bật, optional được tắt tương ứng với mặc định Boot repackage.
- `failOnMissing=true` cố ý làm build fail nếu license metadata còn thiếu. Cần hoàn thiện `src/license/THIRD-PARTY.properties` trước release.
- CycloneDX plugin sinh BOM riêng, không thay thế `THIRD-PARTY.txt` hoặc legal approval.
- POM chưa chứa repository credentials, allowlist của công ty hoặc quyết định phân phối của một sản phẩm thật.

Trong project thật, hãy pin plugin versions theo build governance, kiểm tra effective POM và xác nhận mọi plugin execution thực sự được kích hoạt.

## 11. Source code và license resources của ứng dụng

### 11.1. Application.java

Tạo `src/main/java/demo/DistributionAuditDemoApplication.java`:

~~~java
/*
 * SPDX-License-Identifier: Apache-2.0
 */
package demo;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class DistributionAuditDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                DistributionAuditDemoApplication.class, args);
    }

    @Bean
    CommandLineRunner report() {
        return args ->
                System.out.println("distribution-audit-demo:ready");
    }
}
~~~

Header SPDX chỉ đúng nếu project này thực sự chọn Apache-2.0 và tổ chức có quyền cấp license đó. Nếu project dùng license khác hoặc nhiều licenses, phải sửa header theo quyết định đã xác minh.

Chạy ứng dụng:

~~~bash
java -jar target/distribution-audit-demo-1.0.0.jar \
  --spring.main.banner-mode=off \
  --logging.level.root=OFF
~~~

Dòng do code ứng dụng in ra chính xác:

~~~text
distribution-audit-demo:ready
~~~

Spring Boot startup logs có thể khác theo môi trường; dòng trên là nội dung của `CommandLineRunner`.

### 11.2. Đặt license text vào resources

Trong project demo, tạo:

~~~text
LICENSE
src/main/resources/META-INF/LICENSE
src/main/resources/META-INF/NOTICE        (nếu có nghĩa vụ NOTICE)
src/license/THIRD-PARTY.properties        (khi có metadata thiếu đã xác minh)
~~~

`LICENSE` ở root repository nên chứa toàn văn license của source project. `META-INF/LICENSE` được đưa vào classpath/resource của executable JAR. Nếu cần phân phối NOTICE của chính project hoặc các upstream components, đưa các nội dung cần thiết vào `META-INF/NOTICE` hoặc vị trí theo policy.

Không copy nguyên license files của mọi dependency một cách máy móc nếu chưa kiểm tra nội dung và collision. Dùng `license:download-licenses` để hỗ trợ thu thập, rồi xác định những license texts/notices phải được ship theo từng license và channel.

## 12. Build, tạo SBOM và kiểm tra dependency inventory

Từ project root:

~~~bash
mvn -B -ntp clean verify
~~~

Build gồm:

1. `generate-resources`: License Maven Plugin resolve dependencies và tạo third-party notice.
2. Compile/test/package: Maven build project.
3. Spring Boot `repackage`: tạo executable JAR.
4. `package`: CycloneDX plugin tạo BOM.

Các output chính:

~~~text
target/distribution-audit-demo-1.0.0.jar
target/bom.json
target/bom.xml
target/generated-sources/license/THIRD-PARTY.txt
~~~

Đường dẫn output của License Plugin phụ thuộc `outputDirectory` nếu tùy chỉnh; đường dẫn trên là vị trí mặc định thường dùng. Kiểm tra file thực tế sau build.

Lấy cây dependency:

~~~bash
mvn dependency:tree -DoutputFile=target/dependency-tree.txt
mvn dependency:tree -Dscope=runtime -DoutputFile=target/runtime-dependencies.txt
~~~

Nếu còn license metadata thiếu trong giai đoạn khám phá, có thể tạm chạy:

~~~bash
mvn license:add-third-party \
  -Dlicense.useMissingFile=true \
  -Dlicense.failOnMissing=false
~~~

Xem danh sách cần xử lý, xác minh upstream license, điền file missing metadata và chạy lại strict build. Không giữ override không có evidence chỉ để CI xanh.

### 12.1. Kiểm tra BOM

Xem file JSON/XML bằng công cụ phù hợp:

~~~text
target/bom.json
target/bom.xml
~~~

BOM phải phản ánh đúng Maven module, version, direct/transitive components, license metadata và dependency relationships có sẵn. CycloneDX plugin mặc định attach BOM với classifier `cyclonedx` khi install/deploy; nếu cần lưu cùng release, kiểm tra artifact thực sự được attach và publish.

### 12.2. Kiểm tra executable JAR

~~~bash
jar tf target/distribution-audit-demo-1.0.0.jar
~~~

Với executable Spring Boot JAR, kiểm tra các nhóm entries:

~~~text
META-INF/MANIFEST.MF
BOOT-INF/classes/demo/DistributionAuditDemoApplication.class
BOOT-INF/classes/META-INF/LICENSE
BOOT-INF/classes/META-INF/THIRD-PARTY.txt
BOOT-INF/lib/...
~~~

Đây là danh sách minh họa các entries cần có trong ví dụ, không phải toàn bộ output của `jar tf`. `BOOT-INF/lib` chứa nested runtime libraries. Nếu ứng dụng có NOTICE cần phân phối, cũng xác nhận entry `BOOT-INF/classes/META-INF/NOTICE`.

**Đừng chỉ kiểm tra `target/generated-sources/license/THIRD-PARTY.txt`**. File có thể được tạo nhưng bị exclude hoặc không được đưa vào JAR cuối. Chỉ archive cuối mới chứng minh nội dung được ship.

## 13. Java 17 validator kiểm tra license resources trong executable JAR

Tạo `DistributionArchiveCheck.java` tại project root, ngoài `src/main/java`:

~~~java
import java.nio.file.Path;
import java.util.jar.JarFile;

public class DistributionArchiveCheck {

    private static void require(boolean condition, String message) {
        if (!condition) {
            throw new IllegalStateException(message);
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: java DistributionArchiveCheck.java <jar-file>");
        }

        Path path = Path.of(args[0]);
        try (JarFile jar = new JarFile(path.toFile())) {
            String prefix = "BOOT-INF/classes/META-INF/";

            boolean projectLicense =
                    jar.getEntry(prefix + "LICENSE") != null;
            boolean thirdPartyNotice =
                    jar.getEntry(prefix + "THIRD-PARTY.txt") != null;
            boolean runtimeLibraries = jar.stream().anyMatch(entry ->
                    entry.getName().startsWith("BOOT-INF/lib/")
                            && entry.getName().endsWith(".jar"));

            require(projectLicense,
                    "Project LICENSE is missing from executable JAR");
            require(thirdPartyNotice,
                    "THIRD-PARTY.txt is missing from executable JAR");
            require(runtimeLibraries,
                    "No nested runtime libraries found");

            System.out.println("archive.project-license=present");
            System.out.println("archive.third-party-notice=present");
            System.out.println("archive.runtime-libraries=present");
        }
    }
}
~~~

Chương trình dùng Java 17 Standard Library `JarFile`, kiểm tra ba điều kiện packaging:

- Project license text được đóng gói ở classpath resources.
- Third-party notice được đưa vào executable JAR.
- JAR có nested runtime dependencies.

Chạy:

~~~bash
java DistributionArchiveCheck.java \
  target/distribution-audit-demo-1.0.0.jar
~~~

Với đúng cấu hình ví dụ và các resources đã tạo, stdout chính xác:

~~~text
archive.project-license=present
archive.third-party-notice=present
archive.runtime-libraries=present
~~~

Validator này **không đánh giá nội dung license có chính xác, đầy đủ hay tương thích pháp lý không**. Nó chỉ ngăn một lỗi packaging phổ biến: report/notice được sinh nhưng không có trong archive. Việc review danh sách component, license texts, NOTICE và obligations vẫn cần bước riêng.

Nếu dùng executable WAR, application resources nằm dưới `WEB-INF/classes/META-INF/` và libraries ở `WEB-INF/lib`/`WEB-INF/lib-provided`. Khi đó cần điều chỉnh validator theo WAR layout; không áp nguyên đường dẫn `BOOT-INF`.

## 14. Đánh giá nghĩa vụ theo loại license và cách sử dụng

Bảng sau chỉ là định hướng để biết những câu hỏi cần đặt ra. Điều khoản cụ thể, phiên bản license, exception, cách linking/combining và kênh phân phối mới quyết định nghĩa vụ thực tế.

| Nhóm/license ví dụ | Các điểm thường cần rà | Không nên suy luận |
| --- | --- | --- |
| Apache-2.0 | Giữ license text, copyright/NOTICE cần thiết; xem patent grant và điều kiện khi sửa đổi | Có Apache-2.0 không có nghĩa được dùng trademark hoặc bỏ NOTICE của upstream |
| MIT | Giữ copyright và permission notice trong bản phân phối phù hợp | MIT không có nghĩa được xóa attribution |
| BSD-2-Clause / BSD-3-Clause | Giữ copyright, điều kiện và disclaimer; BSD-3 có điều khoản không endorsement | Không gộp mọi BSD thành một chuỗi điều khoản duy nhất |
| MPL-2.0 | Rà file-level copyleft, file nào được sửa và cách cung cấp source của covered files khi phân phối | Không kết luận cả sản phẩm tự động có cùng license chỉ từ một file MPL |
| LGPL | Rà cách link, khả năng thay/relink library, source và các điều kiện phân phối tương ứng | Static/dynamic linking và cấu trúc package có thể làm nghĩa vụ khác nhau |
| GPL | Rà việc phân phối covered work, source/corresponding source và điều kiện kết hợp | Không đưa ra kết luận chỉ từ việc một dependency nằm trong Maven tree |
| AGPL | Rà cả cách cung cấp dịch vụ qua mạng và điều khoản network-use | Không giả định hosted service luôn giống việc chỉ sử dụng một binary nội bộ |
| Proprietary/commercial | Kiểm tra hợp đồng, redistribution rights, số lượng instance/user, territory, sublicensing, support và hạn chế chuyển giao | Có thể tải JAR không đồng nghĩa có quyền ship JAR cho khách hàng |
| Custom/unknown | Đọc license text, xác định chủ thể cấp quyền, phạm vi, nguồn và các điều kiện riêng | Không tự đặt tên SPDX ID hoặc cho qua vì POM có URL |

Các obligations có thể gồm:

- Phân phối kèm license text và copyright notices.
- Giữ nguyên file NOTICE hoặc đưa thêm attribution.
- Công bố/đính kèm source code tương ứng hoặc cách cung cấp source.
- Công bố thay đổi đối với các file chịu copyleft.
- Cung cấp relinking materials hoặc quyền thay thế library theo điều kiện cụ thể.
- Ghi rõ các thay đổi và bản quyền.
- Tôn trọng patent clauses, exception và giới hạn trademark.
- Đáp ứng điều khoản hợp đồng riêng cho component thương mại.

Không áp một quy tắc chung cho mọi license cùng tên nếu component có exception, dual-license hoặc license text sửa đổi. Ghi lại **phiên bản license và evidence cụ thể**.

## 15. Ma trận quyết định: component nào được đưa vào distribution?

Mỗi component nên có một record review:

| Trường | Ví dụ nội dung |
| --- | --- |
| Component identity | `org.example:library:2.4.1` hoặc path tới asset |
| Nguồn | Maven repository/upstream URL/vendor package |
| Version và hash | Version chính xác, SHA-256 nếu artifact có |
| Relationship | Direct/transitive, parent dependency |
| Scope | compile/runtime/provided/test/system hoặc non-Maven |
| Có được ship không? | Có/không; artifact/channel nào |
| Declared license | SPDX ID/expression hoặc tên trong POM |
| Evidence | LICENSE, NOTICE, source tag, POM, contract, URL |
| Obligations | Text/notice/source/attribution/other conditions |
| Decision | APPROVED / APPROVED_WITH_OBLIGATIONS / REVIEW_REQUIRED / REJECTED / NOT_SHIPPED |
| Reviewer/date | Người phê duyệt, thời điểm, policy/version áp dụng |

**APPROVED_WITH_OBLIGATIONS** có nghĩa phải có task để đảm bảo các điều kiện được hoàn tất trước release. Không để trạng thái này trôi qua release gate mà chưa có bằng chứng file notice/source tương ứng đã được ship.

### 15.1. Tách review code, asset và contract

Một sản phẩm có thể đồng thời có:

- Maven libraries với SPDX license IDs.
- Font/icon có attribution riêng.
- Ảnh/data có điều khoản cấm thương mại hoặc giới hạn redistributing.
- SDK proprietary cần quyền redistribute cho khách hàng.
- Native binary có license text tách khỏi POM.
- Container base image có packages và notices riêng.

Không ép những component này vào một dependency tree Maven. Tạo inventory riêng nhưng giữ chung release manifest để biết chúng thuộc artifact nào.

## 16. Những component ngoài Maven và Docker base image

### 16.1. Frontend, fonts, images và native binaries

Nếu ứng dụng copy các file sau vào `src/main/resources` hoặc static directories, chúng vẫn là component được phân phối:

- JavaScript packages và CSS frameworks.
- Web fonts, icon packs, SVGs, logos.
- Hình ảnh, video, datasets, maps và sample data.
- Native executables hoặc `.so`/`.dll`/`.dylib` libraries.
- SQL schemas, certificates, command scripts, generated templates.
- Source snippets hoặc code được copy từ Stack Overflow, repositories và tài liệu.

Mỗi file/vendor bundle cần nguồn, version/commit, license, hash và điều kiện phân phối. Một file được copy trực tiếp vào JAR có thể **không xuất hiện** trong Maven SBOM, nhưng vẫn có thể mang nghĩa vụ license.

### 16.2. Container image

Nếu phát hành Docker/OCI image, inventory phải bao gồm:

1. Executable JAR và tất cả embedded dependencies.
2. JRE distribution.
3. Base operating system và package manager packages.
4. CA certificates, fonts, native tools và các package được cài thêm.
5. Startup scripts, healthcheck binaries, files được copy thủ công.
6. SBOM của image và registry digest/version được phát hành.

CycloneDX Maven BOM của Java project không thay thế image-level SBOM. Tạo inventory từ **image cuối** bằng công cụ scanner được tổ chức phê duyệt, đối chiếu OS packages với base image và các layers do Dockerfile thêm.

### 16.3. Build tools và plugins

Maven plugins, compiler, test runners và CI container thường không được đóng gói vào executable JAR. Tuy nhiên chúng vẫn là một phần build supply chain. Nếu phân phối build environment/toolchain image hoặc source bundle cho khách hàng, chúng có thể trở thành thành phần của sản phẩm cần review.

Tách rõ:

- **Runtime SBOM:** những gì ứng dụng cần khi chạy.
- **Build SBOM:** công cụ và dependency dùng để tạo sản phẩm.
- **Container/image SBOM:** mọi packages nằm trong image phát hành.

Ba inventory có thể liên quan nhưng không nhất thiết giống nhau.

## 17. CI release gate cho license và distributable components

Một release pipeline có thể tổ chức như sau:

~~~text
1. Resolve exact dependency versions
          |
          v
2. dependency:tree + source/asset inventory
          |
          v
3. License Maven Plugin
   - generate THIRD-PARTY.txt
   - detect missing metadata
   - resolve verified overrides
   - apply approved allowlist/denylist
          |
          v
4. CycloneDX BOM (+ SPDX document nếu yêu cầu)
          |
          v
5. Human/policy review
   - license text and version
   - distribution channel
   - required notices/source/attribution
   - commercial redistribution rights
          |
          v
6. Build executable JAR / image
          |
          v
7. Inspect final archive/image
   - nested dependencies
   - LICENSE / NOTICE / THIRD-PARTY
   - non-Maven components
          |
          v
8. Save SBOM + hashes + approval evidence
          |
          v
9. Publish exact artifact that passed gates
~~~

| Gate | PASS khi | FAIL/hold khi |
| --- | --- | --- |
| Dependency inventory | Direct/transitive dependencies và versions đã được ghi nhận | Không giải thích được một dependency hoặc version |
| License metadata | Mỗi component có evidence phù hợp; không còn unknown chưa xử lý | Missing/NOASSERTION chưa được review |
| Policy allowlist/denylist | Mọi component khớp policy đã phê duyệt | Component không có trong allowlist hoặc bị cấm |
| Obligations | License texts/NOTICE/source/attribution và hợp đồng cần thiết đã được đáp ứng | Chưa có tài liệu hoặc quyền redistribute |
| Package inspection | Archive/image chứa đúng component đã review và các notices bắt buộc | Có file/component ngoài inventory hoặc thiếu notice |
| SBOM | BOM được tạo, đúng sản phẩm/version và lưu cùng release evidence | SBOM thiếu module, sai scope hoặc không gắn với artifact |
| Integrity | Artifact hash và image digest được ghi lại | Không xác định được bytes đã được review |
| Publish | Đúng file/image đã vượt qua tất cả gates | Build lại/đổi dependency sau phê duyệt mà chưa review |

### 17.1. Release evidence tối thiểu

Một release record hữu ích:

~~~text
Product / module       : distribution-audit-demo
Release version        : 1.0.0
Git revision           : exact source commit
Build toolchain        : Maven + JDK version
Dependency graph       : dependency-tree.txt
License report         : THIRD-PARTY.txt
SBOM                   : bom.json / bom.xml
Project license        : SPDX ID + LICENSE file
Third-party obligations: notices/source/attribution checklist
Non-Maven inventory    : assets/fonts/native/base-image
Approval               : reviewer, policy version, date
JAR SHA-256            : checksum of exact executable JAR
Image digest           : digest if an OCI image is shipped
Repository location    : exact published artifact coordinates
~~~

Không lưu password, token hoặc secret trong SBOM, license report hay build logs. Nếu một vendor license/hợp đồng bị giới hạn truy cập, lưu reference tới kho tài liệu được kiểm soát thay vì nhúng hợp đồng vào public artifact.

### 17.2. Không build lại sau approval mà giữ nguyên kết luận cũ

Nếu dependency version, resource, JAR bytes, base image hoặc Dockerfile thay đổi sau review, release evidence có thể không còn áp dụng cho artifact mới. Chạy lại các bước inventory/scan tương ứng và gắn approval với **đúng artifact hashes/version**. Không dùng approval cho JAR A để phát hành JAR B chỉ vì Git commit không đổi.

## 18. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng điều tra |
| --- | --- | --- |
| `THIRD-PARTY.txt` không có transitive libraries | Plugin filters hoặc `includeTransitiveDependencies` sai | Xem effective POM, plugin logs, dependency tree |
| Build fail vì unknown license | POM dependency thiếu license metadata | Xem upstream source/release, dùng missing file sau khi xác minh |
| Report ghi Apache nhưng source release có LICENSE khác | POM metadata sai hoặc artifact/release không khớp | Xác minh đúng version/hash và upstream license text |
| Allowlist fail với “Apache License” dù đã cho “Apache-2.0” | License plugin so khớp human-readable POM names, không trực tiếp dùng SPDX ID | So tên chính xác trong report, chuẩn hóa policy |
| SBOM thiếu một file font/icon | File không được khai báo là Maven dependency | Bổ sung asset inventory và license evidence riêng |
| SBOM có dependency không nằm trong JAR | Khác biệt scope, optional, system hoặc test | Đối chiếu CycloneDX scope với `BOOT-INF/lib` |
| JAR có library `provided` không nằm trong license report | Scope report bỏ provided nhưng Boot repackage đã include | Include provided trong license inventory hoặc chứng minh không ship |
| JAR có `META-INF/THIRD-PARTY.txt` nhưng thiếu license text | Third-party summary không tự bundle mọi license text | Download/review license files và package theo obligations |
| POM `<licenses>` là Apache nhưng dependency GPL | Nhầm project license với third-party licenses | Review mỗi component riêng |
| `NOASSERTION` bị xem như approved | Chưa có kết luận license | Chuyển sang REVIEW_REQUIRED |
| Dependency tải được từ Maven Central bị coi là tự do redistribute | Nhầm khả năng download với quyền phân phối | Kiểm tra license, contract và channel |
| Container image có thêm packages ngoài Maven BOM | Base OS/JRE và Docker layers không thuộc Maven graph | Tạo image-level SBOM và review OS packages |
| Maven Enforcer không chặn license lạ | BannedDependencies chỉ match artifact coordinates | Dùng license report/allowlist; Enforcer chỉ cho component blacklist |
| `mvn clean verify` xanh nhưng release thiếu notice | Notice chưa được đưa vào archive cuối | Kiểm tra `jar tf` và validator trên chính JAR |
| License file được sửa thủ công mà không có source | Evidence không truy vết được | Lưu upstream URL/hash/reviewer và revision của override |
| Multi-module report chỉ chứa một module | Dùng goal non-aggregate ở root hoặc execution sai | Dùng aggregate goal hoặc từng module theo layout reactor |
| Docker image update làm phát sinh package mới | Base image tag mutable hoặc layer thay đổi | Pin/record digest, tạo lại image SBOM và review |

Không giải quyết lỗi bằng cách bỏ dependency khỏi report nếu nó vẫn được đóng gói. Chỉ exclude khỏi inventory khi có lý do rõ ràng và bằng chứng rằng component không thuộc phạm vi phân phối hoặc được một inventory khác bao phủ.

## 19. Checklist và câu hỏi tự kiểm tra

### Checklist trước khi phát hành

- [ ] Đã chốt chính xác sản phẩm và kênh phân phối: source, JAR, WAR, image, SDK, OEM hay hosted.
- [ ] Đã ghi direct/transitive Maven dependencies, versions và scopes.
- [ ] Đã đối chiếu dependency tree với nested JARs/resources thực tế trong archive.
- [ ] Đã inventory fonts, icons, images, frontend, native binaries, datasets và vendored code.
- [ ] Đã kiểm tra Maven POM license metadata với upstream LICENSE/NOTICE đúng version.
- [ ] Đã dùng SPDX IDs/expressions đúng; không xem `NONE`/`NOASSERTION` là approved.
- [ ] License Maven Plugin không còn missing license metadata chưa xử lý.
- [ ] Allowlist/denylist dùng đúng license names hoặc component coordinates theo policy được duyệt.
- [ ] Đã tạo `THIRD-PARTY.txt` và review nội dung.
- [ ] Đã tạo CycloneDX BOM/SPDX document theo yêu cầu release.
- [ ] Đã giữ project LICENSE và NOTICE cần thiết trong distribution.
- [ ] Đã xác định và ship license texts/source/attribution theo obligations cụ thể.
- [ ] Đã kiểm tra base image/JRE/OS packages nếu phát hành OCI image.
- [ ] Đã có người review và bằng chứng approval cho component cần quyết định.
- [ ] Đã lưu Git revision, dependency tree, SBOM, JAR SHA-256 và image digest (nếu có).
- [ ] Publish **chính artifact bytes** đã được review.

### Tự kiểm tra

**Câu A.** POM project khai báo `Apache-2.0`. Có thể kết luận toàn bộ dependencies đều Apache-2.0 không?

**Trả lời:** Không. Khối `<licenses>` mô tả project hiện tại. Mỗi dependency có license metadata và điều khoản riêng.

**Câu B.** `mvn dependency:tree` chỉ thấy direct dependencies. Đã đủ chưa?

**Trả lời:** Chưa. Cần cả transitive dependencies và kiểm tra artifact thực tế; dùng `dependency:tree` đầy đủ, license report/SBOM và archive inspection.

**Câu C.** `MIT OR Apache-2.0` và `MIT AND Apache-2.0` giống nhau không?

**Trả lời:** Không. `OR` biểu diễn lựa chọn license; `AND` biểu diễn điều kiện phải tuân thủ cả hai.

**Câu D.** License Maven Plugin sinh `THIRD-PARTY.txt`. Đã đáp ứng mọi nghĩa vụ license chưa?

**Trả lời:** Chưa. File này là danh sách metadata; vẫn cần kiểm tra license text, NOTICE, source/attribution và điều kiện theo từng component.

**Câu E.** CycloneDX BOM của Maven có ghi hết packages trong Docker base image không?

**Trả lời:** Không. Maven BOM chủ yếu mô tả Maven project/dependencies. Container image cần inventory/SBOM riêng cho JRE, OS và layers.

**Câu F.** Một component bị Maven Enforcer `bannedDependencies` chặn. Rule có biết nó dùng GPL hay MIT không?

**Trả lời:** Không. Rule chặn coordinates/pattern của dependency. Phân tích license cần plugin/report và review riêng.

**Câu G.** `NOASSERTION` có nghĩa license đã được chấp nhận?

**Trả lời:** Không. Đó là trạng thái chưa đưa ra kết luận. Component cần được điều tra trước khi cho qua release policy.

**Câu H.** Build đã được legal review, nhưng sau đó nâng dependency patch version. Có thể dùng lại approval cũ?

**Trả lời:** Không mặc nhiên. Version mới có thể thay license, notices hoặc component set; phải re-inventory và kiểm tra release evidence tương ứng.

## 20. Tài liệu tham khảo chính thức

- SPDX — License List và identifiers: https://spdx.org/licenses/
- SPDX — License Exceptions: https://spdx.org/licenses/exceptions-index.html
- SPDX — License Expressions (AND/OR/WITH/LicenseRef): https://github.com/spdx/spdx-spec/blob/develop/docs/annexes/spdx-license-expressions.md
- SPDX — Handling License Information: https://spdx.dev/learn/handling-license-info/
- Apache Maven — Dependency Mechanism and Scopes: https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html
- Apache Maven — Dependency Plugin / dependency:tree: https://maven.apache.org/plugins/maven-dependency-plugin/usage.html
- MojoHaus — License Maven Plugin Usage: https://www.mojohaus.org/license-maven-plugin/usage.html
- MojoHaus — License Maven Plugin add-third-party goal and parameters: https://www.mojohaus.org/license-maven-plugin/add-third-party-mojo.html
- MojoHaus — Third-party license examples, missing metadata and allowlists: https://www.mojohaus.org/license-maven-plugin/examples/example-thirdparty.html
- CycloneDX — Maven Plugin documentation: https://cyclonedx.github.io/cyclonedx-maven-plugin/
- CycloneDX — Maven Plugin release history: https://github.com/CycloneDX/cyclonedx-maven-plugin/releases
- SPDX — SPDX Maven Plugin: https://spdx.github.io/spdx-maven-plugin/
- Apache Maven Enforcer — Banned Dependencies: https://maven.apache.org/components/enforcer/enforcer-rules/bannedDependencies.html
- Spring Boot — Packaging Executable Archives and repackage: https://docs.spring.io/spring-boot/3.5/maven-plugin/packaging.html
- Spring Boot — Build / executable archive packaging: https://docs.spring.io/spring-boot/3.5/how-to/build.html
- Java 17 — JarFile API: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/jar/JarFile.html

**Ghi nhớ:** Kiểm tra giấy phép phải nối được **component inventory → license evidence → obligations → approval → đúng artifact được phân phối**. Maven tree, License Maven Plugin và SBOM giúp tự động hóa việc thu thập và chặn một số lỗi; chỉ kiểm tra **sản phẩm cuối cùng**, tài liệu license/NOTICE thực tế và policy của kênh phát hành mới tạo được hồ sơ phân phối đáng tin.