# RDN nhiều giá trị và ảnh hưởng đến phân tích định danh

> **Chương:** DN và định danh  
> **Module:** SPRING_DATA_LDAP — truy cập directory LDAP qua Spring Data LDAP, ánh xạ entry phân cấp sang Java, hiểu DN, objectClass, schema và truy vấn bằng repository/LdapTemplate.

Một **Relative Distinguished Name (RDN)** không bắt buộc chỉ chứa một cặp thuộc tính–giá trị. RDN có thể gồm nhiều **Attribute Value Assertions (AVA)**, nối với nhau bằng dấu cộng `+`. Ví dụ:

~~~text
cn=Tran Thi Lan+uid=lan,ou=people,dc=example,dc=org
~~~

Trong DN này, `cn=Tran Thi Lan+uid=lan` là **một RDN duy nhất**, gồm hai AVA: `cn=Tran Thi Lan` và `uid=lan`. Các RDN `ou=people`, `dc=example` và `dc=org` là các thành phần cha tiếp theo.

Multi-valued RDN khác với một attribute có nhiều giá trị:

~~~ldif
telephoneNumber: +84 28 1234 5678
telephoneNumber: +84 90 111 2222
~~~

Ở đây entry có một attribute `telephoneNumber` với hai giá trị. Còn trong RDN nhiều AVA, nhiều cặp attribute/value cùng tham gia tạo **một thành phần tên**. Sự khác biệt ảnh hưởng đến cách parse DN, tìm định danh, tạo entry, rename và ánh xạ sang Java.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt RDN một AVA, RDN nhiều AVA, DN nhiều RDN và attribute đa trị.
2. Đọc DN có dạng `cn=Lan+uid=lan,ou=people,dc=example,dc=org`.
3. Hiểu vai trò của dấu cộng `+`, dấu phẩy `,` và escaping theo RFC 4514.
4. Dùng `javax.naming.ldap.LdapName` và `Rdn` để parse DN.
5. Trích xuất tất cả AVA từ một RDN bằng `Rdn.toAttributes()`.
6. Xây DN nhiều AVA bằng API cấu trúc và kiểm tra schema/naming attribute.
7. Hiểu ảnh hưởng tới identity, tìm kiếm, rename, repository và xác thực LDAP.
8. Viết unit test và integration test cho multi-valued RDN, AVA order và ký tự đặc biệt.

## 2. Cấu trúc DN, RDN và AVA

Một DN là chuỗi các RDN từ entry cụ thể nhất đi dần về phía gốc:

~~~text
cn=Tran Thi Lan+uid=lan,ou=people,dc=example,dc=org
|---------------------| |---------| |---------| |-----|
       RDN 1              RDN 2       RDN 3      RDN 4
         \________________ DN của entry ______________/
~~~

- **DN (Distinguished Name):** tên phân biệt của entry trong Directory Information Tree (DIT).
- **RDN (Relative Distinguished Name):** thành phần tên của entry tương đối với entry cha.
- **AVA (Attribute Value Assertion):** cặp attribute type và attribute value tham gia cấu tạo RDN.
- **Multi-valued RDN:** một RDN có nhiều AVA, biểu diễn bằng dấu `+`.

~~~text
cn=Lan+uid=lan,ou=people,dc=example,dc=org
   ^^^^^^ ^^^^^^
   AVA 1  AVA 2
   \___________/
      Một RDN
~~~

| Phần | Loại | Ý nghĩa |
|---|---|---|
| `cn=Lan` | AVA thứ nhất | Common name tham gia đặt tên |
| `uid=lan` | AVA thứ hai | UID cũng tham gia đặt tên |
| `cn=Lan+uid=lan` | Một RDN | Tên entry tương đối với OU cha |
| `ou=people` | RDN cha | Entry nằm trong OU people |
| `dc=example`, `dc=org` | RDN cha | Thành phần domain |
| Toàn bộ chuỗi | DN | Tên của entry trong DIT |

**Dấu cộng và dấu phẩy không thể thay thế nhau:**

~~~text
cn=Lan+uid=lan,ou=people,dc=example,dc=org
        ^ dấu +: hai AVA trong cùng một RDN
                      ^ dấu ,: bắt đầu RDN cha tiếp theo
~~~

So sánh:

| Biểu diễn | Cấu trúc |
|---|---|
| `cn=Lan+uid=lan,ou=people,dc=example,dc=org` | RDN đầu có hai AVA; tiếp theo là OU và domain |
| `cn=Lan,uid=lan,ou=people,dc=example,dc=org` | RDN đầu là cn; RDN kế tiếp là uid; sau đó là OU và domain |

Chuỗi thứ hai mô tả một entry có nhiều cấp RDN hơn; nó **không** tương đương multi-valued RDN ở chuỗi thứ nhất.

## 3. Multi-valued RDN khác attribute đa trị

~~~ldif
dn: cn=Tran Thi Lan+uid=lan,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
cn: Tran Thi Lan
uid: lan
sn: Tran
telephoneNumber: +84 28 1234 5678
telephoneNumber: +84 90 111 2222
~~~

Entry trên có:

- Một RDN đầu tiên gồm hai AVA: `cn=Tran Thi Lan` và `uid=lan`.
- Attribute `cn` có giá trị được dùng trong RDN.
- Attribute `uid` có giá trị được dùng trong RDN.
- Attribute `telephoneNumber` có hai giá trị nhưng không tham gia RDN.

| Đặc điểm | Multi-valued RDN | Multi-valued attribute |
|---|---|---|
| Cấu tạo | Nhiều AVA trong cùng RDN | Một attribute type có nhiều value |
| Dấu phân cách | `+` giữa các AVA | Nhiều dòng attribute trong LDIF |
| Phạm vi | Thành phần tên entry | Dữ liệu của entry |
| Vai trò | Tham gia định danh/vị trí | Lưu dữ liệu theo schema |
| Ví dụ | `cn=Lan+uid=lan` | Hai dòng `telephoneNumber` |

Các AVA trong RDN tương ứng với các giá trị attribute của entry được đặt tên. Khi tạo entry có RDN `cn=Tran Thi Lan+uid=lan`, dữ liệu entry phải có các giá trị `cn` và `uid` tương ứng, đồng thời các attribute phải hợp lệ với schema/objectClass. Không chỉ gửi DN có hai AVA nhưng bỏ các naming attribute khỏi entry.

## 4. Vì sao cần multi-valued RDN?

Multi-valued RDN có thể hữu ích khi một thành phần tên cần kết hợp nhiều thuộc tính để phân biệt entry cùng cấp.

~~~text
cn=Tran Thi Lan+uid=lan,ou=people,dc=example,dc=org
cn=Tran Thi Lan+uid=lan2,ou=people,dc=example,dc=org
~~~

Hai entry có cùng CN nhưng khác UID. AVA UID bổ sung thành phần phân biệt trong RDN. Đây là ví dụ về **compound naming**.

Có thể cân nhắc multi-valued RDN khi:

- Tên hiển thị không duy nhất trong cùng OU.
- Hệ thống muốn RDN thể hiện cả tên dễ đọc và mã định danh.
- Directory hiện hữu đã có hợp đồng naming nhiều AVA.
- Một hệ thống tích hợp yêu cầu giữ cấu trúc DN cụ thể.

Tuy nhiên, multi-valued RDN không phải lựa chọn mặc định. Nếu `cn` có thể thay đổi khi nhân viên đổi tên, RDN cũng phải đổi. Nếu chỉ cần định danh ổn định, một RDN dựa trên mã ít thay đổi thường đơn giản hơn.

**Một RDN nhiều AVA không tạo ra hai khóa độc lập cho entry.** Nó tạo một RDN duy nhất gồm nhiều thành phần.

## 5. Thứ tự RDN và thứ tự AVA

Cần phân biệt hai loại thứ tự:

1. **Thứ tự RDN trong DN có ý nghĩa cấu trúc.** RDN bên trái xác định entry cụ thể nhất; RDN bên phải xác định cha và gốc.
2. **Thứ tự AVA trong một RDN không mang ý nghĩa ưu tiên.** Các AVA là một tập hợp; thứ tự hiển thị có thể khác mà vẫn biểu diễn cùng RDN.

Ví dụ:

~~~text
cn=Tran Thi Lan+uid=lan,ou=people,dc=example,dc=org
uid=lan+cn=Tran Thi Lan,ou=people,dc=example,dc=org
~~~

Hai chuỗi trên biểu diễn cùng tập AVA trong RDN đầu. Không coi `cn` là “AVA chính” chỉ vì nó xuất hiện trước dấu cộng.

Ngược lại, không thể tùy ý đảo thứ tự các RDN trong DN:

~~~text
cn=Lan+uid=lan,ou=people,dc=example,dc=org
cn=Lan+uid=lan,dc=example,dc=org,ou=people
~~~

Hai chuỗi không còn mô tả cùng cấu trúc cây.

### Index của LdapName.getRdn

Java JNDI `LdapName` lưu các thành phần theo hướng **từ phải sang trái**: index 0 là RDN ngoài cùng bên phải (ít cụ thể nhất). Với DN:

~~~text
cn=Lan+uid=lan,ou=people,dc=example,dc=org
~~~

| Index JNDI | RDN |
|---:|---|
| 0 | `dc=org` |
| 1 | `dc=example` |
| 2 | `ou=people` |
| 3 | `cn=Lan+uid=lan` |

RDN của entry cụ thể nhất là `name.getRdn(name.size() - 1)`, không phải `getRdn(0)`.

## 6. Escaping trong multi-valued RDN theo RFC 4514

Trong biểu diễn DN, dấu cộng không escape là dấu phân cách AVA trong cùng RDN. Nếu dấu cộng là một phần của giá trị, phải escape.

~~~text
cn=Lan+uid=lan,ou=people,dc=example,dc=org
~~~

RDN này có hai AVA: `cn=Lan` và `uid=lan`.

~~~text
cn=Lan\+Security+uid=lan,ou=people,dc=example,dc=org
~~~

AVA CN có giá trị `Lan+Security`; dấu cộng đã escape không tạo AVA mới. AVA thứ hai vẫn là `uid=lan`.

Một số ký tự cần xử lý trong biểu diễn DN:

| Ký tự trong giá trị | Cách biểu diễn ví dụ |
|---|---|
| Dấu phẩy `,` | `\,` |
| Dấu cộng `+` | `\+` |
| Dấu ngoặc kép `"` | `\"` |
| Backslash `\` | `\\` |
| Dấu nhỏ hơn/lớn hơn `<`, `>` | `\<`, `\>` |
| Dấu chấm phẩy `;` | `\;` |
| Dấu bằng `=` | `\=` |
| Khoảng trắng đầu/cuối | Escape theo RFC |
| Dấu `#` đầu giá trị | Escape |
| NUL | Dạng hex `\00` |

Ví dụ CN có dấu phẩy và dấu cộng literal:

~~~text
cn=Lan\, An\+Security+uid=lan,ou=people,dc=example,dc=org
~~~

RDN gồm:

- AVA `cn` có giá trị `Lan, An+Security`.
- AVA `uid` có giá trị `lan`.

Không tự viết parser bằng `split("+")` hoặc `split(",")`. Ký tự có thể đã escape hoặc được biểu diễn bằng hex escape; dấu phân cách chỉ có ý nghĩa khi ở đúng ngữ cảnh cú pháp.

### DN escaping khác filter escaping

RFC 4514 mô tả chuỗi DN; RFC 4515 mô tả chuỗi LDAP search filter. Không dùng chung một hàm escape cho cả hai.

Ví dụ trong filter `(uid=lan\2a)`, `\2a` biểu diễn dấu sao literal theo RFC 4515. Trong DN, quy tắc escape của RDN value theo RFC 4514 được áp dụng. Dùng `LdapNameBuilder` để dựng DN và `LdapQueryBuilder` để dựng filter.

## 7. Phân tích DN bằng LdapName và Rdn

Không nên dùng:

~~~java
String[] rdns = dn.split(",");
String firstRdn = rdns[0];
String[] pairs = firstRdn.split("\\+");
~~~

Các cách trên sai khi DN chứa dấu phẩy/dấu cộng đã escape, backslash, hex escape hoặc giá trị có nhiều dấu bằng.

Dùng API JNDI:

~~~java
import javax.naming.ldap.LdapName;
import javax.naming.ldap.Rdn;

LdapName name = new LdapName(
        "cn=Tran Thi Lan+uid=lan,ou=people,dc=example,dc=org");

Rdn entryRdn = name.getRdn(name.size() - 1);

System.out.println(entryRdn.size()); // 2 AVA
System.out.println(entryRdn.toAttributes());
~~~

`LdapName` parse chuỗi thành cấu trúc DN; `Rdn` đại diện một RDN và `size()` cho biết số AVA. Để đọc toàn bộ AVA, gọi `toAttributes()` rồi duyệt từng attribute/value.

### Trích xuất AVA theo attribute type

~~~java
import javax.naming.NamingException;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;
import javax.naming.ldap.LdapName;
import javax.naming.ldap.Rdn;

public final class RdnReader {

    private RdnReader() {
    }

    public static String requiredSingleValue(
            LdapName dn, String attributeType)
            throws NamingException {

        if (dn == null || dn.isEmpty()) {
            throw new IllegalArgumentException("DN is required");
        }

        Rdn entryRdn = dn.getRdn(dn.size() - 1);
        Attributes avas = entryRdn.toAttributes();
        Attribute attribute = avas.get(attributeType);

        if (attribute == null || attribute.size() != 1) {
            throw new IllegalArgumentException(
                    "RDN must contain one " + attributeType + " AVA");
        }

        Object raw = attribute.get();
        if (!(raw instanceof String value)) {
            throw new IllegalArgumentException(
                    "Expected text RDN value for " + attributeType);
        }
        return value;
    }
}
~~~

Phương thức lấy RDN cụ thể nhất rồi tìm AVA theo tên attribute, không dựa vào vị trí trước/sau dấu cộng. Nó yêu cầu đúng một giá trị cho attribute được chọn; nếu thiếu hoặc sai kiểu thì báo lỗi.

Nếu cần đọc tất cả AVA, có thể duyệt `Attributes.getAll()` và `Attribute.getAll()`. Phải đóng `NamingEnumeration`:

~~~java
Attributes avas = entryRdn.toAttributes();
NamingEnumeration<? extends Attribute> all = avas.getAll();

try {
    while (all.hasMore()) {
        Attribute attribute = all.next();
        System.out.println(attribute.getID());

        NamingEnumeration<?> values = attribute.getAll();
        try {
            while (values.hasMore()) {
                Object value = values.next();
                // Kiểm tra kiểu trước khi chuyển sang DTO.
            }
        } finally {
            values.close();
        }
    }
} finally {
    all.close();
}
~~~

Đoạn duyệt giả định `entryRdn` đã được lấy từ `LdapName` như ví dụ trước. Không in AVA nhạy cảm vào log production chỉ để debug.

## 8. Xây multi-valued RDN bằng API Java

JNDI cung cấp constructor `Rdn(Attributes)`. Mỗi attribute trong tập Attributes trở thành một AVA của RDN.

~~~java
import javax.naming.Name;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.BasicAttributes;
import javax.naming.ldap.Rdn;
import org.springframework.ldap.support.LdapNameBuilder;

BasicAttributes avas = new BasicAttributes(true);
avas.put(new BasicAttribute("cn", "Tran Thi Lan"));
avas.put(new BasicAttribute("uid", "lan"));

Rdn compoundRdn = new Rdn(avas);

Name relativeDn = LdapNameBuilder
        .newInstance("ou=people")
        .add(compoundRdn)
        .build();
~~~

DN thu được tương đương về cấu trúc với:

~~~text
cn=Tran Thi Lan+uid=lan,ou=people
~~~

Thứ tự AVA trong chuỗi được sinh ra có thể khác do cách thư viện biểu diễn/sắp xếp. Khi kiểm tra tương đương, parse cả hai DN thành `LdapName` và so sánh cấu trúc, không dựa vào `String.equals(...)`.

Nếu `ContextSource` có base `dc=example,dc=org`, DN tương đối truyền vào `LdapTemplate` thường là:

~~~text
cn=Tran Thi Lan+uid=lan,ou=people
~~~

DN đầy đủ dùng làm tham chiếu bên ngoài là:

~~~text
cn=Tran Thi Lan+uid=lan,ou=people,dc=example,dc=org
~~~

Không nối base hai lần. Luôn xác định đầu vào là RDN, DN tương đối hay DN đầy đủ trước khi dùng.

## 9. Schema và naming attributes

Mỗi AVA sử dụng một attribute type có định nghĩa hợp lệ; value phải phù hợp syntax/matching rule. Entry phải đáp ứng object class và các ràng buộc schema của directory.

Với `inetOrgPerson`:

- `cn` là thuộc tính MUST kế thừa từ `person`.
- `sn` cũng là thuộc tính MUST của `person`.
- `uid` được phép theo schema `inetOrgPerson`.
- RDN `cn=Tran Thi Lan+uid=lan` chỉ hợp lệ khi server cho phép các attribute type này và entry có các giá trị naming tương ứng.

~~~ldif
dn: cn=Tran Thi Lan+uid=lan,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
cn: Tran Thi Lan
uid: lan
sn: Tran
~~~

Đừng chỉ nhìn thấy `uid` trong RDN rồi kết luận entry có thể bỏ `cn`. `person` vẫn yêu cầu `cn` và `sn`. Nếu attribute type không được object class cho phép, phải bổ sung class/schema phù hợp theo quy trình quản trị directory.

### Naming value và thao tác Modify

Giá trị dùng trong RDN là một phần của tên entry. Không dùng Modify thông thường để xóa value đang cần cho RDN. LDAP có result code `notAllowedOnRDN (67)` cho thao tác vi phạm quy tắc naming. Muốn thay đổi RDN, dùng **ModifyDN**/rename và kiểm tra semantics `deleteOldRDN`.

Cách server xử lý naming values cần được kiểm thử trên sản phẩm LDAP thực tế; không mặc định mọi server tự bổ sung hoặc xóa các attribute theo cùng một cách.

## 10. Ảnh hưởng tới định danh nghiệp vụ

Multi-valued RDN có thể làm identity trở thành một tổ hợp AVA:

~~~text
cn=Tran Thi Lan+uid=lan,ou=people,dc=example,dc=org
~~~

Nếu `cn` thay đổi khi nhân viên đổi tên, RDN cần được thay đổi bằng ModifyDN. Điều này ảnh hưởng:

- DN đã lưu trong group attribute `member`.
- DN pattern trong Spring Security LDAP.
- Cache theo DN.
- Audit log hoặc hệ thống tích hợp lưu full DN.
- Ứng dụng ngoài dùng DN làm khóa tham chiếu.
- Quy trình đồng bộ và migration giữa OU.

Không nên dùng một thuộc tính thay đổi thường xuyên làm thành phần định danh dài hạn nếu chưa có quy trình rename và cập nhật tham chiếu.

Một phương án khác là dùng RDN ổn định:

~~~text
uid=lan,ou=people,dc=example,dc=org
~~~

Tên hiển thị `cn` vẫn nằm trong entry và có thể đổi mà không nhất thiết đổi DN. Quyết định phụ thuộc yêu cầu naming của tổ chức.

### Phạm vi uniqueness

DN đầy đủ phải xác định duy nhất một entry trong DIT. Nhưng `uid=lan` đơn lẻ không nhất thiết duy nhất toàn directory; hai OU khác nhau có thể có cùng UID. RDN uniqueness được xét trong ngữ cảnh entry cùng parent và quy tắc directory. Nếu identity nghiệp vụ phải duy nhất toàn tổ chức, cần một khóa ổn định và chính sách uniqueness riêng.

## 11. Parse identity: đừng chọn AVA đầu tiên

Một lỗi phổ biến:

~~~java
String identity = dn.split(",")[0].split("=")[1];
~~~

Với DN `cn=Tran Thi Lan+uid=lan,ou=people,...`, code có thể trả về dữ liệu sai vì dấu cộng và dấu bằng là một phần cấu trúc. Nó còn sai khi CN chứa dấu phẩy đã escape.

Không giả định `Rdn.getType()` hoặc `getValue()` đại diện toàn bộ multi-valued RDN. Nếu cần UID, hãy yêu cầu attribute type `uid` từ tập AVA:

~~~java
LdapName dn = new LdapName(
        "cn=Tran Thi Lan+uid=lan,ou=people,dc=example,dc=org");

String uid = RdnReader.requiredSingleValue(dn, "uid");
String cn = RdnReader.requiredSingleValue(dn, "cn");
~~~

Kết quả là `uid=lan` và `cn=Tran Thi Lan`, bất kể AVA được hiển thị theo thứ tự nào.

Nếu cần business identity, hãy tách nó khỏi full DN:

~~~java
public record PersonIdentity(
        String uid,
        String organizationalUnit) {
}
~~~

UID là định danh nghiệp vụ theo hợp đồng ứng dụng; DN là tên/vị trí entry trong directory. Move/rename có thể đổi DN nhưng không nhất thiết đổi UID.

## 12. Tìm entry theo attribute bằng Spring LDAP

Nếu mục tiêu là tìm theo UID, thường nên search trên attribute `uid` thay vì parse DN thủ công:

~~~java
import java.util.List;

import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.SearchScope;

import static org.springframework.ldap.query.LdapQueryBuilder.query;

public List<PersonSummary> findByUid(
        LdapTemplate ldapTemplate, String uid) {

    LdapQuery ldapQuery = query()
            .base("ou=people")
            .searchScope(SearchScope.SUBTREE)
            .where("objectClass").is("inetOrgPerson")
            .and("uid").is(uid);

    return ldapTemplate.search(
            ldapQuery,
            (AttributesMapper<PersonSummary>) attrs ->
                    new PersonSummary(
                            (String) attrs.get("uid").get(),
                            (String) attrs.get("cn").get(),
                            (String) attrs.get("sn").get()));
}
~~~

Đây là ví dụ rút gọn. Production mapper phải kiểm tra attribute có tồn tại, cardinality, Java type và lỗi dữ liệu. Nếu UID không duy nhất trong search base, API cần xử lý 0, 1 hoặc nhiều kết quả tường minh.

`LdapQueryBuilder` xây filter từ giá trị UID mà không nối chuỗi filter thủ công. Equality semantics do matching rule của `uid` trên server quyết định. Nếu cần DN đầy đủ của entry, dùng `ContextMapper`/`DirContextOperations` hoặc ODM phù hợp; không suy DN bằng cách nối các field.

Filter trên attribute có thể là:

~~~text
(&(objectClass=inetOrgPerson)(uid=lan))
~~~

Nếu muốn xác minh cả CN và UID:

~~~text
(&(objectClass=inetOrgPerson)(uid=lan)(cn=Tran Thi Lan))
~~~

Đây là filter trên entry attributes, không phải cú pháp để đưa nguyên chuỗi RDN có dấu cộng vào filter. Search filter có escaping riêng theo RFC 4515.

## 13. Ánh xạ bằng Spring Data LDAP ODM

Một entity Spring Data LDAP có thể giữ DN trong field `Name`:

~~~java
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

    @Attribute(name = "sn")
    private String surname;

    public DirectoryPerson() {
    }

    // Getter/setter theo yêu cầu ODM.
}
~~~

Multi-valued RDN được giữ trong field `dn` dưới dạng một tên có cấu trúc. Không ánh xạ toàn bộ DN vào một `String uid` rồi bỏ các AVA còn lại.

~~~java
import java.util.List;
import org.springframework.data.ldap.repository.LdapRepository;

public interface DirectoryPersonRepository
        extends LdapRepository<DirectoryPerson> {

    List<DirectoryPerson> findByUid(String uid);
}
~~~

`findByUid(...)` là truy vấn theo attribute `uid`, không có nghĩa DN bắt buộc chỉ gồm UID. Entry có DN `cn=Lan+uid=lan,ou=people` vẫn có thể được tìm theo UID nếu mapping và schema đúng.

### Cẩn trọng khi save và rename

Nếu code thay đổi `cn` trong entity trong khi CN cũng là AVA của RDN, việc ghi có thể cần ModifyDN thay vì chỉ sửa attribute. Không giả định `repository.save(entity)` tự xử lý mọi thay đổi RDN nhiều AVA.

Cần xác định:

- Có đổi RDN không?
- UID có được giữ trong RDN mới không?
- `deleteOldRDN` được xử lý thế nào?
- Giá trị AVA cũ có cần giữ như dữ liệu thông thường không?
- Các DN tham chiếu trong group có được cập nhật không?

Dùng `LdapTemplate.rename(...)` hoặc ModifyDN có kiểm soát khi thay đổi tên entry và kiểm thử trên directory test.

## 14. Spring Security LDAP và DN pattern

Một cấu hình DN pattern đơn giản:

~~~java
factory.setUserDnPatterns("uid={0},ou=people");
~~~

giả định user DN có RDN đầu `uid={0}`. Nếu entry có multi-valued RDN:

~~~text
cn=Tran Thi Lan+uid=lan,ou=people,dc=example,dc=org
~~~

thì pattern `uid={0},ou=people` không mô tả đúng RDN. Không thay bằng pattern tùy tiện nếu CN có thể đổi hoặc chứa ký tự đặc biệt.

Cách tiếp cận phù hợp hơn trong nhiều trường hợp là **tìm user theo attribute ổn định**, lấy DN thực từ kết quả search, sau đó bind bằng DN tìm được. Search cần:

- Base DN và scope được giới hạn.
- Filter kết hợp `objectClass` và định danh như `uid`.
- Kết quả duy nhất trong phạm vi xác thực.
- Bind DN lấy từ entry thực, không ghép thủ công.
- ACL chỉ cho phép đọc thông tin cần thiết.

Multi-valued RDN không làm mất khả năng xác thực LDAP; nó làm giả định “DN luôn là uid=...” không còn đúng. Kiểm tra cấu hình Spring Security LDAP theo phiên bản đang dùng.

## 15. ModifyDN và thay đổi một AVA trong RDN

Entry hiện tại:

~~~text
cn=Tran Thi Lan+uid=lan,ou=people,dc=example,dc=org
~~~

Sau khi đổi tên, RDN mới có thể là:

~~~text
cn=Tran Lan Nguyen+uid=lan,ou=people,dc=example,dc=org
~~~

Đây là thay đổi **RDN**. LDAP ModifyDN cho phép chỉ định RDN mới và cờ `deleteOldRDN` để quyết định xử lý các giá trị naming cũ theo giao thức.

Trước khi rename, cần kiểm tra:

1. DN đích chưa được entry sibling khác sử dụng.
2. Parent DN đúng và account có quyền rename.
3. AVA mới hợp lệ theo schema.
4. CN cũ có bị xóa theo `deleteOldRDN` hay cần giữ như dữ liệu lịch sử.
5. UID được giữ trong RDN mới nếu định danh cần ổn định.
6. Các tham chiếu DN như `member` có được cập nhật bởi plugin hoặc migration tool.
7. Cache, audit và consumer ngoài lưu full DN đã được xử lý.

Không dùng Modify thông thường để xóa AVA đang tạo RDN. Thay đổi RDN thuộc thao tác ModifyDN; server có thể trả `notAllowedOnRDN (67)` khi một Modify cố xóa giá trị naming.

## 16. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Parse sai UID | Lấy AVA đầu tiên hoặc split dấu cộng | Dùng `Rdn.toAttributes()` và tìm theo type |
| Tách nhầm DN | `split(",")` gặp comma escaped | Parse bằng `LdapName` |
| Tách nhầm multi-RDN | `split("+")` gặp plus escaped | Parse bằng `Rdn` |
| So sánh DN sai | Dùng `String.equals(...)` trên biểu diễn khác nhau | Parse thành `LdapName`; kiểm tra semantics |
| Chỉ thấy một AVA | Code giả định RDN đơn trị | Dùng `Rdn.size()` và `toAttributes()` |
| Add thất bại schema | Thiếu naming attribute hoặc MUST | Kiểm tra AVA, objectClass và MUST/MAY |
| Modify xóa naming value thất bại | Dùng Modify thay cho ModifyDN | Dùng thao tác rename |
| Group mất tham chiếu | `member` vẫn lưu DN cũ | Kiểm tra referential integrity/cập nhật DN |
| Login không tìm thấy user | DN pattern chỉ có `uid={0}` | Dùng user search và bind DN thực |
| Save làm đổi DN ngoài ý muốn | ODM/save không được thiết kế cho rename | Tách cập nhật attribute và ModifyDN |
| Search trả nhiều entry | UID không duy nhất trong base | Thu hẹp base hoặc kiểm tra business identity |
| Dấu cộng bị hiểu thành AVA mới | Không escape theo RFC 4514 | Dùng LdapNameBuilder/Rdn |

## 17. Unit test cho multi-valued RDN

Unit test nên xác minh: parse đúng số AVA, lấy đúng value theo attribute type và không phụ thuộc thứ tự hiển thị AVA.

~~~java
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;
import javax.naming.ldap.LdapName;
import javax.naming.ldap.Rdn;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class MultiValuedRdnTest {

    @Test
    void parsesBothAvasFromEntryRdn() throws Exception {
        LdapName dn = new LdapName(
                "cn=Tran Thi Lan+uid=lan,ou=people,dc=example,dc=org");

        Rdn entryRdn = dn.getRdn(dn.size() - 1);

        assertEquals(2, entryRdn.size());

        Attributes avas = entryRdn.toAttributes();
        Attribute cn = avas.get("cn");
        Attribute uid = avas.get("uid");

        assertEquals("Tran Thi Lan", cn.get());
        assertEquals("lan", uid.get());
    }

    @Test
    void avaOrderDoesNotChangeRdnIdentity() throws Exception {
        LdapName first = new LdapName(
                "cn=Tran Thi Lan+uid=lan,ou=people,dc=example,dc=org");

        LdapName second = new LdapName(
                "uid=lan+cn=Tran Thi Lan,ou=people,dc=example,dc=org");

        assertEquals(first, second);
    }

    @Test
    void escapedPlusRemainsInsideAttributeValue() throws Exception {
        Rdn rdn = new Rdn("cn=Lan\\+Security+uid=lan");

        assertEquals(2, rdn.size());
        assertEquals("Lan+Security", rdn.toAttributes()
                .get("cn").get());
        assertEquals("lan", rdn.toAttributes()
                .get("uid").get());
    }

    @Test
    void commaInsideValueIsNotAnotherRdn() throws Exception {
        LdapName dn = new LdapName(
                "cn=Lan\\, An+uid=lan,ou=people,dc=example,dc=org");

        assertEquals(4, dn.size());
        Rdn entryRdn = dn.getRdn(dn.size() - 1);

        assertEquals("Lan, An", entryRdn.toAttributes()
                .get("cn").get());
    }
}
~~~

Test `avaOrderDoesNotChangeRdnIdentity` kiểm tra hành vi JNDI `LdapName.equals(...)` trên runtime Java đang dùng. Đây là so sánh cấu trúc tên ở phía client; **không thay thế** schema-specific matching rules và hành vi directory server.

## 18. Integration test với LDAP directory

Unit test xác minh parser; chỉ directory server mới xác nhận schema, naming, Add và ModifyDN. Dùng directory test độc lập có schema tương ứng.

Fixture LDIF:

~~~ldif
dn: ou=people,dc=example,dc=org
objectClass: top
objectClass: organizationalUnit
ou: people

dn: cn=Tran Thi Lan+uid=lan,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
cn: Tran Thi Lan
uid: lan
sn: Tran
~~~

| Kịch bản | Thao tác | Kết quả cần xác nhận |
|---|---|---|
| Add multi-valued RDN | Tạo entry có CN+UID trong RDN | Server chấp nhận nếu schema/naming cho phép |
| Thiếu naming attribute | Bỏ UID hoặc CN khỏi entry | Server áp dụng quy tắc naming/schema |
| AVA không được schema cho phép | Dùng attribute type không hợp lệ | Schema validation thất bại |
| Search theo UID | Filter `(uid=lan)` | Tìm đúng entry |
| AVA order khác | Parse DN đảo thứ tự AVA | Client nhận diện cùng RDN |
| Escaped plus | CN chứa dấu cộng literal | Không tạo thêm AVA |
| Rename CN | ModifyDN với RDN mới | DN đổi, naming values xử lý theo deleteOldRDN |
| Remove naming value bằng Modify | Cố xóa CN đang thuộc RDN | Server từ chối nếu vi phạm quy tắc |
| Group membership | Lưu full DN trong `member` | Group tham chiếu đúng entry |
| Authentication | Search user theo UID rồi bind DN thực | Xác thực theo user-search flow |
| ACL | Bind account không có quyền rename | Server từ chối thao tác |

Không thử ghi entry sai schema trên production. Kết quả Add/ModifyDN phụ thuộc server, schema, ACL, naming context và referential integrity.

## 19. Bảo mật và thiết kế định danh

Multi-valued RDN không làm thay đổi nguyên tắc bảo mật LDAP:

- Không nhận DN tùy ý từ client để lookup/Modify/Delete; nhận business identifier đã validate rồi dựng DN trong nhánh được phép.
- Dùng `LdapNameBuilder` và `LdapQueryBuilder` đúng ngữ cảnh, không ghép chuỗi DN/filter từ input.
- Xác minh UID trong search base và xử lý nhiều kết quả; không chọn tùy tiện entry đầu tiên khi identity bị trùng.
- Giới hạn service account theo OU và thao tác; quyền rename thường nhạy cảm hơn quyền đọc.
- Không log full DN hoặc AVA nhạy cảm nếu không cần.
- Dùng LDAPS/StartTLS có xác minh chứng chỉ và bảo vệ bind credential.
- Không dùng `cn` hoặc tên hiển thị làm yếu tố duy nhất để xác thực khi nó có thể trùng/đổi.
- Khi DN thay đổi, kiểm tra cache, group reference, session và hệ thống ngoài directory.

**DN là tên/vị trí trong DIT, không nhất thiết là khóa nghiệp vụ bền vững.** Ứng dụng nên xác định business identity riêng, ví dụ UID hoặc employee ID có quy tắc duy nhất, rồi ánh xạ tới DN hiện tại. Điều đó giúp đổi OU/RDN mà không bắt mọi hệ thống phụ thuộc phải thay khóa người dùng.

## 20. Bài tập thực hành

**Bối cảnh:** directory nhân sự lưu user dưới `ou=people`. Đội tích hợp nhận DN dạng `cn=Full Name+uid=login,ou=people,...` và cần tìm người, cập nhật hồ sơ, quản lý nhóm bằng Spring Data LDAP.

Thực hiện trên LDAP test:

1. Tạo entry `inetOrgPerson` với DN `cn=Tran Thi Lan+uid=lan,ou=people,...`, bảo đảm AVA và MUST attributes có mặt.
2. Parse DN bằng `LdapName`, lấy RDN cụ thể nhất và xác nhận `Rdn.size() == 2`.
3. Dùng `Rdn.toAttributes()` trích xuất CN và UID theo attribute type.
4. Tạo DN có AVA order đảo; xác minh không phụ thuộc AVA đầu tiên.
5. Thử CN chứa dấu phẩy và dấu cộng literal; parse bằng JNDI.
6. Viết unit test chứng minh split chuỗi không phải parser an toàn.
7. Tạo RDN từ `BasicAttributes` và `Rdn(Attributes)`, sau đó thêm vào DN bằng `LdapNameBuilder`.
8. Tạo entry bằng `LdapTemplate.bind(...)`; kiểm tra objectClass và naming values.
9. Viết `LdapTemplate.search(...)` filter theo UID, không parse DN để tìm user.
10. Ánh xạ entry sang entity có `@Id Name dn` và thử repository finder theo UID.
11. Đổi CN bằng ModifyDN; kiểm tra `deleteOldRDN` và giá trị CN cũ/mới.
12. Cập nhật group `groupOfNames.member` theo full DN; xác minh sau rename.
13. Thử xác thực bằng user search thay cho DN pattern chỉ chứa UID.
14. Viết integration test cho Add, Search, ModifyDN, group reference và ACL.
15. Đề xuất cách lưu business identity độc lập với DN để hỗ trợ đổi tên/di chuyển OU.

**Tiêu chí hoàn thành:** phân biệt AVA với attribute value đa trị; parse RDN nhiều AVA đúng chuẩn; không dựa vào thứ tự hiển thị; xây DN an toàn; xử lý rename và giữ đúng tham chiếu/định danh trong Spring Data LDAP.

## 21. Tổng kết và tài liệu tham khảo

Multi-valued RDN là **một RDN chứa nhiều AVA**, thường được phân cách bằng dấu `+`. Các AVA cùng tham gia đặt tên entry; thứ tự AVA không phải thứ tự ưu tiên. Dấu phẩy `,` phân cách RDN trong DN, còn dấu cộng đã escape chỉ là dữ liệu của AVA value.

Trong Java/Spring Data LDAP:

- Parse bằng `LdapName` và `Rdn`, không tách chuỗi bằng dấu phẩy/dấu cộng.
- Dùng `Rdn.toAttributes()` để lấy AVA theo attribute type.
- Dùng `LdapNameBuilder` để tạo DN và phân biệt DN tương đối/full DN.
- Kiểm tra schema, naming attributes và objectClass khi Add/ModifyDN.
- Tách business identity khỏi DN nếu entry có thể rename hoặc move.
- Kiểm thử với directory server thật cho schema, ACL, group reference và authentication.

Nguồn tham khảo:

- [RFC 4514 — String Representation of Distinguished Names](https://www.rfc-editor.org/rfc/rfc4514): DN, RDN, AVA và escaping.
- [RFC 4512 — Directory Information Models](https://www.rfc-editor.org/rfc/rfc4512): DIT, entry, attribute type, objectClass và naming.
- [RFC 4511 — LDAP Protocol](https://www.rfc-editor.org/rfc/rfc4511): Add, Modify, ModifyDN, Delete và naming value.
- [Java SE — LdapName](https://docs.oracle.com/en/java/javase/17/docs/api/java.naming/javax/naming/ldap/LdapName.html): parse, thao tác và so sánh DN.
- [Java SE — Rdn](https://docs.oracle.com/en/java/javase/17/docs/api/java.naming/javax/naming/ldap/Rdn.html): RDN và chuyển sang Attributes.
- [Spring LDAP Reference](https://docs.spring.io/spring-ldap/reference/): `LdapNameBuilder`, `LdapTemplate`, query và mapping.
- [Spring Data LDAP Reference](https://docs.spring.io/spring-data/ldap/reference/): ODM, `@Entry`, `@Id` và repository.
- [RFC 4515 — LDAP Search Filters](https://www.rfc-editor.org/rfc/rfc4515): filter escaping, phân biệt với DN escaping của RFC 4514.
