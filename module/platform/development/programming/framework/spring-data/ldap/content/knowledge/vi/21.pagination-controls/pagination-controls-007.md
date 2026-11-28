# Giới hạn nhảy đến trang tùy ý và ước lượng tổng số kết quả

Trong giao diện danh bạ nhân sự, người dùng quen với dòng chữ **“Trang 1 / 83”** và có thể bấm thẳng vào **trang 40**. Một nhóm phát triển kết nối directory LDAP qua Spring Data LDAP có thể muốn giữ nguyên trải nghiệm đó: gọi `LdapTemplate.search(...)` với page size 100, lấy tổng số entry để tính số trang, rồi gửi `page=40` cho server.

Vấn đề là **Simple Paged Results (RFC 2696) không phải phân trang bằng offset**. LDAP server cấp một **cookie tiếp tục** sau mỗi trang. Muốn lấy trang kế tiếp, client gửi cookie vừa nhận; giao thức **không định nghĩa thao tác “đến trang 40” trực tiếp**. Response còn có trường `size`, nhưng đó là **ước lượng tổng số entry** do server cung cấp, có thể bằng `0` khi không có ước lượng. Nó không phải kết quả `SELECT COUNT(*)` chính xác hoặc ổn định như cách một giao diện bảng dữ liệu có thể kỳ vọng.

Bài thuộc chương **Phân trang và controls** của module **SPRING_DATA_LDAP** giải thích hai giới hạn trên và cách thiết kế đúng trong ứng dụng Java: dùng `ContextSource`, `LdapTemplate`, LDAP controls, DN/base/filter, mapper/ODM hoặc repository theo đúng vai trò; biết khi nào chỉ nên hiển thị **Tiếp / Trước**, khi nào có thể xây snapshot hoặc dùng tính năng máy chủ khác để hỗ trợ nhảy đến vị trí gần đúng. Các lưu ý về ACL, TLS, giới hạn tài nguyên, nhất quán dữ liệu và kiểm thử directory là một phần của giải pháp, không phải phần bổ sung tùy chọn.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vì sao cookie RFC 2696 là **cursor tuần tự**, không phải page number hay offset.
2. Phân biệt giá trị **ước lượng tổng kết quả** trong response control với tổng số đã kiểm đếm thực tế.
3. Thiết kế UX/API dùng `hasNext` và nút **Tiếp**, đồng thời nêu rõ điều kiện để có nút **Trước**.
4. Nêu chi phí khi cố mô phỏng “nhảy đến trang k” bằng cách đi tuần tự qua k trang.
5. Đọc `PagedResultsResponseControl.getResultSize()` và `getCookie()` bằng JNDI mà không diễn giải nhầm giá trị `0`.
6. Sử dụng Spring LDAP paging processor và `SingleContextSource` theo hợp đồng cùng kết nối.
7. So sánh Simple Paged Results với server-side sort, Virtual List View (nếu provider hỗ trợ), keyset/seek pagination và snapshot lưu trong database.
8. Viết bài kiểm thử nhận diện server không trả ước lượng, thay đổi dữ liệu giữa các trang, cookie không hợp lệ, phân quyền và kết quả bị cắt.

## 2. Phân trang LDAP khác OFFSET/LIMIT trong SQL

Một API database thường hỗ trợ kiểu:

~~~sql
SELECT id, display_name
FROM directory_people_snapshot
ORDER BY display_name, id
LIMIT 100 OFFSET 3900;
~~~

Sau khi có một snapshot phù hợp và quy tắc sắp xếp xác định, query trên nhắm đến các bản ghi ở **vị trí 3.901–4.000**. Trái lại, Simple Paged Results không nhận `OFFSET 3900` hoặc `page=40`:

~~~text
Lần 1: search(base, filter, pageSize=100, cookie=empty)
        -> 100 entry + cookie_A

Lần 2: search(base, filter, pageSize=100, cookie_A)
        -> 100 entry + cookie_B

Lần 3: search(base, filter, pageSize=100, cookie_B)
        -> 100 entry + cookie_C
        ...
~~~

**Trình tự là điều cốt lõi:** cookie của trang 2 chỉ có sau khi nhận response trang 1; cookie của trang 3 chỉ có sau trang 2. Client không thể tính cookie thứ 40 từ số `40 × 100`.

| Tính chất | OFFSET/LIMIT trên snapshot database | LDAP Simple Paged Results |
| --- | --- | --- |
| Đề nghị kích thước trang | `LIMIT 100`. | `pageSize=100` trong RFC 2696 control. |
| Chỉ định vị trí bắt đầu | `OFFSET 3900` hoặc cursor dựa trên khóa. | Cookie do server trả từ lần search trước. |
| Nhảy đến trang tùy ý | Có thể dùng offset nếu database/query hỗ trợ, dù có chi phí. | **Không có trong RFC 2696**. |
| Lấy trang kế tiếp | Truy vấn với offset/cursor mới. | Gửi lại cookie vừa nhận. |
| Lấy trang trước | Query offset/cursor ngược hoặc cache. | Không có cookie “lùi” mặc định. |
| Tổng số hàng | Có thể đếm trên database theo transaction/snapshot được thiết kế. | Response `size` chỉ là **ước lượng**, có thể không có. |
| Tính nhất quán | Phụ thuộc transaction, snapshot và mức cô lập. | RFC 2696 **không bảo đảm snapshot** của toàn directory. |

**Lưu ý:** SQL dùng offset cũng có vấn đề về hiệu năng và biến động dữ liệu; bảng này chỉ giải thích vì sao LDAP không thể được coi như một database hỗ trợ random-access page.

## 3. Bên trong RFC 2696: request, response và cookie

Control **Simple Paged Results** có OID:

~~~text
1.2.840.113556.1.4.319
~~~

Request mang hai dữ liệu chính:

- `size`: số entry mà client **đề nghị** nhận trong một trang.
- `cookie`: chuỗi octet từ lần trước; lần đầu rỗng.

Response mang:

- `size`: **ước lượng** kích thước toàn bộ tập kết quả, nếu server có thể cung cấp; `0` khi server không thể đưa ước lượng.
- `cookie`: token cho trang kế tiếp; cookie rỗng biểu thị kết thúc chuỗi kết quả.

~~~mermaid
sequenceDiagram
    participant App as Spring Boot
    participant LDAP as Directory server
    App->>LDAP: Search + paged control(size=100, cookie=rỗng)
    LDAP-->>App: Entry trang 1 + response(size≈N hoặc 0, cookie=A)
    App->>LDAP: Search cùng base/filter, cookie=A
    LDAP-->>App: Entry trang 2 + response(size≈N hoặc 0, cookie=B)
    App->>LDAP: Search cùng base/filter, cookie=B
    LDAP-->>App: Trang cuối + response(cookie=rỗng)
    Note over App,LDAP: Kết thúc khi response cookie rỗng, không dựa vào số entry trong trang
~~~

### 3.1. Cookie là opaque state, không phải một con số

Ứng dụng không được:

- Giải mã cookie để suy vị trí entry.
- Tự tăng giá trị cookie, nối page number hoặc tự tính cookie thứ k.
- Dùng lại cookie với filter, base, scope hoặc ý định truy vấn khác.
- Giả định cookie từ **server A** còn dùng được trên server B.
- Coi cookie là checkpoint lâu dài sau khi connection đóng, job restart hoặc hết hạn.
- Trả raw cookie ra API công khai mà không có thiết kế session/security rõ ràng.

Theo hướng dẫn Spring LDAP, các search của một chuỗi paging nên sử dụng **cùng underlying LDAP connection**, ví dụ với `SingleContextSource`. Cookie là trạng thái do server định nghĩa; chiến lược quản lý kết nối không thể suy diễn từ việc tên tài khoản bind trùng nhau.

### 3.2. Cookie rỗng khác với trang rỗng

Một trang có ít hơn `pageSize` entry **không** tự chứng minh đã hết dữ liệu. Ngược lại, khi server trả response cookie kết thúc, client mới biết chuỗi paging đã hoàn tất theo giao thức, miễn là không có lỗi/partial response.

Ví dụ:

~~~text
Yêu cầu pageSize=100
Trả 80 entry + cookie=X   => còn trang, phải tiếp tục
Trả 100 entry + cookie=∅  => hết trang, kết thúc
Trả   0 entry + cookie=X  => chưa hết; kiểm tra tình trạng bất thường
~~~

Ứng dụng nên giới hạn số page, thời gian, số lần nhận trang rỗng liên tiếp và dữ liệu xử lý để không mắc vòng lặp vô hạn khi server hoặc client gặp bất thường.

## 4. Vì sao không thể nhảy trực tiếp đến trang 40?

Nếu page size là 100, người dùng muốn trang 40, client có hai lựa chọn phổ biến khi **chỉ có** RFC 2696:

1. **Chưa có cookie của trang 39:** phải đi tuần tự từ đầu qua các trang trước, thường tương ứng khoảng 4.000 entry đã được server duyệt/trả cho client.
2. **Đang giữ trạng thái của chuỗi paging:** có thể tiếp tục từ cookie hiện tại, nhưng không mặc định có thể quay lại trang cũ hoặc chuyển sang một phiên/server khác.

~~~text
User: "Đến trang 40"
Client có: cookie ban đầu (empty)

Page 1 -> cookie1
Page 2 -> cookie2
...
Page 39 -> cookie39
Page 40 -> data cần hiển thị

Không có API chuẩn RFC 2696: getPage(40)
~~~

Giả sử độ trễ round-trip trung bình **80 ms** mỗi trang, chỉ 40 lượt search có thể tiêu tốn khoảng **3,2 giây** thời gian round-trip cơ bản, **chưa tính** server xử lý, truyền 4.000 entry, mapping, TLS, DB và tranh chấp tài nguyên. Đây là phép minh họa, không phải thời gian thực đo trên directory.

### 4.1. Chi phí truy cập trang k

Nếu page size là `S`, muốn đến trang `k` bằng cách đi tuần tự:

\[
N_{\text{đi qua}} \approx k \times S
\]

\[
T_{\text{tối thiểu, mạng}} \approx k \times RTT
\]

Mô hình có thể khác do server trả ít hơn `S` entry và kết quả thay đổi khi đang quét. Nó cho thấy bản chất **O(k) số request** đối với cách truy cập tuần tự, không có tính chất random access `O(1)` theo page number.

### 4.2. Vì sao không giữ 200 cookie rồi dùng để quay lại?

Việc lưu mọi cookie trong một danh sách không khiến chúng trở thành **bookmark bền vững**. Nhiều triển khai xem cookie gắn với trạng thái truy vấn và kết nối; việc dùng lại cookie cũ sau khi đã đi tiếp không được RFC 2696 bảo đảm như một thao tác “previous page”. Kể cả server cụ thể chấp nhận, dữ liệu có thể đã thay đổi và kết quả không còn nhất quán.

Nếu muốn nút **Trước** hoạt động ổn định với dataset vừa hiển thị, cách đơn giản hơn là **cache những trang dữ liệu đã trả**, có giới hạn và TTL, sau khi áp kiểm soát quyền/PII. Cache kết quả không giống cache cookie và cũng không phải ảnh chụp toàn directory.

## 5. Response `size` là ước lượng, không phải COUNT chính xác

Trong RFC 2696, **size trong Paged Results Response Control** có thể cho biết **estimated result set size**. Server có thể báo `0` khi không thể ước lượng. Giá trị này:

- Có thể thay đổi giữa các trang.
- Không nhất thiết bằng số entry cuối cùng nhận được.
- Không bao hàm những entry caller/bind account không có quyền xem.
- Không bảo đảm phản ánh snapshot cố định khi directory được cập nhật đồng thời.
- Không đủ căn cứ để hiển thị **“có chính xác 8.362 người”**.

### 5.1. Bốn trường hợp phải phân biệt

| Thông tin nhận được | Cách hiểu hợp lệ | Điều không được suy ra |
| --- | --- | --- |
| Response `size=8300`, cookie còn. | Server đang ước lượng khoảng 8.300 kết quả phù hợp. | Chắc chắn có 83 trang, mỗi trang 100 và không thay đổi. |
| Response `size=0`, cookie còn. | Server **không cung cấp ước lượng** đáng tin cậy lúc đó. | Không có kết quả hoặc tổng số bằng 0. |
| Response `size=0`, cookie kết thúc, trang không có entry. | Chuỗi search đã hết theo response; có thể là truy vấn thật sự rỗng. | LDAP server công bố một exact count bằng 0 qua trường size. |
| Đọc xong 8.317 entry không lỗi. | Ứng dụng đã **xử lý 8.317 entry trong lần scan**. | Đó là số entry chính xác tại một thời điểm T cố định nếu directory có thay đổi. |

Trong UI, nếu dùng size estimate, nên ghi **“Ước tính khoảng 8.300 kết quả”**. Nếu server không có estimate, có thể hiển thị **“Đã tải 200 kết quả — còn trang tiếp”**, thay vì “Trang 2 / 0”.

### 5.2. Vì sao `ceil(estimatedTotal / pageSize)` dễ gây hiểu lầm?

Với `estimatedTotal=8.300` và `pageSize=100`, phép tính:

\[
\widehat{P} = \left\lceil \frac{8300}{100} \right\rceil = 83
\]

cho **số trang ước tính**, không phải số trang cố định. Server có thể trả số entry thực ít hơn page size hoặc directory thay đổi giữa các search. Khi `estimatedTotal=0` mà cookie còn, công thức cho `0` trang là **sai về mặt hiển thị**.

Một UI chỉ có `hasNext` và `loadedCount` tránh được phần lớn hiểu lầm đó.

### 5.3. Có thể đếm toàn bộ rồi coi là exact không?

Nếu cần số lượng cho **lần chạy cụ thể**, ứng dụng có thể thực hiện hết các trang và tự đếm các entry đã nhận. Tuy nhiên:

1. Đây là một scan đầy đủ, có thể tiêu tốn nhiều request, I/O và kết nối.
2. Kết quả là **số entry đã quan sát/xử lý** trong lần scan, không tự động là snapshot tại một thời điểm.
3. Filter, search base, scope, ACL và trạng thái replication quyết định những entry nào được nhìn thấy.
4. Nếu timeout, size limit, referral chưa xử lý hoặc mất kết nối, số đã đếm là **partial count**, không thể công bố là total.
5. Nếu yêu cầu exact count cho dashboard nghiệp vụ, nguồn đáng tin cậy thường là **snapshot/index riêng có quy tắc cập nhật và timestamp**; khi đó cần giải thích độ trễ đồng bộ.

**Đừng chạy full scan chỉ để in “tổng 8.300” cho mỗi HTTP request.** Điều đó tạo tải lớn và vẫn không giải quyết triệt để tính nhất quán.

## 6. Đọc estimate và cookie bằng JNDI

Spring LDAP quản lý phần lớn công việc tạo context, mapping và xử lý LDAP controls. Để hiểu chính xác trường `size` mà JNDI cung cấp, ví dụ dưới dùng **API chuẩn Java `javax.naming.ldap`**. Nó **không thay thế** lựa chọn Spring LDAP trong ứng dụng; phần dưới là cơ chế nền để giải thích response control.

### 6.1. `PagedResultsResponseControl.getResultSize()`

~~~java
import java.io.IOException;
import javax.naming.Context;
import javax.naming.NamingEnumeration;
import javax.naming.NamingException;
import javax.naming.directory.SearchControls;
import javax.naming.directory.SearchResult;
import javax.naming.ldap.Control;
import javax.naming.ldap.LdapContext;
import javax.naming.ldap.PagedResultsControl;
import javax.naming.ldap.PagedResultsResponseControl;

public final class JndiPagedCountReader {
    private JndiPagedCountReader() {}

    public record ScanObservation(
            long observedCount,
            int pages,
            Integer lastEstimatedTotal) {}

    /**
     * context đã được bind an toàn qua TLS và chỉ có quyền đọc.
     * Caller sở hữu vòng đời context và chịu trách nhiệm đóng nó.
     */
    public static ScanObservation scan(
            LdapContext context, String fullSearchBase)
            throws NamingException, IOException {

        final int pageSize = 250;
        final int maxPages = 1000;
        byte[] cookie = null;
        long observedCount = 0;
        int pages = 0;
        Integer lastEstimate = null;

        SearchControls controls = new SearchControls();
        controls.setSearchScope(SearchControls.SUBTREE_SCOPE);
        controls.setReturningAttributes(new String[] {"uid", "cn"});
        controls.setTimeLimit(5000);

        do {
            if (pages >= maxPages) {
                throw new IllegalStateException(
                        "Vuot maxPages: scan chua hoan tat");
            }

            // Quan trọng: cùng LdapContext và cùng base/filter/scope.
            context.setRequestControls(new Control[] {
                    new PagedResultsControl(
                            pageSize, cookie, Control.CRITICAL)
            });

            NamingEnumeration<SearchResult> results = context.search(
                    fullSearchBase,
                    "(objectClass=inetOrgPerson)",
                    controls);

            try {
                while (results.hasMore()) {
                    SearchResult entry = results.next();
                    // Trong ví dụ chỉ đếm; production có thể map/process.
                    if (entry != null) {
                        observedCount++;
                    }
                }
            } finally {
                results.close();
            }
            pages++;

            PagedResultsResponseControl pageControl = null;
            Control[] responses = context.getResponseControls();
            if (responses != null) {
                for (Control response : responses) {
                    if (response instanceof PagedResultsResponseControl p) {
                        pageControl = p;
                        break;
                    }
                }
            }

            if (pageControl == null) {
                throw new NamingException(
                        "Khong co Paged Results Response Control");
            }

            int estimated = pageControl.getResultSize();
            // Trong RFC 2696, 0 có thể nghĩa là không có estimate.
            lastEstimate = estimated > 0 ? estimated : null;
            cookie = pageControl.getCookie();

        } while (cookie != null && cookie.length != 0);

        return new ScanObservation(
                observedCount, pages, lastEstimate);
    }
}
~~~

**Điểm chính của mã:**

1. `new PagedResultsControl(pageSize, cookie, Control.CRITICAL)` gửi yêu cầu phân trang. Tham số `cookie` ban đầu có thể `null` theo JNDI API; các lượt sau dùng bytes do server cấp.
2. `NamingEnumeration<SearchResult>` phải được đọc hết và đóng cho mỗi search trước khi đánh giá kết quả đầy đủ.
3. `context.getResponseControls()` lấy các response controls do LDAP provider nhận được.
4. `getResultSize()` chỉ được dùng làm **ước lượng**. Code chuyển `0` thành `null` ở DTO quan sát, nghĩa là **không có ước lượng hữu ích**, không phải tổng bằng 0.
5. `getCookie()` điều khiển vòng lặp. Cookie `null` hoặc rỗng là điều kiện kết thúc; không căn cứ vào kích thước trang.
6. Nếu thiếu response control, phát sinh lỗi: **không** biến phần dữ liệu đã đọc thành full scan.
7. `maxPages` bảo vệ ứng dụng khỏi quét vô hạn. Khi chạm giới hạn mà còn trang, scan là **không hoàn tất**.

Đây là ví dụ **cơ chế JNDI**, nhận `LdapContext` đã cấu hình và không minh họa tạo context từ mật khẩu. Trong ứng dụng thực, tạo context phải qua LDAPS/StartTLS đáng tin cậy, quản lý secret an toàn, timeout, ACL và vòng đời kết nối. Không gọi hàm trên từ mỗi HTTP request chỉ để tính tổng danh bạ.

### 6.2. Không có estimate có phải lỗi không?

Không. RFC 2696 cho phép server gửi `size=0` khi không biết ước lượng; điều này **không có nghĩa paging thất bại**. Một chuỗi search vẫn có thể đi đến cuối và xử lý đủ entry theo quyền/phạm vi. Lỗi cần báo nằm ở những tình huống như:

- Server không hỗ trợ paging control bắt buộc.
- Không nhận được response control cần thiết.
- Search gặp time/size/admin limit hoặc referral chưa xử lý.
- Cookie bị từ chối vì thay kết nối/server/search.
- Scan bị cắt bởi `maxPages`, timeout, lỗi mapper hoặc lỗi downstream.

Trong báo cáo, phân tách hai trường `estimateAvailable` và `scanCompleted`. **Không trộn “không có estimate” với “không có dữ liệu”**.

## 7. Triển khai Spring LDAP: đi tiếp tuần tự, không có số trang tùy ý

Trên Spring LDAP 4.1+, `PagedResultsControlExchangeDirContextProcessor` có thể xử lý request/response paging control; trong các phiên bản cũ có `PagedResultsDirContextProcessor`. Khi cần nhiều lần search cho một chuỗi cookie, dùng `SingleContextSource` để giữ cùng context.

### 7.1. Cấu hình Spring Boot

Gradle Kotlin DSL:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-ldap")
}
~~~

`application.yml`:

~~~yaml
spring:
  ldap:
    urls: ${LDAP_URL:ldaps://ldap.example.org:636}
    base: ${LDAP_BASE_DN:dc=example,dc=org}
    username: ${LDAP_BIND_DN}
    password: ${LDAP_BIND_PASSWORD}
    base-environment:
      "com.sun.jndi.ldap.connect.timeout": "3000"
      "com.sun.jndi.ldap.read.timeout": "7000"

directory:
  paging:
    size: 100
    max-pages: 50
~~~

`directory.paging.*` là thuộc tính **tự định nghĩa trong ứng dụng**, không phải một tùy chọn Spring Data LDAP tự động cấu hình. Page size phải được validate và giới hạn theo server policy, bộ nhớ và concurrency; không nhận một số cực lớn trực tiếp từ HTTP client.

Tài khoản bind nên chỉ có quyền search/read trong vùng nghiệp vụ, không dùng quản trị viên directory chỉ để duyệt các trang. Kết nối LDAPS phải xác minh chứng chỉ máy chủ; không chuyển sang `ldap://` không mã hóa khi gặp lỗi TLS.

### 7.2. Đọc tuần tự bằng `LdapTemplate`

Đoạn code minh họa một **job duyệt tuần tự và xử lý mỗi trang**, không phải HTTP endpoint cho phép `?page=40`:

~~~java
import java.util.List;
import java.util.function.Consumer;
import javax.naming.directory.SearchControls;
import org.springframework.ldap.control.PagedResultsControlExchangeDirContextProcessor;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.ContextSource;
import org.springframework.ldap.core.support.SingleContextSource;
import org.springframework.stereotype.Service;

@Service
public final class SequentialDirectoryScanner {

    private final ContextSource contextSource;

    public SequentialDirectoryScanner(ContextSource contextSource) {
        this.contextSource = contextSource;
    }

    public record PersonRow(String uid, String displayName) {}

    public record ScanStats(long entries, int pages) {}

    public ScanStats scan(Consumer<PersonRow> consumer) {
        if (consumer == null) {
            throw new IllegalArgumentException("consumer bat buoc");
        }

        final int pageSize = 100;
        final int maxPages = 50;

        SearchControls controls = new SearchControls();
        controls.setSearchScope(SearchControls.SUBTREE_SCOPE);
        controls.setReturningAttributes(new String[] {"uid", "cn"});
        controls.setTimeLimit(5000);

        AttributesMapper<PersonRow> mapper = attributes ->
                new PersonRow(
                        attributes.get("uid").get().toString(),
                        attributes.get("cn").get().toString());

        var pager =
                new PagedResultsControlExchangeDirContextProcessor(pageSize);

        return SingleContextSource.doWithSingleContext(
                contextSource,
                operations -> {
                    long observed = 0;
                    int pages = 0;

                    do {
                        if (pages >= maxPages) {
                            throw new IllegalStateException(
                                    "Con cookie nhung vuot maxPages");
                        }

                        List<PersonRow> page = operations.search(
                                "ou=people",
                                "(objectClass=inetOrgPerson)",
                                controls,
                                mapper,
                                pager);
                        pages++;

                        for (PersonRow entry : page) {
                            consumer.accept(entry);
                            observed++;
                        }
                    } while (pager.hasMore());

                    return new ScanStats(observed, pages);
                },
                true, false, false
        );
    }
}
~~~

**Lưu ý về ví dụ:** API trên dành cho **Spring LDAP 4.1+**; phiên bản cũ cần processor tương ứng. Mapper giả định entry test có đủ `uid` và `cn`. Production phải xử lý field thiếu/ACL, đánh dấu scan thất bại khi consumer ném exception và không giữ tất cả trang trong RAM.

`SingleContextSource.doWithSingleContext` giữ context cho toàn chuỗi; cookie nằm trong `pager`. `hasMore()` là tín hiệu đi tiếp; **không có `pager.goToPage(40)`**. Nếu muốn kích hoạt scan mới với base/filter khác, phải dùng một chuỗi truy vấn và processor mới.

### 7.3. Làm sao lấy estimate trong một ứng dụng Spring LDAP?

Spring LDAP paging processor giúp quản lý controls và cookie. API để **đọc size estimate cụ thể** có thể phụ thuộc processor/phiên bản (chẳng hạn processor cũ có cơ chế đọc result size). Khi sản phẩm thực sự cần trường estimate, hãy xác minh API version rồi chỉ dùng dữ liệu lấy từ **paged results response control**, như `PagedResultsResponseControl.getResultSize()` của JNDI ở mục 6. Đừng suy total từ số page đã duyệt hoặc tự nhân `pageSize × pageNumber`.

Một service có thể trả đồng thời:

~~~java
public record DirectoryScanProgress(
        long processedEntries,
        boolean scanCompleted,
        Integer estimatedTotalOrNull) {
}
~~~

`estimatedTotalOrNull == null` nghĩa là server không có ước lượng hữu ích; `scanCompleted` là trạng thái riêng, chỉ true khi đi hết cookie và không có lỗi. Trong một API tìm kiếm trang thông thường, bạn có thể **bỏ luôn trường estimate** nếu không có use case rõ ràng.

## 8. Thiết kế API/UI: ưu tiên Next, đừng hứa “Trang x / y” không có căn cứ

### 8.1. Mô hình UI phù hợp với paging tuần tự

Ví dụ giao diện hiển thị:

~~~text
Danh bạ nhân sự
Tìm kiếm: [Nguyễn]

Đã hiển thị 100 kết quả
[Trước]   [Tiếp]

Ước tính khoảng 8.300 kết quả (nếu server có ước lượng)
~~~

Các trạng thái cần hiển thị:

| State | UI đề xuất | Vì sao? |
| --- | --- | --- |
| Có cookie tiếp tục. | Nút **Tiếp**. | Có thể lấy trang sau trong cùng chuỗi truy vấn. |
| Đang ở trang đầu, chưa cache trang trước. | Ẩn/vô hiệu hóa **Trước**. | Protocol không định nghĩa backward cursor. |
| Đã cache một số trang trước có giới hạn. | Có thể dùng **Trước** để xem trang cached. | Không phải truy vấn ngược bằng cookie LDAP. |
| Cookie kết thúc. | Vô hiệu hóa **Tiếp**, có thể ghi “Đã tải hết”. | Chuỗi search đã hết. |
| Estimate bằng 0/không có. | Không hiển thị tổng số. | `0` không nên hiểu là tổng chính xác. |
| Server có estimate khác 0. | “Khoảng N kết quả”. | Không tạo cảm giác đây là `COUNT(*)` chính xác. |
| Kết nối hỏng giữa trang. | Lỗi/“Bắt đầu lại tìm kiếm”. | Không tiếp tục cookie cũ trên context tùy ý. |

Không nên hiển thị nút **1 2 3 … 83** nếu backend chỉ có RFC 2696 và chưa có chiến lược truy cập trang bất kỳ. UI không nên mô phỏng một khả năng mà server không cung cấp.

### 8.2. Hợp đồng dữ liệu cho API “Tiếp”

Một API của ứng dụng có thể dùng kiểu:

~~~json
{
  "items": [
    {
      "id": "corp-ad:00112233-4455-6677-8899-aabbccddeeff",
      "displayName": "Lan Nguyen"
    }
  ],
  "hasNext": true,
  "nextPageToken": "opaque-application-token",
  "estimatedTotal": 8300,
  "totalKind": "ESTIMATE"
}
~~~

`nextPageToken` ở đây là **token ứng dụng** trong một thiết kế đã có state/snapshot an toàn, **không phải raw cookie LDAP**. Nếu backend không triển khai khả năng duy trì/truy xuất trạng thái giữa các request, **không nên trả token giả** chỉ để làm giao diện. Khi không có estimate, trả `estimatedTotal: null` và `totalKind: "UNKNOWN"`.

**Cảnh báo kiến trúc:** Giữ một LDAP connection đang mở qua nhiều HTTP request chỉ để giữ cookie có thể gây hết connection pool, timeout, leak và tranh chấp tài nguyên. Một hệ thống nhiều người dùng không nên coi mô hình “mỗi người xem danh bạ sở hữu một connection LDAP trong vài phút” là giải pháp mặc định. Nếu cần trải nghiệm nhiều trang bền vững, cân nhắc snapshot/cache hoặc dịch vụ tìm kiếm riêng.

### 8.3. Ràng buộc token theo danh tính và điều kiện tìm kiếm

Nếu tự xây stateful API, token phiên tìm kiếm phải:

- Gắn với **caller/tenant** đã được xác thực, không thể dùng chéo người dùng.
- Gắn với base/scope/filter/sort/projection đã được chuẩn hóa và kiểm soát; khi user đổi filter, bắt đầu search mới.
- Có **TTL và giới hạn dung lượng** cache, số phiên đồng thời, số trang được lưu.
- Không lộ DN, service account credential hoặc cookie LDAP thô trong URL/log.
- Có cơ chế xóa state khi logout, hết hạn hoặc thay đổi quyền.
- Không hứa cursor dùng lại được sau khi restart/đổi replica nếu backend không hỗ trợ.

Chỉ thêm những tính năng này khi có yêu cầu sản phẩm rõ; với chức năng nội bộ đọc vài trang, UI “Tiếp” cùng giới hạn dữ liệu có thể đơn giản và an toàn hơn.

## 9. Bốn lựa chọn khi thật sự cần nhảy tới vị trí bất kỳ

| Lựa chọn | Có nhảy đến trang k? | Đánh đổi / điều kiện |
| --- | --- | --- |
| **RFC 2696 thuần** | **Không trực tiếp**; muốn tới k phải đi tuần tự. | Ít phụ thuộc provider, nhưng tốn k request và cần cùng connection. |
| **Cache các trang đã xem** | Chỉ những trang đã cache. | Tốn memory/storage, TTL, ACL, không phải snapshot toàn directory. |
| **Virtual List View (VLV) + server-side sort**, nếu provider hỗ trợ. | Có thể yêu cầu cửa sổ quanh **offset** và nhận ước lượng số lượng. | Là control mở rộng, không phổ biến trên mọi LDAP server; cần sort/index/policy phù hợp. |
| **Snapshot/index vào database hoặc search service** | Có thể triển khai offset, keyset và tổng số theo snapshot/index. | Cần đồng bộ, bảo mật PII, dữ liệu có độ trễ và chi phí vận hành. |

Ngoài ra, nếu chỉ cần tìm danh tính theo một khóa xác định, **lookup/search chính xác theo stable ID hoặc username** tốt hơn nhiều so với việc tìm bằng “trang 40”.

### 9.1. Virtual List View (VLV) không phải RFC 2696

Một số directory hỗ trợ LDAP **Virtual List View**, thường đi cùng **server-side sorting**. VLV có thể đề nghị một **cửa sổ kết quả quanh offset** thay vì bắt buộc duyệt mọi trang bằng cookie tuần tự.

~~~text
Client yêu cầu:
  sắp xếp theo cn
  lấy cửa sổ quanh vị trí 3.900

Server (nếu có VLV + sort phù hợp):
  trả cửa sổ kết quả + metadata/ước lượng theo control
~~~

Nhưng:

- VLV **không nằm trong khả năng mặc định của Simple Paged Results**.
- Không phải OpenLDAP/AD/proxy/provider nào cũng hỗ trợ như nhau; schema, index, quyền và query policy ảnh hưởng kết quả.
- Cần kiểm chứng OID controls/cách sử dụng theo **từng server**.
- Sắp xếp có thể thay đổi khi entry được thêm/xóa/rename; offset không tự tạo snapshot ổn định.
- Số lượng trả về/ước lượng của VLV cũng không nên mặc định là exact count.

**Chỉ chọn VLV khi có yêu cầu random access thật và server hiện tại hỗ trợ rõ ràng**, không tự cấu hình VLV cho mọi LDAP endpoint.

### 9.2. Keyset/seek pagination theo thuộc tính được sắp xếp

Một hướng khác là truy vấn theo giá trị khóa cuối cùng đã thấy: ví dụ bắt đầu tại `uid` lớn hơn một giá trị theo quy tắc so sánh. Tuy nhiên LDAP filter và matching rule **không phải SQL `WHERE uid > x ORDER BY uid`** theo nghĩa tổng quát:

1. Không phải mọi attribute đều có ordering matching rule được server hỗ trợ.
2. Filter `(uid>=x)` chỉ là **điều kiện so sánh theo schema**, không cam kết thứ tự kết quả.
3. Muốn seek pagination đáng tin cậy cần **server-side sort** hoặc thứ tự được provider đảm bảo, khóa duy nhất, và logic chặn duplicate/missing khi dữ liệu thay đổi.
4. DN/username không ổn định qua rename/đổi username; nếu dùng làm khóa vị trí, cần xử lý đặc thù.

Không coi “đổi sang `uid>=lastUid`” là mẹo chung để nhảy trực tiếp đến trang tùy ý. Nó còn không giải quyết việc muốn trang 40 khi chưa biết khóa bắt đầu của trang đó.

### 9.3. Snapshot/index riêng cho UX bảng dữ liệu

Đối với một trang quản trị cần lọc/sắp xếp/nhảy trang/phân trang ngược và tổng số, kiến trúc thường rõ ràng hơn là:

~~~mermaid
flowchart LR
    A["LDAP server"] --> B["Job đồng bộ theo trang<br/>stable ID + reconciliation"]
    B --> C["Database snapshot / search index"]
    D["HTTP UI"] --> E["Query API có authz, sort, page"]
    E --> C
    C --> F["Trang dữ liệu + total có timestamp"]
    F --> D
~~~

Trong mô hình này:

- Đồng bộ LDAP bằng `LdapTemplate` và phân trang phù hợp.
- Định danh link bằng `(provider_key, stable_external_id)`; `DN`, `cn`, `uid` có thể thay đổi.
- API áp ACL/tenant policy ở **lớp query** trước khi trả snapshot.
- Database có index/sort và khả năng đếm theo dataset đang lưu; đặt timestamp **asOf** và trạng thái **lastSuccessfulSync**.
- Tổng số là số lượng trong **snapshot/index ở thời điểm được xác định**, không khẳng định bằng số người hiện tại trên LDAP nếu đồng bộ có độ trễ.

Đây không phải cách bỏ qua quyền LDAP: dữ liệu khi lấy từ directory vẫn phải tuân thủ ACL và bảo vệ trên đường truyền; bản sao trong database cần quyền, mã hóa và retention phù hợp.

## 10. Tính nhất quán: tổng ước lượng và trang đều có thể thay đổi

RFC 2696 không bảo đảm tất cả các trang phản ánh **một snapshot**. Trong lúc quét, một entry có thể được thêm, xóa, chuyển OU hoặc đổi thuộc tính. Hãy xem:

~~~text
T0: Search bắt đầu, server estimate 8.300
T1: Client nhận trang 1
T2: 50 account mới được tạo, 10 account bị xóa
T3: Client nhận trang 2, server estimate có thể đổi
T4: Client kết thúc scan
~~~

Ngay cả nếu tất cả trang đều kết thúc không lỗi:

- `estimate=8.300` ở T0 không phải chính xác total ở T4.
- Số `observedCount` có thể không giống một snapshot tại T0 hoặc T4.
- Nếu không có sort/snapshot bảo đảm, một số entry có thể xuất hiện lại hoặc bị bỏ sót trong các điều kiện thay đổi/topology cụ thể.
- Nếu yêu cầu định danh, dùng stable ID để deduplicate và đối soát sau full scan.
- Nếu dùng estimatedTotal để dựng page navigation, số “trang cuối” có thể biến động gây UX khó hiểu.

### 10.1. Sort control có giải quyết snapshot không?

Không hoàn toàn. **Server-side sorting (RFC 2891)** giúp yêu cầu thứ tự kết quả theo thuộc tính khi server hỗ trợ, nhưng không tự biến một chuỗi paged search thành snapshot bất biến. Sort cũng có chi phí tài nguyên, yêu cầu matching rules/index và giới hạn quyền. Người dùng nhìn thấy một trang được sắp xếp không nên suy ra tổng số trang là cố định.

### 10.2. Full scan phục vụ đồng bộ

Nếu mục tiêu là đối soát nhân sự:

1. Gắn mỗi entry với stable ID theo provider, ví dụ `entryUUID` của directory có RFC 4530 hoặc `objectGUID` nhị phân của AD sau khi decode đúng.
2. Upsert idempotent vào database với unique constraint trên `(provider_key, external_id)`.
3. Ghi `run_id`, `observedCount`, `pageCount` và trạng thái `COMPLETE/PARTIAL/FAILED`.
4. Chỉ đánh dấu những entry vắng mặt sau một **full scan** có phạm vi đủ và không lỗi, kèm chính sách grace period/cross-check phù hợp.
5. Không dùng size estimate để xác định entry bị xóa hoặc quyết định đã đọc đủ trang.

**Ước lượng giúp trải nghiệm và capacity planning; nó không phải nguồn sự thật để xóa hay vô hiệu hóa người dùng.**

## 11. Quyền truy cập: “tổng số kết quả” cũng có thể nhạy cảm

Một ứng dụng dùng `cn=app-reader,ou=services,...` có thể tìm nhiều entry hơn một người dùng HTTP bình thường được phép xem. **LDAP ACL** điều khiển account bind; **Spring Security/authorization nghiệp vụ** điều khiển dữ liệu trả cho caller.

### 11.1. Nếu estimate xuất phát từ một search rộng

Giả sử:

~~~text
Bind account: được search ou=people gồm 8.300 người
HTTP caller: chỉ được xem ou=engineering gồm 450 người
~~~

Trả ngay `estimatedTotal=8300` cho caller Engineering có thể tiết lộ **quy mô/phạm vi ngoài quyền**. Cũng không thể lấy estimate 8.300 rồi lọc 450 item ở Java và vẫn hiển thị “8.300 kết quả”. Search base/filter và mọi con số hiển thị phải thuộc **phạm vi đã phân quyền**.

### 11.2. Các biện pháp bắt buộc

- Giới hạn search base, filter, scope và returning attributes theo use case; không nhận tùy ý các giá trị đó từ HTTP client.
- Dùng `LdapQueryBuilder.where(...).is(value)` hoặc `EqualsFilter` để escape giá trị filter theo RFC 4515.
- Dùng `LdapNameBuilder`/`Rdn` khi dựng DN; DN escaping khác filter escaping.
- Dùng TLS (LDAPS hoặc StartTLS đúng cách), xác minh hostname/CA, quản lý bind password qua secret manager.
- Áp authorization theo tenant/OU/object và rate limit; không dựa chỉ vào quyền read của service account.
- Không log raw cookie, bind secret, nguyên filter chứa PII, hoặc toàn bộ entry.
- Giới hạn số kết nối/scan đồng thời; tránh giữ LDAP connection qua nhiều HTTP requests.
- Không coi search trả rỗng do ACL là bằng chứng người dùng không tồn tại hoặc đã nghỉ việc.

### 11.3. Cookie có phải dữ liệu mật không?

RFC 2696 không mô tả cookie như một credential đăng nhập, nhưng nó là **trạng thái opaque do server cấp** và có thể liên quan tới phiên/search. Xử lý nó như dữ liệu nội bộ: không giải mã, không đưa vào analytics/URL công khai, không cho người dùng khác tái sử dụng và không lưu lâu hơn cần thiết. Nếu xây application token, áp ràng buộc danh tính, quyền, TTL và chống sửa giả.

## 12. Chi phí mô phỏng nhảy trang và giới hạn ứng dụng

Giả sử danh bạ có khoảng 50.000 entry, page size 100 và UI cho phép người dùng nhập `page=400`. Chỉ để đến trang đó bằng RFC 2696 thuần, client có thể phải yêu cầu khoảng **400 trang** (40.000 entry được server duyệt/trả) rồi bỏ 399 trang đầu. Nhiều người dùng cùng làm như vậy có thể gây áp lực lớn lên directory.

Một API nên giới hạn:

| Giới hạn | Ví dụ chính sách | Mục đích |
| --- | --- | --- |
| `pageSize` | 20–100 cho UI thông thường. | Giảm response/PII mỗi request. |
| `maxSequentialPages` | Không cho đi qua quá 10 trang chỉ vì một request nhảy sâu. | Chặn request tốn tài nguyên không tương xứng. |
| `maxConcurrentScans` | Quota theo toàn hệ thống/tenant. | Không làm cạn LDAP connection pool. |
| `scanDeadline` | Deadline toàn job/luồng. | Không giữ context vô hạn. |
| `cacheTtl` | Thời hạn ngắn và max cached pages. | Tránh dữ liệu lỗi thời/chiếm bộ nhớ lâu. |
| `maxEstimatedTotalDisplayed` | Chỉ hiển thị estimate trong scope được phép. | Tránh rò rỉ thông tin qua tổng số. |
| `maxPagesToCount` | Trần rõ ràng cho thao tác thống kê. | Không biến mỗi click “bao nhiêu user?” thành full scan. |

Các con số trong bảng chỉ là **ví dụ chính sách ứng dụng**. Cần chọn theo server policy, SLA, số người dùng, quy mô entry và yêu cầu kiểm toán. Nếu cần jump sâu thường xuyên, dùng VLV được xác minh hoặc snapshot/index riêng thay vì tăng quota mô phỏng.

### 12.1. Phân biệt page size và giới hạn kết quả

`LdapQueryBuilder.countLimit(100)` giới hạn search theo API, **không tự tạo paging cursor**. Khi dùng RFC 2696, `pageSize=100` là số entry **đề nghị mỗi trang**, còn số trang tiếp tục được quyết định qua cookie. Không dùng `countLimit(100)` rồi gọi lại filter giống hệt 400 lần để “đến trang 400”: nó có thể trả lại **cùng 100 entry đầu tiên**.

## 13. Kiểm thử đúng cả cursor và total estimate

### 13.1. Kiểm tra capability server

Trên directory **test** được cấp quyền, dùng `ldapsearch` truy vấn root DSE:

~~~bash
ldapsearch -LLL -x \
  -H "ldaps://ldap.example.org:636" \
  -D "cn=app-reader,ou=services,dc=example,dc=org" -W \
  -b "" -s base "(objectClass=*)" supportedControl
~~~

Tìm OID RFC 2696 `1.2.840.113556.1.4.319`. Không thấy OID chưa đủ để kết luận chắc chắn server không hỗ trợ; kiểm tra quyền, proxy và tài liệu provider, sau đó thử paging theo chính sách lab.

~~~bash
ldapsearch -LLL -x \
  -H "ldaps://ldap.example.org:636" \
  -D "cn=app-reader,ou=services,dc=example,dc=org" -W \
  -b "ou=people,dc=example,dc=org" -s sub \
  -E pr=100/noprompt \
  "(objectClass=inetOrgPerson)" dn uid cn
~~~

CLI `-E pr=100/noprompt` (OpenLDAP tools) giúp kiểm tra server hỗ trợ phân trang và tự tiếp tục; **không có nghĩa Java tự giữ đúng connection**. `-W` yêu cầu nhập password tương tác; không đặt secret trên dòng lệnh.

### 13.2. Ma trận kiểm thử cốt lõi

| Kịch bản | Thao tác | Kỳ vọng |
| --- | --- | --- |
| Server trả estimate dương. | Paged response có `size=1000`. | UI ghi “ước tính”, không tuyên bố exact count. |
| Server trả `size=0` nhưng cookie còn. | Duyệt trang đầu rồi đọc response control. | **UNKNOWN estimate**, `hasNext=true`. |
| Server trả `size=0` và không có entry. | Truy vấn dataset rỗng có response kết thúc. | Scan kết thúc, `observedCount=0`; phân biệt metadata estimate. |
| Trang có 60 entry với pageSize 100, cookie còn. | Kiểm tra logic vòng lặp. | Tiếp tục, không break chỉ vì trang ngắn. |
| Trang đủ 100 entry, cookie kết thúc. | Kiểm tra logic vòng lặp. | Kết thúc, không yêu cầu một trang thừa vì thấy đủ 100. |
| Muốn trang 40 nhưng chỉ có cookie trang 1. | Gửi `page=40`. | API không khẳng định truy cập trực tiếp; cần chính sách/giải pháp khác. |
| Người dùng nhấn **Trước**. | Đang ở trang 3. | Chỉ dùng cache trang đã lưu hoặc chiến lược được thiết kế riêng, không tự tăng/giảm cookie. |
| Cookie hết hạn hoặc đổi backend. | Chuyển từ server A sang B. | Phát hiện lỗi, làm mới search; không tự tiếp tục cookie cũ. |
| User thay đổi filter. | Từ `cn=Nguyen` sang `cn=Tran`. | Bắt đầu chuỗi mới; không reuse cookie. |
| Directory đổi dữ liệu khi scan. | Thêm/rename/xóa entry test. | Không kết luận snapshot/tổng exact. |
| Caller bị giới hạn OU. | Search theo tenant khác. | Không lộ items hay estimatedTotal ngoài quyền. |
| Không có Paged Results Response Control. | Server không gửi control. | Báo FAILED hoặc unsupported; không biến partial data thành COMPLETE. |
| Lỗi mapper ở trang 5. | Consumer ném exception. | Scan FAILED; observedCount không được công bố là total. |
| `maxPages` đạt khi cookie còn. | Cấu hình limit thấp. | Báo PARTIAL/FAILED, không tuyên bố đã đọc hết. |
| Server size/time/admin limit. | Query gây vượt policy trong test. | Phân loại lỗi rõ, không dùng count partial làm exact. |
| Cùng dữ liệu, khác tài khoản ACL. | Search bằng reader-a và reader-b. | Số kết quả/estimate có thể khác theo quyền, không tự nâng quyền. |

### 13.3. Unit test xử lý estimate không có

Tách logic diễn giải `size` khỏi code LDAP/JNDI để kiểm thử:

~~~java
import java.util.OptionalInt;

public final class LdapResultEstimate {
    private LdapResultEstimate() {}

    public static OptionalInt fromResponseSize(int responseSize) {
        if (responseSize <= 0) {
            return OptionalInt.empty();
        }
        return OptionalInt.of(responseSize);
    }
}
~~~

JUnit 5:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class LdapResultEstimateTest {

    @Test
    void zeroMeansUnknownNotExactZero() {
        assertTrue(LdapResultEstimate.fromResponseSize(0).isEmpty());
    }

    @Test
    void positiveValueIsOnlyAnEstimate() {
        var estimate = LdapResultEstimate.fromResponseSize(8300);
        assertEquals(8300, estimate.orElseThrow());
    }
}
~~~

Hai test chứng minh contract của **đoạn code ứng dụng**, không chứng minh server thực tế trả `size=0`/`8300`. Cần integration test để quan sát response controls của directory, cookie và ACL. Nếu UI cần exact count, phải thiết kế và kiểm thử một nguồn đếm khác có timestamp và phạm vi xác định.

## 14. Bài tập tình huống

Một ứng dụng HR sử dụng Spring LDAP đọc **khoảng 21.500 nhân viên** từ `ou=people,dc=company,dc=internal`. Quản trị viên xác nhận server hỗ trợ RFC 2696, page size được ứng dụng chọn là `200`. Người dùng muốn:

- Trang đầu có 200 nhân viên; nút **Tiếp / Trước**.
- Nhảy ngay đến trang 55.
- Nhìn thấy “Tổng số nhân viên: 21.500” và “Trang 1 / 108”.
- Có thể thay filter theo phòng ban.
- Quyền xem dữ liệu phân theo tenant.

Trong lần truy vấn đầu, server trả `size=21500` và cookie `A`. Ở trang thứ hai, server trả `size=0` nhưng cookie `B` vẫn còn. Một số nhân viên đang được chuyển OU trong lúc quét.

**Yêu cầu:**

1. Có thể suy cookie của trang 55 từ `pageSize=200` và số `55` hay không? Giải thích.
2. Nếu đi tuần tự từ đầu tới trang 55, client phải thực hiện khoảng bao nhiêu lần search và duyệt bao nhiêu entry?
3. `size=21500` có chứng minh tổng số người chính xác hay không? `size=0` ở trang hai nghĩa là gì?
4. Có được hiển thị “Trang 1 / 108” như một con số chính xác không? Nên viết UI thế nào?
5. Người dùng nhấn **Trước** ở trang ba: tại sao chỉ có cookie của trang hai chưa bảo đảm có thể truy cập ngược? Đưa ra một cách làm hợp lý.
6. Khi chuyển từ filter phòng Engineering sang Finance, có được reuse cookie cũ không?
7. Có nên giữ riêng một LDAP connection cho mỗi session HTTP người dùng trong 30 phút để duy trì cookie không? Nêu rủi ro.
8. Nếu sản phẩm bắt buộc có nút nhảy trang, so sánh VLV nếu server hỗ trợ với snapshot/index database.
9. Nếu caller chỉ được xem tenant A nhưng service account đọc cả công ty, “ước lượng tổng số” cần được tính/hiển thị theo quyền nào?
10. Khi một entry bị move giữa các trang, vì sao không thể dùng `observedCount` làm snapshot count tại một thời điểm?
11. Viết điều kiện dừng đúng cho paged search và cách xử lý khi response control không có.
12. Nếu dùng snapshot database, cần hiển thị thông tin gì để người dùng hiểu độ mới của dữ liệu?

**Gợi ý lời giải:**

- (1) Không. Cookie là token opaque của server, không thể suy từ offset.
- (2) Khoảng **55 search**, và nếu server trả đủ 200 entry mỗi trang, khoảng **11.000 entry được duyệt/trả** để tới hết trang 55. Chi phí thật phụ thuộc server, network và biến động dữ liệu.
- (3) `21500` chỉ là estimated total; `0` ở response tiếp theo có nghĩa server không có estimate hữu ích, **không** chứng minh không còn nhân viên.
- (4) Nếu muốn dùng số trang, phải ghi **“ước tính”**; tốt hơn là “Đã tải 200 — Tiếp” với `hasNext`. Khi cần tổng exact, dùng một snapshot nguồn khác có thời điểm đồng bộ rõ.
- (5) Dùng cache các trang trước có giới hạn, hoặc snapshot/index; không coi cookie là backward cursor bền vững.
- (6) Không. Filter mới tương ứng một chuỗi search mới.
- (7) Không nên làm mặc định: dễ hết LDAP connections, timeout, lộ state và phụ thuộc backend. Dùng job/cache/index hợp lý.
- (8) VLV cần server-side sort, support và policy riêng; snapshot database giải quyết UX random access tốt hơn nhưng có độ trễ đồng bộ và chi phí bảo vệ PII.
- (9) Phải theo phạm vi mà **caller HTTP được phép xem**; không tiết lộ estimate của OU/tenant khác.
- (10) RFC 2696 không tạo snapshot; entry có thể thêm/xóa/rename trong khi scan.
- (11) Dừng khi cookie rỗng; thiếu control hoặc lỗi giữa search → FAILED, không dùng observedCount như full total.
- (12) Hiển thị `asOf`, `lastSuccessfulSync` hoặc nhãn dữ liệu cập nhật đến thời điểm nào; mọi sort/total được tính trên phạm vi snapshot được phân quyền.

## 15. Ghi nhớ

**Simple Paged Results của LDAP là cơ chế lấy trang kế tiếp bằng cookie, không phải cơ chế nhảy tới trang tùy ý.** Client không tính được cookie trang k từ `k × pageSize`, và không có backward page chuẩn trong RFC 2696. Nếu cần nút **Trước**, hãy cache trang đã xem có giới hạn; nếu cần nhảy sâu, cân nhắc VLV/server-side sort được nhà cung cấp hỗ trợ hoặc snapshot/index database.

**`size` trong Paged Results Response Control là ước lượng**, có thể bằng `0` khi không có ước lượng. Không dùng nó làm exact total, không suy số trang cuối chắc chắn và không dùng để xóa dữ liệu vắng mặt. Thiết kế an toàn cần tách `observedCount`, `estimatedTotal` và `scanCompleted`; giữ cookie trên kết nối phù hợp, kiểm soát TLS/ACL/authorization, giới hạn thời gian và số trang, đồng thời công bố rõ độ mới của mọi kết quả snapshot.

### Tài liệu tham khảo

- [RFC 2696 — LDAP Control Extension for Simple Paged Results Manipulation](https://www.rfc-editor.org/rfc/rfc2696)
- [RFC 2891 — LDAP Control Extension for Server Side Sorting of Search Results](https://www.rfc-editor.org/rfc/rfc2891)
- [RFC 4511 — Lightweight Directory Access Protocol (LDAP): The Protocol](https://www.rfc-editor.org/rfc/rfc4511)
- [RFC 4515 — LDAP String Representation of Search Filters](https://www.rfc-editor.org/rfc/rfc4515)
- [Spring LDAP — Processing the DirContext](https://docs.spring.io/spring-ldap/reference/processing-the-dircontext.html)
- [Spring LDAP — Basic Usage and LdapTemplate](https://docs.spring.io/spring-ldap/reference/basic.html)
- [Spring Data LDAP Reference](https://docs.spring.io/spring-data/ldap/reference/)
- [Java SE 17 — PagedResultsResponseControl](https://docs.oracle.com/en/java/javase/17/docs/api/java.naming/javax/naming/ldap/PagedResultsResponseControl.html)
- [Java SE 17 — PagedResultsControl](https://docs.oracle.com/en/java/javase/17/docs/api/java.naming/javax/naming/ldap/PagedResultsControl.html)
