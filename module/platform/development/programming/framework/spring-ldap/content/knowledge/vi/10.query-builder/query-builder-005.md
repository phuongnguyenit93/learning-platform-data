# like, is, gte và lte

Khi tìm kiếm entry trong LDAP bằng **Spring LDAP**, lập trình viên thường không cần tự nối các chuỗi filter như `(&(objectClass=inetOrgPerson)(uid=linh))`. Thay vào đó, **`LdapQueryBuilder`** cung cấp các phương thức để diễn đạt điều kiện tìm kiếm theo cấu trúc. Bốn toán tử đáng chú ý là **`is`**, **`like`**, **`gte`** và **`lte`**.

Tuy chúng trông giống các phép so sánh quen thuộc trong SQL hoặc Java, ý nghĩa thực tế của chúng do **LDAP filter syntax**, **schema** và **matching rule** của từng thuộc tính quyết định. Sử dụng sai toán tử có thể khiến truy vấn không khớp, mở rộng quá mức do wildcard hoặc trả kết quả khác mong đợi khi so sánh theo thứ tự.

Bài này thuộc chương **Query builder** của module **SPRING_LDAP**, gắn trực tiếp với việc tìm kiếm bằng `LdapTemplate`, cấu hình `ContextSource`, xây filter an toàn, xử lý DN, TLS, quyền đọc và kiểm thử LDAP server. Sau bài học, bạn sẽ biết khi nào dùng `is` để tìm chính xác, `like` để tìm theo mẫu, `gte`/`lte` để so sánh ngưỡng, và cách kết hợp chúng mà không làm mất an toàn của truy vấn.

## 1. Một `LdapQuery` gồm những thành phần nào?

Một phép search LDAP không chỉ có điều kiện filter. Nó còn có **base DN** (tìm từ đâu), **search scope** (duyệt sâu bao nhiêu cấp) và **requested attributes** (muốn nhận những trường nào).

Giả sử `LdapContextSource` được cấu hình:

~~~text
URL:        ldaps://directory.example.org:636
Base DN:    dc=example,dc=org
Bind DN:    cn=app-reader,ou=service,dc=example,dc=org
~~~

Trong ứng dụng chỉ quản lý người dùng ở `ou=people`, một truy vấn Spring LDAP có thể viết:

~~~java
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;
import org.springframework.ldap.query.SearchScope;

LdapQuery query = LdapQueryBuilder.query()
        .base("ou=people")
        .searchScope(SearchScope.ONELEVEL)
        .attributes("uid", "cn", "mail")
        .where("objectClass").is("inetOrgPerson")
        .and("uid").is("linh");
~~~

Bốn phần cần phân biệt:

| Thành phần | Trong ví dụ | Ý nghĩa |
| --- | --- | --- |
| **Base** | `ou=people` | Tìm dưới OU người dùng, tương đối với `dc=example,dc=org` |
| **Scope** | `ONELEVEL` | Chỉ xét các entry con trực tiếp của OU đó |
| **Filter** | `(&(objectClass=inetOrgPerson)(uid=linh))` | Entry cần khớp đồng thời hai điều kiện |
| **Attributes** | `uid`, `cn`, `mail` | Chỉ yêu cầu trả những thuộc tính cần dùng |

`LdapQueryBuilder` tạo đối tượng query; **`LdapTemplate`** hoặc API Spring LDAP phù hợp sẽ thực hiện query với một `ContextSource`. Query builder không tự tạo kết nối, không xác thực người dùng và không thay thế ACL của LDAP server.

Nếu base của `ContextSource` đã là `dc=example,dc=org`, việc truyền thêm base đầy đủ `ou=people,dc=example,dc=org` vào nơi mong đợi tên tương đối có thể làm lặp suffix. Khi base được xây từ đầu vào động, dùng `LdapName`/`LdapNameBuilder` thay vì ghép chuỗi DN.

## 2. Bản đồ nhanh: `is`, `like`, `gte` và `lte`

| Phương thức Spring LDAP | Dạng LDAP filter tương ứng | Mục đích | Điều cần lưu ý |
| --- | --- | --- | --- |
| `.is("linh")` | `(uid=linh)` | So khớp bằng (*equality*) | Dựa vào equality matching rule |
| `.like("Lin*")` | `(cn=Lin*)` | So khớp chuỗi con/mẫu có wildcard | `*` có ý nghĩa cú pháp; phải kiểm soát input |
| `.gte("3")` | `(employeeLevel>=3)` | So khớp lớn hơn hoặc bằng | Cần ordering matching rule phù hợp |
| `.lte("7")` | `(employeeLevel<=7)` | So khớp nhỏ hơn hoặc bằng | Không mặc nhiên là so sánh số học |

`employeeLevel` là **thuộc tính ví dụ** của một schema LDAP tùy biến, được giả định có **integer ordering matching rule**. Không được copy filter đó vào một LDAP server bất kỳ rồi kết luận phương thức `gte`/`lte` bị lỗi nếu schema không định nghĩa thuộc tính hoặc không hỗ trợ ordering.

Về mặt giao thức, LDAP search filter được biểu diễn thành chuỗi theo RFC 4515. Filter giống với một biểu thức logic server đánh giá trên từng entry trong vùng tìm kiếm. Query builder giúp lập trình viên diễn đạt biểu thức mà không phải tự quản lý mọi dấu ngoặc và escape.

## 3. `is`: so khớp bằng theo schema

**`is(value)`** dùng để yêu cầu thuộc tính khớp một **giá trị assertion** thông qua equality matching rule của thuộc tính đó.

Ví dụ tìm chính xác `uid`:

~~~java
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;

LdapQuery byUid = LdapQueryBuilder.query()
        .base("ou=people")
        .where("uid").is("linh");
~~~

Biểu thức filter về mặt ý nghĩa:

~~~ldap
(uid=linh)
~~~

Khi cần giới hạn theo object class:

~~~java
LdapQuery personByUid = LdapQueryBuilder.query()
        .base("ou=people")
        .where("objectClass").is("inetOrgPerson")
        .and("uid").is("linh");
~~~

Kết quả tương ứng:

~~~ldap
(&(objectClass=inetOrgPerson)(uid=linh))
~~~

### 3.1. `is` không phải phép so chuỗi Java

Phép equality ở LDAP được quyết định bởi **schema**:

- Thuộc tính có thể áp dụng matching rule **không phân biệt chữ hoa/chữ thường**, ví dụ `caseIgnoreMatch`.
- Một thuộc tính khác có thể dùng matching rule phân biệt chữ hoa/chữ thường hoặc dành cho dạng dữ liệu đặc thù.
- Với thuộc tính có nhiều giá trị, entry có thể khớp khi **ít nhất một giá trị** của thuộc tính thỏa điều kiện.
- Khi thuộc tính không tồn tại, điều kiện equality thông thường không khớp.

Vì thế `.is("linh")` không phải một lời hứa rằng Java sẽ gọi `String.equals("linh")` trên từng giá trị, cũng không bảo đảm rằng hai giá trị Unicode có cách viết khác nhau sẽ được coi là một. Hành vi cụ thể do server và matching rule quyết định.

### 3.2. Dấu `*` trong equality phải là dữ liệu literal

Xét định danh thực sự chứa ký tự sao: `an*b`.

~~~java
LdapQuery literal = LdapQueryBuilder.query()
        .where("uid").is("an*b");
~~~

Đối với equality builder, giá trị được mã hóa như **dữ liệu literal**, nên về ý nghĩa filter tương ứng với:

~~~ldap
(uid=an\2ab)
~~~

Dấu `\2a` biểu diễn ký tự `*` như dữ liệu, **không phải wildcard**. Điều này khác `.like("an*b")`: trong mẫu like, dấu `*` có vai trò so khớp chuỗi con.

Không tự escape `an*b` thành `an\2ab` trước rồi lại truyền cho `.is(...)`: việc encode lặp có thể khiến dấu gạch chéo ngược trở thành ký tự literal. Hãy giữ **giá trị Java nguyên bản**, truyền nó cho builder và để builder chịu trách nhiệm encode.

### 3.3. Khi nào nên dùng `is`?

`is` phù hợp với:

- Tìm tài khoản theo `uid`, mã nhân viên hoặc email khi nghiệp vụ cần **equality**.
- Xác định object class: `(objectClass=inetOrgPerson)`.
- Lọc entry theo loại/tình trạng được biểu diễn bởi một giá trị thuộc tính.
- Xây truy vấn đăng nhập **tìm DN tài khoản** trước một bước xác thực riêng, nếu thiết kế yêu cầu.

**Tìm được entry không đồng nghĩa người dùng đã đăng nhập thành công.** Xác thực còn cần LDAP bind hoặc cơ chế IdP/Spring Security phù hợp, và phân quyền vẫn là bước riêng.

## 4. `like`: mẫu chuỗi con và wildcard

**`like(pattern)`** biểu diễn phép tìm kiếm dạng **substring** trong LDAP, trong đó ký tự `*` ở vị trí thích hợp mang nghĩa wildcard.

Ví dụ:

~~~java
LdapQuery startsWithLin = LdapQueryBuilder.query()
        .base("ou=people")
        .where("cn").like("Lin*");

LdapQuery endsWithNguyen = LdapQueryBuilder.query()
        .base("ou=people")
        .where("cn").like("*Nguyen");

LdapQuery containsAnh = LdapQueryBuilder.query()
        .base("ou=people")
        .where("cn").like("*Anh*");
~~~

Các dạng filter tương ứng:

~~~ldap
(cn=Lin*)
(cn=*Nguyen)
(cn=*Anh*)
~~~

| Mẫu | Ý nghĩa |
| --- | --- |
| `Lin*` | Giá trị bắt đầu bằng `Lin` |
| `*Nguyen` | Giá trị kết thúc bằng `Nguyen` |
| `*Anh*` | Giá trị có phần chứa `Anh` |
| `Le*Anh` | Giá trị có phần đầu `Le` và kết thúc bằng `Anh` với đoạn giữa bất kỳ |

Đây là cách diễn giải về **mẫu**, không phải bảo đảm kết quả sẽ khớp theo quy tắc `String.contains` trong Java. LDAP server sử dụng **substring matching rule** của thuộc tính. Quy tắc chuẩn hóa, không phân biệt hoa thường và mức hỗ trợ có thể khác theo schema và sản phẩm LDAP.

### 4.1. Vì sao `like` cần được kiểm soát chặt khi có input động?

Giả sử API cho người dùng tìm tên bắt đầu bằng một tiền tố:

~~~java
// Không nên để client tự quyết định mẫu tùy ý.
LdapQuery query = LdapQueryBuilder.query()
        .where("cn").like(prefixFromRequest);
~~~

Nếu `prefixFromRequest` là `*`, ý nghĩa của filter có thể trở thành truy vấn rất rộng. Ngay cả khi thư viện mã hóa một số ký tự nguy hiểm, **dấu sao có chủ ý trong pattern vẫn là wildcard**. Do đó:

1. Xác định rõ nghiệp vụ cho phép **equality**, **starts-with**, **ends-with** hay **contains**.
2. Cố định tên thuộc tính ở code hoặc trong allowlist.
3. Giới hạn độ dài và tập giá trị input.
4. Chỉ cho code thêm wildcard tại vị trí do ứng dụng quyết định.
5. Đặt base DN, scope, count limit và timeout để tránh search diện rộng.

Ví dụ bài học dùng **tiền tố ASCII chữ cái** có quy tắc hạn chế rõ ràng:

~~~java
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;
import org.springframework.ldap.query.SearchScope;

public final class EmployeeNameQueries {
    private EmployeeNameQueries() {}

    public static LdapQuery startsWithAsciiLetters(String prefix) {
        if (prefix == null || !prefix.matches("[A-Za-z]{2,40}")) {
            throw new IllegalArgumentException("Tiền tố không hợp lệ");
        }

        // Tại đây prefix không thể chứa wildcard hoặc dấu ngoặc.
        String controlledPattern = prefix + "*";

        return LdapQueryBuilder.query()
                .base("ou=people")
                .searchScope(SearchScope.ONELEVEL)
                .countLimit(30)
                .timeLimit(2000)
                .attributes("uid", "cn")
                .where("objectClass").is("inetOrgPerson")
                .and("cn").like(controlledPattern);
    }
}
~~~

Regex `[A-Za-z]{2,40}` là **chính sách giới hạn của ví dụ**, không phải ràng buộc chung của LDAP. Một ứng dụng tiếng Việt cần tìm họ tên Unicode không nên áp regex này máy móc; phải xác định cách chấp nhận Unicode, escape giá trị literal và tạo wildcard bằng API phù hợp của **phiên bản Spring LDAP đang sử dụng**. Điểm cốt lõi là không cho input chưa qua kiểm soát trở thành **cấu trúc filter**.

Một cách làm sai thường thấy là tự nối:

~~~java
// KHÔNG AN TOÀN: giá trị chưa xử lý trở thành cú pháp filter.
String unsafe = "(cn=" + userInput + "*)";
~~~

Nếu input chứa `*`, `(` hoặc `)`, biểu thức có thể đổi ý nghĩa hoặc sai cú pháp. Tránh khắc phục bằng vài phép `replace` thủ công; hãy dùng query/filter builder và kiểm thử đối kháng.

### 4.2. `like` không phải lựa chọn mặc định cho tra cứu định danh

Nếu tìm `uid` để xác thực, nên sử dụng `.is(uid)`. Không thay bằng `.like(uid + "*")` chỉ để “dễ tìm hơn”: một tiền tố có thể khớp nhiều tài khoản, làm hỏng việc xác định người dùng duy nhất.

Ngược lại, khi xây ô gợi ý tìm kiếm danh bạ, `like` có thể hợp lý nếu giới hạn base/scope và kết quả, đồng thời không đọc những thuộc tính nhạy cảm không cần thiết.

### 4.3. Truy vấn substring có chi phí

Mẫu có wildcard ở đầu, ví dụ `*Anh*`, có thể khó được tăng tốc bằng chỉ mục prefix thông thường. Chi phí phụ thuộc chiến lược index, matching rule và cách server thực thi.

**Không dựa vào `countLimit(30)` như một giải pháp duy nhất cho search quá rộng.** Server có thể vẫn phải xét nhiều entry trước khi trả 30 kết quả. Cần thu hẹp base, chọn scope đúng, chỉ yêu cầu thuộc tính cần thiết và có chính sách tần suất truy vấn.

## 5. `gte` và `lte`: so sánh theo ordering matching rule

`gte` là viết tắt của **greater than or equal** (lớn hơn hoặc bằng); `lte` là **less than or equal** (nhỏ hơn hoặc bằng).

Trong LDAP filter:

~~~ldap
(employeeLevel>=3)
(employeeLevel<=7)
~~~

Với Spring LDAP query builder:

~~~java
LdapQuery atLeastThree = LdapQueryBuilder.query()
        .base("ou=people")
        .where("employeeLevel").gte("3");

LdapQuery atMostSeven = LdapQueryBuilder.query()
        .base("ou=people")
        .where("employeeLevel").lte("7");
~~~

**Quan trọng:** `employeeLevel` ở đây là **thuộc tính minh họa**, cần được định nghĩa trong schema của LDAP server với cú pháp và **ordering matching rule** phù hợp (ví dụ integer ordering). Nếu server không nhận diện thuộc tính hoặc không hỗ trợ ordering, câu lệnh có thể không trả kết quả như dự kiến hoặc dẫn đến lỗi matching; không mặc định so sánh Java sẽ được dùng.

### 5.1. So sánh theo schema, không theo kiểu Java của tham số

Chú ý các ví dụ đều truyền **chuỗi** như `"3"` và `"7"`. Builder xây assertion value và filter. **LDAP server** thực hiện so sánh dựa vào matching rule của thuộc tính.

Đối với thuộc tính chuỗi được so sánh theo quy tắc thứ tự chữ, `"10"` có thể được xếp trước `"2"` theo thứ tự từ điển, trái với so sánh số học. Đối với thuộc tính có integer ordering matching rule phù hợp, các giá trị `10` và `2` mới được so sánh theo ngữ nghĩa số như mong muốn.

Không thể kết luận chỉ từ tên trường như `grade`, `salary` hay `employeeNumber` rằng server sẽ dùng phép so sánh số. Phải xem **schema** thực tế, không chỉ tên và hình thức của dữ liệu.

### 5.2. Kết hợp `gte` và `lte` thành khoảng

Giả sử schema có `employeeLevel` kiểu số nguyên với ordering matching rule. Yêu cầu nghiệp vụ: chỉ tìm nhân viên có cấp bậc từ 3 đến 7, tính cả hai đầu mút.

~~~java
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;
import org.springframework.ldap.query.SearchScope;

public final class EmployeeLevelQueries {
    private EmployeeLevelQueries() {}

    public static LdapQuery betweenThreeAndSeven() {
        return LdapQueryBuilder.query()
                .base("ou=people")
                .searchScope(SearchScope.SUBTREE)
                .countLimit(100)
                .attributes("uid", "cn", "employeeLevel")
                .where("objectClass").is("inetOrgPerson")
                .and("employeeLevel").gte("3")
                .and("employeeLevel").lte("7");
    }
}
~~~

Filter về mặt ý nghĩa:

~~~ldap
(&(objectClass=inetOrgPerson)(employeeLevel>=3)(employeeLevel<=7))
~~~

Đây là **giao của hai điều kiện**: mỗi entry cần đồng thời không nhỏ hơn 3 và không lớn hơn 7. Không được đổi hai điều kiện thành OR nếu nghiệp vụ thực sự là một khoảng.

Phương thức `gte`/`lte` không tự kiểm tra rằng `min <= max` theo loại dữ liệu mong muốn. Khi nhận khoảng từ HTTP request, cần kiểm tra thứ tự và giới hạn hợp lệ ở tầng nghiệp vụ, rồi mới chuyển thành giá trị assertion phù hợp với schema.

### 5.3. Phân biệt thời gian, ngày và chuỗi số

Một số thư mục sử dụng các thuộc tính thời gian theo cú pháp LDAP `GeneralizedTime`. Một số khác lại lưu ngày trong chuỗi tự định nghĩa. **Không thể giả định** mọi thuộc tính chứa ngày đều hỗ trợ ordering chính xác.

Nếu ứng dụng cần tìm theo ngày tạo tài khoản, ngày hết hạn hoặc cấp bậc, nên:

- Xác định thuộc tính thực tế của server.
- Đọc schema: syntax, equality matching rule và ordering matching rule.
- Chuẩn hóa giá trị thời gian/number sang biểu diễn đúng cú pháp trước khi gọi builder.
- Kiểm thử các mốc ranh giới, múi giờ và định dạng dữ liệu.
- Tránh tự chế một thuộc tính string rồi tin rằng `gte`/`lte` sẽ tự hiểu đó là số hoặc timestamp.

Đối với các server hỗ trợ thuộc tính thời gian/number khác nhau, logic có thể cần adapter riêng thay vì một filter dùng chung cho mọi sản phẩm.

## 6. Kết hợp các toán tử trong một `LdapQuery`

Một nhu cầu thực tế: tìm nhân viên thuộc cấp bậc 3–7 **và** tên bắt đầu bằng `Lin`, chỉ đọc `uid`, `cn` và `employeeLevel`:

~~~java
LdapQuery query = LdapQueryBuilder.query()
        .base("ou=people")
        .searchScope(SearchScope.ONELEVEL)
        .countLimit(50)
        .timeLimit(2000)
        .attributes("uid", "cn", "employeeLevel")
        .where("objectClass").is("inetOrgPerson")
        .and("cn").like("Lin*")
        .and("employeeLevel").gte("3")
        .and("employeeLevel").lte("7");
~~~

Biểu thức filter tương ứng về mặt logic:

~~~ldap
(&(objectClass=inetOrgPerson)(cn=Lin*)(employeeLevel>=3)(employeeLevel<=7))
~~~

Khi cần tìm một trong hai tài khoản chính xác, có thể dùng OR:

~~~java
LdapQuery eitherUid = LdapQueryBuilder.query()
        .base("ou=people")
        .where("uid").is("linh")
        .or("uid").is("mai");
~~~

Filter:

~~~ldap
(|(uid=linh)(uid=mai))
~~~

Đối với điều kiện AND/OR phức tạp hơn, hãy kiểm tra khả năng nhóm của query builder phiên bản dự án đang dùng hoặc xây filter qua `AndFilter`, `OrFilter`, `EqualsFilter` và những filter tương ứng. **Không tự thêm dấu ngoặc bằng nối chuỗi** nếu dữ liệu đầu vào chưa được mã hóa.

### 6.1. Chọn đúng toán tử theo ý định

| Ý định nghiệp vụ | Toán tử thường phù hợp | Không nên |
| --- | --- | --- |
| Tra cứu đúng `uid` | `is` | `like(uid + "*")` để nhận thêm tài khoản |
| Gợi ý tên theo tiền tố | `like` với wildcard do ứng dụng tạo | Cho client gửi nguyên một filter bất kỳ |
| Chọn cấp bậc tối thiểu | `gte` với thuộc tính có ordering | Giả định mọi trường số dạng string đều so được |
| Chọn cấp bậc tối đa | `lte` với thuộc tính có ordering | Chuyển giới hạn thành phép so Java ở client sau khi tải toàn bộ |
| Chọn khoảng bao gồm hai biên | AND của `gte` và `lte` | OR hai điều kiện ngưỡng |
| Kiểm tra attribute có tồn tại | Presence filter `(mail=*)` | Dùng `is("*")` để thay presence |

Ở dòng cuối, `is("*")` có ý nghĩa tìm **dấu sao literal** khi builder escape đúng; nó không tương đương presence. Với yêu cầu thuộc tính tồn tại, sử dụng API presence filter của thư viện hoặc filter cấu trúc đúng `(mail=*)`.

## 7. Thực thi query với `LdapTemplate`

`LdapQueryBuilder` chỉ xây query. Để lấy dữ liệu, đưa query vào `LdapTemplate.search` với mapper:

~~~java
import java.util.List;
import javax.naming.directory.Attribute;

import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;

public final class EmployeeDirectoryService {
    private final LdapTemplate template;

    public EmployeeDirectoryService(LdapTemplate template) {
        this.template = template;
    }

    public List<EmployeeView> findByQuery(LdapQuery query) {
        return template.search(query,
                (AttributesMapper<EmployeeView>) attributes -> {
                    Attribute uid = attributes.get("uid");
                    Attribute cn = attributes.get("cn");
                    if (uid == null || cn == null) {
                        throw new IllegalStateException(
                                "LDAP entry thiếu uid hoặc cn");
                    }
                    return new EmployeeView(
                            String.valueOf(uid.get()),
                            String.valueOf(cn.get()));
                });
    }

    public record EmployeeView(String uid, String fullName) {}
}
~~~

Ví dụ cố tình yêu cầu hai thuộc tính bắt buộc, thay vì chuyển các lỗi dữ liệu âm thầm thành chuỗi rỗng. Mã thực tế cần cân nhắc:

- Cách schema biểu diễn thuộc tính đa trị và xử lý giá trị thiếu.
- Nên giới hạn **những thuộc tính được trả về**, đặc biệt khi có dữ liệu nhạy cảm.
- Kết quả không có entry không đồng nghĩa LDAP server đã kết thúc thành công trong mọi tình huống; cần phân biệt lỗi timeout/referral và kết quả chưa đầy đủ.
- Một query trả nhiều entry không chứng minh `uid` là duy nhất; tính duy nhất cần chính sách của server và nghiệp vụ.
- Các thao tác đọc cần dùng **LDAPS hoặc StartTLS** có xác minh chứng chỉ và tài khoản chỉ có quyền đọc cần thiết.

### 7.1. Giới hạn tìm kiếm không thay thế scope hoặc ACL

Ví dụ `countLimit(50)` là yêu cầu giới hạn số entry được trả; `timeLimit(2000)` ở API Spring LDAP/JNDI thường biểu diễn **mili giây**. Server LDAP vẫn có giới hạn quản trị riêng. Cả hai cũng không thay `SearchScope`, filter hoặc việc giới hạn base.

**Đừng tải toàn bộ danh bạ rồi dùng Java `stream().limit(50)`** nếu chỉ cần 50 kết quả: lúc đó ứng dụng có thể đã nhận rất nhiều dữ liệu từ server. Đồng thời, không coi kết quả chạm ngưỡng limit là danh sách hoàn chỉnh. Nếu cần duyệt nhiều trang, xem cơ chế LDAP paged results do server hỗ trợ và đặt giới hạn tổng.

### 7.2. Query builder không tự xử lý xác thực

Một ứng dụng có thể tìm tài khoản bằng `.where("uid").is(uid)`, lấy DN và sau đó sử dụng cơ chế authentication. Nhưng **search và authentication bind là hai thao tác khác nhau**. Không đánh dấu đăng nhập thành công chỉ vì tìm thấy entry. Khi cần xác thực bằng mật khẩu, bảo vệ kênh TLS, chặn mật khẩu rỗng và phân quyền riêng sau xác thực.

## 8. Bảo vệ filter khỏi LDAP injection và kết quả quá rộng

LDAP filter có ký tự cú pháp đặc biệt: `*`, `(`, `)`, `\` và NUL. Trong dạng chuỗi RFC 4515, nếu muốn tìm những ký tự này như **giá trị literal**, phải escape đúng cách, ví dụ:

| Ký tự literal | Biểu diễn assertion value |
| --- | --- |
| `*` | `\2a` |
| `(` | `\28` |
| `)` | `\29` |
| `\` | `\5c` |
| NUL | `\00` |

Một đoạn code sai:

~~~java
// KHÔNG AN TOÀN: input HTTP được đặt trực tiếp vào cú pháp filter.
String rawFilter = "(&(objectClass=inetOrgPerson)(uid=" + uid + "))";
~~~

Với `uid` bằng `*)(uid=*`, chuỗi có thể trở thành:

~~~ldap
(&(objectClass=inetOrgPerson)(uid=*)(uid=*))
~~~

Thay vì tìm đúng một UID, truy vấn trở thành điều kiện hiện diện của thuộc tính `uid` và có thể khớp nhiều tài khoản hơn.

Với `is(uid)`, builder diễn đạt equality với input là **giá trị**, không cho phép người dùng tự thêm toán tử filter. Với `like(pattern)`, cần chú ý thêm rằng **wildcard là một phần của pattern có chủ ý**; phải giới hạn cách user cung cấp pattern và chỉ thêm dấu `*` ở nơi ứng dụng cho phép.

**Validation, escaping và authorization là ba lớp độc lập:**

- **Validation:** giá trị có đúng độ dài, định dạng, khoảng và chức năng được phép không?
- **Escaping/builder:** giá trị có được chuyển thành assertion value đúng cú pháp mà không thay đổi cấu trúc filter không?
- **Authorization/ACL:** người gọi và tài khoản LDAP có quyền đọc dữ liệu phù hợp không?

Thêm TLS giúp bảo vệ đường truyền, nhưng **không sửa** lỗi nối input vào filter. Đổi DN bằng chuỗi cũng là lỗi khác: escape DN theo RFC 4514 và escape filter theo RFC 4515 không phải một việc.

## 9. Khi nào cần tìm hiểu schema trước khi viết `gte`/`lte`?

Một tình huống dễ gây nhầm lẫn: developer có thuộc tính `employeeCode` chứa các giá trị dạng `"1"`, `"2"` và `"10"`, rồi viết:

~~~java
LdapQuery query = LdapQueryBuilder.query()
        .where("employeeCode").gte("2");
~~~

Cú pháp query builder có thể hợp lệ, nhưng kết quả chưa chắc đúng kỳ vọng số học:

- Nếu `employeeCode` là Directory String với ordering dạng ký tự, có thể bị xếp theo chữ thay vì số.
- Nếu schema không khai báo ordering matching rule, filter không có ý nghĩa so sánh thứ tự như mong muốn.
- Nếu server dùng quy tắc riêng, có thể cần attribute/matching rule đặc thù của hệ triển khai.
- Nếu một entry có giá trị sai định dạng, cần biết server xử lý theo syntax và validation nào.

**Cách thiết kế đúng:** xác định rõ attribute, syntax, equality/ordering matching rules và kiểu dữ liệu trong schema; chỉ sau đó mới chọn `gte`/`lte`. Với nhu cầu tính toán báo cáo phức tạp, LDAP có thể không phải nơi thực hiện tốt nhất mọi phép so sánh như một hệ quản trị CSDL quan hệ.

### 9.1. So sánh hai mức điều kiện

| Mức | Ví dụ | Trách nhiệm |
| --- | --- | --- |
| **Nghiệp vụ Java** | `minLevel <= maxLevel`; level từ 1 đến 10 | Validation dữ liệu do API nhận |
| **LDAP filter** | `(employeeLevel>=3)` và `(employeeLevel<=7)` | Server đánh giá theo schema/matching rule |

Đừng coi validation ở Java đã thay thế được kết quả lọc trên server, và cũng đừng tin LDAP filter tự biết những quy tắc nghiệp vụ như “cấp bậc chỉ từ 1 đến 10”.

## 10. Thực hành kiểm thử từng toán tử

Hãy dùng **LDAP server thử nghiệm**, có base `dc=example,dc=org`, nhánh `ou=people` và schema phù hợp. Dữ liệu LDIF minh họa cho `is`/`like`:

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

Các entry cha được giả định đã tồn tại. Với `gte`/`lte`, cần **bổ sung thuộc tính `employeeLevel` vào schema thử nghiệm** với cú pháp số nguyên và ordering matching rule, sau đó đặt `3` cho Linh và `8` cho Mai. Không thêm một thuộc tính tùy biến không có trong schema rồi mong server tự chấp nhận.

| Phép thử | Query/filter dự định | Kỳ vọng với dữ liệu mẫu |
| --- | --- | --- |
| `is` chính xác | `(uid=linh)` | Linh |
| `is` khác | `(uid=mai)` | Mai |
| `like` prefix | `(cn=Lin*)` | Linh |
| `like` suffix | `(cn=*Tran)` | Mai |
| `like` contains | `(cn=*inh*)` | Linh |
| `gte` ngưỡng 5 | `(employeeLevel>=5)` | Mai, khi ordering đúng kiểu số |
| `lte` ngưỡng 5 | `(employeeLevel<=5)` | Linh, khi ordering đúng kiểu số |
| `gte AND lte` từ 3 đến 7 | `(&(employeeLevel>=3)(employeeLevel<=7))` | Linh |
| Equality với dấu sao literal | `(uid=an\2ab)` | Không khớp hai entry mẫu |
| `like` với prefix không hợp lệ | Input chỉ là `*` | Ứng dụng từ chối theo chính sách |
| Thuộc tính không có ordering | Dùng `gte` với attribute chưa được schema cho phép | Không giả định có phép so sánh đúng; kiểm tra response/error server |

### 10.1. Các bước kiểm thử tích hợp

1. Cấu hình `LdapContextSource` trỏ tới một LDAP server thử nghiệm qua TLS và base phù hợp.
2. Kiểm tra `LdapTemplate` có thể đọc OU/entry bằng tài khoản dịch vụ chỉ được cấp quyền cần thiết.
3. Chạy từng query `is` và `like` với **cùng base/scope**, đối chiếu DN và thuộc tính thực tế trả về.
4. Cấu hình thuộc tính có integer ordering matching rule trên server test; chạy `gte`/`lte` ở các biên thấp, cao và giữa.
5. Thử đầu vào nguy hiểm `*`, `(`, `)`, `\` và Unicode để bảo đảm input không làm thay đổi cấu trúc filter.
6. Kiểm tra kết quả khi thuộc tính vắng mặt, ACL không đủ, schema không hỗ trợ matching rule, time limit và server bị gián đoạn.
7. Xác nhận lớp service phân biệt “không có kết quả” với “không thể lấy dữ liệu vì lỗi”.

### 10.2. Unit test cho validation và builder

Đây là ví dụ JUnit 5 chỉ kiểm tra **chính sách input của ứng dụng** và xây một query thành công:

~~~java
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;
import org.springframework.ldap.query.LdapQuery;

class EmployeeNameQueriesTest {
    @Test
    void acceptedPrefixBuildsQuery() {
        LdapQuery query =
                EmployeeNameQueries.startsWithAsciiLetters("Lin");
        assertNotNull(query);
    }

    @Test
    void wildcardFromClientIsRejected() {
        assertThrows(IllegalArgumentException.class,
                () -> EmployeeNameQueries.startsWithAsciiLetters("*"));
    }

    @Test
    void tooShortPrefixIsRejected() {
        assertThrows(IllegalArgumentException.class,
                () -> EmployeeNameQueries.startsWithAsciiLetters("L"));
    }
}
~~~

Unit test không chứng minh LDAP server đánh giá ordering hay substring theo đúng kỳ vọng. **Matching rules, schema, quyền, TLS và hành vi của server phải được kiểm thử tích hợp**. Nếu thêm thuộc tính tùy biến, phải kiểm tra schema và fixture thực tế thay vì chỉ mock `LdapTemplate`.

## 11. Lỗi thường gặp và cách sửa

| Triệu chứng | Khả năng nguyên nhân | Cách khắc phục |
| --- | --- | --- |
| `is("Lin*")` không tìm các tên có prefix `Lin` | `is` biểu diễn equality, `*` được xem là literal | Dùng `like("Lin*")` khi thực sự muốn substring |
| `like("*")` trả quá nhiều entry | Cho phép wildcard từ client tùy ý | Kiểm soát pattern và giới hạn base/scope |
| `gte("2")` cho kết quả lạ với `"10"` | Thuộc tính so sánh dạng chuỗi hoặc không có ordering phù hợp | Xem lại schema/matching rule, dùng thuộc tính đúng |
| `lte` không khớp entry | Thuộc tính thiếu, giá trị sai syntax hoặc server không hỗ trợ ordering | Kiểm tra schema và dữ liệu |
| Filter bị lỗi hoặc kết quả mở rộng bất ngờ | Tự nối chuỗi input vào filter | Dùng builder và escape assertion value |
| Dữ liệu đúng nhưng search rỗng | Base DN, search scope, ACL hoặc alias/referral sai | Kiểm tra từng yếu tố độc lập |
| Không tìm được entry ở OU con | Đang dùng `ONELEVEL` | Dùng `SUBTREE` chỉ khi nghiệp vụ cần |
| Chạy chậm khi `like("*...*")` | Wildcard đầu chuỗi và filter quá rộng | Giới hạn truy vấn, cân nhắc chỉ mục/server |
| Lỗi mạng/TLS bị hiểu thành không có dữ liệu | Bắt mọi exception rồi trả danh sách rỗng | Phân loại exception và trạng thái partial result |

Đừng thay việc sửa query bằng cách dùng bind account đặc quyền hơn. Nếu tài khoản dịch vụ thiếu quyền đọc phù hợp, cần xác định ACL chính xác và cấp **quyền tối thiểu**.

## 12. Câu hỏi tự đánh giá

**Câu 1.** `.where("uid").is("linh")` và `.where("uid").like("linh")` có hoàn toàn giống nhau không?

**Đáp án:** Không nên xem là tương đương về ngữ nghĩa. `is` dùng equality matching rule; `like` nhắm tới substring pattern/matching. Khi cần định danh chính xác, chọn `is`.

**Câu 2.** Muốn tìm tên bắt đầu bằng `Lin`, dùng toán tử nào?

**Đáp án:** Dùng `like` với mẫu `Lin*`, nhưng nếu tiền tố do user nhập thì phải kiểm soát/escape phần literal và chỉ để wildcard do ứng dụng quyết định.

**Câu 3.** `gte("3")` có nghĩa Java sẽ chuyển mọi thuộc tính thành số nguyên và so sánh không?

**Đáp án:** Không. LDAP server đánh giá filter bằng ordering matching rule của thuộc tính. Phải xác minh schema có hỗ trợ và quy tắc đúng kiểu dữ liệu.

**Câu 4.** Muốn khoảng cấp bậc 3–7 bao gồm cả hai biên, dùng AND hay OR giữa `gte` và `lte`?

**Đáp án:** Dùng AND: `(&(employeeLevel>=3)(employeeLevel<=7))`, với điều kiện schema hỗ trợ ordering phù hợp.

**Câu 5.** Tại sao `.is(uid)` không thay thế được authentication?

**Đáp án:** Nó chỉ giúp search một entry. Xác thực phải qua LDAP bind, IdP hoặc cơ chế tương ứng, và phân quyền được thực hiện riêng.

**Câu 6.** Khi `like("Lin*")` trả hơn 30 entry nhưng ứng dụng chỉ hiển thị 30 entry đầu, có thể kết luận toàn bộ danh bạ chỉ có 30 kết quả không?

**Đáp án:** Không. Giới hạn kết quả không chứng minh tập dữ liệu đầy đủ. Phải xét trạng thái search, giới hạn server và cơ chế phân trang nếu cần.

**Câu 7.** Có nên dùng `String.replace` thủ công để escape dấu ngoặc, dấu sao và backslash khi dựng filter?

**Đáp án:** Không nên. Dùng filter/query builder có semantics rõ ràng, kiểm soát wildcard, tên thuộc tính và kiểm thử với đầu vào đặc biệt.

**Ghi nhớ:** **`is`** dành cho equality, **`like`** dành cho mẫu chuỗi con có wildcard được kiểm soát, còn **`gte`/`lte`** dành cho so sánh có **ordering matching rule** phù hợp. Trong Spring LDAP, dùng builder để giữ cấu trúc filter an toàn và kết hợp với base/scope, TLS, ACL, giới hạn search cùng kiểm thử server thật.

