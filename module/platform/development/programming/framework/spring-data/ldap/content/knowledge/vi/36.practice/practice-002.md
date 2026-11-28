# Quản lý người dùng bằng ODM và LDAP Repository

## 1. Mục tiêu và tình huống thực hành

Trong **Spring Data LDAP**, ứng dụng Java có thể quản lý các entry trong một dịch vụ thư mục LDAP qua interface repository và **Object-Directory Mapping (ODM)**. Người học không cần viết từng thao tác JNDI để đọc/ghi thuộc tính, nhưng vẫn phải hiểu **DN**, `objectClass`, schema, query, CRUD, bảo mật và giới hạn của directory.

Bài thực hành này xây một API nội bộ để tạo, tra cứu, cập nhật email và xóa người dùng bằng **Spring Boot + Spring Data LDAP + LDAP Repository**. Dữ liệu được lưu trong nhánh `ou=people` của một directory **dành riêng cho thử nghiệm**.

Khi hoàn thành, bạn có thể:

1. Chuẩn bị LDAP server có base DN và nhánh chứa người dùng.
2. Kích hoạt repository và thiết lập `ContextSource`/`LdapTemplate` qua cấu hình Spring Boot.
3. Ánh xạ entry `inetOrgPerson` vào entity Java bằng `@Entry`, `@Id`, `@DnAttribute` và `@Attribute`.
4. Viết repository method `findByUid`, `findBySurname` và dùng `save`/`delete`.
5. Xây REST API có validate đầu vào, phân biệt lỗi not found, conflict và service unavailable.
6. Kiểm thử CRUD trên directory thật, xác minh DN, thuộc tính LDAP và an toàn filter.

### Cây LDAP mục tiêu

```text
dc=example,dc=org                      <- base DN trong cấu hình Spring
└── ou=people                           <- nhánh người dùng
    ├── uid=linh
    └── uid=an

DN đầy đủ của Linh:
uid=linh,ou=people,dc=example,dc=org
```

Entry minh họa:

```ldif
dn: uid=linh,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: linh
cn: Linh Nguyen
sn: Nguyen
mail: linh@example.org
```

`uid=linh` là RDN (*Relative Distinguished Name*) của entry; `ou=people` là DN nhánh. `cn` và `sn` là các thuộc tính bắt buộc của `person`. `objectClass` phải hợp lệ với schema mà directory server đang sử dụng; không thể tùy tiện thêm một attribute Java rồi kỳ vọng server chấp nhận.

## 2. Kiến trúc và project minh họa

```text
HTTP client
    |
    v
DirectoryPersonController     -- request, validation, HTTP status
    |
    v
DirectoryPersonService        -- nghiệp vụ tạo/đọc/sửa/xóa
    |
    v
DirectoryPersonRepository     -- LdapRepository<DirectoryPerson>
    |
    v
Spring Data LDAP ODM          -- @Entry / @Id / @Attribute
    |
    v
LdapTemplate -> ContextSource -> LDAP/LDAPS directory
```

Lựa chọn cho bài lab: **Java 17**, **Maven**, **Spring Boot 3.5.0** và OpenLDAP test. Các ví dụ code đặt trong package `com.example.directory`:

```text
ldap-users-lab/
├── pom.xml
├── src/main/resources/application.yml
├── src/main/java/com/example/directory/
│   ├── DirectoryApplication.java
│   ├── config/DirectoryRepositoryConfig.java
│   ├── domain/DirectoryPerson.java
│   ├── repository/DirectoryPersonRepository.java
│   ├── service/DirectoryPersonService.java
│   └── api/
│       ├── CreatePersonRequest.java
│       ├── ChangeMailRequest.java
│       ├── PersonResponse.java
│       ├── DirectoryPersonController.java
│       └── DirectoryExceptionHandler.java
└── src/test/java/com/example/directory/
    └── DirectoryPersonIntegrationTest.java
```

Đây là **cấu trúc project để người học tự tạo**. Tài liệu này chỉ mô tả bài thực hành, không tự tạo các file Java hay tài nguyên khác trong module bài học.

## 3. Chuẩn bị LDAP test

Sử dụng một OpenLDAP dành riêng cho lab; nếu có Docker, có thể khởi động container mẫu như sau (PowerShell):

```powershell
docker run -d --name ldap-practice -p 127.0.0.1:1389:389 -e LDAP_ORGANISATION="Example Org" -e LDAP_DOMAIN="example.org" -e LDAP_ADMIN_PASSWORD="lab-only-secret" osixia/openldap:1.5.0
```

Container mẫu thiết lập base `dc=example,dc=org`, admin bind DN `cn=admin,dc=example,dc=org`. Đây là LDAP **không mã hóa trên localhost**, chỉ dùng để học. Trong sản phẩm thật, sử dụng **LDAPS hoặc StartTLS**, xác thực chứng chỉ, quản lý secret an toàn và tài khoản có quyền tối thiểu.

Tạo file `people.ldif`:

```ldif
dn: ou=people,dc=example,dc=org
objectClass: top
objectClass: organizationalUnit
ou: people
```

Sau khi server khởi động, nạp OU:

```powershell
docker cp people.ldif ldap-practice:/tmp/people.ldif
docker exec ldap-practice ldapadd -x -H ldap://127.0.0.1:389 -D "cn=admin,dc=example,dc=org" -w lab-only-secret -f /tmp/people.ldif
```

Nếu OU đã có, không nạp lại; lỗi trùng DN không đồng nghĩa directory hỏng. Kiểm tra nhánh:

```powershell
docker exec ldap-practice ldapsearch -x -H ldap://127.0.0.1:389 -D "cn=admin,dc=example,dc=org" -w lab-only-secret -b "ou=people,dc=example,dc=org" "(objectClass=*)" dn
```

Nếu không dùng Docker, cần cung cấp một LDAP server test có `dc=example,dc=org`, `ou=people`, tài khoản bind và quyền tạo/đọc/sửa/xóa entry thử nghiệm tương ứng.

## 4. Cài dependency và cấu hình Spring Boot

### 4.1. Tạo pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>ldap-users-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-data-ldap</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-validation</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-boot-starter-data-ldap` cung cấp repository và ODM Spring LDAP; không cần JPA để lưu người dùng trong directory. Để các phiên bản Spring Data và Spring LDAP tương thích, dùng dependency management của Spring Boot thay vì khai báo phiên bản cho từng thư viện.

### 4.2. Cấu hình application.yml

```yaml
server:
  port: 8080

spring:
  ldap:
    urls: ${LDAP_URL:ldap://127.0.0.1:1389}
    base: dc=example,dc=org
    username: ${LDAP_BIND_DN:cn=admin,dc=example,dc=org}
    password: ${LDAP_BIND_PASSWORD}
```

Đặt biến môi trường trước khi chạy ứng dụng trên PowerShell:

```powershell
$env:LDAP_BIND_PASSWORD = "lab-only-secret"
mvn spring-boot:run
```

Mật khẩu trên chỉ dành cho container lab. Trong ứng dụng thật, không đặt mật khẩu vào source, Git, log hoặc response HTTP. `spring.ldap.base` là DN gốc của kết nối, **khác** với Java package được quét bởi `@EnableLdapRepositories`.

### 4.3. Main class và cấu hình repository

Tạo `DirectoryApplication.java`:

```java
package com.example.directory;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DirectoryApplication {
    public static void main(String[] args) {
        SpringApplication.run(DirectoryApplication.class, args);
    }
}
```

Spring Boot có thể tự cấu hình LDAP repositories khi dependency và package phù hợp. Để thực hành rõ cơ chế quét, tạo `config/DirectoryRepositoryConfig.java`:

```java
package com.example.directory.config;

import com.example.directory.repository.DirectoryPersonRepository;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.ldap.repository.config.EnableLdapRepositories;

@Configuration
@EnableLdapRepositories(
    basePackageClasses = DirectoryPersonRepository.class
)
public class DirectoryRepositoryConfig {
}
```

`basePackageClasses` lấy package của interface được nêu làm gốc quét; Spring Data đăng ký implementation repository tại runtime. Nếu hệ thống đã có nhiều cấu hình `@EnableLdapRepositories` thì tránh phạm vi quét chồng nhau. `@EnableLdapRepositories` **không tự tạo tài khoản LDAP hoặc nhánh OU**.

## 5. Tạo entity ODM

Tạo `domain/DirectoryPerson.java`:

```java
package com.example.directory.domain;

import javax.naming.Name;
import org.springframework.ldap.odm.annotations.Attribute;
import org.springframework.ldap.odm.annotations.DnAttribute;
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

    @DnAttribute(value = "uid", index = 0)
    @Attribute(name = "uid")
    private String uid;

    @Attribute(name = "cn")
    private String commonName;

    @Attribute(name = "sn")
    private String surname;

    @Attribute(name = "mail")
    private String email;

    public DirectoryPerson() {}

    public Name getDn() { return dn; }
    public void setDn(Name dn) { this.dn = dn; }
    public String getUid() { return uid; }
    public void setUid(String uid) { this.uid = uid; }
    public String getCommonName() { return commonName; }
    public void setCommonName(String commonName) { this.commonName = commonName; }
    public String getSurname() { return surname; }
    public void setSurname(String surname) { this.surname = surname; }
    public String getEmail() { return email; }
    public void setEmail(String email) { this.email = email; }
}
```

| Annotation | Chức năng | Ghi nhớ |
| --- | --- | --- |
| `@Entry(base="ou=people", objectClasses=...)` | Khai báo vùng entry và các object class. | `ou=people` tương đối với base `dc=example,dc=org`. |
| `@Id` | Đánh dấu DN của entry. | Import `org.springframework.ldap.odm.annotations.Id`; kiểu bắt buộc là `javax.naming.Name`. |
| `@DnAttribute(value="uid", index=0)` | Dùng UID làm RDN khi tạo/tính DN. | Với một RDN và base OU, `index=0` chỉ đúng thành phần `uid`. |
| `@Attribute(name="uid")` | Ánh xạ giá trị attribute `uid`. | `@DnAttribute` vẫn có thể đi cùng attribute mapping. |
| `@Attribute(name="cn")` | Ánh xạ `commonName` tới `cn`. | `cn` là attribute bắt buộc theo `person`. |
| `@Attribute(name="sn")` | Ánh xạ `surname` tới `sn`. | `sn` cũng là attribute bắt buộc. |
| `@Attribute(name="mail")` | Ánh xạ `email` tới `mail`. | Phụ thuộc schema và chính sách máy chủ. |

Khi `uid="linh"`, ODM có thể tính DN tương đối `uid=linh,ou=people` nhờ `@DnAttribute(index=0)` và `@Entry.base`; thêm base kết nối thành `uid=linh,ou=people,dc=example,dc=org`. Việc đổi UID là thao tác **đổi RDN/rename** có tác động tới DN; bài lab chỉ cập nhật email để không vô tình đổi định danh.

## 6. Khai báo LDAP Repository

Tạo `repository/DirectoryPersonRepository.java`:

```java
package com.example.directory.repository;

import com.example.directory.domain.DirectoryPerson;
import java.util.List;
import java.util.Optional;
import org.springframework.data.ldap.repository.LdapRepository;

public interface DirectoryPersonRepository
        extends LdapRepository<DirectoryPerson> {

    Optional<DirectoryPerson> findByUid(String uid);

    List<DirectoryPerson> findBySurname(String surname);
}
```

Các điểm quan trọng:

- `LdapRepository<T>` nhận **một** tham số kiểu entity vì ID LDAP đã mặc định là `javax.naming.Name`; `LdapRepository<DirectoryPerson, Long>` là sai.
- `findByUid` dựa trên tên field `uid` trong entity.
- `findBySurname` dựa vào field Java `surname`, được map tới attribute LDAP `sn` qua `@Attribute`.
- `save`, `findById`, `delete`, `deleteById` được kế thừa; các query thường được Spring Data sinh implementation, không phải tự viết DAO.
- Với LDAP, repository không hỗ trợ đầy đủ phân trang/sắp xếp kiểu JPA. Muốn lọc dữ liệu lớn, cân nhắc `LdapTemplate`, search base và giới hạn tìm kiếm.

Derived query mã hóa giá trị tham số theo cơ chế framework; đừng ghép filter bằng chuỗi `"(uid=" + uid + ")"` từ input không tin cậy.

## 7. DTO và validate

Tách request/response khỏi entity LDAP để tránh đưa DN hay thuộc tính nội bộ vào mọi API response.

Tạo `api/CreatePersonRequest.java`:

```java
package com.example.directory.api;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

public record CreatePersonRequest(
    @NotBlank
    @Pattern(regexp = "^[a-z][a-z0-9._-]{2,31}$")
    String uid,

    @NotBlank @Size(max = 100) String commonName,
    @NotBlank @Size(max = 100) String surname,
    @NotBlank @Email @Size(max = 200) String email
) {}
```

Quy tắc UID bắt đầu bằng chữ thường, dài 3–32 ký tự, chỉ cho phép chữ thường/số/dấu chấm/gạch dưới/gạch ngang là **quy tắc bài lab**, không phải quy tắc chung của LDAP. Với dữ liệu DN phức tạp hơn, dùng `LdapNameBuilder` để escape thành phần RDN đúng cách.

Tạo `api/ChangeMailRequest.java`:

```java
package com.example.directory.api;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record ChangeMailRequest(
    @NotBlank @Email @Size(max = 200) String email
) {}
```

Tạo `api/PersonResponse.java`:

```java
package com.example.directory.api;

import com.example.directory.domain.DirectoryPerson;

public record PersonResponse(
    String uid,
    String commonName,
    String surname,
    String email
) {
    public static PersonResponse from(DirectoryPerson p) {
        return new PersonResponse(
            p.getUid(), p.getCommonName(), p.getSurname(), p.getEmail()
        );
    }
}
```

## 8. Service thực hiện CRUD

Tạo `service/DirectoryPersonService.java`:

```java
package com.example.directory.service;

import com.example.directory.api.ChangeMailRequest;
import com.example.directory.api.CreatePersonRequest;
import com.example.directory.api.PersonResponse;
import com.example.directory.domain.DirectoryPerson;
import com.example.directory.repository.DirectoryPersonRepository;
import java.util.List;
import org.springframework.ldap.NameAlreadyBoundException;
import org.springframework.stereotype.Service;

@Service
public class DirectoryPersonService {
    private final DirectoryPersonRepository repository;

    public DirectoryPersonService(DirectoryPersonRepository repository) {
        this.repository = repository;
    }

    public PersonResponse create(CreatePersonRequest request) {
        if (repository.findByUid(request.uid()).isPresent()) {
            throw new UserAlreadyExists(request.uid());
        }

        DirectoryPerson person = new DirectoryPerson();
        person.setUid(request.uid());
        person.setCommonName(request.commonName());
        person.setSurname(request.surname());
        person.setEmail(request.email());

        try {
            // DN được ODM tính từ @DnAttribute và @Entry.base.
            return PersonResponse.from(repository.save(person));
        } catch (NameAlreadyBoundException ex) {
            // Hai request song song có thể cùng vượt qua bước kiểm tra.
            throw new UserAlreadyExists(request.uid(), ex);
        }
    }

    public PersonResponse get(String uid) {
        return PersonResponse.from(requireUser(uid));
    }

    public List<PersonResponse> searchBySurname(String surname) {
        return repository.findBySurname(surname).stream()
            .map(PersonResponse::from)
            .toList();
    }

    public PersonResponse updateEmail(String uid, ChangeMailRequest request) {
        DirectoryPerson person = requireUser(uid);
        person.setEmail(request.email());
        return PersonResponse.from(repository.save(person));
    }

    public void delete(String uid) {
        repository.delete(requireUser(uid));
    }

    private DirectoryPerson requireUser(String uid) {
        return repository.findByUid(uid)
            .orElseThrow(() -> new UserNotFound(uid));
    }

    public static class UserNotFound extends RuntimeException {
        public UserNotFound(String uid) {
            super("Không tìm thấy UID: " + uid);
        }
    }

    public static class UserAlreadyExists extends RuntimeException {
        public UserAlreadyExists(String uid) {
            super("UID đã tồn tại: " + uid);
        }
        public UserAlreadyExists(String uid, Throwable cause) {
            super("UID đã tồn tại: " + uid, cause);
        }
    }
}
```

Tạo mới: validate DTO → kiểm tra sơ bộ UID → tạo entity → `repository.save`. Kiểm tra `findByUid` trước không thay thế bảo đảm duy nhất DN của LDAP server; vì hai request cùng lúc có thể vượt qua bước này, cần xử lý lỗi trùng DN từ server.

Cập nhật: lấy entity hiện hữu → thay đổi `mail` → `save`. Xóa: lấy entity → `delete`. Nếu không tìm thấy UID, trả lỗi nghiệp vụ. Riêng tìm theo surname trả danh sách rỗng khi không có kết quả; đây không phải lỗi kết nối.

## 9. Controller và xử lý HTTP status

Tạo `api/DirectoryPersonController.java`:

```java
package com.example.directory.api;

import com.example.directory.service.DirectoryPersonService;
import jakarta.validation.Valid;
import java.net.URI;
import java.util.List;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/directory/users")
public class DirectoryPersonController {
    private final DirectoryPersonService service;

    public DirectoryPersonController(DirectoryPersonService service) {
        this.service = service;
    }

    @PostMapping
    public ResponseEntity<PersonResponse> create(
            @Valid @RequestBody CreatePersonRequest request) {
        PersonResponse person = service.create(request);
        return ResponseEntity.created(
            URI.create("/api/directory/users/" + person.uid())
        ).body(person);
    }

    @GetMapping("/{uid}")
    public PersonResponse get(@PathVariable String uid) {
        return service.get(uid);
    }

    @GetMapping
    public List<PersonResponse> search(@RequestParam String surname) {
        return service.searchBySurname(surname);
    }

    @PatchMapping("/{uid}/email")
    public PersonResponse updateEmail(
            @PathVariable String uid,
            @Valid @RequestBody ChangeMailRequest request) {
        return service.updateEmail(uid, request);
    }

    @DeleteMapping("/{uid}")
    public ResponseEntity<Void> delete(@PathVariable String uid) {
        service.delete(uid);
        return ResponseEntity.noContent().build();
    }
}
```

Tạo `api/DirectoryExceptionHandler.java`:

```java
package com.example.directory.api;

import com.example.directory.service.DirectoryPersonService.UserAlreadyExists;
import com.example.directory.service.DirectoryPersonService.UserNotFound;
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.ldap.CommunicationException;
import org.springframework.ldap.ServiceUnavailableException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class DirectoryExceptionHandler {

    @ExceptionHandler(UserNotFound.class)
    public ResponseEntity<ProblemDetail> notFound(UserNotFound ex) {
        return result(HttpStatus.NOT_FOUND, ex.getMessage());
    }

    @ExceptionHandler(UserAlreadyExists.class)
    public ResponseEntity<ProblemDetail> conflict(UserAlreadyExists ex) {
        return result(HttpStatus.CONFLICT, ex.getMessage());
    }

    @ExceptionHandler({
        CommunicationException.class,
        ServiceUnavailableException.class
    })
    public ResponseEntity<ProblemDetail> unavailable(Exception ex) {
        return result(HttpStatus.SERVICE_UNAVAILABLE,
            "Dịch vụ LDAP tạm thời không sẵn sàng");
    }

    private ResponseEntity<ProblemDetail> result(
            HttpStatus status, String detail) {
        ProblemDetail body = ProblemDetail.forStatusAndDetail(status, detail);
        return ResponseEntity.status(status).body(body);
    }
}
```

Spring MVC kết hợp Bean Validation thường trả `400 Bad Request` khi `@Valid` thất bại. Các handler trên chỉ xử lý các tình huống được chỉ định; hệ thống production cần phân loại thêm lỗi quyền, schema, authentication, mapping và logging phù hợp. Đặc biệt, bind thất bại của **tài khoản dịch vụ** không mặc nhiên tương đương với HTTP `401` của người dùng cuối.

## 10. Thực hiện các lời gọi CRUD

Khởi động container, tạo `ou=people`, đặt `LDAP_BIND_PASSWORD` và chạy `mvn spring-boot:run`. Dùng PowerShell để thao tác HTTP.

### 10.1. Tạo người dùng

```powershell
$body = @{
  uid = "linh"
  commonName = "Linh Nguyen"
  surname = "Nguyen"
  email = "linh@example.org"
} | ConvertTo-Json

Invoke-RestMethod -Method Post -Uri "http://localhost:8080/api/directory/users" -ContentType "application/json" -Body $body
```

Kỳ vọng: HTTP `201` và response DTO chứa bốn field. LDAP server có entry `uid=linh,ou=people,dc=example,dc=org`.

### 10.2. Lấy một người dùng và tìm theo họ

```powershell
Invoke-RestMethod "http://localhost:8080/api/directory/users/linh"
Invoke-RestMethod "http://localhost:8080/api/directory/users?surname=Nguyen"
```

Kỳ vọng: GET theo UID trả một DTO; tìm surname trả danh sách, trong đó có Linh. `surname=KhongTonTai` trả danh sách rỗng. GET UID không tồn tại trả `404`.

### 10.3. Thay đổi email

```powershell
$newMail = @{ email = "linh.new@example.org" } | ConvertTo-Json
Invoke-RestMethod -Method Patch -Uri "http://localhost:8080/api/directory/users/linh/email" -ContentType "application/json" -Body $newMail
```

Kỳ vọng: trường `mail` đổi thành `linh.new@example.org`; UID và DN không đổi.

### 10.4. Xóa entry

```powershell
Invoke-WebRequest -Method Delete -Uri "http://localhost:8080/api/directory/users/linh"
```

Kỳ vọng: HTTP `204 No Content`. Đọc lại UID này nhận `404`. Nếu thử tạo cùng UID lần nữa sau khi xóa thành công, server có thể cho phép tạo mới.

### 10.5. Kiểm tra trực tiếp dữ liệu trong directory

```powershell
docker exec ldap-practice ldapsearch -x -H ldap://127.0.0.1:389 -D "cn=admin,dc=example,dc=org" -w lab-only-secret -b "ou=people,dc=example,dc=org" "(uid=linh)" dn uid cn sn mail objectClass
```

Chạy `ldapsearch` sau tạo, sửa và xóa để thấy dữ liệu thực tế trên server. API trả JSON thành công không đủ chứng minh entry đã được ghi đúng: cần đối chiếu DN và attributes từ directory.

## 11. Integration test với directory thử nghiệm

Tạo `src/test/java/com/example/directory/DirectoryPersonIntegrationTest.java`:

```java
package com.example.directory;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.example.directory.api.ChangeMailRequest;
import com.example.directory.api.CreatePersonRequest;
import com.example.directory.repository.DirectoryPersonRepository;
import com.example.directory.service.DirectoryPersonService;
import com.example.directory.service.DirectoryPersonService.UserNotFound;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class DirectoryPersonIntegrationTest {
    @Autowired
    private DirectoryPersonService service;

    @Autowired
    private DirectoryPersonRepository repository;

    @Test
    void createsReadsUpdatesAndDeletesEntry() {
        String uid = "lab" + UUID.randomUUID()
            .toString().replace("-", "").substring(0, 10);
        boolean created = false;

        try {
            var result = service.create(new CreatePersonRequest(
                uid, "Lan Nguyen", "Nguyen", "lan@example.org"
            ));
            created = true;
            assertThat(result.uid()).isEqualTo(uid);
            assertThat(service.get(uid).commonName()).isEqualTo("Lan Nguyen");

            var fromLdap = repository.findByUid(uid).orElseThrow();
            assertThat(fromLdap.getDn()).isNotNull();
            assertThat(fromLdap.getSurname()).isEqualTo("Nguyen");

            service.updateEmail(uid,
                new ChangeMailRequest("lan.new@example.org"));
            assertThat(service.get(uid).email())
                .isEqualTo("lan.new@example.org");

            service.delete(uid);
            created = false;
            assertThat(repository.findByUid(uid)).isEmpty();
            assertThatThrownBy(() -> service.get(uid))
                .isInstanceOf(UserNotFound.class);
        } finally {
            if (created) {
                repository.findByUid(uid).ifPresent(repository::delete);
            }
        }
    }
}
```

Chạy:

```powershell
mvn test
```

Test **cần kết nối LDAP server thử nghiệm đang chạy và OU đã được nạp**; nếu không, nó sẽ lỗi kết nối chứ không chứng minh sai về CRUD. Việc dùng UID ngẫu nhiên giúp tránh trùng dữ liệu giữa các lần chạy; `finally` cố gắng dọn entry nếu test dừng sớm. Nếu LDAP mất kết nối khi cleanup, cần kiểm tra và dọn thủ công.

### Các ca kiểm thử mở rộng

| Ca | Thao tác | Kỳ vọng |
| --- | --- | --- |
| UID trùng | POST hai lần cùng UID. | Lần sau báo `409 Conflict`, không ghi đè. |
| UID không tồn tại | GET một UID chưa tạo. | `404 Not Found`. |
| Tìm kiếm không có kết quả | `surname=KhongCo`. | Danh sách `[]`, không phải lỗi kết nối. |
| Dữ liệu đầu vào sai | UID chứa ký tự cấm hoặc email sai định dạng. | HTTP `400`, không ghi vào LDAP. |
| Thiếu thuộc tính schema bắt buộc | Tạo `inetOrgPerson` không có `sn` qua client thử nghiệm. | Server báo lỗi schema; không tạo entry. |
| ACL chỉ đọc | Dùng tài khoản LDAP chỉ được đọc. | Query thành công, ghi/xóa bị từ chối. |
| LDAP mất kết nối | Dừng container trong môi trường test. | Lỗi dịch vụ, không trả danh sách rỗng giả. |
| Ký tự đặc biệt trong filter | Input chứa `*`, `(`, `)` hoặc dấu gạch chéo ngược. | Filter xử lý input như giá trị dữ liệu, không tạo điều kiện query ngoài ý muốn. |

## 12. So sánh Repository và LdapTemplate

| Nhu cầu | API nên dùng | Lý do |
| --- | --- | --- |
| CRUD entity ODM | `LdapRepository<DirectoryPerson>` | Ít code, tích hợp tốt với service và query method. |
| Tìm user theo field | `findByUid`, `findBySurname` | Sinh truy vấn dựa trên mapping property. |
| Query linh hoạt với base/filter riêng | `LdapTemplate` + `LdapQueryBuilder` | Điều khiển điều kiện và phạm vi tìm kiếm. |
| Trả DTO từ vài thuộc tính | `LdapTemplate` + `AttributesMapper` | Không bắt buộc cần nguyên entity. |
| Thêm/bớt giá trị attribute nhiều giá trị | `LdapTemplate.modifyAttributes` | Điều khiển `ADD_ATTRIBUTE`/`REMOVE_ATTRIBUTE` rõ ràng. |
| LDAP controls và truy vấn đặc thù server | Spring LDAP/JNDI với `LdapContext` | Repository mặc định không có mọi tính năng paging kiểu SQL. |

Ví dụ tìm UID bằng `LdapTemplate` với filter builder:

```java
import static org.springframework.ldap.query.LdapQueryBuilder.query;

import java.util.List;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;

List<String> commonNames(LdapTemplate template, String input) {
    return template.search(
        query().base("ou=people").where("uid").is(input),
        (AttributesMapper<String>) attrs ->
            (String) attrs.get("cn").get()
    );
}
```

`LdapQueryBuilder` áp dụng escaping thích hợp cho tham số filter; khi tạo DN thủ công phải dùng API tạo DN (như `LdapNameBuilder`), bởi **escaping của DN khác escaping của LDAP filter**. Không ghép raw input thành filter bằng nối chuỗi.

## 13. Chẩn đoán lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Không tìm thấy bean repository. | Chưa scan package hoặc thiếu starter LDAP. | Kiểm tra `@EnableLdapRepositories`, package và dependency. |
| Không có `ldapTemplate`. | ContextSource/template không được cấu hình, tên bean không khớp. | Kiểm tra `spring.ldap.*` và auto-configuration. |
| `AuthenticationException` khi query. | Bind DN, password hoặc chính sách xác thực sai. | Xác minh quyền bind và secret. |
| `CommunicationException`, TLS failure. | URL/cổng sai, network, truststore, timeout. | Kiểm tra endpoint, chứng chỉ, kết nối. |
| `NameNotFoundException` khi tạo. | `ou=people` thiếu hoặc base DN không đúng. | Kiểm tra LDAP tree bằng `ldapsearch`. |
| `NameAlreadyBoundException`. | DN đã tồn tại. | Kiểm tra UID và xử lý conflict. |
| `SchemaViolationException`. | Thiếu `cn`/`sn`, sai `objectClass`/attribute. | Đối chiếu schema server với annotation ODM. |
| `NoPermissionException`. | Tài khoản bind không có quyền thao tác. | Kiểm tra ACL, không tự tăng quyền. |
| `findBySurname` không ra dữ liệu. | Query property/mapping sai hoặc base DN không đúng. | Kiểm tra `@Attribute(name="sn")` và dữ liệu thực tế. |
| Thay UID gây lỗi rename. | UID là thành phần RDN. | Tách nghiệp vụ đổi DN khỏi cập nhật email. |

Một ứng dụng có thể tạo bean repository thành công nhưng không kết nối được LDAP khi query đầu tiên. Vì vậy cần integration test thực sự truy cập server, không chỉ test khởi tạo Spring context.

## 14. Lưu ý bảo mật và triển khai thật

Bài lab sử dụng admin bind, không mã hóa trên localhost và API chưa có đăng nhập để dễ học; khi triển khai production cần thay đổi:

- Xác thực và phân quyền cho API CRUD; ghi nhận ai đã sửa/xóa người dùng.
- Dùng LDAPS/StartTLS có xác thực chứng chỉ, không tắt kiểm tra TLS để xử lý lỗi kết nối.
- Thay admin bind bằng tài khoản dịch vụ chỉ có quyền cần thiết trên đúng OU.
- Không log mật khẩu, DN chứa dữ liệu nhạy cảm, filter thô hoặc stack trace ra response API.
- Giới hạn số kết quả tìm kiếm; cấu hình timeout và dùng query có phạm vi hẹp.
- Kiểm soát xung đột khi nhiều tác nhân cùng sửa entry; không xem `save` nhiều lần là transaction ACID.
- Thiết kế riêng nghiệp vụ rename UID và quản lý group membership, vì những thay đổi đó có thể ảnh hưởng entry khác.
- Có kế hoạch sao lưu/khôi phục và vận hành với dữ liệu thực, nhất là trước khi bật xóa hàng loạt.

## 15. Bài tập tự luyện và tiêu chí nghiệm thu

### Bài tập mở rộng

1. Thêm `telephoneNumber` vào ODM entity và DTO; thực hiện tạo, cập nhật và kiểm chứng dữ liệu trên LDAP.
2. Thêm API tìm theo `mail`; giải thích sự khác nhau giữa query theo field Java và tên LDAP attribute.
3. Thực hiện rename UID trong môi trường test, cập nhật các liên kết cần thiết và xử lý DN đích đã tồn tại.
4. Tạo bind account chỉ đọc và chứng minh API đọc được nhưng thao tác sửa/xóa bị từ chối.
5. So sánh `repository.findByUid` với `LdapTemplate.search` khi input chứa ký tự đặc biệt.
6. Viết integration test kiểm tra trường hợp LDAP server tạm thời không sẵn sàng và xác minh API không giả vờ trả kết quả rỗng.

### Checklist hoàn thành

- [ ] LDAP server thử nghiệm sẵn sàng, `ou=people` tồn tại.
- [ ] Ứng dụng tạo được bean `LdapTemplate` và `DirectoryPersonRepository`.
- [ ] POST tạo được user có `uid`, `cn`, `sn`, `mail` hợp lệ.
- [ ] GET theo UID và tìm theo họ trả dữ liệu từ directory.
- [ ] PATCH thay email mà giữ nguyên DN.
- [ ] DELETE xóa entry, GET tiếp theo trả `404`.
- [ ] UID trùng trả `409`, request sai validation trả `400`.
- [ ] Integration test chạy PASS trên directory test và dọn dữ liệu.
- [ ] Có thể giải thích `@Id Name`, `@DnAttribute(index=0)` và `@Entry.base`.
- [ ] Biết giới hạn khi triển khai thực tế: TLS, ACL, schema, escaping, timeout, rename và đồng thời.

## 16. Tài liệu tham khảo

- [Spring Data LDAP — Configuration](https://docs.spring.io/spring-data/ldap/reference/ldap/configuration.html): repository, kiểu ID và phạm vi quét.
- [Spring Data LDAP — Usage](https://docs.spring.io/spring-data/ldap/reference/ldap/usage.html): cách sử dụng ODM entity và repository.
- [Spring LDAP — Object-Directory Mapping](https://docs.spring.io/spring-ldap/reference/odm.html): `@Entry`, `@Id`, `@Attribute` và `@DnAttribute`.
- [Spring LDAP — Reference](https://docs.spring.io/spring-ldap/reference/): `LdapTemplate`, `ContextSource`, DN và query.
- [Spring Boot — LDAP](https://docs.spring.io/spring-boot/reference/data/nosql.html): tự động cấu hình kết nối Spring LDAP.
- [RFC 4511 — LDAP Protocol](https://www.rfc-editor.org/rfc/rfc4511): LDAP Search, Add, Modify, Delete và result code.
- [RFC 4512 — LDAP Directory Information Models](https://www.rfc-editor.org/rfc/rfc4512): entry, DN, attributes và schema.
- [RFC 4515 — LDAP Filter Syntax](https://www.rfc-editor.org/rfc/rfc4515): cú pháp và escaping LDAP filter.
