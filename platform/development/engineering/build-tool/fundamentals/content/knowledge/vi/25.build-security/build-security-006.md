# Danh mục thành phần phần mềm (SBOM) và truy vết phụ thuộc

Một ứng dụng Java hiếm khi chỉ gồm những class do nhóm phát triển viết. Khi build, ứng dụng thường kết hợp thư viện trực tiếp, dependency bắc cầu, plugin, runtime, thư viện hệ thống và đôi khi cả thành phần được đóng gói từ bên thứ ba. Nếu một thư viện có lỗ hổng, thay đổi license hoặc bị thu hồi, nhóm cần biết sản phẩm nào đang chứa nó, dependency đến từ đâu và phiên bản nào đã được phát hành.

**Software Bill of Materials (SBOM)** là danh mục có cấu trúc mô tả các thành phần phần mềm trong một sản phẩm. SBOM hỗ trợ kiểm kê, phân tích lỗ hổng, kiểm tra license và truy vết chuỗi cung ứng. Nó giúp trả lời câu hỏi “sản phẩm này chứa những gì?” nhưng không tự chứng minh sản phẩm an toàn, không thay thế kiểm thử bảo mật và cũng không chứng minh cách artifact được tạo ra.

Để truy vết đầy đủ, cần kết hợp SBOM với dependency graph, lock/verification metadata, digest của artifact, build provenance và chữ ký hoặc attestation khi quy trình yêu cầu. Những thông tin này tạo thành mối liên hệ từ source revision và dependency đã resolve đến binary được triển khai.

## 1. SBOM là gì?

SBOM là bản kê khai các thành phần tạo nên một sản phẩm phần mềm, được biểu diễn bằng định dạng máy có thể đọc và trao đổi. Tùy phạm vi, SBOM có thể mô tả:

- thư viện và package trực tiếp;
- dependency bắc cầu;
- module hoặc component nội bộ;
- framework và runtime component;
- package của hệ điều hành trong container image;
- file hoặc thành phần được nhúng trong archive;
- mối quan hệ giữa các component;
- thông tin nhà cung cấp, version, license và checksum khi có dữ liệu.

Một SBOM có thể được tạo từ dependency graph của build tool, phân tích archive đã đóng gói hoặc quét container image. Ba cách này có thể cho kết quả khác nhau vì chúng quan sát các lớp khác nhau của sản phẩm.

### 1.1. SBOM trả lời những câu hỏi nào?

Ví dụ, khi một advisory công bố lỗ hổng trong thư viện JSON, nhóm có thể dùng SBOM để:

1. tìm những artifact có chứa package bị ảnh hưởng;
2. xác định version đang dùng;
3. xem package là dependency trực tiếp hay bắc cầu;
4. tìm đường dẫn dependency dẫn đến package;
5. xác định release nào và môi trường nào đang sử dụng artifact đó;
6. quyết định nâng cấp, loại bỏ, giảm thiểu hoặc ghi nhận lý do chưa bị ảnh hưởng.

Khi có yêu cầu license, SBOM giúp liệt kê component và license metadata để đội pháp chế hoặc compliance xem xét. Khi có sự cố chuỗi cung ứng, SBOM giúp xác định nhanh phạm vi sản phẩm có thể bị ảnh hưởng.

### 1.2. SBOM không phải là gì?

SBOM không tự động:

- phát hiện mọi lỗ hổng;
- chứng minh component có thể bị khai thác trong ứng dụng;
- chứng minh dependency tải từ nguồn đáng tin cậy;
- chứng minh source code hoặc build process không bị can thiệp;
- thay thế test, code review, SAST, DAST hay container scanning;
- bảo đảm mọi file trong artifact đều được nhận diện chính xác;
- chứng minh artifact được tạo từ commit mà nhóm tuyên bố.

SBOM là dữ liệu kiểm kê. Chất lượng kết luận phụ thuộc độ đầy đủ, độ chính xác, thời điểm tạo và khả năng gắn nó với đúng artifact.

## 2. Phân biệt SBOM với Maven BOM

Trong hệ sinh thái Java, từ BOM thường xuất hiện với hai nghĩa khác nhau:

| Thuật ngữ | Ý nghĩa | Mục đích |
|---|---|---|
| Maven BOM (Bill of Materials) | POM quản lý version dependency thông qua dependencyManagement | Giúp project resolve các dependency theo bộ version đã định |
| SBOM (Software Bill of Materials) | Danh mục component thực tế của sản phẩm | Kiểm kê, bảo mật, license và truy vết |

Maven BOM giúp điều khiển dependency version trước và trong lúc build. SBOM mô tả những component đã được đưa vào hoặc được xác định là thành phần của sản phẩm sau khi resolve/build.

Một Maven BOM không tự động là SBOM. Ngược lại, SBOM có thể được tạo từ dependency graph đã chịu ảnh hưởng của một hoặc nhiều Maven BOM.

Ví dụ Maven BOM:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.example.platform</groupId>
            <artifactId>platform-dependencies</artifactId>
            <version>4.2.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Đoạn cấu hình này quản lý version của dependency. Nó không liệt kê đầy đủ mọi component cuối cùng được đóng gói trong ứng dụng, cũng không thay thế SBOM.

## 3. Định dạng SBOM phổ biến

Hai định dạng được sử dụng rộng rãi trong chuỗi cung ứng phần mềm là SPDX và CycloneDX.

### 3.1. SPDX

SPDX là một chuẩn mở để biểu diễn component, package, file, license, quan hệ và thông tin liên quan đến phần mềm. Chuẩn này được dùng trong kiểm kê component và trao đổi dữ liệu license/compliance.

Thông tin SPDX có thể bao gồm:

- document metadata;
- package/component name và version;
- supplier hoặc originator nếu biết;
- download location hoặc external reference;
- license declared/concluded;
- checksum;
- file và package relationship;
- creator/tool tạo tài liệu;
- thông tin bản quyền và ghi chú.

SPDX có nhiều phiên bản và cách serialize. Khi trao đổi SBOM, cần thống nhất specification version và file format mà công cụ tiêu thụ hỗ trợ.

### 3.2. CycloneDX

CycloneDX là chuẩn SBOM do OWASP khởi xướng, hỗ trợ mô tả component, service, dependency relationship và dữ liệu liên quan đến chuỗi cung ứng.

Một CycloneDX BOM có thể chứa:

- metadata của document và công cụ tạo;
- component name, version, supplier;
- package URL (PURL);
- hashes;
- licenses;
- external references;
- dependency graph;
- vulnerability data hoặc liên kết tới dữ liệu liên quan, tùy phiên bản và workflow.

CycloneDX thường được trao đổi dưới dạng JSON hoặc XML. Cần chọn schema version tương thích với generator, validator và hệ thống tiếp nhận.

### 3.3. Chọn SPDX hay CycloneDX

| Tiêu chí | SPDX | CycloneDX |
|---|---|---|
| Trọng tâm truyền thống | Component inventory, license và software package metadata | SBOM và dữ liệu phục vụ application security/supply chain |
| Mô hình dữ liệu | Document, package, file, relationship, license | Metadata, component, service, dependency, vulnerability |
| Trao đổi | Nhiều serialization theo phiên bản chuẩn | JSON/XML và các định dạng được schema hỗ trợ |
| Hệ sinh thái | Compliance, license và supply chain tooling | Security scanner, dependency analysis và SBOM tooling |

Không có định dạng duy nhất phù hợp mọi tổ chức. Hãy chọn theo yêu cầu khách hàng, regulator, repository, scanner và quy trình nội bộ. Nếu cần cả hai, có thể sinh hoặc chuyển đổi định dạng, nhưng phải kiểm tra rằng việc chuyển đổi không làm mất trường quan trọng.

### 3.4. Schema version và validation

SBOM phải chỉ rõ specification version. Generator mới có thể tạo schema mà scanner cũ không đọc được. Trước khi phát hành, cần:

1. xác định schema version được chấp nhận;
2. pin version generator;
3. validate file bằng công cụ tương thích;
4. lưu thông tin generator/version;
5. kiểm tra component count và dependency relationship có hợp lý.

Không nên chỉ kiểm tra rằng file JSON/XML tồn tại. Một file có cú pháp hợp lệ vẫn có thể thiếu component hoặc relationship cần thiết.

## 4. Các trường thông tin quan trọng trong SBOM

Một SBOM hữu ích cần đủ metadata để định danh component và liên kết nó với artifact.

| Trường | Mục đích | Ví dụ hoặc ghi chú |
|---|---|---|
| Name | Tên component | commons-lang3 |
| Version | Phiên bản component | 3.14.0 |
| Supplier | Nhà cung cấp nếu xác định được | Apache Software Foundation |
| Package URL | Định danh package theo ecosystem | pkg:maven/org.apache.commons/commons-lang3@3.14.0 |
| Hash | Nhận diện nội dung cụ thể | SHA-256 của artifact dependency |
| License | License khai báo hoặc được xác định | Apache-2.0, MIT, hoặc NOASSERTION khi chưa biết |
| External reference | Liên kết tới source, advisory hoặc tài liệu | Repository URL, issue tracker |
| Relationship | Quan hệ dependency | application DEPENDS_ON library |
| Scope/context | Component xuất hiện trong phạm vi nào | runtime, test, development, container |
| Document metadata | Thời điểm, serial/version và công cụ tạo | Generator name/version |

Không phải mọi component đều có đủ tất cả trường. Nếu không biết supplier hoặc license, hãy thể hiện là chưa xác định theo quy tắc của format và workflow; không tự suy đoán.

### 4.1. Package URL (PURL)

PURL là cách chuẩn hóa định danh package trên nhiều package ecosystem. Một PURL thường thể hiện type, namespace, name, version và qualifier khi cần.

Ví dụ Maven:

~~~text
pkg:maven/org.apache.commons/commons-lang3@3.14.0
~~~

Trong ví dụ:

- type là maven;
- namespace tương ứng groupId;
- name tương ứng artifactId;
- version là phiên bản package.

PURL giúp scanner đối chiếu component giữa nhiều nguồn dữ liệu. Nó không thay thế hash: hai file có cùng tọa độ/version vẫn có thể khác nội dung nếu repository cho phép ghi đè artifact.

### 4.2. CPE và định danh khác

CPE thường được dùng trong hệ thống quản lý lỗ hổng để định danh sản phẩm/phần mềm theo tên chuẩn hóa. Không phải package Java nào cũng có CPE chính xác. Với thư viện Java, PURL thường hữu ích để định danh package; scanner có thể ánh xạ sang CPE hoặc advisory identifier nếu có.

Không nên ép mọi component vào một CPE suy đoán. Sai định danh có thể gây false positive hoặc bỏ sót advisory.

### 4.3. Hash component

Hash giúp phân biệt nội dung artifact cụ thể. Với dependency JAR, có thể ghi SHA-256 khi generator hoặc quy trình có thể thu thập.

Tên và version cho biết package được khai báo là gì; hash cho biết file thực tế có byte nào. Khi điều tra repository bị thay thế artifact, hash là dữ liệu quan trọng để so sánh.

## 5. Dependency trực tiếp và dependency bắc cầu

Một ứng dụng thường khai báo một số dependency trực tiếp, nhưng những dependency đó lại kéo theo thư viện khác.

Ví dụ:

~~~text
inventory-service
└── catalog-client
    ├── jackson-databind
    │   ├── jackson-core
    │   └── jackson-annotations
    └── http-client
        └── commons-codec
~~~

Trong sơ đồ:

- catalog-client là dependency trực tiếp của ứng dụng;
- jackson-databind và http-client là dependency bắc cầu qua catalog-client;
- jackson-core, jackson-annotations và commons-codec là các dependency sâu hơn.

Một lỗ hổng có thể nằm trong dependency bắc cầu mà developer không khai báo trực tiếp. Vì vậy, chỉ đọc file POM hoặc build script không đủ để lập inventory.

### 5.1. Dependency graph khác danh sách khai báo

Dependency graph phản ánh kết quả resolve sau khi build tool áp dụng:

- version constraints và dependency management;
- conflict resolution;
- exclusions;
- optional dependency;
- dependency scope/configuration;
- platform/BOM;
- repository metadata;
- variant/capability selection trong Gradle.

Hai project cùng khai báo một dependency trực tiếp vẫn có thể resolve dependency graph khác nhau do version, platform, exclusion hoặc metadata.

### 5.2. Đường dẫn dependency

Để truy vết một package, cần biết nó được kéo vào qua nhánh nào. Ví dụ:

~~~text
inventory-service
  -> catalog-client:2.3.0
      -> jackson-databind:2.17.2
          -> jackson-core:2.17.2
~~~

Đường dẫn giúp xác định nơi cần nâng version. Nếu jackson-core là dependency bắc cầu, nhóm có thể nâng catalog-client, dùng dependency constraint/BOM hoặc exclude và khai báo version tương thích nếu việc override được hỗ trợ.

Không nên nâng một dependency bắc cầu tùy tiện nếu thư viện cha yêu cầu API khác. Cần kiểm thử tương thích sau khi thay đổi graph.

## 6. Maven: xem dependency graph để truy vết

Maven Dependency Plugin cung cấp goal dependency:tree để hiển thị graph.

~~~bash
./mvnw dependency:tree
~~~

Có thể xem chi tiết hơn, gồm một số node bị loại do conflict:

~~~bash
./mvnw dependency:tree -Dverbose
~~~

Để tập trung vào dependency runtime:

~~~bash
./mvnw dependency:tree -Dscope=runtime
~~~

Để lọc một artifact:

~~~bash
./mvnw dependency:tree -Dincludes=org.apache.commons:commons-lang3
~~~

Các tham số lọc phụ thuộc version Maven Dependency Plugin. Nếu không thấy component, hãy kiểm tra scope và filter trước khi kết luận component không có trong sản phẩm.

### 6.1. Xem effective POM

POM thực tế có thể chịu ảnh hưởng parent POM, profile và dependencyManagement. Dùng effective POM để xem cấu hình Maven sau khi hợp nhất:

~~~bash
./mvnw help:effective-pom
~~~

Effective POM giúp truy vết version/plugin/configuration được kế thừa. Nó không phải SBOM và không cho biết chính xác mọi file đã được đóng gói.

### 6.2. Hiểu scope của Maven

| Scope | Ý nghĩa khái quát | Có thường nằm trong runtime app? |
|---|---|---|
| compile | Dependency dùng khi compile và thường có trên classpath runtime | Có |
| runtime | Cần khi chạy, không nhất thiết cần compile | Có |
| provided | Được môi trường/container cung cấp | Thường không đóng gói |
| test | Chỉ phục vụ compile/test | Không |
| system | Lấy từ đường dẫn cục bộ được khai báo | Phụ thuộc packaging, không nên dùng tùy tiện |
| import | Nhập dependency management từ POM/BOM trong dependencyManagement | Không phải component runtime chỉ vì được import |

Scope ảnh hưởng cách resolve và classpath. SBOM của sản phẩm runtime nên tập trung đúng dependency được phân phối hoặc yêu cầu bởi môi trường, đồng thời có thể tạo thêm SBOM riêng cho test/development nếu cần.

### 6.3. Optional và exclusions

Dependency optional trong Maven không được consumer kéo theo như dependency bắt buộc theo cách thông thường. Exclusion loại một nhánh dependency bắc cầu khỏi graph của project.

Khi tạo SBOM, cần biết generator có đưa optional, test hoặc dependency bị loại vào danh mục hay không. Không nên trộn mọi dependency được khai báo trong POM thành một danh sách runtime duy nhất.

## 7. Gradle: xem dependency graph để truy vết

Gradle dùng configurations để mô tả các classpath khác nhau. Với Java application, có thể xem runtime classpath:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Compile classpath:

~~~bash
./gradlew dependencies --configuration compileClasspath
~~~

Test runtime:

~~~bash
./gradlew dependencies --configuration testRuntimeClasspath
~~~

### 7.1. dependencyInsight

Khi cần biết một package đến từ đâu hoặc tại sao một version được chọn:

~~~bash
./gradlew dependencyInsight --dependency jackson-databind --configuration runtimeClasspath
~~~

Lệnh này giúp xem:

- dependency path;
- version được yêu cầu và version được chọn;
- lý do conflict resolution hoặc constraint;
- dependency nào đưa component vào configuration.

Đây là công cụ quan trọng khi xử lý lỗ hổng ở dependency bắc cầu.

### 7.2. Hiểu configuration của Gradle

| Configuration | Ý nghĩa thường gặp | Có thường nằm trong runtime application? |
|---|---|---|
| api | Dependency được công khai qua API của thư viện | Có thể được consumer resolve |
| implementation | Dependency dùng nội bộ implementation | Có trong runtime của ứng dụng/thư viện theo graph |
| compileOnly | Cần khi compile nhưng môi trường khác cung cấp | Thường không |
| runtimeOnly | Chỉ cần khi chạy | Có |
| testImplementation | Dependency dành cho test compile/runtime | Không |
| testRuntimeOnly | Chỉ dùng khi chạy test | Không |

Ý nghĩa chính xác phụ thuộc plugin và loại project. Khi tạo SBOM, hãy chọn configuration tương ứng với sản phẩm cần mô tả, chẳng hạn runtimeClasspath cho ứng dụng JVM, thay vì lấy toàn bộ configuration một cách không phân biệt.

### 7.3. Platform và version constraints

Gradle platform/BOM và constraints ảnh hưởng version được chọn. Khi một package có version khác dự kiến, hãy kiểm tra dependencyInsight và platform được import.

Dependency locking giúp giữ resolution ổn định giữa các lần build. Tuy nhiên, lockfile không tự chứng minh nội dung JAR tải về đúng; dependency verification hoặc hash/provenance có thể bổ sung bằng chứng về nội dung.

## 8. Dependency graph chưa chắc là inventory của artifact cuối

Một điểm quan trọng trong SBOM là phân biệt dependency được resolve với component thực sự có mặt trong sản phẩm được phân phối.

Ví dụ:

- dependency test có trong testRuntimeClasspath nhưng không được đóng gói vào ứng dụng;
- Servlet API có scope provided và do container cung cấp;
- một executable JAR có thể nhúng dependency theo cấu trúc riêng;
- một uber JAR có thể giải nén và hợp nhất class từ nhiều JAR;
- một container image có thêm JRE, OS packages, shell utilities và native libraries;
- một script distribution có thể chứa nhiều JAR trong thư mục lib.

SBOM được tạo từ dependency graph có thể mô tả những component đã resolve cho configuration đó. SBOM được tạo bằng cách quét archive/image có thể nhìn thấy những component thực sự được đóng gói. Tùy sản phẩm, cần một hoặc cả hai góc nhìn.

### 8.1. Thin JAR

Thin JAR thường chỉ chứa class/resource của project. Dependency được resolve riêng qua Maven/Gradle metadata hoặc classpath runtime. Với thư viện, SBOM có thể mô tả chính artifact và graph dependency công bố.

### 8.2. Fat JAR và uber JAR

Fat JAR có thể chứa dependency lồng trong cấu trúc riêng; uber JAR có thể hợp nhất class/resource từ dependency. Nếu chỉ đọc POM của project, scanner có thể không nhìn thấy đầy đủ nội dung đã được nhúng nếu metadata không đi kèm hoặc cách đóng gói không được hỗ trợ.

Hãy kiểm tra SBOM generator có nhận diện được nested JAR/shaded component hay không. Nếu cần, quét artifact cuối bằng công cụ phân tích archive.

### 8.3. WAR

WAR có thể chứa class/resource ứng dụng và dependency trong WEB-INF/lib. Các API do application server cung cấp có thể không được đóng gói. SBOM nên nêu rõ phạm vi artifact và những runtime component được giả định từ môi trường.

### 8.4. Container image

SBOM của JAR không mô tả đầy đủ container image. Image có thể chứa:

- JRE hoặc JDK;
- package hệ điều hành;
- thư viện native;
- shell và công cụ hệ thống;
- application JAR và dependency;
- agent hoặc sidecar binaries được copy vào image.

Nếu sản phẩm được phát hành dưới dạng image, cần inventory gắn với image digest. Có thể tạo SBOM cho JAR và một SBOM khác cho image, hoặc một inventory tổng hợp nếu công cụ hỗ trợ.

## 9. Tạo SBOM trong Maven

Một cách phổ biến là dùng CycloneDX Maven Plugin để tạo BOM từ project dependency model.

Có thể gọi goal makeBom với version plugin được pin theo chính sách dự án:

~~~bash
./mvnw org.cyclonedx:cyclonedx-maven-plugin:VERSION:makeBom
~~~

Thay VERSION bằng một version plugin cụ thể đã được kiểm tra và khóa trong cấu hình release. Không dùng version trôi nổi cho pipeline phát hành cần tái lập.

Với Maven multi-module, plugin có goal aggregate để tạo BOM tổng hợp cho reactor:

~~~bash
./mvnw org.cyclonedx:cyclonedx-maven-plugin:VERSION:makeAggregateBom
~~~

Tên goal và cấu hình output phụ thuộc version plugin. Hãy kiểm tra tài liệu của version đã pin, xác định output path, schema version và scope/configuration được đưa vào BOM.

### 9.1. Gắn plugin vào lifecycle

Có thể cấu hình plugin trong POM để tạo SBOM ở một phase như verify hoặc package, tùy yêu cầu pipeline. Cần bảo đảm:

- version plugin được pin;
- output được đặt ở vị trí dễ thu thập;
- module aggregation đúng với cấu trúc project;
- scope dependency phù hợp;
- SBOM được tạo sau khi dependency model hoàn chỉnh;
- report được upload ngay cả khi bước scan sau đó thất bại.

Không nên chỉ thêm plugin rồi mặc định rằng BOM bao phủ mọi thành phần trong fat JAR, WAR hoặc container image.

### 9.2. Maven multi-module

Một reactor có thể có:

~~~text
platform-parent
├── common-library
├── catalog-client
└── inventory-service
~~~

SBOM aggregate có thể giúp nhìn toàn bộ module trong một build. Tuy nhiên, cần phân biệt:

- BOM của từng module;
- BOM tổng hợp của reactor;
- SBOM của artifact service cuối;
- SBOM của distribution hoặc container image.

Một aggregate BOM có thể bao gồm component thuộc module không được đưa vào sản phẩm triển khai cụ thể. Hãy chọn BOM theo đối tượng cần kiểm kê.

## 10. Tạo SBOM trong Gradle

Có thể dùng plugin CycloneDX cho Gradle để sinh BOM từ dependency model.

Ví dụ khai báo plugin với version được pin:

~~~kotlin
plugins {
    java
    id("org.cyclonedx.bom") version "PINNED_VERSION"
}
~~~

Chạy task do plugin cung cấp, thường có tên cyclonedxBom:

~~~bash
./gradlew cyclonedxBom
~~~

Tên task, configuration, output path và tùy chọn phụ thuộc version plugin. Hãy đọc tài liệu đúng version được dùng, chọn configuration tương ứng với runtime/deployment và kiểm tra schema/output sau khi sinh.

### 10.1. Chọn configuration đúng

Một ứng dụng Java có thể có compileClasspath, runtimeClasspath, testRuntimeClasspath và configuration tùy chỉnh. Nếu mục tiêu là SBOM cho ứng dụng runtime, hãy chọn runtime graph hoặc configuration tương đương.

Nếu cần inventory cho test tooling, có thể tạo SBOM riêng cho test scope. Không nên gộp mọi configuration vào một file rồi coi tất cả component đều được triển khai.

### 10.2. Multi-project Gradle

Với multi-project build, xác định SBOM cần mô tả:

- một subproject;
- toàn bộ build;
- một application distribution;
- một image cụ thể.

Một BOM toàn build hữu ích cho dependency governance, nhưng có thể chứa component không đi vào một ứng dụng cuối. Một SBOM theo artifact giúp đội vận hành xác định đúng binary đang chạy.

## 11. Ví dụ cấu trúc SBOM rút gọn

Ví dụ dưới đây minh họa các trường cơ bản theo phong cách CycloneDX JSON. Đây là dữ liệu giản lược để giải thích, không phải file hoàn chỉnh để dùng trong production:

~~~json
{
  "bomFormat": "CycloneDX",
  "specVersion": "1.x",
  "version": 1,
  "metadata": {
    "component": {
      "type": "application",
      "name": "inventory-service",
      "version": "1.4.0"
    }
  },
  "components": [
    {
      "type": "library",
      "name": "commons-lang3",
      "version": "3.14.0",
      "purl": "pkg:maven/org.apache.commons/commons-lang3@3.14.0",
      "licenses": [
        {
          "license": {
            "id": "Apache-2.0"
          }
        }
      ]
    }
  ],
  "dependencies": [
    {
      "ref": "application-ref",
      "dependsOn": ["commons-lang3-ref"]
    }
  ]
}
~~~

Các reference trong ví dụ chỉ mang tính minh họa; BOM thực tế cần reference hợp lệ, serial/version, metadata đầy đủ và tuân thủ schema của spec version được chọn.

### 11.1. Dependency relationship

Danh sách component cho biết package nào xuất hiện. Dependency relationships cho biết package nào phụ thuộc package nào. Quan hệ này giúp trả lời đường dẫn đưa một component vào sản phẩm.

Nếu generator không tạo dependency graph hoặc graph không đầy đủ, SBOM vẫn có thể hữu ích cho inventory nhưng khả năng truy vết đường dẫn bị hạn chế.

### 11.2. Component metadata và dữ liệu chưa biết

Nếu license không xác định, cần biểu diễn trạng thái chưa biết theo format được chọn, thay vì gán license dựa trên tên thư viện. Nếu component nội bộ không có PURL công khai, có thể dùng định danh nội bộ hoặc external reference phù hợp.

## 12. Gắn SBOM với đúng artifact

Một file tên bom.json không đủ để chứng minh nó mô tả artifact nào. SBOM cần được liên kết với sản phẩm cụ thể bằng name/version và tốt nhất là digest của artifact.

Ví dụ release:

~~~text
inventory-service-1.4.0.jar
SHA-256: 9a...e2

inventory-service-1.4.0.cdx.json
Subject: inventory-service-1.4.0.jar
Subject digest: 9a...e2
~~~

Digest trong ví dụ là minh họa. Trong quy trình thật, phải tính digest từ file đã publish hoặc file được đưa vào deployment.

### 12.1. SBOM cho source revision và SBOM cho binary

SBOM có thể được sinh từ source/dependency model trước khi đóng gói hoặc phân tích binary sau khi đóng gói. Hai loại này trả lời câu hỏi khác nhau:

- source/build SBOM: dependency graph mà build tool resolve;
- artifact SBOM: component nhận diện được trong file phân phối;
- image SBOM: component trong container image, gồm cả OS/runtime layer.

Hãy ghi rõ scope và subject. Không gọi SBOM của source project là SBOM đầy đủ của container image.

### 12.2. Artifact thay đổi thì SBOM cũng cần được cập nhật

Nếu artifact thay đổi do dependency upgrade, rebuild khác input hoặc thay đổi packaging, SBOM cần được tạo lại và gắn với digest mới. Không tái sử dụng SBOM cũ chỉ vì tên/version sản phẩm giống nhau.

Release version nên bất biến. Nếu cùng version được ghi đè bằng nội dung mới, việc đối chiếu SBOM và binary sẽ mất tin cậy.

### 12.3. Lưu SBOM cạnh artifact

Một release package có thể chứa:

~~~text
release/
├── inventory-service-1.4.0.jar
├── inventory-service-1.4.0.cdx.json
├── inventory-service-1.4.0.spdx.json
├── SHA256SUMS
└── provenance.json
~~~

Có thể lưu SBOM trong artifact repository, registry hoặc hệ thống quản lý supply chain riêng. Điều quan trọng là consumer có thể tìm được SBOM theo version/digest và xác minh nó thuộc artifact đang sử dụng.

## 13. Truy vết dependency từ source đến production

Truy vết dependency là khả năng nối các bước:

~~~text
Source commit
   |
   v
Build configuration and dependency constraints
   |
   v
Resolved dependency graph
   |
   v
Packaged artifact
   |
   v
SBOM + artifact digest + build provenance
   |
   v
Artifact repository / container registry
   |
   v
Deployment record
~~~

Khi một advisory xuất hiện, nhóm có thể đi ngược từ component trong SBOM đến artifact, release, deployment và source revision.

### 13.1. Những định danh nên ghi nhận

Một bản ghi truy vết hữu ích có thể gồm:

- repository và commit SHA;
- project/module và version;
- dependency coordinates;
- resolved version;
- PURL hoặc định danh component;
- direct/transitive relationship;
- repository nguồn;
- hash của dependency khi có;
- build tool, JDK và plugin version;
- artifact digest;
- SBOM serial/version và digest;
- build run ID;
- deployment environment và release ID.

Không phải mọi trường đều phải nhúng vào SBOM. Có thể lưu một phần trong provenance, build metadata hoặc release record, miễn là có liên kết ổn định.

### 13.2. Từ component đến dependency path

Giả sử scanner phát hiện một version của thư viện XML có advisory. Quy trình:

1. Tìm PURL hoặc tọa độ package trong SBOM.
2. Xác định artifact subject và digest.
3. Xem dependency graph để tìm đường dẫn từ ứng dụng tới package.
4. Xác định module khai báo dependency trực tiếp hoặc kéo theo dependency bắc cầu.
5. Xem version constraint/BOM/lockfile quyết định version.
6. Xác định release và deployment đang chứa digest đó.
7. Chọn nâng cấp hoặc biện pháp giảm thiểu.
8. Build artifact mới, tạo SBOM mới và xác minh digest.
9. Phát hành/deploy bản sửa theo quy trình.

Nhờ dependency path, nhóm biết nên nâng thư viện cha hay override một dependency bắc cầu có kiểm soát.

## 14. Dependency locking và verification bổ trợ SBOM

SBOM cho biết component nào được nhận diện trong sản phẩm. Dependency locking và verification giúp giải thích build đã chọn và tải component nào.

### 14.1. Gradle dependency locking

Gradle dependency locking ghi lại version đã resolve cho các configuration được khóa:

~~~kotlin
dependencyLocking {
    lockAllConfigurations()
}
~~~

Tạo hoặc cập nhật lock state theo workflow của project:

~~~bash
./gradlew dependencies --write-locks
~~~

Lockfile giúp các lần build sau dùng graph đã khóa trong phạm vi cấu hình. Khi dependency graph thay đổi có chủ đích, review lockfile như một phần của thay đổi source.

### 14.2. Gradle dependency verification

Gradle dependency verification có thể kiểm tra checksum hoặc chữ ký của artifact tải về theo metadata verification được quản lý trong repository.

Hai cơ chế bổ sung nhau:

- locking kiểm soát version được chọn;
- verification kiểm tra nội dung artifact tải về.

SBOM sau đó mô tả component đã resolve hoặc được nhận diện trong sản phẩm. Ba dữ liệu này hỗ trợ các câu hỏi khác nhau và không thay thế nhau.

### 14.3. Maven dependency management

Maven có thể quản lý version bằng dependencyManagement, parent POM và BOM. Hãy pin version của dependency/plugin và tránh version range hoặc snapshot mutable trong release build nếu mục tiêu là tái lập.

Maven local repository và remote repository metadata ảnh hưởng việc resolve. Release repository nên áp dụng chính sách version bất biến và lưu artifact có thể truy xuất lại.

### 14.4. Hash và repository origin

Nếu SBOM hoặc build record có hash dependency, nhóm có thể đối chiếu nội dung đã tải với artifact trong repository. Nếu cần truy vết nguồn, hãy ghi nhận repository/mirror hoặc provenance của dependency khi hệ thống có cung cấp.

PURL không cho biết file đến từ repository nào. Tọa độ Maven cũng không tự chứng minh file chưa bị thay thế. Hash và nguồn cung cấp bổ sung thông tin đó.

## 15. SBOM trong quy trình quét lỗ hổng

SBOM có thể được đưa vào scanner để đối chiếu với vulnerability database/advisory feed.

Quy trình điển hình:

1. tạo SBOM cho artifact;
2. validate schema và subject;
3. gửi SBOM vào scanner;
4. đối chiếu package/version với advisory;
5. đánh giá severity và điều kiện ảnh hưởng;
6. xác định dependency path và phạm vi deployment;
7. tạo ticket hoặc remediation plan;
8. cập nhật dependency và build artifact mới;
9. tạo SBOM mới, scan lại và lưu kết quả.

### 15.1. CVE không tự động có nghĩa ứng dụng bị khai thác

Một component có CVE chưa chắc mọi ứng dụng chứa component đó đều có thể bị khai thác. Cần xem:

- version range bị ảnh hưởng;
- code path có sử dụng chức năng lỗi không;
- cấu hình có kích hoạt điều kiện nguy hiểm không;
- component có nằm trong runtime artifact không;
- có bản vá hoặc mitigation nào được áp dụng không;
- advisory có chính xác với package ecosystem/version đang dùng không.

Không nên bỏ qua CVE chỉ vì dependency là bắc cầu hoặc không được nhóm gọi trực tiếp. Cũng không nên kết luận ứng dụng exploitable chỉ từ việc tên package xuất hiện trong SBOM.

### 15.2. VEX

Vulnerability Exploitability eXchange (VEX) là cách trao đổi trạng thái ảnh hưởng/exploitability của vulnerability đối với một sản phẩm hoặc component cụ thể.

VEX có thể giúp giải thích rằng một vulnerability:

- đang bị ảnh hưởng;
- không bị ảnh hưởng trong cấu hình/sản phẩm đã đánh giá;
- chưa xác định;
- đã được khắc phục.

Kết luận VEX cần bằng chứng và phạm vi rõ ràng. Nếu lý do “not affected” dựa trên code path không được gọi, cần lưu phân tích để có thể xem xét lại khi sản phẩm thay đổi.

### 15.3. Advisory database thay đổi theo thời gian

Artifact không đổi nhưng kết quả scan có thể đổi vì vulnerability database được cập nhật. Do đó:

- scan khi build/release;
- định kỳ scan lại SBOM của các release còn được triển khai;
- lưu ngày và version dữ liệu scanner;
- liên kết finding với artifact digest;
- không coi kết quả scan cũ là bảo đảm cho hiện tại.

## 16. License compliance từ SBOM

Dependency có thể mang license và nghĩa vụ phân phối khác nhau. SBOM hỗ trợ kiểm kê license, nhưng dữ liệu license có thể thiếu hoặc cần xác minh thủ công.

Một quy trình license có thể:

1. thu thập license metadata từ package và source;
2. chuẩn hóa SPDX license identifiers/expressions khi có căn cứ;
3. phát hiện component thiếu license;
4. áp dụng policy allow/deny/review;
5. kiểm tra nghĩa vụ attribution/notice;
6. đóng gói license text và notices theo yêu cầu;
7. lưu quyết định review cùng release.

Không nên suy luận license chỉ từ tên artifact hoặc publisher. Nếu metadata mâu thuẫn, cần xem file LICENSE/NOTICE và nguồn chính thức của component.

### 16.1. License expression

Một component có thể có nhiều lựa chọn license hoặc điều kiện kết hợp. SPDX license expression biểu diễn quan hệ như AND/OR khi nguồn metadata hỗ trợ.

Ví dụ minh họa:

~~~text
MIT OR Apache-2.0
~~~

Expression này biểu thị lựa chọn theo điều kiện của package. Cách áp dụng thực tế cần được đội compliance xem xét; không nên coi mọi biểu thức OR là tự động chọn license thuận tiện nhất mà không đọc điều khoản.

### 16.2. SBOM không thay thế file NOTICE/LICENSE

SBOM có thể ghi license identifier và reference. Khi phân phối, dự án vẫn có thể cần kèm LICENSE, NOTICE, attribution hoặc source offer theo nghĩa vụ của component. Hãy giữ các tài liệu phân phối cần thiết trong artifact/distribution.

## 17. Build provenance, attestation và chữ ký

SBOM mô tả thành phần. Provenance mô tả quá trình tạo artifact.

### 17.1. Provenance

Build provenance có thể ghi:

- source repository và revision;
- builder identity;
- build workflow/run;
- build parameters;
- toolchain và dependency context;
- artifact subject digest;
- thời điểm và môi trường build.

Thông tin này giúp trả lời: binary được tạo từ commit nào, bằng builder nào và trong workflow nào?

### 17.2. Attestation

Attestation là một statement có cấu trúc, được gắn với subject và có thể được ký/xác thực. Một attestation có thể mang SBOM hoặc provenance predicate.

Liên kết quan trọng là subject digest: consumer kiểm tra statement đang nói về đúng file/image mà họ tải xuống.

### 17.3. Chữ ký số

Chữ ký số giúp xác minh statement hoặc artifact được ký bởi khóa tương ứng và nội dung chưa bị thay đổi kể từ lúc ký. Người tiêu thụ cần có cách xác định public key hoặc identity nào đáng tin cậy.

Chữ ký không tự chứng minh build process an toàn. Nó chứng minh tính toàn vẹn và quan hệ với signer theo trust policy.

### 17.4. SLSA

SLSA là một framework hướng dẫn tăng cường bảo mật chuỗi cung ứng phần mềm, trong đó provenance và mức độ tin cậy của build platform là những phần quan trọng.

SLSA provenance có thể giúp mô tả source, builder và cách tạo artifact. SBOM và provenance bổ sung cho nhau:

- SBOM: thành phần nào có trong sản phẩm?
- Provenance: sản phẩm được tạo từ đâu và bằng quy trình nào?
- Attestation/signature: bằng chứng đó được gắn với artifact và xác thực ra sao?

Không nên tuyên bố đạt một mức SLSA chỉ vì đã tạo file provenance. Mức bảo đảm còn phụ thuộc cách ly builder, tính toàn vẹn pipeline và các yêu cầu khác của framework.

## 18. Tạo SBOM và lưu trong CI

Một pipeline Java có thể tổ chức:

~~~text
Checkout source
      |
      v
Resolve dependencies and build
      |
      v
Run tests
      |
      v
Package artifact
      |
      +----> Generate SBOM
      |          |
      |          v
      |       Validate SBOM
      |          |
      |          v
      |       Scan vulnerabilities/licenses
      |
      v
Calculate artifact digest
      |
      v
Attach SBOM and provenance to digest
      |
      v
Publish immutable artifact and metadata
~~~

Thứ tự chính xác phụ thuộc generator. Nếu SBOM được sinh trước khi artifact đóng gói, cần ghi rõ nó đại diện cho dependency graph nào. Nếu SBOM được sinh bằng cách quét artifact sau package, hãy gắn digest của file đó.

### 18.1. Giữ SBOM khi scan thất bại

Ngay cả khi scanner hoặc policy gate thất bại, pipeline thường vẫn nên lưu SBOM và test reports để phục vụ điều tra. Điều kiện upload report nên cho phép chạy sau khi bước scan/test thất bại, trong khi publish release vẫn bị chặn theo policy.

### 18.2. Tách generate, validate, scan và publish

Các bước có trách nhiệm khác nhau:

- generate tạo inventory;
- validate kiểm tra schema và trường bắt buộc;
- scan đối chiếu vulnerability/license;
- policy gate quyết định có được phát hành không;
- publish lưu artifact và metadata;
- sign/attest gắn bằng chứng xác thực.

Tách các bước giúp biết lỗi do generator, schema, scanner, policy hay repository.

### 18.3. Ví dụ lệnh kiểm tra dependency và sinh BOM

Maven:

~~~bash
./mvnw dependency:tree -Dverbose
./mvnw org.cyclonedx:cyclonedx-maven-plugin:VERSION:makeBom
~~~

Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew cyclonedxBom
~~~

Trong Maven, thay VERSION bằng version CycloneDX plugin đã pin. Trong Gradle, task cần plugin CycloneDX đã được khai báo và cấu hình đúng. Sau khi chạy, xác định chính xác output file, schema version và phạm vi dependency.

## 19. Policy gate cho SBOM

Một tổ chức có thể đặt policy để quyết định artifact nào được phát hành.

Ví dụ policy:

| Điều kiện | Hành động có thể áp dụng |
|---|---|
| SBOM không hợp lệ hoặc thiếu subject | Chặn publish |
| Component không có version/định danh | Yêu cầu review hoặc bổ sung metadata |
| Critical vulnerability đã xác nhận ảnh hưởng | Chặn release hoặc yêu cầu exception có phê duyệt |
| High vulnerability có mitigation | Review theo SLA và policy |
| License bị cấm | Chặn hoặc yêu cầu thay thế |
| License chưa xác định | Yêu cầu compliance review |
| Dependency từ repository không được phép | Chặn hoặc điều tra nguồn |
| SBOM digest không khớp artifact | Chặn publish |

Mức severity chỉ là một tín hiệu. Policy cần xét exploitability, runtime presence, exposure, mitigation và thời hạn khắc phục.

### 19.1. Exception cần có thời hạn

Nếu chấp nhận tạm thời một finding:

- ghi rõ component và version;
- ghi advisory/finding ID;
- nêu lý do và bằng chứng;
- chỉ rõ artifact/release bị ảnh hưởng;
- có owner;
- có hạn xem xét lại;
- xác định mitigation hoặc kế hoạch nâng cấp.

Không dùng suppression vô thời hạn vì nó làm scanner mất khả năng cảnh báo khi sản phẩm hoặc threat landscape thay đổi.

### 19.2. SBOM policy không thay thế review kỹ thuật

Một finding có thể cần developer xác định dependency path và test regression. Một license issue có thể cần chuyên gia compliance. Policy gate nên định tuyến finding đến đúng người có trách nhiệm, không tự động đưa ra kết luận pháp lý hoặc kỹ thuật khi dữ liệu chưa đủ.

## 20. So sánh SBOM giữa các release

SBOM diff giúp phát hiện component được thêm, nâng version, loại bỏ hoặc thay đổi license/hash.

Ví dụ:

~~~text
Release 1.4.0
  jackson-databind 2.17.1
  commons-lang3 3.13.0

Release 1.4.1
  jackson-databind 2.17.2
  commons-lang3 3.14.0
  snakeyaml 2.2
~~~

Diff cho thấy:

- jackson-databind được nâng version;
- commons-lang3 được nâng version;
- snakeyaml được thêm mới.

Nhóm có thể kiểm tra thay đổi này có chủ đích không, package mới đến từ dependency nào và license/vulnerability status ra sao.

### 20.1. Theo dõi dependency drift

Dependency drift xảy ra khi graph thay đổi theo thời gian do version động, snapshot, repository metadata hoặc cập nhật BOM. So sánh SBOM giữa các build giúp phát hiện drift ngoài dự kiến.

Release build nên dùng version bất biến và lock/verification phù hợp để tránh graph thay đổi âm thầm.

### 20.2. Theo dõi release đang được triển khai

Không chỉ so sánh release mới nhất. Cần biết digest nào đang chạy trong từng môi trường. Một release cũ có thể vẫn đang được triển khai dù repository đã có bản mới.

Liên kết SBOM với deployment record giúp trả lời sản phẩm nào đang chứa component bị ảnh hưởng.

## 21. Chất lượng và giới hạn của SBOM

SBOM có thể thiếu hoặc sai do:

- generator chỉ đọc dependency graph mà không quét artifact;
- dependency bị shade/relocate hoặc nested JAR không được nhận diện;
- component nội bộ không có metadata chuẩn;
- license field không đầy đủ;
- dependency runtime được cung cấp bởi server nhưng không nằm trong package;
- image có package OS mà application SBOM không biết;
- generator hoặc schema version cũ;
- package metadata repository không chính xác;
- file binary không có package metadata để nhận diện.

### 21.1. Kiểm tra độ đầy đủ

Hãy kiểm tra:

- tên/version của project root đúng không;
- direct và transitive dependency có được ghi không;
- component count có hợp lý so với dependency graph không;
- test scope có bị trộn vào runtime scope không;
- package được nhúng có được nhận diện không;
- component nội bộ có định danh không;
- license/hash có trường nào bị thiếu không;
- dependency relationships có hợp lý không;
- SBOM có gắn với đúng artifact digest không.

Không đặt ngưỡng component count máy móc cho mọi project. Một project nhỏ có thể có ít component; điều quan trọng là sự phù hợp với dependency graph và sản phẩm thực tế.

### 21.2. False positive và false negative

False positive xảy ra khi scanner ánh xạ nhầm package hoặc version vào advisory không áp dụng. False negative xảy ra khi component bị bỏ sót hoặc không được nhận diện.

Để giảm sai lệch:

- dùng định danh package rõ ràng như PURL;
- giữ version và hash khi có;
- kiểm tra source metadata;
- đối chiếu dependency graph với archive;
- cập nhật scanner/advisory database;
- review finding quan trọng bằng bằng chứng kỹ thuật.

### 21.3. SBOM không tự cập nhật

SBOM là snapshot tại thời điểm tạo. Nếu advisory mới xuất hiện, nội dung SBOM không tự thay đổi. Scanner có thể đánh giá lại cùng SBOM với dữ liệu mới, nhưng khi artifact thay đổi thì phải tạo SBOM mới.

## 22. Bảo vệ tính toàn vẹn và quyền truy cập

SBOM có thể tiết lộ:

- thư viện nội bộ;
- phiên bản framework;
- cấu trúc module;
- dependency chưa công bố;
- thành phần dễ bị tấn công;
- thông tin repository hoặc supplier.

Không phải mọi SBOM đều là bí mật, nhưng cần xác định audience và chính sách phân phối.

Các biện pháp:

- chỉ công bố SBOM ở nơi phù hợp với chính sách sản phẩm;
- kiểm soát quyền truy cập vào SBOM nội bộ;
- không nhúng credential/token hoặc thông tin môi trường nhạy cảm;
- lưu file cùng artifact trong repository có audit trail;
- ký hoặc attest metadata khi cần xác minh nguồn;
- dùng digest để phát hiện thay đổi;
- giữ lịch sử release/SBOM để phục vụ incident response.

SBOM không nên chứa secret. Nếu generator đưa đường dẫn máy, username hoặc thông tin build nhạy cảm vào metadata, cần cấu hình hoặc lọc theo chính sách trước khi phân phối.

## 23. Ví dụ truy vết một lỗ hổng trong dependency bắc cầu

Giả sử scanner báo một version của thư viện HTTP có lỗ hổng. Quy trình điều tra:

**Bước 1 — Định danh component.** Lấy PURL, version và hash từ SBOM. Xác nhận package ecosystem và version đúng.

**Bước 2 — Xác định artifact.** Tìm artifact subject và SHA-256 mà SBOM mô tả. Kiểm tra release và deployment nào đang dùng digest này.

**Bước 3 — Tìm dependency path.** Dùng Maven dependency:tree hoặc Gradle dependencyInsight để xem package được kéo vào qua thư viện cha nào.

**Bước 4 — Xác định scope.** Kiểm tra component nằm trong runtime artifact, test-only graph hay do container/runtime cung cấp.

**Bước 5 — Đọc advisory.** Kiểm tra version range, điều kiện ảnh hưởng, mức độ nghiêm trọng và bản vá.

**Bước 6 — Chọn cách xử lý.** Nâng dependency cha, cập nhật BOM/constraint, loại bỏ dependency không cần hoặc dùng mitigation có kiểm soát.

**Bước 7 — Kiểm thử.** Chạy unit/integration test liên quan để bảo đảm thay đổi không làm hỏng API hoặc hành vi.

**Bước 8 — Tạo artifact mới.** Build với version mới, tạo SBOM mới và tính digest mới.

**Bước 9 — Scan và publish.** Đối chiếu finding đã được xử lý, lưu provenance/attestation và publish đúng artifact.

**Bước 10 — Theo dõi triển khai.** Xác nhận môi trường đã chuyển sang digest mới; không coi việc publish bản sửa là bằng chứng mọi deployment đã cập nhật.

## 24. Quy trình triển khai SBOM cho nhóm Java

Một lộ trình thực tế:

1. **Chọn phạm vi:** module, runtime application, distribution, WAR hay container image.
2. **Chọn format:** SPDX hoặc CycloneDX theo hệ thống tiêu thụ.
3. **Chọn generator:** pin version và xác nhận hỗ trợ Maven/Gradle configuration.
4. **Xác định dependency scope:** runtime, compile, test hoặc image packages.
5. **Tạo dependency graph:** lưu kết quả resolve để có thể điều tra.
6. **Sinh SBOM:** tạo file theo schema version được chấp nhận.
7. **Validate:** kiểm tra cấu trúc, metadata, component và relationship.
8. **Đối chiếu artifact:** kiểm tra package được nhúng và digest của subject.
9. **Scan:** vulnerability, license và policy.
10. **Triage:** phân loại finding, dependency path và exploitability.
11. **Lưu metadata:** SBOM, checksum, provenance, build ID và source revision.
12. **Ký/attest:** gắn bằng chứng xác thực khi quy trình yêu cầu.
13. **Publish:** lưu artifact và SBOM cùng version/digest bất biến.
14. **Rescan:** đánh giá lại release còn được sử dụng khi advisory database thay đổi.
15. **Theo dõi deployment:** xác định môi trường nào đang chạy digest nào.

Không cần triển khai mọi công cụ cùng một lúc. Có thể bắt đầu bằng dependency graph và SBOM runtime, sau đó bổ sung validation, scanning, provenance, signing và deployment inventory.

## 25. Bài tập thực hành

### Bài 1 — Xem dependency graph Maven

Trong một project Maven, chạy:

~~~bash
./mvnw dependency:tree -Dverbose
~~~

Chọn một dependency bắc cầu và ghi lại đường dẫn từ project root đến component. Xem version nào được chọn và có version nào bị loại do conflict.

### Bài 2 — Xem dependency graph Gradle

Chạy:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency jackson-databind --configuration runtimeClasspath
~~~

Ghi lại dependency path và lý do version được chọn. So sánh runtimeClasspath với testRuntimeClasspath.

### Bài 3 — Tạo SBOM CycloneDX

Thêm CycloneDX plugin với version được pin vào project Maven hoặc Gradle. Chạy goal/task tạo BOM, xác định output file, schema version và phạm vi dependency. Validate file bằng tool tương thích.

### Bài 4 — So sánh dependency graph với archive

Tạo JAR hoặc WAR. Liệt kê nội dung archive và so sánh với dependency graph. Xác định dependency nào được đóng gói, dependency nào chỉ dùng khi test hoặc do container cung cấp.

### Bài 5 — Định danh component bằng PURL

Chọn một Maven dependency và viết PURL theo ecosystem Maven. Xác định groupId, artifactId và version. Tìm hash của file JAR local nếu có và ghi lại cùng tọa độ.

### Bài 6 — So sánh SBOM giữa hai release

Tạo hai SBOM từ hai version project khác nhau. Tìm component được thêm, xóa, nâng version hoặc đổi license metadata. Giải thích thay đổi nào là chủ đích.

### Bài 7 — Tạo release record

Tạo một record liên kết source commit, artifact name/version, SHA-256, SBOM file, generator version và build run ID. Xác nhận có thể từ digest tìm ra đúng SBOM và source revision.

### Bài 8 — Triage một advisory

Chọn một advisory công khai trong môi trường thử nghiệm. Tìm package/version trong SBOM, truy vết dependency path, xác định scope và ghi kế hoạch nâng cấp. Sau khi thay dependency, tạo lại SBOM và so sánh.

### Bài 9 — Phân biệt SBOM và provenance

Viết hai record riêng: một SBOM liệt kê component, một provenance record mô tả source/builder/build parameters. Gắn cả hai với cùng artifact digest và giải thích mỗi record chứng minh điều gì.

### Bài 10 — Lập policy gate

Định nghĩa policy cho SBOM không hợp lệ, critical vulnerability, license chưa xác định và component từ repository không được phép. Xác định trường hợp nào chặn release, trường hợp nào cần review và cách lưu exception có thời hạn.

## 26. Câu hỏi tự kiểm tra

1. SBOM là gì và nó giúp trả lời những câu hỏi nào?
2. SBOM khác Maven BOM như thế nào?
3. SPDX và CycloneDX là hai định dạng/chuẩn phục vụ mục tiêu gì?
4. PURL giúp định danh package ra sao?
5. Vì sao package URL và version chưa đủ để chứng minh nội dung JAR?
6. Dependency trực tiếp khác dependency bắc cầu như thế nào?
7. Maven dependency:tree và Gradle dependencyInsight hỗ trợ truy vết ra sao?
8. Vì sao effective POM không phải SBOM?
9. Compile classpath, runtime classpath và test classpath khác nhau như thế nào?
10. Vì sao dependency graph chưa chắc phản ánh chính xác mọi component trong fat JAR hoặc container image?
11. SBOM của JAR khác SBOM của container image ở phạm vi nào?
12. Làm thế nào gắn SBOM với đúng artifact bằng digest?
13. Dependency locking và dependency verification bổ trợ SBOM như thế nào?
14. SBOM, vulnerability scan và VEX có vai trò khác nhau ra sao?
15. Vì sao advisory database thay đổi có thể làm kết quả scan thay đổi dù artifact không đổi?
16. SBOM hỗ trợ license compliance nhưng không thay thế tài liệu LICENSE/NOTICE như thế nào?
17. Provenance khác SBOM ở câu hỏi nào?
18. Attestation và chữ ký giúp xác minh điều gì?
19. Vì sao cần rescan các release cũ còn đang triển khai?
20. Làm thế nào truy từ finding đến dependency path, artifact digest và deployment?

SBOM giúp nhóm biết sản phẩm chứa những component nào; dependency graph giải thích chúng được đưa vào qua đường nào; digest liên kết inventory với binary cụ thể; provenance mô tả cách binary được tạo. Khi các dữ liệu này được tạo, kiểm tra và lưu cùng release một cách nhất quán, nhóm có thể điều tra lỗ hổng, đánh giá license và xác định phạm vi ảnh hưởng mà không phải suy đoán từ danh sách dependency trong source.
