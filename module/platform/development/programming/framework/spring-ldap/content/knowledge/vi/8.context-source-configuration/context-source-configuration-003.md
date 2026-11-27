# Anonymous bind và điều kiện được phép sử dụng

## Mục tiêu bài học

Trong module **SPRING_LDAP**, ứng dụng Java truy cập dịch vụ thư mục qua `ContextSource`, `LdapTemplate`, `LdapClient` hoặc LDAP ODM. Một quyết định quan trọng ngay tại bước cấu hình kết nối là: **ứng dụng có được truy vấn LDAP khi không cung cấp danh tính và mật khẩu hay không?**

**Anonymous bind** cho phép client thiết lập trạng thái truy cập ẩn danh đối với LDAP server. Đây là một cơ chế hợp lệ của giao thức, nhưng **không đồng nghĩa được tự do đọc toàn bộ directory**. Máy chủ quyết định những entry, attribute và thao tác mà danh tính ẩn danh được phép sử dụng theo chính sách truy cập. Dùng nhầm anonymous bind trong chức năng xác thực, đọc dữ liệu cá nhân hoặc cập nhật entry có thể tạo ra sai sót nghiêm trọng.

Sau bài học, bạn có thể:

1. Giải thích **anonymous bind**, **unauthenticated simple bind** và **name/password simple bind**, cùng khác biệt quan trọng giữa chúng.
2. Xác định trường hợp cho phép anonymous read và điều kiện bắt buộc về dữ liệu, ACL, phạm vi truy vấn, TLS và giới hạn tải.
3. Cấu hình `LdapContextSource.setAnonymousReadOnly(true)` trong Spring LDAP và hiểu nó ảnh hưởng thế nào đến read-only context.
4. Dùng `ldapwhoami`, `ldapsearch` và `LdapTemplate` để kiểm chứng thực tế quyền của một kết nối ẩn danh.
5. Phân biệt kết quả rỗng, từ chối quyền, lỗi bind, lỗi kết nối và lỗi TLS; kiểm thử để tránh biến lỗi thành kết quả hợp lệ.
6. Chọn tài khoản dịch vụ hoặc cơ chế xác thực khác khi yêu cầu nghiệp vụ không phù hợp với truy cập ẩn danh.

## 1. Anonymous bind là gì?

LDAP (*Lightweight Directory Access Protocol*) định nghĩa thao tác **Bind** để thiết lập trạng thái xác thực/ủy quyền của một kết nối. Trong simple Bind, chuẩn RFC 4513 phân biệt ba trường hợp:

| Cơ chế | Tên (DN) gửi khi bind | Mật khẩu gửi khi bind | Trạng thái xác thực |
| --- | --- | --- | --- |
| **Anonymous simple bind** | Rỗng | Rỗng | Ẩn danh |
| **Unauthenticated simple bind** | **Không rỗng** | **Rỗng** | Vẫn là ẩn danh, không chứng minh DN đã được xác thực |
| **Name/password simple bind** | DN không rỗng | Mật khẩu không rỗng | Có thể xác thực danh tính khi server kiểm tra credential thành công |

Ví dụ về mặt giao thức:

```text
Anonymous:
Bind name = ""
Bind password = ""
=> Kết nối ở trạng thái truy cập ẩn danh

Unauthenticated simple bind:
Bind name = "uid=lan,ou=People,dc=example,dc=org"
Bind password = ""
=> Vẫn ở trạng thái ẩn danh nếu server chấp nhận

Name/password simple bind:
Bind name = "uid=lan,ou=People,dc=example,dc=org"
Bind password = "<mật khẩu thực>"
=> Server kiểm tra credential rồi thiết lập quyền tương ứng
```

Điểm dễ nhầm nhất: **một DN không rỗng kết hợp mật khẩu rỗng không phải là đăng nhập thành công với tư cách DN đó**. Với *unauthenticated simple bind*, server có thể phản hồi thành công mà kết nối vẫn mang quyền ẩn danh. RFC 4513 khuyến nghị server mặc định từ chối cơ chế này do rủi ro ứng dụng tưởng rằng đã xác thực người dùng.

Vì vậy, giao diện đăng nhập và luồng xác thực phải **từ chối mật khẩu rỗng trước khi yêu cầu LDAP Bind**. Không dựa duy nhất vào mã trả về thành công của một Bind không có mật khẩu để cấp quyền.

### 1.1. Bind, search và authorization là những việc khác nhau

- **Bind:** thiết lập trạng thái xác thực/ủy quyền của kết nối LDAP.
- **Search:** truy vấn những entry phù hợp một base DN, scope và filter.
- **Access control (ACL):** quy định danh tính hiện tại được xem hoặc thay đổi những entry/attribute nào.
- **Authorization trong ứng dụng:** quyết định người dùng cuối được gọi chức năng nào của ứng dụng.

Một kết nối có thể được bind ẩn danh mà không được phép đọc nhánh `ou=People`. Một kết nối ẩn danh cũng có thể được phép đọc một vài attribute công khai ở nhánh riêng, ví dụ danh sách dịch vụ hoặc danh bạ được chủ sở hữu cho phép công khai.

**Không được suy ra "bind thành công" nghĩa là "search thành công", hoặc "search có kết quả" nghĩa là "người dùng đã đăng nhập".**

## 2. Trường hợp nào thực sự được phép dùng anonymous bind?

Một số directory server được cấu hình cho phép **đọc công khai có giới hạn**, chẳng hạn thông tin mô tả dịch vụ, dữ liệu thử nghiệm, hoặc một phần cây thư mục vốn được thiết kế để công bố rộng rãi.

Các tình huống có thể phù hợp:

| Tình huống | Anonymous bind có thể dùng? | Điều kiện |
| --- | --- | --- |
| Đọc thông tin khả năng của máy chủ tại **Root DSE** | **Có thể** | Server cho phép; chỉ đọc attribute cần thiết; không mặc định mọi triển khai đều công khai |
| Tra cứu danh bạ công khai của tổ chức | **Có thể** | Có quyết định công bố dữ liệu; ACL giới hạn đúng entry/attribute công khai |
| Đọc cấu hình dịch vụ công khai, ít thay đổi | **Có thể** | Dữ liệu không bí mật; phạm vi và lượng yêu cầu được giới hạn |
| Bài thực hành với LDAP server riêng | **Có thể** | Fixture giả lập, ACL được thiết lập và thử nghiệm có kiểm soát |
| Xác thực người dùng bằng mật khẩu | **Không** | Cần xác minh credential/SSO hợp lệ, tuyệt đối không coi anonymous bind là xác thực |
| Đọc hồ sơ cá nhân, số điện thoại riêng, nhóm nhạy cảm | **Thông thường không** | Dùng danh tính có quyền phù hợp và chính sách bảo vệ dữ liệu |
| Tạo, sửa, đổi DN, xóa entry | **Không nên** | Dùng danh tính quản trị được cấp quyền tối thiểu; server phải từ chối anonymous write |
| Đồng bộ dữ liệu nội bộ có kiểm soát quyền | **Không nên** | Dùng service identity và phân quyền theo tác vụ |

Trong thực tế, lựa chọn anonymous không chỉ là cấu hình client. Cần trả lời **tất cả** các câu hỏi sau:

1. **Dữ liệu có được phép công bố cho người không định danh không?** Việc nằm trong LDAP không có nghĩa nó là thông tin công khai.
2. **Máy chủ có bật cơ chế này không?** Nhiều hệ thống giới hạn hoặc tắt anonymous search.
3. **ACL có giới hạn được đúng nhánh và attribute công khai?** Không chỉ ẩn ở giao diện mà phải giới hạn tại server.
4. **Có cần xác định ai đang truy cập không?** Nếu cần audit theo người dùng, hạn mức riêng hoặc chính sách quyền theo người, anonymous thường không đủ.
5. **Có giới hạn số entry, thời gian, tốc độ và độ phức tạp truy vấn không?** Dữ liệu công khai vẫn có thể bị quét hoặc lạm dụng tài nguyên.
6. **Đường truyền và server identity được bảo vệ chưa?** Dùng LDAPS hoặc StartTLS đã xác minh chứng chỉ khi môi trường yêu cầu bảo vệ tính bí mật và toàn vẹn.

Nếu một điều kiện không được đáp ứng, chọn **service account đọc hạn chế** hoặc một cơ chế nhận dạng thích hợp thường an toàn và dễ quản trị hơn.

### 2.1. Root DSE là trường hợp đặc biệt

**Root DSE** (*Root Directory Specific Entry*) là entry đặc biệt ở **base DN rỗng** (`""`), thường cung cấp thông tin về khả năng máy chủ như `namingContexts`, `supportedLDAPVersion` hoặc các control/extension được hỗ trợ.

Một số server cho phép truy vấn Root DSE ở trạng thái ẩn danh để client khám phá khả năng kết nối. Tuy nhiên:

- Không phải mọi server đều công bố cùng attribute.
- Quyền đọc Root DSE có thể khác quyền đọc dữ liệu người dùng.
- Đọc thành công Root DSE **không chứng minh** có quyền duyệt nhánh `ou=People`.
- Đối với API có `ContextSource.base`, hãy kiểm tra cách biểu diễn tên rỗng/Root DSE theo phiên bản và cơ chế truy vấn; thao tác từ context đã đặt base có thể cần xử lý riêng.

## 3. Thiết kế quyền: ví dụ nhánh công khai và nhánh nội bộ

Giả sử DIT được thiết kế:

```text
dc=example,dc=org
├── ou=PublicDirectory
│   ├── uid=contact01
│   └── uid=contact02
├── ou=People
│   ├── uid=lan
│   └── uid=mai
└── ou=Services
    └── cn=svc-reader
```

Tổ chức cho phép công bố tên và địa chỉ email công việc của `ou=PublicDirectory` nhưng giữ các thuộc tính khác thuộc nhánh nhân sự ở chế độ nội bộ.

Ma trận quyền **mong muốn**:

| Hành động | Anonymous | Service account chỉ đọc | Admin có quyền ghi |
| --- | --- | --- | --- |
| Đọc `cn`, `mail` của `ou=PublicDirectory` | Cho phép nếu chính sách công bố | Tùy ACL | Tùy ACL |
| Đọc `telephoneNumber` hoặc dữ liệu riêng tư | Từ chối | Chỉ khi được cấp quyền riêng | Theo nhiệm vụ |
| Duyệt toàn bộ `ou=People` | Từ chối | Chỉ nhánh/attribute cần thiết | Theo nhiệm vụ |
| Thêm, sửa, xóa entry | Từ chối | Từ chối | Chỉ với phạm vi được cấp |
| Bind với danh tính người dùng và kiểm tra mật khẩu | Không được thay thế bằng anonymous | Có thể dùng search hỗ trợ tìm DN | Phải thực hiện quy trình xác thực phù hợp |

Đây là **ma trận chính sách mục tiêu**, không phải behavior tự động của LDAP. Cách viết ACL khác nhau giữa OpenLDAP, Active Directory và các sản phẩm khác. **Cấu hình `setAnonymousReadOnly(true)` ở client không tự tạo hoặc thay đổi ACL server.**

Một dữ liệu tưởng như công khai vẫn có thể có ý nghĩa nhạy cảm khi kết hợp: danh sách nhóm, email nội bộ, vị trí tổ chức hay ảnh hồ sơ có thể giúp suy ra cơ cấu nhân sự. Cần duyệt tập dữ liệu công bố trước khi thiết kế anonymous access.

## 4. Cấu hình anonymous read-only với Spring LDAP

Spring LDAP cung cấp **`org.springframework.ldap.core.support.LdapContextSource`**, kế thừa từ `AbstractContextSource`. Theo tài liệu Spring LDAP, mặc định `ContextSource` tạo context **được xác thực** cho cả thao tác đọc và ghi. Khi gọi:

```java
source.setAnonymousReadOnly(true);
```

thì **read-only context** được tạo bằng môi trường ẩn danh. Điều này không biến mọi thao tác LDAP thành anonymous, và cũng không bảo đảm các thao tác thực sự chỉ được phép đọc nếu ACL server cấu hình sai.

### 4.1. Cấu hình riêng một `ContextSource` cho dữ liệu công khai

Ví dụ dưới đây dùng Spring Java Configuration. Giả sử máy chủ thử nghiệm cho phép anonymous search nhánh `ou=PublicDirectory` và JVM có truststore tin cậy chứng chỉ LDAPS:

```java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ldap.core.ContextSource;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.core.support.LdapContextSource;

@Configuration
class PublicLdapConfiguration {

    @Bean("publicContextSource")
    LdapContextSource publicContextSource() {
        LdapContextSource source = new LdapContextSource();
        source.setUrl("ldaps://ldap.example.org:636");
        source.setBase("dc=example,dc=org");
        source.setAnonymousReadOnly(true);
        // Không cấu hình userDn/password cho context chỉ dùng đọc ẩn danh.
        return source;
    }

    @Bean("publicLdapTemplate")
    LdapTemplate publicLdapTemplate(
            @Qualifier("publicContextSource") ContextSource source) {
        return new LdapTemplate(source);
    }
}
```

**Cách dùng mong muốn:** bean `publicLdapTemplate` chỉ dành cho chức năng search/lookup dữ liệu công khai. Việc không khai báo `userDn` và `password` cùng `anonymousReadOnly=true` phải được xác nhận trên server đích. Không chia sẻ bean này cho luồng xác thực người dùng hoặc thao tác ghi.

Khi `LdapContextSource` được quản lý như Spring bean, framework gọi callback khởi tạo sau khi đặt thuộc tính. Nếu tự tạo instance ngoài Spring container, cần gọi `afterPropertiesSet()` trước khi sử dụng theo hợp đồng của lớp.

### 4.2. Search chỉ trong nhánh công khai

```java
import static org.springframework.ldap.query.LdapQueryBuilder.query;

import java.util.List;
import javax.naming.NamingException;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.SearchScope;
import org.springframework.stereotype.Service;

@Service
class PublicDirectoryService {
    private final LdapTemplate ldap;

    PublicDirectoryService(
            @Qualifier("publicLdapTemplate") LdapTemplate ldap) {
        this.ldap = ldap;
    }

    List<String> findPublicDisplayNames(String uid) {
        return ldap.search(
                query().base("ou=PublicDirectory")
                        .searchScope(SearchScope.SUBTREE)
                        .attributes("cn")
                        .where("objectClass").is("inetOrgPerson")
                        .and("uid").is(uid),
                (Attributes attrs) -> firstString(attrs, "cn"));
    }

    private static String firstString(Attributes attrs, String name)
            throws NamingException {
        Attribute attribute = attrs.get(name);
        if (attribute == null || attribute.size() == 0) {
            return null;
        }
        Object value = attribute.get();
        return value instanceof String ? (String) value : null;
    }
}
```

Trong ví dụ, `base("ou=PublicDirectory")` là **DN tương đối** với `dc=example,dc=org` đã đặt tại `ContextSource`. `LdapTemplate.search` dùng read-only context, nên cấu hình anonymous read-only được áp trong trường hợp này.

Hai điều quan trọng:

- **Chọn đúng attribute:** chỉ yêu cầu `cn` để tránh lấy dữ liệu không phục vụ chức năng. Nếu mapper cần `uid` hoặc `mail`, phải bổ sung tường minh vào `attributes(...)`.
- **Không xây filter bằng nối chuỗi từ input:** `LdapQueryBuilder` hỗ trợ truyền giá trị vào filter theo ngữ cảnh phù hợp. Nếu đang xây DN động, dùng `LdapNameBuilder` vì quy tắc escaping DN khác filter.

### 4.3. Nếu cần đọc bằng account dịch vụ và ghi bằng account khác

Khi ứng dụng vừa có chức năng công khai vừa có chức năng nội bộ, nên đặt ranh giới bằng **các bean cấu hình có tên rõ** và inject đúng service:

```text
PublicDirectoryService
   -> publicLdapTemplate
      -> publicContextSource (anonymous read)

InternalDirectoryService
   -> serviceLdapTemplate
      -> serviceContextSource (service DN + secret)

AdministrationService
   -> adminContextSource có quyền ghi hạn chế, chỉ dùng tại chức năng quản trị
```

Một `ContextSource` cũng có thể được cấu hình với account dịch vụ và `anonymousReadOnly=true` để thao tác đọc dùng anonymous, thao tác ghi dùng context có xác thực. Nhưng cấu hình này **dễ gây nhầm** nếu developer cho rằng mọi search đều dùng quyền của service account. Trong hệ thống nhiều nhóm phụ trách, các bean tách biệt thường giúp kiểm soát và kiểm thử rõ ràng hơn.

Không suy rằng tên gọi `getReadOnlyContext()` là cơ chế cưỡng chế quyền ghi của server. **Chỉ ACL máy chủ và chính sách ứng dụng mới xác định các thao tác thực sự được phép.**

### 4.4. Cấu hình XML và thuộc tính Boot

Trong cấu hình XML của Spring LDAP, có thể dùng `anonymous-read-only="true"` **cùng thông tin account dịch vụ**: thao tác đọc sẽ dùng context ẩn danh, trong khi những thao tác cần read-write context dùng danh tính được cấu hình. Ví dụ sau minh họa cấu hình kết hợp và chỉ phù hợp khi chính sách quyền cho phép:

```xml
<ldap:context-source
    id="hybridContextSource"
    url="ldaps://ldap.example.org:636"
    base="dc=example,dc=org"
    username="cn=svc-writer,ou=Services,dc=example,dc=org"
    password="${ldap.service.password}"
    anonymous-read-only="true"/>
```

Trong XML, `ldap.service.password` phải được giải quyết từ nguồn cấu hình/secret được bảo vệ, không đưa mật khẩu thật vào mã nguồn. Dự án phải khai báo namespace/schema Spring LDAP và xác minh khởi tạo bean theo phiên bản sử dụng. Cấu hình kết hợp không thích hợp nếu một developer có thể vô tình gọi thao tác ghi trên context đặc quyền; trong dự án lớn, tách bean public và nội bộ thường dễ quản trị hơn.

Không mặc định rằng chỉ cần để trống `spring.ldap.username` và `spring.ldap.password` trong Spring Boot sẽ tự tạo đúng cấu hình anonymous read-only. **Property của Spring Boot và thuộc tính `anonymousReadOnly` không phải cùng một thiết lập**; hãy kiểm tra phiên bản autoconfiguration và khai báo bean rõ ràng khi cần.

## 5. Kiểm chứng bằng `ldapwhoami` và `ldapsearch`

Việc một client gửi yêu cầu ẩn danh **không chứng minh** directory server cho phép đọc. Cần thử từng thao tác và quan sát quyền thực tế với cùng URL, base DN, filter và thuộc tính mà ứng dụng dự định dùng.

Các lệnh bên dưới giả định máy chủ thử nghiệm ở `ldap.example.org` có LDAPS, chứng chỉ đã được máy khách tin cậy và dữ liệu phù hợp.

### 5.1. Kiểm tra danh tính của kết nối

```bash
ldapwhoami -x -H ldaps://ldap.example.org:636
```

`-x` chỉ định simple authentication. Không có `-D` và `-W`, lệnh này kiểm tra kết nối với trạng thái ẩn danh theo hành vi mặc định của công cụ LDAP. Kết quả Who Am I có thể trống hoặc được biểu diễn khác tùy server; **đừng diễn giải mã kết thúc thành công như bằng chứng người dùng đã được xác thực**.

Để so sánh với account dịch vụ:

```bash
ldapwhoami -x \
  -H ldaps://ldap.example.org:636 \
  -D "cn=svc-reader,ou=Services,dc=example,dc=org" \
  -W
```

Account dịch vụ cần có credential hợp lệ. `-W` nhập mật khẩu qua prompt, tránh đưa secret trực tiếp vào shell history. Nếu kết quả/identity khác giữa hai lần thử, điều đó phù hợp với hai ngữ cảnh quyền khác nhau; vẫn phải kiểm chứng ACL từng nhánh.

### 5.2. Thử Root DSE với base rỗng

```bash
ldapsearch -LLL -x \
  -H ldaps://ldap.example.org:636 \
  -b "" -s base "(objectClass=*)" \
  namingContexts supportedLDAPVersion
```

Yêu cầu `-b ""` và `-s base` nhắm tới Root DSE. Server có thể trả một số attribute, từ chối hoặc không trả trường cụ thể. Đây là phép thử **khả năng khám phá công khai**, không phải chứng minh có thể tìm toàn bộ directory.

### 5.3. Thử nhánh công khai và nhánh hạn chế

```bash
# Tìm entry trong nhánh được thiết kế để công khai.
ldapsearch -LLL -x \
  -H ldaps://ldap.example.org:636 \
  -b "ou=PublicDirectory,dc=example,dc=org" \
  -s sub "(&(objectClass=inetOrgPerson)(uid=contact01))" \
  cn mail

# Kiểm tra rằng truy cập ẩn danh không làm lộ hồ sơ nội bộ.
ldapsearch -LLL -x \
  -H ldaps://ldap.example.org:636 \
  -b "ou=People,dc=example,dc=org" \
  -s sub "(uid=lan)" \
  cn mail telephoneNumber
```

Mục tiêu của thử nghiệm thứ hai là **xác minh ranh giới ACL đã định nghĩa**, thực hiện chỉ với dữ liệu, tài khoản và máy chủ được phép kiểm thử. Tùy directory server, thiếu quyền có thể biểu hiện bằng lỗi, kết quả rỗng hoặc một tập attribute bị ẩn. **Không nên kết luận rằng entry không tồn tại chỉ vì anonymous search không thấy nó.**

Đừng dùng toàn bộ nhánh công khai để thử trên máy chủ production với filter quá rộng. Giới hạn base DN, scope, số lượng kết quả và thời gian chờ để tránh gây tải không cần thiết.

### 5.4. So sánh kết quả với account dịch vụ

Để xác định vấn đề nằm ở dữ liệu hay ACL, có thể chạy cùng filter bằng account dịch vụ đã được phép đọc nhánh đó. Nếu account dịch vụ nhìn thấy entry còn anonymous không thấy, đây là một bằng chứng có ý nghĩa về khác biệt quyền hoặc chính sách visibility. Nhưng vẫn phải xem log server/ACL nếu cần kết luận chính xác, vì còn yếu tố referral, schema, giới hạn và triển khai.

## 6. Không được nhầm anonymous bind với “mật khẩu bị bỏ quên”

Một lỗi thường gặp là ứng dụng có `userDn` nhưng biến môi trường chứa mật khẩu bị thiếu hoặc rỗng:

```java
String serviceDn =
        "cn=svc-reader,ou=Services,dc=example,dc=org";
String servicePassword = System.getenv("LDAP_BIND_PASSWORD");

// Nguy hiểm nếu truyền tiếp một credential rỗng mà không kiểm tra.
source.setUserDn(serviceDn);
source.setPassword(servicePassword);
```

Trong LDAP, một request simple bind có DN **không rỗng** và password **rỗng** có thể bị xem là **unauthenticated simple bind**. Theo RFC 4513, khi server cho phép thao tác này, kết quả thành công vẫn có thể thiết lập **anonymous authorization state**, không xác minh DN.

Không xử lý lỗi cấu hình bằng cách tự động “fallback” sang anonymous:

```java
String servicePassword = System.getenv("LDAP_BIND_PASSWORD");
if (servicePassword == null || servicePassword.isBlank()) {
    throw new IllegalStateException(
            "LDAP service credential is missing");
}

source.setUserDn(
        "cn=svc-reader,ou=Services,dc=example,dc=org");
source.setPassword(servicePassword);
// Cấu hình service account: không bật anonymousReadOnly.
```

**Nguyên tắc fail-closed:** Nếu chức năng yêu cầu xác thực bằng account dịch vụ hoặc người dùng, thiếu credential là lỗi cấu hình/xác thực; không âm thầm chuyển sang trạng thái ẩn danh và tiếp tục như thể thành công.

Trong một luồng đăng nhập:

```java
if (password == null || password.isEmpty()) {
    throw new IllegalArgumentException(
            "Password must not be empty");
}
// Sau bước này mới gọi cơ chế xác thực phù hợp.
```

Đừng dùng `isBlank()` như một thay thế không suy xét cho chính sách mật khẩu của directory server: nếu ứng dụng cấm mọi mật khẩu chỉ gồm whitespace, đó là một **quy tắc sản phẩm bổ sung**; kiểm tra `isEmpty()` là điều cốt lõi để chặn simple bind với password độ dài bằng 0.

### Anonymous bind có chứng minh kết nối an toàn không?

Không. Từ “anonymous” nói về **danh tính/ủy quyền**, còn TLS nói về **bảo mật đường truyền và danh tính máy chủ**:

| Trục | Câu hỏi | Cách kiểm soát |
| --- | --- | --- |
| **Identity** | Client đã chứng minh là ai? | Bind/password, SASL, SSO hoặc anonymous |
| **Transport** | Client có nói chuyện với đúng server qua kênh bảo vệ không? | TLS được xác minh chứng chỉ và hostname |
| **Access control** | Identity hiện hành có quyền đọc/sửa gì? | LDAP ACL, chính sách ứng dụng |
| **Scope & load** | Truy vấn đi đâu, lấy bao nhiêu dữ liệu? | Base DN, scope, filter, size/time limit, rate limit |

Có thể dùng anonymous bind qua **LDAPS**: người dùng vẫn ẩn danh với directory, nhưng kết nối tới server được mã hóa và xác minh. Ngược lại, một bind có mật khẩu qua đường truyền không được bảo vệ có thể làm lộ credential.

## 7. TLS và pooling trong kết nối ẩn danh

**LDAPS** thường chạy tại cổng 636, thiết lập TLS ngay từ đầu. **StartTLS** thường được dùng trên cổng LDAP 389 để nâng cấp kết nối trước khi trao đổi dữ liệu/credential nhạy cảm.

Với anonymous access, TLS vẫn có lợi:

- Tránh người trên đường truyền đọc hoặc sửa kết quả tra cứu nếu dữ liệu cần được bảo vệ.
- Xác minh client đang kết nối tới đúng directory server.
- Hạn chế nguy cơ kết quả LDAP bị can thiệp trên mạng.

TLS **không** làm anonymous client trở thành người dùng đã xác thực. Nếu anonymous được phép đọc một entry, cơ chế phân quyền của server vẫn là điểm quyết định.

### 7.1. Chứng chỉ phải được xác minh

Khi cấu hình `ldaps://...`, hãy đảm bảo JVM có truststore phù hợp và kiểm tra được chứng chỉ theo hostname. Không dùng trust manager chấp nhận mọi chứng chỉ hoặc tắt kiểm tra tên máy chủ chỉ để vượt qua lỗi handshake.

Với StartTLS, logic kết nối phải nâng cấp TLS thành công **trước** khi gửi mật khẩu qua simple bind. Spring LDAP có các `DirContextAuthenticationStrategy` cho TLS ở các phiên bản hỗ trợ, nhưng phải đối chiếu cơ chế cụ thể và kiểm thử trên server đích.

### 7.2. Pooling không đồng nghĩa “ẩn danh và an toàn”

Connection/context pooling giúp giảm chi phí tạo lại kết nối trong một số workload. Tuy nhiên, cần kiểm soát:

1. **Danh tính của context:** tránh trộn context anonymous và context bind bằng service/user credential.
2. **Vòng đời TLS:** đặc biệt với StartTLS, không bật native JNDI pooling tùy tiện khi luồng TLS không hỗ trợ.
3. **Quyền truy cập:** pooled context không được mang quyền khác mong đợi của caller.
4. **Hạn mức tải:** pool không thay thế giới hạn truy vấn hoặc rate limit trên server/client.
5. **Kết nối chết:** phải xử lý thời gian nhàn rỗi, server restart và lỗi tái kết nối.

Đặc biệt, tài liệu Spring LDAP khuyến cáo không kết hợp native LDAP connection pooling với các cơ chế TLS của Spring LDAP theo cách thiếu kiểm chứng. Pooling cho anonymous read cũng cần đo lường cụ thể trước khi bật.

## 8. Hạn mức truy vấn quan trọng hơn khi không định danh người gọi

Anonymous search có thể được gọi mà không có danh tính LDAP cụ thể để giới hạn riêng người dùng. Vì thế, một thư mục có dữ liệu công khai vẫn có nguy cơ bị quét nhiều lần hoặc bị làm quá tải.

Một truy vấn an toàn nên có:

| Kiểm soát | Mục đích |
| --- | --- |
| **Base DN** giới hạn ở nhánh công khai | Không tìm trong toàn bộ DIT khi không cần |
| **Scope** là ONELEVEL/SUBTREE phù hợp | Tránh mở rộng sang các cấp con không chủ đích |
| **LDAP filter** có điều kiện cụ thể | Giảm số entry khớp |
| **Attributes** chỉ gồm dữ liệu công bố | Không kéo toàn bộ hồ sơ hoặc thông tin quản trị |
| **Size limit** và **time limit** | Hạn chế truy vấn tốn tài nguyên |
| **Connect/read timeout** | Không để request bị treo vô hạn khi mạng/server gặp vấn đề |
| **Rate limit/quota ở gateway và server** | Hạn chế quét/thử lặp nhiều lần |
| **Log và theo dõi** | Phát hiện tăng tải hoặc truy vấn bất thường, tránh log dữ liệu nhạy cảm |

Ví dụ với JNDI `SearchControls`:

```java
import javax.naming.directory.SearchControls;

SearchControls controls = new SearchControls();
controls.setSearchScope(SearchControls.SUBTREE_SCOPE);
controls.setReturningAttributes(new String[] {"cn", "mail"});
controls.setCountLimit(50);
controls.setTimeLimit(3000);
```

Trong Spring LDAP, có thể khai báo scope, số lượng, thời gian và attribute ở query API thích hợp với phiên bản; hoặc dùng overload nhận `SearchControls`. **Chọn ít attribute không tự giới hạn số entry**; filter cũng không thay thế timeout hoặc rate limit.

Khi khối lượng lớn, cần xem paged results, index của server và giới hạn truy vấn công khai. Đừng mở anonymous subtree search từ root chỉ để dựng một trang danh bạ vài dòng.

## 9. Xử lý lỗi và quan sát hành vi thực tế

Khi truy vấn ẩn danh không trả dữ liệu, có ít nhất bốn nguyên nhân có thể xảy ra:

1. Filter không khớp entry nào trong base DN/scope được chỉ định.
2. Server cho phép anonymous bind nhưng **không cho phép** đọc nhánh/attribute liên quan.
3. Base DN sai hoặc entry chưa tồn tại.
4. Kết nối tới server lỗi, TLS thất bại, timeout hoặc truy vấn chạm giới hạn.

Ứng dụng không nên bắt mọi exception rồi trả danh sách rỗng:

```java
// Không nên: che giấu lỗi LDAP như thể tìm kiếm thành công.
try {
    return ldapTemplate.search(query, mapper);
} catch (Exception e) {
    return List.of();
}
```

Trong Spring LDAP, nhiều lỗi JNDI được chuyển thành exception runtime của Spring. Chính sách xử lý nên tách:

| Tình huống | Biểu hiện có thể gặp | Cách ứng dụng cần phản ứng |
| --- | --- | --- |
| Không có entry khớp | Search trả danh sách rỗng | Trả kết quả không tìm thấy phù hợp, nếu truy vấn thành công |
| Anonymous không được search | Lỗi quyền, kết quả bị lọc ẩn hoặc thông báo khác tùy server | Kiểm tra ACL/visibility, không mặc định entry không tồn tại |
| Không bind được | Server từ chối anonymous bind hoặc chính sách kết nối | Báo lỗi cấu hình/chính sách, không tự fallback sang service identity quyền cao |
| Base DN sai | Lỗi tên không tồn tại hoặc danh sách rỗng tùy API | Kiểm tra base đã cấu hình và nhánh thực tế |
| Filter sai cú pháp | Lỗi filter hoặc truy vấn bị từ chối | Kiểm tra builder và dữ liệu đầu vào |
| Chứng chỉ TLS lỗi | Handshake/connection failure | Dừng kết nối; xử lý truststore, CA, hostname |
| Server chậm hoặc mất kết nối | Timeout, communication exception | Phản hồi lỗi hạ tầng có kiểm soát, theo dõi và cảnh báo |
| Vượt giới hạn tìm kiếm | Size/time limit, kết quả không trọn vẹn | Thu hẹp query hoặc dùng paging và giới hạn phù hợp |

Một số overload `LdapTemplate.search` có cấu hình xử lý `NameNotFoundException` thành không có kết quả; vì vậy cần kiểm tra phiên bản và hợp đồng API, không suy mọi danh sách rỗng là do filter.

**Logging:** ghi tên loại thao tác, phạm vi công khai, thời gian, loại lỗi và correlation ID là đủ cho nhiều trường hợp. Không ghi credential hoặc giá trị của các attribute nhạy cảm; log truy vấn chưa được giới hạn cũng có thể làm lộ dữ liệu đầu vào.

## 10. Kiểm thử anonymous bind và ranh giới ACL

Chỉ kiểm tra “có thể đọc một entry công khai” là chưa đủ. Cần chứng minh **không thể đọc entry hạn chế**, **không thể ghi**, **không dùng anonymous để đăng nhập**, và **lỗi kết nối không bị che giấu**.

### 10.1. Ma trận kiểm thử tích hợp

| Mã ca | Thiết lập và hành động | Kỳ vọng |
| --- | --- | --- |
| **ANON-01** | Anonymous search entry công khai, chỉ yêu cầu `cn` | Trả `cn` nếu server cho phép và dữ liệu tồn tại |
| **ANON-02** | Anonymous search nhánh `ou=People` bị hạn chế | Không lộ entry/attribute nội bộ theo chính sách ACL |
| **ANON-03** | Anonymous yêu cầu attribute riêng tư của entry công khai | Không nhận được dữ liệu nhạy cảm |
| **ANON-04** | Anonymous cố sửa entry fixture thử nghiệm | Server từ chối do ACL; dữ liệu sau thử vẫn nguyên |
| **ANON-05** | Account dịch vụ được phép đọc nhánh hạn chế | Kết quả tuân theo quyền đã cấp, khác anonymous khi ACL quy định |
| **ANON-06** | DN người dùng không rỗng + mật khẩu rỗng ở luồng đăng nhập | Ứng dụng chặn trước khi bind; không cấp phiên người dùng |
| **ANON-07** | Truststore không tin cậy certificate server | Kết nối TLS thất bại, không tự hạ cấp |
| **ANON-08** | Đọc dữ liệu với server bị ngắt hoặc timeout | Báo lỗi truy cập/hạ tầng, không báo “không tìm thấy” |
| **ANON-09** | Input `uid` chứa ký tự đặc biệt của filter | Query builder giữ input như dữ liệu; không mở rộng phạm vi |
| **ANON-10** | Query yêu cầu quá nhiều entry hoặc chạy lâu | Giới hạn được áp và lỗi/trạng thái được xử lý rõ |

**ANON-04 chỉ được thực hiện trên directory và entry thử nghiệm có quyền kiểm thử.** Test từ chối ghi là kiểm tra phía máy chủ, không thể chứng minh chỉ bằng việc bỏ nút “Sửa” khỏi giao diện.

### 10.2. Phân biệt kiểm thử cấu hình và kiểm thử kết quả

Unit test có thể xác minh Java Configuration đặt `anonymousReadOnly=true`, chọn đúng base DN và truyền đúng bộ lọc. Nhưng điều đó **không thể chứng minh** LDAP server đang áp dụng ACL mong muốn.

Integration test phải kết nối đến LDAP server hoặc môi trường tái hiện được cấu hình ACL, ví dụ:

```text
Given:
 - Nhánh ou=PublicDirectory có contact01 với cn công khai
 - Nhánh ou=People có lan, không được anonymous đọc
 - Server cho phép anonymous read-only tại nhánh công khai

When:
 - Gọi publicLdapTemplate.search cho contact01

Then:
 - Nhận thông tin công khai được cho phép

When:
 - Anonymous search entry lan trong ou=People

Then:
 - Không có dữ liệu cá nhân nào bị trả về
 - Ghi lại behavior cụ thể của server (lỗi hoặc không hiển thị)

When:
 - Luồng đăng nhập nhận password rỗng

Then:
 - Ứng dụng từ chối trước khi gửi Bind
```

Nếu phải dùng server nhúng hoặc thư mục giả lập, hãy nhớ schema, ACL và cách phản hồi anonymous khác nhau giữa các sản phẩm. Kết quả test với một implementation không tự chứng minh cấu hình tương đương ở directory server thật.

### 10.3. Kiểm thử tài khoản dịch vụ không vô tình dùng anonymous

Một phép thử có ích là xóa tạm biến môi trường `LDAP_BIND_PASSWORD` của **ứng dụng thử nghiệm** rồi khởi động service nội bộ:

- Service phải báo lỗi cấu hình/credential rõ ràng.
- Không được tự chuyển sang anonymous và trả kết quả theo quyền ẩn danh.
- Không được tự dùng tài khoản quản trị quyền rộng để “khắc phục” thiếu secret.

Cách kiểm thử này bảo vệ trước tình huống bind không xác thực vì mật khẩu trống mà vẫn có response thành công từ directory server.

## 11. Các lỗi thường gặp

| Nhận định hoặc cách làm | Vì sao sai | Cách sửa |
| --- | --- | --- |
| “Không nhập mật khẩu mà kết nối được tức là đã xác thực” | Anonymous/unauthenticated bind có thể thành công nhưng không xác minh người dùng | Phân biệt trạng thái bind, từ chối password rỗng trong luồng đăng nhập |
| “Anonymous bind cho phép đọc mọi entry” | ACL server mới quyết định visibility | Chỉ công bố nhánh/attribute được duyệt, kiểm thử negative case |
| “`setAnonymousReadOnly(true)` là ACL” | Đây là tùy chọn tạo context ở client | Cấu hình ACL tại directory server |
| “Không trả dữ liệu tức là entry không tồn tại” | Có thể do ACL, base sai, filter, referral hoặc lỗi | So sánh với account được cấp quyền, log/điều tra |
| “Dữ liệu công khai không cần TLS” | Kết quả có thể bị nghe lén/sửa đổi trên đường truyền | Dùng TLS khi cần bảo vệ và xác minh server |
| “Để trống `spring.ldap.password` là anonymousReadOnly” | Không bảo đảm đồng nghĩa, còn có nguy cơ bind không xác thực | Cấu hình explicit, kiểm tra thiếu credential |
| “Read-only context có nghĩa không thể ghi” | Quyền thực tế vẫn do server và operation quyết định | Chặn write bằng ACL, tách bean dùng đúng chức năng |
| “Bật pool thì truy vấn công khai hết chậm” | Pool không sửa filter/index/size limit | Đo hiệu năng và kiểm soát query |
| “Client-side filter là đủ để bảo vệ dữ liệu” | Dữ liệu đã truyền tới client trước khi lọc | ACL và attribute projection ở server, authorization ở ứng dụng |

## 12. Bài tập tổng hợp: danh bạ công khai có giới hạn

**Bối cảnh:** Tổ chức có hai nhánh LDAP: `ou=PublicDirectory` chứa dữ liệu cho phép công bố và `ou=People` chứa hồ sơ nội bộ. Ứng dụng Spring muốn cung cấp chức năng xem tên công khai nhưng không yêu cầu người xem đăng nhập.

**Yêu cầu:**

1. Vẽ DIT và định nghĩa rõ dữ liệu thuộc nhánh công khai, thuộc tính nào được phép đọc.
2. Cấu hình `publicContextSource` với `setAnonymousReadOnly(true)` và kết nối LDAPS có certificate verification đúng.
3. Tạo bean `publicLdapTemplate` và repository chỉ tìm trong `ou=PublicDirectory`, yêu cầu `cn` hoặc `cn,mail` theo nhu cầu.
4. Dùng `ldapwhoami -x` và `ldapsearch -x` để kiểm tra anonymous context thực tế trên server học tập.
5. Xác nhận ACL từ chối anonymous đọc `ou=People` và sửa dữ liệu.
6. Tạo một context khác cho thao tác nội bộ dùng service DN, mật khẩu lấy từ secret và quyền đọc tối thiểu.
7. Kiểm tra thiếu service password phải thất bại rõ ràng; kiểm tra luồng đăng nhập không chấp nhận password rỗng.
8. Thiết lập giới hạn truy vấn, timeout, theo dõi lỗi và kết quả test có thể tái hiện.

**Sản phẩm cần nộp:** mô tả cây/schema/ACL dự kiến, cấu hình Java Spring, query code, kết quả `ldapsearch` đã lược bỏ dữ liệu nhạy cảm, cùng bảng kiểm thử ANON-01 đến ANON-10.

### Câu hỏi tự kiểm tra

**Câu 1.** Anonymous bind có đồng nghĩa tài khoản không tồn tại hoặc server không yêu cầu xác thực cho mọi thao tác?

**Đáp án:** Không. Nó là trạng thái ủy quyền ẩn danh; server vẫn áp chính sách cho từng entry/attribute và có thể từ chối thao tác.

**Câu 2.** Nếu bind với DN của Lan và password rỗng nhưng server trả thành công, ứng dụng có nên đăng nhập Lan không?

**Đáp án:** Không. Đây có thể là unauthenticated simple bind với quyền ẩn danh; phải chặn password rỗng trước khi bind.

**Câu 3.** `setAnonymousReadOnly(true)` có thay đổi ACL của directory server không?

**Đáp án:** Không. Nó làm read-only context dùng môi trường ẩn danh; quyền vẫn được server quyết định.

**Câu 4.** Vì sao có thể đọc Root DSE nhưng không tìm được người trong `ou=People`?

**Đáp án:** Root DSE là entry đặc biệt, thường có chính sách visibility riêng; quyền đọc dữ liệu người dùng là phạm vi khác.

**Câu 5.** Anonymous kết nối qua LDAPS có trở thành danh tính đã xác thực không?

**Đáp án:** Không. TLS bảo vệ kênh và xác minh server, không tự chứng minh danh tính client nếu không có cơ chế xác thực client phù hợp.

**Câu 6.** Nếu query trả rỗng, làm sao biết đó là vì thiếu dữ liệu hay ACL?

**Đáp án:** Cần đối chiếu base, filter, schema, log server và thử nghiệm bằng account có quyền kiểm chứng, vì ACL có thể ẩn entry.

## Tổng kết

**Anonymous bind** là một cơ chế LDAP hợp lệ để truy cập bằng trạng thái ẩn danh, nhưng chỉ phù hợp với **thao tác và dữ liệu đã được quyết định cho phép công bố**. Cần đặc biệt phân biệt nó với **unauthenticated simple bind có DN nhưng mật khẩu rỗng**, vốn có thể đánh lừa một ứng dụng đăng nhập triển khai sai.

Trong Spring LDAP, `LdapContextSource.setAnonymousReadOnly(true)` dùng anonymous context cho các thao tác đọc của `LdapTemplate` hoặc API tương ứng khi sử dụng read-only context. Đây là **cấu hình phía client**: quyền truy cập thực tế phải được áp trên LDAP server và kiểm chứng bằng thử nghiệm ACL. Thiết kế hoàn chỉnh cần thêm TLS, DN/filter đúng, giới hạn truy vấn, chống lạm dụng, xử lý lỗi và tách luồng công khai với luồng xác thực/quản trị.

### Tài liệu tham khảo

- **RFC 4513 — Lightweight Directory Access Protocol (LDAP): Authentication Methods and Security Mechanisms**: https://www.rfc-editor.org/rfc/rfc4513.html (anonymous, unauthenticated simple bind, security considerations).
- **RFC 4511 — Lightweight Directory Access Protocol (LDAP): The Protocol**: https://www.rfc-editor.org/rfc/rfc4511.html (Bind, Search, kết quả và mã lỗi).
- **RFC 4512 — LDAP: Directory Information Models**: https://www.rfc-editor.org/rfc/rfc4512.html (DIT, attribute và schema).
- **RFC 4514 — String Representation of Distinguished Names**: https://www.rfc-editor.org/rfc/rfc4514.html.
- **RFC 4515 — String Representation of Search Filters**: https://www.rfc-editor.org/rfc/rfc4515.html.
- **Spring LDAP Reference: Configuration**: https://docs.spring.io/spring-ldap/reference/configuration.html (`ContextSource`, anonymous read-only, TLS, pooling).
- **Spring LDAP Javadoc: AbstractContextSource**: https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/core/support/AbstractContextSource.html (`setAnonymousReadOnly`, `getReadOnlyContext`).
