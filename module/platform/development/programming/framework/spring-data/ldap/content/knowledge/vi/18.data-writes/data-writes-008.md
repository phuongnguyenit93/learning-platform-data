# Xóa entry bằng unbind

Trong Spring Data LDAP, một entry được xóa khỏi directory bằng thao tác **unbind** của `LdapTemplate` hoặc repository. Ví dụ:

~~~java
ldapTemplate.unbind(dn);
~~~

Tên method dễ gây nhầm: `unbind(dn)` ở `LdapOperations` có nghĩa **xóa entry có DN đó khỏi cây LDAP**. Nó không phải thao tác đăng xuất hay đóng kết nối. Ở mức giao thức, LDAP còn có một `UnbindRequest` riêng để kết thúc phiên làm việc; trong JNDI, `Context.close()` đóng context/kết nối, còn `Context.unbind(name)` xóa tên/entry khỏi namespace.

Theo RFC 4511, một LDAP DeleteRequest thông thường chỉ xóa được **entry lá** (entry không có entry con). Spring LDAP cung cấp thêm overload `unbind(dn, true)` để xóa đệ quy các entry con trước khi xóa entry gốc. Đây là một quy trình gồm nhiều thao tác xóa; nó không biến cả cây thành một giao dịch nguyên tử.

Bài thuộc chương **Ghi dữ liệu** của mô-đun `SPRING_DATA_LDAP`. Chúng ta sẽ học cách xây DN an toàn, dùng `LdapTemplate.unbind`, JNDI `DirContext.unbind` và `LdapRepository.deleteById`, xử lý entry không phải lá, kiểm soát quyền xóa, xử lý tham chiếu nhóm và kiểm thử trên directory thật.

> **Quy tắc quan trọng:** xác định đúng entry và phạm vi trước khi xóa. Dùng xóa một entry lá cho thao tác thông thường; chỉ dùng xóa đệ quy khi nghiệp vụ đã xác nhận rõ toàn bộ subtree được phép loại bỏ.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích `unbind` trong Spring LDAP có nghĩa là xóa entry.
2. Phân biệt xóa entry với LDAP protocol `UnbindRequest` và đóng `DirContext`.
3. Hiểu LDAP DeleteRequest chỉ áp dụng cho entry lá theo RFC 4511.
4. Dùng `LdapTemplate.unbind(Name)` và `unbind(Name, boolean)` đúng ngữ nghĩa.
5. Xây DN bằng `LdapNameBuilder`, tránh ghép chuỗi từ input không tin cậy.
6. Xóa entry bằng JNDI `DirContext.unbind` và quản lý vòng đời context.
7. Xóa theo ID bằng `LdapRepository.deleteById(Name)` mà không nhầm với xóa subtree.
8. Phân biệt lỗi không tìm thấy, entry còn con, thiếu quyền và lỗi kết nối.
9. Thiết kế authorization và LDAP ACL riêng cho thao tác Delete.
10. Nhận diện các tham chiếu DN trong `groupOfNames.member` và các thuộc tính khác có thể còn sót sau khi xóa.
11. Hiểu giới hạn transaction, xóa đệ quy, retry và khả năng khôi phục.
12. Viết integration test xác minh entry đã bị xóa và các entry không liên quan vẫn tồn tại.

## 2. Entry LDAP và DN được dùng khi xóa

LDAP lưu dữ liệu dưới dạng các entry trong Directory Information Tree (DIT). Mỗi entry có một **Distinguished Name (DN)** duy nhất trong phạm vi directory.

Ví dụ:

~~~text
dc=example,dc=org
└── ou=people
    ├── uid=lan
    ├── uid=minh
    └── uid=mai
~~~

Entry của Lan:

~~~ldif
dn: uid=lan,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: lan
cn: Nguyen Thi Lan
sn: Nguyen
mail: lan@example.org
~~~

Trong ví dụ, DN đầy đủ là:

~~~text
uid=lan,ou=people,dc=example,dc=org
~~~

Nếu `ContextSource` đã cấu hình `base=dc=example,dc=org`, các thao tác Spring LDAP thông thường có thể nhận DN tương đối với base:

~~~text
uid=lan,ou=people
~~~

Cần giữ đúng quy ước DN trong ứng dụng:

| Thành phần | Ví dụ | Vai trò |
| --- | --- | --- |
| Naming context/base | `dc=example,dc=org` | Gốc tương đối mà ContextSource đã cấu hình. |
| DN tương đối | `uid=lan,ou=people` | Tên entry truyền cho LdapTemplate khi đã cấu hình base. |
| DN đầy đủ | `uid=lan,ou=people,dc=example,dc=org` | Định danh entry trên toàn directory, hữu ích cho log/audit và tham chiếu. |
| RDN | `uid=lan` | Thành phần định danh ngay tại entry. |

Xóa nhầm DN có thể làm mất dữ liệu của người khác hoặc xóa một OU có nhiều entry con. Vì vậy, API chỉ nên nhận định danh nghiệp vụ như `uid`, sau đó service tự xây DN trong nhánh đã được phép.

## 3. Phân biệt ba thao tác có tên gần giống

Đây là điểm quan trọng nhất khi học `unbind`.

| API | Ý nghĩa | Có xóa entry LDAP không? |
| --- | --- | :---: |
| `LdapTemplate.unbind(dn)` | Xóa entry có DN được chỉ định. | **Có** |
| `DirContext.unbind(name)` | JNDI xóa binding/entry trong namespace. | **Có** |
| LDAP protocol `UnbindRequest` | Kết thúc phiên LDAP hiện tại. | **Không** |
| `DirContext.close()` | Đóng context và giải phóng tài nguyên. | **Không** |
| `LdapUtils.closeContext(ctx)` | Đóng context theo tiện ích Spring LDAP. | **Không** |

### 3.1. JNDI Context.unbind(name)

JNDI định nghĩa `Context.unbind(name)` để loại bỏ binding có tên đó khỏi namespace. Khi dùng JNDI LDAP provider, thao tác này được ánh xạ sang LDAP Delete operation.

~~~java
ctx.unbind("uid=lan,ou=people");
~~~

Lệnh trên xóa entry Lan nếu context đang dùng naming base phù hợp và LDAP server chấp nhận Delete.

### 3.2. LDAP protocol UnbindRequest

LDAPv3 có một operation tên `UnbindRequest`. Theo RFC 4511, nó báo cho server rằng client kết thúc LDAP session. Operation này không có response tương ứng và không xóa entry.

Trong Java, đóng context:

~~~java
ctx.close();
~~~

sẽ giải phóng context; với LDAP provider, phiên LDAP tương ứng được kết thúc theo cơ chế của provider.

### 3.3. Spring LDAP LdapOperations.unbind

Spring LDAP đặt tên method theo API JNDI:

~~~java
ldapTemplate.unbind(dn);
~~~

Method này gọi thao tác xóa entry và quản lý plumbing như lấy context, dịch lỗi JNDI sang exception Spring LDAP và đóng context. **Đừng dùng method này để logout** và cũng đừng nhầm với `LdapUtils.closeContext`.

## 4. LDAP DeleteRequest chỉ xóa entry lá

RFC 4511 `4.8 quy định Delete operation chỉ xóa được **leaf entry**, tức entry không có subordinate entries.

Ví dụ cây:

~~~text
ou=people,dc=example,dc=org
├── uid=lan
│   └── cn=addresses
└── uid=minh
~~~

- Xóa `uid=lan,...` bằng DeleteRequest thông thường sẽ thất bại vì Lan còn entry con `cn=addresses`.
- Xóa `cn=addresses,...` trước thì Lan có thể trở thành entry lá.
- `uid=minh,...` có thể xóa trực tiếp nếu không có entry con và ACL cho phép.

Nếu server từ chối xóa entry không phải lá, LDAP result code thường là `notAllowedOnNonLeaf (66)`. JNDI provider có thể ánh xạ thành `ContextNotEmptyException`; Spring LDAP có `org.springframework.ldap.ContextNotEmptyException`.

### Sơ đồ thứ tự xóa

~~~mermaid
flowchart TD
    A["ou=people"] --> B["uid=lan"]
    B --> C["cn=addresses"]
    A --> D["uid=minh"]
    C --> E["Xóa entry lá trước"]
    E --> F["Xóa uid=lan sau khi đã rỗng"]
    D --> G["Xóa uid=minh trực tiếp nếu không có con"]
~~~

**Không được giả định xóa parent sẽ tự động xóa children** khi gửi một DeleteRequest LDAP thông thường.

## 5. Dùng LdapTemplate.unbind để xóa một entry

Với ứng dụng Spring LDAP, `LdapTemplate` là lựa chọn rõ ràng cho thao tác xóa.

### 5.1. Tạo DN bằng LdapNameBuilder

~~~java
import javax.naming.Name;

import org.springframework.ldap.support.LdapNameBuilder;

Name personDn = LdapNameBuilder
        .newInstance("ou=people")
        .add("uid", "lan")
        .build();
~~~

Nếu `ContextSource.base=dc=example,dc=org`, DN được tạo là:

~~~text
uid=lan,ou=people
~~~

`LdapNameBuilder` xây DN theo cấu trúc và xử lý việc biểu diễn giá trị RDN. Không nên ghép chuỗi thủ công:

~~~java
// Không an toàn khi uid lấy trực tiếp từ HTTP.
String dn = "uid=" + uidFromRequest + ",ou=people";
ldapTemplate.unbind(dn);
~~~

Một giá trị UID chứa dấu phẩy, dấu cộng, dấu bằng hoặc ký tự đặc biệt có thể làm thay đổi cách parse DN nếu không được escape đúng. DN escaping theo RFC 4514 khác với LDAP filter escaping theo RFC 4515.

### 5.2. Xóa bằng Name

~~~java
import javax.naming.Name;

import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

public class PersonDeletionExample {

    private final LdapTemplate ldapTemplate;

    public PersonDeletionExample(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public void deletePerson(String uid) {
        Name dn = LdapNameBuilder.newInstance("ou=people")
                .add("uid", uid)
                .build();

        ldapTemplate.unbind(dn);
    }
}
~~~

`unbind(Name)` xóa **một entry**. Entry phải là entry lá. Nếu DN không tồn tại, thao tác có thể ném Spring LDAP `NameNotFoundException`. Nếu entry có children, thao tác có thể ném `ContextNotEmptyException` hoặc exception tương ứng từ provider.

### 5.3. Xóa bằng String

Có thể truyền DN dưới dạng chuỗi:

~~~java
ldapTemplate.unbind("uid=lan,ou=people");
~~~

Dùng `Name` thường giúp biểu diễn DN có cấu trúc rõ ràng hơn, đặc biệt khi RDN được xây từ input. Chuỗi DN chỉ nên dùng khi nó đã được tạo/kiểm tra an toàn.

## 6. Service xóa người dùng có validation và authorization

Trong ứng dụng thật, không nên để controller gọi trực tiếp `ldapTemplate.unbind` với DN do client cung cấp. Tách một service chịu trách nhiệm:

- Validate UID theo quy tắc định danh.
- Xây DN trong OU cho phép.
- Dùng template được cấu hình bằng service account có quyền Delete giới hạn.
- Kiểm tra quyền của người gọi HTTP.
- Chuyển lỗi LDAP sang lỗi nghiệp vụ.
- Ghi audit sau khi directory xác nhận thao tác thành công.

### 6.1. Service

~~~java
package com.example.directory.service;

import javax.naming.Name;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.ldap.ContextNotEmptyException;
import org.springframework.ldap.NameNotFoundException;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class PersonDeletionService {

    private final LdapTemplate writerTemplate;

    public PersonDeletionService(
            @Qualifier("directoryWriterTemplate")
            LdapTemplate writerTemplate) {
        this.writerTemplate = writerTemplate;
    }

    @PreAuthorize("hasAuthority('DIRECTORY_PERSON_DELETE')")
    public void deleteByUid(String uid) {
        validateUid(uid);

        Name dn = LdapNameBuilder.newInstance("ou=people")
                .add("uid", uid)
                .build();

        try {
            // Chỉ xóa entry lá. Không tự động xóa subtree.
            writerTemplate.unbind(dn);
        } catch (NameNotFoundException missing) {
            throw new PersonNotFoundException(
                    "Person does not exist", missing);
        } catch (ContextNotEmptyException hasChildren) {
            throw new PersonHasChildrenException(
                    "Person entry has subordinate entries", hasChildren);
        }
    }

    private static void validateUid(String uid) {
        if (uid == null
                || !uid.matches("[a-z][a-z0-9._-]{2,31}")) {
            throw new IllegalArgumentException("Invalid uid");
        }
    }
}
~~~

`PersonNotFoundException` và `PersonHasChildrenException` là domain exception do ứng dụng định nghĩa.

### 6.2. Vì sao không Search exists trước rồi mới xóa?

Một cách thường gặp là:

~~~java
if (repository.existsById(dn)) {
    ldapTemplate.unbind(dn);
}
~~~

Đây là hai request riêng. Entry có thể bị xóa hoặc thay đổi giữa lần kiểm tra và lần Delete (race condition). Nếu cần kết quả chính xác, hãy thực hiện Delete và xử lý response của chính thao tác Delete.

Pre-check chỉ hữu ích nếu nghiệp vụ cần hiển thị thông tin hoặc thực hiện workflow khác, nhưng nó **không thay thế** kiểm tra của server và không tạo ra một giao dịch nguyên tử.

### 6.3. Không cho client chọn DN tùy ý

API nhận `uid` rồi service cố định base `ou=people`. Không xây endpoint kiểu:

~~~text
DELETE /api/v1/ldap?dn=dc=example,dc=org
~~~

hoặc nhận `recursive=true` mà không có policy riêng. Client không nên quyết định có thể xóa OU, group, service account hay naming context gốc.

## 7. REST API cho thao tác Delete

Ví dụ controller:

~~~java
package com.example.directory.web;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import com.example.directory.service.PersonDeletionService;

@RestController
@RequestMapping("/api/v1/people")
public class PersonDeletionController {

    private final PersonDeletionService deletionService;

    public PersonDeletionController(
            PersonDeletionService deletionService) {
        this.deletionService = deletionService;
    }

    @DeleteMapping("/{uid}")
    public ResponseEntity<Void> delete(
            @PathVariable String uid) {
        deletionService.deleteByUid(uid);
        return ResponseEntity.noContent().build();
    }
}
~~~

Request:

~~~http
DELETE /api/v1/people/lan
~~~

Nếu xóa thành công, API trả `204 No Content`.

### HTTP authorization

`@PreAuthorize("hasAuthority('DIRECTORY_PERSON_DELETE')")` cần được bật bằng `@EnableMethodSecurity`. Controller cũng có thể được bảo vệ qua `SecurityFilterChain`. Không dựa vào việc frontend ẩn nút Delete.

Quyền người gọi HTTP và quyền LDAP service account là hai lớp độc lập:

| Lớp | Câu hỏi |
| --- | --- |
| Spring Security | Người dùng đang gọi API có được phép yêu cầu xóa người này không? |
| LDAP Bind identity | Ứng dụng đang dùng Bind DN nào để thực hiện Delete? |
| LDAP ACL | Bind DN đó có quyền xóa entry mục tiêu và đáp ứng các điều kiện của server không? |

Ngay cả khi người gọi có authority, LDAP server vẫn có thể từ chối vì service account không có ACL Delete. Ngược lại, service account có quyền Delete không có nghĩa mọi người dùng HTTP đều được gọi endpoint.

## 8. Xử lý lỗi Delete

Một số lỗi thường gặp:

| Lỗi Spring LDAP | Ý nghĩa | Hướng xử lý |
| --- | --- | --- |
| `NameNotFoundException` | DN mục tiêu không tồn tại. | Trả 404 hoặc kết quả idempotent theo hợp đồng API. |
| `ContextNotEmptyException` | Entry còn subordinate entries. | Giữ nguyên entry; yêu cầu xử lý children hoặc workflow subtree riêng. |
| `NoPermissionException` | LDAP ACL từ chối. | Kiểm tra Bind DN và ACL; không retry bằng admin. |
| `CommunicationException` | Kết nối/network lỗi. | Ghi nhận trạng thái không chắc chắn, đối soát trước retry. |
| `ServiceUnavailableException` | Directory không sẵn sàng. | Trả lỗi dịch vụ tạm thời. |
| `InvalidNameException` | DN không hợp lệ. | Kiểm tra cách xây DN; không lộ raw DN. |
| `UncategorizedLdapException` | Provider không ánh xạ được lỗi cụ thể. | Giữ cause để điều tra nội bộ. |

### 8.1. Missing entry và tính idempotent của DELETE

HTTP DELETE thường được thiết kế idempotent: gọi lại nhiều lần không làm thay đổi trạng thái cuối sau lần đầu. Tuy nhiên LDAP Delete một DN đã bị xóa có thể trả `noSuchObject`, được JNDI ánh xạ thành `NameNotFoundException`.

Ứng dụng cần chọn một chính sách rõ ràng:

- **Strict:** lần đầu thành công trả 204; lần tiếp theo không tìm thấy trả 404.
- **Idempotent response:** nếu mục tiêu đã không tồn tại, coi trạng thái cuối đã đạt và trả 204.
- **Audit-oriented:** ghi nhận riêng sự kiện “đã xóa” và “đã không tồn tại”, dù response có thể cùng 204.

Không bắt mọi `NamingException` rồi trả 204; lỗi ACL, TLS hoặc server unavailable không phải trạng thái đã xóa.

### 8.2. Không retry mù khi kết nối mất sau Delete

Nếu client gửi Delete nhưng mất kết nối trước khi nhận response, client có thể không biết server đã xóa entry hay chưa. Trước khi retry, hãy đối soát trạng thái bằng một lần đọc được kiểm soát.

Không biến lỗi mạng thành “xóa thất bại chắc chắn” hoặc “xóa thành công chắc chắn” nếu chưa có response xác nhận.

## 9. Xóa entry có children: overload recursive

Spring LDAP có overload:

~~~java
ldapTemplate.unbind(dn, true);
~~~

Javadoc `LdapOperations` mô tả `unbind(Name, boolean recursive)` là xóa entry, có thể xóa cả descendants. Nếu `recursive=false` và entry có children, thao tác thất bại.

### 9.1. So sánh hai overload

| Lời gọi | Ý nghĩa |
| --- | --- |
| `unbind(dn)` | Xóa một entry lá. |
| `unbind(dn, false)` | Xóa một entry lá; nếu có children thì thất bại. |
| `unbind(dn, true)` | Spring LDAP xóa các descendants rồi xóa entry gốc. |

Đối với thao tác thông thường, ưu tiên `unbind(dn)`. Chỉ dùng `recursive=true` cho use case có quyền và xác nhận riêng.

### 9.2. Recursive unbind không phải DeleteRequest subtree nguyên tử

LDAP DeleteRequest chuẩn chỉ xóa leaf entry. Overload recursive của Spring LDAP là tiện ích phía client: framework duyệt các context con và xóa theo thứ tự phù hợp, sau đó xóa entry gốc.

Hệ quả:

- Có thể phát sinh nhiều request Delete tới server.
- Nếu một child bị từ chối, một phần subtree có thể đã bị xóa trước khi lỗi xuất hiện.
- Không có rollback tự động cho những entry đã xóa thành công.
- Có thể thất bại khi một entry con được thêm đồng thời trong lúc duyệt.
- Cần quyền đọc/list các descendants và quyền Delete phù hợp trên từng entry.
- Referral hoặc server khác có thể khiến quá trình không hoàn tất như dự kiến.

Không đưa `recursive` thành cờ tùy ý trong API công khai. Hãy tạo method nghiệp vụ riêng, ví dụ `deleteDepartmentSubtree`, giới hạn DN trong một OU cụ thể, xác minh số lượng entry và ghi audit.

### 9.3. Ví dụ xóa subtree đã được xác định

~~~java
public void deleteTestOrganizationalUnit(String validatedOuName) {
    if (validatedOuName == null
            || !validatedOuName.matches("[a-z0-9-]{2,40}")) {
        throw new IllegalArgumentException("Invalid OU name");
    }

    Name subtreeDn = LdapNameBuilder
            .newInstance("ou=departments")
            .add("ou", validatedOuName)
            .build();

    // Chỉ gọi trong workflow đã xác nhận toàn bộ subtree.
    ldapTemplate.unbind(subtreeDn, true);
}
~~~

Đoạn code minh họa phải nằm sau kiểm tra quyền quản trị OU, kiểm tra phạm vi và quy trình xác nhận. Không lấy `validatedOuName` từ DN thô của client và không dùng base rộng như `dc=example,dc=org` làm target recursive.

## 10. Xóa bằng JNDI DirContext.unbind

Khi cần gọi JNDI trực tiếp, có thể lấy context từ `ContextSource` rồi gọi `DirContext.unbind`.

~~~java
package com.example.directory.adapter;

import javax.naming.NamingException;
import javax.naming.directory.DirContext;

import org.springframework.ldap.core.ContextSource;
import org.springframework.ldap.support.LdapUtils;

public class RawJndiDeleteAdapter {

    private final ContextSource contextSource;

    public RawJndiDeleteAdapter(ContextSource contextSource) {
        this.contextSource = contextSource;
    }

    public void delete(String relativeDn) {
        DirContext ctx = null;
        try {
            ctx = contextSource.getReadWriteContext();

            // DN tương đối với ContextSource.base.
            ctx.unbind(relativeDn);
        } catch (NamingException ex) {
            throw LdapUtils.convertLdapException(ex);
        } finally {
            LdapUtils.closeContext(ctx);
        }
    }
}
~~~

Điểm cần nhớ:

1. `getReadWriteContext()` lấy context theo credential mặc định của `ContextSource`.
2. `ctx.unbind(relativeDn)` là thao tác xóa entry.
3. JNDI có thể ném checked `javax.naming.NamingException`.
4. `LdapUtils.convertLdapException` chuyển lỗi JNDI sang hierarchy unchecked của Spring LDAP.
5. `LdapUtils.closeContext(ctx)` đóng context dù thao tác thành công hay thất bại.

Nếu chỉ dùng `LdapTemplate.unbind` thì không cần tự quản lý context và converter; template đã xử lý các phần này.

**Không sửa `ContextSource.setUserDn`/`setPassword` trên bean singleton theo từng request.** Dùng một writer service account được cấu hình riêng, hoặc một cơ chế identity có kiểm soát nếu thật sự cần.

## 11. Xóa qua Spring Data LDAP repository

`LdapRepository` mở rộng `ListCrudRepository`/`CrudRepository` và có các method kế thừa:

- `delete(entity)`
- `deleteById(Name id)`
- `deleteAll(Iterable)`
- `deleteAllById(Iterable)`
- `deleteAll()`

Ví dụ entity:

~~~java
import javax.naming.Name;

import org.springframework.ldap.odm.annotations.Attribute;
import org.springframework.ldap.odm.annotations.Entry;
import org.springframework.ldap.odm.annotations.Id;

@Entry(
    base = "ou=people",
    objectClasses = {
        "top", "person", "organizationalPerson", "inetOrgPerson"
    }
)
public class DirectoryPerson {

    @Id
    private Name dn;

    @Attribute(name = "uid")
    private String uid;

    @Attribute(name = "cn")
    private String commonName;

    @Attribute(name = "sn")
    private String surname;

    // Constructor/getter/setter trong ứng dụng thực tế.
}
~~~

Repository:

~~~java
import org.springframework.data.ldap.repository.LdapRepository;

public interface DirectoryPersonRepository
        extends LdapRepository<DirectoryPerson> {
}
~~~

Xóa theo ID:

~~~java
Name dn = LdapNameBuilder.newInstance("ou=people")
        .add("uid", validatedUid)
        .build();

personRepository.deleteById(dn);
~~~

Xóa entity:

~~~java
DirectoryPerson person = personRepository.findById(dn)
        .orElseThrow(PersonNotFoundException::new);

personRepository.delete(person);
~~~

### Repository delete có xóa đệ quy không?

Không nên giả định các method CRUD repository sẽ tự xóa subtree. `deleteById` xóa entry tương ứng với ID theo implementation repository; nó không phải API để yêu cầu xóa tất cả descendants.

Nếu entry có children, server có thể từ chối Delete như với `LdapTemplate.unbind(dn)`. Nếu cần recursive delete, dùng một workflow được thiết kế rõ ràng và kiểm thử riêng.

### Cẩn trọng với deleteAll

`repository.deleteAll()` có thể xóa mọi entity mà repository quản lý. Không gọi nó trong endpoint người dùng thông thường hoặc khi chưa giới hạn repository/base/filter. Với batch delete, dùng danh sách ID đã được kiểm tra và audit; giới hạn kích thước batch để tránh tải lớn và partial failure khó xử lý.

## 12. ACL: quyền xóa nằm ở LDAP server

Phân quyền ở Java là cần thiết nhưng không thay thế ACL trên directory.

### 12.1. OpenLDAP: entry và children

Trong OpenLDAP, ACL có hai pseudo-attribute quan trọng:

- `entry`: kiểm soát quyền trên entry đích.
- `children`: kiểm soát quyền đối với tập entry con trực tiếp của một entry.

Theo tài liệu OpenLDAP, để Delete một entry, requester cần `write` trên `entry` của entry đích **và** `write` trên `children` của parent entry.

Ví dụ minh họa chính sách (không phải cấu hình production hoàn chỉnh):

~~~text
# Cho phép service deleter thao tác trên entry trong OU people.
access to dn.subtree="ou=people,dc=example,dc=org" attrs=entry
    by dn.exact="cn=svc-person-deleter,ou=service,dc=example,dc=org" write
    by * none

# Cho phép xóa entry con trực tiếp từ parent trong phạm vi people.
access to dn.subtree="ou=people,dc=example,dc=org" attrs=children
    by dn.exact="cn=svc-person-deleter,ou=service,dc=example,dc=org" write
    by * none
~~~

Đây chỉ là **minh họa hai quyền cần có**. Phải rà soát thứ tự ACL, các rule hiện có, parent của entry, quyền Search/Read phục vụ workflow và chính sách ở database cụ thể. Không dán hai rule này vào production mà chưa review toàn bộ cấu hình.

### 12.2. Active Directory và directory khác

Active Directory có access control entry và extended rights riêng; không dùng cú pháp OpenLDAP `olcAccess` cho AD. Một Delete có thể cần quyền Delete trên object hoặc quyền Delete Child tại parent, tùy loại đối tượng và policy. Kiểm thử bằng đúng account dịch vụ và OU thực tế.

### 12.3. Không dùng rootdn/admin toàn quyền cho ứng dụng

Không dùng OpenLDAP `rootdn` hoặc Domain Admin làm credential chạy endpoint xóa thông thường. Root/admin có thể vượt qua các hạn chế ACL thông thường và khiến test không phản ánh quyền thật của ứng dụng.

Tạo service account có quyền Delete đúng subtree cần thiết. Nếu ứng dụng có chức năng chỉ đọc và chức năng xóa, tách Bind DN/credential để tránh một lỗi ở reader API trở thành quyền xóa toàn directory.

## 13. Xóa entry có tham chiếu từ group hoặc entry khác

Một entry người dùng có thể được tham chiếu bằng DN trong nhiều thuộc tính:

~~~ldif
dn: cn=engineering,ou=groups,dc=example,dc=org
objectClass: top
objectClass: groupOfNames
cn: engineering
member: uid=lan,ou=people,dc=example,dc=org
member: uid=minh,ou=people,dc=example,dc=org
~~~

Nếu xóa Lan, thuộc tính `member` trong group có thể vẫn chứa DN của Lan, tùy server và cơ chế referential integrity được cấu hình.

### 13.1. LDAP không có cascade delete phổ quát

LDAP DeleteRequest xóa entry mục tiêu. Giao thức không định nghĩa quy tắc chung rằng mọi attribute DN ở các entry khác phải tự động bị xóa theo.

Vì vậy, đừng mặc định xóa `uid=lan` sẽ tự động:
- Xóa Lan khỏi tất cả group.
- Cập nhật mọi `manager`, `owner`, `seeAlso` hoặc custom DN-valued attribute.
- Xóa các quan hệ ở ứng dụng khác.
- Thu hồi session/token đã được cấp trước đó.

Một số server có tính năng riêng. Ví dụ OpenLDAP có overlay `slapo-refint` có thể duy trì tham chiếu trên các attribute được cấu hình. Các linked attribute trong AD cũng có semantics riêng. Hành vi cụ thể phải được kiểm tra theo server, schema và cấu hình; không coi đó là bảo đảm chung của `unbind`.

### 13.2. groupOfNames yêu cầu member

Theo schema ứng dụng LDAP trong RFC 4519, `groupOfNames` yêu cầu thuộc tính `member`. Nếu quy trình xóa user loại bỏ DN của user khỏi group và đó là thành viên cuối cùng, group có thể không còn đáp ứng schema.

Nghiệp vụ cần quyết định rõ:
- Xóa group nếu group không còn thành viên và group đó không còn cần thiết.
- Chuyển sang mô hình nhóm/schema cho phép group rỗng nếu chính sách cho phép.
- Thay thế member bằng một entry hợp lệ theo thiết kế.
- Giữ user ở trạng thái disabled/tombstone trong một thời gian thay vì xóa ngay.

Không để một job dọn membership tự động xóa giá trị cuối cùng rồi giả định entry group vẫn hợp lệ.

### 13.3. Workflow xóa user có quản lý membership

Một quy trình nghiệp vụ có thể gồm:

1. Xác thực actor có quyền xóa user.
2. Tìm các nhóm/tham chiếu liên quan trong phạm vi được phép.
3. Kiểm tra các ràng buộc nghiệp vụ và chính sách retention.
4. Xóa hoặc cập nhật membership theo schema của server.
5. Xác minh group còn hợp lệ.
6. Xóa entry người dùng bằng `unbind`.
7. Ghi audit và đối soát nếu bất kỳ bước nào thất bại.

Đây là **nhiều operation LDAP**, không phải một Delete nguyên tử. Nếu bước 5 hoặc 6 lỗi sau khi bước 4 đã thành công, cần có workflow phục hồi/đối soát.

## 14. Xóa thật hay soft delete?

LDAP không cung cấp một cờ soft delete thống nhất cho mọi directory. Có hai chiến lược thường gặp:

| Chiến lược | Cách làm | Khi phù hợp |
| --- | --- | --- |
| Hard delete | Dùng `unbind(dn)` để xóa entry thật. | Chính sách retention cho phép xóa vật lý và các tham chiếu đã được xử lý. |
| Soft delete/tombstone | Đánh dấu trạng thái như `accountStatus=disabled` hoặc thuộc tính nghiệp vụ đã định nghĩa. | Cần giữ lịch sử, khôi phục hoặc trì hoãn việc xóa vật lý. |

Tên attribute và semantics phụ thuộc schema/directory. Không tự thêm `deleted=true` nếu schema chưa cho phép hoặc các ứng dụng khác không hiểu thuộc tính đó.

### Ví dụ soft delete bằng modify

~~~java
ModificationItem disable = new ModificationItem(
        DirContext.REPLACE_ATTRIBUTE,
        new BasicAttribute("accountStatus", "disabled"));

ldapTemplate.modifyAttributes(
        personDn,
        new ModificationItem[] { disable });
~~~

Đoạn code chỉ minh họa nếu schema và ứng dụng thực tế đã định nghĩa `accountStatus`. Trong Active Directory, trạng thái disabled thường được biểu diễn theo schema/thuộc tính riêng của AD; không dùng ví dụ generic này như một cấu hình AD.

Soft delete cũng phải được áp ACL, kiểm tra authentication và cập nhật quyền truy cập. Một entry bị đánh dấu disabled nhưng vẫn được các ứng dụng khác coi là hoạt động là một lỗi tích hợp.

## 15. Transaction, tính nhất quán và khả năng phục hồi

Một lệnh `LdapTemplate.unbind(dn)` cho một entry là một thao tác Delete đơn lẻ. Nhưng một workflow gồm nhiều bước (xóa group references, xóa user, xóa OU) không tự trở thành transaction nguyên tử.

### 15.1. Không mặc định @Transactional sẽ hoàn tác Delete

Có thể có transaction extension hoặc cơ chế compensating transaction tùy cấu hình, nhưng không nên giả định một `@Transactional` chung sẽ rollback mọi thao tác LDAP.

Khi đã nhận Delete success, entry đã bị directory loại bỏ. Nếu request tiếp theo thất bại, Spring không thể tự khôi phục entry cùng tất cả attributes nếu không có dữ liệu snapshot/backup và workflow phục hồi.

### 15.2. Recursive delete có thể partial

`unbind(dn, true)` có thể thực hiện nhiều lần list/delete. Nếu một child bị từ chối hoặc server ngắt kết nối giữa chừng, một số entry đã bị xóa và một số entry còn lại.

Hãy thiết kế kết quả batch với trạng thái như:
- `COMPLETED`: toàn bộ mục tiêu đã được xóa và đối soát.
- `PARTIAL`: một phần descendants đã bị xóa; cần tiếp tục/khôi phục có kiểm soát.
- `FAILED`: không hoàn thành; cần xác định trạng thái thực trước retry.

Không trả HTTP 204 cho một workflow recursive chưa hoàn tất chỉ vì một số child đã biến mất.

### 15.3. Backup, tombstone và audit

Trước khi xóa dữ liệu có giá trị cao, chính sách vận hành có thể yêu cầu:
- Snapshot/export entry cần xóa theo quyền phù hợp.
- Lưu DN, loại đối tượng, actor, request ID và thời điểm.
- Không log mật khẩu hoặc toàn bộ dữ liệu cá nhân không cần thiết.
- Có backup/restore hoặc quy trình tạo lại entry.
- Ghi rõ trạng thái thực tế sau lỗi network không xác định kết quả.

Audit phải phản ánh **server đã xác nhận xóa**, không chỉ việc ứng dụng đã gửi request.

## 16. Phân loại lỗi và ánh xạ sang HTTP

Một số LDAP result code quan trọng:

| LDAP result code | Tên | Ý nghĩa |
| ---: | --- | --- |
| 0 | `success` | Delete thành công. |
| 32 | `noSuchObject` | DN mục tiêu không tồn tại. |
| 34 | `invalidDNSyntax` | DN không hợp lệ. |
| 50 | `insufficientAccessRights` | Bind DN không đủ quyền. |
| 51 | `busy` | Server bận. |
| 52 | `unavailable` | Server hoặc subsystem không khả dụng. |
| 53 | `unwillingToPerform` | Server từ chối thực hiện theo policy/điều kiện. |
| 66 | `notAllowedOnNonLeaf` | Entry còn subordinate entries. |

Spring LDAP thường dịch JNDI exception sang runtime exception riêng, ví dụ:
- `NameNotFoundException`.
- `ContextNotEmptyException`.
- `NoPermissionException`.
- `CommunicationException`.
- `ServiceUnavailableException`.
- `InvalidNameException`.

Mapping chính xác phụ thuộc JNDI provider và server. Không parse `getMessage()` để đoán result code; giữ cause để chẩn đoán nội bộ.

### HTTP status gợi ý

| Trạng thái nghiệp vụ | HTTP có thể dùng |
| --- | ---: |
| Xóa thành công | 204 |
| DN không tồn tại theo strict policy | 404 |
| Entry còn children, không cho xóa recursive | 409 |
| Caller không có quyền API | 403 |
| Directory service unavailable | 503 |
| Timeout gateway | 504 |
| Input UID/DN sai | 400 |
| ACL của service account bị cấu hình thiếu | 500 hoặc 503 theo hợp đồng nội bộ, không trả raw diagnostic |

Đây là lựa chọn hợp đồng ứng dụng, không phải quy tắc chuyển mã LDAP sang HTTP bắt buộc.

### Ví dụ domain error handler

~~~java
@RestControllerAdvice
public class PersonDeleteErrorHandler {

    public record ApiError(String code, String message) {}

    @ExceptionHandler(PersonNotFoundException.class)
    ResponseEntity<ApiError> notFound() {
        return ResponseEntity.status(404).body(
                new ApiError(
                        "PERSON_NOT_FOUND",
                        "The requested person does not exist"));
    }

    @ExceptionHandler(PersonHasChildrenException.class)
    ResponseEntity<ApiError> hasChildren() {
        return ResponseEntity.status(409).body(
                new ApiError(
                        "ENTRY_HAS_CHILDREN",
                        "The entry cannot be deleted while children exist"));
    }
}
~~~

Không trả `exception.getMessage()` hoặc `getExplanation()` ra client. Những chuỗi này có thể tiết lộ DN, server, cấu hình ACL hoặc dữ liệu nội bộ.

## 17. Kiểm thử bằng JUnit và LDAP server

Xóa dữ liệu phải được kiểm thử với directory dành riêng. Không chạy test Delete trên LDAP production hoặc dữ liệu người dùng thật.

### 17.1. Fixture LDIF

Tạo một user lá:

~~~ldif
dn: uid=delete-me,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: delete-me
cn: Delete Me
sn: Me
~~~

Và một cây có child:

~~~ldif
dn: uid=parent-test,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: parent-test
cn: Parent Test
sn: Test

dn: cn=addresses,uid=parent-test,ou=people,dc=example,dc=org
objectClass: top
objectClass: organizationalUnit
ou: addresses
~~~

Fixture thứ hai dùng để xác minh xóa một entry có child sẽ bị từ chối nếu không dùng recursive overload. Schema test cần hỗ trợ objectClass và naming context tương ứng.

### 17.2. Xóa một entry lá

~~~java
import static org.junit.jupiter.api.Assertions.*;

import javax.naming.Name;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.ldap.NameNotFoundException;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

@SpringBootTest
class PersonUnbindIntegrationTest {

    @Autowired
    LdapTemplate ldapTemplate;

    @Test
    void deletesLeafEntry() {
        Name dn = LdapNameBuilder.newInstance("ou=people")
                .add("uid", "delete-me")
                .build();

        ldapTemplate.unbind(dn);

        assertThrows(
                NameNotFoundException.class,
                () -> ldapTemplate.lookup(dn)
        );
    }
}
~~~

Test phải được chạy sau khi fixture đã được nạp. Nếu test chạy nhiều lần, tạo lại fixture trước mỗi lần hoặc dùng dữ liệu có tên duy nhất.

### 17.3. Entry còn child phải bị từ chối

~~~java
@Test
void refusesToDeleteNonLeafEntry() {
    Name parentDn = LdapNameBuilder.newInstance("ou=people")
            .add("uid", "parent-test")
            .build();

    assertThrows(
            org.springframework.ldap.ContextNotEmptyException.class,
            () -> ldapTemplate.unbind(parentDn)
    );

    // Parent vẫn còn vì DeleteRequest không xóa non-leaf.
    assertDoesNotThrow(() -> ldapTemplate.lookup(parentDn));
}
~~~

Nếu server/provider ánh xạ lỗi khác, kiểm tra cause/result code thực tế và điều chỉnh test theo directory được hỗ trợ. Không làm test pass bằng cách bỏ kiểm tra entry còn tồn tại.

### 17.4. Recursive delete trong fixture test

~~~java
@Test
void recursiveUnbindDeletesChildrenAndParent() {
    Name parentDn = LdapNameBuilder.newInstance("ou=people")
            .add("uid", "parent-test")
            .build();

    ldapTemplate.unbind(parentDn, true);

    assertThrows(
            NameNotFoundException.class,
            () -> ldapTemplate.lookup(parentDn)
    );
}
~~~

Trong một integration suite thực tế, cần kiểm tra thêm DN child `cn=addresses` không còn. Không dùng recursive delete để dọn một base OU dùng chung cho nhiều test.

### 17.5. Ma trận kiểm thử

| Ca kiểm thử | Kết quả mong đợi |
| --- | --- |
| Xóa DN lá có tồn tại | Thành công. |
| Xóa lại DN đã mất | `NameNotFoundException` hoặc kết quả idempotent theo service policy. |
| Xóa DN còn children với unbind mặc định | Bị từ chối. |
| Recursive delete subtree test | Xóa descendants rồi xóa root nếu mọi bước thành công. |
| Reader Bind DN cố Delete | LDAP từ chối theo ACL. |
| Writer Bind DN xóa đúng OU được cấp | Thành công. |
| Writer xóa entry ngoài OU | Bị ACL từ chối. |
| DN input có ký tự đặc biệt | DN builder tạo DN đúng, không xóa nhầm entry. |
| UID không hợp lệ | Bị validation chặn trước LDAP. |
| Caller thiếu authority | HTTP 403, LDAP không được gọi. |
| Entry bị xóa đồng thời bởi request khác | Một request thành công, request còn lại xử lý not found theo policy. |
| Server ngắt kết nối sau khi gửi Delete | Đối soát trạng thái trước khi retry. |
| Parent có child được thêm đồng thời | Delete parent có thể bị từ chối; không báo thành công giả. |
| Group còn tham chiếu DN user | Workflow tham chiếu xử lý theo policy; không giả định cascade. |
| TLS certificate sai | Kết nối thất bại, không fallback plaintext. |
| Recursive delete gặp ACL lỗi ở một child | Ghi nhận partial failure, không tuyên bố subtree đã xóa hết. |

### 17.6. Test authorization HTTP

Với Spring Security Test, kiểm tra caller không có authority không thể gọi service xóa. Ví dụ:

~~~java
@Test
@WithMockUser(authorities = "DIRECTORY_READ")
void readerCannotDeletePerson() throws Exception {
    mvc.perform(delete("/api/v1/people/lan")
            .with(csrf()))
       .andExpect(status().isForbidden());
}
~~~

Ví dụ giả định endpoint đã cấu hình CSRF phù hợp và dùng Spring Security method/request authorization. Cần xác minh service không được gọi khi caller thiếu quyền; một HTTP 403 do CSRF không chứng minh authorization role đã đúng.

## 18. Thực hành bằng ldapdelete

Trong môi trường OpenLDAP test, có thể dùng `ldapdelete` để xác minh Delete operation:

~~~bash
ldapdelete -x \
  -H ldaps://ldap.example.org:636 \
  -D "cn=svc-person-deleter,ou=service,dc=example,dc=org" -W \
  "uid=delete-me,ou=people,dc=example,dc=org"
~~~

- `-H` chọn endpoint LDAPS.
- `-D` là Bind DN có quyền Delete trong phạm vi được cấp.
- `-W` yêu cầu nhập mật khẩu qua prompt.
- Tham số cuối là DN đầy đủ của entry cần xóa.

Nếu entry còn children, lệnh có thể thất bại với `notAllowedOnNonLeaf`. `ldapdelete` thông thường không tự xóa toàn bộ subtree.

**Không** truyền password trực tiếp qua command line hoặc chạy lệnh này trên DN production khi chưa có change approval và backup theo chính sách vận hành.

## 19. Sai lầm thường gặp

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Nghĩ `LdapTemplate.unbind` là logout | Xóa nhầm entry người dùng. | Đóng context/session bằng API close phù hợp. |
| Nghĩ LDAP Delete tự cascade | Parent còn child nên Delete thất bại. | Xóa leaf trước hoặc workflow recursive được kiểm soát. |
| Nhận DN tùy ý từ HTTP | Có thể xóa ngoài subtree được phép. | Nhận UID/business ID và xây DN cố định. |
| Ghép DN bằng chuỗi | RDN đặc biệt có thể bị parse sai. | Dùng `LdapNameBuilder`. |
| Dùng `unbind(dn, true)` mặc định | Có thể xóa cả cây ngoài ý muốn. | Chỉ dùng trong workflow riêng, scope hẹp. |
| Nghĩ recursive delete là một LDAP request nguyên tử | Có thể partial delete khi lỗi giữa chừng. | Audit, đối soát và phục hồi. |
| Search exists rồi mới Delete và tin kết quả | Race condition giữa hai request. | Thực hiện Delete trực tiếp và xử lý response. |
| Bắt mọi exception rồi trả 204 | Che lỗi ACL/network và báo thành công giả. | Chỉ áp policy idempotent cho NameNotFound. |
| Cho service account reader quyền Delete | Lỗi ở API đọc có thể xóa dữ liệu. | Tách Bind DN và ACL theo chức năng. |
| Dùng rootdn/Domain Admin | Bỏ qua ranh giới quyền tối thiểu. | Service account giới hạn OU/operation. |
| Không xử lý group references | Có thể để lại DN tham chiếu không còn tồn tại. | Referential integrity/workflow riêng. |
| Dùng repository.deleteAll() tùy tiện | Xóa nhiều entry ngoài ý muốn. | Dùng ID cụ thể và batch được giới hạn. |
| Cho rằng @Transactional tự khôi phục LDAP Delete | Dữ liệu đã xóa không tự quay lại. | Snapshot, compensation và reconciliation. |
| Retry ngay khi network timeout | Có thể che kết quả Delete đã thành công hoặc phát sinh lỗi khác. | Đọc đối soát trước khi retry. |
| Không test bằng ACL thật | Mã có thể chạy với admin nhưng thất bại ở production. | Test đúng Bind DN và server policy. |

## 20. Checklist trước khi đưa Delete vào production

| Hạng mục | Tiêu chí đạt |
| --- | --- |
| DN | Xây từ business ID đã validate, base cố định. |
| Scope | Chỉ cho phép xóa trong subtree đã phê duyệt. |
| Entry children | Mặc định chỉ xóa leaf; recursive có workflow riêng. |
| Authorization | Caller có authority Delete phù hợp. |
| LDAP ACL | Service Bind DN có đúng quyền entry/parent children hoặc quyền server tương ứng. |
| Credentials | Không dùng rootdn/Domain Admin cho API thông thường. |
| References | Xác định group membership và DN references trước khi xóa user. |
| Schema | Kiểm tra ràng buộc objectClass, ví dụ groupOfNames.member. |
| Transaction | Không giả định nhiều Delete là nguyên tử. |
| Recovery | Có backup/retention/tombstone hoặc quy trình phục hồi phù hợp. |
| Idempotency | Quy định rõ response khi DN không tồn tại. |
| Audit | Ghi actor, target ID, request ID, kết quả và thời điểm. |
| Security | TLS, secret manager, không log credential/entry nhạy cảm. |
| Testing | Có test leaf, non-leaf, recursive, ACL, concurrency và failure. |
| Operations | Có đối soát sau lỗi mạng hoặc partial recursive delete. |

## 21. Bài tập thực hành

**Bài 1 — Xóa entry lá.** Tạo `uid=delete-me` dưới `ou=people`. Xây DN bằng `LdapNameBuilder` và xóa bằng `LdapTemplate.unbind(Name)`. Lookup lại để xác minh entry không còn.

**Bài 2 — Entry còn children.** Tạo `uid=parent-test` với entry con `cn=addresses`. Gọi `unbind(parentDn)` và quan sát lỗi. Giải thích vì sao RFC 4511 chỉ cho Delete entry lá.

**Bài 3 — Recursive unbind.** Trên fixture riêng, gọi `unbind(parentDn, true)`. Xác minh child và parent đều biến mất. Mô tả các request/partial failure có thể xảy ra nếu một child bị ACL từ chối.

**Bài 4 — DN an toàn.** Thử UID có dấu phẩy hoặc dấu cộng trong fixture. So sánh ghép chuỗi với `LdapNameBuilder` và chứng minh DN đúng được tạo.

**Bài 5 — Repository delete.** Viết `LdapRepository` cho `DirectoryPerson` và xóa bằng `deleteById(Name)`. So sánh với `LdapTemplate.unbind`; kiểm tra rằng repository delete không tự xóa subtree.

**Bài 6 — ACL.** Dùng reader Bind DN thử Delete fixture; server phải từ chối. Dùng deleter account có quyền đúng trong OU test để xóa cùng fixture.

**Bài 7 — Group membership.** Tạo group `groupOfNames` có hai member. Xóa một user và kiểm tra referential integrity theo server. Sau đó thử group còn một member, đánh giá quy tắc schema khi loại bỏ member cuối cùng.

**Bài 8 — Idempotency.** Gọi DELETE hai lần cùng UID. Thiết kế hợp đồng 204/404 và bảo đảm lỗi ACL/network không bị coi là đã xóa.

**Bài 9 — Concurrency.** Hai request đồng thời xóa cùng một DN. Xác định response của request thứ hai và cách audit không ghi hai sự kiện thành công giả.

**Bài 10 — Partial subtree.** Cố ý để một child bị ACL từ chối trong recursive delete ở directory test. Xác minh một số entry có thể đã bị xóa và đề xuất quy trình reconciliation.

## 22. Câu hỏi tự đánh giá

1. `LdapTemplate.unbind(dn)` xóa entry hay đóng phiên LDAP?
2. LDAP protocol `UnbindRequest` khác JNDI `Context.unbind(name)` thế nào?
3. Vì sao LDAP DeleteRequest chỉ xóa entry lá?
4. `notAllowedOnNonLeaf (66)` báo tình huống gì?
5. DN tương đối được dùng thế nào khi `ContextSource` có base?
6. Vì sao nên xây DN bằng `LdapNameBuilder`?
7. `unbind(Name)` và `unbind(Name, true)` khác nhau ra sao?
8. Vì sao recursive unbind có thể tạo partial delete?
9. `LdapRepository.deleteById(Name)` có tự xóa tất cả descendants không?
10. Vì sao không nên nhận arbitrary DN từ HTTP client?
11. OpenLDAP cần quyền gì trên entry và parent để Delete?
12. Vì sao ACL server vẫn cần dù service có `@PreAuthorize`?
13. LDAP có cascade delete cho mọi DN-valued reference không?
14. `groupOfNames` có thể tồn tại hợp lệ mà không có `member` không?
15. Vì sao việc xóa user có thể cần cập nhật group membership trước?
16. Khi network timeout sau Delete, vì sao cần đối soát trước retry?
17. `@Transactional` có tự khôi phục entry LDAP đã xóa không?
18. Khi nào nên dùng soft delete/tombstone thay cho unbind?
19. Làm sao kiểm thử một service account không thể xóa ngoài OU?
20. Những trường hợp nào cần dùng recursive delete thay vì xóa entry lá?

**Ghi nhớ:** `unbind(dn)` trong Spring LDAP có nghĩa **xóa entry khỏi directory**. LDAP DeleteRequest chuẩn chỉ xóa entry lá; `unbind(dn, true)` là tiện ích xóa descendants đệ quy của Spring LDAP và có thể partial khi một bước thất bại. Hãy xây DN an toàn, giới hạn subtree, kiểm tra authorization và ACL, xử lý tham chiếu nhóm, giữ audit và không coi Delete nhiều bước là transaction nguyên tử.

### Tài liệu tham khảo

- [Spring LDAP — LdapOperations API](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/LdapOperations.html): `unbind(Name)`, `unbind(Name, boolean)`, `delete(Object)` và ngữ nghĩa xóa entry.
- [Spring LDAP — LdapTemplate API](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/LdapTemplate.html): implementation `unbind` và recursive deletion.
- [Spring Data LDAP — LdapRepository API](https://docs.spring.io/spring-data/ldap/reference/api/java/org/springframework/data/ldap/repository/LdapRepository.html): repository kế thừa `delete`/`deleteById`.
- [Spring Data LDAP — Repositories](https://docs.spring.io/spring-ldap/reference/repositories.html): cấu hình repository và yêu cầu ODM.
- [RFC 4511 — LDAP: The Protocol, Section 4.3 and 4.8](https://www.rfc-editor.org/rfc/rfc4511): Unbind operation kết thúc session; Delete operation chỉ áp dụng cho leaf entry và result code.
- [Java SE — Context API](https://docs.oracle.com/en/java/javase/21/docs/api/java.naming/javax/naming/Context.html): `unbind(name)` và `close()` trong JNDI.
- [Java SE — DirContext API](https://docs.oracle.com/en/java/javase/21/docs/api/java.naming/javax/naming/directory/DirContext.html): thao tác directory và exception JNDI.
- [OpenLDAP 2.6 Administrator's Guide — Access Control](https://www.openldap.org/doc/admin26/access-control.html): quyền `entry` và `children` cần thiết cho Add/Delete, ACL theo DN và thứ tự rule.
- [OpenLDAP — Referential Integrity Overlay (slapo-refint)](https://www.openldap.org/software/man.cgi?query=slapo-refint): cơ chế duy trì một số tham chiếu DN khi entry bị xóa hoặc rename.
- [RFC 4519 — LDAP: Schema for User Applications](https://www.rfc-editor.org/rfc/rfc4519): schema `groupOfNames` và thuộc tính `member`.
- [RFC 4514 — LDAP: String Representation of Distinguished Names](https://www.rfc-editor.org/rfc/rfc4514): biểu diễn và escaping DN.
- [Spring LDAP — LdapNameBuilder API](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/support/LdapNameBuilder.html): xây DN theo cấu trúc.
