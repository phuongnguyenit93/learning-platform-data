# One-level search và các con trực tiếp trong LDAP

Khi tìm kiếm LDAP, chọn đúng **search scope** quyết định máy chủ sẽ xem xét những entry nào trong cây thư mục. **One-level search** chỉ xét các entry **con trực tiếp** của một search base: không xét chính entry base và không đi sâu xuống cháu, chắt. Trong Spring LDAP, phạm vi này thường được cấu hình bằng `SearchControls.ONELEVEL_SCOPE` khi gọi `LdapTemplate.search(...)`.

Bài học thuộc chương **Search scope**, với ví dụ cấu trúc LDAP, lệnh `ldapsearch` và Java/Spring LDAP. Sau bài này, bạn có thể:

- Giải thích chính xác “một cấp” dựa trên DN/RDN của các entry.
- Phân biệt `OBJECT_SCOPE`, `ONELEVEL_SCOPE` và `SUBTREE_SCOPE` bằng cùng một cây dữ liệu.
- Kết hợp **search base**, **scope** và **filter** để dự đoán kết quả.
- Chỉ định one-level search bằng `LdapTemplate` với `SearchControls`.
- Hiểu vì sao một entry tồn tại nhưng không được trả về nếu nằm sâu hơn một cấp hoặc chính là base.
- Thiết kế truy vấn giới hạn phạm vi, kiểm thử và chẩn đoán kết quả thiếu hoặc quá rộng.

## 1. Ví dụ cây thư mục: thế nào là “con trực tiếp”?

Giả sử directory server chứa các entry sau:

```text
dc=example,dc=org
├── ou=people                         ← search base
│   ├── uid=lan                       ← con trực tiếp (cấp 1)
│   ├── uid=minh                      ← con trực tiếp (cấp 1)
│   └── ou=contractors                ← con trực tiếp (cấp 1)
│       └── uid=an                    ← cháu (cấp 2)
└── ou=groups
    └── cn=developers
```

Trong ví dụ này, DN đầy đủ là:

| Entry | Distinguished Name (DN) |
| --- | --- |
| Nhánh people | `ou=people,dc=example,dc=org` |
| Lan | `uid=lan,ou=people,dc=example,dc=org` |
| Minh | `uid=minh,ou=people,dc=example,dc=org` |
| Nhánh contractors | `ou=contractors,ou=people,dc=example,dc=org` |
| An | `uid=an,ou=contractors,ou=people,dc=example,dc=org` |
| Nhánh groups | `ou=groups,dc=example,dc=org` |

Lấy `ou=people,dc=example,dc=org` làm **search base**. Khi đó:

1. **Base** nằm ở cấp 0: `ou=people,dc=example,dc=org`.
2. **Con trực tiếp** là các entry có DN bằng **một RDN thêm vào trước DN của base**: `uid=lan`, `uid=minh` và `ou=contractors`.
3. **Cháu** như `uid=an,ou=contractors,...` có **hai RDN** thêm vào trước DN của base, nên nằm ngoài one-level search.
4. `ou=groups,...` là nhánh khác, không nằm dưới base `ou=people,...`.

“Một cấp” là khoảng cách **cấu trúc cây**, không phụ thuộc số dấu phẩy trong giá trị chuỗi, tên object class hay số lượng thuộc tính của entry. Một RDN có thể chứa nhiều cặp thuộc tính–giá trị, nhưng vẫn chỉ đại diện cho **một cấp tên**.

## 2. Ba search scope trong LDAP

LDAP có ba search scope chuẩn. Với JNDI (được Spring LDAP sử dụng), chúng tương ứng với các hằng trong `javax.naming.directory.SearchControls`:

| Scope | Hằng JNDI | Xét entry base? | Xét con trực tiếp? | Xét cháu/chắt? |
| --- | --- | --- | --- | --- |
| **Base-object** | `OBJECT_SCOPE` | Có | Không | Không |
| **One-level** | `ONELEVEL_SCOPE` | Không | Có | Không |
| **Whole-subtree** | `SUBTREE_SCOPE` | Có | Có | Có |

Ở mức giao thức LDAP (RFC 4511), ba giá trị scope là `baseObject (0)`, `singleLevel (1)` và `wholeSubtree (2)`. Trong thực hành, thuật ngữ **one-level**, **single-level** hoặc **singleLevel** chỉ cùng kiểu phạm vi: tìm **ngay dưới base**.

Giả sử tất cả entry trong cây mẫu đều tồn tại và ta dùng một filter tổng quát `(objectClass=*)`:

| Scope với base `ou=people,...` | Entry được xét và có thể trả về |
| --- | --- |
| `OBJECT_SCOPE` | Chỉ `ou=people` |
| `ONELEVEL_SCOPE` | `uid=lan`, `uid=minh`, `ou=contractors` |
| `SUBTREE_SCOPE` | `ou=people`, `uid=lan`, `uid=minh`, `ou=contractors`, `uid=an` |

Ví dụ trên giả định tất cả entry đều khớp filter, có quyền đọc và không bị hạn chế kết quả. **Search scope chỉ xác định tập entry được xem xét**; filter và quyền truy cập còn quyết định entry nào được trả về.

### Tại sao one-level không trả về chính base?

Nếu muốn lấy thông tin của `ou=people` (ví dụ `description`), dùng **base-object search** với base là entry đó. One-level chỉ tìm **các con của base**, vì thế dù `ou=people` đáp ứng filter, nó vẫn không xuất hiện trong kết quả.

Nếu muốn tìm cả chính nhánh people và tất cả entry bên dưới, dùng **subtree search**. Không có tùy chọn one-level nào tự động “bao gồm base” chỉ bằng thay đổi filter.

## 3. Search base, search scope và filter là ba khái niệm riêng

Một LDAP search thường gồm:

- **Search base:** DN làm điểm bắt đầu, ví dụ `ou=people,dc=example,dc=org`.
- **Search scope:** phạm vi so với base, ví dụ `singleLevel`.
- **Search filter:** điều kiện chọn entry, ví dụ `(objectClass=inetOrgPerson)`.

Ví dụ truy vấn:

```text
Base:   ou=people,dc=example,dc=org
Scope:  one-level
Filter: (objectClass=inetOrgPerson)
```

Giả sử:

- `uid=lan` và `uid=minh` là entry người dùng với `objectClass: inetOrgPerson`.
- `ou=contractors` là entry `organizationalUnit`.
- `uid=an` là `inetOrgPerson` nhưng nằm trong `ou=contractors`.

**Kết quả:** Lan và Minh được trả về; `ou=contractors` bị loại bởi filter dù nằm đúng phạm vi; An bị loại bởi **scope** dù khớp filter. Tăng độ rộng của filter không thể khiến one-level đi xuống sâu hơn.

Thay filter bằng `(objectClass=organizationalUnit)` thì entry `ou=contractors` có thể được trả về, nhưng `ou=people` vẫn bị loại vì đó là **base**, không phải con trực tiếp.

Điểm cần nhớ: **one-level không có nghĩa chỉ tìm người dùng**. Nó xem xét mọi loại entry ở cấp ngay dưới search base; filter mới giới hạn loại đối tượng bạn cần.

## 4. Dùng `ldapsearch` để quan sát one-level

Với công cụ dòng lệnh `ldapsearch` (OpenLDAP client), tùy chọn `-s one` chỉ định phạm vi một cấp. Một lệnh minh họa:

```bash
ldapsearch -x -H ldaps://ldap.example.org:636 \
  -D "cn=readonly,ou=system,dc=example,dc=org" -W \
  -b "ou=people,dc=example,dc=org" \
  -s one \
  "(objectClass=inetOrgPerson)" dn uid cn
```

Giải thích:

| Tham số | Tác dụng |
| --- | --- |
| `-H ldaps://...` | Kết nối LDAP qua TLS theo địa chỉ giả định |
| `-D ... -W` | Bind bằng DN được chỉ định; hỏi mật khẩu lúc chạy |
| `-b "ou=people,dc=example,dc=org"` | Chỉ định search base **đầy đủ** trên server |
| `-s one` | Chỉ xét con trực tiếp của search base |
| `"(objectClass=inetOrgPerson)"` | Chỉ trả entry khớp filter |
| `dn uid cn` | Yêu cầu các trường cần quan sát |

Trong dữ liệu giả định, kết quả có thể chứa DN của Lan và Minh, nhưng không chứa DN của An trong nhánh contractors.

Để so sánh, chạy lại cùng câu lệnh với `-s base` hoặc `-s sub`. `base` chỉ xét chính `ou=people`; `sub` xét cả base và mọi cấp con, vì vậy An có thể xuất hiện khi filter khớp.

Các giá trị hostname, tài khoản và DN ở đây chỉ dùng để minh họa. Với hệ thống thật cần URL, DN bind và truststore/chứng chỉ phù hợp; kết quả còn phụ thuộc ACL của server.

## 5. One-level search với `LdapTemplate` trong Spring LDAP

Giả sử ứng dụng Spring LDAP đã cấu hình `ContextSource` với base `dc=example,dc=org`. Khi đó, các đường dẫn như `ou=people` truyền vào `LdapTemplate` được hiểu là **tương đối với base context**.

Ví dụ cấu hình trong Spring Boot:

```yaml
spring:
  ldap:
    urls: ldaps://ldap.example.org:636
    base: dc=example,dc=org
    username: cn=readonly,ou=system,dc=example,dc=org
    password: ${LDAP_BIND_PASSWORD}
```

Trong Java, sử dụng `SearchControls.ONELEVEL_SCOPE`:

```java
import java.util.List;
import javax.naming.directory.SearchControls;

import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;

record PersonSummary(String uid, String commonName) {}

public class PeopleDirectory {
    private final LdapTemplate ldapTemplate;

    public PeopleDirectory(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<PersonSummary> findDirectUsers() {
        SearchControls controls = new SearchControls();
        controls.setSearchScope(SearchControls.ONELEVEL_SCOPE);
        controls.setReturningAttributes(new String[] {"uid", "cn"});
        controls.setCountLimit(100); // Giới hạn số entry client yêu cầu.

        String filter = "(&(objectClass=inetOrgPerson)(uid=*))";

        return ldapTemplate.search(
            "ou=people", // Tương đối với ContextSource base.
            filter,
            controls,
            (AttributesMapper<PersonSummary>) attrs ->
                new PersonSummary(
                    (String) attrs.get("uid").get(),
                    attrs.get("cn") == null
                        ? null
                        : (String) attrs.get("cn").get()
                )
        );
    }
}
```

Đây là ví dụ Java 17+ sử dụng `record`. Nếu dự án chạy Java cũ hơn, có thể thay `PersonSummary` bằng một class DTO.

Cách đọc từng tham số:

1. `"ou=people"` là **search base tương đối**, ứng với DN đầy đủ `ou=people,dc=example,dc=org`.
2. `controls.setSearchScope(SearchControls.ONELEVEL_SCOPE)` buộc tìm các entry **ngay dưới** nhánh people.
3. `(&(objectClass=inetOrgPerson)(uid=*))` chỉ cho phép các entry người dùng có `uid`; nhánh `ou=contractors` không đáp ứng điều kiện này.
4. `setReturningAttributes` chỉ yêu cầu những thuộc tính cần ánh xạ sang DTO; kết quả tìm kiếm không mặc định cần mọi attribute.
5. `setCountLimit(100)` là giới hạn số entry kết quả yêu cầu từ phía client; máy chủ có thể áp đặt thêm giới hạn riêng. Giới hạn trả về không thay đổi **ngữ nghĩa one-level**.

**Kết quả kỳ vọng theo cây ví dụ:** hai entry `uid=lan` và `uid=minh`. Entry `uid=an,ou=contractors,ou=people,...` không được xét vì sâu hơn một cấp.

### Thay đổi scope mà vẫn giữ nguyên base và filter

Có thể giữ nguyên `ldapTemplate.search(...)` và đổi duy nhất:

```java
controls.setSearchScope(SearchControls.OBJECT_SCOPE);
```

hoặc:

```java
controls.setSearchScope(SearchControls.SUBTREE_SCOPE);
```

Với `OBJECT_SCOPE`, truy vấn người dùng trong ví dụ không trả kết quả vì chính entry `ou=people` không phải `inetOrgPerson`. Với `SUBTREE_SCOPE`, Lan, Minh **và An** có thể được tìm thấy vì An nằm dưới một nhánh con nhưng vẫn thuộc subtree của people.

Đó là cách kiểm chứng quan trọng: **cùng base, cùng filter, chỉ thay scope** sẽ cho thấy tác động riêng của phạm vi tìm kiếm.

## 6. Khi base context khác nhau, search base thay đổi ra sao?

Không nên nhầm **ContextSource base** (gốc tương đối mà client sử dụng) với **search base** (vị trí bắt đầu của một lần tìm kiếm).

Ví dụ cùng muốn tìm các con trực tiếp của `ou=people,dc=example,dc=org`:

| Base của `ContextSource` | Search base trong `LdapTemplate` | Scope |
| --- | --- | --- |
| `dc=example,dc=org` | `ou=people` | `ONELEVEL_SCOPE` |
| `ou=people,dc=example,dc=org` | `""` (DN rỗng, chính base context) | `ONELEVEL_SCOPE` |
| Không cấu hình base | `ou=people,dc=example,dc=org` | `ONELEVEL_SCOPE` |

Ba cách viết cùng chỉ định **search base đầy đủ** trên directory server, với điều kiện cấu hình server và quyền truy cập phù hợp.

Ví dụ, nếu cấu hình `ContextSource.base = "dc=example,dc=org"` nhưng truyền vào `LdapTemplate.search` cả `"ou=people,dc=example,dc=org"`, hậu tố base có thể bị áp dụng hai lần và dẫn tới tìm kiếm sai DN. Hãy xác định rõ quy ước DN tương đối của `LdapTemplate`.

### Chọn base là nhánh chứa con trực tiếp cần tìm

Nếu đặt search base là `dc=example,dc=org` rồi tìm one-level, kết quả được xét sẽ gồm `ou=people` và `ou=groups`, **không phải** Lan và Minh. Muốn tìm Lan và Minh bằng one-level, search base phải là `ou=people,dc=example,dc=org`.

Đây là điểm dễ sai khi người học nhìn filter `(uid=lan)` rồi nghĩ server sẽ tự đi xuống nhánh con. **Filter không thể mở rộng phạm vi tìm kiếm** vượt ngoài search base/scope.

## 7. One-level search khi cấu trúc thư mục có nhiều tầng

Ứng dụng quản lý nhân sự có thể phân người dùng thành nhiều OU:

```text
ou=people
├── ou=employees
│   ├── uid=lan
│   └── uid=minh
└── ou=contractors
    └── uid=an
```

Lúc này, tìm one-level với base `ou=people` **chỉ xét** `ou=employees` và `ou=contractors`. Nếu filter là `(objectClass=inetOrgPerson)`, kết quả có thể rỗng dù ba tài khoản tồn tại.

Để lấy người dùng, có hai hướng:

1. Tìm `SUBTREE_SCOPE` dưới `ou=people` nếu chính sách và yêu cầu cho phép tìm mọi cấp con.
2. Tìm `ONELEVEL_SCOPE` **lần lượt** dưới `ou=employees` và `ou=contractors` nếu ứng dụng chủ ý quản lý các nhánh này riêng.

Sử dụng one-level phù hợp khi mỗi entry cần tìm là **một con trực tiếp** của nhánh đã biết. Nếu cơ cấu tổ chức thay đổi và người dùng được chuyển xuống các OU mới, một truy vấn one-level ở nhánh cũ có thể không còn tìm thấy họ. Đó là thay đổi về **vị trí trong cây**, không nhất thiết là lỗi filter hay lỗi kết nối.

## 8. Những nhầm lẫn và lỗi thường gặp

| Hiện tượng | Nguyên nhân hoặc cách hiểu đúng |
| --- | --- |
| Không thấy entry base trong kết quả one-level | Đây là hành vi đúng; one-level chỉ tìm **con trực tiếp**. Dùng `OBJECT_SCOPE` nếu cần đọc base. |
| Không thấy `uid=an` nằm dưới `ou=contractors` | An nằm sâu hơn một cấp tính từ `ou=people`. Chọn `SUBTREE_SCOPE` hoặc đổi search base. |
| Dùng `(objectClass=*)` nhưng vẫn thiếu cháu/chắt | Filter rất rộng vẫn không vượt qua `ONELEVEL_SCOPE`. |
| One-level trả OU nhưng không trả tài khoản | Các OU đang là con trực tiếp; tài khoản nằm dưới OU con. Kiểm tra cấu trúc DN. |
| Truy vấn từ `dc=example,dc=org` chỉ trả `ou=people` và `ou=groups` | Đó là con trực tiếp của root được chọn; đổi base sang `ou=people` nếu cần các user ngay dưới đó. |
| Dùng DN đầy đủ trong `LdapTemplate.search` dù `ContextSource` đã có base | Có thể dẫn tới DN bị lặp hậu tố. Dùng search base tương đối. |
| Có scope đúng nhưng kết quả rỗng | Kiểm tra filter, sự tồn tại của base, ACL, schema, search limit và tình trạng kết nối. |
| Dùng one-level như một biện pháp phân quyền | Scope chỉ giới hạn phạm vi truy vấn. LDAP server phải thực thi ACL để kiểm soát truy cập. |

Một số lỗi cần phân biệt:

- **Base không tồn tại:** máy chủ có thể trả lỗi tương ứng với `noSuchObject`; đây không đồng nghĩa với “không có entry con nào khớp”.
- **Không có con khớp filter:** trả về danh sách rỗng là bình thường, kể cả khi base tồn tại và có các con thuộc loại khác.
- **Thiếu quyền:** tài khoản bind có thể không nhìn thấy những entry hoặc thuộc tính cần đọc.
- **Giới hạn máy chủ:** giới hạn kích thước, thời gian hoặc paging có thể ảnh hưởng số lượng kết quả thực tế.

## 9. Bảo mật, hiệu năng và kiểm thử

### Scope giúp giới hạn công việc tìm kiếm, nhưng không thay thế ACL

Khi chỉ cần các con trực tiếp, one-level thường là lựa chọn có chủ đích rõ ràng hơn so với tìm toàn bộ subtree. Tuy nhiên, **không thể khẳng định one-level luôn nhanh hơn** trong mọi directory: hiệu năng thực tế còn phụ thuộc số entry con, filter, chỉ mục (index), cấu hình máy chủ và tải hệ thống.

Khi tích hợp Spring LDAP:

- Dùng **LDAPS hoặc StartTLS** với chứng chỉ được kiểm tra đúng cách; không ghi mật khẩu bind thật trong source code.
- Cấp quyền tối thiểu cho tài khoản truy cập thư mục. Search base/scope là tham số truy vấn, không phải chính sách bảo mật.
- Dùng `LdapQueryBuilder` hoặc các lớp `EqualsFilter` khi filter có giá trị đầu vào động; tránh nối chuỗi trực tiếp để phòng **LDAP filter injection**.
- Giới hạn thuộc tính trả về và sử dụng size/time limit phù hợp. Nếu cần duyệt số lượng entry lớn, xem xét paging được LDAP server hỗ trợ.

### Kiểm thử hành vi one-level

Trên một thư mục kiểm thử được phép sử dụng, tạo hoặc chuẩn bị ít nhất:

1. Một entry base `ou=people`.
2. Hai tài khoản nằm ngay dưới base: `uid=lan`, `uid=minh`.
3. Một OU con `ou=contractors` và một tài khoản `uid=an` nằm dưới OU này.

Thực hiện ba lần tìm với **cùng base và filter** `(objectClass=inetOrgPerson)`, chỉ đổi scope. Với dữ liệu mẫu:

| Scope | Kết quả mong đợi |
| --- | --- |
| `OBJECT_SCOPE` | Không có người dùng (base không khớp filter) |
| `ONELEVEL_SCOPE` | `lan` và `minh` |
| `SUBTREE_SCOPE` | `lan`, `minh` và `an` |

Thử thêm một lần `ONELEVEL_SCOPE` với filter `(objectClass=organizationalUnit)`; lúc này `ou=contractors` được tìm thấy nhưng `ou=people` không được trả về.

Khi kiểm thử tự động với LDAP giả lập, embedded LDAP hoặc server kiểm thử, nên kiểm tra **tập DN trả về**, không giả định máy chủ trả entry theo một thứ tự cụ thể.

## 10. Bài thực hành tự kiểm tra

Cho cây:

```text
dc=example,dc=org
└── ou=people
    ├── uid=mai                (inetOrgPerson)
    ├── ou=interns             (organizationalUnit)
    │   └── uid=bao           (inetOrgPerson)
    └── uid=long               (inetOrgPerson)
```

Giả sử server cho phép đọc toàn bộ entry, mọi entry đều có `objectClass` và `ContextSource.base = "dc=example,dc=org"`.

**Câu hỏi:**

1. Với search base `ou=people` và filter `(objectClass=*)`, one-level có thể trả những entry nào?
2. Với cùng base nhưng filter `(objectClass=inetOrgPerson)`, one-level trả những người nào?
3. Nếu dùng `SUBTREE_SCOPE` ở câu 2, kết quả thay đổi thế nào?
4. Muốn tìm trực tiếp `uid=bao` bằng one-level, nên chọn search base tương đối nào?
5. Tại sao `OBJECT_SCOPE` với base `ou=people` và filter `(uid=mai)` không tìm được Mai?
6. Trong ví dụ Java, dòng nào quyết định **độ sâu tìm kiếm**? Dòng nào quyết định **nhánh bắt đầu**?

**Đáp án:**

1. `uid=mai`, `ou=interns` và `uid=long`: đây là ba con trực tiếp. Không có `ou=people` và `uid=bao`.
2. Mai và Long: `ou=interns` không khớp object class yêu cầu, còn Bảo nằm sâu hai cấp.
3. Có thêm Bảo vì subtree gồm mọi cấp con, giả sử Bảo khớp filter.
4. `ou=interns,ou=people`, tương đối với `dc=example,dc=org`. Khi đó Bảo là con trực tiếp của search base.
5. Base-object chỉ kiểm tra chính `ou=people`, không kiểm tra các con của nó. Filter không thay đổi scope.
6. `setSearchScope(SearchControls.ONELEVEL_SCOPE)` quyết định độ sâu; tham số `"ou=people"` của `LdapTemplate.search(...)` chỉ định search base tương đối.

## 11. Ghi nhớ và tài liệu tham khảo

**One-level search** xét **đúng một cấp con trực tiếp** của search base và **không bao gồm chính base**. Kết quả cuối cùng còn phải khớp filter và đáp ứng các quyền, giới hạn do LDAP server đặt ra. Dùng `OBJECT_SCOPE` để kiểm tra chính base; dùng `SUBTREE_SCOPE` khi thực sự cần xét tất cả cấp con. Với Spring LDAP, hãy chỉ định `ONELEVEL_SCOPE` qua `SearchControls`, kết hợp search base tương đối với `ContextSource.base`, và luôn kiểm chứng phạm vi trên cây DN thực tế.

Tìm hiểu thêm:

- [RFC 4511 — Lightweight Directory Access Protocol (LDAP): The Protocol](https://www.rfc-editor.org/rfc/rfc4511): search request, giá trị scope `baseObject`, `singleLevel`, `wholeSubtree`.
- [Java SearchControls API](https://docs.oracle.com/en/java/javase/17/docs/api/java.naming/javax/naming/directory/SearchControls.html): `OBJECT_SCOPE`, `ONELEVEL_SCOPE`, `SUBTREE_SCOPE`, size limit và danh sách thuộc tính trả về.
- [Spring LDAP Reference Documentation](https://docs.spring.io/spring-ldap/reference/): `ContextSource`, `LdapTemplate` và truy vấn tìm kiếm LDAP.
