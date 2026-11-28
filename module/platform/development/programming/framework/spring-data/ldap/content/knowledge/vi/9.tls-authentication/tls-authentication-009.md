# Thay đổi mật khẩu và các yêu cầu riêng của từng máy chủ

Một ứng dụng HR dùng Spring Data LDAP để lưu thông tin nhân viên. Người dùng muốn đổi mật khẩu từ giao diện web. Nhóm phát triển thử gọi `ldapTemplate.modifyAttributes(...)` để thay giá trị `userPassword`, nhưng Active Directory từ chối vì máy chủ dùng thuộc tính `unicodePwd` với định dạng riêng. Khi chuyển môi trường thử nghiệm sang OpenLDAP, cùng cách ghi lại thuộc tính mật khẩu lại không áp dụng chính sách băm và lịch sử mật khẩu như nhóm mong đợi.

LDAP định nghĩa nhiều cơ chế để thay đổi mật khẩu, nhưng **không phải mọi directory server đều lưu hoặc cập nhật mật khẩu theo cùng một cách**. RFC 3062 chuẩn hóa Password Modify Extended Operation; Active Directory dùng quy tắc đặc biệt cho `unicodePwd`; OpenLDAP có thể dùng Password Modify cùng Password Policy overlay. Các yêu cầu về TLS, quyền, mật khẩu cũ, độ dài, lịch sử và khóa tài khoản cũng phụ thuộc server.

Trong chương **TLS và xác thực** của module **SPRING_DATA_LDAP**, bài này hướng dẫn phân biệt đổi mật khẩu và đặt lại mật khẩu, chọn cơ chế theo directory server, tích hợp với Spring LDAP/JNDI, xử lý chính sách mật khẩu và kiểm thử an toàn. Mục tiêu là xây dựng thao tác thay đổi mật khẩu có kiểm soát, bảo vệ bí mật trên đường truyền và tôn trọng chính sách do máy chủ thực thi.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **user password change** và **administrator password reset**.
2. Giải thích RFC 3062 Password Modify Extended Operation và OID của nó.
3. Kiểm tra server có quảng bá Password Modify extension trong Root DSE hay không.
4. Hiểu cách Active Directory xử lý `unicodePwd`, quyền `User-Change-Password` và `User-Force-Change-Password`.
5. Mã hóa giá trị `unicodePwd` đúng dạng UTF-16LE có dấu ngoặc kép và truyền qua LDAP Modify.
6. Hiểu OpenLDAP Password Policy overlay (`ppolicy`) và các thuộc tính chính sách thường dùng.
7. Chọn API Spring LDAP phù hợp, tránh cập nhật mật khẩu qua thao tác lưu entity thông thường.
8. Phân loại lỗi password policy, quyền, TLS và trạng thái kết nối.
9. Thiết kế kiểm thử theo từng loại server và bảo vệ mật khẩu khỏi log, trace, dump và retry không an toàn.

## 2. Đổi mật khẩu và đặt lại mật khẩu là hai thao tác khác nhau

Hai thao tác có mục đích và quyền khác nhau:

| Thao tác | Ai thực hiện? | Thông tin cần có | Quyền phía directory |
| --- | --- | --- | --- |
| **Đổi mật khẩu của chính mình** | Người dùng đã xác thực. | Mật khẩu hiện tại và mật khẩu mới, theo policy server. | Người dùng được phép đổi mật khẩu của chính mình. |
| **Đặt lại mật khẩu** | Helpdesk/admin hoặc quy trình provisioning được ủy quyền. | DN tài khoản đích và mật khẩu mới; thường không cần mật khẩu cũ. | Bind identity cần quyền reset/force-change password trên đối tượng đích. |

Không dùng một endpoint duy nhất rồi suy luận quyền chỉ từ việc client gửi hay không gửi mật khẩu cũ. Tầng service cần phân biệt rõ:

- `changeOwnPassword`: caller đã xác thực lại gần đây, cung cấp mật khẩu hiện tại, chỉ đổi tài khoản của chính caller.
- `adminResetPassword`: caller có quyền quản trị cụ thể, có lý do/audit, chỉ reset tài khoản trong phạm vi được cấp.

Một service account LDAP có quyền đọc danh bạ không mặc nhiên có quyền đổi mật khẩu. Cấp quyền reset cho service account cần được xem như một đặc quyền nhạy cảm và giới hạn theo OU/nhóm tài khoản.

### 2.1. Vì sao không nên cập nhật password như một attribute thông thường?

Mật khẩu có thể được lưu:

- Trong attribute như `userPassword`.
- Trong một attribute đặc biệt như `unicodePwd`.
- Bên ngoài directory hoặc qua một authentication provider.
- Theo dạng hash do server quản lý và thay đổi theo policy.

Nếu ứng dụng tự băm rồi ghi `userPassword`, server có thể băm lần nữa hoặc không nhận dạng được thuật toán. Nếu ứng dụng cố đọc password attribute để so sánh, directory thường không cho đọc hoặc chỉ trả dữ liệu đã mã hóa/hash. Password operation chuyên biệt giúp server áp dụng thuật toán lưu trữ, lịch sử và chính sách của chính nó.

Vì vậy, **không đưa mật khẩu vào entity ODM rồi gọi `repository.save(entity)` như cập nhật hồ sơ thông thường**. Hãy gọi operation chuyên biệt của server qua một service có quyền và policy rõ ràng.

## 3. Cơ chế chuẩn: RFC 3062 Password Modify Extended Operation

RFC 3062 định nghĩa LDAPv3 Extended Operation có OID:

~~~text
1.3.6.1.4.1.4203.1.11.1
~~~

Request value có cấu trúc:

~~~text
PasswdModifyRequestValue ::= SEQUENCE {
  userIdentity    [0] OCTET STRING OPTIONAL,
  oldPasswd       [1] OCTET STRING OPTIONAL,
  newPasswd       [2] OCTET STRING OPTIONAL
}
~~~

Ý nghĩa:

- `userIdentity`: người dùng cần đổi mật khẩu; có thể là DN hoặc identity mà server hiểu. Nếu bỏ trống, operation áp dụng cho user hiện gắn với LDAP session.
- `oldPasswd`: mật khẩu hiện tại; nếu được gửi và sai, server không được đổi mật khẩu.
- `newPasswd`: mật khẩu mới. Nếu bỏ trống, server có thể tạo mật khẩu và trả về trong response.

Response có thể chứa `genPasswd` nếu server tạo mật khẩu mới. Client phải kiểm tra result code; chỉ coi thao tác thành công khi server trả `success`.

### 3.1. Kiểm tra server có hỗ trợ extension

RFC 3062 khuyến nghị server công bố OID trong attribute `supportedExtension` của Root DSE. Client nên kiểm tra trước khi gửi operation.

Ví dụ dùng `ldapsearch`:

~~~bash
ldapsearch \
  -H ldaps://ldap01.corp.example:636 \
  -x \
  -D "cn=app-reader,ou=services,dc=corp,dc=example" \
  -W \
  -b "" \
  -s base \
  supportedExtension
~~~

Nếu kết quả có:

~~~text
supportedExtension: 1.3.6.1.4.1.4203.1.11.1
~~~

thì server đang quảng bá Password Modify Extended Operation. Server có thể chỉ quảng bá extension khi caller đã được xác thực hoặc đã thiết lập mức bảo vệ cần thiết. Không thấy OID có nghĩa là client không nên tự giả định operation được hỗ trợ.

### 3.2. Yêu cầu bảo mật của RFC 3062

RFC 3062 nói rõ operation không tự cung cấp tính bí mật hoặc toàn vẹn cho password. Vì vậy:

- Không gọi operation này qua kết nối LDAP plaintext.
- Dùng TLS (LDAPS hoặc StartTLS đã thiết lập thành công) hoặc cơ chế bảo vệ SASL đủ mạnh theo policy.
- Không gọi operation anonymous.
- Xác minh certificate chain và hostname của server.
- Không đưa mật khẩu vào URL, filter, DN, log hoặc query string.

RFC 3062 cho phép server từ chối operation nếu không có bảo vệ đủ mạnh. Đây là hành vi bảo mật đúng, không phải lỗi cần khắc phục bằng cách tắt TLS.

### 3.3. Khi nào dùng RFC 3062?

RFC 3062 phù hợp khi directory server hỗ trợ extension và muốn server tự quản lý cách lưu mật khẩu. Nó không phụ thuộc password phải nằm trong một attribute cụ thể như `userPassword`.

Trước khi dùng:

1. Đọc Root DSE và xác minh OID `1.3.6.1.4.1.4203.1.11.1`.
2. Thiết lập TLS/SASL confidentiality.
3. Bind bằng danh tính phù hợp với use case.
4. Gửi `userIdentity`, `oldPasswd`, `newPasswd` đúng theo chính sách change/reset của server.
5. Kiểm tra result code và response.
6. Nếu server tạo password, chỉ chuyển password đó qua kênh an toàn tới người nhận được ủy quyền; không ghi log.

## 4. Active Directory: `unicodePwd` có quy tắc riêng

Active Directory Domain Services (AD DS) và Active Directory Lightweight Directory Services (AD LDS) sử dụng attribute `unicodePwd` cho password của user hoặc `inetOrgPerson`. Đây là attribute đặc biệt:

- Không thể đọc bằng LDAP search.
- Chỉ được sửa trong những điều kiện giới hạn.
- Cần kết nối được bảo vệ bằng TLS/SSL hoặc SASL encryption theo yêu cầu của server.
- Không dùng trực tiếp định dạng UTF-8 thông thường.

### 4.1. Yêu cầu kết nối được mã hóa

Microsoft quy định việc sửa `unicodePwd` cần một kết nối có bảo vệ mật mã đủ mạnh. Tài liệu Active Directory mô tả yêu cầu TLS/SSL 128-bit hoặc mạnh hơn; Windows Server 2003 trở lên cũng cho phép kết nối được bảo vệ bằng SASL-layer encryption đủ mạnh.

Trong ứng dụng Spring Boot:

- Ưu tiên `ldaps://dc01.corp.example:636` với certificate hợp lệ.
- Có thể dùng StartTLS nếu domain controller và cấu hình triển khai hỗ trợ, nhưng phải xác minh StartTLS hoàn tất trước khi bind/gửi password.
- Không tắt hostname verification hoặc chấp nhận mọi certificate.
- Không tự động fallback sang LDAP plaintext khi TLS lỗi.

Ví dụ cấu hình endpoint:

~~~yaml
spring:
  ldap:
    urls:
      - ldaps://dc01.corp.example:636
    base: dc=corp,dc=example
    username: ${LDAP_BIND_DN}
    password: ${LDAP_BIND_PASSWORD}
~~~

Certificate của domain controller phải có SAN khớp hostname trong URL và CA phải được truststore của JVM tin cậy. Kiểm tra từ đúng container/JVM chạy ứng dụng, không chỉ từ máy cá nhân.

### 4.2. Mã hóa giá trị `unicodePwd`

Giá trị gửi tới `unicodePwd` phải là:

1. Password được bao quanh bởi dấu ngoặc kép `"` (dấu ngoặc không thuộc password thực).
2. Chuỗi Unicode được mã hóa UTF-16LE.
3. Được gửi dưới dạng LDAP octet string; LDAP provider sẽ BER-encode giá trị attribute trên wire.

Ví dụ password mới `new`:

~~~text
Chuỗi có dấu ngoặc: "new"
UTF-16LE bytes:
22 00 6E 00 65 00 77 00 22 00
~~~

Không tự thêm một lớp BER OCTET STRING vào `byte[]` khi dùng JNDI. JNDI LDAP provider đã mã hóa giá trị attribute thành BER OCTET STRING theo giao thức LDAP. Ứng dụng cung cấp bytes UTF-16LE có dấu ngoặc đúng định dạng.

### 4.3. Đổi mật khẩu của chính mình trên Active Directory

Để đổi password, LDAP Modify request phải chứa **hai modification theo đúng thứ tự**:

1. `DELETE unicodePwd` với mật khẩu hiện tại.
2. `ADD unicodePwd` với mật khẩu mới.

Hai modification được gửi trong cùng một LDAP Modify operation:

~~~java
import java.nio.ByteBuffer;
import java.nio.CharBuffer;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;
import org.springframework.ldap.core.LdapTemplate;

public final class ActiveDirectoryPasswordService {

    private final LdapTemplate ldapTemplate;

    public ActiveDirectoryPasswordService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public void changeOwnPassword(
            String userDnRelativeToBase,
            char[] currentPassword,
            char[] newPassword) {

        byte[] oldValue = null;
        byte[] newValue = null;
        try {
            oldValue = encodeUnicodePwd(currentPassword);
            newValue = encodeUnicodePwd(newPassword);
            ModificationItem[] changes = {
                    new ModificationItem(
                            DirContext.REMOVE_ATTRIBUTE,
                            new BasicAttribute("unicodePwd", oldValue)),
                    new ModificationItem(
                            DirContext.ADD_ATTRIBUTE,
                            new BasicAttribute("unicodePwd", newValue))
            };

            // Một LDAP Modify request với DELETE trước, ADD sau.
            ldapTemplate.modifyAttributes(userDnRelativeToBase, changes);
        } finally {
            if (oldValue != null) Arrays.fill(oldValue, (byte) 0);
            if (newValue != null) Arrays.fill(newValue, (byte) 0);
            Arrays.fill(currentPassword, '\0');
            Arrays.fill(newPassword, '\0');
        }
    }

    private static byte[] encodeUnicodePwd(char[] password) {
        CharBuffer quoted = CharBuffer.allocate(password.length + 2);
        quoted.put('"');
        quoted.put(password);
        quoted.put('"');
        quoted.flip();

        ByteBuffer encoded = StandardCharsets.UTF_16LE.encode(quoted);
        byte[] value = new byte[encoded.remaining()];
        encoded.get(value);

        // Xóa các buffer tạm có thể truy cập được sau khi sao chép.
        Arrays.fill(quoted.array(), '\0');
        if (encoded.hasArray()) {
            Arrays.fill(encoded.array(), (byte) 0);
        }
        return value;
    }
}
~~~

Ví dụ giả định `userDnRelativeToBase` đã được xác định từ danh tính đã xác thực, không nhận DN tùy ý từ request body. `LdapTemplate.modifyAttributes(...)` sử dụng context read-write và gửi các modification theo thứ tự trong cùng một request.

Với Spring LDAP `ContextSource` có cấu hình base DN, tên truyền vào `modifyAttributes` phải tương đối với base đó. Nếu ứng dụng đang giữ full DN, hãy chuyển đổi sang relative DN theo cấu trúc `LdapName`; không ghép chuỗi hoặc truyền một full DN rồi giả định context source tự nhận ra. Ngoài ra, `LdapTemplate` dùng bind identity của `ContextSource`: self-service flow phải dùng context được xác thực như user (hoặc một cơ chế server-specific đã được xác minh), không mặc định dùng service account chung có quyền admin. `currentPassword` và `newPassword` bị xóa ngay trong method; caller không được dùng lại hai mảng đó.

`char[]` và `byte[]` giúp ứng dụng chủ động xóa các buffer do mình tạo sau khi thao tác hoàn tất. JVM/provider có thể tạo bản sao nội bộ; không thể bảo đảm xóa mọi bản sao khỏi heap. Không log giá trị, không bật wire trace chứa payload và không ghi request object ra debug log.

### 4.4. Đặt lại mật khẩu bởi quản trị viên trên Active Directory

Reset password không cần gửi mật khẩu cũ. LDAP Modify request phải chứa **một modification `REPLACE unicodePwd`** với mật khẩu mới:

~~~java
public void resetPassword(
        String targetUserDnRelativeToBase,
        char[] newPassword) {

    // Đặt method này trong cùng ActiveDirectoryPasswordService
    // để dùng helper encodeUnicodePwd ở mục 4.3.
    byte[] newValue = null;
    try {
        newValue = encodeUnicodePwd(newPassword);
        ModificationItem[] reset = {
                new ModificationItem(
                        DirContext.REPLACE_ATTRIBUTE,
                        new BasicAttribute("unicodePwd", newValue))
        };

        // Context phải bind bằng admin/service identity được cấp quyền reset.
        ldapTemplate.modifyAttributes(targetUserDnRelativeToBase, reset);
    } finally {
        if (newValue != null) Arrays.fill(newValue, (byte) 0);
        Arrays.fill(newPassword, '\0');
    }
}
~~~

Đoạn code dùng lại helper `encodeUnicodePwd` ở mục trước. Không gọi phương thức reset này từ endpoint self-service change.

### 4.5. Quyền Active Directory cần có

Active Directory phân biệt quyền:

| Hoạt động | Điều kiện quyền |
| --- | --- |
| Người dùng đổi password của chính mình | Đối tượng phải có control access right `User-Change-Password` trên chính nó và giá trị delete phải khớp password hiện tại. |
| Quản trị viên reset password | Bind identity phải có control access right `User-Force-Change-Password` trên user/inetOrgPerson cần reset. |

Nếu người dùng bị ACL từ chối quyền tự đổi password, thao tác có thể thất bại dù password cũ chính xác. Nếu admin reset thất bại, kiểm tra quyền trên đúng đối tượng và OU; không nâng service account thành Domain Admin chỉ để bỏ qua lỗi.

### 4.6. Các lỗi `unicodePwd` thường gặp

| Triệu chứng / mã lỗi | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| `protocolError` / decoding error | Giá trị không đúng dạng octet string hoặc payload sai encoding. | Xác minh byte UTF-16LE và việc dùng `byte[]` với JNDI. |
| `constraintViolation` / password not in quotes | Thiếu dấu ngoặc kép quanh password trước khi mã hóa. | Bao password bằng U+0022 trước khi UTF-16LE encode. |
| `unwillingToPerform` | Kết nối không đủ bảo vệ, policy server từ chối hoặc thao tác không phù hợp. | Kiểm tra TLS/SASL encryption, policy và quyền. |
| `insufficientAccessRights` | Thiếu `User-Change-Password` hoặc `User-Force-Change-Password`. | Kiểm tra ACL/control access right trên user object. |
| `invalidCredentials` | Password cũ không đúng hoặc bind credential sai. | Xác minh danh tính đã bind và password cũ qua quy trình an toàn. |
| `constraintViolation` khác | Password không đạt length/history/complexity/filter. | Kiểm tra password policy áp dụng cho domain/user. |

Mã LDAP có thể đi kèm diagnostic message hoặc Windows extended error. Nội dung chi tiết phụ thuộc server/version; phân loại bằng result code và diagnostic được bảo vệ, không trả nguyên văn cho caller.

## 5. OpenLDAP: Password Modify và Password Policy overlay

OpenLDAP có thể dùng attribute `userPassword` và Password Policy overlay (`ppolicy`). Overlay cung cấp chính sách như độ dài tối thiểu, tuổi mật khẩu, lịch sử, khóa tài khoản và bắt đổi password ở lần đăng nhập tiếp theo.

### 5.1. Dùng RFC 3062 để server tự xử lý password

OpenLDAP hỗ trợ Password Modify Extended Operation. Operation nhận password dạng cleartext qua kết nối được bảo vệ và để server áp dụng cấu hình `password-hash` trước khi lưu vào `userPassword`.

Đây là cách tránh việc client phải biết server đang dùng `{SSHA}`, `{PBKDF2}`, `{ARGON2}` hay thuật toán hash nào khác. Client không nên tự băm password rồi ghi vào directory vì có thể không tương thích với cấu hình server.

Ví dụ cấu hình server có thể khai báo:

~~~text
password-hash {SSHA}
~~~

Đây chỉ minh họa cú pháp directive, không phải khuyến nghị chọn SSHA cho hệ thống mới. Thuật toán hash thực tế phải theo policy bảo mật của tổ chức và khả năng phiên bản OpenLDAP đang triển khai.

### 5.2. Password Policy overlay (`ppolicy`)

OpenLDAP `slapo-ppolicy` có thể thực thi các quy tắc như:

| Thuộc tính policy | Ý nghĩa |
| --- | --- |
| `pwdAllowUserChange` | Có cho phép user tự đổi password không. |
| `pwdAttribute` | Attribute mật khẩu được policy quản lý; OpenLDAP ppolicy chấp nhận `userPassword`. |
| `pwdCheckQuality` | Mức kiểm tra chất lượng password; có thể từ chối khi server không kiểm tra được định dạng. |
| `pwdMinLength` | Độ dài tối thiểu. |
| `pwdInHistory` | Số password cũ không được tái sử dụng. |
| `pwdMinAge` | Khoảng thời gian tối thiểu giữa các lần đổi. |
| `pwdMaxAge` | Thời hạn password. |
| `pwdLockout` | Có khóa tài khoản sau nhiều lần bind thất bại hay không. |
| `pwdMaxFailure` | Số lần xác thực thất bại trước khi khóa. |
| `pwdLockoutDuration` | Thời gian khóa. |
| `pwdMustChange` | Có buộc đổi password sau một số tình huống reset/expiry không. |
| `pwdSafeModify` | Có yêu cầu cung cấp password cũ khi đổi không. |

Ví dụ policy entry:

~~~ldif
dn: cn=default,ou=policies,dc=example,dc=com
objectClass: top
objectClass: namedPolicy
objectClass: pwdPolicy
cn: default
pwdAttribute: userPassword
pwdAllowUserChange: TRUE
pwdCheckQuality: 2
pwdMinLength: 12
pwdInHistory: 5
pwdMinAge: 0
pwdMaxAge: 0
pwdLockout: TRUE
pwdMaxFailure: 5
pwdLockoutDuration: 900
pwdMustChange: TRUE
pwdSafeModify: TRUE
~~~

Đây là cấu hình minh họa, không phải khuyến nghị giá trị áp dụng cho mọi tổ chức. `pwdPolicy` và password policy response control bắt nguồn từ một đặc tả Internet-Draft đã hết hạn nhưng được nhiều directory server triển khai; hành vi chi tiết phải kiểm tra theo OpenLDAP version và server thực tế.

Trong ví dụ, `pwdCheckQuality: 2` yêu cầu server kiểm tra cú pháp password; nếu server không thể kiểm tra (chẳng hạn client gửi giá trị đã hash/encode sẵn), server từ chối. Các giá trị và chi tiết còn lại cần đối chiếu `slapo-ppolicy(5)` của đúng phiên bản đang chạy.

Policy có thể áp dụng mặc định qua `ppolicy_default` hoặc riêng từng entry qua `pwdPolicySubentry`. Do đó hai user trong cùng directory có thể chịu chính sách khác nhau.

### 5.3. `ppolicy_hash_cleartext`

OpenLDAP có tùy chọn `ppolicy_hash_cleartext` trong Password Policy overlay. Khi bật, overlay có thể bắt LDAP Modify trên `userPassword` dạng cleartext và chuyển xử lý qua cơ chế Password Modify để hash theo `password-hash` server.

Ví dụ:

~~~text
database mdb
suffix "dc=example,dc=com"

overlay ppolicy
ppolicy_default "cn=default,ou=policies,dc=example,dc=com"
ppolicy_hash_cleartext
~~~

Không giả định `ppolicy_hash_cleartext` đã bật chỉ vì server có overlay. Hãy xác minh cấu hình `slapd` và test với một tài khoản fixture. Dù server hash ở phía nào, password cleartext vẫn phải được bảo vệ trên đường truyền bằng TLS/SASL confidentiality.

### 5.4. Không nhầm OpenLDAP policy với chuẩn LDAP chung

Các thuộc tính `pwdMinLength`, `pwdInHistory`, `pwdSafeModify` và các hành vi của overlay là phần triển khai password policy cụ thể. Không được giả định Active Directory hiểu các attribute này hoặc một server LDAP khác sẽ có cùng hành vi.

RFC 3062 chuẩn hóa **operation**; nó không chuẩn hóa toàn bộ chính sách mật khẩu của từng sản phẩm. Password policy và các response control có thể khác nhau giữa OpenLDAP, Active Directory, 389 Directory Server, Oracle Directory Server và các sản phẩm khác.

## 6. So sánh cơ chế theo từng directory server

| Server / môi trường | Cơ chế cần xem xét | Điểm đặc thù |
| --- | --- | --- |
| Active Directory DS / LDS | LDAP Modify trên `unicodePwd`. | UTF-16LE có dấu ngoặc kép; LDAP octet string; TLS/SASL encryption; change dùng delete + add; reset dùng replace; quyền control access riêng. |
| OpenLDAP | RFC 3062 Password Modify Extended Operation. | Server tự hash theo `password-hash`; `ppolicy` áp dụng chính sách; `ppolicy_hash_cleartext` có thể xử lý LDAP Modify trên `userPassword`. |
| Server hỗ trợ RFC 3062 khác | Password Modify Extended Operation. | Kiểm tra `supportedExtension`, cách xác định userIdentity, yêu cầu old password và policy. |
| Server không hỗ trợ RFC 3062 | API/attribute/extension riêng của sản phẩm. | Không tự suy ra từ `userPassword`; đọc tài liệu server và kiểm thử trên môi trường tương ứng. |

### 6.1. Ma trận quyết định

~~~mermaid
flowchart TD
    A["Ứng dụng cần đổi/reset password"] --> B["Xác định directory server và phiên bản"]
    B --> C{"Active Directory DS/LDS?"}
    C -- "Có" --> D["Dùng unicodePwd theo quy tắc AD"]
    C -- "Không" --> E{"Root DSE quảng bá RFC 3062 OID?"}
    E -- "Có" --> F["Dùng Password Modify Extended Operation"]
    E -- "Không" --> G["Tra cứu cơ chế riêng của server"]
    D --> H["Xác minh TLS/SASL, quyền và password policy"]
    F --> H
    G --> H
    H --> I["Kiểm thử change và reset trên directory test"]
~~~

Không chọn cơ chế dựa trên tên attribute nhìn thấy trong một search. Hãy xác định loại server, version, extension support, policy và quyền trước khi triển khai.

## 7. Tích hợp với Spring LDAP

Spring Data LDAP repository rất hữu ích cho CRUD entry, nhưng thay đổi mật khẩu là một thao tác bảo mật riêng. Dùng `LdapTemplate` cho LDAP Modify chuyên biệt hoặc dùng một LDAP SDK hỗ trợ RFC 3062 cho Extended Operation.

### 7.1. `LdapTemplate.modifyAttributes` cho Active Directory

Với AD, ví dụ ở mục 4 dùng:

~~~java
ldapTemplate.modifyAttributes(userDn, modificationItems);
~~~

Spring LDAP cung cấp context read-write và xử lý lifecycle của context. Các `ModificationItem` phải giữ đúng thứ tự và đúng operation:

- User change: `REMOVE_ATTRIBUTE` cũ rồi `ADD_ATTRIBUTE` mới.
- Admin reset: một `REPLACE_ATTRIBUTE` với giá trị mới.

Không dùng `REPLACE_ATTRIBUTE` cho self-service change nếu cần server xác minh password cũ.

### 7.2. `executeReadWrite` cho thao tác JNDI đặc biệt

`LdapTemplate.executeReadWrite(ContextExecutor)` cho phép gọi thao tác trên `DirContext` khi Spring LDAP không có method chuyên biệt. Đây là điểm mở rộng để dùng `LdapContext.extendedOperation(...)` nếu ứng dụng tự triển khai một `javax.naming.ldap.ExtendedRequest` đúng chuẩn:

~~~java
import javax.naming.ldap.ExtendedResponse;
import javax.naming.ldap.LdapContext;
import org.springframework.ldap.core.LdapTemplate;

public ExtendedResponse executePasswordOperation(
        LdapTemplate ldapTemplate,
        javax.naming.ldap.ExtendedRequest request) {

    return ldapTemplate.executeReadWrite(context -> {
        if (!(context instanceof LdapContext ldapContext)) {
            throw new IllegalStateException(
                    "LDAP provider does not expose LdapContext");
        }
        return ldapContext.extendedOperation(request);
    });
}
~~~

Đoạn này minh họa cách Spring LDAP chuyển một JNDI ExtendedRequest xuống provider; nó **không tự tạo** Password Modify request. Lớp request phải mã hóa đúng ASN.1/BER theo RFC 3062 và được kiểm thử độc lập. Không tự viết BER encoder trong ứng dụng nghiệp vụ nếu có thư viện đã được kiểm chứng.

### 7.3. Dùng UnboundID LDAP SDK cho RFC 3062

Một lựa chọn là dùng UnboundID LDAP SDK, thư viện có `PasswordModifyExtendedRequest` và `PasswordModifyExtendedResult`:

~~~kotlin
dependencies {
    implementation("com.unboundid:unboundid-ldapsdk:<approved-version>")
}
~~~

Ví dụ service nhận một connection đã được thiết lập TLS và bind đúng identity:

~~~java
import com.unboundid.ldap.sdk.LDAPConnection;
import com.unboundid.ldap.sdk.ResultCode;
import com.unboundid.ldap.sdk.extensions.PasswordModifyExtendedRequest;
import com.unboundid.ldap.sdk.extensions.PasswordModifyExtendedResult;

public void changeWithRfc3062(
        LDAPConnection tlsBoundConnection,
        String userDn,
        String oldPassword,
        String newPassword) throws Exception {

    PasswordModifyExtendedRequest request =
            new PasswordModifyExtendedRequest(
                    userDn,
                    oldPassword,
                    newPassword);

    PasswordModifyExtendedResult result =
            (PasswordModifyExtendedResult)
                    tlsBoundConnection.processExtendedOperation(request);

    if (!ResultCode.SUCCESS.equals(result.getResultCode())) {
        // PasswordChangeException là exception nghiệp vụ do ứng dụng định nghĩa.
        throw new PasswordChangeException(
                result.getResultCode().toString());
    }
}
~~~

`tlsBoundConnection` là connection do ứng dụng quản lý; nó phải dùng TLS đã xác minh và bind bằng danh tính phù hợp. Không tạo connection plaintext chỉ để chạy password operation. Nếu dùng `newPassword = null` để yêu cầu server tạo mật khẩu, đọc `getGeneratedPassword()` từ response và chuyển nó qua kênh an toàn tới đúng người nhận; không log hoặc lưu vào telemetry.

Ví dụ dùng `String` để dễ đọc. Trong ứng dụng thật, hạn chế thời gian sống của object chứa password, không lưu password vào field lâu dài và ưu tiên API hỗ trợ `byte[]`/`char[]` khi có thể. SDK có thể giữ bản sao dữ liệu trong request object đến khi object được thu gom; không giả định có thể xóa mọi bản sao.

### 7.4. Không trộn lẫn hai giao thức

Đừng gửi UTF-16LE `unicodePwd` bytes vào RFC 3062 `newPasswd`, hoặc gửi RFC 3062 password string vào attribute `unicodePwd`.

| Cơ chế | Password representation |
| --- | --- |
| AD `unicodePwd` | UTF-16LE, bao quanh bằng dấu ngoặc kép, truyền như octet string trong LDAP Modify. |
| RFC 3062 | OCTET STRING trong request value; encoding password theo quy ước của server/SDK, thường dùng UTF-8 cho chuỗi password. |
| OpenLDAP `userPassword` Modify với `ppolicy_hash_cleartext` | Cleartext value được server overlay xử lý/hash; vẫn phải dùng TLS/SASL confidentiality. |

## 8. Kiến trúc service an toàn

Tách API và service theo mục đích:

~~~text
POST /me/password
  -> xác thực lại caller
  -> lấy DN từ security principal đã xác thực
  -> changeOwnPassword(oldPassword, newPassword)

POST /admin/users/{id}/password-reset
  -> kiểm tra quyền admin/helpdesk
  -> resolve user ID sang DN trong phạm vi được cấp
  -> ghi audit reason
  -> adminResetPassword(newPassword)
~~~

### 8.1. Không nhận DN tùy ý từ người dùng

Với self-service endpoint, không nhận `userDn` từ request body. Nếu client gửi DN của người khác, lỗi authorization có thể biến thành thao tác đổi mật khẩu trái phép.

Lấy DN từ danh tính đã xác thực hoặc tra cứu bằng immutable identifier đã được ràng buộc với caller. Với admin reset, resolve target qua service có authorization và tenant/OU boundary.

### 8.2. Xác thực lại trước khi đổi mật khẩu

Một phiên đăng nhập cũ không đủ để chứng minh người dùng hiện biết password hiện tại. Tùy policy, yêu cầu:

- Re-authentication gần thời điểm đổi password.
- Current password được gửi tới password operation nếu server hỗ trợ.
- MFA/step-up authentication nếu tổ chức yêu cầu.
- CSRF protection và rate limit cho endpoint.
- Giới hạn số lần thử password cũ để tránh brute force/lockout.

Không tự kiểm tra password bằng cách bind liên tục nếu server đã có operation kiểm tra old password; các bind lặp có thể kích hoạt lockout policy.

### 8.3. Không lưu hoặc ghi log password

Không ghi các giá trị sau vào log, metric label, trace attribute, exception message, audit record hoặc analytics:

- Mật khẩu cũ/mới.
- `unicodePwd` bytes hoặc payload RFC 3062.
- Request/response object có chứa password.
- Nội dung HTTP body của endpoint đổi mật khẩu.

Audit chỉ nên ghi: caller ID đã được bảo vệ, target ID, loại thao tác (`SELF_CHANGE`/`ADMIN_RESET`), thời điểm, directory alias, result category, correlation ID và admin reason theo policy.

### 8.4. Xử lý timeout và trạng thái không chắc chắn

Nếu kết nối bị ngắt sau khi gửi password operation nhưng trước khi nhận response, client không biết chắc server đã commit hay chưa. **Không retry mù quáng**:

1. Đánh dấu outcome `UNKNOWN` thay vì ghi thất bại chắc chắn.
2. Không ghi lại password vào durable queue để thử lại sau.
3. Dùng quy trình xác minh có kiểm soát, ví dụ xác thực một lần với password mới nếu policy cho phép.
4. Nếu không thể xác minh, yêu cầu người dùng thực hiện lại theo flow an toàn hoặc chuyển admin support.
5. Theo dõi lockout counter và không tự động lặp nhiều lần.

Password change không phải thao tác idempotent trong mọi server/policy. Password history, minimum age và old-password verification có thể khiến lần retry sau cho kết quả khác lần đầu.

### 8.5. Sau khi đổi mật khẩu

Khi server xác nhận thành công:

- Yêu cầu người dùng đăng nhập lại nếu session policy cần.
- Thu hồi hoặc làm mới session/token theo kiến trúc identity.
- Xóa cache xác thực cũ nếu ứng dụng có cache.
- Cập nhật trạng thái yêu cầu reset/force-change nếu nghiệp vụ sử dụng.
- Không tự ghi một password hash vào LDAP hoặc database nội bộ để đồng bộ.

## 9. Chính sách mật khẩu do server thực thi

Client có thể kiểm tra UX trước khi gửi, nhưng **server mới là nguồn quyết định cuối cùng**. Policy có thể khác theo domain, OU, user policy subentry, password filter hoặc phiên bản server.

Những quy tắc thường gặp:

| Chính sách | Câu hỏi |
| --- | --- |
| Minimum length | Mật khẩu mới có đủ độ dài tối thiểu không? |
| Complexity / quality | Server yêu cầu đặc tính nào? Có custom password filter không? |
| Password history | Có được dùng lại password gần đây không? |
| Minimum age | User đã được phép đổi lại chưa? |
| Maximum age | Password hiện tại có hết hạn không? |
| Lockout | Tài khoản có bị khóa do thử sai nhiều lần không? |
| Force change | Sau reset có bắt user đổi ở lần đăng nhập tiếp theo không? |
| Self-service allowed | User có quyền đổi password của chính mình không? |
| Admin reset | Caller có quyền reset đối tượng đích không? |

Không hard-code một policy chung trong Java rồi coi việc vượt qua validation client là đủ. Hãy hiển thị thông báo phù hợp nhưng không tiết lộ password cũ, policy nội bộ nhạy cảm hoặc diagnostic chi tiết.

## 10. Phân loại lỗi và phản hồi cho người dùng

| LDAP result / dấu hiệu | Nguyên nhân có thể | Xử lý ở service |
| --- | --- | --- |
| `invalidCredentials` (49) | Bind credential sai hoặc old password không đúng. | Thông báo thông tin hiện tại không hợp lệ; rate limit và theo dõi lockout. |
| `insufficientAccessRights` (50) | Caller/bind identity thiếu quyền change/reset. | Ghi audit và báo không đủ quyền; không tự nâng quyền. |
| `constraintViolation` (19) | Password vi phạm length/history/complexity hoặc định dạng `unicodePwd`. | Phân loại theo server diagnostic đã làm sạch; hướng dẫn user chọn password khác. |
| `unwillingToPerform` (53) | Server từ chối theo policy, thao tác sai hoặc bảo vệ kết nối chưa đạt. | Kiểm tra TLS, server policy và operation shape. |
| `confidentialityRequired` (13) | Server yêu cầu bảo vệ confidentiality. | Thiết lập TLS/SASL encryption; không fallback plaintext. |
| `unavailableCriticalExtension` (12) | Server không hỗ trợ extension/control bắt buộc. | Kiểm tra `supportedExtension`/control support và chọn cơ chế tương thích. |
| `noSuchObject` (32) | DN đích không tồn tại hoặc sai base. | Kiểm tra target resolution; tránh tiết lộ user existence cho caller trái quyền. |
| `busy` (51), `unavailable` (52) | Server đang bận hoặc không sẵn sàng. | Retry có giới hạn chỉ khi outcome rõ; timeout sau gửi request phải đánh dấu UNKNOWN. |
| `timeLimitExceeded` / timeout | Kết nối hoặc server phản hồi quá chậm. | Không tự gửi lại password operation mù quáng. |

Mã LDAP có thể không đủ để phân biệt mọi lỗi password policy. Active Directory có thể gửi Windows-specific extended error; OpenLDAP ppolicy có thể trả password policy response control. Hãy kiểm tra server logs/diagnostics trong môi trường bảo vệ, không đưa nguyên diagnostic vào HTTP response.

## 11. Kiểm thử theo từng loại directory server

Kiểm thử password operation cần directory thật hoặc test container phù hợp. Mock `LdapTemplate` chỉ xác nhận service gọi đúng method, không chứng minh server chấp nhận encoding, ACL hoặc policy.

### 11.1. Bộ test cơ bản

| Test | Thiết lập | Kết quả mong đợi |
| --- | --- | --- |
| Self change đúng password cũ | User bind hợp lệ, old password đúng, new password hợp policy. | Server trả success; password mới dùng được. |
| Self change sai password cũ | Old password sai. | Server từ chối; password không đổi. |
| Admin reset | Admin có quyền reset, target tồn tại. | Server trả success; password mới dùng được. |
| Thiếu quyền reset | Bind identity không có quyền. | Access denied; không đổi password. |
| TLS không hợp lệ | CA không tin cậy hoặc hostname mismatch. | Handshake thất bại trước password operation. |
| Password quá ngắn | New password vi phạm policy. | Server từ chối theo policy; password cũ vẫn hoạt động. |
| Password trong history | New password trùng lịch sử. | Server từ chối nếu policy bật history. |
| Minimum age | User đổi quá sớm. | Server từ chối theo policy. |
| Tài khoản bị khóa | User đang lockout. | Server từ chối theo trạng thái/policy. |
| Password mới thành công | Xác thực bằng password mới. | Bind mới thành công. |
| Password cũ sau đổi | Xác thực bằng password cũ. | Bind thất bại (trừ cơ chế đặc biệt đã cấu hình). |
| Timeout sau request | Ngắt kết nối trước response. | Service ghi outcome UNKNOWN, không retry mù quáng. |

### 11.2. Test riêng cho Active Directory

- Xác minh endpoint LDAPS/StartTLS và certificate DC.
- Self change gửi đúng thứ tự `DELETE unicodePwd` rồi `ADD unicodePwd`.
- Reset gửi một `REPLACE unicodePwd`.
- Kiểm tra UTF-16LE có dấu ngoặc kép bằng test bytes, không in password.
- Kiểm tra quyền `User-Change-Password` và `User-Force-Change-Password`.
- Kiểm tra lỗi password history, minimum age, complexity và password filter.
- Xác nhận `unicodePwd` không được đọc bằng search.
- Kiểm tra trên AD DS/AD LDS và version thực tế nếu hệ thống hỗ trợ cả hai.

### 11.3. Test riêng cho OpenLDAP

- Xác minh Root DSE quảng bá RFC 3062 OID.
- Kiểm tra Password Modify với old password đúng/sai.
- Kiểm tra `pwdSafeModify`, `pwdAllowUserChange` và ACL.
- Kiểm tra `pwdMinLength`, `pwdInHistory`, `pwdMinAge`, `pwdMaxAge`, `pwdLockout`.
- Xác minh server hash theo `password-hash` và client không tự băm.
- Kiểm tra `ppolicy_hash_cleartext` nếu ứng dụng dùng LDAP Modify trên `userPassword`.
- Kiểm tra per-user `pwdPolicySubentry` khác default policy.

### 11.4. Ma trận tương thích

Mỗi môi trường triển khai nên có bảng đã xác minh:

| Server/version | TLS mode | Password mechanism | Change | Reset | Policy response | Status |
| --- | --- | --- | --- | --- | --- | --- |
| AD DS version đang dùng | LDAPS/StartTLS đã kiểm thử | `unicodePwd` | DELETE + ADD | REPLACE | AD diagnostic/policy | Chờ kiểm thử môi trường |
| AD LDS version đang dùng | TLS/SASL theo cấu hình | `unicodePwd` | DELETE + ADD | REPLACE | Theo cấu hình LDS | Chờ kiểm thử môi trường |
| OpenLDAP version đang dùng | LDAPS/StartTLS | RFC 3062 | OID 1.3.6.1.4.1.4203.1.11.1 | Theo quyền/policy | ppolicy response/control nếu cấu hình | Chờ kiểm thử môi trường |
| Directory khác | Theo tài liệu vendor | Kiểm tra Root DSE/vendor API | Theo vendor | Theo vendor | Theo vendor | Chưa xác minh |

Không đánh dấu một cơ chế là tương thích chỉ vì server chấp nhận bind/search. Password operation có thể có yêu cầu riêng về TLS, rights, control và encoding.

## 12. Checklist trước khi phát hành

- [ ] Đã phân biệt self-service change và admin reset thành hai use case.
- [ ] DN target được resolve từ danh tính/authorization phía server, không nhận tùy ý từ client.
- [ ] Đã xác định directory server, phiên bản và cơ chế password operation.
- [ ] RFC 3062 OID được kiểm tra trong Root DSE nếu dùng extended operation.
- [ ] Active Directory `unicodePwd` dùng đúng UTF-16LE quoted bytes và đúng thứ tự modification.
- [ ] OpenLDAP ppolicy và `password-hash` đã được kiểm tra trên server thực tế.
- [ ] Kết nối dùng TLS/SASL confidentiality, certificate và hostname được xác minh.
- [ ] Service account có quyền tối thiểu; quyền reset được cấp riêng.
- [ ] Password không xuất hiện trong log, trace, metric, URL hoặc audit payload.
- [ ] Request timeout không dẫn tới retry mù quáng.
- [ ] Có test cho old password sai, policy violation, access denied và TLS failure.
- [ ] Session/token/cache cũ được xử lý sau khi password thay đổi.
- [ ] Có quy trình vận hành cho outcome UNKNOWN và account lockout.

## 13. Bài tập tình huống

Một công ty triển khai ứng dụng Spring Boot dùng Spring Data LDAP. Ở môi trường phát triển, directory là OpenLDAP; môi trường production dùng Active Directory. Nhóm đã viết:

~~~java
ldapTemplate.modifyAttributes(
        userDn,
        new ModificationItem[] {
            new ModificationItem(
                DirContext.REPLACE_ATTRIBUTE,
                new BasicAttribute("userPassword", newPassword))
        });
~~~

Trên production, password update bị từ chối. Nhóm thử chuyển sang `unicodePwd` nhưng dùng UTF-8 và chỉ một `REPLACE` cho self-service change. Sau khi sửa một phần, request đôi khi timeout và service tự động retry.

**Yêu cầu:**

1. Vì sao không thể giả định `userPassword` là attribute password chung cho mọi server?
2. Với OpenLDAP, RFC 3062 giúp server xử lý hashing như thế nào?
3. OID của Password Modify Extended Operation là gì và kiểm tra support ở đâu?
4. Vì sao RFC 3062 không nên dùng trên kết nối plaintext hoặc anonymous?
5. Active Directory yêu cầu encoding `unicodePwd` ra sao?
6. Self-service change trên AD cần những modification nào và theo thứ tự nào?
7. Admin reset trên AD dùng operation nào và quyền nào?
8. Vì sao `REPLACE unicodePwd` không phù hợp với self-service change cần xác minh password cũ?
9. OpenLDAP `pwdSafeModify`, `pwdInHistory` và `pwdCheckQuality` tác động ra sao?
10. Vì sao client-side hash password trước khi gửi có thể làm server không xác thực được?
11. Khi timeout sau khi gửi request, tại sao service phải đánh dấu outcome UNKNOWN?
12. Hãy đề xuất integration test tối thiểu cho cả OpenLDAP và Active Directory.

**Gợi ý đáp án:**

- `userPassword`, `unicodePwd` và password backend có thể khác nhau theo server; không có một LDAP Modify chung cho mọi directory.
- RFC 3062 gửi password cleartext trong extended operation qua kết nối bảo vệ, để server tự áp dụng password-hash và policy.
- OID `1.3.6.1.4.1.4203.1.11.1`, kiểm tra `supportedExtension` ở Root DSE.
- RFC 3062 không tự bảo vệ confidentiality/integrity và không cho anonymous operation.
- AD cần password có dấu ngoặc kép, mã hóa UTF-16LE và truyền như LDAP octet string.
- Self change: DELETE old password rồi ADD new password trong một Modify request.
- Admin reset: một REPLACE new password; bind identity cần `User-Force-Change-Password`.
- Self change cần kiểm tra old password; AD yêu cầu `User-Change-Password` và delete value phải khớp password hiện tại.
- OpenLDAP ppolicy có thể yêu cầu old password, kiểm tra history/quality và từ chối password không đạt policy.
- Client hash sai thuật toán hoặc hash lần hai; server không thể xác thực theo password-hash đã cấu hình.
- Timeout không chứng minh server chưa commit; retry có thể vi phạm history/minimum-age hoặc gây trạng thái không rõ.
- Test TLS, old password đúng/sai, admin rights, policy violations, password mới/cũ, Root DSE extension và timeout handling.

## 14. Ghi nhớ

**Thay đổi mật khẩu LDAP phải theo cơ chế mà directory server hỗ trợ.** RFC 3062 cung cấp Password Modify Extended Operation để server quản lý password storage/policy. Active Directory dùng `unicodePwd` với giá trị UTF-16LE có dấu ngoặc kép, kết nối được bảo vệ và hai luồng khác nhau: self change là DELETE old + ADD new; admin reset là REPLACE new với quyền `User-Force-Change-Password`. OpenLDAP có thể dùng RFC 3062 cùng Password Policy overlay để kiểm tra chất lượng, lịch sử, tuổi và khóa tài khoản.

Trong Spring Data LDAP, hãy triển khai password operation thành service chuyên biệt, dùng `LdapTemplate` cho LDAP Modify phù hợp hoặc LDAP SDK hỗ trợ Extended Operation. Xác minh TLS, Root DSE extension, ACL và policy theo server/version. Không lưu password trong entity, không log payload, không tự hash khi server phải quản lý hashing và không retry mù quáng khi kết quả timeout chưa xác định.

### Tài liệu tham khảo

- [RFC 3062 — LDAP Password Modify Extended Operation](https://www.rfc-editor.org/rfc/rfc3062.html)
- [Microsoft Open Specifications — `unicodePwd`](https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-adts/6e803168-f140-4d23-b2d3-c3a8ab5917d2)
- [Microsoft Learn — Change Windows Active Directory and LDS User Password Through LDAP](https://learn.microsoft.com/en-us/troubleshoot/windows-server/active-directory/change-windows-active-directory-user-password)
- [Microsoft Open Specifications — General Password Policy](https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-samr/bbee5135-3db2-4824-873a-55104c3610ad)
- [OpenLDAP Administrator's Guide — Password Policies](https://www.openldap.org/doc/admin26/overlays.html)
- [Spring LDAP API — LdapTemplate](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/LdapTemplate.html)
- [Spring LDAP Reference — Adding Missing Overloaded API Methods](https://docs.spring.io/spring-ldap/reference/adding-missing-overloaded-api-methods.html)
- [Java SE — LdapContext Extended Operations](https://docs.oracle.com/en/java/javase/21/docs/api/java.naming/javax/naming/ldap/LdapContext.html)
- [UnboundID LDAP SDK — PasswordModifyExtendedRequest](https://docs.ldap.com/ldap-sdk/docs/javadoc/com/unboundid/ldap/sdk/extensions/PasswordModifyExtendedRequest.html)
