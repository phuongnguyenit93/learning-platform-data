# Tạo danh mục thành phần phần mềm SBOM từ đồ thị phụ thuộc Maven

## 1. Vấn đề: build thành công không cho biết ứng dụng chứa những thành phần nào

Một ứng dụng Java thường sử dụng nhiều thư viện bên ngoài. Developer chỉ khai vài dependency trong `pom.xml` nhưng mỗi thư viện có thể kéo thêm **transitive dependencies**. Đồ thị thực sự được Maven phân giải có thể lớn hơn nhiều so với phần `<dependencies>` nhìn thấy.

Ví dụ đơn giản:

~~~text
sbom-dependency-demo (ứng dụng)
    |
    +-- jackson-databind                (khai trực tiếp)
    |     |
    |     +-- jackson-core              (bắc cầu)
    |     +-- jackson-annotations       (bắc cầu)
    |
    +-- junit-jupiter                   (test scope)
          |
          +-- các thành phần JUnit khác
~~~

Nếu muốn điều tra một thư viện bị cảnh báo bảo mật, rà soát license hoặc gửi danh mục thành phần cho đơn vị vận hành, chỉ đọc vài dòng `<dependency>` chưa đủ.

**SBOM (Software Bill of Materials)** là tài liệu có cấu trúc mô tả **các thành phần phần mềm và quan hệ phụ thuộc** trong một phạm vi sản phẩm/build được xác định. Với Maven, có thể dùng **CycloneDX Maven Plugin** để chuyển đồ thị dependency đã phân giải thành tài liệu CycloneDX dạng JSON hoặc XML. Tài liệu này có thể được lưu cùng artifact, kiểm tra bằng schema validator và chuyển cho các hệ thống phân tích an toàn chuỗi cung ứng.

Ba điều cần nhớ từ đầu:

1. **Maven dependency tree** giải thích đường đi của các phụ thuộc được Maven chọn theo scope, version mediation và cấu hình build.
2. **SBOM** là bản kê có thể trao đổi giữa các công cụ: component identity, version, package URL, thông tin nguồn/license nếu có, cùng các quan hệ `dependsOn`.
3. **SBOM không tự động là vulnerability scan.** Một file BOM hợp lệ có thể không chứa bất kỳ nhận định CVE nào; cần hệ thống dữ liệu advisory, chính sách và phân tích riêng để xác định rủi ro.

### Mục tiêu bài học

Sau bài này, bạn có thể:

- Giải thích khác biệt giữa SBOM và Maven BOM dùng trong `dependencyManagement`.
- Tìm direct/transitive dependencies bằng `mvn dependency:tree`.
- Phân tích graph theo `groupId`, `artifactId`, `version`, `scope` và các quy tắc mediation.
- Cấu hình CycloneDX Maven Plugin **2.9.3**, tạo SBOM **CycloneDX 1.6** JSON/XML từ dự án Maven.
- Hiểu `makeBom`, `makeAggregateBom` và `makePackageBom`.
- Kiểm tra `components`, `dependencies`, `bom-ref`, `purl`, `metadata.component` trong SBOM.
- Quyết định có đưa compile, runtime, provided, system và test scopes vào inventory hay không.
- Tạo dự án Java 17/JUnit 5 runnable để thấy một dependency trực tiếp kéo theo dependencies bắc cầu.
- Xác minh tính hợp lệ của JSON, validate theo CycloneDX schema và thiết kế quality gate CI.
- Phân biệt SBOM tại source/build time với thực tế của fat JAR, container, native artifacts hoặc môi trường chạy.
- Gắn SBOM đúng với source commit, artifact version, release và xử lý vòng đời cập nhật.
- Biết các giới hạn dữ liệu về license, vulnerabilities, private dependencies và reproducibility.

Bài dùng Maven **3.9.x**, Java **17+**, CycloneDX Maven Plugin **2.9.3**, schema **1.6**, Maven Dependency Plugin **3.10.0**, Compiler Plugin **3.14.1**, Surefire **3.5.4**, JAR Plugin **3.4.2**, Exec Plugin **3.6.4**, Jackson Databind **2.18.3** và JUnit Jupiter **5.11.4**. Đây là phiên bản **minh họa được ghim** để thực hành; không phải khuyến nghị mọi ứng dụng production giữ mãi những version này. Khi đưa vào sản phẩm thực, phải rà soát bản vá và policy hiện hành.

---

## 2. SBOM chứa gì và có ích ở đâu?

Một SBOM hữu ích cần trả lời được các câu hỏi:

- Sản phẩm/thành phần gốc được mô tả là gì? Phiên bản nào?
- Các thư viện third-party và first-party nào nằm trong phạm vi?
- Từng component có tọa độ nhận diện nào, chẳng hạn Maven GAV?
- Component A phụ thuộc trực tiếp vào B hay C?
- B kéo thêm thư viện nào; đường đi tới một package đáng quan tâm là gì?
- License/source/hashes có được công bố hoặc xác minh không?
- Tài liệu được tạo bằng tool nào, trong build/source revision nào, thời điểm nào?
- Phạm vi danh mục có bao gồm test tools, container OS packages hoặc native libraries không?

Với CycloneDX JSON, các trường phổ biến:

| Trường | Chức năng |
| --- | --- |
| `bomFormat` | Loại tài liệu, thường `CycloneDX` |
| `specVersion` | Phiên bản CycloneDX schema, ví dụ `1.6` |
| `version` | Số thứ tự sửa đổi của tài liệu SBOM, không phải Maven project version |
| `serialNumber` | Định danh tài liệu khi có, khác Maven version |
| `metadata` | Metadata về công cụ tạo, timestamp, component được mô tả |
| `metadata.component` | Sản phẩm/project mà SBOM đang mô tả |
| `components` | Các component được liệt kê |
| `components[].group` | Group/name namespace khi có |
| `components[].name` | Tên artifact hoặc component |
| `components[].version` | Version của component |
| `components[].purl` | Package URL định danh package |
| `components[].bom-ref` | Định danh dùng để tham chiếu trong tài liệu |
| `dependencies` | Các cạnh trong đồ thị phụ thuộc |
| `dependencies[].ref` | Node nguồn của quan hệ |
| `dependencies[].dependsOn` | Danh sách nodes mà nguồn phụ thuộc |

Không phải mọi component đều có đủ hash, license text, supplier hoặc external references. **Thiếu trường không có nghĩa component không tồn tại; cần đánh giá chất lượng metadata và tính đầy đủ.**

### 2.1. Dùng SBOM cho những quy trình nào?

Một số use cases:

- **Inventory:** biết sản phẩm sử dụng những thư viện nào.
- **Incident response:** khi có advisory mới, truy tìm những releases có liên quan tới một package/version.
- **License review:** lập danh mục ban đầu để kiểm tra nghĩa vụ license, sau đó vẫn cần bằng chứng pháp lý và kiểm tra thực tế.
- **Supplier exchange:** giao một danh sách có định dạng máy đọc được cho khách hàng/đối tác.
- **Release traceability:** lưu SBOM cùng build artifact và commit.
- **Policy gate:** phát hiện thiếu purl, sai schema hoặc thiếu những thành phần bắt buộc.
- **Vulnerability management:** nạp SBOM vào công cụ phân tích bảo mật để đối chiếu advisories, exposure và mức độ ảnh hưởng.

**Chú ý:** CycloneDX còn hỗ trợ thông tin vulnerability/VEX và nhiều loại BOM khác. Tuy vậy **plugin sinh SBOM từ Maven dependency graph** không tự khám phá mọi lỗ hổng và không thể tự khẳng định thành phần có khai thác được hay không.

---

## 3. SBOM khác Maven BOM trong dependencyManagement

Đây là hai khái niệm có cùng chữ “BOM” nhưng **mục đích khác nhau**.

### Maven BOM (Bill of Materials dùng quản lý version)

Trong Maven, một POM có `packaging=pom` có thể công bố tập versions tập trung. Project khác import nó vào `dependencyManagement`:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>vn.example.platform</groupId>
            <artifactId>company-dependencies</artifactId>
            <version>1.0.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Đây là **snippet minh họa về cú pháp import**. Tọa độ `vn.example.platform:company-dependencies:1.0.0` chỉ là ví dụ, không khẳng định artifact này tồn tại trên Maven Central.

Maven BOM này giúp **quản lý phiên bản** khi dependencies được khai. Một version nằm trong `dependencyManagement` **không tự tạo dependency edge** nếu project không thực sự khai dependency đó. Không được coi tất cả artifact được quản lý trong BOM version platform đều đã được ứng dụng sử dụng.

### SBOM để inventory thành phần phần mềm

CycloneDX SBOM là tài liệu về **những thành phần của build/sản phẩm trong phạm vi đã chọn**, được sinh từ kết quả Maven resolution, cộng metadata quan hệ.

Ví dụ:

~~~text
Maven dependencyManagement BOM:
    quy định jackson-databind -> version X
    quy định một thư viện khác -> version Y

Actual resolved Maven graph:
    ứng dụng -> jackson-databind X -> jackson-core ...
    (thư viện Y không được dùng)

CycloneDX SBOM:
    ứng dụng + jackson-databind X + jackson-core + ...
    không tự thêm Y chỉ vì Y có trong dependencyManagement
~~~

**Quy tắc nhớ nhanh:** Maven BOM đặt **policy phiên bản**; SBOM ghi **inventory/quan hệ thành phần**. Chúng bổ sung, không thay nhau.

---

## 4. Maven resolution quyết định đồ thị đầu vào

Không thể tạo SBOM đúng phạm vi nếu chưa hiểu những gì Maven thực sự resolve.

### 4.1. Direct và transitive dependencies

Trong ứng dụng ví dụ, POM khai:

~~~xml
<dependency>
    <groupId>com.fasterxml.jackson.core</groupId>
    <artifactId>jackson-databind</artifactId>
    <version>2.18.3</version>
</dependency>
~~~

Đây là **dependency trực tiếp**. Jackson Databind cần các thư viện Jackson Core và Jackson Annotations phù hợp, Maven sẽ phân giải qua POM của dependency.

Đồ thị rút gọn:

~~~text
sbom-dependency-demo:1.0.0
    |
    +-- jackson-databind:2.18.3        direct compile
          |
          +-- jackson-core:2.18.3     transitive compile
          +-- jackson-annotations:2.18.3
                                       transitive compile
~~~

Đây là hình minh họa nhóm Jackson của ví dụ đã ghim, không phải toàn bộ log dependency tree. Đồ thị thực tế còn JUnit ở test scope và có thể các node khác theo resolution.

### 4.2. Version mediation

Nếu hai nhánh kéo cùng `groupId:artifactId` nhưng version khác nhau, Maven có quy tắc chọn version, thường dựa vào **nearest definition** và khi ngang khoảng cách có thứ tự khai báo ảnh hưởng. `dependencyManagement` có thể quản lý version được chọn.

SBOM phải phản ánh **version thực được resolve**, không chỉ tất cả versions có mặt dưới `dependencyManagement` hay tất cả những nhánh bị bỏ qua do conflict.

### 4.3. Optional, exclusions và scopes

- `optional=true` trong một dependency có tác động tới việc propagate dependency tới consumers.
- `<exclusions>` có thể loại transitive artifact khỏi một nhánh.
- Scope `test` thường chỉ phục vụ tests, không nhất thiết ship vào runtime.
- Scope `provided` thường do container/JDK hoặc môi trường chạy cung cấp, vẫn quan trọng cho một số inventory.
- Scope `runtime` có thể không cần lúc compile nhưng được dùng khi chạy.
- Scope `system` gắn với local path và có rủi ro tái lập/metadata; Maven không khuyến nghị lạm dụng.

SBOM được sinh theo **Maven effective model**, dependency mediation và **scope flags của plugin**. Không đơn giản là dump mọi khai báo `<dependency>` trong POM.

### 4.4. Profiles và môi trường

Một profile có thể thêm hoặc thay dependencies. Lệnh:

~~~bash
mvn -Pproduction clean verify
~~~

chỉ có ý nghĩa khi project thực sự định nghĩa profile `production`. Hai builds bật profiles khác nhau có thể tạo SBOM khác, dù source giống nhau. Vì vậy trong CI nên ghi **active profiles**, Maven/JDK versions và resolved graph.

### 4.5. Module reactor

Trong multi-module Maven:

~~~text
parent
  |
  +-- common-lib
  |
  +-- api-service --> common-lib
~~~

`common-lib` là **first-party component** của cùng reactor, không phải một artifact “có thể bỏ qua vì do công ty viết”. SBOM tổng hợp cần bao phủ module app cùng những thành phần first-party và third-party liên quan theo scope.

---

## 5. Xem đồ thị Maven trước khi sinh SBOM

Maven Dependency Plugin cung cấp `dependency:tree` để quan sát resolved dependency hierarchy:

~~~bash
mvn dependency:tree
~~~

Để tránh plugin version drift, bài sẽ ghim `maven-dependency-plugin` **3.10.0** trong POM runnable.

Lọc nhóm Jackson:

~~~bash
mvn dependency:tree -Dincludes=com.fasterxml.jackson.core
~~~

Ghi JSON dependency tree:

~~~bash
mvn dependency:tree -DoutputType=json -DoutputFile=target/dependency-tree.json
~~~

Tài liệu Dependency Plugin 3.7.0 trở lên hỗ trợ các output formats `text`, `dot`, `graphml`, `tgf` và `json`. File `dependency-tree.json` là **đồ thị Maven**, không phải CycloneDX SBOM. Hai tài liệu đều hữu ích nhưng có schema và mục đích khác nhau.

### 5.1. Một đoạn kết quả minh họa

~~~text
vn.example:sbom-dependency-demo:jar:1.0.0
+- com.fasterxml.jackson.core:jackson-databind:jar:2.18.3:compile
|  +- com.fasterxml.jackson.core:jackson-annotations:jar:2.18.3:compile
|  \- com.fasterxml.jackson.core:jackson-core:jar:2.18.3:compile
\- org.junit.jupiter:junit-jupiter:jar:5.11.4:test
   \- ... các dependencies của JUnit (lược bớt)
~~~

Đây là **hình minh họa rút gọn**, không phải bản sao log Maven nguyên văn hay một JSON file. Đặc biệt, `junit-jupiter` sẽ kéo thêm JUnit components, và thứ tự/danh sách chính xác phải đọc từ `dependency:tree` của build thật.

### 5.2. Khi thấy nhiều versions trong logs

Đừng copy tất cả versions được Maven xem xét vào SBOM thủ công. Hãy xác định version được chọn sau mediation, scope đang active và những exclusions. Phần dependency tree có thể ẩn/hiển thị omitted nodes tùy flag; một node “omitted for conflict” không tự động là runtime component của artifact đã build.

---

## 6. CycloneDX Maven Plugin: chọn bản và schema tương thích

Tài liệu dự án CycloneDX định nghĩa plugin:

~~~text
groupId:    org.cyclonedx
artifactId: cyclonedx-maven-plugin
version:    2.9.3
~~~

Bài chọn bản phát hành **2.9.3**, tạo tài liệu **CycloneDX 1.6** với cấu hình tường minh:

~~~xml
<schemaVersion>1.6</schemaVersion>
~~~

Điểm dễ nhầm: site tài liệu được cập nhật theo nhánh phát triển đôi khi hiện các giá trị cho **2.10.0-SNAPSHOT / CycloneDX 1.7**. Không nên copy default schema 1.7 của tài liệu SNAPSHOT rồi ghép vào plugin **2.9.3**, vì dòng **2.9.x hỗ trợ CycloneDX 1.6**. Chọn plugin và schema theo khả năng hệ thống nhận SBOM của bạn.

### 6.1. Ba goals chính

| Goal | Dùng khi nào? | Kết quả |
| --- | --- | --- |
| `cyclonedx:makeBom` | Một Maven module hoặc muốn mỗi module một BOM | BOM cho module và dependencies của nó |
| `cyclonedx:makeAggregateBom` | Multi-module reactor | Một BOM aggregate tại root và có thể module BOMs |
| `cyclonedx:makePackageBom` | Dự án packaging `war` hoặc `ear` | BOM cho module/package theo mục tiêu plugin |

Đừng tự đoán `makePackageBom` phù hợp với mọi `jar`. Với bài single-module JAR, dùng **`makeBom`**.

### 6.2. Thông số quan trọng

| Option | Ý nghĩa | Giá trị bài mẫu / mặc định cần biết |
| --- | --- | --- |
| `schemaVersion` | CycloneDX schema | Bài đặt `1.6` với plugin 2.9.3 |
| `outputFormat` | `json`, `xml` hoặc `all` | Bài đặt `all` |
| `outputName` | Tên file không gồm phần mở rộng | `bom` |
| `outputDirectory` | Thư mục file SBOM | Mặc định `${project.build.directory}` = thường là `target` |
| `includeCompileScope` | Include compile dependencies | Mặc định `true` |
| `includeRuntimeScope` | Include runtime dependencies | Mặc định `true` |
| `includeProvidedScope` | Include provided dependencies | Mặc định `true` |
| `includeSystemScope` | Include system dependencies | Mặc định `true` |
| `includeTestScope` | Include test dependencies | Mặc định **`false`** |
| `includeLicenseText` | Có nhúng văn bản license khi có | Mặc định `false` |
| `outputReactorProjects` | Có sinh BOM riêng cho non-root modules không | Mặc định `true` |
| `skipAttach` | Không attach SBOM vào artifact published | Mặc định `false` |
| `skip` / `cyclonedx.skip` | Bỏ qua plugin execution | Mặc định `false` |

Một **default quan trọng**: `includeProvidedScope=true` nhưng `includeTestScope=false`. Vì vậy **cần mô tả rõ loại inventory**: bạn muốn bản kê dependencies liên quan runtime hay cả build/test environment?

### 6.3. File output

Với `outputFormat=all` và `outputName=bom`, single-module demo tạo thông thường:

~~~text
target/bom.json
target/bom.xml
~~~

Đây là **files nội bộ trong build output directory**, không phải JAR app. Chỉ vì file SBOM nằm ở `target` không có nghĩa nó đã được gửi tới repository hoặc nằm trong main JAR.

Theo plugin docs, BOM có thể được attach với classifier `cyclonedx` khi chạy `install`/`deploy`, ví dụ:

~~~text
sbom-dependency-demo-1.0.0-cyclonedx.json
sbom-dependency-demo-1.0.0-cyclonedx.xml
~~~

Đó là **tên attached artifact khi được publish** trong repository, không phải cùng tên `target/bom.json`. Nếu chỉ chạy `mvn verify`, bạn mới kiểm được **file sinh tại build**, chưa chứng minh đã publish SBOM.

### 6.4. Có cần online không?

Goal CycloneDX Maven Plugin được tài liệu đánh dấu **requires online mode**. Đừng mặc nhiên `mvn -o cyclonedx:makeBom` hoạt động như lệnh build thuần local cache. Nếu gặp lỗi resolution hoặc offline, cần đọc log và đảm bảo môi trường/repository phù hợp; không suy ra plugin tạo SBOM sai chỉ vì CI bị chặn mạng.

---

## 7. Dự án Java 17 runnable có dependency bắc cầu

Dựng đúng ba file:

~~~text
sbom-dependency-demo/
├── pom.xml
└── src/
    ├── main/java/vn/example/sbom/App.java
    └── test/java/vn/example/sbom/AppTest.java
~~~

Tại `pom.xml`, khai Jackson Databind là direct compile dependency; Jackson Core và Annotations được Maven phân giải qua POM của nó. JUnit Jupiter là test dependency.

### 7.1. POM hoàn chỉnh

File `sbom-dependency-demo/pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>vn.example</groupId>
    <artifactId>sbom-dependency-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>com.fasterxml.jackson.core</groupId>
            <artifactId>jackson-databind</artifactId>
            <version>2.18.3</version>
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
                <version>3.14.1</version>
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
                <configuration>
                    <archive>
                        <manifest>
                            <mainClass>vn.example.sbom.App</mainClass>
                        </manifest>
                    </archive>
                </configuration>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-dependency-plugin</artifactId>
                <version>3.10.0</version>
            </plugin>

            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.6.4</version>
            </plugin>

            <plugin>
                <groupId>org.cyclonedx</groupId>
                <artifactId>cyclonedx-maven-plugin</artifactId>
                <version>2.9.3</version>
                <executions>
                    <execution>
                        <id>generate-sbom</id>
                        <phase>package</phase>
                        <goals>
                            <goal>makeBom</goal>
                        </goals>
                    </execution>
                </executions>
                <configuration>
                    <schemaVersion>1.6</schemaVersion>
                    <projectType>application</projectType>
                    <outputFormat>all</outputFormat>
                    <outputName>bom</outputName>
                    <includeCompileScope>true</includeCompileScope>
                    <includeRuntimeScope>true</includeRuntimeScope>
                    <includeProvidedScope>true</includeProvidedScope>
                    <includeSystemScope>true</includeSystemScope>
                    <includeTestScope>false</includeTestScope>
                    <skipAttach>false</skipAttach>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Đây là **POM độc lập đầy đủ**, không phải một đoạn cần tự chèn vào dự án khác. Plugin `makeBom` bind ở phase `package` nên lệnh `mvn clean verify` đi qua phase này và tạo SBOM.

#### Giải thích các lựa chọn

- **Jackson Databind** 2.18.3 giúp demo có một dependency trực tiếp và transitives rõ.
- **JUnit Jupiter** 5.11.4 ở `test` scope minh họa việc dependency tree và SBOM có thể bao phủ những scopes khác nhau.
- **Maven Compiler Plugin** 3.14.1 với release17 biên dịch Java17.
- **Maven Surefire Plugin** 3.5.4 chạy JUnit Jupiter tests.
- **Maven JAR Plugin** 3.4.2 khai main class để dễ nhận diện artifact, nhưng **chưa tạo fat JAR**.
- **Maven Dependency Plugin** 3.10.0 hỗ trợ xuất dependency graph dạng text/JSON.
- **Exec Maven Plugin** 3.6.4 chạy main với runtime dependencies đúng Maven classpath, không cần đoán đường dẫn `~/.m2`.
- **CycloneDX Maven Plugin** 2.9.3 tạo schema1.6, JSON/XML, file tên `bom`.
- `includeTestScope=false` làm inventory bài mẫu ưu tiên dependencies compile/runtime/provided/system; JUnit dùng để test **không cần có trong danh sách components của SBOM mặc định**. Nếu muốn kiểm kê tool/test dependencies, bật true theo policy.

Không coi Jackson 2.18.3 là một gợi ý version mới/an toàn cho production; nó là **fixture kiến thức**, nên hệ thống thật vẫn cần update/security review.

### 7.2. App.java

File `src/main/java/vn/example/sbom/App.java`:

~~~java
package vn.example.sbom;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

public final class App {
    private App() {
    }

    public static String status(String json) {
        try {
            JsonNode root = new ObjectMapper().readTree(json);
            return root.path("status").asText();
        } catch (JsonProcessingException error) {
            throw new IllegalArgumentException("Invalid JSON", error);
        }
    }

    public static void main(String[] args) {
        System.out.println(
                "SBOM DEMO: " + status("{\"status\":\"OK\"}")
        );
    }
}
~~~

Code dùng thực sự lớp `ObjectMapper` và `JsonNode` từ Jackson. Vì vậy dependency Jackson Databind **không phải một dependency khai nhưng không dùng**.

### 7.3. AppTest.java

File `src/test/java/vn/example/sbom/AppTest.java`:

~~~java
package vn.example.sbom;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class AppTest {
    @Test
    void readsStatusFromJson() {
        assertEquals("OK", App.status("{\"status\":\"OK\"}"));
    }

    @Test
    void rejectsMalformedJson() {
        assertThrows(
                IllegalArgumentException.class,
                () -> App.status("{broken")
        );
    }
}
~~~

Có **2 JUnit tests**:

- `readsStatusFromJson` xác nhận Jackson đọc đúng JSON.
- `rejectsMalformedJson` xác nhận input sai được chuyển thành `IllegalArgumentException` có nguyên nhân Java/Jackson.

Không có test nào kiểm tra “thư viện không có CVE”. Unit tests cho behavior, còn SBOM phục vụ inventory.

---

## 8. Chạy build và sinh SBOM

Tại thư mục `sbom-dependency-demo`:

~~~bash
mvn -version
java -version
mvn -B -ntp clean verify
~~~

Nếu Maven 3.9.x, JDK17+, dependencies/plugins được resolve và source đúng, kết quả mong đợi:

~~~text
Tests run: 2, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
~~~

Và các files chính:

~~~text
target/sbom-dependency-demo-1.0.0.jar
target/bom.json
target/bom.xml
target/surefire-reports/TEST-vn.example.sbom.AppTest.xml
~~~

**Đây là kết quả kỳ vọng từ project mẫu**, không phải tuyên bố đã thực thi Maven build trên môi trường người đọc. Nội dung exact hash/serialNumber/timestamp của SBOM không được bịa vì phải lấy từ file thật.

### 8.1. Chạy ứng dụng với Maven-managed classpath

Do main JAR **không nhúng Jackson dependencies**, chỉ gọi:

~~~bash
java -jar target/sbom-dependency-demo-1.0.0.jar
~~~

có thể dẫn tới `NoClassDefFoundError` khi JVM thiếu Jackson trên runtime classpath. Điều đó không có nghĩa JAR/SBOM tạo lỗi; đó là khác biệt giữa **thin JAR** và **fat JAR**.

Dùng Exec Plugin đã ghim trong POM:

~~~bash
mvn -q -Dexec.mainClass=vn.example.sbom.App exec:java
~~~

Khi Maven/plugin và runtime classpath hợp lệ, stdout từ **main Java** chính xác:

~~~text
SBOM DEMO: OK
~~~

Lệnh Maven có thể in log tùy option/version; dòng trên chỉ nói stdout của `App.main`. Đối với deploy thực, phải cung cấp các runtime JARs/packaging launcher tương ứng, hoặc sử dụng plugin tạo executable distribution được quản lý riêng.

### 8.2. Xem dependency graph

~~~bash
mvn -B -ntp dependency:tree
~~~

Nếu muốn tập trung Jackson:

~~~bash
mvn -B -ntp dependency:tree -Dincludes=com.fasterxml.jackson.core
~~~

Có thể xuất JSON:

~~~bash
mvn -B -ntp dependency:tree \
    -DoutputType=json \
    -DoutputFile=target/dependency-tree.json
~~~

Lệnh cuối là cú pháp Bash với ký tự `\` xuống dòng. Trong PowerShell/CMD, viết lệnh trên **một dòng** hoặc dùng ký tự nối dòng đúng shell:

~~~text
mvn -B -ntp dependency:tree -DoutputType=json -DoutputFile=target/dependency-tree.json
~~~

Đây là **lệnh text để sao chép**, không phải JSON content. `target/dependency-tree.json` do Dependency Plugin tạo, khác `target/bom.json` của CycloneDX.

### 8.3. Sinh riêng bằng fully qualified goal

Vì POM đã có plugin execution bound `package`, `mvn clean verify` tạo SBOM. Nếu chỉ muốn gọi goal độc lập mà không chạy toàn lifecycle:

~~~bash
mvn org.cyclonedx:cyclonedx-maven-plugin:2.9.3:makeBom
~~~

Điều này có thể resolve dependency graph và tạo SBOM nhưng **không chứng minh compile/test/package đã pass**. Trong CI nên giữ sequence build/verify và kiểm tra files thật, không thay tất cả tests bằng một goal tạo tài liệu.

---

## 9. Đọc bom.json: cấu trúc CycloneDX

Một bản CycloneDX JSON thực có metadata tools, serial number, components, dependency references và nhiều chi tiết khác. Dưới đây là **JSON rút gọn minh họa cấu trúc**, **không phải output nguyên văn của plugin**:

~~~json
{
  "bomFormat": "CycloneDX",
  "specVersion": "1.6",
  "version": 1,
  "metadata": {
    "component": {
      "type": "application",
      "bom-ref": "pkg:maven/vn.example/sbom-dependency-demo@1.0.0",
      "name": "sbom-dependency-demo",
      "version": "1.0.0",
      "purl": "pkg:maven/vn.example/sbom-dependency-demo@1.0.0"
    }
  },
  "components": [
    {
      "type": "library",
      "group": "com.fasterxml.jackson.core",
      "name": "jackson-databind",
      "version": "2.18.3",
      "bom-ref": "pkg:maven/com.fasterxml.jackson.core/jackson-databind@2.18.3",
      "purl": "pkg:maven/com.fasterxml.jackson.core/jackson-databind@2.18.3"
    },
    {
      "type": "library",
      "group": "com.fasterxml.jackson.core",
      "name": "jackson-core",
      "version": "2.18.3",
      "bom-ref": "pkg:maven/com.fasterxml.jackson.core/jackson-core@2.18.3",
      "purl": "pkg:maven/com.fasterxml.jackson.core/jackson-core@2.18.3"
    },
    {
      "type": "library",
      "group": "com.fasterxml.jackson.core",
      "name": "jackson-annotations",
      "version": "2.18.3",
      "bom-ref": "pkg:maven/com.fasterxml.jackson.core/jackson-annotations@2.18.3",
      "purl": "pkg:maven/com.fasterxml.jackson.core/jackson-annotations@2.18.3"
    }
  ],
  "dependencies": [
    {
      "ref": "pkg:maven/vn.example/sbom-dependency-demo@1.0.0",
      "dependsOn": [
        "pkg:maven/com.fasterxml.jackson.core/jackson-databind@2.18.3"
      ]
    },
    {
      "ref": "pkg:maven/com.fasterxml.jackson.core/jackson-databind@2.18.3",
      "dependsOn": [
        "pkg:maven/com.fasterxml.jackson.core/jackson-core@2.18.3",
        "pkg:maven/com.fasterxml.jackson.core/jackson-annotations@2.18.3"
      ]
    },
    {
      "ref": "pkg:maven/com.fasterxml.jackson.core/jackson-core@2.18.3",
      "dependsOn": []
    },
    {
      "ref": "pkg:maven/com.fasterxml.jackson.core/jackson-annotations@2.18.3",
      "dependsOn": []
    }
  ]
}
~~~

Mẫu chỉ trình bày ba thành phần Jackson để giải thích graph và bỏ qua những trường tùy chọn. Trong output thật, thứ tự elements/fields, identifier format, metadata, hashes, serialNumber và các nodes sẽ do CycloneDX Plugin quyết định. Không “sửa” file thật thành đúng y JSON trên nếu nó có thêm metadata hợp lệ.

### 9.1. bom-ref không phải GAV bắt buộc

`bom-ref` là identifier **duy nhất bên trong một BOM**, dùng để tham chiếu các nodes từ `dependencies` hoặc dữ liệu liên quan. Package URL (*purl*) là cách biểu diễn dễ đọc và có khả năng định danh Maven package, ví dụ:

~~~text
pkg:maven/com.fasterxml.jackson.core/jackson-databind@2.18.3
~~~

Nhưng không phải mọi `bom-ref` bắt buộc bằng purl; generator có thể dùng identifier khác. Một consumer phải tuân theo **reference thực** trong file thay vì tự dựng `bom-ref` rồi giả định tương đương.

### 9.2. Component inventory và dependency edges là hai phần khác

`components[]` liệt kê package metadata. `dependencies[]` mô tả **quan hệ**, ví dụ root phụ thuộc Databind, Databind phụ thuộc Core và Annotations.

Nếu chỉ xem danh sách components, bạn biết package có mặt nhưng chưa biết **đường đi nào đưa nó vào ứng dụng**. Khi điều tra CVE ở một transitively included library, graph edges giúp xác định upstream component cần nâng cấp hoặc loại trừ.

### 9.3. Metadata không phải bằng chứng bảo mật tự thân

Một component có `purl` hợp lệ vẫn có thể có vulnerability; một component có license name chưa chắc đã được review legal. Nếu plugin chỉ nhận metadata từ POM/repository, dữ liệu sai hoặc thiếu ở nguồn có thể truyền vào SBOM.

---

## 10. Kiểm tra SBOM đã sinh ra

### 10.1. JSON syntax

Nếu máy có Python 3:

~~~bash
python3 -m json.tool target/bom.json > /dev/null
~~~

Mã thoát `0` nghĩa JSON **đọc được về mặt cú pháp**. Nó **chưa chứng minh file đáp ứng CycloneDX 1.6 schema** hoặc graph có đầy đủ components.

Trên Windows PowerShell:

~~~powershell
Get-Content -Raw target/bom.json | ConvertFrom-Json | Out-Null
~~~

Nếu parser không báo lỗi, JSON syntax đã hợp lệ; vẫn cần schema/content checks.

### 10.2. Kiểm tra những trường căn bản bằng jq

Khi đã cài `jq`:

~~~bash
jq -e '.bomFormat == "CycloneDX" and .specVersion == "1.6"' target/bom.json
~~~

Nếu tài liệu có đúng hai trường, lệnh in:

~~~text
true
~~~

và thường exit `0`. Để xem các packages Jackson:

~~~bash
jq -r '.components[]
  | select(.group == "com.fasterxml.jackson.core")
  | [.name, .version]
  | @tsv' target/bom.json
~~~

Kỳ vọng nhận diện các tên `jackson-databind`, `jackson-core` và `jackson-annotations` nếu plugin/resolver và include flags của ví dụ hoạt động như dự kiến. **Không dự đoán thứ tự dòng** hoặc số component tổng khi chưa đọc file thực.

Kiểm tra có Databind:

~~~bash
jq -e '[.components[] | select(.name == "jackson-databind")] | length >= 1' target/bom.json
~~~

Câu lệnh này giúp gate một điều kiện inventory rất cụ thể. Nhưng chỉ nó **không đủ** bảo đảm mỗi ref/dependsOn hợp lệ hoặc không thiếu các dependencies khác.

### 10.3. Schema validation bằng CycloneDX CLI

Nếu máy hoặc CI runner **đã cài CycloneDX CLI**:

~~~bash
cyclonedx validate \
    --input-file target/bom.json \
    --input-format json \
    --input-version v1_6 \
    --fail-on-errors
~~~

Đây là command của **CycloneDX CLI bên ngoài Maven**, không tự xuất hiện khi cài Maven hoặc CycloneDX Maven Plugin. `--input-version v1_6` là điểm quan trọng: bài xuất CycloneDX **1.6**, nên không dùng schema default 1.7 của bản CLI mới nếu không nêu version.

`--fail-on-errors` yêu cầu validator trả nonzero khi schema errors, giúp CI xử lý. Schema-valid vẫn chưa đồng nghĩa component completeness, license accuracy, vulnerability-free hoặc deployment healthy.

### 10.4. Kiểm tra XML

File `target/bom.xml` cũng được tạo vì `outputFormat=all`. Có thể dùng CycloneDX CLI với `--input-format xml` và `--input-version v1_6`. Không so JSON và XML bằng SHA-256; chúng là hai serializations khác nhau của cùng kiểu dữ liệu, **không thể byte-identical** vì format khác nhau.

### 10.5. Luôn kiểm tra file thuộc invocation hiện tại

Một file `target/bom.json` từ lần build cũ có thể khiến script báo nhầm nếu bạn bỏ `clean` và goal SBOM đã bị skip. Trong CI:

- Chạy build sạch hoặc dùng fresh workspace.
- Kiểm tra Maven exit code của đúng invocation.
- Xác nhận CycloneDX goal thực sự chạy.
- Kiểm tra existence/file size và parse/schema/semantic fields.
- Lưu file cùng source SHA và artifact version.

---

## 11. Scope: vì sao JUnit không xuất hiện trong SBOM mặc định?

Trong POM:

~~~xml
<dependency>
    <groupId>org.junit.jupiter</groupId>
    <artifactId>junit-jupiter</artifactId>
    <version>5.11.4</version>
    <scope>test</scope>
</dependency>
~~~

`mvn dependency:tree` sẽ cho thấy JUnit ở test scope. Tuy nhiên bài đặt:

~~~xml
<includeTestScope>false</includeTestScope>
~~~

nên **JUnit và các dependencies chỉ thuộc test scope không nhất thiết nằm trong BOM generated**. Không được xem sự vắng mặt này là “Maven quên một dependency”; đó là **chính sách coverage** được cấu hình.

### 11.1. Hai kiểu inventory thường gặp

**Runtime-focused SBOM:**

- Tập trung components cần cho build artifact/runtime.
- Có thể loại `test` scope.
- Vẫn phải hiểu `provided` có nằm trong runtime/container hay không.
- Trong fat JAR hoặc container image, cần xác minh thành phần thực tế packaged.

**Build/test environment inventory:**

- Muốn theo dõi cả JUnit, testing tools hoặc dependencies của pipeline.
- Có thể bật `includeTestScope=true`.
- Nếu cần inventory toolchain/OS/packages, Maven dependencies một mình vẫn chưa đủ.

### 11.2. Thử bật test scope

Trong **bản sao bài thực hành**, đổi:

~~~xml
<includeTestScope>true</includeTestScope>
~~~

rồi build lại. So sánh `target/bom.json` và tìm JUnit components. Không tự kết luận rằng mọi thứ mới xuất hiện là runtime dependency của app. Scope của Maven và ý nghĩa “có mặt trong sản phẩm ship cho khách hàng” phải được giải thích cẩn thận.

### 11.3. Provided và system scope

Theo thông số plugin 2.9.3, `includeProvidedScope` và `includeSystemScope` mặc định là `true`. Điều này tăng khả năng inventory components liên quan build nhưng không nhất thiết được đóng gói trong JAR.

Một example: dependency servlet API có scope `provided` trong một WAR có thể được application server cung cấp lúc chạy. Để hiểu **deployment image** thực sự gồm gì, cần kiểm kê cả runtime platform và artifacts đã đóng gói, không chỉ SBOM Maven.

---

## 12. SBOM trong reactor multi-module

Một dự án lớn:

~~~text
platform-parent/
├── pom.xml                 packaging pom
├── model-core/
│   └── pom.xml             library
└── api-app/
    └── pom.xml             depends on model-core
~~~

Ngoài dependencies bên ngoài, còn quan hệ first-party:

~~~text
api-app --> model-core --> third-party library
~~~

Nếu chỉ chạy `makeBom` cho `api-app`, bạn thấy một tập dependency ở module đó; nếu cần **inventory toàn bộ reactor/release**, dùng `makeAggregateBom`.

### 12.1. Lệnh tạo aggregate BOM

Tại root reactor đã cấu hình các modules hợp lệ:

~~~bash
mvn -B -ntp org.cyclonedx:cyclonedx-maven-plugin:2.9.3:makeAggregateBom
~~~

Lệnh gọi fully qualified goal để tránh sử dụng bản plugin không được pin. Goal aggregate tạo SBOM ở root với dependencies của nhiều modules, và theo option `outputReactorProjects` có thể tạo BOM riêng cho từng module.

**Đây là lệnh dành cho một reactor tồn tại**, không phải command chạy trong single-module demo để minh họa nhiều modules. Trong single-module demo, `makeBom` là goal phù hợp.

### 12.2. Bind vào lifecycle cho multi-module

Trong root parent POM, có thể dùng **snippet cấu hình plugin** sau; phải đặt vào `<build><plugins>` của POM có reactor modules:

~~~xml
<plugin>
    <groupId>org.cyclonedx</groupId>
    <artifactId>cyclonedx-maven-plugin</artifactId>
    <version>2.9.3</version>
    <executions>
        <execution>
            <id>generate-reactor-sbom</id>
            <phase>package</phase>
            <goals>
                <goal>makeAggregateBom</goal>
            </goals>
        </execution>
    </executions>
    <configuration>
        <schemaVersion>1.6</schemaVersion>
        <outputFormat>all</outputFormat>
        <outputName>bom</outputName>
        <outputReactorProjects>true</outputReactorProjects>
        <includeTestScope>false</includeTestScope>
    </configuration>
</plugin>
~~~

`makeAggregateBom` là **aggregator goal**, không giống như một goal test/compile độc lập chỉ xử lý current module. Khi đưa vào parent, kiểm tra effective POM, inheritance và reactor execution thực tế; không được tự tạo hai aggregate executions vô tình làm BOM bị ghi nhiều lần.

### 12.3. outputReactorProjects

- `true`: theo tài liệu plugin, cho phép non-root reactor modules có BOM riêng.
- `false`: có thể dùng khi chỉ muốn aggregate output, theo hành vi goal/version cụ thể.

Chọn chế độ theo nhu cầu consumers. Một hệ thống có thể cần cả **root aggregate BOM** cho release và **per-module SBOM** cho từng artifact riêng.

### 12.4. Chọn một phần reactor

~~~bash
mvn -pl :api-app -am verify
~~~

là command ví dụ cho reactor có module `api-app` và dependency `model-core`. Nó **không chứng minh mọi module trong repository** đã được kiểm chứng hoặc nằm trong SBOM của release đầy đủ.

Khi CI dùng `-pl`/`-am`/`-amd`, phải kiểm tra phạm vi thực sự được CycloneDX aggregator tổng hợp. Đừng gắn nhãn “SBOM toàn hệ thống” cho một tập module chưa build/không được chọn.

### 12.5. Không nhầm root POM với runnable module

Root `packaging=pom` có thể đại diện aggregator, không có JAR của chính root. SBOM aggregate mô tả cả tập project/modules và dependencies chứ không nhất thiết phản ánh một file JAR duy nhất. Kiểm tra `metadata.component` và graph edges thực thay vì giả định tất cả modules là children theo đúng thứ tự khai `<modules>`.

---

## 13. SBOM dependency graph có phải toàn bộ sản phẩm đã giao không?

**Không nhất thiết.** Maven graph là nguồn rất tốt cho thư viện Java được Maven quản lý, nhưng sản phẩm thật có thể bao gồm:

- Fat/uber JAR tạo bởi Shade hoặc Assembly Plugin.
- Spring Boot executable JAR với nested JARs.
- WAR/EAR chứa libraries và còn phụ thuộc application server.
- JRE/JDK runtime image, container OS packages, system libraries.
- JNI/native binaries, browser assets, Node/npm dependencies.
- Plugin-generated binary hoặc code được tải tại runtime.
- Downloaded extensions và dynamically loaded artifacts.
- First-party code được đóng gói độc lập không nằm trong Maven dependency graph.

### 13.1. SBOM từ resolved Maven dependencies là một góc nhìn

Nó trả lời tốt: **Maven dự kiến sử dụng những dependencies nào** trong scope/chế độ đã chọn.

Nó không tự chứng minh: **file JAR cuối thực sự chứa những thư viện/classes nào**, đặc biệt khi packaging plugin có relocation/shading, excludes, minimization hoặc bundling. Muốn khẳng định inventory của artifact shipped, bổ sung kiểm tra **binary/package analysis** hoặc SBOM cho container/image theo policy.

### 13.2. Một dependency khai nhưng unused

Nếu POM khai một thư viện mà source không dùng, Maven vẫn có thể resolve nó và CycloneDX vẫn có thể đưa vào SBOM. SBOM từ Maven **không chứng minh mỗi component đều được runtime gọi đến**. Ngược lại, dependency được load động bằng custom classloader/runtime download có thể không lộ trong Maven graph.

### 13.3. “Không có trong BOM” không bằng “không có trong sản phẩm”

Trước khi tuyên bố thiếu một package, phải hỏi:

- Nó thuộc test scope nhưng đã loại test?
- Nằm ngoài Maven graph, ví dụ OS package?
- Được shade/minimize vào binary?
- Do container/application server cung cấp?
- Một profile khác chưa được bật?
- Nó là optional/transitive dependency bị exclusion/version mediation?

Bởi vậy nên ghi **coverage statement** cùng SBOM: loại artifact, lệnh build, profiles, scopes, excluded modules và các kiểm tra bổ sung.

---

## 14. PURL, bom-ref và truy ngược đường đi thành phần

### 14.1. Maven GAV và PURL

Maven coordinate:

~~~text
com.fasterxml.jackson.core:jackson-databind:2.18.3
~~~

Có thể biểu diễn dưới dạng purl:

~~~text
pkg:maven/com.fasterxml.jackson.core/jackson-databind@2.18.3
~~~

PURL giúp nhiều công cụ thống nhất nhận diện package. Nếu dependency có classifier/type khác thường, identity có thể cần qualifiers/metadata tương ứng. Không tự bỏ classifier khi nó quan trọng với việc xác định artifact thực.

### 14.2. bom-ref dùng làm khóa quan hệ

Trong JSON minh họa:

~~~json
{
  "ref": "pkg:maven/com.fasterxml.jackson.core/jackson-databind@2.18.3",
  "dependsOn": [
    "pkg:maven/com.fasterxml.jackson.core/jackson-core@2.18.3"
  ]
}
~~~

`ref` phải trỏ tới một component/service được mô tả hợp lệ và uniqueness theo BOM. Nếu chỉnh sửa SBOM thủ công làm `bom-ref` không nhất quán, vulnerability tool hoặc consumer có thể không hiểu đúng graph.

### 14.3. Truy ngược một package rủi ro

Khi security scanner báo một package bị ảnh hưởng:

1. Xác định package bằng purl/GAV/version **cụ thể**.
2. Tìm node trong components.
3. Dùng dependency edges để tìm những parents trực tiếp và đường đi tới application root.
4. Kiểm tra scope và có thực sự ship/runtime không.
5. Đánh giá advisory applicability và VEX/mitigations.
6. Nâng cấp dependency trực tiếp hoặc quản lý phiên bản transitive phù hợp, tránh override bừa.
7. Regenerate SBOM, rerun scanner/tests và lưu inventory mới.

Không quyết định upgrade chỉ từ một tên artifact có vẻ giống: advisory matching cần đúng ecosystem, group, artifact, version và điều kiện ảnh hưởng.

---

## 15. SBOM không phải vulnerability scan

Một SBOM có thể liệt kê 20 package nhưng **không chứa kết luận nào về vulnerability**. Quét rủi ro thường gồm các bước độc lập:

~~~text
Maven dependency resolution
          |
          v
CycloneDX SBOM generation
          |
          v
Schema / inventory completeness checks
          |
          v
Vulnerability/license policy analysis
          |
          v
Manual triage / VEX / remediation
          |
          v
CI decision and stored release evidence
~~~

### 15.1. Những kết luận không được rút ra

- “CycloneDX plugin chạy thành công” **không đồng nghĩa** mọi dependency an toàn.
- “Không có `vulnerabilities[]` trong BOM” **không đồng nghĩa** không có CVE.
- “Scanner không tìm thấy CVE” **không chứng minh** thư viện không chứa bug hoặc advisory mới chưa công bố.
- “Có license name trong POM” **không thay** license compliance review.
- “Một package có CVE” **không tự chứng minh** ứng dụng có exploit path; phải triage theo version/use case/runtime exposure.

### 15.2. SBOM hỗ trợ quản trị lỗ hổng liên tục

Sau release, advisory mới có thể xuất hiện. Một SBOM được lưu đúng release artifact giúp nhóm an toàn đối chiếu lại mà không cần suy đoán POM hiện tại. Đó là lý do cần **gắn SBOM với commit/release, lưu lâu dài và có thể truy xuất được**.

---

## 16. CI: sinh, validate, lưu và liên kết với artifacts

Một pipeline thực tế:

~~~text
1. Checkout đúng commit
          |
          v
2. Maven clean verify
   - compile
   - unit tests
   - CycloneDX makeBom/makeAggregateBom
          |
          v
3. Kiểm tra target/bom.json, target/bom.xml
          |
          v
4. CycloneDX schema validation
          |
          v
5. Dependency inventory / policy checks
          |
          v
6. Vulnerability & license scan
          |
          v
7. Lưu SBOM + artifact + provenance
          |
          v
8. Publish/promote nếu mọi quality gates đạt
~~~

### 16.1. Quy tắc gate không được bỏ qua

- Maven build phải có exit code `0` với tests thực sự chạy.
- Không dùng `-fn` để che module failures.
- Không bật `cyclonedx.skip=true` trong release job bắt buộc có SBOM.
- Không đánh dấu complete nếu `target/bom.json` không tồn tại hoặc là file cũ.
- Nếu schema validation fail, CI phải trả nonzero.
- Khi scanner/policy yêu cầu chặn phát hành, cần xử lý kết quả scan riêng.
- Giữ đúng active profiles, JDK, Maven và POM versions như build artifact được ship.

### 16.2. Không chèn credentials vào SBOM

SBOM có thể chứa names/versions, purls, source repository URLs, supplier info hoặc metadata nội bộ. Trước khi public, cần kiểm tra chính sách bảo mật thông tin: tên internal packages có thể là dữ liệu nhạy cảm về kiến trúc. Không tự đưa access tokens, private server credentials hoặc username/password vào file.

Nếu cần upload SBOM tới hệ thống bên ngoài, dùng connector/API có quyền được cấp, lưu audit logs và secrets qua CI secret manager. **Bài này không yêu cầu upload SBOM lên bất kỳ dịch vụ nào.**

### 16.3. Đính kèm SBOM vào Maven release

Với `skipAttach=false`, CycloneDX Maven Plugin có thể attach generated SBOM files với classifier `cyclonedx` để chúng đi cùng `install/deploy` lifecycle.

Phân biệt:

- `mvn verify`: tạo main JAR và SBOM trong `target`.
- `mvn install`: có thể cài main artifact và attached SBOM vào local repository.
- `mvn deploy`: có thể publish main artifact và attached SBOM vào remote repository theo config/permissions.

Không dùng `mvn deploy` trên repository production chỉ để thử học; có thể kiểm tra artifact publishing bằng sandbox repository với sự cho phép cần thiết.

---

## 17. Reproducibility của SBOM

Nếu hai builds cùng commit tạo BOM khác JSON, phải điều tra:

- CycloneDX plugin/schema version có khác?
- Source/POM/profile/scopes có khác?
- Dependency resolution có khác, đặc biệt SNAPSHOT hoặc version range?
- Timestamp, serial number và generator metadata có khác?
- Generated external references/license data có bị biến đổi?
- Component sorting/order có thay?
- Build environment hoặc Maven local repository có chứa dependency bytes khác?

CycloneDX Plugin có hỗ trợ `project.build.outputTimestamp` cho reproducible mode ở các phiên bản hiện đại. Ví dụ:

~~~xml
<properties>
    <project.build.outputTimestamp>2024-01-01T00:00:00Z</project.build.outputTimestamp>
</properties>
~~~

Lưu ý đây là **snippet mở rộng**, không phải cấu hình bắt buộc trong POM runnable. Nó giúp kiểm soát một phần metadata thời gian/serial do generator hỗ trợ, **không tự bảo đảm toàn bộ SBOM byte-identical** khi input versions/profiles/dependency data thay đổi.

### 17.1. Không chỉ so BOM hashes

SBOM JSON có thể được serial hóa khác thứ tự fields nhưng biểu diễn cùng graph. Nếu policy yêu cầu **byte-identical SBOM**, phải kiểm soát cả serialization/canonicalization và tool versions. Nếu policy chỉ yêu cầu **tương đương về nội dung inventory**, cần so tập components/edges và metadata theo quy tắc đã định. Hai mục tiêu khác nhau.

### 17.2. Khớp SBOM với đúng artifact

Một build có SBOM đầy đủ nhưng file JAR được lấy từ cache của commit trước có thể làm provenance sai. Do đó CI phải link:

~~~text
source commit SHA
    + build job/run ID
    + Maven GAV / version
    + artifact SHA-256
    + SBOM SHA-256
    + toolchain/plugin versions
~~~

Không tuyên bố SBOM mô tả artifact đã ship nếu artifact identity không được kiểm chứng.

---

## 18. Các tình huống sai lệch thường gặp

| Tình huống | Nguyên nhân khả dĩ | Cách giải quyết |
| --- | --- | --- |
| `target/bom.json` không xuất hiện | Plugin chưa bind/call, goal bị skip, build fail trước package | Xem effective POM, phase, logs |
| Plugin báo Maven offline không được hỗ trợ | Goal yêu cầu online mode | Chạy trên CI/build runner có môi trường phù hợp |
| BOM schema là 1.7 dù mong 1.6 | Lẫn docs phiên bản SNAPSHOT và plugin 2.9.3 | Pin plugin, đặt `schemaVersion=1.6` |
| Chỉ có XML không có JSON | `outputFormat=xml` | Dùng `json` hoặc `all` |
| BOM nằm ở thư mục khác | `outputDirectory` bị override | Đọc effective POM/config |
| JUnit không trong BOM | `includeTestScope=false` | Bật true nếu policy cần test inventory |
| Provided dependency vẫn xuất hiện | `includeProvidedScope=true` | Xác định phạm vi mong muốn |
| Jackson transitives không thấy | Graph/plugin settings khác, exclusions/version mediation | So dependency:tree, effective POM |
| BOM có module nội bộ nhưng không có JAR của nó | Aggregate mô tả modules, packaging/goal khác | Xác minh module output và scope |
| BOM có package không ship | Maven graph gồm provided/unused dependencies | Kết hợp binary inventory |
| BOM thiếu container OS libs | Maven không quản lý OS packages | Tạo image/OS SBOM riêng |
| BOM hợp lệ nhưng scanner báo CVE | Inventory khác security analysis | Triage advisory, update và rescan |
| Không có CVE trong SBOM | Plugin thường tạo inventory, không scan | Dùng vulnerability tool |
| BOM có license name nhưng license review chưa xong | Metadata khác legal assessment | Kiểm tra license source/policy |
| Scanner không nhận schema | Consumer chỉ hỗ trợ CycloneDX version khác | Chọn plugin/schema tương thích |
| BOM bị skip trong CI | `cyclonedx.skip=true` | Loại skip flag, kiểm output |
| Hai BOM hashes khác | Timestamps, serial, resolution, serialization | Pin inputs, kiểm metadata |
| `mvn dependency:tree` khác BOM | Scope/filters/goals/profile khác | Đối chiếu active scope và graph |
| Fat JAR chứa thư viện ngoài BOM | Packaging plugin bổ sung/bundle code | Scan binary/package artifact |
| Project deploy SBOM nhưng không thấy file ở root `target` | Attached artifact path/name khác build output | Phân biệt `bom.json` và classifier |
| Test pass nhưng App không chạy bằng `java -jar` | Main JAR thiếu Jackson runtime dependencies | Dùng Exec Plugin/runtime classpath hoặc fat JAR |
| `jq`/CycloneDX CLI không tìm thấy | Chưa cài công cụ ngoài Maven | Cài qua policy, không đổ lỗi cho SBOM |
| Multi-module aggregate không đủ | Chạy `-pl` subset hoặc exclude modules | Build đúng full reactor, review output |

### 18.1. Quy trình điều tra sáu bước

1. Ghi đúng Maven command, source commit, JDK, plugin/schema version và profiles.
2. Xác minh Maven dependency graph bằng `dependency:tree`.
3. Kiểm tra CycloneDX goal đã chạy, output path, include scope flags.
4. Đọc JSON: metadata.component, components, dependencies, purls.
5. Validate JSON/schema; kiểm inventory đối chiếu với scope/release artifact.
6. Nếu làm security gate, chạy scanner/policy riêng, lưu remediation quyết định và regenerate SBOM sau thay đổi.

---

## 19. Một số điểm chuyên sâu để không báo cáo sai

### 19.1. BOM không phải lockfile

CycloneDX BOM liệt kê components trong một build, nhưng không tự bắt Maven **lần build sau** phải resolve đúng các version đã ghi. Nếu cần inputs bất biến, phải dùng dependency pinning, repository controls và checksum/provenance trong pipeline.

### 19.2. Maven plugins là build tools

CycloneDX Maven Plugin tạo SBOM dựa trên project dependency graph; không được mặc định **mọi Maven plugins và transitive dependencies của plugins** đều là runtime components trong main JAR. Nếu cần build environment SBOM, phải định nghĩa scope inventory mở rộng và công cụ kiểm kê phù hợp.

### 19.3. Shading/relocation và bytecode bundling

Shade Plugin có thể gộp classes từ libraries vào cùng main JAR, relocation package names hoặc minimize dependencies. Maven graph giúp biết inputs, nhưng final binary layout có thể khác. Để phản ánh shipped artifact, kết hợp package/binary analysis; không suy ra “có nguyên JAR dependency bên trong” chỉ từ graph.

### 19.4. Optional và provided không đồng nghĩa an toàn

Một dependency có scope `provided` có thể tồn tại trong application server/runtime và vẫn chịu rủi ro security. Một dependency optional có thể được consumer kích hoạt trong context khác. Tùy inventory goal, bạn có thể cần SBOM khác cho runtime image/container.

### 19.5. Private Maven repositories

Đồ thị có thể chứa internal GAV. Cần quyết định SBOM nào được chia sẻ nội bộ, với khách hàng hoặc công khai. Hãy tránh đưa credentials vào SBOM hay logs; nếu system nhận SBOM ngoài tổ chức yêu cầu auth, dùng secret injection và kiểm quyền.

### 19.6. Cùng package nhưng hai classifiers

Maven coordinates có thể bao gồm type/classifier. Nếu hai artifacts cùng group/artifact/version nhưng classifier khác và thực sự khác bytes/role, quality process cần giữ identity đủ chi tiết. Đừng gộp chúng vì `name` giống nhau.

### 19.7. SBOM diff giữa hai releases

Một so sánh SBOM hữu ích phải nêu:

- Components added/removed.
- Versions upgraded/downgraded.
- Dependency paths changed.
- Scopes hoặc exclusions thay đổi.
- First-party modules có thay đổi không.
- Dữ liệu license/source mới/thiếu.
- Scan findings sau khi regenerate.

Một JSON diff văn bản thuần có thể gây nhiễu do thứ tự components hoặc timestamps, nên dùng comparator theo SBOM schema khi muốn diff ngữ nghĩa.

---

## 20. Bài tập thực hành

### Bài A — Direct và transitive

POM chỉ khai `jackson-databind`. Hãy giải thích vì sao `jackson-core` và `jackson-annotations` có thể xuất hiện trong `dependency:tree` và SBOM.

### Bài B — Maven BOM vs SBOM

Một Maven BOM trong `dependencyManagement` quản lý 30 artifacts, nhưng project chỉ dùng 5. Vì sao CycloneDX SBOM không nên tự liệt kê cả 30 chỉ vì chúng được quản lý phiên bản?

### Bài C — Build demo

Tạo ba files của mục 7, chạy `mvn -B -ntp clean verify`, xác nhận 2 tests PASS và hai files `target/bom.json`/`target/bom.xml`.

### Bài D — Chạy Java

Chạy `mvn -q -Dexec.mainClass=vn.example.sbom.App exec:java`. Kiểm stdout `SBOM DEMO: OK`. Vì sao thin JAR không chạy được bằng `java -jar` nếu Jackson JARs không có trên classpath?

### Bài E — Đọc JSON

Dùng `python3 -m json.tool` hoặc PowerShell parser để kiểm syntax. Mở `bomFormat`, `specVersion`, `metadata.component`, `components` và `dependencies`. Bạn đang xem inventory hay vulnerability report?

### Bài F — JSON schema

Nếu đã cài CycloneDX CLI, chạy validate `--input-version v1_6 --fail-on-errors`. Vì sao JSON syntax check không đủ?

### Bài G — So tree với BOM

Chạy `mvn dependency:tree` và đọc danh sách Jackson components trong BOM. Những packages nào là direct, những packages nào là transitive?

### Bài H — Test scope

Đổi `includeTestScope` sang true, build lại và so BOM. Vì sao JUnit xuất hiện nhiều hơn nhưng không có nghĩa shipped application JAR chứa JUnit?

### Bài I — Provided scope

Một WAR project phụ thuộc servlet API với `provided` scope. Nếu SBOM include provided, danh sách đó có được coi là các libraries đóng gói trong WAR không?

### Bài J — Version mediation

Một dependency mới kéo phiên bản Jackson khác với version được quản lý trong `dependencyManagement`. Làm thế nào xác định version thực sự được Maven chọn trước khi báo SBOM đúng?

### Bài K — Multi-module

Với reactor có `model-core` và `api-app`, khi nào dùng `makeBom` và khi nào dùng `makeAggregateBom`? `outputReactorProjects` ảnh hưởng tới files như thế nào?

### Bài L — Scanner

File SBOM không có trường `vulnerabilities`. Có được kết luận ứng dụng không có CVE? Hãy mô tả công cụ/bước bổ sung.

### Bài M — Build artifact identity

Một CI job tạo SBOM từ commit mới nhưng lấy JAR từ cache commit cũ. Điều gì sai? Cần lưu SHA-256/commit/build identity nào để phát hiện?

### Bài N — SBOM cho fat JAR/container

Một Java application được đóng trong container có JRE, OS libraries và browser assets. Vì sao BOM chỉ từ Maven graph chưa thể là inventory toàn bộ image?

### Bài O — CI security gate

Thiết kế flow Maven clean verify → validate SBOM JSON/schema → inventory checks → vulnerability scan/policy → publish. Chỉ rõ bước nào phải trả nonzero khi sai.

### Bài P — Cấu hình version/schema

Vì sao không nên dùng plugin 2.9.3 nhưng copy `schemaVersion=1.7` từ tài liệu SNAPSHOT 2.10? Cần kiểm tra gì ở consumer nhận SBOM?

### Bài Q — Optional/exclusion

Nếu một dependency bị `<exclusions>` loại bỏ, SBOM từ resolved graph nên thể hiện điều gì? Có cần kiểm thêm packaged binary không?

### Bài R — SBOM mới sau remediation

Sau khi nâng cấp Jackson dependency, hãy regenerate SBOM, so component version/purl và dependency edges, chạy lại unit tests, rồi đưa SBOM mới đi quét security.

---

## 21. Checklist trước khi đưa SBOM vào quy trình phát hành

- [ ] Đã chốt phạm vi: runtime/library inventory, test/build inventory hay release/container inventory.
- [ ] Đã xác minh source commit và Maven project GAV.
- [ ] Đã xem `dependency:tree` để hiểu direct/transitive dependencies.
- [ ] Các Maven dependencies/versions/profiles đã được kiểm soát.
- [ ] CycloneDX plugin và schema version được ghim theo consumer compatibility.
- [ ] `makeBom` hoặc `makeAggregateBom` được chọn đúng single/multi-module.
- [ ] Các scope include flags được quyết định tường minh; biết mặc định test=false.
- [ ] Đã kiểm `target/bom.json` và `target/bom.xml` thuộc build hiện tại.
- [ ] JSON parse thành công, schema validation CycloneDX đúng version.
- [ ] `metadata.component` mô tả đúng project/release.
- [ ] Các component quan trọng có GAV/version/purl đáng tin.
- [ ] Graph `dependencies[].ref/dependsOn` có thể truy đường đi cần thiết.
- [ ] Không nhầm BOM trong dependencyManagement với SBOM inventory.
- [ ] Không nhầm một SBOM hợp lệ với “không có vulnerability”.
- [ ] Đã đánh giá license/source metadata thiếu/sai nếu policy yêu cầu.
- [ ] Với fat JAR/WAR/container, có kiểm kê final artifact/runtime image riêng.
- [ ] CI không skip CycloneDX hoặc test gate trong release workflow.
- [ ] SBOM được lưu cùng artifact checksum, commit, toolchain và build job.
- [ ] Có quy trình cập nhật SBOM sau thay đổi dependencies hoặc bản vá.
- [ ] Không public internal dependencies/metadata ngoài phạm vi cho phép.
- [ ] Mismatch schema, thiếu inventory hoặc policy failure làm CI trả nonzero.

**Kết luận:** Maven `dependency:tree` cho thấy những dependencies mà Maven thực sự phân giải; **CycloneDX Maven Plugin** biến inventory và quan hệ ấy thành **SBOM JSON/XML** có cấu trúc, mang định danh Maven GAV/PURL, components và dependency edges. SBOM đặc biệt hữu ích để theo dõi **phụ thuộc bắc cầu** và liên kết bản kê với release artifact. Tuy vậy nó không tự là vulnerability scan, không luôn bao phủ final runtime image và không thay kiểm thử. Một quy trình đáng tin cần **đúng scope, đúng schema, graph được xác minh, artifact identity và CI controls**.

## 22. Tài liệu chính thức

- [CycloneDX Maven Plugin — Introduction](https://cyclonedx.github.io/cyclonedx-maven-plugin/): mục đích, goals, output formats, scope options và classifier.
- [CycloneDX Maven Plugin — makeBom](https://cyclonedx.github.io/cyclonedx-maven-plugin/makeBom-mojo.html): sinh BOM theo module.
- [CycloneDX Maven Plugin — makeAggregateBom](https://cyclonedx.github.io/cyclonedx-maven-plugin/makeAggregateBom-mojo.html): aggregate reactor, outputReactorProjects, include scopes.
- [CycloneDX Maven Plugin — Releases](https://github.com/CycloneDX/cyclonedx-maven-plugin/releases): xác nhận plugin versions đã phát hành.
- [CycloneDX Specification — Overview](https://cyclonedx.org/specification/overview/): components, dependencies, metadata, vulnerabilities và schema evolution.
- [CycloneDX — Software Dependencies Use Case](https://cyclonedx.org/use-cases/software-dependencies/): `bom-ref`, PURL và dependency relationships.
- [CycloneDX Specification 1.6 — JSON](https://cyclonedx.org/docs/1.6/json/): cấu trúc SBOM và schema.
- [CycloneDX CLI](https://github.com/CycloneDX/cyclonedx-cli): `validate`, convert/diff và schema validation.
- [Apache Maven Dependency Plugin — dependency:tree](https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html): resolved dependency graph, filters.
- [Apache Maven Dependency Plugin — JSON Tree Format](https://maven.apache.org/plugins/maven-dependency-plugin/examples/tree-mojo.html): outputType JSON, DOT, GraphML.
- [Apache Maven — Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html): scopes, mediation, transitive dependencies, dependencyManagement.
- [Apache Maven — Multi-Module Reactor](https://maven.apache.org/guides/mini/guide-multiple-modules.html): project relationships và selected reactor modules.
- [Package URL Specification](https://github.com/package-url/purl-spec): cách định danh package.
- [Maven Central — Jackson Databind 2.18.3](https://central.sonatype.com/artifact/com.fasterxml.jackson.core/jackson-databind/2.18.3): tọa độ dependency minh họa.
