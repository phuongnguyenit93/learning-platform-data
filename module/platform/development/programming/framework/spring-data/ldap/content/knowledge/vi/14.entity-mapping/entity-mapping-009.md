# Bỏ qua trường không lưu trữ bằng @Transient

Trong **Spring Data LDAP**, một entity ODM thường đại diện cho một LDAP entry. Theo mặc định, các field của entity được ánh xạ thành LDAP attribute theo tên field; các annotation như `@Id`, `@Attribute` và `@DnAttribute` điều chỉnh cách ánh xạ đó. Nhưng không phải dữ liệu nào trong object Java cũng thuộc về directory.

Một entity có thể cần thêm các field phục vụ giao diện hoặc xử lý trong ứng dụng, chẳng hạn:

- `displayLabel` được ghép từ họ tên và mã nhân viên.
- `selected` cho biết dòng dữ liệu đang được chọn trên màn hình.
- `searchScore` lưu điểm xếp hạng của một lần tìm kiếm.
- `localNote` là ghi chú chỉ dùng trong một quy trình nội bộ.
- `department` lấy từ thành phần OU của DN nhưng không cần lưu thêm thành LDAP attribute.

Nếu để các field này tham gia mapping mặc định, ODM có thể tìm cách đọc hoặc ghi chúng như attribute của LDAP entry. Điều đó có thể gây lỗi schema, làm dữ liệu directory phình to hoặc lưu nhầm trạng thái giao diện vào nguồn dữ liệu dùng chung.

Spring LDAP ODM cung cấp annotation **`org.springframework.ldap.odm.annotations.Transient`** để đánh dấu field không thuộc mapping LDAP. Field vẫn là một phần của object Java, nhưng Object Directory Mapper bỏ qua field đó khi ánh xạ entry.

Sau bài học, bạn có thể:

- Giải thích vì sao ODM mặc định ánh xạ field theo tên.
- Dùng đúng annotation `org.springframework.ldap.odm.annotations.Transient`.
- Phân biệt Spring LDAP `@Transient` với Java `transient`, JPA `@Transient` và Jackson `@JsonIgnore`.
- Dùng `@Transient` cho field dẫn xuất, trạng thái tạm thời và field chỉ phục vụ ứng dụng.
- Kết hợp `@DnAttribute` với `@Transient` khi chỉ muốn lấy giá trị từ DN.
- Hiểu ảnh hưởng tới create, find và update trong `LdapTemplate`/repository.
- Kiểm thử để bảo đảm field không xuất hiện trong LDAP entry.

## 1. ODM ánh xạ field như thế nào?

Spring LDAP Object-Directory Mapping (ODM) ánh xạ object Java sang LDAP entry. Entity được quản lý cần có `@Entry` ở cấp lớp và `@Id` cho DN. Các field còn lại mặc định được ánh xạ thành LDAP attribute theo tên field.

Ví dụ:

```java
@Entry(
    objectClasses = {
        "top",
        "person",
        "organizationalPerson",
        "inetOrgPerson"
    },
    base = "ou=people"
)
public class PersonEntry {

    @Id
    private Name dn;

    private String uid;
    private String cn;
    private String sn;
    private String mail;
}
```

Các field `uid`, `cn`, `sn` và `mail` được ánh xạ theo tên tương ứng. Không cần khai báo `@Attribute` nếu tên Java field giống tên LDAP attribute.

Khi tên field và tên attribute khác nhau, dùng `@Attribute`:

```java
@Attribute(name = "cn")
private String commonName;
```

Khi field biểu diễn một thành phần trong DN, dùng `@DnAttribute`:

```java
@DnAttribute("uid")
private String username;
```

ODM có quy tắc ánh xạ mặc định rộng: **field không được loại trừ sẽ được xem xét như dữ liệu LDAP**. Một field chỉ phục vụ ứng dụng cần được đánh dấu rõ ràng.

## 2. @Transient của Spring LDAP ODM

Annotation cần import:

```java
import org.springframework.ldap.odm.annotations.Transient;
```

Đặc điểm của annotation trong Spring LDAP:

| Thuộc tính | Giá trị |
| --- | --- |
| Package | `org.springframework.ldap.odm.annotations` |
| Target | `FIELD` |
| Retention | `RUNTIME` |
| Mục đích | Đánh dấu field trong lớp `@Entry` không được persist/map thành LDAP attribute |
| Thành phần áp dụng | Spring LDAP ODM / `OdmManager` |

Ví dụ:

```java
@Transient
private String displayLabel;
```

Field `displayLabel`:

- Vẫn tồn tại trong object Java.
- Có thể được ứng dụng gán hoặc tính toán.
- Không được ODM ánh xạ thành LDAP attribute.
- Không được ODM nạp giá trị từ LDAP attribute khi materialize entity.
- Không được ODM ghi giá trị của field này vào LDAP khi tạo hoặc cập nhật entity.

**`@Transient` không xóa field khỏi class.** Nó chỉ điều khiển mapping của Spring LDAP ODM. Nếu ứng dụng cần serialize object, tạo JSON, ghi log hoặc đưa object vào cache, field vẫn có thể xuất hiện tùy cách xử lý ở các tầng đó.

### 2.1. Khác với mặc định ánh xạ field

Không có `@Transient`:

```java
private String displayLabel;
```

ODM xem field này như LDAP attribute tên `displayLabel`.

Có `@Transient`:

```java
@Transient
private String displayLabel;
```

ODM bỏ qua field này. Nếu directory schema không định nghĩa `displayLabel`, việc cố ghi field không được loại trừ có thể dẫn tới lỗi schema hoặc lỗi khi server xử lý entry.

### 2.2. Ví dụ entity hoàn chỉnh

```java
import javax.naming.Name;
import org.springframework.ldap.odm.annotations.Attribute;
import org.springframework.ldap.odm.annotations.Entry;
import org.springframework.ldap.odm.annotations.Id;
import org.springframework.ldap.odm.annotations.Transient;

@Entry(
    objectClasses = {
        "top",
        "person",
        "organizationalPerson",
        "inetOrgPerson"
    },
    base = "ou=people"
)
public class PersonEntry {

    @Id
    private Name dn;

    @Attribute(name = "uid")
    private String uid;

    @Attribute(name = "cn")
    private String commonName;

    @Attribute(name = "sn")
    private String surname;

    @Attribute(name = "mail")
    private String email;

    @Transient
    private String displayLabel;

    @Transient
    private boolean selected;

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

    public String getCommonName() {
        return commonName;
    }

    public void setCommonName(String commonName) {
        this.commonName = commonName;
    }

    public String getSurname() {
        return surname;
    }

    public void setSurname(String surname) {
        this.surname = surname;
    }

    public String getEmail() {
        return email;
    }

    public void setEmail(String email) {
        this.email = email;
    }

    public String getDisplayLabel() {
        return displayLabel;
    }

    public void setDisplayLabel(String displayLabel) {
        this.displayLabel = displayLabel;
    }

    public boolean isSelected() {
        return selected;
    }

    public void setSelected(boolean selected) {
        this.selected = selected;
    }
}
```

Trong ví dụ, `uid`, `cn`, `sn` và `mail` là dữ liệu directory. `displayLabel` và `selected` chỉ là trạng thái ứng dụng.

## 3. Field dẫn xuất và trạng thái tạm thời

`@Transient` đặc biệt hữu ích cho những field có thể tính lại từ dữ liệu đã lưu.

### 3.1. Field dẫn xuất

Ví dụ nhãn hiển thị được ghép từ tên và UID:

```java
@Transient
private String displayLabel;

public void rebuildDisplayLabel() {
    if (commonName == null || commonName.isBlank()) {
        displayLabel = uid;
        return;
    }

    displayLabel = commonName + " [" + uid + "]";
}
```

Giá trị `displayLabel` không cần lưu vào LDAP vì có thể tính lại từ `commonName` và `uid`. Lợi ích:

- Không nhân đôi dữ liệu trong directory.
- Không phải cập nhật nhiều attribute khi tên hoặc UID thay đổi.
- Không cần thêm LDAP schema attribute chỉ để phục vụ UI.
- Quy tắc hiển thị có thể thay đổi mà không phải migration directory.

Khi đọc entity, ứng dụng gọi phương thức tính toán sau khi ODM đã nạp các field persistent:

```java
PersonEntry person = ldapTemplate.findOne(
        query,
        PersonEntry.class);

if (person != null) {
    person.rebuildDisplayLabel();
}
```

ODM không tự gọi `rebuildDisplayLabel()`. Nếu muốn giá trị dẫn xuất luôn có mặt, hãy gọi ở service/factory hoặc tạo DTO response.

### 3.2. Trạng thái giao diện

Ví dụ:

```java
@Transient
private boolean selected;

@Transient
private int searchScore;

@Transient
private String highlightText;
```

Những field này chỉ có ý nghĩa trong một lần tìm kiếm hoặc một màn hình. Không nên lưu `selected` hoặc `searchScore` vào LDAP vì chúng không phải thuộc tính bền vững của người dùng.

### 3.3. Dữ liệu tính toán có thể cache

Một entity có thể chứa giá trị đã tính:

```java
@Transient
private List<String> validationMessages;
```

Ứng dụng có thể gán danh sách thông báo sau khi kiểm tra dữ liệu. Khi đọc entity mới từ LDAP, ODM không khôi phục danh sách này. Nếu cần hiển thị lại, phải chạy validation hoặc dựng response từ dữ liệu persistent.

Đừng nhầm cache trong object với cache bền vững. Nếu cần lưu cache qua nhiều process hoặc nhiều lần restart, hãy dùng một cache store phù hợp thay vì mong đợi `@Transient` giữ dữ liệu.

## 4. Ảnh hưởng tới create, read và update

`@Transient` có tác dụng trong quy trình mapping ODM, không chỉ trong lúc ghi.

| Operation | Field có `@Transient` |
| --- | --- |
| Create | Không được ghi thành LDAP attribute |
| Find/lookup bằng ODM | Không được nạp từ LDAP attribute |
| Update | Không được ODM dùng để tạo modification cho LDAP attribute |
| Delete | Không ảnh hưởng tới việc xác định DN hoặc xóa entry |

### 4.1. Create entity

Giả sử ứng dụng tạo:

```java
PersonEntry person = new PersonEntry();
// Giả sử DN đã được gán thành javax.naming.Name hợp lệ cho entry.
person.setUid("lan");
person.setCommonName("Nguyen Thi Lan");
person.setSurname("Nguyen");
person.setEmail("lan@example.org");
person.setDisplayLabel("Nguyen Thi Lan [lan]");

ldapTemplate.create(person);
```

LDAP entry chỉ nhận các field được ODM mapping. `displayLabel` không được ghi thành attribute.

### 4.2. Đọc lại entity

Sau khi đọc entry bằng ODM:

```java
PersonEntry loaded = ldapTemplate.findOne(
        LdapQueryBuilder.query()
                .where("uid").is("lan"),
        PersonEntry.class);
```

ODM nạp `uid`, `cn`, `sn` và `mail` theo mapping. Field `displayLabel` không được lấy từ LDAP. Giá trị của field này phụ thuộc constructor/khởi tạo object và logic ứng dụng; nó không được khôi phục từ directory.

Nếu cần hiển thị nhãn:

```java
if (loaded != null) {
    loaded.rebuildDisplayLabel();
}
```

### 4.3. Update entity

```java
loaded.setCommonName("Nguyen Lan");
loaded.setDisplayLabel("Lan Nguyen [lan]");

ldapTemplate.update(loaded);
```

ODM cập nhật các field persistent theo mapping. Giá trị `displayLabel` không trở thành LDAP modification.

**Lưu ý:** Nếu LDAP entry đã có attribute cùng tên với field `@Transient`, annotation không phải lệnh xóa attribute đó. ODM bỏ qua field; việc xóa attribute đã tồn tại phải được thực hiện bằng thao tác LDAP tường minh hoặc migration dữ liệu.

### 4.4. @Transient không phải lệnh xóa attribute

Giả sử entry đang có:

```ldif
dn: uid=lan,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: lan
cn: Nguyen Thi Lan
sn: Nguyen
description: Old directory note
```

Nếu field `description` trong entity được đánh dấu `@Transient`, ODM sẽ không map giá trị đó vào object. Việc thêm annotation không tự xóa `description: Old directory note` khỏi LDAP.

Nếu nghiệp vụ yêu cầu xóa attribute, dùng modification riêng:

```java
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;

ModificationItem removeDescription = new ModificationItem(
        DirContext.REMOVE_ATTRIBUTE,
        new BasicAttribute("description"));

ldapTemplate.modifyAttributes(
        person.getDn(),
        new ModificationItem[] {removeDescription});
```

Chỉ thực hiện thao tác xóa khi đã xác định đúng DN, attribute và quyền. `@Transient` chỉ điều khiển ODM mapping, không thay thế CRUD attribute tường minh.

## 5. Kết hợp @DnAttribute và @Transient

Đây là một trường hợp quan trọng trong Spring LDAP ODM.

`@DnAttribute` lấy giá trị từ một thành phần của DN. Nhưng **`@DnAttribute` không tự loại field khỏi mapping attribute**. Tài liệu Spring LDAP nêu rõ field có `@DnAttribute` vẫn được ánh xạ thành LDAP attribute trừ khi được đánh dấu thêm `@Transient`.

### 5.1. Khi chỉ cần giá trị từ DN

Ví dụ DN:

```text
uid=lan,ou=engineering,ou=people,dc=example,dc=org
```

Entity:

```java
@DnAttribute(value = "ou", index = 0)
@Transient
private String department;
```

Ý nghĩa:

- `@DnAttribute` lấy thành phần `ou=engineering` từ DN theo index đã khai báo.
- `@Transient` ngăn field `department` được ánh xạ thêm thành LDAP attribute.

Nếu bỏ `@Transient`, field vừa có thể được lấy từ DN vừa tham gia mapping attribute theo tên Java field. Điều này không phải lúc nào cũng mong muốn.

### 5.2. Khi muốn lưu cả DN component và LDAP attribute

Nếu nghiệp vụ thực sự cần cả giá trị DN component và một attribute LDAP tương ứng, có thể dùng `@DnAttribute` cùng `@Attribute` theo thiết kế phù hợp, không đánh dấu `@Transient`:

```java
@Attribute(name = "ou")
@DnAttribute(value = "ou", index = 0)
private String department;
```

Lúc này field được dùng cho cả DN mapping và LDAP attribute mapping. Cần bảo đảm schema, naming rule và dữ liệu nhất quán.

### 5.3. Chọn đúng ý nghĩa

| Yêu cầu | Annotation |
| --- | --- |
| Lấy giá trị từ LDAP attribute | `@Attribute` hoặc mapping mặc định |
| Lấy giá trị từ DN component | `@DnAttribute` |
| Lấy từ DN nhưng không lưu thành LDAP attribute | `@DnAttribute` + `@Transient` |
| Chỉ dùng trong ứng dụng | `@Transient` |
| Vừa lấy từ DN vừa map thành LDAP attribute | `@DnAttribute` + `@Attribute` (không `@Transient`) |

Không gắn `@Transient` nếu field thực sự phải được lưu trong directory. Annotation sẽ khiến ODM bỏ qua mapping mà bạn đang mong đợi.

## 6. Phân biệt các annotation cùng tên

Trong hệ sinh thái Java/Spring có nhiều cơ chế mang tên “transient”. Chọn sai import có thể khiến mapping LDAP không hoạt động như dự kiến.

| Cơ chế | Package/cú pháp | Mục đích |
| --- | --- | --- |
| Spring LDAP ODM | `org.springframework.ldap.odm.annotations.Transient` | Bỏ field khỏi mapping LDAP ODM |
| Java Serialization | Từ khóa `transient` | Không đưa field vào Java Object Serialization mặc định |
| JPA | `jakarta.persistence.Transient` | Bỏ property khỏi persistence mapping JPA |
| Spring Data Commons | `org.springframework.data.annotation.Transient` | Bỏ property khỏi mapping framework Spring Data tương ứng |
| Jackson | `@JsonIgnore` | Bỏ property khỏi quá trình JSON serialization/deserialization theo cấu hình Jackson |

### 6.1. Dùng đúng import cho Spring LDAP ODM

Đúng:

```java
import org.springframework.ldap.odm.annotations.Transient;
```

Không thay bằng:

```java
import jakarta.persistence.Transient;
import org.springframework.data.annotation.Transient;
```

Spring LDAP repository yêu cầu entity được annotate bằng bộ annotation ODM của Spring LDAP. Dùng annotation cùng tên từ framework khác không phải cách thay thế tương đương cho ODM.

### 6.2. Java transient keyword không thay annotation ODM

Ví dụ:

```java
private transient String displayLabel;
```

Từ khóa Java `transient` thuộc cơ chế Java Serialization. Nó không diễn đạt rõ quy tắc mapping của Spring LDAP ODM. Để loại field khỏi ODM, dùng:

```java
@Transient
private String displayLabel;
```

Nếu một ứng dụng đồng thời cần loại field khỏi Java Serialization và LDAP ODM, có thể dùng cả Java modifier và annotation ODM, nhưng hai cơ chế giải quyết hai mục đích khác nhau. Chỉ thêm Java modifier không thay thế annotation Spring LDAP.

### 6.3. @Transient không thay @JsonIgnore

Một field được ODM bỏ qua vẫn có thể được Jackson serialize nếu nó có getter và được cấu hình đưa vào JSON:

```java
@Transient
private String internalCalculation;

public String getInternalCalculation() {
    return internalCalculation;
}
```

Nếu API không được phép trả field này, cần thiết kế DTO response hoặc cấu hình JSON riêng, chẳng hạn `@JsonIgnore` khi phù hợp. **Không dùng annotation persistence để thay thế kiểm soát dữ liệu API.**

### 6.4. @Transient không phải biện pháp bảo mật LDAP

Annotation không:

- Tạo hoặc sửa LDAP ACL.
- Ngăn service account đọc một attribute bằng truy vấn JNDI thủ công.
- Mã hóa giá trị trong directory.
- Ẩn field khỏi log, debugger hoặc JSON.
- Xóa attribute đã tồn tại trong directory.

Nếu field chứa dữ liệu nhạy cảm, cần kiểm soát quyền LDAP, query projection, DTO, logging và cache ở các tầng tương ứng.

## 7. Phạm vi tác dụng của @Transient

`@Transient` có hiệu lực trong mapping do Spring LDAP ODM thực hiện. Không nên mở rộng ý nghĩa của annotation sang mọi API xử lý LDAP.

| Cách truy cập | `@Transient` có điều khiển không? |
| --- | --- |
| `LdapTemplate.findOne(query, Entity.class)` | Có, khi dùng ODM mapping |
| `LdapTemplate.find(query, Entity.class)` | Có |
| `LdapTemplate.findByDn(dn, Entity.class)` | Có |
| `LdapTemplate.create(entity)` | Có |
| `LdapTemplate.update(entity)` | Có |
| Spring LDAP repository với ODM entity | Có, thông qua ODM |
| `LdapTemplate.search(query, AttributesMapper)` | Không tự động; mapper do ứng dụng quyết định |
| JNDI `DirContext.getAttributes(...)` | Không |
| `LdapTemplate.modifyAttributes(...)` | Không tự động |
| Jackson JSON serialization | Không |
| Java Serialization | Không |

### 7.1. AttributesMapper vẫn có thể đọc attribute

Nếu cần đọc một LDAP attribute bằng truy vấn thủ công, bạn vẫn có thể dùng `AttributesMapper`:

```java
String description = ldapTemplate.lookup(
        personDn,
        attrs -> {
            var attribute = attrs.get("description");
            if (attribute == null) {
                return null;
            }
            return (String) attribute.get();
        });
```

Field `description` trong một entity ODM có thể được đánh dấu `@Transient`, nhưng truy vấn thủ công ở trên vẫn đọc attribute `description` nếu directory trả về và caller có quyền. Đây là hai đường mapping khác nhau.

### 7.2. Query projection là vấn đề khác

`@Transient` không nhất thiết làm LDAP server ngừng gửi attribute. Nếu truy vấn lấy toàn bộ attribute, server vẫn có thể trả về attribute mà ODM sau đó bỏ qua.

Nếu mục tiêu là giảm dữ liệu truyền qua mạng, cần chọn attribute trả về trong search controls/query projection, ví dụ `SearchControls.setReturningAttributes(...)`. Nếu mục tiêu là giới hạn quyền đọc, cần cấu hình ACL phía directory.

Ba việc cần phân biệt:

- `@Transient`: field Java không tham gia ODM mapping.
- Returning attributes: client yêu cầu server gửi tập attribute nào.
- LDAP ACL: server cho phép principal đọc attribute nào.

## 8. Constructor, giá trị mặc định và vòng đời field

Vì ODM bỏ qua field transient, nó không nạp field đó từ LDAP. Giá trị thực tế trong object phụ thuộc cách object được tạo:

- Field primitive có giá trị mặc định của Java nếu không được khởi tạo.
- Field tham chiếu có thể là `null` nếu không được khởi tạo.
- Constructor hoặc field initializer có thể gán giá trị cục bộ.
- Logic ứng dụng có thể gán giá trị sau khi ODM hoàn tất mapping.

Không nên giả định ODM tự tính lại field dẫn xuất hoặc gọi một lifecycle callback của JPA.

### 8.1. Field có giá trị khởi tạo

```java
@Transient
private List<String> warnings = new ArrayList<>();
```

ODM không nạp `warnings` từ LDAP. Một object được tạo bằng constructor khởi tạo field có thể giữ danh sách rỗng; ứng dụng cần thêm warning sau đó.

### 8.2. Constructor có tham số

Khi thiết kế entity có constructor, bảo đảm constructor và quy trình khởi tạo phù hợp với cơ chế ODM của phiên bản Spring LDAP đang dùng. Field transient không có giá trị directory để khôi phục. Đừng thiết kế constructor bắt buộc một field transient phải có giá trị lấy từ LDAP.

Ví dụ, nếu `displayLabel` cần được tính từ `commonName`:

```java
public void rebuildDisplayLabel() {
    this.displayLabel =
            commonName == null ? uid : commonName + " [" + uid + "]";
}
```

Gọi phương thức sau khi object đã được nạp hoặc tạo từ dữ liệu persistent. Không mong đợi ODM tự gọi phương thức này.

### 8.3. Không dùng @Transient để che một lỗi mapping

Nếu field thực sự cần được lưu mà schema báo lỗi, đánh dấu transient sẽ chỉ che triệu chứng và làm mất dữ liệu persistence. Hãy kiểm tra:

- Tên attribute và chính tả.
- Schema có định nghĩa attribute không.
- Attribute có được phép bởi objectClass của entry không.
- Syntax, cardinality và converter có phù hợp không.
- Service account có quyền ghi attribute không.

Chỉ dùng `@Transient` khi field thực sự nằm ngoài mô hình dữ liệu LDAP.

## 9. Kết hợp với Spring LDAP repository

Spring LDAP repository làm việc với entity được annotate bằng Spring LDAP ODM. Ví dụ:

```java
import java.util.Optional;
import javax.naming.Name;
import org.springframework.data.ldap.repository.LdapRepository;

public interface PersonRepository
        extends LdapRepository<PersonEntry> {

    Optional<PersonEntry> findByUid(String uid);
}
```

Entity `PersonEntry` có thể chứa các field `@Transient`. Khi repository materialize entity, ODM áp dụng metadata của entity và bỏ qua field transient.

Ví dụ service:

```java
@Service
public class PersonDirectoryService {

    private final PersonRepository repository;

    public PersonDirectoryService(PersonRepository repository) {
        this.repository = repository;
    }

    public Optional<PersonEntry> findPerson(String uid) {
        return repository.findByUid(uid)
                .map(person -> {
                    person.rebuildDisplayLabel();
                    return person;
                });
    }
}
```

Field `displayLabel` được tính trong service sau khi repository trả entity. Nó không được lưu lại khi gọi repository save/update.

**Lưu ý:** `@Transient` không biến một field thành thuộc tính có thể query trong repository. Nếu cần tìm theo LDAP attribute, attribute đó phải thực sự tồn tại và được hỗ trợ bởi query/filter. Một field transient chỉ là trạng thái Java.

## 10. Những trường hợp nên và không nên dùng

| Trường hợp | Có nên dùng? | Lý do |
| --- | --- | --- |
| Nhãn hiển thị tính từ CN và UID | Có | Có thể tính lại |
| Cờ chọn dòng trong UI | Có | Chỉ thuộc trạng thái giao diện |
| Điểm xếp hạng một lần search | Có | Không phải dữ liệu directory |
| Cache validation messages | Có | Có thể tính lại |
| Giá trị lấy từ DN nhưng không cần attribute riêng | Có, kết hợp `@DnAttribute` | Tránh map trùng |
| Email chính của người dùng | Không | Đây là dữ liệu cần lưu trong directory |
| Số điện thoại liên hệ | Không nếu nghiệp vụ cần persistence | Annotation sẽ loại field khỏi mapping |
| Membership nhóm dùng cho authorization | Không | Không được bỏ khỏi mô hình dữ liệu nếu cần đọc/ghi |
| Mã nhân viên cần đồng bộ giữa hệ thống | Không | Cần lưu hoặc quản lý ở nguồn dữ liệu phù hợp |
| Password/hash được lưu trong directory | Không dùng `@Transient` để bảo vệ | Cần ACL và quy trình xác thực an toàn |

### 10.1. Khi dữ liệu chỉ phục vụ API

Nếu mục tiêu là response khác entity persistence, thường nên tạo DTO:

```java
public record PersonResponse(
        String uid,
        String displayName,
        String email,
        boolean selected) {
}
```

Service ánh xạ entity sang DTO:

```java
PersonResponse toResponse(PersonEntry person, boolean selected) {
    String displayName = person.getCommonName() == null
            ? person.getUid()
            : person.getCommonName();

    return new PersonResponse(
            person.getUid(),
            displayName,
            person.getEmail(),
            selected);
}
```

DTO giúp tách hợp đồng API khỏi mô hình LDAP. `@Transient` vẫn hữu ích cho field nội bộ của entity, nhưng không nên dùng entity ODM làm response model mặc định.

## 11. Kiểm thử @Transient

Một unit test kiểm tra annotation có thể xác nhận metadata đã khai báo, nhưng integration test mới chứng minh field thực sự không bị ghi/đọc qua ODM.

### 11.1. Kiểm tra annotation ở cấp field

```java
import java.lang.reflect.Field;
import org.springframework.ldap.odm.annotations.Transient;

Field field = PersonEntry.class.getDeclaredField("displayLabel");

if (!field.isAnnotationPresent(Transient.class)) {
    throw new AssertionError(
            "displayLabel must be excluded from ODM mapping");
}
```

Đây là kiểm tra cấu trúc class, không chứng minh directory server không nhận attribute.

### 11.2. Integration test create không ghi field transient

Chuẩn bị entity:

```java
PersonEntry person = new PersonEntry();
person.setUid("lan");
person.setCommonName("Nguyen Thi Lan");
person.setSurname("Nguyen");
person.setEmail("lan@example.org");
person.setDisplayLabel("Nguyen Thi Lan [lan]");

ldapTemplate.create(person);
```

Sau đó đọc trực tiếp LDAP attribute để xác minh `displayLabel` không tồn tại:

```java
Boolean hasDisplayLabel = ldapTemplate.lookup(
        person.getDn(),
        attrs -> attrs.get("displayLabel") != null);

if (Boolean.TRUE.equals(hasDisplayLabel)) {
    throw new AssertionError(
            "Transient field was persisted to LDAP");
}
```

Test phải dùng một directory test có schema và objectClass tương ứng. Nếu attribute không được schema cho phép, việc kiểm tra vẫn hữu ích nhưng cần bảo đảm test xác nhận đúng lý do field không được ghi, không chỉ vì server từ chối attribute.

### 11.3. Integration test read không nạp field transient

Seed entry có một attribute được schema hỗ trợ nhưng field Java tương ứng được đánh dấu transient:

```ldif
dn: uid=lan,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: lan
cn: Nguyen Thi Lan
sn: Nguyen
mail: lan@example.org
description: Directory-only value
```

Entity:

```java
@Transient
private String description;
```

Khi tìm entry bằng ODM, field `description` không được nạp từ LDAP. Để kiểm tra attribute vẫn tồn tại ở directory, dùng một `AttributesMapper` riêng hoặc truy vấn trực tiếp.

### 11.4. Integration test update không ghi field transient

1. Tạo hoặc đọc một entry.
2. Gán giá trị mới vào field transient.
3. Cập nhật entity qua ODM.
4. Đọc trực tiếp attribute trong LDAP.
5. Xác minh field transient không tạo LDAP modification.

Nếu attribute đã tồn tại trước đó, xác minh annotation không tự xóa nó. Việc xóa cần một test riêng cho `modifyAttributes(REMOVE_ATTRIBUTE)`.

### 11.5. Kiểm tra @DnAttribute kết hợp @Transient

Chuẩn bị DN có thành phần OU:

```text
uid=lan,ou=engineering,ou=people,dc=example,dc=org
```

Entity:

```java
@DnAttribute(value = "ou", index = 0)
@Transient
private String department;
```

Kiểm tra:

- Giá trị department được lấy từ thành phần `ou=engineering` theo cấu hình index 0 trong DN tương đối với base `ou=people`.
- Không có LDAP attribute riêng do field `department` tạo ra.
- Update entity không ghi một attribute `department` chỉ vì field này có giá trị.

### 11.6. Ma trận kiểm thử

| Test case | Kỳ vọng |
| --- | --- |
| Field persistent không có `@Transient` | ODM map theo tên field |
| Field có `@Transient` khi create | Không tạo LDAP attribute tương ứng |
| Field có `@Transient` khi find | Không nạp giá trị từ LDAP attribute |
| Field có `@Transient` khi update | Không tạo modification từ field |
| Attribute cũ đã tồn tại | Annotation không tự xóa attribute |
| `@DnAttribute` + `@Transient` | Đọc thành phần DN nhưng không map thêm LDAP attribute |
| Dùng sai package annotation | Test phát hiện field không được ODM loại như mong muốn |
| JSON serialize entity | Field vẫn có thể xuất hiện nếu không có DTO/JSON rule |
| Truy vấn bằng AttributesMapper | Có thể đọc attribute độc lập với ODM annotation |

## 12. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Create entry lỗi schema vì field phụ | Field chưa được loại khỏi mapping mặc định | Thêm Spring LDAP `@Transient` |
| Field transient luôn null sau khi find | ODM không nạp field đó | Tính lại trong service hoặc DTO |
| Đã dùng Java `transient` nhưng ODM vẫn map field | Nhầm Java Serialization với ODM | Dùng đúng annotation package |
| Import `jakarta.persistence.Transient` nhưng ODM vẫn ghi | Dùng annotation JPA thay annotation Spring LDAP | Import `org.springframework.ldap.odm.annotations.Transient` |
| Field `@DnAttribute` vẫn tạo attribute | `@DnAttribute` không tự loại mapping attribute | Kết hợp `@Transient` nếu chỉ cần DN component |
| Thêm `@Transient` nhưng attribute cũ vẫn còn | Annotation không phải lệnh xóa dữ liệu | Dùng LDAP modify/remove hoặc migration |
| Field không xuất hiện trong JSON như mong đợi | Nhầm ODM mapping với JSON serialization | Dùng DTO hoặc `@JsonIgnore` |
| Field nhạy cảm vẫn đọc được bằng JNDI | `@Transient` không phải ACL | Giới hạn quyền đọc ở LDAP server |
| Search thủ công vẫn trả attribute | `AttributesMapper` tự đọc dữ liệu, không qua ODM mapping | Kiểm soát returning attributes và mapper |
| Field dẫn xuất bị null trong API | Không có logic tính sau khi ODM load | Tính ở service/factory hoặc DTO |
| Gắn transient vào field cần lưu | Phân loại sai dữ liệu persistent | Bỏ annotation và kiểm tra schema |
| Update không xóa attribute cũ | ODM không quản lý field transient | Thực hiện modification rõ ràng |

## 13. Quy trình chọn field trước khi gắn @Transient

Trước khi đánh dấu một field, hãy trả lời:

1. Giá trị này có cần tồn tại trong LDAP sau khi ứng dụng restart không?
2. Giá trị có thể tính lại từ attribute hoặc DN hiện có không?
3. Giá trị chỉ phục vụ một request, màn hình hoặc tác vụ không?
4. Có hệ thống khác cần đọc giá trị này từ directory không?
5. Nếu bỏ mapping, có làm mất dữ liệu nghiệp vụ cần đồng bộ không?
6. Field có đang dùng `@DnAttribute` và cần tránh mapping thành attribute không?
7. Có cần ẩn field khỏi JSON/log/cache riêng không?
8. Nếu attribute đã tồn tại trong directory, có cần migration/xóa dữ liệu không?

Nếu field là dữ liệu nghiệp vụ bền vững, hãy giữ mapping và sửa schema/converter/ACL nếu cần. Nếu field chỉ là dữ liệu tính toán hoặc trạng thái tạm thời, `@Transient` là lựa chọn phù hợp.

## 14. Bài tập tự luyện

**Câu 1.** Vì sao một field Java không có annotation vẫn có thể trở thành LDAP attribute?

*Gợi ý:* ODM ánh xạ field theo tên mặc định; annotation điều chỉnh cách ánh xạ.

**Câu 2.** `@Transient` của Spring LDAP nằm trong package nào?

*Gợi ý:* `org.springframework.ldap.odm.annotations`.

**Câu 3.** Field `displayLabel` được đánh dấu `@Transient`. Khi đọc entity mới từ LDAP, ODM có khôi phục giá trị label cũ không?

*Gợi ý:* Không. ODM không map field này; ứng dụng cần tính lại hoặc gán sau khi load.

**Câu 4.** Khác biệt giữa Java `transient` và Spring LDAP `@Transient` là gì?

*Gợi ý:* Một thuộc Java Serialization; một điều khiển mapping ODM.

**Câu 5.** Nếu dùng `@DnAttribute("ou")` mà không có `@Transient`, field có thể được ánh xạ như thế nào?

*Gợi ý:* Ngoài việc lấy thành phần DN, field vẫn được ánh xạ thành LDAP attribute theo mặc định.

**Câu 6.** Vì sao cần thêm `@Transient` vào field có `@DnAttribute` trong trường hợp chỉ cần DN component?

*Gợi ý:* Để tránh field được lưu thêm thành attribute LDAP.

**Câu 7.** Thêm `@Transient` vào field đã có attribute trong LDAP có tự xóa attribute không?

*Gợi ý:* Không. Annotation chỉ loại field khỏi ODM mapping; xóa phải dùng modification riêng.

**Câu 8.** `@Transient` có ngăn Jackson serialize field không?

*Gợi ý:* Không. DTO hoặc cấu hình JSON là trách nhiệm của tầng API.

**Câu 9.** Một truy vấn `LdapTemplate.search(query, AttributesMapper)` có bị `@Transient` chặn không?

*Gợi ý:* Không. AttributesMapper do ứng dụng định nghĩa và có thể đọc attribute trực tiếp.

**Câu 10.** Field chứa email nhân viên có nên đánh dấu transient nếu email cần được đồng bộ giữa các hệ thống?

*Gợi ý:* Không, nếu LDAP là nguồn lưu trữ cho dữ liệu đó. Field cần mapping persistent và schema phù hợp.

## 15. Ghi nhớ

- Spring LDAP ODM mặc định ánh xạ field theo tên field thành LDAP attribute.
- **`@Transient` đúng package là `org.springframework.ldap.odm.annotations.Transient`**, dùng trên field của lớp `@Entry`.
- Field transient vẫn tồn tại trong Java object, nhưng ODM không map field đó khi đọc/ghi LDAP.
- Field dẫn xuất, trạng thái UI, search score và cache tạm thời là các trường hợp phù hợp.
- Field transient không được tự động tính lại sau khi load; ứng dụng phải gán hoặc tính lại.
- **`@DnAttribute` không tự loại field khỏi attribute mapping.** Kết hợp `@DnAttribute` + `@Transient` khi chỉ cần lấy giá trị từ DN.
- Java `transient`, JPA `@Transient`, Spring Data Commons `@Transient` và Jackson `@JsonIgnore` là các cơ chế khác nhau.
- Annotation không xóa attribute đã tồn tại, không thay ACL, không ẩn field khỏi JSON/log và không chặn JNDI/AttributesMapper.
- Kiểm thử create, find, update và trường hợp attribute cũ để xác minh mapping thực tế.
- Nếu dữ liệu là thông tin nghiệp vụ cần tồn tại trong directory, đừng đánh dấu transient để né lỗi schema.

**Tài liệu tham khảo chính thức:**

- [Spring LDAP — Object-Directory Mapping (ODM)](https://docs.spring.io/spring-ldap/reference/odm.html): quy tắc ánh xạ field mặc định, `@Entry`, `@Id`, `@Attribute`, `@DnAttribute` và `@Transient`.
- [Spring LDAP API — Transient](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/odm/annotations/Transient.html): target FIELD, retention RUNTIME và mục đích không persist field vào LDAP.
- [Spring LDAP API — Entry](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/odm/annotations/Entry.html): entity class và quy tắc các field được persist trừ khi đánh dấu Transient.
- [Spring LDAP — Repositories](https://docs.spring.io/spring-ldap/reference/repositories.html): repository sử dụng entity được annotate bằng ODM.
- [Spring LDAP API — LdapTemplate](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/LdapTemplate.html): object mapping operations và thao tác LDAP trực tiếp.
- [Spring Data Commons — Transient](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/annotation/Transient.html): phân biệt annotation mapping với Java Serialization transient.
