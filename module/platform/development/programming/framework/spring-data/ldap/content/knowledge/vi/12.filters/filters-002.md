# Điều kiện bằng, khác, hiện diện và không hiện diện

Khi truy vấn một thư mục LDAP, việc chọn đúng **search filter** quyết định entry nào được trả về. Bốn nhu cầu rất phổ biến là **bằng** (*equality*), **khác** (*negated equality*), **có thuộc tính** (*presence*) và **không có thuộc tính** (*absence*). Chúng trông giống các phép so sánh trong SQL nhưng có những khác biệt quan trọng: thuộc tính LDAP có thể đa giá trị, filter dùng cú pháp riêng và toán tử “khác” không có ký hiệu `!=` trực tiếp.

Bài này thuộc chương **Bộ lọc** của `SPRING_DATA_LDAP`. Người học sẽ đọc cú pháp LDAP theo RFC 4515, hiểu kết quả lọc trong mô hình entry/DN/objectClass và triển khai truy vấn bằng `LdapTemplate` hoặc các thành phần dựng bộ lọc an toàn của Spring LDAP. Các ví dụ cũng gắn với schema, phân quyền đọc và kiểm thử trên directory thật.

## 1. Mục tiêu

Sau khi học, bạn có thể:

1. Viết đúng filter bằng `(attr=value)`, phủ định `(!(attr=value))`, hiện diện `(attr=*)` và không hiện diện `(!(attr=*))`.
2. Phân biệt **“không bằng X”** với **“có giá trị và không bằng X”**.
3. Dự đoán kết quả khi một entry không có thuộc tính hoặc thuộc tính có nhiều giá trị.
4. Kết hợp `&`, `|`, `!` để giải quyết các tình huống tìm kiếm người dùng.
5. Viết truy vấn Spring LDAP với `LdapQueryBuilder` và các lớp `EqualsFilter`, `PresentFilter`, `NotFilter`, `AndFilter`.
6. Phòng tránh LDAP injection, tránh nhầm giá trị rỗng với thuộc tính thiếu và kiểm chứng kết quả theo schema/ACL.

## 2. Bối cảnh: tìm kiếm các entry người dùng

Giả sử directory có nhánh:

~~~text
dc=example,dc=org
└── ou=people
    ├── uid=lan
    ├── uid=minh
    ├── uid=hoa
    └── uid=an
~~~

Cả bốn entry đều có `objectClass=inetOrgPerson`. Nhờ kế thừa từ `person`, mỗi entry đều phải có `cn` và `sn`. Chúng khác nhau ở những thuộc tính tùy chọn:

| Entry (RDN) | `uid` | `mail` | `employeeType` |
| --- | --- | --- | --- |
| `uid=lan` | `lan` | `lan@example.org` | `staff` |
| `uid=minh` | `minh` | *Không có* | `contractor` |
| `uid=hoa` | `hoa` | `hoa@example.org` | `contractor` |
| `uid=an` | `an` | `an@example.org` | *Không có* |

Trong bảng, “không có” nghĩa là **entry thực sự không chứa giá trị cho thuộc tính đó**, không phải chuỗi trống. Mỗi entry còn có DN đầy đủ, ví dụ `uid=lan,ou=people,dc=example,dc=org`.

Trong truy vấn LDAP, **base DN** và **search scope** chọn phạm vi entry; **filter** quyết định entry nào khớp trong phạm vi đó. Ví dụ, nếu base là `ou=people,dc=example,dc=org` với scope `ONELEVEL`, các filter dưới đây sẽ xét bốn entry con trực tiếp.

## 3. Cú pháp filter LDAP cần nhớ

RFC 4515 biểu diễn filter LDAP bằng chuỗi có dấu ngoặc đơn. Những mẫu cơ bản:

| Mục đích | Filter LDAP | Cách đọc |
| --- | --- | --- |
| Bằng một giá trị | `(uid=lan)` | Thuộc tính `uid` khớp giá trị `lan` theo matching rule. |
| Khác một giá trị | `(!(employeeType=contractor))` | Phủ định điều kiện bằng `contractor`. |
| Hiện diện | `(mail=*)` | Thuộc tính `mail` tồn tại và có giá trị. |
| Không hiện diện | `(!(mail=*))` | Thuộc tính `mail` không hiện diện. |
| Có giá trị và khác | `(&(employeeType=*)(!(employeeType=contractor)))` | Có `employeeType`, đồng thời không khớp `contractor`. |
| Kết hợp AND | `(&(objectClass=inetOrgPerson)(mail=*))` | Vừa là người dùng, vừa có `mail`. |
| Kết hợp OR | `(|(uid=lan)(uid=hoa))` | Có `uid` là `lan` hoặc `hoa`. |

### Các toán tử logic

~~~text
(&(A)(B))     A AND B
(|(A)(B))     A OR B
(!(A))        NOT A
~~~

Trong cú pháp thực tế, thay `(A)` và `(B)` bằng các filter hoàn chỉnh. LDAP **không có toán tử chuỗi `!=` chuẩn**; hãy dùng `!` bao ngoài một điều kiện bằng.

Đặc biệt:

- `(mail=*)` là **presence filter**.
- `(mail=)` là một **equality filter có giá trị khẳng định rỗng**, không có nghĩa “thiếu mail”. Tùy schema, giá trị rỗng có thể không hợp lệ hoặc không được lưu.
- `(cn=Lan*)` là **substring filter** dùng ký tự đại diện, khác với equality `(cn=Lan)`.
- `(cn=\2a)` tìm giá trị chứa dấu `*` thật sự (được escape), còn `(cn=*)` kiểm tra thuộc tính tồn tại.

## 4. Điều kiện bằng: `(attr=value)`

Ví dụ:

~~~ldap
(uid=lan)
~~~

Với bốn entry mẫu, điều kiện này trả về `uid=lan`. Đối với `mail`:

~~~ldap
(mail=lan@example.org)
~~~

Kết quả cũng là `uid=lan`.

### “Bằng” có nghĩa là so chuỗi chính xác theo từng byte?

Không nhất thiết. Mỗi loại thuộc tính trong **LDAP schema** có thể định nghĩa một **equality matching rule**. Quy tắc đó quyết định cách so sánh: có thể không phân biệt chữ hoa/thường hoặc xử lý khoảng trắng theo chuẩn của thuộc tính.

Ví dụ, `cn` thường dùng quy tắc so khớp chuỗi phù hợp với tên người, còn `uid` có thể dùng quy tắc khác theo schema. Đừng tự suy ra mọi phép so sánh đều phân biệt hoa/thường hoặc tự động bỏ dấu tiếng Việt; hãy kiểm chứng quy tắc trên directory sử dụng.

### Thuộc tính đa giá trị

Giả sử một entry chứa:

~~~ldif
cn: Nguyen Thi Lan
cn: Lan Nguyen
~~~

Filter `(cn=Lan Nguyen)` **khớp nếu có ít nhất một giá trị** của `cn` đáp ứng equality matching rule. Ngược lại, `(!(cn=Lan Nguyen))` chỉ khớp khi điều kiện bằng bị phủ định thành TRUE, tức không có giá trị `cn` nào khớp trong tình huống so sánh hợp lệ.

Điều này quan trọng khi diễn giải “khác”: **NOT equality** không có nghĩa “tồn tại ít nhất một giá trị khác X”. Nếu một entry có cả giá trị X và Y, điều kiện `(attr=X)` vẫn khớp, nên `(!(attr=X))` không khớp.

## 5. Điều kiện khác: phủ định điều kiện bằng

Nhu cầu: tìm người **không có `employeeType=contractor`**.

~~~ldap
(!(employeeType=contractor))
~~~

Trên dữ liệu mẫu, filter trả về:

- `uid=lan` vì `employeeType=staff`.
- `uid=an` vì thuộc tính `employeeType` không có, nên equality với `contractor` không khớp trong điều kiện thông thường.

Nó không trả về `uid=minh` và `uid=hoa` vì hai entry có giá trị `contractor`.

### Cạm bẫy: “khác X” có thể bao gồm entry không có thuộc tính

Nếu yêu cầu thực tế là **“nhân viên có khai báo employeeType và loại này khác contractor”**, chỉ dùng NOT là chưa đủ. Hãy thêm điều kiện hiện diện:

~~~ldap
(&(employeeType=*)(!(employeeType=contractor)))
~~~

Lúc đó chỉ `uid=lan` khớp. `uid=an` bị loại vì thiếu thuộc tính.

So sánh:

| Filter | Kết quả với dữ liệu mẫu | Ý nghĩa nghiệp vụ |
| --- | --- | --- |
| `(employeeType=contractor)` | `minh, hoa` | Là contractor. |
| `(!(employeeType=contractor))` | `lan, an` | Không khớp contractor, kể cả entry thiếu thuộc tính trong ca thường. |
| `(&(employeeType=*)(!(employeeType=contractor)))` | `lan` | Có phân loại và không phải contractor. |
| `(!(employeeType=*))` | `an` | Chưa khai báo loại nhân viên. |

**Ngoại lệ cần hiểu:** LDAPv3 sử dụng logic ba giá trị **TRUE, FALSE và Undefined**. Nếu server không nhận ra thuộc tính, không hỗ trợ matching rule hoặc không đánh giá được giá trị hợp lệ, một điều kiện có thể thành **Undefined**. Phủ định Undefined vẫn là Undefined và entry không được trả về. Vì thế diễn giải ở bảng giả định thuộc tính có trong schema, matching rule hợp lệ, server có dữ liệu/khả năng đánh giá phù hợp.

## 6. Điều kiện hiện diện: `(attr=*)`

Khi muốn tìm người có email:

~~~ldap
(mail=*)
~~~

Kết quả mẫu là `lan, hoa, an`; `minh` bị loại vì không có `mail`.

Để chỉ tìm user thuộc `inetOrgPerson` có email:

~~~ldap
(&(objectClass=inetOrgPerson)(mail=*))
~~~

Các tình huống cần điều kiện hiện diện:

- Kiểm tra hồ sơ đã có email hoặc số điện thoại trước khi hiển thị nút liên lạc.
- Chọn entry có `employeeNumber` trước khi gửi sang hệ thống nhân sự.
- Giới hạn danh sách cho những entry có thuộc tính bắt buộc **theo nghiệp vụ** nhưng chỉ là `MAY` trong schema.

Lưu ý `objectClass` không phải trường tùy chọn trong entry LDAP hợp lệ. `(objectClass=inetOrgPerson)` lọc kiểu entry, còn `(objectClass=*)` thường không hữu ích để tìm hồ sơ thiếu thông tin.

### Hiện diện khác kiểm tra chuỗi không rỗng

LDAP chuẩn không cho phép entry lưu các thuộc tính “có mặt nhưng hoàn toàn không có giá trị” theo cùng cách đối tượng JSON có khóa với giá trị `null`. Entry chỉ được xem là có thuộc tính khi có giá trị theo mô hình dữ liệu LDAP. Điều kiện presence không kiểm tra giá trị có hợp lệ theo nghiệp vụ hay không: `(mail=*)` không có nghĩa email có định dạng đúng, đã xác minh hoặc có thể gửi thư tới được.

## 7. Điều kiện không hiện diện: `(!(attr=*))`

Nhu cầu: lập danh sách người chưa được ghi email.

~~~ldap
(!(mail=*))
~~~

Kết quả dữ liệu mẫu: `uid=minh`.

Nếu muốn giới hạn đúng đối tượng người dùng:

~~~ldap
(&(objectClass=inetOrgPerson)(!(mail=*)))
~~~

Lưu ý dấu `!` nằm **bên ngoài toàn bộ presence filter**. Các biểu thức `(mail!=*)` hoặc `(mail=!)` không biểu đạt “không hiện diện” theo cú pháp LDAP.

### Không hiện diện ≠ không được trả về trong kết quả Search

Một search có thể chỉ yêu cầu trả thuộc tính `uid`, khiến response **không chứa `mail`** dù entry thực sự có email. Hoặc ACL có thể hạn chế quyền đọc thuộc tính. Do đó không thể kết luận một entry thiếu `mail` chỉ vì đối tượng Java nhận được `null` hay kết quả `ldapsearch` không hiển thị email.

Presence filter được server đánh giá trên dữ liệu và theo cơ chế kiểm soát truy cập của server. Kết quả nhìn thấy phụ thuộc schema, ACL và quyền của danh tính Bind; hãy kiểm thử bằng đúng tài khoản dịch vụ được dùng trong ứng dụng.

## 8. Ma trận kết quả tổng hợp

Dùng bộ dữ liệu từ mục 2, với giả định các thuộc tính đều được schema hỗ trợ và tài khoản tìm kiếm có quyền phù hợp.

| Filter | lan | minh | hoa | an |
| --- | :---: | :---: | :---: | :---: |
| `(uid=lan)` | ✓ | – | – | – |
| `(mail=*)` | ✓ | – | ✓ | ✓ |
| `(!(mail=*))` | – | ✓ | – | – |
| `(employeeType=contractor)` | – | ✓ | ✓ | – |
| `(!(employeeType=contractor))` | ✓ | – | – | ✓ |
| `(&(employeeType=*)(!(employeeType=contractor)))` | ✓ | – | – | – |
| `(&(mail=*)(!(mail=lan@example.org)))` | – | – | ✓ | ✓ |
| `(|(!(mail=*))(employeeType=contractor))` | – | ✓ | ✓ | – |

Dấu ✓ nghĩa entry được filter chọn; dấu – nghĩa không. Thứ tự entry khi search **không mặc định được đảm bảo**, trừ khi có cơ chế sắp xếp phù hợp từ directory.

## 9. Thiết lập ví dụ thực hành với LDIF

Các entry trong bảng có thể nạp vào một directory dành cho test. Giả định `dc=example,dc=org` đã tồn tại và schema `inetOrgPerson` được nạp:

~~~ldif
dn: ou=people,dc=example,dc=org
objectClass: top
objectClass: organizationalUnit
ou: people

dn: uid=lan,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: lan
cn: Nguyen Thi Lan
sn: Nguyen
mail: lan@example.org
employeeType: staff

dn: uid=minh,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: minh
cn: Tran Van Minh
sn: Tran
employeeType: contractor

dn: uid=hoa,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: hoa
cn: Le Thi Hoa
sn: Le
mail: hoa@example.org
employeeType: contractor

dn: uid=an,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: an
cn: Nguyen Van An
sn: Nguyen
mail: an@example.org
~~~

Tài khoản dùng để **nạp LDIF** phải có quyền thêm entry vào nhánh thử nghiệm. Tài khoản **đọc/filter** trong ứng dụng có thể dùng quyền ít hơn. Các DN, domain và hồ sơ trên chỉ phục vụ ví dụ; không dùng mật khẩu hoặc dữ liệu cá nhân thực tế.

Một số server yêu cầu cấu hình riêng để chấp nhận thuộc tính mở rộng; nếu nạp `employeeType` thất bại, hãy kiểm tra schema `inetOrgPerson` và thuộc tính trên server trước khi kết luận filter sai.

## 10. Chạy thử bốn loại filter bằng ldapsearch

Giả sử đã thiết lập TLS và tài khoản chỉ đọc `cn=svc-reader,ou=service,dc=example,dc=org`:

### 10.1. Bằng

~~~bash
ldapsearch -x \
  -H ldaps://ldap.example.org:636 \
  -D "cn=svc-reader,ou=service,dc=example,dc=org" -W \
  -b "ou=people,dc=example,dc=org" -s one \
  "(uid=lan)" dn uid cn mail employeeType
~~~

Dự kiến: `uid=lan`.

### 10.2. Khác với contractor, có giá trị employeeType

~~~bash
ldapsearch -x \
  -H ldaps://ldap.example.org:636 \
  -D "cn=svc-reader,ou=service,dc=example,dc=org" -W \
  -b "ou=people,dc=example,dc=org" -s one \
  "(&(employeeType=*)(!(employeeType=contractor)))" \
  dn uid employeeType
~~~

Dự kiến: `uid=lan`. Nếu bỏ `(employeeType=*)`, `uid=an` cũng có thể được chọn trong bộ fixture.

### 10.3. Hiện diện mail

~~~bash
ldapsearch -x \
  -H ldaps://ldap.example.org:636 \
  -D "cn=svc-reader,ou=service,dc=example,dc=org" -W \
  -b "ou=people,dc=example,dc=org" -s one \
  "(mail=*)" dn uid mail
~~~

Dự kiến: `lan, hoa, an`.

### 10.4. Không hiện diện mail

~~~bash
ldapsearch -x \
  -H ldaps://ldap.example.org:636 \
  -D "cn=svc-reader,ou=service,dc=example,dc=org" -W \
  -b "ou=people,dc=example,dc=org" -s one \
  "(!(mail=*))" dn uid
~~~

Dự kiến: `uid=minh`.

Tham số `-W` yêu cầu nhập mật khẩu qua lời nhắc thay vì ghi mật khẩu vào tham số command. `-s one` chỉ chọn entry con trực tiếp của base DN. Trước khi chạy các lệnh thật, cần cấu hình truststore/chứng chỉ hợp lệ cho công cụ `ldapsearch`.

## 11. Dựng các điều kiện trong Spring Data LDAP

Các lớp filter và builder dưới đây nằm trong Spring LDAP, được sử dụng bởi hệ sinh thái Spring Data LDAP. Khi truy vấn bằng `LdapTemplate`, ứng dụng không cần tự chuyển đổi thủ công từ syntax filter sang giao thức SearchRequest.

### 11.1. LdapQueryBuilder: equality, NOT, presence và absence

~~~java
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;
import org.springframework.ldap.query.SearchScope;

// 1) uid bằng giá trị từ tham số: (uid=<giá trị an toàn>)
LdapQuery equal = LdapQueryBuilder.query()
        .base("ou=people")
        .searchScope(SearchScope.ONELEVEL)
        .where("uid").is(uid);

// 2) khác contractor: (!(employeeType=contractor))
LdapQuery notEqual = LdapQueryBuilder.query()
        .base("ou=people")
        .where("employeeType").not().is("contractor");

// 3) có mail: (mail=*)
LdapQuery hasMail = LdapQueryBuilder.query()
        .base("ou=people")
        .where("mail").isPresent();

// 4) không có mail: (!(mail=*))
LdapQuery missingMail = LdapQueryBuilder.query()
        .base("ou=people")
        .where("mail").not().isPresent();

// 5) có employeeType và không phải contractor:
// (&(employeeType=*)(!(employeeType=contractor)))
LdapQuery knownNonContractor = LdapQueryBuilder.query()
        .base("ou=people")
        .where("employeeType").isPresent()
        .and("employeeType").not().is("contractor");
~~~

`.is(...)` tạo equality; `.not()` phủ định **điều kiện kế tiếp**; `.isPresent()` tạo presence. Kết hợp `.isPresent().and("employeeType").not().is("contractor")` thể hiện đúng yêu cầu “khác và có khai báo”.

**Không nên đưa cả một biểu thức filter do client gửi vào `.filter(String)`.** Biến đầu vào `uid` ở trên là **giá trị của một phép so sánh**, được Spring LDAP encoding như giá trị filter; ứng dụng vẫn cần validation theo quy tắc username. Khi cần loại biểu thức phức tạp, hãy dùng builder hoặc các lớp `Filter`.

### 11.2. Kết hợp filter dưới dạng đối tượng

Spring LDAP cũng có `EqualsFilter`, `PresentFilter`, `NotPresentFilter`, `NotFilter`, `AndFilter` và `OrFilter`:

~~~java
import org.springframework.ldap.filter.AndFilter;
import org.springframework.ldap.filter.EqualsFilter;
import org.springframework.ldap.filter.Filter;
import org.springframework.ldap.filter.NotFilter;
import org.springframework.ldap.filter.NotPresentFilter;
import org.springframework.ldap.filter.PresentFilter;

// Có employeeType và khác contractor
AndFilter knownNonContractor = new AndFilter();
knownNonContractor.and(new PresentFilter("employeeType"));
knownNonContractor.and(
        new NotFilter(new EqualsFilter("employeeType", "contractor"))
);
String ldapFilter = knownNonContractor.encode();

// Không có mail
Filter noMail = new NotPresentFilter("mail");
String missingMailFilter = noMail.encode();

// Có mail
Filter withMail = new PresentFilter("mail");
String presentMailFilter = withMail.encode();
~~~

Các chuỗi encode tương ứng:

~~~text
(&(employeeType=*)(!(employeeType=contractor)))
(!(mail=*))
(mail=*)
~~~

Khi cần thêm `objectClass=inetOrgPerson` để giới hạn kiểu entry:

~~~java
AndFilter filter = new AndFilter();
filter.and(new EqualsFilter("objectClass", "inetOrgPerson"));
filter.and(new PresentFilter("mail"));

LdapQuery query = LdapQueryBuilder.query()
        .base("ou=people")
        .countLimit(100)
        .filter(filter);
~~~

Với `LdapQueryBuilder`, phương thức `.filter(Filter)` là cách cung cấp filter object hoàn chỉnh. Không trộn `.filter(...)` với chuỗi `.where(...)` trong cùng một query builder sau khi đã chỉ định filter, vì đó là hai cách dựng filter loại trừ nhau.

### 11.3. Ví dụ service tìm kiếm trên directory

Giả sử `spring.ldap.base=dc=example,dc=org`, Spring Boot đã tạo `LdapTemplate` với tài khoản service chỉ đọc và kết nối TLS:

~~~java
import java.util.List;

import org.springframework.ldap.core.ContextMapper;
import org.springframework.ldap.core.DirContextOperations;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;
import org.springframework.ldap.query.SearchScope;
import org.springframework.stereotype.Service;

@Service
public class PeopleFilterService {

    private final LdapTemplate ldapTemplate;

    public PeopleFilterService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<String> findByUid(String uid) {
        if (uid == null || uid.isBlank()) {
            throw new IllegalArgumentException("uid must not be blank");
        }

        LdapQuery query = baseQuery()
                .where("objectClass").is("inetOrgPerson")
                .and("uid").is(uid);

        return listUids(query);
    }

    public List<String> findWithEmail() {
        LdapQuery query = baseQuery()
                .where("objectClass").is("inetOrgPerson")
                .and("mail").isPresent();

        return listUids(query);
    }

    public List<String> findWithoutEmail() {
        LdapQuery query = baseQuery()
                .where("objectClass").is("inetOrgPerson")
                .and("mail").not().isPresent();

        return listUids(query);
    }

    public List<String> findKnownNonContractors() {
        LdapQuery query = baseQuery()
                .where("objectClass").is("inetOrgPerson")
                .and("employeeType").isPresent()
                .and("employeeType").not().is("contractor");

        return listUids(query);
    }

    private LdapQueryBuilder baseQuery() {
        return LdapQueryBuilder.query()
                .base("ou=people")
                .searchScope(SearchScope.ONELEVEL)
                .countLimit(100)
                .timeLimit(3000);
    }

    private List<String> listUids(LdapQuery query) {
        return ldapTemplate.search(
                query,
                (ContextMapper<String>) context ->
                        ((DirContextOperations) context)
                                .getStringAttribute("uid")
        );
    }
}
~~~

Với bộ LDIF ở mục 9, bạn kỳ vọng:

| Phương thức | Kết quả (không xét thứ tự) |
| --- | --- |
| `findByUid("lan")` | `["lan"]` |
| `findWithEmail()` | `["lan", "hoa", "an"]` |
| `findWithoutEmail()` | `["minh"]` |
| `findKnownNonContractors()` | `["lan"]` |

Trong ví dụ, `uid` luôn có trên fixture và được tài khoản service phép đọc. Với directory thật, cần xử lý thuộc tính không được trả về, dữ liệu đa giá trị hoặc entry sai quy ước nghiệp vụ. Không dùng một giá trị `null` do mapper đọc được để suy ra ngay thuộc tính đã bị xóa.

### 11.4. Dùng repository khi nào?

Spring Data LDAP repository thích hợp cho các thao tác theo entry/thuộc tính đã ánh xạ (ví dụ tìm người bằng `uid`). Nhưng với bộ lọc tổ hợp có `NOT`, presence, absence và giới hạn scope, `LdapTemplate` cùng `LdapQueryBuilder` cho thấy rõ **ý nghĩa của biểu thức** và phạm vi Search.

Đừng cố dùng phương thức repository lấy mọi entry rồi tự lọc bằng Java cho một directory lớn: cách làm đó chuyển gánh nặng lọc sang ứng dụng, dễ đọc quá nhiều thuộc tính và có thể bỏ qua ACL/giới hạn được áp dụng ở server.

## 12. Escaping filter an toàn theo RFC 4515

Một lỗi thường gặp là ghép trực tiếp giá trị do người dùng nhập vào filter:

~~~java
// KHÔNG sử dụng với dữ liệu đầu vào không tin cậy:
String unsafe = "(uid=" + userInput + ")";
~~~

Nếu `userInput` có ký tự đặc biệt như `*`, `(` hoặc `)`, filter có thể bị đổi cấu trúc hoặc đổi từ equality sang wildcard/presence. Các ký tự phải escape trong **giá trị của filter LDAP** bao gồm:

| Ký tự đầu vào | Biểu diễn escape trong LDAP filter |
| --- | --- |
| Dấu sao `*` | `\2a` |
| Ngoặc mở `(` | `\28` |
| Ngoặc đóng `)` | `\29` |
| Dấu gạch chéo ngược `\` | `\5c` |
| Byte NUL | `\00` |

Ví dụ một `uid` có ký tự sao thật sự cần biểu diễn bằng `(uid=lan\2a)` để so khớp giá trị literal `lan*`; `(uid=lan*)` lại là substring filter. Nếu dùng `EqualsFilter("uid", input)` hay `.where("uid").is(input)`, thư viện sẽ hỗ trợ encoding giá trị an toàn.

### Cẩn thận với thuộc tính, DN và wildcard

- **Giá trị filter**: dùng builder/filter class để escape; không ghép trực tiếp.
- **Tên thuộc tính**: không cho client gửi tùy ý; hãy ánh xạ một tập thuộc tính được phép, ví dụ `uid`, `mail`, `employeeType`.
- **DN**: có quy tắc escaping riêng (RFC 4514), khác escaping filter; nên dùng `LdapNameBuilder` hay API DN.
- **Wildcard**: chỉ chủ động dùng trong điều kiện tìm substring khi nghiệp vụ cần, và kiểm soát phần wildcard do ứng dụng xây dựng.

Lưu ý `.filter(String)` của `LdapQueryBuilder` **không tự escape** chuỗi filter tùy ý. Nếu cần truyền tham số cho một mẫu filter, hãy cân nhắc API `.filter(String, Object...)` hoặc dựng các `Filter` object; tránh để client định nghĩa nguyên biểu thức.

## 13. Ba giá trị logic và giới hạn của kết quả

Một filter có thể trả **TRUE**, **FALSE** hoặc **Undefined**, không hoàn toàn như toán tử Boolean trong Java. LDAP chỉ chọn entry khi filter trả TRUE, còn FALSE/Undefined không được đưa vào kết quả Search.

~~~mermaid
flowchart TD
    A["Đánh giá filter trên một entry"] --> B{"Kết quả"}
    B -->|"TRUE"| C["Entry đủ điều kiện trả về (còn phụ thuộc ACL)"]
    B -->|"FALSE"| D["Không chọn entry"]
    B -->|"Undefined"| D
    E["NOT(TRUE)"] --> F["FALSE"]
    G["NOT(FALSE)"] --> H["TRUE"]
    I["NOT(Undefined)"] --> J["Undefined"]
~~~

Một vài nguyên nhân khiến kết quả Undefined:

- Server không nhận ra loại thuộc tính trong filter.
- Thuộc tính không có matching rule thích hợp cho phép so sánh được yêu cầu.
- Giá trị khẳng định sai cú pháp theo matching rule hoặc server không thực hiện phép lọc.

Vì vậy phép `(!(unknownAttribute=x))` **không bảo đảm** trả mọi entry. Thực hành cần dùng các thuộc tính có trong schema, kiểm tra filter trên LDAP server đang sử dụng và phân biệt “không khớp” với lỗi cấu hình/cú pháp hoặc giới hạn quyền.

## 14. Bảo mật và hiệu năng trong ứng dụng thực tế

Các filter trên thường dùng để tìm hồ sơ người dùng, nhóm, tài khoản dịch vụ và dữ liệu có thể nhạy cảm.

- Kết nối với LDAP server qua **LDAPS** hoặc **StartTLS thành công trước Bind**; xác minh chứng chỉ và hostname.
- Bind bằng tài khoản chỉ có quyền Search và đọc các thuộc tính mà ứng dụng thực sự cần; không mặc định người gọi API có quyền đọc mọi entry.
- Giới hạn **base DN**, **scope**, **size limit** và **time limit**. Filter `(!(attr=value))` hoặc `(!(attr=*))` có thể chọn phạm vi lớn, nhất là khi dùng dưới gốc directory.
- Với các filter dùng wildcard ở đầu chuỗi hoặc NOT, kiểm tra chỉ mục, kế hoạch truy vấn và hiệu năng của server; chi tiết tối ưu phụ thuộc directory.
- Nếu expose chức năng tìm kiếm qua REST API, phải xác thực/phân quyền HTTP riêng, hạn chế tần suất, làm sạch thông tin trả ra và không log mật khẩu/dữ liệu riêng tư.
- Với entry đa giá trị, không biến toàn bộ logic filter thành `Objects.equals()` trên một chuỗi đọc về.
- Đừng suy luận “không có email” từ response bị rút gọn thuộc tính hoặc từ việc thiếu quyền; kiểm tra bằng search filter và đặc tính ACL của server.

## 15. Bài tập thực hành

**Bài 1 — Dự đoán kết quả.** Với bảng ở mục 2, xác định entry của các filter:

~~~ldap
(!(mail=*))
(&(mail=*)(!(uid=hoa)))
(|(employeeType=staff)(employeeType=contractor))
(&(objectClass=inetOrgPerson)(!(employeeType=contractor)))
~~~

Đáp án để tự đối chiếu (không xét thứ tự):

1. `minh`.
2. `lan, an`.
3. `lan, minh, hoa`.
4. `lan, an`.

**Bài 2 — Viết filter phù hợp.** Tạo filter cho các yêu cầu sau:

| Nghiệp vụ | Filter |
| --- | --- |
| Tìm người dùng có `uid=hoa` | `(&(objectClass=inetOrgPerson)(uid=hoa))` |
| Tìm người dùng có email | `(&(objectClass=inetOrgPerson)(mail=*))` |
| Tìm người dùng chưa có email | `(&(objectClass=inetOrgPerson)(!(mail=*)))` |
| Tìm người dùng có `employeeType` nhưng không phải contractor | `(&(objectClass=inetOrgPerson)(employeeType=*)(!(employeeType=contractor)))` |

**Bài 3 — Xác nhận trên directory.** Nạp các entry ở mục 9 vào directory kiểm thử, chạy bốn lệnh `ldapsearch` ở mục 10 và đối chiếu với ma trận mục 8. Thử bỏ `employeeType` trên entry `lan` rồi chạy lại hai filter “khác contractor” để quan sát sự khác biệt. Không thực hiện thí nghiệm trên dữ liệu nhân sự thật.

**Bài 4 — Kiểm thử Spring LDAP.** Viết kiểm thử tích hợp gọi từng phương thức của `PeopleFilterService`, so sánh tập `uid` trả về thay vì dựa vào thứ tự. Bổ sung ca `findByUid("a*)(uid=*)")` và xác minh không làm thay đổi phạm vi Search; thêm ca `findByUid("")` phải bị từ chối từ tầng ứng dụng.

### Ma trận kiểm thử gợi ý

| Trường hợp | Điều cần xác minh |
| --- | --- |
| Equality đúng và sai giá trị | `uid=lan` chỉ ra một entry; `uid=khong-co` không có kết quả. |
| Khác với thuộc tính tồn tại | `(!(employeeType=contractor))` có thể gồm entry thiếu `employeeType`. |
| Khác nhưng bắt buộc thuộc tính tồn tại | `(&(employeeType=*)(!(employeeType=contractor)))` loại entry thiếu thuộc tính. |
| Hiện diện/không hiện diện | `(mail=*)` và `(!(mail=*))` chia fixture thành hai nhóm đúng. |
| Tên thuộc tính sai schema | Không suy ra cứ NOT là sẽ trả tất cả; xử lý Unknown/Undefined đúng. |
| Giá trị có ký tự filter đặc biệt | Query builder escape dữ liệu, không làm mở rộng điều kiện. |
| Service account không có quyền đọc | Kết quả phù hợp chính sách server, không lộ dữ liệu bị hạn chế. |
| Search không giới hạn scope | Cấu hình base/scope để tránh truy vấn vượt nhánh nghiệp vụ. |

## 16. Câu hỏi tự ôn tập

1. Vì sao `(uid=lan)` là equality còn `(uid=lan*)` không phải?
2. LDAP có hỗ trợ trực tiếp `(employeeType!=contractor)` không? Cú pháp đúng là gì?
3. Khi nào `(!(employeeType=contractor))` chọn entry không có `employeeType`?
4. Viết filter yêu cầu “có mail và mail khác lan@example.org”.
5. `(mail=)` và `(!(mail=*))` khác nhau ra sao?
6. Thuộc tính nhiều giá trị ảnh hưởng thế nào đến điều kiện bằng và NOT?
7. Vì sao `NOT Undefined` không thành TRUE?
8. Trong `LdapQueryBuilder`, phương thức nào dùng cho hiện diện và không hiện diện?
9. Vì sao thiếu `mail` trong dữ liệu Java không tự chứng minh entry không có `mail`?
10. Cần áp dụng những giới hạn nào trước khi cho người dùng tìm kiếm thư mục qua REST API?

**Ghi nhớ:** equality dùng `(attr=value)`; “khác” dùng `(!(attr=value))`; hiện diện dùng `(attr=*)`; không hiện diện dùng `(!(attr=*))`. Đặc biệt, nếu nghiệp vụ yêu cầu **“có thuộc tính và giá trị khác X”**, hãy dùng `(&(attr=*)(!(attr=X)))`. Trong Spring Data LDAP, ưu tiên các builder/filter class có escaping chuẩn và luôn kiểm thử với schema/ACL của directory.

### Tài liệu tham khảo

- [RFC 4511 — Lightweight Directory Access Protocol (LDAP): The Protocol](https://www.rfc-editor.org/rfc/rfc4511): SearchRequest, bộ lọc và logic ba giá trị (mục 4.5.1).
- [RFC 4515 — String Representation of Search Filters](https://www.rfc-editor.org/rfc/rfc4515): cú pháp filter, presence, NOT, AND/OR và escaping giá trị.
- [RFC 4512 — LDAP: Directory Information Models](https://www.rfc-editor.org/rfc/rfc4512): entry, schema và matching rule.
- [Spring LDAP — Advanced LDAP Queries](https://docs.spring.io/spring-ldap/reference/query-builder-advanced.html): `is`, `not`, `isPresent` và các toán tử kết hợp.
- [Spring LDAP — Filter API](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/filter/package-summary.html): `EqualsFilter`, `PresentFilter`, `NotPresentFilter`, `NotFilter`, `AndFilter` và `OrFilter`.
