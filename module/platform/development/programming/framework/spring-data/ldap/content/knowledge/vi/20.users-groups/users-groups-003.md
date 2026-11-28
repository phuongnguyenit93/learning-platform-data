# Phân biệt thành viên dạng DN với thành viên dạng tên đăng nhập

Trong **SPRING_DATA_LDAP**, ứng dụng Java dùng Spring Data LDAP repository hoặc `LdapTemplate` để đọc và thao tác với directory LDAP. Một entry người dùng có DN (*Distinguished Name*), các thuộc tính như `uid`, `cn`, `objectClass` và có thể thuộc nhiều nhóm. Tuy nhiên, **thành viên của một nhóm không nhất thiết được lưu cùng một kiểu định danh**. Một số schema lưu **DN của entry thành viên**; schema khác chỉ lưu **tên đăng nhập**.

Ví dụ, cả hai giá trị sau có thể nhắc đến người dùng Lan, nhưng chúng có ý nghĩa khác nhau:

```text
member:    uid=lan,ou=people,dc=example,dc=org
memberUid: lan
```

`member` tham chiếu đến **vị trí entry trong cây LDAP**. `memberUid` chỉ ghi **chuỗi tên đăng nhập** theo quy ước của một hệ thống POSIX/LDAP. Vì vậy, chương trình không thể dùng nguyên một giá trị làm đối số của cả hai kiểu thành viên, cũng không thể giả định hai mô hình có cùng quy tắc cập nhật khi người dùng đổi tên hoặc chuyển nhánh.

Bài học giúp bạn đọc đúng schema nhóm, xây truy vấn an toàn bằng Spring LDAP, phân biệt liên kết trực tiếp với nhóm lồng nhau, xử lý tình huống đổi DN/đổi tên đăng nhập và kiểm thử logic membership trên directory thật.

## 1. Người dùng và nhóm được lưu ở đâu?

Xét một cây LDAP đơn giản:

```text
dc=example,dc=org
├── ou=people
│   ├── uid=lan
│   └── uid=binh
└── ou=groups
    ├── cn=app-admins
    └── cn=unix-engineering
```

Entry người dùng Lan, ví dụ thuộc lớp `inetOrgPerson`:

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
```

Thông tin cần phân biệt:

- **DN**: `uid=lan,ou=people,dc=example,dc=org`, tên đầy đủ xác định vị trí entry Lan trong namespace LDAP này.
- **RDN**: `uid=lan`, thành phần tên tương đối với entry cha `ou=people`.
- **Tên đăng nhập**: giá trị thuộc tính `uid` là `lan` trong ví dụ; sản phẩm khác có thể dùng thuộc tính như `sAMAccountName` hoặc định danh đăng nhập khác.
- **Nhóm**: một LDAP entry khác, chứa các thuộc tính định nghĩa thành viên và chịu ràng buộc bởi `objectClass`/schema riêng của nhóm.

Tên thuộc tính `uid` có thể vừa xuất hiện trong RDN vừa là tên đăng nhập, nhưng đây chỉ là **một cách tổ chức DIT**. Người dùng hoàn toàn có thể có DN bắt đầu bằng `cn=Lan Nguyen` hoặc nằm ở container khác. Không suy ra DN đầy đủ chỉ từ tên đăng nhập nếu chưa biết chắc quy tắc đặt tên và vị trí thực tế.

## 2. Hai schema nhóm tiêu biểu

### 2.1. `groupOfNames`: thành viên là DN

Với schema thông dụng theo RFC 4519, lớp `groupOfNames` lưu danh sách thành viên qua thuộc tính đa trị `member`. Mỗi giá trị là **DN** của một entry.

```ldif
dn: cn=app-admins,ou=groups,dc=example,dc=org
objectClass: top
objectClass: groupOfNames
cn: app-admins
member: uid=lan,ou=people,dc=example,dc=org
member: uid=binh,ou=people,dc=example,dc=org
```

`groupOfNames` yêu cầu `cn` và ít nhất một giá trị `member` theo schema chuẩn. Trong một nhóm như vậy:

- `member` là thuộc tính **đa trị**; mỗi giá trị mô tả một thành viên.
- Giá trị phải được diễn giải theo **cú pháp LDAP DN**, không phải chuỗi tên đăng nhập.
- Có thể có các RDN dạng `uid=...` hoặc `cn=...` trong cùng danh sách, miễn là tham chiếu tới entry phù hợp.
- Khi tìm nhóm chứa người dùng, nên so khớp `member` theo **matching rule DN của LDAP server**, không tách chuỗi rồi tự so khớp bằng `equalsIgnoreCase`.

Ví dụ giá trị sau cũng là một DN hợp lệ về mặt cú pháp, nếu entry tương ứng tồn tại:

```text
member: cn=Lan Nguyen,ou=people,dc=example,dc=org
```

Không thay nó bằng `member: lan`: chuỗi `lan` không phải DN hợp lệ trong mô hình này.

**Biến thể liên quan:** `groupOfUniqueNames` dùng `uniqueMember`. Thuộc tính này có cú pháp **Name and Optional UID**: thường chứa DN, nhưng có thể kèm thành phần UID đặc biệt theo chuẩn, khác với `memberUid` của POSIX. Đừng nhầm `uniqueMember` và `memberUid` chỉ vì cả hai cùng chứa từ “uid”.

### 2.2. `posixGroup`: thành viên là tên đăng nhập

Theo RFC 2307, `posixGroup` biểu diễn nhóm POSIX. Thuộc tính `memberUid` chứa các **login name** ở dạng chuỗi; nhóm cũng có `cn` và `gidNumber`.

```ldif
dn: cn=unix-engineering,ou=groups,dc=example,dc=org
objectClass: top
objectClass: posixGroup
cn: unix-engineering
gidNumber: 2100
memberUid: lan
memberUid: binh
```

Đây là dữ liệu thuộc **một mô hình schema khác**:

- `memberUid: lan` lưu chuỗi `lan`, **không chứa** `ou=people` hay `dc=example,dc=org`.
- `memberUid` có thể đa trị và là thuộc tính **tùy chọn** trong RFC 2307; `posixGroup` có thể không có giá trị `memberUid`.
- RFC 2307 định nghĩa `memberUid` bằng `IA5String` với phép so khớp `caseExactIA5Match`. Đừng tự chuyển thành chữ thường hoặc giả định tên đăng nhập không phân biệt hoa/thường khi server đang áp dụng quy tắc khác.
- `gidNumber` xác định **group ID POSIX**, không phải DN của nhóm và cũng không phải định danh thành viên.

Với tài khoản POSIX, `posixAccount.gidNumber` thường biểu diễn **nhóm chính (primary group)**. Thành viên của nhóm chính có thể **không xuất hiện** trong danh sách `memberUid`; danh sách `memberUid` thường phục vụ thành viên bổ sung. Nếu nghiệp vụ là “mọi nhóm POSIX của người dùng”, cần xét cả `gidNumber` của user và danh sách `memberUid` theo quy ước hệ thống, không chỉ tìm `(memberUid=lan)`.

Lưu ý một số hệ thống sử dụng schema mở rộng thường gọi là *RFC 2307bis* hoặc dạng lai, trong đó nhóm POSIX cũng có thể dùng tham chiếu DN. **Hãy đọc `objectClass` và schema thực tế trên server**, không kết luận kiểu thành viên chỉ dựa trên tên sản phẩm LDAP.

### 2.3. Bảng so sánh quan trọng

| Tiêu chí | Thành viên dạng DN | Thành viên dạng tên đăng nhập |
|---|---|---|
| Schema ví dụ | `groupOfNames.member`, `groupOfUniqueNames.uniqueMember` | `posixGroup.memberUid` |
| Giá trị ví dụ | `uid=lan,ou=people,dc=example,dc=org` | `lan` |
| Thông tin được lưu | Vị trí/tên entry trong LDAP namespace | Login name theo quy ước của directory/POSIX |
| Điều kiện tìm nhóm | So khớp thuộc tính có cú pháp DN | So khớp thuộc tính chuỗi login name |
| Đổi tên đăng nhập | Có thể **không** đổi DN nếu RDN không chứa login name | Cần xem xét cập nhật `memberUid` |
| Rename/move entry | DN thay đổi; liên kết cũ có thể cần cập nhật | Chuỗi `memberUid` có thể giữ nguyên nếu login name không đổi |
| Khả năng trùng định danh | DN xác định một vị trí trong namespace | Login name có thể trùng giữa nhiều vùng/tenant |
| Nested group | Có thể tham chiếu DN của group khác tùy schema/chính sách | `memberUid` không tự biểu diễn liên kết nhóm lồng nhau |
| Rủi ro tồn tại tham chiếu | DN cũ sau rename/move, DN của entry đã xóa | Login name đổi, trùng hoặc không còn tồn tại |

Hai mô hình **không tự chuyển đổi tương đương**. Để đổi từ `memberUid` sang DN, cần tra cứu người dùng theo quy tắc định danh rõ ràng và phạm vi duy nhất; để đổi từ DN sang login name, cần đọc thuộc tính đăng nhập của entry đích.

## 3. Nhận diện nhanh loại thành viên trong dữ liệu

Trước khi viết code, hãy kiểm tra ba điều:

1. **`objectClass` của nhóm**: `groupOfNames`, `groupOfUniqueNames`, `posixGroup`, hay loại riêng của vendor?
2. **Tên và cú pháp thuộc tính thành viên**: `member`, `uniqueMember`, `memberUid` hoặc thuộc tính do tổ chức tự định nghĩa?
3. **Quy tắc nghiệp vụ**: kiểm tra thành viên trực tiếp, nhóm lồng nhau hay toàn bộ quyền effective/primary group?

Ví dụ, kết quả tìm kiếm một nhóm:

```text
dn: cn=app-admins,ou=groups,dc=example,dc=org
objectClass: groupOfNames
member: uid=lan,ou=people,dc=example,dc=org
```

Ứng dụng phải xử lý `member` như một **DN**. Nếu chỉ lấy phần `uid=lan` bằng `split(",")[0]`, chương trình có thể sai khi gặp:

```text
member: cn=Lan\, Platform,ou=people,dc=example,dc=org
```

Dấu phẩy bên trong giá trị `cn` đã được escape, nên `split(",")` sẽ cắt hỏng DN. Hãy dùng `javax.naming.ldap.LdapName` khi cần parse DN; khi **tìm membership**, tốt hơn là dùng filter theo thuộc tính trên LDAP server và để server thực hiện matching rule.

Ngược lại, `memberUid: lan` là **một chuỗi đăng nhập**; không được truyền trực tiếp cho `LdapTemplate.lookup("lan")` rồi cho rằng đó là DN của user.

## 4. Truy vấn nhóm chứa thành viên bằng LdapTemplate

Giả sử `LdapContextSource` được cấu hình:

```text
LDAP endpoint: ldaps://ldap.example.org:636
Context base:  dc=example,dc=org
User branch:   ou=people
Group branch:  ou=groups
```

Với base của context là `dc=example,dc=org`, `query().base("ou=groups")` sẽ tìm dưới `ou=groups,dc=example,dc=org`. Tuy nhiên, **giá trị `member` trong group LDIF là DN đầy đủ của entry user**, không chỉ phần tương đối `uid=lan,ou=people`.

Ví dụ một reader có hai truy vấn rõ ràng:

**`GroupMembershipReader.java`**

```java
package com.example.ldap;

import java.util.List;
import javax.naming.Name;
import javax.naming.NamingException;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;
import javax.naming.directory.InvalidAttributeValueException;

import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.SearchScope;
import org.springframework.stereotype.Repository;

import static org.springframework.ldap.query.LdapQueryBuilder.query;

@Repository
public class GroupMembershipReader {
    private final LdapTemplate ldapTemplate;

    public GroupMembershipReader(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    // Tìm các groupOfNames có member là DN đầy đủ của user.
    public List<String> groupsByMemberDn(Name userFullDn) {
        if (userFullDn == null || userFullDn.isEmpty()) {
            throw new IllegalArgumentException("userFullDn không được rỗng");
        }

        LdapQuery ldapQuery = query()
                .base("ou=groups")
                .searchScope(SearchScope.SUBTREE)
                .attributes("cn")
                .where("objectClass").is("groupOfNames")
                .and("member").is(userFullDn.toString());

        return ldapTemplate.search(ldapQuery,
                attrs -> requiredCn(attrs));
    }

    // Tìm các posixGroup có memberUid là login name.
    public List<String> posixGroupsByLogin(String login) {
        if (login == null || login.isBlank()) {
            throw new IllegalArgumentException("login không được rỗng");
        }

        LdapQuery ldapQuery = query()
                .base("ou=groups")
                .searchScope(SearchScope.SUBTREE)
                .attributes("cn")
                .where("objectClass").is("posixGroup")
                .and("memberUid").is(login);

        return ldapTemplate.search(ldapQuery,
                attrs -> requiredCn(attrs));
    }

    private static String requiredCn(Attributes attrs)
            throws NamingException {
        Attribute cn = attrs.get("cn");
        if (cn == null || cn.size() == 0) {
            throw new InvalidAttributeValueException(
                    "Group LDAP thiếu thuộc tính cn");
        }
        return (String) cn.get();
    }
}
```

Điểm cần hiểu trong code:

- `.where("member").is(userFullDn.toString())` so khớp giá trị **DN** theo schema của LDAP server.
- `.where("memberUid").is(login)` so khớp **chuỗi tên đăng nhập**.
- `LdapQueryBuilder` mã hóa dữ liệu đầu vào ở **lớp LDAP filter**, giảm nguy cơ LDAP filter injection. Đừng nối chuỗi thành `"(member=" + input + ")"` hoặc `"(memberUid=" + input + ")"`.
- `base` và `searchScope` xác định **vùng nhóm** được tìm; bản thân thuộc tính `member` không đặt lại search base.
- `attributes("cn")` chỉ yêu cầu tên nhóm để trả về. Nếu cần cả DN của **nhóm** trong DTO, có thể dùng `ContextMapper` để lấy thông tin DN, vì `AttributesMapper` chỉ nhận tập thuộc tính của entry.
- Hai hàm chỉ kiểm tra **thành viên trực tiếp**. Chúng không tự mở rộng nhóm lồng nhau và không kiểm tra primary group POSIX qua `gidNumber`.

Nếu biết user DN được xây theo một cấu trúc cố định, có thể dùng `LdapNameBuilder`:

```java
import javax.naming.Name;
import org.springframework.ldap.support.LdapNameBuilder;

Name fullUserDn = LdapNameBuilder
        .newInstance("dc=example,dc=org")
        .add("ou", "people")
        .add("uid", "lan")
        .build();

// uid=lan,ou=people,dc=example,dc=org
List<String> dnGroups = reader.groupsByMemberDn(fullUserDn);
List<String> posixGroups = reader.posixGroupsByLogin("lan");
```

**Giới hạn của cách dựng DN:** nếu user có thể ở `ou=contractors`, dùng RDN `cn`, hoặc đã đổi DN, hãy **tra cứu DN thực tế** từ LDAP/nguồn định danh đáng tin trước khi truy vấn `member`. Không tự coi `uid=lan,ou=people` là địa chỉ đúng cho mọi người dùng. `LdapNameBuilder` giúp escape ký tự DN; nó không thể tự tìm vị trí entry.

## 5. Tại sao không thể chỉ chuyển đổi chuỗi member qua lại?

### 5.1. Từ tên đăng nhập sang DN

Quy trình đúng khi cần chuyển `memberUid: lan` thành DN:

```text
memberUid: lan
     |
     v
Chọn directory/tenant và vùng user được phép tìm
     |
     v
Tìm entry theo thuộc tính login tương ứng (ví dụ uid=lan)
     |
     +-- 0 entry -> lỗi tham chiếu / không tồn tại
     +-- >1 entry -> không duy nhất, cần xử lý
     |
     v
Lấy DN thực tế của entry khớp
     |
     v
DN: uid=lan,ou=people,dc=example,dc=org
```

Nếu chưa biết user nằm dưới `ou=people` hay `ou=contractors`, đừng ghép `"uid=" + login + ",ou=people,..."`. Ngoài sai vị trí, cách ghép chuỗi này còn bỏ qua quy tắc DN escaping đối với dấu phẩy, dấu cộng và ký tự đặc biệt.

Ví dụ một người dùng có `uid=lan` xuất hiện ở **hai naming context**. Giá trị `memberUid: lan` không đủ để xác định user nào nếu không có thêm phạm vi hoặc quy ước. Cần định nghĩa cặp `(directoryId, login)`, hoặc khóa ổn định từ directory và cách tra ngược về DN.

### 5.2. Từ DN sang tên đăng nhập

Khi đọc `member: cn=Lan Nguyen,ou=people,dc=example,dc=org`, đừng lấy tên từ **RDN đầu tiên** (`cn=Lan Nguyen`) rồi gọi đó là `uid`. Tên đăng nhập có thể được lưu trong thuộc tính `uid`/`sAMAccountName` của entry và có thể **khác hoàn toàn** `cn`.

Quy trình cần làm:

1. Parse DN bằng `LdapName` hoặc sử dụng kết quả DN đã có từ directory.
2. Dùng quyền đọc được cấp để tìm entry theo DN đó, tại context/naming context thích hợp.
3. Đọc thuộc tính đăng nhập theo schema của backend.
4. Kiểm tra dữ liệu thiếu, trùng, người dùng đã xóa/di chuyển và quyền đọc thuộc tính.

Nếu `member` chứa DN của **một nhóm khác**, chuyển thành login name người dùng còn có thể là sai ngay ở mức loại đối tượng. Kiểm tra `objectClass` của entry đích khi cần.

## 6. Cập nhật membership: hai kiểu ghi khác nhau

`member` và `memberUid` thường là thuộc tính đa trị. Với `LdapTemplate`, có thể sửa một giá trị bằng LDAP Modify thay vì ghi đè cả danh sách thành viên:

**`GroupMembershipWriter.java`**

```java
package com.example.ldap;

import javax.naming.Name;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;
import org.springframework.ldap.core.LdapTemplate;

public class GroupMembershipWriter {
    private final LdapTemplate ldapTemplate;

    public GroupMembershipWriter(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public void addDnMember(Name groupRelativeDn, Name userFullDn) {
        ModificationItem change = new ModificationItem(
                DirContext.ADD_ATTRIBUTE,
                new BasicAttribute("member", userFullDn.toString()));
        ldapTemplate.modifyAttributes(
                groupRelativeDn, new ModificationItem[] { change });
    }

    public void addLoginMember(Name groupRelativeDn, String login) {
        if (login == null || login.isBlank()) {
            throw new IllegalArgumentException("login không được rỗng");
        }
        ModificationItem change = new ModificationItem(
                DirContext.ADD_ATTRIBUTE,
                new BasicAttribute("memberUid", login));
        ldapTemplate.modifyAttributes(
                groupRelativeDn, new ModificationItem[] { change });
    }
}
```

Trong ví dụ này:

- `groupRelativeDn` là DN **tương đối với `ContextSource.base`**, ví dụ `cn=app-admins,ou=groups`.
- `userFullDn` là DN **đầy đủ của thành viên**, ví dụ `uid=lan,ou=people,dc=example,dc=org`, dùng làm giá trị `member`.
- `login` chỉ là chuỗi đăng nhập `lan`, dùng làm giá trị `memberUid`.
- `DirContext.ADD_ATTRIBUTE` thêm **một giá trị** vào thuộc tính đa trị; để xóa giá trị đã chọn, LDAP Modify có thể dùng `DirContext.REMOVE_ATTRIBUTE` với `BasicAttribute` chứa đúng giá trị cần xóa.

**Không gọi các thao tác ghi khi chưa kiểm tra** `objectClass`/schema nhóm, quyền chỉnh sửa, danh tính người dùng, giá trị hiện có và chính sách phân quyền. Với `groupOfNames`, xóa thành viên **cuối cùng** có thể vi phạm schema vì lớp này yêu cầu `member`. `posixGroup` thì `memberUid` có thể vắng mặt. Thêm một DN không tự tạo entry đích; tham chiếu DN cũng không được tự động duy trì sau rename/move ở mọi LDAP server.

Khi một ứng dụng dùng Spring Data LDAP repository cho entity nhóm, các trường tập hợp cần được ánh xạ phù hợp với thuộc tính `member` hoặc `memberUid`; vẫn phải chọn đúng kiểu giá trị. Nếu cần cập nhật đúng một thành viên với kiểm soát schema, `LdapTemplate.modifyAttributes` giúp diễn đạt ý định rõ ràng.

## 7. Nhóm lồng nhau, thuộc tính memberOf và primary group

### 7.1. Thành viên trực tiếp và thành viên kế thừa

Một `groupOfNames` có thể chứa DN của **nhóm khác** trong các triển khai cho phép:

```ldif
dn: cn=platform,ou=groups,dc=example,dc=org
objectClass: top
objectClass: groupOfNames
cn: platform
member: cn=app-admins,ou=groups,dc=example,dc=org
```

Khi đó, Lan là thành viên trực tiếp của `app-admins` nhưng **không nhất thiết** là giá trị `member` trực tiếp của `platform`. Truy vấn `(member=uid=lan,ou=people,...)` trên `platform` có thể không khớp. Muốn xác định “Lan thuộc nhóm platform hay không” theo quan hệ lồng nhau, cần cơ chế đệ quy/chaining group membership riêng, giới hạn vòng lặp, độ sâu và quyền truy cập. Một số directory có matching rule chuyên biệt, nhưng không phải tính năng LDAP chung của mọi server.

### 7.2. `memberOf` không thay thế mọi truy vấn member

Một số directory (chẳng hạn Active Directory hoặc LDAP server có overlay tương ứng) cung cấp `memberOf` trên entry người dùng để truy vết nhóm chứa user. Tuy nhiên:

- `memberOf` không phải thuộc tính bắt buộc của `inetOrgPerson` trên mọi directory.
- Cơ chế duy trì, hiển thị, phạm vi và tính đệ quy của `memberOf` là **đặc thù server/cấu hình**.
- Với Active Directory, nhóm chính dùng `primaryGroupID` có thể không được liệt kê theo cách giống các group membership thông thường trong `memberOf`.
- `memberOf` được dùng với mô hình DN-based; nó không tự biến `memberUid` của POSIX thành quan hệ group DN.

Đối với POSIX, còn có chiều membership qua `posixAccount.gidNumber` tương ứng với `posixGroup.gidNumber`. Vì vậy một hàm chỉ tìm `posixGroup.memberUid=lan` có thể **bỏ sót nhóm chính**.

### 7.3. Rename/move và tính ổn định của tham chiếu

Ví dụ Lan được chuyển:

```text
Trước: uid=lan,ou=people,dc=example,dc=org
Sau:   uid=lan,ou=contractors,dc=example,dc=org
```

Giá trị `member` dạng DN trước đó có thể cần thay đổi để trỏ đến DN mới. Một vài directory tự duy trì referential integrity nhờ cơ chế chuyên dụng; **không giả định server nào cũng tự cập nhật**. Nếu `uid` vẫn là `lan`, `memberUid: lan` có thể không đổi, nhưng quy ước ánh xạ tên đăng nhập sang tài khoản nay phải bao phủ vùng mới.

Nếu đổi tên đăng nhập từ `lan` sang `lan2` mà DN vẫn dựa trên `cn`, giá trị `memberUid` phải được đánh giá và cập nhật theo nghiệp vụ dù DN không đổi. Đối với định danh ổn định hơn trong nội bộ hệ thống, cân nhắc thuộc tính như `entryUUID`/`objectGUID` tùy backend, chứ không thay thế tự động mọi `member` của schema bằng những giá trị đó.

## 8. Bảo mật và tính toàn vẹn khi đọc/ghi nhóm

Group membership thường ảnh hưởng trực tiếp đến **ủy quyền**. Một lỗi hiểu nhầm `member` và `memberUid` có thể cấp hoặc thu hồi quyền sai.

Các nguyên tắc:

1. **Dựa vào schema thực tế:** kiểm tra `objectClass`, thuộc tính member và syntax/matching rule trên directory trước khi diễn giải hoặc ghi dữ liệu.
2. **Giữ ranh giới identity:** không sử dụng login name làm khóa toàn cục khi có nhiều tenant/domain; không đoán DN từ login name nếu chưa xác minh entry.
3. **Escape đúng loại:** tạo DN bằng `LdapNameBuilder`; tạo filter bằng `LdapQueryBuilder`, không tự nối chuỗi từ input.
4. **Giới hạn quyền:** tài khoản đọc nhóm chỉ cần ACL đọc; tài khoản ghi chỉ được thay đổi nhóm đã cho phép. Không trao quyền sửa nhóm quản trị rộng chỉ để kiểm thử.
5. **Đọc kết quả đầy đủ:** có thể tồn tại giới hạn số kết quả, referral, ACL, nhóm lồng nhau và nhóm chính. Không kết luận user “không thuộc nhóm nào” chỉ từ một truy vấn thiếu phạm vi.
6. **Ghi và kiểm toán:** kiểm tra sự tồn tại của user/group, hành vi khi thêm trùng hoặc xóa thành viên cuối; lưu log audit không chứa credential hay thông tin nhạy cảm không cần thiết.

Các thao tác cập nhật một entry thông qua LDAP Modify có thể được xử lý nguyên tử ở mức thao tác đó theo server; chúng không tạo ra giao dịch ACID nhiều entry khi phải đồng thời thay đổi user và nhiều group.

## 9. Kiểm thử để tránh nhầm lẫn

### 9.1. Kiểm thử DN escaping độc lập với server

JUnit 5 có thể xác minh mã tạo DN không tách nhầm dấu phẩy trong giá trị:

**`MembershipDnTest.java`**

```java
package com.example.ldap;

import javax.naming.Name;
import javax.naming.ldap.LdapName;
import org.junit.jupiter.api.Test;
import org.springframework.ldap.support.LdapNameBuilder;

import static org.junit.jupiter.api.Assertions.assertEquals;

class MembershipDnTest {
    @Test
    void commaInUidIsStillOneRdnValue() throws Exception {
        Name fullDn = LdapNameBuilder.newInstance("dc=example,dc=org")
                .add("ou", "people")
                .add("uid", "lan,team")
                .build();

        LdapName parsed = new LdapName(fullDn.toString());
        assertEquals(4, parsed.size());
        assertEquals("lan,team",
                parsed.getRdn(parsed.size() - 1).getValue());
    }
}
```

Test này bảo vệ **cách biểu diễn DN**; nó chưa chứng minh `member` thật sự trỏ tới một entry đang tồn tại. Membership thực sự phải được kiểm tra ở LDAP directory vì matching rule và schema do server thực thi.

### 9.2. Ma trận kiểm thử tích hợp với LDAP test directory

Chuẩn bị directory thử nghiệm có `ou=people` và `ou=groups`, nạp hai user cùng các nhóm `groupOfNames` và `posixGroup` ở phần đầu bài. Bảo đảm directory có schema RFC 2307 nếu sử dụng `posixGroup`.

| Kịch bản | Kết quả mong đợi |
|---|---|
| Tìm `member=uid=lan,ou=people,...` trong `groupOfNames` | Trả nhóm `app-admins` |
| Tìm `memberUid=lan` trong `posixGroup` | Trả nhóm `unix-engineering` |
| Dùng `member=lan` cho `groupOfNames` | Không tương đương với DN member; có thể không hợp lệ cú pháp hoặc không khớp |
| Dùng `memberUid=uid=lan,ou=people,...` cho `posixGroup` | Không khớp `memberUid: lan` |
| User đổi DN nhưng giữ login | Kiểm tra cập nhật/chính sách referential integrity của `member`; `memberUid` có thể vẫn giữ |
| User đổi login nhưng giữ DN | Kiểm tra cập nhật `memberUid`, không mặc định member DN đổi |
| Một login xuất hiện ở hai nhánh | Không đoán DN; báo dữ liệu không duy nhất nếu phạm vi không rõ |
| Nhóm lồng nhau | Truy vấn trực tiếp và truy vấn có mở rộng nhóm cho kết quả khác nhau |
| POSIX primary group | `gidNumber` có thể biểu diễn membership không có trong `memberUid` |
| Giá trị có `*`, `(`, dấu phẩy hoặc dấu `\` | Query builder/Name builder không đổi ý nghĩa dữ liệu đầu vào |
| Không đủ ACL đọc/ghi nhóm | Lỗi quyền rõ ràng, không coi là người dùng không có nhóm |

Nên kiểm thử cả việc thêm/xóa **một giá trị** member trên group thử nghiệm, xử lý thành viên trùng lặp, nhóm không tồn tại, và trường hợp xóa giá trị cuối của `groupOfNames`. Không chạy kiểm thử ghi trên directory thật khi chưa có vùng dữ liệu và quyền kiểm thử riêng.

### 9.3. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Truy vấn group DN không thấy dù user có `uid=lan` | Truyền `lan` vào `member` thay vì full DN | Lấy đúng DN thực tế của user |
| Truy vấn POSIX group không thấy | Truyền full DN vào `memberUid` thay vì login | Dùng thuộc tính login mà RFC 2307/server đang dùng |
| Sai người dùng khi nhiều DN có `uid` giống nhau | Login name không duy nhất toàn namespace | Thêm phạm vi directory/tenant, kiểm tra số kết quả |
| Group bị “mất” member sau rename/move | Tham chiếu `member` còn DN cũ | Kiểm tra plugin referential integrity hoặc cập nhật tham chiếu |
| User có POSIX primary group nhưng `memberUid` trống | Primary group biểu diễn qua `gidNumber` | Đối chiếu `posixAccount.gidNumber` với `posixGroup.gidNumber` |
| Tìm `memberOf` trên OpenLDAP nhưng không có | Overlay/tính năng không được bật hoặc quyền đọc khác | Kiểm tra server; có thể truy vấn trực tiếp group |
| Không xác định được nested membership | Chỉ truy vấn member trực tiếp | Thiết kế mở rộng nhóm theo khả năng directory |
| LDAP filter sai khi username có dấu `*` | Nối filter từ input | Dùng `LdapQueryBuilder.where(...).is(...)` |
| Xóa member cuối báo schema violation | `groupOfNames` yêu cầu `member` | Quy định cách giải thể nhóm và xử lý schema hợp lệ |

## 10. Câu hỏi tự đánh giá

1. `groupOfNames.member` và `posixGroup.memberUid` lưu loại giá trị nào? Vì sao không thể thay thế trực tiếp cho nhau?
2. Với `member: uid=lan,ou=people,dc=example,dc=org`, vì sao lấy `"lan"` từ RDN đầu tiên có thể sai?
3. Khi `ContextSource.base` là `dc=example,dc=org`, DN của group truyền cho `modifyAttributes` và giá trị `member` khác nhau thế nào?
4. Viết ý tưởng tìm các nhóm `groupOfNames` chứa một DN user xác định bằng `LdapQueryBuilder`. Vì sao nên dùng `.is(fullDn.toString())`?
5. Một `posixAccount` có `gidNumber=2100` nhưng không xuất hiện trong `memberUid` của group `2100`. Điều đó có thể có ý nghĩa gì?
6. Khi user bị chuyển sang `ou=contractors` nhưng không đổi login, bạn sẽ kiểm tra những loại membership nào?
7. `memberOf` và nested group có luôn được Spring LDAP tự động tính toán không?
8. Nếu hai directory cùng có login name `lan`, điều gì cần biết trước khi chuyển `memberUid` thành DN?

**Ghi nhớ:** `member` (theo `groupOfNames`) chứa **DN đầy đủ của entry**; `memberUid` (theo `posixGroup` trong RFC 2307) chứa **tên đăng nhập**. Hãy đọc schema trước khi diễn giải, truy vấn bằng đúng thuộc tính và kiểu giá trị, kiểm tra các trường hợp primary/nested group, dùng filter và DN builder an toàn, và xác minh trên directory thử nghiệm.

### Tài liệu tham khảo

- IETF [RFC 4519 — LDAP Schema for User Applications](https://www.rfc-editor.org/rfc/rfc4519): thuộc tính `member`, `uniqueMember` và lớp `groupOfNames`/`groupOfUniqueNames`.
- IETF [RFC 2307 — Using LDAP as a Network Information Service](https://www.rfc-editor.org/rfc/rfc2307): `posixGroup`, `memberUid`, `gidNumber`, `posixAccount`.
- IETF [RFC 4514 — String Representation of Distinguished Names](https://www.rfc-editor.org/rfc/rfc4514): cú pháp DN và escape giá trị RDN.
- IETF [RFC 4515 — String Representation of Search Filters](https://www.rfc-editor.org/rfc/rfc4515): cú pháp và escape LDAP filter.
- Spring LDAP: [`LdapQueryBuilder`](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/query/LdapQueryBuilder.html), [`LdapTemplate`](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/core/LdapTemplate.html), [`LdapNameBuilder`](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/support/LdapNameBuilder.html).
