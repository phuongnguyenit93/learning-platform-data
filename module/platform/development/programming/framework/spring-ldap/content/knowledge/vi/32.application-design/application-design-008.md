# Xử lý eventual consistency và thay đổi ngoài ứng dụng

## 1. Một thay đổi đúng ở LDAP nhưng ứng dụng vẫn hiển thị dữ liệu cũ

Giả sử doanh nghiệp quản lý nhân viên bằng LDAP và sử dụng ứng dụng Spring Boot để quản lý workspace. Hệ thống có một directory có replica, một cache hồ sơ và một database chứa bản chiếu (projection) của thông tin nhân viên.

Vào lúc 10:00, quản trị viên dùng công cụ IdM bên ngoài ứng dụng để đổi email nhân viên Lan từ **lan-old@example.org** sang **lan@example.org**. LDAP server nhận thao tác thành công. Tuy nhiên:

- Replica mà ứng dụng đang đọc chưa nhận thay đổi.
- Cache trong Spring Boot còn giữ email cũ.
- Tác vụ đồng bộ chưa chạy tới bản ghi này nên PostgreSQL cũng chưa cập nhật.
- Người dùng mở trang hồ sơ lúc 10:01 và vẫn nhìn thấy địa chỉ cũ.

Không có thành phần nào nhất thiết hỏng trong tình huống đó. Các hệ thống chỉ **quan sát cùng một thay đổi tại các thời điểm khác nhau**. Đây là một ví dụ của **eventual consistency**: nếu các thay đổi ngừng xảy ra và mọi cơ chế truyền, làm mới, đối soát tiếp tục hoạt động thành công, các bản sao cuối cùng có thể hội tụ về trạng thái được nguồn dữ liệu có thẩm quyền công bố.

Nhưng **eventual consistency không có nghĩa là chấp nhận dữ liệu cũ vô hạn**. Người thiết kế phải xác định loại dữ liệu, độ trễ được phép, cách phát hiện thay đổi từ bên ngoài và cách bảo vệ thao tác nhạy cảm khi không xác minh được trạng thái mới.

Trong chương **Thiết kế ứng dụng** của **Spring LDAP**, bài học tập trung vào các ranh giới nhất quán khi làm việc với **DN, schema, filter và entry** qua **ContextSource**, **LdapTemplate**, **LdapClient** hoặc ODM. Ví dụ dùng Java 17 và OpenLDAP để minh họa; quy tắc triển khai cần điều chỉnh theo topology và schema thật.

## 2. Phân biệt các tầng có thể chứa trạng thái cũ

~~~mermaid
flowchart LR
    ADMIN["IdM / quản trị viên bên ngoài"]
    PRIMARY[("LDAP nguồn ghi")]
    REPLICA[("LDAP replica")]
    READER["Spring LDAP adapter"]
    CACHE["Cache hồ sơ"]
    SYNC["Sync / reconciliation"]
    DB[("Application projection DB")]
    USE["Use case / REST"]

    ADMIN --> PRIMARY
    PRIMARY -. "replication" .-> REPLICA
    REPLICA --> READER
    READER --> CACHE
    READER --> SYNC --> DB
    CACHE --> USE
    DB --> USE
~~~

| Ranh giới | Dữ liệu có thể cũ ở đâu? | Cách làm mới thường gặp |
| --- | --- | --- |
| **LDAP write → replica** | Bản sao directory chưa áp dụng thay đổi | Cơ chế replication của server; theo dõi lag và lựa chọn endpoint |
| **LDAP → cache ứng dụng** | Kết quả tra cứu **cn/mail** còn trong TTL | Expire-after-write, invalidation, đọc lại |
| **LDAP → projection SQL** | Batch đồng bộ, event hoặc checkpoint chưa xử lý | Incremental feed, polling, reconciliation |
| **Projection → phiên/token** | Session chứa quyền được tính tại thời điểm cũ | Quy tắc revalidation, thu hồi session/token hoặc phiên ngắn |
| **Ứng dụng → công cụ ngoài ứng dụng** | Thay đổi do app ghi chưa được hệ thống khác nhìn thấy | Cơ chế xác minh, phát event và SLA truyền dữ liệu |

Một transaction SQL có thể bảo đảm nhất quán trong database của ứng dụng nhưng **không tự bao gồm LDAP, LDAP replica, cache hay message broker**. Một thao tác modify một entry LDAP có thể được server thực hiện nguyên tử ở phạm vi entry đó, nhưng không có transaction tự động bao trùm các hệ thống trên.

**Điểm thiết kế quan trọng:** nếu một trường hợp sử dụng đọc từ projection thì nó đang đọc *dữ liệu quan sát được trước đây*, không mặc nhiên đọc trạng thái hiện tại của directory.

## 3. Xác định nguồn dữ liệu chính và bên có quyền sửa

Hãy xây một **bản đồ quyền sở hữu dữ liệu** trước khi quyết định đồng bộ hai chiều. Ví dụ:

| Trường / quy tắc | Nguồn ghi có thẩm quyền | Ứng dụng được làm gì? |
| --- | --- | --- |
| **uid**, định danh entry, trạng thái tài khoản | LDAP / IdM | Đọc, tham chiếu, phản ánh trạng thái |
| **cn**, **mail** theo chính sách nhân sự | HR/IdM → LDAP | Hiển thị và cache trong giới hạn freshness |
| Nhóm tổ chức LDAP | LDAP / IdM | Đọc làm dữ kiện cho policy, theo schema cụ thể |
| **OWNER/EDITOR/VIEWER** trong workspace | Ứng dụng nghiệp vụ | Tự cập nhật theo aggregate và transaction của app |
| Lịch sử đã thực hiện tác vụ | Ứng dụng / audit system | Giữ theo chính sách lưu trữ, không cascade xóa khi LDAP mất entry |

Nếu **mail** do IdM sở hữu nhưng ứng dụng vẫn cho phép sửa email, phải có lệnh ghi qua port được ủy quyền hoặc một quy trình gửi yêu cầu tới IdM. **Không sửa bản sao SQL rồi giả định nó sẽ luôn ghi ngược LDAP.**

Khi hai hệ thống cùng được phép ghi một thuộc tính, phải định nghĩa chính sách xung đột:

1. Bên nào có thẩm quyền cuối cùng?
2. Có thể kiểm tra phiên bản/kỳ vọng trước khi ghi không?
3. Các sự kiện có thể đến trùng hoặc sai thứ tự không?
4. Làm thế nào ngăn thay đổi từ ứng dụng quay lại chính ứng dụng thành một lệnh ghi mới?
5. Khi không đối chiếu được, có giữ bản ghi ở trạng thái cần xử lý thủ công không?

Quy tắc “bản ghi đến sau sẽ thắng” thường sai nếu thứ tự nhận sự kiện khác thứ tự cập nhật ở nguồn.

## 4. Tính tươi mới là hợp đồng của từng use case

Thay vì nói “hệ thống eventual consistent”, hãy quy định **độ cũ tối đa được phép** cho từng hành vi:

| Use case | Freshness contract minh họa | Khi không đáp ứng |
| --- | --- | --- |
| Hiển thị tên nhân viên | Có thể cũ tối đa 5 phút | Hiển thị dữ liệu cũ hoặc nhãn đang làm mới |
| Hiển thị email liên hệ | Có thể cũ 1 phút theo yêu cầu vận hành | Tải lại nguồn, tránh dùng email cũ cho hành động quan trọng |
| Mời người mới vào workspace | Phải xác minh ID tài khoản ở nguồn đủ tin cậy | Hoãn hoặc báo lỗi tạm thời |
| Kiểm tra quyền đọc tài liệu mật | Thu hồi quyền phải có hiệu lực trong SLA an ninh riêng | Từ chối khi không thể xác minh theo chính sách |
| Xác thực mật khẩu | Dùng cơ chế bind/IdP hiện hành | Không dùng cache hồ sơ làm bằng chứng xác thực |
| Lập báo cáo thống kê nhóm | Có thể dùng snapshot theo kỳ | Công bố thời điểm snapshot |

Các thời gian trong bảng là **ví dụ**, không phải khuyến nghị chung. Nếu hệ thống yêu cầu thu hồi quyền trong 30 giây nhưng replica có thể chậm 2 phút, một cache TTL 30 giây không giải quyết được vấn đề.

Một ngân sách độ trễ để xem xét:

~~~text
Độ cũ dữ liệu tại thời điểm sử dụng có thể chịu ảnh hưởng bởi:
  Trễ cập nhật từ hệ thống sở hữu trường vào LDAP
  + Trễ LDAP replication đến endpoint đang đọc
  + Trễ job/queue đồng bộ vào projection
  + Thời gian dữ liệu tồn tại trong cache/phiên
~~~

Đây là mô hình để **phân bổ ngân sách và đo kiểm**, không phải công thức chính xác nếu các cơ chế chạy song song. Đặc biệt, thiếu event, job bị dừng hoặc lỗi ACL kéo dài có thể làm dữ liệu **không hội tụ**; phải có cảnh báo và reconciliation.

## 5. Định danh bất biến, DN và vị trí entry là hai chuyện khác nhau

Một người có thể chuyển từ:

~~~text
uid=lan,ou=engineering,dc=example,dc=org
~~~

sang:

~~~text
uid=lan,ou=operations,dc=example,dc=org
~~~

DN thay đổi, trong khi danh tính nguồn vẫn là một entry nếu directory giữ nguyên ID. **Không dùng DN, email hoặc tên đăng nhập làm định danh bất biến mặc định**. Nhiều OpenLDAP server cung cấp **entryUUID**; Active Directory thường dùng **objectGUID** (dữ liệu nhị phân). Phải xác minh schema, khả năng đọc thuộc tính và tính ổn định theo server cụ thể.

~~~java
// domain/DirectorySubject.java
package com.example.identity.domain;

import java.util.Objects;

public record DirectorySubject(String sourceId, String entryId) {
    public DirectorySubject {
        Objects.requireNonNull(sourceId, "sourceId");
        Objects.requireNonNull(entryId, "entryId");
        if (sourceId.isBlank() || entryId.isBlank()) {
            throw new IllegalArgumentException("Directory subject không hợp lệ");
        }
    }
}
~~~

Trong database đích, unique constraint theo **(source_id, entry_id)** giúp liên kết danh tính qua rename/move. **currentDn**, **login**, **displayName** và **email** là thuộc tính cập nhật được, không phải khóa tham chiếu lịch sử.

Nếu entry bị xóa rồi tạo mới với cùng login hoặc chuyển sang directory khác, ID có thể đổi. Không tự nối hai entry thành một người chỉ vì email giống nhau; cần quy trình migration và đối soát đã được ủy quyền.

## 6. Mô hình dữ liệu có thông tin quan sát

Một projection chỉ chứa **email hiện tại** mà không biết thời điểm và nguồn quan sát khiến người dùng khó phân biệt dữ liệu mới/cũ. Đối với những nơi cần đánh giá freshness, nên lưu **observedAt** và thông tin phiên bản *nếu nguồn có bảo đảm tương ứng*.

~~~java
// application/DirectorySnapshot.java
package com.example.identity.application;

import com.example.identity.domain.DirectorySubject;
import java.time.Instant;

public record DirectorySnapshot(
        DirectorySubject subject,
        String login,
        String displayName,
        String email,
        String sourceRevision,
        Instant observedAt
) {}
~~~

Phân biệt:

- **sourceRevision:** token phiên bản/định danh thay đổi nếu **LDAP server hoặc feed thực sự cung cấp**. Giá trị có thể chỉ là opaque token; không được tự dùng so sánh từ điển để kết luận mới hơn.
- **observedAt:** thời điểm ứng dụng quan sát thấy entry. Nó phản ánh thời gian đọc, **không chứng minh dữ liệu đã được sửa trên LDAP lúc đó**.
- **lastSyncedAt:** thời điểm projection ghi thành công trong SQL. Khác với thời điểm sửa thuộc tính tại nguồn.
- **currentDn:** nếu cần để thao tác với entry, lưu dưới dạng metadata của adapter/projection hạ tầng; DN có thể đổi sau một lần rename/move và không cần xuất hiện trong port nghiệp vụ.
- **projectionState:** trạng thái do ứng dụng quản lý như CURRENT, STALE, NEEDS_RECONCILIATION; không được giả thành trạng thái tài khoản LDAP.

Operational attribute **modifyTimestamp** có ích để ghi nhận thông tin thay đổi nếu được server hỗ trợ và principal có quyền đọc. Tuy nhiên timestamp này **không tự bảo đảm thứ tự toàn cục**, không giải quyết mọi trường hợp replication và không mô tả được entry đã xóa. Đừng dùng nó như cơ chế compare-and-swap hoặc watermark toàn cục nếu server không cam kết.

## 7. Port đọc trạng thái hiện quan sát được

Ví dụ sử dụng một **DirectoryCurrentReader** độc lập với Spring LDAP. Port được định nghĩa theo danh tính bền vững, tránh yêu cầu domain tự ghép filter hoặc DN:

~~~java
// application/DirectoryCurrentReader.java
package com.example.identity.application;

import com.example.identity.domain.DirectorySubject;
import java.util.Optional;

public interface DirectoryCurrentReader {
    Optional<DirectorySnapshot> findBySubject(DirectorySubject subject);
}
~~~

**Optional.empty()** chỉ có nghĩa **không có entry trong phạm vi truy vấn đã hoàn tất thành công**. Nó chưa khẳng định tài khoản đã bị xóa khỏi mọi nhánh directory hay hệ thống đã có thẩm quyền vô hiệu hóa. Nếu server timeout, bind thiếu quyền, search base sai hoặc mapping thiếu thuộc tính bắt buộc, adapter phải trả lỗi hạ tầng/dữ liệu riêng, không trả Optional rỗng.

Đối với ứng dụng có nhiều directory, **sourceId** phải xác định một ContextSource/reader hợp lệ. Không cho người dùng tùy ý đưa LDAP URL, raw filter hoặc DN nhằm mở rộng phạm vi tra cứu.

## 8. Đọc dữ liệu bằng LdapTemplate ở tầng adapter

Ví dụ OpenLDAP bên dưới tìm một subject bằng **entryUUID** trong phạm vi **ou=people**. Đây là một **giả định schema và search scope**, cần kiểm tra server có hỗ trợ equality search trên attribute đó, có trả operational attribute và entry có thể di chuyển ra khỏi scope hay không.

~~~java
// infrastructure/ldap/SpringLdapCurrentReader.java
package com.example.identity.infrastructure.ldap;

import com.example.identity.application.DirectoryCurrentReader;
import com.example.identity.application.DirectorySnapshot;
import com.example.identity.domain.DirectorySubject;
import java.time.Clock;
import java.time.Instant;
import java.util.List;
import java.util.Optional;
import org.springframework.ldap.core.ContextMapper;
import org.springframework.ldap.core.DirContextOperations;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;
import org.springframework.stereotype.Repository;

@Repository
public final class SpringLdapCurrentReader
        implements DirectoryCurrentReader {

    private final LdapTemplate ldap;
    private final Clock clock;

    public SpringLdapCurrentReader(LdapTemplate ldap, Clock clock) {
        this.ldap = ldap;
        this.clock = clock;
    }

    @Override
    public Optional<DirectorySnapshot> findBySubject(
            DirectorySubject subject) {
        if (!"corp-openldap".equals(subject.sourceId())) {
            throw new IllegalArgumentException("Directory source không hỗ trợ");
        }

        LdapQuery query = LdapQueryBuilder.query()
                .base("ou=people")
                .attributes("entryUUID", "uid", "cn",
                            "mail", "modifyTimestamp")
                .where("entryUUID").is(subject.entryId());

        List<DirectorySnapshot> rows = ldap.search(
                query,
                (ContextMapper<DirectorySnapshot>) context -> {
                    DirContextOperations entry =
                            (DirContextOperations) context;
                    String id = required(entry, "entryUUID");
                    String login = required(entry, "uid");
                    Instant observedAt = clock.instant();

                    return new DirectorySnapshot(
                            new DirectorySubject("corp-openldap", id),
                            login,
                            entry.getStringAttribute("cn"),
                            entry.getStringAttribute("mail"),
                            entry.getStringAttribute("modifyTimestamp"),
                            observedAt);
                });

        if (rows.size() > 1) {
            throw new IllegalStateException(
                    "Directory trả nhiều entry cho một stable ID");
        }
        return rows.stream().findFirst();
    }

    private static String required(
            DirContextOperations entry, String attribute) {
        String value = entry.getStringAttribute(attribute);
        if (value == null || value.isBlank()) {
            throw new IllegalStateException(
                    "Thiếu attribute bắt buộc: " + attribute);
        }
        return value;
    }
}
~~~

Trong cấu hình minh họa, **ContextSource.base = dc=example,dc=org**, vì vậy **base("ou=people")** là tương đối. Nếu entry có thể move sang subtree khác, truy vấn này sẽ không thấy nó; phải có chiến lược search scope rộng đúng ACL, hoặc nguồn change feed giúp cập nhật vị trí. Không suy luận DELETE khi chỉ thấy kết quả rỗng trong nhánh hẹp.

Ví dụ dùng một bean **Clock** do ứng dụng tự cấu hình (Spring Boot không mặc định tạo bean Clock cho mọi dự án):

~~~java
// Trong một lớp @Configuration của ứng dụng:
@org.springframework.context.annotation.Bean
java.time.Clock directoryClock() {
    return java.time.Clock.systemUTC();
}
~~~

**LdapQueryBuilder** escape giá trị filter; nếu cần dựng DN từ thành phần động, dùng **LdapNameBuilder**. Không ghép chuỗi filter hoặc tách DN theo dấu phẩy. Với Active Directory, đổi mapper sang **objectGUID** nhị phân và xây truy vấn theo khả năng AD; không sao chép máy móc đoạn code OpenLDAP.

Ví dụ này tập trung vào hợp đồng quan sát, chưa triển khai mapping exception. Trong sản phẩm, các exception của **org.springframework.ldap** và JNDI phải được chuyển tại adapter thành **DirectoryUnavailable**, **DirectoryAccessDenied** hoặc **DirectoryInvalidData** thuộc ứng dụng.

## 9. Application service đối soát từng subject

Một tác vụ refresh có thể đọc bản mới và cập nhật chỉ những trường do directory sở hữu, qua port **DirectoryProjectionWriter**:

~~~java
// application/DirectoryProjectionWriter.java
package com.example.identity.application;

public interface DirectoryProjectionWriter {
    void observe(DirectorySnapshot snapshot);
}
~~~

~~~java
// application/DirectoryProfileRefresh.java
package com.example.identity.application;

import com.example.identity.domain.DirectorySubject;
import org.springframework.stereotype.Service;

@Service
public final class DirectoryProfileRefresh {
    public enum Outcome { OBSERVED, NOT_FOUND_IN_SCOPE }

    private final DirectoryCurrentReader current;
    private final DirectoryProjectionWriter projection;

    public DirectoryProfileRefresh(
            DirectoryCurrentReader current,
            DirectoryProjectionWriter projection) {
        this.current = current;
        this.projection = projection;
    }

    public Outcome refresh(DirectorySubject subject) {
        return current.findBySubject(subject)
                .map(snapshot -> {
                    projection.observe(snapshot);
                    return Outcome.OBSERVED;
                })
                .orElse(Outcome.NOT_FOUND_IN_SCOPE);
    }
}
~~~

**DirectoryProjectionWriter** được hiện thực bằng SQL/JPA adapter. Adapter này cần upsert theo **(sourceId, entryId)** và **chỉ ghi các field mà directory sở hữu**. Không ghi đè vai trò workspace, cài đặt riêng, số lần thao tác hoặc lịch sử audit do ứng dụng sở hữu.

**NOT_FOUND_IN_SCOPE không phải lệnh xóa.** Một entry có thể vừa move OU, replica chưa đồng bộ hoặc quyền tìm kiếm thay đổi. Xóa/vô hiệu hóa cần sự kiện có thẩm quyền hoặc quy trình reconciliation đầy đủ, với ngưỡng an toàn riêng.

Đoạn mã chỉ chứng minh ranh giới dữ liệu; nếu nhiều worker cùng quan sát từ các replica khác nhau, **đọc rồi ghi SQL theo thứ tự đến có thể làm dữ liệu quay lại phiên bản cũ**. Muốn kiểm soát, projection cần so version do nguồn bảo đảm, đảm bảo thứ tự xử lý per subject, hoặc xác minh lại với nguồn đáng tin cậy trước khi thay thế.

## 10. Phát hiện thay đổi do công cụ bên ngoài tạo ra

Một ứng dụng chỉ invalidate cache khi **chính ứng dụng** thực hiện modify sẽ bỏ lỡ các thay đổi từ IdM, script vận hành hoặc LDAP console. Có ba nhóm chiến lược:

| Cơ chế | Ưu điểm | Giới hạn / điều kiện |
| --- | --- | --- |
| **Change notification / incremental feed** | Độ trễ thấp khi nguồn hỗ trợ | Control và cookie phụ thuộc server, quyền, retention, failover |
| **Polling có watermark** | Dễ bắt đầu trong bài toán nhỏ | Timestamp thiếu độ phân giải, replication lag và delete khó xử lý đúng |
| **Full reconciliation định kỳ** | Phục hồi event bị mất và phát hiện lệch | Tốn tài nguyên, cần paging và bảo vệ chống false delete |

**RFC 4533 LDAP Content Synchronization** có thể được hỗ trợ ở một số server OpenLDAP; **DirSync** của Active Directory là cơ chế khác. Không giả định mọi LDAP server có change feed đồng nhất. Một LDAP control chỉ nên dùng khi adapter đã xác minh server hỗ trợ, cookie có semantics gì, cách resume và yêu cầu gắn với replica.

Khi bắt buộc polling theo **modifyTimestamp**, phải hiểu giới hạn: giá trị có thể không đủ phân giải, các sửa đổi xảy ra cùng timestamp, xóa entry không còn để truy vấn, và một watermark đơn giản có thể bỏ sót thay đổi khi replication trễ. Có thể dùng khoảng chồng lấn (*overlap window*) và upsert idempotent để giảm rủi ro, nhưng vẫn cần full reconciliation và không được quảng bá cơ chế đó là CDC hoàn chỉnh.

Các event có thể bị gửi trùng, mất hoặc đến sai thứ tự. Nếu nguồn cung cấp revision có thứ tự đáng tin cậy cho subject, dùng nó để tránh áp dụng event cũ. Nếu không, coi event là tín hiệu **cần đọc lại current state**, không tự dùng payload event cũ làm nguồn ghi mới.

## 11. Xử lý thay đổi ngoài ứng dụng khi đang có cache

Giả sử ứng dụng cache email 5 phút. Công cụ IdM thay đổi email tại LDAP nhưng ứng dụng không biết để invalidate. Cho đến khi TTL hết, request có thể đọc email cũ.

Các lựa chọn:

- **Expire-after-write:** đặt thời hạn tuyệt đối cho mỗi bản cache, không gia hạn chỉ vì người dùng đọc liên tục.
- **Event invalidation:** khi nhận thông báo thay đổi đáng tin cậy, loại key theo subject và các index phụ thuộc như login/email.
- **Periodic refresh:** nạp lại những subject quan trọng theo lịch có giới hạn tải.
- **Cache bypass theo use case:** thao tác nhạy cảm gọi reader có freshness phù hợp thay vì dùng profile cache.
- **Stale-if-error có điều kiện:** chỉ cho phép với dữ liệu hiển thị ít rủi ro, kèm timestamp và giới hạn tuổi dữ liệu cũ.

**Negative cache** (kết quả không tìm thấy) cũng có thể sai ngay khi tài khoản mới được tạo. Vì vậy negative TTL thường ngắn và phải invalidate sau provisioning khi sự kiện có thể tin cậy.

Một race quan trọng: request A đang load bản cũ từ LDAP replica; event B báo thay đổi và invalidate cache; A trả về muộn và có thể làm bản cũ xuất hiện lại. Invalidation một lần **không tự tạo cam kết thứ tự**. Nếu cần mạnh hơn, dùng version/epoch theo subject, chặn bản cũ ghi lại và test tình huống load–invalidate đan xen.

Ở ứng dụng nhiều instance, invalidate cache của một node không xóa cache ở các node khác. Cần broadcast, cache chia sẻ phù hợp hoặc TTL như tuyến phòng vệ. Tuy nhiên cache phân tán vẫn phải có chính sách tươi mới và bảo vệ dữ liệu cá nhân.

## 12. Read-your-writes: ứng dụng vừa sửa thì đọc thấy gì?

Một use case ghi **mail=lan@example.org** lên LDAP writer, rồi lập tức đọc lại qua LDAP replica. Replica có thể vẫn trả email cũ dù server đã ghi thành công.

~~~mermaid
sequenceDiagram
    participant User as Người dùng
    participant App as Application
    participant Writer as LDAP writer
    participant Replica as LDAP replica
    participant Cache as Cache/projection

    User->>App: Đổi email sang địa chỉ mới
    App->>Writer: modifyAttributes(mail=new)
    Writer-->>App: Thành công
    App->>Replica: lookup ngay sau ghi
    Replica-->>App: mail=old (chưa replicate)
    App->>Cache: Nếu ghi từ bản đọc cũ sẽ làm UI lùi trạng thái
~~~

Cần quyết định hợp đồng:

1. **Acknowledgement:** server ghi đã xác nhận lệnh; ứng dụng có thể trả “thay đổi đã được chấp nhận” và kèm trạng thái đồng bộ nếu đọc nơi khác còn trễ.
2. **Read-your-writes:** nếu thật sự cần người gửi lệnh đọc thấy bản mới ngay, chọn reader có đủ consistency, hoặc dùng dữ liệu đã được server xác nhận trong phạm vi tương tác phù hợp mà không nhầm đó là trạng thái tuyệt đối của mọi replica.
3. **Verification:** với thao tác quan trọng, xác minh trên nguồn đọc đáng tin cậy bằng ID và điều kiện đã đặt; không coi một lần replica trả giá trị cũ là bằng chứng modify thất bại.
4. **Unknown outcome:** nếu ghi bị timeout, server có thể đã ghi rồi mất response. Không retry mù. Đọc lại từ nguồn phù hợp; nếu vẫn chưa biết, lưu trạng thái chờ đối soát.

Ngay cả khi nhận success, một quản trị viên bên ngoài có thể sửa lại email sau đó. Nếu use case cần đảm bảo email sẽ không bị ghi đè, phải thiết kế chính sách quyền sở hữu và kiểm soát cập nhật đồng thời.

## 13. Xung đột giữa thay đổi của ứng dụng và bên ngoài

Xét trình tự:

| Thời điểm | Tác nhân | Hành động |
| --- | --- | --- |
| T0 | Ứng dụng | Đọc **mail=a@example.org** |
| T1 | Quản trị viên | Đổi thành **mail=b@example.org** |
| T2 | Ứng dụng | Dựa vào dữ liệu cũ, ghi **mail=c@example.org** |
| T3 | Job đồng bộ | Nhận event cũ nói email là b |

Nếu ứng dụng ghi tại T2 mà không kiểm soát xung đột, thay đổi của quản trị viên tại T1 có thể bị mất. Nếu job áp dụng event T3 sau T2 chỉ theo thời gian nhận, projection lại có thể quay về b.

Các cách xử lý:

- **Một nguồn ghi có thẩm quyền:** nếu IdM là chủ của email, ứng dụng chỉ gửi yêu cầu tới IdM, không tự ghi trực tiếp.
- **Expected value/version:** command có điều kiện dựa trên trạng thái mong đợi; chỉ đọc trước rồi sửa không bảo đảm nguyên tử khi có race.
- **LDAP assertion control (RFC 4528)** nếu server và thư viện hỗ trợ: điều kiện được kiểm tra tại server khi thực hiện modify. Cần kiểm thử phiên bản server, exception khi assertion fail và quyền/semantics thực tế.
- **Serialize thao tác theo subject** ở application: giảm race giữa các worker của ứng dụng, nhưng không khóa được công cụ bên ngoài tự sửa LDAP.
- **Version-aware projection:** chỉ áp dụng event khi nguồn cung cấp revision có thứ tự được bảo đảm, hoặc đọc lại nguồn hiện hành khi event chỉ đóng vai trò thông báo.
- **Manual conflict resolution:** với trường liên quan pháp lý hoặc bảo mật, đưa vào hàng đối soát nếu không đủ bằng chứng để tự chọn giá trị thắng.

Không dùng **modifyTimestamp** như compare-and-swap token nếu server không cung cấp giao thức kiểm tra điều kiện nguyên tử phù hợp. Không chọn “timestamp lớn nhất thắng” giữa các đồng hồ không có cùng mốc tin cậy.

## 14. Thao tác xóa, khóa tài khoản và đổi OU từ bên ngoài

Một thay đổi bên ngoài có thể mang ý nghĩa khác với cập nhật thuộc tính:

| Biến cố | Nguy cơ nếu nhìn từ một bản cache/replica cũ | Chính sách phù hợp |
| --- | --- | --- |
| **RENAME / MOVE OU** | DN cũ không thấy, bị hiểu nhầm là xóa người dùng | Giữ stable ID; cập nhật vị trí khi tìm được entry mới |
| **DISABLE/LOCK** | Ứng dụng vẫn cho phép dùng quyền cũ | Freshness và quy trình thu hồi truy cập riêng |
| **DELETE entry** | Projection vẫn còn, session cũ còn hiệu lực | Tombstone/deprovision theo nguồn đáng tin cậy |
| **DELETE rồi CREATE cùng login** | Ghép nhầm người mới vào lịch sử người cũ | Phân biệt bằng stable ID |
| **Thay đổi group** | Cache nhóm cũ tiếp tục cấp quyền | Invalidation/revalidation theo SLA quyền |
| **Search không thấy entry do ACL/replica lỗi** | Deprovision sai hàng loạt | Phân biệt absence, unavailable, permission, schema |

**Không đánh dấu account đã bị xóa chỉ từ một lần lookup rỗng.** Nếu đối soát bằng full scan, phải xác nhận **tất cả các trang đã đọc đầy đủ**, cùng search scope/filter, không có lỗi limit hoặc ACL; dùng guardrail trước thay đổi quy mô lớn. Với nguồn hỗ trợ tombstone/change feed đáng tin cậy, áp dụng semantics xóa của nguồn đó thay vì suy luận từ dữ liệu thiếu.

Khi account bị disable, dữ liệu workspace và audit có thể vẫn phải giữ theo thời hạn lưu trữ. Hành vi thu hồi quyền và hành vi xóa dữ liệu cá nhân là **hai quyết định khác nhau**.

## 15. Phân quyền là trường hợp nhất quán nhạy cảm

Thông tin thuộc **member/memberOf**, trạng thái khóa tài khoản và quan hệ nhóm có thể được dùng để cho phép truy cập. LDAP server có thể biểu diễn group qua các schema khác nhau; **memberOf** không có mặt trong mọi server và nested group không tự được mở rộng ở mọi cách tìm kiếm.

Nếu yêu cầu thu hồi quyền trong 30 giây:

1. Xác định nguồn nào biết việc thu hồi trước tiên (IdM, LDAP writer, authorization server).
2. Đo replication lag đến reader mà ứng dụng dùng; nếu quá SLA, thay kiến trúc đọc/quyền.
3. Xem xét session/token sống bao lâu và có cơ chế vô hiệu hóa hay không.
4. Đặt giới hạn sử dụng cache entitlement riêng; không chia sẻ cache hồ sơ 5 phút cho quyết định bảo mật.
5. Khi không thể xác minh, tuân theo chính sách fail-closed hoặc quyết định an ninh được chỉ định, không tự coi người dùng vẫn có quyền.

**Một TTL 30 giây trên projection không thể khắc phục replica chậm 2 phút.** Freshness phải được đánh giá trên cả hệ thống, không chỉ trên lớp cache.

## 16. Chống lỗi và vận hành khi LDAP không khả dụng

Kết nối tới LDAP thường được cấu hình bằng **ContextSource**. Ví dụ Spring Boot:

~~~yaml
spring:
  ldap:
    urls:
      - ldaps://ldap.example.org:636
    base: dc=example,dc=org
    username: ${LDAP_BIND_DN}
    password: ${LDAP_BIND_PASSWORD}
~~~

Cần bảo đảm:

- **LDAPS** hoặc **StartTLS** hoạt động với truststore, chứng chỉ và kiểm tra hostname hợp lệ; không tắt xác minh TLS để xử lý sự cố.
- Tài khoản đọc có ACL tối thiểu; tài khoản ghi có quyền hạn riêng khi cần. Không lưu credential trong code, log hoặc message payload.
- **Connect/read timeout**, phạm vi tìm kiếm, giới hạn size, paging và referral được cấu hình phù hợp với server.
- **Pooling** tương thích TLS/StartTLS và trạng thái bind của kết nối; không tái sử dụng sai một kết nối đã xác thực bằng principal khác.
- Adapter chuyển **javax.naming.NamingException** và các exception của **org.springframework.ldap** thành lỗi ứng dụng có nghĩa. **Không trả Optional.empty() khi LDAP timeout hoặc bind thất bại.**
- Retry có backoff và giới hạn. Đối với modify bị timeout, xác minh trạng thái trước khi quyết định thử lại.

Chính sách khi directory lỗi:

| Loại thao tác | Khuyến nghị thiết kế |
| --- | --- |
| Hiển thị hồ sơ lịch sử | Có thể dùng cache cũ trong giới hạn được công bố |
| Tạo tài khoản hoặc ghi thuộc tính | Trả tạm thời không khả dụng hoặc trạng thái chưa xác minh; tránh ghi trùng |
| Đồng bộ projection | Giữ checkpoint, cảnh báo lag, retry có giới hạn |
| Quyết định quyền nhạy cảm | Dùng policy bảo mật đã chốt; không tự cho phép từ dữ liệu cũ |
| Xác thực người dùng | Dùng bind/IdP thích hợp, không cache password hoặc kết quả xác thực như hồ sơ |

**LDAP authentication bind** có thể ảnh hưởng bộ đếm thất bại và policy khóa tài khoản. Không retry ồ ạt các lần bind mật khẩu; không nhầm với **LdapTemplate.bind** dùng tạo entry.

## 17. Reconciliation và giám sát sự hội tụ

Một change feed có thể ngừng hoạt động, cookie hết hạn, sự kiện bị mất hoặc schema thay đổi. Vì vậy **đồng bộ cuối cùng** cần một đường **đối soát định kỳ**.

Quy trình gợi ý:

1. Chọn search scope và tập attribute do directory sở hữu; xác nhận quyền và server đọc.
2. Quét bằng paging/batching có giới hạn tốc độ; không tải toàn bộ directory lớn vào bộ nhớ.
3. Ánh xạ entry theo **sourceId + stableId**, ghi trạng thái đã quan sát và nguồn/version nếu có.
4. So sánh projection với trạng thái nguồn đã được đọc **đầy đủ**. Đánh dấu những khác biệt cần sửa.
5. Khi đề xuất xóa số lượng lớn, kích hoạt guardrail và đánh giá lỗi ACL, scan scope hoặc replication trước khi hành động.
6. Cập nhật checkpoint **sau khi** đích đã áp dụng thay đổi, bảo đảm replay idempotent.
7. Đo kết quả và cảnh báo nếu độ trễ thực tế vượt freshness SLA.

Các chỉ số:

| Metric | Ý nghĩa |
| --- | --- |
| **Last successful observation** | Subject đã được đọc thành công lần cuối lúc nào |
| **Sync lag / checkpoint age** | Projection đang chậm bao lâu so với nguồn quan sát |
| **Cache age / stale-read count** | Số lần dùng dữ liệu cũ và mức tuổi dữ liệu |
| **Replication lag** | Độ chậm giữa writer và replica nếu server cung cấp số liệu |
| **Unknown-outcome command count** | Lệnh ghi chưa xác minh được sau timeout |
| **Conflict / invalidation delay** | Số xung đột và thời gian invalidation tới các node |
| **Reconciliation mismatch count** | Số projection khác nguồn sau full scan hợp lệ |
| **False-deprovision guardrail activation** | Phát hiện bất thường trước khi khóa/xóa hàng loạt |

Tránh dùng **login, email, DN** làm metric label vì cardinality và rò rỉ dữ liệu cá nhân. Có thể lưu source ID, operation, error code, correlation ID và thông tin chẩn đoán nhạy cảm trong log có kiểm soát quyền truy cập.

## 18. Chiến lược kiểm thử eventual consistency

### 18.1. Unit test use case và projection

Giả lập **DirectoryCurrentReader** theo từng lần gọi: trả email A, sau đó email B, hoặc ném lỗi **UNAVAILABLE**. Xác nhận:

- Chỉ những field do directory sở hữu được cập nhật; workspace role trong SQL không bị đổi.
- Refresh có kết quả **NOT_FOUND_IN_SCOPE** không xóa account.
- Timeout không bị chuyển thành “đã xóa entry”.
- Hai worker cập nhật cùng subject không ghi đè phiên bản mới hơn khi hệ thống có revision đáng tin cậy.
- Event đến lặp hoặc đến muộn không tạo bản ghi trùng.
- Cache được invalidate đúng khi nhận thay đổi; request đang load muộn được kiểm tra theo chính sách race.

### 18.2. Integration test với directory phù hợp

| Tình huống | Điều cần xác minh |
| --- | --- |
| Admin bên ngoài sửa **mail** | Projection nhận được thay đổi theo cơ chế feed/TTL/reconciliation |
| Đổi **DN/OU** nhưng giữ stable ID | Liên kết nghiệp vụ không bị mất |
| LDAP replica trả dữ liệu cũ ngay sau modify | Read-your-writes có hành vi đã định nghĩa |
| **entryUUID** thiếu hoặc không đọc được | Lỗi mapping/ACL, không tạo ID giả từ DN |
| Hai nguồn cùng sửa email | Conflict policy ngăn ghi đè ngoài ý muốn |
| Entry bị delete, replica vẫn nhìn thấy | Không vội deprovision trước khi có bằng chứng đáng tin |
| Full scan bị timeout giữa các trang | Không coi phần còn thiếu là DELETE |
| Group bị thu hồi | Authorization đáp ứng SLA hoặc từ chối khi không thể xác minh |
| LDAP timeout, sai credential, TLS lỗi | Lỗi được phân loại, không biến thành Optional.empty |
| Search có ký tự đặc biệt trong filter | Query builder escape an toàn |

Một LDAP server nhúng có thể phù hợp kiểm thử mapper, nhưng kiểm thử **replication, RFC 4533, AD DirSync, assertion control hoặc failover** phải chạy trên server hỗ trợ cơ chế thật. Không suy luận semantics của production từ mock hoặc một test server đơn giản.

### 18.3. Failure injection theo dòng thời gian

Mô phỏng:

1. T0: application đọc A; T1: admin ngoài ứng dụng ghi B; T2: replica còn A; T3: cache hết hạn; T4: projection nhìn thấy B.
2. Lệnh đổi email ghi thành công trên writer nhưng response mất; kiểm tra ứng dụng không retry mù và ghi nhận trạng thái chưa xác minh.
3. Event xóa tới trước event đổi tên; consumer phải dùng chính sách nguồn/version hoặc đọc lại, không tự xóa nhầm.
4. Hai instance cùng refresh, một instance lấy kết quả cũ hơn và hoàn tất sau; projection/cache phải có cơ chế xử lý theo yêu cầu freshness.
5. Full reconciliation bị gián đoạn sau một phần dữ liệu; guardrail ngăn xóa những entry chưa được quét.

Chỉ xem một bài kiểm thử đạt khi kết quả cuối cùng, thông tin freshness và phản hồi khi không chắc chắn đều đúng theo hợp đồng của use case.

## 19. Các lỗi thiết kế thường gặp

| Lỗi | Tác động | Cách sửa |
| --- | --- | --- |
| Coi eventual consistency là “chấp nhận cũ bao lâu cũng được” | Không có SLA, khó giám sát | Định nghĩa freshness contract cho từng chức năng |
| Chỉ invalidate sau thao tác do chính app gọi | Bỏ qua admin/IdM sửa bên ngoài | Feed, polling phù hợp và reconciliation |
| Dùng DN làm khóa bất biến | Move/rename làm mất liên kết | Stable ID + directory source |
| Dùng **modifyTimestamp** làm version toàn cục | Ghi đè sai do replica/time resolution | Dùng revision nguồn bảo đảm hoặc đọc lại |
| Lookup rỗng được hiểu là DELETE | Outage/ACL/search scope gây xóa nhầm | Phân biệt NOT_FOUND_IN_SCOPE, lỗi hạ tầng và xóa có thẩm quyền |
| Đọc replica ngay sau ghi rồi thấy dữ liệu cũ | Ứng dụng báo ghi thất bại dù writer thành công | Read-your-writes policy và xác minh từ nguồn thích hợp |
| Dùng cache profile làm quyết định phân quyền | Quyền bị thu hồi vẫn còn hiệu lực | Chính sách authorization freshness riêng |
| Retry mọi LDAP modify sau timeout | Ghi lặp hoặc ghi đè ngoài ý muốn | Unknown outcome + readback/reconciliation |
| Chỉ dùng TTL để đáp ứng SLA quyền | Replication lag vẫn vượt SLA | Đo toàn chuỗi và thay luồng authorization |
| Áp dụng sự kiện theo thứ tự nhận | Event cũ ghi đè event mới | Source revision hoặc event-as-invalidation |
| Mọi lỗi LDAP thành Optional.empty | Che outage và lỗi quyền | Error translation ở adapter |
| Không thử kịch bản sửa từ bên ngoài | Hệ thống chỉ đúng khi app là tác nhân duy nhất | Integration test với admin/IdM độc lập |

## 20. Bài tập thiết kế

Một công ty dùng OpenLDAP làm nguồn tài khoản, một application Spring Boot với PostgreSQL và cache Caffeine, cùng hai LDAP replica. Quản trị viên có thể sửa trực tiếp LDAP qua IdM. Tên hiển thị được phép cũ 5 phút; email dùng gửi giấy tờ quan trọng chỉ được cũ 1 phút; quyền nhóm nhạy cảm phải bị thu hồi trong 30 giây. Có lúc replica chậm hơn 2 phút và job đồng bộ bị mất một sự kiện.

Hãy thực hiện:

1. **Vẽ luồng dữ liệu** gồm writer LDAP, replica, adapter Spring LDAP, cache, projection và API. Nêu nơi xảy ra trễ.
2. **Lập bảng nguồn ghi chính** cho email, tên, nhóm, trạng thái account và workspace role.
3. **Định nghĩa hợp đồng freshness** riêng cho UI, gửi email và authorization; xử lý khi replica vượt thời hạn.
4. **Thiết kế DirectoryCurrentReader** theo stable ID; giải thích vì sao **NOT_FOUND_IN_SCOPE** chưa đủ để xóa user.
5. **Chọn cơ chế quan sát thay đổi ngoài ứng dụng**: feed nếu server hỗ trợ, polling có giới hạn và full reconciliation để xử lý event mất.
6. **Thiết kế xung đột email** khi ứng dụng và admin ngoài ứng dụng cùng sửa; chứng minh read-before-write đơn thuần chưa đủ chống race.
7. **Kiểm thử timeline** sau write, rename OU, replica lag, event trùng/sai thứ tự, full scan thất bại, cache invalidation và LDAP outage.
8. **Thiết kế telemetry** đo sync lag, dữ liệu cũ, xung đột và guardrail trước khi deprovision.

Trước khi đưa hệ thống vào sản xuất, phải trả lời rõ: **Nguồn nào có thẩm quyền? Dữ liệu được phép cũ bao lâu? Thay đổi ngoài ứng dụng được phát hiện bằng gì? Nếu không xác minh được, thao tác được tiếp tục hay phải dừng?**

**Kết luận:** xử lý eventual consistency trong Spring LDAP là quản lý các khoảng trễ và thay đổi xuất hiện ngoài tầm kiểm soát của ứng dụng. Tách nguồn dữ liệu chính, stable identity, adapter đọc LDAP, cache, projection và authorization; bổ sung freshness contract, cơ chế quan sát thay đổi, đối soát và xử lý unknown outcome. Khi các giới hạn nhất quán được đo và kiểm thử đúng, ứng dụng có thể hỗ trợ các tác vụ hiển thị chấp nhận độ trễ trong khi vẫn giữ quy tắc chặt chẽ cho danh tính và quyền truy cập.
