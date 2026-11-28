# So sánh thứ tự và điều kiện phụ thuộc matching rule

Trong chương **Bộ lọc** của **SPRING_DATA_LDAP**, truy vấn LDAP không chỉ có phép so sánh bằng `(uid=lan)` hay kiểm tra hiện diện `(mail=*)`. LDAP còn có **bộ lọc so sánh thứ tự** như `(uidNumber>=10000)` và `(uidNumber<=19999)`, cùng **extensible match** để yêu cầu một *matching rule* cụ thể khi server/schema hỗ trợ. Những cú pháp này dễ làm người học liên tưởng đến SQL hoặc toán tử `>=` của Java, nhưng LDAP có một điểm khác biệt nền tảng:

> **Giá trị LDAP được so sánh theo matching rule của attribute type trong schema, không mặc nhiên theo thứ tự ký tự của chuỗi Java.**

Ví dụ `uidNumber` thường là thuộc tính cú pháp số nguyên của mô hình POSIX, có thể so sánh theo `integerOrderingMatch`. Trong khi đó, một thuộc tính văn bản như `cn` có thể chỉ được định nghĩa equality/substrings, **không có ordering matching rule** trên server. Khi ấy `(cn>=M)` không phải cách đáng tin để tìm mọi tên bắt đầu từ M trở đi, dù filter trông có vẻ hợp lệ.

Bài này giải thích ngữ nghĩa `>=`/`<=`, vai trò **EQUALITY**, **ORDERING**, **SUBSTR**, extensible matching, cách kiểm tra schema, giới hạn của biểu thức phủ định, cách sử dụng an toàn với `LdapTemplate`/Spring Data LDAP repository, và kiểm thử với directory thật.

## 1. LDAP Search filter không phải biểu thức SQL

Một phép tìm kiếm LDAP thông thường cần:

| Yếu tố | Ví dụ | Chức năng |
| --- | --- | --- |
| LDAP endpoint | `ldaps://directory.example.org:636` | Chọn directory server, kết nối và TLS |
| Base DN | `ou=people,dc=example,dc=org` | Điểm xuất phát trong cây entry |
| Search scope | `SUBTREE` | Giới hạn độ sâu dưới base |
| Filter | `(&(objectClass=posixAccount)(uidNumber>=10000))` | Quyết định entry nào thỏa điều kiện |
| Projection | `uid`, `uidNumber`, `cn` | Chọn thuộc tính được trả về |
| Bind/ACL | Account dịch vụ có quyền đọc | Quyết định entry và thuộc tính client thực sự được phép thấy |

Giả sử directory có:

```text
dc=example,dc=org
├── ou=people
│   ├── uid=an      (uidNumber=9999)
│   ├── uid=lan     (uidNumber=10000)
│   ├── uid=binh    (uidNumber=15000)
│   ├── uid=mai     (uidNumber=19999)
│   └── uid=nam     (uidNumber=20000)
└── ou=groups
    └── cn=engineering (gidNumber=21000)
```

Bộ lọc:

```text
(&(objectClass=posixAccount)(uidNumber>=10000)(uidNumber<=19999))
```

có thể chọn Lan, Bình và Mai **khi** thuộc tính `uidNumber` hỗ trợ ordering rule theo schema/server, tất cả entry phù hợp, và Bind account có quyền đọc. Nó **không sắp xếp** Lan, Bình và Mai theo UID; thứ tự trả về không được đảm bảo chỉ nhờ điều kiện filter.

## 2. Cú pháp những loại filter dễ nhầm

LDAP filter được biểu diễn bằng chuỗi cú pháp theo RFC 4515; server diễn giải các assertion theo ngữ nghĩa LDAP (RFC 4511) và schema/matching rules (ví dụ RFC 4517, RFC 4519).

| Filter | Tên phép kiểm tra | Ý nghĩa |
| --- | --- | --- |
| `(uid=lan)` | Equality | Giá trị thuộc tính `uid` khớp `lan` theo equality rule |
| `(mail=*)` | Presence | Thuộc tính `mail` có ít nhất một giá trị |
| `(cn=Lan*)` | Substring | Thuộc tính `cn` khớp mẫu con với ký tự đại diện |
| `(uidNumber>=10000)` | Greater-or-equal | Giá trị thuộc tính lớn hơn **hoặc bằng** assertion theo ordering rule |
| `(uidNumber<=19999)` | Less-or-equal | Giá trị thuộc tính nhỏ hơn **hoặc bằng** assertion theo ordering rule |
| `(cn~=Lan)` | Approximate | So khớp xấp xỉ; khả năng/ngữ nghĩa tùy server |
| `(cn:2.5.13.2:=LAN)` | Extensible match | Dùng matching rule được chỉ định, ví dụ `caseIgnoreMatch` |
| `(&(a=1)(b=2))` | AND | Hai điều kiện cùng thỏa |
| `(\|(a=1)(b=2))` | OR | Ít nhất một điều kiện thỏa |
| `(!(a=1))` | NOT | Phủ định kết quả đánh giá của điều kiện |

Trong tài liệu, dấu `\|` trong dòng OR chỉ nhằm hiển thị ký hiệu `|` của cú pháp filter; biểu thức thực tế là `(|(a=1)(b=2))`. LDAP **không** có các toán tử filter tổng quát `>` và `<` theo cú pháp trực tiếp như SQL; chuẩn có `>=` và `<=`. Muốn diễn đạt khoảng, cần kết hợp các assertion được schema hỗ trợ, rồi cân nhắc ranh giới bao gồm/không bao gồm.

### 2.1. So sánh thứ tự không đồng nghĩa sorting

`(uidNumber>=10000)` là câu hỏi **entry này có đáp ứng điều kiện hay không?**; nó không yêu cầu server trả kết quả theo `uidNumber` tăng dần. Nếu cần sắp xếp phía server, thường phải dùng LDAP Server Side Sorting control và kiểm tra server hỗ trợ, quyền, chỉ mục và lỗi; hoặc sort ở ứng dụng khi đã thu đủ tập kết quả phù hợp.

Đừng kết hợp `countLimit(100)` với giả định rằng 100 entry được trả là “100 người có `uidNumber` nhỏ nhất”. Không có sorting được bảo đảm, tập con đó có thể thay đổi khi dữ liệu hoặc kế hoạch thực thi query thay đổi.

## 3. Matching rule nằm trong schema, không nằm trong kiểu String của Java

Mỗi LDAP attribute type có thể khai báo:

| Thành phần schema | Mục đích | Tác động đến filter |
| --- | --- | --- |
| **SYNTAX** | Loại giá trị được chấp nhận: Directory String, Integer, Generalized Time, DN… | Xác định cách biểu diễn và xác minh giá trị |
| **EQUALITY** | Quy tắc so sánh bằng | Ảnh hưởng `(attr=value)` |
| **ORDERING** | Quy tắc so sánh thứ tự | Cần cho `(attr>=value)` và `(attr<=value)` |
| **SUBSTR** | Quy tắc so khớp chuỗi con | Ảnh hưởng `(attr=abc*)` |
| **SINGLE-VALUE** | Chỉ cho phép tối đa một giá trị | Ảnh hưởng dữ liệu/Modify, không biến attr thành sortable |
| **USAGE/operational** | Phân loại thuộc tính thông thường hay thuộc tính vận hành | Ảnh hưởng cách lấy/hiển thị thuộc tính |

Một attribute type cũng có thể **kế thừa** định nghĩa từ loại cha qua `SUP`. Vì vậy khi kiểm tra khả năng ordering, cần xem định nghĩa đã được kế thừa, không chỉ tìm từ `ORDERING` trong một dòng schema con.

Ví dụ minh họa cho một attribute type dạng số theo RFC 2307:

```text
NAME 'uidNumber'
EQUALITY integerMatch
ORDERING integerOrderingMatch
SYNTAX Integer
```

Đây là bản **rút gọn để học ý nghĩa**, không phải khai báo schema có thể nạp nguyên văn vào directory. Nếu directory đã khai báo `uidNumber` theo mô hình này, assertion `uidNumber>=10000` sử dụng ngữ nghĩa **số nguyên**, không phải so sánh chuỗi.

### 3.1. Cùng giá trị hiển thị, kết quả so sánh có thể khác

Xét hai chuỗi:

```text
"9" và "10"
```

Trong so sánh từ điển đơn giản theo ký tự, `"9"` có thể đứng sau `"10"`. Trong so sánh số nguyên, `9 < 10`. LDAP `integerOrderingMatch` phải so sánh **giá trị Integer** sau khi diễn giải theo cú pháp hợp lệ, không lấy kết quả từ `String.compareTo`.

Tương tự, so sánh tên không đơn giản là:

```java
"Lan".compareTo("lan")
```

Một equality/matching rule có thể bỏ qua chữ hoa/thường và xử lý chuẩn hóa ký tự; rule khác có thể phân biệt hoa/thường. **Dùng thứ tự collation hoặc chuẩn hóa của Java để dự đoán kết quả LDAP khi chưa kiểm tra matching rule là sai phương pháp.**

### 3.2. Các matching rule thường gặp

| Matching rule | Thường gắn với loại giá trị | Cần hiểu gì? |
| --- | --- | --- |
| `integerMatch` | Giá trị Integer | So sánh bằng theo số |
| `integerOrderingMatch` | Giá trị Integer | So sánh thứ tự theo số |
| `generalizedTimeMatch` | Thời gian dạng Generalized Time | So sánh bằng theo quy tắc thời gian |
| `generalizedTimeOrderingMatch` | Giá trị Generalized Time | So sánh trước/sau theo mốc thời gian được chuẩn hóa |
| `caseIgnoreMatch` | Một số thuộc tính Directory String | So sánh bằng với quy tắc không phân biệt hoa/thường |
| `caseExactMatch` | Một số thuộc tính Directory String | So sánh bằng theo quy tắc có phân biệt hoa/thường |
| `caseIgnoreOrderingMatch` | Một số thuộc tính Directory String **có khai báo ORDERING phù hợp** | So sánh thứ tự theo normalization/collation của rule, không phải ngẫu nhiên theo `String.compareTo` |
| `distinguishedNameMatch` | Thuộc tính chứa DN | So sánh DN theo ngữ nghĩa tên LDAP |

Sự tồn tại của một matching rule trong server **không chứng minh** mọi thuộc tính có cùng syntax đều dùng rule đó. Ví dụ, `cn` thường cho phép equality và substring nhưng không nhất thiết khai báo ORDERING. Muốn dùng `(cn>=M)`, phải xác minh **schema của `cn` trên directory thực tế**, hoặc một cơ chế so khớp mở rộng được server hỗ trợ.

## 4. Greater-or-equal và less-or-equal: điều kiện khoảng bao gồm hai đầu

LDAP dùng **`>=`** và **`<=`** cho so sánh thứ tự:

```text
(uidNumber>=10000)
(uidNumber<=19999)

(&(uidNumber>=10000)(uidNumber<=19999))
```

Giả sử thuộc tính `uidNumber` có `integerOrderingMatch`:

| Giá trị uidNumber | `>=10000` | `<=19999` | AND cả hai |
| ---: | :---: | :---: | :---: |
| 9999 | Sai | Đúng | Sai |
| 10000 | Đúng | Đúng | Đúng |
| 15000 | Đúng | Đúng | Đúng |
| 19999 | Đúng | Đúng | Đúng |
| 20000 | Đúng | Sai | Sai |

Hai đầu `10000` và `19999` đều **được bao gồm**. Nếu cần một cận mở (ví dụ lớn hơn 10000 nhưng không bao gồm 10000), không thể thay đơn giản bằng `>10000` vì đó không phải cú pháp filter LDAP chuẩn.

### 4.1. Cận mở: tại sao không áp dụng phủ định một cách mù quáng?

Với kiểu số nguyên rời rạc và dải giá trị rõ ràng, điều kiện “lớn hơn 10000” có thể viết `(uidNumber>=10001)` **nếu không có vấn đề về tràn số, biểu diễn, domain và dữ liệu**.

Với thời gian có độ phân giải khác nhau, tên dạng chuỗi, hoặc giá trị có tính liên tục, không có một “giá trị tiếp theo” hiển nhiên. Có thể nhìn thấy cách lập luận:

```text
X < 10000  ≈  X <= 10000 AND NOT(X >= 10000)
```

Tuy nhiên, ở LDAP cần nhớ **logic ba giá trị** (`TRUE`, `FALSE`, `Undefined`). Nếu thuộc tính thiếu hoặc phép matching không thể được đánh giá, phủ định một điều kiện `Undefined` vẫn không tạo ra `TRUE` như người viết SQL/Java có thể tưởng. Nếu cần mô phỏng cận mở, phải kiểm tra thuộc tính có mặt, ordering rule, kiểu giá trị và hệ quả của điều kiện phủ định; với tập dữ liệu quan trọng, hãy kiểm tra tại service và trên directory thật.

**Không dùng `(!(uidNumber>=10000))` như một phép `uidNumber<10000` tổng quát khi chưa xác minh sự tồn tại của thuộc tính và rule.**

### 4.2. Thuộc tính nhiều giá trị

LDAP attribute có thể có **nhiều giá trị**. Một assertion `(attr>=x)` có thể khớp nếu **ít nhất một giá trị phù hợp** với phép so sánh theo matching rule. Nếu đặt đồng thời:

```text
(&(attr>=10)(attr<=20))
```

với một thuộc tính **đa trị**, từng điều kiện có thể được thỏa bởi **hai giá trị khác nhau**; vì thế không được suy ra chắc chắn rằng có **một** giá trị nằm trong khoảng [10, 20].

Ví dụ `attr` có hai giá trị `5` và `30`: `>=10` có thể được thỏa bởi `30`, còn `<=20` có thể được thỏa bởi `5`. Điều kiện AND khi ấy vẫn có thể thành TRUE. Vì vậy, nếu use case cần **cùng một giá trị** ở trong dải, phải chọn thuộc tính `SINGLE-VALUE` phù hợp hoặc có một cách biểu diễn/kiểm tra khác. Đây là rủi ro logic đáng chú ý khi xây filter LDAP phức tạp.

## 5. Ba trạng thái đánh giá: TRUE, FALSE và Undefined

Theo ngữ nghĩa đánh giá LDAP filter, một assertion không chỉ có đúng/sai. Nó có thể nhận trạng thái **Undefined** khi không thể đánh giá, ví dụ do không có matching rule thích hợp hoặc giá trị assertion không phù hợp.

| Trường hợp | Điều cần hiểu |
| --- | --- |
| `(uidNumber>=10000)` với `uidNumber` hợp lệ, có ordering rule | Có thể đánh giá TRUE/FALSE theo số nguyên |
| Entry không có `uidNumber` | Assertion không khớp; không được tự coi entry thuộc dải |
| Attribute không hỗ trợ ORDERING theo schema đang dùng | So sánh có thể không đánh giá được, hoặc server có thể phản hồi lỗi tương ứng |
| Assertion chứa dữ liệu sai syntax Integer | Có thể bị từ chối hoặc không đánh giá được, tùy thao tác/server |
| `(!(filter))` khi `filter` là Undefined | Kết quả vẫn Undefined, **không** tự thành TRUE |

Trong xử lý Search, chỉ các entry mà filter được đánh giá **TRUE** mới thuộc tập kết quả (sau khi xét base/scope/ACL). Server có thể áp thêm chính sách, trả lỗi như **`inappropriateMatching (18)`** hoặc **`invalidAttributeSyntax (21)`**, hoặc không khớp; hành vi quan sát phụ thuộc server và trường hợp cụ thể.

**Không thấy kết quả chưa chứng minh filter đúng và không có entry phù hợp.** Khi dùng operator mới, hãy kiểm tra schema và chạy test đối chứng trên entry đã biết tồn tại.

### 5.1. AND/OR/NOT không ép dữ liệu thành đúng kiểu

`(&(objectClass=posixAccount)(uidNumber>=10000))` thêm `objectClass` giúp giới hạn tập entry, nhưng **không tự biến `uidNumber` thành Integer** nếu schema/server không khai báo đúng. Tương tự, `(|(uidNumber>=10000)(cn=Lan))` có thể trả Lan nhờ vế equality ngay cả khi so sánh thứ tự không có ý nghĩa ở một số entry.

Filter logic **không phải** ngôn ngữ cast dữ liệu hay ép kiểu như SQL. Phần lớn ngữ nghĩa được quy định bởi attribute type và matching rule.

## 6. So sánh thời gian: generalizedTimeOrderingMatch

Một số thuộc tính thời gian do LDAP server duy trì, ví dụ `createTimestamp` hoặc `modifyTimestamp`, sử dụng Generalized Time và có thể hỗ trợ `generalizedTimeOrderingMatch`. Dữ liệu ngày giờ cần được biểu diễn theo cú pháp LDAP hợp lệ và xử lý timezone đúng.

Ví dụ tìm entry được sửa **từ ngày 01/01/2026 theo UTC**:

```text
(&(objectClass=inetOrgPerson)(modifyTimestamp>=20260101000000Z))
```

Nếu cần trong khoảng cả năm 2026 (cận bao gồm):

```text
(&(objectClass=inetOrgPerson)
  (modifyTimestamp>=20260101000000Z)
  (modifyTimestamp<=20261231235959Z))
```

Đoạn trên xuống dòng để dễ đọc; khi gửi filter thành chuỗi ứng dụng hãy tuân thủ cú pháp RFC 4515 và không chèn khoảng trắng mới tùy tiện vào vị trí có ý nghĩa. Với API thời gian, nên thiết kế ranh giới theo **UTC, độ phân giải và khoảng nửa mở** ở tầng nghiệp vụ; nếu LDAP chỉ hỗ trợ `>=`/`<=`, phải xác định cách biểu diễn cận trên tương thích với độ phân giải của server, hoặc lọc chính xác sau khi truy vấn đủ rộng.

Điểm cần nhớ:

- `20260101000000Z` mang ý nghĩa thời gian UTC, không phải chuỗi số bất kỳ.
- Không dùng `String.compareTo` để suy ra thứ tự khi giá trị LDAP có offset, fractional seconds hoặc chuẩn hóa khác nhau.
- `modifyTimestamp` có thể là **operational attribute**, không được trả mặc định khi đọc entry; muốn lấy nó có thể phải yêu cầu rõ và có quyền.
- Directory có thể giới hạn/indexing riêng cho attribute thời gian. Lọc theo thời gian không tự bảo đảm hiệu năng cao.
- Nếu một server không hỗ trợ ORDERING trên thuộc tính thời gian bạn chọn, cú pháp `>=` trông đúng cũng không đảm bảo trả kết quả mong muốn.

### 6.1. Cẩn trọng với sự kiện đồng bộ tăng dần

Một job “lấy entry sửa sau lần đồng bộ trước” thường phải đối mặt với:

1. Độ phân giải timestamp: nhiều entry có thể cùng `modifyTimestamp`.
2. Sự thay đổi trong lúc paging: entry mới/sửa có thể xuất hiện giữa các trang.
3. Replication lag giữa LDAP server khác nhau.
4. Size/time limit và continuation reference/referral: kết quả một phần không đủ làm checkpoint.
5. Cursor/checkpoint: không chỉ dựa vào thời điểm cuối của trang đã đọc nếu còn entry cùng timestamp.

Vì vậy, dù filter thời gian sử dụng matching rule đúng, **tính đầy đủ của đồng bộ** vẫn đòi hỏi chiến lược checkpoint, paging và đối soát phù hợp.

## 7. Extensible matching: yêu cầu matching rule có chủ đích

LDAP có cú pháp **extensible match** để đưa matching rule (theo tên hoặc OID) vào filter khi server hỗ trợ:

```text
(attribute:matchingRule:=value)
(attribute:dn:matchingRule:=value)
(attribute:=value)
(:matchingRule:=value)
```

Cú pháp cụ thể có quy định về thứ tự thành phần, phần optional, yêu cầu tối thiểu phải có attribute hoặc matching rule và cách escape giá trị. Không được tự tạo một “operator LDAP” mới chỉ bằng cách đổi chuỗi trong filter.

Ví dụ sử dụng **OID của `caseIgnoreMatch`**:

```text
(cn:2.5.13.2:=Lan Nguyen)
```

Filter trên yêu cầu so khớp `cn` theo rule `caseIgnoreMatch` (OID `2.5.13.2`), nếu server hỗ trợ sử dụng rule đó cho loại thuộc tính và giá trị liên quan. Nó **không tự yêu cầu sắp xếp** kết quả theo `cn`.

### 7.1. Vai trò của :dn

Tùy chọn `:dn` trong extensible match cho phép xét cả các thành phần attribute-value của **DN** theo ngữ nghĩa LDAP, thay vì chỉ các giá trị attribute thông thường. Ví dụ minh họa:

```text
(ou:dn:=people)
```

Cách diễn giải/khả năng hỗ trợ còn phụ thuộc matching rule/server. Đặc biệt, **`:dn` không có nghĩa “tìm mọi hậu duệ của OU people”**. Muốn giới hạn nơi tìm, dùng **search base** và **search scope**:

```text
base = ou=people,dc=example,dc=org
scope = SUBTREE
```

Đây là cách rõ ràng hơn để chọn nhánh dữ liệu; sử dụng `:dn` chỉ khi nghiệp vụ thực sự cần kiểm tra thuộc tính nằm trong DN và directory đã được kiểm thử.

### 7.2. Extensible matching không tự tạo quy tắc mà server không biết

Giả sử `cn` không có ORDERING rule trong schema. Việc viết:

```text
(cn:caseIgnoreOrderingMatch:=M)
```

**không** biến nó thành điều kiện `cn>=M` chuẩn, cũng không đảm bảo server cho phép dùng rule ordering theo cách này. Extensible match yêu cầu áp dụng matching rule được server nhận diện và hỗ trợ; loại rule, attribute type, cú pháp assertion và tình huống sử dụng phải tương thích.

Nếu một thuộc tính thực sự cần điều kiện thứ tự theo nghiệp vụ, ưu tiên:

1. Sử dụng attribute type đã được schema khai báo ORDERING rule đúng.
2. Xác minh rule/index với quản trị directory.
3. Nếu không có hỗ trợ và tập dữ liệu nhỏ, lấy tập ứng viên đủ hẹp bằng equality/substring/filter được hỗ trợ, rồi **đối chiếu và so sánh ở application** theo ngữ nghĩa nghiệp vụ; không mặc định kết quả Search đã sắp xếp.
4. Nếu phải mở rộng schema, đánh giá tương thích với ứng dụng khác và quản trị dữ liệu; không tự thay schema production chỉ để sửa một filter.

## 8. Kiểm tra matching rule thực tế trên directory

Không nên kết luận toàn bộ dựa vào tên thuộc tính. Directory có thể hỗ trợ schema khác nhau, kế thừa attribute type hoặc từ chối công bố subschema cho Bind account hiện tại.

Một lộ trình kiểm tra:

1. **Xác định entry thật** với DN, `objectClass` và attribute muốn lọc.
2. **Đọc subschemaSubentry** (nếu server cho phép) để biết DN của subschema.
3. **Tra attributeTypes** trong subschema, tìm attribute type theo tên/OID và `SUP` liên quan.
4. **Kiểm tra SYNTAX, EQUALITY, ORDERING, SUBSTR** của attribute type (và thuộc tính cha nếu kế thừa).
5. **Đọc matchingRules/matchingRuleUse** nếu server cung cấp; kiểm tra server có hỗ trợ rule và attribute ứng dụng được rule đó không.
6. **Chạy Search đối chứng** ở cùng base/scope và Bind account với các giá trị ở biên.
7. **Kiểm tra result code và số entry**, không chỉ thấy “không báo lỗi” rồi kết luận filter đúng.

### 8.1. Ví dụ ldapsearch

Tìm subschema DN của một entry:

```bash
ldapsearch -x -H ldaps://directory.example.org:636 \
  -D "uid=app-reader,ou=services,dc=example,dc=org" -W \
  -b "dc=example,dc=org" -s base \
  "(objectClass=*)" subschemaSubentry
```

Nếu directory trả một DN subschema, có thể truy vấn entry đó bằng scope base. **DN dưới đây chỉ là ví dụ**, không được coi là đường dẫn subschema mặc định cho mọi server:

```bash
ldapsearch -x -H ldaps://directory.example.org:636 \
  -D "uid=app-reader,ou=services,dc=example,dc=org" -W \
  -b "cn=subschema" -s base \
  "(objectClass=*)" attributeTypes matchingRules matchingRuleUse
```

`attributeTypes` là thuộc tính đa trị chứa các chuỗi mô tả schema; cần phân tích đúng cú pháp để tìm định nghĩa `uidNumber` hay `cn`. Nếu `subschemaSubentry` không được trả hoặc server dùng subschema ở DN khác, hãy hỏi quản trị directory hoặc dùng tài liệu schema đã được triển khai.

### 8.2. Kiểm thử toán tử >= và <= trực tiếp

```bash
# Tìm tài khoản POSIX có uidNumber trong [10000, 19999].
ldapsearch -x -H ldaps://directory.example.org:636 \
  -D "uid=app-reader,ou=services,dc=example,dc=org" -W \
  -b "ou=people,dc=example,dc=org" -s sub \
  "(&(objectClass=posixAccount)(uidNumber>=10000)(uidNumber<=19999))" \
  dn uid uidNumber
```

So sánh với bộ dữ liệu thử nghiệm `9999`, `10000`, `15000`, `19999`, `20000`; nếu kết quả không như dự đoán, cần kiểm tra schema/matching rule, DN/scope, ACL và dữ liệu thực, thay vì tự tăng pool hay đổi server.

## 9. Spring LDAP: biểu diễn filter và truy vấn có kiểm soát

Spring LDAP cung cấp `LdapTemplate` và `LdapQueryBuilder` để xây Search trên một `ContextSource` được cấu hình trước. Vấn đề kỹ thuật ở đây là **tạo filter đúng mà không ghép raw input**, chứ không phải biến Java String thành một kiểu dữ liệu LDAP khác.

### 9.1. Cấu hình endpoint, Bind và base

```yaml
spring:
  ldap:
    urls: ldaps://directory.example.org:636
    base: dc=example,dc=org
    username: uid=app-reader,ou=services,dc=example,dc=org
    password: ${LDAP_BIND_PASSWORD}
```

`spring.ldap.urls` là endpoint; `spring.ldap.base` là DN gốc chung; `username` là DN dùng Bind. Với `ContextSource.base = dc=example,dc=org`, Search base tương đối `ou=people` tương ứng `ou=people,dc=example,dc=org`. Cần LDAPS hoặc StartTLS đã xác minh chứng chỉ và hostname; không tắt TLS validation để “làm filter hoạt động”.

### 9.2. Truy vấn khoảng cố định bằng LdapTemplate

Ví dụ filter được **định nghĩa hoàn toàn trong code**, không nối giá trị từ request:

```java
import java.util.List;
import javax.naming.directory.Attributes;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;

public class PosixUidNumberSearch {
    private static final String UID_RANGE_FILTER =
        "(&(objectClass=posixAccount)"
      + "(uidNumber>=10000)(uidNumber<=19999))";

    private final LdapTemplate ldapTemplate;

    public PosixUidNumberSearch(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public record UserNumber(String uid, String number) {}

    public List<UserNumber> searchFixedRange() {
        return ldapTemplate.search(
            "ou=people",
            UID_RANGE_FILTER,
            (AttributesMapper<UserNumber>) attrs ->
                new UserNumber(
                    first(attrs, "uid"),
                    first(attrs, "uidNumber"))
        );
    }

    private static String first(Attributes attrs, String name)
            throws javax.naming.NamingException {
        var attr = attrs.get(name);
        return attr == null || attr.size() == 0
            ? null : String.valueOf(attr.get());
    }
}
```

Code trên giả định `uidNumber` có ordering rule theo schema được triển khai, và có quyền đọc `uid`/`uidNumber`. `AttributesMapper` chỉ lấy một giá trị của mỗi thuộc tính; các entry thiếu thuộc tính sẽ được trả `null` trong DTO, cần có validation nếu nghiệp vụ yêu cầu. Với ứng dụng thực tế, nên đặt search scope và count/time limit rõ ràng qua `LdapQuery` hoặc `SearchControls`, tránh quét quá rộng.

### 9.3. Dynamic value: không tự ghép input vào filter

Ví dụ **không an toàn**:

```java
String filter = "(uidNumber>=" + rawMinFromRequest + ")";
```

Dữ liệu đầu vào được đưa trực tiếp vào chuỗi filter có thể thay đổi cú pháp logic hoặc gây LDAP injection. Có hai lớp bảo vệ:

1. **Validate theo domain**: `minUid` và `maxUid` phải là số nguyên trong dải cấp UID/GID được tổ chức cho phép, `minUid <= maxUid` và giới hạn kích thước kết quả. Không lấy tên attribute hoặc operator trực tiếp từ request.
2. **Dùng API filter/query hoặc placeholder** để escape assertion value theo RFC 4515, kể cả khi input “trông giống số”. Validation và escaping là hai yêu cầu **khác nhau**.

Một cách có thể thực hiện trực tiếp bằng JNDI là sử dụng overload `DirContext.search` hỗ trợ biến số filter:

```java
import javax.naming.NamingEnumeration;
import javax.naming.directory.DirContext;
import javax.naming.directory.SearchControls;
import javax.naming.directory.SearchResult;

public void findUsersInRange(DirContext ctx, long minUid, long maxUid)
        throws javax.naming.NamingException {
    if (minUid < 0 || maxUid < minUid) {
        throw new IllegalArgumentException("Invalid UID range");
    }

    SearchControls controls = new SearchControls();
    controls.setSearchScope(SearchControls.SUBTREE_SCOPE);
    controls.setCountLimit(100);
    controls.setTimeLimit(3_000);
    controls.setReturningAttributes(new String[]{"uid", "uidNumber"});

    String filter =
        "(&(objectClass=posixAccount)"
      + "(uidNumber>={0})(uidNumber<={1}))";

    NamingEnumeration<SearchResult> entries = ctx.search(
        "ou=people,dc=example,dc=org",
        filter,
        new Object[]{Long.toString(minUid), Long.toString(maxUid)},
        controls);

    try {
        while (entries.hasMore()) {
            SearchResult entry = entries.next();
            // Xử lý thuộc tính của entry theo hợp đồng nghiệp vụ.
        }
    } finally {
        entries.close();
    }
}
```

`DirContext` đã được Bind qua kết nối bảo mật do caller quản lý; khi không dùng pool, phải đóng context đúng vòng đời. JNDI provider thực hiện thay giá trị các placeholder trong filter theo cơ chế dành cho filter argument. Đây là ví dụ giúp hiểu **giao diện cấp thấp**; trong Spring thường ưu tiên filter/query builder và `LdapTemplate` để được hỗ trợ quản lý context.

### 9.4. LdapQueryBuilder cho equality và điều kiện khác

Khi một use case cần tìm user theo UID hoặc các thuộc tính có equality rule, `LdapQueryBuilder` giúp thể hiện logic rõ ràng:

```java
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;
import org.springframework.ldap.query.SearchScope;

LdapQuery query = LdapQueryBuilder.query()
    .base("ou=people")
    .searchScope(SearchScope.SUBTREE)
    .countLimit(50)
    .where("objectClass").is("posixAccount")
    .and("uid").is(inputUid);
```

`inputUid` là giá trị động được builder xử lý dưới dạng assertion value; **không** đưa `inputUid` vào một chuỗi filter đã ghép sẵn. Với điều kiện ordering phức tạp, kiểm tra API query/filter của **phiên bản Spring LDAP đang dùng** có hỗ trợ toán tử cần thiết trước khi viết code; có thể sử dụng filter hằng hoặc đoạn adapter thấp hơn được parameterize để kiểm soát ngữ nghĩa. Không giả định mọi derived method của `LdapRepository` hỗ trợ đầy đủ các operator so sánh như Spring Data JPA.

## 10. Repository và @Entry không thay thế schema matching rule

Spring Data LDAP giúp ánh xạ entry thành Java object:

```java
import javax.naming.Name;
import org.springframework.ldap.odm.annotations.Entry;
import org.springframework.ldap.odm.annotations.Id;
import org.springframework.ldap.odm.annotations.Attribute;
import org.springframework.data.ldap.repository.LdapRepository;
import java.util.List;

@Entry(base = "ou=people",
       objectClasses = {"inetOrgPerson", "posixAccount"})
public class PosixPersonEntry {
    @Id
    private Name dn;

    @Attribute(name = "uid")
    private String uid;

    @Attribute(name = "uidNumber")
    private String uidNumber;

    public PosixPersonEntry() {}
    public Name getDn() { return dn; }
    public String getUid() { return uid; }
    public String getUidNumber() { return uidNumber; }
}

interface PosixPersonRepository extends LdapRepository<PosixPersonEntry> {
    List<PosixPersonEntry> findByUid(String uid);
}
```

Mặc dù `uidNumber` được ánh xạ thành `String` ở Java, server vẫn diễn giải phép `uidNumber>=10000` theo **LDAP schema**, không theo so sánh từ điển Java. Ngược lại, ánh xạ `uidNumber` thành `long` ở entity cũng không tự thêm `integerOrderingMatch` vào schema directory.

`@Entry(base = "ou=people")` xác định nơi tìm entity tương đối với `ContextSource.base`; `@Id` chứa DN; `@Attribute` mô tả tên thuộc tính. Các annotation này **không phải** phần khai báo matching rule, chỉ mục, ORDER BY hay ACL. Nếu cần filter thứ tự và phân trang/giới hạn đặc thù, có thể tạo **custom repository fragment/adapter `LdapTemplate`** theo khả năng của phiên bản thư viện.

### 10.1. Vì sao filter rỗng chưa chắc là lỗi repository?

Giả sử `findByUid("lan")` trả entry nhưng `(uidNumber>=10000)` không trả dù `uidNumber=11001`. Các nguyên nhân có thể:

- Attribute type `uidNumber` trong directory không có ORDERING rule mong đợi, hoặc matching rule không được server hỗ trợ.
- Entry được tìm dưới base/scope khác, hoặc LDAP client dùng account có ACL khác.
- Giá trị lưu trong directory có vấn đề về syntax, mapping hoặc replication.
- Search có size/time limit, referral/partial result hoặc client nuốt exception.
- Code Java so sánh một thuộc tính khác với thuộc tính trong LDAP filter thực tế.

Đừng mặc định sửa kiểu Java của field là đủ. Phải chẩn đoán trên **schema và request LDAP thật**.

## 11. Filter an toàn, dữ liệu thiếu và hiệu năng

### 11.1. Escape filter khác escape DN

Các ký tự như `*`, `(`, `)`, dấu `\` và NUL có ý nghĩa đặc biệt trong LDAP filter. Khi chúng là **dữ liệu trong assertion value**, cần escape theo RFC 4515. Các biểu diễn thường gặp:

| Ký tự dữ liệu | Escape trong LDAP filter |
| --- | --- |
| `*` | `\2a` |
| `(` | `\28` |
| `)` | `\29` |
| `\` | `\5c` |
| NUL | `\00` |

Hãy để filter builder/parameterization xử lý thay vì tự thay ký tự bằng chuỗi, vì Unicode/UTF-8 và ranh giới cú pháp còn phải tuân thủ chuẩn. **DN** có quy tắc escape khác (RFC 4514); dùng `LdapNameBuilder` để tạo DN, không dùng cùng hàm escape filter cho DN. LDAP URL còn có percent-encoding riêng.

Nếu một API nhận cả tên thuộc tính và toán tử so sánh, **không** cho dùng bất kỳ chuỗi nào: định nghĩa allowlist như `uidNumber` hoặc `modifyTimestamp`, xác minh schema/ACL và chọn biểu thức tương ứng ở server-side code.

### 11.2. Không tạo ra quét toàn directory từ filter sai

Một filter được xây sai có thể trở thành `(objectClass=*)`, khiến server duyệt phần lớn naming context. Với điều kiện thứ tự, query trên thuộc tính thiếu index cũng có thể rất tốn kém.

Biện pháp:

1. Chọn base DN hẹp nhất đáp ứng use case.
2. Chọn `ONELEVEL` hay `SUBTREE` theo cấu trúc thực tế.
3. Kiểm tra thuộc tính có ORDERING và **index phù hợp** theo server; sự tồn tại matching rule không có nghĩa filter đã được index.
4. Dùng count/time limit nhưng không coi kết quả cắt là đầy đủ.
5. Khi cần tất cả dữ liệu, dùng paging/control được server hỗ trợ và đối soát completion; không nuốt `PartialResultException`.
6. Giới hạn số request đồng thời, đo p95/p99 và query latency trước khi tăng connection pool.

### 11.3. Presence và dữ liệu thiếu

Muốn tránh suy luận sai khi dùng NOT trên thuộc tính có thể vắng mặt, có thể kết hợp điều kiện hiện diện trong trường hợp thích hợp:

```text
(&(uidNumber=*)(!(uidNumber>=10000)))
```

Filter này **không nên được xem là “mọi UID nhỏ hơn 10000” trong mọi directory** nếu `ORDERING` không được hỗ trợ hoặc assertion bị Undefined. Nhưng presence giúp diễn đạt rõ rằng ứng dụng quan tâm đến những entry **thực sự có `uidNumber`**.

Với thuộc tính số nguyên bắt buộc trong `posixAccount`, việc lọc thêm `(objectClass=posixAccount)` có thể giúp giữ đúng mô hình schema; tuy nhiên thực tế vẫn cần kiểm tra entry lệch schema hoặc ACL.

## 12. Chẩn đoán lỗi theo mã kết quả và triệu chứng

| Hiện tượng | Hướng kiểm tra |
| --- | --- |
| `(uidNumber=10000)` có kết quả nhưng `(uidNumber>=10000)` không có | Kiểm tra **ORDERING** (khác EQUALITY) trong attribute type/schema và test trực tiếp |
| `(cn>=M)` rỗng hoặc khác server | `cn` có thể không có ordering rule; không dùng String lexical order làm căn cứ |
| Search theo ngày giờ sai khoảng | Generalized Time syntax, UTC/offset, độ phân giải, operational attribute |
| Server trả LDAP `18 inappropriateMatching` | Matching rule không phù hợp với attribute/loại assertion theo server |
| Server trả LDAP `17 undefinedAttributeType` | Tên thuộc tính không được directory nhận diện |
| Server trả LDAP `21 invalidAttributeSyntax` | Assertion hoặc giá trị có cú pháp không hợp lệ theo directory |
| Server trả LDAP `32 noSuchObject` | Search base hoặc DN mục tiêu không tồn tại/không thấy được; chưa phải lỗi ordering |
| Server trả LDAP `50 insufficientAccessRights` | Account Bind không đủ quyền xem/thực hiện thao tác |
| Search trả mã `0` với 0 entry | Filter không khớp trong phạm vi được tìm; còn cần kiểm chứng matching rule/schema |
| Search trả LDAP `3`/`4` | Time/size limit; không coi dữ liệu thu được là toàn bộ |
| Search gặp `PartialResultException` | Referral/continuation reference chưa xử lý; không biến phần dữ liệu có sẵn thành kết quả đầy đủ |
| Timeout mạng không có LDAP response | Connect/read timeout, TLS, pool hay server; đừng gán một mã LDAP tùy ý |
| Tăng filter phức tạp làm p99 tăng | Chỉ mục, base/scope, scan lớn, concurrency, cấu hình directory |

Các mã là **kết quả LDAP khi thực sự có response tương ứng**. Không parse `exception.getMessage()` một cách tùy tiện để tạo metric result code chính xác nếu Spring LDAP/JNDI không công bố thông tin đủ tin cậy. Hãy theo dõi `operation=search`, `outcome`, nhóm lỗi, độ trễ và tên loại filter hữu hạn; không ghi UID, DN, filter có dữ liệu cá nhân hoặc mật khẩu vào metric label.

## 13. Kiểm thử với directory để chứng minh matching rule

Nên tạo dữ liệu test có cả entry hợp lệ, entry thiếu thuộc tính tùy chọn và giá trị biên. Ví dụ:

```text
ou=people,dc=example,dc=org
  uid=an    posixAccount  uidNumber=9999
  uid=lan   posixAccount  uidNumber=10000
  uid=binh  posixAccount  uidNumber=15000
  uid=mai   posixAccount  uidNumber=19999
  uid=nam   posixAccount  uidNumber=20000
  uid=khach inetOrgPerson (không có uidNumber)
```

| Ca thử | Filter / thao tác | Kết quả cần xác minh |
| --- | --- | --- |
| Cận dưới | `(uidNumber>=10000)` | Có Lan/Bình/Mai/Nam, không có An |
| Cận trên | `(uidNumber<=19999)` | Có An/Lan/Bình/Mai, không có Nam |
| Khoảng hai cận | `(&(uidNumber>=10000)(uidNumber<=19999))` | Có Lan/Bình/Mai; hai đầu được bao gồm |
| Entry thiếu thuộc tính | Cùng filter, thêm `uid=khach` | Không tự coi Khách thuộc khoảng |
| So sánh số khác từ điển | Thêm UID `9` và `10` trong namespace thử | `integerOrderingMatch` xử lý theo giá trị số |
| Không có ORDERING | Chọn thuộc tính test chưa khai báo rule | Ghi lại hành vi server, không kỳ vọng lexical compare |
| Extensible equality | `(cn:2.5.13.2:=LAN NGUYEN)` | Kiểm tra `caseIgnoreMatch` được server cho phép với `cn` |
| Filter input đặc biệt | UID chứa ký tự `*`, `(` theo schema cho phép | Builder/placeholder không mở rộng điều kiện bất ngờ |
| Lỗi syntax | Assertion số nguyên sai định dạng | Không đánh dấu thành công giả; phân loại response đúng |
| Phủ định + thuộc tính thiếu | `(!(uidNumber>=10000))` | Kiểm tra ba-valued logic/không suy luận sai về entry thiếu |
| Search nhiều OU | Có người dùng trong OU con | Kiểm tra `SUBTREE` vs `ONELEVEL` và base chính xác |
| Chỉ đọc theo ACL | Bind account giới hạn | Không xem kết quả thiếu do ACL là thiếu dữ liệu thực |
| Server giới hạn kết quả | Size/time limit và paging | Không chấp nhận tập kết quả thiếu như đã hoàn tất |
| Thời gian sửa entry | Query theo `modifyTimestamp` | So timestamp UTC, độ phân giải, index và quyền xem |

**Unit test** kiểm tra validation của min/max, logic chọn filter và mapper DTO, nhưng không chứng minh server thực hiện `integerOrderingMatch`/`generalizedTimeOrderingMatch`. **Integration test** cần một LDAP directory có schema gần thực tế, chạy Search qua đúng `ContextSource`/Bind/ACL/TLS và đối chiếu dữ liệu biên.

### 13.1. Một trường hợp đặc biệt: multi-valued range

Nếu tổ chức tạo attribute tùy biến `score` cho phép nhiều giá trị số nguyên, seed thử một entry có `score: 5` và `score: 30`. Query:

```text
(&(score>=10)(score<=20))
```

có thể khớp do **hai giá trị khác nhau** thỏa từng assertion. Kiểm thử này giúp phân biệt “entry thỏa hai điều kiện” và “có một giá trị nằm trong khoảng”. Nếu nghiệp vụ cần vế sau, model/syntax/constraint phải phản ánh rõ yêu cầu thay vì dựa trên hai assertion độc lập.

## 14. Câu hỏi tự kiểm tra

1. **`(uidNumber>=10000)` so sánh theo Java String hay LDAP matching rule?** Theo **ORDERING matching rule** của attribute type được directory áp dụng.
2. **LDAP có phép lọc `>` và `<` trực tiếp như SQL không?** Không. Cú pháp filter chuẩn có `>=` và `<=`; phải thiết kế cận mở có xét kiểu dữ liệu và ba-valued logic.
3. **Tại sao `(cn>=M)` có thể không hoạt động như mong đợi?** `cn` có thể không khai báo ordering rule phù hợp; equality/substring không tự suy ra khả năng so sánh thứ tự.
4. **`(uidNumber>=10000)` có sắp xếp kết quả tăng dần không?** Không. Filter chọn entry thỏa điều kiện, không phải ORDER BY.
5. **Cùng một filter khoảng trên attribute đa trị có luôn buộc một giá trị nằm trong khoảng không?** Không. Điều kiện `>=` và `<=` có thể được thỏa bởi hai giá trị khác nhau.
6. **Vì sao `(!(uidNumber>=10000))` không đơn giản tương đương mọi entry có UID dưới 10000?** Vì thuộc tính có thể thiếu hoặc assertion là Undefined; NOT không biến Undefined thành TRUE.
7. **Muốn so sánh thời gian LDAP cần làm gì?** Dùng Generalized Time hợp lệ và kiểm tra `generalizedTimeOrderingMatch`/schema, timezone, độ phân giải và index của server.
8. **Extensible match có biến tên thuộc tính thiếu ORDERING thành sortable không?** Không. Rule và thuộc tính phải tương thích và được server hỗ trợ; `:=` cũng không phải ORDER BY.
9. **`@Attribute(name="uidNumber") String` có khiến LDAP so sánh như chuỗi không?** Không. Kiểu mapping Java không quyết định matching rule của schema server.
10. **Filter nhận giá trị từ HTTP nên xây thế nào?** Validate domain và dùng builder/placeholder escape RFC 4515; giữ tên thuộc tính/operator trong allowlist, không ghép chuỗi raw.
11. **Vì sao Search 0 entry chưa chứng minh bộ lọc ordering đúng?** Có thể schema không hỗ trợ rule, base/scope/ACL khác hoặc kết quả chưa hoàn tất; phải kiểm tra trên dữ liệu biên.
12. **Muốn kiểm tra matching rule đang áp dụng nên xem ở đâu?** Attribute type trong subschema (`SYNTAX`, `EQUALITY`, `ORDERING`, `SUBSTR` và các kế thừa), kết hợp kiểm thử thực tế.

**Ghi nhớ:** LDAP filter `>=`/`<=` là **so sánh theo ORDERING matching rule trong schema**, không phải so sánh chuỗi Java và không phải phép sắp xếp kết quả. Khi dùng Spring Data LDAP/Spring LDAP, hãy xác minh attribute type hỗ trợ ordering, hiểu ba-valued logic và thuộc tính đa trị, xây filter động an toàn, kiểm soát base/scope/ACL và thử với dữ liệu ở biên. Chỉ khi quy tắc matching, phạm vi truy vấn và độ đầy đủ của kết quả đều được kiểm chứng, ứng dụng mới có thể dựa vào các điều kiện thứ tự để ra quyết định nghiệp vụ.
