# Đọc ma trận tương thích Spring Boot, Spring Data, client và server

Một ứng dụng Spring Data Elasticsearch có thể biên dịch thành công nhưng vẫn không chạy được với Elasticsearch server đang dùng. Ngược lại, ứng dụng có thể kết nối được nhưng một API, kiểu query, authentication mechanism hoặc tính năng mapping lại không tương thích. Nguyên nhân là phiên bản của ứng dụng không chỉ gồm một dependency: Spring Boot quản lý Spring Framework và Spring Data; Spring Data Elasticsearch chọn client/transport; client giao tiếp với Elasticsearch server; còn Java runtime, plugin và test environment cũng có giới hạn phiên bản riêng.

Đọc ma trận tương thích là cách xác định một **tổ hợp phiên bản được hỗ trợ**, thay vì chọn từng thành phần độc lập. Cần kiểm tra ít nhất bốn lớp:

1. **Spring Boot ↔ Spring Data release train**: các module Spring Data phải thuộc release train phù hợp với Boot.
2. **Spring Data Elasticsearch ↔ Elasticsearch Java client/transport**: module Spring Data cần đúng thế hệ client và dependency mà nó được xây dựng để sử dụng.
3. **Elasticsearch client ↔ Elasticsearch server**: REST API, protocol compatibility và feature support phải phù hợp.
4. **Java runtime và hệ sinh thái test/plugin**: JDK, Testcontainers, Elasticsearch plugins và build tooling cũng cần tương thích.

Không có một con số phiên bản duy nhất chứng minh toàn bộ stack tương thích. Cần đọc đúng tài liệu của từng lớp, kiểm tra dependency thực tế được resolve và chạy integration test trên server version mục tiêu.

## 1. Bốn lớp phiên bản cần đọc cùng nhau

Một stack có thể được hình dung như sau:

~~~mermaid
flowchart TD
    A["Application code"] --> B["Spring Boot"]
    B --> C["Spring Data release train"]
    C --> D["Spring Data Elasticsearch"]
    D --> E["Elasticsearch Java API Client / transport"]
    E --> F["Elasticsearch HTTP server"]
    B --> G["Java runtime"]
    F --> H["Elasticsearch plugins"]
    D --> I["Testcontainers / integration test"]
    I --> F
~~~

Mỗi mối quan hệ có một loại tương thích khác nhau:

| Cặp thành phần | Cần kiểm tra | Dấu hiệu không tương thích |
|---|---|---|
| Spring Boot và Spring Data | Boot BOM quản lý release train nào | Dependency convergence lỗi, NoSuchMethodError trong Spring |
| Spring Data và Spring Data Elasticsearch | Module thuộc release train nào | Module Spring Data lệch phiên bản, API không đồng bộ |
| Spring Data Elasticsearch và Java client | Client generation, version và transport | Class missing, method signature khác, client configuration không khớp |
| Java client và Elasticsearch server | Major version, REST compatibility, API/feature support | HTTP 400/406, API không tồn tại, request field không được hỗ trợ |
| Elasticsearch server và plugin | Plugin version tương thích server | Plugin không load hoặc node không khởi động |
| Spring Boot và JDK | Java baseline của Boot/framework/dependencies | UnsupportedClassVersionError, compiler/runtime mismatch |
| Testcontainers và server image | Image version, startup/security behavior | Test khác production, container không khởi động hoặc test sai protocol |

Không nên chỉ so sánh số major của Spring Boot và Elasticsearch rồi kết luận. Hai dự án có lịch phát hành độc lập; phiên bản 3.x của Spring Boot không có nghĩa phải dùng Elasticsearch 3.x.

## 2. Bắt đầu từ Spring Boot BOM

Trong ứng dụng Spring Boot, parent POM hoặc dependency management BOM thường là điểm bắt đầu để xác định các phiên bản Spring Framework và Spring Data được quản lý.

Ví dụ Maven:

~~~xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.x.y</version>
    <relativePath/>
</parent>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-elasticsearch</artifactId>
    </dependency>
</dependencies>
~~~

3.x.y chỉ là placeholder để minh họa cấu trúc. Dự án thật phải dùng một phiên bản Spring Boot đã được chọn từ ma trận chính thức và tương thích với JDK/build tool của dự án.

Nếu không dùng spring-boot-starter-parent, có thể import BOM:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>3.x.y</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Khi dependency được Boot BOM quản lý, thường không cần khai báo version riêng cho starter.

Điều cần đọc:

- Boot version đang dùng.
- Spring Framework version do Boot quản lý.
- Spring Data release train mà Boot chọn.
- Version của spring-data-elasticsearch.
- Version các client/transport transitive.
- Java version tối thiểu và build plugin version.

BOM là tập quy tắc version management. Nó không chứng minh Elasticsearch server ở bất kỳ version nào cũng được hỗ trợ; đó là một bước kiểm tra riêng.

## 3. Spring Data release train là gì?

Spring Data phát hành các module liên quan theo một release train. Các module như Commons, Elasticsearch, JPA, MongoDB và Redis có thể cần phối hợp cùng release train để tránh API nội bộ lệch nhau.

Ví dụ một dự án có thể dùng:

- spring-data-commons
- spring-data-elasticsearch
- Các module Spring Data khác nếu ứng dụng cần.

Không nên nâng riêng spring-data-elasticsearch lên một version tùy ý trong khi spring-data-commons vẫn do Boot quản lý ở release train khác.

Một số dấu hiệu dependency Spring Data bị lệch:

- NoSuchMethodError trong package org.springframework.data.
- Class được compile ở một version nhưng runtime nạp class từ version khác.
- Repository configuration hoạt động khác nhau giữa IDE và CI.
- Dependency tree có hai version của Spring Data Commons.
- Test context lỗi khi tạo repository proxy.

Nếu cần version mới hơn Boot BOM đang quản lý, hãy xác định release train Spring Data tương ứng và kiểm tra ma trận Spring Boot trước khi override. Nâng đồng bộ các module liên quan và kiểm tra dependency convergence; không chỉ đổi một dòng version.

## 4. Thế hệ client của Spring Data Elasticsearch

Một ranh giới quan trọng trong lịch sử Spring Data Elasticsearch là việc chuyển từ Elasticsearch High Level REST Client sang Elasticsearch Java API Client.

Ở mức định hướng theo major family:

| Dòng Spring Data Elasticsearch | Client thường gắn với dòng đó | Ý nghĩa khi nâng cấp |
|---|---|---|
| 4.x | Elasticsearch High Level REST Client (HLRC) | Code thường dùng API client cũ và kiểu query cũ |
| 5.x | Elasticsearch Java API Client | Chuyển sang client mới, query model và cấu hình transport thay đổi |

Đây là định hướng kiến trúc theo major family, không phải bảng patch-level được bảo đảm cho mọi combination. Hãy xem tài liệu của đúng minor/patch Spring Data Elasticsearch và dependency tree của dự án.

Việc chuyển từ HLRC sang Java API Client không phải chỉ đổi artifact:

- Các class request/response khác nhau.
- Query builder và kiểu dữ liệu query khác nhau.
- Client/transport configuration khác nhau.
- Cách cấu hình authentication, SSL và HTTP headers có thể khác.
- Code custom repository, converter hoặc callback có thể cần sửa.
- Các API đã deprecated/removed có thể không còn.

Nếu dự án vẫn dùng HLRC, không thêm Java API Client mới vào chỉ để dùng một ví dụ code mà không xác định Spring Data version có hỗ trợ cách kết hợp đó hay không.

## 5. Spring Boot và Spring Data Elasticsearch: đọc quan hệ theo release train

Ma trận Spring Boot thường cho biết Boot version quản lý một Spring Data release train nào. Release train đó lại xác định version của spring-data-elasticsearch.

Có thể đọc theo chiều:

~~~text
Spring Boot version
       |
       v
Spring Boot dependency management
       |
       v
Spring Data release train
       |
       v
spring-data-elasticsearch version
       |
       v
Supported client generation and dependency versions
~~~

Một định hướng lịch sử thường gặp:

| Nhóm ứng dụng | Spring Data Elasticsearch | Client generation | Lưu ý lớn |
|---|---|---|---|
| Ứng dụng Spring Boot 2.x | Thường thuộc Spring Data Elasticsearch 4.x | HLRC | Hệ sinh thái Spring Framework 5 và javax APIs |
| Ứng dụng Spring Boot 3.x | Thường thuộc Spring Data Elasticsearch 5.x | Elasticsearch Java API Client | Spring Framework 6, Java 17 baseline và Jakarta namespace |

Bảng này chỉ giúp nhận diện thế hệ. Nó không thay thế ma trận release cụ thể. Không phải mọi patch của Boot 2/3 đều dùng cùng một patch Spring Data Elasticsearch; hãy lấy version được Boot BOM quản lý cho đúng release.

Khi nâng Boot 2 lên Boot 3, ngoài Elasticsearch còn có thay đổi javax.* sang jakarta.*, Java baseline, Spring Security và các thư viện khác. Nếu chỉ kiểm tra Elasticsearch client, ứng dụng vẫn có thể không build hoặc không khởi động.

## 6. Đọc quan hệ Elasticsearch Java client và server

Elasticsearch Java API Client là client HTTP được sinh theo API Elasticsearch. Version của client có quan hệ chặt với dòng API server, nhưng không nhất thiết phải trùng patch với server.

Khi đọc tài liệu client/server, phân biệt:

- **Same-major compatibility**: client và server cùng major, là vùng tương thích thông thường cần ưu tiên.
- **Forward compatibility**: client cũ có thể giao tiếp với server minor mới hơn trong cùng major theo chính sách tương thích được công bố.
- **Backward compatibility**: client mới giao tiếp với server cũ hơn; không được mặc định là được hỗ trợ.
- **Cross-major compatibility**: chỉ dùng nếu tài liệu chính thức chỉ rõ cách hỗ trợ, chẳng hạn REST API compatibility mode cho cặp version cụ thể.
- **Feature compatibility**: request có thể được truyền thành công nhưng server cũ không hỗ trợ tính năng mới.

Không suy ra tương thích chỉ từ việc request trả HTTP 200. Một số field mới, query option hoặc response property có thể khác giữa các version.

### Ví dụ cách đọc

Giả sử ứng dụng dùng Java API Client dòng 8 và server cũng thuộc dòng 8:

- Đây là vùng cùng major nên là điểm khởi đầu hợp lý.
- Cần kiểm tra client minor có hỗ trợ server minor mục tiêu theo tài liệu Elastic.
- Nếu ứng dụng dùng API vừa được thêm ở server minor mới, client model cũng phải có API tương ứng.
- Nếu server được nâng minor nhưng client giữ nguyên, cần kiểm tra forward compatibility và behavior của tính năng đang dùng.

Nếu ứng dụng dùng client major mới hơn server major, đừng giả định nó hoạt động chỉ vì HTTP là giao thức REST. Kiểm tra REST compatibility mode, media type/version header và giới hạn API theo tài liệu của cặp version cụ thể.

## 7. Phân biệt protocol compatibility và feature compatibility

Hai khái niệm này rất dễ bị nhầm.

**Protocol compatibility** trả lời liệu client có thể gửi request và hiểu response qua HTTP/API hay không.

**Feature compatibility** trả lời server có hỗ trợ hành vi mà ứng dụng yêu cầu hay không.

Ví dụ:

- Client có thể kết nối và gọi _search.
- Nhưng server cũ không biết một query option mới.
- Kết nối và authentication thành công.
- Request cụ thể vẫn bị HTTP 400 hoặc query execution error.

Một ví dụ khác là Java client mới có model cho field response mới. Khi gọi server cũ, field đó có thể không xuất hiện; code không được giả định luôn có giá trị.

Vì vậy, ma trận cần được đọc theo từng feature được ứng dụng sử dụng, không chỉ theo client/server major.

## 8. Elasticsearch REST API compatibility mode

Elasticsearch có cơ chế REST API compatibility cho một số chuyển đổi major version. Mục đích là giúp client của major trước tiếp tục hoạt động trong một khoảng chuyển tiếp đã được tài liệu hóa.

Tuy nhiên:

- Không phải mọi API đều có thể dùng compatibility mode.
- Không phải mọi tính năng mới đều có thể dùng với client cũ.
- Cần cấu hình media type/compatibility header đúng theo version.
- Chỉ nên dựa vào mode được Elastic hỗ trợ cho cặp major cụ thể.
- Đây không phải cam kết rằng mọi client library và Spring Data version đều tương thích hoàn toàn.

Nếu Spring Data Elasticsearch không expose cấu hình compatibility cần thiết hoặc client không hỗ trợ request headers tương ứng, việc tự thêm header ở một nơi không đủ để đảm bảo cả stack tương thích.

Ưu tiên nâng client/Spring Data theo lộ trình hỗ trợ. Dùng compatibility mode như cầu nối có thời hạn, có test và kế hoạch loại bỏ.

## 9. Đừng nhầm version của Elasticsearch server với version của Java client

Ví dụ dependency:

~~~xml
<dependency>
    <groupId>co.elastic.clients</groupId>
    <artifactId>elasticsearch-java</artifactId>
</dependency>
~~~

Artifact này là Java API Client. Server Elasticsearch là một dịch vụ chạy độc lập, có version được xác định trong cluster/container/managed service.

Ngoài ra có thể có HTTP transport dependency, JSON mapper và các thư viện hỗ trợ. Chỉ nhìn version của elasticsearch-java không cho biết server đang chạy version nào.

Cần ghi nhận cả hai:

| Thành phần | Nguồn xác định version |
|---|---|
| Spring Boot | Parent/BOM/build file |
| Spring Data Elasticsearch | Dependency management/Resolved dependency |
| Elasticsearch Java API Client | Dependency tree |
| HTTP transport | Dependency tree |
| Elasticsearch server | Cluster info/API hoặc managed service control plane |
| Elasticsearch plugins | Plugin metadata và server deployment |
| Test Elasticsearch | Testcontainers image/tag |

Đừng nâng server bằng cách đổi Maven dependency. Đổi dependency client không nâng cluster; đổi cluster không tự cập nhật client trong ứng dụng.

## 10. Kiểm tra server version đang chạy

Có thể đọc thông tin cluster qua root endpoint:

~~~http
GET /
~~~

Response thường chứa thông tin version server, build và cluster:

~~~json
{
  "name": "es-node-1",
  "cluster_name": "catalog",
  "version": {
    "number": "8.x.y",
    "build_flavor": "default",
    "build_type": "docker"
  },
  "tagline": "You Know, for Search"
}
~~~

Version trong ví dụ là placeholder. Môi trường managed service có thể hiển thị thông tin khác hoặc giới hạn API.

Cần xác minh endpoint mà ứng dụng thực sự kết nối. Một cluster có thể có nhiều environment hoặc nhiều endpoint; kiểm tra local Elasticsearch không chứng minh production đang cùng version.

Có thể kiểm tra thêm:

~~~http
GET /_cluster/health
~~~

~~~http
GET /_cat/nodes?v
~~~

Các API này giúp xác nhận cluster và node, nhưng cần quyền phù hợp. Không cấp cluster-admin cho ứng dụng runtime chỉ để đọc thông tin vận hành; dùng identity monitoring/admin riêng.

## 11. Kiểm tra dependency thực tế bằng Maven

Khai báo trong pom.xml chỉ là đầu vào. Maven có thể resolve version từ parent, BOM, dependency management, profile hoặc transitive dependency.

Xem dependency tree:

~~~bash
./mvnw dependency:tree
~~~

Lọc các dependency liên quan:

~~~bash
./mvnw dependency:tree \
  -Dincludes=org.springframework.boot:*,org.springframework.data:*,co.elastic.clients:*,org.elasticsearch.client:*
~~~

Xem effective POM:

~~~bash
./mvnw help:effective-pom
~~~

Có thể lưu effective POM ra file để xem version đã được quản lý sau khi áp dụng parent/BOM.

Khi đọc output, tìm:

- Có bao nhiêu version spring-data-commons.
- Version spring-data-elasticsearch thực sự được chọn.
- elasticsearch-java có đúng client generation không.
- Có elasticsearch-rest-high-level-client còn sót lại không.
- Có dependency bị Maven chọn version khác do conflict không.
- Dependency nào bị omitted for conflict và version thắng là gì.

Nếu một thư viện kéo một client version khác vào runtime, hãy xử lý dependency management/exclusion có chủ đích. Không thêm exclusion ngẫu nhiên trước khi biết dependency nào cần nó.

## 12. Kiểm tra dependency thực tế bằng Gradle

Gradle có thể dùng version catalog, platform/BOM, constraints và resolution rules. Vì vậy, đọc build.gradle thôi chưa đủ.

Xem runtime dependency graph:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Kiểm tra version được chọn cho Java API Client:

~~~bash
./gradlew dependencyInsight \
  --dependency elasticsearch-java \
  --configuration runtimeClasspath
~~~

Kiểm tra Spring Data Elasticsearch:

~~~bash
./gradlew dependencyInsight \
  --dependency spring-data-elasticsearch \
  --configuration runtimeClasspath
~~~

Kiểm tra Spring Data Commons:

~~~bash
./gradlew dependencyInsight \
  --dependency spring-data-commons \
  --configuration runtimeClasspath
~~~

dependencyInsight giải thích dependency nào yêu cầu version, constraint nào thắng và vì sao version khác bị loại.

Nếu dùng Gradle platform:

~~~kotlin
dependencies {
    implementation(platform(
        "org.springframework.boot:spring-boot-dependencies:3.x.y"
    ))
    implementation("org.springframework.boot:spring-boot-starter-data-elasticsearch")
}
~~~

Dùng version placeholder phù hợp với dự án thật. Nếu project đã dùng Spring Boot plugin/BOM, tránh import thêm một Boot BOM khác version vào cùng configuration mà không có lý do rõ ràng.

## 13. Nhận diện dependency conflict

Một runtime classpath khỏe mạnh thường có một version nhất quán cho các module cần đi cùng release train.

Ví dụ rủi ro:

~~~text
spring-data-commons: version A
spring-data-elasticsearch: version B
elasticsearch-java: version C
elasticsearch-rest-client: version D
~~~

Không phải mọi version khác nhau đều sai; các artifact có lịch phát hành riêng. Điều cần kiểm tra là chúng có thuộc bộ dependency mà release tương ứng hỗ trợ hay không.

Dấu hiệu runtime conflict:

| Exception | Ý nghĩa có thể gặp |
|---|---|
| NoSuchMethodError | Runtime class thiếu method mà code đã compile gọi |
| NoClassDefFoundError | Class cần thiết không có trên runtime classpath hoặc khởi tạo thất bại |
| ClassNotFoundException | Class loader không tìm thấy class được yêu cầu |
| AbstractMethodError | Implementation runtime không đáp ứng method contract mà caller mong đợi |
| NoSuchFieldError | Field không tồn tại ở class version đang được nạp |
| UnsupportedClassVersionError | Bytecode được compile bằng Java mới hơn runtime hiện tại |

Không kết luận mọi NoClassDefFoundError đều do version conflict; static initializer hoặc cấu hình classpath cũng có thể gây ra. Đọc full cause chain và dependency tree.

## 14. Java runtime là một phần của ma trận

Spring Boot và các thư viện nền tảng có Java baseline riêng. Dự án phải dùng JDK đáp ứng cả:

- Spring Boot version.
- Spring Framework version.
- Spring Data release train.
- Elasticsearch Java API Client.
- Plugin/build tool/compiler.
- Bytecode target của ứng dụng.

Ví dụ cấu hình Maven compiler:

~~~xml
<properties>
    <java.version>17</java.version>
</properties>
~~~

Ví dụ Gradle toolchain:

~~~kotlin
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
~~~

Các số trong ví dụ chỉ minh họa. Dùng baseline được yêu cầu bởi Boot version và dependency set cụ thể.

Phân biệt JDK dùng để compile với JDK dùng để chạy ứng dụng. CI có thể compile bằng JDK mới nhưng production image vẫn chạy Java cũ, dẫn tới UnsupportedClassVersionError.

Khi nâng Boot, hãy kiểm tra cả Docker base image, CI toolchain, local IDE và runtime production.

## 15. Jakarta namespace và các thay đổi major của Spring

Khi nâng từ thế hệ Spring Framework 5/Spring Boot 2 sang Spring Framework 6/Spring Boot 3, nhiều API chuyển từ javax.* sang jakarta.*.

Ví dụ:

- javax.servlet.* chuyển sang jakarta.servlet.*.
- javax.validation.* chuyển sang jakarta.validation.*.
- Các API Jakarta EE liên quan có thể cần version tương ứng.

Đây không phải vấn đề Elasticsearch wire protocol, nhưng có thể khiến ứng dụng không compile hoặc Spring context không khởi động sau khi nâng Boot.

Một dependency cũ kéo javax API vào trong khi ứng dụng cần jakarta có thể tạo lỗi khó chẩn đoán. Khi đọc ma trận, kiểm tra các thư viện web, validation, persistence và security cùng lúc.

Không cố sửa bằng cách thêm cả hai namespace vào classpath rồi bỏ qua dependency cũ. Nâng thư viện lên version hỗ trợ nền tảng mới hoặc thay thế dependency không còn tương thích.

## 16. Elasticsearch plugins phải khớp server

Elasticsearch plugins chạy trong server process, vì vậy chúng có quy tắc version riêng. Analysis plugin, ingest plugin hoặc plugin tùy chỉnh thường cần đúng version tương thích với Elasticsearch server node.

Ví dụ:

- Server Elasticsearch version A.
- Analysis plugin build cho version B.
- Node khởi động và từ chối load plugin vì version mismatch.

Đừng nhầm plugin version với Java client version. Plugin không phải dependency runtime của Spring application.

Kiểm tra plugin trên server:

~~~http
GET /_cat/plugins?v
~~~

Với Docker image, cài plugin trong image build hoặc deployment step theo hướng dẫn của đúng Elasticsearch server version. Khi nâng server, kiểm tra plugin availability/compatibility trước khi rollout node.

Một ứng dụng có thể kết nối thành công nhưng analyzer cần thiết không có trên index/node; lúc đó query behavior hoặc index creation có thể thất bại. Test integration cần dùng server image có cùng plugin set với môi trường mục tiêu.

## 17. Testcontainers cũng phải nằm trong ma trận

Testcontainers không chỉ là dependency test. Image Elasticsearch mà test khởi chạy quyết định server API và behavior mà test đang xác nhận.

Ví dụ:

~~~java
@Container
static final ElasticsearchContainer elasticsearch =
        new ElasticsearchContainer(
                "docker.elastic.co/elasticsearch/elasticsearch:8.x.y"
        );
~~~

Không dùng latest trong test suite cần kết quả lặp lại. Pin server image version và chọn version theo mục tiêu:

- Test tương thích hiện tại: dùng server version production.
- Test nâng cấp: chạy thêm server version đích.
- Test migration: kiểm tra dữ liệu/mapping từ version nguồn sang version đích.
- Test security/TLS: image và fixture phải bật security theo cấu hình cần xác minh.

Nếu production dùng Elasticsearch 8.x nhưng Testcontainers dùng 7.x, integration test có thể bỏ sót API khác biệt. Nếu test dùng version mới hơn production, test có thể thành công với feature mà production chưa hỗ trợ.

## 18. Đọc ma trận theo feature, không chỉ theo version

Lập danh sách tính năng ứng dụng đang dùng:

| Feature | Spring Data/client cần hỗ trợ | Server cần hỗ trợ |
|---|---|---|
| Repository CRUD | Repository mapping và client transport | Index/get/index/update/delete APIs |
| NativeQuery | Query model của client | Query DSL cụ thể |
| Nested query | Query builder hỗ trợ nested | Mapping nested và nested query |
| Aggregation | Aggregation response model | Aggregation type/option |
| Highlight | Search hit/highlight mapping | Highlight API và field mapping |
| Bulk | Bulk request/response model | Bulk action và operation semantics |
| Search after/PIT | Client API và Spring Data integration | PIT/search_after APIs |
| API key | Authentication config trong transport | Security feature/license/configuration |
| TLS/mTLS | SSL context/keystore/truststore | HTTP TLS và realm/configuration |
| Index lifecycle/alias | Admin client API nếu app thực hiện | Index/alias APIs và privilege |

Nếu ứng dụng không dùng một feature, không cần kiểm tra nó như blocker. Nếu có dùng, hãy xác nhận feature trên cả client API và server version.

## 19. Không phải mọi server API đều nằm trong abstraction Spring Data

Spring Data cung cấp abstraction tiện lợi, nhưng không bao phủ toàn bộ Elasticsearch REST API. Khi cần một API mới, có thể phải:

- Nâng Spring Data Elasticsearch để API được expose.
- Dùng Elasticsearch Java API Client trực tiếp nếu dependency/version cho phép.
- Dùng custom repository fragment hoặc adapter.
- Dùng REST client khác theo hướng dẫn chính thức nếu cần một endpoint chưa được expose.

Không thêm client version tùy ý bên cạnh client do Spring Data quản lý. Có thể dẫn đến hai transport stack, hai connection pool, hai bộ cấu hình TLS/authentication và dependency conflict.

Nếu phải gọi API trực tiếp, hãy đặt trong adapter có boundary rõ ràng và ghi rõ version/feature dependency. Test cả request và response với server version mục tiêu.

## 20. Ma trận tương thích của dự án nên có cấu trúc gì?

Một bảng nội bộ nên lưu version đã chọn và bằng chứng hỗ trợ:

| Trường | Giá trị cần ghi |
|---|---|
| Spring Boot | Version đầy đủ |
| Spring Framework | Version do Boot quản lý |
| Spring Data release train | Tên/version train |
| Spring Data Elasticsearch | Version resolved |
| Spring Data Commons | Version resolved |
| Elasticsearch Java API Client | Version resolved |
| HTTP transport | Artifact/version |
| Elasticsearch server | Version của từng environment |
| Java runtime | JDK vendor và version |
| Build tool | Maven/Gradle wrapper version |
| Testcontainers | Library version và Elasticsearch image tag |
| Elasticsearch plugins | Plugin name/version/server compatibility |
| Features | Query/API/security features ứng dụng dùng |
| Evidence | Link release notes/compatibility docs và kết quả integration test |

Bảng nên phân biệt:

- **Declared version**: version ghi trong build file.
- **Resolved version**: version thực tế được Maven/Gradle chọn.
- **Deployed version**: version đang chạy trong environment.
- **Tested version**: version đã được integration test xác nhận.

Bốn giá trị này có thể khác nhau. Khi có khác biệt, cần giải thích rõ thay vì chỉ ghi một con số.

## 21. Ví dụ đọc một ma trận giả định

Giả sử nhóm có bảng sau (số version được đặt tên giả để minh họa cách đọc):

| Thành phần | Version trong dự án | Nguồn xác nhận |
|---|---|---|
| Spring Boot | 3.A.B | Parent/BOM |
| Spring Data train | 2023.X | Boot dependency management |
| Spring Data Elasticsearch | 5.C.D | Resolved dependency |
| Elasticsearch Java API Client | 8.E.F | Dependency tree |
| Elasticsearch server production | 8.G.H | Cluster info |
| Elasticsearch server test | 8.G.H | Testcontainers image |
| Java runtime | 17 | Toolchain và production image |

Cách đọc:

1. Boot 3.A.B quản lý Spring Data train 2023.X hay không?
2. Spring Data Elasticsearch 5.C.D có thuộc train được Boot hỗ trợ không?
3. Version Java API Client 8.E.F có phải dependency mà SDE 5.C.D kỳ vọng không?
4. Client 8.E.F có hỗ trợ server 8.G.H theo tài liệu Elastic không?
5. Server test có cùng version và plugin/security behavior cần thiết với production không?
6. JDK 17 có đáp ứng Boot và mọi dependency không?
7. Integration test có cover các feature ứng dụng thực sự dùng không?

Nếu một ô không có bằng chứng, đánh dấu chưa xác minh. Đừng tự điền compatible chỉ vì ứng dụng chạy được trên máy lập trình viên.

## 22. Phân biệt ma trận chính thức và dependency tree

Hai nguồn này trả lời câu hỏi khác nhau:

- **Compatibility matrix/release documentation**: tổ hợp nào được nhà cung cấp hỗ trợ.
- **Dependency tree/effective POM**: ứng dụng hiện tại đang nạp version nào.

Cần cả hai.

Ví dụ dependency tree cho thấy client version 8.x. Điều đó chưa chứng minh server production 8.y được hỗ trợ. Ngược lại, ma trận chính thức có một tổ hợp hỗ trợ nhưng build file override client version khác, thì dự án thực tế không còn dùng đúng tổ hợp trong ma trận.

Quy trình xác nhận:

1. Đọc ma trận chính thức.
2. Đọc release notes của Boot/Spring Data/Spring Data Elasticsearch.
3. Kiểm tra dependency tree.
4. Kiểm tra server version thực tế.
5. Chạy test tích hợp trên server version mục tiêu.
6. Ghi lại kết quả và các feature đã kiểm tra.

## 23. Những trang tài liệu nên đọc

Khi xác nhận compatibility, ưu tiên tài liệu chính thức theo đúng thành phần:

| Thành phần | Tài liệu nên tìm |
|---|---|
| Spring Boot | System requirements, dependency versions, release notes |
| Spring Data | Release train documentation và supported versions |
| Spring Data Elasticsearch | Reference documentation, compatibility note, migration guide |
| Elasticsearch Java API Client | Client compatibility và release notes |
| Elasticsearch server | Upgrade guide, REST API compatibility, breaking changes |
| Testcontainers | Elasticsearch module docs và version-specific notes |
| Java | JDK release notes và class-file compatibility |
| Plugins | Plugin compatibility với server version |

Không dùng một bài blog cũ làm nguồn duy nhất cho bảng version. Một bài hướng dẫn có thể đúng tại thời điểm viết nhưng dependency management và supported server versions thay đổi theo release.

Khi đọc tài liệu, kiểm tra URL versioned hoặc chọn phiên bản tài liệu tương ứng với dependency đang dùng. Trang current có thể mô tả release mới hơn stack production.

## 24. Đọc release notes và migration guide

Compatibility matrix thường cho biết tổ hợp hỗ trợ, còn release notes giải thích những thay đổi có thể ảnh hưởng code.

Tìm các mục:

- Minimum Java version.
- Changed dependency versions.
- Removed/deprecated client APIs.
- Query builder API changes.
- Mapping/converter changes.
- Default settings thay đổi.
- Security/authentication changes.
- HTTP transport/TLS changes.
- Behavior thay đổi trong server API.
- Upgrade path và breaking changes.

Khi nâng major, đọc migration guide từ version hiện tại đến version đích. Nếu có nhiều major ở giữa, không giả định có thể nhảy thẳng mà không đi qua các bước upgrade bắt buộc.

Với Elasticsearch server, upgrade path có thể có quy định về snapshot, intermediate version và rolling upgrade. Tuân theo server upgrade guide độc lập với việc nâng Java client.

## 25. Nâng client trước hay server trước?

Không có thứ tự chung cho mọi trường hợp. Quyết định dựa trên ma trận và đường nâng cấp được hỗ trợ.

Một quy trình có thể là:

~~~text
Current application + current server
          |
          v
Inspect compatibility and breaking changes
          |
          v
Choose supported intermediate client/server combination
          |
          v
Upgrade application dependencies and test
          |
          v
Deploy compatible client to current server (if supported)
          |
          v
Upgrade server using official upgrade path
          |
          v
Run smoke/integration tests
          |
          v
Enable new features after both sides support them
~~~

Trong một số trường hợp, cần nâng server trước để đáp ứng yêu cầu upgrade path; trong trường hợp khác, cần nâng client trước để ứng dụng hiểu API mới. Không chọn thứ tự chỉ dựa trên tiện lợi triển khai.

Cần kiểm tra cả mixed-version cluster trong thời gian rolling upgrade. Một client có thể kết nối tới node cũ hoặc mới tùy load balancer; tính tương thích phải bao phủ giai đoạn chuyển tiếp đó.

## 26. Lập kế hoạch nâng Spring Boot và Spring Data

Khi nâng Boot:

1. Xác định Boot version đích và JDK baseline.
2. Xem dependency management của Boot đích.
3. Xác định Spring Data release train được Boot quản lý.
4. Xác nhận Spring Data Elasticsearch version và client generation.
5. Đọc Spring Framework/Spring Security migration notes.
6. Kiểm tra namespace javax/jakarta.
7. Chạy compile, unit tests và integration tests.
8. Kiểm tra resolved dependency tree.
9. Kiểm tra cấu hình Elasticsearch client, SSL và authentication.
10. Chạy trên server version mục tiêu.

Nếu cần override Spring Data module, phải có lý do và bằng chứng tương thích. Ưu tiên để Boot BOM quản lý các module trong cùng release train.

## 27. Lập kế hoạch nâng Elasticsearch server

Khi nâng cluster:

- Xác định server version hiện tại và đích.
- Kiểm tra upgrade path chính thức.
- Xem breaking changes của API/query/mapping.
- Kiểm tra plugin và module.
- Kiểm tra index format và migration requirement.
- Tạo snapshot/backup theo hướng dẫn.
- Kiểm tra shard allocation và cluster health.
- Kiểm tra Java client/Spring Data support với server đích.
- Test trên bản sao dữ liệu hoặc staging.
- Theo dõi log, task, cluster health và search/write behavior sau nâng cấp.

Đừng chỉ kiểm tra endpoint root trả version mới. Cần chạy các operation thật mà ứng dụng dùng: repository CRUD, search, aggregation, bulk, alias, security và TLS.

## 28. Dùng Testcontainers để kiểm tra nhiều server version

Có thể tạo profile/test suite khác nhau để chạy cùng bộ integration tests với nhiều Elasticsearch image.

Ví dụ cấu hình image theo property:

~~~java
static String elasticsearchImage() {
    return System.getProperty(
            "test.elasticsearch.image",
            "docker.elastic.co/elasticsearch/elasticsearch:8.x.y"
    );
}
~~~

Khởi tạo container:

~~~java
@Container
static final ElasticsearchContainer elasticsearch =
        new ElasticsearchContainer(elasticsearchImage());
~~~

Có thể chạy test với image hiện tại và image đích qua hai CI job. Giữ cùng application dependency set nếu đang kiểm tra client/server compatibility. Nếu đồng thời đổi client và server trong cùng một test run, sẽ khó biết thay đổi nào gây lỗi.

Test matrix nên gồm:

| Job | Spring/client | Server image | Mục tiêu |
|---|---|---|---|
| Baseline | Current | Current | Xác nhận trạng thái hiện tại |
| Target server | Current | Target | Kiểm tra client hiện tại với server đích |
| Target application | Target | Current | Kiểm tra client mới với server hiện tại |
| Full target | Target | Target | Xác nhận tổ hợp cuối |
| Upgrade path | Các bước trung gian | Các version trung gian | Kiểm tra transition nếu cần |

Chỉ chạy các tổ hợp được tài liệu hỗ trợ hoặc cần thiết để xác minh upgrade plan. Không coi mọi ô trong Cartesian product là một tổ hợp hợp lệ.

## 29. Phân tích lỗi thường gặp khi stack lệch phiên bản

| Dấu hiệu | Nơi kiểm tra đầu tiên |
|---|---|
| NoSuchMethodError trong Spring Data | Spring Data release train và dependency convergence |
| ClassNotFoundException cho HLRC class | Code/client generation sau migration |
| NoClassDefFoundError cho Java API Client | Runtime dependency hoặc client artifact bị exclude |
| UnsupportedClassVersionError | JDK runtime so với bytecode dependency |
| HTTP 406 / media type error | REST compatibility headers/content type |
| HTTP 400 với query option lạ | Server có hỗ trợ API/DSL option không |
| Client compile nhưng server trả unsupported operation | Client/server feature compatibility |
| Plugin không load | Plugin version so với Elasticsearch server |
| Test pass nhưng production fail | Test server image lệch production hoặc thiếu plugin/security |
| Spring context không khởi động sau Boot upgrade | Spring Framework/Jakarta/dependency versions |

Đừng đổi hàng loạt dependency ngay khi thấy lỗi. Trước hết thu thập:

- Full stack trace.
- Resolved dependency tree.
- Boot/Spring Data/client/server/JDK version.
- HTTP request/response error type nếu request đã tới server.
- Test và production configuration khác nhau ở đâu.

## 30. Một compatibility checklist cho mỗi lần nâng cấp

Có thể ghi checklist trong pull request hoặc release plan:

| Kiểm tra | Bằng chứng |
|---|---|
| Boot version đích hỗ trợ JDK hiện tại | Boot system requirements |
| Spring Data train đúng với Boot | Boot dependency management |
| SDE version thuộc train đó | Effective POM/dependency tree |
| Client generation được SDE hỗ trợ | SDE reference/release notes |
| Client version hỗ trợ server đích | Elastic compatibility docs |
| Các API/query đang dùng có trên server đích | Feature docs/integration tests |
| Plugin tương thích server | Plugin documentation |
| Testcontainers image khớp mục tiêu | CI config |
| Runtime JDK khớp compile target | Docker/CI/runtime config |
| Security/TLS/auth hoạt động | Secured integration tests |
| Upgrade path server hợp lệ | Elasticsearch upgrade guide |
| Rollback/snapshot được chuẩn bị | Deployment plan |

Checklist này dùng để lưu bằng chứng, không thay thế đọc tài liệu. Một ô chỉ nên đánh dấu hoàn tất khi có nguồn hoặc test hỗ trợ.

## 31. Ví dụ lưu ma trận version trong dự án

Có thể lưu một bảng trong tài liệu engineering:

~~~yaml
platform:
  springBoot: "3.x.y"
  springFramework: "6.x.y"
  springDataTrain: "2023.x"
  springDataElasticsearch: "5.x.y"

elasticsearch:
  javaApiClient: "8.x.y"
  httpTransport: "resolved-version"
  productionServer: "8.x.y"
  testServerImage: "docker.elastic.co/elasticsearch/elasticsearch:8.x.y"
  plugins:
    - name: "analysis-plugin"
      version: "8.x.y"

runtime:
  java: "17"
  buildTool: "Gradle wrapper version"

verification:
  dependencyTreeReviewed: true
  officialCompatibilityDocsReviewed: true
  integrationTestsAgainstTargetServer: true
~~~

Đây là cấu trúc minh họa, không phải bộ version khuyến nghị. Nên cập nhật bảng trong cùng pull request nâng cấp và giữ link tới release notes/compatibility docs đã dùng.

Không ghi password, API key hoặc certificate private key trong ma trận. Chỉ ghi version, artifact, image tag và tham chiếu tài liệu.

## 32. Những lỗi thường gặp

### Chỉ nhìn version của Spring Boot

Boot BOM quản lý nhiều dependency, nhưng server Elasticsearch là hệ thống độc lập. Cần kiểm tra cả client và server.

### Tự nâng riêng spring-data-elasticsearch

Có thể làm lệch Spring Data Commons hoặc release train. Kiểm tra Boot BOM và compatibility của cả train.

### Cho rằng Java API Client version phải trùng patch server

Không nhất thiết. Đọc chính sách client/server compatibility và kiểm tra feature đang dùng.

### Cho rằng cùng major là đủ

Cùng major là điểm bắt đầu, không chứng minh mọi API/feature đã được hỗ trợ. Minor version và feature availability vẫn quan trọng.

### Dùng client mới với server cũ mà không kiểm tra

Backward/cross-major compatibility không tự được bảo đảm. Kiểm tra REST compatibility mode nếu có và test chính xác.

### Chỉ chạy unit test sau khi nâng

Unit test không chứng minh HTTP protocol, mapping và query behavior với server thật. Cần integration test trên server version mục tiêu.

### Testcontainers dùng latest

Kết quả test thay đổi theo thời gian và có thể khác production. Pin image version.

### Bỏ qua plugin version

Node có thể không khởi động hoặc analyzer/processor không hoạt động sau server upgrade. Kiểm tra plugin cùng server.

### Compile bằng JDK mới nhưng chạy bằng JDK cũ

Có thể gặp UnsupportedClassVersionError. Đồng bộ CI toolchain và production runtime.

### Nâng Boot mà quên Jakarta migration

Code hoặc dependency javax.* có thể không tương thích với Spring Framework mới. Đọc migration guide toàn stack.

### Dùng compatibility mode như giải pháp vĩnh viễn

REST compatibility là cầu nối có giới hạn. Lập kế hoạch nâng client và loại bỏ mode khi hoàn tất transition.

### Không ghi version thực tế

Build file có thể khai báo version khác với resolved dependency hoặc deployed server. Lưu cả declared, resolved, deployed và tested versions.

## 33. Quy trình đọc ma trận và xác nhận một stack

Khi chuẩn bị chọn hoặc nâng phiên bản:

1. Ghi lại Spring Boot, JDK và build tool hiện tại.
2. Xem Boot BOM để biết Spring Data release train được quản lý.
3. Xác định spring-data-elasticsearch version thực tế.
4. Xác định client generation và version được resolve.
5. Xác định HTTP transport và các dependency liên quan.
6. Đọc compatibility guidance của Java API Client với server version.
7. Ghi lại Elasticsearch server version của từng environment.
8. Kiểm tra các feature/query/security APIs ứng dụng thực sự sử dụng.
9. Kiểm tra plugin, Testcontainers image và JDK runtime.
10. Đọc release notes/migration guide từ current tới target.
11. Chạy dependency tree và xử lý conflict.
12. Chạy unit tests, rồi integration tests trên server version mục tiêu.
13. Nếu nâng server, tuân theo upgrade path và kiểm tra mixed-version transition.
14. Lưu compatibility matrix cùng nguồn tài liệu và kết quả test.
15. Chỉ bật feature mới sau khi cả client, server và mapping đã hỗ trợ.

## Tài liệu tham khảo

- [Spring Boot — Dependency Versions](https://docs.spring.io/spring-boot/appendix/dependency-versions/)
- [Spring Boot — System Requirements](https://docs.spring.io/spring-boot/system-requirements.html)
- [Spring Data — Release Trains](https://spring.io/projects/spring-data)
- [Spring Data Elasticsearch — Reference Documentation](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch.html)
- [Spring Data Elasticsearch — Migration Guides](https://docs.spring.io/spring-data/elasticsearch/reference/migration-guides.html)
- [Elasticsearch Java API Client — Compatibility](https://www.elastic.co/guide/en/elasticsearch/client/java-api-client/current/introduction.html)
- [Elasticsearch — REST API Compatibility](https://www.elastic.co/guide/en/elasticsearch/reference/current/rest-api-compatibility.html)
- [Elasticsearch — Upgrade Guide](https://www.elastic.co/guide/en/elasticsearch/reference/current/setup-upgrade.html)
- [Elasticsearch — Plugins](https://www.elastic.co/guide/en/elasticsearch/plugins/current/index.html)
- [Testcontainers — Elasticsearch Module](https://java.testcontainers.org/modules/elasticsearch/)
- [Maven — Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html)
- [Gradle — Viewing and Debugging Dependencies](https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html)

## Kết luận

Đọc ma trận tương thích theo chuỗi Spring Boot → Spring Data release train → Spring Data Elasticsearch → Java client/transport → Elasticsearch server, đồng thời kiểm tra JDK, plugin và Testcontainers. Boot BOM cho biết bộ dependency Spring được quản lý; dependency tree cho biết version thực tế được resolve; tài liệu Elastic cho biết client/server và feature nào được hỗ trợ. Cùng major không thay thế kiểm tra minor/feature, còn REST compatibility mode chỉ là cầu nối có phạm vi. Ghi lại declared, resolved, deployed và tested versions, đọc migration guide và chạy integration test trên server mục tiêu trước khi nâng cấp.
