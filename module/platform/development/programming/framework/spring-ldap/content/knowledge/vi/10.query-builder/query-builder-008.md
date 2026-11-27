# Đối chiếu query builder với filter chuỗi trong Spring LDAP

## 1. Cùng một câu hỏi, hai cách viết LDAP Search

Giả sử ứng dụng quản lý nhân sự cần **tìm người dùng có `uid=alice` trong mọi OU con của `ou=people`**, nhưng chỉ lấy tên và email. Với Spring LDAP, ta có thể viết **chuỗi filter LDAP** rồi truyền vào `LdapTemplate`, hoặc dùng **`LdapQueryBuilder`** để mô tả cả truy vấn.

**Cách A — filter chuỗi cố định:**

~~~java
List<String> names = ldapTemplate.search(
        "ou=people",
        "(&(objectClass=inetOrgPerson)(uid=alice))",
        (AttributesMapper<String>) attrs ->
                String.valueOf(attrs.get("cn").get())
);
~~~

**Cách B — query builder:**

~~~java
LdapQuery query = LdapQueryBuilder.query()
        .base("ou=people")
        .searchScope(SearchScope.SUBTREE)
        .attributes("cn", "mail")
        .where("objectClass").is("inetOrgPerson")
        .and("uid").is("alice");

List<String> names = ldapTemplate.search(
        query,
        (AttributesMapper<String>) attrs ->
                String.valueOf(attrs.get("cn").get())
);
~~~

Hai ví dụ cùng thể hiện ý tưởng **lọc entry `inetOrgPerson` với UID xác định**, nhưng không nên coi chúng giống nhau về *mọi tham số*: ví dụ A sử dụng overload đơn giản, dựa vào scope và tập thuộc tính mặc định của overload đó; ví dụ B chỉ rõ scope và những thuộc tính cần trả về. Muốn so sánh kết quả công bằng, phải đồng nhất **base, scope, filter, attributes, giới hạn, bind identity và dữ liệu**.

Bài này nằm trong chương **Query builder** của module **Spring LDAP**. Trọng tâm là khi nào dùng builder, khi nào chuỗi filter vẫn hợp lý, cách tránh LDAP injection, phân biệt filter với DN, cách biểu diễn logic AND/OR, kiểm thử và vận hành trên kết nối TLS có phân quyền.

**Sau bài học, bạn sẽ có thể:**

- So sánh tính dễ đọc, an toàn và khả năng bảo trì giữa hai cách viết.
- Tạo truy vấn với `LdapQueryBuilder` hoặc filter chuỗi đúng cú pháp RFC 4515.
- Dùng các lớp `Filter` để cấu thành filter phức tạp mà không ghép dữ liệu người dùng vào chuỗi.
- Phân biệt escaping **filter value** với escaping **DN/RDN**.
- Kiểm thử xem hai truy vấn thật sự tương đương trên LDAP server hay không.

## 2. Tách ba tầng: mô tả truy vấn, biểu thức filter và thực thi

Một truy vấn LDAP Search chứa nhiều hơn một filter:

~~~text
Ứng dụng
    |
    +-- Base DN                  (tìm từ entry nào?)
    +-- Search scope             (base / one-level / subtree?)
    +-- Filter                   (entry nào thỏa điều kiện?)
    +-- Returning attributes     (lấy những thuộc tính nào?)
    +-- Size / time limits       (giới hạn tài nguyên?)
    |
    v
 LdapQuery hoặc overload của LdapTemplate
    |
    v
 LdapTemplate.search(...)
    |
    v
 ContextSource -> DirContext/JNDI -> LDAP server
    |
    v
 ACL + schema + dữ liệu + matching rules
    |
    v
 Mapper -> kết quả Java
~~~

| Thành phần | Ví dụ | Vai trò |
| --- | --- | --- |
| **Filter chuỗi** | `(&(objectClass=inetOrgPerson)(uid=alice))` | Chỉ biểu thức điều kiện |
| **`Filter` object** | `new EqualsFilter("uid", uid)` | Xây biểu thức điều kiện có cấu trúc, rồi `encode()` |
| **`LdapQueryBuilder`** | `query().base(...).where(...).is(...)` | Xây mô tả base/scope/attributes/filter/limits |
| **`LdapQuery`** | Biến `query` thành phẩm | Mô tả một LDAP Search, chưa thực thi |
| **`LdapTemplate`** | `search(query, mapper)` | Gửi truy vấn và quản lý context/kết quả |
| **`ContextSource`** | `LdapContextSource` | Kết nối LDAP, bind, cấu hình base DN |

**Không có chuyện filter chuỗi tự kết nối LDAP** hoặc builder tự truy cập server. Cả hai cuối cùng đều phải được gửi qua client và được LDAP server đánh giá.

### 2.1. Base DN không nằm trong biểu thức filter

Giả sử cây LDAP:

~~~text
dc=example,dc=org
├── ou=people
│   ├── uid=alice
│   ├── ou=engineering
│   │   └── uid=bob
│   └── ou=sales
│       └── uid=carol
└── ou=groups
    └── cn=developers
~~~

Khi `ContextSource` có base `dc=example,dc=org`, search base tương đối `ou=people` trở thành `ou=people,dc=example,dc=org`. Dù filter có `(uid=alice)`, nó không tìm ở `ou=groups` nếu search base được chọn là `ou=people`.

Tương tự, **ONELEVEL** chỉ xét các entry con trực tiếp; **SUBTREE** xét entry base và mọi hậu duệ. Một filter chuỗi đúng vẫn có thể bỏ sót người dùng ở OU sâu nếu scope không phù hợp.

## 3. Filter chuỗi LDAP: mạnh, phổ biến nhưng dễ dùng sai

LDAP search filter tuân theo cú pháp chuẩn, thường được trình bày dưới dạng biểu thức có ngoặc.

~~~ldap
(uid=alice)
(&(objectClass=inetOrgPerson)(uid=alice))
(|(uid=alice)(uid=bob))
(&(objectClass=inetOrgPerson)(mail=*))
~~~

Các ký hiệu cần nhớ:

| Ký hiệu | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `=` | Equality filter | `(uid=alice)` |
| `&` | AND | `(&(objectClass=person)(uid=alice))` |
| `|` | OR | `(|(uid=alice)(uid=bob))` |
| `!` | NOT | `(!(uid=alice))` |
| `*` | Presence hoặc wildcard substring theo vị trí | `(mail=*)`, `(cn=Ali*)` |
| `>=` / `<=` | So sánh theo ordering matching rule | `(createTimestamp>=20260101000000Z)` |

**Ưu điểm của filter chuỗi** là ngắn gọn, dễ đối chiếu với RFC/LDAP logs và dễ chạy lại bằng `ldapsearch`. Khi filter là hằng số được code review, không chứa giá trị động và truy vấn đơn giản, cách viết này có thể hoàn toàn phù hợp.

**Nhược điểm** bắt đầu khi ứng dụng nối những đoạn biểu thức động: lỗi ngoặc, lỗi logic AND/OR, wildcard bất ngờ, escape sai và khó bảo trì khi thêm điều kiện tùy chọn.

### 3.1. Filter cố định khác filter có đầu vào động

**Hằng số tin cậy:**

~~~java
String filter = "(&(objectClass=inetOrgPerson)(mail=*))";
~~~

**Cần tránh nếu `uid` đến từ HTTP/form:**

~~~java
String unsafeFilter =
        "(&(objectClass=inetOrgPerson)(uid=" + uid + "))";
~~~

Chuỗi thứ hai đưa dữ liệu không tin cậy vào **ngữ pháp filter**. Ngay cả khi lập trình viên chỉ muốn equality, người dùng có thể đưa vào các ký tự đặc biệt khiến bộ lọc bị mở rộng hoặc hỏng cú pháp.

## 4. Query builder: diễn đạt điều kiện thay vì ghép văn bản

`LdapQueryBuilder` là API xây `LdapQuery` theo từng thành phần. Ví dụ:

~~~java
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.SearchScope;
import static org.springframework.ldap.query.LdapQueryBuilder.query;

LdapQuery query = query()
        .base("ou=people")
        .searchScope(SearchScope.SUBTREE)
        .attributes("uid", "cn", "mail")
        .where("objectClass").is("inetOrgPerson")
        .and("uid").is(uid);
~~~

Ý nghĩa từng lời gọi:

1. `query()`: bắt đầu dựng mô tả truy vấn.
2. `base("ou=people")`: chọn gốc tìm kiếm tương đối với base của `ContextSource`.
3. `searchScope(SearchScope.SUBTREE)`: xét mọi hậu duệ trong nhánh, bao gồm base.
4. `attributes(...)`: yêu cầu chỉ những thuộc tính ứng dụng cần đọc.
5. `where(...).is(...)` và `and(...).is(...)`: dựng các điều kiện equality và AND.
6. Biến `query`: kết quả mô tả, **chưa gọi LDAP server**.

So với lọc bằng chuỗi thủ công, builder giúp code review dễ nhận thấy base/scope/attributes và điều kiện. Quan trọng hơn, những giá trị được truyền cho phương thức như `is(uid)` được encode theo ngữ pháp filter thay vì chèn thẳng vào cú pháp LDAP.

> **Giới hạn:** builder giúp tạo biểu thức hợp lệ từ giá trị, nhưng không kiểm tra UID đã tồn tại, account có được phép tìm hay không, attribute có được định nghĩa trong schema không hoặc filter có hiệu năng tốt trên server không.

### 4.1. Chạy truy vấn với LdapTemplate

Một repository có thể trực tiếp thực thi query và ánh xạ kết quả:

~~~java
import java.util.List;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;

import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.SearchScope;
import org.springframework.stereotype.Repository;

import static org.springframework.ldap.query.LdapQueryBuilder.query;

@Repository
public class DirectorySearchRepository {

    private final LdapTemplate ldapTemplate;

    public DirectorySearchRepository(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<String> findDisplayNamesByUid(String uid) {
        if (uid == null || uid.isBlank()) {
            throw new IllegalArgumentException("uid must not be blank");
        }

        LdapQuery q = query()
                .base("ou=people")
                .searchScope(SearchScope.SUBTREE)
                .attributes("cn")
                .where("objectClass").is("inetOrgPerson")
                .and("uid").is(uid);

        return ldapTemplate.search(
                q,
                (AttributesMapper<String>) attrs -> {
                    Attribute cn = attrs.get("cn");
                    return cn == null ? null : String.valueOf(cn.get());
                }
        );
    }
}
~~~

Phương thức `search` thường trả danh sách rỗng nếu không có entry khớp. Nó có thể ném ngoại lệ khi base DN không tồn tại, server không khả dụng, bind thất bại hoặc bị chính sách truy cập từ chối. **Không được biến tất cả lỗi thành danh sách rỗng**.

Nếu nhiều OU chứa cùng một UID, LDAP search có thể trả về nhiều entry. Không nên tự chọn kết quả đầu tiên khi nghiệp vụ đòi hỏi định danh duy nhất.

## 5. So sánh trực tiếp hai cách trên cùng thông số

Để hai cách viết thực sự có thể đối chiếu, đặt cùng **base**, **scope**, **returning attributes**, **filter**, **credentials** và **mapper**.

### 5.1. Chuỗi filter kết hợp SearchControls

~~~java
import java.util.List;
import javax.naming.directory.Attribute;
import javax.naming.directory.SearchControls;

import org.springframework.ldap.core.AttributesMapper;

SearchControls controls = new SearchControls();
controls.setSearchScope(SearchControls.SUBTREE_SCOPE);
controls.setReturningAttributes(new String[] {"cn"});
controls.setCountLimit(100L);
controls.setTimeLimit(5000);

String fixedFilter =
        "(&(objectClass=inetOrgPerson)(uid=alice))";

List<String> fromString = ldapTemplate.search(
        "ou=people",
        fixedFilter,
        controls,
        (AttributesMapper<String>) attrs -> {
            Attribute cn = attrs.get("cn");
            return cn == null ? null : String.valueOf(cn.get());
        }
);
~~~

Đoạn trên giả định đã có biến `ldapTemplate`. Dùng `SearchControls` của JNDI để đặt scope, danh sách thuộc tính và giới hạn. Filter `fixedFilter` là **hằng số** đã biết, không có nối giá trị người dùng.

### 5.2. Cùng truy vấn bằng LdapQueryBuilder

~~~java
import java.util.List;
import javax.naming.directory.Attribute;

import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.SearchScope;
import static org.springframework.ldap.query.LdapQueryBuilder.query;

LdapQuery q = query()
        .base("ou=people")
        .searchScope(SearchScope.SUBTREE)
        .attributes("cn")
        .countLimit(100)
        .timeLimit(5000)
        .where("objectClass").is("inetOrgPerson")
        .and("uid").is("alice");

List<String> fromBuilder = ldapTemplate.search(
        q,
        (AttributesMapper<String>) attrs -> {
            Attribute cn = attrs.get("cn");
            return cn == null ? null : String.valueOf(cn.get());
        }
);
~~~

Trong điều kiện không gặp giới hạn/ACL đặc biệt, hai truy vấn **dự kiến chọn cùng tập entry và thuộc tính**. Kết quả LDAP không mặc định có thứ tự ổn định: khi kiểm thử hãy so sánh **tập DN hoặc giá trị định danh**, không chỉ thứ tự của danh sách.

Hai đoạn mã đều cho thấy: **filter string không nhất thiết thiếu kiểm soát scope hay limits**, vì các tham số đó có thể được cấu hình bằng `SearchControls`. Lợi ích của query builder ở đây là **gom mô tả truy vấn** vào một biểu thức fluent rõ ràng, chứ không phải cho phép một tính năng tìm kiếm hoàn toàn mới.

### 5.3. Bảng đối chiếu ưu và nhược điểm

| Tiêu chí | Filter chuỗi | Query builder |
| --- | --- | --- |
| Hằng số đơn giản | Ngắn, dễ đọc và đối chiếu trực tiếp LDAP filter | Dài hơn nhưng nhất quán API |
| Giá trị động | Phải tự xử lý an toàn nếu ghép chuỗi | Các phép như `is(value)` mã hóa giá trị phù hợp |
| Logic nhiều điều kiện | Dễ sai ngoặc và toán tử khi nối chuỗi | Dễ biểu đạt hơn với builder/filter objects |
| Base, scope, attributes | Đặt riêng trong overload/SearchControls | Cùng nằm trong `LdapQuery` |
| Giới hạn | Dùng SearchControls hoặc API tương ứng | Có thể khai báo count/time limit |
| Tính linh hoạt | Có thể biểu diễn mọi cú pháp filter chuẩn nếu viết đúng | Phụ thuộc những toán tử builder hỗ trợ; có thể kết hợp Filter objects |
| Debug | Chuỗi filter hiện rõ, dễ dùng với ldapsearch | Có thể quan sát biểu thức sinh ra theo API và công cụ thích hợp |
| Schema, ACL, hiệu năng | Vẫn do server quyết định | **Vẫn do server quyết định** |
| Rủi ro injection | Cao nếu nối đầu vào trực tiếp | Giảm đáng kể với API tạo biểu thức/escape value |

**Quy tắc chọn:** ưu tiên builder hoặc các đối tượng `Filter` với dữ liệu đầu vào động; filter chuỗi cố định đã được xem xét vẫn là lựa chọn hợp lý khi đơn giản và không có injection surface.

## 6. Khác biệt cốt lõi: escaping filter value

LDAP filter có cú pháp escaping riêng. Theo cách biểu diễn filter chuỗi, những ký tự sau cần được mã hóa khi chúng xuất hiện **như dữ liệu literal** trong giá trị:

| Ký tự literal | Mã hóa trong LDAP filter value |
| --- | --- |
| `*` | `\2a` |
| `(` | `\28` |
| `)` | `\29` |
| Dấu gạch chéo ngược `\` | `\5c` |
| NUL | `\00` |

Đây là cách escape trong **LDAP filter**, **không phải** DN/RDN. Ngoài các ký tự trên, các byte không hợp lệ trong biểu diễn UTF-8 cần được xử lý theo yêu cầu chuẩn filter và hệ thư viện, không nên chỉ thay ký tự bằng thao tác string đơn giản rồi coi là đã có một encoder toàn diện.

### 6.1. Ví dụ wildcard ngoài ý muốn

Giả sử giao diện cho phép tìm một UID literal. Người dùng nhập ký tự `*`.

**Nếu nối thẳng:**

~~~java
String unsafeFilter = "(uid=" + userProvidedUid + ")";
// userProvidedUid = "*" tạo thành (uid=*).
~~~

Trong LDAP, `(uid=*)` là **presence filter**, có thể khớp rất nhiều entry có thuộc tính UID, hoàn toàn khác yêu cầu “UID bằng đúng ký tự sao”.

**Nếu dùng builder:**

~~~java
LdapQuery q = query()
        .base("ou=people")
        .where("uid").is(userProvidedUid);
~~~

Builder xử lý dấu `*` như **ký tự dữ liệu trong equality value**, tránh vô tình biến nó thành wildcard/presence. Điều này không có nghĩa UID chứa dấu sao chắc chắn hợp lệ theo chính sách nghiệp vụ; validation vẫn cần kiểm tra.

### 6.2. Một ví dụ nhỏ với EqualsFilter

Spring LDAP có lớp `EqualsFilter` để encode filter equality mà không cần tự escape từng ký tự:

~~~java
import org.springframework.ldap.filter.EqualsFilter;

String encoded = new EqualsFilter("uid", "a*b").encode();
// Dấu * trong giá trị sẽ được escape, thay vì trở thành wildcard.
~~~

Bộ mã hóa filter của thư viện giúp cách xử lý nhất quán. **Không escape thủ công rồi lại truyền chuỗi đã escape vào builder**, vì có thể gây double escaping và tìm sai dữ liệu.

### 6.3. Ký tự dấu phẩy khác nhau giữa filter và DN

Trong equality filter `(cn=Nguyen, Alice)`, dấu phẩy không tự phân chia cấu trúc filter. Nhưng trong DN, dấu phẩy là ký tự phân cách RDN và phải được xử lý khi nằm trong **giá trị** của một RDN.

~~~java
import javax.naming.Name;
import org.springframework.ldap.support.LdapNameBuilder;

Name dn = LdapNameBuilder.newInstance("ou=people")
        .add("cn", "Nguyen, Alice")
        .build();
~~~

`LdapNameBuilder` tạo/escape DN theo cấu trúc tên. **Không sử dụng cơ chế escape LDAP filter thay cho cơ chế escape DN**, và không nối DN bằng phép cộng chuỗi không kiểm soát.

## 7. AND, OR và các điều kiện lồng nhau

Với filter đơn giản, cả hai cách viết đều dễ hiểu:

~~~ldap
(&(objectClass=inetOrgPerson)(uid=alice))
~~~

Builder tương đương:

~~~java
LdapQuery q = query()
        .base("ou=people")
        .where("objectClass").is("inetOrgPerson")
        .and("uid").is("alice");
~~~

Khi nghiệp vụ phức tạp hơn, ví dụ **người dùng thuộc inetOrgPerson và UID là alice hoặc bob**, filter có hai mức nhóm:

~~~ldap
(&(objectClass=inetOrgPerson)(|(uid=alice)(uid=bob)))
~~~

Không nên ghép các nhóm bằng những biểu thức cộng chuỗi khó đọc. Các **đối tượng filter** của Spring LDAP thể hiện logic lồng nhau rõ ràng:

~~~java
import org.springframework.ldap.filter.AndFilter;
import org.springframework.ldap.filter.OrFilter;
import org.springframework.ldap.filter.EqualsFilter;

OrFilter acceptedUids = new OrFilter();
acceptedUids.or(new EqualsFilter("uid", "alice"));
acceptedUids.or(new EqualsFilter("uid", "bob"));

AndFilter combined = new AndFilter();
combined.and(new EqualsFilter("objectClass", "inetOrgPerson"));
combined.and(acceptedUids);

String encodedFilter = combined.encode();
~~~

Ta có thể dùng biểu thức đã encode với overload nhận chuỗi filter, cùng các thuộc tính và scope phù hợp:

~~~java
import javax.naming.directory.SearchControls;
import org.springframework.ldap.core.AttributesMapper;

SearchControls controls = new SearchControls();
controls.setSearchScope(SearchControls.SUBTREE_SCOPE);
controls.setReturningAttributes(new String[] {"uid", "cn"});

List<String> names = ldapTemplate.search(
        "ou=people",
        encodedFilter,
        controls,
        (AttributesMapper<String>) attrs ->
                String.valueOf(attrs.get("cn").get())
);
~~~

**Phân biệt ba thứ:**

- **Filter chuỗi viết tay:** biểu thức được lập trình viên tự cấu thành.
- **`Filter.encode()`:** cũng trả chuỗi filter nhưng được tạo từ các đối tượng có cấu trúc.
- **`LdapQueryBuilder`:** mô tả toàn bộ yêu cầu tìm kiếm; một số điều kiện có thể được tạo qua API fluent, còn điều kiện rất phức tạp có thể được xây bằng đối tượng Filter phù hợp.

Chọn API dựa trên yêu cầu thực tế và phiên bản Spring LDAP. Không bắt buộc phải ép mọi biểu thức nhiều mức vào một chuỗi nối tay hoặc một chuỗi phương thức fluent rất khó đọc.

### 7.1. Cần hiểu grouping, không chỉ escape

Escape dữ liệu không giúp sửa một lỗi logic. Ví dụ hai biểu thức khác nhau:

~~~ldap
(&(objectClass=inetOrgPerson)(|(uid=alice)(uid=bob)))
(|(&(objectClass=inetOrgPerson)(uid=alice))(uid=bob))
~~~

Biểu thức thứ hai **có thể** chọn entry `uid=bob` ngay cả khi entry đó không có `objectClass=inetOrgPerson`, vì nhánh OR bên phải chỉ kiểm tra UID. Dùng builder/filter objects giúp biểu diễn grouping tốt hơn, nhưng người viết vẫn phải hiểu yêu cầu nghiệp vụ và kiểm thử kết quả.

## 8. Khi nào vẫn nên sử dụng filter chuỗi?

Builder **không đồng nghĩa mọi filter chuỗi đều sai**. Có những trường hợp chuỗi hợp lệ là một công cụ tốt:

1. **Truy vấn hằng số, nhỏ, dễ kiểm tra:** chẳng hạn `(objectClass=organizationalUnit)` trong công cụ quản trị nội bộ.
2. **Đối chiếu với công cụ LDAP:** sao chép chuỗi cố định sang `ldapsearch` để chẩn đoán.
3. **Một số dạng filter nâng cao:** có thể thuận tiện biểu đạt cú pháp đặc thù hoặc extensible matching khi API builder của phiên bản thư viện chưa hỗ trợ thuận tay.

Tuy nhiên, nếu một biểu thức filter chứa **dữ liệu từ HTTP, CLI, file hoặc nguồn ngoài**, không chèn thẳng vào chuỗi. Hãy dùng API encode/filter builder thích hợp hoặc cơ chế tham số hóa an toàn được JNDI/LDAP client phiên bản đó hỗ trợ. Đừng giả định `String.format(...)` hoặc `replace(...)` là cơ chế binding tự động escape.

**Ví dụ filter cố định hợp lý:**

~~~java
String staticFilter = "(&(objectClass=inetOrgPerson)(mail=*))";
~~~

**Ví dụ không nên dùng cho dữ liệu người dùng:**

~~~java
String unsafeFilter =
        "(&(objectClass=inetOrgPerson)(uid=" + inputUid + "))";
~~~

Với filter cực kỳ đặc thù, việc dùng chuỗi vẫn đòi hỏi review theo RFC 4515, kiểm tra schema/matching rule và bảo vệ các vị trí có giá trị động bằng encoder đúng ngữ pháp.

## 9. Thuộc tính, giới hạn và search scope: chỗ builder dễ quan sát hơn

Filter chỉ quyết định **entry nào phù hợp**, không thể quyết định chính xác số thuộc tính được trả về hoặc cách phân trang.

Với query builder:

~~~java
LdapQuery limited = query()
        .base("ou=people")
        .searchScope(SearchScope.SUBTREE)
        .attributes("uid", "cn")
        .countLimit(100)
        .timeLimit(5000)
        .where("objectClass").is("inetOrgPerson");
~~~

Với filter chuỗi và SearchControls, vẫn cấu hình được tương đương:

~~~java
SearchControls controls = new SearchControls();
controls.setSearchScope(SearchControls.SUBTREE_SCOPE);
controls.setReturningAttributes(new String[] {"uid", "cn"});
controls.setCountLimit(100L);
controls.setTimeLimit(5000);

String filter = "(objectClass=inetOrgPerson)";
~~~

**Lưu ý về giới hạn:**

- `countLimit(100)` và `setCountLimit(100L)` không bảo đảm hệ thống đã nhận **toàn bộ** tập kết quả.
- `timeLimit(5000)` là giới hạn ở lớp thao tác tìm kiếm; timeout mở kết nối/TCP read là vấn đề khác.
- LDAP server có thể áp giới hạn chặt hơn, trả lỗi `sizeLimitExceeded` hoặc `timeLimitExceeded`.
- Truy vấn rất lớn có thể cần **paging** bằng LDAP control phù hợp nếu server hỗ trợ. Count limit không tự động chuyển thành paging.
- Chỉ yêu cầu thuộc tính cần thiết để giảm dữ liệu đi qua mạng. Thuộc tính vận hành như `createTimestamp` có thể phải yêu cầu tường minh.

Lợi ích của builder là tập trung nhiều quyết định vào **một mô tả truy vấn** dễ review, nhưng bản thân builder không lập index, không sửa lỗi ACL hoặc tối ưu tự động mọi truy vấn.

## 10. Cấu hình ContextSource và danh tính bind

Để ví dụ chạy trên ứng dụng Spring, cần khai báo `LdapContextSource` và `LdapTemplate`. Ví dụ đơn giản:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.core.support.LdapContextSource;

@Configuration
public class LdapConfiguration {
    @Bean
    public LdapContextSource ldapContextSource(
            @Value("${app.ldap.url}") String url,
            @Value("${app.ldap.base}") String base,
            @Value("${app.ldap.bind-dn}") String bindDn,
            @Value("${app.ldap.bind-password}") String password) {

        LdapContextSource source = new LdapContextSource();
        source.setUrl(url);
        source.setBase(base);
        source.setUserDn(bindDn);
        source.setPassword(password);
        return source;
    }

    @Bean
    public LdapTemplate ldapTemplate(LdapContextSource ldapContextSource) {
        return new LdapTemplate(ldapContextSource);
    }
}
~~~

~~~yaml
# application.yml: minh họa với LDAP server thử nghiệm
app:
  ldap:
    url: ${LDAP_URL:ldaps://ldap.example.org:636}
    base: dc=example,dc=org
    bind-dn: ${LDAP_BIND_DN}
    bind-password: ${LDAP_BIND_PASSWORD}
~~~

Một `ContextSource` được cấu hình với base DN `dc=example,dc=org` thường hiểu `search("ou=people", ...)` như tìm từ `ou=people,dc=example,dc=org`. Đừng đặt lặp lại hậu tố đó vào vị trí DN tương đối khi chưa kiểm tra.

Nếu dùng Spring Boot với cơ chế auto-configuration LDAP, có thể cấu hình các property `spring.ldap.*` phù hợp thay vì bean thủ công; tránh khai báo hai bean cùng trách nhiệm mà không rõ repository nhận cái nào.

Tài khoản chỉ tìm kiếm nên có **quyền đọc tối thiểu** trên những OU cần thiết; Spring LDAP builder không cấp quyền. Cũng không nên coi query build thành công là bằng chứng LDAP server đang hoạt động: kết nối và bind thực sự thường chỉ được kiểm chứng khi thực hiện một thao tác.

## 11. Đối chiếu kết quả với ldapsearch

Hãy dùng máy chủ thử nghiệm và dữ liệu giả. Một truy vấn tương đương về base/scope/filter/attributes:

~~~bash
ldapsearch -LLL -x \
  -H "ldaps://ldap.example.org:636" \
  -D "cn=directory-reader,ou=system,dc=example,dc=org" -W \
  -b "ou=people,dc=example,dc=org" -s sub \
  "(&(objectClass=inetOrgPerson)(uid=alice))" \
  cn mail
~~~

Trong công cụ này:

- `-H` chọn URL LDAP/LDAPS.
- `-D` và `-W` dùng bind DN, hỏi mật khẩu qua lời nhắc.
- `-b` là **base DN đầy đủ**.
- `-s sub` chọn subtree scope.
- Chuỗi filter được đặt trong dấu ngoặc kép để shell không diễn giải ký tự đặc biệt.
- `cn mail` là những thuộc tính yêu cầu trả về.

Nếu lệnh `ldapsearch` thành công nhưng Java trả khác kết quả, cần so sánh bind identity, base DN hiệu lực, scope, filter, returning attributes, server endpoint và limits. Hai truy vấn trông giống nhau về filter chưa đủ để khẳng định chúng tương đương.

### 11.1. Đừng lẫn DN với filter

LDAP filter `(uid=alice)` là một điều kiện **chọn entry**. DN `uid=alice,ou=people,dc=example,dc=org` là **vị trí của một entry**. Khi đã biết DN cụ thể, `LdapTemplate.lookup(...)` có thể phù hợp hơn một subtree search. Khi UID nằm ở OU chưa biết, query với subtree và filter phù hợp giúp tìm DN đó.

## 12. Bảo mật và lỗi vận hành: cả hai cách đều cần phòng vệ

Không có cách xây filter nào tự thay thế TLS, ACL, schema và kiểm soát tài nguyên.

### 12.1. TLS và thông tin xác thực

- Sử dụng `ldaps://` với xác minh chứng chỉ và hostname, hoặc StartTLS được cấu hình thực sự **trước** simple bind trên đường truyền cần bảo vệ.
- Chỉ đặt URL `ldap://` **không** tự bật StartTLS.
- Mật khẩu bind lấy từ nguồn secrets an toàn, không hard-code, không log.
- Nếu dùng pooling, xác minh trạng thái kết nối, danh tính bind và tương thích TLS/StartTLS; không tái sử dụng nhầm context đã bind bằng người dùng khác.

### 12.2. Các lỗi cần phân biệt

| Triệu chứng / mã | Nhóm nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| Kết quả rỗng | Không có entry khớp hoặc base/scope/ACL không bao phủ | Kiểm tra DN, filter, quyền và dữ liệu |
| LDAP **87 / filterError** | Filter sai cú pháp | Xác minh dấu ngoặc, cấu trúc và escaping |
| LDAP **18 / inappropriateMatching** | Attribute không hỗ trợ matching rule tương ứng | Đối chiếu schema |
| LDAP **32 / noSuchObject** | Base DN không tồn tại hoặc không thể thấy | Kiểm tra DN tương đối/tuyệt đối |
| LDAP **50 / insufficientAccessRights** | Tài khoản bind thiếu quyền | Kiểm tra ACL, không tự tăng quyền |
| LDAP **3 / timeLimitExceeded** | Vượt thời gian tìm kiếm | Thu hẹp base/filter, kiểm tra index và limits |
| LDAP **4 / sizeLimitExceeded** | Vượt giới hạn kết quả | Xem xét paging/giới hạn phù hợp |
| TLS/bind/connection failure | Endpoint, credentials, chứng chỉ hoặc mạng không hợp lệ | Kiểm tra hạ tầng, không quy thành “không tìm thấy” |

Thông báo cụ thể và cách server bảo vệ thông tin có thể khác nhau. Không trả nguyên chuỗi diagnostic message nhạy cảm từ LDAP server ra API công khai; log thông tin tối thiểu như loại thao tác, mã lỗi và correlation ID.

### 12.3. Hiệu năng và rủi ro query quá rộng

Ngay cả query builder được dùng đúng vẫn có thể tạo filter `(objectClass=*)` trên base rất rộng, gây tải lớn. Hãy chọn base hẹp, scope phù hợp, thuộc tính có index nếu khả thi, giới hạn kích thước/timeout và sử dụng paging khi có yêu cầu đọc tập lớn.

Escape ký tự không thay thế chính sách **allowlist attribute**, validation đầu vào, kiểm soát quyền người gọi hay giới hạn độ dài dữ liệu. Không cho client tùy ý chọn base DN hoặc attribute name chỉ vì builder không dễ bị phá ngoặc.

## 13. Kiểm thử tính tương đương và chống filter injection

Một bộ test tốt nên kiểm tra **cả phần dựng truy vấn và kết quả chạy trên LDAP server**. Mock chỉ có thể xác nhận Java code gọi phương thức mong muốn, không chứng minh ACL hoặc matching rule server có hiệu lực.

### 13.1. Thử dữ liệu biên của filter

| Giá trị UID đầu vào | Filter chuỗi ghép tay | Builder equality |
| --- | --- | --- |
| `alice` | Thường hoạt động như kỳ vọng | Tìm literal `alice` |
| `*` | `(uid=*)` là presence filter, có thể mở rộng kết quả | Tìm literal `*` sau khi escape |
| `a*b` | Có thể thành substring filter ngoài ý muốn | Tìm literal `a*b` |
| Chuỗi chứa `(` hoặc `)` | Có nguy cơ hỏng cú pháp | Escaping các ký tự dữ liệu |
| Chuỗi có dấu gạch chéo ngược | Dễ escape sai | Builder encode giá trị phù hợp |

Kiểm tra thêm đầu vào rỗng, quá dài, Unicode hợp lệ và các giá trị vi phạm quy tắc đặt tên của ứng dụng. Dùng dữ liệu giả và không dựa vào tài khoản thật để tạo ví dụ ký tự đặc biệt.

### 13.2. Unit test cho việc encode dấu sao

Một phép kiểm tra gọn, không cần kết nối LDAP:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.ldap.filter.EqualsFilter;

import static org.junit.jupiter.api.Assertions.assertEquals;

class LdapFilterEncodingTest {

    @Test
    void literalAsteriskIsEscaped() {
        String filter = new EqualsFilter("uid", "a*b").encode();
        assertEquals("(uid=a\\2ab)", filter);
    }
}
~~~

Trong Java string, `\\` đại diện một dấu backslash thực tế. Assertion kiểm tra dấu sao được biểu diễn là escape hex, **không** phải ký tự wildcard. Nếu kết quả encode theo phiên bản thư viện khác cách biểu diễn escape nhưng vẫn đúng chuẩn, nên kiểm tra ngữ nghĩa thay vì cố gắn mọi chi tiết serialization vào test.

### 13.3. Integration test cho hai cách viết

Với thư mục thử nghiệm có các entry ở nhiều OU con:

1. Cấu hình URL, base DN, bind credentials và ACL như nhau cho cả hai truy vấn.
2. Dùng filter hằng số và `SearchControls.SUBTREE_SCOPE`; chạy `ldapTemplate.search(...)`.
3. Dùng `LdapQueryBuilder` với cùng base, scope, filter, attributes và limits; chạy lần nữa.
4. So sánh tập định danh/DN, không dựa vào thứ tự LDAP trả về.
5. Thử người dùng ở OU con sâu để chứng minh scope SUBTREE cần thiết.
6. Thử `*` và `a*b` như UID literal; builder không được mở rộng filter thành presence/substring ngoài ý muốn.
7. Thử sai base DN, tài khoản thiếu quyền và lỗi TLS để chứng minh không phải mọi bất thường đều là lỗi cấu trúc filter.
8. Giới hạn count/time thấp trên tập dữ liệu phù hợp, xác minh ứng dụng không coi kết quả chưa hoàn tất là đầy đủ.

### 13.4. Cần đọc lại các thuộc tính đa trị đúng cách

Nếu kết quả chứa nhiều `telephoneNumber` hoặc `description`, mapper chỉ gọi `Attribute.get()` sẽ đọc một giá trị. Để kiểm thử tập kết quả đầy đủ cần duyệt `Attribute.getAll()` theo hợp đồng JNDI. Đây là vấn đề **mapping**, không phải lỗi filter string hay query builder.

## 14. Thực hành: chuyển từ chuỗi filter sang builder

**Bối cảnh:** một dịch vụ REST tìm hồ sơ theo UID trong `ou=people`. Ban đầu code sử dụng chuỗi:

~~~java
String filter =
        "(&(objectClass=inetOrgPerson)(uid=" + inputUid + "))";
~~~

Thực hiện các bước:

1. Viết ra query search đầy đủ: base DN, scope SUBTREE, filter, returning attributes và giới hạn.
2. Xác định chính xác vì sao phép nối `inputUid` có thể làm thay đổi nghĩa filter khi đầu vào chứa `*`.
3. Thay bằng `LdapQueryBuilder.query()` với `.base("ou=people")`, `.searchScope(SearchScope.SUBTREE)` và `.where("uid").is(inputUid)`.
4. Bổ sung điều kiện `objectClass=inetOrgPerson` và chỉ lấy `uid`, `cn`, `mail`.
5. Xây query với count/time limit phù hợp; nếu cần toàn bộ dữ liệu, mô tả lý do cần paging thay vì chỉ tăng limit.
6. Xây một filter gồm OR của hai UID và AND với object class bằng `OrFilter` / `AndFilter` / `EqualsFilter`; không tự nối ngoặc.
7. Kiểm thử hai cách trên dữ liệu thử nghiệm tại nhiều cấp OU; so sánh tập entry khi đầu vào là UID thông thường.
8. Thử UID có dấu sao và dấu ngoặc để xác nhận code mới coi chúng là literal, không mở rộng điều kiện.
9. Kiểm tra LDAPS, truststore, tài khoản read-only và xử lý ngoại lệ khi server từ chối hoặc không kết nối được.
10. Ghi lý do chọn builder hoặc filter hằng số cho từng use case, không đưa dữ liệu người dùng không tin cậy vào chuỗi filter thủ công.

**Câu hỏi tự kiểm tra:**

1. Vì sao `LdapQuery` không phải chính là một chuỗi filter?
2. Hai overload `ldapTemplate.search(...)` có cùng chuỗi điều kiện nhưng scope khác nhau có thể trả cùng kết quả không?
3. Vì sao `(uid=*)` khác với equality của một UID có giá trị literal `*`?
4. Cách escaping của LDAP filter khác escaping DN/RDN thế nào?
5. Khi OR hai UID trong một điều kiện object class, grouping có vai trò gì?
6. Lợi ích chính của `LdapQueryBuilder` là gì và nó **không** giúp giải quyết vấn đề nào?
7. Khi nào filter chuỗi cố định là lựa chọn chấp nhận được?
8. Vì sao cần so sánh base, scope, returning attributes, ACL và limits để kiểm chứng hai truy vấn tương đương?
9. Tại sao count limit không chứng minh client đã đọc toàn bộ subtree?
10. Vì sao chỉ test encode filter không đủ để xác nhận query hoạt động trên LDAP server thực tế?

## 15. Tổng kết

**Filter chuỗi** mô tả **điều kiện** LDAP dưới dạng văn bản; **`LdapQueryBuilder`** giúp mô tả **toàn bộ truy vấn** gồm base, scope, filter, thuộc tính trả về và giới hạn. **`LdapTemplate`** là thành phần thực thi thông qua `ContextSource`. Filter chuỗi **cố định, đáng tin cậy** vẫn hữu ích, nhưng việc nối giá trị động trực tiếp dễ gây sai cú pháp hoặc LDAP injection. Với dữ liệu từ bên ngoài, ưu tiên builder hoặc các lớp `Filter` như `EqualsFilter`, `AndFilter` và `OrFilter` để giữ cấu trúc và escaping có kiểm soát. Dù chọn cách nào, kết quả cuối cùng vẫn phụ thuộc vào DN, search scope, schema, matching rules, ACL và dữ liệu của server. Kết hợp TLS được xác minh, quyền tối thiểu, giới hạn tìm kiếm và kiểm thử tích hợp là nền tảng để tra cứu LDAP an toàn, rõ ràng và dễ bảo trì.
