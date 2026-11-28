# So sánh DN theo ngữ nghĩa thay vì chuẩn hóa chuỗi tùy ý

Hai chuỗi dưới đây nhìn khác nhau:

~~~text
CN=Lan Nguyen,OU=People,DC=example,DC=org
cn=Lan Nguyen, ou=People, dc=example, dc=org
~~~

RFC 4514 không định nghĩa một chuỗi DN canonical duy nhất. RFC 4517 quy định phép so sánh DN theo matching rule distinguishedNameMatch: thứ tự RDN có ý nghĩa, thứ tự AVA trong cùng một multi-valued RDN không có ý nghĩa, và giá trị AVA được so sánh theo equality matching rule của loại thuộc tính tương ứng.

Bài thuộc chương **DN và định danh** của module `SPRING_DATA_LDAP`. Nội dung tập trung vào parse cấu trúc DN, so sánh ngữ nghĩa, escape, JNDI LdapName/Rdn và các giới hạn của so sánh ở phía Java.

## 1. Mục tiêu học tập

- Phân biệt DN string với cấu trúc RDN/AVA.
- Giải thích thứ tự RDN và AVA.
- Dùng javax.naming.ldap.LdapName và Rdn.
- Hiểu matching rule distinguishedNameMatch.
- Phân biệt JNDI equals với schema-aware equality ở LDAP server.
- Kiểm tra DN con theo base DN.
- Tránh lowercase, trim, split hoặc sort chuỗi DN tùy tiện.
- Phân biệt DN escaping với filter escaping.
- Nhận biết DN có thể thay đổi khi entry rename/move.

## 2. DN là cấu trúc, chuỗi chỉ là cách biểu diễn

DN (Distinguished Name) định danh một entry trong cây directory. Ví dụ:

~~~text
uid=lan,ou=people,dc=example,dc=org
~~~

Có thể đọc theo cấu trúc:

~~~text
DN
├── RDN: uid=lan
├── RDN: ou=people
├── RDN: dc=example
└── RDN: dc=org
~~~

Mỗi RDN (Relative Distinguished Name) gồm một hoặc nhiều AVA (Attribute Value Assertion). AVA là một cặp attribute type và attribute value.

| Lớp | Ví dụ | Vai trò |
|---|---|---|
| Chuỗi DN | uid=lan,ou=people,dc=example,dc=org | Biểu diễn text |
| Cấu trúc DN | Chuỗi RDN gồm AVA | Tên đã parse |
| Matching semantics | distinguishedNameMatch | Quyết định equality |

Một DN không đơn giản là một câu có dấu phẩy. Dấu phẩy có thể nằm trong giá trị đã escape; dấu cộng có thể phân tách nhiều AVA trong cùng RDN; giá trị có thể dùng escape hex hoặc biểu diễn nhị phân. Vì vậy, split theo dấu phẩy không phải parser DN.

## 3. Thứ tự RDN trong DN có ý nghĩa

Xét hai tên:

~~~text
uid=lan,ou=people,dc=example,dc=org
ou=people,uid=lan,dc=example,dc=org
~~~

Chúng có cùng một số đoạn text, nhưng thứ tự RDN khác nhau. Tên thứ nhất biểu diễn entry UID Lan nằm trong OU people. Tên thứ hai mô tả một cây phân cấp khác.

Với DN có dạng uid=lan,ou=people,dc=example,dc=org:

- RDN bên trái nhất thường là RDN leaf của entry đang được định danh.
- RDN bên phải nhất nằm gần root hơn.
- Các RDN tiếp theo đi về phía naming context/root.

RFC 4517 yêu cầu hai DN có cùng số RDN và các RDN tương ứng theo vị trí phải tương đương. Không được sắp xếp toàn bộ RDN theo alphabet rồi so sánh.

| DN A | DN B | Kết luận |
|---|---|---|
| uid=lan,ou=people,dc=example,dc=org | uid=lan,ou=people,dc=example,dc=org | Cùng cấu trúc |
| uid=lan,ou=people,dc=example,dc=org | uid=lan,ou=engineering,dc=example,dc=org | Khác RDN OU |
| uid=lan,ou=people,dc=example,dc=org | ou=people,uid=lan,dc=example,dc=org | Khác thứ tự RDN |
| uid=lan,ou=people,dc=example,dc=org | uid=lan,ou=people,dc=other,dc=org | Khác naming context |

## 4. Thứ tự AVA trong một multi-valued RDN không có ý nghĩa

Một RDN có thể chứa nhiều AVA, phân tách bằng dấu cộng:

~~~text
cn=Lan Nguyen+uid=lan,ou=people,dc=example,dc=org
~~~

Hai chuỗi sau biểu diễn cùng tập AVA trong RDN đầu tiên:

~~~text
cn=Lan Nguyen+uid=lan,ou=people,dc=example,dc=org
uid=lan+cn=Lan Nguyen,ou=people,dc=example,dc=org
~~~

Theo distinguishedNameMatch, AVA trong cùng RDN được ghép theo attribute type; thứ tự viết AVA không có ý nghĩa. Điều này không cho phép sắp xếp RDN giữa các cấp của DN.

## 5. RFC 4514 không định nghĩa canonical DN string

Một lỗi thường gặp là tạo hàm:

~~~java
String normalizeDn(String dn) {
    return dn.trim().toLowerCase();
}
~~~

Hàm này không phải canonicalization DN hợp lệ. Nó thay đổi mọi giá trị theo một quy tắc chung, trong khi semantics của giá trị AVA phụ thuộc loại thuộc tính và matching rule.

RFC 4514 quy định cách chuyển DN có cấu trúc sang chuỗi và parse chuỗi trở lại. Tiêu chuẩn nói rõ không có một biểu diễn chuỗi canonical duy nhất; so sánh equality phải theo distinguishedNameMatch của RFC 4517.

Các dạng biểu diễn có thể khác nhau nhưng vẫn parse thành cấu trúc tương đương: attribute type viết hoa/thường, dấu cách hợp lệ quanh dấu phân tách, ký tự đặc biệt escape bằng ký tự hoặc hex, biểu diễn UTF-8 hex tương đương và AVA trong multi-valued RDN có thứ tự text khác nhau.

Ngược lại, lowercase không sửa được cấu trúc RDN sai thứ tự.

## 6. Escape trong DN: parse trước khi so sánh

RFC 4514 quy định cách escape các ký tự đặc biệt trong giá trị DN.

| Ký tự trong giá trị | Cách biểu diễn có thể dùng |
|---|---|
| Dấu phẩy , | \, hoặc \2C |
| Dấu cộng + | \+ hoặc \2B |
| Dấu nháy kép " | \" hoặc dạng hex |
| Backslash | \\ hoặc \5C |
| Dấu chấm phẩy ; | \; hoặc \3B |
| Dấu nhỏ hơn/lớn hơn < và > | \< hoặc \> (có thể dùng dạng hex) |
| Dấu bằng = | Có thể escape bằng \= hoặc \3D |
| Khoảng trắng đầu/cuối | Escape theo quy tắc RFC 4514 |
| Dấu thăng ở đầu giá trị # | Escape theo quy tắc RFC 4514 |
| NUL | Dùng escape hex |

Ví dụ CN có dấu phẩy:

~~~text
cn=Smith\, Alice,ou=people,dc=example,dc=org
~~~

Hoặc dùng escape hex:

~~~text
cn=Smith\2C Alice,ou=people,dc=example,dc=org
~~~

Không xóa backslash hoặc thay mọi dấu phẩy bằng dấu phân tách. Dấu phẩy được escape là một phần của giá trị AVA, không phải ranh giới RDN.

## 7. Java string literal có thêm một tầng escape

Trong Java, backslash của DN string cần được escape trong source code:

~~~java
String dnText =
    "cn=Smith\\, Alice,ou=people,dc=example,dc=org";
~~~

Khi chạy, giá trị dnText có một backslash trước dấu phẩy. Parser DN mới giải mã escape đó thành dấu phẩy trong giá trị CN.

Không tự viết chuỗi replace để unescape DN. Escape hex, Unicode UTF-8 và backslash literal có thể bị xử lý sai nếu thay thế theo thứ tự tùy ý. Dùng parser chuẩn như LdapName/Rdn.

## 8. Unicode, UTF-8 và giá trị nhị phân

DN có thể chứa Unicode, ví dụ:

~~~text
cn=Nguyễn Văn An,ou=people,dc=example,dc=org
~~~

Một giá trị UTF-8 cũng có thể được biểu diễn bằng octet escape hex theo RFC 4514. Khi parse, điều quan trọng là so sánh giá trị đã được giải mã theo semantics, không so sánh chuỗi escape thô.

- Chuỗi Unicode có thể có nhiều dạng code point nhìn giống nhau.
- Tự gọi Unicode normalization như NFC/NFD không tự động đồng nghĩa với LDAP matching rule.
- Matching rule có thể áp dụng các bước chuẩn bị chuỗi cụ thể.
- AVA có giá trị nhị phân có thể được biểu diễn bằng hexstring và BER-encoded value.
- Không giả định mọi AVA đều có giá trị Java String; JNDI Rdn.getValue() có thể trả byte[] cho giá trị nhị phân.

Nếu directory có attribute custom chứa dữ liệu nhị phân, hãy xác minh schema và syntax trước khi viết comparator.


## 9. Matching rule quyết định equality của DN

RFC 4517 định nghĩa distinguishedNameMatch với OID 2.5.13.1. Quy tắc này được áp dụng khi so sánh giá trị có DN syntax với một giá trị DN khác, ví dụ trong các thuộc tính tham chiếu DN như member hoặc manager nếu schema khai báo matching rule phù hợp.

Hai DN được xem tương đương theo quy tắc này khi:

1. Có cùng số RDN.
2. Các RDN tương ứng theo vị trí là tương đương.
3. Mỗi RDN có cùng số AVA.
4. AVA được đối chiếu theo attribute type; thứ tự AVA trong cùng RDN không có ý nghĩa.
5. Giá trị của hai AVA cùng type được so sánh theo equality matching rule của attribute type đó.

Điểm thứ năm rất quan trọng: equality của giá trị cn không nhất thiết dùng cùng quy tắc với một attribute custom có matching rule khác. Không thể kết luận “mọi giá trị DN đều không phân biệt hoa thường” chỉ từ một ví dụ dùng cn.

### 9.1. Ví dụ schema ảnh hưởng kết quả

Giả sử schema có:

- cn dùng một matching rule không phân biệt hoa thường.
- employeeCode dùng matching rule phân biệt hoa thường.

Khi đó, sự khác biệt chữ hoa/chữ thường trong AVA cn và employeeCode có thể có kết quả khác nhau theo schema. Nếu comparator tự lowercase mọi AVA, nó có thể làm mất khác biệt có ý nghĩa của employeeCode.

Ví dụ minh họa:

~~~text
employeeCode=AB12,ou=people,dc=example,dc=org
employeeCode=ab12,ou=people,dc=example,dc=org
~~~

Không tự khẳng định hai tên bằng nhau. Kết luận phụ thuộc equality matching rule của employeeCode trong schema đang dùng.

### 9.2. Không nhầm DN matching với attribute matching thông thường

Một filter tìm người theo cn sẽ dùng matching rule của thuộc tính cn. Một filter tìm group có member bằng một DN sẽ dùng matching rule của member theo schema server.

~~~text
(cn=Lan Nguyen)
(member=uid=lan,ou=people,dc=example,dc=org)
~~~

Filter thứ hai còn cần escape giá trị DN theo cú pháp LDAP filter. DN escaping và filter escaping là hai bước khác nhau; phần 18 sẽ trình bày chi tiết.

## 10. JNDI LdapName: công cụ parse và so sánh DN trong Java

JDK cung cấp:

- javax.naming.ldap.LdapName: biểu diễn một DN thành danh sách RDN.
- javax.naming.ldap.Rdn: biểu diễn một RDN thành các cặp attribute type/value.

Đây là API có sẵn trong module java.naming, không cần thêm dependency Spring để parse DN. Tham khảo [Java SE 17 LdapName API](https://docs.oracle.com/en/java/javase/17/docs/api/java.naming/javax/naming/ldap/LdapName.html) và [Java SE 17 Rdn API](https://docs.oracle.com/en/java/javase/17/docs/api/java.naming/javax/naming/ldap/Rdn.html).

### 10.1. Parse và so sánh hai DN

~~~java
import javax.naming.InvalidNameException;
import javax.naming.ldap.LdapName;

public final class DnComparison {

    private DnComparison() {
    }

    public static boolean sameJndiName(
            String first,
            String second) throws InvalidNameException {

        LdapName left = new LdapName(first);
        LdapName right = new LdapName(second);

        return left.equals(right);
    }
}
~~~

Sử dụng:

~~~java
boolean same = DnComparison.sameJndiName(
    "CN=Lan Nguyen,OU=People,DC=example,DC=org",
    "cn=Lan Nguyen, ou=People, dc=example, dc=org"
);

System.out.println(same);
~~~

Với semantics được JDK công bố, parser xử lý khác biệt về chữ hoa/chữ thường ở type và string value, các dạng quoting/escaping/UTF-8 hex tương đương, cùng thứ tự AVA trong multi-valued RDN. Xem [LdapName equality](https://docs.oracle.com/en/java/javase/26/docs/api/java.naming/javax/naming/ldap/LdapName.html#equals(java.lang.Object)).

### 10.2. LdapName.equals không phải schema-aware distinguishedNameMatch

Đây là giới hạn cần nhớ khi dùng Java để so sánh DN.

JDK Javadoc mô tả LdapName/Rdn equality theo quy tắc của implementation:

- Attribute type được so sánh không phân biệt hoa thường.
- String value được so sánh không phân biệt hoa thường.
- Các dạng escape/quoting/UTF-8 hex tương đương được xem bằng nhau.
- Thứ tự AVA trong một multi-valued RDN không có ý nghĩa.

Trong khi đó, RFC 4517 distinguishedNameMatch so sánh giá trị AVA theo equality matching rule của từng attribute type. Vì vậy, LdapName.equals() là công cụ parse và so sánh cấu trúc hữu ích trong Java, nhưng không nên xem nó là bản triển khai đầy đủ matching semantics của mọi schema LDAP. Đặc biệt với attribute custom có caseExactMatch hoặc matching rule riêng, phép so sánh JNDI có thể cho kết quả khác server.

Khi cần kết quả có thẩm quyền theo schema, hãy để LDAP server thực hiện phép so sánh trên thuộc tính DN có matching rule phù hợp, hoặc triển khai comparator có schema/matching-rule metadata rõ ràng. Không tự suy ra rule của attribute từ tên hiển thị.

### 10.3. Parser không thay thế schema validation

Javadoc của JNDI mô tả LdapName theo cú pháp RFC 2253, phiên bản tiền nhiệm đã được RFC 4514 thay thế. Parser có chủ ý chấp nhận một số dạng biểu diễn rộng và không phát hiện mọi vi phạm của một DN không hợp lệ. Parser cũng không truy vấn schema của LDAP server để xác nhận attribute type, object class hoặc quyền tồn tại của entry.

Vì vậy, parse thành công chỉ chứng minh chuỗi được JNDI chuyển thành cấu trúc Name. Directory server vẫn là nơi quyết định DN có hợp lệ trong naming context và schema cụ thể hay không. Khi tích hợp với server/thiết bị directory khác nhau, hãy có interoperability test cho các DN có Unicode, binary value, attribute descriptor và escape đặc biệt.

## 11. Những trường hợp JNDI LdapName có thể xem bằng nhau

Ví dụ minh họa theo semantics JDK:

~~~java
import javax.naming.ldap.LdapName;

public class DnExamples {

    public static void main(String[] args) throws Exception {
        LdapName a = new LdapName(
            "cn=Smith\\, Alice,ou=people,dc=example,dc=org"
        );

        LdapName b = new LdapName(
            "CN=Smith\\2C Alice, OU=people, DC=example, DC=org"
        );

        System.out.println(a.equals(b));
    }
}
~~~

Trong source Java, hai backslash trước escape là cần thiết để runtime string có một backslash theo cú pháp DN. Ví dụ trên minh họa cùng dấu phẩy trong CN được viết bằng escape ký tự và escape hex.

Một ví dụ multi-valued RDN:

~~~java
LdapName first = new LdapName(
    "cn=Lan Nguyen+uid=lan,ou=people,dc=example,dc=org"
);

LdapName second = new LdapName(
    "UID=lan+CN=Lan Nguyen,OU=people,DC=example,DC=org"
);

boolean same = first.equals(second);
~~~

Thứ tự AVA thay đổi nhưng các cặp type/value vẫn tương ứng.

### 11.1. Những trường hợp không nên coi bằng nhau

~~~java
LdapName first = new LdapName(
    "uid=lan,ou=people,dc=example,dc=org"
);

LdapName differentParent = new LdapName(
    "uid=lan,ou=engineering,dc=example,dc=org"
);

LdapName differentOrder = new LdapName(
    "ou=people,uid=lan,dc=example,dc=org"
);

System.out.println(first.equals(differentParent)); // false
System.out.println(first.equals(differentOrder));   // false
~~~

Đây là các DN có cấu trúc khác nhau. Không được sắp xếp RDN để biến chúng thành cùng một tên.

## 12. Xây dựng DN từ Rdn thay vì nối chuỗi

Khi tạo DN động, dùng Rdn và LdapName:

~~~java
import javax.naming.ldap.LdapName;
import javax.naming.ldap.Rdn;

public class DnBuilderExample {

    public static LdapName personDn(String uid) throws Exception {
        LdapName dn = new LdapName("dc=example,dc=org");
        dn.add(new Rdn("ou", "people"));
        dn.add(new Rdn("uid", uid));
        return dn;
    }

    public static void main(String[] args) throws Exception {
        LdapName dn = personDn("lan,contractor");
        System.out.println(dn);
    }
}
~~~

Rdn("uid", uid) nhận giá trị chưa escape như một giá trị literal và chịu trách nhiệm tạo biểu diễn RDN hợp lệ. Nếu UID chứa dấu phẩy, dấu cộng, backslash hoặc ký tự đặc biệt, toString() sẽ escape để không bị hiểu nhầm thành ranh giới RDN.

Kết quả có thể tương tự:

~~~text
uid=lan\,contractor,ou=people,dc=example,dc=org
~~~

Không viết:

~~~java
String dn = "uid=" + uid + ",ou=people,dc=example,dc=org";
~~~

Nếu uid có dấu phẩy, dấu cộng, backslash hoặc ký tự đặc biệt, chuỗi ghép có thể bị parse thành cấu trúc khác.

### 12.1. Thứ tự khi add RDN vào LdapName

LdapName đánh số RDN từ phải sang trái so với cách hiển thị DN. Với:

~~~text
uid=lan,ou=people,dc=example,dc=org
~~~

JDK mô tả index 0 là RDN bên phải nhất (dc=org), index tiếp theo là dc=example, rồi ou=people, cuối cùng mới tới uid=lan.

Vì vậy, đoạn code:

~~~java
LdapName dn = new LdapName("dc=example,dc=org");
dn.add(new Rdn("ou", "people"));
dn.add(new Rdn("uid", "lan"));
~~~

tạo DN có biểu diễn:

~~~text
uid=lan,ou=people,dc=example,dc=org
~~~

Khi thao tác add, remove, getRdn hoặc getPrefix, hãy nhớ thứ tự index nội bộ này. Tham khảo [JDK LdapName class description](https://docs.oracle.com/en/java/javase/26/docs/api/java.naming/javax/naming/ldap/LdapName.html).

## 13. Kiểm tra DN có nằm dưới base DN hay không

Một use case thường gặp là kiểm tra entry có nằm trong naming context mà service được phép truy cập không.

Ví dụ:

~~~text
Entry DN:
uid=lan,ou=people,dc=example,dc=org

Base DN:
dc=example,dc=org
~~~

Trong chuỗi hiển thị, base DN là phần hậu tố bên phải. Tuy nhiên LdapName lưu/index RDN từ phải sang trái; vì thế startsWith() có thể được dùng để kiểm tra base suffix theo cấu trúc Name.

~~~java
import javax.naming.ldap.LdapName;

public static boolean isUnderBase(
        LdapName entryDn,
        LdapName baseDn) {

    return entryDn.startsWith(baseDn);
}
~~~

Ví dụ:

~~~java
LdapName entry = new LdapName(
    "uid=lan,ou=people,dc=example,dc=org"
);

LdapName base = new LdapName(
    "dc=example,dc=org"
);

System.out.println(entry.startsWith(base)); // true
~~~

Điều này có thể gây bất ngờ vì người đọc thấy base nằm ở bên phải chuỗi. JDK đánh số RDN bên phải nhất tại index 0; startsWith kiểm tra prefix của chuỗi component nội bộ. Xem [LdapName startsWith API](https://docs.oracle.com/en/java/javase/17/docs/api/java.naming/javax/naming/ldap/LdapName.html#startsWith(javax.naming.Name)).

### 13.1. Tránh kiểm tra base bằng String.endsWith

Không dùng:

~~~java
boolean allowed = entryDnText.endsWith(baseDnText);
~~~

Vì phép so sánh chuỗi không hiểu escaping, case, AVA hoặc ranh giới RDN. Ví dụ một giá trị CN có chứa text giống base DN có thể làm kiểm tra chuỗi trở nên khó tin cậy. Parse cả hai DN rồi so sánh cấu trúc.

**Lưu ý bảo mật:** kiểm tra suffix bằng LdapName.startsWith() chỉ là kiểm tra cấu trúc theo semantics JNDI. Nếu hệ thống dựa vào schema-specific matching rule, alias attribute type hoặc các attribute value đặc biệt, hãy bổ sung kiểm chứng theo directory schema và server. Không coi một phép so sánh cục bộ là authorization hoàn chỉnh nếu DN đến từ caller không đáng tin cậy.

## 14. Đọc các RDN từ LdapName

Có thể duyệt từng thành phần:

~~~java
LdapName dn = new LdapName(
    "uid=lan,ou=people,dc=example,dc=org"
);

System.out.println("RDN count: " + dn.size());

for (int i = 0; i < dn.size(); i++) {
    System.out.println(i + " -> " + dn.getRdn(i));
}
~~~

Theo cách đánh số của JDK, thứ tự in ra là từ root về leaf:

~~~text
0 -> dc=org
1 -> dc=example
2 -> ou=people
3 -> uid=lan
~~~

getRdn(size() - 1) trả RDN bên trái nhất, thường là RDN định danh entry. getRdn(0) trả RDN bên phải nhất, gần root hơn.

### 14.1. Đọc AVA từ một RDN

~~~java
import javax.naming.ldap.LdapName;
import javax.naming.ldap.Rdn;

LdapName dn = new LdapName(
    "cn=Lan Nguyen+uid=lan,ou=people,dc=example,dc=org"
);

Rdn leaf = dn.getRdn(dn.size() - 1);

System.out.println("AVA count: " + leaf.size());
System.out.println(leaf.toAttributes());
~~~

Với multi-valued RDN, getType() và getValue() là tiện ích cho một AVA trong RDN. Nếu RDN có nhiều AVA, không giả định method đó đại diện cho toàn bộ RDN. Dùng toAttributes() để xem toàn bộ các mapping type/value.

## 15. Không tự chuẩn hóa toàn bộ DN bằng lowercase

Vì sao đoạn code sau nguy hiểm?

~~~java
String key = dn.toLowerCase();
~~~

Một số vấn đề:

1. Làm thay đổi giá trị AVA dù matching rule của attribute có thể phân biệt hoa thường.
2. Không parse được dấu phẩy/dấu cộng đã escape.
3. Không giải mã escape hex.
4. Không nhận biết nhiều AVA trong một RDN.
5. Không biết attribute descriptor có alias/schema mapping ra sao.
6. Không áp dụng đúng Unicode preparation/matching rule.
7. Không giải quyết thứ tự RDN sai.
8. Không tạo canonical representation theo RFC 4514.

Tương tự, các thao tác sau cũng không phải canonicalization hợp lệ:

- trim toàn bộ chuỗi.
- Xóa mọi dấu cách.
- Thay nhiều dấu cách thành một.
- Sort tất cả RDN theo alphabet.
- Sort mọi phần tử sau khi split theo dấu phẩy.
- Chuyển dấu escape hex thành ký tự bằng regex.
- Unicode normalize tất cả AVA bằng một quy tắc chung.
- Chuyển attribute type từ descriptor sang OID theo một bảng tự viết không đồng bộ với schema.

Nếu mục tiêu chỉ là phát hiện hai chuỗi có thể biểu diễn cùng DN theo semantics JNDI, parse bằng LdapName rồi so sánh. Nếu mục tiêu là matching theo schema, hãy dùng matching rule server hoặc comparator có schema cụ thể.

## 16. DN và định danh bền vững: entry có thể đổi tên

DN định danh vị trí entry trong cây directory. Nếu entry được rename hoặc move sang OU khác, DN thay đổi:

~~~text
Trước:
uid=lan,ou=people,dc=example,dc=org

Sau:
uid=lan,ou=engineering,dc=example,dc=org
~~~

Entry có thể vẫn là cùng một đối tượng nghiệp vụ, nhưng DN mới khác DN cũ. Một ứng dụng lưu DN làm khóa chính bên ngoài có thể giữ lại tham chiếu cũ sau khi entry được move.

RFC 4530 định nghĩa operational attribute entryUUID: UUID do server gán cho entry, bất biến trong vòng đời entry theo đặc tả và có thể giúp nhận diện entry sau khi rename. Mức hỗ trợ attribute này phụ thuộc directory server. Xem [RFC 4530 — entryUUID](https://www.rfc-editor.org/rfc/rfc4530).

Trong Microsoft Active Directory, hệ thống có thể dùng objectGUID như định danh ổn định theo semantics riêng của AD. Hãy dùng identifier mà directory thực tế hỗ trợ và bảo đảm quyền đọc phù hợp.

| Giá trị | Vai trò | Có thể thay đổi khi rename/move? |
|---|---|---|
| DN | Địa chỉ/định danh entry trong cây | Có |
| RDN | Thành phần tên ở cấp entry | Có |
| entryUUID | UUID do server gán theo RFC 4530 | Không theo đặc tả entryUUID |
| objectGUID | Identifier đặc thù Active Directory | Theo semantics của AD |
| UID/email | Thuộc tính nghiệp vụ | Có thể thay đổi theo chính sách tổ chức |

Không suy luận UID hay email luôn bất biến. Nếu ứng dụng cần khóa liên kết lâu dài, hãy chọn immutable identifier phù hợp với directory và nghiệp vụ.

## 17. Dùng DN trong Spring LDAP

Spring LDAP dùng kiểu Name/LdapName cho các thao tác directory. Có thể parse DN thành LdapName trước khi gọi template.

~~~java
import javax.naming.ldap.LdapName;

import org.springframework.ldap.core.LdapTemplate;
import org.springframework.stereotype.Service;

@Service
public class PersonLookupService {

    private final LdapTemplate ldapTemplate;

    public PersonLookupService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public PersonEntry lookupKnownPerson() throws Exception {
        LdapName relativeDn = new LdapName(
            "uid=lan,ou=people"
        );

        return ldapTemplate.lookup(
            relativeDn,
            new PersonAttributesMapper()
        );
    }
}
~~~

Ví dụ giả định ContextSource.base đã cấu hình dc=example,dc=org, nên DN truyền vào là tương đối. Nếu ContextSource.base rỗng, cần truyền DN đầy đủ phù hợp với directory root. Spring LDAP mô tả rằng các DN đưa vào/nhận về operation sẽ tương đối với base DN nếu base được cấu hình. Xem [Spring LDAP configuration](https://docs.spring.io/spring-ldap/reference/configuration.html).

PersonEntry và PersonAttributesMapper là class minh họa của ứng dụng. Đoạn code chỉ cho thấy cách truyền LdapName làm DN; mapper phải đọc attribute theo schema của directory.

### 17.1. Đừng dùng String compare cho DN nhận từ repository

Nếu entity ODM có trường:

~~~java
@Id
private Name dn;
~~~

hãy giữ kiểu Name/LdapName xuyên suốt tầng xử lý khi phù hợp. Không chuyển sang String rồi so sánh equalsIgnoreCase() hoặc lowercase trước khi quyết định cùng entry.

Khi serialize ra JSON/API, có thể xuất DN string theo RFC 4514 để hiển thị hoặc truyền tải. Khi nhận lại, parse thành LdapName, kiểm tra quyền và naming context; không dùng raw string như bằng chứng caller có quyền truy cập entry.

## 18. LdapName mutable: cẩn thận khi dùng làm Map key

LdapName có các method thay đổi cấu trúc như add() và remove(). Nó không phải immutable value object.

Không nên:

~~~java
Map<LdapName, PersonEntry> people = new HashMap<>();

LdapName dn = new LdapName(
    "uid=lan,ou=people,dc=example,dc=org"
);

people.put(dn, person);

dn.remove(dn.size() - 1);

// Hash/equality của key đã thay đổi sau khi put.
~~~

Nếu key thay đổi sau khi đưa vào HashMap hoặc HashSet, cấu trúc hash có thể không tìm thấy key ở bucket cũ.

Cách an toàn:

- Không mutate LdapName sau khi dùng làm key.
- Tạo bản copy trước khi chỉnh sửa.
- Giữ LdapName trong một wrapper immutable của ứng dụng.
- Nếu dùng String làm key lưu trữ, phải xác định rõ đó là representation string phục vụ serialization hay một canonical key do ứng dụng định nghĩa; không gọi nó là canonical DN theo RFC 4514.

Ví dụ clone trước khi thêm RDN:

~~~java
LdapName original = new LdapName(
    "uid=lan,ou=people,dc=example,dc=org"
);

LdapName modified = (LdapName) original.clone();
modified.add(new Rdn("ou", "archive"));
~~~

original không bị thay đổi khi modified được chỉnh sửa.

## 19. DN escaping khác LDAP filter escaping

Hai chuẩn thường bị nhầm:

| Chuẩn | Dùng cho | Ví dụ |
|---|---|---|
| RFC 4514 | Biểu diễn/parse DN | cn=Smith\, Alice,ou=people |
| RFC 4515 | Biểu diễn LDAP search filter | (cn=Smith\2c Alice) |

Một giá trị DN được nhúng vào filter phải trải qua hai lớp:

1. Xây dựng DN hợp lệ theo RFC 4514.
2. Escape toàn bộ DN string như một assertion value trong filter theo RFC 4515.

Ví dụ filter tìm group có member bằng DN của Lan:

~~~java
import org.springframework.ldap.query.LdapQuery;

import static org.springframework.ldap.query.LdapQueryBuilder.query;

String memberDn = personDn.toString();

// Dùng API query builder để encode assertion value.
LdapQuery query = query()
    .base("ou=groups")
    .where("member").is(memberDn);
~~~

Không dùng Rdn.escapeValue() để escape filter. Hàm đó escape giá trị của RDN theo cú pháp DN, không phải cú pháp filter.

Không ghép filter thủ công:

~~~java
String filter =
    "(member=" + personDn.toString() + ")";
~~~

Nếu DN chứa dấu ngoặc, dấu sao hoặc backslash, raw concatenation có thể làm sai cú pháp filter hoặc mở ra LDAP injection. Dùng LdapQueryBuilder hoặc API filter encoder phù hợp. Xem [RFC 4515 — LDAP Filter String Representation](https://www.rfc-editor.org/rfc/rfc4515).

## 20. Không dùng DN tùy ý từ client để kiểm tra quyền

Một API có thể nhận request:

~~~json
{
  "dn": "uid=lan,ou=people,dc=example,dc=org"
}
~~~

Parse thành LdapName giúp xác nhận cú pháp có thể đọc được, nhưng không chứng minh:

- Entry tồn tại.
- Caller được phép đọc hoặc sửa entry.
- DN thuộc tenant của caller.
- DN nằm trong base DN mà service được phép thao tác.
- Attribute type/value tuân theo schema server.
- DN không trỏ tới một entry khác sau rename/delete/recreate.

Quy trình an toàn:

1. Xác thực caller.
2. Xác định tenant/OU từ identity và policy server-side.
3. Parse DN bằng LdapName.
4. Kiểm tra DN nằm dưới base được phép theo cấu trúc.
5. Kiểm tra authorization theo domain policy.
6. Thực hiện lookup/search bằng service account least-privilege.
7. Không coi LdapName.equals() là cơ chế authorization duy nhất.

DN có thể chứa thông tin nhận dạng cá nhân như tên, email hoặc vị trí tổ chức. Không ghi toàn bộ DN ra log công khai nếu không cần thiết.

## 21. Unit test cho DN equality và cấu trúc

Các test nên bao phủ ít nhất:

- Hai chuỗi có khác biệt về hoa/thường và dấu cách.
- Escape ký tự và escape hex tương đương.
- Multi-valued RDN có thứ tự AVA khác nhau.
- Thứ tự RDN khác nhau.
- Base DN khác nhau.
- DN có giá trị chứa dấu phẩy.
- DN Unicode.
- DN sai cú pháp.
- Phân biệt LdapName.equals() với matching rule schema-specific.

Ví dụ JUnit 5:

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import javax.naming.InvalidNameException;
import javax.naming.ldap.LdapName;

import org.junit.jupiter.api.Test;

class DnComparisonTest {

    @Test
    void equivalentRepresentationsCompareEqualInJndi() throws Exception {
        LdapName first = new LdapName(
            "CN=Lan Nguyen,OU=People,DC=example,DC=org"
        );

        LdapName second = new LdapName(
            "cn=Lan Nguyen, ou=People, dc=example, dc=org"
        );

        assertThat(first).isEqualTo(second);
    }

    @Test
    void escapedCommaAndHexEscapeCompareEqualInJndi()
            throws Exception {
        LdapName first = new LdapName(
            "cn=Smith\\, Alice,ou=people,dc=example,dc=org"
        );

        LdapName second = new LdapName(
            "cn=Smith\\2C Alice,ou=people,dc=example,dc=org"
        );

        assertThat(first).isEqualTo(second);
    }

    @Test
    void avaOrderWithinMultiValuedRdnDoesNotMatter()
            throws Exception {
        LdapName first = new LdapName(
            "cn=Lan Nguyen+uid=lan,ou=people,dc=example,dc=org"
        );

        LdapName second = new LdapName(
            "uid=lan+cn=Lan Nguyen,ou=people,dc=example,dc=org"
        );

        assertThat(first).isEqualTo(second);
    }

    @Test
    void rdnSequenceOrderStillMatters() throws Exception {
        LdapName first = new LdapName(
            "uid=lan,ou=people,dc=example,dc=org"
        );

        LdapName second = new LdapName(
            "ou=people,uid=lan,dc=example,dc=org"
        );

        assertThat(first).isNotEqualTo(second);
    }

    @Test
    void parentDnIsCheckedStructurally() throws Exception {
        LdapName entry = new LdapName(
            "uid=lan,ou=people,dc=example,dc=org"
        );

        LdapName base = new LdapName(
            "dc=example,dc=org"
        );

        assertThat(entry.startsWith(base)).isTrue();
    }

    @Test
    void malformedDnIsRejectedWhenParserDetectsSyntaxError() {
        assertThatThrownBy(() ->
            new LdapName("uid")
        ).isInstanceOf(InvalidNameException.class);
    }
}
~~~

Các test trên kiểm tra semantics của JNDI parser. Chúng không thay thế test với LDAP server để xác nhận matching rule/schema thực tế.

### 21.1. Test khác biệt giữa JNDI và matching rule schema

Nếu schema có attribute custom với equality matching rule phân biệt hoa thường, hãy tạo integration test với server test đúng schema:

- Thêm một entry hoặc attribute DN value dùng attribute type đó.
- So sánh bằng Java LdapName.equals().
- Dùng LDAP Search filter có equality assertion theo schema server.
- Quan sát kết quả hai phía.
- Ghi rõ comparator nào là nguồn sự thật trong ứng dụng.

Không dùng mock để giả định matching rule server; mock chỉ xác minh code gọi đúng API.

## 22. Integration test với LDAP directory

Một integration test hữu ích có thể xác minh:

1. Entry Lan tồn tại tại DN dự kiến.
2. LdapTemplate.lookup(Name, mapper) đọc được entry.
3. Một filter có thuộc tính DN như member so sánh assertion theo matching rule của schema.
4. Sau khi rename entry, DN mới lookup được và DN cũ không còn là địa chỉ hiện tại.
5. Nếu server cung cấp entryUUID, giá trị này vẫn giữ nguyên qua rename theo đặc tả RFC 4530.

Khi đọc entryUUID, yêu cầu rõ operational attribute này trong projection/query và xác minh bind account được phép đọc. Operational attributes thường không nằm trong danh sách user attributes mặc định mà client lấy về.

Ví dụ logic kiểm tra:

~~~java
@Test
void entryIdentityAndDnLocationAreDifferentConcepts() {
    PersonSnapshot before = directoryReader.readByDn(
        "uid=lan,ou=people,dc=example,dc=org"
    );

    directoryWriter.rename(
        before.dn(),
        "uid=lan,ou=engineering,dc=example,dc=org"
    );

    PersonSnapshot after = directoryReader.readByDn(
        "uid=lan,ou=engineering,dc=example,dc=org"
    );

    assertThat(after.entryUuid()).isEqualTo(before.entryUuid());
}
~~~

PersonSnapshot, directoryReader và directoryWriter là abstraction của ứng dụng. Test cần dùng LDAP server hỗ trợ entryUUID, quyền rename phù hợp và fixture không có DN đích trùng. Không giả định mọi directory server đều hỗ trợ attribute operational này.

## 23. Các lỗi thường gặp khi so sánh DN

| Cách làm | Vấn đề | Cách sửa |
|---|---|---|
| String.equals() | Không nhận biết biểu diễn tương đương | Parse thành LdapName |
| equalsIgnoreCase() | Vẫn chỉ so sánh text; không hiểu escape/RDN | Dùng parser DN |
| toLowerCase() toàn bộ DN | Làm thay đổi giá trị theo matching rule không đồng nhất | Không lowercase chuỗi DN |
| split(",") | Hỏng khi giá trị có dấu phẩy escape | Dùng LdapName |
| Sort mọi RDN | Phá thứ tự cây DN | Giữ nguyên RDN sequence |
| Sort AVA bằng chuỗi | Có thể sai khi value escape hoặc type mapping | Dùng Rdn equality |
| Tự xóa backslash | Làm thay đổi giá trị AVA | Dùng parser/escape API |
| Dùng Rdn.escapeValue cho filter | Nhầm RFC 4514 với RFC 4515 | Dùng filter builder |
| Coi LdapName.equals là schema-aware | Bỏ qua matching rule cụ thể của attribute type | Dùng server matching rule hoặc comparator schema-aware |
| Lưu DN làm primary key bất biến | DN thay đổi khi rename/move | Dùng immutable identifier như entryUUID nếu được hỗ trợ |
| Tin rằng parse thành công nghĩa DN tồn tại | Parser không truy cập server | Lookup/search để xác minh entry |
| Dùng DN từ client để phân quyền | DN hợp lệ không đồng nghĩa caller được phép | Authorization server-side |

## 24. Hướng dẫn thiết kế comparator trong ứng dụng

Trước khi viết comparator, hãy xác định yêu cầu chính xác:

| Nhu cầu | Công cụ/phương pháp |
|---|---|
| Kiểm tra hai chuỗi có parse được thành DN không | new LdapName(String) |
| So sánh theo semantics JNDI | LdapName.equals() |
| Kiểm tra DN có thuộc base DN theo cấu trúc Name | entryDn.startsWith(baseDn) |
| Tạo RDN có ký tự đặc biệt | new Rdn(type, literalValue) |
| Xây dựng DN động | LdapName.add(Rdn) hoặc Spring LDAP name builder phù hợp version |
| So sánh DN-valued attribute theo schema | Để LDAP server áp dụng equality matching rule |
| Nhận diện cùng entry sau rename | entryUUID hoặc immutable ID do directory cung cấp |
| Authorization theo tenant/OU | Parse DN, kiểm tra base và áp dụng policy caller/server-side |

### 24.1. Một wrapper rõ ràng hơn cho domain code

Nếu ứng dụng cần phân biệt comparator JNDI và matching theo server, đặt tên method để nói rõ semantics:

~~~java
public final class DirectoryDn {

    private final LdapName value;

    public DirectoryDn(String text) throws InvalidNameException {
        this.value = new LdapName(text);
    }

    public boolean sameJndiName(DirectoryDn other) {
        return value.equals(other.value);
    }

    public boolean isUnderBase(DirectoryDn base) {
        return value.startsWith(base.value);
    }

    public LdapName asLdapName() {
        return (LdapName) value.clone();
    }

    @Override
    public String toString() {
        return value.toString();
    }
}
~~~

Tên sameJndiName làm rõ đây là equality theo JNDI. Không đặt tên chung như isSameEntry nếu method chưa kiểm tra schema/server/immutable identity.

Trong ứng dụng lớn, wrapper có thể giữ immutable identifier và DN location riêng biệt, tránh nhầm một địa chỉ có thể thay đổi với một định danh nghiệp vụ ổn định.

## 25. Bài tập thực hành

### Bài 1 — Biểu diễn khác nhau

Cho hai DN:

~~~text
CN=Smith\, Alice,OU=People,DC=example,DC=org
cn=Smith\2C Alice, ou=People, dc=example, dc=org
~~~

Giải thích vì sao string equality trả false, parser DN có thể coi hai representation tương đương và những yếu tố nào ảnh hưởng kết quả JNDI.

### Bài 2 — Thứ tự RDN

So sánh:

~~~text
uid=lan,ou=people,dc=example,dc=org
ou=people,uid=lan,dc=example,dc=org
~~~

Vẽ cây directory tương ứng và giải thích vì sao không được sort RDN trước khi so sánh.

### Bài 3 — Multi-valued RDN

Hai DN có RDN đầu tiên:

~~~text
cn=Lan+uid=lan
uid=lan+cn=Lan
~~~

Giải thích vì sao thứ tự AVA trong RDN không có ý nghĩa, trong khi thứ tự RDN của toàn DN vẫn quan trọng.

### Bài 4 — Case sensitivity và schema

Một custom attribute dùng caseExactMatch. Hai DN khác nhau ở giá trị chữ hoa/chữ thường. So sánh kết quả dự kiến theo matching rule server với LdapName.equals(). Tại sao không nên xem hai phép so sánh là một?

### Bài 5 — Base DN

Viết code dùng LdapName.startsWith() để kiểm tra:

~~~text
uid=lan,ou=people,dc=example,dc=org
~~~

có nằm dưới:

~~~text
dc=example,dc=org
~~~

Giải thích vì sao startsWith hoạt động dù base nằm ở bên phải chuỗi DN hiển thị.

### Bài 6 — Escape DN

Tạo RDN cn có giá trị Smith, Alice bằng new Rdn("cn", value). In DN đầy đủ và giải thích vì sao không nối chuỗi trực tiếp.

### Bài 7 — Escape filter

Viết truy vấn tìm group có member bằng DN chứa dấu phẩy trong CN. Dùng LdapQueryBuilder và giải thích vì sao DN escaping không thay thế filter escaping.

### Bài 8 — DN thay đổi sau rename

Một người được chuyển từ OU people sang OU engineering. DN thay đổi nhưng entryUUID giữ nguyên theo RFC 4530. Thiết kế cache key và API identifier phù hợp.

### Bài 9 — Mutable Name trong HashMap

Một LdapName được thêm vào HashMap, sau đó bị add() hoặc remove(). Giải thích vì sao lookup có thể hỏng và cách tạo snapshot trước khi dùng làm key.

### Bài 10 — Integration test

Tạo LDAP fixture có hai OU và một entry. Kiểm tra:

- DN trước rename lookup thành công.
- Rename sang OU mới thành công.
- DN cũ không còn là địa chỉ hiện tại.
- DN mới trỏ tới entry.
- entryUUID không đổi nếu server hỗ trợ.

## 26. Checklist khi xử lý DN trong production

| Câu hỏi | Tiêu chí |
|---|---|
| Đã parse DN thành cấu trúc? | Dùng LdapName, không split chuỗi |
| Thứ tự RDN được giữ nguyên? | Không sort RDN |
| Multi-valued RDN được xử lý? | So sánh AVA theo type/value, không phụ thuộc thứ tự text |
| Escape được xử lý đúng? | Dùng parser/builder, không replace regex |
| Matching rule đã rõ? | Kiểm tra schema của từng attribute type |
| Có nhầm JNDI equals với server matching? | Nêu rõ semantics comparator |
| Base DN kiểm tra theo cấu trúc? | Dùng startsWith và test orientation |
| DN có đến từ caller không tin cậy? | Parse, validate base và authorization |
| Filter dùng DN làm assertion? | Escape theo RFC 4515 qua builder |
| DN được lưu làm primary key? | Đánh giá immutable ID như entryUUID |
| LdapName có bị mutate sau khi dùng làm key? | Không mutate hoặc clone |
| Có test escape/Unicode/multi-valued? | Unit test và integration test |
| Có test rename/move? | Xác minh DN mới và identity ổn định |
| Log có lộ thông tin nhạy cảm? | Mask DN/PII khi cần |

## 27. Kết luận và tài liệu tham khảo

So sánh DN đúng nghĩa bắt đầu từ việc **parse chuỗi thành cấu trúc**. DN là chuỗi RDN có thứ tự; mỗi RDN chứa một hoặc nhiều AVA, và thứ tự AVA trong cùng RDN không quan trọng. Escape, Unicode và cách viết attribute type có thể tạo ra nhiều representation cho cùng một cấu trúc. RFC 4514 không định nghĩa một chuỗi canonical duy nhất; equality theo LDAP được mô tả bởi distinguishedNameMatch trong RFC 4517, với giá trị AVA so sánh theo matching rule của từng attribute type.

Trong Java, LdapName và Rdn giúp parse, xây dựng, kiểm tra suffix/base và so sánh theo semantics JNDI. Tuy nhiên, LdapName.equals() không thay thế đầy đủ matching rule schema-specific của LDAP server. Đặt tên comparator rõ ràng, để server xử lý DN-valued attribute khi cần matching có thẩm quyền, và dùng immutable identifier như entryUUID khi cần nhận diện entry qua rename. Tránh lowercase, trim, split hoặc sort chuỗi DN tùy ý.

Tài liệu chính thức:

- [RFC 4514 — LDAP String Representation of Distinguished Names](https://www.rfc-editor.org/rfc/rfc4514)
- [RFC 4517 — LDAP Syntaxes and Matching Rules, distinguishedNameMatch](https://www.rfc-editor.org/rfc/rfc4517)
- [RFC 4515 — LDAP Filter String Representation](https://www.rfc-editor.org/rfc/rfc4515)
- [RFC 4530 — LDAP entryUUID Operational Attribute](https://www.rfc-editor.org/rfc/rfc4530)
- [Java SE 17 — LdapName API](https://docs.oracle.com/en/java/javase/17/docs/api/java.naming/javax/naming/ldap/LdapName.html)
- [Java SE 17 — Rdn API](https://docs.oracle.com/en/java/javase/17/docs/api/java.naming/javax/naming/ldap/Rdn.html)
- [Spring LDAP — Configuration and ContextSource base DN](https://docs.spring.io/spring-ldap/reference/configuration.html)
- [Spring LDAP — DistinguishedName deprecated API](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/DistinguishedName.html)
- [Spring Data LDAP — Reference](https://docs.spring.io/spring-data/ldap/reference/)
