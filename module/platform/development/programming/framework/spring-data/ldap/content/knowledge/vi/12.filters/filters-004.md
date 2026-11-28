# Kết hợp điều kiện AND, OR và NOT

Trong một directory LDAP, ứng dụng hiếm khi chỉ tìm entry bằng một điều kiện duy nhất. Chẳng hạn, màn hình danh bạ cần tìm **người dùng có `objectClass=inetOrgPerson`, thuộc nhóm nhân sự Engineering hoặc Support và không nằm trong danh sách đã lưu trữ**. Muốn truy vấn đúng, cần kết hợp các điều kiện bằng **AND**, **OR** và **NOT** theo cú pháp LDAP search filter, thay vì ghép chuỗi SQL hay tự nối input từ người dùng.

Trong module **SPRING_DATA_LDAP**, dữ liệu LDAP được tổ chức thành cây DN, entry tuân theo schema/`objectClass` và được truy cập từ Java qua `LdapRepository` hoặc `LdapTemplate`. Bài thuộc chương **Bộ lọc** này đi sâu vào **logic kết hợp điều kiện**, thứ tự nhóm lồng nhau, cách xây filter bằng Spring LDAP, rủi ro injection và kiểm thử trên directory. Bộ lọc chỉ quyết định *entry nào phù hợp truy vấn*; base DN, search scope, quyền LDAP và giới hạn kết quả vẫn cần được cấu hình riêng.

## 1. Kết quả cần đạt

Sau bài này, bạn có thể:

1. Đọc đúng các toán tử filter LDAP: `&` (AND), `|` (OR) và `!` (NOT).
2. Viết được filter nhiều điều kiện và xác định chính xác nhóm điều kiện qua dấu ngoặc.
3. Diễn đạt yêu cầu “A và (B hoặc C), nhưng không D” bằng một filter LDAP duy nhất.
4. Phân biệt **NOT một phép so khớp** với **thuộc tính tồn tại nhưng có giá trị khác**.
5. Sử dụng `LdapQueryBuilder` hoặc các lớp `AndFilter`, `OrFilter`, `NotFilter`, `EqualsFilter` của Spring LDAP để tránh ghép filter thủ công từ input không tin cậy.
6. Kiểm tra kết quả bằng `ldapsearch`, lưu ý schema, base DN, scope, ACL và những tình huống filter có kết quả rỗng.

## 2. Cú pháp LDAP filter: toán tử đứng trước các điều kiện

LDAPv3 sử dụng biểu diễn filter theo RFC 4515. Các thành phần cơ bản:

~~~text
(uid=lan)             Một điều kiện so khớp bằng.
(objectClass=person)   Một điều kiện trên objectClass.
(mail=*)              Thuộc tính mail hiện diện.
(&(A)(B))             AND: cả A và B.
(|(A)(B))             OR: ít nhất một trong A, B.
(!(A))                NOT: phủ định A.
~~~

`A` và `B` ở trên chỉ là ký hiệu minh họa cho **toàn bộ biểu thức filter con**, không phải chuỗi thuộc tính LDAP thực tế. Một filter hợp lệ luôn có cặp ngoặc bao quanh mỗi biểu thức con; toán tử logic đặt **ngay sau dấu ngoặc mở**.

| Toán tử | Dạng tổng quát | Ý nghĩa |
| --- | --- | --- |
| **AND** | `(&(uid=lan)(objectClass=inetOrgPerson))` | Entry phải thỏa mãn cả `uid=lan` và `objectClass=inetOrgPerson`. |
| **OR** | `(\|(uid=lan)(uid=minh))` | Entry thỏa ít nhất một trong hai giá trị `uid`. |
| **NOT** | `(!(uid=lan))` | Entry không thỏa phép so khớp `uid=lan` theo ngữ nghĩa filter LDAP. |

Trong bảng, ký tự `|` ở biểu thức OR có thể được escape khi hiển thị Markdown; **filter gửi đến LDAP thực tế không có dấu gạch chéo escape Markdown**:

~~~ldap
(|(uid=lan)(uid=minh))
~~~

### Ví dụ về một cây directory

~~~text
dc=example,dc=org
├── ou=people
│   ├── uid=lan           objectClass=inetOrgPerson, ou=Engineering
│   ├── uid=minh          objectClass=inetOrgPerson, ou=Support
│   ├── uid=an            objectClass=inetOrgPerson, ou=Finance
│   └── uid=robot         objectClass=inetOrgPerson, ou=Engineering
├── ou=groups
│   └── cn=developers
└── ou=services
    └── cn=sync-reader
~~~

Hình vẽ chỉ mô tả các entry minh họa. Thuộc tính `ou` trên entry user là dữ liệu **tùy schema và tổ chức**, không được suy từ tên nhánh. Để thử filter trong bài, giả sử các entry `uid=lan`, `uid=minh`, `uid=an` và `uid=robot` thực sự có các attribute như mô tả, được phép đọc bằng tài khoản dịch vụ và được tìm dưới `ou=people`.

## 3. AND: mọi điều kiện đều phải đúng

Nhu cầu: chỉ tìm người có object class `inetOrgPerson` và `uid=lan`.

~~~ldap
(&(objectClass=inetOrgPerson)(uid=lan))
~~~

Cách đọc: “lấy entry mà **đồng thời** là `inetOrgPerson` và có `uid` khớp với `lan`”.

Nhóm AND có thể chứa nhiều điều kiện:

~~~ldap
(&(objectClass=inetOrgPerson)(ou=Engineering)(mail=*))
~~~

Filter này yêu cầu:

1. Entry thỏa phép so khớp `objectClass=inetOrgPerson`.
2. Thuộc tính `ou` khớp `Engineering` theo matching rule của server.
3. Thuộc tính `mail` **tồn tại**.

Nếu Lan thuộc Engineering nhưng không có `mail`, Lan không phù hợp filter trên. Điều đó không có nghĩa entry của Lan không tồn tại. Chỉ là tổ hợp yêu cầu của truy vấn chưa được thỏa mãn.

Để lọc đúng, mỗi điều kiện nên dùng attribute có trong schema và thực sự được server trả về/tìm kiếm theo ACL. Không tự giả định tên thuộc tính hay phép so khớp chuỗi giống SQL; một số LDAP matching rule có thể không phân biệt chữ hoa/chữ thường hoặc có quy tắc chuẩn hóa riêng.

## 4. OR: ít nhất một điều kiện đúng

Nhu cầu: tìm người có `uid=lan` **hoặc** `uid=minh`.

~~~ldap
(|(uid=lan)(uid=minh))
~~~

Filter OR không có nghĩa server trả hai entry trong mọi trường hợp: nó chỉ trả entry **nằm trong search base/scope, phù hợp filter và được phép hiện diện trong kết quả theo ACL**. Nếu Minh ở ngoài base tìm kiếm, filter đúng vẫn có thể không trả Minh.

Một OR có thể kết hợp nhiều giá trị:

~~~ldap
(|(ou=Engineering)(ou=Support)(ou=Operations))
~~~

Đây là cách diễn đạt việc tìm những entry thuộc **ít nhất một** phòng ban. Nếu muốn chỉ tìm người dùng, nên kết hợp thêm `objectClass` bằng AND:

~~~ldap
(&(objectClass=inetOrgPerson)(|(ou=Engineering)(ou=Support)))
~~~

Khi không giới hạn `objectClass`, một số entry loại khác cũng có thể mang thuộc tính `ou` và thỏa OR, tùy schema/ACL.

## 5. NOT: phủ định **một filter con**

Nhu cầu: tìm những người dùng không khớp `uid=robot`.

~~~ldap
(&(objectClass=inetOrgPerson)(!(uid=robot)))
~~~

`!` nhận **một** filter con. Muốn phủ định cả một nhóm điều kiện, bao nhóm đó trong AND/OR rồi phủ định:

~~~ldap
(!(|(ou=Engineering)(ou=Support)))
~~~

Đọc là “không thỏa **(Engineering hoặc Support)**”, thay vì “không Engineering hoặc Support” (cách nói nhập nhằng).

### 5.1. NOT không đồng nghĩa với “có thuộc tính mang giá trị khác”

Xét yêu cầu “người dùng có email, nhưng email không bằng `lan@example.org`”. Hãy nêu rõ hai điều kiện: **email tồn tại** và **email không khớp giá trị bị loại**:

~~~ldap
(&(mail=*)(!(mail=lan@example.org)))
~~~

Đừng chỉ dùng:

~~~ldap
(!(mail=lan@example.org))
~~~

rồi mặc định mọi kết quả đều có email khác giá trị đó. LDAP filter có quy tắc đánh giá (bao gồm trường hợp phép so khớp không xác định) và server/ACL có thể làm thay đổi những gì truy vấn quan sát được. Filter phủ định **không tự thêm điều kiện tồn tại thuộc tính**. Với nghiệp vụ yêu cầu “có giá trị khác X”, hãy thêm presence filter `(mail=*)`.

Ngược lại, để hỏi **thuộc tính hoàn toàn không có mặt**:

~~~ldap
(!(mail=*))
~~~

Điều này phủ định phép kiểm tra presence, không phải so sánh email với chuỗi rỗng. Kết quả thực tế vẫn phụ thuộc schema, quyền đọc/tìm kiếm và trạng thái entry.

### 5.2. Không phủ định cả một điều kiện bằng cách chỉ thay dấu `=`

LDAP filter không phải SQL: không sử dụng `uid != robot` hoặc `(uid!=robot)` như cú pháp “khác”. Cách biểu diễn chuẩn là phủ định một equality filter:

~~~ldap
(!(uid=robot))
~~~

Nếu ứng dụng cần so sánh không bằng trong một tập dữ liệu có các thuộc tính thiếu, hãy nêu rõ chính sách với giá trị vắng mặt thay vì phụ thuộc vào cách hiểu tự nhiên của toán tử.

## 6. Kết hợp nhiều cấp: dùng ngoặc để tạo cây logic

Yêu cầu:

> Tìm entry thuộc lớp `inetOrgPerson`, ở bộ phận **Engineering hoặc Support**, nhưng **không** có `uid=robot`.

Biểu thức logic:

~~~text
person AND (Engineering OR Support) AND NOT robot
~~~

LDAP filter:

~~~ldap
(&(objectClass=inetOrgPerson)(|(ou=Engineering)(ou=Support))(!(uid=robot)))
~~~

Sơ đồ cây giúp kiểm tra việc nhóm điều kiện:

~~~mermaid
flowchart TD
    A["AND (&)"] --> B["objectClass=inetOrgPerson"]
    A --> C["OR (|)"]
    A --> D["NOT (!)"]
    C --> E["ou=Engineering"]
    C --> F["ou=Support"]
    D --> G["uid=robot"]
~~~

**Phân tích từng entry theo dữ liệu ví dụ:**

| Entry | `inetOrgPerson`? | Engineering/Support? | `uid != robot`? | Kết quả |
| --- | --- | --- | --- | --- |
| Lan | Có | Engineering | Có | Phù hợp. |
| Minh | Có | Support | Có | Phù hợp. |
| An | Có | Finance | Có | Không phù hợp. |
| Robot | Có | Engineering | Không | Không phù hợp. |

Bảng minh họa logic trên các entry có đủ attribute như dữ liệu mẫu. LDAP có thể đánh giá một phép so khớp là không xác định khi thiếu attribute hoặc matching rule không áp dụng; không dùng bảng Boolean đơn giản để suy đoán mọi tình huống thực tế.

### Hai filter gần giống nhưng khác ý nghĩa

~~~ldap
# 1. Person và (Engineering hoặc Support)
(&(objectClass=inetOrgPerson)(|(ou=Engineering)(ou=Support)))

# 2. (Person và Engineering) hoặc Support
(|(&(objectClass=inetOrgPerson)(ou=Engineering))(ou=Support))
~~~

Ở filter 2, nhánh Support **không bắt buộc** thỏa `objectClass=inetOrgPerson`. Đây là lỗi nhóm ngoặc dễ gặp: đặt OR quá cao có thể vô ý nới rộng kết quả. Chú thích `#` bên trên chỉ để giải thích trong code block, **không thuộc cú pháp filter LDAP**; khi gửi query chỉ lấy dòng biểu thức trong ngoặc.

### Định luật De Morgan khi đọc filter lồng nhau

Theo logic Boolean thông thường:

~~~text
NOT (A OR B)  tương đương (NOT A) AND (NOT B)
NOT (A AND B) tương đương (NOT A) OR  (NOT B)
~~~

Cách viết LDAP:

~~~ldap
(!(|(ou=Engineering)(ou=Support)))
~~~

và dạng đã phân phối:

~~~ldap
(&(!(ou=Engineering))(!(ou=Support)))
~~~

Các biến đổi này hữu ích để đọc cấu trúc. Tuy vậy, khi xuất hiện giá trị không xác định, attribute thiếu hoặc matching rule đặc thù, hãy dựa vào **ngữ nghĩa LDAP thực tế** và kiểm thử trên server mục tiêu. Không làm phức tạp filter bằng nhiều tầng phủ định khi có cách biểu diễn nghiệp vụ dễ hiểu hơn.

## 7. Từ biểu thức viết tay sang Spring LDAP

Khi biết trước tên attribute và cấu trúc filter, Spring LDAP cung cấp API xây điều kiện với giá trị được escape. Ví dụ Gradle Kotlin DSL:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-ldap")
}
~~~

Cấu hình một kết nối LDAP:

~~~yaml
spring:
  ldap:
    urls: ${LDAP_URL:ldaps://ldap.example.org:636}
    base: ${LDAP_BASE_DN:dc=example,dc=org}
    username: ${LDAP_BIND_DN}
    password: ${LDAP_BIND_PASSWORD}
~~~

`spring.ldap.base` là gốc dành cho DN tương đối; tài khoản bind cần ACL đọc những entry/attribute được truy vấn. Đừng đưa mật khẩu thật vào mã nguồn và hãy dùng LDAPS hoặc StartTLS được cấu hình/xác minh chứng chỉ phù hợp.

### 7.1. AND đơn giản bằng `LdapQueryBuilder`

~~~java
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;

public LdapQuery byUid(String uid) {
    return LdapQueryBuilder.query()
            .base("ou=people")
            .attributes("uid", "cn", "mail")
            .where("objectClass").is("inetOrgPerson")
            .and("uid").is(uid);
}
~~~

Với `spring.ldap.base=dc=example,dc=org`, base tìm kiếm là `ou=people,dc=example,dc=org`. Builder tạo AND của hai điều kiện; giá trị `uid` được đưa vào `.is(uid)` nên không cần tự ghép chuỗi filter thô.

Khi cần cấu trúc lồng nhau phức tạp, có thể dùng các lớp xây filter từ package `org.springframework.ldap.filter`, sau đó đưa vào `LdapQuery`.

### 7.2. Xây AND, OR và NOT bằng `Filter` objects

~~~java
import org.springframework.ldap.filter.AndFilter;
import org.springframework.ldap.filter.EqualsFilter;
import org.springframework.ldap.filter.NotFilter;
import org.springframework.ldap.filter.OrFilter;

public final class PersonFilterFactory {

    private PersonFilterFactory() {}

    public static AndFilter activeTeamsFilter() {
        OrFilter allowedTeams = new OrFilter();
        allowedTeams.or(new EqualsFilter("ou", "Engineering"));
        allowedTeams.or(new EqualsFilter("ou", "Support"));

        AndFilter all = new AndFilter();
        all.and(new EqualsFilter("objectClass", "inetOrgPerson"));
        all.and(allowedTeams);
        all.and(new NotFilter(new EqualsFilter("uid", "robot")));
        return all;
    }
}
~~~

Filter được biểu diễn bởi các đối tượng:

- `EqualsFilter(attribute, value)` tạo một phép so khớp bằng, có cơ chế encode/escape giá trị filter.
- `AndFilter.and(...)` thêm điều kiện con với AND.
- `OrFilter.or(...)` thêm điều kiện con với OR.
- `NotFilter(...)` phủ định **đúng một filter**; có thể bọc một `OrFilter` hoặc `AndFilter` để phủ định cả nhóm.

Kết quả logic mong đợi tương ứng:

~~~ldap
(&(objectClass=inetOrgPerson)(|(ou=Engineering)(ou=Support))(!(uid=robot)))
~~~

Thứ tự biểu diễn các nhánh con thường không làm thay đổi kết quả logic AND/OR, nhưng nên giữ cấu trúc dễ đọc để review và viết test. Không xem việc tạo `Filter` object là hình thức kiểm tra quyền; filter chỉ tạo điều kiện truy vấn.

### 7.3. Dùng filter lồng nhau với `LdapTemplate`

Ví dụ DTO không trả về toàn bộ entry:

~~~java
public record PersonSummary(String uid, String displayName, String department) {}
~~~

Service:

~~~java
import java.util.List;
import javax.naming.NamingException;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.filter.AndFilter;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;
import org.springframework.stereotype.Service;

@Service
public class PeopleFilterService {
    private final LdapTemplate ldapTemplate;

    public PeopleFilterService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<PersonSummary> findTeamMembers() {
        AndFilter filter = PersonFilterFactory.activeTeamsFilter();

        LdapQuery query = LdapQueryBuilder.query()
                .base("ou=people")
                .attributes("uid", "cn", "ou")
                .countLimit(100)
                .timeLimit(2000)
                .filter(filter);

        return ldapTemplate.search(
                query,
                (AttributesMapper<PersonSummary>) attributes ->
                    new PersonSummary(
                        getString(attributes, "uid"),
                        getString(attributes, "cn"),
                        getString(attributes, "ou")));
    }

    private static String getString(
            Attributes attributes, String attributeName)
            throws NamingException {
        Attribute attribute = attributes.get(attributeName);
        return attribute == null ? null : (String) attribute.get();
    }
}
~~~

`.attributes("uid", "cn", "ou")` yêu cầu chỉ các trường DTO cần. `.countLimit(100)` và `.timeLimit(2000)` đặt giới hạn ở mức truy vấn; chúng không cam kết một lời gọi luôn hoàn thành trong đúng thời gian mong muốn, cũng không chứng minh toàn directory chỉ có 100 entry. Với production, chọn ngưỡng theo SLA, sử dụng phân trang thích hợp khi cần danh sách lớn.

Trường `department` của DTO đến từ thuộc tính `ou` theo **giả định schema cụ thể trong ví dụ**. Nếu directory tổ chức dùng một thuộc tính khác như `departmentNumber` hoặc không lưu phòng ban trong entry người dùng, phải đổi cách ánh xạ.

## 8. OR động: một danh sách đầu vào không biến thành filter thô

Một trường hợp phổ biến là client chọn một tập username để tra cứu. Tạo `OrFilter` từ từng **giá trị** đã kiểm tra thay vì nối chuỗi `(|(uid=...)(uid=...))`:

~~~java
import java.util.List;
import org.springframework.ldap.filter.AndFilter;
import org.springframework.ldap.filter.EqualsFilter;
import org.springframework.ldap.filter.OrFilter;

public AndFilter buildUserListFilter(List<String> requestedUids) {
    if (requestedUids == null
            || requestedUids.isEmpty()
            || requestedUids.size() > 20) {
        throw new IllegalArgumentException(
                "Danh sach uid phai co tu 1 den 20 phan tu");
    }

    OrFilter usernames = new OrFilter();
    for (String uid : requestedUids) {
        if (uid == null || uid.isBlank() || uid.length() > 128) {
            throw new IllegalArgumentException("uid khong hop le");
        }
        usernames.or(new EqualsFilter("uid", uid));
    }

    AndFilter people = new AndFilter();
    people.and(new EqualsFilter("objectClass", "inetOrgPerson"));
    people.and(usernames);
    return people;
}
~~~

Ở đây, **tên thuộc tính `uid` là hằng số do server chọn**. `requestedUids` chỉ được dùng làm *giá trị* trong `EqualsFilter`, để encoder xử lý các ký tự có ý nghĩa đặc biệt theo cú pháp filter. Không dùng user input làm tên attribute hoặc cấu trúc filter.

Giới hạn 20 phần tử và 128 ký tự chỉ là ngưỡng minh họa. Trong sản phẩm thật, nên giới hạn thêm tổng độ dài request, số điều kiện lồng nhau, tần suất gọi API và các loại phép toán được phép, nhằm tránh query quá lớn hoặc gây áp lực cho directory.

### OR rỗng có nghĩa gì?

Nếu caller truyền danh sách rỗng, đừng tự đoán cách thư viện encode một `OrFilter` không có điều kiện. Xác định rõ kết quả nghiệp vụ: **không tìm gì** (trả danh sách rỗng) hoặc **từ chối request**. Ví dụ trên chọn từ chối; với API khác có thể trả rỗng trước khi gọi LDAP. Tuyệt đối không âm thầm chuyển OR rỗng thành truy vấn không có filter để tải cả directory.

## 9. Những ký tự đặc biệt và LDAP filter injection

Giả sử người dùng nhập username có ký tự đặc biệt. Nếu ứng dụng tạo filter thủ công:

~~~java
// Không an toàn: input có thể thay đổi cú pháp/ý nghĩa của filter.
String filter = "(&(objectClass=inetOrgPerson)(uid=" + userInput + "))";
~~~

thì người dùng có thể cố chèn dấu ngoặc, dấu sao hoặc phép toán logic làm filter sai cú pháp hoặc thay đổi điều kiện. **Chỉ kiểm tra user đã đăng nhập không ngăn lỗi này**; mọi input không tin cậy cần được xử lý đúng ngữ cảnh.

RFC 4515 quy định escape các byte đặc biệt trong giá trị assertion:

| Ký tự trong giá trị | Dạng escape của filter |
| --- | --- |
| `*` | `\2a` |
| `(` | `\28` |
| `)` | `\29` |
| `\` | `\5c` |
| Byte NUL | `\00` |

Ví dụ khi cần so khớp *ký tự dấu sao literal* trong một giá trị, cú pháp filter có dạng:

~~~ldap
(uid=lan\2atest)
~~~

Đây là ví dụ cú pháp RFC, không phải username thực trong directory. Khác với `(uid=lan*)`, nơi dấu sao **không escape** mang nghĩa wildcard cho substring filter.

**Trong Spring LDAP, ưu tiên filter builder**:

~~~java
LdapQuery query = LdapQueryBuilder.query()
        .base("ou=people")
        .where("uid").is(userInput);
~~~

Hoặc:

~~~java
EqualsFilter equalsUid = new EqualsFilter("uid", userInput);
~~~

Không tự escape một lần rồi đưa lại vào API đã escape tự động, vì có thể gây **double escaping** và kết quả không khớp. Không lấy giá trị đã escape theo filter đưa vào DN; xây DN bằng `LdapNameBuilder` khi cần, bởi quy tắc escaping DN theo RFC 4514 là khác.

### Filter an toàn chưa đủ: attribute, base và scope

Kể cả `new EqualsFilter(userSuppliedAttribute, value)` có escape *value*, tên thuộc tính do client tự chọn vẫn có thể khiến API tìm kiếm theo trường không được phép. Search base `dc=example,dc=org` và scope `SUBTREE` cũng có thể mở rộng truy vấn tới `ou=services`, mặc dù filter được encode hợp lệ.

Quy tắc:

- **Attribute:** chọn từ allowlist nghiệp vụ do server định nghĩa, không nhận tên thô tùy ý.
- **Base DN:** dùng OU cố định hoặc tập nhánh do service xác định theo quyền người gọi.
- **Search scope:** dùng mức tối thiểu cần thiết, ví dụ `ONELEVEL` khi không cần OU con; chỉ mở rộng `SUBTREE` có điều kiện.
- **Phép toán:** chỉ hỗ trợ OR, NOT, wildcard hoặc tiền tố khi nghiệp vụ thực sự cần; không cung cấp bộ máy LDAP filter tùy ý cho client phổ thông.

## 10. Tác động của base DN, search scope, schema và quyền

Giả sử filter:

~~~ldap
(|(uid=lan)(uid=minh))
~~~

Những truy vấn sau có thể khác kết quả:

| Base DN | Search scope | Điều kiện | Khả năng quan sát |
| --- | --- | --- | --- |
| `ou=people,dc=example,dc=org` | ONELEVEL | Hai entry nằm trực tiếp dưới People. | Có thể trả Lan và Minh. |
| `ou=people,dc=example,dc=org` | OBJECT | Chỉ kiểm tra chính OU People. | Không trả entry con Lan/Minh. |
| `ou=people,dc=example,dc=org` | SUBTREE | Bao gồm OU con. | Có thể thêm entry trùng uid ở nhánh sâu hơn, nếu có. |
| `ou=groups,dc=example,dc=org` | SUBTREE | Chỉ tìm dưới Groups. | Không trả Lan/Minh ở People. |

Thêm `(&(objectClass=inetOrgPerson)... )` giúp làm rõ loại entry cần trả, nhưng không thay thế được việc chọn **base và scope đúng**. Nếu LDAP ACL ẩn entry hoặc thuộc tính khỏi tài khoản dịch vụ, kết quả có thể rỗng hoặc khác dự đoán. Tương tự, schema quyết định thuộc tính có tồn tại và matching rule được áp dụng ra sao.

Với cây lớn, dùng nhiều OR với wildcard và NOT trên một base rộng dễ gây truy vấn đắt đỏ. Ưu tiên giới hạn base, filter có điều kiện cụ thể, projection nhỏ, search size/time limit và phân trang theo khả năng server.

## 11. Thử filter với `ldapsearch`

Trên directory thử nghiệm có quyền đọc, dùng OpenLDAP client để đối chiếu filter:

~~~bash
ldapsearch -LLL -x \
  -H "ldaps://ldap.example.org:636" \
  -D "cn=app-reader,ou=services,dc=example,dc=org" -W \
  -b "ou=people,dc=example,dc=org" -s sub \
  "(&(objectClass=inetOrgPerson)(|(ou=Engineering)(ou=Support))(!(uid=robot)))" \
  dn uid cn ou
~~~

Giải thích:

- `-H` chọn endpoint LDAPS; kiểm tra chứng chỉ và kho tin cậy.
- `-D` chọn DN tài khoản kết nối, `-W` nhập mật khẩu tương tác.
- `-b` là base DN, `-s sub` tìm toàn bộ cây con.
- Biểu thức filter được đặt trong dấu nháy kép để shell không diễn giải dấu ngoặc và ký tự đặc biệt.
- Cuối lệnh chỉ yêu cầu trả `dn`, `uid`, `cn` và `ou`.

Hãy thử từng phần:

~~~bash
# 1. Tìm entry Lan theo một điều kiện.
ldapsearch -LLL -x -H "ldaps://ldap.example.org:636" \
  -D "cn=app-reader,ou=services,dc=example,dc=org" -W \
  -b "ou=people,dc=example,dc=org" -s sub \
  "(uid=lan)" dn uid cn ou

# 2. Dùng OR để tìm Lan hoặc Minh.
ldapsearch -LLL -x -H "ldaps://ldap.example.org:636" \
  -D "cn=app-reader,ou=services,dc=example,dc=org" -W \
  -b "ou=people,dc=example,dc=org" -s sub \
  "(|(uid=lan)(uid=minh))" dn uid cn ou

# 3. Dùng AND, OR, NOT trong cùng một truy vấn.
ldapsearch -LLL -x -H "ldaps://ldap.example.org:636" \
  -D "cn=app-reader,ou=services,dc=example,dc=org" -W \
  -b "ou=people,dc=example,dc=org" -s sub \
  "(&(objectClass=inetOrgPerson)(|(ou=Engineering)(ou=Support))(!(uid=robot)))" \
  dn uid cn ou
~~~

Các ví dụ yêu cầu người học có quyền và dữ liệu thử nghiệm tương ứng. Không truy vấn directory sản xuất ngoài phạm vi được cấp phép. `ldapsearch` thành công chứng minh tài khoản bind có khả năng đọc kết quả ở điều kiện đó; nó không chứng minh người gọi HTTP trong ứng dụng đã được **Spring Security** cấp phép xem các entry này.

### Kết quả rỗng không nhất thiết do logic AND/OR sai

Khi một filter trả rỗng, kiểm tra theo thứ tự:

1. URL LDAP, TLS và bind DN có đúng không?
2. Base DN và scope có bao phủ entry cần tìm không?
3. Attribute như `ou` có thực sự nằm trên entry hay chỉ xuất hiện trong DN?
4. Schema/`objectClass` và matching rule có khớp dữ liệu không?
5. ACL có cho tài khoản dịch vụ nhìn thấy các entry/thuộc tính không?
6. Có áp dụng quá nhiều điều kiện AND hoặc đặt OR sai cấp ngoặc không?
7. Query có bị size/time limit hay lỗi kết nối thay vì thật sự không có kết quả không?

Đừng tự bỏ điều kiện phân quyền hoặc chuyển search base thành toàn bộ gốc directory để “sửa” một truy vấn rỗng trước khi xác định nguyên nhân.

## 12. Kiểm thử logic và bảo mật filter

### 12.1. Ma trận dữ liệu thử nghiệm

Chuẩn bị các entry trong directory thử nghiệm với những đặc điểm:

| UID | `objectClass` | `ou` | `mail` | Dự kiến với filter ở mục 6 |
| --- | --- | --- | --- | --- |
| `lan` | `inetOrgPerson` | Engineering | Có | Trả về. |
| `minh` | `inetOrgPerson` | Support | Có | Trả về. |
| `an` | `inetOrgPerson` | Finance | Có | Không trả về. |
| `robot` | `inetOrgPerson` | Engineering | Có | Không trả về vì NOT. |
| `mai` | `inetOrgPerson` | Support | Thiếu | Trả về nếu filter không yêu cầu `mail=*`. |

Sau đó thêm `(mail=*)` vào AND và xác minh entry Mai không còn được trả (theo giả định directory chứa entry và ACL cho đọc các trường). Đây là cách kiểm chứng **sự hiện diện attribute là một điều kiện riêng**, không nên tự thêm vào logic một cách ngầm định.

### 12.2. Unit test cách xây filter

Với lớp `PersonFilterFactory`, có thể kiểm tra encode trong JUnit 5:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

class PersonFilterFactoryTest {

    @Test
    void encodesAndOrNotTree() {
        assertEquals(
                "(&(objectClass=inetOrgPerson)"
                + "(|(ou=Engineering)(ou=Support))"
                + "(!(uid=robot)))",
                PersonFilterFactory.activeTeamsFilter().encode());
    }
}
~~~

Nếu implementation thay đổi thứ tự encode của các điều kiện con, test so sánh chuỗi cần được điều chỉnh theo hợp đồng thư viện; trong kiểm thử tích hợp, **điều quan trọng nhất là kết quả logic**, không chỉ chuỗi hiển thị. Code test minh họa yêu cầu JUnit 5 và các class cùng package hoặc imports phù hợp.

### 12.3. Những tình huống nên kiểm thử thêm

| Dữ liệu/điều kiện | Kỳ vọng |
| --- | --- |
| `(&(uid=lan)(objectClass=inetOrgPerson))` | Chỉ entry thỏa cả hai điều kiện. |
| `(\|(uid=lan)(uid=minh))` | Có thể trả cả Lan và Minh nếu cùng nằm trong base/scope và ACL cho phép. |
| `(!(uid=robot))` | Không bao gồm entry thỏa equality với `uid=robot`; cần chính sách rõ khi thuộc tính thiếu. |
| `(&(mail=*)(!(mail=lan@example.org)))` | Chỉ entry có mail và không khớp email bị loại theo matching rule. |
| `(!(|(ou=Engineering)(ou=Support)))` | Không bao gồm entry thỏa ít nhất một trong hai điều kiện bên trong. |
| `uid` chứa `*`, `(`, `)`, `\` | Giá trị được escape khi qua filter builder, không biến thành toán tử hoặc thay đổi cây filter. |
| Danh sách OR rỗng hoặc hơn 20 username | Được từ chối hoặc xử lý theo chính sách đã định, không gửi truy vấn không giới hạn. |
| User cố chọn attribute `userPassword` hoặc base `ou=services` | API từ chối trước khi gọi LDAP nếu không nằm trong allowlist/quyền. |
| Nhiều OR cùng filter quá rộng | Thực thi trong giới hạn time/count/rate; không coi kết quả bị cắt là đầy đủ. |

**Không xem unit test của chuỗi filter là đủ để kiểm chứng an toàn:** cần kiểm thử tích hợp với server thật hoặc container directory thử nghiệm, cùng schema/ACL/base/scope, bởi kết quả có thể chịu ảnh hưởng matching rule và cách server xử lý thuộc tính không tồn tại.

## 13. Lỗi thường gặp

| Lỗi | Ví dụ | Cách sửa |
| --- | --- | --- |
| Dùng cú pháp SQL thay LDAP. | `(uid=lan AND ou=Engineering)` | `(&(uid=lan)(ou=Engineering))`. |
| Thiếu ngoặc của từng filter con. | `(&(uid=lan)ou=Engineering)` | `(&(uid=lan)(ou=Engineering))`. |
| Nhầm AND với OR. | `(&(uid=lan)(uid=minh))` khi muốn hai tài khoản khác nhau. | `(\|(uid=lan)(uid=minh))`. |
| Đặt OR ở ngoài làm nới kết quả. | `(\|(&(objectClass=inetOrgPerson)(ou=Engineering))(ou=Support))` | `(&(objectClass=inetOrgPerson)(\|(ou=Engineering)(ou=Support)))`. |
| Hiểu NOT là “thuộc tính có giá trị khác” bất kể có tồn tại. | `(!(mail=lan@example.org))` | Nếu bắt buộc có mail, thêm `(mail=*)` trong AND. |
| Nối input thành filter thô. | `"(uid=" + uid + ")"` | `where("uid").is(uid)` hoặc `new EqualsFilter("uid", uid)`. |
| Để người dùng chọn field/filter tùy ý. | `new EqualsFilter(request.field, value)` | Attribute/logic từ allowlist của ứng dụng. |
| Bỏ qua giới hạn base/scope. | Tìm `SUBTREE` từ directory root cho chức năng danh bạ. | Đặt base hẹp và scope cần thiết, giới hạn count/time. |
| Cho rằng tìm thấy entry đồng nghĩa đã xác thực người gọi. | `findByUid("lan")` trả entry nên xem caller là Lan. | Xác thực/authorization riêng bằng Spring Security và LDAP ACL. |

## 14. Bài tập tình huống

Một ứng dụng nhân sự có các entry ở `ou=employees,dc=company,dc=internal` với thuộc tính `uid`, `ou`, `mail`, `objectClass`. Các yêu cầu:

1. Tìm **tất cả `inetOrgPerson`** ở Engineering có email.
2. Tìm nhân viên có `uid=mai` **hoặc** `uid=binh`.
3. Tìm người dùng thuộc Engineering **hoặc** Support, **không** có `uid=service-bot`.
4. Tìm entry có `mail` nhưng không bằng `test@company.internal`.
5. Lọc **NOT (Engineering OR Support)** và giải thích nhóm dấu ngoặc.
6. Tạo filter cho một danh sách username không vượt quá 20 phần tử bằng Spring LDAP `OrFilter` và `EqualsFilter`, không nối chuỗi input.
7. Dự đoán sai sót nếu dùng `(|(&(objectClass=inetOrgPerson)(ou=Engineering))(ou=Support))` thay cho `(&(objectClass=inetOrgPerson)(|(ou=Engineering)(ou=Support)))`.
8. Nêu vì sao vẫn cần giới hạn base DN, search scope, attribute trả về và authorization HTTP ngay cả khi filter được escape đúng.

**Gợi ý đáp án:**

~~~ldap
# 1. Person ở Engineering, có email
(&(objectClass=inetOrgPerson)(ou=Engineering)(mail=*))

# 2. Hai username
(|(uid=mai)(uid=binh))

# 3. Engineering/Support, loại bot
(&(objectClass=inetOrgPerson)(|(ou=Engineering)(ou=Support))(!(uid=service-bot)))

# 4. Có email và khác một giá trị
(&(mail=*)(!(mail=test@company.internal)))

# 5. Phủ định cả nhóm OR
(!(|(ou=Engineering)(ou=Support)))
~~~

Các dòng bắt đầu bằng `#` là **chú thích trong tài liệu**, không phải một phần LDAP filter khi gửi đến server. Với câu 6, lặp từng username đã kiểm tra để tạo `new EqualsFilter("uid", uid)` trong `OrFilter`, rồi AND với `(objectClass=inetOrgPerson)`; từ chối danh sách rỗng/quá dài. Ở câu 7, nhánh Support của filter sai không bắt buộc `objectClass=inetOrgPerson`. Ở câu 8, escaping chỉ bảo vệ cú pháp **giá trị filter**: chính sách truy cập, phạm vi tìm kiếm và độ nhạy cảm của dữ liệu phải do server và directory kiểm soát.

## 15. Ghi nhớ

LDAP filter dùng **`&` cho AND**, **`|` cho OR** và **`!` cho NOT**, theo cú pháp tiền tố với dấu ngoặc chứa các filter con. Cách nhóm là yếu tố quyết định: `(&(A)(|(B)(C))(!(D)))` diễn đạt **A và (B hoặc C) và không D**. Đối với điều kiện “có thuộc tính và khác X”, hãy viết rõ presence filter `(attr=*)` cùng NOT.

Trong Spring Data LDAP, dùng `LdapQueryBuilder` hoặc các lớp `AndFilter`/`OrFilter`/`NotFilter`/`EqualsFilter` của Spring LDAP để xây điều kiện và escape giá trị đúng ngữ cảnh, thay vì nối chuỗi input. Kết quả truy vấn còn phụ thuộc **base DN, scope, schema/`objectClass`, matching rule, ACL, TLS và giới hạn truy vấn**. Một filter đúng cú pháp chưa thay thế kiểm tra quyền hay xác thực người dùng.

### Tài liệu tham khảo

- [RFC 4515 — LDAP: String Representation of Search Filters](https://www.rfc-editor.org/rfc/rfc4515)
- [RFC 4511 — LDAP: The Protocol, Search Filter](https://www.rfc-editor.org/rfc/rfc4511#section-4.5.1)
- [Spring LDAP Reference — Query Builder](https://docs.spring.io/spring-ldap/reference/query-builder-advanced.html)
- [Spring LDAP Reference — Basic Usage](https://docs.spring.io/spring-ldap/reference/basic.html)
- [Spring Data LDAP Reference](https://docs.spring.io/spring-data/ldap/reference/)
