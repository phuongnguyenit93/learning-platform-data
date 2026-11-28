# Kiểm tra thay đổi Cypher sinh tự động và dialect khi nâng Neo4j

Khi nâng Neo4j hoặc Spring Data Neo4j (SDN), ứng dụng có thể tiếp tục khởi động nhưng một số thao tác repository lại phát sinh Cypher khác trước, query plan thay đổi hoặc câu lệnh cũ không còn hợp lệ với ngôn ngữ Cypher mới. Vì vậy, cần kiểm tra cả hai phía: **Cypher do SDN sinh ra** và **Cypher dialect mà database đang dùng**.

SDN tạo statement cho các thao tác như `save`, `findById`, derived finder và mapping relationship. Từ SDN 7.1.5, logger `org.springframework.data.neo4j.cypher` ghi tất cả statement được SDN gọi cùng các notification do server gửi. Có thể dùng log để thu thập query thực tế, sau đó kiểm tra cú pháp, parameter, kết quả và execution plan trên phiên bản Neo4j đích.

Một thay đổi quan trọng từ Neo4j 2025.06 là Cypher có version độc lập với server: Neo4j hỗ trợ Cypher 5 và Cypher 25. Vì vậy, nâng server không tự nói lên database đang chạy dialect nào. Cần đọc `defaultLanguage` của từng database, kiểm tra cú pháp bị deprecated hoặc removed, rồi chạy bộ integration test trên đúng phiên bản Cypher dự kiến trước khi rollout.

## 1. Những thành phần có thể làm thay đổi Cypher

Statement ứng dụng gửi đến Neo4j là kết quả phối hợp của nhiều thành phần:

| Thành phần | Có thể ảnh hưởng đến điều gì? | Cần kiểm tra khi nâng cấp |
|---|---|---|
| Spring Data Neo4j | Cấu trúc Cypher sinh từ entity metadata, repository method và template operation | Statement được sinh cho save/load, relationship mapping, finder và pagination |
| Neo4j Java Driver | Bolt protocol, parameter binding, transaction và API gửi query | Driver version được SDN/Spring Boot quản lý và khả năng kết nối server đích |
| Neo4j server | Parser, planner, runtime, procedure, function và execution behavior | Server version, notification, query plan và giới hạn tương thích |
| Cypher language version | Cú pháp và semantics được áp dụng khi parse query | Database đang dùng Cypher 5 hay Cypher 25 |
| APOC/GDS và extension | Procedure/function được cài đặt và hỗ trợ theo server/Cypher version | Phiên bản plugin, chữ ký procedure và compatibility matrix |
| Domain model và mapping metadata | Label, relationship type, property, ID và độ sâu graph được truy vấn | Annotation, constructor, relationship direction và custom mapping |

Không nên quy mọi khác biệt về Cypher cho Neo4j server. Nếu SDN được nâng cùng lúc với server, statement có thể thay đổi vì generator của SDN đã thay đổi. Để tìm đúng nguyên nhân, thay đổi từng lớp có kiểm soát hoặc lưu lại ma trận phiên bản trước/sau.

## 2. Phân biệt Cypher do SDN sinh và Cypher do ứng dụng viết

SDN có thể sinh statement từ mapping metadata hoặc thực thi query do lập trình viên cung cấp:

- **Generated Cypher:** thường đến từ `Neo4jRepository`, derived finder, `Neo4jTemplate`/`ReactiveNeo4jTemplate` và thao tác persistence.
- **Custom Cypher:** được khai báo trong `@Query`, gọi qua `Neo4jClient`/`ReactiveNeo4jClient` hoặc tạo từ Cypher-DSL.
- **Cypher quản trị:** migration, index, constraint và database administration thường chạy ngoài luồng repository nghiệp vụ.

Logger SDN có thể ghi statement mà SDN gọi, bao gồm cả custom query được thực thi qua hạ tầng SDN. Tuy nhiên, custom query vẫn là trách nhiệm của ứng dụng: SDN không tự chuyển cú pháp cũ sang cú pháp mới trong nội dung query do bạn viết.

Ví dụ, repository method:

```java
public interface PersonRepository extends Neo4jRepository<Person, Long> {
    Optional<Person> findByEmail(String email);
}
```

SDN dựa trên metadata của `Person` và tên method để tạo truy vấn tương ứng. Hình dạng statement có thể thay đổi giữa các phiên bản SDN. Hãy quan sát statement thực tế trong log thay vì tự giả định query generator luôn dùng một alias hoặc một thứ tự clause cố định.

Custom query có nội dung do ứng dụng quản lý:

```java
@Query("""
    MATCH (p:Person {email: $email})
    RETURN p
    """)
Optional<Person> findPersonByEmail(String email);
```

Khi nâng Cypher dialect, cần kiểm tra query này theo danh sách cú pháp deprecated/removed và sửa source query nếu cần.

## 3. Bật logger để thu thập generated Cypher

Từ Spring Data Neo4j 7.1.5, logger `org.springframework.data.neo4j.cypher` bao gồm các statement SDN gọi và notification server gửi. Trong môi trường local hoặc staging, có thể bật riêng logger này:

```yaml
logging:
  level:
    root: INFO
    org.springframework.data.neo4j: INFO
    org.springframework.data.neo4j.cypher: DEBUG
```

Các notification category có thể được điều chỉnh độc lập:

| Logger | Nội dung |
|---|---|
| `org.springframework.data.neo4j.cypher.performance` | Cảnh báo hoặc gợi ý về hiệu năng |
| `org.springframework.data.neo4j.cypher.hint` | Notification liên quan query hint |
| `org.springframework.data.neo4j.cypher.deprecation` | Cú pháp hoặc tính năng deprecated |
| `org.springframework.data.neo4j.cypher.unsupported` | Tính năng không được hỗ trợ |
| `org.springframework.data.neo4j.cypher.unrecognized` | Notification chưa được nhận diện |
| `org.springframework.data.neo4j.cypher.security` | Notification về bảo mật |
| `org.springframework.data.neo4j.cypher.topology` | Notification về topology |
| `org.springframework.data.neo4j.cypher.generic` | Notification chung |

Nếu muốn tập trung vào cảnh báo deprecated:

```yaml
logging:
  level:
    org.springframework.data.neo4j.cypher: INFO
    org.springframework.data.neo4j.cypher.deprecation: WARN
    org.springframework.data.neo4j.cypher.unsupported: WARN
```

Thu log trong một kịch bản có thể tái hiện: tạo entity, cập nhật relationship, đọc theo derived finder, chạy `@Query` và xóa dữ liệu thử nghiệm. Lưu lại statement cùng tên operation, SDN version, Driver version, server version, database và Cypher language version.

Không bật `TRACE` toàn bộ ứng dụng chỉ để xem query. Log query có thể chứa tên label/property, parameter và dữ liệu nghiệp vụ tùy logger/backend. Không ghi parameter nhạy cảm vào log chia sẻ; dùng dữ liệu test hoặc redaction trước khi lưu artifact.

## 4. Ghi lại phiên bản server, driver và Cypher dialect

Trước khi so sánh statement, hãy ghi nhận fingerprint của môi trường. Có thể lấy server version và edition:

```cypher
CALL dbms.components()
YIELD name, versions, edition
RETURN name, versions, edition;
```

Với Neo4j 2025.06 trở lên, Cypher language version được tách khỏi server version. Dùng `SHOW DATABASES` trên system database để xem dialect của từng database:

```cypher
SHOW DATABASES
YIELD name, defaultLanguage
RETURN name, defaultLanguage
ORDER BY name;
```

Có thể kiểm tra setting DBMS mặc định cho database mới:

```cypher
SHOW SETTINGS "db.query.default_language"
YIELD name, value, defaultValue
RETURN name, value, defaultValue;
```

Hai kết quả có mục đích khác nhau:

- `SHOW DATABASES ... defaultLanguage` cho biết ngôn ngữ mặc định gắn với từng database.
- `SHOW SETTINGS ... db.query.default_language` cho biết setting DBMS dùng làm mặc định khi tạo database mới nếu không chỉ định riêng.

Thay đổi setting mặc định ở DBMS không tự động đổi dialect của các database đã tồn tại. Nếu database đang chạy khác với giá trị DBMS default, hãy dựa vào `defaultLanguage` của database đó.

Lưu cùng fingerprint của ứng dụng:

- Spring Boot version và dependency management/BOM.
- Spring Data Neo4j version.
- Neo4j Java Driver version thực tế trên runtime classpath.
- Neo4j server version và edition.
- Database name và `defaultLanguage`.
- APOC, GDS hoặc plugin khác nếu query sử dụng.

SDN dựa vào Neo4j Java Driver và mỗi release SDN được kiểm tra với driver tương thích ở thời điểm phát hành. Khi dùng Spring Boot, ưu tiên dependency management của Boot; chỉ override driver khi đã kiểm tra compatibility và test với server mục tiêu. Tránh nâng SDN, Driver và Neo4j cùng lúc mà không có baseline để so sánh.

## 5. Hiểu Cypher 5 và Cypher 25 khi nâng Neo4j

Từ Neo4j 2025.06, server hỗ trợ Cypher 5 và Cypher 25:

| Dialect | Đặc điểm |
|---|---|
| Cypher 5 | Tương thích với query được viết cho Neo4j 2025.05 trở về trước; từ 2025.06 được đóng băng ở semantics của thời điểm đó và chỉ nhận performance enhancement/bug fix |
| Cypher 25 | Bắt đầu từ Neo4j 2025.06; bổ sung tính năng mới, cập nhật và loại bỏ một số cú pháp; tiếp tục phát triển theo các server release |

Các mốc mặc định cần chú ý:

- Neo4j 2025.06 đến 2026.01: database mới hoặc database được migrate tiếp tục dùng Cypher 5, trừ khi được cấu hình Cypher 25.
- Neo4j 2026.02 trở lên: file `neo4j.conf` phân phối mặc định đặt `db.query.default_language=CYPHER_25` cho database mới. Database hiện có giữ cấu hình ngôn ngữ của chúng.
- Nếu setting DBMS không được đặt, giá trị mặc định của `db.query.default_language` là `CYPHER_5`.

Vì vậy, hai database trên cùng một Neo4j server version có thể chạy dialect khác nhau. Không được suy luận dialect chỉ từ số phiên bản server hoặc từ việc nâng cấp thành công.

### Chọn dialect cho từng database

DBMS default được cấu hình bằng `db.query.default_language` trong `neo4j.conf`. Có thể chỉ định rõ ngôn ngữ khi tạo database:

```cypher
CREATE DATABASE application_graph
DEFAULT LANGUAGE CYPHER 25;
```

Hoặc đổi ngôn ngữ mặc định của database hiện có:

```cypher
ALTER DATABASE application_graph
SET DEFAULT LANGUAGE CYPHER 25;
```

Để giữ Cypher 5 trong giai đoạn chuyển tiếp:

```cypher
ALTER DATABASE application_graph
SET DEFAULT LANGUAGE CYPHER 5;
```

Chỉ thay đổi sau khi đã kiểm tra cú pháp, procedure, function và kết quả nghiệp vụ. Quyền quản trị cần thiết để thay đổi default language phải được cấp cho tài khoản migration/operations.

### Chọn dialect cho một query

Có thể đặt version ngay đầu query:

```cypher
CYPHER 25
MATCH (p:Person {personId: $personId})
RETURN p;
```

Hoặc tiếp tục chạy một query cũ bằng Cypher 5:

```cypher
CYPHER 5
MATCH (p:Person {personId: $personId})
RETURN p;
```

Query-level version override hữu ích cho một số custom query trong giai đoạn chuyển đổi. Với statement do SDN sinh tự động, lựa chọn mặc định ở database là cách quản lý tổng quát hơn; không cố sửa chuỗi Cypher nội bộ bằng string replacement để chèn prefix.

## 6. Phát hiện cú pháp bị thay đổi giữa Cypher 5 và Cypher 25

Cypher 25 có một số thay đổi so với Cypher 5. Ví dụ, Cypher 25 không còn cho phép dùng trực tiếp node hoặc relationship ở vế phải của `SET` như một map.

Query chạy với Cypher 5:

```cypher
CYPHER 5
MATCH (order:Order)-[shipping:SHIPPED_TO]->(:Address)
SET order = shipping;
```

Cú pháp tương ứng cho Cypher 25:

```cypher
CYPHER 25
MATCH (order:Order)-[shipping:SHIPPED_TO]->(:Address)
SET order = properties(shipping);
```

Hãy tìm các query trong code có pattern hoặc function bị deprecated/removed. Đặc biệt kiểm tra:

- Gán toàn bộ property map bằng `SET n = ...` hoặc `SET n += ...`.
- Function nội bộ như `id()` đã phát cảnh báo deprecated; không dùng internal ID làm business key.
- Procedure/function của APOC và plugin khác có thể gắn với Cypher language version cụ thể.
- Query quản trị `SHOW`, `CREATE`, `ALTER`, index và constraint có thể có syntax khác nhau theo Cypher version/server release.
- Cú pháp mới chỉ có trong Cypher 25 sẽ không chạy khi database còn chọn Cypher 5.

Không chỉ sửa query để hết lỗi parse. Sau khi đổi cú pháp, cần xác nhận kết quả tương đương về property, relationship, null behavior, cardinality và quyền truy cập.

## 7. Kiểm tra APOC và procedure/function phụ thuộc dialect

Procedure và function, bao gồm built-in và APOC, được gắn với Cypher language version. Một procedure có thể tồn tại trên server nhưng không khả dụng khi query chạy bằng dialect khác.

Ví dụ, tài liệu Neo4j ghi nhận APOC 2025.06+ không hỗ trợ procedure `apoc.create.uuids()` trong Cypher 25, trong khi query chạy với Cypher 5 vẫn có thể sử dụng ở phiên bản tương ứng. Đây là lý do phải kiểm tra cả APOC version và Cypher language version, không chỉ server version.

Liệt kê procedure đang có:

```cypher
SHOW PROCEDURES
YIELD name, signature
WHERE name STARTS WITH 'apoc.'
RETURN name, signature
ORDER BY name;
```

Nếu môi trường/phiên bản không hỗ trợ biến thể `SHOW` có `YIELD`, xem `SHOW PROCEDURES` đơn giản rồi đối chiếu output thực tế. Kiểm tra tài liệu compatibility của đúng phiên bản APOC/GDS và thử gọi procedure trong dialect đích.

## 8. Quy trình thu thập và so sánh generated Cypher

Nên có baseline trước khi nâng cấp:

1. Bật logger Cypher ở môi trường test trên phiên bản SDN hiện tại.
2. Chạy bộ use case đại diện: repository finder, `save`, cập nhật relationship, delete, pagination và custom `@Query`.
3. Lưu statement, parameter name, loại thao tác, thời gian, record count và notification; dùng fixture không chứa dữ liệu thật.
4. Ghi fingerprint server, driver, SDN và dialect.
5. Nâng server/driver/SDN trong môi trường test theo từng bước có kiểm soát.
6. Chạy lại đúng kịch bản trên database có cùng schema và dữ liệu tương đương.
7. So sánh kết quả, graph mutation, notification, exception, query plan và latency.
8. Phân loại khác biệt: thay đổi formatting/alias nội bộ, thay đổi query plan, thay đổi semantics hoặc query không còn parse được.
9. Sửa custom query hoặc mapping khi cần, rồi chạy lại toàn bộ regression suite.

Generated Cypher là chi tiết thực thi của SDN, không phải API contract ổn định để ứng dụng phụ thuộc vào tên alias nội bộ hoặc thứ tự clause. Có thể lưu query snapshot để phục vụ review, nhưng tránh test chỉ so sánh chuỗi tuyệt đối. Ưu tiên test kết quả graph và hành vi nghiệp vụ; chỉ dùng assertion cấu trúc query khi có lý do cụ thể như phát hiện full scan hoặc một operator quan trọng.

## 9. Kiểm tra execution plan của statement thực tế

Khi có statement từ logger, dùng đúng query và parameter names để xem plan trên database đích. Với query đọc, `EXPLAIN` hiển thị kế hoạch mà không thực thi truy vấn:

```cypher
EXPLAIN
MATCH (p:Person {personId: $personId})
RETURN p;
```

`PROFILE` thực thi query và thu thập số liệu thực tế:

```cypher
PROFILE
MATCH (p:Person {personId: $personId})
RETURN p;
```

Với query ghi, `PROFILE` vẫn thực hiện thay đổi. Chỉ chạy trong môi trường test hoặc khi đã hiểu rõ tác động và có dữ liệu an toàn.

Khi so sánh plan giữa hai server/dialect, quan sát:

- Index seek hay label scan.
- Số hàng thực tế so với ước lượng.
- Số `DB Hits`, page hits và page faults nếu có.
- Số relationship được expand và độ rộng của graph traversal.
- Thời gian planning, waiting và execution.
- Notification mới về index, hint, deprecated hoặc unsupported feature.

Plan có thể khác giữa server release do planner/runtime được cải thiện dù kết quả query không đổi. Không yêu cầu plan phải giống từng operator; xác định tiêu chí hiệu năng và correctness của ứng dụng rồi đánh giá theo các tiêu chí đó.

## 10. Kiểm thử tích hợp trên đúng server và dialect đích

Integration test phải chạy trên Neo4j version mà production sẽ dùng. Nếu production chọn Cypher 25, test chỉ trên server cũ dùng Cypher 5 là chưa đủ. Dùng Testcontainers hoặc Neo4j Test Harness phù hợp với phiên bản, cấu hình database và language version rõ ràng.

Một bộ test tối thiểu nên bao gồm:

| Kịch bản | Điều cần xác nhận |
|---|---|
| `repository.save()` node mới | Node, label, ID và property được ghi đúng |
| Save node có relationship | Relationship type, direction và target đúng |
| Update entity | Property thay đổi, relationship không liên quan được giữ |
| Derived finder | Predicate, sort, pagination và kết quả đúng |
| Custom `@Query` | Query parse được trên dialect đích và mapping đúng |
| `Neo4jClient` query | Parameter binding, alias và result mapping đúng |
| Delete | Chỉ dữ liệu dự kiến bị xóa |
| Constraint/index | Migration schema chạy được và trạng thái index sẵn sàng |
| APOC/GDS | Procedure/function được hỗ trợ trong dialect và plugin version đích |
| Transaction rollback | Lỗi giữa thao tác không để lại graph mutation ngoài ý muốn |

Ví dụ test repository đơn giản:

```java
@DataNeo4jTest
class PersonRepositoryUpgradeTest {

    @Autowired
    PersonRepository people;

    @Test
    void savesAndReloadsPersonOnTargetCypherDialect() {
        Person saved = people.save(new Person("p-100", "Lan"));

        Person reloaded = people.findById(saved.getId()).orElseThrow();

        assertThat(reloaded.getPersonId()).isEqualTo("p-100");
        assertThat(reloaded.getName()).isEqualTo("Lan");
    }
}
```

Đây là khung minh họa; entity constructor, ID type và repository phải khớp domain model của ứng dụng. Điều quan trọng là test chạy với đúng Neo4j image, database default language và dependency versions của release candidate.

Không chỉ chạy test với database rỗng. Dùng fixture có relationship sâu, dữ liệu null, nhiều relationship cùng type, dữ liệu lớn và các trường hợp gần với graph production để phát hiện thay đổi mapping hoặc planner.

## 11. Tách thay đổi SDN, Driver và Neo4j để tìm nguyên nhân

Nếu có thể, thực hiện nâng cấp theo ma trận:

| Lần thử | SDN | Driver | Neo4j server/dialect | Mục tiêu |
|---|---|---|---|---|
| Baseline | Hiện tại | Hiện tại | Hiện tại | Lưu generated Cypher và kết quả chuẩn |
| A | Hiện tại | Tương thích | Server mới, Cypher 5 | Tách ảnh hưởng server khỏi thay đổi SDN |
| B | Hiện tại | Tương thích | Server mới, Cypher 25 | Tách ảnh hưởng dialect khỏi server release |
| C | SDN mới | Driver do BOM quản lý | Server mới, Cypher 25 | Đánh giá query generator và mapping mới |

Đây là ma trận chẩn đoán, không phải cam kết mọi tổ hợp đều được hỗ trợ. Chỉ chạy tổ hợp được Spring Data Neo4j, Spring Boot và Driver hỗ trợ. Nếu một tổ hợp không nằm trong compatibility matrix, dùng nó để tìm nguyên nhân trong môi trường thử nghiệm có kiểm soát, không dùng làm cấu hình production.

Nếu không thể tách tất cả thành phần, ít nhất hãy lưu fingerprint trước và sau, sau đó kiểm tra log statement để xác định thay đổi xuất phát từ generator, dialect hay planner.

## 12. Quy trình rollout và rollback

Trước khi nâng production:

1. Xác nhận upgrade path của Neo4j server được hỗ trợ và có backup hợp lệ.
2. Kiểm thử nâng cấp trên bản sao dữ liệu hoặc môi trường staging tương đương.
3. Hoàn tất kiểm tra custom query, generated query, procedure/plugin và query plan.
4. Quyết định Cypher default language cho database; ghi lại giá trị hiện tại và giá trị mục tiêu.
5. Chạy regression và performance test trên dialect mục tiêu.
6. Lập kế hoạch rollback gồm server, application artifact và database compatibility constraints.
7. Triển khai theo canary hoặc từng môi trường; theo dõi query error, latency, notification và connection failure.
8. Chỉ chuyển toàn bộ traffic khi các chỉ số đạt ngưỡng chấp nhận.

Không coi đổi database default language là một bước rollback vô hại. Một query có thể đã được viết theo Cypher 25 và không còn parse được khi database chuyển về Cypher 5. Giữ một danh sách query compatibility và chỉ đổi default language sau khi xác nhận toàn bộ ứng dụng dùng được dialect đó.

## 13. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Chỉ kiểm tra server version | Bỏ sót database đang dùng dialect khác | Kiểm tra `SHOW DATABASES ... defaultLanguage` |
| Cho rằng nâng server tự đổi mọi database sang Cypher 25 | Existing database có thể giữ dialect cũ | Kiểm tra từng database và setting mặc định |
| Chỉ test custom `@Query` | Không phát hiện thay đổi generated Cypher từ repository/template | Test cả derived finder, save, update và delete |
| So sánh generated query bằng chuỗi tuyệt đối | Test dễ vỡ khi alias/format nội bộ đổi | Assert semantics, graph state và query plan theo tiêu chí |
| Nâng SDN, Driver và server cùng lúc | Khó xác định nguồn gốc regression | Lưu fingerprint và tách thay đổi khi có thể |
| Dùng query Cypher 5 trong database Cypher 25 mà không rà soát | Query có thể lỗi parse hoặc đổi semantics | Dùng compatibility list và sửa cú pháp bị removed |
| Cho rằng `CYPHER 25` là cú pháp của mọi server | Server trước 2025.06 không hỗ trợ Cypher 25 | Chỉ dùng trên Neo4j 2025.06 trở lên |
| Chỉ nhìn notification, không chạy regression | Query có thể chạy nhưng kết quả hoặc plan thay đổi | Test kết quả và hiệu năng trên dữ liệu đại diện |
| Dùng `PROFILE` với query ghi trên production | Query thực sự thay đổi graph | Dùng `EXPLAIN` hoặc chạy trong test an toàn |
| Quên kiểm tra APOC/GDS | Procedure/function không tồn tại trong dialect đích | Kiểm tra plugin version và Cypher version compatibility |
| Ghi parameter thật vào query snapshot | Lộ dữ liệu nhạy cảm trong artifact | Dùng fixture giả và redaction |
| Rollback dialect mà không kiểm tra query mới | Ứng dụng có thể không chạy được với dialect cũ | Giữ compatibility gate trước khi đổi language version |

## 14. Bài tập thực hành

Giả sử ứng dụng quản lý `Person` và `KNOWS` relationship, dùng SDN repository và một custom Cypher query:

1. Bật `org.springframework.data.neo4j.cypher` ở `DEBUG` trong môi trường test.
2. Chạy `save`, `findById`, derived finder, update relationship và delete; lưu statement được SDN gọi.
3. Ghi lại SDN version, Driver version, Neo4j server version và `defaultLanguage`.
4. Chạy `SHOW DATABASES YIELD name, defaultLanguage` để xác nhận dialect của database test.
5. Tạo một query dùng `SET n = r`; chạy với Cypher 5 và Cypher 25, sau đó sửa thành `SET n = properties(r)`.
6. Kiểm tra một custom query có `id()` và thay bằng business key hoặc API phù hợp sau khi đánh giá mục đích sử dụng.
7. Chạy cùng bộ integration test trên Neo4j server cũ và server đích.
8. Dùng `EXPLAIN` để so sánh plan của query quan trọng; dùng `PROFILE` trên dữ liệu test để đo DB Hits và thời gian.
9. Kiểm tra các procedure APOC/GDS mà ứng dụng gọi trong dialect đích.
10. Viết upgrade gate yêu cầu không có query lỗi, regression dữ liệu và performance vượt ngưỡng.
11. Viết rollback note ghi rõ server version, database language version và application artifact tương thích.

Sau bài tập, hãy giải thích được vì sao server version không xác định đầy đủ Cypher dialect, cách quan sát statement do SDN sinh, cách kiểm tra Cypher 5/25 và cách xác nhận query vẫn đúng sau nâng cấp.

## Kết luận

Khi nâng Neo4j, cần kiểm tra cả generated Cypher của SDN lẫn Cypher dialect mà từng database đang sử dụng. Thu thập statement bằng logger `org.springframework.data.neo4j.cypher`, ghi fingerprint của SDN/Driver/server, kiểm tra `defaultLanguage`, rà soát cú pháp deprecated/removed và procedure/plugin. Từ Neo4j 2025.06, Cypher 5 và Cypher 25 được quản lý độc lập; database hiện có có thể giữ dialect cũ dù server đã nâng. Chạy integration test, kiểm tra query plan và benchmark trên đúng dialect đích trước khi rollout. Dùng kết quả graph và hành vi nghiệp vụ làm tiêu chí chính, không phụ thuộc vào chuỗi generated Cypher nội bộ như một API contract.

## Tài liệu tham khảo

- [Spring Data Neo4j – Logging](https://docs.spring.io/spring-data/neo4j/reference/appendix/logging.html)
- [Spring Data Neo4j – FAQ: Neo4j Java Driver compatibility](https://docs.spring.io/spring-data/neo4j/reference/faq.html)
- [Neo4j Cypher Manual – Select Cypher version](https://neo4j.com/docs/cypher-manual/current/queries/select-version/)
- [Neo4j Cypher Manual – Additions, deprecations, removals, and compatibility](https://neo4j.com/docs/cypher-manual/current/deprecations-additions-removals-compatibility/)
- [Neo4j Operations Manual – Configure the Cypher default version](https://neo4j.com/docs/operations-manual/current/configuration/cypher-version-configuration/)
- [Neo4j Operations Manual – Show configuration settings](https://neo4j.com/docs/operations-manual/current/configuration/show-settings/)
- [Neo4j Upgrade and Migration Guide](https://neo4j.com/docs/upgrade-migration-guide/current/)
