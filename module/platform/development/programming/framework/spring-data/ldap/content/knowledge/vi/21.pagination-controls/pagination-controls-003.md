# Quản lý cookie giữa các lần đọc trang

## 1. Bài toán và mục tiêu

Trong **Spring Data LDAP**, dữ liệu thường nằm trong một cây directory với các entry được định danh bằng **DN** (*distinguished name*), mô tả bằng `objectClass` và thuộc tính theo schema. Khi một nhánh như `ou=people,dc=example,dc=org` chứa hàng chục nghìn người dùng, việc tìm kiếm và tải toàn bộ entry trong một lần gọi dễ gặp giới hạn của LDAP server, tốn bộ nhớ và kéo dài thời gian phản hồi.

**Simple Paged Results** theo RFC 2696 cho phép yêu cầu server trả các kết quả tìm kiếm theo từng trang. Sau mỗi trang, server có thể trả về một **cookie** để client tiếp tục chính xác chuỗi truy vấn đang thực hiện. Quản lý cookie đúng là trách nhiệm của phía client hoặc cơ chế hỗ trợ trong **Spring LDAP**, chứ không phải một tính năng `Pageable` tự có của mọi `LdapRepository`.

Sau bài học, người học có thể:

1. Giải thích cookie LDAP khác gì HTTP cookie, số trang và SQL offset.
2. Gửi yêu cầu trang đầu, nhận cookie và chuyển **cookie mới nhất** vào yêu cầu trang kế tiếp.
3. Nhận biết khi nào phải dừng: cookie rỗng hoặc `null` nghĩa là không còn trang tiếp.
4. Duy trì cùng kết nối LDAP trong một chuỗi đọc trang với `SingleContextSource` hoặc `LdapContext`.
5. Xử lý cookie không hợp lệ, mất kết nối, thay đổi filter, gián đoạn truy vấn, giới hạn tài nguyên và bảo mật.
6. Viết vòng lặp phân trang bằng JNDI và Spring LDAP, sau đó kiểm thử trên directory có hỗ trợ paging.

Ví dụ xuyên suốt:

```text
dc=example,dc=org                     <- base DN của kết nối
└── ou=people                          <- search base (tương đối)
    ├── uid=an
    ├── uid=binh
    ├── uid=chi
    ├── uid=dung
    ├── uid=ha
    ├── uid=linh
    └── uid=son

LDAP filter: (objectClass=inetOrgPerson)
Page size: 3
```

Ở đây `dc=example,dc=org` là DN gốc, `ou=people` là vùng tìm kiếm, và từng entry có DN như `uid=linh,ou=people,dc=example,dc=org`. Phạm vi tìm kiếm và filter phải được giữ nhất quán khi tiếp tục bằng cookie.

## 2. Cookie LDAP thực sự là gì?

RFC 2696 định nghĩa LDAP control với **OID `1.2.840.113556.1.4.319`**. Control này chứa hai trường:

- `size`: trong **request**, số entry client muốn trong một trang; trong **response**, con số ước lượng tổng entry nếu server cung cấp.
- `cookie`: một chuỗi **byte tùy ý** (*opaque octet string*) do server phát hành để tiếp tục truy vấn.

Client phải xem cookie là **dữ liệu mờ đục**: không tự giải mã ý nghĩa, không sửa, không cộng số trang, không tự sinh cookie mới và không dùng cookie của một truy vấn khác. Cookie có thể liên quan đến trạng thái truy vấn đang được server giữ; **không có bảo đảm** rằng nó là token có thể dùng lại mãi mãi.

| Khái niệm | Vai trò | Có thay cookie LDAP được không? |
| --- | --- | --- |
| Cookie LDAP | Trạng thái tiếp tục của **một chuỗi tìm kiếm** do server phát hành. | Đây là giá trị phải gửi lại nguyên vẹn. |
| Số trang `1, 2, 3` | Chỉ là chỉ số hiển thị cho con người. | Không. Không thể suy ra cookie từ số trang. |
| `LIMIT/OFFSET` của SQL | Cơ chế phân trang của cơ sở dữ liệu quan hệ. | Không; LDAP không có API SQL offset tương đương trong Simple Paged Results. |
| HTTP `Cookie` header | Cơ chế trạng thái giữa browser và web server. | Không. Cookie RFC 2696 nằm trong **LDAP control**, không phải HTTP header. |
| `nextCursor` của REST API | Token do ứng dụng thiết kế để trình bày cho client. | Không mặc nhiên; chỉ có thể ánh xạ nếu backend quản lý vòng đời truy vấn LDAP hợp lệ. |

Cookie LDAP **không phải mật khẩu**, nhưng vẫn cần đối xử như trạng thái phiên nhạy cảm: không in raw bytes vào log, không dùng cookie làm token xác thực và không công khai vô thời hạn trên một URL.

## 3. Chu trình đọc trang và quy tắc của RFC 2696

### 3.1. Trang đầu

Client gửi `SearchRequest` với cùng search base, scope, filter, các thuộc tính cần lấy và control:

```text
Control OID = 1.2.840.113556.1.4.319
size       = 3
cookie     = ""  (zero-length; JNDI có thể biểu diễn bằng null ban đầu)
```

Server trả tối đa số lượng entry theo yêu cầu và một `SearchResultDone` kèm **paged results response control**. Nếu còn dữ liệu, response chứa cookie khác rỗng. Ví dụ chuỗi dưới đây chỉ minh họa, các giá trị `C1`/`C2` **không phải cookie thật**:

```text
Client                         LDAP server
  | Search(size=3,cookie="")       |
  |------------------------------->|
  |  [an, binh, chi], cookie=C1   |
  |<-------------------------------|
  | Search(size=3,cookie=C1)      |
  |------------------------------->|
  | [dung, ha, linh], cookie=C2   |
  |<-------------------------------|
  | Search(size=3,cookie=C2)      |
  |------------------------------->|
  |       [son], cookie=""        |
  |<-------------------------------|
  |        DỪNG                 |
```

Không suy luận rằng trang gồm ít hơn ba entry chắc chắn là trang cuối. **Chỉ dấu kết thúc theo giao thức là cookie rỗng**. Phải đọc response control và kiểm tra cookie sau mỗi trang; không dựa hoàn toàn vào `page.size() < pageSize`.

### 3.2. Trang tiếp theo

Khi server trả cookie `C1`, client gửi lại **chính cookie đó** cùng một truy vấn. Theo RFC 2696, các tham số SearchRequest phải được giữ nguyên, ngoại trừ `messageID`, cookie và có thể thay page size. Với ứng dụng thông thường, giữ **page size cố định** giúp dễ kiểm tra và vận hành.

Các yếu tố phải giữ nhất quán bao gồm:

| Tham số | Yêu cầu đối với lần đọc trang kế tiếp |
| --- | --- |
| Search base DN | Không tự đổi từ `ou=people` sang `ou=groups`. |
| Search scope | Giữ nguyên `ONELEVEL_SCOPE`/`SUBTREE_SCOPE` đã chọn. |
| Filter | Không đổi `(objectClass=inetOrgPerson)` thành filter khác. |
| Attributes và các search controls | Giữ cùng cách truy vấn, thuộc tính trả về và giới hạn liên quan. |
| Bind identity và endpoint | Duy trì cùng ngữ cảnh/quyền; với Spring LDAP, phải giữ cùng kết nối bên dưới. |
| Cookie | Chỉ dùng cookie **mới nhất** từ response của lần tìm vừa hoàn tất. |

Nếu user đổi bộ lọc, vùng tìm kiếm hoặc tiêu chí khác, hãy **bắt đầu chuỗi phân trang mới bằng cookie rỗng**, thay vì tiếp tục từ cookie cũ.

### 3.3. Kết thúc và hủy truy vấn

Khi server gửi cookie rỗng, chuỗi đọc đã hoàn tất. Không tái sử dụng cookie đã kết thúc. Một số JNDI API biểu diễn trạng thái này bằng `null`; mã cần coi `null` và mảng byte rỗng là dấu dừng.

RFC 2696 cũng định nghĩa cách **bỏ chuỗi phân trang còn dang dở**: gửi một SearchRequest có cùng truy vấn, với paged results control `size=0` và **cookie mới nhất** đã nhận. Việc này giúp server có cơ hội giải phóng trạng thái. Chỉ gọi `LdapContext.close()` hay đóng HTTP request chưa chắc là thao tác hủy theo đúng giao thức; chi tiết tài nguyên có thể khác nhau giữa các LDAP server.

## 4. Những quy tắc sống còn của cookie

1. **Cookie là opaque bytes:** giữ nguyên chính xác `byte[]` mà server phát hành; tránh parse, chuyển thành số hoặc tự sửa byte.
2. **Chỉ cookie mới nhất được dùng cho bước tiếp:** gửi lại cookie cũ hoặc dùng cùng cookie hai lần là hành vi không được RFC bảo đảm.
3. **Không chia sẻ cookie giữa hai truy vấn:** cookie gắn với một tiến trình search cụ thể và không thể hoán đổi giữa những user, filter hay search base khác nhau.
4. **Duy trì kết nối:** tài liệu Spring LDAP nêu yêu cầu dùng **cùng underlying LDAP connection** cho các trang của một chuỗi. Không giả định cookie còn hiệu lực khi kết nối bị đóng, chuyển LDAP server hoặc lấy connection mới từ pool.
5. **Không coi cookie là dấu trang dài hạn:** server có thể hết hạn/loại bỏ trạng thái; mất kết nối hoặc khởi động lại server có thể khiến cookie không còn dùng được.
6. **Không lấy tổng số kết quả từ page size:** `getResultSize()` trong response chỉ là **ước lượng tùy chọn**; server được phép trả `0` khi không biết.
7. **Không biến lỗi thành hết dữ liệu:** không có response paging control, lỗi `unwillingToPerform` hoặc mất kết nối phải được xử lý như lỗi, không thay bằng `cookie=null` rồi giả vờ hoàn tất.

Đáng chú ý: Simple Paged Results **không cung cấp snapshot isolation**. Khi các entry thay đổi giữa hai trang, client có thể thấy entry lặp, bỏ sót hoặc kết quả dịch chuyển. Cookie giúp tiếp tục một truy vấn, **không bảo đảm tất cả trang phản ánh cùng một thời điểm**.

## 5. Ví dụ JNDI: quản lý cookie trực tiếp

Đây là ví dụ rõ nhất để hiểu cookie, vì các bước nhận/truyền byte được viết tường minh. Dùng Java 17 và interface `javax.naming.ldap.LdapContext` với `PagedResultsControl`, `PagedResultsResponseControl`.

### 5.1. Mở một context cho toàn bộ chuỗi trang

```java
package com.example.directory.paging;

import java.io.IOException;
import java.util.Hashtable;
import java.util.List;
import javax.naming.Context;
import javax.naming.NamingException;
import javax.naming.ldap.InitialLdapContext;
import javax.naming.ldap.LdapContext;

public final class LdapPagingClient {
    private LdapPagingClient() {}

    public static List<String> loadAllUids(
            String ldapUrl,
            String bindDn,
            String password
    ) throws NamingException, IOException {

        Hashtable<String, Object> environment = new Hashtable<>();
        environment.put(Context.INITIAL_CONTEXT_FACTORY,
            "com.sun.jndi.ldap.LdapCtxFactory");
        environment.put(Context.PROVIDER_URL, ldapUrl);
        environment.put(Context.SECURITY_AUTHENTICATION, "simple");
        environment.put(Context.SECURITY_PRINCIPAL, bindDn);
        environment.put(Context.SECURITY_CREDENTIALS, password);
        environment.put("com.sun.jndi.ldap.connect.timeout", "3000");
        environment.put("com.sun.jndi.ldap.read.timeout", "5000");

        LdapContext context = new InitialLdapContext(environment, null);
        try {
            return LdapPageReader.readAll(context);
        } finally {
            context.close();
        }
    }
}
```

Ví dụ `ldapUrl` có dạng `ldaps://ldap.example.org:636/dc=example,dc=org`, trong đó base DN gắn với `PROVIDER_URL` và `ou=people` trong phép tìm bên dưới được tính tương đối. Đây là URL minh họa; thực tế cần cấu hình truststore và chứng chỉ LDAPS đúng cách. Không ghi bind password vào source hoặc log.

Trong bài này, toàn bộ vòng đọc chạy trên **một `LdapContext`**. Nếu đóng context sau trang đầu và tạo context khác cho trang hai, không được coi cookie cũ đương nhiên còn hợp lệ.

### 5.2. Đọc, lưu và dùng cookie mới nhất

Tạo `LdapPageReader.java`:

```java
package com.example.directory.paging;

import java.io.IOException;
import java.util.ArrayList;
import java.util.List;
import javax.naming.NamingEnumeration;
import javax.naming.NamingException;
import javax.naming.directory.Attribute;
import javax.naming.directory.SearchControls;
import javax.naming.directory.SearchResult;
import javax.naming.ldap.Control;
import javax.naming.ldap.LdapContext;
import javax.naming.ldap.PagedResultsControl;
import javax.naming.ldap.PagedResultsResponseControl;

public final class LdapPageReader {
    private static final int PAGE_SIZE = 100;

    private LdapPageReader() {}

    public static List<String> readAll(LdapContext context)
            throws NamingException, IOException {
        SearchControls searchControls = new SearchControls();
        searchControls.setSearchScope(SearchControls.SUBTREE_SCOPE);
        searchControls.setReturningAttributes(new String[] {"uid"});

        List<String> uids = new ArrayList<>();
        byte[] cookie = null; // Trang đầu: cookie rỗng.

        do {
            // Luôn gửi lại cookie vừa nhận ở trang trước.
            context.setRequestControls(new Control[] {
                new PagedResultsControl(PAGE_SIZE, cookie, Control.CRITICAL)
            });

            NamingEnumeration<SearchResult> results = context.search(
                "ou=people",
                "(objectClass=inetOrgPerson)",
                searchControls
            );

            try {
                while (results.hasMore()) {
                    SearchResult entry = results.next();
                    Attribute uid = entry.getAttributes().get("uid");
                    if (uid != null) {
                        uids.add((String) uid.get());
                    }
                }
            } finally {
                results.close();
            }

            // Đọc response control sau khi duyệt hết trang.
            PagedResultsResponseControl response =
                findPagingResponse(context.getResponseControls());

            if (response == null) {
                throw new NamingException(
                    "LDAP server không trả paged results response control");
            }

            // Không giải mã cookie hoặc lưu nó vào file/log.
            cookie = response.getCookie();

        } while (cookie != null && cookie.length > 0);

        return uids;
    }

    private static PagedResultsResponseControl findPagingResponse(
            Control[] controls) {
        if (controls == null) {
            return null;
        }
        for (Control control : controls) {
            if (control instanceof PagedResultsResponseControl response) {
                return response;
            }
        }
        return null;
    }
}
```

Giải thích luồng:

1. `cookie=null` tương ứng cookie rỗng của request đầu.
2. `PagedResultsControl(PAGE_SIZE, cookie, Control.CRITICAL)` yêu cầu paging; khi server không hỗ trợ control quan trọng này, request phải báo lỗi thay vì lặng lẽ trả quá nhiều kết quả.
3. `context.search(...)` luôn dùng cùng `SearchControls`, base và filter.
4. `NamingEnumeration` được duyệt và đóng trước khi lấy response control; giúp đảm bảo xử lý phần kết quả của trang.
5. `getResponseControls()` được duyệt để tìm đúng `PagedResultsResponseControl`; không suy ra rằng mọi control được server trả đều là paging.
6. `getCookie()` có thể trả `null`, hoặc byte rỗng ở ranh giới protocol. Vòng lặp dừng khi không còn byte cookie.
7. `LdapPagingClient` chỉ đóng `LdapContext` sau toàn bộ chuỗi, kể cả khi có ngoại lệ.

**Giới hạn của ví dụ:** hàm trả toàn bộ UID trong một `List` để dễ hiểu. Với directory lớn, nên xử lý và ghi kết quả **theo từng trang** thay vì giữ mọi trang trong RAM. Khi dừng trước trang cuối, cân nhắc gửi yêu cầu hủy `size=0` có cookie cuối nếu vẫn còn kết nối, tùy khả năng server và API đang dùng.

## 6. Spring LDAP quản lý cookie giúp ta như thế nào?

Spring LDAP cung cấp cơ chế **`DirContextProcessor`** chạy trước và sau thao tác tìm kiếm. Processor cho paging có nhiệm vụ đặt LDAP request control, nhận response control và cập nhật trạng thái cookie giữa các lần gọi.

Tuy nhiên, `LdapTemplate` thường lấy/giải phóng context cho **mỗi** thao tác. Nếu gọi nhiều lần `ldapTemplate.search(...)` độc lập mà không giữ một kết nối bên dưới, chuỗi cookie có thể bị gián đoạn.

### 6.1. Phiên bản Spring LDAP 3.x: PagedResultsDirContextProcessor

Đây là mẫu cho các dự án sử dụng API `org.springframework.ldap.control.PagedResultsDirContextProcessor` (phổ biến ở Spring LDAP 3.x). Mẫu dùng `SingleContextSource` để giữ cùng kết nối trong phạm vi callback.

```java
package com.example.directory.paging;

import java.util.ArrayList;
import java.util.List;
import javax.naming.directory.SearchControls;
import org.springframework.ldap.control.PagedResultsDirContextProcessor;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.ContextSource;
import org.springframework.ldap.core.support.SingleContextSource;
import org.springframework.stereotype.Service;

@Service
public class SpringLdapPagingReader {
    private final ContextSource contextSource;

    public SpringLdapPagingReader(ContextSource contextSource) {
        this.contextSource = contextSource;
    }

    public List<String> readAllUids() {
        SearchControls controls = new SearchControls();
        controls.setSearchScope(SearchControls.SUBTREE_SCOPE);
        controls.setReturningAttributes(new String[] {"uid"});

        return SingleContextSource.doWithSingleContext(
            contextSource,
            operations -> {
                PagedResultsDirContextProcessor paging =
                    new PagedResultsDirContextProcessor(100);
                List<String> all = new ArrayList<>();

                do {
                    List<String> onePage = operations.search(
                        "ou=people",
                        "(objectClass=inetOrgPerson)",
                        controls,
                        (AttributesMapper<String>) attrs ->
                            (String) attrs.get("uid").get(),
                        paging
                    );
                    all.addAll(onePage);
                } while (paging.hasMore());

                return all;
            }
        );
    }
}
```

Ở ví dụ này:

- Processor là **một đối tượng được giữ xuyên suốt vòng lặp**. Sau mỗi trang, nó cập nhật cookie và `hasMore()`; không khởi tạo processor mới sau từng lời gọi search.
- `SingleContextSource.doWithSingleContext(...)` bảo đảm các lời gọi trong callback dùng cùng context/connection phía dưới và giải phóng tài nguyên khi callback kết thúc.
- Không lưu processor trong field singleton và chia sẻ giữa các luồng/request. Nó chứa **trạng thái phân trang** của một lần truy vấn.
- Bước xử lý ở đây vẫn gom toàn bộ kết quả; xử lý từng `onePage` trong vòng lặp giúp tránh giữ kết quả lớn trong bộ nhớ.

Trong Spring LDAP 3.x, có thể đọc `paging.getCookie()` hoặc `paging.hasMore()` khi cần quan sát trạng thái. Nếu lập trình tay qua các constructor nhận `PagedResultsCookie`, phải truyền **đúng cookie được trả về từ lần trước**, trong cùng ngữ cảnh tìm kiếm. Không trộn cookie của các vòng tìm kiếm khác nhau.

### 6.2. Spring LDAP 4.1 trở lên: API ControlExchange

Trong các phiên bản **Spring LDAP 4.1+**, API `PagedResultsControlExchangeDirContextProcessor` được giới thiệu để thay thế `PagedResultsDirContextProcessor` đã bị đánh dấu deprecated. Đoạn logic trong vòng lặp tương tự:

```java
import org.springframework.ldap.control.PagedResultsControlExchangeDirContextProcessor;

PagedResultsControlExchangeDirContextProcessor paging =
    new PagedResultsControlExchangeDirContextProcessor(100);

// Trong cùng callback SingleContextSource:
do {
    List<String> onePage = operations.search(
        "ou=people",
        "(objectClass=inetOrgPerson)",
        controls,
        (AttributesMapper<String>) attrs ->
            (String) attrs.get("uid").get(),
        paging
    );
    all.addAll(onePage);
} while (paging.hasMore());
```

Đây là **đoạn thay thế trong method** của ví dụ trước; các biến `operations`, `controls`, `all` vẫn được khai báo ở ngữ cảnh ngoài. Không được coi nó là một file Java độc lập có thể chạy ngay. Khi nâng cấp Spring, kiểm tra API của đúng phiên bản thực tế; không dùng class chỉ xuất hiện ở 4.1+ trong dự án 3.x.

**Phân biệt hai tầng:** Spring Data LDAP `LdapRepository` phù hợp cho CRUD và derived queries; paging bằng LDAP controls là công việc của **Spring LDAP/JNDI**, không đồng nghĩa với `PageRequest.of(page, size)` hay `findAll(Pageable)` kiểu Spring Data JPA.

## 7. Vì sao cookie thường phải đi cùng một kết nối LDAP?

Tài liệu Spring LDAP nêu rõ **paged results cookie cần cùng underlying connection** ở các lần gọi. Lý do thực tế: nhiều LDAP server duy trì trạng thái phiên phân trang hoặc ánh xạ cookie với kết nối/client. Server cũng có thể áp dụng giới hạn cho số chuỗi paging đang mở.

```text
ĐÚNG CHO MỘT CHUỖI:

  ContextSource -- SingleContextSource (connection A)
                        |
                   search page 1 --> cookie C1
                        |
                   search page 2 (C1) --> cookie C2
                        |
                   search page 3 (C2) --> cookie rỗng
                        |
                    đóng context A

DỄ GÂY LỖI:

  HTTP GET page 1 -> connection A -> cookie C1 -> đóng A
  HTTP GET page 2 -> connection B -> gửi C1  -> có thể bị từ chối
```

**Không nên đưa raw LDAP cookie vào token `nextPage` của REST API rồi giả định request HTTP sau có thể lấy bất kỳ connection từ pool và tiếp tục.** Ngay cả khi một server cụ thể chấp nhận, giải pháp đó phụ thuộc mạnh vào implementation, trạng thái và vòng đời cookie.

Nếu ứng dụng thực sự cần nút “Trang tiếp” giữa **các HTTP request độc lập**, phải thiết kế rõ cách quản lý phiên:

| Thiết kế | Ưu điểm | Rủi ro và giới hạn |
| --- | --- | --- |
| Đọc hết một chuỗi trong một callback, xử lý từng trang. | Dễ bảo đảm cùng kết nối, phù hợp job đồng bộ/export. | Không tạo API phân trang trực tiếp cho từng HTTP request. |
| Backend giữ một session truy vấn và kết nối gắn với session. | Có thể hỗ trợ HTTP “Next” khi phiên còn sống. | Tốn kết nối, cần timeout/cleanup/giới hạn số session, ảnh hưởng scale-out. |
| Backend duy trì snapshot kết quả hoặc ID do ứng dụng quản lý. | Client phân trang từ snapshot ứng dụng. | Cần bộ nhớ/lưu trữ và định nghĩa thời hạn/độ mới dữ liệu. |
| Dùng bookmark/keyset với thuộc tính có thứ tự ổn định, khi server hỗ trợ. | Không phụ thuộc vào cookie LDAP xuyên HTTP request. | Cần thiết kế filter/index/sort và xử lý dữ liệu thay đổi; không tương đương RFC 2696. |

Trong thiết kế session phía server, token của REST API nên chỉ là một **session ID khó đoán**, có thời hạn, gắn với user/quyền và dấu vân tay truy vấn; backend giữ cookie cùng connection ở phạm vi được quản lý. Việc giữ nhiều kết nối mở rất tốn tài nguyên, vì vậy cần hạn mức, phát hiện session hết hạn và cơ chế dọn dẹp.

## 8. Các trường hợp cookie không còn hợp lệ

| Tình huống | Điều có thể xảy ra | Cách xử lý |
| --- | --- | --- |
| Thay đổi filter/search base/scope | Cookie gắn với kết quả cũ, trạng thái tiếp tục không phù hợp. | Hủy chuỗi cũ nếu có thể, mở chuỗi mới với cookie rỗng. |
| Đóng/reconnect kết nối LDAP | Server có thể không còn nhận ra cookie hoặc trạng thái phiên. | Không tiếp tục mù quáng; bắt đầu lại truy vấn nếu nghiệp vụ cho phép. |
| Failover từ server A sang B | Cookie có thể chỉ có ý nghĩa với server A. | Khởi động lại quá trình search hoặc dùng cơ chế bảo đảm tính liên tục riêng của hệ thống. |
| Cookie đã hết hạn hoặc bị loại bỏ | Server có thể trả `unwillingToPerform` hoặc lỗi khác. | Xem chuỗi bị lỗi, tránh sử dụng cookie cũ; theo dõi server limits. |
| Dùng lại cookie đã tiêu thụ | Tính hợp lệ không được giao thức bảo đảm. | Luôn cập nhật cookie mới nhất và chỉ dùng theo đúng thứ tự. |
| Search trả lỗi giữa chuỗi | Trạng thái server có thể không còn resumable. | Coi chuỗi thất bại; thiết kế restart và chống xử lý trùng nếu cần. |
| Client nhận phản hồi không có paging control | Server không hỗ trợ control hoặc có vấn đề cấu hình. | Báo lỗi rõ, không tự coi là trang cuối. |
| Truy vấn thay đổi dữ liệu giữa hai trang | Có thể gặp bản ghi lặp hoặc bỏ sót. | Cân nhắc quét lại, đồng bộ tăng dần hoặc kiểm tra tính nhất quán. |

### 8.1. Retry khi mất phản hồi của một trang

Giả sử client đã gửi `cookie=C2`, server thực hiện search nhưng kết nối đứt trước khi client nhận cookie `C3`. Client **không biết chắc** server đã tiêu thụ trạng thái `C2` hay chưa. RFC không bảo đảm việc dùng lại cookie cũ sẽ an toàn.

Với job đồng bộ, chiến lược thực tế là **đánh dấu chuỗi hiện tại thất bại**, tạo kết nối mới và quét lại từ đầu nếu chấp nhận được; dữ liệu xuất nên được xử lý **idempotent** theo DN hoặc khóa nghiệp vụ để tránh nhân đôi. Nếu cần khôi phục có bảo đảm mạnh hơn, hãy thiết kế checkpoint/đối soát riêng thay vì chỉ ghi cookie vào database.

### 8.2. Không xem paging như snapshot giao dịch

Khi Alice bị đổi DN hoặc một entry được thêm/xóa giữa trang 1 và 2, thứ tự/trạng thái kết quả có thể thay đổi. Theo RFC 2696, nếu tập kết quả thay đổi trong quá trình đọc, client có thể nhận entry lặp hoặc không nhận đủ entry.

Do đó:

- Cookie **không bảo đảm tính nhất quán tại một thời điểm**.
- `getResultSize()` chỉ là ước lượng, có thể bằng `0` khi server không biết tổng.
- Thêm sorting control có thể giúp ổn định thứ tự khi server hỗ trợ, nhưng **không tự tạo snapshot isolation**.
- Nếu cần đồng bộ chắc chắn, cân nhắc cơ chế thay đổi tăng dần do directory cung cấp (nếu có) hoặc đối soát theo chu kỳ.

## 9. Vận hành và bảo mật cookie

### 9.1. Giới hạn tài nguyên

Một chuỗi paged search có thể chiếm tài nguyên phía directory, đặc biệt trên những server cần giữ trạng thái tìm kiếm. Cần quy định:

- Page size hợp lý theo server và dữ liệu, ví dụ thử từ 100 entry rồi đo; không mặc định một kích thước phù hợp mọi nơi.
- Số trang tối đa, thời gian tối đa và chính sách dừng khi ứng dụng quá tải.
- Hạn mức đồng thời các phiên đang mở, thời gian hết hạn của phiên do ứng dụng quản lý.
- Search base cụ thể (`ou=people`) và filter đủ hẹp, hạn chế tải các attribute không cần thiết.
- Timeout kết nối và đọc của JNDI; `SearchControls.setTimeLimit` là giới hạn tìm kiếm, **không thay thế timeout mạng**.
- Quy trình hủy chuỗi chưa hoàn tất; có thể gửi page size `0` và cookie cuối nếu còn kết nối.

Đừng đặt `SearchControls.setCountLimit` nhỏ hơn tổng dữ liệu muốn đọc rồi kỳ vọng paging tự bỏ qua giới hạn: giới hạn này không phải `pageSize`. Server có thể có giới hạn cứng và chính sách riêng.

### 9.2. Cookie và dữ liệu nhạy cảm

Raw LDAP cookie là dữ liệu máy chủ cấp phát cho một phiên truy vấn. Không cần đưa nó vào log hoặc phản hồi công khai. Nếu phải truyền qua tầng khác trong hệ thống, sử dụng kênh được bảo vệ, tránh URL dài và có chính sách hết hạn/quyền truy cập; tốt nhất backend tự giữ cookie với context đang sống.

Mỗi chuỗi paging phải được gắn với tài khoản bind, filter và người dùng được cấp quyền. Không tái sử dụng cookie của người dùng A để phục vụ yêu cầu của người dùng B hoặc kết nối có ACL khác nhau. Với dữ liệu danh tính, dùng LDAPS/StartTLS cùng xác minh chứng chỉ và tài khoản bind có quyền tối thiểu.

Gợi ý log:

```text
INFO  ldap-page task=sync-people page=4 entries=100 elapsedMs=92 hasMore=true
WARN  ldap-page task=sync-people page=5 failure=CommunicationException
```

Không cần log `cookie=<bytes>`, thông tin đăng nhập, DN nhạy cảm hoặc filter chứa dữ liệu cá nhân. Để chẩn đoán, ưu tiên số trang theo ứng dụng, độ trễ, số entry và nhóm exception.

## 10. Kiểm thử cookie giữa các trang

Một unit test có thể giả lập response để kiểm tra thuật toán “lấy cookie mới nhất rồi dừng ở cookie rỗng”. Tuy nhiên, unit test **không chứng minh** directory hỗ trợ OID paging hoặc giữ kết nối đúng. Integration test cần LDAP server thử nghiệm thực sự hỗ trợ **Simple Paged Results**.

### 10.1. Kịch bản tối thiểu

Chuẩn bị `ou=people` chứa **7 entry `inetOrgPerson`** có `uid` khác nhau và chọn `pageSize=3`. Khi không có thay đổi dữ liệu trong lúc đọc, kết quả mong đợi:

| Lần đọc | Số entry mong đợi | Cookie phản hồi | Quyết định |
| --- | --- | --- | --- |
| Trang 1 | 3 | Khác rỗng. | Lưu cookie C1 và đọc tiếp. |
| Trang 2 | 3 | Khác rỗng. | Thay C1 bằng C2 và đọc tiếp. |
| Trang 3 | 1 | Rỗng hoặc `null`. | Dừng, không có trang 4. |

Không kiểm tra chuỗi bytes cookie cụ thể, vì nó do server quyết định. Không giả định thứ tự `uid` là thứ tự bảng chữ cái khi chưa dùng sorting có hỗ trợ tương ứng.

### 10.2. Các ca kiểm thử cần có

| Test | Mục tiêu |
| --- | --- |
| Trang đầu với cookie rỗng | Server trả trang đầu và response control. |
| Vòng lặp dùng cookie mới nhất | Không lặp trang đầu, dừng khi cookie rỗng. |
| Không có kết quả | Chuỗi kết thúc đúng, trả danh sách rỗng. |
| Server không hỗ trợ control | Với control `CRITICAL`, fail rõ thay vì coi như paging thành công. |
| Mất connection giữa trang | Chuỗi bị báo thất bại; không giả định resume bằng connection khác. |
| Đổi filter giữa trang | Client bắt đầu query mới với cookie rỗng. |
| Bỏ dở giữa chừng | Có cleanup resource và, nếu phù hợp, yêu cầu abandon theo RFC 2696. |
| Dữ liệu thay đổi trong lúc quét | Tài liệu hóa trường hợp trùng/bỏ sót; không khẳng định snapshot. |
| Server trả result size = 0 | Vẫn dựa vào cookie để kết thúc; không tự trả “0 kết quả”. |
| Hai request song song | Cookie/context độc lập, không rò trạng thái giữa hai người dùng. |

### 10.3. Kiểm tra trên server thật

Trong môi trường lab riêng, có thể dùng `ldapsearch` nếu phiên bản client hỗ trợ paging control:

```bash
ldapsearch -x \
  -H "ldaps://ldap.example.org:636" \
  -D "cn=reader,dc=example,dc=org" -W \
  -b "ou=people,dc=example,dc=org" \
  -E pr=3/noprompt \
  "(objectClass=inetOrgPerson)" uid
```

Lệnh chỉ mang tính minh họa. Tùy bản `ldapsearch` và server, cú pháp extension hoặc cách in cookie có thể khác; phải kiểm tra hỗ trợ paging và TLS trong môi trường thực tế. Không ghi bind password vào tham số command line hoặc file script. Với directory test có 7 entry, kiểm tra truy vấn trả đủ 7 UID khi không có thay đổi đồng thời.

## 11. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| “Cookie là số thứ tự trang.” | Cookie là opaque bytes do server phát hành; không được tự tạo hoặc sửa. |
| “Trang có ít kết quả nghĩa là hết.” | Phải kiểm tra cookie rỗng hoặc `null` theo protocol. |
| “Có `Pageable` của Spring Data thì LDAP tự hỗ trợ.” | Simple Paged Results sử dụng LDAP controls qua Spring LDAP/JNDI. |
| “Có cookie thì đổi filter rồi tiếp tục được.” | Khi thay điều kiện truy vấn, bắt đầu chuỗi mới bằng cookie rỗng. |
| “Có thể giữ cookie một tuần rồi resume bất kỳ lúc nào.” | Cookie có vòng đời phụ thuộc LDAP server/kết nối/trạng thái phiên. |
| “Lấy connection mới từ pool vẫn luôn resume được.” | Spring LDAP yêu cầu cùng underlying connection trong chuỗi. |
| “Cookie bảo đảm không trùng/không thiếu entry.” | Directory thay đổi khi phân trang vẫn có thể gây trùng/bỏ sót. |
| “Server trả `getResultSize()=0` là không có kết quả.” | Server có thể dùng 0 để báo không biết tổng số entry. |
| “Không có response control tức là trang cuối.” | Có thể là thiếu hỗ trợ hoặc lỗi; phải báo rõ. |
| “Chỉ cần lưu cookie xuống DB là có checkpoint bền vững.” | Cookie không thay thế checkpoint nghiệp vụ, connection lifecycle hoặc reconciliation. |

## 12. Bài tập áp dụng

1. Giả sử có 7 entry và page size 3. Mô phỏng cookie `C1`, `C2` và cookie rỗng, giải thích chính xác thời điểm dừng.
2. Sửa ví dụ `LdapPageReader` để xử lý từng trang bằng callback, không gom tất cả entry vào RAM. Giới hạn số trang và thời gian tổng, đồng thời thiết kế cách hủy khi dừng giữa chừng.
3. Tạo hai filter `(sn=Nguyen)` và `(sn=Tran)`. Giải thích vì sao không được dùng cookie của filter đầu để tiếp tục filter sau.
4. Viết integration test với 7 entry và page size 3; xác minh đủ 7 UID khác nhau khi directory ổn định, nhưng không ràng buộc thứ tự hoặc byte cookie.
5. Thiết kế API `GET /users?cursor=...` mà không lộ cookie LDAP: mô tả backend quản lý connection/session, TTL, quyền và cleanup ra sao; nêu nhược điểm khi nhiều user duyệt chậm.
6. Directory server restart sau trang 2; ứng dụng chỉ còn cookie `C2`. Hãy thiết kế cách báo lỗi và khôi phục đồng bộ theo DN mà không giả định cookie vẫn hợp lệ.
7. Giải thích sự khác biệt giữa LDAP `PagedResultsControl` với `SearchControls.setCountLimit` và SQL `LIMIT/OFFSET`.

## 13. Tài liệu tham khảo

- [RFC 2696 — LDAP Simple Paged Results](https://www.rfc-editor.org/rfc/rfc2696): cấu trúc control, cookie, yêu cầu duy trì query, kết thúc và abandon.
- [Spring LDAP Reference — Processing the DirContext](https://docs.spring.io/spring-ldap/reference/processing-the-dircontext.html): `DirContextProcessor`, paged search, `SingleContextSource` và yêu cầu cùng kết nối.
- [Spring LDAP API — PagedResultsDirContextProcessor](https://docs.spring.io/spring-ldap/docs/3.3.x/api/org/springframework/ldap/control/PagedResultsDirContextProcessor.html): API processor trên Spring LDAP 3.x.
- [Spring LDAP API — PagedResultsControlExchangeDirContextProcessor](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/control/PagedResultsControlExchangeDirContextProcessor.html): API mới từ Spring LDAP 4.1.
- [Spring LDAP API — SingleContextSource](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/core/support/SingleContextSource.html): giữ cùng context qua nhiều operation.
- [Java SE 17 — PagedResultsControl](https://docs.oracle.com/en/java/javase/17/docs/api/java.naming/javax/naming/ldap/PagedResultsControl.html): tạo request control JNDI.
- [Java SE 17 — PagedResultsResponseControl](https://docs.oracle.com/en/java/javase/17/docs/api/java.naming/javax/naming/ldap/PagedResultsResponseControl.html): đọc cookie và ước lượng result size.
- [Spring Data LDAP Reference](https://docs.spring.io/spring-data/ldap/reference/): repository, ODM và cách dùng `LdapTemplate` khi cần tính năng ngoài repository.
