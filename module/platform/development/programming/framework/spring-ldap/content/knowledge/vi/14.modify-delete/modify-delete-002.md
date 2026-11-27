# ADD_ATTRIBUTE, REPLACE_ATTRIBUTE và REMOVE_ATTRIBUTE trong Spring LDAP

Khi cập nhật một entry LDAP, ứng dụng thường chỉ cần thêm, thay hoặc xóa một vài **giá trị thuộc tính**. Chẳng hạn, nhân viên được bổ sung địa chỉ email, đổi số điện thoại hoặc gỡ một email không còn sử dụng. Trong Spring LDAP, ta có thể mô tả chính xác các thay đổi đó bằng `ModificationItem`, rồi gửi đến máy chủ thông qua `LdapTemplate.modifyAttributes(...)`.

Ba phép sửa đổi được định nghĩa trong JNDI, thuộc `javax.naming.directory.DirContext`:

- **`ADD_ATTRIBUTE`**: thêm giá trị vào thuộc tính, giữ những giá trị hợp lệ đã tồn tại.
- **`REPLACE_ATTRIBUTE`**: thay **toàn bộ tập giá trị** của thuộc tính bằng tập giá trị mới.
- **`REMOVE_ATTRIBUTE`**: xóa một hay nhiều giá trị được chỉ định, hoặc xóa cả thuộc tính.

Điểm then chốt là **sửa thuộc tính khác với xóa hay tạo lại entry**. Các lệnh này tác động đến entry ở một DN xác định; chúng không tự đổi DN, không tự di chuyển entry và không tương đương `unbind`/`rebind`.

## 1. Thuộc tính LDAP có thể có nhiều giá trị

Giả sử thư mục có entry:

~~~ldif
dn: uid=an,ou=people,dc=example,dc=org
objectClass: inetOrgPerson
cn: An Nguyen
sn: Nguyen
uid: an
mail: an.work@example.org
mail: an.personal@example.org
telephoneNumber: +84-28-1111
description: Khoi tao tu he thong nhan su
~~~

Thuộc tính `mail` chứa **hai giá trị**. Nếu muốn bổ sung `an.alt@example.org`, ứng dụng cần bảo toàn hai email cũ. Nếu muốn cập nhật số điện thoại chính và bỏ số cũ, ứng dụng phải thay tập giá trị `telephoneNumber`. Nếu muốn xóa riêng email cá nhân, ứng dụng phải chỉ định đúng giá trị cần xóa.

LDAP lưu các giá trị của một thuộc tính như một tập hợp: **không dựa vào thứ tự giá trị** để quyết định đâu là email chính, điện thoại mặc định, v.v. Ngoài ra, schema quyết định một thuộc tính có thể chứa nhiều giá trị hay chỉ một giá trị, cú pháp hợp lệ và thuộc tính nào là bắt buộc.

## 2. So sánh ba phép sửa đổi

| Phép | Khi thuộc tính đã tồn tại | Khi thuộc tính chưa tồn tại | Lưu ý |
| --- | --- | --- | --- |
| `ADD_ATTRIBUTE` | Thêm giá trị mới, giữ giá trị cũ | Tạo thuộc tính với giá trị được cung cấp, nếu schema cho phép | Giá trị trùng hoặc thêm vào thuộc tính chỉ cho phép một giá trị có thể bị từ chối |
| `REPLACE_ATTRIBUTE` | Bỏ toàn bộ giá trị cũ và dùng tập giá trị mới | Tạo thuộc tính với tập giá trị mới, nếu hợp lệ | Rất dễ làm mất các giá trị cũ nếu chỉ truyền một giá trị |
| `REMOVE_ATTRIBUTE` | Xóa giá trị được nêu; nếu không nêu giá trị thì xóa cả thuộc tính | Có thể bị từ chối hoặc được bỏ qua tùy nhà cung cấp/máy chủ | Không thể xóa thuộc tính bắt buộc nếu vi phạm schema |

### 2.1. ADD_ATTRIBUTE: bổ sung

~~~java
ModificationItem addEmail = new ModificationItem(
    DirContext.ADD_ATTRIBUTE,
    new BasicAttribute("mail", "an.alt@example.org")
);
~~~

Với entry ví dụ, `mail` sau khi áp dụng thành công sẽ gồm ba giá trị:

~~~text
an.work@example.org
an.personal@example.org
an.alt@example.org
~~~

Lệnh **không thay thế** hai email có trước. Nếu `an.alt@example.org` đã tồn tại, máy chủ LDAP có thể trả lỗi tương ứng với giá trị đã có (chẳng hạn `attributeOrValueExists`). Vì vậy, không được mặc định rằng gọi `ADD_ATTRIBUTE` nhiều lần với cùng dữ liệu luôn an toàn.

### 2.2. REPLACE_ATTRIBUTE: thay toàn bộ tập giá trị

~~~java
ModificationItem replacePhone = new ModificationItem(
    DirContext.REPLACE_ATTRIBUTE,
    new BasicAttribute("telephoneNumber", "+84-28-2222")
);
~~~

Sau khi áp dụng, `telephoneNumber` chỉ còn `+84-28-2222`. Nếu thuộc tính trước đó có ba số điện thoại thì **cả ba số cũ đều bị thay**, không riêng số đầu tiên.

Để thay một thuộc tính đa trị bằng nhiều giá trị mới, tạo `BasicAttribute` rồi thêm lần lượt từng giá trị:

~~~java
Attribute newMails = new BasicAttribute("mail");
newMails.add("an.team@example.org");
newMails.add("an.contact@example.org");

ModificationItem replaceMails = new ModificationItem(
    DirContext.REPLACE_ATTRIBUTE,
    newMails
);
~~~

Kết quả là `mail` chỉ còn hai email vừa đưa vào. `REPLACE_ATTRIBUTE` cũng có thể tạo thuộc tính chưa tồn tại, miễn là schema và quyền ghi cho phép.

Theo hợp đồng JNDI, `REPLACE_ATTRIBUTE` với **không có giá trị** sẽ xóa các giá trị hiện tại. Tuy nhiên, khi mục đích là xóa thuộc tính, nên dùng `REMOVE_ATTRIBUTE` để người đọc mã hiểu đúng ý định; đừng vô tình truyền tập rỗng khi ứng dụng thực sự muốn giữ dữ liệu.

### 2.3. REMOVE_ATTRIBUTE: xóa một giá trị hoặc cả thuộc tính

Xóa **một email** nhưng giữ email còn lại:

~~~java
ModificationItem removeOneEmail = new ModificationItem(
    DirContext.REMOVE_ATTRIBUTE,
    new BasicAttribute("mail", "an.personal@example.org")
);
~~~

Sau thao tác này, `an.work@example.org` vẫn có mặt (và `an.alt@example.org` cũng vẫn còn nếu đã được thêm thành công). Để **xóa toàn bộ thuộc tính** `description`, truyền một `BasicAttribute` chỉ có tên, không có giá trị:

~~~java
ModificationItem removeDescription = new ModificationItem(
    DirContext.REMOVE_ATTRIBUTE,
    new BasicAttribute("description")
);
~~~

Phân biệt rõ:

- `new BasicAttribute("mail", "an.personal@example.org")`: chỉ định **giá trị phải xóa**.
- `new BasicAttribute("description")`: chỉ định **toàn bộ thuộc tính phải xóa**.

Khi giá trị cần xóa không tồn tại, hợp đồng JNDI cho phép nhà cung cấp bỏ qua sự vắng mặt hoặc báo lỗi. Với LDAP server, cũng cần xét schema và quy tắc kiểm tra dữ liệu. Vì vậy, không nên xây dựng nghiệp vụ với giả định mọi thao tác REMOVE đều idempotent.

## 3. Gửi thay đổi bằng LdapTemplate

`LdapTemplate` cung cấp phương thức:

~~~java
void modifyAttributes(Name dn, ModificationItem[] mods);
~~~

Ở đây, `dn` xác định entry, còn mảng `mods` chứa từng phép thêm/thay/xóa cần thực hiện. Ví dụ service dưới đây giả định `ContextSource` của Spring LDAP đã được cấu hình với **base DN** `dc=example,dc=org`. Vì vậy, DN truyền cho `LdapTemplate` là **DN tương đối** `uid=an,ou=people`; không lặp lại phần base.

~~~java
import java.util.Collection;
import javax.naming.Name;
import javax.naming.directory.Attribute;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;

import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;
import org.springframework.stereotype.Service;

@Service
public class UserDirectoryService {

    private final LdapTemplate ldapTemplate;

    public UserDirectoryService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    // Giữ lại mọi email cũ, bổ sung một email mới.
    public void addEmail(String uid, String email) {
        ModificationItem change = new ModificationItem(
            DirContext.ADD_ATTRIBUTE,
            new BasicAttribute("mail", requireText("email", email))
        );
        ldapTemplate.modifyAttributes(userDn(uid), new ModificationItem[] {change});
    }

    // Thay toàn bộ các số điện thoại bằng tập giá trị mới.
    public void replacePhoneNumbers(String uid, Collection<String> numbers) {
        if (numbers == null || numbers.isEmpty()) {
            throw new IllegalArgumentException("numbers phải có ít nhất một giá trị");
        }

        Attribute replacement = new BasicAttribute("telephoneNumber");
        for (String number : numbers) {
            replacement.add(requireText("telephoneNumber", number));
        }

        ModificationItem change = new ModificationItem(
            DirContext.REPLACE_ATTRIBUTE,
            replacement
        );
        ldapTemplate.modifyAttributes(userDn(uid), new ModificationItem[] {change});
    }

    // Xóa đúng email được chỉ định.
    public void removeEmail(String uid, String email) {
        ModificationItem change = new ModificationItem(
            DirContext.REMOVE_ATTRIBUTE,
            new BasicAttribute("mail", requireText("email", email))
        );
        ldapTemplate.modifyAttributes(userDn(uid), new ModificationItem[] {change});
    }

    // Xóa toàn bộ thuộc tính tùy chọn description.
    public void removeDescription(String uid) {
        ModificationItem change = new ModificationItem(
            DirContext.REMOVE_ATTRIBUTE,
            new BasicAttribute("description")
        );
        ldapTemplate.modifyAttributes(userDn(uid), new ModificationItem[] {change});
    }

    private Name userDn(String uid) {
        return LdapNameBuilder.newInstance()
            .add("ou", "people")
            .add("uid", requireText("uid", uid))
            .build();
    }

    private static String requireText(String field, String value) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(field + " không được rỗng");
        }
        return value;
    }
}
~~~

Ví dụ sử dụng:

~~~java
userDirectoryService.addEmail("an", "an.alt@example.org");

userDirectoryService.replacePhoneNumbers(
    "an", java.util.List.of("+84-28-2222", "+84-90-3333")
);

userDirectoryService.removeEmail("an", "an.personal@example.org");
userDirectoryService.removeDescription("an");
~~~

**Lưu ý về DN và schema:**

- `LdapNameBuilder` tạo DN bằng các RDN có cấu trúc và xử lý việc escape ký tự đặc biệt trong giá trị tốt hơn cách nối chuỗi DN thủ công.
- Các thuộc tính như `mail`, `telephoneNumber`, `description` chỉ là ví dụ. Máy chủ sẽ đối chiếu với schema thực tế của entry (ví dụ `inetOrgPerson`), cú pháp giá trị và quyền được cấp.
- Đoạn mã kiểm tra giá trị không rỗng nhằm minh họa; ứng dụng thực tế cần thêm kiểm tra định dạng, chính sách dữ liệu, trùng lặp và quyền cập nhật trước khi gọi LDAP.
- Nếu `ContextSource` **không** đặt base DN, cần truyền DN đầy đủ phù hợp với cấu hình đó.

## 4. Kết hợp nhiều thay đổi trong một lần gọi

Khi một yêu cầu nghiệp vụ gồm nhiều sửa đổi trên **cùng entry**, hãy tạo mảng `ModificationItem[]`:

~~~java
Name dn = LdapNameBuilder.newInstance()
    .add("ou", "people")
    .add("uid", "an")
    .build();

ModificationItem[] changes = {
    new ModificationItem(
        DirContext.ADD_ATTRIBUTE,
        new BasicAttribute("mail", "an.project@example.org")
    ),
    new ModificationItem(
        DirContext.REPLACE_ATTRIBUTE,
        new BasicAttribute("telephoneNumber", "+84-28-4444")
    ),
    new ModificationItem(
        DirContext.REMOVE_ATTRIBUTE,
        new BasicAttribute("description")
    )
};

ldapTemplate.modifyAttributes(dn, changes);
~~~

Theo giao diện JNDI, các phần tử trong mảng được áp dụng **theo thứ tự khai báo**. Trên LDAP server tuân thủ giao thức, một yêu cầu Modify đối với một entry được thực hiện nguyên tử: nếu một thay đổi không hợp lệ, yêu cầu thất bại và các thay đổi thuộc cùng yêu cầu không được xác nhận từng phần. Tài liệu JNDI diễn đạt mức bảo đảm chung là thực hiện nguyên tử *khi có thể*, vì hành vi cuối cùng còn phụ thuộc nhà cung cấp dịch vụ thư mục.

Không nhầm tính nguyên tử của **một yêu cầu Modify** với giao dịch nhiều entry: hai lời gọi `modifyAttributes` trên hai DN khác nhau **không mặc nhiên** tạo thành một transaction. Tương tự, thao tác đọc rồi `REPLACE_ATTRIBUTE` sau đó có thể ghi đè cập nhật của tiến trình khác; hãy thiết kế kiểm soát đồng thời nếu dữ liệu cần ràng buộc mạnh.

## 5. Đọc kết quả theo góc nhìn LDAP: LDIF

Một thay đổi tương đương có thể mô tả bằng LDIF loại `changetype: modify`:

~~~ldif
dn: uid=an,ou=people,dc=example,dc=org
changetype: modify
add: mail
mail: an.project@example.org
-
replace: telephoneNumber
telephoneNumber: +84-28-4444
-
delete: description
~~~

Ở đây, `add` tương ứng `ADD_ATTRIBUTE`, `replace` tương ứng `REPLACE_ATTRIBUTE`, còn `delete` tương ứng `REMOVE_ATTRIBUTE`. Để xóa một giá trị thay vì toàn bộ thuộc tính, chỉ rõ giá trị ngay dưới dòng `delete`:

~~~ldif
dn: uid=an,ou=people,dc=example,dc=org
changetype: modify
delete: mail
mail: an.personal@example.org
~~~

LDIF hữu ích khi kiểm tra log thay đổi, đối chiếu với công cụ quản trị LDAP hoặc trao đổi với người vận hành. Dù sử dụng Java hay LDIF, luật của schema và quyền truy cập vẫn được máy chủ thực thi.

## 6. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Hướng kiểm tra |
| --- | --- | --- |
| `ADD_ATTRIBUTE` thất bại | Giá trị đã có; thuộc tính chỉ cho phép một giá trị; giá trị sai cú pháp | Kiểm tra giá trị hiện tại, schema và thông báo LDAP `attributeOrValueExists`/constraint |
| `REPLACE_ATTRIBUTE` làm mất email khác | Chỉ gửi một email cho thuộc tính nhiều giá trị | Xây dựng đầy đủ tập giá trị mong muốn trước khi replace; dùng ADD nếu chỉ cần bổ sung |
| `REMOVE_ATTRIBUTE` thất bại | Thuộc tính/giá trị không tồn tại; thuộc tính bắt buộc; quyền không đủ | Kiểm tra trạng thái entry, schema, ACL và phản hồi từ server |
| Không tìm thấy entry | DN tương đối không khớp base DN; nhầm `uid` hoặc `ou` | Đối chiếu DN thực tế và cấu hình `ContextSource` |
| Sửa đổi bị từ chối dù DN đúng | Bind account không có quyền ghi; thuộc tính bị kiểm soát bởi server | Kiểm tra ACL và thuộc tính vận hành; dùng tài khoản có quyền tối thiểu đủ dùng |

`LdapTemplate` chuyển các lỗi của JNDI sang hệ ngoại lệ không kiểm tra của Spring LDAP, vì vậy mã ứng dụng cần phân loại các trường hợp **entry không tồn tại**, **giá trị trùng/không tồn tại**, **vi phạm schema**, **thiếu quyền** và **lỗi kết nối** theo yêu cầu nghiệp vụ. Đừng coi tất cả thất bại là lý do để retry: thử lại lệnh ADD sau timeout có thể gặp giá trị đã được thêm trong lần trước.

Một số nguyên tắc khi triển khai trong hệ thống thật:

1. **Giới hạn quyền ghi** của tài khoản bind cho đúng nhánh và thuộc tính cần cập nhật. Không để dữ liệu người dùng quyết định tùy ý tên thuộc tính hoặc DN đích.
2. **Dùng TLS** (`ldaps://` hoặc StartTLS cấu hình đúng) khi truyền thông tin người dùng hay thông tin xác thực; kiểm tra chứng chỉ máy chủ.
3. **Không ghi log bí mật hoặc toàn bộ entry** chỉ để debug. Với trường nhạy cảm như `userPassword`, dùng chính sách đổi mật khẩu và cơ chế bảo vệ phù hợp với máy chủ LDAP thay vì xem nó như một trường văn bản thông thường.
4. **Kiểm tra thuộc tính bắt buộc** trước khi xóa, đồng thời dựa vào phản hồi của server làm nguồn quyết định cuối cùng.
5. **Kiểm chứng kết quả** bằng cách đọc lại những thuộc tính cần thiết trong bài kiểm thử tích hợp; không dựa vào thứ tự của tập giá trị đa trị.

## 7. Bài tập vận dụng

Cho entry có `mail = {an.work@example.org, an.personal@example.org}`, `telephoneNumber = {111, 222}` và `description = {active}`. Hãy dự đoán kết quả cho từng tình huống **độc lập**, đều bắt đầu từ trạng thái ban đầu:

| Yêu cầu | Phép phù hợp | Kết quả mong đợi khi máy chủ chấp nhận |
| --- | --- | --- |
| Thêm `an.alt@example.org`, giữ các email cũ | `ADD_ATTRIBUTE` trên `mail` | Có 3 email |
| Chỉ giữ số `333` | `REPLACE_ATTRIBUTE` trên `telephoneNumber` | Chỉ còn `333` |
| Xóa email cá nhân, giữ email công việc | `REMOVE_ATTRIBUTE` với giá trị `an.personal@example.org` | Còn `an.work@example.org` |
| Bỏ hẳn phần mô tả | `REMOVE_ATTRIBUTE` với `new BasicAttribute("description")` | Không còn thuộc tính `description` |
| Thêm lại `an.work@example.org` bằng ADD | `ADD_ATTRIBUTE` trên `mail` | Có khả năng bị từ chối vì giá trị đã tồn tại |

Khi thực hành trên LDAP server thử nghiệm, hãy tạo entry theo schema cho phép, thực hiện từng thao tác, dùng tìm kiếm/lookup để so sánh trước và sau, rồi thử thêm một thao tác cố tình sai để quan sát mã lỗi và tính nguyên tử của yêu cầu. Không thử sửa thông tin người dùng thật trong môi trường production.

## 8. Ghi nhớ

- **ADD** khi cần **bổ sung** giá trị, **REPLACE** khi muốn **quyết định lại toàn bộ tập giá trị**, **REMOVE** khi cần **bỏ một giá trị hoặc cả thuộc tính**.
- Với thuộc tính đa trị, REPLACE một giá trị nghĩa là **loại bỏ tất cả giá trị cũ**; REMOVE một giá trị mới bảo toàn các giá trị khác.
- `ModificationItem` mang **mã phép sửa đổi + thuộc tính**, còn `LdapTemplate.modifyAttributes(dn, changes)` gửi các thay đổi lên entry ở DN đã chọn.
- Mỗi thay đổi vẫn chịu kiểm tra của **schema, ACL và server LDAP**. Cần xử lý lỗi trùng giá trị, thiếu giá trị, thiếu quyền và cập nhật đồng thời theo bối cảnh nghiệp vụ.

### Tài liệu tham khảo

- [Spring LDAP — API của LdapTemplate](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/LdapTemplate.html)
- [Spring LDAP — Basic Usage: Updating by Using modifyAttributes](https://docs.spring.io/spring-ldap/reference/spring-ldap-basic-usage.html)
- [Oracle JNDI — DirContext (ADD, REPLACE, REMOVE)](https://docs.oracle.com/en/java/javase/25/docs/api/java.naming/javax/naming/directory/DirContext.html)
- [Oracle JNDI Tutorial — Modify Attributes](https://docs.oracle.com/javase/tutorial/jndi/ops/modattrs.html)
