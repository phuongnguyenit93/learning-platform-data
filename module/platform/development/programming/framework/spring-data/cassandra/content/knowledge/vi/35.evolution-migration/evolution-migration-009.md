# Nâng Spring Boot, Spring Data, Java Driver và Cassandra theo ma trận tương thích

**Chương: Tiến hóa và di trú — Spring Data Cassandra**

Một ứng dụng dùng **Spring Data Cassandra** không chỉ có một phiên bản cần nâng cấp. Đường truy cập dữ liệu bao gồm **Spring Boot**, **Spring Data Cassandra**, **Cassandra Java Driver**, **Apache Cassandra server**, Java runtime và cả schema CQL. Khi nâng một thành phần, phần mềm có thể **biên dịch thành công nhưng sai kết quả**, **khởi động được nhưng không kết nối được** hoặc **đọc dữ liệu cũ được nhưng thất bại khi gặp schema/kiểu dữ liệu mới**.

Ví dụ, nâng Spring Boot có thể kéo theo Spring Data Cassandra và Java Driver mới qua BOM; trong khi nâng Cassandra server thay đổi môi trường thực thi CQL, native protocol, cấu hình node và quá trình lưu trữ. Trường hợp thay đổi partition key còn phải chuyển dữ liệu sang bảng mới, vì không thể tùy tiện sửa khóa chính bằng `ALTER TABLE` như thêm cột thường.

Bài này trình bày phương pháp **lập ma trận tương thích có nguồn kiểm chứng, nâng từng chặng, chạy kiểm thử hợp đồng và triển khai có đường quay lại**. Kết quả mong muốn là giữ cho `CassandraRepository`, `CassandraTemplate`, `CqlTemplate` và các truy vấn CQL hoạt động đúng với partition key, consistency, paging và giới hạn hiệu năng của hệ thống phân tán.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt **tương thích dependency**, **tương thích native protocol** và **tương thích hành vi dữ liệu**.
- Đọc Spring Boot BOM, Spring Data release train và dependency graph để xác nhận chính xác bản Java Driver đang chạy.
- Lập bảng mục tiêu cho Spring Boot, Spring Data Cassandra, Java Driver, Cassandra server và JDK mà không coi phiên bản “mới nhất” của từng sản phẩm là tự động tương thích.
- Kiểm tra thay đổi API, property, mapping entity, repository, `CassandraTemplate`, CQL, consistency và paging khi nâng cấp.
- Lập kế hoạch **rolling upgrade Cassandra** tách biệt với rolling deploy ứng dụng và migration schema.
- Tổ chức kiểm thử nhiều phiên bản, canary, quan sát p95/p99, lỗi Driver, retry và đối soát dữ liệu.
- Đề xuất rollback phù hợp với mức độ thay đổi, nhất là khi DDL, SSTable hoặc dữ liệu đã chuyển đổi khiến quay về phiên bản cũ trở nên phức tạp.

## 2. Bốn lớp tương thích cần kiểm tra

Một dòng “Spring Boot X hỗ trợ Cassandra Y” thường thiếu thông tin. Thực tế có ít nhất bốn lớp:

| Lớp | Cặp thành phần | Điều cần chứng minh | Ví dụ dấu hiệu không tương thích |
|---|---|---|---|
| **Build/runtime** | Java ↔ Spring Boot ↔ Spring Framework ↔ Spring Data | Build khớp API và runtime yêu cầu; phiên bản thư viện được quản lý đúng | `NoSuchMethodError`, `ClassNotFoundException`, bean auto-config không tạo được |
| **Driver integration** | Spring Data Cassandra ↔ Java Driver | Adapter, exception translation, codec, mapper, cấu hình và session hoạt động | Import Driver 3.x lẫn 4.x, codec lỗi, cấu hình Driver bị bỏ qua |
| **Wire protocol** | Java Driver ↔ Cassandra server | Driver bắt tay, thương lượng protocol và hỗ trợ CQL được dùng | Không kết nối được node, protocol negotiation error, tính năng CQL không có |
| **Data contract** | Schema CQL ↔ entity/repository ↔ dữ liệu cũ và mới | Query theo khóa đúng; deserialize/serialize ổn; consistency/paging đúng | `InvalidQueryException`, sai tên cột, thiếu dữ liệu sau dual-write |

~~~mermaid
flowchart LR
    A["JDK và build tool"] --> B["Spring Boot BOM"]
    B --> C["Spring Data Cassandra"]
    B --> D["Cassandra Java Driver 4.x"]
    C --> D
    D -->|"Native CQL protocol"| E["Apache Cassandra cluster"]
    F["Schema: PK, UDT, index, TTL"] --> E
    G["Entity / Repository / Template / CQL"] --> C
    H["Release notes + integration tests"] -.-> B
    H -.-> D
    H -.-> E
~~~

**Tương thích biên dịch không chứng minh tương thích vận hành.** Một ứng dụng có thể gọi `findById` thành công trên một node lab nhưng lỗi ở `LOCAL_QUORUM` khi cluster nhiều replica đang nâng cấp; một truy vấn phân trang có thể trả trang đầu đúng nhưng hỏng khi dùng paging state giữa những cấu hình/schema khác nhau.

## 3. Lập ma trận tương thích dựa vào nguồn chính thức

### 3.1. Phần Spring Boot ↔ Spring Data ↔ Driver do BOM quản lý

**Bảng tham chiếu tại ngày 25/11/2026**, trích từ *Managed Dependency Coordinates* của các nhánh Spring Boot tương ứng. Đây là **bảng phiên bản dependency** khi giữ cấu hình quản lý dependency mặc định, không phải lời cam kết một-tất-cả với bất kỳ Cassandra server hoặc extension nào:

| Spring Boot | Spring Data Cassandra do Boot quản lý | Java Driver core do Boot quản lý | JDK tối thiểu của Boot | Cách hiểu |
|---|---|---|---|---|
| `3.5.16` | `4.5.13` | `org.apache.cassandra:java-driver-core:4.19.3` | Java 17 | Nhánh ứng dụng Boot 3.5 |
| `4.0.10` | `5.0.9` | `org.apache.cassandra:java-driver-core:4.19.4` | Java 17 | Nhánh Boot 4.0 / Spring Data 5.0 |
| `4.2.0` | `5.2.0` | `org.apache.cassandra:java-driver-core:4.19.4` | Java 17 | Nhánh Boot 4.2 / Spring Data 5.2 |

Nguồn đối chiếu:

- [Spring Boot 3.5 — Managed Dependency Coordinates](https://docs.spring.io/spring-boot/3.5/appendix/dependency-versions/coordinates.html)
- [Spring Boot 4.0 — Managed Dependency Coordinates](https://docs.spring.io/spring-boot/4.0/appendix/dependency-versions/coordinates.html)
- [Spring Boot — Managed Dependency Coordinates của nhánh hiện hành](https://docs.spring.io/spring-boot/appendix/dependency-versions/coordinates.html)
- [Spring Boot 4.0 — System Requirements](https://docs.spring.io/spring-boot/4.0/system-requirements.html)

**Lưu ý quan trọng về bảng:**

1. Phiên bản patch trong bảng **sẽ thay đổi** khi có bản vá mới. Trong mỗi đợt nâng, tra đúng tài liệu hoặc BOM tại phiên bản **đích thực tế**, không chép bảng này thành chính sách bất biến.
2. Các hàng là **ví dụ bộ dependency được quản lý cùng nhau**. Không tự suy ra rằng mọi cặp Spring Data 4.5.x + Driver 4.19.x hoặc 5.2.x + một bản Driver bất kỳ đều đã được kiểm tra cho ứng dụng của bạn.
3. Java Driver 4.x có **tọa độ Maven** khác giữa những giai đoạn phân phối. Trong các phiên bản Apache mới, có artifact `org.apache.cassandra:java-driver-core`; mã Java vẫn dùng package `com.datastax.oss.driver.api.core.*`. Đổi **groupId** không đồng nghĩa đổi package import theo tên nhóm artifact.
4. Khi dùng `spring-boot-starter-data-cassandra`, thông thường **không cần** khai báo tường minh phiên bản Spring Data và Driver; Boot BOM sẽ chọn tập dependency đồng bộ.
5. JDK của **Cassandra server** là câu chuyện riêng với JDK chạy Spring Boot. Ví dụ, Cassandra 5.0 có yêu cầu/runtime Java riêng; kiểm tra hướng dẫn của Cassandra khi nâng node.

Nếu dự án còn ở Boot 2.x, Spring Data đời cũ hoặc Driver 3.x, cần đi qua các hướng dẫn migration của từng thế hệ. Đừng áp thẳng một patch dependency của Boot 4.x lên ứng dụng chưa chuyển phần javax/Jakarta, API Spring và cấu hình cần thiết.

### 3.2. Ma trận Spring ↔ Cassandra server không phải phép nhân các hàng

Lập tiếp **ma trận kiểm chứng kết nối**, trong đó mỗi ô thể hiện bài test sẽ chạy và kết quả:

| Bộ client ứng dụng | Cassandra 4.1 | Cassandra 5.0 | Tiêu chí bắt buộc |
|---|---|---|---|
| Boot 3.5.x + Data 4.5.x + Driver do BOM quản lý | Cần chạy integration test | Cần chạy integration test | Connect/TLS/auth, CQL, mapping, paging, consistency |
| Boot 4.0.x + Data 5.0.x + Driver do BOM quản lý | Cần chạy integration test | Cần chạy integration test | Cùng contract tests; thêm test API/config thay đổi |
| Boot 4.2.x + Data 5.2.x + Driver do BOM quản lý | Cần chạy integration test | Cần chạy integration test | Cùng contract tests; thử cả rolling/mixed state nếu cần |

“Cần chạy integration test” **không có nghĩa tổ hợp không được hỗ trợ**. Nó thể hiện bằng chứng cần được thu cho **ứng dụng, schema, tính năng CQL và bản patch cụ thể**. Trước khi gán nhãn “PASS”, đối chiếu tài liệu chính thức và kết quả chạy thật của tổ hợp đó.

Java Driver 4.x hỗ trợ thương lượng native protocol. Tài liệu Driver 4.19 mô tả hỗ trợ protocol v3–v5 và Cassandra 4.x thương lượng v5. **Đừng ép** `advanced.protocol.version` hoặc mặc định các tính năng mới của Cassandra 5.0 đều dùng được chỉ vì session đã kết nối. Một tính năng CQL mới còn phụ thuộc **phiên bản server, driver/codec và API ứng dụng**.

Nguồn: [Apache Cassandra Java Driver — Native Protocol](https://apache.github.io/cassandra-java-driver/4.19.0/core/native_protocol/).

### 3.3. Thêm các chiều thường bị quên vào bảng thực tế

Ma trận cho doanh nghiệp nên có thêm:

| Chiều | Ví dụ dữ liệu cần ghi | Nguy cơ khi bỏ quên |
|---|---|---|
| JDK ứng dụng | 17, 21; vendor và patch | Lỗi JVM, TLS provider, bytecode/build tool |
| JDK node Cassandra | Bản được Cassandra server cho phép | Node không chạy được hoặc GC behavior khác |
| Build plugins | Maven/Gradle, annotation processor | Không sinh mapper, test plugin không tương thích |
| Spring Cloud / Observability | Release train, Micrometer, Actuator | Auto-configuration/metric thay đổi |
| Native protocol | Tự thương lượng hay cấu hình cưỡng bức | Fail kết nối khi mixed version |
| Driver custom codecs | UUID/Instant/UDT/vector tự viết | Mapping sai hoặc codec không còn phù hợp |
| Security | Authentication, TLS, CA, hostname verification | Session khởi động thất bại, mất bảo đảm bảo mật |
| Cluster topology | RF, DC, rack/AZ, CL, node count | Kết quả test đơn node che lỗi quorum |
| Query contract | PK, clustering, bảng read model, paging | Query chạy được nhưng sai dữ liệu/hiệu năng |

## 4. Chụp hiện trạng trước khi thay version

Không thể lập ma trận chính xác chỉ từ `build.gradle` hoặc `pom.xml` nếu dự án có overrides, dependency constraints, shaded artifacts hoặc BOM khác. Cần ghi lại **dependency tree đã resolve**.

### 4.1. Kiểm tra với Maven

~~~bash
# Chạy tại thư mục dự án ứng dụng, không phải tại Cassandra node.
mvn -version
mvn help:effective-pom
mvn dependency:tree -Dincludes=org.springframework.data:*,org.apache.cassandra:*,com.datastax.oss:*
~~~

`effective-pom` giúp kiểm tra parent/BOM, dependency management và overrides. `dependency:tree` cho biết bản thật sự được kéo vào classpath; các plugin và cú pháp filter có thể khác theo phiên bản Maven Dependency Plugin, nên điều chỉnh khi cần.

### 4.2. Kiểm tra với Gradle

~~~bash
./gradlew --version
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-data-cassandra --configuration runtimeClasspath
./gradlew dependencyInsight --dependency java-driver-core --configuration runtimeClasspath
~~~

Các lệnh trên dùng cho dự án Java/Gradle có `runtimeClasspath`. Nếu module plugin có configuration khác, thay đúng configuration mà ứng dụng runtime sử dụng.

**Điều cần xác minh:** Chỉ có **một phiên bản mong muốn** của các module Spring Data Cassandra và Driver chính; không vô tình kéo Driver 3.x song song với 4.x hoặc khai báo nhiều artifact core trùng chức năng. Để kiểm soát reproducibility, lưu lockfile/SBOM và commit phiên bản plugin/BOM được phê duyệt.

### 4.3. Bảng inventory ban đầu

~~~text
Application: orders-api
Current Boot:            [from build]
Current Spring Data:     [from resolved classpath]
Current Java Driver:     [group:artifact:version]
JDK application:         [version/vendor]
Cassandra servers:      [exact versions per node]
Cassandra keyspace/CL:   [RF/DC/LOCAL_QUORUM etc.]
Schema version/hash:     [migration artifact]
Custom codecs/session:  [yes/no; source owner]
Spring Cloud/test libs: [versions]
Rollback artifacts:     [app image + schema/backfill/backup plan]
~~~

Trong ví dụ này, các dấu `[...]` là ô bắt buộc **thu thập từ hệ thống**, không được điền bằng suy đoán. Tên “orders-api” chỉ để minh họa.

## 5. Quản lý dependency bằng BOM thay vì pin từng thư viện

### 5.1. Maven với Spring Boot parent

~~~xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>4.0.10</version>
    <relativePath/>
</parent>

<properties>
    <java.version>17</java.version>
</properties>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-cassandra</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Đây là **mẫu nâng lên Boot 4.0.10 theo bảng tham chiếu**, không phải lời khuyên mọi dự án phải dùng đúng bản patch này. Phiên bản Spring Data Cassandra và Java Driver được lấy từ Boot dependency management; không thêm một `<version>` độc lập vào dependency Cassandra nếu chưa có lý do và ma trận kiểm thử tương ứng.

Với dự án không dùng Boot parent, có thể import `spring-boot-dependencies` vào `dependencyManagement`. Khi đó phải kiểm tra phiên bản các Maven plugin/build setup riêng vì import BOM chỉ quản lý dependency, không tự cấu hình toàn bộ hành vi build như parent.

### 5.2. Gradle với Spring Boot plugin

Ví dụ Groovy DSL khi dùng thêm `io.spring.dependency-management`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '4.0.10'
    id 'io.spring.dependency-management' version '1.1.7'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-cassandra'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Plugin quản lý dependency trong ví dụ là một lựa chọn minh họa; **kiểm tra bản plugin tương thích với Gradle/Boot mục tiêu** trong ứng dụng thực tế. Với Gradle native platform/BOM, cú pháp quản lý sẽ khác. Sau thay đổi, chạy `dependencyInsight` để xác nhận bản Driver được chọn, thay vì chỉ nhìn mã build.

### 5.3. Khi nào override driver được chấp nhận?

Ví dụ có CVE hoặc lỗi Driver ảnh hưởng production mà Boot BOM chưa cập nhật, có thể cân nhắc override trong phạm vi đã kiểm chứng:

1. Nêu rõ vấn đề cần vá và phiên bản driver tối thiểu theo advisories/changelog.
2. Xác nhận Spring Data Cassandra mục tiêu có thể dùng bản Driver đó; không trộn tùy tiện module mapper/query-builder khác version.
3. Chạy integration/contract/soak test với cluster hiện tại và target.
4. Ghi override cùng lý do, người duyệt và điều kiện gỡ bỏ khi Boot BOM cập nhật.

Đổi riêng Driver để “mới nhất” có thể làm hỏng lựa chọn dependency đã kiểm thử của Boot; nhưng bỏ qua bản vá bảo mật có căn cứ cũng không phải lựa chọn đúng. Quyết định phải dựa trên ma trận và bằng chứng thử nghiệm.

## 6. Breaking changes cần rà soát khi đi qua major version

### 6.1. Spring Boot / Spring Framework

Khi nâng Boot 2.x lên 3.x hoặc 3.x lên 4.x, cần đọc migration guide và release notes cho từng chặng. Các nhóm thay đổi thường chạm tới:

- JDK tối thiểu và phiên bản Gradle/Maven hỗ trợ.
- Namespace Java/Jakarta, dependency Jakarta EE và các thư viện liên quan.
- Điều kiện kích hoạt auto-configuration, module/starter, cách tạo bean và test slice.
- Tên, vị trí, kiểu dữ liệu và mặc định của configuration properties.
- Actuator, metrics, tracing, logging, security và behavior của các starter khác.

Ví dụ đường cấu hình kết nối Cassandra trong Boot 3.x/4.x:

~~~yaml
spring:
  cassandra:
    contact-points: ${CASSANDRA_CONTACT_POINTS}
    port: ${CASSANDRA_PORT:9042}
    local-datacenter: ${CASSANDRA_LOCAL_DC}
    keyspace-name: ${CASSANDRA_KEYSPACE}
    username: ${CASSANDRA_USERNAME}
    password: ${CASSANDRA_PASSWORD}
~~~

Trong các nhánh Boot 2.x, nhiều property nằm dưới `spring.data.cassandra.*`. Việc app start không chứng minh mọi cấu hình cũ vẫn được sử dụng: **cấu hình bị bỏ qua** có thể khiến Driver dùng sai DC, timeout, consistency hoặc endpoint. Nên kiểm tra mapping property và giá trị runtime bằng công cụ an toàn, tránh in secret.

`spring-boot-properties-migrator` có thể hữu ích **tạm thời** khi chuyển những property đã đổi tên; nó không thay thế kiểm thử hành vi và nên được gỡ sau migration.

### 6.2. Spring Data Cassandra

Kiểm tra thay đổi ở:

- Repository method, query derivation, `@Query` binding và mapping giữa tên property Java với tên cột CQL.
- `@Table`, `@PrimaryKey`, `@PrimaryKeyClass`, `@PrimaryKeyColumn`, clustering order và composite partition key.
- `CassandraTemplate`/`CqlTemplate`, `SessionFactory`, converters và các hook tùy biến.
- Exception translation sang hệ thống Spring `DataAccessException`.
- Hành vi reactive (`Mono`/`Flux`), thread scheduling và nơi nhận exception.
- Các constructor/method đã deprecated hoặc bị gỡ bỏ; thay đổi metadata/schema action.

**Không suy** rằng mapping “compile được” nghĩa là kết quả đọc vẫn giống trước. Khi đổi converter của `Instant`/`LocalDate`/`UUID` hay UDT, hãy kiểm thử bằng **dữ liệu đã ghi bởi phiên bản cũ** và bằng dữ liệu mới.

### 6.3. Java Driver 3.x và 4.x

Một ứng dụng quá cũ có thể còn import:

~~~java
// Driver 3.x — API cũ, dùng để nhận diện mã cần migration.
import com.datastax.driver.core.Session;
import com.datastax.driver.core.Cluster;
~~~

Trong Java Driver 4.x, làm việc với `CqlSession`:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.Row;

void inspect(CqlSession session) {
    Row row = session.execute(
            "SELECT release_version FROM system.local").one();
    if (row != null) {
        System.out.println("CQL session is ready");
    }
}
~~~

**Không** trộn import `com.datastax.driver.core.*` và `com.datastax.oss.driver.api.core.*` trong luồng tương tác Cassandra hiện đại. Nâng Driver 3 → 4 là bước API lớn: cấu hình, session, async/paging, retry, codecs và mapper có thay đổi. Dùng [Java Driver Upgrade Guide](https://apache.github.io/cassandra-java-driver/4.19.0/upgrade-README/) thay vì thay số version rồi hy vọng tương thích nhị phân.

Ở các bản Driver 4.x, một số biểu hiện lỗi cũng thay đổi (ví dụ `AllNodesFailedException` so với các lỗi node đơn lẻ ở tình huống cụ thể). Khi nâng, theo dõi cả **cause và lỗi theo từng node**, không chỉ chuỗi tên exception phía ngoài.

### 6.4. CQL và schema không “tự di trú” theo Maven BOM

Spring Data đổi version **không đồng nghĩa đã nâng schema Cassandra**. Repository dùng partition key cũ vẫn phát CQL cũ nếu bạn chưa sửa. Schema migration là quá trình riêng, có version, DDL, backfill, kiểm chứng và điều kiện rollout riêng.

Đặc biệt, không tự bật `CREATE_DROP` hay chế độ schema action phá hủy bảng khi deploy production. Bảng tồn tại, UDT, index và dữ liệu phải được quản lý bằng kế hoạch DDL được review, thường qua migration tooling/quy trình DBA.

## 7. Quy trình nâng ứng dụng theo từng chặng

### Bước 1 — Chốt nguồn và trạng thái

Ghi nguyên bộ hiện trạng: image, commit, lockfile/SBOM, Boot BOM, Driver, JDK, server versions, CQL schema hash, cấu hình consistency, timeout, TLS và feature flags. Đọc release notes tất cả phiên bản trung gian nếu nhảy qua nhiều nhánh.

### Bước 2 — Chọn một bộ dependency mục tiêu

Ví dụ từ Boot 3.5.x → Boot 4.0.x:

~~~text
Baseline: Boot 3.5.x -> Data Cassandra 4.5.x -> Driver managed by Boot
Target:   Boot 4.0.x -> Data Cassandra 5.0.x -> Driver managed by Boot
Server:   Giữ nguyên phiên bản Cassandra hiện có trong pha nâng ứng dụng
JDK:      Chọn bản được cả Boot và môi trường build hỗ trợ
~~~

Giữ Cassandra server ổn định ở pha này làm giảm số nguyên nhân nếu test fail. Đổi Boot + server + schema trong một lần có thể làm root cause khó xác định.

### Bước 3 — Sửa lỗi build và API

Nâng Boot plugin/parent/BOM; đồng bộ thư viện ngoài Boot, sửa import/deprecation, test annotations, property, converter, custom Driver options và Spring bean configuration. Kiểm tra dependency tree sau resolve.

### Bước 4 — Chạy contract test trên Cassandra version hiện tại

Test entity mapping, CQL, repository/template, paging, consistency, TLS và lỗi timeout. Dùng **bản dữ liệu cũ** lẫn bản dữ liệu ghi bởi code mới để phát hiện thay đổi serialization.

### Bước 5 — Deploy canary/rolling

Đưa một phần traffic nhỏ vào ứng dụng mới trên Cassandra server **chưa nâng**. Quan sát p95/p99, tỷ lệ lỗi, retry, Driver session, read/write consistency, kết quả nghiệp vụ và số liệu so sánh với phiên bản cũ.

### Bước 6 — Hoàn tất chuyển đổi và ổn định

Tăng canary từng bước, có điều kiện dừng/rollback dựa trên SLO và đối soát dữ liệu. Sau khi ổn định mới xem xét nâng server Cassandra hoặc thay schema bằng dự án con tương ứng.

~~~mermaid
flowchart TD
    A["Baseline và ma trận version"] --> B["Nâng BOM + sửa API/config"]
    B --> C["Build + contract tests trên Cassandra cũ"]
    C --> D{"Tests PASS?"}
    D -->|"Không"| E["Sửa incompatibility, không deploy"]
    E --> C
    D -->|"Có"| F["Canary ứng dụng mới"]
    F --> G{"SLO và data contract PASS?"}
    G -->|"Không"| H["Rollback ứng dụng, điều tra"]
    G -->|"Có"| I["Rolling deploy ứng dụng"]
    I --> J["Ổn định + ghi baseline mới"]
~~~

## 8. Nâng Cassandra server: một kế hoạch khác với nâng ứng dụng

Cassandra server là hệ thống phân tán: **rolling upgrade** nghĩa là thay phiên bản các node theo thứ tự được hướng dẫn, trong khi cluster vẫn phục vụ tùy theo topology/replication/consistency. Thao tác này phải tuân thủ **đường nâng cấp server được Apache Cassandra hỗ trợ**, không suy từ việc Java Driver kết nối thành công.

### 8.1. Tiền kiểm trước khi nâng node

Kiểm tra tối thiểu:

| Hạng mục | Cần xác minh | Vì sao |
|---|---|---|
| Đường nâng chính thức | Bản nguồn → bản đích có hỗ trợ upgrade trực tiếp/rolling không? | Có thể cần đi qua bản trung gian |
| Health/quorum | Node sống, RF, CL, replication và topology | Không nên nâng node khi cluster đang mất quá nhiều replica |
| Repair và dữ liệu | Tình trạng repair, streaming, pending compactions, disk | Hạn chế rủi ro dữ liệu không nhất quán |
| Backup | Snapshot/backup **đã kiểm thử restore**, version metadata | Rollback node/server có thể không đơn giản |
| Disk và memory | Headroom cho SSTable/compaction/upgrade | Chuyển định dạng có thể tăng nhu cầu tài nguyên |
| Security | TLS, auth, RBAC, keyspace/system tables | Các node không gặp lỗi handshake/permission |
| Monitoring | p99, read/write latency, dropped messages, timeout, pending tasks | Có baseline để phát hiện regression |
| Client matrix | Driver, CQL features, protocol negotiation | App phải làm việc với trạng thái mixed-version được hỗ trợ |

Lưu từng phiên bản node và **trạng thái Cassandra thực tế** qua hệ thống quản trị phù hợp; backup không được coi là đã an toàn nếu chưa có lần phục hồi kiểm thử.

### 8.2. Mixed-version cluster và giao thức

Trong giai đoạn rolling upgrade, cluster có thể tồn tại các node **phiên bản cũ và mới**. Nếu tài liệu Cassandra cho phép trạng thái này, ứng dụng cần chịu được sự khác biệt tạm thời trong cách node xử lý request. Java Driver 4.x có khả năng **thương lượng native protocol** và xử lý nhiều node; tuy nhiên, bạn vẫn phải kiểm tra:

- Bản cũ/mới có được phép cùng tồn tại trong upgrade window không?
- Các schema/type/index mới có được hỗ trợ trong khi còn node cũ không?
- CQL được ứng dụng gửi có dùng tính năng chỉ có ở bản Cassandra mới không?
- Driver có chọn đúng local DC, auth/TLS và mức consistency không?
- Latency/read/write timeout và retry thay đổi thế nào khi node tuần tự rời/vào cluster?

**Nguyên tắc thực tế:** Không bật tính năng CQL/schema mới đòi hỏi toàn bộ cluster đã nâng xong khi còn node cũ chưa hiểu tính năng ấy.

### 8.3. Khung runbook rolling upgrade

Các bước dưới đây là **khung kiểm soát**, không phải hướng dẫn lệnh vận hành áp dụng y nguyên cho mọi nhánh Cassandra:

1. Xác nhận tài liệu chính thức của đường nâng, cửa sổ bảo trì và khả năng chịu lỗi.
2. Sao lưu/kiểm tra phục hồi; chụp baseline; xác nhận cluster khỏe và đủ dung lượng.
3. Nâng một node hoặc một nhóm nhỏ **theo chiến lược đã được hỗ trợ**, tránh ảnh hưởng đồng thời đủ replica làm mất quorum.
4. Chờ node phục vụ bình thường và tiến trình bắt buộc hoàn thành; xác nhận consistency/latency sau thay đổi.
5. Quan sát metric từ ứng dụng Spring Data, Java Driver và node; dừng khi vượt ngưỡng lỗi/p99.
6. Lặp cho node tiếp theo, chỉ khi điều kiện kiểm tra của node trước PASS.
7. Sau toàn bộ cluster đã chuyển đổi, hoàn thành các bước schema/SSTable/operational housekeeping **được release notes yêu cầu**, rồi chạy lại soak test.

Một số quá trình upgrade có liên quan **định dạng SSTable**. Công cụ `nodetool upgradesstables`/`sstableupgrade` có mục đích riêng và yêu cầu vận hành riêng; không tự chạy chúng theo thói quen hoặc khi chưa kiểm tra điều kiện, tài nguyên, trạng thái cluster và tài liệu bản đích. Tham khảo [Cassandra 5.0 — nodetool upgradesstables](https://cassandra.apache.org/doc/latest/cassandra/managing/tools/nodetool/upgradesstables.html).

### 8.4. Rollback server có thể khó hơn rollback ứng dụng

Một image ứng dụng cũ thường có thể deploy trở lại **nếu schema và dữ liệu vẫn tương thích**. Cassandra node đã nâng, ghi dữ liệu mới hoặc chuyển SSTable/schema có thể **không thể đơn giản hạ version bằng cách đổi binary**. Có trường hợp phải khôi phục từ backup hoặc triển khai cluster mới rồi chuyển dữ liệu. Vì vậy:

- Dùng quy trình **stop/go** trước khi nâng node kế tiếp.
- Không mặc định rollback node là “undo package update”.
- Đặt **điểm không thể đảo ngược** (nếu có) trong kế hoạch; sau điểm đó ưu tiên roll-forward có kiểm soát hoặc restore theo runbook.
- Thử restore và recovery time trước khi nâng production.

## 9. Schema evolution theo nguyên tắc expand → migrate → contract

Một ứng dụng có thể nâng Spring Boot thành công mà vẫn phải thay thiết kế bảng để đáp ứng truy vấn mới. Cassandra không khuyến khích dùng cùng một bảng chung cho mọi query: partition key quyết định phân bố dữ liệu; thay khóa phân vùng thường là **tạo bảng mới và chuyển dữ liệu**.

### 9.1. Thay đổi cộng thêm: thêm cột

Giả sử bảng cũ:

~~~sql
CREATE TABLE orders_by_id (
    order_id uuid PRIMARY KEY,
    customer_id uuid,
    status text
);
~~~

Ứng dụng mới cần lưu `note`:

~~~sql
ALTER TABLE orders_by_id ADD note text;
~~~

Lộ trình an toàn:

1. **Expand:** thêm cột mới theo DDL được kiểm soát; code cũ tiếp tục hoạt động.
2. **Deploy code mới:** entity thêm trường `@Column("note")`; logic đọc chấp nhận `null` ở dữ liệu cũ.
3. **Backfill nếu cần:** tạo giá trị cho record cũ một cách có giới hạn và idempotent.
4. **Contract:** chỉ loại bỏ nhánh cũ khi mọi client đã dùng hợp đồng mới.

Trong Java, cần chú ý kiểu nullable của các cột mới: ánh xạ cột chưa có giá trị vào primitive như `int` có thể tạo khác biệt so với `Integer` nullable. Kiểm thử entity đọc row cũ là bắt buộc.

### 9.2. Thay partition key: tạo bảng mới

Bảng theo `order_id` không phục vụ hiệu quả việc “tìm đơn theo khách và tháng”. Một read model khác:

~~~sql
CREATE TABLE orders_by_customer_month_v2 (
    customer_id uuid,
    order_month text,
    created_at timestamp,
    order_id uuid,
    status text,
    PRIMARY KEY ((customer_id, order_month), created_at, order_id)
) WITH CLUSTERING ORDER BY (created_at DESC, order_id DESC);
~~~

Đừng cố:

~~~sql
-- Không phải cách thay partition key hợp lệ:
-- ALTER TABLE orders_by_id ALTER PRIMARY KEY (...);
~~~

Cassandra không hỗ trợ đổi partition key của một bảng theo cách đó. Cần có **bảng mới**, code ghi/đọc thích hợp, backfill và kiểm chứng kết quả. Một hệ thống dùng Spring Data có thể khai báo hai entity/table và hai repository hoặc dùng `CassandraTemplate` rõ bảng đích trong giai đoạn chuyển tiếp.

### 9.3. Dual-write/backfill không tự mang lại transaction toàn cục

~~~mermaid
flowchart TD
    A["Command thay đổi đơn"] --> B["Service phiên bản chuyển đổi"]
    B --> C["Bảng cũ: orders_by_id"]
    B --> D["Bảng mới: orders_by_customer_month_v2"]
    E["Backfill / CDC có checkpoint"] --> D
    D --> F["Đối soát counts + keys + payload"]
    C --> F
    F --> G{"Đủ và đúng?"}
    G -->|"Chưa"| H["Sửa/replay có kiểm soát"]
    H --> F
    G -->|"Rồi"| I["Chuyển read path sang v2"]
~~~

**Hai lời ghi vào hai partition/bảng không mặc nhiên tạo một transaction ACID toàn cục hoặc khả năng đọc nhất quán tức thời.** Khi một ghi thành công và ghi còn lại thất bại, cần cơ chế retry idempotent, outbox/event log, CDC hoặc reconciliation thích hợp với kiến trúc. Cẩn thận với:

- Mutation có TTL khác nhau ở bảng cũ/mới.
- Delete/tombstone không được replay vào bảng mới.
- Ghi đến từ nhiều phiên bản service trong cùng thời gian deploy.
- Write timestamp và thứ tự cập nhật: dữ liệu backfill cũ không được ghi đè bản cập nhật mới một cách ngoài ý muốn.
- Retry sau timeout: timeout không chứng minh mutation chưa áp dụng; cần xử lý idempotency.

Khi đọc từ bảng mới, kiểm thử **thứ tự clustering, partition bucket, paging**, độ đầy đủ của dữ liệu và consistency của các request thực tế. Chỉ xóa bảng cũ khi đủ bằng chứng và đã qua cửa sổ rollback.

### 9.4. Giữ hợp đồng API trong quá trình nâng schema

Ví dụ kết quả API đơn hàng có thể cần duy trì:

~~~json
{
  "orderId": "00000000-0000-0000-0000-000000000001",
  "status": "PAID",
  "note": null
}
~~~

Khi dữ liệu cũ chưa có `note`, contract có thể quy định trường là `null` hoặc bỏ qua trường, nhưng **phải nhất quán** giữa code cũ và mới trong giai đoạn triển khai. Đừng để migration schema vô tình biến “bản ghi không tồn tại” thành “trường tùy chọn chưa được nạp” hoặc ngược lại.

## 10. Kiểm thử ma trận qua Testcontainers và cluster đại diện

### 10.1. Tạo các job ma trận độc lập

Một bảng CI hữu ích (minh họa):

| Job | Client app | Cassandra | Mục tiêu |
|---|---|---|---|
| Baseline | Build cũ | Server cũ | Ghi bằng chứng hành vi trước khi đổi |
| Target/current server | Build mới | Server cũ | Bảo đảm ứng dụng có thể rollout trước server |
| Target/target server | Build mới | Server mục tiêu | Bảo đảm hoạt động sau nâng server |
| Old app/new schema | Build cũ | Server với schema expand | Kiểm tra mixed app versions |
| New app/old data | Build mới | Dữ liệu cũ + schema mới | Kiểm tra backward data compatibility |
| Rolling state | Build mới và cũ | Cluster mixed version **nếu hỗ trợ** | Kiểm tra trạng thái chuyển tiếp |

Với job CRUD đơn giản, một Cassandra Testcontainers có thể đủ để xác minh entity/repository/`CassandraTemplate`. Nhưng để kiểm tra **RF=3, `LOCAL_QUORUM`, mixed-version cluster, topology và p99**, cần môi trường nhiều node đáp ứng cấu hình production; Testcontainers đơn node **không chứng minh** điều đó.

### 10.2. Ví dụ smoke test connection + CQL bằng Spring

Mẫu Java dưới dùng Spring Boot test, Java Driver 4.x và JUnit 5. Chạy với cấu hình Cassandra test được cấp động bên ngoài test (Testcontainers, test environment hoặc CI). Test không hard-code user/password hoặc endpoint production:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.Row;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.cassandra.core.CassandraTemplate;

@SpringBootTest
class CassandraUpgradeSmokeTest {
    @Autowired CqlSession session;
    @Autowired CassandraTemplate template;

    @Test
    void cqlSessionCanReadServerMetadata() {
        Row row = session.execute(
                "SELECT release_version, data_center FROM system.local").one();
        assertThat(row).isNotNull();
        assertThat(row.getString("release_version")).isNotBlank();
        assertThat(row.getString("data_center")).isNotBlank();
        assertThat(template).isNotNull();
    }
}
~~~

Kiểm tra bean được tạo và `system.local` đọc được chỉ là **smoke test**. Nó chưa chứng minh business CQL, schema mapping, paging/consistency hoặc hiệu năng hoạt động đúng. Hãy bổ sung CRUD round-trip và kiểm tra kết quả trên **cùng fixture** ở tất cả ô của ma trận.

### 10.3. Contract tests tối thiểu cho Spring Data Cassandra

| Nhóm | Tình huống cần có | Assertion |
|---|---|---|
| Mapping | Đọc row cũ; insert/update row mới; nullable/UDT/date | Giá trị đúng, không mất cột, không lỗi codec |
| Repository | `findById`, derived/`@Query`, custom repository | Trả đúng record, số record, thứ tự |
| Template/CQL | `CassandraTemplate`, `CqlTemplate`, prepared CQL | Bind đúng param và cột/table |
| Partition key | Partition đơn/tổng hợp, clustering order | Query hợp lệ, không full scan ngoài ý muốn |
| Consistency | `LOCAL_ONE`/`LOCAL_QUORUM` theo yêu cầu | Response và lỗi hợp đồng ở topology thích hợp |
| Paging | Page đầu và page sau, page size, thứ tự | Không mất/trùng row; xử lý state đúng |
| Error handling | Read/write timeout, unavailable, auth/TLS lỗi | Cause không bị nuốt, retry đúng điều kiện |
| Migration | Code cũ/new + data cũ/new + schema expand | Tương thích trong giai đoạn mixed |
| Performance | p95/p99, throughput, retry count, GC | Không vượt regression budget |

**Paging state không nên được xem là token dùng được vô thời hạn qua mọi lần thay đổi query, schema và Driver.** Hợp đồng API phải xác định phiên bản/cách hết hạn hoặc tạo lại cursor khi thay đổi không tương thích. Test phải trả lời điều gì xảy ra với một cursor cũ sau khi deploy.

### 10.4. So sánh performance trước và sau

Ở cùng workload và dữ liệu đại diện, ghi:

~~~text
Build/version matrix ID: ...
Cluster topology/RF/CL: ...
Workload mix + hot keys: ...
Read p50 / p95 / p99: ...
Write p50 / p95 / p99: ...
Offered RPS / achieved RPS: ...
Error / timeout / retry rate: ...
Driver in-flight / node pool: ...
Cassandra pending tasks / compaction / GC: ...
Schema hash and test dataset: ...
~~~

Không kết luận bản mới “tốt hơn” chỉ vì latency của request thành công giảm trong khi nhiều request đã timeout. Đo **cả tỷ lệ lỗi, retry và p99**; giữ cùng RF/CL, page size, partition distribution, network và dữ liệu khi so sánh.

## 11. Triển khai có canary và điểm dừng

Một đợt nâng ứng dụng và Cassandra nên có **tiêu chí go/no-go đo được**. Ví dụ giả định:

| Giai đoạn | Điều kiện tiếp tục | Khi không đạt |
|---|---|---|
| Build + tests | Compile, unit, integration, contract PASS | Sửa dependency/API |
| Canary 5% | Không tăng lỗi auth/TLS/CQL; p99 trong ngân sách | Dừng rollout và quay image |
| Canary 25% | So khớp dữ liệu, retry và latency ổn định | Giảm traffic, điều tra |
| Deploy toàn ứng dụng | Hệ thống cũ/mới cùng đọc dữ liệu được | Rollback app nếu schema còn tương thích |
| Bắt đầu server upgrade | Cluster khỏe, backup được kiểm tra, client PASS | Hoãn upgrade node |
| Sau mỗi node | Replica/CL phục vụ, SLO ổn | Dừng, xử lý theo runbook |
| Kết thúc schema migration | Backfill/reconciliation đạt ngưỡng | Tiếp tục dual-read/dual-write; chưa xóa bảng cũ |

Các tỷ lệ và ngưỡng ở đây chỉ là **mẫu quy trình**, không phải SLO chung. Mỗi hệ thống cần định nghĩa p99, error budget, thời gian ổn định và người có quyền dừng rollout.

### 11.1. Phân biệt rollback và roll-forward

| Phạm vi thay đổi | Khả năng trở lại trạng thái cũ | Điều kiện |
|---|---|---|
| Boot/Spring Data/Driver, không đổi schema | Thường dễ hơn: redeploy image cũ | Driver cũ vẫn tương thích server và dữ liệu |
| Thêm cột nullable | Thường vẫn hỗ trợ code cũ | Code cũ không giả định cột không tồn tại theo cách gây lỗi |
| Bảng mới + dual write | Có thể chuyển read path về bảng cũ khi còn đồng bộ | Dữ liệu cũ vẫn đầy đủ; có đối soát |
| Xóa/đổi cột không tương thích | Khó hoặc không khả thi bằng image rollback | Cần kế hoạch phục hồi dữ liệu/schema |
| Cassandra server + SSTable/schema thay đổi | Phụ thuộc đường nâng và định dạng dữ liệu | Runbook chính thức/restore; không tự downgrade binary |

Không gọi việc “đổi lại dependency version” là một kế hoạch rollback hoàn chỉnh nếu dữ liệu hoặc schema đã biến đổi.

## 12. Các lỗi nâng cấp thường gặp

| Triệu chứng | Nguồn cần kiểm tra trước | Hướng xử lý |
|---|---|---|
| `NoSuchMethodError` khi start | Spring/Driver jar conflict trong runtimeClasspath | Kiểm tra BOM và dependencyInsight/tree |
| `ClassNotFoundException` cho `com.datastax.driver.core.*` | Mã còn dùng API Driver 3.x | Chuyển sang Driver 4 `CqlSession` và API tương ứng |
| Session không kết nối node | Endpoint, local DC, TLS/auth, protocol | Xem Driver cause theo node; so server/Driver config |
| `InvalidQueryException` sau nâng | CQL, schema/keyspace, tính năng mới | Kiểm tra DDL và query shape; không retry lỗi schema |
| Entity thiếu cột hoặc sai kiểu | Mapping/codec/UDT/nullable | So row cũ mới, converter, annotation |
| Bảng có thêm cột nhưng code cũ lỗi | Contract không thật sự backward-compatible | Điều chỉnh expand step và code đọc |
| Paging trả thiếu/trùng row | Query order, cursor/page state, dữ liệu thay đổi | Kiểm tra paging contract, clustering và consistency |
| p99 tăng mạnh sau nâng Driver | Retry/default timeout, pool, protocol, workload, hot keys | So metric Driver và server dưới cùng tải |
| `UnavailableException` khi nâng node | RF/CL, replica down, thiếu capacity | Dừng upgrade node; kiểm tra quorum/topology |
| Chạy lại app cũ vẫn lỗi | Server/schema đã đổi không tương thích | Dùng runbook dữ liệu/server, không chỉ image rollback |

## 13. Ví dụ end-to-end: nâng ứng dụng rồi Cassandra

Giả sử dịch vụ đơn hàng đang chạy một nhánh Spring Boot 3.5 và Cassandra 4.1, sau đó hướng đến Boot 4.0 và Cassandra 5.0. Đây là **kịch bản minh họa**, không phải đường nâng mặc định hoặc khẳng định mọi phiên bản patch có thể nâng trực tiếp:

**Pha A — Đổi ứng dụng, giữ server Cassandra 4.1:**

1. Chốt BOM 3.5.x hiện tại và 4.0.x đích, đối chiếu Spring Data/Driver trên dependency tree.
2. Nâng Boot, sửa code/config và kiểm thử entity/repository/template/CQL.
3. Chạy contract test trên Cassandra 4.1, gồm paging và TLS/auth.
4. Canary, đo p99/timeout và kiểm tra dữ liệu, sau đó rolling deploy ứng dụng.

**Pha B — Nâng Cassandra server theo đường hỗ trợ:**

1. Xác nhận release notes của cặp server 4.1 → 5.0, JDK node và mixed-version requirements.
2. Backup/restore drill, kiểm tra repair/replica/CL, chọn lịch nâng từng node.
3. Khi mỗi node thay phiên bản, quan sát Driver, consistency, timeout, CQL và node health.
4. Kết thúc quá trình, chạy contract, dữ liệu và soak benchmark trên Cassandra 5.0.

**Pha C — Triển khai tính năng schema mới (nếu cần):**

1. Thêm cột hoặc tạo bảng read model mới, giữ code cũ còn chạy được.
2. Backfill và dual-write được kiểm soát, đối soát dữ liệu.
3. Chuyển read path và theo dõi kết quả/hiệu năng.
4. Chỉ xóa nhánh dữ liệu cũ khi đã hết thời gian rollback và đủ điều kiện.

Việc **tách ba pha** giúp hạn chế nguyên nhân chồng chéo. Nếu tổ chức buộc triển khai gộp do ràng buộc kinh doanh, phải mở rộng ma trận để kiểm thử mọi trạng thái trung gian cần tồn tại và xác định điểm không thể quay lại.

## 14. Câu hỏi tình huống tự kiểm tra

**Tình huống A — Mismatch dependency.** `pom.xml` dùng Boot 4.0.x nhưng vẫn pin Spring Data Cassandra 4.5.x và kéo Driver cũ để “giữ ổn định”. Dự án compile được. Có thể triển khai ngay?

**Gợi ý:** Không. Đọc dependency tree và release notes; kiểm tra binary/API Spring Framework, Spring Data, Driver, sau đó chạy ma trận contract. Ưu tiên bộ dependency do Boot BOM quản lý trừ khi có override được kiểm chứng.

**Tình huống B — Thương lượng protocol.** Driver mới khởi tạo `CqlSession` thành công với Cassandra 5.0. Vậy mọi feature Cassandra 5.0 đã tương thích Spring Data?

**Gợi ý:** Không. Handshake chỉ chứng minh khả năng giao tiếp cơ bản. Cần kiểm tra CQL type/feature, codec, schema, mapping và workload thực.

**Tình huống C — Rollback sau DDL.** Ứng dụng mới đã ngừng ghi bảng cũ, xóa bảng cũ và chuyển sang khóa phân vùng mới. Canary lỗi. Có thể chỉ redeploy image cũ?

**Gợi ý:** Không có bảo đảm. Image cũ cần bảng cũ và dữ liệu nhất quán. Cần kế hoạch restore/replay hoặc giữ bảng cũ trong giai đoạn expand-migrate trước khi contract.

**Tình huống D — Server rolling upgrade.** Cluster RF=3, ứng dụng ghi `LOCAL_QUORUM`; hai replica của một tập partition đồng thời không sẵn sàng. Có nên tiếp tục nâng node khác vì Driver vẫn kết nối được vài node?

**Gợi ý:** Không. Quorum và availability phải được đánh giá theo replica thực của partition. Dừng và khôi phục health trước khi tiếp tục.

**Tình huống E — Paging.** Client giữ paging state tạo bởi truy vấn cũ rồi gửi sau khi code/schema/query thay đổi. Có thể chắc chắn dùng tiếp?

**Gợi ý:** Không. Paging state phụ thuộc query context và Driver/Cassandra; API cần hợp đồng cursor, version/expiry và test tương thích.

**Tình huống F — “Nhanh hơn” nhưng lỗi nhiều hơn.** Sau nâng, p99 request thành công giảm 20% nhưng timeout tăng từ 0,1% lên 3%. Nên chấp nhận?

**Gợi ý:** Không chỉ nhìn p99 của request thành công. So SLO/error budget, achieved throughput, retry, Driver và node metrics; kiểm tra request bị timeout đã bị loại khỏi mẫu đo latency hay chưa.

## 15. Checklist nâng cấp theo ma trận

- [ ] Có inventory version: Boot, Spring Framework/Data, Driver, JDK, Cassandra node, schema.
- [ ] Đã lấy dependency mapping từ **BOM phiên bản cụ thể**, không tự đoán qua tên major.
- [ ] Đã kiểm tra artifact groupId/namespace đúng Driver 4.x và không còn dependency 3.x.
- [ ] Có ma trận client × Cassandra server × JDK × tính năng CQL thực sự sử dụng.
- [ ] Release notes/migration guides của từng chặng đã được đọc, gồm phiên bản trung gian.
- [ ] Cấu hình contact points, local DC, keyspace, auth/TLS, timeout, retry được kiểm tra sau nâng.
- [ ] Entity mapping, partition/clustering keys, converters, repository và template có contract tests.
- [ ] Dữ liệu cũ và mới, paging state, consistency và reactive behavior (nếu dùng) được kiểm tra.
- [ ] Đã thử canary/mixed application, đối soát dữ liệu và đặt điều kiện go/no-go.
- [ ] Cassandra upgrade có backup/restore drill, RF/CL health và runbook chính thức.
- [ ] Schema dùng expand → migrate → contract; không xóa bảng/cột trước khi hết cửa sổ rollback.
- [ ] Performance regression đo p95/p99, lỗi, retry, throughput và node metrics trên tải đại diện.
- [ ] Rollback/roll-forward có điểm không thể đảo ngược và người chịu trách nhiệm rõ ràng.
- [ ] Kết quả từng ô ma trận được lưu lại cùng version, dataset, commit và thời điểm chạy.

## 16. Tổng kết

Nâng **Spring Boot, Spring Data Cassandra, Java Driver và Apache Cassandra** là bài toán tương thích **nhiều lớp**. Boot BOM giúp chọn tập dependency Spring/Driver nhất quán; Driver native protocol quyết định khả năng giao tiếp với Cassandra; còn mapping entity, partition key, CQL, consistency và paging quyết định ứng dụng có tiếp tục trả dữ liệu đúng hay không.

Hãy **khóa một bộ version cụ thể, xác minh dependency tree, chạy ma trận client × server, nâng ứng dụng trước khi thay đổi cluster khi phù hợp, và tách migration schema thành các bước có đối soát**. Một kế hoạch hoàn chỉnh còn cần canary, khả năng quan sát p99/timeout/retry, backup được thử phục hồi và rollback đúng mức độ biến đổi dữ liệu.

## Tài liệu tham khảo

- [Spring Boot 3.5 — Managed Dependency Coordinates](https://docs.spring.io/spring-boot/3.5/appendix/dependency-versions/coordinates.html)
- [Spring Boot 4.0 — Managed Dependency Coordinates](https://docs.spring.io/spring-boot/4.0/appendix/dependency-versions/coordinates.html)
- [Spring Boot — Managed Dependency Coordinates](https://docs.spring.io/spring-boot/appendix/dependency-versions/coordinates.html)
- [Spring Boot — Upgrading](https://docs.spring.io/spring-boot/4.0/upgrading.html)
- [Spring Data Cassandra — Dependencies và BOM](https://docs.spring.io/spring-data/cassandra/reference/data-commons/3.5/dependencies.html)
- [Spring Data Cassandra — Migration Guides](https://docs.spring.io/spring-data/cassandra/reference/migration-guides.html)
- [Apache Cassandra Java Driver — Native Protocol](https://apache.github.io/cassandra-java-driver/4.19.0/core/native_protocol/)
- [Apache Cassandra Java Driver — Upgrade Guide](https://apache.github.io/cassandra-java-driver/4.19.0/upgrade-README/)
- [Apache Cassandra — Download và các nhánh release](https://cassandra.apache.org/_/download.html)
- [Apache Cassandra — New Features in 5.0](https://cassandra.apache.org/doc/stable/cassandra/new/)
- [Apache Cassandra — Operating Cassandra](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/index.html)
- [Apache Cassandra — upgradesstables](https://cassandra.apache.org/doc/latest/cassandra/managing/tools/nodetool/upgradesstables.html)
