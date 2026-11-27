# Search base tương đối với ContextSource trong Spring LDAP

Khi tìm kiếm LDAP bằng Spring LDAP, một lỗi rất thường gặp là **truy vấn đúng filter nhưng đặt sai search base**. Nguyên nhân nằm ở chỗ ứng dụng có thể cấu hình **base DN ở `ContextSource`**, rồi tiếp tục truyền **search base riêng cho mỗi truy vấn**. Trong cách dùng chuẩn của `LdapTemplate`, search base được hiểu **tương đối với base DN đã cấu hình ở `ContextSource`**.

Bài học thuộc chương **Search scope** của SPRING_LDAP. Mục tiêu là xác định chính xác vùng tên mà một truy vấn truy cập, phân biệt base với filter và scope, tránh lặp DN, và áp dụng tư duy đó khi làm việc với `LdapTemplate`, `LdapClient` hoặc ODM. Các ví dụ sử dụng thư mục LDAP nhân sự; cấu hình TLS, xác thực, pooling, phân quyền và kiểm thử cũng được đặt vào đúng vị trí trong luồng truy cập.

## 1. Ba loại “base” hoặc “gốc” dễ nhầm lẫn

Giả sử LDAP server phục vụ cây thư mục sau:

~~~text
dc=example,dc=org
├── ou=people
│   ├── uid=an
│   ├── uid=binh
│   └── ou=contractors
│       └── uid=chi
├── ou=groups
│   ├── cn=engineering
│   └── cn=operations
└── ou=services
    └── cn=ldap-reader
~~~

Các thành phần cần phân biệt:

| Khái niệm | Ví dụ | Được dùng vào việc gì? |
| --- | --- | --- |
| **Naming context** | `dc=example,dc=org` | Vùng tên mà LDAP server phục vụ, được quản trị trên server |
| **Base DN của `ContextSource`** | `dc=example,dc=org` | Gốc làm việc mà Spring LDAP dùng khi phân giải DN của thao tác |
| **Search base của truy vấn** | `ou=people` | Entry bắt đầu tìm kiếm, tương đối với base của `ContextSource` |
| **Search scope** | `SUBTREE_SCOPE` | Độ sâu tìm kiếm: base, con trực tiếp hoặc toàn bộ cây con |
| **Search filter** | `(objectClass=inetOrgPerson)` | Điều kiện chọn những entry khớp trong phạm vi tìm kiếm |

**Naming context do server công bố và base do client cấu hình không phải lúc nào cũng trùng nhau.** Ví dụ ứng dụng chỉ cần nhân sự có thể cấu hình base `ou=people,dc=example,dc=org`, dù server còn có nhánh nhóm và tài khoản dịch vụ.

DN (*Distinguished Name*) gồm các RDN (*Relative Distinguished Name*) từ entry cụ thể tới gốc. Entry An có DN đầy đủ:

~~~text
uid=an,ou=people,dc=example,dc=org
~~~

Nếu một DN được viết **tương đối với** `dc=example,dc=org`, nó có thể được biểu diễn là `uid=an,ou=people`. Từ “tương đối” ở đây nói về **phần hậu tố DN được xem là gốc đã biết**; nó không có nghĩa LDAP server sẽ tự suy luận mọi phần còn lại của tên.

## 2. Quy tắc giải quyết search base

Trong các thao tác tìm kiếm qua `LdapTemplate`, có thể hình dung việc phân giải như sau:

~~~text
Base của ContextSource:  dc=example,dc=org
Search base do code gửi: ou=people

Base thực tế trên server:
ou=people,dc=example,dc=org
~~~

Quy tắc tư duy:

> **DN base hiệu lực = search base tương đối + base DN của ContextSource**.

Đây là cách diễn giải tên trong phạm vi ứng dụng, **không phải phép cộng chuỗi tùy tiện**. DN là một cấu trúc có cú pháp escape và thứ tự RDN, nên khi dựng tên động hãy dùng API hiểu DN như `LdapNameBuilder` thay vì nối chuỗi bằng tay.

Bảng sau minh họa khi `ContextSource` có base `dc=example,dc=org`:

| Search base truyền vào `LdapTemplate` | Base hiệu lực trên LDAP server | Ý nghĩa |
| --- | --- | --- |
| `""` (rỗng) | `dc=example,dc=org` | Tìm từ gốc đã cấu hình |
| `ou=people` | `ou=people,dc=example,dc=org` | Tìm nhánh nhân sự |
| `ou=contractors,ou=people` | `ou=contractors,ou=people,dc=example,dc=org` | Tìm nhánh nhân sự hợp đồng |
| `ou=groups` | `ou=groups,dc=example,dc=org` | Tìm nhóm |
| `uid=an,ou=people` | `uid=an,ou=people,dc=example,dc=org` | Bắt đầu từ entry An nếu entry tồn tại |
| `ou=people,dc=example,dc=org` | Có thể bị diễn giải thành `ou=people,dc=example,dc=org,dc=example,dc=org` | **Sai**: lặp suffix base |

Điểm quan trọng: API làm việc tương đối với `ContextSource` **không tự nhận ra rằng một chuỗi DN trông có vẻ đầy đủ và bỏ phần suffix trùng nhau**. Khi đã thiết lập base, đừng đưa lại cùng suffix đó vào search base của thao tác thông thường.

### Trường hợp `ContextSource` không thiết lập base

Nếu base DN của `ContextSource` là rỗng, search base như `ou=people,dc=example,dc=org` có thể được dùng để chỉ nhánh đầy đủ trong naming context mà server phục vụ. Nhưng đây là **cấu hình khác**, nên không được sao chép nguyên search base từ hệ thống này sang hệ thống khác mà không kiểm tra base của `ContextSource`.

Cũng đừng đồng nhất search base rỗng dưới một `ContextSource` có base với **Root DSE** của LDAP. Với base đã cấu hình, `""` chỉ gốc đó; Root DSE là entry đặc biệt ở DN rỗng phía server, được truy cập qua ngữ cảnh/thao tác phù hợp riêng.

## 3. Cấu hình `ContextSource`: một gốc dùng chung

`ContextSource` là tầng cung cấp ngữ cảnh JNDI để truy cập LDAP. `LdapContextSource` là một triển khai thường dùng. Nó mang URL server, base DN, thông tin bind và các thiết lập môi trường liên quan.

Trong ứng dụng Spring Boot có hỗ trợ auto-configuration Spring LDAP, có thể sử dụng:

~~~yaml
spring:
  ldap:
    urls: ldaps://ldap.example.org:636
    base: dc=example,dc=org
    username: cn=ldap-reader,ou=services,dc=example,dc=org
    password: ${LDAP_BIND_PASSWORD}
~~~

Đây là cấu hình minh họa. Mật khẩu được lấy từ biến môi trường hoặc kho bí mật; không đưa mật khẩu thật vào mã nguồn. Để kết nối an toàn, server phải có chứng chỉ hợp lệ và client phải tin cậy CA phù hợp. Nếu dùng StartTLS thay cho LDAPS, cần cấu hình và kiểm chứng phiên TLS theo cơ chế được stack LDAP hỗ trợ.

Hai giá trị trong cấu hình rất khác nhau:

- `base` là **gốc dùng để phân giải tên cho thao tác LDAP của ứng dụng**.
- `username` là **DN tài khoản dùng để bind**, thường được khai báo dưới dạng DN đầy đủ, ví dụ `cn=ldap-reader,ou=services,dc=example,dc=org`.

Không dùng quy tắc search base tương đối để tự động cắt suffix của bind DN. Cách Spring LDAP cấu hình danh tính bind và cách `LdapTemplate` phân giải DN tìm kiếm là **hai quan tâm khác nhau**.

Nếu cấu hình bằng Java thay vì Spring Boot:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ldap.core.ContextSource;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.core.support.LdapContextSource;

@Configuration
public class LdapConfiguration {

    @Bean
    LdapContextSource contextSource() {
        LdapContextSource source = new LdapContextSource();
        source.setUrl("ldaps://ldap.example.org:636");
        source.setBase("dc=example,dc=org");
        source.setUserDn("cn=ldap-reader,ou=services,dc=example,dc=org");
        // Truyền mật khẩu từ Secret Manager/environment trong hệ thống thật.
        // source.setPassword(...);
        return source;
    }

    @Bean
    LdapTemplate ldapTemplate(ContextSource contextSource) {
        return new LdapTemplate(contextSource);
    }
}
~~~

Ví dụ Java làm rõ vị trí của `setBase(...)`; **chưa phải cấu hình kết nối hoàn chỉnh để chạy thực tế** vì mật khẩu cần được nạp an toàn. Trong dự án Spring Boot, nên chọn nhất quán auto-configuration hoặc bean tùy biến để tránh hai `ContextSource` trùng vai trò.

Base DN cố định giúp giảm lượng DN lặp lại ở service và repository, nhưng **không phải ranh giới bảo mật tuyệt đối**. Server vẫn kiểm soát các quyền thực tế bằng ACL và danh tính bind.

## 4. Một query hoàn chỉnh gồm base, scope và filter

Muốn tìm tất cả nhân viên dưới `ou=people` kể cả nhánh hợp đồng, ba thành phần được phối hợp như sau:

~~~text
ContextSource base: dc=example,dc=org
Query search base:  ou=people
Scope:              subtree
Filter:             (objectClass=inetOrgPerson)

Server tìm từ:
ou=people,dc=example,dc=org

Rồi lọc theo objectClass trên tập entry trong subtree đó.
~~~

**Base xác định vị trí**, **scope xác định độ sâu**, còn **filter xác định điều kiện**. Không thể sửa một base bị sai chỉ bằng việc đổi filter. Nếu base trỏ sang nhánh không tồn tại, filter hoàn toàn hợp lệ vẫn không trả dữ liệu.

### Ba giá trị scope

| Search scope (JNDI) | Vùng entry được xét từ search base | Với search base `ou=people` |
| --- | --- | --- |
| `OBJECT_SCOPE` | Chỉ entry ngay tại base | Chỉ `ou=people` |
| `ONELEVEL_SCOPE` | Các entry con trực tiếp, **không** gồm base | `uid=an`, `uid=binh`, `ou=contractors` |
| `SUBTREE_SCOPE` | Base và tất cả descendant ở mọi độ sâu | `ou=people`, An, Bình, `ou=contractors`, Chi |

Một query dùng filter `(objectClass=inetOrgPerson)` sẽ còn loại bỏ những OU không mang class này. Vì vậy:

| Scope | Kết quả với filter người dùng từ `ou=people` |
| --- | --- |
| Object | 0 người dùng |
| One level | An và Bình |
| Subtree | An, Bình và Chi |

Như vậy, **không thấy Chi ở one level là hành vi đúng**, vì Chi nằm hai cấp dưới `ou=people`. Trường hợp này không liên quan escaping filter hay lỗi `ContextSource`.

## 5. Ví dụ Spring LDAP với `LdapQueryBuilder`

Giả sử ứng dụng cần tìm một `uid` trong toàn bộ cây người dùng, gồm các OU lồng nhau. `LdapQueryBuilder` cho phép thể hiện base, scope và filter độc lập:

~~~java
import java.util.List;
import javax.naming.directory.SearchControls;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;
import org.springframework.stereotype.Service;

record PersonView(String uid, String fullName, String email) {}

@Service
public class PeopleDirectory {

    private final LdapTemplate ldapTemplate;

    public PeopleDirectory(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<PersonView> findByUid(String uid) {
        if (uid == null || uid.isBlank() || uid.length() > 128) {
            throw new IllegalArgumentException("Invalid uid");
        }

        LdapQuery query = LdapQueryBuilder.query()
                .base("ou=people")
                .searchScope(SearchControls.SUBTREE_SCOPE)
                .where("objectClass").is("inetOrgPerson")
                .and("uid").is(uid);

        return ldapTemplate.search(
                query,
                (AttributesMapper<PersonView>) attrs -> new PersonView(
                        (String) attrs.get("uid").get(),
                        (String) attrs.get("cn").get(),
                        attrs.get("mail") == null
                                ? null
                                : (String) attrs.get("mail").get()));
    }
}
~~~

Khi `ContextSource` có base `dc=example,dc=org`, phương thức này tìm từ **`ou=people,dc=example,dc=org`**. Nó không tìm trong `ou=groups` hoặc `ou=services` vì hai nhánh đó nằm ngoài subtree bắt đầu tại `ou=people`.

Một số chi tiết triển khai:

1. `.base("ou=people")` chỉ khai báo **phần tương đối** với ContextSource base, không cần thêm `dc=example,dc=org`.
2. `.searchScope(SearchControls.SUBTREE_SCOPE)` cho phép tìm trong `ou=contractors` và các cấp sâu hơn.
3. `.where(...).is(uid)` để filter builder xử lý escaping của giá trị do người dùng nhập; không nối chuỗi filter thủ công.
4. `AttributesMapper` chỉ nhận attributes. `mail` được xử lý như thuộc tính có thể vắng mặt.
5. Danh sách kết quả có thể có 0, 1 hoặc nhiều entry; uniqueness của `uid` trên nhiều OU phải được xác định theo chính sách thư mục, không đoán từ tên thuộc tính.

Nếu lớp nghiệp vụ còn cần DN của entry, sử dụng `ContextMapper` hoặc ODM thích hợp. Cần hiểu tên mà mapper trả về tương đối với ngữ cảnh nào trước khi lưu hoặc truyền tên đó sang API khác.

### Chỉ tìm con trực tiếp của OU

Nếu nghiệp vụ chỉ quản lý nhân viên trực tiếp dưới `ou=people`, thay phần cấu hình query:

~~~java
LdapQuery query = LdapQueryBuilder.query()
        .base("ou=people")
        .searchScope(SearchControls.ONELEVEL_SCOPE)
        .where("objectClass").is("inetOrgPerson");
~~~

Trong cây ví dụ, An và Bình sẽ được xét, còn Chi dưới `ou=contractors` không được xét. **Không cần thay ContextSource** để đổi search scope hay search base cho một chức năng.

## 6. Search base rỗng có ý nghĩa gì?

Một search base rỗng thường dùng khi muốn tìm từ chính gốc đã khai báo trong `ContextSource`. Ví dụ:

~~~java
LdapQuery query = LdapQueryBuilder.query()
        .base("")
        .searchScope(SearchControls.ONELEVEL_SCOPE)
        .where("objectClass").is("organizationalUnit");
~~~

Với `ContextSource.base = dc=example,dc=org`, query tìm các OU **trực tiếp** dưới `dc=example,dc=org`: `ou=people`, `ou=groups` và `ou=services`, giả sử server cho phép đọc những entry này.

Cũng dùng `.base("")` nhưng đổi sang `SUBTREE_SCOPE` sẽ tìm trên toàn bộ nhánh `dc=example,dc=org`, có thể rất lớn. Base rỗng không mặc nhiên là “không tìm gì”; ý nghĩa phụ thuộc vào base cấu hình và scope.

Ví dụ cần tìm duy nhất entry ở gốc ContextSource, dùng `OBJECT_SCOPE`. Khi truy vấn các metadata ở **Root DSE** (DN rỗng của LDAP server), không nên áp dụng máy móc kỹ thuật này nếu `ContextSource` đã được cấu hình base khác rỗng.

## 7. Chuyện gì xảy ra khi base của ContextSource đặt ở một OU?

Giả sử dự án khác chỉ được phép thao tác dữ liệu nhân sự và cấu hình:

~~~yaml
spring:
  ldap:
    urls: ldaps://ldap.example.org:636
    base: ou=people,dc=example,dc=org
    username: cn=ldap-reader,ou=services,dc=example,dc=org
    password: ${LDAP_BIND_PASSWORD}
~~~

Các search base lúc này có ý nghĩa khác:

| Search base trong service | Search base thực tế | Kết quả dự kiến |
| --- | --- | --- |
| `""` | `ou=people,dc=example,dc=org` | Bắt đầu từ OU people |
| `ou=contractors` | `ou=contractors,ou=people,dc=example,dc=org` | Nhánh nhân sự hợp đồng |
| `uid=an` | `uid=an,ou=people,dc=example,dc=org` | Entry An |
| `ou=people` | `ou=people,ou=people,dc=example,dc=org` | Sai: lặp OU people |
| `ou=groups` | `ou=groups,ou=people,dc=example,dc=org` | Sai vị trí: không phải nhánh groups cạnh people |

Một đoạn code `.base("ou=people")` có thể chạy đúng trong môi trường A (ContextSource base là `dc=example,dc=org`) nhưng thất bại trong môi trường B (ContextSource base đã là `ou=people,dc=example,dc=org`).

Do đó **search base không phải hằng số độc lập với cấu hình nguồn kết nối**. Khi triển khai nhiều môi trường, phải kiểm thử cặp **ContextSource base + query base** cùng nhau.

### Có nên đặt ContextSource base tại naming context hay OU chức năng?

Cả hai đều có thể phù hợp:

- Base tại `dc=example,dc=org`: linh hoạt truy vấn các nhánh `ou=people`, `ou=groups`, `ou=services`; các service cần chọn search base cụ thể.
- Base tại `ou=people,dc=example,dc=org`: các thao tác trong vùng nhân sự ngắn gọn; muốn truy cập nhánh `ou=groups` nằm ngoài base này thì cần cấu hình truy cập khác phù hợp.

Lựa chọn dựa trên phạm vi nghiệp vụ và cấu trúc thư mục. Dù base chỉ ra một OU, **quyền truy cập vẫn phải do LDAP ACL thực thi**; không coi base của client là biện pháp phân quyền thay thế ACL.

## 8. DN tương đối của entry kết quả khác search base

Search base là điểm bắt đầu truy vấn; **DN của một entry kết quả** chỉ ra entry đó nằm ở đâu trong DIT. Ví dụ:

~~~text
ContextSource base:
dc=example,dc=org

Query search base:
ou=people

Entry khớp:
uid=chi,ou=contractors,ou=people,dc=example,dc=org
~~~

Trong API Spring LDAP, dữ liệu ngữ cảnh trả về có thể cung cấp DN ở dạng **tương đối với base của ContextSource**; trong khi kết quả JNDI thô của một thao tác search có thể biểu diễn tên **tương đối với search base**. Vì vậy không được mặc định mọi API trả DN theo cùng một gốc.

Chẳng hạn `DirContextOperations.getDn()` trong luồng mapping của `LdapTemplate` thường được dùng để lấy DN của entry theo ngữ cảnh `ContextSource`, còn tên mà `SearchResult.getName()` của JNDI thô biểu diễn cần được diễn giải theo phạm vi search đang thực hiện.

Để tránh lỗi:

- Khi log phục vụ điều tra, xác định rõ đang hiển thị **full DN**, **DN tương đối với ContextSource** hay **tên tương đối với search base**.
- Không tự động thêm `ou=people` vào một DN kết quả đã có suffix đó.
- Không tự động thêm `dc=example,dc=org` vào một full DN đã có suffix này.
- Dùng API biểu diễn `Name`/`LdapName` khi cần thao tác RDN hoặc kết hợp DN, thay vì cắt và ghép chuỗi bằng `split(",")`.
- Khi truyền DN từ service sang service có `ContextSource` base khác, xác định lại hệ quy chiếu tên; tốt nhất truyền định danh và ngữ cảnh đầy đủ theo hợp đồng API.

Tên tương đối không phải tên “không hoàn chỉnh” theo nghĩa lỗi: nó chỉ hoàn chỉnh **trong ngữ cảnh một base đã được xác định rõ**. Sai sót thường xuất hiện khi chuyển tên giữa các ngữ cảnh mà bỏ qua base.

## 9. Dựng search base động theo OU

Có trường hợp API cho người dùng chọn phòng ban để tìm nhân viên. Ví dụ người dùng chọn `contractors` để tìm dưới `ou=contractors,ou=people`.

Không nên tạo search base bằng cách nối chuỗi tùy tiện:

~~~java
// Rủi ro sai cú pháp DN khi organizationUnit chứa ký tự đặc biệt.
String relativeSearchBase = "ou=" + organizationUnit + ",ou=people";
~~~

Dùng builder hỗ trợ DN:

~~~java
import javax.naming.Name;
import org.springframework.ldap.support.LdapNameBuilder;

String organizationUnit = "contractors";

Name relativeSearchBase = LdapNameBuilder.newInstance("ou=people")
        .add("ou", organizationUnit)
        .build();

// ou=contractors,ou=people
~~~

`LdapNameBuilder` xử lý escape các ký tự đặc biệt trong giá trị RDN theo cú pháp DN. Việc escape không thay cho **kiểm tra OU có nằm trong tập được phép**: ứng dụng nên đối chiếu danh sách nhánh mà nghiệp vụ cho phép, thay vì cho người dùng chỉ định một DN tùy ý.

Nếu dùng `LdapTemplate` với một overload nhận `Name` cho search base, có thể truyền trực tiếp `relativeSearchBase`. Nếu dùng một API chỉ nhận chuỗi, chuyển từ `Name` đã dựng hợp lệ sang dạng chuỗi bằng `toString()`. Cần kiểm tra overload cụ thể của phiên bản Spring LDAP dự án đang sử dụng.

Ví dụ dùng overload của `LdapTemplate` với `SearchControls` và `AttributesMapper`:

~~~java
import java.util.List;
import javax.naming.Name;
import javax.naming.directory.SearchControls;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;

public List<String> findDirectUserNames(
        LdapTemplate template, Name relativeSearchBase) {

    SearchControls controls = new SearchControls();
    controls.setSearchScope(SearchControls.ONELEVEL_SCOPE);

    return template.search(
            relativeSearchBase,
            "(objectClass=inetOrgPerson)",
            controls,
            (AttributesMapper<String>) attributes ->
                    (String) attributes.get("cn").get());
}
~~~

Ở đây, base đã được dựng dưới `ou=people` nên không cần (và không nên) nối thêm base DN `dc=example,dc=org` một lần nữa. Filter trong ví dụ là chuỗi **cố định do ứng dụng định nghĩa**; khi đưa đầu vào người dùng vào giá trị filter, hãy dùng `LdapQueryBuilder` hoặc filter builder có escaping thay vì nối string.

## 10. Các lỗi khi cấu hình sai search base

| Triệu chứng | Nguyên nhân có thể | Cách điều tra |
| --- | --- | --- |
| Không có kết quả dù entry tồn tại | Base đặt sai OU hoặc scope không đủ sâu | Kiểm tra full DN của entry, ContextSource base, query base và scope |
| `NameNotFoundException` / LDAP `noSuchObject (32)` | Search base hiệu lực không tồn tại, thường do lặp suffix | Ghi lại hai thành phần base (không lộ bí mật) và phân giải full DN dự kiến |
| Tìm được ở môi trường A nhưng không ở B | Khác cấu hình `spring.ldap.base` | So sánh base của từng môi trường trước khi sửa filter |
| Search base rỗng trả rất nhiều kết quả | Đang tìm tại gốc ContextSource với `SUBTREE_SCOPE` | Giới hạn search base, scope và size/time limit |
| Tìm thấy An/Bình nhưng không thấy Chi | `ONELEVEL_SCOPE` không đi vào `ou=contractors` | Chuyển sang `SUBTREE_SCOPE` nếu nghiệp vụ cần |
| Có kết quả không mong muốn | Search base quá cao hoặc filter quá rộng | Thu hẹp OU, filter, thuộc tính trả về và quyền truy cập |
| Lỗi DN syntax | RDN được nối chuỗi có dấu phẩy, dấu bằng hoặc ký tự đặc biệt | Dùng `LdapNameBuilder` và xác định DN tương đối/đầy đủ |
| Tìm được nhánh nhưng không thể đọc mọi entry | ACL, referral, size/time limit hoặc chính sách server | Kiểm tra bind identity và phản hồi LDAP cụ thể |
| Tìm được người dùng nhưng cập nhật thất bại | Quyền ghi hoặc ràng buộc schema, không nhất thiết do search base | Phân biệt thao tác search với modify/bind |

Cần lưu ý một search base hợp lệ về cú pháp vẫn có thể không tồn tại trên server. Khi truy vấn thất bại, đừng vội thay đổi filter hoặc tự mở rộng search từ gốc. Hãy xác minh vị trí entry và phạm vi cho phép.

### Cách chẩn đoán có hệ thống

Với câu hỏi “tại sao không tìm thấy `uid=chi`?”, theo thứ tự:

1. Xác nhận DN thật của Chi là `uid=chi,ou=contractors,ou=people,dc=example,dc=org`.
2. Đọc cấu hình `ContextSource.base` thực tế đang dùng (tránh suy đoán từ cấu hình môi trường khác).
3. Đọc search base trong query và phân giải ra DN hiệu lực.
4. Kiểm tra `searchScope` có bao phủ lớp `ou=contractors` không.
5. Kiểm tra filter `(uid=chi)` và `(objectClass=inetOrgPerson)` có phù hợp schema/entry không.
6. Kiểm tra ACL của bind identity, referral và các giới hạn từ server.
7. Nếu vẫn sai, dùng một LDAP client kiểm thử có quyền phù hợp để so sánh cùng **base DN, scope và filter**, trên kết nối TLS đã xác minh.

Quy trình này giúp tách biệt lỗi vị trí, độ sâu, cú pháp filter, quyền truy cập và sự cố kết nối.

## 11. Kiểm thử hai cấu hình ContextSource

Để chắc chắn service không phụ thuộc nhầm vào base DN, thử cùng một cây LDAP với hai cấu hình:

**Cấu hình A:**

~~~text
ContextSource base: dc=example,dc=org
Search base:        ou=people
Effective base:     ou=people,dc=example,dc=org
Scope:              SUBTREE
Filter:             (objectClass=inetOrgPerson)
Expected:           An, Binh, Chi
~~~

**Cấu hình B:**

~~~text
ContextSource base: ou=people,dc=example,dc=org
Search base:        ""
Effective base:     ou=people,dc=example,dc=org
Scope:              SUBTREE
Filter:             (objectClass=inetOrgPerson)
Expected:           An, Binh, Chi
~~~

Hai cấu hình có thể nhắm cùng một vùng tìm kiếm, dù giá trị **query base** khác nhau. Đây là cách kiểm chứng trực quan mối quan hệ tương đối.

Trong kiểm thử tích hợp, nên bổ sung các trường hợp:

| Trường hợp | Base/Scope | Điều cần chứng minh |
| --- | --- | --- |
| Base đúng, one level | `ou=people` + one level ở cấu hình A | Chỉ An/Bình, không có Chi |
| Base đúng, subtree | `ou=people` + subtree ở cấu hình A | Bao gồm cả Chi |
| Base lặp suffix | `ou=people,dc=example,dc=org` ở cấu hình A | Truy vấn không trỏ tới nhánh people dự định |
| Base rỗng | `""` + subtree ở cấu hình B | Tìm từ `ou=people`, không phải Root DSE |
| Base nhánh không tồn tại | `ou=unknown` ở cấu hình B | Nhận kết quả/lỗi phù hợp với server; không âm thầm chuyển sang nhánh khác |
| Filter chứa ký tự đặc biệt | UID như `a*b` dùng filter builder | Ký tự `*` được xử lý như giá trị khi tìm chính xác |

Không cần đưa thông tin tài khoản hay mật khẩu thật vào báo cáo test. Sử dụng thư mục thử nghiệm có dữ liệu chủ động tạo, không thử search rộng tùy ý trên hệ thống sản xuất.

## 12. Thực hành: giải thích đường đi của truy vấn

Giả sử server có DIT của mục 1 và `ContextSource.base` bằng `dc=example,dc=org`. Với mỗi cấu hình dưới đây, hãy xác định **base hiệu lực** và **tập entry có thể được xét**, trước khi xét filter.

| Bài | Search base | Scope | Filter |
| --- | --- | --- | --- |
| A | `ou=people` | OBJECT | `(objectClass=*)` |
| B | `ou=people` | ONELEVEL | `(objectClass=inetOrgPerson)` |
| C | `ou=people` | SUBTREE | `(objectClass=inetOrgPerson)` |
| D | `ou=contractors,ou=people` | SUBTREE | `(uid=chi)` |
| E | `""` | ONELEVEL | `(objectClass=organizationalUnit)` |
| F | `ou=people,dc=example,dc=org` | SUBTREE | `(uid=an)` |

### Đáp án có giải thích

| Bài | Base hiệu lực | Kết quả dự kiến với DIT minh họa |
| --- | --- | --- |
| A | `ou=people,dc=example,dc=org` | Entry `ou=people`, do OBJECT chỉ xét chính base |
| B | `ou=people,dc=example,dc=org` | An và Bình; Chi nằm sâu hơn |
| C | `ou=people,dc=example,dc=org` | An, Bình và Chi |
| D | `ou=contractors,ou=people,dc=example,dc=org` | Chi |
| E | `dc=example,dc=org` | Các OU `people`, `groups`, `services` ở mức con trực tiếp |
| F | Có thể thành `ou=people,dc=example,dc=org,dc=example,dc=org` | Sai base do lặp suffix; không phải nhánh `ou=people` dự định |

Kết quả giả định entry tồn tại, class phù hợp, server cho phép đọc và không bị giới hạn số kết quả. Ở bài F, hình thức lỗi cụ thể do server quyết định; điều cần nhận ra là **cách cấu hình tên đã sai**.

### Bài mở rộng

Cho `ContextSource.base` đổi thành `ou=people,dc=example,dc=org`. Hãy sửa các bài B, C, D để vẫn tìm đúng vùng trước đó. Đáp án: base của B và C thành `""`, base của D thành `ou=contractors`; scope và filter giữ nguyên. Đây là ví dụ cho thấy search base trong code phải được xem trong quan hệ với `ContextSource` chứ không thể hiểu độc lập.

## 13. Những nguyên tắc cần ghi nhớ

- **Search base của `LdapTemplate` được diễn giải tương đối với base DN của `ContextSource`** trong cách sử dụng chuẩn; tránh lặp suffix của base đã cấu hình.
- **ContextSource base** là gốc cho thao tác; **search base** xác định nhánh cần tìm; **search scope** quyết định độ sâu; **filter** quyết định entry nào khớp.
- Với base `dc=example,dc=org`, search base `ou=people` trỏ tới `ou=people,dc=example,dc=org`. Với base `ou=people,dc=example,dc=org`, search base `""` cũng trỏ đến entry đó.
- Search base rỗng ở `ContextSource` có base khác rỗng **không phải Root DSE**.
- Khi tạo OU/DN động, dùng `LdapNameBuilder`; khi tạo filter chứa input, dùng `LdapQueryBuilder` hoặc API filter có escaping. Hai loại escaping **khác nhau**.
- Giới hạn base, scope, thuộc tính trả về và số kết quả để tránh truy vấn quá rộng. Dùng tài khoản có ACL tối thiểu và kết nối LDAPS/StartTLS được cấu hình, kiểm thử phù hợp.
- Trước khi sửa code vì “không thấy dữ liệu”, kiểm tra **cặp ContextSource base + query base** cùng scope và filter. Đây là cách nhanh nhất để phân biệt lỗi vị trí với lỗi truy vấn.
