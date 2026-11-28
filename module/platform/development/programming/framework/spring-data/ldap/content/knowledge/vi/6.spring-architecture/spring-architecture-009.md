# Ranh giới trách nhiệm giữa lớp cấu hình, Repository và dịch vụ

> **Chương:** Kiến trúc Spring  
> **Module:** SPRING_DATA_LDAP — truy cập dịch vụ thư mục LDAP qua Spring Data LDAP, ánh xạ entry phân cấp sang đối tượng Java, hiểu DN, objectClass, schema, truy vấn repository/LdapTemplate, CRUD, filter an toàn, bảo mật kết nối và kiểm thử với directory.

Một ứng dụng Spring Data LDAP thường có ba nhóm thành phần dễ bị trộn lẫn: **lớp cấu hình**, **Repository** và **dịch vụ ứng dụng**. Khi cả ba cùng biết URL LDAP, tự ghép DN, viết filter, kiểm tra nghiệp vụ và gọi CRUD, code nhanh chóng khó kiểm thử, khó thay đổi và dễ tạo lỗi bảo mật.

Một kiến trúc rõ ràng phân công như sau:

- **Configuration** tạo và kết nối các thành phần hạ tầng: `ContextSource`, `LdapTemplate`, repository scanning, TLS, pool và các bean liên quan.
- **Repository** biểu diễn cách lưu/đọc entity LDAP: mapping `@Entry`, ID là DN, finder method và các thao tác persistence đặc thù.
- **Service** thực hiện use case: xác thực đầu vào nghiệp vụ, điều phối các thao tác, áp dụng quy tắc nghiệp vụ, kiểm soát kết quả và trả dữ liệu phù hợp cho lớp gọi.

Ranh giới này giúp thay đổi endpoint, base DN, cách query hoặc cách lưu entry mà không phải sửa logic nghiệp vụ ở nhiều nơi.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

1. Giải thích vai trò và phạm vi của Configuration, Repository và Service trong ứng dụng Spring Data LDAP.
2. Mô tả luồng dependency từ service tới repository và từ repository tới hạ tầng LDAP.
3. Cấu hình `LdapContextSource`, `LdapTemplate` và `@EnableLdapRepositories` tại một composition root.
4. Ánh xạ LDAP entry thành Java entity bằng `@Entry`, `@Id` và `@Attribute`.
5. Thiết kế repository cho finder method và custom persistence operation.
6. Đặt validation, authorization, orchestration và xử lý kết quả ở service.
7. Nhận biết các anti-pattern như ghép DN trong controller, gọi LDAP trực tiếp từ service và đưa business rule vào repository.
8. Phân biệt lỗi hạ tầng LDAP với lỗi nghiệp vụ và ánh xạ lỗi ở đúng tầng.
9. Kiểm thử từng tầng độc lập và kiểm thử tích hợp với directory thực.

## 2. Kiến trúc tổng thể

Một luồng điển hình:

~~~mermaid
flowchart TD
    HTTP["Controller / API"]
    SVC["Application Service"]
    REPO["Spring Data LDAP Repository"]
    FRAG["Custom Repository Operation"]
    ODM["ODM Mapping / Query Derivation"]
    TEMPLATE["LdapTemplate"]
    SOURCE["ContextSource"]
    LDAP["LDAP Directory"]

    CONFIG["Configuration"]
    CONFIG -. tạo bean .-> TEMPLATE
    CONFIG -. đăng ký .-> REPO
    CONFIG -. cấu hình .-> SOURCE

    HTTP --> SVC
    SVC --> REPO
    REPO --> ODM
    REPO --> FRAG
    FRAG --> TEMPLATE
    ODM --> SOURCE
    TEMPLATE --> SOURCE
    SOURCE --> LDAP
~~~

Trong ứng dụng thực tế, repository và `LdapTemplate` cùng dùng cấu hình kết nối phù hợp. Custom repository operation là nơi đặt thao tác LDAP chuyên biệt mà repository CRUD cơ bản không diễn đạt tốt.

| Thành phần | Câu hỏi mà nó trả lời | Trách nhiệm chính |
|---|---|---|
| Configuration | Ứng dụng kết nối directory bằng cách nào? | URL, base DN, bind credential, TLS, ContextSource, LdapTemplate, repository scanning |
| Entity/ODM | Entry LDAP được biểu diễn trong Java ra sao? | Object classes, DN, attribute mapping |
| Repository | Đọc và ghi entity bằng những thao tác nào? | Finder, CRUD, query persistence, custom LDAP operation |
| Service | Ứng dụng thực hiện use case gì? | Validation nghiệp vụ, orchestration, authorization, consistency policy, mapping kết quả |
| Controller | Giao tiếp HTTP/API ra sao? | Parse request, gọi service, định dạng response |

**Điểm cốt lõi:** Configuration lắp ráp hạ tầng; Repository đóng gói persistence; Service điều phối nghiệp vụ. Controller chỉ nên là adapter cho giao thức bên ngoài.

## 3. Dependency đi theo một hướng

Một hướng phụ thuộc dễ kiểm soát:

~~~text
Controller
    |
    v
Application Service
    |
    v
Repository interface
    |
    v
Spring Data LDAP / custom persistence implementation
    |
    v
LdapTemplate / ContextSource
    |
    v
LDAP server
~~~

Configuration nằm ở rìa ứng dụng, tạo và kết nối các bean cần thiết. Service không cần biết cách tạo JNDI context hoặc URL LDAP. Repository không cần biết một request HTTP đến từ endpoint nào.

Các quy tắc nên giữ:

- Controller gọi service thay vì tự gọi repository cho từng use case.
- Service phụ thuộc repository abstraction hoặc port persistence, không tự tạo connection.
- Repository nhận diện entry và attribute theo schema; không quyết định chính sách nghiệp vụ cấp cao.
- Configuration không chứa điều kiện kiểu “nếu user là quản trị viên thì cho phép đổi email”.
- Entity LDAP không nên trở thành API response object mặc định.
- Không để một tầng gọi ngược tầng cao hơn, ví dụ repository phụ thuộc controller hoặc service.

## 4. Cấu trúc package gợi ý

Một cách tổ chức cho module directory:

~~~text
com.example.directory
├── config
│   └── LdapConfiguration.java
├── person
│   ├── api
│   │   ├── PersonController.java
│   │   └── PersonResponse.java
│   ├── application
│   │   ├── PersonDirectoryService.java
│   │   └── RegisterPersonCommand.java
│   ├── domain
│   │   └── PersonView.java
│   └── persistence
│       ├── PersonEntry.java
│       ├── PersonRepository.java
│       └── PersonDirectoryOperationsImpl.java
└── group
    ├── application
    └── persistence
~~~

Đây là ví dụ, không phải quy tắc bắt buộc của Spring. Dự án nhỏ có thể dùng ít package hơn; điều quan trọng là không trộn lẫn trách nhiệm.

| Package | Có thể chứa | Không nên chứa |
|---|---|---|
| config | ContextSource, LdapTemplate, repository scanning, TLS properties | Quy tắc tạo tài khoản, phân quyền nghiệp vụ |
| persistence | ODM entity, repository, custom query/modify | HTTP DTO, thông báo UI, workflow |
| application/service | Use case, validation, orchestration, policy | JNDI context, nối filter bằng chuỗi, cấu hình TLS |
| api/controller | HTTP request/response, status code | LDAP ModifyItem, Base DN, bind password |
| domain | Business identity, value object, quy tắc miền | Spring bean wiring hoặc connection details |

## 5. Configuration: nơi lắp ráp hạ tầng LDAP

Configuration chịu trách nhiệm tạo bean mà Spring Data LDAP cần để làm việc với directory.

~~~java
package com.example.directory.config;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.ldap.repository.config.EnableLdapRepositories;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.core.support.LdapContextSource;

@Configuration
@EnableLdapRepositories(
        basePackages = "com.example.directory.person.persistence",
        ldapTemplateRef = "ldapTemplate")
public class LdapConfiguration {

    @Bean
    public LdapContextSource ldapContextSource(
            @Value("${app.ldap.url}") String url,
            @Value("${app.ldap.base}") String base,
            @Value("${app.ldap.bind-dn}") String bindDn,
            @Value("${app.ldap.password}") String password) {

        LdapContextSource source = new LdapContextSource();
        source.setUrl(url);
        source.setBase(base);
        source.setUserDn(bindDn);
        source.setPassword(password);
        return source;
    }

    @Bean
    public LdapTemplate ldapTemplate(
            LdapContextSource ldapContextSource) {
        return new LdapTemplate(ldapContextSource);
    }
}
~~~

Ví dụ trên dùng một directory endpoint và một bean `LdapTemplate`. `@EnableLdapRepositories` đăng ký repository trong package được chỉ định và nối chúng với template có tên đã cấu hình.

Các giá trị cấu hình mẫu:

~~~yaml
app:
  ldap:
    url: ldaps://ldap.example.org:636
    base: dc=example,dc=org
    bind-dn: uid=svc-directory,ou=services,dc=example,dc=org
    password: ${LDAP_BIND_PASSWORD}
~~~

Password nên được inject từ secret manager hoặc biến môi trường do nền tảng triển khai quản lý. Không commit credential thật vào repository mã nguồn.

### Vì sao không đặt URL trong service?

Nếu service tự tạo `LdapContextSource` hoặc `LdapTemplate`:

- Mỗi use case có thể vô tình dùng base DN khác nhau.
- Cấu hình TLS, timeout hoặc pool dễ không đồng nhất.
- Unit test phải biết chi tiết kết nối.
- Việc đổi môi trường cần sửa logic ứng dụng.
- Có nguy cơ tạo context/connection lặp lại không cần thiết.

Configuration tập trung các khác biệt môi trường và cho phép Spring quản lý lifecycle của bean.

## 6. Những gì Configuration nên và không nên làm

Configuration nên:

- Tạo `LdapContextSource` với URL, base DN và bind identity.
- Cấu hình LDAPS/StartTLS, trust material, timeout và pool theo yêu cầu vận hành.
- Tạo `LdapTemplate` dùng chung.
- Khai báo repository scan và nối đúng template.
- Tạo bean cho nhiều directory source nếu kiến trúc thực sự cần.
- Bind properties từ cấu hình môi trường và secret.

Configuration không nên:

- Kiểm tra UID đã tồn tại để quyết định có đăng ký người dùng hay không.
- Tự tạo group khi người dùng được đăng ký.
- Kiểm tra một người có đủ quyền nghiệp vụ để sửa entry.
- Chuyển đổi lỗi LDAP thành thông báo HTTP.
- Viết chuỗi filter theo từng use case.
- Chứa workflow nhiều bước như tạo user, thêm group, gửi sự kiện.

Có thể dùng một class `@ConfigurationProperties` để nhóm các thuộc tính LDAP khi cấu hình phức tạp. Điều này giúp kiểm tra cấu hình đầu vào, nhưng không biến class properties thành nơi chứa business rules.

## 7. Repository: ranh giới persistence

Repository biểu diễn thao tác lưu trữ theo ngôn ngữ của entity.

~~~java
package com.example.directory.person.persistence;

import java.util.List;

import org.springframework.data.ldap.repository.LdapRepository;

public interface PersonRepository
        extends LdapRepository<PersonEntry> {

    List<PersonEntry> findByUid(String uid);
}
~~~

Repository cho phép service tìm entry theo UID mà không cần biết filter LDAP cụ thể hoặc cách mapper chuyển Attributes sang Java object.

Trách nhiệm của repository:

- Xác định entity/ID được lưu trong directory.
- Khai báo finder method phù hợp.
- Đóng gói query theo thuộc tính LDAP.
- Cung cấp CRUD theo semantics Spring Data LDAP.
- Đặt custom persistence operation khi cần thao tác LDAP đặc thù.
- Giữ chi tiết mapping và query ở tầng persistence.

Repository không nên:

- Trả HTTP status code.
- Kiểm tra một user có được phép phê duyệt yêu cầu hay không.
- Gửi email hoặc gọi hệ thống thanh toán.
- Chọn workflow theo vai trò nghiệp vụ.
- Trả thông báo giao diện.
- Tự quyết định chính sách retry nhiều bước của use case.

### Vì sao finder method thuộc Repository?

Phương thức:

~~~java
List<PersonEntry> findByUid(String uid);
~~~

mô tả một cách truy xuất dữ liệu theo attribute `uid`. Nó không nói “đăng nhập”, “mời nhân viên”, “phê duyệt tài khoản” hay “cấp quyền”. Đó là các use case của service.

Nếu một finder cần filter phức tạp hoặc matching rule riêng, chi tiết đó vẫn thuộc persistence. Service chỉ cần một phương thức có ý nghĩa truy xuất rõ ràng.

## 8. Entity ODM: biểu diễn entry, không phải toàn bộ domain

Spring LDAP ODM có thể ánh xạ entry thành Java class:

~~~java
package com.example.directory.person.persistence;

import javax.naming.Name;

import org.springframework.ldap.odm.annotations.Attribute;
import org.springframework.ldap.odm.annotations.Entry;
import org.springframework.ldap.odm.annotations.Id;

@Entry(
    base = "ou=people",
    objectClasses = {
        "top",
        "person",
        "organizationalPerson",
        "inetOrgPerson"
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
    private String mail;

    public PersonEntry() {
    }

    public Name getDn() {
        return dn;
    }

    public void setDn(Name dn) {
        this.dn = dn;
    }

    public String getUid() {
        return uid;
    }

    public void setUid(String uid) {
        this.uid = uid;
    }

    public String getCommonName() {
        return commonName;
    }

    public void setCommonName(String commonName) {
        this.commonName = commonName;
    }

    public String getSurname() {
        return surname;
    }

    public void setSurname(String surname) {
        this.surname = surname;
    }

    public String getMail() {
        return mail;
    }

    public void setMail(String mail) {
        this.mail = mail;
    }
}
~~~

Ở đây:

- `@Entry` mô tả object classes và base DN cho entity.
- `@Id` đánh dấu DN định danh entry.
- `@Attribute` liên kết field Java với attribute LDAP.
- `Name` giữ DN ở dạng cấu trúc thay vì thao tác bằng chuỗi tùy ý.

Entity phản ánh cấu trúc lưu trữ. Nó có thể chứa tên attribute, DN và các chi tiết schema mà API không nên công khai trực tiếp.

### Không nhầm entity với DTO

Không trả thẳng `PersonEntry` từ controller nếu không có chủ đích. Entity có thể thêm attribute nội bộ trong tương lai, hoặc DN/objectClass có thể không phù hợp để lộ ra API.

Tạo DTO/view riêng:

~~~java
package com.example.directory.person.domain;

public record PersonView(
        String uid,
        String commonName,
        String surname,
        String mail) {
}
~~~

Service chuyển entity sang view theo hợp đồng use case. Điều này giúp thay đổi mapping LDAP mà không tự động thay đổi response của API.

## 9. Service: nơi điều phối use case

Service mô tả hành động mà ứng dụng muốn thực hiện. Ví dụ một use case đọc hồ sơ theo UID:

~~~java
package com.example.directory.person.application;

import java.util.List;

import org.springframework.stereotype.Service;

import com.example.directory.person.domain.PersonView;
import com.example.directory.person.persistence.PersonEntry;
import com.example.directory.person.persistence.PersonRepository;

@Service
public class PersonDirectoryService {

    private final PersonRepository repository;

    public PersonDirectoryService(PersonRepository repository) {
        this.repository = repository;
    }

    public PersonView getPerson(String uid) {
        if (uid == null || !uid.matches("[A-Za-z0-9._-]{1,64}")) {
            throw new IllegalArgumentException("Invalid uid");
        }

        List<PersonEntry> matches = repository.findByUid(uid);

        if (matches.isEmpty()) {
            throw new PersonNotFoundException(uid);
        }
        if (matches.size() > 1) {
            throw new IllegalStateException(
                    "UID is ambiguous in the configured search base");
        }

        return toView(matches.get(0));
    }

    private static PersonView toView(PersonEntry entry) {
        return new PersonView(
                entry.getUid(),
                entry.getCommonName(),
                entry.getSurname(),
                entry.getMail());
    }
}
~~~

Service thực hiện:

1. Kiểm tra UID theo quy tắc đầu vào của use case.
2. Gọi repository để lấy entry.
3. Xử lý trường hợp không có kết quả hoặc nhiều kết quả.
4. Chuyển entity thành view của ứng dụng.

Ví dụ này dùng validation đơn giản để làm rõ trách nhiệm. Dự án thực tế có thể dùng Bean Validation, exception riêng và policy authorization.

**Lưu ý:** validation UID ở service không thay thế escaping filter hoặc DN. Repository/LDAP API vẫn phải xây query an toàn; service không được ghép filter LDAP thủ công.

## 10. Service không nên chứa chi tiết LDAP

Một service có thể bị viết như sau:

~~~java
@Service
public class BadPersonService {

    public PersonEntry find(String uid) {
        LdapContextSource source = new LdapContextSource();
        source.setUrl("ldaps://ldap.example.org:636");
        source.setBase("dc=example,dc=org");
        source.afterPropertiesSet();

        LdapTemplate template = new LdapTemplate(source);

        String filter = "(uid=" + uid + ")";
        // Gọi search trực tiếp và tự parse Attributes...
        return null;
    }
}
~~~

Vấn đề:

- Service biết URL, base DN và lifecycle context.
- Filter được nối trực tiếp từ input, dễ lỗi escaping/injection.
- Không tái sử dụng bean và cấu hình chung.
- Khó mock persistence trong unit test.
- Logic LDAP bị nhân bản ở nhiều service.

Hướng đúng là service gọi repository:

~~~java
@Service
public class PersonDirectoryService {

    private final PersonRepository repository;

    public PersonDirectoryService(PersonRepository repository) {
        this.repository = repository;
    }

    public List<PersonEntry> findByUid(String uid) {
        return repository.findByUid(uid);
    }
}
~~~

Trong ví dụ rút gọn này service chỉ chuyển tiếp; service thật nên có use case, validation, authorization, mapping hoặc orchestration có ý nghĩa. Nếu chỉ cần expose một finder đơn giản, controller/application facade có thể gọi theo thiết kế dự án, nhưng không nên tạo service rỗng chỉ để thêm một tầng.

## 11. Custom Repository Operation cho thao tác LDAP đặc thù

Không phải mọi persistence operation đều phù hợp với derived finder hoặc `save(entity)`. Ví dụ, cập nhật riêng một attribute nên dùng LDAP Modify để không ghi đè toàn bộ entry.

Khai báo repository fragment:

~~~java
package com.example.directory.person.persistence;

public interface PersonDirectoryOperations {

    void replaceMailByUid(String uid, String newMail);
}
~~~

Implementation dùng `LdapTemplate`:

~~~java
package com.example.directory.person.persistence;

import javax.naming.Name;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;

import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

public class PersonDirectoryOperationsImpl
        implements PersonDirectoryOperations {

    private final LdapTemplate ldapTemplate;

    public PersonDirectoryOperationsImpl(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    @Override
    public void replaceMailByUid(String uid, String newMail) {
        Name relativeDn = LdapNameBuilder.newInstance("ou=people")
                .add("uid", uid)
                .build();

        ModificationItem change = new ModificationItem(
                DirContext.REPLACE_ATTRIBUTE,
                new BasicAttribute("mail", newMail));

        ldapTemplate.modifyAttributes(
                relativeDn,
                new ModificationItem[] { change });
    }
}
~~~

Repository kết hợp CRUD và fragment:

~~~java
package com.example.directory.person.persistence;

import java.util.List;

import org.springframework.data.ldap.repository.LdapRepository;

public interface PersonRepository
        extends LdapRepository<PersonEntry>,
                PersonDirectoryOperations {

    List<PersonEntry> findByUid(String uid);
}
~~~

Spring Data repository composition có thể ghép fragment implementation với repository chính. Tên implementation, package discovery và repository configuration cần tuân theo convention của phiên bản Spring Data đang dùng; đặt fragment implementation cạnh interface giúp việc phát hiện rõ ràng.

**Ranh giới vẫn được giữ:** service gọi một phương thức persistence có ý nghĩa; chi tiết `LdapNameBuilder`, `ModificationItem` và `LdapTemplate` nằm trong adapter/repository fragment.

## 12. Service gọi custom repository operation

Service điều phối validation và quyền nghiệp vụ trước khi yêu cầu persistence thực hiện:

~~~java
@Service
public class PersonDirectoryService {

    private final PersonRepository repository;

    public PersonDirectoryService(PersonRepository repository) {
        this.repository = repository;
    }

    public void changeMail(String uid, String newMail) {
        validateUid(uid);
        validateMail(newMail);

        List<PersonEntry> matches = repository.findByUid(uid);

        if (matches.isEmpty()) {
            throw new PersonNotFoundException(uid);
        }
        if (matches.size() != 1) {
            throw new IllegalStateException("UID is not unique");
        }

        repository.replaceMailByUid(uid, newMail);
    }

    private static void validateUid(String uid) {
        if (uid == null || !uid.matches("[A-Za-z0-9._-]{1,64}")) {
            throw new IllegalArgumentException("Invalid uid");
        }
    }

    private static void validateMail(String mail) {
        if (mail == null || mail.isBlank() || mail.length() > 254) {
            throw new IllegalArgumentException("Invalid mail");
        }
    }
}
~~~

Service không cần biết thao tác thay attribute được biểu diễn bằng `ModificationItem` nào. Repository fragment đảm nhiệm chi tiết đó.

Ví dụ trên có hai thao tác LDAP: tìm người và sửa mail. Giữa hai thao tác có thể có race nếu entry bị xóa/rename hoặc dữ liệu thay đổi đồng thời. Kiểm tra trước giúp trả lỗi nghiệp vụ dễ hiểu, nhưng không phải transaction hay compare-and-swap. Kết quả của Modify tại server vẫn là nguồn xác nhận cuối cùng.

## 13. Ai chịu trách nhiệm về DN, filter và schema?

Các chi tiết này thuộc persistence boundary, nhưng service có thể truyền business key đã xác thực.

| Chi tiết | Tầng nên xử lý | Lý do |
|---|---|---|
| DN tương đối và base DN | Configuration + Repository | Gắn với topology và cách định vị entry |
| Ghép RDN bằng `LdapNameBuilder` | Repository/adapter | Đây là quy tắc biểu diễn DN |
| Escape filter assertion | Repository/query builder | Bảo vệ cú pháp LDAP filter |
| Object class và attribute mapping | ODM entity/schema | Phản ánh cấu trúc entry |
| Chọn search base/scope | Repository | Là một phần của truy vấn persistence |
| UID có được phép theo nghiệp vụ hay không | Service/domain policy | Quy tắc ứng dụng |
| Người gọi có quyền sửa hồ sơ hay không | Security/application service | Authorization |
| Attribute mail được thay bằng Modify hay save entity | Repository/custom operation | Quyết định kỹ thuật persistence |
| URL, TLS, bind account | Configuration/secret management | Hạ tầng và môi trường |

Không để service nhận một raw DN từ client rồi đưa thẳng vào repository nếu client không được phép quyết định vị trí directory. Thường API nhận UID hoặc employee ID, service xác thực business identity, repository xây DN từ base/OU được cấu hình.

## 14. Phân biệt Repository và Service qua ví dụ use case

Giả sử yêu cầu “chuyển nhân viên sang phòng ban mới và thêm vào group tương ứng”.

Một repository có thể cung cấp các thao tác:

- Tìm person theo UID.
- Cập nhật thuộc tính phòng ban.
- Tìm group theo tên.
- Thêm member DN vào group.

Service điều phối thứ tự và quy tắc:

1. Kiểm tra người yêu cầu có quyền chuyển nhân viên.
2. Xác minh person tồn tại và trạng thái cho phép chuyển.
3. Xác định OU/group đích theo quy tắc nghiệp vụ.
4. Gọi repository cập nhật thuộc tính/entry.
5. Gọi repository membership operation.
6. Xử lý kết quả từng bước và ghi nhận trạng thái nếu một bước thất bại.

Repository không nên tự quyết định “phòng ban A luôn thuộc group B” nếu đó là policy thay đổi theo nghiệp vụ. Service cũng không nên tự tạo filter `(member=...)` hoặc thao tác JNDI trực tiếp.

### Một workflow nhiều bước không tự nguyên tử

LDAP Modify trên một entry không tạo transaction cho việc cập nhật person và group ở hai entry. Nếu bước cập nhật person thành công nhưng thêm group member thất bại, service phải có chính sách:

- Báo lỗi kèm trạng thái partial completion.
- Thử bù trừ nếu thao tác bù trừ an toàn.
- Lưu workflow/checkpoint để tiếp tục.
- Dùng extension transaction chỉ khi directory/client hỗ trợ và đã được kiểm thử.

Không mặc định `@Transactional` của Spring với transaction manager cơ sở dữ liệu sẽ rollback LDAP changes.

## 15. Exception: tầng nào xử lý điều gì?

Lỗi có thể phát sinh ở nhiều tầng:

| Lỗi | Nơi nhận diện ban đầu | Cách xử lý |
|---|---|---|
| UID đầu vào sai định dạng | Service | Validation error |
| Không tìm thấy person | Service sau repository result | Business not found |
| UID trả nhiều entry | Service hoặc repository contract | Ambiguous identity; điều tra uniqueness |
| DN không tồn tại khi Modify | Repository/LDAP adapter | Chuyển thành kết quả persistence phù hợp; service quyết định use case |
| Schema violation | LDAP server, được client chuyển thành exception | Giữ nguyên nguyên nhân kỹ thuật; ánh xạ thành lỗi nghiệp vụ nếu có quy tắc |
| Invalid credentials | Connection/bind layer | Báo lỗi hạ tầng/xác thực, không retry vô hạn |
| Insufficient access rights | LDAP server | Cấu hình ACL hoặc quyền service account |
| Timeout/network failure | ContextSource/client | Timeout, retry có giới hạn và xử lý unknown outcome |
| Mapping sai attribute | ODM/repository | Sửa mapping/schema contract |
| Lỗi HTTP serialization | Controller/API | Xử lý ở adapter HTTP |

Spring LDAP thường chuyển các lỗi JNDI thành hệ exception của Spring DataAccessException hierarchy qua các API template. Không nên bắt Exception chung rồi trả danh sách rỗng, vì điều đó biến lỗi directory thành “không tìm thấy dữ liệu”.

Service có thể ánh xạ lỗi persistence thành lỗi use case, nhưng cần giữ cause và phân biệt lỗi có thể retry với lỗi validation/ACL/schema.

## 16. Security: bind identity và authorization không cùng một trách nhiệm

Configuration quyết định ứng dụng bind vào LDAP bằng account nào. Đây là **technical identity** của kết nối.

Service/Spring Security quyết định **người dùng đang gọi use case có quyền thực hiện hành động hay không**. Đây là authorization ở ứng dụng.

Hai khái niệm khác nhau:

- Bind DN như `uid=svc-directory,ou=services,...` là account ứng dụng dùng để truy cập directory.
- UID của nhân viên đang được chỉnh sửa là business identity.
- Principal đăng nhập API là danh tính người gọi.
- LDAP ACL quyết định bind account có quyền đọc/ghi entry nào.
- Application authorization quyết định principal có được phép yêu cầu hành động đó hay không.

Không dùng bind account đặc quyền cao để thay thế kiểm tra quyền người gọi. Ngược lại, không mong LDAP ACL hiểu đầy đủ mọi quy tắc nghiệp vụ của ứng dụng.

Các nguyên tắc:

- Dùng LDAPS hoặc StartTLS và xác minh chứng chỉ.
- Inject bind password qua secret manager/environment.
- Dùng service account quyền tối thiểu.
- Tách account read-only và writer nếu topology/chính sách yêu cầu.
- Không log credential, full entry hoặc dữ liệu nhạy cảm không cần thiết.
- Hạn chế OU/base và quyền rename/delete.
- Kiểm thử ACL bằng đúng bind identity của từng bean.

## 17. Nhiều ContextSource: Configuration chọn, Repository định tuyến

Một ứng dụng có thể dùng nhiều directory source, ví dụ một LDAP nội bộ và một directory đối tác. Configuration có thể tạo hai `ContextSource` và hai `LdapTemplate` có qualifier rõ ràng.

~~~java
@Bean("internalLdapTemplate")
LdapTemplate internalLdapTemplate(
        @Qualifier("internalContextSource")
        LdapContextSource source) {
    return new LdapTemplate(source);
}

@Bean("partnerLdapTemplate")
LdapTemplate partnerLdapTemplate(
        @Qualifier("partnerContextSource")
        LdapContextSource source) {
    return new LdapTemplate(source);
}
~~~

Repository cần được nối đúng template cho package/aggregate tương ứng. Với Spring Data LDAP, có thể cấu hình nhiều nhóm repository scan riêng theo `@EnableLdapRepositories` và `ldapTemplateRef` tương ứng; phải tránh scan trùng repository hoặc để bean selection mơ hồ.

Service nên gọi repository tương ứng với use case. Service không nên tự kiểm tra hostname rồi chọn một `LdapTemplate` theo chuỗi URL. Chính sách định tuyến directory thuộc adapter/configuration và phải được kiểm thử.

## 18. Những anti-pattern thường gặp

| Anti-pattern | Vấn đề | Hướng sửa |
|---|---|---|
| Controller tự gọi `LdapTemplate` | HTTP và persistence bị trộn | Controller gọi service |
| Service tạo `LdapContextSource` | Lặp config, khó test | Khai báo bean ở Configuration |
| Service nối DN/filter | Dễ lỗi escaping và lệch base | Dùng repository/query builder |
| Repository quyết định business role | Persistence chứa policy cấp cao | Chuyển policy sang service/domain |
| Entity dùng làm API response | Lộ cấu trúc LDAP và schema | Map sang DTO/view |
| Repository gửi email hoặc event | Persistence biết workflow | Service điều phối |
| Service gọi nhiều `modifyAttributes` trực tiếp | Low-level LDAP rải rác | Đóng gói custom repository operation |
| Bắt mọi exception rồi trả empty list | Che lỗi ACL/network/schema | Phân loại exception |
| Dùng `save` cho cập nhật một attribute | Có thể ghi lại dữ liệu không cần thiết | Custom partial Modify operation |
| Ghép URL/base từ input request | Rủi ro routing và truy cập ngoài phạm vi | Chọn source/base từ config |
| Dùng `@Transactional` như transaction nhiều entry | Tạo cảm giác atomic giả | Thiết kế partial success/compensation |
| Tạo LdapTemplate mới cho mỗi request | Lifecycle và config khó kiểm soát | Reuse bean Spring |

## 19. Kiểm thử theo từng ranh giới

Không cần dùng một loại test để chứng minh mọi tầng.

| Loại test | Thành phần | Mục tiêu |
|---|---|---|
| Unit test service | Mock repository/ports | Validation, orchestration, not-found, ambiguous result |
| Repository integration test | Repository + directory test | Mapping, finder, CRUD, custom Modify |
| Configuration/context test | Spring application context | Bean wiring, repository scan, qualifier |
| LDAP contract test | Directory server thực tế | Schema, ACL, TLS, referral, result code |
| API test | Controller + service | HTTP contract, validation và error mapping |

### Unit test service

Ví dụ kiểm tra service không tìm thấy người:

~~~java
@ExtendWith(MockitoExtension.class)
class PersonDirectoryServiceTest {

    @Mock
    private PersonRepository repository;

    @InjectMocks
    private PersonDirectoryService service;

    @Test
    void throwsWhenUidDoesNotExist() {
        when(repository.findByUid("lan"))
                .thenReturn(List.of());

        assertThrows(
                PersonNotFoundException.class,
                () -> service.getPerson("lan"));
    }
}
~~~

Test này không cần LDAP server vì mục tiêu là kiểm tra use case. Nó không chứng minh query filter hoặc ODM mapping đúng.

### Repository integration test

Dùng directory test để xác minh:

- `@Entry` và `@Attribute` map đúng objectClass/attribute.
- DN tương đối kết hợp base DN chính xác.
- Finder method trả đúng entry.
- Custom fragment chỉ thay attribute được yêu cầu.
- Schema violation và duplicate DN được xử lý như mong đợi.
- ACL reader/writer đúng quyền.
- Kết nối TLS hoạt động theo cấu hình.

### Configuration test

Khởi động Spring context để xác minh:

- `LdapContextSource` có đúng URL/base.
- `LdapTemplate` nhận đúng source.
- Repository scan đúng package.
- Repository dùng đúng template.
- Không có nhiều bean cùng tên/qualifier gây mơ hồ.

Không ghi credential thật vào test log hoặc fixture.

## 20. Quyết định đặt code ở đâu?

Khi phân vân một đoạn code thuộc tầng nào, hãy xét mục đích:

| Câu hỏi | Tầng phù hợp |
|---|---|
| URL LDAP, base DN, bind DN là gì? | Configuration |
| Truststore, pool, timeout được cấu hình ra sao? | Configuration |
| Field Java map tới attribute nào? | ODM entity |
| Tìm person theo UID bằng LDAP query nào? | Repository |
| Sửa riêng attribute mail bằng ModifyRequest nào? | Repository/custom fragment |
| Người dùng có được đổi email không? | Service/security policy |
| Email mới có hợp lệ theo nghiệp vụ không? | Service/domain |
| Khi đổi email phải cập nhật thêm hệ thống nào? | Service/orchestrator |
| Nếu cập nhật hai entry thành công một phần thì xử lý thế nào? | Service/workflow |
| HTTP trả 404 hay 409? | Controller/API exception adapter |

Một câu hỏi hữu ích: **nếu đổi LDAP server hoặc cách mapping entry, đoạn code này có cần đổi không?** Nếu có, nó thường thuộc configuration/persistence. **Nếu đổi quy tắc nghiệp vụ mà không đổi LDAP schema, đoạn code này có cần đổi không?** Nếu có, nó thường thuộc service/domain.

## 21. Bài tập thực hành

**Bối cảnh:** xây API quản lý nhân viên lưu trong LDAP. API có chức năng xem hồ sơ theo UID, thay email và thêm nhân viên vào group. Directory có base DN `dc=example,dc=org`, OU `people` và OU `groups`.

Thực hiện trên directory test:

1. Tạo package config, person.persistence, person.application và person.api.
2. Viết LdapConfiguration tạo LdapContextSource, LdapTemplate và bật repository scan.
3. Định nghĩa PersonEntry với @Entry, @Id Name và các field uid, cn, sn, mail.
4. Tạo PersonRepository với finder theo UID.
5. Viết PersonDirectoryService xử lý UID không hợp lệ, không tìm thấy và kết quả trùng.
6. Tạo DTO PersonView; không trả entity LDAP trực tiếp từ API.
7. Viết custom repository operation để thay riêng mail bằng LdapTemplate.modifyAttributes.
8. Đưa validation email và authorization vào service/security policy.
9. Thử đặt URL LDAP trong service rồi refactor về Configuration; so sánh khả năng unit test.
10. Tạo unit test service bằng mock repository.
11. Tạo integration test cho finder, mapping và custom Modify trên LDAP test.
12. Thử cấu hình sai base DN hoặc bind credential; xác định lỗi xuất hiện ở đúng tầng.
13. Mô phỏng cập nhật person và group thành công một phần; thiết kế cách báo lỗi/tiếp tục.
14. Giải thích vì sao `@Transactional` database không tự rollback nhiều LDAP operations.
15. Vẽ sơ đồ dependency và chỉ ra chỗ đặt DN builder, filter builder, secret và business rule.

**Tiêu chí hoàn thành:** người học có thể giải thích và triển khai đúng ranh giới Configuration/Repository/Service; service không chứa chi tiết kết nối/filter/JNDI; repository không chứa workflow nghiệp vụ; configuration không chứa policy; từng tầng có thể kiểm thử độc lập và luồng tích hợp chạy được trên directory test.

## 22. Tổng kết và tài liệu tham khảo

Một ứng dụng Spring Data LDAP dễ bảo trì khi mỗi tầng có một trách nhiệm rõ:

- **Configuration** tạo và nối `ContextSource`, `LdapTemplate`, repository scanning, TLS, pool và secret.
- **Repository** ánh xạ entity, truy vấn và đóng gói CRUD hoặc custom LDAP operation.
- **Service** thực hiện use case, validation, authorization, orchestration, consistency và xử lý kết quả.
- **Controller** chuyển HTTP request/response, không tự thực hiện LDAP persistence.

Khi một thao tác cần nhiều bước, service điều phối chúng và xử lý partial success. Repository thực hiện từng thao tác LDAP có phạm vi rõ; Configuration bảo đảm các thao tác dùng đúng endpoint, base và credential. Không giả định transaction cơ sở dữ liệu áp dụng cho nhiều LDAP entry.

Tài liệu tham khảo:

- [Spring Data LDAP Reference](https://docs.spring.io/spring-data/ldap/reference/): repository, ODM, entity mapping và repository configuration.
- [Spring LDAP Reference](https://docs.spring.io/spring-ldap/reference/): LdapContextSource, LdapTemplate, query, Modify và exception translation.
- [Spring Framework — Java-based Container Configuration](https://docs.spring.io/spring-framework/reference/core/beans/java.html): @Configuration, @Bean và dependency injection.
- [Spring Data Commons — Repository Abstraction](https://docs.spring.io/spring-data/commons/reference/repositories/core-concepts.html): repository abstraction và composition.
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): authorization tại application/service boundary.
- [RFC 4511 — LDAP Protocol](https://www.rfc-editor.org/rfc/rfc4511): Search, Add, Modify, Delete và ModifyDN.
- [RFC 4512 — LDAP Directory Information Models](https://www.rfc-editor.org/rfc/rfc4512): DIT, entry, schema và attribute.
