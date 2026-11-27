# Kiểm tra conflict khi DN đích đã tồn tại trong Spring LDAP

Trong một hệ thống quản lý người dùng hoặc nhóm bằng **Spring LDAP**, đổi tên entry thường có nghĩa là đổi **Distinguished Name (DN)**. Điều gì xảy ra nếu DN mới đã được một entry khác sử dụng? Chẳng hạn, ứng dụng muốn đổi `cn=legacy-readers` thành `cn=platform-readers`, nhưng nhóm `platform-readers` đã tồn tại. Đây là **xung đột DN đích (destination DN conflict)**: LDAP không được ghi đè tùy tiện lên entry ở tên đích.

Bài học thuộc phần **Rename và move**, tập trung vào cách phát hiện xung đột trước thao tác, xử lý lỗi thực tế từ `LdapTemplate.rename()`, hiểu giới hạn của bước kiểm tra trước và thiết kế phản hồi an toàn khi nhiều yêu cầu chạy đồng thời. Các ví dụ giả định ứng dụng đã cấu hình `ContextSource`, quyền truy cập LDAP phù hợp và kết nối bảo mật bằng LDAPS hoặc StartTLS theo môi trường triển khai.

## 1. Hiểu rõ DN đích và điều kiện gây conflict

Giả sử directory có hai entry:

```ldif
dn: cn=legacy-readers,ou=groups,dc=example,dc=org
objectClass: top
objectClass: groupOfNames
cn: legacy-readers
member: uid=lan,ou=people,dc=example,dc=org

dn: cn=platform-readers,ou=groups,dc=example,dc=org
objectClass: top
objectClass: groupOfNames
cn: platform-readers
member: uid=minh,ou=people,dc=example,dc=org
```

Ứng dụng yêu cầu:

```text
DN nguồn: cn=legacy-readers,ou=groups,dc=example,dc=org
DN đích : cn=platform-readers,ou=groups,dc=example,dc=org
```

Trong trường hợp này, `cn=platform-readers,ou=groups,dc=example,dc=org` đã định danh một entry đang tồn tại. Máy chủ LDAP phải từ chối phép đổi DN nếu kết quả dẫn đến hai entry có cùng DN.

**Conflict được xét theo toàn bộ DN**, không chỉ theo chuỗi `cn`:

| Yêu cầu | Có xung đột DN đích không? | Giải thích |
| --- | --- | --- |
| Đổi thành `cn=platform-readers,ou=groups,...` khi DN này đã tồn tại | **Có** | Hai entry sẽ trùng cùng DN đầy đủ. |
| Đổi thành `cn=platform-readers,ou=archive,...` khi DN đó chưa tồn tại | **Không vì trùng DN** | RDN giống nhau nhưng khác parent; thao tác move có thể còn bị chặn bởi ACL, schema hoặc chính sách khác. |
| Đổi `legacy-readers` thành chính `legacy-readers` | **Không phải conflict với entry khác** | DN nguồn và DN đích giống nhau; nên xem là yêu cầu không thay đổi. |
| Đổi thành DN chưa tồn tại, nhưng không có quyền đổi tên | **Không phải conflict** | Đây là lỗi quyền truy cập, phải xử lý riêng. |

Việc tên `cn` bị trùng ở các nhánh khác nhau không đồng nghĩa với việc trùng DN. Một số ứng dụng có **quy tắc nghiệp vụ riêng** yêu cầu tên nhóm duy nhất trên toàn directory; khi đó cần kiểm tra bổ sung ở phạm vi nghiệp vụ. LDAP chỉ áp đặt tính duy nhất của **DN đầy đủ**.

## 2. Phản hồi của LDAP khi DN đích đã tồn tại

`LdapTemplate.rename(oldDn, newDn)` gọi thao tác đổi DN của directory (LDAP **Modify DN**). Theo RFC 4511, máy chủ có thể trả về kết quả:

```text
LDAP resultCode: 68
LDAP result name: entryAlreadyExists
Ý nghĩa: entry tại DN đích đã tồn tại
```

Trên đường đi từ máy chủ tới ứng dụng Java:

1. LDAP server đánh giá yêu cầu đổi DN và trả về `entryAlreadyExists (68)` nếu đích đã có entry.
2. Nhà cung cấp LDAP của JNDI thường chuyển mã 68 thành `javax.naming.NameAlreadyBoundException`.
3. Spring LDAP chuyển ngoại lệ JNDI tương ứng thành `org.springframework.ldap.NameAlreadyBoundException` (runtime exception), cho phép ứng dụng bắt riêng xung đột.

Như vậy, khi gặp mã 68, **không có ý nghĩa là entry nguồn đã đổi tên thành công**; cần báo tên đích đã được sử dụng. Cũng không nên tự `unbind()` hoặc `rebind()` DN đích như một cách “sửa conflict”: các thao tác đó có thể xóa hay thay thế entry không thuộc về yêu cầu rename.

> **Phân biệt ngoại lệ:** Tài liệu Java và RFC ánh xạ `entryAlreadyExists (68)` với `NameAlreadyBoundException`; trong Javadoc của `LdapOperations.rename` còn có mô tả `ContextNotEmptyException` khi DN mới đã được bind. Tuy nhiên `ContextNotEmptyException` cũng gắn với tình huống *non-leaf* (ví dụ server từ chối thao tác với entry có con), nên **không tự động quy mọi `ContextNotEmptyException` thành trùng DN**. Hãy kiểm tra phản hồi thực tế từ server hoặc xác minh DN đích trước khi phân loại lỗi.

Những lỗi sau cần được phân biệt:

| Tình huống | Mã kết quả LDAP thường gặp | Hướng xử lý |
| --- | --- | --- |
| DN đích đã tồn tại | `entryAlreadyExists (68)` | Báo conflict, đề nghị chọn DN khác. |
| DN nguồn hoặc parent yêu cầu không tồn tại | `noSuchObject (32)` | Kiểm tra DN nguồn, parent và base DN. |
| Tài khoản không đủ quyền | `insufficientAccessRights (50)` | Từ chối và kiểm tra ACL; không xem là conflict. |
| Tên vi phạm chính sách đặt tên | `namingViolation (64)` | Kiểm tra RDN, schema và chính sách server. |
| Máy chủ không hỗ trợ/cấm thao tác trong hoàn cảnh đó | Có thể là `unwillingToPerform (53)` hoặc mã khác | Xem chẩn đoán của server, không gộp thành lỗi trùng tên. |

Nhà cung cấp LDAP và máy chủ có thể trả thông điệp hoặc ngoại lệ khác nhau. Khi phân loại lỗi, ưu tiên **mã kết quả và loại ngoại lệ đáng tin cậy**, tránh kiểm tra thông điệp lỗi bằng chuỗi như `contains("already exists")` vì ngôn ngữ hoặc nội dung thông điệp có thể thay đổi.

## 3. Kiểm tra DN đích trước khi rename

Kiểm tra trước (preflight check) giúp giao diện thông báo sớm rằng tên được chọn đã được dùng. Với `LdapTemplate`, có thể lookup trực tiếp DN đích:

```java
import javax.naming.Name;

import org.springframework.ldap.NameNotFoundException;
import org.springframework.ldap.core.LdapTemplate;

public final class LdapDnChecker {
    private final LdapTemplate ldapTemplate;

    public LdapDnChecker(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public boolean isVisibleAt(Name dn) {
        try {
            ldapTemplate.lookup(dn);
            return true;
        } catch (NameNotFoundException ex) {
            return false;
        }
    }
}
```

Tên phương thức `isVisibleAt` có chủ ý: lookup thành công chứng minh entry **có thể được tìm thấy với quyền và truy vấn hiện tại**. Khi lookup báo `NameNotFoundException`, ở một số directory cấu hình ACL che giấu entry, kết quả này chưa bảo đảm tên thực sự có thể được dùng. Các ngoại lệ khác như mất kết nối, xác thực không hợp lệ hoặc thiếu quyền phải được truyền lên để xử lý, không được coi là “DN đích chưa tồn tại”.

Để bảo đảm check đúng entry, hãy tạo **DN tương đối với base DN đã cấu hình**. Ví dụ `ContextSource` có base `dc=example,dc=org`:

```java
import javax.naming.Name;
import org.springframework.ldap.support.LdapNameBuilder;

Name newDn = LdapNameBuilder.newInstance()
        .add("ou", "groups")
        .add("cn", "platform-readers")
        .build();

boolean visible = new LdapDnChecker(ldapTemplate).isVisibleAt(newDn);
```

Giá trị `newDn` tương ứng với DN đầy đủ `cn=platform-readers,ou=groups,dc=example,dc=org`. `LdapNameBuilder` xử lý cú pháp và escape các ký tự đặc biệt trong giá trị tên, tránh nối chuỗi DN trực tiếp từ input người dùng.

**Giới hạn quan trọng:** Một lần kiểm tra `isVisibleAt(newDn) == false` không bảo đảm `rename` sẽ thành công. Giữa hai lệnh, một request khác có thể tạo hoặc đổi tên entry tới cùng DN đích.

## 4. Xử lý conflict đúng tại thao tác rename

Hãy xây một service thực hiện hai tầng kiểm tra:

1. **Kiểm tra trước** để cung cấp phản hồi sớm khi DN đích đang hiện diện.
2. **Bắt `NameAlreadyBoundException` ngay khi rename** vì máy chủ mới có quyền quyết định cuối cùng tại thời điểm ghi.

Ví dụ có thể đưa vào dự án Spring đã cấu hình `LdapTemplate`:

```java
import javax.naming.Name;

import org.springframework.ldap.NameAlreadyBoundException;
import org.springframework.ldap.NameNotFoundException;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

public class SafeGroupRenameService {
    public enum RenameResult {
        RENAMED,
        UNCHANGED,
        TARGET_EXISTS
    }

    private final LdapTemplate ldapTemplate;

    public SafeGroupRenameService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public RenameResult renameGroup(String oldCn, String newCn) {
        if (oldCn == null || oldCn.isBlank()
                || newCn == null || newCn.isBlank()) {
            throw new IllegalArgumentException("Tên nhóm không được rỗng");
        }

        Name oldDn = groupDn(oldCn);
        Name newDn = groupDn(newCn);

        // Đổi về cùng DN: không cần gọi máy chủ.
        if (oldDn.equals(newDn)) {
            return RenameResult.UNCHANGED;
        }

        // Hỗ trợ giao diện phát hiện trùng tên sớm.
        if (targetVisible(newDn)) {
            return RenameResult.TARGET_EXISTS;
        }

        try {
            // Quyết định cuối cùng luôn thuộc về LDAP server.
            ldapTemplate.rename(oldDn, newDn);
            return RenameResult.RENAMED;
        } catch (NameAlreadyBoundException ex) {
            // Một request khác có thể đã chiếm DN đích sau bước lookup.
            return RenameResult.TARGET_EXISTS;
        }
    }

    private boolean targetVisible(Name dn) {
        try {
            ldapTemplate.lookup(dn);
            return true;
        } catch (NameNotFoundException ex) {
            return false;
        }
    }

    private Name groupDn(String cn) {
        // Các DN này tương đối với base dc=example,dc=org.
        return LdapNameBuilder.newInstance()
                .add("ou", "groups")
                .add("cn", cn)
                .build();
    }
}
```

Ví dụ gọi:

```java
SafeGroupRenameService service =
        new SafeGroupRenameService(ldapTemplate);

SafeGroupRenameService.RenameResult result =
        service.renameGroup("legacy-readers", "platform-readers");

switch (result) {
    case RENAMED:
        System.out.println("Đã đổi DN thành công");
        break;
    case UNCHANGED:
        System.out.println("DN không thay đổi");
        break;
    case TARGET_EXISTS:
        System.out.println("Tên nhóm đích đã được sử dụng");
        break;
}
```

Mã sử dụng `String.isBlank()` nên cần Java 11+. Đối với phương án chỉ cần **thực hiện rename và phản hồi conflict**, có thể bỏ bước `targetVisible(newDn)` để giảm một round-trip LDAP; khi đó vẫn phải bắt `NameAlreadyBoundException`:

```java
try {
    ldapTemplate.rename(oldDn, newDn);
} catch (NameAlreadyBoundException ex) {
    // Trả về lỗi nghiệp vụ "destination already exists".
}
```

Đoạn rút gọn giả định `oldDn` và `newDn` đã được tạo hợp lệ. Nếu lỗi khác `NameAlreadyBoundException` xảy ra, hãy để nó đi vào cơ chế xử lý lỗi tương ứng; **không trả `TARGET_EXISTS` cho tất cả ngoại lệ**.

## 5. Race condition: kiểm tra xong vẫn có thể conflict

Giả sử hai người quản trị A và B cùng muốn sử dụng DN `cn=platform-readers,ou=groups,...`:

```text
Thời điểm  | Quản trị viên A                  | Quản trị viên B
-----------|---------------------------------|-------------------------------
T1         | Lookup DN đích -> không thấy    |
T2         |                                 | Tạo entry ở DN đích -> thành công
T3         | Gọi rename tới DN đích          |
T4         | Nhận entryAlreadyExists (68)   |
```

Đây là lỗi **time-of-check to time-of-use (TOCTOU)**: trạng thái có thể thay đổi giữa bước đọc và bước ghi. Một phép lookup trước đó không có khả năng “đặt chỗ” tên trong LDAP. Khóa trong bộ nhớ của một instance ứng dụng cũng không chặn được người dùng hoặc ứng dụng khác ghi trực tiếp lên directory.

Do đó:

- Lookup trước phù hợp để cải thiện **trải nghiệm người dùng**, không đủ làm điều kiện bảo toàn nhất quán.
- Lệnh `rename` và kết quả server trả về là **điểm quyết định** tên có được đổi hay không.
- Khi nhận conflict, trả về kết quả rõ ràng; không tự xóa entry ở DN đích hoặc âm thầm chọn tên mới.
- Nếu buộc phải bảo đảm một quy tắc đặt tên chặt hơn phạm vi DN, cần cơ chế phối hợp ở nơi quản lý danh tính/tên nghiệp vụ, đồng thời vẫn xử lý xung đột tại directory.

## 6. Xử lý trường hợp lỗi không rõ ràng và thử lại

Trong hệ thống thực tế, không phải lỗi nào xảy ra khi `rename` cũng xác định được kết quả cuối cùng. Ví dụ, máy chủ có thể đã đổi tên thành công nhưng kết nối bị cắt trước khi ứng dụng nhận phản hồi.

| Quan sát | Có thể kết luận? | Xử lý đề xuất |
| --- | --- | --- |
| `rename` trả về bình thường | Lệnh đã được máy chủ chấp nhận; thành công theo phản hồi API. | Tra cứu DN mới nếu nghiệp vụ cần xác minh trạng thái/thuộc tính. |
| `NameAlreadyBoundException` | Có bằng chứng xung đột DN tại thời điểm thực hiện. | Báo conflict; giữ nguyên entry đích. |
| `NameNotFoundException` | Không đủ để nói DN đích trùng. | Kiểm tra DN nguồn, parent đích và base DN. |
| Lỗi truyền thông hoặc timeout | **Chưa biết** máy chủ đã hoàn thành thao tác hay chưa. | Đọc lại trạng thái khi kết nối ổn định trước khi thử lại. |
| Lookup báo lỗi quyền | Không thể kết luận entry có tồn tại hay không. | Bảo toàn nguyên nhân quyền truy cập, không suy ra DN còn trống. |

Với timeout sau rename, có thể kiểm tra cả `oldDn` và `newDn`:

- **Chỉ DN cũ tìm thấy:** Có khả năng rename chưa diễn ra, nhưng vẫn cần đánh giá các thao tác đồng thời trước khi retry.
- **Chỉ DN mới tìm thấy:** Có thể rename đã thành công; xác minh đây đúng là entry nguồn bằng thuộc tính định danh ổn định nếu server cung cấp (chẳng hạn `entryUUID` trên một số LDAP server hoặc `objectGUID` trên Active Directory).
- **Cả hai DN đều tìm thấy:** Có thể đã có entry khác tại DN đích; không mặc định kết quả là thành công.
- **Không tìm thấy DN nào:** Kiểm tra quyền, parent, replication và kết nối; không suy diễn hoặc tự động tạo entry mới.

**Không dựa vào `cn` để xác nhận hai entry là cùng một đối tượng**, vì `cn` có thể thay đổi trong quá trình rename. Đồng thời, không phải tất cả máy chủ đều cung cấp `entryUUID` hoặc `objectGUID` dưới cùng cách truy vấn; ứng dụng phải chọn thuộc tính ổn định tương thích với directory đang dùng.

## 7. Quy trình kiểm thử với directory thử nghiệm

Sử dụng môi trường LDAP thử nghiệm với quyền tối thiểu cần thiết để tạo và rename nhóm. Giả sử `ContextSource` trỏ base `dc=example,dc=org` và có sẵn hai entry `legacy-readers`, `platform-readers`.

1. Tra cứu hai DN trước khi đổi tên và ghi nhận `cn`, `member` của mỗi entry.
2. Gọi `renameGroup("legacy-readers", "platform-readers")`. Dự kiến nhận `TARGET_EXISTS`; cả hai entry vẫn truy cập được ở DN ban đầu và dữ liệu không bị ghi đè.
3. Gọi `renameGroup("legacy-readers", "new-readers")` khi DN `new-readers` chưa có. Dự kiến `RENAMED`; kiểm tra `new-readers` xuất hiện và entry nguồn không còn ở DN cũ.
4. Gọi `renameGroup("new-readers", "new-readers")`. Dự kiến `UNCHANGED` và không có lệnh LDAP rename.
5. Tạo hai tác nhân cạnh tranh cho cùng DN đích: một bên tạo/rename thành công trước, bên còn lại nhận conflict. Có thể mô phỏng xen kẽ bước lookup và bước ghi; **không coi kiểm tra trước là khóa độc quyền**.
6. Kiểm tra thêm trường hợp tài khoản thiếu quyền, DN nguồn không tồn tại và mất kết nối; bảo đảm chúng không bị gán nhầm thành `TARGET_EXISTS`.

Ví dụ chuỗi thao tác LDAP để minh họa yêu cầu rename ở mức giao thức (LDIF change record):

```ldif
dn: cn=legacy-readers,ou=groups,dc=example,dc=org
changetype: modrdn
newrdn: cn=platform-readers
deleteoldrdn: 1
```

Nếu DN đích đã có entry, máy chủ thông thường từ chối yêu cầu với `entryAlreadyExists (68)`. `deleteoldrdn: 1` quy định việc xử lý giá trị RDN cũ nếu rename thành công; nó **không** là tùy chọn ghi đè DN đích.

## 8. Câu hỏi tự kiểm tra

1. Vì sao `cn=platform-readers,ou=groups,...` và `cn=platform-readers,ou=archive,...` không trùng DN?
2. Nếu lookup DN đích trả `NameNotFoundException`, tại sao bạn vẫn cần bắt `NameAlreadyBoundException` tại `rename`?
3. LDAP result code `68` thể hiện lỗi gì? Khác `32` và `50` như thế nào?
4. Vì sao không được gọi `rebind(newDn, ...)` để xử lý conflict?
5. Sau một lần rename bị timeout, cần xác nhận điều gì trước khi thử lại?

**Ghi nhớ:** Kiểm tra DN đích giúp thông báo sớm, nhưng không thay thế kiểm tra nhất quán của LDAP server. Với Spring LDAP, xây DN chính xác, xử lý `NameAlreadyBoundException` từ `LdapTemplate.rename()`, giữ tách biệt lỗi trùng DN với lỗi quyền, thiếu entry và mất kết nối, đồng thời không ghi đè dữ liệu của entry đang chiếm DN đích.

## Tài liệu tham khảo

- [RFC 4511 — LDAPv3: Modify DN và result codes](https://www.rfc-editor.org/rfc/rfc4511.html)
- [Spring LDAP Javadoc — LdapOperations](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/LdapOperations.html)
- [Spring LDAP Javadoc — LdapTemplate](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/LdapTemplate.html)
- [Spring LDAP Javadoc — NameAlreadyBoundException](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/NameAlreadyBoundException.html)
- [Oracle JNDI — How LDAP Error Codes Map to JNDI Exceptions](https://docs.oracle.com/javase/tutorial/jndi/ldap/exceptions.html)
