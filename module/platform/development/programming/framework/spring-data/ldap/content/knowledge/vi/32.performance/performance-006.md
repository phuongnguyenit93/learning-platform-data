# Tránh truy vấn lặp khi ánh xạ người dùng và nhóm

Trong một ứng dụng **Spring Data LDAP**, việc ánh xạ LDAP entry sang đối tượng Java bằng ODM giúp xử lý người dùng và nhóm thuận tiện hơn. Tuy nhiên, nếu mỗi lần tải một người dùng lại chạy thêm một truy vấn LDAP để tìm các nhóm mà người đó thuộc về, một yêu cầu trả về 100 người dùng có thể phát sinh **101 LDAP search** hoặc nhiều hơn. Hiện tượng này tương tự vấn đề **N+1 query**, nhưng ở đây chi phí nằm ở mạng, LDAP server, connection pool, TLS, schema và cách tìm kiếm trong cây thư mục, không phải SQL JOIN.

Bài thuộc chương **Hiệu năng**, với đề tài **“Tránh truy vấn lặp khi ánh xạ người dùng và nhóm”**, hướng dẫn nhận diện truy vấn phát sinh khi ánh xạ user–group, đo số thao tác LDAP thực tế, thiết kế **tải theo hai pha**, **gom điều kiện theo lô**, **giảm lượng thuộc tính**, kiểm soát **nested group**, cache và tính nhất quán. Các giải pháp được đặt trong phạm vi **SPRING_DATA_LDAP**: dùng DN, `objectClass`, schema, `LdapRepository`/`LdapTemplate`, LDAP filter an toàn, tài khoản bind tối thiểu và kiểm thử với directory.

**Nguyên tắc:** đừng tối ưu bằng cách đơn thuần tăng kích thước connection pool. Trước hết cần biết vì sao một tác vụ nghiệp vụ sinh ra nhiều LDAP operations, và liệu có thể giảm số lần tìm kiếm mà vẫn giữ đúng kết quả, base DN, ACL và tính nhất quán hay không.

## 1. Mô hình ví dụ: người dùng và nhóm là những entry khác nhau

Giả sử LDAP server phục vụ naming context `dc=example,dc=org`:

```text
dc=example,dc=org
├── ou=people
│   ├── uid=u1001
│   ├── uid=u1002
│   └── uid=u1003
├── ou=groups
│   ├── cn=developers
│   ├── cn=reviewers
│   └── cn=operators
└── ou=service-accounts
    └── cn=svc-reader
```

Một người dùng:

```ldif
dn: uid=u1001,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: u1001
cn: An Nguyen
sn: Nguyen
mail: an@example.org
```

Một nhóm theo schema `groupOfNames`:

```ldif
dn: cn=developers,ou=groups,dc=example,dc=org
objectClass: top
objectClass: groupOfNames
cn: developers
member: uid=u1001,ou=people,dc=example,dc=org
member: uid=u1002,ou=people,dc=example,dc=org
```

Những đặc điểm quan trọng:

- User có DN đầy đủ như `uid=u1001,ou=people,dc=example,dc=org`; **UID riêng lẻ không phải DN**.
- Nhóm cũng có DN của riêng mình. `cn=developers` có thể không duy nhất nếu tồn tại ở các OU khác nhau.
- Thuộc tính `member` có thể **đa trị** và chứa các **DN của thành viên**, không phải một foreign key trong SQL.
- `objectClass=groupOfNames` là mô hình ví dụ; các server và object class khác có thể dùng `uniqueMember` hoặc thuộc tính, quy tắc khác.
- Một nhóm có thể có người dùng hoặc nhóm khác làm thành viên. **Nhóm lồng nhau** là một bài toán riêng.
- LDAP server thực thi schema và ACL; nếu tài khoản chỉ có quyền đọc user nhưng không đọc được `member`, không thể giả định một trường ánh xạ Java sẽ tự tìm được membership.

Bài này dùng dữ liệu thử nghiệm, không giả định mọi directory đều có schema hoặc naming convention như trên. Đặc biệt trong **Active Directory**, user thường có RDN `CN=...` và group dùng `objectClass=group`; phải chọn filter và attribute phù hợp với AD thật.

## 2. Bài toán N+1 LDAP search xuất hiện như thế nào?

Một REST endpoint cần trả danh sách người dùng kèm các nhóm:

```json
[
  {
    "uid": "u1001",
    "name": "An Nguyen",
    "groups": ["developers", "reviewers"]
  },
  {
    "uid": "u1002",
    "name": "Binh Tran",
    "groups": ["developers"]
  }
]
```

Một cách viết dễ hiểu nhưng tốn kém:

```text
1 LDAP search để lấy 100 người dùng
      │
      ├── user 1  → LDAP search tìm group có member=user1 DN
      ├── user 2  → LDAP search tìm group có member=user2 DN
      ├── user 3  → LDAP search tìm group có member=user3 DN
      ├── ...
      └── user 100 → LDAP search tìm group có member=user100 DN

Tổng: 1 + 100 = 101 LDAP search (chưa tính paging/retry)
```

Với mỗi người, ứng dụng có thể thực hiện:

```ldap
(&(objectClass=groupOfNames)(member=uid=u1001,ou=people,dc=example,dc=org))
```

rồi đổi DN người dùng và chạy lại. **Bottleneck không phải ODM tự động “join”**, mà là code ứng dụng **chủ động phát sinh một search cho mỗi object**.

### Chi phí không chỉ là số lệnh

Mỗi LDAP operation có thể kéo theo:

- Network round trip tới LDAP server hoặc domain controller.
- Tìm kiếm theo attribute và áp dụng ACL, matching rule, index.
- Phân bổ hoặc mượn `DirContext` từ pool; có thể phải tạo kết nối/bind/TLS handshake.
- Serialization dữ liệu LDAP và chuyển thành Java object/DTO.
- Referral, paging, retry hoặc failover tạo thêm nhiều operation.
- Tranh chấp connection pool khi nhiều HTTP request cùng chạy.

Do đó **101 search nhanh** trong môi trường local có thể trở thành độ trễ lớn trong production qua mạng hoặc khi directory chịu tải đồng thời.

## 3. Đo N+1 trước khi sửa code

Trước khi chọn chiến lược, ghi lại **số LDAP search thực tế cho một lời gọi nghiệp vụ**, độ trễ và kích thước payload. Không chỉ đo số method Java được gọi.

| Metric | Ý nghĩa | Ví dụ dấu hiệu |
|---|---|---|
| LDAP search operations / API request | Số search thực sự gửi đến server | Tăng gần tuyến tính theo số user |
| LDAP lookup operations | Số lần đọc trực tiếp một DN | Một lookup cho mỗi member |
| p50/p95/p99 latency | Độ trễ của endpoint và LDAP operations | p95 tăng mạnh khi page size tăng |
| Connection borrow wait | Thời gian chờ mượn context | Pool cạn khi nhiều user được tải |
| Payload bytes / attributes | Lượng dữ liệu directory trả về | Group lớn kéo về quá nhiều `member` |
| Search base, scope, filter shape | Phạm vi và độ chọn lọc | Filter rộng hoặc không có index |
| Paging/referral/retry count | Các operation bổ sung | Một search logic có nhiều request |
| Error rate, size/time limit | Kết quả có đầy đủ không | Server cắt kết quả hoặc từ chối |

### Bằng chứng thực tế

Trong môi trường test được phép, có thể đếm thao tác từ **LDAP server access log** (nếu được bật) hoặc instrumentation tại tầng LDAP client. Log nên ghi **loại operation**, correlation ID, số trang, thời gian và bộ nhận diện filter dạng đã khử dữ liệu cá nhân; không log toàn bộ DN/email hoặc thông tin bind.

Một biểu đồ kỳ vọng trong bài test:

| Số user trả về | Cách mỗi user một search | Cách gom theo lô 20 user |
|---:|---:|---:|
| 1 | 2 LDAP search | 2 LDAP search |
| 20 | 21 LDAP search | Khoảng 2 LDAP search |
| 100 | 101 LDAP search | Khoảng 6 LDAP search |
| 200 | 201 LDAP search | Khoảng 11 LDAP search |

Các số của cột gom lô là **mô hình minh họa**: 1 search lấy user + một search group cho mỗi lô, **chưa tính paging, referral, retry, lookup bù**. Kết quả thực cần đo trên hạ tầng đang dùng.

## 4. ODM không tự có lazy loading quan hệ kiểu JPA

Spring LDAP ODM có annotation như `@Entry`, `@Id`, `@Attribute` để ánh xạ entry sang Java object. Một entity user:

```java
import javax.naming.Name;

import org.springframework.ldap.odm.annotations.Attribute;
import org.springframework.ldap.odm.annotations.Entry;
import org.springframework.ldap.odm.annotations.Id;

@Entry(
    base = "ou=people",
    objectClasses = {
        "top", "person", "organizationalPerson", "inetOrgPerson"
    }
)
public class DirectoryPerson {

    @Id
    private Name dn;

    @Attribute(name = "uid")
    private String uid;

    @Attribute(name = "cn")
    private String commonName;

    public DirectoryPerson() {}

    public Name getDn() { return dn; }
    public void setDn(Name dn) { this.dn = dn; }
    public String getUid() { return uid; }
    public void setUid(String uid) { this.uid = uid; }
    public String getCommonName() { return commonName; }
    public void setCommonName(String commonName) {
        this.commonName = commonName;
    }
}
```

Ví dụ một group entity có thể giữ tập DN thành viên:

```java
import java.util.Set;
import javax.naming.Name;

import org.springframework.ldap.odm.annotations.Attribute;
import org.springframework.ldap.odm.annotations.Entry;
import org.springframework.ldap.odm.annotations.Id;

@Entry(base = "ou=groups", objectClasses = {"top", "groupOfNames"})
public class DirectoryGroup {

    @Id
    private Name dn;

    @Attribute(name = "cn")
    private String commonName;

    @Attribute(name = "member")
    private Set<String> memberDns;

    public DirectoryGroup() {}

    public Name getDn() { return dn; }
    public void setDn(Name dn) { this.dn = dn; }
    public String getCommonName() { return commonName; }
    public void setCommonName(String commonName) {
        this.commonName = commonName;
    }
    public Set<String> getMemberDns() { return memberDns; }
    public void setMemberDns(Set<String> memberDns) {
        this.memberDns = memberDns;
    }
}
```

Ví dụ giả định ODM trong phiên bản đang dùng hỗ trợ cách ánh xạ collection này và directory cho phép đọc `member`. **Luôn kiểm thử converter/kiểu phần tử, thuộc tính tùy chọn và đa trị trên server đích.**

Điều cần nhớ:

- `DirectoryGroup.memberDns` không phải một `@OneToMany` tự động tải `DirectoryPerson`.
- ODM biết ánh xạ `member` thành **giá trị thuộc tính**, không tự làm SQL JOIN.
- Nếu getter `getGroups()` tự gọi repository để search, ứng dụng **đã tự tạo N+1**.
- Nếu serialization JSON gọi một getter có side effect LDAP, số search có thể khó nhìn thấy hơn.

**Khuyến nghị:** phân biệt rõ **entity đọc từ LDAP** với **DTO trả về API**. Thực hiện enrichment membership có kiểm soát tại service, không tự tải nhóm bên trong getter của entity.

## 5. Hai hướng tìm membership và sự khác nhau

Với user DN đã biết, có ít nhất hai chiến lược chính:

| Hướng truy vấn | Cách tìm | Lợi ích | Giới hạn |
|---|---|---|---|
| Từ user sang group | Tìm group có `member=userDN` | Phù hợp schema group có `member` và index | Có thể thành N search cho N user |
| Từ group sang user | Đọc `member` của nhóm rồi map DN tới users | Một group trả nhiều DN | Group quá lớn gây payload lớn |
| Thuộc tính backlink như `memberOf` | Đọc group DN trực tiếp từ user khi server cung cấp | Có thể giảm truy vấn phụ | Không chuẩn phổ quát; có thể thiếu nhóm đặc biệt/lồng nhau |
| Membership index/cache nội bộ | Lưu map user stable ID ↔ group DN từ lần đồng bộ | Đọc nhanh, tránh LDAP search mỗi request | Cần cơ chế refresh/reconcile/ACL và xử lý dữ liệu cũ |

Không có phương án tối ưu cho mọi directory. Quyết định phụ thuộc **phạm vi**, **số người**, **số nhóm**, **kích thước membership**, **matching rule/index**, **quyền** và yêu cầu **freshness**.

### Cần hiểu điều gì về `memberOf`?

Một số directory, đặc biệt AD, cung cấp backlink `memberOf`. Tuy nhiên:

- Không phải schema LDAP nào cũng có thuộc tính này.
- Nó có thể là **thuộc tính được tính ra bởi server**, không được ghi trực tiếp.
- Kết quả có thể chỉ thể hiện **membership trực tiếp**, không tự mở rộng mọi nhóm lồng nhau.
- Trong AD, các cơ chế group/primary group có quy tắc riêng; không đồng nhất `memberOf` với toàn bộ quyền thực tế.
- Nếu thuộc tính bị ACL che hoặc endpoint Global Catalog có subset thuộc tính, kết quả có thể thiếu.

Vì vậy, **chỉ tối ưu bằng một lần đọc `memberOf` nếu directory đích có contract được kiểm thử** và nghiệp vụ chấp nhận giới hạn đó.

## 6. Anti-pattern: lặp search cho từng người dùng

Một service có thể trông như sau (mã minh họa anti-pattern, không nên sao chép vào production):

```java
import java.util.ArrayList;
import java.util.List;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import static org.springframework.ldap.query.LdapQueryBuilder.query;

public final class NaiveGroupLookup {

    private final LdapTemplate ldap;

    public NaiveGroupLookup(LdapTemplate ldap) {
        this.ldap = ldap;
    }

    public List<String> groupsForOneUser(String fullUserDn) {
        LdapQuery q = query()
                .base("ou=groups")
                .where("objectClass").is("groupOfNames")
                .and("member").is(fullUserDn);

        return ldap.search(q, (attrs) ->
                (String) attrs.get("cn").get());
    }

    public List<List<String>> groupsForUsers(
            List<String> fullUserDns) {

        List<List<String>> result = new ArrayList<>();
        for (String fullUserDn : fullUserDns) {
            // Mỗi lần lặp lại phát sinh một LDAP search.
            result.add(groupsForOneUser(fullUserDn));
        }
        return result;
    }
}
```

Code sử dụng `LdapQueryBuilder` nên **không nhất thiết có LDAP injection**, nhưng vẫn có thể rất chậm vì **N search**. Tránh nhầm **“filter an toàn”** với **“truy vấn hiệu quả”**.

Nếu mỗi user còn được đọc từng group bằng `lookup(groupDn)` để lấy tên hoặc thuộc tính, có thể xuất hiện thêm một lớp N+1 khác. Trước khi tối ưu, hãy vẽ chuỗi operations thực sự trong request, không chỉ tìm một vòng `for`.

## 7. Chiến lược hai pha: đọc users rồi gom membership theo lô

Thay vì tìm từng user một, có thể:

1. Search users ở `ou=people` với filter đủ hẹp và chỉ lấy thuộc tính cần dùng.
2. Lấy **DN đầy đủ đã được xác minh** của những users trong trang kết quả.
3. Chia danh sách thành các lô nhỏ, ví dụ **20 user/lô**.
4. Với mỗi lô, tìm groups có `member` bằng **một trong những DN** của user trong lô.
5. Từ group trả về, đọc các `member` DN và **ánh xạ ngược** tới tập user đã yêu cầu.
6. Gắn nhóm vào DTO ở service và kiểm tra tính đầy đủ của các search.

LDAP filter cho ba user có thể là:

```ldap
(&(objectClass=groupOfNames)
  (|(member=uid=u1001,ou=people,dc=example,dc=org)
    (member=uid=u1002,ou=people,dc=example,dc=org)
    (member=uid=u1003,ou=people,dc=example,dc=org)))
```

Khi gửi lên LDAP, filter ở dạng một dòng (không có whitespace trang trí):

```ldap
(&(objectClass=groupOfNames)(|(member=uid=u1001,ou=people,dc=example,dc=org)(member=uid=u1002,ou=people,dc=example,dc=org)(member=uid=u1003,ou=people,dc=example,dc=org)))
```

Đây vẫn là **một LDAP search** với OR nhiều equality trên `member`, nhưng **không phải một phép JOIN chuẩn SQL**. Server có thể tận dụng index membership nếu cấu hình phù hợp; hiệu năng phải đo.

### Cẩn thận: OR filter không miễn phí

- Filter quá dài có thể vượt giới hạn request hoặc làm server xử lý đắt hơn.
- Directory phải đánh giá từng nhánh equality; hiệu quả phụ thuộc index `member`.
- Một group có rất nhiều member sẽ trả **payload lớn** nếu request cả thuộc tính `member`.
- Số group khớp có thể vượt size limit; cần paging và kiểm tra completeness.
- Nếu membership có DN đa dạng nhiều suffix, cần xác minh mỗi DN trong scope được phép.

**Kích thước lô 20 chỉ là ví dụ**, không phải ngưỡng chuẩn của LDAP. Hãy benchmark với các cỡ lô khác nhau, dựa trên filter length, số entry, tải server và latency.

## 8. Ví dụ Java: gom nhiều user DN thành một truy vấn group

Ví dụ sau minh họa một **batch resolver** cho schema `groupOfNames`, với các điều kiện:

- Spring LDAP `LdapContextSource` có base `dc=example,dc=org`.
- `fullUserDn` **đã được lấy và kiểm chứng từ directory/trusted identity mapping**, không phải DN tùy ý do HTTP client gửi.
- Nhóm nằm dưới `ou=groups`; thuộc tính `member` chứa DN đầy đủ.
- Mỗi nhóm được phép trả toàn bộ `member` và kích thước nhóm nằm trong giới hạn test.
- Bean `LdapTemplate` sử dụng tài khoản chỉ đọc, TLS hợp lệ và ACL tối thiểu.

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import javax.naming.Name;
import javax.naming.NamingException;
import javax.naming.ldap.LdapName;

import org.springframework.ldap.core.ContextMapper;
import org.springframework.ldap.core.DirContextOperations;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.filter.AndFilter;
import org.springframework.ldap.filter.EqualsFilter;
import org.springframework.ldap.filter.OrFilter;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.SearchScope;

import static org.springframework.ldap.query.LdapQueryBuilder.query;

public final class GroupBatchResolver {

    private static final int MAX_USERS_PER_BATCH = 20;
    private static final int MAX_GROUPS_PER_SEARCH = 200;

    private final LdapTemplate readLdapTemplate;

    public record PersonRef(String uid, String fullUserDn) {}

    public record GroupRow(String relativeGroupDn,
                           List<String> memberDns) {}

    public GroupBatchResolver(LdapTemplate readLdapTemplate) {
        this.readLdapTemplate = readLdapTemplate;
    }

    // Chỉ gọi với PersonRef đã được truy xuất/đối chiếu trong
    // phạm vi và quyền được phép, không nhận arbitrary DN từ client.
    public Map<Name, Set<String>> groupDnsByUser(
            List<PersonRef> people) throws NamingException {

        if (people == null || people.size() > MAX_USERS_PER_BATCH) {
            throw new IllegalArgumentException("Invalid batch size");
        }
        Map<Name, Set<String>> result = new LinkedHashMap<>();
        OrFilter anyMember = new OrFilter();

        for (PersonRef person : people) {
            Name canonicalDn = new LdapName(person.fullUserDn());
            if (result.putIfAbsent(
                    canonicalDn, new LinkedHashSet<>()) != null) {
                throw new IllegalArgumentException("Duplicate user DN");
            }
            anyMember.or(
                    new EqualsFilter("member", person.fullUserDn()));
        }

        if (people.isEmpty()) {
            return result; // Không gửi OR rỗng tới server.
        }

        AndFilter all = new AndFilter();
        all.and(new EqualsFilter("objectClass", "groupOfNames"));
        all.and(anyMember);

        LdapQuery q = query()
                .base("ou=groups")
                .searchScope(SearchScope.SUBTREE)
                .attributes("cn", "member")
                .timeLimit(3000)
                .countLimit(MAX_GROUPS_PER_SEARCH + 1)
                .filter(all);

        ContextMapper<GroupRow> mapper = ctx -> {
            DirContextOperations group =
                    (DirContextOperations) ctx;
            String[] members =
                    group.getStringAttributes("member");
            return new GroupRow(
                    group.getDn().toString(),
                    members == null
                            ? List.of()
                            : List.copyOf(Arrays.asList(members)));
        };

        List<GroupRow> matchedGroups =
                readLdapTemplate.search(q, mapper);

        // Bảo thủ: từ chối nếu chạm ngưỡng, vì không
        // thể coi kết quả có khả năng bị cắt là đầy đủ.
        if (matchedGroups.size() >= MAX_GROUPS_PER_SEARCH) {
            throw new IllegalStateException(
                    "Group search may be incomplete");
        }

        for (GroupRow group : matchedGroups) {
            for (String memberDn : group.memberDns()) {
                Name parsed = new LdapName(memberDn);
                Set<String> groupDns = result.get(parsed);
                if (groupDns != null) {
                    groupDns.add(group.relativeGroupDn());
                }
            }
        }
        return result;
    }
}
```

**Cách sử dụng:** nếu một trang gồm 20 `PersonRef` có DN đầy đủ, service gọi `groupDnsByUser(page)` **một lần**, sau đó gắn danh sách group DN lên DTO tương ứng. Với 100 user, chia thành năm lô; **không gọi một lần cho 100 user khi method có giới hạn 20**.

### Những lưu ý để code không bị hiểu sai

1. `Name` trong map là đối tượng JNDI có cấu trúc, giảm nguy cơ so sánh DN bằng phép cắt chuỗi. **Nó không bảo đảm tương đương mọi biến thể DN/alias/matching rule của server**.
2. `relativeGroupDn` từ `DirContextOperations.getDn()` cần được hiểu theo **context base của Spring LDAP**. Nếu gửi sang hệ thống khác, phải chuẩn hóa thành DN đầy đủ một cách có kiểm chứng.
3. `member` có thể là thuộc tính cực lớn. Ví dụ này phù hợp **group có số member hữu hạn và trả đủ giá trị**; phải đổi chiến lược nếu server giới hạn attribute values hoặc dữ liệu quá lớn.
4. `countLimit` là giới hạn phía query, không bảo đảm LDAP server trả 201 group rồi thành công. Ứng dụng phải phân loại **size/time limit, paging và partial results**; một request lỗi không được trả danh sách nhóm thiếu như đầy đủ.
5. Query `objectClass=groupOfNames` **không áp dụng nguyên xi cho AD group** hoặc schema dùng `groupOfUniqueNames`. Cần đổi object class, thuộc tính membership và test trực tiếp.
6. `EqualsFilter` escape **giá trị DN trong LDAP filter**. Với filter equality trên `member`, truyền **DN đúng**; điều này khác bước xây RDN bằng `LdapNameBuilder`.
7. `PersonRef.fullUserDn` phải được server/trusted mapping xác nhận. Nếu danh sách đến từ API tùy ý, phải có kiểm tra OU, naming context và quyền trước khi truy vấn.
8. Tên group `cn` không được dùng làm khóa duy nhất toàn directory; ví dụ trả **group DN** để tránh nhầm tên ở OU khác.

Đoạn code chỉ là một pattern minh họa; với số nhóm lớn, group đa trị hàng nghìn thành viên hoặc AD ranged retrieval, cần thiết kế bộ đọc chuyên biệt và paging thay vì xem đây là phương pháp tối ưu tuyệt đối.

## 9. Tối ưu hơn nữa: không phải lúc nào cũng lấy toàn bộ `member`

Ở lô 20 user, một group có 30.000 member có thể khớp chỉ vì một user. Nếu để dựng reverse mapping mà tải **toàn bộ** `member`, ứng dụng có thể chuyển từ N+1 search sang **một search nhưng hàng megabyte payload**.

Có thể cân nhắc:

| Phương án | Ưu điểm | Đánh đổi |
|---|---|---|
| Đọc `member` đầy đủ như ví dụ | Dễ map group→nhiều user | Tốn bytes/memory cho group rất lớn |
| Dùng `memberOf` trên user | Ít truy vấn bổ sung nếu server cung cấp đủ | Hành vi server-specific, có thể thiếu primary/nested groups |
| Đọc group metadata và kiểm tra membership bằng compare | Có thể tránh tải mọi member value | Vẫn cần operation bổ sung, ACL/compare semantics cần test |
| Tạo/duy trì membership index ở ứng dụng | Một lần lookup nội bộ nhanh | Chi phí đồng bộ và quản trị freshness |
| Truy vấn theo từng user có index tốt | Dễ kiểm soát payload, với số user nhỏ có thể hợp lý | N operations; p95 có thể cao |
| Dùng cơ chế server-specific | Tận dụng khả năng directory | Giảm tính di động và cần test kỹ |

Không có quy tắc “cứ gom OR là tốt nhất”. **Tối ưu theo tổng chi phí**: số LDAP operations, thời gian, bytes truyền, số attribute value, CPU server, bộ nhớ client và độ tin cậy kết quả.

## 10. Giới hạn đặc thù trong Active Directory

Active Directory thường có cách tổ chức user/group và xử lý membership khác ví dụ `groupOfNames`:

- Group thường có `objectClass=group` và thuộc tính `member`.
- User có thể có thuộc tính backlink `memberOf` cho membership trực tiếp, nhưng **không nhất thiết bao gồm toàn bộ logic primary group hoặc nested group**.
- `objectGUID` là thuộc tính nhị phân ổn định theo vòng đời AD object hơn DN; cần converter đúng khi làm khóa của cache/bản sao.
- Truy vấn AD qua **Global Catalog** có phạm vi, tập thuộc tính và quyền khác domain controller thông thường; không suy group data luôn đầy đủ trên GC.
- AD có thể trả thuộc tính đa trị lớn qua **ranged retrieval**, ví dụ tên thuộc tính theo dạng `member;range=0-1499`. Nếu code chỉ tìm chính xác `member` mà server trả tên có range, có nguy cơ hiểu nhầm nhóm rỗng.

### Ranged retrieval không phải LDAP paging

Hai vấn đề cần phân biệt:

| Cơ chế | Đơn vị được chia | Điều cần làm |
|---|---|---|
| LDAP Paged Results Control | **Các entry** trong kết quả search | Theo dõi cookie và số trang, xử lý tính nhất quán |
| AD ranged retrieval | **Các giá trị của một attribute đa trị trên một entry** | Đọc đủ các range theo contract AD, xử lý giới hạn/ACL |

Ví dụ nhận 100 group entries không có nghĩa đã nhận đủ 100% member của từng group. Nếu cần ánh xạ quyền hoặc đối soát membership, **một attribute bị cắt có thể nguy hiểm hơn một search bị cắt** vì ứng dụng dễ nhầm người không còn thuộc nhóm.

Không viết bộ xử lý ranged retrieval chung cho mọi LDAP server; đây là đặc điểm phải được triển khai và kiểm thử **riêng cho AD**.

## 11. Nhóm lồng nhau: tránh N+1 theo nhiều tầng

Giả sử:

```text
group developers
  ├── uid=u1001
  └── group backend
        ├── uid=u1002
        └── group platform
              └── uid=u1003
```

Nếu ứng dụng duyệt nhóm lồng nhau bằng cách lookup từng member rồi lại lookup mọi nhóm của member, có thể phát sinh **hàng trăm LDAP operations**, lặp vô hạn hoặc stack overflow khi có vòng tham chiếu.

Cần phân biệt:

- **Membership trực tiếp:** group có `member=userDN`.
- **Membership bắc cầu:** user thuộc nhóm thông qua một hay nhiều nhóm trung gian.
- **Quyền thực tế:** có thể chịu quy tắc đặc thù server, chính sách ứng dụng, loại nhóm và cơ chế xác thực.

Khi business cần nested groups:

1. Xác nhận server có **matching rule/control server-specific** cho truy vấn bắc cầu hay không; không tự giả định LDAP chuẩn có JOIN/recursive query.
2. Nếu duyệt ở client, dùng **visited set theo group identity/DN** để tránh chu kỳ.
3. Đặt **maxDepth**, **maxGroups** và thời gian tối đa; fail khi chưa thu đủ dữ liệu.
4. Nếu duyệt breadth-first, có thể **batch group DN theo từng mức** thay vì lookup từng nhóm.
5. Chỉ mở rộng những nhánh được ACL và nghiệp vụ cho phép.
6. Với nghiệp vụ authorization, không dùng kết quả **partial** làm căn cứ cấp quyền hay thu hồi quyền.

Ở AD, matching rule in chain có thể hỗ trợ một số phép kiểm membership bắc cầu tùy attribute và server, nhưng **ngữ nghĩa phải được kiểm thử cụ thể**; không khái quát sang OpenLDAP hoặc mọi loại group.

## 12. Projection: trả đúng dữ liệu cần hiển thị

Không phải endpoint nào cũng cần toàn bộ membership. Nhiều API danh sách chỉ cần:

```json
{
  "uid": "u1001",
  "name": "An Nguyen",
  "groupCount": 2
}
```

hoặc thậm chí chỉ `uid` và `name`.

**Bẫy hiệu năng:** nếu `DirectoryPerson` có getter `getGroups()` tự gọi LDAP để trả JSON, một danh sách hiển thị 100 dòng vẫn có N+1 chỉ vì serializer truy cập getter.

Thiết kế API theo nhu cầu:

| Endpoint | Dữ liệu cần | Chiến lược |
|---|---|---|
| Danh sách user | UID, tên | Chỉ search user; **không tải groups** |
| Chi tiết một user | Thông tin user + group trực tiếp | Một user lookup + group search có phạm vi |
| Danh sách có group badges | User page + group membership của trang | Batching hoặc backlink đã kiểm chứng |
| Quản lý nhóm | Group metadata + thành viên phân trang/kiểm soát | Đọc group theo DN, xử lý đa trị và giới hạn |
| Kiểm tra quyền realtime | Membership đủ tin cậy và mới | Chính sách riêng, không cache bừa và không chấp nhận partial |

**Một cách tối ưu hiệu quả nhất là không thực hiện query chưa cần.** Khi UI yêu cầu groupCount, cũng cần kiểm tra xem directory có hỗ trợ cách đếm server-side hay không; không mặc định có aggregate COUNT giống SQL.

### Dùng `AttributesMapper` cho DTO mỏng

```java
import java.util.List;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.query.LdapQuery;

import static org.springframework.ldap.query.LdapQueryBuilder.query;

public record UserSummary(String uid, String name) {}

// Đặt trong một service có biến readLdapTemplate đã được tiêm.
LdapQuery q = query()
        .base("ou=people")
        .attributes("uid", "cn")
        .where("objectClass").is("inetOrgPerson");

AttributesMapper<UserSummary> mapper = attrs ->
        new UserSummary(
                (String) attrs.get("uid").get(),
                (String) attrs.get("cn").get());

List<UserSummary> users =
        readLdapTemplate.search(q, mapper);
```

Đây là ví dụ **minh họa bên trong method**, không phải source file Java hoàn chỉnh. Cần có validation, search scope, paging/limit và xử lý attribute vắng mặt theo yêu cầu thật. Khi chỉ cần hai trường, một mapper DTO thường rõ ràng hơn việc tải entity lớn và vô tình kích hoạt logic membership.

## 13. Paging người dùng rồi batch groups theo đúng trang

Không nên lấy toàn bộ 50.000 users chỉ để gom chung một filter OR dài hàng megabyte. Nên:

```text
LDAP search users (page size phù hợp)
           │
           ▼
  50 user trên một trang
           │
           ▼
  Chia lô membership: 20 + 20 + 10
           │
           ▼
  3 LDAP group searches (nếu đầy đủ)
           │
           ▼
    Gắn group DN vào DTO
           │
           ▼
      Trả một API page
```

Một endpoint trả nhiều trang cần xác định:

- Có server-side paging control không? Kiểm tra `supportedControl` của server.
- Search filter và sort có giữ đủ tính ổn định qua các trang không?
- Có áp dụng **time/size limit** hoặc referral nào khiến kết quả không hoàn chỉnh?
- Một user vừa đổi OU trong lúc paging sẽ ảnh hưởng đến tính nhất quán thế nào?
- Member DN có thể đổi khi rename/move; membership mapping phải xử lý được cách directory cập nhật tham chiếu.

**Một trang LDAP không đồng nghĩa một snapshot nguyên tử** nếu dữ liệu thay đổi trong lúc đọc. Với giao diện hiển thị thông thường, eventual consistency có thể chấp nhận; với bài toán phân quyền hoặc đối soát, cần contract chặt hơn.

## 14. Cache membership có thể giúp, nhưng không được làm sai quyền

Cache có thể giảm số lần hỏi LDAP khi người dùng/nhóm được truy cập lặp lại:

```text
HTTP request
    │
    ▼
Cache user-group membership
    │  hit        miss/expired
    │             │
    ▼             ▼
DTO           LDAP resolver
                  │
                  ▼
           lưu kết quả có TTL
```

Chọn **cache key** cẩn thận:

- DN có thể đổi khi user/group rename hoặc chuyển OU.
- Nếu server cung cấp `entryUUID` hoặc `objectGUID`, có thể dùng stable ID nhưng phải hiểu vòng đời/migration.
- Key còn cần **source directory/tenant**, phạm vi và dạng membership (direct hay nested).
- Nếu cache data chịu **ACL theo người gọi**, không được trả dữ liệu do principal đặc quyền đọc cho người không được xem.

### Ba chiến lược làm mới

| Chiến lược | Ưu điểm | Hạn chế |
|---|---|---|
| TTL ngắn | Đơn giản, giới hạn độ cũ | Vẫn có stale trong TTL |
| Invalidate khi workflow ghi thành công | Giảm stale do ứng dụng tự cập nhật | Không thấy thay đổi từ hệ thống khác |
| Đồng bộ thay đổi directory + reconcile | Có thể cập nhật gần realtime | Cần change tracking, retry, kiểm chứng delete/rename |

**Không dùng cache group membership quá cũ để cấp quyền bảo mật nhạy cảm.** Nếu ứng dụng vừa thu hồi một nhóm đặc quyền, một cache stale có thể giữ quyền lâu hơn dự kiến. Khi không có khả năng xác minh trạng thái hoặc directory gặp lỗi, lựa chọn fail closed đối với hành động yêu cầu quyền cao.

**Negative caching** (lưu “không có nhóm”) cũng phải có TTL và chỉ áp dụng khi kết quả LDAP **đầy đủ**. Một truy vấn bị ACL che/timeout không phải bằng chứng người dùng không thuộc nhóm.

## 15. Read/write separation, pool và TLS

Các truy vấn membership thường chỉ đọc. Vì vậy:

- Dùng **tài khoản bind chỉ đọc** các entry/attribute được phép.
- Không sử dụng tài khoản có quyền modify/delete chỉ để lấy group names.
- Nếu hệ thống có đường đọc và ghi, gắn query group vào đúng **readLdapTemplate** hoặc repository được cấu hình với read context.
- Nếu cần connection pool, đặt giới hạn và timeout hợp lý; **không** giải quyết N+1 bằng cách tăng pool vô hạn.
- Với StartTLS, cần kiểm tra sự tương thích của pooling với vòng đời TLS/context; không bật native JNDI LDAP pooling tùy tiện.
- Tất cả kết nối sử dụng LDAPS hoặc StartTLS với xác minh chứng chỉ và hostname.

### Vì sao tăng pool không phải lời giải gốc?

Giả sử 20 HTTP requests đồng thời, mỗi request tải 100 users và chạy 100 searches tìm group. Tổng có thể xấp xỉ **2.000 search phụ**. Tăng pool từ 5 lên 50 connections có thể làm client chờ ít hơn, nhưng LDAP server vẫn phải xử lý cùng khối lượng (thậm chí nhận tải đột ngột hơn).

Nếu giảm còn 5 group searches/request bằng batching, cùng workload chỉ còn khoảng **100 search phụ** (chưa tính paging/retry). Chênh lệch này thường quan trọng hơn việc thay đổi số connection, nhưng **chỉ được xem là tối ưu khi đo và xác minh tính đầy đủ**.

## 16. Lưu ý về DN, filter và quyền khi batch

Bộ lọc group bằng `member=userDN` có ít nhất ba tầng escaping/validation khác nhau:

1. **DN syntax:** khi dựng DN từ RDN, dùng `LdapNameBuilder`; không nối chuỗi `"uid=" + input + ",ou=people"`.
2. **LDAP filter syntax:** khi đưa DN vào equality filter, dùng `EqualsFilter("member", fullDn)` để escape giá trị theo RFC 4515.
3. **Authorization:** DN hợp lệ và filter an toàn **không đồng nghĩa** người gọi được phép đọc membership của user đó.

Ngoài ra:

- `@Id Name` trong ODM thường biểu diễn DN tương đối theo context base, không mặc định là DN đầy đủ.
- `member` của group thường chứa **DN đầy đủ**; cần quy đổi chính xác, không chỉ so chuỗi UID.
- Client phải biết nguồn/server để tránh trộn DN từ hai naming context hoặc domain khác nhau.
- Một filter gồm 20 DN do caller tự chọn có thể trở thành công cụ **enumeration** nếu không có quyền nghiệp vụ.
- Query phải cố định base `ou=groups`, object class, attribute allowlist và scope; không tự mở tìm kiếm toàn forest.
- Khi DN chứa dấu phẩy, dấu cộng, dấu bằng hoặc ký tự đặc biệt, parser DN và filter builder phải được thử cùng dữ liệu thật.

**Không dùng một group name dạng `cn` làm khóa membership toàn cục**, và không suy các giá trị `member` luôn trỏ tới user: chúng có thể trỏ tới group hoặc object khác theo schema.

## 17. Khi nào nên giữ vài query nhỏ thay vì batch lớn?

Batching không phải công thức bắt buộc. Những trường hợp có thể giữ truy vấn riêng:

- Trang chỉ có một hoặc hai người dùng, overhead gom/parse không mang lại lợi ích.
- Server có index membership rất tốt, mỗi search nhỏ có response ít và latency thấp.
- Group rất lớn khiến lấy toàn bộ `member` để reverse mapping trở nên đắt hơn nhiều query riêng.
- Cần result ACL khác nhau cho từng user, không thể gom vào một principal/scope chung an toàn.
- Có cơ chế backlink hoặc native API theo server hỗ trợ truy vấn đúng và nhanh hơn.
- Directory áp giới hạn filter OR hoặc không hỗ trợ request lớn.

Cách chọn nên là **benchmark A/B** trên cùng dataset, cùng tài khoản bind và cùng giới hạn, không dựa vào số search một cách đơn độc.

| Phương án | LDAP ops | Bytes trả về | Correctness | p95 latency |
|---|---|---|---|---|
| N group searches | Cao | Có thể nhỏ mỗi search | Dễ so từng user | Cần đo |
| OR theo lô | Thấp hơn | Có thể lớn với group đa trị | Cần kiểm tra đầy đủ/giới hạn | Cần đo |
| `memberOf` | Có thể rất thấp | Thường gọn | Server-specific | Cần đo |
| Membership cache | Gần 0 khi hit | Dữ liệu từ cache | Cần freshness/invalidation | Cần đo |

## 18. Các lỗi và anti-pattern thường gặp

| Triệu chứng | Nguyên nhân khả dĩ | Hành động |
|---|---|---|
| Trang 50 user gọi 51 LDAP search | Một group search trong mỗi vòng lặp | Gom theo lô hoặc chỉ tải group khi cần |
| Search giảm nhưng payload tăng mạnh | Mỗi group trả quá nhiều `member` | Đo bytes/attr values, đổi chiến lược |
| Membership bị thiếu | Size/time limit, paging hoặc range chưa đọc hết | Đánh dấu incomplete, lấy đủ theo cơ chế server |
| User có nhóm nhưng API báo rỗng | ACL reader thiếu quyền đọc `member` hoặc scope sai | Kiểm tra bind account và quyền |
| AD group bị bỏ qua | Filter `groupOfNames` không khớp AD schema | Dùng objectClass phù hợp |
| Nhóm lồng nhau gây treo | Không có visited set/maxDepth | Giới hạn duyệt, chống chu kỳ |
| Group cũ xuất hiện sau rename | Cache/DN mapping chưa refresh | Invalidate theo stable identity/scope |
| Permission cũ vẫn còn | Cache membership quá lâu | Chính sách consistency và fail closed |
| Tăng pool không cải thiện | LDAP server quá tải hoặc filter thiếu index | Đo actual operations và server search plan |
| Filter không đúng khi DN có ký tự đặc biệt | Nối raw DN/filter | Dùng DN builder và filter builder |
| Người dùng bị mất khỏi kết quả sau move | Base DN cố định không còn chứa entry | Xử lý theo nghiệp vụ, không tự tìm toàn directory |
| `getGroups()` làm N+1 bất ngờ | Getter/serializer gọi LDAP | Chuyển enrichment sang service |
| Test pass dù code query lặp | Dữ liệu test chỉ một người dùng | Tăng page size và assert số operations |

**Phân loại lỗi rõ ràng:** network/TLS, authentication, ACL, schema, filter, size/time limit, paging và mapping. Không gộp tất cả thành “user không có nhóm”.

## 19. Bộ kiểm thử tích hợp cho việc giảm N+1

Mock repository có thể xác nhận service gọi method bao nhiêu lần, nhưng chưa chứng minh server trả membership đầy đủ và nhanh. Cần directory test có schema, ACL và cấu trúc gần môi trường đích.

| Ca kiểm thử | Thiết lập | Kết quả kỳ vọng |
|---|---|---|
| Một user, một group | `u1001` thuộc `developers` | Ánh xạ đúng DN group |
| N user không group | 20 người không thuộc nhóm nào | Không trả nhóm giả |
| Một group chứa nhiều user | `developers` chứa `u1001` và `u1002` | Một group search có thể map cả hai |
| User thuộc nhiều group | `u1001` thuộc `developers`, `reviewers` | Không mất membership |
| Hai group cùng `cn` khác OU | DN group khác nhau | Không gộp nhầm theo cn |
| Group có member là group khác | Nested group | Không tự coi là user trực tiếp |
| Group rất lớn | Hàng nghìn `member` | Không báo đủ nếu bị ranged retrieval/limit |
| DN có dấu phẩy/escape | UID hoặc RDN đặc biệt trong test | Không làm hỏng filter và matching |
| User đổi OU | DN user thay đổi | Mapping/invalidation đúng contract |
| ACL không cho đọc member | Reader thiếu quyền | Lỗi/kết quả hạn chế được xử lý, không tự suy vắng membership |
| Size limit khi OR batch | Nhiều group khớp | Không trả kết quả cắt như hoàn chỉnh |
| Group class khác | `groupOfUniqueNames` hoặc AD `group` | Schema-specific adapter được test |
| TLS certificate sai | Server test với CA/hostname không hợp lệ | Fail closed, không fallback LDAP thường |
| 1/20/100 users | Các page kích cỡ khác nhau | Số LDAP operations thay đổi theo batching, không tuyến tính N |
| Nhiều request đồng thời | Load test có giới hạn | Pool wait, p95 và server metrics chấp nhận được |

**Tiêu chí hiệu năng:** trên cùng dataset/cùng server, so cách naïve và batching bằng **số LDAP search thực tế**, p95 latency, bytes payload, CPU server và số kết quả membership chính xác. Tốc độ cải thiện **không đạt yêu cầu** nếu đổi lại bằng sai ACL hoặc thiếu thành viên.

### Test logic ghép membership

Với group:

```text
developers:
  member = uid=u1001,ou=people,dc=example,dc=org
  member = uid=u1002,ou=people,dc=example,dc=org

reviewers:
  member = uid=u1001,ou=people,dc=example,dc=org
```

Khi tìm hai user trong cùng batch, kết quả cần là:

```text
u1001 → developers, reviewers
u1002 → developers
```

Test nên đối chiếu **tập group DN đầy đủ hoặc group ID**, không chỉ tên `cn`. LDAP không bảo đảm thứ tự kết quả nếu không có sort control, vì vậy không assert thứ tự list khi không có cơ sở.

## 20. Bài tập thiết kế và đánh giá

Một endpoint cần trả 120 người dùng, mỗi người có danh sách group trực tiếp. Directory dùng `groupOfNames` và `member`, base `dc=example,dc=org`, OU user `ou=people`, OU group `ou=groups`. Tài khoản dịch vụ chỉ được đọc một số thuộc tính.

Hãy trả lời:

1. Nếu code lấy user một lần rồi search groups cho từng user, cần tối thiểu bao nhiêu LDAP search? Chưa tính điều gì?
2. Nếu gom theo lô 20 user, số group searches dự kiến là bao nhiêu khi mọi search đều hoàn chỉnh?
3. Vì sao filter OR trên `member` phải dùng **DN đầy đủ**, không chỉ UID?
4. Làm sao dùng `EqualsFilter` để tránh LDAP injection khi member DN có ký tự đặc biệt?
5. Vì sao một group rất lớn có thể khiến batching **chậm hơn** dù giảm số search?
6. Khi server dùng AD ranged retrieval, cần kiểm tra gì trước khi tin dữ liệu `member` đã đầy đủ?
7. Nếu cần nested groups, làm sao tránh vòng tham chiếu và N+1 nhiều tầng?
8. Trường `memberOf` có thể giảm truy vấn trong trường hợp nào và có những giới hạn nào?
9. Tại sao cache group membership cần xử lý rename/move và quyền bị thu hồi?
10. Nếu API danh sách chỉ hiển thị tên, có cần tải group membership không?
11. Thiết kế ma trận benchmark để chọn cỡ batch hợp lý thay vì cố định 20 cho mọi tình huống.
12. Khi một group search bị size-limit error, được phép trả danh sách nhóm rỗng hoặc thiếu như “đầy đủ” không?

**Gợi ý:** phương án lặp cần ít nhất **121 search** (1 lấy user + 120 nhóm) nếu mỗi user chỉ một group search. Batch 20 người dự kiến **6 group searches**, cộng search user là **7** (chưa tính paging/retry). Để ánh xạ đúng, dùng DN thật và group DN; không dùng tên/UID đơn lẻ làm khóa phổ quát. Với các kết quả partial hoặc ACL không đủ, cần báo trạng thái không đầy đủ và tránh sử dụng trong quyết định quyền.

## 21. Checklist vận hành

Trước khi đưa tối ưu user-group mapping vào production:

- [ ] Đã đo **số LDAP search/lookup thực tế** trên mỗi request và từng page size.
- [ ] Xác định nơi phát sinh N+1: vòng lặp service, getter/entity, JSON serializer hoặc truy vấn nested group.
- [ ] Có chiến lược rõ ràng: **không tải nếu không cần**, batch OR, backlink, index hoặc cache.
- [ ] Có giới hạn batch/filter length, time/size limit, paging và kiểm chứng completeness.
- [ ] Không nhầm **LDAP paged results** với **AD ranged attribute values**.
- [ ] Ánh xạ membership bằng **DN/identity** phù hợp, không chỉ `cn` hoặc `uid`.
- [ ] Phân biệt group trực tiếp và nhóm lồng nhau, có max depth/visited set khi cần.
- [ ] Query dùng filter builder để escape giá trị, giữ base DN/scope/attribute allowlist.
- [ ] Tài khoản bind chỉ đọc, TLS được xác minh và ACL đúng phạm vi.
- [ ] Cache có TTL/invalidation, chính sách consistency và không cấp quyền theo dữ liệu stale.
- [ ] Đã test schema đặc thù, missing attribute, nhiều member, rename/move, giới hạn server và ACL.
- [ ] Đã so p95 latency, LDAP operations, payload bytes và server load trước–sau.

### Nguồn kỹ thuật tham khảo

- [Spring LDAP Reference](https://docs.spring.io/spring-ldap/reference/).
- [Spring Data LDAP Reference](https://docs.spring.io/spring-data/ldap/reference/).
- [RFC 4511 – Lightweight Directory Access Protocol](https://www.rfc-editor.org/rfc/rfc4511).
- [RFC 4512 – LDAP Directory Information Models](https://www.rfc-editor.org/rfc/rfc4512).
- [RFC 4515 – LDAP Search Filter String Representation](https://www.rfc-editor.org/rfc/rfc4515).

**Kết luận:** tránh truy vấn lặp khi ánh xạ người dùng và nhóm trong **Spring Data LDAP** đòi hỏi hiểu đúng **mô hình quan hệ dựa trên DN**, đo số LDAP operations và chọn chiến lược truy vấn theo dữ liệu thật. Batch OR, projection, backlink hoặc cache có thể giảm N+1, nhưng phải đồng thời giữ đúng schema, base/scope, escaping, TLS/ACL, tính đầy đủ của membership và yêu cầu nhất quán. Tối ưu thành công là **ít thao tác hơn mà vẫn đúng dữ liệu và đúng quyền**, không chỉ giảm một con số trên biểu đồ.
