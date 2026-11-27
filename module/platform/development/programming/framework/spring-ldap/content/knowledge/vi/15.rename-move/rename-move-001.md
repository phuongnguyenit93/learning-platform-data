# Rename entry bằng RDN mới trong Spring LDAP

Trong LDAP, tên của một entry được xác định bằng **Distinguished Name (DN)**. Khi cần đổi tên một nhóm từ `backend-readers` thành `api-readers`, ứng dụng không thể chỉ cập nhật trường hiển thị rồi giả định entry đã đổi tên: phần tên trong DN cũng phải thay đổi. Với **Spring LDAP**, `LdapTemplate.rename(...)` thực hiện thao tác đổi DN của entry qua dịch vụ thư mục.

Bài này tập trung vào trường hợp **rename bằng RDN mới nhưng giữ nguyên nhánh cha**. Từ đó, bạn sẽ biết cách nhận diện RDN, tạo DN đúng bằng `LdapNameBuilder`, gọi `LdapTemplate.rename`, kiểm tra kết quả và xử lý những tình huống thường gặp trước khi tìm hiểu thao tác *move* giữa các nhánh.

## 1. DN, RDN và tên của một entry

Xét nhóm LDAP:

```ldif
dn: cn=backend-readers,ou=groups,dc=example,dc=org
objectClass: top
objectClass: groupOfNames
cn: backend-readers
member: uid=lan,ou=people,dc=example,dc=org
```

DN có hai phần cần phân biệt:

| Thành phần | Giá trị trong ví dụ | Vai trò |
| --- | --- | --- |
| **RDN (Relative Distinguished Name)** | `cn=backend-readers` | Xác định entry trong phạm vi nhánh cha trực tiếp. |
| **DN của nhánh cha** | `ou=groups,dc=example,dc=org` | Nơi chứa entry. |
| **DN đầy đủ** | `cn=backend-readers,ou=groups,dc=example,dc=org` | Địa chỉ của entry trong cây LDAP. |

Khi đổi RDN từ `cn=backend-readers` thành `cn=api-readers` mà vẫn giữ nguyên `ou=groups`, entry sẽ có DN mới:

```text
Trước: cn=backend-readers,ou=groups,dc=example,dc=org
Sau:   cn=api-readers,ou=groups,dc=example,dc=org
```

Đây là **rename trong cùng parent**. Entry không được tạo mới ở một vị trí khác rồi xóa bản cũ; máy chủ xử lý yêu cầu đổi tên theo thao tác LDAP **Modify DN** (còn được gọi là *Modify RDN* trong một số tài liệu). Khả năng thực hiện còn phụ thuộc quyền và chính sách của directory server.

### Đổi RDN khác gì sửa thuộc tính?

- **Sửa thuộc tính**: `LdapTemplate.modifyAttributes(...)` dùng khi bạn muốn thay đổi dữ liệu của một entry, ví dụ `description`, nhưng giữ nguyên DN.
- **Đổi RDN**: `LdapTemplate.rename(oldDn, newDn)` dùng khi phần định danh của entry trong cây LDAP thay đổi.
- **Move**: cũng có thể dùng thao tác đổi DN, nhưng `newDn` nằm dưới parent khác. Việc di chuyển giữa các nhánh có thể bị hạn chế riêng bởi máy chủ, ACL hoặc cấu trúc directory.

Ví dụ, thay `description` thành `"Đội vận hành API"` không đổi `cn=backend-readers` trong DN. Ngược lại, đổi RDN thành `cn=api-readers` làm địa chỉ tra cứu của entry thay đổi.

## 2. Bản chất LDAP Modify DN

Theo mô hình LDAP, yêu cầu Modify DN xác định **DN hiện tại** và **RDN mới**; khi cần chuyển vị trí, yêu cầu còn có thể chỉ ra parent mới. Thao tác cũng có cờ `deleteOldRDN` quyết định có xóa giá trị thuộc tính từng dùng trong RDN cũ hay giữ lại nếu schema và chính sách cho phép.

Ví dụ:

```text
old DN : cn=backend-readers,ou=groups,dc=example,dc=org
new RDN: cn=api-readers
parent : ou=groups,dc=example,dc=org  (không thay đổi)
```

Sau khi đổi tên, **RDN trong DN chắc chắn là tên mới nếu thao tác thành công**. Về các giá trị thuộc tính của entry:

- Máy chủ sẽ bảo đảm giá trị tương ứng với RDN mới được xử lý theo quy tắc Modify DN.
- Giá trị RDN cũ có thể bị xóa hoặc được giữ lại tùy cờ `deleteOldRDN`, cấu hình API và quy định schema.
- Các thuộc tính không tham gia RDN, ví dụ `description`, không tự đổi chỉ vì DN thay đổi.

Vì vậy, khi nghiệp vụ yêu cầu `cn` chỉ còn một giá trị, hãy **đọc lại thuộc tính `cn` sau rename** để xác nhận hành vi thực tế của hệ thống LDAP. Không giả định mọi directory server có cùng cách giữ giá trị cũ.

> **Phạm vi:** Một RDN có thể chứa nhiều thành phần, ví dụ `cn=Lan+uid=lan`. Bài này sử dụng RDN đơn `cn=...` để làm rõ quy trình cơ bản.

## 3. Rename bằng `LdapTemplate.rename`

Giả sử đã cấu hình `ContextSource` với base DN `dc=example,dc=org`, đã khởi tạo bean `LdapTemplate` và tài khoản bind có quyền đổi tên entry nhóm. Hai DN truyền cho `LdapTemplate` dưới đây là **DN tương đối với base DN đã cấu hình**.

```java
import javax.naming.Name;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

public class GroupRenameService {
    private final LdapTemplate ldapTemplate;

    public GroupRenameService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public void renameGroup(String oldCn, String newCn) {
        if (oldCn == null || oldCn.isBlank()
                || newCn == null || newCn.isBlank()) {
            throw new IllegalArgumentException("Tên nhóm không được rỗng");
        }

        Name oldDn = LdapNameBuilder.newInstance()
                .add("ou", "groups")
                .add("cn", oldCn)
                .build();

        Name newDn = LdapNameBuilder.newInstance()
                .add("ou", "groups")
                .add("cn", newCn)
                .build();

        ldapTemplate.rename(oldDn, newDn);
    }
}
```

Sử dụng:

```java
GroupRenameService service = new GroupRenameService(ldapTemplate);
service.renameGroup("backend-readers", "api-readers");
```

Nếu entry tồn tại và máy chủ chấp nhận thao tác, DN đổi từ:

```text
cn=backend-readers,ou=groups,dc=example,dc=org
```

sang:

```text
cn=api-readers,ou=groups,dc=example,dc=org
```

**Điểm đáng chú ý trong mã:**

1. `LdapNameBuilder` ghép các thành phần DN đúng cú pháp LDAP và xử lý ký tự đặc biệt trong giá trị `cn` (ví dụ dấu phẩy, dấu cộng). Hạn chế tự nối chuỗi DN từ dữ liệu người dùng.
2. `oldDn` và `newDn` đều giữ `ou=groups`; vì vậy đây là đổi RDN, không phải chuyển nhóm sang tổ chức khác.
3. `rename` không trả về entry vừa đổi tên. Nếu máy chủ từ chối, Spring LDAP chuyển lỗi JNDI/LDAP thành ngoại lệ thuộc `DataAccessException` phù hợp; ứng dụng cần xử lý theo nghiệp vụ.
4. Ví dụ dùng `String.isBlank()` từ Java 11. Nếu dự án dùng Java cũ hơn, thay bằng kiểm tra `trim().isEmpty()` sau khi đã loại trừ `null`.

Không đưa `dc=example,dc=org` vào `oldDn` hoặc `newDn` lần nữa nếu `ContextSource` đã cấu hình base đó. Nếu ứng dụng không cấu hình base DN, cần xây DN đầy đủ theo cách thiết lập `ContextSource` thực tế.

## 4. Kiểm tra entry sau khi đổi RDN

Một lệnh `rename` chạy thành công cho thấy máy chủ đã chấp nhận yêu cầu. Nếu ứng dụng còn cần dùng entry dưới tên mới, nên kiểm tra DN mới và các thuộc tính liên quan.

Bạn có thể thêm phương thức sau vào `GroupRenameService`:

```java
import java.util.Arrays;
import org.springframework.ldap.core.DirContextOperations;

public void printRenamedGroup(String newCn) {
    Name newDn = LdapNameBuilder.newInstance()
            .add("ou", "groups")
            .add("cn", newCn)
            .build();

    DirContextOperations entry = ldapTemplate.lookupContext(newDn);

    String[] cnValues = entry.getStringAttributes("cn");
    String[] members = entry.getStringAttributes("member");

    System.out.println("DN mới: " + newDn);
    System.out.println("CN: " + Arrays.toString(cnValues));
    System.out.println("Số member được trả về: "
            + (members == null ? 0 : members.length));
}
```

Hãy đối chiếu với dữ liệu ban đầu:

| Điều cần xác minh | Kết quả mong đợi |
| --- | --- |
| Tra cứu `cn=api-readers,ou=groups,...` | Tìm thấy entry dưới DN mới. |
| Tra cứu `cn=backend-readers,ou=groups,...` | Thông thường không còn tìm thấy entry tại DN cũ, trừ khi máy chủ có alias hoặc cơ chế ánh xạ riêng. |
| Thuộc tính `cn` | Có giá trị phù hợp RDN mới; có thể còn giá trị cũ tùy hành vi `deleteOldRDN` và schema. |
| Thuộc tính `member` | Vẫn chứa thành viên của nhóm nếu thao tác chỉ đổi RDN và máy chủ không áp dụng quy tắc phụ khác. |

Nếu chỉ muốn xác minh tồn tại, hãy tra cứu DN mới hoặc dùng phép kiểm tra tồn tại tương ứng của `LdapTemplate`. Không bắt ngoại lệ từ việc tra cứu DN cũ rồi xem đó là bằng chứng duy nhất của thành công: ứng dụng có thể đang gặp sự cố quyền truy cập hoặc kết nối.

## 5. Những lỗi và ràng buộc cần dự liệu

| Tình huống | Điều cần kiểm tra |
| --- | --- |
| **DN cũ không tồn tại** | Base DN, OU cha, chuỗi RDN và tên entry thực tế; thường phát sinh lỗi không tìm thấy đối tượng. |
| **DN mới đã tồn tại** | LDAP không thể có hai entry với cùng DN; cần chọn tên khác hoặc thông báo trùng tên cho người dùng. |
| **Không đủ quyền** | Tài khoản bind có thể đọc nhóm nhưng không được rename; kiểm tra ACL cho thao tác Modify DN, không tự nâng quyền. |
| **RDN mới không hợp lệ theo schema** | Kiểm tra attribute type dùng trong RDN, giá trị cho phép và các ràng buộc của object class. |
| **Không thể rename entry có con** | Một số máy chủ giới hạn thao tác với subtree; phải kiểm tra chính sách server và mối liên hệ DN của các entry con. |
| **Ứng dụng vẫn dùng DN cũ** | Cập nhật cấu hình, cache, mapping hoặc tham chiếu bên ngoài đang lưu DN; nếu máy chủ có cơ chế referential integrity, cần xác nhận phạm vi cập nhật. |
| **Xử lý lại yêu cầu sau timeout** | Kiểm tra trạng thái của cả DN cũ lẫn mới trước khi thử lại; phản hồi lỗi mạng không chứng minh server chưa thực hiện. |

Đổi RDN **không có nghĩa** là mọi nơi tham chiếu tới DN đó sẽ tự được chỉnh sửa. Chẳng hạn một ACL, cấu hình tích hợp hoặc thuộc tính thành viên của nhóm khác có thể đang lưu DN cũ. Việc tự cập nhật tham chiếu có phụ thuộc cơ chế riêng của server, và có thể phải là một bước nghiệp vụ tách biệt.

### Nguyên tắc xử lý lỗi trong ứng dụng

Ở tầng giao diện hoặc API, nên phản hồi theo nguyên nhân cụ thể: không tìm thấy nhóm, tên mới đã được dùng, người gọi không có quyền, hoặc lỗi hệ thống. Log đủ thông tin để chẩn đoán nhưng tránh ghi mật khẩu bind và dữ liệu LDAP nhạy cảm. Kết nối tới directory nên được bảo vệ bằng LDAPS hoặc StartTLS theo cấu hình triển khai.

Nếu quy trình đổi tên còn cập nhật một cơ sở dữ liệu khác hoặc nhiều entry LDAP, đừng mặc định `ldapTemplate.rename` tạo thành một transaction chung cho các hệ thống đó. Cần thiết kế cơ chế khôi phục hoặc đồng bộ riêng khi bước tiếp theo thất bại.

## 6. Bài thực hành

**Bối cảnh:** Directory có nhóm `cn=backend-readers,ou=groups,dc=example,dc=org` và một thành viên `uid=lan,ou=people,dc=example,dc=org`. Tài khoản kết nối có quyền rename nhóm.

1. Tra cứu nhóm bằng DN cũ và ghi nhận giá trị `cn` cùng `member` trước khi thay đổi.
2. Gọi `renameGroup("backend-readers", "api-readers")`.
3. Tra cứu DN mới; kiểm tra `cn` và so sánh tập DN trong `member` với trước khi rename.
4. Thử đổi sang một `cn` đã được một entry khác sử dụng; quan sát cách API báo lỗi và bảo đảm nhóm ban đầu vẫn truy cập được.
5. Với môi trường thử nghiệm phù hợp, đổi lại `api-readers` thành `backend-readers` để khôi phục trạng thái ban đầu.

**Câu hỏi suy ngẫm:**

- Vì sao gọi `modifyAttributes` để đổi `cn` chưa đủ để kết luận DN cũng đã đổi?
- Với `ContextSource` đặt base `dc=example,dc=org`, DN nào phải truyền cho `rename`?
- Vì sao cần kiểm tra các hệ thống đang lưu DN cũ sau khi rename?
- Nếu sau rename có hai giá trị `cn`, cơ chế `deleteOldRDN` có thể liên quan như thế nào?

## Ghi nhớ

- **Rename RDN** đổi thành phần định danh của entry trong cùng nhánh cha; về bản chất là LDAP Modify DN.
- Trong Spring LDAP, dùng **`ldapTemplate.rename(oldDn, newDn)`** với hai DN được xây dựng và xác định tương đối với base DN phù hợp.
- Kiểm tra entry dưới **DN mới**, các giá trị thuộc tính RDN và tham chiếu DN mà hệ thống khác đang sử dụng.
- Đổi tên là một thao tác ghi có thể bị từ chối bởi ACL, schema, xung đột DN hoặc chính sách của directory; xử lý lỗi và thao tác thử lại theo trạng thái thực tế.

## Tài liệu tham khảo

- [Spring LDAP Reference — Basic Usage of LdapTemplate](https://docs.spring.io/spring-ldap/reference/spring-ldap-basic-usage.html)
- [Spring LDAP Javadoc — LdapTemplate](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/LdapTemplate.html)
- [RFC 4511 — Lightweight Directory Access Protocol (LDAP): The Protocol, Modify DN Operation](https://www.rfc-editor.org/rfc/rfc4511#section-4.9)
- [Spring LDAP Reference — Dynamically Building Distinguished Names](https://docs.spring.io/spring-ldap/reference/basic-configuration.html)
