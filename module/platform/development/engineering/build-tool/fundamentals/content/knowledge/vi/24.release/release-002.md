# Metadata phát hành và thông tin cần cho dự án sử dụng thư viện

Khi một nhóm phát hành thư viện Java, việc tải lên một tệp JAR là chưa đủ. Dự án sử dụng thư viện cần biết artifact đó thuộc về ai, có phiên bản nào, được build cho nền tảng Java nào, phụ thuộc vào những thư viện nào, dùng API ra sao, có tương thích với phiên bản trước không và lấy được tài liệu hoặc bằng chứng toàn vẹn ở đâu.

Những thông tin này được gọi chung là **metadata phát hành**. Một phần metadata được lưu trong POM hoặc Gradle Module Metadata để công cụ build phân giải dependency. Phần khác được cung cấp qua tài liệu, release notes, checksum, chữ ký, SBOM và build provenance để người dùng tích hợp, đánh giá và xác minh thư viện.

Metadata tốt giúp consumer sử dụng thư viện mà không cần biết chi tiết nội bộ của quy trình build. Nó cũng giúp công cụ build chọn đúng variant, giải quyết dependency bắc cầu, nhận biết yêu cầu tương thích và xác định nguồn gốc artifact. Nếu metadata thiếu hoặc sai, thư viện có thể tải được nhưng không biên dịch, không chạy, kéo theo dependency không cần thiết hoặc khó kiểm chứng khi triển khai.

## 1. Artifact phát hành và metadata phát hành

Một bản phát hành thư viện thường gồm nhiều thành phần:

| Thành phần | Ví dụ | Vai trò |
| --- | --- | --- |
| Artifact chính | payment-client-2.4.0.jar | Bytecode và tài nguyên của thư viện |
| POM | payment-client-2.4.0.pom | Metadata Maven và dependency |
| Gradle Module Metadata | payment-client-2.4.0.module | Metadata variant và dependency phong phú cho Gradle |
| Sources JAR | payment-client-2.4.0-sources.jar | Mã nguồn để đọc và debug |
| Javadoc JAR | payment-client-2.4.0-javadoc.jar | Tài liệu API |
| Checksum | .sha256, SHA256SUMS | Kiểm tra tính toàn vẹn |
| Signature | .asc hoặc chữ ký theo hệ thống | Xác minh người/khóa ký |
| Release notes | CHANGELOG.md hoặc trang release | Thay đổi, sửa lỗi và breaking changes |
| SBOM | bom.json, bom.xml | Danh sách thành phần phần mềm |
| Provenance | Attestation hoặc metadata build | Nguồn và quy trình tạo artifact |

Không phải mọi repository đều bắt buộc lưu tất cả các tệp trên. Tuy nhiên, artifact chính và metadata dependency cần thiết phải được publish đúng; tài liệu, checksum và thông tin nguồn gốc giúp consumer đánh giá và sử dụng release an toàn hơn.

## 2. Tọa độ định danh một thư viện

Với Maven repository, một artifact thường được nhận diện bằng các tọa độ:

    groupId:artifactId:version

Ví dụ:

    com.example.billing:payment-client:2.4.0

Các thành phần:

- **groupId:** namespace của tổ chức hoặc nhóm sở hữu artifact.
- **artifactId:** tên module hoặc thư viện.
- **version:** phiên bản phát hành.
- **packaging/type:** loại artifact, thường là jar, pom hoặc war.
- **classifier:** biến thể bổ sung, chẳng hạn sources, javadoc hoặc một nền tảng cụ thể.

Trong Gradle, module bên ngoài thường được xác định bởi group, name và version. Repository có thể lưu metadata bổ sung để phân biệt variant.

Tọa độ cần ổn định và duy nhất trong phạm vi repository. Hai thư viện khác nhau không nên dùng cùng tọa độ nếu chúng không đại diện cho cùng một module và cùng quy tắc version.

### Chọn groupId và artifactId

Một tổ chức có thể dùng namespace dựa trên domain sở hữu:

    com.example.platform:logging-api
    com.example.platform:logging-core
    com.example.billing:payment-client

Tên nên thể hiện vai trò và phạm vi của thư viện. Tránh tên quá chung như common, utils hoặc library nếu tổ chức có nhiều module; chúng gây khó tìm kiếm và dễ xung đột tọa độ.

Với thư viện nội bộ, nên dùng group riêng và publish vào repository nội bộ. Không nên dựa vào một tọa độ nội bộ trùng với module công khai trên Maven Central.

## 3. Version là thông tin hợp đồng

Version giúp consumer chọn một bản phát hành cụ thể và đánh giá mức độ thay đổi.

Một cách phổ biến là Semantic Versioning:

    MAJOR.MINOR.PATCH

Ví dụ:

    2.4.0

- **MAJOR:** thay đổi không tương thích API hoặc hành vi theo chính sách version của dự án.
- **MINOR:** thêm chức năng tương thích ngược.
- **PATCH:** sửa lỗi tương thích ngược.

Semantic Versioning là quy ước cần được dự án áp dụng nhất quán. Công cụ build không tự chứng minh rằng một bản 2.5.0 thực sự tương thích ngược với 2.4.0. Nhóm phát hành phải kiểm tra API, hành vi và dependency trước khi chọn version.

### Release và SNAPSHOT

Một version release như 2.4.0 nên đại diện cho một nội dung bất biến. Không publish lại artifact khác với cùng tọa độ release.

Version phát triển có thể dùng:

    2.5.0-SNAPSHOT

Snapshot thường được cập nhật nhiều lần và metadata repository có thể trỏ tới bản timestamped mới. Đây là cơ chế dành cho phát triển tích cực, không phù hợp làm đầu vào bất biến cho một release production cần tái lập.

### Pre-release version

Nhóm có thể dùng các hậu tố như:

    3.0.0-alpha.1
    3.0.0-beta.2
    3.0.0-rc.1

Chúng biểu thị trạng thái chưa phát hành chính thức theo quy ước của dự án. Cần công bố rõ chính sách chọn version và mức độ ổn định để consumer không nhầm pre-release với bản production.

## 4. POM cung cấp thông tin gì cho Maven consumer?

POM là metadata trung tâm của Maven artifact. Khi consumer khai báo dependency, Maven đọc POM để biết thông tin artifact và dependency bắc cầu.

Ví dụ dependency:

    <dependency>
        <groupId>com.example.billing</groupId>
        <artifactId>payment-client</artifactId>
        <version>2.4.0</version>
    </dependency>

Consumer thường không phải tự liệt kê mọi dependency mà payment-client cần. Maven đọc POM được publish và xây dựng dependency graph.

POM có thể mô tả:

- groupId, artifactId, version và packaging.
- tên, mô tả và URL dự án.
- license.
- SCM và thông tin quản lý mã nguồn.
- developer hoặc organization.
- dependency và scope.
- dependency optional.
- dependencyManagement và BOM nếu POM được dùng làm parent hoặc platform.
- plugin/configuration cho build khi POM đóng vai trò parent project.

Không phải mọi trường trong POM đều ảnh hưởng tới runtime resolution. Ví dụ name, description, licenses và SCM giúp người dùng hiểu và đánh giá dự án; dependencies và scopes trực tiếp ảnh hưởng dependency graph.

## 5. Dependency metadata phải mô tả đúng runtime

Một thư viện cần khai báo dependency mà consumer thực sự cần để compile hoặc chạy.

Ví dụ POM:

    <dependencies>
        <dependency>
            <groupId>com.fasterxml.jackson.core</groupId>
            <artifactId>jackson-databind</artifactId>
            <version>2.17.2</version>
        </dependency>
        <dependency>
            <groupId>org.slf4j</groupId>
            <artifactId>slf4j-api</artifactId>
            <version>2.0.16</version>
        </dependency>
    </dependencies>

Khi consumer sử dụng payment-client, Maven có thể đưa các dependency này vào graph theo scope và quy tắc mediation.

### Scope của dependency trong thư viện

| Scope | Ý nghĩa phổ biến đối với consumer |
| --- | --- |
| compile | Dependency thông thường, có thể truyền tiếp và cần cho compile/runtime theo quy tắc Maven |
| runtime | Cần khi chạy nhưng không dùng để compile mã nguồn chính của module hiện tại |
| provided | Môi trường consumer được kỳ vọng cung cấp; không truyền tiếp như compile thông thường |
| test | Chỉ dùng khi build/test chính thư viện, không phải dependency runtime của consumer |

Ví dụ, JUnit chỉ dùng để kiểm thử payment-client nên khai báo scope test. Không nên để JUnit trở thành dependency compile của mọi ứng dụng sử dụng thư viện.

Một API công khai trong payment-client có thể tham chiếu một kiểu thuộc dependency khác. Nếu consumer cần kiểu đó để biên dịch mã gọi API, dependency cần được công bố với scope và cấu trúc phù hợp.

### Optional dependency

Một dependency optional cho biết consumer không tự động nhận dependency đó như một dependency bắc cầu thông thường.

Ví dụ:

    <dependency>
        <groupId>com.example</groupId>
        <artifactId>payment-cloud-adapter</artifactId>
        <version>1.2.0</version>
        <optional>true</optional>
    </dependency>

Optional phù hợp khi tính năng chỉ được dùng bởi một số consumer. Tài liệu phải nói rõ consumer muốn dùng tính năng đó cần khai báo dependency nào.

Không nên đánh dấu một dependency bắt buộc cho runtime là optional chỉ để làm dependency tree gọn hơn. Consumer có thể biên dịch được nhưng lỗi khi gọi chức năng tương ứng.

## 6. Phân biệt dependency của thư viện và dependencyManagement

POM phát hành một thư viện cần mô tả dependency mà thư viện thực sự sử dụng. Phần dependencyManagement có vai trò quản lý version/metadata cho dependency được khai báo ở nơi khác; nó không tự thêm tất cả dependency vào classpath của consumer.

Ví dụ:

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>com.fasterxml.jackson</groupId>
                <artifactId>jackson-bom</artifactId>
                <version>2.17.2</version>
                <type>pom</type>
                <scope>import</scope>
            </dependency>
        </dependencies>
    </dependencyManagement>

Consumer thường nhận được quy tắc quản lý BOM khi sử dụng POM đó trong vai trò phù hợp, chẳng hạn kế thừa parent hoặc import BOM vào dependencyManagement của chính consumer.

Nếu phát hành một BOM, POM của BOM thường có packaging pom và phần dependencyManagement liệt kê version của một nhóm artifact. Consumer import BOM để đồng bộ version. BOM không có nghĩa mọi thư viện được liệt kê đều tự động trở thành dependency của consumer.

## 7. Gradle Module Metadata và POM

Gradle có thể tiêu thụ Maven POM và Gradle Module Metadata. Module Metadata thường có đuôi:

    payment-client-2.4.0.module

Metadata này có thể mô tả những thông tin phong phú hơn POM truyền thống, đặc biệt là:

- Nhiều variant của cùng module.
- Thuộc tính variant như usage và target JVM.
- Dependency theo từng variant.
- Dependency constraints và rich version information.
- Capabilities và quan hệ giữa variant.

Một module Java library có thể cung cấp variant compile và runtime. Consumer chọn variant phù hợp với configuration và attribute của mình.

POM vẫn rất quan trọng vì Maven và nhiều công cụ khác dùng nó. Khi Gradle publish một component qua maven-publish, Gradle có thể publish cả POM và Gradle Module Metadata nếu publication và repository hỗ trợ.

### Không nên chỉ dựa vào .module

Không phải mọi consumer đều đọc Gradle Module Metadata. Maven consumer thường dựa vào POM. Vì vậy, metadata quan trọng cho dependency graph cần được biểu diễn tương thích trong POM ở mức có thể, hoặc được tài liệu hóa nếu hai định dạng không thể diễn đạt hoàn toàn giống nhau.

Nếu POM và .module mâu thuẫn, các công cụ có thể phân giải khác nhau. Hãy kiểm tra metadata được publish và thử bằng cả loại consumer mà thư viện cam kết hỗ trợ.

## 8. Variant và thuộc tính nền tảng

Một thư viện có thể cung cấp nhiều biến thể:

- API dành cho compile.
- Artifact runtime.
- Variant tương thích với một mức Java cụ thể.
- Variant cho platform hoặc architecture khác nhau.
- Variant chứa tài liệu hoặc metadata bổ sung.

Gradle Module Metadata có thể mô tả các variant và thuộc tính giúp Gradle chọn đúng artifact. Ví dụ, một consumer yêu cầu JVM 17 có thể chọn variant tương thích với JVM 17 thay vì variant chỉ hỗ trợ JVM 21.

Khi publish bằng Java Library Plugin, Gradle có thể đưa thông tin target JVM vào variant metadata dựa trên cấu hình compile options/toolchain. Điều này giúp Gradle consumer đánh giá tính tương thích khi resolve.

Maven POM truyền thống không có một trường chuẩn phổ quát tương đương cho mọi thuộc tính variant. Dự án Maven thường cần tài liệu hóa Java baseline và có thể dùng Maven Enforcer hoặc quy ước nội bộ để kiểm tra.

### Công bố Java baseline

Consumer cần biết thư viện yêu cầu Java tối thiểu nào. Ví dụ:

    Requires Java 17 or later.

Thông tin này nên xuất hiện trong README, release notes và tài liệu phát hành. Nếu Gradle metadata có target JVM attribute, hãy bảo đảm nó phản ánh đúng bytecode thực tế.

Không nên chỉ dựa vào phiên bản JDK trên máy phát hành. Một thư viện được build bằng JDK 21 vẫn có thể nhắm Java 17 nếu cấu hình compiler phù hợp; ngược lại, chỉ ghi Java 17 trong README không làm bytecode Java 21 chạy được trên Java 17.

## 9. Metadata mô tả API công khai

Consumer cần biết lớp, interface, method và kiểu dữ liệu nào là API được hỗ trợ. Một thư viện nên phân biệt:

- API công khai và được cam kết ổn định.
- API nội bộ, có thể thay đổi không báo trước.
- Extension point hoặc SPI dành cho plugin.
- API deprecated và thời điểm dự kiến loại bỏ.
- Hành vi thread-safety, lifecycle và giới hạn sử dụng nếu liên quan.

Javadoc giúp mô tả contract của public API. Sources JAR giúp consumer đọc implementation khi debug, nhưng implementation không tự trở thành hợp đồng tương thích.

### Public API không chỉ là lớp public

Một lớp public có thể vẫn là chi tiết nội bộ nếu dự án không cam kết hỗ trợ nó. Tài liệu cần chỉ rõ package hoặc module nào được xem là public API.

Nếu dùng JPMS, module-info.java có thể khai báo exports cho package được công khai. Tuy nhiên, exports không thay thế tài liệu API hoặc chính sách version.

### Deprecated API

Khi thay thế API, nên:

1. Đánh dấu API cũ deprecated.
2. Chỉ ra API thay thế.
3. Nêu thời điểm hoặc phiên bản dự kiến loại bỏ nếu có chính sách.
4. Cung cấp ví dụ migration.
5. Chỉ loại bỏ theo quy tắc major version hoặc chính sách tương thích đã công bố.

Consumer cần thông tin này để nâng version có kế hoạch thay vì bị bất ngờ bởi breaking change.

## 10. Sources JAR và Javadoc JAR

Hai artifact bổ sung phổ biến:

    payment-client-2.4.0-sources.jar
    payment-client-2.4.0-javadoc.jar

Sources JAR chứa mã nguồn tương ứng với bản phát hành. Nó giúp IDE hiển thị code khi debug hoặc điều hướng vào thư viện.

Javadoc JAR chứa tài liệu API đã tạo. IDE có thể gắn tài liệu vào dependency để hiển thị mô tả method, tham số và exception.

Các artifact này không nên được xem là dependency runtime của ứng dụng. Chúng phục vụ phát triển và tài liệu.

### Maven source và Javadoc artifacts

Maven Source Plugin và Javadoc Plugin có thể gắn các classifier sources và javadoc vào quá trình package/deploy.

Ví dụ gọi:

    mvn source:jar javadoc:jar deploy

Trong dự án thực tế, nên cấu hình phiên bản plugin và execution trong POM hoặc release profile để CI phát hành artifact nhất quán. Cần xác nhận Javadoc build thành công và artifact classifier được deploy.

### Gradle source và Javadoc artifacts

Với Java plugin:

    java {
        withSourcesJar()
        withJavadocJar()
    }

Gradle có thể tạo sourceJar và javadocJar để publish cùng component Java khi dùng maven-publish.

Nếu thư viện không thể tạo Javadoc sạch vì warning hoặc lỗi doclint, nhóm cần quyết định chính sách xử lý rõ ràng. Không nên publish Javadoc rỗng hoặc không tương ứng với version artifact.

## 11. Thông tin dự án và liên hệ

Consumer cần biết ai duy trì thư viện, tìm mã nguồn ở đâu và báo lỗi ở đâu.

Các thông tin hữu ích:

- Tên và mô tả ngắn.
- Website hoặc trang tài liệu.
- SCM URL và tag tương ứng release.
- Issue tracker hoặc trang hỗ trợ.
- Organization/developer maintainer.
- Kênh thông báo security advisory.
- Chính sách hỗ trợ version.

Maven POM hỗ trợ các trường như name, description, url, licenses, scm, developers và issueManagement.

Ví dụ:

    <name>Payment Client</name>
    <description>Java client for the Example payment API.</description>
    <url>https://github.com/example/payment-client</url>
    <licenses>
        <license>
            <name>Apache License, Version 2.0</name>
            <url>https://www.apache.org/licenses/LICENSE-2.0</url>
            <distribution>repo</distribution>
        </license>
    </licenses>
    <scm>
        <connection>scm:git:https://github.com/example/payment-client.git</connection>
        <url>https://github.com/example/payment-client</url>
        <tag>v2.4.0</tag>
    </scm>
    <issueManagement>
        <system>GitHub Issues</system>
        <url>https://github.com/example/payment-client/issues</url>
    </issueManagement>

Thông tin này nên trỏ tới đúng repository, tag và trang hỗ trợ của release. Một SCM tag không tồn tại hoặc trỏ tới commit khác sẽ làm giảm khả năng truy nguyên.

## 12. License và quyền sử dụng

Consumer cần biết điều kiện pháp lý để sử dụng, sửa đổi và phân phối thư viện.

Metadata nên nêu:

- License của chính thư viện.
- Link tới văn bản license.
- License của dependency quan trọng nếu được tổng hợp.
- Notice hoặc attribution cần giữ khi phân phối.
- Các giới hạn hoặc nghĩa vụ liên quan.

Trường licenses trong POM là metadata mô tả license; nó không thay thế việc đóng gói file LICENSE, NOTICE hoặc các thông báo bắt buộc trong artifact/repository.

Nếu thư viện dùng nhiều dependency với license khác nhau, nhóm phát hành cần quản lý license của toàn bộ dependency graph. Consumer có thể cần SBOM và license report để đánh giá chính sách nội bộ.

Không nên ghi một license chung trong POM nếu nội dung source, binary và dependency thực tế không phù hợp với license đó.

## 13. Release notes và changelog

Release notes là một trong những nguồn thông tin quan trọng nhất để consumer quyết định có nâng version hay không.

Một release note hữu ích thường nêu:

- Version và ngày phát hành.
- Tính năng mới.
- Sửa lỗi.
- Breaking changes.
- API deprecated hoặc bị loại bỏ.
- Thay đổi dependency hoặc Java baseline.
- Thay đổi cấu hình mặc định.
- Lỗ hổng bảo mật đã xử lý nếu có thể công bố.
- Hướng dẫn migration và các lưu ý khi nâng cấp.

Ví dụ:

    ## 2.4.0
    - Added retry configuration for PaymentClient.
    - Fixed timeout handling for asynchronous requests.
    - Requires Java 17 or later.
    - Updated the HTTP transport dependency.
    - Deprecated LegacyPaymentRequest; use PaymentRequest instead.

Release notes nên phản ánh đúng artifact được publish. Nếu release 2.4.0 đã được phát hành, không sửa nội dung artifact cùng tọa độ để thêm thay đổi; hãy phát hành version mới hoặc cập nhật tài liệu release theo chính sách có audit.

### Migration guide

Với major release, migration guide nên chỉ rõ:

- API cũ và API mới.
- Cách thay đổi cấu hình.
- Dependency hoặc plugin version cần nâng.
- Java baseline mới.
- Hành vi mặc định thay đổi.
- Những bước cần thực hiện trước khi deploy.

Một migration guide tốt giảm chi phí tích hợp và giúp consumer nâng cấp có kiểm soát.

## 14. Checksum và tính toàn vẹn artifact

Repository hoặc pipeline phát hành có thể cung cấp SHA-256 checksum cho từng artifact.

Ví dụ:

    sha256sum payment-client-2.4.0.jar

Hoặc trên Windows PowerShell:

    Get-FileHash -Algorithm SHA256 -LiteralPath '.\payment-client-2.4.0.jar'

Consumer tải artifact có thể tính lại digest và so sánh với giá trị được công bố.

Checksum giúp phát hiện:

- File bị hỏng trong quá trình truyền.
- Artifact bị thay đổi sau khi publish.
- Tải nhầm file hoặc nhầm version.
- Khác biệt giữa artifact lưu trong CI và artifact trong repository.

Checksum không chứng minh ai đã phát hành artifact nếu kẻ tấn công có thể thay cả file lẫn checksum. Với yêu cầu xác thực nguồn, cần chữ ký số hoặc cơ chế attestation đáng tin cậy.

## 15. Chữ ký số và xác thực người phát hành

Artifact có thể được ký bằng khóa riêng của tổ chức phát hành. Consumer dùng khóa công khai hoặc hệ thống trust đã được phân phối độc lập để xác minh chữ ký.

Với Maven, artifact có thể được ký theo OpenPGP và publish tệp signature, thường có đuôi .asc. Maven GPG Plugin là một cách phổ biến để tích hợp ký artifact vào quy trình release.

Ví dụ lệnh kiểm tra chữ ký bằng GPG:

    gpg --verify payment-client-2.4.0.jar.asc payment-client-2.4.0.jar

Việc xác minh chỉ có ý nghĩa khi public key được xác nhận thuộc đúng tổ chức/maintainer. Không lấy khóa công khai từ cùng một nguồn không đáng tin rồi mặc nhiên tin chữ ký.

Không bao giờ publish private signing key cùng artifact hoặc ghi nó vào build log. Khóa riêng nên nằm trong secret store hoặc signing service được kiểm soát, và chỉ pipeline phát hành được cấp quyền sử dụng.

## 16. SBOM cho consumer

Software Bill of Materials (SBOM) là danh mục các thành phần phần mềm trong một sản phẩm hoặc artifact.

SBOM có thể cho biết:

- Tên và version của component.
- Package URL hoặc định danh component.
- Supplier/producer.
- License.
- Quan hệ dependency.
- Hash của component.
- Thông tin nguồn hoặc external reference.

Các định dạng phổ biến gồm CycloneDX và SPDX. SBOM giúp consumer kiểm tra dependency graph, license và tác động khi một thư viện có lỗ hổng bảo mật.

### SBOM cần gắn với artifact cụ thể

Một SBOM nên xác định rõ:

- Artifact hoặc sản phẩm được mô tả.
- Version và build ID.
- Thời điểm tạo.
- Công cụ tạo SBOM.
- Phạm vi component được đưa vào.
- Có bao gồm dependency runtime, test, build tool hay không.

SBOM của source tree và SBOM của binary có thể khác nhau. Nếu consumer cần biết những thư viện thực sự được đóng gói vào runtime artifact, cần tạo SBOM từ đúng sản phẩm hoặc dependency graph tương ứng.

SBOM không thay thế dependency metadata của Maven/Gradle. Nó phục vụ inventory và phân tích; POM hoặc module metadata vẫn cần để build tool resolve dependency.

## 17. Build provenance và nguồn gốc artifact

Provenance mô tả artifact được tạo từ đâu và bằng quy trình nào. Metadata có thể bao gồm:

- Source repository và commit SHA.
- Tag hoặc release identifier.
- Builder identity.
- CI workflow/job.
- Build tool và JDK version.
- Tham số hoặc profile quan trọng.
- Dependency lock state.
- Thời điểm build.
- Artifact digest.

Provenance giúp consumer hoặc hệ thống phát hành truy nguyên artifact tới source và pipeline đã tạo nó.

Một file build-info.txt tự ghi trong JAR có thể hữu ích, nhưng không tự chứng minh thông tin đó là trung thực. Attestation được ký bởi builder đáng tin cậy có thể cung cấp bằng chứng mạnh hơn.

Khi phát hành thư viện quan trọng, có thể lưu:

    payment-client-2.4.0.jar
    payment-client-2.4.0.pom
    payment-client-2.4.0.module
    payment-client-2.4.0-sources.jar
    payment-client-2.4.0-javadoc.jar
    payment-client-2.4.0.jar.sha256
    payment-client-2.4.0.jar.asc
    sbom.cdx.json
    provenance.json
    release-notes.md

Danh sách thực tế tùy chính sách repository và nhu cầu consumer. Các file nên có tên/version nhất quán và được liên kết với cùng release.

## 18. Publish metadata với Maven

Maven dùng POM để mô tả artifact và dependency. Plugin maven-deploy-plugin thường thực hiện publish artifact và POM lên repository được cấu hình trong distributionManagement.

Ví dụ POM thư viện:

    <project>
        <modelVersion>4.0.0</modelVersion>
        <groupId>com.example.billing</groupId>
        <artifactId>payment-client</artifactId>
        <version>2.4.0</version>
        <packaging>jar</packaging>

        <name>Payment Client</name>
        <description>Java client for the Example payment API.</description>
        <url>https://github.com/example/payment-client</url>

        <licenses>
            <license>
                <name>Apache License, Version 2.0</name>
                <url>https://www.apache.org/licenses/LICENSE-2.0</url>
            </license>
        </licenses>

        <scm>
            <connection>scm:git:https://github.com/example/payment-client.git</connection>
            <tag>v2.4.0</tag>
        </scm>

        <dependencies>
            <dependency>
                <groupId>org.slf4j</groupId>
                <artifactId>slf4j-api</artifactId>
                <version>2.0.16</version>
            </dependency>
        </dependencies>
    </project>

Trong release thực tế, POM còn cần parent/version management, plugin version và thông tin repository phù hợp. Ví dụ trên chỉ thể hiện metadata chính để consumer hiểu artifact.

### distributionManagement

Repository publish có thể được cấu hình:

    <distributionManagement>
        <repository>
            <id>company-releases</id>
            <url>https://repo.example.com/releases/</url>
        </repository>
        <snapshotRepository>
            <id>company-snapshots</id>
            <url>https://repo.example.com/snapshots/</url>
        </snapshotRepository>
    </distributionManagement>

Thông tin xác thực tương ứng được đặt trong settings.xml với server id khớp repository id. Không đặt token hoặc password trong POM được commit.

### Deploy

Lệnh:

    mvn deploy

chạy lifecycle đến deploy và publish artifact/POM theo cấu hình plugin và distributionManagement. Nếu cần ký artifact, tạo sources/Javadoc hoặc SBOM, hãy cấu hình các bước đó trong release pipeline và xác nhận file được publish đúng.

## 19. Publish metadata với Gradle maven-publish

Gradle có plugin maven-publish để publish Java component và POM.

Ví dụ Groovy DSL:

    plugins {
        id 'java-library'
        id 'maven-publish'
    }

    group = 'com.example.billing'
    version = '2.4.0'

    java {
        withSourcesJar()
        withJavadocJar()
    }

    publishing {
        publications {
            mavenJava(MavenPublication) {
                from components.java
                pom {
                    name = 'Payment Client'
                    description = 'Java client for the Example payment API.'
                    url = 'https://github.com/example/payment-client'
                    licenses {
                        license {
                            name = 'Apache License, Version 2.0'
                            url = 'https://www.apache.org/licenses/LICENSE-2.0'
                        }
                    }
                    scm {
                        url = 'https://github.com/example/payment-client'
                    }
                }
            }
        }
        repositories {
            maven {
                name = 'companyReleases'
                url = uri('https://repo.example.com/releases/')
                credentials {
                    username = providers.gradleProperty('repoUser').orNull
                    password = providers.gradleProperty('repoToken').orNull
                }
            }
        }
    }

Đoạn cấu hình tạo publication từ Java component và thêm metadata POM. Sources/Javadoc JAR được tạo để publish cùng component.

Thông tin xác thực nên lấy từ Gradle properties hoặc secret environment được bảo vệ, không commit giá trị thật. Repository URL và credentials cần được cấu hình theo môi trường release.

### Gradle Module Metadata

Khi publish component Gradle qua maven-publish, Gradle có thể publish file .module bên cạnh POM và artifact nếu metadata publication được bật và repository hỗ trợ lưu tệp đó.

Gradle Module Metadata giữ thông tin variant và dependency phong phú hơn POM. Consumer Gradle có thể dùng metadata này để chọn variant phù hợp. Maven consumer tiếp tục dùng POM.

Sau khi publish, hãy kiểm tra repository có các tệp dự kiến và metadata phản ánh đúng component. Không nên chỉ xác nhận task publish thành công rồi mặc định POM/.module đã đầy đủ.

## 20. Kiểm tra metadata trước khi publish

Một release pipeline nên kiểm tra:

- Group, artifact và version đúng với release.
- Không dùng SNAPSHOT cho release chính thức nếu chính sách yêu cầu version bất biến.
- POM có dependency và scope đúng.
- Optional dependency được dùng đúng mục đích.
- Java baseline và target JVM phản ánh đúng bytecode.
- Public API và deprecated API được tài liệu hóa.
- License, SCM, issue tracker và project URL đúng.
- Sources/Javadoc artifact được tạo nếu chính sách yêu cầu.
- Release notes khớp thay đổi thực tế.
- Checksum và signature được tạo cho đúng artifact cuối.
- SBOM/provenance gắn đúng build ID, commit và digest.
- Không có credential hoặc dữ liệu nhạy cảm trong metadata.

Kiểm tra metadata nên thực hiện trên artifact đã package hoặc staging repository, không chỉ trên source POM/build script.

## 21. Thử sử dụng artifact như một consumer độc lập

Một cách kiểm tra hữu ích là tạo project consumer nhỏ, chỉ khai báo tọa độ đã publish và thử compile/test.

Ví dụ Maven consumer:

    <dependency>
        <groupId>com.example.billing</groupId>
        <artifactId>payment-client</artifactId>
        <version>2.4.0</version>
    </dependency>

Ví dụ Gradle consumer:

    dependencies {
        implementation 'com.example.billing:payment-client:2.4.0'
    }

Project thử nghiệm nên dùng repository staging hoặc repository release thực tế theo quyền truy cập phù hợp. Kiểm tra:

- Dependency được resolve từ đúng nguồn.
- POM và Gradle metadata có thể đọc.
- API public biên dịch được.
- Dependency bắc cầu được đưa vào đúng configuration.
- Runtime smoke test chạy được.
- Javadoc và sources có thể tải nếu được publish.
- Java baseline được đáp ứng.

Không nên chỉ chạy test bên trong chính project thư viện. Build nội bộ có thể nhìn thấy source set hoặc dependency mà consumer thực tế không có.

## 22. Kiểm tra POM và Gradle Module Metadata đã publish

Với Maven, tải POM từ repository staging và kiểm tra:

    payment-client-2.4.0.pom

Đối chiếu groupId, artifactId, version, dependency, scope, optional và thông tin dự án.

Với Gradle, kiểm tra:

    payment-client-2.4.0.module

Đối chiếu variants, attributes, dependencies, constraints và artifact file names.

Có thể dùng dependency report của consumer:

    mvn dependency:tree

hoặc:

    ./gradlew dependencies --configuration runtimeClasspath

Kết quả phải phù hợp với contract của thư viện. Nếu Maven và Gradle consumer nhận graph khác nhau, hãy xem metadata format và quy tắc resolution của từng công cụ.

## 23. Metadata và tính tương thích của API

Metadata version chỉ giúp consumer chọn release. Nó không tự chứng minh API tương thích.

Một thư viện nên có quy trình kiểm tra:

- API public được thêm/xóa/thay đổi.
- Kiểu dữ liệu public thay đổi package hoặc chữ ký.
- Phương thức thay đổi visibility hoặc exception.
- Hành vi mặc định thay đổi.
- Dependency public API thay đổi.
- Java baseline tăng.
- Module exports/requires thay đổi.

Có thể dùng công cụ kiểm tra API binary compatibility trong CI. Kết quả nên được đối chiếu với version policy của dự án.

### Binary compatibility và source compatibility

Một thay đổi có thể biên dịch lại được nhưng phá binary compatibility với consumer đã biên dịch trước đó. Ví dụ đổi chữ ký method hoặc xóa method có thể làm consumer gặp NoSuchMethodError khi chạy.

Release notes nên nêu breaking change và migration. Với thay đổi không tương thích, tăng major version theo chính sách Semantic Versioning của dự án.

### Dependency compatibility

Ngay cả khi API của thư viện không đổi, nâng dependency bắc cầu có thể làm thay đổi classpath hoặc hành vi runtime. Metadata phát hành cần phản ánh dependency đúng; release pipeline nên test với các version được công bố.

## 24. Metadata bảo mật và dependency inventory

Consumer thường cần đánh giá thư viện trước khi cho phép sử dụng trong production. Metadata bảo mật hữu ích gồm:

- SBOM.
- License inventory.
- Dependency versions.
- Security advisory hoặc link tới trang vulnerability.
- Release provenance.
- Artifact checksum/signature.
- Contact hoặc quy trình báo cáo lỗ hổng.

Không phải mọi lỗ hổng đều có thể mô tả đầy đủ trong POM. Có thể cung cấp trang security policy hoặc advisory riêng và liên kết từ tài liệu dự án.

Nếu phát hiện vulnerability trong dependency, nhóm phát hành nên cập nhật dependency, test lại, publish version mới và mô tả rõ ảnh hưởng trong release notes. Không sửa artifact release cũ dưới cùng tọa độ để thay dependency một cách âm thầm.

## 25. Repository metadata và tính bất biến của release

Một release version nên là bất biến:

    com.example.billing:payment-client:2.4.0

luôn trỏ tới cùng nội dung JAR và metadata trong repository release.

Nếu publish lại cùng tọa độ với JAR hoặc POM khác:

- Cache của consumer có thể giữ bản cũ.
- Máy khác có thể tải bản mới.
- Checksum và signature không còn khớp.
- Dependency graph có thể thay đổi dù tọa độ không đổi.
- Việc điều tra và tái lập build trở nên khó khăn.

Repository manager nên bật chính sách ngăn redeploy/overwrite release. Nếu có lỗi trong artifact, phát hành version sửa lỗi mới như 2.4.1. Với snapshot, chính sách cập nhật có thể linh hoạt hơn nhưng cần hiểu metadata timestamp và cache.

## 26. Metadata của BOM và platform

Một BOM giúp consumer quản lý nhiều dependency version theo một bộ tương thích.

Ví dụ Maven BOM:

    <project>
        <modelVersion>4.0.0</modelVersion>
        <groupId>com.example.platform</groupId>
        <artifactId>platform-bom</artifactId>
        <version>5.2.0</version>
        <packaging>pom</packaging>
        <dependencyManagement>
            <dependencies>
                <dependency>
                    <groupId>com.example.billing</groupId>
                    <artifactId>payment-client</artifactId>
                    <version>2.4.0</version>
                </dependency>
                <dependency>
                    <groupId>com.example.identity</groupId>
                    <artifactId>identity-client</artifactId>
                    <version>3.1.0</version>
                </dependency>
            </dependencies>
        </dependencyManagement>
    </project>

Consumer import BOM:

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>com.example.platform</groupId>
                <artifactId>platform-bom</artifactId>
                <version>5.2.0</version>
                <type>pom</type>
                <scope>import</scope>
            </dependency>
        </dependencies>
    </dependencyManagement>

Sau đó consumer có thể khai báo các dependency được quản lý mà không cần lặp version.

Với Gradle, BOM có thể được sử dụng qua platform:

    dependencies {
        implementation platform('com.example.platform:platform-bom:5.2.0')
        implementation 'com.example.billing:payment-client'
        implementation 'com.example.identity:identity-client'
    }

BOM/platform là metadata quản lý version; nó không tự động thêm mọi artifact được quản lý vào classpath. Consumer vẫn khai báo các thư viện thực sự sử dụng.

## 27. Metadata cho nhiều biến thể artifact

Một thư viện có thể publish nhiều classifier hoặc variant:

- JAR chính.
- Sources.
- Javadoc.
- Native artifact cho nền tảng cụ thể.
- Variant compile/runtime.
- Artifact dành cho test fixtures.

Classifier trong Maven thường phân biệt các artifact phụ có cùng tọa độ cơ bản. Gradle variant model cung cấp cách mô tả phong phú hơn, dựa trên attributes và capabilities.

Consumer cần metadata để biết artifact nào phù hợp. Nếu publish nhiều file nhưng không có metadata/đặt tên rõ ràng, consumer có thể tải nhầm hoặc không biết cách sử dụng.

Không nên dùng classifier như một cách thay thế tùy tiện cho version. Nếu artifact có API hoặc hành vi khác biệt đáng kể, hãy cân nhắc module/version riêng hoặc variant được mô tả rõ.

## 28. Thông tin phát hành cần có trong tài liệu người dùng

Ngoài metadata máy đọc được, trang tài liệu hoặc README release nên nêu:

1. Tọa độ Maven/Gradle.
2. Repository cần thêm nếu không dùng Maven Central.
3. Java baseline và toolchain yêu cầu.
4. Ví dụ khai báo dependency.
5. Các dependency hoặc module tùy chọn.
6. Cách cấu hình authentication nếu repository riêng yêu cầu.
7. API chính và ví dụ sử dụng.
8. Release notes và migration guide.
9. License và chính sách hỗ trợ.
10. Link checksum, signature, SBOM và provenance nếu có.

Ví dụ cho consumer:

    dependencies {
        implementation 'com.example.billing:payment-client:2.4.0'
    }

Nếu thư viện được publish lên repository riêng:

    repositories {
        maven {
            url = uri('https://repo.example.com/releases/')
        }
    }

Không đưa username/password thật vào ví dụ. Dùng secret hoặc credential mechanism phù hợp với công cụ build.

## 29. Quy trình phát hành thư viện có metadata đầy đủ

Một release pipeline có thể tổ chức:

    Chọn version và commit
             |
             v
    Compile + unit/integration tests
             |
             v
    Kiểm tra API compatibility
             |
             v
    Tạo JAR + POM/module metadata
             |
             v
    Tạo sources/Javadoc
             |
             v
    Tạo SBOM và provenance
             |
             v
    Tính checksum và ký artifact
             |
             v
    Publish lên staging repository
             |
             v
    Kiểm tra metadata bằng consumer thử nghiệm
             |
             v
    Promote/publish release bất biến
             |
             v
    Công bố release notes và tài liệu

Thứ tự cụ thể phụ thuộc repository manager và quy trình ký. Một số hệ thống ký sau khi publish lên staging; hệ thống khác ký trước khi upload. Điều quan trọng là chữ ký và checksum phải gắn với đúng bytes cuối cùng được phân phối.

### Staging repository

Publish vào staging trước khi phát hành chính thức giúp kiểm tra:

- POM và Gradle Module Metadata.
- Dependency graph.
- Sources/Javadoc.
- Signature và checksum.
- Consumer compatibility.
- Artifact naming và version.

Chỉ promote release khi các kiểm tra bắt buộc thành công. Nếu staging không được dùng, có thể kiểm tra trên repository thử nghiệm riêng trước khi publish release.

## 30. Checklist cho consumer khi nhận thư viện

Consumer có thể đánh giá release bằng các câu hỏi:

| Câu hỏi | Thông tin cần xem |
| --- | --- |
| Đây có đúng thư viện không? | Group, artifact/module name và version |
| Release ổn định hay thử nghiệm? | Version, release channel và changelog |
| Có tương thích Java hiện tại không? | Java baseline, target JVM/variant |
| Dependency nào được kéo vào? | POM, Gradle Module Metadata, dependency report |
| API nào được hỗ trợ? | Javadoc, public API docs, deprecation policy |
| Có thể debug không? | Sources JAR và hướng dẫn |
| License có phù hợp không? | POM license, LICENSE/NOTICE, SBOM |
| Artifact có nguyên vẹn không? | SHA-256 checksum |
| Nguồn phát hành có đáng tin không? | Signature, provenance và builder identity |
| Nâng cấp có rủi ro gì? | Release notes, migration guide, compatibility report |
| Báo lỗi ở đâu? | SCM, issue tracker và security contact |

## 31. Những lỗi metadata thường gặp

### POM thiếu dependency runtime

Thư viện hoạt động trong project phát triển nhưng consumer gặp NoClassDefFoundError vì dependency cần lúc chạy không được công bố đúng scope.

### Đưa test dependency vào metadata runtime

Consumer nhận thêm JUnit, Mockito hoặc test utility không cần thiết. Kiểm tra scope test và configuration publish.

### Ghi sai Java baseline

Metadata hoặc tài liệu ghi Java 11 nhưng bytecode/variant yêu cầu Java 17. Consumer có thể resolve thành công rồi lỗi khi compile hoặc chạy.

### POM và Gradle Module Metadata không nhất quán

Maven và Gradle consumer nhận dependency graph hoặc variant khác nhau. Kiểm tra publication component và metadata được publish.

### Version release bị ghi đè

Hai consumer cùng khai báo một tọa độ nhưng tải bytes khác nhau. Bảo vệ repository khỏi redeploy và phát hành version mới khi cần.

### Release notes thiếu breaking changes

Consumer nâng version mà không biết API hoặc hành vi đã đổi. Ghi rõ migration và compatibility.

### Sources/Javadoc không khớp binary

IDE hiển thị source khác với bytecode đang chạy. Publish source/Javadoc từ cùng commit và build record với artifact chính.

### Checksum được tạo trước khi artifact hoàn tất

Checksum không khớp file phân phối cuối. Tạo digest sau repackage/sign/finalization theo quy trình thống nhất.

### License hoặc provenance không chính xác

Consumer không thể đánh giá quyền sử dụng hoặc nguồn gốc. Tạo metadata từ đầu vào thực tế và review trước khi phát hành.

## 32. Nguyên tắc thực hành

- Dùng tọa độ và version ổn định, duy nhất.
- Giữ release artifact bất biến; dùng version mới khi cần sửa.
- Publish POM và/hoặc Gradle Module Metadata chính xác.
- Mô tả đúng dependency, scope, optional và variant.
- Công bố Java baseline và platform compatibility.
- Phân biệt public API, implementation detail và deprecated API.
- Cung cấp Javadoc, sources và release notes phù hợp.
- Công bố license, SCM, issue tracker và kênh hỗ trợ.
- Tạo checksum cho artifact cuối; dùng chữ ký/provenance khi cần xác thực nguồn.
- Cung cấp SBOM và dependency evidence theo yêu cầu.
- Kiểm tra metadata bằng một consumer độc lập trước khi release.
- Giữ POM, .module, source, Javadoc và binary đồng bộ cùng commit/version.

Metadata phát hành là hợp đồng giữa người tạo thư viện và dự án sử dụng thư viện. POM và Gradle Module Metadata giúp công cụ build resolve đúng artifact và dependency; version, Java baseline và API documentation giúp consumer đánh giá tương thích; release notes và migration guide giải thích thay đổi; checksum, signature, SBOM và provenance hỗ trợ xác minh tính toàn vẹn, inventory và nguồn gốc. Một release chỉ thực sự dễ sử dụng khi các thông tin này chính xác, nhất quán và gắn với đúng artifact được publish.
