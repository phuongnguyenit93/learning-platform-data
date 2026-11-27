# Spring LDAP giải quyết những khó khăn nào của JNDI?

## 1. Từ JNDI đến Spring LDAP: vấn đề nằm ở đâu?

Trong một ứng dụng Java, **LDAP (Lightweight Directory Access Protocol)** thường được dùng để truy cập dịch vụ thư mục chứa tài khoản, nhóm, đơn vị tổ chức hoặc thông tin định danh. Ví dụ, một ứng dụng nội bộ cần tìm người dùng theo `uid`, đọc tên hiển thị và email, xác thực mật khẩu hoặc cập nhật thuộc tính của một entry trong LDAP.

Java cung cấp **JNDI (Java Naming and Directory Interface)**, một API cấp thấp cho các thao tác này. Với JNDI, lập trình viên trực tiếp tạo `DirContext`, xây dựng DN và bộ lọc tìm kiếm, gọi phương thức trên context, duyệt `NamingEnumeration`, xử lý `NamingException` và đóng tài nguyên. JNDI linh hoạt nhưng khiến cùng một lượng mã hạ tầng phải xuất hiện ở nhiều nơi trong ứng dụng.

**Spring LDAP** xây dựng một lớp trừu tượng trên cơ chế truy cập LDAP của Java. Nó không phải máy chủ LDAP hay một giao thức thay thế JNDI. Mục tiêu của Spring LDAP là giảm mã lặp, tập trung cấu hình kết nối, cung cấp thao tác tìm kiếm/cập nhật dễ dùng hơn, chuyển đổi lỗi sang hệ ngoại lệ nhất quán của Spring và hỗ trợ ánh xạ entry thành đối tượng Java.

Trong bức tranh tổng thể, quan hệ giữa các lớp có thể hình dung như sau:

```text
Ứng dụng nghiệp vụ (UserDirectoryService, GroupService, ...)
                       |
                       v
Spring LDAP (LdapTemplate / LdapClient / ODM)
                       |
                       v
          ContextSource và các cơ chế JNDI
                       |
                       v
              Giao thức LDAP / TLS
                       |
                       v
        Máy chủ thư mục (OpenLDAP, AD, ...)
```

`LdapTemplate` là lựa chọn phổ biến để minh họa. `LdapClient` cung cấp cách gọi dạng fluent ở các phiên bản Spring LDAP có hỗ trợ; ODM (Object-Directory Mapping) phù hợp khi cần biểu diễn entry bằng lớp Java. Cả ba đều cần hiểu DN, schema, filter và quyền truy cập của máy chủ LDAP.

## 2. Những khó khăn khi làm việc trực tiếp với JNDI

### 2.1. Phải tự quản lý vòng đời kết nối và tài nguyên

Một truy vấn JNDI thường cần khởi tạo môi trường, mở context, đặt phạm vi tìm kiếm, duyệt kết quả và đóng cả `NamingEnumeration` lẫn `DirContext`:

```java
import java.util.Hashtable;
import javax.naming.Context;
import javax.naming.NamingEnumeration;
import javax.naming.directory.*;

Hashtable<String, String> env = new Hashtable<>();
env.put(Context.INITIAL_CONTEXT_FACTORY,
        "com.sun.jndi.ldap.LdapCtxFactory");
env.put(Context.PROVIDER_URL,
        "ldaps://ldap.example.org:636/dc=example,dc=org");
env.put(Context.SECURITY_AUTHENTICATION, "simple");
env.put(Context.SECURITY_PRINCIPAL,
        "cn=directory-reader,ou=system,dc=example,dc=org");
env.put(Context.SECURITY_CREDENTIALS,
        System.getenv("LDAP_BIND_PASSWORD"));

DirContext context = new InitialDirContext(env);
NamingEnumeration<SearchResult> results = null;
try {
    SearchControls controls = new SearchControls();
    controls.setSearchScope(SearchControls.SUBTREE_SCOPE);

    // Giá trị filter cố định nhằm tập trung minh họa vòng đời JNDI.
    results = context.search("ou=people", "(uid=alice)", controls);
    while (results.hasMore()) {
        SearchResult entry = results.next();
        System.out.println(entry.getAttributes().get("cn").get());
    }
} finally {
    try {
        if (results != null) {
            results.close();
        }
    } finally {
        context.close();
    }
}
```

Đoạn mã này vẫn chưa xử lý mọi trường hợp lỗi hay thuộc tính bị thiếu. Nếu có nhiều phương thức tra cứu người dùng, nhóm và tổ chức, việc mở/đóng context, duyệt kết quả và chuyển đổi thuộc tính dễ lặp lại, làm tăng nguy cơ rò rỉ tài nguyên hoặc xử lý lỗi thiếu nhất quán.

**Spring LDAP giải quyết:** `LdapTemplate` thực thi các thao tác qua `ContextSource`, quản lý việc lấy/trả/đóng context và đóng tài nguyên tìm kiếm theo vòng đời của thao tác. Mã nghiệp vụ tập trung vào truy vấn và cách chuyển kết quả thành đối tượng cần dùng.

### 2.2. Truy vấn dễ bị trộn với mã hạ tầng

Trong JNDI, việc xác định base DN, scope, filter, danh sách thuộc tính và vòng lặp duyệt kết quả thường nằm trong cùng một phương thức. Khi cần thay đổi quy tắc tìm người dùng, người đọc phải phân biệt đâu là logic nghiệp vụ, đâu là mã thao tác với LDAP.

**Spring LDAP giải quyết:** `LdapQueryBuilder` diễn đạt rõ các thành phần của truy vấn; `LdapTemplate.search(...)` nhận một hàm ánh xạ kết quả. Nhờ vậy, một truy vấn như “tìm `cn` của người dùng có `uid` cho trước trong `ou=people`” có thể được viết gọn mà vẫn thể hiện đúng mục đích.

### 2.3. DN và LDAP filter có quy tắc escape khác nhau

**DN (Distinguished Name)** định vị một entry, ví dụ `uid=alice,ou=people,dc=example,dc=org`. **Filter** lựa chọn các entry thỏa điều kiện, ví dụ `(uid=alice)`. Chúng là hai cú pháp khác nhau. Nối chuỗi trực tiếp với dữ liệu đầu vào có thể tạo filter sai, dẫn đến LDAP injection, hoặc tạo DN không đúng khi giá trị có dấu phẩy, dấu cộng, dấu bằng và các ký tự đặc biệt.

**Spring LDAP giải quyết:** dùng `LdapNameBuilder` để ghép DN và `LdapQueryBuilder`/các đối tượng filter để mã hóa giá trị theo ngữ cảnh. Không lấy giá trị đã escape cho DN rồi dùng nguyên làm giá trị filter, hay ngược lại. Các builder chỉ giúp tạo cú pháp an toàn hơn; quyền truy cập, giới hạn dữ liệu và kiểm soát đầu vào vẫn là trách nhiệm của ứng dụng và máy chủ.

### 2.4. Ngoại lệ khó dùng thống nhất trong ứng dụng Spring

JNDI trả về các ngoại lệ dạng `javax.naming.NamingException` và các lớp con. Khi triển khai nhiều repository, lập trình viên phải tự phân loại lỗi không tìm thấy DN, sai thông tin xác thực, lỗi kết nối và lỗi schema để quyết định cách phản hồi.

**Spring LDAP giải quyết:** chuyển các ngoại lệ JNDI phù hợp sang hệ ngoại lệ LDAP của Spring, phần lớn là ngoại lệ không kiểm tra (*unchecked exceptions*). Chẳng hạn, ứng dụng có thể bắt các loại lỗi LDAP cụ thể của Spring ở ranh giới dịch vụ để ghi log, ánh xạ thông báo hoặc quyết định có thử lại hay không. Cần phân biệt “tìm kiếm không có kết quả” (thường là danh sách rỗng) với lỗi tra cứu DN hoặc lỗi kết nối thực sự.

### 2.5. Chuyển đổi Attributes thành đối tượng Java dễ lặp

Với JNDI, kết quả thường là `Attributes` và `Attribute`. Nghiệp vụ phải lấy từng giá trị, kiểm tra thuộc tính có tồn tại không, xử lý thuộc tính đa trị và ép kiểu. Cùng cấu trúc người dùng có thể bị chuyển đổi khác nhau ở mỗi lớp.

**Spring LDAP giải quyết:** dùng `AttributesMapper` cho phép ánh xạ ngay trong thao tác tìm kiếm; `ContextMapper` khi cần cả ngữ cảnh entry; ODM khi muốn ánh xạ tập trung các entry vào lớp Java và làm việc theo mô hình đối tượng. ODM không loại bỏ yêu cầu phải hiểu `objectClass`, schema hay các thuộc tính bắt buộc của LDAP.

## 3. Một ví dụ đầy đủ: tìm tên hiển thị theo UID

Giả sử máy chủ chứa các entry như sau:

```ldif
dn: uid=alice,ou=people,dc=example,dc=org
objectClass: inetOrgPerson
uid: alice
cn: Alice Nguyen
sn: Nguyen
mail: alice@example.org
```

Ta muốn xây dựng một repository tìm `cn` theo `uid`. Ví dụ dưới đây cấu hình Spring LDAP bằng Java và lấy thông tin kết nối từ biến môi trường. Dùng `ldaps://` giả định máy chủ đã cấu hình TLS và ứng dụng đã tin cậy chứng chỉ phù hợp.

```java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.core.support.LdapContextSource;

@Configuration
class LdapConfiguration {

    @Bean
    LdapContextSource contextSource(
            @Value("${app.ldap.url}") String url,
            @Value("${app.ldap.base}") String base,
            @Value("${app.ldap.bind-dn}") String bindDn,
            @Value("${app.ldap.bind-password}") String password) {
        LdapContextSource source = new LdapContextSource();
        source.setUrl(url);
        source.setBase(base);
        source.setUserDn(bindDn);
        source.setPassword(password);
        return source; // Spring gọi afterPropertiesSet() cho bean.
    }

    @Bean
    LdapTemplate ldapTemplate(LdapContextSource source) {
        return new LdapTemplate(source);
    }
}
```

```yaml
# application.yml
app:
  ldap:
    url: ${LDAP_URL:ldaps://ldap.example.org:636}
    base: dc=example,dc=org
    bind-dn: ${LDAP_BIND_DN}
    bind-password: ${LDAP_BIND_PASSWORD}
```

`base` là hậu tố DN dùng chung. Với cấu hình này, truy vấn tương đối `ou=people` sẽ tìm trong nhánh `ou=people,dc=example,dc=org`. Tài khoản `bind-dn` là danh tính kết nối dành cho ứng dụng và chỉ nên có quyền cần thiết.

```java
import java.util.List;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.stereotype.Repository;
import static org.springframework.ldap.query.LdapQueryBuilder.query;

@Repository
class UserDirectoryRepository {
    private final LdapTemplate ldapTemplate;

    UserDirectoryRepository(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    List<String> findDisplayNamesByUid(String uid) {
        return ldapTemplate.search(
                query().base("ou=people").where("uid").is(uid),
                attributes -> (String) attributes.get("cn").get()
        );
    }
}
```

Các thành phần trong ví dụ có nhiệm vụ riêng:

1. `LdapContextSource` chứa cấu hình địa chỉ LDAP, base DN và thông tin bind; `LdapTemplate` dùng source này cho các thao tác.
2. `query().base("ou=people").where("uid").is(uid)` tạo truy vấn theo giá trị `uid`, tránh nối trực tiếp đầu vào vào chuỗi filter.
3. `search(...)` trả về danh sách kết quả, dùng lambda ánh xạ thuộc tính `cn` sang `String`. Không tìm thấy người dùng thì danh sách rỗng; nếu có nhiều entry trùng `uid`, có thể có nhiều phần tử.
4. Ví dụ giả định mọi entry phù hợp đều có `cn`. Với schema thực tế, mapper cần xử lý thuộc tính tùy chọn, thuộc tính đa trị và dữ liệu thiếu để tránh `NullPointerException`.

Khi xử lý dữ liệu từ người dùng, hãy truyền `uid` như một giá trị cho query builder. Ví dụ, ký tự `*` trong đầu vào phải được coi là dữ liệu cần escape nếu mục tiêu là tìm UID đúng bằng ký tự đó, chứ không trở thành wildcard của LDAP filter.

## 4. Ngoài tìm kiếm: tạo, sửa, xóa và xác thực

Sau khi hiểu ví dụ tìm kiếm, có thể áp dụng cùng cơ chế với những thao tác thường gặp:

| Nhu cầu | API Spring LDAP thường dùng | Điều cần chú ý |
| --- | --- | --- |
| Tìm entry theo điều kiện | `LdapTemplate.search(...)` | Base, scope, filter, thuộc tính được trả về, giới hạn kết quả |
| Đọc một entry theo DN | `LdapTemplate.lookup(...)` | DN tuyệt đối/tương đối với base cấu hình; xử lý entry không tồn tại |
| Tạo entry | `LdapTemplate.bind(...)` | DN hợp lệ, `objectClass` và thuộc tính bắt buộc theo schema |
| Cập nhật thuộc tính | `LdapTemplate.modifyAttributes(...)` | Quyền ghi, thao tác thêm/thay/xóa và thuộc tính đa trị |
| Xóa entry | `LdapTemplate.unbind(...)` | Quyền xóa, phụ thuộc entry con và quy định máy chủ |
| Kiểm tra thông tin đăng nhập LDAP | `LdapTemplate.authenticate(...)` | Tìm đúng danh tính cần xác thực, bind an toàn qua TLS, lỗi không đồng nghĩa mật khẩu sai |
| Ánh xạ entry thành đối tượng | `AttributesMapper`, `ContextMapper`, ODM | Khả năng thiếu/đa trị của thuộc tính, schema và phiên bản thư viện |

Ví dụ, nếu muốn xây DN tương đối để cập nhật entry của người dùng, thay vì nối chuỗi `"uid=" + uid + ",ou=people"`, có thể dùng builder:

```java
import javax.naming.Name;
import org.springframework.ldap.support.LdapNameBuilder;

Name userDn = LdapNameBuilder.newInstance("ou=people")
        .add("uid", uid)
        .build();
// userDn dùng trong các thao tác của LdapTemplate,
// tương đối với base dc=example,dc=org của ContextSource.
```

Việc xác thực cần phân biệt **bind của ứng dụng** với **xác thực người dùng**. Bind cấu hình trong `ContextSource` thường dùng tài khoản dịch vụ để tìm entry. Để kiểm tra mật khẩu của một người dùng, ứng dụng có thể dùng cơ chế `authenticate(...)` nhằm tìm DN người dùng rồi thử bind bằng thông tin người dùng đó, với chính sách kết nối và phân quyền phù hợp. Đừng kiểm tra mật khẩu bằng cách so sánh chuỗi đọc từ thuộc tính LDAP. Nếu ứng dụng dùng Spring Security, cần xác định rõ phần nào thuộc cơ chế xác thực/ủy quyền của Spring Security và phần nào là truy cập thư mục do Spring LDAP thực hiện.

## 5. Spring LDAP giải quyết được gì, và không tự giải quyết được gì?

| Vấn đề | JNDI trực tiếp | Spring LDAP |
| --- | --- | --- |
| Khởi tạo và quản lý context | Tự mở, đóng và bảo vệ tài nguyên quanh mỗi thao tác | `ContextSource` và template gom vòng đời tài nguyên |
| Truy vấn LDAP | Tự lắp `SearchControls`, filter, duyệt `NamingEnumeration` | Query builder và các phương thức `search`, `lookup` |
| Xây DN / escape filter | Lập trình viên phải chủ động dùng API/escaping đúng | Có `LdapNameBuilder` và bộ dựng filter, vẫn cần hiểu cú pháp |
| Xử lý kết quả | Thường tự thao tác `SearchResult`/`Attributes` | Mapper và ODM giúp quy đổi có hệ thống |
| Xử lý lỗi | Hệ `javax.naming.NamingException` | Hệ ngoại lệ LDAP của Spring nhất quán hơn |
| Cấu hình và kiểm thử | Tự chia sẻ cấu hình và thay thế kết nối | Bean `ContextSource` dễ cấu hình, tiêm phụ thuộc, thay bằng môi trường kiểm thử |
| Bảo mật, quyền truy cập, schema | Phải cấu hình/thiết kế đúng | Vẫn phải cấu hình/thiết kế đúng; framework không tự cấp quyền hay sửa schema |

Một số giới hạn quan trọng:

- **TLS và chứng chỉ:** Chọn LDAPS hoặc StartTLS theo hạ tầng; xác minh chứng chỉ và hostname, quản lý truststore đúng cách. Spring LDAP không biến kết nối LDAP không mã hóa thành an toàn chỉ bằng cách dùng `LdapTemplate`. Không gửi mật khẩu bind qua kết nối không bảo vệ.
- **Pooling và hiệu năng:** Chọn chiến lược tái sử dụng context khi phù hợp; cần xem tương thích với xác thực theo người dùng, StartTLS và môi trường triển khai. Pooling không đương nhiên được bật cho mọi tình huống; không nên tùy ý chia sẻ một kết nối đã bind bằng danh tính nhạy cảm.
- **Timeout, paging và tải lớn:** Cần đặt timeout, scope, giới hạn truy vấn, phân trang và kiểm soát độ lớn kết quả theo đặc tính máy chủ. Template không tự giải quyết truy vấn chậm, LDAP server-side limits hay số lượng entry quá lớn.
- **Schema và ACL:** `objectClass`, thuộc tính bắt buộc, quan hệ DN cha/con và quyền đọc/ghi do máy chủ quyết định. Mapper giúp thao tác dữ liệu nhưng không thay thế việc hiểu schema.
- **Lỗi mạng và vận hành:** Phải phân biệt sai mật khẩu, người dùng không tồn tại, máy chủ không khả dụng và lỗi chứng chỉ. Đặc biệt, không được coi mọi lỗi xác thực hoặc kết nối là “sai thông tin đăng nhập”. Việc retry cần giới hạn, có log phù hợp và tránh ghi mật khẩu, token hoặc giá trị nhạy cảm.

## 6. Nên chọn cách tiếp cận nào?

**Dùng JNDI trực tiếp** khi ứng dụng rất nhỏ, phải thao tác với khả năng JNDI đặc thù hoặc không sử dụng hệ sinh thái Spring. Khi đó vẫn phải xử lý an toàn vòng đời context, escape đúng chuẩn, ngoại lệ và TLS.

**Dùng `LdapTemplate`** khi ứng dụng Spring cần thực hiện các thao tác LDAP rõ ràng: tìm người dùng, đọc nhóm, tạo/sửa entry, xác thực với danh tính phù hợp. Đây là điểm bắt đầu dễ kiểm soát vì việc truy cập và ánh xạ hiển thị ngay trong từng phương thức.

**Cân nhắc `LdapClient`** nếu phiên bản Spring LDAP đang sử dụng hỗ trợ API fluent và nhóm muốn viết truy vấn, thao tác theo cú pháp dạng chuỗi lời gọi. Khả năng và chữ ký phương thức cụ thể phụ thuộc phiên bản, vì vậy cần đối chiếu tài liệu tương ứng với dependency của dự án.

**Cân nhắc ODM** khi có nhiều loại entry, schema tương đối ổn định và nhu cầu ánh xạ chúng thành các lớp Java. Với tác vụ LDAP đơn giản, mapper của `LdapTemplate` thường đã đủ.

## 7. Thực hành và tự kiểm tra

Hãy dùng một thư mục LDAP thử nghiệm có nhánh `ou=people,dc=example,dc=org` để làm bài tập sau:

1. Cấu hình `LdapContextSource` bằng biến môi trường cho địa chỉ LDAPS, base DN và tài khoản chỉ có quyền đọc. Kiểm tra đường tin cậy chứng chỉ trước khi kết nối.
2. Nhờ tài khoản có quyền ghi chuẩn bị hai entry có `uid`, `cn`, `sn` và `objectClass` hợp lệ; sau đó dùng tài khoản chỉ đọc với `LdapTemplate.search(...)` tìm theo một `uid` có thật rồi một `uid` không tồn tại. Quan sát sự khác nhau giữa danh sách có kết quả và danh sách rỗng.
3. Thử giá trị đầu vào có `*`, dấu ngoặc hoặc dấu gạch chéo ngược, và xác nhận bộ dựng filter xử lý chúng như dữ liệu khi thực hiện so khớp bằng nhau. Dùng `LdapNameBuilder` với một RDN chứa ký tự đặc biệt và kiểm tra DN được tạo.
4. Thử tình huống tài khoản bind không có quyền đọc, sai chứng chỉ TLS hoặc máy chủ ngắt kết nối. Quan sát loại lỗi và thiết kế phản hồi không tiết lộ thông tin nội bộ.
5. So sánh lượng mã nghiệp vụ và số thao tác quản lý tài nguyên giữa ví dụ JNDI và bản Spring LDAP. Xác định phần nào được framework hỗ trợ, phần nào vẫn do bạn chịu trách nhiệm.

**Câu hỏi củng cố:** Vì sao `LdapTemplate` giúp giảm lỗi đóng tài nguyên nhưng không tự ngăn được mọi lỗi bảo mật LDAP? Vì sao một tìm kiếm trả về danh sách rỗng phải được xử lý khác với lỗi không kết nối được máy chủ? Khi nào bạn chọn mapper đơn giản thay vì ODM?

### Ghi nhớ

Spring LDAP làm việc với dịch vụ thư mục LDAP thông qua những khái niệm vẫn quen thuộc như DN, schema, filter, base, scope và bind. Giá trị chính so với JNDI trực tiếp nằm ở **quản lý tài nguyên, truy vấn rõ ràng, ánh xạ dữ liệu, ngoại lệ nhất quán và tích hợp cấu hình Spring**. Để sử dụng an toàn, người học vẫn cần hiểu giao thức LDAP, dùng TLS, phân quyền tối thiểu, xây DN/filter đúng cách và kiểm thử với dữ liệu, schema, lỗi mạng thực tế.
