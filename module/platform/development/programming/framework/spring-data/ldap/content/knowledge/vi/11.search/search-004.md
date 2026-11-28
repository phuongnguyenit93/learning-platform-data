# Chỉ lấy các thuộc tính cần thiết

Trong **SPRING_DATA_LDAP**, ứng dụng Java truy cập dịch vụ thư mục LDAP bằng Spring Data LDAP repository và `LdapTemplate`. Entry LDAP được định danh bằng DN (*Distinguished Name*), có các `objectClass` và thuộc tính tuân theo schema; ứng dụng dùng base DN, search scope và LDAP filter để tìm entry. Tuy nhiên, **tìm đúng entry chưa đủ**: mỗi truy vấn còn phải quyết định **cần nhận lại những thuộc tính nào**.

Ví dụ, một màn hình gợi ý người dùng chỉ cần `uid`, `cn` và `mail`, nhưng entry thực tế có thể còn `telephoneNumber`, `description`, `memberOf`, nhiều giá trị `objectClass` và các thuộc tính khác. Yêu cầu tất cả thuộc tính khi chỉ dùng ba trường sẽ truyền dữ liệu không cần thiết, tăng công việc ánh xạ và có thể mở rộng phạm vi dữ liệu nhạy cảm mà code tiếp xúc.

Bài học tập trung vào **LDAP attribute selection** (hay *projection thuộc tính ở tầng LDAP*): dùng `LdapQueryBuilder.attributes(...)`, `SearchControls` và mapper để chỉ yêu cầu dữ liệu tối thiểu; phân biệt thuộc tính yêu cầu trả về với filter, DN và schema; xử lý thuộc tính tùy chọn/đa trị; đo hiệu quả và kiểm thử tính đúng đắn.

## 1. Tách điều kiện tìm kiếm khỏi danh sách thuộc tính cần trả về

Giả sử directory có người dùng:

```ldif
dn: uid=lan,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: lan
cn: Lan Nguyen
sn: Nguyen
mail: lan@example.org
telephoneNumber: +84 28 1234 5678
description: Platform engineer
```

Màn hình danh bạ chỉ hiển thị tên và email. Truy vấn nên có các thành phần độc lập:

```text
LDAP endpoint : ldaps://ldap.example.org:636
Context base  : dc=example,dc=org
Search base   : ou=people
Search scope  : ONELEVEL
Filter        : (&(objectClass=inetOrgPerson)(uid=lan))
Attributes    : uid, cn, mail
```

Hình dung luồng xử lý:

```text
Ứng dụng
  |
  | SearchRequest:
  |   base    = ou=people,dc=example,dc=org
  |   scope   = ONELEVEL
  |   filter  = (&(objectClass=inetOrgPerson)(uid=lan))
  |   attrs   = [uid, cn, mail]
  v
LDAP server -- tìm entry khớp base/scope/filter
  |
  | SearchResultEntry:
  |   objectName = uid=lan,ou=people,dc=example,dc=org
  |   attributes = {uid=lan, cn=Lan Nguyen, mail=lan@example.org}
  v
AttributesMapper / ContextMapper --> DTO cho màn hình
```

Ba khái niệm cần tách:

| Thành phần | Điều khiển điều gì? | Ví dụ |
|---|---|---|
| **Base DN + scope** | Vùng cây LDAP sẽ được tìm | `ou=people`, `ONELEVEL` |
| **LDAP filter** | Entry nào đáp ứng điều kiện | `(uid=lan)` |
| **Returning attributes** | Thuộc tính nào được server gửi lại cho các entry khớp | `uid`, `cn`, `mail` |

**Chỉ định thuộc tính trả về không làm đổi điều kiện tìm kiếm.** Dù `objectClass` xuất hiện trong filter, bạn không bắt buộc yêu cầu server trả `objectClass` nếu DTO không dùng nó. Ngược lại, việc thêm `mail` vào danh sách returning attributes **không** khiến server chỉ tìm entry có `mail`; muốn kiểm tra sự tồn tại của thuộc tính này phải đưa điều kiện `(mail=*)` vào filter.

Trong LDAPv3, `SearchResultEntry` còn chứa tên entry ở trường `objectName`; DN này **không phải** một thuộc tính LDAP mang tên `dn` nằm trong `Attributes`. Vì vậy, muốn trả DN trong DTO thường phải dùng API có ngữ cảnh tên, không chỉ thêm `"dn"` vào danh sách thuộc tính.

## 2. Vì sao nên lấy ít thuộc tính?

Việc chỉ lấy đúng trường cần dùng có nhiều lợi ích:

1. **Giảm dữ liệu trên mạng.** Nếu mỗi entry có thuộc tính lớn hoặc đa trị (ví dụ ảnh, chứng chỉ hay danh sách thành viên nhóm), bỏ qua các trường này có thể giảm đáng kể payload khi trả hàng trăm entry.
2. **Giảm chi phí xử lý phía client.** JNDI/Spring LDAP không phải tạo và chuyển đổi các giá trị mà ứng dụng không dùng.
3. **Giảm bề mặt lộ dữ liệu.** Một chức năng danh bạ không cần đọc giá trị nội bộ hoặc nhạy cảm; giảm lượng dữ liệu đi qua logs, cache, heap và các tầng downstream là nguyên tắc *data minimization*.
4. **Làm rõ hợp đồng API.** Mapper và DTO chỉ phụ thuộc những thuộc tính thực sự cần hiển thị hoặc xử lý nghiệp vụ.
5. **Dễ nhận diện thay đổi schema.** Tập thuộc tính được khai báo rõ khiến việc kiểm thử và đánh giá ACL cụ thể hơn.

Tuy nhiên, projection **không chắc làm LDAP server tìm entry nhanh hơn**. Server vẫn phải đánh giá filter, quyền đọc, index và phạm vi tìm kiếm. Nếu filter không được index hoặc search scope quá rộng, giảm returning attributes chỉ tối ưu một phần chi phí. Cũng không được xem projection là cơ chế bảo mật thay cho **ACL của directory**.

Ví dụ:

```text
Truy vấn A: filter=(uid=lan); trả tất cả thuộc tính
Truy vấn B: filter=(uid=lan); trả uid,cn,mail

Tập entry khớp: về nguyên tắc giống nhau.
Dữ liệu của mỗi entry: truy vấn B trả ít hơn.
Chi phí đánh giá filter: vẫn phụ thuộc LDAP server/index/search scope.
```

## 3. Thuộc tính user, operational và selector đặc biệt

LDAP phân biệt **user attributes** và **operational attributes**. Không nên hiểu “all attributes” là mọi dữ liệu mà server có thể cung cấp.

| Selector trong yêu cầu LDAP | Ý nghĩa thường gặp | Lưu ý |
|---|---|---|
| `uid`, `cn`, `mail` | Chỉ định rõ các thuộc tính user cần trả | Hữu ích cho DTO nhẹ |
| `*` | Yêu cầu **tất cả user attributes** | Không mặc nhiên gồm operational attributes |
| `+` | Yêu cầu **tất cả operational attributes** nếu server hỗ trợ RFC 3673 | Quyền đọc và hỗ trợ tùy server |
| `1.1` | Yêu cầu **không trả thuộc tính nào** | Hữu ích khi chỉ cần tên entry; không kết hợp tùy tiện với selector khác |
| Danh sách rỗng theo API LDAP/JNDI | Có thể có ý nghĩa **không thuộc tính nào** ở JNDI, nhưng mặc định builder/API khác có thể là trả tất cả | Không suy luận giống nhau giữa các API |

Ví dụ:

```text
attributes: uid cn mail  -> lấy ba thuộc tính được yêu cầu, nếu có/quyền cho phép
attributes: *            -> lấy tất cả user attributes
attributes: +            -> lấy operational attributes nếu được server hỗ trợ
attributes: 1.1          -> chỉ lấy tên entry, không lấy Attributes của entry
```

`createTimestamp`, `modifyTimestamp` hoặc `entryUUID` là ví dụ thường gặp của operational attributes, nhưng **không phải server nào cũng có cùng tên và cùng khả năng truy cập**. Ví dụ Microsoft Active Directory còn có các thuộc tính/metadata đặc thù. Muốn dùng thuộc tính operational, hãy xác minh schema, ACL và hành vi của backend; đừng mặc định `attributes("*")` lấy đủ mọi thứ.

Tùy chọn `1.1` được quy định ở cấp giao thức LDAP; muốn *chỉ kiểm tra DN/tồn tại* có thể dùng nó trong yêu cầu thích hợp, nhưng trong các API ánh xạ entity, thiếu thuộc tính có thể khiến mapper không tạo được đối tượng. Với mục tiêu chỉ kiểm tra một DN cụ thể, API `lookup` hoặc `exists` chuyên dụng đôi khi diễn đạt ý định tốt hơn.

**Lưu ý về cách đặt tên thuộc tính:** LDAP cho phép attribute description kèm options, chẳng hạn `cn;lang-en`, và các server có thể dùng cú pháp trả về đặc thù như `member;range=0-1499`. Đừng giả định `Attributes.get("member")` luôn lấy được toàn bộ membership trên mọi backend; hãy kiểm tra contract của directory.

## 4. Sử dụng `LdapQueryBuilder.attributes(...)` trong Spring LDAP

Trong Spring LDAP, cách tiện lợi nhất để chọn thuộc tính khi tìm kiếm là khai báo `.attributes(...)` **trước** phần điều kiện `.where(...)`:

```java
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.SearchScope;
import static org.springframework.ldap.query.LdapQueryBuilder.query;

LdapQuery ldapQuery = query()
        .base("ou=people")
        .searchScope(SearchScope.ONELEVEL)
        .attributes("uid", "cn", "mail")
        .countLimit(100)
        .timeLimit(3000)
        .where("objectClass").is("inetOrgPerson")
        .and("uid").is("lan");
```

Đoạn code giả định `LdapContextSource.base` là `dc=example,dc=org`, nên `base("ou=people")` là **tên tương đối** dưới base đã cấu hình. Server tìm trong nhánh thực tế `ou=people,dc=example,dc=org`. Các tùy chọn:

- `.base("ou=people")`: nơi bắt đầu tìm kiếm.
- `.searchScope(SearchScope.ONELEVEL)`: chỉ tìm các entry con trực tiếp của `ou=people`; không gồm entry `ou=people`.
- `.attributes("uid", "cn", "mail")`: yêu cầu trả ba thuộc tính.
- `.countLimit(100)`: giới hạn kết quả ở phía client/search controls; không thay thế paging hoặc server limit.
- `.timeLimit(3000)`: giới hạn thời gian theo search controls/provider; không đồng nghĩa timeout kết nối TCP.
- `.where(...).is(...)`: xây filter và escape giá trị an toàn.

**Không có điều kiện `mail` trong filter**; vì thế entry không có `mail` vẫn có thể khớp và được trả về với `mail` vắng mặt. Mapper cần xử lý khả năng đó.

## 5. Ánh xạ vào DTO chỉ có trường cần dùng

Một cách hiệu quả để giảm ràng buộc vào schema là chọn thuộc tính tại LDAP server, sau đó ánh xạ trực tiếp sang DTO nhỏ bằng `AttributesMapper<T>`. Ví dụ:

**`PersonSummary.java`**

```java
package com.example.ldap;

public record PersonSummary(
        String uid,
        String displayName,
        String email
) {
}
```

**`PersonSearchReader.java`**

```java
package com.example.ldap;

import java.util.List;
import javax.naming.NamingException;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;

import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.SearchScope;
import org.springframework.stereotype.Repository;

import static org.springframework.ldap.query.LdapQueryBuilder.query;

@Repository
public class PersonSearchReader {

    private final LdapTemplate ldapTemplate;

    public PersonSearchReader(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<PersonSummary> findByUid(String uid) {
        if (uid == null || uid.isBlank()) {
            throw new IllegalArgumentException("uid không được rỗng");
        }

        LdapQuery ldapQuery = query()
                .base("ou=people")
                .searchScope(SearchScope.SUBTREE)
                .attributes("uid", "cn", "mail")
                .countLimit(100)
                .where("objectClass").is("inetOrgPerson")
                .and("uid").is(uid);

        AttributesMapper<PersonSummary> mapper = attrs ->
                new PersonSummary(
                        requiredString(attrs, "uid"),
                        requiredString(attrs, "cn"),
                        optionalString(attrs, "mail")
                );

        return ldapTemplate.search(ldapQuery, mapper);
    }

    private static String requiredString(Attributes attrs, String name)
            throws NamingException {
        Attribute attr = attrs.get(name);
        if (attr == null || attr.size() == 0) {
            throw new IllegalStateException(
                    "Thiếu thuộc tính bắt buộc để ánh xạ: " + name);
        }
        Object value = attr.get();
        if (!(value instanceof String text)) {
            throw new IllegalStateException(
                    "Sai kiểu giá trị của thuộc tính: " + name);
        }
        return text;
    }

    private static String optionalString(Attributes attrs, String name)
            throws NamingException {
        Attribute attr = attrs.get(name);
        if (attr == null || attr.size() == 0) {
            return null;
        }
        Object value = attr.get();
        return value instanceof String text ? text : null;
    }
}
```

Code sử dụng Java 17 trở lên vì có `record` và pattern matching cho `instanceof`. Trong dự án dùng Java cũ hơn, chuyển `PersonSummary` thành một POJO và dùng kiểu ép truyền thống.

Những điều quan trọng:

1. `LdapTemplate.search(ldapQuery, mapper)` **trả một danh sách DTO**, không đòi ánh xạ toàn bộ entry sang entity ODM.
2. `AttributesMapper` chỉ được cấp `Attributes` của entry và thường thích hợp khi DTO **không cần DN**.
3. `uid`, `cn` là những trường DTO bắt buộc theo **hợp đồng của ứng dụng** trong ví dụ; dù schema LDAP có `cn`, tài khoản đọc thiếu quyền hay cấu hình projection sai vẫn có thể khiến chúng không xuất hiện ở kết quả.
4. `mail` là trường tùy chọn. Thiếu `mail` không phải là chứng cứ người dùng không có email: cũng có thể do ACL hoặc truy vấn không yêu cầu nó.
5. Dùng `.is(uid)` để builder escape ký tự filter; tuyệt đối không nối chuỗi `"(uid=" + uid + ")"` từ đầu vào không tin cậy.

Nếu thuộc tính có nhiều giá trị, `attr.get()` chỉ lấy **một giá trị**, không được hiểu là toàn bộ tập hợp. Phần sau sẽ có ví dụ đọc đa trị.

## 6. Nếu DTO cần DN, dùng mapper có ngữ cảnh

`AttributesMapper` không cung cấp trực tiếp DN của entry. Nếu UI cần liên kết đến một người dùng cụ thể hoặc nghiệp vụ phải phân biệt hai entry có cùng `uid` ở hai nhánh, hãy dùng `ContextMapper<T>`:

```java
import java.util.List;
import org.springframework.ldap.core.ContextMapper;
import org.springframework.ldap.query.LdapQuery;
import static org.springframework.ldap.query.LdapQueryBuilder.query;

record PersonHit(String relativeDn, String uid, String displayName) {}

LdapQuery ldapQuery = query()
        .base("ou=people")
        .attributes("uid", "cn")
        .where("objectClass").is("inetOrgPerson");

ContextMapper<PersonHit> mapper = ctx -> new PersonHit(
        ctx.getDn().toString(),
        ctx.getStringAttribute("uid"),
        ctx.getStringAttribute("cn"));

List<PersonHit> hits = ldapTemplate.search(ldapQuery, mapper);
```

Ở đây `ctx.getDn()` là DN theo **quy ước ngữ cảnh của Spring LDAP**, không nên tự coi chuỗi được trả về là DN đầy đủ trên toàn directory. Khi chuyển thông tin sang service khác, phải quy định nó tương đối với base nào và thuộc LDAP endpoint/naming context nào; cách trích xuất DN đầy đủ có thể phụ thuộc API/provider.

Một entry LDAP có thể hợp lệ ngay cả khi nó không có các thuộc tính UI mong đợi. Khi đó phải quyết định trả lỗi, bỏ qua entry hay trả giá trị `null` theo hợp đồng sản phẩm, thay vì im lặng tự suy ra giá trị từ RDN.

## 7. Khi dùng `SearchControls` trực tiếp

Nếu cần thao tác ở tầng thấp hơn `LdapQueryBuilder`, API JNDI `javax.naming.directory.SearchControls` có `setReturningAttributes(String[])`:

```java
import javax.naming.directory.SearchControls;

SearchControls controls = new SearchControls();
controls.setSearchScope(SearchControls.ONELEVEL_SCOPE);
controls.setReturningAttributes(new String[]{"uid", "cn", "mail"});
controls.setCountLimit(100);
controls.setTimeLimit(3000);
```

Trong các lời gọi JNDI hoặc overload `LdapTemplate.search(...)` sử dụng `SearchControls`, mảng `getReturningAttributes()` xác định những trường người gọi yêu cầu. Phân biệt:

- `setReturningAttributes(null)` theo hợp đồng JNDI nghĩa là **trả toàn bộ các thuộc tính áp dụng mặc định** (thông thường là user attributes, không mặc định có operational attributes).
- `setReturningAttributes(new String[0])` theo hợp đồng JNDI nghĩa là **không trả thuộc tính nào**.
- `setReturningAttributes(new String[]{"uid", "cn"})` yêu cầu chỉ trả `uid` và `cn`.

Vì vậy **không** áp dụng cùng một suy luận về mảng rỗng cho mọi builder/helper. Trước khi dùng danh sách thuộc tính được tạo động, hãy kiểm tra hành vi của API và kiểm thử trường hợp mảng rỗng để tránh vô tình trả dữ liệu rộng hơn hoặc hẹp hơn dự kiến.

`SearchControls` còn có các lựa chọn như scope, giới hạn count/time và returning object flag. Những giá trị đó ảnh hưởng phép tìm kiếm nhưng không biến danh sách thuộc tính thành điều kiện lọc. Nếu filter có dữ liệu người dùng, hãy dùng filter builder hoặc cơ chế binding/escape phù hợp; `SearchControls` không tự chống filter injection khi bạn tự nối filter.

## 8. Đọc thuộc tính tùy chọn và đa trị

### 8.1. Một thuộc tính không xuất hiện có nhiều nguyên nhân

`attrs.get("mail") == null` có thể do:

- Entry thực sự không có `mail`.
- Truy vấn không yêu cầu `mail`.
- Người dùng bind không có quyền đọc `mail` hoặc server áp dụng chính sách che thuộc tính.
- Backend không hỗ trợ tên/cú pháp thuộc tính như giả định.

Để hiển thị email tùy chọn, trả `null` hoặc `Optional` theo hợp đồng DTO là hợp lý; **không** mặc định đi tìm lại với `attributes("*")` khi chỉ muốn xác định nguyên nhân, vì điều đó có thể mở rộng quyền và payload. Hãy dùng tài khoản/test fixture phù hợp để phân biệt lỗi mapping với hạn chế ACL.

### 8.2. Với thuộc tính đa trị, đọc tất cả giá trị

Ví dụ `member` của một `groupOfNames` có thể chứa nhiều DN:

```ldif
dn: cn=developers,ou=groups,dc=example,dc=org
objectClass: top
objectClass: groupOfNames
cn: developers
member: uid=lan,ou=people,dc=example,dc=org
member: uid=binh,ou=people,dc=example,dc=org
```

Nếu nghiệp vụ cần danh sách DN thành viên, nên yêu cầu `member` thay vì mọi thuộc tính của group, nhưng cần duyệt **toàn bộ** giá trị:

```java
import java.util.ArrayList;
import java.util.List;
import javax.naming.NamingEnumeration;
import javax.naming.NamingException;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;

static List<String> getAllStrings(Attributes attrs, String name)
        throws NamingException {
    Attribute attr = attrs.get(name);
    if (attr == null) {
        return List.of();
    }

    List<String> values = new ArrayList<>();
    NamingEnumeration<?> all = attr.getAll();
    try {
        while (all.hasMore()) {
            Object value = all.next();
            if (value instanceof String text) {
                values.add(text);
            }
        }
    } finally {
        all.close();
    }
    return values;
}
```

**Cẩn trọng với `member` trên Active Directory:** server có thể trả thuộc tính theo **range retrieval** khi danh sách nhiều phần tử, chẳng hạn `member;range=0-1499`, thay vì trả một `member` duy nhất chứa toàn bộ giá trị. Đây là hành vi đặc thù AD; muốn thực sự lấy đầy đủ membership phải xử lý cơ chế range theo tài liệu server. `getAllStrings(attrs, "member")` ở trên phù hợp khi response chứa một thuộc tính `member` bình thường và **không** tự giải quyết AD ranged attributes.

Nếu ứng dụng chỉ cần kiểm tra người dùng có thuộc nhóm hay không, lấy mọi `member` của một nhóm cực lớn có thể tốn kém. Tùy schema, truy vấn nhóm theo điều kiện `(member=<DN>)` sẽ thích hợp hơn là tải toàn bộ membership rồi lọc bằng Java. Lúc này phải dựng DN và filter an toàn, đồng thời lưu ý nested membership theo chính sách backend.

## 9. Repository ODM và nguy cơ cập nhật đối tượng thiếu thuộc tính

Spring Data LDAP repository dùng các annotation ODM như `@Entry`, `@Id` và `@Attribute` để ánh xạ entry thành entity Java. Ví dụ lớp:

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
public class PersonEntry {
    @Id
    private Name dn;

    @Attribute(name = "uid")
    private String uid;

    @Attribute(name = "cn")
    private String displayName;

    @Attribute(name = "sn")
    private String surname;

    @Attribute(name = "mail")
    private String email;

    public PersonEntry() {}
    // Getter/setter cho các trường.
}
```

Nếu cần một **entity đầy đủ để chỉnh sửa**, bạn phải hiểu nó được tải với các thuộc tính nào. Với truy vấn chọn lọc hoặc ánh xạ projection, những trường không có trong response có thể thành `null` hoặc không được nạp. **Không gọi `repository.save(...)` trên một object thiếu thuộc tính** nếu chưa kiểm chứng kỹ semantics update của ODM/phiên bản Spring Data LDAP và schema server: thao tác ghi có thể làm mất hoặc thay đổi giá trị ngoài phạm vi mong muốn.

Quy ước an toàn:

| Use case | Cách đọc/ánh xạ được khuyên |
|---|---|
| UI danh bạ, danh sách tìm kiếm | `LdapTemplate.search` + `attributes(...)` + DTO chuyên biệt |
| Báo cáo chỉ cần `uid`, `cn` | Projection DTO với đúng hai trường |
| Xác định entry theo DN | `lookup` hoặc repository `findById`, đọc đủ thông tin cần dùng |
| Cập nhật `mail` của một DN đã xác minh | Xem xét `LdapTemplate.modifyAttributes` với thay đổi riêng thuộc tính `mail` |
| Thao tác ghi toàn entity ODM | Nạp và validate entity theo chiến lược ODM; kiểm tra schema và ACL trước khi `save` |

Việc **read projection** và việc **write entity** là hai hợp đồng khác nhau. Nếu các API dùng chung một kiểu Java rồi người gọi nhầm DTO với entity, có thể phát sinh lỗi khó phát hiện. Tách `PersonSummary`, `PersonDetail` và `PersonEntry` giúp ngăn nhầm lẫn.

## 10. Quy định tập thuộc tính theo nghiệp vụ và quyền

Không cho frontend hoặc client tùy ý gửi danh sách thuộc tính LDAP rồi đưa thẳng vào `.attributes(userFields)`. Dù chỉ là danh sách trả về, đầu vào đó có thể khiến ứng dụng đọc dữ liệu ngoài nhu cầu nghiệp vụ nếu tài khoản bind có quyền lớn.

Một cách tổ chức tốt là dùng **projection cố định hoặc allowlist**:

```java
enum PersonView {
    SUMMARY, CONTACT
}

static String[] attributesFor(PersonView view) {
    return switch (view) {
        case SUMMARY -> new String[]{"uid", "cn"};
        case CONTACT -> new String[]{"uid", "cn", "mail"};
    };
}
```

Nếu hệ thống có nhiều API, mỗi API nên xác định **hợp đồng dữ liệu riêng**. Ví dụ:

- Tìm kiếm nhanh: `uid` và `cn`.
- Danh bạ nội bộ được cấp quyền: `uid`, `cn`, `mail`.
- Kiểm tra tồn tại theo DN: không cần trả danh sách thuộc tính đầy đủ.
- Quản trị directory: chỉ các trường được phép đối với vai trò quản trị, và vẫn cần kiểm soát ACL ở server.

Một thuộc tính có thể chứa dữ liệu nhạy cảm ngay cả khi tên nghe vô hại; điều này phụ thuộc directory/schema thực tế. `returning attributes` chỉ giảm dữ liệu ứng dụng **yêu cầu**. **LDAP ACL vẫn là hàng rào bảo mật chính**, không được coi việc ẩn trường trên UI hay dùng `attributes(...)` là thay thế cho phân quyền.

Không đưa giá trị `mail`, `uid`, tên nhóm, DN đầy đủ hoặc filter chứa thông tin người dùng vào metric tags hay logs không được bảo vệ. Để quan sát hiệu quả projection, nên log/đo **tên loại truy vấn**, số entry, số thuộc tính yêu cầu, kích thước response (nếu đo được) và latency, chứ không cần ghi nội dung giá trị.

## 11. Đánh giá hiệu năng cho projection thuộc tính

Chọn ít trường hơn **thường** giảm kích thước response và chi phí ánh xạ, nhưng cần đo trên workload cụ thể:

```text
Kịch bản A — trả mặc định nhiều user attributes:
    search base = ou=people
    filter      = (objectClass=inetOrgPerson)
    attributes  = *

Kịch bản B — chỉ trả trường cần cho danh bạ:
    search base = ou=people
    filter      = (objectClass=inetOrgPerson)
    attributes  = uid, cn, mail

Giữ nguyên server, base, scope, filter và limit để so sánh.
```

Các chỉ số hữu ích:

| Chỉ số | Điều cần quan sát |
|---|---|
| Kích thước dữ liệu trả về | Response B có thực sự nhỏ hơn A không? |
| Số entry trả về | A và B có cùng tập DN trong điều kiện kiểm thử không? |
| p50/p95/p99 latency | Tác động ở network và mapping có đáng kể không? |
| Heap/GC của ứng dụng | DTO/projection có giảm giữ dữ liệu lớn không? |
| Server CPU/search time | Tối ưu filter/index có vẫn là nút thắt chính không? |
| ACL và trường thiếu | Một số trường không trả vì thiếu quyền hay không tồn tại? |

Để so sánh công bằng, kiểm thử cùng search base/filter/scope/size limit, dữ liệu đầu vào, phiên bản directory và mức tải tương tự. Nếu cần tất cả kết quả, không dùng danh sách đầu tiên trong một phép tìm kiếm lớn làm bằng chứng bởi server size limit, referral hoặc paging có thể khiến kết quả không đầy đủ.

**Không tự động mở rộng danh sách thuộc tính sau khi query bị lỗi.** Nếu thiếu trường cần thiết, ghi nhận lỗi projection hoặc quyền; cần điều tra với một tài khoản test có đủ ACL và truy vấn kiểm chứng có kiểm soát.

## 12. Kiểm thử các trường hợp quan trọng

### 12.1. Kiểm thử tích hợp projection với directory mẫu

Để kiểm tra server thực sự chỉ trả những trường yêu cầu, hãy tạo LDAP test directory có `dc=example,dc=org`, `ou=people` và entry Lan với `uid`, `cn`, `sn`, `mail`, `telephoneNumber`. Trong test, dùng tài khoản bind đủ quyền đọc những thuộc tính đó:

**`PersonProjectionIT.java`**

```java
package com.example.ldap;

import java.util.List;
import javax.naming.directory.Attributes;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import static org.springframework.ldap.query.LdapQueryBuilder.query;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;

@SpringBootTest
class PersonProjectionIT {

    @Autowired
    LdapTemplate ldapTemplate;

    @Test
    void returnsOnlyRequestedUserAttributes() {
        LdapQuery ldapQuery = query()
                .base("ou=people")
                .attributes("uid", "cn", "mail")
                .where("uid").is("lan");

        AttributesMapper<Attributes> mapper = attrs -> attrs;
        List<Attributes> result = ldapTemplate.search(ldapQuery, mapper);

        assertEquals(1, result.size());
        Attributes attrs = result.get(0);
        assertNotNull(attrs.get("uid"));
        assertNotNull(attrs.get("cn"));
        assertNotNull(attrs.get("mail"));
        assertNull(attrs.get("telephoneNumber"));
        assertNull(attrs.get("sn"));
    }
}
```

**Điều kiện tiên quyết:** entry test thực sự có `sn` và `telephoneNumber`, tài khoản bind có thể đọc chúng, query chỉ khớp một entry và `LdapContextSource.base` là `dc=example,dc=org`. Nếu không biết fixture thực tế, một assert `attrs.get("telephoneNumber") == null` chưa chứng minh projection đã hoạt động: thuộc tính có thể vốn không tồn tại hoặc bị ACL che.

Sau test trên, chạy một truy vấn test đối chứng có chủ đích yêu cầu `sn`/`telephoneNumber` và xác nhận server trả về các giá trị đó cho tài khoản test; nhờ vậy mới phân biệt được *server không trả theo projection* với *server không có/không cho đọc thuộc tính*.

### 12.2. Các trường hợp cần kiểm chứng

| Tình huống | Kết quả mong đợi |
|---|---|
| Yêu cầu `uid`, `cn`, `mail` | DTO có các trường đó; không nhận field khác chỉ vì entry có |
| Filter sử dụng `objectClass` nhưng không yêu cầu trả `objectClass` | Filter vẫn chọn đúng entry |
| Entry không có `mail` | DTO có `email == null` theo hợp đồng |
| Input `uid` có dấu `*` hoặc `(` | Filter builder giữ đúng giá trị literal, không mở rộng kết quả ngoài ý muốn |
| Scope `ONELEVEL` so với `SUBTREE` | Thay đổi vùng entry được tìm, không thay đổi tên attribute selector |
| Cần DN nhưng dùng `AttributesMapper` | Không có DN trực tiếp; chuyển sang `ContextMapper` nếu cần |
| Thuộc tính đa trị | Đọc bằng `Attribute.getAll()`, không chỉ `get()` |
| `1.1` | Không trả user attributes thông thường; mapper phải phù hợp |
| `*` và `+` | Phân biệt user attributes với operational attributes theo backend |
| Attribute bị hạn chế ACL | Không cho rằng thiếu attribute nghĩa là dữ liệu không tồn tại |
| Tạo DTO rồi vô tình `save` như entity | Thiết kế API/ngăn ghi để không xóa nhầm dữ liệu ngoài projection |
| Directory có referral hoặc server size limit | Không báo kết quả đầy đủ khi các vùng chưa được tìm hết |

Không chạy bài test ghi trên directory production chỉ để xác minh projection. Việc lựa chọn thuộc tính là thao tác **đọc**; có thể đánh giá bằng test fixture và tài khoản chỉ đọc, sau đó đo hiệu năng trên môi trường có tải tương đương.

## 13. Các lỗi phổ biến và hướng xử lý

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Search trả đủ entry nhưng DTO có nhiều `null` | Projection thiếu field cần ánh xạ, thiếu ACL hoặc thuộc tính không tồn tại | Kiểm tra `attributes(...)`, schema và quyền đọc |
| Dùng `attributes("cn")` nhưng mapper đọc `mail` | Yêu cầu không khớp nhu cầu mapper | Thêm `mail` nếu được phép, hoặc đổi DTO |
| Search chậm dù chỉ lấy hai thuộc tính | Filter không được index, base/scope quá rộng, mạng/server nghẽn | Tối ưu search, kiểm tra index và server latency |
| `Attributes.get("dn")` trả `null` | DN không mặc nhiên là LDAP attribute | Dùng mapper/API có thông tin tên |
| Nhận mỗi một member của nhóm | Chỉ gọi `Attribute.get()` trên thuộc tính đa trị | Duyệt `getAll()` và kiểm tra AD range retrieval nếu có |
| Lấy `*` nhưng không thấy `modifyTimestamp` | Operational attributes thường không nằm trong selector `*` | Kiểm tra ACL/server, chọn thuộc tính operational rõ ràng hoặc `+` nếu hỗ trợ |
| Kết quả ít hơn mong đợi | Limit, scope, referral, ACL hoặc filter, không nhất thiết do projection | Kiểm tra riêng từng phần của query |
| Vô tình mở rộng quyền truy xuất | Client chọn danh sách thuộc tính tùy ý với bind account mạnh | Thiết kế allowlist/projection cố định, hạn chế ACL |
| Dùng entity tải thiếu trường để `save` | Ghi nhầm trạng thái không đầy đủ | Dùng DTO cho read-only hoặc thay đổi từng thuộc tính |

Đừng xử lý lỗi projection bằng `catch (Exception) { return List.of(); }`. Điều này khiến lỗi schema, thiếu quyền, lỗi kết nối hoặc mapper thiếu thuộc tính bị hiểu nhầm thành “không có người dùng nào khớp”.

## 14. Câu hỏi tự kiểm tra

1. Trong LDAP search, ba vai trò **base/scope**, **filter** và **returning attributes** khác nhau ra sao?
2. Vì sao lọc bằng `objectClass=inetOrgPerson` không đòi hỏi phải trả `objectClass` trong kết quả?
3. Khi muốn trả `uid`, `cn` và `mail`, cần khai báo `LdapQueryBuilder.attributes(...)` như thế nào?
4. `*`, `+` và `1.1` có ý nghĩa gì? Chúng có được hỗ trợ/được trả như nhau trên mọi server không?
5. Vì sao không thể lấy DN đầy đủ bằng cách mặc định gọi `attrs.get("dn")`?
6. Khi `mail` không xuất hiện trong response, có thể kết luận user không có email không? Vì sao?
7. Với thuộc tính `member` đa trị, vì sao `attr.get()` chưa đủ?
8. Vì sao tách DTO chỉ đọc khỏi entity ODM có thể ngăn lỗi mất dữ liệu khi cập nhật?
9. Cần đo những chỉ số nào để chứng minh chọn ít thuộc tính hơn thực sự có lợi?

**Ghi nhớ:** trong Spring Data LDAP/Spring LDAP, hãy **tìm đúng entry** bằng base/scope/filter và **chỉ trả đúng thuộc tính** mà use case cần bằng `.attributes(...)` hoặc `SearchControls.setReturningAttributes(...)`. Dùng `AttributesMapper` cho DTO nhỏ; dùng `ContextMapper` khi cần DN; xử lý thuộc tính tùy chọn/đa trị và kiểm soát ACL. Projection giúp giảm dữ liệu không cần thiết nhưng **không thay thế** tối ưu filter/index hoặc chính sách bảo mật của directory.

### Tài liệu tham khảo

- IETF [RFC 4511 — LDAP: The Protocol](https://www.rfc-editor.org/rfc/rfc4511): `SearchRequest`, `attributes`, `SearchResultEntry`, selector `*` và `1.1`.
- IETF [RFC 3673 — LDAP: All Operational Attributes](https://www.rfc-editor.org/rfc/rfc3673): selector `+` cho operational attributes.
- IETF [RFC 4515 — String Representation of Search Filters](https://www.rfc-editor.org/rfc/rfc4515): cú pháp/escape LDAP filter.
- Spring LDAP API: [`LdapQueryBuilder`](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/query/LdapQueryBuilder.html) và [`LdapTemplate`](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/core/LdapTemplate.html).
- Spring LDAP API: [`AttributesMapper`](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/core/AttributesMapper.html), [`ContextMapper`](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/core/ContextMapper.html).
- Oracle Java SE: [`SearchControls`](https://docs.oracle.com/en/java/javase/17/docs/api/java.naming/javax/naming/directory/SearchControls.html), [`Attribute`](https://docs.oracle.com/en/java/javase/17/docs/api/java.naming/javax/naming/directory/Attribute.html).
