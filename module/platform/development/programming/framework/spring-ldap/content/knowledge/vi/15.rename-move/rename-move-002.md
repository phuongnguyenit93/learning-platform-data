# Giữ hay bỏ old RDN value khi rename và move trong Spring LDAP

Khi đổi tên một entry LDAP từ `uid=an,ou=people,dc=example,dc=org` sang `uid=an2,ou=people,dc=example,dc=org`, một câu hỏi quan trọng xuất hiện: **giá trị `uid: an` có còn nằm trong entry sau khi đổi tên hay không?** Câu trả lời gắn với cờ **`deleteOldRDN`** của thao tác LDAP **Modify DN**. Trong môi trường có tài khoản người dùng, nhóm và hệ thống đồng bộ, lựa chọn này có thể ảnh hưởng trực tiếp đến việc tìm kiếm theo UID cũ, định danh đăng nhập, dữ liệu tham chiếu và quy tắc cấp phát tên.

Bài học thuộc chương **Rename và move** của SPRING_LDAP. Chúng ta sẽ phân biệt **DN cũ** với **giá trị thuộc tính nằm trong RDN cũ**, tìm hiểu cờ `deleteOldRDN=true/false`, thao tác `LdapTemplate.rename(...)`, cách cấu hình và kiểm chứng hành vi của JNDI provider, ràng buộc schema, ACL, xử lý xung đột và kiểm thử trên LDAP server lab. Những nguyên tắc này cũng áp dụng khi triển khai bằng `LdapClient`, ODM hoặc API LDAP khác vì server vẫn thực thi ngữ nghĩa Modify DN.

## 1. DN, RDN và attribute value không phải một thứ

Giả sử LDAP server có cây thư mục (*DIT*):

~~~text
dc=example,dc=org
├── ou=people
│   ├── uid=an
│   └── uid=binh
├── ou=contractors
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
mail: an@example.org
~~~

Có ba khái niệm khác nhau:

| Khái niệm | Giá trị minh họa | Vai trò |
| --- | --- | --- |
| **DN** (*Distinguished Name*) | `uid=an,ou=people,dc=example,dc=org` | Tên đầy đủ xác định vị trí entry trong cây |
| **RDN** (*Relative Distinguished Name*) | `uid=an` | Thành phần tên phân biệt entry với các entry cùng cha |
| **RDN attribute value** | `an` trong thuộc tính `uid` | Giá trị thuộc tính tương ứng với thành phần RDN |

Sau khi đổi RDN thành `uid=an2`, DN mới là `uid=an2,ou=people,dc=example,dc=org`. Để tên mới hợp lệ, entry cần có giá trị `uid: an2` (server xử lý việc thêm giá trị RDN mới nếu cần). Nhưng xử lý `uid: an` cũ lại phụ thuộc `deleteOldRDN`.

**Quy tắc cốt lõi:** trong cả hai lựa chọn giữ hoặc bỏ old RDN value, **DN cũ không còn là DN của entry sau khi rename thành công**. Giữ `uid: an` chỉ giữ **giá trị thuộc tính**, không tạo alias LDAP hay một entry thứ hai tại DN cũ.

## 2. LDAP Modify DN làm gì?

Giao thức LDAP mô tả thao tác đổi tên/di chuyển entry bằng **Modify DN request**. Những thành phần chính gồm:

| Thành phần | Ý nghĩa |
| --- | --- |
| `entry` | DN hiện tại của entry cần đổi tên hoặc chuyển vị trí |
| `newrdn` | RDN mới; ví dụ `uid=an2` |
| **`deleteoldrdn`** | Boolean quy định có bỏ các giá trị attribute từ RDN cũ hay không |
| `newSuperior` *(tùy chọn)* | DN của parent mới khi di chuyển entry sang nhánh khác |

Ví dụ ý định (biểu diễn logic, không phải cú pháp LDIF chính thức):

~~~text
entry        = uid=an,ou=people,dc=example,dc=org
newrdn       = uid=an2
deleteoldrdn = TRUE
newSuperior  = (không thay đổi)
~~~

Nếu giữ giá trị cũ:

~~~text
entry        = uid=an,ou=people,dc=example,dc=org
newrdn       = uid=an2
deleteoldrdn = FALSE
newSuperior  = (không thay đổi)
~~~

Lệnh Modify DN **không đồng nghĩa** thao tác `modifyAttributes(...)` thông thường và cũng không phải `unbind(...)` để xóa entry. Nó thay đổi **tên và/hoặc vị trí** của entry, đồng thời xử lý các giá trị RDN theo cờ của giao thức.

### Sơ đồ đổi tên

~~~mermaid
flowchart TD
    A["Entry hiện tại: uid=an,ou=people"] --> B["LDAP Modify DN: newRDN=uid=an2"]
    B --> C{"deleteOldRDN?"}
    C -->|true| D["DN mới: uid=an2,ou=people\nuid: an2"]
    C -->|false| E["DN mới: uid=an2,ou=people\nuid: an\nuid: an2"]
    D --> F["DN uid=an,ou=people không còn là tên entry"]
    E --> F
~~~

Sơ đồ sử dụng trường hợp đơn giản: trước khi đổi tên chỉ có một giá trị `uid: an`. Những thuộc tính khác và các giá trị UID thứ cấp, nếu có, vẫn cần được xét theo schema và chính sách server.

## 3. `deleteOldRDN=true`: bỏ giá trị thuộc RDN cũ

Giả sử trạng thái trước:

~~~ldif
dn: uid=an,ou=people,dc=example,dc=org
uid: an
cn: Nguyen Van An
sn: Nguyen
~~~

Thực hiện:

~~~text
Modify DN:
  newRDN = uid=an2
  deleteOldRDN = TRUE
~~~

Trạng thái mong muốn sau thao tác thành công:

~~~ldif
dn: uid=an2,ou=people,dc=example,dc=org
uid: an2
cn: Nguyen Van An
sn: Nguyen
~~~

Giá trị `uid: an` bị bỏ vì thuộc RDN cũ. Giá trị `uid: an2` được bảo đảm cho RDN mới. Nếu ứng dụng tìm người dùng bằng filter `(uid=an)`, entry này thông thường **không còn khớp** nếu nó không có giá trị UID cũ khác.

**Khi nào nên dùng?** Khi việc đổi UID có ý nghĩa **thu hồi định danh cũ**, và quy tắc nghiệp vụ chỉ muốn công nhận ID mới. Điều này thường phù hợp với hệ thống muốn tránh nhiều username đồng thời hoặc muốn ngừng nhận một alias đăng nhập cũ.

Tuy nhiên, cần khảo sát hệ thống phụ thuộc vào `uid=an`: ứng dụng cũ, đồng bộ, nhóm, tài liệu tham chiếu hoặc hệ thống quản lý định danh. Xóa giá trị cũ trước khi những nơi đó chuyển đổi có thể gây mất khả năng tra cứu.

### Chú ý nếu thuộc tính đã có nhiều giá trị

Trước rename:

~~~ldif
dn: uid=an,ou=people,dc=example,dc=org
uid: an
uid: employee-104
cn: Nguyen Van An
sn: Nguyen
~~~

Sau đổi sang `uid=an2` với `deleteOldRDN=true`, giá trị `uid: an` thuộc RDN cũ bị bỏ; **`employee-104` không thuộc RDN cũ** nên không phải đối tượng bị xóa bởi cờ này. Kết quả dự kiến:

~~~ldif
dn: uid=an2,ou=people,dc=example,dc=org
uid: an2
uid: employee-104
cn: Nguyen Van An
sn: Nguyen
~~~

Cờ này **không phải thao tác xóa toàn bộ thuộc tính `uid`**. Nó điều khiển các giá trị được xác định bởi RDN cũ; những giá trị khác không tự động bị xóa.

## 4. `deleteOldRDN=false`: giữ giá trị RDN cũ như một giá trị thuộc tính

Vẫn từ entry:

~~~ldif
dn: uid=an,ou=people,dc=example,dc=org
uid: an
cn: Nguyen Van An
sn: Nguyen
~~~

Thực hiện Modify DN với `newRDN=uid=an2`, `deleteOldRDN=false`. Trạng thái mong muốn:

~~~ldif
dn: uid=an2,ou=people,dc=example,dc=org
uid: an
uid: an2
cn: Nguyen Van An
sn: Nguyen
~~~

Những điểm quan trọng:

- **DN hiện hành** là `uid=an2,ou=people,dc=example,dc=org`.
- **Giá trị UID cũ** `an` vẫn ở trong thuộc tính `uid`.
- Search filter `(uid=an)` **có thể vẫn trả entry mới**, nếu server cho phép tìm và matching rule của UID xem giá trị khớp.
- **Lookup DN cũ** `uid=an,ou=people,...` không tự hoạt động. Việc giữ attribute value không tạo referral, alias entry hay chuyển hướng tên cũ.

**Khi nào nên dùng?** Khi ứng dụng chủ đích duy trì UID cũ như một giá trị tra cứu bổ sung hoặc cần giai đoạn chuyển tiếp khi đồng bộ định danh. Nhưng không nên dùng cờ này chỉ để “an toàn hơn” nếu chưa hiểu hệ quả: nó có thể giữ lại một identifier lẽ ra phải được thu hồi.

### Rủi ro ở tính năng đăng nhập

Nếu cơ chế xác thực tìm DN của người dùng bằng filter `(uid=<username>)` trước khi bind bằng mật khẩu, việc giữ `uid: an` có thể khiến username cũ vẫn tìm thấy cùng một entry. **Điều này không đồng nghĩa tự động đăng nhập được**, vì còn phụ thuộc các chính sách xác thực; nhưng nó có thể giữ một đường tra cứu mà nghiệp vụ định bỏ.

Nếu yêu cầu bảo mật là “sau đổi username, tên đăng nhập cũ không còn hợp lệ”, phải kiểm thử **luồng đăng nhập thực tế**, không chỉ xác nhận rằng DN đã thay đổi.

## 5. Bảng so sánh: giữ hay bỏ old RDN value

| Kết quả sau rename từ `uid=an` sang `uid=an2` | `deleteOldRDN=true` | `deleteOldRDN=false` |
| --- | --- | --- |
| DN hiện hành | `uid=an2,ou=people,...` | `uid=an2,ou=people,...` |
| DN cũ tiếp tục là DN của entry? | **Không** | **Không** |
| Giá trị `uid: an2` | Có | Có |
| Giá trị `uid: an` ban đầu | Bỏ, nếu không nằm trong RDN mới | Giữ |
| Giá trị UID khác ngoài RDN cũ | Không tự xóa | Không tự xóa |
| Search `(uid=an)` | Thường không khớp sau rename | Có thể tiếp tục khớp |
| Lookup trực tiếp DN cũ | Không tự được bảo lưu | Không tự được bảo lưu |
| Có thay thế cơ chế alias/redirect? | Không | Không |
| Cần xét schema và ACL? | Có | Có |
| Có thể ảnh hưởng đăng nhập hoặc đồng bộ? | Có | Có |

**Một câu chốt:** `deleteOldRDN` quyết định **số phận của attribute value trong RDN cũ**, không quyết định có giữ lại **entry với DN cũ** hay không.

## 6. RDN có thể gồm nhiều attribute-value assertion (AVA)

Nhiều ví dụ dùng RDN đơn trị như `uid=an`, nhưng LDAP cho phép RDN nhiều thành phần, chẳng hạn:

~~~text
cn=An Nguyen+uid=an,ou=people,dc=example,dc=org
~~~

Trong Modify DN, server phải xử lý tập giá trị nằm trong RDN cũ và RDN mới theo ngữ nghĩa giao thức. Nếu `deleteOldRDN=true`, các giá trị cũ tương ứng được bỏ **trừ những giá trị cũng xuất hiện trong RDN mới**. Với `false`, những giá trị cũ được giữ.

Không tự viết code tách RDN bằng `split("+")` hoặc `split(",")`: dấu cộng, dấu phẩy có thể xuất hiện trong **giá trị đã escape**. Dùng parser/builder hiểu cú pháp LDAP DN.

Ví dụ minh họa về tập RDN:

~~~text
RDN cũ: cn=An Nguyen+uid=an
RDN mới: cn=Nguyen An+uid=an2

deleteOldRDN=true:
- Giá trị CN và UID cũ trong RDN được bỏ nếu không còn trong RDN mới.
- Các giá trị của RDN mới được thêm nếu cần.
- Attribute value không thuộc RDN cũ không bị cờ này nhắm tới.
~~~

Cách server thực thi có thể bị ràng buộc bởi attribute syntax, matching rule, quyền sửa và object class. Trong sản phẩm, RDN nhiều thành phần nên được kiểm thử tường minh vì nhiều hệ thống quản trị thường chỉ sử dụng RDN đơn giản.

## 7. Schema có thể khiến lựa chọn giữ/bỏ không hợp lệ

`deleteOldRDN=false` không bảo đảm mọi rename đều thành công. Nếu thuộc tính dùng trong RDN được khai báo **`SINGLE-VALUE`**, việc vừa giữ giá trị cũ vừa thêm giá trị mới cho **cùng một thuộc tính** có thể vi phạm schema.

Ví dụ giả định attribute `employeeKey` là `SINGLE-VALUE`:

~~~text
Trước: employeeKey=E104
Sau dự định: employeeKey=E105
deleteOldRDN=false => cần giữ E104 và thêm E105
=> có thể vi phạm SINGLE-VALUE
~~~

Ngược lại, `deleteOldRDN=true` cũng cần được xét. Nếu RDN đổi **loại thuộc tính** từ `cn=...` sang `uid=...` và việc bỏ giá trị `cn` làm mất giá trị `cn` cuối cùng, entry có thể vi phạm MUST của `person`/`inetOrgPerson`.

| Trường hợp | Rủi ro |
| --- | --- |
| Giữ hai giá trị trong attribute SINGLE-VALUE | `constraintViolation (19)` hoặc lỗi schema |
| Bỏ giá trị `cn` cuối cùng của entry `person` | `objectClassViolation (65)` |
| RDN mới dùng attribute không được object class cho phép | Lỗi schema |
| RDN mới chứa giá trị sai syntax | `invalidDNSyntax (34)` hoặc `invalidAttributeSyntax (21)` |
| Rename sang DN đã tồn tại | `entryAlreadyExists (68)` |
| Thiếu quyền rename/move/sửa tên | `insufficientAccessRights (50)` |

**Không sửa lỗi schema bằng cách âm thầm chuyển cờ.** Cần hiểu mục đích nghiệp vụ, yêu cầu của object class và ràng buộc dữ liệu thực tế. Nếu nghiệp vụ cần hai định danh nhưng attribute đang là SINGLE-VALUE, có thể phải dùng một thuộc tính alias khác được schema cho phép, thay vì cố giữ cả hai dưới cùng attribute.

## 8. Spring LDAP: `LdapTemplate.rename(...)` và cờ deleteOldRDN

Spring LDAP cung cấp `LdapTemplate.rename(oldDn, newDn)` để đổi tên hoặc chuyển entry theo mô hình JNDI. Ở mức ý tưởng, nó sử dụng khả năng rename của JNDI provider; API này **không có tham số Boolean `deleteOldRDN` trong lời gọi thông thường**.

Giả sử `ContextSource.base=dc=example,dc=org`:

~~~java
import javax.naming.Name;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

public class DirectoryRenameService {

    private final LdapTemplate ldapTemplate;

    public DirectoryRenameService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public void renameUid(String oldUid, String newUid) {
        Name oldDn = personDn(oldUid);
        Name newDn = personDn(newUid);

        ldapTemplate.rename(oldDn, newDn);
    }

    private static Name personDn(String uid) {
        if (uid == null || uid.isBlank() || uid.length() > 64) {
            throw new IllegalArgumentException("Invalid uid");
        }

        return LdapNameBuilder.newInstance("ou=people")
                .add("uid", uid)
                .build();
    }
}
~~~

Ví dụ dùng `LdapNameBuilder` để tránh lỗi escape RDN. Cả hai DN trong code đều **tương đối với base của `ContextSource`**:

~~~text
oldDn: uid=an,ou=people
newDn: uid=an2,ou=people
ContextSource.base: dc=example,dc=org
~~~

**Câu hỏi cần kiểm chứng trước khi vận hành:** khi lời gọi `ldapTemplate.rename(...)` được chuyển xuống JNDI provider, provider đặt `deleteOldRDN` là true hay false?

Đừng tự suy luận từ tên phương thức `rename` rằng nó luôn giữ hoặc luôn xóa giá trị cũ trên mọi provider. Việc này phụ thuộc giao thức được gửi và cấu hình JNDI/LDAP client.

### Cấu hình của JNDI LDAP provider

Với **JNDI LDAP provider thông dụng trên OpenJDK/Oracle JDK**, thuộc tính môi trường:

~~~text
java.naming.ldap.deleteRDN = true | false
~~~

được dùng để điều khiển cờ `deleteOldRDN` khi rename. Giá trị mặc định của provider này thường là `true`, nhưng **không áp đặt giả định đó cho mọi JNDI provider và mọi cấu hình runtime**.

Khi tự khai báo bean `LdapContextSource` trong Spring, có thể đưa property này vào base environment:

~~~java
import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.ldap.core.support.LdapContextSource;

@Configuration
public class LdapDirectoryConfiguration {

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

        // Chính sách cho provider JNDI hỗ trợ thuộc tính này.
        // false: đề nghị giữ old RDN attribute value sau rename.
        source.setBaseEnvironmentProperties(
                Map.of("java.naming.ldap.deleteRDN", "false"));

        return source;
    }
}
~~~

Cấu hình ngoại vi minh họa (không ghi password thật):

~~~yaml
app:
  ldap:
    url: ldaps://ldap.example.org:636
    base: dc=example,dc=org
    bind-dn: cn=app-editor,ou=services,dc=example,dc=org
    bind-password: ${LDAP_BIND_PASSWORD}
~~~

**Giới hạn quan trọng của ví dụ:**

1. Thuộc tính trên là **cơ chế của JNDI provider**, không phải tham số `deleteOldRDN` chuẩn của mọi overload `LdapTemplate.rename(...)`.
2. Việc đặt base environment property có thể tác động đến **mọi lời gọi rename** sử dụng context source đó, không chỉ một request.
3. Cần kiểm tra cách phiên bản Spring LDAP/JNDI của dự án tạo context, bảo toàn environment và tương tác với pooling.
4. Đặt property không bảo đảm server sẽ chấp nhận giữ giá trị cũ: schema, ACL và server policy vẫn có hiệu lực.
5. Khi dùng Spring Boot auto-configuration, việc tự khai báo `LdapContextSource` có thể thay đổi những bean được cấu hình tự động. Phải xác định chính xác `LdapTemplate` nào nhận context source này.
6. Nếu một nghiệp vụ cần **true** và một nghiệp vụ cần **false** theo từng thao tác, không nên đổi property trên một bean singleton dùng chung giữa các thread. Cân nhắc một cơ chế client/connection riêng, API LDAP cho phép đặt cờ tường minh hoặc thiết kế cấu hình tách biệt có kiểm soát; kiểm thử thực tế.

Do đó, hãy coi cấu hình này là **phương án cho một provider cụ thể**, không phải bằng chứng cuối cùng. Cách xác nhận đáng tin cậy là rename entry thử nghiệm có giá trị RDN cũ rồi **lookup entry mới và đọc toàn bộ các giá trị thuộc tính liên quan**.

## 9. Move sang OU khác và quan hệ với old RDN

Khi di chuyển entry sang OU mới, tên parent thay đổi. Ví dụ:

~~~text
DN cũ: uid=an,ou=people,dc=example,dc=org
DN mới: uid=an,ou=contractors,dc=example,dc=org
~~~

RDN ở cả hai vị trí **vẫn là `uid=an`**. Vì giá trị RDN cũ cũng nằm trong RDN mới, cờ `deleteOldRDN` thường **không làm mất `uid: an`** trong tình huống chỉ chuyển OU mà không đổi RDN.

Nếu vừa move vừa rename:

~~~text
DN cũ: uid=an,ou=people,dc=example,dc=org
DN mới: uid=an2,ou=contractors,dc=example,dc=org
~~~

thì cần xem cả hai thành phần:

- Parent mới: `ou=contractors,dc=example,dc=org`.
- RDN mới: `uid=an2`.
- Cờ `deleteOldRDN`: có giữ `uid: an` trong entry sau move+rename hay không.

Spring LDAP có thể diễn đạt ý định bằng cùng phương thức `rename(oldDn, newDn)`:

~~~java
Name oldDn = LdapNameBuilder.newInstance("ou=people")
        .add("uid", "an")
        .build();

Name newDn = LdapNameBuilder.newInstance("ou=contractors")
        .add("uid", "an2")
        .build();

ldapTemplate.rename(oldDn, newDn);
~~~

Để move thành công, OU đích phải tồn tại; server phải hỗ trợ thao tác đó theo naming context và chính sách quyền. Một số server hạn chế move qua các naming context/DSA hoặc vùng quản trị. Không dùng `rename` để suy ra mọi LDAP server đều cho phép di chuyển mọi subtree qua mọi suffix.

### Không nhầm move với copy

Một rename/move thành công **không tạo bản sao entry** còn tại DN cũ. Nếu cần giữ đường truy cập tên cũ, phải thiết kế riêng cơ chế redirect/alias, ánh xạ ở ứng dụng hoặc kế hoạch di trú dữ liệu theo khả năng server. Việc đặt `deleteOldRDN=false` **không thực hiện việc copy**.
## 10. Tham chiếu DN trong nhóm: giữ UID cũ chưa đủ

Nhiều LDAP server lưu danh sách thành viên nhóm bằng **DN đầy đủ**:

~~~ldif
dn: cn=developers,ou=groups,dc=example,dc=org
objectClass: top
objectClass: groupOfNames
cn: developers
member: uid=an,ou=people,dc=example,dc=org
~~~

Khi rename người dùng thành `uid=an2,ou=people,dc=example,dc=org`, giá trị `member` ở trên vẫn là **DN cũ** nếu server không có cơ chế tự cập nhật tham chiếu. Cho dù `deleteOldRDN=false` giữ thuộc tính `uid: an`, nó **không tự thay** `member: uid=an,...` bằng `member: uid=an2,...`.

Tùy directory, việc quản lý tham chiếu có thể thuộc về:

- Plugin/cơ chế **referential integrity** được server cấu hình.
- Một quy trình cập nhật thuộc tính `member` hoặc thuộc tính DN tham chiếu khác.
- Dịch vụ đồng bộ/group-management của tổ chức.
- Chính sách từ chối hoặc hạn chế đổi DN trong một số nhánh.

Không tự tin rằng `memberOf` trên entry người dùng có thể được client sửa trực tiếp: ở nhiều server nó là thuộc tính dẫn xuất. Cần kiểm tra schema và cơ chế nhóm thực tế.

**Bài học quan trọng:** old RDN value và old DN reference là hai vấn đề độc lập. Muốn chuyển đổi không làm hỏng quan hệ nhóm, cần kiểm tra **cả filter tìm UID cũ lẫn các nơi lưu DN cũ**.

### Những hệ thống khác có thể phụ thuộc DN

Ngoài nhóm LDAP, DN có thể được lưu trong bảng người quản lý, cache phân quyền, cơ sở dữ liệu ứng dụng, chính sách truy cập, file cấu hình, hàng đợi đồng bộ hoặc tích hợp bên thứ ba. Với hệ thống lớn, dùng một **định danh nghiệp vụ bất biến** để liên kết dữ liệu thường an toàn hơn lấy DN làm khóa vĩnh viễn.

## 11. Chọn giữ hay bỏ theo mục tiêu nghiệp vụ

| Yêu cầu | Lựa chọn phù hợp để cân nhắc | Điều cần kiểm chứng thêm |
| --- | --- | --- |
| Đổi username và **không cho dùng username cũ** | `deleteOldRDN=true` | Search theo old UID, xác thực, cache và các alias khác |
| Chuyển đổi từng bước, **giữ UID cũ để tra cứu** | `deleteOldRDN=false`, nếu schema cho phép | Tác động tới đăng nhập và thời hạn thu hồi alias |
| Tiếp tục lookup trực tiếp **DN cũ** | Không cờ nào đáp ứng | Cơ chế alias/redirect hoặc migration riêng |
| Chỉ move OU, RDN không đổi | Cờ thường không quyết định xóa giá trị RDN | Quyền trên parent mới và tham chiếu DN |
| RDN thuộc attribute `SINGLE-VALUE` | Thường không thể giữ hai giá trị cũ và mới | Ràng buộc schema |
| Đổi từ RDN type `cn` sang `uid` | Phải bảo toàn thuộc tính `cn` MUST | Có thể cần giữ `cn` hoặc chọn chiến lược khác |
| Hai loại nghiệp vụ cần true/false riêng | Tách client/context hoặc chọn API đặt cờ rõ ràng | Tránh thay cấu hình singleton đang dùng chung |

### Ví dụ chuyển đổi UID có thời hạn

Một tổ chức muốn giữ UID cũ để hỗ trợ đồng bộ trong thời gian chuyển đổi:

1. Xác nhận rằng server và schema cho phép thuộc tính `uid` đa trị.
2. Đổi RDN và dùng chế độ giữ old RDN value theo cấu hình được kiểm nghiệm.
3. Xác nhận filter tìm theo UID cũ và UID mới đều trỏ **đúng cùng một entry**.
4. Kiểm tra cơ chế đăng nhập có vô tình cho phép UID cũ làm username hay không; nếu không được phép, chặn tại chính sách xác thực.
5. Cập nhật tham chiếu DN, cache và các hệ thống liên quan.
6. Hết thời gian chuyển đổi, gỡ UID cũ bằng `modifyAttributes(...)` **chỉ sau khi xác nhận nó không còn là RDN hiện hành**, và kiểm thử không còn thành phần nào dùng nó.

**Không nên gọi đây là một giao dịch duy nhất.** Rename LDAP, cập nhật nhóm, đồng bộ cache và hệ thống ngoài có thể thành công/thất bại ở những thời điểm khác nhau. Cần thiết kế quy trình phục hồi và quan sát trạng thái.

## 12. Kiểm tra trước khi gửi Modify DN

Một service thay tên người dùng nên có các kiểm tra sau:

| Kiểm tra | Mục tiêu |
| --- | --- |
| DN cũ thuộc OU được phép | Không đổi nhầm service account hoặc người dùng ngoài phạm vi |
| New RDN hợp lệ, không trùng DN | Hạn chế lỗi dữ liệu và xung đột tên |
| Parent mới đã có và đúng vùng quản trị | Move tới vị trí hợp lệ |
| Object class và attribute syntax hợp lệ | Không phá schema khi giữ/bỏ giá trị |
| Chính sách `deleteOldRDN` đã xác định | Không vô tình giữ alias đăng nhập |
| Danh sách hệ thống tham chiếu old DN | Tránh liên kết đứt gãy |
| Người gọi có quyền nghiệp vụ | Không cho một request sửa tên bất kỳ |
| Service bind có ACL rename/move | Server cho phép thao tác tại nhánh cũ/mới |
| Kết nối dùng TLS và secret được quản lý | Không lộ thông tin xác thực |

Dùng `LdapNameBuilder` để xây DN từ input thay vì nối chuỗi:

~~~java
import javax.naming.Name;
import org.springframework.ldap.support.LdapNameBuilder;

public static Name personDn(String uid) {
    if (uid == null || uid.isBlank() || uid.length() > 64) {
        throw new IllegalArgumentException("Invalid uid");
    }
    return LdapNameBuilder.newInstance("ou=people")
            .add("uid", uid)
            .build();
}
~~~

Với `ContextSource.base=dc=example,dc=org`, kết quả từ hàm là DN **tương đối với base**. Khi cần tìm người dùng theo thuộc tính, dùng `LdapQueryBuilder` và escaping của **filter**, không dùng DN escaping thay filter escaping.

**Pre-check không loại bỏ race condition.** Giữa lúc client kiểm tra DN mới chưa tồn tại và lúc server nhận rename, một tiến trình khác có thể chiếm DN đó. Server vẫn có thể trả `entryAlreadyExists (68)`.

## 13. Các lỗi đặc trưng của rename/move

| Tình huống | Mã hoặc biểu hiện thường gặp | Cách kiểm tra |
| --- | --- | --- |
| DN cũ hoặc parent mới không tồn tại | `noSuchObject (32)` | Base, OU và RDN thực tế |
| DN mới đã được sử dụng | `entryAlreadyExists (68)` | Naming conflict và thao tác đồng thời |
| Tài khoản thiếu quyền rename/move | `insufficientAccessRights (50)` | ACL tại nguồn/đích |
| Giữ giá trị cũ vi phạm `SINGLE-VALUE` | `constraintViolation (19)` | Schema của naming attribute |
| Bỏ value cũ làm thiếu MUST attribute | `objectClassViolation (65)` | Object class và thuộc tính RDN |
| RDN mới sai cú pháp | `invalidDNSyntax (34)` | DN builder và dữ liệu đầu vào |
| Server hạn chế thao tác | `unwillingToPerform (53)` | Chính sách/khả năng server |
| Move vượt ranh giới không được hỗ trợ | `affectsMultipleDSAs (71)` | Naming context, DSA |
| Rename subtree bị hạn chế | Lỗi non-leaf hoặc chính sách riêng | Các entry con, server capabilities |
| Username cũ còn tìm thấy | Giữ `uid` cũ hoặc còn alias khác | Đọc toàn bộ UID và kiểm thử filter |
| Nhóm còn DN cũ | Không có ref integrity tự động | Kiểm tra thuộc tính `member` |
| LDAP/TLS timeout | Không chắc rename đã được thực hiện | Kiểm tra DN cũ/mới và entry ID trước retry |

LDAP server có thể trả mã khác khi đồng thời có nhiều ràng buộc không hợp lệ. Spring LDAP chuyển nhiều JNDI exception thành exception của framework. Không dùng thông điệp lỗi chứa đầy đủ thông tin của server làm phản hồi công khai.

### Timeout sau rename: kết quả có thể chưa rõ

Nếu server đã đổi tên nhưng response bị mất, gọi rename lần nữa bằng **DN cũ** có thể báo không tồn tại. Điều đó **không đủ** để khẳng định request trước thành công: entry có thể bị tác nhân khác đổi tên hoặc xóa.

Quy trình xử lý:

1. Lookup **DN cũ** và **DN mới** nếu được phép.
2. Dùng định danh ổn định để chứng minh entry ở DN mới là chủ thể mong đợi.
3. Kiểm tra tập thuộc tính RDN sau rename theo chính sách.
4. Kiểm tra các tham chiếu nhóm và ứng dụng đồng bộ.
5. Chỉ retry hoặc hòa giải sau khi xác định trạng thái; tránh ghi đè hoặc đổi nhầm entry khác.

## 14. Unit test: kiểm tra DN và API được gọi

Một unit test có thể kiểm tra service dùng đúng DN tương đối, nhưng không xác minh được cờ `deleteOldRDN` của JNDI provider.

Ví dụ JUnit 5/Mockito cho `DirectoryRenameService` ở mục 8:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.*;

import javax.naming.Name;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.ldap.core.LdapTemplate;

class DirectoryRenameServiceTest {

    @Test
    void renameUsesRelativeNames() {
        LdapTemplate template = mock(LdapTemplate.class);
        DirectoryRenameService service = new DirectoryRenameService(template);

        service.renameUid("an", "an2");

        ArgumentCaptor<Name> oldDn = ArgumentCaptor.forClass(Name.class);
        ArgumentCaptor<Name> newDn = ArgumentCaptor.forClass(Name.class);

        verify(template).rename(oldDn.capture(), newDn.capture());

        assertEquals("uid=an,ou=people", oldDn.getValue().toString());
        assertEquals("uid=an2,ou=people", newDn.getValue().toString());
        verifyNoMoreInteractions(template);
    }
}
~~~

Nên kiểm thử thêm UID trống, quá dài hoặc chứa ký tự DN đặc biệt. Test này xác minh service chuẩn bị đúng tên, không chứng minh LDAP server có quyền rename, schema hợp lệ hoặc cách giữ/bỏ RDN value.

## 15. Integration test: kiểm chứng true và false

Đây là lớp kiểm thử **bắt buộc** nếu việc giữ old UID quan trọng cho bảo mật/đồng bộ. Chuẩn bị LDAP server lab có schema `inetOrgPerson`, `ou=people`, tài khoản được phép tạo/rename/đọc/xóa trong OU thử nghiệm và LDAPS/StartTLS đã xác minh chứng chỉ.

Entry ban đầu:

~~~ldif
dn: uid=lab-old,ou=people,dc=lab,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: lab-old
cn: Lab Person
sn: Person
mail: lab@example.org
~~~

Thiết lập hai lượt thử riêng biệt hoặc hai context source thử nghiệm:

- **Lượt A:** xác định provider sẽ gửi `deleteOldRDN=true`.
- **Lượt B:** xác định provider sẽ gửi `deleteOldRDN=false`.

Sau mỗi lượt rename thành `uid=lab-new,ou=people,...`:

1. Lookup DN mới, đọc toàn bộ `uid` qua `getStringAttributes("uid")`.
2. Xác nhận `uid: lab-new` hiện diện.
3. Với **true**, xác nhận `lab-old` không còn (dữ liệu đầu vào chỉ có một old UID).
4. Với **false**, xác nhận cả `lab-old` và `lab-new` có mặt nếu schema cho phép.
5. Lookup DN cũ: không tự thấy entry mới, bất kể old UID có còn hay không.
6. Kiểm tra `cn`, `sn`, `mail` không bị đổi ngoài ý định.
7. Tìm theo filter `(uid=lab-old)` và so kết quả với chính sách.
8. Dọn dữ liệu test tại **DN hiện hành** và chỉ dọn entry do test tạo.

### Khung code kiểm tra sau rename

~~~java
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.Arrays;
import java.util.List;
import javax.naming.Name;
import org.springframework.ldap.core.DirContextOperations;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

public class RenameStateVerifier {

    private final LdapTemplate ldapTemplate;

    public RenameStateVerifier(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public void verifyUidValues(boolean keepOld) {
        Name newDn = LdapNameBuilder.newInstance("ou=people")
                .add("uid", "lab-new")
                .build();

        DirContextOperations entry = ldapTemplate.lookupContext(newDn);
        String[] raw = entry.getStringAttributes("uid");
        List<String> values = raw == null ? List.of() : Arrays.asList(raw);

        assertTrue(values.contains("lab-new"));
        if (keepOld) {
            assertTrue(values.contains("lab-old"));
        } else {
            assertFalse(values.contains("lab-old"));
        }
    }
}
~~~

Đây chỉ là **helper dùng trong integration test**, không tự cấu hình server, chạy rename hay cleanup. Cần chạy cùng setup/teardown và đối chiếu đúng context source đang dùng. Đừng chạy hai lượt true/false trên cùng một entry đã bị thay đổi mà không khởi tạo lại trạng thái gốc.

### Kiểm tra trường hợp chỉ move

Đổi `uid=an,ou=people` thành `uid=an,ou=contractors` mà không đổi RDN. Sau đó kiểm tra DN đã chuyển, `uid: an` vẫn hiện diện, quyền ở OU đích phù hợp và các reference DN được xử lý. Không coi việc di chuyển OU là lệnh xóa UID cũ.

## 16. Bài thực hành: dự đoán kết quả

Giả sử ban đầu có:

~~~text
DN:  uid=an,ou=people,dc=example,dc=org
uid: an
cn:  Nguyen Van An
sn:  Nguyen
~~~

Yêu cầu đổi sang `uid=an2,ou=people,dc=example,dc=org`.

**Câu hỏi**

1. Sau `deleteOldRDN=true`, DN mới và các giá trị UID dự kiến là gì?
2. Sau `deleteOldRDN=false`, DN mới và các giá trị UID dự kiến là gì?
3. Giữ `uid: an` có khiến lookup DN cũ hoạt động trở lại không?
4. Vì sao `(uid=an)` có thể khớp sau `false` dù DN cũ không tồn tại?
5. Nếu naming attribute là `SINGLE-VALUE`, `false` có thể vi phạm gì?
6. Nếu chuyển OU nhưng giữ RDN `uid=an`, có nên xóa `uid: an` không?
7. Giữ old UID có tự cập nhật DN thành viên trong `groupOfNames.member` không?
8. Nếu username cũ phải ngừng hoạt động, cần kiểm thử ngoài lookup DN mới những gì?
9. Trong Spring LDAP, có tham số Boolean trực tiếp ở lời gọi `rename(oldDn,newDn)` không?
10. Sau timeout, dựa vào điều gì để quyết định retry?

**Đáp án**

| Câu | Giải thích |
| --- | --- |
| 1 | DN mới là `uid=an2,ou=people,...`; UID cũ `an` bị bỏ nếu chỉ có một value ban đầu |
| 2 | DN mới như trên; `uid` có thể chứa cả `an` và `an2` khi schema cho phép |
| 3 | Không. Old RDN value không phải old DN/alias |
| 4 | Search lọc attribute, còn lookup truy cập tên DN hiện tại |
| 5 | Có thể gây constraint violation vì giữ đồng thời hai giá trị |
| 6 | Không. Giá trị RDN mới vẫn chính là `uid: an` |
| 7 | Không bảo đảm. Server cần referential integrity hoặc ứng dụng cập nhật tham chiếu |
| 8 | Kiểm thử filter tìm user, auth/bind, nhóm, cache và quy tắc đăng nhập |
| 9 | Trong API `LdapTemplate.rename(...)` thông thường không có tham số đó; kiểm soát qua provider/LDAP client |
| 10 | Đọc DN cũ/mới, đối chiếu định danh bất biến, trạng thái UID và các tham chiếu trước khi quyết định |

### Chọn chính sách cho ba sản phẩm

**A.** Sau đổi UID, tên đăng nhập cũ phải hết hiệu lực. → Cân nhắc `true` **và** kiểm thử toàn bộ luồng đăng nhập.

**B.** Giữ khả năng tìm theo UID cũ một thời gian cho hệ thống tích hợp. → Cân nhắc `false` khi schema cho phép, có kế hoạch thu hồi alias và không vô tình giữ quyền đăng nhập cũ.

**C.** Chỉ chuyển OU mà không đổi UID. → Trọng tâm là DN/ACL/tham chiếu, không phải xóa giá trị RDN đã giữ nguyên.

## 17. Checklist trước khi vận hành

- [ ] Ghi rõ DN/RDN cũ, DN/RDN mới và parent mới khi move.
- [ ] Xác định chính sách giữ/bỏ **old RDN attribute value** và tác động tới tìm kiếm/đăng nhập.
- [ ] Không nhầm giữ old UID với giữ **old DN** hoặc tạo alias LDAP.
- [ ] Kiểm tra schema: SINGLE-VALUE, MUST/MAY, syntax và matching rule.
- [ ] Dựng DN bằng `LdapNameBuilder`; không nhận raw DN tùy ý qua API.
- [ ] Kiểm tra `ContextSource.base`, URL, bind identity, TLS và ACL phù hợp.
- [ ] Xác định JNDI provider và cách cài `java.naming.ldap.deleteRDN` khi cần.
- [ ] Không thay property runtime của shared singleton để đổi hành vi giữa các request.
- [ ] Kiểm tra OU đích, naming context và khả năng di chuyển subtree.
- [ ] Lập kế hoạch cập nhật tham chiếu nhóm, cache và hệ thống bên ngoài.
- [ ] Kiểm thử xung đột DN, lỗi schema/ACL và tình huống timeout chưa rõ kết quả.
- [ ] Unit test xây DN; integration test true/false trên server lab và đọc lại tất cả giá trị RDN.
- [ ] Có phương án rollback nghiệp vụ hoặc phục hồi trạng thái khi đồng bộ liên hệ thất bại.

## 18. Ghi nhớ

- **`deleteOldRDN=true`** yêu cầu bỏ giá trị thuộc **RDN cũ** không còn trong RDN mới; **`false`** giữ chúng nếu hợp lệ theo schema và chính sách server.
- **Cả hai lựa chọn đều đổi DN.** Giữ `uid: an` không giữ `uid=an,ou=people,...` làm tên entry.
- **`LdapTemplate.rename(...)`** biểu diễn rename/move; cần xác minh cách JNDI provider truyền cờ `deleteOldRDN` và kiểm thử trên server thật.
- **Schema và ACL** quyết định rename có được chấp nhận. Giữ old UID có thể ảnh hưởng tìm kiếm và đăng nhập; chuyển OU có thể ảnh hưởng quyền và nhóm.
- **Tham chiếu DN không tự được bảo đảm cập nhật** chỉ vì giữ RDN value. Cần cơ chế ref integrity hoặc quy trình migration có kiểm soát.
- **Kiểm thử trên LDAP lab** bằng lookup DN mới, search UID cũ/mới, kiểm tra toàn bộ giá trị thuộc tính RDN và các hệ thống phụ thuộc trước khi áp dụng trên production.

### Tài liệu tham khảo

- [Spring LDAP Reference Documentation](https://docs.spring.io/spring-ldap/reference/)
- [RFC 4511 — LDAP Modify DN Operation](https://www.rfc-editor.org/rfc/rfc4511)
- [RFC 4512 — LDAP Directory Information Models](https://www.rfc-editor.org/rfc/rfc4512)
- [RFC 4514 — String Representation of Distinguished Names](https://www.rfc-editor.org/rfc/rfc4514)
- [Java SE 17 — JNDI Context.rename](https://docs.oracle.com/en/java/javase/17/docs/api/java.naming/javax/naming/Context.html)
