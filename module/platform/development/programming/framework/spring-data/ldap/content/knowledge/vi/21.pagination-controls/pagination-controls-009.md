# Phân biệt sắp xếp tại ứng dụng với sắp xếp toàn bộ kết quả

Trong **SPRING_DATA_LDAP**, ứng dụng Java (ví dụ dùng record của Java 16+ và Spring LDAP control API 4.1+) truy cập directory theo DN (*Distinguished Name*), `objectClass` và schema. Khi tìm danh sách người dùng, nhóm hoặc thiết bị, ứng dụng thường cần sắp xếp theo `cn`, `sn`, `uid` hay một thuộc tính nghiệp vụ. Điều quan trọng là phải xác định **tập dữ liệu nào đang được sắp xếp**: toàn bộ kết quả LDAP hay chỉ những entry đã tải về một trang.

Sắp xếp tại ứng dụng có thể dùng `Comparator` để sắp xếp một `List` Java. Cách này đúng với toàn bộ kết quả nếu ứng dụng đã lấy đầy đủ tất cả entry trước khi sort. Nếu ứng dụng chỉ tải một trang rồi sort trang đó, thứ tự chỉ đúng trong trang; khi nối các trang lại, toàn bộ danh sách có thể không còn được sắp xếp.

Sắp xếp phía LDAP server dùng **Server Side Sort control** trong SearchRequest. Khi kết hợp đúng với **Paged Results control**, server áp dụng sort trên toàn bộ tập kết quả trước khi chia thành các trang theo hành vi được RFC 2891 khuyến nghị. Đây là cách phù hợp khi cần hiển thị trang 1, trang 2... theo cùng một thứ tự toàn cục mà không tải tất cả entry về ứng dụng.

Sau bài này, bạn có thể:

- Phân biệt sort toàn bộ tập dữ liệu, sort một trang và sort tại giao diện.
- Giải thích vì sao sort từng trang không tạo ra thứ tự toàn cục.
- Chọn sort tại Java hay sort tại LDAP server theo kích thước dữ liệu và yêu cầu phân trang.
- Hiểu vai trò của RFC 2891 Server Side Sort và RFC 2696 Paged Results.
- Dùng Spring LDAP `SortControlExchange`, `ControlExchangeDirContextProcessor` và `PagedResultsControlExchangeDirContextProcessor`.
- Kiểm tra response control để biết server thực sự đã sort hay chưa.
- Tạo thứ tự ổn định bằng sort key phụ có tính duy nhất và xử lý dữ liệu thay đổi trong lúc phân trang.
- Nhận biết giới hạn của Spring Data LDAP Repository đối với sorting và paging.

## 1. Một yêu cầu sort có thể nói về ba tập dữ liệu khác nhau

Trước khi chọn API, hãy xác định rõ phạm vi sort.

| Cách làm | Tập dữ liệu được sắp xếp | Có bảo đảm thứ tự toàn cục? |
|---|---|---|
| Java sort toàn bộ kết quả đã tải | Tất cả entry ứng dụng đã lấy đủ | Có, trong tập đã tải đầy đủ |
| Java sort từng trang sau khi nhận | Chỉ các entry trong trang hiện tại | Không |
| LDAP Server Side Sort | Toàn bộ tập entry match SearchRequest | Có, nếu server xác nhận sort thành công |
| UI sort trên dữ liệu đang có | Những hàng đã tải vào trình duyệt | Chỉ trong tập đang có |

### 1.1. Ví dụ vì sao sort từng trang sai

Giả sử directory có năm người dùng và thứ tự toàn cục theo `cn` phải là:

```text
An, Binh, Chi, Dung, Hoa
```

Server trả kết quả theo thứ tự chưa sắp xếp, mỗi trang có ba entry:

```text
Trang 1 nhận được: Chi, Hoa, An
Trang 2 nhận được: Dung, Binh
```

Ứng dụng sort riêng từng trang:

```text
Trang 1 sau khi sort: An, Chi, Hoa
Trang 2 sau khi sort: Binh, Dung

Ghép hai trang:
An, Chi, Hoa, Binh, Dung
```

Mỗi trang đều tăng dần, nhưng toàn bộ danh sách không tăng dần: `Binh` đứng sau `Hoa` dù phải đứng trước. Nếu giao diện chuyển từ trang 1 sang trang 2, người dùng sẽ thấy thứ tự nhảy ngược.

Nếu lấy toàn bộ năm entry về rồi sort, Java có thể tạo thứ tự đúng `An, Binh, Chi, Dung, Hoa`. Nhưng với hàng trăm nghìn entry, việc lấy tất cả về chỉ để hiển thị trang đầu tiên sẽ tốn băng thông, bộ nhớ và thời gian.

### 1.2. Không có sort control thì không có thứ tự mặc định để dựa vào

LDAP Search không cam kết trả entry theo thứ tự DN, thứ tự thêm vào directory, thứ tự `cn` hoặc thứ tự vật lý trong backend. Nếu request không yêu cầu sort, thứ tự nhận được không phải một hợp đồng ổn định cho giao diện hoặc logic nghiệp vụ.

Đừng viết test chỉ tình cờ pass vì một directory test đang trả dữ liệu theo thứ tự chèn. Khi yêu cầu thứ tự có ý nghĩa, hãy chỉ rõ sort key và kiểm tra kết quả.

## 2. Sort tại ứng dụng: phù hợp với tập kết quả nhỏ và đầy đủ

Sort tại ứng dụng có nghĩa là:

1. Thực hiện LDAP Search.
2. Nhận tất cả entry cần thiết vào collection.
3. Ánh xạ entry sang object Java.
4. Dùng `Comparator` để sắp xếp collection.

### 2.1. Ví dụ sort một danh sách đã tải đầy đủ

Giả sử ứng dụng đã truy vấn đủ người dùng trong một OU và ánh xạ thành `PersonSummary`:

```java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

record PersonSummary(String uid, String cn) {}

class PersonDirectory {

    List<PersonSummary> sortAllByCommonName(
            List<PersonSummary> allPeople) {

        List<PersonSummary> sorted = new ArrayList<>(allPeople);

        Comparator<PersonSummary> byName =
                Comparator.comparing(
                        PersonSummary::cn,
                        Comparator.nullsLast(String.CASE_INSENSITIVE_ORDER))
                .thenComparing(
                        PersonSummary::uid,
                        Comparator.nullsLast(String.CASE_INSENSITIVE_ORDER));

        sorted.sort(byName);
        return sorted;
    }
}
```

Ở đây:

- `nullsLast` đưa entry không có `cn` xuống cuối.
- `CASE_INSENSITIVE_ORDER` so sánh chuỗi không phân biệt hoa/thường theo quy tắc của Java.
- `uid` là khóa phụ để phân biệt các entry có cùng `cn`.
- Copy sang `ArrayList` giúp không làm thay đổi collection do tầng gọi đang sở hữu.

`String.CASE_INSENSITIVE_ORDER` không phải collation theo ngôn ngữ. Nếu yêu cầu nghiệp vụ cần quy tắc dấu, thứ tự chữ cái tiếng Việt hoặc locale cụ thể, hãy định nghĩa `Collator` phù hợp và dùng nhất quán. Kết quả sort tại Java có thể khác LDAP server nếu matching rule/collation của schema khác.

### 2.2. Điều kiện để Java sort tạo thứ tự toàn cục

Sort tại ứng dụng chỉ tạo thứ tự toàn cục khi collection đầu vào chứa **toàn bộ entry thuộc tập kết quả cần sắp xếp**. Nếu collection bị giới hạn bởi:

- Một page duy nhất.
- `sizeLimit` hoặc count limit.
- Search scope quá hẹp.
- Referral chưa được theo.
- Một truy vấn chỉ lấy một phần OU.
- Một số entry bị bỏ qua do lỗi/partial result.

thì Java chỉ sort phần đã nhận. Comparator đúng không thể khôi phục các entry chưa được tải.

### 2.3. Chi phí và giới hạn

Với `n` entry:

- Bộ nhớ collection thường tăng theo `O(n)`.
- Sort so sánh thông thường cần khoảng `O(n log n)` phép so sánh.
- Ứng dụng phải nhận toàn bộ attribute cần map qua mạng trước khi sort.
- Thời gian phản hồi trang đầu phụ thuộc vào việc tải hết tập kết quả.

Sort local phù hợp khi:

- Tập dữ liệu nhỏ và có giới hạn rõ.
- Ứng dụng cần một phép sort tùy biến mà LDAP server không hỗ trợ.
- Dữ liệu đã được tải đầy đủ cho mục đích nghiệp vụ khác.
- Ứng dụng cần sort trên thuộc tính tính toán sau khi map sang object.

Không dùng cách này để giả lập phân trang toàn cục cho một directory lớn bằng cách tải toàn bộ entry vào mỗi request.

### 2.4. Không sort một trang rồi gắn nhãn như đã sort toàn bộ

Nếu nghiệp vụ thực sự chỉ cần sắp xếp nội bộ một trang, hãy mô tả rõ phạm vi, ví dụ "sắp xếp 50 kết quả hiện đang hiển thị". Đừng cung cấp API `findPageSorted(...)` khiến caller hiểu rằng page 2 là phần tiếp theo của cùng một thứ tự toàn cục.

Một nút sort trên UI cũng cần nói rõ nó đang sort toàn bộ dataset đã tải hay chỉ sort các hàng của trang hiện tại. Nếu server trả page tiếp theo, giao diện không thể tự đảm bảo thứ tự toàn cục bằng cách sort riêng page đó.

## 3. LDAP Server Side Sort: yêu cầu server sắp xếp toàn bộ Search result

RFC 2891 định nghĩa hai control:

- **Sort Key Request Control**: client gửi danh sách attribute và chiều sort mong muốn.
- **Sort Key Response Control**: server phản hồi sort thành công hay thất bại.

OID của request control là `1.2.840.113556.1.4.473`; OID của response control là `1.2.840.113556.1.4.474`.

Client có thể yêu cầu một hoặc nhiều sort key. Các key xuất hiện theo thứ tự ưu tiên cao xuống thấp. Ví dụ:

```text
Sort keys:
1. cn ASC
2. uid ASC
```

Server sắp xếp theo `cn`; nếu nhiều entry có cùng `cn`, dùng `uid` để phân định thứ tự trong nhóm đó.

### 3.1. Sort control không giống filter

Filter xác định entry nào được chọn. Sort control xác định thứ tự trả các entry đã match.

```text
SearchRequest
  base   = ou=people,dc=example,dc=org
  scope  = SUBTREE
  filter = (objectClass=inetOrgPerson)
  sort   = cn ASC, uid ASC
       |
       v
Server lọc entry theo filter
       |
       v
Server sắp xếp toàn bộ entry match theo sort keys
       |
       v
Server gửi SearchResultEntry theo thứ tự đã sort
```

Sort control không thay đổi filter, base DN hoặc scope. Nó cũng không có nghĩa server trả mọi attribute của entry; projection và ACL vẫn quyết định attribute nào được trả.

### 3.2. Server phải xác nhận đã sort

Không chỉ nhìn vào thứ tự vài entry đầu tiên để kết luận server đã thực hiện sort.

Theo RFC 2891:

- Nếu sort control không được hỗ trợ và request control là critical, server phải trả `unavailableCriticalExtension` và không trả search entries.
- Nếu control không critical, server có thể bỏ qua yêu cầu và xử lý Search như không có sort control.
- Nếu server không thể sort theo key được yêu cầu, response control chứa result code lỗi; với non-critical request, server có thể trả các entry không được sắp xếp.
- Client chỉ được bảo đảm kết quả đã sort khi `sortResult` trong response control là `success (0)`.
- Nếu response control bị thiếu, client nên giả định sort control đã bị bỏ qua.

Một số sort result code có thể gặp:

| Result code | Ý nghĩa |
|---|---|
| `success (0)` | Server đã sort theo key yêu cầu |
| `timeLimitExceeded (3)` | Không hoàn tất sort trước time limit |
| `strongAuthRequired (8)` | Server từ chối trả kết quả đã sort qua kết nối không đủ bảo mật |
| `adminLimitExceeded (11)` | Tập kết quả vượt giới hạn sort của server |
| `noSuchAttribute (16)` | Không nhận biết attribute trong sort key |
| `inappropriateMatching (18)` | Matching rule không phù hợp |
| `insufficientAccessRights (50)` | Không đủ quyền để sort |
| `busy (51)` | Server đang bận |
| `unwillingToPerform (53)` | Server từ chối thực hiện sort |

Search result code và sort result code là hai trạng thái riêng. Một Search có thể thành công nhưng sort control báo lỗi/không được thực hiện nếu control không critical.

### 3.3. Chọn sort key đúng schema

Sort key phải là attribute có ordering matching rule phù hợp với kiểu dữ liệu:

- `cn`, `sn`, `uid`: thường là chuỗi; cần kiểm tra ordering rule và matching rule server sử dụng.
- `employeeNumber`: nếu được định nghĩa là chuỗi, so sánh có thể là từ điển (`"100"` có thể đứng trước `"20"`), không phải số học.
- Timestamp/number: phải có schema và matching rule đúng với kiểu dữ liệu; không giả định mọi chuỗi số đều được so sánh như số.
- Attribute nhiều giá trị: RFC 2891 khuyến nghị server dùng giá trị nhỏ nhất theo ordering rule nếu không có control khác ảnh hưởng.
- Attribute thiếu: được xem như giá trị `NULL`; theo RFC 2891, `NULL` lớn hơn mọi giá trị hợp lệ khi sort tăng dần, và đi trước khi đảo chiều.

Hãy kiểm tra schema, dữ liệu và quyền ACL trên attribute sort key. Một attribute có thể không được phép đọc nhưng server cũng có thể từ chối sort theo attribute đó tùy implementation/policy.

### 3.4. Tạo thứ tự ổn định bằng khóa phụ

Sort theo một attribute không duy nhất, chẳng hạn `cn`, có thể tạo ra nhiều entry bằng nhau:

```text
cn=Lan Nguyen, uid=lan01
cn=Lan Nguyen, uid=lan02
cn=Lan Nguyen, uid=lan03
```

Nếu chỉ sort theo `cn`, thứ tự giữa ba entry này không được xác định bởi key. Khi người dùng đi qua các trang, thứ tự trong nhóm trùng có thể thay đổi giữa các lần thực hiện query.

Hãy thêm một key phụ có tính duy nhất trong phạm vi search:

```text
cn ASC, uid ASC
```

Nếu `uid` chỉ duy nhất trong một OU, nhưng SearchRequest bao phủ nhiều OU/tenant, hãy dùng key phụ đủ duy nhất trong toàn search scope, ví dụ một mã định danh duy nhất hoặc DN nếu server hỗ trợ ordering phù hợp. Không giả định mọi attribute mang tên `uid` là duy nhất trên toàn directory.

Thứ tự ổn định giúp phân trang dễ dự đoán hơn, nhưng không tạo snapshot transaction cho toàn bộ directory; phần dữ liệu thay đổi giữa các page vẫn có thể ảnh hưởng kết quả.

## 4. Kết hợp Server Side Sort với Paged Results

RFC 2696 định nghĩa Paged Results control để client yêu cầu server trả kết quả theo từng page. Server trả một cookie opaque; client gửi cookie đó trong SearchRequest tiếp theo để lấy phần kế tiếp của cùng chuỗi kết quả.

Khi kết hợp RFC 2891 Sort control và RFC 2696 Paged Results:

1. Server áp dụng sort keys trên toàn bộ tập kết quả theo hành vi được RFC 2891 khuyến nghị.
2. Server sau đó trả từng page từ tập đã sort.
3. Sort key list phải xuất hiện trong mỗi SearchRequest thuộc cùng chuỗi phân trang.
4. Sort key list không được thay đổi giữa các SearchRequest trong chuỗi đó.
5. Theo RFC 2891, server nên sort trên toàn bộ tập kết quả và không nên chỉ sort riêng từng page vì sẽ tạo kết quả sai cho client.

Ví dụ:

```text
Toàn bộ thứ tự sau server sort:
An, Binh, Chi, Dung, Hoa, Khoa, Lan

Page size = 3

Page 1: An, Binh, Chi
Page 2: Dung, Hoa, Khoa
Page 3: Lan
```

Khi ghép các page theo thứ tự cookie, ứng dụng vẫn nhận được thứ tự toàn cục.

### 4.1. Cookie không phải offset hoặc số trang

Paged Results cookie là dữ liệu opaque do server tạo. Client:

- Giữ nguyên cookie trả về ở page trước.
- Gửi cookie mới nhất trong request tiếp theo.
- Không giải mã, chỉnh sửa hoặc tự tạo cookie.
- Dừng khi server trả cookie rỗng/null, nghĩa là không còn page tiếp theo.

Cookie không cho phép client tùy ý nhảy đến page 20 như một offset SQL. Muốn quay lại trang trước, ứng dụng thường phải lưu kết quả/page đã nhận hoặc bắt đầu lại chuỗi Search theo cách server hỗ trợ.

### 4.2. Cùng một kết nối cho chuỗi paging

Paged Results cookie có thể gắn với trạng thái search của server và cần được tiếp tục trên cùng underlying LDAP connection. Spring LDAP đóng context sau mỗi lời gọi `LdapTemplate` theo cách thông thường, vì vậy phải giữ kết nối cho toàn bộ chuỗi page.

Spring LDAP cung cấp:

- `SingleContextSource` để giữ cùng một context trong callback.
- `ContextSourceTransactionManager` cùng `TransactionAwareContextSourceProxy` để dùng context trong một transaction.

Ví dụ bên dưới dùng `SingleContextSource`. Không mở một `SingleContextSource` mới cho từng page; phải bao toàn bộ vòng lặp paging trong một callback duy nhất.

### 4.3. Dùng Spring LDAP API hiện hành

Trong Spring LDAP hiện hành (API 4.1+), các class phù hợp là:

| Nhu cầu | API |
|---|---|
| Tạo sort request/nhận sort response | `SortControlExchange` |
| Gắn request control/đọc response control | `ControlExchangeDirContextProcessor` |
| Tạo paging request và theo dõi cookie | `PagedResultsControlExchangeDirContextProcessor` |
| Kết hợp nhiều control processor | `AggregateDirContextProcessor` |
| Giữ cùng kết nối qua các page | `SingleContextSource` |

Một số API cũ như `SortControlDirContextProcessor` và `PagedResultsDirContextProcessor` đã deprecated trong Spring LDAP hiện hành. Khi dự án đang dùng phiên bản cũ, hãy kiểm tra Javadoc đúng phiên bản; không trộn ví dụ giữa API cũ và API mới.

### 4.4. Ví dụ Spring LDAP: server sort và phân trang

Ví dụ dùng `LdapOperations`, sort theo `cn` rồi `uid`, page size 100. Hai context processor được kết hợp bằng `AggregateDirContextProcessor`.

```java
import java.util.ArrayList;
import java.util.List;

import javax.naming.directory.SearchControls;
import javax.naming.ldap.SortControl;
import javax.naming.ldap.SortResponseControl;

import org.springframework.ldap.control.ControlExchangeDirContextProcessor;
import org.springframework.ldap.control.PagedResultsControlExchangeDirContextProcessor;
import org.springframework.ldap.control.SortControlExchange;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.ContextSource;
import org.springframework.ldap.core.support.AggregateDirContextProcessor;
import org.springframework.ldap.core.support.LdapOperationsCallback;
import org.springframework.ldap.core.support.SingleContextSource;

record PersonSummary(String uid, String cn) {}

class SortedPersonSearch {

    private static final int PAGE_SIZE = 100;

    private final ContextSource contextSource;

    SortedPersonSearch(ContextSource contextSource) {
        this.contextSource = contextSource;
    }

    List<PersonSummary> findAllSorted() {
        SearchControls controls = new SearchControls();
        controls.setSearchScope(SearchControls.SUBTREE_SCOPE);
        controls.setReturningAttributes(new String[]{"uid", "cn"});

        AttributesMapper<PersonSummary> mapper = attrs -> {
            String uid = (String) attrs.get("uid").get();
            String cn = attrs.get("cn") == null
                    ? null
                    : (String) attrs.get("cn").get();
            return new PersonSummary(uid, cn);
        };

        return SingleContextSource.doWithSingleContext(
                contextSource,
                (LdapOperationsCallback<List<PersonSummary>>) operations -> {

                    List<PersonSummary> all = new ArrayList<>();

                    PagedResultsControlExchangeDirContextProcessor paging =
                            new PagedResultsControlExchangeDirContextProcessor(
                                    PAGE_SIZE);

                    do {
                        // Sort request phải có trong từng page request.
                        SortControlExchange sortExchange =
                                new SortControlExchange("cn", "uid");

                        ControlExchangeDirContextProcessor<
                                SortControl, SortResponseControl> sorting =
                                new ControlExchangeDirContextProcessor<>(
                                        sortExchange);

                        AggregateDirContextProcessor processors =
                                new AggregateDirContextProcessor();
                        processors.addDirContextProcessor(sorting);
                        processors.addDirContextProcessor(paging);

                        List<PersonSummary> page = operations.search(
                                "ou=people",
                                "(objectClass=inetOrgPerson)",
                                controls,
                                mapper,
                                processors);

                        SortResponseControl sortResponse =
                                sorting.getExchange().getResponse();

                        if (sortResponse == null && !page.isEmpty()) {
                            throw new IllegalStateException(
                                    "LDAP server returned entries without "
                                            + "a sort response control");
                        }
                        if (sortResponse != null
                                && sortResponse.getResultCode() != 0) {
                            String detail = "sort result code = "
                                    + sortResponse.getResultCode();
                            throw new IllegalStateException(
                                    "LDAP server did not confirm sorting: "
                                            + detail);
                        }

                        all.addAll(page);
                    } while (paging.hasMore());

                    return all;
                });
    }
}
```

Điểm cần chú ý:

- `SortControlExchange` được tạo lại cho mỗi page để kiểm tra response của đúng SearchRequest vừa chạy.
- Sort keys `cn`, `uid` không đổi giữa các page.
- `PagedResultsControlExchangeDirContextProcessor` được giữ lại trong vòng lặp để quản lý cookie giữa các page.
- `AggregateDirContextProcessor` áp dụng cả sort và paging control cho cùng một SearchRequest.
- `SingleContextSource` giữ cùng kết nối cho toàn bộ vòng lặp.
- Nếu page có entry nhưng server không gửi sort response control hoặc response không xác nhận thành công, ví dụ dừng thay vì âm thầm trả kết quả có thứ tự không được bảo đảm.

RFC 2891 cho phép server bỏ sort response control khi không có `SearchResultEntry` nào được trả. Vì vậy ví dụ không báo lỗi sort trong page rỗng; nếu page có entry mà thiếu response control, ứng dụng dừng vì không có bằng chứng thứ tự đã được bảo đảm.

Ví dụ trên gom tất cả page vào `List` để minh họa. Nếu ứng dụng chỉ cần hiển thị một page, có thể trả page hiện tại và cookie/continuation token đã được đóng gói ở tầng service; không cần giữ toàn bộ kết quả trong bộ nhớ. Tuy nhiên, sort control vẫn phải được gửi ở mỗi request page.

`LdapTemplate` cần được cấu hình với `LdapContextSource` để dùng LDAPv3 controls. Các control không hoạt động trên một `DirContext` thông thường không hỗ trợ `LdapContext`.

### 4.5. Đọc sort response control

`SortResponseControl` có các method:

- `isSorted()`: server xác nhận sort thành công.
- `getResultCode()`: result code của sort control; `0` nghĩa là thành công.
- `getAttributeID()`: attribute key gây lỗi nếu server trả về.
- `getException()`: exception tương ứng result code lỗi.

Không chỉ kiểm tra `LdapTemplate.search()` có trả list hay không. Search operation và sort control là hai kết quả riêng. Với sort control non-critical, server có thể trả entries không sort nhưng Search vẫn thành công.

Nếu server không hỗ trợ sort control, hãy quyết định rõ:

- Fail request và báo tính năng sort không khả dụng.
- Chuyển sang local sort chỉ khi đã tải đầy đủ toàn bộ tập kết quả và giới hạn tài nguyên cho phép.
- Dùng một API khác có thể cung cấp thứ tự toàn cục.

Không fallback sang sort từng trang rồi giữ nguyên nhãn "đã sắp xếp toàn bộ".

## 5. Spring Data LDAP Repository có hỗ trợ Sort/Pageable không?

Spring LDAP repository dựa trên ODM và DN làm identifier. Do đặc thù LDAP protocol, **Spring LDAP repositories không hỗ trợ paging và sorting** theo tài liệu chính thức.

Vì vậy, không giả định các method theo phong cách Spring Data JPA như:

```java
Page<Person> findByObjectClass(String objectClass, Pageable pageable);
List<Person> findByObjectClass(String objectClass, Sort sort);
```

sẽ tự sinh LDAP server-side sort/paged-results control. Với nhu cầu đó, dùng `LdapTemplate` hoặc `LdapClient` và quản lý controls rõ ràng.

Repository vẫn phù hợp với CRUD và query theo các khả năng được Spring LDAP hỗ trợ. Nếu cần trang kết quả có thứ tự toàn cục, hãy thiết kế lớp truy vấn LDAP riêng thay vì cố gắn `Pageable` vào repository.

## 6. So sánh hai phương án trong thực tế

| Tiêu chí | Sort tại ứng dụng | Server Side Sort |
|---|---|---|
| Phạm vi sort | Collection đã tải | Toàn bộ entry match trên server |
| Sort theo từng page | Chỉ trong page | Thứ tự toàn cục được duy trì khi kết hợp paging đúng |
| Bộ nhớ ứng dụng | Có thể lớn nếu tải hết | Có thể chỉ giữ một page |
| Băng thông | Phải tải mọi entry cần sort | Chỉ tải các page ứng dụng yêu cầu |
| CPU sort | Dùng CPU ứng dụng | Dùng tài nguyên LDAP server |
| Quy tắc so sánh | Java `Comparator`/`Collator` | Schema ordering matching rule của LDAP |
| Khả năng tùy biến | Cao, có thể sort theo giá trị tính toán | Giới hạn bởi attribute và matching rule server |
| Khả năng hỗ trợ | Luôn có nếu dữ liệu đã tải | Phụ thuộc server/control/ACL/configuration |
| Kiểm tra thành công | Kiểm soát collection đầy đủ | Phải kiểm tra sort response control |

### 6.1. Khi nào chọn sort tại ứng dụng?

Chọn sort tại Java khi:

- Tập dữ liệu nhỏ, có giới hạn và đã tải đầy đủ.
- Sort theo nhiều giá trị tính toán mà LDAP không lưu thành attribute.
- Cần một collation đặc biệt mà server không hỗ trợ.
- Ứng dụng đang xử lý toàn bộ danh sách cho một tác vụ batch.
- Có thể chấp nhận chi phí bộ nhớ và thời gian tải hết dữ liệu.

### 6.2. Khi nào chọn server-side sort?

Chọn server-side sort khi:

- Directory lớn và giao diện chỉ tải từng page.
- Người dùng cần chuyển trang nhưng thứ tự phải liên tục trên toàn bộ tập kết quả.
- Sort key là attribute LDAP có ordering rule phù hợp.
- Server hỗ trợ RFC 2891 sort control và RFC 2696 paged results.
- Server có đủ tài nguyên/quyền để thực hiện sort và trả response control thành công.

### 6.3. Khi server không hỗ trợ sort

Đừng tự động chọn một fallback sai semantics. Các lựa chọn hợp lý:

1. Nếu tập kết quả có giới hạn nhỏ, lấy đủ tất cả rồi sort local.
2. Nếu dataset lớn, cân nhắc thay đổi truy vấn/filter để giảm tập kết quả, bổ sung index hoặc cấu hình directory hỗ trợ sort.
3. Nếu sort theo một giá trị tính toán, cân nhắc duy trì attribute đã chuẩn hóa trong directory để server có thể sort.
4. Nếu cần phân trang toàn cục nhưng không có server sort, thay đổi kiến trúc hoặc trải nghiệm sản phẩm để không tuyên bố thứ tự toàn cục.

## 7. Tính ổn định khi dữ liệu thay đổi giữa các page

Paged Results duy trì trạng thái tiếp tục search bằng cookie, nhưng không đồng nghĩa server tạo snapshot transaction bất biến cho toàn bộ dữ liệu.

RFC 2696 nêu rõ nếu tập kết quả thay đổi kể từ SearchRequest khởi đầu, client có thể nhận một entry nhiều lần hoặc bỏ lỡ entry đáng lẽ match.

Ví dụ đang phân trang theo `cn ASC, uid ASC`:

```text
Ban đầu:
An, Binh, Chi, Dung, Hoa

Page 1:
An, Binh

Trong lúc người dùng đọc page 1:
Một entry mới "Ba" được thêm vào.
Một entry "Chi" đổi cn thành "A Chi".

Page 2:
Kết quả tiếp tục có thể phản ánh trạng thái mới,
không nhất thiết là snapshot tại thời điểm page 1.
```

Sort key duy nhất giúp thứ tự rõ ràng hơn, nhưng không loại bỏ ảnh hưởng của insert/delete/modify trong lúc paging.

Nếu nghiệp vụ yêu cầu báo cáo nhất quán tuyệt đối:

- Tạo snapshot/export ở tầng ứng dụng hoặc directory backend có hỗ trợ snapshot phù hợp.
- Giới hạn thời gian giữa các page và xử lý retry/expired cookie.
- Ghi nhận thời điểm truy vấn và trạng thái hoàn tất.
- Thiết kế tác vụ batch có thể chạy lại an toàn.

Không lưu cookie vô thời hạn hoặc dùng lại cookie sau khi chuỗi paging đã kết thúc. Cookie có thể hết hạn hoặc bị server loại bỏ.

## 8. Những chi tiết cần kiểm tra khi sort

### 8.1. Attribute sort key có trong schema

Server cần nhận biết attribute type và ordering matching rule. Nếu sort theo attribute không tồn tại trong schema hoặc matching rule không áp dụng, sort control có thể trả `noSuchAttribute` hoặc `inappropriateMatching`.

Đừng dùng tên thuộc tính tùy ý do client gửi vào mà không kiểm soát allowlist. Sort key phải là cấu hình do ứng dụng quản lý, không nhận tên attribute tùy ý từ query parameter bên ngoài.

### 8.2. Thứ tự null/missing value

Entry có thể không có attribute sort key. RFC 2891 quy định giá trị null được xếp sau các giá trị hợp lệ khi sort tăng dần; khi `reverseOrder` bật, null đi trước. Quy tắc cụ thể của server và matching rule cần được xác minh nếu nghiệp vụ phụ thuộc vị trí của dữ liệu thiếu.

### 8.3. Sort key nhiều giá trị

Một attribute LDAP có thể nhiều giá trị. RFC 2891 khuyến nghị server dùng giá trị nhỏ nhất theo ordering rule cho sort key đó nếu không có control khác ảnh hưởng. Nếu muốn sắp xếp theo một giá trị đơn nghĩa, hãy chọn attribute single-valued hoặc tạo attribute chuẩn hóa riêng.

### 8.4. Sort key và ACL

Một số server kiểm tra quyền truy cập trên sort key. Sort có thể thất bại do `insufficientAccessRights` dù filter và search bình thường vẫn chạy được. Không suy luận rằng có quyền đọc entry nghĩa là chắc chắn có quyền sort theo mọi attribute.

### 8.5. Criticality và fallback

Criticality của request control quyết định hành vi khi server không hỗ trợ hoặc không thể thực hiện control:

- Critical: client yêu cầu server phải thực hiện control; nếu không, Search có thể thất bại.
- Non-critical: server có thể bỏ qua control và tiếp tục Search mà không sort.

Nếu API/framework đang dùng không cho điều khiển criticality trực tiếp, hãy đọc request control thực tế và luôn xác minh response control. Không suy luận criticality chỉ từ tên class.

## 9. Những anti-pattern cần tránh

| Anti-pattern | Vấn đề | Hướng xử lý |
|---|---|---|
| Sort từng page rồi coi là global order | Thứ tự giữa các page không đúng | Sort toàn bộ trước khi paging hoặc tải đủ rồi local sort |
| Sort list đã bị size limit | Chỉ sort phần dữ liệu nhận được | Kiểm tra tính đầy đủ của search |
| Dựa vào thứ tự mặc định của LDAP | LDAP không cam kết thứ tự đó | Dùng sort control hoặc sort local trên full set |
| Chỉ kiểm tra Search result code | Sort control có thể thất bại riêng | Kiểm tra `SortResponseControl` |
| Bỏ qua cookie và gửi page mới bằng kết nối khác | Cookie paging có thể không tiếp tục được | Giữ cùng kết nối theo yêu cầu Spring LDAP/server |
| Thay sort key giữa các page | Chuỗi paged search không còn cùng một request | Giữ nguyên sort keys và các tham số search |
| Sort theo key không duy nhất | Thứ tự trong nhóm bằng nhau không ổn định | Thêm key phụ duy nhất |
| Dùng comparator Java nhưng mong khớp LDAP collation | Quy tắc so sánh khác nhau | Chọn một quy tắc nghiệp vụ và kiểm thử trên cả hai phía |
| Fallback sang sort từng page khi server sort lỗi | Tạo kết quả sai semantics | Fail rõ hoặc tải đủ toàn bộ rồi sort local |
| Giữ cookie sau khi hoàn tất search | Cookie đã hết hiệu lực | Bắt đầu chuỗi Search mới |
| Dùng Spring Data LDAP `Pageable` như JPA | Repository không hỗ trợ paging/sorting | Dùng `LdapTemplate` controls |

## 10. Checklist thiết kế phân trang có thứ tự

Trước khi đưa tính năng vào production, hãy xác nhận:

1. SearchRequest có base DN, scope và filter đúng.
2. Sort key là attribute có trong schema và có ordering rule phù hợp.
3. Sort keys có thứ tự ưu tiên rõ ràng; có key phụ duy nhất nếu cần.
4. Server hỗ trợ RFC 2891 sort control.
5. Sort response control xác nhận `success (0)` trên từng page.
6. Paged Results control được hỗ trợ và cookie được giữ nguyên.
7. Mọi page dùng cùng sort key list, base, scope, filter và các điều kiện tìm kiếm.
8. Spring LDAP dùng cùng underlying connection qua `SingleContextSource` hoặc transaction-aware context source.
9. Page size phù hợp với giới hạn server và khả năng xử lý của ứng dụng.
10. Có xử lý lỗi khi cookie hết hạn, server từ chối sort hoặc referral không hoàn tất.
11. Không giả định paging là snapshot bất biến khi dữ liệu đang thay đổi.
12. Nếu fallback sang local sort, đã tải đầy đủ tập kết quả và có giới hạn tài nguyên.
13. Không để client bên ngoài tự chọn attribute sort key ngoài allowlist.
14. Không cache kết quả có thứ tự giữa các filter, tenant hoặc authorization context khác nhau.

## 11. Câu hỏi tự đánh giá

1. Vì sao sort từng page không bảo đảm thứ tự toàn cục?
2. Khi nào Java sort có thể tạo thứ tự toàn cục chính xác?
3. LDAP Search có đảm bảo thứ tự entry nếu không gửi sort control không?
4. RFC 2891 định nghĩa request control và response control nào?
5. Vì sao phải kiểm tra `SortResponseControl` thay vì chỉ kiểm tra Search thành công?
6. `cn ASC, uid ASC` khác gì chỉ sort theo `cn`?
7. Khi kết hợp RFC 2891 với RFC 2696, server phải áp dụng sort ở phạm vi nào?
8. Vì sao sort key list phải giữ nguyên giữa các page request?
9. Vì sao Paged Results cookie không phải offset page number?
10. Spring LDAP cần cơ chế nào để giữ cùng kết nối giữa các page?
11. Vì sao Spring Data LDAP Repository không nhận `Pageable`/`Sort` như Spring Data JPA?
12. Dữ liệu thay đổi giữa các page có thể gây duplicate/missing entry như thế nào?
13. Khi server không hỗ trợ sort, những fallback nào vẫn đúng semantics?
14. Vì sao sort key không duy nhất có thể làm thứ tự giữa các trang khó dự đoán?

**Ghi nhớ:** sort ở Java chỉ sắp xếp collection đã tải; sort từng page chỉ sắp xếp nội bộ page. Nếu cần thứ tự toàn cục trên một tập kết quả lớn có phân trang, hãy yêu cầu LDAP server sort toàn bộ Search result bằng RFC 2891 rồi dùng RFC 2696 để lấy các page theo cookie. Giữ nguyên sort keys và SearchRequest, giữ cùng kết nối, và xác minh sort response control trước khi tuyên bố kết quả đã được sắp xếp.

### Tài liệu tham khảo

- IETF [RFC 2891 — LDAP Control Extension for Server Side Sorting of Search Results](https://www.rfc-editor.org/rfc/rfc2891): sort key request/response controls, criticality, sort result codes và yêu cầu sort toàn bộ tập kết quả khi kết hợp paging.
- IETF [RFC 2696 — LDAP Control Extension for Simple Paged Results Manipulation](https://www.rfc-editor.org/rfc/rfc2696): page size, opaque cookie, tiếp tục Search và ảnh hưởng khi result set thay đổi giữa các page.
- Spring LDAP Reference — [Processing the DirContext](https://docs.spring.io/spring-ldap/reference/processing-the-dircontext.html): `DirContextProcessor`, `PagedResultsControlExchangeDirContextProcessor`, cookie và giữ cùng kết nối bằng `SingleContextSource`.
- Spring LDAP API — [SortControlExchange](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/control/SortControlExchange.html): request/response exchange cho server-side sort.
- Spring LDAP API — [ControlExchangeDirContextProcessor](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/control/ControlExchangeDirContextProcessor.html): gắn request control và nhận response control.
- Spring LDAP API — [PagedResultsControlExchangeDirContextProcessor](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/control/PagedResultsControlExchangeDirContextProcessor.html): quản lý paged results và trạng thái còn page.
- Spring LDAP API — [AggregateDirContextProcessor](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/support/AggregateDirContextProcessor.html): kết hợp nhiều `DirContextProcessor`.
- Spring LDAP API — [SortResponseControl (Java SE)](https://docs.oracle.com/en/java/javase/23/docs/api/java.naming/javax/naming/ldap/SortResponseControl.html): kiểm tra `isSorted`, result code và attribute gây lỗi.
- Spring LDAP Reference — [Spring LDAP Repositories](https://docs.spring.io/spring-ldap/reference/repositories.html): giới hạn sorting và paging trong Spring LDAP repositories.
