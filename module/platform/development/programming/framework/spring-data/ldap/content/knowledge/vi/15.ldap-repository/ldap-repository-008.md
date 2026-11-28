# Thao tác nhiều entry và số yêu cầu LDAP phát sinh

> **Chương:** LDAP Repository  
> **Module:** SPRING_DATA_LDAP — truy cập dịch vụ thư mục LDAP qua Spring Data LDAP, ánh xạ entry phân cấp sang đối tượng Java, truy vấn qua repository/LdapTemplate và thực hiện CRUD an toàn.

Khi ứng dụng xử lý một danh sách vài trăm hoặc vài nghìn người dùng, câu hỏi không chỉ là repository có phương thức `saveAll()` hay `findAllById()` không, mà còn là **mỗi lời gọi tạo ra bao nhiêu LDAP request**, server trả bao nhiêu entry, có phát sinh thêm truy vấn cho từng entry hay không, và số lượt trao đổi ảnh hưởng thế nào tới latency.

LDAP là giao thức client–server. Một SearchRequest có thể trả về nhiều entry trong cùng một lượt tìm kiếm; ngược lại, Add, Modify và Delete thông thường tác động tới **một entry được chỉ định**. Vì vậy, đọc nhiều entry có thể gộp điều kiện thành một SearchRequest, trong khi ghi hoặc xóa nhiều entry thường cần nhiều LDAP operation riêng.

Spring Data LDAP cung cấp abstraction repository để thao tác entity, nhưng **tên phương thức tiện lợi không tự đồng nghĩa với một lệnh bulk ở tầng giao thức**. Cần hiểu request/response, kiểm tra implementation theo phiên bản Spring Data LDAP đang dùng và đo trên directory thực tế.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt số lần gọi Java repository, số LDAP request, số response message và số entry kết quả.
2. Ước lượng request count cho `findById`, `findAll`, `findAllById`, `saveAll` và `deleteAll`.
3. Nhận biết N+1 LDAP operations khi đọc danh sách rồi lookup từng entry.
4. Dùng một SearchRequest với filter kết hợp để lấy nhiều entry theo danh sách khóa.
5. Phân trang kết quả bằng LDAP paged results control khi server hỗ trợ.
6. Hiểu vì sao nhiều thao tác ghi/xóa trên nhiều DN vẫn thường là nhiều LDAP requests.
7. Chọn `LdapRepository` hay `LdapTemplate` theo yêu cầu và giới hạn số request.
8. Thiết kế giới hạn kích thước batch, timeout, retry, idempotency và concurrency.
9. Kiểm thử và quan sát request count ở tầng LDAP, không chỉ đếm số lần gọi method Java.

## 2. Phân biệt các loại “số lượng”

Một API Java có thể chỉ được gọi một lần nhưng tạo ra nhiều LDAP requests; một LDAP SearchRequest lại có thể trả về hàng trăm entry.

| Khái niệm | Ví dụ | Cách hiểu |
|---|---|---|
| Java method call | `repository.findAll()` | Một lần gọi phương thức ứng dụng |
| LDAP request operation | SearchRequest, AddRequest, ModifyRequest, DeleteRequest | Một yêu cầu giao thức gửi tới directory |
| LDAP response message | SearchResultEntry, SearchResultDone, SearchResultReference | Các phản hồi cho một search hoặc operation |
| Entry returned | 500 nhân viên từ một search | Số đối tượng dữ liệu, không phải số request |
| Network round trip | Client gửi request và nhận phản hồi | Phụ thuộc connection, latency và cách trao đổi |
| TCP connection | Kết nối LDAP được mở hoặc tái sử dụng | Không bằng số LDAP operations |

Ví dụ:

~~~text
Ứng dụng gọi một lần:
  ldapTemplate.search(...)

LDAP protocol:
  1 SearchRequest
  500 SearchResultEntry
  1 SearchResultDone
~~~

Đây vẫn là **một SearchRequest**, dù server trả về nhiều response messages và nhiều entry. Nếu bật phân trang, một truy vấn logic có thể cần nhiều SearchRequest, mỗi request lấy một trang.

Một điểm quan trọng khác: LDAP protocol không có operation chuẩn tên `LookupRequest`. Khi ứng dụng gọi `LdapTemplate.lookup(...)`, JNDI provider thực hiện ngữ nghĩa đọc entry qua các thao tác LDAP phù hợp, thường là search scope `baseObject`; cần đo trên provider thực tế thay vì giả định số request chỉ từ tên method.

## 3. LDAP operation tác động tới một hay nhiều entry?

Các operation cơ bản có phạm vi khác nhau:

| LDAP operation | Phạm vi thông thường | Có thể trả nhiều entry? |
|---|---|---|
| Search | Một base, scope và filter | **Có**, trả nhiều entry phù hợp |
| Add | Một DN mới | Không |
| Modify | Một DN | Không; có thể chứa nhiều ModificationItem cho cùng entry |
| Delete | Một DN | Không |
| ModifyDN | Một entry được đổi RDN/vị trí | Không |
| Compare | Một DN và một assertion | Không |

Vì vậy:

- Một SearchRequest có thể đọc nhiều người dùng nếu filter và scope phù hợp.
- Một ModifyRequest có thể cập nhật nhiều attribute trên **cùng một entry**.
- Sửa email cho 100 DN khác nhau thường cần 100 ModifyRequests.
- Xóa 100 entry khác nhau thường cần 100 DeleteRequests.
- LDAP không cung cấp một bulk CRUD request tổng quát để gửi danh sách 100 DN trong một operation chuẩn.

Có các extension hoặc tính năng riêng của một số directory, nhưng không được mặc định rằng `LdapRepository`/`LdapTemplate` tự sử dụng chúng. Đặc biệt, atomicity của nhiều thay đổi trong **một ModifyRequest** không phải transaction cho nhiều entry.

## 4. Ước lượng request count cho các thao tác repository

Bảng sau mô tả **mô hình thường gặp để lập kế hoạch**, không thay thế việc kiểm tra source/trace của đúng phiên bản Spring Data LDAP đang chạy.

| Phương thức/luồng | Mô hình LDAP thường gặp | Ước lượng ban đầu |
|---|---|---:|
| `findByUid(uid)` | Một SearchRequest theo filter UID | 1 search |
| `findAll()` | Một SearchRequest cho phạm vi repository | 1 search nếu không phân trang/tiếp tục |
| `findById(id)` | Đọc entry theo DN, thường là base-scope read/search | Khoảng 1 read |
| Gọi `findById` trong vòng lặp N ID | Một lần đọc cho mỗi ID | Khoảng N reads |
| `findAllById(ids)` | Có thể lặp từng ID tùy implementation | Kiểm tra phiên bản; có thể N reads |
| `save(entity)` | Add hoặc thao tác ghi theo semantics repository/ODM | Ít nhất một write operation cho entry trong luồng ghi |
| `saveAll(entities)` | Thường xử lý từng entity; không có bulk Add chuẩn | Có thể N writes |
| `deleteById(id)` | Xóa một DN | 1 DeleteRequest |
| Xóa N ID riêng lẻ | Một DeleteRequest cho mỗi DN | N deletes |
| `deleteAll(entities)` | Thường lặp thao tác xóa từng entity | Có thể N deletes |
| Search rồi lookup chi tiết từng kết quả | Một search cộng N lần đọc | 1 + N reads |

**Vì sao chỉ ghi “ước lượng”?** Spring Data LDAP có thể thay đổi implementation giữa phiên bản; repository base class, mapping entity, kiểm tra tồn tại, exception handling, referrals và connection provider đều có thể làm số operation thực tế khác nhau. Tài liệu API của một method không nhất thiết cam kết số LDAP requests. Khi hiệu năng quan trọng, đo bằng LDAP server logs/protocol trace hoặc instrumentation ở client.

## 5. Một SearchRequest trả nhiều entry: cách đọc hiệu quả

Giả sử cần lấy hồ sơ 3 nhân viên theo UID:

~~~text
lan
binh
minh
~~~

Cách đơn giản nhưng tốn request:

~~~java
List<PersonSummary> people = new ArrayList<>();

for (String uid : uids) {
    repository.findByUid(uid).forEach(people::add);
}
~~~

Nếu mỗi finder tạo một search, ba UID sẽ tạo ba SearchRequests. Với N UID, request count tăng theo N.

Nếu cần tìm nhiều UID trong cùng OU, có thể xây một filter OR:

~~~text
(&
  (objectClass=inetOrgPerson)
  (|(uid=lan)(uid=binh)(uid=minh))
)
~~~

Một SearchRequest có thể trả tất cả entry phù hợp. Khi dùng `OrFilter` và `EqualsFilter` của Spring LDAP, giá trị assertion được encode theo cú pháp filter:

~~~java
import java.util.List;

import org.springframework.ldap.filter.AndFilter;
import org.springframework.ldap.filter.EqualsFilter;
import org.springframework.ldap.filter.OrFilter;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;

public List<PersonSummary> findPeopleByUids(
        LdapTemplate ldapTemplate,
        List<String> uids) {

    if (uids == null || uids.isEmpty()) {
        return List.of();
    }

    OrFilter anyUid = new OrFilter();

    for (String uid : uids) {
        if (uid == null || uid.isBlank()) {
            throw new IllegalArgumentException("UID must not be blank");
        }
        anyUid.or(new EqualsFilter("uid", uid));
    }

    AndFilter filter = new AndFilter();
    filter.and(new EqualsFilter("objectClass", "inetOrgPerson"));
    filter.and(anyUid);

    return ldapTemplate.search(
            "ou=people",
            filter.encode(),
            (AttributesMapper<PersonSummary>) attrs ->
                    new PersonSummary(
                            requiredText(attrs, "uid"),
                            requiredText(attrs, "cn"),
                            requiredText(attrs, "sn")));
}

private static String requiredText(
        javax.naming.directory.Attributes attrs,
        String name) throws javax.naming.NamingException {

    javax.naming.directory.Attribute attribute = attrs.get(name);
    if (attribute == null || attribute.size() != 1) {
        throw new IllegalStateException(
                "Missing or ambiguous LDAP attribute: " + name);
    }

    Object raw = attribute.get();
    if (!(raw instanceof String text)) {
        throw new IllegalStateException(
                "Expected text value for LDAP attribute: " + name);
    }
    return text;
}

public record PersonSummary(String uid, String cn, String sn) {
}
~~~

Trong ví dụ, `EqualsFilter` và `OrFilter` xây biểu diễn filter thay vì nối chuỗi từ dữ liệu người dùng. Search base `ou=people` là DN tương đối với base đã cấu hình trong `ContextSource`.

**Request count:** với danh sách UID nhỏ và không phân trang, đây thường là một SearchRequest, thay vì N search. Server vẫn trả một response entry cho mỗi người và một kết thúc search. Nếu UID không duy nhất trong search base, kết quả có thể có nhiều entry cho một UID; ứng dụng cần xử lý rõ điều đó.

### Khi nào không nên dùng một OR filter quá lớn?

Một filter có hàng nghìn nhánh OR có thể:

- Vượt giới hạn kích thước filter/request của server hoặc proxy.
- Làm query planning/index kém hiệu quả.
- Tăng CPU và bộ nhớ của directory.
- Tạo response quá lớn.
- Khó retry hoặc phân tích khi một phần dữ liệu không như mong đợi.

Hãy chia danh sách thành **chunk có kích thước giới hạn**, đo thời gian từng search và chọn chunk size theo server. Chia 1.000 UID thành 10 nhóm có thể tạo 10 SearchRequests; đây vẫn thường ít hơn 1.000 lần đọc riêng lẻ.

## 6. Search scope, projection và giới hạn kết quả

Một truy vấn tốt không chỉ giảm số request mà còn giảm lượng dữ liệu server phải xử lý/trả về.

~~~java
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.SearchScope;

import static org.springframework.ldap.query.LdapQueryBuilder.query;

LdapQuery peopleQuery = query()
        .base("ou=people")
        .searchScope(SearchScope.SUBTREE)
        .attributes("uid", "cn", "sn", "mail")
        .countLimit(500)
        .timeLimit(2000)
        .where("objectClass").is("inetOrgPerson");
~~~

Ý nghĩa:

- `base("ou=people")`: giới hạn nhánh tìm kiếm.
- `searchScope(...)`: chọn OBJECT, ONELEVEL hoặc SUBTREE theo cấu trúc DIT.
- `attributes(...)`: chỉ yêu cầu những attribute cần thiết.
- `countLimit(500)`: giới hạn số entry trả theo cấu hình truy vấn.
- `timeLimit(2000)`: giới hạn thời gian tìm kiếm theo đơn vị millisecond trong API Spring LDAP tương ứng.

Tên method và cách áp dụng limit cần được kiểm tra với phiên bản Spring LDAP của dự án. Directory server cũng có thể có giới hạn riêng thấp hơn. **Count limit không phải phân trang**: nó giới hạn kết quả; muốn duyệt hết tập dữ liệu lớn cần paging hoặc chiến lược chia truy vấn.

Nếu ứng dụng cần 3 thuộc tính nhưng lại lấy toàn bộ entry có thể tăng băng thông và lộ dữ liệu nhạy cảm. Projection tối thiểu giúp giảm payload và làm rõ hợp đồng DTO.

## 7. Phân trang: một truy vấn logic có thể thành nhiều SearchRequests

Với hàng chục nghìn entry, không nên mặc định tải toàn bộ vào một lần. LDAP Paged Results Control cho phép yêu cầu từng trang khi server hỗ trợ control này.

Spring LDAP có `PagedResultsDirContextProcessor`. Ví dụ minh họa:

~~~java
import java.util.ArrayList;
import java.util.List;

import org.springframework.ldap.control.PagedResultsDirContextProcessor;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;

public List<PersonSummary> findAllPaged(
        LdapTemplate ldapTemplate,
        LdapQuery query) {

    int pageSize = 200;
    PagedResultsDirContextProcessor processor =
            new PagedResultsDirContextProcessor(pageSize);

    List<PersonSummary> all = new ArrayList<>();

    do {
        List<PersonSummary> page = ldapTemplate.search(
                query,
                (AttributesMapper<PersonSummary>) attrs ->
                        new PersonSummary(
                                requiredText(attrs, "uid"),
                                requiredText(attrs, "cn"),
                                requiredText(attrs, "sn")),
                processor);

        all.addAll(page);
    } while (processor.hasMore());

    return all;
}
~~~

Giả sử có 1.000 entry và page size là 200, có thể cần khoảng 5 SearchRequests (mỗi trang một request), tùy cách server trả cookie và kết quả thực tế. Đây là **một luồng duyệt có phân trang**, không phải một request trả 1.000 entry.

Điều kiện và giới hạn:

- Server phải hỗ trợ Paged Results Control (RFC 2696) và cho phép sử dụng.
- Cookie trang phải được giữ và gửi lại đúng cách qua các lần tiếp tục.
- Cần xử lý trường hợp cookie hết hạn, server restart, context đổi hoặc truy vấn bị hủy.
- Kết quả giữa các trang có thể thay đổi nếu dữ liệu được ghi đồng thời; paging không tự tạo snapshot nhất quán trên toàn bộ directory.
- Không giả định offset paging kiểu SQL; LDAP paging thường dùng cookie continuation.
- Giới hạn page size và tổng thời gian duyệt để không tạo tải kéo dài.

Nếu query được gọi qua load balancer, phải xác minh server/pool xử lý cookie có tương thích với việc chuyển node hay không. Một số cơ chế paging yêu cầu cookie được gửi về đúng server/session phù hợp.

## 8. N+1 LDAP requests: dấu hiệu và cách loại bỏ

N+1 xuất hiện khi ứng dụng lấy danh sách bằng một SearchRequest rồi phát sinh thêm một request cho mỗi entry để lấy thông tin bổ sung.

~~~java
List<PersonSummary> people = ldapTemplate.search(
        peopleQuery, summaryMapper);

List<PersonDetail> details = new ArrayList<>();

for (PersonSummary person : people) {
    // Mỗi lần có thể phát sinh thêm một LDAP read.
    details.add(directoryService.findDetail(person.uid()));
}
~~~

Nếu Search trả N entry và mỗi `findDetail` tạo một lookup/search, tổng số lần đọc xấp xỉ:

\[
Q = 1 + N
\]

Với 500 người, đó có thể là 501 lượt LDAP read thay vì một truy vấn lấy đủ trường.

### Cách 1: lấy đủ attribute trong projection ban đầu

Nếu dữ liệu cần thiết nằm trong cùng entry, thêm các attribute vào query:

~~~java
LdapQuery detailQuery = query()
        .base("ou=people")
        .searchScope(SearchScope.SUBTREE)
        .attributes("uid", "cn", "sn", "mail", "telephoneNumber")
        .where("objectClass").is("inetOrgPerson");
~~~

Mapper tạo DTO đầy đủ từ một kết quả search. Không cần lookup lại từng DN.

### Cách 2: gộp điều kiện theo nhóm

Nếu dữ liệu cần lấy từ cùng loại entry và có khóa tìm kiếm, dùng OR filter hoặc điều kiện kết hợp. Chia chunk khi filter quá lớn.

### Cách 3: xác định có thật sự cần lookup riêng không

Một số attribute có thể chỉ được đọc bởi service account khác hoặc có ACL khác. Nếu buộc phải truy cập bằng nhiều context source, request count tăng là hệ quả của ranh giới bảo mật; không nên gộp quyền chỉ để giảm request.

**Không phải mọi N+1 đều có thể loại bỏ bằng một filter.** Nếu dữ liệu nằm ở nhiều entry khác nhau, LDAP không cung cấp join tùy ý như SQL. Ứng dụng phải lựa chọn giữa nhiều search, cache có kiểm soát, materialized attribute hoặc một cấu trúc directory phù hợp.

## 9. findAllById và tìm nhiều khóa

`findAllById(ids)` là API tiện lợi trong `CrudRepository`, nhưng không nên suy luận nó luôn biến danh sách ID thành một OR filter. Hành vi cụ thể phụ thuộc implementation repository và phiên bản.

Có hai chiến lược phổ biến:

**Chiến lược A — đọc từng ID:**

~~~java
List<DirectoryPerson> found = new ArrayList<>();

for (Name id : ids) {
    repository.findById(id).ifPresent(found::add);
}
~~~

Nếu mỗi lần `findById` là một read, N ID tạo N reads. Ưu điểm là đơn giản, dễ xử lý từng lỗi và không cần tạo filter lớn.

**Chiến lược B — search theo nhiều khóa:**

Dùng OR filter trên một attribute có thể tìm kiếm, ví dụ `uid`, như mục 5. Với N UID và một chunk đủ nhỏ, có thể dùng một SearchRequest cho chunk đó.

| Tiêu chí | Đọc từng ID | OR search |
|---|---|---|
| Request count | Thường tăng theo N | Thường một search mỗi chunk |
| Filter size | Nhỏ | Tăng theo số ID |
| Kết quả không tồn tại | Dễ nhận biết theo từng ID | Phải so sánh tập ID yêu cầu và tập trả về |
| DN phức tạp | Có thể đọc trực tiếp theo DN | Cần attribute search phù hợp |
| Trùng UID | Mỗi DN cụ thể rõ ràng | Có thể trả nhiều entry nếu UID không unique |
| ACL/search base | Có thể theo từng DN | Search base và quyền ảnh hưởng toàn bộ |
| Tối ưu cho số lượng lớn | Nhiều round trips | Thường hiệu quả hơn nếu filter và index phù hợp |

Nếu ID của repository là full DN, đừng tự chuyển DN thành chuỗi filter không an toàn. Dùng API parse/build DN; nếu muốn gộp theo attribute, xác định rõ attribute business key và uniqueness trước.

## 10. saveAll: nhiều entity không đồng nghĩa một bulk Add/Modify

`saveAll(entities)` giúp caller gửi một iterable entity và nhận lại kết quả. Nhưng LDAP protocol không có một AddRequest hoặc ModifyRequest chuẩn mang danh sách nhiều DN.

Ví dụ:

~~~java
List<DirectoryPerson> people = loadPeopleToCreate();

List<DirectoryPerson> saved = repository.saveAll(people);
~~~

Không nên mặc định đây là một LDAP request. Implementation có thể xử lý từng entity và gọi operation tương ứng. Trong trường hợp N entry cần tạo, mô hình wire-level thường gần với:

~~~text
AddRequest DN-1
AddRequest DN-2
AddRequest DN-3
...
AddRequest DN-N
~~~

Nếu repository cần kiểm tra tồn tại, mapping hoặc xử lý khác trước/sau thao tác, số request có thể cao hơn. Vì vậy hãy đo đúng phiên bản thư viện.

### Tạo nhiều entry tường minh bằng LdapTemplate

~~~java
for (CreatePersonRequest request : requests) {
    Name dn = LdapNameBuilder.newInstance("ou=people")
            .add("uid", request.uid())
            .build();

    Attributes attrs = new BasicAttributes(true);
    Attribute objectClass = new BasicAttribute("objectClass");
    objectClass.add("top");
    objectClass.add("person");
    objectClass.add("organizationalPerson");
    objectClass.add("inetOrgPerson");

    attrs.put(objectClass);
    attrs.put("uid", request.uid());
    attrs.put("cn", request.cn());
    attrs.put("sn", request.sn());

    ldapTemplate.bind(dn, null, attrs);
}
~~~

Mỗi `bind` tạo một thao tác Add cho một DN. Đoạn code minh họa cấu trúc, cần kiểm tra validation, parent OU, duplicate DN và ACL trước khi chạy. Nếu request thứ 5 thất bại, bốn entry trước có thể đã được tạo; vòng lặp không tự rollback.

**Một lệnh ghi lỗi không có nghĩa toàn batch đã thất bại.** Hãy xác định chính sách partial success, ghi nhận từng DN thành công/thất bại và cho phép chạy tiếp an toàn.

## 11. Sửa nhiều entry: N ModifyRequests, nhưng có thể gộp nhiều thay đổi trên một entry

Giả sử cập nhật email của ba nhân viên:

~~~text
uid=lan,ou=people,...
uid=binh,ou=people,...
uid=minh,ou=people,...
~~~

Có thể dùng vòng lặp:

~~~java
for (MailUpdate update : updates) {
    Name dn = LdapNameBuilder.newInstance("ou=people")
            .add("uid", update.uid())
            .build();

    ModificationItem[] changes = {
        new ModificationItem(
                DirContext.REPLACE_ATTRIBUTE,
                new BasicAttribute("mail", update.mail()))
    };

    ldapTemplate.modifyAttributes(dn, changes);
}
~~~

Với N entry, đây là khoảng N ModifyRequests. Nhưng nếu cùng một entry cần sửa nhiều thuộc tính, gom các thay đổi vào **một mảng ModificationItem**:

~~~java
ModificationItem[] changes = {
    new ModificationItem(
            DirContext.REPLACE_ATTRIBUTE,
            new BasicAttribute("cn", "Tran Lan")),
    new ModificationItem(
            DirContext.REPLACE_ATTRIBUTE,
            new BasicAttribute("sn", "Tran")),
    new ModificationItem(
            DirContext.REPLACE_ATTRIBUTE,
            new BasicAttribute("mail", "lan@example.org"))
};

ldapTemplate.modifyAttributes(personDn, changes);
~~~

Đây là một ModifyRequest cho một DN chứa ba thay đổi attribute. Theo LDAP Modify semantics, các modification trong cùng request được xử lý như một thao tác nguyên tử trên entry đó. Điều này không mở rộng thành transaction trên nhiều DN.

### Không đọc rồi ghi lại toàn bộ entry nếu chỉ cần sửa một trường

Nếu tải 500 entry rồi thay một field và gọi `repository.save(...)` từng entry, ứng dụng vừa tạo nhiều request vừa có nguy cơ ghi lại dữ liệu không cần thiết. Với cập nhật có chủ đích, `LdapTemplate.modifyAttributes(...)` giúp gửi đúng những attribute cần đổi.

## 12. Xóa nhiều entry và rủi ro partial completion

Xóa N entry thường cần N DeleteRequests:

~~~java
for (String uid : uids) {
    Name dn = LdapNameBuilder.newInstance("ou=people")
            .add("uid", uid)
            .build();

    ldapTemplate.unbind(dn);
}
~~~

Một vòng lặp có thể dừng giữa chừng nếu DN không tồn tại, ACL từ chối hoặc entry còn child. Khi đó:

- Một số entry trước đã xóa thành công.
- Entry hiện tại có thể thất bại.
- Các entry sau có thể chưa được xử lý.
- Không có rollback tự động cho các DeleteRequests trước đó.

Với thao tác xóa số lượng lớn, nên có **dry-run**, danh sách DN được phê duyệt, batch size nhỏ, audit và kết quả từng entry. Không dùng `deleteAll()` trên repository nếu chưa xác định chính xác phạm vi và semantics của implementation; tránh nhầm “xóa toàn bộ iterable” với “xóa toàn bộ directory”.

Nếu cần xóa entry còn child, LDAP Delete chuẩn thường không xóa đệ quy subtree. Phải xác định chính sách xử lý cây con riêng; không biến batch delete thành cascade không được phê duyệt.

## 13. Batch loop không phải transaction

Ví dụ:

~~~java
for (MailUpdate update : updates) {
    ldapTemplate.modifyAttributes(
            personDn(update.uid()),
            modificationFor(update.mail()));
}
~~~

Nếu thao tác thứ 4 lỗi, ba thao tác trước có thể đã được commit. Vòng lặp Java không tạo transaction LDAP.

| Cơ chế | Phạm vi đảm bảo |
|---|---|
| Một ModifyRequest có nhiều ModificationItem | Một entry, một thao tác Modify |
| N ModifyRequests trong vòng lặp | N entry; có thể thành công một phần |
| `saveAll(...)` | API tiện lợi; không mặc định transaction/bulk protocol |
| Transaction extension riêng của LDAP server | Chỉ khi server/client hỗ trợ và ứng dụng sử dụng đúng extension |
| Saga/compensation do ứng dụng thiết kế | Điều phối nhiều bước, cần logic hoàn tác và xử lý trạng thái |

Không mặc định `@Transactional` của Spring tạo transaction ACID trên nhiều LDAP entry. Spring transaction manager dùng cho relational database không tự biến một tập LDAP operations thành transaction.

Nếu cần all-or-nothing trên nhiều entry, phải khảo sát transaction extension cụ thể của directory và client hoặc thiết kế quy trình điều phối/compensation. Đa số ứng dụng LDAP nên chấp nhận **partial success có kiểm soát** và có thể resume.

## 14. Giới hạn batch size và chia chunk

Một batch quá lớn có thể tạo filter khổng lồ, response lớn, tăng memory và làm directory quá tải. Chia chunk giúp kiểm soát:

~~~java
public static <T> List<List<T>> chunks(List<T> input, int size) {
    if (size <= 0) {
        throw new IllegalArgumentException("Chunk size must be positive");
    }

    List<List<T>> result = new ArrayList<>();
    for (int start = 0; start < input.size(); start += size) {
        int end = Math.min(start + size, input.size());
        result.add(input.subList(start, end));
    }
    return result;
}
~~~

Ví dụ:

~~~java
for (List<String> uidChunk : chunks(uids, 50)) {
    List<PersonSummary> page =
            findPeopleByUids(ldapTemplate, uidChunk);
    process(page);
}
~~~

Nếu có 1.000 UID và chunk size 50, sẽ có khoảng 20 SearchRequests nếu mỗi chunk được xử lý bằng một OR search và không cần paging bổ sung.

Chọn chunk size theo:

- Giới hạn filter/request size của directory hoặc proxy.
- Số lượng kết quả trung bình mỗi filter.
- Độ phức tạp matching/index.
- Latency và throughput quan sát được.
- Giới hạn memory của ứng dụng.
- Timeout của LDAP connection và HTTP/job.
- Khả năng retry từng chunk.

Không có một chunk size tối ưu cho mọi directory. Hãy bắt đầu nhỏ, đo, tăng dần và đặt trần cấu hình.

## 15. Concurrency: song song không làm giảm request count

Có thể chạy 100 ModifyRequests tuần tự hoặc chạy một số request song song. Nếu vẫn sửa 100 DN, tổng số ModifyRequests vẫn xấp xỉ 100; concurrency chỉ thay đổi cách phân bố thời gian và tải.

| Cách thực hiện | Request count | Ảnh hưởng |
|---|---:|---|
| Tuần tự 100 Modify | 100 | Dễ kiểm soát, latency tổng có thể cao |
| 5 worker song song, mỗi worker 20 Modify | 100 | Có thể giảm wall-clock time, tăng tải đồng thời |
| 100 worker đồng thời | 100 | Có nguy cơ cạn connection pool, quá tải server |
| Một Modify với 100 attribute changes trên cùng DN | 1 ModifyRequest | Chỉ phù hợp khi mọi thay đổi thuộc cùng entry |

Nếu cần concurrency, dùng giới hạn rõ ràng (ví dụ 4–8 worker để bắt đầu thử nghiệm, không phải mặc định production), connection pool đủ capacity, timeout, backpressure và dừng khi tỷ lệ lỗi tăng.

**Không chạy song song vô hạn** bằng cách tạo một future/thread cho mỗi entry. LDAP server có giới hạn connection, worker, request queue và tài nguyên xử lý. Nhiều request đồng thời còn làm tăng nguy cơ conflict nếu cùng entry bị cập nhật bởi nhiều luồng.

## 16. Idempotency và retry cho batch

Một batch có thể bị gián đoạn sau khi đã xử lý một phần. Khi chạy lại, cần xác định thao tác nào an toàn để retry:

| Operation | Retry có thể gặp | Chính sách |
|---|---|---|
| Add entry | DN đã tồn tại (68) | Đọc/đối soát identity; không tự coi mọi duplicate là thành công |
| Replace một attribute bằng cùng value | Thường có hiệu quả mong muốn lặp lại giống nhau | Kiểm tra tác nhân khác và nghiệp vụ |
| Add một value vào multi-valued attribute | Value đã tồn tại (20) | Xử lý duplicate theo idempotency contract |
| Remove một value | Value không còn (16) | Phân biệt đã hoàn tất với trạng thái bất thường |
| Delete entry | Entry không còn (32) | Có thể xem như đã đạt trạng thái đích theo hợp đồng |
| ModifyDN | Source không còn hoặc destination tồn tại (68/32) | Đọc lại source/destination và xác minh identity |

Khi timeout xảy ra sau khi gửi write request, client có thể **không biết thao tác đã được server thực hiện hay chưa**. Đó là unknown outcome; không thể chỉ nhìn exception rồi khẳng định chưa ghi.

Một batch job bền vững nên lưu:

- Batch ID và thời điểm bắt đầu.
- Stable business ID của entry, DN tại thời điểm thao tác.
- Trạng thái từng entry: pending/success/failed/skipped.
- Operation và dữ liệu thay đổi đã được kiểm soát.
- Mã lỗi phân loại, số lần thử và thời điểm retry.
- Checkpoint để tiếp tục sau khi tiến trình dừng.

Không log password, toàn bộ entry nhạy cảm hoặc giá trị attribute không cần thiết trong ledger.

## 17. Giới hạn tìm kiếm và paging ảnh hưởng tới số request

Một SearchRequest có thể trả nhiều entry, nhưng server có thể áp dụng:

- **Size limit:** giới hạn số entry trả về.
- **Time limit:** giới hạn thời gian xử lý.
- **Administrative limit:** giới hạn do cấu hình quản trị.
- **Referral:** trả thông tin chuyển hướng tới naming context/server khác.
- **Paged Results Control:** trả từng trang khi client tiếp tục bằng cookie.
- **Access control:** chỉ trả các entry/attribute mà bind identity được phép đọc.

Do đó, nếu `findAll()` chỉ trả 500 trong khi có 2.000 entry, đừng lập tức cho rằng repository bị lỗi. Có thể server đã áp dụng size limit, search scope chưa bao phủ toàn bộ hoặc caller không có quyền đọc một phần dữ liệu.

Một lần gọi `findAll()` không nhất thiết duyệt hết directory. Kiểm tra API, limit và paging behavior theo phiên bản thư viện. Nếu phải đọc hết dữ liệu lớn, hãy dùng paging có kiểm soát thay vì tăng limit vô hạn.

## 18. Ước lượng tổng request cho một workflow

Giả sử một job cần:

1. Tìm 1.000 nhân viên theo trạng thái.
2. Cập nhật thuộc tính `description` của mỗi nhân viên.
3. Thêm một thuộc tính cho 50 người thuộc nhóm đặc biệt.
4. Xóa 10 entry đã hết hiệu lực.

Một ước lượng với page size 200:

| Bước | Thiết kế | LDAP request ước tính |
|---|---|---:|
| Đọc 1.000 nhân viên | Paged Search, 200 entry/trang | 5 SearchRequests |
| Cập nhật 1.000 entry | Một ModifyRequest/entry | 1.000 ModifyRequests |
| Cập nhật 50 người đặc biệt | Một ModifyRequest/entry | 50 ModifyRequests |
| Xóa 10 entry | Một DeleteRequest/entry | 10 DeleteRequests |
| **Tổng** | Chưa tính retry/referral/health check | **1.065 requests** |

Nếu bước 1 dùng một SearchRequest không phân trang và server cho phép trả 1.000 entry, request count có thể giảm xuống 1 cho search; nhưng response lớn hơn và có thể chạm size/time limit. Nếu bước cập nhật từng entry có thêm lookup để kiểm tra trước khi Modify, số request tăng thêm tới 1.000 reads.

Mục tiêu tối ưu không phải lúc nào cũng là số request nhỏ nhất. Cần cân bằng **tải server, kích thước response, tính an toàn, ACL, khả năng resume và consistency**.

## 19. Quan sát request count ở tầng nào?

Đếm `repository.saveAll()` một lần không đủ để biết server nhận bao nhiêu request. Nên kết hợp nhiều nguồn:

| Nguồn đo | Quan sát được | Giới hạn |
|---|---|---|
| Application metrics | Số lần gọi service/repository, thời gian method | Không luôn phản ánh số LDAP operations bên dưới |
| Spring LDAP instrumentation/wrapper | Các lần gọi `LdapOperations` | Một method có thể tạo nhiều thao tác JNDI |
| JNDI/provider debug hoặc protocol trace | Hoạt động ở client/protocol | Có thể nhiều dữ liệu, cần giới hạn và bảo vệ log |
| LDAP server access log | Operation server nhận, DN/base, result code tùy cấu hình | Cần cấu hình server và quyền vận hành |
| Network capture trên môi trường test | LDAPMessage và round-trip | TLS mã hóa nội dung; phân tích chi tiết cần công cụ/điểm giải mã phù hợp |

Các metric ứng dụng có thể tự định nghĩa:

- `ldap_operations_total{operation="search|add|modify|delete"}`.
- `ldap_operation_duration`.
- `ldap_entries_returned`.
- `ldap_batch_items_total`.
- `ldap_batch_failures_total`.
- `ldap_page_count`.
- `ldap_connection_wait_duration`.

Tên trên là **metric gợi ý**, không khẳng định Spring Data LDAP tự tạo sẵn mọi metric này. Không dùng UID, email hoặc DN cá nhân làm label cardinality cao. Có thể log batch ID, operation type, thời gian, endpoint đã ẩn thông tin nhạy cảm và result code.

### Một nguyên tắc đo

Đo cùng một workload theo các phương án:

- N lần `findByUid`.
- Một OR search.
- `findAll` với projection đầy đủ.
- `findAll` rồi lookup từng entry.
- `saveAll` so với loop `save` hoặc `LdapTemplate.bind`.
- Loop Modify tuần tự so với concurrency giới hạn.

Ghi lại **số LDAP requests, tổng entries, số lỗi, p50/p95 latency và tải server**. Một phương án giảm request nhưng làm server search chậm hơn hoặc trả quá nhiều dữ liệu có thể không phải lựa chọn tốt hơn.

## 20. Kiểm thử batch và request count

Có ba lớp kiểm thử hữu ích:

| Test | Mục tiêu | Có LDAP thật? |
|---|---|---|
| Unit test service | Kiểm tra chia chunk, filter, validation, retry và kết quả từng item | Không |
| Integration test LDAP | Xác minh schema, Add/Modify/Delete/Search, ACL | Có, một directory test |
| Protocol/count test | Đếm operation thực tế, kiểm tra search paging và N writes | Nên có server logs/trace; nhiều node nếu cần |

### Test chức năng batch

Kiểm tra các trường hợp:

- Danh sách rỗng: không gửi LDAP request.
- Một ID: kết quả đúng.
- N ID hợp lệ: kết quả đầy đủ.
- Một số ID không tồn tại: hợp đồng trả kết quả thiếu được xác định rõ.
- UID trùng hoặc filter trả nhiều entry: không chọn tùy tiện.
- Một entry bị ACL từ chối: các item khác xử lý theo chính sách partial success.
- DN đích đã tồn tại: Add trả duplicate; không ghi đè ngoài ý muốn.
- Entry còn child: Delete bị từ chối theo quy tắc server.
- Search vượt count/time limit: báo rõ kết quả không đầy đủ.
- Paging cookie hết hạn: job dừng/resume có kiểm soát.

### Đo số request bằng server log

Trên LDAP test, bật access log theo cách phù hợp sản phẩm. Chạy cùng batch ID và cùng dataset cho mỗi phương án. So sánh số Search/Add/Modify/Delete thực tế, không suy ra từ số dòng Java.

Nếu dùng mock `LdapTemplate`, mock có thể chứng minh service gọi method bao nhiêu lần nhưng **không chứng minh chính xác số LDAP protocol messages** do một method có thể thực hiện nhiều bước nội bộ. Hãy phân biệt hai cấp test này.

## 21. Các lỗi thường gặp

| Lỗi/hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| `saveAll()` chậm hơn mong đợi | N thao tác ghi riêng, có thể thêm read/lookup | Đo protocol, giới hạn batch, giảm bước thừa |
| `findAllById()` tạo nhiều request | Implementation đọc từng ID | Dùng OR search theo attribute phù hợp nếu an toàn |
| `findAll()` chỉ trả một phần | Size limit, scope, ACL hoặc chưa paging | Kiểm tra result code/limit và paged control |
| Search một lần nhưng payload quá lớn | Projection quá rộng | Chỉ yêu cầu attribute cần thiết |
| Search + lookup từng entry | N+1 operations | Lấy đủ attributes trong search ban đầu |
| OR filter thất bại | Filter quá dài hoặc assertion không hợp lệ | Chia chunk, dùng filter builder |
| Delete batch dừng giữa chừng | Một DN lỗi, ACL hoặc entry có child | Ghi nhận per-entry outcome và resume |
| Add batch tạo một phần | Không có transaction nhiều entry | Partial-success ledger và reconciliation |
| Retry tạo duplicate | Unknown outcome sau timeout | Đối soát DN trước retry |
| Chạy song song làm directory quá tải | Concurrency vượt pool/server capacity | Giới hạn worker, backpressure |
| Mock test cho số request sai | Mock đếm method call, không đếm protocol | Kiểm tra server logs/trace |
| Gọi `@Transactional` nhưng vẫn partial | Không có transaction manager LDAP tương ứng | Thiết kế semantics nhiều entry rõ ràng |

## 22. Bài tập thực hành

**Bối cảnh:** hệ thống nhân sự dùng Spring Data LDAP có 5.000 entry dưới `ou=people`. Một job cần tìm nhân viên theo danh sách UID, cập nhật một thuộc tính và xóa một nhóm entry hết hiệu lực. Directory có giới hạn search và connection pool.

Thực hiện trên directory test độc lập:

1. Tạo dataset ít nhất 500 entry `inetOrgPerson` có `uid`, `cn`, `sn`, `mail`.
2. Viết job gọi `findByUid` trong vòng lặp cho 100 UID; ghi số lần gọi Java và số SearchRequests thực tế.
3. Viết OR filter bằng `OrFilter` + `EqualsFilter` để tìm cùng 100 UID; so sánh request count và latency.
4. Thử tăng lên 1.000 UID; xác định giới hạn filter và chọn chunk size.
5. So sánh một search lấy projection tối thiểu với search lấy toàn bộ attributes.
6. Viết `findAll` có paging, đặt page size 100 và đếm số SearchRequests.
7. So sánh `findAllById` của phiên bản Spring Data LDAP đang dùng với OR search; ghi rõ implementation thực tế.
8. Thực hiện `saveAll` cho 100 entry mới và đo số Add/Modify requests; không giả định API method count là protocol count.
9. Cập nhật 100 entry, so sánh một ModifyRequest/entry với nhiều ModificationItem trên cùng một entry.
10. Xóa 50 entry, cố tình làm một item thất bại và ghi nhận partial completion.
11. Chạy batch tuần tự rồi concurrency giới hạn; so sánh p50/p95, lỗi và tải server.
12. Ngắt job giữa batch, khởi động lại và kiểm tra idempotency/checkpoint.
13. Tạo test N+1: search danh sách rồi lookup từng entry; sửa thành projection đủ trường.
14. Viết báo cáo gồm request count, entries returned, response size, latency và lỗi cho từng phương án.

**Tiêu chí hoàn thành:** người học giải thích được vì sao một SearchRequest có thể trả nhiều entry nhưng nhiều Add/Modify/Delete thường cần nhiều operation; biết cách gộp truy vấn đọc, phân trang, tránh N+1, đo request count thật và xử lý partial success khi batch ghi.

## 23. Tổng kết và tài liệu tham khảo

Khi làm việc với nhiều entry, hãy phân biệt **một lần gọi repository**, **một LDAP request**, **nhiều response entry** và **nhiều lần round trip**. Một SearchRequest có thể trả nhiều entry; một thao tác ghi/xóa LDAP chuẩn thường chỉ tác động tới một DN. `saveAll`, `findAllById` hay `deleteAll` là API ở tầng repository, không phải lời hứa rằng directory sẽ nhận một bulk protocol request.

Để giảm request hợp lý:

- Gộp điều kiện đọc bằng filter OR an toàn khi schema/search base cho phép.
- Chỉ lấy các attribute cần thiết và dùng search scope nhỏ nhất.
- Phân trang khi tập dữ liệu lớn.
- Tránh N+1 bằng cách projection đủ dữ liệu trong Search.
- Gom nhiều ModificationItem cho cùng một entry, không nhầm với batch nhiều DN.
- Chia chunk, giới hạn concurrency, timeout và retry.
- Theo dõi từng item để xử lý partial success/resume.
- Đo ở LDAP server/protocol khi cần số request chính xác.

Tài liệu tham khảo:

- [Spring Data LDAP Reference](https://docs.spring.io/spring-data/ldap/reference/): LdapRepository, ODM và truy vấn repository.
- [Spring LDAP Reference](https://docs.spring.io/spring-ldap/reference/): LdapTemplate, LdapQueryBuilder, mapping, paging và thao tác LDAP.
- [Spring Data Commons — CrudRepository](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/repository/CrudRepository.html): hợp đồng findAll, findAllById, saveAll, deleteAll.
- [RFC 4511 — LDAP: The Protocol](https://www.rfc-editor.org/rfc/rfc4511): Search, Add, Modify, Delete, ModifyDN và cấu trúc request/response.
- [RFC 2696 — LDAP Control Extension for Simple Paged Results Manipulation](https://www.rfc-editor.org/rfc/rfc2696): paged results control và cookie tiếp tục truy vấn.
- [RFC 4515 — LDAP Search Filter](https://www.rfc-editor.org/rfc/rfc4515): cú pháp filter và escaping.
