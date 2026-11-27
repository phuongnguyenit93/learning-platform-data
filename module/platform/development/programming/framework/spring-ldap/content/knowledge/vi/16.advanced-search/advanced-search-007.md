# Count limit, time limit và size limit trong tìm kiếm Spring LDAP

Một ứng dụng **Spring LDAP** có thể tìm được hàng chục nghìn entry khi truy vấn một cây thư mục lớn. Nếu không đặt giới hạn hợp lý, một lần tìm kiếm rộng có thể tiêu tốn bộ nhớ, băng thông và thời gian xử lý; ngược lại, giới hạn quá nhỏ có thể khiến ứng dụng hiểu nhầm rằng dữ liệu chỉ có vài kết quả.

Trong chương **Search nâng cao**, ba khái niệm cần nắm vững là **count limit**, **time limit** và **size limit**. Chúng liên quan với nhau nhưng không đồng nghĩa. Bài học giải thích đơn vị đo, cách cấu hình trong `LdapQueryBuilder` và JNDI `SearchControls`, giới hạn do LDAP server áp đặt, cách nhận diện kết quả không đầy đủ và hướng xử lý khi cần tìm đủ dữ liệu.

## 1. Ba giới hạn khác nhau ở điểm nào?

Giả sử hệ thống quản lý nhân viên có 30.000 entry dưới `ou=people,dc=example,dc=org`. Người dùng yêu cầu liệt kê các tài khoản với filter `(objectClass=inetOrgPerson)`.

| Giới hạn | Ai yêu cầu hoặc áp đặt? | Đo lường điều gì? | Cấu hình thường gặp |
| --- | --- | --- | --- |
| **Count limit** | Ứng dụng Java khi tạo truy vấn | Số **entry** tối đa muốn nhận từ tìm kiếm | `LdapQueryBuilder.countLimit(100)`; JNDI `SearchControls.setCountLimit(100)` |
| **Time limit** | Ứng dụng Java khi tạo truy vấn; server cũng có giới hạn riêng | Thời gian tối đa dành cho thao tác tìm kiếm | `LdapQueryBuilder.timeLimit(3000)`; JNDI `SearchControls.setTimeLimit(3000)` |
| **Size limit** | Thuật ngữ của LDAP protocol và chính sách server | Số **entry kết quả** tối đa được phép trả về | Trường `SearchRequest.sizeLimit` của LDAP, hoặc giới hạn tối đa do quản trị server áp đặt |

`countLimit` trong Spring LDAP/JNDI là cách ứng dụng yêu cầu giới hạn số kết quả. Với LDAP, yêu cầu đó thường được chuyển thành giới hạn `sizeLimit` của `SearchRequest`; server có thể áp dụng giới hạn riêng thấp hơn. Vì thế, đừng coi `count limit` và `size limit` là hai bộ lọc số lượng độc lập luôn được áp dụng cộng dồn.

Cả hai đều giới hạn **số entry**, không phải số thuộc tính, byte tải về, số trang hay tổng số entry thực sự khớp filter. Nếu truy vấn nhận được 50 entry, điều đó **không chứng minh** server chỉ có 50 entry khớp.

### Hai lớp giới hạn

```text
Ứng dụng Spring LDAP
  └─ LdapQueryBuilder / SearchControls
       ├─ countLimit = 100 entry
       └─ timeLimit  = 3000 ms
            │
            ▼
       JNDI LDAP provider
            │  chuyển thành tham số LDAP theo cơ chế provider
            ▼
       LDAP server
       ├─ nhận giới hạn được client yêu cầu
       ├─ áp dụng quota/chính sách server (size/time) nếu có
       └─ trả entry và mã kết quả của phép tìm kiếm
```

Nếu ứng dụng yêu cầu tối đa 500 entry nhưng server chỉ cho phép trả 200 entry trong một lần tìm kiếm, không được giả định chỉnh `countLimit(1000)` sẽ lấy được 500 entry. Cần xem chính sách máy chủ, phạm vi truy vấn và khả năng dùng **paged results**.

## 2. Count limit: khống chế số entry trả về

`countLimit(n)` cho phép ứng dụng đặt số entry tối đa mong muốn cho **một truy vấn**. Trong Spring LDAP:

- `.countLimit(100)`: yêu cầu tối đa 100 entry.
- `.countLimit(1)`: thích hợp khi nghiệp vụ chỉ cần một kết quả đầu tiên, nhưng **không đủ để chứng minh tính duy nhất** vì có thể có kết quả khác.
- `.countLimit(0)`: không đặt giới hạn số lượng từ phía client; **không xóa giới hạn của server**.
- Nếu không gọi `countLimit(...)` trong query builder, Spring LDAP sử dụng giá trị mặc định của `LdapTemplate`.

Một yêu cầu nhận tối đa 100 entry **không tự động tìm ra 100 entry đầu tiên theo thứ tự ổn định**. LDAP search thông thường không bảo đảm thứ tự kết quả; muốn thứ tự cụ thể cần cơ chế sắp xếp phù hợp và được server hỗ trợ.

### Ví dụ với `LdapQueryBuilder`

Giả sử `ContextSource` đã có base DN `dc=example,dc=org`. Trong service đã được inject `LdapTemplate`:

```java
import java.util.List;
import javax.naming.directory.Attribute;

import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;
import org.springframework.ldap.query.SearchScope;

public class PeopleSearchService {
    private final LdapTemplate ldapTemplate;

    public PeopleSearchService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<String> findSomeDisplayNames() {
        LdapQuery query = LdapQueryBuilder.query()
                .base("ou=people")
                .searchScope(SearchScope.SUBTREE)
                .attributes("cn")
                .countLimit(100)
                .timeLimit(3_000)
                .where("objectClass").is("inetOrgPerson");

        AttributesMapper<String> mapper = attrs -> {
            Attribute cn = attrs.get("cn");
            return cn == null ? "(không có cn)" : cn.get().toString();
        };

        return ldapTemplate.search(query, mapper);
    }
}
```

Trong ví dụ:

1. `base("ou=people")` là DN tìm kiếm **tương đối với base** đã cấu hình; không thêm `dc=example,dc=org` lần nữa.
2. `SearchScope.SUBTREE` duyệt các entry thuộc cây con của `ou=people`.
3. `attributes("cn")` chỉ yêu cầu thuộc tính cần dùng; đây là cách giảm dữ liệu nhận về, **khác** với giảm số entry qua `countLimit`.
4. `countLimit(100)` đặt mức tối đa cho kết quả; `timeLimit(3_000)` yêu cầu 3.000 mili giây.
5. `where("objectClass").is("inetOrgPerson")` tạo filter có cấu trúc. Khi có đầu vào người dùng, ưu tiên query builder hoặc bộ lọc có escape đúng cách thay vì nối chuỗi LDAP filter thủ công.

Nếu nhận đúng 100 phần tử, chưa thể kết luận đã đọc hết: có thể còn nhiều kết quả bị giới hạn. Nếu nhận ít hơn 100, vẫn phải lưu ý chính sách server hoặc lỗi đã bị bỏ qua.

## 3. Time limit: giới hạn thời gian tìm kiếm

Với `LdapQueryBuilder.timeLimit(int)` và `SearchControls.setTimeLimit(int)`, giá trị trong ứng dụng Java được diễn giải theo **mili giây (ms)**.

| Giá trị Java | Ý nghĩa dự kiến |
| --- | --- |
| `timeLimit(500)` | Khoảng 0,5 giây |
| `timeLimit(3_000)` | Khoảng 3 giây |
| `timeLimit(10_000)` | Khoảng 10 giây |
| `timeLimit(0)` | Không yêu cầu giới hạn thời gian tìm kiếm từ phía client |

**Phân biệt đơn vị:** `SearchRequest.timeLimit` trong LDAP protocol được định nghĩa bằng **giây**, trong khi giao diện Java `SearchControls` dùng **mili giây**. LDAP provider thực hiện chuyển đổi và áp dụng giới hạn theo khả năng hỗ trợ, vì vậy đừng giả định cấu hình 500 ms sẽ luôn được thực thi chính xác đến mili giây tại server. Quản trị server cũng có thể đặt trần thời gian riêng.

Ví dụ: ứng dụng yêu cầu 8 giây nhưng chính sách server chỉ cho mỗi tìm kiếm tối đa 2 giây. Truy vấn quá chậm vẫn có thể bị dừng theo quy tắc của server.

Khi vượt giới hạn, JNDI có thể phát sinh `javax.naming.TimeLimitExceededException` và Spring LDAP chuyển thành `org.springframework.ldap.TimeLimitExceededException`. Ở mức LDAP protocol, kết quả `timeLimitExceeded` có mã **3**.

### Time limit không thay thế các timeout mạng

Một lệnh tìm kiếm còn liên quan đến thời gian thiết lập kết nối, độ trễ mạng, thời gian nhận dữ liệu và xử lý kết quả ở ứng dụng. `timeLimit` của search **không phải** cơ chế bảo đảm mọi request HTTP của ứng dụng chắc chắn hoàn tất trong đúng số mili giây đã khai báo.

Tùy LDAP provider và kiến trúc triển khai, cần xem xét thêm:

- **Connect timeout:** giới hạn thời gian thiết lập kết nối tới LDAP server.
- **Read/socket timeout:** giới hạn thời gian chờ dữ liệu từ kết nối; là cấu hình khác với search time limit.
- **Timeout nghiệp vụ tại API/gateway:** kiểm soát thời gian phản hồi tổng thể cho người dùng.

Không tăng `timeLimit` thật lớn để che một filter quá rộng hoặc index chưa phù hợp; trước tiên hãy thu hẹp base, search scope và điều kiện tìm kiếm.

## 4. Size limit: chính sách máy chủ và mã lỗi

LDAP SearchRequest có trường `sizeLimit` xác định số entry tối đa mà **client yêu cầu**. Theo RFC 4511, `sizeLimit = 0` có nghĩa không yêu cầu giới hạn số lượng từ phía client. Tuy nhiên **LDAP server vẫn có thể áp đặt hạn mức riêng**, thường cấu hình theo directory, tài khoản bind, loại truy vấn hoặc quyền quản trị.

Ví dụ giả định:

```text
countLimit của ứng dụng: 2.000
quota của máy chủ:         500 entry mỗi search
số entry khớp filter:     3.500

=> Không thể nhận đủ 3.500 entry bằng một search không phân trang.
   Server có thể trả tối đa 500 entry rồi báo giới hạn vượt mức.
```

Khi không thể trả toàn bộ kết quả vì giới hạn kích thước, server có thể trả LDAP result code **4**, tên `sizeLimitExceeded`. Ở Java, JNDI có `javax.naming.SizeLimitExceededException` và Spring LDAP có `org.springframework.ldap.SizeLimitExceededException`.

Lưu ý mã **4** khác mã **3** (`timeLimitExceeded`). Không gộp hai loại lỗi thành một thông báo “không có dữ liệu”.

Các giới hạn của server còn ảnh hưởng đến các truy vấn có `countLimit(0)`. Đặt `0` không làm truy vấn trở nên “vô hạn” trên thực tế và có thể khiến ứng dụng tải lượng dữ liệu không mong muốn.

## 5. Điều khiển trực tiếp bằng JNDI `SearchControls`

Khi cần cấu hình theo API JNDI, Spring LDAP cung cấp overload `LdapTemplate.search(..., SearchControls, AttributesMapper)`:

```java
import java.util.List;
import javax.naming.directory.Attribute;
import javax.naming.directory.SearchControls;

import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;

public class SearchControlsExample {
    private final LdapTemplate ldapTemplate;

    public SearchControlsExample(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<String> searchNames() {
        SearchControls controls = new SearchControls();
        controls.setSearchScope(SearchControls.SUBTREE_SCOPE);
        controls.setCountLimit(50L);
        controls.setTimeLimit(2_000); // 2000 ms = 2 s
        controls.setReturningAttributes(new String[] {"cn"});

        AttributesMapper<String> mapper = attrs -> {
            Attribute cn = attrs.get("cn");
            return cn == null ? "(không có cn)" : cn.get().toString();
        };

        return ldapTemplate.search(
                "ou=people",
                "(objectClass=inetOrgPerson)",
                controls,
                mapper);
    }
}
```

Trong `SearchControls`, `setCountLimit(long)` nhận kiểu `long`; `setTimeLimit(int)` nhận kiểu `int`. Cả hai đều chấp nhận `0` để biểu diễn “không đặt giới hạn” ở lớp client. Ví dụ này dùng filter cố định; nếu filter chứa input người dùng, hãy tạo biểu thức bằng builder có escape hoặc cơ chế tham số hóa tương ứng.

Hai cách cấu hình `LdapQueryBuilder` và `SearchControls` cùng phục vụ một mục đích. Chọn cách phù hợp với API hiện có của service, không cần tạo hai search riêng chỉ để áp cùng một giới hạn.

## 6. Cấu hình mặc định tại `LdapTemplate`

Nếu nhiều search trong ứng dụng có chung giới hạn, có thể đặt mặc định khi khởi tạo bean:

```java
LdapTemplate ldapTemplate = new LdapTemplate(contextSource);
ldapTemplate.setDefaultCountLimit(200);
ldapTemplate.setDefaultTimeLimit(5_000); // mili giây
```

Ở đây `contextSource` là bean đã cấu hình; đoạn mã minh họa phần thiết lập trong cấu hình ứng dụng. Hai tham số mặc định có giá trị `0` nếu không thiết lập. Trong query có `.countLimit(...)` hoặc `.timeLimit(...)` riêng, giá trị của query được ưu tiên cho search tương ứng.

Với Spring XML namespace, `ldap-template` cũng hỗ trợ các thuộc tính `count-limit` và `time-limit`. Tuy nhiên, việc đặt default chỉ giới hạn các request đi qua template đó; nó **không thay đổi quota ở máy chủ**.

**Thực hành cấu hình:** Chọn giá trị mặc định theo nhu cầu thật của hệ thống, đồng thời đặt giới hạn riêng cho các màn hình có đặc điểm khác nhau (ví dụ autocomplete nhỏ và báo cáo lớn). Tránh thay đổi cấu hình chung của một bean đang được nhiều luồng sử dụng ngay trong lúc xử lý từng request.

## 7. Kết quả bị cắt ngắn và ngoại lệ bị bỏ qua

Một chi tiết dễ gây lỗi nghiệp vụ: `LdapTemplate` có phương thức `setIgnoreSizeLimitExceededException(boolean)` và **mặc định là `true`** theo Javadoc Spring LDAP. Điều đó hữu ích khi ứng dụng chủ động đặt count limit và chỉ cần một tập kết quả nhỏ. Nhưng nếu đang xây báo cáo cần **đủ tất cả entry**, việc bỏ qua ngoại lệ có thể khiến ứng dụng nhận danh sách không đầy đủ mà không phát hiện ngay.

Đối với luồng mà tính đầy đủ là bắt buộc, hãy cân nhắc một `LdapTemplate` được cấu hình rõ chính sách:

```java
// Thực hiện khi khởi tạo bean/template dành cho nghiệp vụ cần kết quả đầy đủ.
ldapTemplate.setIgnoreSizeLimitExceededException(false);
```

Và xử lý hai tình huống giới hạn riêng biệt:

```java
import org.springframework.ldap.SizeLimitExceededException;
import org.springframework.ldap.TimeLimitExceededException;

// query và mapper đã được tạo như ở ví dụ trên.
try {
    List<String> names = ldapTemplate.search(query, mapper);
    // Chỉ diễn giải đầy đủ khi toàn bộ điều kiện giới hạn/phan trang
    // và hành vi máy chủ đã được đánh giá phù hợp.
    useNames(names);
} catch (SizeLimitExceededException ex) {
    // Dữ liệu không đầy đủ: không xuất báo cáo như kết quả toàn bộ.
    reportIncompleteSearch("Quá giới hạn số entry", ex);
} catch (TimeLimitExceededException ex) {
    reportIncompleteSearch("Vượt thời gian tìm kiếm", ex);
}
```

Hai hàm `useNames` và `reportIncompleteSearch` ở đây là **pseudocode nghiệp vụ**, cần hiện thực trong ứng dụng. Nếu muốn ví dụ chạy độc lập, thay chúng bằng cách trả kết quả hoặc ném exception phù hợp.

Một số lưu ý quan trọng:

- Khi `setIgnoreSizeLimitExceededException(true)`, không thể dựa vào việc “không có exception” để chứng minh đã lấy hết kết quả. Bắt exception trong `catch` cũng không có tác dụng nếu template đã bỏ qua exception từ trước.
- Khi `setIgnoreSizeLimitExceededException(false)`, ngoại lệ giúp biết kết quả không hoàn chỉnh; tùy overload, danh sách đang được mapper xử lý trước đó không nhất thiết được trả lại cho caller.
- `org.springframework.ldap.PartialResultException` thường liên quan tới **referral** (chuyển hướng LDAP), không đồng nghĩa với `SizeLimitExceededException`. Cấu hình `setIgnorePartialResultException` là một tùy chọn khác và không sửa được vấn đề vượt size limit.
- Một list có kích thước **bằng đúng count limit** vẫn có thể là kết quả đầy đủ hoặc kết quả đã bị cắt; riêng số lượng không chứng minh được trường hợp nào.

### Khi nào coi dữ liệu là đầy đủ?

| Tín hiệu | Có thể kết luận gì? |
| --- | --- |
| Nhận đúng 100 entry với `countLimit(100)` | Đã nhận tới giới hạn yêu cầu; **chưa biết** còn entry khác hay không. |
| Nhận 80 entry với `countLimit(100)` | Có thể là 80 entry khớp, nhưng vẫn cần xem giới hạn phía server và lỗi bị bỏ qua. |
| Nhận `SizeLimitExceededException` | Truy vấn bị giới hạn số lượng; không coi kết quả là đầy đủ. |
| Nhận `TimeLimitExceededException` | Tìm kiếm không hoàn thành trong giới hạn thời gian; không coi kết quả là đầy đủ. |
| Search phân trang trả cookie kết thúc theo đúng giao thức | Có thể đã đọc hết chuỗi trang **của truy vấn đó**, nhưng vẫn cần xét thay đổi đồng thời và tính nhất quán của directory. |

## 8. Muốn lấy nhiều entry hơn giới hạn thì làm gì?

Không nên chỉ tăng `countLimit` và `timeLimit` liên tục. Hướng xử lý phù hợp tùy nghiệp vụ:

1. **Thu hẹp search base**: thay vì quét toàn `dc=example,dc=org`, truy vấn dưới `ou=people` hoặc một đơn vị tổ chức cụ thể.
2. **Chọn search scope**: `OBJECT`, `ONELEVEL` hoặc `SUBTREE` theo nhu cầu; phạm vi càng rộng thì số entry tiềm năng càng lớn.
3. **Làm rõ filter**: tìm theo `uid`, `employeeNumber` hoặc thuộc tính có index phù hợp, thay vì filter quá chung.
4. **Chỉ yêu cầu thuộc tính cần thiết**: ví dụ `uid` và `cn`, tránh tải thuộc tính nhị phân lớn khi chỉ hiển thị danh sách.
5. **Sử dụng LDAP paged results** nếu cần đọc nhiều entry, server hỗ trợ và quyền truy cập cho phép. Với Spring LDAP, có cơ chế xử lý Simple Paged Results thông qua `PagedResultsDirContextProcessor`; phải lặp theo cookie trang tới khi kết thúc và xử lý lỗi ở từng trang.
6. **Thiết kế phản hồi rõ ràng**: với màn hình gợi ý, 20–50 bản ghi có thể đủ; với báo cáo kiểm toán hoặc đồng bộ người dùng, cần biết kết quả có đầy đủ hay không.

**Phân trang không đồng nghĩa với `countLimit`.** Ví dụ đặt `countLimit(100)` chỉ yêu cầu trả tối đa 100 entry từ một truy vấn; không tạo ra cookie để lấy trang 2. LDAP Simple Paged Results là một control riêng (RFC 2696) và cần server hỗ trợ. Đừng tự giả định số trang hay tổng số kết quả chỉ từ độ dài list trả về.

## 9. Bài thực hành kiểm tra giới hạn

Chuẩn bị một LDAP server thử nghiệm có ít nhất 12 entry loại `inetOrgPerson` dưới `ou=people,dc=example,dc=org`. Thiết lập `ContextSource` với base `dc=example,dc=org` và tài khoản có quyền đọc. Đảm bảo đường kết nối LDAP của môi trường dùng TLS khi cần.

| Bài thử | Cấu hình | Điều cần quan sát |
| --- | --- | --- |
| A | `countLimit(5)`, `timeLimit(5_000)` | Danh sách nhận không vượt 5 entry; không xem nó là toàn bộ 12 entry. |
| B | `countLimit(0)`, `timeLimit(5_000)` | Nếu server cho phép, có thể nhận đủ 12 entry; quota phía server vẫn có hiệu lực. |
| C | `countLimit(5)`, `timeLimit(1)` | Có thể lỗi thời gian, hoặc hoàn thành rất nhanh tùy provider/server; không được coi đây là test tất định. |
| D | Thiết lập server size limit thấp hơn số entry khớp | Quan sát `sizeLimitExceeded` và so sánh kết quả khi bật/tắt ignore size-limit exception. |
| E | Dùng cơ chế paged results với page size 4 | Tiếp tục lấy cookie các trang đến khi hết, rồi so sánh tập entry nhận được với dữ liệu thử nghiệm. |

Nếu không thể điều chỉnh chính sách server, hãy coi D là tình huống cần môi trường kiểm thử riêng. Để kiểm tra giới hạn thời gian đáng tin cậy, sử dụng một bộ dữ liệu hoặc hạ tầng mô phỏng có độ trễ kiểm soát được; không trông chờ `timeLimit(1)` luôn gây lỗi.

### Câu hỏi tự đánh giá

1. `countLimit(100)` khác gì với `attributes("uid", "cn")`?
2. Tại sao `countLimit(0)` không bảo đảm nhận vô hạn entry?
3. Tại sao `timeLimit(2_000)` không có nghĩa request HTTP sẽ kết thúc chính xác sau 2 giây?
4. LDAP result code **3** và **4** lần lượt phản ánh điều gì?
5. Vì sao `setIgnoreSizeLimitExceededException(true)` có thể nguy hiểm đối với báo cáo kiểm toán?
6. Một kết quả dài đúng 100 entry với `countLimit(100)` có đủ cơ sở để ghi “tổng số người dùng là 100” không?
7. Khi nào nên chọn LDAP paged results thay vì tăng count limit?

## 10. Ghi nhớ

- **Count limit** đặt số entry tối đa ứng dụng muốn nhận; trong Spring LDAP dùng `LdapQueryBuilder.countLimit(...)` hoặc `SearchControls.setCountLimit(...)`.
- **Time limit** đặt giới hạn thời gian tìm kiếm; trong Java/Spring LDAP dùng **mili giây**, trong LDAP protocol tính bằng **giây**. Nó không thay thế hoàn toàn connect/read timeout.
- **Size limit** là giới hạn số entry ở mức LDAP search và chính sách directory; server có thể áp trần riêng dù client đặt `0`.
- Kết quả bị giới hạn hoặc vượt thời gian **không chứng minh** dữ liệu đã được truy xuất đầy đủ. Đặc biệt cần nhận thức mặc định `LdapTemplate` bỏ qua `SizeLimitExceededException`.
- Với dữ liệu lớn, hãy cải thiện base/filter/scope, giới hạn thuộc tính và sử dụng **paged results** đúng giao thức khi cần đọc hết.

## Tài liệu tham khảo

- [Spring LDAP Reference — Advanced LDAP Queries](https://docs.spring.io/spring-ldap/reference/query-builder-advanced.html)
- [Spring LDAP Javadoc — LdapQueryBuilder](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/query/LdapQueryBuilder.html)
- [Spring LDAP Javadoc — LdapTemplate](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/LdapTemplate.html)
- [Spring LDAP Reference — LdapTemplate Configuration](https://docs.spring.io/spring-ldap/reference/configuration.html)
- [Oracle Java JNDI — Result Count](https://docs.oracle.com/javase/tutorial/jndi/ops/countlimit.html)
- [Oracle Java JNDI — Time Limit](https://docs.oracle.com/javase/tutorial/jndi/ops/timelimit.html)
- [RFC 4511 — LDAP SearchRequest sizeLimit/timeLimit](https://www.rfc-editor.org/rfc/rfc4511#section-4.5.1)
- [RFC 2696 — LDAP Simple Paged Results](https://www.rfc-editor.org/rfc/rfc2696)
