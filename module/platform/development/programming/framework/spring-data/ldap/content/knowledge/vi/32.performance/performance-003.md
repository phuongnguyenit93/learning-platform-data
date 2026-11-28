# Chọn bộ lọc phù hợp với chỉ mục của máy chủ

Trong **Spring Data LDAP**, ứng dụng Java thường đọc entry theo `uid`, email, tên hoặc thành viên nhóm bằng `LdapRepository` và `LdapTemplate`. Một truy vấn LDAP có thể đúng cú pháp, trả về dữ liệu chính xác nhưng vẫn chậm khi máy chủ phải duyệt rất nhiều entry. Nguyên nhân phổ biến là **điều kiện trong search filter không phù hợp với các chỉ mục mà directory server duy trì**, hoặc phạm vi tìm kiếm quá rộng.

Tối ưu filter vì vậy phải dựa trên **schema, loại so khớp, cấu hình index và dữ liệu thực tế ở máy chủ LDAP**. Spring Data LDAP giúp xây truy vấn và ánh xạ entry thành đối tượng Java, nhưng **không tự tạo chỉ mục cho directory** như một số cơ chế ORM trên cơ sở dữ liệu quan hệ.

Sau bài học, bạn có thể:

- Phân biệt **search base**, **search scope**, **filter** và **server-side index**.
- Ghép đúng **equality**, **presence**, **substring**, các phép so sánh thứ tự và biểu thức AND/OR với khả năng lập chỉ mục tương ứng.
- Hiểu độ chọn lọc (*selectivity*), chi phí của wildcard, NOT và điều kiện ít chọn lọc.
- Viết truy vấn an toàn bằng `LdapQueryBuilder`, kể cả khi nhận giá trị tìm kiếm từ người dùng.
- Kiểm chứng việc sử dụng index và hiệu năng trên directory thật trước khi kết luận một filter “nhanh”.

## 1. Vì sao cùng một LDAP filter có thể nhanh ở server này, chậm ở server khác?

Xét một cây thông tin thư mục (**DIT**) đơn giản:

```text
dc=example,dc=org
├── ou=people
│   ├── uid=lan
│   ├── uid=minh
│   ├── uid=mai
│   └── ... hàng trăm nghìn entry người dùng
├── ou=groups
│   ├── cn=backend
│   └── cn=qa
└── ou=services
    └── uid=inventory-app
```

Giả sử ứng dụng cần tìm người dùng Lan bằng:

```ldap
(&(objectClass=inetOrgPerson)(uid=lan))
```

Một LDAP SearchRequest còn có **base** và **scope**, ví dụ:

```text
base   = ou=people,dc=example,dc=org
scope  = SUBTREE
filter = (&(objectClass=inetOrgPerson)(uid=lan))
```

Máy chủ có thể dùng **equality index của `uid`** để thu hẹp nhanh tập entry ứng viên. Nhưng nếu `uid` chưa được index, server có thể phải kiểm tra rất nhiều entry trong phạm vi search. Cùng filter và dữ liệu, hai directory server có thể chọn kế hoạch xử lý khác nhau do **backend lưu trữ**, **chỉ mục được cấu hình**, **bộ tối ưu truy vấn** và **thống kê dữ liệu** khác nhau.

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **DN** | Tên và vị trí của một entry | `uid=lan,ou=people,dc=example,dc=org` |
| **Search base** | DN gốc của vùng được tìm | `ou=people,dc=example,dc=org` |
| **Search scope** | Kiểm tra chính base, con trực tiếp hoặc toàn subtree | `BASE`, `ONELEVEL`, `SUBTREE` |
| **Filter** | Điều kiện entry cần thỏa | `(uid=lan)` |
| **Index** | Cấu trúc do server duy trì để hỗ trợ tra cứu một thuộc tính/kiểu so khớp | Equality index trên `uid` |
| **Schema/matching rule** | Quy định giá trị thuộc tính được so khớp ra sao | Quy tắc so sánh `uid`, `cn`, số, thời gian |

**Điểm cốt lõi:** một filter “dùng được index” chỉ có ý nghĩa khi máy chủ **thực sự có index phù hợp và chọn sử dụng nó**. Không nên suy luận hiệu năng chỉ từ cách nhìn chuỗi filter.

## 2. Index LDAP ánh xạ theo thuộc tính và kiểu so khớp

LDAP filter không chỉ chứa tên thuộc tính, mà còn chứa **phép so khớp**. Với OpenLDAP, các tên index thông dụng gồm `eq` (equality), `pres` (presence), `sub` (substring) và `approx` (gần đúng). Đây là **tên cấu hình của OpenLDAP**; các directory server khác có tên, khả năng và cơ chế tối ưu riêng.

| Filter | Loại so khớp | Index liên quan (ví dụ OpenLDAP) | Điều cần biết |
| --- | --- | --- | --- |
| `(uid=lan)` | Equality | `uid eq` | Phù hợp truy vấn ID chính xác, thường có độ chọn lọc cao |
| `(mail=lan@example.org)` | Equality | `mail eq` | Phù hợp nếu thường tìm theo email và server có index |
| `(mail=*)` | Presence | `mail pres` | Tìm entry có `mail`; có thể khớp phần lớn directory |
| `(cn=Lan*)` | Substring, tiền tố | `cn sub` hoặc `subinitial` | Hiệu quả tùy index substring và cách phân tích tiền tố |
| `(cn=*Lan*)` | Substring, chứa | `cn sub` hoặc `subany` | Có thể nhiều ứng viên; index không bảo đảm truy vấn rẻ |
| `(cn=*Lan)` | Substring, hậu tố | `cn sub` hoặc `subfinal` | Phụ thuộc loại substring index server hỗ trợ |
| `(cn~=Lan)` | Approximate | `cn approx` nếu hỗ trợ | Thuật toán gần đúng không chuẩn hóa thành một cách duy nhất cho mọi server |
| `(employeeNumber>=1000)` | Ordering | Phụ thuộc ordering rule/backend | Không mặc định được hỗ trợ bởi `eq` |
| `(employeeNumber<=2000)` | Ordering | Phụ thuộc ordering rule/backend | Không mặc định là so sánh số nếu schema mô tả chuỗi |
| `(!(mail=*))` | NOT + Presence | Không có “index NOT” phổ quát | Có thể phải xét tập lớn; cần đo thực tế |

Đây là **quan hệ khả năng**, không phải quy tắc “có index là truy vấn chắc chắn dùng index”. Ví dụ, OpenLDAP có thể khai báo `cn sub` nhưng một mẫu chứa quá phổ biến vẫn trả rất nhiều entry. Mặt khác, server khác có thể tối ưu một phép so khớp bằng cơ chế riêng mà không có cấu hình `eq/pres/sub` giống OpenLDAP.

### 2.1. Matching rule là điều kiện nền tảng

Schema định nghĩa các **matching rule** áp dụng cho thuộc tính. Ví dụ, equality trên `cn` có thể dùng quy tắc bỏ qua khác biệt chữ hoa/chữ thường, trong khi thuộc tính dạng số dùng quy tắc khác. Index được xây trên cách server **chuẩn hóa giá trị theo matching rule**, không nhất thiết dựa vào phép so sánh chuỗi Java.

Không nên giả định:

- `(uid=LAN)` tương đương hay khác `(uid=lan)` giống hệt `"LAN".equals("lan")`.
- `(employeeNumber>=100)` luôn so sánh như số nguyên Java.
- Mọi thuộc tính cho phép equality đều hỗ trợ substring hoặc approximate.
- Chỉ cần khai báo `sub` trên một attribute là mọi dạng tìm văn bản đều tối ưu như một full-text search engine.

Trước khi chọn index hay filter, cần đọc schema của attribute và khả năng matching rule của directory thật.

## 3. Ưu tiên equality cho khóa tra cứu chính xác

### 3.1. Từ yêu cầu nghiệp vụ đến filter

Khi nghiệp vụ đã có `uid` chính xác, sử dụng **equality**:

```ldap
(uid=lan)
```

Nếu chỉ quan tâm loại người dùng `inetOrgPerson`, thêm điều kiện `objectClass`:

```ldap
(&(objectClass=inetOrgPerson)(uid=lan))
```

Giả sử server có index equality trên `uid` và `objectClass`, truy vấn này có thể thu hẹp ứng viên hiệu quả. Thường `uid=lan` chọn lọc hơn `objectClass=inetOrgPerson` trong nhánh chứa nhiều người dùng. Bộ tối ưu có thể dùng một hoặc nhiều index rồi kiểm tra điều kiện còn lại; **thứ tự viết các điều kiện trong AND không phải lệnh buộc server dùng index theo thứ tự đó**.

Một cặp filter dễ thấy khác biệt:

```ldap
# Biết chính xác uid: dùng equality
(uid=lan)

# Tìm mọi uid bắt đầu bằng lan: dùng substring
(uid=lan*)
```

Hai filter **không tương đương**. Nếu ứng dụng đã có `uid` chính xác mà vẫn dùng `(uid=lan*)`, tập kết quả có thể chứa cả `lan01`, `lan.test` và nhiều entry khác, đồng thời có thể bỏ lỡ lợi ích equality index.

### 3.2. Độ chọn lọc quan trọng hơn số điều kiện

**Selectivity** là mức độ một điều kiện giảm số entry ứng viên. Nếu thư mục có 500.000 người dùng, điều kiện `(objectClass=inetOrgPerson)` có thể khớp gần hết; `(uid=lan)` chỉ khớp vài entry hoặc một entry theo chính sách hệ thống.

Minh họa **giả định**, không phải số liệu benchmark:

| Điều kiện | Entry khớp trên 500.000 | Độ chọn lọc |
| --- | ---: | --- |
| `(objectClass=inetOrgPerson)` | 485.000 | Thấp |
| `(mail=*)` | 470.000 | Thấp |
| `(ou=Engineering)` | 25.000 | Trung bình, nếu attribute được lưu trên entry |
| `(uid=lan)` | 1 | Rất cao |

Lưu ý `ou=Engineering` trong ví dụ là **giá trị thuộc tính** của một entry; nó không đồng nghĩa entry nằm dưới container `ou=Engineering` trong DIT. Khi ứng dụng muốn giới hạn **vị trí trong cây**, chọn search base/scope phù hợp.

## 4. Substring filter: khi nào cần, khi nào quá đắt?

LDAP substring filter dùng dấu `*` ở vị trí đặc biệt:

```ldap
(cn=Nguyen*)       # Giá trị cn bắt đầu bằng Nguyen
(cn=*Nguyen)       # Giá trị cn kết thúc bằng Nguyen
(cn=*Nguyen*)      # Giá trị cn chứa Nguyen
(cn=Ngu*Van*An)    # Nhiều thành phần theo thứ tự
```

Trong OpenLDAP, các lựa chọn index có thể bao gồm `subinitial`, `subany`, `subfinal` hoặc `sub`. Với server và cấu hình hỗ trợ, prefix như `(cn=Nguyen*)` có thể thuận lợi hơn tìm chuỗi nằm ở vị trí bất kỳ `(cn=*Nguyen*)`.

Tuy nhiên, **không thể tuyên bố prefix luôn nhanh hơn contains trên mọi directory**. Index có hay không, độ dài tiền tố, quy tắc phân mảnh substring, phân phối tên và tối ưu của backend đều ảnh hưởng. Một prefix quá ngắn như `(cn=N*)` có thể trả về tập rất lớn.

### 4.1. Tìm “chứa từ khóa” không miễn phí

Nếu sản phẩm yêu cầu người dùng gõ bất kỳ đoạn nào trong tên, `(cn=*an*)` có thể có rất nhiều ứng viên. Nên xem xét:

- Có thể làm rõ yêu cầu thành **tìm theo tiền tố** hoặc **tìm chính xác mã định danh** không?
- Có thể giới hạn search base vào một OU hoặc một nhóm dữ liệu đủ nhỏ không?
- Server có substring index phù hợp và thống kê chứng minh nó được dùng không?
- Có nên yêu cầu độ dài tối thiểu của từ khóa và giới hạn số kết quả không?
- Nếu yêu cầu là fuzzy/full-text search phức tạp, LDAP search có còn là công cụ phù hợp hay cần một hệ thống tìm kiếm chuyên dụng?

Giới hạn số kết quả giúp giảm khối lượng dữ liệu trả về và chi phí ánh xạ Java, nhưng **không tự bảo đảm máy chủ không cần quét nhiều entry để tìm chúng**.

### 4.2. Presence filter có thể ít giá trị chọn lọc

```ldap
(mail=*)
```

Presence filter chỉ kiểm tra thuộc tính `mail` có tồn tại. Trong directory mà gần như mọi người dùng đều có email, điều kiện này vẫn khớp gần như toàn bộ nhánh `ou=people`. OpenLDAP khuyến nghị **chỉ thêm presence index khi thuộc tính đủ hiếm và truy vấn presence thực sự phổ biến**, vì index quá ít chọn lọc có thể không đáng chi phí lưu trữ và cập nhật.

Đừng xem `(objectClass=*)` hoặc `(mail=*)` là “filter vô hại” trong một subtree khổng lồ. Chúng có ý nghĩa đúng về dữ liệu nhưng không nhất thiết giúp tối ưu.

## 5. AND, OR và NOT: kết hợp nhiều điều kiện có index

### 5.1. AND: dùng điều kiện chọn lọc cao

```ldap
(&(objectClass=inetOrgPerson)(uid=lan)(mail=*))
```

Đây là AND gồm ba điều kiện. Nếu `uid=lan` rất chọn lọc và được index, máy chủ có thể dùng nó để giảm ứng viên rồi xác minh hai điều kiện khác. Viết thêm `mail=*` chỉ có ích về **ngữ nghĩa nghiệp vụ** nếu yêu cầu phải có email; nó không mặc nhiên làm truy vấn nhanh hơn.

Với server cụ thể, optimizer có thể lấy giao của những tập ứng viên từ nhiều index hoặc chọn một chỉ mục hiệu quả nhất. **Thứ tự các mệnh đề trong chuỗi LDAP không phải hint tối ưu truy vấn có tính di động**. Cần đo trên server thực tế.

### 5.2. OR: mỗi nhánh đều cần được xem xét

```ldap
(|(uid=lan)(uid=mai))
```

Nếu cả hai nhánh là equality trên `uid` đã được index, server có thể kết hợp kết quả hiệu quả. Nhưng:

```ldap
(|(uid=lan)(cn=*an*))
```

Nhánh `cn=*an*` có thể trả rất nhiều ứng viên, làm tổng truy vấn tốn tài nguyên dù nhánh `uid=lan` rất chọn lọc. Một OR có một nhánh không được index có thể buộc server thực hiện kế hoạch đắt hơn; hành vi cụ thể phụ thuộc backend.

Khi nghiệp vụ thực chất là “ưu tiên tra cứu ID, nếu không có mới tìm tên”, **hai truy vấn có điều kiện** đôi khi dễ kiểm soát hơn một OR quá rộng; nhưng phải xét đúng yêu cầu sản phẩm, tính nhất quán và số lượt mạng. Không tự tách OR nếu ứng dụng thực sự cần hợp kết quả của cả hai nhánh.

### 5.3. NOT và điều kiện không xác định

```ldap
(!(mail=*))
```

Đây là filter tìm entry **không có thuộc tính `mail`**. Nếu phần lớn entry đều có `mail`, kết quả ít nhưng máy chủ có thể phải đánh giá vùng dữ liệu rộng vì phép phủ định không phải kiểu index chọn lọc thuận tiện ở mọi backend.

LDAP có ngữ nghĩa filter ba giá trị: **TRUE, FALSE, Undefined**. Với một số matching rule hoặc thuộc tính không được hỗ trợ, `(!(attr=value))` không thể tùy tiện hiểu là “mọi entry không bằng value”. Nếu mục tiêu là thuộc tính không tồn tại, biểu diễn trực tiếp `(!(attr=*))` và kiểm tra server.

Không nên cố “tối ưu” bằng cách biến đổi filter làm thay đổi ngữ nghĩa; trước hết xác định chính xác tập kết quả cần trả về.

## 6. Search base và scope: thu hẹp vùng dữ liệu trước khi lọc

Giả sử cùng một `uid=lan` có thể tồn tại ở `ou=people` và `ou=contractors`:

```text
dc=example,dc=org
├── ou=people
│   ├── uid=lan
│   └── uid=minh
└── ou=contractors
    └── uid=lan
```

Tìm từ `dc=example,dc=org` với `SUBTREE` có thể phải xét nhiều nhánh và trả về **hai entry**; tìm từ `ou=people` theo scope phù hợp chỉ xét nhánh người dùng nội bộ.

| Search scope | Vùng được xét với base `ou=people` |
| --- | --- |
| `OBJECT`/`BASE` | Chỉ chính entry `ou=people` |
| `ONELEVEL` | Các entry con trực tiếp, chẳng hạn `uid=lan`, `uid=minh` |
| `SUBTREE` | Base cùng toàn bộ hậu duệ ở mọi cấp dưới base |

Thu hẹp base/scope có thể giảm số entry server cần xem xét và giảm rủi ro truy xuất nhầm dữ liệu. Nhưng việc chọn base phải dựa trên **vị trí nghiệp vụ thực sự**: dùng `ONELEVEL` sẽ bỏ sót những người dùng nằm sâu dưới OU con nếu hệ thống cho phép cấu trúc đó.

**Không biến search base thành một giá trị người dùng có thể tự do nhập**. Nó ảnh hưởng phạm vi dữ liệu và quyền truy vấn, khác với việc escape giá trị filter. Ứng dụng nên xác định base/scope theo quy tắc được cho phép.

## 7. Viết filter bằng Spring LDAP mà vẫn dùng được index

### 7.1. Equality filter an toàn với `LdapQueryBuilder`

Một dịch vụ tìm tên hiển thị theo `uid`:

```java
import java.util.List;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;
import org.springframework.ldap.query.SearchScope;

public class PersonDirectorySearch {
    private final LdapTemplate ldapTemplate;

    public PersonDirectorySearch(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<String> findNamesByUid(String uid) {
        LdapQuery query = LdapQueryBuilder.query()
                .base("ou=people")
                .searchScope(SearchScope.SUBTREE)
                .attributes("cn")
                .countLimit(100)
                .where("objectClass").is("inetOrgPerson")
                .and("uid").is(uid);

        return ldapTemplate.search(query,
                (AttributesMapper<String>) attrs ->
                        (String) attrs.get("cn").get());
    }
}
```

Giả định `LdapContextSource` đã cấu hình base `dc=example,dc=org`; vậy `ou=people` là **base tương đối**. Trong ví dụ, `.is(uid)` tạo equality condition và **mã hóa ký tự đặc biệt của giá trị**; nó phù hợp với index equality trên `uid` nếu server có index đó. `.attributes("cn")` chỉ yêu cầu thuộc tính cần trả về, giảm dữ liệu mạng và công sức ánh xạ. `.countLimit(100)` là giới hạn kết quả, **không phải yêu cầu server dùng index**.

Không dùng cách nối chuỗi sau với dữ liệu từ client:

```java
// KHÔNG AN TOÀN: chuỗi nhập có thể thay đổi cú pháp filter.
String filter = "(&(objectClass=inetOrgPerson)(uid=" + userInput + "))";
```

Input chứa dấu `*` hoặc dấu ngoặc có thể biến yêu cầu equality thành substring hoặc thay đổi logic truy vấn. Dùng builder đúng loại so khớp giúp giữ ngữ nghĩa và tránh **LDAP filter injection**.

### 7.2. Substring cố định và prefix do người dùng nhập

Khi mẫu do ứng dụng **cố định** và chủ động muốn tìm tiền tố:

```java
LdapQuery query = LdapQueryBuilder.query()
        .base("ou=people")
        .where("cn").like("Lan*");
```

Spring LDAP có `like(...)` cho filter chứa wildcard. **Cẩn thận:** `like` cố ý giữ dấu `*` làm wildcard; vì thế **không** truyền trực tiếp chuỗi người dùng để giả vờ so khớp chính xác.

Nếu muốn tính năng “tên bắt đầu bằng tiền tố người dùng nhập”, có thể giữ dấu sao do **ứng dụng quyết định** bên ngoài tham số đã escape:

```java
public List<String> findNamesByPrefix(String userPrefix) {
    if (userPrefix == null || userPrefix.trim().length() < 3) {
        throw new IllegalArgumentException("Prefix must contain at least 3 characters");
    }

    LdapQuery query = LdapQueryBuilder.query()
            .base("ou=people")
            .searchScope(SearchScope.SUBTREE)
            .attributes("cn")
            .countLimit(100)
            .filter("(&(objectClass=inetOrgPerson)(cn={0}*))", userPrefix);

    return ldapTemplate.search(query,
            (AttributesMapper<String>) attrs ->
                    (String) attrs.get("cn").get());
}
```

Ở đây, `filter(String, Object...)` của Spring LDAP **escape các tham số**, còn `*` được viết cố định trong filter format để tạo substring **prefix**. Input chứa dấu `*` được xem là một phần giá trị của tiền tố, không tự mở rộng thành wildcard tùy ý. Không cho client điều khiển **tên thuộc tính** hoặc toàn bộ chuỗi filter nếu không có cơ chế allowlist/kiểm soát riêng.

Ví dụ trên còn cần áp dụng giới hạn độ dài tối đa, quy tắc chuẩn hóa input, authorization và chính sách lỗi phù hợp với ứng dụng thật. Độ dài tối thiểu 3 chỉ là lựa chọn minh họa, không phải giới hạn chuẩn của LDAP hay yêu cầu tối ưu chung cho mọi directory.

### 7.3. Spring Data LDAP repository

Với entity `@Entry`, `@Id` và `@Attribute` được ánh xạ đúng, repository có thể khai báo:

```java
import java.util.List;
import org.springframework.data.ldap.repository.LdapRepository;

public interface PersonRepository extends LdapRepository<Person> {
    List<Person> findByUid(String uid);
}
```

Phương thức `findByUid` thể hiện một truy vấn theo **thuộc tính `uid` đã ánh xạ**. Nếu filter thực tế là equality và directory duy trì equality index tương ứng, repository có thể hưởng lợi. Nhưng **Spring Data LDAP không tự thêm `olcDbIndex` hoặc cấu hình index trên server**. Phải đối chiếu bộ lọc sinh ra, search base/scope và các tính năng repository với phiên bản framework đang dùng.

Khi yêu cầu tối ưu cần kiểm soát chính xác filter, vùng tìm hoặc thuộc tính được trả về, `LdapTemplate` với `LdapQueryBuilder` thường cho phép thể hiện lựa chọn một cách trực tiếp và dễ kiểm chứng hơn.

## 8. Ví dụ chỉ mục bên máy chủ OpenLDAP

Với OpenLDAP sử dụng cấu hình `cn=config` và backend hỗ trợ indexing, quản trị viên có thể khai báo trong cấu hình database các chỉ mục như:

```ldif
olcDbIndex: objectClass eq
olcDbIndex: uid eq
olcDbIndex: mail eq
olcDbIndex: cn sub
```

Đây là **đoạn minh họa cú pháp cấu hình index**, không phải một entry người dùng hoàn chỉnh để Add trực tiếp. Nó nói rằng:

- `objectClass eq` hỗ trợ tìm theo object class.
- `uid eq` hỗ trợ equality filter trên mã người dùng.
- `mail eq` hỗ trợ equality filter email.
- `cn sub` hỗ trợ substring match trên common name theo khả năng backend.

OpenLDAP cũng có loại `pres`, `approx`, `subinitial`, `subany`, `subfinal`. Không nên thêm tất cả index “cho chắc”: mỗi index tốn dung lượng và chi phí duy trì khi **Add/Modify/Delete**. Index có ích khi phù hợp với truy vấn thường gặp và dữ liệu có độ chọn lọc phù hợp.

**Giới hạn ví dụ:** các tên `olcDbIndex` và `eq/pres/sub` là quy ước OpenLDAP; chúng **không phải annotation Spring Data LDAP, không phải chuẩn cấu hình chung** cho Microsoft Active Directory, 389 Directory Server hoặc mọi sản phẩm LDAP. Directory khác có giao diện quản trị và cơ chế index riêng. Khi thay đổi index trên server đang chạy, cần hiểu quy trình xây dựng lại chỉ mục, tải hệ thống, backup và cách kiểm tra hoàn tất theo hướng dẫn của phiên bản server.

### 8.1. Cách chọn danh sách index theo workload

Thay vì cấu hình mọi thuộc tính, hãy xuất phát từ **bộ lọc đang được ứng dụng sử dụng nhiều nhất**:

| Workload | Filter điển hình | Index cần xem xét ở OpenLDAP |
| --- | --- | --- |
| Đăng nhập/tra cứu user ID bằng tài khoản dịch vụ | `(uid=lan)` | `uid eq` |
| Tìm người dùng theo email chính xác | `(mail=lan@example.org)` | `mail eq` |
| Tìm tên theo prefix | `(cn=Lan*)` | `cn sub` hoặc `subinitial` |
| Chỉ đọc entry thuộc một object class | `(objectClass=inetOrgPerson)` | `objectClass eq`, nhưng thường ít chọn lọc |
| Tìm những entry thiếu email | `(!(mail=*))` | Đo thực tế; không mặc định thêm `mail pres` sẽ tốt |
| Tìm user theo thuộc tính tùy chỉnh `employeeId` | `(employeeId=A1234)` | `employeeId eq` nếu schema/index hỗ trợ |

Tên `employeeId` chỉ là **ví dụ thuộc tính tùy chỉnh**; không phải mọi LDAP directory đều có tên thuộc tính đó. Phải xác minh schema và matching rule trước khi dùng.

## 9. Chọn filter theo một quy trình thực tế

### Bước 1: Xác định đúng yêu cầu dữ liệu

Hỏi rõ ứng dụng cần **đúng một người theo mã**, danh sách người trong OU, tìm tên theo tiền tố hay tìm chuỗi bất kỳ. Nếu đã biết `uid` chính xác, đừng dùng contains search chỉ vì giao diện của ứng dụng có một ô tìm kiếm chung.

### Bước 2: Xác định entry và schema

Xem attribute thực tế có trong directory: `uid`, `cn`, `mail`, `member`, `uniqueMember`, hoặc thuộc tính riêng. Kiểm tra:

- Attribute là đơn trị hay đa trị?
- Có equality/substring/ordering matching rule phù hợp không?
- Các entry muốn tìm có cùng `objectClass` hay phân tán nhiều class?
- Việc so sánh có phụ thuộc kiểu chữ, khoảng trắng, mã hóa hay DN reference không?

Ví dụ `memberOf` không phải attribute mặc định được tất cả LDAP server tự duy trì; không viết filter phụ thuộc `memberOf` rồi giả định mọi directory đều hỗ trợ và đã index.

### Bước 3: Giới hạn search base/scope theo nghiệp vụ

Chọn OU, naming context và scope nhỏ nhất **mà vẫn đầy đủ kết quả**. Không nên tìm cả `dc=example,dc=org` chỉ để tra cứu người dùng trong `ou=people` khi có thể giới hạn nhánh.

### Bước 4: Chọn phép so khớp phù hợp

Ưu tiên equality cho **khóa chính xác**, substring prefix nếu nghiệp vụ thật sự cần prefix, presence cho việc kiểm tra tồn tại, và chỉ dùng approximate/order/extensible match khi schema/server hỗ trợ. Tránh NOT hoặc OR chứa nhánh wildcard rất rộng trừ khi nghiệp vụ yêu cầu.

### Bước 5: Đối chiếu index với quản trị viên server

Xác định directory product, backend, phiên bản, những index hiện có và khả năng sử dụng. Nếu thiếu index, cần đánh giá **thêm index** so với **đổi filter/giới hạn scope**, vì thêm index có chi phí dung lượng và ghi dữ liệu.

### Bước 6: Thử và đo

Đo kết quả thực tế trên workload đại diện. Không coi bộ lọc có index theo lý thuyết là đã tối ưu nếu chưa thấy cải thiện hiệu năng và quan sát phù hợp ở server.

## 10. Đo hiệu năng: tránh nhầm tốc độ client với index server

Một phép đo đáng tin cậy cần phân biệt:

```text
Tổng latency ở ứng dụng
    ≈ chờ pool/kết nối + network/TLS
    + thời gian search tại LDAP server
    + truyền và chuyển đổi kết quả sang Java
```

Nếu chỉ đo tổng HTTP response time, khó biết thay đổi là do index, pool, mạng, số entry trả về, hay cache. Thiết kế một thử nghiệm như sau:

1. **Chuẩn bị dataset:** directory test có đủ entry và độ phân bố thuộc tính gần production; đặt tên/uid/email giả.
2. **Chạy đường cơ sở:** giữ cố định search base/scope, request concurrency, kết nối và số lần chạy. Đo p50/p95/p99 và số entry trả về.
3. **Ghi filter chính xác:** ví dụ `(uid=lan)` so với `(uid=lan*)`, hoặc `(cn=Lan*)` so với `(cn=*Lan*)`. **Không so sánh hai filter như thể tương đương** nếu tập kết quả khác nhau.
4. **Kiểm tra server logs/counters:** xem số entry được xét, index được dùng hay không, thời gian xử lý, lỗi giới hạn theo khả năng của directory server. Với OpenLDAP, đọc logging/debug của backend và hướng dẫn quản trị phù hợp.
5. **Thay một yếu tố:** ví dụ điều chỉnh index trong directory test theo đúng quy trình của server, sau đó chạy lại **cùng filter** và cùng dataset để so sánh có kiểm soát.
6. **Làm nóng hợp lý:** phân biệt cold cache, warm cache, thời gian xây index và trạng thái connection pool; tránh chỉ chạy một truy vấn rồi kết luận.
7. **Kiểm chứng kết quả:** DN, `objectClass` và các thuộc tính của kết quả phải đúng trước và sau tối ưu; kiểm tra cả trường hợp không có kết quả, trùng uid trong hai OU và lỗi quyền.

Ví dụ bảng đo **giả định**, chỉ để minh họa cách ghi kết quả:

| Kịch bản | p95 từ ứng dụng | Entry trả về | Ghi chú cần điều tra |
| --- | ---: | ---: | --- |
| `(uid=lan)`, chưa có `uid eq` | 120 ms | 1 | Server có thể kiểm tra nhiều entry |
| `(uid=lan)`, có `uid eq` | 15 ms | 1 | Cần xác minh index được dùng |
| `(cn=*an*)`, có `cn sub` | 210 ms | 8.000 | Tập khớp lớn; index chưa chắc đủ giúp |
| `(mail=*)` | 170 ms | 480.000 | Presence có độ chọn lọc thấp |

**Không diễn giải số giả định này như hiệu năng của Spring LDAP hay OpenLDAP.** Dữ liệu, phiên bản, caching và hạ tầng thật có thể cho kết quả hoàn toàn khác. Index có thể giúp tìm ứng viên nhưng không thể miễn chi phí trả về/ánh xạ hàng nghìn entry.

### 10.1. Thử trực tiếp bằng `ldapsearch`

Trong môi trường thử nghiệm có tài khoản read-only:

```bash
ldapsearch -x \
  -H "ldaps://directory.example.org:636" \
  -D "uid=reader,ou=services,dc=example,dc=org" -W \
  -b "ou=people,dc=example,dc=org" -s sub \
  "(&(objectClass=inetOrgPerson)(uid=lan))" \
  dn uid cn
```

Lệnh trên gửi filter cố định và chỉ lấy `dn`, `uid`, `cn`. `-W` yêu cầu nhập mật khẩu tương tác, tránh ghi mật khẩu trực tiếp vào dòng lệnh. Với môi trường khác, cách xác thực có thể là SASL hoặc cơ chế khác; kết nối TLS cần xác minh chứng chỉ. Thời gian thực thi `ldapsearch` vẫn bao gồm thời gian kết nối và mạng, không tự chứng minh index đã được dùng.

Đối với tập kết quả lớn, cần xem xét **LDAP paged results control** nếu server hỗ trợ để nhận dữ liệu theo trang. Phân trang giảm áp lực trả về dữ liệu mỗi lần, nhưng cũng **không thay thế tối ưu filter/index**.

## 11. Lỗi thường gặp khi tối ưu filter

| Triệu chứng | Nguyên nhân có thể | Điều cần làm |
| --- | --- | --- |
| `findByUid` chậm dù chỉ một kết quả | `uid` thiếu equality index, base quá rộng hoặc kết nối chậm | Kiểm tra index `uid eq`, base/scope và đo server |
| Tìm `cn` với wildcard rất chậm | Dùng `*term*`, thiếu substring index hoặc mẫu quá phổ biến | Kiểm tra `cn sub` và cân nhắc prefix/giới hạn nhánh |
| `(mail=*)` vẫn chậm dù có presence index | Gần mọi entry đều có `mail` | Đánh giá lại nhu cầu và selectivity; index không biến kết quả lớn thành nhỏ |
| Thêm nhiều điều kiện AND nhưng không nhanh | Các điều kiện đều ít chọn lọc hoặc optimizer chọn index khác | Đo từng predicate và xem server plan/log |
| OR có một nhánh ID và một nhánh chứa tên | Nhánh substring quá rộng làm kế hoạch đắt | Cân nhắc tách luồng nghiệp vụ và tối ưu nhánh rộng |
| Dùng `>=`, `<=` nhưng index `eq` không giúp | Ordering rule/index không được hỗ trợ như giả định | Kiểm tra schema và directory product |
| Tìm `memberOf` không ra kết quả | Server không tạo attribute đó hoặc ACL/thuộc tính khác | Kiểm tra schema, mapping nhóm và quyền truy cập |
| User nhập `*` làm filter trả quá nhiều entry | Nối chuỗi input hoặc dùng `like` sai ý nghĩa | Dùng `is` cho equality; escape giá trị đúng chuẩn |
| Thêm index xong write chậm hơn | Index mới phải được duy trì trong Add/Modify/Delete | Chọn index theo workload và đo cả tải ghi |
| Giới hạn `countLimit(100)` nhưng server vẫn tốn tài nguyên | Giới hạn kết quả không tự chọn index | Đánh giá filter/selectivity và logs server |
| Test một lần nhanh, lúc tải thật chậm | Cache, pool, concurrency và data skew khác nhau | Chạy benchmark đại diện, xem p95/p99 |

## 12. Bài thực hành tự kiểm tra

**Bài 1.** API đã biết chính xác `uid=lan`, server có `uid eq`. Chọn filter nào phù hợp hơn giữa `(uid=lan)` và `(uid=*lan*)`?

*Gợi ý:* Chọn **equality `(uid=lan)`** vì đó là yêu cầu chính xác và phù hợp với equality index. Substring thay đổi ngữ nghĩa, có thể trả thêm entry và tốn hơn.

**Bài 2.** Trong 500.000 entry, 480.000 entry có `mail`. Nếu truy vấn `(mail=*)` thường xuyên, thêm `mail pres` có chắc làm truy vấn nhanh không?

*Gợi ý:* **Không**. Presence filter có độ chọn lọc rất thấp; chi phí index và khối lượng kết quả lớn vẫn đáng kể. Cần đo workload và xem khuyến nghị server.

**Bài 3.** Server có `uid eq` nhưng chưa có `cn sub`. Vì sao `(|(uid=lan)(cn=*an*))` vẫn có thể chậm?

*Gợi ý:* Nhánh `cn=*an*` có thể không có index phù hợp và khớp nhiều entry. Một nhánh OR có index không bảo đảm cả biểu thức rẻ.

**Bài 4.** Với DN `uid=lan,ou=contractors,dc=example,dc=org`, tại sao query từ `ou=people,dc=example,dc=org` không trả Lan dù filter `(uid=lan)` chính xác?

*Gợi ý:* Entry nằm **ngoài search base**, nên không thuộc vùng được xét. Index không thể thay đổi ngữ nghĩa của base/scope.

**Bài 5.** Vì sao không nên lấy input người dùng `prefix` rồi viết `"(cn=" + prefix + "*)"`?

*Gợi ý:* Dữ liệu có thể chứa ký tự filter đặc biệt; cần escape phần giá trị do người dùng nhập. Dùng `LdapQueryBuilder.filter("(...(cn={0}*))", prefix)` hoặc API phù hợp, và giữ wildcard do ứng dụng quyết định.

**Bài 6.** Bạn muốn biết `uid eq` thực sự được sử dụng. Chỉ nhìn `findByUid` trả kết quả trong 10 ms đã đủ kết luận chưa?

*Gợi ý:* **Chưa đủ**. Có thể do cache, pool hoặc ít dữ liệu. Cần quan sát thông tin server, đo tải đại diện và so sánh có kiểm soát.

## 13. Ghi nhớ

- Filter LDAP phải khớp **ý nghĩa nghiệp vụ** trước, rồi mới tối ưu theo **index và matching rule** của máy chủ.
- Với OpenLDAP, `eq`, `pres`, `sub` là các loại index khác nhau; **cùng một attribute nhưng khác phép so khớp có thể cần loại index khác**.
- **Equality** trên khóa chính xác như `uid` thường là lựa chọn tốt khi có index và độ chọn lọc cao. Wildcard, presence, OR rộng và NOT cần được đánh giá thận trọng.
- **Base + scope + filter** cùng quyết định dữ liệu được xét; giới hạn vùng tìm đúng nghiệp vụ thường hữu ích không kém việc có index.
- `LdapQueryBuilder` hỗ trợ filter an toàn; dùng `is` cho equality, `like` khi **cố ý** dùng wildcard và tham số escape với `filter(String, Object...)` khi xây prefix từ input.
- **Spring Data LDAP không cấu hình index server thay bạn.** Chỉ thêm hoặc thay index theo workload đã đo, cân nhắc chi phí ghi và kiểm tra việc server thật sự sử dụng index.

**Tài liệu tham khảo:**

- [OpenLDAP Administrator's Guide — Indexing](https://directory.openldap.org/doc/admin26/guide.html): `olcDbIndex`, `eq/pres/approx/sub` và các loại substring index.
- [OpenLDAP Administrator's Guide — Tuning Indexes](https://www.openldap.org/doc/admin25/guide.html): chọn index theo filter thực tế, độ chọn lọc presence và chi phí duy trì.
- [Spring LDAP — Advanced LDAP Queries](https://docs.spring.io/spring-ldap/reference/query-builder-advanced.html): `is`, `like`, `isPresent`, `gte`/`lte` và filter tham số.
- [Spring LDAP API — LdapQueryBuilder](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/query/LdapQueryBuilder.html): base, search scope, attributes, count limit và cách mã hóa tham số.
- [RFC 4511 — LDAP: The Protocol](https://www.rfc-editor.org/rfc/rfc4511): search request, filter và logic so khớp ba giá trị.
- [RFC 4515 — String Representation of Search Filters](https://www.rfc-editor.org/rfc/rfc4515): cú pháp và escape giá trị LDAP filter.
