# Schema violation khi thêm hoặc sửa entry trong Spring LDAP

## 1. Khi LDAP từ chối ghi dữ liệu dù kết nối đã thành công

Giả sử ứng dụng Spring LDAP đã kết nối thành công qua TLS, tài khoản dịch vụ có quyền ghi và một lệnh tìm kiếm người dùng trả về kết quả bình thường. Tuy nhiên, khi gọi `LdapTemplate.bind(...)` để tạo tài khoản hoặc `LdapTemplate.modifyAttributes(...)` để cập nhật thông tin, máy chủ trả lỗi:

```text
LDAP: error code 65 - Object Class Violation
```

Đây là một lỗi liên quan đến **schema**: cấu trúc hoặc giá trị của entry sau thao tác không đáp ứng một hay nhiều quy tắc mà máy chủ thư mục áp dụng. LDAP không hoạt động như một kho dữ liệu cho phép ghi tùy ý mọi thuộc tính. Dữ liệu phải tuân theo lớp đối tượng (`objectClass`), định nghĩa thuộc tính (`attributeType`), cú pháp, các ràng buộc về số lượng giá trị và quy tắc đặt tên.

Chủ đề này nằm trong phần **Attribute và schema** của Spring LDAP. Mục tiêu là đọc được thông báo lỗi, tìm chính xác điều kiện bị vi phạm và sửa thao tác tạo/cập nhật entry một cách có kiểm soát bằng `LdapTemplate`, `LdapClient` hoặc Object-Directory Mapping (ODM). Đồng thời cần phân biệt lỗi schema với lỗi DN, filter, xác thực, TLS, kết nối và phân quyền: chúng có thể xuất hiện ở cùng một luồng nghiệp vụ nhưng cần cách xử lý khác nhau.

Sau bài học, người học có thể:

- Phân biệt các quy tắc `MUST`, `MAY`, `SINGLE-VALUE`, syntax, `objectClass` và quy tắc đặt tên.
- Chẩn đoán một số mã kết quả LDAP thường gặp khi thêm hoặc sửa entry.
- Tạo một entry hợp lệ, cố ý tạo lỗi schema, sau đó xác minh cách khắc phục.
- Thiết kế kiểm tra dữ liệu tại ứng dụng mà vẫn coi schema của máy chủ là nguồn quyết định cuối cùng.

## 2. Schema LDAP quy định điều gì?

### 2.1. `objectClass` và thuộc tính bắt buộc, được phép

Mỗi entry có một hoặc nhiều giá trị `objectClass` để xác định loại đối tượng và tập thuộc tính được phép sử dụng. Các object class có thể kế thừa nhau; ví dụ, lớp `inetOrgPerson` thường có chuỗi kế thừa:

```text
top (ABSTRACT)
  └── person (STRUCTURAL)
        └── organizationalPerson (STRUCTURAL)
              └── inetOrgPerson (STRUCTURAL)
```

Ở một schema tiêu chuẩn có hỗ trợ `inetOrgPerson`, `person` yêu cầu thuộc tính `cn` và `sn`. Các lớp con kế thừa những yêu cầu này, đồng thời có thể cho phép thêm `uid`, `mail` và nhiều thuộc tính khác.

| Thành phần schema | Ý nghĩa | Ví dụ thực tế |
| --- | --- | --- |
| `MUST` | Thuộc tính bắt buộc phải có theo object class | `cn` và `sn` với `person` và các lớp con |
| `MAY` | Thuộc tính được phép có nhưng không bắt buộc | `mail`, `uid` trong `inetOrgPerson` |
| `SUP` | Quan hệ kế thừa object class hoặc attribute type | `inetOrgPerson` kế thừa `organizationalPerson` |
| `STRUCTURAL` | Lớp mô tả loại entry chính và cấu trúc kế thừa của nó | `person`, `organizationalPerson`, `inetOrgPerson` |
| `AUXILIARY` | Lớp bổ sung thuộc tính cho entry nếu được phép | Một số schema mở rộng dùng auxiliary class riêng |
| `ABSTRACT` | Lớp nền dùng trong quan hệ kế thừa, không dùng độc lập làm lớp cấu trúc entry | `top` |
| `SINGLE-VALUE` | Thuộc tính chỉ nhận tối đa một giá trị | Tùy định nghĩa của từng attribute type |
| `SYNTAX` | Kiểu/cú pháp giá trị và cách mã hóa hợp lệ | Chuỗi, số nguyên, DN, dữ liệu nhị phân, v.v. |
| Matching rules | Cách so sánh, chuẩn hóa, tìm kiếm giá trị | So khớp không phân biệt hoa thường cho một số thuộc tính |

Các thuộc tính hợp lệ là hợp của những thuộc tính được cho phép bởi các object class đang áp dụng, kể cả thuộc tính kế thừa. Một attribute type **được định nghĩa trong schema của máy chủ** chưa có nghĩa nó **được phép xuất hiện ở mọi entry**.

Để phân biệt:

- `mail` có thể là một thuộc tính được định nghĩa và được `inetOrgPerson` cho phép.
- `customBadgeId` chưa được khai báo trong schema sẽ thường bị từ chối vì máy chủ không biết loại thuộc tính đó.
- Một thuộc tính đã được khai báo nhưng không được bất kỳ object class phù hợp nào của entry cho phép cũng có thể bị từ chối, dù tên và giá trị của nó được viết đúng.

### 2.2. Schema kiểm tra cả **trạng thái entry sau thao tác**

Khi tạo entry, máy chủ đánh giá dữ liệu được đề nghị thêm mới. Khi sửa entry, máy chủ đánh giá trạng thái của entry sau các thay đổi. Ví dụ, một entry ban đầu có đủ `cn`, `sn`, `uid` và `objectClass` có thể đang hợp lệ; nhưng nếu lệnh cập nhật **xóa hết giá trị `sn`**, entry sẽ không còn đáp ứng ràng buộc `MUST` của lớp `person`.

Điều này giải thích vì sao một lệnh `modifyAttributes(...)` tưởng chỉ tác động một thuộc tính vẫn có thể thất bại vì vi phạm schema của toàn entry.

### 2.3. Schema và DN có mối liên hệ nhưng không đồng nhất

Một DN như `uid=alice,ou=people,dc=example,dc=org` có RDN `uid=alice`. Máy chủ còn kiểm tra quy tắc đặt tên và giá trị thuộc tính tham gia RDN. Nếu cố xóa `uid` đang làm RDN hoặc đổi DN theo cách không được máy chủ hỗ trợ, lỗi có thể thuộc nhóm **naming violation** hay **not allowed on RDN** thay vì lỗi object class thông thường.

Vì thế, khi điều tra lỗi phải xem đồng thời:

1. Entry đang mang DN nào và RDN chứa thuộc tính gì?
2. Entry khai báo những `objectClass` nào?
3. Thao tác thay đổi chính xác các thuộc tính/giá trị nào?
4. Trạng thái entry cuối cùng có đáp ứng schema và quy tắc naming không?

## 3. Ví dụ: entry người dùng hợp lệ và entry vi phạm schema

Giả sử máy chủ hỗ trợ schema `inetOrgPerson` chuẩn, nhánh `ou=people,dc=example,dc=org` đã tồn tại và tài khoản bind có quyền thêm entry.

Một entry hợp lệ ở dạng LDIF:

```ldif
dn: uid=alice,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
cn: Alice Nguyen
sn: Nguyen
uid: alice
mail: alice@example.org
```

Một phiên bản **không hợp lệ** vì thiếu thuộc tính bắt buộc `sn`:

```ldif
dn: uid=bob,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
cn: Bob Tran
uid: bob
# Thiếu sn — person yêu cầu cn và sn
```

Khi thêm entry thứ hai, máy chủ thường trả mã **65 / `objectClassViolation`**. Thông báo đi kèm có thể nêu tên `sn`, tên object class, hoặc chỉ ghi “object class violation”. Văn bản chẩn đoán phụ thuộc máy chủ; không nên viết xử lý nghiệp vụ bằng cách so khớp từng câu tiếng Anh của thông báo.

Một tình huống khác: entry đã có đầy đủ thuộc tính bắt buộc nhưng ứng dụng thêm một thuộc tính mới `customBadgeId`. Nếu thuộc tính này chưa được định nghĩa trong schema, máy chủ có thể trả **17 / `undefinedAttributeType`**. Nếu thuộc tính đã được định nghĩa nhưng không được các object class của entry cho phép, kết quả có thể là **65 / `objectClassViolation`**. Cùng một hành động “thêm một trường” nhưng nguyên nhân và cách sửa khác nhau.

## 4. Các mã lỗi LDAP dễ nhầm với schema violation

| Mã LDAP | Tên kết quả | Ý nghĩa thường gặp |
| --- | --- | --- |
| **65** | `objectClassViolation` | Thiếu `MUST`, dùng thuộc tính không được lớp cho phép, hoặc cấu trúc object class không hợp lệ |
| **21** | `invalidAttributeSyntax` | Giá trị không đúng cú pháp của attribute type được định nghĩa |
| **17** | `undefinedAttributeType` | Tên attribute type không được schema máy chủ biết đến |
| **19** | `constraintViolation` | Vi phạm ràng buộc giá trị, tính đơn trị hoặc quy tắc bổ sung của máy chủ |
| **69** | `objectClassModsProhibited` | Một thay đổi object class bị cấm, thường liên quan structural class |
| **64** | `namingViolation` | DN/RDN vi phạm quy tắc đặt tên của máy chủ |
| **67** | `notAllowedOnRDN` | Cố sửa/xóa giá trị tham gia RDN theo cách không được phép |
| **68** | `entryAlreadyExists` | DN đích đã tồn tại; đây là xung đột tên, không phải thiếu `MUST` |
| **50** | `insufficientAccessRights` | Tài khoản bind không có quyền thực hiện thao tác |
| **32** | `noSuchObject` | DN được tham chiếu không tồn tại hoặc không truy cập được theo cách máy chủ phản hồi |
| **53** | `unwillingToPerform` | Máy chủ từ chối thao tác theo chính sách hoặc hạn chế triển khai |

Đây là tên các **result code** của LDAP. Không phải mọi máy chủ đều trả cùng mã trong mọi trường hợp, và LDAP server có thể kèm chẩn đoán mở rộng riêng. Spring LDAP chuyển đổi ngoại lệ JNDI theo cơ chế của thư viện; vì vậy khi cần chẩn đoán, hãy lưu đủ mã lỗi và thông tin ngữ cảnh ở phía máy chủ hoặc log bảo vệ phù hợp. Đừng đồng nhất mọi `NamingException` với lỗi schema.

Ví dụ, việc không thêm được entry có thể do `ou=people` chưa tồn tại (liên quan `noSuchObject`), ACL thiếu quyền thêm (`insufficientAccessRights`) hoặc chứng chỉ TLS không hợp lệ (lỗi kết nối). Sửa schema sẽ không giải quyết được những vấn đề đó.

## 5. Tạo entry bằng `LdapTemplate.bind(...)`

### 5.1. Cấu hình kết nối để thao tác ghi an toàn

Spring LDAP sử dụng `ContextSource` để tạo và quản lý các context truy cập thư mục. Dưới đây là cấu hình ứng dụng minh họa; tài khoản bind và mật khẩu được cung cấp qua biến môi trường:

```java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.core.support.LdapContextSource;

@Configuration
class DirectoryConfiguration {
    @Bean
    LdapContextSource ldapContextSource(
            @Value("${app.ldap.url}") String url,
            @Value("${app.ldap.base}") String base,
            @Value("${app.ldap.bind-dn}") String bindDn,
            @Value("${app.ldap.bind-password}") String password) {
        LdapContextSource source = new LdapContextSource();
        source.setUrl(url);
        source.setBase(base);
        source.setUserDn(bindDn);
        source.setPassword(password);
        return source;
    }

    @Bean
    LdapTemplate ldapTemplate(LdapContextSource ldapContextSource) {
        return new LdapTemplate(ldapContextSource);
    }
}
```

```yaml
# application.yml
app:
  ldap:
    url: ${LDAP_URL:ldaps://ldap.example.org:636}
    base: dc=example,dc=org
    bind-dn: ${LDAP_BIND_DN}
    bind-password: ${LDAP_BIND_PASSWORD}
```

Trong ví dụ, `ContextSource` có base `dc=example,dc=org`. DN truyền vào `LdapTemplate` được tạo tương đối với base này: `uid=alice,ou=people`. Endpoint `ldaps://` giả định kết nối TLS đã được cấu hình xác minh chứng chỉ và hostname đúng với máy chủ; không vô hiệu hóa kiểm tra TLS để thử thao tác ghi.

### 5.2. Tạo entry với `objectClass` và thuộc tính đúng schema

```java
import javax.naming.Name;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.BasicAttributes;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;
import org.springframework.stereotype.Repository;

@Repository
class PersonDirectoryRepository {
    private final LdapTemplate ldapTemplate;

    PersonDirectoryRepository(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    void createPerson(String uid, String commonName, String surname) {
        Name dn = LdapNameBuilder.newInstance("ou=people")
                .add("uid", uid)
                .build();

        Attributes attributes = new BasicAttributes(true);
        Attribute classes = new BasicAttribute("objectClass");
        classes.add("top");
        classes.add("person");
        classes.add("organizationalPerson");
        classes.add("inetOrgPerson");
        attributes.put(classes);

        attributes.put("uid", uid);
        attributes.put("cn", commonName);
        attributes.put("sn", surname);

        ldapTemplate.bind(dn, null, attributes);
    }
}
```

Trong một directory có schema và quyền tương ứng, gọi `createPerson("alice", "Alice Nguyen", "Nguyen")` sẽ tạo entry tại `uid=alice,ou=people,dc=example,dc=org`. Việc thêm các object class kế thừa ở ví dụ giúp người học thấy rõ chuỗi kế thừa; cách máy chủ tự bổ sung/hiển thị object class có thể khác nhau tùy triển khai.

Các chi tiết đáng chú ý:

- `LdapNameBuilder` tạo DN đúng cú pháp. Nó không kiểm tra `uid` đã tồn tại hay chính sách username của ứng dụng.
- `BasicAttributes(true)` tạo tập thuộc tính xử lý tên thuộc tính không phân biệt hoa thường theo API JNDI.
- `objectClass` có nhiều giá trị; `cn` và `sn` là bắt buộc do lớp `person` trong chuỗi kế thừa.
- `bind(...)` gửi thao tác tạo entry. Nếu schema/ACL không cho phép, máy chủ từ chối; template không sửa dữ liệu tự động cho hợp lệ.

Khi ứng dụng nhận dữ liệu từ HTTP/API, cần kiểm tra giá trị đầu vào: `uid` không rỗng, `commonName` và `surname` có nội dung và độ dài được phép, tránh dữ liệu vượt giới hạn. **Kiểm tra tại ứng dụng hỗ trợ thông báo dễ hiểu; schema máy chủ vẫn là nơi quyết định entry hợp lệ.**

### 5.3. Cố ý gây lỗi để thấy vai trò của `MUST`

Nếu bỏ dòng `attributes.put("sn", surname);` khỏi đoạn tạo entry, entry không có `sn` sẽ thường bị từ chối bằng `objectClassViolation` (LDAP 65). Giải pháp đúng là cung cấp `sn` hợp lệ theo dữ liệu nghiệp vụ, hoặc thay đổi mô hình entry và schema theo thiết kế đã được quản trị cho phép. Không nên “chữa lỗi” bằng cách gửi một giá trị giả như `N/A` vào dữ liệu định danh thật chỉ để qua kiểm tra.

Trong thực tế, server có thể còn kiểm tra thêm nội dung RDN, độ dài thuộc tính, ACL, object class hỗ trợ hoặc chính sách riêng. Lỗi đầu tiên được máy chủ báo chưa chắc là lỗi duy nhất của dữ liệu.

## 6. Sửa entry bằng `modifyAttributes(...)` và những lỗi thường gặp

### 6.1. Cập nhật thuộc tính được phép

Giả sử entry người dùng đã tồn tại với `objectClass: inetOrgPerson`, ta có thể cập nhật email nếu schema và ACL cho phép:

```java
import javax.naming.Name;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;
import org.springframework.ldap.support.LdapNameBuilder;

Name dn = LdapNameBuilder.newInstance("ou=people")
        .add("uid", "alice")
        .build();

ModificationItem[] update = {
    new ModificationItem(
        DirContext.REPLACE_ATTRIBUTE,
        new BasicAttribute("mail", "alice.new@example.org")
    )
};

ldapTemplate.modifyAttributes(dn, update);
```

Đoạn mã giả định đang nằm trong lớp có biến `ldapTemplate` từ ví dụ cấu hình trước. `REPLACE_ATTRIBUTE` thay tập giá trị của thuộc tính `mail` bằng tập được cung cấp, do đó cần cẩn thận với thuộc tính **đa trị**: thay một giá trị có thể vô tình xóa những giá trị khác. Nếu nghiệp vụ chỉ thêm hoặc bỏ một giá trị, hãy xem xét `ADD_ATTRIBUTE` hoặc `REMOVE_ATTRIBUTE` cùng điều kiện schema phù hợp.

### 6.2. Xóa thuộc tính bắt buộc

Lệnh dưới đây cố xóa toàn bộ thuộc tính `sn` khỏi entry có object class `person` hoặc lớp con:

```java
ModificationItem[] invalidUpdate = {
    new ModificationItem(
        DirContext.REMOVE_ATTRIBUTE,
        new BasicAttribute("sn")
    )
};

ldapTemplate.modifyAttributes(dn, invalidUpdate);
```

Nếu entry đang yêu cầu `sn`, máy chủ sẽ từ chối vì trạng thái sau thao tác thiếu thuộc tính `MUST`, thường là LDAP 65. Cần dùng `REPLACE_ATTRIBUTE` với một họ hợp lệ nếu mục tiêu là đổi họ, không dùng `REMOVE_ATTRIBUTE` để xóa thuộc tính bắt buộc.

### 6.3. Thêm object class nhưng quên thuộc tính bắt buộc

Một ứng dụng có thể muốn mở rộng entry hiện có bằng object class bổ sung. Nếu object class mới yêu cầu thuộc tính `MUST` mà entry chưa có, việc thêm riêng giá trị `objectClass` có thể thất bại. Cần nghiên cứu schema và cập nhật các thuộc tính cần thiết **cùng thao tác hợp lệ** (hoặc theo quy trình được máy chủ hỗ trợ), thay vì thử đi thử lại từng thuộc tính ngẫu nhiên.

Việc thay structural object class của entry còn có giới hạn nghiêm ngặt: máy chủ có thể trả `objectClassModsProhibited` (69) ngay cả khi tập thuộc tính mới trông hợp lệ. Không nên giả định `objectClass` là một mảng chuỗi tùy ý có thể sửa như `mail`.

### 6.4. Thuộc tính không cho phép hoặc kiểu giá trị không đúng

Các ví dụ dưới đây minh họa nhóm nguyên nhân; mã lỗi thực tế phụ thuộc schema và server:

| Dữ liệu gửi lên | Vi phạm dự kiến | Cách sửa phù hợp |
| --- | --- | --- |
| Thiếu `sn` với `person` | Thiếu thuộc tính `MUST` | Bổ sung `sn` có ý nghĩa |
| Gửi `customBadgeId` khi schema chưa khai báo | `undefinedAttributeType` | Dùng thuộc tính đã tồn tại hoặc phối hợp quản trị mở rộng schema |
| Gửi thuộc tính đã định nghĩa nhưng không có trong `MAY`/`MUST` của lớp đang áp dụng | `objectClassViolation` | Chọn đúng object class hoặc bỏ thuộc tính không hợp lệ |
| Gửi chữ cho thuộc tính có syntax số nguyên | `invalidAttributeSyntax` | Chuẩn hóa kiểu giá trị theo `attributeType` |
| Gửi nhiều giá trị cho thuộc tính `SINGLE-VALUE` | `constraintViolation` hoặc mã cụ thể của máy chủ | Chỉ gửi một giá trị hợp lệ |
| Xóa giá trị dùng làm RDN | Có thể gặp lỗi naming/RDN | Nếu cần đổi RDN, dùng thao tác Modify DN/`rename` phù hợp |

## 7. Quy trình chẩn đoán có hệ thống

Khi Spring LDAP trả lỗi lúc thêm hoặc sửa, hãy điều tra theo thứ tự sau:

### Bước 1 — Xác định thao tác và DN thực tế

Ghi lại loại thao tác (`add`/`modify`/`modifyDN`), DN đầy đủ dự kiến, `ContextSource` base, các thuộc tính được sửa và tên object class. Trong log sản xuất, không ghi mật khẩu, token, giá trị nhạy cảm hoặc toàn bộ entry nếu không cần thiết. DN cũng có thể chứa dữ liệu cá nhân, nên chỉ ghi phần tối thiểu cho phép.

Nếu template có base `dc=example,dc=org` mà code gửi `uid=alice,ou=people,dc=example,dc=org` như DN **tương đối**, có thể tạo truy vấn sai DN. Kiểm tra cách sử dụng DN tuyệt đối/tương đối trước khi kết luận schema bị lỗi.

### Bước 2 — Đọc mã kết quả, tách lỗi schema khỏi lỗi kết nối/quyền

Đặc biệt kiểm tra 65, 21, 17, 19 và 69; so sánh với 50, 32, 68 và lỗi giao tiếp/TLS. Đọc diagnostic message của máy chủ để lấy manh mối, nhưng không phụ thuộc hoàn toàn vào nội dung thông báo tự do của nhà cung cấp.

### Bước 3 — Kiểm tra `objectClass`, `MUST`, `MAY` và `SYNTAX`

Đọc entry hiện tại và schema có hiệu lực. Xem các object class có quan hệ kế thừa như thế nào, tất cả thuộc tính cần thiết có tồn tại không, kiểu giá trị và số lượng giá trị có hợp lệ không. Với hệ thống có overlay, plugin hoặc chính sách riêng, kiểm tra cả các ràng buộc ngoài schema chuẩn.

### Bước 4 — Tạo thay đổi tối thiểu và kiểm tra kết quả

Trên thư mục thử nghiệm, tạo entry hợp lệ trước rồi thay đúng một điều kiện gây lỗi. Khi sửa, so sánh thuộc tính trước/sau dự kiến. Sau khi lệnh thành công, đọc lại entry bằng `LdapTemplate.lookup(...)` hoặc `ldapsearch` để xác nhận dữ liệu thực tế thay vì chỉ tin việc không có ngoại lệ.

### Bước 5 — Ghi nhận nguyên nhân và phòng ngừa

Nếu yêu cầu nghiệp vụ không phù hợp schema, trao đổi với quản trị viên LDAP để thống nhất mô hình object class, attribute type và quá trình thay đổi schema. Nếu chỉ do mapper hay dữ liệu đầu vào, sửa validation và mã chuyển đổi. Không mở rộng schema hoặc vô hiệu hóa kiểm tra bảo mật chỉ để tránh một thông báo lỗi.

## 8. Xem schema thực tế với `ldapsearch`

Thư mục LDAP thường công bố thuộc tính `subschemaSubentry` trên Root DSE (DN rỗng) để cho biết vị trí entry chứa schema. Có thể bắt đầu bằng:

```bash
ldapsearch -LLL -x \
  -H "ldaps://ldap.example.org:636" \
  -b "" -s base \
  "(objectClass=*)" subschemaSubentry namingContexts
```

Ví dụ kết quả:

```ldif
dn:
subschemaSubentry: cn=Subschema
namingContexts: dc=example,dc=org
```

Sau đó đọc entry schema theo DN **thực sự** nhận được, chẳng hạn:

```bash
ldapsearch -LLL -x \
  -H "ldaps://ldap.example.org:636" \
  -b "cn=Subschema" -s base \
  "(objectClass=subschema)" objectClasses attributeTypes
```

Trong nhiều triển khai, các định nghĩa `objectClasses` và `attributeTypes` có thể rất dài. Hãy lọc hoặc phân tích bằng công cụ phù hợp để tìm `inetOrgPerson`, `person`, `cn`, `sn`, `uid`, `mail` và thuộc tính đang gặp lỗi. `subschemaSubentry` và quyền đọc schema có thể khác nhau theo sản phẩm LDAP. Nếu anonymous bind bị cấm, thêm `-D "<bind DN>" -W` với tài khoản được cấp quyền; giữ nguyên TLS và tránh cung cấp mật khẩu trực tiếp trên dòng lệnh.

Một định nghĩa schema LDAP dùng các từ khóa như sau (đây là **mẫu giải thích**, không phải định nghĩa OID có thể nhập trực tiếp vào máy chủ):

```text
objectClass: person
  SUP: top
  KIND: STRUCTURAL
  MUST: cn, sn
  MAY: userPassword, telephoneNumber, description, seeAlso

attributeType: một thuộc tính ví dụ
  SYNTAX: kiểu dữ liệu được chấp nhận
  SINGLE-VALUE: chỉ một giá trị nếu có cờ này
```

Ngoài Root DSE, có thể xem thuộc tính trên entry cụ thể bằng:

```bash
ldapsearch -LLL -x \
  -H "ldaps://ldap.example.org:636" \
  -D "cn=directory-reader,ou=system,dc=example,dc=org" -W \
  -b "uid=alice,ou=people,dc=example,dc=org" -s base \
  "(objectClass=*)" objectClass cn sn uid mail
```

Lệnh `ldapsearch` chỉ đọc dữ liệu; tài khoản đọc có thể khác tài khoản ghi. Nếu không nhìn thấy một thuộc tính, cần phân biệt nó không tồn tại với việc quyền đọc, thuộc tính vận hành hoặc chính sách máy chủ hạn chế hiển thị.

## 9. Xử lý schema violation trong ứng dụng Spring

### 9.1. Kiểm tra dữ liệu trước khi gọi LDAP

Ở tầng API/service, nên xác minh các trường bắt buộc theo use case, chuẩn hóa dữ liệu và ánh xạ sang các thuộc tính LDAP đã được xác nhận trong schema triển khai. Ví dụ:

```java
void registerPerson(String uid, String fullName, String surname) {
    if (uid == null || uid.isBlank()) {
        throw new IllegalArgumentException("uid is required");
    }
    if (fullName == null || fullName.isBlank()) {
        throw new IllegalArgumentException("cn is required");
    }
    if (surname == null || surname.isBlank()) {
        throw new IllegalArgumentException("sn is required");
    }

    personDirectoryRepository.createPerson(uid, fullName, surname);
}
```

Đây là validation cho use case mẫu dùng `person`/`inetOrgPerson`, không phải bộ mô phỏng toàn bộ LDAP schema. Không nên sao chép mọi chi tiết schema máy chủ vào ứng dụng vì hai nguồn có thể lệch nhau khi thay đổi cấu hình. Ứng dụng kiểm tra sớm những điều kiện rõ ràng; máy chủ tiếp tục kiểm tra các ràng buộc thực tế.

### 9.2. Xử lý ngoại lệ theo loại lỗi

`LdapTemplate` giúp chuyển đổi ngoại lệ từ JNDI sang hệ ngoại lệ của Spring LDAP, thường ở dạng unchecked. Khi thiết kế API, có thể ánh xạ lỗi dữ liệu không hợp schema thành phản hồi nghiệp vụ thích hợp, lỗi DN trùng thành xung đột, lỗi ACL thành từ chối thao tác và lỗi kết nối thành sự cố dịch vụ. Tên lớp ngoại lệ chính xác và thông tin chi tiết phụ thuộc phiên bản Spring LDAP, JNDI provider và kết quả từ server; nên kiểm tra bản thư viện thực tế khi triển khai handler.

Không trả nguyên văn diagnostic message của LDAP cho người dùng cuối nếu nó chứa DN nội bộ, cấu trúc OU hoặc dữ liệu nhạy cảm. Nhưng phía vận hành phải có đủ dấu vết an toàn để phân biệt nguyên nhân, chẳng hạn loại thao tác, mã LDAP, correlation ID và thông tin phiên bản schema.

### 9.3. Tương quan với `LdapClient` và ODM

`LdapClient` có thể cung cấp API fluent cho thao tác LDAP trên các phiên bản thư viện hỗ trợ; ODM ánh xạ thuộc tính entry vào lớp Java. Hai cách tiếp cận giúp quản lý mã nhưng **không miễn trừ yêu cầu schema**. Một lớp Java có trường `mail` hay annotation ánh xạ object class không chứng minh entry sẽ được server chấp nhận. Khi phát sinh schema violation, vẫn phải kiểm tra các giá trị LDAP gửi thực tế, chuỗi object class, schema của máy chủ và ACL.

## 10. Kiểm thử schema violation an toàn

Bộ kiểm thử tích hợp nên dùng thư mục LDAP thử nghiệm riêng, có schema gần với môi trường đích, dữ liệu giả và quyền kiểm soát rõ ràng. Có thể dùng tài khoản có quyền tạo/sửa trong OU thử nghiệm; tuyệt đối không tự cấp quyền cao cho tài khoản ứng dụng sản xuất để chạy test.

| Ca kiểm thử | Chuẩn bị | Kết quả mong đợi |
| --- | --- | --- |
| Add hợp lệ | `inetOrgPerson` có `cn`, `sn`, `uid` | Entry được tạo và có thể đọc lại |
| Add thiếu `sn` | Bỏ `sn` khỏi một entry `person` | Bị từ chối vì `MUST`; thường LDAP 65 |
| Add thuộc tính chưa định nghĩa | Dùng tên thuộc tính thử nghiệm không có trong schema | Bị từ chối; thường LDAP 17 |
| Modify xóa `sn` | Entry đang có đủ `cn`, `sn` | Bị từ chối; entry ban đầu vẫn hợp lệ |
| Modify giá trị sai syntax | Thuộc tính có syntax rõ ràng, gửi giá trị không hợp lệ | Bị từ chối theo syntax/constraint của server |
| Modify thuộc tính cho phép | Thay `mail` của entry có quyền ghi | Thành công, đọc lại giá trị mới |
| Add trùng DN | DN đã tồn tại | Lỗi trùng DN; không ghi đè entry cũ |
| Ghi với tài khoản chỉ đọc | Entry hợp lệ nhưng bind thiếu quyền | Lỗi ACL, không được hiểu là lỗi schema |

Với ca thất bại, không chỉ kiểm tra có ngoại lệ: hãy đọc lại entry để chứng minh dữ liệu **không bị sửa ngoài dự kiến**. Với ca thành công, kiểm tra cả `objectClass`, `cn`, `sn`, thuộc tính nghiệp vụ và DN. Nên tự tạo dữ liệu mỗi ca test, dọn dẹp sau test, tránh phụ thuộc vào entry có sẵn hoặc chạy đồng thời trên cùng DN.

### Bài thực hành

1. Dùng `ldapsearch` đọc Root DSE, lấy `subschemaSubentry` và xác nhận schema có `inetOrgPerson`, `cn`, `sn` và `uid`.
2. Dùng `LdapTemplate.bind(...)` tạo `uid=training-01` với đầy đủ `objectClass`, `cn`, `sn`, `uid`, sau đó `lookup(...)` để kiểm tra entry.
3. Cố tạo `uid=training-02` với cùng object class nhưng thiếu `sn`. Ghi lại mã LDAP và giải thích quy tắc `MUST` bị vi phạm.
4. Sửa `mail` của `training-01` bằng `REPLACE_ATTRIBUTE`, đọc lại để xác nhận; tiếp theo thử xóa `sn` và kiểm tra entry vẫn giữ giá trị cũ sau khi lệnh thất bại.
5. Thử thêm một thuộc tính chưa định nghĩa trong schema, đối chiếu mã lỗi với trường hợp thiếu `sn`.
6. Thực hiện một thao tác tương tự bằng tài khoản chỉ đọc để chứng minh `insufficientAccessRights` là một nhóm lỗi khác với vi phạm schema.
7. Ghi lại quy trình xử lý khi lỗi xảy ra trong ứng dụng: validation phía API, phân loại ngoại lệ Spring LDAP, kiểm tra trạng thái entry và log an toàn.

**Câu hỏi tự kiểm tra:** Vì sao một thuộc tính đã được đăng ký trong schema vẫn có thể không được phép ghi vào entry `inetOrgPerson`? Vì sao xóa `sn` có thể lỗi nhưng thay `sn` bằng giá trị khác lại hợp lệ? Vì sao `objectClassViolation` (65) khác `invalidAttributeSyntax` (21)? Khi một thao tác thất bại, dựa vào đâu để loại trừ lỗi ACL hoặc TLS trước khi sửa dữ liệu?

## 11. Ghi nhớ

**Schema violation** xuất hiện khi entry hoặc thay đổi được yêu cầu không đáp ứng quy tắc schema của dịch vụ LDAP. Với Spring LDAP, cần hiểu `objectClass`, `MUST`/`MAY`, syntax, tính đơn trị, RDN và các ràng buộc máy chủ; các API `LdapTemplate`, `LdapClient` và ODM chỉ hỗ trợ thao tác, không bỏ qua việc kiểm tra schema. Khi gặp lỗi, hãy xác định DN và thao tác thực tế, đọc mã kết quả LDAP, đối chiếu schema, sửa dữ liệu hoặc mô hình entry theo thiết kế và xác minh lại trên thư mục thử nghiệm. Kết hợp TLS, quyền tối thiểu, validation phù hợp và xử lý ngoại lệ chính xác giúp thao tác thêm/sửa entry an toàn, có thể kiểm chứng và dễ bảo trì.
