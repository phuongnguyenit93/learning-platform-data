# Không bảo đảm thứ tự nếu server không hỗ trợ sort trong Spring LDAP

Khi xây dựng danh bạ nhân viên bằng Spring LDAP, một yêu cầu phổ biến là hiển thị người dùng **theo họ tên từ A đến Z**, mỗi lần chỉ lấy một trang. Điều dễ bỏ sót là: **kết quả của LDAP Search không có thứ tự được bảo đảm nếu server không thực hiện sắp xếp theo một cơ chế được xác nhận**.

Chẳng hạn, cùng một filter `(objectClass=inetOrgPerson)`, truy vấn hôm nay có thể trả `An, Chi, Binh`, nhưng lần khác trả `Binh, An, Chi`. Các nguyên nhân có thể là thứ tự duyệt index, cache, backend, replica, thay đổi dữ liệu hoặc kế hoạch truy vấn của server. Spring LDAP chỉ nhận và ánh xạ các entry mà LDAP trả về; bản thân `LdapTemplate.search(...)` **không tự áp đặt một thứ tự toàn cục**.

Bài học này giải thích vì sao thứ tự là một phần của **hợp đồng truy vấn**, cách sử dụng và xác nhận LDAP Server-Side Sorting (RFC 2891), hậu quả với phân trang và các giải pháp khi máy chủ không hỗ trợ tính năng đó.

## 1. Thứ tự ngẫu nhiên không phải lỗi của LdapTemplate

Giả sử một nhánh thư mục có các entry:

~~~ldif
dn: uid=an,ou=people,dc=example,dc=org
objectClass: inetOrgPerson
cn: An Nguyen
sn: Nguyen
uid: an

dn: uid=binh,ou=people,dc=example,dc=org
objectClass: inetOrgPerson
cn: Binh Tran
sn: Tran
uid: binh

dn: uid=chi,ou=people,dc=example,dc=org
objectClass: inetOrgPerson
cn: Chi Le
sn: Le
uid: chi
~~~

Một lời gọi:

~~~java
List<String> names = ldapTemplate.search(
    "ou=people",
    "(objectClass=inetOrgPerson)",
    (AttributesMapper<String>) attrs ->
        (String) attrs.get("cn").get()
);
~~~

có thể trả `["Binh Tran", "An Nguyen", "Chi Le"]`. Không có `Comparator` phía client hoặc sort control phía LDAP thì **không tồn tại lời hứa** rằng kết quả phải theo `cn`, `sn`, `uid`, DN hoặc thời gian tạo.

Vì vậy, không nên viết logic:

- “Entry đầu tiên chắc chắn là nhân viên có tên nhỏ nhất”.
- “Cứ gọi lại cùng search thì vị trí của từng người không đổi”.
- “Thứ tự của `List` mà `LdapTemplate` trả về là thứ tự alphabet”.
- “Page 2 đương nhiên tiếp nối page 1 theo `cn`”.

**Đừng đồng nhất thứ tự đang quan sát được với thứ tự được giao thức bảo đảm.** Một máy chủ có thể tình cờ trả thứ tự DN hoặc thứ tự index, nhưng đó không phải tiêu chí để ứng dụng cam kết giao diện ổn định.

## 2. LDAP Server-Side Sorting: yêu cầu và phản hồi

RFC 2891 định nghĩa một LDAP request control yêu cầu server sắp xếp kết quả `SearchResultEntry` **trước khi gửi trả**:

| Thành phần | OID | Vai trò |
| --- | --- | --- |
| Sort Request Control | `1.2.840.113556.1.4.473` | Yêu cầu sort theo danh sách khóa, ví dụ `sn` rồi `cn` |
| Sort Response Control | `1.2.840.113556.1.4.474` | Cho biết server đã thực hiện sort thành công hoặc vì sao không thể sort |
| Simple Paged Results Control | `1.2.840.113556.1.4.319` | Phân trang (RFC 2696); **không phải** sort control |

Sort key có thể chỉ định thuộc tính, ordering matching rule thích hợp và chiều đảo ngược. Nếu có nhiều sort key, server xét chúng theo độ ưu tiên từ trái sang phải, ví dụ `sn` trước, `cn` sau.

Một request sort **không tự chứng minh** kết quả đã được sắp xếp. Theo RFC 2891, client chỉ nên coi thứ tự được bảo đảm khi đã nhận **Sort Response Control** với kết quả `success`.

### 2.1. Tại sao criticality quan trọng?

LDAP control có cờ `criticality`:

| Tình huống | Kết quả theo RFC 2891 | Hệ quả cho ứng dụng |
| --- | --- | --- |
| Server **không hỗ trợ** sort; request **critical=true** | Server trả lỗi `unavailableCriticalExtension`, không trả entry của search đó | Ứng dụng biết rằng yêu cầu sắp xếp bắt buộc không được đáp ứng |
| Server **không hỗ trợ** sort; request **critical=false** | Server được yêu cầu bỏ qua sort control và thực hiện search như thường | Có thể trả entry **chưa sắp xếp** mà thao tác vẫn thành công |
| Server hỗ trợ control nhưng không sort được khóa đã chọn | Có thể báo lỗi sort trong response; với critical request có thể thất bại | Phải kiểm tra phản hồi và result code, không chỉ sự hiện diện của danh sách |
| Server sort thành công | Sort Response Control mang `success` | Có căn cứ dựa vào thứ tự do server thực hiện |
| Không có Sort Response Control | Không có bằng chứng server đã làm sort | Theo RFC 2891, nên xem như yêu cầu sort đã bị bỏ qua |

Ví dụ, một API cần trả `employees?sort=sn&page=2` **không nên** âm thầm trả dữ liệu không có thứ tự khi sort thất bại. Nếu thứ tự là điều kiện bắt buộc, nên báo “không hỗ trợ sắp xếp” hoặc chuyển sang phương án thay thế có giới hạn và đã được thiết kế.

## 3. Kiểm tra server có hỗ trợ sort hay không

LDAP root DSE (DN rỗng, scope `base`) thường công bố danh sách `supportedControl`. Có thể truy vấn trực tiếp bằng `ldapsearch` trên máy đã cài công cụ:

~~~bash
ldapsearch -LLL -x \
  -H ldaps://ldap.example.org:636 \
  -b "" -s base "(objectClass=*)" supportedControl
~~~

Tìm OID `1.2.840.113556.1.4.473` trong danh sách. Nếu có, server **công bố** hỗ trợ Sort Request Control, nhưng điều đó **chưa bảo đảm** mọi thuộc tính, mọi matching rule hay mọi kích thước truy vấn đều có thể sắp xếp thành công.

Nguyên nhân server có control nhưng không sort được có thể bao gồm:

1. **Thuộc tính không phù hợp:** `sn` hoặc sort key khác không có ordering matching rule mà server chấp nhận; máy chủ có thể trả `inappropriateMatching` hoặc `noSuchAttribute`.
2. **Giới hạn tài nguyên:** tập kết quả quá lớn, vượt bộ nhớ, giới hạn quản trị hoặc thời gian; server có thể trả mã lỗi tương ứng.
3. **Chính sách/ACL:** tài khoản có thể không đủ quyền đọc hoặc dùng sort key.
4. **Backend khác nhau:** endpoint, replica hoặc phân vùng dữ liệu khác nhau có tính năng/phiên bản không giống nhau.
5. **Chuỗi referral/chaining:** nếu search tổng hợp entry từ nhiều nguồn, server phải đáp ứng yêu cầu sắp xếp toàn bộ kết quả theo các điều kiện RFC 2891; không thể chỉ dựa vào thứ tự của từng nguồn.

Ngược lại, **không thấy OID** trong lần đọc root DSE không tự chứng minh chắc chắn server không hỗ trợ tính năng trong mọi cấu hình: quyền truy cập, cách công bố khả năng và chính sách máy chủ có thể khác nhau. Khi kết quả ảnh hưởng tới nghiệp vụ, hãy xác nhận bằng tài liệu của đúng phiên bản server và một yêu cầu thử với sort response được kiểm tra.

## 4. Ví dụ Spring LDAP: kiểm tra kết quả sắp xếp

Spring LDAP cung cấp cơ chế `DirContextProcessor` để thêm LDAP controls trước thao tác search và đọc response controls sau khi search hoàn tất. **Trong Spring LDAP 4.1 trở lên**, có thể dùng `SortControlExchange` cùng `ControlExchangeDirContextProcessor`; chúng thay thế cách tiếp cận `SortControlDirContextProcessor` đã bị deprecated ở các phiên bản mới.

Ví dụ sau giả định `LdapContextSource` đã cấu hình base DN `dc=example,dc=org`, kết nối LDAPv3 qua TLS, và server cho phép sort theo `sn`. Để dùng API `SortControlExchange`, ứng dụng cần đúng phiên bản Spring LDAP có lớp đó.

Các LDAP controls yêu cầu context hỗ trợ `LdapContext`, vì vậy cần cấu hình `LdapContextSource` phù hợp. Với một tìm kiếm trả **0 entry**, RFC 2891 cho phép server không gửi Sort Response Control. Ví dụ bên dưới chọn chính sách kiểm tra **nghiêm ngặt** và báo chưa xác nhận sort ngay cả trong trường hợp đó; ứng dụng có thể xử lý riêng danh sách rỗng mà vẫn không được suy ra server hỗ trợ sort.

~~~java
import java.util.List;
import javax.naming.NamingException;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;
import javax.naming.directory.SearchControls;
import javax.naming.ldap.SortControl;
import javax.naming.ldap.SortResponseControl;

import org.springframework.ldap.control.ControlExchangeDirContextProcessor;
import org.springframework.ldap.control.SortControlExchange;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.stereotype.Service;

@Service
public class SortedEmployeeSearch {

    public record Employee(String uid, String surname, String commonName) {}

    private final LdapTemplate ldapTemplate;

    public SortedEmployeeSearch(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<Employee> findBySurname() {
        SearchControls controls = new SearchControls();
        controls.setSearchScope(SearchControls.SUBTREE_SCOPE);
        controls.setReturningAttributes(new String[] {"uid", "sn", "cn"});

        // Tạo mới processor cho một lượt tìm kiếm.
        ControlExchangeDirContextProcessor<SortControl, SortResponseControl> sort =
            new ControlExchangeDirContextProcessor<>(
                new SortControlExchange("sn")
            );

        List<Employee> rows = ldapTemplate.search(
            "ou=people",
            "(objectClass=inetOrgPerson)",
            controls,
            (AttributesMapper<Employee>) attrs -> new Employee(
                text(attrs, "uid"),
                text(attrs, "sn"),
                text(attrs, "cn")
            ),
            sort
        );

        SortResponseControl response = sort.getExchange().getResponse();
        if (response == null || !response.isSorted()) {
            String detail = response == null
                ? "server không trả sort response"
                : "sort result code = " + response.getResultCode();
            throw new IllegalStateException(
                "Không thể bảo đảm thứ tự theo sn: " + detail
            );
        }
        return rows;
    }

    private static String text(Attributes attrs, String name)
            throws NamingException {
        Attribute attribute = attrs.get(name);
        return attribute == null ? null : (String) attribute.get();
    }
}
~~~

Điểm quan trọng là bước `sort.getExchange().getResponse()` và `response.isSorted()`. Nếu server không hỗ trợ critical sort hoặc từ chối yêu cầu, `ldapTemplate.search(...)` cũng **có thể ném ngoại lệ trước khi mã kiểm tra response được chạy**. Caller cần phân loại các lỗi đó như lỗi tìm kiếm/sắp xếp, không ép thành một danh sách “đã sắp xếp”.

Ví dụ cố ý dùng **một** khóa `sn`. Hai entry cùng họ `Nguyen` vẫn có thể đổi vị trí tương đối. Nếu yêu cầu nghiệp vụ đòi hỏi thứ tự ổn định giữa các giá trị bằng nhau, cần thêm **khóa phụ mang tính duy nhất** mà server cho phép sắp xếp, chẳng hạn `uid` khi schema và chính sách bảo đảm tính duy nhất trong phạm vi tìm kiếm. RFC 2891 hỗ trợ nhiều khóa; khả năng áp dụng từng khóa phải được thử trên server.

Với Spring LDAP 3.x, có thể gặp ví dụ cũ dùng:

~~~java
SortControlDirContextProcessor sort =
    new SortControlDirContextProcessor("sn");

// Sau lượt search có gắn processor:
boolean serverSorted = sort.isSorted();
int resultCode = sort.getResultCode();
~~~

Đây là cách dùng theo API của các phiên bản cũ; không ghép nguyên snippet với API 4.1+ mà chưa kiểm tra dependency. Dù dùng phiên bản nào, **phải kiểm tra kết quả sort thực tế**, không đánh dấu thành công chỉ vì đã tạo request control.

## 5. Tại sao phân trang làm vấn đề trở nên nghiêm trọng hơn?

**Simple Paged Results** (RFC 2696) chia tập kết quả thành các trang bằng một cookie do server phát hành. Nó giúp không cần tải quá nhiều entry trong một lần phản hồi, nhưng **không cung cấp tiêu chí sắp xếp**.

Ví dụ server trả bốn tên theo thứ tự không xác định, page size = 2:

~~~text
Page 1 nhận từ LDAP: [Zoey, An]
Page 2 nhận từ LDAP: [Binh, Mai]
~~~

Nếu client chỉ sort **từng trang riêng lẻ**, ta được:

~~~text
Page 1 sau sort: [An, Zoey]
Page 2 sau sort: [Binh, Mai]
Ghép hai trang: [An, Zoey, Binh, Mai]  <-- vẫn sai thứ tự toàn cục
~~~

Sắp xếp toàn bộ bốn bản ghi mới cho kết quả `[An, Binh, Mai, Zoey]`. Vì vậy, **sort sau khi đã chia trang không tạo ra các trang của một danh sách sắp xếp toàn cục**.

### 5.1. Khi server hỗ trợ cả sort và paging

RFC 2891 quy định khi kết hợp Sort Request Control với Paged Results Control, server nên sắp xếp **toàn bộ tập khớp** trước khi chia trang, thay vì sắp xếp riêng từng trang. Khi gửi trang tiếp theo, client phải giữ **cùng danh sách sort key**, cùng search base, filter, scope và các tham số truy vấn liên quan. Cookie phân trang là dữ liệu opaque; không được tự sửa hoặc tái dùng cho truy vấn khác.

Trong Spring LDAP, xử lý paged results thường dùng `PagedResultsControlExchangeDirContextProcessor` và có thể cần `SingleContextSource` để **giữ cùng underlying connection** suốt các yêu cầu trang. Việc đồng thời gắn paging và sort controls phải được thử với phiên bản Spring LDAP và backend đang sử dụng; không giả định mọi server hỗ trợ kết hợp hai controls.

### 5.2. Ngay cả khi đã sort, dữ liệu thay đổi vẫn làm trang dịch chuyển

Sort tạo tiêu chí thứ tự, nhưng không mặc nhiên tạo **snapshot isolation** cho nhiều lượt search:

~~~text
T0: [An, Binh, Chi, Dung], size = 2
Page 1 = [An, Binh]
T1: một entry "Bao" được thêm vào giữa hai lượt đọc
Page 2 có thể khác kỳ vọng, tùy server và cơ chế paging
~~~

Khi đồng bộ dữ liệu lớn, cần xem tài liệu server về tính nhất quán của cookie, chính sách thay đổi đồng thời và ranh giới phiên. **Đừng dùng vị trí trang làm danh tính của entry**. Dùng định danh ổn định phù hợp để xử lý trùng/lệch hoặc tái đồng bộ khi cần.

## 6. Fallback: sort phía client khi server không hỗ trợ

Nếu bắt buộc hiển thị A–Z nhưng server không hỗ trợ sort, có thể **lấy toàn bộ tập dữ liệu thuộc phạm vi nghiệp vụ, xác nhận truy vấn đã hoàn tất, rồi sort phía Java trước khi cắt trang**. Cách này hợp lý khi tập dữ liệu **nhỏ và có giới hạn rõ ràng**.

Ví dụ sau sử dụng `Collator` để so sánh họ theo quy tắc ngôn ngữ tiếng Việt ở phía Java, sau đó dùng `uid` làm khóa phụ. Giả định mỗi entry có `sn` và `uid` dạng chuỗi, và `uid` là duy nhất trong nhánh nghiệp vụ này.

~~~java
import java.text.Collator;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import javax.naming.directory.Attributes;

import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;

public class LocalSortedPeople {

    public record Person(String uid, String surname) {}

    private final LdapTemplate ldapTemplate;

    public LocalSortedPeople(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<Person> loadAndSortAll() {
        // Chỉ dùng cho tập có giới hạn và sau khi kiểm soát lỗi size/time limit.
        List<Person> rows = new ArrayList<>(ldapTemplate.search(
            "ou=people",
            "(objectClass=inetOrgPerson)",
            (AttributesMapper<Person>) attrs -> new Person(
                (String) attrs.get("uid").get(),
                (String) attrs.get("sn").get()
            )
        ));

        Collator vi = Collator.getInstance(Locale.forLanguageTag("vi-VN"));
        Comparator<Person> byNameThenUid =
            Comparator.comparing(Person::surname, vi)
                      .thenComparing(Person::uid);
        rows.sort(byNameThenUid);
        return List.copyOf(rows);
    }

    public List<Person> onePage(List<Person> sorted, int offset, int size) {
        if (offset < 0 || size <= 0 || offset > sorted.size()) {
            throw new IllegalArgumentException("offset hoặc size không hợp lệ");
        }
        int end = (int) Math.min((long) sorted.size(), (long) offset + size);
        return sorted.subList(offset, end);
    }
}
~~~

**Phạm vi áp dụng và giới hạn:**

- `loadAndSortAll()` chỉ phù hợp nếu hệ thống **thực sự lấy đủ các entry**. Cần phát hiện lỗi `SizeLimitExceededException`, `TimeLimitExceededException`, referral/partial result và giới hạn phía server; `List` trả về không tự chứng minh đã đủ.
- Dùng `ldapTemplate.setIgnoreSizeLimitExceededException(false)` trên bean được kiểm soát nếu không muốn nuốt lỗi giới hạn số lượng. Không tắt các hạn chế phía server chỉ để phục vụ sắp xếp.
- `Collator` phụ thuộc locale và cấu hình; kết quả sort Java có thể **không giống** matching rule/ordering rule của LDAP server khác.
- Nếu `sn` hoặc `uid` thiếu, code trên cần bổ sung chính sách xử lý null trước khi sử dụng thực tế. Mẫu `inetOrgPerson` thường có `sn` bắt buộc, nhưng `uid` và quyền đọc vẫn tùy entry/schema/ACL.
- Không dùng chiến lược này cho hàng triệu entry hoặc cho giao diện phân trang tùy ý với từng request đều tải lại toàn bộ LDAP. Khi tập dữ liệu lớn, cân nhắc hệ thống tìm kiếm/index riêng hoặc thay đổi yêu cầu sản phẩm theo khả năng server.

Nếu mỗi lần gọi trang đều **tải lại toàn bộ tập và sort lại**, cập nhật đồng thời vẫn có thể khiến vị trí trang thay đổi. Có thể cần cache/snapshot ứng dụng với thời hạn và kiểm soát nhất quán rõ ràng, thay vì hứa “page 2 luôn nối tiếp page 1” trên một dữ liệu liên tục biến động.

## 7. Chọn hành vi đúng cho API và giao diện

Một hệ thống thực tế nên công bố **khả năng sort** và kết quả xác nhận sort một cách minh bạch:

| Nhu cầu | Cách xử lý được đề xuất | Điều cần tránh |
| --- | --- | --- |
| Danh sách nhỏ, chỉ cần A–Z | Tải đủ tập, sort Java, rồi phân trang ở ứng dụng | Sort riêng từng trang LDAP |
| Danh sách lớn, paging thật sự, server hỗ trợ RFC 2891 | Gửi server-side sort control, kiểm tra sort response; kết hợp paging nếu server hỗ trợ | Coi request gửi thành công là sort thành công |
| Server không hỗ trợ sort, dữ liệu lớn | Trả lỗi/giới hạn tùy năng lực sản phẩm, hoặc dùng index/search service riêng | Trả API `sorted=true` khi dữ liệu chưa sort |
| Có nhiều replica hoặc source | Chọn endpoint nhất quán; định nghĩa cách gộp và sort toàn bộ nguồn | Tin rằng từng nguồn đã sort sẽ tự tạo thứ tự toàn cục |
| Sort theo thuộc tính nhiều giá trị hoặc thiếu giá trị | Đối chiếu RFC 2891 và matching rule, thử thực tế, thiết lập khóa phụ | Giả định mọi entry có đúng một giá trị sort key |

Với các thuộc tính đa trị, RFC 2891 khuyến nghị chọn giá trị nhỏ nhất theo ordering rule khi không có control khác chi phối. Entry thiếu sort key được xem như có giá trị NULL theo quy tắc của RFC; khi đảo chiều, vị trí tương đối của NULL cũng thay đổi. Điều này cho thấy **thứ tự tùy thuộc matching rule và dữ liệu**, không chỉ tên trường `sort=mail` hay `sort=cn`.

Khi trả kết quả cho người dùng, API có thể đưa ra hợp đồng rõ ràng như:

~~~json
{
  "items": [
    {"uid": "an", "sn": "Nguyen"},
    {"uid": "binh", "sn": "Tran"}
  ],
  "sort": {
    "key": "sn",
    "direction": "asc",
    "confirmed": true,
    "performedBy": "ldap-server"
  },
  "page": {"index": 0, "size": 2}
}
~~~

Đây là **ví dụ JSON do ứng dụng tự thiết kế**, không phải phản hồi mặc định của LDAP hay Spring LDAP. Chỉ đặt `confirmed=true` nếu ứng dụng có căn cứ kiểm chứng rõ ràng, chẳng hạn Sort Response Control với `success` hoặc kết quả đã được ứng dụng sắp xếp đầy đủ theo hợp đồng của nó.

## 8. Tình huống lỗi và cách chẩn đoán

| Biểu hiện | Nguyên nhân cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| Không có sort response dù search trả dữ liệu | Server bỏ qua non-critical sort control hoặc không trả response | Xem support OID; không coi dữ liệu đã sort |
| `unavailableCriticalExtension` | Server không hỗ trợ critical sort hoặc không thể đáp ứng | Thông báo không hỗ trợ, chọn fallback phù hợp |
| Sort response trả `inappropriateMatching` | Thuộc tính/ordering rule không phù hợp | Đổi sort key hoặc đối chiếu schema server |
| Sort response trả `noSuchAttribute` | Server không nhận ra sort attribute | Kiểm tra schema, tên thuộc tính và khả năng backend |
| Trang riêng lẻ có vẻ đúng A–Z nhưng ghép trang bị đảo | Client chỉ sort từng trang | Sort toàn bộ tập trước khi phân trang hoặc nhờ server sort toàn cục |
| Cùng filter, thứ tự thay đổi giữa các lần search | Không có sort bảo đảm; tie keys; replica/đồng thời | Dùng sort được xác nhận và khóa phụ phù hợp |
| Cùng sort key nhưng chữ có dấu xếp khác | LDAP ordering rule khác `Collator` phía Java | Xác định locale/quy tắc sort chuẩn cho nghiệp vụ |
| Kết quả thiếu entry khi phân trang | Size/time limit, referral, cookie sai/lạc kết nối hoặc cập nhật đồng thời | Phân loại lỗi, kiểm tra cookie, endpoint và trạng thái toàn bộ search |

Không ghi log toàn bộ thuộc tính cá nhân, password hay token khi debug. Nên ghi OID control, sort key, result code, endpoint, thời gian và lỗi đã được làm sạch dữ liệu nhạy cảm. Tài khoản truy vấn dùng quyền đọc tối thiểu cần thiết, TLS và xác thực chứng chỉ phù hợp.

## 9. Kiểm thử có ý nghĩa

Trong LDAP test server có thể kiểm soát, chuẩn bị ít nhất bốn entry với tên không theo thứ tự DN và hai entry trùng họ. Sau đó:

1. **Không gửi sort control:** xác nhận ứng dụng **không khẳng định** thứ tự, dù kết quả tình cờ đúng A–Z.
2. **Gửi critical sort tới server không hỗ trợ:** xác nhận lỗi được xử lý và API không trả `sorted=true`.
3. **Gửi non-critical sort tới server không hỗ trợ:** xác nhận ứng dụng phát hiện thiếu sort response, thay vì tin vào thứ tự hiện tại.
4. **Gửi sort tới server hỗ trợ:** kiểm tra cả result code của Sort Response Control và danh sách trả về.
5. **Hai entry có cùng `sn`:** thử thêm khóa phụ duy nhất và xác nhận thứ tự rõ ràng theo hợp đồng.
6. **Nhiều trang:** dựng bộ dữ liệu khiến sort từng trang cho thứ tự sai; so sánh với sort toàn bộ tập trước paging.
7. **Cập nhật giữa các lần đọc trang:** đo khả năng xuất hiện entry trùng/bỏ sót và đưa ra chính sách xử lý.
8. **Thuộc tính thiếu, nhiều giá trị hoặc có dấu:** kiểm tra thứ tự theo schema/matching rule và cách Java `Collator` hoạt động.

Các ca kiểm thử này phải đối chiếu **trạng thái xác nhận sort** và đúng thứ tự đầu ra, không chỉ đếm số entry. Một bài kiểm thử chỉ chứng minh được thứ tự trên **một server, một bộ dữ liệu và một cấu hình cụ thể**; nó không tự mở rộng bảo đảm sang mọi backend/replica.

## 10. Bài tập vận dụng

Một API Spring LDAP có `pageSize=2` và server trả bốn bản ghi theo thứ tự: `[Minh, An, Dung, Binh]`. Server **không hỗ trợ** RFC 2891.

1. Nếu API lấy hai trang rồi sort từng trang phía Java, danh sách ghép có được bảo đảm A–Z không? Hãy tính kết quả.
2. Nếu request có sort control `critical=false` và không nhận sort response, có thể trả `sortConfirmed=true` không?
3. Nếu `critical=true` bị từ chối, API nên trả dữ liệu tự nhận đã sắp xếp hay báo lỗi/fallback có kiểm soát?
4. Nếu toàn bộ danh sách rất nhỏ, hãy đề xuất trình tự bước để trả trang 2 đúng thứ tự A–Z.
5. Nếu hai entry cùng `sn`, cần thêm điều kiện gì để hạn chế vị trí thay đổi giữa các lần đọc?
6. Paging cookie rỗng có chứng minh LDAP server đã sắp xếp kết quả không? Vì sao?

**Gợi ý đáp án:** (1) page 1 thành `[An, Minh]`, page 2 thành `[Binh, Dung]`, ghép lại `[An, Minh, Binh, Dung]` vẫn sai; (2) không; (3) báo lỗi hoặc thực hiện fallback có giới hạn; (4) tải đủ dữ liệu, phát hiện giới hạn/lỗi, sort toàn bộ, rồi cắt trang; (5) thêm khóa phụ duy nhất được server/client hỗ trợ và xử lý cập nhật đồng thời; (6) không, cookie chỉ biểu thị trạng thái phân trang của truy vấn.

## 11. Ghi nhớ

- LDAP Search **không bảo đảm thứ tự** nếu server không thực hiện sort được xác nhận hoặc ứng dụng chưa sắp xếp lại toàn bộ tập dữ liệu.
- Sort Request Control theo RFC 2891 chỉ là **yêu cầu**. Sort Response Control với `success` mới là bằng chứng server đã sắp xếp.
- **Critical sort** giúp fail rõ ràng khi không hỗ trợ; **non-critical sort** có thể bị bỏ qua mà search vẫn trả entry chưa sort.
- **Phân trang không đồng nghĩa sắp xếp.** Sort riêng từng trang không tạo thứ tự toàn cục, và sort + paging cũng không mặc nhiên tạo snapshot bất biến khi dữ liệu thay đổi.
- Khi server không hỗ trợ sort, chỉ nên **sort phía Java sau khi lấy đủ tập dữ liệu** với quy mô được giới hạn; nếu dữ liệu lớn, cần thay đổi kiến trúc hoặc hợp đồng API.
- Kiểm tra matching rule, khóa phụ, độ đầy đủ, lỗi giới hạn, referral, quyền đọc và endpoint để biết chính xác mức bảo đảm của danh sách hiển thị.

### Tài liệu tham khảo

- [RFC 2891 — LDAP Control Extension for Server Side Sorting](https://www.rfc-editor.org/rfc/rfc2891)
- [RFC 2696 — LDAP Simple Paged Results Control](https://www.rfc-editor.org/rfc/rfc2696)
- [RFC 4511 — Lightweight Directory Access Protocol (LDAPv3)](https://www.rfc-editor.org/rfc/rfc4511)
- [Spring LDAP — Processing the DirContext (DirContextProcessor và paged results)](https://docs.spring.io/spring-ldap/reference/processing-the-dircontext.html)
- [Spring LDAP — LdapTemplate API](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/LdapTemplate.html)
- [Spring LDAP — SortControlExchange API (4.1+)](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/control/SortControlExchange.html)
- [Spring LDAP — ControlExchangeDirContextProcessor API (4.1+)](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/control/ControlExchangeDirContextProcessor.html)
- [Oracle JNDI — SortControl, SortResponseControl](https://docs.oracle.com/en/java/javase/25/docs/api/java.naming/javax/naming/ldap/SortControl.html)
