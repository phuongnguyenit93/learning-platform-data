# Đóng context đúng cách và vòng đời tài nguyên trong JNDI và Spring LDAP

Trong ứng dụng Java truy cập LDAP, một lời gọi tìm kiếm có thể đã trả về danh sách người dùng đúng nhưng vẫn gây rò rỉ tài nguyên nếu `DirContext` hoặc `NamingEnumeration` không được giải phóng. Lỗi này thường chỉ xuất hiện sau thời gian chạy dài: số kết nối tăng dần, pool hết context khả dụng, request chờ lâu hoặc máy chủ LDAP từ chối thêm kết nối. Ngược lại, **đóng context quá sớm** khiến một đối tượng kết quả còn đang sử dụng tài nguyên mạng không thể đọc tiếp.

Bài học thuộc chương **JNDI và Spring** của **Spring LDAP**. Bạn sẽ hiểu ai sở hữu tài nguyên trong từng API, khi nào phải gọi `close()`, cách xử lý cả kết quả tìm kiếm lẫn lỗi phát sinh giữa chừng, và cách `ContextSource`, `LdapTemplate`, `LdapClient`, pooling và TLS ảnh hưởng đến vòng đời kết nối.

## 1. Phân biệt context, kết nối và kết quả tìm kiếm

**JNDI** (*Java Naming and Directory Interface*) cung cấp các interface Java truy cập dịch vụ tên/thư mục. Với LDAP, những đối tượng đáng quan tâm là:

| Đối tượng | Vai trò | Ai phải quản lý vòng đời? |
|---|---|---|
| `Context` / `DirContext` | Điểm truy cập để lookup, search, bind, modify, unbind... | Đoạn mã tạo/mượn context, trừ khi một API cấp cao đã nhận trách nhiệm quản lý |
| `LdapContext` | Mở rộng `DirContext` để hỗ trợ LDAP controls và extended operations | Chủ sở hữu context |
| `NamingEnumeration<T>` | Duyệt dần tập kết quả của thao tác JNDI, ví dụ `search()` | Đoạn mã nhận enumeration, nếu framework không tự quản lý |
| `SearchResult` / `Attributes` | Dữ liệu của một kết quả tìm kiếm | Thông thường là dữ liệu đọc từ enumeration, không có `close()` riêng |
| Kết nối mạng LDAP | Socket hoặc phiên trao đổi với LDAP server | JNDI provider hoặc pool quản lý theo chính sách kết nối |
| `ContextSource` trong Spring LDAP | Nhà cung cấp các context cho mỗi thao tác | Thường là bean sống theo ứng dụng; không đóng bean sau từng request |
| `LdapTemplate` / `LdapClient` | API Spring LDAP thực thi thao tác, lấy và trả context trong phạm vi lời gọi | Framework quản lý context của thao tác; code ứng dụng quản lý dữ liệu trả về |

**`DirContext` không hoàn toàn đồng nghĩa với một TCP socket.** Context là đối tượng JNDI đại diện cho môi trường làm việc và trạng thái truy cập LDAP. Tùy JNDI provider và pool, một context có thể sử dụng kết nối được chia sẻ/tái sử dụng. Gọi `close()` là cách **trả/giải phóng tài nguyên mà mình sở hữu**, nhưng với pooling nó có thể trả kết nối về pool thay vì đóng socket vật lý ngay lập tức.

Cần phân biệt rõ hai kiểu sở hữu:

1. **Tự lấy context** từ `ContextSource.getReadOnlyContext()`, `getReadWriteContext()` hoặc tạo `InitialDirContext`: code ứng dụng phải đảm bảo đóng.
2. **Gọi `LdapTemplate` hoặc `LdapClient`** để tìm kiếm/ghi dữ liệu: framework thường lấy và giải phóng context trong phạm vi thao tác; code gọi không tự đóng context bên trong framework.

## 2. Vòng đời chuẩn của một thao tác JNDI

Một thao tác tìm kiếm trực tiếp với JNDI thường diễn ra như sau:

~~~mermaid
flowchart TD
    A["Lấy DirContext"] --> B["Tạo SearchControls/filter"]
    B --> C["Gọi search()"]
    C --> D["Nhận NamingEnumeration"]
    D --> E["Duyệt và chuyển kết quả thành dữ liệu độc lập"]
    E --> F["Đóng NamingEnumeration"]
    F --> G["Đóng / trả DirContext"]
    G --> H["Trả DTO/List cho tầng gọi"]
    C --> X["Có exception"]
    D --> X
    E --> X
    X --> F
~~~

**Nguyên tắc:** sau khi lấy được context, mọi nhánh điều khiển đều phải đi qua đoạn giải phóng của context. Tương tự, khi `search()` đã trả về enumeration, mọi nhánh đều phải đóng enumeration, kể cả khi chỉ đọc một phần kết quả, người dùng hủy request hoặc phát sinh exception.

### Vì sao phải đóng `NamingEnumeration`?

`DirContext.search(...)` thường trả về một `NamingEnumeration<SearchResult>`. Tùy provider, enumeration có thể giữ trạng thái duyệt kết quả hoặc tài nguyên truy vấn của máy chủ. Nó có thể truy cập mạng **trong lúc gọi `hasMore()` hoặc `next()`**, chứ không nhất thiết tải xong toàn bộ dữ liệu khi `search()` trả về.

Ví dụ sai:

~~~java
NamingEnumeration<SearchResult> results =
        ctx.search("ou=people", "(objectClass=person)", controls);

if (results.hasMore()) {
    return results.next().getName();
}

// Quên đóng results.
// Nếu ctx được lấy từ ContextSource và cũng không đóng:
// có thể giữ tài nguyên lâu hơn dự kiến.
~~~

Đọc chỉ một dòng rồi `return` không đồng nghĩa provider đã hết công việc. Ngay cả khi duyệt hết kết quả, nên gọi `NamingEnumeration.close()` để chủ động giải phóng.

> `NamingEnumeration` và interface `Context` chuẩn của JNDI có phương thức `close()` nhưng **không khai báo kế thừa `AutoCloseable`**. Vì vậy không mặc định dùng trực tiếp `try (DirContext ctx = ...)` hay `try (NamingEnumeration<?> results = ...)` như với `InputStream`. Hãy dùng `try/finally` hoặc một adapter tự quản lý nếu thực sự cần try-with-resources.

## 3. Mẫu đúng: đóng enumeration trước, rồi đóng context

Giả sử `ContextSource` được cấu hình với base DN `dc=example,dc=org`, yêu cầu tìm người dùng dưới `ou=people`. Mã Java sau minh họa khi **phải dùng JNDI trực tiếp**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.logging.Level;
import java.util.logging.Logger;

import javax.naming.NamingEnumeration;
import javax.naming.NamingException;
import javax.naming.directory.Attribute;
import javax.naming.directory.DirContext;
import javax.naming.directory.SearchControls;
import javax.naming.directory.SearchResult;

import org.springframework.ldap.core.ContextSource;
import org.springframework.ldap.support.LdapUtils;

public final class RawJndiPersonReader {
    private static final Logger LOG =
            Logger.getLogger(RawJndiPersonReader.class.getName());

    private final ContextSource contextSource;

    public RawJndiPersonReader(ContextSource contextSource) {
        this.contextSource = contextSource;
    }

    public List<String> findCommonNames(String uid) throws NamingException {
        DirContext ctx = null;
        NamingEnumeration<SearchResult> results = null;

        try {
            ctx = contextSource.getReadOnlyContext();

            SearchControls controls = new SearchControls();
            controls.setSearchScope(SearchControls.SUBTREE_SCOPE);
            controls.setCountLimit(100);
            controls.setReturningAttributes(new String[] {"cn"});

            // DN tương đối với base đã cấu hình trong ContextSource.
            // JNDI cung cấp filterArgs để xử lý giá trị filter.
            results = ctx.search(
                    "ou=people",
                    "(&(objectClass=inetOrgPerson)(uid={0}))",
                    new Object[] {uid},
                    controls
            );

            List<String> names = new ArrayList<>();

            while (results.hasMore()) {
                SearchResult item = results.next();
                Attribute cn = item.getAttributes().get("cn");

                if (cn != null) {
                    names.add((String) cn.get());
                }
            }

            return names; // finally vẫn được chạy
        } finally {
            if (results != null) {
                try {
                    results.close();
                } catch (NamingException closeFailure) {
                    LOG.log(Level.WARNING,
                            "Cannot close LDAP search results",
                            closeFailure);
                }
            }

            // Đóng context được code mượn từ ContextSource.
            LdapUtils.closeContext(ctx);
        }
    }
}
~~~

Những điểm quan trọng trong mẫu:

- `ctx` và `results` được khởi tạo `null` để phần `finally` xử lý được cả khi lỗi xảy ra trước hoặc sau `search()`.
- `results.close()` chạy trước `LdapUtils.closeContext(ctx)`. Lúc này enumeration được giải phóng khi context vẫn còn hợp lệ.
- Lỗi khi đóng enumeration được ghi nhận riêng; nó không vô tình che khuất lỗi tìm kiếm chính. Không nên bỏ trống `catch` hoặc log dữ liệu nhạy cảm.
- `LdapUtils.closeContext(ctx)` là helper Spring LDAP để đóng context theo cách an toàn, kể cả khi biến `ctx` là `null`. Nếu chỉ dùng JNDI thuần, bạn có thể gọi `ctx.close()` trong `finally` và tự xử lý `NamingException`.
- Mã biến kết quả thành `List<String>` trước khi đóng context. Danh sách này không phụ thuộc vào enumeration hay kết nối.
- `SearchControls` giới hạn nhánh, số kết quả trả về và các attribute cần lấy; đây là cách giảm lượng dữ liệu xử lý nhưng **không thay thế** việc đóng tài nguyên.

Phần code trên làm rõ vòng đời, không phải mẫu phải sử dụng cho mọi truy vấn Spring LDAP. Khi không có yêu cầu JNDI đặc biệt, `LdapTemplate.search(...)` ngắn hơn và quản lý tài nguyên giúp ứng dụng.

### Đóng context mà vẫn giữ được nguyên nhân lỗi

Một biến thể thủ công như dưới đây cần cẩn thận:

~~~java
finally {
    results.close();
    ctx.close();
}
~~~

Nếu `results` chưa được gán hoặc `results.close()` ném exception, `ctx.close()` có thể không chạy. Nếu thao tác chính đã thất bại và đoạn close ném lỗi mới, lỗi gốc có thể bị che khuất.

Khi viết mã JNDI thuần, hãy bảo đảm cleanup **độc lập** và có cách ghi nhận lỗi cleanup. Ví dụ:

~~~java
finally {
    try {
        if (results != null) {
            results.close();
        }
    } catch (NamingException closeFailure) {
        // Ghi log lỗi đóng enumeration;
        // không bỏ qua việc đóng context.
        logger.log(Level.WARNING, "Failed to close results", closeFailure);
    } finally {
        if (ctx != null) {
            try {
                ctx.close();
            } catch (NamingException closeFailure) {
                logger.log(Level.WARNING,
                        "Failed to close context", closeFailure);
            }
        }
    }
}
~~~

Đây là **mảnh mã minh họa đặt trong lớp đã định nghĩa `logger`, `ctx` và `results`**, không phải phương thức Java độc lập. Trong ứng dụng Spring LDAP, `LdapUtils.closeContext(ctx)` giúp tránh lặp phần xử lý close của context.

## 4. Các nhánh thoát phải được dọn dẹp như nhau

Trong nghiệp vụ thực tế, không chỉ đường đi thành công mới cần cleanup.

| Tình huống | Nguy cơ nếu bỏ quên cleanup | Cách xử lý |
|---|---|---|
| `search()` trả về kết quả rỗng | Context vẫn sống đến khi provider tự thu hồi | `finally` đóng context |
| Chỉ lấy kết quả đầu tiên rồi `return` | Enumeration chưa được duyệt hết | `finally` đóng enumeration và context |
| `hasMore()` hoặc `next()` ném `NamingException` | Tài nguyên đã cấp trước khi lỗi | Giữ cleanup trong `finally` |
| Mapping attribute ném exception | Vòng duyệt dừng đột ngột | Cleanup chạy độc lập với mapping |
| Timeout, giới hạn máy chủ hoặc kết nối đứt | Không còn kết quả hoàn chỉnh | Không tin dữ liệu bán phần; release context |
| Mã gọi hủy xử lý | Context giữ tới cuối vòng đời không xác định | Đưa quyền sở hữu về một phạm vi lời gọi rõ ràng |
| Pool trả về context lỗi | Tài nguyên pool có thể không tái sử dụng được | Cơ chế pool/validation quyết định loại bỏ hoặc tạo lại |

Trong Java, `finally` chạy khi rời khỏi khối `try` bằng cách bình thường hoặc qua `return`, `break` hay exception. Nó không bảo đảm chạy trong mọi tình huống ngoài kiểm soát JVM, chẳng hạn tiến trình bị kết thúc cưỡng bức. Đó là lý do nên kết hợp cleanup tại client với **timeout**, giới hạn số kết nối và giám sát tại server.

### Những gì không nên trả về từ phương thức

Tránh trả trực tiếp `NamingEnumeration<SearchResult>`, `DirContext` hoặc `SearchResult` mà vẫn cần đọc thông qua context đã bị đóng. Với API callback của Spring LDAP cũng tránh giữ tham chiếu context hoặc lazy iterator ở trường của bean để dùng sau này.

Một phương thức repository nên trả **DTO, record hoặc collection đã materialize**, ví dụ:

~~~java
record PersonSummary(String uid, String cn, String mail) {}

List<PersonSummary> findPeople(...);
~~~

Nếu cần tải dữ liệu theo từng trang với khối lượng lớn, hãy thiết kế API phân trang rõ ràng và quản lý vòng đời mỗi truy vấn; không mở context xuyên suốt một request web kéo dài hoặc xuyên suốt cả luồng xử lý không xác định.

## 5. `ContextSource` và `LdapTemplate`: ai đóng tài nguyên?

Trong Spring LDAP, `ContextSource` là thành phần cung cấp context, thường được cấu hình một lần và dùng lại. `LdapContextSource` là một triển khai phổ biến, nhận URL máy chủ, base DN, thông tin bind và cấu hình môi trường JNDI.

~~~mermaid
flowchart LR
    A["Service / Repository"] --> B["LdapTemplate hoặc LdapClient"]
    B --> C["ContextSource"]
    C --> D["DirContext"]
    D --> E["LDAP Server"]
    E --> D
    D --> B
    B --> F["DTO / List / kết quả đã đọc"]
    F --> A
~~~

### 5.1. Dùng `LdapTemplate` cho thao tác thông thường

Ví dụ dùng query builder để lấy tên người dùng:

~~~java
import java.util.List;

import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;

import static org.springframework.ldap.query.LdapQueryBuilder.query;

public final class PersonRepository {
    private final LdapTemplate ldapTemplate;

    public PersonRepository(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<String> findNames(String uid) {
        LdapQuery criteria = query()
                .base("ou=people")
                .where("objectClass").is("inetOrgPerson")
                .and("uid").is(uid);

        return ldapTemplate.search(
                criteria,
                (AttributesMapper<String>) attrs ->
                        (String) attrs.get("cn").get()
        );
    }
}
~~~

Với thao tác này, **`LdapTemplate` phụ trách lấy context, thực hiện search, duyệt/map kết quả và đóng tài nguyên liên quan theo hợp đồng API**. Ứng dụng chỉ nhận về `List<String>`. Không có `DirContext` nào để tầng repository tự đóng.

Tương tự, các thao tác lookup, bind, modify và unbind qua `LdapTemplate` thường quản lý tài nguyên trong phạm vi lời gọi. Nếu dùng `LdapClient` (API fluent ở các phiên bản Spring LDAP hỗ trợ), nguyên tắc tương tự: thực thi và hoàn tất kết quả trong phạm vi API được cung cấp; không lưu giữ đối tượng JNDI nội bộ.

### 5.2. Callback được mượn context: đừng tự đóng

Khi cần dùng JNDI trong callback, `LdapTemplate` có API thực thi trên context, ví dụ `executeReadOnly(...)`. Callback sử dụng context **chỉ khi callback đang chạy**:

~~~java
String unit = ldapTemplate.executeReadOnly(ctx ->
        (String) ctx.getAttributes("ou=people")
                .get("ou")
                .get()
);
~~~

Phân biệt rõ:

- Framework **sở hữu** context của `executeReadOnly(...)` và chịu trách nhiệm đóng/trả nó sau callback.
- Callback chỉ **mượn** context, không gọi `ctx.close()`.
- Callback không trả về context, enumeration hay một lambda sẽ dùng context về sau.
- Nếu callback dùng một `NamingEnumeration` mới tạo, phải đảm bảo xử lý enumeration trong callback theo đúng hợp đồng của API đang dùng; không thoát callback khi enumeration vẫn cần đọc.

Có thể coi callback là một “ranh giới sử dụng tài nguyên”: mọi thao tác cần context phải hoàn tất trước khi callback kết thúc.

### 5.3. Khi lấy context từ `ContextSource` ngoài template

Các lời gọi như sau chuyển quyền cleanup về ứng dụng:

~~~java
DirContext context = contextSource.getReadOnlyContext();
try {
    // Thao tác JNDI tự quản lý.
} finally {
    LdapUtils.closeContext(context);
}
~~~

Dùng `getReadWriteContext()` cho thao tác ghi khi cấu hình nguồn context cho phép. Đừng gọi các phương thức này trong mỗi luồng xử lý rồi giữ context vào singleton để “tiết kiệm mở kết nối”: quản lý kết nối phải giao cho `ContextSource`/pool.

## 6. Authentication: context bind bằng danh tính người dùng cũng phải đóng

Một quy trình xác thực LDAP có thể cần bind bằng DN và mật khẩu người dùng. Khi lấy context qua `ContextSource.getContext(principal, credentials)`, tài nguyên này thường chỉ cần sống trong một lần xác thực.

~~~java
import javax.naming.directory.DirContext;
import org.springframework.ldap.core.ContextSource;
import org.springframework.ldap.support.LdapUtils;

public boolean bindCredentials(
        ContextSource source,
        String userDn,
        String password) {

    if (password == null || password.isEmpty()) {
        return false; // Không để mật khẩu rỗng trở thành anonymous bind.
    }

    DirContext userContext = null;
    try {
        // Mở context với danh tính và credentials của người dùng.
        userContext = source.getContext(userDn, password);
        return true;
    } finally {
        LdapUtils.closeContext(userContext);
    }
}
~~~

**Đoạn mã trên chỉ cho thấy vòng đời tài nguyên**: lỗi xác thực sẽ phát sinh từ JNDI/Spring LDAP và cần được lớp gọi xử lý thành kết quả phù hợp. Không nên bao một `catch (Exception)` trả `false` cho mọi lỗi, bởi như vậy nhầm lỗi hạ tầng (timeout, chứng chỉ TLS, server down) với mật khẩu sai.

Với các ứng dụng thông thường, nên cân nhắc `LdapTemplate.authenticate(...)` để Spring LDAP thực hiện quy trình xác thực và cleanup theo API của nó, ví dụ:

~~~java
boolean authenticated = ldapTemplate.authenticate(
        query().base("ou=people").where("uid").is(uid),
        password
);
~~~

Nên xác thực kết nối TLS trước khi gửi mật khẩu, từ chối input mật khẩu trống nếu phương thức authentication của ứng dụng yêu cầu và không log password hoặc thông tin nhạy cảm. Đừng truyền context đã bind bằng tài khoản người dùng ra ngoài phạm vi xác thực để tái sử dụng cho các request khác.

## 7. Khi dùng connection pooling, `close()` vẫn cần thiết

Pool giúp tái sử dụng kết nối hoặc context phù hợp để giảm chi phí thiết lập kết nối liên tục. Vòng đời có thể là:

~~~text
Không dùng pool:
  create context -> search -> close context -> provider giải phóng tài nguyên

Có pool:
  borrow context -> search -> close context -> return to pool
                                       |
                                       v
                           context có thể được tái sử dụng
~~~

Trong Spring LDAP có các lựa chọn pooling tùy phiên bản/cấu hình, ví dụ cơ chế pool của JNDI provider hoặc thành phần pooling quanh `ContextSource`. Không phải cơ chế nào cũng có cùng hành vi, đặc biệt với authentication, LDAP controls và TLS.

**Vẫn phải gọi `close()` cho context do mình mượn**, kể cả khi biết có pool; lúc này `close()` thường biểu thị “trả lại cho pool”. Nếu bỏ quên, số context đang được mượn (*active/borrowed*) có thể tăng đến giới hạn và các request tiếp theo phải chờ hoặc bị lỗi.

Các điểm cần nhớ:

- **Không chia sẻ một `DirContext` giữa nhiều thread**. Context và trạng thái LDAP của nó không nên được xem là đối tượng dùng chung thread-safe.
- **Không lưu context trong singleton** để giảm chi phí mở; giữ một `ContextSource` hoặc `LdapTemplate` dùng chung theo thiết kế Spring.
- **Không trộn context bind người dùng với context dịch vụ** một cách thiếu kiểm soát; cần hiểu pool phân nhóm kết nối theo danh tính/xác thực và loại context ra sao.
- **Giới hạn kích thước pool, thời gian chờ, idle và validation** phù hợp tải thực tế; những cơ chế và tên thuộc tính cấu hình phụ thuộc thư viện đang dùng.
- **Mọi thao tác mượn phải có thao tác trả**, kể cả khi ném exception hoặc khi chỉ đọc một phần kết quả.
- Khi ứng dụng dừng, để Spring quản lý vòng đời/destroy của các bean pool theo hợp đồng thư viện, thay vì tự đóng bean nguồn context sau từng request.

### Pool không thay thế timeout

Nếu LDAP server không phản hồi, một request có thể giữ context được mượn lâu. Tùy JNDI provider, cần cân nhắc các timeout kết nối/đọc; ví dụ thuộc tính `com.sun.jndi.ldap.connect.timeout` và `com.sun.jndi.ldap.read.timeout` của LDAP provider trong JDK. Đây là **cấu hình phụ thuộc provider**, không phải chuẩn LDAP hay luôn tương đương với `SearchControls.setTimeLimit(...)`.

Với search, cũng nên cân nhắc `SearchControls.setCountLimit(...)` và giới hạn server hỗ trợ; những giới hạn này giảm công việc và bảo vệ tài nguyên nhưng không thay việc đóng enumeration/context.

### Những thao tác phụ thuộc một phiên làm việc

Một số nghiệp vụ như thao tác nhiều bước, server controls hoặc truy vấn phân trang có thể yêu cầu giữ đúng trạng thái LDAP/context giữa các lời gọi. Khi đó cần chọn API hỗ trợ phạm vi context phù hợp (ví dụ cơ chế thực thi với cùng context của Spring LDAP khi cần) và đảm bảo **giải phóng ở cuối phạm vi**, không đơn giản gọi template riêng lẻ rồi giả định luôn dùng cùng kết nối.

Không nên tự tạo “pool” bằng `static List<DirContext>`. Tái sử dụng an toàn còn liên quan trạng thái bind, lỗi mạng, kết nối idle, TLS và xác thực, chứ không chỉ cất giữ object.

## 8. LDAP qua TLS và tài nguyên bổ sung

LDAP vận chuyển dữ liệu có thể dùng **LDAPS** (thường port 636) hoặc **StartTLS** trên kết nối LDAP theo cấu hình máy chủ. Cơ chế nào cũng cần kiểm tra chứng chỉ, hostname và trust chain phù hợp để bảo vệ thông tin đăng nhập cũng như dữ liệu thư mục.

Với LDAPS, vòng đời `DirContext` vẫn theo các quy tắc đã trình bày. Với **StartTLS** dùng trực tiếp JNDI, ứng dụng có thể nhận thêm `StartTlsResponse` từ một extended operation; đối tượng này có phương thức `close()` riêng để kết thúc lớp TLS theo hợp đồng API.

Các lưu ý vòng đời khi dùng StartTLS:

1. Mở kết nối và đàm phán TLS trước khi gửi thông tin bind nhạy cảm.
2. Quản lý `StartTlsResponse` và `LdapContext` trong phạm vi rõ ràng; đóng theo đúng trình tự do API/provider quy định và đảm bảo context cuối cùng được đóng.
3. Không coi một kết nối đã hủy TLS là kênh an toàn để tiếp tục gửi credentials.
4. Tránh ghép StartTLS tùy tiện với pool không hỗ trợ reset/validation trạng thái TLS. Xem tài liệu của provider và thư viện pooling thực tế.

Ví dụ này chỉ nêu **nguyên tắc**; triển khai StartTLS đầy đủ còn cần trust manager, kiểm tra danh tính máy chủ, xử lý handshake và chính sách tái sử dụng kết nối. Không bỏ qua xác thực chứng chỉ chỉ để giảm lỗi kết nối khi kiểm thử.

## 9. Những lỗi vòng đời thường gặp

| Sai lầm | Vì sao gây vấn đề | Cách sửa |
|---|---|---|
| Lấy `DirContext` rồi `return` trước đoạn close | Bỏ qua giải phóng nếu không có `finally` | Đặt close trong `finally` |
| Duyệt một phần `NamingEnumeration` và thoát | Có thể giữ tài nguyên kết quả tìm kiếm | Đóng enumeration dù chưa duyệt hết |
| Đóng context trước khi duyệt enumeration xong | Iterator phụ thuộc phiên LDAP bị mất | Materialize dữ liệu, đóng enumeration rồi context |
| Dùng try-with-resources trực tiếp với `DirContext` JNDI chuẩn | Interface không triển khai `AutoCloseable` | Dùng `try/finally` hoặc wrapper có hợp đồng close |
| Đóng context trong callback `LdapTemplate.executeReadOnly` | Framework vẫn cần hoàn tất quản lý context | Callback dùng context trong phạm vi được mượn |
| Trả enumeration từ callback | Tài nguyên đã bị đóng khi callback kết thúc | Trả DTO/List đã đọc xong |
| Giữ context trong field của singleton | Chia sẻ trạng thái không an toàn và làm cạn pool | Dùng bean `ContextSource`/`LdapTemplate` |
| Nghĩ `close()` sẽ luôn đóng TCP socket | Với pool, close có thể trả tài nguyên về pool | Đánh giá pool bằng metric active/idle và kiểm tra server |
| Dùng một lệnh `catch (Exception)` che mọi lỗi | Không phân biệt auth, schema, timeout, kết nối | Xử lý theo nhóm lỗi và ghi log an toàn |
| Rò rỉ `StartTlsResponse` hay tái sử dụng phiên TLS sai | Kết nối/tầng mã hóa còn trạng thái không mong muốn | Quản lý rõ vòng đời TLS và chính sách pooling |

### Dấu hiệu vận hành đáng chú ý

- Pool báo tất cả context đang được mượn, ít hoặc không có context khả dụng.
- Sau mỗi đợt tìm kiếm thất bại, số kết nối đang mở trên LDAP server không trở về mức bình thường.
- Request thao tác LDAP bị treo lâu dù log cho biết câu lệnh search đã bắt đầu.
- Các vấn đề chỉ tái hiện khi có nhiều request đồng thời, không xuất hiện ở thử nghiệm đơn lẻ.

Tuy vậy, số kết nối ổn định ở mức cao **chưa chứng minh bị rò rỉ**: pool có thể cố tình giữ các kết nối idle. Cần đối chiếu số context active/idle, tốc độ request, thời gian chờ, timeout và cấu hình pool.

## 10. Kiểm thử xử lý tài nguyên

Để kiểm tra mã sử dụng LDAP một cách thực tế, thiết kế một số kịch bản:

1. **Thành công:** tạo/đọc nhiều entry, kết quả mapping đầy đủ, số context đang mượn trở về mức ban đầu sau mỗi thao tác.
2. **Kết quả rỗng:** filter không khớp nhưng context vẫn phải được trả.
3. **Dừng sớm:** chỉ đọc một phần enumeration và `return`; cleanup vẫn được gọi.
4. **Lỗi giữa vòng lặp:** giả lập `NamingException` khi `hasMore()`, `next()` hoặc mapping, xác nhận đóng enumeration và context.
5. **Sai credentials:** các lần bind thất bại không tích lũy context.
6. **Timeout/kết nối đứt:** request kết thúc theo chính sách timeout và pool không giữ context hỏng vô hạn.
7. **Nhiều thread:** chạy đồng thời đủ lớn để thấy pool active tăng rồi giảm, không có lỗi do dùng chung context.

Khi có thể, dùng LDAP server thử nghiệm hoặc môi trường tích hợp cô lập, với cấu hình TLS và schema đại diện cho production. Unit test giả lập JNDI có ích để kiểm tra thứ tự/nhánh `close()`; bài test tích hợp mới cho biết hành vi pool, server control và socket thực tế.

Không khẳng định đã hết rò rỉ chỉ vì một test trả đúng dữ liệu. Điều cần kiểm tra là **kết quả nghiệp vụ đúng đồng thời tài nguyên được giải phóng trong cả đường thành công và đường lỗi**.

## 11. Bài tập tình huống

### Tình huống A: tìm kiếm sớm một người

Đoạn mã sau có lỗi vòng đời ở đâu?

~~~java
DirContext ctx = contextSource.getReadOnlyContext();
NamingEnumeration<SearchResult> results =
        ctx.search("ou=people", "(uid=linh)", controls);

if (results.hasMore()) {
    return results.next().getName();
}
return null;
~~~

**Lời giải:** cả `results` lẫn `ctx` đều không được đóng, kể cả khi có kết quả. Sửa bằng `try/finally` với cleanup cho từng đối tượng; hoặc thay truy vấn thủ công bằng `LdapTemplate.search(...)` rồi trả dữ liệu độc lập. Khi mã có thêm user input, nên dùng filter argument API hoặc query builder thay cho phép nối chuỗi filter.

### Tình huống B: callback trả kết quả lười

~~~java
NamingEnumeration<SearchResult> found =
        ldapTemplate.executeReadOnly(ctx ->
                ctx.search("ou=people", "(objectClass=person)", controls)
        );

// Đoạn mã khác đọc found.hasMore() sau callback.
~~~

**Lời giải:** callback trả enumeration còn cần context, trong khi `executeReadOnly` đã kết thúc phạm vi sử dụng context. Sửa bằng cách duyệt toàn bộ kết quả bên trong callback, đóng enumeration ở đó và chỉ trả DTO/List; tốt hơn, dùng trực tiếp API search của `LdapTemplate`. Không gọi `ctx.close()` bên trong callback.

### Tình huống C: bật pooling nhưng tải cao vẫn hết kết nối

Giả sử pool có giới hạn 20 context; mỗi lần chạy search, code lấy context và có một nhánh `return` sớm không đóng. Sau nhiều request, pool báo không còn context khả dụng.

**Lời giải:** việc bật pool không sửa được rò rỉ logic. Chuyển cleanup vào `finally` hoặc dùng `LdapTemplate`; sau đó kiểm thử lại nhánh `return`, exception, timeout và theo dõi số context đang mượn. Chỉ tăng kích thước pool sẽ hoãn thời điểm cạn tài nguyên mà không giải quyết nguyên nhân.

## 12. Câu hỏi tự kiểm tra

**1. Đã gọi `NamingEnumeration.hasMore()` đến khi trả `false`, còn cần `close()` không?**

*Nên có.* Không nên dựa vào giả định provider đã giải phóng mọi tài nguyên ngay khi duyệt hết; hãy chủ động đóng enumeration.

**2. Dùng `LdapTemplate.search(...)` thì ai đóng `DirContext`?**

*Spring LDAP* quản lý context trong phạm vi thao tác. Repository chỉ xử lý danh sách/DTO trả về và không đóng context nội bộ.

**3. Vì sao không để `DirContext` ở field của Spring singleton?**

Context có trạng thái và không được coi là đối tượng dùng chung an toàn cho nhiều luồng. Việc giữ lâu còn làm sai mô hình mượn/trả khi sử dụng pool.

**4. Pool có khiến `close()` trở nên thừa không?**

*Không.* Với pool, `close()` có thể chính là tín hiệu trả context/kết nối, giải phóng suất sử dụng cho request khác.

**5. Thứ tự cleanup hợp lý khi mã tự gọi `search()` là gì?**

Đóng `NamingEnumeration` trước, rồi đóng `DirContext` trong mọi nhánh. Xử lý lỗi close sao cho không bỏ qua thao tác cleanup tiếp theo.

**6. Khi Spring callback được truyền một `DirContext`, có được đưa context ra ngoài callback để dùng sau không?**

*Không nên.* Callback chỉ mượn context trong thời gian được cấp; dùng ngoài phạm vi có thể gặp context đã bị đóng hoặc trả về pool.

## Tài liệu tham khảo

- [Oracle JNDI `Context`](https://docs.oracle.com/javase/8/docs/api/javax/naming/Context.html): hợp đồng `close()` của context.
- [Oracle JNDI `NamingEnumeration`](https://docs.oracle.com/javase/8/docs/api/javax/naming/NamingEnumeration.html): cách duyệt và đóng enumeration.
- [Oracle JNDI `DirContext`](https://docs.oracle.com/javase/8/docs/api/javax/naming/directory/DirContext.html): tìm kiếm và các thao tác thư mục.
- [Spring LDAP Reference](https://docs.spring.io/spring-ldap/reference/): `ContextSource`, `LdapTemplate`, quản lý context và các API truy cập LDAP.
- [RFC 4511 — LDAP Protocol](https://www.rfc-editor.org/rfc/rfc4511): hành vi giao thức liên quan đến thao tác LDAP và kết quả tìm kiếm.

## Ghi nhớ

Trong **JNDI**, đoạn mã trực tiếp mở hoặc mượn `DirContext` chịu trách nhiệm đóng context; đoạn mã nhận `NamingEnumeration` trực tiếp cũng phải đóng enumeration, kể cả khi có `return` hay exception. Trong **Spring LDAP**, hãy ưu tiên `LdapTemplate`/`LdapClient` cho thao tác thông thường để framework đảm nhiệm phạm vi tài nguyên; nếu nhận context qua callback, chỉ dùng trong callback. Pooling, TLS và timeout làm thay đổi cách kết nối được quản lý, nhưng **không thay đổi trách nhiệm trả tài nguyên đúng thời điểm**. Khi nắm chắc điều này, ứng dụng có thể truy cập LDAP qua DN, filter, thao tác entry và xác thực một cách ổn định ngay cả dưới tải và khi lỗi xảy ra.
