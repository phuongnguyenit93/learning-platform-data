# Giới hạn phân trang, sắp xếp và các chức năng không được suy ra từ JPA

Khi chuyển từ Spring Data JPA sang **Spring Data LDAP**, nhiều tên API có vẻ quen thuộc: repository, query method, `List<T>`, `Pageable`, `Sort`, `findAll()`. Tuy nhiên, directory LDAP không phải cơ sở dữ liệu quan hệ. Một LDAP search đi qua cây entry theo **base DN**, **scope** và **filter**; server có thể áp dụng size/time limit và các control riêng. Vì vậy, không thể mặc định một repository LDAP hỗ trợ mọi khả năng mà `JpaRepository` cung cấp.

Điểm cần nhớ với module **SPRING_DATA_LDAP** là: tài liệu Spring LDAP hiện hành nêu rõ **paging và sorting không được hỗ trợ trực tiếp bởi Spring LDAP repositories**. Khi cần duyệt tập lớn hoặc sắp xếp kết quả, hãy dùng các LDAP control qua **Spring LDAP `LdapTemplate`/`LdapOperations`**, kiểm tra khả năng của directory server và quản lý cookie/kết nối đúng cách. `Pageable`, `Page`, `Slice` hay `Sort` của Spring Data Commons không tự biến thành LDAP paged-results hoặc server-side sort control.

Bài thuộc chương **LDAP Repository**, tập trung vào chủ đề **“Giới hạn phân trang, sắp xếp và các chức năng không được suy ra từ JPA”**. Nội dung đi từ giới hạn của repository đến RFC 2696 paging, RFC 2891 server-side sorting, ví dụ Spring LDAP 4.1+, thiết kế API continuation token, các bẫy khi xử lý dữ liệu lớn và cách kiểm thử.

## 1. Vì sao không thể xem LDAP như JPA?

JPA làm việc với các entity quan hệ và query có thể được thực thi bằng SQL. LDAP search làm việc với entry trong Directory Information Tree (DIT).

| Khía cạnh | Spring Data JPA | Spring Data LDAP |
|---|---|---|
| Mô hình dữ liệu | Entity và quan hệ bảng | Entry phân cấp, DN và attribute |
| Định danh | Thường là khóa chính scalar | DN, thường ánh xạ thành `javax.naming.Name` |
| Truy vấn | JPQL, Criteria, SQL | LDAP filter, base DN, scope và controls |
| Phân trang | `Pageable`, `Page`, `Slice` qua query execution | Repository LDAP không hỗ trợ paging trực tiếp; dùng paged-results control qua Spring LDAP |
| Sắp xếp | `Sort`/`ORDER BY` | Repository LDAP không hỗ trợ sorting trực tiếp; có thể yêu cầu server sort control |
| Tổng số kết quả | `COUNT` query thường dùng để tạo `Page` | Server có thể không cung cấp estimate; count/search riêng có thể tốn tài nguyên |
| Quan hệ | Join, lazy/eager, cascade theo mapping | Không có SQL join; DN-valued attribute hoặc group membership cần truy vấn/ánh xạ riêng |
| Transaction | Có transaction manager và semantics của database | Không suy ra transaction ACID nhiều entry từ repository LDAP |
| Thay đổi entity | Dirty checking tùy persistence context | Không mặc định có JPA persistence context/dirty checking |

Repository abstraction giúp chuẩn hóa cách gọi, nhưng **khả năng thực tế phụ thuộc store module**. Một method có thể hợp lệ về cú pháp Java mà không có nghĩa LDAP repository sẽ thực hiện cùng semantics với JPA.

## 2. Những gì Spring LDAP Repository hỗ trợ và không hỗ trợ

Spring LDAP repository được xây trên ODM entity và repository infrastructure của Spring Data. Một repository điển hình:

```java
import java.util.List;
import org.springframework.data.ldap.repository.LdapRepository;

public interface PersonRepository
        extends LdapRepository<DirectoryPerson> {

    List<DirectoryPerson> findByUid(String uid);

    List<DirectoryPerson> findBySn(String surname);
}
```

Với Spring LDAP hiện hành:

- Entity phải dùng ODM annotations của Spring LDAP.
- ID của entity ODM là Distinguished Name, kiểu `javax.naming.Name`.
- `LdapRepository<T>` có một type parameter cho entity; ID mặc định là `Name`.
- `LdapRepository` được dùng khi cần hỗ trợ `LdapQuery` parameters trong repository infrastructure.
- **Paging và sorting không được hỗ trợ trực tiếp bởi Spring LDAP repositories.**

Các keyword chung như `First`/`Top` hoặc `OrderBy...` có thể xuất hiện trong tài liệu Spring Data Commons, nhưng parser chung không chứng minh store LDAP hỗ trợ từng cách kết hợp. Nếu dự án cần giới hạn một truy vấn repository, hãy xác nhận behavior của đúng phiên bản bằng integration test. Dù một giới hạn `First`/`Top` được hỗ trợ, nó cũng không tạo continuation cookie để lấy page tiếp theo; khi cần kiểm soát rõ ràng, dùng `countLimit` qua `LdapQuery` hoặc search controls.

Do đó, không nên thiết kế repository như sau rồi mặc định nó chạy được như JPA:

```java
// Không coi đây là API paging/sorting được Spring LDAP repository hỗ trợ.
Page<DirectoryPerson> findBySn(
        String surname, Pageable pageable);

// Không coi Sort động là tính năng repository LDAP được bảo đảm.
List<DirectoryPerson> findBySn(
        String surname, Sort sort);
```

Các ví dụ `Pageable`, `Page`, `Slice`, `Sort` trong tài liệu Spring Data Commons mô tả abstraction chung. Tài liệu store-specific của Spring LDAP vẫn là nơi quyết định khả năng thực thi. Không suy diễn rằng một interface kế thừa `PagingAndSortingRepository` sẽ tự có server-side paging hoặc sorting khi backing store không hỗ trợ.

## 3. Phân biệt giới hạn số kết quả với phân trang

Ba khái niệm thường bị nhầm:

| Cơ chế | Ý nghĩa | Có lấy được trang tiếp theo? |
|---|---|---|
| `countLimit`/size limit | Dừng search khi đạt số entry tối đa | Không |
| Paged Results Control | Server trả kết quả theo từng lô và cấp cookie tiếp tục | Có, nếu server hỗ trợ và cookie còn hiệu lực |
| Cắt `List` trong Java | Tải kết quả rồi lấy một đoạn bằng `subList` | Chỉ là phân trang phía ứng dụng, không giảm dữ liệu đã tải |

Ví dụ:

```java
LdapQuery request = query()
        .base("ou=people")
        .searchScope(SearchScope.SUBTREE)
        .countLimit(100)
        .timeLimit(3000)
        .where("objectClass").is("inetOrgPerson");

List<DirectoryPerson> people =
        ldapTemplate.find(request, DirectoryPerson.class);
```

`countLimit(100)` giới hạn số entry mà search request được phép trả về. Nó **không có page number, offset hoặc cookie**. Nếu có 1.000 entry phù hợp, query này không cung cấp cách tiếp tục từ entry thứ 101.

Tương tự, code sau không phải server-side pagination:

```java
List<DirectoryPerson> all = repository.findBySn("Nguyen");

int from = pageNumber * pageSize;
int to = Math.min(from + pageSize, all.size());

List<DirectoryPerson> page = all.subList(from, to);
```

Directory server đã phải xử lý và client đã tải toàn bộ kết quả trước khi cắt danh sách. Cách này chỉ chấp nhận được với tập dữ liệu nhỏ, đã có giới hạn rõ và có lý do nghiệp vụ.

## 4. Paged Results Control theo RFC 2696

LDAP có extension **Simple Paged Results Manipulation**, được mô tả trong RFC 2696. Client gửi:

- Page size mong muốn.
- Cookie rỗng ở request đầu tiên.
- Cookie mới nhất server trả về ở request kế tiếp.

Server trả một tập entry cho page hiện tại và một cookie. Cookie là dữ liệu opaque do server tạo; client không được diễn giải nội dung hoặc tự tạo lại nó.

```text
Request 1: Search + PagedResults(size=100, cookie="")
                 │
                 ▼
        LDAP server trả 100 entry
                 │
                 └── cookie = C1
                         │
                         ▼
Request 2: Search + PagedResults(size=100, cookie=C1)
                 │
                 ▼
        LDAP server trả 100 entry tiếp theo
                 │
                 └── cookie = C2
                         │
                         ▼
                       ...
                         │
                         ▼
        Response cookie rỗng → hết page
```

Các quy tắc quan trọng:

1. Cookie phải được giữ nguyên như server trả về; không giải mã hoặc chỉnh sửa.
2. Request tiếp theo phải giữ các tham số search ban đầu giống nhau: base, filter, scope và các control liên quan. RFC cho phép đổi page size, nhưng không được đổi các tham số tìm kiếm tùy tiện.
3. Dùng cookie của response mới nhất, không quay lại cookie cũ.
4. Khi cookie rỗng, sequence đã hoàn tất và cookie không còn dùng được.
5. Server có thể từ chối cookie nếu trạng thái paging đã hết hạn hoặc không còn được lưu.
6. Ước lượng tổng số entry trong response là tùy chọn; giá trị 0 hoặc không có estimate không có nghĩa kết quả rỗng.
7. Nếu dữ liệu directory thay đổi trong lúc duyệt, client có thể nhận entry lặp hoặc bỏ sót theo giới hạn được RFC mô tả.

Paged results là một **sequence search có trạng thái**, không phải `OFFSET n LIMIT m` như SQL.

## 5. Dùng PagedResultsControlExchangeDirContextProcessor với Spring LDAP 4.1+

Spring LDAP 4.1 giới thiệu `PagedResultsControlExchangeDirContextProcessor`, một `DirContextProcessor` chuyên quản lý request/response controls cho paged results.

Ví dụ dưới đây minh họa cách đọc toàn bộ các page bằng cùng một LDAP context:

```java
import java.util.ArrayList;
import java.util.List;
import javax.naming.directory.SearchControls;

import org.springframework.ldap.control.PagedResultsControlExchangeDirContextProcessor;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.ContextSource;
import org.springframework.ldap.core.support.SingleContextSource;
import org.springframework.ldap.core.support.LdapOperationsCallback;

public class PagedPeopleReader {

    public record PersonSummary(
            String uid, String commonName, String email) {}

    private final ContextSource contextSource;

    public PagedPeopleReader(ContextSource contextSource) {
        this.contextSource = contextSource;
    }

    public List<PersonSummary> readAllActivePeople() {
        final int pageSize = 100;

        SearchControls controls = new SearchControls();
        controls.setSearchScope(SearchControls.SUBTREE_SCOPE);
        controls.setCountLimit(0);
        controls.setTimeLimit(5000);
        controls.setReturningAttributes(
                new String[] {"uid", "cn", "mail"});

        AttributesMapper<PersonSummary> mapper = attrs ->
                new PersonSummary(
                        attrs.get("uid") == null
                                ? null : (String) attrs.get("uid").get(),
                        attrs.get("cn") == null
                                ? null : (String) attrs.get("cn").get(),
                        attrs.get("mail") == null
                                ? null : (String) attrs.get("mail").get());

        PagedResultsControlExchangeDirContextProcessor paging =
                new PagedResultsControlExchangeDirContextProcessor(
                        pageSize);

        return SingleContextSource.doWithSingleContext(
                contextSource,
                (LdapOperationsCallback<List<PersonSummary>>) operations -> {
                    List<PersonSummary> result = new ArrayList<>();

                    do {
                        List<PersonSummary> onePage = operations.search(
                                "ou=people",
                                "(&(objectClass=inetOrgPerson)"
                                        + "(employeeStatus=active))",
                                controls,
                                mapper,
                                paging);

                        result.addAll(onePage);
                    } while (paging.hasMore());

                    return result;
                });
    }
}
```

Điểm cần hiểu trong ví dụ:

- `SearchControls` xác định scope, time limit và attribute cần trả về.
- `PagedResultsControlExchangeDirContextProcessor(100)` yêu cầu page size 100.
- `operations.search(..., paging)` gửi search kèm paging control.
- `paging.hasMore()` kiểm tra server có trả cookie tiếp theo hay không.
- `SingleContextSource.doWithSingleContext(...)` giữ cùng connection trong toàn bộ vòng lặp.
- Kết quả được gom thành `List` để minh họa. Nếu tập dữ liệu rất lớn, nên xử lý từng page và ghi vào nơi tiêu thụ thay vì giữ tất cả trong RAM.

`countLimit(0)` trong `SearchControls` không đặt một count limit tổng ở client. Server vẫn có thể áp dụng giới hạn quản trị riêng.

### Phiên bản Spring LDAP cũ hơn

`PagedResultsDirContextProcessor` được dùng trong các phiên bản trước Spring LDAP 4.1. Trong API mới, lớp này đã deprecated để chuyển sang `PagedResultsControlExchangeDirContextProcessor`. Hãy đối chiếu version dependency đã resolve trước khi copy import và code. Dù dùng processor nào, nguyên tắc quan trọng vẫn là giữ cùng connection cho toàn bộ sequence.

## 6. Vì sao paging cần cùng connection?

`LdapTemplate` thông thường lấy và đóng context sau mỗi operation. Nhưng paged-results cookie có thể gắn với trạng thái phía server của connection/session. Nếu mỗi page dùng một connection khác, server có thể không tiếp tục được sequence.

Spring LDAP cung cấp một số cách giữ connection:

- `SingleContextSource` để thực hiện nhiều thao tác trên cùng context.
- `ContextSourceTransactionManager` kết hợp `TransactionAwareContextSourceProxy` khi kiến trúc dùng transaction support phù hợp.
- Với Spring LDAP 4.1+, control processor cũng ghi rõ yêu cầu cùng LDAP connection cho các stateful controls.

Không tạo một processor mới cho mỗi page nếu làm mất trạng thái cookie. Không đưa cookie vào một worker khác đang dùng connection khác. Không lưu cookie rồi khởi tạo connection mới sau nhiều phút và mặc định nó vẫn còn hiệu lực.

### Cookie không phải offset

Cookie có thể là một chuỗi byte opaque, không phải số trang. Không được:

- Tự cộng/trừ cookie.
- Dùng cookie của user A cho user B.
- Đổi base/filter rồi tiếp tục bằng cookie cũ.
- Dùng cookie sau khi server trả cookie rỗng.
- Giả định cookie có thể dùng lại sau khi sequence đã kết thúc.
- Dựa vào cookie như một snapshot bất biến của directory.

## 7. Thiết kế API phân trang cho ứng dụng web

Một API REST thường muốn trả:

```json
{
  "items": [],
  "nextPageToken": "opaque-token",
  "hasMore": true
}
```

LDAP paging không tự cung cấp page number/offset. Với API web, backend cần quản lý trạng thái tiếp tục:

1. Xác thực caller và xác định tenant/base DN.
2. Chuẩn hóa filter, scope và sort policy.
3. Tạo paging sequence trên LDAP connection phù hợp.
4. Lưu continuation state ở server nếu cần đi qua nhiều HTTP request.
5. Trả token ứng dụng đã ký hoặc mã tham chiếu ngẫu nhiên tới trạng thái server-side.
6. Ở request kế tiếp, kiểm tra token gắn với principal, query signature, page size và thời hạn.
7. Tiếp tục sequence bằng đúng cookie và connection/session được giữ.
8. Khi hết dữ liệu hoặc token hết hạn, đóng/giải phóng state và connection.

**Không nhất thiết trả raw LDAP cookie cho browser.** Cookie có thể phụ thuộc session và server implementation. Token ứng dụng nên che giấu chi tiết LDAP và ràng buộc với user/tenant/query để tránh dùng nhầm continuation state.

Nếu triển khai nhiều instance backend, phải thiết kế session affinity hoặc lưu trạng thái điều phối sao cho instance tiếp theo có thể tiếp tục đúng LDAP connection. Một cookie không tự làm cho connection state được chuyển qua instance khác.

### Cursor API không tương đương PageRequest

`PageRequest.of(3, 50)` có offset 150. LDAP paged results thường dùng cookie tiếp tục. Một API cursor phù hợp hơn có dạng:

```java
public record DirectoryPageRequest(
        String continuationToken,
        int pageSize
) {}

public record DirectoryPage<T>(
        List<T> items,
        String nextContinuationToken,
        boolean hasMore
) {}
```

Đây chỉ là contract API. Backend phải giữ cookie và connection state đúng quy tắc; không thể chỉ lấy token rồi gọi `findAll()` lại từ đầu.

## 8. CountLimit, total count và Page<T>

Một `Page<T>` thường có:

- Content.
- Page number.
- Page size.
- Total elements.
- Total pages.

Để tạo total count, database thường chạy thêm `COUNT(*)`. LDAP có thể cung cấp estimate trong paged-results response, nhưng RFC 2696 cho phép server không biết hoặc không trả estimate. Vì vậy:

- Không coi estimate là tổng số chính xác được đảm bảo.
- Không suy ra total pages từ estimate nếu server không trả dữ liệu hợp lệ.
- Không chạy một search toàn bộ chỉ để đếm nếu số entry lớn.
- Nếu cần count chính xác, thiết kế một use case riêng và đánh giá chi phí/ACL/giới hạn.
- Với giao diện, `hasMore`/cursor thường thực tế hơn total page count.

`countLimit` của LDAP SearchControls là giới hạn số kết quả của một search request. Nó không thay thế paged-results control và không tạo metadata của `Page<T>`.

## 9. Sắp xếp: LDAP server-side sort control

LDAP không có thứ tự mặc định cho search result. Nếu không yêu cầu sort control, không nên giả định entry sẽ luôn trả theo:

- DN tăng dần.
- UID tăng dần.
- Thứ tự được tạo.
- Thứ tự lần trước server trả.
- Thứ tự giống một lần chạy test.

**Server-side sorting** được mô tả trong RFC 2891. Client gửi sort key gồm attribute và có thể có ordering rule/reverse order. Server trả response control riêng để báo kết quả sắp xếp.

Ví dụ yêu cầu sắp xếp theo họ, sau đó tên:

```text
Sort keys:
1. sn
2. givenName
```

Một số điều kiện:

- Attribute sort phải tồn tại và có ordering matching rule phù hợp.
- Server phải hỗ trợ sort control.
- Server có thể giới hạn số sort key hoặc từ chối sort vì tài nguyên.
- Kết quả sort có response code riêng, có thể lỗi dù search operation vẫn trả entry.
- Nếu control không critical, server có thể bỏ qua control không hỗ trợ; client phải kiểm tra response để biết có thực sự sorted hay không.
- Attribute đa trị và entry thiếu sort key có semantics riêng trong RFC; không giả định như sort cột SQL.

### Spring LDAP 4.1+: SortControlExchange

Spring LDAP 4.1 cung cấp `SortControlExchange` và `ControlExchangeDirContextProcessor`:

```java
import javax.naming.ldap.SortControl;
import javax.naming.ldap.SortResponseControl;

import org.springframework.ldap.control.ControlExchangeDirContextProcessor;
import org.springframework.ldap.control.SortControlExchange;

SortControlExchange exchange =
        new SortControlExchange("sn", "givenName");

ControlExchangeDirContextProcessor<SortControl, SortResponseControl>
        sortProcessor =
        new ControlExchangeDirContextProcessor<>(exchange);
```

Truyền `sortProcessor` vào overload search của `LdapTemplate`/`LdapOperations` nhận `DirContextProcessor`:

```java
List<PersonSummary> sortedPeople = ldapTemplate.search(
        "ou=people",
        "(&(objectClass=inetOrgPerson)(employeeStatus=active))",
        searchControls,
        mapper,
        sortProcessor);

SortResponseControl response =
        sortProcessor.getExchange().getResponse();

if (response == null || !response.isSorted()) {
    throw new IllegalStateException(
            "LDAP server did not confirm sorted results");
}
```

Ví dụ trên yêu cầu sort ascending theo các sort key do `SortControlExchange` tạo. Nếu nghiệp vụ cần chiều giảm dần, matching rule cụ thể hoặc sort key phức tạp, cần dùng control phù hợp với API/version của Spring LDAP và kiểm thử trên server đích.

### Không sort bằng Java sau mỗi page

Nếu tải từng page rồi sort mỗi page trong Java, kết quả toàn cục không được sắp xếp:

```text
Page 1: A, C, F  → sort riêng → A, C, F
Page 2: B, D, E  → sort riêng → B, D, E

Ghép hai page:
A, C, F, B, D, E
```

Kết quả trên không phải thứ tự toàn cục. Nếu cần thứ tự xuyên suốt các page, phải yêu cầu server sort toàn bộ result set bằng sort control kết hợp paged-results control, hoặc dùng một chiến lược khác có thể chứng minh thứ tự toàn cục.

## 10. Kết hợp sorting và paging

Khi gửi sort control cùng paged-results control:

- Sort key list phải được gửi trên mỗi page request.
- Sort key không được thay đổi giữa các request của cùng sequence.
- Server phải sort trên toàn bộ result set trước khi trả page, không chỉ sort từng page.
- Cookie paging phải tiếp tục trên cùng connection.
- Cần kiểm tra sort response và paging response.

Spring LDAP hỗ trợ kết hợp các `DirContextProcessor` bằng `AggregateDirContextProcessor`:

```java
import javax.naming.ldap.SortControl;
import javax.naming.ldap.SortResponseControl;

import org.springframework.ldap.control.ControlExchangeDirContextProcessor;
import org.springframework.ldap.control.PagedResultsControlExchangeDirContextProcessor;
import org.springframework.ldap.control.SortControlExchange;
import org.springframework.ldap.core.support.AggregateDirContextProcessor;

PagedResultsControlExchangeDirContextProcessor paging =
        new PagedResultsControlExchangeDirContextProcessor(100);

ControlExchangeDirContextProcessor<SortControl, SortResponseControl>
        sorting =
        new ControlExchangeDirContextProcessor<>(
                new SortControlExchange("sn", "givenName"));

AggregateDirContextProcessor controls =
        new AggregateDirContextProcessor();
controls.addDirContextProcessor(paging);
controls.addDirContextProcessor(sorting);
```

Dùng `controls` làm processor cho mỗi search trong cùng một `SingleContextSource` sequence. Sau khi nhận page cuối, kiểm tra sort response từ `sorting.getExchange().getResponse()` và xác minh server đã xác nhận sort.

Nếu server không hỗ trợ một trong hai control, hãy xử lý theo policy đã định. Không trả dữ liệu như thể đã được sort và paginate thành công khi server bỏ qua hoặc từ chối control.

## 11. Sort key, schema và dữ liệu thiếu

Sort không chỉ là chỉ định tên attribute. Server cần hiểu cách so sánh giá trị theo schema:

- Attribute có ordering matching rule phù hợp hay không?
- Có cần case-ignore ordering hay case-exact ordering?
- Giá trị có phải timestamp, integer, DN hay chuỗi?
- Attribute có nhiều giá trị không?
- Entry không có attribute được sort sẽ nằm ở đâu?
- Server có index hoặc giới hạn sort size không?

Ví dụ `sn` có thể có ordering behavior khác `createTimestamp` hoặc một custom numeric attribute. Nếu sort key không tồn tại hoặc matching rule không phù hợp, server có thể trả lỗi trong sort response control.

Không cho client truyền tên attribute tùy ý. Hãy ánh xạ API field sang allowlist:

```java
public enum PeopleSortField {
    SURNAME("sn"),
    GIVEN_NAME("givenName"),
    UID("uid");

    private final String ldapAttribute;

    PeopleSortField(String ldapAttribute) {
        this.ldapAttribute = ldapAttribute;
    }

    public String ldapAttribute() {
        return ldapAttribute;
    }
}
```

Nếu cần chiều sort hoặc nhiều key, xác định rõ danh sách key và hướng sort trong service. Không nối chuỗi từ query parameter thành LDAP control.

## 12. Các lựa chọn khi không thể dùng repository paging

Tùy nhu cầu, có một số cách xử lý:

| Nhu cầu | Cách phù hợp |
|---|---|
| Tìm một entry theo DN | `findById(Name)` hoặc `LdapTemplate.lookup` |
| Tìm theo thuộc tính với kết quả nhỏ | Repository query method trả `Optional<T>`/`List<T>` phù hợp |
| Giới hạn số entry của một search | `LdapQuery.countLimit(...)` hoặc `SearchControls.setCountLimit(...)` |
| Duyệt tập lớn theo từng page | `PagedResultsControl` qua `LdapTemplate` |
| Sắp xếp kết quả trên server | Server-side sort control qua `LdapTemplate` |
| Kết hợp page và sort | Paged Results + Sort control trên cùng sequence/connection |
| Tập dữ liệu nhỏ, không cần page server | Lấy đủ kết quả có giới hạn rồi sort trong Java |
| Browse toàn directory | Use case riêng, quyền riêng, base/scope chặt, paging và audit |

### Giới hạn số kết quả với LdapQuery

Nếu chỉ cần lấy tối đa một số entry, có thể đặt `countLimit`:

```java
LdapQuery limitedQuery = query()
        .base("ou=people")
        .searchScope(SearchScope.SUBTREE)
        .countLimit(50)
        .timeLimit(3000)
        .where("objectClass").is("inetOrgPerson");

List<DirectoryPerson> firstBatch =
        ldapTemplate.find(limitedQuery, DirectoryPerson.class);
```

Đây là một search có giới hạn. Nó không cho biết trang tiếp theo bắt đầu ở đâu và không bảo đảm thứ tự nếu không có sort control.

## 13. Những chức năng JPA không nên tự suy ra cho LDAP

| Thói quen từ JPA | Cách hiểu đúng trong LDAP |
|---|---|
| `JpaRepository.findAll(Pageable)` | `LdapRepository` không cung cấp paging trực tiếp theo tài liệu store-specific |
| `Sort.by("name")` | Không tự chuyển thành LDAP sort control |
| `Page<T>` có total pages | Paged-results estimate không bảo đảm tổng chính xác |
| `ORDER BY` trong JPQL | LDAP dùng server-side sort control và matching rule |
| `@OneToMany`/`@ManyToMany` | LDAP entry có attribute DN/group membership; cần truy vấn/ánh xạ riêng |
| Lazy loading quan hệ | Không có JPA persistence context để tự nạp relation |
| Cascade persist/remove | Không giả định ghi/xóa một entry sẽ cascade qua entry liên quan |
| Dirty checking | Thay đổi Java object không tự được đồng bộ về LDAP |
| `@Transactional` như database | Không suy ra transaction ACID nhiều LDAP entry |
| JPQL bulk update/delete | LDAP modify/delete theo entry và quyền ACL; cần xác định từng operation |
| SQL offset pagination | LDAP paged cookie là continuation state, không phải offset |
| Thứ tự kết quả ổn định | Search không có sort control thì không bảo đảm thứ tự |

Một query method được đặt tên giống Spring Data chung không có nghĩa mọi semantics database đều tồn tại. Hãy đọc tài liệu của đúng store và viết integration test trên directory thật.

## 14. QueryDSL không tự giải quyết paging/sorting

Spring LDAP có hỗ trợ QueryDSL predicate để xây điều kiện tìm kiếm. Điều đó hữu ích khi biểu thức filter phức tạp hoặc muốn type-safe hơn.

Tuy nhiên:

- QueryDSL predicate chỉ mô tả điều kiện truy vấn.
- Nó không tự tạo RFC 2696 paged-results sequence.
- Nó không tự gửi RFC 2891 sort control.
- Không suy ra `Pageable`/`Sort` được hỗ trợ chỉ vì repository có QueryDSL extension.
- Vẫn cần dùng Spring LDAP controls nếu use case cần server-side paging/sorting.

Phân biệt **cách biểu diễn filter** với **cách điều khiển search result**.

## 15. Những lỗi thường gặp khi xử lý kết quả lớn

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Dùng `Pageable` như JPA | Repository LDAP không có paging semantics tương ứng | Dùng Paged Results Control |
| Dùng `countLimit` như page size | Chỉ giới hạn một search, không có continuation | Dùng cookie paging |
| Mỗi page mở connection mới | Server có thể từ chối cookie | Giữ cùng connection bằng `SingleContextSource` hoặc transaction-aware proxy |
| Tạo processor mới cho mỗi page | Mất trạng thái cookie/control exchange | Dùng cùng processor trong sequence |
| Đổi filter/base/scope giữa page | Cookie không còn tương ứng query ban đầu | Giữ nguyên search parameters |
| Tự giải mã cookie | Vi phạm tính opaque | Chỉ giữ và gửi lại cookie |
| Coi result size estimate là total chính xác | UI hiển thị sai số trang | Dùng `hasMore`, xem estimate là optional |
| Sort từng page trong Java | Kết quả không được sort toàn cục | Dùng server-side sort control |
| Không kiểm tra sort response | Server có thể bỏ qua sort | Xác nhận response control |
| Sort attribute không có ordering rule | Sort thất bại hoặc không đúng kỳ vọng | Kiểm tra schema/matching rule |
| Lấy tất cả rồi `subList` | Tốn RAM và thời gian, server đã trả toàn bộ | Paging ngay tại LDAP |
| Browse ở root naming context | Có thể đọc dữ liệu vượt quyền | Giữ base DN/scope theo authorization |
| Không đóng stream/connection | Rò rỉ tài nguyên | Quản lý lifecycle và try/finally phù hợp |

## 16. Hiệu năng và giới hạn server

Paged results không làm cho một truy vấn rộng trở nên rẻ. Server vẫn phải đánh giá filter, ACL, index và sort key.

Trước khi bật paging/sorting:

1. Thu hẹp base DN và search scope.
2. Chọn filter đủ chọn lọc, có `objectClass` phù hợp.
3. Xác nhận attribute filter/sort có index nếu server hỗ trợ.
4. Chỉ yêu cầu attribute cần dùng.
5. Đặt page size vừa phải, đo latency và memory.
6. Đặt time limit và xử lý size/time limit exception.
7. Kiểm tra ACL, referral và giới hạn quản trị.
8. Giới hạn số paging sequence đồng thời để không tiêu tốn session state của server.
9. Dừng sequence đúng cách khi caller hủy hoặc rời màn hình.
10. Không chạy sort trên tập quá lớn nếu server không thể đáp ứng.

Server có thể áp dụng size limit nhỏ hơn page size, từ chối sort vì thiếu quyền hoặc trả unsupported control. Client cần phân biệt search result với response của từng control.

## 17. Kiểm thử paging và sorting

Không chỉ kiểm tra method trả về `List`. Cần xác minh protocol behavior và kết quả trên đúng directory server.

### Unit test

- Page size nằm trong giới hạn cấu hình.
- Query builder giữ nguyên base, scope và filter.
- Sort field được map qua allowlist.
- Sort direction không nhận raw LDAP syntax.
- API không chấp nhận page size âm hoặc quá lớn.
- Continuation token gắn với principal và query signature.
- Hủy sequence giải phóng tài nguyên.

### Integration test

Chuẩn bị ít nhất 250 entry để page size 100 tạo ra nhiều page:

| Ca test | Kỳ vọng |
|---|---|
| Không có entry phù hợp | Một page rỗng, không có page tiếp |
| Có 1 entry | Một page, cookie cuối rỗng |
| Có 250 entry, page size 100 | Ba page (100, 100, 50) nếu server hỗ trợ |
| Tiếp tục bằng cookie mới nhất | Lấy được page kế tiếp |
| Tiếp tục bằng cookie cũ | Không giả định được hỗ trợ; xác minh lỗi/behavior server |
| Thay filter giữa sequence | Sequence phải bị từ chối hoặc khởi tạo mới |
| Dùng connection khác | Kiểm tra server có từ chối cookie không |
| Server không hỗ trợ paged control | Xử lý unsupported/ignored theo criticality |
| Server không hỗ trợ sort | Không báo kết quả đã sorted |
| Sort response lỗi | Trả lỗi/diagnostic phù hợp |
| Sort + paging | Kiểm tra thứ tự toàn cục qua ranh giới page |
| Entry thiếu sort attribute | Xác minh vị trí theo semantics server/RFC |
| Directory thay đổi khi paging | Không giả định snapshot bất biến |
| Caller hủy | Đóng context và dừng sequence |
| ACL che entry/attribute | Không coi dữ liệu thiếu là kết quả đầy đủ |

### Ví dụ dữ liệu test

Tạo entry có họ theo thứ tự không liên tiếp, ví dụ:

- `uid=u1001`, `sn=Tran`
- `uid=u1002`, `sn=Nguyen`
- `uid=u1003`, `sn=Le`
- `uid=u1004`, `sn=Pham`

Khi sort ascending theo `sn`, kết quả phải là `Le`, `Nguyen`, `Pham`, `Tran` theo matching rule server. Hãy đặt entry ở hai page khác nhau để chứng minh server sort toàn bộ tập trước khi chia page.

## 18. Bài tập thực hành

Một API quản trị nhân viên cần hiển thị danh sách active users trong `ou=people`, 100 entry mỗi page, sắp xếp theo họ và tên.

Yêu cầu:

1. Tạo repository `PersonRepository extends LdapRepository<DirectoryPerson>` cho truy vấn nghiệp vụ nhỏ.
2. Không khai báo `Pageable`/`Sort` và kỳ vọng repository tự phân trang.
3. Viết service dùng `LdapTemplate`/`LdapOperations`.
4. Tạo `SearchControls` với `SUBTREE_SCOPE`, `timeLimit` và returning attributes.
5. Dùng `PagedResultsControlExchangeDirContextProcessor(100)`.
6. Dùng `SortControlExchange("sn", "givenName")`.
7. Kết hợp hai processor bằng `AggregateDirContextProcessor`.
8. Thực hiện toàn bộ sequence trong `SingleContextSource`.
9. Kiểm tra sort response control.
10. Thiết kế `DirectoryPage<T>` và continuation token ở tầng API.
11. Ràng buộc token với principal, tenant, base DN, filter và sort keys.
12. Kiểm thử page cuối, cookie hết hạn, server không hỗ trợ control, ACL và directory thay đổi trong sequence.

**Câu hỏi tự đánh giá:**

- Vì sao `countLimit(100)` không tương đương paged results?
- Vì sao page cookie không phải offset?
- Tại sao cần cùng connection khi tiếp tục paging?
- Vì sao `Page<T>` không thể được suy ra từ result size estimate?
- Vì sao sort từng page trong Java không tạo ra thứ tự toàn cục?
- Nếu sort control bị server bỏ qua, ứng dụng phải làm gì?
- Tại sao query method có tên `OrderBy...` vẫn cần kiểm tra store-specific support?

## 19. Checklist trước khi phát hành

- [ ] Đã kiểm tra tài liệu của đúng version Spring Data LDAP/Spring LDAP.
- [ ] Không giả định `LdapRepository` hỗ trợ `Pageable`, `Page`, `Slice` hoặc `Sort`.
- [ ] Không coi `countLimit` là paging.
- [ ] Đã chọn RFC 2696 Paged Results Control nếu cần duyệt tập lớn.
- [ ] Dùng cookie opaque mới nhất và giữ nguyên search parameters.
- [ ] Giữ cùng LDAP connection xuyên suốt paging sequence.
- [ ] Dùng processor/API phù hợp version Spring LDAP; không copy lớp deprecated vào version mới.
- [ ] Nếu sort, đã kiểm tra server hỗ trợ RFC 2891 sort control.
- [ ] Sort key được allowlist và có ordering matching rule phù hợp.
- [ ] Kiểm tra sort response control, không mặc định server đã sắp xếp.
- [ ] Khi kết hợp sort + paging, gửi sort key ổn định trên mọi page và xác minh thứ tự toàn cục.
- [ ] Không sort từng page riêng trong Java.
- [ ] Không tải toàn bộ directory chỉ để cắt page trong memory.
- [ ] Base DN, scope và filter tuân theo authorization/tenant boundary.
- [ ] Có timeout, page-size limit, server-limit handling và cancellation.
- [ ] Continuation token không lộ cookie tùy tiện và được ràng buộc với caller/query.
- [ ] Có integration test trên đúng sản phẩm/version directory.

### Tài liệu tham khảo

- [Spring LDAP Repositories](https://docs.spring.io/spring-ldap/reference/repositories.html) — lưu ý paging/sorting không được hỗ trợ bởi Spring LDAP repositories.
- [Spring Data LDAP Configuration](https://docs.spring.io/spring-data/ldap/reference/ldap/configuration.html) — repository setup, ODM và ID kiểu `Name`.
- [Spring LDAP — Processing the DirContext](https://docs.spring.io/spring-ldap/reference/processing-the-dircontext.html) — `DirContextProcessor` và paged search.
- [Spring LDAP API — PagedResultsControlExchangeDirContextProcessor](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/control/PagedResultsControlExchangeDirContextProcessor.html).
- [Spring LDAP API — SortControlExchange](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/control/SortControlExchange.html).
- [Spring LDAP API — ControlExchangeDirContextProcessor](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/control/ControlExchangeDirContextProcessor.html).
- [RFC 2696 — LDAP Control Extension for Simple Paged Results Manipulation](https://www.rfc-editor.org/rfc/rfc2696).
- [RFC 2891 — LDAP Control Extension for Server Side Sorting of Search Results](https://www.rfc-editor.org/rfc/rfc2891).

**Kết luận:** Spring Data LDAP repository giúp truy vấn entry theo ODM và method name, nhưng không tự mang theo paging/sorting semantics của JPA. Khi cần phân trang thật, dùng RFC 2696 và cookie tiếp tục trên cùng connection; khi cần thứ tự toàn cục, dùng RFC 2891 sort control và kiểm tra response từ server. Giữ base/scope/ACL chặt chẽ, giới hạn page size, xử lý connection/cookie đúng vòng đời và kiểm thử trên directory đích để ứng dụng không nhầm một danh sách bị cắt hoặc chưa sắp xếp với kết quả hoàn chỉnh.
