# Modify attributes với `ModificationItem` trong Spring LDAP

## 1. Bài toán: sửa entry mà không tạo lại tài khoản

Trong ứng dụng sử dụng **Spring LDAP**, việc thay đổi thông tin người dùng thường chỉ liên quan đến **thuộc tính** của một entry đã tồn tại: cập nhật email, thêm số điện thoại, xóa một ghi chú cũ hoặc điều chỉnh các giá trị của một thuộc tính đa trị. Không nên xóa rồi tạo lại toàn bộ entry để thực hiện các thay đổi nhỏ này.

Ví dụ một entry trong dịch vụ thư mục:

~~~ldif
dn: uid=alice,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: alice
cn: Alice Nguyen
sn: Nguyen
mail: alice@example.org
telephoneNumber: +84 28 1111 2222
description: active
description: onboarding
~~~

Ứng dụng có thể cần:

- **Thay** email bằng `alice.new@example.org`.
- **Thêm** số điện thoại `+84 28 3333 4444`, giữ số hiện có nếu schema cho phép nhiều giá trị.
- **Bỏ** đúng giá trị `onboarding` của thuộc tính `description`, nhưng giữ `active`.

Trong Spring LDAP, `LdapTemplate.modifyAttributes(...)` kết hợp với mảng **`ModificationItem[]`** của JNDI là cách trực tiếp để gửi những thay đổi này tới server.

Bài học thuộc chương **LdapTemplate**, tập trung vào thao tác LDAP **Modify**. Chúng ta sẽ phân biệt ba phép **ADD**, **REPLACE**, **REMOVE**, hiểu thứ tự áp dụng và tính nguyên tử của một yêu cầu Modify, dựng DN an toàn, kiểm tra schema/ACL, xử lý ngoại lệ và kiểm thử trên LDAP directory thử nghiệm.

> **Phân biệt:** sửa thuộc tính bằng **Modify** không phải đổi tên entry bằng **Modify DN**. Nếu cần chuyển `uid=alice,ou=people,...` sang `ou=alumni` hoặc đổi RDN `uid=alice`, hãy dùng thao tác `rename` phù hợp thay vì chỉ sửa `uid` trong mảng `ModificationItem`.

## 2. Ba thành phần cấu thành thao tác Modify

Trong Java/JNDI, một thay đổi thuộc tính được biểu diễn bằng:

~~~java
new ModificationItem(
    DirContext.REPLACE_ATTRIBUTE,
    new BasicAttribute("mail", "alice.new@example.org")
);
~~~

Các phần chính:

| Thành phần | Vai trò | Ví dụ |
| --- | --- | --- |
| `ModificationItem` | Một thao tác sửa thuộc tính đơn lẻ | Replace giá trị `mail` |
| Mã thao tác `DirContext.*_ATTRIBUTE` | Chọn thêm, thay thế hay xóa | `REPLACE_ATTRIBUTE` |
| `BasicAttribute` | Chứa tên thuộc tính và giá trị tác động | `new BasicAttribute("mail", "...")` |
| `ModificationItem[]` | Danh sách thao tác gửi cho cùng một entry | Replace `mail`, add `telephoneNumber` |
| DN đích | Xác định entry được sửa | `uid=alice,ou=people` tương đối với base |
| `LdapTemplate.modifyAttributes(dn, items)` | Gửi yêu cầu LDAP Modify | Trả về sau khi server xử lý hoặc ném ngoại lệ |

Hai kiểu liên quan đến thao tác sửa thuộc tính—`javax.naming.directory.ModificationItem` và `javax.naming.directory.BasicAttribute`—thuộc **JNDI**. `LdapTemplate` thuộc **Spring LDAP**, sử dụng chúng để tương tác với server mà không cần mã nghiệp vụ tự mở, đóng `DirContext`.

### 2.1. ADD_ATTRIBUTE: thêm thuộc tính hoặc giá trị

~~~java
ModificationItem addPhone = new ModificationItem(
    DirContext.ADD_ATTRIBUTE,
    new BasicAttribute("telephoneNumber", "+84 28 3333 4444")
);
~~~

Nếu entry chưa có `telephoneNumber`, thao tác có thể tạo thuộc tính với giá trị đó. Nếu entry đã có thuộc tính **đa trị**, phép ADD có thể thêm giá trị mới mà không xóa các giá trị trước.

Tuy nhiên:

- Nếu thuộc tính là **SINGLE-VALUE**, thêm một giá trị thứ hai có thể bị từ chối.
- Nếu giá trị đã tồn tại, server có thể trả `attributeOrValueExists` (LDAP result code **20**).
- Nếu thuộc tính không được object class cho phép, hoặc giá trị sai syntax, server sẽ từ chối theo schema.

**ADD không có nghĩa “upsert bất kể trạng thái”.** Muốn kết quả có thể chạy lại an toàn, cần biết trạng thái hiện tại, chính sách schema và cách xử lý trường hợp giá trị đã có.

### 2.2. REPLACE_ATTRIBUTE: thay cả tập giá trị của thuộc tính

~~~java
ModificationItem replaceMail = new ModificationItem(
    DirContext.REPLACE_ATTRIBUTE,
    new BasicAttribute("mail", "alice.new@example.org")
);
~~~

`REPLACE_ATTRIBUTE` đặt tập giá trị của `mail` theo những giá trị cung cấp trong `BasicAttribute`. Với một thuộc tính đa trị, **replace có thể xóa các giá trị cũ mà bạn không truyền lại**.

Ví dụ, nếu entry đang có hai giá trị `telephoneNumber` nhưng bạn replace bằng một giá trị, số điện thoại còn lại có thể bị mất. Nếu ý định chỉ là thêm số mới, dùng `ADD_ATTRIBUTE` là đúng hơn.

### 2.3. REMOVE_ATTRIBUTE: xóa một giá trị hoặc toàn bộ thuộc tính

**Xóa một giá trị cụ thể** khỏi một thuộc tính có nhiều giá trị:

~~~java
ModificationItem removeOneNote = new ModificationItem(
    DirContext.REMOVE_ATTRIBUTE,
    new BasicAttribute("description", "onboarding")
);
~~~

**Xóa toàn bộ thuộc tính** (không truyền giá trị):

~~~java
ModificationItem removeAllNotes = new ModificationItem(
    DirContext.REMOVE_ATTRIBUTE,
    new BasicAttribute("description")
);
~~~

Với trường hợp đầu tiên, entry có thể vẫn giữ `description: active`. Với trường hợp thứ hai, tất cả giá trị `description` đều bị loại bỏ nếu thao tác hợp lệ.

Nếu yêu cầu xóa một giá trị hoặc thuộc tính **không tồn tại**, server có thể trả `noSuchAttribute` (LDAP result code **16**). Nếu xóa thuộc tính bắt buộc (`MUST`) hoặc giá trị tham gia RDN theo cách bị cấm, server có thể trả lỗi schema/naming thay vì xóa.

### 2.4. Bảng quyết định nhanh

| Nhu cầu | Mã thao tác | Điều dễ sai |
| --- | --- | --- |
| Thêm số điện thoại thứ hai | `ADD_ATTRIBUTE` | Thuộc tính có thể chỉ cho phép một giá trị |
| Thay địa chỉ email hiện có | `REPLACE_ATTRIBUTE` | Mọi giá trị cũ của thuộc tính có thể bị thay |
| Xóa một ghi chú cụ thể | `REMOVE_ATTRIBUTE` + `BasicAttribute(id, value)` | Giá trị bị xóa phải tồn tại |
| Xóa toàn bộ ghi chú tùy chọn | `REMOVE_ATTRIBUTE` + `BasicAttribute(id)` | Đừng xóa thuộc tính `MUST` |
| Đổi UID dùng trong RDN | **Modify DN / `rename`** | Không phải trường hợp dùng `ModificationItem` đơn thuần |
| Tạo một người dùng mới | **LDAP Add / `bind`** | DN mới phải chưa tồn tại |

## 3. Cấu hình LdapTemplate và ContextSource

`LdapTemplate` lấy context qua `ContextSource`, thực hiện thao tác và quản lý vòng đời tài nguyên. Ví dụ ứng dụng Spring sử dụng tài khoản bind có quyền phù hợp trong OU thử nghiệm:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.core.support.LdapContextSource;

@Configuration
public class DirectoryConfiguration {

    @Bean
    public LdapContextSource ldapContextSource(
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
    public LdapTemplate ldapTemplate(LdapContextSource ldapContextSource) {
        return new LdapTemplate(ldapContextSource);
    }
}
~~~

~~~yaml
# application.yml
app:
  ldap:
    url: ${LDAP_URL:ldaps://ldap.example.org:636}
    base: dc=example,dc=org
    bind-dn: ${LDAP_BIND_DN}
    bind-password: ${LDAP_BIND_PASSWORD}
~~~

**Ba thành phần cần phân biệt**:

- **Server URL:** `ldaps://ldap.example.org:636` là điểm kết nối có TLS.
- **Base DN:** `dc=example,dc=org` là tiền tố/gốc mà template sử dụng để giải quyết các DN tương đối.
- **Bind DN:** danh tính của tài khoản dịch vụ, ví dụ `cn=directory-editor,ou=system,dc=example,dc=org`, không phải tên của entry đang sửa.

Với base như trên, DN tương đối `uid=alice,ou=people` được hiểu là `uid=alice,ou=people,dc=example,dc=org`.

Không nhúng password trực tiếp vào source code hoặc file commit. Biến môi trường/secret manager cần được quản lý an toàn; LDAPS phải xác minh chứng chỉ và hostname. Việc tạo bean thành công chưa chứng minh LDAP server chấp nhận bind hoặc thao tác ghi.

## 4. Ví dụ hoàn chỉnh: sửa email bằng ModificationItem

Dưới đây là lớp repository có một chức năng đơn giản: thay email của entry có `uid` được chỉ định. Dự kiến entry nằm trực tiếp bên dưới `ou=people` và có thuộc tính `mail` được object class cho phép.

~~~java
import javax.naming.Name;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;

import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;
import org.springframework.stereotype.Repository;

@Repository
public class PersonDirectoryRepository {

    private final LdapTemplate ldapTemplate;

    public PersonDirectoryRepository(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public void replaceMail(String uid, String newMail) {
        if (uid == null || uid.isBlank()
                || newMail == null || newMail.isBlank()) {
            throw new IllegalArgumentException(
                    "uid and mail must not be blank");
        }

        Name relativeDn = LdapNameBuilder.newInstance("ou=people")
                .add("uid", uid)
                .build();

        ModificationItem[] changes = {
            new ModificationItem(
                    DirContext.REPLACE_ATTRIBUTE,
                    new BasicAttribute("mail", newMail)
            )
        };

        ldapTemplate.modifyAttributes(relativeDn, changes);
    }
}
~~~

Một lần gọi:

~~~java
personDirectoryRepository.replaceMail(
        "alice",
        "alice.new@example.org"
);
~~~

yêu cầu server cập nhật entry:

~~~text
DN đích: uid=alice,ou=people,dc=example,dc=org
Thao tác: REPLACE_ATTRIBUTE
Thuộc tính: mail
Giá trị mới: alice.new@example.org
~~~

**Dựng DN an toàn:** `LdapNameBuilder.add("uid", uid)` xử lý escaping DN cho giá trị RDN; tránh tự nối chuỗi như `"uid=" + uid + ",ou=people"` khi `uid` có thể chứa ký tự đặc biệt.

**Kiểm tra dữ liệu:** builder xử lý cấu trúc DN, không xác minh email hợp lệ theo quy tắc nghiệp vụ, tính duy nhất của UID, sự tồn tại entry hoặc quyền ghi. Trên thư mục có người dùng nằm sâu trong nhiều OU, không nên giả định mọi UID nằm trực tiếp dưới `ou=people`: cần tìm DN thực tế hoặc thiết kế nhánh theo mô hình hạ tầng.

## 5. Thêm và xóa giá trị: ví dụ với thuộc tính đa trị

### 5.1. Thêm một số điện thoại, giữ số cũ

~~~java
public void addPhone(String uid, String phone) {
    Name relativeDn = LdapNameBuilder.newInstance("ou=people")
            .add("uid", uid)
            .build();

    ModificationItem[] changes = {
        new ModificationItem(
                DirContext.ADD_ATTRIBUTE,
                new BasicAttribute("telephoneNumber", phone)
        )
    };

    ldapTemplate.modifyAttributes(relativeDn, changes);
}
~~~

Đây là phương thức bổ sung trong lớp repository ở phần trước, với các import đã nêu. Trong mô hình dữ liệu có `telephoneNumber` đa trị, số mới được thêm, không thay số cũ. Với hệ thống khác hoặc schema mở rộng, cần xác nhận quy tắc số lượng giá trị và định dạng số điện thoại.

### 5.2. Bỏ một ghi chú nhưng giữ các ghi chú khác

~~~java
public void removeNoteValue(String uid, String noteToRemove) {
    Name relativeDn = LdapNameBuilder.newInstance("ou=people")
            .add("uid", uid)
            .build();

    ModificationItem[] changes = {
        new ModificationItem(
                DirContext.REMOVE_ATTRIBUTE,
                new BasicAttribute("description", noteToRemove)
        )
    };

    ldapTemplate.modifyAttributes(relativeDn, changes);
}
~~~

Nếu entry có hai giá trị `description: active` và `description: onboarding`, gọi `removeNoteValue("alice", "onboarding")` nhằm xóa **chỉ** `onboarding`. Nếu giá trị không tồn tại, server có thể từ chối thay vì lặng lẽ coi thành công.

### 5.3. Xóa hẳn một thuộc tính tùy chọn

~~~java
ModificationItem deleteDescription = new ModificationItem(
        DirContext.REMOVE_ATTRIBUTE,
        new BasicAttribute("description")
);
ldapTemplate.modifyAttributes(relativeDn,
        new ModificationItem[] {deleteDescription});
~~~

Đoạn mã giả định đã có `relativeDn` hợp lệ và `ldapTemplate` của repository. Chỉ sử dụng khi `description` **không bắt buộc** theo schema và nghiệp vụ thực sự muốn xóa tất cả giá trị. Đối với `cn` hoặc `sn` bắt buộc của object class `person`, xóa toàn bộ có thể gây `objectClassViolation`.

## 6. Gộp nhiều thay đổi trong một lần gọi

Một LDAP Modify request có thể chứa **danh sách thay đổi có thứ tự** đối với **cùng một entry**. Đây là một trong những lý do quan trọng để dùng `ModificationItem[]` thay vì gọi template riêng lẻ cho từng thuộc tính.

Giả sử entry Alice đã có:

~~~ldif
dn: uid=alice,ou=people,dc=example,dc=org
mail: alice@example.org
telephoneNumber: +84 28 1111 2222
description: active
description: onboarding
~~~

Có thể thay email, thêm số điện thoại thứ hai và xóa đúng ghi chú `onboarding`:

~~~java
import javax.naming.Name;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;
import org.springframework.ldap.support.LdapNameBuilder;

Name dn = LdapNameBuilder.newInstance("ou=people")
        .add("uid", "alice")
        .build();

ModificationItem[] changes = {
    new ModificationItem(
            DirContext.REPLACE_ATTRIBUTE,
            new BasicAttribute("mail", "alice.new@example.org")
    ),
    new ModificationItem(
            DirContext.ADD_ATTRIBUTE,
            new BasicAttribute("telephoneNumber", "+84 28 3333 4444")
    ),
    new ModificationItem(
            DirContext.REMOVE_ATTRIBUTE,
            new BasicAttribute("description", "onboarding")
    )
};

ldapTemplate.modifyAttributes(dn, changes);
~~~

Khi schema, ACL và trạng thái ban đầu đáp ứng tiền điều kiện, kết quả dự kiến:

~~~ldif
dn: uid=alice,ou=people,dc=example,dc=org
mail: alice.new@example.org
telephoneNumber: +84 28 1111 2222
telephoneNumber: +84 28 3333 4444
description: active
~~~

### 6.1. Thứ tự thay đổi có ý nghĩa

Theo ngữ nghĩa của LDAP Modify, các sửa đổi trong một request được xử lý **theo thứ tự chúng xuất hiện**. Vì vậy, với một thuộc tính, hành vi của chuỗi `REMOVE_ATTRIBUTE` rồi `ADD_ATTRIBUTE` có thể khác chuỗi `ADD_ATTRIBUTE` rồi `REMOVE_ATTRIBUTE`, nhất là khi giá trị trùng hoặc khi thuộc tính đơn trị.

Không nên tự sắp xếp lại các `ModificationItem` một cách ngẫu nhiên, cũng không xây mảng từ một cấu trúc mà thứ tự phụ thuộc vào cách duyệt không ổn định khi có quan hệ phụ thuộc.

### 6.2. Tính nguyên tử của một LDAP Modify request

LDAP yêu cầu **cả danh sách sửa đổi trong một Modify request được thực hiện như một thao tác nguyên tử trên entry đó**: về nguyên tắc, nếu một thay đổi không hợp lệ, request không được phép áp dụng dở dang các thay đổi khác của cùng yêu cầu.

Điều này **khác** với gọi:

~~~java
ldapTemplate.modifyAttributes(dn, emailChanges);
ldapTemplate.modifyAttributes(dn, phoneChanges);
ldapTemplate.modifyAttributes(dn, noteChanges);
~~~

Ba lời gọi trên tạo **ba yêu cầu độc lập**. Nếu lời gọi thứ hai hoặc thứ ba thất bại, thay đổi ở lời gọi trước có thể đã được lưu.

Dù một request trên một entry là nguyên tử, **đừng suy ra** Spring LDAP tự tạo transaction bao trùm nhiều LDAP entry, một database SQL, cache và API bên ngoài. Cũng không được tự động khẳng định thao tác thất bại khi mạng bị ngắt sau khi gửi request nhưng trước khi nhận response; cần đọc lại trạng thái thực tế.

### 6.3. Gộp không thay thế kiểm tra dữ liệu

Nếu `description: onboarding` không tồn tại, bước REMOVE có thể bị từ chối và request nguyên tử sẽ không thay email hoặc thêm số điện thoại. Nếu người dùng thực sự yêu cầu bỏ ghi chú “nếu có”, ứng dụng phải thiết kế rõ **tiền điều kiện và chính sách idempotency**, thay vì giả định mọi LDAP server đều bỏ qua lỗi xóa giá trị không tồn tại.

## 7. Đối chiếu với LDIF và công cụ ldapmodify

Một cách dễ học là so sánh `ModificationItem[]` với LDIF dạng **changetype: modify**. Giả sử entry đã có dữ liệu tiền điều kiện ở phần 6, tệp `update-alice.ldif` có thể chứa:

~~~ldif
dn: uid=alice,ou=people,dc=example,dc=org
changetype: modify
replace: mail
mail: alice.new@example.org
-
add: telephoneNumber
telephoneNumber: +84 28 3333 4444
-
delete: description
description: onboarding
~~~

Lưu ý các dấu `-` ngăn cách từng thao tác. `replace`, `add` và `delete` trong LDIF ở đây tương ứng với ba mã thao tác của `DirContext` trong Java. Cả hai cách cùng mô tả một LDAP Modify request đối với entry đích.

Trên directory dành riêng cho thử nghiệm, có thể chạy:

~~~bash
ldapmodify -x \
  -H "ldaps://ldap.example.org:636" \
  -D "cn=directory-editor,ou=system,dc=example,dc=org" -W \
  -f update-alice.ldif
~~~

- `-H`: URL máy chủ LDAP qua TLS.
- `-D`: DN của tài khoản **có quyền thay đổi entry**.
- `-W`: nhập mật khẩu qua lời nhắc thay vì đặt ngay trên dòng lệnh.
- `-f`: tệp LDIF chứa yêu cầu thay đổi.

Sau đó xác minh:

~~~bash
ldapsearch -LLL -x \
  -H "ldaps://ldap.example.org:636" \
  -D "cn=directory-reader,ou=system,dc=example,dc=org" -W \
  -b "uid=alice,ou=people,dc=example,dc=org" -s base \
  "(objectClass=*)" dn mail telephoneNumber description
~~~

Dữ liệu và DN là ví dụ, không dùng trực tiếp trên thư mục sản xuất. Máy chủ phải có schema hỗ trợ `mail`, `telephoneNumber`, `description` cho object class thực tế và tài khoản bind có quyền phù hợp.

## 8. Đọc lại kết quả sau khi modify

`LdapTemplate.modifyAttributes(...)` gửi thao tác và không trả về object chứa entry đã cập nhật. Nếu nghiệp vụ cần xác nhận giá trị thực tế, hãy **lookup lại entry**.

~~~java
import javax.naming.Name;
import javax.naming.directory.Attribute;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.support.LdapNameBuilder;

Name dn = LdapNameBuilder.newInstance("ou=people")
        .add("uid", "alice")
        .build();

String currentMail = ldapTemplate.lookup(
        dn,
        (AttributesMapper<String>) attributes -> {
            Attribute mail = attributes.get("mail");
            return mail == null ? null : String.valueOf(mail.get());
        }
);

// So sánh currentMail với giá trị mới đã yêu cầu.
~~~

Nếu muốn kiểm chứng **thuộc tính đa trị**, đừng chỉ đọc `Attribute.get()` rồi kết luận đủ tất cả giá trị. Phải duyệt `getAll()` và đóng `NamingEnumeration` nếu cần. Kết quả readback cũng phụ thuộc quyền đọc: tài khoản có thể ghi một thuộc tính nhưng lại không được quyền đọc thuộc tính đó theo ACL.

### 8.1. Vì sao lookup trước khi modify chưa đủ?

Một phương thức có thể kiểm tra entry trước khi sửa, nhưng giữa hai lần gọi **một tác nhân khác có thể cập nhật entry**. Đây là một vấn đề cạnh tranh (race condition). Ví dụ, ứng dụng đọc `telephoneNumber` cũ, chuẩn bị replace toàn bộ rồi một yêu cầu khác thêm số mới: lời gọi replace sau đó có thể loại bỏ thay đổi của yêu cầu kia.

Cách giải quyết phụ thuộc mô hình dữ liệu và server: chọn `ADD_ATTRIBUTE` hoặc `REMOVE_ATTRIBUTE` cho các thay đổi nhỏ thay vì ghi đè toàn bộ; sử dụng cơ chế kiểm soát đồng thời/LDAP assertion control khi được hỗ trợ; hoặc thiết kế quy trình cập nhật có xác minh và xử lý xung đột. Không nên coi thao tác “read, modify, write” là một transaction chỉ vì sử dụng cùng `LdapTemplate`.

## 9. Schema, DN và quyền ghi: ba điều kiện độc lập

### 9.1. Chỉ sửa những thuộc tính được objectClass cho phép

Ví dụ `inetOrgPerson` kế thừa `person` với thuộc tính bắt buộc như `cn`, `sn` và có thể cho phép `mail`, `telephoneNumber`. Tuy nhiên, schema thực tế và overlay của server vẫn là nguồn quyết định.

| Thao tác | Nguy cơ | Lỗi có thể xuất hiện |
| --- | --- | --- |
| Xóa toàn bộ `sn` của entry `person` | Vi phạm thuộc tính `MUST` | `objectClassViolation` (65) |
| Thêm giá trị thứ hai cho thuộc tính `SINGLE-VALUE` | Vượt số giá trị cho phép | `constraintViolation` (19) hoặc mã tương ứng |
| Thêm thuộc tính không được schema định nghĩa | Attribute type không tồn tại | `undefinedAttributeType` (17) |
| Ghi giá trị sai cú pháp | Sai `SYNTAX` | `invalidAttributeSyntax` (21) |
| Ghi một thuộc tính có định nghĩa nhưng object class không cho phép | Sai cấu trúc entry | `objectClassViolation` (65) |
| Xóa giá trị tham gia RDN theo cách bị cấm | Sai quy tắc đặt tên | `notAllowedOnRDN` (67) hoặc lỗi naming |
| Sửa thuộc tính chỉ đọc do server quản lý | Vi phạm chính sách máy chủ | Mã lỗi tùy server, ví dụ `constraintViolation` hoặc `unwillingToPerform` |

Các thuộc tính **vận hành** như `createTimestamp`, `modifyTimestamp`, `entryUUID` thường do server quản lý và không phải trường có thể sửa tùy ý. Thuộc tính nhạy cảm như `userPassword` còn cần chính sách xác thực, quyền và bảo vệ đường truyền riêng. Không đưa password vào log hoặc thử nghiệm thay đổi credential của người dùng thật.

### 9.2. DN phải đúng, kể cả khi filter đúng

`modifyAttributes` thao tác trên **một DN đích cụ thể**, không dùng search scope hoặc filter để tự tìm entry. Với `LdapContextSource.setBase("dc=example,dc=org")`, DN truyền vào template thường **tương đối** so với hậu tố đó.

~~~text
ContextSource base = dc=example,dc=org
DN đưa vào       = uid=alice,ou=people
DN thực tế       = uid=alice,ou=people,dc=example,dc=org
~~~

Nếu người dùng có thể nằm sâu hơn trong `ou=engineering`, DN sẽ khác. Khi cần tìm trước, hãy dùng search với base, scope và filter đúng; sau đó thao tác trên **DN thực của entry** được xác định. Không lấy `uid` rồi tự giả định vị trí OU nếu hạ tầng không có quy tắc cố định.

### 9.3. ACL được server thực thi

`LdapTemplate` không quyết định quyền ghi. Dù phương thức Java tồn tại và kết nối bind thành công, server có thể từ chối sửa. Một thiết kế tốt tách:

- **Reader**: danh tính chỉ đọc phục vụ tìm người dùng/nhóm.
- **Editor**: danh tính có quyền sửa **đúng OU và đúng thuộc tính** cần thiết.

Ngay cả khi dùng `ContextSource.getReadWriteContext()`, một tài khoản reader vẫn không được tự cấp quyền sửa. Khi có hai `LdapTemplate` trong Spring, hãy đặt tên bean và dùng `@Qualifier` để đảm bảo repository ghi sử dụng đúng tài khoản.

## 10. Escaping dữ liệu và bảo mật trong thao tác modify

Ba loại giá trị dễ bị nhầm:

1. **DN/RDN**: được tạo bằng `LdapNameBuilder` hoặc công cụ xử lý DN theo chuẩn.
2. **LDAP filter**: được tạo bằng `LdapQueryBuilder` hoặc các lớp filter để escape dữ liệu tìm kiếm.
3. **Giá trị thuộc tính**: được truyền qua `BasicAttribute`, không phải một đoạn cú pháp filter/DN cần ghép chuỗi.

Ví dụ:

~~~java
Name dn = LdapNameBuilder.newInstance("ou=people")
        .add("uid", userProvidedUid)
        .build();

ModificationItem item = new ModificationItem(
        DirContext.REPLACE_ATTRIBUTE,
        new BasicAttribute("mail", userProvidedMail)
);
~~~

Đừng tự ghép DN bằng dấu phẩy hoặc áp dụng cú pháp escape filter cho giá trị thuộc tính. Tuy nhiên, việc API nhận giá trị thô **không thay thế validation**: hãy giới hạn tên thuộc tính có thể sửa bằng allowlist, kiểm tra kiểu/độ dài, quyền người dùng, giới hạn nhánh cập nhật và chống ghi đè không mong muốn.

Một endpoint cho phép client chọn tên thuộc tính tùy ý rồi gọi `REPLACE_ATTRIBUTE` là thiết kế nguy hiểm: người dùng có thể cố sửa `objectClass`, thuộc tính mật khẩu, nhóm hoặc trường quản trị nếu ACL bị cấu hình quá rộng. Dùng dịch vụ chuyên biệt như `replaceMail`, `addPhone`, `removeNoteValue` với quyền tối thiểu.

**Bảo mật kết nối:** khi dùng LDAPS hoặc StartTLS phải xác minh chứng chỉ và hostname. Chỉ đặt URL `ldap://` không tự bật StartTLS; không gửi mật khẩu simple bind qua mạng không được bảo vệ. Pooling có thể giúp hiệu năng nhưng phải kiểm tra danh tính bind, tương thích StartTLS và cơ chế trả context; pooling không thay thế ACL.

## 11. Phân loại lỗi khi sửa thuộc tính

| LDAP result code | Tên phổ biến | Nguyên nhân cần kiểm tra |
| --- | --- | --- |
| **16** | `noSuchAttribute` | Xóa giá trị/thuộc tính không tồn tại |
| **17** | `undefinedAttributeType` | Tên thuộc tính chưa được định nghĩa |
| **19** | `constraintViolation` | Vi phạm tính đơn trị hoặc quy tắc bổ sung |
| **20** | `attributeOrValueExists` | Thêm giá trị đã tồn tại |
| **21** | `invalidAttributeSyntax` | Sai định dạng theo schema |
| **32** | `noSuchObject` | DN đích/base không tồn tại hoặc không thể thấy |
| **50** | `insufficientAccessRights` | Bind identity không có quyền sửa |
| **53** | `unwillingToPerform` | Server từ chối theo chính sách |
| **65** | `objectClassViolation` | Không thỏa object class/MUST/MAY |
| **67** | `notAllowedOnRDN` | Sửa giá trị RDN theo cách bị cấm |

Mã và thông báo cụ thể có thể khác theo server và chính sách. Spring LDAP chuyển nhiều lỗi JNDI thành các ngoại lệ của framework, nhưng ứng dụng vẫn cần phân biệt:

- **Validation nghiệp vụ**: đầu vào thiếu email, UID không hợp lệ.
- **Không tìm thấy DN**: entry đích sai hoặc đã bị đổi tên.
- **Schema violation**: dữ liệu mới không hợp lệ.
- **ACL**: kết nối được nhưng không đủ quyền ghi.
- **Kết nối/TLS/timeout**: lỗi hạ tầng, không đồng nghĩa “không tìm thấy entry”.

Không bắt mọi exception rồi trả HTTP “thành công” hoặc “không tìm thấy”. Cũng không trả nguyên văn diagnostic message có DN nội bộ hoặc thông tin nhạy cảm cho người dùng cuối. Log nên lưu mã lỗi, loại thao tác và correlation ID, hạn chế dữ liệu cá nhân và tuyệt đối không log credentials.

### 11.1. Chú ý khi retry

`REPLACE_ATTRIBUTE` với cùng giá trị có thể dễ kiểm soát hơn một thao tác `ADD_ATTRIBUTE` không idempotent. Tuy vậy, nếu server đã xử lý request mà response mất trên mạng, client không biết chắc trạng thái thực tế. Hãy lookup lại entry và so sánh giá trị trước khi quyết định retry. Với `ADD`, retry khi giá trị đã được thêm có thể trả `attributeOrValueExists`, không có nghĩa lần đầu chưa thành công.

## 12. Kiểm thử trên LDAP directory thử nghiệm

Hãy sử dụng một directory riêng có schema gần môi trường mục tiêu, một OU chứa dữ liệu giả và tài khoản được cấp quyền rõ ràng. Không thao tác trên tài khoản thật hoặc tự nâng quyền sản xuất chỉ để vượt qua lỗi.

### 12.1. Ma trận ca kiểm thử

| Ca | Tiền điều kiện | Kết quả mong đợi |
| --- | --- | --- |
| Replace mail | Entry có mail cũ, editor được phép sửa | Mail mới xuất hiện, mail cũ bị thay |
| Add phone | Thuộc tính cho phép đa trị, số mới chưa tồn tại | Giữ số cũ và thêm số mới |
| Remove một description | Entry có `active` và `onboarding` | Bỏ `onboarding`, giữ `active` |
| Remove toàn description | Schema không yêu cầu description | Không còn thuộc tính description |
| Remove `sn` bắt buộc | Entry thuộc class person | Server từ chối, dữ liệu cũ vẫn hợp lệ |
| Add giá trị trùng | Value đã tồn tại | Thường bị từ chối hoặc trả lỗi phù hợp |
| Multi-change có một bước sai | Một yêu cầu Modify chứa thay email + remove giá trị không tồn tại | Không áp dụng dở dang trong **cùng request** |
| Reader cố modify | Reader không có quyền ghi | Server chặn; entry không đổi |
| DN sai | Entry không tồn tại | Lỗi đối tượng hoặc hành vi tương ứng |
| Rớt mạng khi modify | Server/mạng bị gián đoạn | Cần đọc lại trạng thái trước khi retry |

### 12.2. Mã kiểm thử JUnit 5 minh họa

Giả sử có `LdapTemplate` thật trỏ LDAP **thử nghiệm**, entry `training-01` đã tồn tại và có schema/ACL phù hợp:

~~~java
import javax.naming.Name;
import javax.naming.directory.Attribute;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;

import org.junit.jupiter.api.Test;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

import static org.junit.jupiter.api.Assertions.assertEquals;

class PersonModifyIntegrationTest {
    private final LdapTemplate template;

    // Nhận template thử nghiệm qua cấu hình hoặc fixture của dự án.
    PersonModifyIntegrationTest(LdapTemplate template) {
        this.template = template;
    }

    @Test
    void replaceMailAndReadBack() {
        Name dn = LdapNameBuilder.newInstance("ou=people")
                .add("uid", "training-01")
                .build();

        template.modifyAttributes(dn, new ModificationItem[] {
            new ModificationItem(
                    DirContext.REPLACE_ATTRIBUTE,
                    new BasicAttribute("mail", "training-01@example.org"))
        });

        String actual = template.lookup(dn,
                (AttributesMapper<String>) attrs -> {
                    Attribute mail = attrs.get("mail");
                    return mail == null ? null : String.valueOf(mail.get());
                });

        assertEquals("training-01@example.org", actual);
    }
}
~~~

Đây là **khung nội dung test**: constructor cần được cung cấp bean/fixture phù hợp bởi framework kiểm thử của dự án; tự tạo và dọn entry test để chạy lặp lại. Không nhầm một mẫu minh họa với một bộ integration test có thể chạy độc lập khi chưa cấu hình LDAP server, schema và quyền.

### 12.3. Bài thực hành theo từng bước

1. Tạo OU và entry `uid=training-01` trong directory thử nghiệm bằng tài khoản được cấp phép; xác nhận `objectClass`, `cn`, `sn`, `mail`, `telephoneNumber` và `description`.
2. Với `ldapsearch`, đọc trạng thái ban đầu và ghi nhận DN đầy đủ.
3. Viết `replaceMail` bằng `REPLACE_ATTRIBUTE`; gọi `modifyAttributes` và lookup lại.
4. Dùng `ADD_ATTRIBUTE` thêm một số điện thoại, đọc toàn bộ giá trị `telephoneNumber` để xác nhận số cũ không bị mất.
5. Dùng `REMOVE_ATTRIBUTE` xóa đúng một giá trị `description`, sau đó thử xóa toàn thuộc tính.
6. Gộp ba thao tác trong một `ModificationItem[]`, cố ý chọn một giá trị cần xóa không tồn tại. Kiểm tra **không có thay đổi một phần** ở các thuộc tính khác.
7. Thử xóa `sn`, ghi nhận lỗi schema; thử sửa với reader account và phân biệt lỗi ACL.
8. Thử một UID chứa ký tự cần escape DN, sử dụng `LdapNameBuilder` thay vì nối chuỗi.
9. Dùng LDAPS có xác minh chứng chỉ, không ghi password trong code/log và kiểm tra hành vi khi thao tác bị timeout.
10. Ghi báo cáo về sự khác nhau giữa ADD, REPLACE, REMOVE và khi nào nên dùng Modify DN thay vì Modify.

### Câu hỏi tự kiểm tra

1. Khác biệt chính giữa `ADD_ATTRIBUTE` và `REPLACE_ATTRIBUTE` với một thuộc tính đa trị là gì?
2. `new BasicAttribute("description", "onboarding")` và `new BasicAttribute("description")` tạo ra hai yêu cầu REMOVE khác nhau thế nào?
3. Vì sao `ModificationItem[]` có thứ tự và một request nhiều sửa đổi được coi là nguyên tử trên một entry?
4. Tại sao ba lời gọi `modifyAttributes` liên tiếp không phải transaction nhiều bước?
5. Khi ContextSource có base `dc=example,dc=org`, DN nào nên đưa vào template để sửa `uid=alice` trong `ou=people`?
6. Vì sao không nên xóa `sn` của entry `inetOrgPerson`, hoặc sửa `uid` đang tham gia RDN bằng Modify thông thường?
7. Nếu retry một thao tác ADD sau timeout, tại sao có thể nhận lỗi trùng giá trị?
8. Vì sao kết nối TLS hợp lệ không chứng minh tài khoản có quyền sửa entry?

## 13. Tổng kết

`LdapTemplate.modifyAttributes(Name, ModificationItem[])` là API cốt lõi để **sửa thuộc tính của một entry LDAP đã tồn tại**. `ModificationItem` kết hợp `BasicAttribute` với ba mã thao tác JNDI: **ADD** để thêm thuộc tính/giá trị, **REPLACE** để thay tập giá trị, **REMOVE** để xóa một giá trị hoặc toàn bộ thuộc tính. Một yêu cầu LDAP Modify áp dụng danh sách sửa đổi **theo thứ tự và nguyên tử trên cùng entry**, nhưng không tự tạo transaction bao trùm nhiều request hoặc hệ thống khác. Khi dùng Spring LDAP, hãy dựng DN bằng `LdapNameBuilder`, hiểu base của `ContextSource`, kiểm tra schema, ACL, giá trị đa trị và kết quả đọc lại. Kết hợp LDAPS/StartTLS được xác minh, quyền tối thiểu, xử lý lỗi và kiểm thử thực tế giúp cập nhật LDAP chính xác, an toàn và có thể bảo trì.
