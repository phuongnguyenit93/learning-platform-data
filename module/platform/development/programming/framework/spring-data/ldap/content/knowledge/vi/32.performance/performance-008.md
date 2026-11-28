# Xử lý nhóm lớn và thuộc tính nhiều giá trị

> **Chương:** Hiệu năng  
> **Module:** SPRING_DATA_LDAP — truy cập dịch vụ thư mục LDAP qua Spring Data LDAP, ánh xạ entry phân cấp sang đối tượng Java, hiểu DN, objectClass, schema, truy vấn repository/LdapTemplate, CRUD, filter an toàn, bảo mật kết nối và kiểm thử với directory.

Trong LDAP, một entry nhóm có thể chứa hàng trăm, hàng nghìn hoặc nhiều hơn các giá trị thành viên trong cùng một attribute. Ví dụ, `groupOfNames` lưu DN của từng thành viên trong attribute `member`. Các attribute như `telephoneNumber`, `mail` hoặc `description` cũng có thể là đa trị theo schema.

Khi số lượng giá trị tăng, thao tác tưởng như đơn giản — đọc toàn bộ thành viên, thêm một người vào nhóm, tìm tất cả nhóm của một user hoặc đồng bộ danh sách thành viên — có thể tạo payload lớn, tốn nhiều round trip, gây tải lên directory và ảnh hưởng tới thời gian đăng nhập/ủy quyền.

Muốn tối ưu đúng, cần phân biệt **nhiều entry** với **nhiều giá trị trong một entry**. LDAP Search paging giúp chia trang entry; nó không tự chia trang các giá trị của một attribute lớn. Tương tự, một LDAP ModifyRequest có thể thay đổi nhiều giá trị của một attribute trên một entry, nhưng không phải bulk transaction cho nhiều entry nhóm.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

1. Phân biệt attribute đơn trị, attribute đa trị, nhóm có nhiều thành viên và nhiều entry.
2. Giải thích cách `groupOfNames.member`, `groupOfUniqueNames.uniqueMember` và `posixGroup.memberUid` lưu thành viên khác nhau.
3. Đọc attribute đa trị bằng `LdapTemplate` mà không làm mất giá trị.
4. Thêm/xóa một giá trị hoặc nhiều giá trị bằng ModifyRequest có chủ đích.
5. Tìm nhóm chứa một user bằng equality filter trên DN thành viên.
6. Nhận biết N+1 lookup, response quá lớn và giới hạn của server.
7. Phân biệt LDAP Paged Results Control với cơ chế ranged retrieval riêng của Active Directory.
8. Thiết kế nested group, cache quyền và đồng bộ membership an toàn.
9. Đo hiệu năng và kiểm thử nhóm lớn trên directory test.

## 2. Attribute đa trị và nhóm lớn là gì?

LDAP entry là tập attribute; một attribute có thể chứa một hoặc nhiều giá trị tùy schema. Ví dụ:

~~~ldif
dn: uid=lan,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: lan
cn: Tran Thi Lan
sn: Tran
mail: lan@example.org
mail: lan.work@example.org
telephoneNumber: +84 28 1234 5678
telephoneNumber: +84 90 111 2222
~~~

Entry trên có hai giá trị `mail` và hai giá trị `telephoneNumber`. Chúng vẫn là **một entry**, có một DN.

Ví dụ nhóm có nhiều thành viên:

~~~ldif
dn: cn=developers,ou=groups,dc=example,dc=org
objectClass: top
objectClass: groupOfNames
cn: developers
member: uid=lan,ou=people,dc=example,dc=org
member: uid=binh,ou=people,dc=example,dc=org
member: uid=minh,ou=people,dc=example,dc=org
~~~

Nhóm `developers` là một entry; attribute `member` chứa ba giá trị DN. Nếu nhóm có 20.000 thành viên, về cấu trúc vẫn là **một entry với một attribute có 20.000 giá trị**, nếu directory/schema/server cho phép.

| Trường hợp | Entry count | Value count |
|---|---:|---:|
| Một user có hai số điện thoại | 1 | 2 giá trị `telephoneNumber` |
| Một group có 5.000 thành viên | 1 | 5.000 giá trị `member` |
| 5.000 user entry riêng biệt | 5.000 | Mỗi entry có các attribute riêng |
| 100 group, mỗi group có 1.000 thành viên | 100 | 100.000 giá trị `member` cộng dồn |

Đây là khác biệt quyết định cách tối ưu: Search paging phân trang **entry**, còn đọc attribute đa trị lớn cần xem xét giới hạn giá trị của attribute và tính năng riêng của directory server.

## 3. Các mô hình lưu thành viên thường gặp

Không phải mọi schema lưu membership theo cùng một cách.

| Object class / attribute | Giá trị thành viên | Đặc điểm |
|---|---|---|
| `groupOfNames.member` | DN đầy đủ của member | `member` là thuộc tính MUST; nhóm phải có ít nhất một member theo schema chuẩn |
| `groupOfUniqueNames.uniqueMember` | Name and Optional UID | Giá trị là DN kèm thành phần UID tùy chọn theo syntax của attribute |
| `posixGroup.memberUid` | UID dạng chuỗi | Không phải DN; phụ thuộc schema POSIX/RFC 2307 |
| Dynamic group | Filter/URL hoặc cơ chế server-specific | Membership được tính theo điều kiện, không nhất thiết lưu danh sách DN trong `member` |
| Nested group | DN của group khác làm member | Cần quy tắc mở rộng nhóm và xử lý chu trình |

### groupOfNames

`groupOfNames` của schema LDAP phổ biến yêu cầu `cn` và ít nhất một giá trị `member`. Vì vậy, không thể xóa thành viên cuối cùng bằng cách xóa toàn bộ attribute rồi vẫn kỳ vọng entry hợp lệ theo schema đó.

### groupOfUniqueNames

`groupOfUniqueNames` sử dụng `uniqueMember`, có syntax riêng `NameAndOptionalUID`. Không thay thế giá trị `uniqueMember` bằng chuỗi UID tùy ý. Hãy kiểm tra schema và matching rule trên directory server.

### posixGroup

`posixGroup` thường dùng `memberUid` là UID dạng Directory String. Ứng dụng không thể giả định giá trị này là DN hay tự thêm hậu tố base DN.

**Không đổi objectClass chỉ để giảm payload** nếu chưa đánh giá toàn bộ consumer, schema, hệ điều hành/dịch vụ tích hợp và semantics phân quyền.

## 4. Chi phí hiệu năng khi nhóm có nhiều giá trị

Một nhóm lớn tác động tới nhiều lớp:

~~~text
HTTP / login / authorization request
             |
             v
       Spring Security
             |
             v
      LdapTemplate / Repository
             |
             v
       LDAP Search / Modify
             |
             v
  Entry group + attribute member lớn
             |
       +-----+------+
       |            |
    Network       Directory
    payload       memory/index/replication
~~~

Các yếu tố chính:

- **Payload:** một lần đọc group có thể trả hàng nghìn DN, làm tăng bytes truyền qua mạng và thời gian parse.
- **Bộ nhớ:** mapper giữ toàn bộ danh sách member trong `List<String>` có thể làm tăng heap đáng kể.
- **Latency:** response lớn và search filter trên attribute không có index có thể chậm.
- **Replication:** thay đổi membership có thể tạo công việc đồng bộ lớn; cách server ghi/replicate nội bộ tùy sản phẩm.
- **Authorization:** mỗi lần login đọc và mở rộng nhiều group có thể tạo nhiều search/lookup.
- **Concurrency:** nhiều request đồng thời tải cùng group lớn có thể tạo tải lặp lại.
- **Cache:** giảm truy vấn nhưng tăng độ trễ khi cấp/thu hồi quyền nếu invalidation không rõ.

Không chỉ đếm số LDAP requests. Cần đo cả **response bytes, số giá trị, latency, heap, CPU directory và replication/authorization delay**.

## 5. Đọc attribute đa trị bằng LdapTemplate

Khi nhóm có số lượng thành viên vừa phải và ứng dụng thực sự cần toàn bộ danh sách, có thể đọc attribute bằng `AttributesMapper`:

~~~java
import java.util.ArrayList;
import java.util.List;

import javax.naming.NamingEnumeration;
import javax.naming.NamingException;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;
import javax.naming.Name;

import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;

public List<String> readGroupMembers(
        LdapTemplate ldapTemplate, Name groupDn) {

    return ldapTemplate.lookup(
            groupDn,
            (AttributesMapper<List<String>>) attrs ->
                    readStringValues(attrs, "member"));
}

private static List<String> readStringValues(
        Attributes attrs, String attributeName)
        throws NamingException {

    Attribute attribute = attrs.get(attributeName);
    if (attribute == null) {
        return List.of();
    }

    List<String> values = new ArrayList<>(attribute.size());
    NamingEnumeration<?> all = attribute.getAll();

    try {
        while (all.hasMore()) {
            Object raw = all.next();
            if (!(raw instanceof String value)) {
                throw new IllegalStateException(
                        "Unexpected value type for " + attributeName);
            }
            values.add(value);
        }
    } finally {
        all.close();
    }

    return List.copyOf(values);
}
~~~

`groupDn` trong ví dụ là DN tương đối với base của `ContextSource`. `lookup` đọc một entry; mapper lấy toàn bộ giá trị `member` và đóng `NamingEnumeration`.

**Giới hạn:** cách này tải toàn bộ các giá trị được server trả về vào bộ nhớ. Nếu group có hàng chục nghìn thành viên, đừng dùng nó mặc định chỉ để kiểm tra một người có thuộc nhóm hay không.

Nếu cần nhiều attribute đa trị, phải xác định rõ cardinality và kiểu Java. Không ép mọi giá trị thành `String` nếu attribute có binary syntax hoặc kiểu đặc thù.

## 6. Chỉ đọc attribute cần thiết

Đọc group bằng mapper không có nghĩa luôn phải tải membership. Nếu chỉ cần tên nhóm, không yêu cầu `member`:

~~~java
String groupName = ldapTemplate.lookup(
        groupDn,
        (AttributesMapper<String>) attrs -> {
            javax.naming.directory.Attribute cn = attrs.get("cn");
            if (cn == null || cn.size() != 1) {
                throw new IllegalStateException("Invalid group cn");
            }
            return (String) cn.get();
        });
~~~

Với search, chỉ yêu cầu các attribute cần dùng:

~~~java
LdapQuery query = query()
        .base("ou=groups")
        .searchScope(SearchScope.ONELEVEL)
        .attributes("cn", "description")
        .where("objectClass").is("groupOfNames");
~~~

Projection giúp tránh truyền hàng nghìn member values khi màn hình chỉ hiển thị tên và mô tả nhóm. Cần kiểm tra overload và behavior cụ thể của Spring LDAP version; một số thao tác lookup/mapper có thể mặc định tải attributes khác nhau.

Nguyên tắc: **đừng đọc membership chỉ vì đang đọc group metadata**. Tách DTO metadata và DTO membership nếu hai use case có nhu cầu dữ liệu khác nhau.

## 7. Thêm một thành viên mà không thay toàn bộ attribute

Nếu chỉ thêm một user vào group, dùng `DirContext.ADD_ATTRIBUTE` với đúng giá trị cần thêm:

~~~java
import javax.naming.Name;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;

public void addMember(
        LdapTemplate ldapTemplate,
        Name groupDn,
        String fullMemberDn) {

    ModificationItem addition = new ModificationItem(
            DirContext.ADD_ATTRIBUTE,
            new BasicAttribute("member", fullMemberDn));

    ldapTemplate.modifyAttributes(
            groupDn,
            new ModificationItem[] { addition });
}
~~~

Đây là một ModifyRequest trên **một group entry**. Không cần đọc 10.000 member, thêm một phần tử trong Java rồi gửi toàn bộ 10.001 giá trị trở lại.

Lợi ích:

- Giảm payload từ client lên server.
- Giảm nguy cơ ghi đè các member được client khác thêm trong lúc đọc–sửa–ghi.
- Tránh yêu cầu client có bản snapshot membership đầy đủ.
- Làm rõ ý định thay đổi một giá trị.

Nếu giá trị đã tồn tại, server thường trả `attributeOrValueExists (20)`. Ứng dụng cần định nghĩa “đã là thành viên” là thành công idempotent hay lỗi nghiệp vụ; không bắt mọi exception rồi bỏ qua.

### Xây full DN an toàn

Nếu thành viên là user entry, giá trị `member` phải là DN đầy đủ theo schema. Dùng `LdapNameBuilder` để tạo DN từ các thành phần đã kiểm soát, không nối chuỗi tùy ý:

~~~java
Name personDn = LdapNameBuilder.newInstance("ou=people")
        .add("uid", uid)
        .build();

String fullMemberDn = LdapNameBuilder
        .newInstance(baseLdapName)
        .add(personDn)
        .build()
        .toString();
~~~

Ví dụ giả định `baseLdapName` được lấy từ đúng `ContextSource`. Phân biệt DN tương đối truyền cho `LdapTemplate` với DN đầy đủ lưu trong `member`.

## 8. Xóa đúng một thành viên

Dùng `DirContext.REMOVE_ATTRIBUTE` với attribute chứa **một giá trị cụ thể**:

~~~java
ModificationItem removal = new ModificationItem(
        DirContext.REMOVE_ATTRIBUTE,
        new BasicAttribute("member", fullMemberDn));

ldapTemplate.modifyAttributes(
        groupDn,
        new ModificationItem[] { removal });
~~~

Không dùng `REMOVE_ATTRIBUTE` với attribute rỗng nếu mục tiêu chỉ là xóa một user; dạng đó có thể yêu cầu xóa toàn bộ attribute `member`.

Với `groupOfNames`, xóa member cuối cùng làm entry không còn đáp ứng MUST attribute. Directory có thể từ chối Modify với lỗi schema/objectClass. Trước thao tác cần quyết định nghiệp vụ:

- Không cho phép nhóm rỗng và yêu cầu luôn có ít nhất một member.
- Khi nhóm không còn member, xóa group entry bằng quy trình riêng.
- Dùng mô hình nhóm khác có semantics cho phép rỗng, nếu phù hợp và được schema/ứng dụng hỗ trợ.

Không tự đổi objectClass hoặc bỏ MUST attribute để “làm cho thao tác xóa chạy được”.

## 9. Thêm nhiều thành viên cho cùng một group

Khi cần thêm một batch member vào **một group**, có thể gom nhiều giá trị vào một `BasicAttribute` và gửi một ModifyRequest:

~~~java
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;

BasicAttribute newMembers = new BasicAttribute("member");

for (String memberDn : memberDns) {
    newMembers.add(memberDn);
}

ModificationItem addition = new ModificationItem(
        DirContext.ADD_ATTRIBUTE,
        newMembers);

ldapTemplate.modifyAttributes(
        groupDn, new ModificationItem[] { addition });
~~~

Nếu server chấp nhận kích thước request và toàn bộ giá trị hợp lệ, đây là **một ModifyRequest cho một entry** với nhiều giá trị được thêm. Cần xử lý duplicate: một giá trị đã tồn tại có thể khiến thao tác thất bại theo semantics LDAP Modify. Trước khi gửi batch, có thể kiểm tra/đối soát, nhưng không nên tải toàn bộ group chỉ để thêm một vài member.

Với một nhóm cực lớn, request chứa hàng nghìn DN có thể vượt giới hạn message, attribute values hoặc server policy. Chia batch theo giới hạn đã đo. Khi chia thành nhiều ModifyRequests, từng batch có thể thành công một phần; cần checkpoint và retry idempotent.

**Gom nhiều giá trị cho một entry khác với gom nhiều group entry vào một request.** LDAP ModifyRequest chỉ chỉ định một DN đích.

## 10. Vì sao không nên read–modify–replace cả danh sách?

Cách làm dễ viết nhưng nguy hiểm:

~~~java
List<String> members = readGroupMembers(ldapTemplate, groupDn);
members.add(newMemberDn);

// Gửi REPLACE_ATTRIBUTE với toàn bộ danh sách mới.
~~~

Giả sử:

1. Client A đọc danh sách member hiện tại.
2. Client B thêm một member khác.
3. Client A thêm member của mình vào snapshot cũ.
4. Client A dùng `REPLACE_ATTRIBUTE` ghi lại toàn bộ danh sách.

Member mà B vừa thêm có thể bị mất vì A ghi đè snapshot cũ.

Đối với thao tác đơn giản, hãy dùng **ADD_ATTRIBUTE/REMOVE_ATTRIBUTE cho giá trị cụ thể**. Nếu nghiệp vụ cần thay toàn bộ danh sách, phải có cơ chế concurrency/version hoặc khóa điều phối phù hợp, xác định rõ source of truth và kiểm thử xung đột.

Một ModifyRequest trên một entry được xử lý như một thao tác nguyên tử theo LDAP protocol; điều này không biến chuỗi đọc–sửa–replace thành compare-and-swap. Có thể dùng LDAP Assertion Control (RFC 4528) khi directory và client hỗ trợ để kiểm tra điều kiện ngay tại server trong thao tác ghi.

## 11. Tìm nhóm chứa một user mà không tải toàn bộ member list

Nếu câu hỏi là “user Lan thuộc những group nào?”, thường không cần đọc tất cả nhóm rồi duyệt danh sách member ở client. Có thể tìm ngược bằng equality filter trên `member`:

~~~java
import java.util.List;

import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.SearchScope;

import static org.springframework.ldap.query.LdapQueryBuilder.query;

public List<String> findGroupNamesForMember(
        LdapTemplate ldapTemplate,
        String fullMemberDn) {

    LdapQuery ldapQuery = query()
            .base("ou=groups")
            .searchScope(SearchScope.SUBTREE)
            .attributes("cn")
            .where("objectClass").is("groupOfNames")
            .and("member").is(fullMemberDn);

    return ldapTemplate.search(
            ldapQuery,
            (AttributesMapper<String>) attrs ->
                    (String) attrs.get("cn").get());
}
~~~

Filter tương đương:

~~~text
(&(objectClass=groupOfNames)
  (member=uid=lan,ou=people,dc=example,dc=org))
~~~

`LdapQueryBuilder`/`EqualsFilter` phải xử lý escaping của filter assertion; đừng nối trực tiếp DN từ input vào chuỗi filter. DN value có cú pháp DN riêng, còn vị trí của nó trong filter phải tuân theo RFC 4515. Dùng API filter để encode đúng cả ngữ cảnh.

Truy vấn ngược có thể giảm payload khi một group có hàng nghìn member nhưng một user chỉ thuộc một vài group. Tuy nhiên hiệu năng phụ thuộc index equality trên attribute `member`, search base và directory server. Nếu attribute không được index, server có thể phải quét nhiều entry.

## 12. Index và search scope cho membership

Các truy vấn thường gặp:

- Tìm group theo tên: `(cn=developers)`.
- Tìm group có member cụ thể: `(member=<full DN>)`.
- Tìm group theo loại: `(&(objectClass=groupOfNames)(member=<DN>))`.
- Tìm user theo UID: `(&(objectClass=inetOrgPerson)(uid=lan))`.

Để tối ưu:

1. Giới hạn base vào `ou=groups` thay vì search toàn DIT.
2. Chọn `ONELEVEL` nếu group chỉ nằm trực tiếp dưới OU; dùng `SUBTREE` khi cần nhóm con.
3. Chỉ yêu cầu attribute cần trả về, ví dụ `cn`, không lấy `member` khi không cần.
4. Kiểm tra equality index trên `member`, `uniqueMember`, `cn` hoặc `uid` theo sản phẩm LDAP.
5. Đo query với group nhỏ và group lớn; không suy hiệu năng từ dữ liệu test vài thành viên.
6. Xem query plan/index statistics và access log theo khả năng server.

Cấu hình index là **server-specific**, không được tạo bởi annotation Spring Data LDAP. Thay đổi index có thể cần rebuild hoặc thời gian cập nhật; phải thực hiện theo runbook của directory.

Không nên dùng substring filter trên DN thành viên như `(member=*uid=lan*)` để tìm quan hệ membership. Nó vừa kém chính xác, vừa có thể làm mất khả năng dùng equality index, và có nguy cơ khớp sai DN có thành phần tương tự.

## 13. Search paging khác với ranged retrieval của attribute

Đây là điểm rất quan trọng khi xử lý group cực lớn.

**LDAP Paged Results Control (RFC 2696)** phân trang **các entry của SearchResult**. Ví dụ tìm 10.000 group entry có thể lấy 200 entry mỗi trang.

Nó **không tự phân trang các giá trị trong một attribute**. Nếu một group entry có 30.000 giá trị `member`, một search trả về entry đó không tự biến `member` thành 150 trang, mỗi trang 200 giá trị.

~~~text
Paged Results:
  Search base + filter
      -> Page 1: group entry A, B, C...
      -> Page 2: group entry ...
  (phân trang entry)

Ranged attribute retrieval:
  Read một group entry
      -> member range 0-1499
      -> member range 1500-2999
      -> ...
  (phân đoạn giá trị của một attribute)
~~~

LDAP protocol chuẩn không định nghĩa một cơ chế phân trang giá trị attribute phổ quát tương tự RFC 2696. Một số directory có extension/attribute option riêng.

### Active Directory ranged retrieval

Microsoft Active Directory hỗ trợ cơ chế **ranged retrieval** cho attribute nhiều giá trị, thường gặp với `member`. Client yêu cầu một range trong attribute description, ví dụ:

~~~text
member;range=0-1499
~~~

Server có thể trả về attribute description dạng `member;range=0-1499`; nếu đã tới cuối, tên có thể có dạng `member;range=1500-*`. Client tiếp tục từ giá trị kế tiếp dựa trên range server trả về.

Ví dụ truy vấn minh họa với `ldapsearch`:

~~~bash
ldapsearch -LLL -H ldaps://ad.example.org:636 \
  -D "CN=svc-reader,OU=Services,DC=example,DC=org" -W \
  -b "CN=developers,OU=Groups,DC=example,DC=org" \
  -s base "(objectClass=*)" "member;range=0-1499"
~~~

Đây là **tính năng riêng của Active Directory**, không phải cú pháp LDAP tổng quát áp dụng cho OpenLDAP hoặc mọi directory. Giới hạn range cần theo tài liệu/cấu hình của AD, không hardcode 1.500 cho mọi môi trường.

Trong Java/JNDI, tên attribute trả về có thể là `member;range=...`, không nhất thiết chính xác là `member`. Code đọc phải nhận diện attribute description và lặp range đúng theo response thực tế. Không giả định `attrs.get("member")` luôn trả tất cả giá trị nếu server áp dụng ranged retrieval.

### Cách chọn chiến lược

| Tình huống | Cơ chế |
|---|---|
| Nhiều group entry, mỗi group có ít member | Search + Paged Results Control |
| Một group có rất nhiều member trên Active Directory | Ranged retrieval theo attribute |
| Một group có rất nhiều member trên directory không có range feature | Kiểm tra giới hạn server; cân nhắc mô hình dữ liệu/chia nhóm |
| Chỉ cần biết user có thuộc group không | Equality search trên `member`, không tải cả danh sách |
| Chỉ cần group metadata | Projection bỏ `member` |
| Cần duyệt toàn bộ member để export | Range API nếu có, streaming/processing theo lô, giới hạn memory |

## 14. Nested groups và tránh N+1

Một group có thể chứa DN của một group khác nếu schema và directory policy cho phép nested membership. Ví dụ:

~~~ldif
dn: cn=engineering,ou=groups,dc=example,dc=org
objectClass: top
objectClass: groupOfNames
cn: engineering
member: uid=lan,ou=people,dc=example,dc=org
member: cn=backend,ou=groups,dc=example,dc=org
~~~

Khi mở rộng toàn bộ thành viên, ứng dụng phải nhận biết giá trị `member` có thể là user hoặc group. Cách ngây thơ:

1. Đọc group A.
2. Với mỗi member, lookup DN.
3. Nếu là group, đọc tiếp group con.

Có thể tạo N+1 hoặc hàng nghìn LDAP reads. Cần thiết kế rõ:

- Phân loại member theo objectClass khi tra cứu.
- Gom nhiều DN cần xác minh vào batch search theo chunk nếu directory cho phép.
- Giới hạn độ sâu mở rộng và số entry tối đa.
- Dùng tập `visited` theo DN đã chuẩn hóa để tránh vòng lặp.
- Xác định semantics nested group của ứng dụng có trùng với directory/server hay không.
- Xử lý group tham chiếu không tồn tại hoặc caller không có quyền đọc.

Ví dụ thuật toán BFS:

~~~java
Deque<Name> pendingGroups = new ArrayDeque<>();
Set<LdapName> visitedGroups = new HashSet<>();
Set<LdapName> users = new HashSet<>();

pendingGroups.add(rootGroupDn);

while (!pendingGroups.isEmpty()) {
    Name groupDn = pendingGroups.removeFirst();
    LdapName normalized = new LdapName(groupDn.toString());

    if (!visitedGroups.add(normalized)) {
        continue; // đã thăm, tránh chu trình
    }

    List<String> memberDns = readGroupMembers(ldapTemplate, groupDn);

    for (String memberValue : memberDns) {
        Name memberDn = new LdapName(memberValue);

        if (isGroupEntry(ldapTemplate, memberDn)) {
            pendingGroups.addLast(memberDn);
        } else {
            users.add(new LdapName(memberDn.toString()));
        }
    }
}
~~~

Đây là **pseudocode định hướng**, vì `isGroupEntry(...)` nếu lookup từng DN sẽ lại tạo N+1. Trong triển khai thực tế nên có phương thức batch phân loại member theo chunk, giới hạn số group/user đã thăm, depth và deadline. `LdapName` giúp so sánh DN theo cấu trúc tốt hơn việc dùng chuỗi raw; cần áp dụng quy tắc normalization phù hợp schema/server.

Một số directory có matching rule hoặc API riêng để truy vấn membership lồng nhau. Ví dụ Active Directory có matching rule in chain với OID riêng; không dùng cú pháp đó như tính năng LDAP portable. Hãy xác minh sản phẩm và quyền truy vấn.

## 15. Dynamic groups và mô hình membership thay thế

Với nhóm có thành viên biến động rất lớn, lưu toàn bộ DN trong một attribute có thể không phải mô hình tối ưu.

| Mô hình | Cách xác định thành viên | Ưu điểm | Đánh đổi |
|---|---|---|---|
| Static group (`member`) | Danh sách DN được lưu trực tiếp | Membership tường minh, dễ cập nhật từng giá trị | Attribute lớn, phải đồng bộ khi user đổi DN |
| POSIX group (`memberUid`) | Danh sách UID | Tích hợp hệ sinh thái POSIX | Không chứa DN; cần uniqueness và resolver |
| Dynamic group | Filter/URL hoặc cơ chế server-specific | Không cần lưu mọi thành viên tĩnh | Mỗi lần đánh giá có thể tốn search; phụ thuộc server |
| Nhóm theo OU/attribute | Tính membership từ thuộc tính user | Có thể giảm danh sách membership lặp | Phải định nghĩa semantics, query/index và quyền rõ |
| Nhóm phân cấp | Group chứa group | Tái sử dụng nhóm con | Phải xử lý cycle, depth và semantics authorization |

Dynamic group không có một implementation đồng nhất trong mọi LDAP server. Có server hỗ trợ object class/control riêng; có hệ thống để ứng dụng tự tính membership. Không tự tạo attribute `memberURL` rồi giả định mọi server hiểu nó.

Trước khi thay static group bằng dynamic group, đánh giá cách Spring Security LDAP, hệ thống Unix/POSIX, ứng dụng ngoài và audit xác định quyền. Tối ưu lưu trữ không được làm thay đổi semantics bảo mật ngoài ý muốn.

## 16. Cache membership: giảm tải nhưng phải tính tới thu hồi quyền

Một group lớn có thể được đọc lặp lại khi nhiều user đăng nhập. Cache kết quả membership giúp giảm LDAP requests và payload:

~~~text
User login
   |
   +--> Cache hit: dùng membership còn hiệu lực
   |
   +--> Cache miss: query LDAP -> cache kết quả
~~~

Có thể cache theo:

- DN/UID của user → danh sách group.
- DN của group → danh sách member (chỉ khi use case thật sự cần).
- Business identity ổn định → membership/authorities.

Không nên cache toàn bộ member list của một group cực lớn nếu chỉ cần trả lời “user này thuộc group nào?”. Hãy chọn hướng cache theo truy vấn thực tế.

**Rủi ro bảo mật:** cache làm dữ liệu membership cũ tồn tại sau khi thêm/xóa member. Khi cấp quyền, người dùng có thể phải chờ cache refresh. Khi thu hồi quyền, cache cũ có thể giữ quyền lâu hơn mong muốn.

Cần quyết định:

1. TTL theo mức độ nhạy cảm của quyền.
2. Invalidation theo sự kiện cập nhật group nếu có event đáng tin cậy.
3. Hành vi khi LDAP/cache unavailable.
4. Giới hạn cache size và chống cache stampede.
5. Cách refresh authorities của session/JWT đã phát hành.
6. Cách audit thời điểm membership thay đổi và quyền có hiệu lực.

Không coi TTL cache là bảo đảm nhất quán nếu không có cơ chế invalidation. Với quyền nhạy cảm, có thể phải kiểm tra nguồn authoritative hoặc thu hồi token/session theo chính sách.

## 17. Đồng thời và tính toàn vẹn khi nhiều người sửa cùng group

Giả sử hai admin cùng thêm thành viên vào group lớn.

**Cách read–modify–replace có race:**

~~~text
A đọc member list: [lan, binh]
B đọc member list: [lan, binh]
A thêm minh rồi REPLACE: [lan, binh, minh]
B thêm hoa rồi REPLACE: [lan, binh, hoa]
Kết quả: member minh có thể bị mất
~~~

Dùng ADD/REMOVE cho giá trị cụ thể giúp tránh ghi đè toàn bộ snapshot:

~~~java
ModificationItem addMinh = new ModificationItem(
        DirContext.ADD_ATTRIBUTE,
        new BasicAttribute("member", minhDn));

ldapTemplate.modifyAttributes(
        groupDn, new ModificationItem[] { addMinh });
~~~

Một ModifyRequest tác động nguyên tử lên entry theo giao thức. Nếu hai request thêm hai giá trị khác nhau, directory xử lý từng thao tác theo semantics server; client không cần thay toàn bộ tập member.

Tuy nhiên:

- Hai client thêm cùng DN có thể khiến một request nhận `attributeOrValueExists (20)`.
- Xóa member cuối cùng khỏi `groupOfNames` có thể vi phạm MUST.
- Một request thêm nhiều giá trị có thể thất bại do một giá trị trùng hoặc không hợp lệ; không giả định thành công một phần.
- Nếu cần điều kiện “chỉ thêm khi group version vẫn là X”, cần cơ chế assertion/locking do server hỗ trợ hoặc coordinator.
- Không có transaction chuẩn bao trùm việc cập nhật group, user entry và các hệ thống ngoài.

## 18. Batch update, giới hạn và xử lý partial success

Với một group có nhiều member cần thêm, có thể gom theo batch:

~~~java
for (List<String> chunk : chunks(memberDns, 100)) {
    BasicAttribute attribute = new BasicAttribute("member");

    for (String dn : chunk) {
        attribute.add(dn);
    }

    ModificationItem addition = new ModificationItem(
            DirContext.ADD_ATTRIBUTE, attribute);

    ldapTemplate.modifyAttributes(
            groupDn, new ModificationItem[] { addition });
}
~~~

Ví dụ chunk size 100 chỉ là giá trị thử nghiệm. Mỗi chunk là một ModifyRequest trên cùng group. Nếu chunk thứ 3 lỗi, các chunk trước có thể đã thành công; phải ghi checkpoint và đối soát trạng thái trước khi retry.

Với batch qua nhiều group, request count tăng theo số group/chunk. Không gộp tất cả member của mọi group vào một BasicAttribute vì mỗi ModifyRequest chỉ có một DN đích.

Giới hạn cần đo:

- Maximum message/request size.
- Maximum attribute values hoặc giới hạn do server áp dụng.
- LDAP operation timeout.
- Connection pool capacity.
- Response size và memory.
- Replication backlog khi membership thay đổi nhiều.
- Tải trên một group entry khi nhiều writer cùng sửa.

Không có một con số batch size chung cho mọi LDAP server. Chọn từ thử nghiệm có kiểm soát, bắt đầu nhỏ và tăng dần.

## 19. Đọc một phần, kiểm tra membership và giảm payload

Nếu chỉ cần kiểm tra một DN có nằm trong group hay không, có hai hướng:

**Hướng A — đọc group rồi duyệt:** đơn giản nhưng tải toàn bộ attribute `member`.

**Hướng B — search group bằng filter `member=<DN>`:** server trả các group phù hợp; nếu chỉ cần tên group, projection chỉ lấy `cn`.

Ví dụ Hướng B thường tốt hơn khi group rất lớn và user chỉ thuộc một số ít group, đặc biệt nếu server có equality index trên `member`.

Không nên gửi `attributes("member")` cho mọi truy vấn group metadata. Nếu API có màn hình group detail cần hiển thị 10.000 member, cân nhắc API riêng có phân trang/range retrieval và giới hạn rõ; không trả cả danh sách trong một HTTP response mặc định.

LDAP không cung cấp generic attribute-value paging, vì vậy với directory không có extension range retrieval, có thể cần thiết kế lại use case hoặc lưu membership thành nhiều entry quan hệ riêng thay vì một attribute khổng lồ. Đây là thay đổi mô hình dữ liệu, cần migration và đánh giá schema/authorization.

## 20. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Đọc group chậm | Tải toàn bộ `member` values | Chỉ đọc `cn`/metadata hoặc tìm ngược bằng filter |
| Heap tăng khi map group | Tạo `List<String>` chứa hàng chục nghìn DN | Streaming/processing theo range hoặc giới hạn use case |
| Thêm member làm lỗi | DN sai, ACL, duplicate hoặc schema | Kiểm tra DN, result code, quyền và objectClass |
| Xóa member cuối bị từ chối | `groupOfNames.member` là MUST | Xóa group hoặc dùng mô hình phù hợp cho nhóm rỗng |
| Membership filter chậm | Attribute không được index hoặc search base rộng | Index equality và giới hạn base/scope |
| Search paging không lấy hết member | Paging phân trang entry, không phải attribute values | Dùng ranged retrieval nếu server hỗ trợ |
| AD trả `member;range=...` | Server đang áp dụng ranged retrieval | Đọc range tiếp theo theo response |
| Code chỉ đọc `attrs.get("member")` không thấy | Attribute description có option range | Xử lý tên attribute trả về; kiểm tra server-specific |
| Nested group lookup quá nhiều | N+1 và mở rộng đệ quy không giới hạn | Batch classify, visited set, depth/deadline |
| Nested group lặp vô hạn | Có chu trình giữa các group | Cycle detection theo DN |
| Thu hồi quyền chậm | LDAP replication hoặc authorization cache | Định nghĩa consistency/TTL/invalidation |
| Retry Add báo duplicate | Lần trước có thể đã thành công | Đối soát trạng thái trước retry |
| REPLACE làm mất member khác | Read–modify–replace race | ADD/REMOVE đúng value hoặc conditional update |
| Batch thất bại giữa chừng | Một chunk/member lỗi | Ledger per-group/per-chunk, resume |
| Dynamic group không chạy | Directory không hỗ trợ object class/control đã dùng | Kiểm tra vendor capability và schema |

## 21. Đo hiệu năng với nhóm nhỏ và nhóm lớn

Tạo dataset test có các quy mô khác nhau, ví dụ 10, 100, 1.000 và 10.000 member nếu server test cho phép. Đo riêng:

| Workload | Chỉ số cần đo |
|---|---|
| Lookup group không lấy member | Latency, response bytes |
| Lookup group lấy toàn bộ member | Latency, bytes, heap, số giá trị |
| Add một member | Modify latency, result code |
| Add 100 member một lần | Request size, latency, server limits |
| Add 100 member theo chunk | Số requests, tổng thời gian, partial failure |
| Search groups by member DN | Search latency, index usage, kết quả |
| Mở rộng nested group | Số LDAP requests, số group/user visited, depth |
| Cache hit/miss | Latency, hit ratio, stale authorization |
| Ranged retrieval trên AD | Số range requests, tổng bytes, completion |

Metric ứng dụng có thể tự định nghĩa:

- `ldap_group_lookup_duration`
- `ldap_group_member_values_returned`
- `ldap_group_member_response_bytes`
- `ldap_membership_modify_total`
- `ldap_nested_group_nodes_visited`
- `ldap_membership_cache_hit_ratio`
- `ldap_membership_refresh_failures`

Đây là tên metric gợi ý, không phải tất cả đều có sẵn trong Spring LDAP. Không dùng DN, email hoặc UID cá nhân làm metric label cardinality cao.

Đo cùng môi trường, cùng dataset, cùng bind identity và cùng cache policy. Tách cold-cache và warm-cache; nếu không, kết quả so sánh dễ sai.

## 22. Kiểm thử tích hợp và bảo mật

### Fixture test

Tạo OU và group trên directory test:

~~~ldif
dn: ou=groups,dc=example,dc=org
objectClass: top
objectClass: organizationalUnit
ou: groups

dn: cn=developers,ou=groups,dc=example,dc=org
objectClass: top
objectClass: groupOfNames
cn: developers
member: uid=lan,ou=people,dc=example,dc=org
~~~

Fixture phải có parent DN và user entry tồn tại theo schema test. GroupOfNames cần ít nhất một member hợp lệ.

### Ma trận test

| Kịch bản | Kết quả cần xác nhận |
|---|---|
| Đọc group metadata | Không tải member nếu projection bỏ member |
| Đọc member list nhỏ | Đọc đủ giá trị, không mất giá trị |
| Add một member mới | Chỉ thêm giá trị được yêu cầu |
| Add member trùng | Xử lý `attributeOrValueExists` theo hợp đồng |
| Remove một member | Các giá trị khác được giữ |
| Remove member cuối | Schema MUST được tôn trọng |
| Add batch | Số ModifyRequests và payload đo được |
| Batch lỗi giữa chừng | Checkpoint/resume không nhân đôi dữ liệu |
| Tìm group theo member DN | Filter trả đúng group, escaping an toàn |
| Group cực lớn | Không tải vô hạn vào heap |
| AD ranged retrieval | Lặp đúng range đến khi server báo `*` |
| Nested group cycle | Kết thúc nhờ visited set/depth limit |
| Cache sau thu hồi quyền | Hành vi theo TTL/invalidation đã định nghĩa |
| ACL reader/writer | Reader không có quyền ghi; writer có quyền cần thiết |
| DN có ký tự đặc biệt | Builder/filter encode đúng ngữ cảnh |

### Các nguyên tắc bảo mật

- Không nhận raw DN hoặc filter từ client để thực hiện membership modification.
- Validate business identifier rồi dựng DN bằng `LdapNameBuilder`.
- Dùng `EqualsFilter`/`LdapQueryBuilder` để encode filter assertion.
- DN escaping và filter escaping là hai ngữ cảnh khác nhau.
- Tài khoản đọc group chỉ cần quyền đọc; tài khoản thay đổi membership chỉ có quyền trên OU/group cần thiết.
- Không log toàn bộ member list hoặc dữ liệu cá nhân chỉ để đo hiệu năng.
- Dùng LDAPS/StartTLS và xác minh chứng chỉ.
- Kiểm tra quyền thu hồi membership và cache/session/token theo yêu cầu bảo mật.

## 23. Bài tập thực hành

**Bối cảnh:** directory nhân sự có group `developers` với 8.000 member. API cần hiển thị tên nhóm, kiểm tra một user có thuộc nhóm hay không, thêm/xóa thành viên và cung cấp chức năng export danh sách.

Thực hiện trên directory test độc lập:

1. Tạo `groupOfNames` với nhiều giá trị `member`, đồng thời tạo các user entry tương ứng.
2. Viết mapper đọc tất cả `member` bằng `Attribute.getAll()` và đo thời gian/heap.
3. Viết query chỉ lấy `cn`; xác nhận không tải `member` khi chỉ hiển thị metadata.
4. Viết equality filter tìm group theo DN user; so sánh với cách đọc toàn bộ member rồi duyệt.
5. Bật/kiểm tra equality index cho `member` theo hướng dẫn server; đo trước/sau.
6. Thêm một member bằng `ADD_ATTRIBUTE`; xác nhận các member cũ còn nguyên.
7. Xóa một member bằng `REMOVE_ATTRIBUTE`; xác nhận các giá trị khác không mất.
8. Thử xóa member cuối và giải thích ràng buộc MUST của `groupOfNames`.
9. Thêm 500 member bằng một ModifyRequest; ghi nhận request size, latency và giới hạn server.
10. Chia cùng batch thành chunk; mô phỏng lỗi giữa chừng và triển khai checkpoint/resume.
11. Tạo nested group có vòng tham chiếu; kiểm tra thuật toán BFS dừng đúng.
12. Trên Active Directory test, dùng `member;range=...` để lấy toàn bộ member theo response range; giải thích vì sao RFC 2696 không thay thế cơ chế này.
13. Thử cache membership, thu hồi một member và đo thời gian quyền được cập nhật.
14. Viết báo cáo so sánh payload, latency, request count, heap, cache hit ratio và tính đúng đắn.

**Tiêu chí hoàn thành:** người học biết giảm payload khi không cần member list, cập nhật một giá trị mà không thay toàn bộ attribute, tìm ngược membership bằng filter, phân biệt paging entry và ranged attribute, xử lý nested group/cache/concurrency, đồng thời giữ nguyên schema và ACL.

## 24. Tổng kết và tài liệu tham khảo

Nhóm lớn thường là một entry với attribute đa trị lớn, vì vậy không nên nhầm số lượng **entry** với số lượng **attribute values**. `groupOfNames.member` chứa DN; `groupOfUniqueNames.uniqueMember` và `posixGroup.memberUid` có semantics khác.

Các hướng tối ưu quan trọng:

- Không đọc `member` nếu chỉ cần metadata group.
- Nếu chỉ cần tìm nhóm chứa một user, dùng equality search trên `member` và index phù hợp.
- Thêm/xóa đúng giá trị bằng `ADD_ATTRIBUTE`/`REMOVE_ATTRIBUTE`; tránh read–modify–replace toàn bộ danh sách.
- Gom nhiều giá trị cho cùng group trong một ModifyRequest khi payload/server limits cho phép.
- Chia batch có checkpoint khi nhóm quá lớn; xử lý partial success và duplicate.
- Dùng visited set/depth limit cho nested group.
- Thiết kế cache membership theo yêu cầu cấp/thu hồi quyền.
- Phân biệt paged results của Search với ranged retrieval riêng của Active Directory.
- Đo payload, latency, heap, request count và tải directory trong môi trường tương đương production.

Tài liệu tham khảo:

- [RFC 4511 — LDAP Protocol](https://www.rfc-editor.org/rfc/rfc4511): Search, Modify, Add, Delete và request/response.
- [RFC 4512 — LDAP Directory Information Models](https://www.rfc-editor.org/rfc/rfc4512): attribute, objectClass, DIT và schema.
- [RFC 4519 — LDAP Schema for User Applications](https://www.rfc-editor.org/rfc/rfc4519): groupOfNames, groupOfUniqueNames, member, uniqueMember.
- [RFC 2307 — An Approach for Using LDAP as a Network Information Service](https://www.rfc-editor.org/rfc/rfc2307): posixGroup và memberUid.
- [RFC 2696 — LDAP Simple Paged Results](https://www.rfc-editor.org/rfc/rfc2696): phân trang SearchResult entries.
- [Microsoft Learn — Range Retrieval Search](https://learn.microsoft.com/en-us/windows/win32/adsi/range-retrieval-search): ranged retrieval cho attribute đa trị trong Active Directory.
- [Spring LDAP Reference](https://docs.spring.io/spring-ldap/reference/): LdapTemplate, query, ModificationItem và mapping.
- [Spring Data LDAP Reference](https://docs.spring.io/spring-data/ldap/reference/): ODM, @Entry, LdapRepository.
