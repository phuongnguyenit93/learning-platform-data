# Update object và phát hiện thay đổi attribute trong Spring LDAP ODM

Trong Spring LDAP, **Object-Directory Mapping (ODM)** giúp ánh xạ một LDAP entry thành Java object có chú thích, rồi ghi thay đổi trở lại directory thông qua `LdapTemplate.update(Object)`. Ví dụ, nhân viên đổi tên hiển thị, bộ phận nhân sự cập nhật mô tả, hoặc hệ thống quản lý bổ sung email. Với ODM, lập trình viên sửa field trên Java object và gọi `update` thay vì tự lắp ghép từng `ModificationItem`.

Tuy nhiên, **phát hiện thay đổi attribute** trong ODM cần được hiểu chính xác. `LdapTemplate.update` sẽ **đọc trạng thái hiện tại của entry từ LDAP**, so sánh với những giá trị được ánh xạ từ object và tính ra các thao tác sửa đổi cần thiết. Nó không vận hành như một persistence context của JPA/Hibernate tự theo dõi mọi setter trên một object đã được quản lý. Vì vậy, gửi một object chỉ chứa một vài field hoặc dùng object cũ trong môi trường ghi đồng thời có thể tạo thay đổi ngoài dự kiến.

Bài học thuộc chương **ODM operations**, tập trung vào luồng update, cách xác định attribute nào thật sự khác nhau, các quy tắc mapping cần chú ý và cách kiểm thử để cập nhật dữ liệu thư mục một cách an toàn.

## 1. Từ LDAP entry đến Java object

Giả sử directory có entry:

~~~ldif
dn: uid=an,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: an
cn: An Nguyen
sn: Nguyen
description: Backend developer
mail: an.work@example.org
mail: an.personal@example.org
~~~

Ứng dụng muốn đổi `description` thành `Senior backend developer` nhưng giữ nguyên tên và hai email. Nếu thực hiện bằng JNDI, lập trình viên có thể tạo một `ModificationItem` với phép `REPLACE_ATTRIBUTE`. Với ODM, có thể dùng:

~~~java
EmployeeEntry person = ldapTemplate.findByDn(dn, EmployeeEntry.class);
person.setDescription("Senior backend developer");
ldapTemplate.update(person);
~~~

Ở trường hợp không đổi DN, cơ chế update của Spring LDAP dựa trên dữ liệu hiện tại trong directory và những field được ánh xạ để sinh các `ModificationItem` tương ứng. Đây là tiện ích đáng giá, nhưng cần phân biệt **giá trị được đưa vào object** với **những giá trị thật sự đã thay đổi trên server**.

## 2. Cơ chế update của LdapTemplate

Spring LDAP cung cấp các thao tác ODM qua `LdapOperations` / `LdapTemplate`:

| API | Vai trò |
| --- | --- |
| `findByDn(Name, Class<T>)` | Đọc một entry theo DN và ánh xạ thành entity |
| `find(LdapQuery, Class<T>)` | Tìm nhiều entity theo LDAP query |
| `create(Object)` | Tạo LDAP entry từ entity |
| `update(Object)` | Cập nhật entry đã tồn tại dựa trên metadata ODM |
| `delete(Object)` | Xóa entry được xác định bởi entity |

Theo JavaDoc `LdapTemplate.update(Object)`, ở **đường cập nhật thông thường khi DN không đổi**, quy trình có thể hình dung như sau:

~~~mermaid
flowchart TD
    A["Java entity với các field mong muốn"] --> B["Xác định DN từ @Id hoặc @DnAttribute"]
    B --> C{"DN tính ra khác DN hiện tại?"}
    C -->|Không| D["Đọc entry hiện tại từ LDAP"]
    D --> E["ODM ánh xạ field thành các thuộc tính mong muốn"]
    E --> F["So sánh với trạng thái LDAP vừa đọc"]
    F --> G["Tạo ModificationItem cho các khác biệt"]
    G --> H["Gửi modifyAttributes đến LDAP server"]
    C -->|Có| I["Nhánh di chuyển entry theo cơ chế ODM"]
    I --> J["Cần xem xét unbind/bind và rủi ro riêng"]
~~~

Những kết luận thực tế:

1. **Đối tượng Java không giữ một “bản gốc” tự động để đánh dấu dirty field như JPA.** Việc so sánh xảy ra với dữ liệu được đọc lại từ directory trong quá trình `update`.
2. **Chỉ các field được ODM quản lý mới tham gia ánh xạ.** `@Transient` loại một field khỏi thao tác lưu; `@Attribute` cho biết tên attribute trên LDAP khi khác với tên field.
3. **Không phải field nào được gán setter cũng chắc chắn sinh thay đổi LDAP.** Nếu giá trị mong muốn đã giống giá trị server, bộ tính chênh lệch có thể không tạo phép sửa đổi cho field đó.
4. **Mảng thay đổi là chi tiết thực thi, không phải hợp đồng “mỗi setter tạo đúng một REPLACE”.** Với nhiều giá trị, thuật toán có thể xét tập giá trị và tính thay đổi tương ứng.
5. **DN có quy tắc riêng.** Nếu cấu hình `@DnAttribute` cho phép tính DN và DN tính được khác `@Id`, JavaDoc mô tả nhánh **di chuyển entry bằng unbind rồi bind**. Đây là luồng khác với modify thuộc tính thông thường.

Spring LDAP xử lý cơ chế này qua `ObjectDirectoryMapper`, `DirContextAdapter`/`DirContextOperations` và những phương thức modify của `LdapTemplate`. Không nên tự diễn giải một lần gọi `update` là transaction bao trùm nhiều entry hoặc là optimistic locking.

## 3. Định nghĩa entity ODM rõ ràng

Một entity tối thiểu phải có `@Entry` và `@Id`. Ví dụ dưới đây dùng thêm `@Attribute` để ánh xạ đúng tên LDAP, `@Transient` cho field chỉ phục vụ giao diện.

~~~java
import java.util.Set;
import javax.naming.Name;

import org.springframework.ldap.odm.annotations.Attribute;
import org.springframework.ldap.odm.annotations.Entry;
import org.springframework.ldap.odm.annotations.Id;
import org.springframework.ldap.odm.annotations.Transient;

@Entry(
    base = "ou=people",
    objectClasses = {
        "inetOrgPerson", "organizationalPerson", "person", "top"
    }
)
public class EmployeeEntry {

    @Id
    private Name dn;

    @Attribute(name = "uid")
    private String uid;

    @Attribute(name = "cn")
    private String fullName;

    @Attribute(name = "sn")
    private String surname;

    @Attribute(name = "description")
    private String description;

    @Attribute(name = "mail")
    private Set<String> emails;

    @Transient
    private boolean selectedInUi;

    public EmployeeEntry() {
    }

    public Name getDn() {
        return dn;
    }

    public void setDn(Name dn) {
        this.dn = dn;
    }

    public String getUid() {
        return uid;
    }

    public void setUid(String uid) {
        this.uid = uid;
    }

    public String getFullName() {
        return fullName;
    }

    public void setFullName(String fullName) {
        this.fullName = fullName;
    }

    public String getSurname() {
        return surname;
    }

    public void setSurname(String surname) {
        this.surname = surname;
    }

    public String getDescription() {
        return description;
    }

    public void setDescription(String description) {
        this.description = description;
    }

    public Set<String> getEmails() {
        return emails;
    }

    public void setEmails(Set<String> emails) {
        this.emails = emails;
    }

    public boolean isSelectedInUi() {
        return selectedInUi;
    }

    public void setSelectedInUi(boolean selectedInUi) {
        this.selectedInUi = selectedInUi;
    }
}
~~~

Các điểm cần hiểu:

- `@Id` chứa DN với kiểu `javax.naming.Name`. Nếu `ContextSource` đặt base `dc=example,dc=org`, DN truyền cho `LdapTemplate` thông thường là DN **tương đối** như `uid=an,ou=people`.
- `@Entry(objectClasses = ...)` khai báo object class thuộc phạm vi mapping. Cần bao gồm các class phù hợp với những attribute muốn quản lý; chọn class theo schema thực tế của server.
- Tên Java `fullName` được ánh xạ sang LDAP `cn`, tên `emails` được ánh xạ sang `mail`. Nếu không có `@Attribute`, Spring LDAP thường mặc định dùng tên field làm tên LDAP attribute.
- `selectedInUi` không được ghi xuống LDAP vì có `@Transient`.
- `Set<String>` phù hợp để biểu diễn `mail` đa trị vì thứ tự các giá trị thuộc tính LDAP thường không có ý nghĩa. Hãy kiểm tra converter phù hợp cho kiểu collection trên phiên bản Spring LDAP đang dùng.

Ví dụ không dùng `@DnAttribute` cho DN để tránh vô tình kích hoạt cơ chế di chuyển khi chỉ cần cập nhật thuộc tính.

## 4. Ví dụ hoàn chỉnh: đọc, sửa và update

Service dưới đây nhận UID từ nghiệp vụ, đọc entity trước khi cập nhật `description`, gọi `update`, rồi đọc lại để xác nhận giá trị. Giả định `ContextSource` có base DN `dc=example,dc=org`, đã kết nối qua TLS và tài khoản bind có quyền đọc/ghi tại `ou=people`.

~~~java
import javax.naming.Name;

import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;
import org.springframework.stereotype.Service;

@Service
public class EmployeeDirectoryService {

    private final LdapTemplate ldapTemplate;

    public EmployeeDirectoryService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public EmployeeEntry changeDescription(
            String uid, String newDescription) {

        if (newDescription == null || newDescription.isBlank()) {
            throw new IllegalArgumentException("description không được rỗng");
        }

        Name dn = userDn(uid);
        EmployeeEntry person =
            ldapTemplate.findByDn(dn, EmployeeEntry.class);

        person.setDescription(newDescription);
        ldapTemplate.update(person);

        // Xác nhận trạng thái quan sát được sau update.
        EmployeeEntry confirmed =
            ldapTemplate.findByDn(dn, EmployeeEntry.class);
        if (!newDescription.equals(confirmed.getDescription())) {
            throw new IllegalStateException(
                "LDAP update đã gọi nhưng giá trị đọc lại không khớp"
            );
        }
        return confirmed;
    }

    private static Name userDn(String uid) {
        if (uid == null || uid.isBlank()) {
            throw new IllegalArgumentException("uid không được rỗng");
        }
        return LdapNameBuilder.newInstance()
            .add("ou", "people")
            .add("uid", uid)
            .build();
    }
}
~~~

Khi `findByDn` hoặc `update` báo lỗi (ví dụ DN không tồn tại, không đủ quyền, lỗi schema, lỗi TLS), `LdapTemplate` sẽ ném ngoại lệ tương ứng; ứng dụng phải xử lý ở tầng nghiệp vụ. `update` trả `void`, nên đọc lại là **bước kiểm chứng tùy nhu cầu**, không phải chứng nhận tuyệt đối rằng không có tiến trình khác sửa dữ liệu sau thời điểm đọc. Nếu có replication, lần đọc có thể đến replica chậm đồng bộ.

Khi muốn **xóa description tùy chọn**, có thể dùng một workflow riêng đặt field đó thành `null` và cập nhật, sau khi đã xác nhận mapping/schema và cách chuyển đổi `null` của phiên bản đang dùng. Không nên biến một chuỗi trắng hoặc một field bị bỏ qua trong request thành lệnh xóa một cách ngầm định.

## 5. Phát hiện thay đổi: “giá trị Java khác giá trị LDAP hiện tại”

Giả sử trạng thái LDAP tại thời điểm `update` đọc entry là:

~~~text
cn          = An Nguyen
description = Backend developer
mail        = {an.work@example.org, an.personal@example.org}
~~~

Các thay đổi dự kiến của object:

| Giá trị entity đưa vào update | So với trạng thái LDAP hiện tại | Ý nghĩa |
| --- | --- | --- |
| `description = "Senior backend developer"` | Khác `Backend developer` | Cần cập nhật description |
| `description = "Backend developer"` | Bằng hiện tại | Không cần thay đổi description |
| `mail = {work, personal, alt}` | Có thêm email mới | Cần cập nhật tập mail |
| `mail = {work}` | Thiếu email personal | Email personal có thể bị gỡ khỏi LDAP |
| `selectedInUi = true` | Field `@Transient` | Không tham gia so sánh attribute LDAP |
| `dn` không đổi | Không thay đổi vị trí | Đi theo nhánh sửa thuộc tính thông thường |

Đừng dựa vào số lần gọi setter để suy ra số thao tác LDAP. Ví dụ, lời gọi `person.setDescription(person.getDescription())` không làm nội dung khác đi; ngược lại, một object được dựng từ dữ liệu cũ có thể **khác với trạng thái mới trên server** dù ứng dụng không chủ ý sửa field đó.

### 5.1. Cập nhật tập giá trị đa trị

Với thuộc tính `mail` gồm nhiều giá trị, nên thao tác trên **tập đầy đủ** thay vì chỉ gán một giá trị nếu nghiệp vụ là “thêm email, giữ email cũ”:

~~~java
EmployeeEntry person = ldapTemplate.findByDn(dn, EmployeeEntry.class);

Set<String> next = new java.util.HashSet<>(
    person.getEmails() == null ? Set.of() : person.getEmails()
);
next.add("an.project@example.org");

person.setEmails(next);
ldapTemplate.update(person);
~~~

Nếu chỉ gán `Set.of("an.project@example.org")` vào `emails`, object mô tả **toàn bộ tập mới** gồm một email; dữ liệu email cũ có nguy cơ bị xóa khi ODM đồng bộ hóa thuộc tính. Để chỉ thêm một giá trị trong môi trường có nhiều tiến trình cập nhật, hãy cân nhắc dùng `ModificationItem` với `ADD_ATTRIBUTE` trực tiếp, đồng thời xử lý trường hợp giá trị đã tồn tại.

Spring LDAP còn hỗ trợ kiểu `Set<Name>` để ánh xạ các thuộc tính tham chiếu DN trong nhóm; khi cập nhật các tập DN, ODM có cơ chế so sánh theo sự bằng nhau của DN thay vì chỉ so chuỗi biểu diễn. Cần kiểm thử thực tế với schema, canonical DN và converter của server.

## 6. Xem thay đổi cụ thể bằng DirContextAdapter

Nếu cần **quan sát danh sách attribute dự kiến thay đổi trước khi gửi**, sử dụng tầng thấp hơn với `DirContextOperations` / `DirContextAdapter`. Adapter khi ở update mode có thể xác định các thuộc tính thay đổi qua `getNamesOfModifiedAttributes()` và tạo `ModificationItem[`] bằng `getModificationItems()`.

~~~java
import java.util.Arrays;
import javax.naming.Name;
import javax.naming.directory.ModificationItem;

import org.springframework.ldap.core.DirContextOperations;
import org.springframework.ldap.core.LdapTemplate;

public void updateDescriptionWithVisibleDiff(
        LdapTemplate template, Name dn, String newDescription) {

    DirContextOperations context = template.lookupContext(dn);
    context.setAttributeValue("description", newDescription);

    String[] names = context.getNamesOfModifiedAttributes();
    ModificationItem[] items = context.getModificationItems();

    // Chỉ ghi tên thuộc tính, không log dữ liệu LDAP nhạy cảm.
    System.out.println("Modified attributes: " + Arrays.toString(names));

    if (items.length > 0) {
        template.modifyAttributes(context);
    }
}
~~~

**Lưu ý:** đây là API cập nhật qua `DirContextAdapter`, không phải cách lấy trực tiếp danh sách sửa đổi từ một `EmployeeEntry` của ODM. Cả hai cùng sử dụng ý tưởng so sánh trạng thái thuộc tính, nhưng `LdapTemplate.update(Object)` không trả về `ModificationItem[`] để caller xem hoặc phê duyệt. Nếu yêu cầu là preview chính xác mọi phép sửa đổi của một object trước khi update, cần thiết kế luồng riêng để tính/kiểm tra khác biệt và quản lý nguy cơ trạng thái server thay đổi trước khi ghi.

Không coi việc đọc `names` như bằng chứng đã ghi thành công. Chỉ sau khi `modifyAttributes` không báo lỗi và khi cần đã đọc lại, ta mới có căn cứ để mô tả trạng thái đã quan sát.

## 7. ODM update khác với PATCH một attribute

Giả sử API HTTP nhận payload:

~~~json
{
  "description": "Senior backend developer"
}
~~~

Nếu tạo một `EmployeeEntry` mới, chỉ gán `dn` và `description`, các field `cn`, `sn`, `mail`, `uid` có thể là `null`. Gọi `ldapTemplate.update(partialObject)` trong tình huống này **nguy hiểm**: ODM có thể xem những giá trị thiếu trong object là trạng thái mong muốn và làm mất dữ liệu đã lưu. Nó **không tự hiểu** rằng field không có trong HTTP payload nghĩa là “giữ nguyên”.

Hai cách thực hiện phổ biến:

**A. Đọc full entity, sửa field cần thiết, update entity**

~~~java
EmployeeEntry person = ldapTemplate.findByDn(dn, EmployeeEntry.class);
person.setDescription(newDescription);
ldapTemplate.update(person);
~~~

Cách này dễ đọc khi entity được ánh xạ đầy đủ và số lượng thuộc tính quản lý vừa phải. Tuy nhiên, do có hai lần đọc/ghi khác nhau và object có thể cũ so với server, cần xem xét cập nhật đồng thời.

**B. Chỉ gửi đúng attribute cần sửa**

~~~java
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;

ModificationItem[] changes = {
    new ModificationItem(
        DirContext.REPLACE_ATTRIBUTE,
        new BasicAttribute("description", newDescription)
    )
};
ldapTemplate.modifyAttributes(dn, changes);
~~~

Ở cách B, thao tác ghi thể hiện rõ chỉ định cập nhật `description`, nên hợp lý với API kiểu PATCH, các thuộc tính nhạy cảm hoặc trường hợp cần tránh ghi đè những field không liên quan. Vẫn cần xử lý quyền ghi, schema, kiểm tra dữ liệu và lỗi cạnh tranh cập nhật.

| Nhu cầu | Cách cân nhắc | Điều cần kiểm soát |
| --- | --- | --- |
| Cập nhật object đầy đủ, mô hình ổn định | `LdapTemplate.update(entity)` | Mapping của toàn bộ field, DN, xung đột đồng thời |
| Chỉ sửa một attribute có phạm vi rõ | `modifyAttributes(dn, mods)` | Chỉ định phép ADD / REPLACE / REMOVE chính xác |
| Muốn quan sát thay đổi trước ghi | `lookupContext` + `DirContextOperations` | Khoảng thời gian giữa đọc/so sánh/ghi |
| Chuyển entry sang DN khác | Workflow rename/move riêng | Bảo toàn entry, tham chiếu DN, tính nguyên tử, quyền |

## 8. Cập nhật đồng thời: trường hợp dễ bị mất dữ liệu

Điểm khó của ODM nằm ở việc `update` so sánh **object gửi vào** với **entry đang tồn tại trên server**. Giả sử:

~~~text
T0: LDAP có cn = "An Nguyen", description = "Backend developer".
T1: Client A đọc object: cn = "An Nguyen".
T2: Client B sửa LDAP: cn = "An N.", description không đổi.
T3: Client A chỉ gọi setDescription("Senior backend developer").
T4: Client A gọi ldapTemplate.update(object đọc ở T1).
~~~

Ở T4, object A vẫn giữ `cn = "An Nguyen"`, trong khi server có `cn = "An N."`. Phần so sánh ODM có thể xem đây là **một khác biệt cần ghi**, qua đó đưa `cn` về giá trị cũ và làm mất cập nhật của B. Đây là dạng **lost update**; ODM không tự cung cấp optimistic locking như `@Version` của JPA.

Để giảm rủi ro:

1. **Giới hạn attribute có quyền sửa** theo nghiệp vụ và tránh gửi object dựng dở.
2. **Ưu tiên sửa đúng field** bằng `ModificationItem` khi chỉ cần cập nhật một thuộc tính.
3. **Kiểm soát phiên bản hoặc điều kiện ghi** nếu directory hỗ trợ. Có thể xem LDAP assertion control (RFC 4528), dùng control/extension phù hợp với server hoặc cơ chế ứng dụng; điều này cần thiết kế riêng, không xuất hiện tự động trong `update(Object)`.
4. **Đọc lại để xác nhận** các thuộc tính cần bảo toàn lẫn thuộc tính mới. Đọc lại chỉ cho biết trạng thái quan sát, không thay thế cơ chế chống tranh chấp.
5. **Không retry mù quáng** khi request lỗi hoặc timeout: dữ liệu có thể đã được áp dụng ở lần đầu.

Nếu `@DnAttribute(index = ...)` được dùng để tính DN, thay đổi các field thuộc DN có thể kích hoạt **di chuyển entry**, theo JavaDoc có nhánh `unbind` rồi `bind`. Hai bước đó không tương đương một Modify DN nguyên tử và có thể ảnh hưởng tham chiếu, ACL, thuộc tính do server quản lý hoặc entry con. Với nghiệp vụ đổi OU/rename, hãy thiết kế và kiểm thử luồng riêng thay vì vô tình thay một field có tham gia DN.

## 9. Kiểm thử update và phát hiện thay đổi

Unit test ở tầng Java có thể kiểm tra việc service sửa đúng field và chọn đúng phương thức. Tuy nhiên, để khẳng định ODM sinh thay đổi LDAP như mong đợi, nên có **integration test** trên LDAP server thử nghiệm với schema và quyền gần giống hệ thống thật.

### 9.1. Ma trận kiểm thử

| Trạng thái ban đầu | Thao tác | Kỳ vọng khi đọc lại |
| --- | --- | --- |
| `description=A`, `cn=An` | Đổi description sang B | `description=B`, `cn=An` |
| `description=A` | Update object vẫn chứa A | Không có thay đổi nội dung LDAP ngoài dự kiến |
| `mail={a,b}` | Bổ sung c bằng cách tạo tập `{a,b,c}` | `mail={a,b,c}`, không mất a/b |
| `mail={a,b}` | Gán tập `{c}` | Chỉ còn c theo hợp đồng thay thế toàn bộ tập |
| `selectedInUi=false` | Đặt `selectedInUi=true` rồi update | Không có attribute `selectedInUi` trong LDAP |
| Entry có thuộc tính bắt buộc | Tạo object thiếu `cn`, gọi update | Phải được phát hiện và xử lý; không được coi là PATCH an toàn |
| Client A giữ object cũ | Client B sửa `cn` rồi A update description | Phát hiện nguy cơ ghi đè giá trị mới của B |
| Entry DN cũ khác DN tính từ `@DnAttribute` | Update object | Có thể đi nhánh move; xác minh DN, entry và hậu quả liên quan |
| Tài khoản bind không có quyền ghi | Update một field | Nhận lỗi quyền; không báo thành công |

### 9.2. Ví dụ kiểm thử tích hợp (khung minh họa)

Đoạn kiểm thử sau giả định test fixture đã cung cấp `LdapTemplate` trỏ tới LDAP test server và đã tạo entry `uid=an,ou=people,dc=example,dc=org`. Test đọc lại cả attribute đổi và attribute phải giữ:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import javax.naming.Name;
import org.junit.jupiter.api.Test;
import org.springframework.ldap.support.LdapNameBuilder;

class EmployeeOdmUpdateIntegrationTest {

    private final LdapTemplate ldapTemplate;

    // Ví dụ: test fixture sẽ inject ldapTemplate và seed dữ liệu LDAP.
    EmployeeOdmUpdateIntegrationTest(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    @Test
    void updateDescriptionKeepsOtherMappedValues() {
        Name dn = LdapNameBuilder.newInstance()
            .add("ou", "people")
            .add("uid", "an")
            .build();

        EmployeeEntry before = ldapTemplate.findByDn(dn, EmployeeEntry.class);
        String oldName = before.getFullName();
        var oldEmails = before.getEmails() == null
            ? java.util.Set.<String>of()
            : java.util.Set.copyOf(before.getEmails());

        before.setDescription("Senior backend developer");
        ldapTemplate.update(before);

        EmployeeEntry after = ldapTemplate.findByDn(dn, EmployeeEntry.class);
        assertEquals("Senior backend developer", after.getDescription());
        assertEquals(oldName, after.getFullName());
        assertEquals(oldEmails, after.getEmails());
    }
}
~~~

Đây là **khung minh họa**, cần cấu hình JUnit/Spring Test và fixture trong dự án trước khi chạy; chỉ truyền constructor như trên không tự khiến JUnit tạo được `LdapTemplate`. Hãy quản lý vòng đời entry test, dọn dữ liệu và không chạy trên production. Test cũng nên bổ sung trường hợp dữ liệu đa trị, thiếu thuộc tính, lỗi schema và ghi đồng thời có chủ đích.

### 9.3. Theo dõi attribute thật sự gửi qua mạng

Để kiểm chứng “chỉ field X thay đổi”, kiểm tra cả **trạng thái trước/sau** và **thao tác LDAP được ghi nhận** nếu cần. Có thể dùng audit log của LDAP test server hoặc công cụ bắt thao tác được phép trong môi trường kiểm thử. Chỉ kiểm tra Java object sau `setDescription` không cho biết server đã nhận phép `ADD_ATTRIBUTE`, `REPLACE_ATTRIBUTE` hay `REMOVE_ATTRIBUTE` nào. Không ghi mật khẩu, token, giá trị nhạy cảm vào log.

Khi dữ liệu bị chặn bởi ACL hoặc LDAP server tự chuẩn hóa giá trị, phép so sánh có thể cho kết quả khác dự kiến. Cần đối chiếu schema, matching rule, các field đa trị và quyền của bind account. Việc đọc lại trên replica cũng có thể bị ảnh hưởng bởi replication lag.

## 10. Lỗi và hiểu nhầm thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| `update` làm mất mail không có trong payload | Entity partial, field không được nạp nhưng vẫn tham gia mapping | Dùng full entity hoặc `modifyAttributes` cho field mục tiêu |
| Update description lại thay cả cn | Object cũ so với LDAP đang thay đổi bởi client khác | Kiểm soát đồng thời; cập nhật field cụ thể |
| Không thấy cập nhật ở server | Giá trị mới đã trùng giá trị cũ, ACL từ chối, hoặc đọc nhầm replica | Kiểm tra exception, trạng thái thực tế, endpoint và audit |
| Update kéo entry sang nhánh khác | Field tham gia `@DnAttribute` bị đổi làm DN tính ra khác | Tách quy trình rename/move, xác minh DN trước update |
| Object đã update nhưng không tự refresh | `update` trả `void`, entity Java không phải live view của LDAP | Đọc lại theo DN khi cần xác nhận dữ liệu |
| Lỗi schema khi ghi thuộc tính | `@Entry` không khớp objectClasses, attribute sai tên/kiểu hoặc thiếu trường bắt buộc | Rà soát schema, converter và objectClasses |
| Thao tác qua nhiều entry được coi là nguyên tử | Mỗi lời gọi update chỉ áp dụng cho entry mục tiêu | Thiết kế transaction/compensation riêng theo server |
| Không đọc được attribute nhưng gán null | ACL hoặc truy vấn không trả thuộc tính | Không suy luận null là yêu cầu xóa; kiểm tra quyền và mapping |

Trong Spring LDAP ODM, các ngoại lệ LDAP/JNDI được chuyển thành họ ngoại lệ runtime của Spring LDAP khi gọi qua `LdapTemplate`. Cần phân loại không tồn tại entry, thiếu quyền, trùng tên, vi phạm schema, kết nối/TLS và xung đột nghiệp vụ. Với trường nhạy cảm như `userPassword`, không nên cập nhật như field văn bản thông thường; dùng quy trình đổi mật khẩu được LDAP server của bạn hỗ trợ.

## 11. Bài tập vận dụng

Một entity `EmployeeEntry` được đọc lúc 09:00 có `cn="An Nguyen"`, `description="Backend developer"` và `mail={work,personal}`. Sau đó:

1. Ứng dụng đặt `description="Senior backend developer"` rồi gọi `update`. Trong trường hợp không có ghi đồng thời và DN không đổi, thuộc tính nào cần khác đi?
2. Ứng dụng tạo entity **mới**, chỉ gán `dn` và `description`, các field khác để `null`, rồi gọi `update`. Vì sao không được xem đây là PATCH một field?
3. Trước khi A gọi `update`, một ứng dụng khác đã sửa `cn` thành `An N.`. Mối nguy nào xuất hiện khi A vẫn dùng object cũ?
4. Để bổ sung email thứ ba nhưng giữ email trước đó, nên sửa collection như thế nào?
5. Một field được gắn `@Transient` có tạo LDAP attribute tương ứng sau `update` không?
6. Nếu thay đổi field `@DnAttribute` khiến DN tính ra khác, có được mặc định `update` chỉ gửi `modifyAttributes` không?
7. Nếu nghiệp vụ chỉ sửa `description`, khi nào nên chọn `ModificationItem(REPLACE_ATTRIBUTE, ...)`?

**Gợi ý:** (1) chỉ `description` cần khác khi các giá trị khác giữ nguyên; (2) các field chưa gán có thể bị hiểu là trạng thái mong muốn và làm mất attribute; (3) lost update, đưa `cn` về giá trị cũ; (4) đọc tập đầy đủ rồi thêm email, hoặc dùng ADD_ATTRIBUTE trực tiếp có kiểm soát; (5) không; (6) không, có thể đi nhánh move/unbind/bind; (7) khi cần PATCH rõ phạm vi, tránh ảnh hưởng các attribute không liên quan hoặc có nguy cơ ghi đồng thời.

## 12. Ghi nhớ

- `LdapTemplate.update(Object)` cập nhật một LDAP entry dựa trên metadata ODM, **đọc trạng thái hiện tại** và tính chênh lệch giữa LDAP với dữ liệu entity.
- Cơ chế này **không phải dirty tracking kiểu JPA**: Java object cũ hoặc partial object có thể dẫn đến khác biệt ngoài ý định.
- `@Entry`, `@Id`, `@Attribute`, `@Transient` và `@DnAttribute` quyết định đối tượng nào và attribute nào tham gia ánh xạ. DN có quy tắc update/move riêng.
- Với thuộc tính đa trị, hãy nghĩ tới **toàn bộ tập giá trị**; thay tập bằng một phần tử có thể xóa các giá trị khác.
- Nếu chỉ muốn sửa một thuộc tính, `modifyAttributes(dn, ModificationItem[])` thường biểu đạt thao tác rõ ràng hơn. `DirContextAdapter` cho phép xem `getModificationItems()` trước khi gửi cập nhật.
- ODM không tự bảo đảm optimistic locking, snapshot xuyên nhiều lời gọi hay tính nguyên tử của quy trình đổi DN. Cần bảo vệ quyền ghi, kiểm soát đồng thời và kiểm tra lại trên LDAP server phù hợp.

### Tài liệu tham khảo

- [Spring LDAP — Object-Directory Mapping (ODM)](https://docs.spring.io/spring-ldap/reference/odm.html)
- [Spring LDAP — LdapTemplate.update(Object) API](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/LdapTemplate.html)
- [Spring LDAP — ObjectDirectoryMapper API](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/odm/core/ObjectDirectoryMapper.html)
- [Spring LDAP — DirContextAdapter và getModificationItems()](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/DirContextAdapter.html)
- [Spring LDAP — Updating data with DirContextAdapter](https://docs.spring.io/spring-ldap/reference/dirobjectfactory.html)
- [RFC 4511 — LDAP Modify Operation](https://www.rfc-editor.org/rfc/rfc4511.html#section-4.6)
- [RFC 4528 — LDAP Assertion Control](https://www.rfc-editor.org/rfc/rfc4528)
