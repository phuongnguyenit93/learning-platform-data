# Chọn công cụ migration phù hợp thay vì kỳ vọng SDN tự tạo schema

Spring Data Neo4j (SDN) ánh xạ entity Java sang node, relationship và property trong Neo4j. Nhiệm vụ này khác với việc quản lý vòng đời schema và dữ liệu của database. Khi ứng dụng cần tạo index, constraint, đổi cấu trúc graph hoặc chuyển đổi dữ liệu cũ, hãy quản lý các thay đổi đó bằng migration có phiên bản và có thể kiểm tra lại.

Neo4j thường được gọi là database schema-optional: bạn có thể tạo node và relationship mà không cần khai báo trước một bộ bảng/cột cố định. Tuy vậy, production vẫn cần quy tắc dữ liệu, uniqueness constraint, index, chuẩn hóa property và kế hoạch chuyển đổi dữ liệu. SDN hiện đại không tự suy ra toàn bộ các yêu cầu này từ entity rồi tự áp dụng schema lên database. Chọn công cụ migration phù hợp giúp thay đổi graph có lịch sử, có thứ tự và có thể triển khai nhất quán qua các môi trường.

## 1. Phân biệt mapping, schema và data migration

Ba công việc thường bị nhầm lẫn:

| Công việc | Câu hỏi cần trả lời | Ví dụ |
|---|---|---|
| Object mapping | Java object được đọc/ghi thành graph như thế nào? | `@Node`, `@Relationship`, `@Property`, repository |
| Schema migration | Database cần index hoặc constraint nào? | Unique constraint cho `Person.personKey`, index cho `Person.email` |
| Data migration | Dữ liệu hiện có cần chuyển đổi ra sao? | Chuẩn hóa email, đổi property `fullName` thành `name`, chuyển relationship type |

SDN tập trung vào mapping và truy cập dữ liệu. Entity có `@Id` không đồng nghĩa Neo4j đã có uniqueness constraint cho property tương ứng. Tương tự, khai báo property trong Java không tự tạo index để tối ưu truy vấn.

Trong các thế hệ SDN hiện đại, cơ chế automatic index manager của Neo4j-OGM đã bị loại bỏ. Những annotation cũ như `@Index`, `@CompositeIndex` và `@Required` không còn được hỗ trợ như một cơ chế thay thế để tự tạo schema. Vì vậy, hãy quản lý schema bằng migration có chủ đích. [Spring Data Neo4j reference – Automatic creation of constraints and indexes](https://docs.spring.io/spring-data/data-graph/docs/7.1.x/reference/html/).

## 2. Neo4j có schema-optional nhưng vẫn cần quản lý schema

Neo4j không yêu cầu mọi property phải được khai báo trước như cột trong bảng quan hệ. Tuy nhiên, index và constraint giúp bảo vệ invariant của domain và cải thiện hiệu năng:

- Unique constraint ngăn nhiều node cùng label có cùng business key.
- Existence constraint hoặc key constraint có thể bảo đảm property bắt buộc, tùy phiên bản và edition.
- Property type constraint giúp giới hạn kiểu dữ liệu khi mô hình cần điều đó.
- Index giúp query planner tìm điểm bắt đầu hiệu quả hơn.
- Constraint trên relationship giúp bảo vệ quy tắc liên quan đến property của relationship.

Ví dụ, ứng dụng tra cứu `Person` theo `personKey` trong nhiều use case. Nếu `personKey` phải duy nhất, hãy thể hiện quy tắc này bằng constraint:

~~~cypher
CREATE CONSTRAINT person_person_key_unique IF NOT EXISTS
FOR (p:Person)
REQUIRE p.personKey IS UNIQUE;
~~~

Nếu truy vấn thường xuyên lọc theo email nhưng email không phải duy nhất, có thể tạo index:

~~~cypher
CREATE INDEX person_email_idx IF NOT EXISTS
FOR (p:Person)
ON (p.email);
~~~

`IF NOT EXISTS` giúp câu lệnh có thể chạy lại trong một số tình huống, nhưng không thay thế việc quản lý phiên bản migration. Nó cũng không bảo đảm constraint đã tồn tại có đúng định nghĩa mong muốn; vẫn cần kiểm tra schema sau khi triển khai.

Tài liệu Neo4j giải thích cách dùng index và constraint trong schema mở tại [Neo4j – Defining a schema](https://neo4j.com/docs/getting-started/cypher/schema/).

## 3. Vì sao không nên để mỗi instance ứng dụng tự thay đổi schema?

Nếu nhiều phiên bản ứng dụng cùng chạy trong quá trình rolling deployment, mỗi instance có thể được khởi động ở thời điểm khác nhau và kỳ vọng schema khác nhau. Nếu từng instance tự tạo hoặc xác nhận schema theo model của riêng nó, có thể phát sinh:

- Nhiều tiến trình cùng cố gắng áp dụng một thay đổi.
- Phiên bản cũ gặp lỗi khi schema mới đã được áp dụng.
- Một thay đổi destructive được thực hiện trước khi mọi instance ngừng dùng cấu trúc cũ.
- Khó xác định database đã chạy đến phiên bản migration nào.
- Không có lịch sử rõ ràng để biết ai triển khai thay đổi và thay đổi nào đã thành công.

Migration tập trung giúp xác định trước thứ tự thay đổi và trạng thái database. Ứng dụng có thể tập trung vào mapping và nghiệp vụ, còn schema/data migration được chạy trong một bước triển khai được kiểm soát.

## 4. Các lựa chọn công cụ migration

Không có một công cụ duy nhất phù hợp cho mọi dự án. Hãy chọn theo cách nhóm phát triển viết Cypher, quy trình CI/CD hiện có, nhu cầu rollback và mức độ phức tạp của chuyển đổi graph.

| Lựa chọn | Phù hợp khi | Điểm mạnh | Cần cân nhắc |
|---|---|---|---|
| Neo4j-Migrations | Dự án Java/Spring muốn quản lý migration theo Cypher | Có Core API, CLI, Maven plugin và Spring Boot starter; lưu lịch sử migration trong database | Cần tuân thủ quy ước tên file, checksum và compatibility của phiên bản |
| Liquibase Neo4j plugin | Tổ chức đã dùng Liquibase cho các database khác | Changelog, changeset, precondition và rollback; hỗ trợ Cypher cùng các format changelog khác | Phải ghép đúng phiên bản extension với Liquibase core và kiểm tra tính năng theo Neo4j version |
| Script Cypher tự quản lý | Prototype hoặc tác vụ vận hành nhỏ, có phạm vi hẹp | Ít phụ thuộc, dễ đọc và chạy trực tiếp | Nhóm phải tự quản lý thứ tự, lịch sử, checksum, khóa chạy và xử lý lỗi |

### Neo4j-Migrations

Neo4j-Migrations được thiết kế riêng cho Neo4j và lấy Cypher script làm trung tâm. Công cụ có các cách chạy migration qua Java API, CLI, Maven plugin và Spring Boot starter. Starter có thể dùng Driver do Spring Boot cấu hình và tự tìm migration scripts trong vị trí mặc định `classpath:neo4j/migrations`.

Ví dụ một migration có phiên bản:

~~~text
src/main/resources/
└── neo4j/
    └── migrations/
        ├── V001__Create_person_constraints.cypher
        └── V002__Normalize_person_email.cypher
~~~

Nội dung `V001__Create_person_constraints.cypher`:

~~~cypher
CREATE CONSTRAINT person_person_key_unique IF NOT EXISTS
FOR (p:Person)
REQUIRE p.personKey IS UNIQUE;

CREATE INDEX person_email_idx IF NOT EXISTS
FOR (p:Person)
ON (p.email);
~~~

Nội dung `V002__Normalize_person_email.cypher`:

~~~cypher
MATCH (p:Person)
WHERE p.email IS NOT NULL
  AND p.emailNormalized IS NULL
SET p.emailNormalized = toLower(trim(p.email));
~~~

Tên migration dùng tiền tố `V` cho versioned migration, phần version, hai dấu gạch dưới và mô tả. Neo4j-Migrations cũng hỗ trợ repeatable migration với tiền tố `R`; chỉ dùng loại này cho script an toàn khi được áp dụng lại.

Các versioned migration đã chạy cần được xem là bất biến. Neo4j-Migrations ghi nhận lịch sử và checksum; nếu sửa nội dung file đã áp dụng, bước validate có thể phát hiện checksum không còn khớp. Hãy tạo migration mới để sửa sai hoặc bổ sung thay đổi, thay vì viết lại lịch sử đã triển khai.

Tham khảo [Neo4j-Migrations – tài liệu và các module](https://neo4j.com/labs/neo4j-migrations/) và [Neo4j-Migrations – current manual](https://michael-simons.github.io/neo4j-migrations/current/).

### Liquibase Neo4j plugin

Nếu tổ chức đã chuẩn hóa Liquibase, plugin Neo4j cho phép quản lý database graph bằng changelog và changeset. Plugin hỗ trợ Cypher changes, các format changelog như XML, YAML, JSON và Cypher, cùng cơ chế precondition và rollback theo khả năng của từng change.

Ví dụ changelog theo định dạng Cypher:

~~~cypher
-- liquibase formatted cypher

-- changeset platform:001-create-person-constraint
CREATE CONSTRAINT person_person_key_unique IF NOT EXISTS
FOR (p:Person)
REQUIRE p.personKey IS UNIQUE;

-- changeset platform:002-create-person-email-index
CREATE INDEX person_email_idx IF NOT EXISTS
FOR (p:Person)
ON (p.email);
~~~

Với thao tác đổi dữ liệu, cần định nghĩa rollback nếu có thể khôi phục chính xác:

~~~xml
<changeSet id="003-normalize-email" author="platform">
    <neo4j:cypher>
        MATCH (p:Person)
        WHERE p.email IS NOT NULL
        SET p.emailNormalized = toLower(trim(p.email))
    </neo4j:cypher>
    <rollback>
        MATCH (p:Person)
        REMOVE p.emailNormalized
    </rollback>
</changeSet>
~~~

Ví dụ XML chỉ minh họa cấu trúc changeset; cần khai báo namespace extension và schema location theo cấu hình Liquibase Neo4j của dự án. Rollback trên chỉ hợp lệ nếu property `emailNormalized` chưa được dùng cho dữ liệu khác và chưa có giá trị được tạo bởi quy trình khác. Với migration dữ liệu thực tế, rollback phải được thiết kế theo ngữ nghĩa nghiệp vụ.

Tài liệu plugin hiện công bố phiên bản riêng và yêu cầu kiểm tra cặp phiên bản `liquibase-neo4j` với Liquibase core tương ứng. Extension hiện hỗ trợ Neo4j Community và Enterprise, với Neo4j tối thiểu 4.4 theo tài liệu hiện hành. Đừng chọn version chỉ dựa trên số mới nhất của Liquibase core; hãy đối chiếu release notes và ma trận tương thích. [Neo4j Plugin for Liquibase – documentation](https://neo4j.com/labs/liquibase/docs/).

### Script Cypher tự quản lý

Với prototype hoặc một thao tác vận hành một lần, có thể lưu Cypher script trong repository và chạy bằng công cụ CLI hoặc pipeline triển khai. Tuy nhiên, nếu dùng cách này cho production, nhóm phải tự bổ sung:

- Số thứ tự và quy ước tên migration.
- Bảng hoặc graph lưu lịch sử đã chạy.
- Cơ chế ngăn hai pipeline chạy cùng một migration.
- Checksum để phát hiện script đã thay đổi.
- Quy tắc retry, tiếp tục sau lỗi và xác minh kết quả.
- Cách xử lý rollback hoặc migration bù.

Khi các yêu cầu này bắt đầu xuất hiện, dùng công cụ migration chuyên dụng thường dễ kiểm soát hơn việc tự xây một framework nhỏ.

### Còn Flyway thì sao?

Neo4j-Migrations được lấy cảm hứng từ Flyway, nhưng đó là hai công cụ khác nhau. Không nên giả định một cấu hình Flyway dành cho SQL/JDBC có thể thực thi Cypher trên Neo4j chỉ vì cách đặt tên migration giống nhau. Nếu tổ chức muốn giữ Flyway trong quy trình, hãy xác minh rõ extension/driver hỗ trợ Neo4j ở phiên bản đang dùng. Với dự án Neo4j-native, Neo4j-Migrations hoặc Liquibase Neo4j plugin là những lựa chọn có tài liệu tích hợp riêng.

## 5. Chọn công cụ theo yêu cầu của dự án

Có thể dùng các câu hỏi sau để đưa ra quyết định:

1. Nhóm có chủ yếu viết Cypher và muốn chạy migration từ Spring Boot, CLI hoặc CI/CD không? Nếu có, hãy đánh giá Neo4j-Migrations trước.
2. Nhóm đã có quy trình Liquibase, cần changelog đa định dạng, precondition và rollback theo changeset không? Hãy đánh giá Liquibase Neo4j plugin.
3. Thay đổi chỉ là một script nhỏ trong môi trường thử nghiệm hay cần quản lý qua nhiều môi trường production? Nếu là production, cần versioning và lịch sử được lưu bền vững.
4. Migration có cần Java code để gọi API, đọc file hoặc thực hiện chuyển đổi đặc biệt không? Neo4j-Migrations hỗ trợ migration viết bằng Java; Liquibase có custom change extension theo mô hình riêng.
5. Công cụ có tương thích Neo4j version, Java version, Spring Boot version và topology triển khai không? Hãy kiểm tra tất cả trước khi thêm dependency.

Đừng chọn công cụ chỉ vì nó đã được dùng cho relational database. Điều quan trọng là công cụ hiểu cách kết nối Neo4j, thực thi Cypher, lưu lịch sử và xử lý failure theo đúng mô hình graph.

## 6. Phân loại migration theo mục đích

Một quy trình rõ ràng thường tách các nhóm thay đổi:

| Nhóm migration | Ví dụ | Mục tiêu |
|---|---|---|
| Schema/index | Tạo unique constraint, index, constraint property | Bảo vệ invariant và cải thiện truy vấn |
| Data backfill | Bổ sung property mới từ dữ liệu cũ | Chuẩn bị dữ liệu cho model mới |
| Graph refactoring | Đổi label, relationship type hoặc hướng relationship | Thay đổi cách biểu diễn domain |
| Data cleanup | Xử lý duplicate, giá trị sai định dạng hoặc node mồ côi | Đưa graph về trạng thái hợp lệ |
| Destructive cleanup | Xóa property cũ, label cũ hoặc relationship không còn dùng | Hoàn tất việc loại bỏ cấu trúc cũ sau giai đoạn chuyển tiếp |

Không gộp tất cả vào một migration khổng lồ. Tách bước giúp xác định rõ điều kiện trước/sau, kiểm tra lỗi và triển khai theo giai đoạn.

## 7. Quy trình triển khai expand–migrate–contract

Khi đổi cấu trúc graph mà nhiều phiên bản ứng dụng có thể cùng chạy, hãy triển khai theo hướng tương thích ngược:

~~~mermaid
flowchart TD
    A[Phiên bản cũ đang chạy] --> B[Expand: thêm property/constraint mới]
    B --> C[Deploy code đọc được cả cấu trúc cũ và mới]
    C --> D[Backfill dữ liệu cũ]
    D --> E[Kiểm tra và chuyển code sang cấu trúc mới]
    E --> F[Deploy phiên bản chỉ dùng cấu trúc mới]
    F --> G[Contract: xóa property/index/relationship cũ]
~~~

Ví dụ đổi `fullName` thành `name`:

1. Tạo phiên bản ứng dụng có thể đọc `name` và fallback sang `fullName`.
2. Thêm property `name` vào các node hiện có bằng migration backfill.
3. Chuyển toàn bộ luồng ghi sang cập nhật `name`; trong giai đoạn chuyển tiếp có thể ghi cả hai property nếu cần tương thích với instance cũ.
4. Kiểm tra không còn node cần đọc `fullName`.
5. Triển khai phiên bản không còn tham chiếu `fullName`.
6. Chạy migration loại bỏ property cũ sau khi mọi instance cũ đã ngừng hoạt động.

Không xóa property cũ ngay trong cùng đợt triển khai với code mới nếu còn instance cũ có thể đọc hoặc ghi property đó.

## 8. Kiểm tra dữ liệu trước khi tạo constraint

Một migration tạo unique constraint có thể thất bại nếu dữ liệu hiện tại đã vi phạm quy tắc. Trước khi tạo constraint cho `Person.personKey`, hãy kiểm tra duplicate:

~~~cypher
MATCH (p:Person)
WHERE p.personKey IS NOT NULL
WITH p.personKey AS personKey, count(*) AS total
WHERE total > 1
RETURN personKey, total
ORDER BY total DESC;
~~~

Kiểm tra property bị thiếu:

~~~cypher
MATCH (p:Person)
WHERE p.personKey IS NULL
RETURN count(p) AS missingPersonKey;
~~~

Nếu có duplicate hoặc giá trị thiếu, cần quyết định cách hợp nhất, gán lại key hoặc loại bỏ dữ liệu không hợp lệ trước khi tạo constraint. Không tự động xóa node trùng chỉ để migration chạy qua; phải xác định relationship và dữ liệu liên quan cần được hợp nhất ra sao.

Sau khi dữ liệu đã đạt yêu cầu, mới chạy lệnh tạo constraint. Cách làm này biến migration thành một thay đổi có thể giải thích và kiểm chứng.

## 9. Backfill dữ liệu với khối lượng lớn

Với graph nhỏ, một câu lệnh `MATCH ... SET` có thể đủ. Với graph lớn, backfill trong một transaction kéo dài có thể giữ tài nguyên lâu, tăng transaction memory và làm ảnh hưởng workload đang chạy.

Hãy cân nhắc:

- Chạy backfill theo batch có giới hạn số node mỗi lần.
- Lưu checkpoint hoặc điều kiện để biết batch nào đã hoàn tất.
- Thiết kế câu lệnh idempotent để có thể chạy lại mà không làm hỏng dữ liệu.
- Theo dõi số node đã xử lý, số node còn lại và thời gian mỗi batch.
- Tách backfill khỏi bước tạo constraint nếu dữ liệu chưa thỏa điều kiện.
- Chạy trong maintenance window nếu thay đổi ảnh hưởng đáng kể tới query production.

Ví dụ một phép backfill có điều kiện:

~~~cypher
MATCH (p:Person)
WHERE p.email IS NOT NULL
  AND p.emailNormalized IS NULL
SET p.emailNormalized = toLower(trim(p.email));
~~~

Điều kiện `p.emailNormalized IS NULL` giúp lần chạy tiếp theo bỏ qua node đã được cập nhật. Với dữ liệu rất lớn, hãy triển khai cơ chế phân trang/batch hoặc migration Java có checkpoint theo công cụ đã chọn; không giả định một script mặc định sẽ tự chia nhỏ transaction.

## 10. Migration phải có lịch sử và tính bất biến

Một migration production nên có:

- Version duy nhất và mô tả dễ hiểu.
- Nội dung được review và lưu trong version control.
- Lịch sử đã áp dụng được ghi vào database hoặc hệ thống migration.
- Checksum hoặc cơ chế phát hiện nội dung đã thay đổi.
- Bằng chứng xác minh sau khi chạy.

Sau khi migration đã chạy ở một môi trường dùng chung, không chỉnh sửa file cũ để “sửa cho đúng”. Hãy tạo migration tiếp theo để sửa trạng thái database. Việc thay đổi file đã áp dụng có thể khiến checksum mismatch hoặc làm môi trường khác nhau có lịch sử không thể so sánh.

Với Neo4j-Migrations, versioned migration được ghi nhận trong migration chain và có checksum; công cụ có lệnh validate để phát hiện thiếu, sai thứ tự hoặc thay đổi migration đã áp dụng. [Neo4j-Migrations – concepts, naming conventions and validation](https://michael-simons.github.io/neo4j-migrations/current/).

## 11. Rollback, forward fix và backup

Rollback không phải lúc nào cũng đơn giản trong graph database. Một migration tạo index có thể có thao tác xóa tương ứng; nhưng một migration hợp nhất hai node hoặc xóa property cũ có thể làm mất thông tin không thể tái tạo.

Phân biệt:

- **Rollback kỹ thuật:** đảo ngược một thay đổi khi dữ liệu gốc vẫn còn và thao tác đảo ngược là xác định.
- **Forward fix:** tạo migration mới để sửa trạng thái hiện tại khi rollback không an toàn hoặc không thể thực hiện.
- **Restore backup:** khôi phục database về một điểm trước migration khi sự cố có phạm vi lớn và đã có kế hoạch downtime/phục hồi.

Trước thay đổi destructive, cần backup phù hợp và thử quy trình restore. Không coi `IF EXISTS`, `IF NOT EXISTS` hoặc rollback script là bằng chứng rằng migration không thể gây mất dữ liệu.

Liquibase Neo4j plugin hỗ trợ rollback change và custom rollback, nhưng khả năng đảo ngược vẫn phụ thuộc nội dung change. Với chuyển đổi graph có mất thông tin, hãy lưu dữ liệu cần thiết hoặc chọn forward fix thay vì viết một rollback giả định. [Liquibase Neo4j – Cypher and rollback changes](https://neo4j.com/labs/liquibase/docs/reference-features/).

## 12. Chạy migration ở đâu trong CI/CD?

Một pipeline triển khai có thể chia thành các bước:

1. Kiểm tra migration naming, version và checksum trong pull request.
2. Chạy migration trên database dùng cho integration test.
3. Xác minh index, constraint và các invariant dữ liệu sau migration.
4. Sao lưu hoặc xác nhận backup trước khi triển khai production nếu thay đổi có rủi ro.
5. Chạy migration bằng một bước triển khai được điều phối, dùng tài khoản database có quyền cần thiết.
6. Chờ migration hoàn tất và xác minh trạng thái.
7. Triển khai phiên bản ứng dụng tương thích với schema mới.
8. Theo dõi lỗi truy vấn và tình trạng database sau triển khai.

Với nhiều replica ứng dụng, tránh để nhiều instance cùng tự chạy một migration không được điều phối. Dùng một migration job hoặc release step duy nhất nếu quy trình triển khai cho phép. Nếu chọn Spring Boot starter tự chạy migration lúc khởi động, hãy hiểu rõ hành vi khi nhiều instance khởi động cùng lúc và kiểm tra cơ chế điều phối của công cụ.

Không nên chạy migration production từ một developer laptop với thông tin đăng nhập thủ công mà không có log, review và lịch sử triển khai.

## 13. Xác minh sau migration

Migration kết thúc mà không báo lỗi chưa đủ để khẳng định graph ở trạng thái mong muốn. Hãy kiểm tra cả schema và dữ liệu.

Kiểm tra constraint:

~~~cypher
SHOW CONSTRAINTS;
~~~

Kiểm tra index:

~~~cypher
SHOW INDEXES;
~~~

Kiểm tra số node chưa được backfill:

~~~cypher
MATCH (p:Person)
WHERE p.email IS NOT NULL
  AND p.emailNormalized IS NULL
RETURN count(p) AS notNormalized;
~~~

Kiểm tra duplicate sau chuẩn hóa:

~~~cypher
MATCH (p:Person)
WHERE p.emailNormalized IS NOT NULL
WITH p.emailNormalized AS email, count(*) AS total
WHERE total > 1
RETURN email, total;
~~~

Ngoài các câu lệnh này, nên kiểm tra migration history, query quan trọng của ứng dụng và thời gian thực thi. Với index mới, kiểm tra trạng thái index đã sẵn sàng trước khi dựa vào nó trong workload production.

## 14. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Kỳ vọng entity `@Node` tự tạo index hoặc constraint | Database không có schema rule như mong muốn | Quản lý schema bằng Cypher migration |
| Dùng annotation cũ `@Index` của Neo4j-OGM trong SDN hiện đại | Annotation không còn là cơ chế schema management của SDN | Dùng migration tool và Cypher |
| Tạo unique constraint trước khi xử lý duplicate | Migration thất bại do dữ liệu vi phạm constraint | Kiểm tra và làm sạch dữ liệu trước |
| Sửa migration đã chạy ở môi trường khác | Checksum hoặc lịch sử các môi trường không còn khớp | Tạo migration mới để sửa |
| Dùng script tự chạy không có lịch sử | Không biết môi trường đã chạy đến đâu | Dùng migration tool hoặc tự quản lý ledger/checksum |
| Để mọi replica cùng chạy migration lúc startup | Có nguy cơ chạy đồng thời và gây cạnh tranh triển khai | Điều phối migration thành một release step |
| Chạy backfill khổng lồ trong một transaction | Giữ tài nguyên lâu và ảnh hưởng workload | Chia batch, checkpoint và theo dõi tiến độ |
| Xóa property cũ ngay khi deploy code mới | Instance cũ có thể vẫn cần property đó | Dùng expand–migrate–contract |
| Viết rollback giả định có thể khôi phục dữ liệu đã xóa | Mất dữ liệu hoặc rollback không đúng | Backup, giữ dữ liệu nguồn hoặc dùng forward fix |
| Không xác minh sau migration | Schema/data có thể chưa đạt yêu cầu dù lệnh đã chạy | Kiểm tra history, schema, invariant và query thực tế |

## 15. Quy trình chọn và áp dụng migration tool

1. Xác định thay đổi là schema migration, data migration hay graph refactoring.
2. Chọn Neo4j-Migrations nếu muốn Cypher-first và tích hợp Java/Spring Boot/CLI; chọn Liquibase Neo4j nếu cần giữ changelog workflow của tổ chức.
3. Kiểm tra compatibility giữa Neo4j, Java, Spring Boot, migration tool và edition đang triển khai.
4. Viết migration có version, mô tả rõ và điều kiện chạy lại an toàn.
5. Kiểm tra dữ liệu hiện tại trước khi tạo constraint hoặc xóa cấu trúc cũ.
6. Chạy trên database thử nghiệm có dữ liệu gần production và xác minh kết quả.
7. Đưa migration vào CI/CD như một bước triển khai được điều phối.
8. Triển khai code theo expand–migrate–contract nếu cần tương thích nhiều phiên bản.
9. Xác minh migration history, index, constraint, dữ liệu và các query quan trọng.
10. Chuẩn bị backup, rollback hoặc forward fix trước khi áp dụng thay đổi destructive.

## 16. Tự kiểm tra

1. Vì sao mapping entity của SDN không đồng nghĩa database đã có index hoặc constraint tương ứng?
2. `schema-optional` trong Neo4j có nghĩa là không cần quản lý schema trong production không?
3. Neo4j-Migrations phù hợp với loại dự án nào và lưu lịch sử migration ra sao?
4. Khi nào nên cân nhắc Liquibase Neo4j plugin thay vì thêm một công cụ migration mới?
5. Vì sao không nên sửa nội dung versioned migration đã được áp dụng?
6. Cần kiểm tra điều gì trước khi tạo unique constraint?
7. Expand–migrate–contract giúp tránh vấn đề nào khi rolling deployment?
8. Vì sao backfill dữ liệu lớn nên có batch và checkpoint?
9. Khi nào rollback không phù hợp và cần dùng forward fix?
10. Sau khi migration chạy xong, cần xác minh những gì ngoài trạng thái exit code?

SDN đảm nhiệm mapping và truy cập graph; migration tool đảm nhiệm lịch sử thay đổi schema và dữ liệu. Hãy chọn Neo4j-Migrations hoặc Liquibase Neo4j theo quy trình của nhóm, lưu migration có version trong source control, kiểm tra dữ liệu trước khi áp dụng constraint và xác minh kết quả sau triển khai. Cách làm này giúp database phát triển có kiểm soát khi model Java, Cypher và yêu cầu nghiệp vụ thay đổi theo thời gian.

Tài liệu tham khảo:

- [Spring Data Neo4j – Automatic creation of constraints and indexes](https://docs.spring.io/spring-data/data-graph/docs/7.1.x/reference/html/)
- [Neo4j – Defining a schema](https://neo4j.com/docs/getting-started/cypher/schema/)
- [Neo4j-Migrations – current manual](https://michael-simons.github.io/neo4j-migrations/current/)
- [Neo4j Plugin for Liquibase](https://neo4j.com/labs/liquibase/docs/)
