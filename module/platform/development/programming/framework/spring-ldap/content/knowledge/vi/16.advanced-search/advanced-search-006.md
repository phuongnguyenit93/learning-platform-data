# Virtual List View và yêu cầu hỗ trợ của server trong Spring LDAP

Một giao diện quản trị có thể cần hiển thị hàng chục nghìn tài khoản LDAP theo thứ tự tên, cho phép người vận hành **nhảy tới vị trí thứ 2.001**, xem một vùng nhỏ quanh vị trí đó, hoặc cuộn qua một danh sách dài mà không tải toàn bộ thư mục. Cách gọi `LdapTemplate.search(...)` rồi sắp xếp và cắt danh sách trong Java không thích hợp: ứng dụng phải nhận quá nhiều entry, chịu giới hạn tài nguyên của server và dễ cho kết quả sai khi dữ liệu thay đổi.

**Virtual List View (VLV)** là một cơ chế mở rộng LDAP sử dụng *search controls* để yêu cầu server trả về **một cửa sổ nhỏ trong tập kết quả đã sắp xếp**. Khác với phân trang đơn giản, VLV hướng tới việc duyệt danh sách theo **vị trí** hoặc **giá trị sắp xếp**, với điều kiện quan trọng: **LDAP server phải hỗ trợ VLV lẫn Server-Side Sorting (SSS)** cho truy vấn cụ thể.

Bài thuộc chương **Search nâng cao** của **SPRING_LDAP**. Người học sẽ hiểu VLV request/response, cách khám phá `supportedControl` trên Root DSE, sử dụng `VirtualListViewControlAggregateDirContextProcessor` cùng `LdapTemplate`, quản lý offset và context cookie, phân biệt VLV với Simple Paged Results, xử lý server không hỗ trợ, ảnh hưởng schema/index/ACL và thiết kế kiểm thử truy cập thư mục an toàn.

## 1. Bài toán: duyệt một danh sách LDAP rất lớn

Giả sử một LDAP server có DIT:

~~~text
dc=example,dc=org
├── ou=people
│   ├── uid=an
│   ├── uid=binh
│   ├── uid=chi
│   └── ... hàng chục nghìn entry
├── ou=groups
└── ou=services
~~~

Một entry mẫu:

~~~ldif
dn: uid=an,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: an
cn: Nguyen Van An
sn: Nguyen
mail: an@example.org
~~~

UI yêu cầu: “Sắp theo `cn`, hiển thị 20 người một lần và có thể chuyển nhanh tới nhóm entry ở khoảng vị trí 1.001”. Có ba cách tiếp cận khác nhau:

| Cách tiếp cận | Server làm gì? | Hạn chế |
| --- | --- | --- |
| Tải toàn bộ rồi cắt bằng Java | Trả tập lớn cho client | Tốn bộ nhớ/băng thông, dễ vượt size limit và quyền đọc |
| Simple Paged Results (RFC 2696) | Trả những trang tiếp theo qua paging cookie | Phù hợp duyệt tuần tự; không phải API nhảy tới vị trí bất kỳ trong danh sách đã sắp |
| **Virtual List View + Server-Side Sort** | Sắp tập kết quả và trả một vùng quanh vị trí/giá trị mục tiêu | Yêu cầu server hỗ trợ controls, matching/index và trạng thái điều hướng |

VLV phù hợp với giao diện **danh sách có vị trí**; Simple Paged Results thường hợp lý hơn cho **đọc lần lượt** hoặc xử lý hàng loạt. Không cần VLV nếu mỗi truy vấn chỉ trả vài entry.

### VLV không thay thế search filter

VLV vẫn nằm trong một LDAP SearchRequest với:

- **Search base:** ví dụ `ou=people,dc=example,dc=org`.
- **Search scope:** ví dụ `SUBTREE_SCOPE` để bao gồm các OU con.
- **Filter:** ví dụ `(objectClass=inetOrgPerson)` hoặc `(&(objectClass=inetOrgPerson)(departmentNumber=DEV))`.
- **Sorting:** thuộc tính sắp xếp được server chấp nhận, ví dụ `cn`.
- **VLV window:** vùng kết quả mà client muốn nhận.

VLV **chỉ chọn cửa sổ trong tập kết quả phù hợp với filter và scope**, không phải cách bỏ qua ACL, schema hoặc mở rộng search ra ngoài base được cấp quyền.

## 2. VLV là control của giao thức LDAP, không phải một filter

LDAP v3 cho phép đính kèm **controls** vào một SearchRequest. VLV không phải chuỗi filter như `(uid=*)`, không phải thuộc tính bên trong entry và cũng không phải parameter HTTP của Spring Boot.

Các OID quan trọng:

| Control | Request OID | Response OID |
| --- | --- | --- |
| **VLV** | `2.16.840.1.113730.3.4.9` | `2.16.840.1.113730.3.4.10` |
| **Server-Side Sorting (SSS)** | `1.2.840.113556.1.4.473` | `1.2.840.113556.1.4.474` |
| **Simple Paged Results** | `1.2.840.113556.1.4.319` | Cùng cơ chế control của RFC 2696 |

**VLV không phải phần cốt lõi mà mọi LDAPv3 server bắt buộc triển khai.** Mô tả cơ chế VLV truyền thống nằm trong các tài liệu *Internet-Draft* về scrolling view; đừng gọi nó là tính năng mặc định của RFC 4511. Tính năng cụ thể có thể khác nhau theo sản phẩm server, phiên bản, plugin/index và chính sách quản trị.

Điểm mấu chốt trong mô hình VLV truyền thống: **một VLV request phải đi kèm Server-Side Sorting request**. Nếu không, server có thể báo lỗi `sortControlMissing (60)` trong VLV response hoặc từ chối yêu cầu.

~~~mermaid
sequenceDiagram
    participant UI as UI điều hướng
    participant App as Spring LDAP service
    participant LDAP as LDAP server
    UI->>App: Lấy 20 entry quanh offset=101
    App->>LDAP: Search(base, scope, filter) + SSS(cn) + VLV(offset=101)
    LDAP->>LDAP: Lọc theo ACL/filter; sắp và chọn cửa sổ
    LDAP-->>App: SearchResultEntry[] và response controls
    App->>App: Kiểm tra SSS/VLV result, contentCount/contextID
    App-->>UI: 20 hàng + metadata của cửa sổ
~~~

**Không sắp lại toàn bộ một trang đã trả về rồi coi đó là server-side sort.** VLV dựa trên thứ tự do server tạo cho **toàn bộ tập kết quả**, còn sắp từng cửa sổ ở Java có thể làm các trang không nhất quán.

## 3. Các thành phần của VLV request

Mô hình điều khiển VLV request thường được mô tả dưới dạng:

~~~text
VirtualListViewRequest ::= SEQUENCE {
    beforeCount  INTEGER,
    afterCount   INTEGER,
    target       CHOICE {
        byOffset {
            offset        INTEGER,  -- vị trí 1-based
            contentCount  INTEGER   -- thông tin về tổng số trước đó
        },
        greaterThanOrEqual AssertionValue
    },
    contextID    OCTET STRING OPTIONAL
}
~~~

Các trường:

| Trường | Ý nghĩa thực hành |
| --- | --- |
| **`beforeCount`** | Số entry yêu cầu lấy **trước** mục tiêu |
| **`afterCount`** | Số entry yêu cầu lấy **sau** mục tiêu |
| **`target.byOffset.offset`** | Vị trí mục tiêu trong tập đã sắp, **đếm từ 1** |
| **`target.byOffset.contentCount`** | Thông tin kích thước danh sách client đã biết; `0` có thể biểu diễn chưa biết |
| **`target.greaterThanOrEqual`** | Chọn vùng dựa trên giá trị so sánh theo sort order thay vì số thứ tự |
| **`contextID`** | Dữ liệu trạng thái opaque do server cung cấp để liên hệ các lượt duyệt, nếu có |

Ví dụ: danh sách có các vị trí `1..1000`, người dùng muốn cửa sổ quanh mục tiêu `101`:

~~~text
targetOffset = 101
beforeCount = 2
afterCount  = 3

Các vị trí mong đợi (nếu đủ entry):
99, 100, [101], 102, 103, 104
~~~

Ở ví dụ trên, cửa sổ có **tối đa 6 entry** vì tính cả entry mục tiêu: `2 + 1 + 3`. Gần đầu/cuối danh sách, server có thể trả ít hơn hoặc điều chỉnh vị trí hiệu lực theo khả năng/protocol.

### Offset 1-based và lỗi off-by-one

Trong web frontend, mảng và trang thường được đánh số từ **0**, trong khi `byOffset.offset` của VLV bắt đầu ở **1**.

| UI | VLV target offset minh họa |
| --- | --- |
| Dòng đầu tiên, index `0` | `1` |
| Dòng thứ 21, index `20` | `21` |
| Dòng thứ 101, index `100` | `101` |

Nếu UI chia trang 20 dòng và trang đầu được đánh số 0, vị trí bắt đầu của trang `pageIndex` là `pageIndex * 20 + 1`. Phải kiểm soát overflow và giới hạn offset hợp lệ; không cộng một cách tùy tiện cho mọi trường hợp.

### Chọn theo giá trị, không chỉ theo offset

`greaterThanOrEqual` hữu ích cho hành vi “nhảy tới phần danh sách bắt đầu gần chữ N” khi điều kiện sắp xếp phù hợp. Đây **không phải filter equality trên thuộc tính**, mà là cách chọn vị trí dựa vào giá trị trong thứ tự sắp của VLV.

Không phải API client nào cũng cung cấp cùng mức hỗ trợ cho cả hai cách chọn mục tiêu. Nếu chỉ dùng API processor của Spring LDAP trong ví dụ bên dưới, ta tập trung vào **cửa sổ theo offset**; muốn gửi assertion target kiểu khác có thể cần API/control cụ thể của client hoặc provider.

## 4. VLV response: vị trí, số lượng và context cookie

Một VLV response control có thể trả:

~~~text
VirtualListViewResponse ::= SEQUENCE {
    targetPosition         INTEGER,
    contentCount           INTEGER,
    virtualListViewResult  ENUMERATED,
    contextID              OCTET STRING OPTIONAL
}
~~~

| Trường | Cách diễn giải |
| --- | --- |
| `targetPosition` | Vị trí mục tiêu server đã xác định trong tập kết quả |
| `contentCount` | Số lượng/kích thước danh sách theo response; có thể là thông tin ước tính tùy server |
| `virtualListViewResult` | Trạng thái xử lý VLV, không nên bỏ qua |
| `contextID` | Token opaque mà server có thể trả để client dùng ở các yêu cầu tiếp theo |

**`contentCount` không phải bản cam kết tổng số vĩnh viễn hoặc một snapshot bất biến.** Khi entry được thêm/xóa, filter thay đổi, quyền người dùng đổi hoặc truy vấn đi qua server/replica khác, tổng số và vị trí có thể thay đổi. Một server cũng có thể cung cấp giá trị ước lượng.

Một số VLV-specific result cần lưu ý:

- `success (0)` — control được xử lý thành công.
- `sortControlMissing (60)` — thiếu Server-Side Sort request bắt buộc.
- `offsetRangeError (61)` — offset được yêu cầu nằm ngoài phạm vi hợp lệ của server/tập kết quả.
- Các trạng thái giới hạn như thời gian, quyền, busy hoặc unwilling-to-perform có thể được trả về tùy triển khai.

**Lỗi VLV trong response control không nhất thiết xuất hiện như một exception Java cho toàn bộ search.** Ứng dụng phải kiểm tra phản hồi của control, trạng thái SSS và những lỗi mà processor/client phơi bày, thay vì giả định có `List` là đủ.

### Context cookie không phải Paged Results cookie

VLV `contextID` là dữ liệu nhị phân opaque, có thể được Spring LDAP đưa vào `VirtualListViewResultsCookie`. Nó **khác** cookie của Simple Paged Results (RFC 2696) và không được đổi qua lại giữa hai API.

Khi dùng cookie:

- Giữ nguyên bytes do server trả về; không phân tích, tự tăng số hoặc sửa nội dung.
- Chỉ dùng lại với **ngữ cảnh truy vấn tương thích**: cùng base, scope, filter, sort, danh tính và server/session theo chính sách.
- Không mặc định cookie tồn tại, không hết hạn hoặc dùng được trên replica khác.
- Không dùng cookie làm access token, không ghi nó vào log công khai; ứng dụng vẫn cần phân quyền chính xác.
- Khi cookie hết hiệu lực hoặc dữ liệu thay đổi quá nhiều, sẵn sàng tạo lại một phiên duyệt thay vì lặp vô hạn.

## 5. Yêu cầu bắt buộc ở LDAP server

VLV là tính năng **server-side**. Việc thêm dependency Spring LDAP hoặc tạo `DirContextProcessor` **không tự bật VLV cho server**.

Thông thường cần kiểm tra các nhóm điều kiện:

| Điều kiện | Vì sao quan trọng |
| --- | --- |
| LDAP server công bố hỗ trợ VLV request OID | Client biết có thể gửi control |
| Server cũng hỗ trợ SSS request OID | VLV cần thứ tự kết quả phía server |
| User bind được phép search và sử dụng controls | ACL/giới hạn quản trị có thể chặn một số thao tác |
| Sort key được schema hỗ trợ | Matching rule/ordering của thuộc tính ảnh hưởng việc sort |
| Index/cấu hình cho filter và sort phù hợp | Server có thể yêu cầu VLV/sort index hoặc áp limit khi quá tải |
| Search base/scope hợp lệ | Control không thay thế DN, search filter, subtree và permission |
| Kết quả không vượt ngưỡng bộ nhớ, CPU, thời gian của server | Một cửa sổ nhỏ vẫn có thể cần server xử lý tập lớn |
| Response controls được client đọc và kiểm tra | Không bỏ qua lỗi sort hoặc VLV |

**Có OID trong Root DSE là tín hiệu cần thiết để khám phá khả năng, không phải bảo đảm mọi kiểu VLV search đều chạy thành công.** Server có thể cần index riêng, cho phép VLV trên một số base/attribute nhất định, hoặc chặn truy vấn rộng. Một proxy/virtual directory cũng có thể xử lý controls khác với backend.

### Không suy luận theo tên nhà cung cấp

Một số LDAP server hỗ trợ VLV trực tiếp, một số hỗ trợ trong phiên bản/cấu hình nhất định, số khác không hỗ trợ hoặc cần plugin/index. Cách xử lý đúng là **đọc capabilities của endpoint cụ thể đang kết nối, rồi kiểm thử truy vấn thật**. Không khẳng định “cứ dùng Active Directory/OpenLDAP/LDAP bất kỳ là VLV hoạt động” khi chưa xác minh đúng phiên bản và cấu hình.

## 6. Khám phá khả năng bằng Root DSE

**Root DSE** là entry đặc biệt có DN rỗng `""` ở gốc server, khác với naming context như `dc=example,dc=org`. Nó thường công bố các giá trị `supportedControl`.

Cần tìm ít nhất:

~~~text
supportedControl: 2.16.840.1.113730.3.4.9
supportedControl: 1.2.840.113556.1.4.473
~~~

Lưu ý **Root DSE không phải entry ở `dc=example,dc=org`**. Nếu `LdapContextSource` của ứng dụng có `base=dc=example,dc=org`, tìm bằng `.base("")` trong query builder có thể vẫn ở naming context root theo cấu hình chứ không chắc là Root DSE. Vì vậy nên dùng kết nối/công cụ cho phép truy vấn DN rỗng ở cấp server.

### Kiểm tra với `ldapsearch` trong môi trường lab

Lệnh minh họa với bộ công cụ OpenLDAP:

~~~bash
ldapsearch -x \
  -H "ldaps://ldap.example.org:636" \
  -s base -b "" supportedControl
~~~

Nếu server yêu cầu xác thực để đọc Root DSE, dùng tài khoản read-only và nhập password qua prompt an toàn:

~~~bash
ldapsearch -x \
  -H "ldaps://ldap.example.org:636" \
  -D "cn=app-reader,ou=services,dc=example,dc=org" \
  -W -s base -b "" supportedControl
~~~

Lệnh này chỉ **đọc metadata**, không ghi thư mục. Phải cấu hình CA/trust store phù hợp và **không tắt kiểm tra TLS** để cố vượt lỗi chứng chỉ. Tham số `-W` yêu cầu nhập password tương tác, không đưa secret vào lịch sử shell.

Khi nhìn response:

- Có **cả** VLV request OID và SSS request OID → có cơ sở thử VLV trên directory lab.
- Có SSS nhưng **không có VLV** → chỉ dùng server-side sort hoặc cách phân trang khác; không coi VLV là mặc định.
- Không thấy `supportedControl` → cần xem quyền đọc Root DSE, proxy, phiên bản server và tài liệu chính thức. Không tự động diễn giải “trống” thành “hỗ trợ”.
- Có OID nhưng request thực tế lỗi → kiểm tra index, giới hạn, quyền, sort key và response control trước khi quyết định bật tính năng.

### Tách kiểm tra capability khỏi request nghiệp vụ

Nên khám phá capability ở bước khởi tạo hoặc kiểm tra sức khỏe có kiểm soát, cache theo endpoint/cấu hình với thời hạn phù hợp. Khi cluster có nhiều LDAP backend, **khả năng hỗ trợ có thể không đồng nhất**: request VLV gửi tới một replica khác có thể không xử lý như server đầu tiên.

Không nên mở một search dữ liệu lớn trên mỗi request HTTP chỉ để “thử xem server có hỗ trợ VLV không”. Hãy kiểm tra capability, giới hạn phạm vi và có fallback được thiết kế trước.

## 7. Spring LDAP đã có processor hỗ trợ VLV

Spring LDAP cung cấp các class trong package `org.springframework.ldap.control`:

| Lớp | Vai trò |
| --- | --- |
| `VirtualListViewControlDirContextProcessor` | Xử lý request/response VLV |
| `SortControlDirContextProcessor` | Xử lý Server-Side Sort |
| **`VirtualListViewControlAggregateDirContextProcessor`** | Gộp processor VLV và processor Sort bắt buộc |
| `VirtualListViewResultsCookie` | Giữ context cookie, target position và content count từ response |
| `PagedResultsDirContextProcessor` | Cơ chế **Simple Paged Results**, khác VLV |

Dùng **aggregate processor** là phương án đơn giản khi cần VLV và SSS cùng nhau. `LdapTemplate.search(...)` có overload nhận `DirContextProcessor`; Spring LDAP gọi processor trước và sau search để gắn request controls rồi đọc response controls.

Đây **không** phải cú pháp `LdapQueryBuilder.where(...).is(...)`. Query builder xác định filter/base/scope; processor gắn **controls bổ sung vào cùng search request**.

### Thứ tự công việc trong một lần search

~~~text
LdapTemplate.search(base, filter, SearchControls, mapper, processor)
  ├─ Lấy context từ ContextSource
  ├─ processor.preProcess(context)
  │    └─ Thêm Sort request + VLV request vào LdapContext
  ├─ Gửi SearchRequest
  ├─ Duyệt các SearchResultEntry của cửa sổ
  ├─ mapper chuyển entry thành Java DTO
  ├─ processor.postProcess(context)
  │    └─ Đọc response controls và cookie/trạng thái
  └─ Trả DTO và metadata cho service
~~~

Processor có **trạng thái gắn với một lần search**, nên tạo mới cho mỗi request/cửa sổ. Không lưu một instance processor mutable trong singleton rồi dùng chung cho các thread.

## 8. Ví dụ Java: lấy cửa sổ đầu tiên bằng Spring LDAP

Giả sử `LdapContextSource.base=dc=example,dc=org`; tài khoản dịch vụ chỉ có quyền search dưới `ou=people` và server hỗ trợ VLV/SSS cho thuộc tính `cn`.

~~~java
import java.util.List;
import javax.naming.directory.SearchControls;
import org.springframework.ldap.control.VirtualListViewControlAggregateDirContextProcessor;
import org.springframework.ldap.control.VirtualListViewResultsCookie;
import org.springframework.ldap.core.ContextMapper;
import org.springframework.ldap.core.DirContextOperations;
import org.springframework.ldap.core.LdapTemplate;

record PersonRow(String dn, String uid, String commonName, String mail) {}

record VlvWindow(
        List<PersonRow> rows,
        int targetPosition,
        int reportedContentCount,
        VirtualListViewResultsCookie cookie) {}

public class PersonDirectoryBrowser {

    private final LdapTemplate ldapTemplate;

    public PersonDirectoryBrowser(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public VlvWindow firstWindow() {
        int pageSize = 20;

        SearchControls controls = new SearchControls();
        controls.setSearchScope(SearchControls.SUBTREE_SCOPE);
        controls.setReturningAttributes(new String[] {
                "uid", "cn", "mail"
        });
        controls.setTimeLimit(3000);

        // Aggregate kết hợp Sort(cn) với VLV.
        VirtualListViewControlAggregateDirContextProcessor processor =
                new VirtualListViewControlAggregateDirContextProcessor(
                        "cn", pageSize);

        List<PersonRow> rows = ldapTemplate.search(
                "ou=people",
                "(objectClass=inetOrgPerson)",
                controls,
                (ContextMapper<PersonRow>) context -> {
                    DirContextOperations entry =
                            (DirContextOperations) context;

                    return new PersonRow(
                            entry.getDn().toString(),
                            entry.getStringAttribute("uid"),
                            entry.getStringAttribute("cn"),
                            entry.getStringAttribute("mail"));
                },
                processor);

        VirtualListViewResultsCookie cookie = processor.getCookie();
        if (cookie == null) {
            throw new IllegalStateException(
                    "VLV response metadata is unavailable");
        }

        return new VlvWindow(
                List.copyOf(rows),
                cookie.getTargetPosition(),
                cookie.getContentCount(),
                cookie);
    }
}
~~~

**Điều kiện để chạy:** ứng dụng đã cung cấp bean `LdapTemplate` sử dụng `ContextSource` hợp lệ; server thật sự hỗ trợ hai control; phiên bản Spring LDAP chứa các class trên; schema cho phép đọc/sort thuộc tính `cn`; ACL/TLS/limit của server phù hợp.

Giải thích:

1. `SearchControls.SUBTREE_SCOPE` tìm trong cả subtree của `ou=people`.
2. `setReturningAttributes(...)` chỉ tải những field cần để hiển thị; `mail` có thể không có nên mapper cho phép `null`.
3. Filter cố định chọn người dùng theo `objectClass`. Với filter động, dùng `LdapQueryBuilder` hoặc filter builder để escape dữ liệu thay vì nối text.
4. Aggregate processor **gửi Sort và VLV cùng nhau**, không cần người viết tự mã hóa BER của VLV control.
5. `cookie.getContentCount()` là **giá trị được server báo trong response**, không phải số lượng chính xác bảo đảm cho mọi thời điểm.
6. `entry.getDn()` là DN trong ngữ cảnh Spring LDAP; phải hiểu base của `ContextSource` trước khi dùng làm định danh ở hệ thống khác.
7. Trong ví dụ, server chịu trách nhiệm chọn cửa sổ và sắp xếp; mapper chỉ chuyển entry được trả về thành DTO.

**Điểm cần điều chỉnh cho production:** mã trên minh họa happy path và việc có cookie không thay thế kiểm tra trạng thái sort/VLV. Với triển khai thực tế, cần phát hiện và phân loại response control lỗi, điều kiện unsupported, timeout, cookie không hợp lệ, trạng thái 0 entry và server-side limits. Không đưa `VirtualListViewResultsCookie` thô vào JSON cho frontend; quản lý nó ở tầng backend với quyền và thời hạn phù hợp.
## 9. Chuyển sang cửa sổ tiếp theo và dùng metadata của server

Với API Spring LDAP được trình bày ở mục 8, aggregate processor còn có constructor nhận:

~~~java
new VirtualListViewControlAggregateDirContextProcessor(
        sortKey, pageSize, targetOffset, listSize, previousCookie);
~~~

Ví dụ user muốn chuyển tới vị trí **21** trong danh sách đã sắp `cn`, với `pageSize=20` và kết quả cửa sổ trước đó được lưu trong `previous`:

~~~java
// Phương thức thêm vào PersonDirectoryBrowser ở mục 8.
public VlvWindow windowAt(int targetOffset, VlvWindow previous) {
    final int pageSize = 20;

    if (targetOffset < 1 || targetOffset > 100_000) {
        throw new IllegalArgumentException("Invalid VLV offset");
    }
    if (previous == null || previous.cookie() == null) {
        throw new IllegalArgumentException(
                "A valid previous VLV context is required");
    }

    SearchControls controls = new SearchControls();
    controls.setSearchScope(SearchControls.SUBTREE_SCOPE);
    controls.setReturningAttributes(new String[]{"uid", "cn", "mail"});
    controls.setTimeLimit(3000);

    VirtualListViewControlAggregateDirContextProcessor processor =
            new VirtualListViewControlAggregateDirContextProcessor(
                    "cn",
                    pageSize,
                    targetOffset,
                    previous.reportedContentCount(),
                    previous.cookie());

    List<PersonRow> rows = ldapTemplate.search(
            "ou=people",
            "(objectClass=inetOrgPerson)",
            controls,
            (ContextMapper<PersonRow>) context -> {
                DirContextOperations entry =
                        (DirContextOperations) context;
                return new PersonRow(
                        entry.getDn().toString(),
                        entry.getStringAttribute("uid"),
                        entry.getStringAttribute("cn"),
                        entry.getStringAttribute("mail"));
            },
            processor);

    VirtualListViewResultsCookie next = processor.getCookie();
    if (next == null) {
        throw new IllegalStateException("Missing VLV response");
    }
    return new VlvWindow(
            List.copyOf(rows),
            next.getTargetPosition(),
            next.getContentCount(),
            next);
}
~~~

Đoạn này minh họa **chỉ một lượt tiếp theo**; `previous` ở đây là kết quả của cùng bộ base/filter/sort và danh tính truy vấn. Trong thực tế cần kiểm tra trạng thái VLV/SSS, khả năng cookie đã hết hiệu lực và tính hợp lệ của metadata trước khi điều hướng.

Những nguyên tắc quan trọng khi sử dụng đoạn mã:

- `targetOffset` là vị trí **1-based**; với 20 entry một cửa sổ, các vị trí bắt đầu lý tưởng lần lượt là `1`, `21`, `41`.
- `listSize` là thông tin `contentCount` từ response trước, **không tự lấy `rows.size()` làm tổng danh sách**.
- `previous.cookie()` là wrapper của server context ID và metadata, **không phải** cookie của HTTP browser.
- Các thuộc tính trong projection, filter, scope và sort phải tương thích với phiên duyệt; không dùng cookie của `ou=people` cho `ou=groups`.
- Giới hạn offset tại API để tránh yêu cầu phi lý hoặc gây tải không cần thiết; giá trị 100.000 là **chính sách minh họa**, không phải giới hạn của giao thức.
- Nếu server thay đổi danh sách hoặc cookie không còn hợp lệ, ứng dụng cần cơ chế **tạo lại lượt duyệt**, thông báo UI hoặc chọn cách phân trang khác.

### Nếu UI muốn nhảy tới trang rất xa

VLV cho phép thể hiện mong muốn chọn vùng ở một vị trí cụ thể mà không nhất thiết phải lấy tất cả các trang trước đó. Tuy vậy, điều này **không đồng nghĩa độ phức tạp O(1)** hay chi phí không đổi: server có thể phải lọc/sắp xếp tập kết quả hoặc dùng index đã xây dựng.

Một số server chỉ hỗ trợ tốt VLV khi sort key và search filter được index phù hợp; với truy vấn rất rộng, việc nhảy xa có thể bị từ chối vì size/time/admin limit.

## 10. Đảm bảo thứ tự nhất quán: sort key, matching rule và index

VLV chỉ có ý nghĩa khi server tạo thứ tự sắp xếp tương đối ổn định. Với tên người dùng, hai entry có thể có cùng `cn`:

~~~ldif
dn: uid=an,ou=people,dc=example,dc=org
cn: Nguyen Van An
uid: an

dn: uid=an.hr,ou=people,dc=example,dc=org
cn: Nguyen Van An
uid: an.hr
~~~

Nếu sort chỉ theo `cn`, hai entry này **bằng nhau theo khóa sắp xếp**. Thứ tự giữa chúng có thể không được xác định rõ, dẫn tới hiện tượng một dòng nằm ở hai cửa sổ khác nhau hoặc bị bỏ qua khi dữ liệu thay đổi.

| Vấn đề | Hệ quả | Thiết kế phù hợp |
| --- | --- | --- |
| Sort key không duy nhất | Thứ tự giữa các entry cùng giá trị có thể không ổn định | Dùng khóa phụ hoặc khóa định danh ổn định khi API/server hỗ trợ |
| Sort key không có giá trị trên mọi entry | Vị trí không dễ dự đoán | Chọn filter/dữ liệu bảo đảm thuộc tính sort, hoặc có quy tắc thiếu giá trị |
| Schema/matching rule khác kỳ vọng | Chữ hoa/thường hoặc thứ tự ký tự có thể khác UI | Kiểm thử với schema/server đang vận hành |
| Sort không có index phù hợp | CPU/memory cao hoặc lỗi server limit | Trao đổi quản trị viên về index/sort configuration |
| Dữ liệu cập nhật trong khi duyệt | Offset bị dịch, có thể lặp/bỏ entry | Chấp nhận consistency phù hợp hoặc dùng cơ chế session/cookie do server hỗ trợ |
| Sắp xếp một trang ở Java | Không tạo thứ tự toàn cục | Dựa vào Server-Side Sort của cùng SearchRequest |

Spring LDAP aggregate processor nhận một `sortKey` dạng String; nếu nghiệp vụ yêu cầu **tie-breaker nhiều khóa**, phải xem khả năng của Server-Side Sort API/provider và cấu hình processor phù hợp. Không tự khẳng định một khóa `cn` luôn tạo tổng thứ tự duy nhất.

### VLV và phân quyền

Một server có thể không cho tài khoản bind đọc một số thuộc tính. Nếu ứng dụng sắp theo thuộc tính bị ACL che hoặc một thuộc tính nội bộ nhạy cảm, hành vi tìm kiếm có thể không giống khi dùng tài khoản quản trị.

Chỉ yêu cầu những thuộc tính cần hiển thị, nhưng vẫn phải bảo đảm sort key hợp lệ và có quyền sử dụng. Không tăng bind account lên toàn quyền chỉ để “cho VLV hoạt động”.

## 11. So sánh VLV với Simple Paged Results

Hai cơ chế này cùng giảm số entry trả về **mỗi lần**, nhưng không nên đánh đồng:

| Tiêu chí | Virtual List View + SSS | Simple Paged Results |
| --- | --- | --- |
| Trọng tâm | **Cửa sổ tại một vị trí** trong danh sách đã sắp | **Duyệt tiếp** qua các trang |
| Giao thức | VLV controls và Sort control | RFC 2696, OID `1.2.840.113556.1.4.319` |
| Có nhảy tới vị trí `1.001`? | Có thể, nếu server hỗ trợ và đủ điều kiện | Không được bảo đảm bằng cookie paging |
| Bắt buộc Server-Side Sort? | **Có** theo mô hình VLV | Không bắt buộc bởi RFC 2696, dù sort có thể cần cho UI |
| Metadata tổng số | `contentCount` của VLV, có thể là ước lượng | Cookie và thông tin kích thước nếu server cung cấp |
| Token trạng thái | VLV `contextID` | Paged Results cookie riêng |
| Phù hợp | LDAP directory browser, danh sách cuộn/nhảy vị trí | Đọc lần lượt, đồng bộ, batch processing |
| Khả năng server | Không phổ biến đồng nhất | Tương đối phổ biến hơn nhưng vẫn cần kiểm tra OID |
| Khả năng lặp/bỏ dữ liệu khi tập đổi | Có thể xảy ra | Cũng cần xét consistency khi dữ liệu đổi |

**Không truyền đồng thời VLV và Simple Paged Results một cách tùy tiện rồi mong chúng phối hợp chuẩn trên mọi server.** Tương tác giữa controls là khả năng theo triển khai và cần kiểm thử nếu hệ thống thực sự có yêu cầu đặc biệt.

Với tác vụ **xuất toàn bộ danh bạ hoặc đồng bộ dữ liệu**, thường nên cân nhắc Simple Paged Results, cơ chế đồng bộ LDAP chuyên dụng hoặc chiến lược khác thay cho VLV. Với UI chỉ xem 20 hàng quanh vị trí cụ thể trong tập đã sắp, VLV có thể phù hợp hơn.

## 12. Thiết kế fallback khi LDAP server không hỗ trợ VLV

Một hệ thống chạy được trên nhiều directory không nên phụ thuộc vào VLV như một tính năng luôn có. Ví dụ chiến lược:

~~~mermaid
flowchart TD
    A["API yêu cầu duyệt danh sách"] --> B["Kiểm tra capability đã cache"]
    B --> C{"Có VLV và SSS?"}
    C -->|Có| D["Thử search VLV + SSS trong phạm vi giới hạn"]
    D --> E{"Server xử lý thành công?"}
    E -->|Có| F["Trả VLV window + metadata"]
    E -->|Không| G["Phân loại lỗi, ghi telemetry"]
    C -->|Không| H["Chọn phương án phân trang khác"]
    G --> H
    H --> I{"Simple Paged Results hỗ trợ?"}
    I -->|Có| J["PagedResultsDirContextProcessor"]
    I -->|Không| K["Search bị giới hạn và không hứa random access"]
    J --> L["Trả cursor/next token"]
    K --> L
~~~

Một fallback tốt cần đảm bảo **không thay đổi ngữ nghĩa API âm thầm**:

1. Khi hỗ trợ VLV, UI có thể yêu cầu vị trí tùy ý.
2. Khi chỉ có Simple Paged Results, UI nên chuyển sang kiểu “Next/Previous” hoặc cursor; không giả vờ có thể nhảy thẳng tới trang 1000.
3. Khi không có cả hai, chỉ trả một tập nhỏ dưới base/filter hẹp và giới hạn rõ; không tải toàn bộ LDAP vào bộ nhớ.
4. Nếu request sử dụng **critical control** mà server không hỗ trợ, thường phải xử lý lỗi `unavailableCriticalExtension (12)` thay vì coi kết quả không phân trang là thành công.
5. Việc tự động fallback có thể cần giới hạn quyền, chi phí, thời gian và thông báo UI; không chạy lại một truy vấn toàn cây vô hạn.

### Phân biệt “không có VLV” với “VLV bị lỗi”

Một server có thể quảng bá cả hai OID nhưng vẫn không thực hiện được truy vấn cụ thể do index, quyền, schema, size/time limit hoặc control response không thành công. Không nên đánh dấu server “không hỗ trợ VLV” toàn cục ngay sau một request lỗi.

| Dạng vấn đề | Hướng xử lý |
| --- | --- |
| Root DSE không công bố VLV | Tránh VLV hoặc kiểm tra cấu hình/provider với quản trị viên |
| Thiếu SSS control | Sửa client để gửi Sort và VLV cùng lúc |
| Sort key không phù hợp | Chọn thuộc tính được server hỗ trợ, xem schema/index |
| VLV trả `offsetRangeError` | Sửa offset hoặc tải lại metadata danh sách |
| Cookie hết hạn/không hợp lệ | Tạo cửa sổ đầu mới theo filter/sort hiện hành |
| ACL bị từ chối | Giải quyết quyền theo chính sách, không tự tăng quyền service |
| Server busy/time limit | Thu hẹp base/filter, giảm tải, retry giới hạn theo loại lỗi |
| Unsupported critical control | Dùng phương án khác đã được thiết kế, hoặc báo unsupported |
| Kết quả thiếu/trùng khi dữ liệu đổi | Xem consistency và ổn định sort key trước khi quy lỗi cho mapper |

## 13. Những giới hạn quan trọng đối với tính nhất quán

VLV không tự tạo một snapshot giao dịch bất biến xuyên nhiều HTTP request.

Giả sử danh sách ban đầu (đã sắp):

~~~text
1  An
2  Binh
3  Chi
4  Dung
5  Ha
6  Lan
~~~

Người dùng xem cửa sổ đầu, rồi một tiến trình khác thêm entry `Bao` vào giữa. Danh sách mới:

~~~text
1  An
2  Bao
3  Binh
4  Chi
5  Dung
6  Ha
7  Lan
~~~

Nếu ứng dụng gọi cửa sổ tiếp theo bằng offset cũ mà không có cơ chế giữ context/consistency phù hợp, người dùng có thể thấy một entry bị lặp hoặc bỏ qua.

Các tác động cần dự kiến:

- **Thay đổi membership của filter:** entry mới có thể xuất hiện hoặc biến mất khỏi tập.
- **Thay đổi sort key:** một entry có thể chuyển từ vị trí này sang vị trí khác.
- **Replication lag:** hai backend khác nhau có thể thấy số lượng và thứ tự khác nhau.
- **Context cookie:** có thể giúp server giữ ngữ cảnh hoặc tối ưu việc duyệt, nhưng không tự bảo đảm snapshot nhất quán theo mọi thời điểm/server.
- **ACL thay đổi:** các entry được phép nhìn thấy có thể thay đổi, nên count và offset thay đổi theo.

Với nghiệp vụ **bắt buộc không bỏ sót, không lặp entry** như đồng bộ hoặc xuất dữ liệu kiểm toán, cần đánh giá một phương án dựa trên khóa bất biến và cơ chế đồng bộ/chụp dữ liệu thích hợp, thay vì coi VLV là transaction cursor.

## 14. Xử lý lỗi và giám sát vận hành

| Triệu chứng | Nguyên nhân có thể | Kiểm tra |
| --- | --- | --- |
| `unavailableCriticalExtension (12)` | Server không hỗ trợ control critical | `supportedControl` và endpoint thực |
| `sortControlMissing (60)` trong VLV response | Search không có sort control phù hợp | Gắn aggregate Sort + VLV, xem response |
| `offsetRangeError (61)` | Vị trí ngoài phạm vi hiệu lực | Chuyển offset 0-based → 1-based, cập nhật count |
| Sort response không thành công | Attribute/rule sort không hỗ trợ hoặc tài nguyên hạn chế | Sort key, schema, index và SSS result |
| Không có VLV cookie | Server không cung cấp hoặc processor không nhận được response hợp lệ | Phân tích response control, không giả định thành công |
| `timeLimitExceeded (3)` hoặc timeout | Sort/search quá rộng | Filter, base, indexing, time limit |
| `adminLimitExceeded (11)` | Vượt giới hạn vận hành server | Giảm phạm vi, trao đổi quản trị viên |
| `insufficientAccessRights (50)` | Bind account không có quyền | ACL, thuộc tính sort, search base |
| `noSuchObject (32)` | Search base không tồn tại | `ContextSource.base` và DN tương đối |
| Kết quả danh sách bất thường | Cookie cũ, trùng sort key, dữ liệu thay đổi hoặc replica khác | Target position, sort, identity và server |
| Lỗi TLS hoặc xác thực | Chứng chỉ, bind DN/secret, endpoint | Kiểm tra TLS/truststore, secret rotation, pooling |

### Nên đo những gì?

Một dịch vụ LDAP browser có thể theo dõi **chỉ số không nhạy cảm**:

- Latency của mỗi VLV search, tỉ lệ timeout và kết quả lỗi.
- Search base/scope ở mức danh mục an toàn, kích thước cửa sổ và sort key đã allowlist.
- Số lượng entry thực nhận so với cửa sổ yêu cầu.
- `targetPosition`, `contentCount` server báo và số lần reset cookie, khi không vi phạm chính sách dữ liệu.
- Tỉ lệ dùng VLV thành công và tỉ lệ chuyển fallback.
- LDAP endpoint/replica xử lý và phiên bản capability nếu có.

Không log **mật khẩu bind**, dữ liệu entry nhạy cảm, toàn bộ DN của nhân viên hoặc bytes của cookie trong log phổ thông. Với thông tin metadata có thể dùng để suy đoán quy mô tổ chức, cần chính sách hiển thị và audit phù hợp.

## 15. Bảo mật: VLV không vượt ACL và không hợp thức hóa truy vấn rộng

Spring LDAP lấy context từ `ContextSource`; với service bind đơn giản cần **LDAPS hoặc StartTLS được xác minh chứng chỉ**, đúng CA và hostname. Secret phải lấy từ nguồn được quản lý thay vì hardcode trong source code.

Các nguyên tắc:

1. **Least privilege:** tài khoản search chỉ được đọc OU/attributes cần thiết.
2. **Base hẹp:** tìm dưới `ou=people` thay vì toàn bộ naming context nếu UI chỉ cần nhân viên.
3. **Filter an toàn:** với input người dùng, dùng `LdapQueryBuilder`/filter builder; không ghép filter thô.
4. **Sort key allowlist:** không nhận tên attribute tùy ý từ request. Chỉ cho phép những trường đã được kiểm tra schema, index và quyền truy cập.
5. **Page size giới hạn:** đặt ngưỡng nhỏ hợp lý (ví dụ 20–100 tùy hệ thống), kiểm soát offset và tổng tài nguyên của request.
6. **Phân quyền API:** người được phép xem danh sách phải được xác định ở ứng dụng **và** LDAP ACL; VLV không biến thông tin nội bộ thành dữ liệu công khai.
7. **Cookie và dữ liệu trạng thái:** không để client sửa bytes contextID hoặc dùng cookie của một quyền truy cập khác.
8. **Timeout/pooling:** không trộn ngữ cảnh xác thực của người dùng khác; kiểm tra tính tương thích của controls, TLS và pooling theo provider.
9. **Không mặc định count công khai:** ngay cả việc hiển thị tổng số nhân viên cũng có thể cần quyền.

Một ứng dụng có thể giữ VLV cookie trong session server-side, cấp cho UI một mã tham chiếu ứng dụng ngắn hạn và ràng buộc mã này với user/filter/sort/base. Nếu frontend cần lưu cursor, phải thiết kế xác thực và kiểm soát quyền riêng; không coi contextID của LDAP là token bảo mật.

## 16. Kiểm thử: từ capability đến hành vi thật

Unit test có thể kiểm tra phép tính offset và cách service tạo processor, nhưng **không thể chứng minh server hỗ trợ VLV**. Cần integration test có LDAP server đã bật tính năng và index phù hợp.

### Unit test offset 1-based

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class VlvOffsetTest {
    static int startOffset(int zeroBasedPageIndex, int pageSize) {
        if (zeroBasedPageIndex < 0 || pageSize <= 0
                || pageSize > 100) {
            throw new IllegalArgumentException("Invalid page");
        }
        long offset = (long) zeroBasedPageIndex * pageSize + 1L;
        if (offset > Integer.MAX_VALUE) {
            throw new IllegalArgumentException("Offset overflow");
        }
        return (int) offset;
    }

    @Test
    void firstPageStartsAtOne() {
        assertEquals(1, startOffset(0, 20));
    }

    @Test
    void thirdPageStartsAtFortyOne() {
        assertEquals(41, startOffset(2, 20));
    }

    @Test
    void rejectsInvalidPageSize() {
        assertThrows(IllegalArgumentException.class,
                () -> startOffset(3, 0));
    }
}
~~~

Đây chỉ là kiểm thử chuyển đổi chỉ số của ứng dụng sang VLV target offset, không tạo VLV control và không kết nối LDAP.

### Unit test metadata wrapper

Spring LDAP cung cấp `VirtualListViewResultsCookie` với các thành phần context cookie, target position và content count:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertArrayEquals;

import org.junit.jupiter.api.Test;
import org.springframework.ldap.control.VirtualListViewResultsCookie;

class VlvCookieTest {
    @Test
    void keepsServerMetadata() {
        byte[] opaque = new byte[]{0x01, 0x02, 0x03};
        VirtualListViewResultsCookie cookie =
                new VirtualListViewResultsCookie(opaque, 21, 1200);

        assertArrayEquals(opaque, cookie.getCookie());
        assertEquals(21, cookie.getTargetPosition());
        assertEquals(1200, cookie.getContentCount());
    }
}
~~~

Test này xác nhận thao tác với wrapper, **không chứng minh 1200 là số entry thực tế**. Context cookie trong ví dụ chỉ là byte giả lập; ứng dụng không được tự tạo cookie để gửi cho server như thể nó đã được cấp.

### Kịch bản integration test cần có

Chuẩn bị một LDAP lab có:

- Ít nhất vài chục hoặc vài trăm entry `inetOrgPerson` trong `ou=people`.
- Một số entry có cùng `cn` để kiểm tra tính ổn định sort.
- Các UID và CN dễ quan sát thứ tự; tránh dữ liệu cá nhân thật.
- Tài khoản read-only có quyền search thuộc tính `uid`, `cn` theo chính sách.
- VLV và SSS control được server hỗ trợ, với cấu hình index/sort phù hợp.

| Kịch bản | Kết quả cần xác nhận |
| --- | --- |
| Root DSE công bố VLV và SSS | Hai OID được nhận diện chính xác |
| Cửa sổ đầu 20 entry | Trả cửa sổ đúng kích thước khả thi và metadata có thể đọc |
| Cửa sổ bắt đầu ở 21 | Không bị lỗi off-by-one; xác minh vị trí theo response |
| Offset nằm gần cuối danh sách | Không trả số entry vượt quá thực tế hoặc giả định luôn đủ 20 |
| Offset vượt giới hạn | Xử lý `offsetRangeError`/hành vi server rõ ràng |
| Thiếu sort control | Quan sát cách server từ chối hoặc báo thiếu sort |
| Sort key không được hỗ trợ | Không coi kết quả không sắp là VLV hợp lệ |
| Server không hỗ trợ VLV | Fallback hoạt động, không tải toàn bộ entry |
| Cookie bị thay/không hợp lệ | Có quy trình reset; không reuse bừa qua filter khác |
| Hai người dùng có ACL khác nhau | Không lẫn kết quả/cookie giữa danh tính |
| Dữ liệu đổi giữa hai lượt | Ghi nhận khả năng lặp/bỏ và phương án xử lý |
| Truy vấn rộng gây limit | Xử lý size/time/admin limit, không tăng quyền |
| LDAP backend khác nhau | Kiểm tra capabilities và cookie compatibility |

Đừng kiểm thử bằng cách đột ngột tải toàn bộ DIT production. Server-side sort và VLV trên dữ liệu lớn có thể tiêu tốn tài nguyên dù mỗi response chứa ít entry.

## 17. Bài thực hành: xây giao diện LDAP browser có thể fallback

Hệ thống nhân sự có 50.000 hồ sơ trong `ou=people`. Màn hình web hiển thị 25 người mỗi lần, sắp xếp theo một thuộc tính tên và hỗ trợ chuyển tới trang bất kỳ nếu hạ tầng cho phép. Ứng dụng dùng Spring LDAP với `ContextSource.base=dc=example,dc=org`.

### Nhiệm vụ

1. Liệt kê **hai OID request** mà server cần hỗ trợ để dùng VLV theo mô hình truyền thống.
2. Giải thích vì sao chỉ bật VLV control nhưng không có Server-Side Sort là sai.
3. Nếu UI đánh số trang từ 0, trang thứ 4 (`pageIndex=3`) với `pageSize=25` bắt đầu ở VLV target offset nào?
4. `contentCount=50000` trong response có phải cam kết mọi request sau vẫn thấy đúng 50.000 entry không?
5. `contextID` có thể được gửi lại với filter khác hoặc server khác tùy tiện không?
6. Dùng class nào của Spring LDAP để gộp VLV và SSS?
7. Nếu Root DSE chỉ có `1.2.840.113556.1.4.319` và không có VLV OID, giao diện nên làm gì?
8. Tại sao `cn` không duy nhất có thể khiến trải nghiệm cuộn thiếu ổn định?
9. Nếu người dùng nhập từ khóa, nên nối thẳng vào chuỗi `(cn=*...*)` hay dùng builder an toàn?
10. Nếu app nhận được một danh sách nhưng response control báo VLV thất bại, có được coi là thành công không?

### Đáp án và giải thích

| Câu | Đáp án |
| --- | --- |
| 1 | VLV `2.16.840.1.113730.3.4.9` và SSS `1.2.840.113556.1.4.473` |
| 2 | Không có thứ tự toàn cục đáng tin cho vị trí VLV; server có thể trả `sortControlMissing` |
| 3 | `3 * 25 + 1 = 76`, do offset VLV 1-based |
| 4 | Không. Đây là metadata theo lần xử lý của server; tập kết quả có thể đổi và count có thể được ước lượng |
| 5 | Không. Cookie opaque gắn với ngữ cảnh request/server theo quy tắc của provider |
| 6 | `VirtualListViewControlAggregateDirContextProcessor` |
| 7 | Cân nhắc `PagedResultsDirContextProcessor` và UI cursor/next; không hứa random access |
| 8 | Các entry trùng khóa sort có thể đổi thứ tự giữa các cửa sổ; cần khóa phụ/khóa ổn định |
| 9 | Dùng `LdapQueryBuilder`/filter builder, kiểm soát wildcard, base, scope và trường được phép |
| 10 | Không. Phải kiểm tra kết quả sort/VLV, xử lý lỗi hoặc fallback đúng hợp đồng |

### Bài tập thiết kế fallback

Điền hành vi tương ứng:

~~~text
Kết quả kiểm tra capability:
A. Có VLV + SSS
B. Có Paged Results nhưng không có VLV
C. Không có hai cơ chế trên

Yêu cầu:
- Tính năng nào được bật?
- UI có được nhảy tới trang tùy ý không?
- Có giới hạn gì để tránh tải quá mức?
~~~

Gợi ý:

- **A:** thử VLV với filter/sort/index đã kiểm tra; bật nhảy vị trí khi query thực sự thành công.
- **B:** dùng Simple Paged Results với cursor; UI chủ yếu duyệt tuần tự.
- **C:** giới hạn search hẹp, cảnh báo tính năng duyệt danh sách lớn không được hỗ trợ; không kéo tất cả entry về rồi “phân trang giả”.

## 18. Checklist đưa VLV vào sản phẩm

- [ ] Xác định nhu cầu **random-access theo vị trí** có thực sự cần thiết không.
- [ ] Kiểm tra Root DSE của **đúng LDAP endpoint**, gồm VLV OID và SSS OID.
- [ ] Xác minh server/index/ACL thực sự xử lý VLV cho filter, base và sort key đã chọn.
- [ ] Dùng `VirtualListViewControlAggregateDirContextProcessor` để gắn cả VLV lẫn Sort.
- [ ] Chỉ gửi filter an toàn, sort key từ allowlist, search base/scope được giới hạn.
- [ ] Chuyển UI offset 0-based sang VLV target offset 1-based và kiểm tra overflow.
- [ ] Không xem `contentCount` là tổng chính xác bất biến hoặc cookie là snapshot bảo đảm.
- [ ] Quản lý cookie ở backend, ràng buộc với query và danh tính; xử lý cookie hết hiệu lực.
- [ ] Kiểm tra response controls và lỗi, không coi sự tồn tại của `List` là thành công.
- [ ] Có fallback sang Simple Paged Results hoặc search giới hạn, và phản ánh đúng khả năng UI.
- [ ] Theo dõi timeout, index, search cost, admin limits và năng lực server khi tải lớn.
- [ ] Bảo vệ kết nối bằng LDAPS/StartTLS, xác minh chứng chỉ, giữ secret an toàn.
- [ ] Unit test offset/cookie logic; integration test VLV/SSS, unsupported và thay đổi dữ liệu trên LDAP lab.

## 19. Những điểm cần nhớ

- **Virtual List View** giúp yêu cầu **cửa sổ quanh một vị trí hoặc giá trị** trong tập kết quả **đã sắp xếp phía server**; không phải LDAP filter hay cơ chế cắt danh sách trong Java.
- **Server-Side Sort là thành phần đi kèm quan trọng** của VLV. Client cần cả control VLV lẫn SSS; server phải hỗ trợ **thực sự**, không chỉ về mặt cú pháp.
- **Khám phá khả năng ở Root DSE qua `supportedControl`** và thử với directory lab. Spring LDAP có processor VLV và aggregate processor, nhưng dependency Java không thể bật tính năng bị tắt ở server.
- **Offset VLV là 1-based; `contentCount` và `contextID` là metadata từ server**, không phải bảo đảm số lượng bất biến hoặc token dùng được giữa mọi server/truy vấn.
- **VLV khác RFC 2696 Simple Paged Results**: VLV hướng tới vị trí trong danh sách đã sort, còn paging thường hướng tới duyệt tiếp bằng cookie.
- **Schema, matching rule, index, ACL, sort-key uniqueness và dữ liệu thay đổi** đều ảnh hưởng kết quả. Cửa sổ ít entry không chứng minh server xử lý rẻ.
- Luôn có **fallback an toàn, giới hạn tài nguyên, TLS và kiểm thử tích hợp** trước khi bật VLV cho giao diện production.

### Tài liệu tham khảo

- [Spring LDAP — Javadoc package `org.springframework.ldap.control`](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/control/package-summary.html)
- [Spring LDAP — VirtualListViewControlAggregateDirContextProcessor](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/control/VirtualListViewControlAggregateDirContextProcessor.html)
- [Spring LDAP — VirtualListViewResultsCookie](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/control/VirtualListViewResultsCookie.html)
- [Spring LDAP — Processing the DirContext](https://docs.spring.io/spring-ldap/reference/processing-the-dircontext.html)
- [IETF Internet-Draft — LDAP Extensions for Scrolling View Browsing of Search Results](https://datatracker.ietf.org/doc/html/draft-ietf-ldapext-ldapv3-vlv-09)
- [RFC 2891 — LDAP Control Extension for Server Side Sorting of Search Results](https://www.rfc-editor.org/rfc/rfc2891)
- [RFC 2696 — LDAP Control Extension for Simple Paged Results Manipulation](https://www.rfc-editor.org/rfc/rfc2696)
- [RFC 4512 — LDAP Directory Information Models, Root DSE](https://www.rfc-editor.org/rfc/rfc4512)
