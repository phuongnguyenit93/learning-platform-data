# Không dùng offset kiểu SQL cho LDAP subtree

Trong cơ sở dữ liệu quan hệ, lập trình viên thường phân trang bằng **LIMIT** và **OFFSET**: lấy 50 dòng, bỏ qua 100 dòng đầu, rồi trả “trang 3”. Khi chuyển sang **Spring LDAP**, cách nghĩ này dễ dẫn đến lỗi: LDAP Search không có toán tử SQL **OFFSET**, thứ tự kết quả không mặc nhiên ổn định và việc tìm kiếm cả một **subtree** có thể đi qua nhiều nhánh với số lượng entry lớn.

Với LDAP, cách tiếp cận phổ biến là **Simple Paged Results Control** theo **RFC 2696**: ứng dụng yêu cầu một số entry cho lần search, nhận **cookie** do server cấp, rồi gửi lại cookie để lấy phần tiếp theo. Nếu cần thứ tự xác định, ứng dụng kết hợp thêm **Server-side Sort Control** khi server hỗ trợ. Điều quan trọng là phân biệt **phân trang tuần tự bằng cookie** với yêu cầu **nhảy trực tiếp đến trang N**.

Bài này thuộc chương **Phân trang và sorting** của module **SPRING_LDAP**. Các ví dụ dùng **LdapTemplate**, **ContextSource**, **SearchControls** và LDAP controls để trình bày cơ chế, lỗi thường gặp và phương án thiết kế API có thể triển khai an toàn.

## 1. Vì sao không thể lấy tư duy OFFSET của SQL áp vào LDAP?

Một câu SQL quen thuộc:

~~~sql
SELECT uid, cn
FROM people
ORDER BY cn, uid
LIMIT 50 OFFSET 100;
~~~

Trong LDAP, ứng dụng mô tả **base DN**, **scope**, **filter** và các thuộc tính cần trả về, chẳng hạn:

~~~text
Base DN:   ou=people,dc=example,dc=org
Scope:     SUBTREE
Filter:    (&(objectClass=inetOrgPerson)(uid=*))
Attrs:     uid, cn
~~~

Yêu cầu trên có nghĩa là tìm các entry phù hợp **bên trong nhánh** người dùng. Nó không có thành phần tương đương **OFFSET 100** trong thao tác LDAP Search chuẩn. Nếu chỉ gọi **LdapTemplate.search(...)** rồi bỏ qua 100 entry ở Java, ứng dụng phải **nhận và xử lý** ít nhất các entry bị bỏ qua, có thể vượt giới hạn truy vấn và không bảo đảm thứ tự nếu chưa yêu cầu sort phía server.

| SQL | LDAP Search |
| --- | --- |
| **FROM people** chọn bảng | **base DN + search scope** xác định vùng tìm kiếm trong cây thư mục. |
| **WHERE** | **LDAP filter**; cú pháp và matching rule khác SQL. |
| **ORDER BY** | Cần **Server-side Sort Control** nếu muốn server áp dụng thứ tự được xác nhận. |
| **LIMIT 50** | **Paged Results Control** yêu cầu page size 50; **SearchControls.setCountLimit(50)** là giới hạn kết quả, không phải cursor phân trang. |
| **OFFSET 100** | **Không có toán tử tương đương** trong LDAP Search thông thường. Phân trang tuần tự sử dụng cookie. |
| **COUNT(*)** | Paged Results response có thể chứa **ước lượng** số entry hoặc **0** nếu không biết; không mặc nhiên là COUNT chính xác. |

Ví dụ nguy hiểm:

~~~text
Truy vấn LDAP ban đầu trả về (không có sort):
  [U8, U2, U5, U1, U7, U3, U4, U6]

Client tự bỏ 3 entry đầu, lấy 3 entry tiếp:
  [U1, U7, U3]

Lần tìm kiếm mới có thể trả thứ tự khác:
  [U3, U7, U1, U5, U8, U4, U2, U6]

Client bỏ 6 entry đầu để lấy "trang 3":
  [U2, U6]
~~~

Hai lần query độc lập không đảm bảo một chuỗi trang liên tục. Ngay cả khi thêm sort, mô phỏng offset bằng cách liên tục lấy và bỏ các trang trước vẫn tiêu tốn tài nguyên tỷ lệ với số entry phải duyệt và chịu ảnh hưởng của dữ liệu thay đổi.

## 2. Subtree search làm vấn đề rõ hơn

Trong LDAP, một **DN** mô tả vị trí của entry trong cây. Với:

~~~text
dc=example,dc=org
└── ou=people
    ├── ou=engineering
    │   ├── uid=an
    │   └── uid=binh
    └── ou=sales
        ├── uid=chi
        └── uid=dung
~~~

Ba scope của **SearchControls** có ý nghĩa khác nhau:

| Scope | Khu vực tìm kiếm | Ví dụ khi base = **ou=people** |
| --- | --- | --- |
| **OBJECT_SCOPE** | Chỉ entry tại base DN. | Chính entry **ou=people**. |
| **ONELEVEL_SCOPE** | Các entry con trực tiếp của base. | **ou=engineering**, **ou=sales**. |
| **SUBTREE_SCOPE** | Base và mọi entry bên dưới, ở mọi độ sâu. | Bao gồm cả các OU và người dùng bên dưới chúng. |

Khi người dùng nằm trong nhiều OU, **ONELEVEL_SCOPE** ở **ou=people** có thể không tìm thấy họ; **SUBTREE_SCOPE** mở rộng đúng phạm vi nhưng cũng có thể chạm hàng chục nghìn entry. Không được coi **số trang × kích thước trang** là một “vị trí” có thể tìm thẳng trong cây LDAP, bởi thứ tự duyệt nội bộ, filter, ACL và chỉ mục phụ thuộc server.

Hãy **giới hạn base DN và filter trước khi phân trang**. Nếu màn hình chỉ hiển thị nhân viên thuộc **ou=engineering**, tìm ngay trong nhánh đó thường hợp lý hơn việc tìm toàn bộ **ou=people** rồi lọc ở Java.

## 3. RFC 2696: phân trang tuần tự bằng opaque cookie

**Simple Paged Results Control** (OID **1.2.840.113556.1.4.319**) cho phép client yêu cầu số entry mỗi trang và nhận **cookie** cho lần tiếp theo. Cookie là **giá trị opaque** do server quyết định; client không được phân tích hoặc tự tính toán nó.

~~~mermaid
sequenceDiagram
    participant C as Spring LDAP client
    participant L as LDAP server
    C->>L: Search + PagedResults(size=3, cookie=rỗng)
    L-->>C: [A, B, C] + cookie_1
    C->>L: Cùng search + PagedResults(size=3, cookie_1)
    L-->>C: [D, E, F] + cookie_2
    C->>L: Cùng search + PagedResults(size=3, cookie_2)
    L-->>C: [G] + cookie=rỗng
    Note over C,L: Cookie rỗng ở response: hết dữ liệu
~~~

Một lần yêu cầu page có các thành phần:

- **page size:** số entry mong muốn trong một phản hồi, ví dụ 50.
- **cookie gửi đi:** rỗng cho trang đầu; ở trang tiếp theo dùng chính cookie mới nhất server trả về.
- **response cookie:** khác rỗng khi server còn phần kết quả để trả; rỗng khi kết thúc.
- **size estimate:** tùy server, có thể là ước lượng tổng entry hoặc bằng **0** khi không xác định; **không dùng như tổng chính xác mặc định**.

Trong suốt chuỗi lấy trang, giữ nguyên các thông số của truy vấn như **base DN, scope, filter, các controls/sort keys**; theo RFC 2696, chỉ message ID, cookie và có thể page size được thay đổi giữa các request thuộc cùng chuỗi. Không dùng cookie từ truy vấn **ou=people** cho truy vấn **ou=groups**, cũng không tái sử dụng cookie của chuỗi đã kết thúc.

### Cookie không phải số trang

Không thể áp dụng:

~~~text
cookie = pageNumber * pageSize        // SAI
cookie = base64("offset=100")          // SAI
~~~

Cookie có thể chứa trạng thái server không công khai. Việc phát lại cookie cũ, gửi cookie sau khi chuỗi đã kết thúc hoặc mang cookie sang truy vấn khác có hành vi **không được bảo đảm**. Khi cần lấy “trang 5”, client thường phải **đi tuần tự qua các trang 1–4** hoặc dùng một tính năng truy cập theo vị trí khác mà server hỗ trợ, không thể tự suy ra cookie của trang 5.

### Cùng kết nối LDAP

Nhiều LDAP server/provider ràng buộc cookie với **cùng kết nối** và trạng thái tìm kiếm. Với Spring LDAP, mỗi lệnh **LdapTemplate** thường mượn/đóng context sau khi hoàn thành; vì vậy chuỗi paged requests cần giữ cùng context/kết nối bằng cơ chế phù hợp như **SingleContextSource**. Tài liệu Spring LDAP lưu ý yêu cầu này ngay trong ví dụ paged results.

**Không nhầm kết nối LDAP với phiên HTTP:** một cookie LDAP chuyển về trình duyệt hôm nay rồi gửi lại cho một instance backend khác ở request HTTP tiếp theo có thể **không hợp lệ**, kể cả nội dung cookie còn nguyên. Load balancer, connection pool, failover và restart làm vấn đề rõ hơn. Nếu cần “next page” qua nhiều HTTP request, ứng dụng phải thiết kế quản lý cursor/session phía server (có giới hạn thời gian, tài nguyên và quyền), hoặc một phương án phân trang khác có thể tái tạo kết quả. Tránh công bố rằng cookie LDAP là cursor HTTP có thể dùng tùy ý.

## 4. Ví dụ Spring LDAP 4.1+: đọc tuần tự các trang

Trong Spring LDAP **4.1+**, API khuyến nghị là **PagedResultsControlExchangeDirContextProcessor**. Ví dụ sau dùng Java 17+, bean **ContextSource** cấu hình base DN **dc=example,dc=org** và user kết nối có quyền đọc **ou=people**. Kết quả được gom về một danh sách chỉ để minh họa **batch duyệt tuần tự có giới hạn**; UI nên thiết kế giao thức trả trang phù hợp thay vì giữ toàn bộ entry trong RAM.

~~~java
import java.util.ArrayList;
import java.util.List;
import javax.naming.NamingException;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;
import javax.naming.directory.SearchControls;

import org.springframework.ldap.control.PagedResultsControlExchangeDirContextProcessor;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.ContextSource;
import org.springframework.ldap.core.LdapOperations;
import org.springframework.ldap.core.support.SingleContextSource;
import org.springframework.stereotype.Service;

@Service
public class PersonSubtreePager {
    private static final int MAX_PAGE_SIZE = 200;
    private static final int MAX_ENTRIES = 1000;
    private static final int MAX_REQUESTS = 20;

    private final ContextSource contextSource;

    public PersonSubtreePager(ContextSource contextSource) {
        this.contextSource = contextSource;
    }

    public record Person(String uid, String cn) { }

    public List<Person> loadBoundedSubtree(int pageSize) {
        if (pageSize < 1 || pageSize > MAX_PAGE_SIZE) {
            throw new IllegalArgumentException("pageSize không hợp lệ");
        }

        SearchControls search = new SearchControls();
        search.setSearchScope(SearchControls.SUBTREE_SCOPE);
        search.setReturningAttributes(new String[] { "uid", "cn" });
        search.setTimeLimit(5000); // ms cho mỗi LDAP search.

        var pager = new PagedResultsControlExchangeDirContextProcessor(
                pageSize);

        // Các lần search trong callback dùng cùng LDAP context.
        return SingleContextSource.doWithSingleContext(
                contextSource, (LdapOperations ldap) -> {
                    List<Person> all = new ArrayList<>();
                    int requestCount = 0;

                    do {
                        if (++requestCount > MAX_REQUESTS) {
                            throw new IllegalStateException(
                                    "Vượt giới hạn số lượt lấy trang");
                        }

                        List<Person> page = ldap.search(
                                "ou=people", // DN tương đối với base
                                "(&(objectClass=inetOrgPerson)(uid=*))",
                                search,
                                (AttributesMapper<Person>) attrs ->
                                        new Person(
                                                value(attrs, "uid"),
                                                value(attrs, "cn")),
                                pager);

                        // Search có dữ liệu chưa chứng minh server đã phân trang.
                        if (pager.getExchange().getResponse() == null) {
                            throw new IllegalStateException(
                                    "LDAP không trả Paged Results Response");
                        }
                        all.addAll(page);

                        if (all.size() > MAX_ENTRIES) {
                            throw new IllegalStateException(
                                    "Tập kết quả vượt ngân sách ứng dụng");
                        }
                    } while (pager.hasMore());

                    return all;
                });
    }

    private static String value(Attributes attributes, String name)
            throws NamingException {
        Attribute attr = attributes.get(name);
        return attr == null ? null : String.valueOf(attr.get());
    }
}
~~~

Những điểm quan trọng của ví dụ:

1. **SUBTREE_SCOPE** tìm cả các OU con của **ou=people**; filter chỉ nhận người dùng phù hợp **inetOrgPerson** có **uid**.
2. **PagedResultsControlExchangeDirContextProcessor** quản lý request/response cookie cho các trang liên tiếp. **hasMore()** quyết định còn trang tiếp theo hay không; không suy ra từ **page.size() == pageSize**.
3. **SingleContextSource.doWithSingleContext(...)** giữ context/kết nối qua vòng lặp, tránh cookie bị từ chối vì thay kết nối giữa chừng.
4. Kiểm tra **response control** để tránh nhầm trường hợp server không thực thi paging mà vẫn trả dữ liệu search thông thường.
5. Có **giới hạn page size, số trang và số entry** để ví dụ không thể vô tình đọc vô hạn. Đây là giới hạn phía ứng dụng; nên thêm deadline tổng thể và xử lý dừng/giải phóng trạng thái phân trang của server theo RFC và khả năng provider.
6. **setTimeLimit(5000)** là giới hạn từng search của JNDI, không tự tạo deadline cho toàn bộ chuỗi. Tương tự, **setReturningAttributes(...)** giới hạn thuộc tính tải về, không giới hạn số entry phù hợp mà LDAP server phải duyệt.

**Lưu ý phiên bản:** Nếu dự án dùng **Spring LDAP 3.x**, API tương ứng là **PagedResultsDirContextProcessor(pageSize)**; lớp này đã được **deprecated** ở Spring LDAP 4.1 để nhường cho **PagedResultsControlExchangeDirContextProcessor**. Đừng trộn tên class của hai phiên bản mà chưa kiểm tra dependencies. Dù dùng processor nào, vấn đề giữ cùng kết nối vẫn tồn tại.

## 5. Sorting phải phục vụ toàn bộ chuỗi, không sort từng trang

RFC 2696 chỉ định **phân trang**, không tự quy định **thứ tự sắp xếp** theo nghiệp vụ. Nếu giao diện yêu cầu “nhân viên theo tên”, cần gửi thêm **Server-side Sort Control** (RFC 2891) khi server hỗ trợ. Sắp xếp **từng mảng page ở Java** tạo ra thứ tự sai:

~~~text
Tập dữ liệu đúng thứ tự tên: [An, Binh, Chi, Dung, Hoa, Lan]

Server trả:
  Page 1: [Lan, An, Dung]
  Page 2: [Chi, Hoa, Binh]

Client sort riêng:
  Page 1: [An, Dung, Lan]
  Page 2: [Binh, Chi, Hoa]

Nối lại: [An, Dung, Lan, Binh, Chi, Hoa]  // Không có thứ tự toàn cục
~~~

Giải pháp: yêu cầu **server-side sort trên toàn tập kết quả** trước khi chia trang; giữ **cùng danh sách khóa sort** cho mọi request trong chuỗi. Chọn khóa phụ đủ ổn định khi nhiều entry trùng tên, ví dụ **cn** rồi **uid** (nếu **uid** là duy nhất theo phạm vi bạn quản lý). Khi sort theo thuộc tính không có ordering rule thích hợp, server có thể từ chối; cần kiểm tra **Sort Response Control**, không chỉ thấy có dữ liệu là kết luận đã sort.

Thêm hai controls vào cùng request phải đúng với API Spring LDAP đang dùng; không giả định hai **DirContextProcessor** độc lập truyền liên tiếp cho cùng **search(...)** sẽ tự động ghép controls. Dùng cơ chế kết hợp controls mà thư viện/server hỗ trợ và xác minh cả **paged response** lẫn **sort response**. Với phiên bản 4.1+, có các abstraction **ControlExchange** và **DirContextProcessor**; việc phối hợp thực tế cần được kiểm tra trên dependency và LDAP server cụ thể.

**Ngay cả khi đã sort**, LDAP paging **không đảm bảo snapshot bất biến** nếu directory đang thay đổi. Một entry mới hoặc thuộc tính sort bị chỉnh giữa các lần đọc có thể khiến kết quả bị lặp, bỏ sót hoặc thay đổi thứ tự tương đối. RFC 2696 cho phép hiện tượng này khi tập kết quả thay đổi trong chuỗi phân trang.

## 6. Thiết kế API: next-page hợp lý hơn page=37

Với một API HTTP sử dụng LDAP phía sau, ba kiểu giao diện có ý nghĩa khác nhau:

| Mong muốn UI/API | Phương án khả thi | Đánh đổi |
| --- | --- | --- |
| **“Xem tiếp”** danh sách | Paged Results cookie trong **chuỗi search được quản lý**; chỉ cung cấp next token do ứng dụng kiểm soát nếu backend có cơ chế duy trì/tiếp tục kết nối tương thích. | Phải quản lý vòng đời, quyền truy cập, thời gian sống, tải server. |
| **Đồng bộ/batch toàn bộ subtree** | Duyệt lần lượt bằng cookie trên một context ổn định; xử lý từng trang và giải phóng tài nguyên khi xong. | Tổng số trang có thể lớn; cần checkpoint, timeout và chiến lược chạy lại. |
| **“Đi đến trang 37”** tức thời | Chỉ thực hiện khi server có **tính năng truy cập theo vị trí** thích hợp, như Virtual List View (VLV) trong một số directory; hoặc thiết kế chỉ mục/snapshot ở hệ thống riêng. | VLV không được mọi server hỗ trợ; chỉ mục riêng có chi phí đồng bộ và lưu trữ. |

### Không lộ trực tiếp cookie LDAP ra frontend

Nếu cần trả token cho API, hãy định nghĩa một **continuation token của ứng dụng** chứa hoặc tham chiếu đến trạng thái được phép sử dụng. Tối thiểu cần gắn trạng thái với **người dùng/tenant**, hash hoặc phiên bản của **filter**, **base DN**, **scope**, **sort**, thời hạn và session/connection nếu server cần. Token phải được chống sửa đổi và kiểm soát quyền; không nên coi base64 là cơ chế bảo vệ.

Chỉ truyền nguyên cookie LDAP giữa các HTTP request **không bảo đảm** lần sau có thể resume do kết nối LDAP có thể đã được trả về pool hoặc chuyển sang server khác. Nếu không thể duy trì state phù hợp giữa các HTTP request, API nên hạn chế lời gọi trong một phiên xử lý phía server, khởi động lại một truy vấn giới hạn khi cần hoặc dùng một mô hình lưu kết quả đã được materialize.

### Có dùng được keyset pagination như SQL?

Đôi khi có thể thiết kế **seek/keyset** dựa trên thuộc tính được sort, ví dụ filter tìm các **uid** lớn hơn giá trị cuối đã thấy theo một ordering rule phù hợp. Nhưng đây **không phải** khả năng phổ quát của LDAP:

- LDAP filter chuẩn có so sánh **>=** và **<=** với thuộc tính có ordering matching rule tương ứng; không có toán tử **>** thuần giống SQL trong mọi trường hợp.
- Nếu nhiều entry trùng khóa, cần điều kiện ghép khóa và cách lọc bảo đảm thứ tự, vốn có thể khó biểu diễn chính xác theo matching rule của server.
- Các thay đổi danh tính và thuộc tính sort trong quá trình duyệt vẫn gây trùng/bỏ sót.

Vì vậy chỉ dùng seek pagination khi schema, matching rule, khả năng server và logic nghiệp vụ cho phép chứng minh đúng. Không thay một phép **OFFSET** giả bằng filter cắt chuỗi tùy ý.

## 7. Các lỗi thường gặp và cách xử lý

| Dấu hiệu | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| **Trang 2 trùng trang 1** | Không gửi cookie mới, mỗi lần lại gửi cookie rỗng. | Chuyển tiếp đúng cookie mới nhất; quản lý processor state trong cùng chuỗi. |
| **Invalid cookie / unwillingToPerform** | Cookie đã hết hiệu lực, không còn state trên server, sai kết nối hoặc thay đổi tham số truy vấn. | Dừng chuỗi; khởi động truy vấn mới theo giao kèo API, không tự tái dùng cookie cũ. |
| **Chỉ thấy vài chục entry dù subtree lớn** | Nhầm **count limit** với paging; filter/scope sai; server áp dụng size/time/admin limit. | Kiểm tra search scope, filter, response control và giới hạn server. |
| **Kết quả trang sau không đúng thứ tự** | Sort ở client trên từng trang, sort control bị bỏ qua hoặc server không hỗ trợ ordering rule. | Gửi Sort Control cùng paging và kiểm tra Sort Response Control. |
| **Mất/bị lặp entry khi đồng bộ** | Directory thay đổi giữa các lần lấy trang. | Chọn chiến lược đối soát theo ID bất biến, snapshot/change tracking hoặc quét bổ sung tùy server. |
| **Bị timeout sau nhiều trang** | Subtree/filter quá rộng, server thiếu index hoặc ứng dụng không đặt deadline tổng thể. | Thu hẹp base/scope/filter, giới hạn batch, đo latency và tối ưu directory. |
| **Cookie dùng được ở dev nhưng lỗi sau deploy** | Nhiều LDAP endpoint/pool, request HTTP được chạy trên các kết nối khác nhau. | Giữ connection affinity cho chuỗi hoặc quản lý session phía server; không mặc định cookie là stateless. |
| **Server bỏ qua Paged Control** | Không hỗ trợ control hoặc client không yêu cầu critical/không kiểm tra response. | Kiểm tra **supportedControl** trong Root DSE và fail closed khi API đòi paging bắt buộc. |

Một số LDAP server cho phép dừng sớm một paged sequence bằng yêu cầu đặc biệt **page size = 0** cùng **cookie mới nhất** (theo RFC 2696). Nếu client chỉ ngừng gọi thêm trang, tài nguyên phía server có thể phải chờ thời gian hết hạn. Cần quyết định chính sách hủy chuỗi theo API của provider và thư viện; không tự gửi một cookie bất kỳ khi đã đóng session.

## 8. Bảo mật và hiệu năng khi tìm subtree lớn

Phân trang không được dùng để lách **server size limits** hoặc **ACL**. Tài khoản kết nối thông qua **ContextSource** cần được xác thực đúng, có quyền tối thiểu và dùng **LDAPS/StartTLS** phù hợp môi trường. Nếu người dùng chỉ có quyền xem một nhánh, API không nên nhận base DN tùy ý rồi trả dữ liệu từ toàn cây thư mục.

Một số thực hành nên áp dụng:

1. **Giới hạn page size**, ví dụ 50–200 theo đặc điểm server và lượng thuộc tính, có một mức trần cứng.
2. **Chọn filter và scope chặt chẽ**: dùng subtree khi thật sự cần đi nhiều cấp; không search toàn bộ domain để lấy một nhóm nhỏ.
3. **Giảm thuộc tính trả về** bằng **setReturningAttributes(...)**; tránh trả password, token, objectClass dư thừa và dữ liệu nhạy cảm.
4. **Thiết lập ngân sách**: số trang tối đa mỗi job, deadline tổng thể, time limit cho từng search, giới hạn đồng thời và retry có backoff.
5. **Theo dõi thông số**: thời gian từng trang, tổng entry xử lý, page count, tỷ lệ cookie lỗi, sort failure, lỗi size/admin limit và kết nối đang giữ.
6. **Kiểm tra mức độ hỗ trợ server**: Paged Results, Sort Control, VLV (nếu dự định dùng), matching rules, index và chính sách session. Không mặc định mọi LDAP server đều hành xử giống nhau.

## 9. Kịch bản kiểm thử nên có

| Kịch bản | Kết quả mong đợi |
| --- | --- |
| Search **SUBTREE_SCOPE** dưới **ou=people** có nhiều OU con | Kết quả bao gồm entry ở cấp con đúng filter; không bị giới hạn ở một OU trực tiếp. |
| 7 entry, page size 3 | Ba lượt trả **3, 3, 1**; cookie cuối rỗng; không cần tự tính offset. |
| Lần đầu dùng cookie rỗng, lần tiếp dùng cookie mới nhất | Duyệt đủ kết quả khi directory không đổi và server hỗ trợ paging. |
| Tạo cookie bằng cách encode **pageNumber** | Bị thiết kế từ chối; cookie chỉ đến từ LDAP server. |
| Thử lấy trang sau trên kết nối khác | Xác định đúng hành vi server/provider; code không ngầm giả định cookie dùng được. |
| Server không hỗ trợ Paged Results | API phát hiện response không có paging; không công bố đã phân trang thành công. |
| Search với sort keys và paging | Cùng sort keys trên mọi trang; xác minh response sort và thứ tự toàn cục. |
| Thêm/sửa entry giữa các trang | Có test cho duplicate/skip và chiến lược đối soát hoặc tính nhất quán mong muốn. |
| Filter quá rộng và đạt admin limit | Dừng an toàn, không trả kết quả thiếu như tập dữ liệu đầy đủ. |
| Hết ngân sách số trang/timeout | Job dừng với trạng thái rõ ràng; connection được giải phóng; có chính sách hủy phân trang. |
| Nhiều người dùng đồng thời | Không dùng lẫn cookie, session hoặc quyền truy cập giữa các request. |

Để chứng minh đặc tính của cookie, sort và connection affinity, cần **integration test với LDAP server thật hoặc test container tương thích**. Unit test chỉ xác minh được mapper, điều kiện vòng lặp và việc truyền tham số; nó không chứng minh RFC control được server hỗ trợ.

## Ghi nhớ

**LDAP subtree search không có phép OFFSET theo kiểu SQL**. Với Spring LDAP, dùng **Simple Paged Results Control** và **opaque cookie** để duyệt **tuần tự**, giữ cùng kết nối khi provider/server yêu cầu, giữ nguyên tham số search và kiểm tra response control. Nếu UI cần thứ tự xác định, phối hợp **server-side sorting** cho toàn tập kết quả; nếu cần nhảy trang ngẫu nhiên, phải xác minh khả năng VLV hoặc dùng mô hình lưu kết quả riêng. Kết quả phân trang không đương nhiên là một snapshot bất biến khi directory thay đổi.

## Tài liệu tham khảo

- [RFC 2696 – LDAP Control Extension for Simple Paged Results Manipulation](https://www.rfc-editor.org/rfc/rfc2696).
- [RFC 2891 – LDAP Control Extension for Server Side Sorting of Search Results](https://www.rfc-editor.org/rfc/rfc2891).
- [Spring LDAP – Processing the DirContext và Paged Results](https://docs.spring.io/spring-ldap/reference/processing-the-dircontext.html).
- [Spring LDAP – PagedResultsControlExchangeDirContextProcessor API](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/control/PagedResultsControlExchangeDirContextProcessor.html).
