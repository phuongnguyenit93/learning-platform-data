# ObjectFactory và chuyển đổi đối tượng directory

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích vì sao **entry trong LDAP directory** khác với **Java object** và phân biệt việc đọc thuộc tính với việc khôi phục một đối tượng.
- Hiểu vai trò của `javax.naming.spi.ObjectFactory`, `DirObjectFactory`, `NamingManager` và `DirectoryManager` trong Java Naming and Directory Interface (JNDI).
- Phân biệt việc JNDI provider tự chuyển đổi object với cách **Spring LDAP** ánh xạ entry chủ động bằng `AttributesMapper`, `ContextMapper`, `DirContextOperations` và Object-Directory Mapping (ODM).
- Chọn chiến lược chuyển đổi phù hợp khi dùng `ContextSource`, `LdapTemplate` hoặc repository; nhận biết các giới hạn về DN, schema, attribute nhiều giá trị và lỗi ánh xạ.
- Tránh các rủi ro do tự động giải mã đối tượng, sử dụng factory hoặc deserialize dữ liệu đến từ LDAP server không đáng tin cậy.

Bài thuộc chương **JNDI và Spring** trong module **SPRING_LDAP**. Các thao tác tìm kiếm, đọc entry và chuyển đổi dữ liệu thường gặp trong Spring LDAP đều dựa trên việc hiểu LDAP là **dịch vụ thư mục theo DN và thuộc tính**; nó không tự biến mọi entry thành một Java bean tương ứng.

## 1. LDAP entry và Java object là hai mô hình khác nhau

Một entry LDAP gồm **Distinguished Name (DN)**, tập các **attribute** và các giá trị thuộc tính chịu ràng buộc của schema:

~~~ldif
dn: uid=lan,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: lan
cn: Nguyen Lan
sn: Nguyen
mail: lan@example.org
~~~

Ứng dụng Java có thể muốn hiển thị entry này dưới dạng:

~~~java
public record EmployeeProfile(
        String uid,
        String commonName,
        String email
) {}
~~~

Muốn chuyển từ entry sang `EmployeeProfile`, ứng dụng cần trả lời:

1. Lấy giá trị `uid`, `cn` và `mail` từ đâu?
2. Mỗi thuộc tính có **một hay nhiều giá trị**? Có thể vắng mặt không?
3. Giá trị được trả về là `String`, `byte[]` hay kiểu khác?
4. DN cần giữ ở dạng `javax.naming.Name`, string hay không cần trong DTO?
5. Ai chịu trách nhiệm chuyển đổi và xử lý trường hợp dữ liệu sai schema hoặc không được phép đọc?

JNDI và Spring LDAP cung cấp nhiều cách trả lời, nhưng chúng hoạt động ở những lớp khác nhau.

~~~mermaid
flowchart TB
    LDAP[("LDAP directory<br/>DN + Attributes + schema")]
    JNDI["JNDI LDAP provider<br/>DirContext / Attributes / SearchResult"]
    SPI["JNDI ObjectFactory / DirObjectFactory<br/>chuyển object khi provider yêu cầu"]
    Spring["Spring LDAP LdapTemplate<br/>AttributesMapper / ContextMapper"]
    ODM["Spring LDAP ODM<br/>@Entry / @Attribute / @Id"]
    App["Java DTO / domain object"]
    LDAP --> JNDI
    JNDI -. "Tùy provider và cấu hình" .-> SPI
    JNDI --> Spring
    Spring --> App
    Spring --> ODM --> App
    SPI -. "Object do factory tạo" .-> App
~~~

**Điểm mấu chốt:** `ObjectFactory` là một cơ chế mở rộng **SPI của JNDI**. Nó không đồng nghĩa với mapper thông thường trong `LdapTemplate`, không mặc nhiên chạy cho mọi entry và không phải cơ chế duy nhất để ánh xạ dữ liệu directory.

## 2. Dòng chảy JNDI cơ bản: Context, Attributes, SearchResult

JNDI là API Java cho dịch vụ đặt tên và thư mục. LDAP là một trong những provider có thể được JNDI sử dụng.

| Khái niệm JNDI | Vai trò | Ví dụ trong LDAP |
| --- | --- | --- |
| `Context` | Đặt tên và tra cứu đối tượng | Tra cứu theo tên |
| `DirContext` | Mở rộng Context để làm việc với attributes và tìm kiếm | `getAttributes`, `search`, `modifyAttributes` |
| `Attributes` | Tập các attribute của một entry | `uid`, `cn`, `mail` |
| `Attribute` | ID thuộc tính và một hoặc nhiều giá trị | `cn: Nguyen Lan` |
| `SearchResult` | Một kết quả tìm kiếm gồm tên, object (nếu được yêu cầu/cung cấp) và attributes | Một entry dưới search base |
| `NamingEnumeration<SearchResult>` | Duyệt kết quả tìm kiếm | Nhiều entry khớp filter |

Một truy vấn JNDI thường cần `DirContext`, search base, filter và `SearchControls`:

~~~java
import java.util.Hashtable;
import javax.naming.Context;
import javax.naming.NamingEnumeration;
import javax.naming.directory.Attributes;
import javax.naming.directory.DirContext;
import javax.naming.directory.InitialDirContext;
import javax.naming.directory.SearchControls;
import javax.naming.directory.SearchResult;

Hashtable<String, String> env = new Hashtable<>();
env.put(Context.INITIAL_CONTEXT_FACTORY,
        "com.sun.jndi.ldap.LdapCtxFactory");
env.put(Context.PROVIDER_URL,
        "ldaps://ldap.example.org:636/dc=example,dc=org");
env.put(Context.SECURITY_AUTHENTICATION, "simple");
env.put(Context.SECURITY_PRINCIPAL,
        "uid=directory-reader,ou=services,dc=example,dc=org");
env.put(Context.SECURITY_CREDENTIALS,
        System.getenv("LDAP_READER_PASSWORD"));

DirContext context = new InitialDirContext(env);
try {
    SearchControls controls = new SearchControls();
    controls.setSearchScope(SearchControls.SUBTREE_SCOPE);
    controls.setReturningAttributes(
            new String[] {"uid", "cn", "mail"});

    NamingEnumeration<SearchResult> found = context.search(
            "ou=people",
            "(uid=lan)",
            controls
    );
    try {
        while (found.hasMore()) {
            SearchResult result = found.next();
            Attributes attributes = result.getAttributes();

            System.out.println(
                    attributes.get("cn").get()
            );
        }
    } finally {
        found.close();
    }
} finally {
    context.close();
}
~~~

Đây là **ví dụ JNDI thuần** nhằm minh họa ranh giới API. Trong Spring LDAP, `ContextSource` và `LdapTemplate` thường quản lý context và đóng tài nguyên giúp bạn. Ví dụ JNDI giả định biến môi trường có mật khẩu phù hợp, LDAPS được cấu hình với **chứng chỉ tin cậy**, tài khoản dịch vụ có quyền tra cứu và các entry khớp đều có `cn`.

Trong vòng lặp, `result.getAttributes()` trả **dữ liệu thuộc tính**. Nó chưa có nghĩa một instance `EmployeeProfile` đã được tạo.

### 2.1. Vì sao `SearchResult.getObject()` không phải DTO của ứng dụng?

`SearchResult` kế thừa các khái niệm binding trong JNDI và có phương thức `getObject()`. Đối tượng này **phụ thuộc provider, cách lookup/search và các tùy chọn JNDI**, đặc biệt việc có yêu cầu returning object hay không. Với search chỉ cần attributes, mặc định thường không yêu cầu trả về object Java tương ứng.

Đừng giả định:

~~~java
EmployeeProfile p = (EmployeeProfile) result.getObject();
~~~

sẽ hoạt động cho mọi LDAP server hoặc mọi entry có `uid`/`cn`/`mail`. Một directory entry thông thường không tự mang class Java `EmployeeProfile`; để có DTO này, ứng dụng phải thực hiện một phép ánh xạ cụ thể.

Nếu chỉ muốn đọc thuộc tính, dùng `Attributes` hoặc mapper ở Spring LDAP; không cần kích hoạt cơ chế khôi phục Java object của JNDI.

## 3. `ObjectFactory` là gì trong JNDI?

`javax.naming.spi.ObjectFactory` là một **Service Provider Interface (SPI)**: một factory có thể tạo một đối tượng Java từ thông tin mà hệ thống naming/directory cung cấp.

Chữ ký cốt lõi:

~~~java
import java.util.Hashtable;
import javax.naming.Context;
import javax.naming.Name;

public interface ObjectFactory {
    Object getObjectInstance(
        Object obj,
        Name name,
        Context nameCtx,
        Hashtable<?, ?> environment
    ) throws Exception;
}
~~~

Ý nghĩa các tham số:

| Tham số | Nội dung | Lưu ý |
| --- | --- | --- |
| `obj` | Thông tin/object được provider đưa tới để chuyển đổi | Có thể là object trực tiếp, `Reference` hoặc dạng khác; không mặc định là `Attributes` |
| `name` | Tên liên quan tới object trong naming context | Có thể tương đối với `nameCtx` hoặc vắng mặt |
| `nameCtx` | Context liên quan đến tên | Có thể `null`, phụ thuộc cách gọi |
| `environment` | Môi trường JNDI | Chỉ sử dụng thông tin tin cậy, tránh đưa secret vào log |

Factory trả về object nếu biết xử lý; khi **không** xử lý được, thông thường trả `null` để JNDI thử cơ chế/factory khác hoặc giữ lại thông tin ban đầu theo quy trình của nó.

### 3.1. `Reference` và `Referenceable` khác với LDAP entry thông thường

JNDI có mô hình `Reference` mô tả thông tin để tái tạo một object, chẳng hạn tên class, các địa chỉ tham chiếu và thông tin về factory. `Referenceable` là interface cho object có thể cung cấp reference của chính nó.

Điều này khác với entry LDAP chỉ có:

~~~text
uid = lan
cn = Nguyen Lan
mail = lan@example.org
~~~

Entry trên là dữ liệu directory. Chỉ nhìn thấy `cn` hay `objectClass=inetOrgPerson` **không đủ** để JNDI biết phải dựng lớp Java `EmployeeProfile` nào hoặc gọi constructor ra sao.

Một số JNDI LDAP provider hỗ trợ cách lưu tham chiếu/đối tượng Java trong LDAP bằng metadata riêng. Những cơ chế đó có ràng buộc tương thích, cấu hình và đặc biệt là **rủi ro bảo mật**. Không dùng chúng như giải pháp mặc định để mô hình hóa hồ sơ nhân viên.

### 3.2. `NamingManager` là nơi điều phối chuyển đổi object

JNDI cung cấp `javax.naming.spi.NamingManager` để điều phối việc lấy object instance từ thông tin tham chiếu, object factory và môi trường hiện có. Một provider có thể gọi cơ chế này trong một số thao tác lookup/bind/search.

Vì vậy có hai trách nhiệm tách biệt:

- **Provider** truy cập dịch vụ naming/directory và biết dữ liệu trả về theo giao thức.
- **Object factory** có thể chuyển thông tin thành một object mà ứng dụng hiểu.

Lời gọi `getObjectInstance(...)` **không tự động xảy ra mỗi lần** bạn đọc `DirContext.getAttributes(...)`. Sự tham gia của factory phụ thuộc provider, operation và cấu hình object-returning.

## 4. `DirObjectFactory`: biến thể cho dịch vụ directory

LDAP không chỉ có tên mà còn có **attributes**. JNDI bổ sung `javax.naming.spi.DirObjectFactory`, mở rộng `ObjectFactory` với overload nhận `Attributes`:

~~~java
import java.util.Hashtable;
import javax.naming.Context;
import javax.naming.Name;
import javax.naming.directory.Attributes;
import javax.naming.spi.DirObjectFactory;

public interface DirObjectFactory extends ObjectFactory {
    Object getObjectInstance(
        Object obj,
        Name name,
        Context nameCtx,
        Hashtable<?, ?> environment,
        Attributes attrs
    ) throws Exception;
}
~~~

`DirectoryManager` là cơ chế JNDI dành cho provider directory muốn thực hiện object conversion có cả attributes. Khi provider và cấu hình sử dụng đường đi đó, `DirObjectFactory` có thể đọc dữ liệu `uid`/`cn` thay vì chỉ nhận một object/reference.

### 4.1. Ví dụ factory ánh xạ attributes thành DTO

Đây là một **factory minh họa SPI**, không phải cấu hình bắt buộc của Spring LDAP:

~~~java
import java.util.Hashtable;
import javax.naming.Context;
import javax.naming.Name;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;
import javax.naming.spi.DirObjectFactory;

public final class EmployeeDirObjectFactory
        implements DirObjectFactory {

    public record EmployeeSummary(
        String uid,
        String commonName
    ) {}

    @Override
    public Object getObjectInstance(
            Object obj,
            Name name,
            Context nameCtx,
            Hashtable<?, ?> environment,
            Attributes attrs
    ) throws Exception {

        if (attrs == null) {
            return null;
        }

        Attribute uidAttr = attrs.get("uid");
        Attribute cnAttr = attrs.get("cn");

        if (uidAttr == null || cnAttr == null) {
            return null; // Factory này không xử lý entry thiếu dữ liệu.
        }

        Object uidValue = uidAttr.get();
        Object cnValue = cnAttr.get();
        if (!(uidValue instanceof String)
                || !(cnValue instanceof String)) {
            return null;
        }

        return new EmployeeSummary(
                (String) uidValue,
                (String) cnValue
        );
    }

    @Override
    public Object getObjectInstance(
            Object obj,
            Name name,
            Context nameCtx,
            Hashtable<?, ?> environment
    ) {
        return null; // Không có Attributes: factory không tự suy đoán.
    }
}
~~~

Factory trên:

- Chỉ tạo object khi attributes tồn tại và có `uid`, `cn` kiểu chuỗi.
- Không deserialize dữ liệu nhị phân hoặc tải class từ LDAP.
- Không âm thầm biến mọi object/reference thành `EmployeeSummary`.
- Không tự bảo đảm `uid` là duy nhất hay entry đã được xác thực.

Ví dụ không gán DN cho DTO vì `name` có thể là tên tương đối phụ thuộc provider/context. Nếu nghiệp vụ cần danh tính entry, hãy thiết kế cách lấy DN rõ ràng và thống nhất với base DN của `ContextSource`.

### 4.2. Có thể đăng ký factory như thế nào?

JNDI định nghĩa thuộc tính môi trường `Context.OBJECT_FACTORIES` (tên cấu hình `java.naming.factory.object`) để cung cấp danh sách factory cho quá trình object conversion:

~~~java
import javax.naming.Context;
import java.util.Hashtable;

Hashtable<String, Object> environment = new Hashtable<>();
environment.put(
    Context.OBJECT_FACTORIES,
    "com.example.ldap.EmployeeDirObjectFactory"
);
~~~

Phần này minh họa **khai báo factory class** trong môi trường JNDI. Để factory thực sự được dùng, provider/operation phải đi qua cơ chế object conversion tương ứng và class phải có trên classpath tin cậy. Không nên coi cấu hình trên là lời hứa `DirContext.search(...)` sẽ tự động trả `EmployeeSummary` cho mọi entry.

Trong một ứng dụng dùng Spring LDAP, việc phải cấu hình SPI này để đọc `uid`/`cn` thường làm giải pháp phức tạp không cần thiết. `AttributesMapper` hoặc ODM đáp ứng nhu cầu dữ liệu nghiệp vụ trực tiếp và dễ kiểm thử hơn.

## 5. Vì sao Spring LDAP thường dùng mapper?

Spring LDAP bọc JNDI bằng các API truy cập directory mà ứng dụng dễ kiểm soát. Khi gọi `LdapTemplate.search(...)`, ta **chủ động truyền mapper** quyết định cách chuyển một entry thành DTO.

| Cách chuyển đổi | Nơi hoạt động | Dữ liệu được cung cấp | Phù hợp khi |
| --- | --- | --- | --- |
| JNDI `ObjectFactory` | SPI của naming provider | Object/reference và thông tin naming | Cần tích hợp object conversion đặc thù của JNDI/provider |
| JNDI `DirObjectFactory` | SPI cho directory provider | Thêm `Attributes` nếu provider hỗ trợ đường đi tương ứng | Phải dùng mô hình object factory của JNDI |
| Spring LDAP `AttributesMapper<T>` | Ứng dụng với `LdapTemplate` | `Attributes` của entry | DTO chỉ cần các thuộc tính |
| Spring LDAP `ContextMapper<T>` | Ứng dụng với `LdapTemplate` | Context cho entry, thường là `DirContextOperations` | DTO cần DN hoặc thao tác đọc thông tin context |
| Spring LDAP ODM | Tầng ánh xạ entry-object của Spring | Entity có annotation `@Entry`, `@Id`, `@Attribute` | Mô hình entry ổn định, cần mapping lặp lại |
| Spring Data LDAP repository | Trên hạ tầng ODM/Spring LDAP | Entity và repository methods | Truy cập entry theo kiểu repository |

Đặc biệt, `ObjectFactory` ở đây là interface trong package `javax.naming.spi`, **không** phải `org.springframework.beans.factory.ObjectFactory<T>` của Spring IoC. Cả hai có tên giống nhau nhưng mục đích và hợp đồng API khác hoàn toàn.

## 6. `AttributesMapper`: đọc và chuyển thuộc tính rõ ràng

Giả sử ứng dụng Spring Boot đã khai báo kết nối LDAP:

~~~yaml
spring:
  ldap:
    urls: ldaps://ldap.example.org:636
    base: dc=example,dc=org
    username: uid=directory-reader,ou=services,dc=example,dc=org
    # Cấp spring.ldap.password từ secret manager hoặc biến môi trường.
~~~

Tạo DTO và service:

~~~java
import java.util.List;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;

import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.filter.EqualsFilter;
import org.springframework.stereotype.Service;

record EmployeeProfile(
    String uid,
    String commonName,
    String email
) {}

@Service
public class EmployeeDirectoryService {
    private final LdapTemplate ldapTemplate;

    public EmployeeDirectoryService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<EmployeeProfile> findByUid(String uid) {
        String filter = new EqualsFilter("uid", uid).encode();

        return ldapTemplate.search(
            "ou=people",
            filter,
            (AttributesMapper<EmployeeProfile>) attrs ->
                new EmployeeProfile(
                    requiredString(attrs, "uid"),
                    requiredString(attrs, "cn"),
                    optionalString(attrs, "mail")
                )
        );
    }

    private static String requiredString(
            Attributes attrs, String id) throws javax.naming.NamingException {
        Attribute attr = attrs.get(id);
        if (attr == null || attr.size() == 0) {
            throw new IllegalArgumentException(
                "Thiếu thuộc tính LDAP bắt buộc: " + id
            );
        }
        return (String) attr.get();
    }

    private static String optionalString(
            Attributes attrs, String id) throws javax.naming.NamingException {
        Attribute attr = attrs.get(id);
        if (attr == null || attr.size() == 0) {
            return null;
        }
        return (String) attr.get();
    }
}
~~~

Ở đây:

- `EqualsFilter` mã hóa giá trị `uid` đầu vào theo **cú pháp LDAP filter**, tránh lỗi khi chứa `*`, dấu ngoặc hoặc ký tự escape.
- `"ou=people"` là search base **tương đối** với `dc=example,dc=org` trong `ContextSource` đã cấu hình.
- `AttributesMapper` nhận `Attributes` và tạo `EmployeeProfile`; không cần JNDI object factory.
- Các hàm helper xử lý **thuộc tính thiếu** khác nhau tùy hợp đồng nghiệp vụ. Ví dụ giả định các giá trị cần đọc là `String`.
- `List<EmployeeProfile>` phù hợp vì không nên tự suy rằng một thuộc tính như `uid` duy nhất toàn directory nếu server không có ràng buộc tương ứng.

Trong ứng dụng thực, cần kiểm tra size/loại của attribute thay vì ép kiểu `(String)` cho mọi schema. Một số attribute như ảnh, certificate hoặc UUID nhị phân có thể được JNDI biểu diễn dưới dạng `byte[]`.

### 6.1. Thuộc tính nhiều giá trị

LDAP cho phép một số attribute có **nhiều giá trị**. Ví dụ người dùng có hai số điện thoại hoặc nhóm có nhiều `member`. Hàm `Attribute.get()` chỉ lấy một giá trị, không bảo đảm bảo toàn toàn bộ dữ liệu nhiều giá trị.

Ví dụ đọc từng `member`:

~~~java
import java.util.ArrayList;
import java.util.List;
import javax.naming.NamingEnumeration;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;

static List<String> readMembers(Attributes attrs)
        throws javax.naming.NamingException {

    Attribute member = attrs.get("member");
    if (member == null) {
        return List.of();
    }

    List<String> values = new ArrayList<>();
    NamingEnumeration<?> en = member.getAll();
    try {
        while (en.hasMore()) {
            values.add((String) en.next());
        }
    } finally {
        en.close();
    }
    return values;
}
~~~

Không giả định **thứ tự** các giá trị LDAP phản ánh thứ tự nghiệp vụ, trừ khi server/schema cung cấp bảo đảm cụ thể. Với thuộc tính kiểu DN như `member`, cần xử lý theo quy tắc DN, tránh so khớp bằng phép lowercase toàn bộ string.

## 7. `ContextMapper`: khi cần DN và thông tin context

`AttributesMapper` chỉ nhận danh sách thuộc tính. Nếu ứng dụng cần thêm **DN** hoặc phương thức đọc context thuận tiện, `ContextMapper<T>` phù hợp hơn.

~~~java
import java.util.List;
import org.springframework.ldap.core.ContextMapper;
import org.springframework.ldap.core.DirContextOperations;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.filter.EqualsFilter;

record EmployeeIdentity(
    String relativeDn,
    String uid,
    String commonName
) {}

public List<EmployeeIdentity> findEmployeeIdentities(
        LdapTemplate ldapTemplate, String uid) {

    return ldapTemplate.search(
        "ou=people",
        new EqualsFilter("uid", uid).encode(),
        (ContextMapper<EmployeeIdentity>) ctx -> {
            DirContextOperations entry = (DirContextOperations) ctx;

            return new EmployeeIdentity(
                entry.getDn().toString(),
                entry.getStringAttribute("uid"),
                entry.getStringAttribute("cn")
            );
        }
    );
}
~~~

`DirContextOperations` là abstraction của Spring LDAP cho thao tác thuộc tính trên một entry, thường được hiện thực bằng `DirContextAdapter`. Nó cung cấp những phương thức như `getStringAttribute(...)` và `getDn()`.

**Lưu ý về DN:** DN được context mapper giữ có thể chịu quy ước tương đối với base/context đang dùng. Không tự giả định `entry.getDn().toString()` luôn là **full DN** từ root của LDAP server. Nếu cần DN toàn phần để lưu ngoài hệ thống, hãy kiểm tra API/phiên bản và kết hợp base DN đúng cách.

### 7.1. Khi dùng mapper nào?

**Chọn `AttributesMapper`** nếu muốn ánh xạ `cn`, `mail`, `uid` vào DTO nhẹ cho REST API hoặc báo cáo.

**Chọn `ContextMapper`** nếu cần biết DN, kiểm tra attribute theo tiện ích `DirContextOperations` hoặc làm việc với một entry theo mô hình context.

**Chọn ODM/repository** khi cùng một kiểu entry được ánh xạ lặp lại ở nhiều nơi và nhu cầu truy cập theo entity rõ ràng. Đây là các cấp abstraction; không nhất thiết mỗi ứng dụng phải dùng tất cả.

## 8. Object-Directory Mapping (ODM): một con đường khác với JNDI ObjectFactory

Spring LDAP cung cấp ODM để ánh xạ entry thành object có khai báo annotation. Ví dụ:

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

    @Attribute(name = "mail")
    private String email;

    // Constructor, getter, setter theo yêu cầu mapping.
}
~~~

Đây là **entity đại diện entry LDAP**, khác DTO `EmployeeProfile` được tạo thủ công. Các annotation `@Entry`, `@Id` và `@Attribute` thuộc **Spring LDAP ODM**, không phải `ObjectFactory` của JNDI.

Khi sử dụng Spring Data LDAP, repository có thể làm việc với entity này:

~~~java
import java.util.List;
import org.springframework.data.ldap.repository.LdapRepository;

public interface PersonRepository
        extends LdapRepository<DirectoryPerson> {
    List<DirectoryPerson> findByUid(String uid);
}
~~~

Repository cần được bật/khai báo đúng trong ứng dụng, ví dụ bằng `@EnableLdapRepositories` phù hợp. Spring Data LDAP tận dụng mapping của Spring LDAP và cung cấp các phương thức truy cập dữ liệu; nó **không** yêu cầu JNDI `DirObjectFactory` phải tạo bean từ một `Reference`.

### 8.1. ODM không vô hiệu hóa schema

`@Attribute(name = "mail")` chỉ định field lấy dữ liệu từ attribute nào. Nó không thay đổi LDAP schema, equality matching rule, ACL hoặc thuộc tính bắt buộc của `inetOrgPerson`.

`@Id` là DN dạng `javax.naming.Name`, không phải ID số tự tăng của cơ sở dữ liệu quan hệ. Đổi RDN hoặc chuyển entry sang OU khác có thể làm DN thay đổi. Nếu nghiệp vụ cần khóa bền vững, phải hiểu khả năng của server và schema, ví dụ một số server có `entryUUID` hoặc `objectGUID`.

Các giá trị nhiều phần, binary, operational attributes hoặc custom schema có thể cần chiến lược ánh xạ/đọc riêng. ODM không thể tự suy ra ý nghĩa nghiệp vụ của mọi attribute LDAP.

## 9. Vì sao không dùng JNDI ObjectFactory như cơ chế mặc định?

### 9.1. Vòng đời và trách nhiệm khó thấy hơn

Với `LdapTemplate.search(..., mapper)`, đoạn code gọi truy vấn cho thấy **chính xác** object được tạo như thế nào. Test có thể cấp một bộ `Attributes` giả hoặc LDAP test server để kiểm tra.

Với JNDI `ObjectFactory`, việc factory có được gọi hay không phụ thuộc provider, operation và môi trường JNDI. Người đọc code có thể thấy `context.lookup(...)` mà không biết tầng SPI nào sẽ tạo object sau đó. Sự khác nhau về provider/phiên bản và cấu hình làm test/phân tích lỗi khó hơn.

### 9.2. Không đưa dữ liệu LDAP vào cơ chế thực thi class động

Một số lịch sử tích hợp JNDI/LDAP có hỗ trợ thông tin **reference** hoặc dữ liệu Java đã serialize. Khi lookup xử lý tên hoặc reference không đáng tin cậy, việc kích hoạt factory/classloading/deserialization có thể tạo ra rủi ro nghiêm trọng, bao gồm khai thác **JNDI injection** hoặc deserialization.

Trong ứng dụng nghiệp vụ hiện đại, nguyên tắc an toàn:

- **Không deserialize** dữ liệu Java từ thuộc tính LDAP không đáng tin cậy chỉ để dựng domain object.
- **Không** tải class/factory từ codebase, URL hoặc tên class do bên ngoài điều khiển.
- Chỉ dùng factory **cục bộ, thuộc classpath tin cậy** nếu thật sự cần SPI.
- Kiểm soát mọi đầu vào dùng cho JNDI name, URL, search base và filter; không chuyển input thành đường dẫn JNDI tùy ý.
- Dùng `AttributesMapper`, `ContextMapper` hoặc ODM với whitelist field/kiểu dữ liệu để ánh xạ entry nghiệp vụ.

Các bản Java hiện đại có nhiều cơ chế hạn chế remote class loading qua JNDI, nhưng **không** nên dựa vào đó để coi các object/reference từ LDAP không đáng tin cậy là an toàn. Hành vi bảo mật còn phụ thuộc Java runtime, provider và cấu hình.

### 9.3. Factory không thay được xác thực

`ObjectFactory` có thể tạo DTO từ `cn`/`uid`. Điều đó chỉ chứng minh một entry hoặc tập thuộc tính đã được đọc và chuyển thành object.

Để xác thực người dùng, **Spring Security LDAP** nên dùng bind hoặc cơ chế xác thực phù hợp; để quyết định quyền truy cập, phải áp dụng `Authentication`/authorities đã xác minh và chính sách của ứng dụng. Không coi một Java object được dựng thành công là bằng chứng người dùng đã đăng nhập hoặc có quyền admin.

## 10. Lỗi thường gặp khi chuyển entry sang Java object

| Lỗi | Biểu hiện | Cách xử lý |
| --- | --- | --- |
| Ép `SearchResult.getObject()` thành DTO bất kỳ | `ClassCastException` hoặc object `null` | Đọc `Attributes` và ánh xạ có chủ đích |
| Nghĩ mọi entry tự chạy `ObjectFactory` | Factory không được gọi, khác hành vi giữa provider | Xác minh đường đi JNDI; ưu tiên mapper Spring LDAP |
| Nhầm `javax.naming.spi.ObjectFactory` với `org.springframework.beans.factory.ObjectFactory` | Sai interface, sai tham số | Phân biệt SPI JNDI với bean-provider của Spring |
| Gọi `attrs.get("cn").get()` không kiểm tra thuộc tính | `NullPointerException` khi thiếu/không có quyền đọc | Kiểm tra thiếu và chọn chính sách fallback rõ |
| Ép mọi attribute thành `String` | Lỗi với `byte[]` hoặc kiểu giá trị khác | Hiểu schema, kiểm tra kiểu và map phù hợp |
| Dùng `Attribute.get()` cho thuộc tính nhiều giá trị | Mất những giá trị còn lại | Duyệt `getAll()` và đóng enumeration |
| Gắn DN tương đối vào DTO như full DN | Sai danh tính entry khi hệ thống có nhiều base | Xác định rõ ngữ cảnh của `getDn()` |
| Tự ghép LDAP filter từ input | LDAP filter injection | Dùng `EqualsFilter` hoặc query builder có escaping |
| Coi map thành công là đã xác thực | Cấp nhầm quyền | Tách luồng truy vấn dữ liệu khỏi xác thực |
| Cho factory deserialize/tải class theo reference do LDAP trả | Nguy cơ thực thi mã hoặc lỗi bảo mật | Không chạy factory/deserialize không tin cậy |
| Bỏ qua ACL và thuộc tính bị ẩn | Tưởng server thiếu dữ liệu | Kiểm tra quyền tài khoản bind và dữ liệu/entry thật |
| Để exception mapper thành “không có user” | Che lỗi schema, kết nối, mapping | Phân loại lỗi và trả phản hồi phù hợp |

## 11. Kiểm thử chuyển đổi object với LDAP

### 11.1. Test mapper không cần server

Với một phép ánh xạ thuần từ `Attributes`, bạn có thể tạo dữ liệu JNDI nội bộ:

~~~java
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.BasicAttributes;
import javax.naming.directory.Attributes;

Attributes attrs = new BasicAttributes(true);
attrs.put(new BasicAttribute("uid", "lan"));
attrs.put(new BasicAttribute("cn", "Nguyen Lan"));
attrs.put(new BasicAttribute("mail", "lan@example.org"));

String uid = (String) attrs.get("UID").get();
System.out.println(uid); // lan
~~~

`new BasicAttributes(true)` chỉ khiến **collection attributes ở phía Java** tra cứu attribute ID không phân biệt case. Nó **không** làm LDAP server thay đổi equality matching rule của giá trị.

Có thể tách logic chuyển DTO thành một hàm thuần nhận `Attributes`, rồi kiểm thử những trường hợp:

1. Tên attribute khác case (`cn`/`CN`).
2. Một thuộc tính bắt buộc bị thiếu.
3. Thuộc tính nhiều giá trị, thứ tự giá trị không xác định.
4. Giá trị kiểu `byte[]` khi mapper kỳ vọng `String`.
5. Attribute có option như `cn;lang-vi` khác với `cn;lang-en`.

### 11.2. Test tích hợp cần LDAP server thật hoặc embedded LDAP

Để xác minh `LdapTemplate.search(...)`, `ContextMapper` hoặc ODM thực sự hoạt động, cần LDAP test server có schema tương ứng, ví dụ một embedded LDAP được hỗ trợ trong môi trường kiểm thử.

Nên kiểm tra:

- DN, search base, scope và filter dẫn đến đúng entry.
- `ContextSource` bind bằng tài khoản có quyền phù hợp; schema cấp `uid`/`cn`/`mail`.
- Entry nằm trong OU lồng nhau, response có/không có `mail`.
- Việc lấy DN trong mapper/ODM là tương đối hay đầy đủ theo cấu hình thật.
- Truy vấn với thuộc tính binary/multivalued, các options và custom objectClass.
- Server không trả một thuộc tính do ACL; ứng dụng phân biệt được dữ liệu thiếu và lỗi ánh xạ.
- Timeout, lỗi kết nối TLS, bind thất bại và giới hạn kết quả.
- Nếu dùng custom JNDI factory, kiểm tra rõ provider/operation nào gọi factory, cách trả `null`, và bảo đảm factory không xử lý reference không tin cậy.

**Ghi nhớ:** unit test của một mapper chỉ chứng minh phép chuyển đổi **với attributes đã cho**. Nó không chứng minh LDAP server sẽ trả đúng entry, đúng attributes hoặc có quyền đọc.

### 11.3. Chi phí ánh xạ và tài nguyên

Đọc hàng nghìn entry thành object sẽ tạo ra chi phí CPU, cấp phát bộ nhớ và băng thông. Khi dùng Spring LDAP:

- Chọn base/scope đủ hẹp.
- Dùng filter chọn lọc và index phù hợp trên server.
- Chỉ yêu cầu những attribute cần thiết, ví dụ `uid`/`cn`, tránh tải ảnh hoặc certificate nếu không dùng.
- Thiết kế size/time limits và phân trang theo khả năng server; đừng nhận toàn directory trong một lần gọi.
- Quản lý kết nối qua `ContextSource`, cấu hình LDAPS/StartTLS với xác thực chứng chỉ và sử dụng pooling có kiểm soát.

Factory hay mapper không làm truy vấn LDAP nhanh lên nếu vấn đề thực tế là filter quá rộng hoặc server thiếu index.

## 12. Bài tập tình huống

**Bối cảnh:** ứng dụng quản lý nhân viên cần lấy `uid`, `cn` và `mail` để hiển thị, lấy DN để cập nhật đúng entry, rồi tra cứu các nhóm của người dùng. Đội phát triển đề xuất đăng ký một JNDI `ObjectFactory` để tự chuyển toàn bộ entry thành object và xử lý cả xác thực.

Hãy trả lời:

1. Vì sao `ObjectFactory` không cần thiết chỉ để tạo DTO từ ba attribute này?
2. Phương án nào phù hợp nếu cần thêm DN: `AttributesMapper` hay `ContextMapper`? Phần nào cần kiểm chứng về DN?
3. Nếu `mail` có thể vắng mặt, nên xử lý ở tầng nào và theo chính sách nào?
4. Nếu thuộc tính `member` của group có nhiều DN, có thể gọi `get()` một lần rồi coi là toàn bộ membership không?
5. Nếu người dùng gửi `uid=lan*`, cách nào bảo đảm dấu sao là ký tự literal khi tìm kiếm chính xác?
6. Nếu có yêu cầu login LDAP, có thể dựa vào DTO được factory tạo để cho phép vào trang admin không?
7. Trường hợp nào khiến `DirObjectFactory` thực sự đáng cân nhắc hơn mapper?
8. Tại sao một entry trả về dưới dạng `Reference` hoặc serialized object cần được xử lý thận trọng?

**Gợi ý đáp án:**

1. `AttributesMapper` tạo DTO đơn giản, công khai logic và không phụ thuộc object-conversion SPI.
2. `ContextMapper` vì có `DirContextOperations`; kiểm tra DN tương đối với base của context và yêu cầu full DN.
3. Mapper/service phân biệt bắt buộc và tùy chọn, không tự làm ứng dụng crash hoặc bịa giá trị.
4. Không; dùng `Attribute.getAll()` và đóng enumeration.
5. Dùng `EqualsFilter` hoặc cơ chế filter encoding an toàn của Spring LDAP.
6. Không; bind xác thực và authority mapping thuộc Spring Security LDAP.
7. Khi phải tích hợp naming/directory provider có hợp đồng object conversion riêng và đã kiểm soát vòng đời/factory tin cậy.
8. Thông tin chuyển đổi có thể tác động tới class loading, deserialization hoặc object creation ngoài ý định của ứng dụng.

## 13. Checklist thiết kế

- [ ] Xác định dữ liệu đầu vào thực sự là `Attributes`, `SearchResult`, `DirContextOperations` hay `Reference`.
- [ ] Chọn mapper/ODM nếu chỉ cần biểu diễn entry LDAP thành object nghiệp vụ.
- [ ] Chỉ dùng JNDI `ObjectFactory`/`DirObjectFactory` khi có nhu cầu SPI cụ thể và provider hỗ trợ.
- [ ] Kiểm tra thuộc tính thiếu, optional, nhiều giá trị, binary và schema.
- [ ] Giữ rõ relative DN/full DN khi lưu định danh entry.
- [ ] Escape input theo LDAP filter; không dùng escape DN để thay filter escaping.
- [ ] Không dùng dữ liệu directory để tải class hoặc deserialize object tùy ý.
- [ ] Quản lý credentials, TLS, ACL và pooling của `ContextSource`.
- [ ] Tách truy vấn dữ liệu khỏi xác thực và phân quyền.
- [ ] Kiểm thử cả mapper ở mức unit và luồng thực tế trên LDAP server.

## 14. Tóm tắt

**JNDI `ObjectFactory` và `DirObjectFactory` là cơ chế mở rộng để biến thông tin naming/directory thành Java object trong những trường hợp provider và cấu hình hỗ trợ.** Chúng không tự chạy với mọi entry LDAP và không phải là lựa chọn mặc định để ánh xạ hồ sơ nhân viên.

Trong **Spring LDAP**, lựa chọn thường rõ hơn: dùng `AttributesMapper` để đọc thuộc tính, `ContextMapper` khi cần context/DN, hoặc ODM/Spring Data LDAP khi mô hình entity ổn định. Việc ánh xạ phải tôn trọng schema, xử lý kiểu/multiplicity và không làm mất kiểm soát bảo mật, đặc biệt khi dữ liệu từ LDAP có thể không đáng tin cậy.

### Tài liệu tham khảo

- [Java SE — ObjectFactory (javax.naming.spi)](https://docs.oracle.com/en/java/javase/17/docs/api/java.naming/javax/naming/spi/ObjectFactory.html)
- [Java SE — DirObjectFactory (javax.naming.spi)](https://docs.oracle.com/en/java/javase/17/docs/api/java.naming/javax/naming/spi/DirObjectFactory.html)
- [Java SE — NamingManager](https://docs.oracle.com/en/java/javase/17/docs/api/java.naming/javax/naming/spi/NamingManager.html)
- [Java SE — DirectoryManager](https://docs.oracle.com/en/java/javase/17/docs/api/java.naming/javax/naming/spi/DirectoryManager.html)
- [Java SE — SearchControls](https://docs.oracle.com/en/java/javase/17/docs/api/java.naming/javax/naming/directory/SearchControls.html)
- [Spring LDAP Reference Documentation](https://docs.spring.io/spring-ldap/reference/)
- [Spring LDAP — Object-Directory Mapping](https://docs.spring.io/spring-ldap/reference/odm.html)
- [Spring Data LDAP — Reference Documentation](https://docs.spring.io/spring-data/ldap/reference/)
- [RFC 4511 — LDAP: The Protocol](https://www.rfc-editor.org/rfc/rfc4511)
- [RFC 4515 — LDAP filter string syntax](https://www.rfc-editor.org/rfc/rfc4515)
