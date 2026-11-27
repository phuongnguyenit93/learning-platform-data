# ModificationItem sinh ra từ thay đổi trên DirContextAdapter trong Spring LDAP

## 1. Bài toán: thay đổi entry mà không tự lập mảng ModificationItem

Trong một ứng dụng sử dụng **Spring LDAP**, lập trình viên thường đọc một entry, sửa vài thuộc tính rồi gửi cập nhật tới LDAP server. Với API JNDI trực tiếp, cách phổ biến là tự tạo các phần tử `ModificationItem`:

~~~java
ModificationItem[] changes = {
    new ModificationItem(
            DirContext.REPLACE_ATTRIBUTE,
            new BasicAttribute("mail", "alice.new@example.org")
    )
};

ldapTemplate.modifyAttributes(dn, changes);
~~~

Cách này phù hợp khi đã biết chính xác những thay đổi cần gửi. Nhưng nếu entry có nhiều trường tùy chọn, form chỉnh sửa có thể thay một số thuộc tính và giữ nguyên phần còn lại. Việc tự xây mảng thay đổi dễ dẫn đến **ghi đè giá trị cũ**, đặc biệt với thuộc tính đa trị.

**`DirContextAdapter`** của Spring LDAP giải quyết một phần khó khăn đó: adapter biểu diễn entry LDAP dưới dạng `DirContextOperations`, cung cấp phương thức đọc/sửa thuộc tính và có thể tạo các `ModificationItem` từ thay đổi đã thực hiện so với trạng thái ban đầu. Điểm cần hiểu là **adapter hỗ trợ theo dõi thay đổi ở phía client**; LDAP server chỉ thấy yêu cầu Modify sau khi ứng dụng chủ động gọi template.

Ví dụ luồng xử lý:

~~~text
1. LDAP server trả entry Alice
           |
           v
2. LdapTemplate.lookupContext(dn)
           |
           v
3. DirContextOperations / DirContextAdapter
   - trạng thái thuộc tính lúc đọc
   - trạng thái thuộc tính được sửa qua API adapter
           |
           v
4. context.setAttributeValue("mail", "alice.new@example.org")
           |
           v
5. context.getModificationItems()
   -> ModificationItem[] đại diện thay đổi
           |
           v
6. ldapTemplate.modifyAttributes(context)
           |
           v
7. LDAP Modify request -> server kiểm tra ACL, schema, DN
~~~

**Mục tiêu bài học:**

- Hiểu vai trò `DirContextAdapter`, `DirContextOperations` và `ModificationItem` trong Spring LDAP.
- Biết cách đọc entry bằng `lookupContext`, thay đổi bằng API adapter và gửi thay đổi bằng `modifyAttributes`.
- Phân biệt ba mã JNDI **ADD**, **REPLACE**, **REMOVE** với logic theo dõi trạng thái.
- Hiểu thuộc tính đa trị, no-op, rủi ro thay đổi qua đường vòng, concurrency và kiểm thử.
- Thực hành cập nhật an toàn với DN, schema, TLS, pooling và quyền LDAP tối thiểu.

Bài học thuộc chương **DirContextAdapter** của module **Spring LDAP**, liên hệ từ schema, DN, filter/tìm kiếm đến thao tác entry qua `LdapTemplate`, `LdapClient` hoặc ODM.

## 2. Những thành phần tham gia vào quy trình

| Thành phần | Nằm ở đâu? | Vai trò |
| --- | --- | --- |
| `DirContextOperations` | Spring LDAP | Giao diện đọc/thay đổi thuộc tính entry qua API cấp cao |
| `DirContextAdapter` | Spring LDAP | Triển khai thông dụng của `DirContextOperations`, hỗ trợ tính thay đổi |
| `Attributes`, `Attribute` | JNDI | Tập thuộc tính và các giá trị |
| `ModificationItem` | JNDI | Một hành động sửa thuộc tính |
| `DirContext.ADD_ATTRIBUTE` | JNDI | Mã thao tác thêm thuộc tính/giá trị |
| `DirContext.REPLACE_ATTRIBUTE` | JNDI | Mã thao tác thay tập giá trị |
| `DirContext.REMOVE_ATTRIBUTE` | JNDI | Mã thao tác loại bỏ thuộc tính/giá trị |
| `LdapTemplate` | Spring LDAP | Đọc entry, gửi LDAP Modify và quản lý vòng đời context |
| `ContextSource` | Spring LDAP | Tạo/cung cấp context đã bind để truy cập máy chủ |

### 2.1. Phân biệt “cập nhật object Java” và “cập nhật LDAP server”

Xét đoạn mã:

~~~java
DirContextOperations context = ldapTemplate.lookupContext(dn);
context.setAttributeValue("mail", "alice.new@example.org");
~~~

Đến đây, bạn chỉ mới thay đổi **đối tượng adapter trong bộ nhớ**. LDAP server **chưa** nhận yêu cầu Modify chỉ vì một setter được gọi.

Cần thao tác tiếp:

~~~java
ldapTemplate.modifyAttributes(context);
~~~

Bước này mới yêu cầu template gửi thay đổi qua kết nối LDAP. Thành công hay thất bại được quyết định bởi server, ACL, schema và trạng thái entry.

> **Nguyên tắc:** setter trên `DirContextAdapter` không đồng nghĩa đã commit; `modifyAttributes` là điểm gửi thao tác ra LDAP.

### 2.2. Vì sao không nên coi adapter là một ORM có transaction?

`DirContextAdapter` có một số đặc điểm giống cơ chế **dirty tracking**, nhưng không phải một entity manager có transaction xuyên nhiều entry. Mỗi LDAP Modify request tác động lên **một entry**; việc đọc và sửa hai entry liên tiếp không tự thành một transaction đa đối tượng. Nếu server cập nhật entry A rồi gặp lỗi ở entry B, adapter không tự rollback entry A.

Tương tự, adapter không tự giải quyết xung đột giữa hai client cùng thay đổi một entry.

## 3. Cấu hình ContextSource và LdapTemplate

Ví dụ dùng LDAP server **thử nghiệm** ở `ldap.example.org`. Tài khoản bind cần có quyền phù hợp cho việc đọc và thay đổi thuộc tính được thực hành; không dùng mật khẩu hoặc entry thật.

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.core.support.LdapContextSource;

@Configuration
public class DirectoryConfiguration {

    @Bean
    public LdapContextSource contextSource(
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
    public LdapTemplate ldapTemplate(LdapContextSource source) {
        return new LdapTemplate(source);
    }
}
~~~

~~~yaml
# application.yml
app:
  ldap:
    url: ${LDAP_URL:ldaps://ldap.example.org:636}
    base: dc=example,dc=org
    bind-dn: ${LDAP_BIND_DN}
    bind-password: ${LDAP_BIND_PASSWORD}
~~~

Ở đây:

- **URL** chọn máy chủ và giao thức; `ldaps://` sử dụng TLS từ đầu kết nối.
- **Base DN** `dc=example,dc=org` là gốc để giải quyết DN tương đối khi gọi template.
- **Bind DN** chọn danh tính dịch vụ; có thể là `cn=directory-editor,ou=system,dc=example,dc=org`.
- **Mật khẩu** được đưa từ môi trường/secret manager, không đưa vào mã nguồn hoặc log.

Khi dự án dùng Spring Boot LDAP auto-configuration, có thể sử dụng các property chuẩn `spring.ldap.urls`, `spring.ldap.base`, `spring.ldap.username`, `spring.ldap.password` tương ứng với dependency và phiên bản. Không cấu hình cả bean thủ công và auto-configuration trùng lặp mà không kiểm tra bean được tiêm.

**Bảo mật:** phải xác minh chứng chỉ và hostname LDAPS. Nếu dùng `ldap://` với StartTLS thì cần thực sự nâng cấp TLS **trước khi gửi credentials**; chỉ đặt URL `ldap://` không tự bật StartTLS.

## 4. Ví dụ nền tảng: tra cứu, thay thuộc tính, gửi modification

Giả sử entry có DN:

~~~text
uid=alice,ou=people,dc=example,dc=org
~~~

và dữ liệu:

~~~ldif
dn: uid=alice,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: alice
cn: Alice Nguyen
sn: Nguyen
mail: alice@example.org
description: active
~~~

Một thao tác đổi email sử dụng adapter:

~~~java
import javax.naming.Name;
import javax.naming.directory.ModificationItem;

import org.springframework.ldap.core.DirContextOperations;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;
import org.springframework.stereotype.Repository;

@Repository
public class PersonDirectoryRepository {

    private final LdapTemplate ldapTemplate;

    public PersonDirectoryRepository(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public void updateMail(String uid, String newMail) {
        if (uid == null || uid.isBlank()
                || newMail == null || newMail.isBlank()) {
            throw new IllegalArgumentException(
                    "uid and mail must not be blank");
        }

        Name dn = LdapNameBuilder.newInstance("ou=people")
                .add("uid", uid)
                .build();

        DirContextOperations context = ldapTemplate.lookupContext(dn);

        String oldMail = context.getStringAttribute("mail");
        if (newMail.equals(oldMail)) {
            return; // Không cần gửi Modify nếu nghiệp vụ không đổi.
        }

        context.setAttributeValue("mail", newMail);

        ModificationItem[] changes = context.getModificationItems();

        if (changes.length == 0) {
            return;
        }

        ldapTemplate.modifyAttributes(context);
    }
}
~~~

### 4.1. Vai trò của từng dòng

1. `LdapNameBuilder` xây DN tương đối `uid=alice,ou=people`, escape RDN thay vì nối chuỗi tùy ý.
2. `ldapTemplate.lookupContext(dn)` đọc entry và trả một `DirContextOperations` có dữ liệu ban đầu để adapter đối chiếu thay đổi.
3. `getStringAttribute("mail")` đọc giá trị cho use case một email; trong ứng dụng khác cần xác định mail có thể đa trị hay không.
4. `setAttributeValue("mail", newMail)` sửa giá trị trên adapter, **chưa gửi LDAP Modify**.
5. `getModificationItems()` tạo tập `ModificationItem` để quan sát điều sắp gửi.
6. `ldapTemplate.modifyAttributes(context)` dùng thông tin DN và thay đổi của adapter để gửi cập nhật.

Nếu phiên bản API hoặc mô hình đối tượng dùng overload `modifyAttributes(dn, items)`, ứng dụng có thể chủ động gửi mảng `changes` được lấy từ adapter. **Chỉ chọn một đường gửi** cho một đợt sửa: đừng gọi cả `modifyAttributes(context)` lẫn `modifyAttributes(dn, changes)` liên tiếp vì sẽ gửi thay đổi hai lần.

### 4.2. Base DN và DN truyền vào template

Cấu hình mẫu có `ContextSource.base = dc=example,dc=org`. Vì vậy:

~~~text
DN tương đối trong Java: uid=alice,ou=people
DN đầy đủ trên server:   uid=alice,ou=people,dc=example,dc=org
~~~

Không thêm lại `dc=example,dc=org` vào DN tương đối nếu đã có base trong `ContextSource`. Nếu người dùng ở OU con như `ou=engineering`, phải xác định DN thật trước khi lookup; không tự giả định tất cả tài khoản nằm trực tiếp dưới `ou=people`.

## 5. Cơ chế sinh ModificationItem từ trạng thái của adapter

`DirContextAdapter` hỗ trợ biểu diễn trạng thái của entry và theo dõi các thay đổi qua API adapter. Khi được tạo từ lookup một entry đã tồn tại, nó có **dữ liệu ban đầu** làm cơ sở xác định những thuộc tính đã thay.

Cách tư duy hữu ích:

~~~text
Trạng thái trước (LDAP lookup)       Trạng thái sau (adapter)
------------------------------       ------------------------
mail: alice@example.org              mail: alice.new@example.org
description: active                   description: active
telephoneNumber: [a, b]              telephoneNumber: [a, b, c]
                                      |
                                      v
                           getModificationItems()
                                      |
                                      v
                        Thay đổi có ý nghĩa phải gửi
                        - mail thay giá trị
                        - telephoneNumber thay tập giá trị
                          hoặc thao tác bổ sung phù hợp
                        - description giữ nguyên
~~~

**Điều cần tránh:** khẳng định rằng mọi lời gọi `setAttributeValue` **luôn** sinh đúng một `REPLACE_ATTRIBUTE`, hoặc `addAttributeValue` **luôn** sinh một `ADD_ATTRIBUTE`. Mảng thực tế có thể phụ thuộc **trạng thái gốc**, sự tồn tại/đơn trị/đa trị của thuộc tính, chuỗi thao tác trên adapter và cách thư viện tính thay đổi ở phiên bản cụ thể.

Khi cần dự đoán chính xác mã `ADD/REPLACE/REMOVE`, hãy **kiểm tra chính mảng `getModificationItems()` và chạy test** với phiên bản Spring LDAP đang dùng, thay vì suy từ tên setter.

### 5.1. Khi không có thay đổi

Ví dụ entry đã có `mail: alice@example.org` và ứng dụng không chỉnh sửa gì:

~~~java
DirContextOperations context = ldapTemplate.lookupContext(dn);
ModificationItem[] changes = context.getModificationItems();

if (changes.length == 0) {
    // Không có thay đổi nào được adapter đưa vào yêu cầu Modify.
}
~~~

Nếu ứng dụng gọi setter nhưng gán lại giá trị tương đương, việc có phát sinh modification hay không phải dựa trên **so sánh trạng thái và API tracking** của phiên bản thư viện. Cách an toàn là có điều kiện nghiệp vụ kiểm tra trước (như ví dụ đổi email), và nếu cần thì xác minh `getModificationItems().length`.

### 5.2. Thêm thuộc tính mới so với thay thuộc tính đã có

Giả sử entry chưa có `description`:

~~~java
DirContextOperations context = ldapTemplate.lookupContext(dn);
context.setAttributeValue("description", "training account");

ModificationItem[] changes = context.getModificationItems();
~~~

Ở mức LDAP, mục tiêu là **entry có một giá trị `description` mới**. Một thay đổi có thể được biểu diễn bằng thao tác ADD/REPLACE phù hợp, nhưng không nên suy ra mã trực tiếp chỉ từ tên `setAttributeValue`. Hãy quan sát `changes` nếu bài toán cần phân biệt.

Ngược lại, nếu `description` đã tồn tại, setter mô tả **giá trị mong muốn sau sửa**. Điều này khác hẳn mục tiêu “chỉ bổ sung một giá trị” trên thuộc tính đa trị.

### 5.3. Xóa một giá trị và xóa toàn bộ thuộc tính

Với thuộc tính `description` đa trị, có hai nhu cầu:

- Xóa **một giá trị** như `training` nhưng giữ `active`.
- Xóa **toàn bộ giá trị** của thuộc tính, nếu schema cho phép.

Các API chuyên biệt trên adapter như `removeAttributeValue` có thể phục vụ nhu cầu đầu tiên. Một thao tác làm rỗng/loại thuộc tính có thể được thể hiện thành `REMOVE_ATTRIBUTE` khi chuyển sang Modify.

**Không dùng cùng một cách cho mọi thuộc tính.** Nếu xóa `sn` trên entry `inetOrgPerson`, server có thể từ chối vì `person` yêu cầu `sn`. Nếu đụng thuộc tính nằm trong RDN, có thể phải dùng thao tác Modify DN/rename thay vì xóa bằng Modify thông thường.

## 6. Các phương thức sửa thuộc tính trên DirContextOperations

Những phương thức được dùng thường xuyên:

~~~java
DirContextOperations context = ldapTemplate.lookupContext(dn);

// Đặt một giá trị đơn theo ý định nghiệp vụ.
context.setAttributeValue("mail", "alice.new@example.org");

// Đặt toàn bộ tập giá trị của một thuộc tính đa trị.
context.setAttributeValues(
        "telephoneNumber",
        new String[] {"+84 28 1111 2222", "+84 28 3333 4444"}
);

// Bổ sung một giá trị vào thuộc tính đa trị.
context.addAttributeValue(
        "description",
        "engineering"
);

// Loại một giá trị khỏi thuộc tính đa trị.
context.removeAttributeValue(
        "description",
        "training"
);

ModificationItem[] changes = context.getModificationItems();
~~~

Đoạn mã trên là minh họa thao tác liên tiếp, **không phải kịch bản chắc chắn hợp lệ cho mọi entry**. Cần kiểm tra `description: training` có tồn tại trước khi xóa; việc bổ sung hoặc xóa có thể tác động đến cùng thuộc tính nhiều lần, nên các modification cuối cùng phụ thuộc vào trạng thái gốc và các thao tác đã thực hiện.

### 6.1. `setAttributeValues` là một quyết định quan trọng

Giả sử dữ liệu LDAP có:

~~~ldif
telephoneNumber: +84 28 1111 2222
telephoneNumber: +84 28 3333 4444
~~~

Nếu form chỉ cho phép sửa số thứ nhất và bạn gọi:

~~~java
context.setAttributeValues(
        "telephoneNumber",
        new String[] {"+84 28 9999 0000"}
);
~~~

thì bạn vừa mô tả tập giá trị mới **chỉ còn một số**. Số thứ hai có nguy cơ bị loại khỏi entry, dù form không hiển thị nó. Bởi vậy, **đừng chuyển một form chứa một phần dữ liệu thành yêu cầu replace toàn bộ thuộc tính đa trị**.

Để “thêm một số” hoặc “loại một số”, dùng API phản ánh mục đích, rồi kiểm tra `getModificationItems()` và trạng thái đọc lại. Trường hợp cạnh tranh với client khác phải được xử lý bằng chiến lược đồng thời phù hợp nếu mất cập nhật là vấn đề nghiêm trọng.

### 6.2. Khác biệt giữa tên attribute và giá trị attribute

`setAttributeValue("mail", value)` nhận **tên thuộc tính** và **giá trị**. Tên `mail` cần hợp schema/allowlist của ứng dụng; không nên cho client tự chọn tên trường bất kỳ.

Giá trị truyền trực tiếp cho API adapter không phải một đoạn LDAP search filter. Vì vậy, **không tự thêm dấu ngoặc của filter** hoặc escape filter-value để “làm sạch” email trước khi set. Tuy nhiên, ứng dụng vẫn phải validate format, độ dài, kiểu dữ liệu và quyền người gọi.

## 7. Đọc mảng ModificationItem để hiểu delta

Để học và debug, có thể kiểm tra mã thao tác được sinh trước khi gửi. Trong production, **không log giá trị thuộc tính nhạy cảm**.

~~~java
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;

ModificationItem[] items = context.getModificationItems();

for (ModificationItem item : items) {
    int operation = item.getModificationOp();
    String attributeId = item.getAttribute().getID();

    String operationName;
    switch (operation) {
        case DirContext.ADD_ATTRIBUTE:
            operationName = "ADD";
            break;
        case DirContext.REPLACE_ATTRIBUTE:
            operationName = "REPLACE";
            break;
        case DirContext.REMOVE_ATTRIBUTE:
            operationName = "REMOVE";
            break;
        default:
            operationName = "UNKNOWN";
    }

    System.out.println(operationName + " " + attributeId);
}
~~~

Đây là mã **minh họa trong ứng dụng thử nghiệm**. Việc in `operationName` và `attributeId` có thể hữu ích để quan sát cấu trúc; đừng log trực tiếp `item.getAttribute().toString()` khi thuộc tính có email, nhóm, thông tin xác thực hay dữ liệu cá nhân.

### 7.1. Chỉ nhìn số lượng ModificationItem có đủ không?

Không. Giả sử `getModificationItems()` có một phần tử, bạn vẫn cần biết:

- Phần tử thuộc attribute type nào?
- Là ADD, REPLACE hay REMOVE?
- Chứa giá trị cụ thể hay thao tác trên cả thuộc tính?
- Có tác động lên giá trị khác ngoài ý định ban đầu không?
- Có vi phạm schema, SINGLE-VALUE hoặc ACL không?

Với test tích hợp, **kiểm tra entry sau Modify** quan trọng hơn việc assert máy móc rằng mảng luôn có đúng một phần tử và một opcode cố định trong mọi phiên bản.

### 7.2. Phân biệt sửa một giá trị và thay toàn bộ tập

Ở JNDI, các mã thao tác có ý nghĩa:

| Mã | Ý nghĩa LDAP Modify thường gặp | Lưu ý |
| --- | --- | --- |
| `ADD_ATTRIBUTE` | Thêm attribute hoặc giá trị vào attribute đa trị | Có thể lỗi nếu trùng giá trị hoặc SINGLE-VALUE |
| `REPLACE_ATTRIBUTE` | Đặt tập giá trị mới cho thuộc tính | Các giá trị cũ không được giữ lại trừ khi nằm trong tập mới |
| `REMOVE_ATTRIBUTE` | Loại giá trị được chỉ định hoặc toàn bộ thuộc tính | Có thể lỗi nếu giá trị/thuộc tính không tồn tại |

`DirContextAdapter` tạo `ModificationItem` để biểu diễn **kết quả thay đổi trạng thái**, nhưng không thể tự biết ý định UI là “thêm” hay “ghi đè” nếu code chỉ cung cấp một tập giá trị mới. Vì vậy việc chọn đúng phương thức adapter **quan trọng hơn** dựa vào cơ chế diff để sửa một thiết kế dữ liệu thiếu thông tin.

## 8. Điểm dễ sai: thay đổi Attributes qua đường vòng

Khi đã có `DirContextOperations`, lập trình viên có thể muốn truy cập `getAttributes()` rồi sửa trực tiếp đối tượng JNDI:

~~~java
// Không nên dựa vào cách sửa này để đảm bảo adapter nhận biết delta:
context.getAttributes().put(
        new BasicAttribute("mail", "alice.new@example.org")
);
~~~

Vấn đề: cơ chế theo dõi thay đổi của adapter dựa trên **hợp đồng phương thức chỉnh sửa mà nó cung cấp**. Việc thao tác trực tiếp trên tập `Attributes` hoặc trên một `Attribute` lấy ra có thể **bỏ qua hoặc làm sai lệch** logic ghi nhận thay đổi, tùy chi tiết triển khai.

**Hãy dùng API adapter thay thế:**

~~~java
context.setAttributeValue("mail", "alice.new@example.org");
ModificationItem[] items = context.getModificationItems();
~~~

Không chỉnh sửa tập `Attributes` bên trong rồi giả định `getModificationItems()` nhất định biết tất cả các thay đổi.

### 8.1. Không trộn nhiều đường cập nhật trên cùng adapter

Ví dụ một luồng code vừa gọi `setAttributeValues(...)`, vừa sửa trực tiếp `BasicAttribute` trả về từ `getAttributes()` thì khó xác định đâu là trạng thái cuối được tracker nhìn thấy. Chọn một cách rõ ràng: **các setter/add/remove của adapter**, và kiểm tra delta trước khi gửi.

### 8.2. Adapter tạo từ entry mới khác adapter tra cứu từ server

Có hai loại tình huống cần phân biệt:

- **Tạo entry mới:** có thể dùng một `DirContextAdapter` mới, đặt các thuộc tính `objectClass`, `cn`, `sn` rồi gọi `ldapTemplate.bind(...)`. Đây là LDAP **Add**, không phải Modify một entry có baseline.
- **Sửa entry hiện có:** nên `lookupContext(dn)` để lấy trạng thái hiện tại, sau đó sửa qua adapter và gọi `modifyAttributes(...)`.

Đừng tạo adapter rỗng, chỉ đặt `mail` rồi tưởng rằng nó biết trước những giá trị còn lại của entry tồn tại trên server. Thiếu trạng thái gốc có thể làm thay đổi không phản ánh ý định sửa một phần.

## 9. Ví dụ đa trị: giữ, thêm và loại một mô tả

Giả sử Alice có:

~~~ldif
description: active
description: training
telephoneNumber: +84 28 1111 2222
~~~

Yêu cầu: **bỏ `training` và thêm `engineering`**, giữ `active` và số điện thoại cũ.

~~~java
import javax.naming.Name;
import javax.naming.directory.ModificationItem;
import org.springframework.ldap.core.DirContextOperations;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

public void updateDescriptions(LdapTemplate template, String uid) {
    Name dn = LdapNameBuilder.newInstance("ou=people")
            .add("uid", uid)
            .build();

    DirContextOperations context = template.lookupContext(dn);

    context.removeAttributeValue("description", "training");
    context.addAttributeValue("description", "engineering");

    ModificationItem[] changes = context.getModificationItems();
    if (changes.length == 0) {
        return;
    }

    template.modifyAttributes(context);
}
~~~

Trong bài thực hành, xác nhận dữ liệu ban đầu có đúng `description: training`. Nếu không, phiên bản adapter/server và chính sách thay đổi có thể xử lý giá trị vắng mặt khác nhau. Không nên suy rằng xóa một giá trị không tồn tại luôn thành công mà không phát sinh lỗi.

Sau khi cập nhật thành công, **kết quả nghiệp vụ mong đợi** là:

~~~ldif
description: active
description: engineering
telephoneNumber: +84 28 1111 2222
~~~

Lưu ý rằng **giá trị của attribute đa trị không có thứ tự nghiệp vụ đảm bảo**. Khi test hãy so sánh tập giá trị, không dựa vào vị trí phần tử đầu tiên.

### 9.1. Readback để kiểm tra dữ liệu sau Modify

Có thể lookup lại entry (bằng tài khoản có quyền đọc phù hợp), lấy toàn bộ giá trị `description` và đối chiếu với tập mong đợi:

~~~java
import java.util.HashSet;
import java.util.Set;
import javax.naming.NamingEnumeration;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;
import org.springframework.ldap.core.AttributesMapper;

Set<String> descriptions = template.lookup(
        dn,
        (AttributesMapper<Set<String>>) attrs -> {
            Set<String> result = new HashSet<>();
            Attribute description = attrs.get("description");

            if (description == null) {
                return result;
            }

            NamingEnumeration<?> values = description.getAll();
            try {
                while (values.hasMore()) {
                    result.add(String.valueOf(values.next()));
                }
            } finally {
                values.close();
            }

            return result;
        }
);
~~~

Đây là đoạn trong phương thức đã có `template` và `dn`. Khi dữ liệu thuộc tính có thể là `byte[]`, cần mapper phù hợp; cách chuyển sang chuỗi chỉ áp dụng cho các giá trị văn bản trong ví dụ. Cũng không thể kết luận một giá trị **không tồn tại ở server** chỉ từ lookup bị ACL che.

## 10. Adapter và ModificationItem so với thao tác JNDI thủ công

Cả hai cách đều tạo yêu cầu Modify đối với **một DN** nhưng khác trách nhiệm lập trình viên.

### 10.1. Tự tạo ModificationItem

~~~java
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;

ModificationItem[] manual = {
    new ModificationItem(
            DirContext.REPLACE_ATTRIBUTE,
            new BasicAttribute("mail", "alice.new@example.org")
    )
};

ldapTemplate.modifyAttributes(dn, manual);
~~~

Lợi ích: mã biểu diễn **chính xác ý định Modify** khi update đơn giản, không cần lookup chỉ để dựng delta. Hạn chế: nếu code tự tạo nhiều thay đổi phụ thuộc trạng thái hiện tại, cần xử lý thủ công điều kiện tồn tại và thuộc tính đa trị.

### 10.2. Đọc entry, sửa adapter, lấy delta

~~~java
DirContextOperations context = ldapTemplate.lookupContext(dn);
context.setAttributeValue("mail", "alice.new@example.org");

ModificationItem[] calculated = context.getModificationItems();
ldapTemplate.modifyAttributes(context);
~~~

Lợi ích: hữu ích khi UI chỉnh sửa một đối tượng phức tạp, cần giữ trạng thái cũ và so sánh với dữ liệu mới. Hạn chế: cần lookup trước, có thể gặp **race condition** nếu LDAP entry thay đổi sau khi được đọc; adapter không thay thế cơ chế đồng bộ phiên bản.

| Tiêu chí | ModificationItem thủ công | DirContextAdapter tự tính delta |
| --- | --- | --- |
| Điều kiện có sẵn entry gốc | Không nhất thiết cần lookup | Thường lookup để có baseline |
| Kiểm soát opcode | Trực tiếp chọn ADD/REPLACE/REMOVE | Xem `getModificationItems()` sau các thao tác adapter |
| Update nhiều field trên form | Phải tạo nhiều item có điều kiện | Có thể tập trung sửa trạng thái trên context |
| Tránh ghi đè đa trị | Phụ thuộc cách xây item | Vẫn phụ thuộc phương thức set/add/remove được chọn |
| Truyền qua Spring LDAP | `modifyAttributes(dn, items)` | `modifyAttributes(context)` |
| Xử lý ACL, schema, xung đột | Server quyết định | **Server vẫn quyết định** |

Không nên xem adapter là lựa chọn luôn tốt hơn manual API. Chọn hướng phù hợp số trường, điều kiện dữ liệu và yêu cầu đồng thời của ứng dụng.

## 11. Một LDAP Modify có tính nguyên tử nhưng lookup + modify không tự là transaction

Theo ngữ nghĩa LDAP, danh sách thay đổi trong **một Modify request trên một entry** được xử lý theo thứ tự và nguyên tử: nếu một thay đổi không hợp lệ, server không được để entry ở trạng thái chỉ áp dụng một phần của request đó.

Ví dụ:

~~~text
Một request:
- Replace mail
- Add telephoneNumber
- Remove description=training

Nếu tất cả hợp lệ: áp dụng cả ba.
Nếu một phần không hợp lệ: request phải thất bại như một thao tác nguyên tử.
~~~

Tuy nhiên:

~~~text
lookupContext(dn)          <-- đọc ở thời điểm T1
setAttributeValue(...)     <-- đổi adapter tại client
modifyAttributes(context)  <-- gửi Modify tại thời điểm T2
~~~

Giữa **T1** và **T2**, một client khác có thể sửa entry đó. Adapter thường tính delta so với baseline T1, nhưng **không đảm bảo tránh mất cập nhật** khi có cập nhật đồng thời, đặc biệt với các phép thay toàn bộ tập giá trị.

### 11.1. Đặt chiến lược concurrency theo nghiệp vụ

Các lựa chọn đáng cân nhắc:

- Dùng các thao tác thêm/loại giá trị nhỏ thay vì replace cả attribute đa trị khi phù hợp.
- Đọc lại dữ liệu và kiểm tra bất biến nghiệp vụ trước/sau khi gửi.
- Dùng LDAP assertion control hoặc cơ chế kiểm soát phiên bản mà server hỗ trợ nếu cần đảm bảo điều kiện đồng thời thực sự.
- Tránh giả định một chuỗi thao tác với nhiều entry được rollback cùng nhau.
- Nếu kết nối đứt sau khi gửi Modify, **đọc lại trạng thái trước khi tự retry**, vì server có thể đã áp dụng thay đổi nhưng client chưa nhận response.

Không nên chạy hai cập nhật đồng thời trên cùng entry thử nghiệm rồi lấy kết quả một lần làm bằng chứng thuật toán delta luôn an toàn.

## 12. Schema và quyền truy cập: adapter không bỏ qua LDAP server

Một mảng `ModificationItem[]` hợp lệ về cấu trúc Java vẫn có thể bị LDAP server từ chối.

| Mã LDAP phổ biến | Tên | Tình huống cần xem |
| --- | --- | --- |
| **16** | `noSuchAttribute` | Xóa giá trị/thuộc tính không tồn tại |
| **17** | `undefinedAttributeType` | Attribute type chưa được schema định nghĩa |
| **19** | `constraintViolation` | Vi phạm ràng buộc, ví dụ thuộc tính đơn trị |
| **20** | `attributeOrValueExists` | Thêm giá trị trùng |
| **21** | `invalidAttributeSyntax` | Giá trị sai syntax |
| **32** | `noSuchObject` | DN đích/base không tồn tại hoặc không được hiển thị |
| **50** | `insufficientAccessRights` | Bind identity thiếu quyền sửa |
| **53** | `unwillingToPerform` | Server từ chối theo chính sách |
| **65** | `objectClassViolation` | Thao tác làm entry vi phạm MUST/MAY/objectClass |
| **67** | `notAllowedOnRDN` | Sửa giá trị RDN theo cách không được phép |

Thông báo và mã thực tế phụ thuộc LDAP server và chính sách bảo mật. Một số máy chủ che chi tiết quyền truy cập; không nên coi mọi `noSuchObject` là DN thật sự không tồn tại.

### 12.1. Cần phân biệt lỗi adapter với lỗi server

- **Không có ModificationItem:** có thể không có thay đổi được tracker nhận biết; không tự suy ra “server đã cập nhật”.
- **Adapter phát sinh exception khi sửa trạng thái:** có thể sai dữ liệu/kiểu, null hoặc điều kiện ở tầng Java.
- **Modify bị server từ chối:** có thể do ACL, schema, attribute value, DN hoặc chính sách server.
- **Lỗi TLS/bind/timeout:** là lỗi hạ tầng; không có cơ sở kết luận giá trị đã/không được cập nhật nếu mất response sau khi gửi yêu cầu.

Spring LDAP chuyển nhiều ngoại lệ JNDI thành các ngoại lệ thuộc hệ Spring LDAP. Hãy phân loại để service/API có phản hồi phù hợp, tránh bắt mọi lỗi rồi trả thành công hoặc trả “không tìm thấy”.

### 12.2. Quyền tối thiểu

`ContextSource.getReadWriteContext()` không tự cấp quyền ghi; quyền phụ thuộc bind DN và ACL ở LDAP server. Ứng dụng chỉ cần tra cứu có thể dùng tài khoản reader. Chức năng cập nhật nên dùng tài khoản editor chỉ được sửa **đúng OU và đúng thuộc tính** nghiệp vụ cho phép.

Một endpoint cho phép client chọn tùy ý attribute name rồi gọi `setAttributeValue(name, value)` là thiết kế rủi ro. Cần allowlist rõ ràng, kiểm soát quyền người dùng và schema, tránh mở khả năng sửa `objectClass`, thuộc tính nhạy cảm hoặc dữ liệu nhóm mà không có phê duyệt.

## 13. Kiểm thử cách adapter sinh ModificationItem

Có hai mức kiểm thử: **đơn vị** để kiểm tra logic của adapter/bộ dựng dữ liệu và **tích hợp** để chứng minh LDAP server thực thi cập nhật.

### 13.1. Một bài test tích hợp đầy đủ

Giả sử dự án có một bean `LdapTemplate` trỏ đến LDAP server thử nghiệm và entry `uid=training-01,ou=people,...` đã được tạo hợp schema:

~~~java
import javax.naming.Name;
import javax.naming.directory.ModificationItem;

import org.junit.jupiter.api.Test;
import org.springframework.ldap.core.DirContextOperations;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

import static org.junit.jupiter.api.Assertions.*;

class AdapterModificationIntegrationTest {

    private final LdapTemplate template;

    // Test fixture/Spring Test của dự án cung cấp template.
    AdapterModificationIntegrationTest(LdapTemplate template) {
        this.template = template;
    }

    @Test
    void updatesMailThroughAdapter() {
        Name dn = LdapNameBuilder.newInstance("ou=people")
                .add("uid", "training-01")
                .build();

        DirContextOperations context = template.lookupContext(dn);

        context.setAttributeValue(
                "mail", "training-01-new@example.org");

        ModificationItem[] items = context.getModificationItems();
        assertTrue(items.length > 0);

        template.modifyAttributes(context);

        DirContextOperations after = template.lookupContext(dn);
        assertEquals(
                "training-01-new@example.org",
                after.getStringAttribute("mail")
        );
    }
}
~~~

Đây là **khung test**; cần test fixture/Spring Test cung cấp `LdapTemplate` và LDAP server thực sự, đồng thời khởi tạo/dọn entry dữ liệu giả. Đừng cho rằng constructor JUnit trong ví dụ tự được inject nếu chưa có cấu hình kiểm thử tương ứng.

Kiểm thử trên tập dữ liệu ban đầu phải biết rõ giá trị `mail` **khác** giá trị muốn set, nếu không `items.length > 0` có thể không phản ánh điều kiện thử. Nên tạo giá trị ban đầu cố định hoặc reset entry trước mỗi case.

### 13.2. Các tình huống cần kiểm chứng

| Tình huống | Đầu vào | Kết quả kiểm tra |
| --- | --- | --- |
| Không sửa gì | Lookup, gọi ngay `getModificationItems()` | Không có delta cần gửi |
| Thay mail | Mail cũ khác mail mới | Có thay đổi liên quan mail; readback mail mới |
| Set lại giá trị cũ | Gán cùng mail | Quan sát no-op/delta theo phiên bản; không suy từ tên setter |
| Thêm description mới | Ban đầu không có description | Sau Modify entry chứa giá trị mới |
| Thêm một giá trị đa trị | Có `active`, thêm `training` | Giữ giá trị cũ và thêm giá trị mới |
| Loại một giá trị đa trị | Có `active` và `training` | Bỏ training, giữ active |
| Thay cả tập giá trị | Đặt hai giá trị thành một | Xác minh chính xác tập giá trị sau |
| Thiếu quyền ghi | Bind bằng reader | Server từ chối Modify |
| Sai schema | Xóa thuộc tính MUST | Server từ chối; entry không bị hỏng |
| Sai DN/base | Entry không tồn tại | Lỗi DN phù hợp, không giả là kết quả search rỗng |
| Kết nối đứt sau gửi | Gián đoạn mạng trong test | Đọc lại trạng thái trước khi retry |
| Dùng API Attributes trực tiếp | Sửa qua `getAttributes()` | So sánh tracking với setter, xác minh tránh cách ngoài hợp đồng |

### 13.3. Kiểm thử không phụ thuộc số lượng opcode cụ thể

Một test chỉ khẳng định `items[0].getModificationOp() == DirContext.REPLACE_ATTRIBUTE` có thể gắn chặt vào thuật toán sinh delta của một phiên bản thư viện. Với bài toán nghiệp vụ, ưu tiên kiểm tra:

- Thuộc tính nào thực sự được thay đổi.
- Những thuộc tính không liên quan còn giữ nguyên.
- Giá trị đa trị được bảo toàn hoặc loại bỏ **đúng như yêu cầu**.
- LDAP server có phản hồi thành công hay lỗi hợp lệ.
- Kết quả sau cập nhật được đọc lại đúng.

Có thể thêm test cụ thể về opcode nếu hệ thống cần hợp đồng đầu ra của `getModificationItems()` và đã cố định phiên bản Spring LDAP; khi đó test làm rõ rủi ro khi nâng cấp.

## 14. Thực hành: quan sát delta rồi cập nhật entry thử nghiệm

**Bối cảnh:** một trang hồ sơ cho phép sửa email và tập ghi chú `description`, nhưng phải giữ nguyên `uid`, `cn` và số điện thoại của người dùng.

1. Tạo entry `training-01` hợp schema trong một OU thử nghiệm; chuẩn bị `mail` và hai giá trị `description`.
2. Cấu hình `LdapContextSource` với LDAPS đã xác minh chứng chỉ, `ContextSource.base` và tài khoản editor chỉ có quyền sửa trong OU thử nghiệm.
3. Dùng `ldapTemplate.lookupContext(dn)` để đọc entry thành `DirContextOperations`.
4. Gọi `getModificationItems()` **trước khi sửa**; ghi nhận trạng thái không có delta cần gửi.
5. Gọi `setAttributeValue("mail", ...)` với email mới; đọc lại mảng ModificationItem và chỉ log **tên thuộc tính + mã thao tác**, không log email.
6. Bổ sung một giá trị `description`, sau đó bỏ một giá trị cũ qua API adapter. Quan sát thay đổi ở mảng và giải thích vì sao không nên dựa vào đúng một opcode nếu chưa kiểm chứng.
7. Gọi `ldapTemplate.modifyAttributes(context)` **một lần**; lookup lại để xác minh mail mới, ghi chú đúng và các thuộc tính không liên quan không đổi.
8. Thử `setAttributeValues` thay toàn bộ `description`; xác định rủi ro mất một giá trị mà form không hiển thị.
9. Dùng reader không có quyền ghi thử cùng thao tác; xác minh server từ chối và entry không thay đổi.
10. Thử sửa một thuộc tính bắt buộc sai schema trong directory test, xác nhận lỗi và tính nguyên tử của một Modify request.
11. Mô phỏng một cập nhật khác xảy ra giữa lookup và modify; giải thích cách tránh mất cập nhật và vì sao adapter không tự làm optimistic locking.
12. Thu hồi/dọn dữ liệu kiểm thử, bảo đảm không để lộ credentials, DN nhạy cảm hoặc toàn bộ entry trong log.

### Câu hỏi tự kiểm tra

1. `lookupContext(dn)` khác một adapter mới dùng để tạo entry ra sao?
2. Gọi `setAttributeValue` đã làm LDAP server đổi dữ liệu chưa?
3. `getModificationItems()` trả về gì và tại sao phải quan sát nó với dữ liệu gốc?
4. Có thể suy rằng `addAttributeValue` luôn tạo đúng một `ADD_ATTRIBUTE` không?
5. Vì sao sửa `getAttributes()` trực tiếp có thể khiến tracker không nhận biết đúng delta?
6. Khi nào `setAttributeValues` gây nguy cơ làm mất giá trị đa trị?
7. Vì sao không nên gọi cả hai overload `modifyAttributes` liên tiếp cho cùng đợt cập nhật?
8. Nếu một LDAP Modify request là nguyên tử, tại sao lookup + modify vẫn có nguy cơ race condition?
9. Đặc điểm nào thuộc adapter ở client, đặc điểm nào do schema/ACL trên LDAP server quyết định?
10. Tại sao cần đọc lại trạng thái entry khi kết nối bị timeout sau khi gửi yêu cầu ghi?

## 15. Tổng kết

**`DirContextAdapter` và `DirContextOperations`** giúp thao tác với thuộc tính entry trong Spring LDAP như với một đối tượng Java, đồng thời cung cấp cơ chế sinh **`ModificationItem[]`** từ những thay đổi mà adapter theo dõi. Quy trình điển hình là **`lookupContext(dn)` → sửa bằng `setAttributeValue`/`setAttributeValues`/`addAttributeValue`/`removeAttributeValue` → quan sát `getModificationItems()` → `modifyAttributes(context)`**. Không tự suy đoán mã ADD/REPLACE/REMOVE chỉ từ tên setter và không bypass tracking bằng cách sửa `Attributes` trực tiếp. Adapter không thay thế kiểm tra DN, schema, ACL, quyền tối thiểu, TLS, xử lý đa trị hay chiến lược concurrency. Kiểm thử cả thay đổi dự kiến và **trạng thái thực tế sau Modify** là cách bảo đảm cập nhật LDAP chính xác, an toàn và dễ bảo trì.
