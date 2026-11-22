# Kiểm thử thao tác hàng loạt có cả phần tử được phép và bị từ chối

## 1. Bài toán và mục tiêu kiểm thử

Một API thao tác hàng loạt (bulk operation) nhận nhiều ID trong một yêu cầu, chẳng hạn lưu trữ tài liệu, xóa bản ghi, đổi trạng thái đơn hàng hoặc cấp quyền cho nhiều đối tượng. Khi người gọi chỉ được phép thao tác trên **một phần** danh sách, kiểm tra quyền ở cấp endpoint hoặc kiểm tra duy nhất phần tử đầu tiên là không đủ. Đây là trường hợp dễ dẫn đến lỗi *Broken Object Level Authorization (BOLA/IDOR)*: một phần tử không thuộc phạm vi của người dùng vẫn bị thay đổi vì nó đi cùng các phần tử hợp lệ.

Ví dụ xuyên suốt: API `POST /api/documents/bulk-archive` nhận `{"ids":[101,102,103]}`. Người dùng `alice` có quyền tổng quát `DOC_ARCHIVE`; tài liệu `101` và `103` thuộc `alice`, tài liệu `102` thuộc `bob`. Tất cả ban đầu có `archived=false`.

| ID | Chủ sở hữu | Alice được phép lưu trữ? | Trạng thái ban đầu |
| --- | --- | --- | --- |
| 101 | alice | Có | `archived=false` |
| 102 | bob | Không | `archived=false` |
| 103 | alice | Có | `archived=false` |

**Mục tiêu chính:** chứng minh rằng phần tử `102` không bị thay đổi dưới bất kỳ cách xử lý nào được hệ thống công bố, và kết quả với `101`/`103` tuân thủ đúng chính sách bulk đã chọn. Một mã HTTP thành công hoặc thất bại **không tự chứng minh** dữ liệu được bảo vệ; bài kiểm thử phải đọc lại trạng thái lưu trữ và kiểm tra các tác dụng phụ.

Sau bài này, người học cần biết cách xác định chính sách thành công từng phần hay toàn bộ, tạo dữ liệu kiểm thử hỗn hợp, thực hiện request với Spring Security Test, khẳng định kết quả theo từng ID, phát hiện rò rỉ thông tin, và kiểm tra transaction/cạnh tranh.

## 2. Chốt hợp đồng bảo mật trước khi viết test

Hai chính sách đều có thể đúng về nghiệp vụ, nhưng **không được trộn lẫn**. Chọn một chính sách và viết kỳ vọng rõ ràng trong API contract.

| Chính sách | Yêu cầu chứa 101, 102, 103 | HTTP/response gợi ý | Trạng thái sau request |
| --- | --- | --- | --- |
| **All-or-nothing (nguyên tử)** | Có ít nhất một phần tử bị từ chối ⇒ từ chối toàn bộ | `403 Forbidden` hoặc mã lỗi đã thống nhất; phản hồi chung chung | 101, 102, 103 đều không đổi |
| **Partial success (thành công từng phần)** | Chỉ xử lý phần tử được phép; mỗi ID có kết quả riêng | Ví dụ `200 OK` với `results` cho từng ID; `207 Multi-Status` chỉ khi API cố ý định nghĩa | 101 và 103 đổi; 102 giữ nguyên |

Trong ví dụ Spring bên dưới, ta **chủ động chọn partial success**, trả `200 OK` và hai trạng thái `ARCHIVED`, `NOT_PROCESSED`. Trạng thái `NOT_PROCESSED` cố ý gộp các trường hợp không có quyền, không tồn tại và đã ở trạng thái lưu trữ, nhằm tránh lộ liệu ID có tồn tại hoặc thuộc ai. Đây là lựa chọn thiết kế của API ví dụ, **không phải mặc định của Spring Security**.

Ký hiệu `allowed(u,id)` là quyết định cấp quyền của người dùng `u` với đối tượng `id` và `changed(id)` là đối tượng đã bị cập nhật:

- Với **partial success**: `changed(id) ⇒ allowed(u,id)` cho mọi ID; mọi ID bị từ chối phải giữ nguyên dữ liệu.
- Với **all-or-nothing**: `∃ id : !allowed(u,id) ⇒ ∀ id : !changed(id)`.
- Với cả hai: người dùng không có quyền gọi thao tác bulk ở cấp phương thức phải bị chặn **trước mọi ghi**; xác thực không thay thế cấp quyền theo từng đối tượng.

Cần định nghĩa thêm các điểm dễ gây sai test: thứ tự kết quả, xử lý ID trùng, ID không tồn tại, giới hạn kích thước batch, điều kiện coi là “đã xử lý” khi đối tượng đã ở trạng thái đích, và cách rollback khi thao tác cơ sở dữ liệu lỗi. Ví dụ này loại ID trùng nhưng giữ thứ tự xuất hiện đầu tiên; danh sách rỗng/ID không hợp lệ trả `400 Bad Request`.

## 3. Các lớp cấp quyền cần đi qua

Luồng request điển hình:

`HTTP request → authentication → quyền thao tác DOC_ARCHIVE → kiểm tra phạm vi từng ID → mutation có điều kiện ở database → response`.

1. **Xác thực:** danh tính lấy từ `Authentication`/principal do Spring Security xác thực. Không lấy `username`, tenant hoặc role do client tự khai trong JSON để quyết định quyền.
2. **Quyền chức năng:** `@PreAuthorize("hasAuthority('DOC_ARCHIVE')")` trên Spring bean được quản lý ngăn người không có quyền sử dụng chức năng. Bật `@EnableMethodSecurity`; Spring Boot Security starter không tự bật method authorization.
3. **Quyền theo đối tượng:** trước hoặc ngay khi sửa mỗi bản ghi, kiểm tra owner/tenant/permission thực tế. Có quyền chức năng **không có nghĩa** mọi ID trong batch đều được phép.
4. **Ghi an toàn:** câu lệnh cập nhật có điều kiện `WHERE id = ? AND owner_username = ?` giúp bảo đảm bản ghi ngoài phạm vi không bị thay đổi, kể cả khi ID bị chèn giữa các ID hợp lệ. Với chính sách phức tạp, điều kiện phải bao gồm tenant, ACL, trạng thái và version phù hợp.
5. **Phản hồi:** không trả owner, tenant, metadata, nội dung hoặc lý do chi tiết của ID bị từ chối nếu caller không được phép biết. Dùng thông báo chung theo hợp đồng API.
6. **Điểm chặn sâu:** không chỉ bảo vệ controller. Gọi service từ job, listener hoặc code nội bộ vẫn phải tuân thủ quy tắc cấp quyền; nhớ rằng gọi nội bộ cùng instance (*self-invocation*) có thể không đi qua Spring AOP proxy của `@PreAuthorize`.

`@PreFilter`/`@PostFilter` có thể hữu ích cho một số phép lọc, nhưng không tự chứng minh an toàn của thao tác ghi hàng loạt. Đặc biệt, **không được** cập nhật trước rồi lọc các phần tử bị từ chối ra khỏi response: dữ liệu đã thay đổi thì lỗi bảo mật vẫn tồn tại.

## 4. Ví dụ Java 17 chạy độc lập: test hành vi cốt lõi

Đoạn này mô phỏng kho dữ liệu trong bộ nhớ để thấy rõ bất biến “ID bị từ chối không bị ghi”. Nó là mô hình Java thuần, **chưa thay thế** test Spring Security, HTTP hoặc database bên dưới.

Tệp `BulkArchiveDemo.java`:

```java
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;

public class BulkArchiveDemo {
    record Document(long id, String owner, boolean archived) {}
    enum Status { ARCHIVED, NOT_PROCESSED }
    record ItemResult(long id, Status status) {}

    static List<ItemResult> archivePartial(
            Map<Long, Document> database, String actor, List<Long> ids) {
        if (ids == null || ids.isEmpty()
                || ids.size() > 100 || ids.contains(null)) {
            throw new IllegalArgumentException("Invalid batch");
        }

        List<ItemResult> results = new ArrayList<>();
        for (Long id : new LinkedHashSet<>(ids)) {
            Document document = database.get(id);
            if (document == null
                    || !document.owner().equals(actor)
                    || document.archived()) {
                results.add(new ItemResult(id, Status.NOT_PROCESSED));
                continue;
            }

            database.put(id, new Document(id, document.owner(), true));
            results.add(new ItemResult(id, Status.ARCHIVED));
        }
        return List.copyOf(results);
    }

    public static void main(String[] args) {
        Map<Long, Document> database = new LinkedHashMap<>();
        database.put(101L, new Document(101, "alice", false));
        database.put(102L, new Document(102, "bob", false));
        database.put(103L, new Document(103, "alice", false));

        List<ItemResult> results = archivePartial(
                database, "alice", List.of(101L, 102L, 103L));

        System.out.println(results.stream()
                .map(x -> x.id() + ":" + x.status()).toList());
        System.out.println("archived=" + database.values().stream()
                .filter(Document::archived).map(Document::id).toList());
    }
}
```

Chạy với JDK 17 trở lên:

```bash
javac BulkArchiveDemo.java
java BulkArchiveDemo
```

Stdout chính xác:

```text
[101:ARCHIVED, 102:NOT_PROCESSED, 103:ARCHIVED]
archived=[101, 103]
```

Hãy thử đổi chủ sở hữu `102` thành `alice`: cả ba ID sẽ được lưu trữ. Hãy thử `List.of(101L,101L,102L)`: mỗi ID chỉ có một kết quả do `LinkedHashSet` loại trùng và giữ thứ tự. Demo chỉ xác minh thuật toán trên bộ nhớ; test thực tế còn phải chứng minh filter chain, method security, transaction và điều kiện ghi ở database.

## 5. Áp dụng trong Spring Security: partial success

Ví dụ dưới đây dùng Spring MVC, Spring Security method security, Spring JDBC và transaction. Giả định ứng dụng đã có Spring Boot, Spring Security, JDBC, cấu hình DataSource và bảng `documents(id, owner_username, archived)`; các lớp đặt trong package được Spring quét. Đoạn này minh họa **một thiết kế cụ thể**: chỉ owner được phép lưu trữ. Nếu hệ thống dùng tenant/ACL/phân quyền chia sẻ thì phải thay điều kiện `owner_username` bằng chính sách có hiệu lực thật.

```java
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Objects;

import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Repository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;

@Configuration
@EnableMethodSecurity
class MethodSecurityConfig {}

record BatchArchiveRequest(List<Long> ids) {}
record BatchItemResult(long id, String status) {}
record BatchArchiveResponse(List<BatchItemResult> results) {}

interface DocumentArchiveRepository {
    int archiveIfOwned(long id, String owner);
}

@Repository
class JdbcDocumentArchiveRepository implements DocumentArchiveRepository {
    private final JdbcTemplate jdbc;

    JdbcDocumentArchiveRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Override
    public int archiveIfOwned(long id, String owner) {
        return jdbc.update("""
                UPDATE documents
                   SET archived = TRUE
                 WHERE id = ?
                   AND owner_username = ?
                   AND archived = FALSE
                """, id, owner);
    }
}

@Service
class BulkArchiveService {
    private final DocumentArchiveRepository repository;

    BulkArchiveService(DocumentArchiveRepository repository) {
        this.repository = repository;
    }

    @Transactional
    @PreAuthorize("hasAuthority('DOC_ARCHIVE')")
    public BatchArchiveResponse archivePartial(
            List<Long> rawIds, Authentication actor) {
        if (rawIds == null || rawIds.isEmpty() || rawIds.size() > 100
                || rawIds.stream().anyMatch(
                        id -> id == null || id <= 0)) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "Invalid batch");
        }

        List<BatchItemResult> results = new ArrayList<>();
        for (Long id : new LinkedHashSet<>(rawIds)) {
            int updated = repository.archiveIfOwned(id, actor.getName());
            results.add(new BatchItemResult(
                    id, updated == 1 ? "ARCHIVED" : "NOT_PROCESSED"));
        }
        return new BatchArchiveResponse(List.copyOf(results));
    }
}

@RestController
@RequestMapping("/api/documents")
class BulkArchiveController {
    private final BulkArchiveService service;

    BulkArchiveController(BulkArchiveService service) {
        this.service = service;
    }

    @PostMapping("/bulk-archive")
    BatchArchiveResponse archive(
            @RequestBody BatchArchiveRequest request,
            Authentication authentication) {
        return service.archivePartial(request.ids(), authentication);
    }
}
```

**Vì sao cách ghi này an toàn hơn `findById() → kiểm tra → updateById()`?** Câu `UPDATE` chỉ tác động khi cùng lúc ID, owner và trạng thái vẫn khớp. Cập nhật trả `0` nếu không đủ điều kiện, nên service không thể vô tình ghi vào tài liệu `102`. Với tenant, bổ sung `AND tenant_id = ?` và lấy tenant từ principal đáng tin cậy; nếu cho phép chia sẻ quyền, thay bằng predicate/permission evaluator phản ánh ACL thật. Chỉ dựa vào owner trong SQL là **chưa đủ** cho mô hình phân quyền khác.

`@Transactional` khiến các lỗi runtime khi thực hiện các update thường rollback cả transaction; tuy nhiên chính sách *partial success* ở đây nói đến **phần tử bị từ chối vì quyền**, không tự động hứa xử lý từng lỗi database độc lập. Nếu cần “best effort” ngay cả khi một ID lỗi I/O hoặc vi phạm constraint, phải thiết kế transaction riêng cho từng ID và test chính xác.

Lưu ý: `@PreAuthorize` cần được gọi qua Spring-managed proxy; annotation trên phương thức gọi nội bộ trực tiếp trong cùng bean có thể bị bỏ qua. `hasAuthority` đối chiếu đúng chuỗi `DOC_ARCHIVE`; `hasRole("ADMIN")` lại liên quan tới quy ước tiền tố `ROLE_`, không thể tùy tiện thay thế.

## 6. Kiểm thử tích hợp Spring Security + dữ liệu sau request

Cần dependency `spring-security-test` cùng hệ sinh thái Spring Boot Test. Ví dụ dưới đây dùng `MockMvc`, `@WithMockUser`, `csrf()` và một database test cô lập, có bảng `documents` như phần trên. `@BeforeEach` khôi phục dữ liệu từng test; test **không phụ thuộc thứ tự chạy**.

```java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class BulkArchiveAuthorizationIT {
    @Autowired MockMvc mvc;
    @Autowired JdbcTemplate jdbc;

    @BeforeEach
    void seed() {
        jdbc.update("DELETE FROM documents WHERE id IN (101,102,103)");
        jdbc.update("INSERT INTO documents (id,owner_username,archived) "
                + "VALUES (?,?,FALSE)", 101L, "alice");
        jdbc.update("INSERT INTO documents (id,owner_username,archived) "
                + "VALUES (?,?,FALSE)", 102L, "bob");
        jdbc.update("INSERT INTO documents (id,owner_username,archived) "
                + "VALUES (?,?,FALSE)", 103L, "alice");
    }

    private boolean archived(long id) {
        return Boolean.TRUE.equals(jdbc.queryForObject(
                "SELECT archived FROM documents WHERE id = ?",
                Boolean.class, id));
    }

    @Test
    @WithMockUser(username = "alice", authorities = "DOC_ARCHIVE")
    void mixedBatch_updatesOnlyOwnedDocuments() throws Exception {
        mvc.perform(post("/api/documents/bulk-archive")
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"ids\":[101,102,103]}"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.results[0].id").value(101))
            .andExpect(jsonPath("$.results[0].status").value("ARCHIVED"))
            .andExpect(jsonPath("$.results[1].id").value(102))
            .andExpect(jsonPath("$.results[1].status").value("NOT_PROCESSED"))
            .andExpect(jsonPath("$.results[2].id").value(103))
            .andExpect(jsonPath("$.results[2].status").value("ARCHIVED"));

        assertThat(archived(101L)).isTrue();
        assertThat(archived(102L)).isFalse();
        assertThat(archived(103L)).isTrue();
    }

    @Test
    @WithMockUser(username = "alice", authorities = "DOC_READ")
    void missingFunctionalAuthority_rejectsAllWrites() throws Exception {
        mvc.perform(post("/api/documents/bulk-archive")
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"ids\":[101,103]}"))
            .andExpect(status().isForbidden());

        assertThat(archived(101L)).isFalse();
        assertThat(archived(102L)).isFalse();
        assertThat(archived(103L)).isFalse();
    }

    @Test
    @WithMockUser(username = "alice", authorities = "DOC_ARCHIVE")
    void deniedOnly_doesNotModifyDocument() throws Exception {
        mvc.perform(post("/api/documents/bulk-archive")
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"ids\":[102]}"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.results[0].status").value("NOT_PROCESSED"));

        assertThat(archived(102L)).isFalse();
    }
}
```

Đây là test chạy được **trong ứng dụng đã khai báo schema, dependencies và security configuration tương ứng**, không phải một tệp Java độc lập để chạy bằng `javac`. Với các API session/cookie bật CSRF, request POST trong test cần `.with(csrf())`; nếu cấu hình API dùng bearer token và không dùng CSRF, test phải phản ánh filter chain thật. `@WithMockUser` thích hợp cho kiểm thử MockMvc cùng Spring Test context; HTTP end-to-end chạy trên server và thread khác cần gửi credential thật trong request.

Điều test phải giữ: xác thực `alice`, quyền chức năng `DOC_ARCHIVE`, kết quả **từng ID** và trạng thái **database sau yêu cầu**. Không dùng mock repository chỉ trả JSON cố định nếu mục tiêu là chứng minh dữ liệu được bảo vệ: một mock như vậy có thể báo `NOT_PROCESSED` cho `102` dù code thật đã ghi sai bản ghi.

## 7. Nếu nghiệp vụ yêu cầu all-or-nothing

Với policy nguyên tử, không được lặng lẽ “bỏ qua” `102` rồi vẫn commit `101` và `103`. Trình tự an toàn là:

1. Xác thực, kiểm tra quyền chức năng, validate toàn bộ input và bỏ ID trùng.
2. Trong transaction, xác minh **mọi** phần tử được phép và ở trạng thái có thể thao tác. Nếu bất kỳ phần tử nào không đạt, ném `AccessDeniedException` hoặc lỗi nghiệp vụ đã quy định.
3. Khi tất cả đạt, thực hiện các câu `UPDATE` có điều kiện theo actor/tenant; nếu bất kỳ update nào trả `0` do trạng thái hoặc quyền đổi trong lúc chạy, **ném exception làm rollback**, không trả thành công.
4. Sau request hỗn hợp `[101,102,103]`, test trả lỗi đúng contract và cả ba dòng vẫn `archived=false`. Thử thêm tình huống ID bị từ chối ở **cuối batch** để chắc chắn các lần ghi trước đó được rollback.

`@Transactional` cần có transaction manager thật và lời gọi đi qua Spring proxy. Mặc định Spring rollback trên unchecked exception như `AccessDeniedException`; nếu bắt exception và trả response bình thường trong transaction, các update trước đó có thể đã commit. Đừng hiểu “đã chạy preflight” là hết rủi ro TOCTOU: cần update có điều kiện, khóa hoặc version/optimistic locking tùy độ quan trọng của dữ liệu.

Ví dụ kỳ vọng all-or-nothing:

```text
Input:  user=alice; ids=[101,102,103]
Policy: 101=ALLOW, 102=DENY, 103=ALLOW
HTTP:   403 (theo hợp đồng API ví dụ)
DB:     archived(101)=false
        archived(102)=false
        archived(103)=false
```

Hai dấu hiệu sai nghiêm trọng: API trả `403` nhưng `101` đã đổi (thiếu rollback), hoặc API trả `200` và báo hoàn tất cả batch dù `102` bị từ chối.

## 8. Ma trận kiểm thử cần có

Các phép thử sau dùng fixture sạch; cột kết quả mặc định là **partial success** như phần 5. Với all-or-nothing, chỉnh kỳ vọng cho mọi batch hỗn hợp thành **không có thay đổi**.

| Tình huống | Request / danh tính | Điều cần khẳng định |
| --- | --- | --- |
| Tất cả được phép | alice: `[101,103]` | Cả hai được cập nhật, kết quả đúng thứ tự |
| **Hỗn hợp, deny ở giữa** | alice: `[101,102,103]` | 101/103 cập nhật; 102 không đổi; 102 có kết quả chung chung |
| Hỗn hợp, deny ở đầu/cuối | alice: `[102,101]` và `[101,102]` | Không lệ thuộc thứ tự, không bỏ sót kiểm tra cuối vòng lặp |
| Tất cả bị từ chối | alice: `[102]` | Không có bất kỳ update hay tác dụng phụ |
| Thiếu quyền chức năng | alice không có `DOC_ARCHIVE` | Bị chặn ở method/endpoint; không có ghi |
| Chưa xác thực | anonymous | Không có ghi; mã `401`/redirect/`403` tùy entry point đã cấu hình |
| Trùng ID | alice: `[101,101,102]` | Theo contract ví dụ: chỉ một update/kết quả cho 101 |
| ID không tồn tại | alice: `[101,999]` | Không coi 999 là đã cập nhật; không lộ phân biệt tồn tại với bị deny |
| Input sai | `[]`, ID null, ID âm, >100 ID | `400`, không có phần tử nào bị đổi |
| Bản ghi đã archived | alice: `[101]` khi 101 đã archived | Theo contract ví dụ: `NOT_PROCESSED`, không cập nhật lại |
| Khác tenant/ACL | actor thuộc tenant A, ID tenant B | Điều kiện DB/permission evaluator chặn dù ID được biết |
| Lỗi giữa batch | database lỗi sau một lần update | Rollback/partial commit đúng chính sách transaction đã công bố |
| Cạnh tranh | đổi owner/quyền/trạng thái trong lúc batch chạy | Không xuất hiện update trái quyền; transaction/version xử lý đúng |
| Thao tác phụ | event, audit, queue, email gắn với ID 102 | Không có tác dụng phụ “đã lưu trữ” cho ID bị từ chối |

Không nhất thiết viết 14 bài test dài từ đầu; ưu tiên test hỗn hợp, tất cả bị deny, thiếu quyền chức năng và kiểm tra database, rồi bổ sung các biến thể theo rủi ro của module.

## 9. Cách kiểm tra tác dụng phụ và chống rò rỉ thông tin

**Đừng dừng ở `status().isOk()` hoặc `isForbidden()`.** Sau request, truy vấn lại đúng ba dòng hoặc so snapshot trước–sau. Với mock-based unit test, dùng `verify(repository, never()).archiveIfOwned(102L, ...)` chỉ là bổ trợ; test integration với database mới khẳng định được trạng thái persist. Nếu có event/audit/queue, kiểm tra không phát sinh sự kiện thành công cho ID 102 và không phát sinh sau rollback. Audit về lần cố gắng bị từ chối có thể được ghi riêng nếu chính sách yêu cầu, nhưng không được giả là thao tác nghiệp vụ đã thành công.

Kiểm tra response không chứa tên `bob`, tenant khác, tài liệu hoặc thông báo “ID 102 tồn tại nhưng không thuộc bạn”. Nếu sản phẩm quyết định trả `403` và `404` khác nhau theo ngữ cảnh, phải đánh giá nguy cơ đoán sự tồn tại đối tượng và kiểm thử đúng hợp đồng bảo mật đó. Đừng mặc định `403`/`404` là một lựa chọn duy nhất cho mọi API.

Ngoài ra nên giới hạn số ID, chuẩn hóa và kiểm tra toàn bộ request **trước** lần ghi đầu tiên. Đừng đọc từng ID mà bỏ qua tenant filter ở query. Đừng lấy danh sách ID “được phép” từ phía client rồi tin tưởng. Nếu hệ thống xử lý bulk bất đồng bộ, test cả hàng đợi/job worker vì cấp quyền có thể thay đổi giữa lúc enqueue và lúc thực thi; cần chính sách rõ ràng về kiểm tra lại và ngữ cảnh actor tin cậy.

## 10. Các lỗi phổ biến và dấu hiệu nhận biết

- **Chỉ kiểm tra `hasAuthority`:** caller có quyền gọi chức năng, nhưng vẫn thay đổi được đối tượng người khác; khắc phục bằng quyết định theo từng ID và update có điều kiện.
- **Kiểm tra một ID đại diện:** phần tử đầu hợp lệ che khuất phần tử giữa/cuối bất hợp lệ; test thay đổi vị trí phần tử deny.
- **Chỉ kiểm tra response:** status là `403` nhưng transaction đã commit một phần; truy vấn lại DB và sự kiện phụ.
- **Lọc response sau khi ghi:** kết quả trông hợp lệ nhưng đối tượng bị deny đã đổi; xác minh phía lưu trữ, không dựa vào JSON.
- **Bắt exception rồi commit:** trong all-or-nothing, xử lý lỗi giữa transaction không rollback; cần ném unchecked exception hoặc đánh dấu rollback theo contract.
- **Cho phép TOCTOU:** kiểm tra owner trước rồi update không có điều kiện; dùng conditional update và xử lý số dòng bị thay đổi.
- **Không test đúng security chain:** tắt filter hoặc mock cả service trong test integration, khiến `@PreAuthorize`/CSRF/credential không được kiểm chứng.
- **Rò rỉ qua per-item error:** thông điệp nêu owner/tenant hoặc phân biệt ID đã tồn tại mà caller không được phép xem.

## 11. Checklist nghiệm thu cho một bài test bulk authorization

Một bộ test có giá trị trả lời được các câu hỏi: *Ai đang gọi? Quyền chức năng nào? Những ID nào được phép? Contract chọn nguyên tử hay partial? Database thay đổi chính xác những ID nào? Có rollback khi cần không? Response có lộ dữ liệu không?* Tối thiểu, test hỗn hợp phải có **ít nhất một ID ALLOW, một ID DENY, và assert riêng từng ID sau request**.

Chỉ xem bài là đạt khi cùng một fixture độc lập tái hiện được kết quả, cách xử lý ID trùng và input xấu đã rõ, quyền chức năng và quyền đối tượng đều được kiểm tra, và không có tác dụng phụ trái phép. Việc bổ sung test race condition, tenant/ACL hay async phụ thuộc kiến trúc của hệ thống, nhưng không được ngầm giả định chúng đã được bảo vệ bởi `@PreAuthorize`.

## Tài liệu tham khảo

- Spring Security — Method Security: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Security — Testing Method Security: https://docs.spring.io/spring-security/reference/servlet/test/method.html
- Spring Security — Spring MVC Test Integration: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/
- Spring Security — Testing with CSRF Protection: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html
