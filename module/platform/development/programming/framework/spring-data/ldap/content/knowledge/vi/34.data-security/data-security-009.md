# Giới hạn truy vấn rộng, dữ liệu trả về và tần suất yêu cầu

> **Chương:** Bảo mật dữ liệu  
> **Module:** SPRING_DATA_LDAP — truy cập dịch vụ thư mục LDAP qua Spring Data LDAP bằng repository và ánh xạ entry phân cấp sang đối tượng Java. Người học hiểu DN, objectClass, schema, truy vấn repository/LdapTemplate, CRUD, filter an toàn, bảo mật kết nối và kiểm thử với directory.

LDAP Search có thể trả về hàng nghìn entry và rất nhiều attribute values. Một endpoint tìm nhân viên tưởng như vô hại có thể vô tình cho phép người dùng duyệt toàn bộ directory, tải ảnh/chứng thư không cần thiết hoặc gửi hàng trăm truy vấn mỗi giây. Filter hợp lệ về cú pháp vẫn có thể quá rộng, tốn CPU hoặc làm lộ dữ liệu.

Bảo vệ truy vấn LDAP cần giới hạn đồng thời **phạm vi tìm kiếm, số entry, thời gian xử lý, attribute được trả về, kích thước phản hồi, số trang và tần suất request**. Các giới hạn ở ứng dụng phải phối hợp với ACL và administrative limits của directory server. Chỉ giới hạn kết quả ở giao diện không ngăn server phải quét một subtree lớn để tìm kết quả.

Bài này hướng dẫn xây API search có allowlist, đặt giới hạn bằng JNDI SearchControls và Spring LDAP, phân trang có giới hạn, giảm dữ liệu trả về, điều tiết request, xử lý lỗi giới hạn và kiểm thử các tình huống enumeration/denial of service.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

1. Nhận diện truy vấn quá rộng và filter có chi phí cao.
2. Giới hạn base DN, search scope và loại entry được phép tìm.
3. Xây filter bằng API an toàn thay vì nối chuỗi từ input.
4. Đặt count limit và time limit ở mỗi SearchRequest.
5. Hiểu giá trị 0 của JNDI SearchControls là không giới hạn.
6. Chỉ trả về attribute cần thiết và ánh xạ sang DTO tối thiểu.
7. Phân trang bằng LDAP Paged Results Control nhưng vẫn giới hạn tổng số trang/kết quả.
8. Phân biệt giới hạn client, giới hạn server và timeout mạng.
9. Giới hạn tần suất và concurrency theo người gọi, tenant và endpoint.
10. Xử lý sizeLimitExceeded, timeLimitExceeded, adminLimitExceeded và lỗi server bận.
11. Thiết kế retry, cache và backpressure không làm tăng tải khi directory đang suy giảm.
12. Kiểm thử enumeration, response lớn, filter đắt và lạm dụng pagination.

## 2. Vì sao truy vấn LDAP rộng là rủi ro bảo mật?

Một SearchRequest có thể yêu cầu server duyệt một vùng lớn trong DIT, đánh giá filter trên nhiều entry và trả về nhiều attribute values. Chi phí không chỉ là số entry cuối cùng.

~~~text
Client request
     |
     v
API validation / authorization
     |
     v
Build LDAP SearchRequest
     |
     +--> base DN + scope
     +--> filter evaluation
     +--> server index / directory scan
     +--> result limits
     +--> selected attributes
     |
     v
LDAP response entries + controls
     |
     v
DTO mapping / serialization
     |
     v
HTTP response
~~~

Một truy vấn rộng có thể gây:

- **Enumeration:** người gọi lần lượt dò tìm toàn bộ user, group hoặc email.
- **Resource exhaustion:** filter không có index buộc server quét nhiều entry.
- **Memory pressure:** ứng dụng gom tất cả kết quả vào List rồi serialize thành JSON lớn.
- **Network saturation:** trả ảnh, certificate, group membership hoặc attribute dài không cần thiết.
- **Accountability gap:** log không cho biết actor nào thực hiện search rộng hoặc vượt quota.
- **Availability impact:** nhiều truy vấn lớn chạy đồng thời làm chậm login, authorization và provisioning.
- **Data exposure:** người dùng có thể đọc attribute ngoài mục đích nghiệp vụ nếu bind identity hoặc ACL quá rộng.

Một endpoint chỉ trả 20 kết quả vẫn có thể tốn kém nếu server phải quét hàng triệu entry để tìm 20 kết quả đó. Vì vậy, giới hạn kết quả cần đi cùng base/scope, index, timeout và quota.

## 3. Xác định phạm vi tìm kiếm bằng base DN

Base DN xác định điểm bắt đầu của SearchRequest. Ứng dụng nên chọn base theo use case, không nhận tùy ý từ client.

Ví dụ:

| Use case | Base DN gợi ý |
|---|---|
| Tìm người dùng | ou=people,dc=example,dc=org |
| Tìm group | ou=groups,dc=example,dc=org |
| Tìm thiết bị | ou=devices,dc=example,dc=org |
| Đọc một entry đã biết | DN cụ thể của entry |
| Đồng bộ toàn bộ directory | Quy trình quản trị riêng, không phải endpoint search công khai |

Không để API nhận tham số baseDN rồi truyền trực tiếp vào LdapTemplate. Người dùng có thể đổi base để tìm ở OU nhạy cảm hoặc mở rộng phạm vi sang naming context khác.

Hãy ánh xạ một use case/tenant sang base DN đã được cấu hình phía server. Nếu tenant có subtree riêng, server-side ACL vẫn phải bảo đảm bind identity không thể đọc dữ liệu của tenant khác.

## 4. Chọn search scope nhỏ nhất

LDAP hỗ trợ ba search scope cơ bản:

| Scope | Phạm vi | Khi dùng |
|---|---|---|
| OBJECT | Chỉ entry tại base DN | Đọc đúng một entry |
| ONELEVEL | Các entry con trực tiếp của base | Danh sách user trong một OU |
| SUBTREE | Base và toàn bộ hậu duệ | Tìm kiếm phân cấp khi thật sự cần |

Ví dụ, nếu tất cả user nằm trực tiếp dưới ou=people, ONELEVEL tránh quét các OU con không liên quan. Nếu cần tìm user trong các OU con, SUBTREE có thể cần thiết nhưng phải giới hạn base, filter, thời gian và kết quả.

Đừng mặc định SUBTREE cho mọi endpoint. Cũng không nên đổi sang OBJECT nếu use case thực sự cần nhiều entry; chọn scope theo cấu trúc DIT và contract API.

Với Spring LDAP query builder, scope có thể được đặt rõ ràng:

~~~java
LdapQuery query = query()
        .base("ou=people")
        .searchScope(SearchScope.ONELEVEL)
        .where("objectClass").is("inetOrgPerson");
~~~

Base ở ví dụ là tương đối với base DN của ContextSource. Hãy kiểm tra cấu hình ContextSource và không ghép base DN từ input thô.

## 5. Nhận diện filter quá rộng hoặc tốn kém

Các filter dưới đây khác nhau về phạm vi và chi phí:

| Filter | Rủi ro | Cách dùng an toàn hơn |
|---|---|---|
| (objectClass=*) | Thường khớp gần như mọi entry có objectClass | Thêm objectClass cụ thể và base/scope hẹp |
| (uid=*) | Presence filter có thể trả rất nhiều user | Yêu cầu prefix/identifier hợp lệ hoặc giới hạn use case |
| (cn=*lan*) | Substring search có thể tốn kém nếu không có index phù hợp | Dùng equality/prefix theo yêu cầu nghiệp vụ |
| (mail=*) | Có thể enumerate mọi entry có email | Chỉ dùng trong job quản trị có quyền |
| (&(objectClass=person)(uid=lan)) | Thu hẹp theo objectClass và UID | Phù hợp tra cứu một identity nếu base/scope đúng |
| (|(uid=a)(uid=b)... rất nhiều giá trị) | Filter lớn, nhiều nhánh OR | Chia batch nhỏ và giới hạn số phần tử |

Không có quy tắc rằng mọi substring filter đều chậm; hiệu năng phụ thuộc directory server, index và matching rule. Tuy nhiên, endpoint công khai không nên cho phép người dùng tùy ý tạo wildcard/presence filter.

Cần kiểm tra index ở server cho attribute được dùng trong equality/prefix search. Cấu hình index là tính năng server-specific; annotation Spring Data LDAP không tự tạo index.

## 6. Không nhận raw LDAP filter từ client

Một API như sau rất nguy hiểm:

~~~java
public List<Person> search(String filterFromRequest) {
    return ldapTemplate.search(
            "",
            filterFromRequest,
            personMapper);
}
~~~

Người gọi có thể gửi filter rộng, lồng nhiều OR, wildcard hoặc filter nhắm tới attribute ngoài ý định. Nếu filter được nối chuỗi, còn có nguy cơ LDAP filter injection.

Thay vào đó:

1. API nhận các tham số nghiệp vụ đã định nghĩa, ví dụ uid hoặc email.
2. Validate độ dài, charset, format và quyền truy cập.
3. Chọn objectClass, base và scope từ cấu hình phía server.
4. Dùng EqualsFilter/LdapQueryBuilder để encode assertion value.
5. Đặt count/time limits và attribute projection.
6. Kiểm tra authorization trước khi gửi SearchRequest.

Ví dụ xây filter có cấu trúc:

~~~java
AndFilter filter = new AndFilter();
filter.and(new EqualsFilter("objectClass", "inetOrgPerson"));
filter.and(new EqualsFilter("uid", validatedUid));

String encodedFilter = filter.encode();
~~~

EqualsFilter mã hóa assertion value theo cú pháp LDAP filter. Không nối trực tiếp validatedUid vào chuỗi "(uid=...)" dù input đã qua kiểm tra định dạng.

**DN escaping và filter escaping là hai việc khác nhau.** Dùng LdapNameBuilder/LdapEncoder cho DN theo đúng ngữ cảnh; dùng Filter API cho assertion value trong search filter.

## 7. Validate input và allowlist attribute

Validate input cần giới hạn kích thước trước khi tạo filter:

~~~java
public String validateUid(String uid) {
    if (uid == null || uid.isBlank()) {
        throw new IllegalArgumentException("uid is required");
    }

    if (uid.length() > 64) {
        throw new IllegalArgumentException("uid is too long");
    }

    if (!uid.matches("[A-Za-z0-9._-]+")) {
        throw new IllegalArgumentException("invalid uid format");
    }

    return uid;
}
~~~

Regex trên chỉ là ví dụ cho quy ước UID của ứng dụng. Không áp dụng nó cho DN, email, tên hiển thị hoặc attribute có Unicode nếu schema/contract cho phép các ký tự đó.

Attribute trả về cũng cần allowlist. Không để client truyền tên attribute tùy ý như:

~~~text
?attributes=uid,cn,mail,userPassword,member,*
~~~

Thay vào đó, API chọn projection cố định theo use case. Nếu cần nhiều loại view, định nghĩa các DTO/projection khác nhau và quyền tương ứng.

Allowlist giảm nguy cơ lộ dữ liệu, nhưng không thay thế ACL của directory server. Nếu bind identity có quyền đọc mọi attribute, một lỗi code vẫn có thể làm lộ dữ liệu.

## 8. Đặt giới hạn bằng JNDI SearchControls

JNDI SearchControls cho phép cấu hình phạm vi, số entry tối đa, thời gian server xử lý và attribute được trả về.

~~~java
SearchControls controls = new SearchControls();

controls.setSearchScope(SearchControls.ONELEVEL_SCOPE);
controls.setCountLimit(100);
controls.setTimeLimit(2_000);
controls.setReturningAttributes(
        new String[] {"uid", "cn", "mail"});
controls.setReturningObjFlag(false);
controls.setDerefLinkFlag(false);
~~~

Ý nghĩa:

- setSearchScope: chọn OBJECT, ONELEVEL hoặc SUBTREE.
- setCountLimit: giới hạn số entry được trả về cho search.
- setTimeLimit: giới hạn thời gian xử lý SearchRequest, tính bằng milliseconds.
- setReturningAttributes: chỉ yêu cầu các attribute được liệt kê.
- setReturningObjFlag(false): không yêu cầu JNDI dựng Java object từ entry.
- setDerefLinkFlag(false): không yêu cầu dereference alias theo mặc định.

**Cảnh báo quan trọng:** với JNDI SearchControls, countLimit = 0 có nghĩa không giới hạn số entry; timeLimit = 0 có nghĩa không giới hạn thời gian. Không dùng giá trị 0 khi mục tiêu là bảo vệ tài nguyên.

Client-side SearchControls không thay thế administrative limits ở server. Server có thể áp giới hạn thấp hơn, trả lỗi hoặc cắt kết quả theo policy. Cũng cần đặt timeout ở connection/network layer; SearchControls timeLimit không bao trùm mọi giai đoạn connect, bind và đọc response.

## 9. Ví dụ search có giới hạn bằng LdapTemplate

Ví dụ sau chỉ tìm một UID trong OU people, giới hạn 100 entry, 2 giây và ba attribute:

~~~java
public List<PersonSummary> findPeopleByUid(String rawUid) {
    String uid = validateUid(rawUid);

    AndFilter filter = new AndFilter();
    filter.and(new EqualsFilter("objectClass", "inetOrgPerson"));
    filter.and(new EqualsFilter("uid", uid));

    SearchControls controls = new SearchControls();
    controls.setSearchScope(SearchControls.ONELEVEL_SCOPE);
    controls.setCountLimit(100);
    controls.setTimeLimit(2_000);
    controls.setReturningAttributes(
            new String[] {"uid", "cn", "mail"});
    controls.setReturningObjFlag(false);

    return ldapTemplate.search(
            "ou=people",
            filter.encode(),
            controls,
            (AttributesMapper<PersonSummary>) attrs ->
                    new PersonSummary(
                            (String) attrs.get("uid").get(),
                            (String) attrs.get("cn").get(),
                            attrs.get("mail") == null
                                    ? List.of()
                                    : readStringValues(attrs, "mail")));
}
~~~

Ví dụ minh họa một use case tra cứu UID; trong thực tế có thể trả tối đa một kết quả nếu uid được bảo đảm unique trong base đó. Giới hạn 100 vẫn là safety cap để tránh dữ liệu duplicate hoặc lỗi schema làm trả nhiều entry.

Trong ví dụ này, mail được ánh xạ thành danh sách vì schema có thể cho phép nhiều giá trị. Hàm readStringValues phải duyệt và đóng NamingEnumeration; không âm thầm lấy phần tử đầu tiên nếu contract cho phép nhiều email.

Một helper tối thiểu có thể viết như sau:

~~~java
private List<String> readStringValues(
        Attributes attributes,
        String attributeName) throws NamingException {

    Attribute attribute = attributes.get(attributeName);
    if (attribute == null) {
        return List.of();
    }

    List<String> values = new ArrayList<>(attribute.size());
    NamingEnumeration<?> all = attribute.getAll();
    try {
        while (all.hasMore()) {
            Object value = all.next();
            if (!(value instanceof String text)) {
                throw new IllegalStateException(
                        "Unexpected LDAP value type");
            }
            values.add(text);
        }
    } finally {
        all.close();
    }
    return List.copyOf(values);
}
~~~

Nếu UID là khóa duy nhất, khi kết quả có nhiều hơn một entry cần ghi nhận conflict identity thay vì chọn kết quả đầu tiên.

Không nên trả toàn bộ Attributes hoặc DirContextAdapter trực tiếp ra REST response. Map sang DTO chỉ chứa field cần thiết.

## 10. Count limit không phải giới hạn số entry server phải quét

Count limit chủ yếu giới hạn số entry được trả về cho client. Nó không đảm bảo server chỉ đánh giá filter trên đúng số entry đó.

Ví dụ, search trong subtree có một triệu entry, filter trên attribute không có index và chỉ trả về 20 kết quả. Server vẫn có thể phải duyệt/đánh giá một phần lớn subtree để tìm các kết quả phù hợp.

Do đó, phải kết hợp:

- Base DN hẹp.
- Scope nhỏ nhất.
- Equality/prefix filter có index phù hợp.
- Server administrative limits.
- Search time limit.
- Count limit.
- Giới hạn concurrency và request rate.

Không tăng count limit chỉ vì người dùng báo “thiếu kết quả”. Trước tiên kiểm tra scope, filter, server limit và yêu cầu nghiệp vụ. Nếu use case cần export nhiều dữ liệu, chuyển sang job quản trị có kiểm soát.

## 11. Giới hạn ở LdapQueryBuilder

Spring LDAP query builder cho phép gắn giới hạn trực tiếp vào query:

~~~java
LdapQuery ldapQuery = query()
        .base("ou=people")
        .searchScope(SearchScope.ONELEVEL)
        .countLimit(100)
        .timeLimit(2_000)
        .attributes("uid", "cn", "mail")
        .where("objectClass").is("inetOrgPerson")
        .and("uid").is(validatedUid);

List<PersonSummary> people =
        ldapTemplate.search(ldapQuery, personSummaryMapper);
~~~

Cách này giúp query giữ base, scope, filter, giới hạn và projection cùng một chỗ. Đối chiếu API/Javadoc của phiên bản Spring LDAP đang dùng trước khi sao chép vì overload và kiểu tham số có thể thay đổi giữa các dòng.

Dù dùng SearchControls hay LdapQueryBuilder, hãy đặt giới hạn ở phía server request và vẫn có giới hạn ở tầng ứng dụng. Không dựa vào việc controller chỉ lấy 10 phần tử đầu từ một List đã được load toàn bộ.

## 12. Projection: chỉ trả attribute cần thiết

LDAP entry có thể chứa rất nhiều attribute: ảnh, certificate, group membership, thông tin vận hành, dữ liệu audit và thuộc tính xác thực. Nếu use case chỉ hiển thị tên, email và UID, hãy yêu cầu đúng ba attribute đó.

Ví dụ projection:

~~~java
controls.setReturningAttributes(
        new String[] {"uid", "cn", "mail"});
~~~

Không yêu cầu các attribute sau trong search thông thường nếu không có use case và quyền rõ ràng:

- userPassword hoặc attribute credential tương đương.
- jpegPhoto, userCertificate và binary blob.
- member/uniqueMember khi chỉ hiển thị group metadata.
- operational attributes không cần cho nghiệp vụ.
- attribute chứa PII nhạy cảm.
- wildcard "*" hoặc "+" để lấy toàn bộ user/operational attributes.

Một số LDAP server xử lý attribute operational riêng; dấu "*" và "+" có semantics khác nhau. API công khai nên dùng allowlist tên attribute cụ thể thay vì nhận wildcard từ client.

Projection giúp giảm response bytes và bộ nhớ, nhưng server vẫn phải xử lý filter. Cần kết hợp index, scope và time limit.

## 13. Giới hạn kích thước dữ liệu trả về

Giới hạn số entry chưa đủ. Một entry có thể chứa attribute đa trị hàng nghìn giá trị hoặc một giá trị binary rất lớn.

Thiết kế response budget theo nhiều chiều:

| Giới hạn | Ví dụ policy | Mục đích |
|---|---|---|
| Entry count | Tối đa 100 entry/page | Giảm số object |
| Page count | Tối đa 10 page/request workflow | Ngăn enumerate vô hạn |
| Attribute allowlist | uid, cn, mail | Giảm data exposure |
| Attribute value count | Giới hạn số member hiển thị | Tránh list quá lớn |
| Attribute value length | Giới hạn chuỗi theo schema/use case | Chặn payload bất thường |
| Binary attributes | Không trả trong search list | Tránh response nặng |
| HTTP response size | Giới hạn bytes ở API/gateway | Bảo vệ heap và network |
| Processing time | Deadline tổng cho workflow | Không giữ worker vô hạn |

Các con số trong bảng chỉ minh họa; phải xác định theo tải thực tế, schema và server policy. Không có một giới hạn attribute-value count phổ quát áp dụng cho mọi LDAP server.

Nếu cần tải binary, tạo endpoint riêng có authorization, quota, streaming và audit. Không gộp binary vào endpoint tìm kiếm danh sách.

## 14. Phân trang bằng LDAP Paged Results Control

RFC 2696 định nghĩa Paged Results Control để chia SearchResult thành các trang. Spring LDAP cung cấp PagedResultsDirContextProcessor để làm việc với control này.

Phân trang giúp giới hạn lượng dữ liệu xử lý mỗi lần, nhưng **không phải giới hạn tổng số kết quả**. Một client có thể tiếp tục gửi cookie để lấy hết directory nếu ứng dụng không đặt page cap.

Ví dụ khung xử lý:

~~~java
private static final int PAGE_SIZE = 100;
private static final int MAX_PAGES = 10;
private static final long MAX_ENTRIES = 1_000;

public ExportResult exportPeople(Consumer<PersonSummary> consumer) {
    PagedResultsDirContextProcessor processor =
            new PagedResultsDirContextProcessor(PAGE_SIZE);

    LdapQuery ldapQuery = query()
            .base("ou=people")
            .searchScope(SearchScope.ONELEVEL)
            .timeLimit(2_000)
            .attributes("uid", "cn", "mail")
            .where("objectClass").is("inetOrgPerson");

    int pageNumber = 0;
    long entriesProcessed = 0;
    byte[] previousCookie = null;
    long deadlineNanos =
            System.nanoTime() + Duration.ofSeconds(20).toNanos();

    while (true) {
        if (System.nanoTime() >= deadlineNanos) {
            return new ExportResult(
                    pageNumber, entriesProcessed, false);
        }

        List<PersonSummary> page =
                ldapTemplate.search(
                        ldapQuery,
                        personSummaryMapper,
                        processor);

        for (PersonSummary person : page) {
            if (entriesProcessed >= MAX_ENTRIES) {
                return new ExportResult(
                        pageNumber, entriesProcessed, false);
            }
            consumer.accept(person);
            entriesProcessed++;
        }
        pageNumber++;

        byte[] nextCookie = processor.getCookie();
        boolean hasMore = nextCookie != null && nextCookie.length > 0;

        if (!hasMore) {
            return new ExportResult(
                    pageNumber, entriesProcessed, true);
        }

        if (previousCookie != null
                && Arrays.equals(previousCookie, nextCookie)) {
            throw new IllegalStateException(
                    "LDAP paging cookie did not advance");
        }
        previousCookie = nextCookie.clone();

        if (pageNumber >= MAX_PAGES
                || entriesProcessed >= MAX_ENTRIES) {
            return new ExportResult(
                    pageNumber, entriesProcessed, false);
        }
    }
}

public record ExportResult(
        int pages, long entries, boolean complete) {
}
~~~

Đây là khung minh họa; kiểm tra API của phiên bản Spring LDAP và cách processor cập nhật cookie/response control. Ví dụ giả định có MAX_ENTRIES được khai báo cùng PAGE_SIZE và MAX_PAGES, cùng imports cho Arrays, Duration và DTO/mapper. Deadline tổng 20 giây được đo bằng nanoTime; timeLimit của mỗi SearchRequest vẫn được đặt riêng. Production code cần trả trạng thái **incomplete/limit reached** nếu dừng ở bất kỳ quota nào, không báo export hoàn tất.

Một page size nhỏ hơn không tự giảm tổng số dữ liệu nếu client tiếp tục lấy trang. Luôn đặt giới hạn tổng pages, tổng entries, deadline và quyền export.

## 15. Cookie phân trang là trạng thái điều khiển, không phải quyền truy cập

Paged Results cookie là dữ liệu opaque do server cấp để tiếp tục search. Ứng dụng không nên:

- Cho client tự tạo hoặc sửa cookie.
- Chấp nhận cookie từ user khác hoặc tenant khác.
- Dùng cookie với base DN/filter khác.
- Log cookie nguyên văn.
- Lưu cookie vô thời hạn.
- Cho phép client lặp vô hạn chỉ bằng cách gửi lại cookie.

Nếu cần expose cursor cho REST API, tạo cursor token do ứng dụng ký/mã hóa và gắn với user/tenant, query fingerprint, page state, expiry và quota. Cookie LDAP gốc nên được giữ phía server hoặc được bảo vệ trong token có xác thực toàn vẹn.

Khi client gửi cursor, kiểm tra người gọi vẫn có quyền với cùng query scope. Không coi việc có cookie là bằng chứng authorization.

## 16. Server-side administrative limits

Client controls là một lớp bảo vệ. LDAP server cần policy riêng để hạn chế search từ các bind identity.

Ví dụ:

- OpenLDAP có cơ chế limits theo database/identity và các cấu hình như olcLimits.
- Active Directory áp dụng LDAP query policies như giới hạn số entry trả về, thời gian truy vấn và một số tài nguyên search.
- Các sản phẩm directory khác có cấu hình admin limit, maximum page size, query duration hoặc giới hạn operation riêng.

Tên tham số, default và phạm vi áp dụng phụ thuộc sản phẩm/version. Không sao chép cấu hình OpenLDAP sang Active Directory hoặc ngược lại.

Hãy cấu hình server limits để bảo vệ directory ngay cả khi một ứng dụng bị lỗi hoặc bị chiếm quyền. App-side countLimit không đủ vì client có thể bỏ qua code đó và gửi LDAP request trực tiếp nếu credential bị lộ.

## 17. Bind identity và ACL giới hạn dữ liệu đọc

Dùng service account có quyền đọc tối thiểu:

- Search account chỉ đọc các OU và attribute phục vụ use case.
- Provisioning account có quyền ghi trên OU cần thiết.
- Account quản trị directory tách biệt khỏi ứng dụng runtime.
- Không dùng Directory Manager/domain admin cho search thông thường.
- ACL phải giới hạn cả entry lẫn attribute.

Một ứng dụng có thể projection chỉ trả uid, cn, mail nhưng bind identity vẫn có quyền đọc mọi attribute. Nếu một endpoint khác bị lỗi, dữ liệu nhạy cảm vẫn có thể bị lộ. ACL server-side là lớp bảo vệ độc lập với DTO.

Nếu cần nhiều quyền search khác nhau, cân nhắc tách service account hoặc ContextSource theo use case. Không truyền bind credential từ client.

## 18. Giới hạn tần suất request

Rate limit ngăn một người gọi gửi quá nhiều SearchRequest trong một khoảng thời gian.

Các chiều quota có thể gồm:

| Dimension | Ví dụ |
|---|---|
| User/service principal | Số search mỗi phút |
| Tenant/business unit | Tổng request và entry trả về |
| Endpoint/use case | Search UID khác với bulk export |
| Source IP/API client | Phát hiện client bị lỗi hoặc lạm dụng |
| Query cost class | Presence/subtree search có quota thấp hơn exact lookup |
| Export job | Số job đồng thời và tổng page budget |

Không dùng một quota chung cho mọi query. Một exact lookup theo UID trong ONELEVEL scope rẻ hơn một subtree search với substring filter trên attribute không index.

Rate limit cần được thực thi ở API gateway và/hoặc application service. Nếu có nhiều instance ứng dụng, quota toàn hệ thống cần dùng bộ đếm phân tán hoặc gateway chung; limiter trong bộ nhớ từng instance chỉ giới hạn cục bộ.

## 19. Giới hạn concurrency và backpressure

Rate limit kiểm soát số request trong thời gian; concurrency limit kiểm soát số request đang chạy đồng thời.

Ví dụ:

~~~text
Incoming search requests
          |
          v
   Per-user rate limiter
          |
          v
   Global concurrency cap
          |
          v
   LDAP connection pool
          |
          v
      LDAP server
~~~

Các nguyên tắc:

- Đặt giới hạn số search đồng thời cho endpoint.
- Giới hạn số bulk export worker.
- Dùng queue/backpressure khi công việc vượt năng lực.
- Không để request chờ vô hạn connection pool.
- Tách workload interactive (login/lookup) khỏi bulk reconciliation/export nếu có thể.
- Có deadline tổng và cancellation khi client disconnect.
- Khi quá tải, trả 429/503 theo contract thay vì xếp hàng vô hạn.

Connection pool chỉ tái sử dụng connection và giới hạn số connection; nó không tự giới hạn request rate hay chi phí filter. Một connection có thể thực hiện nhiều operation theo thời gian.

## 20. Timeout ở nhiều lớp

Một search có thể chờ ở nhiều giai đoạn:

1. Chờ connection pool cấp context.
2. Kết nối TCP/TLS.
3. Bind/authentication.
4. Server đánh giá filter.
5. Server trả entry và controls.
6. Client đọc hết NamingEnumeration.
7. Ứng dụng map DTO và serialize response.

SearchControls timeLimit chủ yếu đặt giới hạn thời gian search tại server. Nó không thay thế connection timeout, read/socket timeout, pool acquisition timeout hay deadline HTTP.

Hãy đặt timeout theo thứ tự phù hợp: thời gian chờ pool và connect phải nằm trong request budget; server search limit ngắn hơn deadline tổng; ứng dụng còn thời gian xử lý response và trả lỗi có kiểm soát.

Không đặt client timeout quá ngắn đến mức client thường xuyên bỏ cuộc trong khi server vẫn xử lý query. Khi timeout, connection/context có thể cần được đóng hoặc loại khỏi pool theo hành vi provider.

## 21. Xử lý sizeLimitExceeded và timeLimitExceeded

LDAP có result code phổ biến:

| Result code | Tên | Ý nghĩa xử lý |
|---:|---|---|
| 3 | timeLimitExceeded | Server dừng search do vượt time limit |
| 4 | sizeLimitExceeded | Search vượt giới hạn số entry |
| 11 | adminLimitExceeded | Vượt administrative limit của server |
| 12 | unavailableCriticalExtension | Server không hỗ trợ critical control/extension |
| 50 | insufficientAccessRights | Bind identity không đủ quyền |
| 51 | busy | Server tạm thời bận |
| 52 | unavailable | Directory không khả dụng |

Tùy JNDI provider và Spring LDAP version, lỗi có thể được chuyển thành các exception trong hệ thống NamingException/DataAccessException. Hãy log result code gốc nếu có thể và phân biệt lỗi limit với lỗi kết nối.

Nếu search bị giới hạn:

- Không coi tập kết quả nhận được là đầy đủ.
- Không đánh dấu batch đồng bộ đã hoàn tất.
- Không tự tăng limit rồi retry vô hạn.
- Ghi lại query fingerprint, base/scope, page, thời gian và limit đã chạm.
- Thu hẹp filter/base hoặc chuyển sang pagination/job quản trị có quota.
- Nếu cần dữ liệu đầy đủ, tiếp tục theo cursor/checkpoint có kiểm soát hoặc báo rõ incomplete.

## 22. Retry khi LDAP bận hoặc quá tải

Retry có thể làm tình hình xấu hơn nếu không giới hạn.

| Lỗi | Retry? | Hướng xử lý |
|---|---|---|
| Invalid filter / invalid DN | Không | Sửa input/code |
| Insufficient access rights | Không retry tự động | Sửa ACL/bind identity |
| Size/time/admin limit | Không retry cùng query vô hạn | Thu hẹp query hoặc thay đổi job policy |
| Busy / unavailable tạm thời | Có giới hạn | Exponential backoff + jitter |
| Connection reset | Có điều kiện | Reconnect, giới hạn attempts, quan sát unknown outcome |
| Client cancelled | Không | Dừng xử lý và giải phóng tài nguyên |
| Unavailable critical extension | Không lặp cùng request | Kiểm tra server capability hoặc bỏ tính năng theo policy |

Với SearchRequest thuần đọc, retry thường không làm thay đổi dữ liệu nhưng vẫn tạo tải lặp. Dùng số lần retry nhỏ, backoff có jitter, circuit breaker và global concurrency cap.

Không retry từng page đồng thời trên nhiều worker nếu server đang trả busy. Tạm giảm tốc độ và resume từ trạng thái cookie/checkpoint hợp lệ.

## 23. Cache và dữ liệu nhạy cảm

Cache có thể giảm số search lặp lại, nhưng cần đánh đổi freshness và quyền truy cập.

- Cache metadata ít thay đổi như danh mục OU hoặc thông tin hiển thị công khai trong ứng dụng.
- Cache theo identity/tenant và quyền truy cập; không dùng cache key chỉ dựa trên uid nếu kết quả phụ thuộc caller.
- TTL ngắn hơn cho membership/authorization.
- Invalidate khi dữ liệu nguồn thay đổi nếu có event đáng tin cậy.
- Không cache userPassword, credential, token hoặc dữ liệu nhạy cảm không cần thiết.
- Không dùng stale cache để cấp quyền nhạy cảm nếu policy yêu cầu kiểm tra hiện thời.
- Giới hạn kích thước cache và chống cache stampede.

Cache không thay thế ACL và không nên trở thành bản sao dữ liệu LDAP không kiểm soát. Log cache hit/miss bằng metric tổng hợp, không ghi PII vào label.

## 24. Logging và observability an toàn

Theo dõi chất lượng và mức độ sử dụng query mà không ghi dữ liệu nhạy cảm.

Metric gợi ý:

- ldap_search_requests_total{use_case,result}
- ldap_search_duration_seconds{use_case}
- ldap_search_entries_returned{use_case}
- ldap_search_limit_reached_total{limit_type}
- ldap_search_response_bytes
- ldap_search_pages_total{use_case}
- ldap_search_rate_limited_total{use_case}
- ldap_search_in_flight
- ldap_connection_pool_wait_seconds
- ldap_search_retry_total{reason}

Không dùng DN, uid, email, filter đầy đủ, raw cookie hoặc attribute value làm metric label. Những giá trị này tạo cardinality cao và có thể chứa PII.

Log có thể ghi:

- Correlation/request ID.
- Use case và endpoint.
- Base alias đã cấu hình, scope và query class.
- Filter template đã redact.
- Count/time limit, page size và số kết quả.
- Result code và thời gian.
- Caller/service principal ở dạng đã bảo vệ.

Không log bind password, userPassword, certificate bytes, toàn bộ member list hoặc raw filter có dữ liệu người dùng.

## 25. Kiểm thử chống enumeration và query abuse

Một bộ test nên xác minh cả giới hạn ứng dụng lẫn hành vi server.

| Kịch bản | Kết quả mong đợi |
|---|---|
| Base DN bị client thay đổi | Bị từ chối hoặc bỏ qua, dùng base allowlist |
| Client gửi raw filter | API không chấp nhận |
| UID quá dài | Validation từ chối trước LDAP call |
| UID chứa ký tự filter đặc biệt | Được encode an toàn hoặc validation từ chối |
| Scope SUBTREE không được phép | Không thể bật qua request |
| Count limit bằng 0 | Không được cấu hình cho endpoint công khai |
| Query trả hơn count limit | Báo incomplete/limit reached |
| Server time limit exceeded | Không coi partial result là đầy đủ |
| Client lặp cookie | Page cap/rate limit chặn |
| Cookie của tenant khác | Bị từ chối |
| Request vượt quota | Trả 429/503 theo policy |
| Nhiều request đồng thời | Concurrency cap/backpressure có hiệu lực |
| Attribute binary không trong allowlist | Không được trả |
| Bind identity thiếu ACL | Server từ chối đọc attribute |
| LDAP busy/unavailable | Retry bounded, không tạo retry storm |
| Filter unindexed trong test | Timeout/alert/cost policy phát hiện |

Dùng directory test có dữ liệu đủ lớn và index giống production. Mock LdapTemplate chỉ kiểm tra code tạo query; nó không chứng minh server áp dụng size/time/admin limits.

## 26. Ví dụ kiểm thử giới hạn SearchControls

Một unit test có thể xác minh ứng dụng đặt giới hạn trước khi gọi LDAP. Với Spring LDAP, dùng mock/spy LdapTemplate hoặc tách hàm tạo SearchControls để test:

~~~java
SearchControls controls = buildPersonSearchControls();

assertEquals(
        SearchControls.ONELEVEL_SCOPE,
        controls.getSearchScope());

assertEquals(100L, controls.getCountLimit());
assertEquals(2_000, controls.getTimeLimit());

assertArrayEquals(
        new String[] {"uid", "cn", "mail"},
        controls.getReturningAttributes());

assertFalse(controls.getReturningObjFlag());
~~~

Hàm cấu hình nên có policy constants tập trung:

~~~java
static SearchControls buildPersonSearchControls() {
    SearchControls controls = new SearchControls();
    controls.setSearchScope(SearchControls.ONELEVEL_SCOPE);
    controls.setCountLimit(100);
    controls.setTimeLimit(2_000);
    controls.setReturningAttributes(
            new String[] {"uid", "cn", "mail"});
    controls.setReturningObjFlag(false);
    controls.setDerefLinkFlag(false);
    return controls;
}
~~~

Unit test chứng minh ứng dụng không quên đặt giới hạn. Integration test vẫn cần xác minh LDAP server thực thi controls và trả result code như dự kiến.

## 27. Runbook khi truy vấn vượt giới hạn

Khi metric cho thấy query thường xuyên chạm limit:

1. Xác định use case và caller, không bắt đầu bằng cách tăng limit.
2. Kiểm tra base DN và scope có rộng hơn cần thiết không.
3. Kiểm tra filter có presence/substring/OR quá lớn không.
4. Kiểm tra attribute có index phù hợp không.
5. Kiểm tra projection có đang lấy binary/multi-valued data không.
6. Đối chiếu count/time limit phía ứng dụng và administrative limit phía server.
7. Xem số request đồng thời, pool wait và retry.
8. Chạy lại với dataset đại diện trong môi trường test.
9. Thay query hoặc chuyển sang export job có quota/checkpoint.
10. Chỉ điều chỉnh server limit sau khi có đánh giá tải và phê duyệt vận hành.

Nếu query phục vụ login hoặc authorization, không để một bulk export cạnh tranh cùng quota/connection pool mà không có phân tách workload. Cần ưu tiên luồng tương tác quan trọng và giới hạn job nền.

## 28. Bài tập thực hành

**Bối cảnh:** API tìm kiếm nhân viên đang cho phép client gửi UID, base DN, scope và raw LDAP filter. API trả toàn bộ attributes thành JSON. Một client nội bộ có thể gửi request liên tục.

Thực hiện trên LDAP test:

1. Thiết kế lại API chỉ nhận các tham số nghiệp vụ được allowlist.
2. Cố định base DN theo use case và chọn ONELEVEL hoặc OBJECT scope phù hợp.
3. Dùng AndFilter/EqualsFilter để tạo filter; không nối chuỗi từ input.
4. Validate độ dài/format UID và giới hạn số phần tử trong filter OR.
5. Đặt SearchControls countLimit, timeLimit, returningAttributes và returningObjFlag.
6. Viết DTO chỉ chứa uid, cn, mail.
7. Thêm LDAP Paged Results với page size cố định và MAX_PAGES.
8. Khi đạt MAX_PAGES, trả trạng thái incomplete thay vì giả vờ đã lấy hết.
9. Tạo cursor API gắn với caller, tenant, query fingerprint và expiry.
10. Thêm rate limit theo principal/tenant và concurrency cap.
11. Mô phỏng sizeLimitExceeded, timeLimitExceeded, adminLimitExceeded và busy.
12. Viết retry bounded với backoff/jitter cho lỗi tạm thời.
13. Xác minh bind identity chỉ đọc được OU/attribute được phép.
14. Kiểm tra không trả userPassword, binary photo hoặc group membership ngoài nhu cầu.
15. Đo response bytes, query duration, entries/page, pages/request và limit-reached count.
16. Mô phỏng client lặp cookie và gửi nhiều request đồng thời; xác minh quota/backpressure.
17. Viết runbook xử lý query chạm limit mà không tăng limit mù quáng.

**Tiêu chí hoàn thành:** API không nhận raw filter/base/scope tùy ý, mọi search có giới hạn thời gian/số entry/projection, pagination có tổng quota, tần suất/concurrency được kiểm soát, server ACL/administrative limits được xác minh và partial results không bị coi là hoàn tất.

## 29. Tổng kết và tài liệu tham khảo

Bảo vệ LDAP Search đòi hỏi giới hạn ở nhiều lớp. Base DN và scope xác định vùng dữ liệu; filter và index ảnh hưởng chi phí server; count/time limit hạn chế một request; projection và response budget giảm dữ liệu; page cap, rate limit và concurrency cap ngăn enumeration và quá tải.

Các nguyên tắc cần nhớ:

- Không nhận raw LDAP filter, base DN hoặc scope tùy ý từ client.
- Dùng allowlist và Filter API để encode assertion values.
- Chọn base/scope nhỏ nhất đáp ứng use case.
- Đặt countLimit và timeLimit; tránh giá trị 0 của SearchControls vì đó là không giới hạn.
- Chỉ trả attribute cần thiết và map sang DTO.
- Pagination không thay thế giới hạn tổng số trang/kết quả.
- Cookie là trạng thái điều khiển, không phải authorization token.
- Kết hợp client controls với server administrative limits và ACL.
- Rate limit, concurrency cap, backpressure và retry bounded phải hoạt động cùng nhau.
- Không coi partial result do limit là dữ liệu hoàn chỉnh.
- Log query metadata đã redact, không log PII hoặc credential.
- Kiểm thử với directory server thật và dữ liệu đại diện.

Tài liệu tham khảo:

- [RFC 4511 — Lightweight Directory Access Protocol: The Protocol](https://www.rfc-editor.org/rfc/rfc4511): SearchRequest, SearchResult, limits và LDAP controls.
- [RFC 4515 — LDAP String Representation of Search Filters](https://www.rfc-editor.org/rfc/rfc4515): cú pháp và escaping assertion value trong filter.
- [RFC 2696 — LDAP Control Extension for Simple Paged Results Manipulation](https://www.rfc-editor.org/rfc/rfc2696): Paged Results Control và cookie.
- [Java SE — SearchControls](https://docs.oracle.com/en/java/javase/21/docs/api/java.naming/javax/naming/directory/SearchControls.html): search scope, count limit, time limit và returning attributes.
- [Spring LDAP Reference](https://docs.spring.io/spring-ldap/reference/): LdapTemplate, query builder, filter API và paged results processor.
- [OpenLDAP Administrator's Guide — Limits](https://www.openldap.org/doc/admin26/limits.html): giới hạn search theo identity/database trong OpenLDAP.
- [Microsoft Learn — LDAP policies](https://learn.microsoft.com/en-us/troubleshoot/windows-server/active-directory/view-set-ldap-policy-using-ntdsutil): LDAP query policies và administrative limits trong Active Directory.
- [OWASP — LDAP Injection](https://owasp.org/www-community/attacks/LDAP_Injection): rủi ro filter injection và cách phòng tránh.
