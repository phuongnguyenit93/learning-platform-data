# Chọn kích thước trang theo giới hạn máy chủ và ứng dụng

Khi đọc danh bạ LDAP lớn qua Spring Data LDAP, chúng ta thường nghe đề xuất: “Cứ đặt page size bằng 1.000 để giảm số lần gọi server”. Con số đó có thể phù hợp với một môi trường nhưng quá lớn với môi trường khác. Một entry chỉ có `uid` và `cn` rất nhỏ; một entry tải ảnh, chứng chỉ, thuộc tính nhiều giá trị và hàng trăm DN nhóm có thể lớn hơn nhiều. Mạng giữa ứng dụng và directory cũng có thể có độ trễ vài mili giây hoặc hàng trăm mili giây. Ngoài ra, mỗi request phân trang cần được xử lý và giữ kết nối trong suốt chuỗi truy vấn.

Trong chương **Phân trang và controls** của module **SPRING_DATA_LDAP**, bài này tập trung vào quyết định **chọn kích thước trang (LDAP page size)** khi sử dụng Simple Paged Results Control của **RFC 2696**. Spring Data LDAP cung cấp repository, ODM và mô hình entry/DN; `LdapTemplate` của Spring LDAP cho phép thực hiện search và gắn các LDAP controls cần thiết. Lựa chọn page size phải kết hợp **giới hạn LDAP server**, **bộ nhớ ứng dụng**, **độ trễ mạng**, **tốc độ xử lý từng entry**, **số job đồng thời** và **yêu cầu hoàn tất dữ liệu**.

**Nguyên tắc cốt lõi:** page size là một tham số vận hành cần **đo lường và giới hạn**, không phải một con số “tối ưu cho mọi hệ thống”. Bài sử dụng số liệu giả định để minh họa phép tính; các giá trị không phải mặc định bắt buộc của LDAP hoặc Spring.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt `page size` của RFC 2696 với `countLimit`, size limit server, batch size ghi database và HTTP pagination.
2. Xác định các giới hạn mà LDAP server áp dụng cho paged search, bao gồm hỗ trợ control, policy kích thước trang và giới hạn tài nguyên.
3. Ước tính mức sử dụng heap theo **page size × kích thước entry × số scan đồng thời × hệ số overhead**.
4. Giải thích khi nào page nhỏ tốt hơn page lớn và ngược lại theo RTT, thời gian search, GC và throughput.
5. Chọn page size khởi đầu qua một bảng quyết định, sau đó hiệu chỉnh dựa trên số liệu p50/p95, timeout, heap và tiến độ scan.
6. Cấu hình page size có chặn biên ở Spring Boot, sử dụng với `LdapTemplate`/paged control và xử lý cookie đúng.
7. Xây bài kiểm thử áp lực và tiêu chí chấp nhận mà không nhầm một kết quả thiếu thành một lần quét hoàn chỉnh.

## 2. Page size thực sự kiểm soát điều gì?

**Simple Paged Results** (RFC 2696) cho client gửi kích thước trang được đề nghị và một cookie tiếp tục. Server phản hồi các entry phù hợp cùng cookie mới nếu còn kết quả. Control có OID:

~~~text
1.2.840.113556.1.4.319
~~~

Sơ đồ ví dụ một lần quét `N = 2.505` entry, `S = 250`:

~~~mermaid
flowchart TD
    A["Client yêu cầu 250 entry, cookie ban đầu rỗng"] --> B["LDAP server kiểm tra filter, scope, ACL và policy"]
    B --> C["Trả trang 1 + cookie 1"]
    C --> D["Client xử lý trang, dùng cookie mới"]
    D --> E{"Cookie còn cho trang tiếp?"}
    E -- "Có" --> F["Gửi search tiếp theo trên cùng connection"]
    F --> B
    E -- "Không" --> G["Quét hoàn chỉnh nếu không có lỗi"]
~~~

Các điểm cần nhớ:

- `S = 250` nghĩa là **đề nghị server trả khoảng 250 entry trong một lần phản hồi**, không yêu cầu server lưu một số thứ tự trang ổn định.
- Server có thể điều chỉnh số entry thực trả, áp đặt policy riêng, hoặc từ chối control/operation theo cấu hình. **Không cam kết mỗi trang đúng S entry**.
- Cookie là **opaque token**, không phải offset như `LIMIT/OFFSET` trong SQL.
- Cần giữ cùng search base, scope, filter và context theo hợp đồng thư viện/server. Khi sử dụng Spring LDAP, cơ chế `SingleContextSource` giúp giữ cùng kết nối xuyên suốt một chuỗi paged search.
- Chỉ khi response control cho biết **không còn trang** và tất cả trang đều được xử lý không lỗi, ứng dụng mới được đánh dấu scan hoàn tất.

### 2.1. Không nhầm với các giới hạn khác

| Tham số | Nó giới hạn gì? | Có tự cho phép lấy trang tiếp theo? |
| --- | --- | --- |
| **LDAP page size** | Kích thước trang yêu cầu trong RFC 2696. | Có, qua paging cookie nếu server hỗ trợ. |
| `LdapQueryBuilder.countLimit(...)` | Giới hạn số kết quả của một truy vấn theo API. | **Không** tạo cookie. |
| `SearchControls.setCountLimit(...)` | Giới hạn số kết quả theo JNDI search controls. | **Không** thay thế paged control. |
| **Server size limit / search limit** | Policy của directory, có thể khác theo tài khoản, query hoặc cơ chế paging. | Phụ thuộc server; không tự được vô hiệu hóa khi bật paging. |
| **Database batch size** | Số dòng ghi trong một transaction/batch ở hệ downstream. | Không quyết định LDAP page size. |
| **HTTP page size** | Số item API trả cho người dùng. | Không đồng nhất với cookie LDAP và có vòng đời khác. |

Ví dụ, một ứng dụng có thể **đọc 250 entry LDAP mỗi trang**, chuyển thành DTO rồi **ghi database theo batch 100 dòng**. Hai tham số đáp ứng hai mục tiêu khác nhau; không cần bắt buộc trùng nhau.

## 3. Các ràng buộc phía LDAP server

Trước khi chọn `S`, phải biết hệ thống directory đang cung cấp những gì.

### 3.1. Server có hỗ trợ RFC 2696 không?

Truy vấn root DSE, nơi nhiều LDAP server công bố `supportedControl`:

~~~bash
ldapsearch -LLL -x \
  -H "ldaps://ldap.example.org:636" \
  -D "cn=app-reader,ou=services,dc=example,dc=org" -W \
  -b "" -s base "(objectClass=*)" supportedControl
~~~

Tìm OID `1.2.840.113556.1.4.319`. `-W` hỏi password qua prompt; không đưa secret vào command-line. Nếu không thấy, xác minh với quản trị viên và thử control trên directory test được cấp quyền. Việc OID không hiển thị trong một câu trả lời chưa đủ để tự sửa ACL hay cho rằng có thể dùng bất kỳ kích thước nào.

Kiểm tra bằng OpenLDAP command-line client (trên server hỗ trợ):

~~~bash
ldapsearch -LLL -x \
  -H "ldaps://ldap.example.org:636" \
  -D "cn=app-reader,ou=services,dc=example,dc=org" -W \
  -b "ou=people,dc=example,dc=org" -s sub \
  -E pr=250/noprompt \
  "(&(objectClass=inetOrgPerson)(uid=*))" dn uid cn
~~~

`-E pr=250/noprompt` khiến công cụ thử Simple Paged Results và tự tiếp tục khi có cookie. Đây là cách kiểm chứng **capability** và tập dữ liệu; chưa phải kết luận về hiệu năng của code Spring Boot.

### 3.2. Chính sách kích thước trang không giống nhau giữa các sản phẩm

Mỗi directory có các tham số và giới hạn riêng. Ví dụ:

| Môi trường | Những điều cần xác minh | Không nên suy luận |
| --- | --- | --- |
| **Microsoft Active Directory** | LDAP query policies như `MaxPageSize`, quyền account, khả năng paging và topology domain controller. | Giá trị thường gặp **1.000** không phải mức cố định của mọi domain/chính sách. |
| **OpenLDAP** | `sizelimit`/`timelimit`, khả năng paged results, overlay/cấu hình và giới hạn thao tác. | Không mặc nhiên giống cấu hình AD hoặc bỏ mọi giới hạn khi dùng paging. |
| **LDAP proxy/load balancer** | Policy tại proxy, backend thực, stickiness, timeout và khả năng duy trì cookie. | Kết nối vào một VIP không bảo đảm cookie của A dùng được trên B. |
| **Directory dịch vụ quản lý** | Tài liệu provider, quota, page size tối đa, rate limit và khả năng truy cập root DSE. | Không tự chọn 5.000/10.000 vì endpoint phản hồi nhanh một lần. |

**Kích thước trang hợp lệ phụ thuộc server và chính sách của tài khoản đang bind.** Một server có thể giới hạn page size, trả ít entry hơn yêu cầu, từ chối truy vấn, áp tổng giới hạn hoặc timeout. Phải quan sát hành vi thực tế, không dùng kết quả từ một môi trường dev để khẳng định production cũng vậy.

### 3.3. Giới hạn của search query quan trọng không kém page size

Hai truy vấn dưới đây có rủi ro khác nhau dù cùng `S = 500`:

~~~text
Query A:
  base  = ou=employees,dc=example,dc=org
  scope = ONELEVEL
  filter= (&(objectClass=inetOrgPerson)(uid=lan))

Query B:
  base  = dc=example,dc=org
  scope = SUBTREE
  filter= (objectClass=*)
~~~

Query B có thể duyệt cả account dịch vụ, nhóm và các OU khác. Chọn trang nhỏ hơn không biến query B thành an toàn. **Search base, scope, filter và authorization** phải được thiết kế trước khi tối ưu page size.

## 4. Các ràng buộc phía ứng dụng

Một Spring Boot service có bộ nhớ, CPU, connection pool và thời gian xử lý hữu hạn. Mỗi trang có thể gồm kết quả JNDI, object `Attributes`, DTO Java, dữ liệu tạm của mapper và batch ghi database.

### 4.1. Kích thước mỗi entry

Không có một “kích thước entry LDAP” dùng được cho mọi ứng dụng:

| Kiểu projection | Ví dụ attribute | Tác động tới page size |
| --- | --- | --- |
| **Danh bạ tối giản** | `uid`, `cn`. | Thường nhỏ; có thể thử page lớn hơn. |
| **Danh bạ liên hệ** | `uid`, `cn`, `mail`, `telephoneNumber`. | Mỗi entry lớn hơn một chút; cần đo. |
| **Nhóm nhiều thành viên** | `member`/`uniqueMember` chứa hàng trăm hoặc hàng nghìn DN. | Có thể rất lớn và biến động mạnh. |
| **Đối tượng có ảnh/chứng chỉ** | `thumbnailPhoto`, `jpegPhoto`, `userCertificate`. | Có thể làm page lớn tạo áp lực heap/network. |
| **Metadata nhị phân** | `objectGUID`, `objectSid`. | Cần mapper đúng kiểu; chỉ thêm khi nghiệp vụ cần. |

Nếu chỉ cần hiển thị tên và email, dùng `.attributes("uid", "cn", "mail")` hoặc `SearchControls.setReturningAttributes(...)` để yêu cầu đúng các thuộc tính. **Projection nhỏ thường cải thiện hiệu năng hơn việc tăng page size một cách mù quáng.**

### 4.2. Page size nhân với mức đồng thời

Giả sử mỗi trang sau khi map có `S` DTO; một job có thể giữ cả dữ liệu JNDI lẫn DTO cùng lúc. Nếu có `C` job chạy song song, tác động bộ nhớ xấp xỉ:

\[
M_{\text{paging}} \approx S \times B_{\text{entry}} \times C \times K
\]

Trong đó:

- `S`: số entry mỗi trang yêu cầu.
- `B_entry`: mức dùng bộ nhớ **ước tính** cho một entry đã ánh xạ, đo bằng profiler hoặc thống kê thực nghiệm.
- `C`: số chuỗi scan đồng thời tối đa.
- `K`: hệ số an toàn cho kết quả trung gian, object overhead, GC và dao động kích thước entry (ví dụ `2`–`3` để lập kế hoạch sơ bộ, không phải hằng số JVM).

Đây là **ước lượng hoạch định**, không phải công thức đo chính xác dung lượng heap Java. Bộ nhớ thực phụ thuộc implementation, charset, số lượng attribute, collection, heap layout, mapper và tốc độ downstream giải phóng page.

**Điểm quan trọng:** đừng lấy toàn bộ `-Xmx` làm ngân sách paging. Heap còn dùng cho HTTP requests, cache, thread, JIT/runtime, các job khác và những phần của ứng dụng không liên quan LDAP.

### 4.3. Độ trễ mạng và số round-trip

Nếu directory có tổng `N` entry và server trả khoảng `S` mỗi trang, số lượt search tối thiểu để nhận tất cả entry thường xấp xỉ:

\[
P \approx \left\lceil\frac{N}{S}\right\rceil
\]

Ước lượng thời gian:

\[
T_{\text{scan}} \approx P\,(T_{\text{roundtrip}} + T_{\text{fixed-server}})
       + N\,T_{\text{per-entry}}
       + T_{\text{downstream}}
\]

Số hạng `T_per-entry` có thể bao gồm truyền dữ liệu, decode và map từng entry. Công thức chỉ là mô hình gần đúng: server có thể thực hiện công việc thay đổi theo filter/index, trả số lượng không đúng yêu cầu và có thể phát sinh thêm thao tác kiểm tra kết thúc.

Khi RTT lớn, page quá nhỏ gây nhiều round-trip. Khi entry lớn hoặc downstream chậm, page quá lớn gây áp lực RAM, GC và latency. **Không có một S tối ưu độc lập với môi trường.**

## 5. Ví dụ tính kích thước trang từ ngân sách bộ nhớ

Giả sử quản trị viên xác nhận server thử nghiệm hỗ trợ paging và chính sách hiện tại cho phép **tối đa 1.000 entry/trang**. Đội ứng dụng quyết định:

| Thông số | Giá trị giả định |
| --- | --- |
| Giới hạn page từ directory | `1.000` entry. |
| Số scan chạy song song tối đa | `3`. |
| Ngân sách heap dành riêng cho paging | `20 MiB` cho cả ba scan. |
| Bộ nhớ đo/ước lượng mỗi DTO cùng dữ liệu thường trú | `3,5 KiB` mỗi entry. |
| Hệ số an toàn cho dữ liệu trung gian | `2,5`. |
| Giới hạn cấu hình nghiệp vụ | `500` entry/trang. |

Tính giới hạn từ bộ nhớ:

\[
S_{\text{heap}} =
\left\lfloor
\frac{20 \times 1024 \times 1024}
{3 \times 3{,}5 \times 1024 \times 2{,}5}
\right\rfloor \approx 780
\]

Ta lấy giá trị nhỏ nhất giữa **server cap 1.000**, **heap cap khoảng 780** và **application cap 500**:

\[
S_{\text{chọn}} = \min(1000, 780, 500) = 500
\]

**Lưu ý:** 20 MiB là ngân sách giả định cho phần dữ liệu paging, không phải khuyến nghị đặt heap của Spring Boot bằng 20 MiB.

### 5.1. So sánh page size trong cùng dataset

Với `N = 2.505` entry, số trang **lý thuyết tối thiểu** nếu server trả đủ `S` entry mỗi lượt:

| S (entry/trang) | Số trang xấp xỉ | Đặc điểm dự kiến |
| --- | --- | --- |
| 50 | 51 | Ít RAM mỗi trang, nhiều round-trip. |
| 100 | 26 | Phù hợp thử ban đầu ở mạng RTT thấp hoặc entry lớn. |
| 250 | 11 | Cân bằng tương đối cho bài lab. |
| 500 | 6 | Ít lượt gọi hơn, RAM mỗi trang lớn hơn. |
| 1.000 | 3 | Ít round-trip nhất trong bảng nhưng có thể gần server cap và tạo spike bộ nhớ. |

Con số trên là phép tính `ceil(N/S)` để ước tính. **Không phải hợp đồng rằng server luôn trả đúng số trang ấy**; một server có thể trả ít entry hơn page size hoặc cần bước kiểm tra kết thúc tùy response control. Không lấy “trang cuối có ít entry” thay cho tín hiệu cookie.

### 5.2. Không chọn S chỉ từ bộ nhớ

Dù tính toán cho phép `500`, vẫn phải chạy phép đo:

- `S = 500` có tạo lỗi timeout, `sizeLimitExceeded`, lỗi control hay giới hạn policy không?
- p95 thời gian nhận/xử lý một trang có vượt budget?
- GC pause và heap peak có tăng mạnh khi nhiều scan cùng chạy?
- Batch ghi database có xử lý kịp hay tạo backlog?
- Tổng thời gian quét và mức tiêu thụ LDAP connection có đáp ứng vận hành?

Nếu có lỗi, giảm S và kiểm tra nguyên nhân; nếu không có lỗi, thử tăng/giảm có kiểm soát và đo lại. **Một page size làm scan nhanh hơn trên laptop không đương nhiên tốt hơn khi có nhiều request HTTP ở production.**

## 6. Thiết kế thuật toán chọn page size

Page size ứng dụng nên bị chặn bởi các giới hạn có nguồn xác thực:

~~~text
                 Server policy / capability
                            |
                     cap phía server
                            |
 App page cap --+------------+------------+-- Heap/concurrency cap
                |                         |
                +----- lấy MIN ----------+
                            |
                    Page size khởi đầu
                            |
             Benchmark và điều chỉnh có kiểm soát
                            |
                 Page size được vận hành
~~~

Đây là chiến lược **chọn giá trị trước khi bắt đầu một chuỗi paging**. Để việc so sánh dữ liệu đáng tin cậy, hãy giữ page size cùng base/filter/scope ổn định trong một scan. Nếu muốn thay đổi S để benchmark, bắt đầu **scan mới**; không tự đổi tham số giữa một chuỗi cookie đang hoạt động và coi như kết quả có thể so sánh trực tiếp.

### 6.1. Một hàm Java chọn kích thước trang

Code dưới đây là **bộ tính toán hoạch định**, không tự dò policy của LDAP server và không tự đo heap:

~~~java
public final class PageSizePlanner {

    private PageSizePlanner() {}

    public record Constraints(
            int serverPageCap,
            int applicationPageCap,
            long pagingHeapBudgetBytes,
            long estimatedEntryBytes,
            int concurrentScans,
            double safetyFactor) {}

    public static int choose(Constraints c) {
        if (c == null
                || c.serverPageCap() < 1
                || c.applicationPageCap() < 1
                || c.pagingHeapBudgetBytes() < 1
                || c.estimatedEntryBytes() < 1
                || c.concurrentScans() < 1
                || !Double.isFinite(c.safetyFactor())
                || c.safetyFactor() < 1) {
            throw new IllegalArgumentException("Budget khong hop le");
        }

        double bytesPerPageEntryAcrossScans =
                (double) c.estimatedEntryBytes()
                * c.concurrentScans()
                * c.safetyFactor();
        double heapCap =
                Math.floor(c.pagingHeapBudgetBytes()
                        / bytesPerPageEntryAcrossScans);

        double selected = Math.min(
                Math.min(c.serverPageCap(), c.applicationPageCap()),
                heapCap);

        if (selected < 1) {
            throw new IllegalArgumentException(
                    "Khong du budget de xu ly mot entry");
        }
        return (int) selected;
    }
}
~~~

Ví dụ gọi:

~~~java
var budget = new PageSizePlanner.Constraints(
        1000,                 // server cap từ vận hành
        500,                  // application cap
        20L * 1024 * 1024,  // paging heap budget: 20 MiB
        3584,                 // 3,5 KiB/entry ước lượng
        3,                    // tối đa ba job đồng thời
        2.5                   // hệ số an toàn
);

int pageSize = PageSizePlanner.choose(budget);
System.out.println(pageSize);  // 500
~~~

**Đây là công cụ đưa ra giá trị khởi đầu, không phải “auto-tuner tối ưu”.** Bộ nhớ mỗi entry và số job đồng thời phải được đo hoặc ràng buộc từ hệ thống thật; nếu giá trị không chính xác, kết quả có thể quá lớn. Khi entry kích thước biến động mạnh, nên dùng percentile cao và tính thêm headroom.

### 6.2. Unit test cho giới hạn

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class PageSizePlannerTest {

    @Test
    void respectsAppCapWhenMemoryAndServerAllow() {
        var c = new PageSizePlanner.Constraints(
                1000, 500, 20L * 1024 * 1024,
                3584, 3, 2.5);
        assertEquals(500, PageSizePlanner.choose(c));
    }

    @Test
    void reducesSizeWhenMemoryIsSmall() {
        var c = new PageSizePlanner.Constraints(
                1000, 500, 30L * 1024,
                1024, 3, 1.0);
        assertEquals(10, PageSizePlanner.choose(c));
    }

    @Test
    void rejectsImpossibleBudget() {
        var c = new PageSizePlanner.Constraints(
                1000, 500, 100, 4096, 2, 2.0);
        assertThrows(IllegalArgumentException.class,
                () -> PageSizePlanner.choose(c));
    }
}
~~~

Các test xác nhận chính sách số học trong hàm chọn S, **không chứng minh directory chấp nhận S** hoặc paging control hoạt động. Điều đó cần integration test.

## 7. Đưa page size thành cấu hình có kiểm soát

Với Spring Boot, có thể đặt:

~~~yaml
spring:
  ldap:
    urls: ${LDAP_URL:ldaps://ldap.example.org:636}
    base: ${LDAP_BASE_DN:dc=example,dc=org}
    username: ${LDAP_BIND_DN}
    password: ${LDAP_BIND_PASSWORD}
    base-environment:
      com.sun.jndi.ldap.connect.timeout: "3000"
      com.sun.jndi.ldap.read.timeout: "7000"

directory:
  paging:
    page-size: 250
    max-pages: 1000
~~~

Các thông số `directory.paging.*` là **thuộc tính tùy biến của ứng dụng**, không phải thuộc tính mặc định của Spring Data LDAP. Cần code đọc/validate chúng, không mặc định Spring Boot tự lấy `directory.paging.page-size` rồi đưa vào paged control.

Ví dụ component cấu hình:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class DirectoryPagingSettings {
    private final int pageSize;
    private final int maxPages;

    public DirectoryPagingSettings(
            @Value("${directory.paging.page-size:250}") int pageSize,
            @Value("${directory.paging.max-pages:1000}") int maxPages) {
        if (pageSize < 1 || pageSize > 500) {
            throw new IllegalArgumentException(
                    "page-size phai nam trong khoang 1..500");
        }
        if (maxPages < 1 || maxPages > 10000) {
            throw new IllegalArgumentException(
                    "max-pages phai nam trong khoang 1..10000");
        }
        this.pageSize = pageSize;
        this.maxPages = maxPages;
    }

    public int pageSize() { return pageSize; }
    public int maxPages() { return maxPages; }
}
~~~

Giới hạn `500` được chọn cho **môi trường ví dụ** theo `application cap`, không phải thông số chung của Spring LDAP. Nếu server policy thay đổi, cập nhật cấu hình và benchmark; không tăng giới hạn bằng một HTTP query parameter chưa phân quyền.

### 7.1. Dùng page size với Spring LDAP

Trên Spring LDAP 4.1+ có thể dùng `PagedResultsControlExchangeDirContextProcessor` và `SingleContextSource`. API cũ hơn dùng `PagedResultsDirContextProcessor` với cơ chế cookie tương ứng; **chọn theo version thực tế**.

~~~java
import java.util.List;
import javax.naming.directory.SearchControls;
import org.springframework.ldap.control.PagedResultsControlExchangeDirContextProcessor;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.ContextSource;
import org.springframework.ldap.core.support.SingleContextSource;
import org.springframework.stereotype.Service;

@Service
public class BoundedDirectoryScanner {
    private final ContextSource contextSource;
    private final DirectoryPagingSettings settings;

    public BoundedDirectoryScanner(
            ContextSource contextSource,
            DirectoryPagingSettings settings) {
        this.contextSource = contextSource;
        this.settings = settings;
    }

    public record PersonRow(String uid, String displayName) {}
    public record ScanStats(long entries, int pages) {}

    public ScanStats scan() {
        SearchControls controls = new SearchControls();
        controls.setSearchScope(SearchControls.SUBTREE_SCOPE);
        controls.setReturningAttributes(
                new String[]{"uid", "cn"});
        controls.setTimeLimit(5000);

        AttributesMapper<PersonRow> mapper = attrs ->
                new PersonRow(
                        attrs.get("uid").get().toString(),
                        attrs.get("cn").get().toString());

        var pager = new PagedResultsControlExchangeDirContextProcessor(
                settings.pageSize());

        return SingleContextSource.doWithSingleContext(
                contextSource,
                ops -> {
                    long entries = 0;
                    int pages = 0;
                    do {
                        if (pages >= settings.maxPages()) {
                            throw new IllegalStateException(
                                    "Scan vuot max-pages, KHONG hoan tat");
                        }

                        List<PersonRow> page = ops.search(
                                "ou=people",
                                "(&(objectClass=inetOrgPerson)(uid=*))",
                                controls,
                                mapper,
                                pager);
                        pages++;

                        // Minh họa: xử lý tại đây rồi giải phóng từng page.
                        // Production: chuyển từng trang sang consumer/batch idempotent.
                        entries += page.size();
                    } while (pager.hasMore());

                    return new ScanStats(entries, pages);
                },
                true, false, false
        );
    }
}
~~~

**Phạm vi ví dụ:** chương trình này đếm các entry có `uid`/`cn` dưới `ou=people` và giả định dữ liệu hợp lệ. Nếu entry thiếu attribute do schema/ACL, mapper sẽ lỗi; trong ứng dụng thật cần hợp đồng trường bắt buộc/tùy chọn, DTO, xử lý exception và quy trình đối soát đầy đủ. Đoạn code minh họa **page size có giới hạn và vòng đời connection**, không phải toàn bộ quy trình đồng bộ production.

Phân tích:

1. `settings.pageSize()` được validate trước khi tạo processor. Không nhận `pageSize=1000000` trực tiếp từ client HTTP.
2. `SearchControls` giới hạn scope/attributes/time limit. **Page size không thay thế các giới hạn này.**
3. `SingleContextSource.doWithSingleContext` giúp các lượt search chia sẻ cùng underlying LDAP connection; cookie không được mang tùy ý sang context/server khác.
4. Một processor duy trì trạng thái paging xuyên suốt vòng lặp; kết thúc theo `pager.hasMore()`, không theo `page.size()`.
5. Đạt `maxPages` khi còn cookie là **scan bị chặn**, phải báo lỗi; không âm thầm trả một con số thiếu và gọi là thành công.
6. Nếu cần thực hiện xử lý nghiệp vụ trên từng entry, đặt consumer/batch rõ ràng và kiểm soát bộ nhớ. **Không tích lũy tất cả các trang vào một `List`** chỉ để sau đó trả HTTP.

## 8. Chọn page size theo số đo thực tế

**Một phép đo tốt phải dùng cùng dữ liệu, cùng account, cùng filter/base/scope và môi trường so sánh được.** Thực hiện phép thử trên directory test hoặc cửa sổ hiệu năng được quản trị viên cho phép, tránh tạo tải bất ngờ lên production.

### 8.1. Kế hoạch benchmark

Giả sử application cap là 500; những giá trị cần thử là:

~~~text
S = 50, 100, 250, 500
~~~

Không thử `S=1000` chỉ vì server hỗ trợ nếu ngân sách heap và application cap đang là 500. Với mỗi S:

1. Xác nhận account bind và LDAP control hoạt động bằng `ldapsearch -E pr=...`.
2. Dùng cùng dataset và **projection nhỏ** (`uid`, `cn`, thêm stable ID nếu cần).
3. Chạy một hoặc nhiều lượt warm-up trước khi đo, nếu không ảnh hưởng test data.
4. Chạy nhiều lần có kiểm soát, ghi `p50/p95` thời gian mỗi trang, **thời gian quét toàn bộ**, số page, tổng entry và số lỗi.
5. Ghi heap peak, GC pause, CPU, network bytes, server load và số LDAP connections đồng thời.
6. Thử `C=1` rồi `C=2/3` nếu chính sách hạ tầng cho phép; kiểm tra cạnh tranh với HTTP traffic.
7. Đối chiếu tổng entry và stable ID; không công nhận phép đo nếu scan chưa hoàn tất đúng.
8. Giảm S nếu có timeout/GC spike/quá tải hoặc tăng thử nếu RTT chiếm phần lớn và hệ thống còn headroom.

**Đừng chỉ so thời gian một trang.** Với S nhỏ, trang có thể nhanh nhưng tổng số trang lớn; với S lớn, một trang có thể chậm hơn nhưng tổng scan lại nhanh. Mục tiêu đúng là tổng throughput **trong mức dùng tài nguyên và SLO chấp nhận được**.

### 8.2. Những metric nên đo

| Metric | Giải thích | Điều cần quan sát |
| --- | --- | --- |
| `ldap_page_request_count` | Số search request của một scan. | S giảm thường làm số request tăng. |
| `ldap_page_duration_p95` | p95 thời gian search + nhận/mapping một trang. | Có spike khi S lớn hay server bận không? |
| `ldap_scan_duration` | Tổng thời gian quét hoàn chỉnh. | Có cải thiện khi tăng S không? |
| `ldap_scan_entries_total` | Tổng entry xử lý. | Có bị thiếu, trùng bất thường hay giới hạn? |
| `ldap_scan_failed_total` | Số scan không hoàn tất. | Phân loại timeout, ACL, control, downstream. |
| `paging_heap_peak_bytes` | Bộ nhớ tăng thêm trong scan. | Có vượt ngân sách hoặc kéo dài GC không? |
| `jvm_gc_pause` | Pause do GC. | S lớn có làm p95 hoặc tail latency xấu đi? |
| `ldap_active_contexts` | Context/connection đang hoạt động. | Scan có chiếm hết connection phục vụ HTTP không? |
| `downstream_batch_latency` | Thời gian xử lý batch sau đọc. | DB có phải bottleneck thay vì LDAP không? |

Các metric có thể được triển khai qua Micrometer/JVM metrics và instrument service. Không gắn UID, DN hoặc email làm metric label vì cardinality cao và rò rỉ thông tin cá nhân. Ghi hostname/endpoint ở mức phù hợp với chính sách log và giảm dữ liệu nhạy cảm.

### 8.3. Bảng ví dụ để diễn giải số đo

Giả sử một lần thử có các kết quả **giả lập**:

| Page size | Số trang | Scan duration | Heap tăng tối đa | p95/page | Đánh giá |
| --- | --- | --- | --- | --- | --- |
| 50 | 51 | 18,4 s | 3 MiB | 0,55 s | Đủ dữ liệu, nhưng nhiều round-trip. |
| 100 | 26 | 11,8 s | 4 MiB | 0,62 s | Cân bằng, ít tải bộ nhớ. |
| 250 | 11 | 8,7 s | 8 MiB | 1,15 s | Nhanh hơn, còn headroom. |
| 500 | 6 | 8,1 s | 15 MiB | 2,40 s | Tổng nhanh hơn ít, p95 tăng; sát budget nếu chạy đồng thời. |

**Đây là bảng số liệu minh họa, không phải kết quả benchmark đã thực hiện.** Nếu S=500 chỉ nhanh hơn 0,6 giây nhưng ảnh hưởng p95/heap lớn trong giờ cao điểm, S=250 có thể là lựa chọn tốt hơn cho hệ thống. Nếu job chạy ban đêm một mình và headroom đủ, S=500 có thể hợp lý. **Quyết định phải dựa trên SLO của môi trường thật.**

## 9. Những quy tắc điều chỉnh page size thực tế

### 9.1. Nếu mạng có RTT cao

Trang quá nhỏ tạo nhiều round-trip. Ví dụ directory ở trung tâm dữ liệu khác vùng, RTT cao hơn bình thường. Tăng S **trong giới hạn server/heap** có thể giảm phần chi phí cố định trên mỗi request.

Trước khi tăng, kiểm tra kết nối TLS và proxy, timeout JNDI, chính sách directory; page size không giải quyết một kết nối không ổn định.

### 9.2. Nếu entry lớn hoặc có thuộc tính nhị phân

Giảm S, thu hẹp returning attributes và cân nhắc tách query chuyên biệt để lấy ảnh/chứng chỉ theo nhu cầu. Tăng page size trong khi projection mang ảnh lớn có thể gây RAM spike và GC pause.

### 9.3. Nếu nhiều job quét song song

Tổng bộ nhớ tăng theo `C`. Khi tăng concurrency, page size tối đa an toàn thường phải giảm hoặc cần tăng ngân sách paging. Không coi việc mỗi worker riêng lẻ qua test là bằng chứng ba worker cùng chạy sẽ qua.

### 9.4. Nếu database downstream xử lý chậm

Đừng chỉ tăng S. Hãy thiết kế **bounded batch queue/backpressure**, số worker và batch size ghi database. Nếu producer đọc LDAP nhanh hơn consumer ghi DB, mọi page size vẫn có thể làm queue phình to khi không giới hạn. Có thể xử lý/commit một trang trước khi yêu cầu trang kế tiếp hoặc dùng queue bounded và rate limit rõ ràng.

### 9.5. Nếu server áp giới hạn thấp hơn dự kiến

Đừng tăng `countLimit` hoặc bỏ paged control để “vượt hạn mức”. Kiểm tra policy với quản trị viên, giảm S nếu phù hợp và xem lại filter/index. Nếu server không hỗ trợ RFC 2696, dùng phương án đồng bộ/phân vùng truy vấn được thiết kế riêng; không tự ghép nhiều query rời rạc rồi giả định có snapshot.

### 9.6. Nếu cần nhiều attribute hơn theo thời gian

Khi thêm `memberOf`, `thumbnailPhoto` hoặc metadata khác vào projection, kích thước entry thay đổi; **benchmark page size cũ không còn đủ cơ sở**. Phải đo lại heap và latency. Tương tự, thay đổi schema, ACL, index hoặc directory provider có thể làm hiệu năng khác đáng kể.

## 10. Các tình huống cần từ chối hoặc đánh dấu scan thất bại

| Tình huống | Vì sao không được coi là hoàn tất? | Xử lý đúng |
| --- | --- | --- |
| Không có RFC 2696 support. | Một search thường có thể bị size limit. | Báo thiếu capability; không tự fallback thành dữ liệu đầy đủ. |
| Page size vượt policy server. | Server có thể từ chối/giảm số entry/trả lỗi. | Đọc thông báo, hạ S theo policy và thử lại từ đầu. |
| `pager.hasMore()` vẫn true khi đạt `maxPages`. | Còn trang chưa đọc. | Đánh dấu FAILED/PARTIAL, không báo thành công. |
| Lỗi mạng/timeout ở trang n. | Không biết còn bao nhiêu entry. | Kết thúc job lỗi, khởi tạo scan mới nếu cần. |
| Tự chuyển sang server B giữa chuỗi. | Cookie có thể gắn với server A/connection. | Không tái sử dụng cookie A tùy tiện. |
| Hết bộ nhớ do page quá lớn. | Kết quả không hoàn chỉnh và ảnh hưởng process. | Giảm S/projection/concurrency, tăng giám sát. |
| Consumer/DB ghi batch thất bại. | Một phần entry đã xử lý, phần sau chưa xử lý. | Idempotent upsert, checkpoint nghiệp vụ và đối soát. |
| Bỏ qua `PartialResultException`/referral. | Có thể thiếu vùng dữ liệu. | Chính sách referral rõ, không âm thầm công nhận full scan. |

**Cookie không phải checkpoint lâu dài.** Không lưu cookie vào database rồi đợi một ngày sau hoặc đổi endpoint LDAP và giả định có thể tiếp tục. Nếu cần resume sau crash, phải thiết kế đồng bộ dựa trên stable ID, trạng thái job và cơ chế incremental của provider (nếu có), không dựa vào token của một kết nối đã kết thúc.

## 11. Phân trang và tính nhất quán dữ liệu

Ngay cả khi page size đã tối ưu, Simple Paged Results **không cung cấp snapshot toàn directory**. Giữa hai trang, entry có thể được thêm, xóa, đổi DN/RDN hoặc thay đổi thuộc tính; một replica có thể chưa đồng bộ. Các lần search của một scan không nhất thiết đại diện cho trạng thái ở cùng một thời điểm.

~~~text
T0: Bắt đầu scan (cookie ban đầu rỗng)
T1: Trang 1 trả uid=lan, uid=minh
T2: Admin chuyển uid=an từ ou=archive sang ou=people
T3: Các trang sau được đọc
T4: Hết cookie
~~~

**Không suy ra** kết quả đúng với toàn bộ dữ liệu tại T0 hay T4. Trong đồng bộ hệ thống:

- Sử dụng stable ID theo provider (`entryUUID`, `objectGUID` với codec đúng, hoặc định danh đáng tin cậy khác), không dùng username/email/DN là khóa bất biến mặc định.
- Dùng unique constraint theo `(provider_key, external_id)` và upsert idempotent.
- Lưu `last_seen_run_id` và chỉ đối soát entry vắng sau khi **full scan đã hoàn tất không lỗi** và chính sách nhất quán cho phép.
- Không hard-delete account nghiệp vụ chỉ vì một lần scan thiếu entry.
- Nếu cần theo dõi thay đổi liên tục, xem xét cơ chế change log, DirSync hoặc đồng bộ theo provider, thay vì xem paging là change data capture.

Page size lớn hay nhỏ không xóa bỏ giới hạn nhất quán này. Đó là vấn đề ngữ nghĩa dữ liệu, không phải bài toán hiệu năng thuần túy.

## 12. Bảo mật và quản trị tài nguyên

### 12.1. Quyền LDAP và phân quyền ứng dụng

Spring Data LDAP repository/`LdapTemplate` thông thường truy cập bằng **bind account** của `ContextSource`. Một HTTP user được xác thực không tự động được quyền quét directory chỉ vì tài khoản dịch vụ có ACL đọc.

Hãy áp dụng:

1. **Spring Security/service authorization** cho chức năng kích hoạt full scan, tách khỏi API xem hồ sơ một người.
2. **LDAP ACL tối thiểu** theo OU và attribute cần đọc; scan không cần quyền ghi.
3. **LDAPS/StartTLS**, xác minh CA và hostname; giữ secret trong hệ thống quản lý bí mật, không log mật khẩu.
4. **Base/filter/scope cố định hoặc allowlist**, không nhận raw DN và attribute từ HTTP client.
5. **Giới hạn page size, max pages, concurrency, deadline và rate limit** cho mỗi loại job.
6. **Logging an toàn**: số page, duration, lỗi và thông số hệ thống, tránh PII và raw cookie.

### 12.2. Query builder không tự giới hạn quyền

`LdapQueryBuilder.where("uid").is(input)` giúp escape giá trị filter, nhưng không có nghĩa caller được phép tự chọn `objectClass`, search base hoặc `SUBTREE` từ root. Tương tự, một page size nhỏ không bảo đảm một truy vấn qua toàn bộ directory là được phép.

Đối với scan toàn bộ OU, dùng tài khoản, audit, quota và khung giờ được quản trị viên phê duyệt. Nếu nhiều dịch vụ cùng quét LDAP, nên phối hợp lịch để tránh dồn tải lên directory controller.

## 13. Ma trận kiểm thử quyết định page size

| Trường hợp | Thao tác test | Kỳ vọng |
| --- | --- | --- |
| Server policy cap=500, config đề nghị 1.000. | Chạy validation của ứng dụng. | Chặn hoặc giảm S theo giới hạn được duyệt; không gửi request quá cap một cách vô ý. |
| Heap budget nhỏ. | Chạy `PageSizePlanner` với per-entry lớn. | S giảm tương ứng; không trả 0 hoặc âm. |
| S=50, 100, 250, 500. | Benchmark cùng OU/filter/account. | Có dữ liệu tổng scan, p95/page, heap, lỗi để so sánh. |
| N=2.505 entry test. | Chạy paged search và đếm theo stable ID. | Đủ 2.505 nếu dataset cố định; không suy hoàn tất từ số trang lý thuyết. |
| Server trả ít entry hơn yêu cầu nhưng còn cookie. | Giả lập/kiểm thử server hỗ trợ. | Tiếp tục theo `hasMore()`, không break vì size trang nhỏ. |
| N là bội số page size. | Dataset 500 entry, S=250. | Xử lý đúng cookie kết thúc, kể cả server có phản hồi đặc biệt ở cuối. |
| S=500 với 3 job đồng thời. | Stress test theo budget. | Không vượt heap/connection SLA, không làm xấu latency HTTP. |
| Đọc ảnh/chứng chỉ ngoài nhu cầu. | Thêm field nhị phân lớn vào projection trong test. | Thấy ảnh hưởng heap/latency, thiết kế lại projection hoặc S. |
| Lỗi ở trang cuối. | Mô phỏng timeout/DB failure. | Scan FAILED; không dùng dữ liệu partial để xóa account. |
| Server A mất giữa scan. | Kiểm thử failover trong directory test. | Không coi cookie trên A tự hợp lệ ở B. |
| User HTTP xin page size 100.000. | Gọi endpoint nếu có. | Không được dùng giá trị tùy ý; policy ứng dụng phải chặn. |
| Entry bị rename trong scan. | Test đổi DN. | Không suy snapshot; đối soát theo stable ID. |

### 13.1. Chia kiểm thử theo lớp

**Unit test** dùng để kiểm tra toán học và validation của `PageSizePlanner`/`DirectoryPagingSettings`, mapper xử lý attribute thiếu, xử lý `maxPages` và consumer idempotency.

**Integration test** mới xác minh được:

- Server hỗ trợ OID RFC 2696 và trả response controls đúng.
- Paging processor sử dụng cookie trên cùng connection.
- Kích thước trang server thực trả và giới hạn policy.
- Tổng entry đầy đủ khi dataset cố định.
- TLS, bind, ACL, referrals, timeout và hành vi khi backend chuyển đổi.

**Load test có kiểm soát** cần thêm số liệu heap/GC, throughput, p95, áp lực connection pool và tải directory. Đừng chỉ chạy một unit test trả danh sách giả rồi tuyên bố page size 500 đã tối ưu.

## 14. Bài tập thực hành

Một đội phát triển xây job đồng bộ danh bạ 80.000 người dùng từ LDAP sang database ứng dụng. Mỗi entry trả `uid`, `cn`, `mail` và stable ID. Quản trị viên cho biết server thử nghiệm đang áp `page cap=1.000`; nhóm chỉ muốn dành 24 MiB heap cho dữ liệu paging, có thể chạy tối đa hai job đồng thời. Sau đo đạc sơ bộ, mỗi entry cần trung bình 4 KiB trong bộ nhớ và nhóm dùng hệ số an toàn 2,5. Cấu hình ứng dụng giới hạn page size tối đa 500.

**Yêu cầu:**

1. Tính page cap theo bộ nhớ và page size hợp lệ từ ba giới hạn: server, heap và application.
2. Ước lượng số trang cho `S=100`, `S=250` và `S=500` với 80.000 entry. Vì sao số thực tế có thể khác?
3. Nếu RTT tăng gấp ba trong khi heap vẫn dư, thử điều chỉnh S theo hướng nào? Cần đo metric gì trước khi quyết định?
4. Nếu thêm `thumbnailPhoto` làm entry lớn gấp 10 lần, có nên giữ S cũ không? Nên sửa projection hay tăng heap thế nào?
5. Vì sao tăng số job đồng thời từ hai lên bốn có thể buộc hạ S?
6. Nếu server trả một trang chỉ 170 entry với `S=250` nhưng cookie vẫn còn, vòng lặp phải làm gì?
7. Nếu vòng lặp đến `maxPages` mà cookie vẫn còn, job nên trả `COMPLETED` hay `FAILED/PARTIAL`?
8. Nếu backend LDAP đổi sau trang thứ tư, có được dùng lại cookie cũ trên server mới không?
9. Nếu job đang dùng để phát hiện tài khoản đã nghỉ việc, tại sao không nên xóa user khỏi database sau một lần scan thất bại?
10. Hãy đề xuất bảng đo gồm `page size`, `duration`, `p95 per page`, `heap peak`, `GC pause`, `entries processed`, `completed` và `server errors` để chọn S.

**Gợi ý đáp án:**

- Ngân sách bộ nhớ: `24 MiB / (2 × 4 KiB × 2,5) ≈ 1.228 entry/trang`. Chọn `min(1.000, 1.228, 500) = 500` làm giới hạn khởi đầu, rồi benchmark.
- Với `N=80.000`, số trang lý thuyết lần lượt `800`, `320`, `160`; server có thể trả khác kích thước đề nghị, cần dựa vào cookie.
- RTT cao thường làm việc tăng page size hấp dẫn hơn vì giảm round-trip, nhưng phải giữ p95, memory, ACL và server policy trong giới hạn.
- Entry lớn gấp 10 làm mô hình heap cap giảm mạnh; ưu tiên bỏ ảnh khỏi projection nếu không cần, đo lại và giảm S phù hợp.
- C tăng làm số page cùng thường trú trong heap tăng; tăng concurrency mà giữ S có thể vượt ngân sách.
- Trang 170 vẫn phải tiếp tục nếu `hasMore()` true. Hết `maxPages` mà còn cookie là **FAILED/PARTIAL**, không hoàn tất.
- Cookie không phải bookmark bền vững hoặc dùng chung giữa LDAP servers; lỗi giữa scan cần đối soát hoặc scan lại theo policy.
- Chỉ đánh dấu vắng/xóa khi scan hoàn tất đáng tin cậy và đã áp quy trình kiểm tra; dữ liệu partial không chứng minh account không còn.

## 15. Ghi nhớ

**Chọn page size là bài toán cân bằng giữa giới hạn LDAP server và tài nguyên ứng dụng.** Page size nhỏ tiết kiệm bộ nhớ mỗi trang nhưng tăng số round-trip; page size lớn giảm số request nhưng có thể tăng heap, GC, p95 và rủi ro vượt policy server. Hãy xác minh RFC 2696, chọn **giá trị nhỏ nhất giữa server cap, heap/concurrency cap và application cap**, rồi đo lường trên đúng dataset và hạ tầng.

Khi triển khai với Spring LDAP, dùng paging control và cookie trên **cùng connection**, giữ base/filter/scope cố định, chỉ đọc projection cần thiết và giới hạn max pages/deadline. **Kích thước trang không làm kết quả trở thành snapshot nhất quán, không thay thế ACL/authorization và không bảo đảm khôi phục sau crash.** Một quyết định page size tốt luôn đi kèm đo throughput, memory, completion và lỗi, không chỉ dựa trên con số số trang.

### Tài liệu tham khảo

- [RFC 2696 — LDAP Control Extension for Simple Paged Results Manipulation](https://www.rfc-editor.org/rfc/rfc2696)
- [RFC 4511 — LDAPv3 Search Operation](https://www.rfc-editor.org/rfc/rfc4511)
- [Spring LDAP Reference — Processing the DirContext](https://docs.spring.io/spring-ldap/reference/processing-the-dircontext.html)
- [Spring LDAP Reference — Basic Usage](https://docs.spring.io/spring-ldap/reference/basic.html)
- [Spring LDAP API — SingleContextSource](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/core/support/SingleContextSource.html)
- [Spring LDAP API — PagedResultsControlExchangeDirContextProcessor](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/control/PagedResultsControlExchangeDirContextProcessor.html)
- [Spring Data LDAP Reference](https://docs.spring.io/spring-data/ldap/reference/)
- [Microsoft Learn — LDAP Query Policies](https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-adts/3f0137a1-63df-400c-bf97-e1040f055a99)
