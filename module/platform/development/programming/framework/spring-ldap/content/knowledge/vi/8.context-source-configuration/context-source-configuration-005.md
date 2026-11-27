# ContextSource proxy và lazy context trong Spring LDAP

Trong ứng dụng Spring LDAP, `ContextSource` là điểm truy cập để tạo các đối tượng JNDI `DirContext`. Từ một `DirContext`, client có thể tìm kiếm, đọc hoặc chỉnh sửa entry trên LDAP server. Khi ứng dụng lớn lên, ta thường muốn **bọc `ContextSource` bằng một proxy** để bổ sung hành vi như quan sát truy vấn, quản lý context trong giao dịch bù trừ hoặc tái sử dụng kết nối. Đồng thời, Spring Framework cho phép **khởi tạo bean theo yêu cầu** (lazy initialization) thay vì tạo ngay khi ứng dụng khởi động.

Hai ý này liên quan nhưng **không đồng nhất**: một proxy của `ContextSource` có thể thay đổi cách lấy và đóng `DirContext` mà không trì hoãn khởi tạo bean; ngược lại, `@Lazy` có thể trì hoãn tạo bean mà không bảo đảm trì hoãn kết nối TCP hay cung cấp pooling. Hiểu rõ sự khác biệt giúp cấu hình Spring LDAP an toàn, tránh rò rỉ context và dễ kiểm tra lỗi kết nối.

Sau bài học trong chương **Cấu hình ContextSource**, bạn có thể:

- Giải thích trách nhiệm của `ContextSource`, `DirContext`, `LdapTemplate` và proxy/decorator.
- Phân biệt **lazy bean**, **lazy dependency proxy** và **thời điểm mở context/kết nối LDAP**.
- Nhận diện các trường hợp dùng `TransactionAwareContextSourceProxy`, `SingleContextSource`, pooling và observation.
- Sử dụng `@Lazy` đúng chỗ, nêu rõ điều kiện phát hiện lỗi bị dời sang lần truy cập đầu.
- Kiểm thử số lần lấy/đóng context và hành vi khi LDAP server không sẵn sàng.
- Lựa chọn cơ chế phù hợp với TLS, xác thực, quyền truy cập và tải thực tế.

## 1. Từ `ContextSource` tới một thao tác LDAP

`ContextSource` là interface của Spring LDAP chịu trách nhiệm **cấu hình và cung cấp `DirContext`**. Ba phương thức chính:

| Phương thức | Ý nghĩa thường dùng |
| --- | --- |
| `getReadOnlyContext()` | Lấy context dành cho thao tác đọc |
| `getReadWriteContext()` | Lấy context dành cho thao tác có thể ghi |
| `getContext(principal, credentials)` | Lấy context xác thực bằng danh tính/mật khẩu cụ thể, thường phục vụ kiểm tra credential |

Tên “read-only” mô tả mục đích API, **không phải cơ chế bảo mật tự động**. Quyền được đọc hoặc sửa entry vẫn do cách xác thực và ACL của LDAP server quyết định. Mặc định, một số triển khai `ContextSource` dùng cùng tài khoản được cấu hình cho context đọc và ghi, trừ khi có cấu hình riêng.

`LdapContextSource` là triển khai cấu hình thường gặp; nó giữ các thông số như URL, base DN, bind DN, password và môi trường JNDI để tạo context. `LdapTemplate` là lớp phía trên, sử dụng `ContextSource` để lấy context, gọi LDAP và đóng tài nguyên khi thao tác kết thúc.

```text
EmployeeDirectory / ứng dụng
             │
             ▼
       LdapTemplate
             │ gọi ContextSource.getReadOnlyContext()
             ▼
       ContextSource
             │ cấp DirContext
             ▼
          DirContext ── LDAP server
             │
             └── close() khi thao tác kết thúc
```

Với nhiều thao tác thông thường, `LdapTemplate` thực hiện phần “plumbing”: lấy context, chạy lệnh, xử lý `NamingEnumeration` khi tìm kiếm, chuyển đổi lỗi JNDI và đóng context. Vì vậy, code nghiệp vụ thường không cần tạo `InitialDirContext` hay tự gọi `close()`. Vòng đời này có thể được điều chỉnh bởi những proxy chuyên dụng.

Ví dụ sử dụng `LdapTemplate` với `ContextSource.base = "dc=example,dc=org"`:

```java
import java.util.List;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;

import static org.springframework.ldap.query.LdapQueryBuilder.query;

public final class PeopleReader {
    private final LdapTemplate template;

    public PeopleReader(LdapTemplate template) {
        this.template = template;
    }

    public List<String> findUids(String uid) {
        return template.search(
            query().base("ou=people").where("uid").is(uid),
            (AttributesMapper<String>) attributes ->
                (String) attributes.get("uid").get()
        );
    }
}
```

Trong đoạn code, `ou=people` là **search base tương đối** với base của `ContextSource`; query builder xử lý escaping giá trị `uid`. Đối tượng `LdapTemplate` có thể sống xuyên suốt ứng dụng, nhưng điều đó **không có nghĩa** một `DirContext` luôn được dùng chung suốt thời gian chạy.

## 2. ContextSource proxy là gì?

Một **proxy/decorator của `ContextSource`** cũng thực hiện interface `ContextSource`, nhận một `ContextSource` đích (target), rồi chuyển tiếp hoặc thay đổi cách xử lý lời gọi:

```text
LdapTemplate
    │
    ▼
ContextSource proxy
    │     ├── quan sát / ghi metric
    │     ├── quản lý context theo giao dịch
    │     └── chính sách cấp và trả context
    ▼
LdapContextSource (target)
    │
    ▼
JNDI DirContext → LDAP server
```

Ý tưởng là **giữ nguyên giao diện** cho client. `LdapTemplate` vẫn gọi `getReadOnlyContext()` hoặc `getReadWriteContext()`; proxy có thể bọc context được trả về, theo dõi thời gian thao tác hoặc điều chỉnh vòng đời đóng.

Proxy có thể ở hai mức khác nhau:

1. **Proxy `ContextSource`:** intercept việc yêu cầu context và quyết định trả về object nào.
2. **Proxy `DirContext`:** intercept các phương thức như `search`, `modifyAttributes` hoặc `close` của context mà client đang dùng.

Một implementation có thể kết hợp cả hai: proxy nguồn trả về proxy context. **Không được giả định** mọi proxy đều có cùng khả năng; hành vi phải đọc theo API/tài liệu của wrapper cụ thể.

### Một số wrapper có thật trong hệ sinh thái Spring LDAP

| Thành phần | Mục đích | Không nên nhầm với |
| --- | --- | --- |
| `TransactionAwareContextSourceProxy` | Đưa `DirContext` vào cơ chế giao dịch bù trừ do Spring LDAP quản lý | Lazy bean hay giao dịch LDAP atomic phía server |
| `SingleContextSource` | Giữ **cùng một context** cho một nhóm thao tác, ví dụ một lượt xử lý phân trang | Pool toàn ứng dụng hoặc singleton `DirContext` dùng chung các thread |
| `PoolingContextSource` / biến thể pool được hỗ trợ theo phiên bản | Quản lý nhóm context/kết nối để tái sử dụng có kiểm soát | `@Lazy`, vốn chỉ liên quan đến khởi tạo bean |
| `ObservationContextSource` (ở phiên bản hỗ trợ) | Bọc context để ghi thời gian và trace của thao tác LDAP | Cơ chế retry hoặc cache kết quả |
| `@Lazy` của Spring Framework | Trì hoãn giải quyết/khởi tạo dependency ở tầng IoC | Một lớp `ContextSource` proxy chuyên dụng của Spring LDAP |

Các wrapper và API cụ thể có thể khác theo **phiên bản Spring LDAP và Spring Framework**. Hãy đối chiếu dependencies của ứng dụng với tài liệu đúng phiên bản trước khi cấu hình.

## 3. Ba kiểu “lazy” rất dễ bị nhầm

Từ “lazy context” thường được dùng không chặt chẽ. Khi thảo luận thiết kế, nên chỉ rõ **điều gì được trì hoãn**:

| Khía cạnh | Điều xảy ra | Cách kiểm soát |
| --- | --- | --- |
| **Lazy bean** | Spring container tạo một bean khi được yêu cầu thay vì tạo ngay lúc startup | `@Lazy` trên bean/class hoặc cấu hình lazy initialization |
| **Lazy dependency resolution** | Một collaborator nhận proxy; target dependency được resolve ở lần sử dụng đầu | `@Lazy` tại injection point, hoặc `ObjectProvider` |
| **Acquisition của DirContext** | Code chỉ yêu cầu context khi bắt đầu thao tác LDAP cần nó | Cách `LdapTemplate` và `ContextSource` hoạt động |
| **Kết nối mạng thực tế** | TCP/TLS/bind được thực hiện ở thời điểm do provider, cấu hình, pool và đường gọi quyết định | Quan sát JNDI provider, network, pool và thời điểm thao tác |

Hai điểm cần nhớ:

- **Tạo bean `LdapContextSource` không đồng nghĩa kết nối LDAP đã thành công.** Một số lỗi URL/cấu hình có thể phát hiện sớm, trong khi lỗi DNS, TLS, bind hoặc kết nối có thể chỉ xuất hiện khi lấy context hay thực hiện thao tác. Thời điểm phụ thuộc phiên bản/provider/cấu hình.
- **Đánh dấu `@Lazy` không đảm bảo “không có socket nào mở khi startup”** nếu bean khác, health check, bước initialization hoặc background task vẫn chủ động dùng LDAP.

Khi hệ thống có yêu cầu *fail fast* (không được nhận traffic nếu LDAP không hoạt động), trì hoãn quá nhiều có thể dời sự cố đến request đầu tiên. Ngược lại, nếu LDAP chỉ phục vụ tính năng tùy chọn, lazy initialization có thể giúp phần ứng dụng không phụ thuộc LDAP khởi động độc lập hơn. Lựa chọn dựa trên yêu cầu sẵn sàng của hệ thống.

## 4. Dùng `@Lazy` để trì hoãn resolve bean

Ví dụ một ứng dụng Spring có `LdapTemplate` đã được cấu hình bằng `ContextSource` (qua Spring Boot auto-configuration hoặc cấu hình Java riêng). Một service chỉ dùng LDAP khi người dùng thực sự mở tính năng danh bạ:

```java
import java.util.List;
import org.springframework.context.annotation.Lazy;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.stereotype.Service;

import static org.springframework.ldap.query.LdapQueryBuilder.query;

@Service
public class OptionalDirectoryFeature {
    private final LdapTemplate ldapTemplate;

    public OptionalDirectoryFeature(@Lazy LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<String> findUserIds(String uid) {
        return ldapTemplate.search(
            query().base("ou=people").where("uid").is(uid),
            (AttributesMapper<String>) attributes ->
                (String) attributes.get("uid").get()
        );
    }
}
```

`@Lazy` trên tham số constructor cho phép Spring tiêm một **lazy-resolution proxy**. Service có thể được tạo mà chưa cần resolve dependency này tại điểm injection; việc dùng `ldapTemplate.search(...)` sẽ buộc proxy lấy target khi cần.

**Lưu ý quan trọng:** nếu `LdapTemplate` đã được Spring tạo sẵn theo chính sách singleton eager hoặc do bean khác sử dụng lúc startup, lazy-resolution proxy trong service **không quay ngược thời gian để hủy việc tạo bean đó**. Nó chỉ làm lazy việc resolve tại injection point này.

Nếu ứng dụng tự khai báo bean `LdapTemplate`, có thể đánh dấu bean đó là lazy:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Lazy;
import org.springframework.ldap.core.ContextSource;
import org.springframework.ldap.core.LdapTemplate;

@Configuration(proxyBeanMethods = false)
public class DirectoryTemplateConfiguration {
    @Bean
    @Lazy
    LdapTemplate directoryLdapTemplate(ContextSource contextSource) {
        return new LdapTemplate(contextSource);
    }
}
```

Đoạn này phù hợp khi bạn **quản lý bean template riêng**. Nếu Boot đã tạo `LdapTemplate`, tránh vô tình tạo thêm nhiều bean cùng kiểu gây lỗi dependency ambiguity; dùng cấu hình nhất quán và `@Qualifier` khi có nhiều template. Theo quy tắc của Spring, **một bean lazy vẫn có thể được tạo lúc startup nếu singleton eager khác yêu cầu nó trực tiếp**, nên cần xem toàn bộ dependency graph.

### Dùng `ObjectProvider` khi cần quyết định bằng code

`ObjectProvider<T>` của Spring cho phép trì hoãn thao tác **lấy dependency** đến khi logic chủ động gọi `getObject()`:

```java
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.stereotype.Service;

@Service
public class DirectoryAvailabilityProbe {
    private final ObjectProvider<LdapTemplate> templateProvider;

    public DirectoryAvailabilityProbe(ObjectProvider<LdapTemplate> provider) {
        this.templateProvider = provider;
    }

    public boolean canReadRoot() {
        // Ở đây mới chủ động yêu cầu bean thông qua provider.
        LdapTemplate template = templateProvider.getObject();
        return template.lookup("") != null;
    }
}
```

Đây là ví dụ đơn giản về **thời điểm resolve dependency**, không phải một health check production hoàn chỉnh. `lookup("")` chỉ hữu ích nếu base context tồn tại và tài khoản có quyền đọc. Chỉ cần một bean khác dùng target trước đó thì target có thể đã được tạo từ trước. `getObject()` cũng không tự bảo đảm an toàn trước timeout hoặc lỗi LDAP.

## 5. Phân biệt Spring lazy proxy với `ContextSource` proxy

Hai luồng thực thi khác nhau:

```text
Trường hợp A — @Lazy tại injection point

Service ── lazy Spring bean proxy ── (lần gọi đầu) ── LdapTemplate
                                                   │
                                                   ▼
                                             ContextSource
                                                   │
                                                   ▼
                                                DirContext

Trường hợp B — ContextSource wrapper

Service ── LdapTemplate ── ContextSource proxy ── target ContextSource
                                │
                                ▼
                       DirContext (có thể là proxy)
                                │
                                ▼
                             LDAP server
```

Ở **A**, câu hỏi chính là “Spring đã khởi tạo/resolve collaborator chưa?”. Ở **B**, câu hỏi chính là “lấy context nào, có bọc context hay giữ nó không, khi đóng thì tác động tới context thật như thế nào?”.

Hai cơ chế có thể dùng cùng nhau nhưng không bắt buộc đi đôi. Việc thêm `@Lazy` không làm `LdapTemplate` tự nhiên có transactional context hay connection pool, và việc dùng `TransactionAwareContextSourceProxy` không khiến mọi bean trong ứng dụng khởi tạo theo yêu cầu.

## 6. Ví dụ `TransactionAwareContextSourceProxy`

Spring LDAP có cơ chế **compensating transaction** trong những phiên bản/module hỗ trợ. Cơ chế này có thể ghi nhận thao tác chỉnh sửa LDAP và thực hiện thao tác bù để cố khôi phục trạng thái khi rollback.

`TransactionAwareContextSourceProxy` bọc target `ContextSource` để các `DirContext` mà `LdapTemplate` nhận được nhận biết ngữ cảnh transaction. Nó phối hợp với `ContextSourceTransactionManager`, chứ **không tự tạo giao dịch** chỉ bằng việc bọc source.

Một sơ đồ cấu hình:

```text
ContextSourceTransactionManager ────────┐
     dùng target ContextSource          │
                                        ▼
                                  LdapContextSource
                                        ▲
                                        │ target của proxy
LdapTemplate ── TransactionAwareContextSourceProxy
                   (bọc DirContext khi sử dụng)
```

Ví dụ wiring rút gọn, với bean raw source đã được cấu hình ở nơi khác:

```java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ldap.core.ContextSource;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.transaction.compensating.manager.TransactionAwareContextSourceProxy;

@Configuration(proxyBeanMethods = false)
public class LdapTransactionProxyConfiguration {
    @Bean("transactionAwareContextSource")
    ContextSource transactionAwareContextSource(
            @Qualifier("rawLdapContextSource") ContextSource target) {
        return new TransactionAwareContextSourceProxy(target);
    }

    @Bean("transactionAwareLdapTemplate")
    LdapTemplate transactionAwareLdapTemplate(
            @Qualifier("transactionAwareContextSource") ContextSource source) {
        return new LdapTemplate(source);
    }
}
```

**Về tính hoàn chỉnh:** ví dụ này chỉ minh họa **wiring của proxy và template**. Muốn dùng transaction thật trong ứng dụng phải cấu hình `ContextSourceTransactionManager` với **target context source** (không phải proxy), cấu hình transaction boundary/annotation và bảo đảm phiên bản thư viện cung cấp hỗ trợ này. Nếu đã có template/source do Boot tạo, cần quản lý bean name/qualifier để tránh nhập nhằng.

> Transaction bù trừ của Spring LDAP **không phải giao dịch ACID atomic được LDAP server bảo đảm**. Nếu mất kết nối giữa lúc rollback, một phần thao tác có thể không được hoàn tác. Không dùng proxy này như lời bảo đảm cho cập nhật dữ liệu nhạy cảm hoặc các thao tác cần atomicity liên hệ nhiều hệ thống.

Các trường hợp dùng transaction proxy thường liên quan đến chuỗi thao tác ghi có chính sách bù trừ; nó không cần thiết cho truy vấn đọc `lookup` đơn giản và cũng không phải giải pháp cải thiện latency do kết nối LDAP chậm.

## 7. `SingleContextSource`: giữ cùng context trong một nhóm thao tác

Theo mặc định, nhiều lần gọi độc lập vào `LdapTemplate` có thể lấy những `DirContext` khác nhau. Một số tác vụ đặc biệt, ví dụ **paged results** theo yêu cầu của LDAP server, cần giữ cùng kết nối/context giữa các bước xử lý cookie.

Spring LDAP cung cấp `SingleContextSource` như một decorator: trong phạm vi một callback, nó có thể làm cho những thao tác `LdapOperations` sử dụng **cùng một context**. Wrapper context có thể **bỏ qua các lời gọi `close()` tạm thời** để context gốc còn dùng được, rồi đóng khi callback kết thúc.

Ví dụ độc lập, mục đích cho thấy cách gom thao tác:

```java
import java.util.List;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.ContextSource;
import org.springframework.ldap.core.support.SingleContextSource;

public final class RelatedLookups {
    private final ContextSource source;

    public RelatedLookups(ContextSource source) {
        this.source = source;
    }

    public List<String> readTwoCommonNames() {
        return SingleContextSource.doWithSingleContext(source, operations -> {
            String first = operations.lookup(
                "uid=lan,ou=people",
                (AttributesMapper<String>) attrs ->
                    (String) attrs.get("cn").get()
            );
            String second = operations.lookup(
                "uid=minh,ou=people",
                (AttributesMapper<String>) attrs ->
                    (String) attrs.get("cn").get()
            );
            return List.of(first, second);
        });
    }
}
```

Đoạn code trên giả định `ContextSource.base = "dc=example,dc=org"` và các entry có `cn`. Đây là ví dụ về **chung một context**; trong truy vấn tên đơn giản, thực tế không nhất thiết cần `SingleContextSource`. Hãy dùng nó khi có lý do kỹ thuật rõ ràng, chẳng hạn workflow phải chia nhiều bước phụ thuộc trạng thái kết nối.

**Không giữ một `DirContext` sống vĩnh viễn như singleton application** và chia sẻ bừa bãi giữa các request/thread. `DirContext` là tài nguyên có trạng thái và vòng đời; cách dùng đó dễ gây vấn đề đồng thời, hết hạn kết nối và khó khôi phục khi LDAP server đóng session. `SingleContextSource.doWithSingleContext(...)` có phạm vi sử dụng/cleanup hữu hạn, khác với việc dùng một context toàn cục.

## 8. Pooling và observation cũng là wrapper, nhưng không phải “lazy”

**Pooling:** một `PoolingContextSource` hoặc biến thể được phiên bản Spring LDAP hỗ trợ có thể quản lý tập context để giảm chi phí tạo lại kết nối. Khi ứng dụng “đóng” context đã mượn, wrapper có thể **trả tài nguyên về pool**, thay vì đóng kết nối mạng ngay lập tức. Vì vậy, không thể suy ra rằng cứ gọi `close()` là TCP socket bị ngắt.

Pooling cần chính sách về kích thước pool, validation, thời gian chờ, hủy kết nối hỏng và xoay vòng credential. Với Java/JNDI native pooling, cần chú ý giới hạn về kiểm tra kết nối và tương tác với TLS; không tự động bật pooling chỉ vì muốn “lazy connection”. Không dùng pool chia sẻ sai danh tính khi mỗi request bind bằng credential khác nhau.

**Observation:** ở các phiên bản hỗ trợ `ObservationContextSource`, context được bọc để ghi thời gian và trace của các thao tác directory. Wrapper giúp quan sát latency, lỗi và những vị trí gọi LDAP chậm. Đây là công cụ đo đạc; nó không tự thực hiện retry, caching, hay trì hoãn tạo bean.

| Nhu cầu | Cơ chế phù hợp để xem xét | Điều phải kiểm chứng |
| --- | --- | --- |
| Chỉ tạo bean khi tính năng được sử dụng | `@Lazy`, `ObjectProvider` | Dependency graph, startup behavior |
| Nhiều thao tác phải giữ cùng context | `SingleContextSource` trong một callback | Cleanup, session scope, hành vi provider |
| Nhóm ghi cần quản lý rollback bù trừ | Transaction-aware proxy + manager | Ràng buộc rollback và failure modes |
| Giảm chi phí cấp phát kết nối lặp lại | Pooling chuyên dụng | Pool validation, TLS, credentials, timeout |
| Muốn trace/metric thao tác LDAP | Observation wrapper nếu có hỗ trợ | Phiên bản, dữ liệu nhạy cảm trong metric |
| Yêu cầu truy vấn nhanh hơn | Index, filter, base/scope và đo đạc | Hiệu năng máy chủ, không tự suy ra từ proxy |

Trong một hệ thống thực tế, nhiều wrapper có thể được phối hợp. **Thứ tự bọc** ảnh hưởng context nào được đưa vào template, manager hoặc pool; cần áp dụng hướng dẫn của từng thành phần và test lifecycle sau khi cấu hình. Đừng tự suy ra mọi thứ tự proxy đều tương đương.

## 9. Kết nối an toàn và thời điểm phát hiện lỗi

Với Spring Boot, cấu hình cơ bản có thể đưa các giá trị môi trường vào `application.yml`:

```yaml
spring:
  ldap:
    urls: ${LDAP_URL:ldaps://ldap.example.org:636}
    base: ${LDAP_BASE:dc=example,dc=org}
    username: ${LDAP_BIND_DN}
    password: ${LDAP_BIND_PASSWORD}
```

Những giá trị trên là ví dụ; không ghi mật khẩu thật vào file. Dùng LDAPS hoặc StartTLS được cấu hình với chứng chỉ tin cậy và xác minh hostname phù hợp. Bean lazy hay proxy **không làm thay đổi yêu cầu bảo mật**:

- **ACL phía LDAP server** vẫn quyết định tài khoản bind được làm gì.
- **TLS** cần được bật/kiểm chứng; trì hoãn tạo context không giải quyết cấu hình chứng chỉ sai.
- **Timeout** của kết nối và đọc dữ liệu cần được thiết lập theo JNDI provider/thư viện đang dùng; một proxy lazy không tạo timeout tự động.
- **Không ghi log credential hoặc toàn bộ DN/filter nhạy cảm** khi bật tracing/observability.
- **Health/readiness:** nếu directory là dependency bắt buộc, nên có cách kiểm tra kết nối bằng bind/read hợp lệ trước khi service nhận traffic; nếu directory tùy chọn, phản hồi lỗi truy cập feature rõ ràng khi context được tạo muộn.

Phân biệt lỗi theo thời điểm:

| Thời điểm | Ví dụ lỗi | Cách hiểu |
| --- | --- | --- |
| Tạo bean/đọc properties | Sai kiểu cấu hình, thiếu bean, URL không hợp lệ | Lỗi cấu hình Spring |
| Lần đầu gọi proxy lazy | Dependency đích không tạo được | Lỗi bị hoãn tới lúc sử dụng |
| Lấy `DirContext` / bind | TLS handshake, sai credential, không tới server | Lỗi xác thực hoặc kết nối LDAP |
| Thực hiện search/modify | ACL, schema, timeout, referral, server limit | Lỗi truy vấn hoặc dữ liệu |
| Trả context về pool/cleanup | Context lỗi, pool bị đóng, tài nguyên hết hạn | Lỗi vòng đời tài nguyên |

Không bắt mọi exception rồi trả “không tìm thấy người dùng”: một lỗi LDAP chưa hoàn tất không chứng minh entry không tồn tại. Tầng tích hợp cần phản ánh sự cố tới ứng dụng với chính sách retry, fallback hoặc báo lỗi tương ứng.

## 10. Kiểm thử proxy và lazy context

Khi kiểm thử, nên tách những điều sau thành tiêu chí riêng:

1. **Lazy bean:** bean target có bị tạo lúc startup không, hay chỉ sau lần gọi đầu?
2. **Lazy dependency:** service nhận proxy có gọi được method và resolve đúng target không?
3. **Context acquisition:** mỗi thao tác thường gọi `getReadOnlyContext()` hoặc `getReadWriteContext()` đúng mục đích không?
4. **Cleanup:** trong đường thành công và đường lỗi, context được đóng/trả về pool như kỳ vọng không?
5. **Proxy wrapping:** template đang dùng context source proxy đúng bean, transaction manager đang nhận target đúng bean?
6. **Hạ tầng thực:** LDAP down, chứng chỉ sai, credential bị thu hồi, timeout và ACL có được biểu diễn bằng lỗi hợp lý không?

### 10.1. Unit test vòng đời context khi dùng `LdapTemplate`

Với Mockito và JUnit 5, có thể xác minh hành vi lấy/đóng context ở một thao tác đọc riêng:

```java
import static org.mockito.Mockito.*;

import javax.naming.directory.DirContext;

import org.junit.jupiter.api.Test;
import org.springframework.ldap.core.ContextSource;
import org.springframework.ldap.core.LdapTemplate;

class LdapTemplateContextLifecycleTest {
    @Test
    void closesContextAfterReadOnlyOperation() throws Exception {
        ContextSource source = mock(ContextSource.class);
        DirContext context = mock(DirContext.class);
        when(source.getReadOnlyContext()).thenReturn(context);

        LdapTemplate template = new LdapTemplate(source);
        template.executeReadOnly(ctx -> {
            ctx.getAttributes("uid=lan,ou=people");
            return null;
        });

        verify(source, times(1)).getReadOnlyContext();
        verify(context, times(1)).close();
    }
}
```

Test này kiểm tra **đường gọi Java** và callback của `LdapTemplate`; nó không chứng minh server LDAP thực đã nhận request, cũng không chứng minh pool đã đóng socket. Nếu source là wrapper pooling hoặc transaction-aware, ý nghĩa `close()` có thể khác với source thuần.

### 10.2. Integration test cần môi trường đại diện

Trên LDAP server thử nghiệm hoặc embedded LDAP có schema phù hợp, nên kiểm tra:

- Đúng `ContextSource.base`: tên `uid=lan,ou=people` trỏ tới đúng DN đầy đủ.
- Truy vấn đọc thành công với bind account chỉ có quyền cần thiết.
- Kết nối sai TLS/credential trả lỗi rõ ràng; bật `@Lazy` không làm ứng dụng báo nhầm thành công.
- Các thao tác đồng thời không dùng chung context có trạng thái ngoài phạm vi được thiết kế.
- Khi pool được bật, context bị lỗi được loại bỏ/kiểm tra theo chính sách thực tế.
- Khi dùng transaction-aware proxy, tình huống rollback được kiểm thử với giới hạn “compensating”, không giả định atomic server-side.
- Nếu dùng `SingleContextSource` cho nhiều trang kết quả, xác minh dữ liệu đầy đủ và context được giải phóng khi callback kết thúc.

Kiểm thử thêm một tình huống đặc biệt: **LDAP server không hoạt động tại startup nhưng hoạt động lại trước request đầu tiên**. Nếu cấu hình lazy, ứng dụng có thể khởi động nhưng cần kiểm chứng request đầu tiên có kết nối lại đúng không. Ngược lại, nếu directory là bắt buộc, cần xác định có chấp nhận startup trong trạng thái chưa sẵn sàng hay không.

## 11. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| Đã khai báo `@Lazy` nên chắc chắn chưa có kết nối LDAP nào | Bean/proxy được resolve lazy; kết nối thực tế tùy provider và hoạt động của các bean khác |
| Proxy `ContextSource` nào cũng trì hoãn tạo bean | Proxy LDAP chủ yếu bọc việc lấy/sử dụng context, có mục đích riêng |
| `getReadOnlyContext()` bảo đảm server từ chối mọi lệnh ghi | Chỉ LDAP server và ACL mới là ranh giới phân quyền đáng tin cậy |
| `LdapTemplate` là singleton nên dùng đúng một `DirContext` singleton | Template có thể lấy và đóng context theo từng thao tác; pool/wrapper thay đổi chính sách |
| `close()` luôn đóng socket vật lý ngay | Proxy/pool có thể chặn `close()` hoặc trả tài nguyên về pool |
| `SingleContextSource` đồng nghĩa pooling | Nó giữ một context trong callback; pool quản lý nhiều context cho nhiều lượt mượn |
| Transaction-aware proxy bảo đảm rollback ACID | Cơ chế bù trừ có giới hạn, nhất là khi kết nối hỏng |
| `@Lazy` làm LDAP chạy nhanh hơn | Nó đổi thời điểm khởi tạo, không tự tối ưu filter, index hay mạng |
| Bật proxy/lazy có thể bỏ qua timeout, TLS hoặc credentials | Các ràng buộc kết nối và bảo mật vẫn cần cấu hình |
| Unit test mock context chứng minh tích hợp LDAP thật đã đúng | Test tích hợp riêng mới kiểm chứng bind, schema, ACL và TLS thực tế |

## 12. Bài thực hành tự kiểm tra

Giả sử ứng dụng có `LdapTemplate` dùng `ContextSource.base = "dc=example,dc=org"`. Directory chứa:

```ldif
dn: uid=lan,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: lan
cn: Lan Nguyen
sn: Nguyen
```

**Câu hỏi:**

1. Nếu service được tạo bằng `@Lazy LdapTemplate` tại constructor injection, có thể khẳng định bean `LdapTemplate` chưa được tạo ở toàn ứng dụng không?
2. `ContextSource` cung cấp loại object nào cho `LdapTemplate` thao tác LDAP?
3. Vì sao `TransactionAwareContextSourceProxy` không tương đương với `@Lazy`?
4. Nếu hai bước của paged results phải chạy trên cùng kết nối, wrapper nào là một lựa chọn để tìm hiểu?
5. Tại sao không nên giữ một `DirContext` duy nhất trong field singleton dùng cho tất cả request?
6. Một unit test xác minh `DirContext.close()` được gọi có chứng minh TCP connection đã đóng không?
7. Nếu LDAP là dependency bắt buộc cho mọi request, có nên trì hoãn mọi lỗi kết nối đến request đầu tiên không?
8. Trong ví dụ này, muốn `lookup` Lan qua template đã có base, DN tương đối nên là gì?

**Đáp án và giải thích:**

1. Không. `@Lazy` ở injection point tạo proxy resolve dependency cho **chỗ injection đó**; một bean khác có thể đã khiến target được tạo trước.
2. `DirContext` của JNDI, có thể đã được bọc/proxy theo cấu hình nguồn.
3. Transaction-aware proxy can thiệp vào ngữ cảnh giao dịch/vòng đời context, còn `@Lazy` liên quan đến thời điểm resolve/khởi tạo bean.
4. `SingleContextSource` với callback dùng một context; cần kiểm thử cách server xử lý cookie và cleanup.
5. Context có trạng thái, vòng đời, timeout và có thể không phù hợp để chia sẻ giữa các thread; hãy để template/pool quản lý đúng phạm vi.
6. Không. `close()` có thể được wrapper/pool diễn giải là “trả context”, và mock không có socket thật.
7. Tùy yêu cầu vận hành; hệ thống phụ thuộc LDAP hoàn toàn thường cần readiness check hoặc fail-fast rõ ràng. Không nên dùng lazy như cách che giấu outage.
8. `uid=lan,ou=people`. Phần `dc=example,dc=org` đã thuộc base context của `ContextSource`.

## 13. Tổng kết và tài liệu tham khảo

**ContextSource proxy** là một lớp giữ interface `ContextSource` để điều chỉnh cách cấp, bọc và giải phóng `DirContext`. Mỗi loại wrapper có mục tiêu riêng: transaction bù trừ, giữ một context cho một nhóm thao tác, pooling hoặc observation. **Lazy initialization** của Spring là cơ chế riêng ở tầng IoC để trì hoãn khởi tạo/resolve bean. Còn thời điểm kết nối LDAP thật phụ thuộc provider, cấu hình và lúc ứng dụng yêu cầu thao tác.

Khi cấu hình Spring LDAP, hãy chọn cơ chế dựa trên mục tiêu cụ thể, quản lý đúng lifecycle của `DirContext`, kiểm tra TLS/ACL/timeout và test cả hành vi khi LDAP unavailable. Kết hợp `ContextSource` với `LdapTemplate` hoặc `LdapClient` giúp giữ phần JNDI và kết nối ở tầng tích hợp, trong khi nghiệp vụ chỉ nhìn thấy các chức năng thư mục cần thiết.

Tài liệu chính thức:

- [Spring LDAP — ContextSource API](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/core/ContextSource.html): contract cấp context cho các thao tác LDAP.
- [Spring LDAP — LdapTemplate API](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/core/LdapTemplate.html): lifecycle, tìm kiếm, đóng context và exception translation.
- [Spring LDAP — TransactionAwareContextSourceProxy](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/transaction/compensating/manager/TransactionAwareContextSourceProxy.html): proxy tích hợp transaction bù trừ.
- [Spring LDAP — SingleContextSource](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/core/support/SingleContextSource.html): giữ một context cho callback, hữu ích trong paged results.
- [Spring LDAP — Pooling Support](https://docs.spring.io/spring-ldap/reference/pooling.html): pool context, validation và hạn chế triển khai.
- [Spring LDAP — Observability Support](https://docs.spring.io/spring-ldap/reference/observability.html): observation wrapper và metric.
- [Spring Framework — Lazy-initialized Beans](https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-lazy-init.html): chính sách khởi tạo bean lazy.
- [Spring Framework — `@Lazy` API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/annotation/Lazy.html): lazy-resolution proxy tại injection point.
