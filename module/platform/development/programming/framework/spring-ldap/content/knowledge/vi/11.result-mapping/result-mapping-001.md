# ContextMapper và ánh xạ entry sang domain object

Khi truy vấn LDAP bằng **Spring LDAP**, kết quả trả về không tự động trở thành một đối tượng Java có kiểu dữ liệu, quy tắc validation và ý nghĩa nghiệp vụ rõ ràng. Ở tầng JNDI, entry chủ yếu được biểu diễn bằng các **thuộc tính LDAP**; trong khi ứng dụng lại muốn sử dụng một kiểu như `EmployeeProfile`, `DirectoryGroup` hoặc `AccountSummary`.

**`ContextMapper<T>`** là callback của Spring LDAP giúp chuyển **một entry LDAP** thành **một đối tượng Java kiểu `T`**. Khác với `AttributesMapper` chỉ nhận tập thuộc tính, `ContextMapper` cho phép tiếp cận **`DirContextOperations`**, từ đó đọc thuộc tính và thông tin tên (DN) mà context kết quả cung cấp. Đây là lựa chọn hữu ích khi domain object cần biết cả **dữ liệu** lẫn **vị trí entry trong cây LDAP**.

Bài thuộc chương **Mapping kết quả** của module **SPRING_LDAP**. Người học sẽ tự viết mapper, sử dụng nó với `LdapTemplate.search` và `lookup`, xử lý thuộc tính bắt buộc/tùy chọn/đa trị, phân biệt DN với các thuộc tính LDAP, và hiểu khi nào nên dùng LDAP ODM hoặc `LdapClient`. Bài cũng đề cập cấu hình `ContextSource`, quyền truy cập, TLS và kiểm thử mapping an toàn.

## 1. Bài toán: entry LDAP không phải domain object

Giả sử directory có một nhân viên:

~~~ldif
dn: uid=linh,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: linh
cn: Linh Nguyen
sn: Nguyen
mail: linh@example.org
mail: linh.work@example.org
ou: Engineering
~~~

Trong JNDI, entry có thể được nhìn dưới dạng các thuộc tính `Attributes`. Nhưng API nội bộ muốn một object có ngữ nghĩa:

~~~java
public record EmployeeProfile(
        String uid,
        String displayName,
        String department,
        java.util.List<String> emails,
        String contextDn) {
    public EmployeeProfile {
        emails = java.util.List.copyOf(emails);
    }
}
~~~

Trong ví dụ, `contextDn` là **tên được callback mapping cung cấp**, không mặc định là DN đầy đủ có thể dùng như khóa định danh toàn hệ thống. Phần `emails` là danh sách vì thuộc tính `mail` của LDAP có thể có **nhiều giá trị**. Record tạo mô hình dữ liệu tách khỏi kết nối LDAP và danh sách được copy để tránh bên gọi sửa tùy tiện.

Một phép ánh xạ cần trả lời các câu hỏi:

- Thuộc tính nào bắt buộc, thuộc tính nào có thể thiếu?
- Một thuộc tính có thể có bao nhiêu giá trị?
- Kiểu dữ liệu Java có phù hợp kiểu dữ liệu LDAP không?
- DN nhận được là dạng nào, và có thể sử dụng lại ở API khác không?
- Nếu quyền LDAP che một thuộc tính, mapper nên làm gì?
- Đối tượng kết quả có nên giữ tham chiếu tới context JNDI không?

Việc đặt ra các quy tắc trên một lần trong mapper giúp lớp service nhất quán hơn và tránh phải ép kiểu/kiểm tra null ở mọi nơi.

## 2. `ContextMapper<T>` nằm ở đâu trong quy trình search?

Trong Spring LDAP, `LdapTemplate` thực hiện truy vấn qua `ContextSource`, nhận entry và gọi mapper cho từng kết quả:

~~~mermaid
flowchart LR
    A["Service"] --> B["LdapQueryBuilder"]
    B --> C["LdapTemplate.search"]
    C --> D["ContextSource / JNDI"]
    D --> E["LDAP server"]
    E --> D
    D --> F["Entry và DirContextOperations"]
    F --> G["ContextMapper<EmployeeProfile>"]
    G --> H["List<EmployeeProfile>"]
    H --> A
~~~

**Đầu vào của `ContextMapper` là `Object`** theo hợp đồng giao diện. Trong cách dùng Spring LDAP thông thường, đối tượng này triển khai `DirContextOperations` (ví dụ `DirContextAdapter`), cho phép lấy thuộc tính và tên. Khi viết mapper, ứng dụng thường ép kiểu về `DirContextOperations` thay vì phụ thuộc trực tiếp vào lớp triển khai cụ thể.

Một dạng khai báo điển hình:

~~~java
import org.springframework.ldap.core.ContextMapper;
import org.springframework.ldap.core.DirContextOperations;

public final class SimpleEmployeeMapper implements ContextMapper<String> {
    @Override
    public String mapFromContext(Object ctx) {
        DirContextOperations entry = (DirContextOperations) ctx;
        return entry.getStringAttribute("cn");
    }
}
~~~

`mapFromContext` được gọi trong quá trình thực hiện search/lookup. Ứng dụng nên **chuyển dữ liệu sang kiểu Java độc lập ngay tại đây**, không giữ `DirContextOperations` trong domain object để truy cập sau khi thao tác đã hoàn tất.

## 3. Phân biệt `AttributesMapper` và `ContextMapper`

Cả hai đều giúp đổi một entry thành đối tượng Java, nhưng chúng có phạm vi đầu vào khác nhau:

| Tiêu chí | `AttributesMapper<T>` | `ContextMapper<T>` |
| --- | --- | --- |
| Đầu vào | `javax.naming.directory.Attributes` | Đối tượng context, thường là `DirContextOperations` |
| Đọc `cn`, `mail`, `uid` | Có | Có |
| Đọc thông tin tên được context cung cấp | Không trực tiếp qua mapper input | Có thể dùng `getDn()` |
| Dùng khi nào? | Chỉ cần một số thuộc tính | Cần cả thuộc tính và tên/context |
| Mức trừu tượng | Gọn cho kết quả đơn giản | Linh hoạt hơn nhưng phải hiểu context |
| Nên trả về gì? | DTO/domain object tách rời JNDI | DTO/domain object tách rời JNDI |

Nếu chỉ cần lấy email:

~~~java
import org.springframework.ldap.core.AttributesMapper;

AttributesMapper<String> emailMapper = attributes -> {
    var mail = attributes.get("mail");
    return mail == null ? null : String.valueOf(mail.get());
};
~~~

Nếu cần cả tên LDAP gắn với kết quả:

~~~java
import org.springframework.ldap.core.ContextMapper;
import org.springframework.ldap.core.DirContextOperations;

ContextMapper<String> nameMapper = ctx -> {
    DirContextOperations entry = (DirContextOperations) ctx;
    return entry.getDn().toString();
};
~~~

**Không phải mọi bài toán mapping đều cần `ContextMapper`.** Khi chỉ đọc thuộc tính, `AttributesMapper` thường đơn giản hơn. Ngược lại, nếu cần tên entry, không nên suy ra DN bằng cách ghép `uid` với một OU cố định: nhân viên có thể nằm trong nhiều OU hoặc entry có thể được rename/move.

## 4. Xây `EmployeeContextMapper` hoàn chỉnh

Một mapper có thể đóng gói chính sách đọc thuộc tính bắt buộc, thuộc tính không bắt buộc và thuộc tính đa trị. Ví dụ:

~~~java
import java.util.Arrays;
import java.util.List;

import org.springframework.ldap.core.ContextMapper;
import org.springframework.ldap.core.DirContextOperations;

public final class EmployeeContextMapper
        implements ContextMapper<EmployeeProfile> {

    @Override
    public EmployeeProfile mapFromContext(Object context) {
        DirContextOperations entry = (DirContextOperations) context;

        String uid = required(entry.getStringAttribute("uid"), "uid");
        String fullName = required(entry.getStringAttribute("cn"), "cn");

        String department = entry.getStringAttribute("ou");

        String[] rawEmails = entry.getStringAttributes("mail");
        List<String> emails = rawEmails == null
                ? List.of()
                : List.copyOf(Arrays.asList(rawEmails));

        String dnFromContext = entry.getDn() == null
                ? ""
                : entry.getDn().toString();

        return new EmployeeProfile(
                uid, fullName, department, emails, dnFromContext);
    }

    private static String required(String value, String attribute) {
        if (value == null || value.isBlank()) {
            throw new IllegalStateException(
                    "LDAP entry thiếu thuộc tính bắt buộc: " + attribute);
        }
        return value;
    }
}
~~~

Các điểm thiết kế:

1. **`uid` và `cn` bắt buộc theo hợp đồng API ví dụ.** Nếu không đọc được chúng, mapper báo lỗi rõ ràng thay vì trả object thiếu định danh.
2. **`ou` là tùy chọn.** Nếu entry thiếu thuộc tính này, domain nhận `null`; ứng dụng có thể chọn `Optional` hoặc một kiểu kết quả chuyên biệt nếu phù hợp hơn.
3. **`mail` là đa trị.** Mapper đọc bằng `getStringAttributes(...)` và trả danh sách bất biến. Không mặc định chỉ lấy một giá trị rồi làm mất các email khác.
4. **DN không được tự ghép.** Mapper lấy tên từ context, không ghép `"uid=" + uid + ...`.
5. **Không giữ context.** `EmployeeProfile` chỉ chứa các giá trị Java, không chứa `DirContextOperations`, `Attributes` hoặc `NamingEnumeration`.

Đoạn mã giả định các thuộc tính tương ứng có giá trị văn bản. Nếu schema cho phép kiểu dữ liệu khác hoặc giá trị được trả về ở dạng byte, phải viết logic chuyển đổi và validation phù hợp.

**Cần phân biệt chính sách ứng dụng và schema LDAP.** `cn` và `sn` thường liên quan tới schema `person`; còn yêu cầu API của ví dụ rằng `uid` bắt buộc là **quy ước của ứng dụng**. Không suy rằng mọi object class LDAP đều yêu cầu cùng các thuộc tính hoặc có cùng số giá trị.

### 4.1. Một mapper nên thuần và dễ kiểm thử

Mapper nên chỉ làm công việc **chuyển đổi dữ liệu**:

- Không gọi thêm LDAP search cho từng entry nếu không thật sự cần, vì có thể sinh **N+1 queries**.
- Không gọi `modifyAttributes` hoặc thay đổi entry trong quá trình ánh xạ kết quả đọc.
- Không tự kết nối mạng, gọi HTTP hoặc đọc secret.
- Không log toàn bộ entry, password, token, email hoặc ảnh cá nhân.
- Không áp quy tắc phân quyền thay cho service hoặc LDAP ACL.

Domain model có thể chứa các quy tắc bất biến như danh sách email không sửa được, nhưng mapper không nên trở thành nơi xử lý mọi nghiệp vụ của công ty.

## 5. Dùng mapper trong `LdapTemplate.search`

Giả sử `ContextSource` có base `dc=example,dc=org` và người dùng được phép tra cứu nhánh `ou=people`. Ta xây query bằng `LdapQueryBuilder` và truyền mapper:

~~~java
import java.util.List;

import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;
import org.springframework.ldap.query.SearchScope;

public final class EmployeeDirectoryRepository {
    private final LdapTemplate template;
    private final EmployeeContextMapper mapper = new EmployeeContextMapper();

    public EmployeeDirectoryRepository(LdapTemplate template) {
        this.template = template;
    }

    public List<EmployeeProfile> findByDepartment(String department) {
        if (department == null || department.isBlank()) {
            throw new IllegalArgumentException("department không được rỗng");
        }

        LdapQuery query = LdapQueryBuilder.query()
                .base("ou=people")
                .searchScope(SearchScope.SUBTREE)
                .countLimit(100)
                .timeLimit(2000)
                .attributes("uid", "cn", "mail", "ou")
                .where("objectClass").is("inetOrgPerson")
                .and("ou").is(department);

        return template.search(query, mapper);
    }
}
~~~

Ý nghĩa các thành phần:

| Cấu hình | Tác dụng |
| --- | --- |
| `base("ou=people")` | Search bắt đầu ở `ou=people`, tương đối với base của `ContextSource` |
| `SearchScope.SUBTREE` | Bao gồm base và các cấp con; chỉ dùng khi nghiệp vụ thực sự cần |
| `countLimit(100)` | Client yêu cầu giới hạn kết quả từ search; server vẫn có thể áp giới hạn khác |
| `timeLimit(2000)` | Giới hạn thời gian search qua API Java tính bằng mili giây; khác timeout mạng |
| `attributes(...)` | Chỉ yêu cầu những thuộc tính mapper cần đọc |
| `where(...).is(...)` | Dựng filter với giá trị từ input được mã hóa phù hợp |
| `template.search(query, mapper)` | Chạy truy vấn và map từng entry sang `EmployeeProfile` |

Vì mapper yêu cầu `uid` và `cn`, danh sách thuộc tính yêu cầu phải **chứa đủ hai trường đó**. Việc thêm một thuộc tính mới vào mapper mà quên cập nhật `attributes(...)` có thể khiến ứng dụng ném lỗi “thiếu thuộc tính” dù entry trên server vẫn có trường đó.

**Quan trọng:** `attributes(...)` là tập thuộc tính *yêu cầu trả về*, không phải một phép cấp quyền. LDAP server chỉ trả những gì cho phép theo ACL và chính sách. Nếu tài khoản không đủ quyền đọc `cn`, mapper có thể nhận giá trị thiếu; cần phân loại vấn đề dữ liệu và vấn đề quyền khi chẩn đoán.

### 5.1. Một filter đúng không tự bảo đảm kết quả đầy đủ

Khi search gặp size limit, time limit, referral hoặc lỗi server, có thể chỉ nhận một phần dữ liệu hoặc exception. Không viết code bắt mọi lỗi rồi trả `List.of()`; điều đó che giấu việc directory đang lỗi.

Ngoài ra, `SUBTREE` dưới một OU lớn có thể đưa về nhiều entry. Giảm base và scope, chỉ yêu cầu thuộc tính cần thiết, đặt giới hạn hợp lý và dùng paging khi server hỗ trợ nếu chức năng phải đọc nhiều trang. `ContextMapper` xử lý từng kết quả **đã được truy vấn trả về**; nó không tự giảm chi phí search trên server.

### 5.2. Khi API cần tìm một định danh duy nhất

Nếu nghiệp vụ yêu cầu người dùng theo `uid`, có thể tìm bằng filter:

~~~java
LdapQuery query = LdapQueryBuilder.query()
        .base("ou=people")
        .searchScope(SearchScope.SUBTREE)
        .attributes("uid", "cn", "mail", "ou")
        .where("objectClass").is("inetOrgPerson")
        .and("uid").is(uid);
~~~

Tuy nhiên, **không mặc định lấy `list.get(0)`** và coi đây là tài khoản duy nhất. Dữ liệu có thể có hai `uid` giống nhau ở những OU khác nhau; kết quả search cũng có thể bị cắt ngắn. Nếu hệ thống cần đảm bảo uniqueness, phải có chính sách ở LDAP server/nguồn dữ liệu và kiểm tra kết quả nghiệp vụ tương ứng.

Nếu đã biết DN rõ ràng theo một cấu trúc tên đáng tin cậy, `lookup` thường phù hợp hơn `search` và tránh một số mơ hồ của filter/search scope.

## 6. Dùng `ContextMapper` trong `lookup` theo DN

`LdapTemplate.lookup` nhận DN của một entry cụ thể; với base `dc=example,dc=org`, DN tương đối để lấy Linh là `uid=linh,ou=people`.

~~~java
import java.util.Optional;
import javax.naming.Name;

import org.springframework.ldap.NameNotFoundException;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

public final class EmployeeLookupRepository {
    private final LdapTemplate template;
    private final EmployeeContextMapper mapper = new EmployeeContextMapper();

    public EmployeeLookupRepository(LdapTemplate template) {
        this.template = template;
    }

    public Optional<EmployeeProfile> findByUid(String uid) {
        if (uid == null || !uid.matches("[a-z0-9._-]{1,64}")) {
            throw new IllegalArgumentException("uid không hợp lệ");
        }

        Name dn = LdapNameBuilder.newInstance("ou=people")
                .add("uid", uid)
                .build();

        try {
            return Optional.of(template.lookup(dn, mapper));
        } catch (NameNotFoundException notFound) {
            return Optional.empty();
        }
    }
}
~~~

Ở đây:

- `LdapNameBuilder` tạo DN theo RDN, không nối chuỗi từ đầu vào.
- `lookup(dn, mapper)` lấy entry và áp dụng cùng chính sách mapping với search.
- `NameNotFoundException` của Spring LDAP có thể được xử lý thành “không tìm thấy”.
- Lỗi bind của tài khoản dịch vụ, TLS, mạng, ACL, schema hoặc mapper **không được đánh đồng** với “không tìm thấy”.

Regex `[a-z0-9._-]{1,64}` là **chính sách input minh họa**, không phải giới hạn chung của LDAP. Khi cần hỗ trợ Unicode hoặc định dạng định danh khác, phải thay bằng validation phù hợp.

Nếu ứng dụng còn phải xác thực người dùng, **việc lookup thành công không phải là authentication**. Xác thực mật khẩu cần LDAP bind hoặc một cơ chế danh tính như IdP, còn quyền nghiệp vụ phải được kiểm tra sau đó.

## 7. DN trong `ContextMapper`: dữ liệu có cấu trúc, không phải chuỗi tùy ý

Một ưu điểm của `ContextMapper` là có thể lấy tên của entry qua `DirContextOperations.getDn()`. Nhưng cần hiểu rõ:

1. DN được cung cấp phụ thuộc **base của `ContextSource`** và ngữ cảnh thao tác; không mặc định nó là DN đầy đủ độc lập với mọi context.
2. Với search, cách biểu diễn tên trong context có thể khác với `SearchResult.getName()` của JNDI thô; đừng suy ra quy tắc bằng cách tách chuỗi.
3. DN có thể thay đổi khi entry bị **rename/move**, nên không nên dùng chuỗi DN làm khóa nghiệp vụ bất biến nếu có một ID khác ổn định hơn.
4. Nếu cần so sánh DN, dùng `javax.naming.ldap.LdapName` hoặc `javax.naming.Name` thay cho `endsWith` và `split(",")`.
5. Nếu cần đưa DN đầy đủ sang hệ thống khác, hãy xác định dạng tên mà API hiện tại cung cấp và kết hợp với base **theo các thành phần RDN**, không ghép chuỗi bằng dấu phẩy.

Ví dụ lấy tên ở dạng `Name`:

~~~java
import javax.naming.Name;
import org.springframework.ldap.core.ContextMapper;
import org.springframework.ldap.core.DirContextOperations;

ContextMapper<Name> dnMapper = context -> {
    DirContextOperations entry = (DirContextOperations) context;
    Name dn = entry.getDn();
    return dn == null ? null : (Name) dn.clone();
};
~~~

Trả về bản sao `Name` giúp object kết quả không giữ một đối tượng tên có thể bị sửa qua tham chiếu chung. Nếu domain chỉ cần hiển thị một giá trị chuỗi, có thể dùng `dn.toString()`, nhưng nên đặt tên field theo **ý nghĩa của tên trong context** thay vì mặc định `fullDn`.

### 7.1. Alias và referral

Một DN được parse thành công không khẳng định entry là một bản ghi cục bộ. LDAP server có thể sử dụng **alias** hoặc trả **referral**, tùy cấu hình dereference/chasing. Một mapper phải ánh xạ **đúng dữ liệu thực sự nhận được** và không che giấu lỗi partial result bằng cách tạo domain object rỗng.

Khi có nhiều LDAP server hoặc naming context, không tự động theo referral tới máy chủ chưa tin cậy rồi gửi credential. Vấn đề này thuộc cấu hình client/server và chính sách bảo mật, không phải chức năng của `ContextMapper`.

## 8. Thuộc tính nhiều giá trị, kiểu dữ liệu và binary

LDAP attribute không nhất thiết là một chuỗi đơn. Mỗi attribute có cú pháp và matching rule theo schema; có thể có **một hoặc nhiều giá trị**.

### 8.1. Thuộc tính đa trị

Ví dụ một nhân viên có hai địa chỉ email:

~~~ldif
mail: linh@example.org
mail: linh.work@example.org
~~~

Nếu mapper gọi `getStringAttribute("mail")`, thường chỉ nhận **một** giá trị, làm mất phần còn lại. Khi nghiệp vụ cần đầy đủ, dùng:

~~~java
String[] values = entry.getStringAttributes("mail");
List<String> emails = values == null
        ? List.of()
        : List.copyOf(java.util.Arrays.asList(values));
~~~

**Đừng dựa vào thứ tự của thuộc tính đa trị** trừ khi schema/giao thức và nghiệp vụ bảo đảm điều đó. LDAP values của một attribute thông thường không có thứ tự mang ý nghĩa. Nếu phải chọn “email chính”, cần một quy tắc xác định rõ, chẳng hạn một thuộc tính riêng được quản trị, không mặc định phần tử đầu tiên luôn là chính.

### 8.2. Thuộc tính thiếu

Phân biệt ba trường hợp:

| Trạng thái | Cách xử lý gợi ý |
| --- | --- |
| `uid` bắt buộc nhưng không được trả | Fail mapping hoặc trả lỗi dữ liệu/phân quyền rõ ràng |
| `mail` tùy chọn và không được trả | Danh sách rỗng hoặc giá trị tùy chọn theo hợp đồng domain |
| `cn` có mặt nhưng kiểu dữ liệu không phù hợp | Báo lỗi schema/mapping, không ép kiểu mù |

Một thuộc tính không xuất hiện trong kết quả có thể vì **entry thiếu thuộc tính**, vì query **không yêu cầu trả thuộc tính đó**, hoặc vì **ACL giới hạn**. Mapper không luôn phân biệt được ba nguyên nhân này. Cần phối hợp kiểm tra query, schema và quyền ở tầng chẩn đoán.

### 8.3. Thuộc tính nhị phân

Một số thuộc tính như `jpegPhoto` có thể chứa dữ liệu nhị phân, không phải `String`. Khi thực sự cần sử dụng, dùng API đọc object attribute và xử lý loại dữ liệu rõ ràng:

~~~java
import java.util.Arrays;
import org.springframework.ldap.core.DirContextOperations;

public final class BinaryAttributeReader {
    private BinaryAttributeReader() {}

    public static byte[] jpegPhotoOrNull(DirContextOperations entry) {
        Object raw = entry.getObjectAttribute("jpegPhoto");
        if (raw == null) {
            return null;
        }
        if (!(raw instanceof byte[] bytes)) {
            throw new IllegalStateException("jpegPhoto không có kiểu byte[]");
        }
        return Arrays.copyOf(bytes, bytes.length);
    }
}
~~~

Bản sao mảng `byte[]` giúp không chia sẻ trực tiếp dữ liệu có thể bị chỉnh sửa. Nếu đặt mảng trong một domain object, cần defensive copy cả khi nhận vào **và** khi trả ra. Ngoài ra, ảnh và dữ liệu nhị phân có thể lớn; đừng đưa `jpegPhoto` vào mọi kết quả search nếu giao diện chỉ hiển thị danh sách tên.

### 8.4. Chuyển đổi kiểu dữ liệu không phải matching rule

LDAP có các cú pháp chuyên biệt cho thời gian, số nguyên, giá trị nhị phân và DN. `ContextMapper` chuyển dữ liệu **đã nhận** thành kiểu Java; nó **không thay đổi** cách LDAP server đánh giá filter hoặc so khớp thuộc tính.

Nếu cần chuyển một chuỗi GeneralizedTime thành `Instant`, phải kiểm tra chính xác cú pháp thời gian, offset và quy tắc của server. Không tự gọi `Instant.parse` lên mọi giá trị LDAP rồi giả định tất cả đều theo ISO 8601 giống nhau.

## 9. Ánh xạ sang domain object hay dùng LDAP ODM?

`ContextMapper` là ánh xạ **tường minh theo từng truy vấn**. Spring LDAP còn có LDAP ODM (*Object-Directory Mapping*) để ánh xạ entry với đối tượng thông qua annotation và cơ chế do framework cung cấp.

| Tiêu chí | `ContextMapper` | LDAP ODM |
| --- | --- | --- |
| Cách ánh xạ | Viết Java trực tiếp trong mapper | Khai báo metadata/annotation và cấu hình |
| Quy tắc thiếu/đa trị | Do mapper quyết định rõ | Phụ thuộc khả năng ODM và mô hình được ánh xạ |
| DTO riêng cho API đọc | Rất phù hợp | Có thể cần thêm bước chuyển từ entity sang DTO |
| Truy vấn chọn ít thuộc tính | Chủ động kiểm soát mapper và projection | Cần hiểu cách ODM tải trường |
| Logic chuyển kiểu đặc thù | Viết trực tiếp | Có thể dùng converter/cơ chế mở rộng phù hợp |
| Khi nào dùng | Projection, hệ thống tích hợp hoặc model đọc linh hoạt | Entity có mapping ổn định, thao tác CRUD lặp lại |

Không có lựa chọn đúng cho mọi bài toán. Nếu ứng dụng chỉ cần danh sách nhân viên với `uid`, `cn`, `mail`, một mapper tường minh rất dễ đọc. Nếu cần quản lý nhiều loại entry có cấu trúc lâu dài, ODM có thể giảm mã lặp, nhưng vẫn phải xét schema, DN, ACL, TLS và khả năng tương thích phiên bản Spring LDAP.

`LdapClient` là API fluent trong các phiên bản hỗ trợ, nhưng **không thay đổi bản chất ánh xạ**: dữ liệu LDAP vẫn cần một chính sách chuyển đổi sang Java, và không được mặc định rằng một entry đọc được đã đủ điều kiện phân quyền.

## 10. Thiết kế mapper an toàn trong ứng dụng thật

Các lớp bảo vệ nên được tách rõ:

~~~mermaid
flowchart TD
    A["HTTP request đã xác thực"] --> B["Service: kiểm tra authorization"]
    B --> C["LdapQueryBuilder: base, scope, filter, projection"]
    C --> D["LdapTemplate trên ContextSource"]
    D --> E["LDAP server: bind identity + ACL"]
    E --> F["DirContextOperations"]
    F --> G["ContextMapper: validation và projection"]
    G --> H["Domain DTO tách khỏi context"]
    H --> I["Response chỉ chứa trường được phép"]
~~~

**Nguyên tắc thực hành:**

1. **Không giao phó authorization cho mapper.** Mapper làm việc sau khi server trả entry; quyền của caller cần được quyết định trước và khi trả DTO.
2. **Chỉ đọc thuộc tính cần thiết.** Không mặc định map `userPassword`, thông tin credential, token hoặc thuộc tính nhạy cảm vào object hiển thị.
3. **Tách tên LDAP khỏi định danh nghiệp vụ.** DN có thể đổi theo OU và không nên là business key bất biến.
4. **Giữ callback thuần.** Mapper không giữ `DirContextOperations` sau search và không tự gọi thêm mạng ở mỗi kết quả.
5. **Đặt base, scope và limit.** Query rộng vừa tốn tài nguyên vừa tăng rủi ro dữ liệu bị đọc quá mức.
6. **Sử dụng TLS.** LDAPS hoặc StartTLS phải xác minh chứng chỉ/hostname, đặc biệt khi dùng bind password.
7. **Phân loại lỗi.** Lỗi mapping, thiếu quyền, mất kết nối, referral hoặc search bị giới hạn không được biến thành kết quả “không có nhân viên”.
8. **Kiểm thử schema và ACL thật.** Mock mapper có thể chạy đúng nhưng server production vẫn có kiểu attribute hay quy tắc truy cập khác.

Phần cấu hình pool/ContextSource thuộc tầng kết nối; mỗi mapper nên độc lập trạng thái và an toàn khi tái sử dụng giữa các lời gọi. Không cache context trong mapper, không tái sử dụng connection dưới danh tính người dùng khác và không đưa email/DN cá nhân vào metric labels có cardinality lớn.

## 11. Kiểm thử mapping: unit test và test tích hợp

### 11.1. Unit test không cần LDAP server

`DirContextAdapter` là một triển khai `DirContextOperations` hữu ích để kiểm thử mapper thuần Java.

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.ldap.core.DirContextAdapter;
import org.springframework.ldap.support.LdapNameBuilder;

class EmployeeContextMapperTest {
    private final EmployeeContextMapper mapper =
            new EmployeeContextMapper();

    @Test
    void mapsMultivaluedMailIntoImmutableDomainData() {
        DirContextAdapter entry = new DirContextAdapter(
                LdapNameBuilder.newInstance("uid=linh,ou=people").build());

        entry.setAttributeValue("uid", "linh");
        entry.setAttributeValue("cn", "Linh Nguyen");
        entry.setAttributeValue("ou", "Engineering");
        entry.setAttributeValues(
                "mail",
                new String[] {"linh@example.org", "linh.work@example.org"});

        EmployeeProfile profile = mapper.mapFromContext(entry);

        assertEquals("linh", profile.uid());
        assertEquals("Linh Nguyen", profile.displayName());
        assertEquals(2, profile.emails().size());
        assertThrows(UnsupportedOperationException.class,
                () -> profile.emails().add("new@example.org"));
    }

    @Test
    void rejectsEntryWithoutRequiredUid() {
        DirContextAdapter entry = new DirContextAdapter(
                LdapNameBuilder.newInstance("uid=unknown,ou=people").build());
        entry.setAttributeValue("cn", "Unknown");

        assertThrows(IllegalStateException.class,
                () -> mapper.mapFromContext(entry));
    }
}
~~~

Test trên kiểm tra **quy tắc của mapper**, không chứng minh LDAP server sẽ trả toàn bộ các thuộc tính đã yêu cầu. `DirContextAdapter` được dựng trong bộ nhớ, không thực hiện kết nối. Trong các phiên bản Spring LDAP cụ thể, cần bảo đảm các constructor/setter sử dụng tương thích với API thực tế của dự án.

Có thể bổ sung unit test cho trường hợp `mail` không tồn tại, `cn` rỗng, nhiều giá trị hoặc DN chứa ký tự đặc biệt. Khi domain record có thêm trường, cập nhật mapper và test cùng lúc để giữ hợp đồng dữ liệu nhất quán.

### 11.2. Test tích hợp với LDAP server

Chuẩn bị LDAP server thử nghiệm có schema `inetOrgPerson`, base `dc=example,dc=org` và nhánh `ou=people`. Chỉ tạo/sửa dữ liệu dưới OU thử nghiệm.

| Ca | Điều kiện | Kết quả mong đợi |
| --- | --- | --- |
| A | Search Linh với `uid`, `cn`, `mail`, `ou` | `EmployeeProfile` đúng các thuộc tính |
| B | `mail` có hai giá trị | Mapping giữ cả hai email |
| C | Entry thiếu `mail` | Danh sách email rỗng theo hợp đồng |
| D | Query bỏ `cn` khỏi requested attributes | Mapper báo thiếu trường bắt buộc |
| E | Tài khoản dịch vụ bị hạn chế đọc `uid` hoặc `cn` | Không trả DTO thiếu định danh như thành công |
| F | `lookup` DN không tồn tại | `Optional.empty()` chỉ cho trường hợp not found |
| G | Search dưới OU con | `ContextMapper` nhận tên entry phù hợp trong context |
| H | Input `uid` chứa `*`/ngoặc | Filter builder không mở rộng cấu trúc truy vấn |
| I | Tìm nhiều entry trùng `uid` ở các OU khác nhau | Service phát hiện bất thường, không chọn phần tử đầu |
| J | `sizeLimitExceeded` hoặc timeout | Không coi tập kết quả từng phần là đầy đủ |
| K | LDAP certificate hoặc bind password không hợp lệ | Báo lỗi kết nối/xác thực, không giả thành danh sách rỗng |
| L | Attribute binary không đúng kiểu kỳ vọng | Mapping có lỗi rõ ràng thay vì ép kiểu mù |

**Một mock `LdapTemplate` chỉ chứng minh mapper được gọi**, không chứng minh kết quả về DN, schema, matching rule, ACL, referral hoặc TLS giống server thật. Cần kiểm thử trên đúng loại server hoặc môi trường có hành vi tương đương dự kiến triển khai.

### 11.3. Bài tập thực hành

**Yêu cầu:** Viết endpoint nội bộ tìm thành viên bộ phận `Engineering` từ nhánh `ou=people`, chỉ trả `uid`, `displayName` và các `email` được phép hiển thị.

Hãy thực hiện theo thứ tự:

1. Tạo `EmployeeProfile` hoặc DTO tương đương, quy định rõ thuộc tính bắt buộc/tùy chọn/đa trị.
2. Viết `ContextMapper` dùng `DirContextOperations`, đọc `uid`, `cn`, `mail` và `ou`; lấy DN từ context nếu nghiệp vụ thực sự cần.
3. Xây `LdapQuery` bằng `LdapQueryBuilder`: base đúng, scope phù hợp, equality filter với `ou`, requested attributes và limit.
4. Dùng `LdapTemplate.search(query, mapper)` để trả danh sách DTO.
5. Thêm test cho email đa trị, thiếu `uid` và trường hợp không có email.
6. Kiểm thử tích hợp trên LDAP test với tài khoản ít quyền và TLS xác minh được.
7. Thử LDAP outage hoặc quyền đọc bị từ chối; xác minh API không giả kết quả thành danh sách rỗng.

**Kết quả mong đợi:** Controller không nhìn thấy `DirContextOperations` hay `Attributes`; mọi dữ liệu được chuyển thành kiểu Java tách biệt, và những lỗi truy cập/thiếu thuộc tính bắt buộc được giữ rõ ràng.

## 12. Câu hỏi tự đánh giá

**Câu 1.** Khi nào `ContextMapper` hữu ích hơn `AttributesMapper`?

**Đáp án:** Khi ngoài các thuộc tính, cần thông tin tên/context của entry như DN mà `DirContextOperations` cung cấp. Nếu chỉ đọc vài thuộc tính, `AttributesMapper` thường gọn hơn.

**Câu 2.** Có nên lưu `DirContextOperations` trong `EmployeeProfile` để đọc thêm thuộc tính sau khi `LdapTemplate.search` kết thúc?

**Đáp án:** Không. Hãy map thành các giá trị Java độc lập ngay trong callback. Context thuộc vòng đời thao tác và không nên được lưu để truy cập tùy tiện về sau.

**Câu 3.** Vì sao `getStringAttribute("mail")` có thể làm mất dữ liệu?

**Đáp án:** `mail` có thể đa trị. Nếu cần giữ tất cả, dùng `getStringAttributes("mail")` và ánh xạ thành danh sách.

**Câu 4.** Nếu `uid` thiếu trong kết quả, có thể khẳng định entry không có `uid` trên LDAP server?

**Đáp án:** Chưa. Có thể query không yêu cầu thuộc tính, ACL hạn chế, hoặc entry thật sự thiếu. Cần kiểm tra query, schema và quyền trước khi kết luận.

**Câu 5.** `entry.getDn()` có luôn là DN đầy đủ ổn định qua mọi môi trường không?

**Đáp án:** Không nên giả định. Dạng tên phụ thuộc context/base và DN có thể đổi khi entry di chuyển/rename. Cần hiểu hợp đồng API và dùng `Name` để xử lý theo thành phần.

**Câu 6.** Mapper có tự bảo vệ khỏi LDAP injection hay phân quyền cho user không?

**Đáp án:** Không. Query builder xử lý cấu trúc filter/escaping; service xác định quyền người gọi, LDAP server thực thi ACL. Mapper chỉ chuyển dữ liệu đã đọc thành đối tượng Java.

**Câu 7.** Có thể xác minh mapping đúng trên mọi LDAP server chỉ bằng unit test `DirContextAdapter` không?

**Đáp án:** Không. Unit test xác minh logic chuyển đổi trong Java; schema, kiểu dữ liệu, ACL, referral và TLS cần test tích hợp.

**Ghi nhớ:** **`ContextMapper<T>`** là cầu nối từ entry LDAP sang domain object **độc lập với JNDI**. Dùng `DirContextOperations` để đọc thuộc tính và DN khi cần, quy định rõ trường bắt buộc/tùy chọn/đa trị, giữ mapper thuần và chỉ trả DTO đã kiểm tra. Kết hợp mapper với `LdapTemplate`, base/scope/filter an toàn, quyền tối thiểu, TLS và test tích hợp để truy cập directory một cách đáng tin cậy.
