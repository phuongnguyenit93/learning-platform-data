# Giới hạn auditing khi dữ liệu được ghi ngoài quy trình entity

## Mục tiêu

Sau bài học này, bạn có thể:

- Giải thích phạm vi hoạt động của auditing trong Spring Data Neo4j (SDN).
- Nhận biết vì sao @CreatedDate, @CreatedBy, @LastModifiedDate và @LastModifiedBy không tự cập nhật khi ghi bằng Cypher trực tiếp.
- Phân biệt thao tác lưu entity với custom query, Neo4jClient, Java Driver và công cụ import.
- Bổ sung metadata audit một cách tường minh trong Cypher.
- Dùng cùng một transaction cho thay đổi nghiệp vụ và bản ghi audit.
- Quản lý actor và thời gian nhất quán cho request, batch job và tác vụ hệ thống.
- Thiết kế audit history cho cập nhật và xóa dữ liệu.
- Kiểm thử các đường ghi khác nhau để phát hiện bản ghi thiếu metadata.

## 1. Auditing của SDN hoạt động trong phạm vi nào?

Spring Data Neo4j tích hợp Spring Data Auditing để ghi nhận ai tạo hoặc sửa entity và thời điểm thay đổi. Entity khai báo metadata bằng các annotation:

- @CreatedBy: người tạo entity.
- @CreatedDate: thời điểm tạo entity.
- @LastModifiedBy: người sửa entity gần nhất.
- @LastModifiedDate: thời điểm sửa gần nhất.

Auditing cần được bật bằng @EnableNeo4jAuditing. Với thao tác lưu entity qua repository hoặc Neo4jTemplate, SDN chạy quy trình mapping và auditing trước khi tạo dữ liệu ghi. Những giá trị audit được gắn vào entity rồi mới được chuyển thành tham số Cypher.

Ví dụ, khi gọi:

~~~java
documents.save(document);
~~~

SDN nhận biết domain type, xác định trạng thái entity, áp dụng auditing metadata, chuyển entity thành dữ liệu ghi và thực thi Cypher.

Điểm giới hạn quan trọng là auditing của SDN gắn với quy trình entity này. Nếu ứng dụng thay đổi graph bằng một câu Cypher tự viết, SDN không có entity save operation để áp dụng auditing metadata cho node hoặc relationship bị thay đổi.

## 2. Những đường ghi nào không tự chạy auditing entity?

Các thao tác sau có thể ghi dữ liệu vào Neo4j mà không đi qua luồng lưu entity của SDN:

| Đường ghi | Tự động áp dụng entity auditing? | Lý do |
|---|---|---|
| repository.save(entity) | Có | Entity đi qua quy trình persistence của SDN |
| neo4jTemplate.save(entity) | Có | Template lưu domain object qua mapping infrastructure |
| Neo4jClient.query(...).run() | Không | Client thực thi Cypher trực tiếp, không gọi entity save pipeline |
| Driver.session().run(...) | Không | Java Driver làm việc trực tiếp với Cypher |
| Repository method dùng @Query để SET, CREATE, MERGE | Không | Query tự ghi graph, không thực hiện thao tác save entity |
| Import bằng LOAD CSV hoặc công cụ ETL | Không | Dữ liệu được ghi ở phía Neo4j hoặc công cụ ngoài SDN |
| Cypher chạy từ Neo4j Browser hoặc script quản trị | Không | Không có Spring ApplicationContext tham gia |

Một custom @Query có thể trả về node để SDN ánh xạ thành entity. Việc ánh xạ kết quả đọc không đồng nghĩa với một lần lưu entity; các annotation auditing không tự cập nhật metadata cho thay đổi được thực hiện trong chính câu Cypher đó.

Tương tự, @Transactional chỉ quản lý transaction boundary. Annotation này không tự chèn createdAt, lastModifiedAt hoặc actor vào câu query.

## 3. Ví dụ entity có audit metadata

Giả sử ứng dụng quản lý tài liệu:

~~~java
import java.time.Instant;

import org.springframework.data.annotation.CreatedBy;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.LastModifiedBy;
import org.springframework.data.annotation.LastModifiedDate;
import org.springframework.data.annotation.Version;
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Document")
public class Document {

    @Id
    private String id;

    private String title;

    @CreatedBy
    private String createdBy;

    @CreatedDate
    private Instant createdAt;

    @LastModifiedBy
    private String lastModifiedBy;

    @LastModifiedDate
    private Instant lastModifiedAt;

    @Version
    private Long version;

    protected Document() {
    }

    public Document(String id, String title) {
        this.id = id;
        this.title = title;
    }

    public String getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }

    public String getCreatedBy() {
        return createdBy;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }

    public String getLastModifiedBy() {
        return lastModifiedBy;
    }

    public Instant getLastModifiedAt() {
        return lastModifiedAt;
    }
}
~~~

Bật auditing:

~~~java
import java.util.Optional;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.domain.AuditorAware;
import org.springframework.data.neo4j.config.EnableNeo4jAuditing;
import org.springframework.security.core.Authentication;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.context.SecurityContextHolder;

@Configuration
@EnableNeo4jAuditing(
    modifyOnCreate = true,
    auditorAwareRef = "auditorAware"
)
public class Neo4jAuditingConfiguration {

    @Bean
    AuditorAware<String> auditorAware() {
        return () -> Optional.ofNullable(
                SecurityContextHolder.getContext().getAuthentication()
            )
            .filter(authentication -> authentication.isAuthenticated()
                && !(authentication instanceof AnonymousAuthenticationToken))
            .map(Authentication::getName);
    }
}
~~~

modifyOnCreate = true yêu cầu điền cả metadata sửa đổi khi tạo entity. Nếu chỉ muốn ghi createdBy và createdAt ở lần tạo đầu, cấu hình modifyOnCreate = false.

AuditorAware<String> cung cấp actor cho hai field @CreatedBy và @LastModifiedBy. Nếu ứng dụng chỉ ghi ngày tạo và ngày sửa, không cần triển khai AuditorAware.

SDN dùng DateTimeProvider để lấy thời gian. Mặc định là thời điểm hiện tại; có thể cấu hình dateTimeProviderRef nếu ứng dụng cần một clock thống nhất hoặc clock giả trong test.

Vì ví dụ dùng business ID được gán sẵn, entity có field @Version. Với business ID, SDN cần version property để phân biệt entity mới với entity đã tồn tại; version null biểu thị entity mới. Field này đồng thời hỗ trợ optimistic locking. Nếu dùng ID do SDN sinh và ID còn null trước lần lưu đầu, SDN có thể nhận biết entity mới qua ID.

## 4. Vì sao raw Cypher không tự biết actor và timestamp?

Xét câu query:

~~~cypher
MATCH (d:Document {id: $id})
SET d.title = $title
RETURN d
~~~

Cypher chỉ biết các biến được truyền vào query và các property được chỉ định trong SET. Nó không biết:

- Request hiện tại được xác thực bởi người dùng nào trong Spring Security.
- AuditorAware của ứng dụng trả về actor nào.
- DateTimeProvider được cấu hình ra sao.
- Quy tắc modifyOnCreate của @EnableNeo4jAuditing.
- Entity đang được xem là mới hay đã tồn tại theo metadata của Spring Data.

Đó là thông tin thuộc Spring ApplicationContext và entity auditing infrastructure. Neo4jClient và Java Driver không tự gọi AuditorAware hoặc DateTimeProvider khi thực thi Cypher.

Vì vậy, khi viết query trực tiếp, ứng dụng cần lấy actor và timestamp ở tầng service rồi truyền chúng thành tham số Cypher.

## 5. Tự ghi audit metadata trong Cypher

Một query dùng MERGE có thể xử lý cả trường hợp tạo mới và cập nhật. Hãy đặt createdAt và createdBy trong nhánh ON CREATE; chỉ cập nhật lastModifiedAt và lastModifiedBy trong nhánh ON MATCH.

Với khóa business ID, hãy bảo đảm tính duy nhất ở database:

~~~cypher
CREATE CONSTRAINT document_id_unique IF NOT EXISTS
FOR (d:Document)
REQUIRE d.id IS UNIQUE
~~~

~~~cypher
MERGE (d:Document {id: $id})
ON CREATE SET
    d.title = $title,
    d.createdAt = $now,
    d.createdBy = $actor,
    d.lastModifiedAt = $now,
    d.lastModifiedBy = $actor,
    d.version = 0
ON MATCH SET
    d.title = $title,
    d.lastModifiedAt = $now,
    d.lastModifiedBy = $actor,
    d.version = coalesce(d.version, 0) + 1
RETURN d.id AS id
~~~

Quy tắc ở đây:

- Tạo mới: ghi cả thông tin tạo và thông tin sửa.
- Cập nhật: giữ nguyên createdAt và createdBy.
- Mỗi lần cập nhật: thay lastModifiedAt và lastModifiedBy.
- Cùng một query có thể được gọi lại mà không ghi đè metadata tạo ban đầu.

Ví dụ service dùng Neo4jClient:

~~~java
import java.time.ZonedDateTime;
import java.time.ZoneOffset;

import org.springframework.data.neo4j.core.Neo4jClient;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class DocumentWriter {

    private final Neo4jClient client;
    private final CurrentActor currentActor;

    public DocumentWriter(
            Neo4jClient client,
            CurrentActor currentActor
    ) {
        this.client = client;
        this.currentActor = currentActor;
    }

    @Transactional
    public String saveDocument(String id, String title) {
        String actor = currentActor.requireActor();
        ZonedDateTime now = ZonedDateTime.now(ZoneOffset.UTC);

        return client.query("""
                MERGE (d:Document {id: $id})
                ON CREATE SET
                    d.title = $title,
                    d.createdAt = $now,
                    d.createdBy = $actor,
                    d.lastModifiedAt = $now,
                    d.lastModifiedBy = $actor,
                    d.version = 0
                ON MATCH SET
                    d.title = $title,
                    d.lastModifiedAt = $now,
                    d.lastModifiedBy = $actor,
                    d.version = coalesce(d.version, 0) + 1
                RETURN d.id AS id
                """)
            .bind(id).to("id")
            .bind(title).to("title")
            .bind(now).to("now")
            .bind(actor).to("actor")
            .fetchAs(String.class)
            .one()
            .orElseThrow();
    }
}
~~~

Định nghĩa abstraction nhỏ này trong application layer:

~~~java
public interface CurrentActor {
    String requireActor();
}
~~~

CurrentActor là abstraction của ứng dụng để lấy principal đã được xác thực. Ví dụ có thể triển khai nó dựa trên Spring Security, nhưng không nên nhận actor tùy ý từ request body rồi ghi thẳng vào audit field.

Dùng ZonedDateTime theo UTC trong ví dụ để truyền một giá trị thời gian tường minh vào Neo4j. Query khởi tạo version = 0 và tăng version ở nhánh cập nhật để đồng bộ với field @Version trong entity. Query này chưa so sánh version kỳ vọng; nếu cần optimistic locking đầy đủ cho đường ghi trực tiếp, dùng mẫu kiểm tra expectedVersion ở phần 10. Nếu hệ thống chọn dùng datetime() trong Cypher, hãy thống nhất quy tắc đó trên tất cả đường ghi. Không nên để một luồng dùng clock của ứng dụng và luồng khác dùng clock của database mà không xác định rõ ý nghĩa của timestamp.

## 6. Tách actor của người dùng và actor hệ thống

Không phải thao tác ghi nào cũng xuất phát từ HTTP request. Dữ liệu có thể được cập nhật bởi:

- Scheduler chạy định kỳ.
- Batch import.
- Consumer xử lý message.
- Script bảo trì.
- Tác vụ đồng bộ từ hệ thống bên ngoài.

Trong các luồng này, SecurityContextHolder có thể không có authentication. AuditorAware có thể trả Optional.empty() nếu không tìm được principal.

Hãy quy định actor hệ thống rõ ràng, ví dụ:

| Tác nhân | Giá trị audit gợi ý |
|---|---|
| Người dùng đăng nhập | ID người dùng ổn định |
| Batch import | system:catalog-import |
| Scheduler | system:nightly-sync |
| Message consumer | service:order-consumer |
| Script vận hành | Tài khoản vận hành đã xác thực |

Nên dùng một định dạng actor thống nhất và lưu ID ổn định thay vì tên hiển thị có thể thay đổi.

Với các luồng async, message nên mang correlation ID và thông tin nguồn phát đã được xác thực. Consumer cần xác định actor từ danh tính service hoặc metadata tin cậy, không mặc nhiên tin một chuỗi actor do producer tùy ý gửi.

## 7. Bảo đảm dữ liệu nghiệp vụ và audit được ghi cùng transaction

Khi query vừa cập nhật node vừa tạo audit event, hãy thực hiện cả hai trong cùng transaction. Nếu một phần thất bại, cả thay đổi nghiệp vụ và audit event phải rollback.

Ví dụ cập nhật Document và tạo lịch sử:

~~~cypher
MATCH (d:Document {id: $id})
SET d.title = $title,
    d.lastModifiedAt = $now,
    d.lastModifiedBy = $actor
CREATE (:DocumentAuditEvent {
    eventId: $eventId,
    documentId: d.id,
    action: 'UPDATED',
    actor: $actor,
    occurredAt: $now,
    changedFields: $changedFields
})
RETURN d.id AS id
~~~

Service có thể gọi query này trong một method @Transactional. Nếu dùng Neo4jClient được cấu hình với cùng Driver và transaction infrastructure của SDN, query có thể tham gia transaction Spring đang mở.

Một số điểm cần bảo đảm:

- Tạo eventId duy nhất cho audit event.
- Truyền cùng $now và $actor cho cập nhật node và event.
- Tạo uniqueness constraint cho DocumentAuditEvent.eventId.
- Nếu không tìm thấy Document, query không tạo event.
- Nếu nghiệp vụ yêu cầu event và cập nhật node phải cùng tồn tại, hãy để chúng ở cùng transaction.

Ví dụ constraint:

~~~cypher
CREATE CONSTRAINT document_audit_event_id_unique IF NOT EXISTS
FOR (e:DocumentAuditEvent)
REQUIRE e.eventId IS UNIQUE
~~~

Nếu audit event được gửi tới message broker hoặc hệ thống log bên ngoài, hãy cân nhắc transactional outbox. Lưu outbox event cùng transaction với Document; worker gửi event sau commit. Việc gửi message trực tiếp trong transaction không làm message rollback theo Neo4j.

## 8. Audit metadata và audit history là hai mục đích khác nhau

Bốn annotation audit phổ biến chỉ biểu diễn metadata hiện tại:

| Field | Ý nghĩa |
|---|---|
| createdBy | Ai tạo entity |
| createdAt | Khi entity được tạo |
| lastModifiedBy | Ai sửa entity gần nhất |
| lastModifiedAt | Khi entity được sửa gần nhất |

Chúng không lưu toàn bộ lịch sử thay đổi.

Nếu một Document được sửa 20 lần, các field lastModifiedBy và lastModifiedAt chỉ cho biết lần gần nhất. Chúng không cho biết 19 lần trước đã thay đổi title từ gì sang gì.

Nếu cần lịch sử đầy đủ, tạo node event riêng:

~~~text
(:Document)-[:HAS_AUDIT_EVENT]->(:DocumentAuditEvent)
~~~

Một event có thể lưu:

- eventId: định danh duy nhất.
- documentId: ID tài liệu liên quan.
- action: CREATED, UPDATED hoặc DELETED.
- actor: người hoặc service thực hiện.
- occurredAt: thời điểm xảy ra.
- changedFields: danh sách field thay đổi.
- before và after: giá trị cần lưu nếu chính sách dữ liệu cho phép.

Với dữ liệu nhạy cảm, không lưu toàn bộ snapshot nếu không cần thiết. Hãy giới hạn field, thời gian lưu trữ và quyền truy cập audit history theo chính sách bảo mật.

Nếu cần audit cả relationship, hãy áp dụng hợp đồng tương tự cho relationship properties hoặc tạo event riêng chứa ID hai đầu, loại relationship, actor và thời gian. Việc cập nhật relationship bằng Cypher trực tiếp cũng không kích hoạt auditing của entity relationship properties.

## 9. Xử lý thao tác xóa

Khi xóa cứng node, metadata audit lưu trên node đó cũng bị xóa. Vì vậy, nếu cần truy vết thao tác xóa, hãy tạo audit event trước khi xóa node trong cùng transaction.

Các annotation Created/LastModified không tự tạo deletedBy, deletedAt hoặc tombstone khi gọi repository.delete(entity). Nếu cần lưu dấu vết xóa, ứng dụng phải ghi event riêng hoặc chuyển sang soft delete trước khi xóa vật lý theo chính sách lưu trữ.

~~~cypher
MATCH (d:Document {id: $id})
CREATE (:DocumentAuditEvent {
    eventId: $eventId,
    documentId: d.id,
    action: 'DELETED',
    actor: $actor,
    occurredAt: $now
})
DETACH DELETE d
RETURN $eventId AS eventId
~~~

Event giữ lại ID tài liệu và thông tin người xóa sau khi node gốc bị xóa.

Nếu nghiệp vụ cần khôi phục hoặc giữ nguyên dấu vết dữ liệu, cân nhắc soft delete:

~~~cypher
MATCH (d:Document {id: $id})
SET d.deleted = true,
    d.deletedAt = $now,
    d.deletedBy = $actor,
    d.lastModifiedAt = $now,
    d.lastModifiedBy = $actor
RETURN d.id AS id
~~~

Soft delete giữ node và audit metadata để truy vấn hoặc phục hồi theo chính sách. Hãy xác định rõ các truy vấn nghiệp vụ có phải loại bỏ node deleted = true hay không.

## 10. Dùng chung quy tắc audit giữa nhiều đường ghi

Một ứng dụng có thể có nhiều đường cập nhật cùng một loại node: repository save, custom @Query, Neo4jClient, import và batch job. Nếu mỗi nơi tự đặt tên field hoặc cách tính timestamp, dữ liệu audit sẽ không nhất quán.

Hãy định nghĩa hợp đồng dùng chung:

| Quy tắc | Giá trị thống nhất |
|---|---|
| Actor field | createdBy, lastModifiedBy |
| Time field | createdAt, lastModifiedAt |
| Timezone | UTC |
| Actor format | User ID hoặc service ID ổn định |
| Tạo mới | Ghi created và lastModified |
| Cập nhật | Giữ created, cập nhật lastModified |
| Xóa | Audit event hoặc soft delete |
| History | Event append-only nếu cần truy vết đầy đủ |

Có thể gom query vào repository fragment hoặc một service chuyên trách để các thành phần không tự viết lại logic audit. Với import ngoài ứng dụng, hãy cung cấp một hợp đồng dữ liệu và Cypher template tương đương.

Nếu một thao tác chỉ đi qua repository.save(entity), hãy để auditing của SDN thực hiện công việc. Nếu một thao tác ghi bằng Cypher trực tiếp, hãy truyền actor và thời gian rõ ràng. Tránh vừa để auditing tự cập nhật entity vừa tự gán các field tương tự trong callback mà không có thứ tự và quy tắc sở hữu rõ ràng.

Raw Cypher cũng không tự thực hiện optimistic locking của SDN. Nếu entity dùng @Version, custom query cần tự kiểm tra version mong đợi trong MATCH/WHERE và tăng version khi cập nhật; nếu không, một đường ghi trực tiếp có thể bỏ qua cơ chế phát hiện cập nhật đồng thời mà repository.save cung cấp.

Ví dụ cập nhật có kiểm tra version:

~~~cypher
MATCH (d:Document {id: $id, version: $expectedVersion})
SET d.title = $title,
    d.version = d.version + 1,
    d.lastModifiedAt = $now,
    d.lastModifiedBy = $actor
RETURN d.id AS id,
       d.version AS version
~~~

Nếu query không trả record, document có thể không tồn tại hoặc version đã thay đổi. Service cần phân biệt hai trường hợp theo nhu cầu nghiệp vụ và trả conflict khi phát hiện dữ liệu đã được cập nhật bởi transaction khác.

## 11. Kiểm thử giới hạn auditing qua các đường ghi

Cần kiểm tra riêng từng đường ghi để xác nhận nơi nào có auditing tự động và nơi nào cần gán thủ công.

### Kiểm thử entity save

Với @EnableNeo4jAuditing, lưu Document qua repository và xác nhận bốn field audit được điền theo cấu hình:

~~~java
Document saved = documents.save(
    new Document("doc-101", "Graph Basics")
);

assertThat(saved.getCreatedBy()).isEqualTo("alice");
assertThat(saved.getCreatedAt()).isNotNull();
assertThat(saved.getLastModifiedBy()).isEqualTo("alice");
assertThat(saved.getLastModifiedAt()).isNotNull();
~~~

Kết quả phụ thuộc modifyOnCreate. Nếu đặt modifyOnCreate = false, không yêu cầu các field LastModified được điền ở lần tạo đầu.

### Kiểm thử raw Cypher không tự kích hoạt auditing

Tạo node bằng Neo4jClient mà không gán audit field:

~~~java
client.query("""
        CREATE (:Document {id: $id, title: $title})
        """)
    .bind("doc-raw").to("id")
    .bind("Raw Cypher").to("title")
    .run();
~~~

Đọc trực tiếp bằng Cypher và xác nhận các field audit không tự xuất hiện. Test này chứng minh Neo4jClient không gọi entity auditing pipeline.

### Kiểm thử raw Cypher có gán audit rõ ràng

Chạy query MERGE ở phần 5 với actor và timestamp cố định. Sau đó kiểm tra:

- Lần đầu: createdBy và createdAt được ghi.
- Cập nhật lần sau: createdBy và createdAt giữ nguyên.
- lastModifiedBy và lastModifiedAt thay đổi theo lần cập nhật.
- Query lặp lại không tạo thêm node Document nếu ID là khóa duy nhất.

### Kiểm thử rollback

Trong một method @Transactional, cập nhật Document và tạo DocumentAuditEvent, sau đó cố ý ném exception. Kiểm tra cả cập nhật Document lẫn event đều không được commit.

Đừng chỉ kiểm tra Java object trả về. Hãy đọc lại property và event trực tiếp từ Neo4j để xác nhận trạng thái lưu trữ.

## 12. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| @LastModifiedDate không đổi sau custom query | Custom Cypher không chạy entity auditing | Gán lastModifiedAt trong query |
| @CreatedBy trống khi import | Import không có Spring Security principal hoặc AuditorAware context | Truyền actor hệ thống đã xác định |
| Query cập nhật làm mất createdAt | Gán lại field tạo trong mọi nhánh | Chỉ ghi created field trong nhánh tạo mới |
| Raw Cypher không có audit metadata | Không có entity save lifecycle | Thêm actor/time parameter và SET |
| @Transactional nhưng audit vẫn trống | Transaction không tự thêm metadata | Viết audit field trong query hoặc dùng entity save |
| lastModifiedAt không nhất quán | Mỗi đường ghi dùng một clock hoặc timezone khác nhau | Dùng DateTimeProvider hoặc quy tắc UTC chung |
| Audit event tồn tại nhưng cập nhật node thất bại | Event và node không cùng transaction | Gộp vào một transaction |
| Xóa node làm mất audit | Audit chỉ nằm trên node bị xóa | Ghi event riêng hoặc dùng soft delete |
| Batch job ghi actor rỗng | Không có principal người dùng | Dùng actor định danh service/job |
| Audit history chỉ có lần sửa cuối | Chỉ lưu bốn field metadata hiện tại | Tạo event history riêng |

## 13. Bài tập thực hành

Tạo entity Article có các field createdBy, createdAt, lastModifiedBy và lastModifiedAt.

Thực hiện:

1. Bật @EnableNeo4jAuditing.
2. Tạo AuditorAware<String> lấy actor từ Spring Security.
3. Lưu Article bằng repository và xác nhận metadata được điền.
4. Cập nhật Article bằng repository và xác nhận metadata sửa đổi thay đổi.
5. Viết custom @Query dùng SET để cập nhật title; kiểm tra auditing không tự chạy cho query đó.
6. Viết lại query bằng cách truyền actor và now, rồi cập nhật lastModifiedBy và lastModifiedAt.
7. Tạo một batch job dùng actor system:article-import.
8. Tạo ArticleAuditEvent cùng transaction với cập nhật Article.
9. Viết query xóa Article nhưng giữ audit event.
10. Viết integration test cho rollback, cập nhật lặp và xóa.

Câu hỏi tự kiểm tra:

- Auditing của SDN chạy ở giai đoạn nào trong quy trình lưu entity?
- Vì sao Neo4jClient không tự gọi AuditorAware?
- @Transactional có tự cập nhật lastModifiedAt không?
- Vì sao custom @Query ghi node không tự áp dụng auditing?
- Khi update bằng MERGE, cần đặt createdAt ở nhánh nào?
- Làm thế nào để audit một batch job không có người dùng đăng nhập?
- Vì sao bốn field auditing không thay thế audit history?
- Khi xóa cứng node, cần làm gì để giữ lại dấu vết thao tác?

## Kết luận

Auditing của Spring Data Neo4j hoạt động cùng quy trình lưu domain entity. Khi ứng dụng ghi graph bằng custom Cypher, Neo4jClient, Java Driver hoặc công cụ import, các annotation auditing không tự cập nhật metadata cho node và relationship bị thay đổi. @Transactional cũng chỉ quản lý commit/rollback, không tự bổ sung actor hay timestamp.

Với các đường ghi ngoài entity lifecycle, hãy truyền actor đã được xác thực và timestamp theo một quy tắc thống nhất, rồi cập nhật audit field ngay trong Cypher. Giữ created metadata ở lần tạo, chỉ thay đổi lastModified metadata khi cập nhật. Nếu cần lịch sử đầy đủ hoặc truy vết thao tác xóa, hãy ghi audit event riêng trong cùng transaction với thay đổi nghiệp vụ.

## Tài liệu tham khảo

- [Spring Data Neo4j 8.1.2 FAQ: Auditing entities và cấu hình](https://docs.spring.io/spring-data/neo4j/reference/faq.html)
- [Spring Data Neo4j: Auditing](https://docs.spring.io/spring-data/neo4j/reference/auditing.html)
- [Spring Data Neo4j: Business ID, new entity detection và @Version](https://docs.spring.io/spring-data/neo4j/reference/object-mapping/mapping-ids.html)
- [Spring Data Commons: Auditing](https://docs.spring.io/spring-data/commons/reference/auditing.html)
- [Spring Data Neo4j: Neo4jClient](https://docs.spring.io/spring-data/neo4j/reference/appendix/neo4j-client.html)
