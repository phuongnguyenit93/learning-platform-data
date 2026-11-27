# Sort control và sắp xếp phía server trong Spring LDAP

Một màn hình quản trị danh bạ thường cần hiển thị danh sách người dùng theo họ tên, bộ phận hoặc mã nhân viên. Trong **Spring LDAP**, lời gọi **LdapTemplate.search(...)** thông thường trả các entry theo thứ tự do LDAP server cung cấp; ứng dụng **không nên giả định** thứ tự này là theo DN, theo ngày tạo hoặc theo tên. Khi kết quả lớn hay được phân trang, việc tải một phần dữ liệu rồi **sort ở Java** có thể khiến các trang hiển thị sai thứ tự tổng thể.

**Server-side sorting** giải quyết yêu cầu này bằng cách đưa một **LDAP Sort Control** vào chính yêu cầu tìm kiếm. LDAP server thực hiện sắp xếp theo khóa đã chọn và gửi lại kết quả theo thứ tự đó, đồng thời trả thông tin liệu việc sort có thành công không. Chủ đề này thuộc chương **Search nâng cao** của module **SPRING_LDAP**, kết nối các kiến thức về filter, search scope, schema, **ContextSource**, **LdapTemplate**, phân trang và xử lý lỗi LDAP.

## 1. Vì sao cần sắp xếp phía server?

Giả sử tìm thấy các người dùng có **cn** lần lượt là:

~~~text
LDAP search không yêu cầu sort:
  [Nguyen Van B, Le Thi C, Bui An, Tran A]

LDAP search có sort tăng dần theo cn (minh họa):
  [Bui An, Le Thi C, Nguyen Van B, Tran A]
~~~

Thứ tự thực tế phụ thuộc **matching rule/collation** mà server sử dụng; ví dụ trên chỉ nhằm minh họa ý tưởng. Không được mặc nhiên áp dụng thứ tự chữ cái tiếng Việt trong Java vào kết quả LDAP.

| Phương án | Cách hoạt động | Phù hợp khi | Giới hạn |
| --- | --- | --- | --- |
| **Sort trong ứng dụng** | Client nhận kết quả rồi dùng comparator Java. | Tập kết quả nhỏ, đã tải **toàn bộ** và cần thứ tự tùy biến của ứng dụng. | Nếu chỉ nhận trang đầu hoặc bị size limit, client chỉ sắp xếp được phần đã tải; không tạo được thứ tự toàn cục. |
| **LDAP Server-side Sort Control** | Server sắp xếp toàn bộ tập kết quả phù hợp với tìm kiếm theo khóa được yêu cầu. | Danh bạ lớn, cần thứ tự thống nhất khi phân trang hoặc tránh tải mọi entry về client. | Server phải hỗ trợ control, sort key và matching rule; có thể tốn CPU/bộ nhớ hoặc bị giới hạn quản trị. |

Ví dụ không đúng:

~~~text
Tập thực:      [A, B, C, D, E, F]
Server trả:    [F, B, D, A, E, C]   (thứ tự không đảm bảo)
Client lấy 3:  [F, B, D]
Client sort:   [B, D, F]            (không phải trang 1 của [A, B, C, D, E, F])
~~~

Do đó, nếu API yêu cầu “trang 1, xếp theo **cn**”, cần để server thực hiện **sort trên tập kết quả của truy vấn** rồi mới lấy các trang; **sort từng trang riêng** không tương đương với sort toàn bộ.

## 2. LDAP Sort Control theo RFC 2891

**RFC 2891 – LDAP Control Extension for Server Side Sorting of Search Results** quy định một cặp control:

| Loại control | OID | Mục đích |
| --- | --- | --- |
| **Sort Request Control** | **1.2.840.113556.1.4.473** | Đính kèm vào **SearchRequest** để yêu cầu sắp xếp. |
| **Sort Response Control** | **1.2.840.113556.1.4.474** | Server gửi trong **SearchResultDone** để cho biết kết quả sort hay lỗi sort. |

Sort request chứa **danh sách khóa** có thứ tự ưu tiên từ cao xuống thấp:

~~~text
SortKeyList = [
  {attributeType: "sn", reverseOrder: false},
  {attributeType: "givenName", reverseOrder: false},
  {attributeType: "uid", reverseOrder: false}
]

Nghĩa: sắp theo sn; nếu trùng sn thì xét givenName;
      nếu còn trùng thì xét uid.
~~~

Mỗi khóa có các phần:

- **attributeType:** tên thuộc tính hoặc attribute description cần sắp xếp, ví dụ **cn**, **sn**, **uid**.
- **orderingRule (tùy chọn):** matching rule dùng để so sánh thứ tự; phải phù hợp với syntax/schema của thuộc tính. Nếu bỏ qua, server dùng ordering rule dành cho thuộc tính đó khi có thể.
- **reverseOrder (tùy chọn):** mặc định **false** (thứ tự tăng); đặt **true** để đảo thứ tự của khóa tương ứng.

Trong wire protocol, danh sách khóa được mã hóa theo **BER/ASN.1** bên trong control. Không truyền chuỗi JSON minh họa ở trên vào server như một control thực. Thư viện LDAP/JNDI đảm nhiệm việc mã hóa.

### Criticality và việc kiểm tra response

LDAP control có cờ **critical**:

- **critical = true:** nếu server không hỗ trợ control, request phải thất bại thay vì trả một tập kết quả không có sắp xếp. Đây thường là lựa chọn cho API yêu cầu thứ tự có bảo đảm.
- **critical = false:** server không hỗ trợ có thể **bỏ qua sort control**, sau đó vẫn trả kết quả search. Dữ liệu nhận được **không được xem là đã sort** chỉ vì lệnh search thành công.

Ngay cả khi search trả về entry và không ném exception, **sort vẫn có thể thất bại độc lập**. Ứng dụng phải kiểm tra **Sort Response Control** và mã **sortResult = success (0)** khi cần bảo đảm thứ tự. Theo RFC 2891, nếu không có sort response, client nên xem yêu cầu sort đã bị bỏ qua. Một số trường hợp search thất bại hoặc không có entry, server có thể không gửi sort response; cần phân biệt “không có dữ liệu” với “có dữ liệu nhưng thứ tự chưa được xác nhận”.

~~~mermaid
sequenceDiagram
    participant App as Spring LDAP client
    participant Server as LDAP server
    App->>Server: SearchRequest + Sort Request Control (cn)
    Server->>Server: Search + xác định thứ tự theo schema/rule
    Server-->>App: SearchResultEntry theo thứ tự
    Server-->>App: SearchResultDone + Sort Response Control
    App->>App: Kiểm tra sortResult trước khi trả dữ liệu có cam kết thứ tự
~~~

## 3. Sử dụng Sort Control với Spring LDAP

Spring LDAP cung cấp cơ chế **DirContextProcessor** để thao tác với các LDAP request/response control quanh một lệnh **LdapTemplate.search(...)**. Processor thêm control trước khi search và đọc response sau khi Spring LDAP đã duyệt kết quả. Khi sử dụng control, **ContextSource** phải cung cấp **LdapContext** (thường dùng **LdapContextSource**), thay vì một **DirContext** không hỗ trợ LDAPv3 controls.

Cần xác định phiên bản thư viện để chọn API phù hợp:

| Phiên bản Spring LDAP | Cách làm |
| --- | --- |
| **4.1 trở lên** | Ưu tiên **SortControlExchange** kết hợp **ControlExchangeDirContextProcessor**. |
| **3.x** hoặc mã cũ | Có thể dùng **SortControlDirContextProcessor**; lớp này đã được đánh dấu **deprecated** ở các phiên bản mới. |

### Ví dụ Spring LDAP 4.1+: SortControlExchange

Ví dụ sau giả định **LdapTemplate** được inject sẵn, **ContextSource** có base DN **dc=example,dc=org**, và user kết nối được quyền search trong **ou=people**. Server phải hỗ trợ server-side sorting và các khóa đã chọn. Lệnh tìm tất cả **inetOrgPerson** có **uid**, sắp theo **cn**, rồi **uid** để giảm trường hợp hai người trùng tên.

~~~java
import java.util.List;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;
import javax.naming.directory.SearchControls;
import javax.naming.ldap.SortControl;
import javax.naming.ldap.SortResponseControl;

import org.springframework.ldap.control.ControlExchangeDirContextProcessor;
import org.springframework.ldap.control.SortControlExchange;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.stereotype.Service;

@Service
public class SortedPersonSearch {
    private final LdapTemplate ldapTemplate;

    public SortedPersonSearch(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public record PersonRow(String uid, String cn) { }

    public List<PersonRow> findByName() {
        SearchControls controls = new SearchControls();
        controls.setSearchScope(SearchControls.ONELEVEL_SCOPE);
        controls.setReturningAttributes(new String[] {"uid", "cn"});
        controls.setTimeLimit(3000); // Giới hạn phía client, tính bằng ms.

        var exchange = new SortControlExchange("cn", "uid");
        var processor =
            new ControlExchangeDirContextProcessor
                <SortControl, SortResponseControl>(exchange);

        List<PersonRow> rows = ldapTemplate.search(
                "ou=people",
                "(&(objectClass=inetOrgPerson)(uid=*))",
                controls,
                (AttributesMapper<PersonRow>) attrs ->
                    new PersonRow(text(attrs, "uid"), text(attrs, "cn")),
                processor
        );

        // Chỉ xác nhận 'sorted' khi server trả SortResponseControl
        // với trạng thái thành công; không dựa vào thứ tự của rows.
        SortResponseControl response =
                processor.getExchange().getResponse();
        if (response == null || !response.isSorted()) {
            int code = response == null ? -1 : response.getResultCode();
            throw new IllegalStateException(
                    "LDAP server chưa xác nhận sort; sort code=" + code);
        }
        return rows;
    }

    private static String text(Attributes attrs, String name)
            throws javax.naming.NamingException {
        Attribute value = attrs.get(name);
        return value == null ? null : String.valueOf(value.get());
    }
}
~~~

Điểm cần chú ý:

1. **SearchControls.ONELEVEL_SCOPE** tìm trực tiếp bên dưới **ou=people**. Nếu users được lưu trong nhiều OU con, phải chọn scope phù hợp và cân nhắc lượng dữ liệu.
2. **setReturningAttributes(...)** hạn chế thuộc tính trả về, **không** giới hạn số entry được tìm và sắp xếp. Khóa sort có thể được server dùng trong quá trình xử lý ngay cả khi không nằm trong danh sách thuộc tính trả về, tùy chính sách truy cập.
3. **SortControlExchange("cn", "uid")** biểu diễn hai khóa tăng dần. Việc server hỗ trợ từng khóa/matching rule cần được kiểm chứng bằng response và kiểm thử tích hợp.
4. **processor.getExchange().getResponse()** đọc control trả về. Nếu search không có entry và response bị lược bỏ theo RFC, ví dụ hiện tại sẽ báo “chưa xác nhận sort”. API thực tế có thể xử lý danh sách rỗng riêng nếu đã xác định LDAP search thành công.
5. Mỗi request nên tạo processor/exchange thích hợp với lần search. Không dùng một processor chứa response state làm singleton chia sẻ giữa các request đồng thời.

**Lưu ý phiên bản:** **SortControlExchange** và **ControlExchangeDirContextProcessor** xuất hiện từ dòng Spring LDAP **4.1**; dự án đang dùng Spring LDAP cũ phải dùng API sẵn có trong phiên bản tương ứng. Mã trên là ví dụ search có một vòng yêu cầu/đáp ứng, chưa triển khai paging.

### Ví dụ Spring LDAP 3.x: SortControlDirContextProcessor

Trong ứng dụng đang dùng Spring LDAP **3.x**, có thể dùng processor chuyên dụng với một khóa:

~~~java
import org.springframework.ldap.control.SortControlDirContextProcessor;

SortControlDirContextProcessor sort =
        new SortControlDirContextProcessor("cn");
sort.setCritical(true);

List<String> names = ldapTemplate.search(
        "ou=people",
        "(objectClass=inetOrgPerson)",
        controls,
        (AttributesMapper<String>) attrs ->
                String.valueOf(attrs.get("cn").get()),
        sort
);

if (!sort.isSorted()) {
    throw new IllegalStateException(
            "LDAP sort không thành công; resultCode=" + sort.getResultCode());
}
~~~

**SortControlDirContextProcessor** là lớp **có trạng thái**; luôn tạo instance mới cho từng search. Trong Spring LDAP 4.1+, lớp này được giữ để hỗ trợ mã cũ nhưng đã deprecated; khi nâng cấp nên chuyển sang API **SortControlExchange**. Ví dụ của phiên bản 3.x sử dụng **controls** là một **SearchControls** đã được cấu hình tương tự ví dụ trước.

## 4. Khóa sort, kiểu dữ liệu và thứ tự kết quả

LDAP **không** lấy comparator của Java như **String.CASE_INSENSITIVE_ORDER** để sắp xếp. Server áp dụng **ordering matching rule** tương ứng với thuộc tính được yêu cầu hoặc do control chỉ rõ. Kết quả có thể khác quy tắc sắp xếp theo locale trong UI, đặc biệt với dấu tiếng Việt, ký tự hoa/thường, số được lưu dạng chuỗi và cách xử lý khoảng trắng.

| Trường hợp | Điều cần lưu ý |
| --- | --- |
| **cn**, **sn** dạng Directory String | Cách sort phụ thuộc ordering rule và khả năng server. Không giả định có thể sort mọi thuộc tính chuỗi mặc định; server có thể báo **inappropriateMatching**. |
| Thuộc tính số/ngày có ordering rule | Server có thể so sánh theo kiểu dữ liệu và matching rule, không theo thứ tự từ điển của giá trị dạng chuỗi. |
| Giá trị thiếu (NULL) | Theo RFC 2891, giá trị thiếu được coi lớn hơn mọi giá trị hợp lệ: thường nằm cuối khi tăng dần, đầu khi đảo chiều. |
| Thuộc tính nhiều giá trị | RFC 2891 khuyến nghị server dùng giá trị nhỏ nhất theo ordering rule trong các điều kiện được quy định; nên kiểm thử với server thực tế. |
| Nhiều entry có cùng khóa | Tương quan thứ tự giữa các entry trùng khóa chưa xác định; thêm khóa phụ ổn định, phân biệt được entry khi server hỗ trợ. |
| Khóa chứa thông tin nhạy cảm | ACL và chính sách server có thể ngăn sắp xếp theo thuộc tính không được phép đọc hoặc truy cập. |

Ví dụ muốn sort theo **sn → givenName → uid** thì gửi ba khóa theo đúng thứ tự ưu tiên. Nếu API cho phép người dùng chọn cột sort, **chỉ nhận giá trị từ danh sách cho phép** (ví dụ **cn**, **uid**, **sn**) thay vì chuyển tên thuộc tính tùy ý do client cung cấp; còn cần kiểm soát việc sort theo thuộc tính nặng hoặc nhạy cảm.

### Sort giảm dần và matching rule tùy chỉnh

Với JNDI, **SortKey** cho phép mô tả chiều sắp xếp và matching rule:

~~~java
import javax.naming.ldap.SortKey;
import javax.naming.ldap.SortControl;
import javax.naming.ldap.Control;

SortKey[] keys = {
    new SortKey("sn", false, null), // descending
    new SortKey("uid", true, null)  // ascending
};
SortControl requestControl = new SortControl(keys, Control.CRITICAL);
~~~

**false** trong **SortKey** là **ascending=false** (giảm dần), còn **true** là tăng dần. Đây chỉ là đoạn minh họa **cách mô tả request control của JNDI**; để gửi bằng **LdapTemplate**, cần đưa control vào một **DirContextProcessor/ControlExchange** phù hợp phiên bản, không chỉ khởi tạo đối tượng **requestControl** rồi gọi search bình thường. Không tự chọn một matching rule bằng tên/ OID khi chưa xác nhận server hỗ trợ và quy tắc đó tương thích với attribute syntax.

## 5. Kết hợp Server-side Sorting và phân trang

Với hàng nghìn entry, server-side sort thường đi cùng **Simple Paged Results Control** theo **RFC 2696**. Điều này đòi hỏi phân biệt hai khái niệm:

- **Sắp xếp toàn bộ tập kết quả:** server xác định thứ tự của các entry khớp filter.
- **Trả từng trang:** server gửi một phần kết quả và cookie cho client lấy phần kế tiếp.

~~~text
Search: (objectClass=inetOrgPerson), sort: cn + uid

Tập kết quả đã sort của server:
  [A, B, C, D, E, F, G, H, I]

Page size = 3:
  Page 1 [A, B, C]  -> cookie1
  Page 2 [D, E, F]  -> cookie2
  Page 3 [G, H, I]  -> end
~~~

RFC 2891 yêu cầu **cùng SortKeyList** phải được gửi trong **mỗi SearchRequest** thuộc chuỗi trang, và khóa sort **không được thay đổi** giữa các trang của cùng tập kết quả. Server cần sắp xếp **toàn bộ** tập kết quả rồi trả trang tương ứng; sort riêng từng trang là sai. Kết quả có thể bị ảnh hưởng nếu directory thay đổi trong lúc client đang lấy các trang; server-side sort không tự tạo một snapshot nhất quán qua mọi lần search.

Khi dùng Spring LDAP:

1. Thêm **cả paging control và sort control** cho mỗi yêu cầu tìm kiếm. API nào phù hợp phụ thuộc phiên bản Spring LDAP; có thể cần cơ chế tổng hợp **DirContextProcessor/ControlExchange**.
2. Giữ nguyên **base DN**, **filter**, **scope**, **sort keys**, **page size** và các tham số có liên quan trong suốt vòng phân trang, trừ khi server/documentation cho phép thay đổi cụ thể.
3. Giữ **paged results cookie** và sử dụng **cùng kết nối LDAP** trong chuỗi request nếu provider/server yêu cầu. Spring LDAP có **SingleContextSource** hoặc tích hợp transaction-aware context giúp giữ context cho các lần lấy trang.
4. Kiểm tra **Sort Response Control** ở các trang được server trả về, đồng thời xử lý lỗi paging/cookie riêng; đừng coi chỉ việc nhận cookie là bằng chứng sort thành công.
5. Nếu UI cần thứ tự tuyệt đối ổn định khi có cập nhật đồng thời, phải thiết kế thêm cơ chế snapshot, khóa phiên bản hoặc quy tắc nghiệp vụ chấp nhận dữ liệu thay đổi. Sort và paging tự thân không bảo đảm điều đó.

**Virtual List View (VLV)** là một control khác dùng với server-side sorting trong một số directory, nhưng khả năng hỗ trợ không đồng nhất; không coi VLV là lựa chọn thay thế mặc định cho RFC 2696.

## 6. Hiệu năng, giới hạn và bảo mật

Việc yêu cầu sort không có nghĩa server luôn hoàn thành nhanh. LDAP server có thể cần thu thập, so sánh nhiều entry trước khi gửi kết quả; chỉ mục (index) và cấu hình schema có thể làm thay đổi đáng kể thời gian xử lý.

| Vấn đề | Cách thiết kế |
| --- | --- |
| Filter quá rộng | Thu hẹp **base DN**, **search scope** và filter trước khi sort; tránh tìm toàn directory chỉ để hiển thị một OU. |
| Thuộc tính sort chưa có index hoặc không có ordering rule | Kiểm tra schema/matching rule và chỉ mục phù hợp theo tài liệu server; đo truy vấn thực tế trước khi tối ưu. |
| Giới hạn tài nguyên | Đặt **size limit**, **time limit**, page size hợp lý và tôn trọng administrative limits; không tìm cách chia nhỏ filter để lách giới hạn. |
| Nhiều client sort đồng thời | Giới hạn concurrency/rate, theo dõi p95 latency, timeout, memory/CPU của server và lỗi sort. |
| Thuộc tính cần được bảo vệ | Chỉ cho phép sort theo thuộc tính phù hợp với quyền truy cập, áp dụng ACL, xác thực và kết nối **LDAPS/StartTLS** theo cấu hình bảo mật. |
| Dữ liệu đa ngôn ngữ | Kiểm chứng thứ tự Unicode/dấu tiếng Việt với server; nếu UI đòi hỏi locale riêng không được server hỗ trợ, thiết kế yêu cầu dữ liệu/sort lại cho phù hợp. |

**setReturningAttributes(...)** giảm dữ liệu truyền về client, nhưng **không** bảo đảm giảm chi phí server phải tìm và sắp xếp. Tương tự, **setCountLimit(...)** có thể khiến chỉ nhận một phần kết quả, nên phải làm rõ giao kèo API về tính đầy đủ và phân trang.

Trong log/audit, ghi **mã truy vấn**, **base/scope/filter đã kiểm soát**, **sort keys**, thời gian, mã sort response và số entry; tránh ghi thuộc tính người dùng, mật khẩu hay token nhạy cảm.

## 7. Xử lý lỗi và kiểm chứng kết quả sort

**Sort Response Control** có thể có một mã lỗi riêng trong khi LDAP search không nhất thiết thất bại theo cùng cách. Các mã dưới đây là mã **sortResult** theo RFC 2891:

| sortResult | Ý nghĩa thường gặp | Hành động |
| --- | --- | --- |
| **success (0)** | Server xác nhận đã sort theo khóa chỉ định. | Có thể trả kết quả với cam kết thứ tự, kèm giới hạn dữ liệu của search. |
| **noSuchAttribute (16)** | Khóa sort dùng thuộc tính server không nhận ra. | Kiểm tra tên thuộc tính/schema và allowlist. |
| **inappropriateMatching (18)** | Matching rule không có hoặc không phù hợp. | Kiểm tra ordering rule/schema, đổi khóa tương thích. |
| **timeLimitExceeded (3)** | Không hoàn thành sort trước time limit. | Giới hạn truy vấn và đánh giá hiệu năng; không coi dữ liệu là đã sort. |
| **adminLimitExceeded (11)** | Vượt giới hạn quản trị của server. | Thu hẹp filter hoặc xử lý theo quy tắc giới hạn chính thức. |
| **insufficientAccessRights (50)** | Không có quyền thực hiện sort yêu cầu. | Kiểm tra ACL và chính sách phân quyền. |
| **busy (51)** hoặc **unwillingToPerform (53)** | Server quá tải hoặc từ chối xử lý. | Đo tải, kiểm tra cấu hình; chỉ retry có kiểm soát nếu lỗi tạm thời. |
| **Không có response** | Sort có thể bị bỏ qua, hoặc search không trả entry / đã thất bại. | Phân biệt nguyên nhân; không tự đánh dấu **sorted=true**. |

Ngoài ra, nếu **critical=true** mà server không hỗ trợ request control, LDAP search có thể thất bại với **unavailableCriticalExtension (12)**. Nếu **critical=false**, server có thể trả kết quả chưa sort mà không báo lỗi LDAP search; việc ứng dụng phớt lờ response là một lỗi logic.

Không nên bắt mọi **Exception** rồi sort lại một phần danh sách ở Java và trả như kết quả bình thường. Với API yêu cầu sort bắt buộc, báo lỗi có thể theo dõi hoặc cho caller chọn lại tiêu chí; chỉ dùng fallback khi giao kèo API cho phép và **toàn bộ tập kết quả** đã có trong bộ nhớ.

## 8. Kiểm thử tích hợp trên LDAP server

Do control và matching rule là khả năng của **server**, unit test chỉ xác minh được việc dựng request và mapper. Các ca sau cần test với directory tương ứng môi trường dùng thật:

| Kịch bản | Kỳ vọng |
| --- | --- |
| Không yêu cầu sort | Ứng dụng không giả định thứ tự mặc định của LDAP. |
| Sort tăng dần theo **cn** | Kết quả đúng thứ tự server đã xác nhận và có **sortResult=0**. |
| Sort hai khóa **cn, uid** | Khi nhiều entry trùng cn, uid quyết định thứ tự phụ. |
| Các bản ghi thiếu khóa sort | Kiểm tra vị trí NULL theo RFC 2891 và chính sách server. |
| Chứa dấu tiếng Việt, chữ hoa/thường | Xác nhận ordering rule/collation thực tế đáp ứng kỳ vọng UI. |
| Khóa sort không hợp lệ | Phát hiện **noSuchAttribute**/**inappropriateMatching**, không coi search thành công là sort thành công. |
| Server không hỗ trợ control, **critical=true** | Nhận lỗi tương ứng; ứng dụng không trả dữ liệu như đã sort. |
| Server không hỗ trợ control, **critical=false** | Phát hiện control bị bỏ qua; xử lý theo giao kèo API. |
| Sort cùng **Simple Paged Results** | Mọi trang giữ cùng sort keys; kết hợp lại ra đúng thứ tự toàn cục và không trùng/thiếu entry khi tập dữ liệu không đổi. |
| Search bị time limit hoặc admin limit | Trả lỗi rõ ràng, không ghi nhận sai thứ tự/độ đầy đủ. |
| Nhiều request song song | Processor và response riêng cho từng request, không có trạng thái sort bị dùng lẫn. |

Để kiểm thử paging và kết quả ổn định, trước tiên chạy với một dataset **không đổi**. Sau đó tạo kịch bản **thêm/sửa/xóa giữa các trang** để xác định ứng dụng cần xử lý thay đổi như thế nào. So sánh với thứ tự dự kiến từ matching rule của server, không mặc định lấy comparator Java làm chuẩn duy nhất.

## Ghi nhớ

**Server-side Sort Control** yêu cầu LDAP server sắp xếp kết quả **trước khi trả về client** và đặc biệt hữu ích khi kết hợp với phân trang. Với **Spring LDAP**, dùng **DirContextProcessor** để gắn request control và đọc response; chọn **SortControlExchange** cho phiên bản 4.1+ hoặc processor cũ cho 3.x. Luôn **kiểm tra Sort Response Control**, chọn sort key hợp lệ theo schema, giữ sort keys ổn định qua các trang, và đánh giá chi phí tính toán của server. Việc **search thành công** không tự chứng minh **sort thành công**.

## Tài liệu tham khảo

- [RFC 2891 – LDAP Control Extension for Server Side Sorting of Search Results](https://www.rfc-editor.org/rfc/rfc2891).
- [Spring LDAP – Processing the DirContext](https://docs.spring.io/spring-ldap/reference/processing-the-dircontext.html).
- [Spring LDAP – SortControlExchange API](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/control/SortControlExchange.html).
