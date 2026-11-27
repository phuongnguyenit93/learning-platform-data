# Bind entry bằng DirContextAdapter trong Spring LDAP

## 1. Bài toán: tạo một entry người dùng mới

Một ứng dụng quản lý tài khoản cần đưa hồ sơ nhân viên mới vào thư mục LDAP để các dịch vụ khác có thể tìm theo `uid`, đọc `cn`, `mail` và tra cứu thông tin nhóm. Với **Spring LDAP**, một cách tạo entry là chuẩn bị đối tượng `DirContextAdapter` có **DN và các thuộc tính hợp lệ**, sau đó gọi `LdapTemplate.bind(...)`.

Ví dụ mục tiêu là tạo entry:

~~~ldif
dn: uid=training-01,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: training-01
cn: Training User
sn: User
mail: training-01@example.org
~~~

Điều này yêu cầu **thêm một entry chưa tồn tại** vào nhánh `ou=people,dc=example,dc=org`, không phải sửa entry đã có.

### Hai nghĩa của từ “bind” cần phân biệt

Trong hệ sinh thái LDAP, từ **bind** có hai ngữ cảnh dễ nhầm:

| Ngữ cảnh | Mục đích | Ví dụ |
| --- | --- | --- |
| **LDAP Bind (xác thực)** | Chứng minh danh tính bằng credentials, tạo trạng thái xác thực của kết nối | Simple bind bằng DN + mật khẩu; `ContextSource.getContext(principal, credentials)` |
| **JNDI/Spring LDAP `bind` (tạo entry)** | Đăng ký/thêm một entry mới tại DN được chọn, tương ứng về ý nghĩa với LDAP **Add** | `LdapTemplate.bind(context)` |

Vì vậy, **gọi `LdapTemplate.bind(context)` không phải thao tác kiểm tra mật khẩu đăng nhập của một người dùng**. Đây là thao tác ghi vào thư mục và đòi hỏi tài khoản dịch vụ đã kết nối **có quyền tạo entry**. Nếu người dùng cần đăng nhập, ứng dụng phải xử lý LDAP Bind/xác thực theo một quy trình khác, chẳng hạn API `authenticate` hoặc Spring Security LDAP phù hợp.

Bài học thuộc chương **Bind và tạo entry** của module **Spring LDAP**. Trọng tâm là tạo entry bằng `DirContextAdapter`, kết nối các kiến thức DN, schema, object class, thao tác trên `LdapTemplate`, TLS, quyền truy cập và kiểm thử an toàn.

**Sau bài này, bạn có thể:**

- Tạo DN cho entry mới bằng `LdapNameBuilder`, hiểu sự khác nhau giữa DN đầy đủ và DN tương đối.
- Khởi tạo `DirContextAdapter` và điền `objectClass`, các thuộc tính bắt buộc/tùy chọn.
- Gọi `LdapTemplate.bind(context)` và kiểm tra lại entry đã tạo.
- Phân biệt thao tác **Add**, **Modify**, **Modify DN** và **LDAP Bind authentication**.
- Chẩn đoán lỗi trùng DN, thiếu parent, schema, ACL, TLS và timeout.
- Kiểm thử trên LDAP directory riêng, không ảnh hưởng dữ liệu thật.

## 2. DN và cấu trúc thư mục quyết định vị trí tạo entry

Xét cây LDAP mẫu:

~~~text
dc=example,dc=org
|
+-- ou=people
|   |
|   +-- uid=alice
|   +-- ou=engineering
|       |
|       +-- uid=bob
|
+-- ou=groups
|   |
|   +-- cn=developers
|
+-- ou=system
    |
    +-- cn=directory-reader
    +-- cn=directory-editor
~~~

DN của entry mới cần tạo:

~~~text
uid=training-01,ou=people,dc=example,dc=org
~~~

Trong DN này:

- `uid=training-01` là **RDN** định danh entry trong OU cha.
- `ou=people` là entry cha trực tiếp, phải **tồn tại** trước khi tạo entry con.
- `dc=example,dc=org` là hậu tố của vùng dữ liệu trong ví dụ.

**LDAP Add không tự tạo các OU cha**. Nếu `ou=people` chưa tồn tại hoặc tài khoản không thể tạo entry tại đó, lệnh tạo người dùng có thể bị từ chối.

### 2.1. DN đầy đủ so với DN tương đối trong Spring LDAP

Giả sử `LdapContextSource` đã cấu hình base:

~~~text
ContextSource base: dc=example,dc=org
~~~

Khi đó DN truyền cho nhiều phương thức của `LdapTemplate` là DN **tương đối** với base:

~~~text
DN trong Java:      uid=training-01,ou=people
DN trên LDAP server: uid=training-01,ou=people,dc=example,dc=org
~~~

Không thêm lại `dc=example,dc=org` vào DN trong Java nếu nó đã được đặt ở ContextSource, vì việc dùng lẫn DN tương đối và đầy đủ dễ tạo vị trí sai.

### 2.2. Tạo DN bằng LdapNameBuilder

**Không nên** xây DN bằng cách nối một UID chưa tin cậy:

~~~java
// Không nên dùng khi uid đến từ API/form:
String dn = "uid=" + uid + ",ou=people";
~~~

Nếu UID chứa dấu phẩy, dấu cộng, dấu bằng hoặc ký tự đặc biệt khác, chuỗi DN có thể bị diễn giải khác với ý định ban đầu.

**Nên dùng:**

~~~java
import javax.naming.Name;
import org.springframework.ldap.support.LdapNameBuilder;

Name relativeDn = LdapNameBuilder.newInstance("ou=people")
        .add("uid", "training-01")
        .build();
~~~

`LdapNameBuilder` tạo tên theo cấu trúc DN và xử lý escaping RDN. Tuy nhiên, việc escape **không thay thế** validation nghiệp vụ: cần giới hạn chiều dài, ký tự được hỗ trợ theo chính sách tổ chức và tính hợp lệ của UID. Escaping DN cũng khác escaping **LDAP filter** dùng trong `LdapQueryBuilder`.

## 3. Schema: objectClass và thuộc tính phải hợp lệ

**Schema LDAP** quy định loại object class, thuộc tính cho phép và những ràng buộc về syntax/số lượng giá trị. Không thể thêm tùy ý một entry chỉ có `uid` mà bỏ các thuộc tính bắt buộc.

Với một entry người dùng kiểu `inetOrgPerson` thường gặp:

| Thuộc tính | Ví dụ | Vai trò |
| --- | --- | --- |
| `objectClass` | `top`, `person`, `organizationalPerson`, `inetOrgPerson` | Xác định cấu trúc entry và nhóm thuộc tính hợp lệ |
| `cn` | `Training User` | Common Name; `person` yêu cầu `cn` |
| `sn` | `User` | Surname; `person` yêu cầu `sn` |
| `uid` | `training-01` | Định danh trong ví dụ, đồng thời được dùng ở RDN |
| `mail` | `training-01@example.org` | Email; thường tùy chọn |
| `telephoneNumber` | `+84 28 1111 2222` | Điện thoại; có thể đa trị theo schema |
| `description` | `training` | Mô tả tùy chọn, có thể có nhiều giá trị |

Nhánh kế thừa phổ biến của `inetOrgPerson` là:

~~~text
top
  |
person
  |
organizationalPerson
  |
inetOrgPerson
~~~

Với LDAP server tuân theo schema chuẩn tương ứng, `cn` và `sn` là thuộc tính **MUST** do object class cha; `mail` và nhiều thuộc tính khác là **MAY**. Các schema mở rộng hoặc chính sách cụ thể của hệ thống có thể bổ sung yêu cầu riêng, vì vậy cần đối chiếu cấu hình LDAP server mục tiêu.

### 3.1. Object class là thuộc tính đa trị

Ở Java, đặt `objectClass` bằng danh sách giá trị, không tạo nhiều thuộc tính có cùng ID một cách tùy tiện:

~~~java
context.setAttributeValues("objectClass", new String[] {
        "top",
        "person",
        "organizationalPerson",
        "inetOrgPerson"
});
~~~

**Không đặt `objectClass` thành một chuỗi duy nhất chứa dấu phẩy** như:

~~~java
// Sai ý nghĩa: một String, không phải 4 giá trị objectClass.
context.setAttributeValue(
        "objectClass",
        "top,person,organizationalPerson,inetOrgPerson"
);
~~~

Một số LDAP server có thể suy diễn object class cha khi chỉ truyền lớp con, nhưng ví dụ chủ động khai báo đầy đủ chuỗi kế thừa để dễ kiểm tra và không phụ thuộc giả định riêng của server.

### 3.2. Thuộc tính RDN phải nhất quán

Nếu DN bắt đầu bằng `uid=training-01`, entry được thêm phải có dữ liệu định danh tương ứng với quy tắc naming/schema của server. Đừng tạo DN `uid=training-01,...` nhưng lại điền `uid=somebody-else`.

Một số server kiểm tra sự tương ứng giữa giá trị trong RDN và attribute của entry; các sai lệch có thể dẫn đến lỗi naming hoặc schema. Trong mã ví dụ, cùng một biến UID được dùng để dựng DN và thuộc tính `uid`.

### 3.3. Thông tin xác thực không đồng nghĩa hồ sơ người dùng

Một entry `inetOrgPerson` có `cn`, `sn` và `uid` **chưa chắc có thể đăng nhập**. Khả năng xác thực còn phụ thuộc thuộc tính thông tin xác thực, chính sách mật khẩu, trạng thái tài khoản và cấu hình server.

Không tự lưu mật khẩu dạng plaintext hoặc tự chọn thuật toán băm chỉ vì có thuộc tính `userPassword`. Việc cấp mật khẩu khởi tạo, reset bắt buộc, policy và xác thực là quy trình bảo mật riêng, nên dùng cơ chế chính thức của hạ tầng.

## 4. DirContextAdapter là gì và vì sao phù hợp để tạo entry?

Trong Spring LDAP:

- `DirContextOperations` là giao diện thuận tiện để truy cập và thao tác thuộc tính entry.
- `DirContextAdapter` là triển khai phổ biến, có thể chứa DN cùng các thuộc tính của entry.
- `LdapTemplate` sử dụng `ContextSource` để gửi thao tác tới LDAP server.

Đối với **tạo entry**, ta có thể tạo một adapter mới:

~~~java
import javax.naming.Name;
import org.springframework.ldap.core.DirContextAdapter;

DirContextAdapter context = new DirContextAdapter(relativeDn);

context.setAttributeValues("objectClass", new String[] {
        "top", "person", "organizationalPerson", "inetOrgPerson"
});
context.setAttributeValue("uid", "training-01");
context.setAttributeValue("cn", "Training User");
context.setAttributeValue("sn", "User");
context.setAttributeValue("mail", "training-01@example.org");
~~~

Đến đây, adapter **chỉ là một đối tượng phía Java**. Nó chưa làm LDAP server tạo entry.

Cần gọi tiếp:

~~~java
ldapTemplate.bind(context);
~~~

**Lưu ý tên gọi:** `bind(context)` trong Spring LDAP dùng để **thêm entry**. Không được hiểu lời gọi này là xác thực credentials mới cho kết nối.

### 4.1. Khác adapter mới với adapter đọc từ server

| Trường hợp | Cách lấy adapter | Thao tác LDAP phù hợp |
| --- | --- | --- |
| Tạo entry mới | `new DirContextAdapter(dn)` rồi đặt đầy đủ thuộc tính | `LdapTemplate.bind(context)` |
| Đọc entry hiện có | `LdapTemplate.lookupContext(dn)` | Đọc/ánh xạ |
| Sửa entry hiện có | `lookupContext(dn)`, thay thuộc tính qua adapter | `LdapTemplate.modifyAttributes(context)` |
| Đổi DN/RDN | Xác định DN cũ và DN mới | `LdapTemplate.rename(oldDn, newDn)` |
| Xóa entry | Xác định DN đích và điều kiện nghiệp vụ | `LdapTemplate.unbind(dn)` |

Một adapter mới để tạo entry **không có bản sao trạng thái hiện tại trên server**. Vì thế, không dùng nó như bằng chứng rằng entry đã tồn tại hoặc rằng `getModificationItems()` là cách thích hợp để cập nhật entry. Phân biệt Add và Modify sẽ giúp tránh ghi đè hoặc gửi sai loại thao tác.

## 5. Ví dụ hoàn chỉnh: tạo người dùng bằng DirContextAdapter

### 5.1. Cấu hình ContextSource và LdapTemplate

Ví dụ dùng Spring Framework Java Config và các biến môi trường:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.core.support.LdapContextSource;

@Configuration
public class DirectoryConfiguration {

    @Bean
    public LdapContextSource ldapContextSource(
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
    public LdapTemplate ldapTemplate(LdapContextSource ldapContextSource) {
        return new LdapTemplate(ldapContextSource);
    }
}
~~~

~~~yaml
# application.yml — chỉ là giá trị ví dụ
app:
  ldap:
    url: ${LDAP_URL:ldaps://ldap.example.org:636}
    base: dc=example,dc=org
    bind-dn: ${LDAP_BIND_DN}
    bind-password: ${LDAP_BIND_PASSWORD}
~~~

Những property `app.ldap.*` là cấu hình **do ứng dụng minh họa định nghĩa**. Với Spring Boot và dependency thích hợp, có thể thay bằng các property chuẩn như `spring.ldap.urls`, `spring.ldap.base`, `spring.ldap.username` và `spring.ldap.password`. Không tạo trùng các bean hạ tầng mà không biết bean nào được tiêm vào repository.

Tài khoản bind của cấu hình cần quyền tạo entry **chỉ trong OU được phê duyệt**. Mật khẩu không được commit vào Git hoặc đưa vào log. Kết nối LDAPS phải xác minh chứng chỉ và hostname.

### 5.2. DTO cho thông tin đầu vào

Java 17 `record` có thể diễn đạt đầu vào của chức năng tạo người dùng:

~~~java
public record NewDirectoryPerson(
        String uid,
        String commonName,
        String surname,
        String email
) {
}
~~~

Trong ví dụ, `uid`, `commonName` và `surname` là dữ liệu bắt buộc. `email` là tùy chọn. Với dự án Java cũ hơn, có thể thay record bằng một lớp DTO/POJO và các getter tương ứng.

### 5.3. Repository tạo entry

~~~java
import javax.naming.Name;

import org.springframework.ldap.core.DirContextAdapter;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;
import org.springframework.stereotype.Repository;

@Repository
public class DirectoryPersonRepository {
    private final LdapTemplate ldapTemplate;

    public DirectoryPersonRepository(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public Name create(NewDirectoryPerson person) {
        String uid = required(person.uid(), "uid");
        String cn = required(person.commonName(), "commonName");
        String sn = required(person.surname(), "surname");

        // DN tương đối với ContextSource.base = dc=example,dc=org.
        Name dn = LdapNameBuilder.newInstance("ou=people")
                .add("uid", uid)
                .build();

        DirContextAdapter context = new DirContextAdapter(dn);

        context.setAttributeValues("objectClass", new String[] {
                "top",
                "person",
                "organizationalPerson",
                "inetOrgPerson"
        });
        context.setAttributeValue("uid", uid);
        context.setAttributeValue("cn", cn);
        context.setAttributeValue("sn", sn);

        if (person.email() != null && !person.email().isBlank()) {
            context.setAttributeValue("mail", person.email());
        }

        // Gửi LDAP Add thông qua Spring LDAP.
        ldapTemplate.bind(context);
        return dn;
    }

    private static String required(String value, String field) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                    field + " must not be blank");
        }
        return value;
    }
}
~~~

Gọi từ service:

~~~java
Name dn = repository.create(
        new NewDirectoryPerson(
                "training-01",
                "Training User",
                "User",
                "training-01@example.org"
        )
);
~~~

Đây là các đoạn mã minh họa cần đặt trong dự án có đủ dependency Spring LDAP, cấu hình bean và thư mục LDAP test tương thích. Trong hệ thống thực tế, nên có thêm validation domain, kiểm soát quyền người gọi, giới hạn chiều dài và quy trình xử lý lỗi nghiệp vụ.

### 5.4. Phân tích những điểm quan trọng

1. **DN được tạo trước:** `LdapNameBuilder` xử lý escaping RDN cho `uid`.
2. **Adapter gắn với DN:** `new DirContextAdapter(dn)` cho biết entry sẽ được tạo tại đâu.
3. **Object classes được khai báo đầy đủ:** giúp server xác nhận cấu trúc entry.
4. **Thuộc tính bắt buộc được đặt:** `cn`, `sn` cùng `uid` phục vụ naming.
5. **Email là tùy chọn:** không nên đưa vào một giá trị rỗng chỉ để “đủ trường”.
6. **Chỉ lệnh bind mới gửi thao tác tạo:** các setter trước đó chỉ cập nhật đối tượng adapter trong Java.

**Điều quan trọng:** phương thức `create` trả một DN đã được dùng để yêu cầu tạo entry, nhưng kết quả từ lời gọi chỉ bảo đảm theo hợp đồng API và server khi **không có ngoại lệ**. Khi kết nối đứt sau khi gửi yêu cầu, phải xác minh trạng thái entry trước khi khẳng định thất bại hoặc thử lại.

## 6. Tạo thuộc tính đa trị bằng adapter

Nhiều entry có thuộc tính chứa **nhiều giá trị**, chẳng hạn `telephoneNumber` hoặc `description`. Adapter có phương thức `setAttributeValues`:

~~~java
DirContextAdapter context = new DirContextAdapter(dn);

context.setAttributeValues("objectClass", new String[] {
        "top", "person", "organizationalPerson", "inetOrgPerson"
});
context.setAttributeValue("uid", "training-02");
context.setAttributeValue("cn", "Training Two");
context.setAttributeValue("sn", "Two");

context.setAttributeValues("telephoneNumber", new String[] {
        "+84 28 1111 2222",
        "+84 28 3333 4444"
});

context.setAttributeValues("description", new String[] {
        "training",
        "engineering"
});

ldapTemplate.bind(context);
~~~

Trong đoạn này, biến `dn` phải trỏ tới `uid=training-02,ou=people` (DN tương đối), được dựng trước bằng `LdapNameBuilder`. Đừng tái sử dụng DN của `training-01` vì tạo entry thứ hai cùng DN sẽ thất bại.

### 6.1. Không nhầm một chuỗi phân tách bằng dấu phẩy với nhiều giá trị

**Sai ý nghĩa:**

~~~java
context.setAttributeValue(
        "telephoneNumber",
        "+84 28 1111 2222, +84 28 3333 4444"
);
~~~

Đây là **một chuỗi duy nhất**, không phải hai giá trị LDAP. Nếu schema cho phép nhiều giá trị, dùng `setAttributeValues(...)` hoặc API thêm giá trị phù hợp.

### 6.2. Thứ tự thuộc tính đa trị không phải thứ tự nghiệp vụ

LDAP attribute đa trị thông thường không có thứ tự được bảo đảm theo nghĩa ứng dụng. Khi đọc lại hai số điện thoại, không nên mặc định số đầu tiên là số “chính”. Nếu nghiệp vụ cần số chính/phụ, phải có mô hình dữ liệu hoặc thuộc tính riêng mô tả ưu tiên.

### 6.3. Schema SINGLE-VALUE vẫn được kiểm tra

Một số attribute type được schema đánh dấu `SINGLE-VALUE`. Đưa hai giá trị vào thuộc tính như vậy có thể khiến LDAP server từ chối Add, dù Java code xây adapter thành công. Không được hiểu `setAttributeValues` là cách bỏ qua schema.

## 7. Phân biệt bind tạo entry, modify và rename

Một số lỗi trong ứng dụng đến từ việc dùng **sai thao tác LDAP** dù cấu trúc Java hợp lệ.

| Tình huống | API Spring LDAP nên cân nhắc | Ý nghĩa giao thức |
| --- | --- | --- |
| DN chưa tồn tại, cần tạo entry mới | `LdapTemplate.bind(context)` | LDAP Add |
| DN đã tồn tại, chỉ thay mail hoặc phone | `LdapTemplate.modifyAttributes(...)` | LDAP Modify |
| Đổi RDN `uid=old` thành `uid=new` | `LdapTemplate.rename(oldDn, newDn)` | LDAP Modify DN |
| Xóa entry được phép xóa | `LdapTemplate.unbind(dn)` | LDAP Delete |
| Chứng thực người dùng bằng mật khẩu | `ContextSource.getContext(principal, credentials)` hoặc cơ chế authentication | LDAP Bind (xác thực) |

### 7.1. Không dùng bind để “ghi đè nếu đã tồn tại”

`LdapTemplate.bind(context)` không phải **upsert**. Nếu entry có DN tương ứng đã tồn tại, server thường trả LDAP result code **68 — `entryAlreadyExists`**. Ứng dụng cần quyết định rõ:

- Trả về lỗi xung đột của nghiệp vụ.
- Kiểm tra liệu entry đã tồn tại có đúng trạng thái yêu cầu hay không (khi triển khai thao tác idempotent).
- Chuyển sang một luồng **cập nhật** riêng sau khi đã xác minh danh tính/ý định, không tự ghi đè thông tin người khác.

**Không nên** bắt mọi lỗi “đã tồn tại” rồi gọi `modifyAttributes` một cách mù quáng. Rủi ro là ghi đè một entry có cùng DN nhưng được tạo bởi một request hay người dùng khác.

### 7.2. Adapter mới khác adapter lấy từ lookupContext

**Tạo mới:**

~~~java
DirContextAdapter newEntry = new DirContextAdapter(newDn);
newEntry.setAttributeValues("objectClass", objectClasses);
// ... đặt toàn bộ thuộc tính cần thiết ...
ldapTemplate.bind(newEntry);
~~~

**Sửa entry đã tồn tại:**

~~~java
DirContextOperations existing =
        ldapTemplate.lookupContext(existingDn);

existing.setAttributeValue("mail", "new-mail@example.org");
ldapTemplate.modifyAttributes(existing);
~~~

Luồng thứ hai sử dụng dữ liệu đọc được từ server làm trạng thái gốc để adapter theo dõi thay đổi. Nó không tạo entry mới. **Không biến một adapter rỗng thành công cụ cập nhật mà không đọc trạng thái cần thiết**, vì như vậy có thể thiếu hoặc làm sai dữ liệu hiện có.

## 8. Mối quan hệ với LdapTemplate.bind overload dùng Attributes

Spring LDAP cũng cho phép tạo entry bằng các overload `bind(...)` nhận DN/Attributes theo API được sử dụng. Ví dụ, với một DN đã có và các thuộc tính JNDI:

~~~java
import javax.naming.Name;
import javax.naming.directory.Attributes;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.BasicAttributes;

Attributes attributes = new BasicAttributes(true);

BasicAttribute classes = new BasicAttribute("objectClass");
classes.add("top");
classes.add("person");
classes.add("organizationalPerson");
classes.add("inetOrgPerson");

attributes.put(classes);
attributes.put("uid", "training-03");
attributes.put("cn", "Training Three");
attributes.put("sn", "Three");

ldapTemplate.bind(dn, null, attributes);
~~~

Đoạn này giả định `dn` là DN **tương đối** đã được tạo cho `training-03`. `new BasicAttributes(true)` khiến đối tượng `Attributes` của JNDI xử lý tên thuộc tính không phân biệt hoa thường trong cấu trúc dữ liệu Java.

So với API thủ công:

~~~java
DirContextAdapter context = new DirContextAdapter(dn);
context.setAttributeValues("objectClass", new String[] {
        "top", "person", "organizationalPerson", "inetOrgPerson"
});
context.setAttributeValue("uid", "training-03");
context.setAttributeValue("cn", "Training Three");
context.setAttributeValue("sn", "Three");

ldapTemplate.bind(context);
~~~

**DirContextAdapter** giúp mã tạo entry gần với thao tác trên một object có DN/thuộc tính; phương án `Attributes` giúp thao tác trực tiếp với dữ liệu JNDI. Hai phương án cùng cần schema, ACL và DN hợp lệ. Không gửi **cả hai lệnh** cho cùng DN khi chỉ muốn tạo một entry.

## 9. Đối chiếu LDAP Add bằng LDIF và ldapadd

Một tệp LDIF đơn giản dùng để **thêm** entry có thể chứa:

~~~ldif
dn: uid=training-01,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: training-01
cn: Training User
sn: User
mail: training-01@example.org
~~~

Lưu thành `training-01.ldif` trong môi trường thử nghiệm. Nếu công cụ `ldapadd` đã được cài và có quyền truy cập directory thử nghiệm:

~~~bash
ldapadd -x \
  -H "ldaps://ldap.example.org:636" \
  -D "cn=directory-editor,ou=system,dc=example,dc=org" -W \
  -f training-01.ldif
~~~

Một số môi trường dùng `ldapmodify` với LDIF chứa `changetype: add`, nhưng ví dụ này dùng `ldapadd` cho LDIF entry thuần để phân biệt mục đích tạo với Modify.

Ý nghĩa:

- `-H`: URL LDAP qua TLS.
- `-D`: tài khoản bind có quyền thêm entry.
- `-W`: nhập mật khẩu tương tác, tránh truyền mật khẩu thẳng trên dòng lệnh.
- `-f`: tập tin LDIF chứa entry mới.

**Đừng chạy `ldapadd` nếu Spring LDAP đã tạo cùng DN.** Khi đó sẽ gặp lỗi trùng DN, không phải vì hai cách tạo có schema khác nhau.

### 9.1. Xác minh bằng ldapsearch

Sau khi tạo thành công:

~~~bash
ldapsearch -LLL -x \
  -H "ldaps://ldap.example.org:636" \
  -D "cn=directory-reader,ou=system,dc=example,dc=org" -W \
  -b "uid=training-01,ou=people,dc=example,dc=org" -s base \
  "(objectClass=*)" dn objectClass uid cn sn mail
~~~

Lệnh này tìm **chính entry tại DN** bằng `-s base`, không quét cả subtree. Nếu tài khoản đọc thiếu quyền nhìn thấy thuộc tính, tập trả về có thể không đầy đủ dù entry đã được tạo.

### 9.2. Đối chiếu mã Spring LDAP và LDIF

| Tệp LDIF | Mã adapter | Ý nghĩa |
| --- | --- | --- |
| `dn: uid=training-01,...` | `new DirContextAdapter(dn)` | Đích tạo entry |
| Nhiều dòng `objectClass:` | `setAttributeValues("objectClass", ...)` | Các giá trị object class |
| `uid: training-01` | `setAttributeValue("uid", uid)` | Giá trị UID |
| `cn:`, `sn:` | Hai lần `setAttributeValue(...)` | Thuộc tính cần thiết |
| `ldapadd ...` | `ldapTemplate.bind(context)` | Gửi thao tác tạo tới server |

## 10. Kiểm tra trạng thái sau khi tạo bằng LdapTemplate.lookup

Sau khi thêm entry, ứng dụng có thể lookup để kiểm tra:

~~~java
import javax.naming.Name;
import javax.naming.directory.Attribute;

import org.springframework.ldap.core.AttributesMapper;

String createdUid = ldapTemplate.lookup(
        dn,
        (AttributesMapper<String>) attributes -> {
            Attribute uid = attributes.get("uid");
            return uid == null ? null : String.valueOf(uid.get());
        }
);
~~~

Đoạn này giả định có `ldapTemplate` và `dn` đã được tạo. Với dữ liệu mẫu, kết quả mong đợi là `training-01` nếu tài khoản đọc được phép xem `uid`.

**Phân biệt:** việc `lookup` không trả được `mail` có thể do mail không được lưu, do truy vấn không yêu cầu thuộc tính hoặc ACL che dữ liệu. Không tự suy diễn rằng thao tác tạo thất bại chỉ vì một thuộc tính không được nhìn thấy.

### 10.1. Xác minh nhiều thuộc tính

Một kiểm thử đáng tin cậy nên kiểm tra:

1. DN đầy đủ có đúng vị trí mong đợi không?
2. `objectClass` có các giá trị cần thiết không?
3. `uid` khớp với RDN không?
4. `cn` và `sn` có đúng không?
5. Thuộc tính tùy chọn có được giữ nguyên dạng mong đợi không?
6. Thuộc tính đa trị có đủ **tập giá trị** không, không phụ thuộc thứ tự?

Với `AttributesMapper`, có thể dùng `Attribute.getAll()` và đóng `NamingEnumeration` để đọc toàn bộ giá trị. Không dùng chỉ `get()` khi cần kiểm tra tập đa trị.

## 11. Lỗi phổ biến khi bind tạo entry

| LDAP result | Tên thường gặp | Nguyên nhân nên kiểm tra |
| --- | --- | --- |
| **68** | `entryAlreadyExists` | DN đã có entry, không thể Add cùng DN |
| **32** | `noSuchObject` | Parent/base DN không tồn tại hoặc không thể truy cập |
| **65** | `objectClassViolation` | Thiếu `MUST`, thuộc tính không được phép hoặc sai object class |
| **17** | `undefinedAttributeType` | Tên thuộc tính chưa được schema định nghĩa |
| **21** | `invalidAttributeSyntax` | Giá trị không hợp syntax của attribute type |
| **19** | `constraintViolation` | Vi phạm số lượng giá trị hoặc ràng buộc khác |
| **34** | `invalidDNSyntax` | DN không hợp cú pháp |
| **50** | `insufficientAccessRights` | Tài khoản bind không có quyền tạo entry ở OU đích |
| **53** | `unwillingToPerform` | Server từ chối theo chính sách |
| Lỗi bind/TLS/timeout | Tùy provider/server | Thông tin xác thực, chứng chỉ hoặc kết nối hỏng |

Đây là mã lỗi thường gặp; LDAP server có thể trả thông báo hoặc mã khác theo chính sách. Spring LDAP chuyển nhiều ngoại lệ JNDI thành ngoại lệ framework để ứng dụng xử lý, nhưng **không nên bắt mọi lỗi rồi diễn giải là entry đã tồn tại**.

### 11.1. Thiếu parent DN

Nếu parent `ou=people,dc=example,dc=org` chưa tồn tại, lệnh tạo `uid=training-01,...` có thể thất bại. Không tự tạo hàng loạt nhánh OU trong code nghiệp vụ chỉ để chữa một lỗi cấu hình; việc tạo OU là thao tác quản trị có quyền và quy trình riêng.

### 11.2. Schema không cho phép thuộc tính

Ví dụ thêm `departmentCode` vào `inetOrgPerson` khi schema chưa định nghĩa nó có thể bị từ chối. Nếu doanh nghiệp cần thuộc tính mở rộng, cần quy trình quản lý schema/object class được phê duyệt, không cố lách kiểm tra server bằng cách đổi API Java.

### 11.3. Trùng DN và tranh chấp tạo đồng thời

Hai request đến cùng lúc có thể cùng kiểm tra “chưa tồn tại” rồi cùng thử tạo một DN. LDAP Add của server sẽ quyết định request nào thành công; request còn lại thường gặp `entryAlreadyExists`. Vì vậy, một lần lookup trước Add **không thay thế** xử lý duplicate error và không bảo đảm thao tác “check then create” là nguyên tử.

### 11.4. Kết nối đứt sau khi gửi Add

Nếu client gửi yêu cầu Add rồi mất kết nối trước khi nhận response, không thể mặc định server chưa tạo entry. **Đọc lại trạng thái theo DN** trước khi retry. Nếu entry đã tồn tại, kiểm tra xem dữ liệu có khớp yêu cầu hay không; không tự ghi đè hoặc xóa entry khi chưa xác minh ai là chủ sở hữu thao tác.

## 12. Bảo mật khi tạo entry

Tạo entry mới là thao tác **ghi** và có hậu quả lâu dài trong thư mục. Một thiết kế an toàn cần hơn một DN được escape đúng.

### 12.1. Kiểm soát quyền tài khoản dịch vụ

- **Reader identity:** chỉ có quyền tìm/đọc những thuộc tính cần thiết.
- **Editor identity:** chỉ được tạo entry trong **OU được phê duyệt** và với thuộc tính hợp lệ.
- **Admin identity:** không sử dụng làm tài khoản mặc định của ứng dụng chỉ để tạo người dùng.

**`getReadWriteContext()` không tự cấp quyền ghi**. Nếu tài khoản bind không có ACL tạo entry, LDAP server phải từ chối Add.

Nếu sử dụng hai `ContextSource` và hai `LdapTemplate` cho reader/editor, cần đặt tên bean rõ ràng và tiêm đúng bằng `@Qualifier`. Không để repository chỉ đọc vô tình mang credentials có quyền quản trị.

### 12.2. Chỉ cho phép bộ thuộc tính đã duyệt

Không để client HTTP gửi một map `attributeName → value` tùy ý rồi gọi `setAttributeValue(name, value)` cho tất cả. Điều này có thể tạo cơ hội ghi `userPassword`, `objectClass`, thuộc tính nhóm/quyền hoặc các trường quản trị mà nghiệp vụ không dự kiến.

Thay vào đó, dùng DTO có các trường được phê duyệt và xây adapter bằng **allowlist rõ ràng**. Mỗi trường cần được validate kiểu, định dạng, độ dài và quyền gọi.

### 12.3. TLS và secrets

- Sử dụng **LDAPS** với chứng chỉ/hostname được xác minh, hoặc **StartTLS** thực hiện đúng trước khi truyền credentials.
- `ldap://` không tự bật StartTLS.
- Không vô hiệu hóa kiểm tra chứng chỉ để vượt lỗi handshake.
- Giữ mật khẩu tài khoản dịch vụ trong nguồn secrets an toàn; không ghi password vào log hoặc tệp bài tập.
- Hạn chế log DN chứa thông tin cá nhân và không log toàn bộ attributes của entry.

### 12.4. Pooling không giúp vượt ACL

Pooling có thể tái sử dụng context để giảm chi phí kết nối/TLS, nhưng **không** bảo đảm kết quả Add đúng hoặc cấp thêm quyền. Cần kiểm tra trạng thái bind và vòng đời context, nhất là khi ứng dụng dùng nhiều danh tính dịch vụ hoặc StartTLS. Khi dùng `LdapTemplate`, template quản lý context cho thao tác thông thường; nếu lấy `DirContext` trực tiếp, phải đóng tài nguyên đúng hợp đồng.

## 13. Kiểm thử unit và integration cho thao tác tạo

Kiểm thử tạo entry cần hai tầng:

1. **Unit test:** xác nhận DTO/validation và các thuộc tính trên adapter được xây đúng; có thể không cần máy chủ LDAP.
2. **Integration test:** gửi LDAP Add lên **server thử nghiệm thật**, xác nhận schema, ACL, DN, TLS, mã lỗi và đọc lại kết quả.

Một test chỉ mock `LdapTemplate.bind(...)` **không chứng minh** LDAP server thật cho phép Add.

### 13.1. Kiểm tra adapter trước khi bind

Ví dụ kiểm tra đối tượng adapter tại bộ nhớ:

~~~java
import javax.naming.Name;
import org.junit.jupiter.api.Test;
import org.springframework.ldap.core.DirContextAdapter;
import org.springframework.ldap.support.LdapNameBuilder;

import static org.junit.jupiter.api.Assertions.*;

class NewEntryAdapterTest {

    @Test
    void containsRequiredAttributes() {
        Name dn = LdapNameBuilder.newInstance("ou=people")
                .add("uid", "training-01")
                .build();

        DirContextAdapter context = new DirContextAdapter(dn);
        context.setAttributeValues("objectClass", new String[] {
                "top", "person", "organizationalPerson", "inetOrgPerson"
        });
        context.setAttributeValue("uid", "training-01");
        context.setAttributeValue("cn", "Training User");
        context.setAttributeValue("sn", "User");

        assertEquals(
                "training-01",
                context.getStringAttribute("uid")
        );
        assertEquals(
                "Training User",
                context.getStringAttribute("cn")
        );
        assertEquals(
                "User",
                context.getStringAttribute("sn")
        );
        assertEquals(4,
                context.getStringAttributes("objectClass").length);
    }
}
~~~

Đây là kiểm thử Java cho object được xây; nó **không** xác nhận server chấp nhận schema hoặc quyền ghi. Với object class đa trị, so sánh tập giá trị nếu test cần đối chiếu nội dung, không dựa vào thứ tự.

### 13.2. Integration test tạo và đọc lại

Giả định dự án đã cấu hình `LdapTemplate` trỏ LDAP thử nghiệm, `ou=people` tồn tại, tài khoản editor có quyền tạo và dữ liệu test có DN riêng. Một khung test:

~~~java
import javax.naming.Name;
import org.junit.jupiter.api.Test;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.DirContextAdapter;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

import static org.junit.jupiter.api.Assertions.assertEquals;

class DirectoryBindIntegrationTest {
    private final LdapTemplate template;

    // Fixture/Spring Test của dự án cung cấp template.
    DirectoryBindIntegrationTest(LdapTemplate template) {
        this.template = template;
    }

    @Test
    void createsAndReadsTrainingEntry() {
        Name dn = LdapNameBuilder.newInstance("ou=people")
                .add("uid", "training-integration-01")
                .build();

        DirContextAdapter context = new DirContextAdapter(dn);
        context.setAttributeValues("objectClass", new String[] {
                "top", "person", "organizationalPerson", "inetOrgPerson"
        });
        context.setAttributeValue("uid", "training-integration-01");
        context.setAttributeValue("cn", "Integration Training");
        context.setAttributeValue("sn", "Training");

        template.bind(context);

        String actual = template.lookup(
                dn,
                (AttributesMapper<String>) attrs ->
                        String.valueOf(attrs.get("uid").get())
        );

        assertEquals("training-integration-01", actual);
    }
}
~~~

**Đây là khung minh họa**, không tự hoạt động nếu chưa có cấu hình injection, LDAP server và setup/teardown. Một integration test tốt phải:

- Sinh **DN thử nghiệm duy nhất** cho từng ca.
- Chỉ dọn dữ liệu do chính test tạo, không xóa entry có sẵn của môi trường.
- Đảm bảo dọn dẹp trong `finally` hoặc test fixture phù hợp khi đã xác nhận quyền sở hữu entry.
- Không chạy đồng thời các case dùng chung một DN.
- Ghi nhận trường hợp Add đã thành công nhưng test chưa kịp đọc response.

### 13.3. Ma trận kiểm thử cần có

| Ca kiểm thử | Điều kiện | Kết quả dự kiến |
| --- | --- | --- |
| Tạo entry hợp schema | Parent tồn tại, DN mới, editor được phép | Add thành công, lookup đọc lại đúng |
| Thiếu `sn` | Entry thuộc `person` | Schema từ chối |
| Trùng DN | Entry đã có từ trước | LDAP code 68 hoặc lỗi tương ứng |
| Parent không tồn tại | `ou=missing` | Add thất bại, không tự tạo parent |
| Thuộc tính chưa được schema cho phép | Thêm trường tùy ý | Server từ chối |
| Object class là chuỗi thay vì tập giá trị | Sai dữ liệu tạo adapter | Server từ chối hoặc dữ liệu không đúng mục đích |
| Thuộc tính đa trị | Hai số điện thoại hợp lệ | Lookup trả đủ tập giá trị |
| Reader cố tạo | Reader thiếu ACL ghi | Server từ chối |
| RDN chứa ký tự đặc biệt | Dựng bằng `LdapNameBuilder` | DN có escaping đúng, nếu giá trị hợp chính sách |
| Sai chứng chỉ TLS | Truststore/hostname sai | Kết nối thất bại an toàn |
| Mất kết nối sau Add | Gián đoạn sau khi gửi request | Đọc lại DN trước khi retry |
| Tạo hai entry liên tiếp | Hai DN khác nhau | Không suy diễn transaction đa entry |

## 14. Bài thực hành: thêm người dùng thử nghiệm

**Bối cảnh:** một dịch vụ nội bộ cần tạo hồ sơ của một nhân viên mới trong `ou=people` và xác minh dữ liệu đã được đưa vào LDAP. Không yêu cầu cấp mật khẩu đăng nhập trong bài tập này.

1. **Chuẩn bị directory:** tạo hoặc dùng OU thử nghiệm đã được phê duyệt; xác nhận schema hỗ trợ `inetOrgPerson` và tài khoản editor được phép Add dưới nhánh đó.
2. **Cấu hình Spring:** thiết lập `LdapContextSource` với base DN, LDAPS đã xác minh chứng chỉ và credentials từ nguồn an toàn.
3. **Dựng DN:** dùng `LdapNameBuilder` cho `uid=training-01,ou=people`; giải thích tại sao không nối chuỗi DN từ UID.
4. **Tạo adapter:** `new DirContextAdapter(dn)` rồi đặt `objectClass`, `uid`, `cn` và `sn`.
5. **Thêm thuộc tính tùy chọn:** đặt `mail` và hai giá trị `telephoneNumber` nếu schema hỗ trợ.
6. **Gửi Add:** gọi `ldapTemplate.bind(context)` **một lần** và ghi nhận kết quả.
7. **Đọc lại:** dùng `lookup` hoặc `ldapsearch -s base` để đối chiếu DN, object class, RDN và tập thuộc tính.
8. **Thử Add trùng:** tạo lại cùng DN, quan sát lỗi duplicate; không tự cập nhật entry hiện có.
9. **Thử sai schema:** bỏ `sn` trên một DN test khác, quan sát server từ chối; chỉ làm trong directory test.
10. **Thử sai quyền:** sử dụng tài khoản chỉ đọc để thêm entry test mới, xác nhận ACL bảo vệ OU.
11. **So sánh thao tác:** chỉ ra khi nào cần `bind`, khi nào `modifyAttributes` hoặc `rename`.
12. **Dọn dẹp:** chỉ xóa những entry được bài thực hành tạo, ghi log kiểm toán phù hợp và không lưu credentials.

### Câu hỏi tự kiểm tra

1. `LdapTemplate.bind(context)` là LDAP Bind để xác thực hay LDAP Add để tạo entry?
2. Tại sao `DirContextAdapter` cần biết DN trước khi gọi `bind`?
3. Với `ContextSource.base = dc=example,dc=org`, DN tương đối nào dùng để tạo `uid=training-01` dưới `ou=people`?
4. Vì sao `objectClass` phải được đặt như tập nhiều giá trị thay vì một chuỗi phân tách dấu phẩy?
5. Những thuộc tính nào là bắt buộc của `inetOrgPerson` theo chuỗi kế thừa trong bài?
6. Nếu parent OU chưa tồn tại, việc Add entry người dùng có tự tạo nó không?
7. Nếu `bind` báo trùng DN, có nên tự chuyển sang Modify không? Vì sao?
8. Khi tạo `telephoneNumber` đa trị, tại sao không nên suy ra thứ tự giá trị?
9. Vì sao test mock template không đủ xác nhận tính hợp lệ của schema/ACL/TLS?
10. Khi kết nối mất sau khi gửi Add, tại sao cần đọc lại entry trước khi retry?
11. Tại sao không nên tự đưa mật khẩu plaintext vào `userPassword` trong ví dụ tạo hồ sơ?
12. Khi nào cần dùng `LdapTemplate.rename` thay vì chỉ sửa `uid`?

## 15. Tổng kết

**Tạo entry bằng `DirContextAdapter`** là một cách biểu diễn thao tác LDAP Add rõ ràng trong Spring LDAP: **dựng DN bằng `LdapNameBuilder` → tạo `DirContextAdapter(dn)` → đặt `objectClass` và các thuộc tính theo schema → gọi `LdapTemplate.bind(context)` → đọc lại kết quả**. Cần phân biệt `bind` dùng để **tạo entry** với LDAP Bind dùng để **xác thực**, đồng thời không sử dụng thao tác Add thay cho Modify hoặc Modify DN. Một entry chỉ được tạo thành công khi **DN mới, parent có sẵn, schema hợp lệ và tài khoản bind có ACL thích hợp**. Để vận hành an toàn, hãy xác minh TLS, quản lý secrets, giới hạn thuộc tính được phép ghi, xử lý duplicate và timeout, kiểm thử trên directory riêng và chỉ dọn dữ liệu do chính bài tập tạo.
