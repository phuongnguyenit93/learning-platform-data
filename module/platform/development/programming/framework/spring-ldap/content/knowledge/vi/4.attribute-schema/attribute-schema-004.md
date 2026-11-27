# Attribute operational và attribute nghiệp vụ

Một LDAP entry không chỉ chứa dữ liệu mà ứng dụng cần xử lý, như tên nhân viên, email hoặc phòng ban. Nó còn có thể mang thông tin do hệ thống thư mục quản lý, chẳng hạn thời điểm tạo, thời điểm sửa, tài khoản thực hiện thao tác hoặc định danh entry do máy chủ cấp. Trong LDAP, nhóm thứ hai thường được gọi là **operational attributes** (thuộc tính vận hành).

Bài học thuộc chương **Attribute và schema** của mô-đun **SPRING_LDAP**, dành cho người học sử dụng LDAP qua Spring LDAP: từ DN, schema, filter và tìm kiếm đến đọc/ghi entry bằng `LdapTemplate`, `LdapClient` hoặc ODM. Biết phân biệt hai nhóm thuộc tính giúp bạn đọc đúng dữ liệu, hiểu vì sao một số trường không xuất hiện trong kết quả tìm kiếm và tránh cố ghi các giá trị vốn do máy chủ kiểm soát.

**Sau bài học, bạn có thể:**

- Phân biệt **user/application attributes**, **operational attributes** và các thuộc tính **nghiệp vụ** của ứng dụng.
- Nhận biết vai trò của `USAGE`, `NO-USER-MODIFICATION`, `SINGLE-VALUE` trong LDAP schema.
- Sử dụng `*` và `+` khi truy vấn thuộc tính LDAP; biết khi nào cần yêu cầu tên thuộc tính cụ thể.
- Đọc thuộc tính vận hành một cách an toàn bằng `LdapTemplate` và xử lý trường hợp chúng không được trả về.
- Giải thích giới hạn của `createTimestamp`, `modifyTimestamp`, `creatorsName` và `entryUUID` trong nghiệp vụ, đồng bộ và kiểm thử.

## 1. Hai lớp thông tin trong một entry

Giả sử LDAP có entry người dùng:

```text
dn: uid=an,ou=People,dc=example,dc=org
```

Ứng dụng quản lý nhân sự cần đọc `uid`, `cn`, `mail`, `employeeNumber`, `departmentNumber` để hiển thị hồ sơ. Đồng thời, hệ thống quản trị thư mục có thể cần biết entry này được tạo khi nào, lần cuối được sửa khi nào và có định danh nội bộ nào.

| Câu hỏi | Thuộc tính minh họa | Mục đích |
| --- | --- | --- |
| Nhân viên là ai? | `uid`, `cn`, `sn` | Định danh và thông tin hiển thị |
| Liên hệ qua đâu? | `mail`, `telephoneNumber` | Dữ liệu phục vụ ứng dụng |
| Thuộc phòng ban nào? | `departmentNumber` | Phân loại nghiệp vụ |
| Entry được tạo lúc nào? | `createTimestamp` | Metadata do thư mục ghi nhận |
| Entry được sửa lúc nào? | `modifyTimestamp` | Theo dõi biến động entry |
| Ai đã thực hiện thao tác? | `creatorsName`, `modifiersName` | Metadata về danh tính LDAP thực hiện thao tác |
| Entry có định danh do server cấp nào? | `entryUUID` | Hỗ trợ tham chiếu/đồng bộ tùy hệ thống |

**“Attribute nghiệp vụ” không phải tên một giá trị `USAGE` chuẩn của LDAP.** Đây là cách gọi thực tế cho thuộc tính mà ứng dụng dùng để mô hình hóa miền dữ liệu, ví dụ mã nhân viên hoặc phòng ban. Trong schema, phần lớn các thuộc tính này thuộc loại **user/application attributes** với `USAGE userApplications`.

Ngược lại, **operational attribute** là một loại được nhận diện bằng quy tắc `USAGE` trong schema. Không nên phân loại chỉ bằng tên, chỉ bằng việc thuộc tính “quan trọng”, hoặc chỉ bằng việc ứng dụng có thể ghi vào trường đó hay không.

## 2. LDAP schema phân loại attribute như thế nào?

LDAP schema định nghĩa mỗi **attribute type**: tên, OID, cú pháp giá trị (`SYNTAX`), quy tắc so khớp (`EQUALITY`, `ORDERING`, `SUBSTR`), đặc tính đơn trị hoặc đa trị và cách thuộc tính được sử dụng (`USAGE`).

Theo [RFC 4512](https://www.rfc-editor.org/rfc/rfc4512.html), `USAGE` có bốn loại:

| Giá trị `USAGE` | Nhóm | Ý nghĩa |
| --- | --- | --- |
| `userApplications` | User/application attribute | Dữ liệu dành cho ứng dụng/người dùng; đây là **giá trị mặc định** nếu khai báo attribute type không ghi `USAGE` |
| `directoryOperation` | Operational attribute | Hỗ trợ hoạt động quản trị/vận hành của thư mục |
| `distributedOperation` | Operational attribute | Hỗ trợ vận hành thư mục phân tán |
| `dSAOperation` | Operational attribute | Hỗ trợ hoạt động của Directory System Agent (DSA, tức thành phần máy chủ LDAP) |

Có thể mô tả bằng sơ đồ:

```text
Attribute type trong LDAP schema
│
├── USAGE userApplications
│   ├── uid, cn, sn, mail
│   ├── employeeNumber, departmentNumber
│   └── member, userPassword (tùy schema và quyền đọc)
│
└── USAGE khác userApplications  →  operational
    ├── directoryOperation
    │   ├── createTimestamp, modifyTimestamp
    │   ├── creatorsName, modifiersName
    │   ├── structuralObjectClass
    │   └── entryUUID (nếu server hỗ trợ)
    ├── distributedOperation
    └── dSAOperation
```

Trong sơ đồ trên, các ví dụ phụ thuộc schema và khả năng hỗ trợ của máy chủ. Không phải mọi LDAP server đều cung cấp tất cả tên thuộc tính hoặc cùng một hành vi hiển thị.

### 2.1. `USAGE` và `NO-USER-MODIFICATION` là hai khái niệm khác nhau

Xét định nghĩa schema rút gọn cho `modifyTimestamp`:

```text
( 2.5.18.2 NAME 'modifyTimestamp'
  EQUALITY generalizedTimeMatch
  ORDERING generalizedTimeOrderingMatch
  SYNTAX 1.3.6.1.4.1.1466.115.121.1.24
  SINGLE-VALUE
  NO-USER-MODIFICATION
  USAGE directoryOperation )
```

Ý nghĩa của các phần chính:

- `USAGE directoryOperation`: thuộc nhóm operational.
- `NO-USER-MODIFICATION`: người dùng LDAP không được trực tiếp sửa thuộc tính này qua các thao tác cập nhật thông thường.
- `SINGLE-VALUE`: tối đa một giá trị theo schema.
- `SYNTAX` và `EQUALITY`/`ORDERING`: quy định dạng dữ liệu thời gian và cách so khớp.

**`USAGE` trả lời “thuộc tính phục vụ mục đích nào trong mô hình thư mục?”; `NO-USER-MODIFICATION` trả lời “client có được tự sửa thuộc tính này hay không?”.** Nhiều operational attributes là metadata do server quản lý và không cho sửa trực tiếp. Tuy vậy, khi quyết định một thao tác ghi có hợp lệ, vẫn phải xem đúng schema, quyền và quy tắc của server; không chỉ suy đoán từ chữ “operational”.

Ngược lại, **`userPassword` không mặc nhiên là operational attribute**. Trong nhiều schema chuẩn, nó là user/application attribute mặc dù rất nhạy cảm, có thể bị ACL che giấu và bị quy trình đổi mật khẩu kiểm soát chặt chẽ. *Độ nhạy cảm* không phải tiêu chí phân loại `USAGE`.

### 2.2. Quy định của `objectClass` vẫn áp dụng

Dù một thuộc tính thuộc nhóm nào, nó vẫn phải tuân theo schema. `objectClass` của entry quy định những thuộc tính nghiệp vụ nào có thể/bắt buộc xuất hiện (`MAY`/`MUST`), còn các thuộc tính vận hành có thể được tạo, duy trì hoặc tính toán bởi server theo quy tắc của nó.

Ví dụ, một entry `inetOrgPerson` có thể có `cn`, `sn`, `uid`, `mail` và `employeeNumber` tùy cấu hình schema. Điều đó không có nghĩa bạn có thể gửi một bản ghi thêm mới chứa `createTimestamp` tùy ý: thuộc tính này thường do server tạo, và nó được khai báo `NO-USER-MODIFICATION`.

## 3. Những operational attributes thường gặp

| Thuộc tính | Thông tin biểu diễn | Lưu ý |
| --- | --- | --- |
| `createTimestamp` | Thời điểm server ghi nhận entry được tạo | Là thời điểm của entry trong thư mục, không nhất thiết là ngày nhân viên bắt đầu làm việc |
| `modifyTimestamp` | Thời điểm server ghi nhận lần sửa entry gần nhất | Không cho biết chính xác thuộc tính nào thay đổi |
| `creatorsName` | DN danh tính LDAP được ghi nhận khi tạo entry | Có thể là tài khoản dịch vụ, không phải người thực sự thao tác |
| `modifiersName` | DN danh tính LDAP được ghi nhận cho lần sửa gần nhất | Có thể khác người thực hiện nghiệp vụ ở tầng ứng dụng |
| `structuralObjectClass` | Structural object class thực tế của entry | Hữu ích khi chẩn đoán schema |
| `subschemaSubentry` | DN chỉ đến subschema áp dụng cho entry | Giúp truy tìm định nghĩa `attributeTypes` và `objectClasses` |
| `hasSubordinates` | Server cho biết entry có entry con hay không, nếu hỗ trợ | Tùy tính năng và quyền quan sát của server |
| `entryUUID` | Định danh entry do server cung cấp theo RFC 4530 | Không phải server nào cũng có; không coi là mã nhân viên |
| `entryDN` | DN của entry được công bố như operational attribute theo RFC 5020, nếu hỗ trợ | Không đồng nghĩa mọi server đều hỗ trợ lọc hoặc trả về như nhau |

Ngoài các tên theo chuẩn, mỗi hệ thống còn có **operational attributes riêng**. Ví dụ, `entryCSN` và `contextCSN` thường gặp trong triển khai OpenLDAP; `memberOf` có thể được cung cấp như thuộc tính phát sinh/operational qua một số cơ chế hoặc overlay. **Không mặc định mọi server đều có `memberOf` hoặc phân loại nó giống nhau.** Đặc biệt, không nhầm `member` (danh sách DN thành viên của nhóm, thường là thuộc tính ứng dụng) với `memberOf` (quan hệ thành viên nhìn từ phía entry được cung cấp theo khả năng của server).

### 3.1. Dữ liệu minh họa khi đọc entry

Giả sử một server có schema và chính sách cho phép đọc các thuộc tính sau. Đây là ví dụ **đầu ra truy vấn**, không phải nội dung `ldapadd`: các operational attributes bên dưới do server duy trì.

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
employeeNumber: NV-1024
departmentNumber: ENG
createTimestamp: 20261121083000Z
modifyTimestamp: 20261126094510Z
creatorsName: cn=provisioning,ou=ServiceAccounts,dc=example,dc=org
modifiersName: cn=hr-sync,ou=ServiceAccounts,dc=example,dc=org
entryUUID: 550e8400-e29b-41d4-a716-446655440000
```

Các dòng `uid`, `cn`, `mail` và `employeeNumber` phục vụ việc mô tả một người dùng. Các dòng `createTimestamp`, `modifiersName` và `entryUUID` giúp quan sát trạng thái của **entry trong LDAP**.

Chú ý giá trị thời gian mẫu `20261126094510Z` ở định dạng Generalized Time (theo quy ước ở đây: năm, tháng, ngày, giờ, phút, giây và `Z` cho UTC). Khi tích hợp thực tế, cần parse theo cú pháp Generalized Time được schema/server hỗ trợ; đừng giả định mọi máy chủ đều xuất đúng một chuỗi mẫu với độ chính xác giây như trên.

## 4. Vì sao tìm kiếm thông thường không trả operational attributes?

Khi client truy vấn LDAP mà không chỉ định thuộc tính cần trả về, server thường trả về các **user/application attributes** có thể đọc. **Operational attributes thường không được trả về theo mặc định**. Điều đó không chứng minh chúng không tồn tại.

Đây là điểm khác biệt cần nhớ giữa “thuộc tính có thể tồn tại trên entry” và “thuộc tính có mặt trong kết quả trả về”.

LDAP dùng các **attribute selection** đặc biệt trong truy vấn:

| Attribute selection | Yêu cầu trả về |
| --- | --- |
| Không chỉ định danh sách thuộc tính | Mặc định yêu cầu các user attributes |
| `*` | Tất cả **user/application attributes** được phép trả về |
| `+` | Tất cả **operational attributes** mà server hỗ trợ cơ chế lựa chọn này và cho phép trả về |
| `*` và `+` | Yêu cầu cả hai nhóm |
| `cn mail modifyTimestamp` | Chỉ các thuộc tính được nêu tên (nếu tồn tại và có quyền đọc) |
| `1.1` đứng một mình | Không yêu cầu trả về giá trị attribute; hữu ích khi chỉ cần DN của entry |

Ký hiệu `+` là phần mở rộng lựa chọn operational attributes được chuẩn hóa tại **RFC 3673**. Server có thể không hỗ trợ đầy đủ, chỉ trả một phần hoặc áp dụng ACL. Vì vậy, với một vài metadata cần thiết cho nghiệp vụ, **nêu đích danh thuộc tính** thường dễ kiểm soát hơn so với luôn yêu cầu toàn bộ `+`.

### 4.1. So sánh bằng `ldapsearch`

Ví dụ dùng OpenLDAP client trên terminal tương thích Bash. DN và host là dữ liệu minh họa; thay bằng máy chủ và tài khoản thực tế:

```bash
# 1) Chỉ các user/application attributes
ldapsearch -LLL -x -H "ldaps://ldap.example.org:636" \
  -b "uid=an,ou=People,dc=example,dc=org" \
  -s base "(objectClass=*)" "*"

# 2) Chỉ các operational attributes (RFC 3673)
ldapsearch -LLL -x -H "ldaps://ldap.example.org:636" \
  -b "uid=an,ou=People,dc=example,dc=org" \
  -s base "(objectClass=*)" "+"

# 3) Yêu cầu cả hai nhóm
ldapsearch -LLL -x -H "ldaps://ldap.example.org:636" \
  -b "uid=an,ou=People,dc=example,dc=org" \
  -s base "(objectClass=*)" "*" "+"

# 4) Chỉ một vài thuộc tính
ldapsearch -LLL -x -H "ldaps://ldap.example.org:636" \
  -b "uid=an,ou=People,dc=example,dc=org" \
  -s base "(objectClass=*)" cn mail createTimestamp modifyTimestamp
```

Lệnh minh họa dùng simple authentication ở chế độ ẩn danh (không có `-D`). Để chạy trên server yêu cầu bind, có thể thêm `-D "cn=reader,ou=ServiceAccounts,dc=example,dc=org" -W` nhằm nhập mật khẩu qua prompt. Đừng đặt mật khẩu trực tiếp trong dòng lệnh hay tài liệu chia sẻ.

Trong các lệnh trên:

- `-b` chọn **DN entry cần đọc**.
- `-s base` chỉ xét **chính entry đó**, không tìm sâu xuống cây con.
- `(objectClass=*)` là filter presence, thường phù hợp để đọc một entry đã biết DN.
- `cn mail createTimestamp modifyTimestamp` là danh sách attribute selection, **không phải filter**.

Nếu `cn` xuất hiện mà `createTimestamp` không xuất hiện ở lệnh đầu tiên, đó là hành vi dự kiến. Nếu lệnh thứ hai hoặc thứ tư cũng không thấy `createTimestamp`, hãy kiểm tra quyền truy cập, hỗ trợ của server, loại entry và schema trước khi kết luận thuộc tính không tồn tại.

> **Truy vấn `+` không bỏ qua ACL.** Người dùng bind không có quyền đọc metadata sẽ không nhìn thấy chúng chỉ vì đã thêm `+`. Tương tự, một vài attribute có thể được coi là đặc biệt, không được server công bố hoặc không được hỗ trợ.

### 4.2. Phân biệt danh sách attribute và filter

Filter và danh sách thuộc tính trả về là **hai phần độc lập** của LDAP search:

```text
Base DN:   ou=People,dc=example,dc=org
Scope:     SUBTREE
Filter:    (uid=an)
Attributes: cn, mail, createTimestamp, modifyTimestamp
```

- **Base và scope** giới hạn nơi tìm.
- **Filter** quyết định entry nào thỏa điều kiện.
- **Attributes** quyết định trường nào được yêu cầu trong những entry trả về.

Việc yêu cầu `modifyTimestamp` trong danh sách attributes **không làm filter tự động dựa trên `modifyTimestamp`**.

## 5. Đọc operational attributes bằng Spring LDAP

Spring LDAP cung cấp các API truy vấn và ánh xạ attribute thành đối tượng Java. Khi ứng dụng cần hiển thị thông tin nghiệp vụ cùng metadata như “cập nhật lần cuối”, hãy **yêu cầu rõ các thuộc tính cần đọc**.

Giả sử `ContextSource` đã cấu hình:

```java
contextSource.setBase("dc=example,dc=org");
```

Vì thế, search base trong ví dụ dưới đây là `ou=People`, **tương đối với** `dc=example,dc=org`.

### 5.1. Yêu cầu cụ thể user và operational attributes qua `LdapTemplate`

Ví dụ Java:

```java
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import javax.naming.NamingException;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;

import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;
import org.springframework.ldap.query.SearchScope;

public class PersonDirectory {
    private final LdapTemplate ldapTemplate;

    public PersonDirectory(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<Map<String, String>> findPeopleWithMetadata() {
        LdapQuery query = LdapQueryBuilder.query()
            .base("ou=People")
            .searchScope(SearchScope.SUBTREE)
            .attributes(
                "uid", "cn", "mail", "employeeNumber",
                "createTimestamp", "modifyTimestamp", "modifiersName"
            )
            .where("objectClass").is("inetOrgPerson");

        return ldapTemplate.search(
            query,
            (AttributesMapper<Map<String, String>>) PersonDirectory::mapEntry
        );
    }

    private static Map<String, String> mapEntry(Attributes attrs)
            throws NamingException {
        String[] names = {
            "uid", "cn", "mail", "employeeNumber",
            "createTimestamp", "modifyTimestamp", "modifiersName"
        };

        Map<String, String> values = new LinkedHashMap<>();
        for (String name : names) {
            Attribute attribute = attrs.get(name);
            if (attribute != null && attribute.size() > 0) {
                values.put(name, String.valueOf(attribute.get()));
            }
        }
        return values;
    }
}
```

Trong đoạn mã:

1. `.base("ou=People")` xác định nhánh tìm kiếm theo base đã cấu hình trong `ContextSource`.
2. `SearchScope.SUBTREE` xét entry gốc tìm kiếm và các cấp hậu duệ.
3. `.where("objectClass").is("inetOrgPerson")` giới hạn kết quả theo đối tượng người dùng.
4. `.attributes(...)` yêu cầu cả **thuộc tính nghiệp vụ** và **thuộc tính vận hành** theo tên cụ thể.
5. `AttributesMapper` bỏ qua attribute không xuất hiện thay vì giả định `attrs.get("modifyTimestamp")` luôn khác `null`.

Ví dụ dùng `Map<String, String>` để dễ thấy cơ chế đọc attribute. Trong ứng dụng thật, nên chuyển sang DTO có kiểu dữ liệu rõ ràng, parse thời gian thành kiểu thời gian phù hợp và kiểm soát các trường đa trị. Nếu một attribute có thể có nhiều giá trị, chỉ gọi `get()` lấy giá trị đầu tiên là **không đủ**; cần duyệt `Attribute.getAll()` hoặc ánh xạ thành tập hợp.

**Không mặc định mọi entry trả về đầy đủ các trường đã yêu cầu.** Một thuộc tính không xuất hiện có thể vì nó chưa có giá trị, bị chặn bởi ACL, chưa được triển khai, hoặc server không trả về theo quy tắc riêng.

### 5.2. Dùng `LdapClient` hoặc ODM thì sao?

Các nguyên tắc vẫn giữ nguyên:

- Với `LdapClient`, cần xác định đúng base, scope, filter và danh sách thuộc tính cần yêu cầu.
- Với ODM, một lớp Java ánh xạ những attribute LDAP phù hợp; nếu cần metadata operational cho tính năng audit hoặc hiển thị, phải bảo đảm truy vấn và ánh xạ thực sự lấy được chúng.
- Dù dùng API nào, **không giả định metadata vận hành cũng được trả về theo mặc định giống dữ liệu hồ sơ**.

Không nên thiết kế một trường `modifyTimestamp` trong DTO rồi dùng dữ liệu đó để tự viết ngược vào LDAP khi cập nhật hồ sơ. Đối với các attribute do server quản lý, cập nhật dữ liệu nghiệp vụ bình thường và để server quyết định metadata mới.

## 6. Đọc schema để xác định một attribute thuộc nhóm nào

Tên của thuộc tính **không đủ** để khẳng định phân loại. Cách chắc chắn hơn là xem **định nghĩa attribute type trong subschema** của server đang truy cập.

Quy trình về mặt khái niệm:

1. Đọc operational attribute `subschemaSubentry` của một entry mà bạn có quyền truy cập.
2. Lấy DN từ `subschemaSubentry`, ví dụ server có thể trả `cn=Subschema`.
3. Đọc entry subschema đó để xem `attributeTypes` và `objectClasses` (nếu quyền cho phép).
4. Tìm định nghĩa tên thuộc tính cần kiểm tra; xem `USAGE` và `NO-USER-MODIFICATION`.

Ví dụ (giá trị DN schema trong bước hai phụ thuộc server, **không được hard-code nếu server công bố DN khác**):

```bash
# Hỏi entry người dùng xem schema áp dụng nằm ở đâu.
ldapsearch -LLL -x -H "ldaps://ldap.example.org:636" \
  -b "uid=an,ou=People,dc=example,dc=org" \
  -s base "(objectClass=*)" subschemaSubentry

# Nếu kết quả là "cn=Subschema", đọc định nghĩa schema:
ldapsearch -LLL -x -H "ldaps://ldap.example.org:636" \
  -b "cn=Subschema" -s base "(objectClass=subschema)" \
  attributeTypes
```

Kết quả `attributeTypes` là các khai báo schema dạng văn bản; có thể rất dài. Một khai báo có `USAGE directoryOperation` thuộc nhóm operational; khai báo không ghi `USAGE` thường được hiểu là `userApplications` theo mặc định. Khi server không cấp quyền đọc subschema, hãy dùng tài liệu schema chính thức của hệ thống LDAP cụ thể và xác nhận lại với quản trị viên.

### Thuộc tính nghiệp vụ tùy biến

Một doanh nghiệp có thể bổ sung thuộc tính như `costCenter`, `businessUnitCode` hoặc `employmentStatus`. Đây là **tên minh họa**: chúng chỉ dùng được khi schema thực tế đã định nghĩa attribute type tương ứng và các `objectClass` cho phép xuất hiện.

Khi định nghĩa schema riêng, cần dùng OID hợp lệ dưới nhánh OID mà tổ chức sở hữu, chọn `SYNTAX` và matching rule phù hợp, cân nhắc `SINGLE-VALUE`, cùng quy tắc `MAY`/`MUST` ở object class. Nếu đặt `USAGE userApplications` hoặc bỏ `USAGE`, thuộc tính là user/application attribute. Không gán `USAGE directoryOperation` chỉ vì một ứng dụng nội bộ muốn theo dõi “trạng thái”: operational có ý nghĩa cụ thể trong mô hình thư mục.

## 7. Thiết kế ứng dụng: dùng metadata vận hành đúng mục đích

### 7.1. `modifyTimestamp` không thay thế nhật ký nghiệp vụ

Một đội ngũ muốn hiển thị “cập nhật lúc 09:45” có thể đọc `modifyTimestamp`. Nhưng từ đó **không thể suy ra** nhân viên đã đổi phòng ban, đổi email hay được thăng chức. Thuộc tính chỉ ghi nhận thời điểm server thấy entry thay đổi theo cơ chế của nó.

Nếu yêu cầu nghiệp vụ là “ai phê duyệt thay đổi lương?” hoặc “email cũ là gì?”, hãy dùng **audit log ở tầng ứng dụng** hoặc cơ chế audit phù hợp của server. `modifiersName` có thể chỉ chứa DN tài khoản đồng bộ `cn=hr-sync,...`, không phản ánh người duyệt thực tế.

### 7.2. `createTimestamp` không phải ngày gia nhập

Entry được tạo khi một tài khoản được provision vào LDAP. Nhân viên có thể bắt đầu làm việc trước đó hoặc được chuyển từ hệ thống cũ. Do đó:

- `createTimestamp`: thời điểm entry được tạo trong thư mục theo máy chủ.
- `hireDate` hoặc thuộc tính nghiệp vụ tương đương (nếu schema có): ngày bắt đầu làm việc theo nguồn dữ liệu nhân sự.

Hai thời điểm có thể khác nhau mà không có lỗi hệ thống.

### 7.3. `entryUUID` là metadata định danh entry, không phải mã khách hàng

`entryUUID`, khi được server hỗ trợ, hữu ích để theo dõi entry trong một số tình huống đồng bộ vì DN có thể đổi khi rename/move. Tuy nhiên, đừng coi giá trị này là một khóa nghiệp vụ bền vững giữa **mọi** hệ thống, mọi máy chủ và mọi lần xuất/nhập dữ liệu nếu chưa kiểm chứng hành vi của nền tảng. Một quá trình migration có thể tạo lại entry và phát sinh định danh mới.

### 7.4. Quyền đọc và bảo vệ dữ liệu

Cấu hình TLS (LDAPS hoặc StartTLS), kiểm tra chứng chỉ và dùng tài khoản bind với **quyền tối thiểu** phù hợp nhiệm vụ. Operational attributes có thể hé lộ tên tài khoản dịch vụ, cấu trúc DN hoặc metadata nhạy cảm về hoạt động; việc có thể đọc được chúng không có nghĩa nên đưa toàn bộ ra API công khai hoặc ghi log.

**Một chiến lược thực tế:** chỉ yêu cầu thuộc tính phục vụ use case. Ví dụ, API hồ sơ nhân viên lấy `cn`, `mail`, `departmentNumber`; màn hình quản trị có thể cần thêm `modifyTimestamp`; tác vụ đồng bộ có thể cần `entryUUID` nếu môi trường bảo đảm hỗ trợ và tính ổn định như mong đợi.

## 8. Chẩn đoán khi operational attributes không xuất hiện

| Hiện tượng | Khả năng | Cách kiểm tra |
| --- | --- | --- |
| `ldapsearch` có `cn`, `mail` nhưng không có `modifyTimestamp` | Truy vấn mặc định chỉ yêu cầu user attributes | Nêu rõ `modifyTimestamp` hoặc dùng `+` |
| Đã thêm `+` nhưng vẫn thiếu metadata | Server không hỗ trợ `+` đầy đủ, không cung cấp thuộc tính hoặc ACL che kết quả | Yêu cầu đích danh thuộc tính; kiểm tra schema/quyền |
| Spring LDAP trả `null` cho `creatorsName` | Không có attribute trong kết quả | Kiểm tra `.attributes(...)`, server và ACL; xử lý null |
| Gửi `modifyTimestamp` trong lệnh sửa rồi nhận lỗi | Thuộc tính do hệ thống quản lý/`NO-USER-MODIFICATION` | Bỏ trường đó khỏi payload sửa; cho server duy trì |
| Truy vấn đúng tên thuộc tính nhưng không tìm thấy entry | Sai base DN, scope hoặc filter | Kiểm tra từng thành phần tìm kiếm độc lập |
| `entryUUID` có ở môi trường A nhưng thiếu ở B | Khác phiên bản hoặc loại server/schema | Kiểm tra tài liệu và khả năng hỗ trợ thực tế |
| `memberOf` hiển thị khác nhau giữa server | Thuộc tính/overlay/cấu hình riêng từng hệ thống | Không mã hóa phụ thuộc không được kiểm chứng vào ứng dụng |
| Ứng dụng coi mọi giá trị là `String` duy nhất | Một số attribute đa trị hoặc có syntax khác | Xem schema, dùng mapper theo kiểu dữ liệu |

**Lưu ý về kiểm thử:** các LDAP server nhúng dùng cho unit/integration test không nhất thiết tái hiện đầy đủ operational attributes, ACL, replication hay metadata của production. Kiểm thử nghiệp vụ có thể dùng fixture cho các trường này, nhưng kiểm chứng hành vi thực sự cần môi trường LDAP có schema/chính sách gần với hệ thống triển khai.

## 9. Thực hành

Giả sử LDAP có entry `uid=an,ou=People,dc=example,dc=org` và máy chủ hỗ trợ `createTimestamp`, `modifyTimestamp`, `creatorsName`. `ContextSource.base` trong Spring LDAP là `dc=example,dc=org`.

**Bài 1. Phân loại.** Với các thuộc tính `cn`, `employeeNumber`, `createTimestamp`, `modifiersName` và `userPassword`, hãy chỉ ra nhóm user/application hay operational theo schema chuẩn thường gặp. Vì sao không thể lấy mức độ nhạy cảm làm tiêu chí?

**Bài 2. Truy vấn CLI.** Viết lệnh `ldapsearch` chỉ lấy `cn` và `modifyTimestamp` của đúng entry `uid=an`. Nên dùng `-s base` hay `-s sub`?

**Bài 3. Spring LDAP.** Với `ContextSource.base = dc=example,dc=org`, search base cần truyền vào `LdapQueryBuilder.base(...)` để tìm mọi người dùng dưới `ou=People` là gì? Nêu cách yêu cầu `modifyTimestamp` trong kết quả.

**Bài 4. Phân tích thiếu dữ liệu.** Vì sao `ldapsearch` chỉ có filter `(uid=an)` nhưng không chỉ định thuộc tính trả về có thể thấy `cn` mà không thấy `createTimestamp`?

**Bài 5. Nghiệp vụ.** Một nhân viên đổi email qua hệ thống HR, tài khoản LDAP được cập nhật bởi service account `hr-sync`. `modifiersName` có chứng minh được chính nhân viên đó đã sửa dữ liệu không?

### Đáp án gợi ý

1. `cn`, `employeeNumber`, `userPassword` thường là user/application attributes; `createTimestamp`, `modifiersName` là operational attributes. `userPassword` có thể rất nhạy cảm nhưng phân loại dựa trên `USAGE`, không dựa trên tính bí mật.
2. Ví dụ: `ldapsearch -x -H "ldaps://ldap.example.org:636" -b "uid=an,ou=People,dc=example,dc=org" -s base "(objectClass=*)" cn modifyTimestamp`. Chọn `base` vì chỉ cần một entry đã biết DN.
3. Dùng `.base("ou=People")` và `.searchScope(SearchScope.SUBTREE)`, kết hợp `.attributes("cn", "modifyTimestamp")` hoặc danh sách thuộc tính khác theo use case.
4. LDAP thường trả user attributes theo mặc định; cần yêu cầu tên `createTimestamp` hoặc cơ chế `+`, đồng thời phải có quyền đọc.
5. Không. `modifiersName` thường cho biết danh tính LDAP được server ghi nhận ở lần sửa đó, ví dụ tài khoản `hr-sync`; muốn xác định tác nhân nghiệp vụ cần log/nguồn kiểm toán tương ứng.

## 10. Ghi nhớ

**Thuộc tính nghiệp vụ** phục vụ dữ liệu và quy trình của ứng dụng; trong LDAP schema chúng thường là **user/application attributes** (`USAGE userApplications`). **Operational attributes** là metadata hoặc thuộc tính hỗ trợ vận hành được nhận diện bằng `USAGE` khác `userApplications`. Nhiều thuộc tính vận hành do server duy trì, thường không thể ghi trực tiếp và không được trả về trong truy vấn mặc định.

Khi sử dụng Spring LDAP, hãy **nêu rõ những thuộc tính cần lấy**, kiểm tra `ContextSource.base`, search scope, filter và ACL; xử lý trường hợp attribute không hiện diện. Đừng dùng `modifyTimestamp`, `creatorsName` hay `entryUUID` thay thế dữ liệu và kiểm toán nghiệp vụ khi chưa xác nhận chúng đáp ứng yêu cầu.

### Tài liệu tham khảo

- [RFC 4512 — LDAP: Directory Information Models](https://www.rfc-editor.org/rfc/rfc4512.html): mô hình entry, schema, attribute type, `USAGE` và các thuộc tính vận hành chuẩn.
- [RFC 4511 — LDAP: The Protocol](https://www.rfc-editor.org/rfc/rfc4511.html): thao tác tìm kiếm và lựa chọn attribute trả về.
- [RFC 3673 — LDAP: All Operational Attributes](https://www.rfc-editor.org/rfc/rfc3673.html): attribute selection `+`.
- [RFC 4530 — LDAP: entryUUID Operational Attribute](https://www.rfc-editor.org/rfc/rfc4530.html): `entryUUID`.
- [RFC 5020 — LDAP: entryDN Operational Attribute](https://www.rfc-editor.org/rfc/rfc5020.html): `entryDN`.
- [Spring LDAP Reference Documentation](https://docs.spring.io/spring-ldap/reference/): `LdapTemplate`, query builder, ContextSource và ánh xạ thuộc tính.
