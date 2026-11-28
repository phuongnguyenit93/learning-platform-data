# Thay đổi mật khẩu, trạng thái tài khoản và chính sách riêng máy chủ

Trong LDAP, **đổi mật khẩu**, **đặt lại mật khẩu**, **khóa tài khoản**, **vô hiệu hóa tài khoản** và **buộc đổi mật khẩu ở lần đăng nhập kế tiếp** là những thao tác khác nhau. Giao thức LDAP có một số cơ chế chung, nhưng cách lưu password, cách áp dụng chính sách, tên operational attribute và cách biểu diễn trạng thái tài khoản phụ thuộc directory server. Một đoạn code ghi trực tiếp thuộc tính mật khẩu có thể chạy trên OpenLDAP nhưng thất bại trên Active Directory, hoặc có thể bỏ qua chính sách mà người vận hành kỳ vọng.

Bài học thuộc chương **Khác biệt máy chủ** của module **SPRING_DATA_LDAP**. Người học sẽ phân biệt các thao tác password change/reset, tìm hiểu **LDAP Password Modify Extended Operation (RFC 3062)**, so sánh **OpenLDAP**, **Active Directory Domain Services (AD DS)** và **389 Directory Server/Red Hat Directory Server**, đọc trạng thái tài khoản, hiểu password policy và account lockout, tích hợp với **Spring LDAP/Spring Security**, xây dựng adapter theo năng lực server và kiểm thử an toàn.

> **Nguyên tắc thiết kế:** Không coi thuộc tính mật khẩu hoặc trạng thái tài khoản là một schema LDAP portable. Trước khi ghi, xác định **server**, **cơ chế password change**, **bind identity**, **quyền**, **TLS/SASL protection** và **password policy** đang có hiệu lực. Để directory server thực thi policy và lưu trữ password theo cơ chế của nó.

## 1. Phân biệt năm thao tác thường bị gọi chung là “đổi mật khẩu”

Các yêu cầu dưới đây có ý nghĩa khác nhau:

| Thao tác | Người thực hiện thường gặp | Điều kiện chính | Kết quả |
| --- | --- | --- | --- |
| **User password change** | Chính người dùng | Xác minh mật khẩu hiện tại hoặc xác thực theo policy | Mật khẩu mới thay thế mật khẩu cũ |
| **Administrative password reset** | Helpdesk/quản trị viên được ủy quyền | Quyền reset password trên entry | Đặt mật khẩu mới mà không cần biết mật khẩu cũ |
| **Force password change** | Quản trị viên hoặc policy | Server có cơ chế yêu cầu đổi khi đăng nhập tiếp theo | User phải đổi mật khẩu trước khi tiếp tục theo policy |
| **Account lockout** | Password policy tự động | Số lần bind thất bại vượt ngưỡng hoặc điều kiện lockout | Tạm thời ngăn xác thực |
| **Account disable/inactivation** | Quản trị viên hoặc lifecycle workflow | Quyền thay đổi trạng thái account | Chặn xác thực cho tới khi được kích hoạt lại |

Một số trạng thái có thể cùng tồn tại. Ví dụ tài khoản vừa bị disable vừa có password expired; tài khoản locked có thể tự mở sau thời gian lockout hoặc cần quản trị viên unlock. **Password expired** không đồng nghĩa **account expired**, và **account locked** không đồng nghĩa **account disabled**.

### 1.1. Mô hình trạng thái nên giữ riêng

Trong ứng dụng, tránh chỉ có một boolean tên **enabled** rồi gộp mọi nguyên nhân:

~~~text
Account:
  enabled                  = true / false
  locked                   = true / false
  passwordExpired          = true / false
  mustChangePassword       = true / false
  accountExpired           = true / false
  passwordChangeAllowed    = true / false
  passwordPolicyReference  = DN hoặc mã policy (nếu có)
~~~

Đây là **mô hình domain minh họa**, không phải bộ thuộc tính LDAP tiêu chuẩn. Adapter của từng server sẽ đọc các attribute/controls tương ứng và chuyển thành trạng thái nghiệp vụ. Không mặc định mọi directory có thể trả đủ tất cả trường này.

### 1.2. Luồng password change

~~~mermaid
sequenceDiagram
    participant U as User
    participant A as Spring application
    participant S as LDAP server
    U->>A: Gửi mật khẩu hiện tại + mật khẩu mới qua TLS
    A->>A: Xác thực phiên và authorize thao tác
    A->>S: Password Modify hoặc LDAP Modify đặc thù
    S->>S: Kiểm tra quyền, policy, history, quality
    alt Policy chấp nhận
        S-->>A: success
        A-->>U: Đổi mật khẩu thành công
    else Policy từ chối
        S-->>A: LDAP error / policy response
        A-->>U: Thông báo an toàn và hướng dẫn phù hợp
    end
~~~

Ứng dụng không nên tự kết luận password mới hợp lệ chỉ vì kiểm tra độ dài ở giao diện. **Directory server là nơi thực thi password policy cuối cùng**.

## 2. Phần chung của LDAP và phần riêng của từng server

LDAP chuẩn hóa nhiều thao tác giao thức, nhưng không quy định một thuộc tính chung duy nhất để biểu diễn mọi trạng thái tài khoản hay một password policy hoàn chỉnh áp dụng giống nhau ở mọi sản phẩm.

| Thành phần | Tính portable |
| --- | --- |
| LDAP Bind, Search, Modify | Giao thức LDAP chuẩn |
| LDAP Password Modify Extended Operation | Chuẩn hóa trong **RFC 3062**, nhưng server phải hỗ trợ |
| DN, objectClass, attribute syntax | Theo LDAP schema và server configuration |
| Attribute tên **userPassword** | Phổ biến trong nhiều directory, nhưng cách lưu và policy khác nhau |
| **unicodePwd** | Thuộc cơ chế riêng của Active Directory |
| **userAccountControl**, **pwdLastSet** | Thuộc tính/semantics của Active Directory |
| OpenLDAP **ppolicy overlay** | Extension dựa trên password-policy Internet-Draft, không phải một RFC chuẩn hóa hiện hành |
| **nsAccountLock**, **passwordRetryCount** | Đặc trưng của 389/Red Hat Directory Server |
| Password history, lockout, expiry | Policy và implementation phụ thuộc server |

Đừng viết một lớp Java chung giả định rằng chỉ cần đọc attribute có tên **locked**, **disabled** hoặc **passwordExpired** là có thể xử lý mọi directory.

## 3. LDAP Password Modify Extended Operation — RFC 3062

**RFC 3062** định nghĩa một LDAPv3 Extended Operation dành cho thay đổi mật khẩu. OID của operation:

~~~text
1.3.6.1.4.1.4203.1.11.1
~~~

Operation có thể mang ba trường:

| Trường | Ý nghĩa |
| --- | --- |
| **userIdentity** | Định danh người dùng cần đổi mật khẩu; có thể vắng mặt để dùng danh tính bind hiện tại |
| **oldPasswd** | Mật khẩu hiện tại; có thể vắng mặt nếu policy server cho phép cơ chế đó |
| **newPasswd** | Mật khẩu mới; có thể vắng mặt nếu server được phép tạo password |

Server có thể trả mật khẩu do nó tạo ra trong response. Nếu client gửi **newPasswd**, server không được tự thay bằng một mật khẩu khác. Server chỉ trả success khi thay đổi thật sự thành công; nếu không, phải trả result code khác success và giữ password cũ.

### 3.1. Kiểm tra server có hỗ trợ hay không

Server có thể công bố extended operation trong operational attribute **supportedExtension** của **Root DSE**. OID cần tìm là **1.3.6.1.4.1.4203.1.11.1**.

Ví dụ với OpenLDAP command-line client:

~~~bash
export LDAP_URI='ldaps://ldap.lab.example:636'
export READER_DN='uid=reader,ou=services,dc=lab,dc=example'

ldapsearch -LLL -x -H "$LDAP_URI" \
  -D "$READER_DN" -W \
  -b '' -s base '(objectClass=*)' \
  supportedExtension supportedControl
~~~

Root DSE có base DN rỗng và scope **base**. Kết quả phải được đọc từ đúng server/endpoint mà ứng dụng thực sự sử dụng. Một số server chỉ quảng bá operation khi client đã được xác thực hoặc có đủ điều kiện bảo mật/quyền.

**Không thấy OID không có nghĩa có thể thay thế operation bằng một lệnh Modify tùy ý.** Cần dùng cơ chế riêng mà server tài liệu hóa.

### 3.2. Bảo mật của Password Modify

RFC 3062 không tự mã hóa hoặc bảo vệ tính toàn vẹn cho password. Operation phải chạy trong kênh có **confidentiality protection**, chẳng hạn **LDAPS** hoặc **StartTLS** với chứng chỉ được xác minh; cơ chế SASL có mã hóa cũng có thể đáp ứng khi server cho phép.

Operation này **không được dùng anonymously**. Server nên từ chối request nếu thiếu bảo vệ bảo mật cần thiết; client phải xác thực danh tính và có quyền phù hợp trước khi đổi password.

- Không gửi password qua simple bind trên kết nối không mã hóa.
- Không ghi old/new password vào log, trace, exception message hoặc audit payload.
- Không truyền password qua query string, URL, command-line argument hoặc file LDIF lưu lâu dài.
- Không lưu password vào entity, cache, session hoặc file cấu hình.
- Dùng tài khoản bind có quyền tối thiểu; không dùng Directory Manager/domain admin chỉ để tránh lỗi.

### 3.3. Password policy response control

Một số server hỗ trợ **Password Policy Request/Response Control** để gửi cảnh báo password sắp hết hạn, số lần grace login còn lại hoặc lý do policy từ chối. Đây là một cơ chế control riêng, không phải nội dung tự động có trong mọi response của RFC 3062.

Ứng dụng phải kiểm tra năng lực server và client library. Nếu không nhận được policy control, không suy ra password không hết hạn hoặc tài khoản không bị khóa.

## 4. Đổi mật khẩu và đặt lại mật khẩu là hai quyền khác nhau

Một user tự đổi mật khẩu thường phải chứng minh mình biết mật khẩu hiện tại hoặc đáp ứng phương thức xác thực mà server chấp nhận. Quản trị viên reset mật khẩu thường không biết password cũ nhưng cần **quyền reset password** rõ ràng.

~~~text
USER CHANGE
  bind/authenticate as user
  provide old password (or server-approved proof)
  provide new password
  server checks old password + change permission + policy

ADMIN RESET
  bind as delegated administrator/helpdesk
  target a user's DN
  provide new password
  server checks reset permission + policy
~~~

Đừng cho API của người dùng gọi đường reset bằng service account có quyền sửa mọi password. Đừng dùng password hiện tại do client gửi để tự chọn DN mục tiêu mà không kiểm tra session identity.

## 5. OpenLDAP: userPassword và ppolicy overlay

### 5.1. Thuộc tính mật khẩu phổ biến

Trong OpenLDAP, password của entry người dùng thường được quản lý qua **userPassword**. Giá trị lưu trong directory thường là password hash theo scheme server hỗ trợ, không nên là plaintext. Tên scheme và thuật toán phụ thuộc cấu hình, phiên bản và chính sách triển khai.

~~~ldif
dn: uid=linh,ou=people,dc=lab,dc=example
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: linh
cn: Linh Nguyen
sn: Nguyen
userPassword: {SCHEME}HASH_VALUE
~~~

**{SCHEME}HASH_VALUE** chỉ là placeholder minh họa, không phải password dùng được. Không đưa hash thật vào tài liệu, fixture công khai hoặc log. Việc lưu password nên do server hoặc password-management API có chủ đích thực hiện.

### 5.2. Password Policy overlay

OpenLDAP có **ppolicy overlay** để triển khai password policy. Theo Administrator's Guide, overlay dựa trên một Internet-Draft password policy đã hết hạn, dù được nhiều directory server triển khai. Vì vậy phải xem đây là **khả năng cụ thể của OpenLDAP/server**, không mặc định là LDAP core feature.

Overlay có thể hỗ trợ:

- Độ dài tối thiểu và kiểm tra chất lượng password.
- Tuổi tối thiểu/tối đa của password.
- Lịch sử password, ngăn tái sử dụng password cũ.
- Cảnh báo password sắp hết hạn và grace authentication.
- Khóa sau nhiều lần bind sai và thời gian unlock.
- Buộc người dùng đổi password ở lần xác thực tiếp theo.
- Policy mặc định hoặc policy áp dụng theo entry/subtree.

### 5.3. Các thuộc tính policy thường gặp

| Attribute | Ý nghĩa trong ppolicy implementation |
| --- | --- |
| **pwdPolicySubentry** | DN của policy áp dụng cho entry, nếu được cấu hình |
| **pwdAttribute** | Attribute chứa password, thường là userPassword trong OpenLDAP |
| **pwdMinLength** | Độ dài tối thiểu |
| **pwdMaxAge** | Tuổi tối đa của password |
| **pwdMinAge** | Khoảng thời gian tối thiểu giữa hai lần đổi |
| **pwdInHistory** | Số password cũ cần giữ để ngăn tái sử dụng |
| **pwdCheckQuality** | Cách server xử lý việc kiểm tra chất lượng password |
| **pwdMaxFailure** | Số lần bind thất bại tối đa |
| **pwdLockout** | Có bật khóa sau nhiều lần thất bại hay không |
| **pwdLockoutDuration** | Thời gian khóa |
| **pwdGraceAuthNLimit** | Số lần grace authentication sau khi password hết hạn |
| **pwdMustChange** | Chính sách buộc đổi password sau reset |
| **pwdSafeModify** | Có yêu cầu password hiện tại trong user password change hay không |

Các thuộc tính và cách áp dụng cụ thể phụ thuộc schema/overlay được cài. Không đưa chúng vào một entry người dùng tùy tiện khi server chưa nạp ppolicy schema hoặc overlay.

### 5.4. Operational attributes về password state

OpenLDAP ppolicy có thể duy trì các operational attribute như **pwdChangedTime**, **pwdFailureTime**, **pwdAccountLockedTime**, **pwdGraceUseTime**. Một số thuộc tính chỉ xuất hiện khi có trạng thái tương ứng hoặc được yêu cầu trong search theo quy tắc operational attributes.

Không coi việc search không trả **pwdAccountLockedTime** là bằng chứng chắc chắn rằng account đang active: có thể overlay chưa bật, ACL che thuộc tính, hoặc server sử dụng policy khác.

Có thể yêu cầu các operational attributes trong một lần đọc entry:

~~~bash
ldapsearch -LLL -x -H "$LDAP_URI" \
  -D "$READER_DN" -W \
  -b 'uid=linh,ou=people,dc=lab,dc=example' -s base \
  '(objectClass=*)' dn pwdPolicySubentry pwdChangedTime \
  pwdAccountLockedTime pwdFailureTime pwdGraceUseTime +
~~~

Dấu **+** yêu cầu các operational attributes mà server cho phép trả về. Kết quả phụ thuộc overlay, ACL và phiên bản; lệnh không phải cách kiểm tra portable cho AD.

### 5.5. Hash password ở phía server

Nếu client gửi sẵn hash thay vì password rõ qua kênh bảo mật, server có thể không kiểm tra được chất lượng password theo policy. Với **pwdCheckQuality=2**, OpenLDAP có thể từ chối password mà server không thể kiểm tra chất lượng. Cấu hình **ppolicy_hash_cleartext** cho phép overlay hash cleartext theo password storage scheme đã chọn.

Điều này không có nghĩa gửi plaintext trên mạng không mã hóa. Password chỉ được gửi qua **TLS/SASL confidentiality protection**; server thực hiện hashing khi xử lý lưu trữ.

### 5.6. Unlock và inactivate

Khi ppolicy khóa user sau nhiều lần bind thất bại, trạng thái lockout do overlay quản lý. Quản trị viên phải dùng quy trình được tài liệu hóa cho phiên bản server, đúng quyền và đúng policy. Không tự xóa một operational attribute chỉ vì thấy tên của nó có vẻ biểu diễn lockout.

Vô hiệu hóa tài khoản lâu dài là một quyết định khác với lockout tạm thời. Nếu cần inactivate, hãy dùng cơ chế account lifecycle/ACL phù hợp và ghi nhận rõ trạng thái nghiệp vụ.

## 6. Active Directory: unicodePwd là cơ chế riêng

Active Directory Domain Services lưu password của user hoặc inetOrgPerson trong **unicodePwd**. Thuộc tính này có quy tắc đặc biệt:

- Có thể **ghi bằng LDAP Modify** trong điều kiện giới hạn.
- Không được trả về trong LDAP Search.
- Giá trị truyền là chuỗi Unicode **UTF-16** có dấu ngoặc kép bao quanh password, sau đó được mã hóa như BER OCTET STRING.
- Kết nối phải được bảo vệ bằng **TLS/SSL có độ mạnh tối thiểu theo tài liệu Microsoft**, hoặc SASL encryption đáp ứng yêu cầu của phiên bản server.

Không đọc **unicodePwd** để xác minh password. Xác minh bằng cách dùng phương thức xác thực được phê duyệt trong môi trường test, không thử liên tục trên account thật.

### 6.1. User tự đổi password trên AD

Đối với thao tác user change, LDAP ModifyRequest phải chứa **hai modification trong cùng một request**:

1. **DELETE unicodePwd** với password hiện tại, có dấu ngoặc kép.
2. **ADD unicodePwd** với password mới, có dấu ngoặc kép.

Directory kiểm tra password cũ và quyền **User-Change-Password** trên chính object. Nếu old password không đúng, hoặc user không có quyền change, operation thất bại.

### 6.2. Helpdesk/admin reset password trên AD

Đối với administrative reset, ModifyRequest dùng một thao tác **REPLACE unicodePwd** chứa password mới có dấu ngoặc kép. Bind identity phải có control access right **User-Force-Change-Password** trên target user/inetOrgPerson.

**Không nhầm reset với change.** Nếu dùng DELETE + ADD cho reset, hoặc REPLACE nhưng chạy dưới identity không có quyền reset, server có thể từ chối.

### 6.3. Mã hóa giá trị unicodePwd

Ví dụ chuỗi password về mặt khái niệm:

~~~text
password mong muốn: Example-Value
chuỗi trước khi encode: "Example-Value"
encoding: UTF-16LE/Unicode
giá trị LDAP: byte array được gửi dưới dạng OCTET STRING
~~~

Trong JNDI, một **byte[]** truyền làm giá trị attribute sẽ được LDAP provider mã hóa như OCTET STRING. Client phải tạo byte array từ chuỗi đã đặt dấu ngoặc kép và UTF-16LE theo tài liệu Microsoft. Không gửi trực tiếp Java String UTF-8 vào attribute này.

### 6.4. Ví dụ JNDI/Spring LDAP ở mức thao tác

Đoạn mã dưới đây minh họa **user change** trên AD. Hàm **quotedUtf16Le(...)** là helper của adapter, nhận password từ nguồn an toàn và trả về byte[] theo quy tắc ở mục 6.3; helper phải xóa buffer tạm sau khi encode. **ldapTemplate** phải được cấu hình dùng kết nối LDAPS/StartTLS đã xác minh certificate. **userDn** phải là DN mục tiêu đã được ứng dụng xác minh và theo dạng relative DN phù hợp với ContextSource base:

~~~java
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;
import org.springframework.ldap.core.LdapTemplate;

public final class ActiveDirectoryPasswordChanger {
    private final LdapTemplate ldapTemplate;

    public ActiveDirectoryPasswordChanger(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public void changeOwnPassword(
            String userDn,
            char[] currentPassword,
            char[] newPassword) {

        byte[] oldValue = null;
        byte[] newValue = null;
        try {
            oldValue = quotedUtf16Le(currentPassword);
            newValue = quotedUtf16Le(newPassword);

            ModificationItem[] changes = {
                new ModificationItem(
                    DirContext.REMOVE_ATTRIBUTE,
                    new BasicAttribute("unicodePwd", oldValue)
                ),
                new ModificationItem(
                    DirContext.ADD_ATTRIBUTE,
                    new BasicAttribute("unicodePwd", newValue)
                )
            };

            ldapTemplate.modifyAttributes(userDn, changes);
        } finally {
            if (oldValue != null) {
                java.util.Arrays.fill(oldValue, (byte) 0);
            }
            if (newValue != null) {
                java.util.Arrays.fill(newValue, (byte) 0);
            }
            java.util.Arrays.fill(currentPassword, '\0');
            java.util.Arrays.fill(newPassword, '\0');
        }
    }

    private byte[] quotedUtf16Le(char[] password) {
        // Helper cần tạo chuỗi password có dấu quote, encode UTF-16LE,
        // trả về byte[] và xóa char/byte buffer trung gian trong finally.
        throw new UnsupportedOperationException(
            "Implement with a reviewed secret-handling helper");
    }
}
~~~

Đây là **khung minh họa**; helper cố ý để trống vì cần được review riêng về secret handling và buffer lifetime. Không copy đoạn mã này vào production trước khi hoàn thiện helper, kiểm tra TLS, quyền và integration test. Ví dụ dùng DN target đã được ứng dụng xác minh, không nhận một DN tùy ý từ request.

### 6.5. Admin reset trên AD

Khi adapter được ủy quyền reset password, phần thay đổi dùng **REPLACE**:

~~~java
byte[] resetValue = quotedUtf16Le(newPassword);
try {
    ModificationItem reset = new ModificationItem(
        DirContext.REPLACE_ATTRIBUTE,
        new BasicAttribute("unicodePwd", resetValue)
    );
    ldapTemplate.modifyAttributes(
        targetUserDn, new ModificationItem[]{reset}
    );
} finally {
    java.util.Arrays.fill(resetValue, (byte) 0);
    java.util.Arrays.fill(newPassword, '\0');
}
~~~

Đây là phần minh họa operation, không phải một method độc lập có thể biên dịch nếu chưa có **quotedUtf16Le**, **ldapTemplate**, quyền **User-Force-Change-Password** và xử lý xóa buffer. Chỉ cung cấp endpoint reset cho vai trò helpdesk được ủy quyền; không cho user tự chọn target DN. DN mục tiêu phải được lấy từ đối tượng đã authorize, không nối chuỗi từ input.

## 7. Active Directory: đọc trạng thái account

AD dùng nhiều thuộc tính để biểu diễn trạng thái. Một số giá trị là bitmask, một số là timestamp, một số được server tính toán.

| Attribute | Vai trò | Lưu ý |
| --- | --- | --- |
| **userAccountControl** | Bit flags mô tả loại và tùy chọn account | Các bit cộng dồn; không ghi một số magic cố định |
| **msDS-User-Account-Control-Computed** | Các trạng thái computed như lockout/password expired trong các phiên bản AD phù hợp | Operational/computed; không coi là field để client set |
| **pwdLastSet** | Thời điểm password được đổi | Giá trị 0 yêu cầu đổi password ở lần logon kế tiếp khi điều kiện áp dụng |
| **lockoutTime** | Thời điểm lockout bắt đầu | Cần xét lockout duration và trạng thái hiện tại |
| **accountExpires** | Thời điểm account hết hạn | Khác password expiration |
| **badPwdCount / badPasswordTime** | Thông tin về lần bind sai | Có thể chịu ảnh hưởng DC đang đọc và replication semantics |
| **msDS-ResultantPSO** | Password Settings Object áp dụng cho user nếu có | Liên quan Fine-Grained Password Policies |

### 7.1. Một số bit userAccountControl

Các flag thường gặp:

| Flag | Hex | Ý nghĩa |
| --- | ---: | --- |
| **ACCOUNTDISABLE** | 0x0002 | Account bị disable |
| **LOCKOUT** | 0x0010 | Flag lockout trong mô hình bit |
| **PASSWD_NOTREQD** | 0x0020 | Password không bắt buộc theo flag |
| **NORMAL_ACCOUNT** | 0x0200 | Loại account người dùng thông thường |
| **DONT_EXPIRE_PASSWORD** | 0x10000 | Password không hết hạn theo flag |
| **PASSWORD_EXPIRED** | 0x800000 | Flag lịch sử trong tài liệu flag; trạng thái computed cần xem theo phiên bản |

Giá trị của userAccountControl là tổng hợp các bit. Ví dụ **0x0202** gồm **NORMAL_ACCOUNT (0x0200)** và **ACCOUNTDISABLE (0x0002)**. Không gán 514 cho mọi user để disable vì có thể xóa những flag hợp lệ khác.

Khi đọc giá trị số trong Java, kiểm tra bit bằng phép AND:

~~~java
long flags = Long.parseLong(userAccountControlValue);
boolean disabled = (flags & 0x0002L) != 0;
boolean passwordNeverExpires = (flags & 0x10000L) != 0;
~~~

Đây là ví dụ đọc hai bit cấu hình. Không dùng đoạn mã này để suy ra lockout hiện tại; trạng thái lockout/password-expired phải được đọc theo computed attribute và policy của phiên bản AD.

Microsoft lưu ý một số flag không thể được set/reset trực tiếp bằng userAccountControl. **PASSWD_CANT_CHANGE** được thể hiện qua quyền ACL, không phải chỉ bật bit tương ứng. Trên các phiên bản AD hiện đại, **LOCKOUT** và **PASSWORD_EXPIRED** được thể hiện qua thuộc tính computed **msDS-User-Account-Control-Computed** thay vì dựa vào việc set bit UAC như một thuộc tính thường.

### 7.2. Password expired và force change at next logon

Trong AD, **pwdLastSet = 0** là cách biểu diễn yêu cầu người dùng đổi password ở lần logon tiếp theo khi các điều kiện liên quan cho phép. Không nhầm với việc account bị disable. Không dùng **pwdLastSet** như một cờ boolean; đây là một giá trị thời gian dạng số 64-bit với quy ước đặc biệt cho 0.

### 7.3. Lockout không đồng nghĩa lockoutTime khác 0 vĩnh viễn

AD có **lockoutTime** và thời lượng lockout. Một giá trị lockoutTime khác 0 cần được đánh giá cùng **lockout duration** và trạng thái computed; thời điểm khóa có thể đã hết hạn theo policy. Đọc một thuộc tính riêng lẻ rồi kết luận account đang bị khóa có thể tạo false positive.

### 7.4. Account expiration

**accountExpires** biểu diễn thời điểm account hết hạn, khác với thời điểm password hết hạn. Ứng dụng không nên gộp cả hai thành **passwordExpired**. Khi hiển thị trạng thái account, hãy phân biệt account expiration, password expiration, disable và lockout.

Có thể đọc các thuộc tính trạng thái bằng một base search trên user DN:

~~~bash
ldapsearch -LLL -x -H "$LDAP_URI" \
  -D "$READER_DN" -W \
  -b "$USER_DN" -s base '(objectClass=*)' \
  dn userAccountControl pwdLastSet lockoutTime accountExpires \
  msDS-User-Account-Control-Computed msDS-ResultantPSO
~~~

Ví dụ dùng **USER_DN** là biến đã được xác minh, trỏ tới user object trong AD. Một số thuộc tính computed/operational có thể không được trả cho mọi danh tính hoặc mọi phiên bản. Không yêu cầu unicodePwd trong attribute list.

## 8. Active Directory: Fine-Grained Password Policies

AD DS hỗ trợ **Fine-Grained Password Policies (FGPP)** thông qua **Password Settings Objects (PSO)**. Một domain có thể áp dụng các chính sách password/lockout khác nhau cho những user hoặc global security groups khác nhau, ví dụ chính sách nghiêm ngặt hơn cho tài khoản đặc quyền.

Các thuộc tính policy có thể bao gồm:

- Độ dài tối thiểu, độ phức tạp và lịch sử password.
- Tuổi tối thiểu/tối đa của password.
- Ngưỡng lockout, thời lượng lockout và observation window.
- Precedence để xác định PSO có ưu tiên cao hơn khi nhiều policy áp dụng.

**Precedence số nhỏ hơn có ưu tiên cao hơn** khi nhiều PSO áp dụng và có xung đột theo quy tắc AD. Không tự chọn policy chỉ từ OU hoặc một group bất kỳ; cần xác định **resultant policy** thực sự áp dụng cho user.

Trong AD DS, Fine-Grained Password Policies áp dụng cho user objects và global security groups theo điều kiện functional level/tài liệu phiên bản. Không mặc định cơ chế này có trong AD LDS hoặc các server LDAP khác.

## 9. 389 Directory Server / Red Hat Directory Server

389 Directory Server và Red Hat Directory Server có password policy và account state attributes riêng. Khả năng và tên thuộc tính phụ thuộc phiên bản, global policy, local/subtree policy và cấu hình instance.

### 9.1. Lockout do bind thất bại

Tài liệu 389 DS mô tả các operational attribute:

| Attribute | Ý nghĩa |
| --- | --- |
| **passwordRetryCount** | Số lần bind thất bại liên tiếp |
| **retryCountResetTime** | Thời điểm bộ đếm lỗi được reset |
| **accountUnlockTime** | Thời điểm account được mở khóa |

Một policy có thể khóa account khi vượt số lần bind thất bại; sau đó server tự mở khi hết thời gian hoặc giữ trạng thái khóa tới khi admin can thiệp, tùy cấu hình.

Đọc trạng thái trên user entry trong lab:

~~~bash
ldapsearch -LLL -x -H "$LDAP_URI" \
  -D "$READER_DN" -W \
  -b "$USER_DN" -s base '(objectClass=*)' \
  dn passwordRetryCount retryCountResetTime accountUnlockTime nsAccountLock
~~~

Nếu một thuộc tính không xuất hiện, kiểm tra server version, policy, ACL và trạng thái của entry trước khi kết luận nó không được hỗ trợ.

### 9.2. Account inactivation

**nsAccountLock: TRUE** là cơ chế account inactivation trong Directory Server. Khi entry mang trạng thái này, server từ chối bind của account; entry và dữ liệu vẫn được giữ lại để có thể kích hoạt lại.

Đây là khái niệm khác với password lockout tự động. Không xóa userPassword để disable account và không thay nsAccountLock bằng thuộc tính userAccountControl của AD.

### 9.3. Password policy theo phạm vi

Directory Server có thể áp dụng policy ở phạm vi toàn server, subtree hoặc user tùy cấu hình. Các tính năng có thể bao gồm:

- Password syntax/complexity, minimum length.
- Password history và password expiration.
- Lockout sau số lần bind sai.
- Account inactivation.
- Policy riêng cho nhóm user hoặc entry.

Không mang LDIF chứa thuộc tính policy của 389 DS sang OpenLDAP/AD và mong chúng có cùng tác dụng. Kiểm tra tài liệu đúng phiên bản và command-line tool quản trị của instance.

## 10. So sánh ba nhóm server

| Khả năng | OpenLDAP | Active Directory DS | 389/Red Hat Directory Server |
| --- | --- | --- | --- |
| Password attribute phổ biến | **userPassword** | **unicodePwd** | **userPassword** thường gặp |
| Password Modify RFC 3062 | Kiểm tra supportedExtension trên instance | Không mặc định giả định; AD có quy tắc unicodePwd riêng | Kiểm tra supportedExtension trên instance/version |
| Password policy | **ppolicy overlay** nếu được cài/cấu hình | Domain policy và FGPP/PSO | Global/local password policy |
| Password lockout | ppolicy operational state | lockoutTime + computed flags/policy | passwordRetryCount, accountUnlockTime |
| Account disable/inactivation | Phụ thuộc policy/ACL hoặc schema custom | userAccountControl ACCOUNTDISABLE | nsAccountLock |
| Force password change | ppolicy policy/attributes | pwdLastSet = 0 | passwordMustChange/policy theo phiên bản |
| Policy response | Password Policy controls nếu hỗ trợ | AD-specific diagnostics/controls | Policy controls/diagnostics tùy phiên bản |
| Quyền reset | ACL và server policy | User-Force-Change-Password control access right | ACI/ACL và policy |

**Bảng là hướng dẫn nhận diện**, không phải ma trận bảo đảm mọi phiên bản đều hỗ trợ giống nhau. Luôn kiểm tra Root DSE, schema, server documentation và integration test trên môi trường mục tiêu.

## 11. Spring Data LDAP và Spring Security: vai trò khác nhau

**Spring Data LDAP** tập trung vào repository, ODM và truy cập entry. Nó không tự cung cấp một API password change portable cho mọi directory server chỉ bằng cách gọi **repository.save(...)**.

**Spring Security LDAP** có thành phần **LdapUserDetailsManager** phục vụ quản lý user details và password change. API **changePassword(oldPassword, newPassword)** dùng user hiện tại lấy từ SecurityContext. Thành phần này thuộc Spring Security, không phải LdapRepository.

### 11.1. LdapUserDetailsManager và RFC 3062

LdapUserDetailsManager có lựa chọn:

~~~java
manager.setUsePasswordModifyExtensionOperation(true);
~~~

Khi bật, phương thức **changePassword(...)** dùng Password Modify Extended Operation. Khi tắt, phương thức sửa password attribute trực tiếp trên entry. **Mặc định là false**. Trước khi bật, phải xác minh server hỗ trợ RFC 3062 và cấu hình phù hợp.

Theo Javadoc, khi không dùng extension:

- Nếu cung cấp **oldPassword**, manager có thể rebind bằng danh tính người dùng để thay đổi bằng quyền của user.
- Nếu **oldPassword** là null, thao tác được thử bằng read/write context do ContextSource cung cấp; đây là đường có thể dùng cho administrative reset khi identity được cấp quyền.

Không cho client truyền **oldPassword = null** để tự ý biến một password change thành admin reset. Authorization và danh tính thao tác phải được kiểm soát ở service.

### 11.2. Ví dụ cấu hình manager

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ldap.core.ContextSource;
import org.springframework.security.ldap.userdetails.LdapUserDetailsManager;

@Configuration
public class DirectorySecurityConfiguration {

    @Bean
    LdapUserDetailsManager ldapUserDetailsManager(
            ContextSource contextSource) {
        LdapUserDetailsManager manager =
            new LdapUserDetailsManager(contextSource);

        manager.setUsePasswordModifyExtensionOperation(true);
        return manager;
    }
}
~~~

Ví dụ giả định dependency **Spring Security LDAP** phù hợp đã được thêm, ContextSource trỏ đúng server và Root DSE đã xác nhận hỗ trợ RFC 3062. Nếu dùng AD với **unicodePwd**, không giả định việc bật extension này sẽ tự thực hiện quy tắc UTF-16/quoted value của AD; cần adapter theo cơ chế AD được tài liệu hóa.

### 11.3. Không lưu password trong ODM entity

Tránh tạo entity như:

~~~java
@Attribute(name = "userPassword")
private String password;
~~~

Password không nên được đọc vào object graph, trả qua API, ghi log hoặc serialize vào cache. Dùng password-management component riêng và chỉ chuyển secret qua kênh bảo mật trong thời gian ngắn cần thiết.

## 12. Thiết kế adapter theo server capability

Một ứng dụng hỗ trợ nhiều directory nên định nghĩa **hợp đồng nghiệp vụ** rồi cài adapter theo từng server/capability.

~~~java
public interface DirectoryPasswordService {
    void changeOwnPassword(
        DirectoryIdentity currentUser,
        char[] oldPassword,
        char[] newPassword
    );

    void resetPassword(
        DirectoryIdentity targetUser,
        char[] newPassword,
        DirectoryOperator operator
    );
}
~~~

Các kiểu **DirectoryIdentity** và **DirectoryOperator** là domain type minh họa. Chúng phải được xây dựng từ session/authorization context đã xác thực, không nhận DN tùy ý từ người gọi.

### 12.1. Phân tách capability

~~~java
public enum PasswordChangeMechanism {
    RFC3062_PASSWORD_MODIFY,
    ACTIVE_DIRECTORY_UNICODE_PWD,
    SERVER_SPECIFIC_ATTRIBUTE_MODIFY,
    UNSUPPORTED
}
~~~

Capability này nên được xác định từ cấu hình server đã được kiểm tra và kiểm thử, có thể đối chiếu Root DSE **supportedExtension**. Không phát hiện server bằng cách thử ghi password thật vào production rồi xem lỗi.

### 12.2. Hợp đồng trạng thái tài khoản

~~~java
public record DirectoryAccountStatus(
    boolean enabled,
    boolean locked,
    boolean passwordExpired,
    boolean mustChangePassword,
    boolean accountExpired
) {}
~~~

Đây là domain DTO. Adapter OpenLDAP, AD DS và 389 DS đọc những nguồn trạng thái khác nhau rồi chuyển đổi. Nếu một server không cung cấp một trạng thái đáng tin cậy, ứng dụng cần biểu diễn **unknown/not-supported** thay vì tự suy ra false.

### 12.3. Không dùng tên attribute làm chiến lược

Một cấu hình như:

~~~yaml
directory:
  password-attribute: userPassword
~~~

có thể hữu ích cho một số server, nhưng chưa đủ để hỗ trợ AD. AD cần **operation semantics**, encoding và TLS requirements của unicodePwd. Một adapter thực tế cần ít nhất:

- Cơ chế change/reset riêng.
- Cách encode value theo server.
- Quyền tối thiểu cho change và reset.
- Cách đọc password/account state.
- Cách đọc policy hiệu lực.
- Error mapping và test theo version server.

## 13. Chính sách password và thông báo lỗi

Các chính sách phổ biến:

| Chính sách | Tác dụng |
| --- | --- |
| Minimum length | Từ chối password quá ngắn |
| Complexity/syntax | Kiểm tra độ phức tạp hoặc quy tắc ký tự |
| Password history | Ngăn tái sử dụng password cũ |
| Minimum age | Không cho đổi quá thường xuyên |
| Maximum age | Buộc đổi khi password hết hạn |
| Failed bind threshold | Khóa sau nhiều lần xác thực sai |
| Lockout duration | Tự mở sau một thời gian |
| Grace authentication | Cho phép số lần đăng nhập hạn chế sau expiry |
| Must change | Buộc đổi sau reset hoặc ở lần logon kế tiếp |

### 13.1. Result code có thể khác nhau

| LDAP result | Ý nghĩa thường gặp | Lưu ý |
| ---: | --- | --- |
| **0 success** | Đổi/reset thành công | Chỉ báo thành công khi server trả success |
| **13 confidentialityRequired** | Kênh chưa đủ bảo vệ | Thiết lập TLS/SASL encryption |
| **19 constraintViolation** | Policy/constraint từ chối | Có thể là password quality hoặc lockout tùy server |
| **49 invalidCredentials** | Password cũ hoặc bind credentials sai | Không phân biệt nguyên nhân quá chi tiết cho client cuối |
| **50 insufficientAccessRights** | Thiếu quyền change/reset | Kiểm tra ACL/control access right |
| **53 unwillingToPerform** | Server không chấp nhận thao tác/policy | Xem diagnostic và tài liệu vendor |
| **12 unavailableCriticalExtension** | Extension/control bắt buộc không hỗ trợ | Kiểm tra capability và phiên bản |
| **1 operationsError** | Lỗi xử lý operation | Xem server log có kiểm soát |

Không ánh xạ một mã LDAP duy nhất thành “password yếu” trên mọi sản phẩm. Ví dụ một số phiên bản 389 DS có thể trả **constraintViolation (19)** khi vượt retry limit; AD có thể kèm diagnostic data riêng khi password policy từ chối.

### 13.2. Không tiết lộ policy nội bộ quá mức

API có thể thông báo “Mật khẩu không đáp ứng chính sách” hoặc “Bạn cần liên hệ bộ phận hỗ trợ”. Không trả nguyên diagnostic string của directory nếu nó tiết lộ tên DC, DN, cấu trúc OU, password policy nội bộ hoặc thông tin vận hành.

Log nội bộ nên có:

- Request/trace ID.
- Loại operation: user change hay admin reset.
- Server type/version đã cấu hình.
- LDAP result code và loại exception.
- Thời gian xử lý và kết quả tổng quát.

Không log oldPassword/newPassword, encoded unicodePwd, password hash hoặc raw request/response có chứa secret.

## 14. Security: TLS, quyền và xử lý secret

Password operation là đường nhạy cảm nhất của directory integration:

1. **TLS:** dùng LDAPS hoặc StartTLS với CA/hostname verification; không tắt kiểm tra chứng chỉ.
2. **Bind identity:** user change nên thực hiện với danh tính và quyền phù hợp; admin reset dùng delegated identity tối thiểu.
3. **Authorization:** xác minh caller được đổi password cho chính mình hoặc có vai trò reset đúng phạm vi.
4. **No password readback:** không Search userPassword/unicodePwd để lấy password.
5. **Secret lifetime:** giữ password trong bộ nhớ ngắn nhất có thể; xóa char/byte buffers khi có thể.
6. **No logs:** tắt logging payload hoặc che dữ liệu nhạy cảm ở tầng LDAP client/tracing.
7. **Rate limiting:** giới hạn yêu cầu đổi/reset để giảm abuse; lockout không phải cơ chế chống mọi loại DoS.
8. **Audit:** ghi ai thực hiện reset, đối tượng nào, lúc nào và kết quả; không ghi secret.
9. **Password encoder:** không tự hash password theo BCrypt/SCrypt rồi gửi vào LDAP nếu server mong nhận password rõ qua password operation. Server cần lưu trữ/hash theo policy riêng.
10. **Connection pool:** không để password hoặc request control của user này rò sang thao tác khác; reset trạng thái context đúng cách.

### 14.1. Không thay password bằng cách ghi hash tùy tiện

Đưa một giá trị **{SSHA}...** hoặc **{PBKDF2}...** vào userPassword trực tiếp có thể bỏ qua kiểm tra chất lượng hoặc tạo scheme mà server không hỗ trợ. Dùng cơ chế password operation/server policy được khuyến nghị. Nếu hệ thống bắt buộc import hash, phải có quy trình migration riêng, schema/server support rõ ràng và kiểm thử xác thực sau import.

### 14.2. Không dùng userAccountControl như ACL

Trong AD, flag **PASSWD_CANT_CHANGE** không được bật bằng cách cộng bit vào userAccountControl; đây là quyền trên object. Tương tự, quyền user tự đổi password và quyền helpdesk reset password là các control access right/ACL khác nhau. Đọc và sửa trạng thái phải tuân semantics server, không dùng một bitmask như hệ thống phân quyền tổng quát.

## 15. Kiểm tra trạng thái account mà không gây lockout

Khi xây dựng màn hình quản trị, lấy trạng thái từ **read-only search** hoặc API quản trị được hỗ trợ. Không thử Bind với nhiều password giả để xem user có locked không.

### 15.1. Câu hỏi cần trả lời

| Câu hỏi nghiệp vụ | Dữ liệu/capability cần kiểm tra |
| --- | --- |
| Account có bị disable không? | AD userAccountControl; 389 nsAccountLock; cơ chế server tương ứng |
| Account có bị lockout tạm thời không? | AD lockoutTime/computed flags; OpenLDAP ppolicy; 389 lockout attributes |
| Password có hết hạn không? | Policy hiệu lực + thời điểm password change + server rules |
| User phải đổi password không? | AD pwdLastSet; OpenLDAP ppolicy; 389 policy |
| Account đã hết hạn chưa? | account expiration riêng với password expiry |
| User có được tự đổi password không? | ACL/control access right và policy |
| Admin có được reset password không? | Reset-specific ACL/control access right |

### 15.2. Đọc đúng server và đúng DC

Trong AD, một số thuộc tính trạng thái có thể chịu ảnh hưởng replication/DC. Khi ứng dụng load-balance giữa nhiều DC, kết quả đọc từ một DC có thể chưa phản ánh ngay thao tác trên DC khác. Đối với thao tác nhạy cảm, hãy xác định write endpoint, replication expectations và nguồn đọc được phép.

Không gộp mọi trường hợp “không đọc thấy attribute” thành false. ACL có thể ẩn operational attribute; server version có thể không cung cấp field; hoặc adapter chưa hỗ trợ. Trạng thái **unknown** là kết quả hợp lệ hơn một phỏng đoán.

## 16. Kiểm thử password change và account policy

Không kiểm thử password lockout, password reset hoặc password history trên account production. Tạo **directory lab**, user fixture riêng, policy riêng và quyền bind tách biệt.

### 16.1. Ma trận test chung

| Test | Kịch bản | Kỳ vọng |
| --- | --- | --- |
| Password change hợp lệ | User gửi đúng old password và new password | Success |
| Old password sai | User gửi old password không đúng | Không đổi password |
| New password vi phạm policy | Quá ngắn/không đạt complexity/history | Server từ chối |
| Password reuse | Dùng lại một password trong history | Server từ chối nếu policy bật |
| Admin reset | Helpdesk có quyền reset | Success |
| User không có quyền reset người khác | Gọi API reset ngoài phạm vi | Application/LDAP từ chối |
| Kênh không mã hóa | Password operation thiếu confidentiality | Không cho thực hiện |
| Extension không hỗ trợ | Yêu cầu RFC3062 khi server không hỗ trợ | Adapter báo capability error |
| Must change | Admin reset và policy buộc đổi | Login flow yêu cầu đổi |
| Account disabled | Bind với user bị disable | Authentication bị từ chối |
| Lockout | Thử bind sai trong lab tới ngưỡng | Server lock theo policy |
| Unlock | Hết thời gian hoặc admin unlock | Bind được cho phép trở lại nếu các điều kiện khác hợp lệ |
| Multi-DC | Đổi password qua một DC rồi kiểm tra DC khác | Xác minh replication và thời gian hội tụ |

### 16.2. Kiểm thử RFC 3062

1. Đọc Root DSE và xác minh OID **1.3.6.1.4.1.4203.1.11.1**.
2. Dùng một test account và kết nối TLS đã xác minh.
3. Thực hiện change với old password đúng.
4. Xác nhận old password không còn bind được và new password bind được.
5. Thử old password sai; xác nhận server không thay password.
6. Thử password vi phạm policy; xác nhận result code/response control.
7. Kiểm tra password không xuất hiện trong logs/traces.

Không thử nhiều lần bằng password sai trên cùng user nếu lockout policy đang bật; mỗi lần sai có thể tăng bộ đếm và khóa test account.

### 16.3. Kiểm thử AD unicodePwd

Trong AD lab:

- Xác minh LDAPS/SASL encryption và certificate chain.
- Test user change bằng **DELETE old + ADD new** trong một ModifyRequest.
- Test admin reset bằng **REPLACE new** với delegated reset right.
- Xác minh không thể Search unicodePwd.
- Xác minh **pwdLastSet = 0** buộc đổi ở lần đăng nhập kế tiếp theo policy.
- Kiểm tra disable/enable bằng flag **ACCOUNTDISABLE** nhưng giữ nguyên các bit khác.
- Kiểm tra lockout bằng trạng thái computed và thời lượng lockout.

Không ghi trực tiếp các bit UAC bằng số cố định khi không giữ các flag hiện có.

### 16.4. Kiểm thử OpenLDAP ppolicy

Trong OpenLDAP lab:

- Xác nhận ppolicy schema/module/overlay đã được nạp.
- Kiểm tra policy mặc định và policy gắn riêng entry nếu có.
- Test minimum length, password history, expiration, grace authentication.
- Test lockout sau nhiều bind sai, sau đó unlock theo cấu hình.
- Kiểm tra Password Policy Response Control nếu client/server bật.
- Xác minh password được hash theo storage scheme dự kiến.

Nếu overlay chưa được bật, đừng mong các attribute tên pwd* tự thực thi policy.

### 16.5. Kiểm thử 389 Directory Server

Trong 389 DS lab:

- Đọc global/local password policy bằng công cụ quản trị đúng phiên bản.
- Test passwordRetryCount, retryCountResetTime và accountUnlockTime.
- Test **nsAccountLock** độc lập với lockout do bind thất bại.
- Kiểm tra password history, expiration, temporary password rules nếu bật.
- Kiểm tra account state sau khi policy được thay đổi.

## 17. Troubleshooting theo triệu chứng

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| RFC3062 trả unavailableCriticalExtension | Server không hỗ trợ Password Modify | Kiểm tra supportedExtension và chọn adapter phù hợp |
| RFC3062 trả confidentialityRequired | Kênh không đủ bảo vệ | Dùng LDAPS/StartTLS hoặc SASL encryption được hỗ trợ |
| User change trả invalidCredentials | Old password sai hoặc bind identity không hợp lệ | Kiểm tra session và old password, tránh retry nhiều lần |
| Admin reset trả insufficientAccessRights | Thiếu quyền reset password | Cấp delegated reset right đúng phạm vi |
| OpenLDAP từ chối password dù đủ độ dài | ppolicy quality/history/syntax | Kiểm tra policy hiệu lực và response control |
| OpenLDAP không khóa sau nhiều lần sai | ppolicy overlay chưa bật hoặc pwdLockout tắt | Kiểm tra overlay và policy config |
| AD từ chối unicodePwd | TLS, encoding, quote, change/reset operation hoặc quyền sai | Kiểm tra UTF-16, BER OCTET STRING, operation semantics và ACL |
| AD không trả unicodePwd trong Search | Hành vi được thiết kế như vậy | Không dùng Search để xác minh password |
| AD báo password expired | pwdLastSet/policy | Xác định force change và password age |
| AD báo account disabled | ACCOUNTDISABLE trong userAccountControl | Kiểm tra account lifecycle |
| AD account vẫn locked dù lockoutTime khác 0 | Lockout duration/computed state | Đánh giá trạng thái theo server và thời gian |
| 389 DS trả constraintViolation khi bind sai nhiều lần | Lockout policy có thể đang chặn | Xem passwordRetryCount/accountUnlockTime và policy |
| 389 DS không cho bind dù password đúng | nsAccountLock hoặc policy inactivation | Kiểm tra account state và quyền unlock |
| Spring Security không dùng RFC3062 | Cấu hình mặc định false | Chỉ bật nếu server hỗ trợ extension |
| LdapUserDetailsManager ghi sai password attribute trên AD | Adapter đang dùng generic userPassword path | Dùng chiến lược unicodePwd riêng |
| Test account bị khóa ngoài ý muốn | Test bind sai quá ngưỡng | Reset/unlock bằng admin procedure trong lab |
| App báo password đổi thành công nhưng user không đăng nhập được | Read replica chưa hội tụ, user bị disabled/locked hoặc bind path khác | Kiểm tra đúng DC/server, trạng thái và replication |

### 17.1. Ghi nhận lỗi an toàn

Không log password, Base64/BER payload, unicodePwd byte array, userPassword hash hoặc credential bind. Log **LDAP result code**, operation type, server family, trace ID và một mã lỗi nghiệp vụ đã chuẩn hóa. Nếu cần diagnostic message, giữ ở log nội bộ được kiểm soát và loại bỏ dữ liệu nhạy cảm.

## 18. Checklist trước khi triển khai

~~~text
[ ] Server family và phiên bản đã được xác định
[ ] Root DSE capability được kiểm tra (nếu dùng RFC3062)
[ ] Password change và admin reset là hai luồng riêng
[ ] TLS/SASL confidentiality và certificate validation đã bật
[ ] Bind identity có quyền tối thiểu đúng thao tác
[ ] Password policy hiệu lực đã được kiểm tra
[ ] Account disabled / locked / expired / must-change được phân biệt
[ ] Không map password vào repository entity/DTO
[ ] Không log secret hoặc protocol payload
[ ] Error mapping không tiết lộ thông tin nội bộ
[ ] Integration test chạy trên directory lab đúng loại server
[ ] Retry và lockout behavior đã được kiểm soát
[ ] Read/write DC và replication expectations đã được ghi rõ
~~~

## 19. Bài thực hành

Tạo một môi trường lab riêng. Nếu chỉ có một loại directory, hoàn thành phần tương ứng và ghi rõ các capability không có.

1. Dùng ldapsearch đọc Root DSE và tìm **supportedExtension**; ghi nhận server có hỗ trợ RFC 3062 không.
2. Tạo một user lab với bind identity riêng; thực hiện password change theo RFC 3062 nếu server hỗ trợ.
3. Tạo một password policy thử nghiệm: minimum length, history và lockout threshold.
4. Thử password không đạt policy; đọc result code và policy response nếu có.
5. Thử user change và admin reset; ghi lại khác biệt về identity/permission.
6. Với OpenLDAP, bật ppolicy overlay trong lab và đọc các operational attributes sau một số lần bind sai.
7. Với AD, dùng userAccountControl để đọc trạng thái disable; phân biệt pwdLastSet, lockoutTime và accountExpires.
8. Với AD, thực hiện user change và admin reset bằng unicodePwd trong LDAPS lab; không dùng production account.
9. Với 389 DS, quan sát passwordRetryCount/accountUnlockTime và nsAccountLock.
10. Viết một interface DirectoryPasswordService cùng adapter cho server đang có; không nhét logic vendor vào repository.
11. Viết integration test xác nhận password cũ bị từ chối, password mới được chấp nhận và password không lộ trong log.
12. Viết báo cáo ngắn nêu những thuộc tính trạng thái nào có thể đọc, thuộc tính nào computed/operational và quyền cần thiết để reset.

## 20. Câu hỏi ôn tập và ghi nhớ

### 20.1. Câu hỏi ôn tập

1. Khác nhau giữa **user password change** và **administrative password reset** là gì?
2. RFC 3062 dùng OID nào và client kiểm tra năng lực server qua Root DSE bằng cách nào?
3. Vì sao Password Modify Extended Operation phải chạy trên kênh có confidentiality protection?
4. Tại sao một server có thể dùng userPassword trong khi AD dùng unicodePwd?
5. Vì sao không thể Search unicodePwd để đọc password?
6. AD user change yêu cầu hai modification nào trong cùng ModifyRequest?
7. AD admin reset dùng thao tác nào và cần quyền gì?
8. userAccountControl là bitmask hay boolean? Vì sao không nên gán một giá trị cố định?
9. Phân biệt ACCOUNTDISABLE, lockoutTime, pwdLastSet và accountExpires.
10. OpenLDAP ppolicy overlay có phải một LDAP core feature được RFC chuẩn hóa hiện hành không?
11. pwdAccountLockedTime và passwordRetryCount có thể được dùng portable giữa mọi server không?
12. Khác nhau giữa OpenLDAP ppolicy và 389 DS password policy là gì?
13. Spring Security LdapUserDetailsManager có liên quan gì đến Spring Data LDAP repository?
14. Vì sao setUsePasswordModifyExtensionOperation chỉ nên bật sau khi xác minh server support?
15. Làm thế nào để ứng dụng biểu diễn trạng thái account khi server không cung cấp một thuộc tính?

### 20.2. Ghi nhớ

LDAP có cơ chế password change chung qua **RFC 3062**, nhưng server phải hỗ trợ và client phải kiểm tra **supportedExtension**. Operation không tự bảo vệ password; cần TLS/SASL confidentiality. **OpenLDAP** thường dùng **userPassword** và có thể áp dụng **ppolicy overlay**; **Active Directory** dùng quy tắc đặc biệt của **unicodePwd**, **userAccountControl**, **pwdLastSet**, **lockoutTime** và policy/PSO; **389 Directory Server** có password policy cùng các attribute như **passwordRetryCount**, **accountUnlockTime** và **nsAccountLock**.

**Đổi password, reset password, force change, lockout, disable và account expiration là các trạng thái/thao tác riêng.** Spring Data LDAP giúp truy cập entry; password management cần API/adapter đúng server. Không đọc hoặc log password, không sửa operational/computed attributes tùy tiện, không dùng một boolean enabled để gộp mọi trạng thái. Luôn kiểm tra capability, quyền, policy và integration test trên directory mục tiêu.

## Tài liệu tham khảo

- [RFC 3062 — LDAP Password Modify Extended Operation](https://www.rfc-editor.org/rfc/rfc3062.html): OID, request/response fields, supportedExtension và yêu cầu bảo mật.
- [RFC 4511 — LDAPv3 Protocol](https://www.rfc-editor.org/rfc/rfc4511.html): Bind, Modify, Extended Operation và LDAP result codes.
- [RFC 4513 — LDAP Authentication Methods and Security Mechanisms](https://www.rfc-editor.org/rfc/rfc4513.html): TLS, SASL và bảo vệ xác thực LDAP.
- [OpenLDAP 2.6 Administrator's Guide — Password Policies](https://www.openldap.org/doc/admin26/overlays.html#Password_Policies): ppolicy overlay, password quality, history, expiry, grace login và lockout.
- [389 Directory Server — Password Reset and Lockout](https://www.port389.org/docs/389ds/howto/howto-passwordreset.html): passwordRetryCount, retryCountResetTime và accountUnlockTime.
- [Red Hat Directory Server — Account Lockout Policy](https://docs.redhat.com/en/documentation/red_hat_directory_server/13/html/security_and_access_control/managing-access-control): account lockout và operational attributes.
- [Red Hat Directory Server — User Management and Authentication](https://docs.redhat.com/en/documentation/red_hat_directory_server/13/html/security_and_access_control/user-management-and-authentication): global password policy và account policy.
- [Microsoft — Change Windows Active Directory and LDS user password through LDAP](https://learn.microsoft.com/en-us/troubleshoot/windows-server/active-directory/change-windows-active-directory-user-password): unicodePwd, user change và administrative reset.
- [Microsoft MS-ADTS — unicodePwd](https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-adts/6e803168-f140-4d23-b2d3-c3a8ab5917d2): quy tắc UTF-16/BER, TLS/SASL và quyền change/reset.
- [Microsoft — UserAccountControl flags](https://learn.microsoft.com/en-us/troubleshoot/windows-server/active-directory/useraccountcontrol-manipulate-account-properties): bit flags và trạng thái account.
- [Microsoft — msDS-User-Account-Control-Computed](https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-adts/b80798ae-1f8c-4d30-9d80-a1f3281e96e2): cách AD DS tính cờ lockout và password expired.
- [Microsoft — pwdLastSet](https://learn.microsoft.com/en-us/windows/win32/adsi/user-must-change-password-at-next-logon): quy tắc yêu cầu đổi password ở lần logon kế tiếp.
- [Microsoft — Configure Fine-Grained Password Policies](https://learn.microsoft.com/en-us/windows-server/identity/ad-ds/get-started/adac/fine-grained-password-policies): PSO và policy áp dụng theo user/group.
- [Microsoft — User Account Control Bits](https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-adts/dd302fd1-0aa7-406b-ad91-2a6b35738557): định nghĩa các bit userAccountControl.
- [Spring Security — LdapUserDetailsManager API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/ldap/userdetails/LdapUserDetailsManager.html): changePassword và Password Modify Extension option.
- [Spring LDAP — LdapTemplate API](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/LdapTemplate.html): Modify và truy cập directory từ Java.
