# Filter trên attribute đa trị

Trong LDAP, một **attribute** của entry có thể chứa **nhiều giá trị**. Ví dụ, một nhóm có nhiều DN thành viên trong attribute `member`; một entry thường có nhiều giá trị `objectClass`; và một người có thể có nhiều địa chỉ `mail` nếu schema cho phép. Khi viết LDAP filter, các giá trị này được so khớp theo cách khác với việc so sánh một trường đơn trị trong cơ sở dữ liệu quan hệ.

Bài học thuộc chương **Filter LDAP** trong mô-đun **SPRING_LDAP**. Đây là nền tảng cho việc tìm kiếm entry bằng `LdapTemplate`, `LdapClient`, hoặc ODM, đồng thời giúp lựa chọn đúng search base, scope, filter và xử lý kết quả an toàn.

**Mục tiêu học tập:**

- Giải thích được cách một filter đánh giá **attribute đa trị**.
- Viết filter tìm nhóm có một hoặc nhiều thành viên, entry có nhiều `objectClass` và người dùng có nhiều giá trị `mail`.
- Hiểu chính xác ý nghĩa của `&`, `|`, `!` khi cùng một attribute xuất hiện trong nhiều điều kiện.
- Phân biệt **equality**, **presence**, **substring**, **ordering** và **approximate matching**, cũng như giới hạn do LDAP schema đặt ra.
- Tạo filter an toàn với Spring LDAP; phân biệt escaping của filter với escaping của DN.
- Kiểm thử tình huống attribute thiếu, không được quyền đọc hoặc có nhiều giá trị nhưng chỉ một phần thỏa điều kiện.

## 1. Attribute đa trị là gì?

Theo mô hình LDAP, một entry chứa tập các attribute. Mỗi attribute có **một hoặc nhiều giá trị** khi hiện diện, miễn là không bị schema ràng buộc thành đơn trị bằng `SINGLE-VALUE`. Những attribute không có giá trị thường được xem là **vắng mặt**, thay vì tồn tại như một mảng rỗng.

Ví dụ entry nhóm theo `groupOfNames`:

```ldif
dn: cn=Engineering,ou=Groups,dc=example,dc=org
objectClass: top
objectClass: groupOfNames
cn: Engineering
member: uid=an,ou=People,dc=example,dc=org
member: uid=binh,ou=People,dc=example,dc=org
member: uid=chi,ou=People,dc=example,dc=org
```

Attribute `member` trong ví dụ có **ba giá trị**. Mỗi giá trị là một DN trỏ tới entry người dùng. Giá trị `member` biểu thị quan hệ thành viên; vị trí entry nhóm trong DIT không thay đổi vị trí entry người dùng.

Một entry người dùng cũng có thể có nhiều `objectClass`:

```ldif
dn: uid=an,ou=People,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: an
cn: An Nguyen
sn: Nguyen
mail: an@example.org
mail: an.work@example.net
```

Trong ví dụ này, `objectClass` chứa bốn giá trị. Attribute `mail` có hai giá trị với giả định schema/server cho phép; không phải mọi thuộc tính đều có thể tùy ý chứa nhiều giá trị.

### 1.1. Đa trị khác gì đơn trị?

| Tiêu chí | Attribute đơn trị | Attribute đa trị |
| --- | --- | --- |
| Số giá trị tối đa theo schema | Một, khi có `SINGLE-VALUE` | Có thể nhiều, nếu schema không cấm |
| Ví dụ thường gặp | `createTimestamp` | `member`, `objectClass` |
| Filter equality | So khớp giá trị đang có | So khớp **ít nhất một giá trị** |
| Cách đọc kết quả | Có thể lấy giá trị đơn | Cần duyệt **tất cả giá trị** khi nghiệp vụ yêu cầu |
| Thứ tự giá trị | Không đặt vấn đề | Không nên dựa vào thứ tự các giá trị được trả về |

LDAP không coi các giá trị của attribute đa trị là danh sách có thứ tự theo nghĩa nghiệp vụ. Đừng dựa vào “phần tử đầu tiên là email chính” hay “thành viên đầu tiên là chủ nhóm”, trừ khi hệ thống có quy ước bổ sung được biểu diễn riêng.

### 1.2. Schema quyết định loại và quy tắc so khớp

Mỗi attribute type trong LDAP schema có thể khai báo:

- `SINGLE-VALUE`: giới hạn tối đa một giá trị.
- `SYNTAX`: kiểu dữ liệu của các giá trị.
- `EQUALITY`: quy tắc so khớp bằng, ví dụ phân biệt hay không phân biệt chữ hoa/thường.
- `SUBSTR`: quy tắc tìm chuỗi con, nếu được định nghĩa.
- `ORDERING`: quy tắc thứ tự, nếu được định nghĩa.

Vì vậy, filter không chỉ so sánh văn bản bằng toán tử của Java; LDAP server thực thi **matching rule của attribute type**. Chẳng hạn, `member` thường dùng so khớp **Distinguished Name** và không nhất thiết hỗ trợ substring; `mail` thường có matching rule dành cho chuỗi và có thể hỗ trợ substring. Cần xem schema cụ thể của server trước khi phụ thuộc một kiểu so khớp.

## 2. Quy tắc then chốt: “tồn tại ít nhất một giá trị khớp”

Với filter equality:

```text
(member=uid=an,ou=People,dc=example,dc=org)
```

LDAP kiểm tra liệu **có ít nhất một giá trị `member`** tương ứng với DN `uid=an,ou=People,dc=example,dc=org` hay không. Nếu nhóm có hàng trăm thành viên, chỉ cần **một** thành viên khớp là điều kiện đúng.

Giả sử có các nhóm:

| Nhóm | Các giá trị `member` |
| --- | --- |
| Engineering | `uid=an,...`, `uid=binh,...`, `uid=chi,...` |
| Support | `uid=binh,...` |
| Product | `uid=chi,...`, `uid=lan,...` |

Với filter `(member=uid=an,ou=People,dc=example,dc=org)`, chỉ **Engineering** khớp dữ liệu mẫu.

Ta có thể diễn đạt:

\[
\operatorname{match}(e, (a=v)) \iff \exists x \in values(e,a):\; x \text{ khớp } v
\]

Trong đó `e` là entry, `a` là attribute type và phép “khớp” tuân theo **matching rule** của LDAP schema. Đây là trực giác chính cho equality matching trên attribute đa trị.

**Không cần mọi giá trị đều thỏa điều kiện.** Filter đó cũng **không trả về riêng giá trị `member` đã khớp**: một LDAP search lựa chọn và trả về **entry**. Khi client yêu cầu trả lại `member`, server có thể gửi các giá trị của attribute mà tài khoản bind được phép đọc, không chỉ giá trị phù hợp filter.

### 2.1. Equality với `objectClass`

Vì `objectClass` thường đa trị, filter:

```text
(objectClass=inetOrgPerson)
```

khớp entry người dùng có một giá trị `objectClass` bằng `inetOrgPerson`. Không cần giá trị đó là giá trị duy nhất.

Tương tự:

```text
(&(objectClass=person)(objectClass=inetOrgPerson))
```

có thể khớp **cùng một entry** vì `person` và `inetOrgPerson` là **hai giá trị khác nhau** của `objectClass` trên entry đó.

Đừng diễn giải phép `AND` ở đây như yêu cầu “một phần tử của `objectClass` vừa là `person` vừa là `inetOrgPerson`”. `AND` phối hợp các điều kiện **ở cấp entry**.

## 3. `AND`, `OR` và `NOT` khi attribute đa trị

Các toán tử logic LDAP filter áp dụng cho kết quả so khớp của **toàn entry**:

| Toán tử | Cú pháp | Ý nghĩa |
| --- | --- | --- |
| AND | `(&(A)(B))` | Cả điều kiện A và điều kiện B đều khớp trên entry |
| OR | `(\|(A)(B))` | Ít nhất một trong hai điều kiện khớp trên entry |
| NOT | `(!(A))` | Phủ định kết quả của điều kiện A trên entry |

Trong bảng, dấu `\|` chỉ được escape để trình bày Markdown; cú pháp filter thực tế dùng ký tự `|` nguyên dạng.

### 3.1. Một nhóm chứa **cả An và Bình**: `AND`

```text
(&(member=uid=an,ou=People,dc=example,dc=org)
  (member=uid=binh,ou=People,dc=example,dc=org))
```

Trong câu trên, điều kiện thứ nhất yêu cầu có **ít nhất một** giá trị `member` khớp An, điều kiện thứ hai yêu cầu có **ít nhất một** giá trị `member` khớp Bình. Hai giá trị khớp có thể **khác nhau**.

Kết quả với dữ liệu mẫu: **Engineering** khớp vì nhóm chứa cả hai DN.

Đây là cách biểu diễn đúng yêu cầu: “Tìm các nhóm mà cả An lẫn Bình đều là thành viên”.

### 3.2. Một nhóm chứa **An hoặc Bình**: `OR`

```text
(|(member=uid=an,ou=People,dc=example,dc=org)
  (member=uid=binh,ou=People,dc=example,dc=org))
```

Kết quả với dữ liệu mẫu: **Engineering** và **Support** khớp.

`OR` không đòi hỏi cả hai cùng khớp, nhưng một entry có cả An và Bình vẫn được trả về **một lần** theo logic tập kết quả của truy vấn LDAP, chứ không tạo bản sao riêng cho từng giá trị `member`.

### 3.3. Nhóm **không có An**: `NOT`

```text
(!(member=uid=an,ou=People,dc=example,dc=org))
```

Điều kiện trên khớp những entry mà `(member=uid=an,...)` **không khớp**. Trong dữ liệu nhóm mẫu, đó là **Support** và **Product**.

Điểm dễ nhầm:

- `(!(member=An))` có nghĩa **không có giá trị `member` nào khớp An**.
- Nó **không** có nghĩa **tồn tại một giá trị `member` khác An**.

Nhóm **Engineering** có Bình và Chi, nhưng cũng có An. Vì vậy nhóm này **không khớp** filter NOT, dù nhiều giá trị `member` của nó khác DN của An.

### 3.4. Nếu attribute không tồn tại thì sao?

Giả sử một entry không có `mail`:

- `(mail=an@example.org)` không khớp entry.
- `(mail=*)` không khớp entry.
- `(!(mail=an@example.org))` thông thường **khớp entry**, vì entry không có giá trị `mail` khớp An.

Nếu nghiệp vụ muốn “entry có email, nhưng **không** có email `an@example.org`”, hãy kết hợp **presence** và **NOT**:

```text
(&(mail=*)(!(mail=an@example.org)))
```

Điều kiện đó yêu cầu entry có ít nhất một giá trị `mail` và không có giá trị `mail` nào khớp địa chỉ bị loại. Nó không bao gồm entry thiếu `mail`.

**Lưu ý:** LDAP filter có thể có kết quả **Undefined** trong một số trường hợp theo giao thức/matching rule; không nên xem mọi trường hợp thiếu thuộc tính, quyền truy cập hoặc thiếu matching rule là một biểu thức Boolean hai giá trị đơn giản. Ví dụ minh họa ở trên giả định attribute type được server hiểu và phép equality được hỗ trợ.

## 4. Presence filter: kiểm tra attribute có giá trị hay không

Filter:

```text
(member=*)
```

là **presence filter**. Nó yêu cầu entry có attribute `member`, không yêu cầu một giá trị cụ thể. Dấu `*` đứng một mình ở phần giá trị có ý nghĩa đặc biệt **“có attribute này”**.

Ví dụ tìm tất cả nhóm `groupOfNames` có `member`:

```text
(&(objectClass=groupOfNames)(member=*))
```

Với schema chuẩn `groupOfNames`, `member` là attribute bắt buộc. Bởi vậy điều kiện `member=*` thường dư thừa cho các entry `groupOfNames` hợp lệ, nhưng nó minh họa rõ presence. Với kiểu nhóm khác hoặc schema tùy biến, presence có thể hữu ích.

**Không có filter LDAP chuẩn để yêu cầu attribute “có ít nhất hai giá trị” chỉ bằng `(member=*)`.** Presence phân biệt **có** và **không có**, không biểu diễn trực tiếp `COUNT(member) >= 2`. Nếu cần kiểm tra số thành viên, hãy lấy dữ liệu theo quyền được cấp rồi đếm ở tầng ứng dụng hoặc dùng khả năng đặc thù của server khi có tài liệu hỗ trợ.

## 5. Substring, ordering và approximate trên attribute đa trị

Quy tắc “có ít nhất một giá trị khớp” còn giúp hiểu nhiều bộ so khớp khác. Nhưng **matching rule và cú pháp của attribute** quyết định kiểu filter nào thực sự hợp lệ và có ý nghĩa.

### 5.1. Substring: bất kỳ giá trị nào phù hợp mẫu

Giả sử một entry có:

```ldif
mail: an@example.org
mail: an.work@example.net
```

Filter:

```text
(mail=*@example.net)
```

khớp entry nếu có **một** giá trị `mail` kết thúc bằng `@example.net` theo quy tắc substring của schema. `an.work@example.net` thỏa mãn, nên entry được trả về.

Ví dụ kết hợp hai điều kiện substring:

```text
(&(mail=*@example.org)(mail=*@example.net))
```

Entry mẫu có thể khớp vì **hai giá trị mail khác nhau** thỏa hai điều kiện. Filter này **không yêu cầu cùng một địa chỉ email** vừa kết thúc bằng `@example.org` vừa kết thúc bằng `@example.net`.

Ngược lại, nếu yêu cầu một địa chỉ email phải thỏa **hai ràng buộc trên cùng một giá trị**, không thể suy ra điều đó chỉ bằng `AND` của hai substring filter độc lập trên cùng attribute. Cần thiết kế lại điều kiện theo một mẫu phù hợp, hoặc truy xuất các giá trị và đánh giá cùng phần tử ở tầng ứng dụng.

**Không áp dụng substring tùy tiện cho DN.** Với `member` chứa DN, schema thường định nghĩa equality matching cho DN và **không** có substring matching rule. Filter như `(member=*uid=an*)` không phải cách đáng tin để tìm thành viên. Hãy xây dựng **DN đầy đủ** và dùng equality:

```text
(member=uid=an,ou=People,dc=example,dc=org)
```

### 5.2. Ordering: `>=` và `<=`

Các toán tử LDAP `>=` và `<=` dùng **ordering matching rule** nếu attribute type hỗ trợ. Với attribute đa trị, điều kiện thường đúng khi **ít nhất một giá trị** thỏa so khớp thứ tự.

Điều này **không tương đương** với các phép so sánh dữ liệu tổng hợp như “giá trị nhỏ nhất”, “giá trị lớn nhất” hay “mọi giá trị đều lớn hơn ngưỡng”. Chẳng hạn, nếu attribute tùy biến `score` có hai giá trị `20` và `90` với ordering rule kiểu số, điều kiện “`score >= 80`” có thể khớp entry bởi giá trị `90`, dù còn giá trị `20`.

LDAP filter không tự suy ra `score` là số chỉ vì các giá trị nhìn giống số; schema và matching rule quyết định cách so sánh. Nhiều attribute không có ordering rule nên không thể dựa vào `>=` hay `<=` trên chúng.

### 5.3. Approximate: `~=`

Filter:

```text
(cn~=An Nguyen)
```

là **approximate match**. Cách so khớp xấp xỉ tùy server/schema; không thể giả định kết quả giống nhau giữa các hệ thống. Trên một attribute đa trị, nếu approximate matching được hỗ trợ, chỉ cần một giá trị khớp theo quy tắc của server.

Đối với tác vụ cần xác định **đúng thành viên nhóm** hay **đúng mã nhân viên**, ưu tiên equality match và định danh ổn định, thay vì approximate.

## 6. Các trường hợp LDAP phổ biến

### 6.1. `member`: danh sách DN thành viên của nhóm

Nhiều thư mục sử dụng `groupOfNames`:

```ldif
dn: cn=Engineering,ou=Groups,dc=example,dc=org
objectClass: top
objectClass: groupOfNames
cn: Engineering
member: uid=an,ou=People,dc=example,dc=org
member: uid=binh,ou=People,dc=example,dc=org
```

Để tìm nhóm chứa An:

```text
(&(objectClass=groupOfNames)
  (member=uid=an,ou=People,dc=example,dc=org))
```

Filter yêu cầu một entry vừa là loại `groupOfNames`, vừa có ít nhất một `member` khớp DN của An. Việc dùng `objectClass` giúp giới hạn kết quả về loại entry mong muốn.

Một số thư mục dùng `groupOfUniqueNames` với `uniqueMember` hoặc quy ước khác. Đừng mặc định mọi hệ thống đều dùng `member`, và đừng tự đổi `uniqueMember` thành `member` nếu schema thực tế không cho phép.

### 6.2. `objectClass`: cùng entry có nhiều lớp

Filter:

```text
(&(objectClass=person)(objectClass=inetOrgPerson))
```

có thể khớp entry `inetOrgPerson` vì entry thường mang các lớp trong hệ phân cấp object class. Việc xuất hiện nhiều giá trị `objectClass` là bình thường và **không đại diện cho nhiều entry**.

### 6.3. `mail`: nhiều địa chỉ liên hệ

Filter:

```text
(mail=an.work@example.net)
```

tìm entry có một giá trị email khớp địa chỉ đó theo equality rule. Nếu cần biết **địa chỉ nào đã khớp**, đừng giả định giá trị đầu tiên của `mail` trong kết quả là email tìm được. Khi trả về cả attribute `mail`, client có thể nhận được nhiều giá trị và phải tự đánh giá theo yêu cầu nghiệp vụ.

### 6.4. `memberOf` không phải lúc nào cũng có

Một số server cung cấp attribute `memberOf` ở entry người dùng để biểu diễn nhóm mà người đó thuộc về, đôi khi theo cơ chế overlay hoặc computed attribute.

Ví dụ trên những server **có hỗ trợ**:

```text
(memberOf=cn=Engineering,ou=Groups,dc=example,dc=org)
```

Tuy nhiên, `memberOf` không phải một tính năng có mặt và hoạt động đồng nhất trên tất cả LDAP server. Nó có thể là operational attribute, không được trả theo mặc định, không được duy trì như kỳ vọng hoặc bị ACL hạn chế.

Khi chưa xác nhận hỗ trợ `memberOf`, cách truy vấn quan hệ thành viên thường chắc chắn hơn là tìm **entry nhóm** theo `member` hoặc theo attribute membership chính thức của schema đang dùng.

### 6.5. Nhóm lồng nhau không đồng nghĩa truy vấn đệ quy

Giả sử `Engineering` có một giá trị `member` tham chiếu DN của một **nhóm khác**. Equality filter:

```text
(member=uid=an,ou=People,dc=example,dc=org)
```

chỉ kiểm tra các **giá trị thành viên được lưu hoặc server biểu diễn cho attribute đó**. LDAP filter tiêu chuẩn không tự động đi xuyên qua nhiều cấp nhóm lồng nhau để xác định thành viên gián tiếp.

Muốn tìm transitive membership, cần thuật toán duyệt nhóm ở tầng ứng dụng hoặc tính năng/matching rule riêng của server (nếu được hỗ trợ). Không nên mặc định filter equality xử lý quan hệ đệ quy.

## 7. Thử filter bằng `ldapsearch`

Giả sử server có nhóm Engineering và Support như các ví dụ ở trên. Các lệnh sau dùng **LDAPS** để mã hóa kết nối, tên miền và DN chỉ mang tính minh họa.

### 7.1. Tìm nhóm chứa một người dùng

```bash
ldapsearch -LLL -x -H "ldaps://ldap.example.org:636" \
  -b "ou=Groups,dc=example,dc=org" -s sub \
  "(&(objectClass=groupOfNames)(member=uid=an,ou=People,dc=example,dc=org))" \
  cn member
```

Lệnh này tìm dưới nhánh Groups, xét cả cây con (`-s sub`), lọc các nhóm chứa An và yêu cầu trả về các attribute `cn`, `member`. `ldapsearch` còn hiển thị **DN của mỗi entry** trong kết quả. Nếu thông tin thành viên nhạy cảm, chỉ yêu cầu `cn` khi đủ cho mục đích.

### 7.2. Tìm nhóm chứa cả hai người dùng

```bash
ldapsearch -LLL -x -H "ldaps://ldap.example.org:636" \
  -b "ou=Groups,dc=example,dc=org" -s sub \
  "(&(objectClass=groupOfNames)(member=uid=an,ou=People,dc=example,dc=org)(member=uid=binh,ou=People,dc=example,dc=org))" \
  cn
```

Nếu Engineering chứa An và Bình, nhóm đó khớp. Không cần so sánh “một giá trị member phải bằng cả hai DN”.

### 7.3. Tìm các nhóm không chứa An

```bash
ldapsearch -LLL -x -H "ldaps://ldap.example.org:636" \
  -b "ou=Groups,dc=example,dc=org" -s sub \
  "(&(objectClass=groupOfNames)(!(member=uid=an,ou=People,dc=example,dc=org)))" \
  cn
```

Filter có `objectClass=groupOfNames` để tránh vô tình đưa các entry loại khác (không có `member`) vào kết quả.

### 7.4. Cấu hình xác thực an toàn

Các lệnh trên dùng `-x` nhưng chưa cung cấp bind DN, nên thường thử truy vấn ẩn danh. Nếu server yêu cầu xác thực, hãy thêm:

```bash
-D "cn=reader,ou=ServiceAccounts,dc=example,dc=org" -W
```

`-W` yêu cầu nhập mật khẩu qua prompt, hạn chế lộ mật khẩu trong lịch sử dòng lệnh. Vẫn cần kiểm tra chứng chỉ TLS và cấp quyền đọc tối thiểu cho tài khoản bind.

**Khi không có kết quả, đừng kết luận filter sai ngay.** Cần kiểm tra base DN, scope, nội dung DN của thành viên, dữ liệu thực sự lưu trong `member`, matching rule, ACL và giới hạn phía server. Search filter đánh giá trên dữ liệu thư mục theo quyền của phiên truy vấn, không phải trên một snapshot không giới hạn quyền.

## 8. Tạo filter đa trị bằng Spring LDAP

Trong Spring LDAP, `LdapTemplate` và `LdapClient` làm việc với truy vấn có base, scope, filter và danh sách attribute trả về. `LdapQueryBuilder` giúp xây filter một cách an toàn, đặc biệt khi điều kiện chứa dữ liệu từ người dùng.

Giả sử cấu hình `ContextSource` như sau:

```java
contextSource.setBase("dc=example,dc=org");
```

Do đó, một truy vấn `base("ou=Groups")` tìm trong nhánh `ou=Groups,dc=example,dc=org`. Đừng nối thêm hậu tố `dc=example,dc=org` vào base tương đối khi Spring đã được cấu hình base.

### 8.1. Tìm các nhóm chứa người dùng

Ví dụ Java dùng `LdapTemplate` và `LdapQueryBuilder`:

```java
import java.util.List;
import javax.naming.Name;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.SearchScope;
import org.springframework.ldap.support.LdapNameBuilder;

import static org.springframework.ldap.query.LdapQueryBuilder.query;

public class GroupDirectory {
    private final LdapTemplate ldapTemplate;

    public GroupDirectory(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    private Name fullPersonDn(String uid) {
        return LdapNameBuilder.newInstance()
            .add("dc", "org")
            .add("dc", "example")
            .add("ou", "People")
            .add("uid", uid)
            .build();
    }

    public List<String> findGroupsContainingUser(String uid) {
        String memberDn = fullPersonDn(uid).toString();

        LdapQuery groupQuery = query()
            .base("ou=Groups")
            .searchScope(SearchScope.SUBTREE)
            .attributes("cn")
            .where("objectClass").is("groupOfNames")
            .and("member").is(memberDn);

        return ldapTemplate.search(
            groupQuery,
            (AttributesMapper<String>) attrs ->
                String.valueOf(attrs.get("cn").get())
        );
    }

    public List<String> findGroupsContainingBoth(
            String firstUid, String secondUid) {
        String firstDn = fullPersonDn(firstUid).toString();
        String secondDn = fullPersonDn(secondUid).toString();

        LdapQuery groupQuery = query()
            .base("ou=Groups")
            .searchScope(SearchScope.SUBTREE)
            .attributes("cn")
            .where("objectClass").is("groupOfNames")
            .and("member").is(firstDn)
            .and("member").is(secondDn);

        return ldapTemplate.search(
            groupQuery,
            (AttributesMapper<String>) attrs ->
                String.valueOf(attrs.get("cn").get())
        );
    }
}
```

Giải thích:

1. `fullPersonDn(uid)` dựng **DN đầy đủ** của user, vì giá trị `member` trong schema nhóm thường là DN của entry thành viên. Đây là dữ liệu được so khớp trong filter; phân biệt với **search base tương đối** `ou=Groups`.
2. `.where("objectClass").is("groupOfNames")` chỉ chọn entry nhóm thuộc kiểu dự kiến.
3. `.and("member").is(memberDn)` yêu cầu một giá trị trong **tập `member`** khớp DN của người dùng.
4. Hai lần `.and("member").is(...)` yêu cầu nhóm có **cả hai DN**.
5. `.attributes("cn")` giới hạn dữ liệu trả về; không tải toàn bộ danh sách thành viên nếu chỉ cần tên nhóm.

`LdapQueryBuilder` dựng và escape filter theo ngữ cảnh LDAP. Tương tự, `LdapNameBuilder` xử lý DN theo cú pháp tên LDAP. **Hai bước xử lý khác nhau:** một bước tạo chuỗi DN hợp lệ, bước kia đưa chuỗi DN ấy thành **giá trị assertion của filter** an toàn.

### 8.2. Đọc đầy đủ các giá trị của attribute đa trị

Filter tìm nhóm trả về **entry**, nhưng khi ứng dụng cần hiển thị tất cả thành viên của một nhóm, phải duyệt các giá trị `member`. Không dùng `attrs.get("member").get()` rồi cho rằng đó là toàn bộ danh sách.

Ví dụ bổ sung phương thức sau vào lớp `GroupDirectory` ở mục 8.1 để dùng lại trường `ldapTemplate`. Phương thức dùng `lookup` theo DN tương đối:

```java
import java.util.ArrayList;
import java.util.List;
import javax.naming.Name;
import javax.naming.NamingException;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;

import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.support.LdapNameBuilder;

public List<String> listDirectMemberDns(String groupName) {
    Name groupDn = LdapNameBuilder.newInstance()
        .add("ou", "Groups")
        .add("cn", groupName)
        .build();

    return ldapTemplate.lookup(
        groupDn,
        (AttributesMapper<List<String>>) attrs -> {
            Attribute member = attrs.get("member");
            List<String> values = new ArrayList<>();
            if (member == null) {
                return values; // Thuộc tính có thể không được phép đọc.
            }
            for (int i = 0; i < member.size(); i++) {
                values.add(String.valueOf(member.get(i)));
            }
            return values;
        }
    );
}
```

Ở đây `groupDn` là tương đối với `ContextSource.base` đã cấu hình. `lookup` đọc entry theo DN, rồi `Attribute.size()` / `Attribute.get(i)` giúp lấy từng giá trị.

**Giới hạn:** thiếu `member` trong kết quả không đủ để chứng minh nhóm không có thành viên; ACL hoặc cách server trình bày attribute có thể che dữ liệu. Kết quả LDAP cũng không bảo đảm một thứ tự nghiệp vụ của các giá trị `member`. Khi hiển thị, có thể sắp xếp các DN trong ứng dụng theo tiêu chí rõ ràng.

### 8.3. Tìm theo hai địa chỉ email

Trên server có schema cho phép `mail` đa trị và hỗ trợ equality matching:

```java
LdapQuery q = query()
    .base("ou=People")
    .searchScope(SearchScope.SUBTREE)
    .where("mail").is("an@example.org")
    .and("mail").is("an.work@example.net");
```

Filter sinh ra mang ý nghĩa: **entry có cả hai địa chỉ trong tập giá trị `mail`**. Chúng là **hai giá trị có thể khác nhau**, không phải một địa chỉ thỏa hai phép so sánh bằng cùng lúc.

Nếu yêu cầu “có một trong hai địa chỉ”, dùng tổ hợp **OR** tương ứng (hoặc API dựng nhóm OR được phiên bản Spring LDAP đang dùng hỗ trợ). Khi truy vấn bằng `LdapClient`, vẫn cần giữ cùng ý nghĩa boolean của filter.

## 9. Escaping: giá trị filter khác giá trị DN

Một lỗi nghiêm trọng là tự nối dữ liệu người dùng vào chuỗi LDAP filter:

```java
// Tránh dùng: dữ liệu người dùng có thể thay đổi cú pháp filter.
String filter = "(mail=" + userInput + ")";
```

LDAP filter theo **RFC 4515** có những ký tự cần escape trong giá trị assertion:

| Ký tự dữ liệu | Escape trong filter |
| --- | --- |
| `*` | `\2a` |
| `(` | `\28` |
| `)` | `\29` |
| `\` | `\5c` |
| NUL | `\00` |

Ví dụ, nếu muốn tìm **chính xác** địa chỉ có ký tự `*` như `a*b@example.org` (nếu schema cho phép lưu giá trị đó), chuỗi filter cần là:

```text
(mail=a\2ab@example.org)
```

Còn `(mail=a*b@example.org)` là **substring filter**, vì dấu `*` chưa được escape mang ý nghĩa wildcard.

**Đừng lẫn với DN escaping (RFC 4514):** dấu phẩy thuộc giá trị RDN cần `\,` trong DN nhưng không nhất thiết cần escape như vậy trong một filter assertion value. Trái lại, dấu `*` rất đặc biệt trong filter nhưng không thuộc danh sách ký tự bắt buộc escape trong DN.

### 9.1. Khi giá trị `member` là DN có ký tự đặc biệt

Giả sử người dùng có DN với dấu phẩy trong `cn`:

```text
DN đầy đủ theo RFC 4514:
cn=Doe\, Jane,ou=People,dc=example,dc=org
```

Khi DN này được đưa vào **giá trị của LDAP filter**, dấu `\` vốn thuộc biểu diễn DN lại phải được escape theo **RFC 4515**:

```text
Filter string:
(member=cn=Doe\5c, Jane,ou=People,dc=example,dc=org)
```

Giải thích hai tầng:

1. `Doe\, Jane` là cách viết DN string biểu thị một `cn` chứa dấu phẩy.
2. `\5c` trong filter string biểu diễn dấu `\` thực tế của DN string đó, để LDAP server nhận giá trị assertion phù hợp.

Tốt nhất là để **`LdapNameBuilder` tạo DN** và **`LdapQueryBuilder` đưa DN vào filter**:

```java
Name personDn = LdapNameBuilder.newInstance()
    .add("dc", "org")
    .add("dc", "example")
    .add("ou", "People")
    .add("cn", "Doe, Jane")
    .build();

LdapQuery q = query()
    .base("ou=Groups")
    .where("member").is(personDn.toString());
```

Không tự thực hiện `replace` dấu phẩy, rồi dùng tiếp builder trên **giá trị đã escape** để tránh double escaping.

### 9.2. Giá trị thuộc tính không phải nơi biểu diễn ý đồ tìm kiếm

Nếu `userInput` chứa `*`, chọn rõ mục tiêu:

- Muốn **tìm đúng giá trị chứa dấu `*` thật**: dùng `.where("mail").is(userInput)` để builder escape ký tự dữ liệu.
- Muốn **tìm theo một mẫu substring**: dùng API biểu diễn substring/pattern theo ý đồ, hoặc cú pháp filter được tạo có kiểm soát; không cho dữ liệu đầu vào tự quyết định dấu nào là wildcard.

Đối với truy vấn lọc thành viên nhóm, dùng DN cụ thể với equality. Không sử dụng `(member=*an*)` như cách tìm user tên An khi schema DN không có substring matching rule.

## 10. Những hiểu nhầm cần tránh

| Cách nghĩ sai | Điều cần hiểu |
| --- | --- |
| “Nếu nhóm có mười `member` thì mười kết quả sẽ được trả về.” | Filter chọn **entry**; một nhóm khớp là một entry kết quả. |
| “`(member=An)` yêu cầu tất cả thành viên bằng An.” | Chỉ cần **ít nhất một giá trị** khớp An. |
| “`(&(member=An)(member=Binh))` bất khả thi vì một giá trị không thể vừa là An vừa là Bình.” | Hai điều kiện có thể khớp **hai giá trị khác nhau** của cùng một attribute. |
| “`(!(member=An))` khớp nhóm nào có một thành viên khác An.” | Filter yêu cầu **không có giá trị nào** khớp An. |
| “`(mail=*)` nghĩa là mail có nhiều giá trị.” | Presence chỉ kiểm tra attribute có xuất hiện, **không đếm** số giá trị. |
| “`(member=*an*)` tìm được DN thành viên chứa chữ An.” | DN attribute thường không có substring matching rule; hãy dùng equality trên DN đầy đủ. |
| “LDAP trả `member` theo đúng thứ tự nhập.” | Thứ tự các giá trị attribute đa trị không nên được giả định. |
| “`memberOf` luôn là trường LDAP có sẵn.” | Phụ thuộc server, schema, overlay và ACL. |
| “Filter đã đúng thì chắc chắn trả hết dữ liệu.” | Search base, scope, size/time limit, ACL và dữ liệu thực tế đều ảnh hưởng. |
| “Đã escape DN thì có thể nhúng thẳng vào filter.” | DN escaping và filter escaping là **hai cú pháp khác nhau**. |

## 11. Thực hành

Giả sử thư mục có các nhóm sau (mỗi giá trị là DN đầy đủ dưới `ou=People,dc=example,dc=org`):

| Nhóm | Thành viên |
| --- | --- |
| Engineering | An, Bình, Chi |
| Support | Bình |
| Product | Chi, Lan |
| Operations | Lan |

Mỗi nhóm là entry `groupOfNames` dưới `ou=Groups,dc=example,dc=org`. Giả sử mọi tài khoản truy vấn đều có quyền đọc các thuộc tính liên quan.

**Bài 1.** Nhóm nào khớp filter:

```text
(member=uid=binh,ou=People,dc=example,dc=org)
```

**Bài 2.** Nhóm nào khớp filter:

```text
(&(member=uid=an,ou=People,dc=example,dc=org)
  (member=uid=chi,ou=People,dc=example,dc=org))
```

**Bài 3.** Nhóm nào khớp filter:

```text
(|(member=uid=an,ou=People,dc=example,dc=org)
  (member=uid=lan,ou=People,dc=example,dc=org))
```

**Bài 4.** Nhóm nào khớp filter:

```text
(!(member=uid=binh,ou=People,dc=example,dc=org))
```

**Bài 5.** Một entry người dùng có hai giá trị `mail`: `an@example.org` và `an.work@example.net`. Entry có khớp `(&(mail=*@example.org)(mail=*@example.net))` không? Phải chăng cùng một địa chỉ thỏa cả hai điều kiện?

**Bài 6.** Một entry **không có** `mail`. Nó có khớp `(!(mail=an@example.org))` không, trong điều kiện server hỗ trợ bình thường cho thuộc tính `mail`? Làm sao chỉ chọn entry **có email nhưng không có địa chỉ An**?

**Bài 7.** Cho `ContextSource.base = dc=example,dc=org`. Muốn tìm nhóm chứa user có `uid = "an"`, nên đặt search base nào và tạo filter Spring LDAP thế nào để tránh tự nối chuỗi?

### Đáp án gợi ý

1. **Engineering** và **Support**: mỗi nhóm có giá trị `member` khớp Bình.
2. **Engineering**: có cả An và Chi; mỗi điều kiện tìm thấy một giá trị tương ứng.
3. **Engineering**, **Product** và **Operations**.
4. **Product** và **Operations**: hai nhóm không có Bình.
5. **Có**, vì một `mail` khớp `@example.org` và giá trị khác khớp `@example.net`; không cần cùng một chuỗi thỏa hai điều kiện.
6. **Có** với semantics equality thông thường; có thể dùng `(&(mail=*)(!(mail=an@example.org)))` để vừa yêu cầu `mail` hiện diện vừa loại địa chỉ An.
7. Dùng search base tương đối `ou=Groups`. Dùng `LdapNameBuilder` tạo DN `uid=an,ou=People,dc=example,dc=org`, sau đó `query().base("ou=Groups").where("objectClass").is("groupOfNames").and("member").is(personDn.toString())` để builder escape filter value.

## 12. Ghi nhớ

**Filter trên attribute đa trị đánh giá điều kiện ở cấp entry và thường chỉ cần một giá trị thỏa mỗi phép so khớp.** Nhiều điều kiện trong `AND` có thể được đáp ứng bởi **các giá trị khác nhau** của cùng attribute; `NOT` phủ định toàn bộ điều kiện “tồn tại giá trị khớp”, còn presence `(attr=*)` không cho biết số lượng giá trị.

Khi dùng Spring LDAP, hãy hiểu schema của `member`, `mail` và `objectClass`; chọn base/scope phù hợp; sử dụng `LdapNameBuilder` cho DN và `LdapQueryBuilder` cho filter; kiểm tra kết quả dưới quyền truy cập thực tế. Nếu cần đếm, sắp xếp hoặc áp đặt nhiều điều kiện **trên cùng một giá trị**, cần cân nhắc xử lý ở tầng ứng dụng thay vì suy diễn từ các filter độc lập.

### Tài liệu tham khảo

- [RFC 4511 — Lightweight Directory Access Protocol (LDAP): The Protocol](https://www.rfc-editor.org/rfc/rfc4511.html): mô hình `SearchRequest` và đánh giá filter, kể cả các trạng thái Undefined.
- [RFC 4512 — LDAP: Directory Information Models](https://www.rfc-editor.org/rfc/rfc4512.html): entry, attribute đa trị, schema và matching rule.
- [RFC 4515 — LDAP: String Representation of Search Filters](https://www.rfc-editor.org/rfc/rfc4515.html): cú pháp filter và escaping.
- [RFC 4514 — LDAP: String Representation of Distinguished Names](https://www.rfc-editor.org/rfc/rfc4514.html): cú pháp DN và escaping cho giá trị RDN.
- [Spring LDAP Reference Documentation](https://docs.spring.io/spring-ldap/reference/): `LdapTemplate`, `LdapClient`, query builder, ContextSource và tìm kiếm.
