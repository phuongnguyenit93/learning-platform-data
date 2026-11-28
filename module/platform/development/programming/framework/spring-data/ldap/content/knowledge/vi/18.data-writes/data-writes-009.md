# Xóa entry có con và thiết kế thứ tự thao tác

Một entry LDAP có thể chứa nhiều entry con. Ví dụ OU `ou=engineering` có user, group con và các OU theo nhóm. Khi cần xóa toàn bộ nhánh này, gọi một lệnh delete trực tiếp trên OU cha thường không thành công: LDAP chuẩn chỉ cho phép DeleteRequest xóa entry lá, tức entry không còn subordinate entries.

Vì vậy, xóa một nhánh directory cần có **thứ tự thao tác**. Phải xóa các entry sâu nhất trước, sau đó mới xóa entry cha. Spring LDAP cung cấp `LdapTemplate.unbind(dn, true)` để thực hiện thao tác unbind đệ quy; với một số directory server, có thể có control xóa subtree phía server. Các cách này có phạm vi hỗ trợ và cách xử lý lỗi khác nhau, nên cần chọn theo directory đang dùng và quy mô subtree.

Bài thuộc chương **Ghi dữ liệu** của module `SPRING_DATA_LDAP`. Module hướng dẫn truy cập directory LDAP qua Spring Data LDAP repository và ánh xạ entry phân cấp sang Java object, bao gồm DN, objectClass, schema, repository, `LdapTemplate`, CRUD, filter an toàn, bảo mật kết nối và kiểm thử. Bài tập trung vào việc xóa entry có con, lựa chọn chiến lược xóa và thiết kế thứ tự thao tác để tránh để lại subtree ở trạng thái dở dang.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích vì sao LDAP DeleteRequest thông thường chỉ xóa entry lá.
- Nhận diện result code `notAllowedOnNonLeaf` (66).
- Dựng thứ tự xóa theo kiểu post-order: con trước, cha sau.
- Phân biệt xóa một entry, xóa descendants nhưng giữ root và xóa toàn bộ subtree gồm root.
- Dùng `LdapTemplate.unbind(Name)` và `unbind(Name, true)` đúng mục đích.
- Hiểu Spring LDAP recursive unbind duyệt và xóa descendants ở phía client.
- Biết khi nào có thể dùng subtree-delete control đặc thù của directory server.
- Lập kế hoạch preview, authorization, giới hạn phạm vi và kiểm tra kết quả.
- Xử lý partial failure, retry, concurrent writer và kết nối bị mất.
- Viết integration test cho cây nhiều tầng và trường hợp xóa thất bại.

## 2. Mô hình cây LDAP và quan hệ cha-con

Directory tổ chức entry theo cây tên phân biệt. Ví dụ:

~~~text
dc=example,dc=org
└── ou=departments
    ├── ou=engineering
    │   ├── uid=lan
    │   ├── uid=minh
    │   └── ou=platform
    │       └── uid=an
    └── ou=finance
        └── uid=hoa
~~~

Mỗi entry có một DN duy nhất trong cây:

| Entry | DN |
|---|---|
| OU Engineering | `ou=engineering,ou=departments,dc=example,dc=org` |
| User Lan | `uid=lan,ou=engineering,ou=departments,dc=example,dc=org` |
| OU Platform | `ou=platform,ou=engineering,ou=departments,dc=example,dc=org` |
| User An | `uid=an,ou=platform,ou=engineering,ou=departments,dc=example,dc=org` |

Trong cây này, `ou=engineering` có subordinate entries là `uid=lan`, `uid=minh` và `ou=platform`. OU Platform lại có user An là entry con.

Khi xóa OU Engineering, cần xử lý toàn bộ descendants. Nếu xóa OU cha trước, các entry con vẫn tồn tại và cấu trúc directory không cho phép thao tác đó theo DeleteRequest thông thường.

### 2.1. Leaf entry và non-leaf entry

- **Leaf entry**: entry không có subordinate entries. Ví dụ `uid=lan` nếu nó không chứa entry con.
- **Non-leaf entry**: entry có ít nhất một subordinate entry. Ví dụ `ou=engineering` trong cây trên.

Một entry có thể là leaf hôm nay và trở thành non-leaf sau khi một entry con được thêm vào. Vì vậy, kết quả kiểm tra trước khi xóa chỉ là snapshot tại thời điểm kiểm tra; nếu có writer khác tạo child sau đó, thao tác delete vẫn có thể thất bại.

## 3. Vì sao DeleteRequest không xóa được entry có con?

RFC 4511 `4.8 mô tả Delete operation. `DelRequest` mang DN của entry cần xóa và server chỉ được xóa leaf entry. Nếu entry vẫn có subordinate entries, server có thể trả `notAllowedOnNonLeaf`, mã kết quả LDAP 66. [RFC 4511 — `4.8 Delete Operation](https://www.rfc-editor.org/rfc/rfc4511#section-4.8) · [RFC 4511 — Result Codes](https://www.rfc-editor.org/rfc/rfc4511#section-4.1.9).

Ví dụ:

~~~text
DeleteRequest:
ou=engineering,ou=departments,dc=example,dc=org
~~~

Nếu `uid=lan` hoặc `ou=platform` vẫn còn bên dưới, thao tác xóa OU Engineering không thể hoàn tất bằng DeleteRequest thông thường.

Một số mã kết quả thường gặp:

| LDAP result code | Tên | Ý nghĩa trong luồng xóa |
|---:|---|---|
| 0 | `success` | Entry mục tiêu đã được xóa |
| 32 | `noSuchObject` | DN mục tiêu không tồn tại hoặc không được tìm thấy trong naming context |
| 50 | `insufficientAccessRights` | Bind identity không có quyền xóa entry hoặc một phần subtree |
| 53 | `unwillingToPerform` | Server từ chối thao tác theo policy hoặc giới hạn riêng |
| 66 | `notAllowedOnNonLeaf` | Entry còn subordinate entries |
| 11 | `adminLimitExceeded` | Có thể gặp với một số thao tác subtree-delete có giới hạn xử lý |

Không nên bắt mọi lỗi xóa rồi chuyển thành “entry không tồn tại”. Mã lỗi giúp phân biệt sai thứ tự thao tác, sai DN, thiếu quyền và giới hạn server.

### 3.1. Delete không dereference alias

RFC 4511 quy định server không dereference alias khi xác định entry đích của DeleteRequest. Nếu DN trỏ tới một alias entry, request tác động lên chính alias entry theo quy tắc server; nó không có nghĩa là xóa object mà alias trỏ tới. Khi preview subtree có alias, phải phân biệt alias entry với target object và không mở rộng phạm vi xóa qua alias một cách ngầm định.

## 4. Quy tắc thứ tự: xóa con trước, cha sau

Thứ tự phù hợp là duyệt cây theo **post-order traversal**:

1. Đi tới từng child.
2. Xóa toàn bộ descendants của child.
3. Xóa chính child.
4. Khi mọi child đã biến mất, xóa parent.

Với cây Engineering:

~~~text
Bắt đầu:
ou=engineering
├── uid=lan
├── uid=minh
└── ou=platform
    └── uid=an

Thứ tự xóa hợp lệ:
1. uid=lan
2. uid=minh
3. uid=an
4. ou=platform
5. ou=engineering
~~~

Thứ tự giữa các nhánh ngang hàng có thể khác nhau nếu chúng độc lập. Ràng buộc quan trọng là một entry phải được xóa trước ancestor của nó.

### 4.1. Ví dụ thứ tự bằng độ sâu DN

Nếu một snapshot subtree chứa DN đầy đủ và tất cả DN dùng cùng một base, entry có nhiều RDN hơn thường nằm sâu hơn. Có thể sắp xếp độ sâu giảm dần:

~~~java
List<LdapName> deletionOrder = treeReader.findSubtreeIncludingRoot(rootDn);

deletionOrder.sort(
    Comparator.comparingInt(LdapName::size).reversed()
);

for (LdapName dn : deletionOrder) {
    ldapTemplate.unbind(dn);
}
~~~

`findSubtreeIncludingRoot` là method của ứng dụng để tìm toàn bộ subtree và trả về DN đầy đủ, bao gồm root. Ví dụ chỉ đúng khi snapshot đã hoàn tất, mọi DN ở cùng naming context và không có entry mới được thêm trong lúc xóa.

Không dùng độ dài chuỗi DN (`String.length()`) để suy ra độ sâu. Escape, Unicode và độ dài giá trị RDN không phản ánh số cấp trong cây.

### 4.2. Sơ đồ luồng

~~~mermaid
flowchart TD
    A["Xác định root DN"] --> B["Preview toàn bộ subtree"]
    B --> C{"Phạm vi và quyền hợp lệ?"}
    C -- "Không" --> X["Dừng, không xóa"]
    C -- "Có" --> D["Chặn hoặc phối hợp writer"]
    D --> E["Xóa các leaf entries"]
    E --> F{"Còn child?"}
    F -- "Có" --> E
    F -- "Không" --> G["Xóa parent"]
    G --> H["Xác minh subtree đã biến mất"]
~~~

## 5. Ba chiến lược xóa subtree

Có ba hướng thường gặp:

| Chiến lược | Cách hoạt động | Phù hợp khi |
|---|---|---|
| Tự duyệt và xóa leaf-first | Ứng dụng tìm child, xóa sâu nhất rồi xóa cha | Cần kiểm soát từng entry, audit và xử lý nghiệp vụ riêng |
| Spring LDAP recursive unbind | `LdapTemplate` duyệt các subcontext và xóa descendants đệ quy | Subtree có quy mô vừa, muốn dùng API Spring LDAP |
| Server-side subtree-delete control | Gửi DeleteRequest kèm control đặc thù do server hỗ trợ | Directory có control phù hợp, subtree lớn và đã xác minh giới hạn |

Không có một cách xóa subtree duy nhất áp dụng cho mọi LDAP server. RFC 4511 DeleteRequest tiêu chuẩn chỉ xóa leaf; subtree-delete control là extension do server hỗ trợ, không nên suy ra từ việc server hỗ trợ LDAPv3.

## 6. Dùng LdapTemplate.unbind đúng cách

Spring LDAP có các overload:

- `unbind(Name dn)` hoặc `unbind(String dn)`: xóa một entry; entry phải là leaf.
- `unbind(Name dn, boolean recursive)` hoặc overload String tương ứng: tùy chọn xóa tất cả subcontexts/descendants.

Tài liệu `LdapOperations` ghi rõ nếu `recursive` là `false` và entry có child, thao tác sẽ thất bại. `LdapTemplate` cũng công bố helper `deleteRecursively(DirContext, Name)` để xóa tất cả subcontexts, bao gồm entry bắt đầu. [Spring LDAP — LdapOperations.unbind](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/LdapOperations.html) · [Spring LDAP — LdapTemplate](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/LdapTemplate.html).

Ví dụ xóa một leaf:

~~~java
ldapTemplate.unbind(
    "uid=lan,ou=engineering,ou=departments"
);
~~~

Ví dụ xóa subtree gồm cả OU Engineering và descendants:

~~~java
ldapTemplate.unbind(
    "ou=engineering,ou=departments",
    true
);
~~~

Nếu `ContextSource` cấu hình base DN là `dc=example,dc=org`, DN trong ví dụ là relative DN so với base đó. Nếu không cấu hình base, truyền DN đầy đủ theo naming context. Luôn thống nhất quy ước DN của service; không nối base DN hai lần.

### 6.1. recursive=true xóa cả entry gốc

Đây là điểm dễ nhầm: `unbind(rootDn, true)` xóa root và toàn bộ descendants của nó. Nếu yêu cầu nghiệp vụ là **chỉ xóa các entry con và giữ OU cha**, cần duyệt child của root và xóa từng child subtree, không gọi recursive unbind trực tiếp trên root.

Ví dụ:

~~~text
Root cần giữ:
ou=engineering,ou=departments,dc=example,dc=org

Cần xóa:
uid=lan,...
uid=minh,...
ou=platform,...
~~~

Sau khi xóa, OU Engineering vẫn tồn tại nhưng rỗng. Đây là hai yêu cầu khác nhau về phạm vi và cần được thể hiện rõ trong API/service method.

### 6.2. Spring recursive unbind không phải một DeleteRequest duy nhất

Recursive unbind là thao tác do Spring LDAP thực hiện thông qua `DirContext` và việc duyệt subcontexts. Nó khác với một control server-side yêu cầu directory xóa subtree trong một DeleteRequest.

Hệ quả:

- Có thể có nhiều lệnh LDAP được gửi theo thứ tự.
- Một lỗi ở giữa có thể để lại một phần subtree đã bị xóa.
- Không có bảo đảm toàn bộ subtree được xóa nguyên tử.
- Cần kiểm tra lại directory sau lỗi hoặc timeout.

Đừng coi `recursive=true` là transaction bao trùm mọi entry con.
## 7. Tự duyệt subtree bằng DirContext

Khi cần kiểm soát từng bước, có thể dùng LdapTemplate.executeReadWrite để thao tác trên một DirContext. Ý tưởng là lấy danh sách child trực tiếp, đóng enumeration, xóa từng child subtree, rồi mới unbind entry hiện tại.

Ví dụ sau là một triển khai minh họa cho cây có độ sâu vừa phải:

~~~java
import java.util.ArrayList;
import java.util.List;

import javax.naming.NameClassPair;
import javax.naming.NamingEnumeration;
import javax.naming.NamingException;
import javax.naming.directory.DirContext;
import javax.naming.ldap.LdapName;
import javax.naming.ldap.Rdn;

import org.springframework.ldap.core.LdapTemplate;

public class DirectoryTreeDeleter {

    private final LdapTemplate ldapTemplate;

    public DirectoryTreeDeleter(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public void deleteSubtree(LdapName rootDn) {
        ldapTemplate.executeReadWrite(ctx -> {
            deleteRecursively(ctx, rootDn);
            return null;
        });
    }

    private void deleteRecursively(
            DirContext ctx,
            LdapName dn) throws NamingException {

        for (LdapName childDn : directChildren(ctx, dn)) {
            deleteRecursively(ctx, childDn);
        }

        // Chỉ xóa entry hiện tại sau khi tất cả child đã biến mất.
        ctx.unbind(dn);
    }

    private List<LdapName> directChildren(
            DirContext ctx,
            LdapName parentDn) throws NamingException {

        List<LdapName> children = new ArrayList<>();
        NamingEnumeration<NameClassPair> result = ctx.list(parentDn);

        try {
            while (result.hasMore()) {
                NameClassPair child = result.next();

                LdapName childDn = (LdapName) parentDn.clone();
                childDn.add(new Rdn(child.getName()));

                children.add(childDn);
            }
        } finally {
            result.close();
        }

        return children;
    }
}
~~~

LdapName lưu RDN theo thứ tự từ phải sang trái. Phương thức add(Rdn) thêm RDN vào cuối chuỗi thành phần nội bộ; khi hiển thị DN, RDN mới trở thành phần bên trái nhất, tức RDN của child. Đây là lý do đoạn code có thể clone parent rồi add RDN do list trả về.

Trong JNDI, tên truyền vào DirContext là relative với context đang thao tác. list(parentDn) liệt kê các binding trực tiếp bên dưới parent; tên của mỗi kết quả tương đối với parent đó. Ví dụ giả định LDAP provider trả về mỗi child dưới dạng một RDN hợp lệ, có thể parse bằng Rdn. [Java SE — DirContext](https://docs.oracle.com/en/java/javase/17/docs/api/java.naming/javax/naming/directory/DirContext.html) · [Spring LDAP — executeReadWrite](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/LdapOperations.html).

### 7.1. Vì sao phải đóng enumeration trước khi xóa?

Method directChildren đọc hết tên child vào list rồi đóng NamingEnumeration. Vòng lặp đệ quy bắt đầu sau đó.

Cách này tránh giữ một search/list enumeration mở trong lúc sửa chính nhánh đang được liệt kê. Nó cũng làm rõ snapshot của từng cấp: child nào được phát hiện trong lần list đó sẽ được xử lý.

Tuy nhiên, đây vẫn là một snapshot tại từng cấp. Nếu writer khác thêm child sau khi list xong, thao tác ctx.unbind(parentDn) có thể thất bại với notAllowedOnNonLeaf. Muốn xóa ổn định, cần phối hợp writer hoặc có cơ chế khóa/maintenance window.

### 7.2. Chỉ xóa descendants và giữ lại root

Nếu muốn giữ root rỗng, tách thao tác thành hai bước: liệt kê child trực tiếp của root, gọi deleteRecursively cho từng child, và không gọi ctx.unbind(rootDn).

~~~java
public void deleteChildrenOnly(LdapName rootDn) {
    ldapTemplate.executeReadWrite(ctx -> {
        for (LdapName childDn : directChildren(ctx, rootDn)) {
            deleteRecursively(ctx, childDn);
        }
        return null;
    });
}
~~~

Đặt tên method thể hiện rõ phạm vi xóa. Tránh một method tên chung deleteDepartment nhưng lúc thì xóa root, lúc thì giữ root tùy boolean khó hiểu.

### 7.3. Giới hạn của cách đệ quy thủ công

Đệ quy dễ đọc, nhưng có một số giới hạn:

- Mỗi cấp mở một danh sách child và giữ stack lời gọi cho đến khi subtree được xóa.
- Một cây cực sâu có thể làm tăng stack depth.
- Một subtree lớn giữ DirContext write context trong thời gian dài.
- Một lỗi giữa chừng để lại phần đã xóa và phần còn tồn tại.
- list có thể gặp referral, quyền bị giới hạn hoặc lỗi provider-specific.

Với cây rất sâu/lớn, cân nhắc thuật toán iterative dùng stack tường minh, chia batch, hoặc control server-side nếu directory hỗ trợ. Luôn kiểm thử trên loại server và phiên bản thực tế.

## 8. Subtree-delete control của Active Directory

Microsoft Active Directory hỗ trợ control LDAP_SERVER_TREE_DELETE_OID có OID:

~~~text
1.2.840.113556.1.4.805
~~~

Control được gửi kèm một LDAP Delete operation để yêu cầu Domain Controller xóa cả subtree bên dưới entry chỉ định, bao gồm chính entry gốc. Đây là extension riêng của AD, không phải hành vi DeleteRequest mặc định của RFC 4511. [Microsoft — LDAP_SERVER_TREE_DELETE_OID](https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-adts/b8ee2305-b0eb-41be-894f-b94b5d29ca9e).

Các điểm quan trọng:

- Control không cần controlValue; trường này được bỏ qua.
- Server phải có quyền phù hợp và có thể từ chối theo policy hoặc trạng thái object.
- Một request xử lý tối đa 16.384 object.
- Nếu server không thể xóa toàn bộ tree trong một request, nó không xóa root và trả adminLimitExceeded / ERROR_DS_TREE_DELETE_NOT_FINISHED.
- Các descendant đã được xử lý trước khi chạm giới hạn có thể đã bị xóa; vì vậy không xem lỗi này là “không có gì thay đổi”.
- Tài liệu Microsoft cho phép gửi lại request tree-delete cho đến khi nhận success; trước khi retry trong ứng dụng, vẫn cần xác minh root và phạm vi mục tiêu.

[Microsoft — Tree-delete Operation](https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-adts/12616f59-c05d-4b4e-8026-2a65db152342) · [Microsoft — LDAP_SERVER_TREE_DELETE_OID control](https://learn.microsoft.com/en-us/previous-versions/windows/desktop/ldap/ldap-server-tree-delete-oid).

### 8.1. Kiểm tra server có hỗ trợ control

RootDSE của LDAP server có thuộc tính supportedControl để công bố control OID được hỗ trợ. Với AD, kiểm tra OID 1.2.840.113556.1.4.805 trước khi chọn chiến lược này.

Không suy luận rằng mọi server hiểu OID đó. Một server LDAP khác có thể từ chối control hoặc trả unavailableCriticalExtension nếu control được gửi với criticality bắt buộc mà server không hỗ trợ.

### 8.2. Tree-delete control và Spring recursive unbind là hai cơ chế khác nhau

| Thuộc tính | Spring unbind(dn, true) | AD tree-delete control |
|---|---|---|
| Ai duyệt cây? | Spring/client qua JNDI | Domain Controller |
| Cách xóa | Nhiều thao tác unbind theo thứ tự | Một DeleteRequest kèm control |
| Phạm vi | Root và descendants | Root và descendants |
| Tính nguyên tử | Không có transaction nguyên tử cho toàn cây | Có thể partial progress khi vượt giới hạn; root chưa bị xóa |
| Khả năng tương thích | API Spring LDAP, tùy provider/JNDI | Chỉ directory server hỗ trợ OID |
| Kiểm soát từng entry | Dễ chèn audit/logic giữa các bước hơn | Ít cơ hội can thiệp giữa các entry |

LdapTemplate.unbind(dn, true) không tự động có nghĩa là Spring gửi AD tree-delete control. Nếu muốn dùng control, phải cấu hình/gửi control qua LDAP API phù hợp và xác minh provider/server hỗ trợ.

## 9. Preview và xác nhận phạm vi trước khi xóa

Xóa subtree có thể ảnh hưởng hàng trăm hoặc hàng nghìn entry. Trước khi thực hiện, cần một bước preview chỉ đọc.

Một kế hoạch xóa nên xác định:

- DN root chính xác.
- Root có nằm dưới naming context/base DN mà service được phép quản lý không.
- Số descendants và số cấp sâu nhất.
- Những loại entry sẽ bị xóa: user, group, OU, service account, application config.
- Có entry hệ thống, replication agreement, service account hoặc object được bảo vệ trong nhánh không.
- Những tham chiếu từ bên ngoài subtree có thể bị ảnh hưởng.
- Danh tính service account thực hiện xóa và quyền xóa cần thiết.
- Người/luồng nghiệp vụ đã phê duyệt phạm vi.

Một preview DTO có thể chứa:

~~~java
public record SubtreeDeletePlan(
    LdapName rootDn,
    int entryCount,
    int maximumDepth,
    List<LdapName> protectedEntries,
    String planId
) {}
~~~

Đây là model minh họa. entryCount cần tính cả root nếu chiến lược cuối cùng xóa root. Nếu preview phát hiện protected entry, service nên dừng hoặc yêu cầu quy trình xử lý riêng thay vì âm thầm bỏ qua entry đó rồi vẫn xóa ancestor.

### 9.1. Không dùng filter quá rộng làm target xóa

Không xây filter từ input không tin cậy rồi dùng kết quả search làm danh sách xóa. DN root phải được xác định và kiểm tra theo policy server-side; filter search phải được parameterize/escape đúng cú pháp LDAP.

Nếu service cho phép xóa theo ou hoặc uid, hãy resolve identifier nghiệp vụ thành DN duy nhất, hiển thị preview và xác minh lại trước khi bắt đầu.

### 9.2. Naming context và ranh giới referral

Một subtree search có thể chạm tới referral hoặc naming context khác tùy cấu hình directory. Không giả định mọi entry hiển thị dưới một base đều có thể xóa bằng cùng một bind connection hoặc cùng server.

Với AD, referral có thể xuất hiện khi search đi qua naming context/domain boundary. Hãy xác minh scope và endpoint; đừng bật bỏ qua partial result rồi coi danh sách preview là đầy đủ nếu không có cơ chế xử lý referral khác.

## 10. Xử lý quyền và bảo vệ entry quan trọng

Bind identity phải có quyền xóa từng entry trong subtree. Quyền xóa parent không nhất thiết đồng nghĩa có quyền xóa mọi child nếu ACL khác nhau.

Các tình huống cần dự kiến:

- Service account có quyền xóa OU nhưng không có quyền xóa user con.
- Một entry được bảo vệ bằng ACL hoặc cờ bảo vệ đặc thù của server.
- Server từ chối xóa một object hệ thống hoặc object đang giữ vai trò hạ tầng.
- Có referral hoặc child ở naming context khác.
- Một entry con được tạo trong khi thao tác đang chạy.

Nên cấp quyền tối thiểu đúng phạm vi OU và chỉ dùng credential của service account qua TLS. Không nâng service account thành domain administrator chỉ để làm cho thao tác xóa chạy qua.

### 10.1. Cơ chế bảo vệ khỏi xóa nhầm

Một service xóa subtree có thể yêu cầu đồng thời:

1. Caller có role nghiệp vụ cho phép xóa OU.
2. Root DN thuộc allowlist naming context.
3. Preview count không vượt ngưỡng cấu hình.
4. Không có protected entry trong subtree.
5. Có plan ID hoặc confirmation token gắn với preview.
6. Snapshot được kiểm tra lại ngay trước khi xóa.

Nếu count thay đổi giữa preview và lúc thực hiện, yêu cầu preview lại hoặc dừng để người vận hành đánh giá. Không tiếp tục theo một plan đã cũ khi subtree đã thay đổi đáng kể.

## 11. Phối hợp writer và xử lý race condition

Ngay cả khi preview báo một OU có 20 descendants, một ứng dụng khác có thể thêm child thứ 21 trước khi xóa hoàn tất. Khi đó:

1. Service đã xóa một số leaf.
2. Writer khác thêm entry con mới.
3. Service tới bước xóa parent.
4. LDAP server trả notAllowedOnNonLeaf.

Đây không phải lỗi có thể sửa bằng cách retry riêng parent mãi mãi nếu writer vẫn tiếp tục tạo child.

Các cách phối hợp:

- Đưa OU vào trạng thái maintenance trong ứng dụng trước khi xóa.
- Chặn các API tạo entry mới bên dưới root.
- Dùng distributed lock theo root DN nếu nhiều instance service có thể cùng thao tác.
- Đặt giới hạn thời gian cho maintenance và giải phóng lock trong finally.
- Sau khi khóa writer, tạo lại preview hoặc xác minh số lượng entry trước khi xóa.

LDAP không cung cấp transaction bao trùm toàn bộ subtree delete tiêu chuẩn. Lock trong ứng dụng chỉ điều phối những writer tuân theo lock đó; nó không chặn quản trị viên hoặc ứng dụng bên ngoài directory. Nếu có writer ngoài hệ thống, cần maintenance window hoặc policy/ACL ở directory để khóa việc thêm child.

### 11.1. Hai lần xóa đồng thời trên cùng root

Nếu hai worker cùng xóa một subtree, chúng có thể cùng liệt kê child và một worker xóa entry trước worker còn lại. Worker thứ hai có thể nhận noSuchObject, hoặc lỗi do parent/child đã biến mất.

Không coi mọi noSuchObject là success một cách vô điều kiện. Chỉ chấp nhận trạng thái “đã xóa” khi service xác minh lại rằng entry mục tiêu và descendants trong phạm vi đã biến mất, và request hiện tại vẫn thuộc cùng plan/root identity.

### 11.2. Không giữ lock quá lâu mà thiếu timeout

Recursive deletion có thể chạy lâu. Lock phải có lease/timeout, heartbeat hoặc cơ chế phục hồi nếu process chết. Nếu lease hết hạn trong khi xóa vẫn đang chạy, writer có thể bắt đầu tạo child mới. Vì vậy, thời hạn lock phải được gia hạn khi thao tác tiến triển hoặc trạng thái maintenance phải được giữ bền vững cho đến khi reconciliation hoàn tất.
## 12. Xóa subtree không phải transaction nguyên tử

LDAP Delete operation áp dụng cho một entry. Khi ứng dụng xóa nhiều entry theo thứ tự, mỗi lần unbind là một operation riêng. Nếu operation thứ 5 thất bại, bốn entry đầu có thể đã bị xóa và các entry còn lại vẫn tồn tại.

Ví dụ:

~~~text
Kế hoạch:
uid=lan       -> success
uid=minh      -> success
uid=an        -> success
ou=platform   -> insufficientAccessRights
ou=engineering -> chưa thực hiện
~~~

Trạng thái thực tế sau lỗi:

~~~text
ou=engineering
├── uid=minh       (đã xóa)
├── uid=lan        (đã xóa)
└── ou=platform    (còn tồn tại)
    └── uid=an     (đã xóa)
~~~

Không có rollback tự động để tạo lại các entry đã xóa. Tạo lại entry có thể không khôi phục đầy đủ operational attributes, UUID, timestamps, ACL, password hash hoặc quan hệ do server quản lý.

Vì vậy, xóa subtree nên được thiết kế như một workflow có trạng thái, không coi nó là một lệnh CRUD đơn giản.

### 12.1. Lưu tiến độ và kết quả từng entry

Một record tiến độ có thể lưu:

~~~java
public record DeleteItemResult(
    LdapName dn,
    String status,
    String ldapErrorCode,
    String message
) {}
~~~

Các trạng thái ứng dụng gợi ý:

| Trạng thái | Ý nghĩa |
|---|---|
| PLANNED | Entry nằm trong snapshot cần xóa |
| DELETE_STARTED | Service đã bắt đầu gửi delete |
| DELETED | Server trả success hoặc đã xác minh entry biến mất |
| FAILED | Server trả lỗi xác định, entry vẫn tồn tại |
| OUTCOME_UNKNOWN | Kết nối mất trước khi nhận response; cần đọc lại trạng thái |
| SKIPPED | Entry bị loại khỏi phạm vi theo policy được phê duyệt |

Không lưu mật khẩu, secret hoặc toàn bộ attribute nhạy cảm trong journal. Chỉ lưu DN, plan ID, thời điểm, kết quả và correlation ID cần cho phục hồi.

## 13. Retry và reconciliation sau lỗi

Retry phải dựa trên trạng thái directory hiện tại. Không phát lại mù một danh sách delete cũ mà không xác minh entry nào đã biến mất.

Quy trình phục hồi:

1. Đọc lại root DN và kiểm tra root còn tồn tại không.
2. Nếu root còn, liệt kê subtree hiện tại từ server.
3. Đối chiếu danh sách hiện tại với plan/journal đã lưu.
4. Xác định entry đã xóa, còn tồn tại, hoặc không còn truy cập được.
5. Kiểm tra writer có tạo thêm child hay không.
6. Chạy lại thứ tự leaf-first trên phần còn tồn tại sau khi phê duyệt tiếp tục.
7. Khi hoàn tất, xác minh root và descendants không còn trong scope.
8. Đánh dấu plan hoàn thành, hoặc ghi rõ phần không thể xóa và nguyên nhân.

### 13.1. Phân biệt noSuchObject với thành công

Nếu request delete trả `noSuchObject`, có thể entry đã bị xóa bởi lần chạy trước hoặc bởi một actor khác. Nhưng cũng có thể DN sai, base DN không đúng hoặc entry đã bị move.

Chỉ đánh dấu DELETED sau khi service xác minh DN không còn ở vị trí dự kiến và đối chiếu đúng root/plan. Với hệ thống có audit requirement, ghi lại nguồn nào đã xóa entry nếu có thể xác định.

### 13.2. Mất kết nối sau khi gửi delete

Nếu client gửi DeleteRequest nhưng mất kết nối trước khi nhận DeleteResponse, kết quả operation là chưa biết. Server có thể đã xóa entry hoặc chưa xử lý request.

Hành vi an toàn:

- Không giả định request thất bại chỉ vì client timeout.
- Reconnect tới directory authority phù hợp.
- Lookup DN mục tiêu và kiểm tra parent/descendants.
- Nếu entry còn, xác minh identity và quyền trước khi retry.
- Nếu entry không còn, xác nhận trạng thái theo plan và tiếp tục phần còn lại.

Không retry một request subtree-control hoặc recursive workflow theo cách có thể mở rộng phạm vi ngoài plan ban đầu.

## 14. Xử lý các lỗi thường gặp

| Lỗi | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| `notAllowedOnNonLeaf` (66) | Parent vẫn còn child hoặc writer vừa tạo child | Liệt kê child hiện tại, xóa leaf-first, phối hợp writer |
| `noSuchObject` (32) | DN sai, entry đã xóa hoặc đã move | Xác minh DN/base và plan; không tự động bỏ qua |
| `insufficientAccessRights` (50) | ACL thiếu quyền xóa một entry trong subtree | Xác định DN bị từ chối và xin quyền tối thiểu phù hợp |
| `unwillingToPerform` (53) | Policy, object protection hoặc server constraint | Đọc diagnostic message, kiểm tra loại entry và policy |
| `adminLimitExceeded` (11) | Subtree-delete control vượt giới hạn server | Với AD tree-delete, xác minh partial progress rồi gửi lại theo hướng dẫn server |
| `referral` (10) | Entry thuộc naming context/server khác | Resolve referral hoặc xử lý theo endpoint có thẩm quyền |
| Timeout / connection reset | Không nhận được response | Reconnect và reconcile state trước khi retry |

Diagnostic message của LDAP server có thể chứa thông tin triển khai. Chỉ ghi log đã kiểm soát; không trả nguyên diagnostic string cho caller bên ngoài nếu nó tiết lộ DN nội bộ, hostname hoặc policy.

## 15. Ảnh hưởng tới tham chiếu và dữ liệu bên ngoài subtree

Xóa entry không đồng nghĩa mọi tham chiếu tới entry đó ở nơi khác sẽ tự được dọn sạch. LDAP schema có thể có attribute chứa DN như `member`, `manager`, `uniqueMember` hoặc thuộc tính custom. Hành vi referential integrity tùy server và cấu hình.

Trước khi xóa, xác định:

- Group nào đang chứa DN của user trong subtree.
- Entry nào trỏ tới manager/owner trong subtree.
- Ứng dụng nào lưu DN trong database, cache hoặc message.
- Có linked attributes hoặc referential-integrity plugin nào tự cập nhật/xóa reference không.
- Quan hệ nào phải được giữ audit history dù target entry đã biến mất.

Với Active Directory, một số linked attributes có semantics riêng và được server quản lý; không suy rộng hành vi đó sang mọi attribute DN-valued hoặc mọi LDAP server.

### 15.1. Thứ tự giữa việc gỡ reference và xóa entry

Nếu schema/server không tự xử lý reference, quy trình nghiệp vụ có thể cần:

1. Tìm các reference bên ngoài subtree.
2. Gỡ hoặc thay thế reference theo policy.
3. Xác minh không còn reference cản trở xóa.
4. Xóa subtree theo thứ tự leaf-first.
5. Cập nhật database/cache sau khi directory đã xác nhận kết quả.

Nếu reference là audit history, có thể giữ lại trong hệ thống nghiệp vụ dưới dạng stable identifier và trạng thái “directory object deleted”, thay vì xóa sạch lịch sử.

Không dùng `member` hoặc `manager` như một khóa ngoại database được đảm bảo có cascade-delete. LDAP server không mặc định triển khai cascade cho mọi thuộc tính.
## 16. Hiệu năng và giới hạn khi subtree lớn

Khi subtree có nhiều entry, chi phí không chỉ là số DeleteRequest. Còn có chi phí search/list, bind context, round trip, replication, ACL evaluation và cập nhật index của server.

Một số điểm cần đánh giá:

- **Count limit**: server có thể giới hạn số kết quả search trả về.
- **Time limit**: search hoặc thao tác có thể vượt thời gian cho phép.
- **Paging**: subtree snapshot lớn cần paged search để tránh mất kết quả do size limit.
- **Referral**: một phần subtree có thể thuộc naming context khác.
- **Connection lifetime**: recursive traversal giữ context mở trong thời gian dài.
- **Depth**: đệ quy sâu có thể tăng stack và làm thời gian xử lý khó dự đoán.
- **Replication**: các thao tác xóa lớn có thể tạo tải đáng kể cho replication topology.
- **Server policy**: một số entry có protection hoặc policy riêng.

Không bắt đầu xóa nếu bước preview bị cắt cụt do size limit hoặc partial result. Nếu không biết đầy đủ subtree, không thể bảo đảm thứ tự và phạm vi xóa.

### 16.1. Chia batch và checkpoint

Với subtree rất lớn, có thể chia công việc thành các batch leaf entries:

1. Tạo snapshot hoặc duyệt theo từng nhánh.
2. Ghi lại DN của batch cùng plan ID.
3. Xóa batch leaf entries.
4. Xác minh batch đã hoàn tất.
5. Ghi checkpoint bền vững.
6. Tiếp tục nhánh tiếp theo.
7. Chỉ xóa parent khi toàn bộ descendants đã được xác nhận biến mất.

Nếu dùng paging, cookie paging phải được xử lý đúng theo session/context và server. Không lưu một page cookie rồi dùng với một connection khác nếu implementation/server yêu cầu cookie gắn với session.

### 16.2. Khi nào nên dùng tree-delete control của AD?

Cân nhắc AD tree-delete control khi:

- Endpoint thực sự là Active Directory hỗ trợ OID.
- Root DN và phạm vi đã được preview/phê duyệt.
- Service account có quyền phù hợp.
- Đã tính đến giới hạn 16.384 object mỗi request.
- Đã có quy trình xử lý adminLimitExceeded và partial progress.
- Đã test trên phiên bản/domain policy tương ứng.

Nếu cần audit từng entry hoặc có quy tắc nghiệp vụ riêng cho từng child, client-side traversal có thể phù hợp hơn dù tốn nhiều round trip.

## 17. Thiết kế service xóa có trạng thái

Một service production nên tách bước lập kế hoạch, thực thi và xác minh:

~~~java
public interface SubtreeDeleteService {

    SubtreeDeletePlan preview(LdapName rootDn);

    SubtreeDeleteResult execute(
        SubtreeDeletePlan plan,
        DeleteApproval approval
    );

    SubtreeDeleteResult reconcile(String planId);
}
~~~

Các type trên là abstraction minh họa. Trạng thái plan có thể là:

~~~text
CREATED
  -> PREVIEWED
  -> APPROVED
  -> DELETING
  -> PARTIALLY_DELETED
  -> VERIFYING
  -> COMPLETED

Các nhánh lỗi:
  -> FAILED
  -> OUTCOME_UNKNOWN
  -> NEEDS_REVIEW
~~~

Quy tắc quan trọng:

- Plan gắn với root DN, directory endpoint, thời điểm preview và số lượng dự kiến.
- Approval gắn với plan cụ thể; không dùng approval cũ cho root khác.
- Nếu snapshot thay đổi đáng kể, chuyển NEEDS_REVIEW.
- Nếu có lỗi giữa chừng, lưu DN cuối cùng đã xử lý và lỗi tương ứng.
- Reconcile đọc trạng thái thực tế từ directory, không chỉ dựa vào journal.
- Chỉ đánh dấu COMPLETED khi xác minh toàn bộ phạm vi đã biến mất.

### 17.1. Không ghi journal trước rồi giả định thao tác chắc chắn xảy ra

Có thể ghi DELETE_STARTED trước khi gửi request, nhưng trạng thái này chỉ cho biết client chuẩn bị thực hiện. Nếu process chết ngay sau đó, entry có thể chưa bị xóa.

Sau khi nhận response success, ghi DELETED. Nếu không biết response có tới hay không, ghi OUTCOME_UNKNOWN rồi reconciliation.

Journal giúp khôi phục luồng điều khiển; directory mới là nguồn sự thật về entry còn tồn tại hay không.

## 18. Kiểm thử với LDAP directory

Unit test có thể kiểm tra thuật toán post-order bằng một cây giả lập, nhưng cần integration test để xác minh hành vi thật của server.

Một fixture mẫu:

~~~text
ou=delete-test,dc=example,dc=org
├── ou=team-a
│   ├── uid=lan
│   └── uid=minh
└── ou=team-b
    └── uid=an
~~~

Các test cần có:

1. Delete một leaf thành công.
2. Delete parent còn child trả notAllowedOnNonLeaf hoặc exception tương ứng.
3. Recursive unbind xóa toàn bộ descendants và root.
4. Xóa children-only giữ lại root.
5. Một child không đủ quyền làm thao tác dừng ở trạng thái partial.
6. Child được tạo đồng thời khiến xóa parent thất bại.
7. DN không tồn tại được xử lý theo policy idempotency.
8. Referral/size limit được phát hiện, không bị coi là snapshot đầy đủ.
9. Với AD, tree-delete control được test riêng trên AD test domain.
10. Sau khi hoàn tất, search lại root/subtree xác nhận không còn entry trong phạm vi.

### 18.1. Test thứ tự bằng fake directory

Với unit test, ghi lại thứ tự delete mà thuật toán phát ra:

~~~java
List<String> deleted = new ArrayList<>();

treeDeleter.delete(
    root,
    dn -> deleted.add(dn.toString())
);

assertThat(deleted).containsExactly(
    "uid=lan,ou=team-a,ou=delete-test,dc=example,dc=org",
    "uid=minh,ou=team-a,ou=delete-test,dc=example,dc=org",
    "ou=team-a,ou=delete-test,dc=example,dc=org",
    "uid=an,ou=team-b,ou=delete-test,dc=example,dc=org",
    "ou=team-b,ou=delete-test,dc=example,dc=org",
    "ou=delete-test,dc=example,dc=org"
);
~~~

Ví dụ giả định treeDeleter dùng thứ tự duyệt depth-first như fixture. Nếu implementation duyệt sibling theo thứ tự khác, assertion nên kiểm tra quan hệ bắt buộc: mỗi child phải xuất hiện trước parent của nó, thay vì khóa cứng toàn bộ thứ tự sibling.

### 18.2. Integration test phải tạo fixture riêng

Không dùng OU đang chứa dữ liệu thật làm test target. Tạo naming context/OU riêng có tiền tố test, thêm entry con, chạy thao tác xóa, rồi xác minh kết quả.

Dọn fixture trong finally hoặc test teardown; nếu test thất bại giữa chừng, teardown cần xóa phần còn lại theo leaf-first hoặc recursive helper.

## 19. Logging, audit và metrics

Xóa subtree là thao tác quản trị có tác động lớn. Audit event nên ghi:

- Plan ID và correlation ID.
- Root DN đã mask theo chính sách.
- Directory endpoint hoặc directory key.
- Bind identity/service account (không ghi credential).
- Số entry dự kiến và số entry đã xóa.
- Chiến lược xóa: manual, Spring recursive hoặc server control.
- Thời gian bắt đầu/kết thúc.
- Kết quả cuối và LDAP result code.
- Số entry còn lại sau reconciliation.
- Actor/approval tham chiếu.

Metrics có thể gồm:

- ldap_subtree_delete_entries_planned
- ldap_subtree_delete_entries_deleted
- ldap_subtree_delete_duration
- ldap_subtree_delete_failures
- ldap_subtree_delete_partial
- ldap_subtree_delete_reconcile_required

Không ghi toàn bộ attributes của entry vào log. DN có thể chứa tên người dùng, email hoặc dữ liệu tổ chức; mask hoặc hash theo policy nếu không cần lưu nguyên văn.

## 20. Checklist trước khi đưa vào production

| Kiểm tra | Tiêu chí |
|---|---|
| Đúng root DN? | Đã resolve và xác minh naming context |
| Đúng phạm vi? | Preview bao gồm đúng descendants và root theo yêu cầu |
| Có phân biệt giữ root/xóa root? | API method diễn đạt rõ semantics |
| Đúng thứ tự? | Leaf/deepest entries được xóa trước ancestor |
| Snapshot đầy đủ? | Không có size limit/referral/partial result chưa xử lý |
| Có phối hợp writer? | Chặn hoặc điều phối tạo child mới |
| Đủ quyền? | Service account có quyền xóa đúng entries |
| Có protected entries? | Đã kiểm tra policy và ngoại lệ |
| Có reference bên ngoài? | Đã đánh giá member/manager và dữ liệu ứng dụng |
| Có xử lý partial failure? | Journal, retry và reconciliation |
| Có xử lý timeout? | Outcome unknown được xác minh trước retry |
| Có giới hạn subtree? | Count, depth, time và batch limits rõ ràng |
| Dùng AD tree-delete? | Đã xác minh OID, quyền và giới hạn server |
| Có integration test? | Test trên cùng loại directory server |
| Có audit? | Plan ID, actor, result code và số lượng |
| Có rollback plan? | Có backup/export/restore hoặc quy trình phục hồi phù hợp |

## 21. Bài tập thực hành

### Bài 1 — Vì sao parent không xóa được?

Tạo OU có hai user con. Gọi `unbind(parentDn)` và quan sát exception/result code. Giải thích ý nghĩa `notAllowedOnNonLeaf` (66).

### Bài 2 — Thiết kế post-order

Cho cây có bốn tầng và nhiều sibling. Viết thứ tự xóa hợp lệ, giải thích vì sao mọi child phải được xóa trước parent.

### Bài 3 — Giữ root lại

Viết method xóa toàn bộ descendants của một OU nhưng giữ OU đó. So sánh với `unbind(rootDn, true)`.

### Bài 4 — Recursive unbind và tree-delete control

So sánh Spring recursive unbind với AD tree-delete control theo số request, phạm vi hỗ trợ, audit và partial failure.

### Bài 5 — Concurrent writer

Trong lúc service xóa subtree, một request khác tạo child mới. Giải thích vì sao parent delete thất bại và đề xuất cách điều phối writer.

### Bài 6 — Retry sau timeout

Client mất kết nối ngay sau khi gửi delete. Thiết kế bước reconciliation để xác định entry đã bị xóa hay chưa trước khi retry.

### Bài 7 — Subtree lớn hơn giới hạn AD

Một AD tree-delete request vượt giới hạn object. Giải thích adminLimitExceeded, partial progress và cách tiếp tục mà không mở rộng phạm vi xóa.

### Bài 8 — Tham chiếu từ group

Một group ngoài subtree có member DN trỏ tới user sắp bị xóa. Xác minh server có referential-integrity behavior nào và quyết định thứ tự xử lý.

### Bài 9 — Preview bị thiếu kết quả

Search preview bị size limit hoặc referral. Vì sao không được bắt đầu xóa theo danh sách hiện có? Thiết kế cách paging/resolve referral.

### Bài 10 — Audit và phục hồi

Thiết kế journal cho một lần xóa subtree có thể kéo dài nhiều phút. Xác định các trạng thái, checkpoint và điều kiện COMPLETED.

## 22. Kết luận và tài liệu tham khảo

LDAP DeleteRequest tiêu chuẩn chỉ xóa entry lá. Khi xóa một entry có con, phải xóa descendants theo thứ tự từ sâu nhất lên root, hoặc dùng một subtree-delete control mà directory server cụ thể hỗ trợ.

Spring LDAP cung cấp LdapTemplate.unbind(dn, true) để xóa root cùng descendants bằng cơ chế recursive phía client. Cơ chế này hữu ích nhưng không tạo transaction nguyên tử cho toàn subtree. Với Active Directory, LDAP_SERVER_TREE_DELETE_OID có thể thực hiện tree-delete phía server, nhưng là extension riêng của AD và có giới hạn/partial progress cần xử lý.

Thiết kế production cần preview đầy đủ, xác minh quyền và phạm vi, phối hợp writer, lưu tiến độ, xử lý lỗi từng entry và reconciliation sau timeout. Phải phân biệt rõ xóa root cùng descendants với xóa descendants nhưng giữ root; đồng thời đánh giá tham chiếu DN từ bên ngoài subtree trước khi thực hiện.

Tài liệu chính thức:

- [RFC 4511 — LDAPv3, `4.8 Delete Operation](https://www.rfc-editor.org/rfc/rfc4511#section-4.8)
- [RFC 4511 — LDAP Result Codes](https://www.rfc-editor.org/rfc/rfc4511#section-4.1.9)
- [Spring LDAP — LdapOperations API](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/LdapOperations.html)
- [Spring LDAP — LdapTemplate API](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/LdapTemplate.html)
- [Spring LDAP — ContextExecutor API](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/ContextExecutor.html)
- [Java SE 17 — DirContext API](https://docs.oracle.com/en/java/javase/17/docs/api/java.naming/javax/naming/directory/DirContext.html)
- [Microsoft — LDAP_SERVER_TREE_DELETE_OID](https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-adts/b8ee2305-b0eb-41be-894f-b94b5d29ca9e)
- [Microsoft — Tree-delete Operation](https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-adts/12616f59-c05d-4b4e-8026-2a65db152342)
- [Microsoft — LDAP_SERVER_TREE_DELETE_OID control code](https://learn.microsoft.com/en-us/previous-versions/windows/desktop/ldap/ldap-server-tree-delete-oid)
