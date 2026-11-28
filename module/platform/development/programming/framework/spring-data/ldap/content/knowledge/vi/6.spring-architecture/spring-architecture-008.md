# Chuyển NamingException sang hệ ngoại lệ của Spring LDAP

Java Naming and Directory Interface (JNDI) dùng `javax.naming.NamingException` để báo lỗi khi thao tác với directory. Đây là **checked exception**: mã Java gọi trực tiếp `DirContext.lookup`, `search` hoặc `modifyAttributes` phải xử lý hoặc khai báo ngoại lệ. Khi dùng Spring LDAP, ứng dụng thường thao tác qua `LdapTemplate` hoặc repository; framework chuyển các lỗi JNDI sang **hệ ngoại lệ runtime riêng của Spring LDAP** để mã nghiệp vụ không phải lặp lại các khối `try/catch` cho từng thao tác.

API chuyển đổi chính là:

~~~java
org.springframework.ldap.support.LdapUtils
        .convertLdapException(javax.naming.NamingException)
~~~

Kết quả là một ngoại lệ thuộc package `org.springframework.ldap`, thường là lớp tương ứng với loại JNDI ban đầu; nếu không có lớp chuyên biệt phù hợp, Spring LDAP dùng `UncategorizedLdapException`. Các ngoại lệ Spring LDAP này là **unchecked**, có giữ nguyên nguyên nhân gốc để chẩn đoán.

Có một điểm rất dễ nhầm: `org.springframework.ldap.NamingException` kế thừa `NestedRuntimeException`, **không kế thừa `org.springframework.dao.DataAccessException`**. Vì vậy, không nên mặc định một `catch (DataAccessException)` sẽ bắt được mọi lỗi LDAP.

Bài thuộc chương **Kiến trúc Spring** của mô-đun `SPRING_DATA_LDAP`. Ta sẽ theo dõi một lỗi từ JNDI tới Spring LDAP, tìm hiểu exception hierarchy, cách `LdapTemplate` tự dịch lỗi, khi nào phải tự gọi `LdapUtils.convertLdapException`, rồi xây lớp service và HTTP error handler có ngữ nghĩa rõ ràng. Các ví dụ dùng DN, `objectClass`, schema, repository/`LdapTemplate`, CRUD, filter an toàn và directory test để đặt ngoại lệ vào đúng bối cảnh.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt `javax.naming.NamingException` với `org.springframework.ldap.NamingException`.
2. Giải thích vì sao JNDI dùng checked exception còn Spring LDAP cung cấp unchecked exception hierarchy.
3. Mô tả cách `LdapUtils.convertLdapException` chuyển loại JNDI sang loại Spring LDAP tương ứng.
4. Nhận diện các lớp thường gặp như `NameNotFoundException`, `NameAlreadyBoundException`, `AuthenticationException`, `CommunicationException` và `SchemaViolationException`.
5. Phân biệt Spring LDAP `NamingException` với Spring Framework `DataAccessException`.
6. Biết thao tác nào qua `LdapTemplate`/repository đã được dịch ngoại lệ và thao tác JNDI trực tiếp nào cần dịch thủ công.
7. Giữ lại cause/root cause, không phân loại lỗi bằng cách so sánh chuỗi thông báo.
8. Xử lý lỗi theo ngữ nghĩa nghiệp vụ: không tìm thấy, trùng DN, sai dữ liệu schema, thiếu quyền, directory tạm thời không khả dụng.
9. Thiết kế `@RestControllerAdvice` không làm lộ DN, Bind DN, filter, credential hoặc diagnostic nội bộ.
10. Viết unit test cho exception conversion và integration test với LDAP server.
11. Hiểu ảnh hưởng của unchecked exception tới transaction rollback và giới hạn của transaction trên LDAP.

## 2. Bối cảnh: cùng một lỗi nhưng hai API khác nhau

Giả sử directory có cây:

~~~text
dc=example,dc=org
├── ou=people
│   ├── uid=lan
│   └── uid=minh
├── ou=groups
│   └── cn=engineering
└── ou=service
    └── cn=svc-directory-reader
~~~

Entry Lan:

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

Giả sử ứng dụng muốn tra cứu:

~~~text
uid=unknown,ou=people,dc=example,dc=org
~~~

Với JNDI thuần:

~~~java
DirContext ctx = ...;
try {
    Object entry = ctx.lookup(
            "uid=unknown,ou=people,dc=example,dc=org");
} catch (javax.naming.NamingException ex) {
    // JNDI yêu cầu xử lý checked exception.
}
~~~

Với Spring LDAP:

~~~java
Object entry = ldapTemplate.lookup(
        "uid=unknown,ou=people",
        mapper);
~~~

Nếu DN không tồn tại, Spring LDAP có thể ném `org.springframework.ldap.NameNotFoundException`. Mã gọi không cần khai báo `throws javax.naming.NamingException`, nhưng vẫn phải quyết định lỗi này có phải “không có dữ liệu” hợp lệ trong use case hay là lỗi cần truyền lên.

**Việc đổi kiểu exception không làm directory tự xử lý lỗi.** Nó chuẩn hóa cách Java biểu diễn lỗi để các tầng service/API có thể phân loại và xử lý nhất quán.

## 3. Ba tầng cần phân biệt

~~~mermaid
flowchart TD
    A["LDAP Server / JNDI provider"] --> B["javax.naming.NamingException<br/>checked"]
    B --> C["Spring LDAP translation<br/>LdapUtils.convertLdapException"]
    C --> D["org.springframework.ldap.*<br/>unchecked hierarchy"]
    D --> E["Application service<br/>domain outcome / domain exception"]
    E --> F["REST / message handler<br/>HTTP response an toàn"]
~~~

| Tầng | Ví dụ | Trách nhiệm |
| --- | --- | --- |
| JNDI/provider | `javax.naming.NameNotFoundException` | Biểu diễn lỗi theo API Java Naming. |
| Spring LDAP | `org.springframework.ldap.NameNotFoundException` | Ngoại lệ runtime chuyên biệt, giữ cause. |
| Service nghiệp vụ | `PersonNotFoundException` hoặc `DirectoryUnavailableException` | Chuyển lỗi kỹ thuật thành ngữ nghĩa của ứng dụng. |
| API | `404`, `409`, `503` | Trả kết quả phù hợp với hợp đồng HTTP, không lộ chi tiết directory. |

### 3.1. JNDI NamingException là checked exception

`javax.naming.NamingException` kế thừa `Exception`. Những thao tác JNDI trực tiếp thường khai báo `throws NamingException`:

- `Context.lookup` / `DirContext.lookup`.
- `DirContext.getAttributes`.
- `DirContext.search`.
- `DirContext.bind` / `rebind` / `unbind`.
- `DirContext.modifyAttributes`.
- `Context.rename`.

Khi gọi trực tiếp, Java yêu cầu bạn catch hoặc khai báo. Đây là cách JNDI buộc caller cân nhắc lỗi ở biên I/O với directory.

### 3.2. Spring LDAP NamingException là unchecked exception

`org.springframework.ldap.NamingException` là lớp cơ sở trong hệ ngoại lệ Spring LDAP. Nó kế thừa `org.springframework.core.NestedRuntimeException`, do đó là **runtime exception**.

Spring LDAP cung cấp các lớp con phản ánh nhiều lớp JNDI thường gặp. Mã dùng `LdapTemplate` không phải viết một `catch` chung cho mọi thao tác, nhưng vẫn có thể bắt các lớp cụ thể nếu use case cần.

### 3.3. Spring LDAP NamingException không phải DataAccessException

Hai nhánh này độc lập:

~~~text
java.lang.RuntimeException
└── org.springframework.core.NestedRuntimeException
    ├── org.springframework.ldap.NamingException
    │   ├── org.springframework.ldap.NameNotFoundException
    │   ├── org.springframework.ldap.CommunicationException
    │   └── ...
    └── org.springframework.dao.DataAccessException
        └── các lỗi truy cập dữ liệu thuộc hệ phân cấp Spring DAO
~~~

`DataAccessException` là lớp cơ sở trong hệ ngoại lệ truy cập dữ liệu của Spring Framework. Spring LDAP xây dựng một hierarchy riêng để phản ánh JNDI NamingException. **Đừng viết logic chỉ bắt `DataAccessException` rồi giả định nó bắt mọi lỗi do `LdapTemplate` phát sinh.**

Nếu một ứng dụng có adapter khác chủ động chuyển lỗi LDAP thành exception DAO/domain, đó là lựa chọn kiến trúc của ứng dụng và phải được thể hiện rõ bằng code.

## 4. Cấu trúc hệ ngoại lệ Spring LDAP

Hệ ngoại lệ Spring LDAP giữ quan hệ cha-con gần với JNDI để code có thể bắt theo mức cụ thể hoặc theo lớp cơ sở.

~~~mermaid
classDiagram
    class RuntimeException
    class NestedRuntimeException
    class SpringLdapNamingException
    class NamingSecurityException
    class LimitExceededException
    class LinkException
    RuntimeException <|-- NestedRuntimeException
    NestedRuntimeException <|-- SpringLdapNamingException
    SpringLdapNamingException <|-- NamingSecurityException
    SpringLdapNamingException <|-- LimitExceededException
    SpringLdapNamingException <|-- LinkException
    NamingSecurityException <|-- AuthenticationException
    NamingSecurityException <|-- AuthenticationNotSupportedException
    NamingSecurityException <|-- NoPermissionException
    LimitExceededException <|-- SizeLimitExceededException
    LimitExceededException <|-- TimeLimitExceededException
    LinkException <|-- LinkLoopException
    LinkException <|-- MalformedLinkException
~~~

Tên `SpringLdapNamingException` trong sơ đồ chỉ là nhãn rút gọn để phân biệt với JNDI; lớp Java thực tế tên `org.springframework.ldap.NamingException`.

### Các lớp thường gặp

| Spring LDAP exception | Ý nghĩa gần với JNDI | Ví dụ tình huống |
| --- | --- | --- |
| `NamingException` | Lớp cơ sở | Lỗi LDAP chưa được xử lý ở lớp cụ thể. |
| `NameNotFoundException` | `javax.naming.NameNotFoundException` | DN lookup không tồn tại. |
| `NameAlreadyBoundException` | `javax.naming.NameAlreadyBoundException` | Add entry vào DN đã có. |
| `AuthenticationException` | `javax.naming.AuthenticationException` | Bind thất bại theo cơ chế provider. |
| `AuthenticationNotSupportedException` | `javax.naming.AuthenticationNotSupportedException` | Server/provider không hỗ trợ kiểu xác thực yêu cầu. |
| `NoPermissionException` | `javax.naming.NoPermissionException` | Không đủ quyền theo kết quả JNDI được provider ánh xạ. |
| `CommunicationException` | `javax.naming.CommunicationException` | Lỗi trao đổi mạng với directory. |
| `ServiceUnavailableException` | `javax.naming.ServiceUnavailableException` | Directory/service không khả dụng. |
| `InvalidNameException` | `javax.naming.InvalidNameException` | DN không hợp lệ theo parser/provider. |
| `InvalidSearchFilterException` | `javax.naming.directory.InvalidSearchFilterException` | Filter không hợp lệ. |
| `SchemaViolationException` | `javax.naming.directory.SchemaViolationException` | Entry/attribute vi phạm schema. |
| `InvalidAttributeValueException` | `javax.naming.directory.InvalidAttributeValueException` | Giá trị attribute không hợp lệ. |
| `NoSuchAttributeException` | `javax.naming.directory.NoSuchAttributeException` | Attribute được yêu cầu không tồn tại theo kết quả provider. |
| `SizeLimitExceededException` | `javax.naming.SizeLimitExceededException` | Search vượt giới hạn số entry. |
| `TimeLimitExceededException` | `javax.naming.TimeLimitExceededException` | Search vượt giới hạn thời gian. |
| `PartialResultException` | `javax.naming.PartialResultException` | Chỉ nhận được một phần kết quả, thường liên quan referral/topology. |
| `LdapReferralException` / `ReferralException` | Referral JNDI/LDAP | Server trả referral cần chính sách xử lý. |
| `UncategorizedLdapException` | Không tìm thấy lớp chuyên biệt | JNDI NamingException không có mapping cụ thể. |

Bảng là ánh xạ theo **loại exception Java**, không phải bảng chuyển đổi cố định từ mọi LDAP result code sang một lớp Java duy nhất. Cách provider diễn giải response phụ thuộc JNDI implementation và directory server.

## 5. LdapUtils.convertLdapException làm gì?

Phương thức:

~~~java
import javax.naming.NamingException;
import org.springframework.ldap.support.LdapUtils;

org.springframework.ldap.NamingException converted =
        LdapUtils.convertLdapException(original);
~~~

nhận một `javax.naming.NamingException` và trả về **Spring LDAP runtime equivalent**.

Về ý nghĩa:

1. Kiểm tra loại exception JNDI gốc.
2. Chọn lớp con Spring LDAP tương ứng nếu có mapping.
3. Tạo exception Spring LDAP và giữ exception JNDI làm cause.
4. Nếu không có mapping chuyên biệt, dùng `UncategorizedLdapException`.

### Ví dụ mapping

~~~java
javax.naming.NameNotFoundException original =
        new javax.naming.NameNotFoundException(
                "uid=missing,ou=people");

org.springframework.ldap.NamingException translated =
        LdapUtils.convertLdapException(original);

assert translated
        instanceof org.springframework.ldap.NameNotFoundException;
assert translated.getCause() == original;
~~~

Không phải mọi thông tin LDAP server trả về đều được chuyển thành một field chuẩn có thể đọc theo cùng cách. Đừng tự parse `getMessage()` để tìm chuỗi `"49"`, `"50"` hoặc `"32"`.

### Giữ nguyên cause

`NestedRuntimeException` giữ cause và cung cấp tiện ích truy cập nguyên nhân gốc. Tùy root cause, `org.springframework.ldap.NamingException` cũng có các method như `getExplanation()`, `getRemainingName()`, `getResolvedName()` và `getResolvedObj()`.

Những thông tin này hữu ích cho chẩn đoán nội bộ, nhưng có thể chứa DN hoặc dữ liệu directory. Không đưa chúng thẳng vào response công khai.

## 6. LdapTemplate đã dịch ngoại lệ hay chưa?

**Các thao tác qua `LdapTemplate` được thiết kế để xử lý plumbing JNDI và chuyển NamingException sang hierarchy Spring LDAP.** Caller thường nhận exception runtime của Spring LDAP, không phải checked JNDI exception.

Ví dụ:

~~~java
import javax.naming.Name;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

public DirectoryPerson findByUid(
        LdapTemplate ldapTemplate, String uid) {

    Name dn = LdapNameBuilder.newInstance("ou=people")
            .add("uid", uid)
            .build();

    return ldapTemplate.lookup(
            dn,
            attrs -> new DirectoryPerson(
                    (String) attrs.get("uid").get(),
                    (String) attrs.get("cn").get()
            )
    );
}
~~~

Đây là lookup qua `LdapTemplate`; nếu entry không tồn tại, lỗi sẽ được biểu diễn bằng Spring LDAP exception tương ứng. Mã không cần catch `javax.naming.NamingException`.

### Vì sao LdapTemplate có thể làm được?

`LdapTemplate` bao quanh các bước thường lặp lại:

- Lấy context từ `ContextSource`.
- Thực hiện thao tác JNDI.
- Duyệt và đóng `NamingEnumeration` khi Search.
- Đóng context theo lifecycle.
- Chuyển exception JNDI gặp trong quá trình thao tác bằng `LdapUtils.convertLdapException`.

Đây là một lý do quan trọng để dùng `LdapTemplate` cho code truy cập LDAP thông thường.

### Search và Lookup không có cùng semantics “không tìm thấy”

Một điểm dễ bỏ qua trong Javadoc `LdapOperations`:

- `lookup(dn, mapper)` tra cứu **một DN cụ thể**. DN không tồn tại thường được biểu diễn bằng `NameNotFoundException` của Spring LDAP.
- Một số overload `search(...)` coi `NameNotFoundException` ở search base là **không có kết quả**, trả danh sách rỗng thay vì ném lỗi.

Vì thế, không dùng cùng một handler “NameNotFound = 404” cho mọi thao tác mà không xét semantics. Search trả `[]` có thể là kết quả bình thường; lookup một DN bắt buộc tồn tại có thể cần chuyển thành “person not found”.

## 7. Khi gọi JNDI trực tiếp, phải dịch exception thủ công

Có những trường hợp bạn cần thao tác trực tiếp với `DirContext`: sử dụng JNDI API đặc thù, request/response control, hoặc tích hợp một thư viện chưa có adapter Spring LDAP.

Trong trường hợp đó, lời gọi JNDI vẫn ném checked `javax.naming.NamingException`. Bạn có thể chuyển nó sang hierarchy Spring LDAP ở biên adapter.

~~~java
package com.example.directory.adapter;

import javax.naming.NamingException;
import javax.naming.directory.DirContext;

import org.springframework.ldap.core.ContextSource;
import org.springframework.ldap.support.LdapUtils;

public class RawJndiDirectoryAdapter {

    private final ContextSource contextSource;

    public RawJndiDirectoryAdapter(ContextSource contextSource) {
        this.contextSource = contextSource;
    }

    public Object lookup(String relativeDn) {
        DirContext context = null;
        try {
            context = contextSource.getReadOnlyContext();
            return context.lookup(relativeDn);
        } catch (NamingException ex) {
            // Chuyển JNDI checked exception thành Spring LDAP runtime.
            throw LdapUtils.convertLdapException(ex);
        } finally {
            // Giải phóng context dù thành công hay thất bại.
            LdapUtils.closeContext(context);
        }
    }
}
~~~

Trong ví dụ:

- `ContextSource` là abstraction của Spring LDAP.
- `getReadOnlyContext()` đã dùng cấu hình Bind mặc định của source.
- `context.lookup(...)` là JNDI API nên ném `javax.naming.NamingException`.
- `convertLdapException` chuyển lỗi từ lời gọi JNDI sang Spring LDAP.
- `closeContext` giải phóng context trong mọi đường đi.

Nếu `getReadOnlyContext()` thất bại, nó đã có thể ném Spring LDAP runtime exception từ ContextSource; catch JNDI ở trên chỉ bắt checked exception do lời gọi JNDI trực tiếp. Không cần bắt rồi chuyển đổi lại một Spring LDAP exception đã được dịch.

### Không chuyển mọi exception thành UncategorizedLdapException

Không nên làm:

~~~java
try {
    return context.lookup(dn);
} catch (Exception ex) {
    throw new UncategorizedLdapException(ex);
}
~~~

Cách đó xóa mất khác biệt giữa:

- DN không tồn tại.
- Bind thất bại.
- Lỗi TLS/mạng.
- Thiếu quyền.
- Schema không hợp lệ.
- Lỗi lập trình như NullPointerException.

Chỉ chuyển **JNDI NamingException** bằng phương thức được thiết kế cho việc đó. Lỗi lập trình hoặc lỗi nghiệp vụ cần giữ nguyên loại và xử lý đúng tầng.

## 8. Khi nào không cần tự gọi convertLdapException?

| Cách truy cập | Caller nhận gì? | Có cần gọi converter thủ công? |
| --- | --- | --- |
| `LdapTemplate.lookup/search/bind/modifyAttributes` | Spring LDAP runtime exceptions | **Không**. |
| Spring Data LDAP repository dùng Spring LDAP operations | Thường là lỗi từ Spring LDAP hierarchy theo đường thực thi | Thông thường **không**. Kiểm tra API/version nếu adapter khác bọc lỗi. |
| `ContextSource.getReadOnlyContext()` | Spring LDAP exception khi source không tạo được context | **Không** chuyển lại. |
| `DirContext.lookup` gọi trực tiếp | JNDI checked exception | **Có** nếu muốn thống nhất về Spring LDAP tại biên adapter. |
| `DirContext.search` gọi trực tiếp | JNDI checked exception | **Có** nếu adapter của ứng dụng muốn dùng hierarchy Spring LDAP. |
| Một thư viện bên ngoài trả JNDI NamingException | Phụ thuộc hợp đồng thư viện | Chuyển tại adapter tích hợp nếu cần. |
| Một service đã ném domain exception | Domain exception của ứng dụng | Không chuyển thành Spring LDAP exception. |

### Repository không phải một “vùng miễn nhiễm lỗi”

Ví dụ:

~~~java
public interface DirectoryPersonRepository
        extends LdapRepository<DirectoryPerson> {
}
~~~

Repository giúp truy vấn và CRUD entity; nó không biến lỗi server thành kết quả thành công. Nếu một operation repository thất bại vì DN trùng, schema sai, ACL hoặc directory không khả dụng, lỗi vẫn phải được xử lý ở service/API.

Không nên viết một lớp catch chung cho toàn bộ `RuntimeException` chỉ vì repository không khai báo `throws NamingException`.

## 9. Đọc nguyên nhân gốc thay vì đọc chuỗi message

Một lỗi LDAP có thể đi qua nhiều lớp:

~~~text
HTTP Controller
    |
    v
Application Service
    |
    v
LdapTemplate
    |
    v
JNDI provider
    |
    v
LDAP server
~~~

Khi server trả lỗi, provider có thể tạo JNDI exception; Spring LDAP chuyển sang runtime wrapper; service có thể chuyển tiếp thành domain exception.

Ví dụ cấu trúc cause:

~~~text
org.springframework.ldap.NameAlreadyBoundException
  caused by:
javax.naming.NameAlreadyBoundException
  (provider diagnostic / server response)
~~~

Cách đọc an toàn:

~~~java
catch (org.springframework.ldap.NamingException ex) {
    Throwable root = ex.getMostSpecificCause();

    // Ghi nhận loại exception, operation và request ID.
    // Không log password, toàn bộ Attributes hoặc diagnostic
    // có thể chứa dữ liệu cá nhân.
    throw ex;
}
~~~

`getMostSpecificCause()` là tiện ích từ Spring exception base; nếu cần tương thích API cụ thể, `getCause()` cũng cho phép đi theo chuỗi nguyên nhân. Không parse chuỗi thông báo để suy ra mã LDAP vì provider có thể thay đổi nội dung hoặc ngôn ngữ.

### LDAP resultCode không phải Java exception type

LDAP protocol có resultCode như:

| Result code | Tên | Ngữ nghĩa |
| ---: | --- | --- |
| 0 | `success` | Operation thành công. |
| 32 | `noSuchObject` | Không tìm thấy entry/base được chỉ định. |
| 34 | `invalidDNSyntax` | DN không đúng cú pháp. |
| 49 | `invalidCredentials` | Bind credentials không hợp lệ theo server. |
| 50 | `insufficientAccessRights` | Không đủ quyền. |
| 65 | `objectClassViolation` | Entry vi phạm quy tắc objectClass/schema. |
| 68 | `entryAlreadyExists` | Entry có DN đã tồn tại. |
| 3 | `timeLimitExceeded` | Search vượt giới hạn thời gian. |
| 4 | `sizeLimitExceeded` | Search vượt giới hạn số entry. |
| 10 | `referral` | Server yêu cầu client xử lý referral. |
| 52 | `unavailable` | Directory không khả dụng. |

Đây là **mã của giao thức LDAP**. JNDI provider có trách nhiệm ánh xạ response thành exception Java; ánh xạ chính xác có thể khác nhau theo provider, thao tác và server. Vì vậy, bảng resultCode giúp hiểu ngữ nghĩa, không phải cam kết rằng mọi server sẽ ném cùng một lớp JNDI.

## 10. Ánh xạ Spring LDAP exception sang ngữ nghĩa nghiệp vụ

Một service nên tránh để controller phụ thuộc quá sâu vào JNDI hoặc Spring LDAP. Thay vào đó, adapter/service chuyển các trường hợp dự kiến thành kết quả/domain exception.

Ví dụ:

| Spring LDAP exception | Ý nghĩa trong service | Quyết định nghiệp vụ có thể phù hợp |
| --- | --- | --- |
| `NameNotFoundException` | DN không tồn tại | Trả Optional.empty khi lookup là tùy chọn; nếu bắt buộc, ném PersonNotFound. |
| `NameAlreadyBoundException` | DN đã được sử dụng | PersonAlreadyExists/Conflict. |
| `AuthenticationException` | Bind thất bại | Sai credential của người dùng hoặc lỗi credential dịch vụ, tùy context. |
| `NoPermissionException` | ACL từ chối thao tác | DirectoryAccessDenied hoặc lỗi cấu hình quyền. |
| `SchemaViolationException` | Entry không đáp ứng schema | Dữ liệu đầu vào không hợp lệ hoặc mapping lỗi. |
| `InvalidAttributeValueException` | Attribute value không hợp lệ | Validation/Domain error. |
| `CommunicationException` | Giao tiếp mạng lỗi | DirectoryUnavailable, retry có giới hạn nếu operation an toàn. |
| `ServiceUnavailableException` | Directory không sẵn sàng | DirectoryUnavailable. |
| `TimeLimitExceededException` | Search quá thời gian | DirectorySearchTimeout. |
| `SizeLimitExceededException` | Search bị giới hạn số entry | SearchIncomplete/TooBroad, không coi dữ liệu partial là đầy đủ. |
| `PartialResultException` | Chỉ có một phần kết quả | Kết quả incomplete, xử lý referral/topology. |
| `UncategorizedLdapException` | Lỗi JNDI chưa phân loại | Internal directory failure; giữ cause để điều tra. |

**Không ánh xạ máy móc mọi `AuthenticationException` thành HTTP 401.** Nếu lỗi xảy ra khi ứng dụng Bind bằng service account, đây có thể là lỗi cấu hình credential nội bộ, không phải người gọi HTTP nhập sai mật khẩu. Ngữ cảnh operation rất quan trọng.

## 11. Ví dụ service: biến lỗi kỹ thuật thành kết quả nghiệp vụ

`PersonDirectoryService.java`:

~~~java
package com.example.directory.service;

import java.util.Optional;

import org.springframework.ldap.NameNotFoundException;
import org.springframework.ldap.NameAlreadyBoundException;
import org.springframework.ldap.CommunicationException;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;
import org.springframework.stereotype.Service;

@Service
public class PersonDirectoryService {

    private final LdapTemplate ldapTemplate;

    public PersonDirectoryService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public Optional<PersonSummary> findByUid(String uid) {
        validateUid(uid);

        var dn = LdapNameBuilder.newInstance("ou=people")
                .add("uid", uid)
                .build();

        try {
            PersonSummary person = ldapTemplate.lookup(
                    dn,
                    attrs -> new PersonSummary(
                            (String) attrs.get("uid").get(),
                            (String) attrs.get("cn").get(),
                            (String) attrs.get("sn").get()
                    )
            );
            return Optional.of(person);
        } catch (NameNotFoundException missing) {
            // Lookup theo DN cụ thể: không tồn tại là trạng thái
            // có thể biểu diễn bằng Optional.empty().
            return Optional.empty();
        } catch (CommunicationException unavailable) {
            throw new DirectoryUnavailableException(
                    "Directory lookup is temporarily unavailable",
                    unavailable);
        }
    }

    public void create(PersonEntry entry) {
        try {
            ldapTemplate.bind(
                    entry.getDn(),
                    null,
                    entry.toAttributes());
        } catch (NameAlreadyBoundException duplicate) {
            throw new PersonAlreadyExistsException(
                    "The requested UID is already in use",
                    duplicate);
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

`PersonSummary`, `PersonEntry`, `DirectoryUnavailableException` và `PersonAlreadyExistsException` là các kiểu DTO/domain của ví dụ, cần khai báo theo mô hình ứng dụng. `entry.getDn()` phải được tạo bằng `LdapNameBuilder` từ UID đã validate; không nhận DN tùy ý từ HTTP.

### Điều cần lưu ý

- Chỉ bắt `NameNotFoundException` cho một lookup mà thiếu entry có nghĩa là “không có người dùng”.
- Search trả danh sách rỗng có thể là kết quả bình thường; không cần bắt `NameNotFoundException` nếu API Search đã xử lý base không tồn tại theo semantics riêng.
- `CommunicationException` có thể xảy ra do lỗi mạng; không đổi thành “user not found”.
- `NameAlreadyBoundException` khi tạo entry là xung đột nghiệp vụ, không phải lỗi server cần retry mù.
- Các lỗi không được bắt vẫn tiếp tục truyền dưới dạng Spring LDAP runtime exception.

## 12. REST error handler: không công khai diagnostic LDAP

Tầng web nên trả lỗi ổn định, không phụ thuộc nội dung message của JNDI provider.

`DirectoryExceptionHandler.java`:

~~~java
package com.example.directory.web;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

import com.example.directory.service.DirectoryUnavailableException;
import com.example.directory.service.PersonAlreadyExistsException;

@RestControllerAdvice
public class DirectoryExceptionHandler {

    public record ApiError(String code, String message) {}

    @ExceptionHandler(PersonAlreadyExistsException.class)
    public ResponseEntity<ApiError> duplicate() {
        return ResponseEntity.status(HttpStatus.CONFLICT).body(
                new ApiError(
                        "PERSON_ALREADY_EXISTS",
                        "The requested person already exists"));
    }

    @ExceptionHandler(DirectoryUnavailableException.class)
    public ResponseEntity<ApiError> unavailable() {
        return ResponseEntity.status(
                HttpStatus.SERVICE_UNAVAILABLE).body(
                new ApiError(
                        "DIRECTORY_UNAVAILABLE",
                        "Directory service is temporarily unavailable"));
    }

    @ExceptionHandler(IllegalArgumentException.class)
    public ResponseEntity<ApiError> invalidInput() {
        return ResponseEntity.badRequest().body(
                new ApiError(
                        "INVALID_REQUEST",
                        "The request parameters are invalid"));
    }
}
~~~

Các exception domain trong ví dụ:

~~~java
public class DirectoryUnavailableException extends RuntimeException {
    public DirectoryUnavailableException(String message, Throwable cause) {
        super(message, cause);
    }
}

public class PersonAlreadyExistsException extends RuntimeException {
    public PersonAlreadyExistsException(String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

Trong ứng dụng thật, có thể có handler chung cho domain errors. Chỉ thêm handler trực tiếp cho `org.springframework.ldap.*` khi muốn định nghĩa rõ policy toàn ứng dụng; không trả `ex.getMessage()` hoặc `ex.getExplanation()` ra ngoài.

### Gợi ý mã HTTP

| Ngữ nghĩa nghiệp vụ | HTTP có thể phù hợp | Ghi chú |
| --- | ---: | --- |
| Không tìm thấy person theo DN bắt buộc | 404 | Chỉ khi caller được phép biết đối tượng tồn tại/không tồn tại. |
| DN đã được sử dụng | 409 | Xung đột định danh. |
| Request/filter/DN không hợp lệ | 400 | Validation ở application boundary. |
| Caller không được phép theo chính sách HTTP | 403 | Phân biệt với ACL service account bị cấu hình sai. |
| Directory tạm thời không khả dụng | 503 | Có thể kèm retry policy thích hợp. |
| Search vượt thời gian | 504 hoặc lỗi nghiệp vụ riêng | Phụ thuộc gateway/API contract. |
| Search bị giới hạn và kết quả không đầy đủ | 422/503 hoặc trạng thái partial có hợp đồng riêng | Không trả danh sách như dữ liệu đầy đủ. |
| Bind người dùng thất bại | 401 trong luồng login | Không dùng mã này cho lỗi Bind của service account. |

Không có một bảng chuẩn bắt buộc chuyển LDAP resultCode sang HTTP status. HTTP status phải phản ánh **ngữ nghĩa ứng dụng** và chính sách bảo vệ thông tin.

## 13. Bắt exception theo loại, không theo message

Không viết:

~~~java
catch (org.springframework.ldap.NamingException ex) {
    if (ex.getMessage().contains("error code 68")) {
        // Duplicate?
    }
}
~~~

Không nên dựa vào:

- Chuỗi diagnostic của OpenLDAP hoặc Active Directory.
- Nội dung message đã được dịch theo locale.
- Tên host/DN xuất hiện trong message.
- Câu chữ khác nhau giữa JDK/JNDI provider.

Hãy bắt lớp cụ thể khi loại exception phản ánh đúng trạng thái cần xử lý:

~~~java
try {
    ldapTemplate.bind(dn, null, attributes);
} catch (org.springframework.ldap.NameAlreadyBoundException duplicate) {
    // Chuyển thành conflict nghiệp vụ.
}
~~~

Nếu provider trả một lớp khác cho cùng resultCode, kiểm tra cause và integration test trên server đang triển khai. Đừng thêm một chuỗi if/else parse message để “hỗ trợ mọi server”.

## 14. Kiểm thử LdapUtils.convertLdapException

Có thể test việc chuyển đổi mà không cần chạy LDAP server:

`LdapExceptionConversionTest.java`:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;
import org.springframework.ldap.support.LdapUtils;

class LdapExceptionConversionTest {

    @Test
    void convertsNameNotFoundToSpringLdapRuntimeType() {
        javax.naming.NameNotFoundException original =
                new javax.naming.NameNotFoundException(
                        "uid=missing,ou=people");

        org.springframework.ldap.NamingException converted =
                LdapUtils.convertLdapException(original);

        assertInstanceOf(
                org.springframework.ldap.NameNotFoundException.class,
                converted);
        assertSame(original, converted.getCause());
    }

    @Test
    void convertsNameAlreadyBoundToSpringLdapRuntimeType() {
        javax.naming.NameAlreadyBoundException original =
                new javax.naming.NameAlreadyBoundException(
                        "uid=lan,ou=people");

        org.springframework.ldap.NamingException converted =
                LdapUtils.convertLdapException(original);

        assertInstanceOf(
                org.springframework.ldap.NameAlreadyBoundException.class,
                converted);
        assertSame(original, converted.getCause());
    }

    @Test
    void convertsCommunicationFailureWithoutLosingCause() {
        javax.naming.CommunicationException original =
                new javax.naming.CommunicationException(
                        "Directory connection failed");

        org.springframework.ldap.NamingException converted =
                LdapUtils.convertLdapException(original);

        assertInstanceOf(
                org.springframework.ldap.CommunicationException.class,
                converted);
        assertSame(original, converted.getCause());
    }
}
~~~

Test xác minh ba điều:

1. Kết quả là kiểu Spring LDAP mong đợi.
2. Cause gốc được giữ lại.
3. Caller có thể catch bằng unchecked hierarchy.

**Không** dùng các test này để kết luận LDAP server đã trả đúng resultCode; chúng chỉ kiểm tra hàm chuyển đổi Java.

### Kiểm thử trường hợp không có mapping cụ thể

Nếu muốn kiểm tra fallback, tạo một subclass JNDI `NamingException` không có mapping cụ thể và xác minh kết quả là `UncategorizedLdapException`. Tên subclass cần tránh một loại đã được Spring LDAP hỗ trợ. Đây là test cho fallback converter, không phải khuyến khích ứng dụng tự tạo JNDI exception giả khi chạy production.

## 15. Integration test: xác minh exception đến từ directory

Dùng directory test có schema `inetOrgPerson` và service account với quyền thích hợp.

### Fixture

~~~ldif
dn: uid=lan,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: lan
cn: Nguyen Thi Lan
sn: Nguyen
~~~

### Ma trận test

| Ca kiểm thử | Operation | Kỳ vọng |
| --- | --- | --- |
| DN có tồn tại | `lookup` | Trả entity/DTO. |
| DN không tồn tại | `lookup` | Spring LDAP `NameNotFoundException`. |
| Search filter hợp lệ, không khớp | `search` | Danh sách rỗng; không nhất thiết có exception. |
| Add DN mới | `bind` | Thành công. |
| Add lại cùng DN | `bind` | Spring LDAP `NameAlreadyBoundException` hoặc kiểu tương ứng theo provider. |
| Bind sai mật khẩu | Authenticate | Spring LDAP `AuthenticationException` nếu provider ánh xạ theo cách này. |
| Bind reader nhưng Modify không đủ ACL | `modifyAttributes` | Lỗi quyền phù hợp; không nâng quyền tự động. |
| Thiếu thuộc tính bắt buộc `sn` | Add `inetOrgPerson` | Schema violation hoặc lỗi provider tương ứng. |
| Server ngừng hoạt động | Lookup/Search | Communication/Service unavailable, không phải “không tồn tại”. |
| TLS certificate sai | Bind/Search | Lỗi TLS/network; không retry bằng plaintext. |
| Search vượt size limit | Search | Limit exception hoặc hành vi partial theo cấu hình; không coi partial là đầy đủ. |
| Referral không xử lý | Search | Referral/partial exception theo provider. |
| JNDI direct lookup | `DirContext.lookup` | Checked JNDI exception; adapter chuyển bằng `LdapUtils`. |
| LdapTemplate lookup | `ldapTemplate.lookup` | Spring LDAP unchecked exception đã được dịch. |

### Một test phân biệt direct JNDI và LdapTemplate

Trong môi trường test:

1. Gọi `DirContext.lookup` trên DN không tồn tại và bắt `javax.naming.NameNotFoundException`.
2. Gọi `LdapTemplate.lookup` trên cùng DN và bắt `org.springframework.ldap.NameNotFoundException`.
3. Xác minh cả hai chỉ ra cùng trạng thái directory, nhưng có loại exception thuộc API khác nhau.
4. Đảm bảo mọi context và enumeration được đóng.
5. Chạy lại bằng đúng Bind DN/ACL của ứng dụng, không dùng rootdn để làm test luôn thành công.

## 16. Ngoại lệ và transaction: runtime không có nghĩa LDAP tự rollback

Vì Spring LDAP exceptions là unchecked, chúng có thể kích hoạt **quy tắc rollback mặc định của Spring transaction** khi thoát khỏi một method được quản lý transaction.

Tuy nhiên, phải phân biệt:

- **Exception translation:** đổi loại lỗi Java.
- **Transaction interception:** Spring nhận biết method transaction thất bại.
- **LDAP operation semantics:** directory server thực hiện Add/Modify/Delete/Rename.
- **Compensating transaction:** Spring LDAP có cơ chế ghi lại thao tác để cố gắng hoàn tác một số operation, nếu được cấu hình.

Một exception runtime không biến nhiều LDAP operation thành một transaction nguyên tử. Nếu service đã Add entry rồi lỗi ở bước cập nhật nhóm, không thể mặc định server tự khôi phục Add chỉ vì method ném `NameAlreadyBoundException` hoặc một exception khác.

Với workflow nhiều bước, cần thiết kế compensating action, retry có điều kiện và đối soát trạng thái thực trên directory. Xem transaction LDAP là một chủ đề riêng, không dùng `@Transactional` trên database để giả định LDAP cùng rollback.

## 17. Các lỗi thường gặp trong kiến trúc Spring LDAP

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Import nhầm `javax.naming.NamingException` để catch lỗi `LdapTemplate` | Không bắt được Spring LDAP runtime exception mong đợi. | Dùng `org.springframework.ldap.*` cho API Spring LDAP. |
| Catch `DataAccessException` để bắt mọi lỗi LDAP | Bỏ sót hierarchy riêng của Spring LDAP. | Catch `org.springframework.ldap.NamingException` hoặc lớp con cụ thể. |
| Tự gọi converter sau `LdapTemplate` | Dịch lặp hoặc code không đúng kiểu exception. | Để template xử lý. |
| Không chuyển JNDI exception trong adapter tự viết | Checked exception rò rỉ sang tầng trên, lặp boilerplate. | Dùng `LdapUtils.convertLdapException` ở biên adapter. |
| Catch `Exception` rồi trả empty list | Che lỗi mạng, ACL, schema và dữ liệu thiếu. | Chỉ bắt loại lỗi mà use case thực sự hiểu. |
| Parse `getMessage()` để tìm LDAP resultCode | Dễ vỡ khi provider/server đổi diagnostic. | Dựa vào class/cause và telemetry. |
| Map mọi AuthenticationException thành HTTP 401 | Lộ sai ngữ nghĩa khi service account Bind sai. | Xem danh tính thực hiện Bind và operation. |
| Map mọi NameNotFoundException thành 404 | Search base không tồn tại có thể có semantics khác. | Xem operation lookup hay search. |
| Trả raw exception message ra REST | Có thể lộ DN, server, ACL, filter và thông tin nội bộ. | Dùng domain error và message công khai ổn định. |
| Bỏ cause khi tạo domain exception | Mất khả năng điều tra root cause. | Giữ cause trong constructor. |
| Retry tất cả LDAP exception | Có thể lặp thao tác không idempotent hoặc gây tải. | Chỉ retry lỗi tạm thời và thao tác an toàn. |
| Nghĩ runtime exception tự rollback LDAP | Dữ liệu có thể đã được ghi một phần. | Thiết kế transaction/compensation và reconciliation. |
| Dùng raw JNDI mà không đóng context/enumeration | Rò rỉ tài nguyên kết nối. | Dùng try/finally hoặc LdapTemplate. |

## 18. Checklist thiết kế exception handling

| Câu hỏi | Tiêu chí đạt |
| --- | --- |
| API nào đang được gọi? | Biết rõ JNDI trực tiếp hay Spring LDAP template/repository. |
| Exception thuộc package nào? | Không nhầm `javax.naming` với `org.springframework.ldap`. |
| Đã được dịch chưa? | `LdapTemplate`/operations đã dịch; JNDI direct cần adapter chuyển đổi. |
| Có giữ cause không? | Domain exception có cause gốc. |
| Có phân loại theo loại exception không? | Không parse message/resultCode bằng chuỗi. |
| Có hiểu ngữ nghĩa operation không? | Lookup missing khác Search empty. |
| Có phân biệt service Bind với user Bind không? | Không map sai thành HTTP 401. |
| Có xử lý lỗi quyền đúng tầng không? | ACL service account khác HTTP authorization của caller. |
| Có che thông tin nhạy cảm không? | Không trả diagnostic/DN/credential ra API. |
| Có retry hợp lý không? | Chỉ retry lỗi tạm thời và operation idempotent/được kiểm soát. |
| Có xử lý partial result không? | Không coi kết quả chưa đầy đủ là thành công. |
| Có test JNDI converter không? | Unit test kiểm tra loại và cause. |
| Có test server thật không? | Integration test bằng đúng directory, Bind DN và ACL. |
| Có hiểu transaction không? | Không giả định unchecked exception tự rollback LDAP. |

## 19. Bài tập thực hành

**Bài 1 — So sánh hai loại exception.** Viết một hàm JNDI trực tiếp gọi `DirContext.lookup` và một hàm dùng `LdapTemplate.lookup` trên cùng DN không tồn tại. Ghi nhận kiểu exception và giải thích vì sao hàm thứ hai không cần catch checked JNDI exception.

**Bài 2 — Dùng converter.** Gọi `LdapUtils.convertLdapException` với `javax.naming.NameNotFoundException`, `NameAlreadyBoundException` và `CommunicationException`. Xác nhận lớp Spring LDAP và cause được giữ nguyên.

**Bài 3 — Search rỗng hay lỗi?** Tạo hai trường hợp: Search filter không khớp entry và Search base không tồn tại. Quan sát `LdapTemplate` trả danh sách rỗng hay ném exception; giải thích khác biệt.

**Bài 4 — Domain exception.** Tạo `PersonAlreadyExistsException` và `DirectoryUnavailableException`, giữ cause và viết service map các exception Spring LDAP phù hợp.

**Bài 5 — REST mapping.** Viết `@RestControllerAdvice` để trả 409 cho duplicate, 503 cho directory unavailable và 400 cho validation; xác minh response không chứa diagnostic LDAP.

**Bài 6 — DataAccessException.** Viết test chứng minh `org.springframework.ldap.NameNotFoundException` không thuộc `org.springframework.dao.DataAccessException`. Giải thích tại sao catch hierarchy sai làm lỗi thoát khỏi handler.

**Bài 7 — ACL.** Bind bằng reader service account và thử Modify entry. Xử lý exception theo operation/identity, không biến lỗi ACL thành user authentication failure.

**Bài 8 — Partial result.** Tạo Search có referral hoặc size limit trong directory test. Chứng minh service không trả danh sách partial như kết quả hoàn chỉnh.

**Bài 9 — Transaction.** Tạo workflow gồm Add user và Add group membership. Cố ý làm bước hai thất bại, kiểm tra trạng thái LDAP sau exception và đề xuất compensating action.

## 20. Câu hỏi tự đánh giá

1. `javax.naming.NamingException` là checked hay unchecked exception?
2. `org.springframework.ldap.NamingException` kế thừa lớp nào?
3. Vì sao Spring LDAP có một unchecked exception hierarchy riêng?
4. `LdapUtils.convertLdapException` nhận kiểu nào và trả kiểu nào?
5. Điều gì xảy ra nếu không có Spring LDAP subclass phù hợp?
6. Vì sao không nên catch `DataAccessException` để xử lý mọi lỗi LDAP?
7. `LdapTemplate.lookup` và `DirContext.lookup` khác nhau thế nào về exception translation?
8. Vì sao không cần gọi converter thủ công sau một thao tác `LdapTemplate`?
9. Khi nào cần chuyển JNDI exception thủ công?
10. `NameNotFoundException` ở Lookup khác kết quả Search rỗng thế nào?
11. Vì sao không nên parse `getMessage()` để suy ra LDAP resultCode?
12. Cause/root cause được giữ lại giúp gì cho việc điều tra?
13. `AuthenticationException` có luôn đồng nghĩa HTTP 401 không?
14. Khi service account thiếu ACL, lỗi thuộc về caller HTTP hay cấu hình directory?
15. Vì sao không nên trả `getExplanation()` trực tiếp ra REST?
16. `SizeLimitExceededException` hoặc `PartialResultException` có thể làm danh sách thiếu dữ liệu ra sao?
17. Vì sao không retry mọi exception LDAP?
18. Unchecked exception có tự làm LDAP server rollback nhiều operation không?
19. Khi nào cần compensating transaction/reconciliation?
20. Cần test gì để chứng minh exception được chuyển đúng giữa JNDI và Spring LDAP?

**Ghi nhớ:** JNDI ném `javax.naming.NamingException` dạng checked; Spring LDAP chuyển sang hệ ngoại lệ `org.springframework.ldap.*` dạng unchecked. `LdapTemplate` đã làm việc chuyển đổi trong các thao tác thông thường; khi gọi JNDI trực tiếp, dùng `LdapUtils.convertLdapException` tại adapter boundary. Hãy giữ cause, xử lý theo ngữ nghĩa operation, phân biệt hierarchy Spring LDAP với `DataAccessException`, và không công khai diagnostic của directory qua HTTP.

### Tài liệu tham khảo

- [Spring LDAP — Exception package summary](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/package-summary.html): danh sách hierarchy exception Spring LDAP và mô tả runtime exception mirror của JNDI.
- [Spring LDAP — NamingException API](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/NamingException.html): lớp cơ sở `NestedRuntimeException` và các tiện ích đọc cause/explanation.
- [Spring LDAP — LdapUtils API](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/support/LdapUtils.html): `convertLdapException` chuyển checked JNDI exception sang Spring LDAP runtime exception.
- [Spring LDAP — LdapOperations API](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/LdapOperations.html): cách các thao tác Search/Lookup xử lý NamingException và semantics `NameNotFoundException`.
- [Spring LDAP — LdapTemplate API](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/LdapTemplate.html): các thao tác LDAP và tiện ích xử lý context/exception.
- [Spring LDAP — Reference Documentation](https://docs.spring.io/spring-ldap/reference/): kiến trúc, ContextSource, LdapTemplate và tích hợp Spring.
- [Spring Framework — NestedRuntimeException API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/NestedRuntimeException.html): cơ chế giữ và truy cập nguyên nhân gốc.
- [Spring Framework — DataAccessException API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/dao/DataAccessException.html): hệ phân cấp exception truy cập dữ liệu của Spring DAO.
- [Java SE — javax.naming.NamingException API](https://docs.oracle.com/en/java/javase/21/docs/api/java.naming/javax/naming/NamingException.html): checked NamingException của JNDI.
- [Java SE — javax.naming.directory.DirContext API](https://docs.oracle.com/en/java/javase/21/docs/api/java.naming/javax/naming/directory/DirContext.html): các operation lookup/search/modify và khai báo NamingException.
- [RFC 4511 — LDAP: The Protocol](https://www.rfc-editor.org/rfc/rfc4511): LDAP resultCode, Bind, Search, Modify và response protocol.
- [RFC 4512 — LDAP: Directory Information Models](https://www.rfc-editor.org/rfc/rfc4512): entry, DN, objectClass và schema.
