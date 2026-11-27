# Đổi tên entry và thay đổi RDN trong Spring LDAP

## 1. Bài toán: đổi tên hiển thị hay đổi địa chỉ của entry?

Trong dịch vụ thư mục LDAP, mỗi **entry** được xác định bởi một **Distinguished Name (DN)**. DN cho biết vị trí của entry trong cây thư mục. Phần tên riêng của entry so với entry cha là **Relative Distinguished Name (RDN)**. Khi quản trị tài khoản, nhóm hoặc đơn vị tổ chức, lập trình viên thường gặp yêu cầu “đổi tên người dùng”, “đổi tên nhóm” hoặc “chuyển người dùng sang phòng ban khác”. Trước khi viết mã cần xác định thao tác nào thực sự được yêu cầu.

Ví dụ, entry sau thuộc vùng tên `dc=example,dc=org`:

```ldif
dn: uid=alice,ou=people,dc=example,dc=org
objectClass: inetOrgPerson
uid: alice
cn: Alice Nguyen
sn: Nguyen
mail: alice@example.org
```

Ở đây:

- **DN đầy đủ:** `uid=alice,ou=people,dc=example,dc=org`.
- **RDN hiện tại:** `uid=alice`, phân biệt entry này với các entry khác có chung cha `ou=people,dc=example,dc=org`.
- **DN của cha:** `ou=people,dc=example,dc=org`.
- **Thuộc tính `cn`:** `Alice Nguyen`, là giá trị dữ liệu; `cn` không phải thành phần RDN của entry trong ví dụ.

Nếu chỉ thay tên hiển thị `cn` thành `Alice Tran`, DN không đổi. Nếu đổi RDN từ `uid=alice` thành `uid=alice.tran`, DN **thay đổi** dù entry vẫn nằm dưới `ou=people`. Nếu chuyển entry sang `ou=alumni`, DN cũng thay đổi dù giữ nguyên RDN `uid=alice`.

| Yêu cầu | Thao tác phù hợp | DN có đổi? |
| --- | --- | --- |
| Đổi tên hiển thị `cn`, giữ nguyên `uid` dùng làm RDN | `modifyAttributes` | Không |
| Đổi `uid=alice` thành `uid=alice.tran` trong cùng OU | LDAP **Modify DN** (rename RDN) | Có |
| Chuyển `uid=alice` từ `ou=people` sang `ou=alumni` | LDAP **Modify DN** với cha mới (move) | Có |
| Đổi cả RDN và OU cha | LDAP **Modify DN** với RDN và cha mới | Có |
| Đổi `cn` khi chính RDN là `cn=Alice Nguyen` | Cần xem xét **rename RDN**, không chỉ sửa thuộc tính | Thường có |

**Ý chính:** thay đổi thuộc tính định danh trong entry và đổi vị trí/tên của entry trong cây LDAP là hai thao tác khác nhau. Đây là lý do Spring LDAP cung cấp `LdapTemplate.rename(...)` bên cạnh `modifyAttributes(...)`.

## 2. Cách hoạt động của LDAP Modify DN

Giao thức LDAP định nghĩa thao tác **Modify DN** để đổi RDN của một entry và, nếu máy chủ hỗ trợ, chuyển entry sang một cha mới. Các thành phần đáng chú ý của yêu cầu gồm:

| Thành phần | Vai trò | Ví dụ |
| --- | --- | --- |
| `entry` | DN cũ cần thay đổi | `uid=alice,ou=people,dc=example,dc=org` |
| `newrdn` | RDN mới của entry | `uid=alice.tran` |
| `deleteoldrdn` | Có xóa các giá trị RDN cũ khỏi thuộc tính tương ứng hay không | `1` (có) hoặc `0` (giữ lại khi hợp lệ) |
| `newSuperior` | DN của entry cha mới, nếu muốn chuyển vị trí | `ou=alumni,dc=example,dc=org` |

Thao tác này **khác** với LDAP Modify (sửa tập thuộc tính). Cú pháp LDIF cho một lần đổi RDN là:

```ldif
dn: uid=alice,ou=people,dc=example,dc=org
changetype: modrdn
newrdn: uid=alice.tran
deleteoldrdn: 1
```

Kết quả dự kiến khi thao tác được máy chủ chấp nhận:

```ldif
dn: uid=alice.tran,ou=people,dc=example,dc=org
uid: alice.tran
cn: Alice Nguyen
sn: Nguyen
mail: alice@example.org
```

Với `deleteoldrdn: 1`, máy chủ cố gắng loại giá trị đặt tên cũ (`alice`) khỏi thuộc tính `uid` và bảo đảm giá trị mới (`alice.tran`) có trong entry, theo các quy tắc schema và máy chủ. Với `deleteoldrdn: 0`, giá trị RDN cũ có thể được giữ như một giá trị bổ sung của thuộc tính, **nếu schema cho phép**. Không nên suy ra rằng mọi nhà cung cấp LDAP đều cho phép giữ hoặc xóa giá trị tùy ý, nhất là với thuộc tính đơn trị hoặc thuộc tính bắt buộc.

Để chuyển entry sau khi đã đổi RDN vào OU khác, LDIF có thêm `newsuperior`:

```ldif
dn: uid=alice.tran,ou=people,dc=example,dc=org
changetype: modrdn
newrdn: uid=alice.tran
deleteoldrdn: 1
newsuperior: ou=alumni,dc=example,dc=org
```

Sau thành công, DN sẽ là `uid=alice.tran,ou=alumni,dc=example,dc=org`. Ở ví dụ thứ hai, RDN không đổi, nhưng cha thay đổi. `newSuperior` phải là DN được máy chủ nhận diện và cần có quyền thao tác phù hợp. Một số máy chủ không hỗ trợ chuyển giữa các naming context hoặc hạn chế đổi tên entry có con.

### 2.1. RDN có thể gồm nhiều thành phần

Không phải mọi RDN chỉ có một cặp `thuộc tính=giá trị`. Một **RDN đa trị** có thể có dạng `cn=Alice+uid=alice`. Dấu `+` ở đây ghép nhiều *attribute-value assertions* trong cùng RDN; nó khác dấu phẩy `,` dùng phân tách các RDN của DN. Đổi RDN đa trị đòi hỏi bảo toàn đầy đủ các thành phần cần thiết và tuân thủ schema, không nên xử lý bằng thao tác cắt/nối chuỗi thủ công.

## 3. Đổi RDN bằng `LdapTemplate.rename(...)`

Trong Spring LDAP, phương thức `LdapTemplate.rename(oldDn, newDn)` biểu đạt việc **đổi DN của entry**. Các DN truyền vào template thường được hiểu tương đối so với base của `ContextSource`. `LdapTemplate` thực hiện lời gọi qua ngữ cảnh LDAP bên dưới và chuyển lỗi sang các ngoại lệ Spring LDAP phù hợp.

### 3.1. Cấu hình `ContextSource`

Ví dụ dưới đây dùng Spring LDAP trong ứng dụng Spring với mật khẩu bind lấy từ cấu hình môi trường. Endpoint `ldaps://` giả định máy chủ đã có chứng chỉ TLS hợp lệ và ứng dụng tin cậy chứng chỉ đó.

```java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.core.support.LdapContextSource;

@Configuration
class LdapConfiguration {

    @Bean
    LdapContextSource contextSource(
            @Value("${app.ldap.url}") String url,
            @Value("${app.ldap.base}") String base,
            @Value("${app.ldap.bind-dn}") String bindDn,
            @Value("${app.ldap.bind-password}") String password) {
        LdapContextSource source = new LdapContextSource();
        source.setUrl(url);
        source.setBase(base);
        source.setUserDn(bindDn);
        source.setPassword(password);
        return source;
    }

    @Bean
    LdapTemplate ldapTemplate(LdapContextSource source) {
        return new LdapTemplate(source);
    }
}
```

```yaml
# application.yml: dùng thông tin thử nghiệm, không ghi mật khẩu trực tiếp vào file
app:
  ldap:
    url: ${LDAP_URL:ldaps://ldap.example.org:636}
    base: dc=example,dc=org
    bind-dn: ${LDAP_BIND_DN}
    bind-password: ${LDAP_BIND_PASSWORD}
```

Tài khoản `bind-dn` phải có quyền đổi tên trong vùng dữ liệu cần thao tác. **Bind DN không phải base DN**, và việc đọc được entry không có nghĩa tài khoản được phép rename entry.

### 3.2. Dựng DN bằng `LdapNameBuilder` thay vì nối chuỗi

Đổi UID làm RDN trong cùng `ou=people`:

```java
import javax.naming.Name;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;
import org.springframework.stereotype.Service;

@Service
class DirectoryAccountService {
    private final LdapTemplate ldapTemplate;

    DirectoryAccountService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    void renameUid(String oldUid, String newUid) {
        Name oldDn = LdapNameBuilder.newInstance("ou=people")
                .add("uid", oldUid)
                .build();

        Name newDn = LdapNameBuilder.newInstance("ou=people")
                .add("uid", newUid)
                .build();

        ldapTemplate.rename(oldDn, newDn);
    }
}
```

Khi `app.ldap.base = dc=example,dc=org`, lời gọi `renameUid("alice", "alice.tran")` tương ứng với:

```text
DN cũ: uid=alice,ou=people,dc=example,dc=org
DN mới: uid=alice.tran,ou=people,dc=example,dc=org
```

`LdapNameBuilder` hỗ trợ tạo và escape cấu trúc DN đúng ngữ cảnh; chẳng hạn nếu RDN dựa trên `cn` có dấu phẩy, hãy truyền **giá trị thô** cho `.add("cn", rawName)` thay vì tự chèn dấu gạch chéo ngược vào một chuỗi DN.

Hàm trên giả định `oldUid`, `newUid` đã được ứng dụng kiểm tra theo quy tắc nghiệp vụ, chẳng hạn không rỗng và độ dài hợp lệ. Builder xử lý cú pháp DN, **không quyết định** UID nào được hệ thống cho phép, người gọi có quyền đổi tên hay tên mới có bị trùng không.

### 3.3. Phân biệt đổi RDN với sửa thuộc tính không tham gia DN

Trong entry có DN `uid=alice,...`, thay `cn` không cần rename:

```java
import javax.naming.Name;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;
import javax.naming.directory.BasicAttribute;
import org.springframework.ldap.support.LdapNameBuilder;

Name dn = LdapNameBuilder.newInstance("ou=people")
        .add("uid", "alice")
        .build();

ModificationItem[] changes = {
    new ModificationItem(
        DirContext.REPLACE_ATTRIBUTE,
        new BasicAttribute("cn", "Alice Tran")
    )
};
ldapTemplate.modifyAttributes(dn, changes);
```

Đoạn mã `modifyAttributes` giả sử được viết trong lớp đã có biến `ldapTemplate` cùng cấu hình ở trên. Khi thao tác thành công, entry vẫn giữ DN `uid=alice,ou=people,dc=example,dc=org`. Nếu RDN là `cn=Alice Nguyen`, chỉ thay `cn` bằng `modifyAttributes` có thể bị máy chủ từ chối hoặc làm trái ràng buộc giữa tên và dữ liệu. Trường hợp đó phải cân nhắc **Modify DN**.

### 3.4. `deleteOldRdn`: điều gì cần kiểm tra?

Ở cấp giao thức, Modify DN có cờ `deleteoldrdn`. API `LdapTemplate.rename(...)` giúp gọi thao tác đổi DN nhưng không có tham số `deleteOldRdn` ngay trên chữ ký `rename(oldDn, newDn)` ở ví dụ này. Cơ chế cấp thấp/JNDI và máy chủ quyết định cách yêu cầu được gửi, nên khi nghiệp vụ quan tâm việc giữ lại giá trị RDN cũ, cần kiểm tra phiên bản thư viện, cách cấu hình provider và trạng thái entry sau rename. Đừng suy luận từ DN mới rằng giá trị thuộc tính cũ chắc chắn đã bị xóa.

## 4. Chuyển entry sang nhánh khác (move)

Nếu muốn chuyển `uid=alice` từ OU `people` sang OU `alumni`, có thể dùng chính thao tác `rename` với DN mới có cha khác:

```java
Name oldDn = LdapNameBuilder.newInstance("ou=people")
        .add("uid", "alice")
        .build();

Name newDn = LdapNameBuilder.newInstance("ou=alumni")
        .add("uid", "alice")
        .build();

ldapTemplate.rename(oldDn, newDn);
```

Đoạn mã giả định `Name`, `LdapNameBuilder` và `ldapTemplate` đã được khai báo như các ví dụ trước. Dù API được gọi là `rename`, thay đổi này là **move** vì RDN không đổi nhưng đường dẫn đến entry thay đổi.

```text
Trước:
  dc=example,dc=org
    ├── ou=people
    │     └── uid=alice
    └── ou=alumni

Sau:
  dc=example,dc=org
    ├── ou=people
    └── ou=alumni
          └── uid=alice
```

Lưu ý các điều kiện:

- **Entry cha mới phải tồn tại.** Đổi DN không tự tạo `ou=alumni`.
- **Quyền và chính sách máy chủ phải cho phép.** Tài khoản có quyền sửa thuộc tính chưa chắc có quyền đổi DN hoặc chuyển entry giữa hai OU.
- **Phạm vi naming context có thể giới hạn move.** Đừng giả định có thể chuyển entry giữa hai domain/partition chỉ bằng `rename(...)`.
- **Entry có con có thể bị hạn chế.** Việc đổi DN của OU hay group container có thể kéo theo DN của toàn bộ cây con về mặt logic; hỗ trợ thao tác này tùy máy chủ, phiên bản và chính sách.
- **Không có bảo đảm tự sửa liên kết bên ngoài.** Các nhóm, cấu hình ứng dụng, cache hoặc hệ thống khác lưu DN dưới dạng chuỗi có thể cần cập nhật. Tính năng đồng bộ tham chiếu của từng máy chủ, nếu có, phải được xác minh riêng.

Trong thực tế, “chuyển phòng ban” nhiều khi chỉ là sửa thuộc tính như `department`, trong khi yêu cầu cấu trúc LDAP lại là chuyển entry giữa các OU. Cần thống nhất ý nghĩa nghiệp vụ trước khi chọn API.

## 5. Thử thao tác bằng LDIF và `ldapmodrdn`

Trước khi tích hợp vào ứng dụng Spring LDAP, có thể thử với máy chủ LDAP riêng cho phát triển. Dùng dữ liệu mẫu, tài khoản có quyền được cấp rõ ràng và kết nối TLS có xác thực chứng chỉ.

### 5.1. Đọc DN hiện có

```bash
ldapsearch -LLL -x \
  -H "ldaps://ldap.example.org:636" \
  -D "cn=directory-editor,ou=system,dc=example,dc=org" -W \
  -b "uid=alice,ou=people,dc=example,dc=org" -s base \
  "(objectClass=*)" dn uid cn
```

Các tham số `-b` và `-s base` yêu cầu đọc đúng entry tại DN đã xác định; `-W` yêu cầu nhập mật khẩu qua lời nhắc thay vì đặt vào lịch sử lệnh.

### 5.2. Đổi RDN, loại giá trị RDN cũ khi được phép

```bash
ldapmodrdn -x \
  -H "ldaps://ldap.example.org:636" \
  -D "cn=directory-editor,ou=system,dc=example,dc=org" -W \
  -r \
  "uid=alice,ou=people,dc=example,dc=org" \
  "uid=alice.tran"
```

Trong công cụ `ldapmodrdn` của OpenLDAP, `-r` yêu cầu xóa các giá trị RDN cũ theo thao tác đổi tên. Nếu không có `-r`, hành vi giữ lại giá trị cũ của công cụ cần được xét theo phiên bản và schema. Để tránh hiểu nhầm, luôn đọc lại cả DN và các thuộc tính dùng làm RDN sau thao tác.

### 5.3. Chuyển sang một OU khác

Ví dụ, sau bước đổi RDN, có thể thử chuyển sang `ou=alumni`:

```bash
ldapmodrdn -x \
  -H "ldaps://ldap.example.org:636" \
  -D "cn=directory-editor,ou=system,dc=example,dc=org" -W \
  -r -s "ou=alumni,dc=example,dc=org" \
  "uid=alice.tran,ou=people,dc=example,dc=org" \
  "uid=alice.tran"
```

Với `ldapmodrdn`, tùy chọn `-s` chỉ **new superior** (entry cha mới), khác với `-s base` hoặc `-s sub` của `ldapsearch` (search scope). Hai công cụ dùng `-s` với mục đích khác nhau. Máy chủ có thể từ chối move nếu cấu hình hoặc ACL không cho phép.

### 5.4. Kiểm tra hậu điều kiện

Sau khi đổi tên, hãy tra cứu **DN cũ** và **DN mới**, không chỉ tìm bằng UID. Nếu cờ giữ giá trị RDN cũ đang được sử dụng, một truy vấn filter như `(uid=alice)` vẫn có thể khớp với entry đã đổi DN, mặc dù DN `uid=alice,...` không còn tồn tại. Kiểm tra thêm các thuộc tính của entry và các tham chiếu DN từ những hệ thống có liên quan.

## 6. Xây dựng DN an toàn và hiểu rủi ro nghiệp vụ

### 6.1. Ký tự đặc biệt trong RDN

DN có cú pháp escape riêng theo LDAP. Các ký tự như dấu phẩy, dấu cộng, dấu bằng, dấu gạch chéo ngược hoặc khoảng trắng tại các vị trí nhạy cảm có thể làm thay đổi ý nghĩa của DN nếu nối chuỗi thủ công.

```java
Name renamedDn = LdapNameBuilder.newInstance("ou=people")
        .add("cn", "Nguyen, Alice")
        .build();
```

Builder nhận **giá trị** `Nguyen, Alice` và sinh DN với cách escape tương ứng cho RDN. Không nên viết `"cn=" + userInput + ",ou=people"`, cũng không tự dùng cơ chế escape của **LDAP filter** cho **DN**: đây là hai ngữ pháp khác nhau.

Nếu cần so sánh DN, nên parse thành kiểu `Name`/`LdapName` rồi dùng các phương thức so sánh theo quy tắc tên tương ứng, thay vì tự cắt chuỗi tại dấu phẩy. Ví dụ, dấu phẩy đã escape trong `cn=Nguyen\, Alice` là một phần giá trị RDN, không phải dấu phân cách sang entry cha.

### 6.2. Rename không phải đổi định danh nghiệp vụ trong mọi hệ thống

DN là tên vị trí của entry trong thư mục, nhưng nhiều ứng dụng còn dùng những thuộc tính khác làm khóa định danh, chẳng hạn `employeeNumber`, `entryUUID` (nếu máy chủ cung cấp), hoặc mã định danh riêng của hệ thống. Khi đổi `uid` làm RDN:

- DN chắc chắn được yêu cầu thay đổi; thuộc tính tham gia RDN phải tương thích schema.
- Các liên kết ứng dụng lưu **DN cũ** cần được rà soát; cơ chế tự cập nhật tham chiếu tùy máy chủ và loại dữ liệu.
- Quy ước đăng nhập có thể dùng `uid`, `userPrincipalName` hoặc thuộc tính khác tùy hạ tầng. Không suy ra đổi RDN tương đương đổi tên đăng nhập trong mọi máy chủ.
- Nếu hệ thống yêu cầu tên người dùng bất biến, cần thiết kế riêng quy trình đổi tên và cập nhật tích hợp; không được tự coi Modify DN là thay đổi an toàn về mặt nghiệp vụ.

### 6.3. Kiểm tra va chạm tên và lỗi thao tác

Một `newDn` đã tồn tại thường khiến máy chủ từ chối đổi tên. Kiểm tra trước bằng `lookup` có thể giúp phản hồi thân thiện, nhưng không loại bỏ **race condition**: một tiến trình khác có thể tạo entry mang DN đó sau lần kiểm tra. Vì vậy, vẫn cần xử lý ngoại lệ của chính thao tác `rename`.

| Kịch bản | Quan sát và hướng xử lý |
| --- | --- |
| DN cũ không tồn tại | Kiểm tra dữ liệu đầu vào và xem có người khác đã đổi tên/move trước đó không |
| DN mới đã tồn tại | Trả lỗi xung đột phù hợp; không ghi đè entry đích |
| Không đủ quyền | Xác định ACL tại entry cũ và cha mới; không nâng quyền bind một cách tùy tiện |
| Vi phạm schema hoặc naming rule | Kiểm tra thuộc tính được dùng trong RDN, kiểu giá trị, `objectClass` và ràng buộc máy chủ |
| Cha mới không tồn tại hoặc move không được hỗ trợ | Xác nhận cây thư mục và chính sách máy chủ; cân nhắc quy trình di chuyển được hỗ trợ |
| Timeout/mất kết nối giữa thao tác | Không đoán thao tác chắc chắn thất bại; đọc lại DN cũ và mới trước khi quyết định thử lại |

**Lưu ý về tính nhất quán:** `LdapTemplate.rename(...)` là một lời gọi LDAP, không tự tạo transaction bao trùm các cập nhật cơ sở dữ liệu ứng dụng, cache, nhóm và dịch vụ bên ngoài. Nếu cần một quy trình nhiều bước, hãy thiết kế cơ chế xác minh, ghi nhận trạng thái và khôi phục phù hợp; không tự động đảo ngược rename bằng cách gọi ngược trong mọi tình huống.

## 7. Kiểm thử rename và move trên thư mục thử nghiệm

Một bài kiểm thử tích hợp có ý nghĩa nên chạy trên một **LDAP test directory** có dữ liệu tách biệt, schema và ACL đủ gần môi trường mục tiêu. Đừng chạy ví dụ trực tiếp lên tài khoản thật.

Giả sử đã có entry thử nghiệm `uid=test-user,ou=people,dc=example,dc=org`, người thực hành có thể kiểm tra ba bước:

1. `lookup(oldDn)` xác nhận entry nguồn tồn tại; `lookup(newDn)` xác nhận đích chưa có entry.
2. Gọi `ldapTemplate.rename(oldDn, newDn)`.
3. `lookup(newDn)` đọc lại entry, đồng thời xác nhận `lookup(oldDn)` không còn trỏ tới entry cũ. Kiểm tra cả giá trị thuộc tính dùng làm RDN, vì nó phụ thuộc quy tắc `deleteOldRdn` thực tế.

Đoạn mã sau minh họa phần kiểm tra DN sau rename trong một lớp kiểm thử đã có `ldapTemplate` và dữ liệu thử nghiệm:

```java
import javax.naming.Name;
import org.springframework.ldap.NameNotFoundException;
import org.springframework.ldap.support.LdapNameBuilder;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;

Name oldDn = LdapNameBuilder.newInstance("ou=people")
        .add("uid", "test-user")
        .build();
Name newDn = LdapNameBuilder.newInstance("ou=people")
        .add("uid", "test-user-renamed")
        .build();

assertNotNull(ldapTemplate.lookup(oldDn));
ldapTemplate.rename(oldDn, newDn);
assertNotNull(ldapTemplate.lookup(newDn));
assertThrows(NameNotFoundException.class,
        () -> ldapTemplate.lookup(oldDn));
```

Trong bộ test thực tế, nên tạo và dọn riêng các entry dùng cho từng bài kiểm thử để test chạy lại được. Lớp ngoại lệ cụ thể do Spring LDAP ánh xạ cần được xác nhận theo phiên bản thư viện và hành vi của máy chủ kiểm thử; phép thử trên minh họa cách phân biệt DN nguồn/đích hơn là cam kết mọi máy chủ có cùng mã lỗi.

### Những tình huống nên bổ sung vào test

- RDN mới chứa dấu phẩy hoặc ký tự đặc biệt, dùng `LdapNameBuilder` và xác minh giá trị được giữ đúng.
- Rename sang DN đã tồn tại, bảo đảm entry đích không bị ghi đè.
- Move giữa hai OU trong cùng naming context với quyền hợp lệ, xác minh DN cũ và DN mới.
- Move khi cha mới không tồn tại, kiểm tra thông báo lỗi và tình trạng entry nguồn.
- Bind bằng tài khoản chỉ đọc, xác nhận rename bị từ chối bởi ACL và ứng dụng không tiết lộ thông tin nhạy cảm.
- Sự cố mạng/TLS sau khi phát lệnh, thực hiện truy vấn kiểm tra trạng thái trước khi thử lại.

## 8. Thực hành: chọn đúng API cho từng thay đổi

Một thư mục thử nghiệm chứa các entry:

```text
dc=example,dc=org
  ├── ou=people
  │     ├── uid=alice
  │     └── uid=bob
  ├── ou=alumni
  └── ou=groups
        └── cn=engineering
```

Hãy thực hiện các yêu cầu theo thứ tự dưới đây, với một tài khoản thử nghiệm có quyền tương ứng:

1. **Đổi tên hiển thị:** `cn` của Alice từ `Alice Nguyen` sang `Alice Tran` mà không đổi DN. Xác định vì sao `modifyAttributes` phù hợp.
2. **Đổi RDN:** `uid=alice` thành `uid=alice.tran` trong `ou=people`. Dựng DN cũ/mới bằng `LdapNameBuilder`, gọi `rename` và kiểm tra lại DN.
3. **Chuyển OU:** chuyển entry vừa đổi tên sang `ou=alumni` mà giữ RDN `uid=alice.tran`. Kiểm tra entry không còn ở DN cũ.
4. **Kiểm tra thuộc tính:** đọc lại `uid`, `cn`, `sn`, `mail` để xem thuộc tính nào thực sự thay đổi; không giả định quy tắc giữ giá trị RDN cũ.
5. **Kiểm tra lỗi:** thử đổi sang một DN đã tồn tại, rồi thử với tài khoản chỉ đọc. Phân biệt lỗi trùng DN với lỗi phân quyền.
6. **Kiểm tra truy cập an toàn:** dùng LDAPS/StartTLS với xác minh chứng chỉ, không ghi mật khẩu vào lệnh hay log; xác nhận base DN trong `ContextSource` đúng với đường dẫn tương đối truyền vào template.

**Câu hỏi tự kiểm tra:**

1. Vì sao cập nhật `cn` không làm thay đổi DN khi entry có RDN là `uid=alice`?
2. Vai trò của `newrdn`, `deleteoldrdn` và `newSuperior` trong một yêu cầu Modify DN là gì?
3. Khi dùng `ContextSource` có base `dc=example,dc=org`, nên truyền DN nào vào `LdapTemplate.rename(...)`?
4. Vì sao truy vấn `(uid=alice)` có thể vẫn trả về entry sau khi entry được đổi DN sang `uid=alice.tran`?
5. Nếu kết nối bị ngắt khi đang rename, vì sao phải đọc lại cả DN cũ và DN mới trước khi thử lại?

## 9. Ghi nhớ

Trong LDAP, **đổi thuộc tính**, **đổi RDN** và **chuyển entry sang cha mới** là những nhu cầu khác nhau. Thao tác Modify DN xử lý đổi tên/đổi vị trí trong cây; Spring LDAP biểu diễn thao tác này qua `LdapTemplate.rename(oldDn, newDn)` và hỗ trợ dựng DN có cấu trúc bằng `LdapNameBuilder`. Khi triển khai thật, cần làm rõ quy tắc `deleteOldRdn`, schema, ACL, base DN, tên có ký tự đặc biệt và các tham chiếu phụ thuộc DN. Sử dụng kết nối TLS có xác thực, xử lý ngoại lệ theo loại lỗi và kiểm thử các hậu điều kiện trên thư mục thử nghiệm giúp việc đổi tên entry an toàn và dễ kiểm soát hơn.
