# Bật và cấu hình `@EnableLdapRepositories`

## 1. Mục tiêu và bối cảnh

Trong **Spring Data LDAP**, `@EnableLdapRepositories` kích hoạt cơ chế phát hiện các interface repository LDAP và tạo bean triển khai tương ứng để ứng dụng có thể truy cập một **dịch vụ thư mục LDAP** bằng mô hình repository. Người học cần phân biệt ba việc:

1. **Kích hoạt repository**: Spring quét các package Java chứa interface repository và tạo proxy.
2. **Kết nối đến directory**: `ContextSource` cung cấp địa chỉ máy chủ, base DN và danh tính bind; `LdapTemplate` thực hiện các thao tác LDAP.
3. **Ánh xạ entry**: các annotation ODM ánh xạ `DN`, `objectClass` và thuộc tính của entry sang đối tượng Java.

`@EnableLdapRepositories` chỉ đảm nhận việc thứ nhất và nối repository với `LdapTemplate`. Nó **không** tạo cây LDAP, tài khoản bind, schema, entry, hoặc tự thiết lập kết nối bảo mật.

Ví dụ xuyên suốt sử dụng directory minh họa:

```text
dc=example,dc=org                        <- base DN của kết nối
└── ou=people                             <- nhánh chứa người dùng
    ├── uid=alice                         <- DN đầy đủ: uid=alice,ou=people,dc=example,dc=org
    └── uid=bob
```

Một entry `uid=alice` có các object class `top`, `person`, `organizationalPerson`, `inetOrgPerson` và các thuộc tính như `uid`, `cn`, `sn`, `mail`. Tên và cấu trúc này chỉ là dữ liệu ví dụ; hệ thống thực tế phải dùng schema và đường dẫn DN mà máy chủ cho phép.

Luồng xử lý:

```text
Service / Controller
       |
       v
DirectoryUserRepository (interface)
       |  do @EnableLdapRepositories tạo proxy
       v
Spring Data LDAP repository implementation
       |
       v
LdapTemplate -> ContextSource -> LDAP/LDAPS server
       |
       v
ODM: @Entry / @Id / @Attribute <-> LDAP entry
```

## 2. Điều kiện tiên quyết

- Ứng dụng có **Spring Data LDAP** và **Spring LDAP** trên classpath. Với Spring Boot, lựa chọn phổ biến là starter `spring-boot-starter-data-ldap` và phiên bản do Spring Boot quản lý.
- Máy chủ LDAP/LDAPS đang chạy, tồn tại base DN và nhánh cần tra cứu (ví dụ `ou=people`), có tài khoản bind đủ quyền đọc/ghi tương ứng.
- Đã xác định object class và thuộc tính theo schema: `inetOrgPerson` thường yêu cầu `cn` và `sn`; `uid` và `mail` phụ thuộc dữ liệu và chính sách máy chủ.
- Cấu hình mạng, chứng chỉ máy chủ và quyền truy cập directory được chuẩn bị trước khi thử thao tác ghi.

Ví dụ khai báo dependency với Maven **khi dự án dùng Spring Boot và quản lý dependency bằng BOM/plugin của Boot**:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-ldap</artifactId>
</dependency>
```

Không cần phụ thuộc JPA để làm việc với LDAP. Các annotation `@Entity` hay `@Id` của JPA/Spring Data không thay thế cho annotation ODM của Spring LDAP.

## 3. Bật repository trong Spring Boot

Với starter LDAP, Spring Boot thường **tự cấu hình** `ContextSource`, `LdapTemplate` và repository LDAP, đồng thời quét từ package ứng dụng chính và các package con. Khi tổ chức code đúng cấu trúc mặc định, nhiều ứng dụng **không cần khai báo** `@EnableLdapRepositories`.

Tuy nhiên, nếu repository nằm ngoài vùng quét mặc định hoặc cần chỉ định rõ repository nào dùng `LdapTemplate` nào, hãy cấu hình annotation chủ động:

```java
package com.example.identity.config;

import com.example.identity.ldap.DirectoryUserRepository;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.ldap.repository.config.EnableLdapRepositories;

@Configuration
@EnableLdapRepositories(
    basePackageClasses = DirectoryUserRepository.class
)
public class LdapRepositoryConfiguration {
}
```

`basePackageClasses` lấy **package chứa class/interface được chỉ định** làm gốc quét. Ở đây `DirectoryUserRepository` là marker để cấu hình không phụ thuộc vào chuỗi package dễ gõ sai. Spring vẫn tìm các interface repository đủ điều kiện trong package đó; nó không chỉ đăng ký đúng một interface được truyền vào.

Kết nối có thể khai báo trong `application.yml`:

```yaml
spring:
  ldap:
    urls: ${LDAP_URL}
    base: dc=example,dc=org
    username: ${LDAP_BIND_DN}
    password: ${LDAP_BIND_PASSWORD}
```

Ví dụ giá trị biến môi trường cho môi trường thử nghiệm: `LDAP_URL=ldaps://ldap.example.org:636`, `LDAP_BIND_DN=cn=service-reader,ou=system,dc=example,dc=org`. Lấy mật khẩu từ secret manager hoặc biến môi trường, không đưa mật khẩu thật vào Git. Dùng **LDAPS** hoặc **StartTLS** với cấu hình xác thực chứng chỉ phù hợp trong môi trường thực tế.

> **Phân biệt hai kiểu base**: `basePackageClasses`/`basePackages` là **package Java** cần quét; `spring.ldap.base` là **DN trong cây LDAP**. Không thay thế hai giá trị cho nhau. Ví dụ, `com.example.identity.ldap` không phải LDAP DN và `dc=example,dc=org` không phải package Java.

## 4. Định nghĩa entry và repository cho ví dụ

Trước khi thấy `@EnableLdapRepositories` hoạt động, cần có một entity ODM và một repository hợp lệ. Ví dụ sử dụng package `com.example.identity.ldap`:

```java
package com.example.identity.ldap;

import javax.naming.Name;
import org.springframework.ldap.odm.annotations.Attribute;
import org.springframework.ldap.odm.annotations.DnAttribute;
import org.springframework.ldap.odm.annotations.Entry;
import org.springframework.ldap.odm.annotations.Id;

@Entry(
    base = "ou=people",
    objectClasses = {"top", "person", "organizationalPerson", "inetOrgPerson"}
)
public class DirectoryUser {
    @Id
    private Name dn;

    @Attribute(name = "uid")
    @DnAttribute(value = "uid", index = 0)
    private String uid;

    @Attribute(name = "cn")
    private String commonName;

    @Attribute(name = "sn")
    private String surname;

    @Attribute(name = "mail")
    private String email;

    public DirectoryUser() {}

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

Những điểm cần đọc kỹ:

- `@Entry` thuộc `org.springframework.ldap.odm.annotations`; `base = "ou=people"` giới hạn vùng entry của kiểu `DirectoryUser` **tương đối với** base DN của `ContextSource`.
- `@Id` phải là `org.springframework.ldap.odm.annotations.Id` và trường DN có kiểu `javax.naming.Name` (hoặc lớp triển khai như `LdapName`). Đây là **định danh LDAP**, không phải khóa số tự tăng.
- `@Attribute` ánh xạ thuộc tính Java sang tên thuộc tính LDAP. Đặt tên Java `surname` nhưng thuộc tính LDAP vẫn là `sn`.
- `@DnAttribute(value = "uid", index = 0)` cho phép ODM lấy `uid` từ RDN và hỗ trợ tính DN khi tạo entry mới. Chỉ nên dùng quy tắc này khi dữ liệu tuân theo DN dạng `uid=<giá trị>,ou=people,...`. Việc thay đổi `uid` có thể kéo theo đổi DN/di chuyển entry; cần cân nhắc trước khi sửa.
- `objectClasses` phải khớp schema và object classes của entry. Khi tạo mới, LDAP yêu cầu đủ thuộc tính bắt buộc và phải cho phép các object classes được khai báo.

Tạo repository:

```java
package com.example.identity.ldap;

import java.util.List;
import java.util.Optional;
import org.springframework.data.ldap.repository.LdapRepository;

public interface DirectoryUserRepository extends LdapRepository<DirectoryUser> {
    Optional<DirectoryUser> findByUid(String uid);
    List<DirectoryUser> findBySurname(String surname);
}
```

Chỉ cần interface; Spring Data tạo phần triển khai tại runtime khi `@EnableLdapRepositories` phát hiện interface đó. `LdapRepository<T>` chỉ có **một** tham số kiểu entity và kế thừa các thao tác CRUD với kiểu ID `Name`. Viết `LdapRepository<DirectoryUser, Long>` là sai số lượng type parameter; `CrudRepository<DirectoryUser, Long>` cũng không phù hợp với DN LDAP.

`findByUid` và `findBySurname` được phân tích thành truy vấn dựa trên tên thuộc tính của entity. Tham số được xử lý qua cơ chế query của framework, giúp hạn chế rủi ro ghép filter từ chuỗi do người dùng nhập.

## 5. Cách viết `@EnableLdapRepositories` và các tham số quan trọng

```java
// Quét package theo chuỗi:
@EnableLdapRepositories(basePackages = "com.example.identity.ldap")

// Cú pháp rút gọn của basePackages:
@EnableLdapRepositories("com.example.identity.ldap")

// Quét theo package của interface được chỉ định:
@EnableLdapRepositories(basePackageClasses = DirectoryUserRepository.class)
```

Ba cách trên thay thế cho nhau trong cùng một cấu hình; không dùng đồng thời `value` và `basePackages`. Nếu không khai báo package nào, Spring quét từ package chứa class được gắn `@EnableLdapRepositories`. Vì thế, đặt class cấu hình quá sâu trong `com.example.identity.config` có thể khiến repository nằm ở `com.example.identity.ldap` không được phát hiện.

| Thuộc tính | Chức năng | Khi nào nên dùng |
| --- | --- | --- |
| `value` / `basePackages` | Chỉ định một hoặc nhiều package Java để quét repository. | Cấu trúc repository trải trên nhiều package. |
| `basePackageClasses` | Chỉ định package qua lớp/interface có thật, tránh lỗi do chuỗi. | Khuyến nghị cho cấu hình ổn định và dễ refactor. |
| `ldapTemplateRef` | Tên bean `LdapTemplate` mà repository sử dụng; mặc định `ldapTemplate`. | Có nhiều kết nối directory hoặc đổi tên bean template. |
| `includeFilters` / `excludeFilters` | Thu hẹp tập repository được phát hiện trong các package đã chọn. | Một package chứa nhiều nhóm repository. |
| `repositoryImplementationPostfix` | Hậu tố tìm implementation tùy biến, mặc định `Impl`. | Repository có phần hiện thực tự viết. |
| `queryLookupStrategy` | Cách chọn truy vấn: tạo từ tên phương thức hoặc dùng truy vấn khai báo. | Muốn áp chính sách cho query methods. |
| `namedQueriesLocation` | Đường dẫn tài nguyên truy vấn đã đặt tên. | Dùng named queries ngoài source code. |

Điểm nhạy cảm nhất thường là `ldapTemplateRef`: annotation **tham chiếu theo tên bean**, nên tên cấu hình và tên bean phải trùng chính xác. `@EnableLdapRepositories` cũng không tự chọn template khác chỉ vì có nhiều `LdapTemplate` trong application context.

## 6. Cấu hình thuần Spring khi không dùng auto-configuration

Đây là biến thể Java Config khi ứng dụng cần tự tạo `ContextSource` và `LdapTemplate` (thay cho phần auto-config của Boot):

```java
package com.example.identity.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;
import org.springframework.data.ldap.repository.config.EnableLdapRepositories;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.core.support.LdapContextSource;

@Configuration
@EnableLdapRepositories(basePackages = "com.example.identity.ldap")
public class ManualLdapConfiguration {

    @Bean
    public LdapContextSource contextSource(Environment env) {
        LdapContextSource source = new LdapContextSource();
        source.setUrl(env.getRequiredProperty("ldap.url"));
        source.setBase(env.getRequiredProperty("ldap.base"));
        source.setUserDn(env.getRequiredProperty("ldap.bindDn"));
        source.setPassword(env.getRequiredProperty("ldap.bindPassword"));
        return source;
    }

    @Bean
    public LdapTemplate ldapTemplate(LdapContextSource contextSource) {
        return new LdapTemplate(contextSource);
    }
}
```

Giá trị `ldap.url`, `ldap.base`, `ldap.bindDn`, `ldap.bindPassword` phải được nạp vào Spring `Environment` từ cấu hình bên ngoài. Spring quản lý lifecycle của `LdapContextSource` khi nó được tạo bằng `@Bean`. Khi dùng Boot, ưu tiên phần tự cấu hình ở mục 3 để tránh tạo hai bộ bean có nhiệm vụ trùng nhau.

Giải thích đường đi DN: Nếu `source.setBase("dc=example,dc=org")` và entity có `@Entry(base = "ou=people")`, entry người dùng `alice` có DN đầy đủ là `uid=alice,ou=people,dc=example,dc=org`. Các DN được truyền cho Spring LDAP thường **tương đối với** base DN trong `ContextSource`; không tự nối lại `dc=example,dc=org` một lần nữa.

## 7. Nhiều directory hoặc nhiều template

Một ứng dụng có thể tra cứu hai LDAP server, chẳng hạn directory nhân sự và directory đối tác. Khi đó, tạo hai `ContextSource` và hai `LdapTemplate` tương ứng, sau đó gắn từng nhóm repository với đúng template:

```java
@Configuration
@EnableLdapRepositories(
    basePackages = "com.example.identity.hr",
    ldapTemplateRef = "hrLdapTemplate"
)
class HrLdapRepositoriesConfig {
    // Bean hrLdapTemplate phải được khai báo trong ApplicationContext.
}

@Configuration
@EnableLdapRepositories(
    basePackages = "com.example.identity.partners",
    ldapTemplateRef = "partnerLdapTemplate"
)
class PartnerLdapRepositoriesConfig {
    // Bean partnerLdapTemplate phải được khai báo trong ApplicationContext.
}
```

Hai nhóm package repository nên **không giao nhau** để tránh một interface được đăng ký hai lần hoặc vô tình truy vấn sai directory. Nếu đồng thời dùng Spring Boot auto-configuration, kiểm tra phạm vi quét tự động để tránh đăng ký bean trùng. Khi đổi tên template (ví dụ `hrLdapTemplate`), nhất thiết khai báo `ldapTemplateRef` tương ứng; mặc định của annotation vẫn là `ldapTemplate`.

## 8. Sử dụng repository sau khi bật

Một dịch vụ có thể inject repository giống cách dùng repository Spring Data khác:

```java
package com.example.identity.service;

import com.example.identity.ldap.DirectoryUser;
import com.example.identity.ldap.DirectoryUserRepository;
import java.util.Optional;
import javax.naming.Name;
import org.springframework.stereotype.Service;

@Service
public class DirectoryUserService {
    private final DirectoryUserRepository users;

    public DirectoryUserService(DirectoryUserRepository users) {
        this.users = users;
    }

    public Optional<DirectoryUser> findByUid(String uid) {
        return users.findByUid(uid);
    }

    public DirectoryUser create(String uid, String fullName,
                                String surname, String email) {
        DirectoryUser user = new DirectoryUser();
        user.setUid(uid);
        user.setCommonName(fullName);
        user.setSurname(surname);
        user.setEmail(email);
        return users.save(user);
    }

    public DirectoryUser changeEmail(Name dn, String email) {
        DirectoryUser user = users.findById(dn).orElseThrow();
        user.setEmail(email);
        return users.save(user);
    }

    public void delete(Name dn) {
        users.deleteById(dn);
    }
}
```

Trong ví dụ này, `create` chỉ hoạt động nếu nhánh `ou=people` tồn tại, `uid` tạo thành RDN hợp lệ, `cn`/`sn` đáp ứng schema, entry chưa tồn tại và tài khoản bind có quyền ghi. Ví dụ được giữ đơn giản để minh họa repository: dịch vụ thực tế cần kiểm tra dữ liệu đầu vào, xử lý trùng UID/race condition và chính sách quyền tạo/xóa. `changeEmail` giữ nguyên `uid` để tránh vô tình đổi DN.

Trường hợp tìm kiếm linh hoạt hơn, `LdapRepository` còn hỗ trợ đối số `LdapQuery`:

```java
import static org.springframework.ldap.query.LdapQueryBuilder.query;

// Với đối tượng DirectoryUserRepository repository:
var matches = repository.findAll(
    query().where("mail").is("alice@example.org")
);
```

Không ghép trực tiếp chuỗi LDAP filter kiểu `"(&(uid=" + input + "))"` từ dữ liệu chưa tin cậy. Với filter thủ công, dùng `LdapQueryBuilder` hoặc placeholder query được framework escape đúng cách; các biểu thức SpEL trong `@Query` cần được đánh giá thêm vì không tự động escape giá trị như tham số thông thường.

**Giới hạn cần nhớ:** LDAP repository không cung cấp đầy đủ tính năng phân trang/sắp xếp `Pageable` và `Sort` như nhiều Spring Data store khác. Khi cần tìm kiếm lớn hoặc điều khiển search controls, hãy cân nhắc `LdapTemplate` và các cơ chế LDAP server hỗ trợ thay vì giả định mọi API JPA đều áp dụng.

## 9. Kiểm chứng cấu hình

Kiểm tra theo thứ tự sau, vì mỗi bước khoanh vùng một loại lỗi riêng:

1. **Khởi tạo context:** ứng dụng khởi động được, bean `DirectoryUserRepository` được đăng ký và inject thành công. Nếu bean thiếu, kiểm tra package scan và đúng annotation `org.springframework.data.ldap.repository.config.EnableLdapRepositories`.
2. **Kết nối và bind:** thử truy vấn một entry đã tồn tại bằng tài khoản dịch vụ, kiểm tra URL, TLS, bind DN, quyền đọc và base DN.
3. **ODM và schema:** kiểm tra entry trả về có `objectClass` phù hợp; `uid`, `sn`, `cn` ánh xạ đúng; DN không bị nhân đôi.
4. **Ghi có kiểm soát:** dùng directory thử nghiệm và entry riêng để thử tạo, sửa, xóa, sau đó dọn dữ liệu thử. Tránh chạy phép xóa trên directory dùng chung.

Ví dụ integration test, **giả sử** directory thử nghiệm đã được seed entry `uid=alice` với `sn=Nguyen`:

```java
import static org.assertj.core.api.Assertions.assertThat;

import com.example.identity.ldap.DirectoryUserRepository;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class DirectoryUserRepositoryIT {
    @Autowired
    DirectoryUserRepository repository;

    @Test
    void findsExistingEntryByUid() {
        var user = repository.findByUid("alice").orElseThrow();
        assertThat(user.getSurname()).isEqualTo("Nguyen");
        assertThat(user.getDn()).isNotNull();
    }
}
```

Test này xác minh xuyên suốt từ cấu hình repository đến kết nối và ánh xạ LDAP. Cần cấu hình test kết nối tới directory kiểm thử thật hoặc LDAP server tạm thời có dữ liệu seed tương ứng; chạy test chỉ với context trống không đủ để xác nhận query hoạt động.

## 10. Chẩn đoán lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| `NoSuchBeanDefinitionException` đối với repository | Package chưa được scan hoặc thiếu dependency Spring Data LDAP. | Chỉ rõ `basePackageClasses`, kiểm tra import annotation và classpath. |
| Không tìm thấy bean `ldapTemplate` | Chưa cấu hình `LdapTemplate` hoặc `ldapTemplateRef` sai tên. | Khai báo bean đúng tên, hoặc trỏ đến tên template thực tế. |
| `AuthenticationException` / bind thất bại | Sai bind DN/mật khẩu, tài khoản bị khóa hoặc cơ chế xác thực khác. | Kiểm tra bind bằng tài khoản thử nghiệm và cấu hình directory. |
| `CommunicationException` / lỗi bắt tay TLS | Sai host, port, sơ đồ `ldap://`/`ldaps://`, chứng chỉ/truststore. | Kiểm tra mạng, URL, xác thực chứng chỉ và cấu hình TLS. |
| Tìm kiếm trả về rỗng dù entry tồn tại | Base DN hoặc `@Entry(base=...)` sai; objectClass không khớp; account thiếu quyền search. | Đối chiếu DN đầy đủ và LDAP schema với entry thực tế. |
| `InvalidAttributeValueException` / `SchemaViolationException` khi lưu | Thiếu thuộc tính bắt buộc hoặc `objectClass` không hợp lệ. | Kiểm tra `cn`, `sn`, object classes và quy tắc schema trên server. |
| Ghi bị `InsufficientAccessRightsException` | Tài khoản bind chỉ có quyền đọc. | Cấp quyền tối thiểu phù hợp hoặc dùng tài khoản dịch vụ chuyên dụng. |
| Repository bị đăng ký trùng | Nhiều vùng `@EnableLdapRepositories` trùng nhau hoặc trùng auto-config. | Tách rõ phạm vi quét và đối chiếu các configuration. |
| Không tìm được `@Id` hoặc xử lý DN sai | Dùng nhầm `org.springframework.data.annotation.Id`; dùng `Long` thay `Name`; ghép trùng base DN. | Dùng `org.springframework.ldap.odm.annotations.Id`, `javax.naming.Name` và DN tương đối đúng. |

**Lưu ý vận hành:** một bean repository khởi tạo thành công **không chứng minh** LDAP server đang sẵn sàng: nhiều lỗi kết nối chỉ xuất hiện khi thực hiện truy vấn đầu tiên. Đặt timeout phù hợp, theo dõi lỗi kết nối và kiểm thử với directory thật trước khi đưa vào hệ thống.

## 11. Bài tập áp dụng

1. Cho cấu trúc `com.example.app.config`, `com.example.app.ldap` và `com.example.app.jpa`. Hãy viết cấu hình chỉ quét repository LDAP trong `com.example.app.ldap`; giải thích tại sao `@EnableLdapRepositories` không nhận `dc=example,dc=org` làm `basePackages`.
2. Chuyển cấu hình từ một `LdapTemplate` sang hai template `employeesLdapTemplate` và `partnersLdapTemplate`. Xác định `ldapTemplateRef`, phạm vi package và một phép thử xác nhận repository gọi đúng directory.
3. Với entry `uid=alice,ou=people,dc=example,dc=org`, hãy chỉ ra giá trị của `spring.ldap.base`, `@Entry(base=...)` và `@DnAttribute` trong ví dụ. Nếu kết quả tìm kiếm trống, bạn sẽ kiểm tra yếu tố nào trước?
4. Viết integration test đọc `uid=alice` từ directory thử nghiệm, xác minh `cn` và `sn`, sau đó thử cập nhật `mail` trên entry thử nghiệm có quyền ghi. Không dùng directory sản xuất cho bài tập này.

## Tài liệu tham khảo

- [Spring Data LDAP — Configuration](https://docs.spring.io/spring-data/ldap/reference/ldap/configuration.html): kích hoạt repository và cấu hình `LdapTemplate`.
- [Spring Data LDAP — EnableLdapRepositories API](https://docs.spring.io/spring-data/ldap/reference/api/java/org/springframework/data/ldap/repository/config/EnableLdapRepositories.html): các tham số của annotation và giá trị mặc định.
- [Spring Data LDAP — Query Methods](https://docs.spring.io/spring-data/ldap/reference/ldap/query-methods.html): query từ tên phương thức, `@Query` và cách mã hóa tham số.
- [Spring LDAP — Object-Directory Mapping](https://docs.spring.io/spring-ldap/reference/odm.html): `@Entry`, `@Id`, `@Attribute`, `@DnAttribute` và quy tắc DN.
- [Spring Boot — Working with NoSQL Technologies, LDAP](https://docs.spring.io/spring-boot/reference/data/nosql.html): auto-configuration, cấu hình kết nối, SSL và khám phá repository.
