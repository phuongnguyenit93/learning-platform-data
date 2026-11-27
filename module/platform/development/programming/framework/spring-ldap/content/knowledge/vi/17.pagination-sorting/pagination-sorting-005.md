# SortControlDirContextProcessor và sort key trong Spring LDAP

Khi tìm kiếm một danh sách người dùng trong dịch vụ thư mục, kết quả có thể xuất hiện với thứ tự khác nhau qua mỗi lần truy vấn. Nếu ứng dụng muốn hiển thị danh bạ theo tên hoặc kết hợp phân trang với sắp xếp, việc chỉ đặt LDAP filter là chưa đủ. **Spring LDAP** hỗ trợ yêu cầu **server-side sorting** thông qua LDAP control; trong các phiên bản trước, lớp thường gặp là `SortControlDirContextProcessor`.

Bài học thuộc chương **Phân trang và sorting**, tập trung vào cách chọn **sort key**, áp dụng `SortControlDirContextProcessor` trong `LdapTemplate`, kiểm tra server có thực sự sắp xếp hay không, hiểu các giới hạn của LDAP schema và kết hợp đúng với phân trang. Cuối bài cũng giới thiệu API thay thế được cung cấp từ Spring LDAP 4.1 để tránh phụ thuộc vào lớp đã deprecated.

## 1. Vì sao cần sắp xếp tại LDAP server?

Giả sử directory chứa ba người dùng:

```ldif
dn: uid=u03,ou=people,dc=example,dc=org
objectClass: inetOrgPerson
cn: Chi
sn: Tran
uid: u03

dn: uid=u01,ou=people,dc=example,dc=org
objectClass: inetOrgPerson
cn: An
sn: Nguyen
uid: u01

dn: uid=u02,ou=people,dc=example,dc=org
objectClass: inetOrgPerson
cn: Binh
sn: Le
uid: u02
```

Với filter `(objectClass=inetOrgPerson)`, LDAP search thông thường **không bảo đảm** các entry được trả về theo `uid`, `cn` hay thứ tự DN. Nếu giao diện cần sắp xếp theo `cn`, ứng dụng có hai lựa chọn:

| Cách làm | Dữ liệu được sắp xếp ở đâu? | Hạn chế |
| --- | --- | --- |
| Lấy toàn bộ entry rồi dùng `Comparator` của Java | Phía ứng dụng | Cần tải hết kết quả; tốn bộ nhớ; khó kết hợp đúng với giới hạn số lượng và phân trang trên server. |
| Gửi LDAP **Server Side Sort Control** | Phía LDAP server, trước khi trả kết quả | Server phải hỗ trợ control và matching rule phù hợp; cần kiểm tra sort response. |

Với nhiều entry và phân trang phía server, sort control thường là lựa chọn thích hợp. Tuy nhiên, yêu cầu sắp xếp **không tự động biến một truy vấn giới hạn 100 entry thành đầy đủ** và cũng không tự tạo cơ chế phân trang.

## 2. Sort key là gì?

**Sort key** là *tên thuộc tính LDAP* mà server dùng làm khóa sắp xếp. Chẳng hạn:

- `cn`: tên chung của entry;
- `sn`: họ của người dùng;
- `uid`: mã định danh người dùng nếu directory/schema hỗ trợ sắp xếp;
- `givenName`: tên riêng, khi schema và máy chủ cho phép ordering tương ứng.

Nếu sắp xếp theo `cn`, các giá trị ví dụ có thể xuất hiện theo thứ tự `An`, `Binh`, `Chi`. Thứ tự thực tế của chữ hoa, dấu tiếng Việt và các ký tự đặc biệt phụ thuộc **ordering matching rule**, schema và cách máy chủ triển khai. Không mặc định nó giống `String.compareTo()` hoặc `Collator` Java.

### Phân biệt sort key với filter và các thuộc tính trả về

| Khái niệm | Ví dụ | Mục đích |
| --- | --- | --- |
| Search filter | `(objectClass=inetOrgPerson)` | Chọn **những entry nào** được tìm thấy. |
| Search base | `ou=people` | Chỉ định **nhánh cây** để tìm. |
| Returning attributes | `cn`, `uid` | Chọn **trường nào** đưa về ứng dụng. |
| Sort key | `cn` | Yêu cầu server **xếp thứ tự** kết quả theo thuộc tính. |

Sort key có thể được server dùng ngay cả khi thuộc tính không nằm trong danh sách returning attributes, nhưng để hiển thị hoặc kiểm tra thứ tự, ta nên yêu cầu nhận về thuộc tính đó. Các quyền đọc và chính sách server vẫn có thể giới hạn khả năng sort.

Không truyền `"cn ASC"` hoặc `"sn DESC"` làm sort key trong constructor `SortControlDirContextProcessor(String)`: API này mong đợi **tên thuộc tính**, không phải cú pháp SQL.

## 3. LDAP Server Side Sort Control hoạt động thế nào?

RFC 2891 định nghĩa hai LDAP control:

| Control | OID | Vai trò |
| --- | --- | --- |
| **Sort request** | `1.2.840.113556.1.4.473` | Client yêu cầu sắp xếp kết quả tìm kiếm theo một hoặc nhiều sort key. |
| **Sort response** | `1.2.840.113556.1.4.474` | Server thông báo có thực hiện sắp xếp được không, cùng mã kết quả. |

Một yêu cầu tổng quát:

```text
Ứng dụng
  ├─ base: ou=people
  ├─ filter: (objectClass=inetOrgPerson)
  └─ sort request: key = cn
           │
           ▼
LDAP server hỗ trợ sort control
  ├─ áp filter, search scope và các chính sách giới hạn
  ├─ dùng ordering rule để sắp kết quả
  └─ trả entry cùng sort response control
           │
           ▼
Spring LDAP đọc kết quả và trạng thái sort
```

Có ba điểm cần nhớ:

1. Kết quả tìm kiếm có thể thành công về mặt giao thức nhưng **yêu cầu sort thất bại**. Mã sort result được báo **riêng** trong sort response control.
2. Nếu server không hỗ trợ sort control và yêu cầu đánh dấu **critical**, server phải từ chối thay vì âm thầm trả dữ liệu không sắp xếp. Nếu không critical, server có thể bỏ qua control.
3. Nếu thiếu sort response control, ứng dụng **không nên tự khẳng định** rằng server đã sắp xếp kết quả.

Mã `0` trong sort response nghĩa là thành công. Các mã khác có thể chỉ lỗi thuộc tính, matching rule, quyền truy cập hoặc giới hạn quản trị; chi tiết được trình bày ở phần xử lý lỗi.

## 4. Dùng SortControlDirContextProcessor với LdapTemplate

`SortControlDirContextProcessor` thuộc package `org.springframework.ldap.control`. Nó triển khai `DirContextProcessor` để thêm request control trước khi search và đọc response control sau khi search. API này có ở Spring LDAP 3.x và vẫn có mặt trong một số bản 4.x; **từ Spring LDAP 4.1, lớp được đánh dấu deprecated** và có phương án mới trong phần 8.

Các phương thức quan trọng:

| API | Ý nghĩa |
| --- | --- |
| `new SortControlDirContextProcessor("cn")` | Yêu cầu sort theo một thuộc tính là `cn`. |
| `setCritical(true)` | Đánh dấu sort control là yêu cầu bắt buộc (phương thức kế thừa). |
| `isSorted()` | Kiểm tra phản hồi có xác nhận server đã sắp xếp hay không. |
| `getResultCode()` | Đọc mã kết quả của sort response control. |
| `getSortKey()` | Đọc **tên thuộc tính đã cấu hình**, không phải giá trị của entry. |

**Quan trọng:** Lớp này **có trạng thái**; cần tạo một đối tượng mới cho mỗi search. Không khai báo một singleton `SortControlDirContextProcessor` được nhiều luồng chia sẻ.

### Ví dụ Java: tìm người dùng theo cn

Giả sử `ContextSource` có base DN `dc=example,dc=org`, đã cấu hình `LdapContextSource` và tạo một `LdapTemplate` có quyền tìm kiếm. Ví dụ sau sắp xếp theo `cn`:

```java
import java.util.List;
import javax.naming.directory.Attribute;
import javax.naming.directory.SearchControls;

import org.springframework.ldap.control.SortControlDirContextProcessor;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;

public class SortedPeopleSearch {
    private final LdapTemplate ldapTemplate;

    public SortedPeopleSearch(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<String> findNamesSortedByCn() {
        SearchControls controls = new SearchControls();
        controls.setSearchScope(SearchControls.SUBTREE_SCOPE);
        controls.setReturningAttributes(new String[] {"cn"});
        controls.setTimeLimit(5_000); // 5.000 ms

        SortControlDirContextProcessor sort =
                new SortControlDirContextProcessor("cn");

        // Tránh im lặng chấp nhận danh sách không được sort.
        sort.setCritical(true);

        AttributesMapper<String> mapper = attrs -> {
            Attribute cn = attrs.get("cn");
            return cn == null ? "(không có cn)" : cn.get().toString();
        };

        List<String> names = ldapTemplate.search(
                "ou=people",
                "(objectClass=inetOrgPerson)",
                controls,
                mapper,
                sort);

        if (!sort.isSorted()) {
            throw new IllegalStateException(
                    "LDAP server không xác nhận đã sort; result code = "
                            + sort.getResultCode());
        }

        return names;
    }
}
```

**Giải thích từng phần:**

1. `SearchControls.SUBTREE_SCOPE` giới hạn phạm vi tìm kiếm trong cây con của `ou=people`. Do `ContextSource` đã có base `dc=example,dc=org`, chuỗi `ou=people` là DN tương đối.
2. `setReturningAttributes(new String[] {"cn"})` giới hạn thuộc tính mang về; điều này khác với giới hạn số entry.
3. `new SortControlDirContextProcessor("cn")` khai báo thuộc tính mà server phải dùng để sắp xếp.
4. `setCritical(true)` yêu cầu server từ chối khi không thể hỗ trợ control, để ứng dụng không vô tình hiển thị kết quả như đã được sort.
5. Overload `ldapTemplate.search(base, filter, controls, mapper, processor)` cho phép `DirContextProcessor` thiết lập và kiểm tra LDAP control.
6. `isSorted()` được kiểm tra **sau khi search hoàn tất**, không được gọi trước rồi dùng như kết quả cuối.

Nếu server từ chối critical control, `search(...)` có thể **ném ngoại lệ trước khi trả list**. Trong tình huống đó nhánh `if (!sort.isSorted())` không chạy; phải xử lý lỗi tìm kiếm ở tầng service/API theo nghiệp vụ. Không suy ra có kết quả đã sắp xếp chỉ vì không nhìn thấy exception nếu server không trả trạng thái xác nhận sort.

> **Lưu ý:** Một số server thiếu ordering rule cho thuộc tính hoặc không cho sort vì giới hạn tài nguyên. Hãy kiểm tra khả năng hỗ trợ server-side sort, schema và permission trong môi trường triển khai thay vì giả định `cn` luôn sắp được.

## 5. Kiểm tra phản hồi và xử lý lỗi sort

Mỗi LDAP search có kết quả riêng; sort response control cũng có một **sortResult** riêng. Với lớp `SortControlDirContextProcessor`, dùng cả `isSorted()` và `getResultCode()`:

```java
SortControlDirContextProcessor sort =
        new SortControlDirContextProcessor("sn");

// Gọi ldapTemplate.search(..., sort) xong mới đọc các giá trị:
if (sort.isSorted()) {
    // Có xác nhận server đã sắp xếp theo sn.
} else {
    int sortCode = sort.getResultCode();
    // Ghi nhận mã lỗi hoặc trạng thái không có phản hồi,
    // xử lý theo chính sách ứng dụng.
}
```

Mã lỗi sort theo RFC 2891 thường gặp:

| Mã | Tên kết quả | Cách diễn giải |
| --- | --- | --- |
| `0` | `success` | Server xác nhận đã sắp xếp theo yêu cầu. |
| `3` | `timeLimitExceeded` | Không thể hoàn tất sort trước giới hạn thời gian. |
| `11` | `adminLimitExceeded` | Quá giới hạn tài nguyên/quản trị dành cho sort. |
| `16` | `noSuchAttribute` | Sort key không nhận diện được tại server. |
| `18` | `inappropriateMatching` | Ordering matching rule không hợp lệ hoặc không phù hợp thuộc tính. |
| `50` | `insufficientAccessRights` | Không được phép thực hiện yêu cầu sort. |
| `53` | `unwillingToPerform` | Server từ chối thực hiện sort trong hoàn cảnh hiện tại. |

Một số trường hợp không nhận được sort response control (ví dụ server bỏ qua control không critical hoặc search thất bại trước khi tạo response); khi đó `isSorted()` không xác nhận thành công. Ở những triển khai, `getResultCode()` có thể giữ giá trị khởi tạo như `-1` khi chưa có response. **Không coi mã -1 là một LDAP result code chuẩn**.

Một nguyên nhân khác là **server không hỗ trợ control**. Có thể kiểm tra thuộc tính `supportedControl` của Root DSE để xem server công bố OID `1.2.840.113556.1.4.473` hay không. Tuy nhiên việc OID được công bố không chứng minh mọi thuộc tính đều có thể dùng làm sort key; vẫn cần kiểm tra sort response.

### Criticality quyết định cách xử lý khi server không hỗ trợ

| Criticality | Khi server không hỗ trợ sort control | Điều ứng dụng cần làm |
| --- | --- | --- |
| `true` | Server trả lỗi như `unavailableCriticalExtension` theo RFC. | Bắt ngoại lệ phù hợp và thông báo tính năng không khả dụng. |
| `false` | Server có thể bỏ qua sort request và trả danh sách không sort. | Kiểm tra `isSorted()`; không gắn nhãn “đã sắp xếp” khi chưa được xác nhận. |

Không dùng `try/catch(Exception)` để tự động sắp xếp từng trang sau khi lỗi LDAP sort: nếu mỗi trang được sắp riêng, thứ tự toàn cục sẽ sai.

## 6. Lựa chọn sort key và thứ tự dữ liệu

### 6.1. Chọn tên thuộc tính có thể sắp xếp

Sort key phải là **attribute description hợp lệ trong schema** và server phải có **ordering matching rule** tương thích để so sánh các giá trị. Một thuộc tính dùng được trong filter equality chưa chắc đã hỗ trợ ordering như mong muốn.

Ví dụ trong danh bạ:

- `sn`: có thể phù hợp nếu muốn sắp xếp theo họ, khi directory hỗ trợ ordering trên thuộc tính này.
- `cn`: phù hợp khi muốn xếp theo tên hiển thị, nhưng hành vi với dấu tiếng Việt, chữ hoa và nhiều giá trị cần được kiểm tra.
- `uid`: thường hữu ích làm khóa bổ sung nếu server hỗ trợ, nhất là khi nhiều người có cùng tên hiển thị.
- Thuộc tính nhị phân như `jpegPhoto` thông thường không phù hợp làm sort key.

Tuyệt đối không lấy chuỗi sort key trực tiếp từ tham số HTTP rồi gắn vào request control tùy ý. Hãy áp dụng **allowlist** các tên thuộc tính đã được ứng dụng kiểm chứng với schema và server:

```java
import java.util.Set;

Set<String> allowed = Set.of("cn", "sn", "uid");
if (!allowed.contains(sortKeyFromUser)) {
    throw new IllegalArgumentException("Sort key không được hỗ trợ");
}

SortControlDirContextProcessor sort =
        new SortControlDirContextProcessor(sortKeyFromUser);
```

Code dùng `Set.of` nên cần Java 9+. `sortKeyFromUser` ở ví dụ chỉ là input đã được lấy từ lời gọi phương thức hoặc request; phải có giá trị trước khi chạy đoạn code. Allowlist vừa ngăn yêu cầu không hợp lệ, vừa giúp ứng dụng kiểm soát các kiểu sort có thể tốn tài nguyên.

### 6.2. Giá trị thiếu, đa trị và trùng sort key

Theo RFC 2891:

| Dữ liệu | Quy tắc tổng quát |
| --- | --- |
| Entry không có thuộc tính dùng để sort | Giá trị được xem là `NULL`; với sort tăng dần theo một key, các entry thiếu key thường đứng **sau** entry có key. |
| Sort đảo ngược một key | Entry thiếu key thường được đưa **lên đầu**. |
| Thuộc tính đa trị | Server **nên** dùng giá trị nhỏ nhất theo ordering rule khi một entry có nhiều giá trị và không có control khác làm thay đổi thứ tự. |
| Hai entry có cùng sort key | Thứ tự giữa chúng có thể không ổn định nếu không có khóa phân biệt bổ sung. |

Đừng giả định thứ tự theo `cn` sẽ đủ ổn định nếu có nhiều người cùng tên. Khi kết hợp phân trang, nên chọn thêm một key có khả năng phân biệt (ví dụ `uid`) nếu server hỗ trợ, hoặc cân nhắc một khóa độc nhất phù hợp schema. Điều này giúp giảm hiện tượng record đổi chỗ giữa các trang, dù **không loại bỏ** thay đổi do dữ liệu được cập nhật đồng thời.

### 6.3. Nhiều key và sort giảm dần

RFC 2891 hỗ trợ danh sách khóa theo **thứ tự ưu tiên**, kèm ordering rule tùy chọn và cờ `reverseOrder` cho từng key. Tuy vậy, constructor:

```java
new SortControlDirContextProcessor("cn");
```

chỉ nhận **một chuỗi tên thuộc tính**. Không truyền một biểu thức `"sn,cn"` hoặc `"cn DESC"` để mong đổi chiều hoặc sắp nhiều khóa; đó không phải cú pháp được API này định nghĩa.

Trong các tình huống cần nhiều key hoặc sort đảo chiều, hãy dùng API mới hỗ trợ nhiều khóa (xem phần 8) hoặc đi xuống JNDI `javax.naming.ldap.SortControl` và `SortKey` khi cần kiểm soát từng rule và hướng sort. Tính năng cụ thể còn phụ thuộc khả năng của LDAP server.

## 7. Quan hệ giữa sorting và phân trang

Sorting và phân trang là hai control/khả năng khác nhau:

- **Sort Control (RFC 2891):** xác định thứ tự của tập kết quả.
- **Simple Paged Results (RFC 2696):** chia kết quả thành các trang và sử dụng cookie để lấy trang kế tiếp.
- **Count limit và time limit:** giới hạn số entry hoặc thời gian xử lý; không tự tạo sort hay pagination.

RFC 2891 yêu cầu khi kết hợp server-side sort với paged results, server phải áp thứ tự sắp xếp cho **toàn bộ tập kết quả**, thay vì sắp riêng từng trang. Client phải gửi **sort key list không đổi cho mỗi lần yêu cầu trang tiếp theo**, và nên kiểm tra sort response của từng trang.

Ví dụ:

```text
Dữ liệu cần sort theo cn:
An, Binh, Chi, Dung, Ha, Lan, Minh

Đúng (sort toàn bộ rồi chia page size 3):
  Trang 1: An, Binh, Chi
  Trang 2: Dung, Ha, Lan
  Trang 3: Minh

Sai (lấy ba kết quả bất kỳ rồi sort từng trang):
  Trang 1: Chi, Dung, Minh
  Trang 2: An, Binh, Lan
  Trang 3: Ha
```

Khi sử dụng Spring LDAP để phân trang:

1. Server cần hỗ trợ cả sort và paged result controls.
2. Các control được áp dụng trên **cùng search request**; nếu dùng `AggregateDirContextProcessor`, hãy bảo đảm từng processor không ghi đè control của nhau và phiên bản Spring LDAP hỗ trợ tổ hợp đó.
3. Truy vấn, search scope, filter và **sort keys phải nhất quán** giữa các trang.
4. Paged results thường cần dùng lại cùng kết nối LDAP qua `SingleContextSource` hoặc cấu hình transaction/context phù hợp, để cookie vẫn dùng được.
5. Nếu một trang không xác nhận sort thành công, đừng ghép nó vào danh sách và tuyên bố toàn bộ dữ liệu đã được sắp xếp.

Với ứng dụng ghi/đọc directory liên tục, ngay cả kết quả đã được sort theo nhiều key cũng có thể thay đổi trong quá trình lấy các trang. Hãy thiết kế tính nhất quán của báo cáo hoặc đồng bộ dữ liệu theo yêu cầu thực tế.

## 8. Từ Spring LDAP 4.1: API thay thế

Trong **Spring LDAP 4.1+**, `SortControlDirContextProcessor` được đánh dấu **deprecated**; tài liệu Spring khuyến nghị dùng `ControlExchangeDirContextProcessor` kết hợp `SortControlExchange`. Cách cũ vẫn hữu ích để đọc các dự án và phiên bản thư viện trước đó, nhưng khi viết ứng dụng mới trên 4.1+ nên dùng API mới.

Ví dụ thay thế phần sort processor trong code `findNamesSortedByCn()` của mục 4 (giữ nguyên `controls`, `mapper` và `ldapTemplate`):

```java
import javax.naming.ldap.SortControl;
import javax.naming.ldap.SortResponseControl;

import org.springframework.ldap.control.ControlExchangeDirContextProcessor;
import org.springframework.ldap.control.SortControlExchange;

// API được giới thiệu từ Spring LDAP 4.1.
ControlExchangeDirContextProcessor<SortControl, SortResponseControl> sort =
        new ControlExchangeDirContextProcessor<>(
                new SortControlExchange("sn", "givenName"));

List<String> names = ldapTemplate.search(
        "ou=people",
        "(objectClass=inetOrgPerson)",
        controls,
        mapper,
        sort);

SortResponseControl response = sort.getExchange().getResponse();

if (response == null || !response.isSorted()) {
    throw new IllegalStateException(
            "LDAP server không xác nhận đã sort theo sn, givenName");
}
```

`SortControlExchange("sn", "givenName")` yêu cầu ưu tiên sắp theo `sn` trước, rồi `givenName` khi các entry có cùng `sn`, **nếu máy chủ hỗ trợ các khóa đó**. Mã này minh họa API mới, cần đặt **bên trong phương thức** có sẵn biến `controls`, `mapper` và `ldapTemplate`; không phải một class độc lập.

`SortControlExchange` giữ request và response control; `ControlExchangeDirContextProcessor.getExchange().getResponse()` trả về `SortResponseControl` hoặc `null`. Nếu có response và `response.isSorted()` là true thì server đã xác nhận sort thành công. Nếu cần chi tiết lỗi, dùng `response.getResultCode()` khi response khác `null`.

**Khác biệt phiên bản:** `SortControlExchange` và `ControlExchangeDirContextProcessor` được giới thiệu từ **Spring LDAP 4.1**. Dự án trên Spring LDAP 3.x cần tiếp tục dùng API phù hợp phiên bản hoặc viết processor JNDI tương ứng; không sao chép nguyên đoạn trên vào 3.x.

## 9. Thực hành với directory thử nghiệm

Chuẩn bị LDAP server thử nghiệm có entry người dùng và cấu hình `LdapContextSource` với base `dc=example,dc=org`. Dùng tài khoản có quyền đọc các entry; bật TLS theo cấu hình hệ thống. Trước khi thử sort, xác nhận server hỗ trợ OID request control của RFC 2891.

Thực hiện:

1. Tìm tất cả entry dưới `ou=people` không dùng sort control, ghi lại `uid` và `cn` nhận được.
2. Tìm lại cùng base/filter/scope với `SortControlDirContextProcessor("cn")`; ghi lại thứ tự và giá trị `isSorted()`, `getResultCode()`.
3. Chạy thêm với sort key `sn` nếu server hỗ trợ. Nhận xét thứ tự khác gì so với `cn`.
4. Yêu cầu sort theo một thuộc tính không có trong schema, ví dụ `unknownSortKey`. Quan sát kết quả trong sort response hoặc ngoại lệ khi control critical.
5. Tắt tính critical trong môi trường thử nghiệm và quan sát xem server có thể trả danh sách không sắp xếp trong trường hợp không hỗ trợ sort hay không.
6. Nếu server hỗ trợ paged results, chia kết quả thành các trang nhỏ, giữ nguyên sort keys giữa các lần truy vấn, rồi kiểm tra thứ tự **toàn bộ các trang ghép lại**.

**Câu hỏi tự đánh giá:**

- Vì sao không thể suy ra thứ tự LDAP search từ tên DN hoặc vị trí entry trong cây?
- `getSortKey()` của `SortControlDirContextProcessor` trả về thông tin gì? Có phải giá trị thuộc tính của entry đầu tiên không?
- Vì sao cần kiểm tra `isSorted()` sau search thay vì mặc định server đã tôn trọng sort request?
- Ý nghĩa của criticality khi server không hỗ trợ sort control là gì?
- Vì sao sort theo `cn` có thể không ổn định nếu nhiều entry cùng tên?
- Nếu đã sort trong Java sau khi lấy từng trang LDAP, có thể bảo đảm thứ tự toàn bộ tập kết quả hay không?
- Tại sao không thể dùng `SortControlDirContextProcessor("cn DESC")` như một cách bật descending?

## 10. Ghi nhớ

- **Sort key** là tên thuộc tính LDAP mà server dùng để sắp kết quả, ví dụ `cn` hoặc `sn`; việc sắp xếp phụ thuộc ordering rule và hỗ trợ của server.
- `SortControlDirContextProcessor("cn")` yêu cầu server-side sort trong các phiên bản Spring LDAP có lớp này. Nó là **stateful**, cần tạo mới cho từng tìm kiếm và kiểm tra `isSorted()` / `getResultCode()` sau khi nhận kết quả.
- Bật **critical** nếu nghiệp vụ yêu cầu kết quả đã được sort; phản hồi tìm kiếm bình thường không tự chứng minh sort thành công.
- Sort và phân trang là hai cơ chế khác nhau; khi kết hợp, server phải sắp theo **tập kết quả toàn cục**, các trang giữ nguyên sort keys và dùng cookie đúng cách.
- Với **Spring LDAP 4.1+**, sử dụng `ControlExchangeDirContextProcessor` và `SortControlExchange` theo API được khuyến nghị thay cho lớp cũ.

## Tài liệu tham khảo

- [Spring LDAP Javadoc 3.3 — SortControlDirContextProcessor](https://docs.spring.io/spring-ldap/docs/3.3.x/api/org/springframework/ldap/control/SortControlDirContextProcessor.html)
- [Spring LDAP Reference — Processing the DirContext](https://docs.spring.io/spring-ldap/reference/processing-the-dircontext.html)
- [Spring LDAP Javadoc — LdapOperations](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/LdapOperations.html)
- [Spring LDAP 4.1 — SortControlExchange](https://docs.spring.io/spring-ldap/reference/4.1-SNAPSHOT/api/java/org/springframework/ldap/control/SortControlExchange.html)
- [Spring LDAP 4.2 — ControlExchangeDirContextProcessor](https://docs.spring.io/spring-ldap/reference/4.2-SNAPSHOT/api/java/org/springframework/ldap/control/ControlExchangeDirContextProcessor.html)
- [RFC 2891 — LDAP Server Side Sorting](https://www.rfc-editor.org/rfc/rfc2891)
- [RFC 2696 — LDAP Simple Paged Results](https://www.rfc-editor.org/rfc/rfc2696)
