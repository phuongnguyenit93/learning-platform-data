# Kiểm tra khả năng chia sẻ Template và giới hạn chia sẻ context giữa các luồng

Trong ứng dụng Spring Data LDAP, **LdapTemplate** thường là một Spring bean dùng chung cho nhiều request. Khi lưu lượng tăng, nhiều thread có thể cùng gọi repository hoặc các method như **search**, **lookup** và **modifyAttributes**. Cần phân biệt hai câu hỏi: có thể chia sẻ Template không, và có thể chia sẻ **DirContext** không?

**LdapTemplate** giữ cấu hình và ủy thác việc lấy/đóng context cho **ContextSource**; nó phù hợp làm bean dùng chung sau khi cấu hình hoàn tất. **DirContext/LdapContext** là phiên làm việc JNDI cụ thể với directory, không được đảm bảo an toàn khi nhiều thread thao tác đồng thời. Mỗi thao tác độc lập cần context có vòng đời riêng.

Bài thuộc chương **Kết nối** của module **SPRING_DATA_LDAP**. Nội dung trình bày thread-safety của Template, ContextSource, DirContext, NamingEnumeration, connection pool, SingleContextSource, transaction-aware context, thread-local state, asynchronous execution và cách kiểm thử cạnh tranh giữa các luồng.

> **Quy tắc thực hành:** Chia sẻ LdapTemplate và ContextSource đã cấu hình; không giữ DirContext, LdapContext, NamingEnumeration hoặc mutable DirContextOperations trong field singleton để nhiều thread dùng chung.

## 1. Phân biệt Template, ContextSource và DirContext

| Thành phần | Trách nhiệm | Cách sử dụng đa luồng |
| --- | --- | --- |
| **LdapTemplate** | API search, lookup, bind, modify, rename, unbind; quản lý vòng đời context/enumeration | Bean singleton dùng chung sau cấu hình |
| **ContextSource** | Tạo hoặc cấp read-only/read-write/authenticated DirContext | Bean dùng chung; cấu hình pool và authentication cẩn thận |
| **DirContext / LdapContext** | Thực hiện thao tác JNDI trên một context/session cụ thể | Giữ trong phạm vi thao tác/callback; không chia sẻ đồng thời |
| **NamingEnumeration** | Duyệt kết quả do Context tạo ra | Duyệt và đóng trong cùng phạm vi sở hữu context |
| **DirContextOperations** | Giữ DN, attributes và modification đang chuẩn bị | Không chia sẻ một instance mutable giữa request/thread |

~~~mermaid
flowchart TD
    A["Thread HTTP 1"] --> T["Singleton LdapTemplate"]
    B["Thread HTTP 2"] --> T
    C["Worker thread 3"] --> T
    T --> S["ContextSource"]
    S --> P["Pool / Context factory"]
    P --> C1["DirContext A"]
    P --> C2["DirContext B"]
    P --> C3["DirContext C"]
    C1 --> L["LDAP server"]
    C2 --> L
    C3 --> L
~~~

Các thread có thể gọi cùng Template; ContextSource cấp context phù hợp cho từng lần thao tác. Khi operation kết thúc, Template đóng context hoặc trả context về pool qua wrapper.

## 2. Vì sao LdapTemplate có thể dùng chung?

**LdapTemplate** gom các bước lấy context, chạy LDAP operation, duyệt NamingEnumeration, dịch NamingException và đóng resource. API giúp ứng dụng không phải tự mở một context rồi tự đóng sau mỗi method search/lookup/modify.

Ví dụ cấu hình bean:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.core.support.LdapContextSource;

@Configuration
class LdapConfiguration {
    @Bean
    LdapContextSource contextSource() {
        LdapContextSource source = new LdapContextSource();
        source.setUrl("ldaps://ldap.lab.example:636");
        source.setBase("dc=lab,dc=example");
        source.setUserDn("uid=app-reader,ou=services,dc=lab,dc=example");
        source.setPassword(System.getenv("LDAP_BIND_PASSWORD"));
        return source;
    }

    @Bean
    LdapTemplate ldapTemplate(LdapContextSource contextSource) {
        return new LdapTemplate(contextSource);
    }
}
~~~

Spring quản lý một bean LdapTemplate và có thể inject vào nhiều service/repository. Sau khi application context khởi tạo xong, các thread gọi method Template độc lập.

**Điều kiện quan trọng:** Không sửa cấu hình dùng chung sau khi bean bắt đầu phục vụ request. Tránh thay đổi ContextSource, URL, base DN, credentials, exception flags hoặc converter giữa các thao tác. Nếu cần đổi endpoint/credentials, dùng lifecycle/configuration rõ ràng thay vì mutate bean đang được nhiều thread sử dụng.

### 2.1. Ví dụ service stateless

~~~java
import java.util.List;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.stereotype.Service;
import static org.springframework.ldap.query.LdapQueryBuilder.query;

@Service
public class DirectoryLookupService {
    private final LdapTemplate ldapTemplate;

    public DirectoryLookupService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<String> findUidsBySurname(String surname) {
        return ldapTemplate.search(
            query().base("ou=people")
                .where("objectClass").is("inetOrgPerson")
                .and("sn").is(surname),
            attrs -> (String) attrs.get("uid").get()
        );
    }
}
~~~

Service không lưu context, enumeration hoặc kết quả mutable làm state dùng chung. Mỗi lời gọi tạo query riêng và trả danh sách riêng.

### 2.2. Không giữ context trong singleton

~~~java
// Không dùng: một DirContext duy nhất được chia sẻ giữa request.
@Service
class UnsafeDirectoryService {
    private final DirContext sharedContext;

    UnsafeDirectoryService(DirContext sharedContext) {
        this.sharedContext = sharedContext;
    }
}
~~~

Nếu cần truy cập context trực tiếp, lấy context theo một operation scope và đóng/return đúng cách.

## 3. DirContext không được đảm bảo thread-safe

JNDI Context/DirContext API không đảm bảo một instance được đồng bộ khi nhiều thread truy cập đồng thời. Java SE API nêu rõ các thread dùng chung một Context instance phải tự đồng bộ; các thread thao tác trên những Context instance khác nhau thì không cần khóa chung theo hợp đồng đó.

JDK LDAP provider cũng được tối ưu cho truy cập đơn luồng trên cùng context. Một context có thể giữ trạng thái xác thực, environment, referral, controls hoặc kết quả operation. Nếu hai thread dùng cùng instance, chúng có thể xen kẽ thao tác, thay đổi request controls hoặc đóng context khi thread kia vẫn đang sử dụng.

~~~java
DirContext context = contextSource.getReadOnlyContext();

// Thread A
NamingEnumeration<SearchResult> resultsA =
    context.search("ou=people", "(uid=linh)", controls);

// Thread B dùng cùng context trước khi A duyệt xong
NamingEnumeration<SearchResult> resultsB =
    context.search("ou=groups", "(cn=developers)", controls);
~~~

Đây là ví dụ lỗi sở hữu context, không phải code production. Kết quả có thể phụ thuộc provider và timing: NamingException, enumeration sai trạng thái, context bị đóng sớm hoặc lỗi khó tái hiện.

### 3.1. Khác context không nhất thiết là khác TCP connection

Hai thread dùng hai DirContext riêng có thể được provider/pool triển khai trên connection vật lý riêng, hoặc nhiều context có thể chia sẻ một số tài nguyên bên dưới theo implementation. Điều cần bảo đảm ở tầng ứng dụng là mỗi thread sở hữu context instance riêng.

Không cần tự khóa toàn bộ LDAP access chỉ vì các thread cùng kết nối một server. Khóa toàn cục thường làm giảm throughput; hãy để Template/ContextSource cấp context riêng và dùng pool nếu cần tái sử dụng connection.

### 3.2. Context operation chưa kết thúc khi enumeration còn mở

JNDI xác định một operation trả về NamingEnumeration chưa được xem là hoàn tất cho tới khi enumeration được sử dụng xong; việc theo referral phát sinh từ operation cũng nằm trong phạm vi đó. Do vậy:

- Không đóng context sau khi lấy enumeration nhưng trước khi duyệt hết.
- Không trả enumeration ra khỏi callback rồi để thread khác duyệt.
- Đóng enumeration trong finally hoặc try-with-resources nếu kiểu cụ thể hỗ trợ AutoCloseable.
- Để LdapTemplate.search quản lý enumeration khi dùng API search thông thường.

## 4. ContextSource cấp context theo từng nhu cầu

**ContextSource** chịu trách nhiệm cấu hình và tạo/cấp DirContext. API cốt lõi gồm:

| Method | Mục đích |
| --- | --- |
| **getReadOnlyContext()** | Lấy context cho thao tác đọc |
| **getReadWriteContext()** | Lấy context cho thao tác ghi |
| **getContext(principal, credentials)** | Tạo context xác thực bằng principal/credentials cụ thể |

Template thường gọi method phù hợp rồi quản lý việc đóng context. Khi dùng trực tiếp ContextSource, code ứng dụng chịu trách nhiệm đóng context trong mọi đường đi, kể cả khi exception xảy ra.

Các implementation ContextSource chuẩn của Spring LDAP được thiết kế để phục vụ nhiều lần lấy context. Nếu tự viết ContextSource, không lưu một DirContext duy nhất trong field rồi trả lại cho mọi caller; implementation phải tạo/cấp context theo vòng đời độc lập và xử lý đóng/return đúng cách.

### 4.1. Dùng executeReadOnly/executeReadWrite khi cần JNDI API

Nếu LdapTemplate chưa có method phù hợp và cần thao tác trực tiếp trên DirContext, có thể dùng callback:

~~~java
import javax.naming.directory.Attributes;
import org.springframework.ldap.core.LdapTemplate;

public Attributes readAttributes(
        LdapTemplate ldapTemplate,
        String relativeDn) {
    return ldapTemplate.executeReadOnly(
        ctx -> ctx.getAttributes(relativeDn)
    );
}
~~~

Template lấy context read-only, chạy callback, dịch exception và đóng/return context sau khi callback kết thúc. Callback không được trả về chính DirContext, NamingEnumeration hoặc object còn phụ thuộc vào context để dùng ở thread khác.

Ví dụ ghi:

~~~java
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;

public void updateDescription(
        LdapTemplate ldapTemplate,
        String relativeDn,
        String description) {
    ldapTemplate.executeReadWrite(ctx -> {
        ModificationItem[] mods = {
            new ModificationItem(
                DirContext.REPLACE_ATTRIBUTE,
                new BasicAttribute("description", description)
            )
        };
        ctx.modifyAttributes(relativeDn, mods);
        return null;
    });
}
~~~

**executeReadOnly** và **executeReadWrite** phù hợp với trường hợp đặc biệt; Javadoc không xem executeReadOnly là API thay thế cho search. Với search, ưu tiên method search của Template để Template tự quản lý enumeration.

## 5. NamingEnumeration và object trả về từ callback

**NamingEnumeration** là resource có thể còn phụ thuộc context và network. Không lưu nó trong field, cache hoặc đưa vào CompletableFuture để một thread khác duyệt sau khi callback đã kết thúc.

~~~java
// Không làm:
NamingEnumeration<SearchResult> findLater() {
    return ldapTemplate.executeReadOnly(
        ctx -> ctx.search("ou=people", "(objectClass=person)")
    );
}
~~~

Callback kết thúc khiến Template có thể đóng context; enumeration trả ra ngoài khi đó không còn hợp lệ.

Thay vào đó, materialize dữ liệu trong callback và trả về object Java độc lập:

~~~java
import java.util.ArrayList;
import java.util.List;
import javax.naming.NamingEnumeration;
import javax.naming.directory.SearchControls;
import javax.naming.directory.SearchResult;

List<String> readCnValues(LdapTemplate ldapTemplate) {
    return ldapTemplate.executeReadOnly(ctx -> {
        List<String> values = new ArrayList<>();
        SearchControls controls = new SearchControls();
        controls.setSearchScope(SearchControls.SUBTREE_SCOPE);
        controls.setReturningAttributes(new String[]{"cn"});

        NamingEnumeration<SearchResult> rows = ctx.search(
            "ou=people", "(objectClass=inetOrgPerson)", controls
        );
        try {
            while (rows.hasMore()) {
                SearchResult row = rows.next();
                Object cn = row.getAttributes().get("cn").get();
                values.add(String.valueOf(cn));
            }
        } finally {
            rows.close();
        }
        return values;
    });
}
~~~

Ví dụ đóng enumeration bằng finally để tương thích với các provider JNDI khác nhau. Kết quả List<String> không còn phụ thuộc context sau khi callback kết thúc.

## 6. DirContextOperations cũng có thể là mutable state

**DirContextOperations/DirContextAdapter** giữ DN, attributes và các thay đổi đang chờ gửi. Đây là đối tượng mutable: gọi setAttributeValue, addAttributeValue hoặc removeAttributeValue có thể thay đổi state bên trong.

~~~java
DirContextOperations entry =
    ldapTemplate.lookupContext("uid=linh,ou=people");
entry.setAttributeValue("description", "Updated by request A");
ldapTemplate.modifyAttributes(entry);
~~~

Không đưa entry vào field singleton rồi cho request A và request B sửa cùng một instance. Cả hai có thể ghi đè giá trị hoặc tập modification của nhau. Tạo instance mới bằng lookupContext trong từng operation, sửa và gửi trong cùng luồng nghiệp vụ.

### 6.1. Không chia sẻ entity đang được sửa

Một entity ODM như DirectoryPerson cũng có thể là mutable. Nếu hai thread cùng nhận một Java object rồi sửa field mail/description, lỗi data race thuộc ứng dụng Java, trước khi LDAP operation diễn ra. Dùng object riêng cho từng request, immutable DTO hoặc cơ chế đồng bộ rõ ràng.

### 6.2. Tránh giữ reference của Attributes từ context lâu dài

Khi lấy Attributes hoặc Attribute từ JNDI, hãy chuyển dữ liệu cần thiết sang DTO/collection của ứng dụng trong scope hiện tại. Không giả định mọi implementation trả object snapshot hoàn toàn độc lập hoặc thread-safe.

## 7. Chia sẻ ContextSource và connection pooling

Khi số lượng LDAP operation lớn, tạo kết nối mới cho mỗi lần có thể tốn chi phí. Spring LDAP cung cấp pool theo từng ContextSource, cho phép tái sử dụng DirContext và cấu hình validation.

Các điểm quan trọng:

- Pool có thể quản lý read-only và read-write context riêng.
- **max-active** giới hạn số context active theo loại.
- **max-total** giới hạn tổng context active theo pool.
- **max-idle** và **min-idle** điều khiển số context idle.
- Validation có thể kiểm tra context khi borrow/return hoặc khi idle.
- Context được mượn phải được đóng đúng cách để wrapper trả nó về pool.

Ví dụ XML cấu hình pool (cú pháp theo Spring LDAP XML namespace):

~~~xml
<ldap:context-source
    url="ldaps://ldap.lab.example:636"
    base="dc=lab,dc=example"
    username="uid=app-reader,ou=services,dc=lab,dc=example"
    password="${LDAP_BIND_PASSWORD}">
    <ldap:pooling
        max-active="16"
        max-total="32"
        max-idle="8"
        min-idle="2"
        test-on-borrow="true"
        test-while-idle="true" />
</ldap:context-source>
~~~

Đây là ví dụ cấu hình minh họa; cần thêm namespace/schema phù hợp và dependency pool tương thích với phiên bản Spring LDAP đang dùng. Trong Spring LDAP mới, package pool và Commons Pool generation có thể khác phiên bản cũ; hãy dùng API tương ứng version BOM của dự án.

### 7.1. Pool không có nghĩa một context được dùng đồng thời

Pool cấp một context cho một caller tại một thời điểm. Sau khi operation hoàn tất và context được đóng qua wrapper, context mới có thể được cấp cho caller khác. Không giữ reference tới context đã đóng/trả pool, vì pool có thể giao chính instance đó cho thread khác.

### 7.2. Pool và custom AuthenticationSource

Spring LDAP ghi rõ một giới hạn quan trọng: **PoolingContextSource** giả định các context lấy qua getReadOnlyContext có cùng environment với nhau, và tương tự cho getReadWriteContext. Nếu gắn AuthenticationSource cung cấp credential theo từng thread/người dùng vào pool, pool có thể được tạo bằng credential của user đầu tiên; các yêu cầu sau có thể nhận context mang credential đó thay vì credential của thread yêu cầu.

Vì vậy **không dùng một pool chung kiểu service account để giả lập pool theo user identity**. Với xác thực theo credential người dùng, dùng luồng tạo context xác thực riêng được hỗ trợ (ví dụ getContext(principal, credentials)), kiểm tra hành vi của version cụ thể và không đưa context cá nhân vào pool dùng chung.

## 8. Connection pool, số thread và áp lực lên LDAP server

Thread pool của ứng dụng và LDAP connection pool là hai tài nguyên độc lập:

~~~text
HTTP executor: 100 worker threads
LDAP pool:      16 read-only + 8 read-write contexts
LDAP server:    giới hạn connection và search concurrency riêng
~~~

Khi 100 request cùng gọi LDAP, chỉ một phần có thể lấy context từ pool tại cùng thời điểm. Các request còn lại phải chờ, timeout hoặc bị từ chối tùy cấu hình pool. Tăng số worker thread không tự làm LDAP nhanh hơn; nó có thể chỉ làm số waiter và memory tăng.

### 8.1. Chọn pool size theo thời gian giữ context

Một phép ước lượng ban đầu theo Little's Law:

~~~text
Concurrent LDAP operations ≈ arrival rate × average context hold time

Ví dụ:
  40 LDAP operations/second × 0.10 second
  ≈ 4 context đang bận trung bình
~~~

Đây chỉ là ước lượng tải trung bình. Cần tính burst, percentile latency, retry, paged search, server capacity và số instance ứng dụng. Không đặt max-active bằng tổng HTTP worker một cách máy móc.

### 8.2. Quan sát pool

Theo dõi ít nhất:

- Số context active/idle theo read-only và read-write.
- Thời gian chờ borrow và số waiter.
- Thời gian giữ context và thời gian LDAP operation.
- Tỷ lệ context bị invalidated/validation failure.
- CommunicationException, timeout và server unavailable.
- Số LDAP connection thực tế trên từng node server.

Nếu pool cạn, xác định context bị giữ quá lâu, enumeration chưa đóng, callback block hoặc connection không được trả. Không chỉ tăng max-total trước khi tìm nguyên nhân.

## 9. SingleContextSource: giữ cùng connection trong một callback

Có những protocol flow cần dùng **cùng một LDAP context/connection qua nhiều operation liên tiếp**. Ví dụ điển hình là **paged results control**: response của trang trước trả một cookie; client gửi cookie đó trong request tiếp theo để lấy trang sau. Cookie thường gắn với cùng LDAP session/context mà server đã dùng để tạo nó.

Spring LDAP cung cấp **SingleContextSource.doWithSingleContext(...)** để thực hiện một callback bằng cùng một context được tạo từ ContextSource. Khi callback kết thúc, wrapper được dispose đúng vòng đời.

~~~java
import java.util.LinkedList;
import java.util.List;
import javax.naming.directory.SearchControls;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.ContextSource;
import org.springframework.ldap.control.PagedResultsControlExchangeDirContextProcessor;
import org.springframework.ldap.core.support.SingleContextSource;

List<String> readSeveralPages(ContextSource contextSource) {
    final int pageSize = 200;
    SearchControls controls = new SearchControls();
    controls.setSearchScope(SearchControls.SUBTREE_SCOPE);
    PagedResultsControlExchangeDirContextProcessor processor =
        new PagedResultsControlExchangeDirContextProcessor(pageSize);
    AttributesMapper<String> mapper = attrs ->
        (String) attrs.get("cn").get();

    return SingleContextSource.doWithSingleContext(
        contextSource,
        operations -> {
            List<String> names = new LinkedList<>();
            do {
                List<String> page = operations.search(
                    "ou=people",
                    "(&(objectClass=inetOrgPerson))",
                    controls,
                    mapper,
                    processor
                );
                names.addAll(page);
            } while (processor.hasMore());
            return names;
        }
    );
}
~~~

Ví dụ dùng đúng một processor cho một chuỗi paging và giữ tất cả request trang trong cùng callback. Cần kiểm tra server hỗ trợ paged results control; một số server có thể giới hạn page size hoặc không hỗ trợ control. Trong ứng dụng thật, mapper và SearchControls nên là biến cục bộ cho mỗi lần gọi.

### 9.1. Không biến SingleContextSource thành singleton context dùng chung

SingleContextSource phục vụ một luồng công việc cần giữ context trong một scope. Không tạo một instance toàn cục rồi chia sẻ context underlying giữa các request. Hai request paging độc lập cần hai scope riêng; không trộn cookie, processor hoặc result state giữa chúng.

Không trả **LdapOperations**/context wrapper hoặc processor còn gắn với context ra khỏi callback. Trả dữ liệu đã materialize như List, DTO hoặc kết quả immutable.

### 9.2. Processor có state cũng cần scope riêng

**PagedResultsControlExchangeDirContextProcessor** giữ cookie và trạng thái trang. Tạo processor mới cho mỗi chuỗi paging. Không dùng một processor mutable trong field singleton cho nhiều thread; cookie của request A có thể bị request B ghi đè.

## 10. Request controls và trạng thái gắn với LdapContext

Một số LDAP operation cần controls, ví dụ paged results, server-side sort, password policy hoặc assertion control. Với Spring LDAP, **DirContextProcessor** cho phép pre-process và post-process context quanh một search. Processor có thể đọc response control hoặc giữ trạng thái cần cho trang tiếp theo.

~~~java
public interface DirContextProcessor {
    void preProcess(DirContext ctx) throws NamingException;
    void postProcess(DirContext ctx) throws NamingException;
}
~~~

Khi dùng processor:

- Tạo processor riêng cho mỗi operation/chuỗi paging nếu processor có state.
- Không chia sẻ một LdapContext đang giữ request controls giữa các thread.
- Không để response cookie của request này được dùng cho request khác.
- Luôn thực hiện post-process và đóng resource theo API Template.
- Xác nhận server hỗ trợ control tương ứng; không giả định mọi LDAP server có cùng extension.

**LdapContext** có API quản lý request controls. Những controls gắn với context có thể ảnh hưởng operation tiếp theo trên cùng context. Đây là một lý do nữa để tránh dùng context toàn cục hoặc tự giữ context sau khi operation kết thúc.

## 11. Transaction và context gắn với thread

LDAP protocol cơ bản không định nghĩa transaction tương đương transaction SQL; LDAP server không cung cấp transaction tổng quát cho một chuỗi operation theo mô hình relational database. Spring LDAP có hỗ trợ **client-side compensating transactions** qua **ContextSourceTransactionManager**.

Trong transaction được cấu hình đúng, Spring LDAP:

- Ghi nhận trạng thái cần thiết trước các thao tác thay đổi.
- Giữ cùng một DirContext trong phạm vi transaction.
- Khi rollback, thực hiện các thao tác bù để cố gắng khôi phục trạng thái trước đó.
- Khi commit, kết thúc transaction scope và giải phóng context.

Đây là **compensation phía client**, không phải server-side atomic transaction. Rollback bù có thể thất bại nếu directory thay đổi đồng thời, server không còn kết nối hoặc thao tác phục hồi không còn hợp lệ.

### 11.1. Transaction-aware ContextSource

Template được cấu hình để dùng **TransactionAwareContextSourceProxy**, còn **ContextSourceTransactionManager** nhận ContextSource đích thực tế. Proxy làm cho DirContext được trả về nhận biết transaction: không đóng context giữa transaction và ghi lại các modification để có thể thực hiện compensation khi rollback.

Ví dụ wiring ở mức cấu hình:

~~~java
@Bean
ContextSource transactionAwareContextSource(
        ContextSource targetContextSource) {
    return new TransactionAwareContextSourceProxy(targetContextSource);
}

@Bean
PlatformTransactionManager ldapTransactionManager(
        ContextSource targetContextSource) {
    return new ContextSourceTransactionManager(targetContextSource);
}

@Bean
LdapTemplate ldapTemplate(
        @Qualifier("transactionAwareContextSource")
        ContextSource transactionAwareContextSource) {
    return new LdapTemplate(transactionAwareContextSource);
}
~~~

Đây là ví dụ wiring, cần import các type Spring LDAP transaction và Spring transaction tương ứng. Bean ContextSource đích phải được cấu hình trước; Template dùng proxy, còn transaction manager dùng ContextSource gốc. Nếu Template dùng ContextSource gốc thay vì proxy, các operation có thể không được transaction-aware như mong đợi.

Sơ đồ khái niệm:

~~~mermaid
sequenceDiagram
    participant T as Thread A
    participant M as ContextSourceTransactionManager
    participant P as TransactionAwareContextSourceProxy
    participant D as DirContext
    participant L as LDAP server
    T->>M: begin transaction
    M->>P: bind transaction resource
    P->>D: lấy context cho transaction
    T->>D: bind / modify / rename
    D->>L: LDAP operations
    T->>M: commit hoặc rollback
    M->>D: hoàn tất hoặc chạy compensation
    M->>P: giải phóng transaction resource
~~~

### 11.2. Transaction context không tự truyền sang thread khác

Transaction resource của Spring LDAP được gắn với thread thực thi transaction (qua transaction synchronization/resource holder). Nếu code bên trong transaction gọi **@Async**, **CompletableFuture.runAsync(...)** hoặc submit sang Executor, worker thread không tự động nhận transaction context của thread gọi.

Ví dụ không an toàn về ranh giới transaction:

~~~java
@Transactional("ldapTransactionManager")
public void updateDirectory() {
    ldapTemplate.modifyAttributes(...);

    CompletableFuture.runAsync(() -> {
        // Đây là thread khác; không mặc định thuộc transaction trên.
        ldapTemplate.modifyAttributes(...);
    });
}
~~~

Operation bất đồng bộ có thể chạy sau khi transaction ngoài đã commit/rollback. Nó cũng có thể mượn một context khác và không được compensation cùng transaction. Nếu cần tính nhất quán, thiết kế một workflow riêng: transaction scope đồng bộ, outbox/job hoặc compensation rõ ràng; không kỳ vọng ThreadLocal tự lan sang executor.

### 11.3. Transaction không phải mutex cho mọi thread

Một transaction giữ context của nó trong một luồng công việc; nó không khóa directory cho các transaction khác hoặc các client khác. LDAP server vẫn có thể nhận thay đổi từ ứng dụng khác trong lúc compensation transaction đang chạy. Thiết kế phải tính tới concurrent update và khả năng rollback bù không khôi phục được chính xác snapshot cũ.

## 12. ThreadLocal, SecurityContext và thông tin request

Một số framework lưu thông tin theo thread:

| State | Phạm vi phổ biến | Tự chuyển sang thread khác? |
| --- | --- | --- |
| Spring transaction resource | Thread hiện tại | Không |
| Spring SecurityContext | Theo SecurityContextHolder strategy | Không mặc định với executor tùy ý; cần wrapper/strategy phù hợp |
| MDC/logging context | Thread hiện tại | Không mặc định |
| Request attributes | Request thread | Không mặc định |
| LDAP DirContext | Context instance cụ thể | Không chia sẻ đồng thời |

Không dùng ThreadLocal để giữ một DirContext vô thời hạn. Thread pool tái sử dụng worker thread cho request khác; nếu context/credential không được dọn đúng, request sau có thể vô tình chạy dưới identity trước đó hoặc dùng state cũ.

Nếu cần truyền SecurityContext hoặc trace context sang worker, dùng cơ chế propagation được framework hỗ trợ. Chỉ truyền identity/authorization information cần thiết và để worker lấy context LDAP mới qua Template/ContextSource. Không truyền trực tiếp DirContext hoặc NamingEnumeration qua queue.

## 13. Asynchronous execution và parallel stream

Mỗi task async nên nhận dữ liệu bất biến (DN đã xác minh, query parameters, correlation ID) và tự gọi LdapTemplate. Không đóng gói context trong lambda.

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Executor;
import org.springframework.ldap.core.LdapTemplate;

CompletableFuture<PersonDto> loadPersonAsync(
        Executor executor,
        LdapTemplate ldapTemplate,
        String relativeDn) {
    return CompletableFuture.supplyAsync(
        () -> ldapTemplate.lookup(
            relativeDn,
            attrs -> new PersonDto(
                (String) attrs.get("uid").get(),
                (String) attrs.get("cn").get()
            )
        ),
        executor
    );
}
~~~

Mỗi lần lookup được Template quản lý context riêng. DTO được trả về không giữ JNDI resource. Ví dụ giả định **PersonDto** là immutable record/class có constructor tương ứng.

### 13.1. Parallel stream không tự làm LDAP an toàn hơn

~~~java
// Không chia sẻ một context giữa các phần tử của parallel stream.
names.parallelStream().forEach(name -> {
    ldapTemplate.lookup(name, mapper);
});
~~~

Mẫu này không chia sẻ context trực tiếp nếu mapper stateless và mỗi lookup đi qua Template, nhưng nó có thể tạo nhiều LDAP operation đồng thời ngoài dự kiến. Số thread của parallel stream thường không được thiết kế theo giới hạn pool LDAP/server. Ưu tiên Executor có giới hạn concurrency rõ ràng và theo dõi pool waiters.

### 13.2. Giới hạn concurrency trước khi chạm LDAP

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

ExecutorService ldapExecutor = new ThreadPoolExecutor(
    4, 8,
    30, TimeUnit.SECONDS,
    new ArrayBlockingQueue<>(100),
    new ThreadPoolExecutor.CallerRunsPolicy()
);
~~~

Ví dụ này giới hạn số task đồng thời và kích thước queue; giá trị 4/8/100 chỉ là minh họa. Cần tính cùng max-active của LDAP pool, số application replicas, server connection limits, latency và yêu cầu response time. Đóng executor khi application shutdown.

## 14. Thread-safe không có nghĩa nghiệp vụ không có race condition

Ngay cả khi mỗi thread có context riêng và dùng chung Template đúng cách, hai operation vẫn có thể cạnh tranh trên cùng một LDAP entry. Thread-safety của client không tạo transaction cho toàn bộ chuỗi nghiệp vụ.

Ví dụ read-modify-write:

~~~text
Entry ban đầu: description = "A"

Thread 1 đọc "A"
Thread 2 đọc "A"
Thread 1 ghi "B"
Thread 2 ghi "C"

Kết quả cuối: "C"
~~~

Không có lỗi chia sẻ object Java ở ví dụ này; đây là **lost update** ở cấp nghiệp vụ. Context riêng chỉ đảm bảo các request không dùng chung một phiên JNDI. Nó không ngăn một request ghi đè kết quả của request khác.

### 14.1. Một LDAP ModifyRequest và nhiều request là hai phạm vi khác nhau

LDAP server xử lý các modification trong **một ModifyRequest** như một operation trên một entry. Nhưng chuỗi gồm Search, kiểm tra business rule, rồi Modify là nhiều operation; một client khác có thể thay đổi entry giữa các bước đó.

~~~text
Search entry
  -> application evaluates current values
  -> Modify entry
~~~

Đừng xem chuỗi trên là transaction nguyên tử. Nếu nghiệp vụ cần kiểm tra trạng thái trước khi ghi, cân nhắc **assertion control** nếu server hỗ trợ, version attribute, lock nghiệp vụ hoặc thiết kế operation idempotent. Phải kiểm tra capability server và result code khi assertion không còn đúng.

### 14.2. Add cùng một DN đồng thời

Hai thread có thể cùng kiểm tra DN chưa tồn tại rồi cùng gọi Add. Một request thành công; request còn lại thường nhận **entryAlreadyExists (68)**. Đây là kết quả cạnh tranh bình thường ở directory, không phải lý do để dùng chung context hoặc khóa toàn bộ ứng dụng.

Ứng dụng cần xử lý duplicate theo semantics nghiệp vụ: đọc lại entry, xác minh nội dung có đúng đối tượng mong đợi hay không, rồi trả kết quả phù hợp. Không nuốt mọi lỗi 68 và báo thành công khi chưa xác minh.

### 14.3. Connection pool không phải khóa entry

Pool giới hạn số context/connection đồng thời và tái sử dụng resource. Nó không đảm bảo hai thread không sửa cùng một DN. Nếu cần tránh lost update, dùng cơ chế kiểm soát cạnh tranh của directory hoặc thiết kế domain phù hợp; tăng/giảm pool size không giải quyết tính nguyên tử nghiệp vụ.

## 15. Phân tách context theo identity và quyền truy cập

Trong nhiều hệ thống, ứng dụng dùng một **service account** cho các thao tác repository. Trong một số luồng, ứng dụng lại bind bằng credential của chính người dùng để xác thực hoặc thực hiện thao tác dưới quyền của họ. Hai trường hợp này không nên bị trộn trong cùng một context dùng chung.

| Trường hợp | Context phù hợp | Lưu ý |
| --- | --- | --- |
| Repository/service account | Read-only hoặc read-write context từ ContextSource cấu hình sẵn | Có thể pool theo từng loại context nếu environment/credential đồng nhất |
| Xác thực user | Context được tạo theo principal/password của user | Không cache hoặc chia sẻ context xác thực giữa user |
| Password change/user operation | Context/extended operation theo API và policy server | Dùng TLS/SASL protection và đúng quyền |
| Admin reset | Context với delegated admin identity tối thiểu | Không dùng context user hiện tại để reset người khác |

### 15.1. Không để credential người dùng rò qua pool

Pool thông thường giả định cùng loại context có cùng environment và credential. Nếu mỗi request dùng một principal/password khác nhau, không thể mặc định lấy context từ pool rồi thay credential bằng cách sửa environment trên context đang mượn. Hành vi này có thể gây nhầm identity hoặc trả context về pool với state không mong đợi.

Với per-user authentication, dùng API tạo context theo credential cụ thể, xử lý/đóng ngay sau xác thực và không lưu password hoặc context trong singleton. Kiểm tra kỹ giới hạn pooling được tài liệu hóa cho phiên bản Spring LDAP đang chạy.

### 15.2. Không dựa vào ThreadLocal để chọn LDAP user

Nếu một AuthenticationSource đọc principal từ ThreadLocal, cần bảo đảm nó được thiết lập và dọn trong cùng request thread. Khi chạy async, worker thread có thể không có principal đó; nếu pool vẫn được dùng, context có thể không mang identity mà code mong đợi. Ưu tiên truyền identity đã xác minh một cách tường minh tới service tạo context phù hợp.

## 16. Anti-pattern thường gặp

| Anti-pattern | Rủi ro | Cách sửa |
| --- | --- | --- |
| Giữ một DirContext trong field singleton | Concurrent access, close sớm, lẫn controls | Dùng LdapTemplate hoặc context riêng theo callback |
| Giữ NamingEnumeration sau khi callback kết thúc | Enumeration phụ thuộc context đã đóng | Duyệt hết trong scope và materialize kết quả |
| Trả DirContext từ executeReadOnly | Template đóng/return context sau callback | Trả DTO/list, không trả context |
| Dùng một DirContextOperations mutable cho nhiều request | Modification state bị trộn | Lookup instance mới cho từng operation |
| Dùng một paging processor cho mọi request | Cookie/state trang bị ghi đè | Tạo processor mới theo chuỗi paging |
| SingleContextSource singleton giữ một context chung | Nhiều request chia sẻ underlying context | Dùng doWithSingleContext cho từng callback |
| Pool context theo credential user nhưng không phân biệt identity | Request có thể dùng credential của user khác | Context xác thực riêng; không pool per-user theo cấu hình đồng nhất |
| Chạy async và mong transaction tự truyền | Worker không thuộc transaction gốc | Thiết kế transaction scope đồng bộ hoặc workflow riêng |
| Tăng HTTP thread pool để chữa pool cạn | Tăng waiter và áp lực lên LDAP server | Đo context hold time, giới hạn concurrency |
| Nghĩ thread-safe đồng nghĩa không lost update | Ghi đè dữ liệu nghiệp vụ | Dùng assertion/version/idempotency phù hợp |

## 17. Kiểm thử đồng thời với directory thật

Unit test mock LdapTemplate có thể xác minh service gọi đúng method, nhưng không chứng minh được context pooling, JNDI concurrency, controls hoặc LDAP server behavior. Cần integration test với directory riêng (ví dụ OpenLDAP/UnboundID test server phù hợp với stack) và fixture có thể reset.

### 17.1. Test nhiều thread dùng chung LdapTemplate

~~~java
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.ldap.core.LdapTemplate;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest
class LdapTemplateConcurrencyIT {
    @Autowired
    LdapTemplate ldapTemplate;

    @Test
    void manyThreadsCanUseTheSameTemplate() throws Exception {
        ExecutorService executor = Executors.newFixedThreadPool(8);
        try {
            List<Callable<String>> tasks = java.util.stream.IntStream
                .range(0, 32)
                .mapToObj(i -> (Callable<String>) () ->
                    ldapTemplate.lookup(
                        "uid=linh,ou=people",
                        attrs -> (String) attrs.get("uid").get()
                    )
                )
                .toList();

            List<Future<String>> results = executor.invokeAll(tasks);
            for (Future<String> result : results) {
                assertEquals("linh", result.get());
            }
        } finally {
            executor.shutdownNow();
        }
    }
}
~~~

Đây là mẫu integration test; cần fixture DN đã tồn tại, Spring Boot LDAP config và JUnit dependency. Test dùng cùng singleton Template nhưng mỗi lời gọi Template tự quản lý context của operation. Nếu project dùng Java trước 16, thay **Stream.toList()** bằng **Collectors.toList()**.

### 17.2. Test giới hạn pool

Thiết lập pool có max-active nhỏ trong môi trường test, sau đó tạo nhiều task đồng thời. Đo:

- Thời gian borrow context.
- Số task chờ.
- Số operation đang chạy.
- Kết quả khi pool cạn hoặc timeout.
- Context có được trả về sau exception hay không.

Không khẳng định một con số latency cố định; test nên xác minh hành vi và không rò context sau khi mọi task hoàn tất.

### 17.3. Test xác nhận context không bị chia sẻ

Nếu có code callback cần lấy context trực tiếp, có thể instrument ContextSource trong test để ghi nhận identity của context theo operation. Xác minh các callback đồng thời không thao tác trên cùng một context instance. Không chỉ so sánh TCP connection ID vì provider/pool có thể tái sử dụng tài nguyên vật lý dưới nhiều context instance.

### 17.4. Test paging dùng cùng context

Chuẩn bị đủ dữ liệu vượt page size và gọi paging qua **SingleContextSource.doWithSingleContext**. Xác minh:

- Tổng số entry nhận được đúng fixture.
- Không có trang bị lặp hoặc bỏ sót.
- Processor/cookie được tạo mới cho từng lần gọi.
- Hai request paging đồng thời không dùng chung processor/cookie.

### 17.5. Test transaction không lan sang async

Tạo integration test chứng minh operation trong transaction chính được compensation theo cấu hình, trong khi task async là operation độc lập và không được xem là một phần của transaction đó. Không viết test dựa vào timing ngẫu nhiên; dùng CountDownLatch/barrier để điều khiển thứ tự.

## 18. Troubleshooting theo triệu chứng

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| ConcurrentModification/LDAP exception ngẫu nhiên | Dùng chung DirContext hoặc mutable object | Tìm field singleton chứa context/adapter/enumeration |
| Enumeration lỗi sau callback | Enumeration bị trả ra ngoài scope | Duyệt và đóng trong callback |
| Pool cạn dù request ít | Context không được đóng/return, enumeration bị giữ | Đo active/idle, xem exception path và callback block |
| Request sau dùng sai identity | Pool ghép với AuthenticationSource theo user | Kiểm tra context credential và cấu hình pool |
| Paging lặp trang hoặc invalid cookie | Mỗi trang dùng context khác hoặc processor bị chia sẻ | Giữ cùng SingleContextSource scope; processor riêng |
| Async operation không rollback | Transaction resource gắn với thread gốc | Không giả định transaction truyền qua Executor |
| Hai request ghi đè description | Lost update ở cấp nghiệp vụ | Kiểm tra read-modify-write; dùng assertion/version nếu server hỗ trợ |
| Add cùng DN có lúc báo 68 | Hai request cùng Add | Đọc lại và xác minh entry sau duplicate |
| Tăng worker làm latency tăng | Pool/server không theo kịp concurrency | Giới hạn executor, đo borrow wait và LDAP latency |
| Context lỗi sau khi trả pool | Connection stale hoặc state không được reset | Bật validation, invalidation và kiểm tra wrapper/version |

### 18.1. Quy trình chẩn đoán

~~~mermaid
flowchart TD
    A["Lỗi khi nhiều thread gọi LDAP"] --> B{"Có chia sẻ DirContext?"}
    B -->|Có| C["Tách context theo operation/callback"]
    B -->|Không| D{"Có giữ enumeration hoặc processor?"}
    D -->|Có| E["Giới hạn resource trong một scope"]
    D -->|Không| F{"Pool có cạn hoặc credential lẫn?"}
    F -->|Có| G["Kiểm tra pool metrics và AuthenticationSource"]
    F -->|Không| H{"Có race ở read-modify-write?"}
    H -->|Có| I["Thêm assertion/version hoặc xử lý conflict"]
    H -->|Không| J["Kiểm tra server limits, timeout và logs"]
    C --> K["Integration test concurrency"]
    E --> K
    G --> K
    I --> K
    J --> K
~~~

## 19. Checklist trước khi triển khai đa luồng

~~~text
[ ] LdapTemplate được cấu hình xong trước khi phục vụ request
[ ] ContextSource không bị mutate khi đang dùng
[ ] Không giữ DirContext/LdapContext trong singleton field
[ ] Mỗi callback trực tiếp có context scope rõ ràng
[ ] NamingEnumeration được duyệt và đóng trước khi callback kết thúc
[ ] DirContextOperations/entity mutable không chia sẻ giữa request
[ ] Pool read-only/read-write được cấu hình theo server capacity
[ ] Không pool credential theo user nếu environment không đồng nhất
[ ] Paged-results processor/cookie được tạo riêng theo request
[ ] SingleContextSource chỉ bao quanh một workflow/callback
[ ] Transaction-aware ContextSource được wiring đúng
[ ] Không mong transaction/SecurityContext tự truyền qua Executor
[ ] Business-level lost update được xử lý riêng
[ ] Executor concurrency phù hợp với LDAP pool và server
[ ] Integration test bao gồm concurrency, pool exhaustion và paging
[ ] Logs/metrics không lộ password hoặc credential
~~~

## 20. Bài thực hành, câu hỏi ôn tập và ghi nhớ

### 20.1. Bài thực hành

1. Khai báo một singleton LdapTemplate và gọi lookup đồng thời từ 8 thread.
2. Viết một service sai có field DirContext dùng chung; giải thích vì sao JNDI không bảo đảm thread safety cho instance đó.
3. Chuyển service sang executeReadOnly/executeReadWrite callback và bảo đảm context không thoát khỏi callback.
4. Viết một search trả List DTO; đóng NamingEnumeration trong finally.
5. Tạo pool có max-active nhỏ và quan sát borrow wait khi nhiều task cùng gọi LDAP.
6. Dùng AuthenticationSource theo user trong môi trường lab, sau đó kiểm tra giới hạn khi kết hợp với PoolingContextSource.
7. Viết paged search qua SingleContextSource.doWithSingleContext; tạo processor riêng cho mỗi request.
8. Cấu hình ContextSourceTransactionManager và TransactionAwareContextSourceProxy; thử rollback bù trong lab.
9. Gọi một operation bằng Executor bên trong transaction và chứng minh worker không tự thuộc transaction gốc.
10. Tạo hai request cùng đọc/sửa một attribute; quan sát lost update và đề xuất cơ chế assertion/version nếu server hỗ trợ.
11. Viết integration test với CountDownLatch để điều khiển hai operation chạy đồng thời.
12. Ghi lại metrics active/idle/waiter và xác định pool size phù hợp với tải test.

### 20.2. Câu hỏi ôn tập

1. Vì sao một LdapTemplate singleton có thể được gọi từ nhiều thread trong khi một DirContext không nên được chia sẻ đồng thời?
2. ContextSource tạo/cấp những loại context nào?
3. JNDI định nghĩa thế nào về concurrent access trên cùng Context instance?
4. Vì sao NamingEnumeration còn mở có nghĩa operation chưa kết thúc?
5. Tại sao không trả DirContext hoặc NamingEnumeration ra khỏi executeReadOnly callback?
6. DirContextOperations có thể gây data race như thế nào?
7. Pool read-only và read-write context có vai trò gì?
8. Vì sao PoolingContextSource có giới hạn khi dùng AuthenticationSource theo user?
9. SingleContextSource giải quyết vấn đề gì khi dùng paged results control?
10. Vì sao mỗi request paging cần processor/cookie riêng?
11. Spring LDAP transaction là server-side transaction hay client-side compensation?
12. Vì sao transaction resource không tự truyền sang thread của CompletableFuture?
13. Thread-safe ở client có ngăn lost update trên LDAP entry không?
14. Khi pool cạn, nên đo những chỉ số nào trước khi tăng max-active?
15. Làm thế nào kiểm thử rằng một Template dùng chung an toàn trong tải đồng thời?

### 20.3. Ghi nhớ

**LdapTemplate và ContextSource** thường là bean dùng chung sau khi cấu hình hoàn tất. Template tự quản lý việc lấy context, thao tác LDAP, duyệt enumeration và đóng resource. **DirContext/LdapContext** không được JNDI bảo đảm đồng bộ khi nhiều thread truy cập cùng một instance; mỗi operation cần context scope riêng. **NamingEnumeration**, **DirContextOperations**, processor có state và request controls cũng phải được giữ trong đúng phạm vi sở hữu.

Connection pool tái sử dụng context sau khi caller trả resource; pool không biến context thành object chia sẻ đồng thời và cũng không phải khóa entry. **SingleContextSource** giữ cùng context trong một callback khi protocol flow như paging yêu cầu; **TransactionAwareContextSourceProxy** và **ContextSourceTransactionManager** hỗ trợ client-side compensating transaction gắn với thread. Async task là luồng công việc riêng; truyền DTO/identity cần thiết và để worker lấy context mới. Cuối cùng, thread safety không thay thế xử lý lost update hoặc concurrency rule ở cấp nghiệp vụ.

## Tài liệu tham khảo

- [Spring LDAP — LdapTemplate API](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/LdapTemplate.html): quản lý context, search, executeReadOnly và executeReadWrite.
- [Spring LDAP — ContextSource API](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/core/ContextSource.html): tạo/cấp read-only, read-write và authenticated context.
- [Spring LDAP — Pooling Support](https://docs.spring.io/spring-ldap/reference/pooling.html): pool, validation, read-only/read-write pool và giới hạn AuthenticationSource.
- [Spring LDAP — SingleContextSource API](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/core/support/SingleContextSource.html): giữ một context trong callback.
- [Spring LDAP — Processing the DirContext](https://docs.spring.io/spring-ldap/reference/processing-the-dircontext.html): DirContextProcessor, request controls và paged results.
- [Spring LDAP — Transaction Support](https://docs.spring.io/spring-ldap/reference/transaction-support.html): ContextSourceTransactionManager và compensating transaction.
- [Spring LDAP — TransactionAwareContextSourceProxy API](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/transaction/compensating/manager/TransactionAwareContextSourceProxy.html): context gắn với transaction.
- [Oracle Java SE — Context, Concurrent Access](https://docs.oracle.com/en/java/javase/24/docs/api/java.naming/javax/naming/Context.html): quy tắc concurrent access và NamingEnumeration lifecycle.
- [Oracle JNDI FAQ — LDAP Contexts](https://docs.oracle.com/javase/tutorial/jndi/ldap/faq.html): JDK LDAP provider và chia sẻ context đa luồng.
- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): executor và asynchronous task execution.
