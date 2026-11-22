# GraphQL dùng chung endpoint: bảo vệ resolver, đối tượng và trường dữ liệu

## 1. Vì sao đây là một lỗ hổng authorization dễ bị bỏ sót?

Với REST, ứng dụng thường có các URL riêng cho từng tài nguyên và hành động. GraphQL thường nhận nhiều loại truy vấn và đột biến (mutation) qua **cùng một endpoint** như `POST /graphql`. Bảo vệ URL đó bằng `requestMatchers("/graphql").authenticated()` chỉ xác nhận người gọi đã đăng nhập; nó **không chứng minh** họ có quyền gọi từng operation, xem từng đối tượng hay đọc từng trường được yêu cầu.

Ví dụ, hai request sau đều đi vào cùng endpoint nhưng cần quyền khác nhau:

```graphql
query {
  document(id: "101") {
    id
    title
  }
}
```

```graphql
mutation {
  archiveDocument(id: "101") {
    status
  }
}
```

Một query còn có thể truy xuất các trường nhạy cảm sâu bên trong:

```graphql
query {
  document(id: "101") {
    id
    title
    internalNotes
  }
}
```

Nếu hệ thống chỉ kiểm tra “đã đăng nhập” ở `/graphql` rồi trả nguyên đối tượng trong resolver, người dùng có thể vượt qua cấp quyền bằng cách yêu cầu ID của người khác hoặc thêm trường nhạy cảm vào selection set. Đây là **Broken Object Level Authorization (BOLA/IDOR)** và **Broken Object Property Level Authorization (BOPLA)** trong bối cảnh GraphQL.

Bài này tập trung vào ba câu hỏi bắt buộc:

1. **Resolver/operation:** người dùng có được gọi hành động đang thực thi không?
2. **Đối tượng:** người dùng có được đọc/sửa **bản ghi cụ thể** được chọn theo ID, quan hệ hoặc danh sách không?
3. **Trường dữ liệu:** trong đối tượng hợp lệ, người dùng có được xem **trường cụ thể** (ví dụ `internalNotes`, giá nội bộ, PII, token, trạng thái duyệt) không?

Ba câu hỏi có thể cho ba câu trả lời khác nhau. Có quyền `DOC_READ` không đồng nghĩa có quyền `DOC_ARCHIVE`; có quyền đọc tài liệu 101 không đồng nghĩa được đọc tài liệu 102; có quyền đọc tiêu đề 101 không đồng nghĩa được đọc ghi chú nội bộ của nó.

## 2. Tình huống xuyên suốt và chính sách mẫu

Giả sử bảng `documents` có hai bản ghi:

| id | owner_username | title | internal_notes | archived |
| --- | --- | --- | --- | --- |
| 101 | alice | Hợp đồng A | `Alice secret` | false |
| 102 | bob | Hợp đồng B | `Bob secret` | false |

Các quyền ứng dụng:

- `DOC_READ`: được sử dụng chức năng đọc tài liệu; **chỉ đọc đối tượng thuộc sở hữu** (chính sách của ví dụ).
- `DOC_NOTE_READ`: bổ sung quyền đọc `internalNotes` **của đối tượng đã được phép xem**.
- `DOC_ARCHIVE`: được sử dụng thao tác archive; vẫn phải kiểm tra chủ sở hữu tại lúc ghi.

Với actor `alice`, kết quả mong đợi:

| Thao tác | Quyền của alice | Kết quả |
| --- | --- | --- |
| Đọc tiêu đề 101 | `DOC_READ` | Thành công |
| Đọc tiêu đề 102 | `DOC_READ` | Không trả dữ liệu bản ghi |
| Đọc `internalNotes` của 101 | Chỉ `DOC_READ` | Không trả ghi chú, có lỗi cấp quyền ở field |
| Đọc `internalNotes` của 101 | `DOC_READ` + `DOC_NOTE_READ` | Trả `Alice secret` |
| Archive 101 | `DOC_ARCHIVE` | Cập nhật 101 |
| Archive 102 | `DOC_ARCHIVE` | Không cập nhật 102 |

Đây là policy minh họa theo owner. Ứng dụng thật có thể sử dụng tenant, ACL, role ở từng dự án, quan hệ thành viên hay trạng thái workflow. Khi đó thay điều kiện owner bằng **bộ quyết định quyền thực tế của domain**, không dùng quyền toàn cục để thay thế.

**Bất biến bảo mật:** trường dữ liệu chỉ được tiết lộ nếu actor vừa được phép truy cập đối tượng, vừa được phép truy cập trường; mutation chỉ được ghi khi actor có quyền hành động **và** quyền với đối tượng tại thời điểm ghi.

## 3. GraphQL thực thi những gì trong một request?

Một GraphQL document có thể chứa nhiều trường gốc, alias, fragment và nhánh lồng nhau. Mỗi trường được chọn có thể kích hoạt một data fetcher/resolver.

```graphql
query MixedAccess {
  own: document(id: "101") {
    id
    title
    internalNotes
  }
  foreign: document(id: "102") {
    id
    title
    internalNotes
  }
}
```

`own` và `foreign` chỉ là **alias của client**, không phải hai endpoint khác nhau. Một policy kiểm tra chuỗi tên operation hoặc regex tìm `document`, `internalNotes` trong HTTP body rất dễ sai với alias, fragment, biến (variables), nhiều operation, trường lồng nhau và schema thay đổi.

Luồng xử lý phù hợp với Spring MVC + Spring for GraphQL:

```text
POST /graphql
   │
   ├─ Spring Security FilterChain: authentication / CSRF / HTTP policy
   │
   └─ GraphQL parse + validate + execute
       ├─ Query.document(id: 101) ──► quyền DOC_READ + đối tượng 101
       │                               └─ Document.internalNotes ──► DOC_NOTE_READ + 101
       └─ Query.document(id: 102) ──► quyền DOC_READ + đối tượng 102 (deny)
```

Điểm quan trọng: **một URL, nhiều quyết định authorization**. Bảo vệ query gốc là cần thiết nhưng chưa đủ nếu cùng kiểu `Document` còn có thể đến từ `search`, `project.documents`, `user.documents`, `node(id:)`, DataLoader hoặc subscription. Policy nằm ở **service/domain layer** phải được tái sử dụng qua mọi đường đi.

## 4. Bốn lớp kiểm soát bổ sung cho nhau

| Lớp | Bảo vệ điều gì? | Ví dụ | Nếu bỏ sót |
| --- | --- | --- | --- |
| HTTP/transport | Chỉ identity hợp lệ mới vào GraphQL endpoint (và chính sách CSRF/token) | `/graphql` yêu cầu authentication | Người lạ có thể vào API |
| Resolver/service operation | Quyền gọi chức năng | `@PreAuthorize("hasAuthority('DOC_ARCHIVE')")` | User đọc được nhưng cũng sửa được |
| Object/domain | Quyền trên từng ID, từng tenant, quan hệ | `WHERE id = ? AND owner_username = ?` | BOLA: đọc/sửa bản ghi người khác |
| Field/property | Quyền trên dữ liệu nhạy cảm của object được phép | `DOC_NOTE_READ` + owner cho `internalNotes` | BOPLA: lộ dữ liệu trong object hợp lệ |

Một lớp không thay cho lớp khác. Ví dụ `@PreAuthorize("hasAuthority('DOC_READ')")` trên `Query.document` chỉ xác nhận quyền chức năng. **ID 102 vẫn phải bị chặn** bằng predicate truy cập đối tượng; trường `internalNotes` lại có thể cần quyền hẹp hơn.

Đừng cho client tự gửi `ownerUsername` hay `tenantId` rồi tin đó là danh tính được phép. Actor phải lấy từ authentication do server xác thực. Tại tầng service, nên ràng buộc actor được truyền vào với `authentication.name` để lời gọi nội bộ không thể giả danh bằng một chuỗi tùy ý.

## 5. GraphQL schema và hợp đồng trả kết quả

Tệp `src/main/resources/graphql/schema.graphqls`:

```graphql
type Query {
  document(id: ID!): Document
}

type Mutation {
  archiveDocument(id: ID!): ArchiveResult!
}

type Document {
  id: ID!
  title: String!
  internalNotes: String
}

type ArchiveResult {
  status: ArchiveStatus!
}

enum ArchiveStatus {
  ARCHIVED
  NOT_PROCESSED
}
```

Chủ ý thiết kế:

- `document` **nullable**: khi ID không tồn tại hoặc caller không được xem, ví dụ trả `null` giống nhau; tránh tạo kênh đoán sự tồn tại của tài liệu.
- `internalNotes` **nullable**: nếu không được phép, field có thể nhận `null` kèm một GraphQL error đã làm sạch. Nếu đánh dấu `String!`, lỗi hoặc `null` sẽ lan lên (*null bubbling*) và có thể khiến cả object hoặc nhiều dữ liệu cha thành `null`.
- `archiveDocument` trả `NOT_PROCESSED` cho ID không tồn tại, không thuộc actor hoặc không cần đổi trạng thái. Đó là một contract cụ thể để hạn chế phân biệt nguyên nhân thất bại; hệ thống khác có thể chọn lỗi `FORBIDDEN` nếu đã đánh giá rủi ro tiết lộ.
- Không khai báo `owner_username` hoặc `internal_notes` thô ở schema. **GraphQL schema không tự kiểm tra quyền**; nó xác định những field có thể hỏi, còn resolver/service mới quyết định những giá trị được trả.

Ví dụ response cho truy vấn hỗn hợp của `alice` với cả `DOC_READ` và `DOC_NOTE_READ`:

```json
{
  "data": {
    "own": {
      "id": "101",
      "title": "Hợp đồng A",
      "internalNotes": "Alice secret"
    },
    "foreign": null
  }
}
```

Nếu `alice` chỉ có `DOC_READ` và hỏi `internalNotes` ở tài liệu 101, response dạng sau là **minh họa**, không phải chuỗi lỗi mặc định cố định của Spring GraphQL:

```json
{
  "data": {
    "document": {
      "id": "101",
      "title": "Hợp đồng A",
      "internalNotes": null
    }
  },
  "errors": [
    {
      "message": "Access denied",
      "path": ["document", "internalNotes"]
    }
  ]
}
```

Phải kiểm soát loại lỗi, message và `extensions` theo hợp đồng bảo mật; không trả stack trace, câu SQL, tên owner/tenant hoặc ghi chú nhạy cảm vào lỗi.

## 6. Spring Boot và Spring Security: triển khai mẫu

Ví dụ dùng **Java 17+, Spring Boot 3.x, Spring MVC, Spring for GraphQL, Spring Security 6, Spring JDBC**. Đây là các tệp trong **một ứng dụng Spring Boot** có DataSource và database phù hợp, không phải chương trình độc lập chạy bằng `javac`. Phụ thuộc chính: `spring-boot-starter-graphql`, `spring-boot-starter-web`, `spring-boot-starter-security`, `spring-boot-starter-jdbc` và JDBC driver. Test dùng `spring-boot-starter-test` + `spring-security-test`.

### 6.1. Xác thực ở URL và bật method security

Tệp `GraphQlSecurityConfig.java`:

```java
package com.example.demo.graphql;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class GraphQlSecurityConfig {

    @Bean
    SecurityFilterChain graphqlSecurity(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/graphql").authenticated()
                .anyRequest().denyAll());
        return http.build();
    }
}
```

`@EnableMethodSecurity` là bắt buộc để `@PreAuthorize` hoạt động trong ví dụ. `authenticated()` tại `/graphql` chặn người chưa đăng nhập ở transport; các service bên dưới mới quyết định quyền operation, object và field.

Ví dụ cố ý giữ **CSRF mặc định của Spring Security**. Với ứng dụng dùng session/cookie, request POST cần CSRF token; test MockMvc sẽ gửi `csrf()`. Với API dùng bearer token stateless, chính sách CSRF có thể khác và cần được cấu hình có chủ đích. Mã trên giả định đã có cơ chế authentication cấp authority thực (không tự tạo người dùng/tài khoản).

### 6.2. DTO chỉ chứa trường cơ bản và schema result

Tệp `DocumentView.java`:

```java
package com.example.demo.graphql;

public record DocumentView(String id, String title) {
    public String getId() { return id; }
    public String getTitle() { return title; }
}
```

Tệp `ArchiveResult.java`:

```java
package com.example.demo.graphql;

enum ArchiveStatus {
    ARCHIVED, NOT_PROCESSED
}

public record ArchiveResult(ArchiveStatus status) {
    public ArchiveStatus getStatus() { return status; }
}
```

DTO không chứa `internalNotes`. Chỉ `@SchemaMapping` cho field này mới tải và trả dữ liệu sau khi qua service kiểm tra quyền. Những getter kiểu JavaBean ở trên giúp GraphQL Java xử lý các trường `id`, `title`, `status` một cách rõ ràng.

**Lưu ý giới hạn:** DTO an toàn ở đường `document(id)` chỉ khi resolver cha đã trả object được cấp quyền. Nếu sau này thêm đường `project.documents` hay `search`, phải dùng cùng service/predicate để lọc object trước khi trả; không giả định DTO tự thực thi authorization.

### 6.3. Repository đặt điều kiện quyền ngay ở truy vấn

Tệp `DocumentRepository.java`:

```java
package com.example.demo.graphql;

import java.util.List;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class DocumentRepository {
    private final JdbcTemplate jdbc;

    public DocumentRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public DocumentView findVisible(long id, String actor) {
        List<DocumentView> rows = jdbc.query("""
                SELECT id, title
                  FROM documents
                 WHERE id = ?
                   AND owner_username = ?
                """,
                (rs, rowNum) -> new DocumentView(
                        Long.toString(rs.getLong("id")),
                        rs.getString("title")),
                id, actor);
        return rows.isEmpty() ? null : rows.get(0);
    }

    public String findNotesIfOwned(long id, String actor) {
        List<String> rows = jdbc.query("""
                SELECT internal_notes
                  FROM documents
                 WHERE id = ?
                   AND owner_username = ?
                """,
                (rs, rowNum) -> rs.getString("internal_notes"),
                id, actor);
        return rows.isEmpty() ? null : rows.get(0);
    }

    public int archiveIfOwned(long id, String actor) {
        return jdbc.update("""
                UPDATE documents
                   SET archived = TRUE
                 WHERE id = ?
                   AND owner_username = ?
                   AND archived = FALSE
                """, id, actor);
    }
}
```

Dấu `?` là tham số bind của `JdbcTemplate`; giá trị ID và actor không được nối chuỗi vào SQL. Quan trọng hơn, **cả đọc, đọc trường nhạy cảm và ghi** đều giới hạn bởi `owner_username`. Kết quả `0` dòng cập nhật nghĩa là không có bản ghi nào thỏa điều kiện; không thể suy ra chắc chắn là “không tồn tại” hay “không có quyền”.

Trong hệ thống nhiều tenant phải thêm `tenant_id = ?` theo tenant xác thực; với ACL phức tạp phải thay predicate bằng quy tắc quyền thực và cân nhắc conditional write/locking để tránh thời gian giữa kiểm tra và cập nhật (*TOCTOU*).

### 6.4. Service là nơi tái sử dụng quyền cho mọi đường vào

Tệp `DocumentAccessService.java`:

```java
package com.example.demo.graphql;

import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class DocumentAccessService {
    private final DocumentRepository repository;

    public DocumentAccessService(DocumentRepository repository) {
        this.repository = repository;
    }

    @PreAuthorize("hasAuthority('DOC_READ') and #actor == authentication.name")
    public DocumentView visible(long id, @P("actor") String actor) {
        return repository.findVisible(id, actor);
    }

    @PreAuthorize("""
            hasAuthority('DOC_READ') and
            hasAuthority('DOC_NOTE_READ') and
            #actor == authentication.name
            """)
    public String internalNotes(long id, @P("actor") String actor) {
        return repository.findNotesIfOwned(id, actor);
    }

    @Transactional
    @PreAuthorize("hasAuthority('DOC_ARCHIVE') and #actor == authentication.name")
    public ArchiveResult archive(long id, @P("actor") String actor) {
        int affected = repository.archiveIfOwned(id, actor);
        return new ArchiveResult(
                affected == 1
                        ? ArchiveStatus.ARCHIVED
                        : ArchiveStatus.NOT_PROCESSED);
    }
}
```

`@P("actor")` đảm bảo Spring Security tìm được tên tham số trong biểu thức SpEL dù compiler chưa bật `-parameters`. Biểu thức `#actor == authentication.name` từ chối một lời gọi service cố truyền tên người dùng khác. Predicate SQL **vẫn cần giữ** để bảo vệ từng ID và tránh tin nhầm `hasAuthority` là quyền trên mọi tài liệu.

Các service phải là Spring-managed beans và được gọi qua proxy để `@PreAuthorize` có hiệu lực; gọi `this.internalNotes(...)` từ phương thức khác trong cùng instance có thể bỏ qua method interception. Cần thiết kế điểm kiểm tra quyền ở service/domain để batch resolver, worker hoặc service khác cũng đi qua.

### 6.5. Resolver gọi service; field nhạy cảm có resolver riêng

Tệp `DocumentGraphQlController.java`:

```java
package com.example.demo.graphql;

import java.security.Principal;
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.MutationMapping;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.graphql.data.method.annotation.SchemaMapping;
import org.springframework.stereotype.Controller;

@Controller
public class DocumentGraphQlController {
    private final DocumentAccessService access;

    public DocumentGraphQlController(DocumentAccessService access) {
        this.access = access;
    }

    @QueryMapping
    public DocumentView document(
            @Argument String id, Principal principal) {
        return access.visible(positiveId(id), principal.getName());
    }

    @SchemaMapping(typeName = "Document", field = "internalNotes")
    public String internalNotes(
            DocumentView source, Principal principal) {
        return access.internalNotes(
                positiveId(source.id()), principal.getName());
    }

    @MutationMapping
    public ArchiveResult archiveDocument(
            @Argument String id, Principal principal) {
        return access.archive(positiveId(id), principal.getName());
    }

    private static long positiveId(String raw) {
        try {
            long id = Long.parseLong(raw);
            if (id <= 0) {
                throw new NumberFormatException("Non-positive ID");
            }
            return id;
        } catch (NumberFormatException ex) {
            throw new IllegalArgumentException("Invalid document ID", ex);
        }
    }
}
```

`Principal` là tham số handler được Spring for GraphQL hỗ trợ khi có security context. `@QueryMapping` dành cho field của kiểu `Query`; `@MutationMapping` dành cho `Mutation`; `@SchemaMapping(typeName="Document", field="internalNotes")` được gọi khi client **chọn** field đó. Tải `internalNotes` tại resolver riêng làm rõ vị trí kiểm tra quyền, đồng thời tránh tải ghi chú trong query thông thường.

**Không nhầm lẫn:** `@SchemaMapping` chỉ nối handler với GraphQL field; bản thân annotation không cấp quyền. Quyền xuất phát từ `DocumentAccessService.internalNotes`. Những trường nhạy cảm khác cần quy tắc tương ứng.

## 7. Kiểm thử HTTP GraphQL bằng MockMvc: quyền và dữ liệu

GraphQL chạy trên HTTP nhưng **không đồng nhất lỗi field với HTTP 403**. Nếu Spring Security filter chặn trước khi GraphQL xử lý, HTTP có thể là `401`/`403` hoặc redirect tùy authentication entry point. Nếu request đi qua filter và một resolver/service bị từ chối, GraphQL thường trả response có `errors`, đồng thời có thể có `data` từng phần, với HTTP `200` theo cách triển khai transport. Vì vậy test cần kiểm tra **cấu trúc GraphQL response, dữ liệu nhạy cảm không xuất hiện và database không đổi**.

Ví dụ test tích hợp dùng `MockMvc` đi qua SecurityFilterChain và GraphQL endpoint. Giả định cấu hình datasource test đã tạo bảng:

```sql
CREATE TABLE documents (
    id BIGINT PRIMARY KEY,
    owner_username VARCHAR(80) NOT NULL,
    title VARCHAR(200) NOT NULL,
    internal_notes VARCHAR(500),
    archived BOOLEAN NOT NULL
);
```

Tệp `DocumentGraphQlAuthorizationIT.java` (đặt cùng package):

```java
package com.example.demo.graphql;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.Arrays;
import java.util.Map;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.ResultActions;
import org.springframework.test.web.servlet.request.RequestPostProcessor;

import static org.assertj.core.api.Assertions.assertThat;
import static org.hamcrest.Matchers.nullValue;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class DocumentGraphQlAuthorizationIT {

    @Autowired MockMvc mvc;
    @Autowired JdbcTemplate jdbc;
    @Autowired ObjectMapper mapper;

    @BeforeEach
    void seed() {
        jdbc.update("DELETE FROM documents WHERE id IN (101, 102)");
        jdbc.update("""
                INSERT INTO documents
                (id, owner_username, title, internal_notes, archived)
                VALUES (?, ?, ?, ?, FALSE)
                """, 101L, "alice", "Hợp đồng A", "Alice secret");
        jdbc.update("""
                INSERT INTO documents
                (id, owner_username, title, internal_notes, archived)
                VALUES (?, ?, ?, ?, FALSE)
                """, 102L, "bob", "Hợp đồng B", "Bob secret");
    }

    private RequestPostProcessor alice(String... authorities) {
        GrantedAuthority[] roles = Arrays.stream(authorities)
                .map(SimpleGrantedAuthority::new)
                .toArray(GrantedAuthority[]::new);
        return user("alice").authorities(roles);
    }

    private ResultActions graphQl(
            String document, RequestPostProcessor identity)
            throws Exception {
        return mvc.perform(post("/graphql")
                .with(identity)
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content(mapper.writeValueAsString(
                        Map.of("query", document))));
    }

    private boolean archived(long id) {
        return Boolean.TRUE.equals(jdbc.queryForObject(
                "SELECT archived FROM documents WHERE id = ?",
                Boolean.class, id));
    }

    @Test
    void aliasCannotBypassObjectAuthorization() throws Exception {
        String query = """
                query {
                  own: document(id: "101") { id title internalNotes }
                  other: document(id: "102") { id title internalNotes }
                }
                """;

        graphQl(query, alice("DOC_READ", "DOC_NOTE_READ"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.data.own.id").value("101"))
            .andExpect(jsonPath("$.data.own.internalNotes")
                    .value("Alice secret"))
            .andExpect(jsonPath("$.data.other").value(nullValue()))
            .andExpect(jsonPath("$.errors").doesNotExist());
    }

    @Test
    void documentReadDoesNotGrantPrivateField() throws Exception {
        String query = """
                { document(id: "101") { id title internalNotes } }
                """;

        String body = graphQl(query, alice("DOC_READ"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.data.document.title")
                    .value("Hợp đồng A"))
            .andExpect(jsonPath("$.data.document.internalNotes")
                    .value(nullValue()))
            .andExpect(jsonPath("$.errors").isArray())
            .andReturn().getResponse().getContentAsString();

        assertThat(body).doesNotContain("Alice secret", "Bob secret");
    }

    @Test
    void mutationCannotModifyForeignObject() throws Exception {
        String mutation = """
                mutation {
                  archiveDocument(id: "102") { status }
                }
                """;

        graphQl(mutation, alice("DOC_ARCHIVE"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.data.archiveDocument.status")
                    .value("NOT_PROCESSED"));

        assertThat(archived(101L)).isFalse();
        assertThat(archived(102L)).isFalse();
    }

    @Test
    void missingMutationAuthorityCausesErrorAndNoWrite()
            throws Exception {
        String mutation = """
                mutation {
                  archiveDocument(id: "101") { status }
                }
                """;

        graphQl(mutation, alice("DOC_READ"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.errors").isArray());

        assertThat(archived(101L)).isFalse();
    }
}
```

Kết quả mong đợi khi chạy test trong ứng dụng đã có DataSource, schema và cấu hình Spring Security tương ứng: cả bốn test thành công. Đây không phải bằng chứng đã chạy trong mọi dự án; khác biệt về error resolver, status transport, GraphQL starter và authentication entry point có thể cần cập nhật assertion nhưng **không được nới lỏng bất biến không rò rỉ/không sửa sai**.

Lưu ý tại test thứ hai: `internalNotes: String` nullable nên lỗi method security có thể chỉ làm field thành `null` và xuất hiện `errors`. Nếu hệ thống có `DataFetcherExceptionResolver` tùy biến để trả `null` im lặng thì test phải kiểm tra hợp đồng thực tế; việc không có một chuỗi secret trong response và không có field trái phép mới là điều cốt lõi.

### Kiểm thử nhanh bằng HTTP với biến GraphQL

Request hợp lệ minh họa (đã có credential tin cậy và chính sách CSRF/token tương ứng):

```http
POST /graphql HTTP/1.1
Content-Type: application/json

{
  "query": "query GetDoc($id: ID!) { document(id: $id) { id title internalNotes } }",
  "variables": { "id": "101" },
  "operationName": "GetDoc"
}
```

Dùng variables giúp tách input khỏi document và tái sử dụng query; **không biến variables thành nguồn đáng tin**. ID, quyền truy cập object, tenant và field vẫn phải được xác minh phía server.

## 8. Java 17 thuần: kiểm chứng bất biến không phụ thuộc GraphQL framework

Đoạn nhỏ sau mô phỏng ba quyết định (chức năng, object, field). Nó **không mở HTTP endpoint hay thực thi GraphQL**, mà chỉ giúp đối chiếu logic riêng lẻ trước khi chạy integration test.

Tệp `GraphQlAuthorizationDemo.java`:

```java
import java.util.Map;

public class GraphQlAuthorizationDemo {
    record Doc(long id, String owner, String title, String note) {}
    record Actor(String name, boolean read, boolean noteRead) {}

    static Doc resolveDocument(
            Map<Long, Doc> db, Actor actor, long id) {
        if (!actor.read()) {
            throw new SecurityException("No document-read authority");
        }
        Doc found = db.get(id);
        return found != null && found.owner().equals(actor.name())
                ? found : null;
    }

    static String resolveNotes(Actor actor, Doc source) {
        if (source == null || !actor.read() || !actor.noteRead()) {
            return null;
        }
        return source.owner().equals(actor.name())
                ? source.note() : null;
    }

    public static void main(String[] args) {
        Map<Long, Doc> db = Map.of(
                101L, new Doc(101, "alice", "A", "Alice secret"),
                102L, new Doc(102, "bob", "B", "Bob secret"));
        Actor basic = new Actor("alice", true, false);
        Actor privileged = new Actor("alice", true, true);

        System.out.println("own=" +
                resolveDocument(db, basic, 101L).title());
        System.out.println("foreign=" +
                resolveDocument(db, basic, 102L));
        System.out.println("notes-basic=" +
                resolveNotes(basic, resolveDocument(db, basic, 101L)));
        System.out.println("notes-privileged=" +
                resolveNotes(privileged,
                        resolveDocument(db, privileged, 101L)));
    }
}
```

Chạy bằng Java 17 trở lên:

```bash
javac GraphQlAuthorizationDemo.java
java GraphQlAuthorizationDemo
```

Stdout chính xác:

```text
own=A
foreign=null
notes-basic=null
notes-privileged=Alice secret
```

Khác biệt cần nhớ: ở mô hình Java thuần, field không có quyền trả `null` mà không phát sinh GraphQL error. Trong ví dụ Spring, `@PreAuthorize` từ chối bằng exception; GraphQL có thể đưa lỗi vào `errors`. Cả hai là lựa chọn contract khác nhau, miễn bảo vệ dữ liệu.

## 9. Những điểm tấn công đặc thù GraphQL phải kiểm thử

### 9.1. Đường truy cập lồng nhau, alias và fragment

Một object không chỉ xuất hiện qua `Query.document(id:)`. Ví dụ:

```graphql
query {
  project(id: "P1") {
    members {
      documents {
        id
        title
        internalNotes
      }
    }
  }
}
```

Nếu `project.members.documents` dùng repository khác và không kiểm tra actor theo từng tài liệu, dữ liệu của Bob có thể bị lộ dù `Query.document` đã được bảo vệ. **Mọi đường dẫn tới cùng loại object cần dùng chung policy domain.** Trong schema có interface/union, phải xem cả subtype, fragment, inline fragment và các field resolver của từng type. Alias làm thay đổi tên response chứ không làm thay đổi quyền.

### 9.2. N+1, @BatchMapping và DataLoader

`@BatchMapping`/DataLoader giảm số lần truy vấn nhưng **không miễn trừ authorization**. Với batch ID `[101,102]`, một query tải cả hai rồi trả toàn bộ map cho client có thể làm lộ 102. Batch loader phải áp dụng predicate có actor/tenant đáng tin cậy, trả `null` hoặc bỏ key không được phép theo contract, và không để cache của user A tái sử dụng nhầm cho user B.

Chỉ dùng cache DataLoader theo **request** hoặc khóa cache có đủ identity/scope; cân nhắc invalidation khi permission thay đổi. Với loader bất đồng bộ, bảo đảm SecurityContext/GraphQLContext được truyền qua thread/reactive context đúng cách. Không lấy `SecurityContextHolder` của một thread bất kỳ rồi giả định đó luôn là actor của request trong `@Async` hoặc custom executor.

### 9.3. Ghi qua mutation và tác dụng phụ

`Mutation` có thể tạo, sửa, xóa, gán owner hoặc thêm member. Kiểm tra quyền **trước mutation**, và ưu tiên update có điều kiện, transaction hoặc optimistic locking để tránh TOCTOU. Test cần đọc lại database và kiểm tra audit/event/queue. Một mutation trả GraphQL error không đảm bảo không có câu lệnh ghi nào đã commit.

Không để một trường có vẻ chỉ đọc (query) gọi service tạo side effect. Cần giới hạn kích thước request/batch, xác minh từng ID và không tin danh sách đối tượng “được phép” do client gửi.

### 9.4. Subscriptions, WebSocket và async

Đối với subscription, authentication lúc mở kết nối **chưa đủ** khi mỗi event chứa dữ liệu của nhiều đối tượng. Cần kiểm tra quyền khi đăng ký và bảo vệ dữ liệu trong luồng event, nhất là khi quyền có thể đổi sau lúc subscribe. Nếu hệ thống dùng WebSocket, xử lý context người dùng và cách chấm dứt luồng sau thu hồi quyền là quyết định kiến trúc phải kiểm thử.

### 9.5. Độ sâu, độ phức tạp và introspection

GraphQL cho phép hỏi nhiều alias, quan hệ lặp và nested fields; nguy cơ **DoS/chi phí truy vấn cao** là vấn đề bổ sung cho authorization. Có thể giới hạn độ sâu, độ phức tạp, số alias, page size, timeout và rate limit. Introspection giúp người dùng hiểu schema nhưng việc tắt introspection chỉ giảm khả năng khám phá, **không thay kiểm tra quyền**. Persisted queries/allowlist giúp khống chế request surface nhưng cũng không thay object/field authorization.

## 10. Ma trận test tối thiểu cho GraphQL authorization

| Ca kiểm thử | Điều cần kiểm tra |
| --- | --- |
| Chưa xác thực ở `/graphql` | HTTP filter chặn theo entry point cấu hình; không có data nhạy cảm |
| Authenticated nhưng thiếu `DOC_READ` | Query bị từ chối ở service; không rò rỉ object |
| Có `DOC_READ`, ID của mình | Đúng object và chỉ field công khai |
| Có `DOC_READ`, ID người khác | Trả `null`/lỗi đã chọn; không lộ title, note, owner |
| Có `DOC_READ` nhưng không `DOC_NOTE_READ` | `internalNotes` không lộ, kể cả khi title đọc được |
| Có cả quyền đọc và note | Chỉ trả ghi chú của object actor được phép |
| Có `DOC_ARCHIVE`, mutate ID người khác | Không có update, không event thành công |
| Không có `DOC_ARCHIVE` | Không update dù ID thuộc actor |
| Alias + fragment + nested relation | Không mở được đường vòng tới object/field bị chặn |
| Multiple operations/variables | `operationName` và variables không thay đổi quyết định quyền |
| Batch/DataLoader/caching | Không trộn kết quả giữa user/tenant hoặc ID allow/deny |
| Hệ thống đổi quyền giữa request | Không tiếp tục trả/ghi vượt quyền theo contract đã công bố |
| Field bị deny nhưng schema đánh dấu `!` | Test null bubbling và dữ liệu/error cuối cùng |
| Lỗi trong transaction / xử lý async | Dữ liệu, audit, queue và rollback đúng chính sách |
| Query quá sâu/alias quá nhiều | Query bị giới hạn tài nguyên theo cấu hình, không DoS |

Mỗi test cần fixture độc lập với actor, owner/tenant, authorities, các ID được phép/bị từ chối và các trường nhạy cảm có giá trị rõ ràng để phát hiện rò rỉ. Nếu test chỉ assert HTTP `200`, `403` hoặc chỉ mock return JSON cố định, nó chưa chứng minh authorization tại repository/database.

## 11. Sai lầm thường gặp, nguyên nhân và cách sửa

1. **“Đã bảo vệ `/graphql` nên toàn bộ GraphQL an toàn.”** HTTP chỉ quyết định quyền vào endpoint; bổ sung method security và domain policy trong từng đường xử lý.
2. **“`@PreAuthorize` ở query gốc là đủ.”** Resolver cha có thể trả object hợp lệ nhưng nested field hoặc mutation khác cần quyền riêng; kiểm tra object và field trong service tái sử dụng.
3. **“Schema không có field nhạy cảm thì chắc chắn an toàn.”** Các field hiện có vẫn có thể lộ PII; schema thay đổi có thể vô tình công khai getter của entity. Dùng DTO hạn chế trường và review schema/resolver mới.
4. **“Lấy entity rồi để GraphQL tự map tất cả getter.”** Default property fetcher có thể truy cập thuộc tính mà developer không định bảo vệ bằng resolver riêng. Trả projection tối thiểu, thêm data fetcher/permission rõ cho trường nhạy cảm.
5. **“Chỉ kiểm tra ID ở query đầu.”** Một object còn đến từ search, node, relation, subscription và batch; mọi đường phải cùng policy.
6. **“User đã có DOC_READ nên được xem mọi ID.”** `hasAuthority` là quyền chức năng, không phải row-level permission. Đưa actor/tenant/ACL vào chính truy vấn.
7. **“Dùng client-supplied tenant/owner để lọc.”** User có thể giả owner/tenant; lấy từ authentication và ràng buộc actor trong service.
8. **“Lỗi GraphQL phải luôn là HTTP 403.”** Từ chối tại resolver có thể trả HTTP 200 + `errors` + `data` từng phần; test đúng mức GraphQL.
9. **“Trả `null` là luôn an toàn.”** Một số lỗi, `extensions` hoặc thời gian phản hồi có thể tiết lộ sự tồn tại của object; rà soát response và domain policy.
10. **“Batch/loader cache là tối ưu vô hại.”** Cache lẫn identity hoặc không lọc từng ID có thể gây lộ dữ liệu xuyên user/tenant.
11. **“Tắt introspection là đủ để bảo mật GraphQL.”** Attacker vẫn có thể gửi query biết trước hoặc đoán schema; authorization phải ở server.
12. **“Trả lỗi rồi thì không có ghi.”** Mutation có thể đã commit hay phát event; assert trạng thái và side effects sau request.

## 12. Bài tập tự kiểm tra và tiêu chí hoàn thành

**Bài tập A — BOLA:** tạo query có hai alias `own` và `foreign` trả về các ID 101/102. Với actor Alice có `DOC_READ`, chứng minh 101 có title nhưng 102 không có dữ liệu. Lặp lại query qua một quan hệ lồng nhau như `project.documents` để chắc chắn không có đường vòng.

**Bài tập B — BOPLA:** với cùng object 101, so sánh response khi actor có và không có `DOC_NOTE_READ`. Xác minh secret không xuất hiện trong `data`, `errors`, extensions hoặc log response khi bị từ chối. Thử schema `String!` và quan sát null bubbling để hiểu ảnh hưởng của non-null field.

**Bài tập C — mutation:** thử archive 102 với quyền `DOC_ARCHIVE`; assert database và sự kiện nghiệp vụ không thay đổi. Thử 101 để chứng minh đường được phép vẫn hoạt động. Lặp lại khi không có quyền chức năng.

**Tiêu chí nghiệm thu:** có authentication thật trong test context, quyết định cấp quyền ở resolver/service được kích hoạt, mọi ID được kiểm tra ở domain/data layer, field nhạy cảm có policy riêng, response lỗi đã được làm sạch, không có side effect trái phép, và những đường GraphQL khác tới cùng đối tượng không đi vòng qua policy. Khi thêm resolver, @BatchMapping, query tìm kiếm hoặc subscription, bổ sung ca kiểm thử tương ứng **trước khi xem đó là một đường truy cập an toàn**.

## Tài liệu tham khảo

- Spring for GraphQL — Security: https://docs.spring.io/spring-graphql/reference/security.html
- Spring for GraphQL — Annotated Controllers và @BatchMapping: https://docs.spring.io/spring-graphql/reference/controllers.html
- Spring for GraphQL — Testing: https://docs.spring.io/spring-graphql/reference/testing.html
- Spring Security — Method Security và @PreAuthorize: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- GraphQL — Authorization: https://graphql.org/learn/authorization/
- GraphQL — Serving over HTTP: https://graphql.org/learn/serving-over-http/
