# Đồng bộ dữ liệu LDAP với hệ thống khác

## 1. Từ truy vấn thư mục đến bài toán đồng bộ

Một ứng dụng dùng **Spring LDAP** có thể lấy thông tin nhân viên từ directory, trong khi hệ thống HR quản lý hợp đồng lao động, hệ thống Identity Management (IdM) quản lý tài khoản và ứng dụng nghiệp vụ quản lý quyền trong từng workspace. Các hệ thống này thường có một số trường giống nhau nhưng **không có cùng trách nhiệm và vòng đời dữ liệu**.

Ví dụ, HR tạo nhân viên; IdM tạo tài khoản dưới **ou=people,dc=example,dc=org**; LDAP lưu **uid**, **cn**, **mail**, **entryUUID** và nhóm. Ứng dụng Spring Boot phải tạo bản chiếu danh tính trong PostgreSQL để hiển thị tên, liên kết lịch sử tác nghiệp và kiểm tra quyền. Sau khi nhân viên được chuyển đơn vị, entry có thể đổi DN nhưng vẫn là cùng người. Khi tài khoản bị vô hiệu hóa hoặc xóa, ứng dụng phải xử lý quyền truy cập mà không phá hủy hồ sơ kiểm toán.

**Đồng bộ** là quá trình phát hiện thay đổi, chuyển đổi schema, cập nhật hệ thống đích, xử lý lỗi, xung đột và xác minh kết quả. Một câu lệnh **LdapTemplate.search()** chỉ giải quyết bước lấy dữ liệu. Giải pháp đầy đủ phải chịu được mạng lỗi, sự kiện trùng, thay đổi sai thứ tự, thiếu quyền đọc, đổi DN, replication lag và khôi phục sau crash.

Bài này thuộc chương **Thiết kế ứng dụng** của **Spring LDAP**. Phạm vi gồm thiết kế ranh giới dữ liệu, truy cập directory bằng **ContextSource**, **LdapTemplate**, **LdapClient** hoặc ODM, kiểm soát DN/schema/filter, TLS, pooling, xử lý lỗi và kiểm thử truy cập thư mục an toàn.

## 2. Lập bản đồ nguồn dữ liệu có thẩm quyền

Trước khi chọn thư viện đồng bộ, xác định **system of record** cho từng trường. Directory chứa dữ liệu danh tính nhưng không tự động là nguồn ghi của mọi thuộc tính liên quan đến nhân viên.

| Dữ liệu | Nguồn ghi chính trong ví dụ | Luồng đến đích | Quy tắc |
| --- | --- | --- | --- |
| Mã nhân viên, tình trạng lao động, ngày nghỉ việc | HR | HR → IdM / provisioning | Không cho ứng dụng tự sửa hồ sơ HR |
| Định danh entry, trạng thái tài khoản, login | IdM/LDAP | LDAP → ứng dụng | Directory quyết định trạng thái tài khoản |
| Email công việc, tên hiển thị | HR hoặc IdM, theo quyết định tổ chức | Nguồn chính → LDAP → app | Chỉ một nơi quyết định giá trị chuẩn |
| Nhóm tổ chức LDAP | IdM/LDAP | LDAP → policy hoặc projection | Không tự quy mọi nhóm thành vai trò nghiệp vụ |
| Vai trò trong workspace | Ứng dụng nghiệp vụ | Application DB | Không tự ghi đè bằng group LDAP |
| Cài đặt thông báo, biệt danh cá nhân | Ứng dụng nghiệp vụ | Application DB → service cần dùng | Không đẩy ngược vào LDAP nếu không có hợp đồng |

Ba mô hình phổ biến:

1. **Inbound LDAP → app:** đồng bộ profile, trạng thái tài khoản hoặc group thành một **read model/projection** trong DB ứng dụng.
2. **Outbound HR/app → LDAP:** provisioning command tạo/sửa/vô hiệu hóa entry hoặc group do nguồn đích cho phép; cần ACL và idempotency.
3. **Hai chiều có kiểm soát:** chỉ dùng khi đã quy định quyền ghi cho từng attribute và chính sách giải quyết xung đột. Không mặc định “bên ghi cuối theo đồng hồ máy chủ sẽ thắng”.

Nếu hai bên đều có thể sửa **mail**, một event cũ đến muộn có thể ghi đè địa chỉ mới, hoặc thay đổi được gửi qua lại gây vòng lặp. Hợp đồng cần chỉ rõ **owner field, hướng dữ liệu, origin của event, idempotency key và expected version** khi cần.

## 3. Kiến trúc port–adapter cho luồng đồng bộ

~~~mermaid
flowchart TB
    HR["HR / IdM"]
    COMMAND["Provisioning application handler"]
    WRITEPORT["DirectoryWritePort"]
    WRITEADAPTER["Spring LDAP write adapter"]
    DIRECTORY[("LDAP directory")]
    READADAPTER["Spring LDAP reader / change feed"]
    READPORT["DirectoryChangeSource"]
    SYNC["Sync orchestrator"]
    PROJECTION["ProjectionWriter"]
    DATABASE[("Application database")]
    CHECKPOINT[("Checkpoint / ledger")]
    POLICY["Domain policy / use cases"]

    HR --> COMMAND --> WRITEPORT
    WRITEPORT -. "implemented by" .-> WRITEADAPTER
    WRITEADAPTER --> DIRECTORY
    DIRECTORY --> READADAPTER
    READADAPTER -. "implemented by" .-> READPORT
    READPORT --> SYNC
    SYNC --> PROJECTION --> DATABASE
    SYNC --> CHECKPOINT
    POLICY --> DATABASE
~~~

**LDAP adapter** hiểu DN, RDN, search base, filter, schema, LDAP controls và exception JNDI/Spring LDAP. **Sync orchestrator** hiểu batch, retry, checkpoint, idempotency và chính sách xử lý sự kiện. **ProjectionWriter** biết cách upsert vào SQL, giữ ràng buộc duy nhất và kiểm soát cập nhật đồng thời. **Domain service** chỉ tiêu thụ model đã ánh xạ.

| Thành phần | Trách nhiệm | Không nên làm |
| --- | --- | --- |
| DirectoryChangeSource | Đọc batch thay đổi hoặc snapshot, quản lý opaque cursor của LDAP | Đưa DirContext hoặc raw NamingException ra application |
| LdapPersonMapper | Chuyển attribute và định danh LDAP sang model trung lập | Quyết định quyền thành viên workspace |
| SyncOrchestrator | Chạy batch, phục hồi sau lỗi, chỉ tiến checkpoint đúng thời điểm | Ghép filter hoặc DN bằng chuỗi |
| ProjectionWriter | Upsert, tombstone, version check và unique constraint | Điều khiển LDAP connection |
| CheckpointStore | Lưu progress và cơ chế cạnh tranh giữa worker | Coi cookie LDAP nào cũng sống mãi qua restart |
| Reconciler | So sánh nguồn và đích, tìm thay đổi bị bỏ lỡ | Xóa hàng loạt khi scan chưa hoàn chỉnh |

Các lớp domain/application **không import org.springframework.ldap, javax.naming hoặc các kiểu Attributes/DirContextOperations**. Việc đổi **LdapTemplate** thành **LdapClient** hoặc ODM nên được giới hạn ở adapter.

## 4. Định danh ổn định khi entry đổi DN

LDAP entry có thể bắt đầu ở:

~~~text
uid=lan,ou=engineering,dc=example,dc=org
~~~

Sau khi chuyển bộ phận:

~~~text
uid=lan,ou=operations,dc=example,dc=org
~~~

Nếu ứng dụng dùng DN làm khóa người dùng, thao tác move có thể bị coi là xóa một người và tạo người khác. Tài liệu, vai trò và lịch sử bị tách khỏi danh tính cũ.

Nên tham chiếu bằng **directory source ID + stable entry ID**. Nhiều triển khai OpenLDAP cung cấp operational attribute **entryUUID**; Active Directory dùng **objectGUID** (dạng nhị phân). Không giả định hai hệ thống có cùng kiểu dữ liệu hoặc cùng vòng đời ID. Phải xác minh quyền đọc và khả năng giữ ID ổn định khi rename/move.

~~~java
// domain/DirectorySubject.java
package com.example.sync.domain;

import java.util.Objects;

public record DirectorySubject(String sourceId, String stableId) {
    public DirectorySubject {
        Objects.requireNonNull(sourceId, "sourceId");
        Objects.requireNonNull(stableId, "stableId");
        if (sourceId.isBlank() || stableId.isBlank()) {
            throw new IllegalArgumentException("Thiếu định danh directory");
        }
    }
}
~~~

Trong database đích đặt unique constraint trên **(directory_source, directory_subject_id)**. **current_dn** và **login** là thuộc tính thay đổi được. Đổi OU chỉ cập nhật đường dẫn, không tạo principal mới.

**Lưu ý:** xóa rồi tạo lại entry, thay directory hoặc migration có thể sinh stable ID mới. Nếu cần liên kết danh tính qua migration, dùng một bảng ánh xạ và quy trình đối soát được xác nhận; không tự ghép tài khoản dựa trên email hoặc login trùng.

## 5. Chọn full scan, incremental feed và reconciliation

| Cơ chế | Khi dùng | Lợi ích | Rủi ro |
| --- | --- | --- | --- |
| **Full snapshot scan** | Khởi tạo projection, kiểm tra định kỳ | Bao quát dữ liệu trong phạm vi scan | Tốn tài nguyên; entry thay đổi giữa các trang |
| **Incremental sync** | Đọc thay đổi mới từ nguồn hỗ trợ | Độ trễ thấp và giảm tải | Cần cursor, retention và khả năng resume đúng |
| **Periodic reconciliation** | Phục hồi sự kiện mất hoặc sai mapping | Phát hiện lệch sau outage | Phải tránh false delete nếu scan không hoàn tất |

Không có **một change feed tiêu chuẩn có mặt trên mọi LDAP server**:

- **LDAP Content Synchronization (RFC 4533)** có thể được dùng khi server hỗ trợ và được cấu hình. Phải kiểm thử cookie, trạng thái refresh/persist và quyền đọc thực tế.
- **Active Directory DirSync** là LDAP control đặc thù của AD, có quy tắc cookie và quyền truy cập riêng.
- Một số sản phẩm cung cấp **persistent search**, changelog hoặc notification riêng; tính sẵn có và ý nghĩa sự kiện khác nhau.
- **modifyTimestamp** hữu ích trong một số truy vấn giới hạn nhưng **không tự bảo đảm đồng bộ xóa entry, thứ tự toàn cục hoặc không bỏ sót**. Độ phân giải thời gian, replication và cập nhật đồng thời cần được đánh giá.

Trong Active Directory, **uSNChanged** có ngữ cảnh domain controller; không dùng USN đọc từ một DC làm watermark toàn cục cho các DC khác. Việc gắn cursor với endpoint/server và phục hồi khi failover phải theo cơ chế được AD công bố.

Thiết kế thường thấy: **full scan ban đầu → đọc feed nếu có → reconciliation định kỳ**. Khi cookie hết hạn hoặc cơ chế incremental không còn tin cậy, khởi tạo lại theo quy trình của server và đối soát projection.

## 6. Search scope, phân trang và tải LDAP server

Không nên gọi một lần **search()** để kéo toàn bộ directory lớn vào List. LDAP server có thể áp dụng size limit, timeout hoặc giới hạn tài nguyên; việc trả thiếu dữ liệu rất nguy hiểm nếu job hiểu nhầm các entry chưa đọc là đã bị xóa.

**Simple Paged Results Control (RFC 2696)** được nhiều LDAP server hỗ trợ nhưng không phải luôn có sẵn. Những nguyên tắc khi dùng:

1. Giới hạn **search base, scope, filter** và bộ attribute cần trả. Ví dụ chỉ quét người dùng trong **ou=people**.
2. Page size phải phù hợp giới hạn server và khả năng xử lý của ứng dụng; dùng batching và backpressure.
3. **Page cookie là opaque**. Không tự sửa cookie hoặc dùng nó cho query khác; phải xem xét vòng đời cookie và server affinity.
4. Các trang **không mặc nhiên tạo snapshot nhất quán** nếu có add/delete/rename trong khi quét. Reconciliation và feed phải xử lý khả năng đọc lặp/bỏ sót.
5. Đặt connect/read timeout, retry giới hạn, backoff và kiểm tra kết quả quét hoàn chỉnh trước khi quyết định xóa.

Trong Spring LDAP có các API search và **DirContextProcessor**, chẳng hạn bộ xử lý paged results ở phiên bản thư viện hỗ trợ. Cần kiểm thử cách lấy cookie và duy trì context với server thực; **LdapClient** và ODM không thay đổi nghĩa của paging/cookie ở LDAP server.

### Mã minh họa query và mapper cho nhánh nhỏ

Ví dụ sau phù hợp để giới thiệu ánh xạ và thử nghiệm một subtree nhỏ. **Không sử dụng phương thức này cho directory lớn**; production cần reader có phân trang hoặc change feed như đã mô tả.

~~~java
// infrastructure/ldap/DirectoryPersonSnapshot.java
package com.example.sync.infrastructure.ldap;

import com.example.sync.domain.DirectorySubject;

record DirectoryPersonSnapshot(
        DirectorySubject subject,
        String login,
        String displayName,
        String email
) {}
~~~

~~~java
// infrastructure/ldap/SpringLdapSmallDirectoryReader.java
package com.example.sync.infrastructure.ldap;

import com.example.sync.domain.DirectorySubject;
import java.util.List;
import org.springframework.ldap.core.ContextMapper;
import org.springframework.ldap.core.DirContextOperations;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;

final class SpringLdapSmallDirectoryReader {
    private final LdapTemplate ldap;

    SpringLdapSmallDirectoryReader(LdapTemplate ldap) {
        this.ldap = ldap;
    }

    List<DirectoryPersonSnapshot> readSmallSubtree() {
        LdapQuery query = LdapQueryBuilder.query()
                .base("ou=people")
                .attributes("uid", "cn", "mail", "entryUUID")
                .where("objectClass").is("inetOrgPerson");

        return ldap.search(query,
                (ContextMapper<DirectoryPersonSnapshot>) ctx -> {
                    DirContextOperations entry =
                            (DirContextOperations) ctx;
                    String uid = required(entry, "uid");
                    String id = required(entry, "entryUUID");
                    return new DirectoryPersonSnapshot(
                            new DirectorySubject("corp-openldap", id),
                            uid,
                            entry.getStringAttribute("cn"),
                            entry.getStringAttribute("mail"));
                });
    }

    private static String required(
            DirContextOperations entry, String attribute) {
        String value = entry.getStringAttribute(attribute);
        if (value == null || value.isBlank()) {
            throw new IllegalStateException(
                    "Thiếu thuộc tính LDAP bắt buộc: " + attribute);
        }
        return value;
    }
}
~~~

Giả định **ContextSource.base = dc=example,dc=org**, nên **base("ou=people")** tương đối với base đó. **entryUUID** có thể cần yêu cầu tường minh và quyền đọc operational attribute. Nếu thiếu, báo lỗi schema/ACL/dữ liệu thay vì âm thầm dùng DN làm stable ID.

**LdapQueryBuilder** escape giá trị filter; với input động không nối chuỗi kiểu **"(uid=" + userInput + ")"**. Khi dựng DN động, dùng **LdapNameBuilder** hoặc **LdapName**, không tự tách/ghép chuỗi theo dấu phẩy. DN escaping và filter escaping là hai quy tắc riêng.

## 7. Hợp đồng batch thay đổi độc lập với LDAP

Hợp đồng ở tầng ứng dụng nên mô tả **ý nghĩa của thay đổi**, không trả trực tiếp cookie LDAP, entry ODM hoặc Attributes:

~~~java
// application/DirectoryChange.java
package com.example.sync.application;

import com.example.sync.domain.DirectorySubject;

public record DirectoryChange(
        DirectorySubject subject,
        Kind kind,
        String login,
        String displayName,
        String email,
        String sourceRevision
) {
    public enum Kind { UPSERT, DISABLE, DELETE }
}
~~~

~~~java
// application/DirectoryBatch.java
package com.example.sync.application;

import java.util.List;

public record DirectoryBatch(
        List<DirectoryChange> changes,
        String nextCursor,
        boolean moreAvailable
) {}
~~~

~~~java
// application/DirectoryChangeSource.java
package com.example.sync.application;

public interface DirectoryChangeSource {
    DirectoryBatch readNext(String cursor, int maxBatchSize);
}
~~~

Trong ví dụ, **cursor** là một kiểu dữ liệu opaque ở port. Một feed cụ thể có thể trả cookie có thể resume, nhưng page cookie của một phiên full search **không tự là checkpoint bền vững**. Adapter phải quy định khi nào cursor hợp lệ, cách lưu và cách khởi tạo lại sau restore, failover hoặc expiry.

**sourceRevision không mặc định so sánh bằng String.compareTo**. Nếu nguồn cung cấp revision tăng dần theo subject với semantics rõ, tạo comparator tương ứng. Nếu không, chỉ lưu revision để chẩn đoán và dùng đối soát/đọc lại trạng thái đích, tránh suy diễn thứ tự từ timestamp hoặc chuỗi UUID.

Đặc biệt, một **full snapshot** không chứa DELETE event cho mỗi record vắng mặt. Đừng biến “không thấy user trong một trang” thành DELETE. Chỉ đánh giá các subject bị thiếu sau khi full scan đúng phạm vi hoàn tất và đã vượt qua guardrail.

## 8. Projection writer, idempotency và checkpoint

Job có thể bị dừng sau khi ghi một phần batch vào SQL. Nếu tiến checkpoint trước khi ghi toàn bộ batch, sự kiện bị mất. Nếu ghi xong nhưng crash trước checkpoint, cùng batch sẽ được chạy lại. Do đó projection phải **idempotent**.

~~~java
// application/ProjectionWriter.java
package com.example.sync.application;

public interface ProjectionWriter {
    void applyIdempotently(DirectoryChange change);
}
~~~

~~~java
// application/SyncCheckpointStore.java
package com.example.sync.application;

public interface SyncCheckpointStore {
    String load(String stream);
    void advanceIfCurrent(
            String stream,
            String expectedPrevious,
            String nextCursor);
}
~~~

~~~java
// application/DirectorySyncJob.java
package com.example.sync.application;

import org.springframework.stereotype.Service;

@Service
public final class DirectorySyncJob {
    private static final String STREAM = "corp-ldap-people";
    private final DirectoryChangeSource source;
    private final ProjectionWriter projection;
    private final SyncCheckpointStore checkpoints;

    public DirectorySyncJob(
            DirectoryChangeSource source,
            ProjectionWriter projection,
            SyncCheckpointStore checkpoints) {
        this.source = source;
        this.projection = projection;
        this.checkpoints = checkpoints;
    }

    public boolean runOneBatch() {
        String previous = checkpoints.load(STREAM);
        DirectoryBatch batch = source.readNext(previous, 200);

        for (DirectoryChange change : batch.changes()) {
            projection.applyIdempotently(change);
        }

        // Chỉ ghi checkpoint sau khi toàn bộ bản ghi đã được áp dụng.
        checkpoints.advanceIfCurrent(
                STREAM, previous, batch.nextCursor());
        return batch.moreAvailable();
    }
}
~~~

**Đây là thuật toán minh họa**, với giả định nguồn hỗ trợ một cursor có thể lưu và resume. Với paging cookie chỉ hợp lệ trong phiên truy vấn, cần luồng scan riêng thay vì lưu cookie vào checkpoint bền vững. **CheckpointStore** phải có compare-and-set hoặc cơ chế claim/lease để hai worker không vô tình tiến cùng một stream.

Projection SQL cần unique constraint theo **(directory_source, stable_id)**. Upsert phải có chính sách để event lặp không tạo bản ghi mới; nếu nguồn cung cấp revision so sánh được, dùng nó để ngăn event cũ ghi đè event mới. Nếu không, cân nhắc tra cứu lại từ nguồn hoặc reconcile, thay vì chọn event đến sau làm nguồn sự thật.

Không giữ transaction SQL mở trong lúc chờ mạng LDAP nếu không cần thiết. Có thể ghi mỗi entry trong transaction ngắn, sau đó commit checkpoint; hoặc ghi batch và checkpoint trong cùng transaction SQL khi cơ sở dữ liệu hỗ trợ. Với hai hệ thống độc lập, vẫn cần xử lý retry và crash.

## 9. Vì sao cần at-least-once và phục hồi sau crash?

~~~mermaid
sequenceDiagram
    participant Job as Sync job
    participant Feed as LDAP change source
    participant DB as Projection DB
    participant CP as Checkpoint store

    Job->>Feed: readNext(C0)
    Feed-->>Job: [A, B, C], next=C1
    Job->>DB: apply(A)
    DB-->>Job: committed
    Job->>DB: apply(B)
    DB-->>Job: committed
    Note over Job: Crash trước khi apply(C)
    Note over CP: Checkpoint vẫn C0
    Job->>Feed: readNext(C0) sau restart
    Feed-->>Job: [A, B, C]
    Job->>DB: applyIdempotently(A, B, C)
    Job->>CP: advance(C0, C1)
~~~

Nếu projection writer xử lý A và B idempotent, việc phát lại cả batch an toàn. Nếu consumer phát thêm thông báo hoặc event khi upsert, cần dedupe side effect, chẳng hạn lưu event ID và dùng **transactional outbox**. Không hứa “exactly once” xuyên LDAP, message bus và SQL nếu chưa có giao thức đảm bảo điều đó.

Một số cách chống lỗi:

- **Unique constraint** tránh tạo hai bản chiếu cùng subject khi hai job chạy đồng thời.
- **Checkpoint compare-and-set hoặc distributed lease** giới hạn worker được phép xử lý một stream.
- **Retry với backoff** cho lỗi mạng tạm thời; không áp dụng retry vô hạn cho schema/ACL.
- **Quarantine/dead-letter có kiểm soát** cho entry sai mapping, có khả năng sửa và replay.
- **Reconciliation** để phát hiện những thay đổi nguồn không được phát hoặc đã mất khỏi retention.

Khi một entry lỗi làm batch không thể hoàn tất, không được âm thầm bỏ qua và tiến checkpoint trừ khi đã có cơ chế lưu lỗi bền vững và replay rõ ràng. Cần theo dõi tuổi checkpoint và số bản ghi chưa xử lý.

## 10. Đọc snapshot và phát hiện xóa an toàn

Một đợt full scan có thể đánh dấu **generation** cho mỗi entry được thấy. Khi quét xong, những subject chưa xuất hiện trong generation mới có thể là ứng viên deprovision. Tuy nhiên phải đáp ứng toàn bộ điều kiện:

1. Scan đúng **search base, filter và scope** đã công bố, không vô tình đổi vùng quét.
2. Tất cả các trang đều được đọc thành công; không có size limit, timeout hoặc referral bị bỏ qua.
3. Job đánh dấu generation **COMPLETED** sau trang cuối, trước khi xét entry vắng mặt.
4. Chính sách đã tính đến LDAP replication lag, quyền đọc mới và khả năng entry tạm di chuyển OU.
5. Số lượng entry được đánh dấu xóa bất thường phải có **guardrail**, không tự động xóa hàng chục nghìn user do một lần cấu hình sai.

Một lần lookup không tìm thấy **không đủ** chứng minh account bị xóa. Directory có thể lỗi mạng, trả kết quả từ replica cũ, ACL che entry hoặc admin di chuyển OU ngoài phạm vi search. Quy trình delete/tombstone cần dữ kiện đáng tin cậy và chính sách retention.

Khi xóa hoặc khóa account, ứng dụng thường **không xóa lịch sử workspace, audit và nội dung đã tạo**. Có thể giữ một identity record dạng tombstone với stable ID và trạng thái không còn hoạt động. Quyền truy cập phải được thu hồi theo SLA, còn dữ liệu lịch sử xử lý theo chính sách bảo mật/lưu trữ.

## 11. Vòng đời create, update, rename, disable và delete

| Biến cố nguồn | Dấu hiệu nhận biết | Hành vi đích |
| --- | --- | --- |
| CREATE | Stable ID mới | Upsert bản chiếu; chỉ tạo membership nếu business rule cho phép |
| UPDATE | Cùng stable ID, attribute đổi | Chỉ cập nhật field do directory sở hữu |
| RENAME / MOVE | Cùng stable ID, DN/login đổi | Giữ liên kết nghiệp vụ, cập nhật login hoặc current DN |
| DISABLE | Trạng thái account thay đổi theo schema/IdM | Thu hồi quyền theo chính sách, giữ audit |
| DELETE | Feed/tombstone đáng tin cậy hoặc scan hoàn chỉnh | Deprovision/tombstone; không cascade delete tùy tiện |
| DELETE + CREATE với cùng login | Stable ID khác | Xem là principal mới trừ khi có ánh xạ đã xác minh |
| Đổi group | Membership thêm/bớt | Cập nhật projection và invalidate cache liên quan |

Đối với **group**, tùy server có **member**, **uniqueMember**, **memberOf**, nested group hoặc dynamic group. Không giả định **memberOf** luôn có; giá trị DN cần parse theo cú pháp LDAP và dữ liệu đa trị nên được xử lý theo tập hợp, không phụ thuộc thứ tự được trả về.

**Group LDAP không tự đồng nghĩa với workspace role**. Nếu ứng dụng sở hữu quyền OWNER/EDITOR, không để sync worker ghi đè chúng bằng group LDAP trừ khi đã có mapping quyền được phê duyệt.

## 12. Đồng bộ hai chiều và tránh vòng lặp

Một luồng có thẩm quyền thường trông như sau:

~~~text
HR phòng ban -> Provisioning service -> LDAP organizational attributes
LDAP identity -> Sync reader -> Application identity projection
Application role -> Application DB (không tự ghi LDAP group)
~~~

Nếu thực sự cần hai chiều, hãy định nghĩa:

- **Owner của từng trường** và tiêu chí xử lý khi hai nguồn phát dữ liệu khác nhau.
- **Origin/correlation ID** để consumer phân biệt thay đổi do chính mình gửi với thay đổi mới từ nguồn khác.
- **Idempotency key** khi một command được gửi lại sau timeout.
- **Version/expected state** khi cần tránh sự kiện cũ ghi đè thay đổi mới.
- **Phản ứng khi thất bại một phần**: ghi SQL thành công nhưng LDAP thất bại, hoặc ngược lại.

Với **LdapTemplate.modifyAttributes()**, một lệnh **REPLACE_ATTRIBUTE** cùng giá trị thường lũy đẳng về giá trị cuối của attribute; nó không bảo đảm không có audit/notification phụ. Sau timeout, server có thể đã ghi nhưng response bị mất. Nên xác minh trạng thái trước khi retry lệnh ghi. Nếu cập nhật có điều kiện là yêu cầu cứng, cần LDAP control hoặc cơ chế concurrency phù hợp được server hỗ trợ.

**@Transactional** của Spring đối với JPA không tự khiến lệnh LDAP thuộc cùng transaction. Với lệnh phát nhiều event, ứng dụng có thể dùng outbox và đối soát để đạt hiệu ứng nghiệp vụ nhất quán sau cùng.

## 13. Tính tươi mới và phân quyền

Độ trễ đồng bộ ảnh hưởng khác nhau theo dữ liệu:

| Dữ liệu | Độ trễ có thể chấp nhận | Hệ quả khi chậm |
| --- | --- | --- |
| Tên hiển thị/ảnh đại diện | Có thể vài phút theo SLA | UI hiển thị tên cũ |
| Email nhận thông báo | Cần chặt hơn theo chức năng | Gửi nhầm địa chỉ |
| Group phục vụ thống kê | Có thể theo batch | Dashboard chậm cập nhật |
| Group quyết định truy cập tài liệu mật | Theo SLA thu hồi quyền rõ ràng | Tài khoản bị thu hồi vẫn có quyền |
| Trạng thái account bị khóa | Chính sách an ninh riêng | Cho phép người không còn hợp lệ truy cập |

Ví dụ tổ chức yêu cầu thu hồi quyền trong **30 giây** nhưng LDAP replica có thể chậm **2 phút**. Giảm TTL cache projection xuống 30 giây **không đáp ứng SLA** nếu nguồn đọc chưa thấy thay đổi. Cần chọn nguồn có độ tươi mới phù hợp, thông báo thu hồi đáng tin cậy, cơ chế session/token revocation hoặc authorization flow khác.

Khi LDAP không sẵn sàng, không tự biến **không xác minh được** thành **có quyền**. Với dữ liệu nhạy cảm, chính sách **fail closed** hoặc thời hạn tin cậy cụ thể là yêu cầu của application/security, không thuộc mapper.

## 14. Cấu hình kết nối, TLS và kiểm soát tài nguyên

Ví dụ cấu hình Spring Boot với LDAPS; credential được cung cấp bằng secret ở môi trường triển khai:

~~~yaml
spring:
  ldap:
    urls:
      - ldaps://ldap.example.org:636
    base: dc=example,dc=org
    username: ${LDAP_BIND_DN}
    password: ${LDAP_BIND_PASSWORD}
~~~

Các điểm phải bảo vệ:

1. Dùng **LDAPS** hoặc **StartTLS** với certificate, hostname validation và truststore hợp lệ; không tắt TLS verification khi gặp lỗi.
2. Reader chỉ có quyền đọc những subtree/attribute cần thiết; writer có ACL ghi tối thiểu và có thể dùng principal riêng.
3. **Connection timeout/read timeout**, giới hạn số connection, page size, search scope và retry limit được cấu hình tập trung trong hạ tầng.
4. **Pooling** phải tương thích TLS/StartTLS và trạng thái bind; không tái sử dụng tùy tiện connection đã xác thực bằng principal khác.
5. Không đưa password, **userPassword**, credential, raw filter chứa dữ liệu nhạy cảm hay toàn bộ entry vào log/queue/dead-letter.
6. Không tải toàn bộ directory vào RAM hoặc giữ transaction SQL mở suốt quá trình gọi LDAP nhiều trang.

**LDAP authentication BindRequest** khác **LdapTemplate.bind() tạo entry**. Khi provisioning, dùng thao tác tạo entry đúng API và bảo vệ credential; không retry dồn dập việc xác thực người dùng vì có thể tác động bộ đếm đăng nhập sai/khóa tài khoản.

## 15. Phân loại lỗi và giám sát job

| Nhóm lỗi | Ví dụ | Phản ứng |
| --- | --- | --- |
| Tạm thời | Timeout, connection reset, server unavailable | Retry có giới hạn, exponential backoff + jitter, giữ checkpoint |
| Xác thực/ACL | Service account sai, không đọc được operational attribute | Cảnh báo cấu hình/quyền, tránh retry liên tục |
| Schema/dữ liệu | Thiếu stable ID, objectGUID sai kiểu | Quarantine, sửa mapping/dữ liệu rồi replay |
| Cursor | Cookie hết hạn hoặc server đổi | Recovery theo cơ chế nguồn hỗ trợ, đối soát |
| Xung đột | Hai nguồn ghi khác nhau, event cũ đến sau | Áp owner-field, version policy hoặc đối soát |
| Projection DB | Unique conflict, SQL outage | Transaction an toàn, không advance checkpoint trước khi áp dụng |
| Ghi LDAP không rõ kết quả | Modify timeout sau khi server có thể đã ghi | Đọc lại xác minh, không retry mù |

Cần theo dõi **sync lag**, checkpoint age, số entry xử lý, số event trùng, lỗi/quarantine, số lần retry, thời gian LDAP search, lượng dữ liệu mỗi trang, thời gian full reconciliation và các thay đổi DELETE/DISABLE bất thường. Đo p95/p99 latency để nhận biết LDAP quá tải khi quét.

Metric label nên dùng **directory source, operation, error code**, không dùng login, email hay DN đầy đủ vì vừa tăng cardinality vừa gây lộ dữ liệu. Dùng correlation ID và log có phân quyền để chẩn đoán.

## 16. Kiểm thử theo từng ranh giới

**Unit test orchestration:** fake **DirectoryChangeSource**, **ProjectionWriter**, **SyncCheckpointStore**. Với cursor C0 và batch A/B/C, cho A và B ghi thành công, C ném lỗi. Checkpoint phải còn C0. Khi chạy lại, A/B được apply idempotent, C thành công rồi mới tiến tới C1. Test thêm tranh chấp compare-and-set giữa hai worker, sự kiện trùng và sự kiện cũ đến sau.

**Integration test Spring LDAP** cần LDAP test server hỗ trợ schema và controls tương ứng:

| Kịch bản | Kỳ vọng |
| --- | --- |
| Đọc entry hợp lệ | Mapping đúng uid, cn, mail, entryUUID |
| Thiếu stable ID | Lỗi dữ liệu/quyền, không tạo ID giả từ DN |
| Rename/move OU | Projection vẫn giữ DirectorySubject |
| Full scan thất bại giữa trang | Không xóa các entry chưa thấy |
| Phân trang/size limit | Không coi partial result là full snapshot |
| Cookie/change feed hết hạn | Có cách recovery và reconciliation rõ ràng |
| Xóa account | Deprovision/tombstone đúng policy, không xóa audit |
| Sự kiện đến lặp hoặc sai thứ tự | Không trùng record và không ghi đè dữ liệu mới hơn |
| Group thay đổi | Tập membership/authorization cập nhật theo SLA |
| LDAP mất kết nối, sai bind, sai ACL hoặc TLS lỗi | Lỗi được phân loại và checkpoint giữ nguyên |
| Login có ký tự đặc biệt | Filter được escape đúng, không LDAP injection |

**Failure injection:** crash sau khi đọc batch, sau khi ghi một phần, sau khi ghi đủ nhưng trước checkpoint, và sau khi checkpoint nhưng trước response. Thử chuyển replica trong lúc sync, cấp quyền đọc khác nhau, đổi OU hàng loạt và nhân viên bị xóa rồi tạo lại cùng login.

Đối với **RFC 4533** hoặc **AD DirSync**, cần integration test với server/control thật. LDAP test server nhúng có thể giúp kiểm tra mapping nhưng không tự chứng minh semantics của change feed, cookie, tombstone hoặc replication trong production.

## 17. Các lỗi thiết kế phổ biến

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| DN/email làm primary key | Rename/move hoặc đổi email tạo danh tính mới giả | Stable ID + source ID |
| Coi modifyTimestamp là feed đầy đủ | Bỏ sót xóa, sai thứ tự, lệch replica | Feed được hỗ trợ + reconciliation |
| Một lần search toàn directory | Hết bộ nhớ, size limit, kết quả thiếu | Paging, batch, giới hạn scope và backpressure |
| Ghi checkpoint trước projection | Mất event khi crash | Apply-before-checkpoint |
| Không idempotent khi retry | Duplicate record, side effect lặp | Unique constraint, dedupe/outbox |
| Một lần scan rỗng đồng nghĩa xóa hết | Sai ACL/outage gây xóa hàng loạt | Chỉ xét DELETE sau scan hoàn chỉnh có guardrail |
| Ghi đè mọi field của DB bằng LDAP | Mất vai trò/dữ liệu ứng dụng sở hữu | Bản đồ owner-field |
| Event đến sau được coi mới hơn | Event cũ có thể trễ | Version có bảo đảm hoặc đối soát |
| Retry mọi LDAP modify sau timeout | Ghi lặp, conflict | Xác minh trạng thái/idempotent command |
| Dùng group cache cũ cấp quyền | Thu hồi quyền có hiệu lực chậm | Freshness SLA, fail closed khi cần |
| Gộp lookup rỗng với lỗi kết nối | False delete/deprovision | Phân loại absent, unavailable, ACL, schema |

## 18. Bài tập thiết kế

Một doanh nghiệp dùng OpenLDAP quản lý 200.000 nhân viên, HR quản lý phòng ban và ứng dụng Spring Boot quản lý workspace membership trên PostgreSQL. Hệ thống chạy ba instance, có hai LDAP replica và hỗ trợ paged search. Nhóm **restricted-readers** quyết định truy cập tài liệu mật. Nhân viên thường được chuyển OU, đổi email hoặc nghỉ việc.

Hãy thiết kế:

1. **Bản đồ source of truth:** HR, LDAP và ứng dụng lần lượt sở hữu trường nào? Trường nào không được đồng bộ ngược?
2. **Định danh:** chọn stable ID phù hợp và mô tả cách giữ liên kết khi rename/move; xử lý xóa rồi tạo lại cùng login ra sao?
3. **Khởi tạo dữ liệu:** full scan có paging, search base, page size, giới hạn tải và cách xác nhận một vòng scan đã hoàn tất.
4. **Đồng bộ incremental:** chọn feed nếu server hỗ trợ, mô tả cookie/checkpoint và đường phục hồi khi cursor hết hạn.
5. **At-least-once:** thiết kế apply idempotent, compare-and-set checkpoint và tình huống crash sau khi ghi A/B nhưng trước C.
6. **Deprovision:** xác định trường hợp nào có thể đánh dấu account deleted/disabled và cách giữ lịch sử nghiệp vụ.
7. **Phân quyền:** đặt SLA thu hồi quyền; xử lý replica trễ hơn SLA, cache cũ và LDAP outage.
8. **Kiểm thử:** xây ma trận ca cho event trùng/sai thứ tự, partial scan, TLS, ACL, connection reset, migration stable ID và full reconciliation.

Trước khi chấp nhận hệ thống, hãy kiểm chứng: **quyền sở hữu dữ liệu rõ ràng**, **định danh bền vững**, **checkpoint an toàn khi crash**, **không deprovision nhầm**, và **có cơ chế đối soát phát hiện sự kiện bị bỏ lỡ**.

**Kết luận:** đồng bộ LDAP với hệ thống khác đòi hỏi thiết kế dữ liệu và độ tin cậy, không chỉ viết một truy vấn tìm kiếm. Spring LDAP cung cấp kết nối và thao tác directory qua **ContextSource**, **LdapTemplate**, **LdapClient** hoặc ODM; tầng ứng dụng quyết định nguồn dữ liệu chính, khóa định danh, batch/cursor, idempotency, conflict, vòng đời tài khoản và chính sách phân quyền. Khi kết hợp kiểm thử lỗi, TLS, kiểm soát tải và reconciliation, dữ liệu có thể được duy trì nhất quán theo các cam kết thực tế của từng hệ thống.
