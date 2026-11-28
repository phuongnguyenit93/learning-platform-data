# Tạo entry bằng `bind` của `LdapTemplate`

Trong **Spring Data LDAP**, một entry là đối tượng dữ liệu nằm trong cây thư mục LDAP (*Directory Information Tree*, DIT). Để thêm người dùng, nhóm hoặc đơn vị tổ chức, ứng dụng phải xác định **Distinguished Name (DN)** của entry mới và cung cấp các thuộc tính phù hợp với schema LDAP. `LdapTemplate` của **Spring LDAP** cung cấp phương thức `bind(...)` để thực hiện thao tác tạo entry một cách trực tiếp; đây là cơ chế ghi dữ liệu nền tảng bên cạnh cách thao tác qua Spring Data LDAP repository.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt `LdapTemplate.bind(...)` để **tạo entry** với thao tác LDAP **Bind** để xác thực kết nối.
- Xác định DN của entry mới, DN của entry cha và quan hệ với `base` của `ContextSource`.
- Khai báo `objectClass`, các thuộc tính bắt buộc và xây dựng `Attributes` hợp lệ trước khi ghi.
- Dùng hai cách tạo entry: `LdapTemplate.bind(Name, Object, Attributes)` và `LdapTemplate.bind(DirContextOperations)`.
- Kiểm tra entry sau khi tạo, nhận diện các lỗi thường gặp và thiết kế kiểm thử ghi dữ liệu an toàn.

## 2. `bind` trong ngữ cảnh tạo dữ liệu có nghĩa gì?

Thuật ngữ **bind** xuất hiện trong LDAP ở hai ngữ cảnh dễ nhầm:

| Ngữ cảnh | Mục đích | Ví dụ |
| --- | --- | --- |
| LDAP **Bind operation** trên giao thức | Xác thực hoặc thiết lập danh tính cho phiên kết nối đến directory. | Kết nối bằng tài khoản dịch vụ có quyền ghi. |
| `LdapTemplate.bind(...)` trong Spring LDAP | Tạo và gắn một **entry mới** vào một DN trong directory; qua JNDI, thao tác này tương ứng với việc thêm entry LDAP. | Tạo `uid=alice,ou=people,dc=example,dc=com`. |

`LdapTemplate.bind(...)` **không phải** lời gọi để kiểm tra mật khẩu đăng nhập của người dùng. Nó tạo entry có tập thuộc tính đã truyền vào. Một kết nối vẫn phải được thiết lập và xác thực bởi `ContextSource` trước khi server cho phép ghi.

Một thao tác tạo entry gồm bốn thành phần:

1. **DN:** xác định vị trí duy nhất của entry trong cây LDAP.
2. **Parent entry:** nhánh cha của DN mới phải tồn tại, trừ khi chính thao tác đang tạo entry gốc phù hợp với directory.
3. **`objectClass`:** chỉ rõ các lớp schema mà entry tuân theo.
4. **Attributes:** chứa các giá trị yêu cầu bởi schema, RDN và ứng dụng.

Ví dụ, muốn thêm Alice dưới nhánh `ou=people`:

```text
dc=com
└── dc=example
    └── ou=people                (entry cha phải tồn tại)
        └── uid=alice            (entry mới)
```

DN đầy đủ sẽ là `uid=alice,ou=people,dc=example,dc=com`. RDN là `uid=alice`; không được tùy ý hoán đổi thứ tự của các thành phần DN.

## 3. Chuẩn bị directory và `LdapTemplate`

Giả sử directory có sẵn các entry `dc=example,dc=com` và `ou=people,dc=example,dc=com`. Ứng dụng Spring Boot sử dụng Spring LDAP/Spring Data LDAP, có bean `LdapTemplate` và một tài khoản được cấp quyền **thêm entry** dưới nhánh `ou=people`.

Ví dụ cấu hình cho môi trường học tập:

```yaml
spring:
  ldap:
    urls: ${LDAP_URL:ldap://127.0.0.1:1389}
    base: dc=example,dc=com
    username: ${LDAP_BIND_DN}
    password: ${LDAP_BIND_PASSWORD}
```

Các giá trị `LDAP_BIND_DN` và `LDAP_BIND_PASSWORD` là thông tin xác thực của **tài khoản dịch vụ**, không phải thuộc tính của entry đang tạo. URL trên chỉ là địa chỉ directory chạy trong môi trường thử nghiệm. Khi triển khai thực tế, cần dùng TLS (`ldaps://` hoặc StartTLS tùy cấu hình máy chủ), xác thực chứng chỉ và quản lý bí mật an toàn.

**Quy tắc quan trọng về base:** với `spring.ldap.base = dc=example,dc=com`, tên được truyền vào những phương thức LDAP thông thường của `LdapTemplate` là **DN tương đối với base**. Để tạo entry đầy đủ:

```text
uid=alice,ou=people,dc=example,dc=com
```

ta xây tên tương đối:

```text
uid=alice,ou=people
```

Không nối lại `dc=example,dc=com` vào tên tương đối rồi truyền cho `LdapTemplate` đã cấu hình base đó, vì có thể khiến đường dẫn bị lặp. Nếu ứng dụng không cấu hình base hoặc thiết lập `ContextSource` khác, phải xem lại tên mong đợi bởi API và môi trường thực tế.

## 4. Tạo entry bằng `bind(Name, Object, Attributes)`

Đây là cách thể hiện rõ hai đầu vào chính: **tên entry** và **tập thuộc tính**. Mã dưới đây tạo một người dùng theo schema `inetOrgPerson`.

```java
import javax.naming.Name;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.BasicAttributes;

import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;
import org.springframework.stereotype.Service;

@Service
public class PersonDirectoryWriter {

    private final LdapTemplate ldapTemplate;

    public PersonDirectoryWriter(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public Name createPerson(String uid, String fullName, String surname) {
        if (uid == null || uid.isBlank()
                || fullName == null || fullName.isBlank()
                || surname == null || surname.isBlank()) {
            throw new IllegalArgumentException(
                    "uid, fullName và surname không được rỗng");
        }

        // Tên tương đối với spring.ldap.base = dc=example,dc=com.
        Name relativeDn = LdapNameBuilder.newInstance()
                .add("ou", "people")
                .add("uid", uid)
                .build();

        // true: tên attribute ID không phân biệt chữ hoa/chữ thường.
        BasicAttributes attributes = new BasicAttributes(true);

        BasicAttribute objectClasses = new BasicAttribute("objectClass");
        objectClasses.add("top");
        objectClasses.add("person");
        objectClasses.add("organizationalPerson");
        objectClasses.add("inetOrgPerson");
        attributes.put(objectClasses);

        attributes.put("uid", uid);
        attributes.put("cn", fullName);
        attributes.put("sn", surname);

        // obj = null: chỉ ghi entry thư mục và các attributes.
        ldapTemplate.bind(relativeDn, null, attributes);

        return relativeDn;
    }
}
```

Lời gọi:

```java
Name createdDn = personDirectoryWriter.createPerson(
        "alice", "Alice Nguyen", "Nguyen");

System.out.println(createdDn);
// uid=alice,ou=people  (tương đối với base đã cấu hình)
```

Khi chạy thành công, directory chứa entry tương đương LDIF sau:

```ldif
dn: uid=alice,ou=people,dc=example,dc=com
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: alice
cn: Alice Nguyen
sn: Nguyen
```

LDIF trên mô tả dữ liệu **dự kiến**; các thuộc tính vận hành như thời gian tạo, người tạo hoặc ID do server sinh thêm tùy directory và cấu hình.

### Tại sao cần đủ `objectClass`, `cn` và `sn`?

`objectClass` liên kết entry với quy tắc schema. Trong ví dụ, `inetOrgPerson` mở rộng các lớp tổ tiên `organizationalPerson`, `person`, `top`. Lớp `person` yêu cầu các thuộc tính như `cn` và `sn`; `uid` được dùng ở đây làm RDN và cũng là thuộc tính của entry. Nếu bỏ thiếu một thuộc tính bắt buộc hoặc dùng thuộc tính không được schema cho phép, server có thể từ chối thao tác vì vi phạm schema.

Schema và cấu hình mỗi directory có thể có yêu cầu riêng, ví dụ lớp cấu trúc bổ sung, quy tắc đặt tên, mật khẩu hoặc chính sách quyền ghi. Không thể kết luận entry hợp lệ chỉ vì mã Java biên dịch thành công.

### Tại sao dùng `LdapNameBuilder`?

DN có cú pháp escape riêng. Nếu `uid` hay `cn` được dùng làm giá trị RDN và chứa ký tự đặc biệt như dấu phẩy, dấu cộng hoặc dấu gạch chéo ngược, phép nối chuỗi trực tiếp rất dễ tạo sai DN. Ví dụ:

```text
cn=Doe\, Jane,ou=people,dc=example,dc=com
```

Trong DN này, `Doe, Jane` là **một** giá trị `cn`, không phải hai RDN. Dùng builder để đặt **loại thuộc tính** và **giá trị** giúp escape theo cú pháp tên LDAP; ứng dụng vẫn phải kiểm tra các ràng buộc nghiệp vụ về nội dung và độ dài của giá trị. Escape DN và escape bộ lọc tìm kiếm LDAP là hai công việc khác nhau.

## 5. Cách khác: `DirContextAdapter` và `bind(context)`

Spring LDAP còn cung cấp `DirContextAdapter` (triển khai `DirContextOperations`) để xây entry theo kiểu đặt từng thuộc tính. Phương pháp này gần với những luồng code sau đó sẽ dùng `lookupContext()` và `modifyAttributes()` để sửa entry.

```java
import javax.naming.Name;
import org.springframework.ldap.core.DirContextAdapter;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

public class PersonContextWriter {

    private final LdapTemplate ldapTemplate;

    public PersonContextWriter(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public void createPerson(String uid, String fullName, String surname) {
        Name relativeDn = LdapNameBuilder.newInstance()
                .add("ou", "people")
                .add("uid", uid)
                .build();

        DirContextAdapter context = new DirContextAdapter(relativeDn);
        context.setAttributeValues("objectClass", new String[] {
                "top", "person", "organizationalPerson", "inetOrgPerson"
        });
        context.setAttributeValue("uid", uid);
        context.setAttributeValue("cn", fullName);
        context.setAttributeValue("sn", surname);

        ldapTemplate.bind(context);
    }
}
```

Cả hai cách đều nhằm **tạo một entry mới** tại DN xác định. Chọn `Attributes` khi muốn xây dựng tập thuộc tính JNDI trực tiếp; chọn `DirContextAdapter` khi ứng dụng đang dùng mô hình ngữ cảnh LDAP của Spring. Không cần gọi cả hai cách cho cùng một DN.

> Ghi nhớ: `bind` là thao tác **thêm mới**, không phải *upsert*. Gọi lại `bind` cho một DN đã có entry thường bị server trả lỗi *entry already exists*. Muốn thay đổi thuộc tính của entry hiện có, dùng thao tác cập nhật phù hợp như `modifyAttributes(...)`; muốn đổi DN, dùng thao tác đổi tên hoặc di chuyển thay vì tạo trùng.

## 6. Kiểm tra kết quả sau khi `bind`

Sau khi ghi, có thể đọc entry bằng `LdapTemplate.lookup(...)` để xác nhận nó xuất hiện với thuộc tính dự kiến. Ví dụ dùng `AttributesMapper`:

```java
import javax.naming.Name;
import org.springframework.ldap.core.AttributesMapper;

Name relativeDn = personDirectoryWriter.createPerson(
        "alice", "Alice Nguyen", "Nguyen");

String actualName = ldapTemplate.lookup(
        relativeDn,
        (AttributesMapper<String>) attrs ->
                attrs.get("cn").get().toString()
);

System.out.println(actualName); // Alice Nguyen
```

`lookup` đọc theo **DN**, khác với truy vấn lọc theo thuộc tính. Khi cần xác minh nhiều thuộc tính, mapper có thể trích `uid`, `cn`, `sn`, `objectClass` thành một DTO. Cần kiểm tra `get(...)` không trả `null` nếu thuộc tính có thể bị lược bỏ hoặc thay đổi bởi server.

Nếu đọc từ replica thay vì server vừa nhận thao tác ghi, có thể có độ trễ đồng bộ tùy hệ thống. Với kiểm thử tích hợp, nên đọc từ cấu hình directory nhất quán và kiểm tra dữ liệu thật thay vì chỉ suy ra thành công từ việc `bind` không ném exception.

## 7. Các điều kiện và lỗi khi tạo entry

| Tình huống | Biểu hiện thường gặp | Hướng xử lý |
| --- | --- | --- |
| Entry đã tồn tại tại cùng DN | LDAP result code `68` (*entryAlreadyExists*). | Chọn DN khác hoặc dùng luồng cập nhật; đừng mặc định ghi đè. |
| Entry cha chưa tồn tại | LDAP result code `32` (*noSuchObject*). | Tạo đúng chuỗi entry cha theo thứ tự, kiểm tra base và DN. |
| Thiếu thuộc tính bắt buộc hoặc sai `objectClass` | LDAP result code `65` (*objectClassViolation*) hoặc lỗi schema khác. | Đối chiếu schema thực tế, thêm đúng `objectClass`/thuộc tính. |
| Tài khoản kết nối không đủ quyền ghi | LDAP result code `50` (*insufficientAccessRights*). | Kiểm tra ACL, vị trí DN và quyền của tài khoản dịch vụ. |
| DN có cú pháp sai hoặc base bị nối lặp | LDAP result code `34` (*invalidDNSyntax*) hoặc không tìm thấy cha. | Dùng DN builder và xác minh cách `ContextSource` xử lý base. |
| Không kết nối được, TLS hoặc chứng chỉ lỗi | Lỗi giao tiếp, thiết lập TLS hoặc xác thực. | Kiểm tra URL, trust store, tài khoản và trạng thái directory. |

`LdapTemplate` chuyển các ngoại lệ JNDI thành hệ ngoại lệ không kiểm tra của Spring LDAP. Mã xử lý lỗi nên phân biệt **DN trùng**, **thiếu cha**, **lỗi schema**, **thiếu quyền** và **hạ tầng** để trả thông điệp phù hợp. Không nên bắt mọi ngoại lệ rồi báo chung rằng người dùng đã tồn tại.

Trong quy trình có khả năng gửi lại yêu cầu, thao tác tạo phải được thiết kế cho trường hợp *retry*: một lần gọi trước có thể đã thêm entry thành công nhưng phản hồi bị mất. Việc kiểm tra tồn tại trước khi tạo có thể hữu ích để hiển thị lỗi sớm nhưng **không loại bỏ điều kiện tranh chấp** giữa bước kiểm tra và bước ghi. Directory vẫn là nơi quyết định tính duy nhất của DN tại thời điểm `bind`.

## 8. Dùng `LdapTemplate.bind` hay Spring Data LDAP repository?

Trong cùng một ứng dụng có thể có cả hai mức trừu tượng:

| Cách tiếp cận | Đặc điểm | Phù hợp khi |
| --- | --- | --- |
| `LdapTemplate.bind(Name, null, Attributes)` | Tự quản lý DN và các cặp thuộc tính LDAP. | Cần kiểm soát chính xác payload LDAP khi thêm entry. |
| `LdapTemplate.bind(DirContextOperations)` | Tạo ngữ cảnh LDAP và đặt các thuộc tính qua API Spring LDAP. | Đã dùng `DirContextAdapter` để thao tác entry. |
| Spring Data LDAP repository với entity `@Entry`, `@Id`, `@Attribute` | Ánh xạ entry sang đối tượng Java và thao tác qua repository. | Phần lớn ứng dụng hướng domain cần CRUD theo mô hình Java. |

Ví dụ, repository có thể ánh xạ `uid`, `cn`, `sn` và DN vào một `PersonEntry`; ở mức thấp hơn, `LdapTemplate.bind` đòi hỏi code chủ động tạo `Attributes`. Dù chọn cách nào, **schema LDAP, DN, quyền ghi và base** vẫn là những ràng buộc mà máy chủ thực thi.

## 9. An toàn khi ghi dữ liệu vào directory

- **Quyền tối thiểu:** tài khoản dịch vụ chỉ nên có quyền thêm/đọc/sửa trong các nhánh cần thiết; phân quyền rõ cho người dùng cuối.
- **Kết nối bảo mật:** dùng TLS và xác minh chứng chỉ, đặc biệt nếu gửi thông tin xác thực hoặc thuộc tính nhạy cảm.
- **Không nhúng mật khẩu vào mã nguồn:** dùng biến môi trường hay nơi quản lý bí mật phù hợp với môi trường chạy.
- **Xác thực dữ liệu trước khi ghi:** kiểm tra trường bắt buộc, định dạng và ràng buộc nghiệp vụ; builder chỉ giải quyết cú pháp DN, không thực hiện mọi quy tắc schema.
- **Không tự nối DN/filter từ dữ liệu ngoài:** dùng `LdapNameBuilder` cho DN; khi truy vấn theo thuộc tính, dùng query/filter builder có escape phù hợp.
- **Giới hạn khả năng tác động:** không cho đầu vào quyết định tùy ý `base`, `ou` đích hoặc `objectClass` nếu nghiệp vụ chỉ cho tạo người dùng dưới một nhánh xác định.
- **Giữ dữ liệu và thông điệp log cần thiết:** log DN hoặc mã tương quan phục vụ điều tra, tránh ghi mật khẩu, bí mật và các thuộc tính nhạy cảm không cần thiết.

Một lệnh `bind` ghi **một entry**. Việc tạo đồng thời nhiều entry hoặc thêm cha và con trong nhiều lời gọi không mặc nhiên có giao dịch nguyên tử xuyên suốt. Nếu quy trình tạo dữ liệu gồm nhiều bước, ứng dụng cần cơ chế điều phối và xử lý lỗi phù hợp.

## 10. Kiểm thử tích hợp với directory

Kiểm thử `bind` thực tế cần một directory dành riêng cho test, có schema và cây cha như môi trường mục tiêu. Một unit test chỉ mock `LdapTemplate` không chứng minh entry tạo ra hợp lệ trên server.

Ví dụ kiểm thử tích hợp bằng JUnit 5 trong ứng dụng Spring Boot đã cấu hình kết nối đến LDAP thử nghiệm:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.UUID;
import javax.naming.Name;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;

@SpringBootTest
class PersonDirectoryWriterIT {

    @Autowired PersonDirectoryWriter writer;
    @Autowired LdapTemplate ldapTemplate;

    @Test
    void createsEntryAndReadsBackAttributes() {
        String uid = "test-" + UUID.randomUUID();
        Name dn = writer.createPerson(uid, "Test User", "User");

        try {
            String actualUid = ldapTemplate.lookup(
                    dn,
                    (AttributesMapper<String>) attrs ->
                            attrs.get("uid").get().toString()
            );
            assertEquals(uid, actualUid);
        } finally {
            // Chỉ xóa entry test vừa tạo, ở directory dành riêng cho test.
            ldapTemplate.unbind(dn);
        }
    }
}
```

Điều kiện tiên quyết: directory thử nghiệm có `dc=example,dc=com` và `ou=people` tương ứng, thông tin kết nối đúng, schema cho phép `inetOrgPerson` và tài khoản test có quyền thêm/đọc/xóa. Nếu cần kiểm thử thiếu quyền hoặc thiếu cha, dùng fixture và tài khoản riêng phù hợp để tránh tác động dữ liệu ngoài phạm vi test.

Các kịch bản bổ sung nên xác minh: tạo entry hợp lệ; DN trùng; thiếu thuộc tính bắt buộc; giá trị RDN chứa ký tự cần escape; parent DN không tồn tại; quyền ghi bị từ chối. Kiểm tra trực tiếp `objectClass` và DN từ directory là cách phát hiện sai khác giữa dữ liệu mong muốn và dữ liệu thực tế.

## 11. Bài thực hành

**Bài 1.** Ứng dụng có `spring.ldap.base = dc=example,dc=com`. Muốn tạo entry `uid=linh,ou=people,dc=example,dc=com`, nên truyền DN nào vào `LdapTemplate.bind` với `ContextSource` đã cấu hình base?

**Đáp án:** `uid=linh,ou=people`. Đây là tên tương đối với base; nhánh `ou=people,dc=example,dc=com` phải tồn tại.

**Bài 2.** Bạn tạo entry có `objectClass=inetOrgPerson` nhưng chỉ truyền `uid` và `cn`. Vì sao thao tác có thể bị từ chối?

**Đáp án:** Thiếu `sn`, một thuộc tính bắt buộc được kế thừa từ lớp `person`. Cần cung cấp đầy đủ thuộc tính bắt buộc theo schema directory.

**Bài 3.** Hai lần gọi `ldapTemplate.bind(relativeDn, null, attributes)` với cùng DN có tạo hai bản ghi khác nhau không?

**Đáp án:** Không. LDAP không cho tồn tại hai entry tại cùng DN trong một cây. Lần tạo tiếp theo thường bị từ chối với *entryAlreadyExists*; `bind` không phải thao tác cập nhật.

**Bài 4.** Khi ứng dụng cần lưu người dùng có RDN chứa dấu phẩy, vì sao không dùng `"cn=" + inputName + ",ou=people"`?

**Đáp án:** Dấu phẩy trong giá trị có thể bị hiểu thành ký tự ngăn RDN. Dùng `LdapNameBuilder` để tạo tên từ loại thuộc tính và giá trị, rồi kiểm tra ràng buộc nghiệp vụ của đầu vào.

## 12. Ghi nhớ

- `LdapTemplate.bind(...)` dùng để **tạo entry mới**, khác với LDAP Bind để xác thực phiên kết nối.
- Một entry mới cần DN đúng vị trí, parent tồn tại, `objectClass` hợp lệ và đủ thuộc tính bắt buộc theo schema.
- Khi cấu hình `spring.ldap.base`, hãy tạo DN **tương đối với base** cho các lời gọi `LdapTemplate` tương ứng.
- Có thể ghi bằng `Attributes` hoặc `DirContextAdapter`; cả hai vẫn chịu kiểm tra schema và quyền ghi từ directory.
- Tạo trùng DN không ghi đè; dùng thao tác cập nhật/đổi tên riêng cho entry đã tồn tại.
- Hãy xác minh kết quả bằng `lookup`, kiểm thử với directory thực tế và bảo vệ thông tin xác thực/kết nối.
