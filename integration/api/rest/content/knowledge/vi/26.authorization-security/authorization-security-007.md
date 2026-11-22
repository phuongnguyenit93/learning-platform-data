# Validation, parameterized query và phòng chống injection

## 1. Bài toán: đầu vào hợp lệ chưa chắc là truy vấn an toàn

API **GET /api/orders?status=CREATED&q=...&sort=createdAt** ghép trực tiếp **q** vào WHERE và **sort** vào ORDER BY. Nếu dữ liệu người dùng được diễn giải thành **cú pháp SQL**, có thể dẫn tới truy vấn vượt phạm vi, thay đổi câu lệnh hoặc hỏng dữ liệu.

Chặn dấu nháy không đủ và có thể chặn tên hợp lệ. **PreparedStatement** bind giá trị nhưng **không bind được tên cột hoặc hướng ORDER BY**. Cần **validation, binding và allowlist cú pháp động**.

Bài thuộc chương **Phân quyền và an toàn**, module **INTEGRATION_API_REST**, liên hệ resource/URI, HTTP methods/status, dữ liệu, pagination, cache, idempotency, OpenAPI, security, lỗi và Java/Spring. Trọng tâm là **từ HTTP input tới DB an toàn**.

**Mục tiêu:**

- Phân biệt **kiểm tra dữ liệu**, **tham số hóa truy vấn**, **allowlist cú pháp động** và **encoding tại nơi xuất dữ liệu**.
- Thiết kế validation cho path/query/body, business rules và ràng buộc DB với lỗi HTTP nhất quán.
- Viết truy vấn Java/Spring bằng **PreparedStatement, NamedParameterJdbcTemplate, JPA parameters** mà không nối dữ liệu người dùng vào SQL.
- Xử lý an toàn **LIKE**, **ORDER BY**, danh sách **IN**, tenant scope và lỗi DB.
- Kiểm thử injection, quyền truy cập và giới hạn tài nguyên trên stack thật.

## 2. Threat model và ba ranh giới tin cậy

~~~mermaid
flowchart LR
    C["Client: path/query/header/JSON"] --> H["HTTP parser + DTO validation"]
    H --> S["Service: business rules + authorization"]
    S --> R["Repository: SQL cấu trúc cố định + bound values"]
    R --> D[("Database: least-privilege account")]
    H --> E["Problem Details"]
    S --> E
    R --> E
~~~

**Dữ liệu ngoài trust boundary đều chưa đáng tin**: URL, JSON, header, webhook, CSV hay cả dữ liệu lưu từ trước. Authentication **không** biến input thành cú pháp SQL đáng tin.

| Lớp | Điều cần kiểm soát | Nếu bỏ qua |
| --- | --- | --- |
| **HTTP parsing / DTO** | Kiểu, độ dài, miền giá trị, format, kích thước request. | Input bất thường gây lỗi, tốn tài nguyên hoặc vượt contract. |
| **Service / domain** | Quan hệ giữa các field, trạng thái, actor, tenant, quota, ownership. | BOLA, mass assignment, tạo dữ liệu trái quy tắc dù SQL an toàn. |
| **Repository / DB** | Bind values, allowlist identifiers, transaction, DB privileges, constraints. | SQL injection, query sai tenant, race/vi phạm invariant. |

**Validation không thay binding**, kể cả dữ liệu đã validate. **Binding không thay authorization**: thiếu tenant condition vẫn lộ dữ liệu. **HTML escaping không thay SQL binding**.

### 2.1. Injection là lỗi lẫn lộn dữ liệu và cú pháp

Ví dụ không an toàn:

~~~java
String sql = "SELECT id FROM orders WHERE note = '"
        + requestNote + "'";
~~~

Với **x' OR '1'='1**, dữ liệu đã bị chèn thành cú pháp truy vấn.

Thay bằng dấu giữ chỗ và binding:

~~~java
String sql = "SELECT id FROM orders WHERE note = ?";
PreparedStatement statement = connection.prepareStatement(sql);
statement.setString(1, requestNote);
~~~

Driver bind requestNote thành **value**, kể cả dấu nháy/Unicode; không tự escape SQL bằng cách sửa chuỗi.

## 3. Input validation theo hợp đồng REST

### 3.1. Kiểm tra đúng thứ cần kiểm tra

| Input | Ví dụ ràng buộc | Tầng |
| --- | --- | --- |
| **Path ID** | UUID hợp lệ, resource tồn tại/được phép truy cập. | MVC binder + service. |
| **status** | Chỉ CREATED, PAID, CANCELLED. | Enum/allowlist DTO. |
| **q** | Không null nếu bắt buộc; dài tối đa 80 ký tự; cho phép ký tự tên/ghi chú hợp lệ. | DTO validation; SQL LIKE binding riêng. |
| **limit** | Số nguyên 1–100. | DTO/Bean Validation + query LIMIT bound. |
| **sort/direction** | Cột công khai và ASC/DESC do server định nghĩa. | Enum allowlist trước khi tạo ORDER BY. |
| **totalMinorUnit** | >= 0, thuộc miền số và luật nghiệp vụ. | Bean Validation + service + DB CHECK. |
| **tenant/order owner** | Khớp danh tính và quyền thực tế. | Security + service/repository. |

**Ba tầng:** syntactic (JSON, UUID, enum, độ dài), semantic (trạng thái, currency, ownership) và invariant/concurrency (unique, CHECK, transaction, optimistic locking).

Không áp regex chỉ cho chữ/số lên mọi field; Unicode, dấu nháy và gạch có thể hợp lệ. **Validate theo nghiệp vụ, không blacklist ký tự**.

### 3.2. Bean Validation cho JSON body

~~~java
import java.util.UUID;
import jakarta.validation.constraints.*;

record CreateOrderRequest(
        @NotNull UUID customerId,
        @NotNull @PositiveOrZero Long totalMinorUnit,
        @Size(max = 200) String note) {}

record OrderDto(UUID id, String status, long totalMinorUnit) {}
~~~

**Long** cho phép phân biệt missing field với 0; @NotNull, @PositiveOrZero, @Size kiểm hình dạng nhưng **không kiểm quyền với customerId**.

### 3.3. Spring MVC controller xử lý query + body

~~~java
import java.net.URI;
import java.util.UUID;
import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

enum OrderStatus { CREATED, PAID, CANCELLED }
enum SortField { createdAt, totalMinorUnit }
enum SortDirection { asc, desc }

record OrderSearch(
        @NotNull OrderStatus status,
        @Size(max = 80) String q,
        @NotNull SortField sort,
        @NotNull SortDirection direction,
        @Min(1) @Max(100) int limit) {}

interface OrdersService {
    java.util.List<OrderDto> searchAuthorized(
            String actor, OrderSearch search);
    OrderDto createAuthorized(String actor, CreateOrderRequest command);
}

@RestController
@RequestMapping("/api/orders")
class OrdersController {
    private final OrdersService orders;
    OrdersController(OrdersService orders) { this.orders = orders; }

    @GetMapping
    java.util.List<OrderDto> list(
            @Valid @ModelAttribute OrderSearch search,
            java.security.Principal principal) {
        return orders.searchAuthorized(principal.getName(), search);
    }

    @PostMapping
    ResponseEntity<OrderDto> create(
            @Valid @RequestBody CreateOrderRequest input,
            java.security.Principal principal) {
        OrderDto result = orders.createAuthorized(
                principal.getName(), input);
        return ResponseEntity.created(
                URI.create("/api/orders/" + result.id())).body(result);
    }
}
~~~

**Mẫu Spring Boot 3/Spring MVC** cần starter-validation, service/repository, advice và Security. @ModelAttribute bind enum để loại sort sai; @Valid kiểm command object.

**@Valid không phải authorization**: service phải lấy actor/tenant từ authentication và kiểm quyền với customerId/resource.

### 3.4. Validation kết thúc ở đâu?

Giới hạn thêm **body size, multipart parts, JSON depth, timeout và media type**; ở DB dùng **NOT NULL, CHECK, UNIQUE, foreign key** để bảo vệ invariant.

## 4. Phản hồi HTTP khi input và quyền không hợp lệ

| Trường hợp | Status thường dùng | Trách nhiệm |
| --- | --- | --- |
| Path UUID sai, query enum sai, JSON không parse được | **400 Bad Request** | MVC binding/message converter. |
| JSON media type không hỗ trợ | **415 Unsupported Media Type** | HTTP content negotiation. |
| Body vượt giới hạn | **413 Content Too Large** | Server/gateway upload limits. |
| DTO hợp cú pháp nhưng luật nhập sai | **400 hoặc 422** theo API contract | Domain validation. |
| Chưa có credential hợp lệ | **401 Unauthorized** | Spring Security authentication. |
| Có danh tính nhưng không được phép | **403 Forbidden**; có thể 404 để che tồn tại | Security/domain authorization. |
| Vi phạm unique state/version hoặc conflict | **409 Conflict / 412 Precondition Failed** tùy contract | Transaction/optimistic concurrency. |
| SQL syntax/DB hỏng do bug | **5xx** phù hợp, log an toàn | Server, không đổ thành 400 bừa bãi. |

Lỗi validation nên có field/code an toàn, **không lộ SQL, stack trace, token hay dữ liệu tenant**; thống nhất 400/422 trong OpenAPI.

Ví dụ **Problem Details (RFC 9457)**:

~~~http
POST /api/orders HTTP/1.1
Authorization: Bearer <redacted>
Content-Type: application/json

{"customerId":"22222222-2222-4222-8222-222222222222","totalMinorUnit":-1}

HTTP/1.1 400 Bad Request
Content-Type: application/problem+json
Cache-Control: no-store

{
  "type":"https://api.example.com/problems/validation-failed",
  "title":"Validation failed",
  "status":400,
  "detail":"Có dữ liệu đầu vào không hợp lệ.",
  "errors":[{"field":"totalMinorUnit","code":"PositiveOrZero"}]
}
~~~

**errors là extension ứng dụng**, không phải field bắt buộc RFC 9457; 422 cần được quy định rõ trong contract.

### 4.1. Spring @RestControllerAdvice cho lỗi DTO

~~~java
import java.net.URI;
import org.springframework.http.*;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.*;

@RestControllerAdvice
class InputProblemAdvice {
    @ExceptionHandler(MethodArgumentNotValidException.class)
    ResponseEntity<ProblemDetail> invalidBody(
            MethodArgumentNotValidException ex) {
        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                HttpStatus.BAD_REQUEST, "Có dữ liệu không hợp lệ.");
        problem.setTitle("Validation failed");
        problem.setType(URI.create(
                "https://api.example.com/problems/validation-failed"));
        return ResponseEntity.badRequest()
                .contentType(MediaType.APPLICATION_PROBLEM_JSON)
                .body(problem);
    }
}
~~~

Mẫu chỉ bắt lỗi **@RequestBody @Valid**; query/type mismatch và domain errors cần handler khác/ResponseEntityExceptionHandler. **Không echo rejectedValue nhạy cảm**.

## 5. Parameterized query: dữ liệu không được biến thành SQL

### 5.1. Truy vấn không an toàn và truy vấn an toàn

**Sai:**

~~~java
String sql = "SELECT id FROM orders WHERE tenant_id = '"
        + tenantId + "' AND status = '" + status + "'";
Statement statement = connection.createStatement();
ResultSet rows = statement.executeQuery(sql);
~~~

**Đúng:**

~~~java
String sql = """
        SELECT id, status, total_minor_unit
        FROM orders
        WHERE tenant_id = ? AND status = ?
        """;
try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setObject(1, trustedTenantId);
    statement.setString(2, requestedStatus);
    try (ResultSet rs = statement.executeQuery()) {
        while (rs.next()) {
            // Ánh xạ cột thành DTO; không log giá trị nhạy cảm.
        }
    }
}
~~~

Bind cả trustedTenantId đã phân quyền và requestedStatus đã validate. **Dấu ? là value, không phải tên cột/bảng hoặc WHERE**.

Không dùng helper tự thay placeholder bằng nối chuỗi; giữ cấu trúc SQL cố định, tránh tự escape theo dialect.

### 5.2. Một PreparedStatement không cứu được phần SQL nối trước đó

~~~java
// Nguy hiểm: orderBy đến từ query parameter rồi nối trực tiếp.
String sql = "SELECT id FROM orders WHERE tenant_id = ? ORDER BY "
        + orderBy;
PreparedStatement ps = connection.prepareStatement(sql);
ps.setObject(1, trustedTenantId);
~~~

**Bind tenant chưa cứu ORDER BY**. Dấu ? là value, không phải identifier; dùng **server-side allowlist** (phần 6).

### 5.3. JPA/Hibernate không tự làm native SQL ghép chuỗi an toàn

**Đúng với bind parameter:**

~~~java
TypedQuery<OrderEntity> query = entityManager.createQuery(
        "select o from OrderEntity o " +
        "where o.tenantId = :tenant AND o.status = :status",
        OrderEntity.class);
query.setParameter("tenant", trustedTenantId);
query.setParameter("status", status);
~~~

**Sai nếu ghép raw JPQL/native query:**

~~~java
String jpql = "select o from OrderEntity o where o.note = '"
        + noteFromRequest + "'";
entityManager.createQuery(jpql, OrderEntity.class);
~~~

**ORM không loại injection** khi nối raw JPQL/native SQL/ORDER BY. Dùng named parameters, Criteria/Querydsl với binding và allowlist sort; **@Query** cũng phải bind values.

## 6. Truy vấn động an toàn với Spring NamedParameterJdbcTemplate

Ví dụ tìm order theo tenant, status, ghi chú; sắp xếp **createdAt/totalMinorUnit**, asc/desc, giới hạn 100. **ORDER BY là cú pháp động**, không bind như value.

Chiến lược đúng:

1. **Value** như tenantId, status, pattern, limit được **bind**.
2. **Identifier / SQL keyword** như tên cột và ASC/DESC được chọn từ **allowlist hằng**.
3. **Cấu trúc điều kiện** được bật/tắt bằng nhánh code do server kiểm soát; không chèn nguyên đoạn WHERE do caller gửi.
4. Kết quả phải có **sort tie-breaker duy nhất** như id để thứ tự ổn định khi nhiều bản ghi trùng created_at.

### 6.1. Repository hoàn chỉnh ở mức minh họa

~~~java
import java.util.List;
import java.util.UUID;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
class OrderSearchRepository {
    private final NamedParameterJdbcTemplate jdbc;

    OrderSearchRepository(NamedParameterJdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    List<OrderDto> findForTenant(UUID tenantId, OrderSearch filter) {
        // Đây là các chuỗi do server định nghĩa, không phải raw input.
        String sortColumn = switch (filter.sort()) {
            case createdAt -> "created_at";
            case totalMinorUnit -> "total_minor_unit";
        };
        String direction = switch (filter.direction()) {
            case asc -> "ASC";
            case desc -> "DESC";
        };

        StringBuilder sql = new StringBuilder("""
                SELECT id, status, total_minor_unit
                FROM orders
                WHERE tenant_id = :tenantId
                  AND status = :status
                """);

        var args = new MapSqlParameterSource()
                .addValue("tenantId", tenantId)
                .addValue("status", filter.status().name())
                .addValue("limit", filter.limit());

        if (filter.q() != null && !filter.q().isBlank()) {
            sql.append("""
                     AND LOWER(note) LIKE LOWER(:pattern) ESCAPE '!'
                    """);
            args.addValue(
                    "pattern", "%" + escapeLike(filter.q()) + "%");
        }
        sql.append(" ORDER BY ")
                .append(sortColumn).append(" ")
                .append(direction)
                .append(", id ").append(direction)
                .append(" LIMIT :limit");

        return jdbc.query(sql.toString(), args,
                (rs, rowNumber) -> new OrderDto(
                        rs.getObject("id", UUID.class),
                        rs.getString("status"),
                        rs.getLong("total_minor_unit")));
    }

    private static String escapeLike(String raw) {
        return raw.replace("!", "!!")
                  .replace("%", "!%")
                  .replace("_", "!_");
    }
}
~~~

**Giả định:** PostgreSQL với id/tenant_id UUID, status, note, total_minor_unit, created_at. **LIMIT :limit**, **ESCAPE '!'** phụ thuộc dialect. Cần DTO phần 3, datasource/transaction; production bổ sung pagination và EXPLAIN.

**Đặc điểm:** ORDER BY chỉ nối literals từ switch, mọi request values được bind. LIKE **escapeLike** biến %, _, ! thành literal; binding riêng chống SQL injection. **LOWER(note)** và pattern bắt đầu % có thể tốn query cost, cần index/trigram/full-text phù hợp và giới hạn thời gian/kích thước.

### 6.2. Tại sao không dùng regex để “lọc SQL”?

**O'Connor** hay **' OR 1=1 --** vẫn là dữ liệu của pattern. Không cần cấm dấu nháy, miễn SQL **không diễn giải data thành code**.

### 6.3. ORDER BY, bảng, cột và hướng truy vấn không bind được

~~~java
// Không an toàn:
String sql = "SELECT * FROM orders ORDER BY " + sortFromRequest;

// Cũng không đúng mong đợi: dấu ? là value, không phải tên cột.
String sql2 = "SELECT * FROM orders ORDER BY ?";
~~~

Tên bảng, cột, operator, JSON path hay sort direction dùng **enum/allowlist**; đầu vào ngoài danh sách trả **400**. Giới hạn sort keys và thêm tie-breaker duy nhất.

### 6.4. Danh sách IN, truy vấn tùy chọn và batch

Danh sách **status IN (...)** cần một placeholder cho mỗi value theo thư viện hoặc dùng tính năng binding collection. Với Spring **NamedParameterJdbcTemplate**:

~~~java
String sql = "SELECT id FROM orders "
        + "WHERE tenant_id = :tenantId AND status IN (:statuses)";
var params = new MapSqlParameterSource()
        .addValue("tenantId", trustedTenantId)
        .addValue("statuses", List.of("CREATED", "PAID"));
var ids = jdbc.queryForList(sql, params, UUID.class);
~~~

NamedParameterJdbcTemplate **mở rộng list thành placeholders** và bind từng value. Kiểm tra list rỗng/giới hạn tham số; không nối từng phần tử vào SQL.

## 7. Validation không thay quyền theo tài nguyên/tenant

Ví dụ query của repository luôn có điều kiện **tenant_id = :tenantId**, nhưng nếu giá trị tenantId lại được lấy trực tiếp từ query của caller thì vấn đề BOLA vẫn tồn tại:

~~~java
// Sai: caller tự chọn tenant mà server không kiểm quyền.
UUID tenantId = UUID.fromString(request.getParameter("tenantId"));
return repository.findForTenant(tenantId, filter);
~~~

**Đúng:** service lấy identity từ **Spring Security**, ánh xạ và xác minh membership tenant trước khi gọi repository. Có thể thêm Postgres RLS phòng vệ nhiều lớp, không thay quyền ở application.

### 7.1. Truy vấn đúng cú pháp vẫn có thể lộ dữ liệu

PreparedStatement **không chặn** thiếu tenant filter, DTO lộ field, mass assignment, race hay DB account có quyền quá rộng.

Áp **DB least privilege**, DTO tách biệt, transaction/constraints và authorization; truy cập ngoài quyền trả **403/404**, không phải 200.

## 8. Injection ngoài SQL: cùng nguyên lý, khác cơ chế

**Parameterization phải phù hợp ngữ cảnh đích.** Một PreparedStatement chỉ bảo vệ SQL query, không bảo vệ HTML, shell, log hay template expression.

| Kiểu rủi ro | Mẫu nguy hiểm | Cách phòng ngừa |
| --- | --- | --- |
| **SQL/JPQL injection** | Nối q vào WHERE, sort vào ORDER BY. | Bind values + allowlist identifiers. |
| **NoSQL injection** | Nhận raw Mongo query JSON từ client rồi thực thi. | Xây DSL/schema typed, cố định operator, bind dữ liệu; giới hạn filter. |
| **OS command injection** | Ghép tên file/input vào lệnh qua shell. | Tránh shell; dùng API thư viện và ProcessBuilder với argv riêng, allowlist chương trình/options. |
| **Template/expression injection** | Đánh giá biểu thức Thymeleaf/SpEL do client cung cấp. | Không evaluate template/expression từ input; dùng template tin cậy, dữ liệu chỉ là biến. |
| **Cross-site scripting (XSS)** | Render ghi chú order thành HTML không escape. | Output encoding **đúng HTML/JS/URL context**, sanitizer nếu chủ đích cho rich HTML, CSP bổ trợ. |
| **CRLF/log/header injection** | Ghi raw newline/token vào log hoặc HTTP header. | Validate cấu trúc header, giới hạn, structured logging/redaction, thư viện HTTP an toàn. |
| **Path traversal** | Ghép tên file client vào đường dẫn lưu. | Storage key do server cấp, canonical path confinement, allowlist file types. |
| **SSRF** | API nhận URL rồi server gọi HTTP trực tiếp. | Allowlist origins, chặn private/link-local targets, kiểm redirect và DNS rebinding theo threat model. |

**Phòng chống injection không phải một hàm sanitize dùng chung.** Ví dụ HTML escaping dấu nháy trước khi lưu xuống DB có thể làm sai dữ liệu; SQL binding mới là việc phải làm khi truy vấn. Dữ liệu được giữ **nguyên ngữ nghĩa hợp lệ ở storage** và được encode **khi đặt vào từng output context**. Nếu người dùng được nhập HTML rich-text, sanitizer theo HTML policy là vấn đề riêng.

### 8.1. Canonicalization và nhiều tầng decode

Gateway có thể URL-decode, framework lại xử lý path/query; nếu code chủ động decode thêm lần nữa, một ký tự đã percent-encoded có thể đổi nghĩa sau khi validation. **Chọn một canonical representation**, chỉ decode tại lớp được xác định và validation trên giá trị thực được sử dụng. Tránh blacklist biểu thức URL trước khi decode rồi cho một lớp sau decode lần nữa.

Unicode normalization và so khớp case cũng phải theo chính sách từng field; đừng tự chuyển toàn bộ input thành ASCII hay bỏ dấu tiếng Việt. Với filename, path và URL, canonicalization còn có các ranh giới filesystem/network riêng, không chỉ kiểm độ dài.

### 8.2. Định dạng output và security headers

JSON API cần trả đúng **Content-Type: application/json** hoặc **application/problem+json** và không render dữ liệu thành HTML tùy ý. Nếu frontend nhúng note vào DOM, vẫn cần output encoding theo context hoặc HTML sanitizer phù hợp. **CORS, Content-Security-Policy và X-Content-Type-Options** chỉ bổ trợ, không thay parameterized query hay authorization.

## 9. Kiểm thử ở cả HTTP, repository và DB thật

### 9.1. Ma trận kiểm thử

| ID | Dữ liệu/kịch bản | Kết quả cần chứng minh |
| --- | --- | --- |
| V01 | POST thiếu totalMinorUnit hoặc customerId | **400**, không tạo order. |
| V02 | POST totalMinorUnit âm/giá trị quá lớn | **400/422** theo contract, không tràn kiểu số/ghi dữ liệu. |
| V03 | GET status không thuộc enum hoặc sort không có trong allowlist | **400**, không xây SQL từ raw input. |
| V04 | GET limit=0/101 hoặc không phải số | **400**, không quét toàn DB. |
| V05 | q chứa dấu nháy và chuỗi **' OR 1=1 --** | Giá trị chỉ là literal tìm kiếm; không mở rộng WHERE. |
| V06 | q chứa **%**, **_**, **!** | Tìm đúng ký tự literal theo contract, không biến thành wildcard. |
| V07 | Cùng actor, hai tenant khác nhau có dữ liệu trùng | API chỉ trả order của tenant được phép. |
| V08 | Actor đổi tenantId ở query/header | Không vượt phân quyền dù truy vấn bind an toàn. |
| V09 | Dữ liệu note từng chứa dấu nháy được lưu rồi dùng lại trong dynamic query | Không phát sinh **second-order SQL injection**. |
| V10 | SQL syntax lỗi hoặc DB mất kết nối | Trả lỗi server an toàn; không trả SQL, stack trace, token. |
| V11 | 100 request cùng tạo dữ liệu trùng unique key | DB constraints/transaction giải quyết race. |
| V12 | Input rất dài, body lớn, LIKE pattern tìm rộng | Giới hạn kích thước, thời gian, query cost và quota. |
| V13 | Path traversal/CRLF/URL ngoài allowlist ở tính năng khác | Từ chối tại trust boundary riêng, không dùng SQL sanitizer chung. |

### 9.2. MockMvc: validation và sort không hợp lệ

Ví dụ test với **Spring Boot + Spring Security Test**:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class OrdersInputIT {
    @Autowired MockMvc mvc;

    @Test
    void unknownSortIsBadRequest() throws Exception {
        mvc.perform(get("/api/orders")
                .param("status", "CREATED")
                .param("sort", "createdAt;DROP TABLE orders")
                .param("direction", "desc")
                .param("limit", "20")
                .with(jwt().authorities(new SimpleGrantedAuthority(
                        "SCOPE_orders.read"))))
            .andExpect(status().isBadRequest());
    }

    @Test
    void outOfRangeLimitIsBadRequest() throws Exception {
        mvc.perform(get("/api/orders")
                .param("status", "CREATED")
                .param("sort", "createdAt")
                .param("direction", "desc")
                .param("limit", "101")
                .with(jwt().authorities(new SimpleGrantedAuthority(
                        "SCOPE_orders.read"))))
            .andExpect(status().isBadRequest());
    }
}
~~~

**Điều kiện chạy:** cần ứng dụng có cấu hình SecurityFilterChain, service/repository, datasource fixture, **spring-security-test** và validation provider. **jwt() tạo Authentication giả**, không kiểm JWT signature/issuer/audience; các kiểm tra đó cần security integration tests riêng. Nếu API không dùng JWT hoặc không có scope orders.read, điều chỉnh fixture theo contract thật. Test validation **chưa chứng minh SQL parameterization**, vì một endpoint trả 400 cho sort xấu vẫn có thể nối chuỗi q vào SQL ở nhánh khác.

### 9.3. Test repository chống SQL injection và lọt tenant

Một integration test dùng **PostgreSQL thật hoặc Testcontainers PostgreSQL** nên chuẩn bị:

~~~text
tenant A:
  id=A1, status=CREATED, note="O'Connor"
  id=A2, status=CREATED, note="100% done"
tenant B:
  id=B1, status=CREATED, note="tenant-secret"
~~~

Sau đó chạy repository/API với tenant A:

1. **q = "O'Connor"** → tìm được A1, không lỗi SQL.
2. **q = "' OR 1=1 --"** → không trả B1 hoặc tất cả orders; nếu fixture không có note literal này thì kết quả rỗng.
3. **q = "%"** → tìm A2 theo ký tự phần trăm literal, không tự trả A1.
4. **q = "_"** → chỉ match ghi chú chứa dấu gạch dưới literal, không biến thành wildcard một ký tự.
5. **sort=totalMinorUnit, direction=asc** → đúng thứ tự, tie-break bằng id; query vẫn giới hạn tenant và limit.
6. **Sai tenant** hoặc actor không có quyền → 403/404 trước truy vấn hoặc repository chỉ thấy dữ liệu tenant được phép; không dựa vào q/SQL binding làm authorization.

Đừng chỉ kiểm HTTP status 200: phải xác minh **ID và tenant các hàng trả về**, số hàng và nội dung DB không bị thay đổi. Bài này không yêu cầu chạy Gradle/Testcontainers trong STEP 4; danh sách là kịch bản cần hiện thực khi bước kiểm thử dự án được cho phép.

### 9.4. Kiểm thử hiệu năng và giới hạn chi phí

Parameterized query vẫn có thể bị lạm dụng: pattern tìm kiếm rộng với leading wildcard, limit lớn, nested JSON, nhiều request đồng thời hoặc query chậm. Dùng **query timeout, connection pool limits, rate limiting, index phù hợp, phân trang và EXPLAIN** trên tập dữ liệu đại diện. Đừng đưa input, token hoặc raw SQL chứa dữ liệu nhạy cảm vào log/metric; log **query template**, route template, duration, status/error code và request ID.

## 10. Bài tập: API tìm kiếm đơn hàng đa tenant

**Tình huống:** endpoint GET /api/orders nhận q, sort, direction và limit; trước đây đội ngũ viết:

~~~java
String sql = "SELECT id FROM orders WHERE tenant_id = '"
    + request.getParameter("tenantId")
    + "' AND note LIKE '%" + request.getParameter("q")
    + "%' ORDER BY " + request.getParameter("sort");
~~~

Một reviewer đề nghị xóa mọi dấu nháy trong q và kiểm q không chứa chữ **DROP**. Người khác cho rằng chỉ thay tenantId và q bằng dấu ? là đủ, dù **sort** vẫn nối chuỗi. Cả hai đề xuất đều chưa hoàn chỉnh.

**Yêu cầu:** (1) Nêu các lỗ hổng riêng biệt trong đoạn code. (2) Đề xuất DTO validation cho q/sort/limit. (3) Thiết kế SQL dùng value binding và allowlist ORDER BY. (4) Xử lý LIKE để % và _ là ký tự literal khi yêu cầu tìm chính xác. (5) Nêu cách lấy tenantId tin cậy. (6) Viết bốn test chứng minh không mở rộng WHERE, không lọt tenant, không gây lỗi khi có dấu nháy và giới hạn limit.

**Hướng giải:** tenantId không lấy trực tiếp từ query; lấy từ principal và authorization policy. q được giới hạn độ dài, **không cấm dấu nháy nếu nghiệp vụ cho phép**; bind trong LIKE với escaping %, _, ký tự escape. sort/direction dùng enum map sang SQL literal hằng. limit là số nguyên 1–100 và được bind. Test fixture có ít nhất hai tenant, ghi chú chứa dấu nháy/wildcard, một payload giống SQL và input sort không thuộc allowlist. Bổ sung DB least privilege và runtime timeout để giảm tác động nếu vẫn có một đường lỗi.

## 11. Checklist trước khi phát hành

- [ ] Mọi path/query/body/header có **hợp đồng kiểu, miền, độ dài và giới hạn tài nguyên** phù hợp.
- [ ] Bean Validation chỉ lo hình dạng/constraint đơn giản; service kiểm **business rules, ownership, tenant**.
- [ ] Các giá trị trong SQL/JPQL/native query **được bind**, không nối chuỗi dù đã validate.
- [ ] ORDER BY, tên cột, bảng, operator và query structure động lấy từ **allowlist server-side**.
- [ ] LIKE search phân biệt bind tham số với **escape ký tự wildcard** theo DB dialect.
- [ ] IN/list filters có số phần tử tối đa; transaction/DB constraints bảo vệ concurrent writes.
- [ ] Tài khoản DB **least privilege**; query tenant scope và field exposure được kiểm tra.
- [ ] Không log token, raw sensitive values, SQL errors hay stack traces cho client.
- [ ] 400/415/422, 401/403/404 và 409/412 được map đúng contract/Problem Details.
- [ ] Test HTTP + repository trên DB thật, bao gồm payload giống injection, dữ liệu lưu trước, tenant khác và hiệu năng.

**Kết luận:** an toàn trước injection đến từ **tách cú pháp khỏi dữ liệu tại điểm thực thi**, không phải cấm một vài ký tự. **Validation** giúp xác định input hợp đồng, **parameterized query** giữ values là values, **allowlist** bảo vệ những vị trí SQL không bind được, và **domain authorization + least privilege + kiểm thử DB** ngăn việc một truy vấn đúng cú pháp vẫn làm lộ hoặc sửa tài nguyên ngoài quyền.
