# SearchControls và việc chọn scope

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt ba phạm vi tìm kiếm LDAP: **base object**, **single level** và **whole subtree**; ánh xạ chúng với các hằng của JNDI `SearchControls`.
- Xác định chính xác entry nào có thể được xét khi thay đổi **search base**, **search scope** và **LDAP filter**.
- Dùng `javax.naming.directory.SearchControls` cùng `LdapTemplate` trong Spring LDAP để kiểm soát scope, số kết quả, thời gian tìm kiếm và thuộc tính cần trả về.
- Nhận diện lỗi bỏ sót người dùng trong OU lồng nhau, tìm kiếm quá rộng, nhân đôi base DN và dùng nhầm scope trong xác thực hoặc tra cứu nhóm.
- Hiểu giới hạn của `countLimit`, `timeLimit` và phân trang; đánh giá đúng hiệu năng, quyền truy cập, TLS/pooling và kết quả kiểm thử.

Bài thuộc chương **Search scope** trong module **SPRING_LDAP**. Module sử dụng các thành phần như `ContextSource`, `LdapTemplate`, `LdapClient` và ODM để làm việc với directory. Trong số đó, **`SearchControls` là đối tượng chuẩn JNDI** dùng mô tả cách thực hiện một thao tác tìm kiếm, đặc biệt là phạm vi mà LDAP server cần xét.

## 1. Tìm kiếm LDAP luôn có ba quyết định độc lập

Một yêu cầu LDAP search không chỉ có filter. Về mặt khái niệm, bạn phải xác định:

1. **Search base**: DN của entry làm gốc tìm kiếm, chẳng hạn `ou=people,dc=example,dc=org`.
2. **Search scope**: chỉ entry tại base, chỉ con trực tiếp, hay toàn bộ cây con tính từ base.
3. **Search filter**: các entry trong phạm vi đó phải thỏa điều kiện nào, ví dụ `(objectClass=inetOrgPerson)`.

Search base định vị **chỗ bắt đầu**; scope chọn **độ sâu được xét**; filter chọn **entry đủ điều kiện**. Ngoài ba yếu tố này còn có giới hạn thời gian/số kết quả và danh sách thuộc tính cần trả về.

~~~mermaid
flowchart LR
    Base["Search base<br/>ou=people,dc=example,dc=org"]
    Scope["Search scope<br/>OBJECT / ONELEVEL / SUBTREE"]
    Filter["LDAP filter<br/>(objectClass=inetOrgPerson)"]
    Results["Kết quả tìm kiếm"]
    Base --> Scope --> Filter --> Results
~~~

Việc dùng filter chọn lọc không thể bù cho scope bị chọn sai. Nếu entry nằm ngoài scope, server sẽ không xét entry đó dù mọi thuộc tính của nó đều khớp filter.

## 2. Cây thư mục ví dụ

Xét LDAP directory minh họa:

~~~text
dc=example,dc=org
├── ou=people
│   ├── uid=an
│   ├── uid=binh
│   └── ou=engineering
│       └── uid=chi
└── ou=groups
    └── cn=developers
~~~

DN đầy đủ của các entry tương ứng là:

~~~text
dc=example,dc=org
ou=people,dc=example,dc=org
uid=an,ou=people,dc=example,dc=org
uid=binh,ou=people,dc=example,dc=org
ou=engineering,ou=people,dc=example,dc=org
uid=chi,ou=engineering,ou=people,dc=example,dc=org
ou=groups,dc=example,dc=org
cn=developers,ou=groups,dc=example,dc=org
~~~

Giả sử:

- `ou=people` và `ou=engineering` có `objectClass=organizationalUnit`.
- `uid=an`, `uid=binh` và `uid=chi` có `objectClass=inetOrgPerson`.
- `ou=groups` chứa entry nhóm `cn=developers`.

Đặt **search base** là:

~~~text
ou=people,dc=example,dc=org
~~~

Với cùng filter `(objectClass=*)`, ba scope tạo phạm vi ứng viên sau:

| Scope | Entry có thể được xét dưới base `ou=people` | Có xét chính base? | Có xét các OU con nhiều cấp? |
| --- | --- | --- | --- |
| **OBJECT** | `ou=people` | Có | Không |
| **ONELEVEL** | `uid=an`, `uid=binh`, `ou=engineering` | Không | Không; chỉ con trực tiếp |
| **SUBTREE** | `ou=people`, `uid=an`, `uid=binh`, `ou=engineering`, `uid=chi` | Có | Có |

Entry `cn=developers,ou=groups,...` **không nằm dưới search base** nên không được xét ở bất kỳ scope nào trong bảng.

Nếu đổi filter thành `(objectClass=inetOrgPerson)` nhưng **giữ base** như trên:

| Scope | Kết quả theo dữ liệu ví dụ | Giải thích |
| --- | --- | --- |
| OBJECT | Không có entry | `ou=people` là organizational unit, không phải person |
| ONELEVEL | `uid=an`, `uid=binh` | Hai người dùng là con trực tiếp |
| SUBTREE | `uid=an`, `uid=binh`, `uid=chi` | Bao gồm nhân viên trong `ou=engineering` |

Đây là ví dụ quan trọng nhất: **ONELEVEL bỏ sót `uid=chi` dù filter đúng**. Không phải vì filter xử lý `uid=chi` sai, mà vì entry này nằm sâu hơn một cấp so với base.

## 3. Ba search scope theo LDAP và JNDI

### 3.1. OBJECT_SCOPE: chỉ entry tại search base

Trong LDAP protocol (RFC 4511), scope `baseObject` yêu cầu kiểm tra chính entry được chỉ định bởi search base. Trong Java JNDI:

~~~java
SearchControls controls = new SearchControls();
controls.setSearchScope(SearchControls.OBJECT_SCOPE);
~~~

Ví dụ search base `uid=an,ou=people,dc=example,dc=org` và filter `(objectClass=inetOrgPerson)`: server chỉ đánh giá entry `uid=an`.

**Dùng khi:**

- Bạn đã biết DN cụ thể, muốn kiểm tra một điều kiện trên chính entry đó.
- Bạn muốn lấy một số thuộc tính của entry đã xác định, thông qua LDAP search thay vì một thao tác lookup khác.
- Bạn kiểm tra entry tại base có đáp ứng filter hay không.

Với tác vụ **chỉ cần đọc entry đã biết DN**, `LdapTemplate.lookup(...)` thường trực tiếp và dễ hiểu hơn. `OBJECT_SCOPE` hữu ích khi bạn vẫn cần áp dụng một LDAP filter lên entry đó.

OBJECT không có nghĩa “trả về đúng một kết quả” bất kể filter: nếu entry tại base không khớp filter thì kết quả là **0 entry**. Nếu DN của base không tồn tại hoặc người dùng không có quyền truy cập thích hợp, server có thể trả lỗi hoặc phản hồi chịu ảnh hưởng ACL; không nên tự động coi mọi tình huống là “không khớp”.

### 3.2. ONELEVEL_SCOPE: chỉ các entry con trực tiếp

LDAP protocol gọi scope này là `singleLevel`. Trong JNDI:

~~~java
controls.setSearchScope(SearchControls.ONELEVEL_SCOPE);
~~~

Với base `ou=people`, ONELEVEL xét `uid=an`, `uid=binh` và `ou=engineering`. Nó **không xét** chính `ou=people` hoặc `uid=chi` nằm bên trong `ou=engineering`.

**Dùng khi:**

- Dữ liệu được tổ chức **phẳng**, chẳng hạn mọi nhân viên đặt trực tiếp trong `ou=people`.
- Bạn chỉ cần liệt kê các OU con, nhóm con hoặc entry con trực tiếp.
- Bạn muốn giữ phạm vi nhỏ và có bằng chứng về cấu trúc directory.

Đừng mặc định ONELEVEL là “tìm tất cả nhân viên”. Nhiều directory phân người dùng thành `ou=engineering`, `ou=finance`, `ou=hr`, hoặc các nhánh theo địa điểm; ONELEVEL ở cấp `ou=people` có thể trả **thiếu người dùng**.

### 3.3. SUBTREE_SCOPE: base và mọi entry hậu duệ

LDAP protocol gọi là `wholeSubtree`. Trong JNDI:

~~~java
controls.setSearchScope(SearchControls.SUBTREE_SCOPE);
~~~

Với base `ou=people`, SUBTREE xét `ou=people`, các con trực tiếp và mọi cấp phía dưới. Nó bao gồm `uid=chi` nằm trong `ou=engineering`.

**Dùng khi:**

- Người dùng/nhóm được tổ chức trong nhiều OU con.
- Yêu cầu nghiệp vụ là tìm trên cả một cây con.
- Bạn chưa thể bảo đảm dữ liệu nằm đúng một cấp cố định và cần bao phủ toàn bộ nhánh hợp lệ.

SUBTREE trên một base quá cao (ví dụ toàn `dc=example,dc=org`) có thể chạm tới rất nhiều entry, kéo theo chi phí index, CPU, I/O, ACL, băng thông và cấp phát đối tượng. Tuy nhiên **SUBTREE không tự động đồng nghĩa với full scan**: server có thể sử dụng chỉ mục để thu hẹp tập ứng viên theo filter.

## 4. SearchControls: đối tượng chứa các tùy chọn tìm kiếm

`SearchControls` nằm trong gói Java:

~~~java
import javax.naming.directory.SearchControls;
~~~

Đây là một lớp **JNDI chuẩn**, không phải lớp chỉ có trong Spring LDAP. Những phương thức quan trọng gồm:

| Tùy chọn | API JNDI | Ý nghĩa |
| --- | --- | --- |
| Scope | `setSearchScope(int)` | `OBJECT_SCOPE`, `ONELEVEL_SCOPE` hoặc `SUBTREE_SCOPE` |
| Giới hạn entry | `setCountLimit(long)` | Giới hạn số entry trả về theo yêu cầu client |
| Giới hạn thời gian | `setTimeLimit(int)` | Thời gian tối đa cho thao tác search theo JNDI, tính bằng mili giây |
| Thuộc tính trả về | `setReturningAttributes(String[])` | Chỉ yêu cầu các thuộc tính ứng dụng cần |
| Trả về đối tượng | `setReturningObjFlag(boolean)` | Liên quan cách JNDI trả về object gắn với entry; không phải kiểm soát schema/filter |
| Dereference link JNDI | `setDerefLinkFlag(boolean)` | Cách xử lý JNDI link, không nên nhầm với mọi cơ chế LDAP alias/referral |

### 4.1. Ví dụ cấu hình rõ ràng

~~~java
import javax.naming.directory.SearchControls;

SearchControls controls = new SearchControls();
controls.setSearchScope(SearchControls.SUBTREE_SCOPE);
controls.setCountLimit(100);
controls.setTimeLimit(2_000); // mili giây
controls.setReturningAttributes(new String[] {
    "uid", "cn", "mail"
});
~~~

Ý nghĩa:

- Tìm từ base và qua các OU con.
- Yêu cầu trả tối đa 100 entry cho lần search này.
- Yêu cầu giới hạn thời gian tìm kiếm là 2.000 ms.
- Chỉ lấy `uid`, `cn` và `mail`, thay vì mọi thuộc tính mặc định của kết quả.

Khi kết quả của một truy vấn có hàng nghìn entry, giảm số thuộc tính có thể tiết kiệm đáng kể dữ liệu truyền qua mạng và khối lượng mapping trong Java.

### 4.2. Mặc định cần biết, nhưng nên đặt rõ

Với constructor mặc định `new SearchControls()`, JNDI đặt **ONELEVEL_SCOPE**, `countLimit = 0` và `timeLimit = 0`; hai giá trị giới hạn bằng 0 biểu thị không yêu cầu giới hạn tương ứng ở phía client. `returningAttributes = null` yêu cầu tập thuộc tính mặc định (thông thường là các user attributes theo ngữ nghĩa LDAP); thuộc tính vận hành (*operational attributes*) không nhất thiết được trả về tự động.

Vì vậy, không nên suy từ việc filter giống nhau rằng các lần search sẽ bao phủ cùng cây nếu nơi này dùng `new SearchControls()` còn nơi khác đặt `SUBTREE_SCOPE`.

**Thực hành tốt:** ghi rõ scope trong code khi ý nghĩa nghiệp vụ phụ thuộc vào nó, thay vì dựa vào giá trị mặc định.

### 4.3. `null` và mảng rỗng ở returningAttributes không giống nhau

~~~java
controls.setReturningAttributes(null);
~~~

Thường thể hiện yêu cầu nhận tập thuộc tính mặc định của server/provider.

~~~java
controls.setReturningAttributes(new String[0]);
~~~

Yêu cầu **không trả về thuộc tính** ở kết quả (theo contract JNDI), dù entry vẫn có thể được trả về nếu khớp filter.

~~~java
controls.setReturningAttributes(new String[] {"uid", "cn"});
~~~

Chỉ yêu cầu hai attribute description này. Nếu mapper của bạn đọc `mail` trong khi không yêu cầu `mail`, có thể gặp `null` ở `attrs.get("mail")`. Danh sách thuộc tính trả về phải khớp dữ liệu mapper thực sự sử dụng.

Lưu ý: một số LDAP server có quy tắc riêng về operational attributes, ACL và attribute options. `returningAttributes` không vượt qua ACL đọc; yêu cầu một attribute không đồng nghĩa server chắc chắn trả nó về.

### 4.4. Giới hạn không phải bảo đảm kết quả “đủ”

`setCountLimit(100)` không có nghĩa **toàn directory chỉ có tối đa 100 entry khớp**. Nó chỉ là giới hạn trả về theo yêu cầu tìm kiếm. Giới hạn từ server hoặc chính sách ACL có thể khiến kết quả ít hơn. Khi vượt giới hạn, JNDI/Spring LDAP có thể phát sinh ngoại lệ tương ứng hoặc phản hồi một phần tùy máy chủ/provider.

`setTimeLimit(2_000)` cũng không biến một filter tốn kém thành filter nhanh: khi quá hạn, thao tác có thể bị cắt hoặc phát sinh `TimeLimitExceededException`. Timeout kết nối TCP, TLS handshake, timeout đọc dữ liệu, server-side time limit và JNDI search time limit là **các loại giới hạn khác nhau**.

Không được diễn giải “mảng trả về rỗng” hay “chỉ trả 100 kết quả” thành kết luận rằng server không còn entry phù hợp.

## 5. Spring LDAP: áp dụng SearchControls qua LdapTemplate

Spring LDAP bọc thao tác JNDI để quản lý context, mapping kết quả và xử lý lỗi. API phổ biến:

~~~java
ldapTemplate.search(
    "ou=people",             // Search base tương đối
    "(objectClass=inetOrgPerson)",
    controls,
    mapper
);
~~~

Để minh họa đầy đủ, giả sử ứng dụng cấu hình `ContextSource` với base `dc=example,dc=org` và có quyền tra cứu directory:

~~~yaml
spring:
  ldap:
    urls: ldaps://ldap.example.org:636
    base: dc=example,dc=org
    username: uid=directory-reader,ou=services,dc=example,dc=org
    # spring.ldap.password được cấp từ hệ thống quản lý secret.
~~~

Với base này, `"ou=people"` trong `LdapTemplate.search(...)` là DN **tương đối với** `dc=example,dc=org`; thao tác thực tế nhắm đến `ou=people,dc=example,dc=org`.

### 5.1. Dịch vụ tra cứu có scope xác định

~~~java
import java.util.List;
import javax.naming.directory.Attribute;
import javax.naming.directory.SearchControls;

import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.filter.EqualsFilter;
import org.springframework.stereotype.Service;

@Service
public class DirectorySearchService {
    private final LdapTemplate ldapTemplate;

    public DirectorySearchService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public record PersonView(String uid, String commonName) {}

    public List<PersonView> findPeopleByUidInSubtree(String uid) {
        SearchControls controls = new SearchControls();
        controls.setSearchScope(SearchControls.SUBTREE_SCOPE);
        controls.setCountLimit(50);
        controls.setTimeLimit(2_000);
        controls.setReturningAttributes(new String[] {"uid", "cn"});

        String filter = new EqualsFilter("uid", uid).encode();

        return ldapTemplate.search(
            "ou=people",
            filter,
            controls,
            (AttributesMapper<PersonView>) attributes -> {
                Attribute uidAttr = attributes.get("uid");
                Attribute cnAttr = attributes.get("cn");
                if (uidAttr == null || cnAttr == null) {
                    throw new IllegalStateException(
                        "LDAP entry thiếu thuộc tính uid hoặc cn"
                    );
                }
                return new PersonView(
                    (String) uidAttr.get(),
                    (String) cnAttr.get()
                );
            }
        );
    }
}
~~~

Trong ví dụ:

- `SUBTREE_SCOPE` bao phủ cả người dùng ở `ou=engineering` bên dưới `ou=people`.
- `EqualsFilter` mã hóa giá trị `uid` đầu vào theo cú pháp LDAP filter. Đây là **equality**, không biến ký tự `*` trong `uid` thành wildcard.
- `setReturningAttributes` cung cấp chính hai thuộc tính mà mapper sử dụng.
- `setCountLimit` và `setTimeLimit` là giới hạn bảo vệ tài nguyên, không bảo đảm duy nhất hoặc đầy đủ.
- Nếu server không cung cấp `uid` hoặc `cn` do schema/ACL, mapper báo lỗi rõ; trong ứng dụng thực có thể thiết kế kiểu kết quả cho phép thiếu thuộc tính theo yêu cầu nghiệp vụ.

Với directory chuẩn, việc tìm `uid` dùng một định danh có thể bị trùng nếu không có ràng buộc uniqueness; code trả danh sách vì **không tự mặc định** tìm được đúng một người.

### 5.2. Nếu thay scope mà không đổi filter

Giữ nguyên phương thức trên và thay:

~~~java
controls.setSearchScope(SearchControls.ONELEVEL_SCOPE);
~~~

Bây giờ `uid=chi` trong OU lồng nhau sẽ không được tìm thấy khi base là `ou=people`, dù filter `(uid=chi)` chính xác và tài khoản dịch vụ có quyền đọc entry đó. Đây là lỗi rất thường gặp khi cấu trúc LDAP được mở rộng thêm các OU con mà code vẫn giả định người dùng nằm ở một cấp.

Nếu thực sự chỉ cần kiểm tra một DN đã biết, có thể sử dụng:

~~~java
controls.setSearchScope(SearchControls.OBJECT_SCOPE);
~~~

và chuyển search base thành DN của entry cụ thể, tương đối với base của `ContextSource`. Khi đã biết DN và không cần filter, cân nhắc `ldapTemplate.lookup(...)` để diễn đạt ý định rõ ràng hơn.

### 5.3. Cấu hình bằng LdapQueryBuilder: không nhầm với SearchControls

Spring LDAP cũng có API truy vấn như `LdapQueryBuilder` để tạo điều kiện tìm kiếm và tùy chọn truy vấn. Tùy phiên bản, builder cung cấp cách đặt search base, search scope, giới hạn và attributes. Nếu chọn API đó, nên giữ chung **một nơi quản lý phạm vi tìm kiếm** để tránh khác biệt giữa các lời gọi.

`SearchControls` vẫn là khái niệm gốc cần hiểu vì nó xuất hiện trong JNDI và các overload của `LdapTemplate.search(...)`. `LdapClient` dùng kiểu fluent; cần kiểm tra API của phiên bản đang dùng để đặt scope/attributes/controls, thay vì mặc định mọi lời gọi search đều dùng cùng scope với JNDI.

## 6. Search base và scope là hai trục khác nhau

Một câu hỏi phổ biến: “Nếu đã dùng SUBTREE, có cần đặt base đúng không?” **Có**. SUBTREE chỉ duyệt cây **bên dưới base đã chọn**.

Với cấu hình `ContextSource.base = dc=example,dc=org`:

| Base truyền vào Spring LDAP | Scope | Phạm vi ý định |
| --- | --- | --- |
| `ou=people` | OBJECT | Chỉ entry `ou=people` |
| `ou=people` | ONELEVEL | Các entry con trực tiếp của `ou=people` |
| `ou=people` | SUBTREE | `ou=people` và toàn bộ hậu duệ |
| `ou=engineering,ou=people` | SUBTREE | Chỉ cây con kỹ thuật |
| `ou=groups` | SUBTREE | Nhánh nhóm, không bao gồm `ou=people` |
| `""` | SUBTREE | Cây con của **base cấu hình** `dc=example,dc=org`; có thể rất rộng |

Nếu truyền `ou=people,dc=example,dc=org` vào API đang yêu cầu tên tương đối với `dc=example,dc=org`, ứng dụng có thể tạo đường dẫn bị **nhân đôi base**. Phải phân biệt DN đầy đủ với DN tương đối, nhất là khi có nhiều `ContextSource`.

**Không được tự động dùng `""` làm base để “tìm cho đủ”** trong mọi trường hợp. Điều này có thể chuyển từ phạm vi vài trăm entry sang hàng trăm nghìn entry, làm tăng độ trễ và diện tích dữ liệu có thể bị truy cập.

## 7. Chọn scope theo yêu cầu nghiệp vụ

| Yêu cầu | Search base gợi ý | Scope gợi ý | Lưu ý |
| --- | --- | --- | --- |
| Kiểm tra một entry có DN xác định | DN của entry | OBJECT | Có thể dùng `lookup` nếu không cần filter |
| Liệt kê các OU con trực tiếp | DN của OU cha | ONELEVEL | Kết hợp filter `(objectClass=organizationalUnit)` |
| Liệt kê nhân viên trong OU phẳng | `ou=people` | ONELEVEL | Chỉ đúng khi mọi người dùng là con trực tiếp |
| Tìm nhân viên trong nhiều OU lồng nhau | `ou=people` | SUBTREE | Dùng filter chọn lọc và giới hạn phù hợp |
| Tìm trong một phòng ban | `ou=engineering,ou=people` | ONELEVEL hoặc SUBTREE | Chọn theo cấu trúc phòng ban thực |
| Tra cứu nhóm ứng dụng | `ou=groups` | ONELEVEL hoặc SUBTREE | Không đặt nhầm base ở `ou=people` |
| Tìm tất cả entry thuộc tổ chức | `dc=example,dc=org` | SUBTREE | Cần kiểm soát tải, quyền, filter và phân trang |

**Nguyên tắc lựa chọn:** bắt đầu từ **nhánh nhỏ nhất bao phủ tập dữ liệu cần tìm**, sau đó chọn scope thấp nhất vẫn phản ánh đúng cấu trúc. Nếu người dùng có thể nằm sâu trong nhiều OU con, SUBTREE là lựa chọn chức năng đúng; khi đó phải tối ưu filter, index và giới hạn thay vì cố ép ONELEVEL để “chạy nhanh”.

### 7.1. ONELEVEL nhanh hơn SUBTREE?

Không thể kết luận chỉ từ scope. ONELEVEL thường xét vùng nhỏ hơn nếu các điều kiện khác giống nhau, nhưng có thể:

- **Bỏ sót** entry nằm sâu hơn.
- Vẫn chậm nếu một OU có số lượng con trực tiếp rất lớn và filter không có chỉ mục hữu ích.
- Trả kết quả không đầy đủ do ACL hoặc server limit.

SUBTREE có thể hoạt động hiệu quả khi search base đã hẹp, filter có độ chọn lọc cao và server có index phù hợp. Các cơ chế index, cache, cấu trúc backend và giới hạn của server thực tế ảnh hưởng đáng kể tới thời gian truy vấn.

### 7.2. Filter được áp dụng sau khi xác định phạm vi xét

Về ý nghĩa logic, server chỉ trả entry vừa **nằm trong scope** vừa **khớp filter** và được phép thấy theo ACL. Một số server tối ưu thứ tự xử lý bằng index; đó là chi tiết triển khai, không làm thay đổi kết quả cần trả về theo ngữ nghĩa giao thức.

Ví dụ:

~~~ldap
(&(objectClass=inetOrgPerson)(uid=chi))
~~~

Nếu base `ou=people` và scope ONELEVEL, filter này không tìm được `uid=chi,ou=engineering,ou=people,...`. Nếu dùng SUBTREE và tài khoản có quyền phù hợp, entry có thể được tìm thấy.

Thêm `(uid=chi)` cho filter không làm server tự động “đi xuống thêm một cấp”.

## 8. SearchControls và quyền truy cập: ranh giới cần giữ

Search scope quyết định **vùng được yêu cầu duyệt**, còn LDAP Access Control List (ACL) quyết định **entry và thuộc tính nào được phép đọc/tìm kiếm**. Hai việc không thay thế nhau.

Ví dụ:

- Một `ContextSource` dùng tài khoản dịch vụ chỉ có quyền đọc `ou=people`.
- Filter với SUBTREE bao phủ cả `ou=engineering`.
- Server có thể không cho xem một số entry hoặc thuộc tính bên trong `ou=engineering`.

Kết quả ít hơn dự kiến có thể do ACL, filter, schema, base/scope hoặc dữ liệu thực tế. Không tự kết luận rằng người dùng không tồn tại chỉ vì một search trả danh sách rỗng.

Đối với xác thực, Spring Security LDAP có thể dùng **user search base** và **group search base** khác nhau. Ví dụ user tìm dưới `ou=people`, trong khi group ở `ou=groups`. Dùng SUBTREE ở `ou=people` không thể tìm các group nằm ở nhánh `ou=groups` vì group không phải hậu duệ của base đó.

**Tồn tại entry không chứng minh mật khẩu đúng.** Bind authentication và quá trình map nhóm/quyền thuộc luồng Spring Security LDAP; không dùng kết quả search trên thuộc tính hiển thị như `cn` để tự cấp quyền.

## 9. Giới hạn thời gian, kích thước và dữ liệu trả về

### 9.1. Search scope rộng có thể tăng chi phí

Chi phí tìm kiếm chịu ảnh hưởng của:

- Số entry nằm trong phạm vi.
- Độ chọn lọc của LDAP filter và chỉ mục (equality, substring, presence...) được server dùng.
- Số entry/attribute trả về, kích thước dữ liệu và lượng băng thông.
- Tải đồng thời, cache, hệ thống lưu trữ và ACL kiểm tra trên server.
- Kết nối mạng, LDAPS/StartTLS, connection pooling và việc dựng/mapping object trong Java.

Vì vậy, tăng `countLimit` hoặc chuyển từ ONELEVEL sang SUBTREE cần được đánh giá trong bối cảnh thực. Server có thể áp đặt giới hạn tối đa nhỏ hơn client mong muốn.

### 9.2. Count limit không phải phân trang

~~~java
controls.setCountLimit(100);
~~~

Giới hạn này không cung cấp một “trang tiếp theo”. Nếu người dùng cần duyệt toàn bộ danh bạ lớn, hãy xem cơ chế **LDAP Simple Paged Results** (RFC 2696) hoặc API phân trang phù hợp, tùy khả năng server/provider. Đừng suy rằng chỉ cần tăng `countLimit` vô hạn là giải pháp an toàn.

Paging chủ yếu quản lý cách nhận kết quả; nó không tự sửa filter kém chọn lọc, search base quá cao hay thiếu index.

### 9.3. Xử lý trường hợp bị giới hạn

Spring LDAP chuyển đổi nhiều ngoại lệ JNDI sang hệ thống ngoại lệ của Spring LDAP. Khi có time/size limit hoặc lỗi mạng, code phải xác định rõ hợp đồng nghiệp vụ:

- Với màn hình gợi ý: có thể báo “kết quả bị giới hạn”, trả số lượng hữu ích trong giới hạn đã thiết kế, hoặc yêu cầu thu hẹp điều kiện.
- Với nghiệp vụ đồng bộ: không nên ghi nhận “đồng bộ thành công” khi chỉ nhận một phần dữ liệu.
- Với xác thực/phân quyền: không bỏ qua lỗi để tự động cấp quyền rộng hơn.

Không dùng `catch (Exception e) { return List.of(); }` cho mọi lỗi, vì sẽ biến timeout, lỗi ACL và lỗi cấu hình thành kết quả “không có người dùng”, làm sai hành vi ứng dụng và che giấu sự cố.

## 10. Những lỗi dùng SearchControls thường gặp

| Lỗi | Biểu hiện | Cách xử lý |
| --- | --- | --- |
| Dùng mặc định ONELEVEL để tìm user phân tán nhiều OU | Một số nhân viên biến mất khỏi kết quả | Cấu hình SUBTREE trên base phù hợp |
| Dùng SUBTREE từ base quá cao | Tăng độ trễ, trả nhiều entry không liên quan | Thu hẹp search base và filter |
| Nghĩ OBJECT_SCOPE kiểm tra con trực tiếp | Trả 0 entry dù có nhiều con | Chuyển sang ONELEVEL hoặc đổi base |
| Nghĩ ONELEVEL bao gồm chính base | Không thấy entry OU gốc | Dùng OBJECT cho base hoặc SUBTREE khi cần cả hai |
| Ghép full DN vào API nhận relative DN | Có thể sinh đường dẫn nhân đôi base | Kiểm tra `ContextSource.base` và cách API diễn giải DN |
| Chỉ đặt filter nhưng quên scope | Phụ thuộc scope mặc định của JNDI hoặc API đang dùng | Thiết lập scope tường minh |
| `setReturningAttributes` thiếu field mapper cần | `attrs.get(...) == null` | Liệt kê đủ thuộc tính và xử lý trường hợp thiếu |
| Nghĩ `countLimit(50)` là “chỉ có 50 entry khớp” | Kết luận sai về dữ liệu | Phân biệt giới hạn output với số entry thực |
| Dùng `timeLimit` như timeout kết nối/TLS | Lỗi mạng vẫn chưa được quản lý đúng | Cấu hình timeout mạng/provider riêng và theo dõi lỗi |
| Dùng filter nối chuỗi với input | Nguy cơ LDAP filter injection | `EqualsFilter`, `LdapQueryBuilder` hoặc escaping phù hợp |
| Mặc định SUBTREE sẽ đọc cả nhánh ngang hàng | Không tìm thấy group ở `ou=groups` khi base `ou=people` | Đặt đúng group search base |
| Che mọi exception thành danh sách rỗng | Không phân biệt “không có dữ liệu” và “truy vấn lỗi” | Phân loại lỗi, log có kiểm soát, phản hồi đúng hợp đồng |

### Lưu ý với LDAP alias và referral

Search scope không đồng nhất với cách xử lý **alias** hoặc **referral**. Directory có thể có entry alias hoặc trả referral sang server khác. Chúng được xử lý theo chính sách của server/provider và cấu hình context. `setDerefLinkFlag` trong `SearchControls` mô tả xử lý **JNDI link**; không nên giả định nó tự thay thế toàn bộ tùy chọn dereference LDAP alias/referral.

Nếu hệ thống có alias hoặc multi-directory referrals, cần kiểm thử riêng với cấu hình JNDI/Spring LDAP đang dùng.

## 11. Bài thực hành: thay scope, giữ nguyên dữ liệu và filter

### 11.1. Dữ liệu thử nghiệm

Tạo một LDAP test server (ví dụ UnboundID) có base `dc=example,dc=org` và cây như ở mục 2. Các entry nhân viên phải đúng schema của server và có những thuộc tính bắt buộc như `sn` khi dùng `inetOrgPerson`.

Dùng một filter cố định:

~~~ldap
(objectClass=inetOrgPerson)
~~~

Và một search base cố định:

~~~text
ou=people,dc=example,dc=org
~~~

Thử lần lượt ba cấu hình:

~~~java
controls.setSearchScope(SearchControls.OBJECT_SCOPE);
controls.setSearchScope(SearchControls.ONELEVEL_SCOPE);
controls.setSearchScope(SearchControls.SUBTREE_SCOPE);
~~~

Trước khi thử, hãy tạo **mỗi lần một `SearchControls` hoặc cập nhật một lần và gọi search riêng** để so sánh rõ. Kết quả kỳ vọng theo dữ liệu ví dụ:

| Scope | Số người dùng | UID |
| --- | ---: | --- |
| OBJECT | 0 | — |
| ONELEVEL | 2 | `an`, `binh` |
| SUBTREE | 3 | `an`, `binh`, `chi` |

Số liệu trong bảng là **kỳ vọng cho bộ dữ liệu minh họa**, không phải benchmark hay cam kết cho mọi directory.

### 11.2. Kiểm thử tích hợp nên bổ sung

1. **Base DN không tồn tại:** kiểm tra lỗi được truyền lên và hiển thị đúng, không tự động xem là “0 kết quả hợp lệ”.
2. **OU lồng hai hoặc ba cấp:** kiểm chứng ONELEVEL không xuống sâu và SUBTREE bao phủ đúng nhánh.
3. **Entry ở nhánh ngang hàng:** kiểm chứng tìm dưới `ou=people` không vô tình đọc `ou=groups`.
4. **ACL hạn chế:** dùng tài khoản chỉ có quyền một phần để xác định hành vi visibility thực tế.
5. **Giới hạn kết quả/thời gian:** cố ý đặt `countLimit` nhỏ và `timeLimit` phù hợp; ghi nhận hành vi provider/server và ngoại lệ.
6. **Thuộc tính trả về:** yêu cầu `uid`, `cn`; kiểm tra mapper khi thiếu `mail` hoặc khi attribute bị ACL ẩn.
7. **Filter chứa ký tự đặc biệt:** thử `uid` chứa `*`, `(`, `)`, `\` để đảm bảo filter builder escape đúng.
8. **TLS/pooling:** với LDAPS hoặc StartTLS, kiểm tra chứng chỉ, quyền bind và không tái sử dụng context sai danh tính trong pooling.
9. **Tải lớn:** so sánh thời gian, số entry xét, tài nguyên server và số kết quả cho từng scope với filter tương đương.

Unit test của code tạo `SearchControls` chỉ chứng minh bạn đã gọi đúng setter. Để xác minh scope **thực sự ảnh hưởng thế nào đến tập kết quả**, cần chạy search trên LDAP server thử nghiệm có cấu trúc cây phù hợp.

## 12. Câu hỏi tự kiểm tra

1. Với base `ou=people`, tại sao ONELEVEL có thể trả `uid=an` nhưng không trả `uid=chi` nằm dưới `ou=engineering`?
2. Nếu dùng `OBJECT_SCOPE` với base `ou=people` và filter `(objectClass=inetOrgPerson)`, vì sao kết quả rỗng?
3. Search base `ou=people` và scope SUBTREE có đọc được `cn=developers,ou=groups` không? Tại sao?
4. `setCountLimit(50)` có đảm bảo server chỉ phải kiểm tra 50 entry không? Có chứng minh directory chỉ có 50 entry phù hợp không?
5. Khác biệt giữa `setReturningAttributes(null)` và `setReturningAttributes(new String[0])` là gì?
6. Để xử lý trường hợp người dùng được chuyển từ `ou=people` sang `ou=hr,ou=people`, bạn cần kiểm tra phần nào trong cấu hình search?
7. Một API trả danh sách rỗng khi LDAP server timeout. Vì sao không nên coi đây là bằng chứng tài khoản người dùng không tồn tại?
8. Khi ứng dụng chỉ cần đọc một entry đã biết DN, tại sao `lookup` có thể phù hợp hơn một cuộc search dùng `OBJECT_SCOPE`?

**Gợi ý đáp án:** (1) ONELEVEL chỉ xét con trực tiếp; (2) base là OU không khớp objectClass của nhân viên; (3) không, groups là nhánh ngang hàng; (4) không, đây là giới hạn output; (5) null yêu cầu tập thuộc tính mặc định, mảng rỗng không yêu cầu attribute; (6) base/scope, nên có thể cần SUBTREE; (7) lỗi vận hành không đồng nghĩa dữ liệu vắng mặt; (8) lookup diễn đạt thao tác đọc entry theo DN trực tiếp, không cần filter.

## 13. Checklist triển khai

- [ ] Xác định DN của nhánh nghiệp vụ và search base chính xác.
- [ ] Quyết định **có cần chính base**, **con trực tiếp** hay **tất cả hậu duệ**.
- [ ] Đặt `setSearchScope(...)` tường minh trong các lời gọi `SearchControls` quan trọng.
- [ ] Đảm bảo filter đúng và các giá trị input được escape an toàn.
- [ ] Yêu cầu đúng các attributes mà mapper sử dụng.
- [ ] Đặt size/time limit hợp lý, xử lý đúng lỗi giới hạn và timeout.
- [ ] Phân biệt DN tương đối với base được cấu hình trong `ContextSource`.
- [ ] Kiểm tra riêng user search base và group search base nếu có Spring Security LDAP.
- [ ] Xác minh quyền tài khoản bind, TLS và chính sách pooling.
- [ ] Viết integration test với OU lồng nhau và nhánh ngang hàng.
- [ ] Đo hiệu năng trên server/số entry/chỉ mục đại diện trước khi quyết định thay đổi scope rộng.

## 14. Ghi nhớ

**`SearchControls` không chỉ là cấu hình “tìm nhiều hay ít”; nó xác định đúng phạm vi cây directory mà yêu cầu tìm kiếm được phép xét.** OBJECT chỉ xét entry tại base; ONELEVEL xét các con trực tiếp; SUBTREE xét base và mọi hậu duệ. Filter xác định entry nào khớp **trong scope đó**, còn ACL và schema tiếp tục chi phối kết quả thực tế.

Trong Spring LDAP, hãy cấu hình `ContextSource` với base rõ ràng, truyền DN tương đối đúng chỗ, đặt scope tường minh trong `LdapTemplate.search(...)`, yêu cầu đúng các attributes cần thiết và xử lý giới hạn/ngoại lệ. Sự lựa chọn tốt nhất là scope **đủ bao phủ dữ liệu nghiệp vụ**, kết hợp filter, chỉ mục và giới hạn phù hợp.

### Tài liệu tham khảo

- [RFC 4511 — LDAP: The Protocol (SearchRequest, baseObject/singleLevel/wholeSubtree)](https://www.rfc-editor.org/rfc/rfc4511)
- [Java SE 17 — javax.naming.directory.SearchControls](https://docs.oracle.com/en/java/javase/17/docs/api/java.naming/javax/naming/directory/SearchControls.html)
- [Java SE 17 — javax.naming.directory.DirContext](https://docs.oracle.com/en/java/javase/17/docs/api/java.naming/javax/naming/directory/DirContext.html)
- [Spring LDAP Reference Documentation](https://docs.spring.io/spring-ldap/reference/)
- [RFC 2696 — LDAP Simple Paged Results](https://www.rfc-editor.org/rfc/rfc2696)
- [RFC 4515 — LDAP Filter String Syntax](https://www.rfc-editor.org/rfc/rfc4515)
