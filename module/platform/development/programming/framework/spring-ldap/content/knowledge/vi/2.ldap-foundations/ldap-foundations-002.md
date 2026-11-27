# Entry, Distinguished Name (DN) và Relative Distinguished Name (RDN)

Khi làm việc với dịch vụ thư mục qua **Spring LDAP**, phần lớn thao tác đều bắt đầu từ câu hỏi: *entry nào cần đọc hoặc cập nhật, và entry đó nằm ở đâu trong cây LDAP?* Ba khái niệm **entry**, **Distinguished Name (DN)** và **Relative Distinguished Name (RDN)** giúp trả lời chính xác câu hỏi ấy. Hiểu chúng trước khi sử dụng `LdapTemplate`, `LdapClient` hay ánh xạ đối tượng (ODM) sẽ tránh được nhiều lỗi tìm kiếm sai nhánh, trùng tên và tạo entry ở nhầm vị trí.

Sau bài này, bạn có thể:

- Nhận diện một LDAP entry, các thuộc tính và mối liên hệ với schema (`objectClass`).
- Đọc một DN từ entry đi lên các nhánh cha; xác định RDN và DN của entry cha.
- Phân biệt DN đầy đủ với DN tương đối theo `base` đã cấu hình cho Spring LDAP.
- Tạo DN an toàn từ giá trị động, và hiểu ảnh hưởng của đổi tên hoặc di chuyển entry.

## 1. Entry: đơn vị dữ liệu trong thư mục LDAP

LDAP tổ chức dữ liệu thành **Directory Information Tree (DIT)**, một cây mà mỗi nút là một **entry**. Một entry có:

1. **Tên định danh (DN):** chỉ ra vị trí của entry trong cây.
2. **Tập thuộc tính (attributes):** các cặp tên thuộc tính và một hoặc nhiều giá trị, chẳng hạn `cn`, `sn`, `uid`, `mail`.
3. **Lớp đối tượng (`objectClass`):** xác định quy tắc schema áp dụng, trong đó có thuộc tính bắt buộc hoặc được phép.

Ví dụ, một entry người dùng có thể chứa:

| Thành phần | Giá trị minh họa | Ý nghĩa |
| --- | --- | --- |
| `uid` | `lan` | Mã định danh người dùng trong entry này. |
| `cn` | `Lan Nguyen` | Tên hiển thị/common name. |
| `sn` | `Nguyen` | Họ; thuộc tính bắt buộc của lớp `person`. |
| `mail` | `lan@example.org` | Địa chỉ email. |
| `objectClass` | `inetOrgPerson` và các lớp cha | Các ràng buộc schema của entry. |
| DN | `uid=lan,ou=people,dc=example,dc=org` | Tên phân biệt dùng để định vị entry trong DIT. |

Một số thuộc tính cho phép **nhiều giá trị**; ví dụ một người có thể có nhiều `telephoneNumber`. Schema và quy tắc tương ứng quyết định thuộc tính nào được phép dùng và dạng giá trị hợp lệ. Không nên coi mỗi entry là một hàng có các cột cố định như trong cơ sở dữ liệu quan hệ.

### Ví dụ dữ liệu LDIF

Đoạn LDIF dưới đây mô tả hai entry. Giả sử nhánh gốc `dc=example,dc=org` đã tồn tại trên máy chủ LDAP:

```ldif
dn: ou=people,dc=example,dc=org
objectClass: top
objectClass: organizationalUnit
ou: people

dn: uid=lan,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: lan
cn: Lan Nguyen
sn: Nguyen
mail: lan@example.org
```

Trong LDIF, dòng `dn:` nêu **tên của entry**; nó không có nghĩa máy chủ phải lưu một thuộc tính người dùng thông thường tên `dn`. Các dòng `objectClass`, `uid`, `cn`, `sn` và `mail` mô tả thuộc tính của entry. Entry `uid=lan,...` nằm dưới entry `ou=people,...`; nhánh cha cần tồn tại trước khi thêm entry con.

## 2. DN: đường định danh duy nhất của entry

**Distinguished Name (DN)** là chuỗi gồm các RDN nối bằng dấu phẩy, biểu diễn tên của entry từ **nút hiện tại hướng về gốc cây**.

```text
uid=lan,ou=people,dc=example,dc=org
│       │         │          │
│       │         │          └─ RDN ở nhánh cao hơn: dc=org
│       │         └──────────── RDN: dc=example
│       └────────────────────── RDN: ou=people
└────────────────────────────── RDN của entry: uid=lan
```

DN trên mô tả đường đi:

```text
dc=example,dc=org
└── ou=people
    └── uid=lan
```

Các thành phần thường gặp:

| Ký hiệu | Tên đầy đủ | Thường biểu diễn |
| --- | --- | --- |
| `dc` | Domain Component | Một thành phần của tên miền, ví dụ `dc=example`. |
| `ou` | Organizational Unit | Đơn vị hoặc nhánh nhóm entry, ví dụ `ou=people`. |
| `o` | Organization | Tên tổ chức khi schema và cách tổ chức DIT sử dụng. |
| `cn` | Common Name | Tên phổ biến, thường dùng cho người hoặc nhóm. |
| `uid` | User ID | Mã người dùng, thường được chọn làm thuộc tính đặt tên. |

Các thuộc tính này chỉ là **quy ước đặt tên phổ biến**, không phải cấu trúc cố định mà mọi máy chủ LDAP buộc phải theo. Ví dụ Active Directory thường có entry người dùng mang RDN dạng `cn=...`, còn một thư mục khác có thể dùng `uid=...`.

**Tính duy nhất:** trong cùng một cây thư mục, hai entry đang tồn tại không thể có cùng DN. Tuy nhiên `uid=lan` có thể xuất hiện ở hai nhánh khác nhau:

```text
uid=lan,ou=employees,dc=example,dc=org
uid=lan,ou=contractors,dc=example,dc=org
```

Đây là hai DN khác nhau dù có cùng RDN `uid=lan`. Vì thế chỉ biết `uid` chưa chắc đủ để xác định một entry trên toàn thư mục. Tính tương đương khi so sánh các giá trị thuộc tính còn phụ thuộc quy tắc matching của LDAP schema; không nên dựa hoàn toàn vào so sánh chuỗi DN bằng `equals` trên Java `String`.

## 3. RDN: tên của entry so với entry cha

**Relative Distinguished Name (RDN)** là phần tên dùng để phân biệt một entry với các entry **cùng cha**. Trong DN của một entry thông thường, RDN của chính entry nằm ở phía **trái nhất**:

```text
DN:           uid=lan,ou=people,dc=example,dc=org
RDN:          uid=lan
DN của cha:           ou=people,dc=example,dc=org
```

Một RDN đơn giản có dạng `attributeType=attributeValue`, ví dụ `uid=lan`, `ou=people` hoặc `cn=Lan Nguyen`. Thuộc tính và giá trị được chọn cho RDN phải phù hợp với schema và phải hiện diện trong entry. Trong cùng một nhánh cha, RDN phải phân biệt được các entry con.

RDN **không nhất thiết chỉ có một cặp** thuộc tính–giá trị. LDAP cho phép RDN đa trị; các cặp được nối bằng dấu `+`:

```text
cn=Lan Nguyen+uid=lan,ou=people,dc=example,dc=org
```

Ở ví dụ này, `cn=Lan Nguyen+uid=lan` là **một RDN đa trị**, còn `ou=people`, `dc=example`, `dc=org` là ba RDN tiếp theo. Dấu `+` không có nghĩa tạo thêm một cấp trong cây; các cặp trong RDN đa trị không có thứ tự ngữ nghĩa cố định. Cả `cn` và `uid` tương ứng phải có trong entry và cách đặt tên này phải được server chấp nhận.

### Đối chiếu nhanh DN và RDN

| Tiêu chí | DN | RDN |
| --- | --- | --- |
| Phạm vi | Định danh entry trong cả DIT tương ứng. | Phân biệt entry trong phạm vi cùng cha. |
| Thành phần | Một chuỗi RDN từ entry lên phía gốc. | Một hoặc nhiều cặp `thuộc tính=giá trị`. |
| Ví dụ | `uid=lan,ou=people,dc=example,dc=org` | `uid=lan` |
| Khi nào dùng | Đọc, sửa, xóa, bind hoặc định vị entry. | Xác định tên cục bộ, tạo tên cho entry con, đổi tên entry. |

## 4. Ba khái niệm dễ nhầm: DN, base DN và bind DN

Khi truy cập LDAP bằng ứng dụng Spring, thuật ngữ **base DN** có thể xuất hiện trong hai ngữ cảnh:

- **Naming base / search base:** nhánh gốc được dùng làm điểm bắt đầu khi tìm kiếm. Ví dụ tìm dưới `ou=people,dc=example,dc=org` sẽ không tự bao gồm người dùng ở `ou=contractors,dc=example,dc=org`.
- **ContextSource base:** phần hậu tố DN mà Spring LDAP cấu hình chung, thường là `dc=example,dc=org`; nhiều API `LdapTemplate` nhận tên **tương đối so với base này**.

**Bind DN** lại là tên đầy đủ của tài khoản được dùng để xác thực với server (ví dụ `uid=svc-reader,ou=service,dc=example,dc=org`). Nó thể hiện **danh tính kết nối**; không đồng nghĩa với base DN hay DN của entry đang tra cứu.

Giả sử cấu hình Spring LDAP có base `dc=example,dc=org`:

| Mục đích | DN |
| --- | --- |
| ContextSource base | `dc=example,dc=org` |
| DN đầy đủ của Lan | `uid=lan,ou=people,dc=example,dc=org` |
| Tên tương đối dùng cho `LdapTemplate` | `uid=lan,ou=people` |
| Search base tương đối | `ou=people` |

Trong trường hợp này, nếu truyền cả `dc=example,dc=org` vào API vốn nhận tên tương đối, ứng dụng có thể ghép hậu tố hai lần và đi đến DN sai. Hãy xác nhận API và `ContextSource` đang xử lý tên theo phạm vi nào trước khi truyền `Name` hoặc DN dạng chuỗi.

## 5. Đọc và dựng DN an toàn trong Java và Spring LDAP

DN có các quy tắc phân tích và escaping riêng. Tránh ghép chuỗi tùy ý bằng `"uid=" + userInput + ",ou=people,..."`, nhất là khi giá trị đến từ người dùng.

### Dùng lớp chuẩn JNDI để phân tích DN

```java
import javax.naming.ldap.LdapName;
import javax.naming.ldap.Rdn;

LdapName fullDn = new LdapName(
    "uid=lan,ou=people,dc=example,dc=org"
);

// LdapName đánh chỉ số RDN từ gốc về phía entry.
Rdn entryRdn = fullDn.getRdn(fullDn.size() - 1);

System.out.println(entryRdn);          // uid=lan
System.out.println(entryRdn.getType()); // uid
System.out.println(entryRdn.getValue());// lan
```

Lưu ý: chuỗi DN hiển thị từ **entry đến gốc**, nhưng `LdapName.getRdn(0)` là RDN **phía gốc**. Nếu nhầm quy tắc chỉ số này, bạn có thể lấy `dc=org` trong khi muốn lấy `uid=lan`.

### Dùng `LdapNameBuilder` để tạo DN từ giá trị động

```java
import javax.naming.Name;
import org.springframework.ldap.support.LdapNameBuilder;

String userId = "lan"; // Có thể là dữ liệu nhập vào

// DN tương đối khi ContextSource đã có base dc=example,dc=org.
Name relativeDn = LdapNameBuilder.newInstance()
    .add("ou", "people")
    .add("uid", userId)
    .build();

System.out.println(relativeDn); // uid=lan,ou=people
```

`LdapNameBuilder` dựng tên bằng các thành phần DN và xử lý escaping của giá trị RDN. Nếu `userId` chứa ký tự đặc biệt, builder giúp tránh biến giá trị đó thành một RDN hoặc một cấp cây khác ngoài ý muốn.

Ví dụ một entry có giá trị `cn` thực tế là `Nguyen, Lan` (chứa dấu phẩy). Khi biểu diễn DN bằng văn bản theo cú pháp RFC 4514, dấu phẩy bên trong **giá trị** phải được escape:

```text
cn=Nguyen\, Lan,ou=people,dc=example,dc=org
```

Ở đây `Nguyen, Lan` là **một giá trị `cn`**, không phải hai RDN. Các trường hợp cần xử lý đặc biệt còn gồm dấu `+`, `"`, `\`, `<`, `>`, `;`, `=`, khoảng trắng đầu/cuối và ký tự `#` ở đầu giá trị. Khi cần dựng DN trong code, ưu tiên các API thao tác `Name`/`Rdn` thay vì tự viết hàm thay thế ký tự.

### Dùng tên tương đối với `LdapTemplate`

Ví dụ dưới đây giả định ứng dụng Spring Boot cấu hình LDAP base là `dc=example,dc=org` và bean `ldapTemplate` đã được cung cấp:

```yaml
spring:
  ldap:
    urls: ldaps://ldap.example.org:636
    base: dc=example,dc=org
    username: uid=svc-reader,ou=service,dc=example,dc=org
    password: ${LDAP_BIND_PASSWORD}
```

```java
import javax.naming.Name;
import javax.naming.directory.Attributes;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

// Trong một service có LdapTemplate được inject:
Name relativeDn = LdapNameBuilder.newInstance()
    .add("ou", "people")
    .add("uid", "lan")
    .build();

String displayName = ldapTemplate.lookup(
    relativeDn,
    (AttributesMapper<String>) attrs ->
        (String) attrs.get("cn").get()
);
```

`lookup` định vị **một entry bằng DN**. Một đối tượng không tồn tại tại DN này thường dẫn đến ngoại lệ LDAP được Spring chuyển đổi; ví dụ trên cũng giả định thuộc tính `cn` có mặt theo schema. Giá trị mật khẩu lấy từ biến môi trường chỉ nhằm minh họa cấu hình; khi triển khai thật, dùng cơ chế quản lý bí mật phù hợp và xác thực chứng chỉ TLS.

Trong trường hợp **chưa biết DN** mà chỉ biết `uid`, dùng tìm kiếm trong một nhánh thay vì đoán cấu trúc DN:

```java
import java.util.List;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;

String userInput = "lan";

LdapQuery query = LdapQueryBuilder.query()
    .base("ou=people")
    .where("uid").is(userInput);

List<String> names = ldapTemplate.search(
    query,
    (AttributesMapper<String>) attrs ->
        (String) attrs.get("cn").get()
);
```

`LdapQueryBuilder` dựng **LDAP search filter** từ giá trị dữ liệu, còn `LdapNameBuilder` dựng **DN**. Hai loại chuỗi có quy tắc escaping khác nhau: **không** dùng một hàm escape DN để tạo filter, hoặc ngược lại. Kết quả `search` có thể là 0, 1 hoặc nhiều entry tùy phạm vi và dữ liệu; `lookup` hướng đến một DN cụ thể.

## 6. Đổi RDN, đổi DN và di chuyển entry

DN phản ánh **vị trí và tên** của entry. Vì thế một số thao tác thay đổi danh tính định vị của entry:

| Thao tác | Trước | Sau | Hệ quả |
| --- | --- | --- | --- |
| Sửa thuộc tính không đặt tên | `uid=lan,ou=people,...` | DN giữ nguyên | Ví dụ đổi `mail`; vị trí entry không thay đổi. |
| Đổi RDN | `uid=lan,ou=people,...` | `uid=lan2,ou=people,...` | Đổi tên entry trong cùng nhánh cha. |
| Chuyển nhánh cha | `uid=lan,ou=people,...` | `uid=lan,ou=contractors,...` | DN thay đổi vì entry được chuyển đến nhánh khác. |

Trong giao thức LDAP, thao tác **Modify DN** được dùng để đổi RDN và, khi server hỗ trợ, thay đổi nhánh cha. Việc giữ hoặc xóa giá trị RDN cũ phụ thuộc tùy chọn `deleteOldRDN` và quy tắc server. Nếu entry có các entry con, việc đổi tên hoặc di chuyển entry cha cũng làm thay đổi **DN đầy đủ của các entry con**. Do đó, không nên coi DN là một mã định danh bất biến dùng để lưu lâu dài ở mọi hệ thống.

Khi thiết kế dịch vụ quản lý người dùng, hãy tách rõ việc sửa `cn`/`mail` với việc đổi RDN `uid=...`. Thay đổi một thuộc tính được dùng để đặt tên có thể cần thao tác đổi tên entry và kiểm tra ràng buộc của máy chủ; không nên giả định `modifyAttributes` tự động đổi DN.

## 7. Các lỗi thường gặp và cách xử lý

| Tình huống | Nguyên nhân điển hình | Hướng xử lý |
| --- | --- | --- |
| `NameNotFoundException` hoặc không tìm thấy entry | DN sai, sai nhánh, hoặc ghép lặp `base`. | Kiểm tra DN đầy đủ, base trong `ContextSource` và tên tương đối truyền vào API. |
| Thêm entry thất bại vì chưa có cha | `ou=people,...` chưa tồn tại. | Tạo hoặc kiểm tra entry cha trước, bảo đảm có quyền thêm con. |
| Tên bị tách sai khi chứa dấu phẩy/dấu cộng | Nối thẳng giá trị động vào chuỗi DN. | Dùng `LdapNameBuilder` hoặc `Rdn`/`LdapName`. |
| `EntryAlreadyExists` / trùng tên | Entry cùng DN hoặc cùng RDN dưới cùng cha đã tồn tại. | Chọn giá trị đặt tên khác hoặc kiểm tra tồn tại trước thao tác thêm. |
| Entry không đạt schema | Thiếu `objectClass`, `sn`, `cn` hoặc thuộc tính đặt tên không phù hợp. | Kiểm tra quy tắc objectClass và các thuộc tính bắt buộc. |
| Tìm thấy nhiều người cùng `uid` | Phạm vi tìm kiếm chứa nhiều nhánh, `uid` không được bảo đảm duy nhất toàn DIT. | Thu hẹp search base hoặc bổ sung tiêu chí định danh. |

Hai quy tắc an toàn quan trọng khi nhận đầu vào từ người dùng:

1. **DN và filter là hai cú pháp khác nhau.** Dùng API chuyên dụng để xử lý giá trị động; không ghép chuỗi từ dữ liệu chưa tin cậy.
2. **Đúng DN chưa đồng nghĩa được phép truy cập.** Máy chủ vẫn phải áp dụng quyền LDAP, TLS và chính sách xác thực phù hợp. Người dùng chỉ nên được thao tác trên nhánh mà ứng dụng cho phép.

## 8. Tự kiểm tra qua một tình huống

Cho DN:

```text
cn=Dev Team,ou=groups,ou=engineering,dc=example,dc=org
```

Hãy xác định tên của entry, tên cha và DN của entry cha trước khi xem lời giải:

- **Entry:** có DN đầy đủ như trên, thường biểu diễn một nhóm nếu schema của nó là nhóm.
- **RDN:** `cn=Dev Team`.
- **DN của cha:** `ou=groups,ou=engineering,dc=example,dc=org`.
- **Nếu Spring LDAP có base `dc=example,dc=org`:** DN tương đối của nhóm là `cn=Dev Team,ou=groups,ou=engineering`.
- **Nếu chuyển nhóm sang `ou=teams,ou=engineering,...`:** DN mới sẽ là `cn=Dev Team,ou=teams,ou=engineering,dc=example,dc=org`, giả sử nhánh đích tồn tại và server cho phép chuyển.

Điểm cần ghi nhớ khi viết code Spring LDAP: **entry** là đơn vị dữ liệu, **RDN** là tên cục bộ dưới một cha, **DN** là tên phân biệt toàn tuyến từ entry lên gốc, còn **base** của `ContextSource` quyết định phần hậu tố mà ứng dụng có thể không cần truyền lại. Nắm được mối quan hệ này giúp chọn đúng giữa `lookup` theo DN, `search` theo nhánh và thao tác đổi tên entry.
