# Wildcard, substring và chi phí tìm kiếm

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Hiểu dấu `*` trong LDAP filter: khi nào là **wildcard**, khi nào là **phép kiểm tra sự hiện diện** (*presence*), khi nào chỉ là **ký tự dấu sao literal** đã escape.
- Phân biệt tìm kiếm **prefix**, **suffix**, **contains** và **substring có nhiều đoạn**; không nhầm chúng với cú pháp SQL `LIKE` hoặc truy vấn full-text.
- Giải thích vì sao các filter wildcard quá rộng dễ tăng chi phí xử lý trên LDAP server, ngay cả khi kết quả trả về ít.
- Chọn search base, search scope, điều kiện giới hạn, thuộc tính trả về và chỉ mục phù hợp với khối lượng dữ liệu.
- Tạo filter an toàn trong **Spring LDAP** bằng `LdapTemplate`, `LdapQueryBuilder`, `EqualsFilter` hoặc `LdapEncoder`, tránh LDAP filter injection.
- Thiết kế phép đo và kiểm thử truy vấn trong điều kiện dữ liệu, schema, ACL và cấu hình server thực tế.

Bài thuộc chương **Filter LDAP** của module **SPRING_LDAP**. Trong ứng dụng sử dụng `ContextSource`, `LdapTemplate`, `LdapClient` hoặc ODM, filter có thể giống một chuỗi ngắn, nhưng hiệu năng và tính đúng đắn của nó phụ thuộc vào schema, chỉ mục, quyền truy cập, số entry trong search scope và khả năng tối ưu của máy chủ LDAP.

## 1. Bối cảnh: một ô tìm kiếm tên nhân viên

Giả sử directory có các entry thuộc nhánh:

~~~ldif
dn: uid=lan,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: lan
cn: Nguyen Lan
sn: Nguyen
mail: lan@example.org
~~~

Một ứng dụng danh bạ muốn hỗ trợ ba thao tác:

1. Tìm chính xác tài khoản `uid=lan` để hiển thị hồ sơ.
2. Gợi ý nhân viên có `cn` **bắt đầu bằng** `Nguyen`.
3. Tìm bất kỳ tên nhân viên nào **chứa** từ `Lan`.

Các LDAP filter tương ứng có thể là:

~~~ldap
(uid=lan)
(cn=Nguyen*)
(cn=*Lan*)
~~~

Chúng không tương đương. Filter thứ nhất yêu cầu **equality**; hai filter còn lại yêu cầu **substring matching**. Chi phí của chúng có thể rất khác nhau tùy cách server đánh chỉ mục và giới hạn tìm kiếm.

## 2. Dấu `*` trong LDAP filter có ba vai trò cần phân biệt

### 2.1. Equality: không có wildcard

~~~ldap
(cn=Nguyen Lan)
~~~

Filter yêu cầu server so sánh giá trị với `Nguyen Lan` theo **equality matching rule** của attribute type `cn`. Với `caseIgnoreMatch` thường dùng cho `cn`, case của giá trị có thể được bỏ qua theo quy tắc chuẩn bị chuỗi LDAP. Không được coi phép so sánh này là `String.equals` trong Java.

### 2.2. Presence: đúng một dấu `*` đơn độc

~~~ldap
(cn=*)
~~~

Đây là filter **presence**: entry có thuộc tính `cn` hiện diện hay không. Nó **không** hỏi giá trị `cn` có chứa dấu sao, cũng không phải substring “khớp mọi thứ” theo ý nghĩa thông thường.

Nếu server hỗ trợ presence index cho thuộc tính và phạm vi tìm kiếm phù hợp, presence filter có thể được tối ưu. Tuy nhiên, khi gần như mọi entry đều có `cn`, điều kiện này vẫn có thể chọn ra một tập kết quả rất lớn.

### 2.3. Substring: wildcard phân tách các phần giá trị

~~~ldap
(cn=Nguyen*)       # Bắt đầu bằng Nguyen
(cn=*Lan)          # Kết thúc bằng Lan
(cn=*Lan*)         # Có chứa Lan ở một vị trí nào đó
(cn=Nguyen*Lan)    # Bắt đầu Nguyen, kết thúc Lan
(cn=N*uy*Lan)      # Các đoạn theo thứ tự: N, uy, Lan
~~~

Trong substring filter, `*` là **ký hiệu ngăn cách các đoạn cần khớp**. Khoảng giữa hai đoạn có thể gồm **không hoặc nhiều ký tự**, theo substring matching rule của attribute type.

Ví dụ `(cn=Nguyen*Lan)` có thể khớp `Nguyen Lan`, `NguyenThiLan` và `NguyenLan` nếu so khớp chuỗi theo schema; nó không yêu cầu có đúng một dấu cách giữa hai phần.

Nếu muốn tìm một giá trị **thực sự chứa ký tự `*`**, phải escape dấu sao đó. Không nên dùng `(cn=**)` để biểu diễn presence; hãy dùng đúng `(cn=*)`. Các mẫu có nhiều wildcard liên tiếp không thêm thông tin có ích cho truy vấn và hành vi tối ưu có thể phụ thuộc server.

### 2.4. Bảng nhanh về ý nghĩa

| Filter | Loại | Điều kiện tìm kiếm |
| --- | --- | --- |
| `(uid=lan)` | Equality | `uid` bằng `lan` theo equality rule |
| `(cn=*)` | Presence | Có thuộc tính `cn` |
| `(cn=Lan*)` | Substring, prefix | Giá trị `cn` bắt đầu bằng `Lan` |
| `(cn=*Lan)` | Substring, suffix | Giá trị `cn` kết thúc bằng `Lan` |
| `(cn=*Lan*)` | Substring, contains | Giá trị `cn` chứa `Lan` |
| `(cn=La*n)` | Substring, nhiều đoạn | Bắt đầu bằng `La`, kết thúc bằng `n` |
| `(cn=Lan\2a)` | Equality với dấu sao literal | Giá trị bằng chuỗi `Lan*` theo equality rule |
| `(cn=Lan\2a*)` | Substring, prefix có dấu sao literal | Bắt đầu bằng chuỗi `Lan*` |

**Mấu chốt:** dấu sao được escape (`\2a` hoặc `\2A`) là **dữ liệu**, còn `*` không escape trong biểu thức substring là **wildcard**.

## 3. Cú pháp RFC 4515: vì sao escape là bắt buộc?

LDAP filter dạng chuỗi được quy định trong **RFC 4515**. Trong *assertion value*, các ký tự đặc biệt cần escape gồm:

| Ký tự dữ liệu | Cách escape trong filter | Lý do |
| --- | --- | --- |
| `*` | `\2a` | Nếu không escape sẽ mang nghĩa wildcard/presence |
| `(` | `\28` | Nếu không escape có thể phá cấu trúc filter |
| `)` | `\29` | Nếu không escape có thể phá cấu trúc filter |
| `\` | `\5c` | Dấu escape phải được biểu diễn đúng |
| Byte NUL | `\00` | Không được đặt NUL trực tiếp vào filter string |

Số hex trong bảng thể hiện octet của ký tự tương ứng; với Unicode ngoài ASCII, phải biểu diễn các octet UTF-8 khi cần escape theo RFC 4515.

Giả sử ứng dụng nhận tên đăng nhập thực sự là `lan*`:

~~~ldap
(uid=lan*)     # Sai nếu muốn tìm literal "lan*": đây là prefix search
(uid=lan\2a)   # Đúng ý nghĩa: so sánh với giá trị chứa dấu *
~~~

Việc tự nối input vào filter như sau là nguy hiểm:

~~~java
String filter = "(uid=" + userInput + ")";
~~~

Nếu input có `*`, `(`, `)` hoặc ký tự escape, ý nghĩa truy vấn có thể bị thay đổi. Với các chuỗi có cấu trúc như `*)(|(uid=*))`, việc ghép thẳng có thể mở rộng điều kiện truy vấn và tạo **LDAP filter injection**.

Trong ứng dụng Spring LDAP, hãy dùng lớp tạo filter biết escape giá trị hoặc encode phần input trước khi thêm wildcard có chủ đích.

### Escape filter và escape DN là hai việc khác nhau

- Escape filter: bảo vệ phần **giá trị truy vấn**, ví dụ `(cn=Nguyen\2a)`.
- Escape DN: biểu diễn giá trị trong cấu trúc tên, ví dụ `cn=Nguyen\, Lan,ou=people,dc=example,dc=org`.

Dấu phẩy `,` rất quan trọng trong DN, nhưng không có cùng vai trò cú pháp trong LDAP filter. Không dùng DN escaping để thay cho filter escaping và ngược lại.

## 4. Matching rule quyết định substring khớp như thế nào

Mỗi attribute type có thể khai báo các rule riêng:

- `EQUALITY`: dùng cho `(attr=value)`.
- `SUBSTR`: dùng cho `(attr=*fragment*)` hoặc các biến thể prefix/suffix.
- `ORDERING`: dùng cho `>=`, `<=` nếu có hỗ trợ.

Ví dụ, `cn` trong schema thông dụng có thể dùng `caseIgnoreMatch` cho equality và `caseIgnoreSubstringsMatch` cho substring. Vì vậy:

~~~ldap
(cn=*LAN*)
~~~

có thể khớp một entry có `cn: Nguyen Lan`. Ngược lại, với một attribute type dùng `caseExactSubstringsMatch`, thay đổi chữ hoa/thường có thể dẫn đến kết quả khác.

Một vài điểm quan trọng:

1. **Tên thuộc tính** như `cn`/`CN` không phân biệt hoa/thường, nhưng **giá trị** có case-sensitive hay không phụ thuộc matching rule.
2. `caseIgnoreSubstringsMatch` không tương đương với việc gọi `toLowerCase()` trong Java: server có thể chuẩn bị chuỗi theo các quy tắc Unicode/khoảng trắng được chuẩn hóa.
3. Một type có equality rule **không đồng nghĩa** nó phải có substring rule. Nếu không có rule thích hợp, biểu thức có thể đánh giá thành **Undefined**, và entry sẽ không được chọn trong kết quả tìm kiếm.
4. Với thuộc tính **nhiều giá trị**, filter khớp nếu ít nhất một giá trị thỏa điều kiện. Không được giả định các đoạn substring được ghép xuyên qua hai giá trị khác nhau.
5. Wildcard LDAP không phải **fuzzy search** hay tìm kiếm theo mức độ liên quan. Approximate filter `~=` và full-text search là những cơ chế khác, còn tùy server.

### Ví dụ với thuộc tính nhiều giá trị

~~~ldif
dn: uid=lan,ou=people,dc=example,dc=org
objectClass: inetOrgPerson
uid: lan
cn: Nguyen Lan
cn: Lan Nguyen
sn: Nguyen
~~~

Filter `(cn=Lan*)` có thể khớp nhờ giá trị thứ hai. Nhưng server không lấy phần đầu của một giá trị rồi ghép với phần cuối của giá trị còn lại để so một substring duy nhất.

## 5. Chi phí tìm kiếm: từ filter đến tập entry phải kiểm tra

Không có công thức tổng quát “một wildcard bằng X mili giây”. Chi phí phụ thuộc vào:

- **Kích thước search scope:** có bao nhiêu entry dưới search base và trong phạm vi `OBJECT`, `ONELEVEL` hay `SUBTREE`.
- **Độ chọn lọc (selectivity):** có bao nhiêu entry thỏa điều kiện.
- **Chỉ mục trên server:** attribute có equality, presence hoặc substring index thích hợp không; engine dùng chỉ mục ra sao.
- **Độ dài và vị trí đoạn cố định:** `Lan*`, `*Lan`, `*Lan*` có thể dẫn tới cách xử lý khác nhau; đoạn quá ngắn thường ít chọn lọc.
- **Phép kết hợp:** các điều kiện `&`, `|`, `!` có thể làm thay đổi tập ứng viên và khả năng tối ưu.
- **Tài nguyên và cấu hình:** CPU, RAM, cache, disk, giới hạn server, ACL, replication, backend và các kết nối đang dùng.
- **Dữ liệu trả về:** số entry, số lượng/kích thước thuộc tính, truyền mạng, ánh xạ kết quả của ứng dụng.

Một cách hiểu thực tế:

~~~mermaid
flowchart TD
    Q["Filter + search base + scope"]
    Q --> P["Server phân tích filter và schema"]
    P --> I{"Có chỉ mục có thể dùng?"}
    I -->|Có| C["Dùng posting lists / tập ứng viên từ index"]
    I -->|Không / không hữu ích| S["Duyệt nhiều entry trong phạm vi tìm kiếm"]
    C --> M["Kiểm tra filter trên các ứng viên"]
    S --> M
    M --> A["Áp dụng quyền truy cập và giới hạn"]
    A --> R["Trả entry + thuộc tính qua mạng"]
    R --> J["Spring LDAP ánh xạ kết quả"]
~~~

Đây là **mô hình khái niệm**: server có thể thay đổi thứ tự, kết hợp điều kiện, dùng cache hoặc chọn chiến lược khác. Ứng dụng không kiểm soát trực tiếp query plan chỉ bằng việc chọn một cú pháp filter.

### 5.1. Prefix, suffix, contains: mức độ rủi ro tương đối

| Mẫu | Độ chọn lọc điển hình | Nhận định hiệu năng |
| --- | --- | --- |
| `(uid=lan)` | Thường cao nếu `uid` gần duy nhất | Thường thuận lợi khi có equality index |
| `(cn=Nguyen*)` | Tùy số người có cùng tiền tố | Có thể dùng substring/prefix index tùy server |
| `(cn=*Lan)` | Tùy hậu tố | Có thể tốn kém nếu index không hỗ trợ tốt hậu tố |
| `(cn=*an*)` | Thường thấp với đoạn rất ngắn | Dễ tạo tập ứng viên lớn, kể cả khi có substring index |
| `(cn=*Nguyen Lan*)` | Có thể chọn lọc hơn `*an*` | Vẫn phụ thuộc index và phạm vi |
| `(cn=*)` | Thường thấp nếu `cn` phổ biến | Presence index không làm tập kết quả tự nhỏ đi |
| `(objectClass=inetOrgPerson)` | Có thể rất rộng | Hữu ích khi phối hợp nhưng không mặc định chọn lọc |
| `(!(cn=Lan))` | Có thể trả phần lớn directory | Phủ định rộng dễ tốn tài nguyên |

Bảng là **xu hướng thiết kế**, không phải cam kết về thứ tự hiệu năng. Một LDAP server có chỉ mục substring phù hợp có thể xử lý tốt query chứa wildcard giữa chuỗi; một server khác có thể phải quét nhiều entry, kể cả với prefix. **Phải đo trên server và dữ liệu thực tế.**

### 5.2. Prefix dễ tối ưu hơn trong nhiều hệ thống, nhưng không phải quy tắc tuyệt đối

`(cn=Lan*)` cung cấp phần đầu cố định `Lan`, có thể giúp engine giới hạn ứng viên. Tuy nhiên việc này chỉ nhanh nếu server có index thích hợp và đoạn đó đủ chọn lọc. LDAP backend thường có chiến lược substring index riêng, không nhất thiết dùng một index B-tree giống RDBMS.

`(cn=*Lan*)` không có ràng buộc vị trí đầu nên có thể cần tìm ứng viên chứa đoạn `Lan` ở mọi vị trí; nhưng không được kết luận chắc chắn truy vấn này **luôn full scan**. Nhiều backend hỗ trợ substring index, ví dụ dạng n-gram hoặc index riêng cho `sub`, giúp tối ưu một số trường hợp.

### 5.3. Chỉ mục không miễn phí

Thêm index có thể tăng dung lượng lưu trữ, RAM/cache cần thiết và chi phí cập nhật khi entry thay đổi. Mỗi server có cú pháp cấu hình index khác nhau; ví dụ OpenLDAP `back-mdb` có các loại index `eq`, `pres`, `sub` nhưng cách chọn cần dựa vào schema và truy vấn thực tế.

Một directory có hàng triệu entry không nên lập chỉ mục substring cho *mọi* thuộc tính chỉ để “tìm cho nhanh”. Hãy thống kê filter thường dùng, khối lượng đọc/ghi, độ dài đoạn tìm và kế hoạch vận hành index theo tài liệu của đúng server.

## 6. Thiết kế filter có độ chọn lọc tốt hơn

Giả sử người dùng tìm chuỗi `Lan` trong danh bạ. Filter rộng:

~~~ldap
(cn=*Lan*)
~~~

Nếu hệ thống chỉ quản lý nhân viên trong một OU cụ thể, hãy thu hẹp **search base** và dùng điều kiện nghiệp vụ:

~~~ldap
(&(objectClass=inetOrgPerson)(cn=*Lan*))
~~~

Ví dụ phức hợp theo họ hoặc tên:

~~~ldap
(&(objectClass=inetOrgPerson)(|(cn=Lan*)(sn=Lan*)))
~~~

**Lưu ý:** thêm điều kiện không đảm bảo giảm thời gian tìm kiếm trong mọi server; nó làm rõ tập kết quả mong muốn và có thể giúp engine chọn index/tối ưu hơn. Nếu `objectClass=inetOrgPerson` chiếm gần hết thư mục, filter phụ này ít tạo khác biệt.

### 6.1. Ưu tiên khóa định danh nếu tác vụ cần đúng một người

Khi ứng dụng cần lấy **chính xác** người dùng đăng nhập, hãy truy vấn `uid`, `entryUUID` hoặc khóa định danh đáng tin cậy theo schema thay vì dùng substring trên `cn`.

~~~ldap
(uid=lan)       # Định danh theo thuộc tính nghiệp vụ phù hợp
(cn=*Lan*)      # Tìm kiếm hiển thị, có thể trả nhiều người
~~~

Đừng dùng kết quả “đã tìm thấy entry bằng `cn=*Lan*`” làm bằng chứng xác thực hoặc phân quyền. Spring Security LDAP dùng cơ chế bind/xác thực và mapping authority phù hợp; filter là công cụ truy xuất dữ liệu.

### 6.2. Chọn phạm vi tìm kiếm

| Scope | Ý nghĩa | Ví dụ phù hợp |
| --- | --- | --- |
| `OBJECT` | Chỉ kiểm tra entry tại search base | Đọc đúng entry đã có DN |
| `ONELEVEL` | Chỉ các entry con trực tiếp của base | Một OU nhân viên phẳng |
| `SUBTREE` | Entry ở base và toàn bộ hậu duệ | Người dùng phân bố nhiều OU con |

Nếu nhân viên nằm trực tiếp dưới `ou=people`, `ONELEVEL` có thể tránh quét các nhánh không liên quan. Nếu người dùng được chia theo `ou=engineering`/`ou=hr` dưới `ou=people`, `ONELEVEL` ở `ou=people` sẽ **bỏ sót** họ; cần `SUBTREE` hoặc truy vấn các nhánh cụ thể.

**Full DN và relative DN:** với `ContextSource` đặt base `dc=example,dc=org`, nhiều API Spring LDAP nhận search base **tương đối**, chẳng hạn `ou=people`. Không tự gắn `dc=example,dc=org` lần thứ hai vào tham số đang yêu cầu DN tương đối.

### 6.3. Giảm số thuộc tính và kết quả trả về

Search lấy toàn bộ entry/thuộc tính không cần thiết có thể tăng chi phí mạng, cấp phát object và thời gian map của Java. Chỉ yêu cầu các thuộc tính cần hiển thị, ví dụ `uid` và `cn`.

Khi thiết kế autocomplete, có thể đặt giới hạn số gợi ý và chỉ phát truy vấn khi người dùng đã nhập đủ ký tự; debounce phía UI giúp giảm tần suất gọi LDAP. Các giới hạn này là **biện pháp quản lý tải**, không phải phép bảo đảm server không phải đọc lượng lớn dữ liệu trước khi trả vài kết quả.

## 7. Tạo filter an toàn bằng Spring LDAP

### 7.1. So sánh bằng: `EqualsFilter` tự escape giá trị

Khi tìm đúng `uid`, sử dụng `EqualsFilter`:

~~~java
import java.util.List;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.filter.EqualsFilter;
import org.springframework.stereotype.Service;

@Service
public class EmployeeLookupService {
    private final LdapTemplate ldapTemplate;

    public EmployeeLookupService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<String> findCommonNamesByUid(String uid) {
        EqualsFilter filter = new EqualsFilter("uid", uid);
        return ldapTemplate.search(
            "ou=people",
            filter.encode(),
            (AttributesMapper<String>) attrs ->
                (String) attrs.get("cn").get()
        );
    }
}
~~~

Nếu `uid` đầu vào là `lan*`, `EqualsFilter` encode dấu `*` thành literal phù hợp thay vì biến nó thành wildcard. Phần ví dụ giả định server có thuộc tính `cn` và tài khoản truy vấn có quyền đọc; ứng dụng production nên xử lý thuộc tính thiếu, kết quả không duy nhất và lỗi mạng/permission.

### 7.2. Substring với pattern cố định, do ứng dụng kiểm soát

`LdapQueryBuilder` hỗ trợ cú pháp `like` cho substring search:

~~~java
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;

LdapQuery query = LdapQueryBuilder.query()
    .base("ou=people")
    .where("cn").like("Lan*");

List<String> names = ldapTemplate.search(
    query,
    (AttributesMapper<String>) attrs ->
        (String) attrs.get("cn").get()
);
~~~

Pattern `"Lan*"` ở đây là **hằng do lập trình viên viết**, nên dấu `*` có chủ đích là wildcard. `like(...)` có ngữ nghĩa nhập *pattern*; không đưa thẳng input không tin cậy vào `like(input + "*")` nếu yêu cầu nghiệp vụ là tìm prefix **literal**. Đầu vào có thể chứa các ký tự điều khiển wildcard hoặc filter khác; cần đảm bảo escape và quyền tạo pattern phù hợp với API thực dùng.

### 7.3. Substring prefix từ input: escape **phần dữ liệu** trước, rồi thêm wildcard

Một cách minh họa tách rõ hai thành phần:

~~~java
import javax.naming.directory.SearchControls;
import java.util.List;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapEncoder;

public List<String> suggestNames(
        LdapTemplate ldapTemplate,
        String literalPrefix) {

    if (literalPrefix == null
            || literalPrefix.codePointCount(0, literalPrefix.length()) < 2) {
        throw new IllegalArgumentException("Cần ít nhất 2 ký tự để tìm kiếm");
    }

    // 'cn' và objectClass là tên thuộc tính cố định, do ứng dụng định nghĩa.
    String encodedPrefix = LdapEncoder.filterEncode(literalPrefix);
    String filter = "(&(objectClass=inetOrgPerson)(cn="
            + encodedPrefix + "*))";

    SearchControls controls = new SearchControls();
    controls.setSearchScope(SearchControls.ONELEVEL_SCOPE);
    controls.setCountLimit(50);
    controls.setTimeLimit(2000);
    controls.setReturningAttributes(new String[] {"uid", "cn"});

    return ldapTemplate.search(
        "ou=people",
        filter,
        controls,
        (AttributesMapper<String>) attrs ->
            (String) attrs.get("cn").get()
    );
}
~~~

Trong ví dụ:

- `LdapEncoder.filterEncode(...)` chỉ encode **giá trị literal** đến từ người dùng. Dấu `*` được nối **sau khi encode** là wildcard prefix do ứng dụng chủ động thêm.
- Nếu input là `La*`, phần dữ liệu có thể trở thành `La\2a`, và filter cuối mang ý nghĩa “bắt đầu bằng chuỗi literal `La*`”, không phải “bắt đầu bằng `La` rồi khớp bất cứ gì”.
- `SearchControls.ONELEVEL_SCOPE` đúng **chỉ khi** nhân viên nằm trực tiếp dưới `ou=people`; nếu có OU con, cần đổi scope phù hợp.
- `setCountLimit(50)` yêu cầu giới hạn số entry nhận từ search; `setTimeLimit(2000)` là giới hạn thời gian tìm kiếm theo API JNDI (mili giây). Chúng **không** đảm bảo server chỉ phải kiểm tra tối đa 50 entry hoặc tự tạo query plan rẻ.
- `setReturningAttributes(...)` chỉ lấy các thuộc tính cần thiết. Ví dụ chưa xử lý thuộc tính `cn` vắng mặt hoặc `SizeLimitExceededException`/`TimeLimitExceededException`; cần hoàn thiện theo hợp đồng API của ứng dụng.

**Cảnh báo về kiểm soát đầu vào:** trong thực tế nên kiểm tra thêm độ dài tối đa, dạng ký tự được phép, search rate và quyền truy cập. Tránh “chữa” filter bằng `trim()` hoặc lowercase mọi input mà không có quy định nghiệp vụ: khoảng trắng và case của giá trị thuộc matching rule/schema.

### 7.4. Đừng biến bộ lọc thành chuỗi không có giới hạn

Trong REST API, tránh nhận trực tiếp toàn bộ LDAP filter do khách hàng gửi để truyền cho `LdapTemplate.search(...)`. Nếu thật sự cần “advanced search”, hãy nhận **cấu trúc điều kiện** được whitelist theo các thuộc tính và toán tử cho phép, rồi xây filter có escaping, giới hạn độ phức tạp, số nhánh OR, search scope, thuộc tính trả về và số kết quả.

## 8. Giới hạn kết quả và paging không tự giảm chi phí xử lý filter

Một lời khuyên thường gặp là “thêm paging thì truy vấn `*Lan*` sẽ nhanh”. Cần phân biệt:

1. **Paging** phân chia cách trả kết quả, ví dụ LDAP Simple Paged Results theo RFC 2696, nếu server và client hỗ trợ.
2. **Index và selectivity** quyết định server phải tìm/kiểm tra những ứng viên nào.
3. **Size/time limits** giới hạn công việc hoặc phản hồi theo cơ chế của client/server, có thể dẫn đến kết quả một phần hoặc lỗi giới hạn.

Paging giúp ứng dụng không cần nhận một lần hàng nghìn entry. Nó **không sửa được** filter substring kém chọn lọc. Một số backend vẫn phải thực hiện nhiều bước tìm kiếm để tạo mỗi trang hoặc duy trì trạng thái truy vấn; cần đo hiệu năng trên server thực tế.

Với autocomplete, thường phù hợp hơn nếu chỉ trả **một số ít kết quả**, giới hạn độ dài và tần suất truy vấn, tối ưu substring index khi cần, và không hứa rằng danh sách là “toàn bộ kết quả” khi có giới hạn.

## 9. Tình huống vận hành: tìm tên trong directory lớn

**Bối cảnh:** tổ chức có 500.000 entry nhân viên. API `GET /employees/suggest?q=an` gửi:

~~~ldap
(cn=*an*)
~~~

Giả sử nhiều tên chứa “an”. Dù UI chỉ hiển thị 20 gợi ý, filter có thể tạo tập ứng viên rất lớn, tùy index server. Nếu mỗi lần nhấn phím đều gửi một truy vấn, số request tăng nhanh; những kết nối LDAP dùng cho luồng tìm kiếm có thể làm tăng áp lực lên connection pool và ảnh hưởng tác vụ khác.

### Hướng tối ưu có thứ tự

1. **Xác định yêu cầu:** gợi ý theo **đầu tên**, theo `uid`, theo surname hay “chứa ở mọi vị trí”? Nếu người dùng chấp nhận prefix, đổi từ `(cn=*an*)` sang `(cn=an*)` có thể giảm chi phí trên nhiều hệ thống, nhưng phải đo.
2. **Thu hẹp scope:** chỉ tìm trong `ou=people` hoặc OU liên quan và chọn `ONELEVEL`/`SUBTREE` đúng cấu trúc.
3. **Thêm điều kiện có ý nghĩa:** chỉ các entry đang dùng trong danh bạ theo objectClass/trạng thái nghiệp vụ; không tạo filter OR quá rộng.
4. **Giới hạn output:** trả số thuộc tính tối thiểu và 20–50 kết quả gợi ý; xử lý rõ trường hợp kết quả bị cắt.
5. **Kiểm tra schema và chỉ mục:** xem `SUBSTR` rule của `cn` và index thực tế; thống kê query nào chiếm nhiều CPU/I/O, điều chỉnh index có kiểm soát.
6. **Giảm tần suất:** debounce input, số ký tự tối thiểu, rate limit theo người dùng/ứng dụng; cache có hạn và có kế hoạch làm mới khi phù hợp.
7. **Theo dõi sau thay đổi:** đo thời gian truy vấn, số entry xét/đọc theo log/metrics server khi có, số kết quả và tỷ lệ lỗi/timeout; kiểm tra tác động tới tác vụ cập nhật entry.

### Ví dụ so sánh để đo

| Phương án | Filter | Điều kỳ vọng cần đo |
| --- | --- | --- |
| A — chứa 2 ký tự | `(cn=*an*)` | Có thể trả nhiều entry, ảnh hưởng tải server |
| B — tiền tố 2 ký tự | `(cn=an*)` | Có thể chọn lọc hơn A, tùy dữ liệu/index |
| C — tiền tố dài hơn | `(cn=angu*)` | Thường ít ứng viên hơn B khi dữ liệu phù hợp |
| D — equality định danh | `(uid=anguyen)` | Thuận lợi khi `uid` định danh và có equality index |
| E — chứa + giới hạn nhánh | `(&(objectClass=inetOrgPerson)(cn=*an*))` | Đúng tập đối tượng hơn; lợi ích hiệu năng tùy index |

**Không bịa số benchmark:** thời gian 5 ms/50 ms/500 ms không thể suy ra chỉ từ filter. Hãy chạy nhiều lượt đo trong điều kiện tương đương, kiểm soát cache, tải đồng thời, network, kích thước kết quả và schema; công bố rõ mẫu dữ liệu và cấu hình khi so sánh.

## 10. Lỗi thường gặp và cách xử lý

| Lỗi | Tác hại | Cách xử lý |
| --- | --- | --- |
| Tìm người dùng chính xác bằng `(cn=*name*)` | Trùng tên, kết quả quá rộng, không phù hợp xác thực | Dùng equality trên thuộc tính định danh thích hợp |
| Ghép trực tiếp input vào `(cn=...*)` | LDAP injection hoặc wildcard ngoài ý muốn | Escape literal input, sau đó thêm `*` do ứng dụng kiểm soát |
| Nhầm `(cn=*)` với “chứa một ký tự bất kỳ” | Kết quả rất lớn và ý nghĩa khác | Xem nó là presence filter |
| Cho phép chuỗi trống tạo `(cn=*)` | Khi gõ rỗng có thể tìm gần toàn bộ directory | Chặn prefix quá ngắn/empty và quy định hành vi UI |
| Nghĩ prefix luôn có index và luôn nhanh | Tối ưu sai, phát sinh bottleneck | Xem backend index và đo query plan/metrics thực |
| Nghĩ filter có `*` luôn full scan | Bỏ qua khả năng substring index của server | Đo và kiểm tra cấu hình index |
| Dùng `toLowerCase()` trong Java để tạo search | Sai chuẩn Unicode/matching rule; thay đổi dữ liệu literal | Để server áp dụng rule theo schema |
| Truy vấn `SUBTREE` từ base quá cao | Tập ứng viên lớn, độ trễ cao | Thu hẹp search base/scope theo nghiệp vụ |
| Tin rằng paging sửa được filter kém | Vẫn tốn CPU/I/O trên server | Tối ưu filter, scope và index; paging chỉ quản lý kết quả |
| Lấy mọi thuộc tính của hàng nghìn entry | Dư băng thông và cấp phát bộ nhớ | Chỉ yêu cầu các attribute cần dùng |
| Tăng pooling để che truy vấn chậm | Tạo thêm tải song song, nghẽn LDAP server | Đo và tối ưu truy vấn, giới hạn concurrency hợp lý |
| Dùng LDAP không mã hóa khi gửi thông tin nhạy cảm | Rò rỉ thông tin truy vấn/dữ liệu và credentials | Dùng LDAPS hoặc StartTLS, xác minh chứng chỉ và quản lý secrets |

Đối với hoạt động quản lý nhóm và phân quyền, một truy vấn substring trên `cn` còn đặc biệt nguy hiểm nếu được dùng để “xác định đúng người”: có thể trùng tên, thiếu ổn định khi đổi tên và không chứng minh danh tính. Nên dựa trên DN/định danh đáng tin cậy và cơ chế xác thực phù hợp của Spring Security LDAP.

## 11. Kiểm thử tính đúng đắn và hiệu năng

### 11.1. Tập dữ liệu nhỏ để kiểm tra cú pháp

Trong một LDAP test server có schema cho `cn`, tạo vài entry ví dụ:

~~~ldif
dn: uid=lan,ou=people,dc=example,dc=org
objectClass: inetOrgPerson
uid: lan
cn: Nguyen Lan
sn: Nguyen

dn: uid=lan2,ou=people,dc=example,dc=org
objectClass: inetOrgPerson
uid: lan2
cn: Lan Anh
sn: Anh

dn: uid=star,ou=people,dc=example,dc=org
objectClass: inetOrgPerson
uid: star
cn: Lan*
sn: Star
~~~

Tùy schema/ACL, có thể cần thêm `objectClass`, naming attribute và các thuộc tính bắt buộc. Không giả định LDIF này áp dụng nguyên xi cho mọi server.

| Filter | Điều cần kiểm tra |
| --- | --- |
| `(cn=Lan*)` | Có tìm `Lan Anh`, và `Lan*` theo substring rule không? |
| `(cn=*Lan)` | Có tìm `Nguyen Lan` không? |
| `(cn=*Lan*)` | Có tìm entry chứa `Lan` ở mọi vị trí không? |
| `(cn=Lan\2a)` | Có tìm giá trị literal `Lan*` không? |
| `(cn=*)` | Chọn các entry có `cn`, không cần dựa trên giá trị cụ thể |
| `(uid=lan\2a)` | Không biến dấu sao được escape thành wildcard |
| `(cn=*lan*)` | Kết quả có phụ thuộc caseIgnoreSubstringsMatch của server không? |

### 11.2. Kiểm thử kết nối và chi phí

Dùng embedded LDAP (ví dụ UnboundID) hoặc môi trường thử nghiệm cô lập để kiểm tra **tính đúng đắn**. Để đo hiệu năng có ý nghĩa, cần môi trường đại diện hơn về số entry, chỉ mục, dữ liệu và concurrency.

Nên có các ca:

- Prefix rỗng, 1 ký tự, rất dài, nhiều wildcard literal, dấu ngoặc, dấu gạch chéo ngược, Unicode và khoảng trắng.
- Tìm kiếm ở `ONELEVEL` và `SUBTREE` với OU lồng nhau để phát hiện bỏ sót hoặc tìm quá rộng.
- Thuộc tính `cn` nhiều giá trị, các type có `SUBSTR` khác nhau và type không hỗ trợ substring.
- Tài khoản bind không được đọc một số entry/attribute; phân biệt **không có kết quả** với lỗi ACL hoặc kết quả bị ẩn.
- Size/time limit, timeout kết nối, server trả lỗi, paging, TLS/StartTLS và pooling.
- Cùng filter khi có/không có index thích hợp trong một môi trường kiểm thử cho phép thay đổi index; theo dõi log/metrics server và tốc độ ghi dữ liệu.

**Lưu ý:** chỉ xác minh filter string đúng trong unit test không chứng minh server sẽ trả đúng dữ liệu hoặc truy vấn sẽ nhanh. Hiệu năng phải được xác nhận bằng đo đạc trên triển khai LDAP cụ thể.

## 12. Bài tập vận dụng

1. Một API tìm user chính xác với input `long*`. Tại sao `(uid=long*)` có thể sai? Hãy viết filter để tìm literal `long*`.
2. Phân biệt `(mail=*)` và `(mail=*example.org)` về loại filter và số kết quả kỳ vọng.
3. Trong một directory rất lớn, vì sao `(cn=*a*)` có thể tốn kém dù ứng dụng chỉ lấy 10 kết quả?
4. `(cn=*LAN*)` không khớp một entry có `cn: Nguyen Lan`. Nêu ba yếu tố cần kiểm tra trước khi kết luận dữ liệu sai.
5. Chọn search scope nào nếu người dùng nằm trực tiếp dưới `ou=people`? Nếu có OU con, cần thay đổi gì?
6. Nếu đã thêm index `sub` cho `cn` nhưng truy vấn vẫn chậm, những vấn đề nào ngoài index cần đo?
7. Hãy sửa ý tưởng `like(userInput + "*")` để đầu vào của người dùng luôn được diễn giải là **literal prefix**.

**Gợi ý đáp án:**

1. `*` có nghĩa wildcard; phải escape `(uid=long\2a)` hoặc dùng `EqualsFilter("uid", "long*")`.
2. `(mail=*)` là presence; `(mail=*example.org)` là substring suffix. Cả hai có thể trả rất nhiều entry; cần đo.
3. Đoạn `a` quá ngắn và phổ biến; tập ứng viên/công việc trên server vẫn có thể lớn; giới hạn output không giới hạn được toàn bộ chi phí.
4. Kiểm tra `SUBSTR` matching rule, search base/scope, quyền đọc/ACL, cách lưu giá trị và trạng thái server.
5. `ONELEVEL` nếu chỉ cần con trực tiếp; `SUBTREE` hoặc các nhánh cụ thể nếu cần duyệt OU con.
6. Độ chọn lọc, phạm vi tìm kiếm, cache/I/O, chỉ mục thực sự được dùng, số entry trả về, thuộc tính, concurrency và mạng.
7. Encode `userInput` theo RFC 4515, sau đó **mới** nối dấu `*` wildcard do code kiểm soát; kiểm tra độ dài và tần suất tìm kiếm.

## 13. Ghi nhớ

- `*` có nghĩa **presence** khi toàn bộ phần assertion là `*`; trong substring filter, `*` là dấu phân tách wildcard; `\2a` là dấu sao literal.
- Equality (`(uid=lan)`), prefix (`(cn=Lan*)`) và contains (`(cn=*Lan*)`) là các điều kiện khác nhau và sử dụng matching rule khác nhau.
- Chi phí truy vấn bị chi phối bởi **schema, chỉ mục, độ chọn lọc, search base/scope, số lượng entry và dữ liệu trả về**. Không có quy tắc phổ quát “dấu sao đầu chuỗi luôn quét toàn bộ”.
- Trong Spring LDAP, hãy dùng **`EqualsFilter`** hoặc encode input bằng **`LdapEncoder.filterEncode`** trước khi thêm wildcard có chủ đích. Không chuyển dữ liệu người dùng thành cú pháp filter một cách tùy tiện.
- Hạn chế prefix quá ngắn, giới hạn kết quả/thuộc tính, chọn scope đúng và đo trên LDAP server đại diện. Paging và pooling hỗ trợ vận hành nhưng không thay thế tối ưu filter.

### Tài liệu tham khảo chính thức

- [RFC 4515 — LDAP: String Representation of Search Filters](https://www.rfc-editor.org/rfc/rfc4515)
- [RFC 4511 — LDAP: The Protocol (search request, filter, scope, limits)](https://www.rfc-editor.org/rfc/rfc4511)
- [RFC 4517 — LDAP: Syntaxes and Matching Rules](https://www.rfc-editor.org/rfc/rfc4517)
- [RFC 4518 — LDAP: Internationalized String Preparation](https://www.rfc-editor.org/rfc/rfc4518)
- [RFC 2696 — LDAP Control Extension for Simple Paged Results Manipulation](https://www.rfc-editor.org/rfc/rfc2696)
- [Spring LDAP Reference — Searching / LdapTemplate](https://docs.spring.io/spring-ldap/reference/)
- [OpenLDAP Administrator's Guide — Database indexes](https://www.openldap.org/doc/admin26/tuning.html)
