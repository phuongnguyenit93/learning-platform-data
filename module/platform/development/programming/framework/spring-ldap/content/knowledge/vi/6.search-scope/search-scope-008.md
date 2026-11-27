# Phân biệt giới hạn phía client với giới hạn server

Khi tìm kiếm trong LDAP bằng **Spring LDAP**, ứng dụng không chỉ quyết định **tìm ở đâu** và **lọc entry nào**, mà còn phải quyết định **chấp nhận bao nhiêu kết quả** và **chờ trong bao lâu**. Tuy nhiên, việc ứng dụng đặt giới hạn không có nghĩa nó kiểm soát hoàn toàn LDAP server. Máy chủ có chính sách và tài nguyên riêng; ứng dụng cũng có timeout mạng, thời hạn xử lý HTTP và các giới hạn bộ nhớ độc lập với giới hạn tìm kiếm của LDAP.

Bài thuộc chương **Search scope** của module **SPRING_LDAP**. Nội dung tập trung vào cách phân biệt giới hạn do client yêu cầu trong `SearchRequest`, giới hạn thực thi bởi LDAP server và giới hạn xử lý phía ứng dụng. Sau bài học, người học có thể cấu hình `LdapTemplate`, `LdapQueryBuilder` hoặc `SearchControls` một cách có chủ đích, hiểu kết quả bị cắt ngắn, thiết kế phân trang an toàn và kiểm thử truy cập thư mục qua `ContextSource` với timeout và TLS phù hợp.

## 1. Một search LDAP đi qua những giới hạn nào?

Giả sử API tra cứu nhân viên thực hiện một yêu cầu tìm kiếm:

~~~text
Base DN:     ou=people,dc=example,dc=org
Scope:       SUBTREE
Filter:      (&(objectClass=inetOrgPerson)(ou=Engineering))
Attributes:  uid, cn, mail
Count limit: 100
Time limit:  3 giây (giới hạn thời gian tìm kiếm được yêu cầu)
~~~

Thư mục có 2.000 entry khớp filter. Client muốn nhận tối đa 100 entry trong tối đa 3 giây. Đồng thời, máy chủ có thể được quản trị để giới hạn tối đa 80 entry trên một truy vấn và tối đa 2 giây xử lý. Dịch vụ web còn đặt deadline 5 giây cho toàn bộ HTTP request.

Các giới hạn hoạt động ở các lớp khác nhau:

| Lớp | Ai quyết định? | Ví dụ | Ảnh hưởng chính |
| --- | --- | --- | --- |
| **Vùng tìm kiếm** | Ứng dụng yêu cầu; server kiểm tra quyền và áp dụng | Base `ou=people`, scope `ONELEVEL` | Những entry nào **có thể được xét** |
| **Giới hạn trong LDAP SearchRequest** | Client gửi; server thực thi theo giao thức và chính sách của nó | `sizeLimit=100`, `timeLimit=3` | Số entry và thời gian tìm kiếm client **đề nghị** |
| **Chính sách/cap của server** | Quản trị viên hoặc cấu hình LDAP server | Tối đa 80 entry, tối đa 2 giây | Có thể chặt hơn yêu cầu client; bảo vệ server |
| **Giới hạn kết nối/đọc của client** | Ứng dụng, JNDI provider hoặc lớp mạng | Connect timeout 2 giây, read timeout 4 giây | Chặn việc chờ kết nối/phản hồi quá lâu |
| **Giới hạn nghiệp vụ ở ứng dụng** | Ứng dụng | API chỉ trả tối đa 20 hồ sơ; HTTP deadline 5 giây | Kiểm soát phản hồi, bộ nhớ, quyền và trải nghiệm |

**Mấu chốt:** `sizeLimit` và `timeLimit` trong LDAP SearchRequest là **giá trị client yêu cầu server thực thi**. Chúng khác với việc Java cắt `List` sau khi nhận kết quả, và cũng khác với giới hạn tối đa do server tự đặt.

## 2. Search scope giới hạn vùng dữ liệu, không giới hạn số kết quả

LDAP search gồm ít nhất **base DN**, **scope**, **filter** và **requested attributes**. Scope quy định vùng tên được duyệt:

| Scope | Phạm vi | Ví dụ với base `ou=people,dc=example,dc=org` |
| --- | --- | --- |
| `OBJECT` / `BASE` | Chỉ xét entry tại base DN | Chính entry `ou=people` |
| `ONELEVEL` | Chỉ xét entry con trực tiếp của base | `uid=linh,ou=people,...` |
| `SUBTREE` | Xét base và các entry ở mọi cấp dưới nó | Người dùng trực tiếp và entry trong các OU con |

~~~mermaid
flowchart TB
    A["dc=example,dc=org"]
    A --> B["ou=people"]
    B --> C["uid=linh"]
    B --> D["uid=mai"]
    B --> E["ou=archive"]
    E --> F["uid=old-user"]
    A --> G["ou=groups"]
~~~

Với base `ou=people`:

- `OBJECT` chỉ xét `ou=people`.
- `ONELEVEL` xét `uid=linh`, `uid=mai` và `ou=archive`; filter quyết định entry nào trong số đó khớp.
- `SUBTREE` còn có thể xét `uid=old-user` trong `ou=archive` và chính entry `ou=people`.

Một số API dùng tên `BASE` thay cho `OBJECT`; cả hai chỉ ý tưởng “chính base object”. Tên enum và cách truyền scope phụ thuộc API được sử dụng.

**Đặt `countLimit=100` không biến `SUBTREE` thành `ONELEVEL`.** Nếu tìm cả cây rồi giới hạn 100 kết quả, server vẫn có thể phải đánh giá một vùng rộng trước khi hoàn thành. Muốn giảm phạm vi nghiệp vụ và chi phí tìm kiếm, hãy thu hẹp base DN, scope và filter; đừng chỉ dựa vào giới hạn số kết quả.

## 3. Giới hạn client gửi trong giao thức LDAP

Trong LDAPv3, `SearchRequest` có các trường quan trọng:

~~~text
baseObject:  ou=people,dc=example,dc=org
scope:       wholeSubtree
derefAliases: neverDerefAliases
sizeLimit:   100
timeLimit:   3
typesOnly:   false
filter:      (&(objectClass=inetOrgPerson)(ou=Engineering))
attributes:  uid, cn, mail
~~~

Các tên trường ở trên mô tả cấu trúc giao thức; không phải cú pháp lệnh cần copy nguyên khối. Theo LDAPv3 (RFC 4511):

- **`sizeLimit`:** số lượng **SearchResultEntry** tối đa client yêu cầu server trả cho một thao tác search; giá trị `0` có nghĩa client **không yêu cầu một giới hạn số entry cụ thể**.
- **`timeLimit`:** thời gian tối đa client yêu cầu dành cho **thao tác search ở server**, đơn vị ở cấp giao thức là **giây**; `0` có nghĩa client **không yêu cầu giới hạn thời gian search cụ thể**.
- **`scope`:** xác định phạm vi tên của search; đây không phải một giới hạn số lượng.
- **`filter`:** chọn entry phù hợp; không có chức năng tự giới hạn số bản ghi hay thời gian.

Giá trị `0` **không có nghĩa** server bắt buộc trả vô hạn dữ liệu hoặc xử lý vô hạn thời gian. Server vẫn có thể áp giới hạn quản trị, từ chối yêu cầu, hết tài nguyên hoặc bị timeout mạng.

### 3.1. Hiểu đúng “client-side size limit”

Có hai khái niệm thường đều bị gọi là “giới hạn phía client” nhưng có cách hoạt động khác nhau:

1. **Client-requested LDAP size limit:** client gửi `sizeLimit=N`; **server** biết về giới hạn và xử lý search theo giao thức.
2. **Local result limit:** ứng dụng chỉ giữ hoặc chỉ trả `N` phần tử sau khi thư viện đã nhận dữ liệu; giới hạn này **không tự động** thay đổi SearchRequest.

Ví dụ:

~~~java
// KHÔNG dùng cách này để giới hạn số entry server phải tìm hoặc gửi.
List<Employee> all = employeeRepository.findAllFromLdap();
List<Employee> visible = all.stream().limit(20).toList();
~~~

Nếu `findAllFromLdap()` đã tải 10.000 entry vào bộ nhớ, `limit(20)` chỉ cắt danh sách sau cùng. Nó không giảm lượng dữ liệu mà LDAP server đã gửi tới client trong thao tác trước đó.

Ngược lại, truyền một giới hạn kết quả qua API truy vấn LDAP có thể khiến server dừng trả entry khi giới hạn có hiệu lực, nhưng server vẫn áp chính sách và quy tắc xử lý của chính nó. **Không coi giới hạn truy vấn là một phép phân trang bảo đảm**, và cũng không coi kết quả chạm ngưỡng là đầy đủ.

### 3.2. Giới hạn thời gian search và timeout truyền tải khác nhau

Giả sử:

- `timeLimit=3` trong LDAP SearchRequest: client yêu cầu server chỉ dùng tối đa **3 giây cho thao tác search**.
- Connect timeout 2 giây: client không đợi quá lâu để tạo kết nối tới LDAP server.
- Read timeout 4 giây: client không đợi quá lâu cho hoạt động đọc phản hồi, theo semantics của JNDI provider/driver đang dùng.
- HTTP deadline 5 giây: toàn bộ request xử lý ở ứng dụng có ngân sách tối đa 5 giây.

Một request HTTP có thể bao gồm **kết nối + bind/xác thực tài khoản dịch vụ + search + xử lý kết quả + serializing JSON**. Vì vậy, search hoàn thành trong 3 giây không bảo đảm request HTTP luôn hoàn thành trong 5 giây.

Timeout của provider cũng không tương đương một deadline tuyệt đối cho toàn bộ request: có thể áp cho các hoạt động kết nối/đọc riêng, và hành vi dừng/cancel tùy implementation. Không dùng một số timeout duy nhất để kết luận toàn bộ đường đi có giới hạn thời gian cứng.

## 4. Giới hạn do LDAP server áp đặt

LDAP server có thể bảo vệ tài nguyên và thực hiện chính sách bằng các giới hạn như:

- **Số entry tối đa được trả:** có thể áp cho truy vấn nói chung, từng tài khoản hoặc từng loại thao tác.
- **Thời gian xử lý tối đa:** tránh các search quá rộng hoặc quá tốn tài nguyên.
- **Giới hạn phân trang:** số entry tối đa mỗi trang, số trang hoặc chính sách về control.
- **Giới hạn tài nguyên khác:** số kết nối, kích thước yêu cầu, mức độ truy cập, xử lý filter, alias/referral, chỉ mục và bộ nhớ.

Tên tham số và mức hỗ trợ khác nhau giữa **OpenLDAP**, **Active Directory Domain Services** và các sản phẩm LDAP khác. Ví dụ, chính sách tìm kiếm của một server có thể áp giới hạn khác nhau cho tài khoản dịch vụ thông thường và tài khoản quản trị. Không suy đoán giá trị mặc định của sản phẩm từ quy tắc chung.

Một cách diễn giải đơn giản cho giới hạn số lượng và thời gian là:

~~~text
Client yêu cầu: sizeLimit=100, timeLimit=3s
Server cap:     tối đa 80 entry, tối đa 2s
Tác động:       server có thể dừng theo ngưỡng chặt hơn
~~~

Tuy nhiên, **không phải mọi yêu cầu đều trả đúng `min(client, server)` entry**: filter có thể chỉ khớp 12 entry; ACL có thể ẩn một phần dữ liệu; search có thể bị hủy, lỗi mạng hoặc chạm time limit trước count limit; server cũng có thể dùng chính sách phân trang và cách thông báo riêng.

### 4.1. Khi đạt giới hạn: kết quả có thể không đầy đủ

LDAPv3 có các result code trong `SearchResultDone`, đáng chú ý:

| Mã LDAP | Tên | Ý nghĩa thường gặp |
| --- | --- | --- |
| `0` | `success` | Search hoàn thành theo semantics của server |
| `3` | `timeLimitExceeded` | Search đạt giới hạn thời gian |
| `4` | `sizeLimitExceeded` | Search đạt giới hạn số entry |
| `11` | `adminLimitExceeded` | Một giới hạn quản trị bị vượt quá |
| `10` | `referral` | Có hướng dẫn tiếp tục truy vấn ở nơi khác |

Một search có thể đã gửi vài `SearchResultEntry` rồi mới trả `timeLimitExceeded` hoặc `sizeLimitExceeded`. Vì vậy, việc nhận được một số entry **không chứng minh** tìm kiếm đã hoàn thành.

Với Spring LDAP/JNDI, lỗi từ server thường được chuyển thành ngoại lệ ở phía Java; loại ngoại lệ và việc client có giữ được các entry trước đó hay không phụ thuộc API, provider và cách xử lý kết quả. Không viết logic chỉ dựa vào `list.size()` rồi ngầm xem mọi danh sách là đầy đủ.

**Nguyên tắc nghiệp vụ:** nếu search dùng để kiểm tra “đã có tài khoản cùng định danh chưa?”, “còn ai thuộc nhóm có quyền đặc biệt?” hay “đã lấy toàn bộ hồ sơ chưa?”, một kết quả bị cắt ngắn phải được xử lý thành **không thể kết luận đầy đủ**, không phải “không có ai khác”.

## 5. Cấu hình giới hạn trong Spring LDAP

### 5.1. `LdapQueryBuilder` và `LdapTemplate`

Spring LDAP có API cho phép đặt search scope, số entry tối đa được yêu cầu và thời gian tìm kiếm theo query:

~~~java
import java.util.List;

import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;
import org.springframework.ldap.query.SearchScope;

public class EmployeeDirectoryReader {
    private final LdapTemplate ldapTemplate;

    public EmployeeDirectoryReader(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<String> findUserIds(String department) {
        if (department == null || department.isBlank()) {
            throw new IllegalArgumentException("department không được rỗng");
        }

        LdapQuery query = LdapQueryBuilder.query()
                .base("ou=people")
                .searchScope(SearchScope.SUBTREE)
                .countLimit(100)
                .timeLimit(3000)
                .attributes("uid")
                .where("objectClass").is("inetOrgPerson")
                .and("ou").is(department);

        return ldapTemplate.search(
                query,
                (AttributesMapper<String>) attrs ->
                        (String) attrs.get("uid").get());
    }
}
~~~

Giả định `LdapContextSource` đã cấu hình base DN `dc=example,dc=org`, nên `ou=people` là **DN tương đối**. `.where(...).is(department)` dùng builder để giữ dữ liệu đầu vào ở vai trò **giá trị filter**, không nối chuỗi chưa escape.

Trong ví dụ:

- `countLimit(100)` truyền giới hạn số kết quả cho yêu cầu search.
- `timeLimit(3000)` biểu diễn **3.000 mili giây ở API Spring LDAP/JNDI**, không phải 3.000 giây của trường protocol `timeLimit`.
- `attributes("uid")` chỉ yêu cầu thuộc tính cần thiết, giảm dữ liệu trả về.
- Server có thể áp giới hạn thấp hơn hoặc trả lỗi do vượt ngưỡng.

**Chú ý đơn vị:** LDAP protocol có trường `timeLimit` tính bằng **giây**; API `SearchControls` của JNDI dùng **mili giây**. Cần đọc hợp đồng của phiên bản thư viện và kiểm thử đường truyền cấu hình, tránh nhầm `3000` thành 3.000 giây. Việc chuyển đổi/ làm tròn về thời gian trong request là chi tiết của provider và cách triển khai; không mặc định chính xác tuyệt đối tới mili giây ở server.

Đoạn code tập trung minh họa giới hạn. Trong ứng dụng thật cần xử lý attribute `uid` vắng mặt, exception, quyền đọc, alias/referral và tình huống nhiều entry khi nghiệp vụ mong đợi một entry duy nhất.

### 5.2. JNDI `SearchControls`

Bên dưới Spring LDAP, JNDI hỗ trợ `javax.naming.directory.SearchControls` để cấu hình các tham số tương tự:

~~~java
import javax.naming.directory.SearchControls;

SearchControls controls = new SearchControls();
controls.setSearchScope(SearchControls.SUBTREE_SCOPE);
controls.setCountLimit(100L);
controls.setTimeLimit(3000);
controls.setReturningAttributes(new String[] {"uid", "cn"});
~~~

Một thao tác JNDI search có thể nhận `SearchControls` để áp các giới hạn yêu cầu. Spring LDAP cũng có các overload search dùng `SearchControls`, khi ứng dụng cần điều khiển trực tiếp thay vì query builder.

| Cấu hình Java | Đơn vị/cách hiểu | Cần nhớ |
| --- | --- | --- |
| `setCountLimit(100L)` | Số entry yêu cầu tối đa | `0` nghĩa là không đặt giới hạn count theo yêu cầu client |
| `setTimeLimit(3000)` | Mili giây theo API JNDI | Không đồng nghĩa timeout toàn bộ HTTP request |
| `setSearchScope(SUBTREE_SCOPE)` | Phạm vi tên | Không phải limit số bản ghi |
| `setReturningAttributes(...)` | Thuộc tính cần nhận | Không giới hạn số entry, nhưng giảm payload |

Không nên đồng thời cấu hình hai đường dẫn riêng (ví dụ query builder và `SearchControls` tự dựng) rồi giả định chúng sẽ được cộng dồn. Hãy xác định một API sở hữu toàn bộ yêu cầu search cho chức năng đó.

### 5.3. Connect timeout và read timeout thuộc phần kết nối

Nếu dùng JNDI LDAP provider của JDK, có các environment property thường gặp:

~~~java
import java.util.Map;
import org.springframework.ldap.core.support.LdapContextSource;

LdapContextSource source = new LdapContextSource();
source.setUrl("ldaps://directory.example.org:636");
source.setBase("dc=example,dc=org");
source.setBaseEnvironmentProperties(Map.of(
        "com.sun.jndi.ldap.connect.timeout", "2000",
        "com.sun.jndi.ldap.read.timeout", "4000"
));
// Còn cần cấu hình danh tính bind/secret và TLS trust phù hợp.
~~~

Cả hai giá trị timeout minh họa ở đây được provider diễn giải theo **mili giây**. Đây là các property **đặc thù của JNDI LDAP provider**, không phải trường chuẩn của LDAP SearchRequest; provider khác có thể dùng cách cấu hình khác.

- **Connect timeout:** giới hạn chờ giai đoạn tạo kết nối theo semantics của provider.
- **Read timeout:** giới hạn chờ đọc phản hồi theo semantics của provider.
- **Search time limit:** yêu cầu server giới hạn thời gian thực hiện phép tìm kiếm.

Trong môi trường thật, cần xác minh chứng chỉ và hostname của endpoint LDAPS/StartTLS, dùng tài khoản tra cứu tối thiểu quyền, bảo vệ secret, quan sát timeout và cách pooling ảnh hưởng việc tạo lại kết nối. Việc dùng pool sẵn có có thể khiến một số lần search không cần mở TCP connection mới, nhưng không làm mất yêu cầu giới hạn thời gian và kiểm soát lỗi.

## 6. Giới hạn ở client sau khi nhận kết quả: khi nào hữu ích?

Cắt bớt kết quả sau khi query có thể hữu ích cho **API response**, nhưng không thay thế giới hạn server hay giới hạn SearchRequest.

~~~java
List<String> ldapUserIds = employeeDirectoryReader.findUserIds("Engineering");

// Chỉ giới hạn số phần tử trong JSON trả ra, sau khi LDAP search đã chạy.
List<String> responseItems =
        ldapUserIds.stream().limit(20).toList();
~~~

Cách này phù hợp khi hàm `findUserIds` vốn đã có giới hạn và bộ dữ liệu nhỏ. Nếu gọi API search “không giới hạn” rồi mới lấy 20 phần tử, ứng dụng có nguy cơ:

- Nhận nhiều entry và tốn băng thông/bộ nhớ.
- Chờ server lâu dù người dùng chỉ cần một trang nhỏ.
- Gây tải server và làm tăng độ trễ của các request khác.
- Vô tình trả “20 kết quả đầu” dù thứ tự search chưa được bảo đảm.

Ngược lại, việc **dừng đọc** một stream phản hồi nếu API cung cấp streaming không tự động đồng nghĩa server đã hoàn tất/hủy search an toàn. Cần xem provider có gửi LDAP abandon/cancel hay đóng tài nguyên không, và cần giải phóng kết nối đúng cách. Với `LdapTemplate.search(...)` trả `List`, dữ liệu đã được thu thập trước khi gọi `stream().limit(...)`.

### 6.1. Không dùng việc nhận ít hơn N entry để kết luận toàn bộ dữ liệu

Ví dụ service lấy tối đa 100 người theo filter. Kết quả chứa 80 entry. Có thể là:

1. Chỉ có 80 entry phù hợp, search hoàn thành.
2. Server có cap 80 entry và dừng do `sizeLimitExceeded`.
3. Search bị giới hạn thời gian giữa chừng.
4. Một nhánh được chuyển sang referral mà ứng dụng chưa xử lý.
5. ACL chỉ cho tài khoản dịch vụ thấy một phần dữ liệu.

**Không thể kết luận từ `list.size() == 80`.** Cần đọc trạng thái hoàn thành/lỗi, chính sách server, phạm vi tra cứu và ý nghĩa nghiệp vụ của kết quả.

Nếu ứng dụng cần chứng minh không có dữ liệu trùng lặp, chỉ kiểm tra trên một trang giới hạn không đủ; phải có chính sách uniqueness ở nguồn dữ liệu hoặc một cách truy vấn được thiết kế riêng cho mục tiêu đó.

## 7. Phân trang có giải quyết giới hạn server không?

LDAP có thể hỗ trợ **Simple Paged Results Control** (RFC 2696), cho phép client yêu cầu từng trang và nhận **cookie** để tiếp tục lấy kết quả. Tính năng này khác với `sizeLimit`:

| Cơ chế | Câu hỏi được giải quyết | Điều không được bảo đảm |
| --- | --- | --- |
| `sizeLimit=100` | “Search được yêu cầu trả tối đa bao nhiêu entry?” | Không có cơ chế lấy trang kế tiếp |
| Simple Paged Results | “Lấy kết quả theo từng lô và tiếp tục bằng cookie như thế nào?” | Không mặc định vượt mọi giới hạn của server |
| App API page size = 20 | “Mỗi phản hồi HTTP cho người dùng gồm bao nhiêu phần tử?” | Không tự tạo phân trang LDAP phía server |
| Search scope/filter | “Tập dữ liệu nào đủ điều kiện tham gia truy vấn?” | Không quy định thứ tự ổn định của các kết quả |

Luồng tổng quát:

~~~mermaid
sequenceDiagram
    participant App as Ứng dụng Spring
    participant LDAP as LDAP server
    App->>LDAP: Search + PagedResultsControl(pageSize=100)
    LDAP-->>App: Entries trang 1 + cookie A
    App->>LDAP: Search + cookie A
    LDAP-->>App: Entries trang 2 + cookie B
    App->>LDAP: Search + cookie B
    LDAP-->>App: Entries trang cuối + cookie rỗng
~~~

Điều cần lưu ý:

1. **Server phải hỗ trợ control**; trang được trả và số lượng kết quả có thể bị chính sách server giới hạn.
2. Client cần **tuân theo cookie** và thực hiện các yêu cầu tiếp theo theo quy tắc của LDAP server; không tự tạo cookie bằng offset.
3. **Phân trang không phải sự bảo đảm về snapshot nhất quán** nếu thư mục thay đổi giữa các lượt search; có thể cần cơ chế nhất quán khác tùy nghiệp vụ và server.
4. Phân trang **không tự cung cấp thứ tự sắp xếp cố định**; nếu cần thứ tự ổn định, đánh giá cơ chế sort control được server hỗ trợ hoặc thiết kế phù hợp.
5. Phải đặt **giới hạn tổng số entry, số trang và thời gian toàn bộ quy trình** ở ứng dụng. Page size nhỏ không loại trừ việc đọc hàng triệu entry qua nhiều trang.
6. Một số giới hạn server có thể được xử lý khác nhau khi có paging control; không được giả định paging luôn bỏ qua giới hạn quản trị.

Ví dụ: API chỉ được xem 500 hồ sơ tối đa, dùng trang LDAP 100 entry/lượt. Ứng dụng cần dừng khi đã đạt giới hạn tổng hoặc gặp lỗi; tuyệt đối không loop cookie vô hạn. Khi LDAP trả lỗi hoặc cookie không thể tiếp tục, phải báo kết quả **chưa đầy đủ** cho tác vụ yêu cầu sự đầy đủ.

## 8. Thiết kế giới hạn theo nhu cầu nghiệp vụ

Không phải chức năng nào cũng cần cùng loại limit. Hãy chọn giới hạn từ **mục đích sử dụng**:

| Nhu cầu | Gợi ý giới hạn | Lý do |
| --- | --- | --- |
| Đăng nhập bằng tên tài khoản | Base/filter hẹp; xử lý trùng định danh và authentication riêng | Cần đúng tài khoản, không duyệt danh bạ rộng |
| Gợi ý người dùng khi gõ | Base đúng OU, limit nhỏ, timeout ngắn, giới hạn input và tần suất | Đáp ứng nhanh, tránh tạo tải lớn |
| Trang danh bạ | Phân trang ở LDAP nếu server hỗ trợ, giới hạn tổng theo phiên/truy vấn | Không tải tất cả hồ sơ vào RAM |
| Xuất báo cáo được cấp quyền | Phân trang theo lô, timeout và quy trình job phù hợp, xử lý dữ liệu thay đổi | Xử lý tập lớn nhưng phải xác nhận tính đầy đủ |
| Đồng bộ toàn bộ nhóm/quyền | Định nghĩa trạng thái partial/error và cơ chế đồng bộ theo sản phẩm | Không thể xem “nhận được N entry” là hoàn thành |

Ví dụ cho một API gợi ý tìm kiếm:

~~~text
- Chỉ cho phép tìm dưới ou=people
- SUBTREE nếu cấu trúc OU con thực sự cần được duyệt
- Search filter được dựng bằng API có escaping
- Yêu cầu tối đa 20 entry và tối đa 2 giây search
- Provider connect/read timeout riêng
- HTTP deadline riêng
- Trả cảnh báo/lỗi nếu bị server cắt ngắn thay vì khẳng định đủ kết quả
~~~

Nếu muốn biết có **ít nhất một** tài khoản khớp hay không, có thể giới hạn số entry yêu cầu rất nhỏ và chỉ hỏi những thuộc tính cần thiết. Nhưng nếu kết quả có ý nghĩa an ninh hoặc tính nhất quán, phải diễn giải trạng thái server và quyền truy cập; không suy từ một kết quả rỗng khi search chưa hoàn thành.

## 9. Quan sát và xử lý lỗi đúng lớp

Một service nên phân loại lỗi thay vì bắt tất cả rồi trả danh sách rỗng:

| Hiện tượng | Lớp liên quan | Hướng xử lý |
| --- | --- | --- |
| `sizeLimitExceeded` | Giới hạn kết quả ở LDAP server/client-requested | Xem kết quả là chưa đầy đủ, thu hẹp filter hoặc phân trang có kiểm soát |
| `timeLimitExceeded` | Giới hạn thời gian search tại server | Thu hẹp phạm vi, tối ưu chỉ mục/filter, điều chỉnh limit hợp lý |
| `adminLimitExceeded` | Chính sách quản trị server | Tôn trọng chính sách; trao đổi với quản trị viên và thiết kế truy vấn phù hợp |
| Kết nối không thiết lập được | Kết nối/DNS/TLS/firewall | Kiểm tra endpoint, chứng chỉ, timeout, khả năng truy cập |
| Đọc phản hồi bị timeout | Provider/network | Ghi nhận read timeout, kiểm tra chất lượng đường truyền và tải |
| HTTP request hết thời hạn | Deadline của ứng dụng hoặc gateway | Kiểm soát tổng thời gian, hủy/cắt công việc phù hợp |
| Search có referral | Naming context và chính sách referral | Chỉ theo đích tin cậy, bảo vệ credential, phân biệt partial result |
| Kết quả ít hơn mong đợi nhưng không có lỗi | Filter/base/scope/ACL/schema/dữ liệu | Kiểm tra dữ liệu và quyền, không tự động tăng limit vô hạn |

Trong Spring LDAP, ngoại lệ từ JNDI được chuyển sang hệ ngoại lệ Spring LDAP; lớp ngoại lệ cụ thể và trạng thái partial results phụ thuộc phiên bản và provider. Chỉ bắt các ngoại lệ mà code thực sự có thể xử lý; những lỗi còn lại cần được theo dõi, ghi log an toàn và trả trạng thái phù hợp cho người gọi.

**Không bật cơ chế bỏ qua partial result chỉ để “hết báo lỗi”.** Nếu `LdapTemplate` được cấu hình bỏ qua một số ngoại lệ partial result, ứng dụng có thể đánh mất dấu hiệu dữ liệu chưa đầy đủ. Chỉ chấp nhận điều đó khi nghiệp vụ cho phép và được kiểm thử với server cụ thể.

### 9.1. Gợi ý metric phục vụ vận hành

Theo dõi các metric hữu ích như:

- Thời gian search thực tế (p50/p95/p99), số kết quả trả về và số query trên một request.
- Số lần gặp `sizeLimitExceeded`, `timeLimitExceeded`, `adminLimitExceeded` và timeout mạng.
- Base/scope và loại truy vấn ở dạng **nhãn nghiệp vụ an toàn**; không biến DN người dùng, giá trị filter nhạy cảm hoặc mật khẩu thành metric labels.
- Số trang và tổng entry trong một lần phân trang; tỷ lệ request bị dừng do đạt giới hạn tổng.

Không log credential, token, toàn bộ filter chứa dữ liệu cá nhân, hay các DN nhạy cảm vào log có phạm vi truy cập rộng. Thông số bảo mật như TLS, quyền tài khoản bind và việc tái sử dụng connection pool cần kiểm tra cùng hành vi search, vì chúng cũng ảnh hưởng kết quả và độ trễ.

## 10. Kiểm thử để biết giới hạn nào đang tác động

Sử dụng LDAP server thử nghiệm có schema và dữ liệu nhân viên đủ lớn (ví dụ 150 entry khớp một filter). Chạy các trường hợp sau với cùng base, scope, filter và danh tính kết nối:

| Ca | Thiết lập | Kỳ vọng/điều cần quan sát |
| --- | --- | --- |
| A | Client `countLimit=20`, server cho phép tối đa 200 | Không yêu cầu quá 20 entry; kiểm tra completion/result code của server |
| B | Client `countLimit=200`, server cap 50 | Server có thể cắt ngắn hoặc trả lỗi limit; không mặc định đủ 150 |
| C | Client `countLimit=0`, server cap 50 | Giá trị 0 không bỏ được server cap |
| D | Query rất rộng, server giới hạn thời gian nhỏ | Ghi nhận `timeLimitExceeded` và những entry có thể đã được trả |
| E | Connect timeout nhỏ, endpoint không kết nối được | Phân biệt lỗi kết nối với `timeLimitExceeded` |
| F | Read timeout nhỏ, server phản hồi chậm | Phân biệt lỗi đọc với thời hạn search |
| G | `SUBTREE` so với `ONELEVEL` trên OU có nhánh con | Thấy tập entry hợp lệ theo scope thay đổi dù limit giữ nguyên |
| H | Paged results, trang 25 entry | Lấy qua nhiều trang theo cookie nếu server hỗ trợ; có giới hạn tổng |
| I | Cắt `stream().limit(10)` sau `search` | API chỉ trả 10 nhưng search ban đầu vẫn đã được thực hiện |
| J | Tài khoản thiếu quyền đọc một nhánh | Không quy thiếu dữ liệu cho giới hạn count nếu ACL mới là nguyên nhân |

Quy trình thực hiện:

1. Cấu hình `ContextSource` cho môi trường thử nghiệm, giới hạn quyền tài khoản, bật TLS và xác minh chứng chỉ thích hợp.
2. Tạo đủ entry với cùng `objectClass`/thuộc tính để dễ đếm tổng phù hợp với filter.
3. Dùng một filter do builder tạo và thay đổi **từng loại limit** theo từng ca, không thay đồng thời nhiều tham số.
4. Ghi lại số entry, thời gian đo ở ứng dụng, result code/ngoại lệ, trạng thái đầy đủ và số request nếu phân trang.
5. Với case giới hạn server, dùng cấu hình quản trị **chỉ trên môi trường test**; không tự chỉnh chính sách production.
6. Xác minh ứng dụng phản hồi đúng: dữ liệu không đầy đủ phải mang trạng thái lỗi/cảnh báo hoặc cơ chế tiếp tục phù hợp nghiệp vụ.

Một unit test với mock có thể xác nhận query builder được gọi với `countLimit` và `timeLimit` mong muốn, nhưng **không xác minh được** server áp cap gì, cách xử lý timeout, LDAP result code hay chính sách ACL. Những yếu tố này cần test tích hợp trên server thật, cùng loại hoặc hành vi tương đương server dự kiến triển khai.

## 11. Các nhầm lẫn cần tránh

1. **“`countLimit(100)` bảo đảm có đúng 100 kết quả.”** Không. Filter có thể chỉ khớp vài entry, hoặc server dừng sớm vì cap/thời gian/quyền.
2. **“`countLimit(0)` sẽ buộc server trả tất cả.”** Không. Nó chỉ không yêu cầu một count limit cụ thể; server vẫn áp chính sách.
3. **“`timeLimit(3000)` nghĩa là giao thức cho 3.000 giây.”** Không. Trong API query của Spring LDAP/JNDI, giá trị được diễn giải theo mili giây; trường LDAP SearchRequest tính bằng giây.
4. **“Chỉ trả 20 phần tử bằng Java stream là server đã tìm 20 entry.”** Không. Thao tác LDAP có thể đã nhận rất nhiều entry trước khi stream chạy.
5. **“Có một phần kết quả là search thành công.”** Không. Phải xem trạng thái hoàn thành, lỗi và referral.
6. **“Bật paged results là hết mọi giới hạn server.”** Không. Server vẫn có thể hạn chế paging, thời gian, kết nối hoặc tổng tài nguyên.
7. **“Tăng timeout sẽ chữa được mọi search chậm.”** Không. Filter quá rộng, base/scope sai, thiếu index hoặc mạng kém cần xử lý từ nguyên nhân.
8. **“Search limit tự thay thế được ACL.”** Không. Giới hạn tài nguyên và quyền truy cập là hai chính sách độc lập.

## 12. Tình huống ứng dụng và tự đánh giá

**Bối cảnh:** Một trang quản trị nhân sự dùng Spring LDAP để hiển thị gợi ý nhân viên. Mỗi lần người dùng gõ tên, API phải phản hồi nhanh, chỉ hiển thị tối đa 20 gợi ý. Server LDAP có chính sách giới hạn tìm kiếm chung và thỉnh thoảng xuất hiện timeout.

**Thiết kế tham khảo:**

- Chỉ search trong nhánh nhân sự được phép, dùng scope đúng với mô hình OU thực tế.
- Dùng `LdapQueryBuilder` tạo filter và mã hóa giá trị tìm kiếm; không nối chuỗi đầu vào.
- Đặt count limit phù hợp (ví dụ 20) và time limit cho search (ví dụ 2.000 mili giây ở API); đồng thời cấu hình connect/read timeout và HTTP deadline riêng.
- Chỉ yêu cầu thuộc tính cần thiết; bảo vệ kết nối bằng TLS và dùng tài khoản truy vấn ít quyền.
- Khi LDAP báo kết quả bị cắt do limit hoặc timeout, trả trạng thái đúng với nghiệp vụ, thay vì gán “không có dữ liệu”.
- Nếu cần duyệt nhiều entry, dùng cơ chế phân trang do server hỗ trợ và luôn có giới hạn tổng.

### Câu hỏi kiểm tra

**Câu 1.** Client gửi `sizeLimit=500`, server có cap 100. Ứng dụng có được giả định sẽ nhận đủ 500 entry nếu thư mục có 1.000 entry khớp?

**Đáp án:** Không. Server có thể áp cap chặt hơn và báo giới hạn bị vượt; số entry nhận được không chứng minh kết quả đầy đủ.

**Câu 2.** `SearchControls.setTimeLimit(3000)` có tương đương đặt read timeout 3.000 mili giây không?

**Đáp án:** Không. `setTimeLimit` là giới hạn thời gian dành cho search theo API; read timeout liên quan tới việc chờ phản hồi mạng theo provider. Hai chính sách cần xem xét riêng.

**Câu 3.** API trả `list.stream().limit(20).toList()`. LDAP server có chắc chỉ gửi 20 entry?

**Đáp án:** Không. Nếu `list` là kết quả của một LDAP search đã hoàn tất, việc cắt danh sách xảy ra ở ứng dụng sau khi nhận dữ liệu.

**Câu 4.** Nếu search trả 35 entry rồi phát `timeLimitExceeded`, có thể dùng 35 entry đó như danh sách nhân viên đầy đủ không?

**Đáp án:** Không. Đây là kết quả chưa hoàn chỉnh; phải xử lý trạng thái lỗi hoặc cơ chế truy vấn tiếp phù hợp nghiệp vụ.

**Câu 5.** Có thể dùng paging để bảo đảm lấy trọn danh bạ bất kể giới hạn của server không?

**Đáp án:** Không. Paging phụ thuộc server hỗ trợ và chính sách quản trị; cần theo dõi cookie, lỗi, giới hạn tổng, trạng thái hoàn thành và khả năng dữ liệu thay đổi giữa các trang.

**Câu 6.** Khi tìm kiếm chậm, chỉ nên tăng `timeLimit`?

**Đáp án:** Không. Trước tiên cần kiểm tra base DN, scope, filter, chỉ mục, quyền, kích thước dữ liệu và hạ tầng; tăng thời gian chờ khi hợp lý chỉ là một phần của giải pháp.

**Ghi nhớ:** Với Spring LDAP, hãy phân biệt bốn quyết định: **(1) phạm vi tìm kiếm bằng base/scope/filter**, **(2) giới hạn search được client yêu cầu server thực hiện**, **(3) chính sách giới hạn của server**, và **(4) timeout/giới hạn xử lý ở ứng dụng và kết nối**. Chỉ khi tách bốn lớp này, ứng dụng mới có thể đánh giá đúng một kết quả có hoàn chỉnh hay không, kiểm soát tài nguyên và bảo vệ trải nghiệm người dùng.
