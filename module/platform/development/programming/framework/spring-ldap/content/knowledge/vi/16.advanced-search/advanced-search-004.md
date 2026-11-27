# Paged results control để phân trang LDAP

## Mục tiêu học tập

Trong chương **Search nâng cao** của Spring LDAP, bài này giải thích cách lấy kết quả tìm kiếm LDAP theo từng đợt bằng **Simple Paged Results Control** (RFC 2696). Khi hoàn thành, bạn có thể:

- Giải thích vì sao phân trang LDAP sử dụng **control và cookie**, thay vì chỉ truyền số trang/offset như cơ sở dữ liệu quan hệ.
- Mô tả vòng lặp request/response của **OID `1.2.840.113556.1.4.319`** và nhận biết điều kiện kết thúc.
- Sử dụng `LdapTemplate.search(...)` kết hợp `PagedResultsDirContextProcessor`, `SearchControls` và `AttributesMapper` để lấy nhiều trang.
- Giữ nguyên base DN, filter, search scope và các tùy chọn tìm kiếm qua các request cùng một chuỗi phân trang.
- Hiểu giới hạn về hỗ trợ của máy chủ, kích thước trang, hiệu năng, thứ tự kết quả, cookie, đồng thời biết cách kiểm thử và xử lý lỗi an toàn.

Bài học áp dụng cho **Spring LDAP** khi tìm kiếm dữ liệu thư mục thông qua `ContextSource` và `LdapTemplate`. Khi dùng JNDI, `LdapClient` hoặc ODM, ngữ nghĩa của LDAP paged results vẫn do máy chủ và RFC 2696 quyết định, dù API gọi có thể khác.

## 1. Vì sao tìm kiếm LDAP cần phân trang?

Giả sử `ou=people,dc=example,dc=org` có 30.000 entry nhân viên. Ứng dụng cần đồng bộ thuộc tính `uid`, `cn` và `mail` mỗi ngày. Một truy vấn lấy toàn bộ kết quả trong một lần có thể gặp các vấn đề:

- Máy chủ giới hạn số entry trả về trong một yêu cầu hoặc trong một phiên tìm kiếm.
- Client nhận quá nhiều dữ liệu cùng lúc, làm tăng bộ nhớ và thời gian xử lý.
- Kết nối và tài nguyên phía máy chủ bị chiếm dụng lâu.
- Nếu gặp lỗi ở cuối quá trình, việc kiểm tra tiến độ và khôi phục khó hơn.

**Simple Paged Results Control** giúp chia một tìm kiếm logic thành nhiều request. Client yêu cầu *khoảng* 100 entry ở mỗi trang; máy chủ trả một tập kết quả kèm **cookie** để client xin trang tiếp theo. Kích thước trang là yêu cầu/hướng dẫn cho máy chủ, không phải cam kết về số lượng tuyệt đối trong từng response.

Ví dụ minh họa cho một tập 235 entry, page size = 100:

~~~text
Client                         LDAP server
  | Request size=100, cookie=""   |
  | ----------------------------> |
  | <---- 100 entries + cookie A  |
  |                               |
  | Request size=100, cookie=A    |
  | ----------------------------> |
  | <---- 100 entries + cookie B  |
  |                               |
  | Request size=100, cookie=B    |
  | ----------------------------> |
  | <---- 35 entries + cookie=""  |
  |                               |
  |   Kết thúc chuỗi phân trang   |
~~~

Số lượng `100 / 100 / 35` là kịch bản điển hình, không phải một quy tắc cố định: server có thể trả trang ít hơn page size hoặc áp đặt giới hạn riêng. **Điều kiện kết thúc chuẩn là cookie rỗng do server trả về**, không phải `page.size() < pageSize`.

### Phân trang LDAP khác gì LIMIT/OFFSET?

| Tiêu chí | Paged Results Control (LDAP) | Phân trang bằng LIMIT/OFFSET (SQL điển hình) |
| --- | --- | --- |
| Cách xin trang tiếp | Gửi lại cookie do máy chủ trả về | Chỉ định offset hoặc page number |
| Tùy ý nhảy đến trang 10 | Không có cơ chế nhảy trang trực tiếp trong RFC 2696 | Có thể chỉ định offset |
| Trạng thái | Cookie đại diện cho trạng thái phân trang do server quản lý | Offset là vị trí số học |
| Thứ tự kết quả | Không tự bảo đảm thứ tự ổn định | Phụ thuộc `ORDER BY` |
| Kết thúc | Cookie rỗng | Tùy ứng dụng/DB dựa trên số hàng |
| Ràng buộc chính | LDAP server phải hỗ trợ control, các request phải tương thích cùng một search | SQL engine và chiến lược truy vấn |

Trong hệ thống cần hiển thị giao diện “Trang 1, 2, 3...” hoặc nhảy thẳng đến trang bất kỳ, cần thiết kế API phía ứng dụng phù hợp với đặc điểm **cursor-based paging** này.

## 2. RFC 2696: cấu trúc control và cookie

Simple Paged Results Control được định danh bởi OID:

~~~text
1.2.840.113556.1.4.319
~~~

Đây là LDAP **control** gắn vào một thao tác Search, không phải filter và cũng không phải thuộc tính của LDAP entry.

Ở mức giao thức, giá trị control có cấu trúc logic:

~~~text
realSearchControlValue ::= SEQUENCE {
    size     INTEGER (0..maxInt),
    cookie   OCTET STRING
}
~~~

Trong **request**:

- `size` là số entry mong muốn mỗi trang, thường chọn một số nguyên dương phù hợp tải và chính sách server.
- `cookie` rỗng ở request đầu tiên; từ trang thứ hai trở đi phải dùng cookie nhận được ở response trước.

Trong **response**:

- `size` có thể là ước lượng tổng số entry thỏa mãn, hoặc **0 nếu máy chủ không cung cấp ước lượng**. Không coi đây là tổng chính xác trong mọi trường hợp.
- `cookie` khác rỗng nghĩa là máy chủ còn trạng thái để truy xuất trang sau. Cookie rỗng báo kết thúc chuỗi.

**Cookie là dữ liệu mờ (opaque).** Client không phân tích nội dung, không tự tạo, không tăng cookie như offset và không dùng cookie của một truy vấn cho truy vấn khác. Cookie có thể gắn với trạng thái tìm kiếm và máy chủ cụ thể, có thể hết hiệu lực theo thời gian hoặc khi kết nối/server thay đổi.

### Vòng đời một phiên tìm kiếm phân trang

1. Client gửi Search với filter, base DN, scope và paged results request control có `cookie=""`.
2. Server trả các entry trong trang và paged results response control kèm cookie.
3. Nếu cookie khác rỗng, client gửi Search **cùng phạm vi và điều kiện tìm kiếm**, mang cookie vừa nhận.
4. Lặp cho đến khi server trả cookie rỗng.
5. Nếu cần dừng sớm chuỗi phân trang, RFC 2696 cho phép một yêu cầu hủy bằng `size=0` và cookie đang có; cách thực hiện cụ thể phụ thuộc API LDAP/client. Đừng chỉ giả định bỏ vòng lặp sẽ lập tức dọn sạch mọi trạng thái phía server.

Điều này khác với việc gọi nhiều lần một search thường: nếu mỗi lần khởi tạo cookie rỗng, bạn đang bắt đầu **nhiều search mới** và có thể chỉ đọc lặp lại trang đầu.

## 3. Spring LDAP cung cấp những thành phần nào?

Thư viện Spring LDAP có lớp **`org.springframework.ldap.control.PagedResultsDirContextProcessor`** để điều khiển quá trình phân trang trong `LdapTemplate`.

| Thành phần | Vai trò |
| --- | --- |
| `LdapTemplate` | Thực hiện LDAP Search thông qua `ContextSource` đã cấu hình |
| `SearchControls` | Chọn scope, giới hạn và những thuộc tính cần lấy |
| `AttributesMapper<T>` | Chuyển một tập thuộc tính LDAP thành đối tượng ứng dụng |
| `PagedResultsDirContextProcessor` | Gắn paged results request control, đọc response control và quản lý cookie |
| `hasMore()` | Cho biết processor nhận được trạng thái còn trang để đọc |
| `PagedResultsCookie` | Kiểu dữ liệu do Spring LDAP cung cấp để mang cookie phân trang khi cần |
| `ContextSource` | Cấu hình máy chủ, base DN, tài khoản bind, TLS và context được `LdapTemplate` sử dụng |

Thông thường ứng dụng chỉ cần tạo **một processor cho mỗi lần duyệt một tìm kiếm logic**, gọi nhiều lần `LdapTemplate.search(...)` với cùng processor, rồi tiếp tục khi `processor.hasMore()` trả `true`.

Lưu ý: processor mang trạng thái cookie, vì vậy **không dùng chung một instance cho nhiều truy vấn song song**. Mỗi luồng/công việc có một processor độc lập để tránh trộn trạng thái phân trang.

## 4. Ví dụ đầy đủ: đọc toàn bộ UID theo từng trang

Giả sử server có cây dữ liệu:

~~~ldif
dn: ou=people,dc=example,dc=org
objectClass: top
objectClass: organizationalUnit
ou: people

dn: uid=lan,ou=people,dc=example,dc=org
objectClass: inetOrgPerson
uid: lan
cn: Lan Tran
sn: Tran
mail: lan@example.org

dn: uid=minh,ou=people,dc=example,dc=org
objectClass: inetOrgPerson
uid: minh
cn: Minh Nguyen
sn: Nguyen
mail: minh@example.org
~~~

Giả sử `ContextSource` đã cấu hình base DN `dc=example,dc=org`. Trong `LdapTemplate.search`, đối số base `"ou=people"` được hiểu **tương đối với base DN trong `ContextSource`**. Ví dụ Java:

~~~java
import java.util.List;
import java.util.function.Consumer;

import javax.naming.directory.SearchControls;

import org.springframework.ldap.control.PagedResultsDirContextProcessor;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.stereotype.Service;

@Service
public class PeoplePagingService {

    private static final int PAGE_SIZE = 100;
    private final LdapTemplate ldapTemplate;

    public PeoplePagingService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public void processUidPages(Consumer<List<String>> onPage) {
        SearchControls controls = new SearchControls();
        controls.setSearchScope(SearchControls.ONELEVEL_SCOPE);
        controls.setReturningAttributes(new String[] {"uid"});

        // Processor thuộc riêng một lần duyệt.
        PagedResultsDirContextProcessor paging =
            new PagedResultsDirContextProcessor(PAGE_SIZE);

        AttributesMapper<String> uidMapper =
            attrs -> (String) attrs.get("uid").get();

        do {
            List<String> page = ldapTemplate.search(
                "ou=people",
                "(objectClass=inetOrgPerson)",
                controls,
                uidMapper,
                paging
            );

            // Có thể lưu vào DB, xử lý batch, hoặc đẩy sang pipeline.
            onPage.accept(page);
        } while (paging.hasMore());
    }
}
~~~

Cách gọi từ tầng ứng dụng:

~~~java
peoplePagingService.processUidPages(page -> {
    for (String uid : page) {
        System.out.println("Found uid: " + uid);
    }
});
~~~

Ví dụ in UID ở đây để minh họa; trong ứng dụng thực tế tránh log dữ liệu định danh không cần thiết. Nên thay bằng xử lý batch có kiểm soát như cập nhật bảng đồng bộ.

### Giải thích đoạn mã

**1. `SearchControls.ONELEVEL_SCOPE`:** tìm các entry là **con trực tiếp** của `ou=people`. Nếu cần cả các nhánh lồng nhau, có thể chọn `SUBTREE_SCOPE`; nếu chỉ cần bản thân entry base thì dùng `OBJECT_SCOPE`. Scope ảnh hưởng trực tiếp đến số lượng kết quả.

**2. `setReturningAttributes(new String[] {"uid"})`:** chỉ yêu cầu thuộc tính cần dùng, giảm dung lượng truyền và xử lý. Nếu mapper cần `cn` hoặc `mail`, phải đưa chúng vào danh sách thuộc tính trả về.

**3. Filter `(objectClass=inetOrgPerson)`:** tìm những entry thuộc loại tương ứng. Filter và base cần giữ nguyên trong cả chuỗi phân trang.

**4. `PagedResultsDirContextProcessor(PAGE_SIZE)`:** processor tạo request control và ghi nhận cookie sau khi `LdapTemplate.search` kết thúc.

**5. `onPage.accept(page)`:** xử lý ngay kết quả từng đợt thay vì cộng tất cả vào một danh sách khổng lồ. Đây là ưu điểm quan trọng của phân trang đối với các công việc đồng bộ lớn.

**6. `while (paging.hasMore())`:** tiếp tục dựa vào trạng thái cookie đã xử lý, kể cả khi trang vừa nhận có ít hơn `PAGE_SIZE` entry.

Ví dụ này **giả định server hỗ trợ Simple Paged Results Control** và mỗi entry khớp filter có thuộc tính `uid`. Nếu schema hoặc loại entry thực tế không bảo đảm `uid`, mapper cần kiểm tra `attrs.get("uid")` trước khi gọi `get()`.

## 5. Nếu muốn lấy cả UID, tên và email?

Ứng dụng thường muốn ánh xạ dữ liệu LDAP vào DTO. Với Java record:

~~~java
public record PersonSummary(String uid, String cn, String mail) {}
~~~

Ta có thể thay mapper ở ví dụ trên bằng:

~~~java
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;
import org.springframework.ldap.core.AttributesMapper;

static String firstValueOrNull(Attributes attrs, String attributeId)
        throws javax.naming.NamingException {
    Attribute attr = attrs.get(attributeId);
    return attr == null ? null : (String) attr.get();
}

AttributesMapper<PersonSummary> personMapper = attrs ->
    new PersonSummary(
        firstValueOrNull(attrs, "uid"),
        firstValueOrNull(attrs, "cn"),
        firstValueOrNull(attrs, "mail")
    );
~~~

Đồng thời đổi dòng cấu hình:

~~~java
controls.setReturningAttributes(
    new String[] {"uid", "cn", "mail"}
);
~~~

Và khai báo nhận `List<PersonSummary>` trong vòng lặp:

~~~java
List<PersonSummary> page = ldapTemplate.search(
    "ou=people",
    "(objectClass=inetOrgPerson)",
    controls,
    personMapper,
    paging
);
~~~

Các snippet trong phần này là những đoạn **thay thế tương ứng** trong service, không phải đặt liền nhau thành một file Java độc lập. Attribute LDAP có thể có nhiều giá trị hoặc kiểu dữ liệu khác chuỗi: khi xử lý dữ liệu thật, mapper cần tuân thủ schema và nghiệp vụ.

## 6. Chọn kích thước trang và giới hạn tìm kiếm

**Page size** nên được chọn dựa trên tải và khả năng của server, không phải “càng lớn càng tốt”. Chẳng hạn có thể bắt đầu thử nghiệm ở 100–500 entry/trang, đo thời gian response, bộ nhớ và giới hạn cấu hình của máy chủ rồi điều chỉnh.

Ba loại giới hạn có thể cùng tồn tại:

| Giới hạn | Cấp áp dụng | Điểm cần biết |
| --- | --- | --- |
| `PAGE_SIZE` của paged results control | Số entry **mong muốn** trong một trang | Không phải bảo đảm số trả về hay số entry được phép đọc tổng cộng |
| `SearchControls.setCountLimit(...)` | Giới hạn tìm kiếm được gửi theo request | Có thể làm tìm kiếm dừng/đụng giới hạn; không dùng nó thay cơ chế cookie |
| Server-side size/time/administrative limits | Chính sách máy chủ LDAP | Có thể từ chối, giới hạn hoặc chấm dứt tìm kiếm ngay cả khi client yêu cầu phân trang |

Ví dụ:

~~~java
SearchControls controls = new SearchControls();
controls.setSearchScope(SearchControls.SUBTREE_SCOPE);
controls.setReturningAttributes(new String[] {"uid", "cn"});

// Không đặt countLimit bằng PAGE_SIZE để "phân trang".
// Số trang do PagedResultsDirContextProcessor quản lý.
~~~

**Không nên bật `setCountLimit(PAGE_SIZE)` với suy nghĩ đó là số entry mỗi trang**. Count limit có ngữ nghĩa giới hạn toàn bộ tìm kiếm ở tầng Search; tùy server/triển khai, nó có thể kết thúc hoặc làm lỗi phân trang sớm. Để nhận từng trang, hãy cấu hình page size trên processor và thử nghiệm với server đích.

### Kiểm soát tài nguyên khi xử lý nhiều trang

Một công việc nền đọc hàng chục nghìn entry cần:

- Giới hạn số tác vụ phân trang chạy song song và số connection LDAP đang mở.
- Xử lý theo batch và giải phóng dữ liệu đã sử dụng; tránh gom mọi trang vào một `List` không giới hạn.
- Đặt timeout hợp lý ở cả LDAP client và tầng dịch vụ, cân nhắc kích thước page và tốc độ xử lý downstream.
- Ghi nhận số trang/entry đã xử lý, latency và mã lỗi (hạn chế lộ dữ liệu cá nhân).
- Có chiến lược khi task bị hủy hoặc quá tải; theo RFC, yêu cầu hủy paged search dùng cookie hiện tại và size bằng 0 nếu client/API hỗ trợ.

Không tái sử dụng cùng `PagedResultsDirContextProcessor` cho một lần đồng bộ mới sau khi công việc cũ hoàn tất; lần duyệt mới cần bắt đầu với cookie rỗng và bộ trạng thái mới.

## 7. Cookie có phải “số trang” hoặc “token API” không?

Không. Cookie LDAP thường là dữ liệu do server tạo và có ý nghĩa đối với phiên tìm kiếm cụ thể. Một số hệ thống cho phép truyền cookie qua các HTTP request, nhưng điều đó cần cân nhắc kỹ:

1. **Không đọc hay sửa byte cookie.** Nếu cần lưu, bảo toàn đúng dạng byte; không tự cắt chuỗi hoặc dùng cách chuyển mã làm sai dữ liệu.
2. **Gắn cookie với cùng truy vấn.** Base DN, filter, scope và các control liên quan phải tương thích các lần gọi tiếp theo.
3. **Không dùng cookie của user A cho user B.** Cookie có thể liên quan đến dữ liệu, phiên và quyền truy cập; không chia sẻ xuyên danh tính/ngữ cảnh bảo mật.
4. **Chú ý server affinity.** Qua load balancer, mỗi request có thể đến server khác; cookie có thể không được chấp nhận ở server đó.
5. **Xử lý hết hạn.** Restart server, reconnect, thay đổi session hoặc timeout có thể khiến cookie không còn hợp lệ; có thể phải bắt đầu một lần tìm kiếm mới.
6. **Không coi cookie là phân quyền.** Kiểm tra quyền mỗi request, bảo vệ đường truyền bằng TLS và tránh log cookie như dữ liệu debug thông thường.

Spring LDAP có `PagedResultsCookie` để biểu diễn cookie trong các API hỗ trợ. Tuy nhiên, việc “đóng gói cookie thành token HTTP rồi lưu nhiều ngày” là thiết kế ứng dụng riêng; không có bảo đảm rằng mọi LDAP server giữ cookie hợp lệ lâu hoặc qua các kết nối khác nhau.

### Nếu muốn giao diện tìm kiếm có nút Next

Một API có thể trả người dùng một token tiếp tục ở lớp ứng dụng, token này được gắn với người dùng, filter và phạm vi tìm kiếm. API phải giữ cookie đúng cách trong phiên được kiểm soát và xử lý token hết hạn. Nếu giao diện đòi nhảy đến trang 20 bất kỳ, LDAP paged results **không cung cấp offset** để nhảy trực tiếp; cân nhắc kho dữ liệu tìm kiếm riêng hoặc thiết kế UI dựa trên “Tiếp”.

## 8. Tính nhất quán và thứ tự kết quả

Phân trang **không tự bảo đảm ảnh chụp dữ liệu nhất quán (snapshot)** trong suốt nhiều request. Giữa trang 1 và trang 2, một tài khoản có thể được tạo, xóa, đổi DN hoặc sửa thuộc tính.

Ví dụ:

~~~text
Thời điểm T1: nhận trang 1 với uid=a, b, c
Thời điểm T2: quản trị viên đổi tên/move một entry
Thời điểm T3: nhận trang 2 trên tập dữ liệu đã biến đổi
~~~

Tùy server, trạng thái tìm kiếm và cách phân trang, ứng dụng có thể gặp entry bị lặp, bị bỏ sót hoặc thứ tự thay đổi. RFC 2696 **không biến chuỗi Search thành giao dịch đọc nhất quán**.

Ngoài ra, simple paged results control **không sắp xếp** kết quả. Nếu ứng dụng yêu cầu thứ tự có ý nghĩa, cần kiểm tra khả năng kết hợp **server-side sorting control** của LDAP server và thư viện sử dụng; ngay cả khi có sắp xếp, dữ liệu thay đổi đồng thời vẫn cần được xử lý ở tầng nghiệp vụ.

Đối với đồng bộ định kỳ:

- Chọn khóa định danh ổn định khi server cung cấp (ví dụ `entryUUID` hoặc định danh tương đương), thay vì mặc định DN luôn bất biến.
- Xử lý idempotent ở phía nhận: nhiều lần xử lý cùng entry không tạo bản ghi trùng.
- Có lịch chạy lại, đối soát hoặc chiến lược delta sync phù hợp yêu cầu dữ liệu.
- Đừng dùng số entry của một lần phân trang làm bằng chứng tuyệt đối về tổng số user trong directory.

## 9. Lỗi thường gặp và cách chẩn đoán

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra/xử lý |
| --- | --- | --- |
| Luôn nhận trang đầu | Tạo processor/cookie mới mỗi vòng | Tạo processor một lần cho toàn chuỗi search |
| Server báo không hỗ trợ control | Chưa hỗ trợ RFC 2696 hoặc bị chính sách hạn chế | Kiểm tra Root DSE `supportedControl` và cấu hình server |
| Lấy thiếu dữ liệu | Dừng khi `page.size() < PAGE_SIZE` | Chỉ kết thúc theo trạng thái cookie/`hasMore()` |
| Cookie bị từ chối giữa chừng | Hết hạn, nhầm server/connection, đổi query hoặc quyền | Giữ nguyên điều kiện, kiểm tra server affinity; khởi động lại an toàn nếu cần |
| `SizeLimitExceededException` hoặc kết quả bị chặn | Server áp limit; client đặt count limit không phù hợp | Xem chính sách tìm kiếm, `SearchControls` và quyền |
| `NameNotFoundException` khi search | Base DN không tồn tại hoặc base tương đối sai | Kiểm tra `ContextSource.base` và search base |
| Không thấy đủ thuộc tính | `setReturningAttributes(...)` chưa liệt kê trường cần đọc, hoặc ACL hạn chế | Bổ sung thuộc tính và xác minh quyền |
| Đọc thiếu/đúp entry trong dữ liệu biến động | Search bị thay đổi giữa các trang | Dùng xử lý idempotent và chiến lược đối soát |
| Lỗi quyền/timeout/TLS | Bind không có quyền, server quá tải hoặc kết nối không an toàn | Phân loại ngoại lệ, kiểm tra tài khoản, timeout và TLS |

### Kiểm tra hỗ trợ từ máy chủ

Root DSE của một LDAP server thường công bố `supportedControl`. Nếu chứa OID:

~~~text
1.2.840.113556.1.4.319
~~~

thì server quảng bá khả năng xử lý Simple Paged Results Control. Khả năng thực tế còn tùy quyền, giới hạn và cấu hình của server. Không nên suy đoán rằng cứ kết nối LDAP thành công là có thể phân trang.

Có thể kiểm chứng độc lập trên môi trường thử nghiệm bằng công cụ LDAP client hỗ trợ RFC 2696; ví dụ với `ldapsearch` của OpenLDAP (cú pháp và tùy chọn có thể thay đổi theo bản cài đặt):

~~~bash
ldapsearch -H ldaps://ldap.example.org \
  -D "cn=reader,dc=example,dc=org" -W \
  -b "ou=people,dc=example,dc=org" \
  -s one -E pr=100/noprompt \
  "(objectClass=inetOrgPerson)" uid cn
~~~

Lệnh yêu cầu nhiều trang kích thước 100 và chỉ dùng trong môi trường mà bạn được phép truy cập. Tùy hệ thống, có thể cần cấu hình TLS trust và giới hạn của LDAP server. Không đưa mật khẩu trực tiếp vào lịch sử shell; tùy chọn `-W` nhắc nhập tương tác.

## 10. Kiểm thử tích hợp với dữ liệu có kiểm soát

Nên kiểm thử trên máy chủ LDAP riêng (hoặc instance nhúng phù hợp với chức năng paged results). Một mock `LdapTemplate` không chứng minh server thực sự phát cookie và xử lý đúng các trang.

Tạo OU `ou=people` và một số entry `inetOrgPerson` có `uid` duy nhất. Sau đó chạy các ca:

| Ca thử | Thiết lập | Kỳ vọng |
| --- | --- | --- |
| Không có kết quả | Filter hợp lệ nhưng không entry khớp | Nhận 0 entry, kết thúc đúng |
| Ít hơn page size | 2 entry, page size 5 | Nhận đủ 2 entry, dừng |
| Bằng page size | 5 entry, page size 5 | Không suy luận điều kiện dừng từ size; theo cookie |
| Vượt page size | 8 entry, page size 3 | Thu thập đủ 8 UID không trùng theo tập |
| Nhiều trang | 235 entry, page size 100 | Sau chuỗi trang nhận đủ 235 UID khi dữ liệu đứng yên |
| Filter hẹp hơn | Chỉ một phần entry khớp filter | Chỉ nhận entry thuộc tập khớp |
| Scope khác nhau | Có OU con dưới `ou=people` | `ONELEVEL_SCOPE` và `SUBTREE_SCOPE` có kết quả đúng |
| Thuộc tính trả về | Chỉ yêu cầu `uid` | Mapper không dựa vào `mail` bị loại khỏi response |
| Control không được hỗ trợ | Dùng server không có paged results | Lỗi/cơ chế không hỗ trợ được nhận diện, không âm thầm coi là đầy đủ |
| Dừng/timeout giữa các trang | Mô phỏng lỗi sau trang đầu | Không báo đồng bộ hoàn tất; có kế hoạch chạy lại hoặc tiếp tục hợp lệ |
| Dữ liệu thay đổi đồng thời | Đổi/move một entry trong khi duyệt | Ứng dụng không giả định snapshot và xử lý được lặp/thiếu |

Khi xác minh, nên so sánh **tập UID thực tế** với tập UID đã khởi tạo và đếm các lần gặp mỗi UID. Không nên dựa vào thứ tự trả về nếu chưa yêu cầu sort từ server.

### Bài tập tự thực hành

1. Tạo 12 entry test dưới `ou=people`. Dùng page size 5 và ghi nhận số lần gọi search đến khi `hasMore()` là `false`.
2. Chuyển `SearchControls.ONELEVEL_SCOPE` sang `SUBTREE_SCOPE`. Khi nào kết quả khác nhau?
3. Đổi filter thành `(&(objectClass=inetOrgPerson)(mail=*))`. Nếu email là đầu vào động, bạn sẽ tạo và escape LDAP filter an toàn như thế nào (gợi ý: dùng `AndFilter`, `EqualsFilter` hoặc `PresentFilter` của Spring LDAP)?
4. Cố tình tạo lại processor bên trong vòng lặp. Hãy giải thích vì sao ứng dụng có thể đọc lặp trang đầu và cách phòng tránh.
5. Giả sử server chỉ trả 40 kết quả trên một trang size 100 nhưng trả cookie khác rỗng. Client có nên dừng không?
6. Nếu bị lỗi mạng sau trang thứ hai, làm sao thiết kế việc retry để tránh mất hoặc nhân đôi kết quả đồng bộ?

## 11. Ghi nhớ

**Simple Paged Results Control** là cơ chế phân trang bằng cookie ở cấp giao thức LDAP. Trong Spring LDAP, cấu hình `PagedResultsDirContextProcessor` cho một lần tìm kiếm logic và truyền cùng processor vào `LdapTemplate.search(...)` ở mỗi vòng cho đến khi `hasMore()` trả `false`. Chú ý giữ nguyên filter, base DN, scope và các control liên quan; phân biệt page size với giới hạn số entry và xử lý kết quả theo batch.

Phân trang giúp quản lý tải và truy xuất tập dữ liệu lớn, nhưng **không tự tạo thứ tự sắp xếp, snapshot nhất quán, offset để nhảy trang hoặc bảo đảm cookie còn hiệu lực vô thời hạn**. Khi triển khai thực tế, cần kiểm tra khả năng server, phân quyền đọc, giới hạn tài nguyên, kết nối TLS và cơ chế đồng bộ có thể chạy lại an toàn.

## Tài liệu tham khảo

- [RFC 2696 — LDAP Control Extension for Simple Paged Results Manipulation](https://www.rfc-editor.org/rfc/rfc2696): giao thức phân trang, cookie, size và cách kết thúc/hủy.
- [RFC 4511 — Lightweight Directory Access Protocol](https://www.rfc-editor.org/rfc/rfc4511): LDAP Search, controls và kết quả trả về.
- [Spring LDAP — Reference Documentation](https://docs.spring.io/spring-ldap/reference/): hướng dẫn tìm kiếm, xử lý request/response và quản lý context.
- [Spring LDAP — PagedResultsDirContextProcessor API](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/control/PagedResultsDirContextProcessor.html): processor và trạng thái cookie.
- [Spring LDAP — LdapTemplate API](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/core/LdapTemplate.html): các overload `search(...)` hỗ trợ `DirContextProcessor`.
