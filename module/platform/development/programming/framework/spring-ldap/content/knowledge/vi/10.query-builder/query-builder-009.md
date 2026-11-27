# Đọc query đã dựng để kiểm tra phạm vi và điều kiện

Một truy vấn LDAP có thể **biên dịch đúng, filter có cú pháp hợp lệ, nhưng vẫn tìm sai dữ liệu**. Lý do thường không nằm ở phép so sánh `uid` hay `mail` mà ở **search base quá rộng**, **scope không đúng**, **attribute projection thiếu trường**, hoặc một điều kiện bảo vệ đã bị thay thế trong quá trình dựng query. Trước khi gửi truy vấn đến server, chúng ta nên biết rõ **query cuối cùng sẽ tìm ở đâu, chọn những entry nào và yêu cầu trả về những gì**.

Bài thuộc chương **Query builder** của mô-đun **SPRING_LDAP**, sử dụng `LdapQueryBuilder`, `LdapQuery` và `LdapTemplate` để kiểm tra cấu trúc truy vấn. Kiến thức phù hợp cho cả ứng dụng dùng `LdapClient` hoặc ODM vì chúng vẫn phải làm việc với base DN, scope, filter, quyền truy cập LDAP và dữ liệu schema.

**Mục tiêu bài học:**

- Đọc sáu thành phần của một `LdapQuery` đã dựng: `base()`, `searchScope()`, `attributes()`, `countLimit()`, `timeLimit()` và `filter()`.
- Diễn giải đúng ý nghĩa của base DN tương đối với `ContextSource.base` và ba mức `SearchScope`.
- Phân tích filter đã mã hóa từ `filter().encode()`, đặc biệt các toán tử `&`, `|`, `!`, sự hiện diện và ký tự escape.
- Nhận biết các giá trị **mặc định/chưa khai báo**; không nhầm `null` với giới hạn `0` hoặc dữ liệu rỗng.
- Viết kiểm thử xác minh query cuối cùng trước khi thực thi, đồng thời không làm lộ dữ liệu nhạy cảm trong log.
- Phòng tránh lỗi do sao chép/sửa query, đặc biệt trường hợp mất filter hạn chế phạm vi khi sử dụng `LdapQueryBuilder.fromQuery(...)` ở những phiên bản Spring LDAP bị ảnh hưởng.

## 1. Vì sao cần đọc lại query đã dựng?

Giả sử LDAP có DIT:

```text
dc=example,dc=org
├── ou=People
│   ├── uid=an
│   ├── uid=binh
│   ├── ou=Engineering
│   │   ├── uid=chi
│   │   └── uid=dung
│   └── ou=Support
│       └── uid=lan
├── ou=Groups
│   └── cn=Engineering
└── ou=ServiceAccounts
    └── cn=ldap-reader
```

Ứng dụng muốn tìm **nhân viên phòng ENG nằm trực tiếp dưới People**, chỉ lấy mã và tên. Nhà phát triển viết:

```java
LdapQuery q = query()
    .base("ou=People")
    .searchScope(SearchScope.ONELEVEL)
    .attributes("uid", "cn")
    .where("departmentNumber").is("ENG");
```

Kết quả có thể **không bao gồm Chi hoặc Dũng**, dù hai người cũng thuộc phòng ENG, vì họ nằm trong `ou=Engineering` (cấp cháu của People). Đó là lỗi **scope**, không phải filter.

Ngược lại, nếu dùng `SUBTREE` trên cả `dc=example,dc=org` với filter thiếu điều kiện `objectClass`, ứng dụng có thể tìm rộng hơn mục tiêu, tùy schema và dữ liệu thực tế.

Đọc query sau khi xây dựng giúp phát hiện những sai lệch như sau:

| Kiểm tra | Nếu sai có thể dẫn đến |
| --- | --- |
| Base DN | Tìm sai OU, không thấy entry, hoặc tràn sang vùng khác |
| Scope | Bỏ sót con cháu hoặc tìm quá sâu |
| Filter cuối cùng | Kết quả sai, mất điều kiện phân vùng, nguy cơ lộ dữ liệu |
| Attributes | Mapper không nhận trường cần dùng hoặc lấy dư thông tin |
| Count limit | Dữ liệu bị cắt, hiểu nhầm kết quả đã đầy đủ |
| Time limit | Truy vấn hết thời gian hoặc quá lâu |
| Ngữ cảnh `ContextSource` | DN bị nối lặp suffix hoặc kết nối nhầm server |

**Đọc lại query chỉ xác minh cấu hình yêu cầu được dựng ở tầng ứng dụng.** Nó không chứng minh server sẽ trả kết quả nào: kết quả còn tùy DIT thực tế, schema, ACL, replication, index và giới hạn server.

## 2. Các getter của `LdapQuery`

`org.springframework.ldap.query.LdapQuery` là interface chứa các thông tin cốt lõi của LDAP search. Spring LDAP công bố các phương thức:

| Getter | Kiểu trả về | Ý nghĩa |
| --- | --- | --- |
| `base()` | `javax.naming.Name` | DN nền tương đối được khai báo |
| `searchScope()` | `SearchScope`, có thể `null` | Phạm vi tìm kiếm |
| `attributes()` | `String[]`, có thể `null` | Tên các thuộc tính được yêu cầu |
| `countLimit()` | `Integer`, có thể `null` | Giới hạn số entry nếu được khai báo |
| `timeLimit()` | `Integer`, có thể `null` | Giới hạn thời gian nếu được khai báo |
| `filter()` | `org.springframework.ldap.filter.Filter` | Cấu trúc filter |
| `filter().encode()` | `String` | Biểu diễn filter theo cú pháp chuỗi LDAP |

**Lưu ý:** `filter()` trả đối tượng `Filter` chứ không phải chuỗi filter. Khi cần xem nội dung điều kiện theo cú pháp LDAP, dùng `filter().encode()`.

### 2.1. Ví dụ đọc một query hoàn chỉnh

Giả sử `ContextSource.base = dc=example,dc=org`:

```java
import java.util.Arrays;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.SearchScope;

import static org.springframework.ldap.query.LdapQueryBuilder.query;

LdapQuery q = query()
    .base("ou=People")
    .searchScope(SearchScope.SUBTREE)
    .attributes("uid", "cn", "mail")
    .countLimit(50)
    .timeLimit(3000)
    .where("objectClass").is("inetOrgPerson")
    .and("departmentNumber").is("ENG");

System.out.println("base       = " + q.base());
System.out.println("scope      = " + q.searchScope());
System.out.println("attributes = " + Arrays.toString(q.attributes()));
System.out.println("countLimit = " + q.countLimit());
System.out.println("timeLimit  = " + q.timeLimit());
System.out.println("filter     = " + q.filter().encode());
```

Nội dung phản ánh từ query được dựng:

```text
base       = ou=People
scope      = SUBTREE
attributes = [uid, cn, mail]
countLimit = 50
timeLimit  = 3000
filter     = (&(objectClass=inetOrgPerson)(departmentNumber=ENG))
```

Ở đây `3000` là **mili giây** theo quy ước API Spring LDAP/JNDI. Phần tử `(&(...)(...))` biểu diễn phép **AND** hai điều kiện. Dòng `base` chỉ là phần **tương đối** do query khai báo; không bao gồm suffix đã cấu hình trong `ContextSource`.

**Chỉ dùng `System.out.println` như ví dụ trong môi trường học tập**, không mặc định in nguyên filter trong log production vì giá trị filter có thể chứa mã nhân viên, email, username hoặc dữ liệu nhạy cảm.

### 2.2. Phân biệt đọc query và thực thi query

```text
LdapQueryBuilder.query()
       |
       v
  Dựng LdapQuery
       |
       +--> base(), searchScope(), attributes(), filter().encode()
       |    (kiểm tra cấu hình, chưa gửi LDAP request)
       |
       v
ldapTemplate.search(q, mapper)
       |
       v
 ContextSource + JNDI + LDAP server
       |
       v
  Kết quả hoặc exception
```

Bạn có thể kiểm tra `LdapQuery` bằng unit test **không kết nối tới LDAP server**. Tuy nhiên, sau đó vẫn nên có integration test để xác minh server nhận được truy vấn đúng ý định và tài khoản bind có quyền thích hợp.

## 3. Đọc `base()` và nhận diện search base thực sự

Base DN quyết định **entry gốc của phạm vi tìm kiếm**. Khi `ContextSource` cấu hình:

```java
contextSource.setBase("dc=example,dc=org");
```

thì các base thường được truyền **tương đối** trong Spring LDAP.

| `q.base().toString()` | Search base đầy đủ theo cấu hình trên |
| --- | --- |
| `""` | `dc=example,dc=org` |
| `"ou=People"` | `ou=People,dc=example,dc=org` |
| `"ou=Engineering,ou=People"` | `ou=Engineering,ou=People,dc=example,dc=org` |
| `"ou=Groups"` | `ou=Groups,dc=example,dc=org` |

**`q.base()` không tự cho biết giá trị `ContextSource.base` đang dùng.** Muốn đánh giá **phạm vi thực sự**, bạn cần cả hai thông tin:

1. Base của query — `q.base()`.
2. Base được cấu hình trong `ContextSource` mà `LdapTemplate` đang sử dụng.

Nếu hệ thống dùng nhiều `LdapTemplate` hoặc nhiều `ContextSource`, cùng `q.base()` có thể dẫn tới các nhánh LDAP khác nhau.

### 3.1. Nguy cơ nối lặp suffix

Ví dụ sai trong bối cảnh đã đặt `ContextSource.base = dc=example,dc=org`:

```java
LdapQuery q = query()
    .base("ou=People,dc=example,dc=org")
    .where("objectClass").is("inetOrgPerson");
```

Đọc `q.base()` sẽ thấy **đã chứa toàn bộ suffix**. Một số thao tác dựa trên base cấu hình sẽ nối thêm suffix một lần nữa và truy vấn DN không tồn tại.

Sửa bằng cách truyền **DN tương đối**:

```java
LdapQuery q = query()
    .base("ou=People")
    .where("objectClass").is("inetOrgPerson");
```

Đừng suy đoán rằng mọi giá trị `base()` là DN đầy đủ hoặc DN của Root DSE. Mặc định `base()` trả về `LdapUtils.emptyLdapName()` — một **Name rỗng**, không phải cam kết tìm từ root của LDAP server.

### 3.2. Kiểm tra DN dựng từ dữ liệu đầu vào

Nếu OU do nghiệp vụ chọn, nên dựng `Name` bằng `LdapNameBuilder`:

```java
import javax.naming.Name;
import org.springframework.ldap.support.LdapNameBuilder;

Name peopleInRegion = LdapNameBuilder.newInstance()
    .add("ou", "People")
    .add("ou", regionOu)
    .build();

LdapQuery q = query()
    .base(peopleInRegion)
    .searchScope(SearchScope.SUBTREE)
    .attributes("uid", "cn")
    .where("objectClass").is("inetOrgPerson");
```

Với `regionOu = "North,West"`, `base()` biểu diễn dấu phẩy trong **giá trị RDN** bằng cú pháp escaping của DN. Nhưng ngay cả DN đã escape đúng vẫn có thể trỏ đến **vùng mà người dùng không được phép yêu cầu**.

**Chính sách phạm vi phải được xác thực ở tầng ứng dụng** (ví dụ whitelist OU/tenant được phép) và dựa vào ACL phía server. Không coi escaping là cơ chế phân quyền.

## 4. Đọc `searchScope()`: kiểm tra độ sâu tìm kiếm

Spring LDAP có ba enum `SearchScope`:

| Giá trị | LDAP tương ứng | Những entry được xét |
| --- | --- | --- |
| `SearchScope.OBJECT` | baseObject | **Chỉ entry base** |
| `SearchScope.ONELEVEL` | singleLevel | **Các con trực tiếp**, không gồm base |
| `SearchScope.SUBTREE` | wholeSubtree | **Base và toàn bộ hậu duệ** |

**Tên enum chính xác là `OBJECT`**, không phải `BASE` (dù công cụ `ldapsearch -s base` dùng thuật ngữ base).

### 4.1. Diễn giải cùng một base ở các scope khác nhau

Với `base("ou=People")`:

```text
ou=People                   <-- base
├── uid=an                  <-- cấp con trực tiếp
├── uid=binh                <-- cấp con trực tiếp
└── ou=Engineering          <-- cấp con trực tiếp
    ├── uid=chi             <-- cấp cháu
    └── uid=dung            <-- cấp cháu
```

- `OBJECT`: chỉ xét entry `ou=People`.
- `ONELEVEL`: xét `uid=an`, `uid=binh` và `ou=Engineering`, nhưng **không** xét Chi/Dũng.
- `SUBTREE`: xét base và mọi entry con/cháu.

Scope không tự trả tất cả những entry được xét. **Filter** vẫn quyết định entry nào khớp.

Ví dụ:

```java
LdapQuery q = query()
    .base("ou=People")
    .searchScope(SearchScope.ONELEVEL)
    .attributes("uid", "cn")
    .where("objectClass").is("inetOrgPerson");
```

Ngay cả khi `ou=Engineering` là entry con trực tiếp, filter `inetOrgPerson` thường loại nó vì đó là `organizationalUnit`, không phải người dùng.

### 4.2. `searchScope() == null` có nghĩa gì?

Nếu query không đặt scope tường minh:

```java
LdapQuery q = query()
    .where("objectClass").is("inetOrgPerson");

System.out.println(q.searchScope()); // null
```

Giá trị `null` có nghĩa **query để cho `LdapTemplate` áp dụng scope mặc định**, **không** có nghĩa không tìm gì và **không** đồng nghĩa `OBJECT`.

Khi phân tích vấn đề an toàn hoặc hiệu năng, nên đặt scope rõ ràng trong code thay vì phụ thuộc mặc định ẩn. Nếu cần biết phạm vi thực sự khi `null`, kiểm tra cấu hình của `LdapTemplate` và version đang sử dụng.

## 5. Đọc `filter().encode()` để hiểu điều kiện cuối cùng

`filter().encode()` là cách quan sát nội dung **filter đã được builder dựng** theo cú pháp LDAP. Ví dụ:

```java
LdapQuery q = query()
    .base("ou=People")
    .searchScope(SearchScope.SUBTREE)
    .where("objectClass").is("inetOrgPerson")
    .and("departmentNumber").is("ENG");

String encoded = q.filter().encode();
System.out.println(encoded);
```

Kết quả:

```text
(&(objectClass=inetOrgPerson)(departmentNumber=ENG))
```

Diễn giải:

- `&`: **tất cả** điều kiện con phải khớp trên cùng entry.
- `objectClass=inetOrgPerson`: entry có ít nhất một giá trị `objectClass` khớp.
- `departmentNumber=ENG`: entry có giá trị phòng ban phù hợp theo matching rule của schema.
- `base` và `scope` vẫn giới hạn **vị trí tìm**, dù không nằm trong chuỗi filter.

**Một filter khớp trên toàn directory nhưng search base hẹp vẫn chỉ xét vùng base/scope.** Ngược lại, filter quá rộng cùng base `dc=example,dc=org` có thể bao quát nhiều entry ngoài mục tiêu.

### 5.1. Bảng đọc nhanh LDAP filter

| Ký hiệu | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Equality | `(uid=an)` | Giá trị `uid` so khớp `an` theo schema |
| Presence | `(mail=*)` | Entry có attribute `mail` |
| Substring | `(cn=An*)` | `cn` có giá trị bắt đầu bằng An theo matching rule |
| AND | `(&(objectClass=person)(uid=an))` | Cả hai điều kiện cùng khớp |
| OR | `(\|(uid=an)(uid=binh))` | Ít nhất một điều kiện khớp |
| NOT | `(!(mail=*))` | Phủ định presence của `mail` |
| Greater/equal | `(employeeNumber>=1000)` | Dùng ordering matching rule nếu schema hỗ trợ |
| Less/equal | `(employeeNumber<=2000)` | Dùng ordering matching rule nếu schema hỗ trợ |
| Approximate | `(cn~=An Nguyen)` | So khớp gần đúng nếu server/schema hỗ trợ |

Trong bảng, ký tự `\|` được escape cho Markdown; filter thực tế dùng `|`.

### 5.2. AND và OR lồng nhau

Xét filter:

```text
(&
  (objectClass=inetOrgPerson)
  (departmentNumber=ENG)
  (|(uid=an)(uid=chi))
)
```

Bản mã hóa liên tục:

```text
(&(objectClass=inetOrgPerson)(departmentNumber=ENG)(|(uid=an)(uid=chi)))
```

Ý nghĩa: entry phải là `inetOrgPerson`, thuộc phòng `ENG` **và** có `uid` là An **hoặc** Chi. Không được hiểu phép OR bên trong là cho phép bỏ qua điều kiện phòng ban.

Khi có filter phức tạp, **kiểm tra dấu ngoặc và cây điều kiện** quan trọng hơn chỉ nhìn chuỗi dài. Có thể dùng công cụ formatter nội bộ khi bảo đảm nó không làm thay đổi cú pháp hoặc gửi dữ liệu nhạy cảm ra bên ngoài.

### 5.3. Dấu `*`: presence, substring hay dữ liệu thật?

Ba biểu thức khác nhau:

```text
(mail=*)          # Presence: có attribute mail
(cn=An*)          # Substring: bắt đầu bằng An
(cn=An\2a)        # Equality: chứa đúng dấu sao trong "An*"
```

Theo **RFC 4515**, dấu sao `*` trong một giá trị assertion phải được escape thành `\2a` nếu muốn tìm **ký tự sao thực** thay vì wildcard.

Những ký tự đặc biệt của filter:

| Dữ liệu thật | Cách escape trong filter |
| --- | --- |
| `*` | `\2a` |
| `(` | `\28` |
| `)` | `\29` |
| `\` | `\5c` |
| NUL | `\00` |

**Không nhầm với DN escaping (RFC 4514)**: dấu phẩy thuộc giá trị RDN cần escaping khi dựng DN nhưng không phải ký tự cần escape giống vậy trong một filter assertion.

### 5.4. Vì sao phải kiểm tra filter sau khi binding giá trị?

Một tên do người dùng nhập:

```text
an*)(uid=*)
```

Nếu ứng dụng nối chuỗi:

```java
// Nguy hiểm: có thể biến dữ liệu thành cú pháp filter.
String filter = "(uid=" + userInput + ")";
```

filter có thể mang ý nghĩa khác so với ý định tìm `uid` bằng đúng input.

Dùng builder:

```java
LdapQuery safe = query()
    .base("ou=People")
    .searchScope(SearchScope.SUBTREE)
    .attributes("uid", "cn")
    .where("uid").is(userInput);

String encoded = safe.filter().encode();
```

Builder sẽ mã hóa các ký tự đặc biệt trong **giá trị filter** theo API của Spring LDAP. Khi kiểm thử, có thể kiểm tra filter đã được escape đúng thay vì ghép chuỗi rồi hy vọng LDAP server tự hiểu.

**Lưu ý:** `filter(String hardcodedFilter)` của `LdapQueryBuilder` **không tự validate hay escape** chuỗi đầu vào. Nếu dùng filter dựng từ tham số, chọn `where(...).is(...)` hoặc overload `filter(String format, Object... params)` có cơ chế encoding của tham số. Không dùng `filter("(uid=" + userInput + ")")`.

## 6. Đọc `attributes()`: dữ liệu yêu cầu trả về

`attributes()` mô tả **projection** (các trường server được yêu cầu trả về) chứ không phải điều kiện lọc entry.

Ví dụ:

```java
LdapQuery q = query()
    .base("ou=People")
    .searchScope(SearchScope.SUBTREE)
    .attributes("uid", "cn", "mail")
    .where("departmentNumber").is("ENG");
```

`q.filter().encode()` có thể là:

```text
(departmentNumber=ENG)
```

Còn `Arrays.toString(q.attributes())`:

```text
[uid, cn, mail]
```

**Filter sử dụng `departmentNumber`, nhưng mapper không nhất thiết nhận `departmentNumber`** vì query không yêu cầu trả về trường đó. Và việc yêu cầu `mail` **không có nghĩa entry phải có mail**; nếu cần lọc entry có mail, dùng điều kiện presence.

### 6.1. `attributes() == null` khác `attributes().length == 0`

Khi chưa gọi `attributes(...)`, getter có thể trả **`null`** để báo “không chỉ định danh sách attribute; sử dụng mặc định của template/server”.

Vì vậy, đoạn code này có thể lỗi:

```java
// Không an toàn: attributes() có thể null.
int length = q.attributes().length;
```

Thay vào đó:

```java
String[] requested = q.attributes();
if (requested == null) {
    System.out.println("Attributes: dùng giá trị mặc định");
} else {
    System.out.println("Attributes: " + Arrays.toString(requested));
}
```

**Không suy ra `null` là yêu cầu không trả thuộc tính nào.** Trong LDAP, lựa chọn `1.1` dùng riêng mới biểu thị yêu cầu **không trả attribute**. Còn mặc định giao thức là yêu cầu user/application attributes có thể đọc.

### 6.2. Những selector đặc biệt

| Attribute selection | Ý nghĩa |
| --- | --- |
| Không chỉ định | Thường yêu cầu các user attributes mặc định |
| `*` | Yêu cầu tất cả user/application attributes |
| `+` | Yêu cầu các operational attributes, theo RFC 3673 nếu server hỗ trợ |
| `cn mail` | Chỉ yêu cầu `cn` và `mail` |
| `cn modifyTimestamp` | Yêu cầu cụ thể user attribute và operational attribute |
| `1.1` khi dùng riêng | Không yêu cầu trả attribute nào |

Các giá trị `*`/`+` hoặc attribute cụ thể đều phải chịu chính sách ACL của server. Yêu cầu một trường không chứng minh ứng dụng được phép đọc trường đó.

**DN của SearchResultEntry không phải một attribute thông thường `dn`** trong mảng `Attributes`. Nếu cần DN, dùng API ánh xạ context/result thích hợp; không mặc định `attrs.get("dn")` hoạt động.

### 6.3. Dùng projection để bảo vệ dữ liệu và hiệu năng

Với màn hình danh sách người dùng, có thể chỉ cần:

```java
.attributes("uid", "cn", "mail")
```

Không nên yêu cầu mọi thuộc tính, nhất là `userPassword`, metadata, thông tin cá nhân hoặc nhóm `member` chứa rất nhiều DN nếu nghiệp vụ không cần. **Đọc query để xác minh không yêu cầu thừa trường** là một phần quan trọng của code review.

Ngoài ra, nếu mapper thực tế gọi `attrs.get("employeeNumber")` mà query chỉ yêu cầu `uid`, `cn`, đó là lỗi hợp đồng giữa **projection và mapper**; ứng dụng có thể gặp `NullPointerException` nếu không xử lý.

## 7. Đọc `countLimit()` và `timeLimit()`

Hai getter này có thể trả `null` khi chưa khai báo tường minh.

| Giá trị trong `LdapQuery` | Cách đọc |
| --- | --- |
| `countLimit() == null` | Chưa cấu hình trên query; `LdapTemplate` quyết định mặc định |
| `countLimit() == 0` | Client không yêu cầu giới hạn count cụ thể theo semantics LDAP/JNDI |
| `countLimit() == 50` | Đặt giới hạn 50 entry |
| `timeLimit() == null` | Chưa cấu hình trên query; dùng mặc định tầng template |
| `timeLimit() == 0` | Không yêu cầu giới hạn thời gian search cụ thể |
| `timeLimit() == 3000` | Theo API JNDI, 3.000 ms (3 giây) |

**`null` và `0` không giống nhau trong cấu hình query.** `null` có nghĩa query giao việc chọn giá trị cho `LdapTemplate`; `0` được đặt tường minh và theo contract của SearchControls có nghĩa không yêu cầu limit client cụ thể. Cả hai **không** vượt qua quota của server.

### 7.1. Đừng đọc count limit như page size

`countLimit = 50` là **giới hạn số entry của một search**, không phải cơ chế “lấy trang đầu, trang sau”. Nếu kết quả thực sự có 500 entry, server có thể trả lỗi `sizeLimitExceeded` hoặc ngừng search theo chính sách. Không coi 50 entry là toàn bộ kết quả nếu search chưa kết thúc hoàn chỉnh.

Phân trang LDAP cần cơ chế riêng như Simple Paged Results Control (RFC 2696) và quản lý cookie, nếu server hỗ trợ.

### 7.2. Đừng nhầm time limit với network timeout

`timeLimit(3000)` của Spring LDAP/JNDI tính bằng **mili giây**, còn LDAP SearchRequest `timeLimit` của giao thức tính theo **giây**. Timeout để tạo kết nối hoặc đọc socket (ví dụ các property của JNDI LDAP provider) là **cơ chế khác** với deadline tìm kiếm.

Đọc query giúp phát hiện giới hạn do ứng dụng yêu cầu, nhưng không cho biết toàn bộ timeout mạng/TLS/pooling hoặc deadline của HTTP request.

## 8. Tạo bảng tóm tắt query để debug an toàn

Nên có một **bản mô tả query có cấu trúc** để kiểm tra và viết test, thay vì chỉ gọi `query.toString()` rồi giả định chuỗi đó có tất cả thông tin.

### 8.1. DTO snapshot cho môi trường test

Ví dụ Java 17+:

```java
import java.util.Arrays;
import java.util.List;

import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.SearchScope;

public final class LdapQueryInspector {

    public record QuerySnapshot(
        String relativeBase,
        SearchScope scope,
        List<String> requestedAttributes,
        Integer countLimit,
        Integer timeLimitMillis,
        String encodedFilter
    ) {}

    public static QuerySnapshot inspectForTest(LdapQuery q) {
        String[] attributes = q.attributes();

        return new QuerySnapshot(
            q.base().toString(),
            q.searchScope(), // null nghĩa là dùng mặc định của template
            attributes == null ? null : List.copyOf(Arrays.asList(attributes)),
            q.countLimit(),
            q.timeLimit(),
            q.filter().encode()
        );
    }

    private LdapQueryInspector() {}
}
```

Cách dùng:

```java
LdapQuery q = query()
    .base("ou=People")
    .searchScope(SearchScope.ONELEVEL)
    .attributes("uid", "cn")
    .countLimit(30)
    .timeLimit(2000)
    .where("objectClass").is("inetOrgPerson");

LdapQueryInspector.QuerySnapshot snapshot =
    LdapQueryInspector.inspectForTest(q);

System.out.println(snapshot);
```

**Snapshot này phù hợp cho unit test hoặc debug có kiểm soát. Không dùng trực tiếp trong log production** nếu filter chứa email, tên tài khoản, DN người dùng hoặc thông tin bí mật. Snapshot lưu biểu diễn chuỗi đã encode, không phải một đối tượng “đã phân quyền”.

### 8.2. Nhật ký production nên ghi gì?

Trong production, ưu tiên log metadata đủ để chẩn đoán mà không lộ nội dung truy vấn:

| Dữ liệu | Khuyến nghị |
| --- | --- |
| Search base | Chỉ log khi không tiết lộ vùng nhạy cảm; hoặc dùng mã định danh vùng |
| Scope | Có thể log `OBJECT/ONELEVEL/SUBTREE` |
| Attribute selection | Chỉ log tên trường được phép; tránh các trường nhạy cảm |
| Count/time limit | Có thể log con số |
| Filter | Không log nguyên giá trị từ người dùng; ghi tên loại truy vấn hoặc dấu vết đã che |
| Bind DN/credentials | Không log credentials; principal cũng có thể cần che |
| LDAP result code, thời gian | Phù hợp để theo dõi truy vấn |
| Correlation ID | Hữu ích để liên kết log nhiều lớp |

Việc `filter().encode()` thực hiện escaping **không làm giá trị filter trở thành không nhạy cảm**. Escaping chỉ dành cho cú pháp, không phải anonymization.

## 9. Viết unit test kiểm tra ý đồ truy vấn

Một query được tạo từ filter động nên có test xác nhận **chính xác ba trục quan trọng**:

1. Base/scope có giới hạn đúng vùng được phép không?
2. Filter cuối cùng có giữ đủ điều kiện không?
3. Projection/limit có đúng yêu cầu không?

### 9.1. Test một query cố định

Ví dụ JUnit 5:

```java
import static org.junit.jupiter.api.Assertions.*;

import java.util.Arrays;
import org.junit.jupiter.api.Test;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.SearchScope;

import static org.springframework.ldap.query.LdapQueryBuilder.query;

class PeopleQueryTest {

    private static LdapQuery buildQuery() {
        return query()
            .base("ou=People")
            .searchScope(SearchScope.SUBTREE)
            .attributes("uid", "cn")
            .countLimit(50)
            .timeLimit(3000)
            .where("objectClass").is("inetOrgPerson")
            .and("departmentNumber").is("ENG");
    }

    @Test
    void checksQueryShape() {
        LdapQuery q = buildQuery();

        assertEquals("ou=People", q.base().toString());
        assertEquals(SearchScope.SUBTREE, q.searchScope());
        assertArrayEquals(new String[] {"uid", "cn"}, q.attributes());
        assertEquals(50, q.countLimit());
        assertEquals(3000, q.timeLimit());
        assertEquals(
            "(&(objectClass=inetOrgPerson)(departmentNumber=ENG))",
            q.filter().encode()
        );
    }
}
```

Ví dụ này xác minh **cấu hình query trước khi gọi server**. Nó không chứng minh LDAP server có entry, có quyền đọc hay sử dụng matching rule như mong đợi.

### 9.2. Test các giá trị mặc định

```java
LdapQuery q = query().where("objectClass").is("inetOrgPerson");

assertTrue(q.base().isEmpty());
assertNull(q.searchScope());
assertNull(q.attributes());
assertNull(q.countLimit());
assertNull(q.timeLimit());
assertEquals("(objectClass=inetOrgPerson)", q.filter().encode());
```

Bài kiểm tra này đặc biệt hữu ích nếu code review phát hiện một query không đặt base/scope: **mặc định đến từ ContextSource và LdapTemplate, không tự xác định tất cả trong query**.

### 9.3. Test input chứa ký tự đặc biệt

```java
String suspiciousUid = "a*b";

LdapQuery q = query()
    .base("ou=People")
    .searchScope(SearchScope.SUBTREE)
    .where("uid").is(suspiciousUid);

assertEquals("(uid=a\\2ab)", q.filter().encode());
```

Trong Java string literal, `"\\2a"` thể hiện chuỗi filter chứa một dấu gạch chéo ngược trước `2a`. Test này giúp xác định ký tự `*` được xem là **dữ liệu trong equality filter** thay vì wildcard.

Tương tự có thể kiểm tra dấu ngoặc và dấu gạch chéo ngược trong input. Nên test cả trường hợp thiếu attribute, không có entry khớp và lỗi LDAP server tại integration test.

## 10. Lỗi bảo mật đáng chú ý: mất filter khi sao chép query

Khi code dùng nhiều lớp service/repository, một pattern thường gặp là **dựng query gốc rồi bổ sung điều kiện**. Nhưng đây là chỗ dễ vô tình làm mất điều kiện giới hạn dữ liệu.

**Spring đã công bố CVE-2026-59368 ngày 19/11/2026** về `LdapQueryBuilder.fromQuery(LdapQuery)`. Ở các phiên bản bị ảnh hưởng, builder được tạo từ query đã có filter rồi được thêm một filter mới có thể **âm thầm thay thế filter cũ** thay vì giữ hoặc từ chối. Nếu filter cũ giới hạn tenant hoặc OU, truy vấn cuối cùng có thể rộng hơn nhiều so với dự kiến.

### 10.1. Vì sao đây là vấn đề?

Giả sử một query gốc chứa điều kiện:

```text
(&(objectClass=inetOrgPerson)(departmentNumber=ENG))
```

Lớp gọi muốn bổ sung `uid=an`, nhưng vô tình thay bằng:

```text
(uid=an)
```

Nếu entry `uid=an` tồn tại ở vùng ngoài ENG trong cùng search base, query cuối cùng đã **mất ràng buộc phòng ban**. Với hệ đa tenant, đây có thể là vi phạm ranh giới truy cập.

**Không suy luận rằng gọi `fromQuery(...)` tự động thực hiện phép AND giữa filter cũ và filter mới.** Phải đọc lại `query.filter().encode()` và test các điều kiện bắt buộc.

### 10.2. Phiên bản và hướng khắc phục theo Spring

Theo thông báo của Spring, các dải bị ảnh hưởng gồm:

| Nhánh Spring LDAP | Phiên bản bị ảnh hưởng | Phiên bản khắc phục |
| --- | --- | --- |
| 4.1.x | 4.1.0–4.1.2 | **4.1.3** (OSS) |
| 4.0.x | 4.0.0–4.0.6 | **4.0.7** (OSS) |
| 3.3.x | 3.3.0–3.3.9 | **3.3.10** (Enterprise) |
| 3.1.x–3.2.x | Từ 3.1.0 đến 3.2.19 | **3.2.20** (Enterprise) |

Thông báo cũng liệt kê bản sửa thuộc Enterprise cho một số nhánh khác. Ở phiên bản đã sửa, việc cố thêm filter lên builder tạo từ `fromQuery(existingQuery)` bị từ chối bằng `IllegalStateException` thay vì âm thầm bỏ filter cũ.

`fromQuery(...)` được đánh dấu deprecated trong các bản sửa, thay bằng **`LdapQueryBuilder.withQuery(...)`**, phương thức cố ý sao chép các tham số query **ngoại trừ filter**. Khi muốn giữ filter gốc, lập trình viên phải **gắn nó lại một cách tường minh**.

Tham khảo: [Spring Security Advisory — CVE-2026-59368](https://spring.io/security/cve-2026-59368/).

### 10.3. Mẫu kết hợp filter tường minh

Trên các phiên bản có `withQuery(...)`, có thể giữ filter gốc bằng `AndFilter`:

```java
import org.springframework.ldap.filter.AndFilter;
import org.springframework.ldap.filter.EqualsFilter;
import org.springframework.ldap.filter.Filter;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;

// sourceQuery đã chứa base, scope, attributes và điều kiện hạn chế.
Filter combined = new AndFilter()
    .and(sourceQuery.filter())
    .and(new EqualsFilter("uid", requestedUid));

// withQuery sao chép tham số không phải filter.
LdapQuery narrowed = LdapQueryBuilder.withQuery(sourceQuery)
    .filter(combined);

String resultFilter = narrowed.filter().encode();
```

Kỳ vọng dạng:

```text
(&(&(objectClass=inetOrgPerson)(departmentNumber=ENG))(uid=an))
```

Đây là filter lồng AND hợp lệ: điều kiện gốc **không bị loại bỏ**, chỉ thêm `uid=an`. `EqualsFilter` xử lý giá trị của thuộc tính theo API filter của Spring LDAP; giá trị `requestedUid` không được nối thẳng vào chuỗi filter.

**Lưu ý tương thích:** `withQuery(...)` là API của các phiên bản đã có bản sửa; nếu dự án dùng bản cũ, hãy **nâng cấp** hoặc xây query mới với đầy đủ điều kiện đã kiểm soát. Không mặc định mã này biên dịch trên mọi phiên bản Spring LDAP trước khi nâng cấp.

### 10.4. Những kiểm thử cần có sau thay đổi

- Kiểm tra `filter().encode()` chứa **toàn bộ điều kiện bắt buộc**, đặc biệt tenant, OU, group và permission predicates.
- Kiểm tra base/scope không rộng hơn phạm vi chính sách cho phép.
- Test user ở tenant A không thể tìm entry chỉ thuộc tenant B.
- Test khi thêm điều kiện mới, filter cũ vẫn tồn tại hoặc code bị từ chối rõ ràng.
- Kiểm tra chính xác phiên bản Spring LDAP trong dependency tree và lập kế hoạch nâng cấp theo advisory.
- **Không coi filter chỉ là lớp bảo mật duy nhất**: tài khoản bind và LDAP ACL phải thực thi giới hạn quyền thực sự.

## 11. Debug bằng `ldapsearch` để đối chiếu hành vi

Đọc query trong Java là bước đầu. Khi cần xác minh search thực tế, có thể chuyển các tham số sang một lệnh `ldapsearch` tương đương.

Giả sử:

```text
ContextSource.base = dc=example,dc=org
Query base         = ou=People
Scope              = ONELEVEL
Filter             = (&(objectClass=inetOrgPerson)(departmentNumber=ENG))
Attributes         = uid,cn
Count limit        = 30
Time limit         = 2000 ms
```

Ví dụ OpenLDAP command-line client:

```bash
ldapsearch -LLL -x -H "ldaps://ldap.example.org:636" \
  -D "cn=ldap-reader,ou=ServiceAccounts,dc=example,dc=org" -W \
  -b "ou=People,dc=example,dc=org" \
  -s one -z 30 -l 2 \
  "(&(objectClass=inetOrgPerson)(departmentNumber=ENG))" \
  uid cn
```

Giải thích phép đối chiếu:

| `LdapQuery` | `ldapsearch` |
| --- | --- |
| `base("ou=People")` + `ContextSource.base` | `-b "ou=People,dc=example,dc=org"` |
| `SearchScope.ONELEVEL` | `-s one` |
| `filter().encode()` | Chuỗi filter đặt trong dấu ngoặc kép |
| `attributes("uid","cn")` | `uid cn` cuối lệnh |
| `countLimit(30)` | `-z 30` |
| `timeLimit(2000)` | `-l 2` (giây ở CLI) |

**Không đưa credentials vào command line**; `-W` để nhập mật khẩu qua prompt. Luôn dùng TLS có xác minh chứng chỉ. Lệnh CLI cũng không tự biết base của Spring, nên phải truyền **DN đầy đủ**.

Nếu `ldapsearch` trả dữ liệu khác ứng dụng, kiểm tra server URL, principal, ACL, referrals, search scope, timeout, bộ lọc, đặc điểm pool và version provider. **Một query có chuỗi filter giống nhau trên hai server chưa chắc trả kết quả giống nhau** nếu replication hoặc quyền khác nhau.

## 12. Các tình huống dễ đọc sai

| Cách diễn giải sai | Cách đọc đúng |
| --- | --- |
| “`base()` rỗng nghĩa là tìm từ toàn bộ directory.” | Query dùng base tương đối rỗng; `ContextSource.base` còn quyết định gốc thực sự. |
| “`searchScope() == null` nghĩa là OBJECT.” | `null` là để template dùng mặc định; không tự suy ra một scope cụ thể. |
| “`ONELEVEL` bao gồm mọi hậu duệ.” | Chỉ con trực tiếp. |
| “`SUBTREE` chỉ tìm entry con, không xét base.” | Xét cả base lẫn hậu duệ. |
| “`attributes("mail")` yêu cầu entry phải có mail.” | Chỉ yêu cầu trường trả về; filter mới quyết định entry khớp. |
| “`filter().encode()` cho biết chắc chắn server sẽ trả entry nào.” | Nó chỉ mô tả điều kiện; kết quả phụ thuộc schema, dữ liệu, ACL và phạm vi. |
| “`countLimit(50)` bằng trang đầu của 50 entry.” | Size limit khác pagination. |
| “`timeLimit(3000)` nghĩa là 3.000 giây.” | API JNDI/Spring LDAP dùng mili giây. |
| “`filter(String)` tự escape dữ liệu bên ngoài.” | Hardcoded filter string không tự escape. |
| “`fromQuery` luôn giữ nguyên filter gốc khi thêm điều kiện.” | Có advisory và khác biệt theo phiên bản; phải kiểm tra/khắc phục. |
| “Chuỗi filter đã escape nên log công khai được.” | Escaping không che dữ liệu nhạy cảm. |
| “Unit test query pass thì ACL server đã an toàn.” | Phải kiểm tra quyền trên server trong integration test. |

## 13. Quy trình review query thực tế

Khi code review một repository, có thể dùng checklist theo thứ tự sau.

**Bước 1 — Xác nhận dữ liệu được phép tìm.** Xác định user/tenant/OU nào được truy cập. Kiểm tra ranh giới này được thực thi ở LDAP ACL, tầng ứng dụng và query đúng thiết kế.

**Bước 2 — Đọc base tương đối và `ContextSource.base`.** Đối chiếu DN đầy đủ. Kiểm tra có suffix lặp, nhầm OU hoặc dùng nhánh quá rộng không.

**Bước 3 — Đọc scope.** `OBJECT`, `ONELEVEL` hay `SUBTREE`? Nếu `null`, kiểm tra giá trị mặc định của `LdapTemplate`. Chọn scope tường minh cho các use case quan trọng.

**Bước 4 — Đọc filter cuối cùng.** Dùng `filter().encode()` trong test. Đánh giá AND/OR/NOT, giá trị được escape và các điều kiện hạn chế. Đặc biệt rà soát code sao chép/chỉnh filter.

**Bước 5 — Kiểm tra projection.** `attributes()` có gồm những trường mapper cần không? Có yêu cầu thừa trường nhạy cảm hoặc nhiều giá trị quá lớn không?

**Bước 6 — Kiểm tra count/time limit.** Phân biệt `null` với `0`; xác định server có quota khác không; cân nhắc pagination khi truy vấn phải trả toàn bộ dữ liệu.

**Bước 7 — Test với thư mục phù hợp.** Unit test xác minh hình dạng query; integration test xác minh ACL, schema, dữ liệu, lỗi server, timeout và kết quả sau replication.

## 14. Thực hành và câu hỏi tự kiểm tra

Giả sử:

```text
ContextSource.base = dc=example,dc=org
ou=People
├── uid=an
├── uid=binh
└── ou=Engineering
    └── uid=chi
```

An/Bình/Chi là `inetOrgPerson`. `departmentNumber` của An và Chi là `ENG`, của Bình là `SUP`.

**Bài 1.** Query:

```java
LdapQuery q = query()
    .base("ou=People")
    .searchScope(SearchScope.ONELEVEL)
    .attributes("uid", "cn")
    .where("departmentNumber").is("ENG");
```

Query xét những entry nào? Chi có được tìm thấy không? `attributes("uid", "cn")` có làm thay đổi filter không?

**Bài 2.** Với `ContextSource.base = dc=example,dc=org`, `q.base().toString()` bằng `ou=People` thì search base đầy đủ là gì?

**Bài 3.** Vì sao `q.searchScope() == null` không cho phép kết luận scope là `OBJECT`?

**Bài 4.** Hãy đọc filter:

```text
(&(objectClass=inetOrgPerson)(|(uid=an)(uid=chi)))
```

Entry nào trong dữ liệu mẫu có thể khớp khi scope là `SUBTREE` và base là People?

**Bài 5.** Query lọc theo `departmentNumber`, nhưng chỉ yêu cầu `attributes("uid", "cn")`. Mapper có chắc nhận được `departmentNumber` không?

**Bài 6.** Nếu `attributes() == null`, chương trình nên hiểu đó là “không trả attribute nào” hay “sử dụng lựa chọn mặc định”?

**Bài 7.** Với input `uid = "a*b"`, `where("uid").is(input)` nên sinh giá trị filter như thế nào để dấu `*` được hiểu là dữ liệu?

**Bài 8.** Query có `countLimit() == null` và `timeLimit() == null`. Có thể khẳng định server không áp limit nào không?

**Bài 9.** Một truy vấn sau khi ghép điều kiện từ nguồn khác bị mất `(departmentNumber=ENG)` nhưng còn `(uid=an)`. Vì sao điều này nguy hiểm? Cần kiểm thử điều gì?

**Bài 10.** Khi log production, tại sao không nên in `q.filter().encode()` không kiểm soát dù filter đã được escape đúng?

### Đáp án gợi ý

1. `ONELEVEL` xét con trực tiếp: An, Bình và các container con; filter `ENG` chọn **An** trong dữ liệu mẫu. Chi ở cấp cháu nên không được xét. `attributes` chỉ quyết định trường trả về.
2. `ou=People,dc=example,dc=org`.
3. `null` có nghĩa query giao việc chọn mặc định cho `LdapTemplate`. Muốn biết scope thực tế phải kiểm tra template và phiên bản.
4. **An và Chi**, vì cả hai có `objectClass=inetOrgPerson` và `uid` thuộc một trong hai giá trị.
5. **Không.** Filter và projection độc lập; phải yêu cầu attribute đó nếu mapper cần đọc.
6. **Lựa chọn mặc định**; không đồng nghĩa selector `1.1`.
7. `(uid=a\2ab)`, vì `\2a` biểu diễn ký tự sao thật trong filter value.
8. **Không.** Query không đặt limit, nhưng `LdapTemplate` và server vẫn có thể áp mặc định/quota.
9. Filter cuối có thể rộng hơn dự kiến và vượt ranh giới nghiệp vụ/tenant. Test **toàn bộ `filter().encode()`**, đặc biệt điều kiện bắt buộc; đồng thời xác nhận phiên bản Spring LDAP và bản vá CVE.
10. Escaping chỉ bảo vệ cú pháp filter, không che giá trị email/username/mã nhân viên; raw log có thể lộ dữ liệu nhạy cảm.

## 15. Ghi nhớ

- **Đọc `LdapQuery` bằng getter**, không suy từ code builder còn dang dở: `base()`, `searchScope()`, `attributes()`, `countLimit()`, `timeLimit()` và `filter().encode()`.
- **Base của query thường tương đối với `ContextSource.base`**; muốn biết vùng tìm thực sự phải xem cả hai.
- **Scope** quyết định độ sâu; **filter** quyết định điều kiện khớp; **attributes** quyết định trường trả về. Ba phần này độc lập nhưng kết hợp quyết định hành vi.
- `searchScope()`, `attributes()`, `countLimit()`, `timeLimit()` có thể là **`null`**, nghĩa là chưa chỉ định trong query. Không tự đánh đồng với `0`.
- **Kiểm tra filter cuối cùng** giúp phát hiện việc thiếu điều kiện, lỗi escaping hoặc thay thế điều kiện khi sao chép query. Đối với `fromQuery`, chú ý advisory **CVE-2026-59368** và dùng bản Spring LDAP đã khắc phục.
- Unit test kiểm tra hình dạng query; integration test kiểm tra LDAP server, schema, ACL, dữ liệu và limit. Không dùng query filter làm lớp phân quyền duy nhất.

### Tài liệu tham khảo

- [Spring LDAP — Interface LdapQuery](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/query/LdapQuery.html): getter cho base, scope, filter, attributes và các limit.
- [Spring LDAP — LdapQueryBuilder](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/query/LdapQueryBuilder.html): cách dựng query và các phương thức `fromQuery`, `filter`.
- [Spring LDAP — Filter interface](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/filter/Filter.html): phương thức `encode()`.
- [Spring LDAP — Advanced LDAP Queries](https://docs.spring.io/spring-ldap/reference/query-builder-advanced.html): các loại filter, tham số và thứ tự builder.
- [Spring LDAP — SearchScope](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/query/SearchScope.html): `OBJECT`, `ONELEVEL`, `SUBTREE`.
- [Spring — Security Advisory CVE-2026-59368](https://spring.io/security/cve-2026-59368/): rủi ro mất điều kiện khi dùng `fromQuery`, phiên bản ảnh hưởng và bản sửa.
- [RFC 4511 — LDAP: The Protocol](https://www.rfc-editor.org/rfc/rfc4511.html): SearchRequest, base/scope/filter/attribute selection và result code.
- [RFC 4515 — String Representation of Search Filters](https://www.rfc-editor.org/rfc/rfc4515.html): biểu diễn filter và escaping.
- [RFC 4514 — String Representation of Distinguished Names](https://www.rfc-editor.org/rfc/rfc4514.html): DN/RDN và escaping.
- [RFC 3673 — All Operational Attributes](https://www.rfc-editor.org/rfc/rfc3673.html): selector `+`.
- [RFC 2696 — Simple Paged Results](https://www.rfc-editor.org/rfc/rfc2696.html): phân trang LDAP theo cookie.
