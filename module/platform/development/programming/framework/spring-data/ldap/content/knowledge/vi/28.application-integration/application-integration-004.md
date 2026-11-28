# Thiết kế API đọc, tạo, cập nhật và xóa entry

> **Chương:** Tích hợp ứng dụng  
> **Module:** SPRING_DATA_LDAP — dùng Spring Data LDAP để ánh xạ entry LDAP thành đối tượng Java, truy vấn qua repository/`LdapTemplate` và thực hiện CRUD trên cây thư mục.

Một dịch vụ quản lý nhân viên thường cung cấp HTTP API cho giao diện quản trị, batch job hoặc hệ thống khác. Trong khi client làm việc với JSON và mã trạng thái HTTP, dữ liệu thực nằm ở **LDAP directory** và được xác định bởi **Distinguished Name (DN)**, `objectClass`, schema và quyền truy cập. Việc đặt `LdapRepository` hoặc `LdapTemplate` trực tiếp vào controller không đủ để tạo ra một API an toàn, ổn định.

Một thiết kế hợp lý cần phân tách: **hợp đồng HTTP → xác thực và phân quyền → kiểm tra dữ liệu → xác định DN → thao tác LDAP → xử lý lỗi → trả phản hồi**. Đồng thời, API phải hiểu sự khác biệt giữa tạo entry, sửa thuộc tính, đổi DN, xóa entry và xóa cả nhánh.

Bài này xây dựng API ví dụ cho người dùng `inetOrgPerson` dưới `ou=people` bằng Spring Boot, Spring LDAP và Spring Data LDAP. Ví dụ dùng Java 17+, HTTP REST và directory test có schema tương ứng. Khi áp dụng cho Active Directory hoặc server khác, cần xác minh schema, naming rule, ACL và cách xử lý password của server thực tế.

## 1. Mục tiêu và ranh giới của API

Giả sử directory có cấu trúc:

~~~text
dc=example,dc=org
├── ou=people
│   ├── uid=lan
│   └── uid=binh
├── ou=groups
│   └── cn=developers
└── ou=services
    └── cn=app-reader
~~~

Ứng dụng cung cấp API cho một entry người dùng nằm **trực tiếp dưới `ou=people`**, sử dụng `uid` làm RDN. Client không được truyền DN tùy ý hay tự chọn OU khác.

| Thao tác | HTTP endpoint | Ý nghĩa |
|---|---|---|
| Đọc entry | `GET /api/people/{uid}` | Trả dữ liệu được phép hiển thị của một entry |
| Tạo entry | `POST /api/people` | Tạo entry mới dưới OU đã định |
| Thay thế các trường API quản lý | `PUT /api/people/{uid}` | Gán lại `cn`, `sn` và `mail` theo hợp đồng API |
| Xóa entry | `DELETE /api/people/{uid}` | Xóa entry sau khi kiểm tra quyền và chính sách nghiệp vụ |
| Tìm kiếm danh sách | `GET /api/people?uid=...` | Tùy chọn mở rộng; dùng filter và base rõ ràng |

Bài chọn `PUT` để minh họa **thay thế toàn bộ tập trường mà endpoint này được phép quản lý**, không thay thế toàn bộ LDAP entry. `objectClass`, DN, UID, group membership và các thuộc tính khác **không bị xóa** chỉ vì JSON không chứa chúng.

Trong một hệ thống thực tế, xóa người dùng hoặc tạo danh tính để đăng nhập thường là nghiệp vụ nhạy cảm. API CRUD hồ sơ không mặc nhiên được phép đặt `userPassword` hoặc bỏ qua cơ chế provisioning, audit và phê duyệt của tổ chức.

## 2. Thiết kế theo lớp, không đặt LDAP trong controller

~~~mermaid
flowchart TD
    CLIENT["Client: JSON / HTTPS"] --> SECURITY["Spring Security<br/>authentication + authorization"]
    SECURITY --> CONTROLLER["REST Controller<br/>route, validation, HTTP"]
    CONTROLLER --> SERVICE["Directory Service<br/>chính sách nghiệp vụ + DN"]
    SERVICE --> LDAP["LdapTemplate / LdapRepository<br/>search, bind, modify, unbind"]
    LDAP --> SERVER["LDAP directory<br/>schema, ACL, DIT"]
    SERVER --> LDAP
    LDAP --> SERVICE
    SERVICE --> CONTROLLER
    CONTROLLER --> CLIENT
~~~

Phân chia trách nhiệm:

| Lớp | Việc nên làm | Việc không nên làm |
|---|---|---|
| Controller | Nhận DTO, `@Valid`, routing, trả HTTP response | Ghép DN/filter hoặc điều khiển JNDI trực tiếp |
| Service | Chọn nhánh LDAP hợp lệ, thực hiện chính sách CRUD, chuyển lỗi nghiệp vụ | Tin vào DN/OU do client tự khai báo |
| Mapper | Chuyển `Attributes`/entity sang DTO và ngược lại | Âm thầm xóa trường không có trong projection |
| Repository/`LdapTemplate` | Thao tác LDAP trong phạm vi đã cấu hình | Tự thay thế authorization của người dùng API |
| LDAP server | Kiểm tra schema, ACL, tên entry, các thao tác LDAP | Tự hiểu các quy tắc HTTP hoặc vai trò của web client |

**Spring Data LDAP repository và `LdapTemplate` có thể cùng tồn tại.** Repository phù hợp với thao tác entity thông dụng; `LdapTemplate` hữu ích khi cần kiểm soát DN, projection và các thay đổi thuộc tính bằng `ModificationItem`.

## 3. HTTP resource không phải bản sao 1:1 của LDAP entry

Ví dụ JSON mà client gửi khi tạo nhân viên:

~~~json
{
  "uid": "lan",
  "cn": "Tran Thi Lan",
  "sn": "Tran",
  "mail": "lan@example.org"
}
~~~

Không cho client tự gửi:

~~~json
{
  "dn": "uid=lan,ou=admins,dc=example,dc=org",
  "objectClass": ["top", "person", "inetOrgPerson"],
  "userPassword": "example"
}
~~~

Lý do:

- **DN phải do server ứng dụng xây dựng** từ UID đã kiểm tra và nhánh đã được phép.
- **`objectClass` do thiết kế schema của ứng dụng quyết định**, không phải trường để client tự thêm class tùy ý.
- **Credential/password không thuộc API hồ sơ thông thường**; cơ chế đổi hoặc khởi tạo password nên tách riêng, với xác thực và chính sách bảo mật phù hợp.
- **Các thuộc tính LDAP chưa được trả về** không nên bị hiểu là null cần xóa.
- **LDAP có thuộc tính đa giá trị**; JSON representation cần chọn kiểu dữ liệu và quy tắc rõ ràng.

Một DTO HTTP đơn giản, rõ giới hạn, dễ kiểm thử hơn việc đưa nguyên entity `@Entry` hoặc `Attributes` ra client.

## 4. Cấu hình kết nối và phụ thuộc

Ví dụ Maven dependencies cho Spring Boot có dependency management phù hợp:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-validation</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-ldap</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-security</artifactId>
    </dependency>
</dependencies>
~~~

Cấu hình `application.yml`:

~~~yaml
spring:
  ldap:
    urls: ${LDAP_URL}
    base: ${LDAP_BASE_DN}
    username: ${LDAP_SERVICE_DN}
    password: ${LDAP_SERVICE_PASSWORD}
~~~

Giả sử trên môi trường test:

~~~text
LDAP_URL=ldaps://ldap-test.example.org:636
LDAP_BASE_DN=dc=example,dc=org
LDAP_SERVICE_DN=cn=app-reader,ou=services,dc=example,dc=org
LDAP_SERVICE_PASSWORD=<secret-được-cấp-an-toàn>
~~~

Tên `app-reader` chỉ là minh họa; với API có quyền ghi, tài khoản dịch vụ phải được cấp các ACL cần thiết trong `ou=people`. **Không sử dụng tài khoản quản trị toàn directory** chỉ để demo thao tác CRUD.

`spring.ldap.base` là gốc của `ContextSource`. Những DN truyền vào `LdapTemplate` trong ví dụ dưới đây được biểu diễn **tương đối với gốc này**. Nếu gọi:

~~~java
LdapNameBuilder.newInstance("ou=people")
        .add("uid", "lan")
        .build();
~~~

DN hiệu lực trong directory là:

~~~text
uid=lan,ou=people,dc=example,dc=org
~~~

Không tự thêm `dc=example,dc=org` vào đoạn DN tương đối khi `ContextSource` đã cấu hình base tương ứng.

## 5. Hợp đồng DTO và quy tắc validation

Ví dụ dùng Java record và Jakarta Bean Validation (phù hợp Spring Boot 3+):

~~~java
package org.example.directory.api;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

public record CreatePersonRequest(
        @NotBlank
        @Pattern(regexp = "[A-Za-z0-9._-]{1,64}")
        String uid,

        @NotBlank
        @Size(max = 128)
        String cn,

        @NotBlank
        @Size(max = 128)
        String sn,

        @Email
        @Size(min = 3, max = 254)
        String mail) {
}
~~~

`uid` được giới hạn theo quy tắc riêng của ví dụ, không phải quy tắc bắt buộc chung của mọi LDAP server. Trong một ứng dụng quốc tế, chính sách nhận diện có thể cho phép Unicode hoặc bộ ký tự khác; khi đó cần kiểm tra và encode DN đúng chuẩn thay vì tự mở rộng regex mà chưa thử nghiệm.

Với `PUT`, UID đến từ path và **không thay đổi**. Chỉ có các thuộc tính được API cho phép cập nhật:

~~~java
package org.example.directory.api;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record ReplacePersonRequest(
        @NotBlank @Size(max = 128) String cn,
        @NotBlank @Size(max = 128) String sn,
        @Email @Size(min = 3, max = 254) String mail) {
}
~~~

DTO phản hồi:

~~~java
package org.example.directory.api;

public record PersonResponse(
        String uid,
        String cn,
        String sn,
        String mail) {
}
~~~

**Quy ước của API `PUT`:** `cn` và `sn` phải có giá trị hợp lệ; `mail` có thể `null` hoặc không xuất hiện trong JSON, được hiểu là **xóa thuộc tính mail**. Một chuỗi email rỗng bị từ chối bởi ràng buộc `@Size(min = 3)`, không mặc nhiên đồng nghĩa với xóa.

Vì `PUT` có tính chất thay thế biểu diễn, nếu client chỉ muốn đổi `cn` mà giữ `mail`, client phải gửi `mail` hiện hành hoặc sử dụng một endpoint `PATCH` được thiết kế riêng. Điều này cần ghi rõ trong API contract để tránh mất dữ liệu.

**Phân biệt validation:** `@NotBlank`, `@Size` và `@Email` kiểm tra hợp đồng HTTP; directory server vẫn kiểm tra riêng cú pháp attribute, `objectClass`, naming rule và ACL. Validation ở Java không thay thế schema checking.

## 6. Dựng DN từ RDN đã kiểm soát

Một API nhận `uid` nhưng không nhận nguyên DN tránh việc client điều hướng sang nhánh khác. Với Spring LDAP, dùng `LdapNameBuilder` để escape thành phần RDN đúng cú pháp:

~~~java
import javax.naming.Name;
import org.springframework.ldap.support.LdapNameBuilder;

public final class PersonDns {

    private PersonDns() {
    }

    public static Name byUid(String uid) {
        return LdapNameBuilder.newInstance("ou=people")
                .add("uid", uid)
                .build();
    }
}
~~~

So sánh:

~~~java
// Tránh ghép trực tiếp DN bằng dữ liệu người dùng:
String unsafeDn = "uid=" + userInput + ",ou=people";

// Nên dùng API xây dựng DN:
Name safeDn = PersonDns.byUid(validatedUid);
~~~

Với `LdapNameBuilder`, các ký tự đặc biệt trong RDN được xử lý theo cú pháp DN. **Escaping không thay thế authorization**: nếu ứng dụng cho phép chọn `ou=admins` hoặc `dc=another-company` từ request thì vẫn có nguy cơ truy cập sai phạm vi.

Trước thao tác ghi, cần quyết định các quy tắc bổ sung: UID có phân biệt hoa/thường không, cho phép đổi UID không, tính duy nhất chỉ dưới một OU hay trên nhiều nhánh, và có được xóa entry mang group membership không. Những quy tắc này là **chính sách nghiệp vụ**, không thể suy ra hoàn toàn từ DN.

## 7. Mapper đọc LDAP entry thành DTO

`LdapTemplate.lookup(...)` có thể sử dụng `AttributesMapper<T>` để nhận các thuộc tính mà LDAP server trả về. Mapper nên kiểm tra thuộc tính bắt buộc, kiểu Java và số giá trị thay vì ép `String` ngay lập tức.

~~~java
package org.example.directory.api;

import javax.naming.NamingException;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;

public final class PersonAttributesMapper {

    private PersonAttributesMapper() {
    }

    public static PersonResponse map(Attributes attrs)
            throws NamingException {
        return new PersonResponse(
                requiredText(attrs, "uid"),
                requiredText(attrs, "cn"),
                requiredText(attrs, "sn"),
                optionalText(attrs, "mail"));
    }

    private static String requiredText(
            Attributes attrs, String name) throws NamingException {
        String value = optionalText(attrs, name);
        if (value == null || value.isBlank()) {
            throw new IllegalStateException(
                    "Missing required LDAP attribute: " + name);
        }
        return value;
    }

    private static String optionalText(
            Attributes attrs, String name) throws NamingException {
        Attribute attribute = attrs.get(name);
        if (attribute == null || attribute.size() == 0) {
            return null;
        }
        if (attribute.size() != 1) {
            throw new IllegalStateException(
                    "Expected one LDAP value for attribute: " + name);
        }

        Object value = attribute.get();
        if (!(value instanceof String text)) {
            throw new IllegalStateException(
                    "Expected String LDAP attribute: " + name);
        }
        return text;
    }
}
~~~

`cn` về mặt LDAP có thể là một attribute đa giá trị; mapper trên đưa ra **quy ước API** rằng DTO chỉ chấp nhận một giá trị cho `cn` và các trường đang ánh xạ. Nếu dữ liệu thực tế có nhiều giá trị `cn` hoặc `mail`, cần thay hợp đồng bằng collection hoặc quy tắc chọn giá trị được xác định trước. Không coi việc gọi `Attribute.get()` là cách chọn “giá trị chính” trong tập đa trị.

Không nên trả toàn bộ `Attributes` trực tiếp ra JSON: nó có thể bao gồm dữ liệu nhạy cảm, kiểu JNDI không thể serialize ổn định và thuộc tính mà client không có lý do được xem.

## 8. Service CRUD với LdapTemplate

Để minh họa rõ cách xây DN và cập nhật từng attribute, ví dụ này chọn `LdapTemplate`. Một phiên bản dùng `LdapRepository` có thể thay thế một số thao tác, nhưng cần hiểu semantics cập nhật entity và thuộc tính chưa được tải.

Định nghĩa lỗi nghiệp vụ tối thiểu:

~~~java
package org.example.directory.api;

public final class PersonNotFoundException
        extends RuntimeException {
    public PersonNotFoundException(String uid) {
        super("Person not found for uid: " + uid);
    }
}

public final class PersonAlreadyExistsException
        extends RuntimeException {
    public PersonAlreadyExistsException(String uid) {
        super("Person already exists for uid: " + uid);
    }
}
~~~

*Hai class trên là hai tệp Java riêng khi đưa vào dự án; được đặt chung trong một code block để trình bày ngắn gọn.*

### 8.1. Đọc bằng lookup

~~~java
import javax.naming.Name;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;

public PersonResponse get(String uid) {
    Name dn = PersonDns.byUid(uid);
    try {
        return ldapTemplate.lookup(
                dn,
                (AttributesMapper<PersonResponse>)
                        PersonAttributesMapper::map);
    } catch (org.springframework.ldap.NameNotFoundException ex) {
        throw new PersonNotFoundException(uid);
    }
}
~~~

Nếu tìm theo UID nhưng chưa biết DN, dùng `ldapTemplate.search(...)` với base `ou=people`, scope phù hợp và bộ lọc `(uid=...)` được builder escape. Không mở search base lên toàn directory chỉ vì UID không khớp trong nhánh đã định.

Trong ví dụ này **UID chính là RDN**, nên `lookup` theo DN có thể diễn đạt ý định chính xác hơn `search`.

### 8.2. Tạo bằng bind

`LdapTemplate.bind(...)` thêm entry mới, với DN và các thuộc tính được xây từ dữ liệu hợp lệ:

~~~java
import javax.naming.Name;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.BasicAttributes;

public void create(CreatePersonRequest request) {
    Name dn = PersonDns.byUid(request.uid());

    Attributes attrs = new BasicAttributes(true);
    Attribute objectClasses = new BasicAttribute("objectClass");
    objectClasses.add("top");
    objectClasses.add("person");
    objectClasses.add("organizationalPerson");
    objectClasses.add("inetOrgPerson");

    attrs.put(objectClasses);
    attrs.put("uid", request.uid());
    attrs.put("cn", request.cn());
    attrs.put("sn", request.sn());

    if (request.mail() != null) {
        attrs.put("mail", request.mail());
    }

    try {
        ldapTemplate.bind(dn, null, attrs);
    } catch (org.springframework.ldap.NameAlreadyBoundException ex) {
        throw new PersonAlreadyExistsException(request.uid());
    }
}
~~~

Ở đây, `objectClass` được ứng dụng lựa chọn theo schema `inetOrgPerson`. Entry cần `cn` và `sn` vì kế thừa từ `person`. Parent `ou=people` **phải có sẵn** và account bind phải được cấp quyền thêm entry ở đúng nhánh.

**Tránh kiểm tra tồn tại rồi mới bind để quyết định duy nhất.** Hai request đồng thời đều có thể thấy “chưa tồn tại”, sau đó cùng thử Add. Directory server phải chịu trách nhiệm phát hiện DN trùng và một request nhận lỗi phù hợp. API chuyển lỗi trùng DN thành `409 Conflict` thay vì tạo hai entry có cùng DN.

### 8.3. Cập nhật một số thuộc tính bằng Modify

Để cập nhật `cn`, `sn` và `mail` mà **không thay `uid` hoặc `objectClass`**, dùng `ModificationItem`:

~~~java
import javax.naming.Name;
import javax.naming.directory.Attribute;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;

public void replace(String uid, ReplacePersonRequest request) {
    Name dn = PersonDns.byUid(uid);

    Attribute mail = request.mail() == null
            ? new BasicAttribute("mail")
            : new BasicAttribute("mail", request.mail());

    ModificationItem[] changes = {
        new ModificationItem(
                DirContext.REPLACE_ATTRIBUTE,
                new BasicAttribute("cn", request.cn())),
        new ModificationItem(
                DirContext.REPLACE_ATTRIBUTE,
                new BasicAttribute("sn", request.sn())),
        new ModificationItem(
                DirContext.REPLACE_ATTRIBUTE,
                mail)
    };

    try {
        ldapTemplate.modifyAttributes(dn, changes);
    } catch (org.springframework.ldap.NameNotFoundException ex) {
        throw new PersonNotFoundException(uid);
    }
}
~~~

Theo ngữ nghĩa LDAP Modify, thay một thuộc tính bằng **tập giá trị rỗng** sẽ xóa thuộc tính đó; đoạn `new BasicAttribute("mail")` thể hiện yêu cầu xóa mail trong `PUT`. Cần kiểm thử hành vi này trên phiên bản JNDI/provider và directory mà hệ thống sử dụng.

Các `ModificationItem` được gửi trong một thao tác LDAP Modify. Theo mô hình LDAP chuẩn, toàn bộ danh sách thay đổi của **một entry** được xử lý như một thao tác nguyên tử; nếu một thay đổi không hợp lệ thì thao tác thất bại thay vì commit một nửa. Điều này **không** có nghĩa API có transaction bao trùm nhiều entry hoặc các service khác.

**Không thay `uid` bằng Modify thuộc tính nếu UID đang là RDN.** Đổi tên entry hoặc di chuyển nhánh là thao tác `ModifyDN`/`rename` riêng, cần bảo đảm cập nhật tham chiếu nhóm, quyền và ứng dụng liên quan. API bài này cố ý coi UID là bất biến.

### 8.4. Xóa bằng unbind

~~~java
import javax.naming.Name;

public void delete(String uid) {
    Name dn = PersonDns.byUid(uid);
    try {
        ldapTemplate.unbind(dn);
    } catch (org.springframework.ldap.NameNotFoundException ex) {
        throw new PersonNotFoundException(uid);
    }
}
~~~

`unbind` xóa entry được chỉ định. Nếu entry còn **con** trong directory, server thông thường không cho xóa theo thao tác Delete chuẩn và trả lỗi như `notAllowedOnNonLeaf (66)`. Không tự biến endpoint `DELETE /api/people/{uid}` thành xóa đệ quy cả subtree khi chưa có hợp đồng và phân quyền cụ thể.

Xóa entry có thể ảnh hưởng group membership hoặc tham chiếu từ hệ thống khác; không giả định mọi directory tự dọn toàn bộ tham chiếu. Trong nghiệp vụ nhân sự, **vô hiệu hóa hoặc lưu trữ** có thể an toàn và phù hợp chính sách hơn xóa vật lý.

### 8.5. Đặt các phương thức trong một service

Các đoạn `get`, `create`, `replace`, `delete` trên là **phần thân phương thức** của một service nhận `LdapTemplate` trong constructor:

~~~java
package org.example.directory.api;

import org.springframework.ldap.core.LdapTemplate;
import org.springframework.stereotype.Service;

@Service
public class PersonDirectoryService {

    private final LdapTemplate ldapTemplate;

    public PersonDirectoryService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    // Đặt get(...), create(...), replace(...), delete(...)
    // như minh họa ở các tiểu mục 8.1–8.4.
}
~~~

Khi ghép ví dụ thành dự án chạy được, bổ sung import tương ứng và mỗi class public vào tệp Java cùng tên. Ví dụ minh họa luồng API và LDAP, không phải một dự án Maven hoàn chỉnh để copy vào một tệp duy nhất.

## 9. REST Controller: chuyển các kết quả thành HTTP

Dùng Spring MVC để ánh xạ request JSON và trả mã phản hồi:

~~~java
package org.example.directory.api;

import java.net.URI;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Pattern;

import org.springframework.http.ResponseEntity;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@Validated
@RequestMapping("/api/people")
public class PersonController {

    private final PersonDirectoryService service;

    public PersonController(PersonDirectoryService service) {
        this.service = service;
    }

    @GetMapping("/{uid}")
    public PersonResponse get(
            @PathVariable
            @Pattern(regexp = "[A-Za-z0-9._-]{1,64}") String uid) {
        return service.get(uid);
    }

    @PostMapping
    public ResponseEntity<Void> create(
            @Valid @RequestBody CreatePersonRequest request) {
        service.create(request);
        URI location = URI.create("/api/people/" + request.uid());
        return ResponseEntity.created(location).build();
    }

    @PutMapping("/{uid}")
    public ResponseEntity<Void> replace(
            @PathVariable
            @Pattern(regexp = "[A-Za-z0-9._-]{1,64}") String uid,
            @Valid @RequestBody ReplacePersonRequest request) {
        service.replace(uid, request);
        return ResponseEntity.noContent().build();
    }

    @DeleteMapping("/{uid}")
    public ResponseEntity<Void> delete(
            @PathVariable
            @Pattern(regexp = "[A-Za-z0-9._-]{1,64}") String uid) {
        service.delete(uid);
        return ResponseEntity.noContent().build();
    }
}
~~~

Việc tạo `Location` bằng nối chuỗi trong ví dụ **chỉ an toàn** vì UID đã được giới hạn vào các ký tự ASCII không cần escape trong đoạn path. Nếu quy tắc UID cho phép dấu cách, dấu `/` hoặc Unicode, hãy sử dụng URI builder có xử lý encoding đúng và kiểm thử đường dẫn.

`@Validated` giúp kiểm tra constraint của tham số controller trong cấu hình Spring MVC phù hợp; cơ chế cụ thể về exception khi lỗi method validation có thể khác theo phiên bản Spring. Lỗi `@Valid @RequestBody` thường được Spring MVC trả về HTTP `400` theo cấu hình chuẩn.

### Bảng HTTP status đề xuất

| Thao tác | Thành công | Lỗi thường gặp |
|---|---|---|
| `GET` | `200 OK` với `PersonResponse` | `404` nếu DN không tồn tại |
| `POST` | `201 Created` và `Location` | `400` dữ liệu sai; `409` DN đã tồn tại |
| `PUT` | `204 No Content` | `400` dữ liệu sai; `404` DN không tồn tại |
| `DELETE` | `204 No Content` | `404` DN không tồn tại; `409` nếu bị ràng buộc nghiệp vụ |
| Bất kỳ thao tác nào | Theo hợp đồng | `401` nếu chưa xác thực; `403` nếu đã xác thực nhưng không có quyền |
| Lỗi hạ tầng tạm thời | Không thành công | `503 Service Unavailable` nếu directory thực sự không sẵn sàng |

Các mã trên là **thiết kế API**, không phải phép ánh xạ tự động 1–1 cho mọi LDAP result code. Ví dụ lỗi `insufficientAccessRights (50)` từ LDAP khi ứng dụng sử dụng service account có thể là **lỗi cấu hình quyền ở backend**, không nhất thiết phản ánh quyền của người gọi HTTP và không nên máy móc trả `403` cho client.

## 10. Chuẩn hóa lỗi nghiệp vụ và LDAP

Ví dụ dùng `ProblemDetail` của Spring Framework 6:

~~~java
package org.example.directory.api;

import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class PersonApiErrors {

    @ExceptionHandler(PersonNotFoundException.class)
    public ProblemDetail notFound(PersonNotFoundException ex) {
        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                HttpStatus.NOT_FOUND, "Person entry does not exist");
        problem.setTitle("Person not found");
        return problem;
    }

    @ExceptionHandler(PersonAlreadyExistsException.class)
    public ProblemDetail conflict(PersonAlreadyExistsException ex) {
        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                HttpStatus.CONFLICT, "Person UID already exists");
        problem.setTitle("Person already exists");
        return problem;
    }
}
~~~

Khi lỗi bất ngờ xuất phát từ server LDAP, nên ghi sự kiện vận hành có mã lỗi và correlation ID, nhưng **không trả raw diagnostic message, bind DN, password hoặc toàn bộ LDAP entry** về client. Phân loại thêm các lỗi khi cần:

| LDAP/result thường gặp | Ý nghĩa có thể | Cách phản hồi |
|---|---|---|
| `noSuchObject (32)` | Base/entry không tồn tại | Với lookup DN mục tiêu: 404; với base cấu hình sai: xử lý như lỗi cấu hình |
| `entryAlreadyExists (68)` | DN trùng khi Add | 409 khi client tạo resource đã có |
| `invalidDNSyntax (34)` | DN không đúng cú pháp | 400 nếu do input; backend error nếu DN dựng sai |
| `objectClassViolation (65)` | Thiếu MUST, class/attribute không hợp lệ | 400/422 nếu dữ liệu client gây lỗi; lỗi cấu hình nếu mapping sai |
| `invalidAttributeSyntax (21)` | Giá trị không phù hợp syntax | 400/422 nếu đúng là lỗi input đã xác minh |
| `insufficientAccessRights (50)` | Bind account không đủ quyền | Điều tra ACL; không tự coi là 403 của end user |
| `notAllowedOnNonLeaf (66)` | Xóa entry còn con | 409 hoặc phản hồi theo hợp đồng, không xóa cascade ngầm |
| `unavailable (52)` hoặc lỗi kết nối | Server không phục vụ được | 503 khi xác định là gián đoạn tạm thời |
| `invalidCredentials (49)` | Bind credential backend sai/hết hạn | Không trả mật khẩu hay thông tin account; báo lỗi hạ tầng và alert |

Nếu nhận lỗi LDAP ngoài các trường hợp dự kiến, không nên `catch (Exception)` rồi trả 200 với JSON rỗng. Lỗi schema, lỗi quyền, timeout và dữ liệu thiếu là các loại vấn đề khác nhau, cần giữ thông tin chẩn đoán phù hợp ở server.

Trong Spring LDAP, exception JNDI thường được chuyển thành các exception thuộc Spring LDAP; tên class, hierarchy và cách chuyển đổi cụ thể cần kiểm tra theo phiên bản framework đang dùng.

## 11. Dùng LdapRepository khi nào?

Spring Data LDAP có thể ánh xạ LDAP entry thành Java entity:

~~~java
package org.example.directory.model;

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

    public DirectoryPerson() {
    }

    // Getter/setter phục vụ ODM.
}
~~~

Repository:

~~~java
import java.util.List;

import org.springframework.data.ldap.repository.LdapRepository;

public interface DirectoryPersonRepository
        extends LdapRepository<DirectoryPerson> {

    List<DirectoryPerson> findByUid(String uid);
}
~~~

Lựa chọn:

| Nhu cầu | Lựa chọn phù hợp |
|---|---|
| Tìm kiếm/đọc entity theo ánh xạ ODM | `LdapRepository` |
| CRUD entity hoàn chỉnh theo DN và mapping đã thống nhất | Repository khi đã kiểm chứng semantics của `save(...)` |
| Tạo entry với tập attribute xác định | `LdapTemplate.bind(...)` |
| Cập nhật có chủ đích một vài thuộc tính | `LdapTemplate.modifyAttributes(...)` |
| Đọc một phần thuộc tính thành DTO | `LdapTemplate.search(...)` với `AttributesMapper` |
| Đổi DN/RDN hoặc chuyển entry sang OU khác | `LdapTemplate.rename(...)` khi chính sách cho phép |

**Cẩn trọng với partial updates:** một entity chỉ được tải vài thuộc tính có thể chứa `null` cho phần còn lại. Đừng sửa một trường rồi `repository.save(entity)` nếu chưa kiểm chứng framework sẽ giữ nguyên các attribute chưa được tải. Với các API cập nhật từng trường, dùng `ModificationItem` hoặc thiết kế mô hình patch rõ trạng thái thay đổi thường an toàn hơn.

## 12. PUT và PATCH: xử lý null, missing và remove

Một API `PATCH` thường phải phân biệt ba trạng thái:

| JSON request | Ý nghĩa nếu dùng merge-patch contract |
|---|---|
| Không có khóa `mail` | Không thay đổi `mail` |
| `"mail": null` | Xóa thuộc tính `mail` |
| `"mail": "new@example.org"` | Thay `mail` bằng giá trị mới |

Điều này **khác** với hợp đồng `PUT` trong bài, nơi trường mail null hoặc vắng mặt đều được hiểu là xóa trong tập thuộc tính endpoint quản lý. Với DTO record `String mail`, Jackson thường ánh xạ cả “missing” và JSON `null` thành Java null; nếu muốn `PATCH` phân biệt hai trường hợp, cần kiểu request hỗ trợ trạng thái presence.

Có thể dùng `JsonNode`, một cấu trúc `FieldUpdate<T>` hoặc thư viện biểu diễn nullable phù hợp. Ví dụ diễn giải:

~~~java
// Giả mã cách xác định thay đổi từ JSON patch:
if (!json.has("mail")) {
    // Không thêm ModificationItem cho mail.
} else if (json.get("mail").isNull()) {
    // REPLACE_ATTRIBUTE bằng tập rỗng -> xóa mail.
} else {
    // Validate mail, rồi REPLACE_ATTRIBUTE bằng giá trị mới.
}
~~~

Trước khi hỗ trợ patch tổng quát, hãy định nghĩa rõ có cho sửa những attribute nào và tránh để client tự gửi `ModificationItem` hay tên attribute tùy ý. `uid`, `objectClass`, group membership, password và các operational attributes thường cần endpoint và chính sách riêng.

Đừng coi **không xuất hiện trong kết quả đọc** đồng nghĩa với **yêu cầu xóa trong ghi**: một thuộc tính có thể vắng mặt do projection hoặc ACL.

## 13. Thiết kế quyền và kiểm soát từng thao tác

Spring Security có thể xác thực người dùng API qua LDAP bind, OIDC, session hoặc cơ chế khác. Tuy nhiên, `LdapTemplate`/repository thường thực hiện thao tác bằng **service account đã cấu hình**, không tự dùng DN/mật khẩu của người gọi HTTP.

Một chính sách phân quyền ví dụ:

| Đường dẫn | Quyền ứng dụng | Quyền LDAP của service account |
|---|---|---|
| `GET /api/people/{uid}` | `PEOPLE_READ` hoặc chính sách xem hồ sơ bản thân | Đọc các thuộc tính DTO cần thiết |
| `POST /api/people` | `PEOPLE_CREATE` | Add trong OU đã chỉ định |
| `PUT /api/people/{uid}` | `PEOPLE_UPDATE` | Modify `cn`, `sn`, `mail` |
| `DELETE /api/people/{uid}` | `PEOPLE_DELETE` | Delete trong phạm vi được phê duyệt |

Một cách thể hiện quyền tại service/controller bằng Spring Security method security:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;

// Gắn trên phương thức ghi sau khi đã bật @EnableMethodSecurity:
@PreAuthorize("hasAuthority('PEOPLE_CREATE')")
public void createPerson(CreatePersonRequest request) {
    service.create(request);
}
~~~

Đây là minh họa phương thức được bảo vệ; khi triển khai cần đặt annotation trên một **Spring bean được Spring Security quản lý**, cấu hình `@EnableMethodSecurity` và xác định rõ `Authentication`/authorities từ nguồn nào. Không mặc nhiên gắn annotation này vào code không qua Spring proxy rồi kỳ vọng nó tự thực thi.

**Phân quyền nghiệp vụ và ACL directory là hai lớp khác nhau.** Một service account có quyền sửa entry không có nghĩa mọi người đã đăng nhập được quyền gọi API sửa. Ngược lại, người gọi có role `PEOPLE_UPDATE` cũng không thể vượt qua ACL mà LDAP server áp dụng cho service account.

### Bảo mật dữ liệu và vận hành

- Bảo vệ HTTPS ở cổng HTTP và LDAPS/StartTLS ở kết nối tới directory, kiểm tra chứng chỉ/hostname.
- Bảo quản bind credential trong secret manager; không hardcode trong mã nguồn, image hoặc log.
- Nếu API dùng cookie/session, xem xét CSRF protection cho các request thay đổi dữ liệu; không tắt CSRF theo thói quen.
- Nếu dùng bearer token/stateless API, xác định rõ chính sách CORS, CSRF, token scope và expiry.
- Dùng rate limiting, audit event và kiểm soát các thao tác nguy hiểm, nhất là Delete.
- Hạn chế thuộc tính trả về, tránh log raw `Attributes`, password, thông tin cá nhân không cần thiết.
- Không lấy DN, search base, `objectClass` hoặc tên attribute ghi từ request tùy ý.

## 14. Tính nhất quán, retry và thao tác đồng thời

LDAP không phải cơ sở dữ liệu quan hệ với transaction đa bảng. Khi thiết kế REST API, cần xem xét:

**Tạo cùng lúc:** hai lệnh `POST` cùng DN cạnh tranh; một thao tác thành công, thao tác khác có thể nhận `entryAlreadyExists (68)`. Dựa vào directory để đảm bảo không trùng DN, không dùng duy nhất check-before-insert.

**Cập nhật cùng lúc:** hai client đọc rồi `PUT` trên cùng entry có thể ghi đè trường nhau theo thứ tự thực thi. `modifyAttributes` nhiều thuộc tính trong một request là atomic ở cấp entry, nhưng **không** tự cung cấp optimistic locking giữa hai request cạnh tranh.

**If-Match và ETag:** chỉ nên hỗ trợ khi ứng dụng có version token đáng tin cậy và cơ chế so khớp **nguyên tử ở LDAP**. Một lượt `lookup` rồi so `modifyTimestamp` trước khi Modify vẫn có race window. LDAP Assertion Control (RFC 4528), nếu được directory và client hỗ trợ, là một hướng thực hiện điều kiện kiểm tra tại server; không tự gắn nhãn ETag “chống ghi đè” khi chưa triển khai điều kiện nguyên tử thật.

**Retry khi mất phản hồi:** client có thể không biết thao tác Add/Modify/Delete đã hoàn tất hay chưa nếu kết nối bị ngắt sau khi server xử lý. Không tự retry vô hạn các lệnh ghi, đặc biệt khi có side effect khác như audit/provisioning. Với POST cần xem xét cơ chế idempotency key/tra cứu kết quả và chính sách xung đột thực tế.

**PUT:** gửi cùng biểu diễn nhiều lần thường có cùng hiệu quả mong muốn trên các thuộc tính endpoint quản lý (idempotent theo ý nghĩa HTTP), nhưng không bảo đảm không có cập nhật đồng thời từ tác nhân khác.

**DELETE:** xóa một lần và xóa lần hai đều dẫn đến trạng thái không còn entry, nhưng API có thể trả `204` lần đầu và `404` lần sau theo hợp đồng đã chọn. Idempotency nói đến **hiệu quả dự kiến**, không yêu cầu mọi lần gọi có cùng HTTP status.

**Nhiều entry:** thay một người dùng rồi sửa các giá trị `member` ở nhiều nhóm không tạo thành một transaction LDAP chung theo chuẩn cơ bản. Nếu có workflows như rename/move/delete người dùng và điều chỉnh membership, cần thiết kế saga/compensation hoặc cơ chế quản lý tham chiếu của directory server.

## 15. Kiểm thử từ controller đến directory

Kiểm thử chia thành các lớp:

| Loại test | Mục tiêu | Có kết nối LDAP? |
|---|---|---|
| Unit test service | Kiểm tra DN được xây đúng, mapping lỗi, chọn thao tác | Không bắt buộc; mock `LdapTemplate` |
| Controller test | JSON validation, routing, status, security | Thường mock service |
| Integration test | Add/Lookup/Modify/Delete thật và schema/ACL | Có, dùng directory test độc lập |
| Security test | Quyền đọc/ghi, CSRF/token và phân quyền nghiệp vụ | Có thể kết hợp test HTTP và LDAP riêng |
| Pre-prod smoke test | Kết nối, TLS, bind, search base, quyền an toàn | Có, ưu tiên read-only probe |

### Ma trận CRUD nên có

| Test case | Hành động | Kỳ vọng |
|---|---|---|
| GET thành công | Đọc UID đã có | `200` và DTO đúng |
| GET không tồn tại | UID không có | `404` |
| POST hợp lệ | Tạo entry đủ `cn`, `sn`, `uid` | `201`; đọc lại thấy DN đúng |
| POST trùng DN | Tạo cùng UID hai lần | `409` ở lần sau |
| POST thiếu bắt buộc | Không có `sn` | `400` ở API hoặc lỗi schema được chuyển có kiểm soát |
| PUT hợp lệ | Thay `cn` và `mail` | `204`; đọc lại đúng; không đổi UID |
| PUT xóa mail | Gửi `mail=null` | `mail` bị loại; các trường khác giữ nguyên |
| PUT UID không tồn tại | Thay dữ liệu ở DN thiếu | `404` |
| DELETE hợp lệ | Xóa một entry lá | `204`; lookup sau đó `404` |
| DELETE entry còn con | Xóa entry có cấp con | Server từ chối; không tự xóa cascade |
| Không đủ quyền API | Client không có role ghi | `403`; LDAP không được gọi |
| Service account thiếu ACL | API role hợp lệ nhưng LDAP từ chối | Lỗi backend phù hợp; không nhầm với role của client |
| Ký tự đặc biệt | UID/email nhập không hợp lệ | Validation hoặc DN builder xử lý an toàn |
| Race tạo cùng UID | Hai request POST đồng thời | Chỉ một DN được tạo |
| Directory không sẵn sàng | Dừng LDAP test | Lỗi 5xx/503 được quản lý, không lộ bind secret |

### Ví dụ integration test ở tầng service

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringBootTest
@ActiveProfiles("test")
class PersonDirectoryServiceIntegrationTest {

    @Autowired
    private PersonDirectoryService service;

    @Test
    void createsReadsUpdatesAndDeletesEntry() {
        String uid = "integration-test-user";

        service.create(new CreatePersonRequest(
                uid, "Test User", "User", null));
        try {
            PersonResponse created = service.get(uid);
            assertEquals("Test User", created.cn());

            service.replace(uid, new ReplacePersonRequest(
                    "Updated User", "User", "test@example.org"));

            PersonResponse updated = service.get(uid);
            assertEquals("Updated User", updated.cn());
            assertEquals("test@example.org", updated.mail());
        } finally {
            service.delete(uid);
        }

        assertThrows(
                PersonNotFoundException.class,
                () -> service.get(uid));
    }
}
~~~

**Điều kiện:** test profile kết nối tới LDAP test độc lập, `ou=people` tồn tại, service account có quyền Add/Modify/Delete và schema `inetOrgPerson` được cài đúng. Nếu fixture tồn tại từ lần chạy cũ hoặc lỗi trước khi tạo thành công, `finally` như trên có thể che lỗi gốc khi cố xóa DN không tồn tại; test suite thực tế nên chuẩn bị **unique fixture/cleanup idempotent**, ví dụ kiểm tra trạng thái hoặc xử lý lỗi NotFound riêng trong teardown.

Test trên kiểm tra sự tích hợp với LDAP nhưng chưa thay cho controller/security test. Với `MockMvc` và `spring-security-test`, kiểm tra `@Valid`, mã status, role và CSRF theo cấu hình HTTP đang áp dụng.

**Không chạy integration test ghi/xóa trên production directory.** Đặt `@ActiveProfiles("test")`, endpoint và credential test riêng; tốt nhất là khởi tạo directory tạm thời, nạp schema và fixture từ đầu.

## 16. Các lỗi thiết kế API thường gặp

| Lỗi | Hậu quả | Cách tránh |
|---|---|---|
| Cho client truyền DN đầy đủ | Có thể đọc/ghi ngoài OU cho phép | Chỉ nhận identifier, build DN phía server |
| Chỉ kiểm tra quyền ở UI | Client gọi API trực tiếp vượt qua UI | Spring Security kiểm tra từng endpoint/method |
| Dùng một service account quá quyền | Một lỗi ứng dụng có thể thay đổi toàn directory | ACL theo OU và thao tác cần thiết |
| PUT biến mọi `null` thành xóa | Mất attribute chưa được tải hoặc client không định gửi | Xác định hợp đồng PUT/PATCH rõ |
| Không kiểm tra schema | Add/Modify lỗi ở runtime khó dự đoán | Kiểm thử `objectClass`, MUST/MAY, naming rule |
| Repository `save` cho entity chỉ đọc một phần | Có nguy cơ ghi đè hoặc mất attribute | Dùng Modify có chủ đích, kiểm thử semantics |
| Nối chuỗi DN/filter | DN sai hoặc injection | `LdapNameBuilder`, `LdapQueryBuilder` |
| Dùng một endpoint Delete xóa cả subtree | Tác động vượt dự kiến | Không cascade mặc định, kiểm tra non-leaf |
| Catch mọi exception rồi trả 404 | Giấu lỗi network/TLS/ACL | Phân loại lỗi theo nguồn, báo 5xx khi backend lỗi |
| Tự retry POST sau timeout | Có thể tạo side effect trùng | Idempotency policy, xác minh kết quả |
| Trả raw LDAP entry | Lộ thông tin và ràng buộc JNDI ra API | DTO và projection tối thiểu |
| Giả định `uid` duy nhất toàn directory | Lấy sai danh tính ở tenant khác | Search base/OU và policy xác định duy nhất |
| Chọn ETag nhưng không có atomic precondition | Vẫn gặp lost update | Assertion Control hoặc giải pháp đồng bộ được chứng minh |

## 17. Bài tập thực hành

**Bối cảnh:** một hệ thống quản trị nội bộ sử dụng Spring Data LDAP, dữ liệu nhân viên nằm dưới `ou=people,dc=example,dc=org`. Cần tạo REST API để đọc, tạo, sửa tên/email và xóa một entry theo UID, với hai role `PEOPLE_READ` và `PEOPLE_WRITE`.

Thực hiện:

1. Dựng LDAP test với base DN, `ou=people`, schema `inetOrgPerson` và service account có ACL giới hạn.
2. Tạo `CreatePersonRequest`, `ReplacePersonRequest` và `PersonResponse`; mô tả chính xác field bắt buộc/tùy chọn.
3. Tạo `PersonDns.byUid(...)` bằng `LdapNameBuilder`; kiểm tra một UID bình thường và UID chứa dấu phẩy/ngoặc (bị policy chặn hoặc được escape theo thiết kế).
4. Viết service đọc entry bằng `ldapTemplate.lookup(...)` và mapper chỉ trả những attribute được phép.
5. Viết thao tác `bind(...)` tạo `inetOrgPerson`; xác minh DN và các thuộc tính MUST.
6. Viết `modifyAttributes(...)` để cập nhật `cn`, `sn`, `mail`, không đổi UID/objectClass.
7. Viết `unbind(...)` xóa entry lá, xử lý trường hợp entry không tồn tại.
8. Tạo REST controller với GET/POST/PUT/DELETE, mã `200/201/204/400/404/409` phù hợp.
9. Áp dụng Spring Security: tài khoản chỉ có `PEOPLE_READ` không gọi được POST/PUT/DELETE.
10. Test trùng UID, thiếu `sn`, mail không hợp lệ, UID vượt ranh giới, lỗi ACL và LDAP server không sẵn sàng.
11. Thiết kế thêm `PATCH /api/people/{uid}` phân biệt absent/null/value; giải thích vì sao một field `String mail` trong DTO không đủ.
12. Trình bày cách xử lý hai request PUT đồng thời và vì sao cần kiểm tra điều kiện cập nhật tại server nếu muốn tránh lost update.

**Tiêu chí hoàn thành:** API giữ đúng ranh giới OU, không lộ DN/credential nhạy cảm, trả mã HTTP có nghĩa, xử lý LDAP schema/ACL, không xóa nhầm thuộc tính và có integration test với directory độc lập.

## 18. Tổng kết và nguồn tham khảo

Thiết kế CRUD API với Spring Data LDAP yêu cầu nhiều hơn việc gọi `save` hay `delete`. **HTTP resource, DN, schema, ACL và kiểu thao tác LDAP là những khái niệm khác nhau nhưng phải được phối hợp nhất quán.**

Một kiến trúc dễ bảo trì là: controller nhận/validate DTO; service xác định DN và chính sách nghiệp vụ; repository/`LdapTemplate` thao tác LDAP; directory kiểm tra schema và quyền; `@RestControllerAdvice` chuyển lỗi có chủ đích thành HTTP. Dùng `bind` cho Add, `lookup`/`search` cho Read, `modifyAttributes` cho Update và `unbind` cho Delete. Đổi UID/RDN hoặc di chuyển entry là bài toán riêng về ModifyDN/rename.

Tài liệu tham khảo:

- [Spring Data LDAP Reference](https://docs.spring.io/spring-data/ldap/reference/): entity ODM, repository và tìm kiếm.
- [Spring LDAP Reference](https://docs.spring.io/spring-ldap/reference/): `LdapTemplate`, `ContextSource`, DN, thao tác bind/modify/unbind.
- [Spring Framework — Web MVC](https://docs.spring.io/spring-framework/reference/web/webmvc.html): controller, request mapping, validation và HTTP response.
- [Spring Framework — Error Responses](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html): `ProblemDetail` và xử lý ngoại lệ.
- [Spring Security — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): kiểm soát quyền tại lớp HTTP.
- [RFC 4511 — LDAP: The Protocol](https://www.rfc-editor.org/rfc/rfc4511): Add, Search, Modify, Delete, ModifyDN và mã kết quả.
- [RFC 4512 — LDAP: Directory Information Models](https://www.rfc-editor.org/rfc/rfc4512): DN, DIT, objectClass và thuộc tính.
- [RFC 4514 — Distinguished Names](https://www.rfc-editor.org/rfc/rfc4514): biểu diễn và escaping DN.
- [RFC 4528 — LDAP Assertion Control](https://www.rfc-editor.org/rfc/rfc4528): điều kiện nguyên tử cho thao tác LDAP khi server hỗ trợ.
