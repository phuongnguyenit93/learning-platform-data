# Theo dõi cập nhật bảo mật cho toàn bộ hệ dependency Jackson

Jackson thường được thêm vào dự án như một thư viện JSON, nhưng trong ứng dụng thực tế nó có thể là cả một nhóm dependency: core parser/generator, databind, annotations, module xử lý ngày giờ, dataformat, module ngôn ngữ và các adapter tích hợp framework. Một lỗ hổng có thể ảnh hưởng đến một artifact cụ thể, một nhóm phiên bản hoặc một cách cấu hình nhất định. Vì vậy, chỉ kiểm tra phiên bản jackson-databind trong file build không đủ để biết ứng dụng đã được cập nhật an toàn hay chưa.

Theo dõi bảo mật cần bao phủ toàn bộ dependency Jackson thực sự được resolve và đóng gói, kể cả dependency bắc cầu do framework hoặc thư viện khác kéo vào. Quy trình tốt phải nối được các bước: lập inventory, nhận advisory, xác định phiên bản bị ảnh hưởng, đánh giá mức phơi nhiễm, nâng cấp đồng bộ, chạy kiểm thử và xác nhận artifact triển khai không còn phiên bản dễ bị tổn thương.

Mục tiêu không phải là nâng mọi thư viện lên phiên bản mới nhất ngay khi có release. Mục tiêu là biết ứng dụng đang dùng những gì, phát hiện bản cập nhật bảo mật kịp thời, chọn phiên bản đã sửa phù hợp với major line đang hỗ trợ và chứng minh bản build cuối cùng đã nhận được bản sửa.

## 1. Vì sao phải theo dõi toàn bộ hệ dependency Jackson?

Jackson là một dự án nhiều module. Ứng dụng có thể dùng trực tiếp ObjectMapper từ databind nhưng dữ liệu vẫn đi qua parser trong core, annotation được đọc từ annotations, hoặc được xử lý bởi module dành cho Java time, YAML, XML, CSV, Kotlin hay framework.

Các thành phần phổ biến:

| Nhóm | Artifact hoặc loại module thường gặp | Vai trò |
|---|---|---|
| Core | jackson-core | Streaming API, JsonParser, JsonGenerator và nền tảng đọc/ghi |
| Annotation | jackson-annotations | Các annotation như JsonProperty, JsonTypeInfo, JsonCreator |
| Databind | jackson-databind | ObjectMapper, serializer, deserializer và Tree Model |
| Datatype | jackson-datatype-jsr310, jackson-datatype-jdk8 | Java Time, Optional và kiểu dữ liệu Java bổ sung |
| Dataformat | jackson-dataformat-yaml, xml, csv, cbor, smile | Đọc/ghi định dạng ngoài JSON text |
| Module | jackson-module-parameter-names, kotlin, blackbird, afterburner | Tích hợp ngôn ngữ hoặc tối ưu binding |
| Framework adapter | Các module JAX-RS/Jakarta REST, JAXB và tích hợp khác | Kết nối Jackson với framework hoặc API |
| Extension | Các module cộng đồng hoặc nội bộ | Hỗ trợ kiểu và giao thức đặc thù |

Danh sách trên chỉ là ví dụ. Thành phần thực tế phụ thuộc vào stack và dependency graph của dự án. Tên artifact và groupId có thể thay đổi giữa các major line; cần kiểm tra tọa độ dependency đang được build resolve thay vì suy luận từ tên package Java.

Một số lý do khiến việc kiểm tra một artifact đơn lẻ không đủ:

- Framework có thể kéo một phiên bản jackson-core khác với phiên bản databind khai báo trực tiếp.
- Một module dataformat có thể có dependency bắc cầu riêng.
- Một starter hoặc adapter có thể đưa Jackson vào runtime dù dự án không khai báo trực tiếp.
- Fat JAR, container hoặc plugin có thể chứa một bản Jackson khác với classpath test.
- Ứng dụng có thể dùng YAML/XML/CSV parser ngoài đường đi JSON chính.
- Một thư viện có thể đóng gói hoặc relocate Jackson classes, khiến dependency tree thông thường chưa thể hiện đầy đủ nội dung trong artifact cuối.

Vì vậy, inventory cần trả lời cả hai câu hỏi: build resolve những dependency nào và sản phẩm được triển khai thực sự chứa những gì.

## 2. Phân biệt dependency trực tiếp và dependency bắc cầu

Dependency trực tiếp là dependency được khai báo trong file build của dự án. Dependency bắc cầu (transitive dependency) được đưa vào bởi một thư viện khác.

Ví dụ Maven:

~~~xml
<dependencies>
    <dependency>
        <groupId>com.fasterxml.jackson.core</groupId>
        <artifactId>jackson-databind</artifactId>
        <version>...</version>
    </dependency>

    <dependency>
        <groupId>com.fasterxml.jackson.dataformat</groupId>
        <artifactId>jackson-dataformat-yaml</artifactId>
        <version>...</version>
    </dependency>
</dependencies>
~~~

Dự án có thể không khai báo jackson-core trực tiếp nhưng vẫn nhận nó qua jackson-databind. Một framework khác cũng có thể mang thêm một phiên bản hoặc constraint khác.

Ví dụ Gradle:

~~~kotlin
dependencies {
    implementation("com.fasterxml.jackson.core:jackson-databind:<version>")
    implementation("com.fasterxml.jackson.dataformat:jackson-dataformat-yaml:<version>")
}
~~~

Các dòng trên chỉ minh họa cấu trúc khai báo. Không sao chép dấu placeholder thành phiên bản thật; hãy dùng BOM hoặc phiên bản đã được phê duyệt cho major line của dự án.

### 2.1. Dependency tree là nguồn inventory đầu tiên

Maven:

~~~bash
mvn dependency:tree
~~~

Có thể lọc một artifact để xem đường dependency:

~~~bash
mvn dependency:tree -Dincludes=com.fasterxml.jackson.core:jackson-databind
~~~

Lặp lại cho các artifact Jackson quan trọng hoặc dùng filter phù hợp với phiên bản Maven/plugin đang dùng. Khi cần xem cấu hình dependency đã hợp nhất từ parent POM và profile, kiểm tra effective POM:

~~~bash
mvn help:effective-pom
~~~

Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Xem vì sao một dependency được chọn:

~~~bash
./gradlew dependencyInsight \
    --dependency jackson-databind \
    --configuration runtimeClasspath
~~~

Có thể chạy dependencyInsight cho từng artifact Jackson cần điều tra, chẳng hạn jackson-core, jackson-annotations và module dataformat.

Dependency tree giúp phát hiện:

- Artifact Jackson nào xuất hiện.
- Phiên bản nào được chọn.
- Dependency nào kéo artifact đó vào.
- Có xung đột phiên bản hoặc constraint không.
- Một module có bị thay thế bởi version khác trong quá trình resolution không.

Đừng chỉ xem compileClasspath. Một thư viện có thể chỉ xuất hiện ở runtimeClasspath, testRuntimeClasspath, plugin classpath hoặc trong image triển khai.

### 2.2. Kiểm tra nhiều configuration và profile

Dự án có thể có:

- Maven profiles khác nhau theo môi trường.
- Gradle configurations như runtimeClasspath, testRuntimeClasspath, integrationTestRuntimeClasspath.
- Application plugin hoặc custom distribution.
- Plugin build chạy trong classloader riêng.
- Dependency chỉ được thêm trong container image hoặc layer đóng gói.

Hãy kiểm tra configuration gần với cách ứng dụng chạy thật. Một kết quả từ dependency tree ở local không đại diện cho mọi môi trường nếu CI bật profile khác hoặc build production dùng dependency constraints khác.

## 3. Lập danh mục tất cả artifact Jackson

Nên duy trì một inventory có thể tái tạo từ build thay vì ghi thủ công một danh sách phiên bản trong wiki.

Một bản inventory tối thiểu nên có:

| Trường | Ý nghĩa |
|---|---|
| GroupId | Namespace của artifact |
| ArtifactId | Tên module |
| Resolved version | Phiên bản thực tế được chọn |
| Scope/configuration | Compile, runtime, test hoặc plugin |
| Direct/transitive | Được khai báo trực tiếp hay kéo vào |
| Introduced by | Dependency dẫn tới artifact |
| Packaged? | Có nằm trong artifact/container triển khai không |
| Owner | Nhóm chịu trách nhiệm nâng cấp |
| Source of version | BOM, constraint, parent POM hoặc khai báo riêng |

Không nên chỉ lọc theo tiền tố artifactId chứa chữ jackson. Một số module có tên khác hoặc được relocate/shade; đồng thời một dependency không thuộc Jackson có thể chứa bản Jackson đã đóng gói bên trong.

### 3.1. Tạo SBOM

Software Bill of Materials (SBOM) liệt kê thành phần phần mềm trong một build hoặc artifact. Có thể dùng định dạng CycloneDX hoặc SPDX tùy công cụ và yêu cầu tổ chức.

SBOM hỗ trợ:

- Ghi nhận tọa độ package và phiên bản.
- Đối chiếu component với advisory/CVE.
- So sánh thành phần giữa hai lần build.
- Kiểm tra dependency bắc cầu.
- Truy vết thành phần trong artifact đã phát hành.
- Cung cấp bằng chứng cho quy trình quản lý lỗ hổng.

SBOM nên được tạo từ build thực tế và lưu cùng thông tin release. Nếu chỉ tạo từ file khai báo dependency, nó có thể bỏ sót version được resolve, dependency đóng gói hoặc thư viện được thêm ở bước đóng gói.

SBOM cũng không tự chứng minh một lỗ hổng có thể khai thác. Nó là inventory đầu vào cho bước đối chiếu và đánh giá.

### 3.2. Kiểm tra artifact cuối

Nếu ứng dụng đóng gói fat JAR, kiểm tra nội dung archive và dependency list đi kèm. Với container, kiểm tra image digest và SBOM của image. Nếu thư viện được copy vào thư mục lib hoặc application server, cần quét cả thư mục đó.

Một dependency tree sạch trong source repository không đủ nếu image production vẫn chứa JAR cũ từ layer cache hoặc thư mục triển khai khác.

## 4. Theo dõi advisory và nguồn thông tin bảo mật

Một quy trình theo dõi cần nhiều nguồn, vì thời điểm công bố, tên package và thông tin affected version có thể khác nhau.

Nguồn nên theo dõi:

- Security advisories chính thức của repository Jackson/FasterXML.
- Release notes và changelog của các module liên quan.
- CVE/NVD để tra mã lỗ hổng và phạm vi ảnh hưởng.
- OSV để đối chiếu package/version theo hệ sinh thái.
- GitHub Security Advisories và dependency alert của repository.
- Advisory từ nhà cung cấp JDK, framework, Linux distribution hoặc nền tảng runtime.
- Công cụ quản lý dependency như Dependabot, Renovate và vulnerability scanner đang được tổ chức phê duyệt.

Các nguồn có vai trò khác nhau:

| Nguồn | Thông tin hữu ích | Cách dùng |
|---|---|---|
| Jackson/FasterXML advisory | Phạm vi ảnh hưởng và bản sửa do dự án công bố | Nguồn ưu tiên để hiểu vấn đề Jackson |
| Release notes | Thay đổi, fix, dependency alignment và migration note | Xác nhận bản release chứa sửa lỗi |
| CVE/NVD | Mã CVE, mô tả và đánh giá mức độ | Tra cứu và liên kết báo cáo |
| OSV | Đối chiếu package version và affected range | Tự động hóa scanner/SBOM |
| Dependabot/Renovate | Phát hiện dependency cũ và tạo update PR | Tạo luồng cập nhật liên tục |
| Scanner của tổ chức | Chính sách, risk score và báo cáo tập trung | Theo dõi SLA và trạng thái remediation |
| Vendor/framework advisory | Ảnh hưởng qua bản phân phối hoặc integration | Kiểm tra stack triển khai thực tế |

Không dùng một nguồn duy nhất làm bằng chứng cuối cùng. Scanner có thể chậm cập nhật, advisory có thể sửa affected range sau khi công bố, và một bản release có thể chứa fix nhưng chưa được scanner nhận diện ngay.

### 4.1. Theo dõi đúng repository và release line

Theo dõi repository chính thức của Jackson và các module mà ứng dụng sử dụng. Đừng chỉ theo dõi release của databind nếu dự án còn dùng YAML, XML, CSV, Kotlin hoặc adapter khác.

Khi nhận thông báo, ghi lại:

- Advisory/CVE identifier.
- Ngày công bố và ngày cập nhật gần nhất.
- Các artifact bị ảnh hưởng.
- Affected version range.
- Phiên bản đã sửa (fixed version) theo advisory.
- Điều kiện khai thác hoặc cấu hình liên quan.
- Workaround nếu có.
- Release note hoặc commit tham chiếu.
- Ngày nhóm ứng dụng xác nhận remediation.

Nếu advisory được cập nhật, phải xem lại đánh giá. Không giữ kết luận cũ chỉ vì ticket đã được tạo.

### 4.2. Không coi mọi dependency update là security fix

Một release mới có thể chứa bug fix, feature, performance improvement hoặc security fix. Ngược lại, một bản sửa bảo mật có thể được phát hành trong một patch release của major/minor line đang hỗ trợ.

Khi tạo update PR, cần phân biệt:

- Security update: giải quyết một advisory cụ thể.
- Routine update: nâng phiên bản để giảm độ trễ dependency.
- Major upgrade: thay đổi có thể cần migration.
- Dependency alignment: đồng bộ các module về một release line tương thích.

Ticket remediation nên liên kết tới advisory và fixed version, không chỉ ghi "upgrade Jackson".

## 5. Thiết lập theo dõi tự động

Theo dõi thủ công dễ bỏ sót advisory, đặc biệt khi dự án có nhiều module. Có thể kết hợp scanner trong CI với bot cập nhật dependency và dashboard tập trung.

### 5.1. Dependabot hoặc Renovate

Các công cụ này có thể:

- Theo dõi dependency trực tiếp và bắc cầu theo khả năng hỗ trợ.
- Phát hiện version mới.
- Tạo pull request nâng cấp.
- Gom nhóm update theo package hoặc ecosystem.
- Gắn nhãn security update.
- Chạy CI trên thay đổi dependency.

Cấu hình nên có quy tắc cho toàn bộ nhóm Jackson artifact mà dự án dùng. Đừng chỉ tạo rule cho jackson-databind nếu runtime còn có nhiều module khác.

Nếu gom nhóm các artifact, cần bảo đảm bot cập nhật version đồng bộ theo BOM. Một PR riêng cho từng module có thể tạm tạo ra dependency set không tương thích nếu merge từng phần.

### 5.2. Scanner trong CI

Chạy dependency vulnerability scan trong pipeline ở các thời điểm:

- Pull request có thay đổi dependency.
- Build chính trên nhánh được bảo vệ.
- Build release.
- Theo lịch định kỳ kể cả khi source code không đổi.

Ví dụ lịch vận hành có thể gồm scan hằng ngày và scan bắt buộc trước release. Tần suất cụ thể theo chính sách bảo mật của tổ chức; advisory nghiêm trọng cần xử lý theo SLA khẩn cấp, không chờ đến lịch review tiếp theo.

CI nên xuất kết quả máy đọc được để so sánh qua build, tạo ticket và kiểm tra trạng thái remediation.

### 5.3. Quản lý cảnh báo và suppression

Scanner có thể tạo false positive hoặc cảnh báo không áp dụng. Nếu cần suppression:

- Ghi lý do cụ thể.
- Gắn người chịu trách nhiệm.
- Đặt ngày hết hạn/review.
- Liên kết advisory và bằng chứng affected path không tồn tại hoặc điều kiện khai thác không áp dụng.
- Không suppression chỉ vì test chưa thất bại.
- Không suppression vô thời hạn.

Một test pass không chứng minh dependency không có lỗ hổng. Security scanner và test suite trả lời hai câu hỏi khác nhau.

## 6. Đánh giá advisory có ảnh hưởng đến ứng dụng không

Khi có cảnh báo, không nên chỉ so sánh số version bằng mắt. Cần đối chiếu chính xác package coordinate và affected range.

Quy trình đánh giá:

1. Xác định advisory đang nói tới artifact nào.
2. Xác định version được resolve trong từng runtime/build configuration.
3. Đối chiếu affected range và fixed version từ nguồn chính thức.
4. Xác định artifact có nằm trong sản phẩm triển khai hay không.
5. Tìm đường code sử dụng thành phần bị ảnh hưởng.
6. Xem điều kiện khai thác có tồn tại trong deployment không.
7. Xác định workaround hoặc mitigation tạm thời.
8. Ước lượng mức phơi nhiễm và deadline remediation.

Ví dụ, advisory chỉ áp dụng cho một dataformat module mà ứng dụng không sử dụng và không đóng gói. Điều đó có thể giảm mức phơi nhiễm, nhưng phải có bằng chứng từ dependency tree và artifact scan. Không suy luận "không gọi API đó" nếu module vẫn được expose qua endpoint khác hoặc framework.

### 6.1. Đánh giá theo điều kiện khai thác

Một lỗ hổng trong deserialization có thể phụ thuộc:

- Input đến từ người dùng hay nguồn tin cậy.
- Có bật polymorphic typing hoặc default typing không.
- Có dùng subtype/extension cụ thể không.
- Parser có xử lý dữ liệu lớn hoặc lồng sâu không.
- Endpoint có thể truy cập từ internet không.
- Dữ liệu được xử lý đồng bộ hay qua queue.
- Có giới hạn kích thước, timeout và nesting không.

Một lỗ hổng có điều kiện khai thác không đồng nghĩa nó vô hại nếu ứng dụng hiện chưa dùng đường code liên quan. Cấu hình có thể thay đổi, endpoint mới có thể xuất hiện và payload từ broker cũng có thể không đáng tin.

### 6.2. Phân biệt severity và priority

CVSS là một đầu vào, không phải toàn bộ quyết định ưu tiên. Cần xem:

- Mức độ nghiêm trọng của advisory.
- Có exploit công khai hoặc đang bị khai thác hay không.
- Endpoint có phơi ra input không tin cậy không.
- Artifact có trong production không.
- Code path bị ảnh hưởng có reachable không.
- Có workaround đáng tin không.
- Tác động nếu bị khai thác.
- Khả năng triển khai bản sửa nhanh.

Một CVE có điểm cao nhưng artifact không được đóng gói có thể có priority khác với một CVE có điểm thấp hơn nhưng nằm trên đường xử lý input công khai. Tuy nhiên, không được bỏ qua advisory chỉ dựa trên giả định reachability chưa được chứng minh.

## 7. Đồng bộ version bằng Jackson BOM

Jackson có nhiều module được phát hành cùng một release line. BOM (Bill of Materials) giúp quản lý phiên bản thống nhất và tránh khai báo version riêng lẻ cho từng artifact.

Maven ví dụ:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.fasterxml.jackson</groupId>
            <artifactId>jackson-bom</artifactId>
            <version>...</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Sau khi import BOM, dependency module có thể bỏ version nếu artifact nằm trong BOM:

~~~xml
<dependencies>
    <dependency>
        <groupId>com.fasterxml.jackson.core</groupId>
        <artifactId>jackson-databind</artifactId>
    </dependency>
    <dependency>
        <groupId>com.fasterxml.jackson.datatype</groupId>
        <artifactId>jackson-datatype-jsr310</artifactId>
    </dependency>
    <dependency>
        <groupId>com.fasterxml.jackson.dataformat</groupId>
        <artifactId>jackson-dataformat-yaml</artifactId>
    </dependency>
</dependencies>
~~~

Gradle Kotlin DSL ví dụ:

~~~kotlin
dependencies {
    implementation(platform("com.fasterxml.jackson:jackson-bom:<version>"))

    implementation("com.fasterxml.jackson.core:jackson-databind")
    implementation("com.fasterxml.jackson.datatype:jackson-datatype-jsr310")
    implementation("com.fasterxml.jackson.dataformat:jackson-dataformat-yaml")
}
~~~

Artifact coordinates của BOM phụ thuộc major line. Ví dụ trên minh họa cách dùng BOM của Jackson 2; khi chuyển sang major line khác, hãy kiểm tra groupId/artifactId chính thức của BOM và module tương ứng trong release documentation.

### 7.1. Vì sao không nên chỉ nâng databind?

jackson-databind phụ thuộc jackson-core và jackson-annotations. Các module khác cũng có thể phụ thuộc các thành phần này.

Nếu chỉ ép databind lên version mới nhưng giữ core hoặc annotations quá cũ, có thể gặp:

- NoSuchMethodError hoặc NoClassDefFoundError.
- API mismatch.
- Hành vi serializer/deserializer khác nhau.
- Một module dataformat không tương thích.
- Classpath chứa nhiều phiên bản không dự kiến.

Dùng BOM hoặc dependency constraints để align các module cùng release line. Sau đó kiểm tra dependency tree để xác nhận version thực tế, vì dependency management có thể bị override bởi parent POM, constraint, resolution strategy hoặc dependency trực tiếp.

### 7.2. Không ép tất cả module có cùng số version nếu release policy không yêu cầu

BOM là nguồn quản lý version được dự án công bố. Hãy dùng version do BOM quản lý cho từng artifact, không tự áp một version string cho mọi module nếu module đó có chu kỳ phát hành khác.

Một số module cộng đồng hoặc adapter có thể không thuộc BOM chính thức. Với chúng, phải kiểm tra compatibility matrix và release notes riêng.

## 8. Xử lý dependency bắc cầu kéo phiên bản cũ

Sau khi import BOM, một thư viện khác có thể khai báo dependency version cũ. Build tool thường giải quyết xung đột theo quy tắc riêng; kết quả cuối phải được kiểm tra.

Maven dependency tree giúp thấy đường kéo vào. Nếu cần loại một dependency cũ, có thể dùng exclusion tại dependency đã đưa nó vào, sau đó khai báo dependency được quản lý đúng version.

~~~xml
<dependency>
    <groupId>com.example</groupId>
    <artifactId>legacy-integration</artifactId>
    <version>...</version>
    <exclusions>
        <exclusion>
            <groupId>com.fasterxml.jackson.core</groupId>
            <artifactId>jackson-databind</artifactId>
        </exclusion>
    </exclusions>
</dependency>
~~~

Chỉ dùng exclusion khi đã xác định dependency mới thay thế tương thích và không phá yêu cầu của thư viện cha. Exclusion không phải bản sửa bảo mật tự thân.

Gradle có thể dùng constraints hoặc platform để quản lý version:

~~~kotlin
dependencies {
    implementation(platform("com.fasterxml.jackson:jackson-bom:<version>"))

    constraints {
        implementation("com.fasterxml.jackson.core:jackson-databind") {
            because("Align Jackson modules with the approved BOM")
        }
    }
}
~~~

Không thêm force rule rộng mà không hiểu tác động. Ép một module lên version không tương thích có thể làm ứng dụng chạy sai hoặc fail lúc runtime.

### 8.1. Kiểm tra version convergence

Sau nâng cấp, cần xác nhận:

- Mỗi artifact Jackson quan trọng resolve đúng version mong đợi.
- Không có bản cũ còn trên runtime classpath.
- Không có duplicate class do shaded/relocated dependency.
- Test runtime và production runtime dùng cùng alignment.
- Container image chứa đúng JAR đã build.

Dependency convergence plugin hoặc Gradle resolution diagnostics có thể giúp phát hiện nhiều version của cùng module. Nhưng phải kết hợp kiểm tra archive/image vì shading có thể che khỏi dependency tree.

## 9. Theo dõi toàn bộ module ngoài core/databind

Không phải mọi lỗ hổng đều nằm trong jackson-databind. Tùy advisory, module cần xem xét có thể thuộc các nhóm:

### 9.1. Core parser/generator

jackson-core xử lý token, buffer, stream, parser và generator. Khi advisory liên quan core, đánh giá tất cả đường đọc/ghi dùng Jackson, kể cả khi ứng dụng chỉ gọi ObjectMapper.

Xem xét payload không tin cậy, input stream lớn, parser constraints, encoding và giới hạn tài nguyên.

### 9.2. Annotation và databind

jackson-annotations ảnh hưởng metadata được databind đọc. jackson-databind điều phối binding, polymorphism, creator, serializer/deserializer và Tree Model.

Các thay đổi bảo mật ở databind cần đặc biệt xem cấu hình polymorphic typing, custom deserializer và input không tin cậy.

### 9.3. Datatype modules

Các module cho Java Time, Optional, JDK types, Hibernate hoặc thư viện bên ngoài có thể có serializer/deserializer riêng. Nếu advisory hoặc release note nêu module cụ thể, hãy kiểm tra module đó và dependency tương ứng.

### 9.4. Dataformat modules

YAML, XML, CSV, CBOR và Smile có parser/format-specific behavior. Nếu ứng dụng nhận các định dạng này, phạm vi rà soát phải bao gồm module thực sự xử lý input. Không giả định một bản sửa trong core tự động giải quyết mọi vấn đề của parser format khác.

### 9.5. Framework và language modules

Kotlin, parameter names, JAXB, JAX-RS/Jakarta REST và các adapter khác có thể ảnh hưởng cách Jackson được khởi tạo hoặc gọi. Kiểm tra release notes, compatibility và transitive dependencies khi nâng chúng.

### 9.6. Module cộng đồng và module nội bộ

Module không thuộc tổ chức FasterXML có thể có maintainer, release cadence và quy trình advisory riêng. Không coi việc nó dùng package com.fasterxml.jackson là bằng chứng nó được cùng team phát hành.

Ghi rõ owner và nguồn advisory cho từng dependency ngoài BOM chính thức.

## 10. Các vùng cấu hình Jackson cần rà soát về bảo mật

Theo dõi version chỉ là một phần. Cấu hình không an toàn có thể làm tăng rủi ro ngay cả khi dependency đã được cập nhật.

### 10.1. Polymorphic deserialization

Không bật default typing rộng cho JSON đến từ nguồn không tin cậy. Tránh để dữ liệu đầu vào quyết định class Java tùy ý thông qua tên class.

Ưu tiên logical type id và subtype allowlist:

~~~java
@JsonTypeInfo(
    use = JsonTypeInfo.Id.NAME,
    include = JsonTypeInfo.As.PROPERTY,
    property = "kind"
)
@JsonSubTypes({
    @JsonSubTypes.Type(value = SafeCardPayload.class, name = "card"),
    @JsonSubTypes.Type(value = SafeBankPayload.class, name = "bank")
})
public interface PaymentPayload {}
~~~

Nếu kiến trúc thực sự cần default typing, phải có PolymorphicTypeValidator với allowlist hẹp và review bảo mật. Không dùng package prefix rộng làm allowlist nếu package chứa nhiều kiểu không được phép khởi tạo.

### 10.2. Không tin vào type id từ producer

Ngay cả logical type id cũng phải được giới hạn trong danh sách subtype được phép. Unknown type cần có chính sách rõ: từ chối, quarantine hoặc giữ raw payload để xử lý sau.

Không biến unknown subtype thành một command mặc định có thể thực hiện giao dịch.

### 10.3. Giới hạn tài nguyên parser

Với Jackson version hỗ trợ StreamReadConstraints, đặt giới hạn phù hợp cho:

- Độ sâu nesting.
- Độ dài string.
- Độ dài number.
- Kích thước request/file ở tầng transport.
- Thời gian xử lý và timeout.

Ví dụ minh họa:

~~~java
StreamReadConstraints constraints =
    StreamReadConstraints.builder()
        .maxNestingDepth(100)
        .maxStringLength(1_000_000)
        .maxNumberLength(1_000)
        .build();

JsonFactory factory = JsonFactory.builder()
    .streamReadConstraints(constraints)
    .build();

ObjectMapper mapper = new ObjectMapper(factory);
~~~

Các giới hạn cần được chọn theo payload hợp lệ của ứng dụng. Không sao chép con số ví dụ vào production mà không đo kích thước dữ liệu thực tế.

StreamReadConstraints không thay thế giới hạn upload, request body, queue message hoặc timeout ở gateway/server.

### 10.4. Custom deserializer và module đăng ký tự động

Rà soát custom deserializer, subtype resolver, module auto-discovery và các extension được nạp từ classpath. Một module có thể thay đổi cách input được chuyển thành object.

Chỉ đăng ký module cần thiết. Kiểm tra nguồn gốc dependency và tránh tự động nạp module không được kiểm soát từ classpath rộng.

### 10.5. Tránh serialize dữ liệu nhạy cảm

Bảo mật không chỉ là deserialize. DTO và serializer có thể vô tình xuất password, token, internal field hoặc dữ liệu cá nhân. Kiểm tra @JsonIgnore, views, filters và custom serializers khi thay đổi module hoặc mapper configuration.

Không ghi toàn bộ payload nhạy cảm vào log khi điều tra security issue. Lưu bằng chứng có kiểm soát và redact dữ liệu.

## 11. Đánh giá phạm vi ảnh hưởng theo đường code

Khi một advisory công bố, lập bảng đối chiếu:

| Câu hỏi | Bằng chứng cần tìm |
|---|---|
| Artifact bị ảnh hưởng có trong build không? | Dependency tree, lockfile, SBOM |
| Có trong production không? | Runtime classpath, fat JAR, image SBOM |
| Input không tin cậy có đi vào parser không? | Endpoint, queue listener, file import |
| Có bật polymorphic typing không? | ObjectMapper builder/config, annotations |
| Có dùng module liên quan không? | Code usage và dependency graph |
| Có giới hạn resource không? | JsonFactory, HTTP/body limits, timeout |
| Có fixed version phù hợp không? | Official advisory và release notes |
| Có workaround đáng tin không? | Advisory, vendor guidance, security review |

Không đánh giá reachability chỉ bằng tìm kiếm tên class. Framework có thể gọi Jackson qua message converter hoặc codec mà source code không gọi ObjectMapper trực tiếp.

Tìm cả:

- ObjectMapper/ObjectReader/ObjectWriter.
- JsonFactory/JsonParser/JsonGenerator.
- Spring HttpMessageConverter hoặc codec.
- JAX-RS/Jakarta REST provider.
- Message listener và serializer của broker.
- File import/export.
- YAML/XML/CSV readers.
- Custom modules và polymorphic annotations.

## 12. Ưu tiên và thời hạn remediation

Một chính sách remediation nên kết hợp mức độ nghiêm trọng với mức phơi nhiễm.

Ví dụ bảng ưu tiên:

| Mức | Tình huống minh họa | Hành động |
|---|---|---|
| Khẩn cấp | Có exploit đang bị khai thác, artifact production bị ảnh hưởng và input không tin cậy có thể tới đường code | Kích hoạt quy trình emergency patch |
| Cao | Advisory nghiêm trọng, module có mặt trong production và điều kiện khai thác khả thi | Ưu tiên update ngay trong SLA cao |
| Trung bình | Có ảnh hưởng nhưng reachability bị giới hạn và có mitigation đã xác minh | Lên lịch nâng cấp sớm, theo dõi mitigation |
| Thấp | Artifact không được đóng gói hoặc điều kiện ảnh hưởng không tồn tại có bằng chứng | Ghi nhận lý do, tiếp tục monitor và review khi build đổi |

Bảng này là khung tham khảo, không thay thế policy/SLA của tổ chức. Nếu advisory có yêu cầu thời hạn cụ thể từ vendor hoặc regulator, áp dụng quy tắc tương ứng.

Một ticket remediation nên chứa:

- Advisory/CVE.
- Artifact và version đang dùng.
- Fixed version mục tiêu.
- Ứng dụng và môi trường bị ảnh hưởng.
- Đường dependency kéo vào.
- Điều kiện khai thác/reachability.
- Owner và deadline.
- Test cần chạy.
- Bằng chứng sau nâng cấp.
- Kết quả triển khai.

## 13. Quy trình nâng cấp an toàn

Khi đã xác định cần cập nhật:

1. Chọn fixed release phù hợp major line đang sử dụng.
2. Kiểm tra release notes và compatibility requirements.
3. Cập nhật BOM hoặc dependency constraints.
4. Đồng bộ tất cả module Jackson được quản lý bởi BOM.
5. Xử lý dependency bắc cầu kéo version cũ.
6. Kiểm tra dependency tree và resolved runtime classpath.
7. Chạy test mapping và integration.
8. Quét vulnerability lại trên build mới.
9. Kiểm tra SBOM/artifact cuối.
10. Triển khai theo rollout policy và theo dõi lỗi.

### 13.1. Chọn fixed version

Không chọn phiên bản chỉ vì số version lớn hơn. Đối chiếu affected range và fixed version trong advisory chính thức.

Cần kiểm tra:

- Bản sửa có nằm trong release line dự án đang dùng không.
- Có bản patch phù hợp cho major line hiện tại không.
- Bản sửa yêu cầu nâng core/databind/module nào khác không.
- Java baseline có thay đổi không.
- Framework version có tương thích không.
- Có breaking change hoặc behavior change không.
- Module cần thiết đã phát hành tương ứng chưa.

Nếu không có fixed version cho major line cũ, đánh giá khả năng nâng major, dùng vendor-maintained backport hoặc mitigation có xác nhận. Không tự backport security patch bằng cách copy vài class mà không có review và kiểm thử đầy đủ.

### 13.2. Không mix major lines tùy tiện

Jackson major upgrade có thể thay đổi API, package, artifact coordinates hoặc compatibility assumptions. Không trộn module từ major line khác nhau chỉ vì chúng có tên artifact tương tự.

Nếu phải chuyển major line:

- Xem migration guide chính thức.
- Kiểm tra groupId/artifactId mới.
- Xem package import và API thay đổi.
- Kiểm tra module tương ứng có sẵn không.
- Chạy toàn bộ contract và integration tests.
- Kiểm tra framework adapter và plugin compatibility.
- Xác nhận runtime classpath không còn module cũ.

Một security patch trong major line hiện tại thường có phạm vi thay đổi nhỏ hơn migration major, nhưng phải dựa vào advisory và release availability.

## 14. Kiểm thử sau khi nâng cấp

Không chỉ xác nhận ứng dụng compile. Cần kiểm tra hành vi JSON quan trọng và đường xử lý input.

### 14.1. Serialization contract

Test:

- Property naming và inclusion.
- Date/time format.
- Enum code.
- BigDecimal precision/scale.
- Custom serializer/deserializer.
- JsonValue, JsonUnwrapped và contextual serializer.
- Polymorphic discriminator.
- Object identity nếu có.
- Null/missing/empty semantics.

### 14.2. Deserialization contract

Test payload hợp lệ và không hợp lệ:

- JSON fixture phiên bản cũ.
- Unknown property.
- Unknown subtype.
- Input scalar sai kiểu.
- Numeric overflow.
- Malformed/truncated JSON.
- String quá dài, number quá dài.
- Nesting sâu.
- Duplicate/ambiguous input nếu schema có quy tắc riêng.
- Custom deserializer và coercion policy.

### 14.3. Integration test

Test đúng adapter production:

- HTTP request body qua Spring/JAX-RS.
- Message broker serializer/deserializer.
- YAML/XML/CSV nếu ứng dụng dùng.
- File import.
- Framework auto-configuration.
- Error mapping và dead-letter behavior.

Một unit test dùng ObjectMapper tự tạo không chứng minh framework production đang dùng cùng mapper. Hãy lấy mapper từ application configuration hoặc test đúng message converter/codec.

### 14.4. Performance và resource test

Patch bảo mật có thể thay đổi parser behavior hoặc giới hạn. Chạy benchmark/representative load test khi release note cho thấy ảnh hưởng performance hoặc ứng dụng xử lý payload lớn.

Không cần chạy benchmark toàn diện cho mọi patch nhỏ nếu không có lý do; ưu tiên các đường code có thay đổi và payload thực tế.

## 15. Kiểm tra lại sau build và sau deploy

Sau khi test thành công:

- Chạy dependency scan lại trên commit đã cập nhật.
- Tạo SBOM mới.
- So sánh Jackson component/version trước và sau.
- Quét artifact cuối và container image.
- Kiểm tra không còn JAR cũ trong deployment layer.
- Lưu build ID, commit, image digest và kết quả scan.
- Theo dõi startup, binding errors, parser exceptions và message dead-letter sau deploy.

Nếu scanner vẫn báo CVE, điều tra:

- Có artifact cũ còn trong dependency graph không.
- Có bản copy JAR cũ trong image không.
- Có shaded dependency chứa class cũ không.
- Scanner đang nhận diện package metadata nào.
- Advisory có affected range đã cập nhật chưa.
- Có false positive hoặc fixed version mapping sai không.

Không đóng ticket chỉ vì file build đã đổi version. Cần xác nhận version được resolve và version được deploy là cùng một bản đã sửa.

## 16. Theo dõi bảo mật trong CI/CD

Một pipeline tham khảo:

~~~text
Commit / Pull Request
        |
        v
Resolve dependencies
        |
        v
Generate dependency report + SBOM
        |
        v
Vulnerability scan
        |
        +---- Critical/blocked policy ----> Fail / security review
        |
        v
Compile + unit tests
        |
        v
Contract + integration tests
        |
        v
Build application artifact
        |
        v
Scan artifact/container image
        |
        v
Publish release evidence
        |
        v
Deploy / monitor
~~~

Các gate nên có:

- Không thêm dependency có vulnerability bị policy chặn.
- Không có Jackson module lệch version ngoài danh sách được phê duyệt.
- Contract tests phải pass.
- SBOM phải được tạo và lưu.
- Artifact/container scan phải dùng đúng digest sắp deploy.
- Suppression phải có owner, lý do và thời hạn.

Một scanner chạy ở bước dependency resolution không thay thế scan artifact cuối. Một bước scan image không thay thế review advisory và reachability.

## 17. Lịch vận hành để không bỏ sót cập nhật

Một lịch mẫu:

| Nhịp | Hoạt động | Kết quả |
|---|---|---|
| Mỗi pull request | Dependency scan và bot update check | Phát hiện sớm version lỗi thời |
| Hằng ngày | Quét advisory mới cho dependency đã triển khai | Ticket cảnh báo kịp thời |
| Hằng tuần | Review update PR và suppression sắp hết hạn | Giảm dependency lag |
| Trước release | Scan SBOM và artifact/image | Xác nhận release sạch theo policy |
| Hằng tháng | Rà soát toàn bộ module Jackson và framework adapter | Phát hiện module ít được dùng nhưng vẫn có trong runtime |
| Khi có advisory khẩn cấp | Emergency triage, patch và deploy theo SLA | Giảm thời gian phơi nhiễm |

Đây là ví dụ về nhịp vận hành. Tổ chức có thể chọn tần suất khác theo độ quan trọng của ứng dụng và yêu cầu bảo mật. Điều cần bảo đảm là advisory mới được phát hiện ngay cả khi repository không có commit mới.

### 17.1. Theo dõi dependency lag

Dependency lag là khoảng thời gian giữa lúc bản sửa được phát hành và lúc ứng dụng dùng bản sửa đó.

Có thể theo dõi:

- Số ngày từ fixed release đến bản build production.
- Số module Jackson đang ở major line cũ.
- Số advisory chưa xử lý.
- Số suppression quá hạn.
- Tỷ lệ repository có SBOM.
- Tỷ lệ image được scan sau build.
- Số lần update thất bại do compatibility.

Các chỉ số này giúp tìm ra điểm nghẽn trong quy trình nâng cấp, không chỉ đếm số CVE.

## 18. Quy trình emergency patch khi có lỗ hổng nghiêm trọng

Khi advisory có mức khẩn cấp:

1. Xác định tất cả service, job, image và repository chứa artifact bị ảnh hưởng.
2. Dùng SBOM và dependency graph để xác định version chính xác.
3. Kiểm tra input exposure và điều kiện khai thác.
4. Chọn fixed release hoặc mitigation chính thức.
5. Tạo một thay đổi dependency tập trung, đồng bộ module.
6. Chạy smoke test và contract test cho đường xử lý bị ảnh hưởng.
7. Build và scan artifact/container mới.
8. Triển khai theo quy trình emergency release.
9. Theo dõi lỗi parser, binding, throughput và message backlog.
10. Ghi lại bằng chứng remediation và xác nhận mọi môi trường đã cập nhật.

Nếu không thể nâng ngay, ghi rõ mitigation đang áp dụng, owner, deadline và cách xác nhận nó có hiệu lực. Ví dụ, tạm thời vô hiệu hóa endpoint nhận payload liên quan có thể giảm exposure, nhưng không thay thế việc cập nhật dependency.

Không để một workaround tạm thời trở thành suppression vô thời hạn.

## 19. Ví dụ checklist inventory cho một ứng dụng

Một bảng có thể được dùng trong review:

| Component | Resolved version | Scope | Direct/transitive | Production packaged | Status |
|---|---|---|---|---|---|
| jackson-core | Theo build | Runtime | Transitive | Có/Không | Đã đối chiếu advisory |
| jackson-annotations | Theo build | Runtime | Transitive | Có/Không | Đã đối chiếu advisory |
| jackson-databind | Theo build | Runtime | Direct | Có/Không | Đã đối chiếu advisory |
| jackson-datatype-jsr310 | Theo build | Runtime | Direct | Có/Không | Đã đối chiếu advisory |
| jackson-dataformat-yaml | Theo build | Runtime | Transitive | Có/Không | Đã đối chiếu advisory |
| Framework adapter | Theo build | Runtime | Transitive | Có/Không | Đã đối chiếu advisory |

Không điền version từ một tài liệu cũ hoặc ghi "latest". Lấy version từ resolved dependency report/SBOM của build cụ thể và ghi build ID để có thể tái tạo.

Các cột status nên phản ánh bằng chứng:

- Not reviewed.
- Not affected (kèm lý do).
- Affected.
- Fixed in source build.
- Fixed in release artifact.
- Deployed.
- Exception approved until date.

Không đánh dấu Deployed chỉ vì PR đã merge.

## 20. Cách xử lý khi advisory không rõ hoặc scanner mâu thuẫn

Có thể xảy ra:

- Scanner báo affected version nhưng advisory chính thức nói khác.
- Advisory chưa liệt kê một module phụ.
- Một bản backport của vendor có version string cũ.
- Package bị shaded và scanner không nhận diện đúng.
- Một CVE được dispute hoặc cập nhật severity.
- Một dependency được fork hoặc patch nội bộ.

Cách xử lý:

1. Giữ lại scanner result và package coordinate.
2. Mở advisory gốc và release note.
3. Xác minh version thực tế trong artifact.
4. Kiểm tra nguồn phát hành/backport của vendor.
5. Hỏi security owner hoặc maintainer khi evidence chưa đủ.
6. Ghi quyết định, người duyệt và thời hạn review.
7. Tiếp tục theo dõi khi advisory được cập nhật.

Không tự kết luận false positive chỉ vì version có suffix hoặc vendor nói đã backport. Cần bằng chứng từ vendor hoặc kiểm tra package metadata/patch provenance.

## 21. Các sai lầm thường gặp

| Sai lầm | Hệ quả | Cách xử lý |
|---|---|---|
| Chỉ theo dõi jackson-databind | Bỏ sót core, dataformat hoặc adapter | Inventory toàn bộ nhóm dependency thực tế |
| Chỉ đọc file build | Bỏ sót transitive version đã resolve | Kiểm tra dependency tree và SBOM |
| Chỉ scan compile classpath | Bỏ sót runtime dependency | Scan runtime và artifact cuối |
| Chỉ theo dõi CVE database | Có thể bỏ sót advisory/release context | Theo dõi cả advisory chính thức và release notes |
| Nâng riêng một module | Tạo version mismatch | Dùng BOM/constraints và kiểm tra convergence |
| Chọn version mới nhất không xem migration | Gây breaking change | Chọn fixed release phù hợp và đọc migration notes |
| Cho rằng module không dùng trực tiếp thì không ảnh hưởng | Framework có thể gọi gián tiếp | Kiểm tra integration và runtime path |
| Tắt polymorphic typing nhưng bỏ qua parser DoS | Chỉ xử lý một nhóm rủi ro | Rà soát toàn bộ input boundary và resource limits |
| Scanner pass được xem là đủ | Có thể bỏ sót artifact đóng gói | Scan SBOM, JAR và image cuối |
| Suppression không có hạn | Lỗ hổng bị quên | Owner, rationale và expiry |
| Chỉ test compile | Không phát hiện thay đổi binding/format | Contract và integration tests |
| Rollback về version dễ bị tổn thương | Tái mở exposure | Rollback sang release đã được xác nhận an toàn |
| Cập nhật BOM nhưng không kiểm tra transitive override | Runtime vẫn dùng bản cũ | Xem resolved dependency và image |
| Dùng fixture chứa dữ liệu thật | Rò rỉ PII/secret | Synthetic test data |

## 22. Quy trình tổng thể theo dõi security update

~~~text
Inventory toàn bộ dependency Jackson
             |
             v
Tạo dependency report + SBOM
             |
             v
Theo dõi advisory / CVE / release
             |
             v
Đối chiếu affected range với resolved versions
             |
             v
Xác định artifact có trong production?
             |
             v
Đánh giá exposure và reachability
             |
             v
Chọn fixed release / mitigation
             |
             v
Align module qua BOM hoặc constraints
             |
             v
Kiểm tra dependency convergence
             |
             v
Chạy unit + contract + integration tests
             |
             v
Scan lại artifact và container image
             |
             v
Deploy và monitor
             |
             v
Lưu evidence, đóng ticket, tiếp tục theo dõi
~~~

Mỗi bước cần có bằng chứng có thể truy vết. Ví dụ, inventory gắn với build ID; advisory gắn với CVE; upgrade PR gắn với fixed version; test gắn với commit; scan gắn với image digest; deployment gắn với môi trường.

## 23. Nguyên tắc nên giữ

1. Theo dõi toàn bộ artifact Jackson được resolve và đóng gói, không chỉ databind.
2. Kiểm tra cả dependency trực tiếp, bắc cầu, runtime, plugin và container.
3. Duy trì dependency tree và SBOM có thể tái tạo.
4. Theo dõi advisory chính thức, release notes, CVE/OSV và scanner của tổ chức.
5. Ghi nhận affected range, fixed version và điều kiện khai thác.
6. Đánh giá exposure/reachability bằng evidence, không phỏng đoán.
7. Dùng BOM hoặc dependency constraints để align module tương thích.
8. Không trộn major line hoặc ép version tùy tiện.
9. Rà soát polymorphic deserialization, custom module và parser resource limits.
10. Chạy contract/integration tests với mapper production.
11. Quét lại JAR/container artifact cuối và xác nhận version được deploy.
12. Quản lý suppression với owner, lý do và expiry.
13. Xử lý advisory khẩn cấp theo SLA, không chờ lịch nâng cấp định kỳ.
14. Giữ fixture/version cũ để bảo vệ tương thích khi nâng Jackson.
15. Lưu evidence remediation và tiếp tục theo dõi sau khi đóng ticket.

Theo dõi bảo mật cho Jackson là một quy trình quản lý dependency liên tục. Cần biết mọi module đang được sử dụng, phát hiện advisory từ nguồn đáng tin cậy, đối chiếu đúng version thực tế, nâng các module theo release line tương thích và xác nhận bản sửa có mặt trong artifact production. Khi kết hợp inventory, SBOM, scanner, BOM, contract test và kiểm tra image cuối, nhóm phát triển có thể phát hiện sớm rủi ro và xử lý cập nhật bảo mật có kiểm soát.

