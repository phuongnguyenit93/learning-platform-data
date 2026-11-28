# Không đồng nhất phân trang LDAP với Pageable của Repository

Khi làm việc với Spring Data, lập trình viên thường quen với repository nhận **Pageable** và trả về **Page<T>** hoặc **Slice<T>**. Nhưng **Spring Data LDAP không triển khai paging và sorting trực tiếp trên Spring LDAP repositories**. Tài liệu store-specific của Spring LDAP nêu rõ giới hạn này; không thể chỉ thêm tham số Pageable vào một query method rồi mong LDAP server tự hiểu page number, offset và total count như cơ sở dữ liệu quan hệ.

LDAP có cơ chế phân trang riêng: **Paged Results Control theo RFC 2696**. Cơ chế này dùng page size và cookie do server trả về để tiếp tục một search sequence. Cookie là opaque, gắn với request sequence và cần giữ cùng underlying LDAP connection giữa các lần gọi. Spring LDAP hỗ trợ cơ chế đó thông qua **PagedResultsControlExchangeDirContextProcessor** và **SingleContextSource**.

Bài thuộc chương **Phân trang và controls**, tập trung vào chủ đề **“Không đồng nhất phân trang LDAP với Pageable của Repository”**. Người học sẽ phân biệt abstraction của Spring Data với protocol control của LDAP, hiểu vì sao page number/offset không chuyển thẳng thành cookie, chọn đúng API cho repository và LdapTemplate, thiết kế cursor API và kiểm thử paging theo đúng directory server.

> **Nguyên tắc:** Pageable mô tả yêu cầu phân trang ở tầng Spring Data. Nó không tự thực hiện paging. Với LDAP, repository support không cung cấp paging/sorting trực tiếp; muốn server trả kết quả theo từng lô, ứng dụng phải dùng LDAP control và quản lý cookie/connection theo RFC 2696.

## 1. Vì sao Pageable không đồng nghĩa với LDAP paging?

Pageable thuộc Spring Data Commons. Nó mô tả một yêu cầu gồm:

- Page number, thường bắt đầu từ 0.
- Page size.
- Sort order.
- Offset được suy ra từ page number và page size.

Ví dụ:

```java
Pageable pageable = PageRequest.of(
        3,
        50,
        Sort.by("sn").ascending());
```

Yêu cầu này có nghĩa: lấy trang thứ 4, mỗi trang 50 phần tử, sắp xếp theo thuộc tính surname. Với một store hỗ trợ offset paging, offset được tính:

```text
offset = pageNumber × pageSize
       = 3 × 50
       = 150
```

LDAP Paged Results Control không nhận offset 150. Request gửi **page size** và **cookie**. Cookie được server cấp sau page trước, dùng để tiếp tục search sequence. Không có cookie tương đương với “bắt đầu tại entry thứ 151”.

```text
Spring Data Pageable
page = 3, size = 50, offset = 150
          │
          │ Không có phép chuyển đổi trực tiếp
          ▼
LDAP Paged Results
size = 50, cookie = opaque server token
```

Hai cơ chế đều có thể hiển thị dữ liệu thành nhiều trang, nhưng cách điều khiển và trạng thái tiếp tục hoàn toàn khác nhau.

## 2. Giới hạn được tài liệu Spring LDAP công bố

Tài liệu **Spring LDAP Repositories** nêu rõ:

- Repository cần entity được ánh xạ bằng ODM annotations.
- ID của ODM entity là Distinguished Name, kiểu javax.naming.Name.
- LdapRepository<T> có type parameter cho entity và mặc định ID là Name.
- Có thể kế thừa LdapRepository để hỗ trợ tham số LdapQuery trong repository infrastructure.
- Do đặc thù LDAP protocol, **paging và sorting không được hỗ trợ cho Spring LDAP repositories**.

Điều này quan trọng hơn việc nhìn thấy Pageable, Page hay Sort trong Spring Data Commons. Các type đó là abstraction dùng chung; từng store phải triển khai semantics tương ứng.

Ví dụ repository phù hợp cho truy vấn đơn giản, không yêu cầu repository paging:

```java
import java.util.List;
import org.springframework.data.ldap.repository.LdapRepository;

public interface PersonRepository
        extends LdapRepository<DirectoryPerson> {

    List<DirectoryPerson> findByUid(String uid);

    List<DirectoryPerson> findBySn(String surname);
}
```

Không thiết kế repository như một JpaRepository rồi giả định method dưới đây được Spring LDAP hỗ trợ:

```java
// Không coi chữ ký này là paging implementation của LDAP repository.
Page<DirectoryPerson> findBySn(
        String surname,
        Pageable pageable);
```

Ngay cả khi một chữ ký Java có thể được khai báo hoặc các type Spring Data Commons có sẵn trong classpath, điều đó không chứng minh store LDAP có thể thực thi nó. Hãy theo tài liệu repository của đúng store và kiểm thử trên version thực tế.

## 3. Phân biệt tầng web nhận Pageable với repository thực thi paging

Một controller Spring MVC có thể nhận tham số Pageable để parse query parameters như page, size và sort. Đây là công việc của web argument resolver. Nó chỉ chuyển HTTP request thành một object Java.

Ví dụ:

```java
@GetMapping("/people")
public ResponseEntity<?> search(Pageable pageable) {
    // pageable đã được Spring MVC tạo từ query parameters.
    // Nó chưa thực hiện bất kỳ LDAP search nào.
    return ResponseEntity.ok(
            "page=" + pageable.getPageNumber()
                    + ", size=" + pageable.getPageSize());
}
```

Có thể dùng Pageable ở tầng web để:

- Đọc page size mà UI yêu cầu.
- Kiểm tra giới hạn page size.
- Nhận biết client đang gửi page number hay sort request.
- Chuyển đổi request sang một contract cursor riêng.

Nhưng không được truyền thẳng object đó vào Spring LDAP repository và nghĩ rằng repository sẽ tự tạo RFC 2696 control. **Web support và datastore support là hai phần độc lập.**

Nếu endpoint nhận page=3&size=50 nhưng backend chỉ có cookie từ page trước, backend không thể nhảy trực tiếp tới offset 150. Nó cần tiếp tục tuần tự qua các cookie trước đó hoặc dùng một thiết kế khác.

## 4. Page, Slice và List mang các kỳ vọng khác nhau

Trong Spring Data:

| Kiểu kết quả | Metadata thường có | Kỳ vọng của caller |
|---|---|---|
| List<T> | Chỉ danh sách phần tử | Caller tự quản lý kết quả |
| Slice<T> | Nội dung, vị trí trang và có trang kế tiếp hay không | Điều hướng tuần tự, không cần total count |
| Page<T> | Nội dung, total elements và total pages | UI hiển thị tổng số trang và điều hướng theo page number |

Với Page<T>, infrastructure thường cần một count query để xác định tổng số phần tử. Với Slice<T>, infrastructure có thể đọc thêm một phần tử để xác định có trang tiếp theo.

LDAP Paged Results Control có response size estimate, nhưng RFC 2696 cho phép server trả 0 khi không thể cung cấp estimate. Đây không phải total count chính xác được đảm bảo.

Do đó:

- Không tạo Page<T> với total count giả định từ số entry của page hiện tại.
- Không coi estimate trong response control là tổng số chính xác.
- Không suy ra total pages nếu server không cung cấp total hợp lệ.
- Có thể thiết kế response cursor với hasMore mà không cần tổng số trang.
- Nếu sản phẩm bắt buộc có total count, phải thiết kế một thao tác count riêng và đánh giá chi phí, ACL, giới hạn server.

## 5. Phân biệt countLimit với paged results

Có ba khái niệm cần tách biệt:

| Cơ chế | Ý nghĩa | Tiếp tục từ vị trí trước? |
|---|---|---|
| SearchControls.setCountLimit(n) | Giới hạn số entry của một search request | Không |
| LdapQuery.countLimit(n) | Đặt count limit cho LDAP query | Không |
| RFC 2696 Paged Results Control | Server trả một page và cookie tiếp tục | Có |

Ví dụ đặt giới hạn search:

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

Query này yêu cầu tối đa 100 entry. Nếu có nhiều hơn, nó không trả cookie để lấy page tiếp theo.

Tương tự, SearchControls.setCountLimit(100) giới hạn số kết quả của search. Nó không tạo page number, offset, total count hay continuation state.

## 6. LDAP Paged Results Control hoạt động bằng cookie

RFC 2696 định nghĩa một control extension để server trả kết quả search thành từng lô. Request control chứa:

- size: số entry client muốn nhận trong page.
- cookie: cookie rỗng ở request đầu tiên, cookie server cấp ở các request tiếp theo.

Response control có thể chứa estimate về tổng số entry và cookie mới. Estimate là tùy chọn; cookie rỗng có nghĩa không còn page tiếp theo.

```text
Request đầu:
Search(base, scope, filter, size=50, cookie="")
                  │
                  ▼
             LDAP server
                  │
                  ▼
        50 entries + cookie C1
                  │
                  ▼
Request tiếp:
Search(cùng base/scope/filter, size=50, cookie=C1)
                  │
                  ▼
             LDAP server
                  │
                  ▼
        50 entries + cookie C2
                  │
                  ▼
                  ...
                  │
                  ▼
          cookie rỗng → hoàn tất
```

Cookie là dữ liệu **opaque**. Client phải giữ nguyên cookie do server trả về và gửi lại cookie mới nhất khi muốn lấy page kế tiếp.

## 7. Những gì cookie không cung cấp

Cookie không phải:

- Page number.
- Offset.
- Sort expression.
- Snapshot ID bảo đảm dữ liệu bất biến.
- Token có thể dùng với mọi connection hoặc mọi LDAP server.
- Cơ chế nhảy tùy ý đến page bất kỳ.
- Cam kết có thể dùng lại cookie cũ để quay về page trước.

RFC 2696 yêu cầu request tiếp theo giữ các giá trị của request ban đầu, ngoại trừ message ID, cookie và page size có thể thay đổi. Dùng cookie từ response cũ thay vì response mới nhất có behavior không được định nghĩa.

Khi cookie rỗng, sequence hoàn tất và cookie không còn được dùng lại. Nếu client muốn hủy sequence, RFC mô tả request paged-results với size bằng 0 và cookie cuối cùng; ứng dụng cần dùng API/control phù hợp với thư viện để thực hiện điều này.

Nếu dữ liệu directory thay đổi giữa các request, client có thể nhận entry lặp hoặc bỏ sót. Paged results không tự cung cấp snapshot isolation như một transaction database.

## 8. Vì sao paging cần cùng underlying LDAP connection?

LdapTemplate thông thường quản lý context cho từng operation. Tuy nhiên, paged-results sequence có thể gắn cookie với trạng thái trên connection/session. Vì vậy, các request tiếp tục phải dùng cùng underlying LDAP connection theo yêu cầu của Spring LDAP.

Spring LDAP cung cấp SingleContextSource để giữ cùng context trong một callback:

```java
SingleContextSource.doWithSingleContext(
        contextSource,
        operations -> {
            // Các lần operations.search(...) trong callback
            // sử dụng cùng underlying context.
            return null;
        });
```

Một cách khác là cấu hình ContextSourceTransactionManager và TransactionAwareContextSourceProxy phù hợp. Không mở một connection mới cho mỗi page rồi mong cookie cũ tiếp tục được.

Đây là khác biệt lớn với offset-based pagination: một query SQL page 4 thường có thể chạy độc lập với query page 1; LDAP paged-results sequence cần cookie mới nhất và connection phù hợp để tiếp tục.

## 9. Ví dụ paging với Spring LDAP 4.1+

Spring LDAP 4.1+ cung cấp PagedResultsControlExchangeDirContextProcessor. Class này quản lý request/response controls và cung cấp hasMore() để biết server có trả cookie tiếp tục hay không.

Ví dụ dưới đây xử lý từng page trong cùng callback, tránh gom toàn bộ entry vào một List lớn:

```java
import java.util.List;
import java.util.function.Consumer;
import javax.naming.directory.SearchControls;

import org.springframework.ldap.control.PagedResultsControlExchangeDirContextProcessor;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.ContextSource;
import org.springframework.ldap.core.support.LdapOperationsCallback;
import org.springframework.ldap.core.support.SingleContextSource;

public final class DirectoryPeoplePager {

    public record PersonSummary(
            String uid,
            String commonName,
            String email) {}

    private final ContextSource contextSource;

    public DirectoryPeoplePager(ContextSource contextSource) {
        this.contextSource = contextSource;
    }

    public void forEachPage(
            int pageSize,
            Consumer<List<PersonSummary>> pageConsumer) {

        if (pageSize < 1 || pageSize > 200) {
            throw new IllegalArgumentException(
                    "Page size must be between 1 and 200");
        }

        SearchControls controls = new SearchControls();
        controls.setSearchScope(SearchControls.SUBTREE_SCOPE);
        controls.setTimeLimit(5000);
        controls.setCountLimit(0);
        controls.setReturningAttributes(
                new String[] {"uid", "cn", "mail"});

        AttributesMapper<PersonSummary> mapper = attrs ->
                new PersonSummary(
                        attrs.get("uid") == null
                                ? null
                                : String.valueOf(attrs.get("uid").get()),
                        attrs.get("cn") == null
                                ? null
                                : String.valueOf(attrs.get("cn").get()),
                        attrs.get("mail") == null
                                ? null
                                : String.valueOf(attrs.get("mail").get()));

        PagedResultsControlExchangeDirContextProcessor paging =
                new PagedResultsControlExchangeDirContextProcessor(
                        pageSize);

        SingleContextSource.doWithSingleContext(
                contextSource,
                (LdapOperationsCallback<Void>) operations -> {
                    do {
                        List<PersonSummary> onePage = operations.search(
                                "ou=people",
                                "(&(objectClass=inetOrgPerson)"
                                        + "(employeeStatus=active))",
                                controls,
                                mapper,
                                paging);

                        pageConsumer.accept(List.copyOf(onePage));
                    } while (paging.hasMore());

                    return null;
                });
    }
}
```

Trong ví dụ:

1. pageSize được kiểm tra và giới hạn ở service.
2. SearchControls chọn SUBTREE, timeout và tập attribute cần trả.
3. PagedResultsControlExchangeDirContextProcessor giữ exchange/cookie.
4. SingleContextSource.doWithSingleContext bảo đảm các page dùng cùng connection.
5. operations.search(...) thực hiện từng page.
6. paging.hasMore() kiểm tra response cookie để tiếp tục.
7. pageConsumer xử lý từng page, không buộc giữ toàn bộ directory result trong RAM.

Import LdapOperationsCallback thuộc package org.springframework.ldap.core.support. Ví dụ dùng Spring LDAP 4.1+; ở dòng phiên bản cũ hơn, API processor có thể là PagedResultsDirContextProcessor. Hãy đối chiếu Javadoc của đúng dependency trước khi copy code.

## 10. Một lần gọi service có thể duyệt hết nhiều page

Ví dụ ở phần trước thực hiện cả sequence trong một callback. Điều này phù hợp với:

- Batch import/export có quyền phù hợp.
- Đồng bộ directory theo lịch.
- Xử lý từng page rồi ghi vào hệ thống khác.
- Tác vụ quản trị có thời gian chạy được kiểm soát.

Nó không nhất thiết phù hợp với một HTTP request phải trả về nhanh. Nếu search có hàng trăm nghìn entry, callback có thể giữ connection trong thời gian dài. Cần giới hạn thời gian, page size, concurrency, cancellation và tài nguyên server.

Nếu chỉ cần một page cho giao diện, việc giữ connection qua nhiều HTTP request sẽ khó hơn nhiều. Không đóng connection sau page 1 rồi mặc định cookie vẫn tiếp tục được ở một connection mới.

## 11. Vì sao không thể chuyển page number thành cookie?

Giả sử UI gửi:

```text
GET /people?page=4&size=50
```

Spring Data có thể biểu diễn offset 200. Nhưng LDAP chỉ có:

```text
pageSize = 50
cookie = cookie của page trước
```

Để đến page 4, client phải có chuỗi cookie từ những lần gọi trước trên cùng sequence. Không thể tính cookie từ số 4 hoặc offset 200.

Có thể chạy lại search từ đầu rồi tuần tự bỏ qua các page trước cho đến page 4. Tuy nhiên, cách này:

- Tốn nhiều request và thời gian khi page number lớn.
- Cần giữ cùng connection trong toàn bộ quá trình.
- Có thể trả dữ liệu khác nếu directory thay đổi giữa các lần search.
- Không có semantics random access như offset.
- Có thể tiêu tốn tài nguyên server chỉ để bỏ qua entry.

Vì vậy, không nên thiết kế API cursor LDAP bằng page number nếu mục tiêu là continuation hiệu quả.

## 12. Thiết kế cursor API thay cho PageRequest

Một API phù hợp với LDAP paging có thể nhận:

```json
{
  "pageSize": 50,
  "cursor": null
}
```

Và trả:

```json
{
  "items": [],
  "nextCursor": "opaque-application-token",
  "hasMore": true,
  "estimatedTotal": null
}
```

nextCursor nên là token do ứng dụng quản lý. Nó có thể tham chiếu đến continuation state được lưu server-side, hoặc chứa dữ liệu đã ký nếu thiết kế có thể bảo đảm an toàn.

Không mặc định đưa raw LDAP cookie trực tiếp cho browser. Cookie có thể gắn với connection và trạng thái server; một token HTTP không tự duy trì connection.

Token ứng dụng nên được ràng buộc với:

- Principal/caller đã xác thực.
- Tenant hoặc directory scope.
- Base DN và search scope.
- Filter đã chuẩn hóa.
- Sort keys nếu có.
- Page size hoặc policy cho phép thay đổi page size.
- Thời hạn và trạng thái sequence.
- ID của server-side session/connection state.

Không dùng token của một user để tiếp tục query của user khác.

## 13. Hai cách triển khai cursor qua HTTP

### Cách A: giữ paging session ở server

Backend giữ processor, cookie và underlying connection trong một session có giới hạn:

```text
HTTP request 1
      │
      ▼
Create paging session
      │
      ▼
Open LDAP connection
      │
      ▼
Read page 1 → return token T1
      │
      ▼
HTTP request 2 with T1
      │
      ▼
Resume same server-side session
      │
      ▼
Read page 2 → return token T2
      │
      ▼
Last page → close connection and delete session
```

Cách này giữ được sequence nhưng phải quản lý:

- TTL cho session bỏ quên.
- Số session paging đồng thời.
- Connection không được dùng đồng thời bởi nhiều request.
- Cleanup khi user logout hoặc request bị hủy.
- Sticky routing hoặc session storage phù hợp trong môi trường nhiều instance.
- Ràng buộc token với principal, query và tenant.
- Xử lý server restart, timeout và cookie hết hạn.

Đây là stateful design và có chi phí connection.

### Cách B: xử lý sequence trong một request/job rồi lưu kết quả

Backend chạy hết paging sequence trong một callback/job, sau đó ghi kết quả vào cache, staging table hoặc object store. UI phân trang trên dữ liệu đã materialize bằng page number/offset theo nhu cầu.

Cách này:

- Không giữ LDAP connection xuyên nhiều HTTP request.
- Có thể hỗ trợ next/previous/random page trên snapshot do ứng dụng tạo.
- Tốn dung lượng lưu kết quả và cần TTL/cleanup.
- Cần xác định snapshot freshness và quyền đọc dữ liệu đã materialize.

Chọn cách theo kích thước dữ liệu, latency, UX và giới hạn LDAP server.

## 14. Previous page và random access không phải khả năng mặc định

Paged Results Control chủ yếu cung cấp cookie để tiếp tục. Nó không cung cấp một API chuẩn để yêu cầu “quay lại page trước” hoặc “đến page 17”.

Nếu cần previous page:

- Có thể lưu các page đã nhận ở tầng ứng dụng.
- Có thể giữ các continuation state/cookie trước đó nếu server hỗ trợ behavior cần thiết, nhưng RFC không bảo đảm cookie cũ có thể dùng lại.
- Có thể materialize kết quả để UI điều hướng hai chiều.
- Không giả định một cookie trước đó là bookmark ổn định.

RFC 2696 quy định client gửi cookie mới nhất từ response trước. Dùng cookie từ response cũ hơn có behavior không được định nghĩa và có thể không hoạt động trên server cụ thể.

## 15. Sort trong Pageable cũng không tự chuyển thành LDAP sort control

Pageable thường chứa Sort. Ví dụ:

```java
Pageable pageable = PageRequest.of(
        0,
        50,
        Sort.by("sn").ascending()
                .and(Sort.by("givenName").ascending()));
```

Nhưng repository LDAP không hỗ trợ sorting trực tiếp. Muốn server sắp xếp, ứng dụng cần triển khai server-side sort control theo RFC 2891 và kiểm tra response từ server. Sort control là một LDAP control riêng; nó không được kích hoạt chỉ vì controller nhận được Sort.

Tên attribute sort phải nằm trong allowlist, tồn tại trong schema và có ordering matching rule phù hợp. Khi kết hợp sort với paged results, cần giữ sort keys ổn định trong sequence và xác nhận server thực sự chấp nhận sort.

Nếu chỉ sort từng page trong Java, thứ tự toàn cục không được đảm bảo.

## 16. Keyset pagination là một lựa chọn khác

Trong một số directory, có thể thiết kế continuation dựa trên giá trị cuối cùng của một thuộc tính ổn định, ví dụ UID:

1. Search page đầu với filter nghiệp vụ.
2. Sắp xếp theo UID bằng cơ chế được server hỗ trợ.
3. Lấy UID cuối cùng.
4. Page kế tiếp bổ sung điều kiện UID lớn hơn giá trị cuối.
5. Lặp lại với cùng base/scope và các điều kiện authorization.

Đây thường được gọi là keyset/seek pagination. LDAP có thể biểu diễn điều kiện ordering nếu attribute có matching rule phù hợp, nhưng đây là thiết kế riêng, không phải behavior chung của LdapRepository.

Cần kiểm tra:

- Attribute có ordering matching rule không.
- Giá trị có duy nhất không; nếu không, cần tie-breaker ổn định.
- Matching rule có phù hợp với thứ tự sort không.
- Giá trị có thể thay đổi giữa các page không.
- Directory có thay đổi khiến entry bị bỏ qua/lặp không.
- Filter có được index và server thực hiện hiệu quả không.

Không dùng keyset khi chưa chứng minh được ordering semantics và tính ổn định của key.

## 17. Tổng số entry và result size estimate

RFC 2696 cho phép server trả estimate về số entry phù hợp. Server không bắt buộc phải cung cấp estimate; giá trị 0 có thể có nghĩa server không biết estimate, không phải search không có kết quả.

Vì vậy:

| Giá trị | Có thể kết luận? |
|---|---|
| Response cookie rỗng | Không còn page tiếp theo trong sequence |
| Response cookie khác rỗng | Có thể tiếp tục search |
| Estimate lớn hơn 0 | Server đã cung cấp một estimate |
| Estimate bằng 0 | Không thể kết luận result set rỗng |
| Số entry trong page nhỏ hơn page size | Không tự kết luận đã hết page; kiểm tra cookie |
| Tổng số entry đã nhận | Số đã duyệt đến hiện tại, không phải total nếu còn cookie |

Nếu UI cần tổng số chính xác, có thể thực hiện một count/search riêng khi server và ACL cho phép, nhưng thao tác đó có thể tốn tài nguyên. Không giả lập total count bằng cách nhân page size với số page đã duyệt.

## 18. Hành vi khi server không hỗ trợ paging

Paged Results Control là extension; không phải mọi LDAP server đều hỗ trợ hoặc cấu hình nó giống nhau.

Theo RFC 2696:

- Nếu client đánh dấu control là critical và server không hỗ trợ, server phải trả lỗi unsupported critical extension.
- Nếu control không critical, server có thể bỏ qua control.
- Server có thể áp dụng size limit quản trị thấp hơn.
- Server có thể từ chối hoặc không tiếp tục một paging sequence đã hết hạn/không còn state.
- Một server có thể giới hạn số paging sequences đang mở cho cùng client.

Ứng dụng phải phân biệt:

- Server hỗ trợ paging và trả cookie.
- Server bỏ qua control.
- Server từ chối control.
- Search bị cắt bởi size/time limit.
- Cookie không còn tiếp tục được.
- Referral/partial result làm dữ liệu không đầy đủ.

Không fallback âm thầm sang tải toàn bộ directory nếu paging control không được hỗ trợ. Fallback phải có giới hạn và policy rõ ràng.

## 19. Hiệu năng và an toàn khi duyệt nhiều page

Paging giúp client xử lý dữ liệu theo lô, nhưng không làm một filter rộng trở nên rẻ. LDAP server vẫn phải đánh giá search base, scope, filter, ACL, index và sort key.

- Thu hẹp base DN và scope theo quyền.
- Dùng filter đủ chọn lọc và objectClass phù hợp.
- Chỉ yêu cầu attribute cần thiết.
- Giới hạn page size theo capacity đã đo.
- Đặt time limit và xử lý lỗi/partial result.
- Giới hạn số paging sequence đồng thời.
- Giải phóng connection khi hoàn tất hoặc hủy.
- Không để client tự thay đổi filter/base/scope khi tiếp tục cursor.
- Không ghi raw cookie hoặc dữ liệu cá nhân vào log thông thường.
- Không cho phép token cursor vượt tenant boundary.
- Đặt TTL và cleanup cho session paging bị bỏ quên.

Một page size quá lớn có thể tăng memory và latency; quá nhỏ lại tăng số round trip và thời gian giữ connection. Chọn bằng benchmark trên directory đích.

## 20. Kiểm thử để chứng minh hai cơ chế không bị nhầm

### Unit test ở tầng API/service

Kiểm tra:

1. Page size null/âm/0/quá lớn bị từ chối hoặc thay bằng default có quy định.
2. Token cursor không được dùng bởi principal khác.
3. Token bị từ chối nếu filter/base/tenant khác với query ban đầu.
4. Sort field chỉ nhận allowlist.
5. Không gọi repository với Pageable như thể LDAP hỗ trợ paging.
6. Khi không có cursor, service tạo paging sequence mới.
7. Khi cookie hết, service đóng/giải phóng sequence.
8. Khi caller hủy, connection và state được cleanup.

### Integration test với LDAP server

Chuẩn bị ít nhất 250 entry và page size 100:

| Ca kiểm thử | Kỳ vọng |
|---|---|
| 0 entry phù hợp | Không có page tiếp |
| 1 entry | Một page, cookie cuối rỗng |
| 250 entry | Ba page nếu server hỗ trợ (100, 100, 50) |
| Tiếp tục bằng cookie mới nhất | Nhận page tiếp theo |
| Dùng cookie cũ | Không giả định được hỗ trợ; xác minh behavior server |
| Đổi filter giữa sequence | Không tiếp tục sequence cũ |
| Đổi base/scope | Bắt đầu sequence mới |
| Dùng connection khác | Kiểm tra cookie có bị từ chối |
| Server không hỗ trợ control | Xử lý lỗi/ignored theo criticality |
| Size limit thấp hơn page size | Không coi kết quả là đầy đủ |
| Directory thay đổi giữa các page | Xác minh behavior lặp/bỏ sót |
| Nhiều sequence đồng thời | Kiểm tra resource limit |
| Caller hủy | Connection được đóng và state được xóa |

### Kiểm tra UI

- UI dùng next cursor thay cho page number nếu backend expose LDAP cursor.
- Không hiển thị total pages nếu chỉ có estimate tùy chọn.
- Nút Previous chỉ xuất hiện nếu ứng dụng có cache/materialize hoặc cơ chế điều hướng ngược đã được thiết kế.
- Loading/cancel state phản ánh đúng việc sequence đang chạy.
- Cursor hết hạn yêu cầu bắt đầu search mới, không tự fallback thành browse toàn directory.

## 21. Những lỗi thường gặp

| Lỗi | Vì sao sai | Cách sửa |
|---|---|---|
| Truyền Pageable thẳng vào LDAP repository | Repository LDAP không hỗ trợ paging trực tiếp | Dùng RFC 2696 qua LdapTemplate |
| Coi PageRequest.getOffset() là cookie | Offset và cookie không cùng semantics | Thiết kế cursor |
| Dùng countLimit làm page size | Không có continuation state | Paged Results Control |
| Tạo Page<T> từ một page | Thiếu total count đáng tin | Dùng cursor response hoặc count riêng |
| Coi estimate 0 là không có kết quả | Server có thể không cung cấp estimate | Dựa vào cookie và entries |
| Mở connection mới cho page kế tiếp | Cookie có thể không còn hiệu lực | Giữ cùng connection |
| Reuse cookie cũ để Previous | RFC không bảo đảm dùng lại cookie cũ | Cache page hoặc materialize kết quả |
| Sort theo Sort của Pageable | Không tự gửi LDAP sort control | Dùng server-side sort control riêng |
| Sort từng page trong Java | Không tạo thứ tự toàn cục | Sort toàn bộ search ở server |
| Dùng page number lớn để scan từ đầu | Tốn round trip và tài nguyên | Cursor hoặc keyset có kiểm chứng |
| Đưa raw LDAP cookie ra client | Lộ chi tiết protocol và connection state | Token ứng dụng ràng buộc caller/query |
| Nuốt partial result | Trả dữ liệu thiếu như đầy đủ | Phân loại lỗi và báo incomplete |

## 22. Bài tập thực hành

Một trang quản trị cần duyệt nhân viên active trong `ou=people`, 50 entry mỗi lần. Team hiện đang dùng:

```java
Page<DirectoryPerson> findByEmployeeStatus(
        String status,
        Pageable pageable);
```

Hãy thiết kế lại:

1. Giải thích vì sao chữ ký trên không tạo ra paging LDAP chỉ bằng Spring LDAP repository.
2. Tạo repository query method trả List<DirectoryPerson> cho các truy vấn nhỏ.
3. Viết service dùng LdapTemplate và PagedResultsControlExchangeDirContextProcessor.
4. Giữ cùng connection bằng SingleContextSource.
5. Xử lý từng page qua callback thay vì gom tất cả vào một List.
6. Thiết kế API response có items, nextCursor và hasMore.
7. Ràng buộc cursor với principal, tenant, base DN, filter và page size.
8. Không dùng Pageable.getOffset() để tạo cookie.
9. Nếu UI yêu cầu Previous/total pages, chọn cache/materialize hoặc một chiến lược khác có thể kiểm chứng.
10. Tạo 250 entry và kiểm thử ba page.
11. Mô phỏng server không hỗ trợ control và server trả size-limit error.
12. Kiểm thử cancellation, timeout và cleanup connection.

**Câu hỏi tự đánh giá:**

- Pageable khác LDAP Paged Results Control ở trường dữ liệu nào?
- Vì sao controller nhận được Pageable nhưng repository LDAP vẫn không hỗ trợ paging?
- Cookie do ai tạo và ai được phép diễn giải?
- Vì sao cần cùng connection giữa các page?
- Tại sao estimate 0 không có nghĩa result set rỗng?
- Vì sao Previous/last page khó thực hiện với cookie?
- Khi nào nên materialize kết quả thay vì giữ connection xuyên HTTP requests?

## 23. Checklist trước khi phát hành

- [ ] Đã đọc tài liệu repository của đúng version Spring LDAP/Spring Data LDAP.
- [ ] Không giả định LdapRepository hỗ trợ Pageable, Page, Slice hoặc Sort.
- [ ] Phân biệt web argument resolver với datastore paging implementation.
- [ ] Không chuyển Pageable.getOffset() thành LDAP cookie.
- [ ] Không coi countLimit là paged results.
- [ ] Dùng RFC 2696 khi cần server trả kết quả theo page.
- [ ] Giữ cookie opaque và chỉ dùng cookie mới nhất.
- [ ] Giữ nguyên base/filter/scope giữa các request tiếp tục.
- [ ] Duy trì cùng underlying connection cho paging sequence.
- [ ] Giới hạn page size, time limit, concurrency và session TTL.
- [ ] Không coi result size estimate là total count chính xác.
- [ ] Thiết kế cursor API nếu UI cần điều hướng tuần tự.
- [ ] Ràng buộc token với principal, tenant và query signature.
- [ ] Có giải pháp riêng cho Previous/random access nếu sản phẩm cần.
- [ ] Dùng server-side sort control riêng nếu cần sorting.
- [ ] Kiểm tra server capability, unsupported control và size/time limit.
- [ ] Không fallback âm thầm sang search toàn directory.
- [ ] Có integration test trên đúng sản phẩm/version LDAP.
- [ ] Đóng connection và xóa paging state khi hoàn tất, timeout hoặc cancellation.

### Tài liệu tham khảo

- [Spring LDAP Repositories](https://docs.spring.io/spring-ldap/reference/repositories.html) — giới hạn paging/sorting của repository.
- [Spring LDAP — Processing the DirContext](https://docs.spring.io/spring-ldap/reference/processing-the-dircontext.html) — paged search và giữ cùng connection.
- [Spring LDAP API — PagedResultsControlExchangeDirContextProcessor](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/control/PagedResultsControlExchangeDirContextProcessor.html).
- [Spring LDAP API — SingleContextSource](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/support/SingleContextSource.html).
- [Spring Data LDAP — Configuration](https://docs.spring.io/spring-data/ldap/reference/ldap/configuration.html).
- [Spring Data Commons — Paging and Sorting](https://docs.spring.io/spring-data/commons/reference/repositories/core-extensions.html).
- [RFC 2696 — LDAP Control Extension for Simple Paged Results Manipulation](https://www.rfc-editor.org/rfc/rfc2696).

**Kết luận:** Pageable mô tả page number, size và sort ở tầng Spring Data; LDAP Paged Results Control dùng page size và cookie tiếp tục do server cấp. Spring LDAP repositories không hỗ trợ paging trực tiếp, nên không thể biến offset thành cookie hoặc suy ra Page<T> chỉ từ một page response. Hãy dùng LdapTemplate với RFC 2696, giữ cùng connection trong sequence, thiết kế cursor nếu cần giao diện next-page và kiểm thử behavior trên directory thực tế.
