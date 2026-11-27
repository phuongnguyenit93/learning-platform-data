# Phân trang search subtree với server control

## 1. Bài toán thực hành và kết quả cần đạt

Một doanh nghiệp quản lý hàng chục nghìn nhân viên trong LDAP directory. Ứng dụng Spring Boot dùng **Spring LDAP** để đọc các entry người dùng dưới **ou=people,dc=example,dc=org**, đồng bộ tên hiển thị và email vào hệ thống nội bộ. Khi chỉ có vài chục entry, một lệnh **LdapTemplate.search()** trả về danh sách là đủ. Nhưng khi subtree có hàng chục nghìn entry, truy vấn không phân trang có thể gặp giới hạn kích thước của server, timeout, tải bộ nhớ lớn và khó phục hồi nếu có lỗi giữa chừng.

Mục tiêu của bài **Thực hành tổng hợp** là triển khai **LDAP subtree search có phân trang ở phía server**, dùng **Simple Paged Results Control (RFC 2696)** thông qua **PagedResultsDirContextProcessor** của Spring LDAP. Người học sẽ:

1. Phân biệt **search scope**, **page size**, **server size limit** và **page cookie**.
2. Cấu hình **ContextSource** cùng TLS và tài khoản đọc có quyền tối thiểu.
3. Viết truy vấn subtree với **LdapTemplate**, **SearchControls** và server control.
4. Xử lý nhiều trang bằng cookie đến khi server xác nhận hết dữ liệu.
5. Ánh xạ attribute thành DTO không làm rò rỉ JNDI vào tầng nghiệp vụ.
6. Giới hạn tài nguyên, xử lý lỗi, phân biệt kết quả rỗng với một đợt quét chưa hoàn tất.
7. Kiểm thử với LDAP server thực sự hỗ trợ paged results, kể cả thay đổi dữ liệu giữa các trang.

**Sản phẩm của bài tập:** một thành phần đọc từng trang và chuyển các batch dữ liệu sang bộ tiêu thụ; một bộ test kiểm tra tập kết quả và khả năng xử lý sự cố; một checklist vận hành trước khi dùng trên directory thật.

## 2. Hiểu cấu trúc DIT và subtree search

**DIT (Directory Information Tree)** là cây entry được định danh bằng **DN (Distinguished Name)**. Ví dụ:

~~~text
dc=example,dc=org
├── ou=people
│   ├── uid=lan
│   ├── uid=minh
│   ├── uid=hoa
│   └── uid=an
├── ou=groups
│   └── cn=staff
└── ou=services
    └── cn=sync-reader
~~~

Khi **ContextSource** có base **dc=example,dc=org**, tham số search base **ou=people** trong **LdapTemplate** thường được hiểu là tên *tương đối với base đã cấu hình*. Không nối thêm **dc=example,dc=org** lần nữa, trừ khi cấu hình ContextSource và API sử dụng DN tuyệt đối được thiết kế riêng.

Các search scope chuẩn của JNDI:

| Scope | Phạm vi | Ví dụ khi base là ou=people |
| --- | --- | --- |
| **OBJECT_SCOPE** | Chỉ entry tại base | Bản thân ou=people |
| **ONELEVEL_SCOPE** | Các entry con trực tiếp của base | Những uid trực tiếp dưới ou=people |
| **SUBTREE_SCOPE** | Base và mọi cấp con cháu | Cả uid dưới OU lồng nhau nếu filter khớp |

Trong bài này chọn **SUBTREE_SCOPE** nhằm tìm người ở mọi cấp dưới **ou=people**. Bộ lọc cố định **(objectClass=inetOrgPerson)** giới hạn kiểu entry trả về. Thực tế có thể cần filter chính xác hơn để loại account kỹ thuật và những OU không thuộc phạm vi đồng bộ.

## 3. Vì sao giới hạn kết quả và phân trang không giống nhau?

Giả sử server có 12.000 nhân viên và giới hạn mặc định 1.000 entry trên một search.

- **search không phân trang:** một request có thể bị từ chối, trả lỗi **SizeLimitExceededException**, hoặc kết quả không đủ theo cách server/client xử lý. Không được coi 1.000 bản ghi đầu là toàn bộ 12.000 bản ghi.
- **phân trang tại application sau khi search:** gọi search lấy mọi entry rồi chia danh sách thành các nhóm 200 trong Java. Cách này **không giảm** giới hạn và tải của thao tác LDAP ban đầu.
- **phân trang tại LDAP server:** client gửi yêu cầu với page size 200 qua **Simple Paged Results Request Control**; server trả một phần kết quả và cookie để client yêu cầu trang tiếp.

~~~mermaid
sequenceDiagram
    participant App as Spring LDAP client
    participant Server as LDAP server
    App->>Server: Search subtree + pageSize=200, cookie rỗng
    Server-->>App: Trang 1 + cookie C1
    App->>Server: Cùng search + pageSize=200, cookie C1
    Server-->>App: Trang 2 + cookie C2
    App->>Server: Cùng search + pageSize=200, cookie C2
    Server-->>App: Trang cuối + cookie rỗng
    Note over App: Chỉ lúc này mới xem đã đọc hết
~~~

**Page size** là số entry client mong muốn nhận mỗi trang; server vẫn áp dụng chính sách và giới hạn riêng. **Cookie** là chuỗi byte opaque do server cấp, không phải số trang hay offset. Không tự sửa cookie, không chuyển cookie của một query sang query khác và không giả định nó tồn tại mãi sau restart.

## 4. Simple Paged Results Control – RFC 2696

LDAP Simple Paged Results có OID **1.2.840.113556.1.4.319**. Một request có control này mang:

- **size:** kích thước trang mong muốn.
- **cookie:** giá trị rỗng ở yêu cầu đầu; về sau dùng cookie server trả từ response trước.

Response control có **estimated result size** (một giá trị ước lượng, có thể là 0) và **cookie** cho lần gọi tiếp theo. **Cookie rỗng** thể hiện server không còn trang tiếp theo trong ngữ cảnh search đó. Số lượng ước lượng **không phải** cơ sở để xác nhận đã quét đầy đủ.

Thao tác search giữa các trang phải giữ **cùng base, scope, filter và thuộc tính/các search option liên quan**. Một số server gắn cookie với trạng thái session hoặc chính connection; kiểm thử với topology và cấu hình pool thực tế là bắt buộc.

**Điểm đặc biệt:** RFC 2696 **không cam kết snapshot nhất quán** của toàn bộ subtree khi entry được tạo, xóa hoặc move trong khi đang quét. Các entry có thể xuất hiện hoặc biến mất giữa những trang; pagination là phương thức giới hạn lượng dữ liệu, **không tự động là cơ chế đồng bộ CDC hoặc transaction**.

## 5. Chuẩn bị LDAP server và dữ liệu thử nghiệm

Môi trường đề xuất:

| Thành phần | Vai trò |
| --- | --- |
| Java 17+ và Spring Boot phù hợp | Chạy ứng dụng Java |
| Spring LDAP, sử dụng **LdapTemplate** | Gửi search và nhận control |
| LDAP server hỗ trợ RFC 2696 | Thực sự phân trang ở phía server |
| Test directory với OU **ou=people** | Phạm vi tìm kiếm có kiểm soát |
| Tài khoản đọc LDAP riêng | Quyền đọc chỉ trong subtree và những attribute cần thiết |
| TLS/LDAPS hoặc StartTLS | Bảo vệ credential và dữ liệu đường truyền |
| Bộ kiểm thử JUnit 5 | Xác minh tích hợp và lỗi |

Dữ liệu thử có thể gồm 5–7 entry **inetOrgPerson**, mỗi entry có **uid**, **cn**, **sn**, và **mail**. Nếu server hỗ trợ operational attribute **entryUUID**, yêu cầu rõ thuộc tính này và kiểm tra bind account được phép đọc.

Một entry mẫu:

~~~ldif
dn: uid=lan,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: lan
cn: Nguyen Lan
sn: Nguyen
mail: lan@example.org
~~~

**Lưu ý về schema:** một số giá trị như **entryUUID** do server quản lý và không được tự khai báo khi nạp LDIF. Active Directory dùng **objectGUID** (nhị phân); ví dụ mapper cho **entryUUID** trong bài này chỉ áp dụng khi schema/server hỗ trợ.

Trước khi lập trình, xác nhận server thực sự hỗ trợ **Simple Paged Results** (có thể kiểm tra khả năng control và thực hiện tìm kiếm có phân trang). Không dựa vào việc server chấp nhận TCP connection để kết luận control đã hoạt động.

## 6. Cấu hình ContextSource và kết nối an toàn

Ví dụ cấu hình Spring Boot dùng **LDAPS**:

~~~yaml
spring:
  ldap:
    urls:
      - ldaps://ldap.example.org:636
    base: dc=example,dc=org
    username: ${LDAP_BIND_DN}
    password: ${LDAP_BIND_PASSWORD}
~~~

Các yêu cầu trước khi chạy:

1. **Dùng TLS đúng cách:** truststore hợp lệ, xác minh certificate và hostname. Không tắt kiểm tra TLS để né lỗi certificate.
2. **Không hard-code secret:** quản lý bind DN/password qua cấu hình bí mật của môi trường chạy.
3. **Quyền đọc tối thiểu:** service account chỉ đọc subtree và attribute cần thiết; không cần quyền sửa group hoặc password.
4. **Timeout:** cấu hình connect timeout, read timeout và thời hạn thực hiện một lượt search; **SearchControls.setTimeLimit** không thay thế network read timeout.
5. **Pooling:** kiểm tra cơ chế giữ kết nối, trạng thái bind và TLS/StartTLS. Không trộn session của các principal khác nhau.
6. **Giới hạn tài nguyên:** quy định page size, số trang tối đa và tổng số entry tối đa cho một lượt quét.

Trong bài dùng **LdapTemplate** để truy cập trực tiếp. **LdapClient** hoặc ODM có thể giúp thao tác entry hoặc mapping nhưng khi cần server control cho paged results, phải chọn API có khả năng gửi/nhận control tương đương. Không tự suy ra rằng một API chỉ hỗ trợ tìm kiếm thông thường cũng đã triển khai paging.

## 7. Thiết kế DTO và hợp đồng xử lý từng trang

Lớp nghiệp vụ không cần nhìn thấy cookie, JNDI **SearchControls**, **DirContextOperations** hoặc **NamingException**. Tầng hạ tầng chuyển attribute sang một DTO trung lập:

~~~java
// domain/DirectoryPerson.java
package com.example.paging.domain;

public record DirectoryPerson(
        String directorySource,
        String stableEntryId,
        String login,
        String displayName,
        String email
) {}
~~~

Một interface nhận kết quả theo batch:

~~~java
// application/DirectoryPageSink.java
package com.example.paging.application;

import com.example.paging.domain.DirectoryPerson;
import java.util.List;

@FunctionalInterface
public interface DirectoryPageSink {
    void accept(List<DirectoryPerson> page);
}
~~~

Giả sử downstream lưu vào SQL, sink có thể **upsert idempotent** từng bản ghi theo **(directorySource, stableEntryId)**. Không tạo một List chứa toàn bộ kết quả chỉ để chia lại thành trang. Với ứng dụng chỉ xem dữ liệu, sink có thể xử lý ngay một trang rồi bỏ khỏi bộ nhớ.

Chúng ta sẽ công bố **ScanStats** sau khi **tất cả** các trang được đọc thành công; nếu có lỗi ở trang giữa thì **không được trả một trạng thái “scan hoàn tất” với dữ liệu thiếu**.

~~~java
// application/ScanStats.java
package com.example.paging.application;

public record ScanStats(int pagesRead, long entriesRead) {}
~~~

## 8. Triển khai Spring LDAP PagedResultsDirContextProcessor

Spring LDAP hỗ trợ xử lý controls qua **DirContextProcessor**. Thành phần **PagedResultsDirContextProcessor** quản lý cookie giữa các yêu cầu search trong một vòng lặp; API cụ thể cần tương thích với phiên bản Spring LDAP của dự án.

Mã sau sử dụng overload **LdapTemplate.search(base, filter, SearchControls, ContextMapper, DirContextProcessor)**. Mục tiêu là đọc từng trang và chuyển dữ liệu sang consumer, không giữ toàn bộ kết quả trong RAM.

~~~java
// infrastructure/ldap/SpringLdapSubtreePager.java
package com.example.paging.infrastructure.ldap;

import com.example.paging.application.DirectoryPageSink;
import com.example.paging.application.ScanStats;
import com.example.paging.domain.DirectoryPerson;
import java.util.List;
import javax.naming.directory.SearchControls;
import org.springframework.ldap.control.PagedResultsDirContextProcessor;
import org.springframework.ldap.core.ContextMapper;
import org.springframework.ldap.core.DirContextOperations;
import org.springframework.ldap.core.LdapTemplate;

public final class SpringLdapSubtreePager {

    private static final String SOURCE = "corp-openldap";
    private static final String BASE = "ou=people";
    private static final String FILTER = "(objectClass=inetOrgPerson)";
    private static final int PAGE_SIZE = 200;
    private static final int MAX_PAGES = 500;
    private static final long MAX_ENTRIES = 100_000L;

    private final LdapTemplate ldap;

    public SpringLdapSubtreePager(LdapTemplate ldap) {
        this.ldap = ldap;
    }

    public ScanStats scan(DirectoryPageSink sink) {
        SearchControls controls = new SearchControls();
        controls.setSearchScope(SearchControls.SUBTREE_SCOPE);
        controls.setReturningAttributes(
                new String[] { "uid", "cn", "mail", "entryUUID" });
        controls.setTimeLimit(15_000);

        PagedResultsDirContextProcessor paging =
                new PagedResultsDirContextProcessor(PAGE_SIZE);

        int pages = 0;
        long entries = 0;

        do {
            List<DirectoryPerson> page = ldap.search(
                    BASE,
                    FILTER,
                    controls,
                    (ContextMapper<DirectoryPerson>) context -> {
                        DirContextOperations entry =
                                (DirContextOperations) context;
                        return new DirectoryPerson(
                                SOURCE,
                                required(entry, "entryUUID"),
                                required(entry, "uid"),
                                entry.getStringAttribute("cn"),
                                entry.getStringAttribute("mail"));
                    },
                    paging);

            pages++;
            entries += page.size();
            if (pages > MAX_PAGES || entries > MAX_ENTRIES) {
                // Không được đánh dấu scan hoàn tất nếu vượt giới hạn.
                throw new DirectoryScanLimitException(
                        "Vượt ngân sách quét subtree");
            }

            sink.accept(List.copyOf(page));
        } while (paging.hasMore());

        return new ScanStats(pages, entries);
    }

    private static String required(
            DirContextOperations entry, String attributeName) {
        String value = entry.getStringAttribute(attributeName);
        if (value == null || value.isBlank()) {
            throw new IllegalStateException(
                    "Thiếu attribute LDAP: " + attributeName);
        }
        return value;
    }
}
~~~

~~~java
// infrastructure/ldap/DirectoryScanLimitException.java
package com.example.paging.infrastructure.ldap;

public final class DirectoryScanLimitException
        extends RuntimeException {
    public DirectoryScanLimitException(String message) {
        super(message);
    }
}
~~~

### Diễn giải từng phần

**SearchControls.SUBTREE_SCOPE** yêu cầu duyệt mọi nhánh con của base. **BASE** là tên tương đối với ContextSource; filter được cố định theo objectClass để chỉ trả person entry. **setReturningAttributes** giảm dữ liệu truyền về và thể hiện rõ attribute nào mapper cần. **setTimeLimit(15_000)** là giới hạn thời gian áp dụng cho search qua JNDI; cần cấu hình timeout mạng tách biệt và đo lường trên server thật.

**PagedResultsDirContextProcessor(PAGE_SIZE)** chuẩn bị request control. Đối tượng **paging** phải được tái sử dụng trong toàn bộ vòng lặp, vì nó giữ cookie mới nhận cho trang tiếp theo. **paging.hasMore()** cho biết có trang tiếp theo theo control đã xử lý; **không dừng chỉ vì một trang trả ít hơn PAGE_SIZE** hay vì estimate bằng 0.

**DirectoryPageSink** nhận một trang tại một thời điểm. Nếu sink ghi SQL, cần transaction ngắn, xử lý idempotent và cơ chế báo lỗi để toàn bộ scan không được đánh dấu hoàn tất khi sink thất bại. Bộ giới hạn MAX_PAGES/MAX_ENTRIES bảo vệ tải; nếu bị chạm, coi scan là **incomplete** và báo lỗi.

**Điểm triển khai cần kiểm tra với server:** một số directory yêu cầu cookie được sử dụng trên cùng LDAP connection hoặc cùng session. Nếu LdapTemplate mở/đóng context giữa các trang và server không chấp nhận việc chuyển cookie, cần cấu hình một phạm vi **single context** bằng cơ chế phù hợp của Spring LDAP (ví dụ **SingleContextSource**) và kiểm thử connection affinity. Không giả định pooling tự bảo đảm cùng kết nối.

**Không dùng tên DN làm khóa nghiệp vụ:** entryUUID là ví dụ ID ổn định trong nhiều OpenLDAP server. Khi entry bị move/rename, dùng **directorySource + stableEntryId** để đối soát. Một DN từ **entry.getDn()** có thể là tên tương đối; không tự ghép lại từ login nếu cần sửa một entry sau này.

## 9. Kiểm tra server control và quyền hỗ trợ

Trước khi chạy scanner ở production, cần xác minh **control thực sự được server xử lý**:

- LDAP server công bố hỗ trợ control phù hợp hoặc chấp nhận tìm kiếm có phân trang trong test thực tế.
- Search trả các response controls theo đúng RFC 2696 và bộ xử lý nhận cookie.
- Trang tiếp nối được trả đúng khi dùng cookie server trước, chứ không phải cùng một tập entry lặp vô hạn.
- Trang cuối có cookie rỗng và vòng lặp kết thúc.
- Sai ACL, search base không tồn tại, filter không phù hợp hoặc schema khác phải tạo kết quả/lỗi có thể phân biệt.
- Khi server không hỗ trợ control, **fail rõ ràng**; không âm thầm chuyển sang search không phân trang cho tập dữ liệu lớn.

Nếu thư viện hoặc server không hỗ trợ PagedResultsDirContextProcessor trong bối cảnh dự án, chọn một LDAP client/control implementation có khả năng gửi **Simple Paged Results** chính xác. Không thay thế bằng xử lý danh sách ở Java rồi tuyên bố là server-side pagination.

### Thử từ công cụ LDAP

Trên môi trường thử nghiệm có **ldapsearch** hỗ trợ paged results:

~~~bash
ldapsearch -LLL -x \
  -H ldaps://ldap.example.org:636 \
  -D "cn=sync-reader,ou=services,dc=example,dc=org" -W \
  -b "ou=people,dc=example,dc=org" -s sub \
  -E "pr=2/noprompt" \
  "(objectClass=inetOrgPerson)" uid cn mail entryUUID
~~~

Lệnh dùng **-W** để nhập password tương tác, tránh đưa password lên command line. Cú pháp tùy bản **ldapsearch**, và **-E pr=...** phải được công cụ hỗ trợ. Đừng coi việc lệnh kết thúc không lỗi là đủ: kiểm tra số ID duy nhất thu được và quyền đọc operational attribute.

## 10. Filter, DN và bảo vệ dữ liệu đầu vào

Trong ví dụ mã, filter là hằng số nên không có đầu vào người dùng. Nếu ứng dụng cần tìm theo phòng ban hoặc prefix login, **không nối chuỗi LDAP filter** từ HTTP parameter.

~~~java
// LdapQueryBuilder tạo filter với escaping cho giá trị.
org.springframework.ldap.query.LdapQuery query =
        org.springframework.ldap.query.LdapQueryBuilder.query()
                .base("ou=people")
                .where("uid").is(userProvidedLogin);
~~~

Với API search dùng **SearchControls + DirContextProcessor**, filter động cần được tạo/encode bằng API LDAP filter an toàn rồi mới truyền vào overload tương ứng. Giữ các tên attribute, search base và kiểu thao tác do ứng dụng xác định, không nhận raw filter từ client.

DN có ngữ pháp khác filter. Khi cần dựng DN:

~~~java
javax.naming.Name dn =
        org.springframework.ldap.support.LdapNameBuilder.newInstance()
                .add("ou", "people")
                .add("uid", userProvidedLogin)
                .build();
~~~

**Không dùng split(",") để tách DN**, vì RDN có thể chứa dấu phẩy được escape. Không dùng DN hoặc email làm identity ổn định mặc định; tên entry có thể đổi khi chuyển OU.

## 11. Phân trang không tạo snapshot nhất quán

Giả sử bạn đã đọc trang 1 rồi một quản trị viên bên ngoài chuyển nhân viên **uid=lan** sang OU khác, thêm người mới và xóa một entry trong khi trang 2 đang được tạo.

Những điều có thể xảy ra tùy server:

- Một entry xuất hiện trong hai trang hoặc bị bỏ qua khi thứ tự/đường đi tìm kiếm thay đổi.
- Dữ liệu của hai trang thể hiện hai thời điểm quan sát khác nhau.
- Entry bị xóa sau khi trang đầu được đọc sẽ không có trong phần còn lại.
- Page cookie có thể hết hạn hoặc không còn hợp lệ nếu server/context thay đổi.

**Không suy ra rằng một vòng paged search là snapshot tại một thời điểm.** Nếu kết quả dùng để đồng bộ SQL, sink cần upsert theo stable ID và xử lý idempotent để chịu được bản ghi lặp. Để phát hiện xóa, phải có **change feed/tombstone** hoặc một quá trình reconciliation đầy đủ với guardrail, không chỉ lấy tập ID nhìn thấy từ một scan bị gián đoạn.

Một số server hỗ trợ **server-side sort control (RFC 2891)** để cải thiện thứ tự xác định khi kết hợp với paging. Nhưng sort cũng **không tự tạo snapshot transaction**; việc phối hợp controls cần được kiểm thử vì không phải server nào cũng hỗ trợ tương tự.

## 12. Checkpoint, khôi phục và cookie có phải bookmark?

Một câu hỏi thường gặp: “Có thể lưu cookie của trang 7 xuống PostgreSQL rồi hôm sau tiếp tục trang 8 không?”

**Không nên coi cookie phân trang RFC 2696 là checkpoint bền vững mặc định.** Cookie thuộc ngữ cảnh search và server. Nó có thể hết hạn, chỉ hợp lệ trong một session, hoặc không được server khác chấp nhận. Nếu restart hoặc failover, hãy chọn chiến lược phù hợp:

1. **Quét lại từ đầu** với cùng scope/filter, ghi **idempotent** vào projection. Phù hợp với dữ liệu vừa phải và scan định kỳ.
2. **Dùng cơ chế incremental sync** được server hỗ trợ, chẳng hạn RFC 4533 LDAP Content Synchronization hoặc AD DirSync, nếu bài toán cần checkpoint thay đổi bền vững. Đây là **controls khác**, với cookie/semantics riêng.
3. **Đối soát theo stable ID**, kiểm tra số bản ghi và dấu hiệu bất thường trước khi kết luận đã đọc đủ.

Nếu scan bị lỗi tại trang 5, không lưu **completed=true**, không xóa những record chưa thấy và không coi 4 trang trước là toàn bộ directory. Nếu downstream upsert từng trang, lần quét lại phải an toàn khi gặp những entry đã ghi.

Để quản lý xóa bằng full scan, có thể dùng **generation ID**: đánh dấu những ID đã thấy trong vòng quét; chỉ sau khi **tất cả trang thành công** mới so sánh ID chưa xuất hiện, và cần chính sách tránh false delete khi replica/ACL/scope thay đổi.

## 13. Lỗi phân trang và xử lý exception

Một scanner tốt không chỉ quan tâm danh sách kết quả. Những lỗi phải được phân biệt:

| Lỗi hoặc kết quả | Diễn giải | Ứng xử |
| --- | --- | --- |
| Trang cuối hợp lệ, cookie rỗng | Đã hết kết quả theo phản hồi server | Hoàn tất scan |
| Trang có 0 entry nhưng cookie tiếp tục | Server báo còn trang khác | Theo control và kiểm tra tiến triển; chặn vòng lặp bất thường |
| **CommunicationException** hoặc timeout | Chưa chắc đã đọc đủ | Mark scan incomplete, retry có giới hạn |
| **SizeLimitExceededException** | Search bị giới hạn, không phải trang cuối | Fail; xem server limit và paging control |
| **NoPermissionException** / bind sai | Không có quyền đọc subtree/attribute | Fail và cảnh báo cấu hình/ACL |
| **NameNotFoundException** với search base | Base không tồn tại hoặc sai cấu trúc | Lỗi cấu hình, không coi toàn bộ subtree rỗng |
| Mapper thiếu **entryUUID** | Dữ liệu/schema/quyền đọc không đáp ứng hợp đồng | Fail hoặc quarantine theo chính sách, không tạo ID từ DN |
| Cookie không hợp lệ/expired | Phiên paging bị gián đoạn | Khởi tạo scan mới, không đoán offset |
| Sink SQL lỗi ở trang N | Chưa áp dụng đủ dữ liệu | Dừng, không đánh dấu hoàn tất; chạy lại idempotent |
| Page count vượt ngân sách | Có thể sai cấu hình hoặc directory quá lớn | Fail và yêu cầu điều chỉnh có kiểm soát |

**Spring LDAP** thường chuyển exception JNDI sang các subtype runtime trong package **org.springframework.ldap**. Adapter phải chuyển chúng thành exception application như **DirectoryUnavailable**, **DirectoryAccessDenied**, **DirectoryScanIncomplete**. Không để **javax.naming.NamingException** hoặc loại exception hạ tầng đi ra domain service.

**Tránh bắt mọi Exception rồi trả List rỗng.** Điều đó có thể khiến job đồng bộ coi toàn bộ tài khoản biến mất. Cần phân biệt **thực sự không có entry** với **chưa đọc hết do lỗi**.

Khi abort một vòng paging, một số LDAP server giữ tài nguyên liên quan tới paged search. RFC 2696 mô tả yêu cầu với page size 0 và cookie hiện tại để chấm dứt chuỗi khi server hỗ trợ. Trong triển khai Spring LDAP, hãy kiểm tra API/cách quản lý context và vòng đời connection để **hủy hoặc giải phóng** tài nguyên đúng cách khi abort; không giả định một exception tự hoàn tất phiên paging.

## 14. Giới hạn tốc độ và quan sát hoạt động

Ngay cả khi mỗi trang chỉ có 200 entry, một job có thể gây tải đáng kể nếu quét hàng trăm nghìn entry nhiều lần mỗi phút.

Thiết kế nên có:

- **PAGE_SIZE** phù hợp thực tế sau khi đo, chẳng hạn thử từ 100–500 thay vì mặc định rất lớn.
- **MAX_PAGES, MAX_ENTRIES, deadline** cho mỗi scan và quota riêng theo directory source.
- **Backpressure:** sink xử lý trang theo tốc độ database, không nạp tất cả trang vào queue vô hạn.
- **Rate limit và retry/backoff** có jitter; không chạy đồng thời nhiều full scan trên cùng subtree nếu không cần.
- **Khả năng hủy** khi deployment shutdown; ghi lại scan incomplete chứ không báo đã đồng bộ xong.
- **Metrics:** số trang, entry/trang, thời gian mỗi search, tổng thời gian scan, số lần retry, failure code, số ID trùng, độ trễ lần quét thành công cuối.

Đừng log toàn bộ DN, email hoặc cookie ở log mức phổ biến; cookie là giá trị opaque, và metric label chứa login sẽ làm tăng cardinality/lộ dữ liệu. Ghi **source ID**, **scan ID**, số trang, loại lỗi và correlation ID là đủ trong đa số trường hợp.

## 15. Unit test cho batch consumer và ranh giới nghiệp vụ

Không cần LDAP server để thử quy tắc upsert và nhận batch. Giả sử application có repository lưu bản chiếu định danh theo **(directorySource, stableEntryId)**:

~~~java
// application/DirectoryProjectionWriter.java
package com.example.paging.application;

import com.example.paging.domain.DirectoryPerson;
import java.util.List;

public interface DirectoryProjectionWriter extends DirectoryPageSink {
    void upsertIdempotently(DirectoryPerson person);

    @Override
    default void accept(List<DirectoryPerson> page) {
        for (DirectoryPerson person : page) {
            upsertIdempotently(person);
        }
    }
}
~~~

Những test nên viết:

1. Hai trang chứa cùng **stableEntryId** không tạo hai record trong SQL.
2. Trang 1 thành công, trang 2 thất bại: không đánh dấu scan **COMPLETED**.
3. Chạy lại từ đầu không ghi đè các trường ứng dụng sở hữu (role, preferences).
4. Thay đổi **cn/mail** được cập nhật theo nguồn sở hữu, nhưng rename DN không đổi stable ID.
5. Sink ném lỗi sẽ không bị scanner nuốt rồi trả **ScanStats** thành công.
6. Bản ghi thiếu ID được báo lỗi/quarantine rõ, không suy từ login/DN.

Unit test không chứng minh được server thực sự gửi cookie; cần integration test riêng cho RFC 2696.

## 16. Integration test với LDAP server hỗ trợ paging

Đây là phần bắt buộc của bài thực hành. Chuẩn bị một LDAP test server có 7 entry **inetOrgPerson** trong subtree, page size **2**, và một entry khác nằm ngoài **ou=people**.

| Ca kiểm thử | Tiêu chí chấp nhận |
| --- | --- |
| Search subtree với page size nhỏ | Nhận đủ 7 ID hợp lệ qua **nhiều trang**, không lẫn entry ngoài subtree |
| Có OU lồng dưới ou=people | Entry trong OU con được tìm bởi **SUBTREE_SCOPE** |
| ONELEVEL_SCOPE để đối chiếu | Không nhận entry ở tầng cháu |
| Filter chọn đúng objectClass | Không lấy entry **groupOfNames** hoặc organizationalUnit không phù hợp |
| Request control hoạt động | Server nhận RFC 2696 control, có response cookie và kết thúc khi cookie rỗng |
| Tổng số entry không chia hết cho page size | Vòng lặp dừng đúng, không bỏ trang cuối |
| Một entry được thêm/move trong lúc scan | Test ghi nhận khả năng scan không là snapshot; quá trình đối soát vẫn an toàn |
| Giới hạn size hoặc control không hỗ trợ | Scanner fail rõ, không đánh dấu hoàn tất |
| Service account thiếu quyền | Lỗi permission được giữ riêng với kết quả rỗng |
| LDAP timeout hoặc kết nối bị ngắt | Scan incomplete; retry không xóa dữ liệu đích |
| Tắt TLS hoặc certificate không hợp lệ | Kết nối thất bại theo chính sách, không vô hiệu hóa xác minh TLS |
| Tên uid chứa ký tự đặc biệt | Nếu filter động, truy vấn được escape; không LDAP injection |

Không nên khẳng định **mỗi trang chắc chắn chứa đúng 2 entry** trên mọi server. Hãy kiểm tra **tập stable ID cuối**, số bản ghi được xử lý, cookie progression và điều kiện kết thúc. Thứ tự trả kết quả không được mặc định ổn định nếu không có cơ chế server-side sort đã được xác minh.

Đối với OpenLDAP, yêu cầu quyền đọc **entryUUID**; với AD, phải điều chỉnh mapping sang **objectGUID**. LDAP test server nhúng có thể kiểm tra search và mapper, nhưng nếu không hỗ trợ RFC 2696 thì **không chứng minh được** bài thực hành phân trang server-side; cần server/control tương thích thật.

## 17. Bài tập mở rộng: từ scan đến đồng bộ đáng tin cậy

Giả sử hệ thống cần đồng bộ 100.000 entry vào PostgreSQL mỗi đêm và có thể bị dừng giữa chừng. Hãy bổ sung:

1. **Run ID và trạng thái:** RUNNING, COMPLETED, FAILED hoặc ABORTED. Chỉ đánh dấu COMPLETED sau trang cuối và sink thành công.
2. **Idempotent upsert:** khóa duy nhất theo source + stable ID, tách trường LDAP sở hữu với trường ứng dụng sở hữu.
3. **Generation reconciliation:** không xem record chưa thấy là đã xóa trước khi scan đầy đủ.
4. **Load guardrail:** page size, max pages, timeout, số scan song song và backoff.
5. **Recovery:** khi cookie hết hạn sau restart, quét lại từ đầu và dùng upsert idempotent; không cố tiếp tục bằng page number.
6. **Đồng bộ delta:** nếu cần ít tải hơn full scan, nghiên cứu một change feed được server hỗ trợ như RFC 4533 hoặc AD DirSync; không nhầm cookie của chúng với RFC 2696.
7. **Bảo mật:** kiểm soát bind account, TLS, ACL và tránh lưu credential/cookie trong log.

### Checklist chấm bài

| Tiêu chí | Đạt khi |
| --- | --- |
| Server-side paging | Có RFC 2696 control và cookie trả từ LDAP server |
| Subtree search | Có SearchControls.SUBTREE_SCOPE, base/filter đúng |
| Điều kiện dừng | Dựa trên cookie/hasMore, không dựa vào kích thước trang |
| Bảo vệ bộ nhớ | Chuyển từng batch cho sink, không gom toàn bộ vào List |
| Định danh | Có source ID và stable entry ID |
| Lỗi | Không đánh dấu hoàn tất khi timeout, size limit, lỗi mapper hoặc sink |
| Idempotency | Rerun hoặc entry lặp không tạo bản ghi trùng |
| Bảo mật | LDAPS/StartTLS, credential từ secret, ACL tối thiểu |
| Quan sát | Có page count, entry count, duration, failure và scan status |
| Kiểm thử | Có integration test server hỗ trợ control, không chỉ mock |

## 18. Tổng kết

**Phân trang search subtree với server control** không phải là việc chia một danh sách Java thành từng phần. Nó là một chuỗi LDAP search với **Simple Paged Results Control**, cookie do server quản lý và vòng đời truy vấn phải được xử lý đúng.

Trong Spring LDAP, **LdapTemplate + SearchControls.SUBTREE_SCOPE + PagedResultsDirContextProcessor** là cách thực hành phù hợp để minh họa cơ chế. Sản phẩm thực cần kiểm tra server support, connection affinity, giới hạn tài nguyên, TLS và schema; xử lý paging cookie như giá trị opaque, phân biệt scan hoàn tất với scan lỗi và không suy diễn một vòng quét là snapshot nhất quán. Nếu kết quả dùng cho đồng bộ, hãy bổ sung stable ID, upsert idempotent và reconciliation để ứng dụng an toàn cả khi directory thay đổi giữa các trang.
