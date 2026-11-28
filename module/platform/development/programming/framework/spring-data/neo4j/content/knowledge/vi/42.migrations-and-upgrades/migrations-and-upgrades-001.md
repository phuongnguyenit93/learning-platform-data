# Đọc release notes và ma trận tương thích Boot–SDN–driver–Neo4j

Khi nâng cấp một ứng dụng Spring Data Neo4j (SDN), không thể chỉ chọn phiên bản mới nhất của từng thư viện rồi ghép chúng lại. Ứng dụng chịu ràng buộc từ nhiều lớp: Spring Boot, Spring Framework, Spring Data release train, Spring Data Neo4j, Neo4j Java Driver và Neo4j Server. Mỗi lớp có chu kỳ phát hành và quy tắc tương thích riêng.

Spring Boot quản lý nhiều dependency thông qua BOM (Bill of Materials). SDN cần một thế hệ Spring Framework và Spring Data Commons phù hợp. Neo4j Java Driver giao tiếp với Neo4j Server qua Bolt, trong khi cú pháp Cypher và tính năng database còn phụ thuộc phiên bản server. Vì vậy, một cặp Driver–Server kết nối được chưa chắc đã chạy được mọi câu query của ứng dụng.

Bài học này hướng dẫn cách đọc release notes, xây dựng ma trận tương thích, xác định phiên bản thực tế mà build đang resolve và lập kế hoạch nâng cấp theo từng lớp. Các phiên bản trong ma trận là ví dụ đã đối chiếu tại ngày 26/11/2026; khi triển khai dự án, cần kiểm tra lại trang phát hành tương ứng.

## 1. Vì sao cần ma trận tương thích?

Giả sử một ứng dụng đang dùng Spring Boot 3.5.x, Spring Data Neo4j 7.5.x, Neo4j Java Driver 5.28.x và Neo4j Server 5.26 LTS. Nhóm phát triển muốn nâng cấp Neo4j Server lên 2025.01 và đồng thời chuyển ứng dụng sang Spring Boot 4.2.0.

Nếu chỉ đổi version của Boot, nhiều dependency nền tảng cũng thay đổi theo: Spring Framework, Spring Data Commons, SDN và Neo4j Java Driver.

Các câu hỏi cần trả lời trước khi nâng cấp:

1. Spring Boot đích quản lý Spring Framework và SDN phiên bản nào?
2. SDN đích yêu cầu Spring Framework tối thiểu bao nhiêu?
3. Driver mà Boot quản lý có tương thích với Neo4j Server đích không?
4. Phiên bản server đích có còn hỗ trợ JVM đang chạy database không?
5. Câu Cypher, procedure, index hoặc transaction mà ứng dụng sử dụng có thay đổi không?
6. Neo4j Server có yêu cầu chuyển store format, cluster discovery hoặc cấu hình trước khi nâng cấp không?

Ma trận giúp kiểm tra các ràng buộc này trước khi sửa build và trước khi thay đổi database production.

## 2. Hiểu vai trò và cách đánh số phiên bản của từng thành phần

| Thành phần | Vai trò | Cách đánh số thường gặp |
|---|---|---|
| Spring Boot | Nền tảng ứng dụng và dependency management | 3.5.x, 4.0.x, 4.2.x |
| Spring Framework | Container, DI, transaction, AOP, web và các API nền | 6.2.x, 7.0.x, 7.1.x |
| Spring Data release train | Bộ phiên bản tương thích của các module Spring Data | CalVer như 2025.0.x, 2026.0.x, 2026.1.x |
| Spring Data Neo4j | Mapping, repository, template, client và transaction integration | 7.5.x, 8.0.x, 8.2.x |
| Neo4j Java Driver | Giao tiếp ứng dụng với database qua Bolt | 5.28.x, 6.x |
| Neo4j Server | Database engine, Cypher, store format và cluster | 4.4.x, 5.x, 2025.x, 2026.x |

Không so sánh các con số giữa các dòng như thể chúng cùng một sản phẩm. SDN 8.2 không có nghĩa là Neo4j Server 8.2; Spring Data train 2026.1 cũng không phải phiên bản Spring Boot.

### Spring Boot và BOM

Spring Boot cung cấp dependency management thông qua BOM. Khi dùng starter, các thư viện Spring và driver được chọn theo bộ phiên bản mà bản Boot đó đã kiểm thử và quản lý.

Ví dụ, dependency sau không cần khai báo version riêng nếu dự án đã nhập Spring Boot dependency management:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-neo4j</artifactId>
</dependency>
```

Starter đưa SDN và các thành phần kết nối cần thiết vào dependency graph; BOM của Boot quyết định version được resolve.

### Spring Data release train và SDN

Các module Spring Data có thể mang số major/minor khác nhau vì chúng được phát triển và phát hành theo nhịp riêng. Spring Data dùng release train BOM để gom các version tương thích.

Ví dụ, release train 2025.0.13 quản lý SDN 7.5.13; release train 2026.1.0 quản lý SDN 8.2.0. Không chọn riêng spring-data-neo4j rồi giữ các module Spring Data khác ở một train không tương thích.

Nếu dùng Spring Boot, mặc định hãy để Boot quản lý bộ Spring Data. Chỉ override spring-data-bom.version khi có yêu cầu rõ ràng và đã xác nhận release train mới tương thích với Spring Framework mà Boot đang dùng.

### Neo4j Java Driver và Neo4j Server

Driver và server nói chuyện với nhau qua Bolt. Trong handshake, hai bên thương lượng phiên bản Bolt mới nhất mà cả hai cùng hỗ trợ. Cơ chế này giúp một driver có thể giao tiếp với nhiều thế hệ server.

Tuy nhiên, Bolt handshake chỉ xác nhận giao thức kết nối. Nó không làm cho một server cũ hiểu cú pháp Cypher mới, procedure mới, vector index mới hoặc thay đổi schema được giới thiệu ở server mới hơn.

## 3. Ma trận ví dụ theo dependency management chính thức

Bảng sau lấy version từ các trang Managed Dependency Coordinates của Spring Boot và tài liệu Spring Data. Đây là các bộ dependency do Boot quản lý, không phải lời khẳng định rằng mọi phiên bản Neo4j Server đều hỗ trợ mọi tính năng của ứng dụng.

| Spring Boot | Spring Framework | Spring Data Neo4j được quản lý | Neo4j Java Driver được quản lý | Neo4j Server cần kiểm tra |
|---|---:|---:|---:|---|
| 3.5.16 | 6.2.19 | 7.5.13 | 5.28.13 | Driver 5.28 có forward compatibility với 2025.x và 2026.x; kiểm tra ma trận chính xác cho server cũ hơn |
| 4.0.10 | 7.0.11 | 8.0.9 | 6.1.0 | Driver 6.x hỗ trợ 4.4.x, 5.x, 2025.x và 2026.x |
| 4.2.0 | 7.1.0 | 8.2.0 | 6.3.0 | Driver 6.x hỗ trợ 4.4.x, 5.x, 2025.x và 2026.x |

Các bộ version này được đối chiếu từ:

- Spring Boot 3.5.16 quản lý Spring Framework 6.2.19, Spring Data Neo4j 7.5.13 và Neo4j Java Driver 5.28.13.
- Spring Boot 4.0.10 quản lý Spring Framework 7.0.11, Spring Data Neo4j 8.0.9 và Neo4j Java Driver 6.1.0.
- Spring Boot 4.2.0 quản lý Spring Framework 7.1.0, Spring Data Neo4j 8.2.0 và Neo4j Java Driver 6.3.0.

Các phiên bản Boot, Framework, SDN và Driver trong bảng là những giá trị được Boot BOM quản lý tại thời điểm đối chiếu. Nếu build dùng thêm BOM khác, version catalog, dependency constraint hoặc explicit version, kết quả thực tế có thể khác bảng.

### Đọc cột Neo4j Server

Neo4j Java Driver 6.x hiện hỗ trợ kết nối đến Neo4j Server 4.4.x, 5.x, 2025.x và 2026.x. Driver 5.28 được công bố forward-compatible với Neo4j Server 2025.x và 2026.x.

Khi dùng Driver 5.28, hãy đọc tài liệu compatibility của đúng nhánh driver để xác nhận server cũ đang chạy. Khi dùng Driver 6.x, vẫn phải kiểm tra Cypher feature, edition, store format và yêu cầu JVM của server.

Không suy ra rằng “Driver hỗ trợ Server 2026” đồng nghĩa với “ứng dụng chạy trên Server 2026 mà không cần thay đổi”. Query dùng cú pháp chỉ xuất hiện trong Neo4j 2026 vẫn sẽ lỗi khi chạy trên Neo4j 5.x.

## 4. Phân biệt JVM của ứng dụng và JVM của Neo4j Server

Đây là hai môi trường chạy độc lập:

- JVM của ứng dụng chạy Spring Boot, SDN và Neo4j Java Driver.
- JVM của database chạy Neo4j Server.

Neo4j Java Driver 6.x yêu cầu Java 17 trở lên. Trong khi đó, Neo4j Server 2025.01 yêu cầu Java 21; Neo4j 2025.10 hỗ trợ Java 21 và Java 25. Neo4j 5.26 LTS hỗ trợ Java 17 và Java 21.

Do đó, ứng dụng có thể chạy trên Java 17 nhưng database server phải chạy trên Java 21 khi nâng lên Neo4j 2025.01. Không lấy yêu cầu Java của Driver để kết luận JVM của server đã đáp ứng.

| Thành phần | Cần xác minh |
|---|---|
| Spring Boot | Java baseline của dòng Boot đích |
| Neo4j Java Driver | Java runtime tối thiểu của nhánh driver |
| Neo4j Server | JVM được hỗ trợ cho đúng bản server |
| Build và CI | JDK dùng để compile, test và đóng gói |
| Production | JDK thực tế trong image/container chạy ứng dụng và database |

Với Neo4j 2025.01, còn cần kiểm tra các yêu cầu nâng cấp từ 5.26 LTS như chuyển cluster discovery service v1 sang v2 trước khi nâng cấp. Những yêu cầu này thuộc về database operations, không thể giải quyết chỉ bằng cách cập nhật dependency Java.

## 5. Những nguồn release notes cần đọc

Một lần nâng cấp SDN nên đọc tài liệu từ cả phía Spring và Neo4j. Mỗi nguồn trả lời một nhóm câu hỏi khác nhau.

| Nguồn | Cần tìm thông tin gì? |
|---|---|
| Spring Boot Release Notes | Dependency upgrades, Java baseline, auto-configuration, property changes, deprecations và breaking changes |
| Spring Boot Managed Dependency Coordinates | Version Boot thực sự quản lý cho SDN, Driver và các thư viện Spring |
| Spring Data Release Notes | Thay đổi chung trong Commons và release train |
| Spring Data Neo4j Reference / Changelog | API mapping, repository, template, transaction, query và dependency upgrades |
| Neo4j Java Driver Upgrade Guide / Changelog | Breaking changes giữa major driver, Java baseline, Bolt, API và behavior |
| Neo4j Server Upgrade & Migration Guide | Cypher changes, store format, cluster, authentication, configuration, Java runtime và quy trình upgrade database |
| Neo4j Cypher Compatibility | Cú pháp, function, clause và behavior theo phiên bản Cypher/server |

Không chỉ đọc trang What's New của phiên bản đích. Khi nâng qua nhiều major/minor, hãy đọc các ghi chú từ phiên bản hiện tại đến phiên bản đích, bao gồm cả các bước trung gian.

### Đọc release notes theo thứ tự

1. Ghi lại version hiện tại đã resolve trong build và version server đang chạy.
2. Chọn version đích của Spring Boot và Neo4j Server.
3. Mở release notes của Boot từ version hiện tại đến version đích.
4. Đối chiếu các dependency mà Boot đích quản lý.
5. Đọc Spring Data release train và SDN changelog tương ứng.
6. Đọc Neo4j Java Driver upgrade guide, đặc biệt khi đổi major từ 5.x sang 6.x.
7. Đọc Neo4j Server upgrade guide cho từng bước nâng server.
8. Ghi lại breaking change, deprecation, default change và yêu cầu vận hành có liên quan đến ứng dụng.
9. Lập test plan cho từng thay đổi có ảnh hưởng.

### Tìm kiếm từ khóa nào trong release notes?

- Breaking changes: API hoặc behavior không còn tương thích.
- Deprecated / Removed: API cũ còn cảnh báo hay đã bị xóa.
- Dependency upgrades: version thư viện được Boot hoặc SDN thay đổi.
- Java: yêu cầu JDK mới hoặc API Java bị thay đổi.
- Bolt / Protocol: thay đổi giao thức giao tiếp.
- Cypher: cú pháp, function, clause hoặc semantics.
- Transaction / Bookmark: behavior transaction và causal consistency.
- Mapping / Repository: thay đổi cách SDN hydrate, persist hoặc tạo query.
- Store format / Cluster: thay đổi ảnh hưởng database và vận hành.
- Configuration / Default: property, giá trị mặc định hoặc cấu hình bị thay đổi.

Sau khi tìm thấy mục liên quan, đọc phần giải thích và migration instruction xung quanh. Một tiêu đề dependency upgrade có thể kéo theo thay đổi Java baseline hoặc API transitively.

## 6. Xây dựng ma trận cho một dự án cụ thể

Không chỉ ghi version. Ma trận tốt cần có nguồn xác nhận và trạng thái kiểm tra:

| Thành phần | Hiện tại | Mục tiêu | Nguồn kiểm tra | Trạng thái |
|---|---|---|---|---|
| Spring Boot | 3.5.16 | 4.2.0 | Boot release notes và BOM | Chưa kiểm tra |
| Spring Framework | 6.2.19 | 7.1.0 | Boot BOM, Framework requirements | Chưa kiểm tra |
| Spring Data Neo4j | 7.5.13 | 8.2.0 | Spring Data BOM, SDN dependencies | Chưa kiểm tra |
| Neo4j Java Driver | 5.28.13 | 6.3.0 | Boot BOM, Driver upgrade guide | Chưa kiểm tra |
| Neo4j Server | 5.26 LTS | 2025.10 | Driver compatibility, Server upgrade guide | Chưa kiểm tra |
| Java ứng dụng | 17 | 17 hoặc cao hơn | Boot và Driver requirements | Chưa kiểm tra |
| Java database | 17 | 21 hoặc 25 | Neo4j Server requirements | Chưa kiểm tra |

Các trạng thái có thể dùng:

- PASS: đã có tài liệu xác nhận và test phù hợp.
- REVIEW: có hỗ trợ nhưng cần đọc thêm migration note hoặc xác minh behavior.
- BLOCKED: version hoặc yêu cầu không tương thích.
- NOT APPLICABLE: không dùng thành phần hoặc tính năng đó.

Không đánh dấu PASS chỉ vì ứng dụng compile. Cần có test kết nối và integration test trên đúng Neo4j Server đích.

## 7. Xác định version thực tế mà build sử dụng

Version khai báo trong file build chưa chắc là version cuối cùng được resolve. Version có thể đến từ:

- Spring Boot parent hoặc dependency BOM.
- Spring Data BOM.
- Một BOM khác được import.
- Explicit dependency version.
- Gradle version catalog hoặc dependency constraint.
- Dependency bắc cầu của một thư viện khác.

Vì vậy, cần xem dependency graph sau khi build tool giải quyết xong.

### Maven

Xem dependency tree cho ba thành phần quan trọng:

```bash
./mvnw dependency:tree \
  -Dincludes=org.springframework.data:spring-data-neo4j,org.neo4j.driver:neo4j-java-driver,org.springframework:spring-core
```

Xem effective POM để kiểm tra version management:

```bash
./mvnw help:effective-pom
```

Trong Windows PowerShell, dùng mvnw.cmd thay cho ./mvnw nếu wrapper của dự án là file batch.

### Gradle

Xem dependency tree của runtime:

```bash
./gradlew dependencies --configuration runtimeClasspath
```

Xem lý do một version cụ thể được chọn:

```bash
./gradlew dependencyInsight --dependency spring-data-neo4j --configuration runtimeClasspath
./gradlew dependencyInsight --dependency neo4j-java-driver --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-core --configuration runtimeClasspath
```

Nếu kết quả khác version trong Boot BOM, hãy tìm dependency nào đã ép version hoặc đưa BOM khác vào build.

## 8. Quản lý dependency đúng cách với Spring Boot

Khi dùng Spring Boot, nên khai báo starter và để BOM quản lý version:

```xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>4.2.0</version>
    <relativePath/>
</parent>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-neo4j</artifactId>
    </dependency>
</dependencies>
```

Không cần khai báo version riêng cho spring-data-neo4j hoặc neo4j-java-driver nếu dependency management của Boot đã quản lý chúng.

Nếu dùng Gradle với Spring Boot plugin:

```kotlin
plugins {
    id("org.springframework.boot") version "4.2.0"
    id("io.spring.dependency-management") version "1.1.7"
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-neo4j")
}
```

Nếu không dùng Spring Boot, có thể import Spring Data BOM trực tiếp:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.data</groupId>
            <artifactId>spring-data-bom</artifactId>
            <version>2026.1.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Khi dùng Spring Data BOM độc lập, cần tự bảo đảm Spring Framework và các dependency nền khác tương thích với release train. BOM Spring Data không thay thế BOM của Spring Boot.

### Khi cần override Spring Data BOM trong Boot

Spring Boot cho phép dùng property spring-data-bom.version để chọn release train Spring Data khác với version mặc định mà Boot quản lý. Chỉ dùng khi có lý do cụ thể, ví dụ cần một bug fix của SDN đã phát hành nhưng chưa nằm trong Boot BOM hiện tại.

Trước khi override:

1. Kiểm tra SDN phiên bản đích yêu cầu Spring Framework tối thiểu nào.
2. Kiểm tra Spring Data Commons cùng train.
3. Kiểm tra Neo4j Java Driver mà SDN phiên bản đó sử dụng.
4. Kiểm tra Boot auto-configuration có còn tương thích không.
5. Chạy dependency tree và integration test.

Không dùng property này để kéo một SDN mới vào một Boot cũ nếu SDN yêu cầu Spring Framework major mới hơn. Việc override BOM không tự nâng Spring Framework theo đúng thế hệ.

## 9. Đọc compatibility Driver–Server đúng cách

Neo4j Java Driver dùng Bolt để giao tiếp với Neo4j Server. Tài liệu Driver công bố compatibility theo major line:

| Driver line | Server compatibility được tài liệu hiện hành nêu |
|---|---|
| 5.28 | Forward-compatible với Neo4j 2025.x và 2026.x |
| 6.x | Neo4j 4.4.x, 5.x, 2025.x và 2026.x |

Đây là compatibility về kết nối và giao thức. Vẫn cần kiểm tra phiên bản server cụ thể, đặc biệt khi dùng tính năng mới hoặc phiên bản cũ hơn.

Ví dụ:

- Driver 6.x có thể kết nối Neo4j 5.x, nhưng query dùng SEARCH hoặc cú pháp chỉ có trong Neo4j 2026 vẫn không chạy trên server 5.x.
- Driver 5.28 forward-compatible với server 2025/2026, nhưng không có nghĩa API Java mới chỉ có trong Driver 6.x sẽ xuất hiện trong Driver 5.28.
- Server có thể chấp nhận kết nối Bolt nhưng từ chối procedure, function hoặc syntax mà phiên bản server chưa hỗ trợ.

Khi nâng server, hãy đọc mục deprecations/additions/removals của Cypher và kiểm tra mọi query custom trong @Query, Neo4jClient và Neo4jTemplate.

## 10. Ví dụ đọc release notes khi nâng từ Boot 3.5 lên Boot 4.2

Giả sử ứng dụng đang ở bộ version sau:

```text
Spring Boot             3.5.16
Spring Framework        6.2.19
Spring Data Neo4j       7.5.13
Neo4j Java Driver       5.28.13
Neo4j Server            5.26 LTS
```

Mục tiêu là:

```text
Spring Boot             4.2.0
Spring Framework        7.1.0
Spring Data Neo4j       8.2.0
Neo4j Java Driver       6.3.0
Neo4j Server            2025.10
```

Không nên thay toàn bộ version rồi chỉ chạy compile. Hãy chia thành các nhóm thay đổi:

### Nhóm 1: Spring Boot và Spring Framework

Boot 4.2.0 chuyển sang Spring Framework 7.1.0 và Spring Data 2026.1.0. Đọc Boot 4.0, 4.1 và 4.2 release notes để không bỏ qua thay đổi từ các phiên bản trung gian.

Đối chiếu:

- Java baseline và build plugin.
- API Spring Framework bị deprecate hoặc remove.
- Auto-configuration và configuration property.
- Thay đổi package/module hoặc starter.
- Test infrastructure, transaction và observability.

### Nhóm 2: SDN 7.5 lên 8.2

SDN 8.2 thuộc Spring Data 2026.1 và yêu cầu Spring Framework 7.1.0. Đọc SDN changelog và upgrade notes để xác định thay đổi trong mapping, repository, template, client và transaction.

Không chỉ tìm thay đổi ở annotation. Một thay đổi trong Spring Data Commons có thể ảnh hưởng repository behavior dù SDN không đổi tên API.

### Nhóm 3: Driver 5.28 lên 6.3

Đây là thay đổi major. Đọc Driver 5.28-to-6.x upgrade guide và changelog. Kiểm tra:

- Java baseline.
- API đã deprecated hoặc bị xóa.
- Cách xử lý giá trị, record và type mapping.
- Authentication, encryption và TLS.
- Metrics, logging, tracing và observation.
- Reactive API và session/transaction behavior.

Nếu ứng dụng dùng trực tiếp Driver ngoài SDN, hãy kiểm tra mọi chỗ tạo Driver, Session, Transaction hoặc gọi API driver. Nếu chỉ dùng SDN abstraction, vẫn cần kiểm thử behavior vì driver là dependency nền của SDN.

### Nhóm 4: Neo4j Server 5.26 lên 2025.10

Đọc hướng dẫn nâng từ Neo4j 5.26 LTS sang 2025.01 và các bản 2025.x tiếp theo.

Ví dụ các điều kiện phải kiểm tra:

- Neo4j 2025.01 yêu cầu Java 21 cho JVM của database; 2025.10 hỗ trợ Java 21 và Java 25.
- Cluster discovery service v1 bị loại bỏ từ 2025.01; chuyển sang v2 phải hoàn tất trước khi nâng.
- Store format cần được xem xét, đặc biệt với database cũ và môi trường Enterprise.
- Cypher query, procedure và configuration có thể cần cập nhật.

Driver mới chỉ giải quyết lớp kết nối. Nó không tự chuyển store format, không thay đổi cluster discovery và không sửa câu Cypher.

### Kết quả của việc đọc release notes

Sau khi đọc, tạo danh sách thay đổi có chủ sở hữu và bằng chứng:

| Thay đổi | Tác động | Việc cần làm |
|---|---|---|
| Spring Framework 7.1 | Có thể ảnh hưởng API hoặc integration | Compile, test context, test transaction |
| SDN 8.2 | Có thể ảnh hưởng mapping/repository | Integration test entity, relationship, custom query |
| Driver 6.3 | Major API và runtime change | Kiểm tra API trực tiếp, test Bolt/TLS/auth |
| Neo4j 2025.10 | Server JVM và feature change | Chuẩn bị Java 21/25, cluster, store, Cypher |

## 11. Thứ tự nâng cấp và chiến lược giảm rủi ro

Neo4j khuyến nghị có thể nâng Driver trước khi nâng Server vì việc rollback ứng dụng thường dễ hơn rollback database. Driver 5.28 còn forward-compatible với Neo4j 2025/2026, giúp một số hệ thống có thể triển khai theo từng bước.

Với ứng dụng SDN, cần thêm một ràng buộc: Driver là dependency mà SDN sử dụng. Không tự ý override major version của Driver trong khi giữ nguyên SDN nếu cặp version đó chưa được xác nhận tương thích.

Một kế hoạch có thể chia thành các đợt:

1. **Chuẩn bị:** chụp dependency tree, backup database, xác nhận restore, lập ma trận và chạy test baseline.
2. **Nâng ứng dụng:** nâng Boot/SDN/Driver theo một bộ BOM tương thích, giữ server ở version hiện tại nếu driver đích hỗ trợ server đó.
3. **Kiểm thử ứng dụng:** chạy integration test trên đúng server version đang dùng, xác minh mapping, transaction, query, cluster và authentication.
4. **Chuẩn bị database:** kiểm tra Java server runtime, cluster discovery, store format, plugins, extensions và Cypher migration.
5. **Nâng server:** thực hiện theo upgrade guide của Neo4j, theo dõi log và trạng thái cluster.
6. **Kiểm thử sau nâng cấp:** chạy smoke test, repository integration test, query regression và kiểm tra performance.

Nếu ứng dụng đang ở SDN 7.x và cần chuyển sang SDN 8.x, không ép riêng Driver 6.x vào SDN 7.x để đi trước. Hãy dùng bộ version mà Boot BOM hoặc SDN release train xác nhận tương thích, rồi kiểm thử toàn bộ ứng dụng.

## 12. Những kiểm thử cần có trước và sau nâng cấp

### Kiểm thử dependency và khởi động

- Build resolve đúng Boot, Framework, SDN và Driver dự kiến.
- Application context khởi động với cấu hình Neo4j production-like.
- Driver kết nối được tới đúng server version.
- Authentication, TLS và routing hoạt động.

### Kiểm thử SDN mapping và persistence

- Tạo, đọc, cập nhật và xóa node.
- Lưu relationship đơn và relationship có property.
- Kiểm tra identity, version và optimistic locking.
- Kiểm tra projection và custom repository query.
- Kiểm tra custom Cypher và DTO mapping.

### Kiểm thử transaction và cluster

- Commit và rollback.
- Read-your-writes và bookmark.
- Read-only transaction, routing đến replica.
- Retry khi transient failure.
- Transaction timeout và lỗi kết nối.

### Kiểm thử tính năng Neo4j

- Index và constraint.
- Cypher function/procedure đang dùng.
- Vector/full-text/spatial search nếu có.
- APOC hoặc plugin ngoài.
- Store format và cluster behavior.

### Kiểm thử vận hành

- Health check và readiness.
- Metrics, logging và tracing.
- Connection pool và session lifecycle.
- Backup/restore.
- Latency và query plan của các truy vấn quan trọng.

Mock repository không đủ để xác minh nâng cấp SDN hoặc Driver. Cần integration test với Neo4j Server thực tế, thường dùng Testcontainers hoặc môi trường staging có version khớp production.

## 13. Những lỗi thường gặp khi đọc ma trận tương thích

| Sai lầm | Vì sao sai | Cách xử lý |
|---|---|---|
| Chọn SDN mới nhất mà không kiểm tra Boot | SDN có thể yêu cầu Spring Framework major mới | Đối chiếu Boot BOM, Framework và SDN dependencies |
| Chỉ nâng spring-data-neo4j mà không nâng Commons | Các module Spring Data được phát hành theo release train | Dùng Boot BOM hoặc Spring Data BOM |
| Override Driver major độc lập với SDN | SDN có thể được build/test với driver line khác | Dùng dependency management tương thích và kiểm tra dependency tree |
| Thấy Driver kết nối được nên cho rằng Cypher query đều chạy | Bolt compatibility khác Cypher feature compatibility | Đọc Cypher compatibility và test query |
| Chỉ đọc release notes của phiên bản đích | Có thể bỏ lỡ migration step ở phiên bản trung gian | Đọc tất cả release notes giữa source và target |
| Dùng milestone hoặc RC trong production như GA | API và dependency có thể còn thay đổi | Chọn bản GA/service release trừ khi có chính sách riêng |
| Dùng JDK ứng dụng để suy ra JDK server | Hai JVM có yêu cầu độc lập | Kiểm tra Boot/Driver và Neo4j Server riêng |
| Nâng database mà chưa đọc migration guide | Có thể bỏ sót store format hoặc cluster prerequisite | Thực hiện checklist server upgrade |
| Chỉ chạy compile | Compile không xác minh Bolt, Cypher, mapping hoặc transaction | Chạy integration và regression test |
| Không kiểm tra dependency đã resolve | Transitive dependency có thể thắng version dự kiến | Dùng Maven dependency tree hoặc Gradle dependencyInsight |

## 14. Checklist trước khi chốt một bộ version

1. Đã ghi lại version thực tế của Boot, Framework, SDN, Driver, Server và JDK chưa?
2. Boot BOM có quản lý đúng SDN và Driver mà build đang resolve không?
3. SDN có tương thích với Spring Framework và Spring Data Commons trong cùng release train không?
4. Driver có hỗ trợ đúng Neo4j Server version không?
5. Câu Cypher và procedure có được server đích hỗ trợ không?
6. JVM của ứng dụng và JVM của Neo4j Server có đáp ứng yêu cầu riêng không?
7. Đã đọc release notes của tất cả phiên bản trung gian chưa?
8. Đã đọc breaking changes, deprecations, removals và default changes chưa?
9. Nếu nâng server, đã kiểm tra store format, cluster, plugin và backup/restore chưa?
10. Dependency tree đã được lưu lại để review chưa?
11. Integration test có chạy trên đúng Neo4j Server version đích không?
12. Có kế hoạch rollback ứng dụng và kế hoạch phục hồi database không?

## 15. Tự kiểm tra

1. Vì sao không thể chỉ chọn version mới nhất của Boot, SDN, Driver và Neo4j Server một cách độc lập?
2. Spring Boot BOM quản lý những dependency nào trong ứng dụng SDN?
3. Spring Data release train BOM giải quyết vấn đề gì khi các module có số version khác nhau?
4. Vì sao SDN 8.2 cần được ghép với thế hệ Spring Framework phù hợp?
5. Driver 6.x hiện hỗ trợ những dòng Neo4j Server nào?
6. Driver–Server tương thích Bolt có bảo đảm mọi Cypher query của ứng dụng đều chạy không? Vì sao?
7. Vì sao phải kiểm tra JVM của ứng dụng và JVM của Neo4j Server riêng?
8. Khi nâng từ SDN 7.5 lên 8.2, những nguồn release notes nào cần đọc?
9. Vì sao cần xem dependency tree sau khi build resolve?
10. Tại sao không nên override major version của Neo4j Java Driver một cách độc lập với SDN?
11. Khi nâng Neo4j 5.26 lên 2025.01, các yêu cầu server-side nào cần được xem xét?
12. Vì sao compile thành công chưa đủ để kết luận nâng cấp an toàn?

Khi đọc release notes theo từng lớp và xác nhận các ràng buộc bằng dependency graph, người học có thể xây dựng ma trận Boot–SDN–Driver–Neo4j có căn cứ, phát hiện sớm xung đột version và tổ chức nâng cấp theo từng bước có thể kiểm thử và rollback.

## Tài liệu tham khảo

- [Spring Boot — Managed Dependency Coordinates](https://docs.spring.io/spring-boot/appendix/dependency-versions/coordinates.html)
- [Spring Boot 4.2.0 — Release Notes](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.2-Release-Notes)
- [Spring Data Neo4j — Dependencies](https://docs.spring.io/spring-data/neo4j/reference/dependencies.html)
- [Spring Data Neo4j 7.5 — Dependencies](https://docs.spring.io/spring-data/neo4j/reference/7.5/dependencies.html)
- [Spring Data 2026.1.0 — Generally Available](https://spring.io/blog/2026/11/19/spring-data-2026-1-0-generally-available/)
- [Spring Data Neo4j — Releases and Changelog](https://github.com/spring-projects/spring-data-neo4j/releases)
- [Neo4j Java Driver — Installation and Server Compatibility](https://neo4j.com/docs/java-manual/current/install/)
- [Neo4j Java Driver — Upgrade from Older Versions](https://neo4j.com/docs/java-manual/current/upgrade/)
- [Neo4j Java Driver — Releases](https://github.com/neo4j/neo4j-java-driver/releases)
- [Neo4j Operations Manual — System Requirements](https://neo4j.com/docs/operations-manual/current/installation/requirements/)
- [Neo4j Upgrade and Migration Guide — From 5.26 LTS to 2025.01 and later](https://neo4j.com/docs/upgrade-migration-guide/current/version-2025-2026/upgrade/)
- [Neo4j Cypher Manual — Deprecations, Additions, Removals and Compatibility](https://neo4j.com/docs/cypher-manual/current/deprecations-additions-removals-compatibility/)
