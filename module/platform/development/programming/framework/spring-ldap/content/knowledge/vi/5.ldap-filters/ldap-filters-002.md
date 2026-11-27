# Equality, presence và substring filter

Trong **Spring LDAP**, ứng dụng không phải lúc nào cũng biết Distinguished Name (DN) của một entry để đọc trực tiếp. Nhiều tình huống chỉ có mã người dùng `uid`, cần lọc những người có email hoặc tìm tên chứa một đoạn văn bản. **LDAP search filter** cho phép mô tả các điều kiện ấy. Ba loại nền tảng là **equality**, **presence** và **substring** filter.

Bài học thuộc chương **Filter LDAP** của module **SPRING_LDAP**, sử dụng cây thư mục giả định `dc=example,dc=org`. Bạn sẽ thấy cách diễn giải cú pháp RFC 4515, ảnh hưởng của schema và matching rule, các ví dụ Java với `LdapTemplate` và `LdapQueryBuilder`, cũng như kỹ thuật xử lý ký tự đặc biệt trong giá trị người dùng. Các nguyên tắc cũng áp dụng khi dùng `LdapClient` hoặc LDAP ODM.

Sau bài này, bạn có thể:

- Viết và giải thích filter `(uid=lan)`, `(mail=*)`, `(cn=Lan*)`.
- Phân biệt wildcard mang ý nghĩa cú pháp với dấu sao `*` là dữ liệu thực.
- Hiểu sự khác nhau giữa giá trị bằng nhau, thuộc tính hiện diện và chuỗi con.
- Dựng filter bằng API của Spring LDAP để tránh lỗi syntax và LDAP injection.
- Kết hợp search base, scope, quyền truy cập và các điều kiện tìm kiếm cho một truy vấn đúng nghiệp vụ.

## 1. Search filter là một phần của phép tìm kiếm LDAP

Một phép LDAP search thường có các thành phần:

1. **Search base (base DN):** nhánh trong Directory Information Tree (DIT) nơi phép tìm bắt đầu.
2. **Search scope:** chỉ entry gốc (`base object`), con trực tiếp (`one-level`) hoặc toàn bộ cây con (`subtree`).
3. **Search filter:** điều kiện để một entry khớp.
4. **Attributes to return:** các thuộc tính cần trả về, ví dụ `uid`, `cn`, `mail`.
5. **Chính sách server:** quyền truy cập, giới hạn thời gian/số bản ghi, schema và matching rule.

Ví dụ:

```text
Base DN:  ou=people,dc=example,dc=org
Scope:    subtree
Filter:   (uid=lan)
Return:   uid, cn, mail
```

Điều kiện `(uid=lan)` kiểm tra thuộc tính của các entry **trong phạm vi tìm kiếm**. Nó không tự di chuyển search base sang nhánh khác và cũng không bảo đảm có quyền đọc entry. **Filter khác DN**: DN là tên để định vị một entry, filter là biểu thức quyết định những entry nào cần tìm.

Chuỗi filter được định nghĩa trong [RFC 4515](https://www.rfc-editor.org/rfc/rfc4515). Các điều kiện cơ bản được bao trong ngoặc:

```text
(attribute=assertion)
```

Trong đó `attribute` là attribute description như `uid`, `mail`, `cn`, còn cú pháp và nội dung phía sau dấu bằng xác định kiểu kiểm tra.

## 2. Equality filter: thuộc tính bằng một giá trị

**Equality filter** có dạng:

```ldap
(attribute=value)
```

Ví dụ:

| Filter | Ý nghĩa |
| --- | --- |
| `(uid=lan)` | Entry có ít nhất một giá trị `uid` khớp `lan`. |
| `(mail=lan@example.org)` | Entry có email khớp với giá trị đã cho. |
| `(cn=Lan Nguyen)` | Entry có tên `cn` khớp `Lan Nguyen`. |
| `(objectClass=inetOrgPerson)` | Entry có giá trị `objectClass` phù hợp với `inetOrgPerson`. |

### “Bằng nhau” do LDAP schema quyết định

**Equality** không đơn giản tương đương với `String.equals` trong Java. LDAP schema định nghĩa `EQUALITY` matching rule của mỗi attribute type:

- `caseIgnoreMatch` có thể bỏ qua khác biệt chữ hoa/thường trong phạm vi quy tắc so sánh tương ứng.
- `caseExactMatch` yêu cầu so khớp có xét hoa/thường.
- Các matching rule cho số, DN hoặc cú pháp khác có thể áp dụng cách chuẩn hóa riêng.
- Một số thuộc tính không hỗ trợ equality matching rule theo cách bạn giả định; server có thể trả kết quả không khớp hoặc phản hồi tùy schema.

Ví dụ `(cn=lan nguyen)` có thể khớp entry có `cn: Lan Nguyen` nếu `cn` sử dụng matching rule bỏ qua hoa/thường. Không nên mô phỏng cách server so sánh bằng `String.equalsIgnoreCase` rồi mặc định kết quả giống nhau.

### Thuộc tính đa trị: chỉ cần một giá trị khớp

Một entry có thể chứa:

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
mail: l.nguyen@example.org
```

Equality filter `(mail=l.nguyen@example.org)` có thể khớp dù entry còn có `mail: lan@example.org`. Với attribute đa trị, một giá trị thỏa điều kiện là đủ theo semantics của filter; không có nghĩa toàn bộ tập giá trị đúng bằng một chuỗi.

### Equality với giá trị rỗng là trường hợp riêng

```text
(mail=)   ← Equality assertion với giá trị rỗng.
(mail=*)  ← Presence filter: thuộc tính mail hiện diện.
```

Hai filter này **không tương đương**. Nhiều thuộc tính bị schema hạn chế giá trị rỗng; `(mail=)` có thể không khớp hoặc không được server hỗ trợ như mong đợi. Nếu muốn tìm người **chưa có `mail`**, cần nghĩ đến phủ định presence filter: `(!(mail=*))`.

## 3. Presence filter: thuộc tính có hiện diện hay không?

**Presence filter** có dạng chính xác:

```ldap
(attribute=*)
```

Dấu `*` trong biểu thức này có ý nghĩa **kiểm tra sự hiện diện** của thuộc tính:

| Filter | Ý nghĩa |
| --- | --- |
| `(mail=*)` | Entry có thuộc tính `mail`. |
| `(telephoneNumber=*)` | Entry có số điện thoại. |
| `(jpegPhoto=*)` | Entry có thuộc tính ảnh, nếu được schema và quyền truy cập cho phép nhìn thấy. |
| `(objectClass=*)` | Entry có `objectClass`; thường dùng để tìm entry trong một nhánh, nhưng quá rộng nếu không giới hạn. |

Để tìm entry thiếu email:

```ldap
(!(mail=*))
```

Để giới hạn ở loại người dùng phù hợp:

```ldap
(&(objectClass=inetOrgPerson)(!(mail=*)))
```

`&` nghĩa là **AND**, `!` là **NOT**. Ở đây biểu thức bên trong `!` vẫn là một presence filter. Trong ví dụ tổng hợp, bạn có thể kết hợp presence với equality để tránh tìm cả nhóm hay organizational unit.

Một điểm cần kiểm tra trên hệ thống thật: **ACL** có thể ảnh hưởng khả năng tìm thấy entry/attribute và cách server đánh giá filter. “Ứng dụng không thấy `mail`” chưa đủ khẳng định “directory thực sự không lưu `mail`” nếu tài khoản bind bị hạn chế quyền.

## 4. Substring filter: tìm phần đầu, cuối hoặc giữa giá trị

**Substring filter** dùng dấu `*` làm wildcard để thể hiện các đoạn không cố định giữa những phần văn bản đã cho:

```ldap
(attribute=prefix*)
(attribute=*suffix)
(attribute=*middle*)
(attribute=pre*middle*post)
```

Dấu `*` trong substring có thể khớp đoạn dài tùy ý, kể cả đoạn rỗng. Thứ tự các phần cố định được giữ nguyên.

| Filter | Ý nghĩa dự kiến |
| --- | --- |
| `(cn=Lan*)` | `cn` bắt đầu bằng `Lan`. |
| `(cn=*Nguyen)` | `cn` kết thúc bằng `Nguyen`. |
| `(cn=*Nguy*)` | `cn` chứa đoạn `Nguy`. |
| `(cn=La*n)` | `cn` bắt đầu `La` và kết thúc `n`. |
| `(cn=*Lan*Nguyen*)` | Trong `cn`, phần `Lan` nằm trước `Nguyen`. |

So sánh:

```text
(cn=Lan)   equality: khớp giá trị Lan
(cn=Lan*)  substring: có phần đầu Lan
(cn=*)     presence: thuộc tính cn tồn tại
```

**`(cn=*)` là presence, không phải substring.** Dù đều có dấu sao, chúng thuộc hai dạng filter khác nhau trong ngữ pháp LDAP.

### Substring phụ thuộc quy tắc so khớp của schema

Attribute type thường cần **`SUBSTR` matching rule** phù hợp để được tìm theo chuỗi con. Không phải thuộc tính nào cũng hỗ trợ substring; trường kiểu byte nhị phân, chứng chỉ hay số định danh không nên mặc định có thể tìm bằng mẫu `*text*`.

Tương tự equality, việc substring có phân biệt chữ hoa/chữ thường hay chuẩn hóa khoảng trắng phụ thuộc `SUBSTR` matching rule. Nếu một filter hợp lệ về cú pháp nhưng không có kết quả, cần xét schema và scope trước khi kết luận dữ liệu không tồn tại.

## 5. Dự đoán kết quả qua bảng entry mẫu

Giả sử dưới `ou=people,dc=example,dc=org` có các entry:

| Entry | `cn` | `uid` | `mail` |
| --- | --- | --- | --- |
| `uid=lan` | `Lan Nguyen` | `lan` | `lan@example.org` |
| `uid=lananh` | `Lan Anh` | `lananh` | Chưa có |
| `uid=an` | `An Tran` | `an` | `an@example.org` |
| `uid=thanh` | `Thanh Lan` | `thanh` | `thanh@example.org` |

Giả định `cn` có substring matching rule bỏ qua hoa/thường, và tài khoản tìm kiếm đủ quyền:

| Filter | Entry khớp dự kiến | Lý do |
| --- | --- | --- |
| `(uid=lan)` | `uid=lan` | Equality theo `uid`. |
| `(mail=*)` | `uid=lan`, `uid=an`, `uid=thanh` | Có `mail`. |
| `(!(mail=*))` | `uid=lananh` | `mail` vắng mặt. |
| `(cn=Lan*)` | `uid=lan`, `uid=lananh` | Tên bắt đầu bằng `Lan`. |
| `(cn=*Lan)` | `uid=thanh` | Tên kết thúc bằng `Lan`. |
| `(cn=*Lan*)` | `uid=lan`, `uid=lananh`, `uid=thanh` | Tên chứa `Lan`. |
| `(cn=Lan)` | Không có | Không entry nào có `cn` chỉ là `Lan`. |

Đây là kết quả trên **dữ liệu giả định**. Kết quả của thư mục thật còn phụ thuộc schema, search scope, ACL và việc có những entry khác trong cùng nhánh.

## 6. Khi `*` là ký tự người dùng nhập, phải escape

Một dấu sao có thể thuộc **cú pháp filter** hoặc là **giá trị văn bản thực sự**. Giả sử tên của một nhóm là `Dev*Ops`, trong đó dấu sao là ký tự dữ liệu:

```text
(cn=Dev*Ops)      Substring: dấu * là wildcard.
(cn=Dev\2aOps)    Equality: \2a biểu diễn ký tự * thực.
(cn=*Dev\2aOps*)  Substring chứa đoạn literal Dev*Ops.
```

Theo [RFC 4515](https://www.rfc-editor.org/rfc/rfc4515), các ký tự cần escape trong một assertion value gồm:

| Ký tự dữ liệu | Escape trong filter |
| --- | --- |
| `*` | `\2a` |
| `(` | `\28` |
| `)` | `\29` |
| `\` | `\5c` |
| Byte NUL (0x00) | `\00` |

`\HH` sử dụng **hai chữ số thập lục phân để biểu diễn một octet**. Dấu sao `*` là byte `0x2A` theo ASCII/UTF-8; `\2a` biểu diễn ký tự sao literal sau khi giải mã, không còn là toán tử wildcard.

Với các ký tự Unicode hợp lệ, chuỗi filter có thể chứa UTF-8. Khi cần biểu diễn dạng hex, phải tính **các octet UTF-8**, không giả định một mã Unicode luôn tương đương một byte.

### DN escaping và filter escaping khác nhau

```text
DN:     cn=Nguyen\, Lan,ou=people,dc=example,dc=org
Filter: (cn=Nguyen, Lan)
```

Dấu phẩy trong giá trị **DN** phải escape để không bị nhầm với dấu phân cách RDN. Dấu phẩy **trong filter** không nằm trong nhóm ký tự buộc escape theo RFC 4515.

Không sử dụng chung một hàm escape cho DN và filter. Spring LDAP có `LdapNameBuilder` để dựng DN, còn filter nên được dựng bằng `LdapQueryBuilder` hoặc công cụ escape filter đúng ngữ cảnh.

## 7. Equality và presence với `LdapQueryBuilder`

Giả sử ứng dụng cấu hình LDAP base `dc=example,dc=org`:

```yaml
spring:
  ldap:
    urls: ldaps://ldap.example.org:636
    base: dc=example,dc=org
    username: uid=svc-reader,ou=service,dc=example,dc=org
    password: ${LDAP_BIND_PASSWORD}
```

Đây là cấu hình minh họa. Trong môi trường thật, tài khoản bind cần quyền tối thiểu, mật khẩu phải được quản lý bằng cơ chế secret phù hợp và kết nối TLS phải xác minh chứng chỉ server.

### Equality từ giá trị động

```java
import java.util.List;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;

// Trong service đã được inject ldapTemplate:
String requestedUid = "lan";

LdapQuery byUid = LdapQueryBuilder.query()
    .base("ou=people")
    .where("uid").is(requestedUid);

List<String> names = ldapTemplate.search(
    byUid,
    (AttributesMapper<String>) attrs ->
        (String) attrs.get("cn").get()
);
```

`.where("uid").is(requestedUid)` biểu diễn **equality**. Query builder xử lý giá trị theo ngữ cảnh, giúp tránh lắp filter bằng phép cộng chuỗi từ đầu vào chưa tin cậy.

### Presence: người dùng đã có email

```java
LdapQuery withEmail = LdapQueryBuilder.query()
    .base("ou=people")
    .where("mail").isPresent();

List<String> usersWithEmail = ldapTemplate.search(
    withEmail,
    (AttributesMapper<String>) attrs ->
        (String) attrs.get("uid").get()
);
```

`.isPresent()` tạo **presence** `(mail=*)`. Với các entry không chắc có `uid`, mapper cần kiểm tra thuộc tính trả về trước khi lấy giá trị; ví dụ giả định entry người dùng có `uid`.

Cả hai ví dụ dùng `ou=people` **tương đối** so với base trong `ContextSource`. Truyền lặp cả `dc=example,dc=org` vào API vốn xử lý tên tương đối có thể khiến truy vấn sai nhánh.

## 8. Substring với `LdapQueryBuilder` và giá trị động

### Mẫu có chủ ý do ứng dụng xác định

```java
LdapQuery startsWithLan = LdapQueryBuilder.query()
    .base("ou=people")
    .where("cn").like("Lan*");

List<String> matchingNames = ldapTemplate.search(
    startsWithLan,
    (AttributesMapper<String>) attrs ->
        (String) attrs.get("cn").get()
);
```

`.like("Lan*")` dùng mẫu substring có ký tự wildcard do **ứng dụng** chủ đích cung cấp. Đây là ví dụ với mẫu cố định, không nối trực tiếp dữ liệu người dùng.

### Tìm đoạn literal do người dùng nhập

Giả sử người dùng nhập `Lan*(QA)` nhưng toàn bộ cụm này là **văn bản thực sự**, kể cả dấu sao và dấu ngoặc. Để tìm tên chứa nguyên cụm, phải escape **phần giá trị**, sau đó mới thêm wildcard có chủ đích.

```java
import java.util.List;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.support.LdapEncoder;

// Trong service đã được inject ldapTemplate:
String rawKeyword = "Lan*(QA)";
String escapedLiteral = LdapEncoder.filterEncode(rawKeyword);

String filter = "(cn=*" + escapedLiteral + "*)";
// (cn=*Lan\2a\28QA\29*)

List<String> results = ldapTemplate.search(
    "ou=people",
    filter,
    (AttributesMapper<String>) attrs ->
        (String) attrs.get("cn").get()
);
```

`LdapEncoder.filterEncode` dùng escaping của **assertion value**. Hai dấu `*` do code thêm bên ngoài `escapedLiteral` vẫn là wildcard để tìm **chứa**. Các dấu `*`, `(`, `)` trong dữ liệu không còn thay đổi cấu trúc filter.

Với API filter builder chuyên dụng của phiên bản Spring LDAP đang dùng, cũng nên giữ nguyên nguyên tắc: dữ liệu người dùng là **literal**; chỉ wildcard do ứng dụng cho phép mới trở thành cú pháp.

## 9. Vì sao nối chuỗi filter trực tiếp nguy hiểm?

Đây là cách viết cần tránh:

```java
String filter = "(uid=" + userInput + ")";
```

Nếu `userInput` chứa `*`, dấu ngoặc, gạch chéo ngược hoặc các chuỗi điều khiển khác, filter cuối cùng có thể bị hiểu khác ý định hoặc sai cú pháp. Chẳng hạn, một đầu vào là `*` có thể biến điều kiện tìm `uid` cụ thể thành `(uid=*)`, tức **presence filter**.

Để tìm đúng mã người dùng, viết:

```java
LdapQuery safeQuery = LdapQueryBuilder.query()
    .base("ou=people")
    .where("uid").is(userInput);
```

Ngoài escape giá trị, ứng dụng cần kiểm soát **tên thuộc tính** nếu tên ấy do người dùng chọn. Ví dụ chỉ chấp nhận tìm kiếm theo `uid`, `cn` hoặc `mail` đã được whitelist; không cho người dùng truyền tùy ý tên thuộc tính, base DN hoặc scope.

Cũng cần giới hạn độ dài từ khóa, số lượng entry trả về và quyền của tài khoản bind. Escape là cơ chế giữ nguyên **ý nghĩa của giá trị** trong filter; nó không thay thế ACL hay chính sách tài nguyên.

## 10. Kết hợp ba loại filter với AND, OR và NOT

LDAP sử dụng các toán tử tiền tố:

- `&`: AND — tất cả filter con phải khớp.
- `|`: OR — ít nhất một filter con khớp.
- `!`: NOT — phủ định một filter con.

Ví dụ:

```ldap
(&(objectClass=inetOrgPerson)(mail=*))
```

Tìm entry thuộc lớp người dùng chỉ định **và** có email.

```ldap
(&(objectClass=inetOrgPerson)(cn=Lan*))
```

Tìm entry người dùng có `cn` bắt đầu bằng `Lan`.

```ldap
(|(uid=lan)(mail=lan@example.org))
```

Tìm entry có `uid=lan` **hoặc** `mail=lan@example.org`.

```ldap
(&(objectClass=inetOrgPerson)(!(mail=*)))
```

Tìm entry người dùng không có `mail` trong phạm vi và theo kết quả đánh giá quyền của server.

Như vậy, equality, presence và substring là **các điều kiện cơ sở**; biểu thức kết hợp chỉ ghép các điều kiện này để phù hợp nghiệp vụ. Không dùng `&&` hay `||` như trong Java.

## 11. Lỗi thường gặp khi thực hành

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| `(uid=lan)` không có kết quả | Search base/scope sai, entry không tồn tại, ACL hoặc matching rule. | Kiểm tra DN nhánh, schema và quyền của tài khoản bind. |
| `(mail=*)` trả cả nhóm | Presence không giới hạn loại entry. | Kết hợp `objectClass`, search base phù hợp. |
| `(cn=*)` bị gọi là substring | Nhầm loại filter. | Đây là presence; dùng `(cn=Lan*)` cho prefix. |
| Tìm dấu `*` literal nhưng trả quá nhiều kết quả | Dấu sao không escape thành `\2a`. | Escape dữ liệu, chỉ tạo wildcard theo chủ ý. |
| `(mail=)` không tìm thấy người thiếu email | Equality rỗng không đồng nghĩa absence. | Sử dụng `(!(mail=*))`. |
| `(cn=Lan*)` không khớp nhưng equality khớp | Có thể do thiếu hoặc khác `SUBSTR` matching rule. | Kiểm tra schema và phản hồi server. |
| Filter hỏng khi từ khóa chứa `(`/`)` | Nối chuỗi đầu vào trực tiếp. | Dùng builder/encoder cho filter. |
| Tìm kiếm chậm hoặc quá nhiều kết quả | Search base lớn, wildcard đầu, thiếu chỉ mục. | Thu hẹp base, bổ sung điều kiện, tối ưu index/giới hạn trên server. |
| Nhập dấu phẩy trong tên nhưng escape sai | Nhầm cú pháp DN với cú pháp filter. | DN dùng escaping RFC 4514; filter dùng RFC 4515. |

### Hiệu năng và tính duy nhất

Equality trên thuộc tính được lập chỉ mục thường hiệu quả hơn tìm substring rộng, nhưng hiệu quả còn phụ thuộc LDAP server và cấu hình index. Mẫu `(cn=*Lan*)` có wildcard đầu nên có thể tốn tài nguyên hơn `(cn=Lan*)`. Không nên chạy `(objectClass=*)` trên cây thư mục rất lớn nếu không có hạn mức và lý do nghiệp vụ rõ ràng.

Filter `(uid=lan)` **không bảo đảm một kết quả duy nhất trên toàn directory**: có thể tồn tại `uid=lan` dưới hai nhánh cha. Ứng dụng phải kiểm soát search base, chính sách dữ liệu và xử lý 0, 1 hoặc nhiều kết quả.

Server cũng không mặc định trả kết quả theo thứ tự mong muốn. Khi API cần phân trang hoặc sắp xếp, sử dụng khả năng tương ứng của server/client và kiểm thử với thư mục thật.

## 12. Kiểm thử trên bộ dữ liệu nhỏ

Để kiểm thử bộ lọc trong Spring LDAP, dựng tập entry có kiểm soát dưới một nhánh test và dùng LDAP server tương thích schema. Các tình huống nên bao gồm:

1. **Equality đúng/sai:** `(uid=lan)` tìm thấy entry chuẩn; `(uid=unknown)` không có kết quả.
2. **Presence:** entry có `mail` khớp `(mail=*)`; entry thiếu `mail` không khớp.
3. **Absence:** `(!(mail=*))` có hành vi đúng trong phạm vi quyền và dữ liệu test.
4. **Substring:** thử prefix `Lan*`, suffix `*Nguyen`, contains `*Nguy*` và nhiều phần cố định `La*n`.
5. **Matching rule:** xác minh behavior chữ hoa/thường và dữ liệu tiếng Việt theo schema server đang dùng.
6. **Ký tự đặc biệt:** một entry có `cn: Dev*Ops` phải khớp literal `(cn=Dev\2aOps)`.
7. **Dữ liệu không tin cậy:** `*` hoặc `()` do người dùng nhập không thể thay đổi cấu trúc filter nếu đi qua API thích hợp.
8. **Scope/ACL:** cùng filter ở nhánh khác hoặc với tài khoản khác có kết quả đúng theo cấu hình.
9. **Giới hạn:** truy vấn `(cn=*)` trên nhiều entry không làm API trả vô hạn hoặc gây quá tải.

Bảng kiểm tra minh họa:

| Filter | Entry mẫu | Kết quả dự kiến |
| --- | --- | --- |
| `(uid=lan)` | `uid: lan` | Khớp. |
| `(mail=*)` | Entry chỉ có `uid` và `cn` | Không khớp. |
| `(cn=Lan*)` | `cn: Lan Nguyen` | Khớp khi substring rule tương thích. |
| `(cn=Dev\2aOps)` | `cn: Dev*Ops` | Khớp dấu sao literal theo equality rule. |
| `(cn=Dev*Ops)` | `cn: DevTeamOps` | Có thể khớp theo substring rule. |

Kiểm thử trên server, không chỉ so sánh chuỗi filter được sinh ra, vì schema, matching rule và quyền truy cập quyết định kết quả thực tế.

## 13. Bài tập tự kiểm tra

**Bài 1.** Viết filter tìm tất cả entry có `telephoneNumber`.

**Lời giải:** `(telephoneNumber=*)`, đây là **presence filter**.

**Bài 2.** Viết filter tìm người có `uid` bằng `minh`.

**Lời giải:** `(uid=minh)`, đây là **equality filter** (cách đánh giá “bằng” do schema quy định).

**Bài 3.** Viết filter tìm entry có `cn` chứa đoạn `Dev` ở bất kỳ vị trí nào.

**Lời giải:** `(cn=*Dev*)`, đây là **substring filter**.

**Bài 4.** Tìm `cn` là chính xác `Team*Ops`, trong đó dấu `*` là dữ liệu. Sau đó viết filter tìm `cn` có chứa đoạn `Team*Ops`.

**Lời giải:**

```ldap
(cn=Team\2aOps)
(cn=*Team\2aOps*)
```

`\2a` là dấu sao literal. Hai dấu sao bao ngoài ở dòng thứ hai là wildcard.

**Bài 5.** Vì sao `(mail=)` không phải cách đúng để tìm entry thiếu `mail`?

**Lời giải:** Đó là equality assertion với giá trị rỗng, không phải “không tồn tại”. Dùng `(!(mail=*))` và giới hạn theo loại entry/scope cần tìm.

**Bài 6.** Spring LDAP đã cấu hình base `dc=example,dc=org`; muốn tìm `uid=lan` dưới `ou=people`, phải đặt search base và filter thế nào?

**Lời giải:** Search base tương đối `ou=people`, filter `(uid=lan)`. Có thể dùng `LdapQueryBuilder.query().base("ou=people").where("uid").is("lan")`.

## 14. Ghi nhớ

**Equality** `(attribute=value)` so khớp giá trị theo schema; **presence** `(attribute=*)` kiểm tra thuộc tính hiện diện; **substring** `(attribute=pre*mid*post)` kiểm tra các phần văn bản theo thứ tự. Một dấu sao `*` có thể là wildcard hoặc ký tự literal `\2a`, tùy cách viết filter.

Khi dùng Spring LDAP, hãy ưu tiên `LdapQueryBuilder` cho equality, presence và các mẫu substring được ứng dụng kiểm soát. Với dữ liệu động, escape assertion value đúng RFC 4515 trước khi thêm wildcard được phép. Luôn xác định base, scope, schema và quyền; một filter hợp lệ không tự bảo đảm kết quả đúng phạm vi hay an toàn.

Tài liệu tham khảo: [RFC 4515 – LDAP Search Filters](https://www.rfc-editor.org/rfc/rfc4515), [RFC 4511 – LDAP Protocol](https://www.rfc-editor.org/rfc/rfc4511), [RFC 4512 – LDAP Directory Information Models](https://www.rfc-editor.org/rfc/rfc4512), [RFC 4517 – LDAP Syntaxes and Matching Rules](https://www.rfc-editor.org/rfc/rfc4517).
