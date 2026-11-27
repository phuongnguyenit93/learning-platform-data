# Giữ cookie đúng trong toàn bộ lượt phân trang với Spring LDAP

## 1. Vấn đề: trang đầu đúng nhưng trang tiếp theo bị lặp hoặc mất

Giả sử thư mục LDAP chứa 25.000 entry dưới `ou=people`. Ứng dụng quản trị cần duyệt lần lượt để xây báo cáo, đồng bộ dữ liệu hoặc tìm các tài khoản cần kiểm tra. Thay vì yêu cầu server gửi toàn bộ kết quả một lần, ứng dụng sử dụng **Simple Paged Results Control** của LDAP (RFC 2696) với kích thước trang, chẳng hạn 200 entry.

Trang đầu trả 200 entry và một **cookie**. Client gửi cookie đó trong yêu cầu Search tiếp theo để server biết vị trí tiếp tục. Nếu ứng dụng quên cookie, tạo một processor mới ở mỗi vòng lặp hoặc chuyển trang bằng một kết nối LDAP khác, kết quả có thể lặp từ đầu, bị từ chối hoặc dừng sớm.

**Nhiệm vụ của bài:** hiểu cách giữ cookie đúng từ trang đầu tới trang cuối khi sử dụng **Spring LDAP**, đặc biệt với `LdapTemplate`, `PagedResultsControlExchangeDirContextProcessor` và `SingleContextSource`.

Bài thuộc chương **Phân trang và sorting** của module **Spring LDAP**. Những kiến thức liên quan bao gồm DN, schema, filter, search scope, `LdapTemplate`/`LdapClient`, cấu hình `ContextSource`, TLS, pooling, kiểm soát lỗi và kiểm thử directory an toàn. Trong chương này, **cookie dùng để đi tiếp trong một lượt tìm kiếm**, chứ không phải trang số hay khóa sắp xếp.

**Sau bài học, bạn sẽ có thể:**

1. Giải thích cookie của LDAP Simple Paged Results là gì, vì sao không được tự tạo hoặc sửa.
2. Xây vòng lặp phân trang có trang đầu không cookie, trang sau dùng cookie từ response và kết thúc đúng.
3. Giữ **cùng một LDAP connection** cho toàn bộ chuỗi request sử dụng cookie.
4. Dùng API Spring LDAP theo phiên bản: `PagedResultsControlExchangeDirContextProcessor` hoặc API cũ.
5. Phân biệt paging với `countLimit`, sorting và chia danh sách Java thành các trang.
6. Xử lý timeout, mất kết nối, cookie hết hạn và các trường hợp kết quả không đầy đủ.
7. Thiết kế kiểm thử phân trang nhiều trang, trang rỗng, ACL/TLS và kết quả bị thay đổi đồng thời.

## 2. Cookie là tín hiệu tiếp tục do LDAP server cấp

LDAP Simple Paged Results được định nghĩa bởi **RFC 2696**. Client gửi request control chứa:

- **size:** số entry mong muốn trong trang.
- **cookie:** chuỗi byte do server trả về từ lần Search trước, hoặc cookie rỗng khi bắt đầu.

Server gửi response control chứa:

- **size:** ước lượng tổng số entry nếu server cung cấp; không phải một `COUNT(*)` đáng tin cậy.
- **cookie:** dữ liệu byte để yêu cầu trang sau; cookie rỗng cho biết lượt phân trang đã đến cuối.

Ví dụ mang tính ý niệm:

~~~text
Client                                  LDAP server

Request 1:
  base = ou=people,dc=example,dc=org
  filter = (objectClass=inetOrgPerson)
  pageSize = 200
  cookie = EMPTY         --------------------->
                        <---------------------  200 entries
                                               cookie = C1

Request 2:
  SAME base/filter/scope/attributes
  pageSize = 200
  cookie = C1            --------------------->
                        <---------------------  200 entries
                                               cookie = C2

Request 3:
  SAME query settings
  pageSize = 200
  cookie = C2            --------------------->
                        <---------------------  35 entries
                                               cookie = EMPTY

Không còn cookie để tiếp tục -> kết thúc.
~~~

**C1 và C2 là tên ký hiệu**, không phải giá trị cookie thật. Client phải gửi lại **đúng dữ liệu cookie mà server trả**, không chuyển chúng thành số offset hay chuỗi tự tạo.

### 2.1. Cookie là opaque token

Một cookie có thể là chuỗi byte không in được. Nó **không có format công khai để ứng dụng phân tích**, và không có quy tắc chung rằng byte đầu tiên chỉ thứ tự entry hay vị trí trong cây LDAP.

**Không làm:**

~~~java
// Không hợp lệ: tự nghĩ cookie là số trang.
byte[] cookie = Integer.toString(pageNumber).getBytes();

// Cũng không đúng: thay cookie do server trả bằng dữ liệu khác.
cookie[0] = 42;
~~~

Trong ứng dụng Spring LDAP, nên để **paged results processor quản lý cookie**. Nếu dùng JNDI thô, chuyển tiếp nguyên vẹn `byte[]` từ response control sang request control tương ứng, không phân tích hoặc ghi chúng ra log.

### 2.2. Cookie không phải access token để truy vấn tùy ý

Cookie gắn với **một chuỗi Search request** trên server. Nó không phải:

- Trang số 1, 2, 3 để nhảy ngẫu nhiên giữa các trang.
- Một khóa sắp xếp hoặc cursor tự thiết kế từ `uid`.
- Một token cho phép truy cập các entry nằm ngoài ACL.
- Một checkpoint bền vững có thể tùy tiện lưu rồi dùng lại hôm sau.
- Một giá trị có thể chuyển sang server, kết nối hay bind identity khác mà vẫn chắc chắn hợp lệ.

Mặc dù được gọi là cookie, dữ liệu này phục vụ giao thức LDAP, không giống cookie HTTP của trình duyệt.

### 2.3. Dấu hiệu kết thúc: response cookie rỗng

Vòng lặp chỉ hoàn thành khi nhận tín hiệu **không còn trang tiếp theo** từ response control phù hợp. Trong Spring LDAP, processor cung cấp `hasMore()` để tránh ứng dụng tự kiểm tra độ dài cookie.

**Đừng dùng** các điều kiện như “trang có ít hơn pageSize entry” hoặc “đã đủ 200 entry” để kết luận kết thúc. Kích thước trang có thể không đúng như kỳ vọng do giới hạn/server, và độ dài kết quả không thay thế tín hiệu cookie.

## 3. Năm bất biến cần giữ xuyên toàn bộ lượt paging

Để trang hai thật sự tiếp nối trang một, nên giữ:

| Bất biến | Ý nghĩa | Hậu quả nếu thay đổi tùy ý |
| --- | --- | --- |
| **Cùng kết nối LDAP** | Chuỗi cookie sử dụng cùng underlying LDAP connection/context | Cookie có thể bị từ chối/mất trạng thái |
| **Cùng base DN** | Không đổi gốc tìm kiếm giữa các trang | Không còn là cùng lượt kết quả |
| **Cùng search scope** | Giữ OBJECT/ONELEVEL/SUBTREE như ban đầu | Tập ứng viên thay đổi |
| **Cùng filter, projection, controls liên quan** | Không đổi logic chọn entry và thuộc tính cần trả | Trang sau có thể không liên tục hoặc không hợp lệ |
| **Cookie từ response ngay trước** | Trang sau dùng đúng cookie server cấp trong lượt hiện tại | Có thể lặp, bỏ sót hoặc thất bại |

**Page size** nên giữ ổn định trong suốt lượt phân trang để dễ kiểm chứng, giám sát và tránh khác biệt hỗ trợ của server. RFC có thể cho phép client thay đổi tham số size trong những trường hợp nhất định, nhưng một ứng dụng cần độ tin cậy nên chọn page size cố định, dương và hợp giới hạn hạ tầng.

Ngoài ra, giữ cùng **LDAP endpoint, bind identity và ngữ cảnh kiểm soát truy cập**. Nếu kết nối bị thay bằng một context khác sau reconnect, đừng giả định cookie cũ vẫn có thể dùng.

### 3.1. Ví dụ cấu hình Search phải giữ không đổi

~~~java
import javax.naming.directory.SearchControls;

SearchControls controls = new SearchControls();
controls.setSearchScope(SearchControls.SUBTREE_SCOPE);
controls.setReturningAttributes(new String[] {
        "uid", "cn", "mail"
});
controls.setReturningObjFlag(false);
~~~

Với `ContextSource.base = dc=example,dc=org`, tìm từ `"ou=people"` nghĩa là tìm từ DN đầy đủ `ou=people,dc=example,dc=org`.

Một trang Search với:

~~~text
base: ou=people
filter: (objectClass=inetOrgPerson)
scope: SUBTREE
attributes: uid, cn, mail
~~~

phải được tiếp tục với **cùng** những tham số đó, chứ không tự đổi thành `(uid=*)` hoặc chuyển `ONELEVEL` ở giữa.

### 3.2. Đừng tạo processor mới ở mỗi trang

**Sai ý tưởng:**

~~~java
do {
    // Tạo mới trong vòng lặp => mất trạng thái cookie trước.
    var processor =
            new PagedResultsControlExchangeDirContextProcessor(200);
    operations.search(base, filter, controls, mapper, processor);
} while (/* không có trạng thái pager ổn định */);
~~~

**Nên:** tạo **một processor cho một lượt phân trang**, giữ nó trong vòng lặp và sử dụng `processor.hasMore()` sau khi từng request hoàn tất.

Không dùng processor đó như singleton cho nhiều request HTTP, nhiều người dùng hoặc nhiều job chạy đồng thời.

## 4. Tại sao cùng kết nối quan trọng hơn chỉ giữ byte cookie?

Đây là điểm dễ sai nhất trong Spring LDAP. `LdapTemplate` thường lấy một `DirContext` từ `ContextSource` rồi **đóng/trả context sau mỗi lời gọi LDAP**. Trong khi đó, Simple Paged Results của nhiều server yêu cầu **cùng LDAP connection** ở toàn bộ chuỗi trang.

~~~text
Sử dụng LdapTemplate riêng cho từng trang:

search(page 1) -> LDAP connection A -> cookie C1 -> close A
search(page 2) -> LDAP connection B -> cookie C1 -> có thể lỗi
                                            ^
                                Kết nối đã thay đổi!
~~~

Dù code truyền lại C1, server có thể chỉ hiểu cookie C1 trong ngữ cảnh connection A. Khi đã đóng A, việc mở lại B cùng host, cùng DN và cùng mật khẩu **không làm B trở thành A**.

Theo tài liệu Spring LDAP, giải pháp phổ biến là:

- **`SingleContextSource.doWithSingleContext(...)`:** giữ một context underlying trong một callback thực thi chuỗi Search.
- **`ContextSourceTransactionManager` kết hợp `TransactionAwareContextSourceProxy`:** dùng khi dự án đã thiết kế quản lý context/transaction-aware đúng cách.

**Không cần** bao một lượt Search nhiều trang vào SQL transaction chỉ để giữ connection LDAP. Giải pháp `SingleContextSource` phù hợp để minh họa vì phạm vi sống của context rõ ràng và được framework dọn sau khi callback hoàn tất.

### 4.1. Pooling không bảo đảm tính liên tục

Một connection pool có thể trả một connection khác ở lần gọi sau. Khi đó:

~~~text
pool.borrow() -> connection #3 (page 1)
pool.return(#3)

pool.borrow() -> connection #7 (page 2)
~~~

Cả hai kết nối đều khỏe mạnh nhưng **không cùng một connection**. Vì vậy chỉ bật pooling không sửa lỗi cookie. Bạn cần **pin** cùng underlying context trong suốt lượt paging theo cơ chế được Spring LDAP hỗ trợ.

Không giữ connection bị pin cho một tác vụ nền vô hạn: điều đó chiếm tài nguyên pool, làm tăng timeout và giảm khả năng phục vụ request khác. Giới hạn số trang, thời gian xử lý và quy mô công việc.


## 5. API Spring LDAP theo phiên bản

Tài liệu Spring LDAP mới sử dụng processor:

~~~java
import org.springframework.ldap.control.PagedResultsControlExchangeDirContextProcessor;
~~~

`PagedResultsControlExchangeDirContextProcessor` có mặt từ **Spring LDAP 4.1**. Bộ xử lý tạo paged request control, lấy response cookie sau Search và có phương thức `hasMore()`.

~~~java
int pageSize = 200;
PagedResultsControlExchangeDirContextProcessor processor =
        new PagedResultsControlExchangeDirContextProcessor(pageSize);
~~~

**Nếu dự án dùng Spring LDAP 4.0 hoặc 3.x**, API `PagedResultsDirContextProcessor` là lựa chọn tương ứng:

~~~java
import org.springframework.ldap.control.PagedResultsDirContextProcessor;

PagedResultsDirContextProcessor processor =
        new PagedResultsDirContextProcessor(200);
~~~

Lớp cũ cung cấp `hasMore()` và `getCookie()`, nhưng đã được đánh dấu **deprecated** trong tài liệu API hiện hành. Không thay tên lớp theo hướng dẫn của phiên bản mới rồi giả định code compile trên mọi dự án: cần xác nhận **dependency thực tế** của ứng dụng.

### 5.1. Processor quản lý cookie như thế nào?

Trước một Search, processor thiết lập `PagedResultsControl` lên `LdapContext`. Sau Search, processor đọc `PagedResultsResponseControl`, cập nhật continuation cookie, rồi cung cấp `hasMore()` để caller biết có cần trang nữa hay không.

Như vậy ứng dụng không phải tự tạo `byte[]` cookie, không phải đoán kết thúc dựa vào số entry và không phải phân tích cấu trúc token.

**Nhưng processor không tự giữ connection**. Cần kết hợp `SingleContextSource` hoặc một cơ chế transaction-aware context đã được thiết kế phù hợp.

### 5.2. Tại sao dùng LdapContextSource?

LDAPv3 request/response controls đòi hỏi API `LdapContext`. Trong Spring LDAP, `LdapContextSource` phù hợp để tạo context hỗ trợ controls. Một `DirContext` thông thường không có đủ API xử lý controls theo JNDI.

Khi tích hợp với connection pool, proxy hoặc cơ chế quản lý context riêng, hãy đảm bảo đối tượng cuối cùng mà processor nhận thực sự hỗ trợ LDAP controls.

## 6. Ví dụ đầy đủ: duyệt toàn bộ trang trên cùng kết nối

Ví dụ sử dụng **Spring LDAP 4.1+**, `SingleContextSource`, `LdapOperations` và `PagedResultsControlExchangeDirContextProcessor`. Nó xử lý UID **từng entry** bằng callback thay vì giữ một `List` gồm toàn bộ danh bạ.

### 6.1. Cấu hình ContextSource

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.core.support.LdapContextSource;

@Configuration
public class LdapConfig {

    @Bean
    public LdapContextSource ldapContextSource(
            @Value("${app.ldap.url}") String url,
            @Value("${app.ldap.base}") String base,
            @Value("${app.ldap.bind-dn}") String userDn,
            @Value("${app.ldap.bind-password}") String password) {

        LdapContextSource source = new LdapContextSource();
        source.setUrl(url);
        source.setBase(base);
        source.setUserDn(userDn);
        source.setPassword(password);
        return source;
    }

    @Bean
    public LdapTemplate ldapTemplate(LdapContextSource source) {
        return new LdapTemplate(source);
    }
}
~~~

~~~yaml
# application.yml — LDAP directory thử nghiệm
app:
  ldap:
    url: ${LDAP_URL:ldaps://ldap.example.org:636}
    base: dc=example,dc=org
    bind-dn: ${LDAP_BIND_DN}
    bind-password: ${LDAP_BIND_PASSWORD}
~~~

`app.ldap.*` là các property minh họa do ứng dụng định nghĩa. Spring Boot còn có `spring.ldap.*` khi dùng auto-configuration. Không khai báo bean thủ công và auto-configuration trùng nhau mà không biết repository sử dụng bean nào.

**An toàn:** xác minh chứng chỉ và hostname của LDAPS, hoặc bật StartTLS thật sự **trước khi** gửi simple-bind credentials. Chỉ `ldap://` không tự bật TLS. Bind identity chỉ cần quyền đọc trong OU liên quan, không dùng administrator credential.

### 6.2. Repository phân trang có giới hạn an toàn

~~~java
import java.util.Objects;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Consumer;

import javax.naming.NamingException;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;
import javax.naming.directory.SearchControls;
import javax.naming.directory.SearchResult;

import org.springframework.ldap.control.PagedResultsControlExchangeDirContextProcessor;
import org.springframework.ldap.core.ContextSource;
import org.springframework.ldap.core.NameClassPairCallbackHandler;
import org.springframework.ldap.core.support.SingleContextSource;
import org.springframework.stereotype.Repository;

@Repository
public class PagedPersonDirectory {

    private static final int PAGE_SIZE = 200;
    private static final int MAX_PAGES = 1000;

    private final ContextSource contextSource;

    public PagedPersonDirectory(ContextSource contextSource) {
        this.contextSource = contextSource;
    }

    public int visitAllUids(Consumer<String> consumer) {
        Objects.requireNonNull(consumer, "consumer");

        SearchControls controls = new SearchControls();
        controls.setSearchScope(SearchControls.SUBTREE_SCOPE);
        controls.setReturningAttributes(new String[] {"uid"});
        controls.setReturningObjFlag(false);

        // Mỗi lượt paging cần processor riêng; không dùng singleton.
        PagedResultsControlExchangeDirContextProcessor pager =
                new PagedResultsControlExchangeDirContextProcessor(PAGE_SIZE);

        AtomicInteger count = new AtomicInteger();

        return SingleContextSource.doWithSingleContext(
                contextSource,
                operations -> {
                    int pages = 0;

                    do {
                        if (++pages > MAX_PAGES) {
                            throw new IllegalStateException(
                                    "Exceeded paged LDAP search budget");
                        }

                        NameClassPairCallbackHandler handler = pair -> {
                            if (!(pair instanceof SearchResult)) {
                                throw new NamingException(
                                        "Expected LDAP SearchResult");
                            }

                            Attributes attrs =
                                    ((SearchResult) pair).getAttributes();
                            Attribute uid = attrs.get("uid");

                            if (uid == null || uid.size() != 1) {
                                throw new NamingException(
                                        "Expected one readable uid");
                            }

                            Object value = uid.get();
                            if (!(value instanceof String)) {
                                throw new NamingException(
                                        "Unexpected uid representation");
                            }

                            consumer.accept((String) value);
                            count.incrementAndGet();
                        };

                        operations.search(
                                "ou=people",
                                "(objectClass=inetOrgPerson)",
                                controls,
                                handler,
                                pager
                        );

                    } while (pager.hasMore());

                    return count.get();
                },
                true, false, false
        );
    }
}
~~~

Trong ví dụ, chữ ký overload của `SingleContextSource.doWithSingleContext` là:

~~~java
doWithSingleContext(
    ContextSource contextSource,
    LdapOperationsCallback<T> callback,
    boolean useReadOnly,
    boolean ignorePartialResultException,
    boolean ignoreNameNotFoundException
)
~~~

Ba boolean cuối có ý nghĩa: `true` dùng read-only context; hai `false` giữ nguyên việc báo lỗi PartialResult và NameNotFound thay vì tự bỏ qua.

### 6.3. Sáu điểm bảo vệ cookie trong đoạn mã

1. **Một processor cho một lượt:** `pager` nằm ngoài vòng lặp; mọi Search nhận cùng object.
2. **Một underlying context:** `SingleContextSource` giữ kết nối tới khi callback trả về hoặc ném exception.
3. **Truy vấn không thay đổi:** base, filter, `SearchControls` được giữ nguyên giữa các lần gọi.
4. **Cookie được lấy từ response:** processor thay ứng dụng quản lý continuation.
5. **Đúng điều kiện kết thúc:** vòng lặp chỉ dừng bình thường khi `pager.hasMore()` là `false`.
6. **Bảo vệ tài nguyên:** `MAX_PAGES` ngăn một bug/protocol error khiến job chiếm connection vô hạn.

Hàm không thu thập toàn bộ entry thành List; `Consumer<String>` có thể ghi vào một writer/buffer được quản lý. Nếu consumer giữ hết UID vào một danh sách, lợi ích bộ nhớ từ callback sẽ biến mất.

**Lưu ý về state:** `AtomicInteger` giúp callback tăng bộ đếm không cần biến cục bộ mutable; nó không có ý nghĩa rằng Spring LDAP gọi handler song song. Tạo state riêng cho mỗi lượt, không chia sẻ `pager` hoặc `count` giữa nhiều request HTTP.

### 6.4. Dùng repository với consumer

~~~java
int processed = pagedPersonDirectory.visitAllUids(uid -> {
    // Xử lý UID đã được map; production cần idempotency ở downstream.
    // Không log UID nếu không có yêu cầu kiểm toán hợp lệ.
    System.out.println("Processed directory entry");
});
~~~

`processed` là số entry callback đã hoàn thành khi toàn bộ hàm trả thành công. Nó **không** tự đại diện cho số lượng toàn directory nếu ACL/filter giới hạn, hoặc nếu hệ thống khác có entry mới trong thời gian paging.

### 6.5. Vì sao không retry một trang ngay sau timeout?

Nếu `operations.search` lỗi vì kết nối đứt, cookie và trạng thái server **có thể đã thay đổi**. Không nên bắt exception rồi mở kết nối mới và gửi lại cookie cũ. Vòng lặp phải dừng và ghi nhận **lượt phân trang chưa hoàn thành**. Khi muốn thử lại, thường khởi động một lượt mới từ cookie rỗng và dùng chiến lược idempotency/đối soát tránh xử lý trùng ở consumer.

### 6.6. Chỉ dùng String mapper nếu thật sự cần List

Nếu UI cần một trang kết quả nhỏ, có thể dùng overload mapper:

~~~java
import java.util.List;
import org.springframework.ldap.core.AttributesMapper;

List<String> onePage = operations.search(
        "ou=people",
        "(objectClass=inetOrgPerson)",
        controls,
        (AttributesMapper<String>) attrs ->
                String.valueOf(attrs.get("uid").get()),
        pager
);

// Xử lý onePage rồi bỏ reference trước khi đọc trang tiếp theo.
~~~

Đoạn này thuộc **bên trong** callback `SingleContextSource`, chia sẻ `operations`, `controls` và `pager` của lượt phân trang hiện hành. Không đặt lời gọi đơn lẻ đó ngoài callback nếu muốn cookie tiếp tục trên cùng connection.

**Tránh gom mọi trang không kiểm soát:**

~~~java
List<String> all = new ArrayList<>();
do {
    all.addAll(operations.search(
            "ou=people", filter, controls, mapper, pager));
} while (pager.hasMore());
~~~

Cách này có thể đúng về continuation nhưng có bộ nhớ tăng theo tổng số entry. Chỉ dùng khi sản phẩm thật sự cần toàn bộ List và đã giới hạn tổng dữ liệu.

## 7. Bảng trạng thái cookie và điều kiện kết thúc

~~~text
START: processor mới, cookie rỗng
  |
  v
PAGE_REQUEST: Search với control và cookie hiện tại
  |
  v
PAGE_RESPONSE: nhận entries + response control
  |
  +-- hasMore() == true -> PAGE_REQUEST tiếp theo trên cùng context
  |
  +-- hasMore() == false -> COMPLETE
  |
  +-- exception / missing response control -> FAILED_OR_INCOMPLETE
~~~

| Trạng thái | Cookie/response | Hành động |
| --- | --- | --- |
| Chưa bắt đầu | Cookie rỗng | Gửi yêu cầu trang đầu |
| Xong trang n | Cookie tiếp tục có giá trị | Gửi request n+1 trên cùng connection |
| Trang cuối | Cookie rỗng | Đánh dấu hoàn tất |
| Search thất bại | Cookie có thể không đáng tin | Dừng/ghi trạng thái incomplete |
| Connection đã đóng | Cookie cũ không được bảo đảm hợp lệ | Restart với cookie rỗng nếu cần |
| Client dừng sớm | Có thể vẫn còn cookie | Cân nhắc bỏ lượt paging theo RFC/server |
| Không có response control hợp lệ | Không thể biết có trang tiếp hay không | Báo lỗi, không giả là complete |

### 7.1. Vì sao không dừng khi trang có ít hơn pageSize?

Một trang có thể ít entry hơn số yêu cầu vì đặc tính server hoặc giới hạn. Trang cuối cũng có thể được xác nhận bằng cookie rỗng ở một response với số lượng entry bất kỳ.

**Tín hiệu hoàn thành** là response cookie rỗng (`hasMore()==false` theo processor), không phải một phép so sánh số entry của trang hiện tại.

Tương tự, không dừng đơn giản khi trang rỗng nếu response vẫn cung cấp cookie tiếp tục; cần có giới hạn tổng số trang/thời gian để tránh một server không tiến triển hoặc bug làm vòng lặp chạy vô hạn.

### 7.2. Response size chỉ có tính gợi ý

RFC 2696 có trường `size` trong response control. Nó có thể là ước lượng hoặc `0` nếu server không thể xác định. Với API legacy, `PagedResultsDirContextProcessor.getResultSize()` cũng không phải một lệnh COUNT đáng tin tuyệt đối.

Không dùng response size để tự tính cookie, bỏ qua request còn lại hoặc hứa với client rằng đã biết tổng số trang chính xác.

### 7.3. Không tái sử dụng processor sau khi hoàn tất

Mỗi lượt paging mới nên tạo một processor mới để cookie ban đầu rỗng. Không lưu processor trong biến field của singleton repository rồi chạy nhiều request người dùng với cùng object. Điều đó có thể trộn cookie và trạng thái response của những lượt độc lập.

## 8. Kết thúc sớm và giải phóng server-side paging state

Theo RFC 2696, client có thể **báo server bỏ một lượt paging còn dở** bằng một Simple Paged Results request control có **size bằng 0** và cookie cuối cùng đã nhận, gửi trong ngữ cảnh hợp lệ. Mục đích là cho server biết không cần duy trì trạng thái của chuỗi paging đang được sử dụng.

Không tự đặt pageSize=0 để “truy vấn trang rỗng” trong vòng lặp bình thường. **size=0 với continuation cookie** mang ý nghĩa **abandon** theo RFC, khác yêu cầu lấy thêm dữ liệu.

Khi framework không cung cấp thao tác hủy thuận tiện, ứng dụng có thể kết thúc lượt, giải phóng context và chấp nhận rằng server sẽ dọn trạng thái theo chính sách timeout. Nếu cần hủy chủ động, hãy dùng API/control đúng chuẩn, **cùng underlying connection và đúng cookie**, kiểm thử trên LDAP server thực tế.

**Không gửi cookie vào URL HTTP, log hoặc hàng đợi bền vững chỉ để cố tiếp tục paging ở một tiến trình khác.** Một lượt dài cần được thiết kế với timeout, điều phối và chiến lược restart rõ ràng, không biến cookie thành checkpoint lâu dài.

## 9. Cookie paging khác với sắp xếp và số trang

**Simple Paged Results (RFC 2696)** giúp client đi tiếp trong tập kết quả Search. Nó **không** mặc định sắp xếp entry theo `uid`, `cn` hoặc `modifyTimestamp`.

| Cơ chế | Công dụng | Có thay cho cookie không? |
| --- | --- | --- |
| Paged Results (RFC 2696) | Chia lượt Search thành các trang và dùng continuation cookie | Chính là cơ chế được học |
| Server-side Sorting (RFC 2891) | Yêu cầu server sắp xếp kết quả theo attribute | Không; đây là control khác |
| Virtual List View (VLV) | Hỗ trợ vùng kết quả/khái niệm vị trí tùy server | Không; cơ chế khác, không mặc định hỗ trợ |
| Java `List.sort` | Sort những dữ liệu client đã nhận | Không giúp duyệt trang tiếp theo |

### 9.1. Sắp xếp trong từng trang không tạo thứ tự toàn cục

~~~text
Trang 1: carol, alice
Trang 2: david, bob

Sort trang 1: alice, carol
Sort trang 2: bob, david

Ghép lại: alice, carol, bob, david  <-- vẫn không sort toàn cục.
~~~

Nếu sản phẩm cần thứ tự toàn cục, phải thiết kế server-side sorting nếu server hỗ trợ, hoặc một phương án dữ liệu khác có bảo đảm rõ ràng. Không mặc định thứ tự LDAP Search là thứ tự tăng dần theo DN hay UID.

### 9.2. Không đổi sort key giữa các trang

Nếu đang sử dụng cả Server-side Sorting và Paged Results, phải giữ **cùng sort specification và các request controls liên quan** suốt lượt:

~~~text
Trang đầu: sort=uid, cookie=EMPTY
Trang sau: sort=cn,  cookie=C1   <-- thay đổi không phù hợp
~~~

Một số LDAP server không hỗ trợ kết hợp hai control hoặc có giới hạn riêng. Kiểm tra tính tương thích, response controls và kiểm thử thật, không coi mọi LDAP vendor đều có cùng semantics.

### 9.3. Cookie không phải random page number

Chuỗi hành động đúng là:

~~~text
page 1 -> page 2 -> page 3 -> ... -> last
~~~

Client không thể yêu cầu ngẫu nhiên “trang 85” bằng cách tự mã hóa số 85 thành cookie. Nếu UI cần nhảy tới một vị trí ngẫu nhiên, nghiên cứu VLV hay giải pháp khác đã được hạ tầng hỗ trợ.

### 9.4. Không mặc định snapshot ổn định khi directory thay đổi

Giữa hai request, một entry có thể được thêm, xóa hoặc đổi các thuộc tính dùng để tìm/sort. Cookie kết thúc hợp lệ **không bảo đảm** đã nhận toàn bộ entry đúng một lần trong một directory biến động. Đồng bộ dữ liệu cần reconciliation, idempotency hoặc cơ chế change tracking/snapshot riêng của server nếu có.

## 10. Minh họa JNDI thô: chuyển tiếp cookie byte nguyên vẹn

`PagedResultsControlExchangeDirContextProcessor` của Spring LDAP tự quản lý request/response cookie. Để hiểu những gì nó che giấu, xem minh họa JNDI sử dụng **một `LdapContext` xuyên suốt**:

~~~java
import java.io.IOException;

import javax.naming.NamingEnumeration;
import javax.naming.NamingException;
import javax.naming.directory.SearchControls;
import javax.naming.directory.SearchResult;
import javax.naming.ldap.Control;
import javax.naming.ldap.LdapContext;
import javax.naming.ldap.PagedResultsControl;
import javax.naming.ldap.PagedResultsResponseControl;

public final class RawPagedSearch {

    public static int scan(
            LdapContext ctx,
            String fullBaseDn,
            String filter,
            int pageSize) throws NamingException, IOException {

        if (pageSize <= 0) {
            throw new IllegalArgumentException("pageSize must be positive");
        }

        SearchControls controls = new SearchControls();
        controls.setSearchScope(SearchControls.SUBTREE_SCOPE);
        controls.setReturningAttributes(new String[] {"uid"});

        byte[] cookie = null;
        int count = 0;

        do {
            ctx.setRequestControls(new Control[] {
                    new PagedResultsControl(
                            pageSize, cookie, Control.CRITICAL)
            });

            NamingEnumeration<SearchResult> results =
                    ctx.search(fullBaseDn, filter, controls);

            try {
                while (results.hasMore()) {
                    SearchResult entry = results.next();
                    // Xử lý từng entry thay vì giữ tất cả trong RAM.
                    count++;
                }
            } finally {
                results.close();
            }

            Control[] responseControls = ctx.getResponseControls();
            boolean sawPagedResponse = false;
            cookie = null;

            if (responseControls != null) {
                for (Control control : responseControls) {
                    if (control instanceof PagedResultsResponseControl) {
                        cookie = ((PagedResultsResponseControl) control)
                                .getCookie();
                        sawPagedResponse = true;
                        break;
                    }
                }
            }

            if (!sawPagedResponse) {
                throw new NamingException(
                        "Missing paged results response control");
            }

        } while (cookie != null && cookie.length > 0);

        return count;
    }

    private RawPagedSearch() {}
}
~~~

Code giả định **caller đã tạo một `LdapContext` có TLS/bind identity phù hợp, giữ nó mở đến hết lượt và đóng trong `finally`**. Lệnh `ctx.search` nhận **DN đầy đủ** khi dùng JNDI context theo cấu hình tương ứng. Trong Spring LDAP, DN truyền cho template thường tương đối với `ContextSource.base`.

Các bước cốt lõi:

1. Request đầu có cookie rỗng (`null`).
2. Trước mỗi trang, `setRequestControls` đính kèm pageSize + cookie hiện tại.
3. Sau mỗi trang, đóng `NamingEnumeration` và lấy `PagedResultsResponseControl`.
4. Gửi lại đúng `byte[]` của response, không phân tích hay thay đổi.
5. Cookie rỗng nghĩa là hoàn tất; response control thiếu phải là lỗi, không phải success.
6. Mọi Search dùng **cùng `ctx`**.

Trong production, nên ưu tiên Spring LDAP processor + `SingleContextSource` để tránh phải tự quản lý nhiều chi tiết JNDI như trên.

## 11. Phân loại sự cố cookie và kết nối

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Trang sau lặp trang đầu | Reset cookie hoặc tạo processor mới mỗi lần | Một processor cho toàn lượt |
| Cookie bị từ chối sau trang đầu | Thay connection, cookie hết hiệu lực | Pin context, dừng/restart nếu kết nối hỏng |
| Chỉ đọc được một trang | Dừng theo page size thay vì `hasMore()` | Dừng theo response cookie |
| Vòng lặp không kết thúc | Sai state, server trả continuation bất thường | Giới hạn số trang và timeout |
| Paging thiếu kết quả | Directory thay đổi, ACL, replication, giới hạn | Đối soát; không hứa snapshot |
| Không có response control | Server/proxy không hỗ trợ paging | Kiểm tra `supportedControl` và cấu hình critical |
| Sort + paging lỗi | Server không hỗ trợ kết hợp | Xác nhận tính tương thích |
| Pool hết connection | Giữ context quá lâu | Budget, giới hạn đồng thời, giải phóng context |

### 11.1. LDAP result code liên quan

| Mã | Tên | Nhóm vấn đề |
| --- | --- | --- |
| **3** | `timeLimitExceeded` | Quá thời gian |
| **4** | `sizeLimitExceeded` | Quá kích thước kết quả |
| **11** | `adminLimitExceeded` | Giới hạn quản trị |
| **12** | `unavailableCriticalExtension` | Control bắt buộc không hỗ trợ |
| **32** | `noSuchObject` | Base DN không tồn tại/không thấy |
| **50** | `insufficientAccessRights` | Thiếu quyền |
| **87** | `filterError` | Filter sai cú pháp |

Mã/diagnostic cho cookie không hợp lệ phụ thuộc server. Không viết code dựa trên một thông điệp tiếng Anh cố định và không đổi mọi exception thành “đã hết trang”.

### 11.2. Không tự nuốt lỗi

~~~java
try {
    operations.search(base, filter, controls, handler, pager);
} catch (RuntimeException failure) {
    break; // Sai: lượt paging chưa hoàn tất.
}
~~~

Khi lỗi xuất hiện, giữ trạng thái `FAILED` hoặc `INCOMPLETE`, lưu tiến độ **của ứng dụng**, điều tra rồi quyết định restart. Không trả số entry đã xử lý như thể đã đọc đầy đủ LDAP directory.

### 11.3. Lỗi trong callback cũng có thể khiến downstream dở dang

Nếu callback đã gửi Alice và Bob sang database nhưng gặp lỗi ở Carol, LDAP Search **không rollback** những side effects trước đó. Với job đồng bộ nên dùng idempotency key theo định danh entry phù hợp, journal/checkpoint bền vững của ứng dụng, retry giới hạn và đối soát. **Đừng lưu cookie opaque như checkpoint lâu dài** để chuyển sang một tiến trình/connection khác.

## 12. Bảo mật cookie, TLS và ACL

### 12.1. Không log raw cookie

Cookie là dữ liệu điều khiển server-side, không phải thông tin nghiệp vụ để xuất trong log, HTTP URL hay ticket hỗ trợ. Ghi số trang, page size, số entry xử lý, thời gian và loại lỗi; không ghi raw cookie hoặc toàn bộ thuộc tính người dùng.

### 12.2. TLS và bind identity

- Sử dụng `ldaps://` với xác minh chứng chỉ/hostname, hoặc nâng cấp StartTLS thật sự trước simple bind.
- `ldap://` không tự bật StartTLS; không truyền mật khẩu trên đường truyền chưa mã hóa.
- Không tắt xác minh chứng chỉ chỉ để xử lý lỗi paging.
- Giữ bind identity và quyền truy cập ổn định trong suốt lượt, không đổi account giữa các trang.
- Khi dùng connection pool, không tái sử dụng underlying context đang được pin cho một lượt cookie ở một job khác.

### 12.3. Quyền tối thiểu và giới hạn kết quả

Paging **không vượt ACL**. Người dùng chỉ được xem một OU vẫn không thể dùng cookie để đọc dữ liệu ngoài OU đó. Chọn base hẹp, filter chọn lọc, thuộc tính trả về tối thiểu, page size phù hợp và giới hạn số request/thời gian.

“Đã đọc xong tất cả entry mà reader được phép thấy” khác với “đã đọc xong toàn bộ LDAP directory”. Khi ACL hoặc referral che một phần cây, cần diễn giải kết quả đúng ngữ cảnh.


## 13. Kiểm thử đúng một lượt cookie từ trang đầu đến cuối

Một test có ích không chỉ khẳng định Search trả dữ liệu, mà còn chứng minh **mọi trang được tiếp tục đúng** khi tổng số entry lớn hơn page size.

Chuẩn bị một LDAP directory **dành riêng cho test** với đúng năm entry `inetOrgPerson` trong `ou=people`:

~~~text
ou=people,dc=example,dc=org
├── uid=training-01
├── uid=training-02
├── uid=training-03
├── uid=training-04
└── uid=training-05
~~~

Dùng **page size = 2** để buộc lượt Search đi qua nhiều trang. Cho test identity quyền đọc `uid` trên cả năm entry.

### 13.1. Integration test với SingleContextSource

~~~java
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

import javax.naming.directory.SearchControls;

import org.junit.jupiter.api.Test;
import org.springframework.ldap.control.PagedResultsControlExchangeDirContextProcessor;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.ContextSource;
import org.springframework.ldap.core.support.SingleContextSource;

import static org.junit.jupiter.api.Assertions.*;

class CookiePagingIntegrationTest {

    private final ContextSource contextSource;

    // Test fixture/Spring Test phải cung cấp bean contextSource.
    CookiePagingIntegrationTest(ContextSource contextSource) {
        this.contextSource = contextSource;
    }

    @Test
    void readsAllFiveEntriesWithPageSizeTwo() {
        SearchControls controls = new SearchControls();
        controls.setSearchScope(SearchControls.SUBTREE_SCOPE);
        controls.setReturningAttributes(new String[] {"uid"});

        PagedResultsControlExchangeDirContextProcessor pager =
                new PagedResultsControlExchangeDirContextProcessor(2);

        List<String> uids = SingleContextSource.doWithSingleContext(
                contextSource,
                operations -> {
                    List<String> read = new ArrayList<>();
                    do {
                        List<String> page = operations.search(
                                "ou=people",
                                "(objectClass=inetOrgPerson)",
                                controls,
                                (AttributesMapper<String>) attrs ->
                                        String.valueOf(
                                                attrs.get("uid").get()),
                                pager
                        );
                        read.addAll(page);
                    } while (pager.hasMore());
                    return read;
                },
                true, false, false
        );

        Set<String> expected = Set.of(
                "training-01", "training-02", "training-03",
                "training-04", "training-05");

        assertEquals(5, uids.size());
        assertEquals(expected, new HashSet<>(uids));
    }
}
~~~

**Điều kiện của test:** directory test phải chứa **đúng năm** entry khớp filter trong base/scope; không có entry ngoài fixture chen vào. Test chưa runnable nếu chưa có Spring Test context, LDAP server, schema, credentials và setup/teardown. Dùng DN thử nghiệm duy nhất và chỉ dọn dữ liệu test sở hữu.

`assertEquals(5, uids.size())` phát hiện thiếu hoặc thừa entry; so sánh `Set` phát hiện dữ liệu bị lặp hoặc bỏ sót khi kết hợp với điều kiện số lượng. LDAP Search không mặc định trả kết quả có thứ tự; không so sánh thứ tự list.

### 13.2. Vì sao test một trang là chưa đủ?

Nếu page size là 200 và fixture chỉ có 5 entry, toàn bộ kết quả có thể được trả ở trang đầu; những lỗi **mất cookie sau trang đầu**, **đổi connection** hoặc **không gọi `hasMore()`** sẽ không lộ ra.

Luôn có ít nhất một case:

~~~text
Tổng entry > pageSize

Ví dụ:
  5 entry, pageSize=2
  hoặc 12 entry, pageSize=5
~~~

Đặc biệt nên có case tổng entry là **bội số của page size**, bởi server có thể đưa một response tiếp theo để biểu thị kết thúc. Test phải dựa vào continuation cookie chứ không dựa vào kích thước trang.

### 13.3. Kiểm tra rằng cùng underlying connection được dùng

Một test chức năng chạy thành công nhiều trang trên LDAP server đòi connection-bound cookie đã là bằng chứng hữu ích, nhưng không nhất thiết cho bạn một định danh socket rõ ràng. Nếu cần chẩn đoán chính xác, dùng server logs/instrumentation của môi trường test để xác nhận mọi Search trong lượt nằm trên cùng connection.

**Đừng** lấy sự trùng nhau của host, bind DN hoặc địa chỉ IP làm bằng chứng hai request dùng cùng connection. Connection identity khác thông tin endpoint.

### 13.4. Test không được dùng cookie đã kết thúc cho lượt mới

Sau `pager.hasMore() == false`, phải tạo processor mới nếu chạy lại toàn bộ Search. Một test regression nên thực hiện **hai lượt độc lập**, mỗi lượt có processor/context riêng và cùng tập kết quả mong đợi.

Không dùng cùng processor qua hai request HTTP đồng thời; test song song cần tạo hai object hoàn toàn riêng.

## 14. Ma trận kiểm thử lỗi và các trường hợp biên

| Trường hợp | Cách chuẩn bị | Kết quả kỳ vọng |
| --- | --- | --- |
| Trang đầu và trang cuối | 5 entry, pageSize=2 | Đủ 5 entry, cookie cuối rỗng |
| Tổng entry chia hết pageSize | 4 entry, pageSize=2 | Không dừng sai khi trang chứa đúng 2 entry |
| Kết quả rỗng | Filter không khớp | Hoàn tất đúng, không lặp vô hạn |
| Một entry nằm ở OU con | Search SUBTREE | Nhận entry ở OU sâu |
| ONELEVEL | Search ONELEVEL | Không nhận entry nằm sâu hơn 1 cấp |
| Processor tạo lại mỗi trang | Test negative hoặc mô phỏng | Phát hiện lặp/mất cookie, không dùng trong production |
| Mỗi trang lấy connection mới | Test negative với server yêu cầu connection-bound cookie | Có thể bị từ chối; sửa bằng SingleContextSource |
| Cookie bị thay byte | Test giao thức trên server test | Bị từ chối hoặc không hợp lệ; không bao giờ làm thực tế |
| Không có paged response control | Server/proxy thiếu hỗ trợ | Báo lỗi, không giả hoàn thành |
| Page size quá lớn | Server có giới hạn | Điều chỉnh theo chính sách server |
| Count limit thấp hơn tổng | Cấu hình SearchControls | Không báo đã nhận toàn bộ |
| Thay filter giữa các trang | Test negative | Không coi là lượt liên tục hợp lệ |
| Thay sort key giữa các trang | Test có Server-side Sorting | Không được thiết kế như chuỗi bình thường |
| Timeout giữa lượt | Fault injection network | Incomplete; không retry cookie trên connection mới |
| Side effect callback lỗi giữa trang | Consumer test ném exception | Lượt chưa hoàn tất; downstream cần idempotency |
| Entry được thêm/xóa giữa lượt | Thay dữ liệu trong directory test | Ghi nhận kết quả phụ thuộc consistency, cần đối soát |
| ACL che một OU | Bind account read-only hạn chế | Không suy số đếm là toàn directory |
| LDAPS chứng chỉ sai | Truststore/hostname không hợp lệ | Kết nối thất bại an toàn |

### 14.1. Không dựa vào kết quả cụ thể của cookie hỏng trên mọi vendor

Một server có thể trả lỗi khi cookie không hợp lệ, server khác có thể xử lý theo chính sách cụ thể hoặc hết hạn session. Vì vậy test cần kiểm tra **ứng dụng không tuyên bố hoàn thành sai**, không phải cứng nhắc kỳ vọng mọi LDAP server đều trả cùng một mã lỗi.

### 14.2. Diễn giải số lượng entry đúng

Nếu callback xử lý được 401 entry rồi timeout ở trang tiếp theo, con số 401 chỉ là **số đã xử lý trước khi job thất bại**. Không nên dùng nó làm số tổng hoặc đánh dấu báo cáo hoàn tất.

Ghi trạng thái như `INCOMPLETE` và số lượng đã xử lý ở tầng job; khi chạy lại, đối soát để tránh duplicate thay vì cố lưu/copy cookie cũ qua một kết nối mới.

## 15. Thiết kế paging cho production

Một luồng paging ổn định cần quyết định:

1. **Bộ lọc và scope:** xác định tập entry thật sự cần; tránh `(objectClass=*)` trên root lớn nếu không bắt buộc.
2. **Kích thước trang:** chọn dựa trên latency, kích thước attribute, giới hạn server và bộ nhớ.
3. **Underlying connection:** dùng `SingleContextSource` hoặc transaction-aware context đúng phiên bản; không chỉ dựa vào pool.
4. **Cookie processor:** mỗi job có processor riêng, không chia sẻ toàn ứng dụng.
5. **Giới hạn:** max pages, max duration, tốc độ request và giới hạn concurrent jobs.
6. **Downstream:** consumer có idempotency/backpressure hoặc xử lý từng trang hợp lý.
7. **Lỗi:** phân loại server error, timeout, cookie expiry, missing response control; fail khi không chắc đầy đủ.
8. **Kết quả:** chỉ đánh dấu `COMPLETE` sau khi trang cuối và tất cả xử lý downstream bắt buộc thành công.
9. **Consistency:** chấp nhận và đối soát thay đổi đồng thời hoặc dùng chức năng server thích hợp khi cần snapshot.
10. **Observability:** số trang, số entry, thời gian từng request, correlation ID, error code; không log cookie/secrets.

### 15.1. Cẩn thận với page size và bộ nhớ

Page size quá nhỏ tạo nhiều round trips; quá lớn có thể làm một trang mất nhiều RAM hoặc chạm giới hạn server. Không có một page size phù hợp cho mọi directory. Bắt đầu ở một mức hợp lý (ví dụ 100–500 tùy dữ liệu) rồi **đo thực tế trên môi trường tương đương production**.

Nếu mỗi entry chứa dữ liệu nhị phân lớn, thậm chí trang 100 entry có thể rất nặng. Hạn chế returning attributes và không yêu cầu ảnh/chứng chỉ khi chỉ cần UID/cn.

### 15.2. Đừng dùng cookie làm token cho người dùng nhảy trang UI

Nếu UI stateless yêu cầu “trang kế tiếp” nhiều phút hoặc nhiều giờ sau, việc giữ một connection đang mở xuyên HTTP requests có thể tốn tài nguyên và dễ timeout. Không chuyển opaque cookie giữa các máy chủ mà không có hợp đồng server cho phép.

Một giải pháp khác có thể là server-side cursor service có lifecycle ngắn, query tái lập với chính sách consistency, hoặc một cache/snapshot được quản trị; thiết kế phải cân nhắc quyền và tải hệ thống. **Không tự tuyên bố Simple Paged Results là một cursor HTTP bền vững.**

### 15.3. Gắn sorting đúng vị trí

Nếu phải dùng Server-side Sorting, cần kiểm tra server hỗ trợ controls, giữ cùng sort spec và kiểm thử sự ổn định của thứ tự giữa các trang. Sorting ở Java **sau khi nhận một trang** không thay đổi thứ tự tổng thể trên LDAP server.

## 16. Bài thực hành: giữ cookie qua nhiều trang

**Bối cảnh:** ứng dụng đồng bộ những tài khoản `inetOrgPerson` trong `ou=people`, mục tiêu đọc đủ tập entry mà không dùng một List khổng lồ.

1. Chuẩn bị LDAP directory test có 7 entry hợp schema, trong đó ít nhất một entry ở OU con. Chỉ dùng dữ liệu giả.
2. Cấu hình `LdapContextSource` với LDAPS xác minh chứng chỉ, bind identity chỉ đọc và base DN `dc=example,dc=org`.
3. Chọn filter cố định `(objectClass=inetOrgPerson)`, scope SUBTREE và returning attributes `uid`.
4. Đặt `pageSize = 3` và khởi tạo **một** `PagedResultsControlExchangeDirContextProcessor`.
5. Bọc toàn bộ vòng lặp trong `SingleContextSource.doWithSingleContext`; dùng cùng `LdapOperations`.
6. Sau mỗi Search, xem `pager.hasMore()` và chỉ thoát thành công khi không còn cookie.
7. So sánh số kết quả và tập UID với fixture; không phụ thuộc thứ tự do server trả.
8. Làm một bài test âm tính cố tình tạo processor mới ở mỗi trang. Giải thích vì sao trạng thái cookie bị mất và tại sao không làm vậy ở production.
9. Thử giải phóng connection giữa trang một và trang hai trong test riêng. Quan sát rủi ro cookie mất hiệu lực.
10. Thử trang cuối nhỏ hơn 3 entry và case tổng là bội số của 3, không dùng độ dài trang làm điều kiện kết thúc.
11. Bổ sung MAX_PAGES và xử lý timeout; trạng thái lỗi phải là `INCOMPLETE`, không phải `COMPLETE`.
12. Xây consumer xử lý từng UID rồi cho consumer ném lỗi giữa chừng; giải thích nhu cầu idempotency khi chạy lại.
13. Nếu server hỗ trợ sorting, yêu cầu sort theo UID và giữ cấu hình sort giống nhau ở mọi trang; giải thích khác biệt với `List.sort`.
14. Thử ACL hạn chế và TLS certificate sai; không coi 0 kết quả hoặc exception là tổng chính xác của directory.
15. Ghi checklist vận hành: connection lifecycle, paging processor, filter, page size, limit, retries, bảo mật cookie và đối soát.

### Câu hỏi tự kiểm tra

1. Cookie trong RFC 2696 do bên nào tạo ra?
2. Vì sao cookie không phải page number?
3. Điều kiện nào xác nhận lượt paging đã đến cuối?
4. Tại sao `page.size() < pageSize` không đáng tin để dừng?
5. Vì sao cùng host và bind DN không bảo đảm cùng underlying connection?
6. `SingleContextSource` giải quyết vấn đề gì?
7. Nếu dùng connection pool, có tự bảo đảm các trang chung connection không?
8. Tại sao không tạo `PagedResultsControlExchangeDirContextProcessor` trong mỗi vòng lặp?
9. Spring LDAP 4.1+ dùng bộ xử lý nào, phiên bản cũ có API nào?
10. `hasMore()` liên quan như thế nào với response cookie?
11. Điều gì xảy ra khi server không trả paged response control?
12. Vì sao server-side sorting khác client-side sorting từng trang?
13. Cookie có thể dùng để nhảy thẳng tới trang 200 không?
14. Mất kết nối giữa lượt thì có thể dùng lại cookie cũ trên connection mới không?
15. Nếu callback đã ghi một số entry trước khi lỗi, hệ thống có rollback tự động không?
16. Vì sao paging không bảo đảm snapshot nếu dữ liệu LDAP thay đổi trong lúc Search?
17. Khi nào cần dùng LDAP request size bằng 0 với cookie theo RFC 2696?
18. Trong test 5 entry/pageSize=2, kiểm tra gì để phát hiện lặp hoặc mất trang?

## 17. Tổng kết

**Giữ cookie đúng trong toàn bộ lượt phân trang** nghĩa là: bắt đầu với cookie rỗng, lấy continuation cookie từ response control, dùng đúng cookie đó ở Search tiếp theo và chỉ kết thúc khi server báo cookie rỗng. Với **Spring LDAP**, `PagedResultsControlExchangeDirContextProcessor` (từ 4.1) hoặc processor legacy theo phiên bản giúp quản lý cookie; **`SingleContextSource` giữ cùng LDAP connection** cho các lần Search trong lượt.

Cần giữ ổn định base DN, filter, scope, returning attributes, bind identity và sort specification nếu có. Không tự đổi cookie thành offset, không chia sẻ processor giữa jobs, không coi `countLimit` là paging và không retry cookie cũ sau khi connection đã hỏng. LDAP Simple Paged Results cũng **không tự cung cấp thứ tự sort hay snapshot bất biến**. Kết hợp TLS đã xác minh, ACL tối thiểu, giới hạn tài nguyên, idempotency/downstream reconciliation và integration test nhiều trang giúp dữ liệu được duyệt chính xác hơn và an toàn khi vận hành.

### Tài liệu tham khảo

- RFC 2696 — LDAP Control Extension for Simple Paged Results: https://www.rfc-editor.org/rfc/rfc2696
- Spring LDAP — Processing the DirContext, Paged Search Results: https://docs.spring.io/spring-ldap/reference/processing-the-dircontext.html
- Spring LDAP API — PagedResultsControlExchangeDirContextProcessor: https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/control/PagedResultsControlExchangeDirContextProcessor.html
- Spring LDAP API — SingleContextSource: https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/core/support/SingleContextSource.html
- RFC 2891 — LDAP Control Extension for Server Side Sorting of Search Results: https://www.rfc-editor.org/rfc/rfc2891




