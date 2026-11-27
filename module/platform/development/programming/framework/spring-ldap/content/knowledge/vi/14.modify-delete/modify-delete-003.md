# Thay đổi attribute đa trị mà không xóa giá trị khác trong Spring LDAP

Trong thư mục LDAP, một nhân viên có thể có nhiều số điện thoại và một nhóm có thể chứa nhiều DN thành viên. Nếu yêu cầu nghiệp vụ chỉ là **thêm một số điện thoại** hoặc **xóa một thành viên khỏi nhóm**, ứng dụng phải giữ nguyên các giá trị còn lại. Sai lầm phổ biến là đọc một danh sách, sửa nó trong Java rồi **thay thế toàn bộ thuộc tính** bằng danh sách mới. Cách đó có thể làm mất dữ liệu, nhất là khi nhiều tiến trình cùng cập nhật entry.

Trong chương **Modify và delete** của SPRING_LDAP, bài này giải thích ba thao tác LDAP Modify — `ADD_ATTRIBUTE`, `REMOVE_ATTRIBUTE` và `REPLACE_ATTRIBUTE` — ở cấp **giá trị của thuộc tính đa trị**. Người học sẽ thực hành bằng `LdapTemplate`, `DirContextAdapter`/`DirContextOperations` và `ModificationItem` của JNDI, tìm hiểu ngữ nghĩa schema, ACL, DN, giao dịch một entry, xung đột đồng thời và kiểm thử trên thư mục lab. Những nguyên tắc này vẫn đúng khi ứng dụng dùng `LdapClient` hoặc ODM vì việc sửa thật được LDAP server thực thi.

## 1. Bài toán: đổi một giá trị, giữ nguyên những giá trị khác

Giả sử entry nhân viên có:

~~~ldif
dn: uid=an,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: an
cn: Nguyen Van An
sn: Nguyen
telephoneNumber: +84 28 1111
telephoneNumber: +84 28 2222
mail: an@example.org
~~~

Ứng dụng nhận yêu cầu **thêm `+84 28 3333`**. Trạng thái mong muốn:

~~~ldif
telephoneNumber: +84 28 1111
telephoneNumber: +84 28 2222
telephoneNumber: +84 28 3333
~~~

Hai số cũ vẫn phải còn trên server. Tương tự, nếu yêu cầu xóa riêng số `+84 28 1111`, kết quả phải giữ lại `+84 28 2222`. Đây là **cập nhật một giá trị** trong thuộc tính đa trị, không phải yêu cầu thay toàn bộ thuộc tính.

Ví dụ khác là nhóm:

~~~ldif
dn: cn=developers,ou=groups,dc=example,dc=org
objectClass: top
objectClass: groupOfNames
cn: developers
member: uid=an,ou=people,dc=example,dc=org
member: uid=binh,ou=people,dc=example,dc=org
~~~

Khi thêm `uid=chi` vào nhóm, hai DN thành viên An và Bình phải được giữ nguyên. Đừng coi `member` như một trường String đơn trị.

## 2. Attribute đa trị trong LDAP nghĩa là gì?

Một **attribute type** do schema định nghĩa có thể là đơn trị hoặc đa trị. Thuộc tính khai báo `SINGLE-VALUE` chỉ cho phép một giá trị; thuộc tính không bị giới hạn như vậy có thể chứa nhiều giá trị hợp lệ.

| Thuộc tính minh họa | Đặc điểm cần lưu ý | Cách sử dụng |
| --- | --- | --- |
| `telephoneNumber` | Có thể có nhiều số | Thêm/xóa số riêng lẻ |
| `mail` | Có thể có nhiều giá trị tùy schema và ứng dụng | Không mặc định chỉ có một email |
| `member` | Nhiều DN thành viên nhóm `groupOfNames` | Thêm/xóa từng DN |
| `objectClass` | Nhiều tên class dùng xác định cấu trúc entry | Không tùy tiện sửa |
| `cn` | Có thể có nhiều cách gọi | Cần quy tắc chọn tên hiển thị |
| Thuộc tính được schema đánh dấu `SINGLE-VALUE` | Chỉ một giá trị hợp lệ | Không áp dụng chiến lược thêm nhiều giá trị |

Đối với thuộc tính đa trị thông thường, các giá trị tạo thành **một tập không có thứ tự nghiệp vụ**. Không nên cho rằng giá trị đầu tiên trong `getStringAttributes(...)` là “chính” hoặc hai mảng khác thứ tự nghĩa là dữ liệu khác nhau.

Server áp dụng **matching rule** của attribute khi xác định giá trị tương đương. Ví dụ, một attribute dạng DN có thể dùng matching rule của DN chứ không so sánh chuỗi theo từng byte. Hai chuỗi DN viết khác nhau có thể đại diện cùng một giá trị theo quy tắc của server.

### Phân biệt ba loại thao tác

| LDAP Modify / JNDI | Ý định | Với `telephoneNumber` |
| --- | --- | --- |
| **`ADD_ATTRIBUTE`** | Thêm giá trị được nêu | Thêm số `+84 28 3333`, giữ các số khác |
| **`REMOVE_ATTRIBUTE`** với giá trị cụ thể | Xóa đúng giá trị được nêu | Bỏ số `+84 28 1111`, giữ số còn lại |
| **`REPLACE_ATTRIBUTE`** | Thay **toàn bộ tập giá trị** bằng tập gửi lên | Nếu chỉ gửi số mới, các số cũ có thể bị mất |

Tên “attribute” trong các hằng JNDI có thể gây hiểu nhầm: `ADD_ATTRIBUTE` và `REMOVE_ATTRIBUTE` có thể nhắm **từng giá trị** khi đối tượng `Attribute` đi kèm chứa giá trị cụ thể. Với `REMOVE_ATTRIBUTE` không kèm giá trị, ý nghĩa lại có thể là **xóa toàn bộ thuộc tính**. Phần tiếp theo sẽ phân biệt hai trường hợp.

## 3. Luồng từ Spring LDAP đến LDAP Modify

~~~mermaid
flowchart TD
    A["Service nhận yêu cầu thêm/xóa giá trị"] --> B["Kiểm tra quyền và giá trị đầu vào"]
    B --> C["Xây DN entry và ModificationItem"]
    C --> D["LdapTemplate.modifyAttributes(...)"]
    D --> E["ContextSource và JNDI DirContext"]
    E --> F[("LDAP server")]
    F --> G{"ACL, schema, matching rule, ràng buộc?"}
    G -->|Được chấp nhận| H["Sửa đúng attribute/value"]
    G -->|Bị từ chối| I["LDAP error / Spring LDAP exception"]
    H --> J["Đọc lại để xác nhận khi cần"]
~~~

`ContextSource` quyết định endpoint, base DN và danh tính bind của ứng dụng. `LdapTemplate` quản lý vòng đời JNDI context và gửi yêu cầu sửa. **LDAP server** mới là nơi quyết định lệnh hợp lệ hay không.

Cần tách ba nghĩa khác nhau của từ “bind”:

- **LDAP protocol Bind:** xác thực tài khoản dịch vụ với LDAP server.
- **`LdapTemplate.bind(...)`:** thêm **entry mới**, không dùng để sửa một thuộc tính.
- **`LdapTemplate.modifyAttributes(...)`:** sửa các attribute/giá trị của entry **đã tồn tại**.

Nếu yêu cầu là thêm số điện thoại vào entry hiện hữu, hãy dùng **Modify**, không dùng `bind` để tạo lại entry và cũng không mặc định dùng `rebind` để thay toàn bộ binding.

## 4. Cách trực tiếp: `ModificationItem` với `ADD_ATTRIBUTE`

Để yêu cầu server thêm đúng một số điện thoại, không cần đọc toàn bộ danh sách số về rồi gửi lại. Dùng overload của `LdapTemplate.modifyAttributes(...)` nhận DN và các `ModificationItem`:

~~~java
import javax.naming.Name;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;
import org.springframework.ldap.core.LdapTemplate;

public class PhoneValueWriter {
    private final LdapTemplate ldapTemplate;

    public PhoneValueWriter(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public void addPhone(Name personDn, String phone) {
        if (phone == null || phone.isBlank() || phone.length() > 64) {
            throw new IllegalArgumentException("Invalid phone number");
        }

        ModificationItem addOne = new ModificationItem(
                DirContext.ADD_ATTRIBUTE,
                new BasicAttribute("telephoneNumber", phone));

        ldapTemplate.modifyAttributes(
                personDn, new ModificationItem[] {addOne});
    }
}
~~~

Ở đây:

1. `personDn` phải trỏ đến **entry đang có**, theo cơ sở tên của `ContextSource`.
2. `BasicAttribute("telephoneNumber", phone)` chỉ chứa **giá trị cần thêm**.
3. `DirContext.ADD_ATTRIBUTE` yêu cầu server bổ sung giá trị đó.
4. **Không gửi danh sách các số hiện tại**, vì không có ý định thay chúng.
5. Nếu server chấp nhận, các số khác của entry được giữ nguyên.

Ví dụ cấu hình `ContextSource.base=dc=example,dc=org` và DN tương đối `uid=an,ou=people`. Server áp dụng thao tác lên `uid=an,ou=people,dc=example,dc=org`.

### Nếu số đó đã tồn tại thì sao?

LDAP có thể trả `attributeOrValueExists (20)` khi cố thêm một giá trị tương đương đã có. Đây **không phải** lỗi `entryAlreadyExists (68)`: entry vốn đã tồn tại là điều kiện bình thường của thao tác Modify.

Ứng dụng cần chọn hợp đồng rõ ràng:

- **Add strict:** thêm thành công nếu mới, báo conflict nếu giá trị đã tồn tại.
- **Add idempotent theo nghiệp vụ:** nếu đúng giá trị đã có, có thể coi mục tiêu cuối đã đạt **sau khi xác minh phù hợp**, không vì thế bỏ qua lỗi khác.
- **Add có điều kiện:** với yêu cầu bảo mật/đồng thời cao, xem cơ chế điều kiện mà server hỗ trợ.

Không bắt mọi exception rồi trả “số điện thoại đã tồn tại”. Lỗi ACL, connection, schema hoặc DN sai cần được phân biệt.

## 5. Xóa đúng một giá trị bằng `REMOVE_ATTRIBUTE`

Giả sử An có hai số và chỉ cần xóa `+84 28 1111`. Dùng `REMOVE_ATTRIBUTE` với đối tượng `Attribute` **chứa số muốn loại**:

~~~java
import javax.naming.Name;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;
import org.springframework.ldap.core.LdapTemplate;

public class PhoneValueRemover {
    private final LdapTemplate ldapTemplate;

    public PhoneValueRemover(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public void removePhone(Name personDn, String phone) {
        if (phone == null || phone.isBlank()) {
            throw new IllegalArgumentException("Phone is required");
        }

        ModificationItem removeOne = new ModificationItem(
                DirContext.REMOVE_ATTRIBUTE,
                new BasicAttribute("telephoneNumber", phone));

        ldapTemplate.modifyAttributes(
                personDn, new ModificationItem[] {removeOne});
    }
}
~~~

Yêu cầu này nói với server: **bỏ giá trị được chỉ định**. Những số khác không phải mục tiêu của request.

### Bẫy nghiêm trọng: xóa thuộc tính hay xóa một giá trị?

Hai ví dụ dưới đây có ý nghĩa khác nhau:

~~~java
// Xóa ĐÚNG MỘT số:
new ModificationItem(
        DirContext.REMOVE_ATTRIBUTE,
        new BasicAttribute("telephoneNumber", "+84 28 1111"));

// Nguy cơ XÓA TOÀN BỘ telephoneNumber:
new ModificationItem(
        DirContext.REMOVE_ATTRIBUTE,
        new BasicAttribute("telephoneNumber"));
~~~

Khi lệnh REMOVE không cung cấp giá trị, LDAP Modify có ngữ nghĩa xóa **toàn bộ thuộc tính**. Đây là thao tác khác hoàn toàn với xóa một số điện thoại.

| Trạng thái trước | Lệnh | Trạng thái mong muốn |
| --- | --- | --- |
| `[1111, 2222]` | REMOVE giá trị `1111` | `[2222]` |
| `[1111, 2222]` | REMOVE cả attribute | Không còn `telephoneNumber` |
| `[1111, 2222]` | REPLACE bằng `[3333]` | `[3333]`, mất `1111` và `2222` |
| `[1111, 2222]` | ADD `3333` | `[1111, 2222, 3333]` |

Nếu yêu cầu xóa một giá trị không tồn tại, server có thể trả `noSuchAttribute (16)` hoặc lỗi liên quan. Không giả định phép REMOVE luôn tự động thành công kiểu idempotent.

## 6. Thay toàn bộ tập giá trị khi và chỉ khi nghiệp vụ yêu cầu

`REPLACE_ATTRIBUTE` là lựa chọn đúng **nếu người dùng được phép quản lý toàn bộ danh sách** và muốn đặt danh sách mới hoàn toàn.

~~~java
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;

BasicAttribute replacement = new BasicAttribute("telephoneNumber");
replacement.add("+84 28 1111");
replacement.add("+84 28 3333");

ModificationItem replaceAll = new ModificationItem(
        DirContext.REPLACE_ATTRIBUTE,
        replacement);

// ldapTemplate.modifyAttributes(personDn, new ModificationItem[]{replaceAll});
~~~

Nó không “chỉ thêm 3333”. Giá trị `2222` sẽ không còn nếu server chấp nhận toàn bộ phép replace.

### Tình huống mất cập nhật khi dùng read–modify–replace

Hai request cùng đọc số điện thoại:

~~~text
Ban đầu trên LDAP:
telephoneNumber = {1111, 2222}

Request A đọc {1111, 2222}, chuẩn bị thêm 3333.
Request B đọc {1111, 2222}, chuẩn bị thêm 4444.

A gửi REPLACE {1111, 2222, 3333}.
B gửi REPLACE {1111, 2222, 4444}.

Kết quả cuối có thể là:
{1111, 2222, 4444}

Số 3333 vừa được A thêm đã bị B ghi đè.
~~~

Đây là *lost update*. Nếu cả A và B đều gửi **ADD đúng một giá trị** thay vì replace dựa trên snapshot cũ, server có thể thêm hai giá trị khác nhau mà không phải thay toàn bộ tập.

**Nhận xét quan trọng:** ADD/REMOVE theo giá trị giúp giảm rủi ro ghi đè các giá trị khác, nhưng không tự giải quyết mọi race condition. Hai tác nhân thêm cùng một giá trị có thể khiến một lệnh trả duplicate; hai tác nhân sửa các thuộc tính liên quan vẫn cần chính sách nghiệp vụ. Khi yêu cầu thay toàn bộ danh sách, có thể cần cơ chế kiểm soát đồng thời.

## 7. Đọc giá trị hiện có bằng `DirContextOperations`

Với một số nghiệp vụ, service cần hiển thị trạng thái trước khi sửa hoặc kiểm tra chính sách. Spring LDAP cung cấp `lookupContext(...)` trả `DirContextOperations`:

~~~java
import javax.naming.Name;
import java.util.Arrays;
import java.util.List;
import org.springframework.ldap.core.DirContextOperations;
import org.springframework.ldap.core.LdapTemplate;

public class PhoneReader {
    private final LdapTemplate ldapTemplate;

    public PhoneReader(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<String> listPhones(Name personDn) {
        DirContextOperations entry = ldapTemplate.lookupContext(personDn);
        String[] phones = entry.getStringAttributes("telephoneNumber");

        if (phones == null || phones.length == 0) {
            return List.of();
        }
        return List.copyOf(Arrays.asList(phones));
    }
}
~~~

Lưu ý:

- `getStringAttribute("telephoneNumber")` chỉ biểu diễn **một giá trị**; để không bỏ sót các giá trị khác, dùng `getStringAttributes(...)`.
- Không dựa vào thứ tự mảng khi so sánh hai tập số.
- Danh sách được trả về phản ánh **những giá trị client được phép đọc**, không nhất thiết toàn bộ dữ liệu trên server nếu có ACL hoặc projection giới hạn.
- Đọc để hiển thị không phải yêu cầu phải dùng read–modify–replace khi thêm/xóa; phần nghiệp vụ cập nhật có thể gửi MODIFY giá trị trực tiếp như các mục trước.

Nếu thuộc tính không chứa `String` (ví dụ ảnh hoặc chứng chỉ), không chuyển tùy tiện thành text. Dùng API `Attributes`/`Attribute` theo syntax thực tế và loại dữ liệu phù hợp.

## 8. Cập nhật qua `DirContextAdapter`: thuận tiện nhưng phải xem diff

Ngoài cách gửi `ModificationItem` trực tiếp, có thể đọc entry rồi thay đổi các thuộc tính qua `DirContextOperations`:

~~~java
import javax.naming.Name;
import javax.naming.directory.ModificationItem;
import org.springframework.ldap.core.DirContextOperations;
import org.springframework.ldap.core.LdapTemplate;

public class PhoneAdapterWriter {
    private final LdapTemplate ldapTemplate;

    public PhoneAdapterWriter(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public void addPhoneFromLoadedEntry(Name dn, String phone) {
        DirContextOperations entry = ldapTemplate.lookupContext(dn);

        entry.addAttributeValue("telephoneNumber", phone);

        ModificationItem[] changes = entry.getModificationItems();
        if (changes.length == 0) {
            return;
        }

        // Đánh giá các thay đổi trước khi ghi.
        ldapTemplate.modifyAttributes(entry);
    }

    public void removePhoneFromLoadedEntry(Name dn, String phone) {
        DirContextOperations entry = ldapTemplate.lookupContext(dn);

        entry.removeAttributeValue("telephoneNumber", phone);

        ModificationItem[] changes = entry.getModificationItems();
        if (changes.length == 0) {
            return;
        }

        ldapTemplate.modifyAttributes(entry);
    }
}
~~~

Các phương thức `addAttributeValue(...)` và `removeAttributeValue(...)` diễn đạt rõ **ý định cục bộ**. Nhưng cần phân biệt:

1. Adapter được khởi tạo từ snapshot của entry, nên có thể theo dõi những thay đổi so với trạng thái đọc.
2. `getModificationItems()` cho biết **các lệnh adapter dự định gửi**.
3. Không mặc định rằng một lời gọi `addAttributeValue` nhất thiết sinh chính xác một `DirContext.ADD_ATTRIBUTE` ở mọi tình huống/phiên bản; cách tính diff tùy trạng thái và triển khai adapter.
4. Nếu adapter phát sinh `REPLACE_ATTRIBUTE` chứa tập giá trị snapshot, vẫn có nguy cơ **ghi đè cập nhật đồng thời**, dù code chỉ gọi phương thức “add”.
5. Với yêu cầu chắc chắn **gửi đúng lệnh ADD/REMOVE một giá trị ở server**, cách dùng `ModificationItem` tường minh ở mục 4–5 dễ kiểm soát ngữ nghĩa hơn.

### Kiểm tra thao tác dự định thay vì chỉ kiểm tra dữ liệu cuối

~~~java
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;
import org.springframework.ldap.core.DirContextOperations;

public static void inspect(DirContextOperations entry) {
    for (ModificationItem item : entry.getModificationItems()) {
        String id = item.getAttribute().getID();
        int operation = item.getModificationOp();

        if (operation == DirContext.REPLACE_ATTRIBUTE) {
            // Cần thẩm định xem thay toàn bộ attribute có thật sự được phép.
        }
        if ("userPassword".equalsIgnoreCase(id)) {
            throw new IllegalArgumentException(
                    "Password modification is not allowed here");
        }
    }
}
~~~

Không log trực tiếp `ModificationItem.toString()` hoặc toàn bộ dữ liệu LDAP. Chúng có thể chứa thông tin cá nhân hoặc giá trị bí mật. Các kiểm tra allowlist cần thêm giới hạn giá trị, loại thao tác, quyền người gọi và phạm vi DN, không chỉ kiểm tra tên attribute.

**Kết luận về lựa chọn API:** dùng adapter khi cần cập nhật nhiều trường từ trạng thái đã đọc và có kiểm tra diff phù hợp. Dùng `ModificationItem(ADD/REMOVE, BasicAttribute(..., value))` khi nghiệp vụ yêu cầu thay **chính xác một giá trị** mà không thay toàn bộ tập.
## 9. Tình huống thực tế: thêm hoặc xóa thành viên nhóm LDAP

Các nhóm LDAP thường lưu DN thành viên dưới dạng thuộc tính đa trị. Ví dụ:

~~~ldif
dn: cn=developers,ou=groups,dc=example,dc=org
objectClass: top
objectClass: groupOfNames
cn: developers
member: uid=an,ou=people,dc=example,dc=org
member: uid=binh,ou=people,dc=example,dc=org
~~~

Yêu cầu là thêm Chi vào nhóm mà **không xóa An hoặc Bình**. Cách đúng là gửi một phép `ADD_ATTRIBUTE` cho thuộc tính `member`.

Có hai loại DN cần đặc biệt phân biệt:

- **DN của entry cần sửa:** `cn=developers,ou=groups`, tương đối với base `dc=example,dc=org` của `ContextSource`.
- **Giá trị của attribute `member`:** thường là **DN đầy đủ** của người dùng, chẳng hạn `uid=chi,ou=people,dc=example,dc=org`. Đây là **dữ liệu thuộc tính**, không phải search base của thao tác sửa.

### Service quản lý membership theo giá trị

~~~java
import javax.naming.Name;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

public class GroupMembershipService {
    private final LdapTemplate ldapTemplate;

    public GroupMembershipService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public void addMember(String groupCn, String userUid) {
        changeMember(DirContext.ADD_ATTRIBUTE, groupCn, userUid);
    }

    public void removeMember(String groupCn, String userUid) {
        changeMember(DirContext.REMOVE_ATTRIBUTE, groupCn, userUid);
    }

    private void changeMember(
            int operation, String groupCn, String userUid) {

        validateId(groupCn);
        validateId(userUid);

        // DN của entry nhóm: tương đối với ContextSource.base.
        Name groupDn = LdapNameBuilder.newInstance("ou=groups")
                .add("cn", groupCn)
                .build();

        // Giá trị 'member': DN đầy đủ của người dùng trên server.
        Name memberDn = LdapNameBuilder.newInstance(
                        "ou=people,dc=example,dc=org")
                .add("uid", userUid)
                .build();

        ModificationItem item = new ModificationItem(
                operation,
                new BasicAttribute("member", memberDn.toString()));

        ldapTemplate.modifyAttributes(
                groupDn, new ModificationItem[] {item});
    }

    private static void validateId(String value) {
        if (value == null || value.isBlank()
                || value.length() > 64) {
            throw new IllegalArgumentException("Invalid identifier");
        }
    }
}
~~~

**Giả định quan trọng:** code sử dụng base cố định `dc=example,dc=org` và nhóm `groupOfNames` theo schema/ACL phù hợp. Trong ứng dụng nhiều môi trường, không hardcode suffix production; xây DN đầy đủ của thành viên từ **nguồn cấu hình được quản trị**, hoặc dùng API xây DN từ base đã xác định. Cần chắc chắn `member` là thuộc tính phù hợp schema của loại nhóm đang dùng.

Điểm mạnh của cách làm này là code không cần tải tất cả `member` rồi viết lại danh sách sau khi thêm/xóa một người. Server xử lý lệnh thay đổi riêng trên giá trị được chỉ định.

### Bẫy: xóa thành viên cuối cùng của `groupOfNames`

Theo schema chuẩn, `groupOfNames` có thuộc tính **`member` là MUST**. Nếu bạn REMOVE giá trị `member` cuối cùng, entry có thể vi phạm schema và server từ chối thao tác.

Ví dụ:

~~~ldif
dn: cn=one-person-team,ou=groups,dc=example,dc=org
objectClass: groupOfNames
cn: one-person-team
member: uid=an,ou=people,dc=example,dc=org
~~~

Xóa duy nhất `member: uid=an,...` không đồng nghĩa nhóm rỗng hợp lệ. Một số directory hỗ trợ kiểu nhóm hoặc schema khác cho nhóm rỗng, nhưng không thể mặc định điều đó cho mọi server.

Ứng dụng cần **quy tắc nghiệp vụ**: không cho xóa thành viên cuối, giải thể nhóm bằng quy trình riêng, hoặc dùng kiểu nhóm thực sự cho phép rỗng trong hệ thống. Một pre-check danh sách thành viên có thể giúp báo lỗi sớm nhưng vẫn có nguy cơ race; server sẽ quyết định schema khi ghi.

### Không coi `memberOf` là danh sách có thể tự sửa

Trong nhiều LDAP server, `memberOf` trên entry người dùng là thuộc tính được **suy ra hoặc bảo trì bởi server/plugin**, không phải nơi ứng dụng trực tiếp thêm tên nhóm. Khi đổi membership, thường sửa `member` hoặc thuộc tính tương ứng **trên entry nhóm**, theo schema server. Cần kiểm tra thực tế của OpenLDAP, Active Directory hoặc directory khác vì thuộc tính nhóm và cơ chế đồng bộ không hoàn toàn giống nhau.

## 10. Kiểm tra đầu vào, DN và quyền nghiệp vụ

Việc xây lệnh `ADD_ATTRIBUTE` đúng cú pháp chưa bảo đảm một người dùng được phép thêm bất kỳ thành viên nào vào nhóm. Cần tách **định danh**, **quyền người gọi**, **quyền tài khoản LDAP**, và **giá trị attribute**.

| Lớp kiểm soát | Câu hỏi |
| --- | --- |
| DN của entry cần sửa | Có thuộc nhánh được phép như `ou=groups` không? |
| DN thành viên | Có tham chiếu một người dùng/đối tượng hợp lệ không? |
| Quyền nghiệp vụ của người gọi | Người này có được sửa membership của nhóm đó không? |
| Quyền LDAP ACL | Service bind có quyền modify thuộc tính `member` của nhóm không? |
| Schema | Kiểu nhóm có `member` đúng syntax và cho phép sửa không? |
| Tính nhất quán | Có cho phép một nhóm rỗng, thành viên trùng, hoặc tham chiếu không tồn tại không? |
| Log/audit | Có ghi lại hành động mà không lộ credential và dữ liệu nhạy cảm không? |

**DN escaping** và **LDAP filter escaping** khác nhau. Khi dựng group DN và member DN từ dữ liệu như UID, CN, dùng `LdapNameBuilder` để escape RDN. Nếu cần tìm entry để xác minh người dùng tồn tại, dùng `LdapQueryBuilder` để escape filter assertion value. Không dùng một hàm escape cho cả hai.

Ngay cả khi member DN hợp lệ về cú pháp, LDAP server không nhất thiết tự xác nhận DN thành viên **thực sự tồn tại**: điều đó phụ thuộc schema, plugin/reference-integrity và chính sách của directory. Nếu nghiệp vụ yêu cầu chỉ thêm người dùng hiện hữu, cần kiểm tra tồn tại bằng quyền phù hợp, đồng thời hiểu rằng pre-check không thay cho ràng buộc phía server.

## 11. Schema, matching rule và quyền: server quyết định kết quả

Một yêu cầu Modify trên attribute đa trị có thể thất bại vì nhiều lý do không liên quan đến code Java:

| Tình huống | LDAP result code thường gặp | Ý nghĩa cần kiểm tra |
| --- | --- | --- |
| Thêm lại giá trị đã tồn tại | `attributeOrValueExists (20)` | Server thấy giá trị tương đương đã có |
| Xóa giá trị không có | `noSuchAttribute (16)` | Thuộc tính hoặc giá trị yêu cầu không tồn tại theo thao tác |
| Không đủ quyền sửa attribute | `insufficientAccessRights (50)` | ACL và danh tính service bind |
| Attribute chỉ chấp nhận một giá trị | `constraintViolation (19)` | `SINGLE-VALUE` hoặc policy khác |
| Giá trị sai cú pháp LDAP | `invalidAttributeSyntax (21)` | Attribute syntax, ví dụ DN không hợp lệ |
| Xóa giá trị bắt buộc cuối cùng | `objectClassViolation (65)` | Ràng buộc MUST của object class |
| Entry đích không tồn tại | `noSuchObject (32)` | DN, ContextSource base, parent hoặc entry đã bị xóa |
| DN/attribute bị server từ chối bởi chính sách khác | Có thể là constraint/result khác | Xem schema/server policy thực tế |
| Tài khoản kết nối không xác thực được | `invalidCredentials (49)` | Lỗi bind identity, không phải lỗi thêm thành viên |
| Mất kết nối trong lúc Modify | Timeout/communication error | Kết quả có thể chưa xác định |

Đây là các mã **điển hình**, không phải hứa hẹn mọi LDAP server sẽ trả cùng mã khi đồng thời có nhiều vấn đề. Spring LDAP chuyển đổi nhiều exception JNDI thành exception của framework; ở tầng service nên phân loại lỗi theo hợp đồng nghiệp vụ và loại exception thực tế, không dựa vào một đoạn chuỗi message riêng của server.

### Dữ liệu đa trị thường không có thứ tự

Nếu `member` chứa ba DN, thứ tự trả về có thể thay đổi giữa các lần đọc. Unit test không nên so sánh mảng theo thứ tự với `assertArrayEquals(...)` trừ khi thuộc tính thực sự có nghĩa thứ tự theo đặc tả/ứng dụng.

So sánh tập các giá trị và lưu ý matching rule của server có thể xem hai giá trị khác hình thức là tương đương. So sánh Java `Set<String>` chỉ là cách kiểm tra **biểu diễn chuỗi** trong test, không hoàn toàn thay thế matching rule LDAP.

## 12. Lỗi đồng thời và tính nguyên tử của Modify

Một **LDAP Modify request** có thể chứa nhiều modification và thông thường được server áp dụng **nguyên tử trên một entry** theo ngữ nghĩa giao thức: các thay đổi trong cùng request được thực hiện cùng nhau hoặc request bị từ chối. Điều này **không** biến nhiều request tới nhiều entry thành một giao dịch có rollback tự động.

Ví dụ ứng dụng muốn thêm hai số điện thoại cùng lúc:

~~~java
ModificationItem[] changes = {
        new ModificationItem(
                DirContext.ADD_ATTRIBUTE,
                new BasicAttribute("telephoneNumber", "+84 28 3333")),
        new ModificationItem(
                DirContext.ADD_ATTRIBUTE,
                new BasicAttribute("telephoneNumber", "+84 28 4444"))
};

ldapTemplate.modifyAttributes(personDn, changes);
~~~

Nếu server từ chối một trong các sửa đổi vì constraint, toàn bộ request Modify này không được coi là đã commit một phần. Nhưng nếu bạn chia thành **hai lời gọi `modifyAttributes(...)` riêng**, request thứ nhất có thể thành công và request thứ hai thất bại. Khi nghiệp vụ cần mọi thay đổi xảy ra cùng nhau trên **một entry**, gửi trong một request phù hợp thay vì chia nhỏ tùy tiện.

### ADD/REMOVE theo giá trị và sự thay đổi song song

| Tình huống đồng thời | Rủi ro | Phương án |
| --- | --- | --- |
| A thêm `3333`, B thêm `4444` | Thường có thể giữ cả hai giá trị nếu dùng ADD riêng | Dùng ADD specific-value thay vì replace snapshot |
| A và B cùng thêm `3333` | Một request có thể gặp `20` | Định nghĩa semantics duplicate/idempotency |
| A xóa `1111`, B xóa `2222` | Hai yêu cầu có thể cùng hợp lệ, nhưng phải xét schema tối thiểu | Dùng REMOVE giá trị cụ thể; kiểm tra schema |
| A xóa giá trị cuối nhóm, B cũng sửa membership | Có thể vi phạm MUST hoặc policy | Kiểm soát trường hợp nhóm rỗng/đồng thời |
| A replace toàn bộ tập từ snapshot cũ, B vừa thêm giá trị | A có thể xóa cập nhật của B | Tránh replace khi không quản lý toàn bộ tập |
| A đọc xong, entry bị xóa trước Modify | Modify có thể lỗi không có DN | Xử lý xung đột và đọc lại khi thích hợp |

Nếu nghiệp vụ cần bảo đảm không sửa dựa trên snapshot cũ, cân nhắc cơ chế **conditional modify** như LDAP Assertion Control nếu server/client hỗ trợ, hoặc versioning tại tầng ứng dụng. Một lần đọc lại trước khi ghi vẫn có thể bị race trong khoảng giữa hai request, vì vậy không nên mô tả nó là khóa nguyên tử.

## 13. Bắt lỗi và xây hợp đồng API rõ ràng

Khi người dùng nhấn “Thêm số điện thoại”, điều gì nên xảy ra nếu số đã có? Đáp án phụ thuộc **hợp đồng nghiệp vụ**, không chỉ LDAP.

Có thể thiết kế:

- **Thêm nghiêm ngặt:** nếu số đã có, trả conflict; nếu mới, thêm.
- **Bảo đảm hiện diện:** nếu số đã có, coi trạng thái cuối là đạt yêu cầu, nhưng chỉ sau khi xác minh đúng thuộc tính/giá trị và không che lỗi khác.
- **Xóa nghiêm ngặt:** nếu giá trị không tồn tại, trả lỗi.
- **Bảo đảm vắng mặt:** nếu giá trị đã vắng, có thể xem như mục tiêu hoàn tất theo chính sách đã định.

Không nên có một catch-all `catch (Exception e) { return true; }`. Điều đó che cả mất kết nối, thiếu quyền, schema sai và dữ liệu bị thay đổi ngoài ý muốn.

### Timeout sau yêu cầu ghi

Nếu client gửi ADD rồi mất kết nối trước khi nhận response, server có thể **đã thêm thành công**. Gửi lại có thể nhận `attributeOrValueExists (20)`. Đây là kết quả chưa chắc chắn sau timeout, tương tự các thao tác ghi khác.

Cách xử lý an toàn:

1. Phân biệt timeout/communication error với phản hồi LDAP rõ ràng.
2. Khi kết nối phục hồi, đọc lại giá trị bằng quyền phù hợp.
3. Xác minh trạng thái mới có thực sự đáp ứng ý định và thuộc đúng đối tượng/entry không.
4. Chỉ retry khi chính sách nghiệp vụ cho phép và có giới hạn số lần; tránh tạo vòng lặp tải lớn.
5. Với thay đổi membership nhạy cảm, ghi audit và cân nhắc đối chiếu danh tính/request đã thực hiện.

Việc **xác minh lại** không biến một thao tác không xác định thành một transaction; nó giúp ứng dụng quyết định phản hồi theo thông tin hiện có.

## 14. Unit test: xác nhận lệnh MODIFY không thay toàn bộ thuộc tính

Một unit test quan trọng không chỉ kiểm tra service đã gọi `modifyAttributes(...)`, mà còn kiểm tra chính xác **operation** và **giá trị** trong `ModificationItem`.

Ví dụ dùng Mockito + JUnit 5 với `PhoneValueWriter` ở mục 4:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.*;

import javax.naming.Name;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

class PhoneValueWriterTest {

    @Test
    void addingOnePhoneUsesAddNotReplace() throws Exception {
        LdapTemplate template = mock(LdapTemplate.class);
        PhoneValueWriter service = new PhoneValueWriter(template);

        Name dn = LdapNameBuilder.newInstance("ou=people")
                .add("uid", "an")
                .build();

        service.addPhone(dn, "+84 28 3333");

        ArgumentCaptor<ModificationItem[]> captor =
                ArgumentCaptor.forClass(ModificationItem[].class);

        verify(template).modifyAttributes(eq(dn), captor.capture());
        verifyNoMoreInteractions(template);

        ModificationItem[] changes = captor.getValue();
        assertEquals(1, changes.length);
        assertEquals(DirContext.ADD_ATTRIBUTE,
                changes[0].getModificationOp());
        assertEquals("telephoneNumber",
                changes[0].getAttribute().getID());
        assertEquals("+84 28 3333",
                changes[0].getAttribute().get());
    }
}
~~~

Tương tự, kiểm tra `PhoneValueRemover`:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.*;

import javax.naming.Name;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

class PhoneValueRemoverTest {

    @Test
    void removingOnePhoneKeepsSpecificValueInRequest()
            throws Exception {
        LdapTemplate template = mock(LdapTemplate.class);
        PhoneValueRemover service = new PhoneValueRemover(template);

        Name dn = LdapNameBuilder.newInstance("ou=people")
                .add("uid", "an")
                .build();

        service.removePhone(dn, "+84 28 1111");

        ArgumentCaptor<ModificationItem[]> captor =
                ArgumentCaptor.forClass(ModificationItem[].class);

        verify(template).modifyAttributes(eq(dn), captor.capture());

        ModificationItem[] changes = captor.getValue();
        assertEquals(1, changes.length);
        assertEquals(DirContext.REMOVE_ATTRIBUTE,
                changes[0].getModificationOp());
        assertEquals("telephoneNumber",
                changes[0].getAttribute().getID());
        assertEquals(1, changes[0].getAttribute().size());
        assertEquals("+84 28 1111",
                changes[0].getAttribute().get());
    }
}
~~~

Điểm mấu chốt của test thứ hai là `getAttribute().size() == 1`: REMOVE **có một giá trị được chỉ định**, không phải đối tượng `BasicAttribute` rỗng khiến thao tác xóa cả thuộc tính.

Các test trên chỉ xác nhận **lệnh do Java chuẩn bị**, chưa xác minh LDAP server áp dụng ra sao hoặc matching rule/ACL. Cần thêm integration test.

## 15. Integration test: giá trị không liên quan phải được bảo toàn

Dùng LDAP server lab có schema phù hợp với `telephoneNumber` và nhánh `ou=people`, tài khoản được cấp quyền sửa đúng thuộc tính. Không sử dụng directory production để thử thao tác ghi.

Dữ liệu ban đầu:

~~~ldif
dn: uid=an,ou=people,dc=lab,dc=example,dc=org
objectClass: inetOrgPerson
uid: an
cn: Nguyen Van An
sn: Nguyen
telephoneNumber: +84 28 1111
telephoneNumber: +84 28 2222
~~~

Với `ContextSource.base=dc=lab,dc=example,dc=org`, DN tương đối cần sửa là `uid=an,ou=people`.

### Kịch bản A — thêm một số

1. Đọc tập số ban đầu, xác nhận có `1111` và `2222`.
2. Gọi `addPhone(dn, "+84 28 3333")`.
3. Lookup entry mới và đọc **tất cả** giá trị `telephoneNumber`.
4. Xác nhận có đủ ba số, không bị mất `1111` và `2222`.
5. Dọn riêng số `3333` do test tạo nếu cần.

### Kịch bản B — xóa riêng một số

1. Chuẩn bị entry có `1111`, `2222` và `3333` trong lab.
2. Gọi `removePhone(dn, "+84 28 1111")`.
3. Lookup lại, xác nhận `1111` vắng nhưng `2222`, `3333` vẫn có.
4. Khôi phục dữ liệu ban đầu theo quy trình cleanup đã được thiết kế.

### Kịch bản C — đánh giá rủi ro replace

1. Tạo bản sao entry thử nghiệm với tập số `{1111, 2222}`.
2. Gửi `REPLACE_ATTRIBUTE` chỉ chứa `3333`.
3. Đọc lại và quan sát các số cũ bị thay.
4. So sánh với kết quả ADD ở kịch bản A và giải thích vì sao replace không dùng để “thêm một số”.

### Kịch bản D — schema và quyền

Kiểm tra riêng:

| Tình huống | Điều muốn xác nhận |
| --- | --- |
| Thêm lại giá trị có sẵn | Lỗi duplicate theo matching rule/server |
| Xóa giá trị không tồn tại | Lỗi hoặc kết quả được xác định đúng |
| Service bind chỉ có quyền đọc | Modify bị từ chối |
| Xóa member cuối cùng của groupOfNames | Server áp dụng ràng buộc MUST |
| Thao tác với DN ngoài OU cho phép | Service và ACL từ chối |
| Hai tiến trình cùng thêm giá trị khác nhau | Không mất cập nhật do replace snapshot |
| Lỗi timeout giữa request và response | Service không retry không kiểm soát |

**Kiểm thử bằng mock không thay thế integration test.** Mock có thể xác minh tạo đúng `ModificationItem`, nhưng chỉ server mới xác nhận schema, ACL, matching rule và kết quả thực tế.

## 16. Bài thực hành: thêm, xóa và thay toàn bộ tập giá trị

Giả sử nhân viên An có:

~~~text
telephoneNumber = { "+84 28 1111", "+84 28 2222" }
~~~

Và nhóm developers có:

~~~text
member = {
  "uid=an,ou=people,dc=example,dc=org",
  "uid=binh,ou=people,dc=example,dc=org"
}
~~~

Hãy trả lời:

1. Muốn thêm `+84 28 3333` mà giữ hai số cũ, dùng mã JNDI operation nào?
2. Muốn xóa riêng `+84 28 1111`, tạo `BasicAttribute` ra sao?
3. Nếu gọi `REPLACE_ATTRIBUTE` với chỉ `+84 28 3333`, hai số ban đầu sẽ thế nào?
4. Vì sao `new BasicAttribute("telephoneNumber")` kết hợp `REMOVE_ATTRIBUTE` nguy hiểm?
5. Với `ContextSource.base=dc=example,dc=org`, DN để Modify nhóm developers và giá trị `member` đầy đủ của Chi khác nhau thế nào?
6. Nếu hai request cùng thêm hai số khác nhau, tại sao ADD riêng theo giá trị thường tốt hơn read–modify–replace?
7. Khi xóa thành viên cuối của `groupOfNames`, điều gì có thể xảy ra?
8. Với `DirContextAdapter.addAttributeValue(...)`, có thể mặc định `getModificationItems()` luôn trả một `ADD_ATTRIBUTE` không?
9. Sau timeout, lặp lại ADD nhận `20`, có thể khẳng định request ban đầu chưa chạy không?
10. Unit test cần kiểm tra điều gì ngoài việc `modifyAttributes(...)` đã được gọi?

### Đáp án tham khảo

| Câu | Đáp án |
| --- | --- |
| 1 | `DirContext.ADD_ATTRIBUTE` với `BasicAttribute("telephoneNumber", "+84 28 3333")` |
| 2 | `DirContext.REMOVE_ATTRIBUTE` với `BasicAttribute("telephoneNumber", "+84 28 1111")` |
| 3 | Tập giá trị bị thay bằng tập mới, có thể chỉ còn `3333` |
| 4 | REMOVE không chỉ rõ giá trị có thể xóa **toàn bộ attribute** |
| 5 | Group DN tương đối: `cn=developers,ou=groups`; member value đầy đủ: `uid=chi,ou=people,dc=example,dc=org` |
| 6 | ADD đúng một giá trị không cần gửi lại snapshot cũ nên tránh ghi đè giá trị khác |
| 7 | Có thể bị từ chối do `member` là MUST trong `groupOfNames` |
| 8 | Không. Cần kiểm tra diff thực tế, nhất là khi adapter làm việc trên snapshot cũ |
| 9 | Không. ADD ban đầu có thể đã thành công, response bị mất; hoặc giá trị được thêm bởi tác nhân khác |
| 10 | Operation phải là ADD/REMOVE, attribute name đúng, REMOVE chứa giá trị cụ thể, không phải REPLACE hoặc REMOVE rỗng |

### Bài tập code

Hoàn thiện hai dòng tạo modification sau mà **không dùng REPLACE**:

~~~java
// Thêm chính xác một số điện thoại:
ModificationItem add = new ModificationItem(
        /* operation */, /* Attribute */);

// Xóa chính xác một số điện thoại:
ModificationItem remove = new ModificationItem(
        /* operation */, /* Attribute */);
~~~

Đáp án:

~~~java
ModificationItem add = new ModificationItem(
        DirContext.ADD_ATTRIBUTE,
        new BasicAttribute("telephoneNumber", newPhone));

ModificationItem remove = new ModificationItem(
        DirContext.REMOVE_ATTRIBUTE,
        new BasicAttribute("telephoneNumber", oldPhone));
~~~

Sau đó gọi `ldapTemplate.modifyAttributes(dn, new ModificationItem[]{add})` hoặc dùng `remove` trong một **request riêng** theo ý định. Chỉ gộp chúng trong một request khi nghiệp vụ muốn cả hai thay đổi cùng nhau trên **một entry** và đã kiểm tra trạng thái/schema phù hợp.

## 17. Checklist trước khi đưa vào sản phẩm

- [ ] Xác định rõ thao tác **thêm một giá trị**, **xóa một giá trị** hay **thay toàn bộ tập**.
- [ ] Khi cần giữ giá trị khác, ưu tiên `ADD_ATTRIBUTE`/`REMOVE_ATTRIBUTE` chứa giá trị cụ thể.
- [ ] Không gửi `REMOVE_ATTRIBUTE` với `BasicAttribute` rỗng nếu chỉ muốn xóa một phần tử.
- [ ] Không dùng `setAttributeValues(...)` hoặc `REPLACE_ATTRIBUTE` từ snapshot cũ khi nghiệp vụ không quản lý toàn bộ tập.
- [ ] Nếu dùng `DirContextAdapter`, kiểm tra `getModificationItems()` và tác động thực tế trước khi ghi.
- [ ] Kiểm tra `SINGLE-VALUE`, `MUST`, syntax và matching rule của attribute theo schema.
- [ ] Hiểu quy tắc nhóm: `member` thường được sửa trên entry nhóm; `memberOf` có thể là thuộc tính dẫn xuất.
- [ ] Xây DN đích bằng `LdapNameBuilder`, hiểu sự khác biệt giữa DN tương đối và DN đầy đủ trong giá trị `member`.
- [ ] Kiểm tra quyền người gọi, ACL của tài khoản dịch vụ, LDAPS/StartTLS và quản lý secret an toàn.
- [ ] Xử lý duplicate, missing value, schema violation, timeout và kết quả ghi chưa chắc chắn riêng biệt.
- [ ] Unit test chính xác `ModificationItem`; integration test xác nhận giá trị không liên quan được bảo toàn.
- [ ] Có cơ chế kiểm soát đồng thời nếu ứng dụng cần thay toàn bộ tập giá trị theo snapshot.

## 18. Những điểm cần nhớ

- **LDAP attribute đa trị là một tập giá trị**, không phải một String đơn. Đọc một phần tử rồi ghi lại bằng REPLACE có thể làm mất dữ liệu.
- **`ADD_ATTRIBUTE` với một giá trị** bổ sung giá trị đó; **`REMOVE_ATTRIBUTE` với một giá trị** loại riêng giá trị đó. **`REPLACE_ATTRIBUTE`** thay tập giá trị, phải được dùng có chủ đích.
- **REMOVE với tập giá trị rỗng** có thể xóa **cả thuộc tính** — đây là cạm bẫy quan trọng nhất khi chỉ muốn loại một phần tử.
- `LdapTemplate.modifyAttributes(Name, ModificationItem[])` cho phép biểu diễn chính xác thay đổi cấp giá trị. `DirContextAdapter` thuận tiện cho sửa cục bộ nhưng cần xem `getModificationItems()`, nhất là khi quan tâm tới đồng thời.
- **Schema và ACL quyết định tính hợp lệ**. Ví dụ `groupOfNames` yêu cầu `member`; không phải nhóm nào cũng cho phép rỗng.
- **Một Modify request có thể nguyên tử trên một entry**, nhưng không cung cấp transaction xuyên nhiều request hoặc tránh mọi race condition.
- Dùng **LDAP server lab** để xác nhận hành vi thực tế, kết nối TLS đã xác minh chứng chỉ và tài khoản quyền tối thiểu. Không thử sửa nhóm hoặc danh bạ production chỉ để kiểm tra code.

### Tài liệu tham khảo

- [Spring LDAP Reference Documentation](https://docs.spring.io/spring-ldap/reference/)
- [Java SE 17 — JNDI ModificationItem](https://docs.oracle.com/en/java/javase/17/docs/api/java.naming/javax/naming/directory/ModificationItem.html)
- [Java SE 17 — JNDI DirContext](https://docs.oracle.com/en/java/javase/17/docs/api/java.naming/javax/naming/directory/DirContext.html)
- [RFC 4511 — LDAP Modify operation](https://www.rfc-editor.org/rfc/rfc4511)
- [RFC 4512 — LDAP Directory Information Models](https://www.rfc-editor.org/rfc/rfc4512)
- [RFC 4517 — LDAP Syntaxes and Matching Rules](https://www.rfc-editor.org/rfc/rfc4517)
