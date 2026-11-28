# Tách mô hình dữ liệu thư mục khỏi mô hình API

## Mục tiêu bài học

Trong **SPRING_DATA_LDAP**, ứng dụng Java đọc và ghi dữ liệu LDAP qua **Spring Data LDAP repository** hoặc **LdapTemplate**. LDAP lưu entry theo **DN**, **objectClass**, schema và các thuộc tính có thể có nhiều giá trị. Trong khi đó, API HTTP cần một hợp đồng ổn định, dễ hiểu và chỉ công bố những trường mà client được phép sử dụng.

Nếu trả thẳng một đối tượng ODM như **PersonEntry** từ controller, API sẽ phụ thuộc vào cấu trúc directory: DN có thể bị lộ, tên thuộc tính LDAP rò rỉ ra JSON, việc thay schema làm thay đổi response và các trường nội bộ có thể bị công bố. Bài này hướng dẫn tách ba lớp:

1. **LDAP persistence model** — mô hình ánh xạ entry, phục vụ Spring LDAP ODM/repository.
2. **Application/domain model** — mô hình nghiệp vụ mà service sử dụng, không phụ thuộc tên thuộc tính LDAP hay JSON.
3. **API request/response DTO** — hợp đồng dữ liệu HTTP, được kiểm soát theo use case và quyền truy cập.

Sau bài học, bạn có thể:

- Giải thích vì sao **DN, objectClass và LDAP attribute** không nên tự động trở thành trường của API.
- Ánh xạ dữ liệu theo chiều **LDAP entry → domain model → response DTO** và **request DTO → command/domain → LDAP modification**.
- Dùng **@Entry, @Id, @Attribute** cho ODM, repository cho truy vấn thông dụng và **LdapTemplate** cho projection/thuộc tính nhiều giá trị.
- Xử lý thuộc tính thiếu, nhiều giá trị, giá trị operational và dữ liệu không có trong schema.
- Thiết kế **PUT/PATCH** rõ ngữ nghĩa, không vô tình xóa dữ liệu LDAP khi field bị bỏ qua.
- Không để API ghi trực tiếp object LDAP hoặc cho client điều khiển DN, objectClass, base DN và raw filter.
- Kiểm thử mapping, validation, authorization, lỗi LDAP và thay đổi schema độc lập với controller.

## 1. Vì sao không trả thẳng LDAP entity qua REST?

Giả sử LDAP entry của An:

~~~ldif
dn: uid=an,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: an
cn: An Tran
sn: Tran
mail: an@example.org
telephoneNumber: +84-28-5550-0101
~~~

Một ODM class có thể biểu diễn entry này:

~~~java
@Entry(
    base = "ou=people",
    objectClasses = {"top", "person", "organizationalPerson",
                     "inetOrgPerson"}
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
}
~~~

Nếu controller trả trực tiếp object này:

~~~java
@GetMapping("/{uid}")
public PersonEntry get(@PathVariable String uid) {
    return repository.findByUid(uid).get(0);
}
~~~

Đây là ví dụ **không nên dùng**. Ngoài việc trả thẳng persistence object, gọi get(0) còn âm thầm chọn một entry nếu username trùng trong search scope. Contract HTTP bị buộc vào chi tiết lưu trữ; tùy serializer và cấu trúc class, client có thể nhìn thấy field nội bộ như dn, commonName, surname hoặc các trường mới được thêm vào ODM sau này. Thay đổi annotation, loại Name, mapping hoặc schema có thể làm JSON đổi ngoài dự kiến.

Các rủi ro chính:

| Rủi ro | Hậu quả |
| --- | --- |
| **Lộ DN** | Công bố naming context, OU, username nội bộ hoặc cấu trúc tổ chức |
| **Lộ thuộc tính LDAP nội bộ** | Client biết thông tin không thuộc hợp đồng API, có thể gồm trạng thái hoặc dữ liệu nhạy cảm |
| **Schema coupling** | Đổi objectClass/attribute kéo theo thay đổi JSON và client |
| **Over-posting** | Client gửi thêm dn, objectClass, member, userPassword hoặc field ngoài use case |
| **Sai cardinality** | LDAP attribute nhiều giá trị bị ép thành một string hoặc mất dữ liệu |
| **Sai ngữ nghĩa** | cn, uid, mail bị dùng như ID/API field dù chúng có vòng đời và quy tắc khác |
| **Khó version API** | Thay đổi directory làm phá vỡ client đang dùng |

**Nguyên tắc:** repository/ODM chịu trách nhiệm lưu trữ; service/domain chịu trách nhiệm nghiệp vụ; DTO chịu trách nhiệm giao tiếp HTTP. Mỗi lớp có thể chuyển đổi rõ ràng sang lớp kế tiếp.

## 2. Kiến trúc mapping ba lớp

Các ví dụ HTTP dùng Spring Boot 3 và Bean Validation. Dependency thường cần có:

~~~groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-ldap")
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.boot:spring-boot-starter-validation")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}
~~~

~~~mermaid
flowchart LR
    LDAP["LDAP server<br/>DN, objectClass, attributes"] --> ODM["LDAP ODM entity<br/>PersonEntry"]
    ODM --> DOMAIN["Application model<br/>DirectoryUser"]
    DOMAIN --> DTO["API response DTO<br/>UserResponse"]
    DTO --> JSON["JSON / HTTP"]
    JSON --> REQUEST["Request DTO<br/>UpdateContactRequest"]
    REQUEST --> COMMAND["Application command<br/>UpdateContact"]
    COMMAND --> SERVICE["Application service"]
    SERVICE --> ODM
    SERVICE --> TEMPLATE["LdapTemplate<br/>targeted LDAP modifications"]
    TEMPLATE --> LDAP
~~~

| Lớp | Ví dụ | Trách nhiệm | Điều không nên làm |
| --- | --- | --- | --- |
| **LDAP persistence model** | PersonEntry | Ánh xạ DN, objectClass, thuộc tính directory | Làm response DTO hoặc chứa logic HTTP |
| **Domain/application model** | DirectoryUser | Biểu diễn user theo nghiệp vụ ứng dụng | Phụ thuộc annotation ODM hoặc JSON |
| **API DTO** | UserResponse, UpdateContactRequest | Định nghĩa field được đọc/ghi qua HTTP | Nhận raw DN, objectClass hoặc LDAP filter tùy ý |
| **Mapper/assembler** | DirectoryUserMapper, UserApiMapper | Chuyển đổi giữa các mô hình | Gọi network hoặc chứa business authorization phức tạp |

Không phải ứng dụng nào cũng cần đủ ba class cho mọi endpoint. Nhưng **ranh giới giữa storage schema và API contract phải có chủ đích**. Một endpoint nhỏ có thể dùng mapper gọn; một hệ thống nhiều use case nên tách package/lớp rõ ràng.

## 3. Xác định hợp đồng API trước khi ánh xạ LDAP

Ví dụ API công bố hồ sơ cơ bản:

~~~json
{
  "username": "an",
  "displayName": "An Tran",
  "email": "an@example.org",
  "phoneNumber": "+84-28-5550-0101"
}
~~~

Response không cần công bố:

- DN đầy đủ uid=an,ou=people,dc=example,dc=org.
- objectClass, naming context, bind DN hoặc thông tin kết nối.
- Thuộc tính nội bộ như userPassword, entryUUID, modifyTimestamp, entryCSN.
- Mọi thuộc tính LDAP mà service account đọc được nhưng caller không được phép xem.

Hãy xác định mỗi trường API:

| API field | Nguồn dữ liệu trong lab | Quy tắc |
| --- | --- | --- |
| username | LDAP uid | Chuỗi định danh theo chính sách ứng dụng |
| displayName | LDAP cn | Tên hiển thị, không dùng làm khóa |
| email | LDAP mail | Ví dụ này áp dụng quy ước một email chính |
| phoneNumber | LDAP telephoneNumber | Có thể không tồn tại |

Trong directory thực tế, mail và telephoneNumber có thể chứa nhiều giá trị tùy schema/server. Nếu nghiệp vụ cho phép nhiều email/số điện thoại, API phải biểu diễn List<String> và mapping phải giữ đủ giá trị; **không lấy phần tử đầu tiên rồi bỏ phần còn lại**.

### 3.1. Không để API quyết định DN

Một API như:

~~~http
PUT /api/directory/entries/uid=an,ou=people,dc=example,dc=org
~~~

đã đưa cấu trúc LDAP vào URL. Điều này vừa rò rỉ thông tin directory, vừa tạo nguy cơ caller điều khiển entry ngoài phạm vi được phép nếu authorization kiểm tra không đầy đủ.

Ưu tiên route theo một định danh nghiệp vụ được kiểm soát:

~~~http
GET /api/users/an
PUT /api/users/an/contact
~~~

Service sẽ resolve username sang entry/DN trong **search base và tenant/OU được phép**. Nếu username không duy nhất, xử lý ambiguity theo policy; không chọn ngẫu nhiên một entry.

Nếu hệ thống cần ID ổn định qua rename, nên dùng **application ID** hoặc server-managed ID có semantics đã xác minh, thay vì giả định DN bất biến.

## 4. LDAP ODM entity: mô hình cho lưu trữ

Ví dụ directory dùng inetOrgPerson, với ứng dụng áp dụng chính sách **một email chính và một số điện thoại chính**:

~~~java
package org.example.directory.persistence;

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
    @Attribute(name = "telephoneNumber")
    private String phoneNumber;

    public PersonEntry() {}
    public Name getDn() { return dn; }
    public void setDn(Name dn) { this.dn = dn; }
    public String getUid() { return uid; }
    public void setUid(String uid) { this.uid = uid; }
    public String getCommonName() { return commonName; }
    public void setCommonName(String commonName) {
        this.commonName = commonName;
    }
    public String getSurname() { return surname; }
    public void setSurname(String surname) { this.surname = surname; }
    public String getEmail() { return email; }
    public void setEmail(String email) { this.email = email; }
    public String getPhoneNumber() { return phoneNumber; }
    public void setPhoneNumber(String phoneNumber) {
        this.phoneNumber = phoneNumber;
    }
}
~~~

Các annotation:

- **@Entry** mô tả objectClass và base của entry cho ODM.
- **@Id Name dn** lưu DN, danh tính entry trong directory.
- **@Attribute(name = ...)** ánh xạ property Java sang tên thuộc tính LDAP.

**PersonEntry không phải API DTO.** Nó có thể được thay đổi khi directory schema thay đổi, và có thể chứa thông tin mà HTTP caller không được xem.

Ví dụ này giả định application policy bảo đảm tối đa một giá trị mail và telephoneNumber. Nếu directory thực tế cho phép nhiều giá trị, không ánh xạ attribute ấy vào một String rồi hy vọng luôn nhận được giá trị đúng; hãy dùng collection hoặc LdapTemplate projection như phần 11.

### 4.1. Repository chỉ thao tác với persistence model

~~~java
package org.example.directory.persistence;

import java.util.List;
import org.springframework.data.ldap.repository.LdapRepository;

public interface PersonRepository extends LdapRepository<PersonEntry> {
    List<PersonEntry> findByUid(String uid);
}
~~~

findByUid tìm theo thuộc tính LDAP uid được ánh xạ, không suy DN bằng cách nối chuỗi. Dùng List để xử lý rõ trường hợp không tìm thấy hoặc tìm thấy nhiều entry nếu directory không bảo đảm uniqueness trong phạm vi.

Nếu ứng dụng dùng nhiều repository module (JPA, MongoDB, LDAP), hãy giữ package và metadata phù hợp để Spring Data xác định đúng repository. Không dùng kiểu ID của JPA như Long cho LdapRepository<PersonEntry>.

## 5. Domain model: biểu diễn nghiệp vụ độc lập directory

Domain model không cần biết @Entry, @Id, @Attribute, DirContextOperations hay tên OU:

~~~java
package org.example.directory.domain;

public record DirectoryUser(
        String username,
        String displayName,
        String email,
        String phoneNumber) {
}
~~~

Đây là một mô hình nghiệp vụ nhỏ cho use case hồ sơ người dùng. Nếu ứng dụng có nhiều loại identity, tenant, account status hoặc quyền, có thể bổ sung những giá trị nghiệp vụ tương ứng — nhưng chỉ khi chúng có semantics rõ ràng.

Không thêm dn vào domain chỉ vì ODM có @Id. Nếu một thao tác nội bộ thật sự cần DN để gọi LDAP, có thể giữ DN trong một persistence adapter/result riêng hoặc dùng entity trong service boundary; không cần biến DN thành ID public của domain/API.

## 6. Mapping từ LDAP entity sang domain model

Tạo mapper tường minh:

~~~java
package org.example.directory.mapping;

import org.example.directory.domain.DirectoryUser;
import org.example.directory.persistence.PersonEntry;
import org.springframework.stereotype.Component;

@Component
public class DirectoryUserMapper {
    public DirectoryUser toDomain(PersonEntry entry) {
        return new DirectoryUser(
                entry.getUid(),
                entry.getCommonName(),
                entry.getEmail(),
                entry.getPhoneNumber());
    }
}
~~~

Mapper này chỉ chuyển dữ liệu. Nó không nên:

- Tự tìm thêm entry LDAP khác trong một vòng lặp.
- Kiểm tra quyền truy cập của caller.
- Gọi HTTP service khác.
- Tự quyết định account bị khóa hay không nếu chưa có quy tắc nghiệp vụ.
- Đưa DN hoặc mọi LDAP attribute vào domain object một cách mặc định.

### 6.1. Thuộc tính thiếu và giá trị mặc định

LDAP entry có thể không có mail hoặc telephoneNumber. Khi đó ODM field có thể là null. Mapper cần quyết định theo hợp đồng:

| Trường hợp | Cách biểu diễn gợi ý |
| --- | --- |
| Email tùy chọn và không có | null hoặc Optional ở lớp domain theo convention |
| Phone tùy chọn và không có | null |
| Attribute bắt buộc theo schema nhưng bị thiếu | Lỗi dữ liệu/schema; không âm thầm tạo chuỗi rỗng |
| Attribute có nhiều giá trị | Collection/List, không chọn tùy ý một giá trị |
| Attribute operational không được đọc | Phân biệt với giá trị rỗng nếu nghiệp vụ cần nó |

**Không thay mọi null bằng chuỗi rỗng trong mapper** chỉ để JSON đẹp hơn. Chuỗi rỗng và giá trị không tồn tại có thể mang ngữ nghĩa khác nhau. API contract có thể chọn omit field, null hoặc mảng rỗng, nhưng phải nhất quán và được mô tả.

## 7. Mapping từ domain model sang response DTO

DTO là hợp đồng HTTP:

~~~java
package org.example.directory.api.dto;

public record UserResponse(
        String username,
        String displayName,
        String email,
        String phoneNumber) {
}
~~~

Mapper API:

~~~java
package org.example.directory.api.mapping;

import org.example.directory.api.dto.UserResponse;
import org.example.directory.domain.DirectoryUser;
import org.springframework.stereotype.Component;

@Component
public class UserApiMapper {
    public UserResponse toResponse(DirectoryUser user) {
        return new UserResponse(
                user.username(),
                user.displayName(),
                user.email(),
                user.phoneNumber());
    }
}
~~~

Tách mapper giúp đổi API mà không phải đổi LDAP schema và ngược lại. Ví dụ API v2 có thể đổi displayName thành name, hoặc thêm contact object mà không cần đổi attribute cn trên directory.

### 7.1. DTO cho các use case khác nhau

| DTO | Dùng cho | Trường được phép |
| --- | --- | --- |
| UserResponse | Đọc hồ sơ | username, displayName, email, phoneNumber |
| UpdateContactRequest | Cập nhật liên hệ | email, phoneNumber |
| UserSummaryResponse | Danh sách | username, displayName |
| AdminUserResponse | Use case quản trị có quyền riêng | Các trường quản trị được phê duyệt |

AdminUserResponse không nên chỉ là UserResponse cộng toàn bộ thuộc tính LDAP. Quyền truy cập từng trường phải được định nghĩa theo nghiệp vụ.

## 8. Service phối hợp repository và mapper

Service resolve username, kiểm tra kết quả duy nhất rồi chuyển sang domain:

~~~java
package org.example.directory.application;

import java.util.List;
import org.example.directory.domain.DirectoryUser;
import org.example.directory.mapping.DirectoryUserMapper;
import org.example.directory.persistence.PersonEntry;
import org.example.directory.persistence.PersonRepository;
import org.springframework.stereotype.Service;

@Service
public class DirectoryUserQueryService {
    private final PersonRepository repository;
    private final DirectoryUserMapper mapper;

    public DirectoryUserQueryService(
            PersonRepository repository,
            DirectoryUserMapper mapper) {
        this.repository = repository;
        this.mapper = mapper;
    }

    public DirectoryUser findByUsername(String username) {
        if (username == null
                || !username.matches("[A-Za-z0-9._-]{1,64}")) {
            throw new IllegalArgumentException(
                    "Tên đăng nhập không hợp lệ");
        }

        List<PersonEntry> matches = repository.findByUid(username);
        if (matches.isEmpty()) {
            throw new UserNotFoundException();
        }
        if (matches.size() != 1) {
            throw new AmbiguousDirectoryIdentityException();
        }
        return mapper.toDomain(matches.get(0));
    }
}
~~~

Exception nghiệp vụ:

~~~java
package org.example.directory.application;

public class UserNotFoundException extends RuntimeException {
    public UserNotFoundException() {
        super("Không tìm thấy người dùng");
    }
}
~~~

~~~java
package org.example.directory.application;

public class AmbiguousDirectoryIdentityException
        extends RuntimeException {
    public AmbiguousDirectoryIdentityException() {
        super("Định danh người dùng không duy nhất");
    }
}
~~~

**Không trả PersonEntry từ service query cho controller.** Service đã chuyển sang DirectoryUser, nên phần HTTP không biết LDAP base DN, Name hay annotation ODM.

## 9. Controller chỉ nhận và trả DTO

~~~java
package org.example.directory.api;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Pattern;
import org.example.directory.api.dto.UserResponse;
import org.example.directory.api.mapping.UserApiMapper;
import org.example.directory.application.DirectoryUserQueryService;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/users")
@Validated
public class UserController {
    private final DirectoryUserQueryService queryService;
    private final UserApiMapper apiMapper;

    public UserController(
            DirectoryUserQueryService queryService,
            UserApiMapper apiMapper) {
        this.queryService = queryService;
        this.apiMapper = apiMapper;
    }

    @GetMapping("/{username}")
    public ResponseEntity<UserResponse> getUser(
            @PathVariable
            @Pattern(regexp = "[A-Za-z0-9._-]{1,64}")
            String username) {
        var user = queryService.findByUsername(username);
        return ResponseEntity.ok(apiMapper.toResponse(user));
    }
}
~~~

Với Spring Boot 3, Bean Validation dùng namespace **jakarta.validation**. Nếu dự án ở Spring Boot/Spring Framework đời cũ, namespace và dependency có thể khác; hãy đồng bộ theo phiên bản thực tế.

Response JSON minh họa:

~~~json
{
  "username": "an",
  "displayName": "An Tran",
  "email": "an@example.org",
  "phoneNumber": "+84-28-5550-0101"
}
~~~

Không có dn, objectClass, member, userPassword hay cấu hình LDAP. Client chỉ nhận những trường thuộc hợp đồng API.

### 9.1. Ánh xạ lỗi sang HTTP

Lỗi LDAP không nên được serialize nguyên exception ra HTTP. Có thể dùng exception handler:

~~~java
package org.example.directory.api;

import org.example.directory.application.UserNotFoundException;
import org.example.directory.application.AmbiguousDirectoryIdentityException;
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ApiExceptionHandler {
    @ExceptionHandler(UserNotFoundException.class)
    ProblemDetail userNotFound(UserNotFoundException ex) {
        return ProblemDetail.forStatusAndDetail(
                HttpStatus.NOT_FOUND, "Không tìm thấy người dùng");
    }

    @ExceptionHandler(AmbiguousDirectoryIdentityException.class)
    ProblemDetail ambiguousIdentity(
            AmbiguousDirectoryIdentityException ex) {
        return ProblemDetail.forStatusAndDetail(
                HttpStatus.CONFLICT,
                "Định danh không duy nhất; cần xử lý dữ liệu directory");
    }
}
~~~

Trong production cần bổ sung xử lý validation, access denied, service unavailable và lỗi ghi LDAP theo operation + bind identity + trạng thái. Không trả diagnostic message nguyên bản, bind DN, server hostname nội bộ hoặc stack trace. Với endpoint đăng nhập công khai, cân nhắc thông điệp chung để tránh account enumeration.

## 10. Mapping theo chiều ghi: request DTO không phải LDAP entity

Client chỉ được cập nhật email và phone:

~~~java
package org.example.directory.api.dto;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record UpdateContactRequest(
        @NotBlank @Email @Size(max = 254) String email,
        @NotBlank @Size(max = 64) String phoneNumber) {
}
~~~

API:

~~~java
@PutMapping("/{username}/contact")
public ResponseEntity<Void> updateContact(
        @PathVariable String username,
        @Valid @RequestBody UpdateContactRequest request) {
    contactService.updateContact(
            username, request.email(), request.phoneNumber());
    return ResponseEntity.noContent().build();
}
~~~

**Request không có DN, objectClass hoặc member**. Caller không thể gửi các trường ấy để yêu cầu service đổi vị trí entry hoặc tự cấp membership.

### 10.1. Service ghi các attribute được phép

~~~java
package org.example.directory.application;

import java.util.List;
import javax.naming.Name;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;

import org.example.directory.persistence.PersonEntry;
import org.example.directory.persistence.PersonRepository;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.stereotype.Service;

@Service
public class DirectoryContactCommandService {
    private final PersonRepository repository;
    private final LdapTemplate ldapTemplate;

    public DirectoryContactCommandService(
            PersonRepository repository,
            LdapTemplate ldapTemplate) {
        this.repository = repository;
        this.ldapTemplate = ldapTemplate;
    }

    public void updateContact(
            String username, String email, String phoneNumber) {
        List<PersonEntry> matches = repository.findByUid(username);
        if (matches.isEmpty()) {
            throw new UserNotFoundException();
        }
        if (matches.size() != 1) {
            throw new AmbiguousDirectoryIdentityException();
        }

        Name dn = matches.get(0).getDn();
        ModificationItem[] changes = {
            new ModificationItem(
                DirContext.REPLACE_ATTRIBUTE,
                new BasicAttribute("mail", email)),
            new ModificationItem(
                DirContext.REPLACE_ATTRIBUTE,
                new BasicAttribute("telephoneNumber", phoneNumber))
        };

        ldapTemplate.modifyAttributes(dn, changes);
    }
}
~~~

Đây là lệnh ghi **whitelist**: chỉ sửa mail và telephoneNumber. Không bind lại toàn bộ PersonEntry từ request; cách đó có thể làm mất những thuộc tính mà client không biết hoặc không được phép sửa.

**Lưu ý:** ví dụ coi email và phone là một giá trị chính duy nhất theo application policy. Nếu directory cho phép nhiều mail hoặc telephoneNumber, hãy xác định endpoint thay thế toàn bộ danh sách hay thêm/xóa từng giá trị, rồi dùng ADD_ATTRIBUTE, REMOVE_ATTRIBUTE hoặc REPLACE_ATTRIBUTE đúng ngữ nghĩa. Không dùng REPLACE một cách vô tình để xóa các giá trị khác.

### 10.2. PUT và PATCH phải có semantics rõ ràng

| Hành vi | PUT contact trong ví dụ | PATCH contact |
| --- | --- | --- |
| Field được gửi | Toàn bộ field bắt buộc trong contact resource | Chỉ field cần thay đổi |
| Field bị bỏ qua | Không hợp lệ theo request contract | Giữ nguyên giá trị cũ |
| Field null | Bị validation từ chối | Cần quy định null có nghĩa xóa hay bỏ qua |
| Field chuỗi rỗng | Bị NotBlank từ chối | Có thể từ chối hoặc có semantics riêng |
| LDAP operation | REPLACE các field được phép | Chỉ sửa field được yêu cầu |

Không dùng một DTO nullable rồi không phân biệt field bị bỏ qua với field được gửi null nếu API cần PATCH. Dùng JSON Merge Patch/JSON Patch hoặc một request model biểu diễn rõ trạng thái field (absent/present/null) và viết test cho từng trường hợp.

## 11. Thuộc tính nhiều giá trị: mapping phải giữ cardinality

LDAP attribute có thể có một hoặc nhiều value. Ví dụ:

~~~ldif
dn: uid=an,ou=people,dc=example,dc=org
mail: an@example.org
mail: an.tran@example.net
telephoneNumber: +84-28-5550-0101
telephoneNumber: +84-90-555-0101
~~~

Nếu API muốn trả đầy đủ:

~~~java
package org.example.directory.api.dto;

import java.util.List;

public record UserContactResponse(
        String username,
        List<String> emails,
        List<String> phoneNumbers) {
}
~~~

Dùng **LdapTemplate.search** với mapper lấy toàn bộ values:

~~~java
import java.util.Arrays;
import java.util.List;
import org.springframework.ldap.core.DirContextOperations;

public UserContactResponse mapContact(DirContextOperations entry) {
    String[] emails = entry.getStringAttributes("mail");
    String[] phones = entry.getStringAttributes("telephoneNumber");

    return new UserContactResponse(
            entry.getStringAttribute("uid"),
            emails == null ? List.of()
                    : List.copyOf(Arrays.asList(emails)),
            phones == null ? List.of()
                    : List.copyOf(Arrays.asList(phones)));
}
~~~

**Không dùng getStringAttribute("mail") nếu contract cần tất cả email**: phương thức đơn giá trị chỉ đọc một giá trị. Dùng **getStringAttributes** để lấy mảng rồi chuyển sang List.

Nếu thứ tự giá trị không được schema/server bảo đảm, API không nên tuyên bố thứ tự có ý nghĩa. Nếu cần email chính, phải có quy tắc xác định primary value (ví dụ thuộc tính/marker riêng hoặc policy ứng dụng), không mặc định phần tử đầu tiên là primary.

### 11.1. Search và mapping trực tiếp bằng ContextMapper

Khi repository ODM chỉ ánh xạ các field cơ bản, LdapTemplate có thể tạo projection theo use case:

~~~java
import java.util.List;
import org.springframework.ldap.core.ContextMapper;
import org.springframework.ldap.core.DirContextOperations;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.SearchScope;

import static org.springframework.ldap.query.LdapQueryBuilder.query;

public List<UserContactResponse> findContacts(
        LdapTemplate ldapTemplate, String uid) {
    return ldapTemplate.search(
            query()
                .base("ou=people")
                .searchScope(SearchScope.SUBTREE)
                .attributes("uid", "mail", "telephoneNumber")
                .countLimit(100)
                .timeLimit(2000)
                .where("objectClass").is("inetOrgPerson")
                .and("uid").is(uid),
            (ContextMapper<UserContactResponse>) raw ->
                mapContact((DirContextOperations) raw));
}
~~~

**attributes(...)** giới hạn dữ liệu đọc về. Nó giảm lượng dữ liệu và giúp code chỉ phụ thuộc các thuộc tính cần thiết. Nhưng giới hạn projection không thay thế ACL; tài khoản bind vẫn cần được cấp quyền đọc đúng dữ liệu.

## 12. Không phải LDAP attribute nào cũng nên map ra domain/API

| Loại dữ liệu | Ví dụ | Xử lý |
| --- | --- | --- |
| Thuộc tính nghiệp vụ | uid, cn, sn, mail | Chọn và map theo use case |
| Thuộc tính nhiều giá trị | member, mail, telephoneNumber | Giữ đúng cardinality và semantics |
| DN | @Id Name | Giữ trong persistence adapter; chỉ expose nếu contract thực sự cần |
| Object classes | objectClass | Dùng cho mapping/schema, không tự trả ra API |
| Operational attributes | createTimestamp, modifyTimestamp, entryUUID | Chỉ dùng nếu nghiệp vụ cần và có policy |
| Bí mật | userPassword, unicodePwd, credentials | Không trả DTO, không log |
| Binary | jpegPhoto, certificate | Map thành resource/metadata phù hợp, không serialize bừa |
| Attribute không được đọc do ACL | Giá trị bị ẩn | Phân biệt không có, không được phép đọc và không được trả về |
| Custom vendor attributes | Thuộc tính riêng của AD/LDAP server | Đặt adapter/mapping riêng, không để lộ vào API chung |

Một API response **không nên là bản dump của LDAP entry**. Chỉ chọn những thuộc tính cần cho use case, đồng thời cân nhắc ACL và quyền của người gọi. Service account có thể đọc nhiều hơn một user cuối được phép xem.

### 12.1. Giá trị thiếu và quyền đọc

Khi mapper nhận null hoặc không nhận được một attribute, có thể có nhiều nguyên nhân:

- Entry thực sự không có thuộc tính.
- Attribute có nhưng service account không được phép đọc.
- Search projection không yêu cầu thuộc tính đó.
- Server trả dữ liệu không đầy đủ do referral, size/time limit hoặc lỗi.

Không phải mọi API của LDAP provider đều cho phép phân biệt tất cả các trường hợp này một cách portable. Nếu nghiệp vụ cần biết lý do, phải thiết kế quyền đọc/kiểm tra riêng và test trên server đích; không tự biến “không thấy attribute” thành “user không có dữ liệu”.

## 13. Ánh xạ group membership sang API

Một group LDAP có thể lưu:

~~~ldif
dn: cn=backend,ou=groups,dc=example,dc=org
objectClass: top
objectClass: groupOfNames
cn: backend
member: uid=an,ou=people,dc=example,dc=org
member: uid=binh,ou=people,dc=example,dc=org
~~~

Không nên trả trực tiếp:

~~~json
{
  "member": [
    "uid=an,ou=people,dc=example,dc=org",
    "uid=binh,ou=people,dc=example,dc=org"
  ]
}
~~~

API có thể trả:

~~~json
{
  "groupName": "backend",
  "members": [
    {"username": "an", "displayName": "An Tran"},
    {"username": "binh", "displayName": "Binh Le"}
  ]
}
~~~

Để làm điều đó, application service phải resolve các DN sang mô hình người dùng theo chính sách. Với group lớn, tránh **N+1 LDAP searches**: dùng batch lookup hoặc search có giới hạn, paging, cache có TTL và kiểm tra ACL. Cũng phải xử lý member DN stale, referral và member ở naming context khác.

**Không biến memberOf thành nguồn quyền duy nhất** khi directory có nested groups, primary group hoặc vendor-specific semantics. API nên biểu diễn đúng loại quan hệ mà nghiệp vụ cần.

## 14. Mapping và bảo mật

Tách DTO không tự động làm ứng dụng an toàn. Cần:

- **Allowlist field ghi:** chỉ sửa attribute được phép trong use case.
- **Authorization theo user/resource:** service kiểm tra caller có quyền đọc email/phone hoặc sửa contact của user đích.
- **Không tin DN từ client:** resolve DN qua server-side lookup và search base được kiểm soát.
- **Filter safety:** dùng LdapQueryBuilder/Filter API; không nối raw input thành LDAP filter.
- **DN safety:** dùng LdapNameBuilder/Rdn; DN escaping và filter escaping là hai cú pháp khác nhau.
- **TLS:** LDAPS hoặc StartTLS với CA/hostname verification; không tắt trust validation.
- **Secrets:** không log bind password, user password, token hoặc toàn bộ exception LDAP.
- **Error mapping:** không trả diagnostic message/stack trace/server topology cho HTTP client.
- **PII:** giới hạn field, mask log và áp dụng retention cho dữ liệu hồ sơ.
- **Mass assignment:** không deserialize request vào PersonEntry rồi gọi save; client chỉ được gửi field của request DTO.

Ví dụ nguy hiểm:

~~~java
// Không làm: caller có thể gửi thêm dn/objectClass/member
// nếu entity được dùng trực tiếp làm request body.
@PutMapping("/{uid}")
public void update(@RequestBody PersonEntry entry) {
    repository.save(entry);
}
~~~

Hãy nhận **UpdateContactRequest** rồi thực hiện một command whitelist như phần 10.

## 15. Kiểm thử các ranh giới mapping

Nên kiểm thử riêng:

1. **Mapper unit test:** field LDAP chuyển sang domain và DTO đúng; null, empty, multivalue được xử lý theo contract.
2. **Application service test:** 0/1/nhiều kết quả; authorization; không gọi LDAP modify khi validation thất bại.
3. **Controller test:** JSON chỉ có field công khai; không lộ DN/objectClass/attributes ngoài DTO; status code đúng.
4. **LDAP integration test:** ODM mapping đúng schema, search đúng attribute, modify đúng DN và không làm mất thuộc tính ngoài whitelist.

### 15.1. Unit test cho mapper

~~~java
package org.example.directory.mapping;

import org.example.directory.persistence.PersonEntry;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;

class DirectoryUserMapperTest {
    private final DirectoryUserMapper mapper =
            new DirectoryUserMapper();

    @Test
    void mapsDirectoryFieldsToDomain() {
        PersonEntry entry = new PersonEntry();
        entry.setUid("an");
        entry.setCommonName("An Tran");
        entry.setSurname("Tran");
        entry.setEmail("an@example.org");
        entry.setPhoneNumber("+84-28-5550-0101");

        var user = mapper.toDomain(entry);

        assertEquals("an", user.username());
        assertEquals("An Tran", user.displayName());
        assertEquals("an@example.org", user.email());
        assertEquals("+84-28-5550-0101", user.phoneNumber());
    }

    @Test
    void preservesMissingOptionalContactValues() {
        PersonEntry entry = new PersonEntry();
        entry.setUid("binh");
        entry.setCommonName("Binh Le");

        var user = mapper.toDomain(entry);

        assertNull(user.email());
        assertNull(user.phoneNumber());
    }
}
~~~

### 15.2. Controller test xác nhận không lộ DN

~~~java
package org.example.directory.api;

import org.example.directory.api.mapping.UserApiMapper;
import org.example.directory.application.DirectoryUserQueryService;
import org.example.directory.domain.DirectoryUser;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.context.annotation.Import;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@WebMvcTest(UserController.class)
@Import(UserApiMapper.class)
class UserControllerTest {
    @Autowired MockMvc mvc;
    @MockBean DirectoryUserQueryService queryService;

    @Test
    void responseContainsOnlyPublicContractFields() throws Exception {
        when(queryService.findByUsername("an"))
                .thenReturn(new DirectoryUser(
                        "an", "An Tran", "an@example.org", null));

        mvc.perform(get("/api/users/an"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.username").value("an"))
                .andExpect(jsonPath("$.displayName").value("An Tran"))
                .andExpect(jsonPath("$.email").value("an@example.org"))
                .andExpect(jsonPath("$.dn").doesNotExist())
                .andExpect(jsonPath("$.objectClass").doesNotExist())
                .andExpect(jsonPath("$.userPassword").doesNotExist());
    }
}
~~~

Đoạn test minh họa với Spring Boot 3; **@MockBean** có thể được thay bằng cơ chế mock bean tương ứng của phiên bản Spring Boot đang dùng. Nếu security filter được bật, cấu hình test phải cung cấp authentication/authorization phù hợp thay vì tắt kiểm soát trong production.

### 15.3. Integration test với LDAP

Dữ liệu test:

~~~ldif
dn: uid=an,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: an
cn: An Tran
sn: Tran
mail: an@example.org
telephoneNumber: +84-28-5550-0101
~~~

Kiểm thử cần chứng minh:

- Repository tìm đúng entry theo uid.
- ODM ánh xạ đúng @Id Name, cn, sn và các field được khai báo.
- API trả đúng DTO và không trả DN.
- Cập nhật contact chỉ thay mail và telephoneNumber.
- Các thuộc tính LDAP ngoài whitelist vẫn giữ nguyên.
- Khi email không tồn tại hoặc có nhiều giá trị, mapper/API xử lý theo policy đã định.
- Tài khoản service thiếu quyền ghi nhận lỗi phù hợp, không làm lộ diagnostic message.

### 15.4. Ma trận test

| Ca | Input/dữ liệu | Kết quả cần xác minh |
| --- | --- | --- |
| User tồn tại | Một entry uid=an | DTO có field công khai đúng |
| Không tìm thấy | Không có entry | 404 theo contract |
| Username trùng | Hai entry trong search base | 409/ambiguous; không chọn entry đầu |
| Attribute tùy chọn thiếu | Không có mail/phone | null/omit theo API contract |
| Attribute nhiều giá trị | Hai mail hoặc hai phone | Không mất giá trị nếu API hỗ trợ list |
| DN thay đổi | Move user sang OU khác | API không lộ old DN |
| Field không được phép | Request thêm objectClass/dn | Bị từ chối hoặc bỏ qua theo contract; không ghi LDAP |
| Email sai định dạng | Request validation fail | 400; không gửi LDAP Modify |
| PATCH bỏ qua field | Chỉ gửi email | Phone giữ nguyên |
| PATCH gửi null | Field null theo contract | Xử lý rõ xóa/không thay đổi |
| LDAP ACL từ chối | Service account thiếu quyền | Error mapping đúng, không lộ server detail |
| TLS lỗi | Certificate không hợp lệ | Kết nối bị từ chối |
| Multi-value replace | Nhiều mail tồn tại | Không xóa giá trị khác ngoài ý định |
| Group response | Member DN nhiều entry | DTO trả user summary, không trả DN |
| Operational attribute | modifyTimestamp/entryUUID | Chỉ expose khi được phê duyệt |

## 16. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| JSON xuất hiện dn | Trả thẳng ODM entity | Dùng response DTO và API mapper |
| Client gửi objectClass rồi entity được save | Mass assignment | Request DTO riêng, whitelist modification |
| Email bị mất một giá trị | ODM/API dùng field đơn cho attribute đa giá trị | Dùng collection và getStringAttributes |
| Field thiếu bị ghi thành chuỗi rỗng | Mapper thay null mặc định | Quy định rõ null/absent/empty |
| PUT làm mất attribute không gửi | Bind lại toàn entry từ request | Chỉ modifyAttributes field được phép |
| DN lộ trong URL/log | Route theo DN hoặc log object persistence | Dùng business identifier và log có chọn lọc |
| Repository finder trả nhiều user | Không có uniqueness trong phạm vi | Xử lý ambiguity và thu hẹp base/policy |
| API thay đổi khi LDAP schema đổi | DTO gắn trực tiếp persistence model | Tách domain/API contract |
| Không đọc được attribute | ACL hoặc attribute không tồn tại | Phân biệt permission và missing data |
| Controller trả LDAP exception | Không có error boundary | Map exception sang ProblemDetail an toàn |

## 17. Tổng kết và bài tập tự luyện

**Tách mô hình dữ liệu thư mục khỏi mô hình API** giúp ứng dụng không để schema LDAP quyết định hợp đồng HTTP. **PersonEntry** ánh xạ DN/objectClass/attribute; **DirectoryUser** biểu diễn dữ liệu nghiệp vụ; **UserResponse** và **UpdateContactRequest** kiểm soát dữ liệu được công bố và nhận vào.

Ở chiều đọc, repository/LdapTemplate lấy entry, mapper chuyển sang domain model rồi API mapper tạo response DTO. Ở chiều ghi, request DTO được validation và authorization, chuyển thành command rồi service chỉ sửa các LDAP attribute được phép. Cách làm này giữ DN và chi tiết directory bên trong adapter, bảo vệ thuộc tính nhiều giá trị và tránh over-posting.

**Bài tập:**

1. Tạo PersonEntry, DirectoryUser và UserResponse; giải thích tại sao ba class không nên dùng thay thế cho nhau.
2. Viết mapper từ LDAP entity sang domain và xử lý mail bị thiếu.
3. Thay mail từ single-value thành multi-value. Cập nhật domain/API DTO để không mất dữ liệu.
4. Viết controller trả UserResponse; kiểm thử JSON không chứa dn, objectClass hoặc userPassword.
5. Viết request DTO chỉ cho phép cập nhật email/phone và một service dùng modifyAttributes theo whitelist.
6. So sánh semantics PUT và PATCH khi field bị bỏ qua hoặc gửi null.
7. Khi username trùng trong directory, service nên trả kết quả gì? Vì sao không lấy phần tử đầu tiên?
8. Thiết kế response group membership dùng username/displayName thay DN, tránh N+1 search.
9. Phân biệt attribute thiếu do dữ liệu và attribute không đọc được do ACL.
10. Nêu cách thay đổi API v2 mà không phải đổi LDAP schema và cách thay đổi LDAP schema mà không làm client v1 bị phá vỡ.

### Tài liệu tham khảo

- [Spring LDAP Reference](https://docs.spring.io/spring-ldap/reference/) — ODM, LdapTemplate, ContextMapper và LDAP attributes.
- [Spring Data LDAP Reference](https://docs.spring.io/spring-data/ldap/reference/) — LdapRepository, mapping entry và query methods.
- [Spring Framework Web MVC](https://docs.spring.io/spring-framework/reference/web/webmvc.html) — controller, request/response và validation integration.
- [Spring Boot Validation](https://docs.spring.io/spring-boot/reference/io/validation.html) — Bean Validation trong ứng dụng Spring Boot.
- [RFC 4512 — LDAP Directory Information Models](https://www.rfc-editor.org/rfc/rfc4512) — entry, objectClass, attribute syntax và naming.
- [RFC 4511 — LDAP Protocol](https://www.rfc-editor.org/rfc/rfc4511) — Search, Modify và attribute values.

