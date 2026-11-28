# Truy cập thông tin base bằng BaseLdapPathAware khi cần

> **Chương:** LdapTemplate  
> **Module:** SPRING_DATA_LDAP — truy cập dịch vụ thư mục LDAP qua Spring Data LDAP, ánh xạ entry phân cấp thành đối tượng Java, truy vấn và CRUD với `LdapRepository`/`LdapTemplate`.

Khi cấu hình Spring LDAP, ta thường khai báo một **base DN** cho `ContextSource`, chẳng hạn `dc=example,dc=org`. Từ đó, `LdapTemplate` và các lớp ánh xạ trong ứng dụng có thể làm việc với **DN tương đối** như `uid=lan,ou=people` thay vì phải lặp lại hậu tố `dc=example,dc=org` ở mọi thao tác.

Tuy nhiên, một vài nghiệp vụ vẫn cần **DN đầy đủ** (*full DN*), chẳng hạn ghi giá trị `member` cho nhóm `groupOfNames`:

~~~ldif
dn: cn=developers,ou=groups,dc=example,dc=org
objectClass: top
objectClass: groupOfNames
cn: developers
member: uid=lan,ou=people,dc=example,dc=org
~~~

Nếu code chỉ biết `uid=lan,ou=people`, nó cần biết base DN để xây giá trị `member` đúng. Spring LDAP có cơ chế truyền base DN đã cấu hình vào các bean: API lịch sử là **`BaseLdapPathAware`**, còn API được khuyến nghị trong các phiên bản hiện đại là **`BaseLdapNameAware`**.

> **Quan trọng về phiên bản:** `org.springframework.ldap.core.support.BaseLdapPathAware` đã bị **deprecated từ Spring LDAP 2.0** và nhận kiểu `DistinguishedName` cũ. Các dự án mới nên dùng `org.springframework.ldap.core.support.BaseLdapNameAware` với `javax.naming.ldap.LdapName`. Đừng nhầm hai interface này dù chúng cùng có phương thức mang tên `setBaseLdapPath`.

Bài học giải thích khi nào cần biết base, cách Spring truyền base vào bean, cách tạo DN tuyệt đối một cách an toàn, các lựa chọn cấu hình, và cách kiểm thử để không ghép hoặc lặp DN sai.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

1. Giải thích vai trò của `base` trong `ContextSource` và sự khác nhau giữa DN tương đối với DN đầy đủ.
2. Biết **khi nào** thao tác `LdapTemplate` chỉ cần DN tương đối, khi nào một giá trị thuộc tính LDAP cần DN tuyệt đối.
3. Phân biệt API cũ `BaseLdapPathAware` với `BaseLdapNameAware` hiện đại.
4. Đăng ký `BaseLdapPathBeanPostProcessor`, nhận `LdapName` vào service và tạo full DN bằng `LdapNameBuilder`.
5. Xử lý trường hợp nhiều `ContextSource`, base rỗng, thay đổi môi trường và cấu hình sai base.
6. Viết test cho DN composition, mapping và thao tác nhóm có `member`.
7. Áp dụng escaping, giới hạn phạm vi dữ liệu và ACL mà không xem việc lấy base DN là cơ chế phân quyền.

## 2. Base DN là gì và tác động đến các thao tác LDAP?

Xét cây thư mục đơn giản:

~~~text
dc=example,dc=org                          ← base DN cấu hình
├── ou=people
│   ├── uid=lan
│   └── uid=binh
└── ou=groups
    └── cn=developers
~~~

Nếu cấu hình `spring.ldap.base=dc=example,dc=org` thì:

| Khái niệm | Giá trị minh họa | Dùng vào đâu? |
|---|---|---|
| **Base DN** | `dc=example,dc=org` | Gốc mà các thao tác LDAP của `ContextSource` được đặt tương đối |
| **DN tương đối với base** | `uid=lan,ou=people` | Tham số của `LdapTemplate.lookup(...)`, `bind(...)`, `modifyAttributes(...)`... |
| **DN đầy đủ** | `uid=lan,ou=people,dc=example,dc=org` | Tên hoàn chỉnh trong directory; giá trị `member` tham chiếu người dùng |
| **Search base tương đối** | `ou=people` | Chỉ định nơi tìm bên trong base khi gọi `LdapTemplate.search(...)` |
| **RDN** | `uid=lan` | Một thành phần dùng để đặt tên entry |

Một thao tác:

~~~java
Name relativeDn = LdapNameBuilder
        .newInstance("ou=people")
        .add("uid", "lan")
        .build();

Person person = ldapTemplate.lookup(relativeDn, mapper);
~~~

chỉ truyền `uid=lan,ou=people` cho `LdapTemplate` (trong đoạn trên, `mapper` là `ContextMapper<Person>` hay `AttributesMapper<Person>` đã khai báo đúng overload).

`ContextSource` biết base nên định vị entry tương ứng với full DN `uid=lan,ou=people,dc=example,dc=org`. Nếu bạn truyền **full DN đó trực tiếp** cho một API đang kỳ vọng DN tương đối với base, việc xử lý có thể dẫn đến DN sai, ví dụ base bị nối hai lần, hoặc lỗi không tìm thấy entry.

**Quy tắc thực hành:** dùng DN tương đối cho các thao tác `LdapTemplate` được neo vào `ContextSource`; chỉ xây DN đầy đủ khi hợp đồng nghiệp vụ hoặc thuộc tính yêu cầu nó.

## 3. Khi nào thực sự cần biết base DN?

Trong nhiều chức năng CRUD, ứng dụng **không cần lấy base ra** vì `ContextSource` đã xử lý nó. Các trường hợp cần full DN thường xuất hiện ở ranh giới hệ thống:

| Trường hợp | Có cần truy xuất base? | Lý do |
|---|---|---|
| Đọc `uid=lan,ou=people` bằng `lookup` | Thường không | `ContextSource` đã có base |
| Tìm người dưới `ou=people` | Thường không | Search base chỉ cần tương đối |
| Cập nhật `mail` tại DN tương đối | Không | `modifyAttributes` hoạt động theo context base |
| Ghi `member` của `groupOfNames` | **Có** | Giá trị của thuộc tính là DN đầy đủ của thành viên |
| Ghi `uniqueMember` cho `groupOfUniqueNames` | **Có** | Giá trị tham chiếu DN theo syntax của attribute |
| Cung cấp DN tham chiếu cho hệ thống khác | Có thể | Hợp đồng bên ngoài có thể yêu cầu full DN |
| Hiển thị một đường dẫn dễ đọc cho quản trị viên | Có thể | Cần phân biệt DN tuyệt đối và DN tương đối |
| Đọc full DN từ một `DirContextOperations` đã cung cấp nó | Không nhất thiết | Không cần nối base lần nữa nếu giá trị đã tuyệt đối |

Lấy base DN **không thay thế việc thiết kế cấu trúc OU**, không khiến một DN tự nằm trong nhánh được phép và không xác nhận entry thực sự tồn tại. Việc tạo full DN chỉ tạo một **tên hợp cú pháp**; tìm kiếm, quyền và tính toàn vẹn tham chiếu là trách nhiệm khác.

## 4. Hai API dễ nhầm: BaseLdapPathAware và BaseLdapNameAware

Tên bài đề cập `BaseLdapPathAware` do đó cần biết lịch sử của nó.

| API | Kiểu nhận vào | Tình trạng | Nên dùng ở đâu? |
|---|---|---|---|
| `BaseLdapPathAware` | `org.springframework.ldap.core.DistinguishedName` | **Deprecated** từ Spring LDAP 2.0 | Chỉ để đọc và bảo trì code cũ |
| `BaseLdapNameAware` | `javax.naming.ldap.LdapName` | API hiện đại được khuyến nghị | Dự án Spring LDAP mới |
| `BaseLdapPathSource` | Getter `getBaseLdapName()` | Nguồn cung cấp base | Khi muốn đọc trực tiếp từ context source |
| `BaseLdapPathContextSource` | Kết hợp `ContextSource` và `BaseLdapPathSource` | Interface cho context source có base | Khi wiring trực tiếp đối tượng context source |

**Legacy API** có chữ ký:

~~~java
import org.springframework.ldap.core.DistinguishedName;
import org.springframework.ldap.core.support.BaseLdapPathAware;

@Deprecated
class LegacyPersonService implements BaseLdapPathAware {

    private DistinguishedName basePath;

    @Override
    public void setBaseLdapPath(DistinguishedName basePath) {
        this.basePath = basePath;
    }
}
~~~

Đây là ví dụ nhận diện code cũ, **không phải gợi ý tạo service mới** bằng `DistinguishedName`. Các class/method liên quan tới `DistinguishedName` đã được deprecated. Trong dự án mới, thay bằng interface `BaseLdapNameAware` và dùng `LdapNameBuilder`.

**Modern API:**

~~~java
import javax.naming.ldap.LdapName;
import org.springframework.ldap.core.support.BaseLdapNameAware;

public class PersonDnService implements BaseLdapNameAware {

    private LdapName basePath;

    @Override
    public void setBaseLdapPath(LdapName basePath) {
        this.basePath = (LdapName) basePath.clone();
    }
}
~~~

Chú ý: cả hai interface có phương thức tên **`setBaseLdapPath`**, nhưng tham số thuộc hai kiểu khác nhau. `javax.naming.ldap.LdapName` là kiểu thuộc JNDI trong Java, **không có package `jakarta.naming.ldap.LdapName`**.

## 5. Cơ chế Spring tiêm base vào bean

Việc service implements `BaseLdapNameAware` **chưa đủ** để tự nhận base. Spring LDAP cần một **`BaseLdapPathBeanPostProcessor`** trong ApplicationContext để phát hiện bean và gọi `setBaseLdapPath(...)`.

~~~mermaid
sequenceDiagram
    autonumber
    participant APP as Spring ApplicationContext
    participant CS as LdapContextSource
    participant BPP as BaseLdapPathBeanPostProcessor
    participant SVC as PersonDnService

    APP->>CS: Tạo ContextSource theo LDAP base
    APP->>BPP: Đăng ký BeanPostProcessor
    APP->>SVC: Tạo Spring-managed service
    BPP->>CS: Lấy base qua BaseLdapPathSource
    CS-->>BPP: LdapName base
    BPP->>SVC: setBaseLdapPath(LdapName)
    APP-->>SVC: Bean sẵn sàng nhận request
~~~

Có **hai điều kiện**:

1. Bean nhận base phải là **Spring-managed bean** (ví dụ `@Service` hoặc được khai báo bằng `@Bean`) và implements `BaseLdapNameAware`.
2. ApplicationContext phải có `BaseLdapPathBeanPostProcessor`. Bộ xử lý lấy base từ một `BaseLdapPathSource`, thường là `LdapContextSource`.

Không tự tạo `new PersonDnService()` bên ngoài Spring rồi mong post-processor sẽ chạy. Khi có nhiều context source, cần cấu hình chọn **đúng nguồn base** thay vì để việc nhận base không rõ ràng.

### Ví dụ đăng ký bằng Java Configuration

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ldap.core.support.BaseLdapPathBeanPostProcessor;

@Configuration(proxyBeanMethods = false)
public class LdapBaseInjectionConfig {

    @Bean
    public static BaseLdapPathBeanPostProcessor
            baseLdapPathBeanPostProcessor() {
        return new BaseLdapPathBeanPostProcessor();
    }
}
~~~

Việc khai báo bean hậu xử lý dạng `static @Bean` tránh tạo instance của configuration class sớm chỉ để khởi tạo post-processor. Một số dự án có thể đã đăng ký post-processor qua XML/namespace hoặc cấu hình sẵn; cần kiểm tra để tránh đăng ký trùng.

Ví dụ này giả định `ApplicationContext` có đúng **một** `BaseLdapPathSource` phù hợp. Nếu có nhiều nguồn, xem mục dành cho multi-directory bên dưới.

## 6. Cấu hình Spring Boot và base DN

Với Spring Boot có Spring LDAP/Spring Data LDAP dependency, có thể cấu hình:

~~~yaml
spring:
  ldap:
    urls: ${LDAP_URL}
    base: ${LDAP_BASE_DN}
    username: ${LDAP_BIND_DN}
    password: ${LDAP_BIND_PASSWORD}
~~~

Giá trị test:

~~~text
LDAP_URL=ldaps://ldap-test.example.org:636
LDAP_BASE_DN=dc=example,dc=org
LDAP_BIND_DN=uid=svc-reader,ou=services,dc=example,dc=org
LDAP_BIND_PASSWORD=<được-cấp-từ-secret-manager>
~~~

Với các property chuẩn như `spring.ldap.base`, Spring Boot có thể khởi tạo `LdapContextSource` tương ứng khi auto-configuration được áp dụng. Post-processor sẽ lấy **base hiệu lực của context source**, không cần giữ thêm một chuỗi hardcode `dc=example,dc=org` trong service.

Chú ý:

- Nếu service thật sự cần ghi nhóm, bind account ví dụ `svc-reader` phải được thay bằng một account có ACL phù hợp cho các thao tác được cấp phép; tên `svc-reader` không mang lại quyền ghi.
- Kết nối qua LDAPS hoặc StartTLS phải xác minh chứng chỉ, không bỏ qua TLS verification.
- Các môi trường dev/test/prod có thể dùng base khác nhau; điều quan trọng là service nhận base từ **context source đang phục vụ các thao tác**.
- Nếu không cấu hình base, getter base sẽ trả một LDAP name rỗng; khi đó các DN truyền cho `LdapTemplate` phải được hiểu theo gốc tương ứng, không tùy tiện cộng thêm một hậu tố tưởng tượng.
- Nếu thay đổi giá trị secret hoặc base bên ngoài, bean đang chạy không tự động thay đổi trừ khi hệ thống có cơ chế refresh/recreate đúng đắn. Thông thường cần rollout/restart theo quy trình vận hành.

## 7. Ví dụ hoàn chỉnh: xây full DN bằng BaseLdapNameAware

Service sau chỉ chịu trách nhiệm **xây DN**. Nó không trực tiếp kết nối LDAP và có thể được unit test một cách độc lập.

~~~java
package org.example.directory;

import javax.naming.Name;
import javax.naming.ldap.LdapName;

import org.springframework.ldap.core.support.BaseLdapNameAware;
import org.springframework.ldap.support.LdapNameBuilder;
import org.springframework.stereotype.Service;

@Service
public class PersonDnService implements BaseLdapNameAware {

    private LdapName baseLdapPath;

    @Override
    public void setBaseLdapPath(LdapName baseLdapPath) {
        if (baseLdapPath == null) {
            throw new IllegalArgumentException(
                    "Base LDAP path must not be null");
        }

        this.baseLdapPath = (LdapName) baseLdapPath.clone();
    }

    public Name relativePersonDn(String uid) {
        validateUid(uid);

        return LdapNameBuilder.newInstance("ou=people")
                .add("uid", uid)
                .build();
    }

    public Name absolutePersonDn(String uid) {
        if (baseLdapPath == null) {
            throw new IllegalStateException(
                    "Base LDAP path has not been injected");
        }

        return LdapNameBuilder.newInstance(baseLdapPath)
                .add(relativePersonDn(uid))
                .build();
    }

    private static void validateUid(String uid) {
        if (uid == null
                || !uid.matches("[A-Za-z0-9._-]{1,64}")) {
            throw new IllegalArgumentException("Invalid uid");
        }
    }
}
~~~

Ví dụ khi base là `dc=example,dc=org` và UID là `lan`:

| Lời gọi | DN thu được |
|---|---|
| `relativePersonDn("lan")` | `uid=lan,ou=people` |
| `absolutePersonDn("lan")` | `uid=lan,ou=people,dc=example,dc=org` |

Ở đây, `LdapNameBuilder.newInstance(baseLdapPath).add(relativePersonDn(uid))` **không ghép chuỗi thủ công**. Nó làm việc trên cấu trúc DN và tự xử lý việc biểu diễn RDN. Hàm `validateUid` áp dụng chính sách định danh của ứng dụng minh họa, còn builder chịu trách nhiệm escaping DN. Hệ thống thực có thể chọn chính sách UID rộng hơn sau khi xác định ranh giới danh tính.

**Lưu ý vòng đời:** service nhận base sau khi được Spring xử lý, không phải trong constructor. Đừng gọi `absolutePersonDn(...)` trong constructor của chính service. Nếu cần sử dụng base ngay khi khởi tạo một object bất biến, cân nhắc inject một `BaseLdapPathContextSource` trực tiếp rồi lấy base trong constructor (mục 11).

## 8. Trường hợp điển hình: gán member cho groupOfNames

Trong schema LDAP phổ biến, `groupOfNames` có attribute `member` chứa các DN đầy đủ của thành viên. Vì vậy khi thêm `lan` vào nhóm, ta **dùng hai dạng DN khác nhau**:

- DN **tương đối** của nhóm để gọi `LdapTemplate.modifyAttributes(...)`.
- DN **đầy đủ** của người dùng làm **giá trị** của `member`.

~~~java
package org.example.directory;

import javax.naming.Name;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;

import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;
import org.springframework.stereotype.Service;

@Service
public class GroupMembershipService {

    private final LdapTemplate ldapTemplate;
    private final PersonDnService personDnService;

    public GroupMembershipService(
            LdapTemplate ldapTemplate,
            PersonDnService personDnService) {

        this.ldapTemplate = ldapTemplate;
        this.personDnService = personDnService;
    }

    public void addMember(String groupCn, String uid) {
        if (groupCn == null
                || !groupCn.matches("[A-Za-z0-9._-]{1,64}")) {
            throw new IllegalArgumentException("Invalid group name");
        }

        Name groupDn = LdapNameBuilder.newInstance("ou=groups")
                .add("cn", groupCn)
                .build();

        String fullMemberDn =
                personDnService.absolutePersonDn(uid).toString();

        ModificationItem addition = new ModificationItem(
                DirContext.ADD_ATTRIBUTE,
                new BasicAttribute("member", fullMemberDn));

        ldapTemplate.modifyAttributes(
                groupDn, new ModificationItem[] { addition });
    }
}
~~~

Khi gọi `addMember("developers", "lan")`:

~~~text
DN thao tác Modify:
  cn=developers,ou=groups
  (tương đối với dc=example,dc=org)

Giá trị được thêm vào member:
  uid=lan,ou=people,dc=example,dc=org
  (DN đầy đủ)
~~~

Đây là một **thao tác LDAP Modify**, không phải tạo nhóm mới. Nhóm `cn=developers` phải tồn tại, có objectClass phù hợp, có quyền sửa thuộc tính `member` và không chứa giá trị thành viên trùng.

LDAP có thể trả `attributeOrValueExists (20)` khi thêm một giá trị đã tồn tại. Với API muốn hành vi idempotent, phải thiết kế cách xử lý “đã là thành viên” theo chính sách cụ thể, không `catch` mọi exception rồi bỏ qua.

### Xóa đúng một DN thành viên

~~~java
ModificationItem removal = new ModificationItem(
        DirContext.REMOVE_ATTRIBUTE,
        new BasicAttribute(
                "member",
                personDnService.absolutePersonDn("lan").toString()));

ldapTemplate.modifyAttributes(
        LdapNameBuilder.newInstance("ou=groups")
                .add("cn", "developers")
                .build(),
        new ModificationItem[] { removal });
~~~

Đoạn trên giả định `ldapTemplate` và `personDnService` đã có trong service.

Với `groupOfNames`, `member` là thuộc tính **MUST** theo schema tiêu chuẩn. Nếu xóa thành viên cuối cùng và không còn giá trị `member`, server thực thi schema có thể từ chối thao tác. Đừng chọn cách gửi `REMOVE_ATTRIBUTE` không có giá trị để xóa toàn bộ `member` nếu chỉ muốn xóa một người.

## 9. Cấu tạo DN đúng thứ tự và escaping

DN LDAP có thứ tự biểu diễn **RDN cụ thể trước, phần gốc sau**:

~~~text
uid=lan,ou=people,dc=example,dc=org
^ entry  ^ nhánh  ^ base
~~~

Mã nên dùng builder:

~~~java
Name absolute = LdapNameBuilder
        .newInstance("dc=example,dc=org")
        .add("ou", "people")
        .add("uid", "lan")
        .build();
~~~

Và tránh:

~~~java
String unsafe = "uid=" + uid + ",ou=people," + baseString;
~~~

Vì dấu phẩy, dấu cộng, dấu bằng, backslash và các ký tự đặc biệt có thể nằm trong giá trị RDN, nối chuỗi thô có nguy cơ làm sai cú pháp hoặc thay đổi ý nghĩa của DN. `LdapNameBuilder.add("uid", uid)` diễn giải `uid` là **giá trị** của RDN và thực hiện escaping khi biểu diễn DN.

**DN escaping khác LDAP filter escaping.** Ví dụ `(uid=lan*)` là một filter substring, còn `uid=lan*` là một thành phần tên và có quy tắc diễn giải riêng. Dùng `LdapQueryBuilder` hoặc các filter API của Spring LDAP khi xây điều kiện tìm kiếm từ giá trị người dùng; không dùng `LdapNameBuilder` thay cho filter builder.

### Quy tắc chống lặp base

Trước khi nối, xác định dữ liệu hiện tại là loại nào:

| Đầu vào | Có nối thêm base không? | Ví dụ |
|---|---|---|
| RDN `uid=lan` | Có, nhưng thêm cả nhánh tương đối | `uid=lan,ou=people,dc=example,dc=org` |
| DN tương đối `uid=lan,ou=people` | Có, **một lần** | `uid=lan,ou=people,dc=example,dc=org` |
| DN đầy đủ `uid=lan,ou=people,dc=example,dc=org` | **Không** | Giữ nguyên |
| DN nhận từ một thuộc tính `member` | Thường **không** nếu schema lưu full DN | Parse/kiểm tra trước khi sử dụng |
| Search base `ou=people` cho `LdapTemplate.search` | Không tự nối khi context đã có base | Dùng search base tương đối |

Trên giai đoạn di chuyển DN, một người dùng có thể đổi OU/RDN. Full DN được xây từ UID và cấu trúc OU dự kiến **không chứng minh** entry thực tế đang nằm ở đó. Khi ứng dụng có nhiều OU hoặc nhiều người cùng UID, cần cơ chế định vị entry, kiểm tra ranh giới và xử lý uniqueness rõ ràng.

## 10. Trả về DN tuyệt đối hay tương đối khi đọc entry?

Một `AttributesMapper<T>` chỉ nhận đối tượng `Attributes`, thích hợp để đọc `cn`, `mail`, `uid` nhưng **không mặc nhiên cung cấp DN**:

~~~java
ldapTemplate.search(
        query().base("ou=people")
                .where("uid").is("lan"),
        (AttributesMapper<String>) attrs ->
                (String) attrs.get("cn").get());
~~~

Nếu cần DN, sử dụng API mapper có ngữ cảnh hoặc ODM phù hợp, ví dụ `ContextMapper<T>` với `DirContextOperations`; kiểm tra rõ phương thức nào trả tên tương đối và tên đầy đủ theo phiên bản thư viện.

~~~java
import javax.naming.Name;

import org.springframework.ldap.core.ContextMapper;
import org.springframework.ldap.core.DirContextOperations;

ContextMapper<Name> dnMapper = context -> {
    DirContextOperations entry =
            (DirContextOperations) context;
    return entry.getDn();
};
~~~

`getDn()` của `DirContextOperations` thường được dùng để nhận DN của entry **tương đối với context base**. Khi cần full DN, hãy dựa trên API hợp đồng tương ứng của Spring LDAP hoặc kết hợp với base đã biết **đúng một lần**. Không dùng `getDn()` và `getNameInNamespace()` thay thế qua lại mà chưa kiểm tra chúng trả DN theo cách nào ở phiên bản đang sử dụng.

Đối với entity `@Entry`:

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

    public DirectoryPerson() {
    }

    // Getter/setter tùy ứng dụng và yêu cầu ODM.
}
~~~

Đừng chỉ dựa vào `@Id Name dn` để kết luận entity đang giữ full DN hay relative DN trong mọi ngữ cảnh. Hãy đối chiếu tài liệu ODM và thử bằng một entry test khi thực hiện API có tham chiếu DN.

## 11. Lựa chọn khác: lấy base trực tiếp từ ContextSource

Nếu không muốn dựa trên `BeanPostProcessor`, một service có thể phụ thuộc vào interface `BaseLdapPathContextSource` để nhận base trong constructor:

~~~java
package org.example.directory;

import javax.naming.ldap.LdapName;

import org.springframework.ldap.core.support.BaseLdapPathContextSource;
import org.springframework.ldap.support.LdapNameBuilder;
import org.springframework.stereotype.Service;

@Service
public class DirectBaseDnService {

    private final LdapName base;

    public DirectBaseDnService(
            BaseLdapPathContextSource contextSource) {

        this.base = (LdapName)
                contextSource.getBaseLdapName().clone();
    }

    public LdapName fullPersonDn(String uid) {
        return (LdapName) LdapNameBuilder
                .newInstance(base)
                .add("ou", "people")
                .add("uid", uid)
                .build();
    }
}
~~~

Trong ví dụ, `LdapContextSource` thường thực hiện interface `BaseLdapPathContextSource`. Cách này có thể phù hợp khi dependency đã rõ và service không cần interface aware. Cần **giới hạn/validate UID**, kiểm soát OU và đảm bảo loại context source thực tế đúng với interface; ví dụ rút gọn trên tập trung vào cách lấy base.

### So sánh hai phương án hiện đại

| Tiêu chí | `BaseLdapNameAware` + post-processor | `BaseLdapPathContextSource.getBaseLdapName()` |
|---|---|---|
| Nhận base | Setter được framework gọi sau khi tạo bean | Constructor hoặc phương thức của service |
| Cần đăng ký post-processor | **Có** | Không |
| Service phụ thuộc trực tiếp vào ContextSource | Không | Có |
| Dễ tạo object để unit test | Gọi setter trong test | Truyền context source test/mock |
| Có nhiều context sources | Chỉ định nguồn base trong post-processor | `@Qualifier` hoặc wiring rõ nguồn đúng |
| Rủi ro chính | Quên post-processor, base chưa được inject | Inject nhầm context source của directory khác |

Không có phương án nào biến base DN thành nguồn quyết định quyền truy cập. Dù lấy base bằng setter hay getter, caller vẫn phải được giới hạn OU, `objectClass`, thao tác và ACL.

## 12. Nhiều ContextSource: chọn đúng base

Một ứng dụng đôi khi kết nối nhiều directory hoặc nhiều naming context:

~~~text
peopleContextSource:
  base=dc=people,dc=example,dc=org

partnersContextSource:
  base=dc=partners,dc=example,dc=net
~~~

Nếu có nhiều `BaseLdapPathSource` trong ApplicationContext, `BaseLdapPathBeanPostProcessor` có thể không biết chọn nguồn nào. Cần chỉ định tên context source thích hợp bằng phương thức `setBaseLdapPathSourceName(...)`.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ldap.core.support.BaseLdapPathBeanPostProcessor;

@Configuration(proxyBeanMethods = false)
public class PeopleBaseConfig {

    @Bean
    public static BaseLdapPathBeanPostProcessor
            baseLdapPathBeanPostProcessor() {

        BaseLdapPathBeanPostProcessor processor =
                new BaseLdapPathBeanPostProcessor();

        processor.setBaseLdapPathSourceName(
                "peopleContextSource");

        return processor;
    }
}
~~~

`peopleContextSource` phải là **tên bean thực tế** có cung cấp base LDAP, không phải một chuỗi tự nhận diện magic của Spring Boot. Cần xác định tên bean thông qua cấu hình Spring của ứng dụng.

**Điểm cần thiết kế thêm:** một post-processor được cấu hình chọn nguồn `peopleContextSource` có thể cung cấp base đó cho **mọi bean implements `BaseLdapNameAware`** mà nó xử lý. Nếu một ứng dụng đồng thời có nhiều service cần base từ **nhiều directory khác nhau**, một nguồn global không đủ để phân biệt ý định từng service. Khi đó nên dùng constructor injection kèm `@Qualifier`, hoặc các factory/service riêng gắn với từng context source.

### Ví dụ constructor injection có qualifier

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.ldap.core.support.BaseLdapPathContextSource;

public PartnerDnService(
        @Qualifier("partnersContextSource")
        BaseLdapPathContextSource partnerContext) {

    this.base = (LdapName)
            partnerContext.getBaseLdapName().clone();
}
~~~

Đây là **đoạn constructor minh họa** trong class `PartnerDnService` có field `private final LdapName base;`, cần thêm import `LdapName` và các method thực tế khi triển khai. Khi có nhiều `LdapTemplate`, phải đảm bảo **base dùng để xây DN** đến từ chính `ContextSource` mà template của nghiệp vụ đó sử dụng, không phải chỉ từ một bean có tên gần giống.

## 13. Base rỗng, base thay đổi và vùng dữ liệu khác nhau

Không phải cấu hình nào cũng có base cố định.

### Trường hợp base rỗng

Nếu `ContextSource` được cấu hình không có base, `getBaseLdapName()` trả một `LdapName` rỗng. Khi đó:

~~~text
base = ""
relativePersonDn("lan") = uid=lan,ou=people
absolutePersonDn("lan") = uid=lan,ou=people
~~~

Chú ý “absolute” ở đây chỉ là tên được ghép từ `base + relativeDN` của ứng dụng. Nếu directory thực tế có naming context `dc=example,dc=org` và yêu cầu DN dưới đó, phải cấu hình base/nhánh đúng; không mặc định chuỗi `uid=lan,ou=people` là DN đầy đủ của entry production.

### Thay đổi base giữa các môi trường

Ví dụ:

~~~text
Dev:  dc=dev,dc=example,dc=org
Test: dc=test,dc=example,dc=org
Prod: dc=example,dc=org
~~~

Nếu hardcode `dc=example,dc=org` vào `member` hoặc code dựng DN, ứng dụng trong môi trường test có thể ghi tham chiếu tới một naming context **khác**. Dùng `BaseLdapNameAware` hoặc getter của context source giúp service lấy base hiệu lực theo môi trường, giảm một loại cấu hình trùng lặp.

Nhưng nếu ứng dụng nhận nhiều directory hoặc tenant có base khác nhau **trong cùng một process**, một field base cố định lấy khi bean khởi tạo không thể đại diện cho mọi request. Cần chọn context source và base theo tenant trong thiết kế, không cố thay setter trên singleton từ các thread/request khác nhau.

### Refresh cấu hình khi đang chạy

`setBaseLdapPath(...)` thường được post-processor gọi trong quá trình khởi tạo bean, **không phải kênh cập nhật base liên tục**. Nếu cấu hình base hoặc topology đổi sau khi ứng dụng khởi động, phải điều phối refresh/recreate bean và các pool/template liên quan hoặc restart theo chính sách triển khai. Thay chuỗi config ở secret manager không tự cập nhật `LdapName` trong một singleton đã khởi tạo.

## 14. LdapRepository, @Entry và base path

Spring Data LDAP cung cấp ODM với `@Entry` và repository:

~~~java
@Entry(
    base = "ou=people",
    objectClasses = { "top", "person",
            "organizationalPerson", "inetOrgPerson" }
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

    // Constructor/getter/setter phù hợp.
}
~~~

Ở đây:

- `spring.ldap.base` đặt **gốc của ContextSource**, ví dụ `dc=example,dc=org`.
- `@Entry(base="ou=people")` mô tả nhánh entity trong phạm vi context base.
- `@Id` biểu diễn DN của entry theo cơ chế ODM.
- `LdapRepository<PersonEntry>` hoạt động dựa trên cấu hình repository và context source tương ứng.

Không “đánh đồng” base của `@Entry` và base của `ContextSource`. Trường hợp ví dụ, full DN của person là:

~~~text
uid=lan,ou=people,dc=example,dc=org
         ^ @Entry   ^ ContextSource base
~~~

Nếu entry cần giá trị `member` là full DN, phải biết cả **nhánh của entry** và **context base**, không chỉ gọi `getBaseLdapName()` rồi bỏ qua `ou=people`.

### Khi nào repository đủ, khi nào cần LdapTemplate?

Repository phù hợp để đọc/ghi entity theo mapping ODM đã thiết kế. `LdapTemplate` thường tiện hơn khi cần sửa một giá trị trong attribute đa trị, ghi trực tiếp `member`, chỉ tải vài thuộc tính hoặc điều khiển DN chính xác.

Không sử dụng `repository.save(...)` trên entity chỉ được nạp một phần rồi kỳ vọng tất cả các thuộc tính khác luôn được giữ nguyên. Khi làm việc với `member` hoặc `telephoneNumber`, dùng thao tác `ModificationItem` có chủ đích và kiểm thử dữ liệu nhiều giá trị.

## 15. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng khắc phục |
|---|---|---|
| `baseLdapPath == null` trong service | Quên `BaseLdapPathBeanPostProcessor` hoặc tự `new` service | Đăng ký post-processor, dùng Spring-managed bean hoặc inject context source trực tiếp |
| `ClassCastException` với kiểu base | Nhầm `DistinguishedName` và `LdapName` | Dùng `BaseLdapNameAware` cùng `LdapName` |
| `NoSuchObject (32)` khi lookup | Truyền full DN vào API mong relative DN; base lặp | Kiểm tra DN hiệu lực và cách `ContextSource` áp dụng base |
| Group không nhận thành viên | `member` lưu DN tương đối thiếu hậu tố | Lấy full DN từ base + relativeDN |
| Group thêm thành viên báo lỗi | Giá trị trùng, ACL, DN không hợp lệ hoặc group sai schema | Kiểm tra `member`, `groupOfNames`, quyền và mã LDAP |
| Cấu hình dev chạy nhưng test sai | Base bị hardcode ở service | Đọc base hiệu lực từ context source |
| Có nhiều LDAP sources, lấy nhầm base | Post-processor không được chọn đúng nguồn | Cấu hình `setBaseLdapPathSourceName` hoặc `@Qualifier` |
| Unit test pass nhưng integration fail | Unit test chỉ so chuỗi DN, không kiểm tra server | Test đọc/Modify trên directory thật độc lập |
| Full DN có hai hậu tố `dc=...` | Nối base hai lần | Phân biệt relative/full DN, test chuỗi kết quả |
| Lỗi tên chứa dấu phẩy hoặc ký tự đặc biệt | Ghép DN từ chuỗi thô | `LdapNameBuilder.add(attribute, value)` |
| Lỗi khi đổi OU hoặc rename | DN tham chiếu trong group không tự cập nhật | Dùng quy trình đổi DN và cập nhật tham chiếu |
| Service lấy base mới nhưng template dùng base cũ | Refresh cấu hình không đồng bộ | Recreate context/template/service nhất quán |

**Chẩn đoán theo thứ tự:** xác minh `spring.ldap.base` → xác minh nguồn `BaseLdapPathSource` → xác minh tên và kiểu DN mà method đang sử dụng → xác minh objectClass/ACL → thử với directory test. Tránh bắt mọi ngoại lệ và coi `NoSuchObject` luôn nghĩa là entry không tồn tại.

## 16. Kiểm thử đơn vị cho việc ghép DN

Unit test quan trọng nhất là chứng minh cấu trúc **base + DN tương đối** đúng, không nối trùng và không phụ thuộc môi trường.

~~~java
import javax.naming.Name;
import javax.naming.ldap.LdapName;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class PersonDnServiceTest {

    @Test
    void combinesBaseAndRelativeDnExactlyOnce() throws Exception {
        PersonDnService service = new PersonDnService();
        service.setBaseLdapPath(
                new LdapName("dc=example,dc=org"));

        Name relative = service.relativePersonDn("lan");
        Name absolute = service.absolutePersonDn("lan");

        assertEquals(
                new LdapName("uid=lan,ou=people"),
                relative);

        assertEquals(
                new LdapName(
                        "uid=lan,ou=people,dc=example,dc=org"),
                absolute);
    }

    @Test
    void rejectsInvalidUid() throws Exception {
        PersonDnService service = new PersonDnService();
        service.setBaseLdapPath(
                new LdapName("dc=example,dc=org"));

        assertThrows(
                IllegalArgumentException.class,
                () -> service.absolutePersonDn("lan,ou=admins"));
    }

    @Test
    void failsFastWhenBaseWasNotInjected() {
        PersonDnService service = new PersonDnService();

        assertThrows(
                IllegalStateException.class,
                () -> service.absolutePersonDn("lan"));
    }

    @Test
    void usesTestEnvironmentBase() throws Exception {
        PersonDnService service = new PersonDnService();
        service.setBaseLdapPath(
                new LdapName("dc=test,dc=example,dc=org"));

        assertEquals(
                new LdapName(
                    "uid=lan,ou=people,dc=test,dc=example,dc=org"),
                service.absolutePersonDn("lan"));
    }
}
~~~

`LdapName.equals(...)` so sánh cấu trúc tên theo cơ chế JNDI, không phụ thuộc vào phép nối chuỗi tự viết. Bài test không kết nối LDAP và chỉ xác minh composition/validation trong Java, **không chứng minh entry tồn tại, server cho phép DN, hay group membership đã được cập nhật**.

Nếu ứng dụng hỗ trợ UID có dấu phẩy hoặc Unicode hợp lệ, nên bổ sung test round-trip cho escaping với `LdapNameBuilder`. Ví dụ đang dùng regex hẹp để tách biệt kiểm tra policy với chức năng encode RDN.

## 17. Kiểm thử tích hợp: bean injection và group membership

Một bộ integration test nên xác minh **cả base injection và thao tác LDAP thật**. Bố trí môi trường:

~~~text
dc=test,dc=example,dc=org
├── ou=people
│   └── uid=lan
└── ou=groups
    └── cn=developers
~~~

Dữ liệu cần có:

- User `uid=lan` với `objectClass: inetOrgPerson` và các thuộc tính MUST `cn`/`sn`.
- Group `cn=developers` với `objectClass: groupOfNames` và ít nhất một `member` hợp lệ theo schema.
- `ContextSource` cấu hình base `dc=test,dc=example,dc=org` và bind account có ACL cần thiết.
- `BaseLdapPathBeanPostProcessor` đã đăng ký trong Spring context.

### Kiểm tra base đã được tiêm cho Spring bean

~~~java
import javax.naming.ldap.LdapName;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest
@ActiveProfiles("test")
class BasePathInjectionIntegrationTest {

    @Autowired
    private PersonDnService personDnService;

    @Test
    void buildsFullMemberDnFromConfiguredBase()
            throws Exception {

        assertEquals(
                new LdapName(
                    "uid=lan,ou=people,dc=test,dc=example,dc=org"),
                personDnService.absolutePersonDn("lan"));
    }
}
~~~

Test này yêu cầu bean được Spring quản lý và profile test dùng base đúng. Nếu Spring context có nhiều context source, cần chỉ định nguồn phù hợp hoặc đổi cách inject trực tiếp như mục 12.

### Kiểm tra member thực sự được ghi

Khi chạy `GroupMembershipService.addMember("developers", "lan")`, dùng `LdapTemplate.lookup(...)` trên DN **tương đối** của group để đọc `member` và xác nhận có **DN đầy đủ**. Nếu group đã có thành viên từ fixture khác, kiểm tra rằng những giá trị đó vẫn tồn tại; thao tác thêm một giá trị không được biến thành REPLACE toàn bộ attribute.

Một ma trận kiểm thử bổ sung:

| Kịch bản | Đầu vào | Kết quả mong đợi |
|---|---|---|
| Base đơn | Chỉ một `LdapContextSource` | Injection đúng |
| Không đăng ký post-processor | Service implements `BaseLdapNameAware` | Base không tự xuất hiện; fail fast theo code |
| Nhiều base | Hai context sources | Chọn rõ nguồn đúng |
| Base rỗng | Không cấu hình base | Chính sách DN được áp dụng có chủ đích |
| Relative DN | `uid=lan,ou=people` | `LdapTemplate.lookup` tìm đúng entry trong base |
| Full DN làm `member` | DN có base đúng một lần | Server chấp nhận giá trị theo schema/ACL |
| Thêm member trùng | Giá trị đã tồn tại | Lỗi/response idempotent theo hợp đồng |
| Xóa member cuối | `groupOfNames` còn một member | Server có thể từ chối vì MUST |
| DN đã rename | DN thành viên thay đổi | Cần cập nhật group references theo cơ chế được chọn |
| Thiếu ACL | Bind account không được sửa group | Operation thất bại, không nới quyền tự động |

**Không chạy các bài Add/Remove trên directory production.** Với môi trường staging, dùng fixture và credential tách biệt; chỉ dùng LDAPS/StartTLS với kiểm tra chứng chỉ và hạn chế quyền.

## 18. An toàn dữ liệu và ranh giới bảo mật

Việc lấy base DN không phải một cơ chế phân quyền. Một service có thể tạo DN nằm trong nhánh `ou=admins` nếu nó nhận OU từ client tùy ý, dù base vẫn đúng. Vì vậy cần:

1. **Cố định hoặc allowlist nhánh hợp lệ.** Ví dụ `ou=people` cho người dùng và `ou=groups` cho nhóm; đừng để request chọn DN tuyệt đối tùy ý.
2. **Dùng DN builder.** Không ghép dấu phẩy hoặc dấu bằng từ input không được kiểm soát.
3. **Đối chiếu ACL.** Service account chỉ nên có quyền cần cho thao tác trên OU tương ứng. Việc `LdapTemplate` dùng DN hợp lệ không khiến thao tác vượt qua ACL.
4. **Giới hạn dữ liệu API trả ra.** Full DN có thể tiết lộ cấu trúc tổ chức/OU; chỉ trả khi hợp đồng thật sự cần và caller được phép xem.
5. **Không log bí mật.** Đừng ghi bind password hay raw `Attributes` nhạy cảm trong trace. DN và UID cũng có thể là thông tin cá nhân, cần bảo vệ theo chính sách.
6. **Bảo vệ đường truyền.** Bind và thao tác dữ liệu qua LDAPS hoặc StartTLS có xác minh TLS.
7. **Xác nhận entry tồn tại khi cần.** Tạo chuỗi full DN không chứng minh user/group đang có trong directory; nếu nghiệp vụ đòi tham chiếu hợp lệ, dùng lookup/scope/ACL tương ứng.
8. **Không tự thay đổi base trong singleton theo request.** Nếu có nhiều tenant, dùng một context/factory rõ ràng cho từng vùng dữ liệu hoặc cơ chế routing được kiểm thử.
9. **Không dùng cấu hình base rỗng để vượt giới hạn phạm vi.** Phải chọn directory naming context và search scope theo yêu cầu nghiệp vụ.

Khi kết hợp Spring Security LDAP, hãy phân biệt **bind DN của tài khoản dịch vụ** với DN của người dùng cần xác thực. Full DN được tạo để lưu `member` không tự cấp quyền hay chứng minh người dùng đã được xác thực.

## 19. Bài tập thực hành

**Bối cảnh:** một ứng dụng Spring Data LDAP lưu người dùng ở `ou=people` và nhóm ở `ou=groups`, với `ContextSource` base khác nhau ở dev/test/prod. Nhóm phát triển phải thêm nhân viên vào `groupOfNames` nhưng không được hardcode hậu tố `dc=...`.

Hãy thực hiện:

1. Cấu hình `spring.ldap.base` qua môi trường, dùng LDAP test có base `dc=test,dc=example,dc=org`.
2. Tạo bean `PersonDnService` implements `BaseLdapNameAware`.
3. Đăng ký `BaseLdapPathBeanPostProcessor`; giải thích vì sao chỉ implements interface chưa đủ.
4. Viết `relativePersonDn("lan")` và `absolutePersonDn("lan")` bằng `LdapNameBuilder`; so sánh kết quả.
5. Viết unit test cho base dev/test/prod khác nhau và cho trường hợp chưa được injection.
6. Dùng `LdapTemplate.lookup(relativeDn, ...)` để đọc user từ directory test.
7. Dùng `GroupMembershipService.addMember(...)` ghi full DN vào `member`, đọc lại và kiểm tra các giá trị thành viên khác không bị mất.
8. Thử lỗi cố tình truyền full DN cho thao tác kỳ vọng relative DN; quan sát cách API/provider phản hồi và giải thích vì sao cần hợp đồng rõ ràng.
9. Tạo hai `ContextSource` trong Spring test context, chỉ định `baseLdapPathSourceName`; giải thích tại sao singleton post-processor không phù hợp khi mỗi service cần base khác nhau.
10. Thay triển khai bằng constructor injection `BaseLdapPathContextSource` và so sánh ưu/nhược điểm.
11. Thêm test DN có ký tự đặc biệt với `LdapNameBuilder`, phân biệt escaping DN và escaping LDAP filter.
12. Thực hiện xóa một giá trị `member` trong directory test, kiểm tra chính sách `groupOfNames` không cho bỏ thuộc tính MUST.
13. Trình bày khi nào API nên trả full DN, khi nào nên trả UID ổn định, và rủi ro nếu DN thay đổi do rename/move.

**Tiêu chí hoàn thành:** người học nhận được base từ đúng `ContextSource`, phân biệt relative/full DN và dùng full DN đúng chỗ trong `member`, không lặp base, không ghép chuỗi DN/filter không an toàn và kiểm chứng thao tác với directory test.

## 20. Tổng kết và tài liệu tham khảo

**`BaseLdapPathAware` là API lịch sử cho phép Spring đưa base DN vào bean nhưng đã deprecated; ứng dụng hiện đại nên dùng `BaseLdapNameAware` với `LdapName`.** Để cơ chế tự injection hoạt động, bean phải được Spring quản lý và `BaseLdapPathBeanPostProcessor` phải được đăng ký. Nếu thích wiring tường minh, có thể lấy base qua `BaseLdapPathContextSource.getBaseLdapName()`.

Trong phần lớn thao tác `LdapTemplate`, hãy **giữ DN tương đối** vì `ContextSource` đã biết base. Chỉ tạo **DN đầy đủ** khi dữ liệu hoặc hệ thống ngoài yêu cầu, chẳng hạn `member` trong `groupOfNames`. Dùng `LdapNameBuilder`, kiểm soát OU, định danh, ACL và schema; tránh lặp base hoặc coi full DN là quyền truy cập.

Tài liệu tham khảo chính thức:

- [Spring LDAP — Configuration / Obtaining a Reference to the Base LDAP Path](https://docs.spring.io/spring-ldap/reference/configuration.html): giải thích relative DN, `BaseLdapNameAware` và `BaseLdapPathBeanPostProcessor`.
- [BaseLdapPathAware API (deprecated)](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/support/BaseLdapPathAware.html): interface cũ dùng `DistinguishedName`.
- [BaseLdapNameAware API](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/core/support/BaseLdapNameAware.html): `setBaseLdapPath(LdapName)`.
- [BaseLdapPathSource API](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/support/BaseLdapPathSource.html): `getBaseLdapName()` và các getter khác.
- [BaseLdapPathContextSource API](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/core/support/BaseLdapPathContextSource.html): context source cung cấp base.
- [Spring Data LDAP Reference](https://docs.spring.io/spring-data/ldap/reference/): ODM, `@Entry`, `LdapRepository` và giới hạn ánh xạ.
- [RFC 4514 — String Representation of Distinguished Names](https://www.rfc-editor.org/rfc/rfc4514): cách biểu diễn/escaping DN.
- [RFC 4515 — LDAP Search Filters](https://www.rfc-editor.org/rfc/rfc4515): escaping filter, phân biệt với DN.
- [RFC 4511 — LDAP Protocol](https://www.rfc-editor.org/rfc/rfc4511): Search, Modify và cách định danh entry.
