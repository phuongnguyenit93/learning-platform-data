# LdapQueryBuilder với base, scope và attributes

Khi truy vấn LDAP qua Spring LDAP, viết đúng filter mới chỉ giải quyết một phần vấn đề. Một truy vấn còn phải biết **bắt đầu tìm từ entry nào (base)**, **đi sâu đến đâu trong Directory Information Tree (scope)** và **yêu cầu server trả lại các thuộc tính nào (attributes)**. Nếu nhầm ba tham số này, ứng dụng có thể không tìm thấy entry, tìm quá rộng, trả về dữ liệu không cần thiết hoặc làm chậm LDAP server.

Trong chương **Query builder** của mô-đun **SPRING_LDAP**, chúng ta sử dụng `LdapQueryBuilder` để tổ chức các tham số tìm kiếm, kết hợp `LdapTemplate` hoặc `LdapClient` và ánh xạ kết quả. Bài này đặt trọng tâm vào `base(...)`, `searchScope(...)`, `attributes(...)`; filter, giới hạn kết quả, DN escaping và bảo mật được minh họa ở những điểm cần thiết để truy vấn hoạt động đúng.

**Sau bài học, bạn có thể:**

- Xác định đúng DN nền và biểu diễn **DN tương đối** với `ContextSource.base`.
- Chọn đúng ba `SearchScope` của Spring LDAP: `OBJECT`, `ONELEVEL` và `SUBTREE`.
- Dùng `attributes(String...)` để yêu cầu các trường cần thiết, hiểu khác biệt giữa **lọc entry** và **chọn thuộc tính trả về**.
- Viết một `LdapQuery` hoàn chỉnh bằng `LdapQueryBuilder.query()` rồi chuyển cho `LdapTemplate.search(...)` hoặc `LdapClient`.
- Phân biệt tham số mặc định và tham số đặt tường minh; hiểu vì sao phải thiết lập cấu hình query **trước** filter.
- Kiểm tra hành vi khi base không tồn tại, thuộc tính bị thiếu, schema/ACL hạn chế, giới hạn kết quả và dữ liệu phân cấp nhiều cấp.

## 1. Một truy vấn LDAP gồm những phần nào?

Giả sử LDAP server có DIT:

```text
dc=example,dc=org
├── ou=People
│   ├── uid=an
│   ├── uid=binh
│   └── ou=Engineering
│       ├── uid=chi
│       └── uid=dung
└── ou=Groups
    └── cn=Engineering
```

Mỗi dòng trong sơ đồ chỉ ghi **RDN**; DN đầy đủ của Chi là:

```text
uid=chi,ou=Engineering,ou=People,dc=example,dc=org
```

Yêu cầu nghiệp vụ: “Tìm người dùng nằm dưới nhánh People, kể cả các OU con; chỉ lấy mã người dùng và tên hiển thị”.

Truy vấn có thể được diễn giải thành:

| Thành phần | Giá trị | Tác dụng |
| --- | --- | --- |
| Base DN | `ou=People,dc=example,dc=org` | Bắt đầu ở nhánh People |
| Search scope | `SUBTREE` | Xét chính base và toàn bộ entry con cháu |
| Filter | `(objectClass=inetOrgPerson)` | Chỉ lấy entry kiểu người dùng |
| Attributes | `uid`, `cn` | Trả về đúng các trường ứng dụng cần |
| Count/time limits | Tùy use case | Khống chế số entry và thời gian tìm kiếm |

Đối chiếu với mã Spring LDAP:

```java
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.SearchScope;

import static org.springframework.ldap.query.LdapQueryBuilder.query;

LdapQuery peopleQuery = query()
    .base("ou=People")
    .searchScope(SearchScope.SUBTREE)
    .attributes("uid", "cn")
    .where("objectClass").is("inetOrgPerson");
```

Đoạn code giả định `ContextSource` có `base = dc=example,dc=org`, nên `.base("ou=People")` là phần DN **tương đối**. Lưu ý thứ tự: các tham số tìm kiếm (`base`, `scope`, `attributes`) được thiết lập **trước** `where(...)`.

`LdapQuery` chứa thông tin về việc tìm ở đâu, đi sâu bao nhiêu, lấy thuộc tính nào và filter ra sao. Đối tượng đó được đưa vào một API thực thi, ví dụ `ldapTemplate.search(peopleQuery, mapper)`. **Tạo `LdapQuery` chưa gửi truy vấn đến server.**

## 2. Cấu trúc của `LdapQueryBuilder`

Spring LDAP cung cấp:

```java
org.springframework.ldap.query.LdapQueryBuilder
org.springframework.ldap.query.LdapQuery
org.springframework.ldap.query.SearchScope
```

Những phương thức cấu hình quan trọng:

| API | Ý nghĩa |
| --- | --- |
| `LdapQueryBuilder.query()` | Bắt đầu dựng truy vấn |
| `base(String dn)` | Đặt search base từ DN dạng chuỗi |
| `base(Name dn)` | Đặt search base từ đối tượng `javax.naming.Name` |
| `searchScope(SearchScope scope)` | Đặt độ sâu tìm kiếm |
| `attributes(String... names)` | Yêu cầu tên các thuộc tính cần trả về |
| `countLimit(int count)` | Giới hạn số entry phía client yêu cầu |
| `timeLimit(int time)` | Giới hạn thời gian theo API JNDI/Spring LDAP |
| `where(String attribute)` | Bắt đầu điều kiện filter |
| `filter(...)` | Cung cấp filter từ chuỗi, mẫu có tham số hoặc đối tượng `Filter` |

Một truy vấn hoàn chỉnh:

```java
LdapQuery query = LdapQueryBuilder.query()
    .base("ou=People")
    .searchScope(SearchScope.ONELEVEL)
    .attributes("uid", "cn", "mail")
    .countLimit(100)
    .timeLimit(3000)
    .where("objectClass").is("inetOrgPerson");
```

Ở đây `countLimit(100)` đặt ngưỡng 100 **entry**, `timeLimit(3000)` tương ứng 3.000 **mili giây** trong API JNDI; giới hạn cuối cùng còn chịu chính sách server. Đây không phải cơ chế phân trang.

### 2.1. Quy tắc thứ tự: cấu hình trước, filter sau

Theo contract của `LdapQueryBuilder`, việc dựng truy vấn theo thứ tự:

```text
LdapQueryBuilder.query()
      |
      +--> base / searchScope / attributes / countLimit / timeLimit
      |
      +--> where(...) / filter(...) 
      |
      +--> toán tử hoặc điều kiện filter tiếp theo
      |
      +--> LdapQuery dùng cho search
```

Sau khi đã gọi `where(...)` để bắt đầu filter, builder **không cho cấu hình lại các tham số nền** như `base`. Vì vậy hãy quyết định phạm vi và các thuộc tính cần đọc trước rồi mới thêm filter.

Hai cách chỉ định filter chính:

```java
// Cách 1: Criteria có escaping cho assertion value.
LdapQuery byUid = query()
    .base("ou=People")
    .attributes("uid", "cn")
    .where("uid").is(userInput);

// Cách 2: Filter cố định, chỉ dùng khi nội dung được kiểm soát.
LdapQuery allPeople = query()
    .base("ou=People")
    .attributes("uid", "cn")
    .filter("(objectClass=inetOrgPerson)");
```

Không trộn `.filter(...)` với `.where(...)` trên cùng một query; Spring LDAP coi chúng là hai cách khai báo filter thay thế nhau. Đặc biệt, overload `filter(String hardcodedFilter)` **không tự escape** dữ liệu đầu vào. Khi nhận dữ liệu từ người dùng, ưu tiên `where(...).is(...)` hoặc overload filter có binding tham số.

### 2.2. Mặc định cần hiểu rõ

Nếu không gọi `base(...)`, query builder mặc định dùng **DN tương đối rỗng**, tương ứng base đã được `ContextSource` cấu hình. Với `searchScope`, `attributes`, `timeLimit` và `countLimit` không được khai báo, giá trị của chúng có thể được để **chưa xác định** cho `LdapTemplate` áp dụng mặc định của nó.

Những lưu ý thực tế:

- Không chỉ định `base` **không có nghĩa search bắt đầu từ Root DSE**. Nếu `ContextSource.base` là `dc=example,dc=org`, điểm bắt đầu thường là suffix đó.
- Không chỉ định `attributes` thường làm truy vấn lấy danh sách user attributes mặc định; operational attributes thường **không tự xuất hiện**.
- Không chỉ định `searchScope` có thể áp dụng mặc định của template (thường là subtree); code cần hành vi chắc chắn nên khai báo tường minh.
- Query builder yêu cầu **một filter**. Nếu muốn xét mọi entry theo kiểu presence, có thể dùng `.where("objectClass").isPresent()` trong vùng dữ liệu phù hợp.

## 3. `base(...)`: bắt đầu tìm ở đâu?

LDAP có cấu trúc dạng cây. `base` chỉ rõ **entry bắt đầu** mà phép tìm kiếm dựa vào để xác định phạm vi.

Giả sử:

```java
contextSource.setBase("dc=example,dc=org");
```

Thì:

| `LdapQueryBuilder.base(...)` | Base DN đầy đủ được nhắm tới |
| --- | --- |
| `base("")` | `dc=example,dc=org` |
| `base("ou=People")` | `ou=People,dc=example,dc=org` |
| `base("ou=Engineering,ou=People")` | `ou=Engineering,ou=People,dc=example,dc=org` |
| `base("ou=Groups")` | `ou=Groups,dc=example,dc=org` |

### 3.1. DN tương đối và lỗi lặp suffix

Lỗi điển hình:

```java
// ContextSource.base đã là "dc=example,dc=org".
LdapQuery wrong = query()
    .base("ou=People,dc=example,dc=org")
    .where("objectClass").is("inetOrgPerson");
```

Trong cấu hình ContextSource có base, cách dùng trên **có thể khiến suffix bị nối lặp** (thành một đường dẫn không đúng) và gây lỗi không tìm thấy. Dùng:

```java
LdapQuery correct = query()
    .base("ou=People")
    .where("objectClass").is("inetOrgPerson");
```

Nếu `ContextSource` không đặt base, search base sẽ phải bao gồm phần DN mà server yêu cầu, tùy kiến trúc kết nối. **Đừng dùng đồng thời DN tương đối và DN đầy đủ mà không biết quy tắc cấu hình.**

### 3.2. Dùng `base(Name)` khi giá trị đến từ input

`base(String)` phù hợp với DN cố định, đã hợp lệ. Nếu một phần DN được tạo từ dữ liệu đầu vào, dùng `LdapNameBuilder` để escape giá trị RDN đúng cách:

```java
import javax.naming.Name;
import org.springframework.ldap.support.LdapNameBuilder;

Name departmentBase = LdapNameBuilder.newInstance()
    .add("ou", "People")
    .add("ou", departmentOu)
    .build();

LdapQuery departmentQuery = query()
    .base(departmentBase)
    .searchScope(SearchScope.SUBTREE)
    .attributes("uid", "cn")
    .where("objectClass").is("inetOrgPerson");
```

Với `departmentOu = "Engineering"`, base tương đối là `ou=Engineering,ou=People`. Nếu giá trị có dấu phẩy, dấu cộng hoặc ký tự đặc biệt khác, builder mã hóa chúng như **giá trị RDN**.

Tuy nhiên, escaping **không thay cho kiểm tra nghiệp vụ**. Nếu người dùng chỉ được tìm trong một số OU, ứng dụng vẫn phải xác minh `departmentOu` có trong danh sách cho phép và tài khoản bind có quyền phù hợp. Không nhận DN tùy ý từ request để mở rộng tìm kiếm ngoài phạm vi dự kiến.

### 3.3. Search base phải tồn tại?

Trong LDAP search thông thường, search base là **entry thực tế**. Nếu base không tồn tại, server có thể trả `noSuchObject`; Spring LDAP thường chuyển lỗi liên quan thành `NameNotFoundException`, trừ khi template được cấu hình bỏ qua lỗi đó trong một số thao tác.

Đừng nhầm:

- **Base tồn tại, filter không khớp** → một search thành công có thể trả danh sách rỗng.
- **Base không tồn tại** → search có thể thất bại với lỗi DN/search base.
- **Base hoặc entry không hiển thị do ACL** → kết quả có thể phụ thuộc quyền người bind.

Không dùng danh sách rỗng để kết luận chắc chắn “user không tồn tại” khi còn lỗi search hoặc ACL chưa được kiểm tra.

## 4. `searchScope(...)`: tìm sâu đến cấp nào?

Spring LDAP định nghĩa enum:

```java
org.springframework.ldap.query.SearchScope
```

Các giá trị được JavaDoc cung cấp là **`OBJECT`, `ONELEVEL` và `SUBTREE`**.

| Scope Spring LDAP | Scope LDAP tương ứng | Entry được xét từ base |
| --- | --- | --- |
| `SearchScope.OBJECT` | baseObject | **Chỉ chính entry base** |
| `SearchScope.ONELEVEL` | singleLevel | **Chỉ các con trực tiếp**, không bao gồm base |
| `SearchScope.SUBTREE` | wholeSubtree | **Base và mọi cấp hậu duệ** |

**Đừng sử dụng `SearchScope.BASE` trong ví dụ Java:** tên enum của Spring LDAP là **`OBJECT`**, dù ở mức LDAP protocol và một số công cụ thường gọi “base search”.

### 4.1. So sánh bằng một DIT cụ thể

Xét lại:

```text
ou=People,dc=example,dc=org           <-- base
├── uid=an
├── uid=binh
└── ou=Engineering
    ├── uid=chi
    └── uid=dung
```

Giả sử tất cả `uid` là `inetOrgPerson`, còn `ou=People` và `ou=Engineering` là `organizationalUnit`.

Với base `ou=People`:

| Scope | Những entry được **xét** | Nếu filter là `(objectClass=inetOrgPerson)` |
| --- | --- | --- |
| `OBJECT` | Chỉ `ou=People` | Không trả user vì base là OU |
| `ONELEVEL` | `uid=an`, `uid=binh`, `ou=Engineering` | Trả **An, Bình** |
| `SUBTREE` | `ou=People` và toàn bộ entry con/cháu | Trả **An, Bình, Chi, Dũng** |

Điểm cần phân biệt: **scope quyết định tập entry được xét**, còn **filter quyết định entry nào trong phạm vi đó khớp**. Đừng coi tất cả entry trong scope đều sẽ được trả về.

### 4.2. Ví dụ `OBJECT`

Khi chỉ muốn đọc thông tin của chính OU People (không lấy user dưới nhánh), có thể dùng:

```java
LdapQuery peopleOu = query()
    .base("ou=People")
    .searchScope(SearchScope.OBJECT)
    .attributes("ou", "description")
    .where("objectClass").is("organizationalUnit");
```

Khi đã biết DN chính xác của một entry cần đọc, `LdapTemplate.lookup(...)` thường là lựa chọn đơn giản hơn. `OBJECT` hữu ích nếu muốn vẫn sử dụng cú pháp search/filter trên đúng entry base.

### 4.3. Ví dụ `ONELEVEL`

Liệt kê các user được đặt trực tiếp dưới People, không bao gồm user trong OU Engineering:

```java
LdapQuery directPeople = query()
    .base("ou=People")
    .searchScope(SearchScope.ONELEVEL)
    .attributes("uid", "cn")
    .where("objectClass").is("inetOrgPerson");
```

Đây là lựa chọn phù hợp khi ứng dụng muốn danh sách **con trực tiếp của một container LDAP**, không phải tất cả descendants.

### 4.4. Ví dụ `SUBTREE`

Tìm cả user dưới các OU con:

```java
LdapQuery allPeople = query()
    .base("ou=People")
    .searchScope(SearchScope.SUBTREE)
    .attributes("uid", "cn")
    .where("objectClass").is("inetOrgPerson");
```

`SUBTREE` có thể phù hợp với cấu trúc OU lồng nhau, nhưng khi DIT rất lớn, cần cân nhắc chỉ mục, filter đủ chọn lọc, giới hạn số kết quả và khả năng phân trang. Đừng dùng toàn bộ suffix `dc=example,dc=org` cho mọi truy vấn nếu nghiệp vụ chỉ cần nhánh nhỏ hơn.

## 5. `attributes(...)`: chọn những thuộc tính nào được trả về?

`LdapQueryBuilder.attributes(String... attributesToReturn)` khai báo **danh sách attribute selection** trong LDAP SearchRequest.

Ví dụ:

```java
LdapQuery q = query()
    .base("ou=People")
    .searchScope(SearchScope.SUBTREE)
    .attributes("uid", "cn", "mail")
    .where("departmentNumber").is("ENG");
```

Server dùng filter `(departmentNumber=ENG)` để xác định entry khớp, nhưng client chỉ yêu cầu giá trị `uid`, `cn`, `mail` trong những entry được trả về.

**Thuộc tính dùng để lọc không bắt buộc phải nằm trong danh sách thuộc tính được trả về.** Ở ví dụ trên, `departmentNumber` có thể được server dùng khi lọc nhưng không xuất hiện trong `Attributes` mà mapper nhận được.

### 5.1. Attribute selection không thay đổi filter

| Thành phần | Câu hỏi nó trả lời |
| --- | --- |
| `.where("departmentNumber").is("ENG")` | Entry nào phù hợp điều kiện? |
| `.attributes("uid", "cn", "mail")` | Với entry phù hợp, client muốn đọc trường nào? |
| `.base("ou=People")` | Bắt đầu tìm từ đâu? |
| `.searchScope(SearchScope.SUBTREE)` | Xét đến độ sâu nào? |

Một hiểu nhầm phổ biến là `.attributes("mail")` sẽ lọc ra entry **có mail**. Không đúng: nó chỉ yêu cầu trả về `mail` nếu có và được phép đọc. Nếu muốn chọn entry có mail, hãy bổ sung điều kiện presence:

```java
LdapQuery withMail = query()
    .base("ou=People")
    .searchScope(SearchScope.SUBTREE)
    .attributes("uid", "mail")
    .where("objectClass").is("inetOrgPerson")
    .and("mail").isPresent();
```

Khi server không cho quyền đọc `mail`, entry có thể vẫn khớp filter theo chính sách server nhưng client không nhận được giá trị `mail`. Không giả định giá trị một attribute luôn xuất hiện trong kết quả chỉ vì tên đã được liệt kê.

### 5.2. Giá trị mặc định và operational attributes

LDAP phân biệt **user/application attributes** với **operational attributes** do hệ thống duy trì, ví dụ `modifyTimestamp` hoặc `creatorsName`.

Theo giao thức LDAP và lựa chọn thuộc tính RFC 3673:

| Lựa chọn | Ý nghĩa |
| --- | --- |
| Không đặt danh sách `attributes` | Thường yêu cầu các user attributes mặc định |
| `attributes("uid", "cn")` | Chỉ yêu cầu các trường này |
| `attributes("*")` | Yêu cầu tất cả user/application attributes |
| `attributes("+")` | Yêu cầu các operational attributes nếu server hỗ trợ selector `+` và ACL cho phép |
| `attributes("*", "+")` | Yêu cầu hai nhóm attribute, trong giới hạn server/ACL |
| `attributes("cn", "modifyTimestamp")` | Yêu cầu cụ thể một user attribute và một operational attribute |
| `attributes("1.1")` | Selector chuẩn mang nghĩa không yêu cầu attribute nào (khi dùng riêng) |

Trong thực tế, **yêu cầu cụ thể tên các trường cần dùng** thường dễ kiểm soát hơn là xin toàn bộ `*` và `+`. Dữ liệu thư mục có thể nhạy cảm, kích thước lớn hoặc chứa các attribute đa trị.

### 5.3. DN không phải một attribute thông thường

DN định danh entry được trả về trong `SearchResultEntry`; nó không nhất thiết nằm trong danh sách `Attributes` như `uid` hoặc `mail`. Vì vậy:

- Không kỳ vọng `attrs.get("dn")` tự trả DN của entry.
- Nếu cần DN của kết quả, sử dụng API ánh xạ context/result phù hợp, chẳng hạn `ContextMapper` hoặc `DirContextAdapter` với contract của phiên bản Spring LDAP đang dùng.
- Một số server có operational attribute như `entryDN`, nhưng đó **không phải** cách portable duy nhất để lấy tên của entry.

`AttributesMapper` chủ yếu hữu ích khi chỉ cần các giá trị attribute; `ContextMapper` phù hợp khi cần thêm thông tin context/DN.

### 5.4. Attribute đa trị và mapper

Một entry có thể có nhiều giá trị `mail` hoặc `member`. Dù `attributes("mail")` chỉ yêu cầu **một loại thuộc tính**, server có thể trả **nhiều giá trị** của loại đó. Đừng gọi `attrs.get("mail").get()` rồi cho rằng đã lấy mọi email. Phải duyệt tập giá trị bằng API `Attribute`.

Thứ tự trả về của các giá trị đa trị cũng không nên được coi là thứ tự nghiệp vụ, trừ khi có cơ chế riêng đã được tài liệu hệ thống xác nhận.

## 6. Ví dụ hoàn chỉnh với `LdapTemplate`

Giả sử ứng dụng có `ContextSource.base = dc=example,dc=org` và dùng `LdapTemplate` đã được Spring cấu hình. Bài toán: lấy danh sách người dùng thuộc phòng `ENG` dưới toàn bộ nhánh People, trả `uid`, `cn` và các email có thể có; không cần tải các thuộc tính khác.

Ví dụ Java 17+ để dùng `record` làm DTO:

```java
import java.util.ArrayList;
import java.util.List;
import javax.naming.NamingException;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;

import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.SearchScope;

import static org.springframework.ldap.query.LdapQueryBuilder.query;

public final class PeopleRepository {

    public record PersonRow(
        String uid, String commonName, List<String> emails) {}

    private final LdapTemplate ldapTemplate;

    public PeopleRepository(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<PersonRow> findByDepartment(String departmentCode) {
        LdapQuery ldapQuery = query()
            .base("ou=People")
            .searchScope(SearchScope.SUBTREE)
            .attributes("uid", "cn", "mail")
            .countLimit(100)
            .timeLimit(3000)
            .where("objectClass").is("inetOrgPerson")
            .and("departmentNumber").is(departmentCode);

        return ldapTemplate.search(
            ldapQuery,
            (AttributesMapper<PersonRow>) attrs ->
                new PersonRow(
                    first(attrs, "uid"),
                    first(attrs, "cn"),
                    values(attrs, "mail")
                )
        );
    }

    private static String first(Attributes attrs, String name)
            throws NamingException {
        Attribute a = attrs.get(name);
        return a == null || a.size() == 0
            ? null : String.valueOf(a.get(0));
    }

    private static List<String> values(Attributes attrs, String name)
            throws NamingException {
        Attribute a = attrs.get(name);
        List<String> result = new ArrayList<>();
        if (a == null) {
            return result;
        }
        for (int i = 0; i < a.size(); i++) {
            result.add(String.valueOf(a.get(i)));
        }
        return result;
    }
}
```

Giải thích theo từng phần:

1. `base("ou=People")`: giới hạn nơi tìm so với `ContextSource.base`.
2. `SearchScope.SUBTREE`: xét mọi OU con của People.
3. `attributes("uid","cn","mail")`: mapper chỉ yêu cầu các trường cần để dựng `PersonRow`.
4. `countLimit(100)` và `timeLimit(3000)`: hạn chế số entry và thời gian tìm kiếm (tương ứng mili giây ở tầng JNDI).
5. Hai điều kiện filter chọn những entry có `objectClass=inetOrgPerson` và `departmentNumber` phù hợp.
6. `first(...)` xử lý attribute đơn trị mong đợi nhưng **có thể vắng mặt** do dữ liệu/ACL; `values(...)` duyệt tất cả giá trị của `mail`.
7. Khi có kết quả hợp lệ, `ldapTemplate.search(...)` trả một `List<PersonRow>`. Search không khớp entry nào thường trả danh sách rỗng; lỗi base, timeout hoặc limit có thể ném exception.

**Chú ý:** một số trường đáng lẽ bắt buộc theo schema vẫn có thể bị ACL che khi client đọc. Ở sản phẩm thực tế, hãy xác định chính sách với `uid` hoặc `cn` bị thiếu (ví dụ bỏ entry, báo lỗi dữ liệu, hoặc hiển thị trường thay thế). Đừng coi `null` tự động có nghĩa LDAP không có entry.

### 6.1. Vì sao mã dùng `AttributesMapper`?

`AttributesMapper<T>` chuyển các `javax.naming.directory.Attributes` được trả về thành đối tượng Java. Nó phù hợp khi dữ liệu đích gồm giá trị attribute và không cần toàn bộ context/DN của entry.

Nếu cần DN, kiểm soát mapping đặc biệt hoặc thao tác trên `DirContextAdapter`, dùng `ContextMapper` hoặc công cụ ODM phù hợp hơn. Dù dùng mapper nào, `base` và `scope` vẫn là tiêu chí **xác định nơi tìm kiếm**, còn `attributes` quyết định dữ liệu yêu cầu.

## 7. Ví dụ tương tự với `LdapClient`

`LdapClient` cũng nhận `LdapQuery` để thực hiện tìm kiếm. Với một `ldapClient` đã được cấu hình, có thể viết:

```java
import java.util.List;
import javax.naming.directory.Attributes;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.SearchScope;

import static org.springframework.ldap.query.LdapQueryBuilder.query;

// ldapClient được khởi tạo và tiêm qua cấu hình ứng dụng.
LdapQuery q = query()
    .base("ou=People")
    .searchScope(SearchScope.ONELEVEL)
    .attributes("uid", "cn")
    .where("objectClass").is("inetOrgPerson");

List<String> directNames = ldapClient.search()
    .query(q)
    .map((Attributes attributes) -> {
        var cn = attributes.get("cn");
        return cn == null ? null : String.valueOf(cn.get());
    })
    .list();
```

Ý tưởng vẫn là **cùng một `LdapQuery`**, nhưng API thực thi và mapper có thể khác theo phiên bản thư viện. Nếu đoạn mã có mapper nhận `Attributes` và có thể ném `NamingException`, hãy đảm bảo kiểu lambda phù hợp với overload `map(...)` đang dùng trong dự án. `LdapTemplate` ở mục 6 là ví dụ tự chứa đầy đủ để thực hành.

Không cần đổi cách dựng `base`/`scope`/`attributes` chỉ vì chuyển từ `LdapTemplate` sang `LdapClient`.

## 8. Giới hạn số kết quả và thời gian tìm kiếm

Mặc dù chủ đề chính là ba tham số, `LdapQueryBuilder` còn có:

```java
.countLimit(100)
.timeLimit(3000)
```

| Tham số | Đơn vị | Ý nghĩa |
| --- | --- | --- |
| `countLimit(100)` | Entry | Giới hạn số entry được yêu cầu trong một search |
| `timeLimit(3000)` | Mili giây qua JNDI | Giới hạn thời gian tìm kiếm được yêu cầu |
| `0` | Tùy tham số | Không áp giới hạn client cụ thể; server vẫn có quota của nó |

**Count limit không phải pagination.** Nếu filter khớp 10.000 entry nhưng limit là 100, không được tự coi 100 entry đã nhận là toàn bộ dữ liệu. Khi LDAP server trả `sizeLimitExceeded` hoặc `timeLimitExceeded`, Spring LDAP có thể phát sinh exception; một phần entry đã được gửi trước lỗi không làm cho search trở thành thành công toàn phần.

Muốn duyệt tập lớn qua nhiều trang, cần cơ chế như **Simple Paged Results Control** (RFC 2696) nếu server hỗ trợ, và phải quản lý cookie/trạng thái phân trang phù hợp. Không tăng `SUBTREE`, `countLimit` và `timeLimit` không kiểm soát để thay cho tối ưu filter hoặc index.

## 9. Ba lỗi thường gặp khi dùng `base`, `scope` và `attributes`

### 9.1. Đã cấu hình `ContextSource.base` nhưng vẫn truyền suffix

```java
// Sai trong bối cảnh ContextSource.base = dc=example,dc=org.
query().base("ou=People,dc=example,dc=org")
       .where("objectClass").is("inetOrgPerson");

// Đúng theo thiết kế base tương đối:
query().base("ou=People")
       .where("objectClass").is("inetOrgPerson");
```

Đối chiếu DN mà `ContextSource` đã định nghĩa trước khi sửa filter. Một filter hợp lệ không sửa được search base sai.

### 9.2. Chọn `ONELEVEL` rồi mong thấy user nằm dưới OU lồng nhau

```java
query().base("ou=People")
       .searchScope(SearchScope.ONELEVEL)
       .where("objectClass").is("inetOrgPerson");
```

Truy vấn trên không xét `uid=chi,ou=Engineering,ou=People,...` vì Chi ở **cấp cháu** của People. Đổi thành `SearchScope.SUBTREE` nếu nghiệp vụ cần toàn bộ user dưới các OU con, hoặc dùng base `ou=Engineering,ou=People` để tìm hẹp hơn.

### 9.3. Chỉ yêu cầu `cn` nhưng mapper lại đọc `mail`

```java
LdapQuery q = query()
    .base("ou=People")
    .attributes("cn")
    .where("objectClass").is("inetOrgPerson");
```

Nếu mapper gọi `attrs.get("mail").get()`, `attrs.get("mail")` có thể trả `null` vì `mail` **không được yêu cầu**. Điều này thường gây `NullPointerException` trong code, khác với lỗi server không tìm thấy entry.

Hãy đảm bảo **các trường mapper cần đọc nằm trong `attributes(...)`**, hoặc điều chỉnh mapper xử lý thiếu trường theo chính sách thiết kế. Nếu entry không có attribute đó hoặc ACL không cho đọc, bổ sung vào projection vẫn có thể không mang lại giá trị.

## 10. Filter và khả năng chống LDAP injection

Một filter được xây từ input cần dùng API hỗ trợ escape assertion value, thay vì nối chuỗi:

```java
// Không an toàn khi uid đến từ request bên ngoài:
String unsafe = "(uid=" + uid + ")";

// An toàn hơn: builder escape giá trị cho LDAP filter.
LdapQuery safe = query()
    .base("ou=People")
    .searchScope(SearchScope.SUBTREE)
    .attributes("uid", "cn")
    .where("uid").is(uid);
```

Theo RFC 4515, các ký tự như `*`, `(`, `)`, dấu gạch chéo ngược và NUL mang ý nghĩa đặc biệt trong filter. `.where("uid").is(uid)` biểu diễn equality với **giá trị dữ liệu** và escape theo ngữ cảnh filter. Nếu muốn **substring** có wildcard, đó là một ý đồ truy vấn khác (ví dụ `.where("cn").like("An*")` khi sử dụng mẫu có chủ đích).

**DN escaping (RFC 4514) và filter escaping (RFC 4515) là hai thao tác khác nhau.** Dùng `LdapNameBuilder` để dựng base từ các giá trị RDN; dùng query builder để đưa dữ liệu vào filter.

Không nhận tên attribute tùy ý từ người dùng rồi chuyển trực tiếp vào `where(attribute)` hoặc `attributes(attribute)` nếu nghiệp vụ chỉ cho phép một số trường. Hãy dùng danh sách tên thuộc tính được schema/ứng dụng chấp nhận để tránh truy vấn ngoài mục đích.

## 11. Quyền truy cập, TLS và hiệu năng

Khi tìm LDAP thật, cần xét cả phạm vi truy vấn và chính sách vận hành:

- **TLS:** dùng LDAPS hoặc StartTLS có xác minh chứng chỉ cho bind và dữ liệu nhạy cảm.
- **Least privilege:** tài khoản bind chỉ cần quyền đọc các nhánh/thuộc tính liên quan.
- **Base hẹp:** ưu tiên `ou=Engineering,ou=People` nếu chỉ cần Engineering, thay vì tìm toàn bộ suffix.
- **Scope vừa đủ:** `OBJECT` cho một entry, `ONELEVEL` cho con trực tiếp, `SUBTREE` cho cả cây con.
- **Projection hẹp:** chỉ lấy `uid`, `cn` cho danh sách; tải `mail`/`member` khi use case cần.
- **Filter chọn lọc:** cân nhắc index của server và matching rule của schema.
- **Limit có kiểm soát:** đặt count/time phù hợp; phân trang nếu thực sự cần duyệt nhiều entry.
- **Xử lý thiếu attribute:** không giả định có quyền đọc tất cả trường đã yêu cầu.

Đặc biệt, một nhóm LDAP có thể chứa hàng nghìn DN trong `member`. Yêu cầu toàn bộ attribute của nhóm có thể trả về payload lớn dù scope là `OBJECT` và chỉ có một entry. Vì vậy giới hạn số entry **không thay thế** việc chọn đúng projection.

## 12. Kiểm thử query builder đúng ý nghĩa

Bạn có thể kiểm tra **cấu hình query** mà không cần LDAP server, sau đó dùng integration test để xác minh kết quả với DIT thực.

### 12.1. Kiểm tra cấu hình `LdapQuery`

Ví dụ Java (đặt trong test có JUnit hoặc một công cụ assertion tương ứng):

```java
LdapQuery q = query()
    .base("ou=People")
    .searchScope(SearchScope.ONELEVEL)
    .attributes("uid", "cn")
    .where("objectClass").is("inetOrgPerson");

assertEquals("ou=People", q.base().toString());
assertEquals(SearchScope.ONELEVEL, q.searchScope());
assertArrayEquals(new String[] {"uid", "cn"}, q.attributes());
```

Các assertion này cho thấy builder đã giữ **base, scope và projection** như mong muốn. Chúng không kiểm tra dữ liệu LDAP thực tế hoặc quyền truy cập.

### 12.2. Kiểm thử integration theo cây ví dụ

Giả sử fixture chứa An, Bình dưới People và Chi, Dũng dưới Engineering.

| Kịch bản | Query | Kỳ vọng |
| --- | --- | --- |
| Đọc OU People | `base("ou=People")`, `OBJECT`, filter OU | Chỉ entry OU People nếu match |
| Liệt kê user trực tiếp | `base("ou=People")`, `ONELEVEL`, filter person | An và Bình |
| Liệt kê user toàn nhánh | `base("ou=People")`, `SUBTREE`, filter person | An, Bình, Chi và Dũng |
| Chỉ đọc tên | `attributes("cn")` | Mapper nhận `cn` được phép đọc, không mặc nhiên có `mail` |
| Filter theo phòng ban | Filter `departmentNumber=ENG` nhưng projection chỉ `uid,cn` | Entry khớp mà không bắt buộc trả `departmentNumber` |
| Base không tồn tại | `base("ou=Unknown")` | Xử lý lỗi noSuchObject/`NameNotFoundException` theo server |
| Không có entry khớp | Base tồn tại, filter `(uid=not-exists)` | Search thành công và danh sách rỗng |
| Chỉ yêu cầu operational attribute | `attributes("modifyTimestamp")` | Trả về nếu server có và ACL cho phép |
| Limit bị vượt | `countLimit(1)` trên nhiều kết quả | Kiểm tra lỗi/đường xử lý kết quả không đầy đủ |

Khi dùng LDAP server nhúng cho test, chú ý nó có thể không tái hiện chính xác ACL, limit, schema hoặc operational attributes của production. Để xác nhận phân trang, performance, TLS và quyền, cần test trên môi trường giống triển khai thực tế.

### 12.3. Đối chiếu với `ldapsearch`

Với cùng cấu hình base và scope:

```bash
ldapsearch -LLL -x -H "ldaps://ldap.example.org:636" \
  -D "cn=app-reader,ou=ServiceAccounts,dc=example,dc=org" -W \
  -b "ou=People,dc=example,dc=org" \
  -s one "(objectClass=inetOrgPerson)" \
  uid cn
```

Trong lệnh này:

- `-b` là **base DN đầy đủ** ở công cụ CLI.
- `-s one` tương ứng `SearchScope.ONELEVEL`.
- `uid cn` ở cuối là danh sách thuộc tính trả về tương ứng `.attributes("uid", "cn")`.
- `(objectClass=inetOrgPerson)` là filter.
- `-W` nhập mật khẩu qua prompt, tránh đặt mật khẩu trên command line.

Khi so sánh CLI với Spring LDAP, nhớ rằng CLI không tự áp `ContextSource.base` của ứng dụng; vì vậy base của CLI trong ví dụ cần **DN đầy đủ**.

## 13. Bài tập thực hành

Giả sử `ContextSource.base = dc=example,dc=org` và cây dữ liệu:

```text
dc=example,dc=org
├── ou=People
│   ├── uid=an
│   ├── uid=binh
│   └── ou=Engineering
│       └── uid=chi
└── ou=Groups
    └── cn=Engineering
```

Các entry user có `objectClass=inetOrgPerson`; OU có `objectClass=organizationalUnit`. Giả sử bind account có quyền đọc các thuộc tính được hỏi.

**Bài 1.** Muốn tìm toàn bộ user trong People, kể cả Chi dưới Engineering, `base` và `scope` nào phù hợp?

**Bài 2.** Muốn liệt kê **chỉ những user được đặt trực tiếp** dưới People, nên dùng scope nào? Entry Chi có xuất hiện không?

**Bài 3.** Muốn đọc đúng attribute `ou` của entry `ou=People` bằng search, nên dùng `OBJECT`, `ONELEVEL` hay `SUBTREE`?

**Bài 4.** Trong query có filter `(departmentNumber=ENG)` và `.attributes("uid","cn")`, server có thể dùng `departmentNumber` để lọc không? Mapper có chắc nhận được giá trị `departmentNumber` không?

**Bài 5.** `ContextSource.base` đã là `dc=example,dc=org`. Vì sao `.base("ou=People,dc=example,dc=org")` có thể sai?

**Bài 6.** `.attributes("mail")` có nghĩa là chỉ trả user có email không? Làm sao yêu cầu server **lọc những entry có mail**?

**Bài 7.** Với đầu vào `uid = "a*(b)"`, tại sao cần `.where("uid").is(uid)` thay vì nối chuỗi filter?

**Bài 8.** `SearchScope.BASE` có phải hằng enum Spring LDAP không? Nếu cần tìm chính base entry, tên đúng là gì?

**Bài 9.** Đoạn code sau có gì cần sửa?

```java
LdapQuery q = query()
    .base("ou=People")
    .searchScope(SearchScope.SUBTREE)
    .attributes("uid")
    .where("objectClass").is("inetOrgPerson");

// Mapper:
String email = attrs.get("mail").get().toString();
```

**Bài 10.** Một query trả 100 entry và ném `SizeLimitExceededException`. Có nên coi 100 entry đã thấy là toàn bộ dữ liệu và kết thúc quy trình đồng bộ không?

### Đáp án gợi ý

1. `base("ou=People")` và `SearchScope.SUBTREE`.
2. `SearchScope.ONELEVEL`; Chi **không** xuất hiện vì thuộc cấp cháu.
3. `SearchScope.OBJECT`, kết hợp filter phù hợp như `(objectClass=organizationalUnit)` và `attributes("ou")`.
4. **Có**. Filter hoạt động độc lập với projection; mapper **không** được đảm bảo nhận `departmentNumber` vì chưa yêu cầu trường này.
5. Có thể bị nối lặp suffix `dc=example,dc=org` trong thao tác dùng ContextSource base. Hãy truyền DN tương đối `ou=People`.
6. **Không**. Nó chỉ chọn thuộc tính trả về; muốn lọc entry có `mail`, thêm `where("mail").isPresent()` hoặc điều kiện `and` tương đương.
7. `(`, `)`, `*` có ý nghĩa cú pháp filter. `where(...).is(...)` xử lý escaping cho giá trị dữ liệu, giúp tránh LDAP injection.
8. **Không**. Tên đúng trong enum Spring LDAP là `SearchScope.OBJECT`.
9. Mapper đang đọc `mail` dù query chỉ yêu cầu `uid`. Cần thêm `mail` vào `attributes` nếu nghiệp vụ cần và vẫn xử lý trường hợp attribute vắng mặt.
10. **Không**. Search đã không kết thúc đầy đủ; cần xử lý giới hạn hoặc dùng phân trang/chia nhỏ truy vấn và xác nhận trạng thái hoàn tất.

## 14. Ghi nhớ

- `LdapQueryBuilder.query()` tạo truy vấn LDAP theo phong cách fluent. **Cấu hình `base`, `searchScope` và `attributes` trước khi bắt đầu filter**.
- **`base`** là entry bắt đầu tìm; trong Spring LDAP thường dùng **DN tương đối với `ContextSource.base`**.
- **`SearchScope.OBJECT`** xét chính base, **`ONELEVEL`** xét con trực tiếp, **`SUBTREE`** xét base và mọi hậu duệ.
- **`attributes(...)`** chỉ xác định trường được yêu cầu trả về; nó **không phải filter**. Attribute dùng để lọc có thể không nằm trong projection.
- Khi cần tên/giá trị từ input, dùng `LdapNameBuilder` cho DN và builder criteria cho filter, tránh nối chuỗi.
- Chỉ yêu cầu attribute cần thiết, chọn base/scope đủ hẹp, kiểm soát count/time limit, phân trang phù hợp và xử lý ACL/thiếu trường rõ ràng.
- `LdapTemplate` và `LdapClient` có thể thực thi `LdapQuery`; cách chọn base, scope và projection vẫn giữ nguyên.

### Tài liệu tham khảo

- [Spring LDAP — Advanced LDAP Queries](https://docs.spring.io/spring-ldap/reference/query-builder-advanced.html): tham số, thứ tự builder, filter và ví dụ dùng API.
- [Spring LDAP — LdapQueryBuilder API](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/query/LdapQueryBuilder.html): `base`, `searchScope`, `attributes`, `countLimit` và `timeLimit`.
- [Spring LDAP — SearchScope API](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/query/SearchScope.html): ba giá trị `OBJECT`, `ONELEVEL`, `SUBTREE`.
- [Spring LDAP — LdapQuery API](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/query/LdapQuery.html): đặc tính mặc định và kiểu dữ liệu của query.
- [Spring LDAP — Configuration](https://docs.spring.io/spring-ldap/reference/configuration.html): `ContextSource`, base DN và cấu hình kết nối.
- [RFC 4511 — LDAP: The Protocol](https://www.rfc-editor.org/rfc/rfc4511.html): SearchRequest, phạm vi tìm kiếm và attribute selection.
- [RFC 3673 — LDAP: All Operational Attributes](https://www.rfc-editor.org/rfc/rfc3673.html): selector `+`.
- [RFC 4514 — String Representation of Distinguished Names](https://www.rfc-editor.org/rfc/rfc4514.html): cú pháp DN.
- [RFC 4515 — String Representation of Search Filters](https://www.rfc-editor.org/rfc/rfc4515.html): cú pháp filter và escaping.
