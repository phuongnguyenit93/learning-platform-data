# Không đưa context đã bị đóng trở lại pool

## 1. Vấn đề và mục tiêu

Trong **Spring LDAP**, ứng dụng Java thường dùng `LdapTemplate`, `LdapClient` hoặc Object-Directory Mapping (ODM) để tìm kiếm, xác thực và sửa entry trong dịch vụ thư mục. Các thao tác này cần một context LDAP do `ContextSource` cung cấp. Việc tạo context mới có thể phải mở kết nối TCP, thương lượng TLS, bind và khởi tạo phiên mạng, nên **pooling** giúp tái sử dụng các kết nối còn khỏe để giảm độ trễ và chi phí hệ thống.

Pool chỉ có ích khi mỗi context được trả lại vẫn **có thể sử dụng an toàn**. Nếu một context thực đã bị đóng, socket đã bị ngắt hoặc phiên TLS/LDAP không còn hợp lệ mà vẫn được đưa vào danh sách rảnh, yêu cầu tiếp theo có thể mượn phải kết nối chết, gặp `CommunicationException` hoặc mất thời gian chờ rồi mới thử lại. Trong hệ thống xác thực và truy cập thư mục, lỗi tái sử dụng context còn có thể ảnh hưởng trạng thái bind hoặc danh tính truy cập.

**Điểm cần phân biệt ngay:** trong pool, lời gọi `close()` có thể mang **hai ý nghĩa khác nhau**:

- Đối với **proxy/context được pool cho mượn**, `close()` thường là thao tác **trả quyền sử dụng (logical close/release)** cho pool. Đối tượng vật lý phía dưới vẫn mở nếu còn khỏe; đó là hành vi bình thường.
- Đối với **context JNDI vật lý**, `close()` đóng tài nguyên mà nó quản lý. Sau khi đóng thực sự hoặc khi context đã hỏng, **không được** đưa nó vào nhóm tài nguyên có thể mượn lại; phải loại bỏ/hủy (*invalidate/destroy*).

Vì vậy, câu “**Không đưa context đã bị đóng trở lại pool**” áp dụng cho **context vật lý đã đóng hoặc không còn hợp lệ**. Nó không có nghĩa cấm client gọi `close()` trên một proxy đang được mượn: trong cơ chế pool phù hợp, chính thao tác đó là cách trả proxy về pool. Bài học hướng dẫn cách quản lý ranh giới này, từ mã Spring LDAP đến xử lý lỗi và kiểm thử.

Sau bài học, bạn có thể nhận diện các trạng thái context, phân biệt `return` với `invalidate`, xử lý lỗi kết nối, tránh dùng context sau khi trả, và xây dựng kiểm thử phát hiện context đã đóng lọt vào pool.

## 2. Vòng đời một LDAP context trong pool

Một pool quản lý nhiều **tài nguyên vật lý** và trao cho bên sử dụng một **handle** tạm thời. Với pool có proxy, handle thường có thể được đóng theo ngữ nghĩa “trả lại” mà không đóng socket vật lý ngay. Khi context vật lý bị lỗi, pool phải loại nó thay vì tái sử dụng.

~~~mermaid
flowchart LR
    NEW["Tạo context vật lý"] --> IDLE["Rảnh trong pool"]
    IDLE --> BORROW["Được mượn"]
    BORROW -->|Trả handle còn hợp lệ| CHECK["Kiểm tra theo chính sách pool"]
    CHECK -->|Hợp lệ| IDLE
    CHECK -->|Hỏng hoặc đã đóng vật lý| DESTROY["Invalidate / destroy"]
    BORROW -->|Kết nối hỏng hoặc chủ động hủy| DESTROY
    IDLE -->|Hết hạn / eviction / shutdown| DESTROY
    DESTROY --> CLOSED["Đóng tài nguyên vật lý"]
~~~

Sơ đồ mô tả vòng đời khái niệm. Tên trạng thái và thời điểm validation phụ thuộc **pool implementation**. Không phải pool nào cũng kiểm tra trên mọi lần mượn/trả: các cơ chế như `testOnBorrow`, `testOnReturn` hoặc kiểm tra khi rảnh (*idle validation*) cần được cấu hình riêng nếu pool hỗ trợ.

### 2.1. Ba trạng thái không được nhầm lẫn

| Trạng thái | Context vật lý | Handle của bên gọi | Hành động đúng |
| --- | --- | --- | --- |
| Đang được mượn, khỏe | Kết nối hợp lệ | Được phép sử dụng | Thực hiện nghiệp vụ trong phạm vi mượn |
| Handle đã `close()` theo giao ước pool | Có thể vẫn mở và khỏe trong pool | **Không còn được sử dụng** | Pool tiếp nhận lại tài nguyên, nếu hợp lệ |
| Context vật lý đã `close()` hoặc bị hỏng | Không dùng được hoặc không đáng tin | Không thể tiếp tục dùng | Hủy/invalidate, tạo context vật lý mới khi cần |

Một proxy đã được trả về pool **không được giữ lại để tái sử dụng** trong biến của service, field singleton hoặc luồng khác. Pool có thể đã cấp kết nối vật lý đó cho request kế tiếp. Điều này đúng ngay cả khi đối tượng Java chứa handle vẫn còn được tham chiếu.

### 2.2. “Đóng” có thể là return; “hủy” phải chấm dứt tái sử dụng

Giả sử pool trả về `DirContext` dạng wrapper. Bên gọi thực hiện truy vấn rồi gọi `close()`. Pool có thể chặn lời gọi này để đánh dấu handle đã được release và trả context vật lý khỏe vào pool. Khi pool thực sự loại context (vì hỏng, quá tuổi hoặc shutdown), nó mới đóng kết nối bên dưới.

Ngược lại, nếu code tự đóng **delegate vật lý** rồi gọi `returnObject(...)` vào một pool tự xây, pool có thể giữ tham chiếu không còn hoạt động. Một lỗi tương tự xảy ra khi network socket hỏng, StartTLS thất bại hoặc LDAP server đã ngắt phiên nhưng logic vẫn đánh dấu đối tượng là rảnh.

Quy tắc thiết kế: **bên mượn kết thúc quyền sử dụng handle một lần; pool quyết định context vật lý được tái sử dụng hay phải tiêu hủy**.

## 3. Những lỗi dễ mắc trong ứng dụng Spring LDAP

### 3.1. Trả một context vật lý đã đóng vào pool tùy biến

Đây là **mã giả minh họa lỗi**, không phải API của Spring LDAP:

~~~text
ctx = pool.borrowPhysicalContext()
try:
    use(ctx)
finally:
    ctx.close()          # Đóng thật kết nối JNDI/TCP
    pool.return(ctx)     # SAI: pool có thể giữ context đã đóng
~~~

Nếu một pool sở hữu tài nguyên vật lý, thì **pool/factory** phải chịu trách nhiệm đóng chúng khi destroy. Bên dùng không được vừa tự đóng delegate vừa đưa lại nó vào nhóm context hợp lệ. Ngoài nguy cơ kết nối chết, đoạn mã trên còn dễ làm phát sinh thao tác đóng lặp hoặc lỗi quản lý trạng thái.

### 3.2. Giữ một DirContext đã trả về pool

Đây cũng là mã giả minh họa hành vi sai:

~~~text
sharedField = poolingContextSource.getReadOnlyContext()
sharedField.search(...)
sharedField.close()      # Handle được trả về pool
...
sharedField.search(...)  # SAI: sử dụng handle sau khi release
~~~

`DirContext` mang trạng thái kết nối và bind, nên không lưu nó trong field của singleton Spring service để dùng chung giữa request/luồng. Service nên giữ **`LdapTemplate` hoặc `ContextSource`**, còn việc lấy và trả context thuộc phạm vi từng thao tác.

### 3.3. Không phân loại lỗi mạng và lỗi nghiệp vụ

Không phải ngoại lệ LDAP nào cũng chứng minh kết nối vật lý đã hỏng:

- `NameNotFoundException` có thể chỉ là base DN/entry không tồn tại.
- `NoSuchAttributeException` có thể là thuộc tính chưa được lưu trên entry.
- Lỗi LDAP ACL hoặc filter hợp lệ không đồng nghĩa socket không sử dụng được.
- `CommunicationException` hoặc `ServiceUnavailableException` thường là tín hiệu kết nối/network có vấn đề và cần được đánh giá để **loại context khỏi pool**.
- TLS handshake thất bại, socket đóng, hoặc xác thực context bị thay đổi ngoài dự kiến là lý do không nên coi context đó là một phiên khỏe để tái sử dụng.

Không nên “invalidate tất cả khi có bất kỳ exception”, vì sẽ làm tăng churn, tốn kết nối và che giấu lỗi nghiệp vụ. Ngược lại, không được mù quáng `return` khi kết nối bị hỏng.

## 4. Cách viết ứng dụng với LdapTemplate để giữ vòng đời ngắn

Với nghiệp vụ thông thường, **ưu tiên `LdapTemplate` hoặc `LdapClient`**. Chúng che bớt công việc mượn, sử dụng và giải phóng LDAP context. Việc pool có hoạt động hay không phụ thuộc `ContextSource` được cấp cho chúng.

~~~java
import static org.springframework.ldap.query.LdapQueryBuilder.query;

import java.util.List;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.stereotype.Service;

@Service
public class DirectoryLookupService {
    private final LdapTemplate ldapTemplate;

    public DirectoryLookupService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<String> findDisplayNames(String uid) {
        return ldapTemplate.search(
            query().base("ou=people").where("uid").is(uid),
            (AttributesMapper<String>) attributes ->
                (String) attributes.get("displayName").get()
        );
    }
}
~~~

Code nghiệp vụ chỉ giữ `LdapTemplate` dưới dạng dependency, không nắm giữ `DirContext` dùng chung. `LdapTemplate` lấy context cần thiết cho thao tác và dọn dẹp theo giao ước `ContextSource`. Khi nguồn kết nối là **pooling context source**, thao tác kết thúc quyền dùng context trả handle về pool theo cơ chế do wrapper cung cấp.

Điều này không thay thế việc cấu hình **validation, timeout, eviction và hủy context lỗi** ở pool. Một `LdapTemplate` dùng cùng nguồn pool cấu hình thiếu validation vẫn có thể gặp context chết.

### 4.1. Nếu phải làm việc trực tiếp với ContextSource

Một tác vụ đặc biệt có thể cần `DirContext`. Khi đó, giới hạn phạm vi mượn và luôn gọi phương thức đóng theo **giao ước của context được trả về**:

~~~java
import javax.naming.NamingException;
import javax.naming.directory.Attributes;
import javax.naming.directory.DirContext;

import org.springframework.ldap.core.ContextSource;
import org.springframework.ldap.support.LdapUtils;

public final class DirectContextLookup {
    private final ContextSource contextSource;

    public DirectContextLookup(ContextSource contextSource) {
        this.contextSource = contextSource;
    }

    public String readCommonName(String relativeDn) throws NamingException {
        DirContext context = contextSource.getReadOnlyContext();
        try {
            Attributes attributes =
                context.getAttributes(relativeDn, new String[] {"cn"});
            return (String) attributes.get("cn").get();
        } finally {
            // Đóng handle. Nếu đây là proxy pool, pool quyết định release.
            LdapUtils.closeContext(context);
        }
    }
}
~~~

Đây là ví dụ tối giản cho phạm vi sử dụng handle. `LdapUtils.closeContext(...)` giúp dọn context và không nên bị hiểu là thao tác tự động bảo đảm một **kết nối vật lý hỏng** đã được invalidate. Nếu xảy ra lỗi đường truyền, cần dựa vào cơ chế phát hiện/huỷ context hỏng của pooling implementation hoặc xử lý invalidate phù hợp với pool được chọn.

Một điều cần tránh là gọi `close()` trên context, sau đó vẫn tiếp tục dùng chính handle đó; cũng không giữ handle trong callback bất đồng bộ để chạy sau khi method trả về.

### 4.2. Không xem DirContext là thread-safe

LDAP context có thể chứa trạng thái xác thực và phiên giao tiếp. Không truyền một `DirContext` được mượn cho nhiều luồng dùng đồng thời trừ khi có tài liệu chính thức đảm bảo cách sử dụng ấy. Cách thiết kế quen thuộc là để các request độc lập mượn handle độc lập, còn `LdapTemplate` được cấu hình dùng `ContextSource` và quản lý truy cập trong phạm vi mỗi lời gọi.

Nếu xác thực người dùng bằng cách bind trên một context, không để đối tượng đó được tái sử dụng dưới danh tính khác khi pool chưa reset hoặc phân biệt chính xác các loại context. Pool phải bảo toàn ranh giới danh tính và quyền truy cập.

## 5. Phân biệt return, invalidate và destroy ở pool

Những thao tác này phải có ý nghĩa nhất quán:

| Thao tác | Ý nghĩa | Khi nào dùng |
| --- | --- | --- |
| **Borrow** | Nhận quyền dùng một context được pool quản lý | Bắt đầu thao tác LDAP |
| **Return/release** | Trả context **còn hợp lệ** để có thể cấp phát lần sau | Thao tác hoàn tất và kết nối vẫn khỏe |
| **Invalidate** | Đánh dấu đối tượng không thể tái sử dụng | Kết nối chết, socket lỗi, phiên TLS hỏng, trạng thái không tin cậy |
| **Destroy** | Pool/factory đóng kết nối vật lý và giải phóng tài nguyên | Sau invalidate, eviction, hết vòng đời hoặc shutdown |
| **Validate** | Kiểm tra đối tượng có đáp ứng điều kiện sử dụng không | Theo chính sách khi mượn, trả hoặc kiểm tra idle |

Một lỗi thiết kế hay gặp là coi `close()` vật lý như `return`. Ngược lại, khi dùng Spring LDAP pooled wrapper, **`close()` ở handle thường là bước release được pool quản lý**, không có lý do tự truy cập delegate để đóng rồi lại return.

### 5.1. Ví dụ điều phối pool thủ công

Nếu thật sự phải tự quản lý Apache Commons Pool thay vì dùng wrapper Spring LDAP, cần phân nhánh **return hoặc invalidate đúng một lần**. Mã dưới đây chỉ minh họa phần mượn/trả; factory và cấu hình `GenericObjectPool` không được trình bày ở đây:

~~~java
import javax.naming.CommunicationException;
import javax.naming.ServiceUnavailableException;
import javax.naming.directory.Attributes;
import javax.naming.directory.DirContext;
import org.apache.commons.pool2.impl.GenericObjectPool;

public final class PhysicalContextBorrower {
    private final GenericObjectPool<DirContext> pool;

    public PhysicalContextBorrower(GenericObjectPool<DirContext> pool) {
        this.pool = pool;
    }

    public String readCn(String dn) throws Exception {
        DirContext context = pool.borrowObject();
        boolean broken = false;
        try {
            Attributes attributes =
                context.getAttributes(dn, new String[] {"cn"});
            return (String) attributes.get("cn").get();
        } catch (CommunicationException | ServiceUnavailableException ex) {
            broken = true;
            throw ex;
        } finally {
            if (broken) {
                pool.invalidateObject(context);
            } else {
                pool.returnObject(context);
            }
        }
    }
}
~~~

Ở ví dụ này, bên mượn **không gọi `context.close()`** trước `pool.returnObject(context)`. Factory của pool phải đóng context vật lý trong bước destroy, còn validator phải phát hiện đối tượng đóng/hỏng. Cần mở rộng phân loại lỗi theo nhà cung cấp JNDI/LDAP và thử nghiệm lỗi thực tế; `CommunicationException` và `ServiceUnavailableException` chỉ là hai trường hợp minh họa, không phải danh sách đầy đủ mọi tình huống phải invalidate.

Đoạn mã dùng `GenericObjectPool` nhằm giải thích ngữ nghĩa của một pool **tự xây**, không phải hướng dẫn thay thế `PoolingContextSource` của Spring LDAP. Nếu dùng wrapper Spring LDAP, tuân theo API mượn/đóng của wrapper đó; **không tự gọi `returnObject(...)` trên handle từ pooling context source**.

### 5.2. Validation không thể sửa một context đã đóng

Một validator có thể kiểm tra khả năng hoạt động bằng thao tác LDAP nhẹ (ví dụ kiểm tra root DSE hoặc một mục thử nghiệm phù hợp quyền). Nếu phát hiện context đã đóng hoặc không phản hồi, validator phải báo **không hợp lệ** để pool hủy nó; không thể “hồi sinh” cùng đối tượng vật lý bằng cách đặt lại cờ trạng thái.

Không được xem một context là khỏe chỉ vì object Java còn tham chiếu hoặc socket trước đó từng hoạt động. Sau thời gian nhàn rỗi, server có thể đóng session; firewall/NAT có thể hết hạn bảng trạng thái; chứng chỉ hoặc danh tính xác thực có thể thay đổi.

## 6. Spring LDAP pooling và JNDI pooling

Trong hệ sinh thái Spring LDAP có thể gặp hai lớp pooling khác nhau:

1. **Native JNDI LDAP connection pooling:** cơ chế ở phía JNDI provider, có liên quan `LdapContextSource#setPooled(...)`. Việc bật nó không cung cấp toàn bộ khả năng kiểm tra sức khỏe/quan sát như một pool wrapper của ứng dụng.
2. **Spring LDAP pooling support:** pool bao quanh một `ContextSource` và cung cấp các handle được mượn, hỗ trợ cấu hình lifecycle/validation tùy phiên bản và implementation, chẳng hạn các implementation dựa trên Apache Commons Pool.

Với Spring LDAP, nên dùng đúng lớp hỗ trợ pooling tương ứng **phiên bản thư viện thực tế** và cấu hình dựa trên tài liệu phiên bản đó. Không tự giả định tên class, gói thư viện hoặc thuộc tính của `PoolingContextSource` giống hệt giữa mọi thế hệ Spring LDAP.

### 6.1. Đặt validation ở những thời điểm thích hợp

Một pooling implementation có thể hỗ trợ:

| Cơ chế | Mục đích | Chi phí/giới hạn |
| --- | --- | --- |
| Kiểm tra khi mượn (*test on borrow*) | Ngăn cấp context chết cho request mới | Thêm một lần kiểm tra hoặc round trip, tăng độ trễ |
| Kiểm tra khi trả (*test on return*) | Phát hiện một số lỗi trước khi đưa về idle | Thêm chi phí khi kết thúc thao tác; không thay logic invalidate rõ ràng |
| Kiểm tra idle định kỳ | Loại kết nối chết do timeout mạng/server | Cần evictor/validation scheduler; phát hiện không tức thời |
| Giới hạn idle lifetime | Giảm tỷ lệ giữ kết nối quá lâu | Có thể làm tăng số lần mở kết nối |
| Giới hạn kích thước pool và thời gian chờ mượn | Tránh cạn tài nguyên hoặc treo vô hạn | Cần sizing theo tải và số kết nối server cho phép |

Validator cần kiểm tra bằng thao tác đủ nhẹ, có timeout và không làm thay đổi dữ liệu. Tránh health check dựa vào DN/entry chưa chắc tồn tại hoặc cần quyền cao, vì có thể loại nhầm context khỏe.

### 6.2. Lưu ý với StartTLS

**StartTLS** khởi tạo bằng `ldap://`, nâng cấp lên TLS rồi mới bind. Việc tái sử dụng một kết nối vật lý yêu cầu pool giữ nguyên tính hợp lệ của phiên TLS, trạng thái xác thực và cách đóng context. Vì vậy:

- Không bật **native JNDI pooling** cho StartTLS chỉ để giảm thời gian handshake nếu chưa có bằng chứng tương thích.
- Nếu dùng pool wrapper, kiểm chứng cách tạo context mới, chiến lược TLS, validation, close/release và destroy.
- Khi StartTLS handshake thất bại, phải hủy kết nối đang ở trạng thái chưa bảo vệ; **không đưa nó vào pool để xử lý request kế tiếp**.
- Khi chứng chỉ server/CA hoặc thông tin xác thực thay đổi, quản lý vòng đời pool để context cũ không tiếp tục dùng trạng thái không còn được chấp nhận.

Với LDAPS, kết nối cũng có thể chết do network, server restart hoặc thay đổi chính sách TLS. LDAPS không làm mất yêu cầu validation; nó chỉ khác thời điểm bắt tay TLS.

### 6.3. Không nhầm đóng handle với đóng socket

Giả sử `LdapTemplate` đã hoàn tất tìm kiếm và release context. Nếu pool trả context vật lý này về trạng thái idle thì **đúng**. Chỉ khi lỗi ở dưới đã khiến kết nối vật lý không hợp lệ, pool mới phải destroy.

Để kiểm thử chính xác, log/metric nên phân biệt **release của handle**, **validation failure**, **invalidate** và **physical close**. Đếm mọi lời gọi `close()` như “đã đóng socket” sẽ tạo kết luận sai về tỷ lệ tái sử dụng.

## 7. Khi nào không được return một context?

| Tình huống quan sát được | Đánh giá | Hành động hợp lý |
| --- | --- | --- |
| Search hợp lệ, context vẫn kết nối và xác thực đúng | Có thể tái sử dụng | Release qua pool wrapper/return theo hợp đồng |
| Không tìm thấy entry, LDAP server trả lỗi nghiệp vụ bình thường | Context có thể vẫn khỏe | Không mặc định invalidate; phân loại lỗi |
| Socket bị đóng, connection reset, server ngắt phiên | Kết nối vật lý không còn tin cậy | Invalidate/destroy |
| `CommunicationException` hoặc lỗi mạng nghiêm trọng | Có khả năng context hỏng | Invalidate hoặc kiểm tra cụ thể theo hợp đồng pool |
| TLS handshake/StartTLS thất bại | Kênh chưa được xác lập an toàn | Đóng và hủy, không bind hay return |
| Context vật lý đã bị gọi `close()` trực tiếp | Không thể dùng lại | Không return; destroy/loại bỏ |
| Handle pooled proxy đã release bằng `close()` | Bên mượn không còn quyền dùng | Không dùng handle lần nữa; pool tự quyết định tài nguyên vật lý |
| Lỗi xác thực làm thay đổi trạng thái bind hoặc nghi ngờ rò rỉ danh tính | Trạng thái context không bảo đảm đúng quyền | Không trả vào pool dùng chung; xử lý theo chính sách pool/danh tính |
| Pool shutdown hoặc object bị evict | Không còn thuộc pool hoạt động | Đóng vật lý qua factory |

Nếu lỗi không rõ đã làm mất trạng thái kết nối hay chưa, ưu tiên **không cấp lại** context đó trước khi có validation phù hợp. Việc loại bỏ một kết nối có chi phí, nhưng cấp lại một kết nối không an toàn có thể kéo theo lỗi liên tiếp hoặc lẫn quyền truy cập.

### 7.1. Tránh double close và double return

Với wrapper pooled:

~~~text
handle = poolingContextSource.getReadOnlyContext()
try:
    performSearch(handle)
finally:
    handle.close()     # Một lần, theo hợp đồng release của pool
    # Không gọi thêm pool.returnObject(handle)
    # Không gọi handle.search(...) sau khi close
~~~

Đoạn trên là **mã giả**. Nếu dùng API `LdapTemplate`, chính template đã xử lý việc kết thúc context; không thêm một lớp `close()` do service gọi. Nếu tự dùng `ContextSource`, có thể dùng `LdapUtils.closeContext(...)` theo kiểu ví dụ ở mục 4.1.

Trong một pool tự viết, cần đảm bảo mỗi lần borrow dẫn đến **một** trong hai nhánh kết thúc: return hoặc invalidate. Gọi cả hai, gọi lặp, hoặc return sau physical close sẽ làm hỏng kế toán pool, cạn connection hoặc gây lỗi tái sử dụng.

## 8. Chẩn đoán và quan sát lỗi context chết

Các triệu chứng thường gặp của việc context đã đóng bị đưa trở lại pool:

- Request đầu tiên sau thời gian idle gặp lỗi như `javax.naming.CommunicationException` hoặc `javax.naming.NamingException` liên quan kết nối đã đóng.
- Lỗi xuất hiện thành đợt sau khi LDAP server restart, load balancer reset hoặc firewall timeout.
- Pool ghi số context idle cao nhưng tỷ lệ mượn thành công thấp, kéo theo retry nhiều lần.
- Một context mượn lại báo “context is closed” hoặc lỗi socket dù vừa được trả về.
- Thao tác qua `LdapTemplate` bị timeout hoặc nhiều request đồng thời chờ vì pool bị lấp đầy tài nguyên chết.

Không kết luận tất cả lỗi kể trên đều do pool; DNS, TLS, chứng chỉ, ACL và thông tin bind cũng có thể gây lỗi. Cần liên kết thời điểm pool **borrow → validate → operation → return/invalidate → destroy** với triệu chứng từ LDAP server và network.

### 8.1. Các chỉ số nên thu thập

| Chỉ số | Ý nghĩa |
| --- | --- |
| Active / borrowed contexts | Số context đang được sử dụng |
| Idle contexts | Số context rảnh và có thể được mượn |
| Wait time khi mượn | Tín hiệu pool thiếu tài nguyên, leak hoặc hoạt động quá tải |
| Validation failures | Context được phát hiện không hợp lệ khi mượn/trả/idle |
| Invalidations / destroys | Tần suất tài nguyên bị loại bỏ |
| Physical connection creations | Chi phí tạo kết nối mới |
| LDAP operation latency/errors | Tác động tới request và phân biệt lỗi mạng/nghiệp vụ |

Tần suất destroy tăng đột biến sau mỗi đợt server restart có thể là hợp lý. Nếu hầu hết request đều phải tạo lại kết nối và nhiều context chết bị mượn, cần kiểm tra giới hạn idle, validation và cách phân loại lỗi.

### 8.2. Xử lý khi server hoặc proxy tự đóng kết nối idle

Server LDAP thường có giới hạn kết nối, timeout không hoạt động hoặc có thể khởi động lại. Network intermediary cũng có thể đóng phiên idle. Cơ chế pool không nhận được thông báo trước trong mọi trường hợp.

Một cách ứng phó là cấu hình thời gian giữ idle phù hợp, bật validation khi mượn hoặc kiểm tra idle, giới hạn thời gian chờ kết nối và retry **có kiểm soát**. Nếu một request thất bại do kết nối chết, context lỗi phải được loại bỏ trước khi lấy context mới. Với thao tác ghi LDAP, chỉ retry tự động nếu có thể xác định ngữ nghĩa thực thi và **tránh lặp thay đổi** ngoài ý muốn.

## 9. Kiểm thử vòng đời trong môi trường thực hành

### 9.1. Kịch bản tối thiểu

Một môi trường lab có LDAP server thử nghiệm, Spring LDAP và pool được cấu hình nên kiểm tra:

1. **Borrow/return bình thường:** liên tục gọi `LdapTemplate.search(...)` rồi xác minh số context active trở về mức ban đầu; không tăng leak.
2. **Đóng handle:** sau `close()` trên pooled proxy, cố dùng handle cũ phải không được phép theo hợp đồng; request mới phải nhận context được cấp phát hợp lệ.
3. **Đóng vật lý:** ép đóng một context delegate ở môi trường test rồi bảo đảm nó **không** được cấp phát lại như context khỏe.
4. **Server restart:** restart LDAP server khi pool có idle connections; các context chết phải bị loại bỏ, kết nối mới phải được xác thực lại.
5. **Idle timeout:** để kết nối lâu hơn timeout của server/proxy; kiểm tra validation và eviction trước khi cấp cho request.
6. **Network failure:** ngắt đường truyền giữa client và server; lỗi mạng không được khiến context hỏng được đánh dấu idle hợp lệ.
7. **Nhiều request đồng thời:** không dùng chung một context đã mượn giữa các luồng; active count, wait time và borrow/return cân bằng sau khi tải giảm.
8. **TLS failure:** với LDAPS/StartTLS, chứng chỉ sai hoặc handshake lỗi không được đưa context vào pool an toàn; không fallback xuống LDAP rõ.

### 9.2. Bảng kiểm thử kỳ vọng

| Thử nghiệm | Kết quả cần khẳng định |
| --- | --- |
| 100 lần search hợp lệ qua pool | Không giữ context active vô hạn; không có lỗi “closed” |
| Context còn khỏe được release qua wrapper | Pool có thể tái sử dụng tài nguyên vật lý sau validation |
| Context vật lý đã đóng bị đưa vào nhánh return của pool tự xây | Validator phát hiện và loại bỏ; bài test phải thất bại nếu object chết được mượn lại |
| Thử dùng handle sau release | Bị từ chối theo hợp đồng của wrapper, không tạo truy vấn LDAP tiếp theo từ handle cũ |
| Socket reset trong lúc query | Context lỗi bị invalidate/destroy, không trở thành idle khỏe |
| LDAP search trả `NameNotFoundException` | Được xử lý như lỗi nội dung; không mặc định hủy cả pool |
| StartTLS handshake thất bại | Không có simple bind trên kết nối rõ, không return phiên thiếu TLS |
| Pool shutdown | Mọi context idle/active được xử lý theo lifecycle, không cấp phát mới |

Không chạy kiểm thử lỗi mạng và certificate trên tài khoản sản xuất. Nếu cần bắt gói tin để kiểm chứng, chỉ dùng dữ liệu giả trong môi trường có thẩm quyền.

### 9.3. Một thử nghiệm có giá trị hơn kiểm tra riêng hàm return

Thay vì chỉ mock `pool.returnObject(...)` và khẳng định nó được gọi, hãy chạy bài test tích hợp với **một LDAP server thử nghiệm** hoặc fake context có trạng thái `open/closed`:

- Mượn context thứ nhất, đóng vật lý để mô phỏng lỗi, chạy nhánh invalidate.
- Mượn context thứ hai và thực hiện một `search` thực tế.
- Đảm bảo context thứ hai **khác** context vật lý đã bị hủy; không có truy vấn nào chạy qua đối tượng đã đóng.
- Kiểm tra số lần destroy và số tài nguyên active/idle cuối bài test.

Nhờ đó, kiểm thử chứng minh **hành vi quan sát được** thay vì chỉ lặp lại câu lệnh trong implementation.

## 10. Tình huống thực tế: lỗi sau khi LDAP server restart

**Bối cảnh:** Một ứng dụng nội bộ dùng `LdapTemplate` để tìm người dùng và kiểm tra `memberOf` trên LDAPS. Để giảm độ trễ, nhóm phát triển tự xây pool `DirContext` với kích thước tối đa 20. Sau mỗi thao tác, code gọi:

~~~text
finally:
    context.close()
    pool.returnObject(context)
~~~

Sau khi LDAP server restart vào ban đêm, các truy vấn sáng hôm sau xuất hiện nhiều `CommunicationException`. Nhóm vận hành thấy pool vẫn báo có 15 context idle nên nghĩ server đang thiếu tài nguyên.

**Câu hỏi:**

1. Hai dòng xử lý `finally` có vấn đề gì nếu `context` là **context vật lý** do pool tự xây quản lý?
2. Nếu `context` thực chất là một proxy của pooling context source, ý nghĩa của `context.close()` thay đổi ra sao?
3. Nên thay đổi cách phân nhánh return/invalidate như thế nào sau lỗi mạng?
4. Những cấu hình validation và eviction nào giúp loại context đã bị server đóng trong thời gian idle?
5. Làm sao chứng minh bản sửa hoạt động qua bài kiểm thử tích hợp?

**Gợi ý giải:**

1. `context.close()` đóng tài nguyên vật lý, nhưng `returnObject(context)` vẫn đưa đối tượng đã đóng vào pool; khi mượn lại sẽ gặp lỗi. Pool/factory phải quyết định đóng vật lý khi destroy.
2. Với pooled wrapper, `close()` thường là **release handle** theo hợp đồng pool, không đồng nghĩa socket vật lý bị đóng. Không gọi thêm `returnObject(...)` thủ công cho proxy này.
3. Đánh giá lỗi: khi có bằng chứng connection/TLS bị hỏng, invalidate để pool destroy; chỉ return context hợp lệ. Mỗi lần borrow đi tới một nhánh kết thúc.
4. Cấu hình validation khi mượn, khi idle hoặc khi trả theo nhu cầu, idle timeout thích hợp, kết nối và read timeout có giới hạn; tránh health check gây tải lớn.
5. Dùng LDAP server lab: thực hiện search, tạo idle context, restart server, kiểm tra context chết bị loại, và lần mượn tiếp theo chỉ dùng kết nối mới hợp lệ. Thu thập metric active/idle và destroy/validation failure.

## 11. Checklist triển khai

- [ ] Xác định rõ pool đang quản lý **context vật lý** hay cung cấp **pooled proxy** có `close()` nghĩa là release.
- [ ] Đảm bảo service chỉ giữ `LdapTemplate`/`ContextSource`, không giữ `DirContext` đã mượn qua nhiều request hoặc luồng.
- [ ] Mỗi lần borrow được kết thúc **đúng một lần** bằng return hoặc invalidate; không vừa physical close vừa return.
- [ ] Context lỗi mạng, socket đóng, TLS hỏng hoặc trạng thái xác thực không tin cậy phải bị **invalidate/destroy**.
- [ ] Lỗi nghiệp vụ LDAP được phân loại riêng, không phá hủy hàng loạt context khỏe.
- [ ] Pool có validation thích hợp, timeout, eviction, kích thước tối đa và metric để phát hiện stale connection.
- [ ] Các đường StartTLS, LDAPS, endpoint dự phòng, referral và phân biệt danh tính bind đã được kiểm thử cùng cơ chế pooling.
- [ ] Bài test tích hợp chứng minh context vật lý đã đóng **không thể xuất hiện lại** trong lần borrow sau.

**Ghi nhớ:** `close()` trên một **pooled handle** có thể là hành vi release bình thường, trong khi `close()` trên **context vật lý** khiến nó không còn khả năng tái sử dụng. Điều cần bảo đảm trong Spring LDAP là **không bao giờ cấp lại một context vật lý đã đóng, lỗi hoặc không còn trạng thái xác thực/TLS hợp lệ**, đồng thời không dùng lại handle đã được trả về pool.
