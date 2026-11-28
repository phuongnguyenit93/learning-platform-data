# Capstone: Rà soát tính đúng dữ liệu, bảo mật và tiêu chí sẵn sàng triển khai

Bài thực hành tổng hợp này yêu cầu xây dựng và rà soát một ứng dụng Spring Data Neo4j trước khi triển khai. Bạn sẽ dùng kiến thức về node entity, relationship properties, repository, Cypher, transaction, optimistic locking, auditing, kiểm thử và vận hành để chứng minh rằng graph lưu đúng dữ liệu, người dùng chỉ truy cập được phạm vi được cấp quyền và hệ thống có thể được theo dõi, phục hồi khi có sự cố.

Capstone sử dụng một **nền tảng cộng tác tri thức theo workspace**. Người dùng thuộc một hoặc nhiều workspace; mỗi workspace chứa tài liệu; tài liệu có thể gắn tag. Thành viên có vai trò OWNER, EDITOR hoặc VIEWER. Các thao tác đọc/ghi phải tuân thủ membership của workspace.

Đây là bài thực hành có tiêu chí nghiệm thu. Bạn cần nộp thiết kế, code, kiểm thử và bằng chứng vận hành. Chỉ có ứng dụng chạy được chưa đủ để kết luận hệ thống sẵn sàng production.

## 1. Mục tiêu và phạm vi

Sau khi hoàn thành, bạn cần chứng minh được các năng lực:

1. Mô hình hóa graph đúng với nghiệp vụ workspace, membership, document và tag.
2. Duy trì tính toàn vẹn bằng ID ổn định, uniqueness constraint, validation và transaction.
3. Thực thi authorization ở mọi đường đọc/ghi, bao gồm custom Cypher.
4. Ngăn Cypher injection, lộ bí mật và truy cập chéo tenant.
5. Xử lý cập nhật đồng thời bằng optimistic locking hoặc câu lệnh Cypher nguyên tử.
6. Kiểm thử rollback, quyền truy cập, dữ liệu biên và xung đột version bằng Neo4j thật hoặc Testcontainers.
7. Theo dõi lỗi, độ trễ và dung lượng; có kế hoạch backup/restore và phát hành an toàn.

Phạm vi capstone là một service Spring Boot dùng Spring Data Neo4j imperative. Có thể mở rộng reactive sau khi hoàn thành yêu cầu bắt buộc. Chọn một phiên bản Spring Boot, SDN, Neo4j Java Driver và Neo4j server tương thích; ghi rõ phiên bản trong README.

Không cần xây giao diện web hoàn chỉnh. Một REST API nhỏ, integration tests và tài liệu vận hành là đủ để đánh giá các yêu cầu.

## 2. Bối cảnh nghiệp vụ

Một tổ chức sử dụng ứng dụng để quản lý tài liệu tri thức trong các workspace:

- Một User có thể tham gia nhiều Workspace.
- Một Workspace có nhiều thành viên với vai trò và trạng thái riêng.
- Một Workspace chứa nhiều Document.
- Một Document do một người tạo, có trạng thái DRAFT, PUBLISHED hoặc ARCHIVED.
- Một Document có thể gắn nhiều Tag.
- Thành viên chỉ được đọc tài liệu trong workspace mà họ đang là thành viên ACTIVE.
- OWNER quản lý workspace và thành viên.
- EDITOR tạo, sửa, gắn tag và lưu trữ tài liệu.
- VIEWER chỉ đọc tài liệu.

Yêu cầu đa tenant là trọng tâm. Người dùng có thể đồng thời là editor của workspace A và viewer của workspace B. Không được dùng một quyền toàn cục để thay thế quyền trong từng workspace.

## 3. Mô hình graph đề xuất

~~~text
(User)-[:MEMBER_OF {role, status, joinedAt}]->(Workspace)
(Workspace)-[:CONTAINS]->(Document)
(Document)-[:HAS_TAG]->(Tag)
~~~

Các node và relationship:

| Thành phần | Thuộc tính chính | Ràng buộc nghiệp vụ |
|---|---|---|
| User | id, email, normalizedEmail, displayName, createdAt | id và normalizedEmail duy nhất |
| Workspace | id, slug, name, createdAt | id và slug duy nhất |
| Document | id, title, body, status, createdById, createdAt, updatedAt, version | id duy nhất; title không rỗng; version do SDN quản lý; DELETED là trạng thái tùy chọn khi xóa mềm |
| Tag | id, name, normalizedName | id và normalizedName duy nhất trên toàn hệ thống trong mô hình này |
| MEMBER_OF | role, status, joinedAt | Một membership active cho mỗi cặp user/workspace |
| CONTAINS | Có thể thêm addedAt | Document thuộc workspace được chỉ định |
| HAS_TAG | Có thể thêm addedAt | Không tạo liên kết trùng cùng tag/document |

createdById là dấu vết nghiệp vụ để biết người tạo. Bạn có thể mở rộng bằng relationship AUTHORED nếu cần truy vấn graph theo tác giả, nhưng phải định nghĩa rõ hướng và quyền truy cập. Không tạo thêm relationship chỉ để lặp lại dữ liệu mà không có use case.

Ví dụ domain mapping cho membership:

~~~java
import java.time.Instant;

import org.springframework.data.neo4j.core.schema.RelationshipId;
import org.springframework.data.neo4j.core.schema.RelationshipProperties;
import org.springframework.data.neo4j.core.schema.TargetNode;

@RelationshipProperties
public class Membership {

    @RelationshipId
    private Long id;

    private String role;
    private String status;
    private Instant joinedAt;

    @TargetNode
    private Workspace workspace;

    // constructors and accessors
}
~~~

Node User sở hữu membership:

~~~java
import java.util.ArrayList;
import java.util.List;

import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;
import org.springframework.data.neo4j.core.schema.Relationship;
import org.springframework.data.neo4j.core.schema.Relationship.Direction;

@Node("User")
public class User {

    @Id
    private String id;

    private String email;
    private String normalizedEmail;
    private String displayName;

    @Relationship(type = "MEMBER_OF", direction = Direction.OUTGOING)
    private List<Membership> memberships = new ArrayList<>();

    // constructors and accessors
}
~~~

Node Document nên có @Version để phát hiện stale update:

~~~java
import java.time.Instant;

import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.LastModifiedDate;
import org.springframework.data.annotation.Version;
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Document")
public class Document {

    @Id
    private String id;

    private String title;
    private String body;
    private String status;
    private String createdById;

    @CreatedDate
    private Instant createdAt;

    @LastModifiedDate
    private Instant updatedAt;

    @Version
    private Long version;

    // constructors and accessors
}
~~~

Các đoạn code trên là khung domain để triển khai. Bổ sung constructor, accessor, validation và relationship mapping theo thiết kế thực tế. Không expose version, createdById hoặc role như field có thể được client tùy ý sửa.

## 4. Định nghĩa quyền theo workspace

Tạo một bảng quyền rõ ràng và dùng nhất quán trong service lẫn Cypher:

| Hành động | OWNER | EDITOR | VIEWER | Người không phải thành viên |
|---|:---:|:---:|:---:|:---:|
| Xem danh sách tài liệu | Có | Có | Có | Không |
| Xem chi tiết tài liệu | Có | Có | Có | Không |
| Tạo tài liệu | Có | Có | Không | Không |
| Sửa tiêu đề/nội dung | Có | Có | Không | Không |
| Gắn hoặc bỏ tag | Có | Có | Không | Không |
| Archive tài liệu | Có | Có | Không | Không |
| Thêm/xóa thành viên | Có | Không | Không | Không |
| Đổi vai trò thành viên | Có | Không | Không | Không |
| Xóa workspace | Có | Không | Không | Không |

Membership có trạng thái ACTIVE, INVITED hoặc SUSPENDED. Chỉ ACTIVE mới được phép truy cập. Nếu người dùng bị xóa khỏi workspace hoặc bị suspend, mọi request tiếp theo phải bị từ chối dù client còn giữ URL hoặc document ID. Document có thể dùng thêm trạng thái DELETED nếu chọn chính sách xóa mềm.

Không tin userId, role hoặc createdById do request body gửi lên. Lấy danh tính người dùng từ principal đã được Spring Security xác thực. Workspace ID từ URL chỉ là đối tượng cần truy cập; service vẫn phải xác minh membership trong workspace đó.

## 5. Thiết kế schema và ràng buộc

Tạo migration schema có version và chạy trước khi ứng dụng nhận traffic. Ví dụ constraint cho Neo4j hỗ trợ cú pháp này:

~~~cypher
CREATE CONSTRAINT user_id_unique IF NOT EXISTS
FOR (u:User)
REQUIRE u.id IS UNIQUE;

CREATE CONSTRAINT user_email_unique IF NOT EXISTS
FOR (u:User)
REQUIRE u.normalizedEmail IS UNIQUE;

CREATE CONSTRAINT workspace_id_unique IF NOT EXISTS
FOR (w:Workspace)
REQUIRE w.id IS UNIQUE;

CREATE CONSTRAINT workspace_slug_unique IF NOT EXISTS
FOR (w:Workspace)
REQUIRE w.slug IS UNIQUE;

CREATE CONSTRAINT document_id_unique IF NOT EXISTS
FOR (d:Document)
REQUIRE d.id IS UNIQUE;

CREATE CONSTRAINT tag_id_unique IF NOT EXISTS
FOR (t:Tag)
REQUIRE t.id IS UNIQUE;

CREATE CONSTRAINT tag_normalized_name_unique IF NOT EXISTS
FOR (t:Tag)
REQUIRE t.normalizedName IS UNIQUE;

CREATE INDEX document_status_updated_at IF NOT EXISTS
FOR (d:Document)
ON (d.status, d.updatedAt);
~~~

Trước khi tạo uniqueness constraint trên graph đang có dữ liệu, hãy truy vấn duplicate và xử lý xong. IF NOT EXISTS không tự giải quyết dữ liệu trùng. Chuẩn hóa email ở một quy tắc duy nhất (trim và lowercase theo chính sách sản phẩm) rồi lưu normalizedEmail; không dựa vào collation mặc định để so sánh email không phân biệt hoa thường. Index phải được chọn theo query thực tế và xác nhận bằng EXPLAIN/PROFILE.

Neo4j không tự áp đặt mọi quy tắc quan hệ của nghiệp vụ. Ví dụ uniqueness của node không ngăn hai relationship MEMBER_OF trùng nhau giữa cùng một user và workspace. Cần kiểm tra bằng query audit, viết thao tác idempotent và kiểm soát transaction. Nếu phiên bản/edition hỗ trợ relationship property uniqueness constraint, có thể cân nhắc khóa membership riêng; không giả định mọi edition đều hỗ trợ mọi loại constraint.

## 6. Bảo đảm membership không bị tạo trùng

Một thao tác thêm thành viên cần có tính idempotent. Nếu cùng lời mời được xử lý hai lần, không được tạo hai cạnh membership active.

Cypher minh họa:

~~~cypher
MATCH (u:User {id: $userId})
MATCH (w:Workspace {id: $workspaceId})
MERGE (u)-[m:MEMBER_OF]->(w)
ON CREATE SET
    m.role = $role,
    m.status = 'ACTIVE',
    m.joinedAt = datetime()
RETURN u.id AS userId, w.id AS workspaceId, m.role AS role;
~~~

MERGE giúp tái sử dụng relationship cùng pattern. Ví dụ cố ý không đổi role hoặc status trong ON MATCH: gửi lại một lời mời không được vô tình kích hoạt lại membership SUSPENDED. Đổi role hoặc kích hoạt lại membership phải là thao tác riêng, có xác minh quyền OWNER và kiểm tra trạng thái chuyển hợp lệ.

MERGE không phải lời hứa rằng mọi mô hình dữ liệu đều tự có uniqueness tuyệt đối khi nhiều transaction chạy đồng thời. Hãy kiểm tra khả năng uniqueness của schema, xử lý lỗi xung đột và viết integration test concurrency.

Nếu cho phép giữ lịch sử lời mời hoặc nhiều membership theo thời gian, mô hình hóa trạng thái/lịch sử rõ ràng thay vì tái sử dụng một relationship không có quy tắc.

Với thao tác tạo Document, dùng ID do server sinh và uniqueness constraint để ngăn hai node cùng ID. Nếu API hỗ trợ retry sau timeout, nhận một Idempotency-Key, lưu khóa đó cùng kết quả tạo trong một node/request record có uniqueness constraint, rồi trả lại kết quả cũ khi client gửi lại cùng khóa. Không chỉ dựa vào UUID mới được sinh ở mỗi lần retry, vì mỗi lần đó sẽ tạo một document khác.

## 7. Kiểm tra quyền ngay trong đường truy cập dữ liệu

Authorization không chỉ là kiểm tra ở controller. Mọi repository query hoặc custom Cypher truy cập tài liệu theo workspace phải gắn với actor và membership. Nếu service kiểm tra quyền ở một query rồi chạy query ghi ở một transaction khác, membership có thể thay đổi giữa hai thao tác.

Ví dụ tạo document chỉ khi actor là thành viên active có vai trò owner/editor:

~~~cypher
MATCH (actor:User {id: $actorId})-[membership:MEMBER_OF]->(workspace:Workspace {id: $workspaceId})
WHERE membership.status = 'ACTIVE'
  AND membership.role IN ['OWNER', 'EDITOR']
WITH DISTINCT workspace
CREATE (document:Document {
    id: $documentId,
    title: $title,
    body: $body,
    status: 'DRAFT',
    createdById: $actorId,
    createdAt: datetime(),
    updatedAt: datetime(),
    version: 0
})
CREATE (workspace)-[:CONTAINS]->(document)
RETURN document.id AS id;
~~~

Nếu membership không tồn tại, không active hoặc role không đủ quyền, query không trả về ID và không tạo document. Map trường hợp này thành kết quả authorization phù hợp, thường là 403 Forbidden hoặc 404 Not Found tùy chính sách chống dò tài nguyên.

Ví dụ method repository dùng query này:

~~~java
import java.util.Optional;

import org.springframework.data.neo4j.repository.query.Query;
import org.springframework.data.repository.Repository;
import org.springframework.data.repository.query.Param;

public interface DocumentCommands extends Repository<Document, String> {

    @Query("""
        MATCH (actor:User {id: $actorId})-[membership:MEMBER_OF]->(workspace:Workspace {id: $workspaceId})
        WHERE membership.status = 'ACTIVE'
          AND membership.role IN ['OWNER', 'EDITOR']
        WITH DISTINCT workspace
        CREATE (document:Document {
            id: $documentId,
            title: $title,
            body: $body,
            status: 'DRAFT',
            createdById: $actorId,
            createdAt: datetime(),
            updatedAt: datetime(),
            version: 0
        })
        CREATE (workspace)-[:CONTAINS]->(document)
        RETURN document.id AS id
        """)
    Optional<String> createForEditor(
        @Param("actorId") String actorId,
        @Param("workspaceId") String workspaceId,
        @Param("documentId") String documentId,
        @Param("title") String title,
        @Param("body") String body
    );
}
~~~

Trong service, actorId phải đến từ Spring Security principal. Không nhận actor ID từ body hoặc query parameter. Nếu một nghiệp vụ cần nhiều query, đặt các thao tác trong cùng @Transactional và thiết kế để mỗi query đều kiểm tra quyền cần thiết.

## 8. Ngăn truy cập chéo workspace

Mọi query đọc chi tiết document phải chứng minh actor là thành viên active của workspace chứa document. Không nên chỉ tìm document bằng ID:

~~~cypher
// Không đủ an toàn cho API đa tenant:
MATCH (d:Document {id: $documentId})
RETURN d;
~~~

Query đọc có membership:

~~~cypher
MATCH (actor:User {id: $actorId})-[membership:MEMBER_OF]->(workspace:Workspace {id: $workspaceId})
WHERE membership.status = 'ACTIVE'
MATCH (workspace)-[:CONTAINS]->(document:Document {id: $documentId})
WITH DISTINCT document
WHERE document.status <> 'DELETED'
RETURN document {
    .id,
    .title,
    .body,
    .status,
    .updatedAt,
    .version
} AS document;
~~~

Danh sách tài liệu cũng phải neo vào workspace và membership:

~~~cypher
MATCH (actor:User {id: $actorId})-[membership:MEMBER_OF]->(workspace:Workspace {id: $workspaceId})
WHERE membership.status = 'ACTIVE'
MATCH (workspace)-[:CONTAINS]->(document:Document)
WITH DISTINCT workspace, document
WHERE document.status IN ['DRAFT', 'PUBLISHED', 'ARCHIVED']
RETURN document.id AS id,
       document.title AS title,
       document.status AS status,
       document.updatedAt AS updatedAt
ORDER BY document.updatedAt DESC, document.id ASC
LIMIT $pageSize;
~~~

Không dùng workspaceId do client gửi làm bằng chứng quyền. Nó chỉ chọn workspace; membership query mới xác định actor có quyền.

## 9. Chống Cypher injection

Luôn bind dữ liệu người dùng thành parameter:

~~~java
client.query("""
    MATCH (d:Document {id: $id})
    SET d.title = $title
    RETURN d.id AS id
    """)
    .bind(documentId).to("id")
    .bind(title).to("title")
    .run();
~~~

Không ghép chuỗi request vào Cypher:

~~~java
// Không an toàn:
String cypher = "MATCH (d:Document {id: '" + documentId + "'}) RETURN d";
~~~

Parameter hóa giá trị không có nghĩa mọi phần cú pháp đều có thể parameterize. Label, relationship type hoặc tên property được chọn động phải đi qua allowlist trong code. Ví dụ:

~~~java
String sortProperty = switch (requestedSort) {
    case "title" -> "title";
    case "updatedAt" -> "updatedAt";
    default -> throw new IllegalArgumentException("Unsupported sort field");
};
~~~

Chỉ nối sortProperty sau khi đã chọn từ allowlist cố định của ứng dụng. Không cho client gửi trực tiếp tên label, relationship type hoặc đoạn ORDER BY.

## 10. Tách xác thực, phân quyền ứng dụng và quyền database

Ba lớp bảo vệ có mục đích khác nhau:

- **Authentication** xác định người gọi là ai, ví dụ JWT được Spring Security xác minh.
- **Authorization ứng dụng** xác định người đó được làm gì trong workspace cụ thể.
- **Database privileges** giới hạn những thao tác mà tài khoản kết nối Neo4j được phép thực hiện.

Tài khoản database của ứng dụng nên có quyền tối thiểu cần thiết trên database và graph được phép truy cập. Không dùng tài khoản admin/superuser trong runtime. Tài khoản migration có thể có quyền cao hơn nhưng chỉ dùng trong pipeline triển khai được kiểm soát.

Không dựa vào việc database user của ứng dụng là cùng một tài khoản cho mọi request để suy ra quyền người dùng cuối. Neo4j không tự biết JWT principal của ứng dụng; service phải thực thi authorization bằng query và business logic.

## 11. Quản lý bí mật và kết nối an toàn

Không commit password, private key, JWT signing secret hoặc credential của Neo4j vào repository.

Yêu cầu tối thiểu:

- Lấy credential từ secret manager hoặc environment được quản lý an toàn.
- Không log connection URI có chứa credential.
- Dùng TLS khi kết nối qua mạng không tin cậy; xác minh certificate theo cấu hình môi trường.
- Xoay vòng credential theo quy trình và kiểm tra ứng dụng có thể nhận secret mới.
- Dùng database/role riêng cho môi trường dev, test, staging và production.
- Giới hạn network ingress tới Bolt port, chỉ cho phép application network và operator được cấp quyền.
- Không expose Bolt trực tiếp ra internet công cộng.

Ví dụ cấu hình tham chiếu bằng biến môi trường:

~~~yaml
spring:
  neo4j:
    uri: <NEO4J_URI>
    authentication:
      username: <NEO4J_USERNAME>
      password: <SECRET_FROM_SECRET_MANAGER>
~~~

Không ghi giá trị secret thật trong file cấu hình được commit. Bảo đảm log khi khởi động không in password hoặc token.

## 12. Tính đúng của document và optimistic locking

Hai editor có thể cùng tải một document rồi sửa gần như đồng thời. Nếu không có cơ chế phát hiện stale update, người lưu sau có thể ghi đè nội dung của người lưu trước.

Dùng @Version trên entity:

~~~java
@Version
private Long version;
~~~

SDN tăng version khi lưu thành công. Nếu object mang version cũ, SDN phát hiện xung đột và ném OptimisticLockingFailureException. API có thể chuyển lỗi này thành 409 Conflict và yêu cầu client tải lại dữ liệu.

Không tự tăng version trong service. Nếu custom Cypher ghi trực tiếp document, hãy dùng compare-and-set với version dự kiến:

~~~cypher
MATCH (actor:User {id: $actorId})-[membership:MEMBER_OF]->(workspace:Workspace {id: $workspaceId})
WHERE membership.status = 'ACTIVE'
  AND membership.role IN ['OWNER', 'EDITOR']
MATCH (workspace)-[:CONTAINS]->(d:Document {id: $documentId})
WHERE d.version = $expectedVersion
WITH DISTINCT d
SET d.title = $title,
    d.body = $body,
    d.version = d.version + 1,
    d.updatedAt = datetime()
RETURN d.version AS version;
~~~

Không có record trả về nghĩa là document không tồn tại hoặc version không còn khớp. Nếu API cần phân biệt hai trường hợp, thực hiện kiểm tra bổ sung có authorization trong cùng transaction. Không trộn một custom query tự tăng version với repository.save() trên cùng object nếu chưa định nghĩa rõ bên nào quản lý version.

Trong ví dụ custom Cypher, version được cập nhật thủ công vì lệnh này bỏ qua quy trình save của SDN. Nếu dùng repository.save() với entity có @Version, để SDN quản lý version và không chạy thêm phép tăng version bằng Cypher cho cùng một lần cập nhật.

## 13. Transaction cho thao tác nhiều bước

Tạo document, liên kết workspace và ghi sự kiện nghiệp vụ phải là một đơn vị nhất quán. Nếu một bước thất bại, không được để document mồ côi.

Ví dụ service:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class DocumentService {

    private final DocumentCommands commands;
    private final AuditWriter auditWriter;
    private final CurrentActor currentActor;

    public DocumentService(
            DocumentCommands commands,
            AuditWriter auditWriter,
            CurrentActor currentActor) {
        this.commands = commands;
        this.auditWriter = auditWriter;
        this.currentActor = currentActor;
    }

    @Transactional
    public String create(
            String workspaceId,
            String documentId,
            String title,
            String body) {

        String actorId = currentActor.requireUserId();

        String createdId = commands.createForEditor(
            actorId, workspaceId, documentId, title, body
        ).orElseThrow(AccessDeniedOrWorkspaceUnavailableException::new);

        auditWriter.recordDocumentCreated(actorId, workspaceId, createdId);
        return createdId;
    }
}
~~~

AuditWriter trong ví dụ phải dùng cùng Spring-managed Neo4j infrastructure để tham gia transaction hiện tại. Nếu ghi audit sang hệ thống ngoài, thao tác đó không rollback cùng Neo4j; dùng transactional outbox hoặc sự kiện AFTER_COMMIT.

Không gọi dịch vụ thanh toán, email hoặc HTTP bên ngoài trong khi đang giữ transaction graph nếu không cần thiết. Giữ transaction ngắn và xác định rõ thao tác nào phải nguyên tử.

## 14. Kiểm soát xóa và tính toàn vẹn quan hệ

Không xóa workspace bằng một câu DETACH DELETE rộng mà chưa xác định chính sách lưu trữ tài liệu. Chọn một chính sách:

- Xóa mềm workspace và chặn mọi truy cập mới.
- Archive tài liệu rồi xóa membership.
- Xóa cứng theo quy trình được audit, backup và xác nhận.

Trước khi xóa hoặc archive:

1. Xác minh actor là OWNER active.
2. Kiểm tra các dependency hoặc retention policy.
3. Thực hiện thay đổi trong transaction.
4. Ghi audit event phù hợp.
5. Xác minh không còn relationship mồ côi theo mô hình.

Nếu xóa mềm, thống nhất cách lọc trạng thái trong mọi query. Một query bỏ quên điều kiện status <> 'DELETED' có thể làm tài liệu đã xóa xuất hiện trở lại.

## 15. Auditing và dấu vết thao tác

Document cần có createdAt, updatedAt, createdById và version. Bổ sung audit log cho thao tác quan trọng:

- Ai tạo, sửa, archive hoặc khôi phục tài liệu.
- Workspace và document bị tác động.
- Thời điểm và loại hành động.
- Request/correlation ID để liên kết log ứng dụng.

Để các annotation auditing hoạt động khi ghi qua repository/template, bật auditing trong cấu hình:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.neo4j.config.EnableNeo4jAuditing;

@Configuration
@EnableNeo4jAuditing
public class Neo4jAuditingConfiguration {
}
~~~

Các câu Cypher ghi trực tiếp không tự chạy auditing callback; chúng phải đặt timestamp và actor property cần thiết trong query như ví dụ tạo document ở trên.

Không lưu nội dung bí mật, token, password hoặc toàn bộ body nhạy cảm vào audit log. Audit cần đủ để điều tra nhưng không biến thành kho dữ liệu nhạy cảm thứ hai.

Nếu cần audit không thể sửa bởi người dùng ứng dụng, dùng role database hạn chế quyền ghi/xóa audit hoặc gửi sự kiện tới hệ thống log append-only phù hợp. Không dựa vào một label Audit đơn thuần để bảo đảm bất biến.

## 16. Bộ integration test bắt buộc

Chạy test với Neo4j Testcontainers hoặc Neo4j Test Harness tương thích với phiên bản ứng dụng. Không dùng mock repository để chứng minh Cypher, constraint, transaction hoặc mapping.

Các nhóm test:

| Nhóm | Kịch bản | Kết quả mong đợi |
|---|---|---|
| Mapping | Lưu User, Workspace, Membership và đọc lại | Đúng label, type, direction, role và status |
| Constraint | Tạo hai user cùng email | Lần ghi vi phạm uniqueness bị từ chối |
| Authorization | Viewer tạo document | Bị từ chối, graph không đổi |
| Authorization | User không thuộc workspace đọc document | Không nhận được nội dung |
| Tenant isolation | Editor workspace A đoán ID document workspace B | Không đọc hoặc sửa được |
| Membership | Thành viên bị suspend rồi gọi API | Bị từ chối ngay request tiếp theo |
| Injection | Title chứa chuỗi giống Cypher | Chỉ được lưu như dữ liệu, không thay đổi cấu trúc graph |
| Transaction | Lỗi sau khi tạo document nhưng trước audit hoàn tất | Không còn document hoặc relationship dở dang |
| Concurrency | Hai editor lưu cùng version | Một cập nhật thắng; cập nhật stale nhận conflict |
| Idempotency | Gửi lại cùng request tạo membership | Không tạo relationship trùng |
| Pagination | Tạo nhiều document cùng timestamp | Thứ tự ổn định, không lặp hoặc bỏ sót giữa trang |
| Soft delete | Đọc danh sách sau khi archive/delete mềm | Tài liệu không xuất hiện ở endpoint không phù hợp |

Với test slice @DataNeo4jTest, nhớ rằng transaction imperative của test có thể rollback khi test kết thúc. Khi cần kiểm tra transaction riêng của service, tắt test-managed transaction bằng Propagation.NOT_SUPPORTED và gọi service qua Spring proxy. Với reactive, dùng ReactiveTransactionManager/TransactionalOperator và StepVerifier.

## 17. Kiểm thử authorization theo ma trận

Tạo fixture có ít nhất:

- User A là OWNER của workspace A.
- User B là EDITOR của workspace A.
- User C là VIEWER của workspace A.
- User D không phải thành viên workspace A.
- User B đồng thời là VIEWER của workspace B.
- Một membership có trạng thái SUSPENDED.

Kiểm tra các cặp actor/action/resource. Đặc biệt, kiểm tra User B không được dùng quyền editor ở workspace A để sửa tài liệu trong workspace B. Đây là lỗi confused-deputy thường xuất hiện khi service chỉ kiểm tra role toàn cục.

Với mỗi request bị từ chối, xác minh cả HTTP status và graph state. Không chỉ assert exception; cần chứng minh không có node, property hoặc relationship nào bị ghi một phần.

## 18. Kiểm thử Cypher injection và dữ liệu đầu vào

Thử các giá trị:

- Dấu nháy đơn và kép.
- Dấu ngoặc, dấu gạch chéo và ký tự Unicode.
- Chuỗi có đoạn Cypher như chuỗi đóng nháy, theo sau bởi DETACH DELETE.
- Chuỗi rất dài vượt giới hạn nghiệp vụ.
- Sort field hoặc filter field không nằm trong allowlist.
- ID sai định dạng hoặc rỗng.

Kết quả đúng là dữ liệu được xử lý theo validation và parameter binding; không câu lệnh nào ngoài ý định được thực thi. Đặt giới hạn độ dài title/body/tag ở tầng API/domain, không chỉ trông chờ database.

Không dùng chuỗi tấn công phá hoại trên database dùng chung. Chạy test injection trong database test riêng, tạo fixture có thể xóa và xác minh graph sau test.

## 19. Kiểm tra dữ liệu trước khi phát hành

Viết các query audit để tìm dữ liệu không hợp lệ:

Tài liệu không thuộc workspace nào:

~~~cypher
MATCH (d:Document)
WHERE NOT EXISTS {
    MATCH (:Workspace)-[:CONTAINS]->(d)
}
RETURN d.id AS documentId;
~~~

Membership trùng giữa cùng user và workspace:

~~~cypher
MATCH (u:User)-[m:MEMBER_OF]->(w:Workspace)
WITH u, w, count(m) AS relationshipCount
WHERE relationshipCount > 1
RETURN u.id AS userId,
       w.id AS workspaceId,
       relationshipCount;
~~~

Document thuộc nhiều workspace trong khi nghiệp vụ chỉ cho phép một workspace:

~~~cypher
MATCH (w:Workspace)-[:CONTAINS]->(d:Document)
WITH d, collect(DISTINCT w.id) AS workspaceIds
WHERE size(workspaceIds) > 1
RETURN d.id AS documentId, workspaceIds;
~~~

Tài liệu có người tạo không tồn tại:

~~~cypher
MATCH (d:Document)
WHERE d.createdById IS NOT NULL
  AND NOT EXISTS {
      MATCH (:User {id: d.createdById})
  }
RETURN d.id AS documentId, d.createdById AS createdById;
~~~

Tag không còn được dùng:

~~~cypher
MATCH (t:Tag)
WHERE NOT EXISTS {
    MATCH (:Document)-[:HAS_TAG]->(t)
}
RETURN t.id AS tagId, t.name AS name;
~~~

Các query trên là ví dụ cho mô hình đã chọn. Nếu quy tắc nghiệp vụ cho phép document chưa thuộc workspace hoặc tag chưa được dùng, hãy điều chỉnh báo cáo thay vì coi mọi kết quả là lỗi. Lưu kết quả audit cùng thời điểm chạy và quyết định xử lý.

## 20. Hiệu năng và giới hạn tài nguyên

Trước khi release:

- Kiểm tra query list/detail bằng EXPLAIN và PROFILE với dữ liệu gần thực tế.
- Xác minh index được dùng cho các predicate quan trọng.
- Giới hạn page size ở server; không tin giá trị do client yêu cầu.
- Tránh trả toàn bộ graph khi endpoint chỉ cần DTO.
- Tránh collect() hoặc collectList() không giới hạn với graph lớn.
- Đặt timeout hợp lý cho request và query.
- Kiểm tra connection pool, acquisition timeout và số replica ứng dụng.
- Đo p50/p95/p99 và memory trong tải thường lẫn tải đỉnh.

Ví dụ phân trang ổn định, có kiểm tra membership:

~~~cypher
MATCH (actor:User {id: $actorId})-[membership:MEMBER_OF]->(workspace:Workspace {id: $workspaceId})
WHERE membership.status = 'ACTIVE'
MATCH (workspace)-[:CONTAINS]->(d:Document)
WHERE d.status = 'PUBLISHED'
  AND (
      $afterUpdatedAt IS NULL
      OR d.updatedAt < $afterUpdatedAt
      OR (d.updatedAt = $afterUpdatedAt AND d.id > $afterId)
  )
RETURN d.id AS id,
       d.title AS title,
       d.updatedAt AS updatedAt
ORDER BY d.updatedAt DESC, d.id ASC
LIMIT $pageSize;
~~~

Ví dụ trên chỉ cho phép mọi thành viên active đọc tài liệu đã publish. Cursor nên được encode/validate để client không thể thay đổi điều kiện phân trang tùy ý. Giới hạn pageSize ở server và kiểm tra quyền trước khi truy cập workspace.

## 21. Observability và xử lý sự cố

Ứng dụng phải phát ra log có cấu trúc và metric đủ để trả lời:

- Request nào chậm, endpoint nào thường lỗi?
- Query nào chiếm nhiều thời gian?
- Có bao nhiêu lỗi authorization, validation, constraint hoặc optimistic lock?
- Pool có thường xuyên hết kết nối hoặc chờ lâu không?
- Có dấu hiệu tăng heap, queue hoặc transaction duration không?
- Release mới có làm thay đổi latency hoặc error rate không?

Gắn requestId/trace ID vào log. Ghi actor ID và workspace ID khi chính sách dữ liệu cho phép, nhưng không ghi token, password hoặc document body nhạy cảm. Phân biệt lỗi 401, 403/404, 409, 422, 429 và 5xx để dashboard không gộp mọi lỗi thành một nhóm.

Health check cần xác minh ứng dụng có thể phục vụ request và kết nối database theo chính sách triển khai. Readiness nên loại instance khỏi traffic khi dependency bắt buộc không sẵn sàng; liveness không nên restart liên tục chỉ vì một lỗi query tạm thời.

## 22. Backup, restore và khôi phục sau sự cố

Backup chỉ có giá trị khi đã thử restore. Tài liệu vận hành cần nêu:

- Cơ chế backup phù hợp với phiên bản Neo4j, edition và kiến trúc triển khai.
- Lịch backup, thời gian lưu, vị trí lưu và người chịu trách nhiệm.
- Mã hóa dữ liệu backup và quyền truy cập.
- RPO (mức mất dữ liệu tối đa chấp nhận được) và RTO (thời gian khôi phục mục tiêu).
- Cách restore vào môi trường cô lập để kiểm tra tính toàn vẹn.
- Quy trình xác nhận ứng dụng hoạt động sau restore.

Không sao chép thư mục data đang chạy như một backup tùy tiện. Dùng công cụ backup được hỗ trợ cho phiên bản Neo4j đang vận hành và tuân thủ hướng dẫn edition/cluster. Không ghi credential hoặc bản backup chứa dữ liệu thật vào repository code.

## 23. Migration schema và phát hành an toàn

Schema migration cần có version, được review và có log trạng thái. Trước migration:

1. Backup và xác nhận khả năng restore.
2. Kiểm tra duplicate hoặc dữ liệu vi phạm constraint.
3. Ước lượng thời gian tạo index/constraint.
4. Chạy migration trên staging với dữ liệu tương đương.
5. Kiểm tra tương thích giữa schema mới và phiên bản ứng dụng cũ đang chạy.

Ưu tiên chiến lược expand-contract:

- **Expand:** thêm property/label/relationship mới theo cách ứng dụng cũ vẫn chạy được.
- **Migrate:** backfill dữ liệu theo batch có thể tiếp tục sau lỗi.
- **Switch:** triển khai ứng dụng mới đọc/ghi schema mới.
- **Contract:** chỉ xóa cấu trúc cũ sau khi mọi instance và consumer cũ đã ngừng sử dụng.

Không gộp thay đổi schema phá hủy và release ứng dụng trong một bước không thể khôi phục. Nếu migration không thể rollback, phải có forward-fix hoặc restore plan được phê duyệt trước.

## 24. Tiêu chí nghiệm thu capstone

Capstone chỉ được coi là đạt khi các tiêu chí bắt buộc dưới đây có bằng chứng:

| Mã | Tiêu chí | Bằng chứng |
|---|---|---|
| D1 | Domain graph đúng label, type, direction và relationship properties | Entity mapping và integration test |
| D2 | ID, normalized email, workspace slug và normalized tag name có uniqueness constraint | Migration Cypher và test duplicate |
| D3 | Không tạo membership trùng qua request lặp | Idempotency test |
| D4 | Tài liệu luôn gắn với workspace theo quy tắc | Transaction test và query audit |
| S1 | Mọi endpoint đọc/ghi kiểm tra membership active | Authorization matrix test |
| S2 | Role được kiểm tra theo từng workspace | Test chéo workspace |
| S3 | Query bind parameter, sort/filter động có allowlist | Code review và injection test |
| S4 | Secret không nằm trong source/log; database role tối thiểu | Config mẫu, secret policy và role review |
| T1 | Rollback loại bỏ toàn bộ thay đổi trong nghiệp vụ lỗi | Integration test |
| T2 | Stale update bị phát hiện | Optimistic locking test |
| T3 | API trả lỗi nhất quán cho conflict/validation/authorization | API test |
| O1 | Có health/readiness, log và metric thiết yếu | Dashboard hoặc mẫu log/metric |
| O2 | Query quan trọng có kế hoạch và latency đo được | EXPLAIN/PROFILE và kết quả load test |
| O3 | Có backup/restore runbook và bằng chứng restore | Biên bản restore thử |
| R1 | Schema migration có version và tương thích rollout | Migration scripts và release notes |
| R2 | Có hướng rollback/forward-fix và xác định RPO/RTO | Runbook triển khai |

## 25. Thang điểm gợi ý

| Hạng mục | Điểm |
|---|---:|
| Mô hình graph, ID, constraint và tính toàn vẹn | 20 |
| Authorization, tenant isolation và Cypher safety | 25 |
| Transaction, optimistic locking và idempotency | 15 |
| Integration test và bằng chứng kiểm thử | 15 |
| Hiệu năng, observability và quản lý tài nguyên | 10 |
| Backup/restore, migration và release readiness | 15 |
| **Tổng** | **100** |

Các lỗi sau là điều kiện không đạt dù tổng điểm cao:

- Người dùng không phải thành viên đọc được tài liệu của workspace khác.
- Viewer có thể tạo hoặc sửa tài liệu.
- Query có thể bị injection qua dữ liệu đầu vào.
- Một nghiệp vụ lỗi để lại document hoặc relationship dở dang.
- Credential production được commit vào source.
- Không có backup có thể restore hoặc không có cách phục hồi sau migration lỗi.

## 26. Sản phẩm cần nộp

Tổ chức kết quả capstone thành các artifact:

1. **README:** mục tiêu, phiên bản công nghệ, cách chạy local/test và sơ đồ kiến trúc.
2. **Domain model:** node, relationship properties, ID strategy và quy tắc ownership.
3. **Schema migrations:** constraint, index và các bước backfill có version.
4. **Application code:** repository, custom query, service transaction, security và API.
5. **Test suite:** mapping, constraint, authorization, injection, rollback, concurrency và pagination.
6. **Security review:** threat model ngắn, quyền database, secret/TLS và log redaction.
7. **Operations runbook:** health, metrics, backup/restore, migration, deploy và incident response.
8. **Release evidence:** test report, EXPLAIN/PROFILE, kết quả load test và checklist nghiệm thu.

## 27. Kế hoạch thực hiện theo thứ tự

1. Vẽ graph model và viết các invariant nghiệp vụ.
2. Tạo schema migration, constraint và fixture dữ liệu.
3. Implement entity, relationship properties và repository.
4. Implement authentication principal và workspace authorization.
5. Viết query list/detail/create/update có parameter binding.
6. Thêm transaction, auditing, optimistic locking và idempotency.
7. Viết integration test trên Neo4j test instance.
8. Chạy query audit và xử lý dữ liệu sai.
9. Đo hiệu năng, cấu hình giới hạn và bổ sung observability.
10. Thử backup/restore, diễn tập release và hoàn thiện runbook.

Không chuyển sang bước triển khai production khi các tiêu chí chặn phát hành trong phần nghiệm thu còn thất bại.

## 28. Câu hỏi tự đánh giá

- Nếu user bị suspend khi đang mở màn hình document, request tiếp theo được xử lý thế nào?
- Nếu client đoán được ID document của workspace khác, query nào ngăn truy cập?
- Nếu hai editor cùng lưu một version, API phản hồi gì và người dùng khôi phục thay đổi thế nào?
- Nếu tạo document thành công nhưng ghi audit thất bại, graph còn trạng thái dở dang không?
- Nếu request gửi lại sau timeout, làm sao tránh tạo membership hoặc document trùng?
- Nếu một Cypher query trả về domain entity thiếu relationship rồi code gọi save(), có thể xảy ra điều gì?
- Nếu index migration thất bại vì duplicate hiện có, quy trình xử lý và tiếp tục release ra sao?
- Nếu backup gần nhất bị hỏng, bằng chứng nào cho thấy hệ thống có thể phục hồi?
- Bạn sẽ quan sát chỉ số nào để phân biệt query chậm với pool acquisition timeout?
- Quyền nào cần thiết cho runtime database user và quyền nào chỉ migration pipeline mới được có?

## 29. Nguyên tắc hoàn thành

- Mọi node và relationship đều có ý nghĩa nghiệp vụ, ownership và hướng rõ ràng.
- Constraint bảo vệ tính duy nhất; validation và transaction bảo vệ các invariant còn lại.
- Mọi query truy cập dữ liệu tenant đều xác minh actor và membership.
- Client không quyết định actor ID, role hoặc cú pháp Cypher.
- Transaction ngắn, atomic và có kiểm thử rollback.
- Cập nhật cạnh tranh được phát hiện hoặc thực hiện bằng phép toán nguyên tử.
- Test chạy trên Neo4j thực tế tương thích, không chỉ mock repository.
- Log và metric đủ để phát hiện lỗi mà không làm lộ dữ liệu nhạy cảm.
- Backup đã được restore thử; migration và release có kế hoạch phục hồi.

Một ứng dụng Spring Data Neo4j sẵn sàng triển khai khi tính đúng của graph, quyền truy cập, khả năng phục hồi và bằng chứng vận hành đều được kiểm chứng. Capstone này kết thúc bằng một quyết định release dựa trên tiêu chí nghiệm thu và dữ liệu kiểm thử, thay vì chỉ dựa vào việc ứng dụng khởi động thành công.

## Tài liệu tham khảo

- [Spring Data Neo4j – Object Mapping and Schema](https://docs.spring.io/spring-data/neo4j/reference/object-mapping/metadata-based-mapping.html)
- [Spring Data Neo4j – Repository Queries and Custom Cypher](https://docs.spring.io/spring-data/neo4j/reference/appendix/query-creation.html)
- [Spring Data Neo4j – Transactions](https://docs.spring.io/spring-data/neo4j/reference/transactions.html)
- [Spring Data Neo4j – Optimistic Locking and Version Properties](https://docs.spring.io/spring-data/neo4j/reference/object-mapping/metadata-based-mapping.html)
- [Neo4j Cypher Manual – Parameters](https://neo4j.com/docs/cypher-manual/current/syntax/parameters/)
- [Neo4j Operations Manual – Authentication and Authorization](https://neo4j.com/docs/operations-manual/current/authentication-authorization/)
- [Neo4j Operations Manual – Backup and Restore](https://neo4j.com/docs/operations-manual/current/backup-restore/)
- [Neo4j Operations Manual – Monitoring](https://neo4j.com/docs/operations-manual/current/monitoring/)
- [Spring Security – OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
