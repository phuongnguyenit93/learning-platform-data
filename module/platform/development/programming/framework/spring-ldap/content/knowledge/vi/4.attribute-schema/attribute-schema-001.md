# Attribute đơn trị và đa trị

Trong chương **Attribute và schema** của **SPRING_LDAP**, một entry LDAP được mô tả bằng các **attribute** (thuộc tính) như `cn`, `sn`, `employeeNumber`, `telephoneNumber` hoặc `member`. Một attribute có thể có **một giá trị** hoặc **nhiều giá trị**; khả năng đó do *attribute type* trong schema quy định, chứ không thể kết luận chỉ từ việc dữ liệu hiện tại đang có một giá trị.

Đây là kiến thức nền tảng khi làm việc với dịch vụ thư mục qua **Spring LDAP**: `LdapTemplate`, `LdapClient` và ODM đều phải tôn trọng schema do máy chủ áp dụng. Nếu ứng dụng đọc một attribute đa trị như chuỗi đơn, các giá trị còn lại có thể bị bỏ sót. Nếu ứng dụng dùng thao tác thay thế toàn bộ khi chỉ muốn thêm một giá trị, dữ liệu cũ có thể bị mất. Hiểu đúng số lượng giá trị cho phép cũng giúp viết filter, xử lý lỗi, phân quyền và kiểm thử truy cập LDAP an toàn.

**Sau bài này, bạn có thể:**

1. Phân biệt attribute đơn trị (*single-valued*) và đa trị (*multi-valued*).
2. Đọc quy định `SINGLE-VALUE` trong schema, phân biệt với `MUST` và `MAY` của object class.
3. Biểu diễn attribute nhiều giá trị trong LDIF, Java/JNDI và Spring LDAP.
4. Chọn chính xác thao tác **thêm một giá trị**, **thay một tập giá trị** hoặc **xóa một giá trị**.
5. Nhận diện lỗi schema, lỗi dữ liệu trùng và các rủi ro làm mất giá trị khi cập nhật.

## 1. Attribute là gì?

Một **entry** trong LDAP là đối tượng nằm tại một **Distinguished Name (DN)**. Entry chứa tập các attribute. Mỗi attribute được nhận diện bởi **attribute description**, thông thường bắt đầu từ tên của *attribute type*, và có một hay nhiều giá trị được lưu theo quy tắc schema.

Ví dụ biểu diễn bằng LDIF:

```ldif
dn: uid=lan,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: lan
cn: Nguyen Thi Lan
sn: Nguyen
employeeNumber: E-1042
telephoneNumber: +84 24 3555 0101
telephoneNumber: +84 28 3555 0102
mail: lan@example.org
```

Trong ví dụ:

- `employeeNumber` đang có **một** giá trị là `E-1042`.
- `telephoneNumber` có **hai** giá trị, được viết trên hai dòng LDIF cùng tên attribute.
- `objectClass` xuất hiện nhiều lần vì entry thuộc nhiều object class.
- `cn`, `sn`, `mail` mỗi thuộc tính hiện chỉ có một giá trị trong entry mẫu; **chưa đủ để suy ra schema chỉ cho phép một**.

Một cách hình dung:

```text
Entry: uid=lan,ou=people,dc=example,dc=org
├── employeeNumber
│   └── "E-1042"
├── telephoneNumber
│   ├── "+84 24 3555 0101"
│   └── "+84 28 3555 0102"
└── objectClass
    ├── top
    ├── person
    ├── organizationalPerson
    └── inetOrgPerson
```

Các giá trị trong attribute đa trị tạo thành một tập theo ngữ nghĩa LDAP; chúng **không tạo thêm các entry con** và cũng **không phải các RDN mới**. Một DN có nhiều RDN và một attribute có nhiều giá trị là hai khái niệm độc lập.

## 2. Đơn trị và đa trị: quy tắc nằm ở schema

**Attribute đơn trị** có tối đa một giá trị trong một entry. Attribute đó có thể vắng mặt nếu object class và các quy tắc liên quan cho phép; "đơn trị" **không đồng nghĩa** với "luôn bắt buộc phải có".

**Attribute đa trị** có thể chứa nhiều giá trị cùng thuộc một attribute trong một entry. Entry cụ thể có thể chỉ lưu một giá trị, nhưng schema vẫn cho phép nhiều giá trị. Nếu chưa có giá trị nào thì attribute thường **vắng mặt**, không được hiểu là một danh sách rỗng đã được lưu thành attribute riêng biệt.

| Đặc điểm | Attribute đơn trị | Attribute đa trị |
| --- | --- | --- |
| Số giá trị tối đa theo schema | 1 | Có thể lớn hơn 1; vẫn chịu giới hạn của máy chủ/chính sách. |
| Khi đang có một giá trị | Không được thêm giá trị thứ hai vào cùng attribute. | Có thể thêm giá trị khác nếu hợp lệ và không bị coi là trùng. |
| Khi chưa có giá trị | Có thể thêm một giá trị nếu attribute được phép. | Có thể thêm một hoặc nhiều giá trị nếu hợp lệ. |
| Thao tác cập nhật phổ biến | Thay giá trị hiện có hoặc xóa nếu không bắt buộc. | Thêm/xóa giá trị cụ thể hoặc thay toàn bộ tập giá trị. |
| Ví dụ theo schema thông dụng | `employeeNumber` của `inetOrgPerson`. | `telephoneNumber`, `member` của nhóm, `objectClass`. |

### `SINGLE-VALUE` là thông tin của attribute type

Trong mô tả schema LDAP, một *attribute type* có thể mang cờ `SINGLE-VALUE`. Ví dụ trích lược để minh họa ý nghĩa (không phải khai báo schema hoàn chỉnh):

```text
attributeTypes: ( ... NAME 'employeeNumber' ... SINGLE-VALUE )
attributeTypes: ( ... NAME 'telephoneNumber' ... )
```

Với attribute type được khai báo `SINGLE-VALUE`, máy chủ chỉ cho phép tối đa một giá trị của attribute đó trong mỗi entry. Trong schema LDAP tiêu chuẩn, nếu **không có cờ `SINGLE-VALUE`**, attribute type về mặt định nghĩa cho phép nhiều giá trị. Tuy vậy, ràng buộc bổ sung của máy chủ, ứng dụng hoặc chính sách tổ chức vẫn có thể giới hạn dữ liệu thực tế.

Không nên tự suy đoán từ tên attribute. Ví dụ, một người chỉ nhập một email không biến `mail` thành đơn trị; trong nhiều schema LDAP thông dụng, `mail` có thể nhận nhiều giá trị. Hãy tra **schema thực tế của máy chủ** trước khi cố định thuộc tính ở tầng Java thành một chuỗi duy nhất.

### Tính "có một giá trị" ở dữ liệu khác tính "chỉ được có một giá trị" ở schema

Giả sử hai entry đều có:

```ldif
telephoneNumber: +84 24 3555 0101
```

Điều đó chỉ cho biết **mỗi entry hiện có một số điện thoại**. Khi schema cho phép đa trị, ứng dụng vẫn có thể bổ sung:

```ldif
telephoneNumber: +84 28 3555 0102
```

Trong khi đó, sau khi `employeeNumber: E-1042` đã tồn tại, yêu cầu **thêm** `employeeNumber: E-1043` vào cùng entry sẽ vi phạm ràng buộc đơn trị. Muốn đổi mã nhân viên, phải **thay thế** giá trị đang có theo quy tắc nghiệp vụ.

## 3. Đừng nhầm `SINGLE-VALUE` với `MUST` và `MAY`

Schema LDAP có nhiều loại quy tắc. Hai loại thường gặp trong cùng một entry là:

- **Attribute type** quy định cú pháp, matching rules và **có được phép có nhiều giá trị hay không** (ví dụ cờ `SINGLE-VALUE`).
- **Object class** quy định một entry **bắt buộc phải có những attribute nào** (`MUST`) và **được phép có những attribute nào** (`MAY`).

Hai nhóm quy tắc này trả lời **hai câu hỏi khác nhau**:

| Câu hỏi | Quy tắc tương ứng |
| --- | --- |
| Entry thuộc lớp này có bắt buộc phải chứa `cn` không? | `MUST` của object class. |
| Entry thuộc lớp này có thể chứa `telephoneNumber` không? | `MAY` của object class (hoặc do lớp kế thừa/auxiliary cho phép). |
| Một entry có thể có hai giá trị `telephoneNumber` không? | Định nghĩa attribute type, chẳng hạn `SINGLE-VALUE`. |
| Nếu một attribute bắt buộc có mặt, có thể xóa hết giá trị không? | Không, vì sẽ vi phạm yêu cầu `MUST`. |

Ví dụ, object class `person` thường yêu cầu `cn` và `sn`. Yêu cầu đó không có nghĩa `cn` và `sn` phải đơn trị: tùy schema, một entry có thể chứa nhiều giá trị được chấp nhận cho những attribute này.

Ngược lại, `employeeNumber` có thể là attribute **đơn trị nhưng không bắt buộc** trong `inetOrgPerson`. Một entry có thể hợp lệ dù thiếu `employeeNumber`, nếu các quy tắc khác không yêu cầu nó.

**Hãy phân biệt ba trạng thái:**

1. Attribute **không được phép** xuất hiện trong entry theo object class/schema.
2. Attribute **được phép nhưng không bắt buộc**; có thể không có giá trị.
3. Attribute **bắt buộc** phải tồn tại; số lượng giá trị tối đa vẫn do attribute type quyết định.

Việc schema cho phép một attribute chưa đồng nghĩa tài khoản LDAP có **quyền ghi** attribute đó. Access Control List (ACL), thuộc tính chỉ đọc và chính sách máy chủ vẫn có thể từ chối cập nhật.

## 4. Đa trị không phải danh sách có thứ tự

Với các attribute đa trị như `telephoneNumber` hoặc `member`, LDAP về cơ bản xem các giá trị là **tập**, không cam kết thứ tự ổn định cho ứng dụng. Điều này có ba hệ quả:

- **Không dựa vào vị trí:** "số điện thoại đầu tiên" được đọc ở lần này không mặc nhiên là "số ưu tiên" ở lần khác.
- **Không mặc định chấp nhận trùng:** máy chủ sử dụng matching rule của attribute để xác định giá trị có trùng/ tương đương hay không; gửi lại giá trị đã tồn tại có thể gây lỗi.
- **Không biểu diễn độ ưu tiên bằng thứ tự:** nếu ứng dụng cần số điện thoại chính, hãy dùng một quy tắc nghiệp vụ/attribute riêng hoặc một mô hình lưu trữ hỗ trợ ý nghĩa đó.

Ví dụ LDIF sau không nói rằng số ở dòng đầu tiên luôn phải được dùng để gọi trước:

```ldif
telephoneNumber: +84 24 3555 0101
telephoneNumber: +84 28 3555 0102
```

Nếu muốn hiển thị ổn định trong giao diện, ứng dụng có thể **sắp xếp bản sao** các giá trị sau khi đọc, nhưng việc sắp xếp này là lựa chọn của ứng dụng, không phải thứ tự gốc được LDAP bảo đảm.

### Kiểu giá trị khác với số lượng giá trị

Một attribute type còn có **syntax** (ví dụ Directory String, Telephone Number, DN hoặc Octet String) và matching rules. **Syntax không quyết định cardinality**.

- Attribute đa trị vẫn có thể chứa các giá trị kiểu chuỗi.
- Attribute đơn trị có thể chứa giá trị nhị phân.
- Mỗi giá trị có thể cần chuyển đổi từ `byte[]` hoặc một kiểu phù hợp; không ép mọi attribute thành `String`.
- Khi so sánh dữ liệu, matching rules của LDAP có thể khác so sánh `String.equals()` trong Java, ví dụ về chữ hoa/chữ thường hoặc cách chuẩn hóa giá trị.

Vì vậy, ứng dụng Spring LDAP cần biết cả **kiểu dữ liệu** và **số lượng giá trị** của từng thuộc tính.

## 5. Ví dụ thực tế: hồ sơ nhân viên và nhóm

Một entry nhân viên dùng các attribute thông dụng của `inetOrgPerson`:

```ldif
dn: uid=lan,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: lan
cn: Nguyen Thi Lan
sn: Nguyen
employeeNumber: E-1042
telephoneNumber: +84 24 3555 0101
telephoneNumber: +84 28 3555 0102
mail: lan@example.org
```

Ở đây, `employeeNumber` minh họa thông tin chỉ nên có một giá trị trong một entry theo định nghĩa attribute type tương ứng. `telephoneNumber` minh họa thông tin có thể có nhiều giá trị. `mail` hiện chỉ chứa một giá trị trong dữ liệu mẫu; không suy từ đó rằng mọi schema đều đặt nó là đơn trị.

Một entry nhóm `groupOfNames` có thể lưu nhiều DN thành viên trong attribute `member`:

```ldif
dn: cn=developers,ou=groups,dc=example,dc=org
objectClass: top
objectClass: groupOfNames
cn: developers
member: uid=lan,ou=people,dc=example,dc=org
member: uid=minh,ou=people,dc=example,dc=org
```

Cần chú ý:

1. **Một entry nhóm** chứa **một attribute `member` đa trị**; mỗi giá trị là DN của một thành viên.
2. Trong schema `groupOfNames` thông dụng, `member` là thuộc tính **bắt buộc**. Việc xóa giá trị thành viên cuối cùng có thể làm entry vi phạm schema; nếu cần nhóm rỗng phải có thiết kế/schema hỗ trợ trường hợp đó.
3. Một nhóm có nhiều thành viên không có nghĩa mỗi thành viên là entry con của nhóm. Giá trị `member` là **tham chiếu DN** tới entry khác, có thể nằm ở nhánh `ou=people`.

Các ví dụ này chỉ có ý nghĩa khi máy chủ đã có schema hỗ trợ object class/attribute tương ứng và account đang dùng có đủ quyền thao tác.

## 6. Đọc attribute đơn trị và đa trị với Spring LDAP

Giả sử cấu hình `ContextSource` của ứng dụng đặt base DN là `dc=example,dc=org`. Trong `LdapTemplate`, DN truyền vào ở ví dụ dưới đây **tương đối với base**: `uid=lan,ou=people`.

### Cách ngắn gọn với `DirContextOperations`

`LdapTemplate.lookupContext()` cho phép đọc entry như một `DirContextOperations`:

```java
import javax.naming.Name;
import org.springframework.ldap.core.DirContextOperations;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

public class PersonAttributeReader {

    private final LdapTemplate ldapTemplate;

    public PersonAttributeReader(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public void printContact(String uid) {
        Name dn = LdapNameBuilder.newInstance("ou=people")
                .add("uid", uid)
                .build();

        DirContextOperations entry = ldapTemplate.lookupContext(dn);

        // Đơn trị theo schema ví dụ:
        String employeeNumber = entry.getStringAttribute("employeeNumber");

        // Đa trị: lấy toàn bộ các giá trị thay vì lấy một giá trị.
        String[] phones = entry.getStringAttributes("telephoneNumber");

        System.out.println("employeeNumber = " + employeeNumber);
        if (phones != null) {
            for (String phone : phones) {
                System.out.println("telephoneNumber = " + phone);
            }
        }
    }
}
```

Trong ví dụ này:

- `getStringAttribute("employeeNumber")` phù hợp vì schema định nghĩa attribute là đơn trị.
- `getStringAttributes("telephoneNumber")` phù hợp vì cần xử lý toàn bộ số điện thoại.
- Attribute không hiện diện cần được xử lý như giá trị thiếu/vắng mặt. Đừng mặc định một thuộc tính tùy chọn luôn tồn tại.
- Không áp dụng các phương thức chuyển chuỗi cho thuộc tính có syntax nhị phân, trừ khi đã biết cách ánh xạ đúng.

**Sai lầm phổ biến:** gọi `getStringAttribute("telephoneNumber")` rồi cho rằng entry chỉ có đúng một số điện thoại. Nếu API lấy một giá trị từ attribute đa trị, các giá trị còn lại có thể bị bỏ sót; ứng dụng không nên chọn một giá trị tùy ý khi nghiệp vụ cần toàn bộ.

### Cách tổng quát với JNDI `Attributes` và `Attribute`

`LdapTemplate.lookup()` có thể dùng `AttributesMapper` để chuyển dữ liệu LDAP thành đối tượng Java. Đối với attribute đa trị, JNDI cung cấp `Attribute.getAll()` để duyệt từng giá trị:

```java
import java.util.ArrayList;
import java.util.List;
import javax.naming.Name;
import javax.naming.NamingEnumeration;
import javax.naming.NamingException;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;

import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

record PersonContact(String employeeNumber, List<String> phoneNumbers) {}

public class PersonContactRepository {

    private final LdapTemplate ldapTemplate;

    public PersonContactRepository(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public PersonContact load(String uid) {
        Name dn = LdapNameBuilder.newInstance("ou=people")
                .add("uid", uid)
                .build();

        return ldapTemplate.lookup(dn, (AttributesMapper<PersonContact>) attrs -> {
            Attribute codeAttr = attrs.get("employeeNumber");
            String employeeNumber = codeAttr == null
                    ? null : (String) codeAttr.get();

            return new PersonContact(
                    employeeNumber,
                    readAllStrings(attrs, "telephoneNumber"));
        });
    }

    private static List<String> readAllStrings(Attributes attrs, String name)
            throws NamingException {
        Attribute attr = attrs.get(name);
        if (attr == null) {
            return List.of();
        }

        List<String> result = new ArrayList<>();
        NamingEnumeration<?> values = attr.getAll();
        try {
            while (values.hasMore()) {
                result.add((String) values.next());
            }
        } finally {
            values.close();
        }
        return List.copyOf(result);
    }
}
```

Đoạn mã giả định `telephoneNumber` có giá trị chuỗi, đúng với schema của ví dụ. Nếu đọc thuộc tính nhị phân, phải xử lý đúng kiểu giá trị thay cho cast `(String)`. `List.copyOf(result)` chỉ tạo bản sao bất biến, **không làm cho thứ tự đọc LDAP trở nên được bảo đảm**.

### Khi dùng `LdapClient` hoặc ODM

API fluent `LdapClient` có thể giúp mô tả thao tác đọc/tìm kiếm rõ ràng hơn; tên phương thức và overload cần đối chiếu phiên bản Spring LDAP đang dùng. Dù chọn API nào, vẫn phải quyết định thuộc tính nào cần trả về dưới dạng **một giá trị**, **tập giá trị** hoặc **dữ liệu nhị phân**.

ODM của Spring LDAP hỗ trợ ánh xạ entry vào Java object. Một mô hình khái niệm như sau:

```java
import java.util.Set;
import javax.naming.Name;

import org.springframework.ldap.odm.annotations.Attribute;
import org.springframework.ldap.odm.annotations.Entry;
import org.springframework.ldap.odm.annotations.Id;

@Entry(base = "ou=people", objectClasses = {
        "top", "person", "organizationalPerson", "inetOrgPerson"
})
public class PersonEntry {
    @Id
    private Name dn;

    @Attribute(name = "employeeNumber")
    private String employeeNumber;

    @Attribute(name = "telephoneNumber")
    private Set<String> phoneNumbers;

    // Constructor mặc định và getter/setter theo cách sử dụng ODM.
}
```

Sự lựa chọn `String` cho `employeeNumber` và `Set<String>` cho `telephoneNumber` thể hiện mục tiêu lưu trữ của mô hình. Tính tương thích chính xác giữa kiểu collection, converter và thao tác save phải được kiểm tra theo phiên bản thư viện và schema đang áp dụng. Nếu nghiệp vụ cần giữ mọi giá trị không có thứ tự, `Set` thường diễn tả ý định tốt hơn một chuỗi đơn.

## 7. Tạo entry có attribute nhiều giá trị

Khi tạo entry mới, `DirContextAdapter` cho phép đặt giá trị đơn hoặc một tập giá trị trước khi gọi `LdapTemplate.bind()`:

```java
import javax.naming.Name;

import org.springframework.ldap.core.DirContextAdapter;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

public class PersonCreator {

    private final LdapTemplate ldapTemplate;

    public PersonCreator(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public void createLan() {
        Name dn = LdapNameBuilder.newInstance("ou=people")
                .add("uid", "lan")
                .build();

        DirContextAdapter entry = new DirContextAdapter(dn);

        entry.setAttributeValues("objectClass", new String[] {
                "top", "person", "organizationalPerson", "inetOrgPerson"
        });
        entry.setAttributeValue("uid", "lan");
        entry.setAttributeValue("cn", "Nguyen Thi Lan");
        entry.setAttributeValue("sn", "Nguyen");
        entry.setAttributeValue("employeeNumber", "E-1042");
        entry.setAttributeValues("telephoneNumber", new String[] {
                "+84 24 3555 0101",
                "+84 28 3555 0102"
        });

        ldapTemplate.bind(entry);
    }
}
```

**Điểm cần nhớ:**

- `setAttributeValue(name, value)` thiết lập một giá trị, thích hợp cho thuộc tính đơn trị theo schema hoặc trường hợp thực sự chỉ cần một.
- `setAttributeValues(name, values)` thiết lập toàn bộ các giá trị của thuộc tính trên đối tượng đang xây dựng.
- `objectClass` có nhiều giá trị và phải gồm những object class phù hợp để entry được chấp nhận theo schema.
- `bind(entry)` ở đây là **thêm entry** vào thư mục, khác với **authentication bind** dùng để xác minh danh tính bằng thông tin đăng nhập.
- Việc tạo entry thành công còn phụ thuộc DN chưa tồn tại, object class/attribute hợp lệ, ACL và các ràng buộc của máy chủ.

Không cần cố tạo một attribute đa trị với giá trị giả để "dự phòng" khi chưa có số điện thoại: nếu attribute là tùy chọn và không có giá trị, thường nên để attribute **vắng mặt**.

## 8. Sửa giá trị: thêm, thay thế và xóa khác nhau thế nào?

Cùng một attribute đa trị có thể được cập nhật theo ba ý định hoàn toàn khác:

| Ý định | Thao tác JNDI phù hợp | Kết quả mong muốn |
| --- | --- | --- |
| Thêm một số điện thoại, giữ các số cũ | `ADD_ATTRIBUTE` với giá trị mới | Tập giá trị được mở rộng. |
| Đổi toàn bộ danh sách số điện thoại | `REPLACE_ATTRIBUTE` với tập mới | Các giá trị cũ bị thay bởi tập mới. |
| Bỏ riêng một số điện thoại | `REMOVE_ATTRIBUTE` với giá trị cần xóa | Giá trị được chỉ định bị xóa, các giá trị khác giữ lại. |
| Đổi mã nhân viên đơn trị | `REPLACE_ATTRIBUTE` với một giá trị mới | Giá trị đơn cũ được thay. |

### Thêm một giá trị mà không xóa giá trị đã có

```java
import javax.naming.Name;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;

import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

public class ContactUpdater {

    private final LdapTemplate ldapTemplate;

    public ContactUpdater(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    private Name personDn(String uid) {
        return LdapNameBuilder.newInstance("ou=people")
                .add("uid", uid)
                .build();
    }

    public void addPhone(String uid, String phone) {
        ModificationItem addPhone = new ModificationItem(
                DirContext.ADD_ATTRIBUTE,
                new BasicAttribute("telephoneNumber", phone));

        ldapTemplate.modifyAttributes(
                personDn(uid), new ModificationItem[] {addPhone});
    }

    public void removePhone(String uid, String phone) {
        ModificationItem removePhone = new ModificationItem(
                DirContext.REMOVE_ATTRIBUTE,
                new BasicAttribute("telephoneNumber", phone));

        ldapTemplate.modifyAttributes(
                personDn(uid), new ModificationItem[] {removePhone});
    }

    public void replaceEmployeeNumber(String uid, String employeeNumber) {
        ModificationItem replaceCode = new ModificationItem(
                DirContext.REPLACE_ATTRIBUTE,
                new BasicAttribute("employeeNumber", employeeNumber));

        ldapTemplate.modifyAttributes(
                personDn(uid), new ModificationItem[] {replaceCode});
    }
}
```

Với `ADD_ATTRIBUTE`, máy chủ sẽ kiểm tra giá trị mới có hợp lệ, có bị xem là trùng với một giá trị đã có và có bị giới hạn bởi `SINGLE-VALUE` hay không. Với `REMOVE_ATTRIBUTE` có ghi rõ giá trị, chỉ giá trị phù hợp mới là mục tiêu xóa. Nếu sử dụng thao tác xóa **toàn bộ attribute** không kèm giá trị, mọi giá trị của attribute đó có thể bị loại bỏ; nên tránh khi mục tiêu chỉ là bỏ một thành viên hoặc một số điện thoại.

### Thay toàn bộ tập giá trị

Nếu hệ thống quản lý hồ sơ là **nguồn dữ liệu chính** của danh sách số điện thoại, nó có thể chủ động thay thế toàn bộ danh sách bằng `REPLACE_ATTRIBUTE`:

```java
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;

// Bên trong ContactUpdater:
public void replaceAllPhones(String uid) {
    BasicAttribute phones = new BasicAttribute("telephoneNumber");
    phones.add("+84 24 3555 0199");
    phones.add("+84 28 3555 0188");

    ModificationItem replacePhones = new ModificationItem(
            DirContext.REPLACE_ATTRIBUTE, phones);

    ldapTemplate.modifyAttributes(
            personDn(uid), new ModificationItem[] {replacePhones});
}
```

**Cảnh báo mất dữ liệu:** nếu entry đang chứa ba số điện thoại nhưng request chỉ gửi một số mới, `REPLACE_ATTRIBUTE` sẽ thay **toàn bộ tập** bằng đúng số đó. Hai số còn lại sẽ không được giữ lại trừ khi được đưa vào tập giá trị thay thế.

Điều này cũng đúng với `DirContextOperations.setAttributeValues()` kết hợp `modifyAttributes()`: thao tác này nhằm đặt một tập giá trị mới cho attribute. Chỉ dùng khi ứng dụng có ý định và quyền cập nhật toàn bộ tập.

### Trường hợp nhóm có `member` đa trị

Với nhóm:

```ldif
dn: cn=developers,ou=groups,dc=example,dc=org
objectClass: top
objectClass: groupOfNames
cn: developers
member: uid=lan,ou=people,dc=example,dc=org
member: uid=minh,ou=people,dc=example,dc=org
```

Để thêm một người, dùng thao tác tương đương `ADD_ATTRIBUTE("member", "uid=an,...")` thay vì thay toàn bộ `member` bằng người mới. Nếu xóa tất cả thành viên, schema `groupOfNames` có thể từ chối vì `member` là attribute bắt buộc.

Khi các giá trị là DN, hãy xây dựng DN thành viên bằng API xử lý tên của LDAP thay vì nối chuỗi từ đầu vào. DN thay đổi do rename/move cũng cần được xử lý theo cơ chế tham chiếu và khả năng của máy chủ, không giả định mọi giá trị `member` sẽ tự được cập nhật.

## 9. Tìm kiếm trên attribute đa trị

LDAP filter so sánh một attribute đa trị với giá trị nhất định theo matching rules. Điều kiện equality có thể khớp khi **ít nhất một giá trị** của attribute đáp ứng phép so sánh.

Ví dụ entry Lan chứa:

```ldif
telephoneNumber: +84 24 3555 0101
telephoneNumber: +84 28 3555 0102
```

Nếu máy chủ hỗ trợ equality matching cho attribute và chuẩn hóa giá trị tương ứng, filter thích hợp có thể là:

```text
(telephoneNumber=+84 28 3555 0102)
```

Entry vẫn có thể khớp dù số đó không phải giá trị xuất hiện đầu tiên trong LDIF. Khi cần tìm entry **có ít nhất một** số điện thoại, dùng presence filter:

```text
(telephoneNumber=*)
```

Hai filter trên khác nhau: filter equality tìm một giá trị phù hợp; presence filter chỉ yêu cầu attribute tồn tại.

Ví dụ xây truy vấn bằng Spring LDAP, với giá trị do người dùng nhập:

```java
import java.util.List;
import javax.naming.directory.SearchControls;

import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;

public class PhoneSearch {
    private final LdapTemplate ldapTemplate;

    public PhoneSearch(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<String> findCommonNamesByPhone(String phone) {
        LdapQuery query = LdapQueryBuilder.query()
                .base("ou=people")
                .searchScope(SearchControls.SUBTREE_SCOPE)
                .where("telephoneNumber").is(phone);

        return ldapTemplate.search(query,
                (AttributesMapper<String>) attrs ->
                        (String) attrs.get("cn").get());
    }
}
```

Không ghép trực tiếp đầu vào người dùng vào chuỗi filter LDAP: ký tự `*`, dấu ngoặc và dấu gạch chéo ngược có ý nghĩa đặc biệt. Hãy dùng builder hoặc cơ chế escape/parameter binding phù hợp với phiên bản Spring LDAP đang sử dụng.

Ngoài ra, **tìm thấy cùng một số điện thoại ở nhiều entry** không tự động là lỗi LDAP: việc attribute cho phép nhiều giá trị ở mỗi entry khác với việc một giá trị phải **duy nhất trên toàn thư mục**. Nếu nghiệp vụ yêu cầu uniqueness xuyên các entry, phải kiểm tra khả năng/ràng buộc của máy chủ và thiết kế kiểm soát đồng thời.

## 10. Xử lý lỗi và lựa chọn dữ liệu an toàn

Một số lỗi thường gặp khi thao tác attribute:

| Tình huống | Nguyên nhân có thể xảy ra | Cách xử lý |
| --- | --- | --- |
| Thêm giá trị thứ hai cho attribute đơn trị | Vi phạm `SINGLE-VALUE`. | Dùng replace khi mục tiêu là đổi giá trị; xác minh schema. |
| Thêm lại giá trị đã có | Máy chủ phát hiện giá trị trùng theo matching rule. | Kiểm tra trạng thái; xử lý lỗi dữ liệu trùng đúng nghiệp vụ. |
| Xóa giá trị cuối cùng của attribute `MUST` | Entry không còn đáp ứng object class. | Giữ giá trị bắt buộc hoặc đổi schema/mô hình theo quy định. |
| Ghi attribute không được phép | Attribute không thuộc `MUST`/`MAY` áp dụng hoặc bị ràng buộc thêm. | Kiểm tra object class và schema máy chủ. |
| Ghi attribute có quyền đọc nhưng không có quyền sửa | ACL không cho phép cập nhật. | Dùng tài khoản dịch vụ với quyền tối thiểu đủ cho chức năng. |
| Chỉ thấy một giá trị dù LDAP lưu nhiều | Ứng dụng gọi getter đơn trị hoặc DTO chỉ có `String`. | Sử dụng getter đa trị, collection và duyệt hết các giá trị. |
| Giá trị hiển thị sai hoặc lỗi cast | Attribute có syntax nhị phân/đặc biệt. | Đọc đúng kiểu, converter và quy tắc mã hóa. |
| Mất thành viên nhóm sau cập nhật | Dùng replace toàn bộ `member` để thêm một thành viên. | Dùng add/remove theo giá trị cụ thể hoặc merge có kiểm soát. |

Các LDAP result code liên quan có thể gồm `19` (*constraint violation*), `20` (*attributeOrValueExists*), `16` (*noSuchAttribute*), `17` (*undefinedAttributeType*), `50` (*insufficientAccessRights*) và `65` (*objectClassViolation*). Mã cụ thể phụ thuộc loại thao tác, schema và máy chủ; Spring LDAP có thể ánh xạ chúng sang các exception tương ứng. Nên ghi log loại lỗi và ngữ cảnh kỹ thuật ở mức đủ dùng mà không ghi thông tin bí mật hoặc dữ liệu nhạy cảm.

### An toàn và tính toàn vẹn dữ liệu

1. **Chỉ đọc các attribute cần thiết:** kết quả tìm kiếm không nên tự động đưa mọi thuộc tính của người dùng, đặc biệt là thông tin bảo mật, ra API công khai.
2. **Dùng kết nối được bảo vệ:** LDAPS hoặc StartTLS cần xác minh chứng chỉ đúng cách. Tránh truyền thông tin xác thực và dữ liệu cá nhân qua kết nối không được bảo vệ.
3. **Tách quyền đọc và ghi:** dịch vụ chỉ tra cứu có thể sử dụng tài khoản bind chỉ đọc. Quyền sửa `member` hoặc hồ sơ nên được cấp cho chức năng cần thiết.
4. **Cân nhắc cập nhật đồng thời:** hai tiến trình đọc cùng tập giá trị rồi mỗi tiến trình replace có thể làm mất cập nhật của nhau. Thao tác add/remove mục tiêu thường thích hợp hơn; nếu phải replace, hãy thiết kế kiểm soát xung đột theo khả năng của máy chủ.
5. **Không suy đoán từ môi trường khác:** schema tiêu chuẩn, biến thể Active Directory, custom attribute và chính sách triển khai có thể khác nhau. Hãy xác minh cấu hình LDAP đích trước khi giả định attribute nào là đơn trị.

Một số máy chủ công bố thông tin schema qua `subschemaSubentry` hoặc giao diện quản trị; truy xuất schema có thể cần quyền thích hợp. Nếu không thấy định nghĩa, nên hỏi người quản trị directory hoặc tham khảo cấu hình/schema của chính máy chủ đó thay vì tự chọn cardinality.

## 11. Bài tập thực hành

Thực hành với một máy chủ LDAP thử nghiệm có schema phù hợp, dữ liệu được phép sửa và hai tài khoản bind: một chỉ đọc, một có quyền cập nhật trên OU mẫu. Sử dụng kết nối TLS được cấu hình đúng. Không thử ghi lên thư mục người dùng thật nếu chưa có quyền và quy trình phê duyệt của tổ chức.

### Bài tập 1 — Đọc và xác định cardinality

Cho entry:

```ldif
dn: uid=an,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: an
cn: Tran Van An
sn: Tran
employeeNumber: E-2020
telephoneNumber: +84 24 3000 1000
telephoneNumber: +84 28 3000 2000
mail: an@example.org
```

Hãy trả lời:

1. Attribute nào **đang có** nhiều giá trị?
2. Từ dữ liệu trên có thể kết luận `mail` là `SINGLE-VALUE` không?
3. Nếu bỏ hết `sn` thì entry có thể vi phạm điều kiện nào?
4. Muốn đổi `employeeNumber`, nên dùng add hay replace?

### Bài tập 2 — Thêm và xóa một giá trị

Dùng `LdapTemplate` và `ModificationItem` để:

1. Thêm `telephoneNumber: +84 236 3000 3000` cho `uid=an`.
2. Đọc lại và xác nhận ba số điện thoại vẫn tồn tại.
3. Xóa **chỉ** `telephoneNumber: +84 24 3000 1000`.
4. Đọc lại; kiểm tra hai số còn lại không bị mất.

Đặt câu hỏi: nếu dùng `REPLACE_ATTRIBUTE` với **một số mới** ở bước 1, điều gì sẽ xảy ra?

### Bài tập 3 — Thử constraint của schema

Trên dữ liệu được phép thử:

1. Tạo entry có một `employeeNumber` hợp lệ.
2. Thử thêm giá trị `employeeNumber` thứ hai bằng `ADD_ATTRIBUTE`.
3. Ghi nhận loại lỗi thực tế và giải thích vì sao máy chủ từ chối.
4. Dùng `REPLACE_ATTRIBUTE` để đổi `employeeNumber`, xác minh chỉ còn giá trị mới.

### Bài tập 4 — Thành viên nhóm

Giả sử `cn=developers` là nhóm `groupOfNames` với hai giá trị `member`. Viết pseudo-code hoặc Java để thêm một thành viên thứ ba mà không làm mất hai thành viên cũ. Xác định điều gì có thể xảy ra khi xóa cả hai giá trị `member` cuối cùng.

### Đáp án gợi ý

1. **Bài 1:** `objectClass` và `telephoneNumber` đang có nhiều giá trị. Không thể suy ra `mail` đơn trị từ một entry chỉ có một email. `sn` là attribute bắt buộc trong `person` thông dụng nên xóa hết có thể vi phạm `MUST`. Đổi `employeeNumber` dùng **replace**.
2. **Bài 2:** Dùng `ADD_ATTRIBUTE` với giá trị mới, sau đó `REMOVE_ATTRIBUTE` với chính giá trị cần bỏ. Nếu replace chỉ với số mới, các số cũ có thể bị thay mất.
3. **Bài 3:** Thêm giá trị thứ hai vào attribute có `SINGLE-VALUE` vi phạm schema; cách đổi là replace. Mã lỗi chính xác có thể phụ thuộc server.
4. **Bài 4:** Dùng `ADD_ATTRIBUTE` cho `member` với DN thành viên mới. Xóa toàn bộ giá trị của `member` trong `groupOfNames` có thể vi phạm thuộc tính bắt buộc.

## 12. Ghi nhớ và tự kiểm tra

- **Đơn trị/đa trị là ràng buộc của attribute type trong schema.** Một attribute đang có một giá trị không chứng minh nó được khai báo `SINGLE-VALUE`.
- **`MUST`/`MAY` và `SINGLE-VALUE` độc lập:** một quy định về sự có mặt của attribute; quy định còn lại về số giá trị tối đa.
- **Attribute đa trị không có thứ tự được bảo đảm.** Khi đọc, hãy lấy đủ các giá trị và chọn cấu trúc Java phù hợp.
- **Thao tác cập nhật phải khớp ý định:** `ADD_ATTRIBUTE` thêm, `REPLACE_ATTRIBUTE` thay tập, `REMOVE_ATTRIBUTE` xóa giá trị hoặc attribute theo cách dùng.
- **Spring LDAP không bỏ qua schema:** dùng `LdapTemplate`, `LdapClient` hay ODM vẫn chịu validation và ACL của directory server.
- **An toàn dữ liệu phụ thuộc cả cách sửa lẫn quyền hạn:** đặc biệt với `member`, `telephoneNumber` và những thuộc tính đồng bộ từ nhiều nguồn.

**Câu hỏi tự đánh giá cuối bài:** Nếu API nhận một số điện thoại mới để bổ sung cho người dùng, tại sao gọi `setAttributeValues("telephoneNumber", new String[]{phone})` rồi lưu có thể nguy hiểm hơn một thao tác `ADD_ATTRIBUTE` trên đúng giá trị? Hãy giải thích bằng ảnh hưởng lên các số điện thoại đã có và tình huống hai yêu cầu cập nhật đồng thời.

**Tài liệu tham khảo để tra cứu thêm:** RFC 4512 (*LDAP Directory Information Models*), RFC 4517 (*LDAP Syntaxes and Matching Rules*), RFC 4519 (*Schema for User Applications*), RFC 2798 (*inetOrgPerson*) và tài liệu API Spring LDAP cho `LdapTemplate`, `DirContextOperations`, `AttributesMapper` cùng JNDI `ModificationItem`.
