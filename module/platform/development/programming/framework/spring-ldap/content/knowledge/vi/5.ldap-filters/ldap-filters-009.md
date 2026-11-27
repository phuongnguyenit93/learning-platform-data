# Không ghép chuỗi filter từ dữ liệu chưa được encode

Một ứng dụng Java có thể dùng **Spring LDAP** để tra cứu tài khoản trong danh bạ LDAP bằng `LdapTemplate`, `LdapClient` hoặc một lớp DAO dựa trên LDAP ODM. Khi tìm theo tên đăng nhập, email hay nhóm, lập trình viên thường cần ghép nhiều điều kiện vào **LDAP search filter**. Nếu đem dữ liệu từ HTTP request, biểu mẫu hoặc hệ thống bên ngoài **nối trực tiếp vào chuỗi filter**, dữ liệu đó có thể bị diễn giải thành **toán tử hoặc cấu trúc cú pháp LDAP**. Đây là nguồn gốc của **LDAP filter injection**.

Quy tắc trọng tâm của bài thuộc chương **Filter LDAP** là:

> **Cấu trúc truy vấn phải do ứng dụng quyết định; dữ liệu chưa được tin cậy phải được xử lý như giá trị cần so khớp, không được phép trở thành cú pháp filter.**

Bài học giải thích vì sao cần quy tắc này, cách biểu diễn an toàn bằng API của Spring LDAP, các ký tự cần escape theo RFC 4515, những trường hợp có wildcard và cách kiểm thử để tránh tìm nhầm entry, lộ dữ liệu hoặc gây truy vấn quá rộng.

## 1. Đặt filter đúng vị trí trong thao tác LDAP

Một yêu cầu tìm kiếm LDAP thường xác định các thành phần độc lập:

| Thành phần | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Base DN | `ou=people,dc=example,dc=org` | Bắt đầu tìm tại nhánh nào |
| Search scope | `SUBTREE` | Tìm trong base và các entry con |
| Filter | `(&(objectClass=inetOrgPerson)(uid=linh))` | Entry nào được coi là phù hợp |
| Requested attributes | `uid`, `cn`, `mail` | Thuộc tính muốn nhận |
| Giới hạn | Số lượng kết quả, thời gian | Kiểm soát chi phí và phạm vi truy vấn |

Một filter gồm những phép kiểm tra có dấu ngoặc:

~~~ldap
(uid=linh)
(&(objectClass=inetOrgPerson)(uid=linh))
(|(uid=linh)(uid=mai))
(!(employeeType=contractor))
~~~

Các toán tử logic `&`, `|` và `!` lần lượt biểu diễn AND, OR và NOT; mỗi filter con phải có ngoặc riêng. Ký tự `*` có thể là wildcard trong phép so khớp chuỗi con hoặc được dùng trong điều kiện hiện diện `(mail=*)`.

**Sự khác biệt quan trọng:** base DN cho biết tìm **ở đâu**, filter cho biết entry nào **khớp**, tài khoản kết nối và ACL quyết định dữ liệu nào **được phép đọc**. Escape filter không thay thế quyền truy cập, TLS, giới hạn truy vấn hay xác thực người dùng.

## 2. Vì sao nối chuỗi trực tiếp nguy hiểm?

Hãy xét ứng dụng cung cấp endpoint tìm nhân viên theo `uid`:

~~~java
// KHÔNG AN TOÀN: uid do người gọi HTTP cung cấp.
public String unsafeFilter(String uid) {
    return "(&(objectClass=inetOrgPerson)(uid=" + uid + "))";
}
~~~

Với đầu vào hợp lệ `linh`, kết quả trông đúng:

~~~ldap
(&(objectClass=inetOrgPerson)(uid=linh))
~~~

Nhưng nếu đầu vào là:

~~~text
*)(uid=*
~~~

thì chuỗi sau khi nối trở thành:

~~~ldap
(&(objectClass=inetOrgPerson)(uid=*)(uid=*))
~~~

Trước khi bị thay đổi, ứng dụng muốn **so khớp chính xác một uid**. Sau khi bị thay đổi, filter lại yêu cầu entry thuộc `inetOrgPerson` **có thuộc tính uid**, thường khớp rất nhiều tài khoản. Dấu `*` trở thành điều kiện hiện diện, còn `)` và `(` làm thay đổi ranh giới các điều kiện.

Ví dụ này cho thấy kiểu tấn công làm thay đổi **logic tìm kiếm**. Mức độ ảnh hưởng thực tế phụ thuộc base DN, search scope, ACL, schema và giới hạn server. Tấn công không mặc nhiên vượt qua ACL; tuy nhiên một truy vấn rộng vẫn có thể tiết lộ dữ liệu mà tài khoản ứng dụng đã được phép đọc hoặc tiêu tốn tài nguyên.

Sơ đồ mô tả đường đi của lỗi:

~~~mermaid
flowchart TD
    A["HTTP request: uid do người dùng nhập"] --> B{"Ứng dụng dựng LDAP filter"}
    B -->|"Nối chuỗi trực tiếp"| C["Input chèn dấu ngoặc / wildcard"]
    C --> D["Cấu trúc filter bị thay đổi"]
    D --> E["Truy vấn quá rộng hoặc sai ý định"]
    B -->|"Filter builder và escape giá trị"| F["Giá trị là dữ liệu literal"]
    F --> G["Cấu trúc filter do ứng dụng kiểm soát"]
    G --> H["LDAP server áp matching rule và ACL"]
~~~

**Không cần có mã Java độc hại để xảy ra injection.** Vấn đề nằm ở việc dữ liệu đầu vào được đưa vào một ngôn ngữ truy vấn có cú pháp riêng mà không qua bước mã hóa thích hợp.

## 3. Chuỗi filter theo RFC 4515 và các ký tự phải escape

RFC 4515 mô tả cách biểu diễn LDAP search filter thành chuỗi. Trong **assertion value** (giá trị cần so khớp), một số ký tự có ý nghĩa cú pháp và cần được biểu diễn bằng `\HH`, trong đó `HH` là hai chữ số thập lục phân của một byte.

| Ký tự literal trong giá trị | Cách biểu diễn trong filter | Nếu để nguyên có thể xảy ra |
| --- | --- | --- |
| `*` | `\2a` | Bị coi là wildcard hoặc presence |
| `(` | `\28` | Bị coi là dấu mở filter |
| `)` | `\29` | Bị coi là dấu đóng filter |
| `\` | `\5c` | Bị coi là ký tự bắt đầu escape |
| Byte NUL (`0x00`) | `\00` | Không được biểu diễn trực tiếp trong chuỗi filter hợp lệ |

Ví dụ các filter có giá trị literal:

~~~ldap
(uid=an\2ab)
(cn=Ha \28Support\29)
(description=path\5cdev)
~~~

Ba filter này lần lượt tìm giá trị `uid` là `an*b`, `cn` là `Ha (Support)`, và `description` chứa dấu gạch chéo ngược giữa `path` và `dev`. Dấu sao trong `an\2ab` **không phải wildcard**.

Điều quan trọng khi viết Java: ký hiệu chuỗi Java và ký hiệu filter LDAP là hai lớp cú pháp. Để có một dấu `\` trong chuỗi Java thông thường, mã nguồn phải escape thành `\\`. Chẳng hạn:

~~~java
// Chuỗi Java chứa text LDAP: (uid=an\2ab)
String literalStarFilter = "(uid=an\\2ab)";
~~~

Không nên tự viết các chuỗi escape động bằng những phép `replace` rời rạc. Nếu quên một ký tự hoặc áp dụng sai thứ tự, filter vẫn có thể bị thay đổi ý nghĩa. **Ưu tiên thư viện dựng filter** để không phải tự mã hóa từng trường hợp.

### 3.1. Unicode, byte và giá trị nhị phân

RFC 4515 quy định dạng `\HH` theo **octet** (byte). Khi gặp ký tự Unicode, ứng dụng Java cần sử dụng encoding phù hợp, thông thường là UTF-8, để chuyển đổi đúng giá trị. Nhiều ký tự Unicode hợp lệ có thể xuất hiện trực tiếp trong chuỗi filter UTF-8; không cần biến mọi chữ có dấu thành ký hiệu `\HH` bằng tay.

Nếu dữ liệu chứa byte không tạo thành chuỗi UTF-8 hợp lệ, dạng biểu diễn phải mã hóa các byte cần thiết. Vì thế không nên xây thuật toán escape bằng cách lấy mỗi ký tự Java rồi coi mã ký tự đó chính là một byte LDAP.

Ví dụ tên người `Đỗ Linh` cần được xử lý như **giá trị Unicode**, với cách so khớp thực tế do schema/matching rule của thuộc tính `cn` quyết định. Escape an toàn và so khớp không phân biệt chữ hoa/thường là **hai vấn đề khác nhau**.

### 3.2. Escape của filter khác escape của DN

Cả filter và DN đều dùng dấu gạch chéo ngược trong biểu diễn chuỗi, nhưng có **quy tắc riêng**:

| Mục đích | Ví dụ | Quy tắc |
| --- | --- | --- |
| Giá trị filter chứa dấu `*` | `(uid=an\2ab)` | RFC 4515 |
| Giá trị RDN trong DN chứa dấu phẩy | `cn=Nguyen\, Linh,ou=people` | RFC 4514 |
| Giá trị filter chứa dấu phẩy | `(cn=Nguyen, Linh)` | Dấu phẩy bình thường không phải dấu phân cách filter |

Nếu ứng dụng nhận `uid` rồi muốn **dựng DN**, hãy dùng `LdapNameBuilder`; nếu muốn **dựng search filter**, hãy dùng API filter hoặc query builder. Không dùng bộ escape DN để thay bộ escape filter, hoặc ngược lại.

## 4. Giải pháp ưu tiên: `LdapQueryBuilder` với tham số giá trị

Spring LDAP hỗ trợ dựng truy vấn theo cấu trúc, không cần tự lắp dấu ngoặc và toán tử từ input. Ví dụ tìm nhân viên theo `uid`:

~~~java
import java.util.List;
import javax.naming.directory.Attribute;

import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;
import org.springframework.ldap.query.SearchScope;

public class EmployeeDirectoryService {
    private final LdapTemplate ldapTemplate;

    public EmployeeDirectoryService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<String> findEmailsByUid(String uid) {
        if (uid == null || uid.isBlank()) {
            throw new IllegalArgumentException("uid không được rỗng");
        }

        LdapQuery query = LdapQueryBuilder.query()
                .base("ou=people")
                .searchScope(SearchScope.SUBTREE)
                .where("objectClass").is("inetOrgPerson")
                .and("uid").is(uid);

        return ldapTemplate.search(
                query,
                (AttributesMapper<String>) attrs -> {
                    Attribute mail = attrs.get("mail");
                    return mail == null ? null : (String) mail.get();
                });
    }
}
~~~

Giả sử `LdapContextSource` có base `dc=example,dc=org`, `ou=people` là **base DN tương đối** của truy vấn. Tên thuộc tính `uid` được ứng dụng cố định; `uid` do người dùng nhập được đưa vào `.is(uid)` để hình thành giá trị assertion của điều kiện bằng.

Cách viết này có những lợi ích:

1. **Tách cấu trúc khỏi dữ liệu:** dấu ngoặc, toán tử AND và tên thuộc tính do code quyết định.
2. **Mã hóa giá trị:** API query builder xử lý escaping khi tạo biểu thức tìm kiếm.
3. **Dễ kiểm thử:** có thể kiểm tra giá trị đặc biệt không biến thành toán tử khác.
4. **Dễ giới hạn vùng tìm:** base và scope được thể hiện riêng với filter.

Đoạn code tập trung vào truy vấn: ứng dụng thực tế cần xử lý kết quả trùng định danh, thuộc tính thiếu, quyền đọc, lỗi TLS/referral/timeout và yêu cầu riêng về số lượng kết quả. Không xem `null` do thuộc tính vắng mặt là bằng chứng LDAP server đã trả dữ liệu đầy đủ.

**Cần phân biệt `.is(value)` với các API mô tả substring hoặc wildcard.** Nếu nghiệp vụ muốn khớp `uid` chính xác, hãy dùng equality. Không thay thành một toán tử kiểu “like” vì thuận tiện nếu đầu vào chưa được kiểm soát wildcard.

## 5. Dựng filter có điều kiện bằng `EqualsFilter` và `AndFilter`

Khi ứng dụng có nhiều điều kiện động, dùng bộ tạo filter của Spring LDAP:

~~~java
import org.springframework.ldap.filter.AndFilter;
import org.springframework.ldap.filter.EqualsFilter;

public final class EmployeeFilters {
    private EmployeeFilters() {}

    public static String exactUid(String uid) {
        if (uid == null || uid.isBlank()) {
            throw new IllegalArgumentException("uid không hợp lệ");
        }

        AndFilter filter = new AndFilter();
        filter.and(new EqualsFilter("objectClass", "inetOrgPerson"));
        filter.and(new EqualsFilter("uid", uid));

        return filter.encode();
    }
}
~~~

Với đầu vào tấn công `*)(uid=*`, mục tiêu là filter có **hai điều kiện do ứng dụng tạo** và giá trị thứ hai là một chuỗi literal:

~~~ldap
(&(objectClass=inetOrgPerson)(uid=\2a\29\28uid=\2a))
~~~

Đây là cách biểu diễn minh họa (chữ số hex có thể viết hoa hoặc thường tương đương). Giá trị chứa dấu sao, ngoặc mở và ngoặc đóng đã được escape, nên không thể tự tạo thêm điều kiện `(uid=*)`.

Trước khi đưa vào triển khai, xác minh phiên bản Spring LDAP đang dùng và kiểm thử đầu vào có ký tự đặc biệt. Điều quan trọng là **tính bất biến của cấu trúc filter và ý nghĩa literal của giá trị**, không phải so khớp chuỗi encoded y hệt từng chữ hoa/thường trong mã hex.

### 5.1. Ghép OR cho tập giá trị động

Giả sử ứng dụng tìm một danh sách `uid` do người dùng chọn. Không nối chuỗi bằng vòng lặp:

~~~java
// Không an toàn và khó xử lý input chứa dấu ngoặc.
String filter = "(|";
for (String uid : requestedUids) {
    filter += "(uid=" + uid + ")";
}
filter += ")";
~~~

Dùng `OrFilter` với từng `EqualsFilter`:

~~~java
import java.util.Collection;
import org.springframework.ldap.filter.AndFilter;
import org.springframework.ldap.filter.EqualsFilter;
import org.springframework.ldap.filter.OrFilter;

public final class EmployeeBatchFilter {
    private EmployeeBatchFilter() {}

    public static String exactUids(Collection<String> uids) {
        if (uids == null || uids.isEmpty() || uids.size() > 20) {
            throw new IllegalArgumentException("Cần từ 1 đến 20 uid");
        }

        OrFilter anyUid = new OrFilter();
        for (String uid : uids) {
            if (uid == null || uid.isBlank() || uid.length() > 64) {
                throw new IllegalArgumentException("uid không hợp lệ");
            }
            anyUid.or(new EqualsFilter("uid", uid));
        }

        AndFilter result = new AndFilter();
        result.and(new EqualsFilter("objectClass", "inetOrgPerson"));
        result.and(anyUid);
        return result.encode();
    }
}
~~~

Tập giá trị vẫn do client chọn, nhưng **số nhánh, độ dài giá trị, tên thuộc tính và cách escape** đều được code kiểm soát. Giới hạn 20 phần tử và 64 ký tự chỉ là chính sách minh họa; tùy nhu cầu thực tế có thể đặt giá trị khác. Trường hợp đầu vào trống cần quyết định theo nghiệp vụ; **không mặc định biến “không có uid nào” thành filter khớp mọi tài khoản**.

### 5.2. Khi field tìm kiếm cũng do người dùng chọn

Một ứng dụng có thể cho phép chọn tìm theo `uid`, `mail` hoặc `cn`. Khi đó không cho người dùng gửi **tên thuộc tính LDAP tùy ý** rồi ghép vào filter. Escaping **giá trị** không bảo vệ các phần khác của cú pháp như tên thuộc tính và matching rule.

Dùng tập cho phép cố định:

~~~java
import org.springframework.ldap.filter.EqualsFilter;

public enum EmployeeSearchField {
    UID("uid"),
    EMAIL("mail"),
    NAME("cn");

    private final String ldapAttribute;

    EmployeeSearchField(String ldapAttribute) {
        this.ldapAttribute = ldapAttribute;
    }

    public String exactMatch(String userValue) {
        if (userValue == null || userValue.isBlank()) {
            throw new IllegalArgumentException("Giá trị tìm kiếm không hợp lệ");
        }
        return new EqualsFilter(ldapAttribute, userValue).encode();
    }
}
~~~

Controller ánh xạ một lựa chọn nghiệp vụ hợp lệ sang enum. Người dùng không thể tự quyết định tìm theo `userPassword`, thêm matching rule lạ hoặc sửa cấu trúc filter chỉ bằng cách gửi một chuỗi tên field.

## 6. Wildcard có chủ đích: xử lý khác equality

Không phải dấu sao nào cũng là lỗi. LDAP có cú pháp substring filter, chẳng hạn:

~~~ldap
(cn=Lin*)
(cn=*Nguyen)
(mail=*@example.org)
~~~

Ba filter trên lần lượt mô tả **bắt đầu bằng**, **kết thúc bằng** và **có hậu tố**. Dấu `*` ở đây do ứng dụng cố ý đưa vào cấu trúc truy vấn.

Tuy nhiên, nếu trang tìm kiếm cho người dùng nhập tiền tố `Lin`, không nên dựng:

~~~java
// Không an toàn: input chưa mã hóa được đặt trước wildcard.
String filter = "(cn=" + userPrefix + "*)";
~~~

Nếu `userPrefix` chứa `*` hoặc dấu ngoặc, ý nghĩa filter thay đổi. Một thiết kế an toàn cần tách:

- **Giá trị tiền tố** từ request: được escape theo RFC 4515 và xem như literal.
- **Một wildcard cuối**: do ứng dụng quyết định, không lấy từ request.
- **Tên thuộc tính và phần còn lại của filter**: cấu trúc cố định hoặc lấy từ allowlist.

Dạng logic mong muốn:

~~~text
filter = "(cn=" + escapeFilterAssertionValue(userPrefix) + "*)"
~~~

Dòng trên là **giả mã để giải thích ranh giới**; `escapeFilterAssertionValue` tượng trưng cho API encode giá trị đúng RFC 4515, **không phải một hàm Java có sẵn để sao chép**. Ưu tiên API tạo substring filter của phiên bản thư viện đang dùng và kiểm thử cách API xử lý dấu `*` trong input.

Ví dụ khi người dùng nhập `Li*n`, chương trình muốn tìm tên bắt đầu bằng chuỗi literal `Li*n`, thì biểu thức mong đợi về mặt ý nghĩa là:

~~~ldap
(cn=Li\2an*)
~~~

Dấu sao **giữa** `Li` và `n` là literal (`\2a`); dấu sao **cuối** là wildcard do ứng dụng thêm. Hai dấu sao không được có cùng cách xử lý.

**Một quy tắc nghiệp vụ cần ghi rõ:** nếu ứng dụng cho phép người dùng tự nhập cú pháp wildcard/filter hoàn chỉnh (chẳng hạn một công cụ LDAP admin), đây là chức năng có quyền hạn khác hẳn tìm kiếm thông thường. Cần authorization, giới hạn base/scope, quota và đánh giá riêng, không áp dụng thiết kế đó cho input của người dùng cuối.

## 7. Vì sao “lọc ký tự nguy hiểm” vẫn chưa đủ?

Một số cách sửa tạm nhìn có vẻ tiện nhưng không đảm bảo đúng:

| Cách làm | Vấn đề |
| --- | --- |
| Xóa toàn bộ `*`, `(` và `)` khỏi input | Làm thay đổi dữ liệu người dùng; bỏ sót dấu `\`, NUL và trường hợp encoding khác |
| Tự `replace("*", "\\2a")` rồi ghép chuỗi | Dễ xử lý thiếu ký tự hoặc escape lặp; khó đảm bảo Unicode/byte |
| Kiểm tra `input.contains("uid=")` | Không kiểm soát được cấu trúc filter lồng nhau |
| URL-encode hoặc HTML-escape input | Cú pháp URL/HTML khác cú pháp LDAP filter |
| Chỉ dùng regex xác nhận “không có dấu ngoặc” | Có thể quá hạn chế giá trị hợp lệ, vẫn không kiểm soát attribute/base/scope |
| Escape toàn bộ chuỗi filter sau khi ghép xong | Có thể biến cả toán tử và dấu ngoặc hợp lệ thành literal, làm hỏng truy vấn |
| Bật TLS rồi tiếp tục nối chuỗi filter | TLS bảo vệ đường truyền, không sửa lỗi injection trong ứng dụng |

**Validation và escaping hỗ trợ nhau nhưng không thay thế nhau.** Validation kiểm soát độ dài, định dạng nghiệp vụ và tài nguyên. Escaping giữ đúng nghĩa literal của dữ liệu trong cú pháp filter. Authorization và ACL kiểm soát người nào được xem dữ liệu nào.

### 7.1. Tránh double encoding

Giá trị đầu vào `an*b` muốn tìm theo equality cần biểu diễn trong filter là `an\2ab`. Nếu bạn **escape sẵn** giá trị rồi tiếp tục đưa chuỗi đã encode vào `EqualsFilter`, builder có thể escape thêm dấu `\` thành `\5c`. Khi đó server nhận một giá trị literal chứa ký tự backslash và các chữ số, không còn là `an*b`.

Thói quen nên dùng:

1. Giữ `uid` ở dạng **giá trị Java nguyên bản** sau khi đã kiểm tra điều kiện nghiệp vụ.
2. Truyền giá trị nguyên bản trực tiếp vào `new EqualsFilter("uid", uid)` hoặc `.where("uid").is(uid)`.
3. Chỉ xem `encode()` là biểu diễn cuối cùng của filter khi API yêu cầu chuỗi.
4. Không gọi lại một bộ encode khác trên phần giá trị đã được builder xử lý.

Nếu buộc phải dùng API chỉ nhận filter raw string, hãy kiểm soát cấu trúc thật chặt và dùng đúng hàm escape của thư viện cho từng **assertion value** đúng một lần; nên bọc logic đó trong một thành phần chung có kiểm thử. Hạn chế tự tạo filter raw string ở nhiều nơi trong codebase.

## 8. Filter được escape vẫn cần ranh giới an toàn khác

Giả sử người dùng nhập một `uid` hợp lệ và builder tạo filter hoàn toàn đúng. Ứng dụng vẫn có thể có những vấn đề sau:

- **Base hoặc scope quá rộng:** truy vấn dưới toàn bộ `dc=example,dc=org` thay vì `ou=people`.
- **Thuộc tính nhạy cảm:** yêu cầu trả về dữ liệu mà ứng dụng không cần, hoặc tài khoản dịch vụ có quyền đọc quá rộng.
- **Không giới hạn số lượng:** OR filter với nhiều điều kiện hoặc substring rộng có thể gây tải lớn.
- **Schema/matching rule không như kỳ vọng:** thuộc tính đa trị, case-insensitive matching và normalization có thể làm kết quả khác cách so sánh chuỗi Java.
- **Alias hoặc referral:** server có thể chuyển hướng hoặc trả kết quả chưa đầy đủ; xử lý referral cần chính sách tin cậy riêng.
- **Lỗi xác thực và phân quyền:** search thấy tài khoản không đồng nghĩa người gọi đã xác thực hoặc có quyền đọc/chỉnh sửa tài khoản đó.

Một đường đi phù hợp thường là:

~~~mermaid
flowchart TD
    A["Nhận yêu cầu từ người dùng"] --> B["Xác thực người gọi và kiểm tra quyền"]
    B --> C["Validation: loại yêu cầu, độ dài, số giá trị"]
    C --> D["Chọn base/scope/field từ cấu hình cho phép"]
    D --> E["Dựng filter bằng builder, encode assertion value"]
    E --> F["Search LDAP qua TLS và tài khoản ít quyền"]
    F --> G["Giới hạn kết quả, xử lý lỗi và partial result"]
    G --> H["Chỉ trả về thuộc tính được phép"]
~~~

Trong Spring LDAP, `ContextSource` thường cấu hình endpoint, base DN và danh tính kết nối; `LdapTemplate` hoặc `LdapClient` thực hiện truy vấn. Việc có thêm LDAP ODM để ánh xạ entry sang object **không loại bỏ** yêu cầu xây filter an toàn trước khi tìm kiếm.

Cần đặt timeout, giới hạn kích thước kết quả, giới hạn số điều kiện trong OR filter và sử dụng TLS có xác minh chứng chỉ. Pooling phải tôn trọng ngữ cảnh kết nối và danh tính bind; không dùng kết nối hoặc thông tin đăng nhập của người này tùy tiện cho người khác. Không đưa mật khẩu hay dữ liệu cá nhân nhạy cảm vào log.

## 9. Ví dụ thiết kế API tìm kiếm nhân viên

**Yêu cầu:** API nhận một `uid` từ người dùng có quyền tra cứu danh bạ nội bộ, trả email của tài khoản đó nếu tồn tại. Dữ liệu LDAP nằm dưới `ou=people,dc=example,dc=org`.

**Thiết kế đề xuất:**

1. Controller kiểm tra người gọi có quyền tra cứu, không nhận filter raw từ HTTP body/query.
2. Service nhận `uid`, kiểm tra giới hạn chiều dài và từ chối giá trị không phù hợp chính sách ứng dụng.
3. Service dựng một query có base `ou=people`, scope phù hợp, điều kiện `objectClass=inetOrgPerson` và `uid=...` qua builder.
4. `LdapTemplate` gửi yêu cầu bằng danh tính tra cứu chỉ có quyền cần thiết trên kênh TLS hợp lệ.
5. Service xử lý **không tìm thấy**, **nhiều kết quả bất thường**, **không đủ quyền**, **partial result** và **lỗi hạ tầng** thành những trạng thái khác nhau.
6. API chỉ trả `uid` và `mail` khi người gọi được phép; không trả toàn bộ attributes hoặc mật khẩu/metadata nhạy cảm.

Không cho người dùng truyền trực tiếp những trường như `filter`, `baseDn`, `scope` hoặc danh sách thuộc tính tùy ý. Nếu sản phẩm cần tìm kiếm nâng cao, định nghĩa một **search specification** có cấu trúc, chẳng hạn:

~~~json
{
  "field": "EMAIL",
  "operator": "EXACT",
  "value": "linh@example.org"
}
~~~

Từ đặc tả đó, backend chọn `mail`, toán tử equality và base cố định; `value` vẫn được builder encode. API dạng cấu trúc giúp thực thi đúng danh sách phép tìm kiếm được hỗ trợ và tránh việc client tự nhập ngôn ngữ filter LDAP.

## 10. Kiểm thử hành vi, không chỉ nhìn chuỗi

Có thể kiểm tra builder ở mức unit test, nhưng cần test tích hợp để biết LDAP server thực sự đánh giá filter như mong đợi. Dữ liệu mẫu nên gồm các entry như sau:

~~~ldif
dn: uid=linh,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: linh
cn: Linh Nguyen
sn: Nguyen
mail: linh@example.org

dn: uid=mai,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: mai
cn: Mai Tran
sn: Tran
mail: mai@example.org
~~~

Giả sử các entry cha đã tồn tại và LDAP server thử nghiệm hỗ trợ schema này. Hãy chạy truy vấn với cùng base, scope, tài khoản bind và các thuộc tính yêu cầu để phép so sánh có ý nghĩa.

| Input đưa vào `EqualsFilter("uid", input)` | Giá trị filter nên mang ý nghĩa | Kết quả trên dữ liệu mẫu |
| --- | --- | --- |
| `linh` | So khớp đúng `linh` | Linh |
| `mai` | So khớp đúng `mai` | Mai |
| `an*b` | Dấu sao là literal `\2a` | Không có entry |
| `a(b)` | Ngoặc là literal `\28`, `\29` | Không có entry |
| `a\b` | Backslash là literal `\5c` | Không có entry |
| `*)(uid=*` | Toàn bộ chuỗi là **một giá trị**, không chèn thêm điều kiện | Không có entry |
| `linh@example.org` | Equality theo `uid`, không tự đổi thành filter `mail` | Không có entry |

Các ca kiểm thử cần xác nhận **mức độ truy vấn bị mở rộng**: với payload tấn công, kết quả không được bất ngờ trả về cả Linh và Mai. Trên server thử nghiệm, có thể thêm một entry có dấu sao literal trong giá trị thuộc tính cho phép để khẳng định builder vẫn tìm được ký tự thật khi được escape.

### 10.1. Unit test cho phần dựng filter

Ví dụ dùng JUnit 5 để kiểm tra filter sinh ra có hai điều kiện cố định và đầu vào đặc biệt không giữ vai trò dấu ngoặc/wildcard:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;

class EmployeeFiltersTest {
    @Test
    void ordinaryUidPreservesExpectedFilterStructure() {
        assertEquals(
                "(&(objectClass=inetOrgPerson)(uid=linh))",
                EmployeeFilters.exactUid("linh"));
    }

    @Test
    void specialCharactersAreEncodedAsData() {
        String filter = EmployeeFilters.exactUid("*)(uid=*");

        assertTrue(filter.contains("uid="));
        assertTrue(filter.contains("\\2a"));
        assertTrue(filter.contains("\\28"));
        assertTrue(filter.contains("\\29"));
    }
}
~~~

Các assertion này minh họa một kiểu kiểm tra, không thay thế việc xem thực tế thư viện phiên bản đang dùng có phát mã hex hoa/thường khác nhau hay không. Trong dự án thật nên xác nhận đúng semantics, không phụ thuộc tùy tiện vào cách định dạng nếu các dạng escape là tương đương.

**Quan trọng:** một unit test nhìn chuỗi không chứng minh filter đã đúng quyền đọc, tính duy nhất của kết quả, matching rule hoặc cách LDAP server xử lý. Kiểm thử tích hợp với server phù hợp là bước cần thiết, đặc biệt khi ứng dụng có xác thực, referral và ACL.

### 10.2. Các tình huống âm cần kiểm tra

Ngoài bảng trên, thử:

- Input `null`, rỗng hoặc quá dài: service từ chối theo chính sách; không tự chuyển thành `(uid=*)`.
- Danh sách OR quá lớn: chặn từ tầng API trước khi tạo truy vấn gây tải lớn.
- Base DN hoặc tên thuộc tính được gửi từ client: phải bị bỏ qua hoặc từ chối nếu không thuộc allowlist.
- Phép substring có wildcard: ký tự `*` trong dữ liệu cần giữ literal; chỉ wildcard do ứng dụng chủ động tạo mới có ý nghĩa cấu trúc.
- Tài khoản thiếu quyền, kết nối TLS lỗi, referral hoặc timeout: báo đúng tình huống, không giả làm “không tìm thấy”.
- Filter khớp nhiều entry trong trường hợp nghiệp vụ yêu cầu duy nhất: xử lý rõ ràng, không mặc định chọn phần tử đầu tiên.
- Input Unicode: kết quả mã hóa và tìm kiếm theo đúng schema; không làm hỏng chuỗi có dấu.

Các bài kiểm thử về cách server thực thi filter nên chạy trên môi trường cô lập với dữ liệu mẫu, tránh query diện rộng trên thư mục sản xuất.

## 11. Lỗi thường gặp khi sửa LDAP injection

| Triệu chứng | Khả năng nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| Dấu `*` trong input làm trả quá nhiều entry | Nối input vào filter hoặc dùng substring ngoài ý định | Dùng equality builder; chỉ bật wildcard khi được yêu cầu |
| Giá trị chứa dấu `\` tìm không ra dù entry có thật | Escape thiếu hoặc escape hai lần | Truyền giá trị nguyên bản cho builder, kiểm tra phần encode cuối |
| Đổi từ nối chuỗi sang builder nhưng vẫn có thể tìm thuộc tính nhạy cảm | Cho phép client chọn attribute không giới hạn | Dùng enum/allowlist các trường tra cứu |
| Filter không parse được | Ngoặc lồng sai, trộn cú pháp DN/filter, tự ghép OR | Dùng `AndFilter`/`OrFilter`, xác minh filter được encode |
| Tất cả input đều trả danh sách rỗng | Base/scope sai, matching rule hoặc quyền không phù hợp | Kiểm tra từng thành phần SearchRequest |
| `(&(uid=linh)(...))` vẫn trả quá nhiều dữ liệu cá nhân | Requested attributes hoặc ACL quá rộng | Giảm thuộc tính trả về, kiểm tra quyền trước khi đáp ứng |
| Search chậm bất thường | Substring rộng, OR quá lớn, không có index | Giới hạn base/scope, số nhánh và timeout; xem chỉ mục server |
| Mã trả “không tìm thấy” khi server lỗi | Bắt mọi ngoại lệ rồi trả list rỗng | Phân biệt lỗi mạng, referral, quyền và trạng thái dữ liệu |

Một filter có escaping đúng **không đồng nghĩa** ứng dụng an toàn hoàn toàn. Cần xem xét nó trong cả đường đi của dữ liệu: kiểm tra đầu vào, lựa chọn field, authorization, kết nối và cách trả kết quả.

## 12. Câu hỏi tự đánh giá

**Câu 1.** Vì sao đoạn `"(uid=" + userInput + ")"` có rủi ro dù chỉ tìm theo một thuộc tính?

**Đáp án:** Vì các ký tự như `*`, `(` và `)` trong `userInput` có thể trở thành cú pháp filter. Người dùng có thể thay đổi logic so khớp thay vì chỉ cung cấp giá trị cần tìm.

**Câu 2.** Người dùng muốn tìm giá trị `uid` thật sự là `an*b`. Filter nào thể hiện equality với dấu sao literal?

**Đáp án:** `(uid=an\2ab)`. Nếu viết `(uid=an*b)`, dấu sao là wildcard của phép tìm chuỗi con.

**Câu 3.** Trước khi truyền `uid` vào `new EqualsFilter("uid", uid)` có nên tự thay `*` thành `\2a` không?

**Đáp án:** Không. Hãy truyền **giá trị nguyên bản** cho builder; builder chịu trách nhiệm encode. Escape trước rồi lại được builder encode có thể khiến dấu gạch chéo ngược trở thành literal và truy vấn không còn đúng.

**Câu 4.** Dùng filter builder rồi có thể cho client chọn tùy ý `baseDn`, `scope`, `attribute` và matching rule không?

**Đáp án:** Không. Builder bảo vệ giá trị assertion, còn tên thuộc tính, base, scope và matching rule là phần cấu trúc/phạm vi phải được ứng dụng giới hạn theo nghiệp vụ và quyền truy cập.

**Câu 5.** Muốn tìm tên bắt đầu bằng một tiền tố do người dùng cung cấp, có nên nối trực tiếp `prefix + "*"`?

**Đáp án:** Không nối prefix chưa được encode vào filter. Cần escape tiền tố như dữ liệu literal rồi chỉ thêm **wildcard cố định do ứng dụng quyết định**, hoặc dùng API tạo substring filter phù hợp của thư viện.

**Câu 6.** Filter được mã hóa đúng có xác nhận người dùng đã đăng nhập hoặc có quyền xem hồ sơ không?

**Đáp án:** Không. Filter chỉ quyết định điều kiện tìm kiếm. Xác thực có thể qua LDAP bind/IdP; phân quyền, ACL, TLS và giới hạn kết quả là các lớp kiểm soát riêng.

---

**Nguyên tắc áp dụng ngay:** Với các truy vấn Spring LDAP, hãy giữ nguyên cấu trúc bằng `LdapQueryBuilder` hoặc các `Filter` builder; đưa dữ liệu người dùng dưới dạng **giá trị literal** cho API xử lý escaping. Khi cần wildcard, field tìm kiếm hay scope linh hoạt, thiết kế một tập tùy chọn có giới hạn rõ ràng và kiểm thử những đầu vào có dấu sao, ngoặc, backslash, NUL và Unicode.
