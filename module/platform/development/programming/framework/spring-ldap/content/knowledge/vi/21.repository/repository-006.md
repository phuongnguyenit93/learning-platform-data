# Phân trang repository và giới hạn server trong Spring LDAP

Một repository LDAP có thể cung cấp phương thức tìm người dùng rất ngắn gọn, nhưng khi thư mục chứa hàng chục nghìn entry, câu hỏi quan trọng là: **dữ liệu được trả về có đầy đủ không, có được chia trang thật sự ở LDAP server không, và điều gì xảy ra khi server áp giới hạn riêng?** Nếu áp dụng tư duy của Spring Data JPA vào Spring Data LDAP mà không kiểm tra khả năng hỗ trợ, ứng dụng có thể hiểu nhầm một danh sách bị cắt là toàn bộ directory.

Bài học thuộc chương **Repository** trong lộ trình **SPRING_LDAP**. Nội dung làm rõ ranh giới giữa **Spring Data LDAP Repository**, truy vấn bị giới hạn bằng `LdapQuery`/`SearchControls` và **Simple Paged Results** ở tầng LDAP server; sau đó hướng dẫn sử dụng `LdapTemplate` khi thực sự cần đọc tuần tự nhiều trang, xử lý cookie, giới hạn kích thước/thời gian, sorting và các lỗi trả kết quả không đầy đủ. Những nguyên tắc này gắn với schema, filter, DN, `ContextSource`, kết nối TLS, pooling và kiểm thử truy cập thư mục an toàn.

## 1. Ba khái niệm thường bị gọi chung là “pagination”

Cần phân biệt rõ:

| Khái niệm | Cách hoạt động | Có bảo đảm đọc được trang tiếp không? |
|---|---|---|
| **Repository trả danh sách có giới hạn** | Một truy vấn yêu cầu trả tối đa N entry, hoặc ứng dụng chỉ giữ N phần tử đầu | **Không**; không có cookie hay vị trí tiếp tục |
| **Phân trang trong bộ nhớ ứng dụng** | Lấy toàn bộ kết quả, rồi chia `List` theo page number/page size | Có thể chia danh sách đã lấy nhưng tốn RAM; nếu server cắt kết quả thì **thiếu dữ liệu** |
| **LDAP Simple Paged Results** | Server trả một trang, kèm cookie để tiếp tục cùng chuỗi truy vấn | **Có điều kiện**; phải hỗ trợ RFC 2696, quản lý cookie và cùng kết nối |

Một API HTTP nhận `page=3&size=50` không có nghĩa LDAP provider đã thực hiện server-side pagination. Nó có thể chỉ cắt mảng sau khi tải tất cả entry, hoặc tệ hơn, tạo ra một “trang” từ tập kết quả không đầy đủ vì size limit phía server.

~~~mermaid
flowchart TD
    A["Yêu cầu danh sách người dùng"] --> B{"Cần tất cả dữ liệu hay chỉ kết quả nhỏ?"}
    B -->|"Ít entry, có giới hạn rõ"| C["LdapRepository / LdapQuery"]
    B -->|"Nhiều entry, cần đọc theo lô"| D["LdapTemplate + LDAP Paged Results"]
    C --> E["List đã giới hạn; không có next-cookie"]
    D --> F["Search trang + response cookie"]
    F --> G{"Cookie còn dữ liệu?"}
    G -->|Có| H["Tìm trang tiếp trên cùng kết nối"]
    H --> F
    G -->|Không| I["Hoàn tất, giải phóng tài nguyên"]
~~~

**Điểm mấu chốt:** giới hạn số entry trả về ở một truy vấn và phân trang có khả năng tiếp tục là hai chức năng khác nhau.

## 2. Spring Data LDAP Repository có hỗ trợ Pageable và Sort không?

**Không, đối với repository chuẩn của Spring Data LDAP được tài liệu chính thức mô tả.** Trang cấu hình Spring Data LDAP nêu rõ rằng paging và sorting **không được hỗ trợ trên LDAP repositories**, do đặc thù giao thức. Tài liệu của Spring Data Commons trình bày `Page<T>`, `Slice<T>`, `Pageable`, `PagingAndSortingRepository` và `Sort` là các **khả năng chung của hạ tầng**, không phải bảo đảm mọi datastore đều triển khai.

Hậu quả đối với thiết kế:

- Đừng sao chép phương thức `Page<PersonEntry> findBy...(..., Pageable pageable)` từ ví dụ JPA rồi giả định nó chạy trên `LdapRepository`.
- Đừng kế thừa `PagingAndSortingRepository` để “bật” phân trang LDAP; interface chung không tự tạo khả năng giao thức và phần triển khai LDAP.
- Đừng suy ra rằng `findAll()` trả về `List` có thể tải an toàn không giới hạn từ LDAP server.
- Đừng dùng `Sort.by("cn")` ở repository rồi kết luận server sẽ gửi kết quả đã được sắp xếp.

**Khả năng phân trang ở tầng Spring LDAP thấp hơn vẫn tồn tại** qua `LdapTemplate` và LDAP Controls. Vì thế đây là sự khác biệt về **tầng API**, không phải tuyên bố LDAP nói chung không bao giờ hỗ trợ phân trang hoặc sorting.

### Kiểm tra tài liệu theo đúng module

| Tên API | Thuộc module | Điều cần nhớ |
|---|---|---|
| `org.springframework.data.ldap.repository.LdapRepository<T>` | Spring Data LDAP | CRUD/repository query; không hỗ trợ paging/sorting chuẩn |
| `org.springframework.data.domain.Pageable`, `Page`, `Slice`, `Sort` | Spring Data Commons | Trừu tượng dùng được khi store module hỗ trợ |
| `org.springframework.ldap.core.LdapTemplate` | Spring LDAP | Search, mapping và hỗ trợ request/response controls |
| `PagedResultsControlExchangeDirContextProcessor` | Spring LDAP | Điều phối Simple Paged Results ở cấp search |
| `SingleContextSource` | Spring LDAP | Giữ cùng context/kết nối trong một chuỗi thao tác phù hợp |
| `javax.naming.ldap.PagedResultsControl` | JNDI | Yêu cầu page size và cookie theo LDAP control |

Với dự án sử dụng phiên bản khác hoặc thư viện tùy biến, luôn đối chiếu tài liệu và integration test của **phiên bản thực đang chạy**. Nội dung này mô tả hành vi repository chuẩn, không loại trừ một custom repository tự triển khai cơ chế paging riêng.

## 3. Repository phù hợp với kiểu truy vấn nào?

Một repository LDAP thông thường sử dụng ODM entity có `@Entry`, `@Id` và các trường `@Attribute`. ID của entity là **DN dạng `javax.naming.Name`**, không phải `Long` hay `Integer` của bảng quan hệ.

Ví dụ entity tối giản:

~~~java
import javax.naming.Name;

import org.springframework.ldap.odm.annotations.Attribute;
import org.springframework.ldap.odm.annotations.Entry;
import org.springframework.ldap.odm.annotations.Id;

@Entry(
    base = "ou=people",
    objectClasses = {
        "top", "person", "organizationalPerson", "inetOrgPerson"
    }
)
public class PersonEntry {
    @Id
    private Name dn;

    @Attribute(name = "uid")
    private String uid;

    @Attribute(name = "cn")
    private String commonName;

    @Attribute(name = "sn")
    private String surname;

    public PersonEntry() {}

    public Name getDn() { return dn; }
    public String getUid() { return uid; }
    public String getCommonName() { return commonName; }
    public String getSurname() { return surname; }
}
~~~

Repository:

~~~java
import org.springframework.data.ldap.repository.LdapRepository;

public interface PersonRepository extends LdapRepository<PersonEntry> {
    // findAll(), findById(Name), save(...) được kế thừa;
    // findAll(LdapQuery) là phương thức LDAP-specific.
}
~~~

Với `LdapRepository<PersonEntry>`, có thể truyền một `LdapQuery` cho `findAll(LdapQuery)`:

~~~java
import java.util.List;

import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.SearchScope;

import static org.springframework.ldap.query.LdapQueryBuilder.query;

// Mảnh mã bên trong service đã inject PersonRepository repository.
LdapQuery criteria = query()
        .base("ou=people")
        .searchScope(SearchScope.SUBTREE)
        .where("objectClass").is("inetOrgPerson")
        .and("uid").is("an");

List<PersonEntry> matches = repository.findAll(criteria);
~~~

Với tìm kiếm UID cụ thể và base DN phù hợp, tập kết quả thường nhỏ. Nhưng **UID không mặc nhiên duy nhất trên toàn DIT**: cùng `uid=an` có thể xuất hiện dưới các OU khác nhau. Repository không có trách nhiệm tự quyết định khóa nghiệp vụ là duy nhất.

### Khi nào không nên gọi findAll() không điều kiện?

Nếu một module quản trị cần hiển thị toàn bộ người dùng của nhiều phòng ban, `repository.findAll()` có thể dẫn tới search rộng. Rủi ro bao gồm:

1. Số entry quá lớn, gây tải mạng và bộ nhớ Java.
2. Server áp `sizeLimit` hoặc `timeLimit`, nên kết quả không đầy đủ hoặc phát sinh exception.
3. Dữ liệu trả về chứa nhiều attribute không cần cho màn hình.
4. Người gọi hiểu nhầm danh sách nhận được là ảnh chụp đầy đủ của directory.
5. Một thay đổi đồng thời trong DIT khiến kết quả ở những thời điểm khác nhau không nhất quán.

Dùng repository cho **tra cứu theo DN, UID trong phạm vi rõ ràng, hoặc CRUD của các entity đã xác định**. Khi phải xử lý dữ liệu lớn, hãy cân nhắc một thành phần search/batch riêng dựa trên `LdapTemplate` hoặc JNDI controls.

## 4. Giới hạn truy vấn không phải trang tiếp theo

Spring LDAP có thể mô tả giới hạn tìm kiếm bằng `LdapQueryBuilder`:

~~~java
LdapQuery limited = query()
        .base("ou=people")
        .searchScope(SearchScope.SUBTREE)
        .countLimit(100)
        .timeLimit(5_000)
        .attributes("uid", "cn")
        .where("objectClass").is("inetOrgPerson");
~~~

Ý nghĩa:

| Thiết lập | Tác động | Không làm được |
|---|---|---|
| `base("ou=people")` | Chọn vị trí bắt đầu search | Tự tạo parent DN hoặc bảo đảm UID duy nhất |
| `searchScope(SUBTREE)` | Tìm cả base và các cấp con | Tự sắp xếp kết quả |
| `countLimit(100)` | Đặt giới hạn số kết quả được yêu cầu | Tạo cookie/trang 2 |
| `timeLimit(5_000)` | Giới hạn thời gian tìm kiếm tại API JNDI, đơn vị ms | Quy định deadline toàn bộ HTTP request |
| `attributes("uid","cn")` | Chỉ yêu cầu các attribute cần thiết | Nâng quyền đọc attribute bị ACL che |
| `where(...).is(...)` | Tạo LDAP filter qua builder | Thay thế kiểm tra phân quyền nghiệp vụ |

**Cảnh báo về chữ “limit”:** `countLimit(100)` chỉ có thể giúp hạn chế quy mô một lần search. Nó không mang “offset=100”, không biết page number, không có next-cookie. Mặc dù số kết quả nằm trong giới hạn, không được suy luận rằng đã đọc hết dữ liệu toàn bộ OU.

Ngoài ra, search bị vượt size/time limit có thể trả **kết quả một phần rồi ném exception** khi JNDI duyệt `NamingEnumeration`. Với đồng bộ dữ liệu, kiểm kê bảo mật hoặc dọn tài khoản, phải coi đây là **FAILED/PARTIAL** chứ không phải “đã đọc hết”.

### Filter và attribute mapping

Nếu mapper cần `cn` nhưng yêu cầu trả về chỉ có `uid`, kết quả có thể thiếu attribute `cn`. Ngược lại, filter có thể sử dụng `objectClass` hoặc `uid` dù các attribute đó không nằm trong projection. Để giảm dữ liệu và hạn chế lộ thông tin, chỉ lấy những attribute thật sự cần và kiểm tra `null` ở mapper.

Không nối trực tiếp input vào filter:

~~~java
// Không nên:
String unsafe = "(uid=" + rawUserInput + ")";
~~~

Hãy dùng `LdapQueryBuilder` hoặc API placeholder/filter argument của JNDI để xử lý escaping theo RFC 4515. Việc escape đúng giúp bảo vệ filter, nhưng vẫn cần authorization riêng ở tầng nghiệp vụ.

## 5. LDAP server có thể giới hạn dữ liệu theo nhiều cách

Mỗi máy chủ có chính sách riêng và người quản trị có thể áp hạn mức khác nhau theo account, base, filter hoặc nhóm người dùng:

| Loại giới hạn | Biểu hiện | Tác động đối với repository |
|---|---|---|
| **Size limit** | Search bị cắt hoặc lỗi `sizeLimitExceeded (4)` | Không thể coi list trả được là tập đầy đủ |
| **Time limit** | `timeLimitExceeded (3)` | Search chưa kết thúc đúng nghĩa |
| **ACL** | Bị ẩn entry hoặc một số attribute | Không thấy không nhất thiết nghĩa là không tồn tại |
| **Quy định search base/scope** | Chỉ thấy một OU, không thấy con sâu | Kết quả phụ thuộc truy vấn |
| **Referral / nhiều naming context** | Server chuyển hướng hoặc từ chối | Không tự có kết quả xuyên nhiều directory |
| **Giới hạn số paged searches** | Không thể mở quá nhiều chuỗi đồng thời | Cần đóng/hủy chuỗi, giới hạn concurrency |
| **Giới hạn page size hoặc control hỗ trợ** | Page size yêu cầu không được đáp ứng như mong đợi | Phải kiểm tra response control và lỗi |
| **Rate limiting / tải server** | Chậm, timeout hoặc lỗi tạm thời | Cần retry có kiểm soát, giảm tải |

Với số lượng lớn, cần phối hợp giới hạn phía client và server. Không tăng `countLimit` từ 100 lên 100.000 với hy vọng vượt qua quy định size limit của directory. **Client không có quyền vô hiệu hóa các hạn mức server** bằng một tham số search.

### SearchControls đặt limit thế nào?

Tầng JNDI có `SearchControls`:

~~~java
import javax.naming.directory.SearchControls;

SearchControls controls = new SearchControls();
controls.setSearchScope(SearchControls.SUBTREE_SCOPE);
controls.setReturningAttributes(new String[] {"uid", "cn"});
controls.setCountLimit(0L); // Không đặt size limit bằng SearchControls.
controls.setTimeLimit(0);   // Không đặt time limit bằng SearchControls.
~~~

Giá trị `0` nghĩa là **không đặt giới hạn qua SearchControls**, **không** có nghĩa server phải trả vô hạn hoặc request không bao giờ timeout. Với paged search, RFC 2696 có tương tác giữa **page size** và **SearchRequest.sizeLimit**: nếu page size lớn hơn hoặc bằng size limit được yêu cầu, máy chủ có thể bỏ qua paged control vì yêu cầu có thể được đáp ứng bằng một trang.

Do đó, khi muốn đọc toàn bộ tập kết quả theo paging, thường không kết hợp một `countLimit` tổng nhỏ hơn page size. Hãy thiết kế kích thước trang, timeout và ngưỡng xử lý nghiệp vụ có chủ đích, đồng thời xử lý những giới hạn do server trả về.

## 6. Simple Paged Results: cơ chế server-side phù hợp

LDAP Simple Paged Results được mô tả trong **RFC 2696**, dùng control OID:

~~~text
1.2.840.113556.1.4.319
~~~

Cơ chế:

1. Client gửi `SearchRequest` đầu tiên với page size mong muốn và cookie rỗng.
2. Server trả entry của trang đầu và **cookie** trong response control.
3. Nếu cookie **không rỗng**, client gửi search tiếp với cookie mới nhất và cùng thông số truy vấn.
4. Nếu cookie **rỗng**, server báo chuỗi đã kết thúc; client đóng tài nguyên.
5. Khi chủ động dừng lúc cookie còn không rỗng, client nên hủy chuỗi bằng **request với page size 0 và cookie cuối**, khi còn cùng kết nối hợp lệ.

~~~mermaid
sequenceDiagram
    participant R as "Repository/Service"
    participant T as "LdapTemplate"
    participant S as "LDAP server"
    R->>T: fetchNextBatch()
    T->>S: Search(pageSize=100, cookie=empty)
    S-->>T: 100 entries + cookie A
    T-->>R: batch 1, hasMore=true
    R->>T: fetchNextBatch()
    T->>S: Search(pageSize=100, cookie=A)
    S-->>T: 37 entries + cookie empty
    T-->>R: batch 2, hasMore=false
    Note over R,S: Kết thúc; giải phóng context
~~~

Cookie phải được coi là **opaque token**, không được giải mã, thay đổi, giả làm số offset hay tự tính page number. Response size có thể là **ước lượng tổng số kết quả** hoặc 0 nếu server không cung cấp ước lượng.

Đặc biệt:

- **Không** dùng `batch.size() < pageSize` làm tín hiệu kết thúc.
- **Không** giả định `pageSize=100` nghĩa mỗi lần trả đúng 100 entry.
- **Không** mặc định có random access tới trang thứ 10 mà không đi qua chuỗi cookie.
- **Không** coi cookie mới nhất là token tái sử dụng an toàn trên một kết nối khác.
- **Không** mặc định sorting hay snapshot nhất quán được cung cấp chỉ vì đang paging.

## 7. Vì sao cần cùng một LDAP connection cho các trang?

Spring LDAP `LdapTemplate` thường lấy context theo phạm vi từng lời gọi search rồi trả/đóng khi hoàn tất. Nhưng với RFC 2696, **cookie tiếp tục chuỗi phụ thuộc trạng thái server/kết nối**; tài liệu Spring LDAP yêu cầu dùng **cùng kết nối bên dưới** giữa các lời gọi.

Không thể chỉ làm:

~~~java
while (hasMore) {
    // Mỗi lần gọi template.search(...) có thể mượn một
    // connection khác từ pool, dù dùng cùng ContextSource.
}
~~~

Vì cookie nhận từ kết nối A không được bảo đảm có thể tiếp tục trên kết nối B. Connection pooling **không bảo đảm** mượn lại đúng connection cũ trong mọi lần gọi.

Spring LDAP cung cấp `SingleContextSource.doWithSingleContext(...)` để thực thi nhiều lệnh qua cùng context trong một callback. Đây là mẫu phù hợp khi muốn đọc **toàn bộ chuỗi phân trang trong một tác vụ**.

### Ranh giới sử dụng context

~~~text
Bắt đầu callback với SingleContextSource
    ├── search trang 1   -> cookie A
    ├── search trang 2   -> cookie B
    ├── ...
    └── search trang cuối -> cookie rỗng
Kết thúc callback
    └── framework giải phóng/trả context
~~~

Không giữ `LdapContext` của callback trong field của singleton. Không trả ra một iterator lười còn dựa vào context đã hết phạm vi. Nếu phải phân trang **qua nhiều HTTP request riêng**, hãy thiết kế một giao thức ứng dụng khác phù hợp; không mặc định rằng raw LDAP cookie có thể chuyển thẳng cho frontend.

## 8. Ví dụ Spring LDAP: đọc theo lô bằng LdapTemplate

Ví dụ dưới đây **không giả định `LdapRepository` có Pageable**. Thay vào đó, một service riêng dùng `LdapTemplate` thông qua `LdapOperations`, `PagedResultsControlExchangeDirContextProcessor` và `SingleContextSource`.

~~~java
import java.util.List;
import java.util.function.Consumer;

import javax.naming.directory.SearchControls;

import org.springframework.ldap.control.PagedResultsControlExchangeDirContextProcessor;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.ContextSource;
import org.springframework.ldap.core.support.SingleContextSource;

public final class PersonBatchReader {
    private final ContextSource contextSource;

    public PersonBatchReader(ContextSource contextSource) {
        this.contextSource = contextSource;
    }

    public record PersonRow(String uid, String cn) {}

    public void forEachBatch(
            int pageSize,
            Consumer<List<PersonRow>> consumeBatch) {

        if (pageSize < 1 || pageSize > 500) {
            throw new IllegalArgumentException(
                    "pageSize must be between 1 and 500");
        }
        if (consumeBatch == null) {
            throw new IllegalArgumentException(
                    "consumeBatch is required");
        }

        SearchControls controls = new SearchControls();
        controls.setSearchScope(SearchControls.SUBTREE_SCOPE);
        controls.setReturningAttributes(new String[] {"uid", "cn"});
        controls.setCountLimit(0L);

        var paging =
                new PagedResultsControlExchangeDirContextProcessor(pageSize);

        SingleContextSource.doWithSingleContext(
                contextSource,
                operations -> {
                    do {
                        List<PersonRow> oneBatch = operations.search(
                                "ou=people",
                                "(&(objectClass=inetOrgPerson)(uid=*))",
                                controls,
                                (AttributesMapper<PersonRow>) attrs -> {
                                    String uid =
                                            (String) attrs.get("uid").get();
                                    String cn = attrs.get("cn") == null
                                            ? null
                                            : (String) attrs.get("cn").get();
                                    return new PersonRow(uid, cn);
                                },
                                paging
                        );
                        consumeBatch.accept(oneBatch);
                    } while (paging.hasMore());

                    return null;
                });
    }
}
~~~

Đoạn code sử dụng **`javax.naming.directory.SearchControls`** và processor của Spring LDAP, không dùng `Pageable`. Nó giả định `ContextSource` được thiết lập với base `dc=example,dc=org`, LDAP server hỗ trợ Paged Results và ứng dụng dùng phiên bản Spring LDAP có lớp `PagedResultsControlExchangeDirContextProcessor`.

Một cách gọi:

~~~java
PersonBatchReader reader = new PersonBatchReader(contextSource);

reader.forEachBatch(100, batch -> {
    // Xử lý trong phạm vi của một trang, ví dụ đối chiếu ID.
    // Không tự động gom tất cả trang vào một List lớn.
    for (PersonBatchReader.PersonRow person : batch) {
        processPerson(person); // Hàm nghiệp vụ do ứng dụng định nghĩa.
    }
});
~~~

**Mảnh code gọi** giả định đã có `contextSource` và `processPerson(...)` của ứng dụng. Tính năng chính: callback nhận **một batch tại một thời điểm**, nên không bắt buộc giữ toàn bộ kết quả trong bộ nhớ.

### Ý nghĩa từng chi tiết

- `SearchControls.SUBTREE_SCOPE` giúp duyệt toàn bộ người dùng bên dưới `ou=people` và các OU con; chỉ dùng nếu đúng phạm vi nghiệp vụ.
- `setReturningAttributes` tránh tải những attribute không cần.
- `setCountLimit(0L)` tránh áp một total count limit của client làm mất ý nghĩa paging; server vẫn có giới hạn riêng.
- Processor gắn request control, đọc response cookie và cập nhật `hasMore()` sau từng lần search.
- `SingleContextSource` giữ cùng context/kết nối trong callback.
- Mỗi batch được xử lý trước khi yêu cầu trang sau; giảm đỉnh sử dụng bộ nhớ nếu callback không tích lũy dữ liệu.
- Dùng `uid` trong filter có thể trả nhiều DN khác nhau với cùng UID; nếu đồng bộ cần khóa ổn định, nên lấy thêm DN hoặc định danh server thích hợp bằng mapper.
- Nếu một batch bị lỗi vì timeout, size limit hoặc callback nghiệp vụ, chuỗi **không được coi là hoàn tất**. Dữ liệu đã xử lý có thể chỉ là một phần.

> Đây là ví dụ minh họa **trường hợp đọc hết chuỗi thành công**. Nếu `consumeBatch` chủ động thoát/throw khi cookie vẫn còn, cần xử lý hủy chuỗi phân trang theo RFC 2696 (page size 0, cookie cuối) trên cùng kết nối nếu còn hợp lệ. Chỉ kết thúc `SingleContextSource` hoặc bỏ biến cookie không phải lúc nào cũng tương đương explicit abandon tại server.

### Cần trả kết quả cho API web thì sao?

Đừng để controller HTTP mở rồi giữ context LDAP qua nhiều request “Next page” tùy ý. Nếu giao diện cần điều hướng người dùng lâu dài, cân nhắc:

1. API **tìm kiếm có filter hẹp** với tập kết quả có giới hạn rõ.
2. **Bản snapshot/bộ kết quả tạm phía ứng dụng** (khi chính sách cho phép), phân trang trên snapshot và quản lý TTL/chi phí.
3. **Một backend cursor service** có hợp đồng phiên, thời gian sống, giới hạn số cursor, ràng buộc connection và hủy đúng lúc — chỉ nếu hạ tầng cho phép vận hành an toàn.
4. Một chiến lược truy vấn theo khóa ổn định với sort/filter tương ứng nếu directory hỗ trợ và yêu cầu nhất quán được thiết kế cụ thể.

Mỗi lựa chọn có đánh đổi về hiệu năng, dữ liệu thay đổi đồng thời, quyền và bộ nhớ. Không có giải pháp “nhảy đến trang bất kỳ” phổ quát chỉ bằng tham số `PageRequest.of(page, size)` trên Spring Data LDAP.

## 9. Phân trang trên UI và phân trang ở LDAP có hợp đồng khác nhau

Ở ứng dụng quan hệ, người dùng quen nhận:

~~~json
{
  "page": 3,
  "size": 25,
  "totalPages": 40,
  "totalElements": 1000
}
~~~

Nhưng LDAP Simple Paged Results chuẩn không định nghĩa **page number** hoặc **totalPages** chắc chắn. Nó dùng cookie theo chuỗi, còn giá trị result size trong response chỉ có thể là **ước lượng**.

Do vậy API phía ứng dụng nên tránh hứa “tổng số trang tuyệt đối chính xác” khi chỉ có response của LDAP. Một response thích hợp hơn cho thao tác đọc tuần tự có thể có dạng:

~~~json
{
  "items": [
    {"uid": "an", "cn": "Nguyen Van An"},
    {"uid": "binh", "cn": "Tran Van Binh"}
  ],
  "complete": false
}
~~~

Ví dụ JSON này **không đưa raw LDAP cookie ra ngoài**. Nếu cần tiếp tục, phía server ứng dụng phải tự quản lý quy trình theo một thiết kế có trạng thái và khả năng hủy, hoặc chọn hình thức truy vấn khác. Trường `complete` phải dựa vào **response cookie rỗng** và search không lỗi, không chỉ vào số phần tử trang.

Không ghi log raw cookie: đó là token trạng thái nội bộ của server và có thể liên quan đến một phiên truy vấn cụ thể.

## 10. Server-side sorting: không tự có khi gọi repository

Tính năng sorting LDAP ở cấp protocol thường gắn với **Server Side Sorting Control** (RFC 2891), khác với paging control. Spring LDAP cung cấp cơ chế pre/post-processing để gắn LDAP controls theo yêu cầu, nhưng **repository chuẩn không hỗ trợ `Sort` như một phần của paging/sorting repository**.

| Nhu cầu | Gợi ý thực hiện | Lưu ý |
|---|---|---|
| Sắp xếp một danh sách nhỏ đã tải đầy đủ | Java `Comparator` trong ứng dụng | Chỉ sắp xếp dữ liệu **đã lấy**, không bổ sung entry bị giới hạn |
| Sắp xếp tập lớn khi server hỗ trợ | LDAP Server Side Sorting Control | Cần kiểm tra response, ACL và khả năng của server |
| Paging + sorting | Kết hợp controls khi server/provider hỗ trợ | Giữ cùng sort key/filter/base giữa các lần tiếp tục |
| Có thứ tự lặp lại ổn định | Xem xét khóa phân biệt và cập nhật đồng thời | Dữ liệu thay đổi có thể khiến lặp/sót |

Không tự tính “trang thứ ba theo tên” bằng cách tải 100 entry đầu, sắp xếp 100 entry ấy rồi lấy phần 51–75: nếu server còn nhiều entry khác, kết quả **không phải** thứ tự toàn bộ directory.

Khi kết hợp paging và sorting, **không đổi thứ tự sort trong chuỗi đã có cookie**. RFC 2696 yêu cầu các thông số search tiếp tục phù hợp với yêu cầu ban đầu; thay sort key có thể làm cookie không còn ý nghĩa.

## 11. Server size limit, countLimit và paging: ba mức phải cùng được xét

Giả sử directory có 10.000 entry thỏa filter, và server có chính sách giới hạn 1.000 kết quả mỗi truy vấn.

| Kịch bản | Client yêu cầu | Điều có thể xảy ra |
|---|---|---|
| Repository `findAll()` | Không giới hạn rõ ràng | Server cắt/đưa lỗi; không nên coi là đủ 10.000 |
| Query `countLimit(300)` | Tối đa 300 entry trong một search | Không có cookie; không thể gọi ngay trang 2 từ kết quả |
| Query `countLimit(5_000)` | Tối đa 5.000 entry | Server vẫn có thể từ chối/cắt ở hạn mức riêng |
| Paged results `pageSize=200` | Mỗi search một trang mong muốn 200 entry | Có thể đọc tuần tự nếu control được hỗ trợ, quyền và giới hạn server cho phép |
| Paged results `pageSize=5_000` | Một trang rất lớn | Server có thể từ chối, giới hạn hoặc trả lỗi tùy chính sách |

**Paging không phải công cụ vượt ACL hay mọi giới hạn quản trị**. Một số server áp size limit theo toàn bộ kết quả, giới hạn số page/cookie đang mở hoặc không hỗ trợ control. Ứng dụng phải phát hiện và báo lỗi hợp lý.

### Time limit có đặc điểm riêng

`SearchControls.setTimeLimit(int)` nhận giá trị bằng **mili giây** trong JNDI; nhưng thời gian LDAP protocol và chính sách server được biểu diễn/áp dụng theo cách riêng. Đồng thời:

- `com.sun.jndi.ldap.connect.timeout` là connect timeout của JDK LDAP provider.
- `com.sun.jndi.ldap.read.timeout` là read timeout của provider.
- Một request HTTP có thể trải qua nhiều thao tác LDAP và mapper Java.
- Giới hạn server `timeLimitExceeded (3)` không nhất thiết tương đương lỗi socket.

**Không xem một `timeLimit` ngắn là cách thay thế connect/read timeout**. Với paging dài nhiều trang, tổng thời gian xử lý còn phụ thuộc số trang, tải server và tốc độ downstream consumer.

## 12. Bảng quyết định: nên dùng repository hay template?

| Tình huống | Lựa chọn mặc định | Vì sao? |
|---|---|---|
| Tìm một account theo DN | `LdapRepository.findById(Name)` | Đã có DN, phù hợp CRUD |
| Tìm vài tài khoản theo UID/email trong OU nhỏ | Repository + `LdapQuery` được giới hạn | Query rõ và kết quả nhỏ |
| Đồng bộ hàng chục nghìn entry theo lô | `LdapTemplate` + RFC 2696 | Cần server-side paging và xử lý từng batch |
| Web muốn nhảy ngay đến page 17 | Thiết kế riêng hoặc snapshot/cursor service | RFC 2696 không tương đương offset pagination |
| Báo cáo cần thứ tự toàn bộ dữ liệu | Server-side sorting nếu hỗ trợ, hoặc quy trình xử lý ngoài | Repository không tạo sorting tự động |
| Dữ liệu phải đầy đủ để xóa/khóa hàng loạt | Quy trình batch + kiểm chứng hoàn tất + audit | Không dùng list từ một search bị giới hạn |
| Directory không hỗ trợ RFC 2696 | Thu hẹp filter theo phân vùng/OU hoặc phương án đặc thù server | Không thể ép server trả cookie bằng repository |
| Khách HTTP chỉ cần vài gợi ý theo tên | Search base hẹp + limit nhỏ | Không cần giữ cursor dài |

**Quy tắc:** dùng repository để biểu diễn dữ liệu và thao tác CRUD một cách rõ ràng; dùng API tìm kiếm có LDAP controls khi cần hành vi nâng cao mà repository không cung cấp.

## 13. Kết quả một phần, lỗi server và kiểm soát trạng thái

Đối với một quy trình đọc theo batch, cần biểu diễn ít nhất ba trạng thái:

~~~text
COMPLETE  - đã nhận cookie rỗng, mọi trang hoàn tất
PARTIAL   - đã xử lý một số entry/trang nhưng chưa hoàn tất chuỗi
FAILED    - lỗi hạ tầng, ACL, control, giới hạn hoặc mapping
~~~

Các tình huống thường gặp:

| Kết quả LDAP | Mã | Ý nghĩa |
|---|---:|---|
| `success` | 0 | Yêu cầu được xử lý thành công; với paging cần kiểm tra cookie cuối |
| `timeLimitExceeded` | 3 | Không hoàn tất trong giới hạn thời gian |
| `sizeLimitExceeded` | 4 | Số kết quả vượt giới hạn áp dụng |
| `unsupportedCriticalExtension` | 12 | Server không hỗ trợ control quan trọng được yêu cầu |
| `noSuchObject` | 32 | Search base/DN không tồn tại hoặc không thấy được |
| `insufficientAccessRights` | 50 | Không có đủ quyền thực hiện/đọc |
| `unwillingToPerform` | 53 | Server từ chối theo chính sách/trạng thái |
| `other` | 80 | Lỗi khác; cần chẩn đoán thêm |

**Không nuốt exception và trả List đã tích lũy như thể hoàn tất**. JNDI có thể gặp lỗi lúc đọc `NamingEnumeration.hasMore()` hoặc `next()`; Spring LDAP thường chuyển ngoại lệ theo hệ thống exception truy cập LDAP. Một số entry có thể đã được xử lý trước khi lỗi xảy ra.

Với các tác vụ đồng bộ ra database khác, nếu đã commit batch 1–4 rồi batch 5 gặp lỗi, dữ liệu đích **đã ở trạng thái từng phần**. Hãy thiết kế checkpoint, idempotency, đối soát và khả năng chạy lại. LDAP paging không tạo một transaction xuyên các trang và các hệ thống khác.

### Concurrent updates có thể làm trùng/sót

RFC 2696 không bảo đảm một snapshot bất biến nếu dữ liệu thay đổi trong khi phân trang. Một entry được rename/move, thêm hoặc xóa trong lúc các trang đang được đọc có thể dẫn đến trùng hoặc bỏ sót trong một số trường hợp.

Khi đồng bộ cần độ nhất quán cao, cân nhắc cơ chế đồng bộ/changelog do server hỗ trợ, hoặc khóa định danh ổn định và chiến lược phát hiện thay đổi. Chỉ bật sorting không giải quyết được mọi race condition.

## 14. Bảo mật và vận hành

Khi ứng dụng cho phép truy vấn diện rộng:

- **Giới hạn search base** ở những OU được nghiệp vụ cho phép, tránh search toàn naming context khi không cần.
- **Ràng buộc filter** bằng `LdapQueryBuilder`/placeholder JNDI, không nối input người dùng thành filter raw.
- **Chỉ trả attribute cần thiết**, tránh `userPassword` và dữ liệu nhạy cảm trong DTO/log.
- **Dùng LDAPS hoặc StartTLS** với xác thực chứng chỉ và hostname; bảo vệ bind credentials qua secret management.
- **Phân quyền tối thiểu** cho tài khoản dịch vụ; không dùng admin toàn directory chỉ để truy vấn.
- **Giới hạn page size và concurrency**; một lượng lớn search sequence có thể giữ trạng thái ở server.
- **Đóng tài nguyên đúng lúc**: `NamingEnumeration`/`DirContext` trong JNDI trực tiếp, hoặc dùng phạm vi `SingleContextSource` phù hợp trong Spring LDAP.
- **Kết thúc chuỗi phân trang còn mở khi chủ động dừng**: RFC 2696 mô tả gửi request với page size 0 và cookie cuối nếu cùng kết nối còn khả dụng.
- **Không lưu raw cookie vô hạn** hoặc đưa cookie sang một session LDAP khác mà không có hợp đồng server hỗ trợ.
- **Giám sát** thời gian search, số batch, số entry, số cookie/connection active, lỗi 3/4/12/53 và số lần retry.

Đừng giảm yêu cầu bảo mật khi benchmark. Việc bật TLS, ACL hoặc pooling có thể ảnh hưởng hiệu năng đo được nhưng là một phần điều kiện hệ thống thực, không phải “nhiễu” có thể bỏ qua ở production.

## 15. Kiểm thử phân trang repository và giới hạn server

Để kiểm chứng, nên dùng LDAP server thử nghiệm hỗ trợ những controls dự kiến. Mock của repository chỉ xác minh method được gọi, **không chứng minh** query đã paging ở server.

| Kịch bản | Thiết lập | Điều phải xác minh |
|---|---|---|
| **Repository query nhỏ** | Một OU có 10 entry | `findAll(LdapQuery)` trả đúng entity trong phạm vi |
| **Repository với dữ liệu lớn** | Tạo nhiều entry vượt size limit | Không lầm kết quả giới hạn là toàn bộ |
| **Pageable trên repository** | Thử thiết kế kiểu JPA | Dự án không dựa vào khả năng không được hỗ trợ |
| **Paged results thành công** | 235 entry, page size 100 | Theo cookie qua các trang và dừng khi cookie rỗng |
| **Số entry đúng bằng page size** | 100 entry, page size 100 | Không dùng độ dài trang để kết luận |
| **Không có kết quả** | Filter không khớp | Kết thúc đúng, không lặp vô hạn |
| **Page size vượt giới hạn** | Đề xuất page size lớn | Kiểm tra lỗi/cơ chế cap, không giả định server luôn phục vụ |
| **Server không hỗ trợ control** | LDAP thử nghiệm tắt/không hỗ trợ RFC 2696 | Phát hiện rõ thiếu khả năng, không silently fallback vào list bị cắt |
| **Mất kết nối giữa chuỗi** | Ngắt sau trang 2 | Không dùng cookie trên kết nối mới như thể hợp lệ |
| **Dừng sớm** | Người dùng hủy tác vụ | Yêu cầu hủy chuỗi khi điều kiện cho phép, giải phóng tài nguyên |
| **Giới hạn size/time** | Ép server báo lỗi | Đánh dấu PARTIAL/FAILED, không báo COMPLETE |
| **Chạy đồng thời** | Hai batch reader sử dụng pool | Mỗi chuỗi giữ đúng connection và không trộn cookie |
| **Sorting + paging** | Sort theo CN nếu server hỗ trợ | Không đổi sort key giữa các trang; kiểm tra tính nhất quán |
| **ACL hạn chế** | Tài khoản chỉ đọc một số entry | Phân biệt tập nhìn thấy với tập vật lý trên server |

Nếu kiểm thử cần đánh giá hiệu năng, ghi lại: số entry, số trang, dữ liệu mỗi trang, thời gian, heap usage, số context active, chỉ số server và tần suất lỗi. Test tốt phải phát hiện cả trường hợp **kết quả có vẻ đúng nhưng chưa đủ**.

## 16. Bài tập thực hành

### Tình huống 1: repository trả đúng 500 entry

Directory có 8.000 tài khoản; code gọi:

~~~java
List<PersonEntry> people = repository.findAll();
System.out.println(people.size()); // 500
~~~

**Câu hỏi:** Có thể kết luận chỉ có 500 entry không?

**Đáp án:** Không. Có thể server/ACL/search base hoặc giới hạn khác ảnh hưởng kết quả. Đặc biệt cần kiểm tra exception, hạn mức size/time và phạm vi tìm kiếm. Nếu nghiệp vụ yêu cầu kiểm kê đầy đủ, hãy dùng một cơ chế paging được server hỗ trợ và chỉ đánh dấu hoàn tất khi đã nhận tín hiệu kết thúc hợp lệ.

### Tình huống 2: thêm Pageable vào interface

Một lập trình viên viết:

~~~java
// Đây là ví dụ KHÔNG được giả định chạy trên LDAP repository chuẩn.
Page<PersonEntry> findBySurname(String sn, Pageable pageable);
~~~

**Câu hỏi:** Vì sao không nên coi đây là phân trang LDAP hoàn chỉnh?

**Đáp án:** Spring Data Commons có `Pageable`, nhưng Spring Data LDAP repository chuẩn không triển khai paging/sorting theo hợp đồng đó. Không thể chỉ thay interface hoặc thêm `PageRequest.of(0, 20)` để có RFC 2696 cookie. Cần dùng API/implementation tùy biến hoặc `LdapTemplate` với paged-results control thích hợp.

### Tình huống 3: countLimit có phải page size?

~~~java
LdapQuery q = query()
        .base("ou=people")
        .countLimit(100)
        .where("objectClass").is("inetOrgPerson");
~~~

**Câu hỏi:** Làm sao lấy entry thứ 101 trở đi?

**Đáp án:** `countLimit(100)` không sinh next-cookie, vì vậy không có “trang 2” từ bản thân query này. Nếu cần duyệt toàn bộ, khởi tạo chuỗi Simple Paged Results được server hỗ trợ, giữ cùng kết nối và đọc cookie response qua processor.

### Tình huống 4: server trả 70 entry trong trang kích thước 100

**Câu hỏi:** Có phải trang cuối?

**Đáp án:** Chưa chắc. **Cookie rỗng** trong response của một search thành công mới là tín hiệu hết trang theo RFC 2696. Nếu cookie không rỗng, client vẫn có thể tiếp tục, bất kể trang có ít hơn 100 entry.

### Tình huống 5: batch thứ ba bị timeLimitExceeded

Một tiến trình đã ghi 200 entry vào database ứng dụng rồi gặp lỗi ở trang thứ ba.

**Câu hỏi:** Có nên trả HTTP 200 với nội dung “đồng bộ xong 200 người dùng” không?

**Đáp án:** Không. Phải đánh dấu trạng thái chưa hoàn tất hoặc thất bại, lưu checkpoint đủ an toàn và có kế hoạch retry/đối soát. Không được suy ra 200 người dùng là toàn bộ directory để xóa/vô hiệu hóa các tài khoản khác.

### Tình huống 6: dùng connection pool có đủ cho paging không?

**Đáp án:** Không. Pool có thể trả một kết nối khác ở mỗi lời gọi. Với chuỗi paged-results dựa trên cookie, cần giữ **cùng kết nối bên dưới** theo hợp đồng Spring LDAP/server, ví dụ dùng `SingleContextSource.doWithSingleContext(...)`.

## 17. Những hiểu nhầm thường gặp

| Hiểu nhầm | Cách hiểu đúng |
|---|---|
| “`Pageable` có trong Spring Data nên mọi repository đều dùng được.” | Hỗ trợ tùy store; Spring Data LDAP repository chuẩn không hỗ trợ paging/sorting. |
| “`countLimit(100)` nghĩa là trang có 100 entry.” | Đây là một limit của search, không phải chuỗi phân trang có cookie. |
| “Server trả 100 entry là đủ vì ứng dụng chỉ thấy 100.” | Có thể còn nhiều dữ liệu hoặc server đã áp giới hạn. |
| “Có RFC 2696 thì nhảy thẳng đến trang 20 được.” | Cookie cung cấp cơ chế tiếp tục tuần tự, không phải offset/page index. |
| “`getResultSize()` là tổng số entry chính xác.” | Có thể chỉ là ước lượng hoặc 0 khi server không cung cấp. |
| “Có pool nên các trang sẽ dùng một connection.” | Pool không tự bảo đảm điều đó. |
| “Trang ít hơn page size là trang cuối.” | Cần kiểm tra response cookie rỗng. |
| “Paging vượt được mọi giới hạn server.” | Không vượt được ACL/chính sách; server có thể hạn chế hoặc không hỗ trợ control. |
| “Sort một trang trong Java tương đương sorting cả directory.” | Chỉ sắp xếp dữ liệu đã tải, không thể thay thế server-side sorting toàn tập. |
| “Timeout sau vài trang có nghĩa là đã đọc đủ phần có thể đọc.” | Đó là kết quả thất bại/không đầy đủ, không phải kết thúc bình thường. |

## Tài liệu tham khảo

- [Spring Data LDAP — Configuration](https://docs.spring.io/spring-data/ldap/reference/ldap/configuration.html): ghi rõ paging/sorting không được hỗ trợ cho repository chuẩn, cùng yêu cầu ODM và kiểu ID `Name`.
- [Spring LDAP — Repositories](https://docs.spring.io/spring-ldap/reference/repositories.html): giới hạn và khả năng của `LdapRepository`.
- [Spring Data LDAP — LdapRepository API](https://docs.spring.io/spring-data/ldap/docs/current/api/org/springframework/data/ldap/repository/LdapRepository.html): `findAll(LdapQuery)`, `findOne(LdapQuery)` và các thao tác CRUD.
- [Spring LDAP — Processing the DirContext](https://docs.spring.io/spring-ldap/reference/processing-the-dircontext.html): ví dụ `PagedResultsControlExchangeDirContextProcessor` và `SingleContextSource`.
- [Spring LDAP — Object-Directory Mapping](https://docs.spring.io/spring-ldap/reference/odm.html): `@Entry`, `@Id`, `@Attribute` và ánh xạ entity.
- [RFC 2696 — LDAP Control Extension for Simple Paged Results](https://www.rfc-editor.org/rfc/rfc2696): cookie, page size, tín hiệu kết thúc và cách hủy chuỗi.
- [RFC 2891 — LDAP Control Extension for Server Side Sorting](https://www.rfc-editor.org/rfc/rfc2891): sorting phía LDAP server.
- [RFC 4511 — LDAP: The Protocol](https://www.rfc-editor.org/rfc/rfc4511): SearchRequest, size/time limit và mã lỗi.
- [RFC 4515 — LDAP: String Representation of Search Filters](https://www.rfc-editor.org/rfc/rfc4515): cấu trúc filter và escape dữ liệu.

## Ghi nhớ

**Spring Data LDAP Repository phù hợp với CRUD và truy vấn giới hạn, nhưng không tự cung cấp `Pageable`/`Sort` như các repository quan hệ.** Khi cần xử lý hàng nghìn entry theo trang, hãy dùng `LdapTemplate` hoặc JNDI với **LDAP Simple Paged Results** nếu server hỗ trợ, quản lý **cookie**, giữ **cùng kết nối** và xác nhận trang cuối bằng **cookie rỗng**. `countLimit`, `timeLimit` và các giới hạn server không phải phân trang; chúng có thể khiến tập kết quả không đầy đủ. Một giải pháp đúng phải đồng thời bảo đảm **phạm vi tìm kiếm, quyền, bảo mật kết nối, tín hiệu hoàn tất và khả năng xử lý lỗi/tái thực thi**, thay vì chỉ chia một `List` thành các trang trên giao diện.
