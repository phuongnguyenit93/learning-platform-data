# Kiểm tra DN trước khi bind, lookup hoặc delete

Trong Spring LDAP, nhiều thao tác nhận **Distinguished Name (DN)** làm đầu vào. Một DN sai có thể khiến ứng dụng tìm không thấy entry, thao tác nhầm nhánh thư mục hoặc xóa sai đối tượng. Nguy hiểm hơn, **DN hợp lệ về cú pháp chưa chắc là DN mà ứng dụng được phép sử dụng**. Trước khi gọi `lookup`, `bind` hay `unbind`, ứng dụng cần kiểm tra cách tạo DN, phạm vi được phép truy cập, quyền người yêu cầu và dữ liệu thực tế trên máy chủ.

Bài này thuộc phần **DN và Name** của module **Spring LDAP**. Người học sẽ sử dụng `LdapName` và `LdapNameBuilder` để xử lý DN an toàn, hiểu cách `ContextSource` áp dụng base DN, phân biệt hai nghĩa của từ “bind”, và thiết kế thao tác qua `LdapTemplate` có khả năng kiểm soát lỗi và kiểm thử.

## 1. DN là gì và tại sao phải kiểm tra?

LDAP tổ chức dữ liệu dưới dạng cây thư mục (**Directory Information Tree – DIT**). Mỗi entry có một **Distinguished Name** định vị entry trong cây. Ví dụ:

~~~text
uid=linh,ou=people,dc=example,dc=org
│        │         │          └── Domain component
│        │         └───────────── Domain component
│        └─────────────────────── Organizational unit
└──────────────────────────────── Relative distinguished name (RDN)
~~~

Trong chuỗi trên:

- `uid=linh` là **RDN** (*Relative Distinguished Name*) của entry người dùng.
- `ou=people` là RDN của nhánh chứa entry.
- `dc=example,dc=org` là phần tên thư mục cấp trên.
- Toàn bộ chuỗi `uid=linh,ou=people,dc=example,dc=org` là **DN**, gồm các RDN theo thứ tự từ entry đến gốc khi viết dưới dạng văn bản thông thường.

DN không phải một URL, không phải SQL primary key và cũng không đơn giản là chuỗi tùy ý. Nó tuân theo quy tắc cú pháp DN (được mô tả trong RFC 4514), đồng thời được LDAP server diễn giải theo schema và naming rules.

**Ba câu hỏi khác nhau** cần được trả lời:

| Câu hỏi | Ví dụ | Mức kiểm tra |
| --- | --- | --- |
| DN có parse được không? | `uid=linh,ou=people,dc=example,dc=org` | Cú pháp |
| DN có nằm đúng vùng ứng dụng quản lý không? | Chỉ thao tác dưới `ou=people,dc=example,dc=org` | Phạm vi và cấu trúc |
| Thao tác có hợp lệ và được phép không? | Người hiện tại có quyền xóa entry của Linh? Entry có tồn tại? | Chính sách nghiệp vụ, ACL và trạng thái LDAP |

Không được gộp ba câu hỏi thành một phép kiểm tra chuỗi.

## 2. Rủi ro thường gặp khi truyền DN thẳng vào API

Giả sử backend có endpoint xóa nhân viên:

~~~java
// Ví dụ nguy hiểm: nhận một DN tùy ý từ request.
public void delete(String dnFromRequest)
        throws javax.naming.InvalidNameException {
    ldapTemplate.unbind(new LdapName(dnFromRequest));
}
~~~

Đoạn trên chỉ để lỗi cú pháp `InvalidNameException` đi ra ngoài. Ngay cả khi bổ sung `try/catch`, logic vẫn có thể xóa entry ở nhánh không mong muốn nếu tài khoản kết nối LDAP được cấp quyền rộng.

Ví dụ, ứng dụng vốn chỉ cho phép xóa người dùng dưới `ou=people` nhưng client có thể gửi:

~~~text
cn=admin,ou=service-accounts,dc=example,dc=org
~~~

Đây có thể là một **DN hợp lệ** nhưng **không phải mục tiêu xóa được phép**. Cũng không nên thử phòng tránh bằng:

~~~java
// Không an toàn: dễ nhầm ranh giới RDN và biến thể biểu diễn.
if (dnFromRequest.contains("ou=people")) {
    ldapTemplate.unbind(new LdapName(dnFromRequest));
}
~~~

Kiểm tra `contains`, `endsWith` hoặc tách tên theo dấu phẩy không thể thay thế parser DN: giá trị RDN có thể chứa các ký tự phải escape, DN có thể có nhiều thuộc tính trong một RDN, và có thể có khác biệt về kiểu chữ hoặc dạng biểu diễn.

Thiết kế an toàn hơn là **cho ứng dụng tự xây DN từ các thành phần được phép** (ví dụ một `uid` đã được kiểm tra), chỉ chấp nhận DN đầy đủ từ bên ngoài trong trường hợp thật sự cần và luôn kiểm tra quyền riêng với kiểm tra cú pháp.

## 3. Parse DN: dùng `LdapName` thay vì tách chuỗi

Java cung cấp `javax.naming.ldap.LdapName`, triển khai giao diện `javax.naming.Name`. `LdapName` phân tích một DN thành các RDN, cho phép so sánh phạm vi theo **thành phần tên**.

~~~java
import javax.naming.InvalidNameException;
import javax.naming.ldap.LdapName;

public final class DnParser {
    private DnParser() {}

    public static LdapName parse(String value) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("DN không được rỗng");
        }
        try {
            return new LdapName(value);
        } catch (InvalidNameException ex) {
            throw new IllegalArgumentException("DN sai cú pháp", ex);
        }
    }
}
~~~

Ví dụ:

~~~java
LdapName dn = DnParser.parse(
        "uid=linh,ou=people,dc=example,dc=org");
System.out.println(dn.size());            // 4
System.out.println(dn.getRdn(3).getType()); // uid
~~~

**Chú ý thứ tự index trong JNDI:** `LdapName` lưu thành phần theo hướng từ gốc đến lá. Với DN trên, index `0` là `dc=org` và index `3` là `uid=linh`. Khi cần RDN của chính entry, dùng `getRdn(dn.size() - 1)`, không mặc định đó là `getRdn(0)`.

**Parse thành công chỉ nói rằng chuỗi biểu diễn được một DN.** Parser không kết nối LDAP server, không kiểm tra entry có tồn tại hay không, không xác nhận object class và không cấp quyền truy cập.

### 3.1. Những ký tự phải xử lý đúng

DN có quy tắc escape riêng. Ví dụ nếu giá trị của `cn` là `Nguyen, Linh` thì DN hợp lệ cần thể hiện dấu phẩy trong giá trị:

~~~text
cn=Nguyen\, Linh,ou=people,dc=example,dc=org
~~~

Nếu nối chuỗi trực tiếp:

~~~java
String unsafe = "cn=" + displayName + ",ou=people,dc=example,dc=org";
~~~

thì dấu phẩy trong tên có thể bị diễn giải thành ranh giới RDN. Ngoài dấu phẩy, các ký tự như dấu cộng, dấu gạch chéo ngược, dấu ngoặc kép và một số vị trí đặc biệt của dấu cách hoặc `#` cũng cần được biểu diễn theo quy tắc DN.

**Quy tắc escape DN khác quy tắc escape LDAP search filter.** Chẳng hạn, `*`, `(`, `)`, ký tự NUL có ý nghĩa đặc biệt trong cú pháp filter (RFC 4515). Vì vậy, không lấy một hàm xử lý filter để thay cho hàm dựng DN, cũng không tự escape bằng vài phép `replace` tùy tiện.

## 4. Xây DN an toàn với `LdapNameBuilder`

Spring LDAP cung cấp `org.springframework.ldap.support.LdapNameBuilder`. Builder nhận từng **tên thuộc tính RDN** và **giá trị**, sau đó dựng DN với escaping phù hợp.

~~~java
import javax.naming.ldap.LdapName;
import org.springframework.ldap.support.LdapNameBuilder;

public final class EmployeeDnFactory {
    private EmployeeDnFactory() {}

    // DN tương đối khi ContextSource.base = dc=example,dc=org
    public static LdapName fromUid(String uid) {
        if (uid == null || !uid.matches("[a-z0-9._-]{1,64}")) {
            throw new IllegalArgumentException("uid không phù hợp chính sách");
        }

        return LdapNameBuilder.newInstance("ou=people")
                .add("uid", uid)
                .build();
    }
}
~~~

Với `uid=linh`, kết quả là `uid=linh,ou=people`. Giá trị mẫu `[a-z0-9._-]{1,64}` chỉ là **chính sách định danh của ứng dụng ví dụ**, không phải giới hạn của LDAP. Ứng dụng hỗ trợ Unicode hoặc định dạng tài khoản khác phải thiết kế quy tắc riêng. Builder xử lý biểu diễn DN; validation nghiệp vụ quyết định giá trị nào được phép.

**Ưu tiên nhận `uid` hoặc business key từ API, rồi tự dựng DN.** Cách này tránh việc client lựa chọn nhánh thư mục, đồng thời giảm nguy cơ viết nhầm entry hoặc mở rộng phạm vi thao tác.

## 5. DN đầy đủ và DN tương đối với `ContextSource`

Trong Spring LDAP, `LdapContextSource` thường được cấu hình một **base DN**:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ldap.core.ContextSource;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.core.support.LdapContextSource;

@Configuration
public class LdapConfiguration {
    @Bean
    public LdapContextSource ldapContextSource() {
        LdapContextSource source = new LdapContextSource();
        source.setUrl("ldaps://directory.example.org:636");
        source.setBase("dc=example,dc=org");
        source.setUserDn(
                "cn=app-reader,ou=service,dc=example,dc=org");
        // Mật khẩu nên lấy từ secret manager/config an toàn.
        return source;
    }

    @Bean
    public LdapTemplate ldapTemplate(ContextSource contextSource) {
        return new LdapTemplate(contextSource);
    }
}
~~~

Đây chỉ là đoạn minh họa sự khác nhau giữa **base DN** và **DN dùng trong thao tác**; không phải cấu hình hoàn chỉnh để kết nối, vì còn thiếu bí mật tài khoản, truststore/TLS và các timeout theo môi trường.

Nếu base là `dc=example,dc=org`:

| Mục đích | DN |
| --- | --- |
| DN đầy đủ trên LDAP server | `uid=linh,ou=people,dc=example,dc=org` |
| DN truyền cho các thao tác `LdapTemplate` dựa trên base đã cấu hình | `uid=linh,ou=people` |
| DN nhánh dùng làm base của search tương đối | `ou=people` |

Các phương thức của `LdapTemplate` thường làm việc với **DN tương đối so với base của `ContextSource`**. Truyền nhầm DN đầy đủ vào nơi mong đợi DN tương đối có thể làm phần base bị ghép lặp hoặc khiến lookup thất bại. Ngược lại, khi bind LDAP để xác thực bằng một principal DN, hệ thống có thể cần **DN đầy đủ**; phải xem hợp đồng của đúng API đang gọi.

**Không “cắt” base DN bằng `substring` hay `replace`.** Khi cần chuyển đổi, hãy so sánh các thành phần bằng `LdapName`, xác định base thực tế, rồi dùng các tiện ích tạo tên hoặc phương thức làm việc với `Name` tương ứng.

## 6. Kiểm tra một DN có thuộc nhánh được phép hay không

Giả sử nghiệp vụ chỉ cho phép thao tác với **entry người dùng trực tiếp dưới** `ou=people`. Hai điều kiện cần là:

1. DN phải nằm dưới base đã quy định theo **thành phần RDN**, không chỉ giống ở cuối chuỗi.
2. DN phải có đúng một RDN con, và RDN đó phải dùng thuộc tính `uid`.

Ví dụ kiểm tra với JNDI `LdapName`:

~~~java
import javax.naming.InvalidNameException;
import javax.naming.ldap.LdapName;
import javax.naming.ldap.Rdn;

import org.springframework.ldap.support.LdapNameBuilder;

public final class EmployeeDnPolicy {
    private static final LdapName PEOPLE =
            LdapNameBuilder.newInstance("ou=people").build();

    private EmployeeDnPolicy() {}

    public static LdapName requireEmployeeDn(String input) {
        final LdapName candidate;
        try {
            candidate = new LdapName(input);
        } catch (InvalidNameException | NullPointerException ex) {
            throw new IllegalArgumentException("DN sai cú pháp", ex);
        }

        // JNDI Name.startsWith dùng thứ tự thành phần từ gốc đến lá.
        // Vì thế startsWith(PEOPLE) xác định suffix văn bản ou=people.
        if (!candidate.startsWith(PEOPLE)
                || candidate.size() != PEOPLE.size() + 1) {
            throw new IllegalArgumentException(
                    "DN phải là entry trực tiếp dưới ou=people");
        }

        Rdn leaf = candidate.getRdn(candidate.size() - 1);
        if (leaf.size() != 1
                || !"uid".equalsIgnoreCase(leaf.getType())
                || leaf.getValue() == null
                || leaf.getValue().toString().isBlank()) {
            throw new IllegalArgumentException("RDN của entry phải là uid");
        }

        return candidate;
    }
}
~~~

Ở đây `PEOPLE` và `candidate` đều là **DN tương đối** với cùng base `dc=example,dc=org`. Không được đưa DN đầy đủ vào hàm rồi so với base tương đối mà không có bước chuyển đổi rõ ràng.

### 6.1. Vì sao kiểm tra theo thành phần tốt hơn chuỗi?

| DN tương đối được nhập | Kết quả kiểm tra | Lý do |
| --- | --- | --- |
| `uid=linh,ou=people` | Hợp lệ về phạm vi | Một entry con trực tiếp có RDN `uid` |
| `ou=people` | Từ chối | Đây là chính nhánh chứa người dùng, không phải entry con |
| `uid=linh,ou=admins` | Từ chối | Không thuộc `ou=people` |
| `uid=linh,ou=teams,ou=people` | Từ chối | Nằm sâu hơn một cấp |
| `cn=linh,ou=people` | Từ chối | RDN lá không phải `uid` |
| `uid=linh,ou=people,dc=example,dc=org` | Từ chối khi áp dụng chính sách DN tương đối | Không cùng dạng với base `ou=people` |

Một DN có thể qua được kiểm tra này mà vẫn trỏ tới entry không phải nhân viên do dữ liệu trên server không đúng schema mong đợi. Vì vậy, ở bước thao tác thực tế còn phải kiểm tra **đối tượng, quyền và trạng thái** trên server.

Nếu nghiệp vụ cho phép cả nhánh con nhiều cấp, cần viết chính sách riêng cho kiểu subtree. Không bỏ điều kiện độ sâu chỉ để “cho chạy được” mà không xét tác động tới khả năng xóa các đối tượng quản trị nằm bên dưới.

## 7. Kiểm tra DN trước khi `lookup`

`LdapTemplate.lookup(Name)` lấy entry tại một DN cụ thể (khác với `search`, vốn xét filter và search scope). Một luồng lookup an toàn gồm:

1. Nhận định danh ứng dụng (ưu tiên `uid`) và tự dựng DN hoặc parse DN theo chính sách.
2. Kiểm tra DN nằm trong phạm vi được phép.
3. Gọi `lookup` bằng tài khoản LDAP có quyền đọc cần thiết.
4. Xác nhận các thuộc tính và object class cần dùng trong nghiệp vụ; xử lý riêng tình huống không tồn tại và lỗi truy cập.

Ví dụ:

~~~java
import java.util.Optional;
import javax.naming.ldap.LdapName;

import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.NameNotFoundException;

public class EmployeeReader {
    private final LdapTemplate ldapTemplate;

    public EmployeeReader(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public Optional<String> findDisplayName(String uid) {
        LdapName dn = EmployeeDnFactory.fromUid(uid);

        try {
            String name = ldapTemplate.lookup(
                    dn,
                    (AttributesMapper<String>) attrs -> {
                        var cn = attrs.get("cn");
                        return cn == null ? null : (String) cn.get();
                    });
            return Optional.ofNullable(name);
        } catch (NameNotFoundException ex) {
            return Optional.empty();
        }
    }
}
~~~

Ví dụ này dùng Spring LDAP `NameNotFoundException` cho trường hợp DN không có trên server. Các lỗi như mất kết nối, xác thực tài khoản dịch vụ thất bại, lỗi quyền hoặc schema **không nên bị gộp** thành kết quả “không tìm thấy”. Khi dữ liệu nhạy cảm, cần áp dụng kiểm tra quyền tại tầng service trước khi trả thông tin.

**Chú ý alias và referral:** nếu DN là alias hoặc máy chủ trả referral, hành vi lookup còn phụ thuộc chính sách dereference/referral và cách triển khai server. DN parse được cũng không đảm bảo client nhận entry đích tại chỗ.

## 8. “Bind” có hai nghĩa cần phân biệt

Từ `bind` trong LDAP/Spring LDAP có thể chỉ **hai thao tác khác nhau**:

| Ngữ cảnh | Ý nghĩa | Kiểm tra DN trước thao tác |
| --- | --- | --- |
| **LDAP bind / authentication bind** | Máy khách gửi danh tính và thông tin xác thực để server xác nhận | DN principal hợp lệ/được xác định đúng tài khoản, kênh TLS an toàn, chống đăng nhập bằng thông tin rỗng |
| **`LdapTemplate.bind(...)`** | Tạo một **entry mới** tại DN cho trước | DN mới nằm đúng nhánh, không đè đối tượng hiện có, các thuộc tính và object class đúng schema, tài khoản dịch vụ được cấp quyền |

Hai trường hợp không thể thay thế nhau. Gọi `LdapTemplate.bind(dn, null, attributes)` **không phải** là thao tác kiểm tra mật khẩu người dùng.

### 8.1. Trước authentication bind

Một ứng dụng có thể dùng Spring Security LDAP hoặc cơ chế authentication của Spring LDAP để xác thực. Bất kể API cụ thể nào, nên:

- **Không tin DN do client tự gửi** để chọn tài khoản hay máy chủ đăng nhập; thường tìm DN bằng định danh người dùng được kiểm soát hoặc xây từ quy tắc đặt tên đã xác định.
- **Từ chối mật khẩu rỗng** ở lớp ứng dụng, tránh những cấu hình LDAP có thể coi simple bind với tên/mật khẩu rỗng là anonymous/unauthenticated bind.
- Dùng **LDAPS hoặc StartTLS**, xác minh chứng chỉ và hostname của máy chủ; không truyền thông tin đăng nhập qua kết nối chưa được bảo vệ.
- Giới hạn nguồn truy vấn, xử lý trùng định danh, trạng thái khóa tài khoản và các chính sách rate limit phù hợp.
- Sau bind thành công vẫn phải **phân quyền** trước khi cho phép thực hiện thao tác nghiệp vụ.

Minh họa quy trình (giản lược ở mức thuật toán, không gắn với một API xác thực cụ thể):

~~~text
userId + password
  -> kiểm tra đầu vào / từ chối password rỗng
  -> tìm hoặc dựng DN người dùng theo nguồn đáng tin cậy
  -> kiểm tra DN thuộc vùng danh tính dự kiến
  -> yêu cầu LDAP server xác thực (bind) trên kết nối TLS hợp lệ
  -> bind thành công? -> tạo authentication/phiên theo framework
  -> kiểm tra quyền nghiệp vụ riêng trước thao tác được yêu cầu
~~~

Một DN đúng cú pháp không xác minh mật khẩu và không có tác dụng cấp quyền.

### 8.2. Trước `LdapTemplate.bind(...)` để tạo entry

Để thêm một nhân viên vào thư mục, ứng dụng phải dựng DN và các thuộc tính phù hợp schema:

~~~java
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.BasicAttributes;
import javax.naming.ldap.LdapName;

import org.springframework.ldap.core.LdapTemplate;

public class EmployeeWriter {
    private final LdapTemplate ldapTemplate;

    public EmployeeWriter(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public void create(String uid, String fullName, String surname) {
        LdapName dn = EmployeeDnFactory.fromUid(uid);

        // Kiểm tra quyền nghiệp vụ của người thực hiện ở tầng gọi.
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

        ldapTemplate.bind(dn, null, attrs);
    }
}
~~~

Ví dụ giả định `ou=people` đã tồn tại và schema máy chủ hỗ trợ `inetOrgPerson`. Dữ liệu thực tế còn cần validation tên, thuộc tính bắt buộc, độ dài/kiểu dữ liệu, quyền thêm entry, quy tắc unique UID và xử lý xung đột (entry đã tồn tại, `NameAlreadyBoundException` hoặc ngoại lệ tương ứng của Spring LDAP).

**Không dùng mẫu “lookup thấy chưa có rồi mới bind” làm bảo đảm không trùng.** Hai yêu cầu đồng thời có thể đều thấy chưa có entry; thao tác thêm trên server và quy tắc uniqueness mới là điểm quyết định. Một lần lookup trước bind có thể hỗ trợ thông báo lỗi tốt hơn, nhưng không thay được kiểm soát đồng thời.

## 9. Kiểm tra kỹ hơn trước `delete` / `LdapTemplate.unbind`

Trong API Spring LDAP, việc xóa entry thường được thực hiện qua `LdapTemplate.unbind(Name)`. Đây là thao tác có hậu quả lớn nên cần nhiều lớp kiểm tra:

~~~mermaid
flowchart TD
    A["Yêu cầu xóa theo uid"] --> B["Xác thực người gọi"]
    B --> C{"Có quyền xóa nhân viên?"}
    C -- "Không" --> STOP["Từ chối"]
    C -- "Có" --> D["Dựng DN qua LdapNameBuilder"]
    D --> E{"Đúng nhánh, đúng độ sâu?"}
    E -- "Không" --> STOP
    E -- "Có" --> F["Lookup kiểm tra entry và chính sách nghiệp vụ"]
    F --> G{"Hợp lệ để xóa?"}
    G -- "Không" --> STOP
    G -- "Có" --> H["LdapTemplate.unbind(dn)"]
    H --> I["Xử lý kết quả / lỗi, ghi audit"]
~~~

Ví dụ service có bước kiểm tra rõ ràng:

~~~java
import javax.naming.ldap.LdapName;

import org.springframework.ldap.core.LdapTemplate;

public class EmployeeDeletionService {
    private final LdapTemplate ldapTemplate;

    public EmployeeDeletionService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public void deleteEmployee(String uid, boolean callerMayDelete) {
        if (!callerMayDelete) {
            throw new SecurityException("Không có quyền xóa nhân viên");
        }

        LdapName dn = EmployeeDnFactory.fromUid(uid);

        // Đọc trạng thái entry và kiểm tra thêm các điều kiện nghiệp vụ
        // (tài khoản đặc biệt, đang được tham chiếu, chính sách lưu trữ...).
        // Việc xóa cần quyền delete thực tế trên LDAP server.
        ldapTemplate.unbind(dn);
    }
}
~~~

Tham số `callerMayDelete` chỉ là cách rút gọn để trình bày, **không phải thiết kế ủy quyền production**: trong ứng dụng thật, quyền phải được lấy từ security context hoặc cơ chế authorization tin cậy; không nhận boolean do client tự tuyên bố.

**Các điều kiện tối thiểu trước khi xóa:**

- Dựng DN từ `uid` đáng tin cậy thay vì nhận DN tùy ý.
- Bảo đảm chỉ xóa entry thuộc nhánh và loại đối tượng mà nghiệp vụ quản lý; không được xóa base DN, nhóm, OU, tài khoản dịch vụ hay entry hệ thống.
- Kiểm tra người thực hiện có quyền theo nghiệp vụ và tài khoản LDAP kết nối có ACL tối thiểu.
- Nếu cần, lookup để đối chiếu `objectClass`, mã nhân viên, trạng thái tài khoản, yêu cầu phê duyệt hoặc quy trình lưu trữ; không chỉ dựa vào tên DN.
- Chuẩn bị xử lý lỗi không tồn tại, lỗi quyền, entry còn con (thường không xóa bằng thao tác đơn lẻ) và lỗi kết nối; ghi audit đúng mức, tránh log mật khẩu.

**Giới hạn quan trọng:** lookup rồi mới delete có **khoảng thời gian tranh chấp (time-of-check/time-of-use)**. Entry có thể bị đổi tên, sửa hoặc xóa bởi tiến trình khác trong khoảng đó. Vì vậy, validation phía ứng dụng phải đi cùng ACL trên LDAP server, kiểm soát thao tác đồng thời và chính sách quản trị dữ liệu phù hợp; không xem preflight lookup là khóa giao dịch.

## 10. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân khả dĩ | Cách xử lý |
| --- | --- | --- |
| `InvalidNameException` lúc parse | DN sai cú pháp hoặc giá trị chứa ký tự đặc biệt không escape đúng | Dùng `LdapNameBuilder` và chỉ nhận từng giá trị RDN |
| `NameNotFoundException` khi lookup | Entry không có, DN sai base, hoặc nơi tra cứu không trả đối tượng mong đợi | Kiểm tra DN tương đối/tuyệt đối, base của `ContextSource`, quyền và alias/referral |
| `NameAlreadyBoundException` khi tạo | DN đã tồn tại | Xử lý xung đột ở tầng nghiệp vụ, không ghi đè mù |
| `InvalidAttributeValueException` hay vi phạm schema | Thiếu thuộc tính bắt buộc, không đúng object class hoặc value | Kiểm tra schema, `objectClass` và dữ liệu đầu vào |
| Lỗi `InsufficientAccessRights` / không đủ quyền | ACL của LDAP server từ chối thao tác | Giảm quyền yêu cầu, kiểm tra bind identity và ACL; không thử tài khoản đặc quyền vô điều kiện |
| Xóa entry gốc hoặc nhánh sai | Kiểm tra DN bằng chuỗi hoặc thiếu giới hạn độ sâu | Bắt buộc kiểm tra RDN/base, role và ACL |
| Đăng nhập bất thường với mật khẩu trống | Simple bind/anonymous bind không được kiểm soát | Chặn mật khẩu rỗng trước khi gọi authentication |
| Lỗi TLS/referral/timeout | Máy chủ/đường kết nối hoặc naming context khác | Xác minh TLS, URL được phép, timeout, loại lỗi và policy referral |

Các tên ngoại lệ ở bảng phản ánh lỗi thường gặp; lớp ngoại lệ chính xác phụ thuộc JNDI, Spring LDAP, phiên bản thư viện và ngữ cảnh thao tác. Bắt ngoại lệ chuyên biệt khi cần phân nhánh xử lý, còn lỗi không xác định nên được ghi log/giám sát an toàn và trả thông báo phù hợp.

## 11. Bài kiểm thử nên có

**Tình huống:** Ứng dụng quản lý người dùng trong `ou=people,dc=example,dc=org` và có quyền thêm/đọc/xóa các entry `inetOrgPerson` theo chính sách.

| Trường hợp | Đầu vào / điều kiện | Kết quả mong đợi |
| --- | --- | --- |
| Tên hợp lệ | `uid=linh,ou=people` | Parse và qua kiểm tra phạm vi |
| DN sai cú pháp | Giá trị DN không thể parse | Từ chối trước khi kết nối LDAP |
| Nhánh không hợp lệ | `uid=linh,ou=admins` | Từ chối dù DN parse được |
| Chính base DN | `ou=people` | Từ chối xóa base |
| Con nhiều cấp | `uid=linh,ou=archive,ou=people` | Từ chối nếu chính sách chỉ cho phép con trực tiếp |
| RDN sai loại | `cn=linh,ou=people` | Từ chối theo chính sách dùng `uid` |
| Dấu phẩy trong giá trị tên | `cn=Nguyen\, Linh` được tạo bằng builder | Escaping đúng, không sinh thêm RDN |
| Lookup entry không có | DN hợp lệ nhưng entry chưa tồn tại | Trả trạng thái không tìm thấy rõ ràng |
| Bind tạo entry trùng | Hai request cùng tạo một DN | Một request bị từ chối do trùng trên server, không ghi đè |
| Delete thiếu quyền | Người gọi hoặc tài khoản LDAP không có quyền | Không xóa, trả lỗi quyền |
| Lỗi dịch vụ LDAP | Timeout hoặc mất TLS | Báo lỗi hạ tầng, không coi là “không có entry” |
| DN hợp lệ nhưng sai loại | Entry đích là nhóm thay vì người dùng | Ngăn thao tác theo chính sách đối tượng |

Có thể kiểm tra thuần Java việc parse, xây DN và so sánh RDN. Nhưng các trường hợp **tồn tại entry, schema, quyền, LDAP bind xác thực và xóa thực sự** phải được kiểm thử tích hợp với một LDAP server phù hợp (ví dụ test container hoặc server thử nghiệm có schema/ACL tương ứng). Mock `LdapTemplate` không chứng minh được ACL hay chính sách naming của server.

Trong kiểm thử thao tác xóa, chỉ sử dụng cây dữ liệu thử nghiệm, mỗi test tự tạo và dọn entry của chính mình. Bổ sung kiểm tra rằng DN gốc, OU, nhóm và service account không thể bị xóa qua service này. Khi kiểm thử kết nối, xác minh TLS và chứng chỉ, hạn chế quyền của tài khoản dịch vụ, giới hạn timeout và không ghi credential hoặc nội dung nhạy cảm vào log.

## 12. Tự đánh giá

**Câu 1.** `new LdapName(input)` chạy thành công. Có thể gọi ngay `ldapTemplate.unbind`?

**Đáp án:** Chưa. Parse chỉ kiểm tra cú pháp. Cần bảo đảm DN thuộc nhánh và kiểu entry được phép, người gọi có quyền, nghiệp vụ cho phép xóa và tài khoản LDAP có ACL thích hợp.

**Câu 2.** `LdapContextSource` dùng base `dc=example,dc=org`. DN nào thường được truyền cho `LdapTemplate.lookup` nếu muốn lấy nhân viên `uid=linh`?

**Đáp án:** DN tương đối `uid=linh,ou=people`. DN đầy đủ trên máy chủ là `uid=linh,ou=people,dc=example,dc=org`. Phải tuân theo hợp đồng cụ thể của API và base đã cấu hình.

**Câu 3.** Tại sao không dùng `dn.endsWith("ou=people")` để quyết định DN có nằm trong nhánh được phép?

**Đáp án:** DN có cú pháp RDN và escaping riêng, các thành phần không thể được kiểm soát đầy đủ bằng so khớp chuỗi. Nên parse thành `LdapName` và so sánh theo thành phần, kèm quy tắc độ sâu.

**Câu 4.** `LdapTemplate.bind(dn, null, attributes)` có kiểm tra mật khẩu người dùng không?

**Đáp án:** Không. Đây là thao tác tạo entry. Authentication bind là thao tác xác thực với LDAP server, thường do cơ chế authentication phù hợp xử lý.

**Câu 5.** Khi lookup thành công rồi delete ngay sau đó, thao tác có chắc xóa đúng dữ liệu vừa đọc không?

**Đáp án:** Không chắc tuyệt đối: dữ liệu có thể thay đổi giữa hai thao tác. Cần kiểm soát quyền tại server, phạm vi thao tác và cơ chế đồng thời phù hợp, thay vì chỉ dựa vào lookup trước khi xóa.

Trong thực tế, **kiểm tra DN là bước đầu để giới hạn đúng mục tiêu**, còn kiểm soát quyền, schema, trạng thái entry, TLS và xử lý lỗi mới hoàn thiện một thao tác Spring LDAP an toàn.
