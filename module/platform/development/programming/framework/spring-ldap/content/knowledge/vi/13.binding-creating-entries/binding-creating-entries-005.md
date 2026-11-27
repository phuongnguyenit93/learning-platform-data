# Bind entry con sau khi tạo container trong Spring LDAP

Khi một ứng dụng tạo tài khoản LDAP ở DN `uid=an,ou=engineering,ou=people,dc=example,dc=org`, việc chuẩn bị đầy đủ thuộc tính của tài khoản vẫn chưa đủ. Entry cha `ou=engineering,ou=people,dc=example,dc=org` phải tồn tại, và bản thân entry cha đó cũng cần một đường dẫn hợp lệ lên đến gốc đang được quản lý. Vì vậy, nếu xây dựng cây thư mục mới, thứ tự đúng là **tạo container trước, rồi mới tạo entry con**.

Bài học thuộc chương **Bind và tạo entry** của **SPRING_LDAP**. Ta sẽ tạo một nhánh tổ chức bằng object class `organizationalUnit`, sau đó thêm tài khoản `inetOrgPerson` bằng `LdapTemplate.bind(...)`; đồng thời phân tích cách dựng DN, ràng buộc schema, khác biệt giữa bind tạo entry và bind xác thực, xử lý lỗi khi thêm từng cấp, kiểm thử và cách tránh tạo cây dữ liệu dở dang. Kiến thức này sử dụng trực tiếp những nền tảng về DN, schema, filter, `ContextSource` và thao tác LDAP qua Spring.

## 1. Container và entry con trong cây LDAP

Trong LDAP, **container** là cách gọi một entry có thể chứa các entry con theo cấu trúc *Directory Information Tree* (DIT). Nó không phải thư mục hệ điều hành. Nhiều hệ thống sử dụng object class `organizationalUnit` cho những nhánh có RDN là `ou=...`; những hệ thống khác có thể dùng `organization`, `domain`, `container` hoặc lớp do nhà cung cấp quy định.

Giả sử máy chủ đã có entry gốc `dc=example,dc=org`. Ứng dụng cần thêm nhánh `ou=people`, bên trong là `ou=engineering`, rồi tạo người dùng An:

~~~text
dc=example,dc=org                      [gốc đã tồn tại]
└── ou=people                          [container cấp 1: tạo trước]
    └── ou=engineering                 [container cấp 2: tạo tiếp]
        └── uid=an                     [entry con: tạo cuối]
~~~

Các DN đầy đủ và quan hệ cha–con:

| Entry | DN đầy đủ | Parent DN |
|---|---|---|
| Gốc | `dc=example,dc=org` | Phụ thuộc cấu trúc directory hiện có |
| Container people | `ou=people,dc=example,dc=org` | `dc=example,dc=org` |
| Container engineering | `ou=engineering,ou=people,dc=example,dc=org` | `ou=people,dc=example,dc=org` |
| Người dùng An | `uid=an,ou=engineering,ou=people,dc=example,dc=org` | `ou=engineering,ou=people,dc=example,dc=org` |

DN biểu diễn một chuỗi RDN từ entry hiện tại đến gốc. **RDN mới được thêm ở bên trái DN cha**: `uid=an` là tên tương đối của An trong `ou=engineering`.

Thứ tự tạo hợp lệ:

~~~mermaid
flowchart TD
    A["dc=example,dc=org đã tồn tại"] --> B["Add ou=people"]
    B --> C["Add ou=engineering,ou=people"]
    C --> D["Add uid=an,ou=engineering,ou=people"]
    D --> E["Lookup hoặc search để kiểm tra"]
    B -. "Nếu thất bại" .-> X["Dừng, phân loại lỗi"]
    C -. "Nếu thất bại" .-> X
    D -. "Nếu thất bại" .-> X
~~~

Mỗi bước **Add** tạo một entry LDAP độc lập. Server không bắt buộc tự tạo các cấp cha còn thiếu khi nhận yêu cầu tạo con.

## 2. Từ “bind” ở đây có nghĩa gì?

Từ **bind** dễ gây nhầm trong LDAP và JNDI vì nó được dùng ở hai ngữ cảnh khác nhau.

| Thuật ngữ/API | Ý nghĩa | Thường dùng khi nào |
|---|---|---|
| **LDAP Bind request** | Xác thực hoặc thiết lập danh tính của kết nối LDAP | Kiểm tra tài khoản, thiết lập quyền để thực hiện thao tác |
| **LDAP Add request** | Thêm một entry mới vào DIT | Tạo container, tài khoản, nhóm |
| **`LdapTemplate.bind(dn, null, attrs)`** | API Spring LDAP tạo entry với các attribute được cung cấp | Thêm container hoặc entry con |
| **`DirContext.createSubcontext(dn, attrs)`** | API JNDI tạo subcontext/entry | Thêm entry bằng JNDI trực tiếp |
| **`ContextSource.getContext(principal, credentials)`** | Lấy context theo thông tin xác thực | Thao tác dưới danh tính chỉ định |

Ở bài này, **“bind entry con” là đặt entry mới vào cây thông qua phương thức tạo entry của Spring LDAP**, không phải đăng nhập bằng mật khẩu của entry đó.

Để tạo entry, ứng dụng đã phải có một `ContextSource` cấu hình được kết nối và xác thực bằng tài khoản có quyền thêm entry ở vị trí đích. Việc thêm một entry chứa `uid` và `cn` không đồng nghĩa tài khoản đó đã có mật khẩu, được phép đăng nhập hay đã vượt qua bước xác thực người dùng.

## 3. Điều kiện cần trước khi tạo entry con

Cần kiểm tra ít nhất bốn nhóm điều kiện:

1. **DN cha tồn tại**: entry gốc và mọi container trung gian phải đã có trong DIT.
2. **Schema hợp lệ**: mỗi entry có `objectClass` phù hợp, chứa các attribute bắt buộc, có RDN và giá trị đúng định nghĩa schema.
3. **Quyền ghi**: tài khoản được dùng bởi `ContextSource` đủ quyền thêm entry dưới parent tương ứng; quyền có thể khác nhau ở từng nhánh.
4. **DN đích chưa bị chiếm**: không thể dùng LDAP Add để ghi đè entry có cùng DN; cần quyết định cách xử lý khi entry đã tồn tại.

Ví dụ entry `organizationalUnit` thường cần attribute `ou`. Với tài khoản `inetOrgPerson` kế thừa `person`, các attribute `cn` và `sn` là bắt buộc theo schema chuẩn; trong trường hợp chọn RDN `uid=an`, entry cũng phải có giá trị `uid: an` tương ứng. Những attribute khác như `mail` có thể là tùy chọn.

**Thứ tự tạo không thay thế kiểm tra schema và ACL.** Parent đã tồn tại nhưng object class của con không hợp lệ thì Add vẫn thất bại; ngược lại schema hợp lệ mà cha không tồn tại cũng không thêm được entry.

### LDIF minh họa

Giả sử `dc=example,dc=org` đã tồn tại và máy chủ hỗ trợ các object class tiêu chuẩn:

~~~ldif
dn: ou=people,dc=example,dc=org
objectClass: top
objectClass: organizationalUnit
ou: people
description: People accounts

dn: ou=engineering,ou=people,dc=example,dc=org
objectClass: top
objectClass: organizationalUnit
ou: engineering
description: Engineering team

dn: uid=an,ou=engineering,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: an
cn: Nguyen Van An
sn: Nguyen
givenName: Van An
mail: an@example.org
~~~

Trong tài liệu LDIF, các entry được ngăn bằng dòng trống. Khi nạp lần đầu, nên giữ đúng thứ tự từ parent đến child như trên. Công cụ nhập LDIF và server có thể có cơ chế xử lý riêng, nhưng **không nên phụ thuộc vào việc chúng tự sắp xếp hoặc tự tạo parent**.

## 4. Chuẩn bị ContextSource và hiểu base DN

Ví dụ Spring LDAP giả định ứng dụng đã cấu hình:

~~~text
LDAP URL:          ldaps://ldap.example.org:636
ContextSource base: dc=example,dc=org
Bind account:      tài khoản dịch vụ có quyền thêm trong ou=people
~~~

Đây là **cấu hình minh họa**: URL, truststore, thông tin bind và ACL thực tế phụ thuộc môi trường. Với `ContextSource` có base `dc=example,dc=org`, tên được truyền vào `LdapTemplate` thường là **DN tương đối với base**:

| Đối tượng cần tạo | DN truyền cho LdapTemplate |
|---|---|
| `ou=people,dc=example,dc=org` | `ou=people` |
| `ou=engineering,ou=people,dc=example,dc=org` | `ou=engineering,ou=people` |
| `uid=an,ou=engineering,ou=people,dc=example,dc=org` | `uid=an,ou=engineering,ou=people` |

Không thêm `dc=example,dc=org` lần nữa khi `ContextSource` đã đặt base tương ứng. Nếu vô tình truyền DN đầy đủ trong API đang mong DN tương đối, phép tra cứu hoặc thao tác có thể trỏ đến đường dẫn sai.

**Nhớ phân biệt:** URL chọn server LDAP; base DN xác định phần DIT mà API sẽ coi là gốc tương đối; còn DN của container hoặc người dùng xác định vị trí entry cần thêm.

## 5. Tạo container cấp đầu bằng LdapTemplate

Với Spring LDAP, có thể dùng phương thức:

~~~java
ldapTemplate.bind(relativeDn, null, attributes);
~~~

Trong đó `relativeDn` là DN entry cần tạo, `attributes` chứa schema và giá trị, còn đối số thứ hai được đặt `null` khi sử dụng dạng tạo entry bằng `Attributes`.

Một phương thức tạo container `organizationalUnit` có thể viết như sau:

~~~java
import javax.naming.Name;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.BasicAttributes;

import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

public final class OrganizationalUnits {
    private final LdapTemplate ldapTemplate;

    public OrganizationalUnits(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public void createPeopleContainer() {
        Name peopleDn = LdapNameBuilder.newInstance()
                .add("ou", "people")
                .build();

        Attributes attrs = new BasicAttributes(true);

        Attribute classes = new BasicAttribute("objectClass");
        classes.add("top");
        classes.add("organizationalUnit");
        attrs.put(classes);

        attrs.put("ou", "people");
        attrs.put("description", "People accounts");

        ldapTemplate.bind(peopleDn, null, attrs);
    }
}
~~~

Giải thích từng thành phần:

- `LdapNameBuilder` tạo DN từ các RDN; tránh tự nối chuỗi DN nếu giá trị có dấu phẩy, dấu cộng, dấu bằng hoặc ký tự đặc biệt.
- `new BasicAttributes(true)` xây tập attribute mà **tên attribute** được tra cứu không phân biệt hoa/chữ thường trong đối tượng Java; điều này không quyết định matching rule của LDAP server.
- `objectClass: top` và `objectClass: organizationalUnit` khai báo kiểu entry.
- `ou: people` đáp ứng attribute cần thiết của `organizationalUnit` và tương ứng RDN `ou=people`.
- `ldapTemplate.bind(...)` gửi thao tác tạo entry. Với lời gọi template thông thường, Spring LDAP lấy và trả JNDI context, nên repository không phải tự đóng `DirContext`.

Chỉ khi **server trả thành công**, bước tiếp theo mới nên tạo container con. Không coi việc xây được đối tượng Java `Attributes` là bằng chứng LDAP đã lưu entry.

## 6. Tạo container lồng nhau và bind entry người dùng

Sau khi `ou=people` đã tồn tại, ta có thể thêm `ou=engineering,ou=people`; sau đó mới thêm `uid=an`. Một ví dụ tự chứa cho cả ba bước:

~~~java
import javax.naming.Name;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.BasicAttributes;

import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

public final class DirectoryProvisioner {
    private final LdapTemplate ldapTemplate;

    public DirectoryProvisioner(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public void createEngineeringTree() {
        // DN tương đối với ContextSource base = dc=example,dc=org.
        Name peopleDn = LdapNameBuilder.newInstance()
                .add("ou", "people")
                .build();

        Name engineeringDn = LdapNameBuilder.newInstance()
                .add("ou", "people")
                .add("ou", "engineering")
                .build();

        Name personDn = LdapNameBuilder.newInstance()
                .add("ou", "people")
                .add("ou", "engineering")
                .add("uid", "an")
                .build();

        // 1) Tạo container cha gần base trước.
        ldapTemplate.bind(
                peopleDn, null, organizationalUnit("people"));

        // 2) Tạo container con dưới people.
        ldapTemplate.bind(
                engineeringDn, null, organizationalUnit("engineering"));

        // 3) Tạo entry người dùng dưới engineering.
        ldapTemplate.bind(
                personDn, null,
                person("an", "Nguyen Van An", "Nguyen", "an@example.org"));
    }

    private static Attributes organizationalUnit(String name) {
        Attributes attrs = new BasicAttributes(true);

        Attribute classes = new BasicAttribute("objectClass");
        classes.add("top");
        classes.add("organizationalUnit");
        attrs.put(classes);

        attrs.put("ou", name);
        return attrs;
    }

    private static Attributes person(
            String uid, String cn, String sn, String mail) {

        Attributes attrs = new BasicAttributes(true);

        Attribute classes = new BasicAttribute("objectClass");
        classes.add("top");
        classes.add("person");
        classes.add("organizationalPerson");
        classes.add("inetOrgPerson");
        attrs.put(classes);

        attrs.put("uid", uid);
        attrs.put("cn", cn);
        attrs.put("sn", sn);
        attrs.put("mail", mail);
        return attrs;
    }
}
~~~

**Điều kiện chạy:** chỉ dùng minh họa này cho một cây mới, nơi `ou=people` và `ou=engineering` chưa tồn tại. Nếu chạy lại sau một lần tạo thành công, lời gọi tạo container đầu tiên sẽ thất bại do DN đã tồn tại. Đừng đưa trực tiếp phương thức này vào một endpoint có thể bị gọi lặp mà chưa bổ sung chính sách idempotency.

### Tại sao gọi `add("ou", "people")` trước `add("uid", "an")`?

Trong đoạn code, thứ tự gọi builder đi từ **parent đến child**. Kết quả DN có dạng:

~~~text
uid=an,ou=engineering,ou=people
~~~

Đây là cách thư viện dựng chuỗi RDN có thứ tự đúng. Không tự đảo lại bằng phép nối chuỗi. Đặc biệt với tên người hoặc OU có dấu phẩy hay khoảng trắng đầu/cuối, giá trị phải được xử lý như **giá trị RDN**, không phải một đoạn cú pháp DN viết tay.

### Nếu cần thêm nhiều người vào cùng container

Container cần tạo **một lần**. Sau đó có thể tạo nhiều entry con:

~~~text
ou=engineering,ou=people,dc=example,dc=org
├── uid=an
├── uid=binh
└── uid=linh
~~~

Mỗi tài khoản có DN khác nhau vì RDN `uid` khác nhau trong cùng parent. Không lặp lại thao tác `bind` cho container đã tồn tại ở mỗi lần tạo người dùng. Một phương thức repository tạo người dùng nên giả định parent đã được hệ thống provisioning chuẩn bị, hoặc kiểm tra/thực hiện bước tạo parent theo một chính sách được chỉ định rõ.

## 7. Quan hệ giữa DN, RDN và attribute khi tạo con

Tại mỗi cấp:

~~~text
RDN của container people:       ou=people
RDN của container engineering:  ou=engineering
RDN của entry người dùng An:    uid=an
~~~

Tên tương đối dùng để xác định entry dưới parent tương ứng. Khi xây dựng attribute, cần để ý:

| Entry | Object class chính | Attribute schema quan trọng | Attribute khớp RDN |
|---|---|---|---|
| `ou=people` | `organizationalUnit` | `ou` | `ou: people` |
| `ou=engineering,ou=people` | `organizationalUnit` | `ou` | `ou: engineering` |
| `uid=an,ou=engineering,ou=people` | `inetOrgPerson` và các class cha | `cn`, `sn`; những thuộc tính khác tùy schema | `uid: an` |

Việc đặt RDN `uid=an` không biến `uid` thành duy nhất trên toàn directory. Có thể tồn tại `uid=an,ou=sales,ou=people,dc=example,dc=org` cùng lúc với `uid=an,ou=engineering,ou=people,dc=example,dc=org` vì DN đầy đủ khác nhau. Nếu nghiệp vụ yêu cầu UID duy nhất trong toàn hệ thống, cần thêm chính sách kiểm tra và ràng buộc tương ứng; LDAP schema không mặc định bảo đảm tính duy nhất toàn cây cho mọi attribute.

Ngược lại, hai entry **cùng parent và cùng RDN** không thể cùng tồn tại vì DN sẽ trùng.

### Container có cần objectClass đặc biệt để chứa con không?

Trong LDAP, khả năng có con phụ thuộc mô hình DIT, schema và quy tắc DIT/ACL mà máy chủ sử dụng. Dùng `organizationalUnit` là mô hình phổ biến cho OU, nhưng không nên hiểu “có class `organizationalUnit`” là điều kiện đủ để mọi LDAP server đều cho phép tạo bất kỳ loại entry con nào dưới đó.

Một số server có **DIT structure rules**, naming context và chính sách tạo entry dưới parent cụ thể. Do đó, khi có lỗi tạo entry con dù parent tồn tại, hãy kiểm tra cả object class, schema, naming policy và quyền trên parent.

## 8. Tìm kiếm và xác minh sau khi tạo

Sau mỗi bước, có thể dùng lookup hoặc search để xác minh trạng thái:

- Sau khi tạo `ou=people`: lookup DN đó, kiểm tra `objectClass` và `ou`.
- Sau khi tạo `ou=engineering`: lookup DN mới, xác nhận parent của nó là `ou=people`.
- Sau khi tạo người dùng: lookup `uid=an,ou=engineering,ou=people`, kiểm tra `uid`, `cn` và `sn`.
- Nếu cần liệt kê các tài khoản con trực tiếp, tìm dưới base `ou=engineering,ou=people` với scope `ONELEVEL` và filter phù hợp.

Ví dụ đơn giản để đọc lại tên từ DN người dùng:

~~~java
import javax.naming.Name;

import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

public final class PersonVerification {
    private final LdapTemplate ldapTemplate;

    public PersonVerification(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public String readCommonName(String uid) {
        Name relativeDn = LdapNameBuilder.newInstance()
                .add("ou", "people")
                .add("ou", "engineering")
                .add("uid", uid)
                .build();

        return ldapTemplate.lookup(
                relativeDn,
                (AttributesMapper<String>) attrs ->
                        (String) attrs.get("cn").get());
    }
}
~~~

Ví dụ giả định caller có quyền đọc `cn`. Nếu entry vừa tạo không thấy khi dùng một kết nối khác, cần xem search base, replication delay hoặc ACL; **không tự động kết luận tạo thất bại** chỉ vì kết quả search rỗng.

Tương tự, lookup thành công chỉ chứng minh có một entry ở DN đó mà tài khoản hiện tại đọc được. Khi kiểm tra khả năng xử lý retry, nên so sánh thêm object class và các thuộc tính định danh hoặc ID hệ thống (nếu server cung cấp) để bảo đảm đúng đối tượng.

## 9. Lỗi phổ biến khi tạo con trước khi có cha

Xét trường hợp gọi:

~~~java
// Chưa tạo ou=people và ou=engineering.
ldapTemplate.bind(
        personDn, null,
        person("an", "Nguyen Van An", "Nguyen", "an@example.org"));
~~~

Máy chủ thường từ chối vì DN cha chưa tồn tại; kết quả LDAP có thể là **`noSuchObject` (32)**. Spring LDAP chuyển lỗi của server/JNDI thành exception phù hợp, tên exception cụ thể tùy phiên bản và cơ chế ánh xạ.

| Mã kết quả LDAP | Tên | Khi tạo container/entry con cần kiểm tra |
|---|---|---|
| **0** | `success` | Entry được chấp nhận; có thể sang bước tiếp theo |
| **32** | `noSuchObject` | Parent DN hoặc một cấp đường dẫn không tồn tại; đôi khi ACL che dữ liệu |
| **34** | `invalidDNSyntax` | DN/RDN sai cú pháp, chẳng hạn tự nối ký tự đặc biệt không escape |
| **50** | `insufficientAccessRights` | Tài khoản bind không có quyền thêm entry dưới parent |
| **53** | `unwillingToPerform` | Server từ chối theo chính sách hoặc hạn chế sản phẩm |
| **64** | `namingViolation` | Quy tắc đặt tên hoặc vị trí entry không phù hợp |
| **65** | `objectClassViolation` | Thiếu attribute MUST, object class không hợp lệ hoặc attribute không được phép |
| **68** | `entryAlreadyExists` | DN đích đã có entry; không thể Add ghi đè |
| **21** | `invalidAttributeSyntax` | Giá trị thuộc tính sai cú pháp schema |
| **19** | `constraintViolation` | Vi phạm ràng buộc khác, ví dụ chính sách giá trị/uniqueness |

**Không nên phân loại mọi lỗi thêm entry thành “container chưa tồn tại”.** Nếu parent đã có nhưng người gọi thiếu quyền, kết quả xử lý cần khác với việc tạo bù parent. Nếu object class sai, retry không sửa dữ liệu sẽ chỉ lặp lại lỗi.

### Cách chẩn đoán có thứ tự

1. Đọc lại **DN tương đối và base DN** thực tế.
2. Xác nhận **parent DN đầy đủ** bằng lookup phù hợp quyền hiện có.
3. Kiểm tra schema: object class, MUST, MAY, syntax và RDN.
4. Kiểm tra ACL tài khoản được dùng để tạo entry.
5. Kiểm tra DN đích có đã tồn tại không.
6. Nếu lỗi xảy ra giữa chuỗi nhiều Add, kiểm tra cấp nào đã tạo trước khi chạy lại.

Ví dụ server báo `objectClassViolation` khi tạo `inetOrgPerson` có `cn` nhưng thiếu `sn`; tạo thêm parent không giúp sửa lỗi này.

## 10. Tạo lại an toàn: idempotency và xử lý chạy đồng thời

Trong thực tế, việc tạo container có thể diễn ra lúc khởi tạo môi trường, khi mở phòng ban mới hoặc do một tác vụ tự động. Cùng một lệnh có thể bị gọi lại sau timeout hoặc chạy song song từ nhiều instance ứng dụng.

### Không coi “đã tồn tại” luôn là thành công

Nếu `ou=people` đã tồn tại, cần xác minh đó là **container đúng loại, đúng phạm vi và thuộc đơn vị mà ứng dụng được phép dùng**, thay vì bỏ qua mọi lỗi `entryAlreadyExists`.

Ví dụ một tình huống nguy hiểm:

- Ứng dụng dự định tạo `ou=engineering,ou=people`.
- Một tiến trình khác đã tạo entry cùng DN với object class hoặc mục đích không tương thích.
- Ứng dụng bắt lỗi “đã tồn tại” rồi tiếp tục tạo người dùng dưới entry đó.

Kết quả có thể vi phạm chính sách quản lý dữ liệu. Với workflow idempotent, chỉ coi trạng thái đã tồn tại là hợp lệ khi entry **đúng loại và nội dung tối thiểu như mong đợi**.

### Vì sao kiểm tra tồn tại trước rồi Add vẫn có thể lỗi?

Hai luồng có thể cùng thấy container chưa tồn tại, rồi cùng gọi Add:

~~~text
Request A: lookup ou=people -> chưa tồn tại
Request B: lookup ou=people -> chưa tồn tại
Request A: add ou=people -> thành công
Request B: add ou=people -> entryAlreadyExists
~~~

Đây là *race condition* thông thường. Không giải quyết chỉ bằng cách thêm một lệnh lookup trước Add. Cần xử lý lỗi khi tạo trùng, đọc lại entry để kiểm tra tính tương thích và chỉ tiếp tục khi trạng thái đúng như mong đợi.

Một quy trình provisioning lặp lại có thể tổ chức:

~~~text
ensureContainer(dn, expectedClass, expectedOu):
    thử tạo entry tại dn
    nếu thành công:
        return CREATED

    nếu entryAlreadyExists:
        đọc entry hiện có và kiểm tra class + ou + ownership
        nếu hợp lệ: return REUSED
        nếu khác mong đợi: báo xung đột và dừng

    các lỗi khác:
        báo lỗi và dừng

ensureContainer(ou=people)
ensureContainer(ou=engineering,ou=people)
createUser(uid=an,ou=engineering,ou=people)
~~~

Đây là **giả mã thiết kế**. Tên exception, quyền lookup, thay đổi đồng thời và cách kiểm tra ownership phụ thuộc ứng dụng và LDAP server. Với entry người dùng, việc Add gặp trùng thường cần báo xung đột nghiệp vụ; không tự ghi đè mật khẩu hoặc thuộc tính tài khoản.

## 11. Chuỗi nhiều thao tác Add có phải một transaction không?

**Không mặc định.** Ba lần gọi `ldapTemplate.bind(...)` trong ví dụ là ba thao tác riêng. Nếu hai container tạo thành công nhưng tạo người dùng thất bại, kết quả có thể là:

~~~text
dc=example,dc=org
└── ou=people                   [đã tạo]
    └── ou=engineering          [đã tạo]
        └── (chưa có uid=an)    [tạo người dùng thất bại]
~~~

LDAP Add thông thường không tạo một giao dịch nhiều thao tác có khả năng rollback toàn bộ. Vì vậy cần xác định chính sách khi có lỗi:

| Cách xử lý | Khi phù hợp | Điều cần chú ý |
|---|---|---|
| **Giữ container đã tạo** | Container là hạ tầng lâu dài và còn phục vụ tài khoản khác | Ghi nhận trạng thái “user create failed”, retry sau |
| **Dọn container mới tạo** | Container chỉ phục vụ một tác vụ dùng tạm | Chỉ xóa entry do tác vụ sở hữu, bảo đảm không có con mới |
| **Provisioning theo đợt có đối soát** | Tạo nhiều phòng ban/người dùng | Ghi log các DN đã tạo, tiếp tục/retry có kiểm soát |
| **Cơ chế transaction riêng của server** | Khi sản phẩm hỗ trợ và nghiệp vụ thực sự yêu cầu | Cần xác minh tài liệu và giới hạn; không phải hành vi mặc định của LDAP |

**Đừng rollback bằng cách xóa nguyên nhánh chỉ vì bước tạo người dùng cuối thất bại.** Container có thể đã tồn tại từ trước hoặc vừa có tài khoản khác được thêm vào. Xóa nhầm parent có thể gây mất dữ liệu nghiêm trọng. Nếu cleanup, chỉ xử lý những DN thực sự do workflow này tạo, sau khi xác minh trạng thái và quan hệ con.

Một cách thiết kế dễ theo dõi là tách hai nghiệp vụ: **khởi tạo cấu trúc OU** (quản trị) và **tạo tài khoản trong OU đã được chuẩn bị** (nghiệp vụ), mỗi nghiệp vụ có quyền và audit riêng.

## 12. So sánh LdapTemplate và JNDI trực tiếp khi tạo entry

Spring LDAP được xây trên JNDI. Tạo entry thông qua `LdapTemplate.bind(...)` thường gọn hơn vì framework quản lý context và chuyển đổi nhiều loại exception từ JNDI. Khi cần thao tác ở mức JNDI, có thể dùng `DirContext.createSubcontext(...)`.

Ví dụ JNDI tạo container `ou=engineering` sau khi `ou=people` tồn tại:

~~~java
import javax.naming.Name;
import javax.naming.NamingException;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.BasicAttributes;
import javax.naming.directory.DirContext;

import org.springframework.ldap.core.ContextSource;
import org.springframework.ldap.support.LdapNameBuilder;
import org.springframework.ldap.support.LdapUtils;

public final class RawJndiContainerCreate {
    public static void createEngineering(ContextSource contextSource)
            throws NamingException {

        Name dn = LdapNameBuilder.newInstance()
                .add("ou", "people")
                .add("ou", "engineering")
                .build();

        Attributes attrs = new BasicAttributes(true);

        Attribute classes = new BasicAttribute("objectClass");
        classes.add("top");
        classes.add("organizationalUnit");
        attrs.put(classes);
        attrs.put("ou", "engineering");

        DirContext context = null;
        DirContext created = null;

        try {
            context = contextSource.getReadWriteContext();
            created = context.createSubcontext(dn, attrs);
        } finally {
            // Nếu tạo thành công, JNDI có thể trả về context của entry mới.
            LdapUtils.closeContext(created);
            LdapUtils.closeContext(context);
        }
    }
}
~~~

Khác biệt trách nhiệm:

- **`LdapTemplate.bind`**: Spring LDAP sở hữu context của lời gọi và quản lý vòng đời tài nguyên.
- **JNDI trực tiếp**: code đã lấy context từ `ContextSource` phải đóng/trả context; nếu thao tác trả thêm context cho entry vừa tạo, cũng giải phóng khi không dùng nữa.
- Cả hai đường đi đều tuân thủ schema, ACL, DN và các quy tắc của server; chọn API khác không thể tự khắc phục parent DN chưa tồn tại.

Không chia sẻ một `DirContext` giữa nhiều luồng hoặc giữ nó trong singleton để sử dụng lâu dài. Nếu bật pooling, đóng context thường là thao tác trả tài nguyên về pool.

## 13. Bảo mật khi tạo container và entry con

Việc cung cấp quyền tạo nhánh LDAP cho ứng dụng cần ranh giới rõ ràng:

- **Giới hạn vị trí tạo**: không nhận DN hoặc parent tùy ý từ HTTP rồi cho phép tạo bên dưới mọi nhánh. Nên sử dụng allowlist những OU nghiệp vụ được phép.
- **Giới hạn quyền bind account**: tài khoản dịch vụ chỉ nên được cấp quyền Add/Read cần thiết dưới nhánh provisioning; tránh dùng tài khoản admin toàn directory cho nghiệp vụ đơn giản.
- **Dựng DN theo thành phần**: dùng `LdapNameBuilder` hoặc `LdapName` và validate UID/OU theo chính sách nghiệp vụ; không tin chuỗi DN tự nhập, cũng không nối chuỗi với ký tự đặc biệt.
- **Bảo vệ đường truyền**: dùng LDAPS hoặc StartTLS khi thích hợp, xác minh chứng chỉ và hostname; đặc biệt quan trọng nếu tạo tài khoản kèm dữ liệu nhạy cảm.
- **Quản lý credential**: không hardcode mật khẩu bind vào mã hoặc LDIF dùng chung; lưu trong kho bí mật và tránh ghi ra log.
- **Tối thiểu hóa attribute**: chỉ gửi những attribute thật sự được schema và nghiệp vụ yêu cầu; không tự giả định mọi server cho phép `userPassword` hay có cùng chính sách mật khẩu.
- **Ghi audit**: ghi nhận ai yêu cầu, container/user DN đã tạo, thời điểm và kết quả; cân nhắc dữ liệu cá nhân trong DN khi lưu log.

Một lỗi thiết kế là để API nhận trực tiếp:

~~~text
POST /directory/create
parentDn = "dc=example,dc=org"
childRdn = "ou=super-admins"
~~~

Dù DN được escape đúng, quyền nghiệp vụ vẫn cần từ chối nếu caller không được tạo nhánh đó. **Escape ngăn sai cú pháp/injection, nhưng không thay thế authorization**.

### Xác thực người dùng sau khi tạo là nghiệp vụ riêng

Việc Add thành công không có nghĩa tài khoản có thể bind để đăng nhập. Còn tùy chính sách mật khẩu, tài khoản khóa/vô hiệu hóa, quyền xác thực, trạng thái đồng bộ và cấu hình LDAP server. Không suy luận rằng có entry `inetOrgPerson` thì đã có credential hợp lệ.

Trong ứng dụng Spring LDAP, xác thực thường dùng các API chuyên dụng như `LdapTemplate.authenticate(...)` hoặc quy trình authentication của Spring Security; đây là bước khác với `LdapTemplate.bind(dn, null, attrs)`.

## 14. Kiểm thử từ container đến entry con

Nên kiểm thử trên môi trường LDAP cô lập có schema và ACL tương tự production. Những ca quan trọng:

| Ca kiểm thử | Thao tác | Kết quả kỳ vọng |
|---|---|---|
| **Tạo đúng thứ tự** | Add `ou=people` → `ou=engineering` → `uid=an` | Cả ba entry tồn tại ở DN tương ứng |
| **Con trước cha** | Add `uid=an` khi `ou=engineering` chưa tồn tại | Thất bại, thường do `noSuchObject` |
| **Chạy lại** | Gọi tạo container đã tồn tại | Nhận lỗi trùng hoặc kiểm tra và reuse theo chính sách |
| **Sai schema container** | Thiếu `ou` hoặc `objectClass` không phù hợp | Server từ chối |
| **Sai schema người dùng** | Thiếu `sn` của class `person` | Server từ chối |
| **Sai DN** | Nối tay DN có ký tự đặc biệt không escape | Lỗi cú pháp hoặc trỏ sai entry |
| **Thiếu quyền** | Dùng bind account chỉ đọc để Add | Thất bại do ACL |
| **Lỗi giữa các bước** | Hai container tạo xong, user Add thất bại | Container không bị xóa ngoài ý muốn |
| **Cạnh tranh tạo parent** | Hai instance cùng tạo `ou=people` | Một tạo thành công; instance kia xử lý trùng có kiểm tra |
| **Kiểm tra sau tạo** | Lookup parent và user bằng DN tương đối đúng base | Đọc được entry phù hợp |

**Không chạy test tạo/xóa trên dữ liệu thật.** Dùng một nhánh test tách biệt, ví dụ `ou=test-provisioning,dc=example,dc=org`, và chuẩn bị parent test phù hợp với chính sách của môi trường.

### Bài thực hành: tạo đội vận hành

Cho cây gốc đã tồn tại:

~~~text
dc=example,dc=org
└── ou=teams
~~~

Hãy tạo container `ou=operations,ou=teams,dc=example,dc=org`, rồi người dùng `uid=mai,ou=operations,ou=teams,dc=example,dc=org`.

Yêu cầu:

1. Viết thứ tự thao tác và DN tương đối nếu `ContextSource` có base `dc=example,dc=org`.
2. Chọn object class và attribute tối thiểu để tạo OU, tài khoản.
3. Viết lệnh `LdapTemplate.bind(...)` bằng DN builder và Attributes.
4. Mô tả lỗi nếu thêm `uid=mai` trước khi tạo `ou=operations`.
5. Nếu chạy lại sau khi thành công, cần xử lý thế nào khi container đã tồn tại?
6. Làm sao xác minh không tạo nhầm entry ở `ou=teams` hoặc một OU khác?

**Gợi ý giải:**

- DN container: `ou=operations,ou=teams`; DN người dùng: `uid=mai,ou=operations,ou=teams`. Tạo container trước rồi user.
- Container dùng `top` + `organizationalUnit`, attribute `ou: operations`. Người dùng dùng chuỗi `top` + `person` + `organizationalPerson` + `inetOrgPerson`, với `cn` và `sn` bắt buộc; `uid: mai` tương ứng RDN.
- Đoạn mã minh họa (giả sử đã có hàm `organizationalUnit(...)` và `person(...)` của mục 6):

~~~java
Name operationsDn = LdapNameBuilder.newInstance()
        .add("ou", "teams")
        .add("ou", "operations")
        .build();

Name maiDn = LdapNameBuilder.newInstance()
        .add("ou", "teams")
        .add("ou", "operations")
        .add("uid", "mai")
        .build();

ldapTemplate.bind(
        operationsDn, null, organizationalUnit("operations"));

ldapTemplate.bind(
        maiDn, null, person("mai", "Tran Mai", "Tran", "mai@example.org"));
~~~

- Nếu parent chưa tồn tại, Add user có thể bị từ chối với `noSuchObject (32)`.
- Khi chạy lại, phân biệt DN đã tồn tại đúng loại container với xung đột dữ liệu; không bỏ qua tất cả lỗi.
- Lookup đúng DN đầy đủ/tương đối, kiểm tra `objectClass`, `ou` hoặc `uid` và xem cấu trúc cây với search scope phù hợp.

## 15. Những hiểu nhầm thường gặp

| Hiểu nhầm | Cách hiểu đúng |
|---|---|
| “Thêm entry con sẽ tự tạo các OU trên đường đi.” | LDAP Add thông thường yêu cầu parent DN đã tồn tại. |
| “`LdapTemplate.bind` là dùng username/password để đăng nhập.” | Ở overload tạo entry, đây là thao tác thêm entry; xác thực LDAP Bind là khái niệm khác. |
| “Có `uid` và `cn` là đủ tạo mọi tài khoản.” | Cần object class hợp lệ, attribute MUST như `sn` và đúng quy tắc RDN/schema. |
| “`organizationalUnit` luôn được phép chứa mọi class.” | DIT policy, naming rules, ACL và cấu hình server có thể giới hạn. |
| “Có thể Add lại container mỗi lần tạo user.” | DN trùng gây lỗi; cần tạo container một lần hoặc thiết kế ensure idempotent. |
| “Kiểm tra tồn tại trước Add là không thể gặp trùng.” | Vẫn có race condition giữa lookup và Add. |
| “Bước thứ ba lỗi thì hai container trước cũng tự rollback.” | Các thao tác Add độc lập, không mặc định là một transaction. |
| “DN được escape đúng là có thể tạo ở bất kỳ nhánh nào.” | Vẫn phải kiểm soát quyền nghiệp vụ và ACL LDAP. |

## Tài liệu tham khảo

- [RFC 4511 — LDAP: The Protocol](https://www.rfc-editor.org/rfc/rfc4511): thao tác Add và LDAP Bind cùng các kết quả lỗi giao thức.
- [RFC 4512 — LDAP: Directory Information Models](https://www.rfc-editor.org/rfc/rfc4512): entry, DIT, DN, object class và schema.
- [RFC 4514 — LDAP: String Representation of Distinguished Names](https://www.rfc-editor.org/rfc/rfc4514): cách biểu diễn và escape DN.
- [RFC 4519 — LDAP: Schema for User Applications](https://www.rfc-editor.org/rfc/rfc4519): các object class `organizationalUnit`, `person` và attribute liên quan.
- [Spring LDAP Reference](https://docs.spring.io/spring-ldap/reference/): `ContextSource`, `LdapTemplate`, thao tác tạo entry.
- [Spring LDAP API — LdapTemplate](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/core/LdapTemplate.html): các overload `bind(...)` và `lookup(...)`.
- [Java JNDI DirContext](https://docs.oracle.com/en/java/javase/17/docs/api/java.naming/javax/naming/directory/DirContext.html): `createSubcontext(...)` và thao tác thư mục qua JNDI.

## Ghi nhớ

Để **bind entry con sau khi tạo container**, hãy đi từ gốc đã tồn tại đến từng cấp cha rồi mới tạo entry lá: **parent trước, child sau**. Mỗi entry cần DN chính xác, `objectClass` hợp lệ và attribute phù hợp schema; trong Spring LDAP, có thể dùng `LdapNameBuilder` cùng `LdapTemplate.bind(relativeDn, null, attrs)`. Cần hiểu “bind tạo entry” khác “LDAP Bind xác thực”, đồng thời xử lý DN trùng, quyền, race condition và lỗi giữa nhiều lần Add. Kiểm tra lại entry sau mỗi bước và quản lý vòng đời provisioning một cách rõ ràng giúp ứng dụng tổ chức dữ liệu thư mục ổn định, nhất quán và an toàn.
