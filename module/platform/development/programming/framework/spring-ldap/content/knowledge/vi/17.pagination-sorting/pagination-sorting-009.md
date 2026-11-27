# Kiểm thử thiếu, trùng hoặc thay đổi entry giữa các trang LDAP

Một chức năng duyệt danh bạ có thể lấy trang đầu gồm 50 nhân viên, sau đó tiếp tục trang thứ hai và thứ ba bằng LDAP Paged Results. Nếu trong thời gian đó người khác **thêm, xóa, đổi tên hoặc di chuyển entry**, liệu toàn bộ phiên duyệt có còn trả về mỗi người đúng một lần?

Câu trả lời là **không thể mặc định như vậy**. **RFC 2696** mô tả rằng một chuỗi kết quả phân trang có thể bị **lặp entry hoặc bỏ sót entry khi tập kết quả thay đổi** giữa các request. Cookie phân trang giúp server tiếp tục nơi đã dừng, nhưng **không tự bảo đảm snapshot bất biến**. Khi kết hợp với Server-Side Sorting, thay đổi thuộc tính sắp xếp hoặc khóa sort không duy nhất còn làm bài toán phức tạp hơn.

Bài thuộc chương **Phân trang và sorting** của **SPRING_LDAP**. Chúng ta sẽ thiết kế bộ kiểm thử phát hiện **entry thiếu, entry trùng, entry thay đổi khi duyệt**, triển khai một bộ thu thập kết quả với `LdapTemplate`, giữ cùng kết nối cho cookie, tạo các tình huống cạnh tranh có kiểm soát, phân biệt test thuần Java và test với LDAP server, và chọn cơ chế xử lý thích hợp theo mức độ nhất quán mà ứng dụng cần.

## 1. Bối cảnh: một lần quét LDAP gồm nhiều request

Giả sử LDAP server có thư mục:

~~~text
dc=example,dc=org
├── ou=people
│   ├── uid=an
│   ├── uid=binh
│   ├── uid=chi
│   ├── uid=dung
│   ├── uid=ha
│   ├── uid=lan
│   └── ... hàng nghìn entry
├── ou=groups
└── ou=services
~~~

Mỗi nhân viên có `objectClass=inetOrgPerson`, `uid`, `cn` và một định danh nội bộ được ứng dụng kiểm soát, ví dụ `employeeNumber`.

Ứng dụng muốn liệt kê tất cả nhân viên dưới `ou=people,dc=example,dc=org`. Nếu có 6 entry và kích thước trang là 3, một chuỗi lý tưởng khi dữ liệu **không thay đổi** sẽ là:

~~~text
Tập dữ liệu ổn định, sắp theo khóa đã kiểm chứng:
[An, Binh, Chi, Dung, Ha, Lan]

Trang 1: [An, Binh, Chi]       cookie C1
Trang 2: [Dung, Ha, Lan]      cookie rỗng
Kết quả tổng hợp: 6 entry, không trùng, không thiếu
~~~

Để một phép quét thành công về mặt kỹ thuật, không chỉ cần “API trả danh sách”:

| Thành phần | Cần xác nhận |
| --- | --- |
| Search base | Đúng nhánh `ou=people` tương đối với `ContextSource.base` |
| Search scope | `SUBTREE_SCOPE` hay `ONELEVEL_SCOPE` theo yêu cầu |
| Filter | Chọn đúng tập, ví dụ `(objectClass=inetOrgPerson)` |
| Projection | Đã yêu cầu **ID để kiểm tra trùng** và các thuộc tính cần đọc |
| Sort | Server hỗ trợ control sắp xếp, rule và khóa phù hợp |
| Cookie | Dùng đúng cookie mới nhất cho cùng chuỗi request |
| Kết nối | Chuỗi paging dùng cùng underlying connection theo yêu cầu client/server |
| Dữ liệu | Tập entry có thay đổi trong lúc duyệt hay không |
| Kết quả test | Kiểm tra ID trùng, ID thiếu, giá trị thay đổi, lỗi control |

Một trang trả đủ 3 entry **không** chứng minh toàn bộ quá trình không trùng hoặc không sót.

## 2. Phân trang LDAP theo RFC 2696 bảo đảm điều gì?

**Simple Paged Results Control**, OID `1.2.840.113556.1.4.319`, cho phép client yêu cầu server trả kết quả tìm kiếm thành nhiều phần nhỏ.

~~~mermaid
sequenceDiagram
    participant App as Spring LDAP service
    participant LDAP as LDAP server
    App->>LDAP: Search + PagedResults(pageSize=3, cookie="")
    LDAP-->>App: An, Binh, Chi + cookie C1
    App->>LDAP: Search giống trước + cookie C1
    LDAP-->>App: Dung, Ha, Lan + cookie rỗng
    App->>App: Hết trang; kiểm tra ID và tổng hợp
~~~

Các quy tắc cốt lõi của RFC 2696:

1. Request đầu dùng **cookie rỗng** và kích thước trang được chọn.
2. Server trả một trang cùng cookie opaque khi còn kết quả; **cookie rỗng** khi không còn.
3. Request tiếp phải giữ các thành phần tìm kiếm giống request đầu, ngoại trừ message ID, cookie và kích thước trang nếu có thay đổi được cho phép.
4. Client phải dùng **cookie từ response mới nhất**, không dùng lại cookie cũ tùy tiện.
5. Khi chuỗi đã hết, cookie không còn giá trị; không được tái sử dụng để “đi về trang trước”.
6. Giá trị tổng số do server trả về có thể chỉ là **ước lượng** hoặc `0` nếu không biết.
7. **Khi tập kết quả thay đổi từ lúc bắt đầu**, client có thể nhận **một entry nhiều lần hoặc không nhận đủ các entry**.

Điều cuối cùng rất quan trọng: đây là đặc điểm được giao thức thừa nhận, **không phải bằng chứng Spring LDAP triển khai sai**.

### “Phân trang” không đồng nghĩa “snapshot”

| Cơ chế | Cung cấp | Không mặc định cung cấp |
| --- | --- | --- |
| RFC 2696 paging | Trả từng phần, cookie tiếp tục | Snapshot giao dịch bất biến, random access |
| Server-Side Sort (RFC 2891) | Server sắp kết quả theo khóa đã yêu cầu | Ổn định thứ tự khi entry thay đổi hay khóa bị trùng |
| VLV | Cửa sổ ở vị trí trong danh sách đã sort nếu server hỗ trợ | Bảo đảm không đổi, phân trang tuần tự kiểu RFC 2696 |
| `LdapTemplate.search(...)` | Gọi LDAP và ánh xạ kết quả | Khóa dữ liệu toàn thư mục qua nhiều request |
| Dedupe theo ID | Không xử lý cùng ID hai lần ở tầng ứng dụng | Tự tìm được entry **đã bị bỏ sót** |

**Không suy từ việc server trả một cookie hợp lệ rằng server đã khóa tập dữ liệu.** Một số server có thể có cơ chế giữ trạng thái đặc biệt, nhưng chỉ được dựa vào nó nếu được tài liệu nhà cung cấp xác nhận và kiểm thử.

## 3. Ba loại vấn đề phải phân biệt khi viết test

| Vấn đề | Triệu chứng | Dữ liệu cần quan sát |
| --- | --- | --- |
| **Trùng entry giữa trang** | Cùng một entry xuất hiện ở trang 1 và trang 2 | ID ổn định và danh sách số trang của ID đó |
| **Thiếu entry** | Entry thuộc tập mong đợi nhưng không xuất hiện ở bất cứ trang nào | **Tập ID kỳ vọng** từ fixture/snapshot độc lập |
| **Entry thay đổi** | Cùng ID nhưng `cn`, `uid`, OU hoặc trạng thái khác | ID bất biến, giá trị trước/sau, thời điểm thay đổi |

### Chọn khóa nhận diện đúng

Trong LDAP, **DN không nhất thiết bất biến**: rename/move làm DN thay đổi. Một `uid` cũng có thể được đổi tên hoặc không duy nhất trong toàn bộ DIT nếu ứng dụng không áp ràng buộc.

Vì vậy:

- Với test **không rename/move**, DN có thể làm khóa tạm để xác minh trùng.
- Với test **có rename/move**, cần ID ổn định hơn: `entryUUID` (nếu directory hỗ trợ/cho đọc), `objectGUID` của hệ thống phù hợp, hoặc **ID nghiệp vụ bất biến** được cấp phát và kiểm soát tính duy nhất.
- Giá trị `objectGUID` có thể là dữ liệu nhị phân; không ép trực tiếp bằng `(String) attrs.get("objectGUID").get()`.
- `employeeNumber` trong ví dụ **chỉ** được coi là ID ổn định khi fixture hoặc hệ thống có cơ chế bảo đảm duy nhất/bất biến; tên attribute tự nó không cung cấp bảo đảm.

Nếu test dùng `uid` làm ID rồi đổi `uid` giữa hai trang, nó có thể báo “entry cũ bị mất, entry mới xuất hiện” dù vẫn là **một đối tượng LDAP**. Đó là cách đo sai danh tính, không chứng minh server đã nhân đôi entry.

## 4. Cách trùng hoặc thiếu xảy ra khi dữ liệu thay đổi

Các ví dụ sau dùng **mô hình chia lát theo vị trí** để giải thích nguy cơ, không phải cam kết rằng mọi server xử lý RFC 2696 theo đúng thuật toán offset này. Server có thể lưu cursor/state riêng, và hành vi cụ thể khi dữ liệu đổi cần integration test.

### Tình huống A — thêm entry trước ranh giới trang

Ban đầu, danh sách đã sắp:

~~~text
[An, Chi, Dung, Ha, Lan, Minh]
Trang 1 (3): [An, Chi, Dung]
~~~

Giữa hai lần lấy trang, có thêm `Binh`:

~~~text
Tập hiện tại: [An, Binh, Chi, Dung, Ha, Lan, Minh]
Nếu server tiếp tục theo vị trí của tập mới:
Trang 2: [Dung, Ha, Lan]
                  ^^^^
Dung đã có trong trang 1 → TRÙNG
~~~

Kết quả phụ thuộc cơ chế cursor/server; ví dụ cho thấy **tại sao không thể lấy sort order động làm snapshot bất biến**.

### Tình huống B — xóa entry trước ranh giới

Ban đầu:

~~~text
[An, Binh, Chi, Dung, Ha, Lan]
Trang 1 (3): [An, Binh, Chi]
~~~

Một tác nhân xóa `Binh` trước khi trang 2 được lấy:

~~~text
Tập hiện tại: [An, Chi, Dung, Ha, Lan]
Nếu tiếp tục từ vị trí thứ 4 của danh sách mới:
Trang 2: [Ha, Lan]
         ^^^
Dung có thể bị BỎ SÓT
~~~

Nếu test lấy **tập kỳ vọng ban đầu**, `Binh` vẫn được thấy ở trang 1 dù nó đã bị xóa sau đó. Cần ghi rõ “kỳ vọng theo thời điểm nào”; nếu không, bài test có thể vừa báo mất entry đã xóa vừa báo thừa entry đã nhìn thấy.

### Tình huống C — đổi thuộc tính sort

Ban đầu:

~~~text
Sort theo cn:
[An, Binh, Chi, Dung, Ha, Lan]
Trang 1: [An, Binh, Chi]
~~~

Giữa hai trang, người dùng `Lan` được đổi `cn` thành `Bao`. Entry ấy có thể chuyển lên **trước** ranh giới của trang đầu; nếu server tiếp tục dựa trên danh sách mới, entry có thể **không xuất hiện trong những trang còn lại**.

Ngược lại, đổi `cn` của entry đã xem từ `An` thành `Zan` có thể khiến nó xuất hiện thêm lần nữa ở vùng trang sau.

**Vì thế:** test thay đổi sort key cần lưu **ID bất biến** và ghi nhận cả giá trị `cn` trước/sau.

### Tình huống D — move hoặc rename entry

Một entry chuyển:

~~~text
DN cũ: uid=chi,ou=people,dc=example,dc=org
DN mới: uid=chi,ou=contractors,dc=example,dc=org
~~~

Nếu search base là `ou=people`, entry này rời **tập kết quả của filter/scope**. Nếu search base là `dc=example,dc=org` với `SUBTREE_SCOPE`, entry có thể vẫn thuộc tập nhưng DN đã đổi.

Không dùng so sánh DN thuần để khẳng định đó là hai người khác nhau. Đồng thời, không mặc định việc giữ old RDN attribute value khi rename làm DN cũ còn truy cập được.

## 5. Sorting: thiếu khóa ổn định có thể gây sai lệch ngay cả khi không ghi dữ liệu

Trong một ứng dụng hiển thị danh sách người, sort theo `cn` thường không tạo thứ tự duy nhất:

~~~ldif
dn: uid=an1,ou=people,dc=example,dc=org
cn: Nguyen Van An
uid: an1

dn: uid=an2,ou=people,dc=example,dc=org
cn: Nguyen Van An
uid: an2
~~~

Hai entry có **cùng khóa sắp xếp**. Nếu server không quy định thứ tự phụ ổn định, vị trí tương đối của chúng có thể không được bảo đảm qua các lần search. Vì vậy, bài kiểm thử phải bao gồm:

- Nhiều entry có **cùng `cn`**.
- Các tên có hoa/thường hoặc Unicode theo matching rule thật của server.
- Entry thiếu thuộc tính sắp xếp (nếu schema/ACL cho phép).
- Một attribute sort có nhiều giá trị, nếu server hỗ trợ và quy tắc chưa rõ.
- Trường hợp server từ chối sort request hoặc không trả sort response hợp lệ.

### Server-Side Sorting không phải `Collections.sort(...)`

LDAP Server-Side Sort request dùng OID `1.2.840.113556.1.4.473` và response OID `1.2.840.113556.1.4.474`, được mô tả trong **RFC 2891**.

Nếu code chỉ lấy từng trang rồi sắp trong Java, nó **không sắp toàn bộ tập kết quả trước khi chia trang**. Như vậy một entry ở trang sau có thể có khóa sắp nhỏ hơn một entry ở trang trước.

~~~text
Sai: lấy P1 rồi sort P1; lấy P2 rồi sort P2
Đúng theo mục tiêu: LDAP server sort toàn tập rồi mới chọn trang
~~~

Nhưng Sort control cũng **không đóng băng toàn bộ thư mục**. Ngay cả khi server xác nhận sort thành công, một tập kết quả đã thay đổi vẫn có thể khiến các trang tiếp theo không còn phản ánh cùng một thời điểm.

Nếu API/server hỗ trợ nhiều sort key, cân nhắc khóa phụ ổn định và duy nhất theo chính sách. Nếu chỉ hỗ trợ một khóa trong processor đang dùng, phải ghi rõ giới hạn này, không tự giả định sắp `cn` luôn tạo tổng thứ tự ổn định.

## 6. Cookie và kết nối: điều kiện phải kiểm thử riêng

RFC 2696 yêu cầu client coi cookie là **opaque**. Nó có thể chứa trạng thái do server tự quản lý; client không được parse, sửa, đoán cấu trúc hoặc tái dùng cookie từ response cũ.

Trong Spring LDAP, tài liệu `PagedResultsDirContextProcessor`/paging hiện đại nêu thêm một điều kiện thực thi quan trọng: **các request thuộc cùng chuỗi paging cần sử dụng cùng underlying LDAP connection**. `LdapTemplate` thường đóng context sau mỗi lời gọi search; nếu ứng dụng vô tình đổi kết nối, cookie có thể không tiếp tục được.

Spring LDAP có **`SingleContextSource.doWithSingleContext(...)`** và hỗ trợ qua `TransactionAwareContextSourceProxy`/`ContextSourceTransactionManager` để giúp duy trì context trong phạm vi thích hợp.

| Sai lầm | Hậu quả |
| --- | --- |
| Mỗi trang tạo một context/connection khác nhau | Cookie có thể không còn hợp lệ |
| Dùng cookie của trang 1 để gọi lại trang 3 | Trình tự paging không được bảo đảm |
| Thay filter/sort/base giữa các trang | Chuỗi query không còn tương thích |
| Đổi bind identity trong lúc duyệt | Quyền và tập kết quả có thể khác |
| Cookie cũ sau khi hết trang | Không được dùng để tiếp tục |
| Cookie bị lộ cho request khác | Rủi ro lẫn phiên truy vấn/dữ liệu |
| Pool cho request kế tiếp chạy trên backend khác | Có thể không tiếp tục được cookie cũ |

**Không sử dụng cookie phân trang như một HTTP access token.** Nếu trang web cần tiếp tục duyệt giữa nhiều request, session/server-side state phải được thiết kế rõ, ràng buộc với người dùng, truy vấn, quyền và lifecycle kết nối. Không nghĩ chỉ lưu cookie là có thể tái tạo cùng một snapshot vô thời hạn.

### Root DSE và capability

Có thể kiểm tra `supportedControl` của Root DSE tại **DN rỗng của server**:

~~~bash
ldapsearch -x -H "ldaps://ldap.example.org:636" \
  -s base -b "" supportedControl
~~~

Các OID nên kiểm tra:

| Cơ chế | OID |
| --- | --- |
| Simple Paged Results | `1.2.840.113556.1.4.319` |
| Server-Side Sort request | `1.2.840.113556.1.4.473` |
| Virtual List View request (nếu cần so sánh) | `2.16.840.1.113730.3.4.9` |

Root DSE không phải entry `dc=example,dc=org`. Chỉ thấy OID công bố khả năng, **chưa chứng minh** truy vấn cụ thể sẽ được phục vụ với mọi sort key/index/ACL và giới hạn server.

## 7. Spring LDAP: duyệt trang với cùng kết nối

Ví dụ sau sử dụng API **`PagedResultsControlExchangeDirContextProcessor`** có trong nhánh Spring LDAP mới (được giới thiệu ở 4.1), minh họa cơ chế trên cùng kết nối. Dự án dùng Spring LDAP 3.x/4.0 có thể sử dụng **`PagedResultsDirContextProcessor`** với `hasMore()` và `getCookie()`; lưu ý class cũ được đánh dấu deprecated ở API mới.

Fixture lab quy định `employeeNumber` là **ID duy nhất/bất biến**; ví dụ chỉ truy cập dữ liệu được phép đọc.

~~~java
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;

import javax.naming.directory.SearchControls;

import org.springframework.ldap.control.PagedResultsControlExchangeDirContextProcessor;
import org.springframework.ldap.core.ContextMapper;
import org.springframework.ldap.core.ContextSource;
import org.springframework.ldap.core.DirContextOperations;
import org.springframework.ldap.core.support.LdapOperationsCallback;
import org.springframework.ldap.core.support.SingleContextSource;

record EmployeeRow(String id, String dn, String commonName) {}

record ScanSummary(
        int pages,
        int received,
        Set<String> uniqueIds,
        List<String> duplicateIds) {}

public class PagingAuditService {

    private final ContextSource contextSource;

    public PagingAuditService(ContextSource contextSource) {
        this.contextSource = contextSource;
    }

    public ScanSummary scanLabPeople() {
        final int pageSize = 25;
        final int maxPages = 200;  // Bảo vệ môi trường test.
        final int maxRows = 5000;

        return SingleContextSource.doWithSingleContext(
                contextSource,
                (LdapOperationsCallback<ScanSummary>) operations -> {

            SearchControls controls = new SearchControls();
            controls.setSearchScope(SearchControls.SUBTREE_SCOPE);
            controls.setReturningAttributes(
                    new String[]{"employeeNumber", "cn"});
            controls.setTimeLimit(3000);

            PagedResultsControlExchangeDirContextProcessor paging =
                    new PagedResultsControlExchangeDirContextProcessor(
                            pageSize);

            Set<String> seen = new LinkedHashSet<>();
            List<String> duplicates = new ArrayList<>();
            int received = 0;
            int pages = 0;

            do {
                if (pages >= maxPages) {
                    throw new IllegalStateException("Too many pages");
                }

                List<EmployeeRow> page = operations.search(
                        "ou=people",
                        "(objectClass=inetOrgPerson)",
                        controls,
                        (ContextMapper<EmployeeRow>) context -> {
                            DirContextOperations entry =
                                    (DirContextOperations) context;
                            return new EmployeeRow(
                                    entry.getStringAttribute("employeeNumber"),
                                    entry.getDn().toString(),
                                    entry.getStringAttribute("cn"));
                        },
                        paging);

                pages++;
                received += page.size();

                if (received > maxRows) {
                    throw new IllegalStateException("Too many rows");
                }

                for (EmployeeRow row : page) {
                    if (row.id() == null || row.id().isBlank()) {
                        throw new IllegalStateException(
                                "Missing stable identity in LDAP result");
                    }
                    if (!seen.add(row.id())) {
                        duplicates.add(row.id());
                    }
                }
            } while (paging.hasMore());

            return new ScanSummary(
                    pages,
                    received,
                    Set.copyOf(seen),
                    List.copyOf(duplicates));
        });
    }
}
~~~

### Vì sao đoạn code dùng `SingleContextSource`?

Toàn bộ vòng `do/while` được thực thi trong một callback có **cùng underlying connection**; Spring LDAP đóng context đã bao bọc đúng lúc callback kết thúc. Việc tạo một processor paging cho chuỗi truy vấn và tái sử dụng nó qua các trang giúp giữ cookie mới nhất do server trả.

**Không chuyển processor hoặc context mutable sang singleton dùng chung giữa nhiều thread.** Mỗi phiên scan cần trạng thái riêng và phải giới hạn thời gian giữ kết nối.

### Mã trên kiểm tra được gì — và chưa kiểm tra được gì?

Nó xác nhận **ID đọc được từ các trang**, số trang, số hàng và ID xuất hiện hơn một lần. Nó **không** tự chứng minh không thiếu entry: muốn xác định thiếu phải biết **tập ID kỳ vọng**, điều không thể suy ra chỉ từ các trang nhận được.

Ngoài ra, ví dụ không gắn Sort control; vì vậy không thể tuyên bố các trang được **sắp theo `cn`**. Khi ứng dụng yêu cầu sorting, cần thêm **Server-Side Sort request** bằng API phù hợp với phiên bản Spring LDAP và xác minh response sort thành công; không dùng `seen` như một phép kiểm tra sort.

**Hạn chế phiên bản:** class `PagedResultsControlExchangeDirContextProcessor` có mặt từ Spring LDAP 4.1. Trong Spring LDAP 3.x/4.0, triển khai tương ứng bằng `PagedResultsDirContextProcessor` hoặc API tương đương; đối chiếu dependency của dự án thay vì copy import vào phiên bản không có class.

## 8. Test không trùng là cần thiết nhưng chưa đủ

Giả sử kết quả quét:

~~~text
Trang 1: [A, B, C]
Trang 2: [E, F]
Seen IDs = {A, B, C, E, F}
Duplicates = {}
~~~

Nếu test chỉ kiểm tra `duplicates.isEmpty()`, nó **PASS**. Nhưng nếu tập phải có `{A, B, C, D, E, F}`, entry **D đã bị bỏ sót**.

Để phát hiện cả **missing** và **unexpected**, cần so hai tập:

~~~text
expected = tập ID từ fixture/snapshot độc lập
actual   = tập ID xuất hiện qua mọi trang

missing    = expected - actual
unexpected = actual - expected
duplicates = những ID được quan sát > 1 lần
~~~

| Kết quả | Diễn giải |
| --- | --- |
| `missing = {}`, `unexpected = {}`, `duplicates = {}` | Đúng với tập kỳ vọng đã cho |
| `duplicates != {}` | Ít nhất một ID được trả nhiều lần |
| `missing != {}` | Có ID kỳ vọng không được thấy |
| `unexpected != {}` | Có ID chưa thuộc tập kỳ vọng, có thể do tạo thêm entry hoặc fixture không đồng nhất |
| `received != unique.size()` | Có trùng ID hoặc vi phạm giả định ID ổn định |
| Không đọc được ID bất biến | Không thể kết luận chắc chắn về danh tính xuyên rename |

Trong test **không có thay đổi**, `expected` được tạo từ bộ fixture do test tự nạp trước khi bắt đầu quét. Với test **có thay đổi**, phải ghi rõ snapshot ở thời điểm T0/T1 hoặc event log; nếu không, `expected` không đại diện cho một phiên bản dữ liệu nào rõ ràng.

### Vì sao so tổng số chưa đủ?

~~~text
expected.size() = 6
received = 6

Trang 1: [A, B, C]
Trang 2: [C, E, F]

Có 6 kết quả nhưng C lặp, D vắng.
~~~

Đếm `6 == 6` vẫn cho kết quả giả **thành công**. Cần so **tập ID** và đếm **mức độ xuất hiện** của từng ID.

## 9. Định nghĩa đúng mục tiêu consistency cho từng loại ứng dụng

| Ứng dụng | Mục tiêu phù hợp | Phương án |
| --- | --- | --- |
| UI danh bạ “Next” | Dữ liệu gần thời điểm hiện tại; chấp nhận thay đổi nhẹ | Paging + sort có kiểm tra, xử lý duplicate khi cần |
| Trang quản trị có chuyển vị trí | Cửa sổ đã sort và metadata hợp lệ | VLV + Server-Side Sort nếu server hỗ trợ |
| Đồng bộ nhân viên sang hệ thống ngoài | Không bỏ sót thay đổi quan trọng | Kết hợp phân trang với cơ chế change tracking/changelog phù hợp |
| Xuất dữ liệu phục vụ kiểm toán | Tập dữ liệu xác định theo thời điểm | Snapshot/export do server/hạ tầng hỗ trợ hoặc cơ chế nhất quán riêng |
| Batch update từng entry | Không xử lý một ID hai lần ngoài ý muốn | Dedupe, idempotency, checkpoint và version check |
| Tìm một người theo UID | Không cần quét toàn directory | Filter equality hẹp, search base phù hợp |

**Không nên nâng yêu cầu của một UI thông thường thành snapshot transaction nếu hạ tầng không hỗ trợ.** Nhưng với bài toán cần đủ mọi thay đổi, chỉ loại trùng ở phía Java là **không đủ**.
## 10. Bộ so sánh có thể unit test độc lập với LDAP

Trước khi tạo lỗi trên server thật, viết một bộ kiểm tra chỉ nhận **danh sách các trang chứa ID** và **tập ID kỳ vọng**. Bộ này không phụ thuộc LDAP, nên dễ tái hiện tình huống trùng, thiếu hoặc có ID ngoài tập.

~~~java
import java.util.ArrayList;
import java.util.HashSet;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;

record PageAudit(
        int received,
        Set<String> actual,
        Set<String> missing,
        Set<String> unexpected,
        List<String> duplicateIds) {

    boolean isExactMatch() {
        return missing.isEmpty()
                && unexpected.isEmpty()
                && duplicateIds.isEmpty();
    }
}

public final class PageAuditCalculator {

    private PageAuditCalculator() {}

    public static PageAudit compare(
            Set<String> expected,
            List<List<String>> pages) {

        Set<String> seen = new LinkedHashSet<>();
        List<String> duplicates = new ArrayList<>();
        int received = 0;

        for (List<String> page : pages) {
            for (String id : page) {
                if (id == null || id.isBlank()) {
                    throw new IllegalArgumentException("Invalid row ID");
                }
                received++;
                if (!seen.add(id)) {
                    duplicates.add(id);
                }
            }
        }

        Set<String> missing = new HashSet<>(expected);
        missing.removeAll(seen);

        Set<String> unexpected = new HashSet<>(seen);
        unexpected.removeAll(expected);

        return new PageAudit(
                received,
                Set.copyOf(seen),
                Set.copyOf(missing),
                Set.copyOf(unexpected),
                List.copyOf(duplicates));
    }
}
~~~

Ở đây, `duplicateIds` có thể chứa một ID nhiều lần nếu nó xuất hiện ba lần trở lên. Nếu nghiệp vụ muốn báo cáo mỗi ID trùng chỉ một lần, có thể chuyển danh sách sang một tập riêng trong tầng hiển thị. Không dùng việc loại trùng để **âm thầm** biến một scan thiếu dữ liệu thành PASS.

### JUnit 5: quét ổn định

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.List;
import java.util.Set;
import org.junit.jupiter.api.Test;

class PageAuditCalculatorTest {

    private static final Set<String> EXPECTED =
            Set.of("A", "B", "C", "D", "E", "F");

    @Test
    void stablePagesContainEveryIdExactlyOnce() {
        PageAudit result = PageAuditCalculator.compare(
                EXPECTED,
                List.of(
                        List.of("A", "B", "C"),
                        List.of("D", "E", "F")));

        assertTrue(result.isExactMatch());
        assertEquals(6, result.received());
        assertEquals(Set.of(), result.missing());
        assertEquals(List.of(), result.duplicateIds());
    }

    @Test
    void duplicateCanHideMissingWhenCountsLookCorrect() {
        PageAudit result = PageAuditCalculator.compare(
                EXPECTED,
                List.of(
                        List.of("A", "B", "C"),
                        List.of("C", "E", "F")));

        assertEquals(6, result.received()); // Count vẫn trùng!
        assertEquals(Set.of("D"), result.missing());
        assertEquals(List.of("C"), result.duplicateIds());
        assertFalse(result.isExactMatch());
    }

    @Test
    void detectsUnexpectedInsertion() {
        PageAudit result = PageAuditCalculator.compare(
                EXPECTED,
                List.of(
                        List.of("A", "B", "C"),
                        List.of("D", "E", "F", "G")));

        assertEquals(Set.of("G"), result.unexpected());
        assertFalse(result.isExactMatch());
    }

    @Test
    void missingEntryWithoutDuplicatesStillFails() {
        PageAudit result = PageAuditCalculator.compare(
                EXPECTED,
                List.of(
                        List.of("A", "B", "C"),
                        List.of("E", "F")));

        assertEquals(Set.of("D"), result.missing());
        assertTrue(result.duplicateIds().isEmpty());
    }
}
~~~

Những test trên **luôn có kết quả xác định** vì trang là dữ liệu giả lập. Chúng chứng minh **bộ phát hiện** hoạt động, không chứng minh server LDAP thực tế sẽ phát sinh cùng mẫu thiếu/trùng sau một thay đổi cụ thể.

## 11. Test trình tự trang với thay đổi được chèn giữa hai lần fetch

Một test đơn vị khác là mô phỏng nguồn trả trang. Ta chèn một “mutation” vào thời điểm **sau khi đã lấy trang 1, trước khi lấy trang 2**. Mục tiêu là kiểm tra thuật toán ứng dụng phản ứng đúng khi dữ liệu nguồn thay đổi.

~~~java
import java.util.List;
import java.util.Set;

public final class ScriptedPagingScenario {

    public static PageAudit simulateDuplicateAtBoundary() {
        Set<String> expectedAtStart =
                Set.of("An", "Chi", "Dung", "Ha", "Lan", "Minh");

        // Trang đầu trước khi Binh được thêm vào tập đã sort.
        List<String> first = List.of("An", "Chi", "Dung");

        // Mô phỏng thuật toán tiếp tục theo vị trí ở tập mới:
        // [An, Binh, Chi, Dung, Ha, Lan, Minh]
        List<String> second = List.of("Dung", "Ha", "Lan");
        List<String> third = List.of("Minh");

        return PageAuditCalculator.compare(
                expectedAtStart,
                List.of(first, second, third));
    }
}
~~~

Kỳ vọng từ bộ audit:

- `duplicateIds` có `Dung`.
- `unexpected` trống vì chỉ so các ID của tập T0, không đưa `Binh` vào các trang giả lập.
- Nếu so với tập T1, `Binh` sẽ là ID thiếu. Điều này minh họa rằng phải chọn **thời điểm snapshot kỳ vọng** trước khi kết luận thiếu.

### Thời điểm T0/T1 phải được ghi rõ

Một kịch bản kiểm thử đổi dữ liệu cần ít nhất hai trạng thái được biết:

~~~text
T0: Fixture trước khi bắt đầu scan
T1: Sau khi tác vụ ghi thực hiện thay đổi
T2: Sau khi toàn bộ trang đã được trả về
~~~

Nếu `expectedAtT0` khác `expectedAtT1`, hai phép so với kết quả scan có ý nghĩa khác nhau:

| So với tập nào? | Muốn trả lời câu hỏi gì? |
| --- | --- |
| `expectedAtT0` | Scan có phản ánh đủ những entry tồn tại lúc bắt đầu không? |
| `expectedAtT1` | Scan có phản ánh đủ những entry có ở thời điểm cập nhật không? |
| Snapshot được server bảo đảm | Scan có đọc đúng một phiên bản nhất quán không? |
| Không có snapshot/fixture độc lập | **Không thể khẳng định chính xác ID nào bị thiếu** chỉ từ dữ liệu đã nhận |

Với LDAP thường không có snapshot transaction mặc định xuyên nhiều page, yêu cầu “đúng toàn bộ tại T0” là một **mục tiêu kinh doanh cần cơ chế hỗ trợ bổ sung**, không phải lời hứa của Simple Paged Results.

## 12. Kịch bản integration test trên LDAP server thật

Cần một LDAP lab có quyền tạo, sửa, đổi tên và xóa **chỉ entry thử nghiệm**. Đừng dùng directory sản xuất.

### Chuẩn bị fixture có ID ổn định

Ví dụ dùng OU riêng `ou=paging-lab,dc=lab,dc=example,dc=org`, bên dưới tạo ít nhất 12 entry với ID bất biến:

~~~ldif
dn: uid=lab-001,ou=paging-lab,dc=lab,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: lab-001
cn: Employee 001
sn: Employee
employeeNumber: TEST-001
~~~

Tạo các entry tương tự với `employeeNumber: TEST-002` đến `TEST-012`, chỉ dùng dữ liệu giả. Các ID phải duy nhất theo quy ước fixture. Với `pageSize=3`, nếu dữ liệu không đổi, một chuỗi quét có thể trả bốn trang.

Đặt `ContextSource.base=dc=lab,dc=example,dc=org` và search base tương đối `ou=paging-lab`, dùng `SUBTREE_SCOPE`. Đảm bảo server cho đọc `employeeNumber`, `cn` và attribute sort mong muốn.

### Trình tự integration test có điểm đồng bộ

~~~mermaid
sequenceDiagram
    participant Test as Test runner
    participant Reader as Reader (connection A)
    participant Writer as Writer (connection B)
    participant LDAP as LDAP server
    Test->>Reader: Bắt đầu scan với pageSize=3
    Reader->>LDAP: Search trang 1 + cookie rỗng
    LDAP-->>Reader: IDs trang 1 + cookie C1
    Reader-->>Test: Đã có trang 1, tạm dừng
    Test->>Writer: Thêm/xóa/đổi cn/rename một entry trong OU lab
    Writer->>LDAP: Modify/Add/Delete/ModifyDN
    LDAP-->>Writer: Success hoặc lỗi xác định
    Writer-->>Test: Mutation hoàn tất
    Test->>Reader: Tiếp tục với cùng search và cookie C1
    Reader->>LDAP: Search trang 2
    LDAP-->>Reader: Trang 2 + cookie mới
    Reader-->>Test: Các trang còn lại và báo cáo ID
    Test->>Test: So T0/T1, duplicates, missing, values
~~~

**Điểm cốt lõi về kết nối:** reader phải giữ cùng LDAP connection cho chuỗi paging, còn writer phải dùng **một connection khác** để tạo thay đổi đồng thời. Không chia sẻ một `DirContext` mutable giữa hai thread mà không có hợp đồng thread-safety được xác minh.

Để test ổn định, dùng một tín hiệu đồng bộ rõ ràng như `CountDownLatch` hoặc callback “sau trang đầu”, không dựa vào `Thread.sleep(1000)` để đoán khi nào server hoàn thành page 1. Sau khi writer nhận success, mới cho reader lấy page 2.

### Không nên hardcode kết quả thiếu/trùng của server

Các LDAP server có thể dùng cursor, paging state, sort index hoặc snapshot riêng. Với một thay đổi cụ thể, server có thể:

- Trả entry bị trùng hoặc bỏ sót.
- Trả đầy đủ danh sách cũ dù dữ liệu mới đã thay đổi.
- Trả lỗi cookie/constraint hoặc không cho tiếp tục.
- Áp dụng một hành vi được nhà cung cấp mô tả riêng.

**Integration test cần ghi nhận điều đã quan sát**, kiểm tra API không xử lý sai hoặc báo thành công giả. Không đặt assertion “cứ thêm Binh thì Dung chắc chắn phải trùng” cho mọi server; đó là hành vi của một mô hình lý giải, không phải bảo đảm giao thức.

## 13. Ma trận kiểm thử cần thực hiện

| Test | Can thiệp giữa trang | Quan sát quan trọng | Kiểm tra |
| --- | --- | --- | --- |
| **S0 — Không đổi** | Không có tác vụ ghi | Tính đầy đủ và duy nhất | `missing=unexpected=duplicates=∅` |
| **S1 — Thêm trước ranh giới** | Add entry có khóa sort nhỏ | Lặp, thiếu, thay đổi count | So tập T0/T1 và ID |
| **S2 — Thêm sau ranh giới** | Add entry có khóa sort lớn | Có thấy entry mới không | Ghi rõ thời điểm kỳ vọng |
| **S3 — Xóa entry đã đọc** | Delete sau trang 1 | Lặp/thiếu khi cursor dịch | So tập T0/T1 |
| **S4 — Xóa entry chưa đọc** | Delete trước trang chứa nó | Entry có còn xuất hiện không | Không coi thiếu entry vừa bị xóa là bug mặc định |
| **S5 — Đổi `cn` lên đầu** | Modify khóa sort trước ranh giới | Mất entry ở trang sau | ID ổn định, CN trước/sau |
| **S6 — Đổi `cn` xuống cuối** | Modify khóa sort của entry đã đọc | Có thể lặp cùng ID | Dedupe và audit |
| **S7 — Rename/move trong scope** | Đổi DN nhưng còn thuộc tập | Dedupe bằng DN có thể sai | ID bất biến và DN trước/sau |
| **S8 — Move ra ngoài scope** | Entry rời search base | Tập kỳ vọng thay đổi | So T0/T1 rõ ràng |
| **S9 — Sort key bằng nhau** | Có nhiều entry cùng `cn` | Thứ tự giữa các trang | Sort response và khóa phụ nếu có |
| **S10 — Filter thay đổi** | Đổi một giá trị quyết định filter | Entry rời/vào tập | Ghi lại filter và trạng thái |
| **S11 — Cookie sai** | Đưa cookie của truy vấn khác hoặc hết hạn | Lỗi và phục hồi | Không tiếp tục âm thầm |
| **S12 — Connection đổi** | Mở context khác giữa hai trang | Cookie có thể vô hiệu | Kiểm tra quản lý kết nối |
| **S13 — ACL thay đổi** | Quyền đọc entry/attribute thay đổi | ID thiếu do ACL | Phân loại lỗi/thiếu dữ liệu |
| **S14 — Backend đổi** | Request tiếp sang replica khác | Khác trạng thái/capability | Ghi endpoint, không reuse cookie tùy tiện |
| **S15 — Không có paging control** | Server không công bố RFC2696 | Client xử lý unsupported | Không lặp đọc toàn DIT vào RAM |

Với **S0**, bộ fixture phải được cố định: không có job đồng bộ hoặc tác nhân khác ghi vào OU lab. Nếu chưa kiểm soát được môi trường, `S0` không thể dùng làm bằng chứng về tính ổn định.

### Test sorting riêng

Một test sorting nên kiểm tra cả:

1. Server công bố và **xử lý thành công** Sort control (không chỉ nhận request).
2. Thứ tự các giá trị theo matching/ordering rule thực tế của attribute.
3. Thứ tự ở **ranh giới giữa các trang**, không chỉ bên trong từng page.
4. Hành vi khi sort key trùng, thiếu hoặc thay đổi.
5. Kết quả sau khi áp index hoặc thay đổi schema/config ở server.

Không so trực tiếp kết quả theo Java `String.compareTo` rồi khẳng định server sort sai nếu server dùng matching rule/collation khác, đặc biệt với tiếng Việt và Unicode.

## 14. Gắn Server-Side Sort cùng paging trong Spring LDAP

Trong Spring LDAP 3.x/4.0, có thể kết hợp `SortControlDirContextProcessor` với `PagedResultsDirContextProcessor` bằng `AggregateDirContextProcessor`:

~~~java
import org.springframework.ldap.control.PagedResultsDirContextProcessor;
import org.springframework.ldap.control.SortControlDirContextProcessor;
import org.springframework.ldap.core.support.AggregateDirContextProcessor;

// Một tập processor cho một chuỗi scan.
PagedResultsDirContextProcessor paging =
        new PagedResultsDirContextProcessor(25);

SortControlDirContextProcessor sort =
        new SortControlDirContextProcessor("cn");

AggregateDirContextProcessor processors =
        new AggregateDirContextProcessor();

processors.addDirContextProcessor(sort);
processors.addDirContextProcessor(paging);

// Truyền 'processors' vào overload search nhận DirContextProcessor:
// operations.search(base, filter, controls, mapper, processors);
// Lặp các trang trên cùng connection và dựa vào paging.hasMore().
// Kiểm tra sort.isSorted() / sort.getResultCode() sau search.
~~~

Đoạn mã chỉ minh họa phần **kết hợp controls**, không phải một phương thức Java độc lập. Vẫn cần tạo `SearchControls`, mapper, duy trì `SingleContextSource` và quản lý vòng đời paging giống các mục trước.

Trong API Spring LDAP mới, `PagedResultsDirContextProcessor` và `SortControlDirContextProcessor` có thể đã được đánh dấu deprecated để chuyển sang các class **`ControlExchangeDirContextProcessor`** và exchange tương ứng. Do đó, kiểm tra **version của dự án** trước khi chọn API. Điều quan trọng bất kể version là cả paging và sorting được **server chấp nhận**, trong cùng search; response sort phải được kiểm tra.

### Những bẫy trong code dùng sorting

- Sort control **không luôn thành công** chỉ vì search trả một danh sách.
- Một số server không hỗ trợ sort theo thuộc tính không có ordering rule phù hợp.
- Sort key do người dùng chọn phải nằm trong **allowlist**, không cho HTTP request gửi tên thuộc tính tùy ý.
- Không thể chữa “sort không ổn định” bằng cách sort từng page ở Java.
- Sort nhiều khóa có thể cần API đặc thù; một constructor nhận một `String` không mặc định biểu diễn nhiều khóa.
- Nếu đổi sort key giữa hai page, phải bắt đầu **một chuỗi paging mới**, không tiếp tục cookie cũ.

## 15. Phân biệt phát hiện sai lệch với khắc phục sai lệch

Phát hiện trùng không tự làm cho kết quả đầy đủ. Hãy tách ba chiến lược:

### A. Dedupe cho UI hoặc tác vụ idempotent

Khi cùng ID xuất hiện hai lần, ứng dụng có thể chỉ hiển thị một lần hoặc bỏ qua lần xử lý thứ hai. Nhưng cần ghi nhận duplicate trong audit.

~~~java
Set<String> processedIds = new java.util.HashSet<>();

for (EmployeeRow row : page) {
    if (!processedIds.add(row.id())) {
        // Trùng ID: ghi nhận, không xử lý lần hai.
        continue;
    }
    // Xử lý idempotent, có kiểm soát quyền.
}
~~~

Mã trên tránh xử lý cùng ID hai lần **trong một tiến trình đang chạy**, nhưng:

- Không khôi phục những ID chưa được server trả về.
- Bộ `processedIds` có thể rất lớn với tập dữ liệu lớn; cân nhắc checkpoint/dedup storage.
- Khi tiến trình crash, một tác vụ chưa có checkpoint bền vững vẫn có thể xử lý lại.
- Bản ghi cùng ID nhưng có version khác có thể cần xử lý theo logic update, không bỏ qua mù.

### B. Reconciliation sau khi scan

Với dữ liệu quan trọng, sau lượt quét có thể:

1. So tập ID đã thấy với nguồn chuẩn hoặc dữ liệu snapshot được hỗ trợ.
2. Nếu không có snapshot, dùng một cơ chế change tracking/LDAP changelog/DirSync/syncrepl tùy server và nghiệp vụ để thu thập thay đổi từ thời điểm bắt đầu.
3. Áp dụng sự kiện và đối chiếu lại ID/version một cách idempotent.
4. Đánh dấu checkpoint chỉ khi dữ liệu được xử lý và lưu bền vững.
5. Khi không thể xác nhận tính đầy đủ, **báo trạng thái chưa chắc chắn**, không tuyên bố đã đồng bộ hoàn tất.

Một lượt search thứ hai cũng có thể bị ghi đồng thời; **quét hai lần không tự tạo snapshot nguyên tử**. Reconciliation là quy trình được thiết kế dựa trên bằng chứng thay đổi và tính nhất quán của nguồn.

### C. Chọn cơ chế khác khi nghiệp vụ yêu cầu snapshot

Đối với xuất dữ liệu “chính xác tại thời điểm T”, cần khả năng snapshot/export có bảo đảm từ directory hoặc hạ tầng. Với đồng bộ liên tục, cân nhắc cơ chế theo dõi thay đổi thực sự của server. Không cam kết có thể cung cấp kết quả transactionally consistent chỉ bằng RFC 2696 + SSS.

## 16. Xử lý lỗi và tình huống kết quả chưa chắc chắn

| Dấu hiệu | Nguyên nhân có thể | Phản ứng thích hợp |
| --- | --- | --- |
| Không còn cookie | Đã hết trang | Kết thúc scan và đối chiếu ID |
| Cookie không hợp lệ | Hết hạn, đổi connection, backend hoặc query | Đóng phiên và bắt đầu lại có kiểm soát |
| `unavailableCriticalExtension (12)` | Server không hỗ trợ control critical | Dùng fallback hoặc báo không hỗ trợ |
| `timeLimitExceeded (3)` | Query/sort quá tốn thời gian | Thu hẹp base/filter, index, timeout |
| `sizeLimitExceeded (4)` hoặc `adminLimitExceeded (11)` | Bị giới hạn server | Giảm phạm vi, thay chiến lược; không bỏ qua phần bị cắt |
| `noSuchObject (32)` | Base không còn tồn tại | Kiểm tra OU và `ContextSource.base` |
| `insufficientAccessRights (50)` | Không đủ quyền hoặc ACL đổi | Không nâng quyền vô điều kiện |
| Sort response thất bại | Sort key/rule/giới hạn server | Không coi trang được sort đúng |
| Nhiều entry trùng ID | Cùng entry được trả hai lần, hoặc ID nghiệp vụ không duy nhất | Phân biệt **lỗi scan** và **lỗi thiết kế ID** |
| Thấy ít entry hơn page size nhưng còn cookie | Server trả phần nhỏ do xử lý/giới hạn | Kiểm tra cookie; **không dừng chỉ vì trang ngắn** |
| Không thấy ID ổn định | Projection, schema hoặc ACL | Không kiểm thử dedupe bằng khóa thiếu |
| Mất kết nối ở trang giữa | Trạng thái scan chưa hoàn tất | Không báo hoàn thành; xử lý restart/checkpoint |
| Một entry thay đổi nội dung | Cập nhật đồng thời | So version/timestamp theo khả năng server |

**Không lấy `result.size() < pageSize` làm điều kiện kết thúc duy nhất.** Theo RFC 2696, dấu hiệu kết thúc là **cookie rỗng** trong response; server có thể có hành vi phân trang và giới hạn riêng. Không chỉ dựa vào số hàng khi đã dùng paging.

### Khi thất bại ở giữa phiên scan

Nếu đã xử lý 10 trang rồi trang 11 lỗi, trạng thái ứng dụng không nên là `COMPLETED`. Một chiến lược hợp lý là:

- Ghi nhận scan ID, tham số base/filter/scope/sort, checkpoint và lỗi theo chính sách bảo mật.
- Không đưa cookie LDAP vào log hoặc coi nó dùng được vô hạn sau reconnect.
- Nếu tác vụ có thể chạy lại, thiết kế **idempotent processing** theo ID và version.
- Quyết định chạy lại từ đầu, resume bằng cơ chế được server cho phép hoặc reconciliation.
- Không sửa state của nhiều entry khi chưa có quyền nghiệp vụ tương ứng.

## 17. Quan sát vận hành và bảo mật

Khi kiểm thử trên LDAP server, có thể lưu một báo cáo kỹ thuật ở dạng:

~~~text
scanId: lab-scan-042
base: ou=paging-lab
scope: SUBTREE
filter: (objectClass=inetOrgPerson)
sortKey: cn
pageSize: 3
pagesReceived: 4
rowsReceived: 12
uniqueStableIds: 12
duplicateStableIds: 0
missingAgainstFixture: 0
unexpectedAgainstFixture: 0
mutationType: NONE
result: PASS
~~~

Đây là dữ liệu **giả lập**, không phải báo cáo đã chạy. Nếu test cố tình có mutation, bổ sung thời điểm ghi, loại thay đổi, entry test ID và phiên bản dữ liệu T0/T1 được kiểm soát.

Nên thu thập thêm:

| Chỉ số | Mục đích |
| --- | --- |
| Thời gian mỗi page và toàn scan | Phát hiện query chậm, sort/index thiếu |
| Số page và số result entry | Phát hiện hành vi bất thường |
| Tỉ lệ duplicate theo ID | Theo dõi kết quả quét bị lặp |
| Tỉ lệ missing chỉ khi có fixture/snapshot đáng tin | Tránh kết luận sai từ số ước lượng |
| Kết quả Sort control | Không tưởng nhầm các page đã được sort |
| Cookie reset/restart | Phát hiện lỗi session/connection |
| LDAP endpoint/replica | Điều tra khác biệt giữa backend |
| Lỗi ACL/TLS/timeout | Điều tra lỗi truy cập và vận hành |

**Bảo mật:** dùng LDAPS hoặc StartTLS đã kiểm chứng certificate/hostname, tài khoản chỉ đọc khi quét, chỉ cấp quyền ghi trong OU lab cho test thay đổi, không dùng dữ liệu cá nhân production. Không log mật khẩu, cookie raw, DN đầy đủ hoặc thuộc tính nhạy cảm khi không cần.

Cookie paging **không phải bằng chứng về quyền truy cập**; dù ứng dụng giữ cookie, server vẫn áp chính sách của danh tính bind. Nếu frontend có cursor, ứng dụng phải ràng buộc session/cursor với người gọi và điều kiện truy vấn, không cho sửa bytes của cookie.

## 18. Bài thực hành: chọn assertion đúng

Giả sử test fixture ở T0 có sáu ID:

~~~text
expectedAtT0 = {A, B, C, D, E, F}
pageSize = 3
~~~

### Phần A — Không thay đổi

Server trả:

~~~text
P1 = [A, B, C]
P2 = [D, E, F]
cookie sau P2 = rỗng
~~~

Hãy tính `received`, `unique`, `missing`, `duplicates` và xác định PASS/FAIL.

### Phần B — Vừa trùng vừa thiếu

Server giả lập trả:

~~~text
P1 = [A, B, C]
P2 = [C, E, F]
cookie sau P2 = rỗng
~~~

Hai trang vẫn có tổng cộng 6 hàng. Vì sao test chỉ dùng `received == expected.size()` là sai?

### Phần C — Có entry mới

Giữa hai trang, người khác thêm G, khiến một response có:

~~~text
P1 = [A, B, C]
P2 = [D, E, F]
P3 = [G]
~~~

So với T0, G là gì? Nếu mục tiêu là “dữ liệu chính xác tại T0”, có thể chấp nhận G không? Nếu mục tiêu là “cập nhật gần hiện tại”, cần thêm điều kiện nào?

### Phần D — Rename

Entry có ID bất biến `E104` đổi:

~~~text
DN cũ: uid=an,ou=people,dc=example,dc=org
DN mới: uid=an2,ou=people,dc=example,dc=org
Stable ID: E104 (không đổi)
~~~

Nếu dùng DN làm khóa dedupe, điều gì có thể xảy ra? Nếu dùng E104 thì sao?

### Phần E — Cookie

Một worker dùng cookie từ trang 1 sau khi một request khác đổi filter `(departmentNumber=DEV)` thành `(departmentNumber=HR)`. Có được tiếp tục cookie đó không? Vì sao?

### Đáp án

| Phần | Đáp án |
| --- | --- |
| A | `received=6`, `unique=6`, `missing=∅`, `duplicates=∅`, PASS với fixture không đổi |
| B | `received=6` nhưng `unique=5`, `missing={D}`, `duplicates={C}`; chỉ đếm hàng không đủ |
| C | G là `unexpected` so với T0; không thuộc snapshot T0. Với mục tiêu gần hiện tại, phải xác định chính sách consistency và so với trạng thái T1/version |
| D | DN có thể khiến một entry bị tính thành hai ID; ID E104 cho phép nhận ra cùng một entry dù tên đổi |
| E | Không. RFC 2696 yêu cầu request tiếp giữ các thành phần tìm kiếm tương thích; filter mới phải bắt đầu chuỗi mới |

### Câu hỏi tự đánh giá

1. Có thể kết luận “không thiếu entry” chỉ bằng cách kiểm tra không có ID trùng không?
2. Vì sao `PagedResultsCookie` không bảo đảm snapshot bất biến?
3. Vì sao các request paging trong Spring LDAP cần duy trì cùng connection?
4. Sort theo `cn` có luôn tạo thứ tự duy nhất không?
5. Một entry bị xóa sau khi trang 1 đã chứa nó thì so với snapshot T0 phải diễn giải ra sao?
6. Khi cần scan tuyệt đối đầy đủ, ngoài paging cần thiết kế thành phần gì?

**Đáp án ngắn:** (1) Không; (2) tập kết quả có thể đổi; (3) cookie/context server có thể gắn connection; (4) không; (5) phải ghi rõ thời điểm kỳ vọng; (6) snapshot/version hoặc change tracking/reconciliation có bảo đảm.

## 19. Checklist kiểm thử thiếu, trùng và thay đổi entry

- [ ] Đã định nghĩa rõ mục tiêu: UI gần hiện tại, batch idempotent, đồng bộ hay snapshot kiểm toán.
- [ ] `ContextSource.base`, search base, scope, filter, projection đúng; có quyền đọc ID ổn định.
- [ ] Server công bố Simple Paged Results; nếu có sort, kiểm tra SSS capability và response thực tế.
- [ ] Cookie mới nhất được giữ trong đúng chuỗi, cùng connection, không tái sử dụng sau khi hết.
- [ ] Không đổi base/filter/scope/sort/identity giữa các page.
- [ ] Không dừng chỉ vì page có ít hàng hơn page size; dừng khi cookie rỗng hoặc xử lý lỗi.
- [ ] Test fixture không đổi so sánh **ID đầy đủ** chứ không chỉ tổng số lượng.
- [ ] Test mutation có T0/T1 rõ, ID bất biến và đồng bộ sau trang 1 trước trang 2.
- [ ] Có test insert, delete, đổi sort key, đổi filter, rename/move và sort key trùng.
- [ ] Không hardcode rằng mọi server chắc chắn bỏ sót/trùng khi có một mutation.
- [ ] Phân biệt trùng do server/page với trùng **ID nghiệp vụ** do dữ liệu không duy nhất.
- [ ] Khi scan thất bại hoặc cookie hết hạn, không công bố hoàn tất; có restart/reconciliation rõ ràng.
- [ ] Không coi dedupe là bằng chứng không bỏ sót.
- [ ] Dùng directory lab, quyền tối thiểu, TLS, giới hạn trang/tài nguyên và dọn entry test an toàn.

## 20. Những điểm cần ghi nhớ

- **RFC 2696 Simple Paged Results** chia kết quả LDAP thành nhiều trang bằng cookie, nhưng **khi tập kết quả thay đổi, client có thể nhận trùng hoặc thiếu entry**.
- **Phải kiểm tra theo ID ổn định**, không chỉ DN/UID có thể đổi và không chỉ so tổng số hàng.
- **Có trùng** có thể phát hiện từ dữ liệu trả về; **không thiếu** đòi hỏi tập ID kỳ vọng độc lập hoặc cơ chế snapshot/change tracking phù hợp.
- **Server-Side Sorting** giúp sắp tập kết quả, nhưng khóa không duy nhất và cập nhật sort key vẫn có thể làm thứ tự trang không ổn định.
- **Spring LDAP cần giữ cùng underlying connection cho chuỗi paging**; sử dụng `SingleContextSource` hoặc cơ chế tương đương của framework.
- **Unit test mô phỏng trang** xác minh thuật toán phát hiện; **integration test có mutation được đồng bộ** xác minh hành vi của server/provider đang dùng. Không áp đặt một biểu hiện trùng/thiếu lên mọi LDAP server.
- **Dedupe không phải snapshot**. Khi nghiệp vụ cần dữ liệu chính xác/đầy đủ, thiết kế reconciliation hoặc change tracking và checkpoint idempotent.
- **Bảo mật và giới hạn tài nguyên** vẫn quan trọng: LDAPS/StartTLS, ACL tối thiểu, filter an toàn, sort key allowlist và không log cookie/secret.

### Tài liệu tham khảo

- [RFC 2696 — LDAP Control Extension for Simple Paged Results Manipulation](https://www.rfc-editor.org/rfc/rfc2696)
- [RFC 2891 — LDAP Control Extension for Server Side Sorting of Search Results](https://www.rfc-editor.org/rfc/rfc2891)
- [Spring LDAP — Processing the DirContext, Paged Search Results](https://docs.spring.io/spring-ldap/reference/processing-the-dircontext.html)
- [Spring LDAP — PagedResultsControlExchangeDirContextProcessor](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/control/PagedResultsControlExchangeDirContextProcessor.html)
- [Spring LDAP — PagedResultsDirContextProcessor (API cho phiên bản cũ)](https://docs.spring.io/spring-ldap/docs/3.3.x/api/org/springframework/ldap/control/PagedResultsDirContextProcessor.html)
- [Spring LDAP — SingleContextSource](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/core/support/SingleContextSource.html)
- [Spring LDAP — AggregateDirContextProcessor](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/support/AggregateDirContextProcessor.html)
- [RFC 4512 — LDAP Directory Information Models](https://www.rfc-editor.org/rfc/rfc4512)

