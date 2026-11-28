# Ảnh hưởng của alias và chính sách dereference

Trong **Spring Data LDAP**, một tên phân biệt (DN) thường xác định trực tiếp một entry trong Directory Information Tree (DIT). Tuy nhiên, LDAP còn hỗ trợ **alias entry**: một entry có tên riêng nhưng trỏ tới entry khác bằng DN trong attribute `aliasedObjectName`. Alias giúp duy trì tên cũ sau khi tổ chức di chuyển hoặc đổi cấu trúc nhánh directory.

Khi ứng dụng tìm kiếm qua alias, cần quyết định **có dereference alias hay không, và dereference ở giai đoạn nào**. Chính sách này ảnh hưởng đến entry được tìm thấy, phạm vi search, số lượng kết quả, quyền truy cập thực tế và khả năng tương thích giữa các LDAP server.

Một khái niệm khác dễ bị nhầm là **LDAP referral**. Alias trỏ tới một DN; referral cung cấp một hoặc nhiều URL để client tiếp tục truy cập server/directory khác. Alias thường được server xử lý trong quá trình search; referral được trả cho client để client quyết định theo, bỏ qua hoặc xử lý thủ công.

Sau bài học, bạn có thể:

- Nhận diện alias entry và attribute `aliasedObjectName` theo RFC 4512.
- Phân biệt alias dereferencing với referral handling.
- Giải thích bốn chính sách `never`, `searching`, `finding` và `always`.
- Cấu hình alias dereferencing qua JNDI LDAP provider và Spring LDAP ContextSource.
- Hiểu vì sao `SearchControls.setDerefLinkFlag(...)` không điều khiển LDAP alias.
- Đánh giá tác động lên base DN, search scope, filter, kết quả trùng và hiệu năng.
- Thiết kế ACL, giới hạn referral và kiểm thử để tránh truy cập ngoài phạm vi dự kiến.

## 1. Alias entry trong LDAP là gì?

Alias là một entry có tên riêng, nhưng chỉ tới một đối tượng khác trong directory. Theo RFC 4512, alias entry:

- Thuộc structural object class `alias`.
- Bắt buộc có attribute `aliasedObjectName` chứa DN được trỏ tới.
- Là entry lá, không có subordinate entry.
- Có thể trỏ tới entry thường hoặc một alias khác.
- Có thể có nhiều alias cùng trỏ tới một entry đích.

Ví dụ directory có nhánh nhân viên:

```text
dc=example,dc=org
└── ou=people
    ├── uid=lan
    ├── uid=minh
    └── uid=mai
```

Sau khi đổi tên nhánh hoặc duy trì tên cũ cho ứng dụng, quản trị viên tạo alias `cn=staff` trỏ tới `ou=people`:

```ldif
dn: cn=staff,dc=example,dc=org
objectClass: top
objectClass: alias
objectClass: extensibleObject
cn: staff
aliasedObjectName: ou=people,dc=example,dc=org
```

Khi client tìm kiếm qua alias và chính sách dereference cho phép, server có thể xử lý search như thể tên alias đang chỉ tới nhánh `ou=people`.

### 1.1. Alias giữ tên cũ khi directory thay đổi

Giả sử trước đây ứng dụng sử dụng:

```text
ou=hardware,dc=example,dc=org
ou=software,dc=example,dc=org
```

Hai nhóm được hợp nhất vào:

```text
ou=engineering,dc=example,dc=org
```

Directory có thể giữ các tên cũ bằng alias:

```text
ou=hardware  ──────┐
                   ├──> ou=engineering
ou=software  ──────┘
```

Các ứng dụng cũ tiếp tục sử dụng DN quen thuộc trong khi directory đã tổ chức lại. Alias không sao chép dữ liệu; nó cung cấp một tên khác để phân giải tới đối tượng đích.

### 1.2. Alias không phải bản sao entry

Alias entry không chứa toàn bộ attribute của đối tượng đích. Attribute `aliasedObjectName` lưu tên được trỏ tới. Khi dereference, server thực hiện phân giải tên theo quy tắc LDAP.

Nếu tắt dereference, ứng dụng có thể nhìn thấy chính alias entry cùng `objectClass: alias` và `aliasedObjectName` thay vì các attribute của entry đích. Kết quả cụ thể còn phụ thuộc base, scope, filter và khả năng của server.

### 1.3. Alias có thể trỏ tiếp tới alias

Ví dụ:

```text
cn=old-staff
    |
    v
cn=staff
    |
    v
ou=people
```

RFC 4511 cho phép quá trình dereference đệ quy khi alias trỏ tới alias. Server **MUST phát hiện vòng lặp alias** để tránh việc phân giải lặp vô hạn và nguy cơ từ chối dịch vụ.

Không tự xây vòng alias trong dữ liệu production. Khi import hoặc cập nhật alias, cần xác minh target DN và phát hiện chu trình ở quy trình quản trị dữ liệu.

## 2. Alias dereferencing diễn ra ở đâu?

Trong LDAP protocol, SearchRequest có trường `derefAliases`. Trường này xác định server có dereference alias trong hai giai đoạn hay không:

1. Khi định vị đối tượng được chỉ định bởi base DN.
2. Khi tìm kiếm các entry subordinate nằm trong search scope.

RFC 4511 định nghĩa bốn giá trị:

| Giá trị LDAP | Giá trị JNDI | Ý nghĩa |
| --- | --- | --- |
| `neverDerefAliases (0)` | `never` | Không dereference alias ở base object hoặc trong quá trình search |
| `derefInSearching (1)` | `searching` | Dereference alias gặp trong các entry được tìm bên dưới base; không dereference alias dùng làm base |
| `derefFindingBaseObj (2)` | `finding` | Dereference alias khi định vị base object; không dereference alias gặp trong các subordinate entry |
| `derefAlways (3)` | `always` | Dereference cả alias ở base object lẫn alias gặp trong quá trình search |

Tên trong cột JNDI là các giá trị chuỗi mà JDK LDAP provider sử dụng qua environment property `java.naming.ldap.derefAliases`.

### 2.1. Phân biệt giai đoạn tìm base và tìm subordinate

Giả sử:

```text
cn=staff,dc=example,dc=org
    alias -> ou=people,dc=example,dc=org

ou=people,dc=example,dc=org
    ├── uid=lan
    ├── uid=minh
    └── cn=old-employee
          alias -> uid=mai,ou=archive,dc=example,dc=org
```

Ứng dụng search với:

```text
base  = cn=staff,dc=example,dc=org
scope = SUBTREE
filter = (objectClass=inetOrgPerson)
```

Các chế độ có hành vi khái quát:

| Chế độ | Alias dùng làm base `cn=staff` | Alias nằm trong subtree `cn=old-employee` |
| --- | --- | --- |
| `never` | Giữ nguyên alias, không chuyển tới target | Không dereference |
| `searching` | Không dereference để tìm base | Dereference nếu alias nằm trong search scope |
| `finding` | Dereference để tìm base `ou=people` | Không dereference alias subordinate |
| `always` | Dereference để tìm base `ou=people` | Dereference alias subordinate |

Bảng mô tả chính sách ở mức LDAP SearchRequest. Việc entry cụ thể có xuất hiện trong kết quả còn phụ thuộc filter, scope, quyền, schema và cách server triển khai alias.

### 2.2. `searching` có thể mở rộng vùng search

Khi alias nằm trong search scope được dereference, target của alias trở thành một điểm bắt đầu search bổ sung. Với scope subtree, server có thể tiếp tục tìm trong subtree của target; với scope single-level, search áp dụng trên target theo quy tắc RFC nhưng không tự động mở rộng xuống toàn bộ subordinate của target.

Do đó, alias có thể khiến một search bắt đầu ở một nhánh nhưng đi tới dữ liệu nằm ở nhánh khác. Đây là hành vi hữu ích khi tổ chức lại DIT, nhưng phải được tính đến khi thiết kế quyền và phạm vi dữ liệu.

### 2.3. Server có thể trả entry trùng?

Nhiều alias có thể trỏ tới cùng một target. RFC 4511 nói server **SHOULD loại bỏ entry trùng** phát sinh do alias dereferencing trong search. Đây là khuyến nghị của giao thức, không nên dùng nó thay cho kiểm tra thực tế trên directory product.

Nếu ứng dụng cần tính duy nhất:

- Xác định khóa nhận diện theo DN đích hoặc identifier nghiệp vụ.
- Kiểm tra hành vi server khi nhiều alias cùng trỏ tới một entry.
- Không mặc định rằng số kết quả bằng số entry vật lý trong subtree.
- Kiểm thử kết quả khi alias trỏ chéo nhiều nhánh.

## 3. Cấu hình alias dereferencing trong JNDI

Với JDK LDAP provider mặc định, alias policy được cấu hình qua environment property:

```text
java.naming.ldap.derefAliases
```

Các giá trị:

| Giá trị | Mô tả |
| --- | --- |
| `always` | Dereference alias khi tìm base và khi search subordinate |
| `never` | Không dereference alias |
| `finding` | Chỉ dereference trong lúc phân giải tên/base |
| `searching` | Dereference alias sau khi đã định vị base |

**Điểm quan trọng:** Oracle JNDI LDAP provider ghi nhận mặc định của property này là `always` nếu không được thiết lập. Đây là mặc định của provider JDK được mô tả trong tài liệu Oracle; không suy rộng thành mặc định bắt buộc cho mọi LDAP client hoặc mọi server.

### 3.1. Cấu hình qua InitialDirContext

Ví dụ JNDI trực tiếp:

```java
import java.util.Hashtable;
import javax.naming.Context;
import javax.naming.directory.InitialDirContext;

Hashtable<String, Object> environment = new Hashtable<>();
environment.put(
        Context.INITIAL_CONTEXT_FACTORY,
        "com.sun.jndi.ldap.LdapCtxFactory");
environment.put(
        Context.PROVIDER_URL,
        "ldaps://ldap.example.org:636");
environment.put(
        Context.SECURITY_AUTHENTICATION,
        "simple");
environment.put(
        Context.SECURITY_PRINCIPAL,
        "uid=app-reader,ou=services,dc=example,dc=org");
environment.put(
        Context.SECURITY_CREDENTIALS,
        passwordFromSecretStore);
environment.put(
        "java.naming.ldap.derefAliases",
        "never");

InitialDirContext context = new InitialDirContext(environment);
```

Ở ví dụ này:

- `never` yêu cầu JDK LDAP provider không dereference alias khi đọc.
- Alias entry được xử lý như entry mang tên alias theo quy tắc server.
- Property được cung cấp khi tạo initial context.

Không ghi mật khẩu thật trong source code hoặc log; ví dụ dùng biến lấy từ secret store.

### 3.2. Cấu hình qua Spring LDAP ContextSource

Spring LDAP cho phép truyền JNDI environment properties bằng `AbstractContextSource.setBaseEnvironmentProperties(...)`:

```java
import java.util.Map;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ldap.core.support.LdapContextSource;

@Configuration(proxyBeanMethods = false)
public class DirectoryConfiguration {

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
        source.setBaseEnvironmentProperties(Map.of(
                "java.naming.ldap.derefAliases", "never"));
        source.setReferral("ignore");
        return source;
    }

}
```

Ví dụ dùng `never` để ứng dụng có hành vi đọc directory dễ dự đoán hơn khi alias không phải một phần của hợp đồng dữ liệu. Nếu nghiệp vụ cần alias, chọn `finding`, `searching` hoặc `always` có chủ đích và kiểm thử trên đúng server.

`setReferral("ignore")` ở ví dụ trên là cấu hình referral, **không phải** alias dereferencing. Hai policy độc lập; phần 9 sẽ giải thích referral.

### 3.3. Property có hiệu lực khi tạo Context

JNDI LDAP provider dùng `java.naming.ldap.derefAliases` khi tạo context. Oracle lưu ý việc thay property qua `Context.addToEnvironment(...)` hoặc `removeFromEnvironment(...)` sau khi context đã tạo không làm thay đổi hành vi của context đó.

Vì vậy:

- Cấu hình property trước khi tạo context.
- Với Spring, cấu hình trên ContextSource trước khi ứng dụng sử dụng context.
- Nếu đổi alias policy, tạo context mới để xác minh hành vi mới.
- Không thay environment property trên context đang được chia sẻ trong pool rồi kỳ vọng các request khác nhau có policy riêng.

### 3.4. Chính sách phụ thuộc provider

`java.naming.ldap.derefAliases` là property của JDK/Sun LDAP provider. Nếu ứng dụng dùng provider JNDI khác hoặc LDAP SDK khác, cần kiểm tra tài liệu provider đó. Đừng cho rằng mọi thư viện đều hiểu cùng tên property hoặc cùng giá trị mặc định.

## 4. SearchControls.setDerefLinkFlag không điều khiển LDAP alias

Một nhầm lẫn phổ biến là gọi:

```java
SearchControls controls = new SearchControls();
controls.setDerefLinkFlag(true);
```

rồi nghĩ rằng đã bật LDAP alias dereferencing.

Điều đó **không đúng**. `SearchControls.setDerefLinkFlag(...)` là cờ dereference link của JNDI naming API; Oracle ghi rõ cờ này **không liên quan** đến alias dereferencing của LDAP.

Hai cơ chế khác nhau:

| Cơ chế | Cấu hình | Tác dụng |
| --- | --- | --- |
| LDAP alias dereferencing | `java.naming.ldap.derefAliases` | Điều khiển trường `SearchRequest.derefAliases` của LDAP |
| JNDI link dereferencing | `SearchControls.setDerefLinkFlag(...)` | Điều khiển xử lý link trong JNDI search API |
| LDAP referral handling | `java.naming.referral` / `ContextSource.setReferral(...)` | Điều khiển client xử lý referral URL |

Nếu ứng dụng chỉ đổi `SearchControls.setDerefLinkFlag(true)` mà không cấu hình alias policy, hành vi LDAP alias vẫn do environment/provider quyết định.

### 4.1. Ví dụ LdapTemplate search

```java
import javax.naming.directory.SearchControls;
import org.springframework.ldap.core.LdapTemplate;

public List<PersonSummary> findPeople(LdapTemplate ldapTemplate) {
    SearchControls controls = new SearchControls();
    controls.setSearchScope(SearchControls.SUBTREE_SCOPE);
    controls.setCountLimit(100);
    controls.setTimeLimit(1_000);
    controls.setReturningAttributes(
            new String[] {"uid", "cn", "mail"});

    return ldapTemplate.search(
            "ou=people",
            "(objectClass=inetOrgPerson)",
            controls,
            personSummaryMapper());
}
```

Trong ví dụ:

- `SearchControls` điều khiển scope, count limit, time limit và attribute trả về.
- Alias dereferencing được cấu hình ở ContextSource/JNDI environment.
- `LdapTemplate.search(...)` sử dụng ContextSource đã cấu hình để tạo context thực hiện search.

Nếu muốn quan sát alias entry như một entry riêng, cấu hình `never` trên ContextSource rồi tìm theo filter/base phù hợp. Không cố dùng cờ link trong SearchControls để thay đổi alias policy.

## 5. Ảnh hưởng đến lookup, search và thao tác ghi

Oracle mô tả `java.naming.ldap.derefAliases` ảnh hưởng tới các thao tác đọc directory của JNDI. Việc dereference alias chỉ áp dụng cho search; các thao tác update như add, modify và delete không dereference alias.

| Operation | Ảnh hưởng của alias policy |
| --- | --- |
| Search | Có; server xử lý theo `derefAliases` trong SearchRequest |
| Lookup/read | JDK LDAP provider áp dụng alias policy cho các thao tác đọc |
| Add | Không tự chuyển alias DN sang target DN |
| Modify | Không tự chuyển alias DN sang target DN |
| Delete | Không tự chuyển alias DN sang target DN |

Điều này đặc biệt quan trọng khi dùng Spring Data LDAP repository. Repository method không có một tham số alias policy riêng cho từng lần gọi; behavior của operation đọc phụ thuộc ContextSource/provider mà repository sử dụng. Đừng giả định một derived query method tự thay đổi dereference mode.

### 5.1. Đọc qua alias và ghi qua alias là hai chuyện khác nhau

Giả sử:

```text
cn=staff,dc=example,dc=org
    alias -> ou=people,dc=example,dc=org
```

Search qua `cn=staff` với `always` có thể đọc các entry trong `ou=people`. Nhưng nếu ứng dụng gọi Modify bằng DN `cn=staff,...`, provider không tự chuyển thao tác ghi sang target như thể alias là một đường dẫn ghi thông thường.

Khi cần sửa target, hãy dùng DN thật đã được xác minh của target. Khi cần sửa alias entry, thao tác phải nhắm tới chính DN alias và tuân theo schema/ACL của alias.

Không dựa vào việc “đọc qua alias thành công” để kết luận “ghi qua alias sẽ sửa entry đích”.

### 5.2. Alias và base DN của ContextSource

Spring LDAP thường cấu hình base DN trên ContextSource. DN được truyền vào LdapTemplate thường là DN tương đối với base này.

Ví dụ:

```text
ContextSource base:
dc=example,dc=org

LdapTemplate search base:
cn=staff

DN hiệu lực:
cn=staff,dc=example,dc=org
```

Nếu `cn=staff` là alias, policy dereference ảnh hưởng đến việc server định vị base object. Khi dùng `never` hoặc `searching`, alias tại base không được dereference theo định nghĩa RFC. Một search có thể thất bại hoặc trả kết quả khác so với khi dùng `finding`/`always`.

Khi gặp `NameNotFoundException` hoặc kết quả rỗng, kiểm tra:

- DN tương đối và base suffix có ghép đúng không?
- Alias có tồn tại và target DN có hợp lệ không?
- Alias policy có cho dereference tại giai đoạn tìm base không?
- Service account có quyền đọc target không?
- Directory server có hỗ trợ alias dereferencing không?

## 6. Chọn chính sách dereference theo nghiệp vụ

Không có một mode tối ưu cho mọi ứng dụng. Chọn dựa trên việc ứng dụng có chấp nhận tên alias như một phần của directory contract hay không.

| Policy | Khi phù hợp | Hạn chế cần biết |
| --- | --- | --- |
| `never` | Muốn chỉ đọc entry đúng DN; cần hành vi dễ dự đoán; alias không được phép mở rộng search | Alias base không tự phân giải; tên tương thích cũ không hoạt động như target |
| `searching` | Muốn alias bên trong subtree được mở rộng nhưng base phải là entry thật | Alias dùng làm base không được phân giải |
| `finding` | Muốn chấp nhận alias làm base DN nhưng không mở rộng alias nằm trong subtree | Alias subordinate không được phân giải |
| `always` | Ứng dụng chủ động dùng alias làm tên thay thế ở cả base và subordinate | Có thể mở rộng phạm vi search và tăng độ phức tạp kết quả |

### 6.1. Khuyến nghị cho ứng dụng nghiệp vụ

Nếu directory không sử dụng alias như một tính năng được thiết kế, hãy chọn policy tường minh và kiểm thử, thường là `never` để tránh việc một alias bất ngờ chuyển search sang nhánh khác.

Nếu tổ chức dùng alias để tương thích tên cũ:

- Chọn `finding` nếu chỉ cần alias ở base DN.
- Chọn `searching` nếu chỉ cần alias nằm trong phạm vi tìm subordinate.
- Chọn `always` nếu cả hai hành vi đều là yêu cầu.

Đừng bật `always` chỉ vì đó là mặc định của JDK provider. Hãy xác nhận tác động lên tenant, ACL, scope và dữ liệu được trả về.

### 6.2. Policy không thay thế ACL

Alias dereferencing không cấp quyền mới. Server vẫn áp dụng quyền truy cập đối với thao tác và dữ liệu đích theo policy của directory. Tuy vậy, alias có thể khiến ứng dụng yêu cầu dữ liệu ở một nhánh khác mà developer không dự kiến.

Vì thế:

- ACL phải giới hạn service account trên cả alias entry và target.
- Không để alias do người dùng không tin cậy tạo ra trỏ sang subtree nhạy cảm.
- Không cho client gửi DN tùy ý rồi dựa vào alias để định tuyến dữ liệu.
- Kiểm tra quyền theo đối tượng/tenant sau khi xác định target.

## 7. Rủi ro về phạm vi search, kết quả và hiệu năng

Alias dereferencing có thể làm search khác đáng kể so với việc chỉ đi qua cây DN ban đầu.

### 7.1. Mở rộng ngoài subtree dự kiến

Giả sử API chỉ cho phép tìm nhân viên trong:

```text
ou=public,dc=example,dc=org
```

Nhưng một alias nằm trong nhánh đó trỏ tới:

```text
ou=executives,dc=example,dc=org
```

Nếu policy cho dereference trong search, server có thể tìm thêm ở target. Ứng dụng có nguy cơ nhận kết quả từ nhánh ngoài dự kiến nếu ACL và filter cho phép.

Đối với multi-tenant:

- Không coi base DN do client gửi là ranh giới bảo mật.
- Ràng buộc tenant và base DN ở server-side.
- Không cho tenant quản lý alias trỏ sang tenant khác.
- Kiểm thử alias cross-subtree với đúng service account.

### 7.2. Vòng lặp alias

Ví dụ lỗi:

```text
cn=alias-a -> cn=alias-b
cn=alias-b -> cn=alias-a
```

RFC 4511 yêu cầu server phát hiện loop. Ứng dụng vẫn cần:

- Không tạo alias cycle trong công cụ quản trị.
- Theo dõi lỗi dereference/loop từ server.
- Đặt timeout và giới hạn tài nguyên cho search.
- Không retry liên tục một lỗi dữ liệu/schema cố định.

### 7.3. Kết quả trùng và thứ tự

Nhiều alias có thể trỏ cùng một entry. Server SHOULD loại duplicate entry trong search do dereferencing tạo ra, nhưng ứng dụng nên kiểm tra hành vi thực tế. Nếu cần danh sách duy nhất, hãy xác định khóa đích ổn định và có quy tắc loại trùng rõ ràng.

Alias dereferencing cũng có thể làm tập kết quả lớn hơn, khiến:

- Search mất nhiều thời gian hơn.
- Count limit bị chạm sớm hơn.
- Kết quả vượt giới hạn server.
- Phân trang hoặc đồng bộ dữ liệu khó dự đoán hơn.

Đặt scope, filter, count/time limit phù hợp. Không dùng alias như một cách gom toàn bộ DIT mà không đánh giá chi phí.

### 7.4. Filter được áp dụng lên đối tượng được dereference

Khi server dereference alias trong search, filter được áp dụng trong quá trình tìm kiếm target theo quy tắc LDAP. Alias entry và entry đích có thể có attribute khác nhau. Không giả định filter khớp trên alias thì cũng khớp trên target.

Nếu ứng dụng cần liệt kê alias entry, dùng policy `never` và filter phù hợp với alias object class/attribute. Nếu cần tìm đối tượng đích, dùng policy phù hợp và filter theo schema của target.

## 8. Alias trong thực tế: ví dụ truy vấn và kiểm thử

### 8.1. Dữ liệu LDIF mẫu

Entry đích:

```ldif
dn: ou=people,dc=example,dc=org
objectClass: top
objectClass: organizationalUnit
ou: people

dn: uid=lan,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: lan
cn: Nguyen Thi Lan
sn: Nguyen
mail: lan@example.org
```

Alias entry:

```ldif
dn: cn=staff,dc=example,dc=org
objectClass: top
objectClass: alias
objectClass: extensibleObject
cn: staff
aliasedObjectName: ou=people,dc=example,dc=org
```

Đây là LDIF minh họa theo schema alias chuẩn. Một số directory product có giới hạn riêng về việc tạo hoặc dereference alias; hãy xác minh khả năng hỗ trợ trước khi dùng trong production.

### 8.2. Search qua alias base

Giả sử base search là `cn=staff`:

```java
SearchControls controls = new SearchControls();
controls.setSearchScope(SearchControls.SUBTREE_SCOPE);
controls.setReturningAttributes(new String[] {"uid", "cn", "mail"});

List<PersonSummary> people = ldapTemplate.search(
        "cn=staff",
        "(objectClass=inetOrgPerson)",
        controls,
        personSummaryMapper());
```

Kết quả mong đợi:

- `finding` hoặc `always`: server có thể phân giải alias base tới `ou=people` rồi search.
- `never` hoặc `searching`: server không dereference alias base theo định nghĩa policy; kết quả có thể là lỗi base hoặc tập kết quả khác.

Đây là ví dụ phụ thuộc directory server. Hãy kiểm tra bằng integration test trên đúng sản phẩm, schema và quyền bind.

### 8.3. Search alias nằm trong subtree

Giả sử search base là `ou=directory,dc=example,dc=org` và một alias nằm bên dưới trỏ tới `ou=archive,dc=example,dc=org`.

Nếu scope là subtree:

- `searching` và `always` có thể mở rộng search tới target alias.
- `never` và `finding` không dereference alias subordinate.

Không dùng alias để trỏ sang nhánh khác nếu yêu cầu bảo mật chỉ cho phép search trong một subtree cố định.

### 8.4. Test từng policy thay vì chỉ test default

Integration test nên tạo context riêng cho từng mode:

```java
Map<String, Object> environment = Map.of(
        "java.naming.ldap.derefAliases", "finding");

LdapContextSource source = new LdapContextSource();
source.setUrl(ldapUrl);
source.setBase("dc=example,dc=org");
source.setBaseEnvironmentProperties(environment);
```

Tạo các test case với:

1. Alias được dùng làm base DN.
2. Alias nằm trong subordinate scope.
3. Alias trỏ tới target ngoài subtree.
4. Hai alias cùng trỏ tới một target.
5. Alias chain có nhiều bước.
6. Alias cycle.
7. Target không tồn tại hoặc account không có quyền đọc target.

Không dùng một test server không hỗ trợ alias rồi kết luận mọi LDAP server đều xử lý giống nhau. Kiểm tra feature support và hành vi của directory product đang triển khai.

## 9. Phân biệt alias với LDAP referral

Alias và referral đều giúp một tên dẫn tới dữ liệu khác, nhưng cơ chế hoạt động khác nhau.

| Tiêu chí | Alias | Referral |
| --- | --- | --- |
| Thông tin trỏ tới | DN trong `aliasedObjectName` | Một hoặc nhiều URL trong referral |
| Ai xử lý | LDAP server dereference trong search | Client nhận referral và quyết định xử lý |
| Có thể dẫn sang server khác? | Alias trỏ DN; việc phân giải diễn ra trong directory server xử lý alias | Có; URL có thể chỉ tới host/port/server khác |
| Điều khiển chính | `java.naming.ldap.derefAliases` | `java.naming.referral` hoặc `ContextSource.setReferral(...)` |
| Các mode | never/searching/finding/always | ignore/follow/throw |
| Rủi ro chính | Mở rộng phạm vi search, loop, duplicate | Theo URL ngoài dự kiến, credential delegation, partial results |

### 9.1. Referral là gì?

Referral cung cấp thông tin về một server hoặc dịch vụ khác có thể tiếp tục xử lý operation. Trong LDAP search, server có thể trả `SearchResultReference` khi cần client truy vấn thêm server khác để hoàn tất search.

Ví dụ referral entry có thể chứa URL:

```ldif
dn: ou=partners,dc=example,dc=org
objectClass: top
objectClass: referral
objectClass: extensibleObject
ou: partners
ref: ldap://partner-directory.example.net/ou=partners,dc=partner,dc=net
```

Ví dụ chỉ minh họa ý tưởng referral; schema/DIT content rule và khả năng tạo referral entry phụ thuộc directory server.

Khác với alias, referral được gửi về client. Client phải quyết định có theo URL đó hay không và dùng credential/TLS nào.

### 9.2. Chính sách referral trong JNDI

JNDI dùng property `java.naming.referral`, cũng là hằng `Context.REFERRAL`:

| Giá trị | Hành vi |
| --- | --- |
| `ignore` | Không tự động follow referral; tùy server/provider có thể gặp PartialResultException nếu kết quả chưa đầy đủ |
| `follow` | LDAP provider tự động follow referral |
| `throw` | Ném ReferralException để ứng dụng xử lý thủ công |

JDK LDAP provider mặc định `ignore` nếu không cấu hình. Spring LDAP cung cấp `AbstractContextSource.setReferral(String)` để chọn chiến lược.

Ví dụ:

```java
LdapContextSource source = new LdapContextSource();
source.setUrl("ldaps://ldap.example.org:636");
source.setBase("dc=example,dc=org");
source.setReferral("follow");
```

Không bật `follow` chỉ để hết lỗi partial result. Referral có thể trỏ tới host khác, yêu cầu TLS trust, DNS, port, credential và ACL khác. Phải xác định rõ endpoint được phép và cách xác thực khi follow.

### 9.3. Referral có thể làm lộ credential

Khi client tự động follow referral, cần đánh giá:

- Referral URL có nằm trong allowlist hostname/domain không?
- Có yêu cầu TLS và hostname verification không?
- Client có gửi credential tới server được referral chỉ định không?
- Credential có được phép dùng ở directory đích không?
- Có giới hạn số lần/hop referral để tránh vòng lặp không?
- Referral có dẫn tới mạng nội bộ hoặc endpoint không đáng tin cậy không?

Không follow URL referral tùy ý từ directory không tin cậy. Một referral có thể là điểm điều hướng kết nối tới host mà ứng dụng không định truy cập.

### 9.4. Spring LDAP và PartialResultException

Tài liệu `LdapTemplate` lưu ý một số Active Directory server không tự xử lý referral theo cách mà JNDI provider mong đợi; search có thể phát sinh `PartialResultException`.

Spring LDAP có thuộc tính:

```java
ldapTemplate.setIgnorePartialResultException(true);
```

Khi bật, `LdapTemplate` bỏ qua PartialResultException để search trả về bình thường. **Điều này có thể làm kết quả không đầy đủ và che mất tín hiệu rằng còn referral/chưa đọc hết dữ liệu.** Tài liệu Spring LDAP cũng lưu ý không có cách đơn giản để nhận thông báo từng PartialResultException đã bị bỏ qua, ngoài log.

Chỉ bật workaround này nếu nghiệp vụ chấp nhận kết quả một phần và đã hiểu chính xác referral nào bị bỏ qua. Không bật để biến một search cần đầy đủ dữ liệu thành vẻ ngoài thành công.

### 9.5. Referral và alias có thể cùng xuất hiện

Một search có thể gặp alias ở một nhánh và referral ở nhánh khác. Khi đó:

- Alias policy điều khiển server phân giải DN alias.
- Referral policy điều khiển client có follow URL server trả về không.
- Cả hai có thể ảnh hưởng tập kết quả cuối cùng.
- Một kết quả thành công ở tầng HTTP không chứng minh search đã thu thập đủ mọi nhánh.

Hãy kiểm tra riêng từng policy và log trạng thái kết quả đầy đủ/partial.

## 10. Cấu hình Spring LDAP tách biệt alias và referral

Một cấu hình rõ ràng nên đặt hai policy riêng biệt:

```java
import java.util.Map;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ldap.core.support.LdapContextSource;

@Configuration(proxyBeanMethods = false)
public class DirectoryContextConfiguration {

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

        // Alias dereferencing do JDK LDAP provider điều khiển.
        source.setBaseEnvironmentProperties(Map.of(
                "java.naming.ldap.derefAliases", "never"));

        // Referral handling do JNDI/Spring ContextSource điều khiển.
        source.setReferral("ignore");
        return source;
    }
}
```

Đây là cấu hình minh họa cho JDK LDAP provider. Nếu dùng provider khác, xác minh property alias tương ứng. `never` và `ignore` là hai lựa chọn độc lập:

- `never`: không dereference LDAP alias.
- `ignore`: không tự động follow LDAP referral.

Nếu ứng dụng cần alias tương thích tên cũ, thay `never` bằng mode đã được lựa chọn theo base/search semantics. Nếu ứng dụng cần follow referral, đánh giá hostname, TLS và credential trước khi đặt `follow`.

## 11. Bảo mật và kiểm soát quyền khi dùng alias/referral

Alias/referral có thể làm một search vượt khỏi hình dung ban đầu của developer. Các biện pháp sau giúp giữ phạm vi truy cập rõ ràng:

1. **Ràng buộc base DN ở server:** không nhận base DN tùy ý từ client.
2. **Least privilege:** service account chỉ đọc những subtree/attribute cần thiết, kể cả target alias.
3. **Allowlist referral host:** chỉ follow URL đã được quản trị viên phê duyệt.
4. **TLS:** xác minh certificate và hostname cho mọi endpoint referral.
5. **Giới hạn alias chain/referral hops:** tránh vòng lặp hoặc truy cập không giới hạn.
6. **Giới hạn search:** dùng scope/filter/count/time limit phù hợp.
7. **Kiểm tra kết quả partial:** không coi một phần dữ liệu là đầy đủ.
8. **Quan sát:** ghi nhận policy, logical directory, operation và trạng thái; không log credential hoặc raw DN nhạy cảm.

### 11.1. Alias không phải cơ chế ủy quyền

Không dùng alias để thay thế phân quyền. Nếu người dùng được phép tra cứu trong OU A, không có nghĩa alias từ OU A sang OU B tự động được phép. Authorization phải dựa trên principal, tenant, target object và policy của ứng dụng.

### 11.2. Không để client điều khiển alias policy

Tránh API kiểu:

```text
GET /api/people?derefAliases=always
```

Nếu client có thể chọn policy, họ có thể mở rộng search sang alias target mà ứng dụng không dự kiến. Alias policy là cấu hình server-side theo directory/use case, không phải tham số tự do của request.

### 11.3. Không follow referral theo URL tùy ý

Referral là dữ liệu do directory trả về. Nếu directory hoặc một referral entry bị thay đổi bởi principal không đáng tin, ứng dụng có thể bị điều hướng tới endpoint ngoài dự kiến. Dùng allowlist, kiểm tra TLS và kiểm soát credential forwarding trước khi follow.

## 12. Kiểm thử alias và referral

Kiểm thử phải xác minh **entry nào được trả về**, không chỉ xác minh ContextSource khởi tạo thành công.

### 12.1. Ma trận alias dereference

Chuẩn bị:

- Một target entry.
- Một alias trỏ tới target làm base.
- Một alias nằm trong subordinate search scope.
- Một alias trỏ tới alias khác.
- Hai alias trỏ cùng target.
- Một alias cycle trong môi trường test riêng.

Chạy cùng filter/scope với từng policy:

| Test | Base alias | Alias subordinate | Kết quả cần quan sát |
| --- | --- | --- | --- |
| `never` | Không dereference | Không dereference | Alias entry không được thay bằng target |
| `searching` | Không dereference | Dereference | Alias base không được tự phân giải |
| `finding` | Dereference | Không dereference | Base target được tìm thấy |
| `always` | Dereference | Dereference | Cả hai vị trí alias được xử lý |

Kết quả chi tiết có thể khác theo directory product và schema. Ghi lại LDAP result code, JNDI exception, số entry và DN được trả về.

### 12.2. Kiểm thử alias loop

Tạo alias cycle trong directory test, không dùng dữ liệu production. Xác minh server phát hiện loop và trả lỗi phù hợp thay vì giữ operation vô hạn. Ghi nhận timeout/exception và đảm bảo ứng dụng không retry vô hạn lỗi dữ liệu này.

### 12.3. Kiểm thử referral riêng

Tạo referral test trỏ tới server test thứ hai:

- `ignore`: xác minh ứng dụng không tự follow và hiểu rõ partial result behavior.
- `follow`: xác minh client kết nối tới đúng endpoint allowlist, TLS và credential đúng.
- `throw`: nếu dùng JNDI trực tiếp, xác minh ReferralException được xử lý; với LdapTemplate cần lưu ý abstraction không cung cấp quy trình manual referral đầy đủ.

Đừng dùng alias test để thay cho referral test; hai cơ chế khác nhau.

### 12.4. Kiểm thử PartialResultException

Với server trả continuation reference:

- Xác minh search có hoàn tất toàn bộ nhánh hay chỉ một phần.
- Kiểm tra `ignorePartialResultException=false` để nhận diện lỗi.
- Nếu bật true, xác minh nghiệp vụ chấp nhận tập kết quả một phần và có telemetry thích hợp.
- Không đánh dấu đồng bộ hoàn tất nếu referral bị bỏ qua mà chưa xử lý.

### 12.5. Kiểm thử quyền

Dùng đúng service account giống production:

- Có quyền đọc target alias.
- Không có quyền đọc subtree nhạy cảm ngoài phạm vi.
- Alias trỏ ra ngoài subtree không làm API lộ dữ liệu.
- Referral tới host ngoài allowlist bị từ chối.
- Referral target dùng certificate sai bị từ chối.
- Credential không bị gửi tới host ngoài dự kiến.

## 13. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Search qua alias base không thấy dữ liệu | Policy là `never` hoặc `searching` | Kiểm tra có cần `finding`/`always` không |
| Search subordinate không mở rộng alias | Policy là `never` hoặc `finding` | Dùng `searching`/`always` nếu nghiệp vụ yêu cầu |
| Bật `SearchControls.setDerefLinkFlag(true)` nhưng alias vẫn không đổi | Cờ này không liên quan LDAP alias | Dùng JNDI `java.naming.ldap.derefAliases` |
| Mặc định JDK dereference quá rộng | Property không đặt, JDK provider mặc định `always` | Đặt mode tường minh |
| Search trả thêm entry từ nhánh khác | Alias target nằm ngoài subtree dự kiến | Kiểm tra policy, target DN, ACL và base DN |
| Kết quả có duplicate | Nhiều alias cùng trỏ target; server behavior khác nhau | Kiểm thử, deduplicate theo khóa đích nếu cần |
| Alias cycle gây lỗi | Dữ liệu alias tạo vòng | Sửa dữ liệu, ghi nhận lỗi, không retry vô hạn |
| Modify qua alias không sửa target | Update operation không dereference alias | Dùng DN thật của target |
| Referral không được theo | Policy `ignore` hoặc server/provider trả partial result | Xác minh referral policy và SearchResultReference |
| Follow referral bị TLS/auth lỗi | Referral endpoint có trust/credential khác | Allowlist host, cấu hình TLS và credential hợp lệ |
| Active Directory search ném PartialResultException | Server/provider xử lý referral không tương thích | Chỉ cân nhắc workaround sau khi đánh giá dữ liệu thiếu |
| Bật ignorePartialResultException làm search “thành công” | Tín hiệu partial result bị bỏ qua | Đảm bảo nghiệp vụ chấp nhận incomplete results |
| Đổi property nhưng context vẫn hành xử cũ | Environment đã được dùng khi context khởi tạo | Tạo context mới và kiểm thử lại |
| Alias policy khác nhau giữa môi trường | Provider/server hoặc property mặc định khác nhau | Cấu hình tường minh và test từng môi trường |

## 14. Bài tập tự luyện

**Câu 1.** Alias entry lưu DN target ở attribute nào? Alias object class có đặc điểm cấu trúc gì?

*Gợi ý:* `aliasedObjectName`; alias là structural object class và alias entry là leaf, không có subordinate.

**Câu 2.** Khác nhau giữa `searching` và `finding` là gì?

*Gợi ý:* Searching dereference alias trong subordinate search scope; finding dereference alias khi định vị base object.

**Câu 3.** JDK LDAP provider mặc định dereference alias theo mode nào nếu không cấu hình property?

*Gợi ý:* Oracle JNDI LDAP provider mô tả mặc định `always`; đừng suy rộng mặc định này cho mọi provider.

**Câu 4.** Vì sao `SearchControls.setDerefLinkFlag(true)` không thay thế `java.naming.ldap.derefAliases=always`?

*Gợi ý:* Một cờ xử lý link của JNDI; property kia điều khiển trường alias dereference trong LDAP SearchRequest.

**Câu 5.** Có nên cho phép alias trong OU public trỏ sang OU payroll không?

*Gợi ý:* Không nếu policy/authorization không cho phép. Alias có thể mở rộng search sang target ngoài subtree dự kiến.

**Câu 6.** Alias có tự động được dereference khi gọi Modify/Delete không?

*Gợi ý:* Không. Alias dereferencing chỉ áp dụng cho thao tác đọc/search theo JNDI provider; update operation không tự chuyển sang target.

**Câu 7.** Referral khác alias ở điểm quan trọng nhất nào?

*Gợi ý:* Alias chứa DN và được server dereference; referral chứa URL và client quyết định follow.

**Câu 8.** Vì sao bật `ignorePartialResultException=true` có thể nguy hiểm với job đồng bộ?

*Gợi ý:* Job có thể đánh dấu hoàn tất dù một số referral/nhánh chưa được đọc; dữ liệu đồng bộ bị thiếu.

**Câu 9.** Nếu alias policy đổi nhưng Context đã được tạo, thay environment property có chắc tác dụng không?

*Gợi ý:* Oracle JNDI provider dùng property khi tạo context; cần tạo context mới để áp dụng.

**Câu 10.** Cần kiểm thử những gì khi bật referral follow?

*Gợi ý:* Host allowlist, TLS/hostname, credential forwarding, referral limit/hop, partial result và quyền ở directory đích.

## 15. Ghi nhớ

- **Alias entry** thuộc object class `alias` và lưu DN đích trong `aliasedObjectName`; alias là leaf entry.
- LDAP SearchRequest có bốn mode: `neverDerefAliases`, `derefInSearching`, `derefFindingBaseObj` và `derefAlways`.
- Với JDK LDAP provider, property là **`java.naming.ldap.derefAliases`**; giá trị chuỗi gồm `never`, `searching`, `finding`, `always`. Oracle mô tả mặc định provider là `always`.
- `searching` áp dụng cho alias trong subordinate search scope; `finding` áp dụng cho alias ở base object.
- `SearchControls.setDerefLinkFlag(...)` **không liên quan** đến LDAP alias dereferencing.
- Alias policy ảnh hưởng đọc/search; add/modify/delete không tự dereference alias tới target.
- Alias có thể mở rộng search ra ngoài subtree dự kiến, tạo kết quả trùng hoặc loop; server MUST phát hiện alias loop.
- **Alias khác referral:** alias trỏ DN và server xử lý; referral chứa URL và client quyết định follow.
- Referral policy dùng `ignore/follow/throw` qua JNDI `Context.REFERRAL` hoặc Spring `ContextSource.setReferral(...)`.
- Không bật follow referral nếu chưa kiểm tra hostname, TLS, credential delegation, allowlist và giới hạn hop.
- `ignorePartialResultException=true` có thể che kết quả search không đầy đủ; chỉ dùng khi nghiệp vụ chấp nhận partial result.
- Kiểm thử trên đúng directory product, provider, schema, service account và môi trường triển khai.

**Tài liệu tham khảo chính thức:**

- [RFC 4511 — LDAP: The Protocol, mục 4.5.1.3](https://www.rfc-editor.org/rfc/rfc4511): bốn giá trị SearchRequest.derefAliases, semantics tìm base/subordinate và phát hiện alias loop.
- [RFC 4512 — LDAP Directory Information Models, mục 2.6](https://www.rfc-editor.org/rfc/rfc4512): alias object class, aliasedObjectName, alias entry là leaf.
- [Oracle JNDI Tutorial — Dereferencing Aliases](https://docs.oracle.com/javase/jndi/tutorial/ldap/misc/aliases.html): property java.naming.ldap.derefAliases, bốn mode, mặc định JDK provider và khác biệt với SearchControls link flag.
- [Oracle JNDI/LDAP Service Provider — Guidelines](https://docs.oracle.com/javase/8/docs/technotes/guides/jndi/jndi-ldap-gl.html): alias property và referral environment.
- [Java API — SearchControls](https://docs.oracle.com/en/java/javase/24/docs/api/java.naming/javax/naming/directory/SearchControls.html): dereference link flag và search controls.
- [Spring LDAP API — AbstractContextSource](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/support/AbstractContextSource.html): setBaseEnvironmentProperties và setReferral.
- [Spring LDAP API — LdapTemplate](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/LdapTemplate.html): search, DirContextProcessor và xử lý PartialResultException.
- [Oracle JNDI Tutorial — Referrals](https://docs.oracle.com/javase/jndi/tutorial/ldap/referral/jndi.html): ignore/follow/throw và xử lý referral.
- [Oracle JNDI Tutorial — Referrals Overview](https://docs.oracle.com/javase/jndi/tutorial/ldap/referral/overview.html): so sánh alias và referral; DN so với URL.
- [RFC 3296 — Named Subordinate References in LDAP Directories](https://www.rfc-editor.org/rfc/rfc3296): ManageDsaIT và referral entries.
