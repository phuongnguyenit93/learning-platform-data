# Ba phạm vi tìm kiếm LDAP: OBJECT, ONELEVEL và SUBTREE

## 1. Vì sao cần xác định phạm vi tìm kiếm?

Trong **Spring Data LDAP**, dữ liệu được tổ chức thành các *entry* trong cây thư mục. Mỗi entry có **Distinguished Name (DN)** để xác định vị trí, các thuộc tính như `uid`, `cn`, `mail` và các `objectClass` mô tả kiểu dữ liệu được phép lưu. Khi sử dụng repository hoặc `LdapTemplate`, ta thường muốn lấy một entry, các entry trực tiếp thuộc một nhánh, hoặc mọi entry nằm sâu dưới nhánh đó.

Một phép tìm kiếm LDAP cần phân biệt ba thành phần:

1. **Base DN**: điểm bắt đầu trong cây thư mục, chẳng hạn `ou=people,dc=example,dc=org`.
2. **Search scope**: phạm vi tương đối với base DN, gồm `OBJECT`, `ONELEVEL` và `SUBTREE`.
3. **Search filter**: điều kiện một entry phải thỏa mãn mới được trả về, chẳng hạn `(objectClass=inetOrgPerson)` hoặc `(&(objectClass=inetOrgPerson)(uid=alice))`.

Scope quyết định **entry nào được xem xét**; filter quyết định **entry nào trong số đó khớp điều kiện**. Một filter đúng không thể trả về entry nằm ngoài scope. Tương tự, mở rộng scope không có nghĩa là mọi entry đều được trả về: chúng vẫn phải khớp filter và phải được quyền truy cập LDAP cho phép đọc.

## 2. Ví dụ cây thư mục

Giả sử directory có cấu trúc sau:

```text
dc=example,dc=org
└── ou=people                      [organizationalUnit]
    ├── uid=alice                  [inetOrgPerson]
    ├── uid=bob                    [inetOrgPerson]
    └── ou=interns                 [organizationalUnit]
        └── uid=carol              [inetOrgPerson]
```

DN đầy đủ của Carol là `uid=carol,ou=interns,ou=people,dc=example,dc=org`. Chọn **base DN** chung là `ou=people,dc=example,dc=org` và filter `(objectClass=*)` (khớp các entry có thuộc tính `objectClass`), ta có ba phạm vi khác nhau:

| Phạm vi | Có xét chính entry `ou=people`? | Có xét con trực tiếp? | Có xét các cấp sâu hơn? | Kết quả trong cây ví dụ |
| --- | :---: | :---: | :---: | --- |
| **OBJECT** | Có | Không | Không | `ou=people` |
| **ONELEVEL** | Không | Có | Không | `uid=alice`, `uid=bob`, `ou=interns` |
| **SUBTREE** | Có | Có | Có | `ou=people`, `uid=alice`, `uid=bob`, `ou=interns`, `uid=carol` |

Các tên ngắn trong bảng được hiểu tương đối với cây trên. Trong giao thức LDAPv3, ba tên tương ứng là `baseObject`, `singleLevel` và `wholeSubtree`.

### 2.1. OBJECT: chỉ chính entry tại base DN

**OBJECT** (còn gọi là *base scope*) chỉ kiểm tra entry có DN **bằng đúng base DN**; nó không tự động truy tìm entry con. Phạm vi này phù hợp khi đã biết DN của đối tượng và muốn đọc thuộc tính hoặc xác minh đối tượng có thỏa mãn filter hay không.

Với base `ou=people,...`:

- Filter `(objectClass=organizationalUnit)` trả về `ou=people`.
- Filter `(objectClass=inetOrgPerson)` trả về **không có entry nào** vì chính `ou=people` không thuộc lớp `inetOrgPerson`, dù bên dưới có nhiều người dùng.

Nếu cần đọc Alice theo DN đã biết, có thể đặt base trực tiếp thành `uid=alice,ou=people,dc=example,dc=org` và chọn OBJECT. Scope OBJECT không có nghĩa là tìm theo thuộc tính `uid` trên toàn cây; nó luôn giới hạn ở **một DN cụ thể**.

### 2.2. ONELEVEL: chỉ các entry con trực tiếp

**ONELEVEL** kiểm tra các entry nằm **đúng một cấp dưới** base DN. Chính entry base không thuộc phạm vi này; mọi cháu, chắt bên dưới cũng không thuộc phạm vi.

Với base `ou=people,...`:

- Filter `(objectClass=*)` khớp Alice, Bob và nhánh `ou=interns`.
- Filter `(objectClass=inetOrgPerson)` chỉ khớp **Alice và Bob**.
- Carol không thể xuất hiện với ONELEVEL vì DN của Carol nằm dưới `ou=interns` thêm một cấp.

ONELEVEL hữu ích khi hiển thị danh sách thành viên trực tiếp của một đơn vị hoặc liệt kê các nhánh con trước khi cho phép người dùng duyệt tiếp.

### 2.3. SUBTREE: base DN và toàn bộ hậu duệ

**SUBTREE** duyệt phạm vi bắt đầu từ **chính base DN**, gồm con trực tiếp và các cấp sâu hơn. Với cùng base `ou=people,...`:

- Filter `(objectClass=*)` khớp cả năm entry trong nhánh `people`.
- Filter `(objectClass=inetOrgPerson)` khớp **Alice, Bob và Carol**; hai entry `organizationalUnit` bị filter loại ra.

SUBTREE phù hợp khi cần tìm nhân sự ở nhiều đơn vị con mà không biết trước họ đang thuộc OU nào. Đổi lại, nhánh càng lớn thì số entry phải duyệt và lượng dữ liệu có thể trả về càng nhiều.

> **Quy tắc ghi nhớ:** OBJECT = đúng điểm gốc; ONELEVEL = các con ngay dưới điểm gốc; SUBTREE = điểm gốc cùng toàn bộ nhánh bên dưới.

## 3. Tách bạch scope và filter bằng một bài toán

Giả sử chức năng tìm tài khoản có filter `(objectClass=inetOrgPerson)` và cùng base `ou=people,dc=example,dc=org`:

| Scope | Entry trả về | Vì sao? |
| --- | --- | --- |
| OBJECT | Không có | Base là `organizationalUnit`, không khớp filter người dùng. |
| ONELEVEL | Alice, Bob | Hai entry người dùng là con trực tiếp; Carol nằm sâu hơn. |
| SUBTREE | Alice, Bob, Carol | Cả ba đều nằm trong nhánh và khớp filter. |

Nếu thay filter thành `(&(objectClass=inetOrgPerson)(uid=carol))`, ONELEVEL vẫn không thể tìm thấy Carol, nhưng SUBTREE có thể. Đây là lý do khi truy vấn trả về rỗng, cần kiểm tra **cả base DN, scope và filter** trước khi kết luận dữ liệu không tồn tại.

## 4. Thực hiện với `LdapTemplate` trong Spring Data LDAP

`LdapTemplate` của Spring LDAP cung cấp các overload `search(...)` cho phép chỉ định `SearchControls`, trong đó `setSearchScope(...)` nhận một trong ba hằng số thuộc `javax.naming.directory.SearchControls`:

| Khái niệm | Hằng số Java | Giá trị giao thức |
| --- | --- | :---: |
| OBJECT | `SearchControls.OBJECT_SCOPE` | `0` |
| ONELEVEL | `SearchControls.ONELEVEL_SCOPE` | `1` |
| SUBTREE | `SearchControls.SUBTREE_SCOPE` | `2` |

Ví dụ sau sử dụng một `LdapTemplate` đã được cấu hình kết nối đến LDAP server. Giả sử `ContextSource` có base `dc=example,dc=org`, nên tham số `"ou=people"` là DN **tương đối với base cấu hình**, tương ứng DN đầy đủ `ou=people,dc=example,dc=org`.

```java
import java.util.List;
import javax.naming.directory.SearchControls;

import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;

public class PeopleDirectory {
    private final LdapTemplate ldapTemplate;

    public PeopleDirectory(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<String> findUserIds(boolean includeNestedOus) {
        SearchControls controls = new SearchControls();
        controls.setSearchScope(includeNestedOus
                ? SearchControls.SUBTREE_SCOPE
                : SearchControls.ONELEVEL_SCOPE);
        controls.setReturningAttributes(new String[] { "uid" });
        controls.setCountLimit(200);
        controls.setTimeLimit(3000); // mili giây (giới hạn phía client)

        AttributesMapper<String> uidMapper = attributes ->
                (String) attributes.get("uid").get();

        return ldapTemplate.search(
                "ou=people",                    // relative DN
                "(objectClass=inetOrgPerson)", // LDAP filter
                controls,
                uidMapper
        );
    }
}
```

Theo cây minh họa (giả sử server cho phép đọc):

```java
directory.findUserIds(false); // ONELEVEL: [alice, bob]
directory.findUserIds(true);  // SUBTREE:  [alice, bob, carol]
```

Thứ tự entry do server trả về **không được đảm bảo**, nên các danh sách trên chỉ minh họa tập kết quả. `uidMapper` chỉ đọc `uid` vì filter đã giới hạn ở entry `inetOrgPerson` có `uid` trong dữ liệu ví dụ; khi dùng schema khác, cần kiểm tra sự tồn tại của thuộc tính trước khi gọi `get()`.

Để kiểm tra **chính entry base** thay vì người dùng bên dưới, thay filter và scope như sau:

```java
SearchControls controls = new SearchControls();
controls.setSearchScope(SearchControls.OBJECT_SCOPE);
controls.setReturningAttributes(new String[] { "ou" });

AttributesMapper<String> ouMapper = attributes ->
        (String) attributes.get("ou").get();

List<String> groups = ldapTemplate.search(
        "ou=people",
        "(objectClass=organizationalUnit)",
        controls,
        ouMapper
); // [people] nếu base tồn tại và tài khoản có quyền đọc
```

Chỉ định scope **tường minh** giúp tránh phụ thuộc vào mặc định: một đối tượng `SearchControls` mới mặc định dùng ONELEVEL, trong khi các overload `LdapTemplate.search(...)` không truyền scope có thể dùng scope mặc định của `LdapTemplate` (thường là SUBTREE). Với yêu cầu cần đúng một cấp, nên thiết lập rõ `ONELEVEL_SCOPE`.

### Khi nào dùng repository, khi nào dùng `LdapTemplate`?

Spring Data LDAP repository hữu ích cho thao tác với entity được ánh xạ từ entry, tìm kiếm theo thuộc tính và thực hiện CRUD. Khi yêu cầu bắt buộc phân biệt **một DN**, **con trực tiếp** hay **toàn bộ nhánh**, `LdapTemplate` với `SearchControls` cho phép thể hiện phạm vi ngay tại lời gọi. Đừng suy đoán rằng tên method repository như `findByUid(...)` tự thể hiện search scope; cần xem cấu hình và cách truy vấn thực tế của phương thức đó.

## 5. Đối chiếu bằng `ldapsearch`

Có thể kiểm chứng kết quả trực tiếp với lệnh `ldapsearch` (đổi URL và tài khoản bind cho phù hợp môi trường):

```bash
ldapsearch -LLL -H ldaps://ldap.example.org:636 \
  -D "uid=reader,ou=service,dc=example,dc=org" -W \
  -b "ou=people,dc=example,dc=org" \
  -s one "(objectClass=inetOrgPerson)" dn uid
```

Tham số `-b` xác định base DN; `-s` xác định phạm vi tìm kiếm:

| Tùy chọn `ldapsearch` | Tương ứng Java | Diễn giải |
| --- | --- | --- |
| `-s base` | `OBJECT_SCOPE` | Chỉ tìm entry tại base DN. |
| `-s one` | `ONELEVEL_SCOPE` | Chỉ tìm các con trực tiếp. |
| `-s sub` | `SUBTREE_SCOPE` | Tìm base và mọi cấp hậu duệ. |

Giữ nguyên `-b`, filter và các tùy chọn còn lại, lần lượt đổi `-s base`, `-s one`, `-s sub` để so sánh. Tùy chọn `-W` yêu cầu nhập mật khẩu thay vì ghi mật khẩu vào lịch sử lệnh. Máy chủ cần hỗ trợ TLS và tài khoản bind cần có quyền đọc các entry được truy vấn.

## 6. Chọn scope theo nhu cầu và lưu ý vận hành

| Nhu cầu | Scope thường phù hợp | Lưu ý |
| --- | --- | --- |
| Kiểm tra một DN đã biết | OBJECT | Filter vẫn phải khớp với entry tại DN đó. |
| Liệt kê nhân viên trực thuộc một OU | ONELEVEL | Không lấy nhân viên ở OU con sâu hơn. |
| Duyệt các OU con của một phòng ban | ONELEVEL | Filter `objectClass=organizationalUnit` để loại người dùng. |
| Tìm nhân viên ở tất cả OU con | SUBTREE | Giới hạn nhánh gốc, filter và kích thước kết quả. |
| Tìm toàn bộ directory | SUBTREE với base đủ cao | Chỉ dùng khi nghiệp vụ thực sự yêu cầu và quyền truy cập cho phép. |

Một số tình huống dễ gây nhầm lẫn:

- **Dữ liệu có nhưng không thấy:** DN nằm sâu hơn một cấp trong khi truy vấn dùng ONELEVEL; hoặc filter không khớp `objectClass`/thuộc tính của entry.
- **Vô tình trả về cả OU cha:** SUBTREE bao gồm chính base DN nếu base khớp filter; ONELEVEL thì không.
- **Không có kết quả khác với base không tồn tại:** Nếu base DN sai hoặc không tồn tại, server có thể trả lỗi LDAP như `noSuchObject`, không đơn thuần là danh sách rỗng.
- **Scope rộng nhưng vẫn thiếu entry:** ACL, giới hạn kích thước/thời gian của server, referral hoặc quy tắc xử lý alias có thể ảnh hưởng kết quả. Scope không vượt qua quyền truy cập LDAP.
- **Truy vấn tốn tài nguyên:** SUBTREE từ một DN quá cao có thể duyệt rất nhiều entry; chọn nhánh nhỏ nhất phù hợp, dùng filter có thuộc tính được đánh chỉ mục khi có thể, chỉ lấy các thuộc tính cần thiết và dùng giới hạn/phân trang nếu cần.
- **Filter có dữ liệu nhập từ người dùng:** Không ghép chuỗi trực tiếp vào LDAP filter. Hãy dùng bộ dựng filter của Spring LDAP (ví dụ `LdapQueryBuilder`, `EqualsFilter`) để escape giá trị đúng quy tắc. Phạm vi tìm kiếm hẹp không thay thế được filter an toàn.
- **Bảo mật kết nối:** Với dữ liệu directory thực, sử dụng LDAPS hoặc StartTLS đã xác thực chứng chỉ, cấp quyền đọc tối thiểu cho tài khoản bind, và không ghi mật khẩu trong source code.

## 7. Tự kiểm tra kiến thức

1. Với base `ou=people,dc=example,dc=org`, dùng filter `(objectClass=inetOrgPerson)`, vì sao ONELEVEL không trả về Carol nhưng SUBTREE có thể?
2. Nếu cần kiểm tra `uid=alice,ou=people,dc=example,dc=org` đã biết trước, bạn chọn base DN và scope nào để không tìm sang entry khác?
3. Vì sao `SUBTREE` kết hợp filter `(objectClass=*)` có thể trả về `ou=people`, nhưng filter `(objectClass=inetOrgPerson)` không trả về OU đó?
4. Một truy vấn ONELEVEL cho kết quả rỗng. Bạn sẽ kiểm tra base DN, filter, độ sâu, quyền truy cập theo thứ tự nào để xác định nguyên nhân?

**Kết luận:** Khi truy vấn LDAP qua Spring Data LDAP, hãy bắt đầu từ base DN đúng, chọn **OBJECT** cho đúng một entry, **ONELEVEL** cho các entry con trực tiếp, **SUBTREE** cho toàn nhánh, rồi áp dụng filter và giới hạn kết quả phù hợp với nghiệp vụ.

### Tài liệu tham khảo

- [RFC 4511 – LDAPv3, mục 4.5.1.2: SearchRequest.scope](https://www.rfc-editor.org/rfc/rfc4511#section-4.5.1.2).
- [Java `SearchControls` API](https://docs.oracle.com/en/java/javase/26/docs/api/java.naming/javax/naming/directory/SearchControls.html).
- [Spring LDAP `LdapTemplate` API](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/LdapTemplate.html).
