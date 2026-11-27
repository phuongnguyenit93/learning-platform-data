# ModifyAttributes và ba loại thay đổi cơ bản

## Mục tiêu học tập

Sau bài này, bạn có thể giải thích cơ chế cập nhật thuộc tính của một LDAP entry, phân biệt rõ `ADD_ATTRIBUTE`, `REPLACE_ATTRIBUTE` và `REMOVE_ATTRIBUTE`, tự tạo mảng `ModificationItem[]` rồi gọi `LdapTemplate.modifyAttributes(...)` trong Spring LDAP. Bạn cũng sẽ biết cách thao tác với thuộc tính nhiều giá trị, kiểm tra kết quả và nhận diện những lỗi thường gặp do schema hoặc quyền truy cập.

Đây là một thao tác cốt lõi của **Spring LDAP**: ứng dụng có thể sửa từng phần dữ liệu trong thư mục thông qua JNDI, thay vì phải dựng lại toàn bộ entry. Các chủ đề khác như `ContextSource`, xác thực, TLS, `LdapClient` và ODM có thể sử dụng cùng quy tắc thay đổi thuộc tính được trình bày ở đây.

## 1. Tại sao cần `modifyAttributes`?

Một entry trong LDAP được nhận diện bằng **Distinguished Name (DN)** và chứa các **attribute**. Mỗi attribute có tên và một hoặc nhiều giá trị, tùy theo schema.

Ví dụ, một tài khoản nhân viên trong thư mục thử nghiệm:

~~~ldif
dn: uid=lan,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: lan
cn: Lan Tran
sn: Tran
mail: lan@example.org
telephoneNumber: +84 90 111 2222
description: Nhan vien khoi kinh doanh
~~~

Giả sử bộ phận nhân sự muốn đổi email của Lan, thêm số điện thoại bàn và xóa mô tả cũ. Cả ba việc đều là **sửa các thuộc tính của cùng một entry**. Chúng không đòi hỏi tạo, xóa hoặc chuyển entry sang DN khác.

Trong Spring LDAP, `LdapTemplate.modifyAttributes(Name dn, ModificationItem[] mods)` gửi một tập thay đổi đến entry xác định. `LdapTemplate` cũng có overload nhận DN kiểu `String` và một overload nhận `DirContextOperations`. Với bài này, chúng ta dùng `ModificationItem[]` vì từng thay đổi được chỉ ra tường minh, rất phù hợp để hiểu bản chất giao thức.

> **Phân biệt phạm vi:** `REMOVE_ATTRIBUTE` xóa giá trị hoặc cả một **attribute**. Xóa toàn bộ **entry** là thao tác khác, chẳng hạn `LdapTemplate.unbind(...)`. Đổi DN của entry là thao tác rename/move, không phải một thay đổi `mail` hay `telephoneNumber` thông thường.

## 2. Cấu tạo của một `ModificationItem`

Một đối tượng `javax.naming.directory.ModificationItem` kết hợp hai thành phần:

- **Mã thao tác**: một trong các hằng của `javax.naming.directory.DirContext`.
- **Đối tượng `Attribute`**: tên attribute cần tác động và, tùy thao tác, các giá trị tương ứng. Lớp `BasicAttribute` thường được dùng để xây dựng đối tượng này.

Cú pháp tối giản:

~~~java
ModificationItem change = new ModificationItem(
    DirContext.REPLACE_ATTRIBUTE,
    new BasicAttribute("mail", "lan.tran@example.org")
);
~~~

Ba thao tác cơ bản có ý nghĩa sau:

| Mã thao tác | Tác dụng khi attribute đang tồn tại | Tác dụng khi không tồn tại |
| --- | --- | --- |
| `DirContext.ADD_ATTRIBUTE` | Thêm giá trị vào tập giá trị hiện có; với thuộc tính một giá trị đã có dữ liệu, thường bị từ chối | Tạo attribute với giá trị được cung cấp, nếu schema cho phép |
| `DirContext.REPLACE_ATTRIBUTE` | Thay **toàn bộ tập giá trị cũ** bằng tập giá trị mới | Tạo attribute với tập giá trị được cung cấp, nếu schema cho phép |
| `DirContext.REMOVE_ATTRIBUTE` | Xóa các giá trị được chỉ rõ; nếu không cung cấp giá trị thì xóa toàn bộ attribute | Có thể bị từ chối hoặc được bỏ qua tùy nhà cung cấp và máy chủ |

**Lưu ý quan trọng:** `REPLACE_ATTRIBUTE` không có nghĩa là "thêm nếu khác". Nếu một thuộc tính đang có ba giá trị mà bạn thay bằng một giá trị, hai giá trị kia sẽ biến mất. Với `REMOVE_ATTRIBUTE`, `new BasicAttribute("description")` có **không giá trị**, biểu thị yêu cầu xóa cả thuộc tính `description`.

### 2.1. Thêm giá trị: `ADD_ATTRIBUTE`

~~~java
ModificationItem addPhone = new ModificationItem(
    DirContext.ADD_ATTRIBUTE,
    new BasicAttribute("telephoneNumber", "+84 28 3822 0000")
);
~~~

Nếu `telephoneNumber` đang có `+84 90 111 2222` và schema cho phép nhiều giá trị, sau thay đổi sẽ có cả hai số. Nếu thêm trùng giá trị đã tồn tại (theo quy tắc so khớp của LDAP), máy chủ có thể trả lỗi; nếu cố thêm số thứ hai vào attribute một giá trị, thao tác cũng không hợp lệ.

### 2.2. Thay thế: `REPLACE_ATTRIBUTE`

~~~java
ModificationItem replaceMail = new ModificationItem(
    DirContext.REPLACE_ATTRIBUTE,
    new BasicAttribute("mail", "lan.tran@example.org")
);
~~~

Mọi giá trị `mail` trước đó bị thay bằng `lan.tran@example.org`. Đây là lựa chọn thường gặp khi hệ thống nghiệp vụ xác định chính xác giá trị cuối cùng của thuộc tính. Với một thuộc tính nhiều giá trị, muốn giữ nhiều giá trị thì phải đưa **đủ các giá trị muốn giữ lại** vào `BasicAttribute` mới.

### 2.3. Xóa giá trị hoặc xóa thuộc tính: `REMOVE_ATTRIBUTE`

~~~java
// Xóa đúng một số trong thuộc tính nhiều giá trị.
ModificationItem removeOnePhone = new ModificationItem(
    DirContext.REMOVE_ATTRIBUTE,
    new BasicAttribute("telephoneNumber", "+84 90 111 2222")
);

// Xóa toàn bộ thuộc tính description: BasicAttribute không có giá trị.
ModificationItem removeDescription = new ModificationItem(
    DirContext.REMOVE_ATTRIBUTE,
    new BasicAttribute("description")
);
~~~

Hai trường hợp này khác nhau về phạm vi. Trường hợp thứ nhất giữ lại các số điện thoại khác. Trường hợp thứ hai xóa cả thuộc tính `description` khỏi entry. Đừng áp dụng xóa toàn bộ cho các thuộc tính bắt buộc của schema, ví dụ `cn` hoặc `sn` của entry kiểu `person`.

## 3. Ví dụ Spring LDAP: thực hiện cả ba thay đổi

Giả sử ứng dụng đã có `LdapTemplate` được cấu hình qua `ContextSource` với **base DN** `dc=example,dc=org` và tài khoản kết nối có quyền sửa entry tương ứng.

Đoạn mã sau sử dụng `LdapNameBuilder` để dựng DN **tương đối** `uid=lan,ou=people`. Cách này cũng xử lý việc escape ký tự đặc biệt trong các thành phần DN khi giá trị đến từ biến đầu vào.

~~~java
import javax.naming.Name;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;

import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;
import org.springframework.stereotype.Service;

@Service
public class ContactDirectoryService {

    private final LdapTemplate ldapTemplate;

    public ContactDirectoryService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public void updateLanContact() {
        // DN tương đối với base dc=example,dc=org trong ContextSource.
        Name dn = LdapNameBuilder.newInstance()
            .add("ou", "people")
            .add("uid", "lan")
            .build();

        ModificationItem[] changes = {
            new ModificationItem(
                DirContext.REPLACE_ATTRIBUTE,
                new BasicAttribute("mail", "lan.tran@example.org")
            ),
            new ModificationItem(
                DirContext.ADD_ATTRIBUTE,
                new BasicAttribute("telephoneNumber", "+84 28 3822 0000")
            ),
            new ModificationItem(
                DirContext.REMOVE_ATTRIBUTE,
                new BasicAttribute("description")
            )
        };

        ldapTemplate.modifyAttributes(dn, changes);
    }
}
~~~

**Giải thích theo thứ tự thực thi:**

1. `LdapNameBuilder` tạo DN `uid=lan,ou=people`; `ContextSource` liên kết tên này với base DN đã cấu hình. Nếu ứng dụng không đặt base DN, phải truyền tên phù hợp với ngữ cảnh kết nối.
2. `REPLACE_ATTRIBUTE` đặt lại email; `ADD_ATTRIBUTE` bổ sung số điện thoại; `REMOVE_ATTRIBUTE` xóa mô tả cũ.
3. `ldapTemplate.modifyAttributes(dn, changes)` gửi các thay đổi cho **một entry**. Theo ngữ nghĩa LDAP Modify, các thay đổi được xử lý theo thứ tự trong một yêu cầu và toàn bộ yêu cầu thành công hoặc thất bại; không có trạng thái chỉ áp dụng một phần nếu máy chủ tuân thủ giao thức.

Sau khi gọi thành công, các thuộc tính liên quan được kỳ vọng như sau:

~~~ldif
dn: uid=lan,ou=people,dc=example,dc=org
mail: lan.tran@example.org
telephoneNumber: +84 90 111 2222
telephoneNumber: +84 28 3822 0000
~~~

Thuộc tính `description` không còn; các thuộc tính không được sửa như `cn`, `sn`, `uid`, `objectClass` vẫn giữ nguyên. Nếu schema, chính sách của máy chủ hoặc ACL không cho phép một trong ba thay đổi thì yêu cầu sẽ thất bại.

### Khi muốn sửa nhiều giá trị cùng một attribute

Ví dụ thay **toàn bộ** danh sách điện thoại bằng hai số cụ thể:

~~~java
BasicAttribute phones = new BasicAttribute("telephoneNumber");
phones.add("+84 90 111 2222");
phones.add("+84 28 3822 0000");

ModificationItem replacePhones = new ModificationItem(
    DirContext.REPLACE_ATTRIBUTE,
    phones
);

ldapTemplate.modifyAttributes(dn, new ModificationItem[] {replacePhones});
~~~

So sánh lựa chọn:

- Dùng `ADD_ATTRIBUTE` khi cần **giữ mọi giá trị hiện tại** rồi bổ sung giá trị.
- Dùng `REMOVE_ATTRIBUTE` với giá trị cụ thể khi cần **bỏ một giá trị** và giữ các giá trị khác.
- Dùng `REPLACE_ATTRIBUTE` khi ứng dụng muốn **quyết định toàn bộ tập giá trị cuối cùng**.

## 4. Kiểm tra kết quả sau khi cập nhật

Không nên suy đoán dữ liệu mới chỉ vì phương thức không phát sinh lỗi. Bạn có thể đọc lại entry bằng `lookupContext` để xác nhận các thuộc tính mong đợi:

~~~java
import org.springframework.ldap.core.DirContextOperations;

// "dn" là Name đã xây dựng trong ví dụ trước.
DirContextOperations updated = ldapTemplate.lookupContext(dn);

String mail = updated.getStringAttribute("mail");
String[] phones = updated.getStringAttributes("telephoneNumber");
String description = updated.getStringAttribute("description");

// Kỳ vọng:
// mail = "lan.tran@example.org"
// phones chứa cả hai số điện thoại đã nêu, không phụ thuộc thứ tự.
// description = null (attribute đã bị xóa).
~~~

Đối với thuộc tính nhiều giá trị, không dựa vào **thứ tự** các giá trị trả về; LDAP coi chúng là một tập giá trị. Trong bài thực hành, nên so sánh theo tập hợp và kiểm tra chính xác DN được truy vấn.

### Ví dụ thử nghiệm nhanh

| Dữ liệu ban đầu | Thao tác | Kết quả mong đợi |
| --- | --- | --- |
| `mail=lan@example.org` | `REPLACE mail=lan.tran@example.org` | Email cũ được thay bằng email mới |
| `telephoneNumber` có số A | `ADD telephoneNumber=B` | Thuộc tính chứa A và B nếu cho phép đa giá trị |
| `telephoneNumber` có A và B | `REMOVE telephoneNumber=A` | Chỉ còn B |
| `description` đang tồn tại | `REMOVE description` không kèm giá trị | Không còn attribute `description` |
| `telephoneNumber` có A và B | `REPLACE telephoneNumber=C` | Chỉ còn C |
| `sn` là thuộc tính bắt buộc | `REMOVE sn` không kèm giá trị | Bị từ chối do vi phạm schema |

Để kiểm thử tích hợp, sử dụng LDAP test server hoặc dữ liệu thử nghiệm riêng, khởi tạo entry trước mỗi ca thử và đọc lại sau mỗi lệnh. Không chạy ví dụ ghi trực tiếp trên tài khoản sản xuất.

## 5. Cách làm ngắn hơn với `DirContextOperations`

Khi cần sửa nhiều trường từ một đối tượng nghiệp vụ, Spring LDAP còn hỗ trợ lấy entry hiện tại rồi để `DirContextAdapter` tính các thay đổi:

~~~java
DirContextOperations context = ldapTemplate.lookupContext(dn);

context.setAttributeValue("mail", "lan.tran@example.org");
context.setAttributeValues(
    "telephoneNumber",
    new String[] {"+84 90 111 2222", "+84 28 3822 0000"}
);
context.setAttributeValue("description", null);

ldapTemplate.modifyAttributes(context);
~~~

Cách này hữu ích khi đã đọc entry và muốn đặt **trạng thái cuối cùng** của các thuộc tính. Tuy nhiên, việc `lookupContext` rồi `modifyAttributes` là **hai thao tác riêng**: nếu có ứng dụng khác sửa cùng entry ở giữa, bạn cần cân nhắc xung đột dữ liệu. Khi cần kiểm soát chính xác kiểu ADD/REPLACE/REMOVE và thứ tự thay đổi, `ModificationItem[]` minh bạch hơn.

Đừng khởi tạo `DirContextAdapter` tùy ý rồi mong nó tự nhận ra dữ liệu cũ; cách thông dụng là nhận `DirContextOperations` từ `lookupContext` để adapter có trạng thái gốc dùng khi tính khác biệt.

## 6. Giới hạn và lỗi thường gặp

| Tình huống | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Không tìm thấy DN | DN tương đối/base DN không khớp hoặc entry đã bị xóa | Kiểm tra base của `ContextSource`, DN sau khi build và sự tồn tại của entry |
| Thêm giá trị bị từ chối | Giá trị đã tồn tại hoặc attribute chỉ cho phép một giá trị | Kiểm tra schema và giá trị hiện tại; dùng `REPLACE` nếu mục tiêu là đặt lại giá trị |
| Xóa hoặc thay đổi thuộc tính thất bại | Thuộc tính bắt buộc, không đúng cú pháp hoặc bị ràng buộc schema | Xác định `objectClass`, loại attribute và quy tắc bắt buộc |
| Bị từ chối truy cập | Tài khoản bind thiếu quyền ghi, hoặc thuộc tính do máy chủ quản lý | Cấp quyền tối thiểu cần thiết; không cố sửa thuộc tính chỉ đọc như `modifyTimestamp` |
| Kết quả không như mong đợi | Dùng `REPLACE` cho thuộc tính đa giá trị làm mất giá trị cũ | Chọn ADD/REMOVE theo giá trị hoặc REPLACE với tập giá trị đầy đủ |
| Kết nối có rủi ro | Gửi thông tin định danh qua đường truyền không bảo vệ | Cấu hình LDAPS hoặc StartTLS đúng cách và kiểm tra chứng chỉ |

Các lỗi LDAP/JNDI thường được Spring LDAP chuyển thành exception để ứng dụng xử lý. Nên phân biệt **không có entry**, **vi phạm schema** và **thiếu quyền** để trả lỗi nghiệp vụ phù hợp; không bắt chung mọi lỗi rồi coi như cập nhật thành công.

Một vài nguyên tắc khi triển khai thật:

1. **Tôn trọng schema:** `objectClass` quy định thuộc tính bắt buộc, cho phép và kiểu giá trị; đừng tự ý xóa `cn`, `sn` hoặc thuộc tính dùng trong RDN.
2. **Không dùng modify để đổi DN:** nếu cần thay `uid=lan` trong tên entry, xem xét `rename(...)` và ảnh hưởng đến tham chiếu liên quan.
3. **Dựng DN an toàn:** dùng `LdapNameBuilder` thay vì nối trực tiếp chuỗi DN từ đầu vào người dùng; kiểm tra giá trị nghiệp vụ trước khi ghi.
4. **Không mặc định thao tác có thể lặp lại:** gọi lại ADD cùng giá trị có thể lỗi; gọi REMOVE một giá trị không còn tồn tại cũng có thể lỗi, tùy server.
5. **Phân biệt tính nguyên tử:** một lệnh LDAP Modify có thể nguyên tử trên một entry, nhưng **không** tạo giao dịch xuyên nhiều lệnh hoặc nhiều entry; cần biện pháp riêng nếu nghiệp vụ yêu cầu cập nhật đồng bộ nhiều nơi.
6. **Bảo vệ dữ liệu:** dùng TLS, ACL theo nguyên tắc quyền tối thiểu, không ghi mật khẩu hay dữ liệu cá nhân nhạy cảm ra log khi chẩn đoán.

## 7. Câu hỏi tự kiểm tra

1. Một attribute `telephoneNumber` đang có hai giá trị. Nếu `REPLACE_ATTRIBUTE` bằng một `BasicAttribute` chỉ chứa một giá trị, điều gì xảy ra với giá trị còn lại?
2. Vì sao `new BasicAttribute("description")` trong `REMOVE_ATTRIBUTE` lại khác `new BasicAttribute("description", "abc")`?
3. Khi cần thay email, vì sao `REPLACE_ATTRIBUTE` thường dễ dự đoán hơn `ADD_ATTRIBUTE`?
4. Vì sao một yêu cầu `modifyAttributes` có ba phần thay đổi vẫn có thể thất bại hoàn toàn nếu chỉ một phần vi phạm schema?
5. Khi nào dùng `LdapTemplate.rename(...)` thay vì `modifyAttributes(...)`?

**Ghi nhớ:** Chọn thao tác dựa vào kết quả mong muốn đối với **tập giá trị của từng attribute**. `ADD` bổ sung, `REPLACE` thay cả tập, `REMOVE` bỏ giá trị được chỉ định hoặc toàn bộ thuộc tính. Đó là nền tảng cho cập nhật LDAP an toàn và có thể dự đoán bằng Spring LDAP.

## Tài liệu tham khảo

- [Spring LDAP – LdapTemplate API](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/LdapTemplate.html): overload `modifyAttributes` và cách làm việc với `DirContextOperations`.
- [Spring LDAP – Basic Usage](https://docs.spring.io/spring-ldap/reference/spring-ldap-basic-usage.html): cách tạo DN bằng `LdapNameBuilder`.
- [Oracle Java – DirContext](https://docs.oracle.com/en/java/javase/25/docs/api/java.naming/javax/naming/directory/DirContext.html): ngữ nghĩa của ba mã thay đổi và các điều kiện lỗi.
- [Oracle Java – Modify Attributes](https://docs.oracle.com/javase/tutorial/jndi/ops/modattrs.html): thứ tự và tính nguyên tử của mảng `ModificationItem`.
