# Cập nhật thuộc tính bằng modifyAttributes

Trong dịch vụ thư mục LDAP, một entry người dùng có thể chứa họ tên, email, số điện thoại, nhóm và nhiều thuộc tính khác. Giả sử ứng dụng quản lý nhân sự chỉ cần đổi `description` của nhân viên Lan, trong khi entry còn các thuộc tính `uid`, `cn`, `sn`, `mail` và `objectClass`. Nếu ứng dụng xóa rồi tạo lại entry để cập nhật một trường, nó có thể làm hỏng DN, thuộc tính không được đưa vào bản ghi mới, quan hệ nhóm hoặc định danh nội tại của entry.

**`modifyAttributes` là cách cập nhật các thuộc tính cụ thể của một entry đang tồn tại.** Trong module **SPRING_DATA_LDAP**, Spring Data LDAP cung cấp repository và ánh xạ entry thành đối tượng Java, còn `LdapTemplate` của Spring LDAP cho phép kiểm soát trực tiếp các thay đổi qua `ModificationItem[]` hoặc `DirContextOperations`. Bài thuộc chương **Ghi dữ liệu**, tập trung vào cập nhật từng thuộc tính đúng schema, đúng DN và đúng quyền.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt `ADD_ATTRIBUTE`, `REPLACE_ATTRIBUTE` và `REMOVE_ATTRIBUTE` của JNDI/LDAP.
2. Tạo `ModificationItem` với `BasicAttribute` và gọi `LdapTemplate.modifyAttributes(Name, ModificationItem[])`.
3. Cập nhật một hoặc nhiều thuộc tính mà không thay thế toàn bộ entry; hiểu cách xử lý thuộc tính nhiều giá trị.
4. Sử dụng `lookupContext`, `DirContextOperations` và `modifyAttributes(DirContextOperations)` để tạo thay đổi dựa trên context đã đọc.
5. Chọn DN tương đối phù hợp với `spring.ldap.base`; tìm DN thực qua filter an toàn khi `uid` không phải RDN.
6. Nhận biết lỗi schema, ACL, giá trị trùng, tranh chấp cập nhật và trường hợp phản hồi thất lạc sau khi server đã ghi.
7. Kiểm thử thay đổi bằng `ldapsearch`, LDIF và một directory thử nghiệm.

## 2. Bài toán minh họa: chỉ thay đổi điều cần thiết

Giả sử LDAP server có entry theo schema `inetOrgPerson`:

~~~ldif
dn: uid=lan,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: lan
cn: Lan Nguyen
sn: Nguyen
mail: lan@example.org
description: Nhan vien phong ky thuat
telephoneNumber: +84-28-1111-2222
~~~

Yêu cầu nghiệp vụ: đổi `description` thành "Phu trach tich hop", giữ nguyên các thuộc tính khác. Đây là phép cập nhật thuộc tính, không phải đổi tên entry.

~~~mermaid
flowchart LR
    A["Entry LDAP hiện có"] --> B["ModificationItem<br/>REPLACE description"]
    B --> C["LdapTemplate.modifyAttributes"]
    C --> D["LDAP server kiểm tra<br/>DN, ACL, schema"]
    D --> E["Entry vẫn cùng DN<br/>chỉ description đổi"]
~~~

`modifyAttributes` tác động lên **một entry đã tồn tại** với một DN cụ thể. Không dùng phương thức này để tạo entry mới, đổi RDN hoặc di chuyển entry sang OU khác. Tạo entry thường dùng `bind` hoặc repository `save` trong luồng tạo mới; đổi DN dùng thao tác `rename`/Modify DN phù hợp.

### Ba thành phần phải đúng trước khi ghi

| Thành phần | Ví dụ | Ý nghĩa khi cập nhật |
| --- | --- | --- |
| **DN đích** | `uid=lan,ou=people,dc=example,dc=org` | Xác định entry nhận thay đổi. |
| **Thuộc tính hợp lệ theo schema** | `description`, `telephoneNumber` | Máy chủ quyết định có được sửa và số lượng giá trị hợp lệ hay không. |
| **Danh tính kết nối có quyền** | `cn=app-writer,ou=services,dc=example,dc=org` | ACL của directory quyết định có thể ghi thuộc tính đó hay không. |

Đọc thành công bằng tài khoản `app-reader` không chứng minh tài khoản này có quyền ghi. Đồng thời, người gọi HTTP đã đăng nhập cũng không tự động khiến `LdapTemplate` sử dụng DN của người đó; thông thường thao tác dùng tài khoản đã cấu hình trong `LdapContextSource`.

## 3. Ba thao tác cập nhật của JNDI

API JNDI `javax.naming.directory.DirContext` định nghĩa ba hằng số cập nhật. Spring LDAP nhận những hằng số này thông qua `ModificationItem`.

| Thao tác | Khi nào dùng | Tác động tới giá trị hiện có |
| --- | --- | --- |
| `DirContext.ADD_ATTRIBUTE` | Thêm một giá trị hoặc attribute chưa có. | Giữ các giá trị cũ; có thể thất bại nếu giá trị đã tồn tại hoặc attribute chỉ cho phép một giá trị. |
| `DirContext.REPLACE_ATTRIBUTE` | Đặt tập giá trị mới cho attribute. | Thay toàn bộ các giá trị hiện có bằng tập mới; attribute chưa tồn tại có thể được tạo. |
| `DirContext.REMOVE_ATTRIBUTE` | Xóa một số giá trị hoặc xóa cả attribute. | Có thể xóa một giá trị được chỉ định; khi không đưa giá trị nào thì xóa cả attribute. |

Ví dụ trên một attribute nhiều giá trị:

~~~text
Trước cập nhật:
telephoneNumber = { "+84-28-1111-2222", "+84-90-3333-4444" }

ADD "+84-93-5555-6666":
telephoneNumber = { "+84-28-1111-2222", "+84-90-3333-4444",
                    "+84-93-5555-6666" }

REPLACE "+84-28-9999-0000":
telephoneNumber = { "+84-28-9999-0000" }

REMOVE "+84-90-3333-4444" (nếu giá trị đang tồn tại):
telephoneNumber = { "+84-28-1111-2222" }  // từ trạng thái ban đầu

REMOVE không chỉ định giá trị:
telephoneNumber = (không còn attribute)
~~~

**Điểm dễ nhầm:** `REPLACE_ATTRIBUTE` với một giá trị mới **không phải “thêm hoặc sửa một giá trị trong danh sách”**. Đối với attribute nhiều giá trị, nó thay cả tập giá trị, dễ làm mất số điện thoại hoặc thành viên nhóm nếu không chủ ý.

Với attribute chỉ cho phép một giá trị theo schema server, `ADD_ATTRIBUTE` có thể thất bại nếu attribute đã tồn tại. Ví dụ `telephoneNumber` có thể nhiều giá trị trên một số server nhưng bị cấu hình/định nghĩa là đơn trị trong một số triển khai, đặc biệt cần kiểm tra schema Active Directory. **Không suy từ tên attribute rằng nó luôn là đa trị.**

Với `REMOVE_ATTRIBUTE`, server có thể trả lỗi nếu giá trị cần xóa không tồn tại; không mặc nhiên coi remove là idempotent trong mọi directory. Việc xóa một thuộc tính bắt buộc theo schema, chẳng hạn `sn` hoặc `cn` của lớp `person`, thông thường cũng không hợp lệ nếu kết quả cuối không đáp ứng schema.

## 4. Cấu hình Spring Boot để có `LdapTemplate`

Thêm Spring Data LDAP starter, ví dụ Gradle Kotlin DSL:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-ldap")
}
~~~

Trong `application.yml`:

~~~yaml
spring:
  ldap:
    urls:
      - ${LDAP_URL:ldaps://ldap.example.org:636}
    base: ${LDAP_BASE_DN:dc=example,dc=org}
    username: ${LDAP_BIND_DN}
    password: ${LDAP_BIND_PASSWORD}
~~~

Ví dụ các biến môi trường của **directory thử nghiệm**:

~~~dotenv
LDAP_URL=ldaps://ldap.example.org:636
LDAP_BASE_DN=dc=example,dc=org
LDAP_BIND_DN=cn=app-writer,ou=services,dc=example,dc=org
LDAP_BIND_PASSWORD=<secret-duoc-cap-rieng>
~~~

Spring Boot thường tự cấu hình `LdapContextSource` và `LdapTemplate` khi thư viện/cấu hình phù hợp. Các URL, DN và mật khẩu trên chỉ là mẫu. Muốn chạy ví dụ, server phải tồn tại, đã có cây LDAP và tài khoản bind được cấp ACL ghi chính xác.

**Về bảo mật:** dùng LDAPS hoặc StartTLS được cấu hình đúng và xác minh chứng chỉ máy chủ. `ldap://` đơn thuần không mã hóa mật khẩu. Không commit mật khẩu, không log credential và tránh dùng tài khoản quản trị directory cho một chức năng chỉ cần sửa `description`.

## 5. Cập nhật một thuộc tính bằng `ModificationItem`

Phương thức cơ bản của `LdapTemplate`:

~~~java
void modifyAttributes(
        javax.naming.Name dn,
        javax.naming.directory.ModificationItem[] mods);
~~~

Đây là chữ ký minh họa để nhận biết tham số. `dn` là DN **tương đối với base của context source** trong cấu hình Spring LDAP thường gặp. `mods` là mảng các thao tác thuộc tính được gửi đến server.

### 5.1. Ví dụ Java đầy đủ

~~~java
import javax.naming.Name;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;
import org.springframework.stereotype.Service;

@Service
public class PersonAttributeWriter {
    private final LdapTemplate ldapTemplate;

    public PersonAttributeWriter(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public void replaceDescription(String uid, String newDescription) {
        if (uid == null || uid.isBlank()) {
            throw new IllegalArgumentException("uid khong duoc rong");
        }
        if (newDescription == null || newDescription.isBlank()) {
            throw new IllegalArgumentException(
                    "description phai co gia tri");
        }

        // Với spring.ldap.base=dc=example,dc=org:
        // DN tương đối sẽ là uid=lan,ou=people.
        Name dn = LdapNameBuilder.newInstance("ou=people")
                .add("uid", uid)
                .build();

        ModificationItem change = new ModificationItem(
                DirContext.REPLACE_ATTRIBUTE,
                new BasicAttribute("description", newDescription));

        ldapTemplate.modifyAttributes(
                dn, new ModificationItem[] {change});
    }
}
~~~

Giải thích:

1. `LdapNameBuilder` tạo DN bằng các RDN được escape đúng cách; không nối input vào chuỗi `"uid=" + uid + ",ou=people"`.
2. `new BasicAttribute("description", newDescription)` đại diện attribute và giá trị mới.
3. `REPLACE_ATTRIBUTE` yêu cầu server thay giá trị `description` hiện tại; nếu attribute chưa có, server có thể tạo attribute đó nếu schema và ACL cho phép.
4. `modifyAttributes` gửi yêu cầu cập nhật tới entry mang DN đã chọn; không bắt buộc ứng dụng phải tải lại toàn bộ entry và ghi lại tất cả thuộc tính.

Đoạn mã giả định **RDN của entry người dùng là `uid`**. Điều này không đúng cho mọi directory: có nơi DN là `cn=...` hoặc dùng cấu trúc riêng. Nếu chỉ biết tên đăng nhập, hãy tìm DN thực trước khi gọi modify; cách làm ở mục 9.

### 5.2. Dùng String DN hay Name?

Spring LDAP hỗ trợ cả `modifyAttributes(String dn, ModificationItem[] mods)` và overload nhận `Name`. Khi DN có dữ liệu động, ưu tiên `Name`/`LdapNameBuilder` vì có cơ chế xử lý ký tự đặc biệt trong RDN. Không sử dụng **filter escaping** thay cho **DN escaping**; đây là hai ngữ cảnh cú pháp khác nhau.

## 6. Thêm, thay thế và xóa thuộc tính

Trong class `PersonAttributeWriter`, bạn có thể bổ sung các phương thức sau với cùng `ldapTemplate`.

### 6.1. Thêm một giá trị vào attribute đa trị

~~~java
public void addPhone(String uid, String phoneNumber) {
    if (phoneNumber == null || phoneNumber.isBlank()) {
        throw new IllegalArgumentException("So dien thoai khong hop le");
    }
    Name dn = LdapNameBuilder.newInstance("ou=people")
            .add("uid", uid).build();

    ModificationItem add = new ModificationItem(
            DirContext.ADD_ATTRIBUTE,
            new BasicAttribute("telephoneNumber", phoneNumber));

    ldapTemplate.modifyAttributes(dn, new ModificationItem[] {add});
}
~~~

Đoạn này chỉ hợp lệ nếu directory cho phép `telephoneNumber` nhiều giá trị, không vượt quy tắc schema và số đang thêm chưa tồn tại theo matching rule của server. Nếu cần xử lý yêu cầu lặp, nên đọc/xác minh trạng thái hoặc áp dụng chiến lược idempotency thích hợp trước khi retry.

### 6.2. Xóa đúng một giá trị

~~~java
public void removePhone(String uid, String phoneNumber) {
    Name dn = LdapNameBuilder.newInstance("ou=people")
            .add("uid", uid).build();

    ModificationItem remove = new ModificationItem(
            DirContext.REMOVE_ATTRIBUTE,
            new BasicAttribute("telephoneNumber", phoneNumber));

    ldapTemplate.modifyAttributes(dn, new ModificationItem[] {remove});
}
~~~

Chỉ định giá trị sau tên attribute nghĩa là **chỉ xóa giá trị đó**. Nếu số không tồn tại, một số server sẽ báo lỗi; nếu đây là thao tác được người dùng nhấn nhiều lần, hãy thiết kế xử lý lỗi hoặc kiểm tra trạng thái sau thao tác.

### 6.3. Xóa toàn bộ attribute

~~~java
public void removeDescription(String uid) {
    Name dn = LdapNameBuilder.newInstance("ou=people")
            .add("uid", uid).build();

    // BasicAttribute không có giá trị: xóa toàn bộ attribute.
    ModificationItem remove = new ModificationItem(
            DirContext.REMOVE_ATTRIBUTE,
            new BasicAttribute("description"));

    ldapTemplate.modifyAttributes(dn, new ModificationItem[] {remove});
}
~~~

Đừng nhầm `new BasicAttribute("description")` (không có giá trị) với `new BasicAttribute("description", "")` (một giá trị chuỗi rỗng). LDAP schema hoặc server có thể từ chối chuỗi rỗng; ý định xóa attribute cần được biểu diễn rõ.

### 6.4. Đổi nhiều thuộc tính của cùng entry

~~~java
public void updateContact(String uid, String description, String mail) {
    Name dn = LdapNameBuilder.newInstance("ou=people")
            .add("uid", uid).build();

    ModificationItem[] changes = {
        new ModificationItem(
                DirContext.REPLACE_ATTRIBUTE,
                new BasicAttribute("description", description)),
        new ModificationItem(
                DirContext.REPLACE_ATTRIBUTE,
                new BasicAttribute("mail", mail))
    };

    ldapTemplate.modifyAttributes(dn, changes);
}
~~~

Ở đây, `description` và `mail` được xem là giá trị **đã được validate và phải có**; ví dụ cần thêm kiểm tra input trong ứng dụng thật. Không gọi `new BasicAttribute("mail", null)` như một cách thay thế ngầm cho việc xóa email: hãy định nghĩa riêng thao tác xóa và ý nghĩa của giá trị vắng mặt.

Theo LDAPv3, **danh sách thay đổi trong một Modify request trên cùng entry được áp dụng theo thứ tự và như một thao tác nguyên tử**: hoặc áp dụng toàn bộ hoặc không áp dụng. Điều này **không tạo transaction bao nhiều entry**, không bao gồm database nghiệp vụ, và không đảm bảo rằng một thao tác đã thành công nhưng mất phản hồi sẽ được nhận biết chính xác ở phía client.

## 7. Cập nhật bằng `DirContextOperations`

Tạo mảng `ModificationItem` tường minh phù hợp khi chỉ biết DN và các thay đổi cần áp dụng. Nếu ứng dụng muốn đọc entry hiện tại rồi thay đổi các giá trị, Spring LDAP có cách thuận tiện hơn:

~~~java
import javax.naming.Name;
import org.springframework.ldap.core.DirContextOperations;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

public void updateWithContext(
        LdapTemplate ldapTemplate,
        String uid,
        String newDescription,
        String newPhone) {

    Name dn = LdapNameBuilder.newInstance("ou=people")
            .add("uid", uid).build();

    // Đọc context hiện có; adapter theo dõi các giá trị bị thay đổi.
    DirContextOperations ctx = ldapTemplate.lookupContext(dn);
    ctx.setAttributeValue("description", newDescription);
    ctx.addAttributeValue("telephoneNumber", newPhone);

    // Spring LDAP xây các ModificationItem từ những thay đổi của ctx.
    ldapTemplate.modifyAttributes(ctx);
}
~~~

`lookupContext(dn)` thường trả một `DirContextAdapter` ở trạng thái cập nhật. Adapter biết giá trị trước/sau và tính ra các `ModificationItem` cần thiết. `setAttributeValue` nhằm đặt một giá trị cho attribute, còn `addAttributeValue` thêm giá trị vào attribute, tránh gửi thay đổi trùng khi adapter biết giá trị đã tồn tại.

**Không tự tạo `new DirContextAdapter(dn)` rồi mặc định gọi `modifyAttributes(ctx)` sẽ có tác dụng như context vừa lookup.** Context phải được khởi tạo và ở *update mode* đúng cách. Cách đơn giản cho bài học là dùng `lookupContext`; khi tự khởi tạo adapter cho mục đích đặc biệt, cần đọc hợp đồng `setUpdateMode`/`getModificationItems` của phiên bản thư viện.

### `DirContextOperations` và thuộc tính chưa được tải

Adapter chỉ biết những attribute đã nhận về. Với **operational attribute** (ví dụ một số định danh do directory quản lý) hoặc attribute bị ACL ẩn, chúng có thể không có trong context. Khi đó một thao tác `removeAttributeValue(...)` dựa trên snapshot không có attribute có thể **không tạo modification nào**.

Nếu thực sự cần thay đổi một attribute được phép sửa nhưng không có trong snapshot, hãy xem xét yêu cầu attribute đó một cách tường minh ở bước đọc hoặc dùng `modifyAttributes(Name, ModificationItem[])` để mô tả thay đổi trực tiếp. Dù chọn cách nào, server vẫn kiểm tra ACL và schema; không cố sửa những operational attribute do server quản lý.

### Khi nào chọn mỗi cách?

| Nhu cầu | API phù hợp |
| --- | --- |
| Đổi một giá trị đã biết mà không cần đọc các field khác. | `modifyAttributes(Name, ModificationItem[])`. |
| Thêm hoặc xóa đúng một giá trị trong attribute nhiều giá trị. | `ModificationItem[]` tường minh. |
| Đọc entry, chỉnh nhiều field theo trạng thái hiện tại rồi gửi phần chênh lệch. | `lookupContext` + `DirContextOperations` + `modifyAttributes(ctx)`. |
| Quản lý entity theo annotation LDAP ODM và repository. | `@Entry`, `LdapRepository` hoặc cập nhật đối tượng theo API Spring Data LDAP. |
| Đổi DN/RDN hoặc chuyển nhánh trong DIT. | `rename`/Modify DN, không phải `modifyAttributes`. |

## 8. Mối liên hệ với `LdapRepository` và entity ODM

Spring Data LDAP có thể ánh xạ entry phân cấp sang Java object:

~~~java
import javax.naming.Name;
import org.springframework.ldap.odm.annotations.Attribute;
import org.springframework.ldap.odm.annotations.Entry;
import org.springframework.ldap.odm.annotations.Id;

@Entry(
    base = "ou=people",
    objectClasses = {"top", "person", "organizationalPerson", "inetOrgPerson"}
)
public class PersonEntry {
    @Id
    private Name dn;

    @Attribute(name = "uid")
    private String uid;

    @Attribute(name = "description")
    private String description;

    public Name getDn() { return dn; }
    public String getUid() { return uid; }
    public String getDescription() { return description; }
    public void setDescription(String value) { this.description = value; }
}
~~~

~~~java
import java.util.Optional;
import org.springframework.data.ldap.repository.LdapRepository;

public interface PersonRepository extends LdapRepository<PersonEntry> {
    Optional<PersonEntry> findByUid(String uid);
}
~~~

Repository giúp đọc entity và thực hiện những thao tác dữ liệu phổ biến. Khi yêu cầu chỉ thay đổi `description` của một DN đã biết, dùng `LdapTemplate.modifyAttributes` có lợi thế là **mô tả chính xác attribute phải cập nhật** mà không cần ánh xạ một entity có thể còn nhiều field khác.

Không coi `save` của repository là tương đương máy móc với một `ModificationItem(REPLACE_ATTRIBUTE, ...)`. Luồng CRUD của repository/ODM còn liên quan đến metadata `@Entry`, DN, thuộc tính đang ánh xạ và hành vi phiên bản thư viện. Hãy chọn API theo mục đích, kiểm tra dữ liệu được ghi và giới hạn trường có quyền sửa.

Annotation `@Id` trong ví dụ là `org.springframework.ldap.odm.annotations.Id` trên DN kiểu `javax.naming.Name`, không phải annotation JPA. Entry thực phải đáp ứng schema server; không tự mặc định mọi hệ thống dùng `inetOrgPerson`.

## 9. Khi chỉ biết username, phải tìm đúng DN trước

Ví dụ trên xây DN theo quy tắc `uid=lan,ou=people`. Trong directory khác, `uid` có thể chỉ là attribute tìm kiếm, còn DN của entry là `cn=Lan Nguyen,ou=staff,...`. Nếu ghép DN từ `uid` rồi gọi modify, yêu cầu có thể trỏ sai entry hoặc nhận lỗi `noSuchObject`.

Hãy tìm DN theo filter an toàn:

~~~java
import java.util.List;
import javax.naming.Name;
import org.springframework.ldap.core.ContextMapper;
import org.springframework.ldap.core.DirContextOperations;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;

public Name findUniqueDn(LdapTemplate ldapTemplate, String uid) {
    LdapQuery query = LdapQueryBuilder.query()
            .base("ou=people")
            .where("uid").is(uid);

    List<Name> matches = ldapTemplate.search(
            query,
            (ContextMapper<Name>) source ->
                ((DirContextOperations) source).getDn());

    if (matches.size() != 1) {
        throw new IllegalStateException(
                "Can dung mot entry: tim thay " + matches.size());
    }
    return matches.get(0);
}
~~~

Với `spring.ldap.base=dc=example,dc=org`, DN trả từ context được dùng tương đối với base phù hợp. Nếu search trả 0 hoặc nhiều hơn 1 entry, **không tự chọn entry đầu tiên để ghi**. `uid` không được mọi schema/server bảo đảm duy nhất trong toàn cây.

`where("uid").is(uid)` dùng query builder để escape giá trị filter. Không nối giá trị người dùng nhập vào filter thô như `"(uid=" + uid + ")"`. Nếu DN đổi giữa khi search và modify, server có thể báo không tồn tại; ứng dụng cần xử lý sự kiện này một cách an toàn.

## 10. Cập nhật thuộc tính đa trị và nhóm

Một số entry nhóm lưu danh sách DN thành viên trong `uniqueMember` hoặc `member` (tùy `objectClass` và schema). Ví dụ:

~~~ldif
dn: cn=developers,ou=groups,dc=example,dc=org
objectClass: top
objectClass: groupOfUniqueNames
cn: developers
uniqueMember: uid=lan,ou=people,dc=example,dc=org
~~~

Khi thêm một thành viên vào nhóm, nên dùng `ADD_ATTRIBUTE` với một DN hợp lệ thay vì `REPLACE_ATTRIBUTE` làm mất toàn bộ danh sách. Khi xóa một thành viên, dùng `REMOVE_ATTRIBUTE` với **giá trị DN cụ thể**; thao tác xóa không giá trị sẽ xóa cả membership attribute và có thể vi phạm schema nếu thuộc tính bắt buộc.

Một yêu cầu thêm thành viên:

~~~java
import javax.naming.Name;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;
import org.springframework.ldap.support.LdapNameBuilder;

Name groupDn = LdapNameBuilder.newInstance("ou=groups")
        .add("cn", "developers")
        .build();

// DN thành viên cần ở định dạng mà schema của directory yêu cầu.
String memberDn = "uid=lan,ou=people,dc=example,dc=org";
ModificationItem addMember = new ModificationItem(
        DirContext.ADD_ATTRIBUTE,
        new BasicAttribute("uniqueMember", memberDn));

ldapTemplate.modifyAttributes(
        groupDn, new ModificationItem[] {addMember});
~~~

Code này giả định `ldapTemplate` đã được inject và directory dùng `groupOfUniqueNames`/`uniqueMember`. Nếu server sử dụng `groupOfNames`/`member` hoặc quy ước riêng của Active Directory, phải đổi attribute và cách kiểm tra quyền nhóm cho phù hợp. Thao tác sửa nhóm có thể trực tiếp thay đổi khả năng truy cập tài nguyên; yêu cầu kiểm tra phân quyền quản trị, audit và xử lý độ trễ cache/replication.

Không tạo chuỗi DN thành viên trực tiếp từ input không tin cậy. Khi cần tạo DN động, dùng `LdapNameBuilder`; khi nhận DN từ nguồn ngoài, parse và validate theo quy tắc danh tính được phép liên kết.

## 11. Tính nguyên tử, đồng thời và retry khi ghi

### 11.1. Nguyên tử trong một Modify request

Một lần `modifyAttributes(dn, changes)` gửi danh sách sửa đổi **cùng một entry**. Theo LDAPv3, các thay đổi được xử lý đúng thứ tự và nguyên tử ở phía directory: một yêu cầu không được chấp nhận từng phần mà để lại trạng thái giữa chừng trái với toàn bộ danh sách sửa đổi.

Điều đó **không đồng nghĩa**:

- Có transaction ACID chung giữa LDAP và PostgreSQL hoặc các dịch vụ khác.
- Hai lần gọi `modifyAttributes` liên tiếp được gom thành một transaction.
- Tranh chấp giữa hai người sửa cùng thuộc tính sẽ được tự động phát hiện.
- Việc mất kết nối trước khi nhận phản hồi chứng tỏ thay đổi chưa áp dụng.

### 11.2. Tranh chấp cập nhật

Ví dụ hai admin đọc `description=A`. Admin 1 ghi `description=B`, sau đó admin 2 dựa trên dữ liệu cũ ghi `description=C`. Nếu không có kiểm soát đồng thời, giá trị cuối có thể là C và cập nhật B bị ghi đè.

Một số directory hỗ trợ LDAP Assertion Control (RFC 4528) hoặc cơ chế điều kiện/version do provider cung cấp, giúp thực hiện kiểm tra điều kiện tại server. **`LdapTemplate.modifyAttributes(...)` theo ví dụ trên không tự biến thành compare-and-swap có kiểm tra version.** Nếu cần bảo đảm không mất cập nhật, phải thiết kế cơ chế điều kiện/kiểm soát đồng thời phù hợp và kiểm thử server, JNDI controls hoặc API tích hợp được chọn.

Một chiến lược **read → compare → write** thuần client giúp phát hiện một số lỗi, nhưng **vẫn có khoảng đua (race)** giữa lần đọc và lần ghi. Đừng gọi đó là optimistic locking bảo đảm nếu server không kiểm tra điều kiện khi cập nhật.

### 11.3. Phản hồi thất lạc sau khi server đã ghi

Giả sử gửi `ADD_ATTRIBUTE` để thêm số điện thoại; server ghi thành công nhưng đường truyền bị ngắt trước khi client nhận response. Nếu tự động retry, yêu cầu lần hai có thể bị từ chối do giá trị đã tồn tại.

Với `REPLACE_ATTRIBUTE` đặt lại đúng một tập giá trị, việc lặp lại đôi khi có cùng kết quả cuối, nhưng vẫn phải cân nhắc ràng buộc, side effect và dữ liệu có thể được người khác cập nhật giữa hai lần thử. Với `REMOVE_ATTRIBUTE`, giá trị có thể đã bị xóa ở lần đầu; retry có thể trả lỗi.

Do đó:

1. Phân loại lỗi kết nối tạm thời khác với schema/ACL/validation error.
2. Khi kết quả ghi **không xác định**, đọc lại trạng thái trên server có thẩm quyền trước khi quyết định thực hiện lại.
3. Giới hạn retry, timeout và số lần kết nối; cân nhắc replication lag nếu có nhiều LDAP URL.
4. Không xem lỗi kết nối là lý do tự chuyển sang máy chủ thứ hai rồi lặp lại thao tác ghi một cách mù quáng.

## 12. Schema, ACL và an toàn cập nhật

### Schema giới hạn attribute có thể ghi

Directory có thể từ chối cập nhật khi:

- Cố xóa `cn` hoặc `sn` trong entry `person` mà schema vẫn yêu cầu.
- Ghi nhiều giá trị vào attribute đơn trị.
- Ghi sai kiểu dữ liệu/chuẩn hóa của attribute, ví dụ DN không hợp lệ hoặc giá trị nhị phân được gửi như chuỗi thông thường.
- Sửa `objectClass` làm entry không còn đáp ứng tập thuộc tính bắt buộc.
- Cố sửa operational attribute do server quản lý như `entryUUID`, `objectGUID` hoặc dấu thời gian do server sinh.

Không dùng `modifyAttributes` để đổi RDN bằng cách sửa một attribute bất kỳ. Đổi tên entry có thể cần thao tác Modify DN, đồng thời cập nhật các quan hệ DN tham chiếu tùy hệ thống.

### ACL và bảo mật kết nối

Tài khoản bind cần quyền **write** với đúng nhánh và thuộc tính. Việc đọc `telephoneNumber` không chứng minh được phép sửa nó; cũng không nên cấp quyền ghi `userPassword` hoặc nhóm quản trị chỉ vì ứng dụng sửa danh bạ.

Nếu giao diện HTTP cho phép sửa LDAP, thực hiện cả **xác thực/phân quyền tại API/service bằng Spring Security hoặc cơ chế tương ứng**, kiểm tra trường được phép sửa và **ACL tối thiểu tại directory**. Tránh endpoint chung nhận tùy ý tên thuộc tính từ client rồi truyền thẳng vào `BasicAttribute`; thay vào đó xây danh sách allowlist các trường nghiệp vụ được sửa.

Kết nối bằng LDAPS hoặc StartTLS, xác minh hostname/CA. Mật khẩu bind lưu qua secret manager, không đưa vào log hoặc mã nguồn. Cân nhắc audit các thay đổi ở cấp ứng dụng và server, nhưng giảm/ẩn nội dung nhạy cảm như số điện thoại cá nhân, token và thuộc tính bảo mật.

## 13. Đối chiếu bằng LDIF và công cụ LDAP

Một thay đổi `description` và thêm số điện thoại có thể biểu diễn ở dạng LDIF như sau:

~~~ldif
dn: uid=lan,ou=people,dc=example,dc=org
changetype: modify
replace: description
description: Phu trach tich hop
-
add: telephoneNumber
telephoneNumber: +84-90-3333-4444
~~~

LDIF này **minh họa cùng ngữ nghĩa** với mảng `ModificationItem[]` gồm `REPLACE_ATTRIBUTE` và `ADD_ATTRIBUTE`. Dấu `-` phân tách các nhóm thay đổi. Đây là dữ liệu thay đổi cho một entry, không phải lời gọi API Spring.

Trên một **directory thử nghiệm được cấp quyền ghi**, có thể dùng `ldapmodify` với một file LDIF do người thực hành chuẩn bị; không áp dụng trực tiếp lên directory thật khi chưa có quy trình xét duyệt.

Kiểm tra trước/sau bằng `ldapsearch`:

~~~bash
ldapsearch -LLL -x \
  -H "ldaps://ldap.example.org:636" \
  -D "cn=app-writer,ou=services,dc=example,dc=org" -W \
  -b "uid=lan,ou=people,dc=example,dc=org" -s base \
  "(objectClass=*)" dn uid cn sn mail description telephoneNumber
~~~

`-W` nhập mật khẩu tương tác để không lộ trực tiếp trên command line. Sau khi gọi code `replaceDescription`, chạy lại truy vấn và so sánh: `description` có giá trị mới, `cn`/`sn`/`mail` còn nguyên; DN không đổi.

Nếu công cụ dòng lệnh truy vấn được còn ứng dụng Java gặp TLS error, hãy kiểm tra truststore của JVM, vì `ldapsearch` và Java không nhất thiết dùng chung kho CA.

### Checklist kiểm thử thao tác ghi

| Kịch bản | Kết quả mong đợi |
| --- | --- |
| Đổi một `description` hợp lệ. | Chỉ attribute đích thay đổi; DN và các trường khác giữ nguyên. |
| `REPLACE_ATTRIBUTE` trên attribute chưa tồn tại. | Server tạo attribute nếu schema và ACL cho phép. |
| `ADD_ATTRIBUTE` với một số mới vào attribute đa trị. | Giá trị mới được thêm, các giá trị cũ vẫn còn. |
| `ADD_ATTRIBUTE` với giá trị đã có. | Server có thể từ chối; ứng dụng báo lỗi hoặc xử lý theo chính sách idempotency. |
| `REPLACE_ATTRIBUTE` với một số trên attribute đa trị. | Các số cũ bị thay bằng số mới; kiểm tra hành vi này có đúng yêu cầu. |
| `REMOVE_ATTRIBUTE` với đúng một giá trị. | Chỉ giá trị đó biến mất; các giá trị còn lại được giữ. |
| `REMOVE_ATTRIBUTE` không chỉ định giá trị. | Attribute bị xóa nếu schema/ACL cho phép. |
| Cố xóa `sn` bắt buộc. | Server từ chối vì vi phạm schema. |
| Tài khoản chỉ có quyền đọc thực hiện modify. | Server từ chối vì thiếu ACL ghi. |
| DN đích không tồn tại hoặc bị rename. | Có lỗi tương ứng; không tự ghi sang entry khác. |
| Mất kết nối ngay sau khi gửi modify. | Phản hồi được coi là không xác định; cần đối soát, không tự retry mù quáng. |
| Hai người đồng thời sửa cùng một trường. | Kiểm tra chính sách kiểm soát tranh chấp và khả năng mất cập nhật. |

## 14. Chẩn đoán lỗi khi gọi `modifyAttributes`

| Dấu hiệu | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| LDAP result code **32** (`noSuchObject`) | DN sai, base DN không đúng hoặc entry vừa bị đổi tên/xóa. | Đối chiếu DN với `ldapsearch -s base`; tìm DN thực qua filter an toàn. |
| LDAP result code **50** (`insufficientAccessRights`) | Tài khoản bind thiếu quyền ghi attribute hoặc nhánh. | Kiểm tra ACL của server và quyền dịch vụ. |
| LDAP result code **65** (`objectClassViolation`) | Ghi/xóa làm entry vi phạm các ràng buộc `objectClass`. | Đối chiếu schema và các thuộc tính bắt buộc. |
| LDAP result code **19** (`constraintViolation`) | Giá trị hoặc ràng buộc không hợp lệ theo server. | Kiểm tra cú pháp, matching rule, số lượng giá trị và chính sách directory. |
| LDAP result code **20** (`attributeOrValueExists`) | Thêm attribute hoặc giá trị đã tồn tại. | Dùng đúng ADD/REPLACE; cân nhắc thao tác idempotent. |
| LDAP result code **16** (`noSuchAttribute`) | Xóa attribute/giá trị không có, tùy ngữ nghĩa server. | Kiểm tra trạng thái trước/sau và chính sách xử lý giá trị vắng. |
| `SSLHandshakeException` hoặc timeout | Lỗi TLS, mạng, hostname hoặc truststore. | Xác minh kết nối an toàn; kết quả ghi có thể chưa xác định nếu lỗi sau khi gửi. |
| Không thấy thay đổi khi dùng context adapter. | Không có modification được tạo vì giá trị không đổi hoặc attribute chưa được tải. | Xem cách `lookupContext`, projection và `getModificationItems` hoạt động. |
| Thay đổi ngoài ý muốn trên attribute đa trị. | Dùng REPLACE khi thực ra cần ADD/REMOVE một giá trị. | Chọn operation chính xác; kiểm thử giá trị cũ được giữ. |

Mã lỗi LDAP và cách Spring chuyển thành exception cụ thể có thể khác nhau theo phiên bản, server và hoàn cảnh. Không trả toàn bộ DN, credential hoặc stack trace từ lỗi server cho client HTTP; chuẩn hóa phản hồi tại service/controller.

## 15. Bài tập thực hành

Directory thử nghiệm có base `dc=company,dc=internal`. Entry nhân viên:

~~~ldif
dn: uid=mai,ou=employees,dc=company,dc=internal
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: mai
cn: Mai Le
sn: Le
description: Nhan vien
telephoneNumber: +84-28-1111-2222
telephoneNumber: +84-90-3333-4444
~~~

Yêu cầu:

1. Viết `Name` tương đối với `spring.ldap.base=dc=company,dc=internal` để trỏ tới entry `mai`, dùng `LdapNameBuilder`.
2. Tạo một `ModificationItem(REPLACE_ATTRIBUTE, ...)` đặt `description` thành "Truong nhom".
3. Tạo `ModificationItem(ADD_ATTRIBUTE, ...)` thêm số `+84-93-8888-9999` mà vẫn giữ hai số đang có.
4. Tạo `ModificationItem(REMOVE_ATTRIBUTE, ...)` để xóa **chỉ** số `+84-90-3333-4444`.
5. Giải thích điều gì xảy ra nếu thay số điện thoại bằng `REPLACE_ATTRIBUTE` chứa duy nhất số mới.
6. Giải thích vì sao không được xóa `sn`, sửa DN bằng `REPLACE_ATTRIBUTE` cho `uid` hoặc retry ghi ngay khi bị timeout mà chưa đối soát.
7. Nếu directory thật dùng DN `cn=Mai Le,ou=employees,...` nhưng có `uid=mai`, sửa cách xác định DN trước khi cập nhật.

**Gợi ý đáp án:**

- DN tương đối: `uid=mai,ou=employees`. Có thể dựng bằng `LdapNameBuilder.newInstance("ou=employees").add("uid", "mai").build()`.
- Thay mô tả: `new ModificationItem(DirContext.REPLACE_ATTRIBUTE, new BasicAttribute("description", "Truong nhom"))`.
- Thêm số: `new ModificationItem(DirContext.ADD_ATTRIBUTE, new BasicAttribute("telephoneNumber", "+84-93-8888-9999"))`.
- Xóa một số: `new ModificationItem(DirContext.REMOVE_ATTRIBUTE, new BasicAttribute("telephoneNumber", "+84-90-3333-4444"))`.
- REPLACE với một số sẽ thay cả tập giá trị cũ. Xóa `sn` vi phạm schema `person`. Đổi RDN phải dùng Modify DN; khi chỉ biết `uid` cần search DN thực. Timeout có thể xảy ra sau khi server ghi thành công nên cần kiểm tra trạng thái trước khi retry.

## 16. Ghi nhớ

`LdapTemplate.modifyAttributes` giúp ứng dụng Spring Data LDAP **ghi đúng phần thuộc tính cần thay đổi trên một entry LDAP**. Với `ModificationItem[]`, bạn chỉ định rõ **ADD**, **REPLACE** hay **REMOVE**; với `DirContextOperations`, Spring LDAP có thể tính các thay đổi dựa trên context vừa đọc. Đặc biệt với thuộc tính đa trị, hãy luôn phân biệt “thêm một giá trị” với “thay toàn bộ giá trị”.

Một thao tác sửa tốt cần: **DN đúng**, **schema cho phép**, **ACL ghi phù hợp**, **filter/DN được xây an toàn**, **TLS tin cậy**, **xử lý tranh chấp**, và **kiểm thử trước/sau**. LDAP Modify trên một entry có tính nguyên tử theo giao thức, nhưng không thay thế transaction xuyên hệ thống hoặc chiến lược đối soát khi phản hồi ghi không rõ kết quả.

### Tài liệu tham khảo

- [Spring LDAP Reference — Basic Usage / Updating by Using modifyAttributes](https://docs.spring.io/spring-ldap/reference/spring-ldap-basic-usage.html)
- [Spring LDAP Reference — DirContextAdapter](https://docs.spring.io/spring-ldap/reference/dirobjectfactory.html)
- [Spring LDAP API — LdapTemplate](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/LdapTemplate.html)
- [Java SE 17 API — DirContext](https://docs.oracle.com/en/java/javase/17/docs/api/java.naming/javax/naming/directory/DirContext.html)
- [Java JNDI Tutorial — Modify Attributes](https://docs.oracle.com/javase/tutorial/jndi/ops/modattrs.html)
- [RFC 4511 — LDAPv3 Modify Operation](https://www.rfc-editor.org/rfc/rfc4511#section-4.6)
- [RFC 4528 — LDAP Assertion Control](https://www.rfc-editor.org/rfc/rfc4528)
