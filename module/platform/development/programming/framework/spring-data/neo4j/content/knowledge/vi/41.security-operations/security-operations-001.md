# Quản lý bí mật kết nối và quyền tài khoản cơ sở dữ liệu

## Mục tiêu bài học

Sau bài này, bạn có thể:

- Phân biệt authentication (xác thực) và authorization (phân quyền) khi Spring Data Neo4j (SDN) kết nối tới Neo4j.
- Thiết kế tài khoản ứng dụng riêng, tránh dùng tài khoản quản trị cho runtime.
- Cấp quyền theo nguyên tắc least privilege bằng role và graph privilege.
- Cấu hình username, password và URI cho Spring Boot mà không đưa bí mật vào mã nguồn.
- Lưu secret bằng environment variable, secret manager hoặc file mount với Spring Boot config tree.
- Bật mã hóa TLS cho kết nối Bolt và chọn URI scheme phù hợp.
- Xoay vòng credential, thu hồi quyền và kiểm tra quyền hiệu lực.
- Chẩn đoán lỗi xác thực, lỗi phân quyền và rò rỉ secret trong log.

## 1. Bảo mật kết nối Neo4j gồm những lớp nào?

Một ứng dụng Spring Data Neo4j không chỉ cần kết nối được tới database. Nó cần chứng minh danh tính, có đúng quyền trên graph và bảo vệ dữ liệu khi truyền qua mạng.

Có thể chia bảo mật thành các lớp:

| Lớp | Câu hỏi cần trả lời | Cơ chế chính |
| --- | --- | --- |
| Network | Ứng dụng có thể tiếp cận đúng endpoint không? | Firewall, private network, allowlist, giới hạn cổng Bolt |
| Transport | Dữ liệu có được mã hóa trên đường truyền không? | TLS cho Bolt |
| Authentication | Kết nối đang dùng danh tính nào? | Username/password, auth provider hoặc token |
| Authorization | Danh tính đó được làm gì trên database/graph? | Role và privilege |
| Secret lifecycle | Credential được lưu, phân phối và thay mới thế nào? | Secret manager, rotation, revoke |
| Observability | Có thể phát hiện đăng nhập thất bại và quyền bất thường không? | Security log, audit, monitoring |

SDN dùng Neo4j Java Driver để giao tiếp với DBMS qua Bolt. Repository, `Neo4jClient` và `Neo4jTemplate` đều thực thi dưới danh tính mà Driver đã xác thực. Việc gọi qua repository không tự cấp thêm quyền và cũng không bỏ qua authorization của Neo4j.

## 2. Phân biệt authentication và authorization

**Authentication** xác minh người dùng hoặc ứng dụng là ai. Ví dụ, Neo4j xác minh username và password của tài khoản `app_service`.

**Authorization** xác định tài khoản đó được phép thực hiện hành động nào. Ví dụ, tài khoản có thể đọc node `Person` nhưng không được xóa node hoặc tạo index.

Hai bước này độc lập:

- Đăng nhập thành công không có nghĩa tài khoản được đọc mọi database.
- Có quyền đọc database không có nghĩa tài khoản được quản trị user hoặc schema.
- Một kết nối TLS được mã hóa không thay thế xác thực hoặc phân quyền.
- Một query chạy qua SDN vẫn bị Neo4j từ chối nếu thiếu privilege.

Khi chẩn đoán lỗi, cần phân biệt:

| Triệu chứng | Khả năng nguyên nhân |
| --- | --- |
| Authentication failure / unauthorized | Username, password, auth provider hoặc trạng thái tài khoản không đúng |
| Database access denied | Tài khoản thiếu quyền truy cập database |
| Read/write operation not allowed | Role thiếu graph privilege tương ứng |
| Connection refused / timeout | Network, DNS, firewall, endpoint hoặc Neo4j server |
| Certificate validation error | TLS URI, trust chain hoặc hostname của certificate không khớp |
| Query bị từ chối sau khi kết nối thành công | Cypher cần quyền mà tài khoản hiện tại chưa được cấp |

## 3. Tạo tài khoản riêng cho từng ứng dụng

Không nên dùng tài khoản quản trị mặc định `neo4j` làm credential của ứng dụng Spring Boot. Tài khoản quản trị thường có quyền quản lý database, user, role và schema. Nếu credential đó bị lộ, phạm vi ảnh hưởng sẽ lớn hơn nhiều so với một tài khoản runtime.

Nên tách danh tính theo mục đích:

| Tài khoản | Mục đích | Quyền thường cần |
| --- | --- | --- |
| `app_runtime` | Ứng dụng Spring Boot đang chạy | Đọc/ghi graph nghiệp vụ theo yêu cầu |
| `app_reader` | Báo cáo hoặc API chỉ đọc | Truy cập database và đọc graph |
| `app_migrator` | Triển khai migration schema | Chỉ quyền schema cần cho migration |
| Tài khoản DBA | Quản trị Neo4j | Quản lý user, role, database và vận hành |
| Tài khoản developer | Truy cập phát triển | Quyền phù hợp môi trường dev, không dùng chung production |

Mỗi ứng dụng hoặc workload production nên có danh tính riêng. Không chia sẻ cùng một tài khoản giữa API, batch job, công cụ quản trị và developer. Khi cần thu hồi một workload, việc có tài khoản riêng giúp thao tác chính xác mà không làm gián đoạn các ứng dụng khác.

Tách riêng tài khoản migration cũng rất hữu ích. Ứng dụng runtime thường không cần quyền tạo index, constraint, label hoặc relationship type mới. Cấp các quyền đó cho tài khoản triển khai schema, chỉ dùng trong giai đoạn release.

## 4. Role và privilege trong Neo4j

Neo4j sử dụng role-based access control (RBAC): privilege được gán cho role, sau đó role được gán cho user. Cách này giúp quản lý quyền theo chức năng thay vì cấp từng quyền trực tiếp cho từng tài khoản.

Một role có thể đại diện cho một nhiệm vụ:

- `app_readonly`: chỉ đọc dữ liệu cần thiết.
- `app_runtime`: đọc và ghi graph nghiệp vụ.
- `app_schema_migrator`: thực hiện thay đổi schema trong quá trình triển khai.

Các role tích hợp sẵn thường gặp:

| Role | Phạm vi điển hình |
| --- | --- |
| `reader` | Đọc graph trên các database được phép truy cập |
| `editor` | Đọc và ghi dữ liệu, không quản lý schema mở rộng |
| `publisher` | Có thêm quyền mở rộng schema như label và relationship type |
| `architect` | Có thêm quyền quản lý index và constraint |
| `admin` | Quản trị DBMS, database, user, role và privilege |
| `PUBLIC` | Role mặc định được gán cho mọi user |

Quyền cụ thể phụ thuộc phiên bản và edition Neo4j. RBAC với custom role và graph privilege chi tiết có giới hạn edition; hãy kiểm tra tài liệu cho phiên bản triển khai. Community Edition có native authentication và một số chức năng quản lý user nhưng không có đầy đủ khả năng RBAC/privilege như Enterprise Edition hoặc các gói Aura hỗ trợ.

Không chọn `admin`, `architect` hoặc `publisher` cho ứng dụng chỉ vì chúng làm query chạy được. Hãy xác định hành động thật sự mà ứng dụng cần và cấp đúng phạm vi.

### 4.1. Role PUBLIC cũng ảnh hưởng đến quyền hiệu lực

Mọi user đều có role `PUBLIC`. Role này có một số quyền mặc định, chẳng hạn quyền truy cập home database và thực thi function/procedure theo cấu hình mặc định.

Vì vậy, quyền hiệu lực của một user không chỉ đến từ role được gán trực tiếp. Khi kiểm tra bảo mật, hãy xem cả các privilege kế thừa từ `PUBLIC` và các role khác.

Không tự ý thu hồi quyền mặc định của `PUBLIC` trong production khi chưa đánh giá ảnh hưởng tới ứng dụng, procedure và function đang sử dụng.

## 5. Tạo user và role cho ứng dụng

Các lệnh quản trị user, role và privilege được thực thi trong database `system`. Khi kết nối tới DBMS qua Bolt, các lệnh quản trị thường được định tuyến tới `system`. Người chạy lệnh phải có quyền quản trị tương ứng.

Ví dụ dưới đây minh họa cách tạo một user riêng. Mật khẩu được truyền dưới dạng parameter để không phải ghi secret trực tiếp trong script:

```cypher
CREATE USER app_service
SET PASSWORD $appPassword
CHANGE NOT REQUIRED;
```

Tên parameter `$appPassword` được cung cấp bởi công cụ quản trị hoặc quy trình triển khai bí mật. Không đưa giá trị thật vào migration được commit lên Git.

Trong Neo4j, password phải đáp ứng password policy của phiên bản server; tài liệu hiện hành yêu cầu tối thiểu 8 ký tự. Với tài khoản ứng dụng, nên dùng secret ngẫu nhiên có entropy cao, không dùng password có thể đoán từ tên service hoặc môi trường.

### 5.1. Tạo custom role cho ứng dụng đọc/ghi

Trên edition hỗ trợ RBAC và graph privileges, có thể tạo role chỉ dành cho database nghiệp vụ:

```cypher
CREATE ROLE app_runtime IF NOT EXISTS;

GRANT ACCESS ON DATABASE appdb TO app_runtime;

GRANT MATCH {*} ON GRAPH appdb NODE *
TO app_runtime;

GRANT MATCH {*} ON GRAPH appdb RELATIONSHIP *
TO app_runtime;

GRANT WRITE ON GRAPH appdb TO app_runtime;

GRANT ROLE app_runtime TO app_service;
```

Ý nghĩa:

- `ACCESS` cho phép kết nối tới database `appdb`.
- `MATCH` trên node và relationship cho phép tìm graph và đọc property.
- `WRITE` cho phép các thao tác ghi graph cần thiết.
- `GRANT ROLE` gắn role vào user ứng dụng.

Ví dụ này cho phép đọc và ghi toàn bộ graph trong database `appdb`. Nếu ứng dụng chỉ cần một số label hoặc relationship type, hãy thu hẹp privilege theo graph element và property thay vì cấp `*` cho toàn bộ graph.

Nếu ứng dụng chỉ đọc, bỏ privilege `WRITE` và chỉ cấp quyền `MATCH` cần thiết. Không cấp quyền quản trị user, role, database, index hoặc constraint cho runtime role nếu ứng dụng không thực hiện các tác vụ đó.

### 5.2. Dùng built-in reader khi phù hợp

Nếu yêu cầu đơn giản là đọc graph và edition có built-in role tương ứng, có thể gán `reader`:

```cypher
GRANT ROLE reader TO reporting_service;
```

Built-in `reader` có phạm vi rộng trên các database mà role cho phép truy cập. Nếu báo cáo chỉ được phép đọc một database hoặc một phần graph, hãy dùng custom role với privilege giới hạn phù hợp thay vì dựa vào quyền rộng.

### 5.3. Tách quyền runtime và migration

Ứng dụng runtime thường cần đọc/ghi dữ liệu, còn migration có thể cần tạo index, constraint hoặc thay đổi schema.

Có thể tổ chức:

| Role | Quyền |
| --- | --- |
| `app_runtime` | Access + MATCH + WRITE trên graph nghiệp vụ |
| `app_readonly` | Access + MATCH trên graph cần đọc |
| `app_schema_migrator` | Các quyền quản lý index, constraint hoặc token cần cho migration |
| `admin` | Chỉ dành cho quản trị DBMS |

Không cấp `ALL DBMS PRIVILEGES` cho `app_schema_migrator`. Hãy kiểm tra migration thực tế cần quyền nào và cấp đúng quyền đó. Tài khoản migration chỉ nên được dùng bởi pipeline triển khai, không lưu chung secret với ứng dụng đang chạy.

## 6. Kiểm tra role và privilege đã cấp

Sau khi tạo user và role, kiểm tra cấu hình từ một tài khoản quản trị:

```cypher
SHOW USERS;
SHOW ROLES WITH USERS;
SHOW ROLE app_runtime PRIVILEGES;
SHOW USER app_service PRIVILEGES;
```

Các lệnh này giúp xác minh:

- User đã tồn tại và đang ở trạng thái hoạt động.
- Role đã được tạo.
- User đã được gán đúng role.
- Role có đúng privilege trên database/graph.
- User còn nhận quyền từ role khác hoặc `PUBLIC` hay không.

Có thể kiểm tra danh tính của kết nối hiện tại:

```cypher
SHOW CURRENT USER;
SHOW USER PRIVILEGES;
```

Hãy kiểm tra cả quyền được cấp lẫn quyền bị deny. Trong Neo4j, `DENY` không xóa một `GRANT` đã tồn tại; hai quy tắc cùng tồn tại và deny có thể chặn truy cập. Dùng `REVOKE` khi muốn loại bỏ một grant hoặc deny đã cấu hình.

Một quy trình kiểm tra tốt nên thử cả hành động được phép và hành động bị cấm. Ví dụ, tài khoản đọc phải đọc được dữ liệu cần thiết nhưng bị từ chối khi thử ghi node.

## 7. Cấu hình credential trong Spring Boot

Spring Boot cấu hình Neo4j thông qua namespace `spring.neo4j.*`. Các property kết nối thường dùng:

- `spring.neo4j.uri`
- `spring.neo4j.authentication.username`
- `spring.neo4j.authentication.password`

Không ghi username/password production trực tiếp vào `application.yml` được commit. Thay vào đó, dùng placeholder trỏ tới nguồn cấu hình bên ngoài:

```yaml
spring:
  neo4j:
    uri: ${NEO4J_URI}
    authentication:
      username: ${NEO4J_USERNAME}
      password: ${NEO4J_PASSWORD}
```

Khi chạy, môi trường cung cấp các biến:

```text
NEO4J_URI=neo4j+s://graph.example.com
NEO4J_USERNAME=app_service
NEO4J_PASSWORD=<injected-secret>
```

Spring Boot cũng hỗ trợ relaxed binding cho environment variable theo tên property, ví dụ:

```text
SPRING_NEO4J_URI=neo4j+s://graph.example.com
SPRING_NEO4J_AUTHENTICATION_USERNAME=app_service
SPRING_NEO4J_AUTHENTICATION_PASSWORD=<injected-secret>
```

Các ví dụ trên chỉ thể hiện tên biến. Secret thật cần được inject bởi nền tảng triển khai, secret manager hoặc cơ chế cấp phát credential của tổ chức.

### 7.1. Dùng secret manager hoặc mounted secret file

Environment variable là một cách externalize cấu hình, nhưng trong môi trường production có thể ưu tiên secret manager hoặc file secret được mount với quyền truy cập hạn chế.

Spring Boot hỗ trợ config tree. Ví dụ, container nhận các file trong `/run/secrets/`:

```text
/run/secrets/
├── spring.neo4j.authentication.username
└── spring.neo4j.authentication.password
```

Khai báo import:

```yaml
spring:
  config:
    import: "configtree:/run/secrets/"
  neo4j:
    uri: ${NEO4J_URI}
```

Tên file được ánh xạ thành tên property. Vì vậy file `spring.neo4j.authentication.password` cung cấp property `spring.neo4j.authentication.password` mà không cần ghi giá trị vào YAML.

Có thể dùng config tree cho secret được mount từ Docker secrets, Kubernetes Secret volume hoặc nền tảng triển khai tương tự. Cần bảo đảm file chỉ được đọc bởi process và user hệ điều hành cần thiết.

Nếu tổ chức dùng AWS Secrets Manager, Azure Key Vault, Google Secret Manager hoặc Vault, hãy dùng cơ chế tích hợp/config import phù hợp của nền tảng. Không nên tự viết mã lấy secret trong mỗi repository method.

### 7.2. Không để secret trong Git hoặc artifact

Tránh các cách sau:

- Commit password thật vào `application.yml`, `application.properties` hoặc file `.env`.
- Đóng gói secret trong Docker image hoặc JAR.
- Truyền password qua command-line argument nếu có lựa chọn secret injection tốt hơn.
- Đưa credential vào log, exception message, screenshot hoặc ticket.
- Lưu password trong source code, test fixture hoặc file mẫu dùng chung.
- Copy secret production sang môi trường dev/test.

Nếu secret đã bị commit hoặc gửi nhầm vào log, xóa file khỏi commit sau đó là chưa đủ. Hãy coi credential đã bị lộ, xoay vòng nó và kiểm tra lịch sử repository, CI log, artifact, cache và nơi đã nhận secret.

## 8. Bảo vệ kết nối Bolt bằng TLS

Neo4j Java Driver hỗ trợ các URI scheme cho kết nối Bolt:

| URI scheme | Mã hóa | Kiểm tra certificate |
| --- | --- | --- |
| `neo4j://` | Không | Không |
| `neo4j+s://` | Có TLS | Chỉ chấp nhận certificate do CA tin cậy ký |
| `neo4j+ssc://` | Có TLS | Chấp nhận cả self-signed certificate |
| `bolt://` | Không | Không |
| `bolt+s://` | Có TLS | Kiểm tra certificate CA |
| `bolt+ssc://` | Có TLS | Chấp nhận self-signed certificate |

Trong production, ưu tiên URI scheme có xác minh certificate đầy đủ như `neo4j+s://` hoặc `bolt+s://`, theo cấu hình server và routing cần dùng.

Ví dụ:

```yaml
spring:
  neo4j:
    uri: ${NEO4J_URI}
    authentication:
      username: ${NEO4J_USERNAME}
      password: ${NEO4J_PASSWORD}
```

Giá trị `NEO4J_URI` trong production có thể là `neo4j+s://...` nếu endpoint hỗ trợ TLS với certificate CA hợp lệ.

Không xem `neo4j+ssc://` là lựa chọn production mặc định. Scheme này vẫn mã hóa dữ liệu nhưng bỏ qua xác minh certificate theo chuỗi CA, phù hợp hơn với môi trường kiểm thử certificate tự ký có kiểm soát. Nếu dùng self-signed certificate trong môi trường nội bộ, hãy quản lý trust và vòng đời certificate có chủ đích.

`neo4j+s` hỗ trợ routing cho cluster; `bolt+s` kết nối trực tiếp tới một máy chủ cụ thể. Chọn scheme theo topology và hướng dẫn của DBA, không chỉ thay chuỗi URI để xử lý lỗi certificate.

### 8.1. TLS không thay thế authentication

TLS bảo vệ kênh truyền và giúp xác minh server certificate. Nó không thay thế user/password hoặc token.

Một kết nối đúng cần đồng thời:

1. Đúng endpoint và database.
2. TLS được cấu hình theo chính sách.
3. Certificate được xác minh.
4. Credential hợp lệ.
5. User có đúng quyền.

Mutual TLS (mTLS) có thể dùng client certificate như một yếu tố xác thực bổ sung trong một số cấu hình Neo4j Java Driver/DBMS. Nó không mặc nhiên thay thế authentication thông thường; cần cấu hình đồng bộ cả phía client và server, đồng thời quản lý private key như một secret.

## 9. Quản lý quyền theo nguyên tắc least privilege

Least privilege có nghĩa mỗi user chỉ có quyền tối thiểu cần thiết để hoàn thành công việc.

Với SDN, hãy bắt đầu từ các thao tác repository và Cypher mà service thật sự sử dụng:

| Thao tác ứng dụng | Quyền cần xem xét |
| --- | --- |
| `findById`, `findAll`, custom read query | ACCESS + MATCH/TRAVERSE/READ phù hợp |
| `save`, `saveAll`, update entity | Quyền ghi graph cần thiết |
| `deleteById`, `deleteAll` | Quyền xóa graph; chỉ cấp nếu nghiệp vụ cần |
| Custom procedure/function | EXECUTE đúng procedure/function cần thiết |
| Tạo index hoặc constraint | Quyền quản lý index/constraint cho migration |
| Tạo database, user, role | Quyền quản trị DBMS, không dành cho runtime |

Một số lưu ý:

- Giới hạn privilege theo database thay vì `GRAPH *` hoặc `DATABASE *` nếu có thể.
- Giới hạn theo label, relationship type và property khi edition hỗ trợ fine-grained graph privileges.
- Không cấp quyền ghi cho service chỉ đọc.
- Không cấp quyền schema cho ứng dụng runtime nếu schema được triển khai bằng migration.
- Không cấp `admin` chỉ để xử lý lỗi `Forbidden`.
- Rà soát các quyền mặc định từ `PUBLIC` và các role được gán gián tiếp.

### 9.1. Đừng cấp quyền quá rộng để làm query chạy

Một lỗi phổ biến là gặp lỗi thiếu privilege rồi gán role `admin` cho service. Điều này che khuất nguyên nhân và tạo ra quyền vượt quá nhu cầu.

Thay vào đó:

1. Xác định câu Cypher hoặc thao tác repository bị từ chối.
2. Xác định database, label, relationship type, property hoặc procedure mà thao tác cần.
3. Kiểm tra privilege hiệu lực của user.
4. Bổ sung quyền tối thiểu cho role chuyên biệt.
5. Chạy lại test đọc/ghi và xác minh các thao tác ngoài phạm vi vẫn bị từ chối.

Nếu query cần đọc một loại node nhưng quyền chỉ cho phép node khác, hãy điều chỉnh privilege theo graph element. Không mở rộng sang toàn bộ graph trừ khi workload thật sự cần.

## 10. Xoay vòng credential mà không làm gián đoạn ứng dụng

Credential cần được xoay vòng theo chính sách bảo mật và ngay khi nghi ngờ bị lộ. Với ứng dụng chạy nhiều instance, đổi password trực tiếp trên cùng user có thể khiến các instance chưa nhận secret mới không thể tạo kết nối mới.

Một cách triển khai ít gián đoạn là dùng hai service user tạm thời:

1. Tạo user mới, ví dụ `app_service_v2`.
2. Gán cùng role runtime cần thiết cho user mới.
3. Sinh password mới và lưu vào secret manager.
4. Cập nhật cấu hình deployment để ứng dụng dùng user mới.
5. Rolling restart hoặc redeploy các instance.
6. Xác nhận kết nối mới thành công và không còn instance dùng credential cũ.
7. Thu hồi role hoặc suspend/drop user cũ sau khi hết thời gian chuyển tiếp.

Ví dụ thay password của một user hiện tại:

```cypher
ALTER USER app_service
SET PASSWORD $newPassword
CHANGE NOT REQUIRED;
```

Câu lệnh này minh họa thao tác quản trị; parameter `$newPassword` phải được truyền từ kênh bảo mật. Khi đổi password cùng user, các kết nối mới cần dùng secret mới. Hãy phối hợp việc cập nhật secret và tái tạo connection pool của ứng dụng.

Với luồng zero-downtime, thay user theo hai bước thường dễ kiểm soát hơn vì có thể xác nhận credential mới hoạt động trước khi thu hồi credential cũ.

### 10.1. Thu hồi tài khoản hoặc quyền

Khi một service ngừng hoạt động hoặc credential bị lộ, có thể:

- Thu hồi role khỏi user.
- Suspend user nếu edition hỗ trợ trạng thái này.
- Đổi password hoặc xóa user.
- Xoay vòng secret trong secret manager.
- Kiểm tra security log và các kết nối còn hoạt động.

Ví dụ thu hồi role:

```cypher
REVOKE ROLE app_runtime FROM app_service;
```

Chỉ xóa user sau khi xác nhận không còn workload hợp lệ sử dụng nó. Với sự cố bảo mật, ưu tiên cô lập và thu hồi quyền nhanh, sau đó điều tra tác động.

## 11. Xử lý credential trong Spring Data Neo4j

Spring Boot tự cấu hình Neo4j Driver từ các property `spring.neo4j.*`. SDN repositories, client và template sử dụng Driver được cấu hình đó.

Ví dụ repository:

```java
import org.springframework.data.neo4j.repository.Neo4jRepository;

public interface PersonRepository
        extends Neo4jRepository<Person, String> {
}
```

Repository không cần biết password hoặc tự tạo Driver. Credential được cung cấp ở tầng cấu hình ứng dụng.

Tránh viết mã kiểu:

```java
// Không làm như vậy trong service hoặc repository
Driver driver = GraphDatabase.driver(
    "bolt://localhost:7687",
    AuthTokens.basic("neo4j", "password123")
);
```

Đoạn code này hard-code credential, tạo kết nối ngoài hạ tầng Spring và có thể sinh thêm Driver/pool không được quản lý đúng vòng đời.

Nếu cần custom Driver bean, hãy inject credential từ externalized configuration hoặc secret provider và để Spring quản lý lifecycle. Không tạo Driver mới cho từng request hoặc từng repository method.

## 12. Log và diagnostics không được làm lộ secret

Khi chẩn đoán lỗi kết nối, log nên cung cấp đủ thông tin kỹ thuật nhưng không ghi credential.

Có thể ghi:

- Host/URI đã loại bỏ thông tin nhạy cảm.
- Database name.
- Username hoặc service identity nếu chính sách cho phép.
- Thời điểm và loại lỗi.
- Correlation ID hoặc request ID.
- Neo4j server/driver version.
- Kết quả kiểm tra connectivity.

Không ghi:

- Password hoặc authentication token.
- Private key hoặc nội dung secret file.
- Full connection string nếu URI chứa credential.
- Request payload có dữ liệu cá nhân không cần thiết.
- Cypher parameter chứa thông tin nhạy cảm.

Nếu bật Actuator `env` hoặc `configprops` để kiểm tra cấu hình, phải bảo vệ endpoint và kiểm tra cơ chế masking của phiên bản Spring Boot. Không công khai endpoint chứa thông tin cấu hình ra internet hoặc cho người dùng không có quyền vận hành.

Neo4j có các security log để theo dõi sự kiện liên quan authentication. Hãy cấu hình thu thập log, cảnh báo đăng nhập thất bại lặp lại và lưu log theo chính sách retention của tổ chức.

## 13. Kiểm tra bảo mật trước khi đưa lên production

Một checklist cơ bản cho SDN service:

| Hạng mục | Điều cần xác nhận |
| --- | --- |
| User | Mỗi workload có service account riêng |
| Admin | Ứng dụng không dùng tài khoản DBA/admin |
| Password | Secret ngẫu nhiên, không nằm trong Git hoặc image |
| Secret injection | Credential được inject từ môi trường/secret manager |
| TLS | Bolt được mã hóa và certificate được xác minh |
| Database scope | User chỉ truy cập database cần thiết |
| Graph scope | Role chỉ đọc/ghi label, relationship và property cần thiết |
| Schema | Quyền migration tách khỏi runtime |
| PUBLIC | Quyền kế thừa đã được xem xét |
| Rotation | Có quy trình thay credential và xác minh rollout |
| Revocation | Có quy trình thu hồi user/role khi service ngừng hoặc secret lộ |
| Logging | Không ghi password, token hoặc private key |
| Monitoring | Có cảnh báo authentication failure và truy cập bất thường |
| Testing | Có test xác nhận hành động được phép và hành động bị cấm |

## 14. Quy trình chẩn đoán lỗi kết nối và quyền

Khi ứng dụng không truy cập được Neo4j, hãy xử lý theo thứ tự:

1. **Kiểm tra endpoint:** URI, DNS, port Bolt, firewall và network route.
2. **Kiểm tra TLS:** scheme `neo4j+s`/`bolt+s`, certificate chain, hostname và thời hạn certificate.
3. **Kiểm tra credential:** username, secret version, auth provider và trạng thái user.
4. **Kiểm tra database:** database name đúng và user có `ACCESS`.
5. **Kiểm tra graph privilege:** query cần MATCH, WRITE hoặc privilege cụ thể nào?
6. **Kiểm tra role inheritance:** user nhận những role nào, bao gồm `PUBLIC`?
7. **Kiểm tra runtime config:** instance đã nhận secret mới chưa, connection pool có được tái tạo không?
8. **Kiểm tra log:** phân biệt authentication failure, authorization failure và network/TLS error.
9. **Kiểm tra từ cùng danh tính:** thử query tối thiểu bằng đúng user và database của ứng dụng.
10. **Không cấp admin để chữa cháy:** xác định quyền thiếu và cấp đúng role/privilege.

Một số lệnh quản trị hữu ích:

```cypher
SHOW CURRENT USER;
SHOW USER app_service PRIVILEGES;
SHOW ROLE app_runtime PRIVILEGES;
SHOW USERS;
SHOW ROLES WITH USERS;
```

Các lệnh hiển thị user/privilege có thể cần quyền quản trị tương ứng. Thực hiện chúng bằng tài khoản vận hành được cấp quyền, không cần mở rộng quyền của ứng dụng runtime.

## 15. Những lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Dùng tài khoản `neo4j` cho ứng dụng | Runtime có quyền quản trị quá rộng | Tạo service account và role riêng |
| Ghi password vào `application.yml` | Secret nằm trong source control hoặc artifact | Dùng environment/secret manager/config tree |
| Dùng cùng user cho nhiều service | Khó xác định nguồn truy cập và thu hồi riêng | Tách danh tính theo workload |
| Gán role `admin` để hết lỗi permission | Che giấu privilege thiếu và mở rộng quyền | Kiểm tra query rồi cấp quyền tối thiểu |
| Dùng `neo4j://` qua mạng production | Kết nối Bolt không được mã hóa | Dùng TLS URI và xác minh certificate |
| Dùng `+ssc` mặc định ở production | Không xác minh CA certificate | Dùng certificate CA tin cậy hoặc trust configuration phù hợp |
| Tạo user nhưng quên gán role | Authentication thành công nhưng không đủ quyền | Gán role và xác minh privilege |
| Chỉ kiểm tra role trực tiếp | Bỏ qua quyền kế thừa từ `PUBLIC` hoặc role khác | Kiểm tra privilege hiệu lực của user |
| Runtime có quyền tạo index/constraint | Gộp quyền migration với quyền vận hành | Dùng migration identity riêng |
| Đổi password nhưng instance vẫn dùng secret cũ | Deployment hoặc connection pool chưa nhận cấu hình mới | Rolling restart và xác minh từng instance |
| Secret đã xóa khỏi file nhưng từng được commit | Git history và artifact vẫn có thể chứa secret | Xoay vòng credential và rà soát lịch sử |
| Log in ra full URI hoặc auth token | Chẩn đoán không che dữ liệu nhạy cảm | Redact log và thay secret đã lộ |
| Bật Actuator diagnostics công khai | Người ngoài có thể xem cấu hình | Giới hạn endpoint, authentication và network access |
| Không kiểm tra edition | Lệnh RBAC không được hỗ trợ trên edition hiện tại | Đối chiếu tính năng theo phiên bản/edition |

## 16. Câu hỏi tự kiểm tra

1. Authentication khác authorization như thế nào?
2. Vì sao ứng dụng SDN không nên dùng tài khoản quản trị Neo4j?
3. Role và privilege liên hệ với nhau như thế nào?
4. Role `PUBLIC` ảnh hưởng đến quyền hiệu lực của user ra sao?
5. Khi nào dùng built-in `reader`, khi nào nên tạo custom role?
6. Vì sao nên tách tài khoản runtime và migration?
7. `GRANT ACCESS ON DATABASE` khác `MATCH` và `WRITE` như thế nào?
8. Vì sao cần kiểm tra cả node và relationship privileges?
9. Spring Boot nhận Neo4j username/password từ property nào?
10. Config tree giúp cung cấp secret từ file mount như thế nào?
11. `neo4j+s` khác `neo4j+ssc` ở cách xác minh certificate nào?
12. Vì sao TLS không thay thế authentication?
13. Xoay vòng credential bằng hai service user có lợi ích gì?
14. Khi nào cần `REVOKE ROLE` hoặc suspend user?
15. Làm thế nào phân biệt authentication failure với authorization failure?
16. Vì sao không nên cấp `admin` để xử lý lỗi thiếu privilege?

## Tài liệu tham khảo

- [Spring Boot – Working with NoSQL Technologies: Neo4j connection properties](https://docs.spring.io/spring-boot/reference/data/nosql.html)
- [Spring Boot – Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [Neo4j Operations Manual – Authentication and authorization](https://neo4j.com/docs/operations-manual/current/authentication-authorization/)
- [Neo4j Operations Manual – Manage users](https://neo4j.com/docs/operations-manual/current/authentication-authorization/manage-users/)
- [Neo4j Operations Manual – Manage roles](https://neo4j.com/docs/operations-manual/current/authentication-authorization/manage-roles/)
- [Neo4j Operations Manual – Role-based access control and privileges](https://neo4j.com/docs/operations-manual/current/authentication-authorization/manage-privileges/)
- [Neo4j Java Driver Manual – Advanced connection information and TLS](https://neo4j.com/docs/java-manual/current/connect-advanced/)
- [Neo4j Operations Manual – SSL framework](https://neo4j.com/docs/operations-manual/current/security/ssl-framework/)

## Kết luận

Bảo mật SDN bắt đầu từ việc tách biệt danh tính ứng dụng, lưu credential ngoài mã nguồn và chỉ cấp quyền cần thiết trên đúng database/graph. Tài khoản runtime nên có quyền đọc/ghi theo workload; quyền quản trị user, database, index và constraint nên được tách sang tài khoản vận hành hoặc migration.

Spring Boot cung cấp cấu hình Neo4j qua `spring.neo4j.*`, cho phép nhận secret từ environment variable, secret manager hoặc config tree. Kết nối Bolt production cần TLS và xác minh certificate. Khi xoay vòng credential, hãy cập nhật secret, rollout các instance, xác minh kết nối mới rồi thu hồi tài khoản cũ. Kết hợp RBAC, least privilege, secret lifecycle và diagnostics không lộ dữ liệu nhạy cảm sẽ giúp ứng dụng Spring Data Neo4j vận hành an toàn hơn.
