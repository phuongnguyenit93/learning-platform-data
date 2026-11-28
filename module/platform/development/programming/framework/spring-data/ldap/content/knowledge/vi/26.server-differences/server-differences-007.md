# Giới hạn kích thước kết quả và đọc thuộc tính nhóm nhiều giá trị

Khi chuyển một ứng dụng Spring Data LDAP từ directory thử nghiệm sang **OpenLDAP** hoặc **Microsoft Active Directory (AD DS)**, truy vấn thành viên nhóm có thể gặp một hiện tượng khó nhận biết: API tìm được **một entry nhóm** nhưng danh sách `member` trả về chỉ chứa **một phần** thành viên. Đồng thời, một truy vấn liệt kê nhiều nhóm có thể bị giới hạn số **entry** trước khi kịp đi hết danh sách.

Đây là **hai loại giới hạn khác nhau**, đòi hỏi hai cách giải quyết khác nhau:

- **Giới hạn số entry của LDAP Search**: dùng filter/base/scope phù hợp, điều chỉnh `countLimit` và khi cần thì dùng **Simple Paged Results Control** (RFC 2696).
- **Giới hạn số giá trị trong một thuộc tính đa trị**: đặc biệt với Active Directory, dùng **range retrieval** qua tên thuộc tính như `member;range=0-999`, đọc tiếp cho tới khi server trả dấu `*` ở khoảng cuối.

Tăng `countLimit` hoặc bật phân trang Search **không khiến AD tự trả hết hàng nghìn giá trị `member` trong một entry**. Ngược lại, đọc đủ một nhóm lớn bằng `member;range` **không tự phân trang danh sách hàng nghìn entry nhóm**.

Bài thuộc chương **Khác biệt máy chủ** của mô-đun `SPRING_DATA_LDAP`, sử dụng Spring LDAP `LdapTemplate`, Spring Data LDAP repository/ODM, JNDI, DN, `objectClass`, schema, bộ lọc an toàn và kiểm thử với directory để xây một giải pháp đúng và có thể đối soát.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **Search result entry**, **giá trị của một LDAP attribute** và **kích thước dữ liệu truyền qua mạng**.
2. Hiểu `sizeLimit`/`countLimit`, `timeLimit` và giới hạn quản trị của server.
3. Giải thích vì sao AD DS thường có chính sách **`MaxPageSize`** và **`MaxValRange`** riêng.
4. Phân biệt **LDAP paging** với **AD range retrieval**, tránh sử dụng sai control/attribute.
5. Đọc đúng attribute ID động `member;range=low-high` và `member;range=low-*`.
6. Viết Java/JNDI qua `ContextSource` để đọc các range của một nhóm lớn, đóng context và giới hạn tài nguyên.
7. Xác định sự khác nhau giữa đọc `groupOfNames.member` ở OpenLDAP và đọc `group.member` ở AD.
8. Biết khi nào chỉ nên **Search kiểm tra một thành viên** thay vì tải toàn bộ danh sách nhóm.
9. Tránh sự cố khi Spring Data LDAP repository/ODM ánh xạ `member` thành `Set<Name>` nhưng dữ liệu bị cắt.
10. Kiểm thử 0, ít, đúng ngưỡng, vượt ngưỡng, thay đổi đồng thời, ACL, TLS, partial result và failure.
11. Đảm bảo chức năng phân quyền không nhầm **danh sách thiếu** với “người dùng không thuộc nhóm”.

## 2. Vì sao truy vấn một nhóm có thể thiếu thành viên?

Giả sử directory có:

~~~text
DC=example,DC=org
├── OU=People
│   ├── CN=Lan
│   ├── CN=Minh
│   └── ...
├── OU=Groups
│   ├── CN=Engineering-All       (3.200 members)
│   ├── CN=Platform-Admins       (20 members)
│   └── ... 2.000 nhóm khác
└── OU=Service
    └── CN=svc-group-reader
~~~

Một entry nhóm Active Directory minh họa:

~~~ldif
dn: CN=Engineering-All,OU=Groups,DC=example,DC=org
objectClass: top
objectClass: group
cn: Engineering-All
member: CN=Lan,OU=People,DC=example,DC=org
member: CN=Minh,OU=People,DC=example,DC=org
~~~

Trong AD, `group` và `member` thuộc schema riêng của AD. Trong OpenLDAP, một mô hình tương đương thường sử dụng `groupOfNames`:

~~~ldif
dn: cn=engineering,ou=groups,dc=example,dc=org
objectClass: top
objectClass: groupOfNames
cn: engineering
member: uid=lan,ou=people,dc=example,dc=org
member: uid=minh,ou=people,dc=example,dc=org
~~~

Không thể chỉ đổi tên kết nối mà giữ nguyên giả định `objectClass=groupOfNames` trên mọi Active Directory: schema, DN, thuộc tính thành viên và các cơ chế trả kết quả phụ thuộc loại máy chủ.

### Hai truy vấn nhìn giống nhau nhưng khác đối tượng bị giới hạn

| Truy vấn | Có bao nhiêu entry? | Có bao nhiêu giá trị? | Cơ chế cần xét |
| --- | ---: | ---: | --- |
| Tìm tất cả nhóm trong `OU=Groups` | Có thể 2.000 entry | Mỗi entry có thuộc tính riêng | **Paged Results Control** khi vượt giới hạn entry. |
| Đọc `member` của `CN=Engineering-All` | **1 entry** | Có thể 3.200 DN | **Range retrieval** nếu AD cắt số giá trị. |
| Tìm nhóm nào chứa Lan | Có thể vài entry | Không cần đọc mọi `member` | Search filter `(member=DN_Lan)`. |
| Đọc 2.000 nhóm và toàn bộ thành viên | 2.000 entry | Nhiều nghìn giá trị trên từng entry | Có thể cần **cả paging và range**. |

**Một `SearchResultEntry` không tương đương một thành viên nhóm.** `member` là một attribute có thể chứa nhiều giá trị DN trong **cùng entry nhóm**.

## 3. Ba tầng giới hạn kích thước

~~~mermaid
flowchart TB
    A["Yêu cầu đọc dữ liệu LDAP"] --> B["Giới hạn số ENTRY trả về của Search"]
    A --> C["Giới hạn số VALUE trong một ATTRIBUTE"]
    A --> D["Giới hạn tài nguyên / timeout client và server"]
    B --> E["sizeLimit, MaxPageSize,<br/>Simple Paged Results"]
    C --> F["AD MaxValRange,<br/>member;range=low-high/*"]
    D --> G["timeLimit, read timeout,<br/>memory, connection, API deadline"]
    E --> H["Kết quả đủ hay chưa đủ?"]
    F --> H
    G --> H
~~~

| Tầng | Tham số/máy chủ | Tác động khi vượt |
| --- | --- | --- |
| **Số entry** | LDAP `SearchRequest.sizeLimit`, AD `MaxPageSize`, OpenLDAP `sizelimit` | Search có thể trả ít entry hơn tập phù hợp, có thể có `sizeLimitExceeded (4)`. |
| **Số giá trị/attribute** | AD `MaxValRange` | Một entry vẫn được trả, nhưng `member` chỉ là **một range** giá trị. |
| **Thời gian/tài nguyên** | `timeLimit`, `MaxQueryDuration`, timeout mạng, giới hạn byte/CPU | Search có thể lỗi, chỉ hoàn tất một phần hoặc chậm hơn SLA API. |

Không giải quyết mọi vấn đề bằng cách tăng giới hạn server. Giới hạn là công cụ bảo vệ directory và những ứng dụng khác cùng sử dụng.

## 4. LDAP Search sizeLimit: giới hạn số entry

Theo RFC 4511, `SearchRequest.sizeLimit` là số **entry** tối đa client yêu cầu directory trả về.

- `sizeLimit=0`: không đặt giới hạn **do client yêu cầu**.
- `sizeLimit=100`: client yêu cầu tối đa 100 entry.
- Server vẫn có thể áp chính sách thấp hơn.
- Khi vượt, server có thể trả một số entry rồi trả `sizeLimitExceeded (4)`.
- `sizeLimitExceeded` khác `adminLimitExceeded (11)`; thông điệp chẩn đoán phụ thuộc server.

Trong Spring LDAP:

~~~java
LdapQuery query = LdapQueryBuilder.query()
        .base("ou=groups")
        .searchScope(SearchScope.ONELEVEL)
        .countLimit(100)
        .timeLimit(2_000) // mili giây ở Spring LDAP/JNDI
        .where("objectClass").is("groupOfNames");
~~~

Đoạn trên áp cho **ví dụ nhóm OpenLDAP**, chưa phải filter AD. `countLimit(100)` yêu cầu tối đa 100 **entry nhóm**, không phải tối đa 100 giá trị `member` trên mỗi nhóm.

**Đơn vị thời gian dễ nhầm:** `LdapQueryBuilder.timeLimit(2_000)` dùng **mili giây**; trường `timeLimit` của LDAP SearchRequest ở giao thức dùng **giây**. Ngoài ra cần connect/read timeout riêng.

### 4.1. Chính sách của từng directory

- **AD DS** có LDAP policy `MaxPageSize`, thường mặc định **1.000 entry** cho Search không phân trang; giá trị thực tế có thể được quản trị viên thay đổi theo DC/policy.
- **OpenLDAP** có thể cấu hình `sizelimit` và các hạn chế theo người dùng, filter hoặc backend; không mặc định dùng tên `MaxPageSize` của AD.
- Directory khác có thể áp giới hạn/tính năng khác, ngay cả khi đều hỗ trợ LDAPv3.

Không hardcode “LDAP luôn trả tối đa 1.000 entry”. Đây là **chính sách phổ biến ở một loại server**, không phải giới hạn chung của giao thức.

### 4.2. Search trả đúng N entry không chứng minh toàn bộ dữ liệu đã được lấy

Giả sử có 2.000 nhóm nhưng client đặt `countLimit=100`. Nhận 100 nhóm **không được suy luận** còn đúng 1.900 nhóm, rằng đây là “100 nhóm đầu” theo thứ tự ổn định, hoặc rằng kết quả đã đầy đủ.

Ứng dụng cần mô hình trạng thái như `complete`/`mayBeTruncated` và thiết kế paging nếu nghiệp vụ thực sự cần tất cả nhóm.

## 5. Simple Paged Results Control xử lý nhiều entry

RFC 2696 định nghĩa control **Simple Paged Results**. Client xin một `pageSize`, server trả các **entry** và một **cookie**; client gửi lại cookie để tiếp tục cho đến khi cookie rỗng.

~~~mermaid
sequenceDiagram
    participant C as Java/Spring LDAP
    participant D as LDAP server
    C->>D: Search + paged control(size=200, cookie rỗng)
    D-->>C: 200 SearchResultEntry + cookie A
    C->>D: Search + paged control(size=200, cookie A)
    D-->>C: 200 SearchResultEntry + cookie B
    C->>D: ... các trang tiếp theo ...
    D-->>C: Trang cuối + cookie rỗng
~~~

Cookie là **opaque**: không tự phân tích hoặc tăng một số offset như SQL. Server cũng không bảo đảm kết quả là snapshot bất biến khi các entry thay đổi giữa các trang. `pageSize` khác `SearchRequest.sizeLimit` và phải được kiểm thử cùng giới hạn server.

### Paged search trong Spring LDAP

Spring LDAP có `DirContextProcessor` hỗ trợ paged results. Tài liệu Spring LDAP mới sử dụng `PagedResultsControlExchangeDirContextProcessor`; ở một số nhánh cũ là `PagedResultsDirContextProcessor`. Hãy đối chiếu class chính xác với **phiên bản thư viện đang chạy**, vì API có thể thay đổi hoặc bị deprecated.

Ví dụ minh họa cho **Spring LDAP 4.1+**, nơi có `PagedResultsControlExchangeDirContextProcessor`:

~~~java
import java.util.ArrayList;
import java.util.List;

import javax.naming.directory.SearchControls;

import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.ContextSource;
import org.springframework.ldap.core.support.SingleContextSource;
import org.springframework.ldap.control.PagedResultsControlExchangeDirContextProcessor;

// Sử dụng page control để đọc ENTRY nhóm, không đọc từng value member.
public List<String> allGroupNames(ContextSource source) {

    return SingleContextSource.doWithSingleContext(
        source,
        operations -> {
            List<String> all = new ArrayList<>();

            SearchControls controls = new SearchControls();
            controls.setSearchScope(SearchControls.ONELEVEL_SCOPE);
            controls.setReturningAttributes(new String[]{"cn"});

            var page = new PagedResultsControlExchangeDirContextProcessor(
                    200);

            do {
                all.addAll(operations.search(
                    "ou=groups",
                    "(objectClass=groupOfNames)",
                    controls,
                    (AttributesMapper<String>)
                            attrs -> attrs.get("cn").get().toString(),
                    page));
            } while (page.hasMore());

            return List.copyOf(all);
        },
        true,  // useReadOnly context
        false, // không bỏ qua PartialResultException
        false  // không bỏ qua NameNotFoundException
    );
}
~~~

Ví dụ dùng `objectClass=groupOfNames` cho directory có schema đó; với **AD** nên thay bằng filter/nhánh nhóm phù hợp, chẳng hạn `(objectClass=group)`. Mỗi page cần timeout, trần tổng số entry và exception policy trong ứng dụng thật.

**Yêu cầu quan trọng:** paging thường cần **giữ cùng kết nối LDAP** xuyên các lời gọi có cookie; `SingleContextSource` được Spring LDAP cung cấp để giải quyết đúng nhu cầu này.

`PagedResultsControlExchangeDirContextProcessor`/`PagedResultsDirContextProcessor` không tự giải quyết thuộc tính `member` bị cắt trong **một entry nhóm**. Đây là điểm chuyển sang nội dung tiếp theo.

## 6. Giới hạn nhiều giá trị trong Active Directory: MaxValRange

Trong AD DS, một attribute đa trị như `member` có thể chứa rất nhiều DN. AD có LDAP policy `MaxValRange` quy định tối đa bao nhiêu **giá trị** được trả trong một request.

Tài liệu Microsoft mô tả giá trị cấu hình phổ biến **1.500 giá trị** đối với các phiên bản AD hiện đại; một số máy chủ cũ sử dụng **1.000**, và cấu hình thực tế có thể khác. Vì vậy:

- Không giả định luôn có đúng 1.500 giá trị mỗi lần đọc.
- Không lấy `member.size()==1500` làm dấu hiệu kết thúc.
- Không dùng `countLimit(5000)` để “lấy hết 5.000 member”.
- Dùng **cơ chế range retrieval** và đọc **tên attribute mà server thực sự trả về**.

### 6.1. Range retrieval là gì?

AD hỗ trợ cú pháp mở rộng trên **tên thuộc tính được yêu cầu**:

~~~text
member;range=low-high
~~~

Trong đó:

- `low` là chỉ số bắt đầu, **tính từ 0**.
- `high` là chỉ số kết thúc **bao gồm cả chỉ số đó**.
- Có thể dùng `*` ở `high` để yêu cầu **toàn bộ phần còn lại trong phạm vi server cho phép**.
- Server có thể trả ít giá trị hơn yêu cầu.
- Tên attribute **trả về** cũng chứa `range=...` để báo chính xác đoạn đã gửi.
- Khi đã trả phần cuối của attribute, server dùng `*` ở **high** để đánh dấu **không còn giá trị tiếp theo**.

Đây là **khả năng mở rộng của Active Directory**, không phải cú pháp phân trang attribute được LDAPv3/RFC 2696 yêu cầu mọi directory hỗ trợ.

### 6.2. Vì sao JNDI get("member") có thể không trả dữ liệu?

Nếu client yêu cầu attribute `member` không kèm `range` và nhóm có quá nhiều giá trị, Microsoft mô tả server có thể trả:

1. Một attribute tên `member` nhưng **không có giá trị**.
2. Một attribute khác tên dạng `member;range=0-1499` chứa các giá trị đầu tiên.

Một số thư viện/map có thể không hiển thị attribute không có giá trị. Nếu Java chỉ viết:

~~~java
Attribute member = attributes.get("member");
~~~

thì có thể nhận `null`/một tập rỗng, mặc dù nhóm thực tế có hàng nghìn thành viên. Nếu Spring LDAP mapper chỉ lấy `@Attribute(name="member")`, phần `member;range=...` **không nhất thiết được tự gộp** vào trường `members`.

**Kết luận quan trọng:** thiếu `attributes.get("member")` không chứng minh nhóm rỗng. Cần xem **toàn bộ attribute IDs** và khả năng range retrieval của server.

## 7. Minh họa đọc một nhóm 3.200 thành viên

Giả sử AD group `CN=Engineering-All,...` có đúng **3.200** DN trong `member`. Client chủ động yêu cầu mỗi lần 1.000 giá trị:

~~~text
REQUEST 1:
  member;range=0-999
RESPONSE 1:
  member;range=0-999        (1.000 DN)

REQUEST 2:
  member;range=1000-1999
RESPONSE 2:
  member;range=1000-1999    (1.000 DN)

REQUEST 3:
  member;range=2000-2999
RESPONSE 3:
  member;range=2000-2999    (1.000 DN)

REQUEST 4:
  member;range=3000-3999
RESPONSE 4:
  member;range=3000-*       (200 DN, kết thúc)
~~~

Đây là ví dụ khi server chấp nhận kích thước trang 1.000 và dữ liệu nhóm không thay đổi. Một AD DC có limit thấp hơn có thể trả **range ngắn hơn yêu cầu**, ví dụ client xin `0-999` nhưng server trả `0-499`. Khi đó **lần tiếp phải bắt đầu từ 500**, không phải từ 1000.

~~~mermaid
sequenceDiagram
    participant App as Spring LDAP/JNDI
    participant AD as Active Directory
    App->>AD: getAttributes(group, member;range=0-999)
    AD-->>App: member;range=0-499
    Note over App: Bước tiếp theo = high thực tế + 1
    App->>AD: getAttributes(group, member;range=500-1499)
    AD-->>App: member;range=500-999
    App->>AD: getAttributes(group, member;range=1000-1999)
    AD-->>App: member;range=1000-*
    Note over App: Dấu * báo đã đọc range cuối
~~~

Trong sơ đồ thứ hai, số lượng và điểm kết thúc chỉ là minh họa cho một nhóm có số thành viên thích hợp.

### Quy tắc không được bỏ qua

1. Đọc tên attribute **response**, không suy ra từ tên **request**.
2. Chỉ số `high` của response là **inclusive**: `nextLow=high+1`.
3. `*` ở response là **dấu hoàn tất**, không phải ký tự wildcard của filter.
4. Đọc mọi range trên **cùng kết nối tới cùng DC** khi có thể.
5. Không coi thứ tự các giá trị là thứ tự ổn định lâu dài; AD không cam kết sắp xếp member.
6. Nếu nhóm bị sửa giữa hai lượt, có thể bị lặp hoặc thiếu DN; không xem range retrieval là snapshot giao dịch.
7. Khi response không có range mong đợi, không trả danh sách đã có với nhãn `complete=true`.

## 8. Vì sao hai cơ chế paging và range không thể thay thế nhau?

| Tiêu chí | Simple Paged Results | AD range retrieval |
| --- | --- | --- |
| Đối tượng bị chia | **Các SearchResultEntry** của Search. | **Các giá trị** trong một attribute của một entry. |
| Cách gọi | LDAP control RFC 2696. | Attribute description `member;range=...`. |
| Tiến trình | Cookie opaque từ server. | `low`/`high` trong tên attribute response. |
| Kết thúc | Cookie rỗng. | `member;range=low-*`. |
| Phạm vi hỗ trợ | Directory có hỗ trợ RFC 2696. | Cơ chế Microsoft AD, không được giả định ở OpenLDAP. |
| Vấn đề giải quyết | Search có nhiều entry nhóm/người dùng. | Một nhóm có quá nhiều giá trị `member`. |
| Rủi ro | Bỏ trang, cookie hết hạn, dữ liệu đổi giữa trang. | Bỏ range, dùng sai offset, nhóm đổi trong lúc đọc. |

**Ví dụ:** Search tất cả nhóm có 2.000 entry, trong đó một nhóm có 3.200 thành viên. Client có thể cần **paging** để lấy 2.000 nhóm, sau đó dùng **range retrieval** để lấy đủ 3.200 `member` của nhóm lớn.

Nếu nghiệp vụ chỉ kiểm tra “Lan có thuộc Engineering-All không?”, tải toàn bộ 3.200 DN có thể **không cần thiết**; xem mục 14.

## 9. Đọc mọi attribute ID từ JNDI để phát hiện range

Trong JNDI, một entry được biểu diễn bởi `javax.naming.directory.Attributes`, bên trong có `Attribute`. Thay vì chỉ gọi `get("member")`, hãy liệt kê attribute ID mà server đã trả.

~~~java
import javax.naming.NamingEnumeration;
import javax.naming.NamingException;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;
import javax.naming.directory.DirContext;

public void inspectMemberAttributes(
        DirContext ctx, String groupRelativeDn)
        throws NamingException {

    Attributes attrs = ctx.getAttributes(
            groupRelativeDn,
            new String[]{"member"}
    );

    NamingEnumeration<? extends Attribute> all = attrs.getAll();
    try {
        while (all.hasMore()) {
            Attribute attr = all.next();
            String id = attr.getID();
            int count = attr.size();
            // In test: id có thể là "member" hoặc
            // "member;range=0-1499".
            // Không đưa DN member thật ra log production.
        }
    } finally {
        all.close();
    }
}
~~~

`Attribute.getID()` trả về tên thực của attribute. Để lấy các giá trị của một `Attribute`:

~~~java
NamingEnumeration<?> values = memberAttr.getAll();
try {
    while (values.hasMore()) {
        Object value = values.next();
        // Với member AD/groupOfNames, thường là String DN.
    }
} finally {
    values.close();
}
~~~

Không đoán attribute ID bằng `attributes.get("member;range=0-1499")` nếu chưa biết server thực tế trả tên gì. Có thể server trả `member;range=0-499` hoặc `member;range=0-*`.

### Không phụ thuộc vào thứ tự attribute

`Attributes` không bảo đảm thứ tự liệt kê. Khi đọc range:

- Tìm ID khớp dạng `member;range=low-high` hoặc `member;range=low-*`.
- Parse chỉ số theo regex **giới hạn đúng attribute cần đọc**.
- Xác minh `low` chính xác bằng vị trí client đang yêu cầu.
- Xác minh `high` hợp lệ, không âm và không đi lùi.
- Nếu thiếu hoặc nhiều attribute ranged mâu thuẫn, dừng và đánh dấu lỗi.
- Đóng cả `NamingEnumeration` của attributes và values.

## 10. Ví dụ đầy đủ: đọc mọi member của một nhóm lớn trên AD

Đoạn dưới là một service **dành cho AD DS** qua Spring LDAP `ContextSource` và JNDI. Nó dùng tên DN **tương đối với `ContextSource.base`**, một context xuyên các range, không lấy credential từ HTTP client và **chỉ trả về danh sách nếu nhận được range cuối**.

Đây là ví dụ thực thi theo API Java/JNDI phổ biến; tên package/bean cần điều chỉnh theo dự án.

`service/ActiveDirectoryGroupMemberReader.java`:

~~~java
package com.example.directory.service;

import java.time.Duration;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import javax.naming.NamingEnumeration;
import javax.naming.NamingException;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;
import javax.naming.directory.DirContext;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.ldap.core.ContextSource;
import org.springframework.ldap.support.LdapUtils;
import org.springframework.stereotype.Service;

@Service
public final class ActiveDirectoryGroupMemberReader {

    // 1000 là mức tương thích thận trọng, KHÔNG khẳng định
    // server luôn trả đúng 1000 giá trị trong một response.
    private static final int REQUEST_VALUES = 1_000;
    private static final int MAX_REQUESTS = 60;
    private static final int MAX_MEMBERS = 50_000;
    private static final long MAX_NANOS =
            Duration.ofSeconds(15).toNanos();

    private static final Pattern RANGE = Pattern.compile(
            "^member;range=(\\d+)-(\\d+|\\*)$",
            Pattern.CASE_INSENSITIVE);

    private final ContextSource source;

    public ActiveDirectoryGroupMemberReader(
            @Qualifier("directoryContextSource") ContextSource source) {
        this.source = source;
    }

    public List<String> readAll(
            String approvedRelativeGroupDn) {
        if (approvedRelativeGroupDn == null
                || approvedRelativeGroupDn.isBlank()) {
            throw new IllegalArgumentException("Group DN required");
        }

        // Caller nội bộ phải cung cấp DN được xây từ group ID
        // đã được authorization và validate, không nhận DN tùy ý
        // từ HTTP client.
        DirContext ctx = null;
        try {
            ctx = source.getReadOnlyContext();
            return readOnOneContext(ctx, approvedRelativeGroupDn);
        } catch (NamingException ex) {
            throw new IllegalStateException(
                    "LDAP group member retrieval failed", ex);
        } finally {
            LdapUtils.closeContext(ctx);
        }
    }

    private static List<String> readOnOneContext(
            DirContext ctx, String relativeDn)
            throws NamingException {

        List<String> members = new ArrayList<>();
        Set<String> seen = new HashSet<>();
        long started = System.nanoTime();
        int next = 0;

        for (int attempt = 0; attempt < MAX_REQUESTS; attempt++) {
            if (System.nanoTime() - started > MAX_NANOS) {
                throw new IllegalStateException(
                        "Group member read deadline exceeded");
            }
            if (next >= MAX_MEMBERS) {
                throw new IllegalStateException(
                        "Group member read exceeded maximum size");
            }

            int requestedHigh = next + REQUEST_VALUES - 1;
            String requested = "member;range="
                    + next + "-" + requestedHigh;

            Attributes attrs = ctx.getAttributes(
                    relativeDn, new String[] { requested });

            Attribute ranged = null;
            Matcher matched = null;

            NamingEnumeration<? extends Attribute> all =
                    attrs.getAll();
            try {
                while (all.hasMore()) {
                    Attribute candidate = all.next();
                    Matcher m = RANGE.matcher(candidate.getID());

                    if (m.matches()) {
                        if (ranged != null) {
                            throw new IllegalStateException(
                                    "Multiple conflicting member ranges");
                        }
                        ranged = candidate;
                        matched = m;
                    }
                }
            } finally {
                all.close();
            }

            // Thiếu range có thể là server không hỗ trợ
            // hoặc ACL giấu thuộc tính, KHÔNG tự coi nhóm rỗng.
            if (ranged == null || matched == null) {
                throw new IllegalStateException(
                        "Expected ranged member attribute was absent");
            }

            int low = Integer.parseInt(matched.group(1));
            if (low != next) {
                throw new IllegalStateException(
                        "Unexpected range start: " + low);
            }

            String highText = matched.group(2);
            boolean last = "*".equals(highText);

            int upper = -1;
            if (!last) {
                upper = Integer.parseInt(highText);
                if (upper < low || upper > requestedHigh) {
                    throw new IllegalStateException(
                            "Invalid or unexpected range end");
                }
            }

            int countThisRange = 0;
            NamingEnumeration<?> values = ranged.getAll();
            try {
                while (values.hasMore()) {
                    Object value = values.next();
                    if (!(value instanceof String dn)
                            || dn.isBlank()) {
                        throw new IllegalStateException(
                                "Invalid member DN value");
                    }
                    if (!seen.add(dn)) {
                        throw new IllegalStateException(
                                "Duplicate member during range retrieval");
                    }
                    members.add(dn);
                    countThisRange++;

                    if (members.size() > MAX_MEMBERS) {
                        throw new IllegalStateException(
                                "Too many group members");
                    }
                }
            } finally {
                values.close();
            }

            if (last) {
                // Chỉ công bố COMPLETE khi server báo khoảng cuối.
                return List.copyOf(members);
            }

            if (countThisRange != upper - low + 1) {
                throw new IllegalStateException(
                        "Range metadata and values disagree");
            }

            // Dựa vào HIGH THỰC TẾ của server, không dựa
            // vào số lượng mà client đã xin.
            next = upper + 1;
        }

        throw new IllegalStateException(
                "Group member read exceeded request limit");
    }
}
~~~

### Cách đọc logic trong service

1. Lấy **một `DirContext`** bằng reader service account.
2. Bắt đầu `low=0`, xin tối đa 1.000 giá trị.
3. Liệt kê tên các attribute trả về, tìm `member;range=...`.
4. Parse `low`, `high` hoặc `*` từ **response**.
5. Xác minh khoảng bắt đầu khớp yêu cầu và response không bất thường.
6. Đọc từng DN từ `Attribute.getAll()`, chặn dữ liệu null/không hợp lệ.
7. Nếu `high=*`, trả về bản sao bất biến và coi quá trình đọc range hoàn tất.
8. Nếu chưa phải cuối, đặt `next=high+1`.
9. Nếu lỗi ACL, timeout, range không hợp lệ, giới hạn số lượt hoặc thiếu attribute, **ném lỗi** chứ không trả danh sách thiếu.
10. Dù thành công, đóng context trong `finally`.

### Các giới hạn quan trọng của ví dụ

- Chỉ hỗ trợ **AD range retrieval**, không dùng làm hàm chung cho mọi directory.
- `approvedRelativeGroupDn` phải được xây và phê duyệt bởi tầng service; truyền trực tiếp giá trị tùy ý từ HTTP là nguy hiểm.
- Việc giữ một kết nối qua các lượt giúp đáp ứng khuyến nghị Microsoft rằng thứ tự giá trị ổn định **trên cùng connection nếu attribute không thay đổi**. Đây **không** phải bảo đảm snapshot khi concurrent writes.
- Giới hạn tổng `50.000`, `60` lượt và `15 giây` là **policy minh họa**; chọn theo quy mô thực tế. Deadline kiểm tra trước lượt mới, không hủy một thao tác JNDI bị treo giữa lượt: vẫn cần connect/read timeout.
- Dùng `HashSet` để phát hiện DN trùng theo chuỗi. DN có thể tương đương về ngữ nghĩa dù khác chữ hoa/escaping; nếu ứng dụng cần đối soát định danh tuyệt đối, chuẩn hóa bằng parser DN/case rules thích hợp.
- Khi nhóm thực sự không có `member`, code **cố ý báo trạng thái không xác định** thay vì coi null là rỗng, vì một ACL cũng có thể che attribute. Xử lý nhóm rỗng cần quy trình xác minh ACL và schema riêng.
- Nếu server trả range không như hợp đồng AD, cần điều tra server/provider; không tự điều chỉnh offset theo `members.size()` mà bỏ qua thông tin tên attribute.

## 11. Bean Spring LDAP riêng cho truy vấn nhóm

Trong môi trường AD, có thể cấu hình Spring Boot dùng tài khoản dịch vụ đọc nhóm với quyền tối thiểu.

`application.yml`:

~~~yaml
directory:
  url: ldaps://ad.example.org:636
  base: DC=example,DC=org
  reader:
    bind-dn: CN=svc-group-reader,OU=Service,DC=example,DC=org
    password: "${LDAP_GROUP_READER_PASSWORD}"
~~~

Đây là namespace tự định nghĩa, được đọc qua `@Value` trong JavaConfig.

`config/DirectoryContextConfig.java`:

~~~java
package com.example.directory.config;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.core.support.LdapContextSource;

@Configuration
public class DirectoryContextConfig {

    @Bean("directoryContextSource")
    public LdapContextSource directoryContextSource(
            @Value("${directory.url}") String url,
            @Value("${directory.base}") String base,
            @Value("${directory.reader.bind-dn}") String principal,
            @Value("${directory.reader.password}") String password) {

        LdapContextSource source = new LdapContextSource();
        source.setUrl(url);
        source.setBase(base);
        source.setUserDn(principal);
        source.setPassword(password);
        source.setReferral("throw");
        return source;
    }

    @Bean("groupReadTemplate")
    public LdapTemplate groupReadTemplate(
            LdapContextSource directoryContextSource) {
        LdapTemplate template = new LdapTemplate(
                directoryContextSource);
        template.setIgnoreSizeLimitExceededException(false);
        template.setIgnorePartialResultException(false);
        return template;
    }
}
~~~

Trong ví dụ:

- `ContextSource.base=DC=example,DC=org`.
- DN nhóm đầy đủ là `CN=Engineering-All,OU=Groups,DC=example,DC=org`.
- DN **tương đối** truyền vào `ctx.getAttributes(...)` là `CN=Engineering-All,OU=Groups`.
- `setReferral("throw")` tránh tự follow một đích chưa phê duyệt và chuyển credential.
- `setIgnoreSizeLimitExceededException(false)` quan trọng cho Search nhiều **entry**, nhưng **không tự sửa dữ liệu `member` bị range-limit**.
- Cần cấu hình timeout JNDI và truststore/TLS, không chỉ đặt timeout của từng Search.

### Không dùng admin/root để khắc phục lỗi

Nếu một reader không thấy `member` do ACL:

- Không đổi ngay sang tài khoản directory administrator.
- Kiểm tra permission đọc `member` và `cn` trên nhánh được phê duyệt.
- Đối chiếu cùng Bind DN bằng `ldapsearch`.
- Đánh giá privacy vì danh sách thành viên nhóm có thể tiết lộ tổ chức và quyền truy cập.
- Giữ credential trong secret manager; không in vào log.

## 12. Đọc thuộc tính đa trị ở OpenLDAP

Trong OpenLDAP với `groupOfNames`, dữ liệu nhóm thường được trả trực tiếp dưới attribute `member` khi tài khoản có quyền đọc và server không áp thêm hạn chế riêng.

~~~java
import java.util.ArrayList;
import java.util.List;

import javax.naming.NamingEnumeration;
import javax.naming.NamingException;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;
import javax.naming.directory.DirContext;

public List<String> readStandardMembers(
        DirContext ctx, String groupRelativeDn)
        throws NamingException {

    Attributes attrs = ctx.getAttributes(
            groupRelativeDn, new String[] { "member" });

    Attribute member = attrs.get("member");
    if (member == null) {
        // Phân biệt: không có member, ACL không cho đọc,
        // projection sai, hoặc directory không đúng schema.
        throw new IllegalStateException(
                "member attribute was not readable");
    }

    List<String> result = new ArrayList<>();
    NamingEnumeration<?> values = member.getAll();
    try {
        while (values.hasMore()) {
            Object value = values.next();
            if (!(value instanceof String dn)) {
                throw new IllegalStateException(
                        "Unsupported member value type");
            }
            result.add(dn);
        }
    } finally {
        values.close();
    }
    return List.copyOf(result);
}
~~~

**Không tự đưa `member;range=...` vào OpenLDAP** khi chưa có chứng cứ server hỗ trợ extension đó. Nếu server không nhận option range, một phản hồi thiếu attribute **không phải bằng chứng nhóm rỗng**.

### Khác biệt schema và semantics

| Directory / model | Object class phổ biến | Thuộc tính thành viên | Lưu ý |
| --- | --- | --- | --- |
| OpenLDAP nhóm tên DN | `groupOfNames` | `member` | Giá trị DN, schema thường yêu cầu ít nhất một member. |
| LDAP nhóm `groupOfUniqueNames` | `groupOfUniqueNames` | `uniqueMember` | Kiểu giá trị và quy tắc có thể khác. |
| POSIX LDAP | `posixGroup` | `memberUid` | Thường chứa UID, **không phải DN**. |
| Active Directory | `group` | `member` | Giá trị DN; nhóm lớn có thể cần `range`. |
| Active Directory reverse membership | Thuộc tính liên quan `memberOf` trên user | `memberOf` | Không mặc định đồng nghĩa toàn bộ quyền, nested groups hoặc primary group. |

**Không thay tên `member` bằng `memberUid` trong một filter rồi mong semantics giống nhau.** DN và UID là hai loại định danh khác nhau.

## 13. Spring Data LDAP ODM có thể âm thầm ánh xạ thiếu member

Ví dụ entity mô tả một nhóm LDAP:

~~~java
import java.util.Set;
import javax.naming.Name;

import org.springframework.ldap.odm.annotations.Attribute;
import org.springframework.ldap.odm.annotations.Entry;
import org.springframework.ldap.odm.annotations.Id;

@Entry(
    base = "ou=groups",
    objectClasses = {"top", "groupOfNames"}
)
public class DirectoryGroup {

    @Id
    private Name dn;

    @Attribute(name = "cn")
    private String name;

    @Attribute(name = "member")
    private Set<Name> members;

    // Constructor/getter/setter trong project thực tế.
}
~~~

Repository:

~~~java
import org.springframework.data.ldap.repository.LdapRepository;

public interface DirectoryGroupRepository
        extends LdapRepository<DirectoryGroup> {
}
~~~

Entity này phù hợp với **schema `groupOfNames` thông thường**, nhưng không phải bảo đảm có thể lấy đủ mọi `member` trên tất cả server.

### Vì sao phải thận trọng ở AD?

Một số luồng ODM/repository yêu cầu hoặc map attribute tên **`member`**. AD có thể trả thực tế `member;range=0-1499`. Tùy phiên bản mapper/provider, trường `members` có thể chỉ chứa một phần, rỗng hoặc không được map như dự kiến.

Do đó:

- Không lấy `repository.findById(groupDn).get().getMembers().size()` làm số thành viên đúng tuyệt đối của nhóm AD lớn.
- Không dùng entity map thiếu để ghi đè toàn bộ danh sách `member`.
- Không gọi `repository.save(group)` sau khi tải group lớn mà chưa xác minh dữ liệu đầy đủ, vì update có thể làm mất giá trị hoặc gây lỗi schema/concurrency.
- Nếu cần duyệt đầy đủ, tạo **reader chuyên biệt cho AD range** hoặc một adapter tương thích được kiểm thử.
- Nếu chỉ cần kiểm tra membership của một user, tránh tải toàn danh sách như mục kế tiếp.

### DTO không nên lộ toàn danh sách

Một endpoint `GET /groups/{id}` cho giao diện quản trị có thể chỉ trả:

~~~json
{
  "name": "Engineering-All",
  "memberCountComplete": false,
  "membersLoaded": 1000,
  "warning": "MEMBERSHIP_NOT_FULLY_LOADED"
}
~~~

Đây là **hợp đồng HTTP ví dụ**, không phải LDAP response chuẩn. Nếu nghiệp vụ cần tổng số chính xác, phải có quy trình lấy đầy đủ và kiểm tra quyền, không tự suy ra từ một range.

## 14. Kiểm tra một người có thuộc nhóm: không phải lúc nào cũng cần range

Nếu mục tiêu chỉ là “Lan có thuộc nhóm Engineering-All không?”, tải 3.200 hoặc 30.000 DN là tốn kém và có thể làm lộ dữ liệu thành viên khác.

Thay vì duyệt mọi `member`, có thể yêu cầu LDAP server **Search tại chính entry nhóm** với filter so sánh `member` bằng **DN đầy đủ của Lan**.

### Ví dụ dùng LdapTemplate

~~~java
import java.util.List;
import javax.naming.Name;

import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;
import org.springframework.ldap.query.SearchScope;
import org.springframework.ldap.support.LdapNameBuilder;

public boolean isDirectMember(
        LdapTemplate template,
        String validatedGroupName,
        String validatedUid) {

    Name groupRelativeDn = LdapNameBuilder
            .newInstance("OU=Groups")
            .add("CN", validatedGroupName)
            .build();

    Name fullUserDn = LdapNameBuilder
            .newInstance("DC=example,DC=org")
            .add("OU", "People")
            .add("CN", validatedUid)
            .build();

    LdapQuery query = LdapQueryBuilder.query()
            .base(groupRelativeDn.toString())
            .searchScope(SearchScope.OBJECT)
            .countLimit(1)
            .timeLimit(2_000)
            .attributes("cn")
            .where("objectClass").is("group")
            .and("member").is(fullUserDn.toString());

    List<String> found = template.search(
            query,
            (AttributesMapper<String>) attrs ->
                attrs.get("cn").get().toString());

    return !found.isEmpty();
}
~~~

**Điều kiện quan trọng:** ví dụ áp cho **AD** và giả định DN của người dùng thực tế có RDN `CN=<validatedUid>` dưới `OU=People`. Trong AD, tên đăng nhập `sAMAccountName` **không nhất thiết trùng giá trị CN/RDN**. Vì vậy, trong ứng dụng thật, `fullUserDn` phải được lấy qua một bước **resolve DN đã xác minh** (chẳng hạn Search đúng `sAMAccountName`/`objectGUID` trong base được phê duyệt), không tạo DN bằng cách đoán username.

Đối với OpenLDAP, đổi objectClass/base/kiểu group theo schema đang dùng. LDAP filter trên `member` phải có quyền **search/compare** phù hợp; thiếu quyền có thể tạo kết quả trông như không phải thành viên.

### Ưu điểm

- Chỉ Search **một entry nhóm** bằng scope `OBJECT`.
- Không truyền mọi DN thành viên qua mạng.
- Không cần xử lý range khi server có thể đánh giá trực tiếp filter `(member=userDN)`.
- Giảm nguy cơ lộ danh sách thành viên nhóm lớn.
- Dễ giới hạn request và bảo vệ API bằng ACL.

### Giới hạn

- Chỉ chứng minh **membership trực tiếp** dựa trên attribute/filter được server hỗ trợ.
- Không mặc định tính nested groups, primary group hoặc mọi chính sách role của AD.
- Kết quả rỗng có thể xuất phát từ ACL/filter/base sai, không chỉ “không phải thành viên”.
- Nếu đây là quyết định phân quyền nhạy cảm, phải có một dịch vụ xác thực/ủy quyền đáng tin, không tin boolean trả về từ truy vấn không kiểm soát được tính đầy đủ.

Có thể dùng capability riêng của AD để xét membership lồng nhau (ví dụ matching rule LDAP `1.2.840.113556.1.4.1941`), nhưng đây **không phải tính năng LDAP chung** và cần kiểm chứng trên DC/schema/ACL thực tế.

## 15. Một điểm dễ sai: get("member") và get("member;range=0-1499")

Giả sử Java nhận:

~~~text
Attributes:
  cn: Engineering-All
  member: <không có giá trị>
  member;range=0-1499: 1.500 giá trị
~~~

Khi đó:

~~~java
attrs.get("member");             // có thể null hoặc rỗng
attrs.get("member;range=0-1499"); // chỉ đúng nếu ID đúng y hệt response
~~~

Nhưng server có thể trả:

~~~text
member;range=0-999
member;range=1000-*
~~~

Tốt hơn nên liệt kê `attrs.getAll()` và parse ID theo quy tắc **case-insensitive**. Không coi `member;range` là một attribute schema hoàn toàn mới cần mapping vào `@Attribute(name="member;range=0-1499")` cố định: offset thay đổi, tên attribute cũng thay đổi.

### Vì sao dùng `next = returnedHigh + 1`?

Client xin `member;range=0-1499` nhưng server có thể trả `member;range=0-999` vì policy thấp hơn. Nếu client tăng offset **1500**, các giá trị 1000–1499 sẽ bị bỏ sót. **Luôn đọc `high` của tên attribute response.**

### Vì sao cần nhận ra `*`?

Nếu response là `member;range=1500-*`, đó là dấu **phần cuối**; không phải yêu cầu tiếp `member;range=3000-4499` hay tự lấy `*` làm số.

### Không gắn ý nghĩa vào thứ tự

Microsoft mô tả thứ tự giá trị ở range retrieval có thể tùy ý, chỉ ổn định trên cùng kết nối khi attribute không đổi. Do đó, không được dùng “member thứ 1200” như một ID nghiệp vụ; khi cần lưu trữ/đối soát, dùng DN hoặc stable object ID theo directory.

## 16. Khi nhóm thay đổi trong lúc đọc nhiều range

Giả sử trước lượt 1, nhóm có 3.200 DN. Trong lúc client vừa đọc `0-999`, một quản trị viên xóa 10 thành viên ở đầu danh sách. Các chỉ số của những giá trị tiếp theo có thể thay đổi; dữ liệu ở range sau có thể bỏ sót hoặc trùng dù response từng lượt trông hợp lệ.

**Range retrieval không phải một transaction snapshot.**

Các biện pháp:

1. Giữ cùng kết nối tới cùng DC trong quá trình đọc.
2. Giảm thời gian giữa các lượt; giới hạn số lượt và tổng thời gian.
3. Nếu có yêu cầu kiểm toán/tính nhất quán cao, ghi một dấu phiên bản thay đổi của group trước/sau (theo khả năng server) và làm lại nếu có thay đổi.
4. Nếu nghiệp vụ cho phép, tạm hạn chế thao tác ghi membership trong một cửa sổ xuất/đối soát.
5. Có bước kiểm tra chéo hoặc reconciliation, không chỉ dựa vào một lần đọc.
6. Không dùng toàn bộ danh sách đọc dang dở để đưa ra quyết định **cấp quyền**.
7. Lỗi hoặc thông tin thiếu phải đánh dấu `incomplete`, không trả danh sách đã có như một kết quả chắc chắn đầy đủ.

Ví dụ AD có metadata như `uSNChanged` và `whenChanged` để hỗ trợ phát hiện thay đổi, nhưng việc kiểm tra những giá trị đó **không tự tạo snapshot xuyên nhiều DC**. Quyền đọc operational attributes cũng khác giữa directory, nên phải kiểm thử.

## 17. Bảo mật khi đọc nhóm lớn

Một danh sách group member có thể là thông tin nhạy cảm: lộ cơ cấu nhân sự, tài khoản quản trị, thành viên nhóm đặc quyền hoặc quan hệ tổ chức.

### Tối thiểu phải thực hiện

- **Tách service account reader và writer**; reader không có quyền thêm/xóa `member` hoặc sửa nhóm.
- **Không Bind bằng rootdn/Domain Admin** cho chức năng đọc thông thường.
- Dùng **LDAPS hoặc StartTLS** đã xác minh CA/hostname trước Simple Bind.
- Không log raw `member` DN, mật khẩu, LDAP diagnostic hoặc directory entry toàn phần vào log công khai.
- Dùng DTO với scope nhỏ, không trả toàn bộ group membership cho client không được phép.
- Đặt giới hạn số range, số entry, kích thước dữ liệu, timeouts và quyền endpoint HTTP.
- Không để HTTP client gửi `baseDn`/`groupDn`/`range` tùy ý; xây DN từ ID đã xác minh và OU được phê duyệt.
- Khi nhận LDAP referral, không tự chuyển credential sang server khác ngoài allowlist.
- Nếu Search trả kết quả thiếu do ACL, không fallback sang admin credential.
- Ghi request ID, group ID được phép, số range, elapsed time và trạng thái `COMPLETE/INCOMPLETE/FAILED`.

Một quyền đọc `member` chưa chắc là quyền xem danh sách đó trên API. **HTTP authorization**, **Bind identity** và **LDAP ACL** đều phải được áp dụng.

## 18. Lỗi thường gặp và cách phân loại

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Tìm 1 nhóm nhưng chỉ có 1.500 member | AD `MaxValRange` | Đọc `member;range` qua nhiều lượt; không tăng `countLimit`. |
| Search chỉ có 1.000 entry nhóm | AD `MaxPageSize` hoặc policy Search | Dùng Paged Results Control, kiểm tra cookie. |
| `attrs.get("member")==null` | AD trả tên ranged, ACL ẩn attr, hoặc attribute không tồn tại | Liệt kê attribute IDs; không tự kết luận nhóm rỗng. |
| Xin `0-1499` nhưng nhận `0-999` | Giới hạn thực tế thấp hơn request | Xin tiếp từ **1000**, không từ 1500. |
| Response `member;range=1500-*` | Khoảng cuối | Dừng, không tự request thêm. |
| Không có range response | Server không hỗ trợ/ACL/entry sai/empty attribute | Báo lỗi hoặc xác minh schema/ACL; không trả COMPLETE. |
| Range ID không đúng offset kỳ vọng | Server/provider bất thường hoặc data thay đổi | Fail closed, kiểm tra kết nối và thay đổi đồng thời. |
| Giá trị member bị trùng qua range | Thay đổi đồng thời hoặc mapping không ổn định | Không coi kết quả là snapshot; đối soát/retry có giới hạn. |
| LDAP resultCode `4` | Search bị sizeLimitExceeded | Không dùng kết quả partial như đầy đủ. |
| LDAP resultCode `3` | Search vượt timeLimit | Tối ưu filter/index, giới hạn time và xử lý timeout. |
| LDAP resultCode `11` | Giới hạn quản trị | Kiểm tra server policy, không cố vượt bằng query vô hạn. |
| Không thấy group vì không đúng class | AD `group` khác `groupOfNames` | Dùng objectClass đúng server. |
| `memberOf` không có/thiếu | Directory không cung cấp đầy đủ hoặc tính toán khác | Không suy ra toàn membership; kiểm chứng server. |
| Query membership không trả group dù DN đúng | ACL không cho Search trên member | Kiểm tra Bind identity/ACL và filter, không nâng quyền. |
| Paging lặp trang đầu | Quên cookie hoặc dùng connection khác | Giữ cookie và cùng underlying connection. |
| TLS handshake lỗi | CA/hostname/SAN sai | Không tắt xác minh certificate để retry. |
| Directory offline | DNS/TCP/SSL/network failure | Không bịa `LDAP 49`/`LDAP 4` nếu chưa nhận resultCode. |

### Client exception không phải luôn là LDAP resultCode

JNDI có thể ném `javax.naming.SizeLimitExceededException`, `TimeLimitExceededException` hoặc `CommunicationException`. Spring LDAP thường dịch sang exception unchecked thuộc `org.springframework.ldap.*`.

`LdapTemplate` có tùy chọn `ignoreSizeLimitExceededException`; theo tài liệu API một số nhánh mặc định `true`, khiến ứng dụng có thể nhận danh sách **đã bị cắt** mà không có lỗi nổi lên. Với luồng cần completeness, nên cấu hình strict và kiểm thử.

**Không có cách khẳng định mọi nhóm đã được đọc đủ chỉ từ kích thước `List`.** Cần bằng chứng kết thúc range cuối hoặc cookie cuối, tùy cơ chế.

## 19. Thực hành với LDAP CLI

Có thể kiểm tra hành vi trên directory test bằng `ldapsearch`. Dùng `-W` để nhập password theo prompt; không đưa secret trên command line.

### 19.1. Active Directory: xem tên member ranged

~~~bash
ldapsearch -LLL -x \
  -H ldaps://ad.example.org:636 \
  -D "CN=svc-group-reader,OU=Service,DC=example,DC=org" -W \
  -b "CN=Engineering-All,OU=Groups,DC=example,DC=org" \
  -s base "(objectClass=group)" \
  "member;range=0-999"
~~~

Nếu có nhiều giá trị, quan sát tên attribute được server trả, ví dụ:

~~~text
member;range=0-999: CN=Lan,OU=People,DC=example,DC=org
member;range=0-999: CN=Minh,OU=People,DC=example,DC=org
...
~~~

Nếu đây là khoảng cuối, có thể nhận `member;range=0-*`. Không khẳng định server luôn trả đúng 1.000 giá trị.

### 19.2. Active Directory: lấy range tiếp theo

Nếu response kết thúc ở `member;range=0-999`, chạy:

~~~bash
ldapsearch -LLL -x \
  -H ldaps://ad.example.org:636 \
  -D "CN=svc-group-reader,OU=Service,DC=example,DC=org" -W \
  -b "CN=Engineering-All,OU=Groups,DC=example,DC=org" \
  -s base "(objectClass=group)" \
  "member;range=1000-1999"
~~~

Lưu ý: hai lời gọi CLI minh họa độc lập có thể sử dụng **hai connection khác nhau**; vì thế trong môi trường có concurrent updates, chúng **không** bảo đảm kết quả giống một vòng range có cùng connection trong Java.

### 19.3. AD: nhiều entry cần paged results

~~~bash
ldapsearch -x \
  -H ldaps://ad.example.org:636 \
  -D "CN=svc-group-reader,OU=Service,DC=example,DC=org" -W \
  -b "OU=Groups,DC=example,DC=org" -s one \
  -E pr=200/noprompt \
  "(objectClass=group)" dn cn
~~~

`-E pr=200/noprompt` là cú pháp của **OpenLDAP ldapsearch client** cho paged-results control; server vẫn phải hỗ trợ RFC 2696. Nó giúp chia **entry nhóm** theo trang, không tự range `member` trong từng nhóm.

### 19.4. OpenLDAP: đọc giá trị member thông thường

~~~bash
ldapsearch -LLL -x \
  -H ldaps://ldap.example.org:636 \
  -D "cn=svc-reader,ou=service,dc=example,dc=org" -W \
  -b "cn=engineering,ou=groups,dc=example,dc=org" \
  -s base "(objectClass=groupOfNames)" member
~~~

Đừng dùng filter `(objectClass=group)` cho nhóm OpenLDAP kiểu `groupOfNames` nếu server không có class tương ứng.

## 20. Ma trận kiểm thử trên từng directory

Để bài kiểm thử có ý nghĩa, chuẩn bị **hai loại server test** hoặc mô hình fixture tương ứng và ghi nhận rõ khả năng của từng server. Không yêu cầu OpenLDAP trả `member;range` chỉ để giống AD.

| Ca kiểm thử | AD DS | OpenLDAP | Điều phải kiểm chứng |
| --- | --- | --- | --- |
| Nhóm ít thành viên | Đọc bình thường hoặc terminal range | `member` bình thường | Không làm mất member. |
| Nhóm đúng ngưỡng hiệu dụng | Kiểm tra response ID thực | Không mặc định có AD range | Không đoán từ `size()`. |
| Nhóm vượt ngưỡng | Nhiều `member;range` | Đọc/giới hạn tùy server | Lấy đủ hoặc trả INCOMPLETE. |
| Server trả ít hơn yêu cầu | Có thể xảy ra | Không áp dụng range AD | Lượt sau bắt đầu từ high+1. |
| Server trả `member;range=low-*` | Kết thúc | Không áp dụng | Dừng đúng. |
| Response không có attribute | ACL/empty/unsupported | ACL/empty/schema | Không tự coi COMPLETE. |
| Group thay đổi giữa các lượt | Cần đối soát | Có thể thay đổi trong lúc đọc | Không cam kết snapshot. |
| Search nhiều hơn số entry giới hạn | MaxPageSize/server policy | sizelimit/server policy | Paged Results khi hỗ trợ. |
| Cookie paged search rỗng | Hết trang | Hết trang | Kết thúc pagination. |
| Paged search dùng connection khác | Có thể mất state | Tùy server | Giữ đúng connection. |
| Reader thiếu quyền Search `member` | Có thể không thấy kết quả | Có thể không thấy kết quả | Phân biệt ACL với không thuộc nhóm. |
| Reader thiếu quyền Read `member` | Giá trị có thể bị ẩn | Giá trị có thể bị ẩn | Không nâng quyền tự động. |
| Người dùng nằm trong nhóm gián tiếp | Chính sách nested groups riêng | Tùy schema/overlay | Không tự đồng nhất direct/transitive. |
| Tài khoản nhóm ở sai naming context | Search sai base | Search sai base | Không kết luận không tồn tại. |
| Referral sang server khác | Kiểm soát destination | Kiểm soát destination | Không chuyển credential ngoài policy. |
| LDAP connection/TLS timeout | Có thể không nhận LDAPResult | Tương tự | Không bịa sizeLimit error. |
| Group rỗng | Có thể không có `member` | `groupOfNames` thường đòi member | Có policy rõ về empty/hidden. |
| Gia tăng thành viên đồng thời | Range có thể biến động | Đọc thường cũng không là snapshot | Phát hiện/đối soát. |

### 20.1. Unit test cho hàm parse range

Tách logic parse response ID thành một helper thuần Java để unit test độc lập với AD thật. Các trường hợp tối thiểu:

~~~text
member;range=0-999      -> low=0, high=999, not last
member;range=1000-*     -> low=1000, last=true
member;range=0-499      -> nextLow=500
member;range=0-*        -> low=0, last=true
MEMBER;RANGE=0-999      -> tùy policy case-insensitive
member                  -> không phải ranged attribute
member;range=abc-*      -> invalid
member;range=-1-999     -> invalid
member;range=500-100    -> invalid
~~~

Thêm test số quá lớn gây `NumberFormatException`, hai ranged attributes mâu thuẫn, no values, duplicate member và giới hạn `MAX_REQUESTS`. **Không** cho những lỗi này biến thành danh sách hoàn chỉnh.

### 20.2. Integration test với nhóm trên 1.500 người

Trong AD test environment, tạo group có số lượng thành viên vượt `MaxValRange` đang áp dụng. Không phụ thuộc vào 1.500 như hằng số tuyệt đối; đọc/ghi nhận policy thực và thay số fixture phù hợp.

Quy trình:

1. Xác minh Bind DN đọc được `member` khi nhóm ít người.
2. Tạo hoặc dùng group thử nghiệm lớn có số member đã biết.
3. Đọc một lượt `member` và liệt kê attribute IDs.
4. Đọc từng range bằng cùng một context, tới `*`.
5. So sánh tập DN với fixture chuẩn; không chỉ so số lượng.
6. Thử giới hạn trả ít hơn request nếu môi trường cho phép cấu hình.
7. Kiểm tra tài khoản reader không được Modify `member`.
8. Thu thập metrics số lượt/độ trễ, không log DN thật.
9. Dọn dữ liệu test; không thay đổi nhóm quyền production.

### 20.3. Kiểm thử một vòng xử lý đầy đủ

Đối với chức năng đồng bộ quyền, hoàn tất chỉ khi:

- Search các entry mục tiêu đã đọc **đủ các trang**;
- Với mọi group cần xuất danh sách, attribute member đã đọc **đủ range** nếu server yêu cầu;
- Không có exception size/time/admin limit hoặc referral chưa xử lý;
- Có đối soát khi nhóm thay đổi đồng thời;
- Không vượt giới hạn tài nguyên của ứng dụng.

Nếu không bảo đảm được các điều kiện trên, trạng thái phải là **FAILED/INCOMPLETE**, không lưu checkpoint “đã đồng bộ tất cả thành viên”.

## 21. Cấu hình giới hạn và khả năng vận hành

### Các tham số cần theo dõi

| Chỉ số | Lý do |
| --- | --- |
| `ldap.search.entry.count` | Phát hiện truy vấn trả nhiều entry. |
| `ldap.search.page.count` | Chi phí paging. |
| `ldap.group.range.request.count` | Số lượt đọc attribute nhiều giá trị. |
| `ldap.group.member.value.count` | Kích thước nhóm thực tế, không dùng làm nhãn metric. |
| `ldap.group.read.duration` | Phát hiện nhóm quá lớn hoặc server chậm. |
| `ldap.group.read.incomplete` | Báo động nếu quá trình lấy thành viên không hoàn tất. |
| `ldap.error.size_limit` | Phân biệt policy từ server với ứng dụng. |
| `ldap.error.tls_or_network` | Không nhầm lỗi transport với kết quả thiếu. |

### Timeout theo lớp

- `SearchRequest.timeLimit` (giao thức): **giây**.
- `LdapQueryBuilder.timeLimit(...)`: **mili giây** ở Java/JNDI.
- JNDI connect/read timeout: cấu hình theo provider/JDK.
- Tổng thời gian duyệt nhiều range và trang: ứng dụng phải tự giới hạn.
- HTTP deadline: không tự được bảo đảm chỉ vì một Search có `timeLimit`.

Duyệt 30 range, mỗi range 2 giây, có thể kéo dài vượt SLA. Giới hạn mỗi request và tổng deadline **đều cần**.

### Giới hạn kích thước bộ nhớ

Một nhóm có 100.000 member DN dài có thể chiếm đáng kể bộ nhớ Java khi đưa vào `List<String>`. Với dữ liệu quá lớn, có thể cần xử lý theo batch và lưu tới một sink được kiểm soát, song vẫn phải ghi **trạng thái incomplete** cho tới khi nhận terminal range. Không phát tán một phần danh sách cho hệ thống phân quyền như dữ liệu hoàn chỉnh.

## 22. Lựa chọn chiến lược cho từng use case

| Mục tiêu | Giải pháp ưu tiên | Vì sao |
| --- | --- | --- |
| Tìm 20 nhóm theo tên | Search với base/filter/countLimit | Không cần paging phức tạp nếu ít entry. |
| Liệt kê tất cả nhóm trong OU lớn | Simple Paged Results | Giải quyết giới hạn **entry**. |
| Hiển thị toàn bộ member nhóm AD lớn | AD range retrieval | Giải quyết giới hạn **value** của một entry. |
| Kiểm tra một user có thuộc group không | Filter `(member=fullUserDn)` tại group entry | Tránh tải mọi member; còn tùy ACL và schema. |
| Xuất toàn bộ nhóm và member | Paging + range + đối soát | Hai giới hạn độc lập. |
| Nhóm OpenLDAP nhỏ | Đọc `member` thường | Không giả định AD extension. |
| Nhóm POSIX | Đọc `memberUid` và ánh xạ UID | Khác về schema và loại định danh. |
| Cấp quyền nhạy cảm cho API | Luồng authorization đáng tin, fail closed | Không dùng danh sách bị cắt để cấp quyền. |

## 23. Những sai lầm phổ biến

1. **Đặt `countLimit(10_000)` rồi nghĩ AD sẽ trả 10.000 member**: countLimit đếm **entry**, không đếm attribute values.
2. **Dùng LDAP paging cookie để đọc tiếp `member`**: cookie dành cho các **entry** Search, không phải offset của member.
3. **Hardcode 1.500 vào ứng dụng**: server có thể trả ít hơn, và MaxValRange có thể thay đổi.
4. **Tăng offset theo request thay vì response**: dễ bỏ sót DN khi server cắt range ngắn hơn.
5. **Không kiểm tra `*`**: có thể request vô hạn hoặc đánh dấu nhầm chưa/đã hoàn tất.
6. **Chỉ đọc `attrs.get("member")`**: có thể bỏ qua attribute ranged do AD trả.
7. **Giả định attribute absent = group rỗng**: có thể do ACL hoặc sai schema.
8. **Dùng groupOfNames trên AD mà không xác minh schema**: objectClass khác nhau giữa hệ thống.
9. **Dùng `memberOf` như toàn bộ tập nhóm hiệu lực**: có khác biệt về direct/nested/primary group và quyền đọc.
10. **Ánh xạ kết quả thiếu vào `Set<Name>` rồi `save`**: nguy cơ làm hỏng nhóm hoặc thay đổi dữ liệu không mong đợi.
11. **Dùng DN của nhóm do HTTP client gửi nguyên văn**: nguy cơ truy vấn ngoài scope và tiết lộ dữ liệu.
12. **Đọc từng range trên DC ngẫu nhiên khác nhau**: thứ tự/replication có thể khiến kết quả không nhất quán.
13. **Để người dùng tìm toàn bộ group member tự do**: rủi ro lộ dữ liệu tổ chức và gây tải.
14. **Fallback sang admin khi reader bị ACL từ chối**: vượt chính sách truy cập.
15. **Bỏ qua `SizeLimitExceededException` trong job cần dữ liệu đầy đủ**: checkpoint sai.
16. **Tin rằng range retrieval là snapshot ACID**: thay đổi đồng thời vẫn gây mất/trùng.
17. **Chỉ test nhóm 3 người**: không hề kiểm chứng vấn đề MaxValRange.
18. **Không giới hạn tổng số lượt read**: có thể tạo request tốn tài nguyên hoặc lặp vô hạn.

## 24. Bài tập thực hành

**Bài 1 — Hai giới hạn độc lập.** Directory có 2.500 entry nhóm; một group chứa 3.200 member. Giải thích tại sao Paged Results cần cho danh sách nhóm và range retrieval cần cho group lớn. Mô tả hai luồng riêng.

**Bài 2 — Đọc response range.** Client xin `member;range=0-1499` nhưng server trả `member;range=0-999`. Viết phép tính `nextLow`, thiết kế request tiếp theo và giải thích vì sao không được lấy 1500.

**Bài 3 — Terminal marker.** Với response `member;range=2000-*`, nêu ý nghĩa và cách dừng. Tại sao `*` ở đây không phải wildcard của LDAP search filter?

**Bài 4 — Java range reader.** Đóng gói code mục 10 thành component nhận **group ID đã xác minh**, xây DN bằng `LdapNameBuilder`, có max member/range/time và trả trạng thái complete hoặc exception. Viết unit test cho parser.

**Bài 5 — Kiểm thử ACL.** Reader service account chỉ đọc `cn`/`member` dưới `OU=Groups`. Thử Modify `member` và xác nhận LDAP từ chối. Sau đó dùng chính account reader kiểm tra group lớn không bị trả dữ liệu thiếu do ACL.

**Bài 6 — Server capabilities.** Dựng AD test (hoặc dùng directory thử nghiệm được phép), so sánh nó với OpenLDAP. Ghi lại `objectClass`, attribute member, hành vi Search nhiều entry và cách trả nhóm nhiều giá trị. Không ép OpenLDAP phải hỗ trợ range.

**Bài 7 — Không tải toàn bộ nhóm.** Viết Search trên chính entry nhóm với `(member=fullUserDn)` để kiểm tra membership trực tiếp. So sánh số request và dữ liệu truyền về với cách duyệt mọi range.

**Bài 8 — Concurrent updates.** Trong directory test, thêm/xóa thành viên giữa các lượt range. Phát hiện duplicate/missing, thảo luận dấu thay đổi và cơ chế đối soát nếu kết quả dùng cho phân quyền.

**Bài 9 — Repository thiếu dữ liệu.** Tạo entity ODM `@Attribute(name="member") Set<Name>`, đọc nhóm AD vượt MaxValRange rồi so sánh với range reader. Chỉ thực hiện **read**, không `repository.save` lên nhóm thật.

**Bài 10 — Paging + range.** Viết sơ đồ hai tầng: duyệt tất cả group bằng cookie rồi đọc `member;range` cho từng group. Xác định lúc nào một batch mới được đánh dấu COMPLETE.

## 25. Câu hỏi tự đánh giá

1. LDAP `sizeLimit` giới hạn số entry hay số giá trị của attribute `member`?
2. Active Directory `MaxPageSize` và `MaxValRange` khác nhau ở điểm nào?
3. Khi một Search trả một group entry, tại sao vẫn có thể thiếu member?
4. `member;range=0-1499` có bao nhiêu **chỉ số** nếu trả đủ?
5. Nếu response là `member;range=0-499`, request tiếp theo nên bắt đầu từ đâu?
6. `member;range=1500-*` báo điều gì?
7. Tại sao không được hardcode 1500 cho mọi DC?
8. Vì sao `attributes.get("member")` có thể null dù AD group có hàng nghìn thành viên?
9. Vì sao phải đọc `Attribute.getID()` trước khi xác định range thực tế?
10. Paging cookie có thay thế `member;range` được không?
11. Thế nào là sự khác nhau giữa `groupOfNames.member` và `posixGroup.memberUid`?
12. Với Active Directory, vì sao `objectClass=group` phù hợp hơn `groupOfNames` khi tra cứu nhóm AD?
13. Vì sao range retrieval cùng kết nối vẫn không bảo đảm snapshot nếu group đang được cập nhật?
14. Nếu không có attribute ranged response, có được kết luận group rỗng ngay không?
15. Vì sao Spring Data LDAP `@Attribute(name="member")` có thể không đủ cho nhóm AD rất lớn?
16. Tại sao không nên `repository.save(group)` khi entity chỉ chứa một phần `member`?
17. Nếu chỉ muốn biết một người thuộc group không, có cách nào tránh đọc toàn bộ member?
18. `memberOf` có luôn bao gồm nested group/primary group trên mọi server không?
19. Vì sao `SearchResultDone` thành công với 1 entry không đồng nghĩa member values đầy đủ?
20. Cần test những gì để chứng minh một workflow đồng bộ nhóm đã đọc đủ dữ liệu?

**Ghi nhớ:** giới hạn số **entry** của LDAP Search và giới hạn số **giá trị** trong một attribute là **hai vấn đề khác nhau**. Với nhiều entry, dùng Paged Results Control. Với nhóm Active Directory có `member` quá lớn, đọc lần lượt `member;range=low-high`, tăng offset theo **high thực tế trả về** và chỉ kết thúc khi nhận `member;range=low-*`. Đừng coi thuộc tính thiếu, Search trả đúng cap hoặc repository mapping chưa kiểm chứng là bằng chứng dữ liệu nhóm đã đầy đủ. Bảo mật, schema, ACL, TLS, timeout và thay đổi đồng thời phải được tính vào thiết kế.

### Tài liệu tham khảo

- [Microsoft MS-ADTS — Range Retrieval of Attribute Values](https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-adts/e27b48db-6f82-44cd-9038-2e54f790cc1f): cú pháp `range=low-high`, dấu `*`, metadata response và thứ tự giá trị.
- [Microsoft MS-ADTS — LDAP Policies](https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-adts/3f0137a1-63df-400c-bf97-e1040f055a99): `MaxPageSize`, `MaxValRange`, `MaxQueryDuration` và cấu hình policy.
- [Microsoft — Enumerating Groups That Contain Many Members](https://learn.microsoft.com/en-us/windows/win32/ad/enumerating-groups-that-contain-many-members): lý do phải dùng range retrieval trên AD.
- [Microsoft — Paging Search Results](https://learn.microsoft.com/en-us/previous-versions/windows/desktop/ldap/paging-search-results): Simple Paged Results và giới hạn entry trên AD.
- [RFC 4511 — LDAP: The Protocol](https://www.rfc-editor.org/rfc/rfc4511): SearchRequest, SearchResultEntry, sizeLimit, timeLimit và resultCode.
- [RFC 2696 — LDAP Control Extension for Simple Paged Results](https://www.rfc-editor.org/rfc/rfc2696): cookie và cơ chế phân trang entry.
- [RFC 4512 — LDAP: Directory Information Models](https://www.rfc-editor.org/rfc/rfc4512): entry, attribute, DN và schema.
- [RFC 4514 — LDAP: String Representation of Distinguished Names](https://www.rfc-editor.org/rfc/rfc4514): DN escaping.
- [RFC 4515 — LDAP: String Representation of Search Filters](https://www.rfc-editor.org/rfc/rfc4515): filter escaping khi kiểm tra membership.
- [RFC 4519 — LDAP: Schema for User Applications](https://www.rfc-editor.org/rfc/rfc4519): `groupOfNames`, `member` và `groupOfUniqueNames`.
- [Spring LDAP — Processing the DirContext](https://docs.spring.io/spring-ldap/reference/processing-the-dircontext.html): `DirContextProcessor`, paged results và `SingleContextSource`.
- [Spring LDAP — LdapTemplate API](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/LdapTemplate.html): `lookup`, `search`, count limit và exception policy.
- [Spring Data LDAP — Reference](https://docs.spring.io/spring-data/ldap/reference/): ODM, `@Entry`, `@Attribute` và repository.
- [Java SE — Attributes API](https://docs.oracle.com/en/java/javase/21/docs/api/java.naming/javax/naming/directory/Attributes.html): `getAll`, `get` và attribute ID.
- [Java SE — DirContext API](https://docs.oracle.com/en/java/javase/21/docs/api/java.naming/javax/naming/directory/DirContext.html): `getAttributes` và các thao tác directory.
