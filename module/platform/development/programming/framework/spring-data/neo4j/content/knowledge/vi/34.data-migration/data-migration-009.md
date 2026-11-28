# Sao lưu, khôi phục và xác minh kết quả chuyển đổi dữ liệu

Khi chuyển đổi dữ liệu trong một ứng dụng Spring Data Neo4j (SDN), nhóm phát triển cần bảo đảm có thể quay lại trạng thái an toàn nếu migration lỗi, đồng thời chứng minh graph sau chuyển đổi vẫn đáp ứng các quy tắc nghiệp vụ. Một file backup tạo thành công chưa đủ để kết luận có thể khôi phục; một database khởi động bình thường cũng chưa chứng minh dữ liệu đã được chuyển đổi đúng.

Quy trình đáng tin cậy gồm ba lớp kiểm soát:

1. **Sao lưu có thể khôi phục:** tạo bản backup nhất quán, lưu tách khỏi môi trường production và thử restore.
2. **Chuyển đổi có thể kiểm soát:** chạy migration theo phiên bản, có checkpoint, có thể tiếp tục hoặc chạy lại an toàn.
3. **Xác minh nhiều tầng:** kiểm tra tính nhất quán vật lý của database, các bất biến dữ liệu graph và hành vi của ứng dụng SDN.

Bài học này tập trung vào cách thiết kế backup, restore và validation trước, trong và sau một đợt chuyển đổi dữ liệu Neo4j.

## 1. Phân biệt backup, restore và migration

Ba hoạt động liên quan nhưng không thay thế nhau:

| Hoạt động | Mục tiêu | Ví dụ |
| --- | --- | --- |
| Backup | Chụp một trạng thái database để có thể phục hồi | Tạo dump hoặc backup artifact trước migration |
| Restore | Tạo lại database từ artifact đã sao lưu | Nạp dump vào database staging |
| Data migration | Thay đổi cấu trúc hoặc giá trị dữ liệu theo quy tắc mới | Đổi property, chuẩn hóa email, tạo relationship mới |

Backup giữ lại trạng thái dữ liệu tại thời điểm sao lưu. Restore đưa trạng thái đó trở lại một database. Migration áp dụng logic chuyển đổi để tạo ra trạng thái đích. Không nên xem thao tác restore là migration; cũng không nên xem việc export một vài node thành CSV là bản backup đầy đủ của database.

Một đợt migration có thể dùng backup làm điểm phục hồi, chạy chuyển đổi trên bản sao staging, kiểm tra kết quả rồi mới cutover sang hệ thống đích.

~~~mermaid
flowchart TD
    A["Neo4j source"] --> B["Backup nhất quán"]
    B --> C["Restore vào staging"]
    C --> D["Chạy data migration"]
    D --> E["Kiểm tra consistency"]
    E --> F["Kiểm tra invariants nghiệp vụ"]
    F --> G{"Tất cả kiểm tra đạt?"}
    G -->|Không| H["Sửa migration hoặc restore lại"]
    H --> C
    G -->|Có| I["Cutover sang database đích"]
    I --> J["Smoke test và theo dõi"]
~~~

## 2. Lập kế hoạch phục hồi trước khi chạy migration

Trước khi tạo backup, cần thống nhất hai mục tiêu phục hồi:

- **RPO (Recovery Point Objective):** lượng dữ liệu tối đa có thể chấp nhận mất, thường được biểu diễn bằng thời gian.
- **RTO (Recovery Time Objective):** thời gian tối đa chấp nhận để khôi phục dịch vụ.

Ví dụ, RPO 15 phút nghĩa là tổ chức chấp nhận khôi phục về một điểm có thể mất tối đa khoảng 15 phút dữ liệu gần nhất. RTO 60 phút nghĩa là mục tiêu đưa dịch vụ trở lại trong vòng một giờ. Đây là mục tiêu vận hành, không phải cam kết mà lệnh backup tự động bảo đảm.

Kế hoạch cần xác định:

- Database nào được migration và database nào cần backup cùng.
- Phiên bản Neo4j nguồn và phiên bản Neo4j đích.
- Neo4j Community hay Enterprise, triển khai standalone, cluster hay Aura.
- Dung lượng database và thời gian downtime cho phép.
- Tần suất ghi dữ liệu trong thời gian migration.
- Điểm dừng nhận ghi trước cutover hoặc cách đồng bộ phần thay đổi cuối.
- Nơi lưu backup, thời gian lưu giữ và quyền truy cập.
- Ai có trách nhiệm thực hiện restore và xác nhận kết quả.

Không chạy migration production trước khi biết chính xác cách khôi phục, thời gian cần thiết và người chịu trách nhiệm thực hiện.

## 3. Chọn phương thức backup phù hợp

Neo4j có hai nhóm lệnh quản trị thường dùng cho backup và restore:

| Phương thức | Edition / trạng thái | Đặc điểm |
| --- | --- | --- |
| Online backup và restore | Enterprise; backup không được hỗ trợ trên Aura | Có thể backup database đang chạy; hỗ trợ full và differential backup |
| Offline dump và load | Community và Enterprise, với điều kiện database offline theo yêu cầu của lệnh | Tạo archive dump để chuyển hoặc khôi phục database |

Online backup phù hợp khi cần giảm downtime và có hạ tầng Enterprise đã cấu hình backup service. Offline dump phù hợp với môi trường có thể dừng database trong thời gian bảo trì.

Không sao chép trực tiếp thư mục database đang chạy bằng thao tác file copy thông thường. Việc copy file store không theo quy trình Neo4j có thể tạo ra database không nhất quán. Hãy dùng công cụ quản trị được hỗ trợ.

### 3.1. Offline dump bằng neo4j-admin database dump

Lệnh dump tạo một archive của database offline:

~~~bash
bin/neo4j-admin database dump neo4j --to-path=/secure/backups
~~~

Thư mục đích phải tồn tại và có quyền truy cập phù hợp. Database không được mount trong một Neo4j server đang chạy. Trên Community Edition, DBMS phải ở trạng thái offline khi chạy lệnh. Trên Enterprise Edition, lệnh vẫn phải làm việc với database không được mount trong server đang chạy.

Ví dụ quy trình bảo trì:

~~~bash
bin/neo4j stop
bin/neo4j-admin database dump neo4j --to-path=/secure/backups
bin/neo4j-admin database dump system --to-path=/secure/backups
bin/neo4j start
~~~

Các lệnh trên là ví dụ cho cài đặt dùng script trong thư mục bin; tên script và cách khởi động có thể khác theo hệ điều hành hoặc cách cài Neo4j. Với Windows, dùng các file batch tương ứng trong thư mục bin.

Dump chỉ lưu database contents. Lệnh dump không hỗ trợ sao lưu metadata users và roles. Vì vậy, cần lập kế hoạch riêng cho tài khoản, role và cấu hình bảo mật nếu môi trường yêu cầu phục hồi đầy đủ danh tính và quyền truy cập.

### 3.2. Online backup bằng Neo4j Enterprise

Với Enterprise Edition, có thể backup database đang chạy:

~~~bash
bin/neo4j-admin database backup --to-path=/secure/backups/neo4j neo4j
~~~

Backup service của Neo4j phải được cấu hình trước. Lệnh tạo một artifact cho database; lần đầu thường tạo full backup, các lần sau có thể tạo differential backup dựa trên artifact trước đó và transaction log sẵn có.

Một backup chain gồm full backup và các differential backup liên tục. Khi restore, cần giữ đủ các artifact trong chain. Không xóa một differential artifact cũ nếu artifact mới hơn còn phụ thuộc vào nó.

Có thể yêu cầu full backup:

~~~bash
bin/neo4j-admin database backup --type=full --to-path=/secure/backups/neo4j neo4j
~~~

Online backup sử dụng tài nguyên CPU, memory và I/O. Nên theo dõi tải database và cân nhắc chạy backup client trên máy chuyên dụng. Online backup của lệnh này không được hỗ trợ trên Neo4j Aura; với Aura cần dùng cơ chế backup/restore do dịch vụ Aura cung cấp.

### 3.3. Backup database system và các file cấu hình

Một DBMS có thể chứa nhiều database. Database system giữ thông tin quản trị như catalog và trạng thái database, cấu hình bảo mật, thông tin đăng nhập và role. Schema graph như node constraint và index thuộc database nghiệp vụ tương ứng; hãy đưa system database cùng tất cả database nghiệp vụ cần phục hồi vào kế hoạch backup.

Ngoài database artifacts, cần sao lưu riêng những tài nguyên cần để dựng lại môi trường:

- File neo4j.conf và cấu hình riêng cho từng cluster member nếu có.
- Private key, certificate và các thư mục trust/revoked dùng cho TLS.
- Plugin tùy chỉnh và đúng phiên bản plugin tương thích.
- License key của các sản phẩm bổ sung nếu môi trường sử dụng.
- Tài liệu cấu hình database, alias, topology và quyền truy cập cần thiết.

Online backup Enterprise mặc định có thể bao gồm metadata users và roles; tùy chọn include-metadata cho phép chọn metadata cần đưa vào. Offline dump không sao lưu metadata users và roles. Không suy luận rằng có một file dump của database nghiệp vụ là đã có đủ mọi thành phần để dựng lại DBMS.

## 4. Bảo vệ và kiểm tra artifact backup

Backup thường chứa dữ liệu nhạy cảm. Cần bảo vệ nó như dữ liệu production:

- Lưu trên storage tách biệt khỏi máy hoặc volume production.
- Hạn chế quyền đọc và thực thi thư mục backup; không để thư mục có quyền truy cập công khai.
- Mã hóa khi truyền và khi lưu theo chính sách của tổ chức.
- Không đặt mật khẩu hoặc token trực tiếp trong script, shell history hay log.
- Ghi lại database name, thời điểm backup, phiên bản Neo4j, loại artifact và vị trí lưu.
- Giữ đủ các thành phần của differential backup chain.
- Kiểm tra dung lượng, checksum và khả năng đọc artifact.

Trên Linux có thể tạo SHA-256 checksum:

~~~bash
sha256sum /secure/backups/neo4j.dump
~~~

Trên Windows PowerShell:

~~~powershell
Get-FileHash -Algorithm SHA256 .\neo4j.dump
~~~

Checksum giúp phát hiện file bị thay đổi hoặc hỏng trong quá trình sao chép. Nó không chứng minh database bên trong artifact có tính nhất quán hoặc có thể khởi động thành công.

Nên có một manifest backup lưu cùng artifact hoặc trong hệ thống quản lý backup, gồm:

| Trường | Ví dụ |
| --- | --- |
| Database | neo4j |
| Backup time | 2026-11-26T02:00:00Z |
| Neo4j version | Phiên bản thực tế của server |
| Artifact type | DUMP, FULL hoặc DIFFERENTIAL |
| Parent artifact | Artifact cha nếu là differential |
| SHA-256 | Hash của file artifact |
| Source environment | production-eu-1 |
| Owner | Nhóm vận hành chịu trách nhiệm |

## 5. Restore vào staging trước khi thay thế production

Một quy trình an toàn là restore backup vào một database hoặc DBMS thử nghiệm riêng. Việc này cho phép kiểm tra artifact và chạy migration mà không tác động trực tiếp đến nguồn production.

### 5.1. Load offline dump

Có thể load dump vào database đích:

~~~bash
bin/neo4j-admin database load --from-path=/secure/backups neo4j --overwrite-destination=true
~~~

Nếu thay thế database đang tồn tại, database phải được dừng trước khi chạy lệnh và cần dùng tùy chọn overwrite. Không thể thay thế một database đang được mount trong Neo4j server đang chạy.

Nếu load thành một database mới trên Enterprise Edition thay vì thay thế database hiện có, cần tạo database bằng Cypher trên database system sau khi load hoàn tất:

~~~cypher
CREATE DATABASE migration_staging
~~~

Trên Community Edition, lệnh load chỉ chạy khi DBMS offline. Trên Enterprise Edition, load có thể chạy với DBMS online hoặc offline, nhưng không thể thay thế database đang mount trong server đang chạy.

### 5.2. Restore online backup artifact

Với Enterprise Edition, có thể restore từ backup artifact:

~~~bash
bin/neo4j-admin database restore --from-path=/secure/backups/neo4j/neo4j-last.backup migration_staging
~~~

Nếu restore một differential artifact, phải có backup chain cần thiết để Neo4j tìm được full backup và các differential artifact liên quan. Thường chọn artifact cuối cùng của chain để phục hồi đến điểm dữ liệu mong muốn.

Sau khi restore thành database mới, tạo database trên system database nếu quy trình triển khai yêu cầu:

~~~cypher
CREATE DATABASE migration_staging
~~~

Không dùng tùy chọn overwrite để thay thế database trong cluster như thể đó là một standalone database. Cluster có thêm trạng thái topology và allocation; hãy dùng quy trình restore/seed được Neo4j hỗ trợ cho cluster. Restore backup artifact cũng không hỗ trợ hạ database xuống một phiên bản Neo4j cũ hơn; cần xác nhận tương thích phiên bản trước khi thực hiện.

## 6. Kiểm tra consistency của database hoặc backup

Sau khi có artifact, có thể dùng Neo4j Admin consistency checker:

~~~bash
bin/neo4j-admin database check --from-path=/secure/backups/neo4j.dump neo4j
~~~

Đối với database đã restore và đang offline:

~~~bash
bin/neo4j-admin database check neo4j
~~~

Lệnh check có thể kiểm tra consistency của database, dump hoặc full recovered backup. Nó không chạy trên database đang được sử dụng. Một số kiểm tra có thể tốn tài nguyên, đặc biệt trên graph lớn.

Với online backup chain có differential artifact, cần tạo full recovered backup artifact phù hợp trước khi consistency check; differential backup riêng lẻ hoặc full backup chưa được recovery không phải đầu vào hợp lệ cho consistency checker.

Consistency checker có thể kiểm tra cấu trúc graph, node, relationship, property, token, counts và index. Nếu phát hiện lỗi, lệnh trả exit code khác 0 và tạo consistency report. Nếu không phát hiện lỗi, lệnh kết thúc thành công và không cần tạo report.

**Consistency check không chứng minh migration đúng về mặt nghiệp vụ.** Database có thể hoàn toàn nhất quán về cấu trúc nhưng email bị chuẩn hóa sai, relationship trỏ nhầm customer hoặc số lượng đơn hàng bị thiếu. Cần thêm các bước kiểm chứng dữ liệu nghiệp vụ.

## 7. Chuẩn bị baseline trước khi chuyển đổi

Trước migration, hãy chụp các số liệu nguồn trên cùng một snapshot logic. Nếu source vẫn tiếp tục nhận ghi trong khi migration chạy, số liệu source và target ở hai thời điểm khác nhau sẽ không thể so sánh trực tiếp.

Một cách đơn giản là tạm dừng ghi trong khoảng cutover. Với hệ thống cần giảm downtime, có thể chạy initial migration từ snapshot, sau đó đồng bộ delta cuối bằng cơ chế CDC hoặc quy trình change capture phù hợp trước khi chuyển ứng dụng sang database đích.

Ví dụ lấy số lượng node theo label:

~~~cypher
MATCH (person:Person)
RETURN count(person) AS personCount
~~~

Đếm relationship theo type:

~~~cypher
MATCH ()-[relationship]->()
RETURN type(relationship) AS relationshipType,
       count(relationship) AS relationshipCount
ORDER BY relationshipType
~~~

Đếm một nhóm node nghiệp vụ:

~~~cypher
MATCH (order:Order)
RETURN count(order) AS orderCount,
       count(order.totalCents) AS ordersWithTotal
~~~

Không chỉ ghi lại tổng số node. Baseline nên có các số liệu liên quan đến quy tắc chuyển đổi:

- Số node theo từng label.
- Số relationship theo từng type và chiều.
- Số property bắt buộc bị thiếu.
- Số khóa nghiệp vụ duy nhất.
- Phân bố trạng thái hoặc loại dữ liệu.
- Các quan hệ bắt buộc giữa aggregate.
- Tổng giá trị nghiệp vụ có thể đối chiếu, chẳng hạn tổng số tiền đơn hàng.

Nếu migration thay đổi mô hình, số lượng node/relationship đích có thể khác nguồn. Hãy định nghĩa trước mapping dự kiến thay vì yêu cầu mọi con số phải bằng nhau.

## 8. Chạy migration có checkpoint và có thể lặp lại

Migration nên có version hoặc ID duy nhất để biết script nào đã chạy, chạy đến đâu và kết quả cuối cùng là gì.

Ví dụ một node theo dõi migration:

~~~cypher
CREATE CONSTRAINT data_migration_id_unique IF NOT EXISTS
FOR (migration:DataMigration)
REQUIRE migration.id IS UNIQUE
~~~

Sau đó tạo hoặc đọc trạng thái migration:

~~~cypher
MERGE (migration:DataMigration {id: $migrationId})
ON CREATE SET
    migration.version = $version,
    migration.status = "STARTED",
    migration.startedAt = datetime()
RETURN migration
~~~

Sau khi một batch hoàn thành, cập nhật checkpoint trong cùng transaction với batch nếu có thể:

~~~cypher
MATCH (migration:DataMigration {id: $migrationId})
SET migration.lastProcessedId = $lastProcessedId,
    migration.processedCount = $processedCount,
    migration.updatedAt = datetime()
~~~

Thiết kế migration để có thể tiếp tục sau lỗi:

- Chọn khóa ổn định để chia batch.
- Dùng MERGE hoặc khóa idempotency cho thao tác tạo node/relationship.
- Chỉ đánh dấu batch hoàn tất sau khi dữ liệu batch đã commit.
- Không lưu checkpoint trước khi thay đổi dữ liệu tương ứng được commit.
- Ghi lại số record đọc, chuyển đổi, ghi thành công và bị từ chối.
- Lưu riêng lỗi dữ liệu cần xử lý thủ công.

Không cập nhật checkpoint theo số dòng đã đọc nếu transaction ghi batch chưa commit. Nếu process dừng giữa chừng, checkpoint phải phản ánh đúng phần dữ liệu đã được lưu bền vững.

## 9. Xác minh kết quả chuyển đổi bằng Cypher

Sau migration, chạy lại các truy vấn baseline trên target và so sánh theo mapping đã xác định. Các ví dụ dưới đây minh họa một mô hình có Person, Customer, Order và relationship PLACED_BY.

### 9.1. Kiểm tra property bắt buộc

~~~cypher
MATCH (person:Person)
WHERE person.email IS NULL OR trim(person.email) = ""
RETURN count(person) AS invalidEmailCount
~~~

Nếu email bắt buộc và migration chuẩn hóa email, kết quả kỳ vọng có thể là 0. Nếu dữ liệu cũ cho phép email trống, cần ghi rõ chính sách xử lý các trường hợp đó thay vì mặc định mọi record phải có email.

### 9.2. Kiểm tra khóa nghiệp vụ bị trùng

~~~cypher
MATCH (person:Person)
WHERE person.tenantId IS NOT NULL
  AND person.email IS NOT NULL
WITH person.tenantId AS tenantId,
     person.email AS email,
     count(*) AS occurrences
WHERE occurrences > 1
RETURN tenantId, email, occurrences
ORDER BY occurrences DESC
~~~

Truy vấn trả về các cặp tenantId và email bị trùng. Nếu migration phải bảo đảm cặp này duy nhất, kết quả cần rỗng trước khi tạo uniqueness constraint tương ứng.

### 9.3. Kiểm tra relationship bắt buộc

~~~cypher
MATCH (order:Order)
OPTIONAL MATCH (order)-[:PLACED_BY]->(customer:Customer)
WITH order, count(customer) AS customerLinks
WHERE customerLinks <> 1
RETURN count(order) AS ordersWithInvalidCustomerLink
~~~

Nếu mỗi Order phải thuộc đúng một Customer, kết quả cần bằng 0. Truy vấn này kiểm tra số relationship thực tế, không chỉ property customerId trên node Order.

### 9.4. Kiểm tra reference property không có node đích

Nếu mô hình lưu customerId như property trên Order thay vì relationship, có thể kiểm tra reference không khớp:

~~~cypher
MATCH (order:Order)
WHERE order.customerId IS NOT NULL
OPTIONAL MATCH (customer:Customer {id: order.customerId})
WITH order, count(customer) AS matchedCustomers
WHERE matchedCustomers = 0
RETURN count(order) AS ordersWithMissingCustomer
~~~

Kết quả cần được đánh giá theo quy tắc domain. Một số record có thể hợp lệ nếu Customer đã bị archive hoặc được chuyển sang hệ thống khác.

### 9.5. Đối chiếu tổng hợp nghiệp vụ

~~~cypher
MATCH (order:Order)
RETURN count(order) AS orderCount,
       sum(order.totalCents) AS totalOrderValue,
       count(order.totalCents) AS ordersWithAmount
~~~

So sánh orderCount, totalOrderValue và ordersWithAmount với baseline hoặc giá trị kỳ vọng sau mapping. Nếu migration chuyển đổi tiền tệ, loại bỏ đơn bị hủy hoặc gộp đơn, cần tính kết quả đích theo đúng quy tắc thay đổi đó.

## 10. So sánh source và target theo khóa ổn định

Tổng số record bằng nhau không chứng minh từng record đã chuyển đổi đúng. Cần chọn các khóa nghiệp vụ ổn định để so sánh.

Ví dụ:

| Dữ liệu | Cách đối chiếu |
| --- | --- |
| Person | So sánh theo tenantId + email hoặc externalId |
| Order | So sánh theo orderNumber hoặc sourceOrderId |
| Relationship | So sánh cặp khóa hai đầu và relationship type |
| Amount | So sánh giá trị sau quy tắc làm tròn/chuyển đơn vị |
| Timestamp | So sánh sau khi chuẩn hóa timezone và precision |
| Enum/status | So sánh theo bảng mapping trạng thái cũ → mới |

Với graph lớn, không cần tải toàn bộ dữ liệu về ứng dụng chỉ để so sánh. Có thể tính count, min/max, tổng, nhóm theo trạng thái và phân vùng theo khóa. Với các thuộc tính quan trọng, có thể tạo checksum xác định từ các field đã canonicalize trong từng batch.

Khi tạo checksum, cần thống nhất:
- Thứ tự property.
- Chuẩn hóa null.
- Định dạng số và timestamp.
- Encoding ký tự.
- Cách biểu diễn relationship.
- Quy tắc bỏ qua hoặc biến đổi field.

Checksum chỉ có ý nghĩa khi source và target dùng cùng một quy tắc canonicalization hoặc quy tắc đối chiếu đã định nghĩa. Với dữ liệu được biến đổi, checksum toàn bộ raw property thường không thể bằng nhau; hãy tính checksum từ biểu diễn nghiệp vụ sau mapping.

## 11. Xác minh constraint và index sau migration

Migration có thể tạo dữ liệu mới khiến uniqueness constraint hoặc property rule không còn thỏa mãn. Trước khi cutover, hãy xác nhận schema đích.

Liệt kê constraint:

~~~cypher
SHOW CONSTRAINTS
~~~

Liệt kê index và trạng thái:

~~~cypher
SHOW INDEXES
YIELD name, type, entityType, labelsOrTypes, properties, state
RETURN name, type, entityType, labelsOrTypes, properties, state
ORDER BY name
~~~

Chỉ xem index đã sẵn sàng khi trạng thái phù hợp, thường là ONLINE. Nếu index đang POPULATING, không nên đánh giá hiệu năng truy vấn cuối cùng hoặc mở traffic dựa trên giả định index đã sẵn sàng.

Tạo constraint sau khi dữ liệu đã được làm sạch giúp phát hiện duplicate còn sót. Nếu constraint được tạo trước migration, migration phải tuân thủ constraint trong suốt quá trình ghi. Chọn thứ tự dựa trên yêu cầu nhất quán và khả năng xử lý dữ liệu hiện có.

## 12. Kiểm thử ứng dụng Spring Data Neo4j trên target

Sau khi kiểm tra database, cần chạy ứng dụng với cấu hình trỏ vào target staging và xác nhận mapping SDN vẫn đúng.

Các smoke test nên bao gồm:

1. Đọc entity bằng repository theo ID và khóa nghiệp vụ.
2. Đọc relationship cần thiết và xác nhận đúng chiều.
3. Lưu một entity thử nghiệm trong transaction rồi rollback để xác nhận transaction manager hoạt động.
4. Chạy các custom Cypher query, projection và repository fragment quan trọng.
5. Kiểm tra converter tùy chỉnh với dữ liệu đã migrate.
6. Kiểm tra enum, temporal type, null và property đã đổi format.
7. Kiểm tra optimistic locking nếu entity dùng @Version.
8. Xác nhận các index quan trọng đã ONLINE và query plan đạt yêu cầu.

Không chỉ kiểm tra một method findById. Thay đổi mô hình entity hoặc property có thể ảnh hưởng đến mapping relationship, projection, converter và custom query dù thao tác đọc đơn giản vẫn thành công.

## 13. Cutover và phương án rollback

Một cutover có kiểm soát thường gồm các bước:

1. Thông báo cửa sổ migration và xác định thời điểm ngừng ghi.
2. Tạo backup cuối hoặc ghi nhận transaction position cuối của nguồn.
3. Đồng bộ phần delta cuối nếu đã chạy migration từ snapshot trước đó.
4. Chạy validation trên target và lưu kết quả.
5. Cập nhật cấu hình ứng dụng sang database đích.
6. Chạy smoke test và kiểm tra các luồng đọc/ghi chính.
7. Mở traffic theo từng giai đoạn nếu kiến trúc cho phép.
8. Theo dõi error rate, latency, số record và các invariant nghiệp vụ.
9. Giữ nguồn và backup theo thời gian rollback đã thống nhất.

Rollback sau cutover cần được thiết kế trước. Nếu target đã nhận write mới, restore backup nguồn cũ có thể làm mất các thay đổi sau cutover. Khi đó cần một trong các cách:

- Chặn ghi mới và chấp nhận quay về snapshot cũ theo RPO đã thống nhất.
- Đồng bộ ngược các thay đổi phát sinh sau cutover.
- Dùng dual-write hoặc change capture được thiết kế và kiểm soát từ đầu.
- Chạy một migration bù để đưa dữ liệu target về mô hình nguồn.

Không tuyên bố rollback an toàn chỉ vì vẫn còn backup. Phải biết dữ liệu phát sinh sau thời điểm backup sẽ được xử lý như thế nào.

## 14. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Backup command thành công nhưng không thể restore | Chưa từng thử restore, thiếu artifact trong chain hoặc sai phiên bản | Thực hiện restore drill và lưu manifest |
| Dump thiếu user/role | Offline dump không lưu metadata users/roles | Chuẩn bị quy trình khôi phục security metadata riêng |
| Database restore được nhưng ứng dụng không đăng nhập được | Thiếu system/security metadata hoặc cấu hình TLS | Kiểm tra system database, account, role và certificate |
| Count source và target khác nhau | Migration có mapping, filter hoặc batch bị bỏ sót | So sánh theo quy tắc mapping và khóa ổn định |
| Consistency check pass nhưng dữ liệu nghiệp vụ sai | Consistency checker không kiểm tra business invariant | Chạy Cypher validation và application smoke tests |
| Relationship bị thiếu hoặc trùng | Migration tạo node nhưng không bảo đảm quan hệ idempotent | Kiểm tra cardinality, dùng khóa ổn định và MERGE phù hợp |
| Migration chạy lại tạo dữ liệu trùng | Script không idempotent hoặc checkpoint sai | Dùng migration ID, unique key và checkpoint cùng transaction |
| Restore target không tạo database online | Chưa tạo database sau khi load/restore theo yêu cầu edition | Tạo database trên system database và kiểm tra trạng thái |
| Cutover rollback làm mất write mới | Backup rollback cũ hơn các thay đổi sau cutover | Xác định delta recovery hoặc quy trình bù trừ |

## 15. Quy trình hoàn chỉnh trước khi xác nhận migration

Hãy dùng checklist này cho mỗi lần chuyển đổi:

- [ ] Ghi rõ nguồn, đích, phiên bản Neo4j và loại deployment.
- [ ] Xác định RPO, RTO, thời gian dừng ghi và người phụ trách.
- [ ] Backup các database cần thiết, bao gồm system database.
- [ ] Lưu cấu hình, certificate, plugin và license cần thiết.
- [ ] Kiểm tra quyền truy cập và checksum của artifact.
- [ ] Restore thử vào staging hoặc môi trường phục hồi riêng.
- [ ] Chạy consistency checker trên dump/full recovered backup phù hợp.
- [ ] Chụp baseline source và định nghĩa mapping kỳ vọng.
- [ ] Chạy migration có version, checkpoint và idempotency.
- [ ] Đồng bộ delta cuối hoặc đóng băng ghi trước cutover.
- [ ] Kiểm tra count, uniqueness, required property và relationship cardinality.
- [ ] Đối chiếu dữ liệu theo khóa nghiệp vụ và checksum phù hợp.
- [ ] Kiểm tra constraint, index state và application smoke tests.
- [ ] Lưu báo cáo validation, thời điểm cutover và kế hoạch rollback.
- [ ] Thử restore định kỳ để bảo đảm quy trình phục hồi vẫn hoạt động.

## 16. Bài tập tự kiểm tra

1. Backup, restore và data migration khác nhau ở mục tiêu nào?
2. Khi nào nên dùng offline dump/load và khi nào cần online backup/restore?
3. Vì sao cần backup system database cùng các database nghiệp vụ?
4. Offline dump có lưu metadata users và roles hay không?
5. Vì sao checksum của file backup không chứng minh database có thể khôi phục?
6. Consistency checker kiểm tra điều gì và không kiểm tra điều gì?
7. Vì sao cần so sánh dữ liệu theo khóa nghiệp vụ thay vì chỉ so sánh tổng số node?
8. Checkpoint cần được cập nhật ở thời điểm nào để migration có thể tiếp tục an toàn?
9. Vì sao migration phải idempotent khi có thể chạy lại sau lỗi?
10. Tại sao cần xử lý các write phát sinh giữa snapshot ban đầu và thời điểm cutover?
11. Vì sao restore backup cũ sau cutover có thể làm mất dữ liệu mới?
12. Những kiểm thử SDN nào cần chạy sau khi dữ liệu đã được chuyển đổi?

Khi hoàn thành bài học, bạn cần lập được kế hoạch backup có thể phục hồi, khôi phục database vào môi trường kiểm thử, chạy consistency check và xác minh các bất biến dữ liệu graph. Bạn cũng cần tổ chức migration có checkpoint, idempotency, cutover và rollback rõ ràng để thay đổi mô hình dữ liệu trong ứng dụng Spring Data Neo4j một cách có kiểm soát.

## Tài liệu tham khảo

- [Neo4j Operations Manual – Backup and restore planning](https://neo4j.com/docs/operations-manual/current/backup-restore/planning/)
- [Neo4j Operations Manual – Back up an offline database](https://neo4j.com/docs/operations-manual/current/backup-restore/offline-backup/)
- [Neo4j Operations Manual – Back up an online database](https://neo4j.com/docs/operations-manual/current/backup-restore/online-backup/)
- [Neo4j Operations Manual – Restore a database dump](https://neo4j.com/docs/operations-manual/current/backup-restore/restore-dump/)
- [Neo4j Operations Manual – Restore a database backup](https://neo4j.com/docs/operations-manual/current/backup-restore/restore-backup/)
- [Neo4j Operations Manual – Check database consistency](https://neo4j.com/docs/operations-manual/current/backup-restore/consistency-checker/)
- [Spring Data Neo4j – Reference Documentation](https://docs.spring.io/spring-data/neo4j/reference/)

