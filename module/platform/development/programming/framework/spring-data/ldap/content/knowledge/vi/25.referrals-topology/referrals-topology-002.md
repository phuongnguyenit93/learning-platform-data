# Lựa chọn ignore, follow hoặc throw cho referral

Trong **SPRING_DATA_LDAP**, ứng dụng Java truy cập dịch vụ thư mục LDAP qua Spring Data LDAP repository hoặc `LdapTemplate`, ánh xạ các entry được định danh bằng DN (*Distinguished Name*), `objectClass` và schema thành đối tượng Java. Trên hệ thống thực tế, một cây tên LDAP có thể trải qua nhiều **naming context**, domain hoặc máy chủ. Khi server nhận yêu cầu ở một vùng dữ liệu do server khác quản lý, nó có thể gửi **referral** để chỉ cho client nơi cần liên hệ tiếp.

Chế độ xử lý referral quyết định ứng dụng có bỏ qua tham chiếu, tự truy vấn server được giới thiệu hay chuyển việc xử lý cho mã ứng dụng. Trong JNDI/Spring LDAP, ba lựa chọn quan trọng nhất là **`ignore`**, **`follow`** và **`throw`**. Chọn sai chế độ có thể gây kết quả thiếu, lỗi không mong đợi, tăng độ trễ hoặc truy cập một endpoint ngoài phạm vi tin cậy.

Sau bài này, bạn có thể:

- Phân tích được kết quả thực tế của từng chế độ khi tìm kiếm qua nhiều nhánh LDAP.
- Cấu hình `Context.REFERRAL` trong JNDI và `LdapContextSource.setReferral(...)` trong Spring LDAP.
- Phân biệt chế độ referral với `LdapTemplate.setIgnorePartialResultException(...)`.
- Chọn chính sách cho use case đọc cục bộ, tìm kiếm phân tán, vận hành có kiểm soát và kiểm thử kết nối/bảo mật.

## 1. Khi nào client gặp referral?

Giả sử ứng dụng muốn tìm người dùng trong vùng `dc=example,dc=org`:

```text
                   Ứng dụng Java / Spring LDAP
                               |
                               v
                LDAP A: ldap-a.example.org
                  base: dc=example,dc=org
                      /             \
                     /               \
           ou=employees          ou=partners
           do A quản lý          do LDAP B quản lý
                                    |
                                    v
                         ldap-b.example.org
                         ou=partners,dc=example,dc=org
```

Nếu client gửi tìm kiếm `SUBTREE` từ `dc=example,dc=org`, LDAP A có thể trả entry bên dưới `ou=employees` và một tham chiếu sang LDAP B cho nhánh `ou=partners`. Có hai dạng liên quan:

| Dạng phản hồi LDAPv3 | Xuất hiện ở đâu? | Hệ quả |
|---|---|---|
| `SearchResultDone` với result code `referral (10)` | Kết quả cuối của thao tác được chuyển hướng | Thao tác hiện tại cần xử lý tại nơi được chỉ định |
| `SearchResultReference` | Xen trong luồng kết quả `SearchRequest` | Một phần kết quả tìm kiếm cần được tiếp tục ở vùng khác |

Ví dụ minh họa khi server A trả entry cục bộ và continuation reference:

```text
SearchRequest: base=dc=example,dc=org, scope=sub
  |
  +-- SearchResultEntry: uid=an,ou=employees,dc=example,dc=org
  +-- SearchResultEntry: uid=lan,ou=employees,dc=example,dc=org
  +-- SearchResultReference:
  |     ldap://ldap-b.example.org/ou=partners,dc=example,dc=org
  +-- SearchResultDone: success (0)
```

**`SearchResultReference` không phải LDAP entry.** `AttributesMapper` chỉ nhận `Attributes` của những entry đã được trả về; nó không tự nhận hoặc tự theo các reference. Đồng thời, `SearchResultDone: success` chỉ biểu thị phần tìm kiếm ở server đang trả lời đã hoàn tất; nó **không bảo đảm** client đã thu được dữ liệu ở tất cả vùng được tham chiếu.

Các referral thường chứa **LDAP URL**, có thể bao gồm host, port, base DN, scope, thuộc tính và filter:

```text
ldap://ldap-b.example.org/ou=partners,dc=example,dc=org??sub?(objectClass=inetOrgPerson)
```

URL này là dữ liệu từ directory. Theo referral có thể làm phát sinh kết nối mạng mới, thay đổi phạm vi tìm kiếm và yêu cầu quyền truy cập khác.

## 2. Ba chế độ JNDI: ignore, follow, throw

JNDI dùng thuộc tính môi trường `Context.REFERRAL`, có tên cấu hình `java.naming.referral`. Với LDAP provider JNDI thông dụng, ba giá trị được định nghĩa là:

| Giá trị | Cách JNDI xử lý | Thường dùng khi | Giới hạn cần nhớ |
|---|---|---|---|
| **`ignore`** | Không đi theo referral; mặc định nếu chưa cấu hình | Chỉ quan tâm vùng dữ liệu cục bộ hoặc muốn tránh tự mở kết nối sang server khác | Có thể gặp `PartialResultException`; kết quả có thể chưa đầy đủ |
| **`follow`** | Provider cố tự động truy vấn các đích được giới thiệu | Cần dữ liệu qua nhiều vùng và các endpoint cùng chính sách tin cậy | Phụ thuộc DNS, mạng, TLS, xác thực, vòng lặp, giới hạn |
| **`throw`** | Provider phát sinh `javax.naming.ReferralException` để mã JNDI xử lý | Muốn xét từng referral hoặc nghiên cứu topology ở tầng JNDI | Cần viết logic bắt ngoại lệ; `LdapTemplate` không cung cấp luồng xử lý thủ công tương đương |

**Mặc định của JNDI và `AbstractContextSource` trong Spring LDAP là `ignore`.** Đây là giá trị mặc định kỹ thuật; yêu cầu dữ liệu của nghiệp vụ mới là yếu tố quyết định có nên giữ nguyên.

### 2.1. ignore: Không tự đi đến server được giới thiệu

Ví dụ:

```java
env.put(Context.REFERRAL, "ignore");
```

Trong JNDI LDAPv3 provider chuẩn của Java, khi đặt `ignore`, provider thường **đính kèm control ManageDsaIT** (RFC 3296) để yêu cầu server xử lý referral entry như một entry thông thường. Nếu server không hỗ trợ hoặc không tuân theo control đó mà vẫn trả referral, JNDI có thể ném `PartialResultException`. Vì vậy, `ignore` **không đồng nghĩa** mọi lời gọi tìm kiếm luôn trả về một danh sách cục bộ mà không gặp ngoại lệ.

Ví dụ:

```text
LDAP A trả 12 entry cục bộ + tham chiếu sang LDAP B
JNDI: ignore
=> Không tự truy vấn B
=> Có thể nhận entry chỉ từ A, entry referral tùy cách server xử lý,
   hoặc PartialResultException khi đang duyệt kết quả
```

Chọn `ignore` khi endpoint A được định nghĩa là **nguồn dữ liệu duy nhất** cho tác vụ đó, ứng dụng chấp nhận không đọc các naming context khác, hoặc muốn giữ đường đi mạng trong phạm vi đã kiểm soát. Hãy thiết kế search base/scope khớp vùng dữ liệu dự kiến để tránh tạo ra yêu cầu vô tình băng qua ranh giới directory.

**Không chọn `ignore` chỉ vì muốn “hết lỗi”.** Nếu API đòi *toàn bộ tài khoản* của nhiều domain mà bạn bỏ qua referral, báo cáo và logic nghiệp vụ có thể thiếu người dùng.

### 2.2. follow: Theo referral tự động

Ví dụ:

```java
env.put(Context.REFERRAL, "follow");
```

Khi nhận referral, JNDI provider cố tiếp tục yêu cầu tại LDAP URL được chỉ định. Đối với **search continuation reference**, Oracle JNDI LDAP provider thông thường trả các entry bình thường trước, rồi xử lý các continuation reference; cách kết quả và ngoại lệ được bộc lộ vẫn phụ thuộc provider/server.

```text
Ứng dụng -> LDAP A
               +-- Entry A1
               +-- Entry A2
               +-- URL giới thiệu LDAP B
                                 |
                 JNDI follow ---+---> LDAP B
                                          +-- Entry B1
                                          +-- Entry B2
```

Chế độ này có thể phù hợp khi cần đọc dữ liệu trên **một topology đã được quản trị thống nhất**, các đích referral được tin cậy và ứng dụng có thể kết nối đến chúng bằng cơ chế TLS/xác thực phù hợp.

Tuy nhiên, `follow` **không phải cơ chế bảo đảm dữ liệu đầy đủ**. Quá trình theo reference có thể gặp:

- Host không phân giải DNS, cổng bị chặn, server B đang ngừng hoạt động.
- Chứng chỉ TLS không hợp lệ, chính sách bảo mật giữa A và B không tương thích.
- Quyền bind hoặc quyền đọc không đủ trên B; một số môi trường yêu cầu credential khác.
- Referral lặp vòng hoặc dẫn qua quá nhiều hop.
- Thời gian xử lý vượt giới hạn, số kết quả vượt ngưỡng server hoặc client.
- Kết quả trùng khi nhiều vùng có replica hoặc cùng entry logic.

Trong Sun/Oracle JNDI LDAP provider, môi trường `java.naming.ldap.referral.limit` có thể giới hạn số referral trong một chuỗi (mặc định thường là **10**; `0` có nghĩa không giới hạn). Đây là thuộc tính **riêng của provider**, không phải bảo đảm chung của mọi LDAP implementation. Giới hạn này và connection/read timeout nên được kiểm thử trong môi trường thực tế.

**Chỉ dùng `follow` khi có chính sách kiểm soát endpoint.** Cơ chế JNDI tự theo referral không tự trở thành allowlist. Không nên giả định một referral URL bất kỳ được server trả về là địa chỉ an toàn để truyền thông tin xác thực.

### 2.3. throw: Để tầng JNDI quyết định theo hay bỏ

Ví dụ:

```java
env.put(Context.REFERRAL, "throw");
```

JNDI ném `javax.naming.ReferralException` khi gặp referral. Mã JNDI trực tiếp có thể dùng `getReferralInfo()` để xem thông tin referral, `getReferralContext()` để lấy context tham chiếu, hoặc `skipReferral()` để bỏ qua một đích và xét đích khác nếu provider hỗ trợ.

**`throw` không tự biến referral thành một object nghiệp vụ.** Ứng dụng phải xác định danh sách endpoint được phép, cách xử lý trường hợp nhiều URL, vòng lặp, timeout và cách tổng hợp lỗi.

Ví dụ JNDI trực tiếp, cố ý chỉ **kiểm tra thông tin** mà không tự kết nối đến referral:

```java
import java.util.Hashtable;
import javax.naming.Context;
import javax.naming.NamingException;
import javax.naming.ReferralException;
import javax.naming.directory.Attributes;
import javax.naming.directory.DirContext;
import javax.naming.directory.InitialDirContext;

public class ManualReferralInspection {

    public void inspect() throws NamingException {
        Hashtable<String, Object> env = new Hashtable<>();
        env.put(Context.INITIAL_CONTEXT_FACTORY,
                "com.sun.jndi.ldap.LdapCtxFactory");
        env.put(Context.PROVIDER_URL, "ldaps://ldap-a.example.org:636");
        env.put(Context.REFERRAL, "throw");
        // Cấu hình TLS/xác thực thật do ứng dụng cung cấp an toàn.

        DirContext context = new InitialDirContext(env);
        try {
            Attributes attrs = context.getAttributes(
                    "ou=partners,dc=example,dc=org");
            // Xử lý dữ liệu chỉ khi server thực sự trả entry.
        } catch (ReferralException ex) {
            Object referralInfo = ex.getReferralInfo();
            // Kiểm tra và xác minh đích referral trước khi cho phép theo.
            // Không gọi getReferralContext() với endpoint chưa xác minh.
            throw ex;
        } finally {
            context.close();
        }
    }
}
```

Đoạn code minh họa cơ chế ở **JNDI thuần**. Đối với các search có `NamingEnumeration<SearchResult>`, referral/`PartialResultException` cũng có thể xuất hiện **khi duyệt enumeration**, không chỉ ngay lúc gọi `search(...)`; phải xử lý và đóng enumeration đúng cách.

Điểm quan trọng với Spring LDAP: `LdapTemplate` quản lý context, enumeration và chuyển đổi ngoại lệ JNDI sang hệ ngoại lệ Spring LDAP. Tài liệu `LdapTemplate` nêu rằng không có đường xử lý `ReferralException` thủ công tương tự ví dụ JNDI trực tiếp qua API template. **Không viết giả định** như sau:

```java
// Sai kỳ vọng: khi gọi LdapTemplate, không mặc định bắt được
// javax.naming.ReferralException từ tầng ứng dụng để gọi getReferralContext().
// ldapTemplate.search(query, mapper);
```

Nếu yêu cầu nghiệp vụ là xem xét từng referral URL theo allowlist, một thiết kế phù hợp hơn có thể là định tuyến tới các `ContextSource` được cấu hình trước, hoặc dùng JNDI có kiểm soát ở một lớp riêng rồi chuyển dữ liệu về service.

## 3. Cấu hình ba chế độ trong Spring LDAP

Trong Spring LDAP, `LdapContextSource` kế thừa `AbstractContextSource` và cung cấp `setReferral(String)`. Phương thức này thiết lập chính sách tương ứng với `Context.REFERRAL` khi tạo JNDI context.

Ví dụ cấu hình rõ ràng qua thuộc tính ứng dụng:

**`LdapConnectionConfiguration.java`**

```java
package com.example.ldap;

import java.util.HashMap;
import java.util.Map;
import java.util.Set;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.core.support.LdapContextSource;

@Configuration
public class LdapConnectionConfiguration {

    @Bean
    LdapContextSource ldapContextSource(
            @Value("${app.ldap.url}") String url,
            @Value("${app.ldap.base}") String base,
            @Value("${app.ldap.bind-dn}") String bindDn,
            @Value("${app.ldap.bind-password}") String password,
            @Value("${app.ldap.referral-mode:ignore}") String mode) {

        if (!Set.of("ignore", "follow", "throw").contains(mode)) {
            throw new IllegalArgumentException(
                    "referral-mode phải là ignore, follow hoặc throw");
        }

        LdapContextSource source = new LdapContextSource();
        source.setUrl(url);
        source.setBase(base);
        source.setUserDn(bindDn);
        source.setPassword(password);
        source.setReferral(mode);

        Map<String, Object> environment = new HashMap<>();
        environment.put("java.naming.ldap.referral.limit", "5");
        environment.put("com.sun.jndi.ldap.connect.timeout", "3000");
        environment.put("com.sun.jndi.ldap.read.timeout", "5000");
        source.setBaseEnvironmentProperties(environment);

        return source;
    }

    @Bean
    LdapTemplate ldapTemplate(LdapContextSource source) {
        return new LdapTemplate(source);
    }
}
```

Ví dụ `application.yml` tương ứng:

```yaml
app:
  ldap:
    url: ldaps://ldap-a.example.org:636
    base: dc=example,dc=org
    bind-dn: cn=reader,ou=service,dc=example,dc=org
    bind-password: ${LDAP_BIND_PASSWORD}
    referral-mode: ignore  # có thể đổi thành follow hoặc throw
```

**Lưu ý triển khai:**

1. `app.ldap.referral-mode` là **thuộc tính do ví dụ này tự định nghĩa**, không phải một property chuẩn của Spring Boot. Chúng ta kiểm tra giá trị trước khi đưa vào `setReferral`.
2. `LdapContextSource` và `LdapTemplate` do Spring quản lý vòng đời; với cấu hình bean như trên, Spring sẽ gọi phương thức khởi tạo cần thiết của context source.
3. Các key `java.naming.ldap.referral.limit` và `com.sun.jndi.ldap.*.timeout` là tùy chọn phụ thuộc JNDI LDAP provider. Chúng giúp kiểm soát hop, thời gian kết nối và thời gian chờ đọc; không được coi là API chuẩn chung của LDAP.
4. `setBase("dc=example,dc=org")` đặt mốc DN cho thao tác sử dụng template. Khi tìm ở `ou=employees`, truyền base tương đối `ou=employees`; không tự ghép lặp `dc=example,dc=org`.
5. Dữ liệu bind phải được cấp từ biến môi trường/secret manager. Kết nối LDAPS cần kiểm tra chuỗi chứng chỉ và hostname; không vô hiệu hóa xác thực TLS để referral “hoạt động”.

Với Spring Data LDAP repository, cùng `ContextSource`/`LdapTemplate` có thể được dùng bởi infrastructure repository. Vì vậy chế độ referral thường nằm ở **hạ tầng kết nối**, không phải ở từng interface `LdapRepository` hoặc một `AttributesMapper`.

## 4. Trường hợp đặc biệt: PartialResultException và LdapTemplate

Một hiểu nhầm phổ biến là coi hai thiết lập sau có cùng tác dụng:

```java
source.setReferral("ignore");                // chính sách JNDI
ldapTemplate.setIgnorePartialResultException(true); // cách template xử lý lỗi
```

Chúng hoàn toàn khác nhau:

| Thiết lập | Tầng áp dụng | Tác động chính | Không làm được |
|---|---|---|---|
| `source.setReferral("ignore")` | `ContextSource` / JNDI | Yêu cầu provider không theo referral | Không bảo đảm không có ngoại lệ hoặc kết quả đã đầy đủ |
| `source.setReferral("follow")` | `ContextSource` / JNDI | Provider cố theo referral | Không xác minh mọi endpoint an toàn hoặc luôn truy vấn thành công |
| `source.setReferral("throw")` | `ContextSource` / JNDI | Provider phát sinh `ReferralException` | Không tạo một callback thủ công tiện dụng trong `LdapTemplate` |
| `ldapTemplate.setIgnorePartialResultException(true)` | `LdapTemplate` | Bỏ qua ngoại lệ `PartialResultException` khi tìm kiếm | Không kết nối đến server được giới thiệu và không bổ sung dữ liệu thiếu |

Trong một số triển khai **Active Directory**, tìm kiếm phạm vi rộng có thể phát sinh `PartialResultException` do cách directory/provider xử lý referral. Spring LDAP cung cấp `setIgnorePartialResultException(true)` như **biện pháp tương thích** khi ứng dụng chấp nhận chỉ dùng phần kết quả đã thu được.

Ví dụ:

```java
@Bean
LdapTemplate ldapTemplate(LdapContextSource source) {
    LdapTemplate template = new LdapTemplate(source);
    template.setIgnorePartialResultException(true);
    return template;
}
```

Nếu sử dụng đoạn cấu hình này, nó **thay thế** bean `ldapTemplate` đã khai báo ở mục trước, không tạo thêm hai bean có cùng tên. Hãy chỉ bật khi hiểu rõ khả năng mất kết quả và có kiểm thử tích hợp xác nhận hành vi server cụ thể.

Ví dụ nghiệp vụ cần danh sách nhân viên để hiển thị gợi ý tên trong ứng dụng nội bộ có thể chấp nhận bỏ qua vùng khác. Ngược lại, đồng bộ quyền truy cập hoặc kiểm kê tất cả tài khoản **không nên báo thành công** nếu một phần directory chưa được tìm kiếm. Trong trường hợp đó, cần phát hiện và đánh dấu *partial* hoặc trả lỗi, đồng thời ghi nhận vùng nào đã thất bại.

## 5. Chọn chế độ theo mục tiêu nghiệp vụ

Không có một chế độ đúng cho tất cả hệ thống. Quyết định nên dựa trên **những vùng dữ liệu phải đọc**, mức độ tin cậy của đích referral và cách xử lý kết quả không đầy đủ.

| Tình huống | Lựa chọn tham khảo | Điều kiện hoặc hành động bổ sung |
|---|---|---|
| Chỉ đọc `ou=employees` trên server A | `ignore` cùng search base hẹp | Xác nhận phạm vi này không cần dữ liệu ở B |
| Directory nhiều nhánh cùng một tổ chức, các endpoint B đã được quản trị | `follow` | Kiểm tra DNS, TLS, quyền, timeout, hop limit và kết quả đầy đủ |
| Cần duyệt và phê duyệt từng URL được server đưa ra | `throw` ở tầng JNDI, hoặc định tuyến riêng | Kiểm tra allowlist và chính sách credential trước khi kết nối |
| Tìm kiếm Active Directory cho chức năng chấp nhận một phần dữ liệu | `ignore` hoặc cấu hình cụ thể đã kiểm thử; cân nhắc `ignorePartialResultException` | Công khai rằng kết quả chỉ từ vùng được phục vụ, không coi là toàn bộ directory |
| Đồng bộ bắt buộc đủ người dùng từ nhiều domain | Điều phối nhiều nguồn đã cấu hình; `follow` chỉ nếu đáng tin và được kiểm chứng | Theo dõi trạng thái thành công từng vùng, xử lý trùng và lỗi |
| Việc chọn endpoint thay đổi theo chính sách/tenant | Điều phối `ContextSource` theo tenant | Tránh để client tự theo URL chưa xác thực từ nguồn ngoài |

Một chuỗi câu hỏi quyết định:

```text
Có cần dữ liệu nằm ngoài naming context hiện tại?
  |
  +-- Không -> Giới hạn base/scope, cân nhắc ignore.
  |
  +-- Có
       |
       +-- Mọi đích referral đều thuộc miền tin cậy và được kiểm thử?
       |       |
       |       +-- Có -> Cân nhắc follow + giới hạn + kiểm tra tính đầy đủ.
       |       |
       |       +-- Không -> Tự định tuyến sang endpoint được phép;
       |                    dùng throw ở JNDI nếu cần kiểm tra referral.
       |
       +-- Bất kỳ nhánh nào thất bại?
               |
               +-- Có -> Báo lỗi hoặc đánh dấu kết quả một phần.
               +-- Không -> Đối chiếu phạm vi đã tìm rồi mới xác nhận đủ.
```

Đây là cây ra quyết định cho **mục tiêu đọc dữ liệu**. Khi dùng LDAP để cập nhật entry, đặc biệt là `rename`/`move`/CRUD xuyên naming context, cần phân tích ownership, schema, quyền và hỗ trợ thao tác của server; không suy ra cách ghi từ cấu hình referral khi đọc.

## 6. Ví dụ tìm kiếm và điểm đặt chính sách

Giả sử `LdapContextSource.base` là `dc=example,dc=org` và ứng dụng cần người dùng dưới `ou=employees`. `LdapTemplate` thực hiện tìm kiếm:

**`EmployeeDirectoryReader.java`**

```java
package com.example.ldap;

import java.util.List;
import javax.naming.directory.Attribute;
import javax.naming.directory.InvalidAttributeValueException;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.SearchScope;
import org.springframework.stereotype.Repository;
import static org.springframework.ldap.query.LdapQueryBuilder.query;

@Repository
public class EmployeeDirectoryReader {
    private final LdapTemplate ldapTemplate;

    public EmployeeDirectoryReader(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<String> findUidsBySurname(String surname) {
        if (surname == null || surname.isBlank()) {
            throw new IllegalArgumentException("surname không được rỗng");
        }

        LdapQuery ldapQuery = query()
                .base("ou=employees")
                .searchScope(SearchScope.SUBTREE)
                .attributes("uid")
                .countLimit(200)
                .timeLimit(5000)
                .where("objectClass").is("inetOrgPerson")
                .and("sn").is(surname);

        AttributesMapper<String> mapper = attrs -> {
            Attribute uid = attrs.get("uid");
            if (uid == null || uid.size() == 0) {
                throw new InvalidAttributeValueException(
                        "Entry LDAP thiếu uid");
            }
            return (String) uid.get();
        };

        return ldapTemplate.search(ldapQuery, mapper);
    }
}
```

Để thay đổi hành vi referral của lời gọi trên, ta đổi `setReferral(...)` trên `LdapContextSource` được inject vào template; **không đặt chế độ trên `AttributesMapper`** vì mapper chỉ chuyển đổi thuộc tính.

`base("ou=employees")` cùng `scope SUBTREE` hạn chế vùng tìm kiếm. `where(...).is(surname)` mã hóa giá trị thành filter an toàn, tránh LDAP filter injection. `countLimit(200)` và `timeLimit(5000)` giúp khống chế tài nguyên, **không phải tín hiệu chứng minh mọi entry đã được thu thập**.

Nếu nghiệp vụ cần truy vấn `ou=partners` trên B, nên cân nhắc một reader riêng kết nối tới B bằng cấu hình đã biết, thay vì chỉ thay filter và kỳ vọng mọi directory tự theo referral theo cùng cách.

## 7. Kiểm thử ba chế độ với directory phân tán

Không thể kiểm chứng referral chỉ bằng `BasicAttributes` hoặc mock `AttributesMapper`, vì referral và continuation reference là hành vi **ở giao thức LDAP/JNDI**, trước khi mapping DTO diễn ra. Cần một directory thử nghiệm gồm ít nhất A và B hoặc một server hỗ trợ thiết lập nhánh referral.

Ví dụ dữ liệu kiểm thử:

```text
Server A: dc=example,dc=org
  uid=an,ou=employees,dc=example,dc=org
  ou=partners -> LDAP URL của B

Server B: ou=partners,dc=example,dc=org
  uid=linh,ou=partners,dc=example,dc=org
```

Ma trận kiểm thử nên có:

| Trường hợp | Cấu hình | Cần quan sát |
|---|---|---|
| Không có referral | Cả base và filter nằm trong A | Cả ba mode cho kết quả cục bộ tương đương |
| A trả search continuation reference | `ignore` | Không có entry B từ việc tự theo; ghi nhận `PartialResultException` nếu provider phát sinh |
| A trả search continuation reference | `follow` | Entry từ A/B được thu thập nếu đường đi hợp lệ; đối chiếu số lượng và DN |
| A trả search continuation reference | `throw` qua JNDI trực tiếp | `ReferralException` có thể xuất hiện khi duyệt enumeration, sau các entry cục bộ |
| A trả result code `referral (10)` | `throw` qua JNDI trực tiếp | Bắt `ReferralException` của thao tác hiện tại |
| LDAP B không truy cập được | `follow` | Lỗi DNS/kết nối/timeout được hiển thị rõ và không báo dữ liệu đầy đủ |
| TLS B không tin cậy | `follow` | Kết nối bị từ chối theo chính sách chứng chỉ |
| B trỏ ngược A | `follow` | Giới hạn hop/timeout giúp tránh lặp vô hạn |
| Server không xử lý ManageDsaIT như mong đợi | `ignore` | Xác minh phản ứng `PartialResultException` và tác động đến kết quả |
| Active Directory trả partial result | `ignorePartialResultException(true)` | Lời gọi có thể hoàn tất với dữ liệu phần đã có; xác nhận không có entry B giả tạo |

Khi log/đo kiểm, lưu **endpoint, base DN, scope, filter đã làm sạch, mode, số entry ở từng vùng, trạng thái hoàn tất, thời gian, exception class và số hop**. Đừng ghi mật khẩu bind hoặc giá trị thuộc tính nhạy cảm.

### Phân biệt thành công của API với dữ liệu đầy đủ

Có thể mô hình hóa kết quả của một use case yêu cầu nhiều nguồn:

```text
expectedSources = {A, B}
completedSources = {A}          -> PARTIAL
completedSources = {A, B}       -> COMPLETE
completedSources = {}           -> FAILED
```

`List<PersonDto>` do repository hoặc `LdapTemplate` trả về **không tự chứa** danh sách naming context đã thành công. Với tác vụ cần đủ dữ liệu, ứng dụng phải tự quản lý chỉ dấu hoàn tất của từng vùng/nguồn hoặc dựa trên hợp đồng rõ ràng với một directory proxy được quản trị. Không kết luận `COMPLETE` chỉ vì không có ngoại lệ.

## 8. Bảo mật khi cho phép follow hoặc xử lý throw

Referral URL là một điểm **điều hướng qua mạng**. Vì vậy phải xét riêng các rủi ro sau:

1. **Đích kết nối:** chỉ cho phép tên miền/host/port thuộc hạ tầng được quản lý; tránh truy cập tùy ý endpoint do directory bên ngoài chỉ định.
2. **Thông tin xác thực:** xác định chính xác JNDI provider dùng credential nào khi mở referral context. Không mặc nhiên chuyển bind DN/quyền cao sang server khác; cấu hình nguyên tắc đặc quyền tối thiểu.
3. **TLS:** ưu tiên LDAPS hoặc StartTLS được cấu hình đúng, xác minh chứng chỉ/hostname ở cả A và B. Không tự chuyển từ kết nối an toàn sang LDAP cleartext chỉ để theo referral.
4. **Độ bền hệ thống:** áp dụng giới hạn hop, thời gian kết nối/đọc, search size/time limit; nhận diện vòng lặp và sự cố endpoint.
5. **Phạm vi dữ liệu:** referral có thể chuyển đến naming context có schema hoặc ACL khác. Kiểm tra quyền đọc và tránh hợp nhất entry trùng với giả định `uid` là khóa duy nhất toàn hệ thống.
6. **Giám sát:** phân biệt kết quả `COMPLETE`, `PARTIAL`, `FAILED`; không ẩn tình trạng một server B bị lỗi trong chức năng phân quyền hoặc đồng bộ danh tính.

`follow` là cơ chế định tuyến kỹ thuật của provider, không thực hiện chính sách allowlist toàn diện. Nếu có nhiều ranh giới tin cậy hoặc yêu cầu audit mọi referral, **định tuyến qua danh sách endpoint được cấu hình trước** thường dễ kiểm soát hơn.

## 9. Chẩn đoán lỗi thường gặp

| Hiện tượng | Giải thích có thể xảy ra | Cách xử lý |
|---|---|---|
| `ignore` nhưng vẫn có `PartialResultException` | Server vẫn trả referral/partial result; ManageDsaIT không được hỗ trợ như mong đợi | Kiểm tra server và provider; quyết định có chấp nhận dữ liệu một phần không |
| `follow` nhưng không đọc được B | DNS, firewall, TLS, bind, ACL hoặc referral URL lỗi | Kiểm tra từng bước và log endpoint đã làm sạch |
| `throw` mà không thấy `javax.naming.ReferralException` tại service | Spring LDAP đã chuyển đổi/quản lý ngoại lệ | Xem exception của Spring; dùng JNDI trực tiếp nếu cần xử lý thủ công |
| `ignorePartialResultException(true)` làm lời gọi “thành công” nhưng thiếu entry | Đã bỏ qua lỗi partial; không theo reference | Xác định vùng chưa tìm, đừng coi danh sách là toàn bộ |
| Tìm kiếm `SUBTREE` chậm bất thường | Nhiều referral, mạng chậm hoặc vòng lặp | Giới hạn base/scope/hop/timeout, kiểm tra topology |
| Có entry trùng sau `follow` hoặc hợp nhất nhiều nguồn | Nhiều replica hay cùng thực thể ở các vùng | Xây dựng quy tắc định danh và khử trùng lặp phù hợp |
| Referrals thay đổi theo môi trường | Server, schema, DNS, ACL hoặc naming context khác nhau | Dùng topology thử nghiệm tương tự production và ghi nhận hợp đồng dữ liệu |

Không nên che toàn bộ `NamingException` hoặc ngoại lệ Spring LDAP bằng `catch (Exception) { return List.of(); }`. Cách này khiến lỗi kết nối, sai schema, thiếu quyền và referral bị lẫn với trường hợp **không có người dùng nào khớp**.

## 10. Câu hỏi và bài tập tự kiểm tra

1. Vì sao `ignore` là mặc định JNDI nhưng không bảo đảm truy vấn sẽ không ném `PartialResultException`? ManageDsaIT có vai trò gì?
2. Tại sao `follow` có thể giúp hoàn chỉnh một truy vấn `SUBTREE`, và những yếu tố nào khiến quá trình này vẫn thất bại?
3. Ở tầng JNDI, `throw` cung cấp dữ liệu nào để ứng dụng quyết định xử lý referral? Vì sao không nên kỳ vọng một callback tương đương khi gọi `LdapTemplate.search(...)`?
4. `source.setReferral("ignore")` khác `ldapTemplate.setIgnorePartialResultException(true)` ở tầng tác động và hậu quả như thế nào?
5. Nếu API dùng để **đồng bộ mọi tài khoản trên hai domain**, bạn sẽ chọn chính sách nào và kiểm chứng “đầy đủ” bằng cách nào?
6. Điều gì phải được xác minh trước khi JNDI mở một kết nối mới đến URL do LDAP server trả về?

**Bài tập tình huống:** Hệ thống có LDAP A quản lý nhân viên và LDAP B quản lý đối tác. Trang gợi ý nhân viên chỉ cần dữ liệu A, nhưng quy trình kiểm kê tài khoản phải lấy cả A và B. Hãy chọn `ignore`, `follow`, `throw` hoặc định tuyến nhiều nguồn cho từng chức năng; nêu rõ search base, chính sách TLS, quyền truy cập, giới hạn hop và quy tắc đánh dấu `PARTIAL` khi B ngừng hoạt động.

**Ghi nhớ:** `ignore` giữ việc tìm kiếm ở vùng hiện tại nhưng có thể trả dữ liệu thiếu hoặc báo lỗi partial; `follow` để JNDI tự theo referral với nhiều phụ thuộc kết nối và bảo mật; `throw` cho phép JNDI caller chủ động xử lý `ReferralException`, trong khi `LdapTemplate` có cơ chế bao bọc ngoại lệ riêng. Chọn mode theo **yêu cầu hoàn chỉnh của kết quả**, topology và ranh giới tin cậy; kiểm thử trên directory thực trước khi áp dụng.

### Tài liệu tham khảo

- Oracle JNDI Tutorial: [Referrals in the JNDI](https://docs.oracle.com/javase/jndi/tutorial/ldap/referral/jndi.html) — `Context.REFERRAL`, ba chế độ, ManageDsaIT và continuation reference.
- Oracle JNDI Tutorial: [Manually Following Referrals](https://docs.oracle.com/javase/jndi/tutorial/ldap/referral/throw.html) — `ReferralException` và quy trình xử lý ở JNDI.
- Oracle JNDI LDAP Provider: [Environment properties](https://docs.oracle.com/javase/8/docs/technotes/guides/jndi/jndi-ldap-gl.html) — `java.naming.ldap.referral.limit` và các đặc điểm của provider.
- Spring LDAP API: [`AbstractContextSource.setReferral`](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/core/support/AbstractContextSource.html), cấu hình referral trong `LdapContextSource`.
- Spring LDAP API: [`LdapTemplate.setIgnorePartialResultException`](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/core/LdapTemplate.html), ngoại lệ khi tìm kiếm, lưu ý với Active Directory.
- IETF [RFC 4511 — LDAP: The Protocol](https://www.rfc-editor.org/rfc/rfc4511) và [RFC 3296 — Named Subordinate References in LDAP](https://www.rfc-editor.org/rfc/rfc3296), nền tảng giao thức và ManageDsaIT.
