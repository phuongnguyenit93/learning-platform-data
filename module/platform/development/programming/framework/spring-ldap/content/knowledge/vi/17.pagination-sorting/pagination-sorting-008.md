# Đọc trạng thái cuối phân trang và dọn cookie trong Spring LDAP

Một truy vấn LDAP có thể trả về hàng nghìn entry, nên ứng dụng thường dùng **Simple Paged Results** để đọc từng trang. Tuy nhiên, đọc được một trang **không có nghĩa** truy vấn đã kết thúc. Muốn biết còn trang tiếp hay không, client phải đọc **response control** của trang vừa hoàn tất, kiểm tra cookie do máy chủ trả về và quyết định tiếp tục hay kết thúc. Khi người dùng dừng giữa chừng, client còn cần xử lý trạng thái phân trang ở server, chứ không chỉ xóa một biến `cookie` trong Java.

Bài học thuộc chương **Phân trang và sorting** của **SPRING_LDAP**. Nội dung tập trung vào hai mục tiêu: **đọc chính xác tín hiệu kết thúc chuỗi phân trang** và **giải phóng trạng thái/cookie khi hoàn tất, hủy hoặc gặp lỗi**. Ví dụ kết hợp nguyên tắc giao thức RFC 2696, JNDI `LdapContext` và Spring LDAP với `ContextSource`, `LdapTemplate` cùng `DirContextProcessor`. Các quy tắc này vẫn có ý nghĩa khi ứng dụng chuyển sang `LdapClient`, ODM hoặc bổ sung server-side sorting.

## 1. Vì sao phải đọc trạng thái sau mỗi trang?

Giả sử máy chủ có 235 tài khoản dưới `ou=people,dc=example,dc=org`, còn ứng dụng yêu cầu mỗi trang tối đa 100 entry:

~~~text
Yêu cầu 1 (page size = 100, cookie rỗng)
    -> 100 entry + cookie A (còn trang tiếp)

Yêu cầu 2 (page size = 100, cookie A)
    -> 100 entry + cookie B (còn trang tiếp)

Yêu cầu 3 (page size = 100, cookie B)
    -> 35 entry + cookie rỗng (đã hết)
~~~

Đây là **ví dụ minh họa**. Trên thực tế, số entry mỗi trang có thể khác kích thước yêu cầu, server có thể áp giới hạn riêng, và dữ liệu có thể thay đổi giữa các lần gọi. Vì vậy:

- Không dùng `page.size() < pageSize` để kết luận trang cuối.
- Không dùng `page.size() == 0` để kết luận chắc chắn đã hết.
- Không dùng số lượng tổng ước lượng để quyết định đã hoàn tất.
- **Chỉ coi chuỗi phân trang kết thúc bình thường khi nhận được phản hồi hoàn tất với cookie rỗng** (trong ngữ cảnh server thực sự hỗ trợ control và không có lỗi).

Tín hiệu kết thúc nằm trong **response control**, không nằm trong số phần tử Java của danh sách kết quả.

## 2. Request control và response control của RFC 2696

LDAP Simple Paged Results dùng control OID:

~~~text
1.2.840.113556.1.4.319
~~~

Control được gửi kèm mỗi `SearchRequest`. Nội dung logic gồm:

| Trường | Ý nghĩa | Cách sử dụng |
|---|---|---|
| `size` ở request | Kích thước trang mong muốn | Ví dụ 100; giá trị 0 có ý nghĩa **hủy chuỗi**, khi đi cùng cookie hợp lệ |
| `cookie` ở request | Trạng thái tiếp tục do server cấp | Trang đầu gửi cookie rỗng; các trang sau gửi cookie gần nhất |
| `size` ở response | **Ước lượng** tổng số kết quả, nếu server cung cấp | Có thể bằng 0 khi server không biết/không báo; không phải số đếm chắc chắn |
| `cookie` ở response | Chỉ báo còn dữ liệu và token tiếp tục | Cookie **không rỗng**: có thể đọc trang sau; cookie **rỗng**: đã hoàn tất |

Cookie có thể là mảng byte; client phải xem nó là **opaque token** — không phân tích cấu trúc, không tự thay đổi hoặc tính offset từ byte cookie.

Ở mức giao thức, quy trình có thể hình dung:

~~~mermaid
sequenceDiagram
    participant C as LDAP client
    participant S as LDAP server
    C->>S: Search + PagedResults(size=100, cookie=empty)
    S-->>C: Entries 1..100 + Done(cookie=A)
    C->>S: Search + PagedResults(size=100, cookie=A)
    S-->>C: Entries 101..200 + Done(cookie=B)
    C->>S: Search + PagedResults(size=100, cookie=B)
    S-->>C: Entries 201..235 + Done(cookie=empty)
    Note over C,S: Không gửi thêm yêu cầu cho chuỗi đã kết thúc
~~~

**Phản hồi cuối của từng trang** là nơi có thể đọc được cookie mới. Client JNDI nên duyệt kết quả đến trạng thái hoàn tất trang và đọc `LdapContext.getResponseControls()`, thay vì kiểm tra response control quá sớm khi `NamingEnumeration` vẫn đang được xử lý.

## 3. Ba trạng thái phải phân biệt

Một ứng dụng nên mô hình hóa rõ ba kết quả:

| Trạng thái | Tín hiệu | Hành động đúng |
|---|---|---|
| **Còn trang** | Search thành công; response control có cookie không rỗng | Dùng đúng cookie mới nhất cho trang tiếp trên cùng phiên/kết nối theo yêu cầu server |
| **Hoàn tất bình thường** | Search thành công; response control có cookie rỗng | Dừng vòng lặp, bỏ token local, đóng tài nguyên |
| **Thất bại hoặc không rõ** | Search ném lỗi, thiếu response control cần thiết, timeout, kết nối lỗi | Không kết luận đã hết; phân loại lỗi, xác minh trạng thái và cleanup |

Điểm tinh tế: nếu một API trả object cookie **không null** nhưng các byte bên trong **rỗng/null**, đó vẫn có thể là **trang cuối**. Ví dụ API cũ của Spring LDAP trả `PagedResultsCookie` wrapper từ `getCookie()`, và tài liệu nêu wrapper có thể tồn tại ngay cả khi nội dung cookie đã là null. Do đó nên ưu tiên **`processor.hasMore()`** khi API cung cấp, thay vì chỉ so sánh object cookie với `null`.

Với JNDI, cách trực tiếp là kiểm tra byte cookie:

~~~java
byte[] cookie = response.getCookie();
boolean hasMore = cookie != null && cookie.length > 0;
~~~

Kiểm tra này có ý nghĩa **sau khi** nhận được `PagedResultsResponseControl` hợp lệ và search hoàn tất không lỗi.

## 4. Vòng đời cookie: trang đầu, tiếp tục, hoàn tất, dừng sớm

~~~mermaid
flowchart TD
    A["Bắt đầu: cookie rỗng"] --> B["Search một trang"]
    B --> C{"Search hoàn tất và có response control?"}
    C -->|Không| X["Lỗi / không rõ; không kết luận hoàn tất"]
    C -->|Có| D{"Cookie phản hồi rỗng?"}
    D -->|Có| E["Kết thúc bình thường"]
    D -->|Không| F{"Cần tiếp tục?"}
    F -->|Có| G["Gửi trang tiếp với cookie mới nhất"]
    G --> B
    F -->|Không| H["Gửi yêu cầu hủy size=0 với cookie cuối"]
    H --> I["Dọn tài nguyên, không tái sử dụng cookie"]
    E --> I
    X --> J["Cleanup context; xử lý trạng thái thất bại"]
~~~

Mỗi cookie nhận được **chỉ có ý nghĩa trong chuỗi truy vấn mà server đã tạo**. RFC 2696 lưu ý không dùng lại cookie cũ thay cho cookie mới nhất, và cookie sau khi chuỗi đã kết thúc không còn hợp lệ.

Điều kiện cần khi tiếp tục trang:

1. Dùng **cùng thông số tìm kiếm** về base DN, filter, scope và các controls liên quan; không tự thay đổi cách sort ở giữa.
2. Dùng **cookie trong response của trang vừa hoàn tất**, không phải cookie đã sử dụng để gửi trang đó.
3. Giữ **cùng kết nối LDAP vật lý** khi server/processor yêu cầu. Tài liệu Spring LDAP nhấn mạnh điểm này cho Simple Paged Results.
4. Không để hai request đồng thời sử dụng cùng cookie như hai “con trỏ” độc lập.
5. Chỉ gọi tiếp nếu lần đọc trang trước hoàn tất thành công và tín hiệu từ cookie cho biết còn dữ liệu.

### Cookie không phải offset hay dữ liệu nghiệp vụ

Đừng ghi log nội dung cookie hoặc giải mã nó thành số thứ tự. Đừng chia sẻ cookie giữa người dùng, giữa hai search có filter khác nhau hoặc tự gắn cookie của một session vào session mới. Với những API HTTP phải trả “next page token”, cần thiết kế giới hạn phiên, thời gian sống và kiểm soát quyền riêng; việc chuyển thẳng raw cookie LDAP cho client ngoài không bảo đảm có thể tiếp tục ở kết nối khác.

## 5. Đọc trạng thái cuối bằng JNDI

JDK có hai lớp phù hợp:

- `javax.naming.ldap.PagedResultsControl` để đưa page size và cookie vào request.
- `javax.naming.ldap.PagedResultsResponseControl` để đọc cookie và kích thước ước lượng ở response.

Khi dùng JNDI trực tiếp, hãy làm việc với `LdapContext`, không chỉ `DirContext`, vì các phương thức `setRequestControls(...)` và `getResponseControls()` thuộc `LdapContext`.

Ví dụ một phương thức đọc tất cả các trang trong **cùng một context** được truyền vào từ tầng quản lý kết nối:

~~~java
import java.io.IOException;
import java.util.ArrayList;
import java.util.List;

import javax.naming.NamingEnumeration;
import javax.naming.NamingException;
import javax.naming.directory.SearchControls;
import javax.naming.directory.SearchResult;
import javax.naming.ldap.Control;
import javax.naming.ldap.LdapContext;
import javax.naming.ldap.PagedResultsControl;
import javax.naming.ldap.PagedResultsResponseControl;

public final class JndiPagedReader {
    private static final int PAGE_SIZE = 100;

    public List<String> readAllUids(LdapContext ctx)
            throws NamingException, IOException {

        SearchControls options = new SearchControls();
        options.setSearchScope(SearchControls.SUBTREE_SCOPE);
        options.setReturningAttributes(new String[] {"uid"});

        byte[] cookie = null;
        List<String> uids = new ArrayList<>();

        do {
            PagedResultsControl request =
                    cookie == null
                    ? new PagedResultsControl(PAGE_SIZE, Control.CRITICAL)
                    : new PagedResultsControl(
                            PAGE_SIZE, cookie, Control.CRITICAL);

            ctx.setRequestControls(new Control[] {request});

            NamingEnumeration<SearchResult> rows = null;
            try {
                rows = ctx.search(
                        "ou=people",
                        "(objectClass=inetOrgPerson)",
                        options);

                while (rows.hasMore()) {
                    SearchResult entry = rows.next();
                    var uid = entry.getAttributes().get("uid");
                    if (uid != null) {
                        uids.add((String) uid.get());
                    }
                }
            } finally {
                if (rows != null) {
                    rows.close();
                }
            }

            // Sau khi trang đã được duyệt xong mới đọc response control.
            PagedResultsResponseControl response = null;
            Control[] controls = ctx.getResponseControls();

            if (controls != null) {
                for (Control control : controls) {
                    if (control instanceof PagedResultsResponseControl) {
                        response = (PagedResultsResponseControl) control;
                        break;
                    }
                }
            }
            if (response == null) {
                throw new NamingException(
                        "LDAP server did not return paged results response");
            }

            // Chỉ dùng byte cookie mới nhất trong response.
            cookie = response.getCookie();
        } while (cookie != null && cookie.length > 0);

        return uids;
    }
}
~~~

**Phạm vi ví dụ:** người gọi phải cung cấp một `LdapContext` đã bind bằng danh tính có quyền tìm kiếm, cấu hình TLS phù hợp và đóng context sau khi hoàn tất. Đối với @@ContextSource@@ trong Spring LDAP, không nên ép kiểu tùy tiện mọi `DirContext` thành `LdapContext` nếu provider không bảo đảm điều đó.

Đoạn mã này trình bày **đường hoàn tất bình thường**; nó cố ý không tự động “nuốt” lỗi limit, mạng hoặc mapping. Nếu lỗi xảy ra sau khi đọc một số trang, danh sách đang thu thập không được coi là dữ liệu đầy đủ. Trường hợp dừng sớm cần thêm logic **abandon** theo phần tiếp theo.

### Vì sao phải duyệt `NamingEnumeration` đến cuối?

JNDI có thể đọc kết quả theo từng phần. Một lỗi server, timeout hoặc lỗi referral có thể xuất hiện tại `hasMore()` hoặc `next()`. Nếu chưa xử lý xong enumeration, ứng dụng có thể chưa nhận được `SearchResultDone` và response control của trang.

Do đó **trang đã xử lý thành công** là trang mà ứng dụng đã duyệt hoàn tất, đọc được response control và không gặp lỗi. Sau đó mới cập nhật cookie dùng cho trang tiếp.

### Dọn kết quả và context

`NamingEnumeration` cần được đóng ngay cả khi vòng lặp ném exception. Context do ứng dụng tự tạo hoặc mượn cũng cần đóng trong `finally` tại nơi sở hữu nó. `LdapTemplate` thường quản lý những tài nguyên này khi ứng dụng dùng API template.

**Đóng enumeration và context không tương đương hoàn toàn với gửi tín hiệu hủy một chuỗi Simple Paged Results còn mở trên server.** Cần phân biệt giải phóng tài nguyên Java/JNDI với vòng đời cookie phía LDAP server.

## 6. Dừng trước trang cuối: dọn cookie theo RFC 2696

Nếu ứng dụng chủ động dừng khi cookie cuối nhận được vẫn **không rỗng** (ví dụ người dùng hủy export, màn hình chỉ cần vài trang hoặc tác vụ bị giới hạn số trang), nó nên **kết thúc chuỗi phân trang** thay vì bỏ mặc trạng thái tìm kiếm.

RFC 2696 mô tả cách client bỏ chuỗi bằng một **SearchRequest mới có Paged Results Control với `size = 0` và `cookie` bằng cookie cuối cùng đã được server trả về**.

~~~text
Client đã nhận:
    response.cookie = A   (không rỗng)

Client quyết định dừng, không đọc trang tiếp:
    SearchRequest:
      same base/filter/search parameters
      pagedResultsControl:
        size   = 0
        cookie = A

Server xử lý yêu cầu dừng:
    giải phóng trạng thái còn giữ của chuỗi nếu có
Client:
    bỏ token local, không tiếp tục dùng A
~~~

Đây là ý nghĩa của **“dọn cookie”** trong giao thức: gửi yêu cầu kết thúc để máy chủ có thể thu hồi trạng thái. Đặt `cookie = null` ở Java chỉ xóa tham chiếu phía client, **không gửi tín hiệu hủy** tới server.

### Mẫu minh họa JNDI cho lần hủy

Ví dụ dưới đây giả định:
- `ctx` vẫn là **cùng LdapContext/kết nối** dùng cho các trang trước.
- `lastCookie` là cookie **không rỗng nhận từ response hoàn tất gần nhất**.
- `options`, base và filter giống chuỗi search cần hủy.

~~~java
// Mảnh mã trong một phương thức có ctx, lastCookie và options.
ctx.setRequestControls(new Control[] {
        new PagedResultsControl(
                0, lastCookie, Control.CRITICAL)
});

NamingEnumeration<SearchResult> cancelled = null;
try {
    cancelled = ctx.search(
            "ou=people",
            "(objectClass=inetOrgPerson)",
            options);
    while (cancelled.hasMore()) {
        cancelled.next(); // Đọc để hoàn tất phản hồi giao thức.
    }
} finally {
    if (cancelled != null) {
        cancelled.close();
    }
}

// Chuỗi đã được yêu cầu kết thúc; không tái sử dụng lastCookie.
lastCookie = null;
~~~

Đây là minh họa cách gửi **size 0** qua JNDI, không phải đoạn code đầy đủ cho xử lý toàn bộ exception. Ứng dụng cần giới hạn thời gian chờ, xử lý lỗi khi server không hỗ trợ, và **không cố gửi yêu cầu hủy khi không có cookie hợp lệ**.

**Không nhầm `size = 0` với yêu cầu trang chứa 0 entry thông thường.** Trong quy trình này, `size = 0` kèm cookie của chuỗi đang mở là tín hiệu *abandon paged search sequence* của RFC 2696.

### Nếu đã ở trang cuối thì sao?

Nếu response đã có **cookie rỗng**, chuỗi được xem là hoàn tất. Không cần gửi một request `size = 0` để dọn chuỗi đã kết thúc; chỉ cần đóng tài nguyên và bỏ cookie local.

### Nếu kết nối đã mất hoặc có lỗi trong lúc search?

Sau lỗi mạng, timeout hoặc mất session, có thể **không thể** gửi yêu cầu hủy với cookie cũ trên cùng kết nối. Khi đó:

1. Đóng/loại bỏ context không còn dùng được theo chính sách provider/pool.
2. Đánh dấu chuỗi phân trang là thất bại, không coi kết quả đang có là toàn bộ.
3. Không mang cookie cũ sang kết nối mới và giả định resume được.
4. Dựa vào cơ chế giới hạn/timeout của LDAP server để thu hồi trạng thái còn lại nếu không thể hủy rõ ràng.
5. Nếu cần retry, bắt đầu **chuỗi phân trang mới** với cookie rỗng và chiến lược chống ghi trùng dữ liệu.

RFC 2696 lưu ý có thể dùng LDAP Abandon cho **một search request đang chạy**, nhưng cách này có thể làm mất tính hợp lệ của cookie. Đối với **một chuỗi nhiều trang đã có cookie**, tín hiệu `size = 0` trên chuỗi hợp lệ là cơ chế hủy được mô tả rõ hơn.

## 7. Spring LDAP: đọc trạng thái qua DirContextProcessor

Khi sử dụng `LdapTemplate`, Spring LDAP hỗ trợ cơ chế `DirContextProcessor` để gắn request control và đọc response control sau khi search. Các phiên bản Spring LDAP khác nhau có lớp helper khác nhau.

### API mới: `PagedResultsControlExchangeDirContextProcessor`

Trong phiên bản có hỗ trợ `PagedResultsControlExchangeDirContextProcessor`, có thể làm như sau:

~~~java
import java.util.ArrayList;
import java.util.List;

import javax.naming.directory.SearchControls;

import org.springframework.ldap.control.PagedResultsControlExchangeDirContextProcessor;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.ContextSource;
import org.springframework.ldap.core.support.SingleContextSource;

public final class PagedPeopleService {
    private final ContextSource contextSource;

    public PagedPeopleService(ContextSource contextSource) {
        this.contextSource = contextSource;
    }

    public List<String> readAllNames() {
        SearchControls controls = new SearchControls();
        controls.setSearchScope(SearchControls.SUBTREE_SCOPE);
        controls.setReturningAttributes(new String[] {"cn"});

        var paging = new PagedResultsControlExchangeDirContextProcessor(100);

        return SingleContextSource.doWithSingleContext(
                contextSource,
                operations -> {
                    List<String> names = new ArrayList<>();
                    do {
                        List<String> page = operations.search(
                                "ou=people",
                                "(objectClass=inetOrgPerson)",
                                controls,
                                (AttributesMapper<String>) attrs ->
                                        (String) attrs.get("cn").get(),
                                paging);
                        names.addAll(page);
                    } while (paging.hasMore());

                    return names;
                });
    }
}
~~~

**Điểm quan trọng nhất:** vòng lặp chỉ dừng bình thường khi **`paging.hasMore()` trả `false` sau lần search hoàn tất**. Phương thức này dựa vào cookie trong response control, nên không cần suy luận từ `page.size()`.

Đây là ví dụ **đọc đến cuối**. Nếu ứng dụng chủ động giới hạn số trang rồi thoát khi `hasMore()` vẫn true, cần xem xét cách hủy chuỗi theo RFC 2696 ở tầng control/kết nối mà phiên bản thư viện hỗ trợ; chỉ thoát callback không phải một bảo đảm về việc server đã được báo hủy.

### Tại sao dùng `SingleContextSource`?

`LdapTemplate` có thể lấy rồi đóng/trả context sau **mỗi** thao tác. Trong khi đó, Simple Paged Results thường yêu cầu **các trang trong cùng chuỗi dùng cùng kết nối bên dưới**. `SingleContextSource.doWithSingleContext(...)` tạo một phạm vi sử dụng **cùng context** cho toàn bộ callback, sau đó giải phóng đúng cách.

Ngoài `SingleContextSource`, Spring LDAP có thể dùng cơ chế transaction/context phù hợp để giữ cùng kết nối khi cần, nhưng phải kiểm tra rõ cấu hình, provider và hành vi thực tế. **Chỉ bật connection pooling không bảo đảm các request sẽ luôn lấy lại đúng một kết nối vật lý.**

### API cũ: `PagedResultsDirContextProcessor`

Các ví dụ ở phiên bản Spring LDAP cũ có thể dùng:

~~~java
PagedResultsDirContextProcessor paging =
        new PagedResultsDirContextProcessor(100);

// Thực hiện từng page trong cùng context qua LdapTemplate.
// Sau khi một page kết thúc:
boolean more = paging.hasMore();
PagedResultsCookie token = paging.getCookie();
int estimatedTotal = paging.getResultSize();
~~~

Trong API cũ, `getCookie()` trả wrapper `PagedResultsCookie` nhưng **wrapper có thể khác null dù cookie bên trong đã hết**. Vì vậy dùng `paging.hasMore()` để quyết định dừng. `getResultSize()` là số ước lượng **tùy chọn**, không dùng để suy ra trang cuối.

Ở API Spring LDAP mới hơn, `PagedResultsDirContextProcessor` đã được đánh dấu **deprecated** để chuyển sang `PagedResultsControlExchangeDirContextProcessor`. Hãy chọn ví dụ theo **phiên bản thư viện thật của dự án**; không trộn hai API trong một đoạn code.

## 8. Phân biệt dọn cookie với đóng connection và xóa biến

Ba việc này có mục đích khác nhau:

| Hành động | Tác dụng | Khi nào? |
|---|---|---|
| **Nhận cookie rỗng ở trang cuối** | Server đã báo chuỗi phân trang hoàn tất | Khi đọc đủ tất cả các trang |
| **Gửi size 0 với cookie cuối** | Yêu cầu server hủy chuỗi đang mở | Khi chủ động dừng sớm và vẫn có kết nối/cookie hợp lệ |
| **Xóa biến cookie Java** | Bỏ token trong bộ nhớ ứng dụng | Sau khi hoàn tất/hủy hoặc hết giá trị sử dụng |
| **Đóng `NamingEnumeration`** | Giải phóng tài nguyên duyệt kết quả của một search | Sau mỗi trang JNDI, kể cả khi lỗi |
| **Đóng/trả `LdapContext`** | Giải phóng kết nối hoặc trả về pool | Khi kết thúc phạm vi sở hữu context |

Khi dùng Spring LDAP, `LdapTemplate` xử lý nhiều phần cleanup JNDI; tuy vậy **trách nhiệm nghiệp vụ xác định khi nào dừng, khi nào coi đã đọc hết và có cần hủy chuỗi chưa kết thúc** vẫn thuộc thiết kế ứng dụng.

Một lỗi phổ biến là:

~~~java
List<Person> page = fetchOnePage();
cookie = null; // Chỉ bỏ token local.
return page;   // Server có thể còn giữ trạng thái chuỗi.
~~~

Nếu thực sự chỉ cần một trang, có thể cân nhắc **không mở chuỗi phân trang server-side** khi chỉ cần một truy vấn giới hạn; hoặc nếu đã mở và còn cookie, kết thúc chuỗi theo cơ chế phù hợp.

## 9. Phân trang kết hợp server-side sorting

Simple Paged Results **không tự bảo đảm một thứ tự hiển thị ổn định**. Khi giao diện cần dữ liệu có thứ tự, server có thể hỗ trợ sort control riêng (LDAP Server Side Sorting, RFC 2891). Nếu dùng sorting cùng paging, client cần giữ điều kiện sắp xếp nhất quán giữa các trang.

~~~text
Trang 1: search ou=people, filter F, sort cn ascending, cookie empty
Trang 2: search ou=people, filter F, sort cn ascending, cookie A
Trang 3: search ou=people, filter F, sort cn ascending, cookie B
~~~

**Không thay `sort=cn` thành `sort=uid` trong lúc dùng cookie của cùng chuỗi.** Cookie là trạng thái opaque gắn với việc server thực hiện một search cụ thể. Thay filter, base DN, scope, sort key hoặc danh tính kết nối giữa các trang có thể làm kết quả sai hoặc khiến server từ chối tiếp tục.

Cần lưu ý hai vấn đề độc lập:

1. **Thứ tự không ổn định khi dữ liệu thay đổi**: nếu entry được tạo, sửa hoặc chuyển OU trong lúc phân trang, RFC 2696 không bảo đảm không trùng/không sót trên mọi trạng thái cập nhật đồng thời.
2. **Kết thúc chuỗi phải dựa vào cookie**: dù sắp xếp có thứ tự, trang cuối vẫn được nhận biết từ response cookie rỗng chứ không phải vì đã đến một UID cụ thể.

Với nhiệm vụ đồng bộ số lượng lớn, nên thiết kế lưu dấu tiến độ và khóa định danh ổn định ở tầng nghiệp vụ. Việc server hỗ trợ sorting không biến chuỗi phân trang thành transaction snapshot.

## 10. Lỗi, timeout và trường hợp thiếu response control

Một số lỗi cần phân biệt:

| Tình huống | Diễn giải | Hướng xử lý |
|---|---|---|
| Search thành công, cookie rỗng | Hoàn tất bình thường | Dừng và đóng tài nguyên |
| Search thành công, cookie không rỗng | Còn trang theo server | Giữ cookie mới nhất, tiếp tục hoặc hủy chủ động |
| Không có response control phân trang | Server/provider không hỗ trợ hoặc không thực thi control như yêu cầu | Không coi là trang cuối; kiểm tra cấu hình/criticality |
| Server trả `unsupportedCriticalExtension` (12) | Control critical không được hỗ trợ | Dừng, báo lỗi khả năng của server |
| `sizeLimitExceeded` (4) | Search bị giới hạn về số entry | Xem dữ liệu là chưa hoàn chỉnh; không coi đã hết |
| `timeLimitExceeded` (3) | Search bị giới hạn thời gian | Giải phóng tài nguyên; xử lý kết quả một phần |
| `unwillingToPerform` (53) khi resume | Server không còn giữ trạng thái/cookie đã hết hạn hoặc policy không cho tiếp tục | Hủy/reset chuỗi, bắt đầu lại nếu nghiệp vụ cho phép |
| Socket/LDAP session bị mất | Cookie có thể không thể dùng lại trên kết nối khác | Đóng context, bỏ chuỗi cũ, tạo chuỗi mới khi retry |
| Ứng dụng dừng sau trang N | Cookie vẫn không rỗng | Khi còn kết nối hợp lệ, gửi yêu cầu hủy với size 0 |

**Không biến exception thành `hasMore=false`.** Nếu vòng lặp gặp lỗi sau 7 trang trong tổng số chưa biết, trả 7 trang đó như “đã hoàn tất” có thể khiến nghiệp vụ đồng bộ hoặc xóa dữ liệu đưa ra quyết định sai.

Với một response không có control phân trang, việc đặt control ở request ở chế độ **critical** có thể giúp fail rõ ràng nếu server không hỗ trợ; cách xử lý vẫn cần đối chiếu tài liệu và provider được sử dụng.

### Có thể resume sau khi process restart không?

Không nên giả định. Cookie thường phụ thuộc trạng thái server và kết nối; chính sách của server có thể giới hạn tuổi thọ và số chuỗi phân trang đang mở. Khi tiến trình chết hoặc kết nối mất, hãy coi cookie cũ không còn đáng tin và **khởi tạo chuỗi mới** sau khi đánh giá tính an toàn của việc chạy lại.

Nếu cần lưu tiến độ lâu dài, thiết kế checkpoint bằng khóa nghiệp vụ hoặc các cơ chế đồng bộ do server cung cấp thay vì dùng raw LDAP paging cookie như resume token vĩnh viễn.

## 11. Giám sát và kiểm thử trạng thái cuối

Theo dõi phân trang mà không tiết lộ cookie:

- Số trang đã hoàn tất thành công.
- Số entry từng trang và tổng số entry được xử lý.
- Trạng thái `COMPLETE`, `CANCELLED` hoặc `FAILED` của cả chuỗi.
- Số lần timeout, missing response control và retry.
- Thời gian mở context và số kết nối active/idle trong pool.
- Search base/filter ở dạng đã loại bỏ hoặc làm mờ dữ liệu nhạy cảm.

**Không log raw cookie**; chỉ cần log cờ `hasMore` hoặc trạng thái cuối. Tùy bối cảnh, DN và filter có thể chứa thông tin cá nhân nên cũng cần xử lý phù hợp chính sách.

### Bộ kịch bản kiểm thử gợi ý

| Kịch bản | Input | Điều cần xác nhận |
|---|---|---|
| Không có entry | Search không khớp | Nhận cookie cuối rỗng, không tiếp tục vô hạn |
| Ít hơn page size | Ví dụ 20 entry, page size 100 | Dừng do cookie rỗng |
| Bằng đúng page size | Ví dụ 100 entry, page size 100 | Không suy luận từ size; tuân response control |
| Nhiều trang | Ví dụ 235 entry, page size 100 | Theo cookie mới nhất; kết thúc khi cookie rỗng |
| Server trả trang rỗng nhưng cookie không rỗng | Trường hợp giới hạn/triển khai đặc biệt | Theo protocol state, có giới hạn chống lặp vô hạn |
| Dừng sớm | Dừng khi cookie A không rỗng | Gửi size 0 với A nếu session còn hợp lệ |
| Mất kết nối | Sau trang thứ hai | Không coi là hoàn tất, không resume bừa trên kết nối mới |
| Server không hỗ trợ control | Control critical | Báo lỗi rõ ràng, không silently paginate sai |
| Dữ liệu thay đổi trong khi đọc | Có add/move/delete đồng thời | Nhận diện khả năng trùng/sót, không giả định snapshot |
| Sorting + paging | Sort theo `cn` ổn định | Không đổi sort control giữa các trang |

Cần kiểm thử tích hợp với LDAP server hỗ trợ RFC 2696 và cấu hình thực về ACL, timeout, TLS, pooling. Mock có thể xác minh nhánh xử lý `hasMore()` và cleanup, nhưng không thay thế kiểm thử cùng kết nối và hành vi cookie trên server.

## 12. Bài tập phân tích trạng thái cookie

Giả sử ứng dụng dùng page size = 50, truy vấn tìm tài khoản dưới `ou=people`.

| Lần gọi | Số entry nhận | Cookie phản hồi | Trạng thái xử lý |
|---|---:|---|---|
| 1 | 50 | `A1` | Thành công |
| 2 | 35 | `B2` | Thành công |
| 3 | 0 | Cookie rỗng | Thành công |

**Câu hỏi 1.** Có được dừng sau lần 2 vì chỉ nhận 35 entry, ít hơn 50 không?

*Không.* Cookie `B2` không rỗng nên server vẫn báo còn khả năng lấy trang sau. Số lượng entry của một trang không thay thế trạng thái từ response.

**Câu hỏi 2.** Sau lần 3 có phải gửi size 0 để hủy không?

*Không cần.* Trang cuối trả cookie rỗng, chuỗi đã hoàn tất bình thường. Chỉ dọn tài nguyên JNDI/connection và bỏ token local.

**Câu hỏi 3.** Nếu người dùng bấm “Hủy” ngay sau lần 1, client nên làm gì?

*Đáp án:* Khi kết nối vẫn còn hợp lệ, gửi yêu cầu Search với Paged Results Control `size = 0`, `cookie = A1`, cùng ngữ cảnh truy vấn để kết thúc chuỗi; sau đó đóng context. Chỉ gán `cookie = null` ở Java không phải tín hiệu hủy của RFC.

**Câu hỏi 4.** Nếu response của lần 2 có `resultSize = 85`, có thể xem đây là tổng chắc chắn rồi ngừng không?

*Không.* Server có thể trả **ước lượng**; tín hiệu cuối vẫn là cookie rỗng. Trong ví dụ, lần 2 còn `B2` nên chưa thể kết luận hoàn tất.

**Câu hỏi 5.** Nếu lần 3 ném `TimeLimitExceededException` trước khi có response control hợp lệ thì trạng thái là gì?

*FAILED/UNKNOWN*, không phải `COMPLETE`. Cần giải phóng tài nguyên, không xem tập 85 entry trước đó là toàn bộ; sau đó quyết định retry hoặc bắt đầu chuỗi mới tùy nghiệp vụ.

**Câu hỏi 6.** Nếu đang phân trang theo `cn` tăng dần mà client đổi sang `uid` trước lần 2, điều gì có thể xảy ra?

Cookie `A1` không được thiết kế để tiếp tục một truy vấn đã đổi sort key; server có thể từ chối hoặc trả dữ liệu không mong đợi. Muốn đổi cách sắp xếp, kết thúc chuỗi hiện tại rồi tạo chuỗi mới với cookie rỗng.

## 13. Các hiểu nhầm cần tránh

| Hiểu nhầm | Cách hiểu đúng |
|---|---|
| “Trang có ít bản ghi hơn page size chắc chắn là trang cuối.” | Phải đọc cookie trong response control. |
| “Wrapper `PagedResultsCookie` khác null nghĩa là còn trang.” | Với API cũ, wrapper có thể tồn tại dù cookie content đã hết; dùng `hasMore()`. |
| “Cookie là offset, có thể tự tính trang 2.” | Cookie là opaque token do server quản lý. |
| “Xóa biến cookie là server đã dọn trạng thái.” | Khi dừng sớm cần yêu cầu hủy với `size=0` nếu còn phiên/cookie hợp lệ. |
| “Đóng context luôn tương đương với hủy RFC 2696.” | Đóng client resources không bảo đảm đã gửi explicit abandon. |
| “Có pool thì tự động dùng cùng connection.” | Pool không bảo đảm mỗi trang mượn đúng connection trước đó. |
| “Sort ổn định sẽ không bao giờ trùng/sót entry.” | Dữ liệu thay đổi giữa các trang vẫn có thể gây trùng/sót. |
| “Lỗi timeout sau vài trang là đã đọc hết phần còn lại.” | Đây là lỗi/đọc chưa hoàn chỉnh, không phải tín hiệu kết thúc. |
| “`getResultSize()` là số tuyệt đối.” | Có thể chỉ là ước lượng hoặc không có giá trị hữu ích. |

## Tài liệu tham khảo

- [RFC 2696 — LDAP Control Extension for Simple Paged Results Manipulation](https://www.rfc-editor.org/rfc/rfc2696): cơ chế cookie rỗng khi kết thúc và lệnh hủy `size = 0`.
- [Spring LDAP Reference — Processing the DirContext](https://docs.spring.io/spring-ldap/reference/processing-the-dircontext.html): ví dụ paging với `SingleContextSource` và `DirContextProcessor`.
- [Spring LDAP API — PagedResultsControlExchangeDirContextProcessor](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/control/PagedResultsControlExchangeDirContextProcessor.html): xử lý response control và `hasMore()` trên API mới.
- [Spring LDAP API — PagedResultsDirContextProcessor](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/control/PagedResultsDirContextProcessor.html): API cũ, `getCookie()`, `getResultSize()` và trạng thái deprecated ở tài liệu hiện hành.
- [Spring LDAP API — SingleContextSource](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/core/support/SingleContextSource.html): giữ cùng kết nối trong callback và quản lý vòng đời.
- [Java JNDI — PagedResultsControl](https://docs.oracle.com/en/java/javase/17/docs/api/java.naming/javax/naming/ldap/PagedResultsControl.html) và [PagedResultsResponseControl](https://docs.oracle.com/en/java/javase/17/docs/api/java.naming/javax/naming/ldap/PagedResultsResponseControl.html): request/response control mức JNDI.
- [RFC 2891 — LDAP Control Extension for Server Side Sorting](https://www.rfc-editor.org/rfc/rfc2891): sorting server-side khi kết hợp phân trang.

## Ghi nhớ

Để xác định **trang cuối**, hãy đọc response control sau khi hoàn tất mỗi search: **cookie rỗng nghĩa là chuỗi đã kết thúc; cookie không rỗng nghĩa là có thể tiếp tục**. Với Spring LDAP, dùng `DirContextProcessor.hasMore()` của API phù hợp thay vì suy luận từ số phần tử hoặc chỉ kiểm tra wrapper cookie. Khi **dừng sớm**, nếu vẫn giữ được cùng kết nối và cookie hợp lệ, gửi yêu cầu theo RFC 2696 với **page size bằng 0 và cookie mới nhất** để hủy chuỗi, rồi dọn tài nguyên; khi đã đọc hết thì chỉ cần đóng và bỏ cookie. Không tái sử dụng cookie qua một truy vấn, phiên hoặc kết nối khác một cách tùy tiện, đặc biệt khi có sorting, timeout và dữ liệu cập nhật đồng thời.
