# BaseLdapPathContextSource và thao tác theo base path

Khi kết nối thư mục LDAP bằng **Spring LDAP**, ứng dụng phải biết một DN được truyền vào API là **tên đầy đủ** hay **tên tương đối với base path**. Chẳng hạn, entry của Linh có DN `uid=linh,ou=people,dc=example,dc=org`. Nếu `LdapContextSource` đã cấu hình base `dc=example,dc=org`, phần lớn thao tác qua `LdapTemplate` sẽ dùng tên `uid=linh,ou=people`. Truyền cả DN đầy đủ có thể dẫn tới đường dẫn bị lặp base, trả kết quả rỗng hoặc ghi dữ liệu sai vị trí.

**`BaseLdapPathContextSource`** là giao diện của Spring LDAP giúp các thành phần Java biết base LDAP path đang được sử dụng. Trong chương **JNDI và Spring** của module **SPRING_LDAP**, bài này giải thích mối quan hệ giữa `ContextSource`, `BaseLdapPathContextSource` và `LdapTemplate`; hướng dẫn tạo/kiểm tra DN có cấu trúc; thực hành search, lookup, tạo, sửa và xóa entry theo base phù hợp; đồng thời chỉ ra các lưu ý về xác thực, TLS, pooling, giới hạn tìm kiếm và xử lý lỗi.

## 1. Hiểu đúng base DN, DN đầy đủ và DN tương đối

Một thư mục LDAP tổ chức dữ liệu thành **Directory Information Tree (DIT)**. Mỗi entry có một **Distinguished Name (DN)** gồm các **Relative Distinguished Name (RDN)**:

~~~text
uid=linh,ou=people,dc=example,dc=org
│        │         └───────────────── Các domain component
│        └─────────────────────────── Nhánh people
└──────────────────────────────────── RDN của entry Linh
~~~

Nếu `dc=example,dc=org` là base của ứng dụng, ta có:

| Khái niệm | Giá trị | Ý nghĩa |
| --- | --- | --- |
| Base DN | `dc=example,dc=org` | Gốc đặt tên do context sử dụng |
| Full DN | `uid=linh,ou=people,dc=example,dc=org` | Tên hoàn chỉnh trên cây LDAP |
| DN tương đối với base | `uid=linh,ou=people` | Tên thường truyền cho `LdapTemplate` |
| Base của phép search | `ou=people` | Điểm bắt đầu search, tương đối với base của context |
| RDN của entry | `uid=linh` | Thành phần phân biệt entry với các entry cùng cha |

**RDN và DN tương đối không đồng nhất.** `uid=linh` là một RDN, trong khi `uid=linh,ou=people` gồm hai RDN nhưng vẫn là một DN tương đối với `dc=example,dc=org`.

~~~mermaid
flowchart TD
    Root["dc=example,dc=org — base"] --> People["ou=people"]
    Root --> Groups["ou=groups"]
    People --> Linh["uid=linh"]
    People --> Mai["uid=mai"]
    Groups --> Editors["cn=editors"]
~~~

Nếu `ContextSource` đổi base thành `ou=people,dc=example,dc=org`, tên tương đối để lookup chính entry Linh sẽ chỉ là `uid=linh`. **Cấu hình base chỉ thay đổi cách giải tên, không di chuyển entry trên server.**

## 2. Quan hệ giữa JNDI và Spring LDAP

**JNDI** (*Java Naming and Directory Interface*) là API Java cho hệ thống đặt tên và thư mục. Spring LDAP cung cấp các lớp tiện ích phía trên JNDI.

| Thành phần | Trách nhiệm |
| --- | --- |
| `javax.naming.directory.DirContext` | Thao tác JNDI: `lookup`, `search`, `bind`, `modifyAttributes`, `unbind` |
| `org.springframework.ldap.core.ContextSource` | Tạo/cấp context LDAP; cấu hình cơ chế lấy kết nối |
| **`BaseLdapPathContextSource`** | Mở rộng `ContextSource`, cung cấp thông tin base path |
| `LdapContextSource` | Triển khai phổ biến, nhận URL, base DN và danh tính bind |
| `LdapTemplate` | Cung cấp thao tác LDAP, mapper/callback, quản lý context, chuyển đổi lỗi JNDI |
| `LdapClient` | API kiểu fluent trong các phiên bản Spring LDAP hỗ trợ |
| LDAP ODM | Ánh xạ entry và thuộc tính sang đối tượng Java, vẫn sử dụng DN/base của LDAP |

**`BaseLdapPathContextSource` là giao diện**, không phải LDAP server hoặc cơ chế tìm kiếm mới. Ứng dụng dùng nó khi cần biết phần tên cơ sở mà `ContextSource` đã thiết lập, nhất là để dựng DN tuyệt đối hoặc kiểm tra tên đầy đủ có nằm trong vùng cho phép.

Hai phương thức quan trọng:

- **`getBaseLdapName()`** cung cấp base dưới dạng tên LDAP có cấu trúc; thích hợp để dựng, nối và kiểm tra các RDN.
- **`getBaseLdapPath()`** cung cấp base dưới dạng chuỗi; hữu ích khi cần hiển thị cấu hình hoặc giao tiếp với API yêu cầu văn bản.

Ví dụ:

~~~java
import javax.naming.Name;
import org.springframework.ldap.core.support.BaseLdapPathContextSource;

public final class DirectoryBaseInfo {
    private final BaseLdapPathContextSource source;

    public DirectoryBaseInfo(BaseLdapPathContextSource source) {
        this.source = source;
    }

    public Name baseName() {
        return source.getBaseLdapName();
    }

    public String baseAsText() {
        return source.getBaseLdapPath();
    }
}
~~~

Khi kiểm tra phạm vi DN, **không sử dụng `String.endsWith`, `contains` hoặc `split(",")`**. DN có cách escape giá trị, RDN đa trị và thứ tự thành phần riêng; hãy dùng `Name`/`LdapName` để so sánh.

## 3. Cấu hình `LdapContextSource` và base path

Ví dụ bean cấu hình:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ldap.core.ContextSource;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.core.support.LdapContextSource;

@Configuration
public class LdapConfiguration {
    @Bean
    public LdapContextSource ldapContextSource(DirectorySettings settings) {
        LdapContextSource source = new LdapContextSource();
        source.setUrl(settings.url());
        source.setBase(settings.base());
        source.setUserDn(settings.bindDn());
        source.setPassword(settings.bindPassword());
        return source;
    }

    @Bean
    public LdapTemplate ldapTemplate(ContextSource contextSource) {
        return new LdapTemplate(contextSource);
    }

    // DirectorySettings phải được tạo từ cấu hình bảo mật thực tế.
    public record DirectorySettings(
            String url, String base, String bindDn, String bindPassword) {}
}
~~~

Ví dụ giá trị cấu hình bên ngoài ứng dụng:

~~~text
url:     ldaps://directory.example.org:636
base:    dc=example,dc=org
bindDn:  cn=app-reader,ou=service,dc=example,dc=org
secret:  lấy từ secret manager hoặc môi trường bảo mật
~~~

**Phân biệt:**

1. **URL** xác định endpoint LDAP.
2. **Base DN** xác định gốc tên của context.
3. **Bind DN** xác định danh tính tài khoản dùng để kết nối; nó không phải base và không tự cho phép truy cập mọi entry dưới base.

Mẫu này cho thấy luồng dữ liệu cấu hình. Cách tạo/inject `DirectorySettings` phụ thuộc nền tảng cấu hình của ứng dụng; password phải lấy từ nơi bảo mật, không hardcode. Khi dùng LDAPS hoặc StartTLS, cần xác minh hostname và chứng chỉ, đặt timeout hợp lý, cấp quyền tài khoản ở mức tối thiểu và cấu hình pooling theo đúng loại kết nối.

### 3.1. Những hệ quả khi đổi base

| Môi trường | Base DN | DN tương đối của cùng entry Linh |
| --- | --- | --- |
| A | `dc=example,dc=org` | `uid=linh,ou=people` |
| B | `ou=people,dc=example,dc=org` | `uid=linh` |
| C | `dc=another,dc=org` | Entry của Linh tại `dc=example,dc=org` nằm ngoài base |

Nếu một helper luôn thêm `ou=people`, nó phù hợp với A nhưng sẽ làm **lặp OU** tại B. Vì thế, phải thiết kế quy ước base rõ ràng và kiểm thử theo cấu hình thực của từng môi trường. Việc đổi base **không chuyển dữ liệu** từ vùng này sang vùng khác.

## 4. Cách `LdapTemplate` hiểu tên tương đối

Giả sử:

~~~text
Source URL:        ldaps://directory.example.org:636
Source base:       dc=example,dc=org
Tên truyền API:    uid=linh,ou=people
DN thực trên cây:  uid=linh,ou=people,dc=example,dc=org
~~~

`LdapTemplate` lấy context từ `ContextSource` và dùng tên tương đối với base của context cho các thao tác thông thường. Mô hình logic:

~~~text
DN tương đối + base từ ContextSource -> DN đầy đủ
uid=linh,ou=people + dc=example,dc=org -> uid=linh,ou=people,dc=example,dc=org
~~~

Đây là mô tả cách giải tên, **không phải hướng dẫn ghép các DN bằng phép cộng chuỗi Java**.

Ví dụ sai trong cấu hình trên:

~~~java
// Sai: đã mang cả phần base vào lookup vốn mong đợi tên tương đối.
ldapTemplate.lookup("uid=linh,ou=people,dc=example,dc=org");
~~~

Nếu phần base bị áp dụng thêm một lần, tên có thể thành:

~~~text
uid=linh,ou=people,dc=example,dc=org,dc=example,dc=org
~~~

Ví dụ đúng:

~~~java
ldapTemplate.lookup("uid=linh,ou=people");
~~~

Một số API ngoài `LdapTemplate` có thể yêu cầu **DN đầy đủ**, như một số luồng authentication hoặc API cần trao đổi DN với hệ thống khác. Không được dùng mặc định một loại DN cho tất cả thư viện và thao tác. Hãy xác định quy tắc tên của **đúng API đang được gọi**.

### 4.1. Base của search, scope và filter là các quyết định riêng

Nếu `ContextSource` có base `dc=example,dc=org`:

~~~text
Search base:   ou=people
Search scope:  ONELEVEL
Filter:        (&(objectClass=inetOrgPerson)(uid=linh))
Attributes:    cn, mail
~~~

- **Search base `ou=people`** là vị trí bắt đầu trong context.
- **`ONELEVEL`** chỉ xét con trực tiếp của `ou=people`; `SUBTREE` duyệt cả cây con.
- **Filter** xác định entry nào khớp, không thay base.
- **Requested attributes** chỉ định thông tin cần trả về, không quy định vị trí tìm kiếm.

Không vì mong tìm một người mà tự đặt base quá rộng. Kết hợp base, scope, filter và giới hạn kết quả giúp giảm tải và tránh đọc dữ liệu ngoài nhu cầu nghiệp vụ.

## 5. Dựng DN tương đối và tuyệt đối bằng `LdapNameBuilder`

Trong phần lớn API nghiệp vụ, nên nhận một định danh như `uid` rồi **tự xây DN trong nhánh đã cấu hình**. Không cho client HTTP tùy chọn DN đầy đủ để thực hiện ghi/xóa.

~~~java
import javax.naming.ldap.LdapName;
import org.springframework.ldap.core.support.BaseLdapPathContextSource;
import org.springframework.ldap.support.LdapNameBuilder;

public final class EmployeeDnFactory {
    private final BaseLdapPathContextSource source;

    public EmployeeDnFactory(BaseLdapPathContextSource source) {
        this.source = source;
    }

    // Quy ước: source.base = dc=example,dc=org.
    public LdapName relativeDn(String uid) {
        validateUid(uid);
        return LdapNameBuilder.newInstance("ou=people")
                .add("uid", uid)
                .build();
    }

    // Dùng khi API đích thực sự cần DN đầy đủ.
    public LdapName absoluteDn(String uid) {
        validateUid(uid);
        return LdapNameBuilder
                .newInstance(source.getBaseLdapName())
                .add("ou", "people")
                .add("uid", uid)
                .build();
    }

    private static void validateUid(String uid) {
        if (uid == null || !uid.matches("[a-z0-9._-]{1,64}")) {
            throw new IllegalArgumentException("uid không hợp lệ");
        }
    }
}
~~~

Với base `dc=example,dc=org`:

~~~text
relativeDn("linh") = uid=linh,ou=people
absoluteDn("linh") = uid=linh,ou=people,dc=example,dc=org
~~~

Regex là **chính sách định danh minh họa của ứng dụng**, không phải giới hạn bắt buộc của LDAP. Nếu cho phép tên chứa Unicode hoặc ký tự đặc biệt, phải định nghĩa validation phù hợp. `LdapNameBuilder` giúp tạo RDN có cấu trúc và escape đúng ký tự theo cú pháp DN; validation kiểm soát giá trị nào được nghiệp vụ chấp nhận.

**Không trộn escaping DN với escaping filter.** Ví dụ `cn=Nguyen\, Linh,ou=people` dùng quy tắc DN, còn `(cn=Nguyen, Linh)` là filter có cú pháp khác. Khi truy vấn từ input, dùng `LdapQueryBuilder` hoặc filter builder thay vì nối chuỗi.


## 6. Search, lookup và thao tác entry theo base path

### 6.1. Search với base tương đối

Ví dụ tìm email nhân viên theo `uid`:

~~~java
import java.util.List;
import javax.naming.directory.Attribute;

import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;
import org.springframework.ldap.query.SearchScope;

public final class EmployeeReader {
    private final LdapTemplate ldapTemplate;

    public EmployeeReader(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<String> findEmails(String uid) {
        if (uid == null || uid.isBlank()) {
            throw new IllegalArgumentException("uid không được rỗng");
        }

        LdapQuery query = LdapQueryBuilder.query()
                .base("ou=people")
                .searchScope(SearchScope.ONELEVEL)
                .attributes("mail")
                .where("objectClass").is("inetOrgPerson")
                .and("uid").is(uid);

        return ldapTemplate.search(
                query,
                (AttributesMapper<String>) attrs -> {
                    Attribute mail = attrs.get("mail");
                    return mail == null ? null : (String) mail.get();
                });
    }
}
~~~

Với source.base là `dc=example,dc=org`, `.base("ou=people")` chọn gốc tìm kiếm **tương đối với base đã cấu hình**. Scope `ONELEVEL` chỉ xét các entry con trực tiếp của `ou=people`; nếu có nhánh OU con, cần đánh giá liệu có cần `SUBTREE`.

API `.where(...).is(uid)` giữ `uid` ở vai trò **giá trị filter** và xử lý escaping; không nên nối input người dùng thành LDAP filter thô. Ở ứng dụng thực tế, nên dùng DTO thay cho các phần tử `null` trong kết quả, giới hạn số lượng entry, xử lý quyền đọc và các trường hợp lỗi mạng/referral.

### 6.2. Lookup bằng DN tương đối

Khi đã biết DN, `lookup` truy vấn một entry cụ thể:

~~~java
import java.util.Optional;

import org.springframework.ldap.NameNotFoundException;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;

public final class EmployeeLookup {
    private final LdapTemplate ldapTemplate;
    private final EmployeeDnFactory names;

    public EmployeeLookup(LdapTemplate ldapTemplate,
                          EmployeeDnFactory names) {
        this.ldapTemplate = ldapTemplate;
        this.names = names;
    }

    public Optional<String> displayName(String uid) {
        try {
            String value = ldapTemplate.lookup(
                    names.relativeDn(uid),
                    (AttributesMapper<String>) attrs -> {
                        var cn = attrs.get("cn");
                        return cn == null ? null : (String) cn.get();
                    });
            return Optional.ofNullable(value);
        } catch (NameNotFoundException ex) {
            return Optional.empty();
        }
    }
}
~~~

Ví dụ này chỉ chuyển lỗi **không tìm thấy entry** thành `Optional.empty()`. Lỗi thiếu quyền, kết nối TLS, timeout, danh tính bind hoặc referral **không phải bằng chứng entry không tồn tại**, nên cần xử lý riêng.

### 6.3. `LdapTemplate.bind` tạo entry, không phải authentication bind

Để thêm một entry mới, `LdapTemplate.bind(...)` nhận DN tương đối và tập thuộc tính theo schema:

~~~java
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.BasicAttributes;
import org.springframework.ldap.core.LdapTemplate;

public final class EmployeeCreator {
    private final LdapTemplate template;
    private final EmployeeDnFactory names;

    public EmployeeCreator(LdapTemplate template, EmployeeDnFactory names) {
        this.template = template;
        this.names = names;
    }

    public void create(String uid, String fullName, String surname) {
        BasicAttributes attrs = new BasicAttributes(true);
        BasicAttribute classes = new BasicAttribute("objectClass");
        classes.add("top");
        classes.add("person");
        classes.add("organizationalPerson");
        classes.add("inetOrgPerson");
        attrs.put(classes);
        attrs.put("uid", uid);
        attrs.put("cn", fullName);
        attrs.put("sn", surname);

        // Giả định caller đã kiểm tra quyền và các giá trị đầu vào.
        template.bind(names.relativeDn(uid), null, attrs);
    }
}
~~~

Ví dụ giả định entry cha `ou=people` đã tồn tại và schema server hỗ trợ `inetOrgPerson`. Tài khoản dịch vụ phải được ACL cho phép tạo entry trong nhánh. Trước khi gọi, ứng dụng cần kiểm tra quyền người yêu cầu, validation và chính sách định danh. Hai request tạo cùng DN có thể xung đột; **lookup trước khi bind không loại trừ tranh chấp đồng thời**, nên phải xử lý lỗi server trả về.

Từ **bind** có hai nghĩa thường gây nhầm lẫn:

| Cách dùng | Ý nghĩa |
| --- | --- |
| `LdapTemplate.bind(name, obj, attrs)` | Tạo một entry tại DN được chỉ định |
| LDAP authentication bind | Gửi danh tính và thông tin xác thực để máy chủ xác minh người dùng |

Tìm được một entry bằng lookup cũng không có nghĩa người dùng đã được xác thực.

### 6.4. Sửa hoặc xóa phải kiểm soát phạm vi

Các thao tác `LdapTemplate.modifyAttributes(...)` và `LdapTemplate.unbind(...)` dùng tên tương đối theo base của ContextSource. Trước khi xóa cần xác minh:

1. Người gọi đã được xác thực và có quyền xóa nhân viên.
2. DN được xây từ `uid` theo quy tắc của ứng dụng; client không thể tự chọn OU quản trị.
3. Đối tượng thuộc đúng nhánh, đúng độ sâu và loại entry được phép.
4. Tài khoản LDAP có quyền tối thiểu và ACL chặn thao tác ngoài phạm vi.
5. Đã xét các ràng buộc nghiệp vụ như yêu cầu duyệt, tài khoản đặc biệt, dữ liệu tham chiếu.
6. Lỗi entry không có, entry còn con, từ chối quyền, referral và timeout được phân loại.

Sau các kiểm tra, thao tác xóa mới có thể là:

~~~java
// Chỉ thực hiện khi authorization và chính sách xóa đã hợp lệ.
ldapTemplate.unbind(names.relativeDn(uid));
~~~

**Base path không phải ACL.** Việc source.base là `dc=example,dc=org` không tự ngăn một tài khoản dịch vụ có quyền rộng xóa entry trong `ou=groups`. Ngăn chặn phải nằm ở chính sách của ứng dụng và quyền trên LDAP server.

## 7. Chuyển DN đầy đủ thành DN tương đối an toàn

Một số hệ thống tích hợp có thể cung cấp DN đầy đủ. Để chuyển thành DN tương đối, không tự cắt suffix bằng `substring` hoặc `replace`:

~~~java
// Không dùng cách này để xác minh ranh giới DN.
String relative = fullDn.replace(",dc=example,dc=org", "");
~~~

DN có escaping và có thể chứa RDN đa trị. Hãy parse thành `LdapName`, đối chiếu `getBaseLdapName()` theo **thành phần RDN**, rồi chỉ chấp nhận nhánh ứng dụng quản lý.

Ví dụ này chỉ cho phép người dùng **trực tiếp dưới `ou=people`**, trong cấu hình base là suffix domain:

~~~java
import javax.naming.InvalidNameException;
import javax.naming.Name;
import javax.naming.ldap.LdapName;
import javax.naming.ldap.Rdn;

import org.springframework.ldap.core.support.BaseLdapPathContextSource;
import org.springframework.ldap.support.LdapNameBuilder;

public final class EmployeeNameConverter {
    private final BaseLdapPathContextSource source;

    public EmployeeNameConverter(BaseLdapPathContextSource source) {
        this.source = source;
    }

    public LdapName toRelativeEmployeeDn(String fullDnText) {
        final LdapName full;
        try {
            full = new LdapName(fullDnText);
        } catch (InvalidNameException | NullPointerException ex) {
            throw new IllegalArgumentException("DN sai cú pháp", ex);
        }

        Name base = source.getBaseLdapName();
        if (base.size() == 0
                || !full.startsWith(base)
                || full.size() != base.size() + 2) {
            throw new IllegalArgumentException("DN ngoài vùng cho phép");
        }

        Name relative = full.getSuffix(base.size());
        Name people = LdapNameBuilder.newInstance("ou=people").build();
        if (!relative.startsWith(people)) {
            throw new IllegalArgumentException("DN không thuộc ou=people");
        }

        Rdn leaf = full.getRdn(full.size() - 1);
        if (leaf.size() != 1
                || !"uid".equalsIgnoreCase(leaf.getType())
                || leaf.getValue() == null
                || leaf.getValue().toString().isBlank()) {
            throw new IllegalArgumentException("RDN cuối phải là uid");
        }

        return LdapNameBuilder.newInstance(relative).build();
    }
}
~~~

**Tại sao dùng `full.startsWith(base)`?** Trong `javax.naming.ldap.LdapName`, thứ tự thành phần của `Name` được biểu diễn từ **gốc đến lá**. Với DN `uid=linh,ou=people,dc=example,dc=org`, index `0` là `dc=org`. Vì vậy phần base ở **cuối biểu diễn văn bản DN** nằm ở **đầu danh sách thành phần JNDI**.

~~~text
Full:     uid=linh,ou=people,dc=example,dc=org
Base:     dc=example,dc=org
Relative: uid=linh,ou=people
~~~

| DN đầy đủ | Kết quả |
| --- | --- |
| `uid=linh,ou=people,dc=example,dc=org` | Chấp nhận; trả `uid=linh,ou=people` |
| `uid=linh,ou=admins,dc=example,dc=org` | Từ chối vì sai OU |
| `uid=linh,ou=archive,ou=people,dc=example,dc=org` | Từ chối vì quá sâu |
| `ou=people,dc=example,dc=org` | Từ chối vì là chính OU |
| `cn=linh,ou=people,dc=example,dc=org` | Từ chối vì RDN lá sai loại |
| `uid=linh,ou=people,dc=other,dc=org` | Từ chối vì ngoài base |

Phép kiểm tra trên giả định **base của source chỉ là suffix domain**, không phải chính `ou=people`. Nó cũng từ chối base rỗng để tránh một tác vụ nhạy cảm mất ranh giới tên. Nếu ứng dụng có cây nhân viên nhiều cấp hoặc base sâu hơn, phải viết chính sách tương ứng và kiểm thử. **DN hợp lệ và trong nhánh chưa bảo đảm entry có tồn tại hay được phép xóa**; cần thêm kiểm tra nghiệp vụ và ACL.

## 8. JNDI trực tiếp và giới hạn của base path

Spring LDAP thường dùng JNDI phía dưới. Khi tự thao tác với `DirContext`, cần giải phóng context đúng cách:

~~~java
import javax.naming.Name;
import javax.naming.NamingException;
import javax.naming.directory.Attributes;
import javax.naming.directory.DirContext;

import org.springframework.ldap.core.ContextSource;

public final class DirectJndiReader {
    private final ContextSource source;

    public DirectJndiReader(ContextSource source) {
        this.source = source;
    }

    public Attributes read(Name relativeDn) throws NamingException {
        DirContext ctx = source.getReadOnlyContext();
        try {
            return ctx.getAttributes(
                    relativeDn, new String[] {"cn", "mail"});
        } finally {
            ctx.close();
        }
    }
}
~~~

Ở đây context được lấy từ source đã cấu hình base, nên tên truyền cho context được diễn giải tương đối với gốc đó. Nếu tự tạo `InitialDirContext` từ provider URL/cấu hình khác, cách giải tên có thể khác. `LdapTemplate` thường thuận tiện hơn vì hỗ trợ lấy/đóng context và chuyển đổi lỗi JNDI.

**`getReadOnlyContext()` không tự tạo ACL bất biến chỉ-đọc trên server**; quyền thực tế vẫn phụ thuộc danh tính bind và ACL. Tương tự, `BaseLdapPathContextSource` cung cấp base để quản lý tên, chứ không thay thế authorization.

## 9. Chẩn đoán, bảo mật và kiểm thử

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Lookup không tìm thấy entry dù DN đúng cú pháp | Full DN bị lặp base, hoặc base cấu hình sai | Kiểm tra `getBaseLdapName()` và DN tương đối |
| Chạy được ở môi trường A nhưng lỗi ở B | Cấu hình base khác; helper thêm OU dư | Đối chiếu quy ước base theo môi trường |
| DN chứa dấu phẩy bị parse sai | Tự nối chuỗi, không escape DN | Dùng `LdapNameBuilder` |
| Search trả ngoài phạm vi | Search base hoặc scope quá rộng | Kiểm tra base query, scope và filter |
| Xóa nhầm đối tượng | Thiếu validation nhánh, quyền quá rộng | Dựng tên từ uid, kiểm tra ACL và authorization |
| Search thấy người dùng nhưng login thất bại | Lookup khác authentication bind | Kiểm tra luồng xác thực riêng |
| Lỗi TLS/timeout/referral | Endpoint, chứng chỉ, network hoặc naming context khác | Phân biệt lỗi hạ tầng với “không có entry” |

Đối với Spring LDAP, cần kết hợp **LDAPS hoặc StartTLS**, xác minh chứng chỉ và hostname, bảo vệ secret, timeout kết nối/đọc và giới hạn tìm kiếm. Tài khoản dịch vụ chỉ nên có quyền cần thiết; pooling phải tôn trọng danh tính của context và không dùng nhầm kết nối giữa người dùng. Khi xử lý referral, không mặc nhiên gửi credential tới endpoint chưa tin cậy. Các API `LdapClient` hay LDAP ODM có thể thay đổi cách viết thao tác nhưng **không tự xử lý thay ứng dụng các quyết định về base, ACL và ranh giới tin cậy**.

### 9.1. Kiểm thử bằng dữ liệu mẫu

Giả sử `dc=example,dc=org` đã tồn tại. Dữ liệu LDIF minh họa:

~~~ldif
dn: ou=people,dc=example,dc=org
objectClass: top
objectClass: organizationalUnit
ou: people

dn: uid=linh,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: linh
cn: Linh Nguyen
sn: Nguyen
mail: linh@example.org
~~~

| Ca kiểm thử | Điều kiện | Kết quả mong đợi |
| --- | --- | --- |
| A | Base `dc=example,dc=org`, lookup `uid=linh,ou=people` | Tìm đúng entry |
| B | Cùng base, search `ou=people` với scope `ONELEVEL` | Chỉ xét entry con trực tiếp |
| C | Base đổi thành `ou=people,dc=example,dc=org` | Tên tương đối để lookup là `uid=linh` |
| D | Converter nhận DN thuộc `ou=admins` | Từ chối |
| E | Converter nhận DN sâu hơn một cấp | Từ chối |
| F | Tạo trùng cùng DN | Server báo trùng, không ghi đè |
| G | Tài khoản bind thiếu quyền ghi | LDAP server từ chối |
| H | Endpoint TLS hoặc kết nối lỗi | Phân loại lỗi hạ tầng, không coi là entry không có |

Có thể unit test tạo/so sánh `LdapName` mà không cần LDAP server. Nhưng schema, ACL, search, authentication, TLS và các thao tác tạo/sửa/xóa thực tế phải được kiểm thử tích hợp trên một server phù hợp. Không chỉ dùng mock để kết luận hệ thống đã giới hạn quyền; thao tác ghi/xóa nên chạy trên dữ liệu test cô lập.

### 9.2. Bài tập tình huống

**Bối cảnh:** Ứng dụng nhân sự chạy ở hai môi trường: A đặt base `dc=example,dc=org`, B đặt base `ou=people,dc=example,dc=org`. API nhận `uid=linh` để lookup, đồng thời cần gửi DN đầy đủ sang một hệ thống khác.

**Hướng giải:** A lookup `uid=linh,ou=people`, B lookup `uid=linh`. Khi cần DN đầy đủ, đọc base từ **đúng `BaseLdapPathContextSource`** rồi thêm các RDN cần thiết bằng `LdapNameBuilder`. Không hardcode base và không cho client tự chọn DN khi thực hiện xóa. Quy tắc dựng DN phải được điều chỉnh theo base thực của từng môi trường.

### 9.3. Câu hỏi tự đánh giá

**Câu 1.** `BaseLdapPathContextSource` có tự tìm kiếm LDAP không?

**Đáp án:** Không. Giao diện này cung cấp context và base path. `LdapTemplate`, `LdapClient` hoặc JNDI mới thực hiện thao tác.

**Câu 2.** Source có base `dc=example,dc=org`; entry có full DN `uid=linh,ou=people,dc=example,dc=org`. Tên nào thường dùng trong `LdapTemplate.lookup`?

**Đáp án:** `uid=linh,ou=people`.

**Câu 3.** Tại sao nên dùng `getBaseLdapName()` hơn phép `endsWith(getBaseLdapPath())` để kiểm tra nhánh?

**Đáp án:** `Name`/`LdapName` biểu diễn các RDN; so sánh theo cấu trúc tránh lỗi với escaping và những chuỗi có đoạn trông giống base.

**Câu 4.** Đổi base từ `dc=example,dc=org` sang `ou=people,dc=example,dc=org` có cần đổi tên tương đối của Linh không?

**Đáp án:** Có. Khi base đã là `ou=people` thì tên tương đối chỉ còn `uid=linh`.

**Câu 5.** Base path có thay thế kiểm tra quyền của người gọi và ACL server không?

**Đáp án:** Không. Base định nghĩa gốc giải tên, còn authorization và ACL quyết định ai được đọc, tạo, sửa hoặc xóa.

**Câu 6.** `LdapTemplate.bind(...)` có dùng để xác thực mật khẩu người dùng không?

**Đáp án:** Không. Đây là thao tác tạo entry; authentication bind là cơ chế xác thực riêng.

**Ghi nhớ:** `BaseLdapPathContextSource` giúp biết **base DN thực của nguồn kết nối**. Khi gọi `LdapTemplate`, hãy dùng DN **tương đối với đúng base**; dựng DN bằng `LdapNameBuilder`, kiểm tra theo thành phần RDN, và giữ nguyên các lớp bảo vệ như TLS, ACL, authorization và xử lý lỗi.

