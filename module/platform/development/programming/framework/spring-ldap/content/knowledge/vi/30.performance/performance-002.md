# Chọn base DN và filter có tính chọn lọc trong Spring LDAP

Một câu truy vấn LDAP có thể tìm đúng người dùng nhưng vẫn chậm, vì máy chủ phải xem xét quá nhiều entry trước khi trả kết quả. Hai quyết định tác động trực tiếp đến phạm vi công việc là **đặt base DN ở đâu** và **viết filter chọn lọc đến mức nào**. Với Spring LDAP, chúng được thể hiện rõ trong `LdapQueryBuilder`, `LdapTemplate` và các API truy vấn liên quan; ODM chỉ là một cách nhận dữ liệu sau khi tìm kiếm.

Bài này thuộc chương **Hiệu năng** của **SPRING_LDAP**. Mục tiêu là biết chọn vị trí tìm kiếm trong cây thư mục, giới hạn độ sâu, xây dựng filter an toàn và thân thiện với index, kiểm chứng chúng với dữ liệu thật, và giữ nguyên tính đúng đắn cùng quyền truy cập. Các cấu hình kết nối, TLS, xác thực và pooling vẫn quan trọng với tổng độ trễ, nhưng trọng tâm ở đây là **lượng công việc mà một search buộc directory server phải thực hiện**.

## 1. Mô hình cần nhớ: base DN, scope và filter

Truy vấn LDAP thường có ba phần cốt lõi:

- **Base DN (Distinguished Name)**: entry làm gốc của vùng tìm kiếm, ví dụ `ou=people,dc=example,dc=org`.
- **Search scope**: chỉ tìm trên chính base (`OBJECT`), con trực tiếp (`ONELEVEL`), hay cả base và mọi cấp con (`SUBTREE`).
- **Filter**: điều kiện entry phải thỏa, chẳng hạn `(&(objectClass=inetOrgPerson)(uid=alice))`.

Ngoài ba phần đó, **attributes trả về, giới hạn thời gian, giới hạn số entry và paging** ảnh hưởng đáng kể tới lượng dữ liệu truyền qua mạng và công ánh xạ sang Java.

Hình dung cây thư mục mẫu:

```text
dc=example,dc=org
├── ou=people
│   ├── ou=engineering
│   │   ├── uid=alice
│   │   └── uid=bob
│   └── ou=sales
│       └── uid=carol
├── ou=groups
│   ├── cn=developers
│   └── cn=sales-team
└── ou=system
    └── cn=svc-reader
```

Các nhãn trong hình được viết tắt; DN đầy đủ của Alice là `uid=alice,ou=engineering,ou=people,dc=example,dc=org`. Nếu hệ thống muốn tìm người ở Engineering, base `ou=engineering,ou=people,dc=example,dc=org` hợp lý hơn root `dc=example,dc=org`, miễn là người cần tìm thực sự nằm trong nhánh này.

Một truy vấn có thể được xem như:

```text
Search(base DN, scope, filter, returningAttributes, limits)
           │        │       │               │           │
           └────────┴───────┴───────────────┴───────────┘
       Phạm vi entry -> số ứng viên -> dữ liệu -> tài nguyên
```

**Độ chọn lọc (selectivity)** mô tả mức filter thu hẹp tập ứng viên. Ví dụ, filter chỉ có `(objectClass=person)` có thể khớp phần lớn tài khoản, còn `(uid=alice)` có thể khớp một entry nếu thuộc tính này được sử dụng như định danh duy nhất trong phạm vi đang tìm. Tuy nhiên, **số entry trả về thấp không tự chứng minh truy vấn rẻ**: server vẫn có thể duyệt rất nhiều entry để tìm ra một kết quả.

## 2. Chọn đúng base DN trước khi tối ưu filter

### 2.1. Base DN là ranh giới của search

Với cây ví dụ:

| Base DN | Scope | Entry có thể thuộc phạm vi |
| --- | --- | --- |
| `dc=example,dc=org` | `SUBTREE` | Cả nhánh people, groups và system |
| `ou=people,dc=example,dc=org` | `SUBTREE` | People ở Engineering, Sales và OU con khác |
| `ou=engineering,ou=people,dc=example,dc=org` | `ONELEVEL` | Alice, Bob và các entry con trực tiếp khác |
| `uid=alice,ou=engineering,ou=people,dc=example,dc=org` | `OBJECT` | Chỉ entry Alice, nếu tồn tại |
| `ou=people,dc=example,dc=org` | `ONELEVEL` | Hai OU Engineering, Sales, **không** gồm Alice/Bob/Carol |

Ba phạm vi search chuẩn theo LDAP là:

| Scope | Ý nghĩa chính xác | Tình huống phù hợp |
| --- | --- | --- |
| `OBJECT` (base object) | Chỉ kiểm tra entry tại base DN | Đã biết DN và cần đọc/chọn thuộc tính của một entry |
| `ONELEVEL` | Các entry con ngay dưới base, **không gồm base** | Người dùng được lưu trực tiếp dưới một OU, không có nhánh con cần duyệt |
| `SUBTREE` | Base cùng tất cả entry ở các cấp con | Người dùng nằm trong nhiều OU lồng nhau |

**Lỗi chức năng phổ biến:** cấu hình `ONELEVEL` ở `ou=people` trong khi người dùng thực tế nằm trong `ou=engineering,ou=people`. Query có thể rất nhanh nhưng trả về rỗng; tốc độ đó không chứng minh tối ưu tốt. Hãy đối chiếu cấu trúc DN với dữ liệu thật và yêu cầu nghiệp vụ trước khi rút ngắn scope.

### 2.2. Base rộng và hẹp đều có đánh đổi

**Base rộng** giúp bao phủ dữ liệu phân tán qua nhiều OU và đơn giản hóa logic; nhưng có thể mở rộng phạm vi ứng viên, làm ACL phải xét nhiều hơn và tăng rủi ro quét một nhánh lớn khi filter kém chọn lọc.

**Base hẹp** có thể giảm phạm vi search, rõ ràng hơn về ranh giới dữ liệu và giới hạn ảnh hưởng của truy vấn lỗi; nhưng dễ **bỏ sót** entry nếu tổ chức đang chuyển người dùng sang OU khác hoặc một đối tượng được đặt trong nhiều nhánh.

Các câu hỏi để chọn base:

1. Dữ liệu cần tìm thực sự nằm ở nhánh nào, có OU con hay không?
2. Phạm vi truy vấn là một tổ chức, một phòng ban, một tenant hay toàn directory?
3. Có phải hỗ trợ chuyển OU, nhiều domain hoặc nhiều directory server?
4. Trường hợp không tìm thấy ở base hẹp là hợp lệ hay cần tìm tiếp nhánh khác?
5. Base có được tính từ input người dùng? Nếu có, đã kiểm tra quyền và escape DN đúng cách chưa?

Không nên tăng lên root `dc=example,dc=org` chỉ vì một lần search theo base hẹp trả rỗng. Hãy phân biệt **base sai**, **filter sai**, **ACL không đủ**, **entry không tồn tại** và **sai schema/thuộc tính** trước.

### 2.3. Base trong `LdapContextSource` và base của từng query

Với Spring LDAP, dễ nhầm base cấu hình chung với base truy vấn:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.core.support.LdapContextSource;

@Configuration
class DirectoryConfig {
    @Bean
    LdapContextSource contextSource() {
        LdapContextSource source = new LdapContextSource();
        source.setUrl("ldaps://directory.example.org:636");
        source.setBase("dc=example,dc=org");
        source.setUserDn("cn=svc-reader,ou=system,dc=example,dc=org");
        source.setPassword(System.getenv("LDAP_BIND_PASSWORD"));
        return source;
    }

    @Bean
    LdapTemplate ldapTemplate(LdapContextSource contextSource) {
        return new LdapTemplate(contextSource);
    }
}
```

Khi dùng một `ContextSource` có base là `dc=example,dc=org`, truy vấn Spring LDAP thường chỉ cần base **tương đối** `ou=people` hoặc `ou=engineering,ou=people`. Không tự động nối suffix `dc=example,dc=org` lần thứ hai vào base của truy vấn; nếu lặp DN, kết quả sẽ là một nhánh không hợp lệ/không tồn tại.

Lưu ý: base DN là vị trí trong DIT (*Directory Information Tree*), không phải chuỗi đường dẫn filesystem. Với RDN chứa dấu phẩy, dấu cộng, khoảng trắng đặc biệt hoặc ký tự cần escape, hãy dùng API xử lý DN đúng chuẩn (ví dụ `LdapName` / `LdapNameBuilder`), tránh nối chuỗi từ input chưa kiểm tra.

## 3. Filter có tính chọn lọc: đúng thuộc tính, đúng toán tử, đúng index

LDAP filter được biểu diễn theo cú pháp chuẩn (RFC 4515). Một số dạng thường gặp:

| Filter | Ý nghĩa | Nhận xét hiệu năng |
| --- | --- | --- |
| `(uid=alice)` | `uid` bằng `alice` | Thường hiệu quả nếu `uid` có equality index thích hợp |
| `(&(objectClass=inetOrgPerson)(uid=alice))` | Người dùng cụ thể và đúng lớp entry | Bổ sung điều kiện ngữ nghĩa; hiệu quả phụ thuộc index và server |
| `(mail=alice@example.org)` | Tìm theo email | Tốt nếu index/uniqueness tương ứng được bảo đảm; email có thể thay đổi |
| `(cn=An*)` | Tên bắt đầu bằng `An` | Có thể tận dụng substring index nếu server hỗ trợ/cấu hình |
| `(cn=*an*)` | Tên chứa `an` | Có thể rộng và tốn tài nguyên; đừng giả định được index |
| `(objectClass=*)` | Mọi entry có `objectClass` | Gần như không chọn lọc trong nhiều DIT |
| `(|(uid=alice)(mail=alice@example.org))` | Khớp uid **hoặc** email | Mở rộng tập khớp; tính hiệu quả tùy index của từng nhánh |
| `(!(accountStatus=inactive))` | Không có trạng thái inactive | Hiệu quả phụ thuộc schema; điều kiện phủ định có thể khó thu hẹp ứng viên |

**Đừng nhầm thuộc tính ví dụ với schema phổ quát.** `uid` và `inetOrgPerson` phổ biến trong các directory theo chuẩn LDAP nhưng Active Directory và schema tùy chỉnh có thể dùng các thuộc tính khác, ví dụ `sAMAccountName` hay `userPrincipalName`. `accountStatus` trong bảng chỉ là **thuộc tính minh họa** và không thuộc mọi schema. Trước khi lập filter, xác nhận attribute, matching rule, tính duy nhất và index trên hệ thống mục tiêu.

### 3.1. Equality thường là điểm bắt đầu tốt

Nếu nghiệp vụ biết identifier chính xác, hãy dùng equality thay vì tìm chuỗi con. Ví dụ, để tìm uid:

```text
Nên dùng:     (&(objectClass=inetOrgPerson)(uid=alice))
Tránh dùng:   (&(objectClass=inetOrgPerson)(uid=*ali*))
Rất rộng:     (objectClass=inetOrgPerson)
```

Equality tốt **khi thuộc tính có cơ chế tìm kiếm phù hợp ở server**. Một index có thể giảm số entry ứng viên đáng kể, nhưng không thể khẳng định mức cải thiện cố định nếu chưa biết số lượng entry, phân phối giá trị và cấu hình máy chủ.

### 3.2. Filter AND/OR/NOT và lựa chọn ứng viên

- `(&(uid=alice)(objectClass=inetOrgPerson))` yêu cầu **tất cả** điều kiện đúng. Một ràng buộc chọn lọc có thể giúp giảm ứng viên nếu server dùng index hiệu quả.
- `(|(uid=alice)(uid=bob))` yêu cầu **một trong** hai điều kiện. Trong nhiều trường hợp, server có thể lấy hợp của các tập kết quả index.
- `(!(uid=alice))` là phủ định. Với nhánh lớn, điều kiện này vẫn khớp phần lớn entry và có thể gây duyệt nhiều ứng viên.
- Điều kiện present `(mail=*)` kiểm tra thuộc tính có tồn tại; hữu ích về nghiệp vụ nhưng thường không đủ để giới hạn tìm kiếm danh tính.

Thứ tự các điều kiện trong `AND` **không bảo đảm** thứ tự đánh giá trên server. Sắp xếp lại `(&(objectClass=person)(uid=alice))` thành `(&(uid=alice)(objectClass=person))` thường không phải biện pháp tối ưu đáng tin cậy. Hãy kiểm tra index và thống kê server thay vì dựa vào vị trí điều kiện trong chuỗi.

### 3.3. Wildcard có ý nghĩa đặc biệt

Trong cú pháp LDAP filter, dấu `*` có thể là wildcard của phép substring; `(cn=*)` cũng có nghĩa kiểm tra hiện diện. Nếu người dùng nhập giá trị thật chứa `*`, dấu này phải được escape như dữ liệu, nếu không ý nghĩa filter bị thay đổi. Tương tự, các ký tự `(`, `)`, `\` và byte NUL cần escape trong giá trị filter.

Ví dụ các escape theo RFC 4515:

| Ký tự dữ liệu | Escape trong filter |
| --- | --- |
| `*` | `\2a` |
| `(` | `\28` |
| `)` | `\29` |
| Dấu gạch chéo ngược `\` | `\5c` |
| Byte NUL | `\00` |

Giá trị filter phải được **escape như filter**, còn các thành phần RDN/DN phải được **escape như DN**; hai ngữ cảnh khác nhau. Không thay thế escaping bằng việc xóa ký tự đặc biệt vì có thể làm đổi định danh hợp lệ.

## 4. Xây dựng query an toàn với Spring LDAP

Một lợi thế của `LdapQueryBuilder` là tách base, scope và filter; builder sẽ mã hóa giá trị cho filter thay vì yêu cầu ứng dụng tự ghép dấu ngoặc.

Giả sử cây có nhiều OU con dưới `ou=people` và mỗi person có `uid`, `cn`, `mail`:

```java
import java.util.List;

import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;
import org.springframework.ldap.query.SearchScope;

record PersonSummary(String uid, String name, String email) {}

class PersonDirectory {
    private final LdapTemplate ldapTemplate;

    PersonDirectory(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    List<PersonSummary> findByUid(String uid) {
        if (uid == null || uid.isBlank()) {
            throw new IllegalArgumentException("uid must not be blank");
        }

        LdapQuery query = LdapQueryBuilder.query()
            .base("ou=people")                   // Tương đối với dc=example,dc=org
            .searchScope(SearchScope.SUBTREE)   // Nhiều OU dưới people
            .attributes("uid", "cn", "mail")     // Chỉ lấy dữ liệu cần thiết
            .countLimit(2)                      // Phát hiện nhiều match trong trường hợp đơn giản
            .timeLimit(2000)
            .where("objectClass").is("inetOrgPerson")
            .and("uid").is(uid);                // Value được builder escape

        return ldapTemplate.search(
            query,
            (AttributesMapper<PersonSummary>) attrs -> new PersonSummary(
                text(attrs, "uid"),
                text(attrs, "cn"),
                text(attrs, "mail")
            )
        );
    }

    private static String text(javax.naming.directory.Attributes attrs,
                               String name) throws javax.naming.NamingException {
        javax.naming.directory.Attribute attribute = attrs.get(name);
        return attribute == null ? null : String.valueOf(attribute.get());
    }
}
```

**Vì sao đoạn code này có tính chọn lọc?**

1. `base("ou=people")` loại bỏ khu vực `ou=groups` và `ou=system` khỏi vùng search.
2. `SUBTREE` vẫn tìm được người dùng trong các OU lồng nhau. Nếu tất cả user nằm trực tiếp dưới `ou=people`, có thể chuyển sang `ONELEVEL` sau khi xác nhận dữ liệu.
3. Filter yêu cầu đúng object class và uid cụ thể, thay vì tìm mọi entry có class đó.
4. `attributes` hạn chế lượng dữ liệu truyền đi; không yêu cầu các thuộc tính lớn như ảnh nhị phân nếu không cần.
5. `countLimit(2)` đủ để ứng dụng nhận ra nguy cơ nhiều kết quả khi kỳ vọng tối đa một entry, **nhưng không thay cho ràng buộc uniqueness hoặc kiểm tra kết quả lỗi/truncation**.
6. `timeLimit(2000)` giới hạn thời gian xử lý search; timeout connect/read phải được cấu hình riêng tại tầng kết nối/JNDI.

Trong ứng dụng thật, hãy kiểm tra danh sách trả về: không có entry, một entry và nhiều entry phải có xử lý rõ ràng. Không chọn phần tử đầu tiên một cách tùy tiện cho luồng đăng nhập hoặc phân quyền. Server có thể áp giới hạn size/time riêng, và một truy vấn bị cắt sớm có thể báo lỗi hay không trả đầy đủ; cần xử lý exception/result code theo provider.

### 4.1. Khi nào chọn `ONELEVEL` thay `SUBTREE`?

Nếu triển khai đã cam kết user nằm **trực tiếp** dưới `ou=engineering,ou=people`:

```java
LdapQuery query = LdapQueryBuilder.query()
    .base("ou=engineering,ou=people")
    .searchScope(SearchScope.ONELEVEL)
    .attributes("uid", "cn")
    .countLimit(2)
    .where("uid").is(uid);
```

Đây là tối ưu có cơ sở vì **phạm vi dữ liệu được ràng buộc bởi thiết kế DIT**. Nếu user được chuyển vào `ou=contractors,ou=engineering`, `ONELEVEL` sẽ không còn thấy họ. Cần thay đổi search contract hoặc dùng `SUBTREE`; không coi đó là lỗi do "index kém".

### 4.2. Truy vấn thành viên nhóm là một bài toán khác

Giả sử directory dùng schema `groupOfNames`, có attribute đa giá trị `member` chứa DN thành viên. Việc tìm nhóm của Alice có thể dùng base `ou=groups` và equality trên `member`:

```java
LdapQuery groups = LdapQueryBuilder.query()
    .base("ou=groups")
    .searchScope(SearchScope.SUBTREE)
    .attributes("cn")
    .countLimit(200)
    .where("objectClass").is("groupOfNames")
    .and("member").is(userDn);
```

`userDn` là giá trị DN cần so khớp trong attribute `member`, được coi là **giá trị filter** và được builder escape đúng ngữ cảnh. Với hệ thống khác, schema nhóm có thể dùng `uniqueMember`, `memberOf` hoặc mô hình khác; cần xác nhận attribute, matching rule và index thực tế. `countLimit(200)` chỉ là mức minh họa, có thể làm thiếu nhóm nếu người dùng thuộc nhiều hơn 200 nhóm.

Không có một filter duy nhất tối ưu cho mọi use case: tìm người bằng uid, tìm tài khoản theo email và tìm nhóm theo member là các phân phối dữ liệu rất khác nhau.

## 5. Độ chọn lọc đo bằng gì?

Để phân tích search, phân biệt ba số:

- **Số entry trong phạm vi base/scope**: phần DIT có thể tham gia tìm kiếm.
- **Số ứng viên mà server phải xét**: phụ thuộc index, filter planner, matching rule và implementation.
- **Số entry được trả về**: phụ thuộc điều kiện, quyền xem và limit.

Ví dụ **giả định** (chỉ để minh họa cách suy nghĩ, không phải số đo của một LDAP server cụ thể):

| Kịch bản | Entry thuộc phạm vi | Ứng viên server có thể phải xét | Kết quả trả về |
| --- | ---: | ---: | ---: |
| Search root với filter rộng | 1.000.000 | Rất nhiều, tùy index | 100.000+ |
| Search `ou=people` với `(objectClass=inetOrgPerson)` | 700.000 | Có thể rất nhiều | Hàng trăm nghìn |
| Search trong một OU với `(uid=alice)` được index | 12.000 | Có thể chỉ vài entry | 1 |
| Search root với `(uid=alice)` **không** index | 1.000.000 | Có thể gần cả vùng search | 1 |

Bảng cho thấy một search trả về **một** entry vẫn có thể cực kỳ đắt nếu không có index. Ngược lại, base hẹp giúp giảm phạm vi ngay cả trước khi xét filter nhưng lợi ích thực tế còn tùy chiến lược tìm kiếm của server.

Một chỉ số trực quan có thể dùng khi thiết kế filter là:

```text
Độ chọn lọc theo kết quả = số entry khớp / số entry trong phạm vi

Ví dụ giả định: 1 / 12.000 ≈ 0,0083%
```

Đây chỉ là **tỉ lệ kết quả**, không phải số ứng viên server thực sự duyệt. Muốn biết server tận dụng index ra sao, cần công cụ thống kê/giám sát hoặc khả năng explain truy vấn của sản phẩm directory cụ thể.

### 5.1. Index là việc của directory server

Spring LDAP không tạo index trên LDAP server bằng cách thêm `.where("uid").is(...)`. Nó gửi filter; việc dùng index do directory server quyết định.

Tùy sản phẩm, index có thể phân biệt:

- **Equality index**: phục vụ điều kiện `(uid=alice)`.
- **Presence index**: phục vụ `(mail=*)`.
- **Substring index**: có thể hỗ trợ một số tìm kiếm `(cn=An*)` hoặc `(cn=*an*)`.
- **Matching rule chuyên biệt**: server có thể áp quy tắc không phân biệt hoa/thường, chuẩn hóa DN, hoặc index đặc thù theo schema.

Không phải server nào cũng hỗ trợ/thiết lập các kiểu index giống nhau. Chẳng hạn, quản trị OpenLDAP thường phải xem cấu hình index của backend, còn Active Directory có cơ chế schema/index và công cụ giám sát riêng. Ứng dụng cần phối hợp với nhóm quản trị thư mục, không tự kết luận một thuộc tính "chắc chắn có index" vì nó mang tên `uid` hoặc `mail`.

Ngay cả khi có index, filter quá rộng vẫn có thể trả nhiều entry và truyền nhiều dữ liệu. **Index tối ưu tìm ứng viên; base, filter và attributes cùng nhau quyết định lượng việc cuối cùng.**

## 6. Những mẫu filter dễ gây chậm và cách sửa

### Trường hợp A: Gõ vài ký tự để tìm người

**Không nên dùng cho mỗi lần gõ**:

```ldap
(&(objectClass=inetOrgPerson)(cn=*a*))
```

Một ký tự quá phổ biến có thể khớp lượng lớn người dùng và tốn tài nguyên khi có nhiều request liên tiếp. Giải pháp thường là đặt **độ dài nhập tối thiểu**, debounce ở giao diện, giới hạn số kết quả, dùng prefix search nếu yêu cầu sản phẩm cho phép, hoặc dùng hệ thống tìm kiếm chuyên biệt cho chức năng gợi ý/substring trên directory rất lớn. Cần xác nhận server hỗ trợ index substring trước khi triển khai tính năng ở quy mô lớn.

**Tùy yêu cầu**, có thể chọn:

```ldap
(&(objectClass=inetOrgPerson)(cn=Nguyen*))
```

Nhưng prefix search vẫn có thể khớp rất nhiều entry, và wildcard phải đến từ logic ứng dụng có chủ đích. Không biến input người dùng chứa `*` thành wildcard tự do.

### Trường hợp B: Kiểm tra một tài khoản bằng filter chung chung

**Không nên** tải toàn bộ người dùng rồi lọc bằng Java:

```java
// Sai hướng khi DIT lớn: lấy nhiều entry rồi lọc phía ứng dụng.
// ldapTemplate.search(..., "(objectClass=inetOrgPerson)", ...);
// users.stream().filter(u -> u.uid().equals(uid))...
```

Hãy chuyển điều kiện exact match vào filter LDAP trên server:

```ldap
(&(objectClass=inetOrgPerson)(uid=alice))
```

Tập dữ liệu truyền sang ứng dụng nhỏ hơn; nếu uid được index, server có thêm cơ hội tìm nhanh. So khớp phải dựa trên matching rule LDAP phù hợp, không thay thế bằng so sánh chuỗi Java tùy ý.

### Trường hợp C: Filter OR quá rộng

Ví dụ:

```ldap
(|(uid=alice)(mail=alice@example.org)(cn=*alice*))
```

Nếu nhánh `cn=*alice*` rất rộng hoặc kém index, chi phí cả OR có thể tăng dù hai nhánh còn lại chọn lọc. Nếu giao diện có các chế độ "đăng nhập bằng uid", "tìm email" và "tìm tên gần đúng", hãy tạo **query riêng** theo từng mục đích, thay vì một OR kết hợp tất cả vào mọi request.

### Trường hợp D: Tìm theo nhánh tenant

Cấu trúc có thể là:

```text
ou=tenants,dc=example,dc=org
├── ou=tenant-a
│   └── ou=people
└── ou=tenant-b
    └── ou=people
```

Với request của tenant A, base `ou=people,ou=tenant-a,ou=tenants` (tương đối với context base) có thể rõ ràng hơn search toàn bộ `ou=tenants` rồi lọc `tenantId=tenant-a`, **nếu DIT và quyền truy cập thực tế được tổ chức như trên**. Tuy nhiên, base do user chọn cần được map từ tenant đã xác thực và kiểm tra quyền; **thu hẹp base không thay thế ACL phía server hoặc kiểm tra authorization phía ứng dụng**.

## 7. Giới hạn dữ liệu trả về để giữ search ổn định

Filter chọn lọc là bước đầu. Một request vẫn có thể chậm nếu lấy tất cả attribute của mỗi entry:

- **Returning attributes**: dùng `attributes("uid", "cn", "mail")` cho danh sách người dùng; không lấy `jpegPhoto`, certificate, các nhóm đa giá trị hoặc blob nếu không cần.
- **Count limit**: giới hạn số entry trả về khi use case chỉ cần tối đa vài kết quả; phải nhận biết lỗi/truncation và tránh xử lý kết quả thiếu như đầy đủ.
- **Time limit**: giới hạn thời gian search ở tầng directory; phối hợp với `connect.timeout`/`read.timeout` của JNDI và deadline request.
- **Phân trang**: với danh sách lớn, cân nhắc LDAP Simple Paged Results (RFC 2696) nếu server hỗ trợ; quản lý cookie qua các trang và xử lý server size limit.
- **Không gọi search lặp kiểu N+1**: ví dụ tìm 200 người rồi search group từng người có thể sinh 201 query. Cân nhắc lấy dữ liệu cần thiết trong search chính hoặc tổ chức batch có giới hạn theo schema và yêu cầu bảo mật.

Ví dụ một màn hình quản trị hiển thị danh sách đầu tiên: filter theo thuộc tính nghiệp vụ thực sự chọn lọc, giới hạn số kết quả và chỉ trả vài cột. Đừng dùng `countLimit(20)` như cơ chế "phân trang": nó chỉ cắt kết quả, không cung cấp trạng thái trang tiếp theo.

### Chú ý về sorting và paging

LDAP server-side sorting và paging có thể hỗ trợ danh sách lớn nhưng cũng có chi phí tài nguyên; khả năng hỗ trợ khác nhau giữa các sản phẩm. Kết quả paging có thể không ổn định khi dữ liệu thay đổi giữa các trang, và không phải mọi trường hợp server trả về đều có thứ tự bảo đảm. Nếu ứng dụng cần thứ tự, hãy yêu cầu/cấu hình sắp xếp rõ ràng ở tầng hỗ trợ nó.

## 8. Đo tác động của base DN và filter

Tối ưu cần vừa nhanh vừa đúng. Một quy trình kiểm chứng gọn:

1. **Cố định nghiệp vụ**: ví dụ "tìm đúng một entry theo uid dù người dùng ở OU con", hoặc "tìm mọi group của một user".
2. **Ghi cấu hình query**: base, scope, filter template (không ghi giá trị nhạy cảm), attribute list, size/time limit, server/version và index có liên quan.
3. **Chọn bộ dữ liệu đại diện**: uid có tồn tại, không tồn tại, xuất hiện nhiều lần, người dùng thuộc OU sâu, tên phổ biến, nhóm có nhiều thành viên.
4. **Chạy warm-up rồi đo**: cùng workload, cùng số concurrent requests và cùng trạng thái pool/kết nối, đo p50/p95/p99, throughput, lỗi, kết quả và số byte phản hồi.
5. **Đối chiếu server metrics**: tìm thông số số ứng viên duyệt, số entry trả về, index hit/miss, search time, CPU/I/O nếu sản phẩm có cung cấp.
6. **Thay một yếu tố mỗi lần**: trước tiên base/scope, sau đó filter và index, cuối cùng attributes/limits; giữ nguyên kết quả mong đợi.
7. **Test regression đúng dữ liệu**: xác nhận query mới không bỏ sót OU con, không trả nhầm tenant, không che mất lỗi size limit/time limit và không thay đổi chính sách quyền.

Có thể tạo một bảng kết quả nội bộ như sau (con số **giả định**, chỉ minh họa cách báo cáo):

| Biến thể | Base + scope | Filter | p95 | Kết quả chức năng |
| --- | --- | --- | ---: | --- |
| A | Root + `SUBTREE` | `(cn=*an*)` | 420 ms | Quá rộng |
| B | `ou=people` + `SUBTREE` | `(cn=*an*)` | 260 ms | Đủ người, vẫn rộng |
| C | `ou=people` + `SUBTREE` | `(uid=alice)` | 28 ms | Đúng yêu cầu tra cứu uid |
| D | `ou=engineering,ou=people` + `ONELEVEL` | `(uid=alice)` | 20 ms | Đúng **chỉ** khi Alice nằm trực tiếp trong OU |

Không so sánh C và D với A như một chiến thắng đơn thuần nếu mục tiêu nghiệp vụ khác nhau: truy vấn exact match, substring và scope hẹp không trả cùng tập kết quả. Trên directory thực tế, một equality index tốt có thể làm khác biệt base DN nhỏ; chỉ đo trên hệ thống mục tiêu mới xác nhận được.

### Phân biệt chi phí client với server

Một stopwatch bọc `ldapTemplate.search(...)` đo cả chờ pool/kết nối, mạng, bind nếu phát sinh, xử lý search và mapping. Để chứng minh base/filter là nguyên nhân, cần kết hợp metric phía client với thông tin xử lý query/index phía server. Có thể quan sát:

| Dấu hiệu | Khả năng cần kiểm tra |
| --- | --- |
| Một filter chính xác trả 1 entry nhưng server search time cao | Thuộc tính thiếu equality index, planner/matching rule hoặc DIT lớn |
| Scope `SUBTREE` ở root chậm, xuống OU nhanh | Phạm vi tìm kiếm rộng hoặc giới hạn/cấu trúc DIT |
| Server trả nhanh nhưng client p95 cao | Mạng, pool wait, bind, TLS hoặc mapping |
| `ONELEVEL` nhanh nhưng trả thiếu người | Entry thực sự nằm trong OU con |
| Filter OR chậm hẳn sau khi thêm `(cn=*...*)` | Nhánh substring quá rộng hoặc index chưa phù hợp |
| Mọi truy vấn đều chậm và lỗi timeout tăng | Sức tải server, giới hạn kết nối hoặc sự cố hạ tầng |

Đặc biệt, **đường tìm không có kết quả** cũng cần đo: không tìm thấy một uid trong cột không index có thể còn tốn kém hơn tìm thấy sớm.

## 9. Tình huống thực hành: tối ưu tra cứu theo uid

Một dịch vụ Spring LDAP phải trả về `uid`, `cn` và `mail` cho người dùng, biết rằng:

- Directory có khoảng một triệu entry (giả định), nhiều OU dưới `ou=people`.
- Đăng nhập nhận uid từ input, nhưng chưa biết user thuộc OU nào.
- Directory server có equality index trên `uid`, còn thuộc tính `cn` có nhiều giá trị trùng.
- Kết quả phải đúng khi user được chuyển từ Engineering sang Sales.

**Thiết kế ban đầu**:

```text
Base:   dc=example,dc=org
Scope:  SUBTREE
Filter: (cn=*<du-lieu-nguoi-dung>*)
Attrs:  all
Limit:  none
```

Nhược điểm: filter không bám uid, tìm substring trên cây rộng, lấy thuộc tính không cần thiết, dễ nhận nhiều entry. Nếu ghép input trực tiếp vào chuỗi filter, còn có nguy cơ LDAP injection.

**Thiết kế đề xuất** (với `ContextSource` đặt base `dc=example,dc=org`):

```text
Query base: ou=people
Scope:      SUBTREE
Filter:     (&(objectClass=inetOrgPerson)(uid=<uid-escaped>))
Attributes: uid, cn, mail
Size limit: 2 (phát hiện trường hợp trùng; xử lý lỗi giới hạn)
Time limit: xác định theo SLA/SLO và khả năng server
```

Vẫn giữ `SUBTREE` vì người dùng có thể đổi OU. Khi ứng dụng thật sự biết OU theo quy tắc được xác thực và đáng tin cậy, có thể cân nhắc base sâu hơn. Cần kiểm chứng search kết quả 0/1/>1, cách xử lý LDAP server limit, quyền truy cập và xác thực tài khoản. Filter tìm entry **không thay cho user bind để kiểm tra mật khẩu** khi use case là đăng nhập.

### Nhiệm vụ cho người học

1. Với sơ đồ DIT đầu bài, cho biết từng scope `OBJECT`, `ONELEVEL`, `SUBTREE` sẽ thấy entry nào khi base là `ou=people`.
2. Viết `LdapQuery` tìm user theo uid trong mọi OU dưới `ou=people`, chỉ lấy `uid` và `mail`.
3. Viết filter để tìm nhóm thuộc `groupOfNames` chứa một DN `member` nhất định; nêu schema/index cần kiểm tra.
4. Giải thích vì sao `(uid=alice)` có thể trả đúng một entry nhưng vẫn chậm nếu server thiếu index.
5. Xây bộ đo trước/sau với ít nhất hai loại dữ liệu có/không tồn tại, một OU lồng nhau và trường hợp tìm kiếm trả nhiều kết quả.
6. Kiểm tra input `a*(b)\` được mã hóa đúng qua builder; chứng minh người dùng không thể sửa cấu trúc filter bằng giá trị nhập.

**Gợi ý đáp án:** câu 1, `ONELEVEL` ở `ou=people` chỉ thấy OU Engineering và Sales, còn `SUBTREE` thấy cả OU và user con; câu 2, dùng `base("ou=people")`, `SearchScope.SUBTREE`, `attributes("uid", "mail")` và `where("uid").is(uid)`; câu 3, dùng equality trên `member` cùng điều kiện `objectClass=groupOfNames` ở nhánh nhóm. Khi đo, phải so sánh truy vấn có cùng mục đích nghiệp vụ và cùng tập kết quả kỳ vọng.

## 10. Checklist áp dụng

- [ ] Đã vẽ đúng DIT, phân biệt base trong `ContextSource` và base tương đối của query.
- [ ] Chọn scope hẹp nhất **vẫn trả đủ** entry đúng trong mọi OU hợp lệ.
- [ ] Dùng định danh exact match và thuộc tính/schema có ý nghĩa nghiệp vụ.
- [ ] Kiểm tra index thực tế trên directory server, không đoán theo tên thuộc tính.
- [ ] Không trộn substring rộng với lookup định danh chính xác một cách vô cớ.
- [ ] Dùng `LdapQueryBuilder` / các lớp filter Spring LDAP để escape giá trị; DN được xây theo quy tắc escape DN.
- [ ] Giới hạn attributes và chọn count/time limit theo use case; kiểm tra kết quả bị cắt.
- [ ] Không dùng base/filter như cơ chế phân quyền thay ACL và authorization.
- [ ] Đo cả kết quả có/không có, p95/p99, thời gian server, số ứng viên và số entry trả về.
- [ ] Có bài kiểm thử tính đúng sau khi đổi base, scope, filter hoặc index.

## Tham khảo kỹ thuật

- [RFC 4511 – Lightweight Directory Access Protocol (LDAP): The Protocol](https://www.rfc-editor.org/rfc/rfc4511): search request, base object, search scope, filter và search result.
- [RFC 4515 – String Representation of Search Filters](https://www.rfc-editor.org/rfc/rfc4515): cú pháp và escaping giá trị filter.
- [RFC 2696 – LDAP Control Extension for Simple Paged Results Manipulation](https://www.rfc-editor.org/rfc/rfc2696): phân trang kết quả search.
- [Spring LDAP – Building Advanced LDAP Queries](https://docs.spring.io/spring-ldap/reference/query-builder-advanced.html): `LdapQueryBuilder`, base/scope/attributes và các điều kiện filter.
- [Spring LDAP – LdapTemplate](https://docs.spring.io/spring-ldap/reference/spring-ldap-basic-usage.html): thao tác truy vấn LDAP qua Spring.

