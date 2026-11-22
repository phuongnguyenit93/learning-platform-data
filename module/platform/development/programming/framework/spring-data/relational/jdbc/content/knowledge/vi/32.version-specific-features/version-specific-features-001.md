# Đọc release train, release notes và ma trận tương thích Spring Boot

Trong **Spring Data Relational JDBC**, phiên bản thư viện ảnh hưởng trực tiếp đến API repository, mapping, transaction integration, custom conversions và các tính năng JDBC. Khi nâng cấp hoặc tạo dự án mới, không nên chọn riêng một phiên bản spring-data-jdbc chỉ vì đó là bản mới nhất trên Maven Central. Cần xác định phiên bản Spring Boot đang dùng, release train Spring Data tương ứng, Spring Framework mà Boot quản lý, phiên bản Java tối thiểu và JDBC driver tương thích với database.

Ba nguồn thông tin cần đọc cùng nhau:

- **Release train:** cho biết nhóm phiên bản Spring Data được phát hành và quản lý đồng bộ.
- **Release notes/changelog:** mô tả tính năng mới, thay đổi hành vi, deprecation, sửa lỗi và hướng dẫn migration.
- **Compatibility matrix/system requirements:** cho biết các phiên bản nền tảng được hỗ trợ, đặc biệt là Spring Boot, Spring Framework, Java và module Spring Data.

Spring Boot cung cấp dependency management để chọn một tập phiên bản đã được kiểm thử cùng nhau. Trong ứng dụng dùng Boot, cách an toàn thường là để Boot quản lý Spring Data JDBC và các thư viện Spring liên quan, rồi chỉ thêm JDBC driver phù hợp với database. Khi nâng cấp, đọc release notes của cả Boot và Spring Data thay vì chỉ xem một changelog riêng lẻ.

## 1. Phân biệt các loại version

Hệ sinh thái Spring có nhiều dự án với chu kỳ phát hành riêng. Một con số version có thể đại diện cho Boot, Framework, Data release train, module Spring Data hoặc JDBC driver.

| Thành phần | Ví dụ cách ghi version | Vai trò |
| --- | --- | --- |
| Spring Boot | 3.5.x, 4.0.x | Nền tảng ứng dụng, auto-configuration và dependency management |
| Spring Framework | 6.2.x, 7.0.x | Container, transaction, JDBC abstraction và các API nền tảng |
| Spring Data release train | 2025.0, 2025.1 | Nhóm phiên bản đồng bộ của các module Spring Data |
| Spring Data JDBC | 3.x.y | Module repository/mapping JDBC cụ thể |
| Spring Data Relational | 3.x.y | Mapping và hạ tầng relational dùng chung |
| Spring Data Commons | 3.x.y | Repository abstraction, paging, auditing và các thành phần dùng chung |
| JDBC driver | Version riêng của PostgreSQL/MySQL/Oracle/... | Kết nối và chuyển đổi dữ liệu giữa JDBC với database |
| Java | 17, 21, 25, ... | JDK chạy và biên dịch ứng dụng |

Các ví dụ version trong bảng chỉ minh họa dạng version, không phải khẳng định mọi tổ hợp đều tương thích. Một module Spring Data có thể dùng version 3.x, trong khi release train được đặt tên theo năm như 2025.0. **Tên release train không phải version module và cũng không phải version Spring Boot.**

Khi đọc một thông báo kiểu “Spring Data 2025.0”, đừng tự suy ra rằng dependency cần khai báo là spring-data-jdbc:2025.0. Hãy mở trang release train hoặc BOM để tìm version module thực tế.

## 2. Release train của Spring Data là gì?

Spring Data gồm nhiều module, ví dụ Spring Data Commons, Spring Data Relational, Spring Data JDBC, Spring Data JPA, Spring Data MongoDB, Spring Data Redis và các module tích hợp khác.

Các module này chia sẻ repository abstraction, mapping concepts và một số dependency chung. Nếu mỗi module được nâng cấp độc lập mà không theo một tập version đã được kiểm thử, có thể xảy ra lệch API hoặc dependency incompatibility.

**Release train** gom các phiên bản module Spring Data thành một đợt phát hành đồng bộ. Release train thường có BOM để quản lý version của các module thuộc train đó.

~~~text
Spring Data release train
        │
        ├── Spring Data Commons
        ├── Spring Data Relational
        ├── Spring Data JDBC
        ├── Spring Data JPA
        └── Các module Spring Data khác
~~~

Một ứng dụng chỉ dùng Spring Data JDBC không cần khai báo tất cả module trong train. Nhưng khi cần dùng nhiều module Spring Data, BOM giúp các module có version tương thích với nhau.

### 2.1. Release train không phải một thư viện

Release train là tên/nhãn của một tập phát hành. Dependency cụ thể vẫn là artifact như:

~~~xml
<dependency>
    <groupId>org.springframework.data</groupId>
    <artifactId>spring-data-jdbc</artifactId>
</dependency>
~~~

Khi dùng dependency management, version của artifact được lấy từ BOM/parent thay vì phải đặt trực tiếp trong dependency. Cách này giảm nguy cơ vô tình kéo một module từ train khác.

### 2.2. Version module thay đổi theo release train

Spring Data module dùng version riêng, thường có major/minor/patch theo nhịp phát triển của train. Vì vậy:

- Một release train có thể quản lý nhiều artifact version khác nhau.
- Version spring-data-jdbc không nhất thiết trùng version spring-data-jpa.
- Không suy luận version train chỉ bằng cách bỏ dấu chấm hoặc đổi năm.
- Không dùng version module của train mới với Commons/Relational của train cũ trừ khi tài liệu chính thức xác nhận tổ hợp đó.

Khi cần xác định version chính xác, dùng BOM hoặc trang dependency versions của Spring Boot đang chọn.

## 3. Spring Boot quản lý Spring Data như thế nào?

Spring Boot phát hành một BOM có tên spring-boot-dependencies. BOM này quản lý version cho nhiều dependency mà ứng dụng Boot thường sử dụng, bao gồm Spring Framework, Spring Data, logging, JSON libraries và các thư viện tích hợp.

Với Spring Boot, dependency management là lớp quan trọng để giữ các thành phần tương thích:

~~~text
Spring Boot version
       │
       ▼
spring-boot-dependencies BOM
       │
       ├── Spring Framework version
       ├── Spring Data release train / module versions
       ├── Spring Data JDBC
       ├── Spring Data Relational
       ├── Spring Data Commons
       └── Các dependency được quản lý khác
~~~

Khi nâng cấp Boot, BOM thường cập nhật cả nhóm dependency. Điều này giúp tránh trường hợp chỉ đổi Spring Data JDBC mà bỏ lại một phiên bản Commons hoặc Framework không tương thích.

### 3.1. Spring Boot starter và version được quản lý

Trong ứng dụng Spring Boot, thường thêm starter:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-jdbc</artifactId>
</dependency>
~~~

Starter kéo các dependency cần thiết cho Spring Data JDBC. JDBC driver thường được khai báo riêng theo database, ví dụ PostgreSQL:

~~~xml
<dependency>
    <groupId>org.postgresql</groupId>
    <artifactId>postgresql</artifactId>
    <scope>runtime</scope>
</dependency>
~~~

Không đặt version riêng cho starter hoặc driver nếu Boot BOM đang quản lý version đó, trừ khi có lý do cụ thể và đã kiểm tra compatibility. Nếu Boot không quản lý một driver version cần dùng, khai báo version theo tài liệu chính thức của driver.

### 3.2. Maven với Spring Boot parent

Ví dụ dùng Spring Boot parent. Version 3.5.0 ở đây chỉ là ví dụ cú pháp để minh họa dependency management; dự án phải thay bằng bản GA được chọn từ ma trận tương thích hiện hành:

~~~xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.0</version>
    <relativePath/>
</parent>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-jdbc</artifactId>
    </dependency>

    <dependency>
        <groupId>org.postgresql</groupId>
        <artifactId>postgresql</artifactId>
        <scope>runtime</scope>
    </dependency>
</dependencies>
~~~

Ở đây không cần ghi version cho starter. Parent cung cấp dependency management để chọn version phù hợp.

### 3.3. Maven khi không dùng Boot parent

Nếu dự án không kế thừa spring-boot-starter-parent nhưng vẫn dùng Spring Boot, có thể import BOM:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>3.5.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Sau đó khai báo starter/dependency không có version như ví dụ trên. Nếu import thêm BOM khác, phải hiểu thứ tự precedence của dependency management trong Maven; không để nhiều BOM vô tình ghi đè lẫn nhau.

### 3.4. Gradle với Spring Boot plugin

Ví dụ Gradle Groovy DSL:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.0'
    id 'io.spring.dependency-management' version '1.1.7'
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-jdbc'
    runtimeOnly 'org.postgresql:postgresql'
}
~~~

Boot plugin kết hợp dependency management để áp dụng version được Boot quản lý. Nếu dự án dùng Gradle native BOM/platform thay cho plugin dependency management, cần khai báo platform phù hợp và kiểm tra kết quả resolution thực tế.

Không trộn nhiều cơ chế version management nếu chưa hiểu precedence giữa plugin, platform, constraints, version catalog và dependency substitution.

## 4. Ma trận tương thích Spring Boot và Spring Data

Ma trận tương thích trả lời câu hỏi: một phiên bản Boot được xây dựng với nhóm Spring Framework và Spring Data nào? Nguồn đáng tin cậy nhất cho ứng dụng Boot là dependency versions appendix/BOM của đúng phiên bản Boot.

Khi xem ma trận, hãy xác định:

1. Phiên bản Spring Boot chính xác, bao gồm major/minor/patch.
2. Phiên bản Spring Framework được Boot quản lý.
3. Release train Spring Data được Boot quản lý.
4. Version module spring-data-jdbc, spring-data-relational và spring-data-commons.
5. Phiên bản Java tối thiểu và các phiên bản JDK được hỗ trợ.
6. Phiên bản driver/database được hỗ trợ theo tài liệu của vendor.

Ví dụ bảng ghi nhận tương thích cho dự án:

| Thành phần | Version dự án | Nguồn xác nhận |
| --- | --- | --- |
| Spring Boot | Bản GA được chọn | Boot dependency versions / system requirements |
| Spring Framework | Version do Boot BOM quản lý | Boot dependency versions |
| Spring Data train | Train do Boot BOM quản lý | Boot BOM / Spring Data release train |
| Spring Data JDBC | Version do BOM quản lý | Effective POM / Gradle dependency report |
| Spring Data Relational | Version do BOM quản lý | Effective POM / Gradle dependency report |
| Spring Data Commons | Version do BOM quản lý | Effective POM / Gradle dependency report |
| Java | JDK chạy và compile | Boot system requirements |
| JDBC driver | Version đã chọn | Tài liệu driver và Boot BOM nếu có |
| Database server | Version môi trường | Ma trận hỗ trợ của vendor/database |

Đừng sao chép một bảng tương thích từ blog hoặc bài viết cũ nếu không biết nó áp dụng cho Boot release nào. Ma trận có thể thay đổi giữa các major/minor release.

### 4.1. Kiểm tra Java baseline

Spring Boot quy định phiên bản Java tối thiểu cho mỗi dòng release. Spring Framework và Spring Data cũng có yêu cầu runtime riêng. Ứng dụng phải thỏa mãn yêu cầu của toàn bộ stack, đặc biệt là Boot đang dùng.

Kiểm tra ít nhất ba nơi:

- Java runtime dùng để chạy ứng dụng.
- Java toolchain/source compatibility dùng để biên dịch.
- JDK được CI và môi trường production cài đặt.

Ví dụ Maven:

~~~xml
<properties>
    <java.version>17</java.version>
</properties>
~~~

Đây là ví dụ cấu hình, không phải yêu cầu Java cho mọi phiên bản Boot. Hãy lấy Java baseline từ trang system requirements của đúng release Boot.

Ví dụ Gradle:

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
~~~

Đặt source target ở một JDK mới hơn không tự bảo đảm runtime production có JDK tương ứng. CI và image/container production phải dùng runtime tương thích.

### 4.2. Kiểm tra JDBC driver và database

Boot BOM có thể quản lý version JDBC driver, nhưng điều đó không thay thế ma trận hỗ trợ của database vendor. Cần kiểm tra:

- Driver version có hỗ trợ JDK đang chạy không?
- Driver có hỗ trợ database server version đang triển khai không?
- Driver có hỗ trợ kiểu dữ liệu ứng dụng dùng như JSONB, UUID, enum, array hoặc timestamp không?
- Các property URL/timeout/pooling có đúng driver không?
- Database server có hỗ trợ cú pháp SQL và tính năng mà Spring Data JDBC query sử dụng không?

Ví dụ, một ứng dụng có thể resolve dependency thành công nhưng driver cũ không hỗ trợ đúng kiểu PostgreSQL mà converter mong đợi. Build thành công không đồng nghĩa runtime compatibility đã được xác nhận.

## 5. Tìm release notes đúng phiên bản

Không đọc changelog chung chung rồi giả định mọi mục áp dụng cho dự án. Hãy xác định version hiện tại và version đích, sau đó đọc release notes theo từng dự án liên quan.

Với nâng cấp Spring Data JDBC, các nguồn nên kiểm tra:

| Nguồn | Nội dung cần đọc |
| --- | --- |
| Spring Boot release notes | Dependency upgrades, thay đổi auto-configuration, migration guide |
| Spring Data release train notes | Thay đổi chung của train, module mới, compatibility |
| Spring Data Relational release notes | Mapping, aggregate persistence, converters, auditing, dialect |
| Spring Data JDBC release notes/changelog | Repository, query methods, JDBC-specific changes |
| Spring Data Commons release notes | Repository abstraction, projection, paging, auditing, events |
| Spring Framework release notes | Transaction, JDBC support, bean/container behavior |
| JDBC driver release notes | JDK support, protocol, type mapping, security fixes |
| Database release notes | SQL behavior, deprecated features, server compatibility |

Một thay đổi trong Commons có thể ảnh hưởng Spring Data JDBC dù changelog của module JDBC không nhắc lại. Tương tự, thay đổi trong Spring Framework có thể ảnh hưởng transaction hoặc infrastructure mà Spring Data JDBC sử dụng.

### 5.1. Đọc theo khoảng version, không chỉ bản mới nhất

Giả sử dự án đang ở Boot 3.3.x và định nâng cấp lên 3.5.x. Quy trình đọc:

1. Đọc migration/release notes của Boot từ dòng hiện tại tới dòng đích.
2. Xác định Spring Framework và Spring Data version do Boot đích quản lý.
3. Đọc các release notes Spring Data train mà dự án đi qua.
4. Đọc notes của Spring Data JDBC/Relational/Commons nếu có thay đổi liên quan.
5. Đọc driver release notes nếu Boot BOM đổi driver hoặc ứng dụng cần nâng driver.
6. Kiểm tra thay đổi database server nếu version database cũng nằm trong kế hoạch nâng cấp.

Nếu đi qua nhiều release train, đừng chỉ đọc notes của train đích. Một deprecation có thể xuất hiện ở train trước và bị xóa ở train sau; migration note trung gian có thể là hướng dẫn quan trọng.

### 5.2. Tìm mục liên quan đến ứng dụng

Khi đọc release notes, ưu tiên tìm các từ khóa phù hợp với codebase:

- JDBC, Relational, Repository, Aggregate.
- Mapping, Converter, JdbcValue, Dialect.
- Query, @Query, Pageable, Sort, Limit.
- Transaction, Optimistic Locking, @Version.
- Auditing, Callbacks, Events.
- Java, JDK, Spring Framework, Spring Boot.
- Deprecated, Breaking, Removed, Migration.

Không chỉ tìm theo tên class đang dùng. Một thay đổi về dependency, default configuration hoặc database dialect có thể ảnh hưởng ứng dụng dù code không trực tiếp import class đó.

## 6. Phân biệt tính năng mới, deprecation và breaking change

Release notes thường chứa nhiều loại thay đổi. Cần phân biệt chúng để ước lượng công sức nâng cấp.

| Loại thay đổi | Ý nghĩa | Hành động |
| --- | --- | --- |
| Feature | Có API/tính năng mới | Chỉ áp dụng nếu ứng dụng có nhu cầu |
| Bug fix | Sửa hành vi sai | Kiểm tra có workaround cũ cần bỏ không |
| Dependency upgrade | Nâng thư viện phụ thuộc | Kiểm tra tương thích và CVE |
| Deprecation | API vẫn còn nhưng được khuyến nghị thay thế | Lập kế hoạch chuyển đổi |
| Behavior change | API có thể giữ nguyên nhưng kết quả/hành vi đổi | Viết test cho behavior liên quan |
| Breaking change | API hoặc contract cũ không còn tương thích | Sửa code/configuration trước khi nâng production |
| Removal | API/dependency cũ bị loại bỏ | Tìm toàn bộ usage và migration path |
| Security fix | Vá lỗ hổng | Đánh giá mức độ ưu tiên và bản vá phù hợp |

### 6.1. Deprecation không giống removal

Một API được đánh dấu deprecated vẫn có thể compile và chạy, nhưng ứng dụng nên chuyển sang API được khuyến nghị. Không nên xóa mọi API deprecated ngay lập tức nếu migration quá rộng; hãy đọc lý do và thời điểm dự kiến removal.

Khi một API bị remove trong release mới, compile error thường chỉ ra các call site trực tiếp. Nhưng behavior change có thể không tạo compile error, nên test và release notes vẫn quan trọng.

### 6.2. Kiểm tra thay đổi hành vi

Ví dụ, release mới có thể thay đổi:

- Cách Spring Data nhận diện entity mới.
- Cách query derivation phân tích tên method.
- Cách converter chọn JDBC type.
- Cách auditing cập nhật field lúc insert.
- Cách dialect sinh SQL cho pagination hoặc generated keys.
- Cách optimistic locking báo lỗi.

Tên method vẫn compile không bảo đảm hành vi giống phiên bản trước. Tạo test tập trung cho những phần có thay đổi trong release notes.

## 7. GA, milestone, release candidate và snapshot

Spring project có thể phát hành các giai đoạn trước bản GA:

| Giai đoạn | Ý nghĩa | Dùng ở đâu? |
| --- | --- | --- |
| Snapshot | Build phát triển thay đổi liên tục | Thử nghiệm, CI nội bộ có chủ đích |
| Milestone (M) | Bản xem trước theo mốc phát triển | Đánh giá tính năng sắp tới |
| Release Candidate (RC) | Bản gần hoàn chỉnh để xác nhận trước GA | Kiểm thử tương thích, phản hồi trước phát hành |
| General Availability (GA) | Bản phát hành chính thức | Lựa chọn thông thường cho production |
| Service release/patch | Bản vá trong cùng dòng release | Cập nhật bug/security theo chính sách dự án |

Ví dụ version có hậu tố -SNAPSHOT, -M1, -RC1 không có cùng mức ổn định với bản GA. Không dùng snapshot chỉ vì nó chứa một API mới hơn nếu ứng dụng cần độ ổn định production.

Với production, chọn bản GA/patch được hỗ trợ và theo dõi chính sách support của Spring. Nếu phải dùng pre-release để thử một tính năng, cô lập trong branch hoặc môi trường thử nghiệm và ghi rõ rủi ro.

## 8. Kiểm tra version thực tế mà build đang resolve

File pom.xml hoặc build.gradle cho biết yêu cầu khai báo, nhưng version thực tế có thể bị thay đổi bởi parent, BOM, plugin, constraint, version catalog hoặc dependency conflict resolution.

Vì vậy, sau khi đọc ma trận và chọn Boot version, hãy kiểm tra dependency graph được resolve.

### 8.1. Maven

Hiển thị cây dependency liên quan Spring Data:

~~~bash
./mvnw dependency:tree -Dincludes=org.springframework.data
~~~

Kiểm tra riêng Spring Framework:

~~~bash
./mvnw dependency:tree -Dincludes=org.springframework
~~~

Tạo effective POM để xem parent/BOM và dependency management sau khi Maven hợp nhất:

~~~bash
./mvnw help:effective-pom
~~~

Nếu một dependency có version không như mong đợi, xem dependency path nào kéo nó vào và dependency management nào ghi đè. Không thêm version override chỉ để làm build qua mà chưa hiểu nguồn xung đột.

### 8.2. Gradle

Kiểm tra version Spring Data JDBC:

~~~bash
./gradlew dependencyInsight --dependency spring-data-jdbc --configuration runtimeClasspath
~~~

Kiểm tra Commons hoặc Relational:

~~~bash
./gradlew dependencyInsight --dependency spring-data-commons --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-data-relational --configuration runtimeClasspath
~~~

dependencyInsight giải thích dependency nào yêu cầu version và lý do Gradle chọn version cuối cùng. Đây là cách phát hiện version bị override bởi constraint hoặc dependency khác.

### 8.3. Kiểm tra JDBC driver

Maven:

~~~bash
./mvnw dependency:tree -Dincludes=org.postgresql:postgresql
~~~

Gradle:

~~~bash
./gradlew dependencyInsight --dependency postgresql --configuration runtimeClasspath
~~~

Thay tọa độ artifact theo driver thực tế. So sánh version resolve với version được Boot BOM quản lý và ma trận hỗ trợ của vendor.

## 9. Những lỗi do version lệch thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách điều tra |
| --- | --- | --- |
| NoSuchMethodError | Runtime nạp version class khác với version lúc compile | Kiểm tra dependency tree và classpath runtime |
| NoClassDefFoundError | Module cần thiết bị thiếu hoặc version không còn class đó | Kiểm tra dependency transitive và release notes |
| ClassNotFoundException | Code/config tham chiếu class không có trong artifact đang chạy | Xác định JAR chứa class và version thực tế |
| AbstractMethodError | API/interface thay đổi nhưng implementation hoặc dependency cũ chưa đồng bộ | Kiểm tra các module Spring cùng train |
| Lỗi auto-configuration/repository bean | Boot, Framework và Data không cùng tổ hợp tương thích | So sánh với Boot BOM và dependency appendix |
| UnsupportedClassVersionError | Runtime JDK thấp hơn bytecode yêu cầu | Kiểm tra JDK build và JDK production |
| Driver không nhận kiểu dữ liệu | Driver version hoặc database type mapping không phù hợp | Kiểm tra driver release notes và JDBC type |
| SQL syntax/feature error | Database server/dialect không hỗ trợ SQL được sinh | Kiểm tra database version và dialect |
| Hành vi paging/locking thay đổi | Behavior change trong module hoặc dialect | Đọc release notes và kiểm thử integration |
| Build dùng một version nhưng production dùng version khác | Packaging/container/classpath không đồng nhất | Kiểm tra dependency report và nội dung artifact triển khai |

Không xử lý NoSuchMethodError bằng cách thêm một dependency mới ngẫu nhiên. Trước hết xác định class nào được nạp và artifact version nào chứa class đó.

## 10. Quy trình nâng cấp Spring Boot và Spring Data JDBC

Một lần nâng cấp có kiểm soát nên đi theo trình tự:

1. **Ghi nhận baseline:** Boot, Framework, Data train, Spring Data JDBC/Relational/Commons, Java, driver và database server hiện tại.
2. **Chọn version đích:** chỉ chọn bản GA được hỗ trợ, dựa trên system requirements và ma trận dependency của Boot đích.
3. **Đọc release notes:** đọc Boot migration guide, Spring Data train notes, module JDBC/Relational/Commons và driver notes trong khoảng version nâng cấp.
4. **Cập nhật dependency management:** nâng Boot parent/plugin/BOM; để Boot quản lý các module Spring Data nếu ứng dụng dùng Boot.
5. **Loại bỏ override cũ:** xem các version khai báo trực tiếp cho Spring Framework, Commons, Relational hoặc JDBC có còn cần không.
6. **Kiểm tra Java:** đồng bộ JDK trên máy phát triển, CI, build toolchain và production runtime.
7. **Kiểm tra dependency graph:** dùng Maven dependency tree/effective POM hoặc Gradle dependencyInsight.
8. **Biên dịch và kiểm thử:** tập trung repository, mapping, converter, query, auditing, transaction và optimistic locking.
9. **Kiểm thử với database thật:** dùng cùng loại database/driver và migration như môi trường triển khai.
10. **Kiểm tra vận hành:** pool, metrics, timeout, connection behavior và cấu hình production.
11. **Triển khai theo giai đoạn:** staging/canary trước khi rollout rộng, có kế hoạch rollback phù hợp schema và dữ liệu.

Nâng version thư viện và nâng version database server là hai thay đổi có thể tách riêng. Nếu thay đổi cả hai cùng lúc, khi có lỗi sẽ khó xác định nguyên nhân. Khi có thể, nâng một lớp mỗi lần và kiểm thử giữa các bước.

## 11. Ví dụ: một dự án muốn nâng Spring Data JDBC

Giả sử dự án đang dùng Spring Boot và có dependency spring-boot-starter-data-jdbc. Nhóm phát triển muốn dùng một API mới của Spring Data JDBC.

### Bước 1: Xác định API thuộc module/version nào

Tìm API trong Javadoc/reference của Spring Data JDBC. Xác định phiên bản đầu tiên có API đó và xem nó thuộc release train nào. Không chỉ dựa vào bài blog hoặc câu trả lời diễn đàn.

### Bước 2: Xác định Boot version quản lý train đó

Mở dependency versions của từng dòng Boot phù hợp. Kiểm tra Boot BOM đang quản lý Spring Data train nào và version spring-data-jdbc nào.

### Bước 3: Kiểm tra Java và Framework

Nếu Boot version đích yêu cầu Java mới hơn, cập nhật JDK cho developer, CI và production. Xác nhận các thư viện nội bộ và agent/runtime khác tương thích.

### Bước 4: Nâng Boot BOM

Ưu tiên nâng Boot parent/plugin/BOM để kéo cả stack về tổ hợp đã được Boot quản lý. Không chỉ thêm một version spring-data-jdbc mới bên cạnh Commons/Relational cũ.

### Bước 5: Đọc migration notes

Tìm breaking change/deprecation trong Boot, Framework, Spring Data train và JDBC module. Sửa code/configuration theo migration guide trước khi triển khai.

### Bước 6: Kiểm tra dependency graph

Xác nhận Spring Data JDBC, Relational và Commons cùng nằm trong tổ hợp BOM mong muốn. Kiểm tra driver version và database compatibility riêng.

### Bước 7: Kiểm thử use case JDBC

Chạy các test đại diện: insert/update aggregate có child, derived query và @Query, projection/DTO, custom conversions, optimistic locking và @Version, auditing, transaction rollback, pagination/sorting và dialect-specific SQL.

### Bước 8: Đưa lên staging

Dùng migration và database engine gần production. Theo dõi log, pool metrics, query latency, lỗi mapping và transaction. Sau khi kết quả ổn định mới rollout production.

## 12. Khi nào nên override version ngoài Boot BOM?

Trong ứng dụng Boot, tránh override version riêng cho spring-data-jdbc, spring-data-relational hoặc spring-data-commons chỉ để lấy một tính năng mới. Override có thể tạo tổ hợp mà Boot chưa kiểm thử.

Một số tình huống có thể cần override:

- Boot BOM chưa cập nhật một bản vá bảo mật cần thiết.
- Có bug đã được sửa trong patch release và Spring xác nhận cách override phù hợp.
- Một dependency driver cần bản vá mới hơn bản Boot quản lý.
- Ứng dụng có yêu cầu tương thích đặc biệt được tài liệu chính thức hướng dẫn.

Khi override:

1. Xác định chính xác dependency nào cần override và vì sao.
2. Kiểm tra compatibility với các module Spring liên quan.
3. Dùng version GA/patch phù hợp, không kéo cả module train khác một cách tùy tiện.
4. Ghi rõ override trong dependency management tập trung.
5. Kiểm tra dependency graph sau resolution.
6. Chạy integration test trên database mục tiêu.
7. Lập kế hoạch bỏ override khi Boot BOM đã bao gồm bản vá.

Nếu ứng dụng cần nâng nhiều module Spring Data cùng lúc, hãy cân nhắc nâng Boot lên dòng quản lý release train đó thay vì tự ghép từng artifact.

## 13. Nguồn chính thức nên dùng

| Nguồn | Dùng để trả lời |
| --- | --- |
| Spring Boot system requirements | Java baseline và runtime requirement của Boot |
| Spring Boot dependency versions | Boot quản lý version nào cho Framework, Data và driver |
| Spring Boot release notes/migration guide | Thay đổi khi nâng Boot |
| Spring Data release trains | Train hiện hành, module và compatibility |
| Spring Data Relational reference/release notes | Tính năng và thay đổi của JDBC/Relational |
| Spring Framework release notes | Thay đổi nền tảng, JDBC và transaction |
| JDBC driver release notes | JDK/database support, protocol và type mapping |
| Database vendor support matrix | Phiên bản server/driver được hỗ trợ |

Một số địa chỉ tham khảo:

- [Spring Boot — System Requirements](https://docs.spring.io/spring-boot/system-requirements.html): yêu cầu Java và build tool theo Boot version.
- [Spring Boot — Dependency Versions](https://docs.spring.io/spring-boot/appendix/dependency-versions/coordinates.html): version dependency được Boot quản lý.
- [Spring Boot — Managing Dependencies](https://docs.spring.io/spring-boot/reference/using/build-systems.html#using.build-systems.dependency-management): cách sử dụng parent/BOM và dependency management.
- [Spring Data — Project and Release Trains](https://spring.io/projects/spring-data): các module và release train của Spring Data.
- [Spring Data Relational Reference](https://docs.spring.io/spring-data/relational/reference/): tài liệu Spring Data JDBC/Relational.
- [Spring Data Relational — Release History](https://github.com/spring-projects/spring-data-relational/releases): release notes theo tag của dự án.
- [Spring Boot — Release History](https://github.com/spring-projects/spring-boot/releases): release notes và thay đổi theo bản phát hành.
- [PostgreSQL JDBC Driver Documentation](https://jdbc.postgresql.org/documentation/): driver configuration, type mapping và compatibility.

Luôn chọn trang tài liệu đúng major/minor version nếu Spring cung cấp selector theo phiên bản. Trang current hữu ích để đọc bản mới nhất nhưng có thể mô tả API khác với ứng dụng đang chạy.

## 14. Lỗi thường gặp khi đọc version và release notes

| Nhầm lẫn | Hậu quả | Cách tránh |
| --- | --- | --- |
| Nghĩ release train là version artifact | Khai báo sai dependency version | Tra version module trong BOM |
| Nâng riêng Spring Data JDBC | Commons/Relational lệch version | Để Boot BOM hoặc Spring Data BOM quản lý đồng bộ |
| Dùng version mới nhất trên Maven Central | Có thể vượt khỏi tổ hợp Boot hỗ trợ | Chọn theo ma trận Boot đích |
| Chỉ đọc changelog của JDBC | Bỏ sót thay đổi từ Commons/Relational/Framework | Đọc notes theo toàn bộ dependency stack |
| Dùng trang current để suy ra API của version cũ | Code không compile hoặc behavior khác | Mở docs đúng version |
| Nhầm patch release với minor/major migration | Bỏ sót breaking change | Xem version range và migration guide |
| Dùng milestone/snapshot production | Build không ổn định hoặc dependency thay đổi | Ưu tiên GA được hỗ trợ |
| Build thành công được coi là tương thích hoàn toàn | Lỗi runtime/driver/database vẫn có thể xảy ra | Integration test với database và driver thật |
| Chỉ kiểm tra version trong file build | Không thấy dependency conflict | Kiểm tra effective POM/dependencyInsight |
| Chỉ nâng thư viện mà không nâng JDK | Runtime không tải được bytecode mới | Đồng bộ JDK build, CI và production |

## 15. Checklist trước khi chọn hoặc nâng version

Trước khi thay đổi dependency, trả lời các câu hỏi:

1. Boot version hiện tại và version đích là gì?
2. Boot đích quản lý Spring Framework và Spring Data release train nào?
3. Version module Spring Data JDBC/Relational/Commons thực tế là bao nhiêu?
4. Java runtime và build JDK có đáp ứng system requirements không?
5. JDBC driver version có hỗ trợ JDK và database server không?
6. Release notes của Boot, Framework, Data train và driver đã được đọc trong toàn khoảng nâng cấp chưa?
7. Có deprecation/removal hoặc behavior change ảnh hưởng codebase không?
8. Dependency có bị override bởi parent, BOM, constraint hoặc version catalog không?
9. Dependency graph sau resolution có đúng tổ hợp mong muốn không?
10. Integration test đã chạy với database/driver mục tiêu chưa?
11. Có kế hoạch migration dữ liệu và rollback nếu schema thay đổi không?
12. Có theo dõi release support/security advisories cho version đã chọn không?

## 16. Bài tập thực hành

**Bài 1 — Đọc dependency BOM.** Chọn một phiên bản Spring Boot GA. Mở dependency versions appendix và ghi lại Spring Framework, Spring Data JDBC, Spring Data Relational, Spring Data Commons và JDBC driver version được quản lý.

**Bài 2 — Xác định release train.** Từ version Spring Data JDBC trong BOM, tìm release train tương ứng trên trang Spring Data. Giải thích vì sao version module không nhất thiết trùng tên train.

**Bài 3 — Đọc release notes.** Chọn hai release train liên tiếp. Tìm một feature, một bug fix, một deprecation và một breaking/behavior change có thể ảnh hưởng ứng dụng JDBC.

**Bài 4 — Kiểm tra Java baseline.** Đọc system requirements của Boot version đã chọn. So sánh với JDK trên máy, CI và runtime production; ghi nhận điểm không tương thích nếu có.

**Bài 5 — Maven dependency tree.** Tạo dự án dùng spring-boot-starter-data-jdbc. Chạy dependency:tree và help:effective-pom; tìm version Spring Data JDBC/Relational/Commons được resolve.

**Bài 6 — Gradle dependencyInsight.** Tạo cùng cấu hình bằng Gradle. Chạy dependencyInsight cho spring-data-jdbc và giải thích vì sao Gradle chọn version đó.

**Bài 7 — Phát hiện override.** Thêm một version override thử nghiệm cho một module Spring Data trong branch riêng. Quan sát dependency graph thay đổi và giải thích rủi ro khi module lệch train. Sau đó bỏ override.

**Bài 8 — Lập kế hoạch nâng cấp.** Chọn một Boot version cũ và một Boot version GA mới hơn. Đọc migration notes trong khoảng nâng cấp, liệt kê code/configuration cần kiểm tra và các integration test phải chạy.

**Bài 9 — Driver compatibility.** Chọn PostgreSQL/MySQL/SQL Server driver đang dùng. Tra tài liệu driver để xác nhận JDK, database server và kiểu dữ liệu ứng dụng cần hỗ trợ.

**Bài 10 — Tạo compatibility matrix.** Viết bảng version cho Boot, Framework, Data train, Data JDBC, Java, JDBC driver và database server. Đính kèm link nguồn chính thức và ngày kiểm tra.

### Kết luận

Đọc version đúng là đọc cả một hệ sinh thái dependency. Bắt đầu từ Spring Boot version, dùng BOM để xác định Spring Framework và Spring Data module versions, sau đó đọc release notes trong toàn khoảng nâng cấp và xác nhận Java/driver/database bằng tài liệu chính thức. Cuối cùng, kiểm tra dependency graph đã resolve và chạy integration test với database mục tiêu. Quy trình này giúp tránh việc một dependency riêng lẻ có version mới nhưng toàn bộ stack lại không tương thích.
