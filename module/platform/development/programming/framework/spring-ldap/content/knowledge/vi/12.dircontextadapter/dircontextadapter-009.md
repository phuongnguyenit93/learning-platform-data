# Kiểm thử trạng thái adapter trước khi commit thay đổi

Khi một ứng dụng Spring LDAP cập nhật tên hiển thị hoặc số điện thoại của nhân viên, thao tác thường gồm: **đọc entry**, **sửa dữ liệu trên đối tượng Java**, rồi **gửi các thay đổi tới LDAP server**. Nếu không kiểm tra bước giữa, ứng dụng có thể gửi một phép sửa không cần thiết, vô tình xóa thuộc tính, hoặc cập nhật những trường mà người gọi không được phép thay.

`DirContextAdapter` hỗ trợ tình huống này bằng cơ chế ghi nhận **những thay đổi của attribute so với trạng thái đã đọc**. Qua interface `DirContextOperations`, ta có thể xem các `ModificationItem` đang chờ gửi, kiểm tra chính sách rồi mới gọi `LdapTemplate.modifyAttributes(...)`.

Đây là bài trong chương **DirContextAdapter** của SPRING_LDAP. Mục tiêu là hiểu trạng thái cục bộ của adapter, phân biệt dữ liệu gốc và dữ liệu đang chỉnh sửa, xem trước lệnh ADD/REPLACE/REMOVE, viết unit test và integration test, kiểm soát DN/schema/ACL, và tránh hiểu nhầm từ “commit”. Những nguyên tắc này hữu ích cả khi một hệ thống dùng `LdapClient`, ODM hoặc các API JNDI khác để ghi dữ liệu thư mục.

## 1. Bối cảnh: sửa entry không giống sửa Java object thuần

Giả sử LDAP server có DIT:

~~~text
dc=example,dc=org
├── ou=people
│   ├── uid=an
│   └── uid=binh
├── ou=groups
│   └── cn=developers
└── ou=services
    └── cn=app-editor
~~~

Entry An:

~~~ldif
dn: uid=an,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: an
cn: Nguyen Van An
sn: Nguyen
displayName: Nguyễn Văn An
mail: an@example.org
telephoneNumber: +84 28 1111
~~~

Ứng dụng muốn thay `displayName` thành `Nguyễn An` mà vẫn giữ nguyên các thuộc tính khác. Có ba trạng thái cần phân biệt:

| Trạng thái | Ví dụ | Nơi tồn tại |
| --- | --- | --- |
| **Trạng thái LDAP đã lưu** | `displayName: Nguyễn Văn An` | Trên LDAP server tại thời điểm đọc |
| **Trạng thái adapter đang sửa** | `displayName: Nguyễn An` | Trong bộ nhớ Java của request/service |
| **Thay đổi dự định gửi** | Replace `displayName` | Các `ModificationItem` mà adapter tính toán |

Sửa một thuộc tính trong adapter **không tự cập nhật LDAP server**. Ngược lại, gọi `LdapTemplate.modifyAttributes(...)` là yêu cầu ghi thật và cần được kiểm soát.

### Ví dụ thao tác không nên làm ngay

~~~java
DirContextOperations entry = ldapTemplate.lookupContext(personDn);
entry.setAttributeValue("displayName", request.displayName());

// Không kiểm tra gì mà gửi ngay:
ldapTemplate.modifyAttributes(entry);
~~~

Cách này có thể phù hợp với chức năng rất đơn giản và dữ liệu đã được kiểm soát đầy đủ. Nhưng trong hệ thống có nhiều trường, phân quyền và audit, ta nên biết rõ adapter **định thay đổi những gì** trước khi thực hiện lệnh LDAP.

## 2. Luồng đọc – chỉnh sửa – kiểm tra – ghi

~~~mermaid
flowchart TD
    A["LdapTemplate.lookupContext(dn)"] --> B["DirContextOperations có dữ liệu ban đầu"]
    B --> C["setAttributeValue / setAttributeValues / add / remove"]
    C --> D["getModificationItems()"]
    D --> E{"Có thay đổi hợp lệ?"}
    E -->|Không có thay đổi| F["Kết thúc: không gửi LDAP Modify"]
    E -->|Không hợp lệ| G["Từ chối và ghi audit an toàn"]
    E -->|Hợp lệ| H["LdapTemplate.modifyAttributes(entry)"]
    H --> I[("LDAP server kiểm tra schema và ACL")]
    I --> J{"Kết quả"}
    J -->|Thành công| K["Đọc lại/xác nhận khi cần"]
    J -->|Lỗi| L["Xử lý exception, không giả định đã rollback"]
~~~

Điểm quan trọng:

1. `lookupContext(dn)` lấy dữ liệu hiện có qua `ContextSource` và cung cấp một `DirContextOperations` có ngữ cảnh cập nhật.
2. Các lệnh setter thay đổi trạng thái trong bộ nhớ của adapter.
3. `getModificationItems()` cho phép **xem trước các phép sửa** mà adapter dự định gửi.
4. Ứng dụng kiểm tra whitelist thuộc tính, giá trị hợp lệ và quyền nghiệp vụ.
5. `modifyAttributes(entry)` mới là thao tác gửi yêu cầu thay đổi tới server.
6. LDAP server quyết định kết quả theo schema, ACL, ràng buộc tên và chính sách.

**Không có phương thức `commit()` kiểu JPA trên `DirContextAdapter`.** Trong bài, “commit” được dùng theo nghĩa nghiệp vụ là **gửi thay đổi tới LDAP qua `LdapTemplate.modifyAttributes(...)`**, không phải commit transaction của một ORM.

## 3. Trạng thái adapter và thay đổi đang chờ

`DirContextAdapter` triển khai `DirContextOperations`; khi được tạo từ dữ liệu đã đọc ở chế độ cập nhật, nó có thể theo dõi các thay đổi so với tập attributes ban đầu.

Các API thường dùng:

| API | Vai trò |
| --- | --- |
| `getStringAttribute("cn")` | Đọc một giá trị chuỗi hiện có trong adapter |
| `getStringAttributes("telephoneNumber")` | Đọc các giá trị chuỗi, thích hợp với thuộc tính đa trị |
| `setAttributeValue("displayName", value)` | Đặt/đổi giá trị của một thuộc tính |
| `setAttributeValues("telephoneNumber", values)` | Đặt tập các giá trị của một thuộc tính |
| `addAttributeValue("telephoneNumber", value)` | Thêm một giá trị vào thuộc tính |
| `removeAttributeValue("telephoneNumber", value)` | Bỏ một giá trị thuộc tính |
| **`getModificationItems()`** | Xem các `ModificationItem` được tính từ thay đổi đang chờ |

Việc có thay đổi trong Java object và danh sách `ModificationItem` **không phải xác nhận server đã ghi**. Nếu thao tác sửa không được gửi, LDAP server không biết nội dung chỉnh sửa cục bộ đó.

### Chú ý chế độ tạo mới và chế độ cập nhật

Hai đoạn mã sau phục vụ hai mục đích khác nhau:

~~~java
// Mục đích tạo entry mới:
DirContextAdapter fresh = new DirContextAdapter(personDn);
fresh.setAttributeValue("cn", "Nguyen Van An");
// Thường dùng với ldapTemplate.bind(fresh).

// Mục đích cập nhật entry hiện có:
DirContextOperations loaded = ldapTemplate.lookupContext(personDn);
loaded.setAttributeValue("displayName", "Nguyễn An");
// Kiểm tra loaded.getModificationItems() rồi modifyAttributes(loaded).
~~~

Với entry **mới**, adapter được dùng để xây toàn bộ tập attributes cho `bind(...)`. Với entry **đã đọc**, nó có cơ sở để tính sự khác biệt cho một phép `modifyAttributes(...)`. Không nên giả định một adapter tạo rỗng có cùng cơ chế “dirty checking” như adapter được tạo từ trạng thái gốc đã biết.

Ngoài ra, Spring LDAP có thể sử dụng các kiểu context và cơ chế mapping khác nhau theo overload. Khi viết logic xem trước thay đổi, hãy dùng đúng đường đọc trả về `DirContextOperations` có snapshot phù hợp, và kiểm thử với phiên bản Spring LDAP thực tế của dự án.

## 4. `getModificationItems()` trả về điều gì?

JNDI `javax.naming.directory.ModificationItem` biểu diễn một phép thay đổi attribute, gồm:

- **Mã thao tác** lấy từ `getModificationOp()`.
- **Đối tượng `Attribute`** lấy từ `getAttribute()`, chứa tên thuộc tính và các giá trị liên quan đến lệnh.

Ba mã sửa thuộc tính do `javax.naming.directory.DirContext` định nghĩa:

| Mã | Tên | Ý nghĩa LDAP Modify |
| --- | --- | --- |
| `DirContext.ADD_ATTRIBUTE` | Add | Thêm thuộc tính hoặc một số giá trị theo quy tắc server |
| `DirContext.REPLACE_ATTRIBUTE` | Replace | Thay tập giá trị được nêu cho thuộc tính |
| `DirContext.REMOVE_ATTRIBUTE` | Remove | Xóa thuộc tính hoặc giá trị được nêu theo lệnh |

Ví dụ hiển thị thông tin **không kèm giá trị nhạy cảm**:

~~~java
import java.util.ArrayList;
import java.util.List;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;
import org.springframework.ldap.core.DirContextOperations;

record PendingChange(String attribute, String operation) {}

public final class ChangeInspector {
    private ChangeInspector() {}

    public static List<PendingChange> summarize(DirContextOperations entry) {
        List<PendingChange> result = new ArrayList<>();

        for (ModificationItem item : entry.getModificationItems()) {
            String operation = switch (item.getModificationOp()) {
                case DirContext.ADD_ATTRIBUTE -> "ADD";
                case DirContext.REPLACE_ATTRIBUTE -> "REPLACE";
                case DirContext.REMOVE_ATTRIBUTE -> "REMOVE";
                default -> "UNKNOWN";
            };
            result.add(new PendingChange(
                    item.getAttribute().getID(),
                    operation));
        }
        return List.copyOf(result);
    }
}
~~~

Đoạn code dùng Java 17 để hỗ trợ switch expression và record. Trong ứng dụng có phiên bản Java thấp hơn, chuyển về cú pháp tương ứng.

**Không log toàn bộ `ModificationItem.toString()` hoặc `Attribute.toString()` một cách vô điều kiện**: các đối tượng này có thể chứa giá trị thư mục nhạy cảm, chẳng hạn thông tin cá nhân hoặc thuộc tính mật khẩu. Một màn hình “preview” công khai cũng cần bảo đảm người gọi chỉ xem được những trường mà họ được phép.

### Không nên giả định số lượng hoặc thứ tự lệnh

Một lời gọi setter không nhất thiết luôn tương ứng chính xác với một `ModificationItem`. Adapter có thể chuẩn hóa thay đổi, phát hiện thao tác no-op hoặc tính lệnh khác nhau tùy trạng thái ban đầu, thứ tự thao tác và đặc tính thuộc tính.

Ví dụ, đổi giá trị rồi đổi về giá trị ban đầu có thể khiến trạng thái cuối không còn khác biệt; nhưng hãy **kiểm tra `getModificationItems()` thực tế** thay vì dự đoán dựa trên số lần gọi setter. Những phép sửa một thuộc tính đa trị cũng cần đặc biệt thận trọng vì thứ tự các giá trị LDAP thường không mang ý nghĩa.

## 5. Ví dụ: preview trước khi cập nhật tên hiển thị

Giả sử `ContextSource.base=dc=example,dc=org` và service chỉ được phép sửa thuộc tính `displayName`. Một phương thức service nhận UID và tên mới:

~~~java
import java.util.List;
import java.util.Objects;
import javax.naming.Name;
import javax.naming.directory.ModificationItem;
import org.springframework.ldap.core.DirContextOperations;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

record UpdateResult(boolean changed, List<PendingChange> planned) {}

public class EmployeeProfileService {
    private final LdapTemplate ldapTemplate;

    public EmployeeProfileService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public UpdateResult changeDisplayName(String uid, String requestedName) {
        if (uid == null || uid.isBlank() || uid.length() > 64) {
            throw new IllegalArgumentException("Invalid uid");
        }
        if (requestedName == null || requestedName.isBlank()
                || requestedName.length() > 200) {
            throw new IllegalArgumentException("Invalid display name");
        }

        Name dn = LdapNameBuilder.newInstance("ou=people")
                .add("uid", uid)
                .build();
        DirContextOperations entry = ldapTemplate.lookupContext(dn);

        String oldName = entry.getStringAttribute("displayName");
        if (Objects.equals(oldName, requestedName)) {
            return new UpdateResult(false, List.of());
        }

        entry.setAttributeValue("displayName", requestedName);

        ModificationItem[] pending = entry.getModificationItems();
        List<PendingChange> preview = ChangeInspector.summarize(entry);

        if (pending.length == 0) {
            return new UpdateResult(false, List.of());
        }

        for (ModificationItem change : pending) {
            if (!"displayName".equalsIgnoreCase(
                    change.getAttribute().getID())) {
                throw new IllegalStateException(
                        "Unexpected LDAP attribute change");
            }
        }

        ldapTemplate.modifyAttributes(entry);
        return new UpdateResult(true, preview);
    }
}
~~~

Ý nghĩa từng bước:

1. Xây DN từ UID bằng `LdapNameBuilder` để giá trị RDN không bị hiểu thành cú pháp DN.
2. Đọc entry bằng `lookupContext(...)`, lấy một giá trị `displayName` hiện có.
3. Kiểm tra input mới và bỏ qua nếu giống giá trị cũ theo **chính sách Java** của ví dụ.
4. Gọi `setAttributeValue(...)` để thay đổi bản sao trong adapter.
5. Kiểm tra `getModificationItems()` trước khi ghi, chỉ cho phép tác động lên `displayName`.
6. Gọi `modifyAttributes(entry)` khi có lệnh hợp lệ; nếu lệnh LDAP thất bại, phương thức không trả kết quả thành công.

Trong hệ thống thật, **không được coi đoạn `Objects.equals` là mô phỏng matching rule LDAP**: server có thể sử dụng quy tắc chuẩn hóa khác. So sánh Java ở đây chỉ nhằm tránh gửi lệnh khi input giống hệt chuỗi được đọc.

Vì `getModificationItems()` phản ánh **những thay đổi hiện tại**, đối tượng `preview` có thể sử dụng cho audit ít thông tin, nhưng không phải bản ghi đã lưu trên server. Với nghiệp vụ đòi hỏi xác nhận chính xác trạng thái sau khi ghi, đọc lại entry khi phù hợp.

## 6. Chính sách allowlist trên các thay đổi dự định

Một màn hình quản trị có thể nhận nhiều trường từ client, nhưng không phải trường nào cũng được phép sửa. Ví dụ `displayName` và `telephoneNumber` được phép, còn `uid`, `objectClass` và `userPassword` không được sửa qua endpoint hồ sơ.

Một cách kiểm soát là xem **danh sách thao tác của adapter**, không chỉ xem danh sách field do HTTP request gửi:

~~~java
import java.util.Locale;
import java.util.Set;
import javax.naming.directory.ModificationItem;
import org.springframework.ldap.core.DirContextOperations;

public final class ProfileChangePolicy {
    private static final Set<String> ALLOWED = Set.of(
            "displayname", "telephonenumber");

    private ProfileChangePolicy() {}

    public static void verify(DirContextOperations entry) {
        ModificationItem[] changes = entry.getModificationItems();

        if (changes.length > 8) {
            throw new IllegalArgumentException("Too many changes");
        }

        for (ModificationItem item : changes) {
            String attribute = item.getAttribute()
                    .getID()
                    .toLowerCase(Locale.ROOT);

            if (!ALLOWED.contains(attribute)) {
                throw new IllegalArgumentException(
                        "Changing this attribute is not allowed");
            }
        }
    }
}
~~~

Sau khi service gọi các setter, chạy `ProfileChangePolicy.verify(entry)` **trước** `ldapTemplate.modifyAttributes(entry)`.

### Chỉ kiểm tra tên thuộc tính chưa đủ

Allowlist là một lớp bảo vệ, nhưng nghiệp vụ còn có thể yêu cầu:

- Kiểm tra **loại thao tác**: cho phép replace `displayName` nhưng không cho remove thuộc tính bắt buộc.
- Kiểm tra **độ dài/định dạng giá trị** theo chính sách ứng dụng và schema.
- Kiểm tra **danh tính người gọi** có quyền sửa entry đó, không chỉ cho phép sửa bất kỳ DN nào dưới OU.
- Kiểm tra **thay đổi trên thuộc tính đa trị** không làm mất các giá trị ngoài phạm vi quản lý.
- Giới hạn số phép sửa và kích thước request.
- Có **audit** loại thao tác mà không ghi nguyên dữ liệu bí mật.

**ACL của LDAP server vẫn là lớp phân quyền cuối cùng.** Policy trong Java giúp tránh gửi lệnh trái ý định nghiệp vụ, nhưng không thay thế quyền trên server.

## 7. Không có lệnh ghi khi adapter không thay đổi

Một use case rất thường gặp: người dùng bấm “Lưu” nhưng thực tế không sửa gì. Gửi yêu cầu LDAP Modify lúc này có thể tạo tải, ảnh hưởng audit của server hoặc làm chạm các tác vụ đồng bộ.

Có thể bỏ qua thao tác ghi:

~~~java
DirContextOperations entry = ldapTemplate.lookupContext(dn);

entry.setAttributeValue("displayName", requestedName);

ModificationItem[] changes = entry.getModificationItems();

if (changes.length == 0) {
    // Không gửi ModifyRequest lên LDAP server.
    return;
}

ProfileChangePolicy.verify(entry);
ldapTemplate.modifyAttributes(entry);
~~~

**Không nên tự suy luận một setter chắc chắn tạo thay đổi.** Kết quả phụ thuộc trạng thái dữ liệu ban đầu và cách adapter tính khác biệt; quyết định no-op nên căn cứ vào trạng thái đang chờ, kết hợp validation và chính sách nghiệp vụ.

### Trường hợp đổi rồi đổi lại

~~~java
// Ví dụ giả định entry đọc từ LDAP có displayName = "Nguyễn Văn An".
entry.setAttributeValue("displayName", "Nguyễn An");
entry.setAttributeValue("displayName", "Nguyễn Văn An");

// Kiểm tra tại đây thay vì đếm hai lần gọi setter:
ModificationItem[] finalChanges = entry.getModificationItems();
~~~

Trong trường hợp đơn giản, trạng thái cuối có thể bằng trạng thái ban đầu và không cần sửa. Nhưng với kiểu dữ liệu khác, tập đa trị hoặc trạng thái adapter không được khởi tạo theo đường update, kết quả cần được xác nhận bằng unit/integration test.

## 8. Thuộc tính đa trị: thêm/bớt giá trị và nguy cơ mất dữ liệu

LDAP cho phép nhiều giá trị trên một thuộc tính, ví dụ:

~~~ldif
dn: uid=an,ou=people,dc=example,dc=org
telephoneNumber: +84 28 1111
telephoneNumber: +84 28 2222
~~~

Có hai ý định khác nhau:

- **Thêm một số điện thoại mới**, giữ nguyên các số khác.
- **Thay toàn bộ tập số điện thoại** bằng danh sách do người dùng gửi.

Các lệnh adapter tương ứng có thể sử dụng:

~~~java
// Đã đọc entry bằng ldapTemplate.lookupContext(dn).

entry.addAttributeValue("telephoneNumber", "+84 28 3333");

// Hoặc khi muốn loại một giá trị cụ thể:
entry.removeAttributeValue("telephoneNumber", "+84 28 1111");

// Nếu thật sự quản lý toàn bộ tập giá trị:
entry.setAttributeValues("telephoneNumber", new String[] {
        "+84 28 1111", "+84 28 3333"
});

ModificationItem[] planned = entry.getModificationItems();
~~~

**Đừng kết hợp ba cách trên trong cùng một nghiệp vụ mà không xác định trạng thái cuối mong muốn.** Dùng `setAttributeValues(...)` có nghĩa ứng dụng chủ động quyết định cả tập giá trị, có thể làm mất những giá trị mà hệ thống khác vừa thêm.

Với thuộc tính đa trị, **thứ tự các giá trị thường không mang ý nghĩa**. Không so sánh hai mảng như một chuỗi hoặc giả định phần tử đầu tiên luôn là giá trị chính. Nếu cần quyết định liệu tập giá trị có thực sự đổi, có thể so sánh theo tập hợp phù hợp với matching rule và chính sách nghiệp vụ.

Mỗi lần cập nhật còn cần xét schema: không phải attribute nào cũng đa trị; server có thể từ chối một giá trị trùng, sai syntax hoặc không được phép. Adapter tính lệnh cục bộ, **LDAP server** mới xác nhận thao tác hợp lệ.
## 9. Unit test: trạng thái ban đầu và lệnh đang chờ

Kiểm thử trạng thái adapter không nhất thiết cần kết nối LDAP server. Có thể tạo một `DirContextAdapter` từ tập thuộc tính đã biết, mô phỏng entry vừa được đọc ở chế độ cập nhật, rồi xem các lệnh mà nó tạo ra sau khi setter chạy.

### Tạo adapter từ dữ liệu hiện có

Ví dụ với JUnit 5:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import javax.naming.ldap.LdapName;
import javax.naming.directory.BasicAttributes;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;
import org.junit.jupiter.api.Test;
import org.springframework.ldap.core.DirContextAdapter;

class AdapterPendingChangesTest {

    private DirContextAdapter loadedEntry() throws Exception {
        BasicAttributes attributes = new BasicAttributes(true);
        attributes.put("uid", "an");
        attributes.put("cn", "Nguyen Van An");
        attributes.put("sn", "Nguyen");
        attributes.put("displayName", "Nguyễn Văn An");

        return new DirContextAdapter(
                attributes,
                new LdapName("uid=an,ou=people"));
    }

    @Test
    void loadedEntryHasNoPendingModifications() throws Exception {
        DirContextAdapter entry = loadedEntry();

        assertEquals("Nguyễn Văn An",
                entry.getStringAttribute("displayName"));
        assertEquals(0, entry.getModificationItems().length);
    }

    @Test
    void changingDisplayNameCreatesReplacement() throws Exception {
        DirContextAdapter entry = loadedEntry();

        entry.setAttributeValue("displayName", "Nguyễn An");
        ModificationItem[] pending = entry.getModificationItems();

        assertEquals(1, pending.length);
        assertEquals(DirContext.REPLACE_ATTRIBUTE,
                pending[0].getModificationOp());
        assertEquals("displayName",
                pending[0].getAttribute().getID());
        assertEquals("Nguyễn An",
                pending[0].getAttribute().get());
    }

    @Test
    void settingUnchangedValueIsNoOp() throws Exception {
        DirContextAdapter entry = loadedEntry();

        entry.setAttributeValue("displayName", "Nguyễn Văn An");

        assertEquals(0, entry.getModificationItems().length);
    }
}
~~~

Bài test sử dụng constructor nhận `Attributes` và DN để mô phỏng adapter có dữ liệu gốc. Không dùng `new DirContextAdapter()` rỗng để khẳng định mọi trường hợp đều có cơ chế diff giống entry đã đọc.

Ở phiên bản Spring LDAP được sử dụng trong dự án, cần xác minh chữ ký constructor và hành vi tracking của adapter; các assertion trên thể hiện kỳ vọng cho **một thuộc tính chuỗi đơn giản**. Chúng không chứng minh mọi phép thay đổi thuộc tính đa trị hoặc giá trị nhị phân luôn tạo đúng một item theo cùng thứ tự.

**Điểm cần học:** unit test không chỉ kiểm tra `getStringAttribute(...)` sau setter mà còn phải kiểm tra `getModificationItems()`. Một thuộc tính có giá trị mới trong bộ nhớ chưa đủ để biết câu lệnh gửi tới LDAP sẽ có dạng nào.

## 10. Kiểm thử không gửi lệnh LDAP khi không có thay đổi

Chỉ xem `getModificationItems()` chưa kiểm tra được service có **thực sự bỏ qua ghi** khi không có gì đổi hay không. Có thể kiểm thử sự phối hợp của service và `LdapTemplate` bằng Mockito.

Giả sử `EmployeeProfileService` ở mục 5 và `ChangeInspector` đều nằm trong dự án:

~~~java
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.mockito.Mockito.*;

import javax.naming.Name;
import javax.naming.directory.BasicAttributes;
import org.junit.jupiter.api.Test;
import org.springframework.ldap.core.DirContextAdapter;
import org.springframework.ldap.core.DirContextOperations;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

class EmployeeProfileServiceTest {

    @Test
    void unchangedNameDoesNotWriteToLdap() throws Exception {
        LdapTemplate template = mock(LdapTemplate.class);

        Name dn = LdapNameBuilder.newInstance("ou=people")
                .add("uid", "an")
                .build();

        BasicAttributes original = new BasicAttributes(true);
        original.put("displayName", "Nguyễn Văn An");
        DirContextAdapter loaded = new DirContextAdapter(original, dn);

        when(template.lookupContext(dn)).thenReturn(loaded);

        EmployeeProfileService service =
                new EmployeeProfileService(template);

        UpdateResult result =
                service.changeDisplayName("an", "Nguyễn Văn An");

        assertFalse(result.changed());
        verify(template, never())
                .modifyAttributes(any(DirContextOperations.class));
    }
}
~~~

Test này kiểm tra **không gọi LDAP Modify từ service** trong trường hợp input giống dữ liệu cũ. Nó không khởi chạy LDAP server và không thử quyền, schema hoặc hiệu ứng của thao tác ghi.

Một test thứ hai nên đưa vào dữ liệu khác giá trị gốc, rồi dùng `verify(template).modifyAttributes(loaded)` để kiểm tra lệnh ghi chỉ được gọi **sau khi** đã áp dụng policy. Nếu policy phát hiện `uid` hoặc `objectClass` bị thay trái phép, kiểm tra service trả lỗi và **không gọi** `modifyAttributes(...)`.

### Kiểm thử một policy từ chối thay đổi không được phép

~~~java
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertEquals;

import javax.naming.ldap.LdapName;
import javax.naming.directory.BasicAttributes;
import org.junit.jupiter.api.Test;
import org.springframework.ldap.core.DirContextAdapter;

class ProfileChangePolicyTest {

    @Test
    void rejectsUnapprovedAttribute() throws Exception {
        BasicAttributes original = new BasicAttributes(true);
        original.put("uid", "an");
        original.put("displayName", "Nguyễn Văn An");

        DirContextAdapter entry = new DirContextAdapter(
                original, new LdapName("uid=an,ou=people"));

        entry.setAttributeValue("uid", "another-user");

        assertEquals(1, entry.getModificationItems().length);
        assertThrows(IllegalArgumentException.class,
                () -> ProfileChangePolicy.verify(entry));
    }
}
~~~

Việc từ chối ở đây là **kiểm tra chính sách ứng dụng**, không phải thay thế quyền trên LDAP server. Nếu một service tự ghi mà bỏ qua policy, server ACL mới là ranh giới bảo mật tiếp theo.

## 11. “Commit” không phải giao dịch ORM: atomicity và khả năng rollback

Một số lập trình viên quen Hibernate/JPA có thể hình dung:

~~~text
load entity → mutate object → transaction.commit()
~~~

Nhưng với Spring LDAP qua `DirContextAdapter`, ta thường có:

~~~text
lookupContext(dn)
    ↓
setAttributeValue(...)
    ↓
getModificationItems() và kiểm tra
    ↓
ldapTemplate.modifyAttributes(entry)
    ↓
LDAP Modify operation tới server
~~~

**Không có cơ chế `commit()` hoặc `rollback()` của adapter** tương tự persistence context của JPA. Việc chưa gọi `modifyAttributes(...)` nghĩa là thay đổi vẫn còn cục bộ; chỉ bỏ đối tượng đang sửa không phải một thao tác rollback phía LDAP, vì server chưa ghi gì.

Khi `modifyAttributes(...)` đã được gửi:

- LDAP server kiểm tra quyền, schema và các ràng buộc trước khi chấp nhận yêu cầu.
- Một LDAP Modify request thông thường có tính **nguyên tử trên một entry đối với các sửa đổi trong yêu cầu đó** theo semantics của giao thức, nhưng không có nghĩa mọi chuỗi gồm nhiều request hoặc nhiều entry đều nằm trong một transaction chung.
- Nếu LDAP trả kết quả thành công, thay đổi đã được server chấp nhận theo cơ chế của server đó.
- Nếu mạng đứt giữa lúc gửi và nhận phản hồi, ứng dụng có thể không biết chắc server đã thực hiện hay chưa; không tự động retry mù.
- Nếu cần khôi phục sau một thay đổi đã lưu, phải có nghiệp vụ sửa ngược có kiểm soát, hoặc cơ chế transaction/server extension thực sự được hỗ trợ; không giả định adapter tự rollback.

### Đừng tái sử dụng adapter đã ghi như snapshot mới

Sau khi gọi `ldapTemplate.modifyAttributes(entry)`, không nên mặc nhiên coi `entry.getModificationItems()` đã được reset về một “trạng thái sạch” phản ánh server. Muốn có snapshot đúng cho vòng sửa tiếp theo, **lookup lại entry** hoặc dùng cơ chế đồng bộ trạng thái được thư viện cung cấp và đã kiểm chứng.

Điều này cũng giúp tránh lỗi dùng cùng một `DirContextOperations` qua nhiều HTTP request. Adapter chứa dữ liệu có thể cũ và các thay đổi cục bộ; nó nên sống trong phạm vi một thao tác nghiệp vụ, không làm singleton dùng chung giữa nhiều người dùng.

## 12. Cạnh tranh đồng thời: preview đúng nhưng vẫn có thể ghi đè

Giả sử hai quản trị viên cùng sửa entry:

~~~text
10:00:00  A đọc displayName = "Nguyễn Văn An"
10:00:01  B đọc displayName = "Nguyễn Văn An"
10:00:02  A chuẩn bị displayName = "Nguyễn An"
10:00:03  B chuẩn bị displayName = "An Nguyễn"
10:00:04  A preview: REPLACE displayName, hợp lệ
10:00:05  B preview: REPLACE displayName, hợp lệ
10:00:06  A gửi LDAP Modify và thành công
10:00:07  B gửi LDAP Modify, có thể ghi đè kết quả của A
~~~

**`getModificationItems()` chỉ kiểm tra sự khác biệt với snapshot đã đọc của chính adapter**, không tự kiểm tra LDAP server có thay đổi từ lúc đó hay chưa. Đây là vấn đề *time-of-check to time-of-use* (TOCTOU).

Nếu nghiệp vụ cần chống mất cập nhật:

1. Xác định trường hợp nào cần phát hiện xung đột, ví dụ số điện thoại cá nhân ít nghiêm trọng hơn quyền truy cập nhóm.
2. Cân nhắc sử dụng một version/ETag của ứng dụng hoặc thuộc tính thay đổi phù hợp (ví dụ metadata được server cung cấp) để phát hiện thay đổi ngoài dự kiến.
3. Với server hỗ trợ LDAP Assertion Control hoặc cơ chế kiểm soát đồng thời thích hợp, có thể dùng điều kiện trên server trước khi ghi; cần xác minh hỗ trợ và cách tích hợp của client.
4. Nếu chỉ kiểm tra lại bằng một search trước khi ghi, hiểu rằng vẫn có cửa sổ race nếu kiểm tra và ghi không có bảo đảm nguyên tử chung.
5. Thiết kế phản hồi conflict rõ ràng; không tự động gửi lại dữ liệu cũ để ghi đè người khác.

Không tự viết logic “chắc chắn không trùng” chỉ bằng cách so sánh hai String trong Java rồi gọi `modifyAttributes(...)`.

## 13. Tương tác với schema, projection và ACL

Cơ chế tracking của adapter chỉ phản ánh **những thuộc tính có trong snapshot và những setter được gọi**, không phản ánh toàn bộ sự thật trên LDAP server.

| Tình huống | Tác động tới preview/ghi |
| --- | --- |
| Entry thiếu `mail` thật sự | Adapter có thể tạo lệnh thêm hoặc thay tùy cách cập nhật |
| Query không yêu cầu `telephoneNumber` | Snapshot không có thuộc tính đó, dù server có thể có |
| Bind account không được đọc một thuộc tính | Preview có thể không biết giá trị hiện tại của thuộc tính |
| Thuộc tính `SINGLE-VALUE` được thêm nhiều giá trị | LDAP server có thể từ chối theo schema |
| Entry thuộc `inetOrgPerson` thiếu MUST `cn`, `sn` trong thao tác không hợp lệ | Server có thể trả lỗi object class violation |
| Endpoint chỉ được sửa `displayName` | Policy phải giới hạn thuộc tính; ACL server vẫn phải thực thi |
| Entry đã bị xóa giữa lúc đọc và ghi | `modifyAttributes` có thể thất bại vì DN không còn tồn tại |

### Không đọc thiếu rồi tự xóa nhầm

Nếu phép tìm kiếm chỉ yêu cầu `uid` và `cn`, mapper có thể thấy `telephoneNumber` vắng trong dữ liệu trả về, dù server thật có giá trị. Nếu sau đó gọi `setAttributeValues("telephoneNumber", new String[]{})` như thể dữ liệu vắng nghĩa là “cần xóa”, ứng dụng có thể mất dữ liệu. Khi sửa một attribute, hãy thiết kế đường đọc và dựa trên dữ liệu/quyền phù hợp, hoặc dùng một phép Modify có chủ đích không phụ thuộc snapshot thiếu.

**Không sử dụng adapter để bỏ qua schema.** Đọc được một thuộc tính và tính được `ModificationItem` chỉ chứng minh dữ liệu cục bộ có thể được biểu diễn; LDAP server còn có thể trả lỗi `constraintViolation (19)`, `invalidAttributeSyntax (21)`, `objectClassViolation (65)` hoặc `insufficientAccessRights (50)`.

## 14. Kiểm thử tích hợp trên LDAP server lab

Unit test xác minh tracking và policy trong Java. Nhưng nó không xác minh đường kết nối, DN tương đối, ACL, schema, matching rule hoặc kết quả LDAP Modify thực tế. Cần thêm integration test trên thư mục kiểm thử **được phép thao tác**.

Giả sử:

~~~text
ContextSource.base: dc=lab,dc=example,dc=org
OU:                 ou=people
Entry:              uid=an,ou=people,dc=lab,dc=example,dc=org
Bind account:       cn=editor,ou=services,dc=lab,dc=example,dc=org
TLS:                LDAPS với chứng chỉ được xác minh
~~~

### Bộ kịch bản cần có

| Kịch bản | Bước kiểm tra | Kết quả dự kiến |
| --- | --- | --- |
| A. Không có thay đổi | Lookup, đặt lại đúng tên cũ | Không gửi LDAP Modify nếu service bỏ qua no-op |
| B. Đổi một trường | Đổi `displayName` và preview | Chỉ thuộc tính được phép nằm trong pending changes |
| C. Thay đổi trái phép | Thử đặt `uid` qua endpoint hồ sơ | Bị policy từ chối trước khi gửi |
| D. Thuộc tính đa trị | Thêm/bỏ một số điện thoại | Đọc lại và xác nhận không mất số còn lại |
| E. Schema | Gửi dữ liệu sai định dạng trong môi trường lab | Server từ chối; service phân loại đúng lỗi |
| F. ACL | Dùng tài khoản không có quyền ghi | Server từ chối, dù preview hợp lệ |
| G. DN sai | Truy vấn từ base không tồn tại | Nhận lỗi tương ứng, không tự mở rộng phạm vi |
| H. Hai tác vụ đồng thời | Cùng sửa một thuộc tính từ snapshot cũ | Quan sát nguy cơ mất cập nhật, thử cơ chế kiểm soát xung đột nếu có |
| I. Kết nối gián đoạn | Mô phỏng timeout sau khi gửi yêu cầu | Không retry mù; xác minh trạng thái an toàn |

Sau bước ghi thành công, **lookup lại** entry và so sánh với kỳ vọng, ví dụ `displayName` mới được lưu còn `sn` và `mail` không đổi. Với thuộc tính đa trị, so sánh **tập giá trị** thay vì thứ tự mảng nếu thuộc tính không có nghĩa thứ tự.

### Vì sao không nên test trên production?

Một LDAP Modify request có thể tác động vào quá trình đăng nhập, đồng bộ danh bạ, phân quyền nhóm hoặc các hệ thống khác. Ngay cả khi sửa trường tưởng như vô hại, thư mục sản xuất có thể kích hoạt audit và đồng bộ dữ liệu. Hãy dùng server/OU lab, tài khoản có quyền tối thiểu và quy trình dọn dữ liệu đã tạo.

## 15. Xử lý lỗi khi gọi `modifyAttributes(...)`

| Nhóm lỗi | Ví dụ mã LDAP hoặc dấu hiệu | Hướng xử lý |
| --- | --- | --- |
| DN hoặc entry không tồn tại | `noSuchObject (32)` | Kiểm tra ContextSource base, DN và trạng thái bị xóa đồng thời |
| Không đủ quyền | `insufficientAccessRights (50)` | Kiểm tra ACL và danh tính bind |
| Dữ liệu vi phạm schema | `objectClassViolation (65)`, `invalidAttributeSyntax (21)` | Xem attribute type/MUST/MAY và giá trị gửi |
| Vi phạm ràng buộc | `constraintViolation (19)` | Kiểm tra SINGLE-VALUE, policy server |
| Thuộc tính hoặc giá trị không tồn tại theo thao tác | `noSuchAttribute (16)` | Kiểm tra REMOVE và snapshot cũ |
| Giá trị trùng trong phép ADD | `attributeOrValueExists (20)` | Kiểm tra trạng thái server mới nhất |
| Kết nối, TLS, timeout | Connection exception, handshake error | Kiểm tra endpoint/chứng chỉ và trạng thái ghi chưa chắc chắn |
| Bind account lỗi | `invalidCredentials (49)` | Kiểm tra secret và quá trình xác thực, không nhầm với lỗi mapping |

Spring LDAP chuyển đổi nhiều exception JNDI thành exception của framework. Không dựa vào một chuỗi error message cụ thể của nhà cung cấp để xác định chính sách retry; cần phân loại lỗi và xử lý riêng trường hợp **kết quả ghi không chắc chắn**.

Không ghi toàn bộ `ModificationItem` vào log lỗi, vì có thể chứa dữ liệu nhân viên hoặc bí mật. Nên log loại operation, một mã định danh request, loại lỗi đã phân loại và tên thuộc tính không nhạy cảm.

## 16. Bài thực hành: dự đoán và kiểm thử trạng thái trước ghi

Giả sử entry thử nghiệm được đọc với các thuộc tính:

~~~ldif
dn: uid=an,ou=people,dc=lab,dc=example,dc=org
objectClass: inetOrgPerson
uid: an
cn: Nguyen Van An
sn: Nguyen
displayName: Nguyễn Văn An
mail: an@example.org
telephoneNumber: +84 28 1111
telephoneNumber: +84 28 2222
~~~

### Yêu cầu

1. Tạo một adapter từ dữ liệu đã có để mô phỏng kết quả `lookupContext(...)`. Kiểm tra `getModificationItems()` trước khi sửa.
2. Đổi `displayName` thành `Nguyễn An`. Dự đoán loại lệnh và kiểm tra bằng unit test.
3. Đặt lại `displayName` bằng chính giá trị ban đầu. Kiểm tra adapter còn lệnh đang chờ hay không.
4. Thêm `+84 28 3333` vào `telephoneNumber`, không xóa hai số cũ. Giải thích vì sao không nên phụ thuộc thứ tự trả về.
5. Thử sửa `uid` qua endpoint chỉ cho phép `displayName` và `telephoneNumber`. Đề xuất một test kiểm tra không có lệnh ghi.
6. Sau khi `modifyAttributes(...)` thành công, cách nào xác minh entry thực tế đã thay đổi?
7. Nếu người khác thay `displayName` giữa lúc service lookup và gửi Modify, `getModificationItems()` có tự phát hiện xung đột không?
8. Nếu adapter không có `mail` vì projection hạn chế, có nên tự động gửi REMOVE đối với `mail` không?

### Đáp án có giải thích

| Câu | Đáp án |
| --- | --- |
| 1 | Adapter khởi tạo từ snapshot dữ liệu cũ ở đường cập nhật thường không có modification trước khi sửa |
| 2 | Dự kiến `REPLACE_ATTRIBUTE` cho `displayName`; xác nhận `ModificationItem.getModificationOp()` và `getAttribute().getID()` |
| 3 | Khi trạng thái cuối giống snapshot, kỳ vọng không có thay đổi; test với phiên bản adapter thực tế |
| 4 | Dùng `addAttributeValue(...)` và xác minh đủ ba giá trị; thuộc tính đa trị thường không có thứ tự có nghĩa |
| 5 | Kiểm tra `ProfileChangePolicy.verify(...)` ném lỗi; Mockito xác nhận không gọi `modifyAttributes(...)` |
| 6 | Gọi `lookupContext(...)` lần mới và đối chiếu dữ liệu đã lưu, schema/ACL và các thuộc tính không định sửa |
| 7 | Không. Preview chỉ so với snapshot cũ của adapter; cần cơ chế kiểm soát đồng thời nếu nghiệp vụ yêu cầu |
| 8 | Không. Dữ liệu thiếu trong response không khẳng định thuộc tính không tồn tại trên server |

### Bài tập nhỏ: viết hàm kiểm tra trước ghi

Hoàn thiện logic từ khung sau:

~~~java
DirContextOperations entry = ldapTemplate.lookupContext(dn);

// Các setter được áp dụng ở đây, chỉ trên các thuộc tính được phép.

// TODO: kiểm tra ModificationItem[].
// TODO: từ chối thay đổi ngoài allowlist.
// TODO: không gửi lệnh nếu mảng rỗng.
// TODO: nếu hợp lệ mới gọi modifyAttributes(entry).
~~~

Đáp án tham khảo:

~~~java
ModificationItem[] changes = entry.getModificationItems();

if (changes.length > 0) {
    ProfileChangePolicy.verify(entry);
    ldapTemplate.modifyAttributes(entry);
}
~~~

Hàm chính sách cần được triển khai với kiểm tra tên thuộc tính, mã thao tác và giá trị theo hợp đồng nghiệp vụ. Đoạn mã trên thể hiện **thứ tự xử lý**, chưa bao gồm xác thực người gọi, audit và cơ chế phát hiện xung đột.

## 17. Checklist áp dụng trong ứng dụng thật

- [ ] `ContextSource` dùng URL/base hợp lệ, LDAPS/StartTLS kiểm tra chứng chỉ và bind account quyền tối thiểu.
- [ ] Service chỉ nhận UID/khóa nghiệp vụ, không tự ý nhận DN tùy ý từ client.
- [ ] `lookupContext(...)` trả dữ liệu thích hợp để cập nhật, không dùng snapshot thiếu thuộc tính quan trọng do projection/ACL.
- [ ] Setter chỉ được gọi trên các thuộc tính được nghiệp vụ cho phép.
- [ ] Kiểm tra `getModificationItems()` để xử lý no-op và phát hiện thay đổi ngoài dự kiến trước khi ghi.
- [ ] Xác minh tên attribute, operation, kích thước và schema; không log giá trị nhạy cảm.
- [ ] Chỉ gọi `LdapTemplate.modifyAttributes(...)` sau validation.
- [ ] Không coi preview là commit/transaction/rollback và không tái sử dụng adapter cũ qua nhiều request.
- [ ] Với dữ liệu quan trọng, có chiến lược phát hiện xung đột và kiểm tra trạng thái sau ghi.
- [ ] Unit test trạng thái adapter; integration test trên directory lab có schema/ACL thực, không ghi vào production.

## 18. Ghi nhớ

- **`DirContextAdapter` lưu trạng thái đang sửa trong Java và có thể tính các thay đổi đang chờ khi sử dụng đúng ngữ cảnh cập nhật.**
- **`getModificationItems()`** là điểm kiểm tra các lệnh ADD/REPLACE/REMOVE dự định gửi; nên dùng nó để xử lý no-op và bảo vệ thuộc tính ngoài allowlist.
- **`LdapTemplate.modifyAttributes(entry)`** mới thực hiện thao tác LDAP Modify. Không có “tự động commit” chỉ vì đã gọi setter.
- **Snapshot khác trạng thái server mới nhất.** Preview không chống cập nhật đồng thời và không bảo đảm server chấp nhận lệnh; cần ACL, schema và kiểm thử.
- **Thuộc tính đa trị cần được xử lý theo tập giá trị**, tránh ghi đè toàn bộ khi chỉ muốn thêm/bớt một phần.
- **Không log dữ liệu thay đổi nhạy cảm**; bảo vệ đường truyền, credential và quyền sửa đúng nhánh LDAP.
- **Kiểm thử hai tầng**: unit test tracking/policy, integration test hành vi ghi thật; nếu cần xác nhận kết quả, đọc lại entry sau khi gửi thao tác.

### Tài liệu tham khảo

- [Spring LDAP Reference Documentation](https://docs.spring.io/spring-ldap/reference/)
- [Java SE 17 — JNDI ModificationItem](https://docs.oracle.com/en/java/javase/17/docs/api/java.naming/javax/naming/directory/ModificationItem.html)
- [Java SE 17 — JNDI DirContext](https://docs.oracle.com/en/java/javase/17/docs/api/java.naming/javax/naming/directory/DirContext.html)
- [RFC 4511 — LDAP protocol: Modify operation](https://www.rfc-editor.org/rfc/rfc4511)
- [RFC 4512 — LDAP directory information models](https://www.rfc-editor.org/rfc/rfc4512)
