# Xây dựng bộ lọc bằng LdapQueryBuilder

Trong **Spring Data LDAP**, một truy vấn tìm entry không chỉ là một chuỗi điều kiện. Ứng dụng phải xác định **search base**, **search scope**, **LDAP filter**, giới hạn thời gian/số kết quả và tập thuộc tính cần trả về. Spring LDAP cung cấp `LdapQueryBuilder` để mô tả các thành phần này bằng API fluent có kiểu rõ ràng, sau đó truyền đối tượng `LdapQuery` cho `LdapTemplate` hoặc các API tìm kiếm tương ứng.

Bài thuộc chương **Bộ lọc**, tập trung vào chủ đề **“Xây dựng bộ lọc bằng LdapQueryBuilder”**. Người học sẽ biết cách dựng truy vấn từ đơn giản đến có nhóm AND/OR/NOT, lựa chọn equality/presence/substring/ordering, kiểm soát base và scope, giới hạn dữ liệu, chọn thuộc tính trả về, xử lý đầu vào không đáng tin và kiểm thử filter. Các ví dụ đặt trong ngữ cảnh **SPRING_DATA_LDAP**: truy cập directory bằng Java/Spring, ánh xạ entry theo DN, `objectClass` và schema, sử dụng repository/`LdapTemplate`, bảo vệ filter và kiểm soát quyền truy cập.

**Ý chính:** `LdapQueryBuilder` tạo **mô tả một LDAP search**. Nó không tự thực hiện search, không tự cấp quyền, không biến LDAP thành SQL và không bảo đảm mọi filter đều có hiệu năng tốt trên mọi directory server.

## 1. LdapQueryBuilder nằm ở đâu trong luồng truy vấn?

Một yêu cầu tìm user theo UID đi qua các bước:

```text
Input nghiệp vụ
  username = "u1001"
       │
       ▼
LdapQueryBuilder
  base + scope + filter + limits + attributes
       │
       ▼
LdapQuery
       │
       ▼
LdapTemplate.search(query, mapper)
       │
       ▼
ContextSource / JNDI
       │
       ▼
LDAP server
  schema + matching rules + ACL + indexes
       │
       ▼
AttributesMapper / ContextMapper / ODM
       │
       ▼
Java DTO hoặc entity
```

Mỗi thành phần có một trách nhiệm:

| Thành phần | Trách nhiệm |
|---|---|
| `LdapQueryBuilder` | Dựng cấu hình và điều kiện cho LDAP search |
| `LdapQuery` | Giữ base, scope, filter, limit và thuộc tính trả về |
| `LdapTemplate` | Thực hiện operation LDAP |
| `ContextSource` | Cung cấp context/kết nối với directory |
| LDAP server | Đánh giá filter theo schema, matching rule và ACL |
| Mapper/ODM | Chuyển entry/attributes thành Java object |

`LdapQueryBuilder` thuộc package `org.springframework.ldap.query`. Cách bắt đầu phổ biến:

```java
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.SearchScope;

import static org.springframework.ldap.query.LdapQueryBuilder.query;
```

Hàm `query()` được static import từ `LdapQueryBuilder` để code ngắn hơn. Nếu không muốn static import, có thể gọi `LdapQueryBuilder.query()`.

## 2. LDAP search gồm những gì?

Trước khi dựng filter, hãy phân biệt các tham số của một LDAP search:

```text
Context base: dc=example,dc=org
       │
       └── Search base: ou=people
               │
               ├── Scope: SUBTREE
               │
               ├── Filter:
               │   (&(objectClass=inetOrgPerson)(uid=u1001))
               │
               ├── Requested attributes:
               │   uid, cn, mail
               │
               ├── Count limit: 100
               └── Time limit: 3000 ms
```

| Tham số | Ý nghĩa | Ví dụ |
|---|---|---|
| Context base | Base được cấu hình trong `ContextSource` | `dc=example,dc=org` |
| Search base | Điểm bắt đầu tương đối với context base | `ou=people` |
| Search scope | Độ sâu tìm kiếm | `ONELEVEL` hoặc `SUBTREE` |
| Filter | Điều kiện chọn entry | `(&(objectClass=inetOrgPerson)(uid=u1001))` |
| Attributes | Thuộc tính server cần trả về | `uid`, `cn`, `mail` |
| Count limit | Giới hạn số entry | `100` |
| Time limit | Giới hạn thời gian search | `3000` ms |

**Search base không phải filter.** Ví dụ `ou=people` giới hạn vị trí tìm kiếm, còn `(uid=u1001)` chọn entry theo thuộc tính. Một filter chính xác nhưng base quá rộng vẫn có thể làm server phải tìm kiếm nhiều dữ liệu.

## 3. Tạo truy vấn đơn giản với where và is

Giả sử directory có entry:

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

Muốn tìm entry có `objectClass=inetOrgPerson` và `uid=u1001`:

```java
LdapQuery userQuery = query()
        .base("ou=people")
        .searchScope(SearchScope.SUBTREE)
        .where("objectClass").is("inetOrgPerson")
        .and("uid").is("u1001");
```

Filter tương ứng có dạng:

```ldap
(&(objectClass=inetOrgPerson)(uid=u1001))
```

Giải thích:

- `query()` tạo một builder mới.
- `base("ou=people")` chọn nhánh user.
- `searchScope(SearchScope.SUBTREE)` tìm trong OU và các nhánh con.
- `where("objectClass").is(...)` tạo điều kiện đầu tiên.
- `and("uid").is(...)` thêm điều kiện AND.

**Phải chỉ định ít nhất một điều kiện filter.** Một builder chỉ có base/scope nhưng không có filter chưa phải truy vấn hoàn chỉnh. Hãy thêm điều kiện `objectClass` hoặc một điều kiện khác đủ chọn lọc để tránh tìm quá rộng.

## 4. Chọn base DN và search scope

`LdapQueryBuilder` cho phép đặt search base bằng `String` hoặc `javax.naming.Name`:

```java
LdapQuery request = query()
        .base("ou=people")
        .searchScope(SearchScope.ONELEVEL)
        .where("objectClass").is("inetOrgPerson");
```

Nếu `ContextSource` đã cấu hình base `dc=example,dc=org`, base `ou=people` thường được hiểu tương đối theo context base. Search DN thực tế là:

```text
ou=people,dc=example,dc=org
```

Các giá trị scope:

| SearchScope | Phạm vi | Trường hợp dùng |
|---|---|---|
| `OBJECT` | Chính entry tại search base | Kiểm tra một entry đã biết DN |
| `ONELEVEL` | Các entry con trực tiếp | OU có user nằm ngay dưới |
| `SUBTREE` | Base và mọi descendant | User được chia thành nhiều OU con |

Ví dụ:

```java
// Chỉ các entry con trực tiếp của ou=people.
LdapQuery directPeople = query()
        .base("ou=people")
        .searchScope(SearchScope.ONELEVEL)
        .where("objectClass").is("inetOrgPerson");

// Tìm cả trong các OU con.
LdapQuery allPeople = query()
        .base("ou=people")
        .searchScope(SearchScope.SUBTREE)
        .where("objectClass").is("inetOrgPerson");
```

`SUBTREE` không có nghĩa tìm xuyên mọi naming context, mọi domain hoặc toàn forest. Directory server chỉ trả dữ liệu trong phạm vi mà endpoint có thể phục vụ, theo referral, ACL và topology. Chọn scope nhỏ nhất đáp ứng nghiệp vụ.

### Khi nào dùng Name thay cho String?

Nếu base DN được dựng từ các thành phần, dùng `LdapNameBuilder` để tránh tự nối RDN:

```java
import javax.naming.Name;
import org.springframework.ldap.support.LdapNameBuilder;

Name peopleBase = LdapNameBuilder.newInstance("dc=example,dc=org")
        .add("ou", "people")
        .build();

LdapQuery queryByName = query()
        .base(peopleBase)
        .searchScope(SearchScope.SUBTREE)
        .where("objectClass").is("inetOrgPerson");
```

Cần hiểu DN trong `ContextSource` và DN tương đối trong query để không ghép base hai lần. Escaping DN theo cú pháp RDN khác escaping giá trị LDAP filter.

## 5. Giới hạn kết quả, thời gian và thuộc tính trả về

Builder hỗ trợ các tham số tìm kiếm:

```java
LdapQuery activeUsers = query()
        .base("ou=people")
        .searchScope(SearchScope.SUBTREE)
        .countLimit(100)
        .timeLimit(3000)
        .attributes("uid", "cn", "mail")
        .where("objectClass").is("inetOrgPerson")
        .and("employeeStatus").is("active");
```

| Method | Tác dụng | Điểm cần nhớ |
|---|---|---|
| `countLimit(int)` | Đặt giới hạn số entry trả về | `0` nghĩa không đặt limit ở query này |
| `timeLimit(int)` | Đặt giới hạn thời gian search | Đơn vị là millisecond theo JNDI search controls |
| `attributes(String...)` | Chỉ định attribute cần trả về | Mặc định thường là tất cả attribute |
| `base(String/Name)` | Chọn search base | Base tương đối theo context source |
| `searchScope(SearchScope)` | Chọn phạm vi tìm | Default builder là `SUBTREE` trong API hiện hành |

Các giới hạn ở query không thay thế chính sách của server. Server có thể đặt size limit/time limit thấp hơn, trả referral hoặc ném lỗi khi kết quả bị cắt. **Không coi danh sách trả về là đầy đủ nếu operation kết thúc bằng size-limit/time-limit error hoặc partial result.**

`countLimit` cũng không phải cơ chế phân trang theo offset. Nếu cần duyệt tập lớn, phải dùng cơ chế paging phù hợp và xử lý cookie/giới hạn server.

### Chỉ lấy các attribute cần thiết

Nếu endpoint chỉ hiển thị UID, tên và email, không cần lấy toàn bộ attribute:

```java
LdapQuery summaryQuery = query()
        .base("ou=people")
        .attributes("uid", "cn", "mail")
        .where("objectClass").is("inetOrgPerson");
```

Giới hạn attribute giúp giảm payload, memory và nguy cơ vô tình đọc dữ liệu nhạy cảm. Nếu cần operational attribute hoặc binary attribute, phải xác định riêng theo server và quyền được cấp.

## 6. Các phép so sánh mà ConditionCriteria hỗ trợ

Sau `where("attribute")`, `ConditionCriteria` cung cấp các phép tạo filter phổ biến:

| Method | LDAP filter | Ý nghĩa |
|---|---|---|
| `is(value)` | `(uid=u1001)` | Equality |
| `isPresent()` | `(mail=*)` | Attribute tồn tại |
| `not().is(value)` | `(!(sn=Nguyen))` | Phủ định equality |
| `like(pattern)` | `(cn=An*Nguyen)` | Substring với wildcard |
| `whitespaceWildcardsLike(text)` | `(cn=An*Nguyen)` | Thay khoảng trắng bằng wildcard |
| `gte(value)` | `(modifyTimestamp>=...)` | Greater-than-or-equal |
| `lte(value)` | `(modifyTimestamp<=...)` | Less-than-or-equal |

Ví dụ:

```java
LdapQuery withMail = query()
        .base("ou=people")
        .where("mail").isPresent();

LdapQuery surnameNotNguyen = query()
        .base("ou=people")
        .where("sn").not().is("Nguyen");

LdapQuery namePrefix = query()
        .base("ou=people")
        .where("cn").like("An*");

LdapQuery updatedAfter = query()
        .base("ou=people")
        .where("modifyTimestamp").gte("20261126000000Z");
```

**Không suy rằng mọi phép so sánh Java đều tương ứng với LDAP.** `gte`/`lte` cần attribute có ordering matching rule phù hợp. `like` cần substring matching rule. Server có thể phân biệt hoa/thường hoặc chuẩn hóa giá trị theo schema. Đặc biệt `modifyTimestamp` là operational attribute trên nhiều directory; quyền đọc/search và định dạng timestamp cần được kiểm chứng.

### LIKE không giống SQL LIKE

Trong LDAP filter, `*` là wildcard cho substring. Ví dụ `(cn=An*)` tìm giá trị bắt đầu bằng `An`; `(cn=*Nguyen)` tìm giá trị kết thúc bằng `Nguyen`; `(cn=*Ng*)` tìm chuỗi có chứa `Ng`.

`like("An*")` cho phép wildcard có chủ đích trong pattern. Nếu người dùng nhập chuỗi tự do, không được mặc định dấu `*` của họ nên trở thành wildcard. Hãy xác định rõ nghiệp vụ là **tìm chính xác** hay **tìm theo pattern**, validate pattern và kiểm thử ký tự đặc biệt.

## 7. Kết hợp điều kiện AND

Để tìm người thuộc class `inetOrgPerson`, có họ Nguyen và có email:

```java
LdapQuery query = query()
        .base("ou=people")
        .searchScope(SearchScope.SUBTREE)
        .where("objectClass").is("inetOrgPerson")
        .and("sn").is("Nguyen")
        .and("mail").isPresent();
```

Filter tương ứng:

```ldap
(&(objectClass=inetOrgPerson)(sn=Nguyen)(mail=*))
```

Tất cả điều kiện phải khớp. Với nhiều điều kiện AND, mỗi cặp attribute/value được thêm bằng `and(...)`.

Một số lỗi thường gặp:

- Viết `and("sn").is("Nguyen")` trước khi đã gọi `where(...)`.
- Dùng tên Java property thay vì tên LDAP attribute thực tế.
- Quên điều kiện `objectClass` trong schema có nhiều loại entry.
- Dùng `isPresent()` rồi hiểu nhầm là giá trị không rỗng hoặc có định dạng hợp lệ. Nó chỉ kiểm tra attribute hiện diện theo filter LDAP.

## 8. Kết hợp OR và nhóm điều kiện lồng nhau

Khi muốn tìm người có họ Nguyen **hoặc** tên An, có thể dùng `or(String)`:

```java
LdapQuery query = query()
        .base("ou=people")
        .where("objectClass").is("inetOrgPerson")
        .and(query()
                .where("sn").is("Nguyen")
                .or("givenName").is("An"));
```

Filter tương ứng:

```ldap
(&(objectClass=inetOrgPerson)(|(sn=Nguyen)(givenName=An)))
```

`ContainerCriteria` hỗ trợ AND/OR với một điều kiện lồng nhau. Cách này rất quan trọng để giữ đúng thứ tự logic.

Ví dụ nghiệp vụ: **(họ Nguyen hoặc tên An) và có email**:

```java
LdapQuery query = query()
        .base("ou=people")
        .where("objectClass").is("inetOrgPerson")
        .and(query()
                .where("sn").is("Nguyen")
                .or("givenName").is("An"))
        .and("mail").isPresent();
```

Filter:

```ldap
(&(objectClass=inetOrgPerson)(|(sn=Nguyen)(givenName=An))(mail=*))
```

Không viết thành `(A OR B AND C)` nếu yêu cầu là `(A OR B) AND C`. Hãy tạo dữ liệu test mà hai cách đặt ngoặc trả kết quả khác nhau để phát hiện lỗi.

## 9. NOT, presence và thuộc tính không tồn tại

Ví dụ:

```java
LdapQuery notBlocked = query()
        .base("ou=people")
        .where("mail").not().is("blocked@example.org");
```

Filter:

```ldap
(!(mail=blocked@example.org))
```

Điểm cần chú ý: phủ định equality không nhất thiết mang nghĩa “attribute có tồn tại và khác giá trị”. Một entry **không có `mail`** có thể vẫn thỏa phủ định filter theo semantics LDAP. Nếu nghiệp vụ yêu cầu có email và email không bị chặn, viết rõ:

```java
LdapQuery hasAllowedMail = query()
        .base("ou=people")
        .where("mail").isPresent()
        .and("mail").not().is("blocked@example.org");
```

Filter:

```ldap
(&(mail=*)(!(mail=blocked@example.org)))
```

Với attribute đa trị, equality kiểm tra giá trị phù hợp trong tập giá trị; NOT cần được kiểm thử với entry có nhiều giá trị, entry thiếu attribute và ACL che thuộc tính. Đừng áp dụng trực tiếp tư duy `NULL` của SQL vào LDAP.

## 10. Dùng Filter objects khi cần biểu thức phức tạp

Với các điều kiện lồng nhau sâu hoặc được xây theo từng phần, có thể tạo cây filter bằng package `org.springframework.ldap.filter` rồi truyền vào `LdapQueryBuilder.filter(Filter)`.

Ví dụ: **(objectClass=inetOrgPerson) AND (sn=Nguyen OR givenName=An) AND mail present**:

```java
import org.springframework.ldap.filter.AndFilter;
import org.springframework.ldap.filter.EqualsFilter;
import org.springframework.ldap.filter.OrFilter;
import org.springframework.ldap.filter.PresentFilter;
import org.springframework.ldap.query.LdapQuery;

AndFilter root = new AndFilter();
root.and(new EqualsFilter("objectClass", "inetOrgPerson"));

OrFilter nameCondition = new OrFilter();
nameCondition.or(new EqualsFilter("sn", "Nguyen"));
nameCondition.or(new EqualsFilter("givenName", "An"));

root.and(nameCondition);
root.and(new PresentFilter("mail"));

LdapQuery query = query()
        .base("ou=people")
        .searchScope(SearchScope.SUBTREE)
        .filter(root);
```

Cách này có ưu điểm:

- Tách từng nhánh filter thành biến, dễ đọc và test.
- Có thể thêm nhánh theo điều kiện nghiệp vụ.
- Tránh ghép chuỗi filter bằng phép nối string.
- Dễ tái sử dụng một filter nhỏ trong nhiều truy vấn.

Không trộn hai cách khai báo filter trên cùng builder: đã gọi `filter(...)` thì không tiếp tục gọi `where(...)`. Chọn một kiểu cho mỗi query. Các class filter vẫn cần attribute name được kiểm soát và giá trị được đưa vào đúng constructor/API.

## 11. Hardcoded filter và filter có tham số

`LdapQueryBuilder` có các overload `filter(...)` khác nhau. Cần hiểu rõ khác biệt bảo mật.

### 11.1 Filter chuỗi hardcoded

```java
LdapQuery query = query()
        .base("ou=people")
        .filter("(&(objectClass=inetOrgPerson)(employeeStatus=active))");
```

Dạng `filter(String hardcodedFilter)` sử dụng chuỗi filter **nguyên trạng**, không tự escape hoặc validate. Chỉ dùng cho filter cố định do developer kiểm soát. Không nối chuỗi từ HTTP input.

### 11.2 Filter format có tham số

Khi cần một cấu trúc filter cố định nhưng có giá trị động, dùng overload `filter(String, Object...)`:

```java
LdapQuery parameterizedQuery = query()
        .base("ou=people")
        .filter(
                "(&(objectClass={0})(uid={1}))",
                "inetOrgPerson",
                username);
```

Spring LDAP định dạng tham số và **encode giá trị** để tránh input làm thay đổi cú pháp filter. Format string vẫn do ứng dụng kiểm soát; không lấy cả format string từ client.

### 11.3 Filter object

```java
import org.springframework.ldap.filter.AndFilter;
import org.springframework.ldap.filter.EqualsFilter;

AndFilter filter = new AndFilter();
filter.and(new EqualsFilter("objectClass", "inetOrgPerson"));
filter.and(new EqualsFilter("uid", username));

LdapQuery objectQuery = query()
        .base("ou=people")
        .filter(filter);
```

Ba lựa chọn:

| Cách | Có tự encode giá trị động? | Khi nên dùng |
|---|---|---|
| `filter(String)` | **Không** | Filter hardcoded do developer viết |
| `filter(String, Object...)` | **Có**, encode tham số | Cấu trúc filter cố định, giá trị thay đổi |
| `filter(Filter)` | Theo implementation filter object | Xây cây filter bằng các class chuyên dụng |
| `where(...).is(...)` | Có, theo query criteria | Truy vấn fluent thông thường |

Không dùng `filter(String)` để nối raw username hoặc dữ liệu bên ngoài. Đây là lỗi LDAP injection phổ biến.

## 12. Xây truy vấn động nhưng giới hạn tên attribute

Nhiều màn hình tìm kiếm cho phép lọc theo một trong vài trường. Giá trị attribute name **không giống giá trị attribute**: LDAP filter builder encode giá trị, nhưng tên attribute phải là identifier hợp lệ và do ứng dụng kiểm soát.

Ví dụ cho phép tìm theo UID, email hoặc common name:

```java
import java.util.Set;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.SearchScope;

import static org.springframework.ldap.query.LdapQueryBuilder.query;

public final class DirectorySearchQueries {

    private static final Set<String> ALLOWED_ATTRIBUTES =
            Set.of("uid", "mail", "cn");

    public LdapQuery exactMatch(
            String attribute, String value) {

        if (!ALLOWED_ATTRIBUTES.contains(attribute)) {
            throw new IllegalArgumentException(
                    "Unsupported search attribute");
        }
        if (value == null || value.isBlank() || value.length() > 128) {
            throw new IllegalArgumentException(
                    "Invalid search value");
        }

        return query()
                .base("ou=people")
                .searchScope(SearchScope.SUBTREE)
                .countLimit(100)
                .timeLimit(3000)
                .where(attribute).is(value);
    }
}
```

Allowlist bảo vệ **tên attribute**; builder encode **giá trị**. Không cho request gửi `objectClass`, `userPassword` hoặc một attribute tùy ý để thay đổi phạm vi tìm kiếm.

Nếu có nhiều tenant/OU, base DN cũng phải lấy từ cấu hình hoặc mapping đã xác thực, không nhận raw DN từ client.

## 13. Thực thi LdapQuery với LdapTemplate

Builder chỉ tạo query; `LdapTemplate` thực hiện search. Ví dụ dùng `AttributesMapper` để trả DTO:

```java
import java.util.List;
import javax.naming.NamingException;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;

import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.SearchScope;

import static org.springframework.ldap.query.LdapQueryBuilder.query;

public final class DirectoryPersonSearch {

    public record PersonSummary(
            String uid, String commonName, String email) {}

    private final LdapTemplate ldapTemplate;

    public DirectoryPersonSearch(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<PersonSummary> findByUid(String username) {
        if (username == null || username.isBlank()
                || username.length() > 128) {
            throw new IllegalArgumentException("Invalid username");
        }

        LdapQuery request = query()
                .base("ou=people")
                .searchScope(SearchScope.SUBTREE)
                .countLimit(100)
                .timeLimit(3000)
                .attributes("uid", "cn", "mail")
                .where("objectClass").is("inetOrgPerson")
                .and("uid").is(username);

        AttributesMapper<PersonSummary> mapper = attrs ->
                new PersonSummary(
                        read(attrs, "uid"),
                        read(attrs, "cn"),
                        read(attrs, "mail"));

        return ldapTemplate.search(request, mapper);
    }

    private static String read(Attributes attrs, String name)
            throws NamingException {
        Attribute attribute = attrs.get(name);
        return attribute == null
                ? null
                : (String) attribute.get();
    }
}
```

Đây là ví dụ hoàn chỉnh về một class search đơn giản. Các điểm quan trọng:

- `username` được kiểm tra độ dài và rỗng trước khi tìm.
- Filter sử dụng `where("uid").is(username)`, không nối chuỗi.
- Base/scope cố định trong service.
- Chỉ yêu cầu ba attribute.
- Mapper xử lý trường hợp `mail` không tồn tại.
- Kết quả là DTO, không vô tình trả toàn bộ entry hoặc dữ liệu nhạy cảm.

Nếu cần DN và thông tin context, có thể dùng `ContextMapper<T>` với `DirContextOperations`. Khi đó cần phân biệt DN tương đối theo context base với tên đầy đủ trong namespace. Chọn mapper theo dữ liệu cần dùng; không tải toàn bộ attribute chỉ để lấy một DN nếu API hỗ trợ.

## 14. LdapQueryBuilder và ODM/repository

Một entity ODM:

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

Có thể dùng query builder với API tìm entity ODM được Spring LDAP hỗ trợ:

```java
LdapQuery request = query()
        .base("ou=people")
        .where("objectClass").is("inetOrgPerson")
        .and("uid").is("u1001");

List<DirectoryPerson> people =
        ldapTemplate.find(request, DirectoryPerson.class);
```

Ở đây có hai việc khác nhau:

- `LdapQueryBuilder` tạo filter/base/scope.
- `ldapTemplate.find(request, DirectoryPerson.class)` yêu cầu ODM ánh xạ entry sang entity.

Nếu chỉ cần vài trường cho API, dùng `AttributesMapper` và DTO có thể gọn hơn. Nếu cần domain object có mapping lặp lại ở nhiều thao tác, ODM entity phù hợp hơn.

`LdapRepository` cũng cung cấp query method theo property entity, ví dụ `findByUid(...)`. Query method và `LdapQueryBuilder` đều có thể tạo search, nhưng builder hữu ích khi cần base/scope/limit/attributes hoặc biểu thức filter động rõ ràng. Không suy ra query builder sẽ thay thế mọi chức năng của repository.

## 15. Giới hạn: paging, matching rule, referral và ACL

Một filter hợp lệ không đảm bảo search trả đủ hoặc nhanh.

### Paging và count limit

`countLimit(100)` đặt giới hạn số entry, không tạo offset/page number. Với kết quả lớn, cần cơ chế paged results control phù hợp. Paged search có cookie và phụ thuộc server; không cộng các page nếu cookie lỗi hoặc search không hoàn tất.

### Matching rule và schema

`gte`/`lte` cần ordering matching rule. `like` cần substring matching rule. Kiểu attribute, normalization, case sensitivity và schema server ảnh hưởng kết quả. Đặc biệt với binary attribute hoặc DN-valued attribute, không so sánh như chuỗi thông thường nếu schema không hỗ trợ.

### Referral và partial result

Server có thể trả referral/continuation reference hoặc lỗi partial result. Cấu hình JNDI/Spring LDAP quyết định cách client xử lý. Không bật bỏ qua partial result rồi coi danh sách là đầy đủ nếu nghiệp vụ yêu cầu chính xác.

### ACL và quyền bind

Filter chỉ hỏi điều kiện nào khớp; **ACL quyết định service account có được search/read attribute hay không**. Một attribute không xuất hiện trong kết quả có thể do entry không có giá trị hoặc do quyền đọc. Cần kiểm thử với đúng bind account của ứng dụng.

### Hiệu năng

- Thu hẹp base DN và scope.
- Thêm điều kiện `objectClass` phù hợp.
- Tìm attribute có index khi directory owner xác nhận.
- Chỉ trả các attribute cần thiết.
- Đặt time/count limit và paging.
- Tránh filter quá rộng hoặc OR có hàng nghìn nhánh.
- Đo latency và số entry thật trên directory đích.

## 16. Các lỗi thường gặp khi xây query

| Lỗi | Hậu quả | Cách sửa |
|---|---|---|
| Bỏ `base(...)` | Tìm từ context base mặc định, có thể rộng hơn dự kiến | Đặt base rõ ràng |
| Nhầm base với filter | Tìm sai nhánh hoặc điều kiện | Tách base DN và điều kiện |
| Quên `searchScope(...)` | Dùng default có thể rộng hơn ý định | Chọn OBJECT/ONELEVEL/SUBTREE rõ ràng |
| Không có filter | Query builder không có điều kiện search hợp lệ | Bổ sung ít nhất một filter |
| Gọi base sau where | Vi phạm thứ tự cấu hình builder | Khai báo base/scope trước filter |
| Nối raw username vào filter | LDAP injection | `where(...).is(value)` hoặc filter tham số |
| Dùng `filter(String)` với input | Không escape/validate chuỗi | Dùng overload tham số hoặc Filter object |
| Đưa attribute name từ client | Có thể tìm attribute ngoài allowlist | Allowlist tên attribute |
| Dùng `like` cho exact match | Wildcard làm kết quả rộng hơn | Dùng `is` |
| Dùng `not().is(...)` rồi hiểu là có attribute | Entry thiếu attribute có thể khớp | Kết hợp `isPresent()` nếu cần |
| Gọi `gte` trên attribute không có ordering rule | Search lỗi hoặc kết quả không như mong đợi | Kiểm tra schema/matching rule |
| `countLimit` bị hiểu là paging | Chỉ nhận giới hạn số entry, không có offset | Dùng paged results control |
| Lấy mọi attribute | Payload lớn và có thể lộ dữ liệu | Chỉ định `attributes(...)` |
| Bỏ qua size/time/partial exception | Danh sách không đầy đủ bị coi là thành công | Phân loại lỗi và báo trạng thái |

## 17. Kiểm thử filter và truy vấn

Một test tốt cần kiểm tra **filter logic, base/scope và kết quả directory**, không chỉ việc code compile.

### 17.1 Unit test escaping

Có thể kiểm tra giá trị filter với ký tự đặc biệt bằng filter object:

```java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;
import org.springframework.ldap.filter.EqualsFilter;

class LdapFilterEncodingTest {

    @Test
    void encodesSpecialCharactersAsLiteralValue() {
        String supplied = "u1001*)(uid=*)";
        String encoded =
                new EqualsFilter("uid", supplied).encode();

        assertTrue(encoded.contains("\\2a"));
        assertTrue(encoded.contains("\\29"));
        assertTrue(encoded.contains("\\28"));
        assertFalse(encoded.contains(")(uid=*)"));
    }
}
```

Test này kiểm tra **filter value encoding**. Nó không kiểm tra base/scope hoặc quyền LDAP.

### 17.2 Integration test với LDAP test server

Dữ liệu test nên có nhiều entry phân biệt:

| DN | uid | sn | mail |
|---|---|---|---|
| `uid=u1001,ou=people,...` | u1001 | Nguyen | an@example.org |
| `uid=u1002,ou=people,...` | u1002 | Nguyen | *không có* |
| `uid=u1003,ou=people,...` | u1003 | Tran | tran@example.org |
| `uid=u1004,ou=contractors,ou=people,...` | u1004 | Le | le@example.org |

Các ca test:

1. Equality theo UID chỉ trả entry mong đợi.
2. AND giữa objectClass và UID giữ cả hai điều kiện.
3. OR lồng nhau trả đúng tập entry.
4. `isPresent()` loại entry thiếu mail.
5. `not().is(...)` được kiểm tra với cả attribute thiếu và đa trị.
6. ONELEVEL không trả entry ở OU con; SUBTREE có thể trả nếu schema/scope phù hợp.
7. Input chứa dấu sao/ngoặc không làm mở rộng filter.
8. Attribute allowlist từ chối field không được hỗ trợ.
9. Size/time limit và referral được xử lý như lỗi/partial theo policy.
10. Mapper không trả attribute nhạy cảm ngoài danh sách.

### 17.3 Kiểm thử ngữ nghĩa với server thật

LDAP server có thể khác về schema, matching rule, index, referral, paging, ACL và limit. Mock hữu ích cho logic service, nhưng **không thay thế integration test** với sản phẩm/phiên bản directory mục tiêu. Với AD, đổi objectClass và login attribute phù hợp; không dùng mặc định `inetOrgPerson`/`uid` nếu schema thực tế không có.

## 18. Bài tập thực hành

Một directory test có base `dc=example,dc=org`, OU `ou=people` và các entry `inetOrgPerson`. API tìm kiếm nhận ba tham số: họ, tên và yêu cầu có email.

Yêu cầu filter:

**(sn = họ nhập OR givenName = tên nhập) AND (mail tồn tại) AND (objectClass = inetOrgPerson)**.

Hãy thực hiện:

1. Viết `LdapQueryBuilder` với base `ou=people` và scope `SUBTREE`.
2. Dùng nested `query()` để nhóm hai điều kiện OR.
3. Dùng `isPresent()` cho mail.
4. Dùng `attributes("uid", "cn", "mail")` để chỉ trả dữ liệu cần thiết.
5. Đặt `countLimit` và `timeLimit` phù hợp.
6. Chạy với một entry thỏa cả hai nhánh, một entry chỉ thỏa nhánh họ, một entry chỉ thỏa nhánh tên và một entry thiếu mail.
7. Thử đầu vào có `*)(uid=*)` để kiểm tra escaping.
8. Đổi base/scope và chứng minh kết quả khác nhau khi entry ở OU con.
9. Viết mapper thành DTO và xác minh không trả attribute nhạy cảm.
10. Ghi lại filter, tập DN kết quả, thời gian và lỗi nếu server cắt kết quả.

**Gợi ý code:**

```java
LdapQuery request = query()
        .base("ou=people")
        .searchScope(SearchScope.SUBTREE)
        .countLimit(100)
        .timeLimit(3000)
        .attributes("uid", "cn", "mail")
        .where("objectClass").is("inetOrgPerson")
        .and(query()
                .where("sn").is(surname)
                .or("givenName").is(givenName))
        .and("mail").isPresent();
```

Cần kiểm tra giá trị `surname`/`givenName` trước khi gọi và xác nhận mapper xử lý attribute tùy chọn đúng. Không biến giá trị người dùng thành raw filter.

## 19. Checklist và tổng kết

Trước khi bàn giao một truy vấn dùng `LdapQueryBuilder`:

- [ ] Đã đặt đúng **base DN**, hiểu quan hệ với context base của `ContextSource`.
- [ ] Đã chọn scope `OBJECT`, `ONELEVEL` hoặc `SUBTREE` theo nhu cầu.
- [ ] Có filter bắt buộc và `objectClass` phù hợp schema.
- [ ] Dùng `where`/`and`/`or`/`not` đúng nhóm logic.
- [ ] Dùng `is`, `isPresent`, `like`, `gte`, `lte` theo matching rule của attribute.
- [ ] Đã phân biệt `filter(String)` hardcoded với `filter(String, Object...)` có encode tham số.
- [ ] Không nối raw user input, không nhận attribute name/base DN tùy ý từ client.
- [ ] Có count/time limit và chiến lược paging khi kết quả lớn.
- [ ] Chỉ trả các attribute cần thiết qua `attributes(...)`.
- [ ] Mapper/ODM xử lý attribute thiếu, đa trị và kiểu binary phù hợp.
- [ ] Phân biệt no-match với ACL, referral, partial result và size/time limit.
- [ ] Có unit test escaping và integration test trên LDAP directory phù hợp.

### Tài liệu chính thức

- [Spring LDAP — Advanced LDAP Queries](https://docs.spring.io/spring-ldap/reference/query-builder-advanced.html).
- [Spring LDAP API — LdapQueryBuilder](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/query/LdapQueryBuilder.html).
- [Spring LDAP API — ConditionCriteria](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/query/ConditionCriteria.html).
- [Spring LDAP API — ContainerCriteria](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/query/ContainerCriteria.html).
- [RFC 4511 — LDAP: The Protocol](https://www.rfc-editor.org/rfc/rfc4511).
- [RFC 4515 — LDAP Search Filter String Representation](https://www.rfc-editor.org/rfc/rfc4515).

Tài liệu Spring LDAP có thể khác theo phiên bản. Hãy đối chiếu Javadoc đúng dependency đã resolve trong ứng dụng; ví dụ API trong bài tập trung vào `LdapQueryBuilder` và `LdapTemplate`.

**Kết luận:** `LdapQueryBuilder` giúp mô tả LDAP search một cách rõ ràng: xác định base, scope, filter, giới hạn và tập attribute cần trả về. Hãy dùng criteria builder hoặc filter object để xây điều kiện có giá trị động, giới hạn attribute/base/scope theo allowlist và kiểm tra matching rule/schema ở server. Khi kết hợp đúng với `LdapTemplate`, ODM và integration test, bộ lọc trở nên dễ đọc, an toàn hơn và có thể kiểm chứng trong ứng dụng Spring Data LDAP.
