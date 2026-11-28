# Directory schema — Lược đồ dữ liệu của thư mục danh tính

## 1. Directory schema giải quyết vấn đề gì?

Một hệ thống IAM cần lưu người dùng, nhóm và những thông tin như tên, email hoặc mã định danh nội bộ. Nếu mỗi ứng dụng tự đặt tên và định dạng tùy ý, cùng một chủ thể có thể xuất hiện dưới các cấu trúc không tương thích.

Ứng dụng A gửi `department=Finance`, ứng dụng B gửi `departmentNumber=FIN`, còn ứng dụng C cố ghi một thuộc tính chưa được directory định nghĩa. Không có hợp đồng rõ ràng, client khó biết nên đọc gì và server khó kiểm soát dữ liệu nào được chấp nhận.

**Directory schema** là tập định nghĩa và quy tắc mô tả cấu trúc dữ liệu mà directory quản lý: loại thuộc tính, loại đối tượng, cú pháp giá trị, cách so sánh và các ràng buộc liên quan.

Bài này dùng mô hình LDAP để giải thích. Directory có thể là một phần của identity store, nhưng schema không thay cho xác thực, phân quyền hoặc quy trình cấp phát tài khoản.

Một schema phù hợp giúp hệ thống:

- Biểu diễn nhất quán các loại entry.
- Kiểm tra thuộc tính được phép và thuộc tính bắt buộc.
- Tra cứu theo đúng ngữ nghĩa so sánh.
- Mở rộng dữ liệu mà vẫn giữ khả năng tích hợp.
- Quản lý thay đổi cấu trúc trong suốt vòng đời danh tính.

## 2. Những khái niệm cần tách riêng

| Khái niệm | Vai trò | Ví dụ |
| --- | --- | --- |
| Entry | Một bản ghi trong directory | Hồ sơ của Linh |
| Attribute | Một thuộc tính của entry | `cn`, `sn`, `mail` |
| Attribute type | Định nghĩa loại thuộc tính và quy tắc của nó | Kiểu dữ liệu, matching rule, số lượng giá trị |
| Object class | Quy định loại entry và các thuộc tính liên quan | `inetOrgPerson`, `groupOfNames` |
| Schema | Hợp đồng cấu trúc và quy tắc dữ liệu | Các định nghĩa được directory công bố |
| DIT | Cách các entry được tổ chức thành cây | People, groups và các nhánh tổ chức |
| DN | Tên phân biệt của entry trong cây | `uid=linh,ou=people,dc=example,dc=com` |

Một entry có thể mang nhiều giá trị `objectClass`. Điều đó không có nghĩa nó là nhiều tài khoản; các lớp cùng mô tả loại và khả năng của một entry.

Schema và cây directory không phải cùng một thứ. Thêm nhánh `ou=people` không tự định nghĩa một thuộc tính mới. Định nghĩa một thuộc tính cũng không tự tạo entry nào trong cây.

Các thuật ngữ và mô hình thông tin LDAP được mô tả trong [RFC 4512](https://www.rfc-editor.org/rfc/rfc4512.html).

### 2.1. So sánh với cơ sở dữ liệu quan hệ

Có thể hình dung entry gần với một bản ghi, attribute gần với field và object class gần với một hợp đồng cấu trúc. Tuy nhiên, không nên ánh xạ máy móc object class thành bảng SQL.

LDAP cho phép một entry kết hợp một chuỗi lớp cấu trúc cùng những lớp bổ trợ phù hợp. Một thuộc tính có thể có nhiều giá trị mà không cần client coi nó như một chuỗi phân cách bằng dấu phẩy.

Schema LDAP cũng mang ngữ nghĩa so sánh thuộc tính. Chọn cú pháp và matching rule ảnh hưởng cách server hiểu điều kiện tìm kiếm.

## 3. Attribute type: tên field chưa phải toàn bộ định nghĩa

Một attribute type thường cần được xem xét ở các mặt sau:

| Thành phần | Ý nghĩa |
| --- | --- |
| OID | Định danh của phần tử schema |
| Tên | Tên mô tả mà client thường dùng |
| Cú pháp | Dạng dữ liệu của từng giá trị |
| Matching rule | Cách so sánh bằng, theo thứ tự hoặc chuỗi con khi được định nghĩa |
| Cardinality | Một hay nhiều giá trị |
| Kế thừa | Có lấy đặc tính từ một attribute type khác không |
| Mục đích sử dụng | Dữ liệu ứng dụng hay dữ liệu vận hành của directory |

Một số tên quen thuộc:

```text
cn    — common name
sn    — surname
uid   — định danh người dùng theo schema và chính sách triển khai
mail  — địa chỉ email theo schema được sử dụng
```

Không suy ra tính duy nhất, bất biến hoặc quyền sử dụng chỉ từ tên field. `uid` không tự trở thành khóa toàn cục không được cấp lại. `mail` không tự có nghĩa hộp thư đã được xác minh.

### 3.1. Một giá trị và nhiều giá trị

Một thuộc tính có `SINGLE-VALUE` cho phép tối đa một giá trị trên entry. Nếu thuộc tính đồng thời bắt buộc theo quy tắc áp dụng, nó phải có một giá trị phù hợp.

Thuộc tính nhiều giá trị được biểu diễn thành các giá trị riêng:

```ldif
mail: linh@example.com
mail: linh.personal@example.net
```

Đây không phải yêu cầu mọi schema cụ thể đều cho phép mọi kiểu email hoặc số lượng như nhau; client phải xem định nghĩa thực tế đang áp dụng.

Không nên tự lưu hai địa chỉ dưới dạng một giá trị:

```text
mail = "linh@example.com,linh.personal@example.net"
```

nếu hợp đồng yêu cầu từng giá trị là một địa chỉ.

Tập giá trị LDAP không phải danh sách có thứ tự ưu tiên. Nếu ứng dụng cần email chính, cần mô hình thể hiện lựa chọn đó thay vì lấy phần tử đầu tiên server trả về.

### 3.2. SINGLE-VALUE không phải UNIQUE

Hai entry khác nhau vẫn có thể cùng một giá trị của thuộc tính single-value nếu không có cơ chế ràng buộc duy nhất phù hợp.

Muốn mã subject không trùng trong phạm vi đã chọn, cần kiểm soát tạo và cập nhật, cùng cơ chế uniqueness mà nền tảng thực sự hỗ trợ. Không chỉ thêm `SINGLE-VALUE` rồi kết luận không thể tạo hai bản ghi trùng.

Tương tự, có schema cho phép ghi một thuộc tính không có nghĩa mọi client có quyền sửa thuộc tính đó.

## 4. Cú pháp và matching rule là hai phần khác nhau

Cú pháp xác định dạng giá trị. Matching rule xác định cách server so sánh một assertion với dữ liệu.

Ví dụ:

| Dạng dữ liệu hoặc quy tắc | Câu hỏi được giải quyết |
| --- | --- |
| Directory String | Giá trị biểu diễn chuỗi theo cú pháp directory |
| Integer | Giá trị có dạng số nguyên theo cú pháp tương ứng |
| DN syntax | Giá trị biểu diễn một distinguished name |
| Equality matching | Assertion có khớp giá trị không? |
| Ordering matching | Giá trị được so sánh theo thứ tự như thế nào? |
| Substring matching | Điều kiện chuỗi con được hiểu thế nào? |

Sự phân biệt giữa syntax và matching rule được quy định trong [RFC 4517](https://www.rfc-editor.org/rfc/rfc4517.html).

### 4.1. Cùng là chuỗi nhưng cách so sánh có thể khác

Một field dùng `caseIgnoreMatch` có ngữ nghĩa khác field dùng `caseExactMatch`. Không nên áp dụng `String.equals()` hoặc lowercase mọi thứ ở client rồi coi đó là mô phỏng đầy đủ matching của LDAP.

Ngay cả `caseExactMatch` cũng không có nghĩa mọi byte phải giống hệt trong mọi biểu diễn chuỗi: việc chuẩn bị chuỗi theo quy tắc LDAP vẫn có thể tham gia. Tên matching rule không thay cho việc đọc định nghĩa thực tế.

Với mã định danh ứng dụng, nên chọn biểu diễn chuẩn hóa được quản lý, ví dụ tập ký tự ASCII không có khoảng trắng, và kiểm tra định dạng ở ranh giới phù hợp. Schema chuỗi tổng quát không tự giới hạn thành đúng định dạng mã mà ứng dụng mong muốn.

### 4.2. Không mặc định mọi phép tìm kiếm đều có cùng ý nghĩa

Một thuộc tính được lưu không có nghĩa server hỗ trợ mọi dạng so sánh trên nó. Việc thiếu matching rule thích hợp có thể làm một loại filter không đánh giá được theo ý định.

Index cũng là vấn đề riêng. Định nghĩa equality matching không tự bảo đảm server đã có index phục vụ truy vấn lớn.

Khi thiết kế field sẽ được dùng tra cứu đăng nhập hoặc membership, cần xác định kiểu filter, matching và phạm vi tìm kiếm ngay từ đầu.

## 5. Object class: bắt buộc, được phép và kế thừa

Object class quy định các thuộc tính cần có hoặc được phép có trên entry, đồng thời có thể kế thừa từ lớp khác.

`MUST` diễn tả thuộc tính bắt buộc; `MAY` diễn tả thuộc tính có thể có theo định nghĩa lớp. Những từ này không phải quyền đọc hoặc ghi của người dùng.

Ví dụ các lớp người dùng thường gặp:

```text
top
 └── person
      └── organizationalPerson
           └── inetOrgPerson
```

`person` yêu cầu các thuộc tính `cn` và `sn`; `inetOrgPerson` kế thừa qua `organizationalPerson` và bổ sung các thuộc tính mô tả người dùng. Xem [RFC 4519](https://www.rfc-editor.org/rfc/rfc4519.html) và [RFC 2798](https://www.rfc-editor.org/rfc/rfc2798.html).

Một thuộc tính bắt buộc từ lớp cha không trở thành tùy chọn chỉ vì lớp con không nhắc lại nó trong phần định nghĩa trực tiếp.

### 5.1. Structural, auxiliary và abstract

- Structural class xác định loại cấu trúc của entry.
- Auxiliary class bổ sung tập thuộc tính theo quy tắc áp dụng.
- Abstract class đóng vai trò cơ sở trong hệ thống kế thừa.

Một entry có thể liệt kê nhiều structural class trong cùng chuỗi kế thừa. Điều đó khác với ghép tùy ý hai structural class không cùng quan hệ kế thừa, chẳng hạn coi cùng một entry vừa là người vừa là nhóm độc lập.

Khi cần bổ sung mã liên kết ứng dụng cho hồ sơ người, một auxiliary class riêng thường là cách tổ chức dễ hiểu hơn việc sửa lớp chuẩn hoặc thêm một lớp cấu trúc không liên quan.

Subschema và quy tắc của server còn có thể giới hạn lớp bổ trợ được chấp nhận. Vì vậy, chỉ nhìn danh sách `objectClass` trong một ví dụ chưa đủ kết luận entry sẽ được nhận ở mọi directory.

## 6. Đọc một entry LDIF

Ví dụ entry người dùng khi server hỗ trợ các schema liên quan:

```ldif
dn: uid=linh,ou=people,dc=example,dc=com
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: linh
cn: Linh Nguyen
sn: Nguyen
mail: linh@example.com
```

Các dòng `objectClass` biểu diễn chuỗi lớp tương thích. `cn` và `sn` đáp ứng yêu cầu được kế thừa; `uid` là giá trị dùng trong RDN của ví dụ.

Cần phân biệt:

| Thành phần | Ý nghĩa trong ví dụ |
| --- | --- |
| `dn` | Tên của entry trong cây directory |
| `objectClass` | Các lớp mô tả cấu trúc entry |
| `uid` | Một thuộc tính được dùng đặt tên entry |
| `cn`, `sn` | Thuộc tính tên theo schema |
| `mail` | Dữ liệu email được lưu |

Đây là ví dụ dữ liệu, chưa phải gói triển khai. Entry cha, schema cần thiết và quyền ghi phải tồn tại phù hợp trước khi tạo entry.

### 6.1. Hợp lệ cấu trúc không có nghĩa đáng tin về nội dung

Server có thể chấp nhận `mail` theo schema mà không biết hộp thư đã được xác minh. Một giá trị phòng ban có thể hợp lệ về cú pháp nhưng do người không có thẩm quyền cung cấp.

Schema kiểm soát hình dạng và một phần ngữ nghĩa dữ liệu. Nguồn có thẩm quyền, bằng chứng xác minh và quyền cập nhật cần được quản lý bằng cơ chế khác.

Không nên dùng kết quả “ghi entry thành công” như bằng chứng người dùng đã được xác thực hoặc được cấp quyền.

## 7. DN, RDN và định danh ổn định

Với DN:

```text
uid=linh,ou=people,dc=example,dc=com
```

RDN ở cấp entry là `uid=linh`; phần còn lại chỉ tới nhánh chứa entry. Các giá trị đặt tên cần phù hợp với thuộc tính và quy tắc áp dụng.

Một mô hình cây minh họa:

```text
dc=example,dc=com
├── ou=people
│   └── uid=linh
└── ou=groups
    └── cn=report-readers
```

Cây hỗ trợ tổ chức, phạm vi tra cứu và cách quản trị. Một OU mang tên tenant không tự cách ly tenant nếu ACL và truy vấn vẫn cho phép vượt phạm vi.

### 7.1. DN có thể thay đổi

Khi đổi tên hoặc chuyển entry sang nhánh khác, DN có thể thay đổi. Một entry khác cũng có thể được tạo về sau tại DN từng dùng trước đó.

Vì thế, dữ liệu nghiệp vụ không nên mặc định dùng DN như khóa bất biến đại diện cho cùng một chủ thể mãi mãi.

Một số directory hỗ trợ `entryUUID`, thuộc tính vận hành do server cấp để nhận diện đối tượng độc lập hơn với việc đổi tên. Mục đích này được mô tả trong [RFC 4530](https://www.rfc-editor.org/rfc/rfc4530.html).

Client cần kiểm tra khả năng của server và chính sách vòng đời. Xóa entry rồi tạo mới cùng DN không nên được coi như chắc chắn là cùng đối tượng cũ.

Ứng dụng có thể giữ ánh xạ:

```text
(directoryConnectionId, stableDirectoryObjectId)
    -> internalSubjectId
```

Không chỉ giữ DN rồi tự chuyển mọi quyền cũ sang bất kỳ entry nào đang chiếm tên đó.

### 7.2. Escape DN khác escape filter

Khi ghép một giá trị tên vào DN, phải dùng cách xử lý của DN. Khi tạo assertion trong search filter, phải dùng cách xử lý của filter.

Hai ngữ cảnh có biểu diễn riêng, được mô tả lần lượt trong [RFC 4514](https://www.rfc-editor.org/rfc/rfc4514.html) và [RFC 4515](https://www.rfc-editor.org/rfc/rfc4515.html).

Không dùng một hàm tự viết để thay vài ký tự rồi áp dụng cho cả hai. Nên dùng thư viện xây dựng DN và filter phù hợp, đồng thời giữ rõ base DN cùng phạm vi search.

Việc có schema không tự ngăn LDAP injection nếu ứng dụng ghép đầu vào trực tiếp thành biểu thức truy vấn.

## 8. Schema của nhóm và quan hệ membership

Ví dụ nhóm:

```ldif
dn: cn=report-readers,ou=groups,dc=example,dc=com
objectClass: top
objectClass: groupOfNames
cn: report-readers
member: uid=linh,ou=people,dc=example,dc=com
```

`groupOfNames` yêu cầu `cn` và `member`. Vì vậy, việc xóa thành viên cuối cùng có thể khiến entry không còn đáp ứng schema này. Định nghĩa được trình bày trong [RFC 4519, mục 3.5](https://www.rfc-editor.org/rfc/rfc4519.html#section-3.5).

Nếu nghiệp vụ cần nhóm rỗng, phải chọn mô hình hoặc khả năng nền tảng phù hợp. Không tùy tiện thêm một người giả làm thành viên chỉ để vượt kiểm tra cấu trúc, nhất là khi membership được dùng cấp quyền.

### 8.1. DN trong member không tự bảo đảm toàn vẹn tham chiếu

Giá trị `member` biểu diễn DN không có nghĩa server nào cũng tự cập nhật nó khi entry thành viên đổi tên, hoặc tự dọn mọi liên kết khi xóa entry.

Cần kiểm tra tính năng toàn vẹn tham chiếu và cấu hình thực tế. Nếu không có, provisioning hoặc tác vụ đối soát phải xử lý quan hệ bị mồ côi.

Với ứng dụng dùng khóa subject nội bộ ổn định, có thể duy trì ánh xạ và đối soát giữa quan hệ directory với membership ứng dụng.

### 8.2. Nhóm directory không tự là role ứng dụng

Một nhóm có tên `report-readers` chưa đủ để kết luận mọi ứng dụng phải trao quyền đọc mọi báo cáo.

Cần có ánh xạ được quản lý từ nhóm nguồn tới role hoặc permission, kèm phạm vi tenant và tài nguyên. Nhóm lồng nhau có được tính hay không cũng phải theo khả năng và chính sách cụ thể, không suy từ tên class.

Quyền thêm thành viên vào nhóm có thể trở thành quyền cấp truy cập gián tiếp. ACL sửa nhóm cần được đánh giá cùng lifecycle quyền.

## 9. Mở rộng schema cho liên kết IAM

Giả sử ứng dụng cần lưu một mã subject nội bộ trên entry người dùng. Yêu cầu gồm:

```text
Thuộc tính: x-exampleIamSubjectId
Giá trị minh họa: usr-1042
Mỗi entry có tối đa một giá trị
Phân biệt chữ hoa/thường theo matching đã chọn
Không do người dùng tự sửa
Tính duy nhất được thực thi trong phạm vi đã quản lý
```

Đây là yêu cầu thiết kế của ứng dụng. Không phải mọi phần của nó được thực thi chỉ bằng định nghĩa attribute type.

### 9.1. Chọn OID và tên

Mỗi phần tử mới cần OID được quản lý; nên dùng tên có prefix riêng để hạn chế xung đột. Hướng dẫn mở rộng schema của [OpenLDAP](https://www.openldap.org/doc/admin26/schema.html) giải thích việc quản lý OID, tên và định nghĩa bổ sung.

Ví dụ sau dùng nhánh `1.3.6.1.4.1.32473` phục vụ tài liệu. Enterprise Number 32473 được dành cho ví dụ theo [RFC 5612](https://www.rfc-editor.org/rfc/rfc5612.html); không dùng nhánh mẫu này làm phân bổ thực tế cho hệ thống sản xuất.

### 9.2. Định nghĩa thuộc tính

Dạng mô tả attribute type minh họa:

```text
( 1.3.6.1.4.1.32473.1.1
  NAME 'x-exampleIamSubjectId'
  DESC 'Application subject identifier'
  EQUALITY caseExactMatch
  SYNTAX 1.3.6.1.4.1.1466.115.121.1.15
  SINGLE-VALUE )
```

Trong ví dụ:

- `NAME` là tên dùng bởi client.
- `EQUALITY` chọn matching rule cho phép so sánh bằng.
- `SYNTAX` chỉ tới Directory String.
- `SINGLE-VALUE` giới hạn số giá trị trên một entry.

Cú pháp Directory String không tự kiểm tra quy tắc mã `usr-...`, tính duy nhất toàn hệ thống hoặc việc người sửa có được phép chuyển liên kết tài khoản hay không.

Nếu mã cần biểu diễn chính xác theo một tập ký tự và dạng chuẩn, lớp nghiệp vụ phải thực hiện quy tắc đó nhất quán với cách so sánh của directory.

### 9.3. Định nghĩa lớp bổ trợ

```text
( 1.3.6.1.4.1.32473.2.1
  NAME 'x-exampleIamIdentityLink'
  DESC 'Application identity association'
  SUP top
  AUXILIARY
  MUST x-exampleIamSubjectId )
```

Lớp này thêm yêu cầu có mã subject cho những entry mang nó. Nó không thay thế cấu trúc `inetOrgPerson`.

Sau khi schema phù hợp được nạp và được phép áp dụng, entry minh họa trở thành:

```ldif
dn: uid=linh,ou=people,dc=example,dc=com
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
objectClass: x-exampleIamIdentityLink
uid: linh
cn: Linh Nguyen
sn: Nguyen
mail: linh@example.com
x-exampleIamSubjectId: usr-1042
```

Các đoạn mô tả không phải lệnh nạp schema dùng chung cho mọi sản phẩm. Cách đóng gói, quyền thay schema và kiểm tra triển khai phụ thuộc server.

### 9.4. Quyền sửa mã liên kết

Nếu người dùng tự sửa `x-exampleIamSubjectId` thành mã của người khác, ứng dụng có thể bị dẫn tới liên kết sai tài khoản nếu chỉ tin field này.

Cần giới hạn quyền ghi cho quy trình liên kết được kiểm soát, kiểm tra chủ thể đích và giữ lịch sử thay đổi. Mã liên kết phải được xác lập bằng bằng chứng phù hợp, không phải chuỗi client tự khai.

Thêm field vào schema chỉ giúp server hiểu field; nó không chứng minh nội dung đúng hoặc người ghi có thẩm quyền về danh tính.

## 10. Đọc schema đang áp dụng

Client không nên mặc định mọi directory có cùng class, attribute hoặc cấu hình mở rộng.

Để khám phá subschema chi phối một entry, LDAP cung cấp thuộc tính vận hành `subschemaSubentry` trên entry đó. Sau khi lấy DN được tham chiếu, client thực hiện base search trên subschema với filter `(objectClass=subschema)` và yêu cầu các thuộc tính schema cần đọc. Xem [RFC 4512, mục 4.4](https://www.rfc-editor.org/rfc/rfc4512.html#section-4.4).

Ví dụ ý định truy vấn, không phải lệnh triển khai:

```text
Bước 1:
    base: uid=linh,ou=people,dc=example,dc=com
    scope: base
    filter: (objectClass=*)
    requested attributes:
        subschemaSubentry

Bước 2:
    base: DN nhận được từ subschemaSubentry
    scope: base
    filter: (objectClass=subschema)
    requested attributes:
        attributeTypes
        objectClasses
        matchingRules
        ldapSyntaxes
```

Không mặc định DN schema luôn là `cn=schema`, hoặc schema được công bố ở root DSE chắc chắn chi phối mọi entry.

Việc đọc schema cũng phụ thuộc quyền và khả năng server. Cần kết hợp thông tin công bố, hợp đồng tích hợp và thử nghiệm trên nền tảng thực tế; không suy rằng mọi schema nhìn thấy đều có thể được dùng theo mọi cách.

### 10.1. Thuộc tính vận hành

Các field như thời điểm tạo, thời điểm sửa hoặc UUID do server quản lý thường phục vụ mục đích vận hành.

Chúng có thể cần được yêu cầu rõ khi đọc và chịu giới hạn truy cập. Một response không chứa field không tự chứng minh field đó chưa tồn tại; có thể client chưa yêu cầu hoặc không có quyền đọc.

Không lấy `modifyTimestamp` của cả entry làm thời điểm xác minh email hoặc xác nhận từng thuộc tính. Sửa tên hiển thị cũng có thể làm thời điểm sửa entry thay đổi.

Tương tự, không biến metadata server quản lý thành dữ liệu tự phục vụ. Người dùng không nên được tự sửa bằng chứng nguồn hoặc định danh liên kết chỉ vì API hồ sơ nhận một đối tượng có nhiều field.

## 11. Schema và phân quyền bảo vệ hai khía cạnh khác nhau

| Yêu cầu | Schema có thể tham gia | Cơ chế vẫn cần |
| --- | --- | --- |
| Entry phải có mã subject khi dùng lớp bổ trợ | Kiểm tra thuộc tính bắt buộc | Quy trình xác lập đúng mã |
| Field chỉ có một giá trị | Cardinality của attribute | Uniqueness giữa các entry khi cần |
| Một giá trị đúng cú pháp | Kiểm tra syntax | Kiểm tra ý nghĩa nghiệp vụ |
| Người dùng chỉ sửa hồ sơ của mình | Không phải chức năng của MUST/MAY | Xác thực và ACL hoặc phân quyền tương ứng |
| Thành viên nhóm được đọc tài nguyên | Biểu diễn nhóm và member | Ánh xạ quyền và kiểm tra tài nguyên |
| Tenant A không đọc tenant B | Có thể hỗ trợ tổ chức dữ liệu | Phạm vi search, ACL và kiểm tra ứng dụng |
| Tài khoản đã đình chỉ không truy cập | Có thể có field biểu diễn trạng thái | Cơ chế thực thi lifecycle, phiên và quyền |

`MAY` không có nghĩa “người gọi nào cũng được ghi”. `MUST` không có nghĩa “mọi người đều phải được đọc”. Đó là những ràng buộc cấu trúc khác với quyền thao tác.

### 11.1. Một schema chuẩn không tự định nghĩa trạng thái IAM

Không nên mặc định mọi entry người dùng đều có một thuộc tính chuẩn chung tên `enabled` hoặc `suspended` với cùng ngữ nghĩa trên mọi directory.

Trạng thái tài khoản, khóa authenticator và đình chỉ membership có thể được biểu diễn bằng cơ chế riêng của sản phẩm hoặc ứng dụng. Cần đọc khả năng thực tế và ánh xạ rõ.

Xóa hoặc thay đổi một field mật khẩu không phải cách vô hiệu hóa tài khoản phổ quát. Thao tác lifecycle cần xét các đường xác thực và phiên đang còn hiệu lực.

### 11.2. Phạm vi dữ liệu ảnh hưởng tới IAM

Một ứng dụng có thể tra cứu đúng `uid` nhưng dùng base DN quá rộng, khiến hai tenant cùng có username trở thành kết quả mơ hồ.

Không nên chọn entry đầu tiên khi có nhiều kết quả rồi coi đó là đúng người. Cần namespace, phạm vi search và quy tắc uniqueness phù hợp.

Các định danh ổn định cần được giữ nguyên theo chính sách; tên hiển thị, vị trí trong cây và địa chỉ email có thể thay đổi mà không chuyển quyền sang người khác.

## 12. Thiết kế schema cho nhu cầu thực tế

Trước khi thêm một thuộc tính, cần xác định:

1. Giá trị đại diện cho điều gì trong nghiệp vụ?
2. Đã có thuộc tính chuẩn phù hợp ngữ nghĩa chưa?
3. Nguồn nào có thẩm quyền tạo hoặc sửa?
4. Cần một hay nhiều giá trị?
5. Cách so sánh và tra cứu là gì?
6. Phạm vi uniqueness hoặc bất biến nằm ở đâu?
7. Client và hệ thống đích có hiểu field đó không?
8. Quyền đọc, ghi và vòng đời dữ liệu được thực thi thế nào?

### 12.1. Không dùng lại thuộc tính chỉ vì thuận tiện

Không nhét toàn bộ role, tenant và trạng thái vào một chuỗi `description` rồi yêu cầu các service tự parse.

Ví dụ:

```text
description = "tenant-a:admin;tenant-b:reader;active=true"
```

Cách đó làm mất kiểu dữ liệu, ngữ nghĩa riêng và khả năng quản lý từng quan hệ. Một dấu phân cách hoặc giá trị không thống nhất có thể làm các consumer hiểu khác nhau.

Nếu dữ liệu quan hệ phức tạp không phù hợp với mô hình field hiện tại, có thể cần entry quan hệ riêng hoặc lưu trong kho quyền ứng dụng. Không phải mọi cấu trúc IAM đều cần ép vào cùng một entry người dùng.

### 12.2. Không sửa ý nghĩa lớp chuẩn để đáp ứng cục bộ

Thay đổi định nghĩa của một OID chuẩn trong một môi trường có thể làm client tin rằng nó đang dùng cùng một schema trong khi ý nghĩa đã khác.

Nên mở rộng bằng phần tử riêng có quản lý hoặc chọn cấu trúc đã hỗ trợ phù hợp. Giữ tài liệu ánh xạ và phiên bản để các connector biết hợp đồng đang dùng.

Một schema được mở rộng tốt không chỉ “server cho ghi được”, mà còn để các bên hiểu cùng một giá trị theo cùng một cách.

### 12.3. Tránh dùng cơ chế nới lỏng như giải pháp mặc định

Dùng `extensibleObject` hoặc tắt kiểm tra schema để xử lý mọi lỗi có thể che giấu thiếu sót trong mô hình.

`extensibleObject` không biến mọi tên field chưa định nghĩa thành thuộc tính hợp lệ và không xóa yêu cầu bắt buộc của các lớp khác. Cần hiểu chính xác cơ chế được nền tảng hỗ trợ trước khi sử dụng.

Nếu một client gửi field lạ, hướng xử lý nên là kiểm tra hợp đồng, ánh xạ và nhu cầu mở rộng thay vì mở rộng vô điều kiện quyền ghi hoặc cấu trúc dữ liệu.

## 13. Thay đổi schema theo từng giai đoạn

Một thay đổi tưởng nhỏ có thể ảnh hưởng dữ liệu đang có, connector, filter và quyền truy cập. Ví dụ thêm `MUST` có thể làm các entry cũ hoặc request cập nhật không còn đáp ứng hợp đồng.

Một quy trình thiết kế có thể gồm:

| Giai đoạn | Việc cần làm |
| --- | --- |
| Khảo sát | Đọc schema, client và dữ liệu đang dùng |
| Thiết kế | Chọn OID, tên, syntax, matching, cardinality và ACL |
| Kiểm tra tương thích | Đánh giá dữ liệu cũ và các điểm tích hợp |
| Mở rộng | Bổ sung định nghĩa và cơ chế đọc chịu được dữ liệu chưa có |
| Bổ sung dữ liệu | Điền từ nguồn có thẩm quyền, kiểm tra xung đột |
| Chuyển sử dụng | Đổi tra cứu hoặc quyết định sang dữ liệu mới theo phạm vi kiểm soát |
| Đối soát | Kiểm tra các replica, consumer và quan hệ tham chiếu |
| Dọn phần cũ | Chỉ bỏ khi không còn phụ thuộc và có kế hoạch phục hồi |

Đây là quy trình minh họa để lập kế hoạch, không phải yêu cầu mọi sản phẩm hỗ trợ thay schema động theo cùng một cách.

### 13.1. Ví dụ chuyển từ DN sang mã liên kết ổn định

Ứng dụng cũ lưu DN làm khóa người dùng. Muốn dùng mã subject riêng, có thể:

```text
1. Định nghĩa field và auxiliary class phù hợp.
2. Lập ánh xạ có bằng chứng giữa entry hiện hữu và subject.
3. Ghi mã và lớp bổ trợ bằng thao tác đáp ứng trạng thái hợp lệ.
4. Kiểm tra không trùng và không liên kết sai.
5. Chuyển client sang tra cứu bằng khóa đã quản lý.
6. Kiểm thử đổi tên, di chuyển, xóa và tạo lại entry.
```

Nếu lớp bổ trợ yêu cầu field, không nên triển khai thành các bước làm entry tạm thiếu thuộc tính bắt buộc. Cần chọn thao tác và thứ tự phù hợp khả năng server.

Không tự suy ánh xạ chỉ từ email hoặc tên giống nhau. Dữ liệu nhập sai ở giai đoạn này có thể chuyển quyền giữa hai tài khoản.

### 13.2. Thay đổi matching hoặc cardinality

Chuyển từ nhiều giá trị sang một giá trị cần xử lý những entry đang có nhiều giá trị trước. Không để server tự bỏ phần còn lại mà chưa có quyết định nghiệp vụ.

Thay đổi cách so sánh có thể tạo các nhóm giá trị bị coi như tương đương hoặc làm truy vấn cũ đổi kết quả. Cần phân tích dữ liệu và các quy tắc uniqueness liên quan, không chỉ kiểm tra schema mới có cú pháp hợp lệ.

### 13.3. Tính nhất quán giữa các node

Trong triển khai nhiều node, client ghi vào một nơi nhưng đọc hoặc failover sang nơi khác. Cần xác minh schema và dữ liệu cần thiết có mặt tại mọi điểm phục vụ liên quan theo cơ chế của nền tảng.

Không mặc định thay schema trên một node làm mọi replica đồng bộ ngay. Cơ chế phân phối schema, thứ tự cập nhật và khả năng rollback cần được kiểm tra riêng.

Rollback schema cũng không chỉ là xóa một định nghĩa. Entry hoặc client có thể đã phụ thuộc vào thuộc tính mới; cần kế hoạch xử lý dữ liệu và các tham chiếu đó.

## 14. Kiểm thử bằng cấu trúc và hành vi IAM

| Tình huống | Điều cần xác minh |
| --- | --- |
| Entry có đủ class và thuộc tính bắt buộc | Được chấp nhận trong môi trường đã cấu hình |
| Thiếu thuộc tính bắt buộc kế thừa | Không vượt kiểm tra chỉ vì lớp con không nhắc lại |
| Gửi thuộc tính chưa định nghĩa | Được xử lý đúng theo schema, không tự tạo field |
| Ghi nhiều giá trị vào field single-value | Không được lưu trái cardinality |
| Hai entry trùng mã subject | Cơ chế uniqueness ngoài cardinality hoạt động theo phạm vi |
| Người dùng tự sửa mã liên kết | Bị từ chối theo quyền cập nhật |
| Giá trị khác nhau về chữ hoa/thường | Kết quả phù hợp matching và quy tắc chuẩn hóa đã chọn |
| Ký tự đặc biệt trong tên hoặc filter | Được xử lý đúng ngữ cảnh, không làm đổi cấu trúc truy vấn |
| Đổi DN của người dùng | Liên kết ứng dụng vẫn theo đúng định danh ổn định |
| Xóa rồi tạo entry mới cùng DN | Không tự nhận dữ liệu và quyền của entry cũ |
| Xóa thành viên cuối khỏi nhóm | Phù hợp schema nhóm và quy trình nghiệp vụ |
| Di chuyển hoặc xóa thành viên | Các tham chiếu nhóm được cập nhật hoặc đối soát |
| Connector gửi field sai ngữ nghĩa | Không được dùng cấp quyền chỉ vì server lưu được |
| Client đọc trên replica | Schema và dữ liệu cần thiết đáp ứng thiết kế |
| Đổi schema rồi rollback | Không bỏ sót entry, client hoặc quyền phụ thuộc |

Kiểm thử schema không thay cho kiểm thử quyền. Một ca ghi hợp lệ phải được chạy bằng actor phù hợp; một ca bị từ chối cần chứng minh đúng ranh giới đang bảo vệ, không chỉ do server ngừng hoạt động.

Nên kiểm tra cả thay đổi vào dữ liệu và tác động ở ứng dụng: danh tính nào được xác định, membership nào được dùng và quyền nào thay đổi. Điều đó giúp phát hiện lỗi mapping mà kiểm tra cú pháp không nhìn thấy.

## 15. Chẩn đoán lỗi theo đúng lớp

| Hiện tượng | Hướng kiểm tra |
| --- | --- |
| Server không biết tên thuộc tính | Schema được nạp chưa, tên hoặc OID có đúng không |
| Entry vi phạm object class | Thuộc tính bắt buộc, thuộc tính được phép và chuỗi kế thừa |
| Giá trị sai cú pháp | Kiểu dữ liệu và cách encode theo schema thực tế |
| Field single-value bị ghi nhiều giá trị | Dữ liệu đầu vào và phép cập nhật |
| Không tìm thấy entry cha hoặc base | DN, cây hiện hữu và phạm vi thao tác |
| Không đủ quyền truy cập | Danh tính kết nối và ACL cho đúng entry/attribute |
| Ghi được nhưng tìm không đúng | Matching, filter, base DN, cache và mapping |
| Dữ liệu có trên node này nhưng không có node khác | Trạng thái triển khai và đồng bộ |
| Schema hợp lệ nhưng ứng dụng cấp sai quyền | Nguồn thuộc tính, liên kết subject và chính sách IAM |

Không sửa mọi lỗi bằng cách dùng tài khoản quản trị hoặc bỏ kiểm tra schema. Điều đó có thể làm thao tác thành công trong thử nghiệm nhưng che mất lỗi mô hình hoặc quyền.

Khi điều tra, cần giữ thông tin lỗi đủ dùng nhưng tránh log mật khẩu bind, secret hoặc toàn bộ dữ liệu cá nhân không cần thiết.

## 16. Vận dụng trong hệ thống danh tính

Directory schema là hợp đồng biểu diễn dữ liệu. Nó giúp server và client thống nhất loại entry, thuộc tính, cú pháp và cách so sánh.

Một thiết kế IAM còn phải giữ rõ định danh ổn định, nguồn có thẩm quyền và quyền sửa dữ liệu. Nhóm, email hoặc mã subject hợp lệ về schema chỉ trở thành đầu vào đáng tin khi có quy trình quản lý tương ứng.

Khi thay đổi schema, hãy kiểm tra chuỗi tác động từ entry đến connector, cache, liên kết tài khoản và quyết định truy cập. Cách nhìn này giúp thư mục danh tính vừa có cấu trúc rõ ràng vừa hỗ trợ đúng vòng đời quyền của người dùng và workload.
