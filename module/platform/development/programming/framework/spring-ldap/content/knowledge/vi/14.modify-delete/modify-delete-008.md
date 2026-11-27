# Đọc lại entry sau thay đổi để xác nhận trong Spring LDAP

Trong Spring LDAP, một lời gọi cập nhật như `LdapTemplate.modifyAttributes(...)` hoặc xóa như `LdapTemplate.unbind(...)` thường trả về `void`. Nếu lời gọi không ném ngoại lệ, ứng dụng biết rằng **máy chủ đã xử lý yêu cầu thành công ở mức giao thức**. Tuy nhiên, đôi khi nghiệp vụ còn yêu cầu chứng minh **trạng thái entry đang được đọc** thực sự khớp với trạng thái mong muốn: email mới đã có mặt, số điện thoại cũ đã bị thay, thuộc tính không còn, hoặc DN đã bị xóa.

Kỹ thuật **read-after-write verification** giải quyết nhu cầu đó: ngay sau một thao tác ghi, đọc lại entry bằng DN, lấy đúng các thuộc tính liên quan, so sánh kết quả với điều kiện cần đạt và xử lý nếu khác biệt.

Đây là bước kiểm chứng bổ sung hữu ích khi xây dựng chức năng quản trị danh bạ, đồng bộ hồ sơ nhân sự hoặc kiểm thử LDAP. Nó **không thay thế** kiểm tra lỗi khi ghi, kiểm soát đồng thời hay bảo đảm nhất quán giữa các bản sao của máy chủ LDAP.

## 1. Xác định điều cần xác nhận

Giả sử ứng dụng quản lý entry:

~~~ldif
dn: uid=an,ou=people,dc=example,dc=org
objectClass: inetOrgPerson
cn: An Nguyen
sn: Nguyen
uid: an
mail: an.work@example.org
mail: an.personal@example.org
telephoneNumber: +84-28-1111
description: Active
~~~

Tùy thao tác, điều kiện xác nhận sẽ khác nhau:

| Thao tác đã thực hiện | Điều kiện đọc lại cần kiểm tra | Điều không nên kết luận chỉ từ kết quả |
| --- | --- | --- |
| `ADD_ATTRIBUTE` thêm email | Tập `mail` chứa email vừa thêm | Có email đó không chứng minh duy nhất lời gọi hiện tại đã tạo ra nó |
| `REPLACE_ATTRIBUTE` thay số điện thoại | Tập `telephoneNumber` **bằng** tập số mong muốn | Chỉ kiểm tra `contains` sẽ bỏ sót số cũ còn tồn tại |
| `REMOVE_ATTRIBUTE` xóa một email | Tập `mail` **không chứa** email bị xóa; có thể kiểm tra email khác vẫn còn | Vắng một giá trị không có nghĩa cả thuộc tính đã bị xóa |
| `REMOVE_ATTRIBUTE` xóa cả `description` | Thuộc tính `description` không được trả về trong lần đọc phù hợp | Thuộc tính không được trả về cũng có thể do quyền đọc hoặc danh sách thuộc tính được yêu cầu |
| `unbind` xóa entry | Lookup **trực tiếp đúng DN** nhận lỗi không tìm thấy entry | Lỗi mạng, quyền hoặc referral không chứng minh entry đã bị xóa |
| `rename` đổi DN | DN mới tồn tại, DN cũ không còn; kiểm tra thêm định danh bất biến nếu cần | Chỉ thấy DN mới tồn tại chưa xác nhận đó là đúng entry vừa chuyển |

Với thuộc tính đa trị, LDAP không bảo đảm thứ tự giá trị; so sánh như tập hợp (set) thay vì so vị trí trong mảng. Với thuộc tính đơn trị, so sánh giá trị theo quy tắc của schema. Ngoài ra, LDAP có các **matching rule** khác nhau (ví dụ không phân biệt chữ hoa/thường) nên việc so sánh chuỗi Java cần phù hợp với kiểu dữ liệu của từng thuộc tính.

## 2. Luồng read-after-write đúng

~~~mermaid
flowchart TD
    A["Chuẩn bị DN và trạng thái mong muốn"] --> B["Gọi thao tác ghi lên LDAP"]
    B --> C{"Ghi có báo lỗi?"}
    C -->|Có| D["Phân loại lỗi ghi, không kết luận thành công"]
    C -->|Không| E["Lookup DN và các thuộc tính cần xác nhận"]
    E --> F{"Đọc thành công?"}
    F -->|Không| G["Phân biệt entry vắng mặt với lỗi kết nối, quyền, referral"]
    F -->|Có| H["So sánh giá trị thực tế với điều kiện mong muốn"]
    H --> I{"Khớp?"}
    I -->|Có| J["Trạng thái vừa quan sát đã được xác nhận"]
    I -->|Không| K["Ghi nhận mismatch, kiểm tra replication/ghi đồng thời"]
~~~

Quy trình thực tế gồm những bước sau:

1. **Giữ lại DN được ghi.** Nếu `ContextSource` cấu hình base DN `dc=example,dc=org`, dùng DN tương đối `uid=an,ou=people` ở cả bước ghi và đọc. Không ghép lại base DN hai lần.
2. **Xác định tiêu chí trước khi ghi.** Với REPLACE, lưu **đầy đủ tập giá trị mong muốn**; với REMOVE, chỉ rõ giá trị cần vắng mặt hay toàn bộ thuộc tính cần biến mất.
3. **Ghi và kiểm tra ngoại lệ.** Nếu thao tác ghi báo lỗi, giải quyết lỗi đó trước; không đọc rồi suy luận rằng ghi đã thành công.
4. **Đọc cùng entry bằng `lookup`.** Yêu cầu đúng các thuộc tính cần xác nhận thay vì tải toàn bộ entry, đặc biệt nếu entry chứa thuộc tính nhạy cảm.
5. **So sánh theo loại thuộc tính.** Xét thuộc tính đơn trị/đa trị, các giá trị có thể thiếu, luật chuẩn hóa và thay đổi đồng thời.
6. **Báo kết quả theo hai trạng thái riêng.** “Thao tác ghi thành công” và “Giá trị đọc lại khớp” là hai quan sát khác nhau. Nếu verify thất bại, thao tác ghi **không tự được rollback**.

## 3. Đọc đúng thuộc tính bằng LdapTemplate.lookup

`LdapTemplate` có các overload phù hợp:

~~~java
<T> T lookup(Name dn, String[] attributes, AttributesMapper<T> mapper);
<T> T lookup(Name dn, String[] attributes, ContextMapper<T> mapper);
~~~

Tham số `attributes` giới hạn những tên thuộc tính cần trả về. `AttributesMapper` nhận `javax.naming.directory.Attributes`, còn `ContextMapper` thường làm việc với `DirContextAdapter`. Nếu chỉ cần các giá trị để so sánh, `AttributesMapper` giúp mã ngắn và dễ kiểm soát dữ liệu đọc.

Ví dụ đọc tập `mail` bằng `AttributesMapper`:

~~~java
import java.util.HashSet;
import java.util.Set;
import javax.naming.Name;
import javax.naming.directory.Attribute;

import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;

public class MailReader {

    private final LdapTemplate ldapTemplate;

    public MailReader(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public Set<String> readMail(Name dn) {
        return ldapTemplate.lookup(
            dn,
            new String[] {"mail"},
            (AttributesMapper<Set<String>>) attributes -> {
                Attribute mail = attributes.get("mail");
                if (mail == null) {
                    return Set.of();
                }

                Set<String> result = new HashSet<>();
                for (int i = 0; i < mail.size(); i++) {
                    result.add((String) mail.get(i));
                }
                return Set.copyOf(result);
            }
        );
    }
}
~~~

Mã trên giả định schema của `mail` trả về các giá trị kiểu `String`. Với thuộc tính nhị phân, JNDI có thể trả về `byte[]`; khi đó phải dùng hàm so sánh dữ liệu nhị phân phù hợp, không ép kiểu thành chuỗi.

Khi `mail` không xuất hiện trong phản hồi, ví dụ biểu diễn kết quả bằng tập rỗng. **Điều đó chỉ cho thấy thuộc tính không được trả về trong lần lookup này**; để diễn giải là thuộc tính đã biến mất, còn phải bảo đảm tên thuộc tính được yêu cầu đúng, tài khoản có quyền đọc và máy chủ đang đọc đúng nơi.

## 4. Ví dụ hoàn chỉnh: thay đổi rồi kiểm tra

Service sau minh họa xác nhận ba kiểu sửa đổi và xóa entry. Để tập trung vào quá trình xác nhận, ví dụ sử dụng trực tiếp `ModificationItem`. Giả định `ContextSource` đã có base DN `dc=example,dc=org`, người dùng có DN tương đối `uid=<uid>,ou=people`, và tài khoản bind có đủ quyền đọc/ghi trên những thuộc tính được kiểm tra.

~~~java
import java.util.Collection;
import java.util.HashSet;
import java.util.Set;
import javax.naming.Name;
import javax.naming.directory.Attribute;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;

import org.springframework.ldap.NameNotFoundException;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;
import org.springframework.stereotype.Service;

@Service
public class VerifiedDirectoryUpdates {

    private final LdapTemplate ldapTemplate;

    public VerifiedDirectoryUpdates(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    // ADD: sau khi ghi, email mới phải nằm trong tập mail.
    public boolean addEmailAndVerify(String uid, String email) {
        Name dn = userDn(uid);
        ldapTemplate.modifyAttributes(dn, new ModificationItem[] {
            new ModificationItem(
                DirContext.ADD_ATTRIBUTE,
                new BasicAttribute("mail", required(email, "email"))
            )
        });
        return readMail(dn).contains(email);
    }

    // REPLACE: sau khi ghi, tập mail phải bằng đúng tập mong muốn.
    public boolean replaceEmailsAndVerify(
            String uid, Collection<String> newEmails) {
        if (newEmails == null || newEmails.isEmpty()) {
            throw new IllegalArgumentException("Cần ít nhất một email");
        }

        Set<String> expected = new HashSet<>();
        for (String email : newEmails) {
            expected.add(required(email, "email"));
        }

        Attribute replacement = new BasicAttribute("mail");
        for (String email : expected) {
            replacement.add(email);
        }

        Name dn = userDn(uid);
        ldapTemplate.modifyAttributes(dn, new ModificationItem[] {
            new ModificationItem(DirContext.REPLACE_ATTRIBUTE, replacement)
        });
        return readMail(dn).equals(expected);
    }

    // REMOVE một giá trị: email đó phải vắng mặt sau ghi.
    public boolean removeEmailAndVerify(String uid, String email) {
        Name dn = userDn(uid);
        ldapTemplate.modifyAttributes(dn, new ModificationItem[] {
            new ModificationItem(
                DirContext.REMOVE_ATTRIBUTE,
                new BasicAttribute("mail", required(email, "email"))
            )
        });
        return !readMail(dn).contains(email);
    }

    // REMOVE cả thuộc tính: description không còn trong kết quả đọc.
    public boolean removeDescriptionAndVerify(String uid) {
        Name dn = userDn(uid);
        ldapTemplate.modifyAttributes(dn, new ModificationItem[] {
            new ModificationItem(
                DirContext.REMOVE_ATTRIBUTE,
                new BasicAttribute("description")
            )
        });
        return ldapTemplate.lookup(
            dn,
            new String[] {"description"},
            (AttributesMapper<Boolean>) attributes ->
                attributes.get("description") == null
        );
    }

    // DELETE entry: lookup đúng DN phải trả về NameNotFoundException.
    public boolean deleteAndVerify(String uid) {
        Name dn = userDn(uid);
        ldapTemplate.unbind(dn);
        try {
            ldapTemplate.lookup(
                dn,
                new String[] {"objectClass"},
                (AttributesMapper<Boolean>) attributes -> true
            );
            return false; // Entry vẫn hiện diện trong lần đọc này.
        } catch (NameNotFoundException notFound) {
            return true;  // DN không tồn tại trong lần đọc này.
        }
    }

    private Set<String> readMail(Name dn) {
        return ldapTemplate.lookup(
            dn,
            new String[] {"mail"},
            (AttributesMapper<Set<String>>) attributes -> {
                Attribute attribute = attributes.get("mail");
                if (attribute == null) {
                    return Set.of();
                }
                Set<String> result = new HashSet<>();
                for (int i = 0; i < attribute.size(); i++) {
                    result.add((String) attribute.get(i));
                }
                return Set.copyOf(result);
            }
        );
    }

    private static Name userDn(String uid) {
        return LdapNameBuilder.newInstance()
            .add("ou", "people")
            .add("uid", required(uid, "uid"))
            .build();
    }

    private static String required(String value, String name) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(name + " không được rỗng");
        }
        return value;
    }
}
~~~

Cách gọi:

~~~java
boolean added = verifiedDirectoryUpdates.addEmailAndVerify(
    "an", "an.new@example.org"
);

boolean replaced = verifiedDirectoryUpdates.replaceEmailsAndVerify(
    "an",
    java.util.List.of("an.work@example.org", "an.team@example.org")
);

boolean removed = verifiedDirectoryUpdates.removeEmailAndVerify(
    "an", "an.team@example.org"
);

boolean descriptionGone =
    verifiedDirectoryUpdates.removeDescriptionAndVerify("an");
~~~

Mỗi phương thức chỉ trả `true` khi kết quả được đọc từ LDAP đáp ứng điều kiện tương ứng. Phương thức có thể **ném ngoại lệ** nếu thao tác ghi hoặc đọc lỗi; giá trị `false` biểu thị thao tác ghi không báo lỗi nhưng kết quả đọc **chưa khớp điều kiện**.

Ví dụ `deleteAndVerify` có thể được gọi cho **entry thử nghiệm**. Không gọi phương thức xóa entry thật chỉ để kiểm tra; cần có yêu cầu xóa thực sự. Ngoài ra, không nên diễn giải `NameNotFoundException` của thao tác `unbind` là xác nhận xóa thành công: lỗi đó phát sinh **khi ghi** và có thể cho biết entry vốn không tồn tại. Ở ví dụ, chỉ ngoại lệ `NameNotFoundException` từ **bước lookup sau khi unbind đã hoàn thành** mới được xem là quan sát entry vắng mặt.

**Giới hạn của ví dụ:** phép so sánh `Set<String>.equals` yêu cầu các chuỗi giống hệt nhau. Với thuộc tính có matching rule không phân biệt chữ hoa/thường hoặc server chuẩn hóa giá trị, ứng dụng thực tế phải xác định cách so sánh theo schema và yêu cầu nghiệp vụ. Hơn nữa, `Set` chỉ phù hợp với thuộc tính đa trị không phụ thuộc thứ tự; các thuộc tính đa trị của LDAP vốn không có thứ tự xác định.

## 5. Kiểm tra cả trạng thái không được thay đổi

Nếu yêu cầu là “bổ sung email mới và **giữ tất cả email cũ**”, chỉ kiểm tra email mới có tồn tại là chưa đủ. Cần đọc **trước khi ghi** để có mốc so sánh:

~~~java
Name dn = LdapNameBuilder.newInstance()
    .add("ou", "people")
    .add("uid", "an")
    .build();

Set<String> before = mailReader.readMail(dn);

ldapTemplate.modifyAttributes(dn, new ModificationItem[] {
    new ModificationItem(
        DirContext.ADD_ATTRIBUTE,
        new BasicAttribute("mail", "an.new@example.org")
    )
});

Set<String> after = mailReader.readMail(dn);

Set<String> expected = new java.util.HashSet<>(before);
expected.add("an.new@example.org");

boolean preservedOldAndAddedNew = after.equals(expected);
~~~

Kiểu kiểm tra này mạnh hơn so với `after.contains("an.new@example.org")`, vì nó còn phát hiện mất hoặc phát sinh bất thường ở các email khác. Tương tự:

- **REMOVE một giá trị:** kỳ vọng `after = before - {giá trị đã xóa}`, nếu nghiệp vụ yêu cầu các giá trị còn lại giữ nguyên.
- **REPLACE:** kỳ vọng `after = toàn bộ tập giá trị mới`, không so từng phần tử theo chỉ số.
- **Thay một thuộc tính đơn trị:** kiểm tra giá trị mới và, nếu cần, xác nhận giá trị cũ không còn.

Tuy nhiên, **đọc trước rồi ghi rồi đọc sau không phải là một giao dịch nguyên tử**. Tiến trình khác có thể sửa entry trong khoảng giữa các lần gọi. Nếu cần bảo đảm chống ghi đè, hãy sử dụng cơ chế kiểm soát đồng thời được hệ thống LDAP của bạn hỗ trợ (chẳng hạn assertion control theo RFC 4528, với hỗ trợ cụ thể của máy chủ và client), hoặc thiết kế luồng đồng bộ tại ứng dụng.

## 6. Xác nhận xóa entry và đổi DN

### 6.1. Xóa entry: phân biệt ba kết quả

Sau `unbind(dn)`, lookup có thể:

| Kết quả lookup | Diễn giải phù hợp |
| --- | --- |
| Trả về entry | DN vẫn nhìn thấy tại điểm đọc này; verify xóa **thất bại** |
| Ném `org.springframework.ldap.NameNotFoundException` | DN không còn tại điểm đọc này; verify xóa **thành công theo quan sát** |
| Ném lỗi timeout, kết nối, xác thực, thiếu quyền, referral... | **Không xác định được**; phải xử lý lỗi, không quy thành “đã xóa” |

Dùng `lookup` theo DN trực tiếp để xác nhận sự hiện diện của **một entry cụ thể**. Tìm kiếm bằng filter có thể không trả về kết quả vì sai search base, filter, scope hoặc quyền đọc; danh sách tìm kiếm trống không tự chứng minh entry đã bị xóa.

### 6.2. Đổi DN: kiểm tra cả DN cũ và mới

Khi thao tác `rename(oldDn, newDn)` đã thành công, có thể lookup tại hai DN:

~~~java
// Hàm kiểm tra sự hiện diện (thực hiện lookup trực tiếp theo DN):
boolean exists(LdapTemplate template, Name dn) {
    try {
        return template.lookup(
            dn,
            new String[] {"objectClass"},
            (AttributesMapper<Boolean>) attrs -> true
        );
    } catch (NameNotFoundException notFound) {
        return false;
    }
}

// Ví dụ logic sau thao tác rename:
ldapTemplate.rename(oldDn, newDn);
boolean verified = exists(ldapTemplate, newDn)
                && !exists(ldapTemplate, oldDn);
~~~

Hai phép kiểm tra độc lập **không** tự chứng minh entry ở DN mới chính là entry cũ nếu có thay đổi đồng thời. Với hệ thống hỗ trợ thuộc tính định danh ổn định (ví dụ `entryUUID` ở máy chủ có cung cấp), có thể đọc ID trước và sau để đối chiếu. Thuộc tính vận hành như `entryUUID` thường phải **yêu cầu rõ tên** và cần quyền đọc thích hợp; không phải LDAP server nào cũng cung cấp cùng một thuộc tính.

## 7. Độ nhất quán của lần đọc và lỗi thực tế

### 7.1. Đọc đúng máy chủ

Read-after-write dễ gây hiểu nhầm khi ứng dụng kết nối một cụm LDAP có nhiều máy chủ:

~~~text
Ứng dụng -- modify --> LDAP primary
      |
      +---- lookup ----> LDAP replica (chưa kịp nhận dữ liệu mới)
~~~

Lệnh ghi có thể thành công trên node nhận ghi, nhưng lần đọc tiếp theo lại truy cập replica còn dữ liệu cũ do **replication lag**. Ngược lại, đọc thấy đúng giá trị trên một node không có nghĩa toàn bộ replica đã đồng bộ.

Nếu nghiệp vụ cần xác nhận ngay, hãy xác định endpoint và chính sách đọc/ghi của `ContextSource`, bộ cân bằng tải, cơ chế failover và cách máy chủ LDAP bảo đảm nhất quán. Khi chỉ cần nhất quán cuối cùng (eventual consistency), có thể thử đọc lại có giới hạn và timeout cụ thể, nhưng chỉ sau khi đã phân loại lỗi; không nên tạo vòng retry vô hạn hoặc ghi lại cùng yêu cầu một cách mù quáng.

### 7.2. Phân loại lỗi thay vì suy diễn

| Biểu hiện | Nguyên nhân có thể | Hành động |
| --- | --- | --- |
| Ghi thành công, lookup vẫn thấy giá trị cũ | Replica chưa đồng bộ; request đọc đi đến node khác; ghi đồng thời | Xác minh routing, đọc từ nguồn phù hợp, so thời điểm/định danh |
| Lookup không trả thuộc tính | Thuộc tính vắng; không được yêu cầu; ACL ẩn; thuộc tính vận hành | Xác minh tên thuộc tính, quyền đọc và thuộc tính requested |
| Giá trị trùng nhưng khác chữ hoa/thường | Matching rule/schema hoặc chuẩn hóa dữ liệu | So sánh theo quy tắc của loại thuộc tính |
| Tập email có đúng các giá trị nhưng thứ tự khác | LDAP không định nghĩa thứ tự giá trị | So sánh bằng set, không so mảng theo vị trí |
| Lookup ném `NameNotFoundException` sau modify | DN không còn hoặc không khớp base DN; có thể bị đổi/xóa đồng thời | Kiểm tra DN, cấu hình base DN và thay đổi đồng thời |
| Lookup lỗi quyền hay kết nối | Tài khoản đọc thiếu ACL; server lỗi; TLS bị gián đoạn | Giữ trạng thái **chưa xác minh**, phân loại lỗi và xử lý |
| Verify trả `false` | Trạng thái hiện tại chưa khớp; có thể do replica hay cạnh tranh cập nhật | Ghi nhận mismatch; không tự động kết luận write rollback |

Nếu cần log hoặc metrics, nên ghi **DN đã được che thông tin nhạy cảm khi cần**, tên phép sửa đổi, tên thuộc tính, kết quả ghi, kết quả xác nhận, thời gian và máy chủ xử lý. Tránh log toàn bộ giá trị `userPassword`, token, dữ liệu cá nhân hoặc bản sao đầy đủ của entry.

## 8. Thiết kế kiểm thử tích hợp

Kiểm thử read-after-write nên chạy trên LDAP test server có schema/ACL tương tự môi trường mục tiêu. Mỗi ca có thể:

1. Khởi tạo entry thử nghiệm với DN và thuộc tính đã biết.
2. Thực hiện đúng một thao tác cập nhật/xóa.
3. Lookup trực tiếp, chỉ lấy những thuộc tính cần kiểm tra.
4. So sánh với trạng thái mong muốn và kiểm tra cả giá trị cần giữ.
5. Dọn dữ liệu thử nghiệm, bảo đảm các ca độc lập.

Ví dụ các ca quan trọng:

| Dữ liệu đầu vào | Thao tác | Điều kiện phải khớp khi đọc lại |
| --- | --- | --- |
| `mail={a@ex.org,b@ex.org}` | ADD `c@ex.org` | `{a,b,c}` (so theo tập, dùng giá trị đầy đủ) |
| `mail={a@ex.org,b@ex.org}` | REPLACE `{d@ex.org}` | Chỉ còn `{d@ex.org}` |
| `mail={a@ex.org,b@ex.org}` | REMOVE `a@ex.org` | Chỉ còn `{b@ex.org}` |
| `description=Active` | REMOVE toàn bộ `description` | Thuộc tính không còn được trả về |
| Entry `uid=an,...` tồn tại | `unbind` | Lookup `uid=an,...` ném `NameNotFoundException` |
| Entry tồn tại | Thao tác ghi bị ACL từ chối | Bước ghi ném ngoại lệ, bước xác nhận không bị báo thành công |

Trong kiểm thử với nhiều LDAP node, có thể tạo thêm ca đọc từ replica để quan sát độ trễ đồng bộ, nhưng tiêu chí thành công phải được định nghĩa theo **node và chính sách nhất quán** mà ứng dụng thực sự cam kết. Không khẳng định read-after-write luôn cho kết quả tức thời trên mọi replica.

## 9. Bài tập vận dụng

Entry thử nghiệm có `mail={an.work@example.org,an.personal@example.org}` và `telephoneNumber={111,222}`. Hãy lựa chọn điều kiện xác nhận phù hợp:

1. Sau khi thêm `an.alt@example.org`, điều kiện nào chứng minh **toàn bộ email cũ vẫn được bảo toàn**?
2. Sau khi REPLACE điện thoại bằng `333`, vì sao chỉ kiểm tra `contains("333")` chưa đủ?
3. Sau khi REMOVE `an.personal@example.org`, làm sao chứng minh `an.work@example.org` vẫn còn?
4. Sau khi xóa entry, vì sao `CommunicationException` của lookup không được xem là “đã xóa”?
5. Nếu lệnh modify thành công trên primary nhưng lookup trả dữ liệu cũ từ replica, đâu là cách diễn giải kết quả an toàn?

**Gợi ý đáp án:** (1) so sánh tập email sau ghi với tập trước ghi cộng email mới; (2) còn có thể tồn tại số cũ; (3) đọc và kiểm tra tập kết quả còn đúng giá trị giữ lại; (4) lỗi kết nối không cung cấp trạng thái entry; (5) ghi đã thành công tại điểm ghi nhưng quan sát từ điểm đọc chưa được xác nhận, cần xem lại routing/replication và thời điểm đọc.

## 10. Ghi nhớ

- **Ghi thành công** và **đọc lại khớp trạng thái mong muốn** là hai điều kiện khác nhau. `LdapTemplate.modifyAttributes` trả `void` không đồng nghĩa ứng dụng đã kiểm chứng độc lập trạng thái đọc.
- Đọc bằng `LdapTemplate.lookup(dn, requestedAttributes, mapper)`, so sánh giá trị thực tế với điều kiện của từng phép ADD, REPLACE hoặc REMOVE.
- Với thuộc tính đa trị, **so tập giá trị**; với xóa entry, cần thấy **`NameNotFoundException` từ lookup sau ghi**, đồng thời không nuốt các ngoại lệ khác.
- Một lần readback là một **quan sát tại điểm đọc**. Quyền truy cập, replication, cân bằng tải và cập nhật đồng thời quyết định độ mạnh của kết luận.
- Khi xác nhận không đạt, **không tự động coi ghi đã rollback** và không tự lặp lệnh ghi. Cần phân biệt lỗi ghi, lỗi đọc và trạng thái không khớp.

### Tài liệu tham khảo

- [Spring LDAP — LdapTemplate API (lookup, modifyAttributes, unbind, rename)](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/LdapTemplate.html)
- [Spring LDAP — Basic Usage](https://docs.spring.io/spring-ldap/reference/spring-ldap-basic-usage.html)
- [Spring LDAP — FAQ: Operational Attributes](https://docs.spring.io/spring-ldap/reference/faq.html)
- [Spring LDAP — NameNotFoundException](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/NameNotFoundException.html)
- [RFC 4511 — LDAP: The Protocol (Search, Modify, Delete)](https://www.rfc-editor.org/rfc/rfc4511)
- [RFC 4528 — LDAP Assertion Control](https://www.rfc-editor.org/rfc/rfc4528)
