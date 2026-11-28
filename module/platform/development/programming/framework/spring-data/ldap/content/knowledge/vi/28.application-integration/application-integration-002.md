# Tách DTO đầu vào khỏi thực thể LDAP

Trong một ứng dụng dùng **Spring Data LDAP**, HTTP client thường gửi JSON để tạo hoặc cập nhật hồ sơ người dùng. Dữ liệu JSON đó nằm ngoài phạm vi tin cậy của server, trong khi **LDAP entity** chứa cả thông tin nghiệp vụ lẫn các chi tiết kỹ thuật của directory như DN, `objectClass` và thuộc tính do schema kiểm soát. Vì vậy, ứng dụng nên **tách DTO đầu vào khỏi thực thể LDAP** và chuyển đổi giữa chúng bằng mã có chủ đích.

Bài học thuộc chương **Tích hợp ứng dụng** của mô-đun `SPRING_DATA_LDAP`. Nội dung kết nối mô hình entry phân cấp, DN, `objectClass`, schema, truy vấn repository/`LdapTemplate`, CRUD, filter an toàn và bảo mật kết nối với thiết kế API Java thực tế.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt **request DTO**, **LDAP entity** và **response DTO**, biết dữ liệu nào nên đi qua từng ranh giới.
- Giải thích nguy cơ khi deserialize trực tiếp JSON vào entity LDAP, đặc biệt với DN, `objectClass`, thuộc tính quyền và thông tin xác thực.
- Thiết kế DTO tạo/cập nhật người dùng chỉ cho phép thay đổi thuộc tính nghiệp vụ đã chọn.
- Ánh xạ DTO sang entry `inetOrgPerson` bằng Spring Data LDAP, xây DN bằng API chuyên dụng và lưu qua repository.
- Phân biệt kiểm tra đầu vào, ràng buộc schema, ACL của directory và escaping filter/DN.
- Xây REST API, xử lý lỗi, kiểm thử trường hợp thành công và trường hợp client cố gắng sửa dữ liệu không được phép.

## 2. Vì sao không nhận trực tiếp LDAP entity từ HTTP?

Giả sử có endpoint:

~~~http
POST /api/v1/people
Content-Type: application/json
~~~

Một cách viết dễ mắc lỗi là:

~~~java
// Ví dụ KHÔNG NÊN dùng:
@PostMapping
public DirectoryPerson create(@RequestBody DirectoryPerson person) {
    return repository.save(person);
}
~~~

Nếu entity có các trường như `dn`, `objectClasses`, `userPassword`, `employeeNumber` hoặc thuộc tính quản trị, client có thể thử gửi các trường đó. Khi các trường được bind tự động và ứng dụng lưu nguyên entity, client có nguy cơ sửa dữ liệu nằm ngoài quyền hạn nghiệp vụ. Đây là dạng rủi ro **mass assignment / over-posting**.

Ngay cả khi Spring/Jackson không bind được mọi loại thuộc tính, dùng entity trực tiếp vẫn tạo ra sự phụ thuộc không cần thiết giữa JSON bên ngoài và mô hình lưu trữ LDAP. Thêm một trường vào entity trong tương lai có thể vô tình mở rộng bề mặt API.

Với LDAP, rủi ro này càng đáng chú ý vì:

| Thành phần | Vì sao server phải kiểm soát |
| --- | --- |
| `dn` | Quy định entry được tạo/sửa ở nhánh nào; có thể chứa RDN được tạo từ đầu vào. |
| `objectClass` | Quy định cấu trúc entry và thuộc tính được phép theo schema. |
| `uid` | Có thể dùng làm RDN, định danh nghiệp vụ; thường không được tùy tiện thay đổi sau khi tạo. |
| `userPassword` | Thuộc tính liên quan xác thực; không được gắn vào API quản lý hồ sơ thông thường. |
| `memberOf`, nhóm và quyền | Thường được xác định từ entry nhóm hoặc cơ chế directory riêng; không cho client tự quyết qua JSON hồ sơ. |
| Thuộc tính nội bộ | Ví dụ mã nhân viên, trạng thái tài khoản, mã tổ chức có thể do hệ thống khác quản lý. |

**Nguyên tắc thiết kế:** client chỉ nói **muốn thay đổi thông tin nghiệp vụ nào**; service quyết định **entry nào được phép thay đổi**, cách xây DN, các thuộc tính LDAP được ghi và tài khoản directory nào thực hiện thao tác.

## 3. Ba mô hình dữ liệu và luồng chuyển đổi

~~~mermaid
flowchart LR
    A["HTTP JSON<br/>Không tin cậy"] --> B["CreatePersonRequest<br/>hoặc UpdatePersonRequest"]
    B --> C["Bean Validation<br/>+ kiểm tra nghiệp vụ"]
    C --> D["PersonDirectoryService<br/>ánh xạ có chủ đích"]
    D --> E["DirectoryPerson<br/>@Entry, @Id, @Attribute"]
    E --> F["LdapRepository / LdapTemplate"]
    F --> G["LDAP server<br/>schema + ACL"]
    G --> F
    F --> H["PersonResponse<br/>trường công khai"]
    H --> I["HTTP JSON phản hồi"]
~~~

| Lớp | Nguồn và mục đích | Có nên chứa DN/`objectClass`? |
| --- | --- | --- |
| **Create request DTO** | Dữ liệu client được phép cung cấp khi tạo hồ sơ. | Không. |
| **Update request DTO** | Các thuộc tính client được phép thay đổi trong hồ sơ đã tồn tại. | Không. |
| **LDAP entity** | Ánh xạ entry directory, phục vụ repository/`LdapTemplate` và schema. | Có thể chứa DN; `objectClass` thường được khai báo qua metadata mapping. |
| **Response DTO** | Phần dữ liệu đã được chọn để công bố ra API. | Thông thường không; chỉ thêm khi hợp đồng API thực sự yêu cầu. |

Việc tách DTO là một **ranh giới kiến trúc**, không thay thế validation hoặc phân quyền. Vẫn cần kiểm tra danh tính người gọi HTTP, quyền thao tác của service account và quy tắc schema LDAP.

## 4. Thiết kế directory và entry sẽ lưu

Giả sử LDAP directory có cây:

~~~text
dc=example,dc=org
├── ou=people
│   ├── uid=lan
│   └── uid=minh
└── ou=service
    └── cn=svc-directory-api
~~~

Entry `uid=lan,ou=people,dc=example,dc=org` có cấu trúc LDIF như sau:

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
title: Backend Developer
employeeNumber: E1042
~~~

Trong đó:

- `uid=lan` là **RDN**; toàn bộ đường dẫn là **DN**.
- `inetOrgPerson` kế thừa `organizationalPerson` và `person`; schema bắt buộc `cn`, `sn`.
- `uid`, `mail`, `title` và `employeeNumber` có thể xuất hiện theo schema phù hợp, nhưng mỗi thuộc tính có chính sách nghiệp vụ khác nhau.
- `employeeNumber` được hệ thống nhân sự cấp, **không nằm trong request DTO** của bài này.
- Việc một thuộc tính được schema cho phép (**MAY**) không có nghĩa người gọi HTTP được phép viết thuộc tính đó.

Tài khoản `cn=svc-directory-api,ou=service,dc=example,dc=org` được giả định có quyền **đọc và tạo/cập nhật những thuộc tính được phép trong `ou=people`**. Trong triển khai thật, ACL nên giới hạn tối đa phạm vi và quyền thao tác; service account không cần quyền quản trị toàn directory.

## 5. Thiết kế hợp đồng HTTP độc lập với LDAP schema

Một API quản lý hồ sơ nhân viên có thể cho phép:

- **Tạo mới:** client gửi `uid`, họ tên, họ, email và chức danh.
- **Xem hồ sơ:** client nhận những trường công khai.
- **Sửa hồ sơ:** client chỉ sửa họ tên, họ, email, chức danh; không thay `uid`/DN.
- **Quản trị nhóm/quyền hoặc đổi định danh:** sử dụng luồng riêng có phân quyền và quy tắc rõ ràng.

Ví dụ JSON tạo người dùng:

~~~json
{
  "uid": "lan",
  "fullName": "Nguyen Thi Lan",
  "familyName": "Nguyen",
  "email": "lan@example.org",
  "jobTitle": "Backend Developer"
}
~~~

Client **không** được quyết định:

~~~json
{
  "dn": "uid=lan,ou=admins,dc=example,dc=org",
  "objectClass": ["inetOrgPerson", "somePrivilegedClass"],
  "userPassword": "guess",
  "employeeNumber": "CEO-0001",
  "memberOf": ["cn=admins,ou=groups,dc=example,dc=org"]
}
~~~

Khối thứ hai minh họa **những trường không có trong hợp đồng request**, không phải lệnh hợp lệ để tạo hồ sơ. Cách xử lý tốt là từ chối trường ngoài DTO theo cấu hình JSON nghiêm ngặt và tiếp tục thực thi kiểm tra phân quyền ở service/directory.

### 5.1. DTO tạo mới

Dùng Java record và Jakarta Bean Validation (Spring Boot 3+):

`api/CreatePersonRequest.java`:

~~~java
package com.example.directory.api;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

public record CreatePersonRequest(
        @NotBlank
        @Pattern(regexp = "[a-z][a-z0-9._-]{2,31}")
        String uid,

        @NotBlank
        @Size(max = 150)
        String fullName,

        @NotBlank
        @Size(max = 100)
        String familyName,

        @Email
        @Size(max = 254)
        String email,

        @Size(max = 120)
        String jobTitle
) {}
~~~

Trong bài lab, `uid` phải bắt đầu bằng chữ thường ASCII, dài 3–32 ký tự; các ký tự còn lại có thể là chữ thường, số, dấu chấm, gạch dưới và gạch nối. Đây là **quy ước định danh của ứng dụng**, không phải quy tắc mặc định của mọi LDAP server.

`@NotBlank` và `@Size` kiểm tra dữ liệu cơ bản; `@Email` kiểm tra cú pháp ở mức thư viện, **không bảo đảm địa chỉ email tồn tại**. Cơ sở dữ liệu và schema vẫn phải được kiểm chứng ở các bước tiếp theo.

### 5.2. DTO cập nhật khác DTO tạo mới

Một người dùng đã tồn tại không nên có quyền tự đổi `uid` hoặc DN qua API sửa hồ sơ. Dùng request riêng cho `PATCH`:

`api/UpdatePersonRequest.java`:

~~~java
package com.example.directory.api;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Size;

public record UpdatePersonRequest(
        @Size(max = 150) String fullName,
        @Size(max = 100) String familyName,
        @Email @Size(max = 254) String email,
        @Size(max = 120) String jobTitle
) {}
~~~

Các trường `null` được hiểu là **không cập nhật** trong ví dụ này. Trường có giá trị phải qua kiểm tra ở service trước khi ghi. API đơn giản này **chưa hỗ trợ xóa một thuộc tính bằng JSON null**; để xóa `mail` hoặc `title`, cần định nghĩa thao tác rõ ràng khác và dùng cơ chế modify/remove LDAP phù hợp.

Không nên tái sử dụng một DTO quá rộng cho cả create, update, admin và authentication: mỗi thao tác có tập thuộc tính được phép khác nhau.

### 5.3. Response DTO

`api/PersonResponse.java`:

~~~java
package com.example.directory.api;

public record PersonResponse(
        String uid,
        String fullName,
        String familyName,
        String email,
        String jobTitle
) {}
~~~

Trả về `PersonResponse` giúp ngăn Jackson vô tình serialize DN, mật khẩu, metadata LDAP hoặc thuộc tính nội bộ nếu entity được mở rộng trong tương lai.

## 6. Ánh xạ entry LDAP bằng Spring Data LDAP ODM

Spring Data LDAP sử dụng annotation trong Spring LDAP để ánh xạ LDAP entry sang Java object.

`model/DirectoryPerson.java`:

~~~java
package com.example.directory.model;

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

    @Attribute(name = "mail")
    private String email;

    @Attribute(name = "title")
    private String jobTitle;

    @Attribute(name = "employeeNumber")
    private String employeeNumber;

    public Name getDn() { return dn; }
    public void setDn(Name dn) { this.dn = dn; }

    public String getUid() { return uid; }
    public void setUid(String uid) { this.uid = uid; }

    public String getCommonName() { return commonName; }
    public void setCommonName(String commonName) {
        this.commonName = commonName;
    }

    public String getSurname() { return surname; }
    public void setSurname(String surname) {
        this.surname = surname;
    }

    public String getEmail() { return email; }
    public void setEmail(String email) { this.email = email; }

    public String getJobTitle() { return jobTitle; }
    public void setJobTitle(String jobTitle) {
        this.jobTitle = jobTitle;
    }

    public String getEmployeeNumber() { return employeeNumber; }
    public void setEmployeeNumber(String employeeNumber) {
        this.employeeNumber = employeeNumber;
    }
}
~~~

Khác DTO đầu vào, entity này giữ `dn` và `employeeNumber` vì ứng dụng có thể cần **đọc** những dữ liệu đó từ directory; service quản lý hồ sơ không cho client sửa `employeeNumber`.

Việc tồn tại setter Java không đồng nghĩa thuộc tính được phép nhận từ API. Quy tắc an toàn nằm ở **ánh xạ thủ công theo danh sách trường cho phép**, kiểm tra nghiệp vụ và ACL. Nếu hệ thống có các thao tác ghi không được phép ảnh hưởng `employeeNumber`, cần bảo đảm chiến lược ODM update giữ nguyên thuộc tính này và kiểm thử trên server; không nên giả định mọi phương thức `save` sẽ tự hiểu ý định bảo toàn các trường khác.

Ở cấp lưu trữ:

- `@Id` gắn DN của entry, không phải khóa số tự tăng.
- `@Entry(base="ou=people")` giới hạn ánh xạ trong nhánh của directory, phối hợp với base của `ContextSource`.
- `@Attribute` xác định tên thuộc tính LDAP; ví dụ `fullName` trong API ánh xạ sang `cn`.
- Nhiều thuộc tính LDAP có thể chứa nhiều giá trị. Kiểu `String` ở ví dụ phù hợp khi quy ước dữ liệu chỉ sử dụng một giá trị; nếu cần nhiều giá trị, hãy thiết kế và kiểm thử kiểu collection tương ứng.

## 7. Repository và cấu hình kết nối

`repository/DirectoryPersonRepository.java`:

~~~java
package com.example.directory.repository;

import org.springframework.data.ldap.repository.LdapRepository;
import com.example.directory.model.DirectoryPerson;

public interface DirectoryPersonRepository
        extends LdapRepository<DirectoryPerson> {
}
~~~

`LdapRepository` cung cấp những thao tác CRUD phù hợp để đọc/ghi entry qua đối tượng đã ánh xạ. `LdapTemplate` là lựa chọn thích hợp khi cần kiểm soát Search, Modify, Rename hoặc các thao tác LDAP chi tiết hơn.

Với Spring Boot, cấu hình ví dụ:

`application.yml`:

~~~yaml
spring:
  ldap:
    urls: ldaps://ldap.example.org:636
    base: dc=example,dc=org
    username: cn=svc-directory-api,ou=service,dc=example,dc=org
    password: ${LDAP_BIND_PASSWORD}

  jackson:
    deserialization:
      fail-on-unknown-properties: true
~~~

Đặt mật khẩu service account qua biến môi trường `LDAP_BIND_PASSWORD` và cấu hình truststore của JVM để xác minh chứng chỉ/tên máy chủ. Nếu dùng `ldap://` thì phải thiết lập **StartTLS thành công trước Bind**; không gửi Simple Bind có mật khẩu qua đường truyền không mã hóa.

Thiết lập `fail-on-unknown-properties` khiến JSON chứa thuộc tính ngoài request DTO bị từ chối thay vì âm thầm bỏ qua. Đây là cơ chế làm rõ hợp đồng API, **không thay thế** bước ánh xạ an toàn hoặc phân quyền. Kiểm chứng cấu hình này trong phiên bản Spring Boot/Jackson đang dùng.

Dependency tối thiểu cho ví dụ: `spring-boot-starter-data-ldap`, `spring-boot-starter-web` và `spring-boot-starter-validation` (cùng starter test khi kiểm thử). Giữ các phiên bản Spring tương thích theo hệ quản lý dependency của dự án.

## 8. Xây DN trên server, không nhận DN từ client

Tại thời điểm tạo mới, service chỉ nhận `uid` từ DTO rồi tự xây DN:

~~~java
import javax.naming.Name;
import org.springframework.ldap.support.LdapNameBuilder;

private Name dnFor(String uid) {
    // uid đã được kiểm tra theo quy tắc nghiệp vụ.
    return LdapNameBuilder.newInstance("ou=people")
            .add("uid", uid)
            .build();
}
~~~

Với `spring.ldap.base=dc=example,dc=org`, tên `uid=lan,ou=people` được hiểu tương đối với base trên và trỏ đến entry có DN đầy đủ `uid=lan,ou=people,dc=example,dc=org`. Hãy kiểm thử cách repository/context source xử lý DN tương đối trong dự án thật, đặc biệt khi dùng nhiều base hoặc đổi phiên bản framework.

Sử dụng `LdapNameBuilder` (hoặc API DN như `LdapName` và `Rdn`) giúp xử lý escaping trong DN. **DN escaping khác LDAP filter escaping**; không nên nối chuỗi `"uid=" + uid + ",ou=people"` từ đầu vào HTTP.

### Quy tắc nghiệp vụ khi tạo DN

- Chỉ cho tạo entry dưới nhánh `ou=people` do ứng dụng kiểm soát.
- Dùng thuộc tính `uid` hợp lệ làm RDN và đồng thời gán `uid` trong entry.
- Không cho create API tự chọn `ou=admins` hoặc `dc` khác.
- Không nhận `objectClass` từ JSON; metadata entity và schema directory xác định class được ghi.
- Kiểm tra xung đột DN và chính sách duy nhất của `uid`. Directory chặn DN trùng, nhưng chưa chắc chặn cùng `uid` ở những DN khác nhau.

## 9. Service ánh xạ có chủ đích và thực hiện CRUD

Đây là ranh giới trung tâm của bài học: mọi dữ liệu được phép ghi vào LDAP được nêu rõ bằng mã. Ví dụ sau dùng repository để tạo, tìm và cập nhật các trường hồ sơ; các thao tác cấp quyền, nhóm và mật khẩu phải có dịch vụ riêng.

`service/PersonDirectoryService.java`:

~~~java
package com.example.directory.service;

import java.util.regex.Pattern;
import javax.naming.Name;

import org.springframework.ldap.support.LdapNameBuilder;
import org.springframework.stereotype.Service;

import com.example.directory.api.CreatePersonRequest;
import com.example.directory.api.UpdatePersonRequest;
import com.example.directory.api.PersonResponse;
import com.example.directory.model.DirectoryPerson;
import com.example.directory.repository.DirectoryPersonRepository;

@Service
public class PersonDirectoryService {

    private static final Pattern UID =
            Pattern.compile("[a-z][a-z0-9._-]{2,31}");

    private final DirectoryPersonRepository repository;

    public PersonDirectoryService(DirectoryPersonRepository repository) {
        this.repository = repository;
    }

    public PersonResponse create(CreatePersonRequest request) {
        Name dn = dnFor(request.uid());

        if (repository.existsById(dn)) {
            throw new PersonAlreadyExists();
        }

        DirectoryPerson entity = new DirectoryPerson();
        entity.setDn(dn);
        entity.setUid(request.uid());

        // Chỉ các trường trong hợp đồng create được ghi:
        entity.setCommonName(required(request.fullName()));
        entity.setSurname(required(request.familyName()));
        entity.setEmail(optional(request.email()));
        entity.setJobTitle(optional(request.jobTitle()));

        // Không nhận objectClass, userPassword, employeeNumber,
        // DN hoặc membership từ payload HTTP.
        DirectoryPerson saved = repository.save(entity);
        return toResponse(saved);
    }

    public PersonResponse get(String uid) {
        return toResponse(load(uid));
    }

    public PersonResponse updateProfile(
            String uid, UpdatePersonRequest request) {

        if (request.fullName() == null
                && request.familyName() == null
                && request.email() == null
                && request.jobTitle() == null) {
            throw new IllegalArgumentException("No fields to update");
        }

        DirectoryPerson entity = load(uid);

        // PATCH: trường bị bỏ qua/null không thay đổi.
        if (request.fullName() != null) {
            entity.setCommonName(required(request.fullName()));
        }
        if (request.familyName() != null) {
            entity.setSurname(required(request.familyName()));
        }
        if (request.email() != null) {
            entity.setEmail(required(request.email()));
        }
        if (request.jobTitle() != null) {
            entity.setJobTitle(required(request.jobTitle()));
        }

        // Không cập nhật uid, dn, employeeNumber và các thuộc tính
        // xác thực/quyền. LDAP schema và ACL vẫn quyết định
        // liệu thay đổi được phép hay không.
        DirectoryPerson saved = repository.save(entity);
        return toResponse(saved);
    }

    private DirectoryPerson load(String uid) {
        return repository.findById(dnFor(uid))
                .orElseThrow(PersonNotFound::new);
    }

    private Name dnFor(String uid) {
        if (uid == null || !UID.matcher(uid).matches()) {
            throw new IllegalArgumentException("Invalid uid");
        }
        return LdapNameBuilder.newInstance("ou=people")
                .add("uid", uid)
                .build();
    }

    private static String required(String value) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                    "Required profile value is blank");
        }
        return value.strip();
    }

    private static String optional(String value) {
        if (value == null || value.isBlank()) {
            return null;
        }
        return value.strip();
    }

    private static PersonResponse toResponse(DirectoryPerson person) {
        return new PersonResponse(
                person.getUid(),
                person.getCommonName(),
                person.getSurname(),
                person.getEmail(),
                person.getJobTitle()
        );
    }

    public static class PersonNotFound extends RuntimeException {
    }

    public static class PersonAlreadyExists extends RuntimeException {
    }
}
~~~

### Các điểm quan trọng trong service

1. **DN được tạo ở server:** client chỉ gửi `uid`, không chọn nhánh directory.
2. **Create chỉ gán trường đã được phép:** `employeeNumber` và thuộc tính quyền hoàn toàn không đọc từ DTO.
3. **Update tải entry đã tồn tại:** các trường không nằm trong `UpdatePersonRequest` vẫn giữ nguyên trong entity trước khi gọi lưu.
4. **Không đổi UID/RDN qua endpoint profile:** nếu cần rename, xây một use case riêng dùng Modify DN và rà soát tham chiếu nhóm.
5. **Không coi `existsById` là khóa đồng bộ:** hai request tạo đồng thời vẫn có thể cùng thấy “chưa có”; server sẽ xử lý xung đột DN. Ứng dụng cần chuyển lỗi entry đã tồn tại thành HTTP 409 phù hợp.
6. **Không bảo đảm atomicity cho quy trình nhiều bước:** một LDAP Modify riêng lẻ có ngữ nghĩa khác với chuỗi đọc-sửa-ghi. Nếu cần chống mất cập nhật khi nhiều người chỉnh cùng hồ sơ, hãy thiết kế cơ chế điều phối/điều kiện cập nhật phù hợp.

Với đoạn `updateProfile`, hãy **kiểm thử thực tế** rằng phương thức repository `save` và cấu hình ODM không ghi đè các thuộc tính không thuộc phạm vi quản lý của API, nhất là trên server có operational attributes hoặc ứng dụng khác cùng sửa. Khi chỉ được cập nhật một tập thuộc tính xác định, có thể dùng `LdapTemplate.modifyAttributes(...)` với các `ModificationItem` cho đúng thuộc tính cần sửa thay vì lưu toàn entity.

**Giới hạn PATCH trong ví dụ:** `null` được hiểu là “bỏ qua”. Để hỗ trợ “xóa email”, thiết kế request/operation riêng (ví dụ `DELETE /people/{uid}/email` hoặc PATCH có biểu diễn rõ việc xóa), xác thực quyền xóa và dùng LDAP modify remove. Không gộp lẫn “không gửi trường” và “muốn xóa trường” một cách mơ hồ.

## 10. Tạo controller chỉ nhận DTO

`web/PeopleController.java`:

~~~java
package com.example.directory.web;

import java.net.URI;

import jakarta.validation.Valid;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import com.example.directory.api.CreatePersonRequest;
import com.example.directory.api.UpdatePersonRequest;
import com.example.directory.api.PersonResponse;
import com.example.directory.service.PersonDirectoryService;

@RestController
@RequestMapping("/api/v1/people")
public class PeopleController {

    private final PersonDirectoryService service;

    public PeopleController(PersonDirectoryService service) {
        this.service = service;
    }

    @PostMapping
    public ResponseEntity<PersonResponse> create(
            @Valid @RequestBody CreatePersonRequest request) {

        PersonResponse created = service.create(request);
        URI location = URI.create("/api/v1/people/" + created.uid());
        return ResponseEntity.created(location).body(created);
    }

    @GetMapping("/{uid}")
    public PersonResponse get(@PathVariable String uid) {
        return service.get(uid);
    }

    @PatchMapping("/{uid}")
    public PersonResponse updateProfile(
            @PathVariable String uid,
            @Valid @RequestBody UpdatePersonRequest request) {

        return service.updateProfile(uid, request);
    }
}
~~~

Dùng `@Valid` kích hoạt Bean Validation trên các request DTO (khi đã thêm starter validation). Với JSON sai cú pháp, thiếu thuộc tính bắt buộc hoặc giá trị không hợp lệ, Spring MVC sẽ tạo lỗi request; hệ thống nên chuyển thành response 400 với thông báo dễ hiểu, không lộ thông tin nhạy cảm.

### Phản hồi lỗi nghiệp vụ

| Trường hợp | HTTP gợi ý | Ý nghĩa |
| --- | --- | --- |
| DTO thiếu `fullName`/`familyName` khi tạo | 400 Bad Request | Vi phạm validation. |
| `uid` sai quy tắc | 400 Bad Request | Không được dùng giá trị đó để tạo/truy xuất DN. |
| Request chứa trường ngoài DTO | 400 Bad Request | Khi đã bật chế độ từ chối unknown properties. |
| Không tìm thấy người cần sửa | 404 Not Found | Entry tương ứng không tồn tại. |
| Tạo trùng DN/`uid` theo quy ước | 409 Conflict | Yêu cầu xung đột dữ liệu hiện tại. |
| Không đủ quyền LDAP/ACL | 403 hoặc lỗi nghiệp vụ phù hợp | Chỉ trả thông tin tối thiểu; log nội bộ an toàn. |
| Directory bị lỗi/TLS lỗi/timeout | 503 Service Unavailable | Không coi lỗi hạ tầng là hồ sơ không tồn tại. |

Có thể ánh xạ `PersonNotFound` và `PersonAlreadyExists` qua `@RestControllerAdvice`. Cần ánh xạ **lỗi LDAP cụ thể** theo loại: xung đột entry, thiếu quyền, lỗi schema, lỗi timeout và lỗi kết nối không nên bị gom thành “sai dữ liệu”. Các thông báo API không được tiết lộ mật khẩu, DN tài khoản dịch vụ hay stack trace nội bộ.

## 11. Ví dụ request/response theo luồng đầy đủ

### 11.1. Tạo người dùng

~~~http
POST /api/v1/people HTTP/1.1
Content-Type: application/json

{
  "uid": "lan",
  "fullName": "Nguyen Thi Lan",
  "familyName": "Nguyen",
  "email": "lan@example.org",
  "jobTitle": "Backend Developer"
}
~~~

Nếu hợp lệ và directory chấp nhận, phản hồi:

~~~http
HTTP/1.1 201 Created
Location: /api/v1/people/lan
Content-Type: application/json

{
  "uid": "lan",
  "fullName": "Nguyen Thi Lan",
  "familyName": "Nguyen",
  "email": "lan@example.org",
  "jobTitle": "Backend Developer"
}
~~~

Entry thật nằm dưới `ou=people` theo DN do service xây, có bộ `objectClass` được entity mapping khai báo. Server kiểm tra schema, quyền tạo entry và tính duy nhất của DN.

### 11.2. Cập nhật phần hồ sơ được phép

~~~http
PATCH /api/v1/people/lan HTTP/1.1
Content-Type: application/json

{
  "jobTitle": "Senior Backend Developer",
  "email": "lan.nguyen@example.org"
}
~~~

Service tải entry hiện có và thay đổi hai trường `title`/`mail`. Các trường `uid`, `cn`, `sn`, `employeeNumber` không bị sửa **theo ý định của application mapping**.

### 11.3. Client cố thay đổi DN hoặc quyền

~~~http
PATCH /api/v1/people/lan HTTP/1.1
Content-Type: application/json

{
  "dn": "uid=lan,ou=admins,dc=example,dc=org",
  "memberOf": ["cn=admins,ou=groups,dc=example,dc=org"]
}
~~~

Các trường này không tồn tại trong `UpdatePersonRequest`. Với cấu hình từ chối unknown properties, framework trả **400** trước khi service thực thi cập nhật. Ngay cả khi cấu hình JSON chỉ bỏ qua trường lạ, service vẫn không đọc các thuộc tính đó; cần duy trì ACL LDAP để hạn chế ảnh hưởng của mã có lỗi hoặc thao tác khác ngoài controller.

## 12. DTO tách biệt với validation, ACL và xác thực

Tách DTO là bước cần thiết nhưng chưa đủ để bảo vệ directory.

### 12.1. Kiểm tra ở các tầng

~~~mermaid
flowchart TD
    A["HTTP request"] --> B{"Đã xác thực người gọi?"}
    B -->|"Không"| Z["401 Unauthorized"]
    B -->|"Có"| C{"Có quyền thao tác?"}
    C -->|"Không"| Y["403 Forbidden"]
    C -->|"Có"| D{"DTO hợp lệ?"}
    D -->|"Không"| X["400 Bad Request"]
    D -->|"Có"| E["Service áp quy tắc nghiệp vụ<br/>+ mapping trường cho phép"]
    E --> F["LDAP Bind service account qua TLS"]
    F --> G{"Schema + ACL directory chấp nhận?"}
    G -->|"Có"| H["Lưu/read entry và trả response DTO"]
    G -->|"Không"| I["Xử lý lỗi có kiểm soát"]
~~~

- **HTTP authentication** xác định ai đang gọi API (ví dụ bằng Spring Security, session hoặc token).
- **HTTP authorization** xác định người đó có quyền tạo/sửa hồ sơ cụ thể hay không.
- **Bean Validation** kiểm tra hình dạng/định dạng giá trị của request.
- **Business rules** kiểm tra định danh, vùng tổ chức, tính duy nhất và trường được phép.
- **LDAP schema và ACL** tiếp tục kiểm soát entry/thuộc tính trong directory.

Bind thành công bằng tài khoản dịch vụ LDAP **không chứng minh người gọi REST API đã đăng nhập**, cũng không cấp cho người gọi HTTP mọi quyền của tài khoản dịch vụ.

### 12.2. Bảo vệ kết nối và secret

Simple Bind qua LDAP không mã hóa có thể làm lộ mật khẩu; hãy dùng **LDAPS** hoặc **StartTLS trước Bind**, kiểm tra chứng chỉ và hostname. Không ghi mật khẩu trong mã nguồn, log hoặc payload API. Hạn chế quyền service account trong `ou=people` và chia tách tài khoản đọc/ghi nếu yêu cầu vận hành.

LDAP `userPassword` không phải trường hồ sơ công khai, không được tự thêm vào create/update DTO chỉ vì muốn “tạo tài khoản”. Xác lập hoặc đổi thông tin đăng nhập cần một luồng riêng có kiểm tra danh tính, cơ chế lưu mật khẩu theo chính sách directory và phân quyền tương ứng.

### 12.3. Truy vấn theo thuộc tính bằng filter an toàn

Nếu cần tìm người trước khi cập nhật, đừng ghép filter từ input:

~~~java
// KHÔNG an toàn:
String rawFilter = "(uid=" + requestUid + ")";
~~~

Dùng API xây filter:

~~~java
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;

LdapQuery query = LdapQueryBuilder.query()
        .base("ou=people")
        .where("objectClass").is("inetOrgPerson")
        .and("uid").is(requestUid);
~~~

`LdapQueryBuilder` giúp escape **giá trị filter**; kiểm tra input theo quy tắc nghiệp vụ vẫn cần thiết. **DN escaping** dùng quy tắc khác và phải thông qua `LdapNameBuilder` hay API tương đương. Với request search công khai, cần thêm base/scope, giới hạn số kết quả, timeout và kiểm soát quyền đọc.

## 13. Những lỗi tích hợp thường gặp

| Sai lầm | Hệ quả | Cách phòng tránh |
| --- | --- | --- |
| `@RequestBody DirectoryPerson` | Client có thể tác động đến các trường nội bộ khi entity mở rộng. | Dùng request DTO với danh sách trường cho phép. |
| Trả trực tiếp entity cho HTTP response | Có thể lộ DN, attribute nội bộ hoặc metadata LDAP. | Tạo response DTO riêng. |
| Nhận DN, `objectClass` từ request | Cho client chọn nhánh hoặc cấu trúc entry không phù hợp. | Service tự xây DN và định nghĩa object class theo metadata. |
| Một DTO cho create/update/admin | Tập quyền của các use case bị trộn lẫn. | Tạo DTO riêng theo thao tác. |
| Chỉ dựa vào `@Valid` | Không xác thực quyền người gọi hoặc phạm vi LDAP. | Kết hợp authn/authz, business rules, schema và ACL. |
| Ghép chuỗi DN/filter | DN sai hoặc LDAP injection. | Dùng `LdapNameBuilder` và `LdapQueryBuilder`. |
| Cho phép update `uid` như sửa `mail` | RDN/DN và các tham chiếu nhóm có thể không còn khớp. | Xây use case Rename/Modify DN riêng. |
| Coi JSON `null` là yêu cầu xóa thuộc tính trong mọi tình huống | Có thể xóa dữ liệu ngoài ý muốn. | Định nghĩa rõ PATCH/PUT và semantics của absence/null. |
| Đọc-sửa-save mà không xét cạnh tranh | Có thể ghi đè thay đổi của request khác. | Kiểm thử cạnh tranh; dùng update thuộc tính cụ thể/điều phối thích hợp. |
| Tin rằng repository tự bảo đảm mọi thuộc tính khác bất biến | Cấu hình ODM có thể xử lý trường null/đa giá trị khác kỳ vọng. | Kiểm thử readback với server thật; dùng LDAP Modify theo danh sách khi cần. |
| Kiểm tra trùng bằng Search rồi cho rằng an toàn tuyệt đối | Có race condition; `uid` khác DN có thể trùng. | Xử lý xung đột tại server và áp chính sách duy nhất. |

## 14. Kiểm thử luồng DTO → entity → directory

Nên dùng một directory dành riêng cho kiểm thử tích hợp, có schema `inetOrgPerson` và ACL giả lập. Khởi tạo dữ liệu bằng LDIF, dùng Spring Boot test và làm sạch fixture sau khi chạy.

### 14.1. Ma trận kiểm thử

| Trường hợp | Kết quả mong đợi |
| --- | --- |
| Tạo hồ sơ hợp lệ | HTTP 201; entry xuất hiện đúng dưới `ou=people` với `uid`, `cn`, `sn`, `mail` và `title` phù hợp. |
| Tạo thiếu `familyName` | HTTP 400 trước khi gọi repository; không sinh entry lỗi schema. |
| Tạo `uid` sai định dạng | HTTP 400; không phát sinh DN mới. |
| Tạo `uid` đã tồn tại | HTTP 409; không ghi đè entry cũ. |
| Tạo hai request cùng `uid` đồng thời | Một request có thể thành công, request kia nhận xung đột; không tạo hai entry cùng DN. |
| Gửi thêm `dn`/`objectClass` vào create DTO | HTTP 400 khi bật strict JSON; không thay đổi nhánh/object class theo client. |
| Gửi `memberOf`/`userPassword` vào update DTO | HTTP 400 với strict JSON; directory không bị sửa thuộc tính trái phép. |
| PATCH chỉ gửi `jobTitle` | Chỉ chức danh thay đổi; `uid`, DN, `employeeNumber` và các trường khác giữ nguyên. |
| PATCH gửi tên rỗng | HTTP 400; bảo toàn `cn`/`sn` bắt buộc. |
| PATCH gửi JSON rỗng | HTTP 400 vì không có trường nào để cập nhật. |
| PATCH gửi `email: null` | Theo hợp đồng ví dụ: không thay đổi email hiện có. |
| Truy xuất người dùng không tồn tại | HTTP 404; không trả thông tin nội bộ directory. |
| Tài khoản LDAP thiếu quyền sửa | Thao tác thất bại có kiểm soát, entry được bảo vệ. |
| TLS/cert lỗi | Không hạ cấp kết nối về plaintext. |
| Response JSON sau khi tạo/đọc | Chỉ có năm trường `uid`, `fullName`, `familyName`, `email`, `jobTitle`; không lộ DN/`employeeNumber`. |

### 14.2. Kiểm tra thuộc tính mà client không được sửa

Một test tích hợp quan trọng là thiết lập `employeeNumber=E1042` cho `uid=lan`, gọi PATCH thay `jobTitle`, rồi đọc lại trực tiếp từ LDAP bằng tài khoản kiểm thử:

~~~bash
ldapsearch -x \
  -H ldaps://ldap.example.org:636 \
  -D "cn=svc-directory-api,ou=service,dc=example,dc=org" -W \
  -b "uid=lan,ou=people,dc=example,dc=org" -s base \
  "(objectClass=inetOrgPerson)" \
  dn objectClass uid cn sn mail title employeeNumber
~~~

Kỳ vọng `title` nhận giá trị mới và `employeeNumber` vẫn bằng `E1042`. Nếu không, cần điều chỉnh phương thức cập nhật (ví dụ dùng LDAP Modify chỉ trên `title`) thay vì nghĩ rằng “không có trường trong DTO” tự bảo đảm mọi cách lưu sẽ bảo toàn trạng thái.

### 14.3. Kiểm tra filter/DN injection

Dù `uid` trong bài lab bị giới hạn bằng regex, nên thử các request như:

~~~text
uid=lan,ou=admins
uid=*
uid=lan)(|(uid=*))
uid=lan\2a
~~~

Tất cả đều không phù hợp regex `uid` và phải bị chặn trước khi xây DN. Nếu sau này quy tắc username thay đổi, vẫn phải sử dụng API DN và filter encoding đúng chuẩn.

### 14.4. Kiểm thử mapper tách biệt

Ngoài test tích hợp, có thể viết unit test trên service với repository giả lập để xác minh:

- Mapping `fullName → cn`, `familyName → sn`, `jobTitle → title`.
- Trường `employeeNumber` không nhận dữ liệu từ request.
- `uid` chỉ được đặt khi tạo; khi cập nhật lấy theo path và DN cũ.
- `PersonResponse` không serialize metadata LDAP.
- Mọi trường được sửa trong PATCH đều nằm trong danh sách cho phép.

Unit test phát hiện lỗi ánh xạ; kiểm thử directory thật/nhúng phát hiện lỗi schema, DN, ACL và hành vi update của Spring LDAP.

## 15. Bài tập mở rộng

**Bài 1 — Thuộc tính chỉ đọc:** thêm `employeeNumber` vào `PersonResponse` để hiển thị, nhưng không thêm vào Create/Update DTO. Viết test chứng minh client không thể chỉnh nó qua endpoint hồ sơ.

**Bài 2 — Thao tác xóa email:** thiết kế endpoint có ý nghĩa rõ ràng để xóa thuộc tính `mail`, kiểm tra quyền, gọi LDAP Modify phù hợp và trả kết quả khi thuộc tính vốn không tồn tại. Không dùng chung semantics “trường vắng mặt” và “xóa”.

**Bài 3 — Quy trình đổi username:** giải thích vì sao đổi `uid` có thể yêu cầu Modify DN, đồng thời cập nhật tham chiếu từ nhóm `groupOfNames` hoặc hệ thống bên ngoài đang lưu DN. Thiết kế một API riêng cho quản trị, giới hạn quyền.

**Bài 4 — Truy vấn repository và LdapTemplate:** bổ sung chức năng tìm người theo email bằng `LdapQueryBuilder`, giới hạn base `ou=people` và số kết quả. API tìm kiếm chỉ trả response DTO, không trả entity thô.

**Bài 5 — Thử dữ liệu cạnh tranh:** cho hai request PATCH cập nhật hai thuộc tính khác nhau cùng lúc. Quan sát hành vi repository/save và thử chiến lược LDAP Modify thuộc tính cụ thể để tránh ghi đè dữ liệu ngoài phạm vi thay đổi.

## 16. Câu hỏi tự ôn tập

1. Vì sao `@RequestBody DirectoryPerson` tạo rủi ro dù entity đang chưa có trường nhạy cảm?
2. Một thuộc tính được schema `inetOrgPerson` cho phép có đồng nghĩa client được sửa nó qua API không?
3. Vì sao Create DTO chứa `uid` còn Update DTO của hồ sơ thông thường không chứa `uid`?
4. Ai quyết định DN và `objectClass` của entry khi tạo người dùng?
5. `@Valid` giúp giải quyết phần nào, và phần nào vẫn phải do authorization/ACL xử lý?
6. Vì sao nên tách `PersonResponse` dù request DTO đã được thiết kế an toàn?
7. Điều gì khác nhau giữa JSON field không xuất hiện và JSON field có `null` khi làm PATCH?
8. Khi `save` một entity đã tải, cần kiểm thử điều gì để bảo đảm thuộc tính do hệ thống khác quản lý không bị mất?
9. Vì sao phải phân biệt escaping giá trị LDAP filter với escaping DN?
10. Làm sao xác định việc HTTP request hợp lệ vẫn có thể bị LDAP server từ chối vì schema hoặc ACL?

**Ghi nhớ:** **Request DTO là hợp đồng dữ liệu được phép nhận**, **LDAP entity là mô hình lưu trữ theo schema**, còn **Response DTO là dữ liệu được phép công bố**. Mọi chuyển đổi giữa chúng phải có chủ đích: server xác định DN, object class, trường ghi và quyền thao tác. Spring Data LDAP giúp ánh xạ/repository thuận tiện, nhưng validation, ACL, TLS và kiểm thử tích hợp vẫn là trách nhiệm của ứng dụng.

### Tài liệu tham khảo

- [Spring Data LDAP Reference](https://docs.spring.io/spring-data/ldap/reference/): repository, object mapping và truy cập entry.
- [Spring LDAP Reference](https://docs.spring.io/spring-ldap/reference/): `LdapTemplate`, ODM, DN builder và thao tác LDAP.
- [RFC 4512 — LDAP: Directory Information Models](https://www.rfc-editor.org/rfc/rfc4512): entry, DN, object class và schema.
- [RFC 4514 — LDAP: String Representation of Distinguished Names](https://www.rfc-editor.org/rfc/rfc4514): biểu diễn/escaping DN.
- [RFC 4515 — LDAP: String Representation of Search Filters](https://www.rfc-editor.org/rfc/rfc4515): cú pháp/escaping filter.
- [RFC 4513 — LDAP Authentication Methods and Security Mechanisms](https://www.rfc-editor.org/rfc/rfc4513): xác thực và bảo mật kết nối.
