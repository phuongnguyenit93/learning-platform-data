# Chẩn đoán filter đúng cú pháp nhưng sai logic trong Spring LDAP

Một LDAP filter có thể **hoàn toàn hợp lệ về cú pháp**, không gây exception, nhưng vẫn tìm sai người dùng: lọt tài khoản không đủ điều kiện, bỏ sót entry cần tìm, hoặc trả về quá nhiều bản ghi. Trong Spring LDAP, đây là lỗi khó nhận ra vì `LdapTemplate` hoặc `LdapClient` vẫn thực hiện truy vấn bình thường; kết quả sai đôi khi chỉ được phát hiện ở tầng nghiệp vụ.

Mục tiêu bài học là đọc được cây điều kiện logic, dự đoán kết quả tìm kiếm trên dữ liệu cụ thể, phân biệt lỗi logic filter với sai base DN, scope hoặc quyền đọc, rồi sửa truy vấn bằng API xây filter của Spring LDAP. Ví dụ áp dụng cho tìm kiếm trực tiếp bằng `LdapTemplate`, `LdapClient` và các luồng có ánh xạ `AttributesMapper`, `ContextMapper` hoặc ODM.

## 1. Cú pháp hợp lệ chưa nói gì về ý nghĩa nghiệp vụ

Xét filter sau:

```ldap
(|(&(objectClass=inetOrgPerson)(employeeType=staff)(ou=Engineering))(ou=Support))
```

Đây là một filter **đúng cú pháp LDAP**, nhưng nhóm thứ hai `(ou=Support)` không bị ràng buộc bởi `employeeType=staff`. Nếu nghiệp vụ yêu cầu “chỉ lấy nhân viên `staff` ở Engineering **hoặc** Support”, filter trên sẽ đưa vào kết quả cả người làm ở Support nhưng không phải staff.

Với LDAP, các toán tử logic cơ bản có dạng:

| Toán tử | Dạng filter | Diễn giải |
|---|---|---|
| AND | `(&(A)(B))` | Entry phải thỏa **cả A lẫn B**. |
| OR | Nhóm `OR` có hai toán hạng A và B | Entry thỏa **ít nhất một** trong A hoặc B. |
| NOT | `(!(A))` | Phủ định kết quả đánh giá A theo ngữ nghĩa filter LDAP. |
| Equality | `(uid=lan)` | Thuộc tính `uid` khớp assertion value theo matching rule của schema. |
| Presence | `(mail=*)` | Entry có thuộc tính `mail`. |
| Substring | `(cn=Lan*)` | Giá trị `cn` khớp mẫu bắt đầu bằng `Lan`, theo matching rule của thuộc tính. |

Dấu ngoặc là cấu trúc logic, không phải phần trang trí. `(&(A)(|(B)(C)))` nghĩa là **A AND (B OR C)**; còn `(|(&(A)(B))(C))` nghĩa là **(A AND B) OR C**. Hai biểu thức này không tương đương.

> Khi debugger báo “filter gửi thành công” hoặc log cho thấy filter đã encode, điều đó mới nói được rằng client đã tạo/gửi một biểu thức hợp lệ. Không có bảo đảm nào rằng biểu thức thể hiện đúng yêu cầu nghiệp vụ.

## 2. Dùng một tập dữ liệu giả làm “đáp án chuẩn”

Giả sử nhánh thư mục thử nghiệm có những entry thuộc `objectClass=inetOrgPerson` sau đây, với `employeeType` là giá trị quy ước của chính bộ dữ liệu giả (không phải một chuẩn LDAP về trạng thái tài khoản):

| Entry | `employeeType` | `ou` trên entry | Kết quả đúng? |
|---|---|---|---|
| `uid=lan` | `staff` | `Engineering` | **Có** |
| `uid=minh` | `staff` | `Support` | **Có** |
| `uid=hoa` | `contractor` | `Support` | Không |
| `uid=bao` | `staff` | `Sales` | Không |
| `uid=an` | Không có attribute | `Support` | Không |

Giả sử tất cả entry nằm trực tiếp dưới `ou=people,dc=example,dc=com`; tài khoản bind có quyền đọc và tìm trên các thuộc tính nêu trong bảng. Trong bài thực hành thật, cấu hình directory/schema và ACL phải hỗ trợ những giá trị này. Thuộc tính `ou` trong bảng là **thuộc tính của entry**, có thể độc lập với RDN hoặc OU chứa entry trong cây.

Yêu cầu nghiệp vụ:

> Chỉ tìm entry `inetOrgPerson` có `employeeType=staff` và `ou` bằng `Engineering` **hoặc** `Support`.

Filter đúng:

```ldap
(&(objectClass=inetOrgPerson)(employeeType=staff)(|(ou=Engineering)(ou=Support)))
```

Một filter sai nhưng vẫn hợp lệ:

```ldap
(|(&(objectClass=inetOrgPerson)(employeeType=staff)(ou=Engineering))(ou=Support))
```

| Entry | Filter **đúng** | Filter **sai** | Vì sao? |
|---|---:|---:|---|
| Lan | Có | Có | Staff ở Engineering. |
| Minh | Có | Có | Staff ở Support. |
| Hoa | Không | **Có** | Vế `(ou=Support)` của filter sai bỏ qua `employeeType`. |
| Bảo | Không | Không | Ở Sales. |
| An | Không | **Có** | Vế `(ou=Support)` của filter sai không buộc `employeeType` phải tồn tại. |

Sự khác biệt nằm ở cấu trúc AND/OR, không phải parser, DN hay mapper. Một phép tìm kiếm chỉ kiểm tra “có tìm được Lan không?” sẽ **không phát hiện bug** này vì cả hai filter đều tìm thấy Lan. Phải có dữ liệu **âm tính** như Hoa và An.

## 3. Đọc filter như cây điều kiện để thấy lỗi

Phân tích filter sai theo cây:

```text
OR
├── AND
│   ├── objectClass = inetOrgPerson
│   ├── employeeType = staff
│   └── ou = Engineering
└── ou = Support
```

Khi `ou=Support` đúng, cả biểu thức OR đúng **mà không cần** kiểm tra hai điều kiện còn lại. Trong khi đó, cây đúng là:

```text
AND
├── objectClass = inetOrgPerson
├── employeeType = staff
└── OR
    ├── ou = Engineering
    └── ou = Support
```

Quy trình đọc một filter dài:

1. Xác định **toán tử ở ngoặc ngoài cùng**: AND, OR hay NOT.
2. Đánh dấu mỗi toán hạng con hoàn chỉnh, không cắt theo vị trí dấu ngoặc một cách cơ học.
3. Viết lại bằng câu tiếng Việt có dấu ngoặc: “A **và** (B **hoặc** C)”.
4. Với mỗi nhánh OR, hỏi: “Nếu **chỉ riêng nhánh này** đúng, entry có bị lọt vào kết quả không?”.
5. Tạo ít nhất một entry **đáng lẽ bị loại** cho mỗi nhánh, rồi so sánh kết quả thực với dự kiến.

Một công thức kiểm tra đặc biệt hữu ích: nếu mọi kết quả đều phải có điều kiện `P` thì biểu thức thường cần giữ `P` ở **ngoài** nhóm OR, ví dụ `(&(P)(|(Q)(R)))`.

## 4. Các lỗi logic điển hình dù filter vẫn hợp lệ

### 4.1. Dùng AND khi nghiệp vụ yêu cầu OR

```ldap
(&(ou=Engineering)(ou=Support))
```

Filter này tìm entry có cả hai giá trị `ou`. Nó không có nghĩa “thuộc một trong hai bộ phận”. Trong một số schema, attribute có thể đa giá trị nên không được khẳng định luôn trả 0; tuy nhiên, với dữ liệu mẫu mỗi entry có một `ou`, kết quả là 0.

Nếu mục tiêu là Engineering **hoặc** Support:

```ldap
(|(ou=Engineering)(ou=Support))
```

Nếu vẫn cần điều kiện `employeeType=staff`, nhóm OR phải nằm **bên trong** AND như ví dụ trước.

### 4.2. Đặt NOT quá rộng hoặc quên điều kiện tồn tại

```ldap
(!(employeeType=contractor))
```

Biểu thức này **không đồng nghĩa** với `(employeeType=staff)`. Ngoài `staff`, directory có thể có `intern`, `external` hoặc entry thiếu thuộc tính. Đánh giá filter của LDAP còn có thể có giá trị **Undefined** khi matching rule hoặc attribute không thể được đánh giá; không được tự suy ra rằng NOT luôn biến mọi tình huống không tìm thấy thành TRUE.

Nếu chỉ muốn staff, hãy viết đúng điều kiện `(employeeType=staff)`. Nếu yêu cầu là “có employeeType và không phải contractor”, diễn đạt đầy đủ:

```ldap
(&(employeeType=*)(!(employeeType=contractor)))
```

Hai yêu cầu nghiệp vụ này khác nhau. Không thay chúng cho nhau mà chưa có dữ liệu kiểm thử và quy tắc xử lý entry thiếu thuộc tính.

### 4.3. Lẫn equality, substring và presence

| Filter | Nghĩa thực tế | Lỗi nghiệp vụ có thể xảy ra |
|---|---|---|
| `(uid=lan)` | So khớp giá trị theo equality matching rule | Đúng khi tìm mã định danh cụ thể. |
| `(uid=lan*)` | Substring bắt đầu bằng `lan` | Có thể trả thêm `lan2` hoặc `lan-admin`. |
| `(uid=*lan*)` | Substring có `lan` ở vị trí bất kỳ | Có thể trả cả `tuanlan`; phạm vi rộng hơn. |
| `(uid=*)` | Presence, chỉ cần có `uid` | Không còn giới hạn theo một mã định danh. |
| `(uid=lan\2a)` | Giá trị `lan*` với dấu sao **literal** | Không tương đương tìm `lan` và các hậu tố. |

Trong RFC 4515, `*` **không được escape** ở vị trí mẫu substring hoặc presence; dấu sao **thuộc giá trị literal** phải được escape thành `\2a`. Những ký tự `(`, `)`, dấu gạch chéo ngược và byte NUL cũng cần escape tương ứng. Việc “encode” không tự biết nghiệp vụ muốn equality hay prefix search: lập trình viên phải chọn đúng loại điều kiện.

Ví dụ: người dùng nhập `lan*` để **tìm chính username chứa dấu sao** thì phải dùng equality filter với giá trị `lan*` được escape; nếu UI hỗ trợ **tìm theo tiền tố** thì phải tạo substring filter có dấu `*` mang ý nghĩa wildcard do ứng dụng kiểm soát. Tránh nối trực tiếp raw input vào filter.

### 4.4. Chọn objectClass rộng hơn ý định

```ldap
(objectClass=person)
```

Filter này có thể khớp những entry có `objectClass=person` vì objectClass đó nằm trong chuỗi kế thừa của một loại entry cụ thể. Nếu ứng dụng chỉ được phép xử lý `inetOrgPerson`, `(objectClass=person)` có thể rộng quá mức. Khi kiểm tra, xem **objectClass thực nhận** và schema thay vì mặc định rằng một tên class chỉ đại diện một loại dữ liệu ứng dụng.

### 4.5. Giả định so khớp là so chuỗi Java

LDAP không nhất thiết so sánh theo `String.equals()`. Mỗi attribute có thể có **equality/substrings/ordering matching rules** quy định cách chuẩn hóa chữ hoa thường, khoảng trắng và kiểu dữ liệu.

Ví dụ, với một attribute sử dụng `caseIgnoreMatch`, `(cn=LAN NGUYEN)` có thể khớp `cn: Lan Nguyen`; với thuộc tính dùng `caseExactMatch` thì kết quả có thể khác. Không tự `toLowerCase()` mọi giá trị hoặc coi đây là lỗi Spring LDAP nếu kết quả không giống phép so sánh của Java. Hãy kiểm tra schema/matching rule của đúng LDAP server.

## 5. Phân biệt lỗi filter với base DN, scope và quyền truy cập

Cùng một filter đúng có thể cho kết quả khác nhau vì **vùng tìm kiếm** hoặc ACL:

```text
dc=example,dc=com
└── ou=people
    ├── uid=lan
    └── ou=partners
        └── uid=minh
```

Nếu `uid=minh` nằm dưới `ou=partners`, tìm kiếm bắt đầu tại `ou=people` với `ONELEVEL` sẽ không thấy Minh. Đổi thành `SUBTREE` hoặc chọn base tương ứng mới đúng phạm vi mong muốn.

Cần phân biệt bốn câu hỏi:

| Câu hỏi | Nếu sai, cần xem |
|---|---|
| Client có bind/kết nối được không? | `ContextSource`, TLS, URL, credentials, pooling. |
| Base DN hiệu lực có chỉ đúng nhánh không? | `ContextSource.base` và base tương đối trong `LdapTemplate` hoặc `LdapClient`. |
| Search scope có quét tới đúng độ sâu không? | `ONELEVEL`, `SUBTREE`, `OBJECT`; giới hạn trả về và referral. |
| Trong tập entry có thể xét, filter có chọn đúng không? | Nhóm AND/OR/NOT, presence, wildcard, matching rule, ACL. |

**Phép thử có ý nghĩa:** giữ nguyên server, bind identity, base, scope và danh sách thuộc tính yêu cầu, chỉ đổi **một filter**. Nếu cần thay scope, ghi đó là một phép thử khác. Đừng nhìn danh sách rỗng mà kết luận ngay “AND sai”; thiếu quyền tìm kiếm hoặc entry nằm ngoài scope có biểu hiện tương tự.

## 6. Kiểm chứng bằng `ldapsearch` trên dữ liệu giả

Khi có bộ dữ liệu kiểm thử như ở mục 2, hãy chạy hai filter trên **cùng server, cùng bind DN, cùng base và scope**. Trong `ldapsearch`, `-b` nhận DN đầy đủ:

```bash
# Filter đúng: staff và một trong hai bộ phận.
ldapsearch -LLL -x \
  -H ldaps://ldap.example.com:636 \
  -D "uid=reader,ou=service,dc=example,dc=com" -W \
  -b "ou=people,dc=example,dc=com" -s one \
  '(&(objectClass=inetOrgPerson)(employeeType=staff)(|(ou=Engineering)(ou=Support)))' dn
```

```bash
# Filter sai: nhánh Support bỏ qua employeeType.
ldapsearch -LLL -x \
  -H ldaps://ldap.example.com:636 \
  -D "uid=reader,ou=service,dc=example,dc=com" -W \
  -b "ou=people,dc=example,dc=com" -s one \
  '(|(&(objectClass=inetOrgPerson)(employeeType=staff)(ou=Engineering))(ou=Support))' dn
```

Các ví dụ dùng cú pháp shell kiểu Bash; cách đặt dấu nháy ở PowerShell có thể khác. `-W` yêu cầu nhập mật khẩu, tránh ghi secret trong lịch sử lệnh; `ldaps://` yêu cầu xác thực CA/chứng chỉ hợp lệ. Dùng danh tính kiểm thử có quyền phù hợp; không đăng kết quả DN chứa danh tính thật vào log công khai.

Với dữ liệu mục 2, filter đúng sẽ trả Lan và Minh, filter sai trả thêm Hoa và An. Khi khám phá sai khác, **đếm và đối chiếu** các entry tìm được trên directory test, không dựa vào việc câu lệnh kết thúc với mã thành công.

Có thể kiểm chứng một điều kiện mỗi lần bằng các filter phụ:

```ldap
(objectClass=inetOrgPerson)
(employeeType=staff)
(|(ou=Engineering)(ou=Support))
```

Đây là **ba lần tìm kiếm riêng** để kiểm tra từng tập con, không phải ba filter được nối liền trong một request. Sau đó hợp chúng theo yêu cầu nghiệp vụ. Nếu một filter đơn không khớp như kỳ vọng, kiểm tra thuộc tính và matching rule trước khi thay đổi nhóm AND/OR.

## 7. Viết filter đúng bằng API Spring LDAP

Với dữ liệu động, sử dụng `LdapQueryBuilder` hoặc bộ lọc của `org.springframework.ldap.filter` để tránh nối chuỗi đầu vào. Ví dụ đơn giản chỉ có AND:

```java
import java.util.List;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;
import org.springframework.ldap.query.SearchScope;

public final class StaffDirectory {
    private final LdapTemplate ldapTemplate;

    public StaffDirectory(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public int countStaffInDepartment(String department) {
        LdapQuery query = LdapQueryBuilder.query()
                .base("ou=people")
                .searchScope(SearchScope.ONELEVEL)
                .where("objectClass").is("inetOrgPerson")
                .and("employeeType").is("staff")
                .and("ou").is(department);

        List<Boolean> entries = ldapTemplate.search(
                query,
                (AttributesMapper<Boolean>) attrs -> Boolean.TRUE);
        return entries.size();
    }
}
```

Giả định `ContextSource.base=dc=example,dc=com`. Giá trị `department` được builder escape theo yêu cầu của equality filter; nếu input chứa dấu sao literal, đừng vô tình chuyển nó thành substring wildcard. Mã không log input và mapper chỉ đếm kết quả, giúp tách logic filter khỏi lỗi ánh xạ thuộc tính nghiệp vụ.

Với yêu cầu `AND` chứa một nhóm `OR`, có thể dựng cây filter rõ ràng:

```java
import java.util.List;
import javax.naming.directory.SearchControls;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.filter.AndFilter;
import org.springframework.ldap.filter.EqualsFilter;
import org.springframework.ldap.filter.OrFilter;

public final class StaffFilterProbe {
    public static int countStaffInEitherDepartment(
            LdapTemplate ldapTemplate,
            String departmentA,
            String departmentB) {
        OrFilter departments = new OrFilter();
        departments.or(new EqualsFilter("ou", departmentA));
        departments.or(new EqualsFilter("ou", departmentB));

        AndFilter allConditions = new AndFilter();
        allConditions.and(new EqualsFilter("objectClass", "inetOrgPerson"));
        allConditions.and(new EqualsFilter("employeeType", "staff"));
        allConditions.and(departments);

        // String encode() chứa dữ liệu thật; chỉ dùng cho request, không ghi log.
        String filterForRequest = allConditions.encode();

        List<Boolean> matches = ldapTemplate.search(
                "ou=people",
                filterForRequest,
                SearchControls.ONELEVEL_SCOPE,
                (AttributesMapper<Boolean>) attrs -> Boolean.TRUE);
        return matches.size();
    }
}
```

Trong ví dụ này, `EqualsFilter` xử lý escape giá trị theo LDAP filter. Bản thân bộ dựng **không sửa được** logic nếu lập trình viên đặt `OrFilter` sai vị trí: cấu trúc `allConditions.and(departments)` mới bảo đảm cả hai nhánh OR đều phải thỏa điều kiện staff và objectClass.

Có thể thay `LdapTemplate` bằng `LdapClient` nếu ứng dụng dùng API đó; nguyên tắc vẫn là giữ **base**, **scope** và **cây filter** đúng yêu cầu. Nếu kết quả đã đúng với mapper đơn giản nhưng sai sau khi chuyển thành DTO/entity, tiếp tục debug `AttributesMapper`, `ContextMapper` hoặc ODM, thay vì sửa lại filter.

## 8. Chẩn đoán từng bước khi kết quả sai

Thực hiện trên directory test hoặc môi trường chẩn đoán được cho phép:

1. **Viết điều kiện nghiệp vụ thành biểu thức rõ ràng.** Ví dụ: “`objectClass=inetOrgPerson` **và** `employeeType=staff` **và** (`ou=Engineering` **hoặc** `ou=Support`)”.
2. **Vẽ cây filter thực tế.** Lấy cấu trúc của builder hoặc filter đã encode trong môi trường test dùng input giả; đối chiếu từng nhánh với biểu thức mong muốn.
3. **Tạo bộ entry dương tính và âm tính.** Có người thỏa toàn bộ điều kiện, người chỉ thỏa một nhánh OR, người thiếu attribute, người có giá trị chứa dấu sao. Mỗi trường hợp phải có expected match.
4. **Xác nhận vùng truy vấn.** Ghi nhận base DN hiệu lực, scope, endpoint và bind identity; giữ các giá trị này cố định khi so sánh logic.
5. **Chạy filter nhỏ trước.** Thử từng điều kiện một, sau đó AND hai điều kiện, cuối cùng thêm nhóm OR/NOT để tìm bước làm thay đổi kết quả ngoài ý muốn.
6. **Dùng mapper tối giản để đếm entry.** Với `LdapTemplate`, `(AttributesMapper<Boolean>) attrs -> Boolean.TRUE` cho phép kiểm tra tìm kiếm trước khi đụng các field nghiệp vụ.
7. **Đối chiếu mapper và giới hạn kết quả.** Nếu tìm đúng entry nhưng DTO sai, kiểm tra returning attributes và mapper. Nếu chỉ mất entry ở kết quả lớn, xem size/time limit, phân trang và ACL.
8. **Ghi lại bản sửa kèm ví dụ phản chứng.** Không chỉ xác nhận Lan và Minh được trả về; còn phải chứng minh Hoa và An đã bị loại.

Bảng phân loại triệu chứng:

| Triệu chứng | Giả thuyết filter | Phép phản chứng |
|---|---|---|
| Kết quả có người `contractor` ở Support | OR thoát khỏi AND bắt buộc | Đặt `employeeType=staff` ngoài nhóm OR; kiểm tra Hoa bị loại. |
| Trả 0 dù có người ở Engineering và Support | Dùng AND thay OR giữa hai giá trị | Thử `(|(ou=Engineering)(ou=Support))`. |
| Có nhiều username cùng tiền tố | `uid=lan*` đang là substring | Thử equality `(uid=lan)` và mẫu dữ liệu `lan2`. |
| Người không có `employeeType` được xử lý ngoài ý định | Logic NOT/presence chưa diễn đạt đủ | Thử entry thiếu field; thêm presence nếu nghiệp vụ yêu cầu. |
| Filter hoạt động khác giữa hai loại directory | Matching rule hoặc schema khác nhau | Kiểm tra attribute type và matching rule trên từng server. |
| Filter đúng trong `ldapsearch` nhưng ứng dụng trả khác | Khác base/scope/bind/limits hoặc mapper | Chạy cùng filter, base, scope, tài khoản với mapper tối giản. |
| Một số entry biến mất khi tăng quy mô dữ liệu | Size/time limit, pagination, ACL hoặc quá tải | Kiểm tra controls, mã lỗi và số trang; không thay AND/OR ngay. |

## 9. Logging và bảo mật khi debug logic filter

Filter đã được `encode()` vẫn có thể chứa email, username, mã nhân viên hoặc điều kiện truy vấn nhạy cảm. **Escape RFC 4515 bảo vệ cú pháp, không che thông tin**. Vì thế không đưa trực tiếp `filter.encode()`, `query.toString()`, toàn bộ DN hoặc exception message vào log production.

Bản log chẩn đoán nên dùng metadata cố định, ví dụ:

```text
ldap.search operationId=people.staffByDepartment
filterId=staff.inSelectedDepartments.v2
baseId=people scope=ONELEVEL
logicalShape="AND(objectClass, employeeType, OR(ou, ou))"
outcome=ok resultCount=2 elapsedMs=14
```

`logicalShape` là chuỗi cố định, được thiết kế riêng cho logging, không phải bản serialize filter thật. Với dữ liệu nhạy cảm, ngay cả `resultCount` cũng cần được cân nhắc theo chính sách quyền xem log. Nếu cần kiểm tra escape từng ký tự, dùng **input giả** trên môi trường test thay vì log dữ liệu thật.

Đồng thời bảo đảm không có logger mức DEBUG/TRACE ở tầng JNDI, Spring LDAP hay gateway phát ra filter thật hoặc nội dung entry một cách ngoài dự kiến. Khi lỗi xác thực, TLS hoặc pooling xuất hiện, hãy chẩn đoán `ContextSource` độc lập; không thay logic filter để “sửa” lỗi kết nối.

## 10. Bài thực hành có đáp án

Giả sử dữ liệu ở mục 2 và tất cả entry đều có thể được tìm thấy trong cùng base/scope. Với từng filter, tự dự đoán danh sách UID trước khi chạy LDAP test server:

Sáu filter cần đánh giá (mỗi dòng là **một** biểu thức độc lập):

- **F1:** `(&(employeeType=staff)(ou=Engineering))`
- **F2:** `(|(ou=Engineering)(ou=Support))`
- **F3:** `(&(employeeType=staff)(|(ou=Engineering)(ou=Support)))`
- **F4:** `(|(&(employeeType=staff)(ou=Engineering))(ou=Support))`
- **F5:** `(&(employeeType=staff)(ou=Engineering)(ou=Support))`
- **F6:** `(employeeType=*)`

| Filter | UID dự kiến | Lý do |
|---|---|---|
| **F1** | `lan` | Staff ở Engineering. |
| **F2** | `lan`, `minh`, `hoa`, `an` | Không kiểm tra employeeType. |
| **F3** | `lan`, `minh` | Đúng điều kiện staff và một trong hai OU. |
| **F4** | `lan`, `minh`, `hoa`, `an` | Nhánh Support bỏ qua staff. |
| **F5** | Không có | Dữ liệu mẫu có một giá trị `ou` mỗi entry. |
| **F6** | `lan`, `minh`, `hoa`, `bao` | An không có employeeType. |

**Bài tập mở rộng:** thêm `uid=lan2` là staff ở Engineering. So sánh `(uid=lan)`, `(uid=lan*)` và `(uid=lan\2a)` khi hệ thống có hoặc không có username chứa dấu `*` thật. Tiếp tục thêm một entry có hai giá trị `ou` và giải thích vì sao `(&(ou=Engineering)(ou=Support))` có thể khớp entry này, dù trong bộ dữ liệu ban đầu kết quả là 0.

**Câu hỏi tự kiểm tra:** Khi filter trả về 0 entry, cần có bằng chứng gì trước khi kết luận lỗi logic AND/OR? Câu trả lời: xác nhận kết nối/bind, base DN hiệu lực, scope, quyền tìm kiếm và sự tồn tại của entry trong test dataset; sau đó chứng minh **từng điều kiện thành phần** có hành vi đúng với matching rule của server.

## 11. Checklist khi sửa filter

- [ ] Biểu thức bằng lời đã xác định rõ nhóm AND/OR và điều kiện bắt buộc.
- [ ] Mỗi nhánh OR được kiểm thử với một entry **đáng lẽ phải bị loại**.
- [ ] NOT được diễn đạt theo ý định về attribute thiếu hoặc giá trị không khớp.
- [ ] Equality, substring và presence được chọn đúng theo chức năng tìm kiếm.
- [ ] Giá trị input được escape bằng builder hoặc `Filter`; không nối raw input vào filter.
- [ ] Base DN, scope, ACL và matching rule được kiểm chứng độc lập.
- [ ] Đã so sánh kết quả với mapper đơn giản trước khi đánh giá mapper nghiệp vụ.
- [ ] Log chứa mã truy vấn và cấu trúc đã ẩn dữ liệu, không chứa filter thật.
- [ ] Kiểm thử gồm cả kết quả **đúng phải xuất hiện** và **sai phải bị loại**.

Một filter LDAP đúng phải **vừa hợp lệ về cú pháp, vừa diễn đạt đúng điều kiện nghiệp vụ**. Trong Spring LDAP, API builder giúp escape giá trị và tạo cấu trúc rõ ràng, nhưng không thay thế việc kiểm tra chân trị, cây điều kiện và bộ dữ liệu phản chứng. Debug filter bằng cách cố định base/scope/bind, kiểm tra từng nhánh logic và dùng dữ liệu giả có cả trường hợp dương tính lẫn âm tính.
