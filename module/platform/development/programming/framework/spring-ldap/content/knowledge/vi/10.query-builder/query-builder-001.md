# LdapQuery và cách mô tả một truy vấn trong Spring LDAP

## 1. Từ câu hỏi nghiệp vụ đến một yêu cầu LDAP Search

Giả sử ứng dụng quản trị nhân sự cần tìm tài khoản có `uid=alice` trong toàn bộ các phòng ban thuộc `ou=people`. Ta cần xác định **tìm từ đâu**, **đi sâu bao nhiêu cấp**, **entry nào thỏa điều kiện**, **lấy những thuộc tính gì** và **có giới hạn kết quả không**.

Trong **Spring LDAP**, `LdapQuery` mô tả các thành phần của một yêu cầu tìm kiếm LDAP. `LdapQueryBuilder` cung cấp API để xây mô tả đó theo cách dễ đọc, thay vì phải ghép filter thô và quản lý nhiều tham số rời rạc.

Một truy vấn minh họa:

~~~java
import static org.springframework.ldap.query.LdapQueryBuilder.query;

LdapQuery ldapQuery = query()
        .base("ou=people")
        .searchScope(SearchScope.SUBTREE)
        .attributes("uid", "cn", "mail")
        .where("objectClass").is("inetOrgPerson")
        .and("uid").is("alice");
~~~

Đoạn trên **chỉ tạo mô tả truy vấn**. Nó chưa kết nối đến máy chủ, chưa tìm entry và chưa trả dữ liệu. Một thành phần thực thi như `LdapTemplate.search(ldapQuery, mapper)` sẽ gửi yêu cầu thông qua `ContextSource`.

Bài học thuộc chương **Query builder** của module **Spring LDAP**. Các nội dung DN, schema, filter và search scope được kết nối thành một truy vấn hoàn chỉnh; đồng thời ta sẽ xét cách xây truy vấn an toàn, giới hạn kết quả, xử lý lỗi và kiểm thử trên LDAP directory.

**Sau bài này, bạn có thể:**

- Phân biệt `LdapQuery`, `LdapQueryBuilder`, `LdapTemplate` và `ContextSource`.
- Mô tả một LDAP Search bằng **base DN, search scope, filter, danh sách thuộc tính và giới hạn**.
- Viết truy vấn an toàn với `where(...).is(...)`, kết hợp điều kiện và ánh xạ kết quả.
- Giải thích vì sao truy vấn rỗng hoặc lỗi dù filter đúng.
- Kiểm tra truy vấn bằng `ldapsearch`, TLS, ACL và dữ liệu thử nghiệm.

## 2. Năm thành phần quyết định kết quả LDAP Search

Một yêu cầu tìm kiếm LDAP có thể được hình dung như sau:

~~~text
Search request
├── Base DN           : Tìm từ entry nào?
├── Search scope      : Xét base, một cấp con hay cả subtree?
├── Search filter     : Entry nào phù hợp điều kiện?
├── Returning attrs   : Trả những thuộc tính nào?
└── Size/time limits  : Dừng sau bao nhiêu kết quả hoặc bao lâu?

           LdapQuery
               |
               v
        LdapTemplate.search(...)
               |
          ContextSource
               |
            LDAP server
               |
       ACL + schema + matching
               |
          Search results
~~~

| Thành phần | Ví dụ | Vai trò |
| --- | --- | --- |
| **Base DN** | `ou=people` (tương đối) | Gốc duyệt cây |
| **Scope** | `SearchScope.SUBTREE` | Bao gồm base và mọi entry hậu duệ |
| **Filter** | `(&(objectClass=inetOrgPerson)(uid=alice))` | Điều kiện để một entry được chọn |
| **Attributes** | `uid`, `cn`, `mail` | Thuộc tính được yêu cầu trong kết quả |
| **Limits** | 100 entry; 5.000 ms | Giới hạn phía client, có thể bị server giới hạn chặt hơn |

Hai điểm cần nhớ:

1. **Filter không thay thế base/scope.** Dù bộ lọc đúng, truy vấn không tự tìm qua những OU nằm ngoài phạm vi đã chọn.
2. **Attributes không phải điều kiện lọc.** Yêu cầu chỉ trả `cn` không có nghĩa LDAP chỉ tìm entry có `cn`; nếu cần điều kiện, phải đưa vào filter.

Một `LdapQuery` mô tả **một thao tác tìm kiếm**, không phải một transaction, không phải câu lệnh tạo/sửa entry, không thay đổi bind DN và không quyết định máy chủ nào được kết nối.

## 3. Ví dụ cây LDAP: base, scope và filter kết hợp thế nào?

Xét thư mục thử nghiệm:

~~~text
dc=example,dc=org
├── ou=people
│   ├── uid=alice
│   ├── ou=engineering
│   │   ├── uid=bob
│   │   └── ou=platform
│   │       └── uid=carol
│   └── ou=sales
│       └── uid=david
└── ou=groups
    └── cn=developers
~~~

Giả sử các entry `alice`, `bob`, `carol` và `david` có object class `inetOrgPerson`, còn các OU có `organizationalUnit`.

### 3.1. Base được tính từ ContextSource thế nào?

Nếu `LdapContextSource` đã cấu hình:

~~~text
ContextSource base = dc=example,dc=org
~~~

thì query:

~~~java
LdapQuery q = query()
        .base("ou=people")
        .searchScope(SearchScope.SUBTREE)
        .where("objectClass").is("inetOrgPerson");
~~~

thường tìm từ **DN hiệu lực**:

~~~text
ou=people,dc=example,dc=org
~~~

Không nên lặp lại `dc=example,dc=org` vào query base tương đối nếu đã cấu hình nó ở ContextSource. Trong khi đó, công cụ `ldapsearch` thường yêu cầu **DN đầy đủ** qua tham số `-b`.

### 3.2. Ba search scope

| Scope Spring LDAP | Ý nghĩa với base `ou=people` | Entry được xét |
| --- | --- | --- |
| `SearchScope.OBJECT` | Chỉ entry tại base | `ou=people` |
| `SearchScope.ONELEVEL` | Chỉ entry con trực tiếp, không gồm base | `uid=alice`, `ou=engineering`, `ou=sales` |
| `SearchScope.SUBTREE` | Base và mọi hậu duệ | `alice`, `bob`, `carol`, `david` cùng các OU trong nhánh |

Các entry trong cột cuối mới là **ứng viên được xét**; filter và quyền truy cập mới quyết định chúng có thực sự xuất hiện trong kết quả hay không.

Với filter `(objectClass=inetOrgPerson)` và quyền đọc đầy đủ trên dữ liệu mẫu:

- OBJECT không trả người dùng vì entry `ou=people` không phải `inetOrgPerson`.
- ONELEVEL trả `alice`.
- SUBTREE trả `alice`, `bob`, `carol`, `david`.

Không scope nào tự mở rộng sang `ou=groups` khi base là `ou=people`.

### 3.3. Filter là biểu thức logic, không phải đường dẫn

Ví dụ:

~~~ldap
(&(objectClass=inetOrgPerson)(uid=alice))
~~~

Dấu `&` nghĩa là **AND**: entry phải vừa là người dùng phù hợp object class, vừa có `uid=alice`. Nếu bỏ điều kiện object class, truy vấn có thể chấp nhận những entry loại khác cũng có thuộc tính `uid`.

Tuy nhiên, một filter đúng cú pháp không đảm bảo kết quả: `uid` phải được định nghĩa đúng theo schema, tài khoản phải có quyền tìm kiếm và entry cần nằm trong base/scope được chọn.

## 4. Thiết lập ContextSource và LdapTemplate

Để chạy `LdapQuery`, ứng dụng cần một `LdapTemplate` được cấu hình với `ContextSource`. Ví dụ Java Config:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.core.support.LdapContextSource;

@Configuration
public class LdapConfiguration {

    @Bean
    public LdapContextSource ldapContextSource(
            @Value("${app.ldap.url}") String url,
            @Value("${app.ldap.base}") String base,
            @Value("${app.ldap.bind-dn}") String bindDn,
            @Value("${app.ldap.bind-password}") String password) {
        LdapContextSource source = new LdapContextSource();
        source.setUrl(url);
        source.setBase(base);
        source.setUserDn(bindDn);
        source.setPassword(password);
        return source;
    }

    @Bean
    public LdapTemplate ldapTemplate(LdapContextSource ldapContextSource) {
        return new LdapTemplate(ldapContextSource);
    }
}
~~~

~~~yaml
# application.yml: thông tin giả định cho LDAP thử nghiệm
app:
  ldap:
    url: ${LDAP_URL:ldaps://ldap.example.org:636}
    base: dc=example,dc=org
    bind-dn: ${LDAP_BIND_DN}
    bind-password: ${LDAP_BIND_PASSWORD}
~~~

`app.ldap.*` là nhóm thuộc tính **do ứng dụng ví dụ định nghĩa**. Nếu dùng cấu hình tự động của Spring Boot, dự án có thể sử dụng `spring.ldap.urls`, `spring.ldap.base`, `spring.ldap.username`, `spring.ldap.password` với dependency thích hợp. Không tự tạo hai bean có cùng chức năng mà không biết bean nào được tiêm vào repository.

Các vai trò khác nhau:

- **URL** `ldaps://ldap.example.org:636`: nơi kết nối và giao thức.
- **Base DN** `dc=example,dc=org`: hậu tố/gốc giải quyết DN tương đối.
- **Bind DN**: danh tính tài khoản truy cập server.
- **Query base** `ou=people`: nhánh cụ thể của từng truy vấn.

Cần tin cậy chứng chỉ TLS và xác minh hostname. Tài khoản chỉ tra cứu không nên có quyền sửa/xóa entry hoặc thay đổi schema. Không đưa mật khẩu vào mã nguồn, log hoặc câu trả lời của API.

## 5. Viết truy vấn đầu tiên: tìm UID theo toàn bộ nhánh

Mẫu sau triển khai repository tìm tên hiển thị của người dùng từ một UID. Giả sử người dùng có thể nằm dưới nhiều OU con trong `ou=people`.

~~~java
import java.util.List;

import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.SearchScope;
import org.springframework.stereotype.Repository;

import static org.springframework.ldap.query.LdapQueryBuilder.query;

@Repository
public class UserDirectoryRepository {

    private final LdapTemplate ldapTemplate;

    public UserDirectoryRepository(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<String> findNamesByUid(String uid) {
        if (uid == null || uid.isBlank()) {
            throw new IllegalArgumentException("uid must not be blank");
        }

        LdapQuery ldapQuery = query()
                .base("ou=people")
                .searchScope(SearchScope.SUBTREE)
                .attributes("cn")
                .where("objectClass").is("inetOrgPerson")
                .and("uid").is(uid);

        return ldapTemplate.search(
                ldapQuery,
                (AttributesMapper<String>) attributes -> {
                    if (attributes.get("cn") == null) {
                        return "";
                    }
                    return String.valueOf(attributes.get("cn").get());
                }
        );
    }
}
~~~

### 5.1. Đọc code theo thứ tự

1. `query()` tạo builder.
2. `.base("ou=people")` chọn DN tìm kiếm **tương đối với ContextSource base**.
3. `.searchScope(SearchScope.SUBTREE)` tìm ở tất cả OU con.
4. `.attributes("cn")` chỉ yêu cầu trường hiển thị cần thiết.
5. `.where("objectClass").is("inetOrgPerson").and("uid").is(uid)` xây filter AND; giá trị `uid` được mã hóa đúng ngữ pháp filter.
6. `ldapTemplate.search(ldapQuery, mapper)` **thực thi** yêu cầu và ánh xạ các entry thành `List<String>`.

**Điểm quan trọng:** builder mô tả câu hỏi; template đặt câu hỏi đó tới LDAP server và xử lý kết quả. Đừng gọi `query()` rồi nghĩ dữ liệu đã được đọc.

### 5.2. Tại sao ví dụ trả List thay vì chỉ một người dùng?

Một LDAP search có thể khớp nhiều entry. Không nên mặc định `uid` là khóa duy nhất trên **toàn bộ subtree** trong mọi triển khai; hai OU con có thể có cùng UID nếu server không áp ràng buộc riêng.

Nếu nghiệp vụ yêu cầu duy nhất, phải kiểm tra các kết quả `0`, `1` và `>1` với thông báo và chính sách cụ thể. Không tự lấy phần tử đầu rồi coi là tài khoản đúng. Cũng không dựa vào thứ tự kết quả, vì tìm kiếm LDAP thông thường không tự đảm bảo sắp xếp ổn định.

### 5.3. Điều gì xảy ra khi thuộc tính không được trả về?

Trong schema chuẩn, `inetOrgPerson` kế thừa `person` có `cn` bắt buộc, nhưng ACL có thể khiến client không nhìn thấy một thuộc tính. Mapper của ví dụ trả chuỗi rỗng khi `cn` không có trong kết quả; ứng dụng thật nên quyết định rõ có bỏ qua entry, dùng giá trị dự phòng hay báo thiếu dữ liệu.

Một số thuộc tính đa trị cần duyệt toàn bộ giá trị, không chỉ gọi `Attribute.get()` một lần.

## 6. Mô tả truy vấn có nhiều điều kiện

Một query thường kết hợp điều kiện nghiệp vụ. Ví dụ chỉ tìm người dùng có object class phù hợp, thuộc OU đúng và UID đã biết:

~~~java
LdapQuery q = query()
        .base("ou=people")
        .searchScope(SearchScope.SUBTREE)
        .attributes("uid", "cn", "mail")
        .where("objectClass").is("inetOrgPerson")
        .and("uid").is(uid);
~~~

Filter tương đương về mặt logic:

~~~ldap
(&(objectClass=inetOrgPerson)(uid=alice))
~~~

Trong filter ví dụ, `alice` là một **giá trị minh họa**. Nếu `uid` nhận từ client, không nên ghép chuỗi filter thô. Builder nhận giá trị rồi escape các ký tự đặc biệt theo cú pháp LDAP filter.

### 6.1. Các toán tử filter thường cần biết

| Cú pháp LDAP | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `(uid=alice)` | So sánh bằng | UID chính xác |
| `(mail=*)` | Kiểm tra thuộc tính tồn tại | Có ít nhất một giá trị mail |
| `(cn=A*)` | So khớp substring nếu schema hỗ trợ | Tên bắt đầu bằng A |
| `(&(a=x)(b=y))` | AND | Cả hai điều kiện |
| `(|(a=x)(a=y))` | OR | Ít nhất một điều kiện |
| `(!(a=x))` | NOT | Phủ định điều kiện |
| `(score>=10)` | So sánh ngưỡng dưới | Cần ordering matching rule |
| `(score<=20)` | So sánh ngưỡng trên | Cần ordering matching rule |

Ở đây `score` là thuộc tính **giả định**, không phải thuộc tính chuẩn có sẵn trong `inetOrgPerson`. Các filter lớn hơn/bé hơn chỉ có ý nghĩa khi attribute type của server có **ordering matching rule** phù hợp.

Không nên tự triển khai mọi phép so sánh bằng nối chuỗi. Khi cần filter phức tạp, sử dụng các phương thức của `LdapQueryBuilder` hoặc đối tượng `Filter` tương ứng với phiên bản Spring LDAP; tránh tạo cấu trúc filter từ đầu vào không tin cậy.

### 6.2. Base, scope, filter và attributes không hoán đổi cho nhau

Một lỗi thiết kế phổ biến là chọn base rất rộng `dc=example,dc=org`, subtree và filter quá đơn giản `(objectClass=*)`, sau đó lọc phần lớn dữ liệu ở Java. Truy vấn này có thể quét nhiều entry, đọc dữ liệu không liên quan và chạm giới hạn server.

Cách tốt hơn là chọn base vừa đủ (ví dụ `ou=people`), filter có tính chọn lọc (`uid` hoặc điều kiện nghiệp vụ phù hợp) và chỉ yêu cầu thuộc tính cần thiết. Nếu LDAP server không index thuộc tính được tìm, code Java tối ưu vẫn không tự làm server tìm nhanh hơn.

## 7. Giới hạn kết quả và thời gian tìm kiếm

Ngoài base, scope, filter và attributes, `LdapQueryBuilder` có thể biểu đạt **count limit** và **time limit** theo API của Spring LDAP.

~~~java
LdapQuery q = query()
        .base("ou=people")
        .searchScope(SearchScope.SUBTREE)
        .attributes("uid", "cn")
        .countLimit(100)
        .timeLimit(5000)
        .where("objectClass").is("inetOrgPerson");
~~~

Các số trên chỉ **minh họa**: tối đa 100 kết quả theo giới hạn phía client được truyền đi và thời hạn 5.000 mili-giây. Giới hạn phía server, chính sách phân quyền và các control LDAP có thể tác động thêm; **đạt giới hạn không đồng nghĩa đã duyệt hết thư mục**.

Các API này không tương đương với paging. Một request có count limit 100 không tự lấy trang 2 khi server còn hàng nghìn entry.

### 7.1. Khi nào cần paging?

Nếu một màn hình quản trị chỉ cần tối đa vài chục kết quả, giới hạn kích thước có thể phù hợp. Nhưng nếu mục tiêu là đồng bộ hàng chục nghìn entry, ứng dụng cần thiết kế phân trang (chẳng hạn LDAP Simple Paged Results control nếu server hỗ trợ), quản lý cookie/trạng thái phiên và kiểm tra kết quả có bị cắt không. Không nên dựa vào `countLimit` để báo cáo rằng “đã tải đầy đủ”.

### 7.2. Timeout tìm kiếm khác timeout mạng

`timeLimit` của query là giới hạn ở mức tìm kiếm; timeout mở kết nối và timeout đọc mạng được cấu hình riêng theo `ContextSource`/JNDI provider. Một timeout không nên bị bắt rồi đổi thành danh sách rỗng, vì ứng dụng sẽ nhầm lỗi hạ tầng thành “người dùng không tồn tại”.

## 8. Ánh xạ kết quả: LdapQuery không quyết định kiểu Java trả về

`LdapQuery` xác định những entry được hỏi; **mapper** xác định cách chuyển một entry thành đối tượng Java. Ví dụ cần trả thêm UID và email:

~~~java
import java.util.List;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;
import javax.naming.NamingException;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;

import static org.springframework.ldap.query.LdapQueryBuilder.query;

// Java 17: record minh họa dữ liệu trình bày.
record PersonSummary(String uid, String name, String mail) {}

class PeopleLookup {
    private final LdapTemplate template;

    PeopleLookup(LdapTemplate template) {
        this.template = template;
    }

    List<PersonSummary> findPeople() {
        LdapQuery q = query()
                .base("ou=people")
                .attributes("uid", "cn", "mail")
                .where("objectClass").is("inetOrgPerson");

        return template.search(q,
                (AttributesMapper<PersonSummary>) attrs ->
                        new PersonSummary(
                                firstValue(attrs, "uid"),
                                firstValue(attrs, "cn"),
                                firstValue(attrs, "mail")
                        ));
    }

    private static String firstValue(Attributes attrs, String name)
            throws NamingException {
        Attribute attr = attrs.get(name);
        return attr == null ? null : String.valueOf(attr.get());
    }
}
~~~

Ví dụ này dùng `record`, vốn có trong các phiên bản Java hiện đại; với dự án Java cũ hơn có thể thay bằng một lớp POJO thông thường. `mail` có thể vắng mặt nên mapper trả `null` cho trường tương ứng; chính sách biểu diễn ở API phải được quyết định riêng.

Ở ví dụ này, query chưa chỉ rõ search scope. **Khi scope là yêu cầu nghiệp vụ, nên đặt tường minh** `.searchScope(SearchScope.SUBTREE)` hoặc scope khác thay vì dựa vào hành vi mặc định của một API/phiên bản thư viện. Điều này quan trọng nếu người dùng có thể nằm dưới nhiều OU con.

Nếu muốn lấy **DN** cùng thuộc tính, có thể dùng mapper nhận ngữ cảnh LDAP tương ứng (ví dụ ContextMapper/DirContextOperations theo API được hỗ trợ). DN không phải là một thuộc tính thông thường như `cn`; tránh suy ra rằng liệt kê `dn` trong danh sách thuộc tính luôn trả cùng một dữ liệu ở mọi server.

### 8.1. Mapper cho thuộc tính đa trị

Một entry có thể có nhiều giá trị `telephoneNumber` hoặc `description`. `Attribute.get()` chỉ lấy một giá trị; nếu cần tất cả, phải duyệt `Attribute.getAll()` và đóng enumeration theo hợp đồng JNDI. Query builder không tự biến thuộc tính đa trị thành một chuỗi chính xác.

### 8.2. LdapClient và ODM đặt ở đâu?

`LdapClient` có thể cung cấp fluent API ở những phiên bản Spring LDAP hỗ trợ; ODM ánh xạ entry vào lớp Java. Dù cách gọi khác `LdapTemplate`, server vẫn xử lý **base, scope, filter và ACL** theo giao thức LDAP. Khái niệm `LdapQuery` giúp hiểu cấu trúc câu hỏi độc lập với cách map kết quả.

## 9. Chống LDAP injection: phân biệt filter value và DN

LDAP có nhiều ngữ pháp cần escaping khác nhau. Hai ngữ pháp đặc biệt cần phân biệt là **filter** và **DN/RDN**.

### 9.1. Tránh tự ghép chuỗi filter

**Không nên làm:**

~~~java
String unsafeFilter = "(uid=" + suppliedUid + ")";
~~~

Nếu `suppliedUid` chứa `*` hoặc dấu ngoặc, cách nối chuỗi có thể thay đổi ý nghĩa filter. Với LDAP filter, các ký tự trong giá trị cần escape gồm `*`, `(`, `)`, dấu gạch chéo ngược và NUL.

**Nên dùng builder:**

~~~java
LdapQuery safe = query()
        .base("ou=people")
        .where("uid").is(suppliedUid);
~~~

Giá trị được mã hóa theo cú pháp **filter**. Không tự escape hai lần và không lấy dữ liệu người dùng làm **tên thuộc tính** hay **biểu thức logic** tùy ý.

### 9.2. Base DN cũng cần được kiểm soát

Một query base như `ou=people` nên đến từ **cấu hình tin cậy hoặc một tập giá trị allowlist**, không phải chuỗi DN tùy ý do client gửi để quét mọi OU.

Nếu thật sự cần xây DN từ giá trị người dùng, hãy sử dụng công cụ tạo DN có cấu trúc như `LdapNameBuilder`:

~~~java
import javax.naming.Name;
import org.springframework.ldap.support.LdapNameBuilder;

Name userDn = LdapNameBuilder.newInstance("ou=people")
        .add("uid", suppliedUid)
        .build();
~~~

`LdapNameBuilder` xử lý cú pháp **DN**, khác hoàn toàn với escaping của `where("uid").is(...)` cho **filter**.

### 9.3. Validation và hạn chế tài nguyên

Builder giúp giảm rủi ro injection qua filter values, nhưng không quyết định một UID dài hàng chục nghìn ký tự có hợp lệ về nghiệp vụ hay không. Tầng API cần kiểm tra dữ liệu đầu vào, giới hạn phạm vi OU, kích thước và thời gian truy vấn, cũng như những thuộc tính có thể tìm kiếm. Một truy vấn đúng cú pháp vẫn có thể gây tải quá lớn.

## 10. So sánh LdapQuery với lệnh ldapsearch và JNDI

### 10.1. Lệnh tương đương trên command line

Với dữ liệu ví dụ, có thể thử trực tiếp trên LDAP server thử nghiệm:

~~~bash
ldapsearch -LLL -x \
  -H "ldaps://ldap.example.org:636" \
  -D "cn=directory-reader,ou=system,dc=example,dc=org" -W \
  -b "ou=people,dc=example,dc=org" -s sub \
  "(&(objectClass=inetOrgPerson)(uid=alice))" \
  uid cn mail
~~~

So sánh:

| Spring LDAP | ldapsearch | Ý nghĩa |
| --- | --- | --- |
| ContextSource URL | `-H` | Máy chủ và giao thức |
| ContextSource bind credentials | `-D` và `-W` | Danh tính xác thực |
| Base `ou=people` + ContextSource base `dc=example,dc=org` | `-b ou=people,dc=example,dc=org` | DN tìm kiếm hiệu lực |
| `SearchScope.SUBTREE` | `-s sub` | Tìm mọi cấp trong nhánh |
| `where(...).is(...)` | Chuỗi filter trong dấu ngoặc kép | Điều kiện |
| `attributes("uid","cn","mail")` | `uid cn mail` | Thuộc tính cần trả |

`-W` yêu cầu nhập mật khẩu tương tác, tránh lộ mật khẩu trong lịch sử lệnh. Tên host, DN và tài khoản đều là ví dụ. Nếu chứng chỉ không được tin cậy, hãy sửa truststore/CA và tên host; không tắt TLS verification để chạy lệnh.

### 10.2. JNDI trực tiếp dùng SearchControls

Trong JNDI, một truy vấn tương tự có thể dùng `SearchControls` để đặt scope và thuộc tính:

~~~java
import javax.naming.directory.SearchControls;

SearchControls controls = new SearchControls();
controls.setSearchScope(SearchControls.SUBTREE_SCOPE);
controls.setReturningAttributes(new String[] {"uid", "cn", "mail"});
controls.setCountLimit(100L);
controls.setTimeLimit(5000);

// DirContext.search(baseDn, filter, controls) thực hiện truy vấn.
~~~

Khi dùng JNDI trực tiếp, ứng dụng còn phải tự quản lý `DirContext`, `NamingEnumeration` và ngoại lệ. `LdapQueryBuilder` giúp tập trung mô tả tìm kiếm; `LdapTemplate` thực hiện và quản lý vòng đời tài nguyên theo framework.

## 11. Chẩn đoán khi query không có kết quả hoặc phát sinh lỗi

Không nên coi “truy vấn trả rỗng” và “truy vấn không thực hiện được” là một.

| Triệu chứng | Nguyên nhân có thể | Bước kiểm tra |
| --- | --- | --- |
| Trả danh sách rỗng | Không có entry khớp, sai base/scope/filter hoặc ACL che dữ liệu | So sánh với ldapsearch, xác nhận DN và quyền |
| Chỉ thấy người dùng ở OU trực tiếp | Scope là ONELEVEL thay vì SUBTREE | Kiểm tra `searchScope` và cấu trúc cây |
| Không thấy `mail` trong mapper | Không yêu cầu thuộc tính, entry không có mail hoặc quyền đọc bị hạn chế | Kiểm tra `attributes(...)`, schema, ACL |
| LDAP **32 / noSuchObject** | Base DN không tồn tại hoặc không thể thấy | Xác nhận DN tương đối/tuyệt đối |
| LDAP **50 / insufficientAccessRights** | Bind identity thiếu quyền | Kiểm tra ACL; không nâng quyền tùy tiện |
| LDAP **87 / filterError** | Filter sai cú pháp | Kiểm tra builder, giá trị và điều kiện |
| LDAP **18 / inappropriateMatching** | Matching rule không phù hợp | Kiểm tra schema của attribute type |
| LDAP **3 / timeLimitExceeded** | Quá giới hạn thời gian | Xem scope, index, timeout, tải server |
| LDAP **4 / sizeLimitExceeded** | Kết quả vượt giới hạn | Thu hẹp query hoặc dùng paging nếu phù hợp |
| TLS/bind/connection failure | Sai chứng chỉ, credentials, endpoint hoặc server lỗi | Kiểm tra truststore, URL, network và log an toàn |

Các LDAP server có thể trả thông báo chi tiết khác nhau hoặc che dữ liệu theo chính sách. Log nên thể hiện loại truy vấn, mã LDAP, thời hạn, tên bean/context và correlation ID ở mức cần thiết; không log mật khẩu, toàn bộ entry chứa thông tin cá nhân hoặc filter chứa bí mật.

### 11.1. Search không phải thao tác sửa

Một `LdapQuery` và `LdapTemplate.search` chỉ mô tả và thực hiện **đọc**. Muốn thêm/sửa/xóa entry, dùng những API chuyên biệt như `bind`, `modifyAttributes`, `rename`, `unbind` theo quyền được cấp. Không nhầm query builder với một công cụ cập nhật LDAP.

### 11.2. Bảo mật và pooling

Pooling có thể giảm chi phí lấy context nhưng không làm filter rộng trở nên hiệu quả, không tự cấp thêm quyền và không thay thế TLS. Nếu dùng nhiều bind identity hay StartTLS, cần đánh giá tương thích với provider, tránh tái dùng context sai danh tính. Một lời gọi template thông thường tự giải phóng tài nguyên; khi thao tác trực tiếp với `DirContext` phải đóng nó đúng vòng đời.

## 12. Kiểm thử LdapQuery trên dữ liệu nhiều cấp OU

Hãy chuẩn bị một **LDAP directory thử nghiệm** với các entry `alice`, `bob`, `carol`, `david` theo cây phần 3. Dữ liệu phải hợp schema (ví dụ `inetOrgPerson` với `cn`, `sn`), tài khoản đọc có ACL phù hợp và kết nối LDAPS với chứng chỉ tin cậy.

### 12.1. Ma trận test

| Truy vấn | Kết quả mong đợi |
| --- | --- |
| Base `ou=people`, scope OBJECT, filter `(objectClass=inetOrgPerson)` | Không có user |
| Base `ou=people`, scope ONELEVEL, cùng filter | `alice` |
| Base `ou=people`, scope SUBTREE, cùng filter | `alice, bob, carol, david` |
| SUBTREE với UID `bob` | Đúng entry `bob` trong OU con |
| SUBTREE với UID không tồn tại | Danh sách rỗng nếu request thành công |
| Base `ou=groups`, filter `(uid=alice)` | Không tìm thấy Alice |
| Query chỉ trả `cn` | Không tự có toàn bộ thuộc tính trong mapper |
| Count limit thấp hơn số entry | Kết quả không được coi là tập hoàn chỉnh |
| Đầu vào UID chứa `*`, `(`, `)` | Builder xử lý như giá trị filter, không tự biến thành điều kiện khác |
| Bind sai hoặc chứng chỉ TLS không hợp lệ | Có lỗi kết nối/xác thực, không “trả rỗng” như kết quả bình thường |

Lưu ý: thứ tự LDAP search không được đảm bảo, nên so sánh **tập DN hoặc UID** thay vì vị trí phần tử. Nếu UID có thể trùng ở nhiều OU, hãy so sánh DN thực để tránh nhận nhầm tài khoản.

### 12.2. Kiểm thử phần dựng query và phần thực thi

Có hai lớp kiểm thử khác nhau:

1. **Kiểm thử logic dựng truy vấn:** base, scope, filter, attributes và limits đã phản ánh đúng yêu cầu nghiệp vụ chưa? Có sử dụng giá trị an toàn và validate đầu vào không?
2. **Kiểm thử tích hợp:** LDAP server thực sự xử lý filter và matching rule như mong đợi không? ACL, paging, TLS, schema, index và dữ liệu cây thực tế có tương thích không?

Một unit test chỉ mock `LdapTemplate` không thể chứng minh quyền LDAP hoặc filter thực sự được server đánh giá chính xác. Không chạy kiểm thử ghi vào tài khoản thật và không tự nâng quyền production để làm một case test qua được.

## 13. Bài thực hành từng bước

**Bối cảnh:** một hệ thống đăng nhập cần tìm người dùng bằng UID trong các OU con khác nhau, chỉ lấy `uid`, `cn`, `mail` và không được quét sang OU nhóm.

1. **Xác định dữ liệu:** từ cây phần 3, viết DN đầy đủ của Bob và Carol; chỉ ra vì sao ONELEVEL có thể bỏ sót hai entry này.
2. **Dựng query:** với ContextSource base `dc=example,dc=org`, sử dụng `query().base("ou=people")`, `SearchScope.SUBTREE` và filter `where("uid").is(uid)`.
3. **Thêm object class:** kết hợp `objectClass=inetOrgPerson` bằng AND để chỉ chọn entry người dùng.
4. **Giới hạn thuộc tính:** yêu cầu `uid`, `cn`, `mail`, rồi ánh xạ thành một DTO/record phù hợp.
5. **Thực thi:** gọi `LdapTemplate.search`, thử UID có thật ở OU sâu, UID không tồn tại và một UID chứa ký tự đặc biệt.
6. **Đối chiếu:** chạy một lệnh `ldapsearch -s sub -b "ou=people,dc=example,dc=org"` với filter tương đương; so sánh DN và giá trị trả về.
7. **Scope:** đổi sang OBJECT/ONELEVEL, giải thích vì sao số kết quả thay đổi dù filter giữ nguyên.
8. **Limits:** thêm count/time limit phù hợp với dữ liệu thử nghiệm, mô tả cách phát hiện kết quả không đầy đủ; nếu cần paging, nghiên cứu cơ chế server hỗ trợ.
9. **Quyền:** dùng tài khoản chỉ đọc được cấp phép, rồi thử tài khoản có quyền hạn chế trên nhánh khác. Phân biệt ACL với sai query.
10. **Bảo mật:** xác minh chứng chỉ/hostname LDAPS; kiểm tra không log mật khẩu hoặc dữ liệu cá nhân không cần thiết, không biến giá trị người dùng thành DN/filter thô.

### Câu hỏi tự kiểm tra

1. `LdapQuery` mô tả điều gì và `LdapTemplate` làm gì thêm?
2. Vì sao `.base("ou=people")` có thể tương ứng với DN đầy đủ `ou=people,dc=example,dc=org`?
3. Sự khác nhau giữa OBJECT, ONELEVEL và SUBTREE là gì?
4. Vì sao `.attributes("cn")` không tương đương điều kiện `(cn=*)`?
5. Khi tìm UID từ đầu vào API, vì sao builder tốt hơn ghép `"(uid=" + uid + ")"`?
6. Count limit có chứng minh client đã đọc hết directory không?
7. Tại sao trả về hai entry cùng UID không nên được tự giải quyết bằng cách lấy phần tử đầu tiên?
8. Điều gì làm một query trả rỗng dù filter hợp lệ về cú pháp?
9. Vì sao search query không thể tự tạo hoặc sửa entry?
10. Khi nào cần kiểm thử tích hợp với LDAP thật thay vì chỉ kiểm thử đối tượng query?

## 14. Tổng kết

**`LdapQuery` là mô tả một yêu cầu LDAP Search**, còn **`LdapQueryBuilder`** giúp tạo mô tả đó bằng các phương thức có ý nghĩa: **base**, **search scope**, **filter**, **returning attributes** và **limits**. **`LdapTemplate.search(...)`** mới thực thi truy vấn thông qua `ContextSource` và ánh xạ kết quả. Để query đúng, cần hiểu DN tương đối/tuyệt đối, schema và filter matching, quyền ACL và vị trí entry trong cây thư mục. Để query an toàn, hãy dùng builder thay cho nối filter từ đầu vào, giới hạn base/scope và tài nguyên, bảo vệ kết nối bằng TLS đã xác minh, xử lý lỗi khác với kết quả rỗng và kiểm thử trên LDAP server phù hợp.
