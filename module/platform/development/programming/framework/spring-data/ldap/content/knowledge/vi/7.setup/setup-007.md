# Cấu hình thủ công khi cần nhiều nguồn thư mục hoặc tùy chọn riêng

Trong **Spring Data LDAP**, trường hợp đơn giản nhất là một ứng dụng kết nối một LDAP server bằng cấu hình `spring.ldap.*` của Spring Boot, sau đó dùng `LdapTemplate` hoặc `LdapRepository` để tra cứu và cập nhật entry. Tuy nhiên, nhiều hệ thống thực tế phải tích hợp **hai hoặc nhiều directory độc lập**: thư mục nhân sự nội bộ, thư mục đối tác, Microsoft Active Directory phục vụ đăng nhập, hoặc một directory chuyên quản lý nhóm.

Ngoài việc có nhiều nguồn, từng directory có thể dùng **base DN, tài khoản bind, TLS, timeout, referral policy, connection pool và cách ánh xạ entity** khác nhau. Nếu để mọi repository tự động tìm một bean `ldapTemplate` mặc định, ứng dụng có thể đọc **sai nơi**, tìm không thấy entry hoặc nghiêm trọng hơn là **ghi dữ liệu vào directory không dự định**.

Chủ đề thuộc chương **Khởi tạo** này hướng dẫn cấu hình Java thủ công theo các tầng:

```text
Directory properties / secrets
             │
             ▼
ContextSource riêng cho từng directory
             │
             ▼
LdapTemplate riêng cho từng directory
             │
       ┌─────┴─────────┐
       ▼               ▼
LdapRepository      LdapTemplate
đúng nhóm package    tra cứu tùy biến
       │               │
       └───────┬───────┘
               ▼
       Application service
       (chọn nguồn rõ ràng)
```

Sau bài học, bạn có thể:

1. Quyết định khi nào **Spring Boot auto-configuration** đủ dùng và khi nào cần Java config thủ công.
2. Tạo **hai `LdapContextSource` và hai `LdapTemplate`**, được đặt tên rõ ràng và gắn bằng `@Qualifier`.
3. Dùng `@EnableLdapRepositories(ldapTemplateRef = "...")` để gắn đúng repository với đúng nguồn LDAP.
4. Cấu hình `base DN`, bind credential, TLS, JNDI timeout, search limit và referral theo chính sách từng directory.
5. Phân biệt **nhiều URL dự phòng cho cùng một directory** với **nhiều directory độc lập**.
6. Kiểm tra các rủi ro cross-directory, sai DN, ACL, consistency, pooling và tự động cấu hình xung đột.
7. Viết integration test để xác minh một request không bao giờ vô tình đọc/ghi ở nguồn còn lại.

## 1. Ba kiến trúc cần phân biệt trước khi cấu hình

Không phải cứ nhìn thấy hai URL LDAP là phải tạo hai `LdapTemplate`. Cần hiểu **hai URL đại diện cho cùng một hệ dữ liệu hay hai hệ dữ liệu khác nhau**.

| Tình huống | Ví dụ | Hướng cấu hình |
| --- | --- | --- |
| Một directory, một endpoint | `ldaps://ldap.example.org:636` | Có thể dùng auto-configuration của Spring Boot |
| Một directory có nhiều server replica/điểm dự phòng | `ldaps://ldap-a.example.org:636` và `ldaps://ldap-b.example.org:636` | Cân nhắc `setUrls(...)` trên một `ContextSource` nếu cùng naming context và chính sách phù hợp |
| Hai directory độc lập | Nhân sự ở `dc=corp,dc=example`, đối tác ở `dc=partners,dc=example` | **Hai ContextSource + hai LdapTemplate** với routing tường minh |
| Hai hệ thống authentication và read-only lookup dùng quyền khác nhau | Bind user trên AD, đọc profile qua LDAP service account | Tách đường xác thực khỏi truy vấn dữ liệu; xem xét nhiều bean |
| Nhiều directory với cùng schema nhưng dữ liệu khác nhau | Hai tenant có LDAP riêng | Mỗi tenant có nguồn, credential và chính sách rõ; không chọn nguồn theo chuỗi URL do client đưa trực tiếp |

**`LdapContextSource.setUrls(String[])` không phải bộ router nhiều tenant.** Nó cung cấp nhiều URL để provider kết nối với cùng nguồn logic theo cơ chế và giới hạn của LDAP/JNDI. Không đưa những directory khác base, khác schema hoặc khác quyền truy cập vào `setUrls` rồi mong repository tự biết nơi nào chứa user.

### 1.1. Ví dụ bài học: staff và partner

Giả sử ứng dụng cần truy vấn:

```text
Directory STAFF                       Directory PARTNER
ldaps://staff-ldap.example.org:636    ldaps://partner-ldap.example.org:636
base: dc=corp,dc=example              base: dc=partners,dc=example
  └── ou=people                          └── ou=contacts
      ├── uid=lan                            ├── uid=supplier01
      └── uid=minh                           └── uid=supplier02
```

Hai nguồn có schema, ACL và user base khác nhau. Ứng dụng có thể dùng `PersonRepository` cho STAFF và `PartnerContactRepository` cho PARTNER; nếu có nhu cầu hợp nhất kết quả để hiển thị, service **gọi từng nguồn có chủ đích** rồi chuyển thành DTO chung, không coi hai directory như một cơ sở dữ liệu LDAP thống nhất.

## 2. Khi nào Spring Boot auto-configuration không đủ?

Spring Boot hỗ trợ cấu hình kết nối LDAP cơ bản:

```yaml
spring:
  ldap:
    urls: ldaps://staff-ldap.example.org:636
    base: dc=corp,dc=example
    username: uid=app-reader,ou=services,dc=corp,dc=example
    password: ${STAFF_LDAP_PASSWORD}
```

Với starter thích hợp, Boot có thể cung cấp `LdapContextSource`, `LdapTemplate` và hỗ trợ tạo Spring Data LDAP repositories theo các điều kiện auto-configuration của phiên bản. Một đường cấu hình tập trung này phù hợp khi ứng dụng chỉ sử dụng **một nguồn LDAP logic**.

Khi có **hai nguồn**, cần quản lý riêng:

- URL hoặc tập replica của từng directory.
- Base DN và cấu trúc `ou=people`, `ou=contacts` tương ứng.
- Bind DN/secret và quyền đọc/ghi.
- Timeout, referral policy và connection pool.
- Tên bean `ContextSource`, `LdapTemplate`.
- Tập repository nào dùng template nào.

Vì vậy, ta tạo **namespace cấu hình ứng dụng riêng**, chẳng hạn `app.directories.staff.*` và `app.directories.partner.*`. Đây là **property tự định nghĩa**, không phải hai tập `spring.ldap.*` được Boot tự hiểu.

### 2.1. Dependency mẫu

Trong Spring Boot, dependency thường dùng là:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-ldap'
    // Chỉ thêm spring-security-ldap nếu ứng dụng có LDAP authentication.
    // implementation 'org.springframework.security:spring-security-ldap'
}
```

Ví dụ giả định project đã có Spring Boot plugin/dependency management và Java tương thích. Không tự ghi phiên bản Spring LDAP/Spring Data LDAP tùy ý vào dependency nếu dự án sử dụng BOM của Spring Boot. Package nguồn ODM/LDAP vẫn nằm dưới `org.springframework.ldap.*` và Spring Data repository dưới `org.springframework.data.ldap.*`.

## 3. Định nghĩa cấu hình riêng cho từng directory

Ví dụ `application.yml`:

```yaml
app:
  directories:
    staff:
      url: ldaps://staff-ldap.example.org:636
      base: dc=corp,dc=example
      bind-dn: uid=app-reader,ou=services,dc=corp,dc=example
      bind-password: ${STAFF_LDAP_PASSWORD}
    partner:
      url: ldaps://partner-ldap.example.org:636
      base: dc=partners,dc=example
      bind-dn: uid=partner-reader,ou=services,dc=partners,dc=example
      bind-password: ${PARTNER_LDAP_PASSWORD}

# Chỉ dùng khi bạn chủ động cấu hình @EnableLdapRepositories thủ công.
spring:
  data:
    ldap:
      repositories:
        enabled: false
```

Các địa chỉ và DN là **giả định**. Những biến môi trường mang tên `STAFF_LDAP_PASSWORD`, `PARTNER_LDAP_PASSWORD` phải được cấp qua secret store hoặc cơ chế triển khai an toàn; không commit password vào source code.

Ở các bản Spring Boot hỗ trợ property `spring.data.ldap.repositories.enabled`, đặt `false` giúp **tắt quét repository tự động của Boot**, tránh quét trùng khi ta tự khai báo `@EnableLdapRepositories` cho từng nhóm. **Nó không vô hiệu hóa các annotation `@EnableLdapRepositories` do ta chủ động tạo.** Luôn kiểm tra property và điều kiện auto-configuration đúng với phiên bản Spring Boot đang sử dụng.

### 3.1. Vì sao không dùng `spring.ldap.urls` cho cả hai nguồn?

`spring.ldap.urls` thường cấu hình **một tập server của một `ContextSource` logic**, không phải map tên STAFF/PARTNER với bean tương ứng. Để hỗ trợ hai base, hai mật khẩu và các giới hạn riêng, ứng dụng phải **tạo và đặt tên bean** tường minh.

Đừng sao chép cấu hình `spring.ldap.base` của STAFF vào PARTNER theo thói quen. Base DN sai không chỉ dẫn tới `NameNotFoundException` mà còn có thể làm truy vấn chạy ở nhánh không dự kiến khi server cho phép.

## 4. Tạo hai LdapContextSource bằng Java Config

`LdapContextSource` (Spring LDAP) là đối tượng tạo những `DirContext` để thực hiện LDAP operation. Một instance xác định nơi kết nối, thông tin bind và base DN.

Ví dụ Spring Java configuration:

```java
import java.util.Map;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ldap.core.support.LdapContextSource;

@Configuration(proxyBeanMethods = false)
public class MultiDirectoryContextConfiguration {

    @Bean("staffContextSource")
    public LdapContextSource staffContextSource(
            @Value("${app.directories.staff.url}") String url,
            @Value("${app.directories.staff.base}") String base,
            @Value("${app.directories.staff.bind-dn}") String bindDn,
            @Value("${app.directories.staff.bind-password}") String password) {

        return contextSource(url, base, bindDn, password);
    }

    @Bean("partnerContextSource")
    public LdapContextSource partnerContextSource(
            @Value("${app.directories.partner.url}") String url,
            @Value("${app.directories.partner.base}") String base,
            @Value("${app.directories.partner.bind-dn}") String bindDn,
            @Value("${app.directories.partner.bind-password}") String password) {

        return contextSource(url, base, bindDn, password);
    }

    private static LdapContextSource contextSource(
            String url, String base, String bindDn, String password) {

        LdapContextSource source = new LdapContextSource();
        source.setUrl(url);
        source.setBase(base);
        source.setUserDn(bindDn);
        source.setPassword(password);
        source.setPooled(false);
        source.setReferral("ignore");
        source.setBaseEnvironmentProperties(Map.of(
                "java.naming.ldap.connect.timeout", "3000",
                "java.naming.ldap.read.timeout", "5000"));
        return source;
    }
}
```

**Các lựa chọn có chủ đích:**

- `setUrl(...)`: URL của đúng directory. Ví dụ dùng **`ldaps://`** và phải có truststore/hostname validation phù hợp.
- `setBase(...)`: DN gốc của các thao tác qua context. Ở STAFF là `dc=corp,dc=example`, ở PARTNER là `dc=partners,dc=example`.
- `setUserDn(...)`/`setPassword(...)`: principal và secret dùng cho **service-side operations** của context; không phải user credentials của một HTTP request.
- `setPooled(false)`: không bật native JNDI pooling khi chưa có thiết kế. Đây cũng là mặc định được Spring LDAP tài liệu hóa.
- `setReferral("ignore")`: ví dụ policy không tự động theo referral sang directory thứ ba. Policy `follow`/`throw` phải được thiết kế và kiểm thử riêng.
- `setBaseEnvironmentProperties(...)`: cung cấp JNDI connect/read timeout bằng chuỗi **millisecond**.

Trong ví dụ bean `@Bean`, Spring gọi lifecycle initialization theo `InitializingBean` của `LdapContextSource`. **Nếu tự tạo object ngoài Spring context**, cần gọi `afterPropertiesSet()` sau khi cấu hình đầy đủ trước khi sử dụng.

### 4.1. Base DN và DN tương đối

Với STAFF source:

```text
ContextSource base = dc=corp,dc=example
DN truyền cho LdapTemplate = uid=lan,ou=people
DN trên LDAP server = uid=lan,ou=people,dc=corp,dc=example
```

Với PARTNER source:

```text
ContextSource base = dc=partners,dc=example
DN truyền cho LdapTemplate = uid=supplier01,ou=contacts
DN trên LDAP server = uid=supplier01,ou=contacts,dc=partners,dc=example
```

DN tương đối **có thể trông giống nhau** giữa hai nguồn nhưng không đại diện cùng một entry. Nếu user chuyển nguyên một DN tương đối của STAFF sang PARTNER template, ứng dụng có thể truy cập một entry khác cùng tên ở directory đối tác. Do đó, dịch vụ phải **quy định nguồn và DN cùng nhau**.

### 4.2. Không hardcode bind password, không tắt kiểm tra TLS

Không cấu hình:

```java
source.setPassword("admin123"); // KHÔNG NÊN
```

Không dùng trust-all SSL socket factory hoặc hostname verifier luôn trả true. Kết nối directory có thể chứa username, DN, group membership và thông tin nhạy cảm; nếu server giả mạo được chấp nhận, cả credential service account lẫn dữ liệu có thể bị lộ.

## 5. Tạo hai LdapTemplate với @Qualifier

`LdapTemplate` bọc JNDI và chịu trách nhiệm truy vấn, mapping kết quả, đóng `DirContext`, dịch ngoại lệ. Một template gắn với một `ContextSource` cụ thể. Đặt tên bean rõ ràng:

```java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ldap.core.ContextSource;
import org.springframework.ldap.core.LdapTemplate;

@Configuration(proxyBeanMethods = false)
public class MultiDirectoryTemplateConfiguration {

    @Bean("staffLdapTemplate")
    public LdapTemplate staffLdapTemplate(
            @Qualifier("staffContextSource") ContextSource source) {

        LdapTemplate template = new LdapTemplate(source);
        template.setDefaultTimeLimit(3_000);
        template.setDefaultCountLimit(200);
        template.setIgnoreSizeLimitExceededException(false);
        return template;
    }

    @Bean("partnerLdapTemplate")
    public LdapTemplate partnerLdapTemplate(
            @Qualifier("partnerContextSource") ContextSource source) {

        LdapTemplate template = new LdapTemplate(source);
        template.setDefaultTimeLimit(5_000);
        template.setDefaultCountLimit(100);
        template.setIgnoreSizeLimitExceededException(false);
        return template;
    }
}
```

Khi inject nhiều bean cùng kiểu, **bắt buộc chỉ rõ bean muốn dùng** nếu không có một lựa chọn duy nhất:

```java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.stereotype.Service;

@Service
public class StaffDirectoryService {
    private final LdapTemplate staffLdap;

    public StaffDirectoryService(
            @Qualifier("staffLdapTemplate") LdapTemplate staffLdap) {
        this.staffLdap = staffLdap;
    }
}
```

**Đừng dùng `@Primary` chỉ để làm lỗi `NoUniqueBeanDefinitionException` biến mất**, vì code inject không chỉ định nguồn có thể âm thầm truy vấn thư mục “primary” dù nghiệp vụ cần PARTNER. `@Primary` có thể hữu ích cho một default được tài liệu hóa, nhưng với tác vụ liên quan danh tính và quyền, **`@Qualifier` rõ ràng thường an toàn hơn**.

### 5.1. Giới hạn của LdapTemplate

Hai bean ở trên có:

| Thiết lập | STAFF | PARTNER | Ý nghĩa |
| --- | ---: | ---: | --- |
| `setDefaultTimeLimit` | 3.000 ms | 5.000 ms | Giới hạn thời gian search theo Spring/JNDI |
| `setDefaultCountLimit` | 200 | 100 | Giới hạn số entry trả về |
| `setIgnoreSizeLimitExceededException` | `false` | `false` | Cố gắng phát hiện size-limit error thay vì mặc định bỏ qua |

Những giới hạn này là **giá trị minh họa**, không phải khuyến nghị cố định cho production. Cần phân biệt **search time limit** với `java.naming.ldap.read.timeout` và `java.naming.ldap.connect.timeout`.

Theo Javadoc `LdapTemplate`, mặc định `ignoreSizeLimitExceededException=true`. Nếu truy vấn cần **tập kết quả đầy đủ** (đồng bộ người dùng, tính membership đầy đủ), bỏ qua exception có thể làm service hiểu nhầm dữ liệu cắt cụt là hoàn chỉnh. Đặt `false` giúp phát hiện nhiều trường hợp nhưng **không bảo đảm mọi server đều báo lỗi khi chạm đúng số lượng giới hạn**; cần phân trang/kiểm tra hợp đồng dữ liệu.

### 5.2. Không thay đổi template singleton theo từng request

Không nên:

```java
// RỦI RO: thay cấu hình bean chia sẻ cho mọi thread/request.
staffLdap.setDefaultTimeLimit(request.getTimeoutMs());
```

Các `LdapTemplate` được khai báo làm bean singleton. Với timeout/limit tùy use case, dùng `LdapQueryBuilder.query().countLimit(...).timeLimit(...)` ở **từng truy vấn**, hoặc tách template chính sách khác nhau nếu hợp lý.

## 6. Dùng hai LdapTemplate trong application service

Ứng dụng có thể truy vấn STAFF và PARTNER nhưng phải chọn rõ nguồn:

```java
import java.util.List;
import javax.naming.NamingException;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;
import org.springframework.stereotype.Service;

@Service
public class DirectoryLookupService {
    private final LdapTemplate staffLdap;
    private final LdapTemplate partnerLdap;

    public DirectoryLookupService(
            @Qualifier("staffLdapTemplate") LdapTemplate staffLdap,
            @Qualifier("partnerLdapTemplate") LdapTemplate partnerLdap) {
        this.staffLdap = staffLdap;
        this.partnerLdap = partnerLdap;
    }

    public List<String> findStaffNamesByUid(String uid) {
        LdapQuery query = LdapQueryBuilder.query()
                .base("ou=people")
                .attributes("cn")
                .where("objectClass").is("inetOrgPerson")
                .and("uid").is(uid);
        return staffLdap.search(query, nameMapper());
    }

    public List<String> findPartnerNamesByUid(String uid) {
        LdapQuery query = LdapQueryBuilder.query()
                .base("ou=contacts")
                .attributes("cn")
                .where("objectClass").is("inetOrgPerson")
                .and("uid").is(uid);
        return partnerLdap.search(query, nameMapper());
    }

    private static AttributesMapper<String> nameMapper() {
        return attrs -> {
            Attribute cn = attrs.get("cn");
            return cn == null || cn.size() == 0
                    ? null
                    : (String) cn.get();
        };
    }
}
```

**Trong hai hàm, nguồn LDAP khác nhau là quyết định tường minh của service**; không dùng URL do client truyền để tạo context động hay suy ra nguồn từ việc một truy vấn ở nguồn đầu không có kết quả.

Giá trị `uid` từ client được đưa vào `.where("uid").is(uid)`, tránh việc ghép filter bằng chuỗi. DN và LDAP filter có **quy tắc escape khác nhau**; khi cần tạo DN từ input, dùng `LdapNameBuilder.add(type, value)`.

### 6.1. Khi cần tổng hợp hai nguồn

Giả sử API nghiệp vụ muốn hiển thị cả nhân viên và đối tác. Có thể gọi hai phương thức rồi tạo các DTO mang **source identifier**:

```text
DirectoryPerson {
  source: STAFF | PARTNER
  fullDn: (DN từ directory tương ứng)
  displayName: ...
}
```

Không chỉ gộp kết quả bằng `uid`: `uid=lan` trên STAFF và `uid=lan` trên PARTNER **không bắt buộc là cùng người**. Khi hợp nhất danh tính, phải có **quy tắc liên kết định danh** được phê duyệt, không tự ghép theo tên/email có thể thay đổi.

## 7. Gắn từng nhóm Spring Data LDAP repository với đúng template

Điểm then chốt của cấu hình nhiều nguồn là **`ldapTemplateRef`** trong annotation `@EnableLdapRepositories`. Mặc định, Spring Data LDAP tìm bean tên **`ldapTemplate`**; nếu template của bạn có tên khác, cần chỉ định tên thật.

### 7.1. Tách package repository

Cấu trúc **minh họa** (chỉ là hướng dẫn tổ chức mã nguồn, không phải các file được tạo trong tác vụ này):

```text
com.acme.directory
├── config
│   ├── MultiDirectoryContextConfiguration.java
│   ├── MultiDirectoryTemplateConfiguration.java
│   ├── StaffRepositoryConfiguration.java
│   └── PartnerRepositoryConfiguration.java
├── staff
│   ├── model
│   │   └── StaffPerson.java
│   └── repository
│       └── StaffPersonRepository.java
└── partner
    ├── model
    │   └── PartnerContact.java
    └── repository
        └── PartnerContactRepository.java
```

Như vậy, hai lần quét repository **không chồng package** và không đăng ký trùng cùng một interface.

### 7.2. Java Config cho STAFF repository

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.ldap.repository.config.EnableLdapRepositories;

@Configuration(proxyBeanMethods = false)
@EnableLdapRepositories(
        basePackages = "com.acme.directory.staff.repository",
        ldapTemplateRef = "staffLdapTemplate")
public class StaffRepositoryConfiguration {
}
```

### 7.3. Java Config cho PARTNER repository

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.ldap.repository.config.EnableLdapRepositories;

@Configuration(proxyBeanMethods = false)
@EnableLdapRepositories(
        basePackages = "com.acme.directory.partner.repository",
        ldapTemplateRef = "partnerLdapTemplate")
public class PartnerRepositoryConfiguration {
}
```

Trong cách này:

- `StaffPersonRepository` được phát hiện trong package STAFF và liên kết với `staffLdapTemplate`.
- `PartnerContactRepository` được phát hiện trong package PARTNER và liên kết với `partnerLdapTemplate`.
- Hai template được tạo từ hai `ContextSource` đã chỉ định.
- Bean `ldapTemplate` mặc định **không phải tên bắt buộc** nếu các cấu hình repo đã đặt `ldapTemplateRef` đúng.
- Nếu bỏ `ldapTemplateRef`, các repository đó có thể cố tìm bean tên `ldapTemplate` hoặc báo lỗi startup, tùy context.

`@EnableLdapRepositories` không phải một annotation trên entity hoặc method: nó **bật quét các interface repository trong package** được cấu hình. Đừng dùng `basePackages="com.acme.directory"` ở cả hai config: package chồng lấp có thể tạo bean trùng hoặc gắn sai template.

### 7.4. Entity và repository dùng ODM của Spring LDAP

Entity STAFF:

```java
package com.acme.directory.staff.model;

import javax.naming.Name;
import org.springframework.ldap.odm.annotations.Attribute;
import org.springframework.ldap.odm.annotations.Entry;
import org.springframework.ldap.odm.annotations.Id;

@Entry(
        base = "ou=people",
        objectClasses = {
            "top", "person", "organizationalPerson", "inetOrgPerson"
        })
public class StaffPerson {
    @Id
    private Name dn;

    @Attribute(name = "uid")
    private String uid;

    @Attribute(name = "cn")
    private String fullName;

    @Attribute(name = "sn")
    private String surname;

    public StaffPerson() {}
    // Getter và setter còn lại theo quy ước project.
}
```

Repository STAFF:

```java
package com.acme.directory.staff.repository;

import com.acme.directory.staff.model.StaffPerson;
import java.util.List;
import org.springframework.data.ldap.repository.LdapRepository;

public interface StaffPersonRepository
        extends LdapRepository<StaffPerson> {
    List<StaffPerson> findByUid(String uid);
}
```

Một entity PARTNER tương tự nhưng với `@Entry(base = "ou=contacts", ...)` và repository trong package PARTNER. Các entity thực tế phải phù hợp **schema** của từng server: AD/389 DS/OpenLDAP có thể không chia sẻ cùng objectClass/attribute.

**`@Id Name dn` là DN của entry**, không phải UUID hoặc số tự tăng. Nhiều directory có thể chứa cùng RDN dưới những base khác nhau. Cần bảo đảm DN do ODM tính ra và `@Entry.base` nhất quán với `ContextSource.base` của **nguồn tương ứng**.

### 7.5. Điều cần biết về repository

Spring Data LDAP repository:

- Dùng ODM annotations của Spring LDAP (`@Entry`, `@Id`, `@Attribute`, `@DnAttribute`), không thay bằng annotation ID của JPA.
- Có các thao tác CRUD và derived queries dựa trên attribute.
- Không tạo schema, OU, user hoặc index của LDAP server từ entity Java.
- Theo tài liệu hiện hành, **không hỗ trợ paging/sorting theo API repository** như một số loại database khác; để nhận nhiều kết quả LDAP theo trang, dùng `LdapTemplate` và controls phù hợp với server.

Nếu một directory cần kiểm soát filter, projection attribute, server control hoặc phân trang đặc thù, việc dùng `LdapTemplate` thủ công **không mâu thuẫn** với sử dụng repository ở những use case đơn giản.

## 8. Cấu hình tùy chọn riêng cho từng nguồn

Với hai `LdapContextSource` và `LdapTemplate` riêng, mỗi nguồn có thể sử dụng một chính sách khác nhau. Tuy nhiên, những tùy chọn đó tác động lên **hành vi LDAP**, không thay đổi yêu cầu bảo mật hoặc ngữ nghĩa của server.

| Tùy chọn | Cấp cấu hình | Dùng để làm gì |
| --- | --- | --- |
| URL / URLs | `ContextSource` | Chọn endpoint hoặc replica cùng nguồn logic |
| `setBase(...)` | `ContextSource` | Gốc DN cho các thao tác tương đối |
| `setUserDn/setPassword` | `ContextSource` | Principal service account |
| `setReferral(...)` | `ContextSource` | Policy xử lý referral |
| `setAuthenticationStrategy(...)` | `ContextSource` | Bind mechanism/StartTLS theo nhu cầu |
| `setBaseEnvironmentProperties(...)` | `ContextSource` | JNDI properties: timeout, binary attributes, factory... |
| `setDefaultCountLimit(...)` | `LdapTemplate` | Giới hạn entry mặc định |
| `setDefaultTimeLimit(...)` | `LdapTemplate` | Giới hạn thời gian search (ms) |
| `setDefaultSearchScope(...)` | `LdapTemplate` | OBJECT/ONELEVEL/SUBTREE mặc định |
| `setIgnoreSizeLimitExceededException(...)` | `LdapTemplate` | Chính sách xử lý size-limit exception |
| `setIgnorePartialResultException(...)` | `LdapTemplate` | Chính sách với `PartialResultException` liên quan referral, không phải mọi lỗi |
| `ldapTemplateRef` | `@EnableLdapRepositories` | Chọn template chính xác cho package repositories |

### 8.1. JNDI connect/read timeout

Trong ví dụ bean:

```java
source.setBaseEnvironmentProperties(Map.of(
        "java.naming.ldap.connect.timeout", "3000",
        "java.naming.ldap.read.timeout", "5000"));
```

Giá trị là **chuỗi biểu diễn milliseconds** đối với JNDI LDAP provider của JDK. Connect timeout liên quan mở kết nối; read timeout liên quan chờ dữ liệu trên kết nối. **Cả hai khác với search time limit của `LdapTemplate`** và deadline HTTP.

Khi thiết kế SLA, phân rã:

```text
HTTP deadline
├── pool wait / connection creation
├── LDAP bind / TLS handshake
├── LDAP search (server + network)
└── ODM / response mapping
```

Thời gian timeout không nhất thiết cộng đơn giản; nhiều operation LDAP cùng chạy trong một request và mỗi operation có thể có giới hạn riêng. Hãy đặt chính sách tổng thời gian ở tầng ứng dụng.

### 8.2. Search scope và count/time limit

```java
import javax.naming.directory.SearchControls;

LdapTemplate template = new LdapTemplate(source);
template.setDefaultSearchScope(SearchControls.ONELEVEL_SCOPE);
template.setDefaultCountLimit(100);
template.setDefaultTimeLimit(2_000);
```

Đây là **ví dụ cấu hình template riêng**, không phải lệnh cần chèn thêm vào mọi bean. Với subtree có nhiều lớp OU, `ONELEVEL` chỉ tìm entry con trực tiếp và có thể **bỏ sót** người ở OU sâu hơn; chọn scope theo cấu trúc thật.

Thời gian `2_000` là **2.000 ms** ở Spring LDAP/JNDI. LDAP protocol biểu diễn time limit theo giây, nên mức chính xác tùy provider/server. Cấu hình `0` ở template nghĩa là không đặt giới hạn mặc định **phía client**, không vượt được server administrative cap.

### 8.3. Binary attributes riêng cho một nguồn

Một số server (đặc biệt Active Directory hoặc schema tùy chỉnh) có attribute binary cần được JNDI nhận diện:

```java
source.setBaseEnvironmentProperties(Map.of(
        "java.naming.ldap.connect.timeout", "3000",
        "java.naming.ldap.read.timeout", "5000",
        "java.naming.ldap.attributes.binary", "objectGUID customBlob"));
```

Ví dụ này chỉ phù hợp nếu **schema của nguồn đó thực sự có `objectGUID` hoặc `customBlob` dạng binary**. Không thêm các tên này vào mọi directory một cách máy móc. Lúc đọc, kiểm tra `byte[]`; không chuyển nhị phân sang `String` tùy ý. Với entity ODM, `@Attribute(type = Attribute.Type.BINARY)` còn chỉ định kiểu mapping ở tầng ODM, là vấn đề **khác với** JNDI provider.

## 9. LDAPS, StartTLS và referral policy

### 9.1. LDAPS cho từng nguồn

Ví dụ bài học sử dụng:

```text
ldaps://staff-ldap.example.org:636
ldaps://partner-ldap.example.org:636
```

Mỗi hostname phải có chứng chỉ hợp lệ, được JVM/client tin cậy và xác minh đúng tên. Khi mỗi directory dùng CA khác nhau, cần thiết kế truststore/SSLContext hoặc factory thích hợp theo khả năng của JNDI/provider. Không sử dụng “trust all certificates”, không tắt hostname verification. Secret bind nên được quản lý tách rời source code.

### 9.2. StartTLS là một lựa chọn khác

Nếu server yêu cầu StartTLS thay vì LDAPS, Spring LDAP có cơ chế `DirContextAuthenticationStrategy`. Ví dụ:

```java
import org.springframework.ldap.core.support.DefaultTlsDirContextAuthenticationStrategy;
import org.springframework.ldap.core.support.LdapContextSource;

LdapContextSource source = new LdapContextSource();
source.setUrl("ldap://directory.example.org:389");
source.setBase("dc=example,dc=org");
source.setUserDn("uid=reader,ou=services,dc=example,dc=org");
source.setPassword(passwordFromSecretStore);
source.setAuthenticationStrategy(
        new DefaultTlsDirContextAuthenticationStrategy());
```

Ví dụ có ý định **nâng cấp kết nối sang TLS trước khi simple bind** theo chiến lược của Spring LDAP. Nó chưa bao gồm cấu hình truststore/secret thực tế, và không tự bảo đảm tương thích với mọi server. Cần verify certificate/hostname theo chính sách và thử với sản phẩm LDAP cụ thể.

Đừng bật native JNDI pooling `setPooled(true)` tùy tiện khi dùng TLS; tài liệu Spring LDAP cảnh báo native pooling **không hoạt động đúng với cấu hình TLS** và thiếu cơ chế validation phong phú. Nếu thật sự cần pool, nghiên cứu Spring LDAP `PoolingContextSource` và cấu hình phù hợp.

### 9.3. Referral không phải automatic cross-directory routing

`setReferral("ignore")`, `"follow"` hoặc `"throw"` quyết định cách JNDI xử lý referral tùy khả năng của provider. Với `follow`, client có thể được yêu cầu tiếp tục truy vấn tới **đích khác**. Điều này ảnh hưởng:

- Quyền truy cập và credential có được/được phép sử dụng tại đích hay không.
- Phạm vi dữ liệu mà người dùng nghiệp vụ được phép đọc.
- Số hop và vòng referral.
- Timeout, TLS, truststore và thông tin ghi log ở server khác.

**Không dùng referral làm cách thay thế cho việc chọn STAFF/PARTNER rõ ràng trong service**. Với nhiều directory độc lập, hãy xác định tuyến truy vấn trong ứng dụng và áp dụng authorization phù hợp.

## 10. Connection pool: tách theo nguồn và principal

Tạo hai `ContextSource` cũng giúp mỗi nguồn có pool policy riêng. Nhưng cần phân biệt:

| Loại | Đặc điểm | Cảnh báo |
| --- | --- | --- |
| Native JNDI pooling qua `setPooled(true)` | Cấu hình pool ở cấp JVM và provider | Hạn chế validation, không phù hợp một số cấu hình TLS |
| Spring LDAP `PoolingContextSource` | Bọc một context source bằng pool quản lý riêng | Cần chọn pool sizing, validation và đóng context đúng |
| Không pooling | Mỗi operation có thể tạo context/kết nối mới | Đơn giản, có thể đủ cho traffic thấp |

Nếu sử dụng `PoolingContextSource`:

```text
staffLdapTemplate
    └── staffPoolingContextSource
         └── staffLdapContextSource

partnerLdapTemplate
    └── partnerPoolingContextSource
         └── partnerLdapContextSource
```

**Không dùng chung một pool giữa hai directory** có bind credential, URL hoặc base khác nhau. Một pool dành cho service account cố định **khác** với pool các context xác thực riêng từng người dùng.

Spring LDAP cảnh báo rằng `PoolingContextSource` giả định các context read-only/read-write trong pool có **môi trường xác thực ổn định**. Nếu bọc một `ContextSource` dùng `AuthenticationSource` thay principal theo request, context đã mượn có thể được tái sử dụng với credential của request khác. Đây là **rủi ro bảo mật**. Các luồng LDAP bind của Spring Security nên dùng cấu hình xác thực riêng và không tùy tiện ghép vào pool dùng chung.

## 11. Hai nguồn không tạo một transaction LDAP chung

Một service có thể làm:

```text
1. Add person vào STAFF
2. Add linked contact vào PARTNER
3. Trả kết quả HTTP
```

Nếu bước 1 thành công nhưng bước 2 lỗi, **hai directory không có transaction phân tán mặc định** chỉ vì code nằm trong một method Java có `@Transactional`. Spring Data LDAP cũng không tự tạo XA transaction chung cho nhiều LDAP server.

Giải pháp cần xét nghiệp vụ:

- **Chỉ đọc:** xác định partial failures, có cho phép trả dữ liệu từ một nguồn không, có ghi rõ nguồn hay không.
- **Ghi hai nguồn:** dùng workflow có idempotency, retry có kiểm soát, đối soát và compensation nếu cần.
- **Đồng bộ danh tính:** xác định source of truth, mapping identity, độ trễ replication và trường hợp dữ liệu lệch.
- **Đổi DN:** không giả định Modify DN của STAFF tự cập nhật group/manager reference ở PARTNER.
- **Audit:** ghi sự kiện rõ nguồn và trạng thái; không chứa credential hoặc dữ liệu người dùng không được phép.

Chỉ thực hiện cross-directory write nếu service có **quyền phù hợp tại từng nguồn** và luồng nghiệp vụ thực sự yêu cầu.

## 12. Quan sát và log cho cấu hình nhiều directory

Khi có lỗi, thông báo “LDAP connection failed” là quá mơ hồ. Cần biết **nguồn logic** nào gặp vấn đề mà không để lộ bí mật.

Ví dụ log ở mức service:

```text
traceId=... directory=staff operation=search result=success latencyMs=25
traceId=... directory=partner operation=search result=timeout latencyMs=5012
```

Nên dùng các tag có tập giá trị hữu hạn:

- `directory=staff/partner` (logical name, không phải full URL nếu URL nhạy cảm).
- `operation=search/lookup/modify`.
- `result=success/timeout/access-denied/not-found/error`.
- `branch=people/contacts` nếu đã được allowlist.
- `durationMs` hoặc histogram latency phù hợp.

**Không** đưa bind DN/password, LDAP filter chứa PII, danh sách group membership hoặc full DN vào metric tags. Với Micrometer Observation/Spring LDAP phiên bản hỗ trợ, có thể instrument từng `ContextSource` và cần xác minh không bọc hai lần. Một trace ID liên kết HTTP request với LDAP client operation nhưng không tự truyền vào LDAP server qua giao thức RFC 4511.

## 13. Lỗi thường gặp trong cấu hình nhiều nguồn

| Hiện tượng | Nguyên nhân khả dĩ | Cách xử lý |
| --- | --- | --- |
| `NoUniqueBeanDefinitionException` khi inject `LdapTemplate` | Có nhiều bean cùng kiểu, không dùng qualifier | Dùng `@Qualifier("staffLdapTemplate")` hoặc bean name rõ |
| Repository cố tìm bean `ldapTemplate` | Bỏ `ldapTemplateRef` | Đặt đúng ref trong `@EnableLdapRepositories` |
| Repository bị đăng ký trùng | Hai cấu hình scan cùng package hoặc Boot auto-scan thêm | Tách package, xem `spring.data.ldap.repositories.enabled` |
| Repository STAFF đọc sang PARTNER | Nhầm `ldapTemplateRef` hoặc dùng service sai template | Integration test truy vấn cross-source, rà soát wiring |
| `NameNotFoundException` dù entry có thật | Base DN sai hoặc truyền full DN vào nơi yêu cầu relative DN | Kiểm tra `ContextSource.base`, `@Entry.base` và DN |
| LDAP bind thất bại | Bind DN/password nhầm nguồn, account khóa hoặc ACL | Kiểm tra credential theo nguồn, không log password |
| Kết nối LDAPS lỗi TLS | Cert, hostname, truststore hoặc server config sai | Sửa trust chain/hostname validation; không trust-all |
| Search chậm ở nguồn PARTNER | Index/filter khác STAFF; scope quá rộng | Đo và tối ưu riêng directory PARTNER |
| Đổi một timeout làm cả hai nguồn thay đổi | Dùng template chung hoặc mutable singleton | Mỗi nguồn có template riêng; limit theo query |
| Kết quả bị cắt mà service không biết | Size limit và mặc định ignore exception | Xem chính sách completeness/paging |
| `PartialResultException` khi theo referral | Policy referral không phù hợp directory | Xem referral handling, ACL/TLS và mục đích |
| Pool chứa credential không đúng | Pool bọc AuthenticationSource động | Không pool context xác thực nhiều người kiểu đó |
| Dữ liệu đồng bộ một nửa | Hai LDAP server không có transaction chung | Thiết kế idempotency/reconciliation |
| Service chạy tốt ở dev nhưng fail ở prod | CA, DNS, secret, firewall, schema và ACL khác | Test riêng từng môi trường và server |
| Có hai URL trong `setUrls` nhưng trả kết quả kỳ lạ | URL thuộc hai directory không cùng dữ liệu logic | Tách thành hai `ContextSource` |

## 14. Kiểm thử cấu hình để tránh nhầm nguồn

Nên dùng **hai LDAP server thử nghiệm độc lập**, có schema và naming context phù hợp. Không dùng hai OU trên **một** server rồi kết luận đã kiểm thử xong vấn đề nhiều server/credential.

### 14.1. Dữ liệu test đề xuất

```text
STAFF test directory
dc=corp,dc=example
└── ou=people
    ├── uid=lan
    └── uid=shared

PARTNER test directory
dc=partners,dc=example
└── ou=contacts
    ├── uid=supplier01
    └── uid=shared
```

Entry `uid=shared` xuất hiện ở **cả hai nguồn** nhưng có `cn` khác nhau. Điều này giúp phát hiện cấu hình nào vô tình trỏ sang nhầm directory.

### 14.2. Test cơ bản theo từng template

1. Dùng `staffLdapTemplate` tìm `uid=lan` dưới `ou=people` → trả về đúng STAFF.
2. Dùng `partnerLdapTemplate` tìm `uid=supplier01` dưới `ou=contacts` → trả về đúng PARTNER.
3. Tìm `uid=shared` ở hai nguồn → kết quả khác nhau theo dữ liệu test, xác minh không chung context.
4. Tìm `uid=lan` trong PARTNER nếu không có entry đó → không tự động fallback sang STAFF.
5. Kiểm tra DN trả về có suffix tương ứng, không tự động nối lại base hai lần.
6. Dùng service account STAFF để truy vấn PARTNER trực tiếp → chỉ chạy nếu policy/credential thật sự cho phép; không coi quyền được chia sẻ mặc định.
7. Thử bind password sai, server không sẵn sàng, TLS cert không hợp lệ, time limit và size limit cho từng nguồn.
8. Kiểm tra log chỉ có `directory=staff/partner` và mã lỗi, không tiết lộ password/PII.

### 14.3. Test wiring repository

Với repository đã cấu hình:

```java
import java.util.List;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class MultiDirectoryRepositoryTest {

    @Autowired
    StaffPersonRepository staffRepository;

    @Autowired
    PartnerContactRepository partnerRepository;

    // Trong test thật, seed hai LDAP directory độc lập.
    // Assert: staffRepository chỉ thấy STAFF;
    //         partnerRepository chỉ thấy PARTNER;
    //         uid=shared trả hai entity khác nhau theo nguồn.
}
```

Đoạn code này là **khung kiểm thử**, không phải test hoàn chỉnh: cần khai báo class repository, mô hình entity, server test, dữ liệu seed và assertion. Không dùng test mock hoàn toàn để chứng minh wiring LDAP đã đúng. Để xác minh thực sự, nên có integration test khởi tạo hai LDAP server độc lập (ví dụ Testcontainers hoặc LDAP embedded phù hợp), nhận seed data và đóng server sau test.

### 14.4. Test negative cho thao tác ghi

Với account thử nghiệm có quyền ghi hạn chế:

- Ghi một entry vào STAFF rồi xác minh PARTNER **không đổi**.
- Cố ghi STAFF data qua PARTNER template → phải được policy/schema/base/ACL chặn hoặc test phát hiện sai nguồn ngay lập tức.
- Thay đổi `uid=shared` ở STAFF và xác minh entry PARTNER cùng UID không bị ảnh hưởng.
- Cho PARTNER LDAP server dừng giữa workflow hai nguồn; xác minh service không kết luận giao dịch đã thành công toàn bộ.
- Test luồng rename/move và cập nhật tham chiếu DN; không giả định hai directory tự đồng bộ.

**Tránh seed hoặc xóa dữ liệu thật trên production khi chạy test.** Sử dụng naming context riêng, thông tin giả và principal có quyền tối thiểu.

## 15. Bài thực hành từng bước

### Bài 1. Tách hai nguồn kết nối

Từ một ứng dụng đang có `spring.ldap.*`, hãy tạo bốn bean:

```text
staffContextSource   -> staffLdapTemplate
partnerContextSource -> partnerLdapTemplate
```

**Câu hỏi:** vì sao cần hai `ContextSource` chứ không chỉ hai `LdapTemplate` cùng dùng một context?

*Gợi ý:* Vì URL, base DN, bind credential và policy khác nhau ở chính **nguồn cấp context**. Hai template cùng một context vẫn trỏ tới cùng directory logic.

### Bài 2. Cố định repository theo nguồn

Tạo hai package repository, dùng:

```java
@EnableLdapRepositories(
    basePackages = "com.acme.directory.staff.repository",
    ldapTemplateRef = "staffLdapTemplate")
```

và config tương tự cho PARTNER. **Câu hỏi:** điều gì xảy ra khi bỏ `ldapTemplateRef`?

*Gợi ý:* Spring Data LDAP sẽ tìm template theo tên mặc định `ldapTemplate`. Với nhiều bean, điều đó có thể thất bại hoặc không phản ánh nguồn dự định.

### Bài 3. Điều chỉnh chính sách search

STAFF cần search `uid` chính xác, PARTNER cần tìm `cn` theo tiền tố. Hãy:

- Đặt search base tương đối đúng từng nguồn.
- Dùng `LdapQueryBuilder` để escape input.
- Đặt `countLimit`/`timeLimit` theo use case.
- Ghi rõ kết quả có được coi là đầy đủ không.

**Gợi ý:** cả hai đều dùng `LdapTemplate.search`, nhưng filter, index và độ chọn lọc của mỗi directory có thể khác nhau.

### Bài 4. Kiểm tra nhầm DN

`uid=shared,ou=people,dc=corp,dc=example` và `uid=shared,ou=contacts,dc=partners,dc=example` có phải cùng entry không?

*Đáp án:* Không. Chúng khác naming context và nằm ở hai directory độc lập. Không thể kết luận là cùng danh tính chỉ vì cùng UID.

### Bài 5. Chẩn đoán TLS và timeout

Một nguồn thường trả về sau 50 ms, nguồn còn lại timeout sau 5 giây. Những thông tin nào cần xem?

*Gợi ý:* Xem URL/hostname/TLS, principal, JNDI read timeout, search time limit, filter/index, network latency, server health, pool wait và mức tải. Không sửa timeout của cả hai nguồn nếu chỉ một nguồn gặp lỗi.

### Bài 6. Thử sai wiring

Đổi thử `ldapTemplateRef` của PARTNER sang `staffLdapTemplate` trong **test configuration**, chạy integration test và quan sát assertion của `uid=shared`.

*Mục tiêu:* Test phải phát hiện được repository PARTNER đang trỏ sang STAFF; đừng kiểm thử chỉ bằng một user có dữ liệu giống nhau ở hai nguồn.

### Bài 7. Giới hạn pool

Nếu sử dụng service account cố định để đọc STAFF nhưng authentication dùng bind DN động của từng nhân viên, có nên cho cả hai đi qua cùng `PoolingContextSource` không?

*Đáp án:* Không nên. Cần tách đường xác thực và pool theo chính sách của Spring LDAP; `PoolingContextSource` không được giả định xử lý principal thay đổi trên mỗi request một cách an toàn.

### Bài 8. Kết hợp dữ liệu hai nguồn

API cần trả danh sách chung nhưng PARTNER tạm không sẵn sàng. Nên làm gì?

*Gợi ý:* Hợp đồng API phải xác định liệu **partial response** có được phép hay không. Nếu không, trả lỗi phù hợp. Nếu có, ghi rõ nguồn nào thất bại và không dùng danh sách thiếu cho nghiệp vụ phân quyền hoặc kiểm soát tuân thủ.

## 16. Ghi nhớ

- Một nguồn LDAP logic có thể dùng Spring Boot auto-configuration; **hai directory độc lập cần cấu hình tường minh**.
- Tạo **mỗi nguồn một `LdapContextSource`**, gắn **mỗi nguồn một `LdapTemplate`**, sử dụng `@Qualifier` để tránh inject nhầm.
- Với Spring Data LDAP repositories, tách package và dùng **`@EnableLdapRepositories(basePackages = "...", ldapTemplateRef = "...")`**. Tên `ldapTemplate` mặc định không đủ để tự chọn nguồn.
- **`spring.data.ldap.repositories.enabled=false`** có thể dùng để tắt repository auto-scan của Spring Boot khi bạn chủ động khai báo config repository riêng; kiểm tra phiên bản framework.
- `ContextSource.setBase(...)` xác định root DN; các thao tác Spring LDAP thường dùng **DN tương đối** với base đó, tránh ghép suffix hai lần.
- URL list cho **replica của cùng directory** không phải router cho nhiều directory có schema hoặc credential khác nhau.
- Kết nối phải có **LDAPS/StartTLS, trust validation, credentials riêng, ACL tối thiểu và timeout hợp lý**. Connection pool không nên dùng chung với principal động nếu cơ chế không hỗ trợ an toàn.
- Search limit, server cap và paging là các cơ chế riêng; đừng dùng dữ liệu bị cắt cho nghiệp vụ đòi kết quả hoàn chỉnh.
- Hai directory **không tự có transaction chung, không tự đồng bộ DN hay danh tính**. Hãy thiết kế reconciliation, logging theo source và kiểm thử negative cross-source.

**Tài liệu tham khảo chính thức:**

- [Spring Boot — LDAP configuration](https://docs.spring.io/spring-boot/reference/data/nosql.html): starter, `spring.ldap.*` và auto-configuration.
- [Spring Data LDAP — Configuration](https://docs.spring.io/spring-data/ldap/reference/ldap/configuration.html): `@EnableLdapRepositories` và template association.
- [Spring Data LDAP API — EnableLdapRepositories](https://docs.spring.io/spring-data/ldap/docs/current/api/org/springframework/data/ldap/repository/config/EnableLdapRepositories.html): `basePackages` và `ldapTemplateRef`.
- [Spring LDAP — Configuration](https://docs.spring.io/spring-ldap/reference/configuration.html): ContextSource, LdapTemplate, authentication và custom JNDI env.
- [Spring LDAP API — AbstractContextSource](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/core/support/AbstractContextSource.html): `setBase`, `setUrls`, `setBaseEnvironmentProperties`, `setReferral` và pooling flag.
- [Spring LDAP API — LdapTemplate](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/core/LdapTemplate.html): query defaults, count/time limits và ignore exceptions.
- [Spring LDAP — Pooling Support](https://docs.spring.io/spring-ldap/reference/pooling.html): `PoolingContextSource`, validation và hạn chế với authentication động.
- [Spring LDAP API — DefaultTlsDirContextAuthenticationStrategy](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/core/support/DefaultTlsDirContextAuthenticationStrategy.html): StartTLS trước simple bind.
- [Spring LDAP — Object-Directory Mapping](https://docs.spring.io/spring-ldap/reference/odm.html): `@Entry`, `@Id`, `@Attribute`.
- [Spring Data LDAP — Repository support](https://docs.spring.io/spring-data/ldap/reference/ldap/repositories.html): giới hạn và khả năng repositories.
- [RFC 4511 — LDAP: The Protocol](https://www.rfc-editor.org/rfc/rfc4511): LDAP operations và kết quả.
- [RFC 4514 — Distinguished Names](https://www.rfc-editor.org/rfc/rfc4514), [RFC 4515 — Search Filters](https://www.rfc-editor.org/rfc/rfc4515): cú pháp DN/filter và escaping.
