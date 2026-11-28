# Dùng các lớp Filter khi cần tổ hợp điều kiện

Trong **Spring Data LDAP**, khi điều kiện tìm kiếm gồm nhiều nhánh AND/OR/NOT, một số điều kiện có thể được bật theo nghiệp vụ hoặc cần tái sử dụng giữa nhiều truy vấn, việc nối chuỗi LDAP filter thủ công rất khó đọc và dễ tạo lỗi escaping. Spring LDAP cung cấp các lớp trong package `org.springframework.ldap.filter` để biểu diễn filter thành **cây đối tượng**. Mỗi nút là một điều kiện hoặc một phép logic; khi hoàn tất, ứng dụng gọi `encode()` để nhận chuỗi filter theo cú pháp LDAP.

Bài thuộc chương **Bộ lọc**, tập trung vào chủ đề **“Dùng các lớp Filter khi cần tổ hợp điều kiện”**. Người học sẽ hiểu interface `Filter`, cách sử dụng `AndFilter`, `OrFilter`, `NotFilter`, các filter so sánh và kiểm tra thuộc tính, cách lồng nhóm điều kiện, quy tắc escaping, cách gắn filter vào `LdapQuery` và thực thi qua `LdapTemplate`. Các ví dụ dùng ngữ cảnh **SPRING_DATA_LDAP**: directory phân cấp, DN, `objectClass`, schema, service Java/Spring, truy vấn repository và bảo mật đầu vào.

**Điểm cốt lõi:** Filter object chỉ mô tả **điều kiện chọn entry**. Search base, scope, quyền bind, timeout, paging và việc thực thi vẫn do phần cấu hình/query/template và LDAP server quyết định.

## 1. Vì sao cần các lớp Filter?

Giả sử ứng dụng cần tìm nhân viên:

- Entry thuộc `inetOrgPerson`.
- Họ là Nguyen **hoặc** tên là An.
- Có attribute `mail`.
- Không phải tài khoản dịch vụ.
- Chỉ tìm trong nhánh `ou=people`.

Filter LDAP có thể được viết thành:

```ldap
(&(objectClass=inetOrgPerson)
  (|(sn=Nguyen)(givenName=An))
  (mail=*)
  (!(uid=svc-*)))
```

Chuỗi trên đúng về mặt cấu trúc nếu các điều kiện phù hợp schema, nhưng khi xây động bằng phép nối string, rất dễ:

- Thiếu hoặc thừa ngoặc.
- Đặt sai nhóm logic.
- Quên escape ký tự đặc biệt trong giá trị.
- Đưa input người dùng vào raw filter.
- Tạo một nhánh OR/AND sai khi có điều kiện tùy chọn.
- Khó kiểm thử từng nhánh độc lập.

Dùng Filter objects cho phép tách biểu thức thành từng phần:

```text
AndFilter
├── EqualsFilter(objectClass, inetOrgPerson)
├── OrFilter
│   ├── EqualsFilter(sn, Nguyen)
│   └── EqualsFilter(givenName, An)
├── PresentFilter(mail)
└── NotFilter
    └── LikeFilter(uid, svc-*)
```

Cây đối tượng phản ánh trực tiếp logic nghiệp vụ, giúp tái sử dụng và test filter trước khi gửi tới directory.

## 2. Interface Filter và phương thức encode()

Các lớp filter của Spring LDAP nằm trong package:

```java
import org.springframework.ldap.filter.Filter;
```

`Filter` là interface chung. Phương thức quan trọng:

```java
String encoded = filter.encode();
```

`encode()` tạo biểu diễn LDAP filter theo cú pháp chuẩn. Ví dụ:

```java
Filter filter = new EqualsFilter("uid", "u1001");
System.out.println(filter.encode());
```

Kết quả:

```ldap
(uid=u1001)
```

Một filter object có thể được:

1. Tạo từ một điều kiện đơn.
2. Ghép với filter khác bằng AND/OR.
3. Bao phủ bởi NOT.
4. Encode thành chuỗi để kiểm tra hoặc truyền cho API chấp nhận filter string.
5. Truyền trực tiếp cho `LdapQueryBuilder.filter(Filter)` để tạo `LdapQuery`.

**Encode không thực hiện truy vấn.** Nó chỉ chuyển cây filter thành chuỗi. Không gọi LDAP server cho đến khi đưa query vào `LdapTemplate` hoặc API LDAP tương ứng.

## 3. Nhóm các lớp Filter thường dùng

Spring LDAP cung cấp nhiều implementation cho các tình huống phổ biến:

| Lớp | Chức năng | Filter thường tạo |
|---|---|---|
| `EqualsFilter` | So sánh bằng | `(uid=u1001)` |
| `PresentFilter` | Kiểm tra attribute tồn tại | `(mail=*)` |
| `NotPresentFilter` | Kiểm tra attribute không có giá trị | `(!(mail=*))` |
| `LikeFilter` | So sánh substring, cho phép wildcard `*` | `(cn=An*)` |
| `WhitespaceWildcardsFilter` | Chuyển whitespace thành wildcard | `(cn=*An*Nguyen*)` |
| `GreaterThanOrEqualsFilter` | So sánh lớn hơn hoặc bằng | `(createTimestamp>=...)` |
| `LessThanOrEqualsFilter` | So sánh nhỏ hơn hoặc bằng | `(createTimestamp<=...)` |
| `AndFilter` | Ghép mọi nhánh theo AND | `(&(A)(B))` |
| `OrFilter` | Ghép các nhánh theo OR | `(|(A)(B))` |
| `NotFilter` | Phủ định một filter | `(!(A))` |
| `HardcodedFilter` | Chèn một đoạn filter viết sẵn | Chuỗi do developer kiểm soát |

Các lớp cụ thể có thể khác theo version Spring LDAP đang dùng. Hãy kiểm tra Javadoc của đúng dependency đã resolve trước khi sử dụng API mới hoặc API đã deprecated.

## 4. Filter đơn: EqualsFilter

`EqualsFilter` tạo điều kiện equality:

```java
import org.springframework.ldap.filter.EqualsFilter;

Filter uidFilter = new EqualsFilter("uid", "u1001");
System.out.println(uidFilter.encode());
```

Kết quả:

```ldap
(uid=u1001)
```

Ví dụ tìm người theo UID và object class:

```java
Filter personFilter =
        new EqualsFilter("objectClass", "inetOrgPerson");

Filter uidFilter =
        new EqualsFilter("uid", "u1001");
```

Không nên dùng tên thuộc tính Java như `commonName` nếu LDAP schema lưu attribute là `cn`. Tên attribute trong filter phải là tên LDAP thật, được server công bố trong schema.

### Equality và attribute nhiều giá trị

Nếu một entry có nhiều giá trị `mail`, filter `(mail=an@example.org)` khớp khi có ít nhất một giá trị phù hợp. Nó không có nghĩa tất cả giá trị đều bằng chuỗi đó.

Cũng cần nhớ matching rule của LDAP server có thể không giống `String.equals()` trong Java. Việc so sánh có phân biệt hoa/thường, chuẩn hóa Unicode hay không phụ thuộc syntax/matching rule của attribute.

## 5. Kiểm tra attribute tồn tại và không tồn tại

Dùng `PresentFilter` khi cần kiểm tra một attribute có ít nhất một giá trị:

```java
import org.springframework.ldap.filter.PresentFilter;

Filter hasMail = new PresentFilter("mail");
```

Kết quả:

```ldap
(mail=*)
```

Dùng `NotPresentFilter` khi cần tìm entry chưa có giá trị cho attribute:

```java
import org.springframework.ldap.filter.NotPresentFilter;

Filter missingMail = new NotPresentFilter("mail");
```

Kết quả:

```ldap
(!(mail=*))
```

Không nhầm hai trường hợp:

- `(!(mail=blocked@example.org))`: entry không có giá trị mail khớp với giá trị bị chặn, hoặc không có giá trị nào khớp.
- `(!(mail=*))`: entry không có giá trị `mail`.

Nếu nghiệp vụ cần **có email và không phải email bị chặn**, phải kết hợp `PresentFilter` với `NotFilter(EqualsFilter)`, như phần 8.

## 6. Tạo nhóm AND bằng AndFilter

`AndFilter` yêu cầu **mọi nhánh con** đều khớp. Cách sử dụng:

```java
import org.springframework.ldap.filter.AndFilter;
import org.springframework.ldap.filter.EqualsFilter;
import org.springframework.ldap.filter.PresentFilter;

AndFilter filter = new AndFilter();
filter.and(new EqualsFilter("objectClass", "inetOrgPerson"));
filter.and(new EqualsFilter("employeeStatus", "active"));
filter.and(new PresentFilter("mail"));

System.out.println(filter.encode());
```

Filter kết quả:

```ldap
(&(objectClass=inetOrgPerson)(employeeStatus=active)(mail=*))
```

Trong đó:

- `new AndFilter()` tạo một nhóm AND.
- `and(Filter)` thêm một điều kiện con.
- Có thể thêm nhiều nhánh vào cùng nhóm.
- Mỗi nhánh có thể là filter đơn hoặc một nhóm logic lồng nhau.

Ví dụ nghiệp vụ: tìm nhân viên đang active, có email và có mã nhân viên:

```java
AndFilter activeEmployee = new AndFilter();
activeEmployee.and(
        new EqualsFilter("objectClass", "inetOrgPerson"));
activeEmployee.and(
        new EqualsFilter("employeeStatus", "active"));
activeEmployee.and(
        new PresentFilter("employeeNumber"));
activeEmployee.and(
        new PresentFilter("mail"));
```

**AND giúp biểu diễn điều kiện bắt buộc.** Nếu một nhánh bắt buộc không khớp, entry không xuất hiện trong kết quả.

## 7. Tạo nhóm OR bằng OrFilter

`OrFilter` khớp nếu **ít nhất một nhánh con** khớp:

```java
import org.springframework.ldap.filter.OrFilter;

OrFilter nameFilter = new OrFilter();
nameFilter.or(new EqualsFilter("sn", "Nguyen"));
nameFilter.or(new EqualsFilter("givenName", "An"));

System.out.println(nameFilter.encode());
```

Kết quả:

```ldap
(|(sn=Nguyen)(givenName=An))
```

Ví dụ này tìm entry có họ Nguyen hoặc tên An. Không phải cả hai điều kiện đều phải đúng.

Có thể đưa nhiều lựa chọn vào OR:

```java
OrFilter loginFilter = new OrFilter();
loginFilter.or(new EqualsFilter("uid", "u1001"));
loginFilter.or(new EqualsFilter("mail", "an@example.org"));
loginFilter.or(new EqualsFilter(
        "userPrincipalName", "an@example.org"));
```

Đây là cách hữu ích khi nhiều loại identifier hợp lệ được ánh xạ về cùng một principal. Tuy nhiên, nếu nhiều entry cùng khớp các nhánh khác nhau, ứng dụng phải kiểm tra số kết quả; **không lấy entry đầu tiên rồi giả định định danh duy nhất**.

## 8. Phủ định bằng NotFilter

`NotFilter` nhận một `Filter` và phủ định kết quả của nó:

```java
import org.springframework.ldap.filter.NotFilter;

Filter notDisabled = new NotFilter(
        new EqualsFilter("employeeStatus", "disabled"));

System.out.println(notDisabled.encode());
```

Kết quả:

```ldap
(!(employeeStatus=disabled))
```

Một ví dụ khác: tìm người có mail và không dùng địa chỉ bị chặn:

```java
AndFilter allowedMail = new AndFilter();
allowedMail.and(new PresentFilter("mail"));
allowedMail.and(new NotFilter(
        new EqualsFilter("mail", "blocked@example.org")));
```

Filter:

```ldap
(&(mail=*)(!(mail=blocked@example.org)))
```

Điều kiện presence rất quan trọng. Nếu chỉ viết NOT equality, entry không có attribute vẫn có thể khớp. Với attribute nhiều giá trị, equality có thể khớp nếu bất kỳ giá trị nào bằng chuỗi đã cho; phủ định sẽ loại entry nếu nhánh equality khớp.

## 9. Lồng AND, OR và NOT thành cây filter

Bài toán thực tế thường có dạng:

**(objectClass là inetOrgPerson) AND (sn là Nguyen OR givenName là An) AND (mail tồn tại) AND NOT (employeeStatus là disabled).**

Ta có thể dựng cây như sau:

```java
AndFilter root = new AndFilter();

root.and(new EqualsFilter(
        "objectClass", "inetOrgPerson"));

OrFilter name = new OrFilter();
name.or(new EqualsFilter("sn", "Nguyen"));
name.or(new EqualsFilter("givenName", "An"));

root.and(name);
root.and(new PresentFilter("mail"));
root.and(new NotFilter(
        new EqualsFilter("employeeStatus", "disabled")));

System.out.println(root.encode());
```

Kết quả:

```ldap
(&(objectClass=inetOrgPerson)
  (|(sn=Nguyen)(givenName=An))
  (mail=*)
  (!(employeeStatus=disabled)))
```

Đọc từ ngoài vào:

1. Root là AND, nên tất cả nhánh cấp cao phải đúng.
2. Nhánh tên là OR, nên chỉ cần họ hoặc tên khớp.
3. Nhánh mail yêu cầu attribute tồn tại.
4. Nhánh NOT loại entry có trạng thái disabled.

### So sánh hai cách đặt ngoặc

Giả sử cần điều kiện `(A OR B) AND C`:

```ldap
(&(|(A)(B))(C))
```

Nếu viết thành `A OR (B AND C)`:

```ldap
(|(A)(&(B)(C)))
```

Hai biểu thức cho kết quả khác nhau. Khi xây cây Filter, hãy tạo nhóm đúng theo yêu cầu nghiệp vụ thay vì thêm từng nhánh vào một root mà không kiểm tra ngoặc.

## 10. Tìm theo substring với LikeFilter

`LikeFilter` cho phép ký tự `*` hoạt động như wildcard trong giá trị filter:

```java
import org.springframework.ldap.filter.LikeFilter;

Filter nameStartsWithAn =
        new LikeFilter("cn", "An*");

Filter nameContainsNguyen =
        new LikeFilter("cn", "*Nguyen*");
```

Ví dụ filter:

```ldap
(cn=An*)
(cn=*Nguyen*)
```

Khác với `EqualsFilter`, `LikeFilter` giữ wildcard `*` có chủ đích. Vì vậy:

- Dùng `EqualsFilter` cho tìm chính xác.
- Dùng `LikeFilter` khi ứng dụng chủ động muốn tìm prefix/suffix/substring.
- Nếu pattern đến từ người dùng, hãy validate hoặc giới hạn wildcard theo nghiệp vụ.
- Không đưa chuỗi raw không đáng tin vào một pattern wildcard mà không xác định rõ semantics.

Ví dụ: nếu API chỉ cho phép tìm prefix, ứng dụng có thể kiểm tra đầu vào không chứa wildcard do người dùng tự thêm, rồi tự nối wildcard ở cuối.

## 11. Tìm tên gần đúng với WhitespaceWildcardsFilter

`WhitespaceWildcardsFilter` tự chuyển khoảng trắng thành wildcard. Ví dụ:

```java
import org.springframework.ldap.filter.WhitespaceWildcardsFilter;

Filter nameSearch =
        new WhitespaceWildcardsFilter("cn", "An Nguyen");
```

Kết quả dạng:

```ldap
(cn=*An*Nguyen*)
```

Filter này hữu ích với ô tìm kiếm tên đầy đủ, nơi người dùng nhập nhiều từ nhưng không biết server lưu cách viết nào. Nó có thể tạo truy vấn rộng hơn equality, vì vậy cần giới hạn base/scope, số kết quả và thời gian.

Không dùng filter tìm gần đúng làm định danh đăng nhập duy nhất. Tìm kiếm tên có thể trả nhiều entry; authentication phải định vị một DN duy nhất bằng thuộc tính login đã được quy định.

## 12. So sánh lớn hơn/nhỏ hơn

Spring LDAP cung cấp:

- `GreaterThanOrEqualsFilter`: tạo điều kiện `>=`.
- `LessThanOrEqualsFilter`: tạo điều kiện `<=`.

Ví dụ:

```java
import org.springframework.ldap.filter.GreaterThanOrEqualsFilter;
import org.springframework.ldap.filter.LessThanOrEqualsFilter;

Filter createdSince = new GreaterThanOrEqualsFilter(
        "createTimestamp", "20260101000000Z");

Filter createdBefore = new LessThanOrEqualsFilter(
        "createTimestamp", "20261231235959Z");
```

Kết hợp để tìm entry trong khoảng thời gian:

```java
AndFilter createdInYear = new AndFilter();
createdInYear.and(new GreaterThanOrEqualsFilter(
        "createTimestamp", "20260101000000Z"));
createdInYear.and(new LessThanOrEqualsFilter(
        "createTimestamp", "20261231235959Z"));
```

Các phép so sánh phụ thuộc **ordering matching rule** của attribute. Đừng dùng chúng cho attribute có syntax/matching rule không hỗ trợ ordering. Định dạng timestamp ở ví dụ chỉ là minh họa; hãy dùng đúng syntax của attribute trên server đích. Với AD, OpenLDAP và schema tùy chỉnh, thuộc tính thời gian và định dạng có thể khác nhau.

## 13. Dùng HardcodedFilter có kiểm soát

`HardcodedFilter` cho phép thêm một đoạn filter đã viết sẵn:

```java
import org.springframework.ldap.filter.HardcodedFilter;

Filter objectClassFilter =
        new HardcodedFilter("(objectClass=inetOrgPerson)");
```

Nó hữu ích khi cần giữ một mảnh cú pháp LDAP do developer kiểm soát hoặc tích hợp filter được định nghĩa tĩnh. Tuy nhiên, **HardcodedFilter không phải bộ escape cho giá trị đầu vào**.

Không làm như sau:

```java
// Không an toàn: raw user input được nối vào cú pháp filter.
Filter unsafe = new HardcodedFilter(
        "(uid=" + username + ")");
```

Với giá trị động, dùng `EqualsFilter` hoặc các Filter class phù hợp để Spring LDAP xử lý encoding. Không dùng `HardcodedFilter` để đưa raw filter, tên attribute hoặc pattern từ HTTP request vào LDAP.

## 14. Ghép các filter có điều kiện tùy chọn

Một màn hình có thể cho phép người dùng nhập họ, email hoặc trạng thái. Chỉ thêm nhánh khi tham số đã được cung cấp:

```java
public Filter buildPeopleFilter(
        String surname,
        String email,
        String status) {

    AndFilter root = new AndFilter();
    root.and(new EqualsFilter(
            "objectClass", "inetOrgPerson"));

    if (surname != null && !surname.isBlank()) {
        root.and(new EqualsFilter("sn", surname));
    }

    if (email != null && !email.isBlank()) {
        root.and(new EqualsFilter("mail", email));
    }

    if (status != null && !status.isBlank()) {
        root.and(new EqualsFilter("employeeStatus", status));
    }

    return root;
}
```

Điểm cần chú ý:

- Điều kiện `objectClass` luôn có để giới hạn loại entry.
- Các nhánh tùy chọn được thêm có kiểm tra input.
- Giá trị được truyền qua constructor của filter cụ thể.
- Không tạo nhánh rỗng hoặc một filter rộng hơn ý định.
- Nên giới hạn số điều kiện và chiều dài input.
- Nếu không có điều kiện nghiệp vụ nào ngoài `objectClass`, xác nhận đó là yêu cầu hợp lệ trước khi chạy search.

Trong code sản xuất, nên tách validation/allowlist ra một lớp riêng và có test cho từng tổ hợp tham số.

## 15. Gắn Filter vào LdapQuery và thực thi bằng LdapTemplate

Filter object có thể được truyền vào `LdapQueryBuilder.filter(Filter)`. Cách này giữ riêng phần điều kiện và phần cấu hình search:

```java
import java.util.List;

import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.SearchScope;

import static org.springframework.ldap.query.LdapQueryBuilder.query;

public final class DirectoryPeopleSearch {

    public record PersonSummary(
            String uid, String commonName, String email) {}

    private final LdapTemplate ldapTemplate;

    public DirectoryPeopleSearch(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<PersonSummary> findPeople(
            String surname, String givenName) {

        AndFilter root = new AndFilter();
        root.and(new EqualsFilter(
                "objectClass", "inetOrgPerson"));

        OrFilter name = new OrFilter();
        name.or(new EqualsFilter("sn", surname));
        name.or(new EqualsFilter("givenName", givenName));

        root.and(name);
        root.and(new PresentFilter("mail"));

        LdapQuery request = query()
                .base("ou=people")
                .searchScope(SearchScope.SUBTREE)
                .countLimit(100)
                .timeLimit(3000)
                .attributes("uid", "cn", "mail")
                .filter(root);

        AttributesMapper<PersonSummary> mapper = attrs ->
                new PersonSummary(
                        value(attrs, "uid"),
                        value(attrs, "cn"),
                        value(attrs, "mail"));

        return ldapTemplate.search(request, mapper);
    }

    private static String value(
            javax.naming.directory.Attributes attrs,
            String name) throws javax.naming.NamingException {
        javax.naming.directory.Attribute attribute = attrs.get(name);
        return attribute == null ? null
                : String.valueOf(attribute.get());
    }
}
```

Ví dụ minh họa cách tích hợp; service thực tế cần kiểm tra `surname` và `givenName` không rỗng trước khi dựng OR. Các điểm quan trọng:

1. `root` mô tả điều kiện logic.
2. `base("ou=people")` giới hạn nhánh tìm kiếm.
3. `searchScope(SUBTREE)` cho phép tìm trong các OU con của nhánh đó.
4. `countLimit` và `timeLimit` giới hạn search ở phía client request.
5. `attributes(...)` chỉ yêu cầu field cần thiết.
6. `filter(root)` gắn cây Filter vào query.
7. `LdapTemplate` thực hiện truy vấn và mapper tạo DTO.

Không nhầm base DN với filter. Filter không thể giới hạn quyền đọc ngoài ACL và cũng không tự xử lý referral hoặc paging.

## 16. Escaping và LDAP injection

LDAP filter có các ký tự đặc biệt cần được encode trong giá trị assertion, thường gồm:

| Ký tự đầu vào | Dạng escape trong filter |
|---|---|
| `*` | `\2a` |
| `(` | `\28` |
| `)` | `\29` |
| `\` | `\5c` |
| NUL | `\00` |

Các lớp như `EqualsFilter` được thiết kế để xây filter từ attribute/value và encode giá trị theo quy tắc LDAP. Đây là lý do nên dùng filter object thay vì nối chuỗi.

Ví dụ:

```java
String userInput = "u1001*)(uid=*)";

Filter safe = new EqualsFilter("uid", userInput);
System.out.println(safe.encode());
```

Giá trị đầu vào được xem như **một giá trị UID duy nhất**, không được phép đóng ngoặc rồi thêm nhánh filter khác.

### Attribute name vẫn cần allowlist

Encoding giá trị không tự bảo vệ attribute name. Nếu client được gửi tên attribute tùy ý, hãy map một enum hoặc key API sang danh sách cố định:

```java
public enum PersonSearchField {
    UID("uid"),
    EMAIL("mail"),
    COMMON_NAME("cn");

    private final String ldapAttribute;

    PersonSearchField(String ldapAttribute) {
        this.ldapAttribute = ldapAttribute;
    }

    public String ldapAttribute() {
        return ldapAttribute;
    }
}
```

Không nhận raw attribute description từ client. Tương tự, base DN và scope phải được ứng dụng kiểm soát.

### Wildcard có chủ đích

`LikeFilter` và `WhitespaceWildcardsFilter` có semantics wildcard. Nếu nghiệp vụ cần ký tự `*` như dữ liệu literal, không dùng một filter wildcard mà không xác định cách encode riêng. Với exact match, ưu tiên `EqualsFilter`.

## 17. Filter, schema và khác biệt directory server

Một filter có cú pháp hợp lệ vẫn có thể không hoạt động như mong đợi nếu schema không phù hợp.

- `objectClass` và attribute name phải tồn tại trên server.
- Attribute có thể có syntax single-valued hoặc multi-valued.
- Equality, substring, ordering và approximate matching phụ thuộc matching rule.
- Một server có thể không index attribute, khiến filter đúng nhưng rất chậm.
- ACL có thể ẩn attribute hoặc entry khỏi bind identity.
- Attribute operational có thể cần yêu cầu tường minh.
- AD thường dùng các attribute như `sAMAccountName`/`userPrincipalName`; OpenLDAP có thể dùng `uid`/`inetOrgPerson`. Không lấy schema của một server làm mặc định cho mọi server.

Với filter OR trên nhiều attribute, cần xác nhận tất cả attribute có thể tìm và matching rule tương ứng. Nếu một nhánh dùng attribute không tồn tại, kết quả có thể phụ thuộc server và schema.

**Filter đúng cú pháp không chứng minh dữ liệu đầy đủ.** Kết quả rỗng có thể do base/scope sai, ACL, referral, size/time limit hoặc thuộc tính không có.

## 18. Kiểm thử các lớp Filter

Nên kiểm tra cả **chuỗi encode**, **cấu trúc logic** và **kết quả thực tế**.

### 18.1 Unit test encode

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;
import org.springframework.ldap.filter.AndFilter;
import org.springframework.ldap.filter.EqualsFilter;
import org.springframework.ldap.filter.OrFilter;
import org.springframework.ldap.filter.PresentFilter;

class DirectoryFilterTest {

    @Test
    void buildsNestedAndOrFilter() {
        AndFilter root = new AndFilter();
        root.and(new EqualsFilter(
                "objectClass", "inetOrgPerson"));

        OrFilter names = new OrFilter();
        names.or(new EqualsFilter("sn", "Nguyen"));
        names.or(new EqualsFilter("givenName", "An"));

        root.and(names);
        root.and(new PresentFilter("mail"));

        assertEquals(
                "(&(objectClass=inetOrgPerson)"
                + "(|(sn=Nguyen)(givenName=An))(mail=*))",
                root.encode());
    }
}
```

Test này xác minh biểu thức filter được dựng đúng. Nó không chứng minh LDAP server trả đúng kết quả.

### 18.2 Test encoding ký tự đặc biệt

```java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;
import org.springframework.ldap.filter.EqualsFilter;

class DirectoryFilterEncodingTest {

    @Test
    void treatsUserInputAsOneEqualityValue() {
        String input = "u1001*)(uid=*)";
        String encoded =
                new EqualsFilter("uid", input).encode();

        assertTrue(encoded.contains("\\2a"));
        assertTrue(encoded.contains("\\28"));
        assertTrue(encoded.contains("\\29"));
        assertFalse(encoded.contains(")(uid=*)"));
    }
}
```

Kiểm tra encoding theo API/version đang dùng. Không kiểm tra bằng cách chỉ so sánh chuỗi con quá lỏng; nên assert toàn bộ encoded filter hoặc dùng test phù hợp với contract của dependency.

### 18.3 Integration test với LDAP test server

Chuẩn bị entry:

| UID | Họ | Tên | Mail | Status |
|---|---|---|---|---|
| u1001 | Nguyen | An | an@example.org | active |
| u1002 | Nguyen | Binh | Không có | active |
| u1003 | Tran | An | tran@example.org | active |
| u1004 | Le | Minh | minh@example.org | disabled |

Kiểm thử:

1. AND chỉ trả entry thỏa mọi nhánh.
2. OR trả entry khớp ít nhất một nhánh.
3. NOT loại entry khớp điều kiện bị phủ định.
4. Present/NotPresent phân biệt attribute có/không có.
5. Attribute nhiều giá trị được kiểm tra với semantics thực.
6. LikeFilter và WhitespaceWildcardsFilter trả kết quả đúng với wildcard.
7. Input chứa dấu sao, ngoặc, backslash và NUL không tạo nhánh filter mới.
8. Base/scope không vượt OU được cho phép.
9. Attribute allowlist từ chối tên không hỗ trợ.
10. ACL, size/time limit và referral được xử lý theo policy.

### 18.4 Test trên đúng loại server

Mock hữu ích cho logic service nhưng không thay thế integration test. OpenLDAP, Active Directory và directory thương mại có thể khác về schema, matching rule, ACL, referral, index và giới hạn search. Chạy bộ test trên sản phẩm/phiên bản directory mục tiêu trước khi phát hành.

## 19. Lỗi thường gặp và cách khắc phục

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Nối chuỗi filter thủ công | Sai ngoặc, LDAP injection | Dùng Filter objects |
| Thêm mọi điều kiện vào AndFilter | Mất ý nghĩa OR | Tạo OrFilter riêng rồi thêm vào nhóm cha |
| Thiếu NotFilter wrapper | Phủ định sai nhánh | Bọc đúng filter cần phủ định |
| Dùng NotFilter thay cho NotPresentFilter | Không kiểm tra đúng ý định attribute vắng mặt | Dùng NotPresentFilter hoặc NotFilter(PresentFilter) |
| Dùng EqualsFilter cho wildcard | Wildcard bị encode thành dữ liệu | Dùng LikeFilter khi wildcard có chủ đích |
| Dùng LikeFilter cho login chính xác | Tìm ra nhiều account | Dùng EqualsFilter |
| Không kiểm tra attribute name | Truy vấn ngoài schema/allowlist | Map field API sang attribute cố định |
| HardcodedFilter nhận user input | Không encode giá trị | Dùng EqualsFilter hoặc filter phù hợp |
| Quên base/scope | Tìm quá rộng hoặc sai nhánh | Đặt search base/scope riêng trong LdapQuery |
| Dùng gte/lte không có matching rule | Search lỗi hoặc không đúng kỳ vọng | Xác minh schema và matching rule |
| Chỉ test encode | Chưa kiểm chứng server behavior | Bổ sung integration test |
| Log filter nguyên văn | Có thể lộ PII hoặc giá trị nhạy cảm | Mask/redact trước khi log |

## 20. Bài tập thực hành

Một ứng dụng cần tìm nhân viên trong `ou=people` với điều kiện:

- `objectClass=inetOrgPerson`.
- Họ là Nguyen hoặc tên là An.
- Có `mail`.
- `employeeStatus` không phải disabled.
- Chỉ trả `uid`, `cn` và `mail`.

Hãy làm theo các bước:

1. Tạo `AndFilter` làm root.
2. Thêm `EqualsFilter` cho objectClass.
3. Tạo `OrFilter` riêng cho surname và givenName.
4. Thêm `PresentFilter("mail")`.
5. Thêm `NotFilter(new EqualsFilter("employeeStatus", "disabled"))`.
6. Encode filter và so sánh với biểu thức LDAP dự kiến.
7. Gắn filter vào `LdapQueryBuilder` với base `ou=people`, scope `SUBTREE`.
8. Đặt count/time limit và chỉ yêu cầu ba attribute.
9. Chạy search qua `LdapTemplate` và map thành DTO.
10. Kiểm tra entry thiếu mail, entry có nhiều mail, entry disabled và entry ở OU con.
11. Thử input chứa ký tự đặc biệt và xác minh filter không bị thay đổi cấu trúc.
12. Viết unit test cho cây filter và integration test cho kết quả server.

**Gợi ý code:**

```java
AndFilter root = new AndFilter();
root.and(new EqualsFilter("objectClass", "inetOrgPerson"));

OrFilter name = new OrFilter();
name.or(new EqualsFilter("sn", surname));
name.or(new EqualsFilter("givenName", givenName));
root.and(name);

root.and(new PresentFilter("mail"));
root.and(new NotFilter(
        new EqualsFilter("employeeStatus", "disabled")));

LdapQuery request = query()
        .base("ou=people")
        .searchScope(SearchScope.SUBTREE)
        .countLimit(100)
        .timeLimit(3000)
        .attributes("uid", "cn", "mail")
        .filter(root);
```

Giá trị surname/givenName cần được validate trước khi dựng query. Không nhận raw filter hoặc base DN từ HTTP request.

## 21. Checklist và tổng kết

Trước khi đưa Filter object vào service:

- [ ] Chọn đúng lớp cho equality, presence, absence, substring và ordering.
- [ ] Dùng `AndFilter`/`OrFilter` để biểu diễn nhóm logic rõ ràng.
- [ ] Dùng `NotFilter` để phủ định đúng một nhánh; phân biệt với `NotPresentFilter`.
- [ ] Tạo nhóm con trước khi thêm vào nhóm cha để giữ đúng ngoặc.
- [ ] Dùng `encode()` để kiểm tra biểu thức, nhớ rằng encode không thực thi query.
- [ ] Không đưa raw input vào `HardcodedFilter` hoặc chuỗi filter thủ công.
- [ ] Dùng `LikeFilter`/`WhitespaceWildcardsFilter` khi wildcard là yêu cầu có chủ đích.
- [ ] Allowlist tên attribute và kiểm soát base DN/scope.
- [ ] Kiểm tra schema, matching rule, multi-valued attribute và ACL.
- [ ] Đặt count/time limit, paging và xử lý referral/partial result theo nhu cầu.
- [ ] Không log filter chứa dữ liệu cá nhân hoặc thông tin nhạy cảm.
- [ ] Có unit test encode và integration test với đúng LDAP server.

### Tài liệu tham khảo

- [Spring LDAP — Filter API](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/filter/Filter.html).
- [Spring LDAP — Filter package summary](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/filter/package-summary.html).
- [Spring LDAP — AndFilter](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/filter/AndFilter.html).
- [Spring LDAP — OrFilter](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/filter/OrFilter.html).
- [Spring LDAP — NotFilter](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/filter/NotFilter.html).
- [Spring LDAP — EqualsFilter](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/filter/EqualsFilter.html).
- [Spring LDAP — CompareFilter](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/filter/CompareFilter.html).
- [Spring LDAP — LikeFilter](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/filter/LikeFilter.html).
- [RFC 4515 — LDAP Search Filter String Representation](https://www.rfc-editor.org/rfc/rfc4515).

Spring LDAP đã thay đổi một số API filter trong các phiên bản mới. Đặc biệt, các constructor/phương thức của `CompareFilter` có ghi deprecated từ Spring LDAP 3.3; khi tự tạo filter class riêng, cần dùng constructor mới nhận operator và giá trị đã encode theo Javadoc của đúng version. Với filter có sẵn, ưu tiên constructor public của lớp tương ứng và tránh gọi method deprecated.

**Kết luận:** các lớp `Filter` biến LDAP filter thành cây đối tượng có thể ghép, kiểm tra và tái sử dụng. `AndFilter`, `OrFilter` và `NotFilter` giúp giữ đúng nhóm logic; các filter so sánh/presence thể hiện điều kiện trên attribute; `encode()` chuyển cây thành biểu thức LDAP. Khi kết hợp với base/scope rõ ràng, escaping đúng ngữ cảnh, allowlist attribute, schema/matching rule và integration test, ứng dụng Spring Data LDAP có thể xây các truy vấn phức tạp dễ đọc và an toàn hơn.
