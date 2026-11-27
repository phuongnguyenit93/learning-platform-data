# Chuyển đổi DN và attribute ở một lớp rõ ràng

## 1. Bối cảnh và mục tiêu

Trong ứng dụng sử dụng **Spring LDAP**, dữ liệu của directory được tổ chức theo **Distinguished Name (DN)**, **Relative Distinguished Name (RDN)**, **objectClass** và các **attribute**. Ví dụ một nhân viên có thể nằm ở DN:

~~~text
uid=lan,ou=people,dc=example,dc=org

objectClass: inetOrgPerson
uid: lan
cn: Nguyễn Lan
sn: Nguyễn
mail: lan@example.org
entryUUID: 7cf6b3cd-7d9e-4ae7-a938-8ed53b0b10d3
~~~

Ứng dụng lại cần các khái niệm như **DirectoryPerson**, **DirectorySubject**, tên hiển thị và email. Những lớp thực hiện nghiệp vụ không nên phải biết **ou=people**, tên attribute **cn**, cách đọc **javax.naming.directory.Attributes**, hoặc cách xây dựng LDAP filter.

Một lỗi thiết kế phổ biến là chuyển đổi từng phần ở nhiều nơi: REST controller ghép DN, service đọc **uid**, mapper của ODM xử lý **cn**, một tác vụ đồng bộ riêng xử lý **mail**. Khi schema hoặc vị trí OU thay đổi, những quy tắc ánh xạ này dễ lệch nhau. Giải pháp là **tập trung việc chuyển đổi DN và attribute trong một lớp (hoặc một nhóm lớp nhỏ cùng trách nhiệm) ở tầng LDAP adapter**.

Chủ đề này nằm trong chương **Thiết kế ứng dụng**. Phạm vi là Spring LDAP: có thể dùng **LdapTemplate**, **LdapClient** hoặc ODM để truy cập directory; kết nối thông qua **ContextSource** và áp dụng TLS, xử lý lỗi, pooling, kiểm thử an toàn. Những công nghệ đó phục vụ việc đọc/ghi thư mục; mô hình nghiệp vụ vẫn nên nói bằng ngôn ngữ của ứng dụng.

## 2. Ranh giới chuyển đổi nằm ở đâu?

~~~mermaid
flowchart LR
    UC["Use case / Domain service"]
    PORT["DirectoryPersonPort\nJava types thuộc ứng dụng"]
    ADAPTER["SpringLdapPersonAdapter"]
    MAPPER["LdapPersonMapper\nDN + attributes → Java model"]
    TPL["LdapTemplate / LdapClient"]
    CS["ContextSource + TLS"]
    DIRECTORY[("LDAP directory")]

    UC --> PORT
    ADAPTER -. "implements" .-> PORT
    ADAPTER --> MAPPER
    ADAPTER --> TPL
    TPL --> CS --> DIRECTORY
~~~

Ba trách nhiệm cần phân biệt:

| Lớp | Trách nhiệm | Kiểu dữ liệu nên thấy |
| --- | --- | --- |
| Domain / application | Kiểm tra quy tắc và điều phối use case | **DirectoryPerson**, **DirectorySubject**, **Optional**, exception ứng dụng |
| LDAP adapter | Tạo query, tìm entry, gọi sửa/xóa, kiểm soát phạm vi tìm kiếm, phân loại lỗi LDAP | **LdapTemplate**, **LdapQuery**, **Name**, **ModificationItem** |
| LDAP mapper | Chuyển **DN + attribute** sang model nội bộ; kiểm tra dữ liệu bắt buộc; chuyển kiểu đa trị/nhị phân | **DirContextOperations**, **Attributes**, các kiểu DTO miền ứng dụng |

Một thiết kế tốt cho phép thay **uid** bằng **sAMAccountName** hoặc đổi từ OpenLDAP sang Active Directory mà phần lớn thay đổi nằm ở adapter/mapper. Hợp đồng ứng dụng nên trả **DirectorySubject**, không trả **DirContextOperations** hoặc bắt use case tự xử lý **Name**.

**Lưu ý:** tập trung mapping không có nghĩa tạo một “super mapper” đọc mọi schema và mọi loại entry. Có thể có **LdapPersonMapper**, **LdapGroupMapper** và **LdapOrganizationUnitMapper** riêng, mỗi mapper có cùng quy ước về tên tương đối, null, lỗi và kiểm thử.

## 3. DN, RDN, search base và base DN

**DN** định danh vị trí của entry trong Directory Information Tree (DIT). DN gồm các RDN, từ entry đến gốc. Với ví dụ:

~~~text
DN đầy đủ:     uid=lan,ou=people,dc=example,dc=org
RDN của entry: uid=lan
Search base:   ou=people
Context base:  dc=example,dc=org
~~~

Nếu **ContextSource** đã được cấu hình **base=dc=example,dc=org**, các DN sử dụng trong nhiều thao tác **LdapTemplate** là **tương đối với context base**:

~~~text
uid=lan,ou=people
~~~

Không được tự động gắn **dc=example,dc=org** lần thứ hai vào một DN đã được tính theo context. Tương tự, **LdapQueryBuilder.query().base("ou=people")** chỉ định nhánh tìm kiếm tương đối với base đã cấu hình. Vị trí entry thực tế, search base và relative DN trả về phải được xác nhận bằng integration test, nhất là khi ứng dụng có nhiều **ContextSource**.

Một phần mềm có thể có nhiều directory source hoặc dùng context base rỗng. Bởi vậy cần định nghĩa rõ tại ranh giới adapter:

- DN dùng để gọi các phương thức trên **LdapTemplate** thuộc phạm vi base nào?
- DN nhận từ kết quả tìm kiếm là tên tương đối hay tên đầy đủ?
- Khi tạo entry, RDN mới được gắn với OU ra sao?
- Khi đổi OU hoặc rename entry, các tham chiếu theo DN cũ được cập nhật thế nào?

**Không tách DN bằng dấu phẩy** để lấy RDN hoặc OU. Giá trị RDN có thể chứa dấu phẩy được escape, dấu bằng, khoảng trắng và thậm chí RDN đa trị. Sử dụng API **javax.naming.Name**, **javax.naming.ldap.LdapName**, **javax.naming.ldap.Rdn** hoặc **LdapNameBuilder**.

Ví dụ tạo tên tương đối an toàn:

~~~java
import javax.naming.Name;
import org.springframework.ldap.support.LdapNameBuilder;

String uid = "lan,project"; // Ví dụ có dấu phẩy trong giá trị.
Name relativeDn = LdapNameBuilder.newInstance()
        .add("ou", "people")
        .add("uid", uid)
        .build();

// RDN uid được escape đúng, không tạo thêm nhánh LDAP ngoài ý định.
~~~

Khi dùng **entry.getDn()** từ **DirContextOperations**, nên giữ đối tượng **Name** bên trong adapter trong lúc xử lý thay vì tự ghép lại DN từ **uid**. Entry có thể được đổi tên, chuyển OU hoặc dùng RDN khác với thuộc tính đăng nhập.

### DN có phải định danh nghiệp vụ bất biến?

Không nên mặc định như vậy. Đổi OU và rename làm DN đổi. Với dữ liệu cần liên kết dài hạn, ưu tiên một định danh ổn định do directory cung cấp, ví dụ **entryUUID** trong nhiều hệ thống OpenLDAP hoặc **objectGUID** trong Active Directory. Cần gắn thêm **directory source ID** để tránh va chạm giữa các nguồn. Việc xóa/tạo lại hoặc migration directory vẫn có thể thay định danh, nên phải có chính sách đối soát.

## 4. Attribute không phải lúc nào cũng là một chuỗi

LDAP schema quy định tên, cú pháp, số lượng giá trị, cách so sánh, điều kiện bắt buộc và quyền truy cập attribute. Trong Java, các giá trị có thể xuất hiện qua **DirContextOperations**, **Attributes/Attribute** và các kiểu dữ liệu khác nhau.

| Kiểu dữ liệu LDAP | Ví dụ | Quy tắc mapping |
| --- | --- | --- |
| Một chuỗi | **uid**, **cn**, **mail** theo schema được chọn | Chuẩn hóa khoảng trắng theo yêu cầu nghiệp vụ; kiểm tra thuộc tính bắt buộc |
| Nhiều giá trị | **member**, **uniqueMember**, đôi khi **memberOf** | Đọc collection, không phụ thuộc thứ tự LDAP trả về |
| DN nằm trong attribute | **member: uid=lan,ou=people,...** | Parse thành **LdapName** khi cần thao tác cấu trúc; không tách bằng dấu phẩy |
| Nhị phân | **objectGUID**, chứng chỉ, ảnh | Lấy **byte[]** và mã hóa rõ ràng; không ép sang String tùy tiện |
| Operational attribute | **entryUUID**, **modifyTimestamp** | Có thể cần yêu cầu cụ thể trong danh sách attribute và quyền đọc |
| Thiếu attribute | **mail** chưa có giá trị | Phân biệt optional và dữ liệu không hợp lệ |
| Attribute có tên khác theo server | **uid** so với **sAMAccountName** | Tập trung quy tắc chọn/mapping ở adapter |

Đừng cho rằng mọi attribute đều có một giá trị, hoặc **memberOf** xuất hiện sẵn trên tất cả LDAP server. Một số schema lưu group membership ở entry nhóm, không ở entry người dùng; nested group lại đòi truy vấn bổ sung và chính sách riêng.

Một mapper cần nhất quán về ba trường hợp: **attribute có giá trị**, **attribute không tồn tại** và **attribute hiện diện nhưng sai kiểu/sai schema**. Không nên biến tất cả thành chuỗi rỗng vì sẽ che giấu vấn đề dữ liệu.

## 5. Định nghĩa hợp đồng ở phía ứng dụng

Ví dụ minh họa sử dụng Java 17 và Spring LDAP. Các khai báo **public** đặt trong file Java riêng đúng theo package tương ứng.

**DirectorySubject** là khóa tham chiếu tách biệt với DN:

~~~java
// domain/DirectorySubject.java
package com.example.identity.domain;

import java.util.Objects;

public record DirectorySubject(String sourceId, String objectId) {
    public DirectorySubject {
        Objects.requireNonNull(sourceId);
        Objects.requireNonNull(objectId);
        if (sourceId.isBlank() || objectId.isBlank()) {
            throw new IllegalArgumentException("DirectorySubject không hợp lệ");
        }
    }
}
~~~

**DirectoryPerson** biểu diễn dữ liệu ứng dụng cần:

~~~java
// domain/DirectoryPerson.java
package com.example.identity.domain;

public record DirectoryPerson(
        DirectorySubject subject,
        String login,
        String displayName,
        String email
) {}
~~~

**Port** khai báo thao tác, không cho tầng ứng dụng nhìn thấy DN:

~~~java
// application/DirectoryPersonPort.java
package com.example.identity.application;

import com.example.identity.domain.DirectoryPerson;
import java.util.Optional;

public interface DirectoryPersonPort {
    Optional<DirectoryPerson> findByLogin(String login);
    void replaceEmail(String login, String email);
}
~~~

Ví dụ dùng **login** cho tra cứu theo yêu cầu người dùng, nhưng sau khi tìm entry, adapter giữ **DN được trả về** để sửa đúng entry đó. Một API ghi nghiêm ngặt hơn có thể sử dụng **DirectorySubject** thay login nhằm tránh rủi ro login bị đổi/tái sử dụng giữa hai bước.

## 6. Một mapper chịu trách nhiệm chuyển DN và thuộc tính

Giả sử directory là OpenLDAP với schema **inetOrgPerson**, search base **ou=people** và operational attribute **entryUUID**. Ta tạo một kiểu **LocatedPerson** chỉ dùng nội bộ hạ tầng, giữ **Name** để thao tác entry mà không phơi ra port.

~~~java
// infrastructure/ldap/LocatedPerson.java
package com.example.identity.infrastructure.ldap;

import com.example.identity.domain.DirectoryPerson;
import javax.naming.Name;

record LocatedPerson(Name relativeDn, DirectoryPerson person) {}
~~~

Mapper đọc thuộc tính, phát hiện entry thiếu trường bắt buộc và xây dựng **DirectoryPerson**:

~~~java
// infrastructure/ldap/LdapPersonMapper.java
package com.example.identity.infrastructure.ldap;

import com.example.identity.domain.DirectoryPerson;
import com.example.identity.domain.DirectorySubject;
import javax.naming.Name;
import org.springframework.ldap.core.ContextMapper;
import org.springframework.ldap.core.DirContextOperations;
import org.springframework.stereotype.Component;

@Component
public final class LdapPersonMapper implements ContextMapper<LocatedPerson> {
    private static final String SOURCE_ID = "corp-openldap";

    @Override
    public LocatedPerson mapFromContext(Object context) {
        DirContextOperations entry = (DirContextOperations) context;

        String uid = required(entry, "uid");
        String entryUuid = required(entry, "entryUUID");
        String displayName = optional(entry, "cn");
        String email = optional(entry, "mail");

        DirectoryPerson person = new DirectoryPerson(
                new DirectorySubject(SOURCE_ID, entryUuid),
                uid, displayName, email);

        Name dn = (Name) entry.getDn().clone();
        return new LocatedPerson(dn, person);
    }

    private static String required(
            DirContextOperations entry, String attributeName) {
        String value = entry.getStringAttribute(attributeName);
        if (value == null || value.isBlank()) {
            throw new InvalidDirectoryEntryException(
                    "Thiếu attribute bắt buộc: " + attributeName);
        }
        return value;
    }

    private static String optional(
            DirContextOperations entry, String attributeName) {
        String value = entry.getStringAttribute(attributeName);
        return value == null || value.isBlank() ? null : value;
    }
}
~~~

~~~java
// infrastructure/ldap/InvalidDirectoryEntryException.java
package com.example.identity.infrastructure.ldap;

public final class InvalidDirectoryEntryException
        extends RuntimeException {
    public InvalidDirectoryEntryException(String message) {
        super(message);
    }
}
~~~

Điểm quan trọng của mapper:

1. **Tên LDAP tập trung tại một chỗ:** **uid**, **cn**, **mail**, **entryUUID** chỉ được diễn giải theo schema trong adapter và mapper.
2. **Field bắt buộc được kiểm tra:** không trả một người dùng với subject ID trống chỉ vì directory trả response thiếu attribute.
3. **Field tùy chọn có trạng thái rõ:** ví dụ trả **null** cho displayName/email vắng mặt; có thể dùng một value object hoặc **Optional** tại lớp ánh xạ cao hơn nếu convention dự án yêu cầu.
4. **Không phụ thuộc DN để định danh domain:** **Name** nằm trong **LocatedPerson** package-private, còn **DirectoryPerson** chỉ mang khóa tham chiếu bền vững.
5. **Không lấy thứ tự và kiểu dữ liệu làm giả định:** mapper chuỗi này thích hợp cho attribute đơn trị; attribute đa trị/nhị phân cần mapper riêng.

Trong sản phẩm thật, **SOURCE_ID** nên đến từ cấu hình định danh **một directory cụ thể**, không nhất thiết hard-code. Khi ứng dụng đọc nhiều directory, mỗi adapter nhận ID từ cấu hình và dùng ID đó làm namespace cho khóa.

## 7. Adapter tạo truy vấn, mapper chuyển kết quả

Adapter Spring LDAP nhận **LdapTemplate** từ cấu hình **ContextSource**, dùng **LdapQueryBuilder** để tra cứu và gọi **LdapPersonMapper** cho phần chuyển đổi:

~~~java
// infrastructure/ldap/SpringLdapPersonAdapter.java
package com.example.identity.infrastructure.ldap;

import com.example.identity.application.DirectoryPersonPort;
import com.example.identity.domain.DirectoryPerson;
import java.util.List;
import java.util.NoSuchElementException;
import java.util.Optional;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;
import org.springframework.stereotype.Repository;

@Repository
public class SpringLdapPersonAdapter implements DirectoryPersonPort {
    private final LdapTemplate ldap;
    private final LdapPersonMapper mapper;

    public SpringLdapPersonAdapter(
            LdapTemplate ldap, LdapPersonMapper mapper) {
        this.ldap = ldap;
        this.mapper = mapper;
    }

    @Override
    public Optional<DirectoryPerson> findByLogin(String login) {
        return findEntry(login).map(LocatedPerson::person);
    }

    @Override
    public void replaceEmail(String login, String email) {
        if (email == null || email.isBlank()) {
            throw new IllegalArgumentException("Email không được rỗng");
        }
        // Kiểm tra quyền sửa email thuộc use case; ở đây chỉ ghi LDAP.
        LocatedPerson located = findEntry(login)
                .orElseThrow(() -> new NoSuchElementException(
                        "Không tìm thấy tài khoản để cập nhật"));

        ModificationItem[] changes = {
                new ModificationItem(
                        DirContext.REPLACE_ATTRIBUTE,
                        new BasicAttribute("mail", email))
        };
        ldap.modifyAttributes(located.relativeDn(), changes);
    }

    private Optional<LocatedPerson> findEntry(String login) {
        if (login == null || login.isBlank()) {
            throw new IllegalArgumentException("Login không được rỗng");
        }
        LdapQuery query = LdapQueryBuilder.query()
                .base("ou=people")
                .attributes("uid", "cn", "mail", "entryUUID")
                .where("uid").is(login);

        List<LocatedPerson> matches = ldap.search(query, mapper);
        if (matches.size() > 1) {
            throw new IllegalStateException(
                    "Nhiều LDAP entry khớp cùng một login");
        }
        return matches.stream().findFirst();
    }
}
~~~

**Luồng dữ liệu** tại ranh giới:

~~~mermaid
sequenceDiagram
    participant App as Application service
    participant Adapter as SpringLdapPersonAdapter
    participant LDAP as LDAP directory
    participant Mapper as LdapPersonMapper
    App->>Adapter: findByLogin("lan")
    Adapter->>LDAP: search base=ou=people, (uid=lan)
    LDAP-->>Adapter: entry DN + attributes
    Adapter->>Mapper: mapFromContext(entry)
    Mapper-->>Adapter: LocatedPerson
    Adapter-->>App: Optional<DirectoryPerson>
~~~

**Quan trọng:** phương thức **replaceEmail** thực hiện tìm-đọc-ghi trong các thao tác riêng, nên entry có thể bị rename/di chuyển hoặc nội dung thay đổi giữa hai bước. LDAP có thể trả lỗi entry không tồn tại ở bước ghi. Với cập nhật yêu cầu chống ghi đè, dùng cơ chế điều kiện/locking được directory hỗ trợ hoặc kiểm tra version phù hợp, không tự giả định có transaction xuyên hai request LDAP. Khi thao tác ghi theo danh tính ổn định, cân nhắc tra cứu DN mới theo subject ID hoặc xử lý conflict/race và retry một cách có kiểm soát.

Mã minh họa tập trung vào mapping. Trong triển khai thực tế cần phân loại exception Spring LDAP, giới hạn số kết quả tìm kiếm, đặt timeout và kiểm tra server schema; không nuốt lỗi kết nối thành **Optional.empty()**.

## 8. Phân biệt DN escaping và filter escaping

Hai loại đầu vào nhìn giống nhau nhưng có **ngữ pháp và quy tắc escaping khác nhau**:

| Ngữ cảnh | Ví dụ | API phù hợp |
| --- | --- | --- |
| Dựng DN/RDN | uid có dấu phẩy, dấu bằng, khoảng trắng | **LdapNameBuilder**, **LdapName**, **Rdn** |
| Dựng điều kiện tìm kiếm | Giá trị uid có dấu sao, ngoặc, backslash | **LdapQueryBuilder.where(...).is(value)** |
| Ghi attribute | Đặt giá trị **mail** vào entry | **ModificationItem**, **DirContextOperations** |
| Parse DN từ attribute nhóm | **member=uid=lan,...** | **new LdapName(value)** với xử lý lỗi cú pháp |

**Không làm như sau:**

~~~java
// Không an toàn: đầu vào từ người dùng được nối trực tiếp vào filter.
String filter = "(uid=" + login + ")";

// Sai về kiến trúc: lớp domain phải đoán cấu trúc DN.
String dn = "uid=" + login + ",ou=people,dc=example,dc=org";
~~~

**Làm như sau:**

~~~java
// Query builder escape giá trị cần tìm theo cú pháp LDAP filter.
LdapQuery query = LdapQueryBuilder.query()
        .base("ou=people")
        .where("uid").is(login);

// Name builder escape giá trị RDN theo cú pháp LDAP DN.
javax.naming.Name relativeDn = org.springframework.ldap.support
        .LdapNameBuilder.newInstance()
        .add("ou", "people")
        .add("uid", login)
        .build();
~~~

Tên attribute như **uid**, **mail**, search base và loại thao tác nên do ứng dụng cấu hình xác định trước; không để client tùy ý truyền tên thuộc tính hoặc raw filter. Việc escape giúp bảo vệ cú pháp, nhưng **không thay thế** chính sách giới hạn phạm vi tìm kiếm, kiểm tra quyền, rate limit hoặc ACL của LDAP server.

Khi cần so sánh DN, hãy dùng **Name/LdapName** thay vì so sánh hai chuỗi biểu diễn không chuẩn hóa. Kết quả so sánh vẫn phải tôn trọng matching rule và các yêu cầu schema/server cụ thể; so sánh cú pháp DN trong Java không tự quyết định hai entry là cùng một principal bất biến.

## 9. Xử lý đa trị và nhị phân tại cùng ranh giới

Mapper cho LDAP group hoặc các thuộc tính nhiều giá trị cần trả về một cấu trúc rõ ràng, thường là **Set** khi thứ tự không có nghĩa.

~~~java
import java.util.Arrays;
import java.util.Set;
import java.util.stream.Collectors;
import org.springframework.ldap.core.DirContextOperations;

static Set<String> groupDns(DirContextOperations entry) {
    // "memberOf" chỉ có trên các server/schema hỗ trợ thuộc tính này.
    String[] values = entry.getStringAttributes("memberOf");
    if (values == null) {
        return Set.of();
    }
    return Arrays.stream(values)
            .collect(Collectors.toUnmodifiableSet());
}
~~~

Khi cần kiểm tra cấu trúc mỗi DN của thành viên, parse từng chuỗi bằng **LdapName** và phân loại lỗi cú pháp. Không dùng **split(",")**. Nếu ứng dụng cần ánh xạ group thành role, hãy đặt quy tắc group→role tại **application policy** hoặc lớp chuyên trách về phân quyền; mapper chỉ chuyển và kiểm tra dữ liệu directory.

Với **objectGUID** trong Active Directory, attribute thường là nhị phân. Đừng gọi **String.valueOf(byte[])** hoặc giả định có thể chuyển byte thành UUID trực tiếp theo thứ tự byte chuẩn. Một cách lưu khóa opaque mà không suy diễn ý nghĩa byte là **Base64 URL-safe**, kèm source ID:

~~~java
import java.util.Base64;
import javax.naming.NamingException;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;

static String opaqueBinaryId(Attributes attributes, String name)
        throws NamingException {
    Attribute attribute = attributes.get(name);
    if (attribute == null || attribute.size() != 1
            || !(attribute.get() instanceof byte[] bytes)) {
        throw new IllegalArgumentException(
                "Attribute nhị phân không hợp lệ: " + name);
    }
    return Base64.getUrlEncoder()
            .withoutPadding()
            .encodeToString(bytes);
}
~~~

Một hệ thống muốn hiển thị **objectGUID** thành định dạng GUID chuẩn cần quy tắc diễn giải byte-order của Active Directory; đây là mapping khác với mã hóa opaque. Bất kể dùng cách nào, **định dạng lưu trữ phải ổn định theo thời gian** và được kiểm thử bằng mẫu nhị phân thật. Khi đọc ảnh hoặc certificate, nên cân nhắc kích thước dữ liệu và chỉ yêu cầu attribute đó trong query thực sự cần.

## 10. Chuyển đổi khi ghi: ngữ nghĩa thay thế, thêm và xóa

Chuyển từ mô hình ứng dụng sang LDAP không chỉ là đổi tên trường. **Schema** và loại cập nhật phải rõ ràng:

| Nhu cầu ứng dụng | LDAP operation thường dùng | Chú ý |
| --- | --- | --- |
| Đặt email mới | **REPLACE_ATTRIBUTE mail** | Email hợp lệ theo nghiệp vụ; kiểm tra ACL/schema |
| Thêm một thành viên vào group | **ADD_ATTRIBUTE member** | Kiểu thành viên có thể là DN, group schema quyết định |
| Gỡ một thành viên cụ thể | **REMOVE_ATTRIBUTE member** | Không xóa toàn bộ các thành viên |
| Xóa giá trị tùy chọn | Xóa attribute/giá trị theo operation phù hợp | Không coi **null**, chuỗi trống và xóa là giống nhau |
| Đổi tên hoặc chuyển OU | **rename** / modDN trên entry | DN thay đổi; kiểm tra quyền và các tham chiếu liên quan |

Một mapper ghi có thể nhận command ứng dụng và tạo tập **ModificationItem**, ví dụ **EmailChangeMapper** chỉ xử lý quy tắc chuyển **email→mail**; adapter chịu trách nhiệm thực hiện thao tác và xử lý lỗi.

~~~java
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;

static ModificationItem[] emailChanges(String newEmail) {
    if (newEmail == null || newEmail.isBlank()) {
        throw new IllegalArgumentException("Email không được rỗng");
    }
    return new ModificationItem[] {
        new ModificationItem(
            DirContext.REPLACE_ATTRIBUTE,
            new BasicAttribute("mail", newEmail))
    };
}
~~~

Nếu dùng **DirContextOperations** và **ldapTemplate.modifyAttributes(context)**, Spring LDAP có thể tính các thay đổi trên context; cần hiểu cách set/remove attribute và kiểm tra diff. Nếu dùng **ODM**, object mapping annotations và repository cũng phải nằm tại hạ tầng; kiểm tra hành vi với attribute đa trị, operational attribute và lifecycle của DN. Không để một field domain đổi tên tự động dẫn đến rename DN nếu nghiệp vụ không yêu cầu.

Với group có giá trị **member** là DN, cần dùng DN đúng dạng và phạm vi mà directory đòi hỏi (thường là DN đầy đủ đối với giá trị attribute) dù DN được truyền vào **LdapTemplate** khi thao tác entry có thể là tên tương đối. Đây là hai vai trò khác nhau của DN; không dùng một chuỗi DN chưa rõ phạm vi cho cả hai.

## 11. Chuyển lỗi LDAP thành lỗi ứng dụng có ý nghĩa

Mapping không nên che giấu dữ liệu hỏng và outage:

| Kết quả tại LDAP | Nghĩa ở cổng ứng dụng | Hướng xử lý |
| --- | --- | --- |
| Truy vấn hợp lệ nhưng không có entry | **Optional.empty()** | Use case quyết định 404 hoặc quy trình tạo mới |
| Có nhiều entry cho một login được kỳ vọng duy nhất | Lỗi tính duy nhất/dữ liệu | Báo lỗi, không tùy tiện chọn entry đầu tiên |
| Thiếu **entryUUID** khi ID đó là bắt buộc | Lỗi schema/permission/dữ liệu | Kiểm tra quyền đọc và ánh xạ |
| Timeout, kết nối gián đoạn | Directory unavailable | Retry/backoff có giới hạn; hiển thị lỗi tạm thời phù hợp |
| Bind thất bại, không đủ quyền sửa | Lỗi authentication/authorization hạ tầng | Kiểm tra principal/ACL; không giả thành “không có entry” |
| DN entry đã bị rename/xóa trước thao tác ghi | Conflict/not found tại thời điểm ghi | Đọc lại khi phù hợp hoặc báo xung đột |
| Attribute nhị phân sai kiểu | Lỗi mapping dữ liệu | Không dùng giá trị không xác định làm danh tính |

Ứng dụng có thể định nghĩa exception trung lập như **DirectoryUnavailableException**, **DirectoryDataException** và **DirectoryPermissionException** rồi chuyển exception của **org.springframework.ldap** tại adapter. Không bắt mọi **RuntimeException** và trả **Optional.empty()**; lỗi lập trình, sai schema và lỗi mạng phải còn được quan sát.

Khi ghi log, tránh đưa đầy đủ DN, filter chứa dữ liệu nhạy cảm, password hoặc giá trị nhị phân vào thông báo phổ biến. Ghi mã lỗi, loại thao tác, mã directory source và correlation ID ở mức cần thiết. Các lỗi mapping có thể xuất hiện do ACL không cho trả attribute mặc dù entry vẫn tồn tại; vì thế không tự kết luận là account bị xóa.

## 12. Cấu hình ContextSource, TLS và pooling

Mapper không được tự mở kết nối. Tầng hạ tầng cấu hình **ContextSource** và tạo **LdapTemplate/LdapClient** tương ứng. Ví dụ Spring Boot:

~~~yaml
spring:
  ldap:
    urls:
      - ldaps://ldap.example.org:636
    base: dc=example,dc=org
    # username/password lấy từ cấu hình secret của môi trường chạy
~~~

- **Base DN** do cấu hình quyết định; mapper dùng **Name** hoặc model nội bộ, còn adapter chịu trách nhiệm chọn search base tương đối.
- Dùng **LDAPS** hoặc **StartTLS** được cấu hình đúng, truststore hợp lệ và xác minh certificate/hostname; không tắt kiểm tra chứng chỉ để chạy thử trong sản phẩm.
- Đặt connect/read timeout, giới hạn kích thước và phạm vi truy vấn; xử lý trang kết quả hoặc server limit khi tìm danh sách lớn.
- **Pooling** phải phù hợp với TLS/StartTLS và trạng thái bind. Không vô tình dùng lại kết nối đã xác thực bằng principal khác; đánh giá cơ chế pool và lifecycle trên thư viện/server cụ thể.
- Giữ credential bên ngoài mã nguồn, cấp tài khoản dịch vụ quyền tối thiểu. Không yêu cầu/đọc **userPassword** để xây domain model.

Việc bật TLS, pooling hoặc chuyển từ **LdapTemplate** sang **LdapClient** không nên khiến domain đổi kiểu dữ liệu. Khi thư mục dùng schema khác, cập nhật adapter/mapper và các integration test của ranh giới đó.

## 13. Kiểm thử trực tiếp lớp chuyển đổi

### Unit test mapper

Vì mapper là một lớp riêng, có thể tạo **DirContextAdapter** với **Attributes** giả để kiểm tra quy tắc đọc attribute mà không cần LDAP server:

~~~java
import javax.naming.Name;
import javax.naming.directory.Attributes;
import javax.naming.directory.BasicAttributes;
import org.springframework.ldap.core.DirContextAdapter;
import org.springframework.ldap.support.LdapNameBuilder;
import static org.junit.jupiter.api.Assertions.*;

// Các dòng này nằm trong một phương thức @Test, cùng package hạ tầng.
Attributes attrs = new BasicAttributes(true);
attrs.put("uid", "lan");
attrs.put("cn", "Nguyễn Lan");
attrs.put("entryUUID", "7cf6b3cd-7d9e-4ae7-a938-8ed53b0b10d3");
Name relativeDn = LdapNameBuilder.newInstance()
        .add("ou", "people").add("uid", "lan").build();
DirContextAdapter context = new DirContextAdapter(attrs, relativeDn);

LocatedPerson located = new LdapPersonMapper()
        .mapFromContext(context);

assertEquals("lan", located.person().login());
assertEquals("Nguyễn Lan", located.person().displayName());
assertEquals("corp-openldap",
        located.person().subject().sourceId());
assertEquals(relativeDn, located.relativeDn());
~~~

Thử thêm **thiếu uid**, **thiếu entryUUID**, **mail vắng mặt**, **cn rỗng**, entry có giá trị Unicode, các giá trị DN có dấu phẩy và lỗi attribute nhị phân. Quan sát mapper trả **null/exception** đúng hợp đồng; không chỉ thử happy path.

### Integration test với LDAP server

Unit test không đủ để kiểm tra DN tương đối và schema thật. Chạy **LDAP test server** phù hợp (ví dụ OpenLDAP container hoặc server nhúng có hỗ trợ attribute tương ứng) và nạp dữ liệu mẫu. Kiểm tra:

1. **base DN** + **search base** không tạo DN bị lặp, **lookup/modify** tác động đúng entry.
2. Filter có ký tự đặc biệt trong **uid** được escape và không tìm sang tài khoản khác.
3. **entryUUID** được trả về khi query chọn rõ attribute; phân biệt thiếu quyền đọc với entry không tồn tại.
4. Entry bị rename hoặc move OU giữa tra cứu và sửa cho ra kết quả lỗi/retry xác định.
5. **REPLACE_ATTRIBUTE** chỉ thay **mail**; entry khác và các attribute khác không bị sửa.
6. Multi-valued **member** được xử lý đúng; order của attribute không được dùng làm khóa business.
7. TLS, credential không hợp lệ, timeout và LDAP server ngừng hoạt động được phân loại rõ.
8. Nếu dùng Active Directory, kiểm tra riêng mapping **objectGUID** nhị phân, **sAMAccountName**, **memberOf** và ACL của AD.

Có thể thêm một kiểm tra kiến trúc: các package **domain** và **application** không import **org.springframework.ldap**, **javax.naming** hoặc **DirContextOperations**. Đây là cách phát hiện mapping bị rò rỉ trở lại những lớp không chịu trách nhiệm về giao thức.

## 14. Các lỗi thiết kế và cách tránh

| Lỗi thường gặp | Tác động | Cách khắc phục |
| --- | --- | --- |
| Mỗi service tự viết **getStringAttribute("cn")** | Dễ lệch quy tắc mapping | Tập trung trong **LdapPersonMapper** |
| Controller nhận và nối DN từ input | Rủi ro sai escaping, lộ schema | Port nhận định danh nghiệp vụ; adapter tạo query |
| Đưa **DirContextOperations** vào domain | Khóa domain vào Spring LDAP | Chuyển sang model Java độc lập |
| Dùng DN làm khóa bền vững của user | Rename/move OU phá tham chiếu | Dùng subject ID ổn định + directory source |
| Nhầm filter escaping với DN escaping | Truy vấn sai hoặc injection | **LdapQueryBuilder** và **LdapNameBuilder** |
| Dùng **getStringAttribute** cho attribute nhị phân | Giá trị danh tính sai | Mapping byte[] và định dạng lưu ổn định |
| Giả định **memberOf** luôn tồn tại | Sai khác schema/server | Thiết kế group reader theo schema thực tế |
| Dùng search base như DN đầy đủ mọi nơi | Lặp base, lookup sai entry | Quy ước rõ tên tương đối trong adapter |
| Xem thiếu attribute là “user not found” | Che lỗi ACL, schema hoặc dữ liệu | Lỗi mapping tách biệt với kết quả rỗng |
| Xem sửa LDAP là transaction cùng JPA | Sai trạng thái nếu một bên thất bại | Điều phối và xử lý consistency ở tầng ứng dụng |

## 15. Bài tập thực hành

Một công ty chuyển từ OpenLDAP sang Active Directory. OpenLDAP dùng **uid**, **cn**, **mail**, **entryUUID**; AD dùng **sAMAccountName**, **displayName**, **mail**, **objectGUID**. API ứng dụng vẫn yêu cầu **findByLogin(login)** trả **DirectoryPerson**, và người dùng có thể đổi đơn vị tổ chức.

Hãy thiết kế:

1. Một **DirectoryPersonPort** ổn định không chứa Spring LDAP API hoặc DN.
2. Hai mapper riêng cho OpenLDAP và AD, cùng trả **DirectorySubject** kèm source ID, xử lý đúng **entryUUID** và **objectGUID**.
3. Một cách tạo filter từ login và xác định relative DN chuẩn, không nối chuỗi từ input.
4. Quy tắc mapping khi thiếu **mail**, thiếu ID bắt buộc, group có nhiều giá trị và DN chứa dấu phẩy.
5. Bộ unit/integration test chứng minh việc rename hoặc move OU không làm thay đổi định danh nghiệp vụ và phép sửa chỉ tác động đúng entry.

Trước khi đưa vào sản phẩm, cần chốt rõ **hợp đồng kiểu dữ liệu**, **directory source**, **base/search base**, **schema thực tế**, **quyền đọc attribute**, **chính sách lỗi**, **mức bảo vệ TLS** và **kiểm thử truy cập directory**.

**Kết luận:** DN và attribute là chi tiết của thư mục, còn application/domain làm việc với danh tính và quy tắc nghiệp vụ. Một lớp mapper rõ trách nhiệm, nằm cạnh adapter Spring LDAP, giúp quy tắc chuyển đổi được kiểm thử độc lập và giảm rủi ro khi đổi schema, DN, server LDAP hoặc API truy cập thư mục.
