# Phân biệt dấu phẩy phân cách RDN với ký tự trong giá trị

Trong LDAP, một dấu phẩy (",") có thể mang **hai ý nghĩa hoàn toàn khác nhau**: ngăn cách hai thành phần của Distinguished Name (DN), hoặc là ký tự thực sự nằm trong giá trị của một thuộc tính đặt tên. Phân biệt đúng hai trường hợp này là điều kiện cần để Spring LDAP tìm đúng entry, dựng DN an toàn và tránh lỗi khi dữ liệu có tên người, tên nhóm hoặc tên tổ chức chứa dấu phẩy.

Bài học thuộc chương **DN và Name** của **SPRING_LDAP**. Các ví dụ dùng thư mục giả định có gốc `dc=example,dc=org`, minh họa bằng cú pháp DN chuẩn, LDIF, Java JNDI và `LdapNameBuilder`/`LdapTemplate` của Spring LDAP.

Sau khi học, bạn có thể:

- Nhận ra dấu phẩy nào là ký tự **phân cách RDN**, dấu phẩy nào thuộc **giá trị RDN**.
- Đọc đúng DN chứa ký tự đặc biệt, kể cả RDN có nhiều cặp thuộc tính–giá trị.
- Phân tích và tạo DN bằng thư viện thay vì tách/ghép chuỗi thủ công.
- Phân biệt cú pháp escape của **DN** với cú pháp escape của **LDAP search filter**.

## 1. Vì sao một dấu phẩy có thể làm sai toàn bộ DN?

Xét DN của entry người dùng:

```text
cn=Nguyen\, Lan,ou=people,dc=example,dc=org
```

Có **bốn RDN**, theo thứ tự hiển thị từ entry lên gốc:

```text
cn=Nguyen\, Lan   ,   ou=people   ,   dc=example   ,   dc=org
└──── RDN 1 ────┘     └─ RDN 2 ─┘     └─ RDN 3 ─┘     └ RDN 4 ┘
```

- Dấu phẩy trong `Nguyen\, Lan` được **escape** bằng dấu gạch chéo ngược (`\`), nên nó là **một phần của giá trị `cn`**: `Nguyen, Lan`.
- Ba dấu phẩy còn lại **không được escape**, nên chúng **phân cách bốn RDN** của DN.

Nếu bỏ dấu `\`:

```text
cn=Nguyen, Lan,ou=people,dc=example,dc=org
```

dấu phẩy sau `Nguyen` trở thành dấu phân cách. Phần `Lan` lúc đó bị xem như một RDN độc lập nhưng thiếu `attributeType=...`, khiến DN không hợp lệ theo cú pháp chuẩn. Đó không còn là DN của entry có `cn` bằng `Nguyen, Lan`.

**Nguyên tắc cốt lõi:** một dấu phẩy là ký tự phân cách RDN khi nó đứng ở vị trí phân cách **theo cú pháp DN**; dấu phẩy thuộc giá trị phải được **escape**. Không thể xác định đúng chỉ bằng cách đếm ký tự dấu phẩy trong chuỗi.

## 2. DN, RDN và giá trị thuộc tính liên hệ với nhau thế nào?

**DN (Distinguished Name)** định danh vị trí của một entry trong cây LDAP. Trong chuỗi biểu diễn DN theo [RFC 4514](https://www.rfc-editor.org/rfc/rfc4514), các RDN được viết theo thứ tự từ **entry đến phía gốc**.

**RDN (Relative Distinguished Name)** đặt tên entry trong phạm vi các entry cùng cha. Với RDN đơn trị, cú pháp thường gặp là `attributeType=value`; ví dụ `cn=Nguyen\, Lan`.

**Giá trị thuộc tính** là dữ liệu thực tế, chẳng hạn tên `Nguyen, Lan`. Escape chỉ thuộc **cách biểu diễn tên bằng chuỗi**; khi LDAP trả về giá trị `cn`, giá trị vẫn là `Nguyen, Lan`, không có dấu `\`.

| Nội dung | Ví dụ | Cách hiểu |
| --- | --- | --- |
| Giá trị `cn` | `Nguyen, Lan` | Dữ liệu chứa một dấu phẩy. |
| RDN | `cn=Nguyen\, Lan` | Dấu phẩy nằm trong giá trị `cn`. |
| DN đầy đủ | `cn=Nguyen\, Lan,ou=people,dc=example,dc=org` | RDN đầu tiên là `cn=Nguyen\, Lan`; các RDN sau xác định nhánh cha. |
| DN cha | `ou=people,dc=example,dc=org` | Lấy đi toàn bộ RDN đầu tiên. |

Cấu trúc cây tương ứng:

```text
dc=example,dc=org
└── ou=people
    └── cn=Nguyen, Lan   ← Tên giá trị được hiển thị cho người đọc
```

Trong cây, tên hiển thị có dấu phẩy bình thường. Chỉ khi chuyển tên đó sang **chuỗi DN**, dấu phẩy trong giá trị mới phải được escape.

## 3. Quy tắc escape dấu phẩy trong DN

RFC 4514 cho phép hai cách biểu diễn dấu phẩy thuộc một giá trị RDN:

| Chuỗi DN | Giá trị `cn` sau khi giải mã | Ý nghĩa |
| --- | --- | --- |
| `cn=Nguyen\, Lan,ou=people` | `Nguyen, Lan` | `\,` biểu diễn dấu phẩy thuộc giá trị. |
| `cn=Nguyen\2C Lan,ou=people` | `Nguyen, Lan` | `\2C` biểu diễn octet có mã hex `2C`, tương ứng dấu phẩy ASCII. |
| `cn=Nguyen,ou=people` | `Nguyen` | Dấu phẩy phân cách hai RDN. |
| `cn=Nguyen, Lan,ou=people` | Không phân tích hợp lệ theo RFC 4514 | `Lan` bị hiểu thành RDN riêng không có dấu `=`. |

Hai cách `\,` và `\2C` cùng biểu diễn dấu phẩy trong **giá trị**, dù chuỗi ký tự đầu vào không giống nhau. Trong thực tế, `\,` thường dễ đọc hơn khi nhập tay. Cú pháp `\HH` sử dụng hai chữ số hex để mô tả **một octet**, nên ký tự Unicode nhiều byte có thể cần nhiều cặp `\HH` nếu muốn mã hóa toàn bộ bằng hex.

### Dấu gạch chéo ngược cũng có thể là dữ liệu

Không phải cứ thấy dấu `\` trước một dấu phẩy là đủ kết luận dấu phẩy đã được escape. Dấu `\` có thể tự được escape bằng `\\`.

```text
cn=Lab\,Ops,ou=teams,dc=example,dc=org
cn=Lab\\,ou=teams,dc=example,dc=org
```

Ở dòng thứ nhất, giá trị `cn` là `Lab,Ops`, có dấu phẩy nội bộ. Ở dòng thứ hai, giá trị `cn` là `Lab\` (kết thúc bằng một dấu gạch chéo ngược), còn dấu phẩy sau `\\` **phân cách RDN**. Vì thế, các biểu thức đơn giản như `split(",")` hoặc quy tắc “dấu phẩy ngay sau backslash luôn thuộc giá trị” đều dễ sai.

### Những ký tự đặc biệt khác cần lưu ý

Dấu phẩy không phải ký tự duy nhất cần escape khi tạo chuỗi DN. Theo RFC 4514, các ký tự như dấu cộng (`+`), dấu nháy kép (`"`), gạch chéo ngược (`\`), dấu chấm phẩy (`;`), dấu bé/lớn (`<`/`>`), dấu bằng (`=`) và ký tự NUL có quy tắc escape. Khoảng trắng **ở đầu hoặc cuối** giá trị, và dấu `#` **ở đầu** giá trị, cũng cần được biểu diễn đúng.

Ví dụ:

```text
cn=Team\+Platform,ou=groups,dc=example,dc=org
cn=\ Lan,ou=people,dc=example,dc=org
cn=Lan\ ,ou=people,dc=example,dc=org
cn=\#support,ou=groups,dc=example,dc=org
```

Lần lượt, `cn` nhận các giá trị `Team+Platform`, ` Lan` (có khoảng trắng đầu), `Lan ` (có khoảng trắng cuối) và `#support`. Thay vì nhớ và thay thế thủ công mọi trường hợp, ứng dụng nên nhờ bộ dựng DN thực hiện escape.

## 4. Đừng nhầm dấu phẩy với dấu cộng trong RDN đa trị

Một RDN có thể gồm **nhiều** cặp thuộc tính–giá trị (Attribute Value Assertion, AVA). Trong chuỗi DN, dấu cộng `+` nối các AVA thuộc **cùng một RDN**; dấu phẩy không được escape mới tách **hai RDN khác nhau**.

```text
cn=Nguyen\, Lan+uid=nlan,ou=people,dc=example,dc=org
└───────── một RDN ─────────┘└─ RDN ─┘└─ RDN ───┘└ RDN ┘
```

RDN đầu tiên gồm hai AVA:

- `cn=Nguyen\, Lan` → `cn` có giá trị `Nguyen, Lan`.
- `uid=nlan` → `uid` có giá trị `nlan`.

Dấu `+` giữa hai AVA là **toán tử cú pháp**; dấu phẩy sau `Lan` là **dữ liệu**; dấu phẩy sau `nlan` là **dấu phân cách RDN**. Nếu giá trị `cn` thật sự chứa dấu cộng, phải biểu diễn thành `cn=Team\+Platform`.

RDN đa trị không phổ biến bằng RDN một AVA, nhưng nó cho thấy lý do nên dùng parser DN chuẩn: parser phân biệt được tầng DN, RDN và AVA.

## 5. Đối chiếu cách viết trong LDIF với giá trị thuộc tính

Cho entry người dùng với tên có dấu phẩy:

```ldif
dn: cn=Nguyen\, Lan,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
cn: Nguyen, Lan
sn: Nguyen
```

Hai dòng có cách viết khác nhau là **đúng chủ ý**:

- `dn: cn=Nguyen\, Lan,...` chứa **chuỗi DN**; dấu phẩy trong `cn` phải được escape để không bị hiểu thành dấu phân cách RDN.
- `cn: Nguyen, Lan` là **giá trị thuộc tính trong LDIF**; dấu phẩy không phải dấu phân cách RDN ở đây, nên không cần viết `\,`.

Nếu nhập nhầm `cn: Nguyen\, Lan`, một trình nhập LDIF có thể hiểu đó là **giá trị chứa cả ký tự backslash** thay vì tên `Nguyen, Lan`. Đừng áp dụng quy tắc escape của chuỗi DN trực tiếp lên tất cả các dòng thuộc tính.

Ví dụ giả định `ou=people,dc=example,dc=org` và các entry cha đã tồn tại. Máy chủ LDAP vẫn sẽ kiểm tra schema, quyền truy cập và các quy tắc đặt tên khi thêm entry.

## 6. Phân tích DN đúng bằng Java JNDI

Java có sẵn `javax.naming.ldap.LdapName` và `javax.naming.ldap.Rdn` để xử lý DN. Chúng giúp nhận diện ký tự phân cách theo cú pháp, thay vì tự tách chuỗi.

```java
import javax.naming.ldap.LdapName;
import javax.naming.ldap.Rdn;

public class DnCommaExample {
    public static void main(String[] args) throws Exception {
        String dnText =
            "cn=Nguyen\\, Lan,ou=people,dc=example,dc=org";

        LdapName dn = new LdapName(dnText);

        // JNDI đánh chỉ số RDN từ phía gốc đến entry.
        Rdn entryRdn = dn.getRdn(dn.size() - 1);

        System.out.println(dn.size());          // 4
        System.out.println(entryRdn.getType()); // cn
        System.out.println(entryRdn.getValue());// Nguyen, Lan
    }
}
```

Cần phân biệt **ba lớp biểu diễn**:

| Lớp | Nội dung |
| --- | --- |
| Giá trị dữ liệu | `Nguyen, Lan` |
| Chuỗi DN theo RFC 4514 | `cn=Nguyen\, Lan,ou=people,dc=example,dc=org` |
| Java string literal chứa chuỗi DN | `"cn=Nguyen\\, Lan,ou=people,dc=example,dc=org"` |

Trong **source Java**, dấu `\` lại là ký tự mở đầu escape sequence của Java, nên phải viết `\\` để tạo ra **một dấu `\` thực sự** trong chuỗi DN tại runtime. Đoạn Java ở trên vì thế có hai dấu backslash liền nhau trước dấu phẩy trong source code.

Thử phân tích chuỗi nhập sai:

```java
// Chuỗi DN không escape dấu phẩy trong giá trị.
String broken = "cn=Nguyen, Lan,ou=people,dc=example,dc=org";

// Phần "Lan" không có dạng attribute=value.
// Theo cú pháp chuẩn, không thể phân tích thành DN mong muốn.
LdapName parsed = new LdapName(broken);
```

Khi nhận dữ liệu từ hệ thống khác, hãy xử lý `InvalidNameException` để phát hiện DN không hợp lệ. Không nên cố sửa bằng cách thay mọi dấu phẩy thành `\,`, vì làm vậy sẽ escape luôn những dấu phẩy **thực sự phân cách RDN**.

## 7. Dựng DN an toàn với Spring LDAP

Khi tên người hoặc nhóm đến từ biểu mẫu/API, bạn nên truyền **giá trị thô** cho bộ dựng DN. Spring LDAP cung cấp `LdapNameBuilder` để tạo đối tượng `Name` đúng cú pháp.

```java
import javax.naming.Name;
import org.springframework.ldap.support.LdapNameBuilder;

String commonName = "Nguyen, Lan";  // Giá trị thực, chưa escape

// Tên tương đối so với ContextSource base dc=example,dc=org.
Name relativeDn = LdapNameBuilder.newInstance()
    .add("ou", "people")
    .add("cn", commonName)
    .build();

System.out.println(relativeDn);
// cn=Nguyen\, Lan,ou=people
```

Trong trường hợp `ContextSource` được cấu hình với base `dc=example,dc=org`, tên tương đối `cn=Nguyen\, Lan,ou=people` tương ứng với DN đầy đủ `cn=Nguyen\, Lan,ou=people,dc=example,dc=org`.

Ví dụ truy cập entry bằng `LdapTemplate` (giả sử `ldapTemplate` đã được inject và kết nối hợp lệ):

```java
import javax.naming.Name;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

String commonName = "Nguyen, Lan";

Name relativeDn = LdapNameBuilder.newInstance()
    .add("ou", "people")
    .add("cn", commonName)
    .build();

String cn = ldapTemplate.lookup(
    relativeDn,
    (AttributesMapper<String>) attributes ->
        (String) attributes.get("cn").get()
);

System.out.println(cn); // Nguyen, Lan
```

Ở đây `lookup` nhận **DN**, không nhận riêng giá trị `cn`. Spring LDAP xử lý DN tương đối theo `ContextSource`. Nếu đã cấu hình base, truyền lặp hậu tố base vào tên tương đối có thể tạo địa chỉ sai.

Nếu đầu vào là `"Lan,ou=admins"`, nối chuỗi tùy ý theo cách `"cn=" + input + ",ou=people"` có thể thay đổi số RDN và ý nghĩa của DN. Với bộ dựng DN, toàn bộ dữ liệu vẫn là **một giá trị `cn`**:

```text
Giá trị đầu vào:  Lan,ou=admins
RDN tạo đúng:   cn=Lan\,ou\=admins
DN tương đối:   cn=Lan\,ou\=admins,ou=people
```

Các ký tự mang ý nghĩa cú pháp trong giá trị được escape, nên chúng không trở thành cấp thư mục hoặc AVA bổ sung. Đây là một lớp bảo vệ khi xây dựng tên; ứng dụng vẫn cần kiểm tra quyền truy cập và phạm vi nhánh LDAP mà tài khoản được phép thao tác.

## 8. Dấu phẩy trong DN không giống dấu phẩy trong search filter

Khi **đã biết DN**, `LdapTemplate.lookup` định vị một entry cụ thể. Khi chỉ biết tên `Nguyen, Lan` và chưa biết DN, bạn thường cần **tìm kiếm theo thuộc tính**.

Ví dụ với `LdapQueryBuilder`:

```java
import java.util.List;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;

String commonName = "Nguyen, Lan";

LdapQuery query = LdapQueryBuilder.query()
    .base("ou=people")
    .where("cn").is(commonName);

List<String> matchingNames = ldapTemplate.search(
    query,
    (AttributesMapper<String>) attrs ->
        (String) attrs.get("cn").get()
);
```

Chuỗi filter theo LDAP có cú pháp khác DN. Trong **filter**, dấu phẩy ở giá trị `cn` không phải ký tự phân cách RDN, nên một filter đơn giản có thể có dạng:

```text
(cn=Nguyen, Lan)
```

Điều này **không** có nghĩa mọi ký tự đều được đưa thẳng vào filter: theo RFC 4515, các ký tự như `*`, `(`, `)`, `\` và NUL có quy tắc escape riêng. Dùng `LdapQueryBuilder` để dựng **filter** và `LdapNameBuilder` để dựng **DN**; không tái sử dụng chung một hàm escape cho hai cú pháp.

| Tình huống | Biểu diễn phù hợp |
| --- | --- |
| Tên `Nguyen, Lan` đặt trong DN | `cn=Nguyen\, Lan,ou=people,...` |
| Tên `Nguyen, Lan` trong giá trị LDIF | `cn: Nguyen, Lan` |
| Tìm theo thuộc tính `cn` | Filter `(cn=Nguyen, Lan)` hoặc query builder tương đương. |
| Dữ liệu nhập từ người dùng | Truyền giá trị `Nguyen, Lan` cho API builder, để API escape đúng. |

## 9. Cách đọc và xử lý DN chứa dấu phẩy khi gỡ lỗi

Khi gặp lỗi `InvalidNameException`, `NameNotFoundException` hoặc `lookup` trả về entry không như dự kiến, hãy kiểm tra từng lớp sau:

1. **Giá trị gốc:** người dùng hoặc nguồn dữ liệu cung cấp `Nguyen, Lan` hay đã chủ động đưa vào chuỗi `Nguyen\, Lan`? Nếu API nhận **giá trị thô**, đừng escape trước lần nữa.
2. **Tên DN đã dựng:** in hoặc ghi log DN **sau khi dựng**, tại môi trường được phép ghi log; xác nhận các dấu phẩy trong giá trị đã được escape và các dấu phẩy giữa RDN không bị escape.
3. **Số và nội dung RDN:** dùng `LdapName`/`Rdn` xem parser có nhận đúng từng thành phần hay không. Không dùng `String.split(",")`.
4. **Base DN của Spring:** xác định API đang dùng tên tương đối hay đầy đủ; tránh thêm lặp `dc=example,dc=org`.
5. **Kiểm tra tồn tại và quyền:** DN hợp lệ về cú pháp vẫn có thể không tồn tại hoặc không được phép truy cập.

Một số nhầm lẫn cụ thể:

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| `"cn=" + name + ",ou=people"` với `name` chứa dấu phẩy | Dữ liệu có thể làm hỏng hoặc thay đổi cấu trúc DN. | Dùng `LdapNameBuilder.add("cn", name)`. |
| `dn.split(",")` | Tách cả dấu phẩy thuộc giá trị. | Phân tích bằng `LdapName`. |
| Chuyển mọi dấu `,` thành `\,` | Làm mất dấu phân cách giữa các RDN. | Escape từng **giá trị** trước khi dựng tên. |
| Truyền `"Nguyen\, Lan"` như giá trị thô vào builder | Có nguy cơ escape dấu `\` lần nữa, tạo giá trị khác. | Truyền `"Nguyen, Lan"`. |
| Dùng DN escaping cho LDAP filter | Hai cú pháp khác nhau nên kết quả có thể sai. | Dùng `LdapQueryBuilder` cho filter. |

## 10. Bài tập kiểm tra

**Bài 1.** Xét DN:

```text
cn=Sales\, APAC,ou=teams,dc=example,dc=org
```

Hỏi: DN có bao nhiêu RDN? Giá trị thực của `cn` là gì?

**Đáp án:** Có **4 RDN**. RDN đầu là `cn=Sales\, APAC`, giá trị `cn` là `Sales, APAC`. Dấu phẩy sau `APAC` mới phân cách RDN kế tiếp.

**Bài 2.** Một ứng dụng muốn đặt `cn` bằng `Platform, Security`, dưới nhánh `ou=groups,dc=example,dc=org`. Hãy viết DN đúng và lý giải vì sao chuỗi không có escape là sai.

**Đáp án:**

```text
cn=Platform\, Security,ou=groups,dc=example,dc=org
```

Phải escape dấu phẩy giữa `Platform` và `Security` vì nó nằm trong **một giá trị `cn`**. Nếu viết `cn=Platform, Security,ou=groups,...`, phần `Security` bị đọc như một RDN độc lập không hợp lệ.

**Bài 3.** Đoán giá trị `cn` trong hai RDN:

```text
A. cn=Lab\,Ops
B. cn=Lab\\
```

**Đáp án:** A có `cn` bằng `Lab,Ops`; B có `cn` bằng `Lab\`. Hai dấu backslash liên tiếp trong **chuỗi DN** biểu diễn một ký tự backslash trong dữ liệu, còn `\,` biểu diễn một dấu phẩy trong dữ liệu.

**Bài 4.** Với base của Spring LDAP là `dc=example,dc=org`, người dùng nhập tên `Ha, Noi`. Hãy cho biết giá trị cần truyền vào `LdapNameBuilder.add("cn", ...)` và DN tương đối khi đặt entry dưới `ou=people`.

**Đáp án:** Truyền **giá trị thô** `"Ha, Noi"`. Kết quả tên tương đối là `cn=Ha\, Noi,ou=people`; không tự chèn `\` vào giá trị trước khi gọi builder.

## 11. Ghi nhớ

Trong cú pháp DN, **dấu phẩy không được escape phân cách hai RDN**; **dấu phẩy được escape (`\,` hoặc `\2C`) thuộc về giá trị của một RDN**. Dấu `+` còn có vai trò riêng là phân cách AVA trong cùng một RDN đa trị. Luôn phân biệt giá trị thuộc tính, chuỗi DN và Java string literal: chúng có quy tắc biểu diễn khác nhau dù nói về cùng một tên. Khi làm việc với Spring LDAP, dùng `LdapNameBuilder` để dựng DN, `LdapName` để phân tích DN và `LdapQueryBuilder` để dựng filter; nhờ đó các tên chứa dấu phẩy vẫn được xử lý đúng và an toàn.
