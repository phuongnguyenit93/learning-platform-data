# Đánh giá chi phí wildcard và tìm kiếm toàn cây

## Mục tiêu bài học

Trong **Spring Data LDAP**, ứng dụng Java có thể dùng **LdapRepository** hoặc **LdapTemplate** để truy vấn người dùng, nhóm và các entry phân cấp của directory. Một truy vấn như **(uid=an)** thường có mục tiêu rất hẹp, trong khi **(cn=*an*)** hoặc tìm **SUBTREE** từ gốc toàn directory có thể phải xét rất nhiều entry. Sự khác biệt này ảnh hưởng đến độ trễ API, tài nguyên LDAP server, lưu lượng mạng và khả năng các request khác được phục vụ.

Ở chương **Hiệu năng**, bài này hướng dẫn **đánh giá chi phí wildcard và tìm kiếm toàn cây** dựa trên cú pháp LDAP filter, phạm vi tìm kiếm, chỉ mục, độ chọn lọc của điều kiện và cách ánh xạ dữ liệu trong Spring LDAP. Mục tiêu không phải cấm mọi wildcard hay subtree search: cần biết khi nào chúng cần thiết, vì sao chúng có thể đắt và cách đo đạc trước khi tối ưu.

Sau bài học, bạn có thể:

- Phân biệt **equality**, **presence**, **prefix substring**, **suffix substring** và **contains substring** trong LDAP filter.
- Phân biệt **SearchScope.OBJECT**, **ONELEVEL** và **SUBTREE**; hiểu vai trò của **base DN**.
- Giải thích tác động của chỉ mục **eq**, **sub**, **pres**, mức độ chọn lọc và số lượng candidate entries lên chi phí truy vấn.
- Dùng **LdapQueryBuilder** và **LdapTemplate** để giới hạn phạm vi, thuộc tính trả về, thời gian và số kết quả.
- Biết khi nào dùng **repository**, khi nào chuyển sang truy vấn LdapTemplate có kiểm soát hiệu năng cụ thể.
- Đánh giá server-side paging, timeout, giới hạn LDAP server và giới hạn riêng của Active Directory.
- Lập benchmark có kiểm soát, đo **p95 latency**, lượng entry trả về và ảnh hưởng tới server mà không biến môi trường sản xuất thành nơi thử truy vấn nặng.

## 1. Hai trục quyết định truy vấn LDAP tốn kém đến đâu

Một yêu cầu LDAP search tối thiểu có:

1. **Search base**: bắt đầu tìm tại DN nào?
2. **Search scope**: chỉ xét entry gốc, các entry con trực tiếp hay toàn bộ cây con?
3. **Filter**: entry nào phải đáp ứng điều kiện?
4. **Attributes to return**: cần đọc những thuộc tính nào?
5. **Giới hạn**: kết quả tối đa, thời gian, chính sách paging và quota server.

Ví dụ directory:

~~~text
dc=example,dc=org
├── ou=people
│   ├── uid=an
│   ├── uid=binh
│   └── ou=contractors
│       └── uid=chi
├── ou=groups
│   └── cn=backend
└── ou=services
    └── uid=svc-app
~~~

Hai truy vấn cùng filter **(uid=an)** nhưng dùng base khác nhau có phạm vi tìm khác nhau. Ngược lại, hai truy vấn cùng tìm trong **ou=people** nhưng dùng **(uid=an)** và **(cn=*an*)** cũng có khả năng tiêu tốn tài nguyên rất khác nhau.

**Nguyên tắc:** chi phí truy vấn phụ thuộc đồng thời vào **scope/base**, **filter**, **index**, **mức phân bố dữ liệu**, **kết quả cần trả** và **cấu hình directory**. Không thể kết luận tốc độ chỉ bằng cách nhìn thấy dấu sao hay một từ khóa **SUBTREE**.

## 2. Wildcard trong LDAP filter thực sự có nghĩa gì?

Theo cú pháp LDAP search filter (RFC 4515), dấu sao **\*** không được escape có thể diễn tả sự xuất hiện thuộc tính hoặc các đoạn khớp trong **substring filter**.

| Filter minh họa | Nghĩa truy vấn | Loại điều kiện |
| --- | --- | --- |
| **(uid=an)** | uid khớp giá trị **an** theo matching rule của thuộc tính | Equality |
| **(cn=An*)** | cn bắt đầu bằng **An** | Substring với phần đầu cố định |
| **(cn=*Tran)** | cn kết thúc bằng **Tran** | Substring với phần cuối cố định |
| **(cn=*an*)** | cn có đoạn **an** ở vị trí bất kỳ | Substring chứa chuỗi |
| **(cn=A*n)** | cn bắt đầu bằng **A** và kết thúc bằng **n**, có thể có nội dung ở giữa | Substring gồm nhiều đoạn |
| **(mail=*)** | Thuộc tính mail có mặt | Presence, **không** phải tìm chuỗi mail bất kỳ |
| **(&(objectClass=inetOrgPerson)(uid=an))** | Kết hợp loại entry và uid | AND giữa hai điều kiện |
| **(!(uid=an))** | Entry không khớp uid=an | NOT, có thể rất rộng |

### 2.1. Equality không phải so khớp chuỗi Java đơn thuần

LDAP **matching rule** được quy định theo attribute type/schema. Ví dụ **uid**, **cn**, **mail** có cách chuẩn hóa, phân biệt hoa/thường hoặc so sánh khác nhau tùy thuộc schema và directory. Vì vậy filter **(uid=an)** không nhất thiết được đánh giá giống **"an".equals(value)** trong Java.

Phần cố định của substring filter cũng chịu matching rule và cách lập index của server. Không tự giả định **(cn=An*)** chỉ được thực hiện bằng cách kiểm tra từng chuỗi từ đầu đến cuối theo thuật toán Java.

### 2.2. Dấu sao mang hai vai trò dễ nhầm

~~~ldap
(mail=*)          # Thuộc tính mail tồn tại
(mail=*example*)   # Chuỗi mail có chứa đoạn example
(mail=an*)        # Mail bắt đầu bằng an
~~~

**(mail=*)** là **presence filter**. Trong thực tế, nếu hầu hết entry trong phạm vi đã có **mail**, điều kiện này **không mang lại độ chọn lọc cao**; nó có thể trả phần lớn dữ liệu.

Một dấu sao mà người dùng nhập với ý nghĩa **ký tự chữ `*` thực sự** không nên được chuyển thẳng thành wildcard. Theo RFC 4515, ký tự sao literal trong giá trị filter phải được escape thành **\\2a**. Ví dụ:

~~~ldap
(cn=\2a)           # cn bằng ký tự * theo matching rule
(cn=*\2a*)         # cn chứa ký tự * literal
~~~

Tương tự, các ký tự **(**, **)**, dấu gạch chéo ngược và NUL có quy tắc escape riêng. **DN escaping** và **filter escaping** là hai cú pháp khác nhau. Hãy sử dụng API tạo DN và filter phù hợp, không tự ghép chuỗi từ input.

## 3. Vì sao wildcard có thể tăng chi phí?

Giả sử một nhánh có nhiều entry **inetOrgPerson**. Truy vấn theo uid cụ thể chỉ nên trả một vài entry; truy vấn **(cn=*an*)** có thể khớp hàng nghìn hồ sơ vì đoạn **an** xuất hiện trong nhiều tên.

Chi phí có thể phát sinh ở nhiều bước:

~~~mermaid
flowchart TD
    A["Nhận search base + scope + filter"] --> B["Server xác định tập entry ứng viên"]
    B --> C["Dùng index nếu có và phù hợp"]
    C --> D["Đánh giá các điều kiện trên candidate entries"]
    D --> E["Áp dụng ACL, giới hạn và chọn attributes"]
    E --> F["Mã hóa/gửi kết quả qua mạng"]
    F --> G["Spring LDAP giải mã và ánh xạ Java object"]
~~~

| Nguồn chi phí | Vì sao đáng chú ý |
| --- | --- |
| **Nhiều candidate entries** | Server phải tìm/đọc và đánh giá nhiều entry hơn |
| **Không có index phù hợp** | Server có thể phải duyệt rộng hoặc làm nhiều thao tác kiểm tra hơn |
| **Filter chọn lọc kém** | Ngay cả khi có index, một tập kết quả rất lớn vẫn tốn tài nguyên |
| **Subtree lớn** | Có thể bao gồm nhiều OU, nhóm, tài khoản dịch vụ và nhánh không liên quan |
| **Trả nhiều attributes** | Dữ liệu lớn hơn, có thể gồm thuộc tính đa giá trị hoặc nhị phân |
| **Nhiều entry trả về** | Tăng chi phí mạng, tạo đối tượng Java, GC và RAM ở ứng dụng |
| **Truy vấn lặp lại** | Nhiều request đắt thực hiện đồng thời có thể ảnh hưởng mọi client LDAP |

**Wildcard đầu chuỗi không phải lúc nào cũng chậm hơn trong mọi server**, và **truy vấn có index không phải lúc nào cũng nhanh**. Các index substring có thể hỗ trợ các dạng phần đầu, phần giữa hoặc phần cuối; cách thực hiện và hiệu quả phụ thuộc directory backend, matching rule, độ dài chuỗi và phân bố giá trị.

### 3.1. So sánh các mẫu truy vấn

| Mẫu truy vấn | Khả năng tối ưu thông thường | Rủi ro cần kiểm tra |
| --- | --- | --- |
| **(uid=an)** | Có thể tận dụng equality index; thường chọn lọc nếu uid có chính sách duy nhất | Index có tồn tại? uid có trùng ở nhiều OU không? |
| **(cn=An*)** | Có thể dùng substring index cho phần đầu hoặc cơ chế tiền tố của server | Prefix quá ngắn, nhiều người có tên giống nhau |
| **(cn=*Tran)** | Phụ thuộc chỉ mục/khả năng xử lý suffix | Có index phù hợp cho hậu tố không? |
| **(cn=*an*)** | Có thể cần substring-any index và tập candidate lớn | Đoạn khớp phổ biến; dễ trả nhiều entry |
| **(cn=*)** | Presence filter, ít chọn lọc nếu hầu hết entry có cn | Index presence khó đem lại lợi ích khi thuộc tính phổ biến |
| **(objectClass=inetOrgPerson)** | Có thể dùng equality index objectClass | Vẫn có thể khớp gần như mọi tài khoản người dùng |
| **(!(uid=an))** | Điều kiện phủ định thường chọn lọc kém | Hầu như toàn bộ cây có thể khớp |

Một prefix hai ký tự như **An** có thể vẫn rất rộng. Thay đổi **(cn=An*)** thành **(cn=An Tran*)** có thể giảm tập kết quả; tuy nhiên không coi việc tăng số ký tự là bảo đảm hiệu năng nếu không đo trên dữ liệu thật.

## 4. Search scope: OBJECT, ONELEVEL và SUBTREE

LDAP có ba phạm vi search cơ bản:

| Scope | Nơi được xem xét | Ví dụ base **ou=people,dc=example,dc=org** |
| --- | --- | --- |
| **OBJECT** | Chỉ chính entry tại base DN | Entry **ou=people** |
| **ONELEVEL** | Chỉ các entry con **trực tiếp** dưới base | **uid=an**, **uid=binh**, **ou=contractors** |
| **SUBTREE** | Base và **mọi cấp con** bên dưới | **ou=people**, An, Binh, **ou=contractors**, Chi |

Nếu người dùng đều là con trực tiếp của **ou=people**, ONELEVEL có thể phù hợp hơn SUBTREE vì không phải đi vào mọi nhánh OU lồng nhau. Nhưng khi hồ sơ người dùng được tổ chức theo phòng ban con, ONELEVEL có thể bỏ sót người dùng.

Trong Spring LDAP, **SearchScope.SUBTREE** thường là mặc định của LdapQueryBuilder/LdapTemplate khi không chỉ định khác. Vì vậy một method tìm kiếm tưởng đơn giản có thể đang duyệt **toàn bộ cây con của base DN**.

### 4.1. Base DN quan trọng ngang scope

Giả sử ContextSource cấu hình **base=dc=example,dc=org**:

~~~text
base=""            + SUBTREE = tìm từ dc=example,dc=org
base="ou=people"   + SUBTREE = chỉ cây dưới ou=people
base="ou=people"   + ONELEVEL = chỉ con trực tiếp của ou=people
base="uid=an,ou=people" + OBJECT = chỉ entry An
~~~

Trong ngữ cảnh LdapTemplate, các **base** trên là DN **tương đối với base của ContextSource**. Nếu ghép **dc=example,dc=org** hai lần, search có thể trả rỗng hoặc lỗi **noSuchObject**, không phải đơn giản là một truy vấn chậm.

**Tìm toàn cây** không có nghĩa bắt buộc là truy vấn không có wildcard. Ví dụ:

~~~ldap
# Base: dc=example,dc=org; Scope: SUBTREE
(&(objectClass=inetOrgPerson)(uid=an))
~~~

Filter khá chọn lọc nhưng search base rộng. Một truy vấn khác:

~~~ldap
# Base: ou=people,dc=example,dc=org; Scope: ONELEVEL
(cn=*)
~~~

Base/scope hẹp hơn nhưng filter rộng. Chi phí thực tế của hai truy vấn phải đo; không chỉ nhìn một thuộc tính để đoán kết quả.

### 4.2. Chọn scope theo mục đích

- **Biết DN của entry cần đọc:** ưu tiên lookup trực tiếp; khi cần search riêng entry, dùng **OBJECT**.
- **Biết danh sách người dùng nằm ngay dưới một OU:** thử **ONELEVEL**.
- **Có OU lồng nhau theo phòng ban:** cần **SUBTREE** trong nhánh nghiệp vụ, không nhất thiết từ toàn suffix.
- **Tìm người dùng toàn công ty:** xác định tập nhánh cần tìm, index, paging và giới hạn cho mục đích này; không mặc định search gốc là lựa chọn tốt.
- **Tìm nhóm:** chỉ tìm dưới vùng nhóm được quản trị thay vì quét mọi OU nếu schema và cấu trúc directory cho phép.

## 5. Index và độ chọn lọc: hai khái niệm không thay thế nhau

**Index** là cấu trúc dữ liệu do LDAP server quản lý để hỗ trợ tra cứu. **Selectivity (độ chọn lọc)** mô tả điều kiện lọc giữ lại ít hay nhiều entry so với tập có thể xem xét. Một filter có index nhưng khớp rất nhiều entry vẫn có thể đắt; một filter rất chọn lọc nhưng không có index có thể phải kiểm tra nhiều entry.

### 5.1. Ví dụ OpenLDAP

OpenLDAP hỗ trợ nhiều kiểu index, phổ biến là:

- **eq:** equality, ví dụ **(uid=an)**.
- **sub:** substring, ví dụ **(cn=An*)**, **(cn=*an*)** khi phù hợp với cấu hình.
- **pres:** presence, ví dụ **(mail=*)**.
- Ngoài ra có một số kiểu/chi tiết index tùy backend và matching rule.

Một cấu hình **minh họa để đọc hiểu**, không phải lệnh áp dụng tự động:

~~~text
# Dạng olcDbIndex trong OpenLDAP; vị trí cấu hình tùy backend.
olcDbIndex: objectClass eq
olcDbIndex: uid eq
olcDbIndex: cn eq,sub
~~~

Trong OpenLDAP, index substring có thể chi tiết hơn thành **subinitial**, **subany**, **subfinal**. Điều này cho thấy một filter bắt đầu hay kết thúc bằng wildcard không đủ để dự đoán chắc chắn khả năng dùng index.

**Không tạo index bừa bãi**: mỗi index chiếm dung lượng, cần bảo trì khi thêm/sửa/xóa entry và có thể làm chậm thao tác ghi. Với thuộc tính xuất hiện gần như ở mọi entry, presence index thường ít đem lại lợi ích. Chọn index dựa trên những truy vấn có thật, thống kê dữ liệu và hướng dẫn quản trị của backend.

### 5.2. Active Directory khác OpenLDAP

Active Directory DS có những đặc điểm riêng như schema **searchFlags**, indexing policies, giới hạn LDAP search, **ANR (Ambiguous Name Resolution)** và Global Catalog/Partial Attribute Set. Không sao chép cấu hình **olcDbIndex** của OpenLDAP vào AD DS.

Nếu dùng Global Catalog để tra cứu trên nhiều domain, việc một thuộc tính không thuộc **Partial Attribute Set** còn ảnh hưởng tới khả năng tìm và đọc dữ liệu của các domain khác. Tối ưu index trên một DC không biến GC thành bản sao đầy đủ mọi thuộc tính, và một scope SUBTREE từ một domain base không tự bao phủ mọi domain tree trong forest.

**Bài học chung:** cần hỏi quản trị viên directory xem **filter nào được lập index, ở backend nào**, loại search nào bị giới hạn và việc thêm index ảnh hưởng ra sao tới replication/ghi dữ liệu.

## 6. Cấu hình truy vấn giới hạn chi phí bằng LdapTemplate

Spring LDAP hỗ trợ **LdapQueryBuilder** với **base**, **searchScope**, **attributes**, **countLimit**, **timeLimit** và filter. Cách kết hợp những thuộc tính này thường dễ kiểm soát hơn việc chỉ khai báo một repository finder không có chính sách truy vấn rõ ràng.

Giả sử Spring Boot kết nối LDAP qua TLS:

~~~yaml
spring:
  ldap:
    urls: ldaps://ldap.example.org:636
    base: dc=example,dc=org
    username: uid=svc-reader,ou=service-accounts,dc=example,dc=org
    password: ${LDAP_BIND_PASSWORD}
~~~

**LDAPS** phải kiểm tra CA và hostname, bind account chỉ có quyền đọc cần thiết. Directory có entry người dùng **inetOrgPerson** dưới **ou=people**, một số nằm trực tiếp dưới OU, một số ở OU lồng nhau.

### 6.1. Service có ba mức truy vấn

~~~java
package org.example.directory;

import java.util.List;
import javax.naming.NamingException;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;

import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.SearchScope;
import org.springframework.stereotype.Service;

import static org.springframework.ldap.query.LdapQueryBuilder.query;

record PersonSummary(String uid, String cn, String mail) {}

@Service
public class PeopleSearchService {
    private static final String PEOPLE_BASE = "ou=people";
    private static final int MAX_RESULTS = 50;

    private static final AttributesMapper<PersonSummary> MAPPER =
        attrs -> new PersonSummary(
            stringValue(attrs, "uid"),
            stringValue(attrs, "cn"),
            stringValue(attrs, "mail"));

    private final LdapTemplate ldapTemplate;

    public PeopleSearchService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    // 1. Equality: nhanh và rõ ý định nếu uid có index phù hợp.
    // ONELEVEL chỉ đúng khi user nằm trực tiếp dưới ou=people.
    public List<PersonSummary> findDirectUserByUid(String uid) {
        requireToken(uid, 2, 64);
        return ldapTemplate.search(
            query()
                .base(PEOPLE_BASE)
                .searchScope(SearchScope.ONELEVEL)
                .attributes("uid", "cn", "mail")
                .countLimit(10)
                .timeLimit(1500)
                .where("objectClass").is("inetOrgPerson")
                .and("uid").is(uid),
            MAPPER);
    }

    // 2. Tìm theo tiền tố; SUBTREE chỉ trong nhánh people.
    public List<PersonSummary> findByCnPrefix(String prefix) {
        requireToken(prefix, 3, 40);
        return ldapTemplate.search(
            query()
                .base(PEOPLE_BASE)
                .searchScope(SearchScope.SUBTREE)
                .attributes("uid", "cn", "mail")
                .countLimit(MAX_RESULTS + 1)
                .timeLimit(1500)
                .where("objectClass").is("inetOrgPerson")
                .and("cn").like(prefix + "*"),
            MAPPER);
    }

    // 3. Contains search: chỉ cho API nghiệp vụ được phê duyệt.
    // Đo hiệu năng trước khi bật trên directory lớn.
    public List<PersonSummary> findByCnContainsForAdmin(String fragment) {
        requireToken(fragment, 4, 40);
        return ldapTemplate.search(
            query()
                .base(PEOPLE_BASE)
                .searchScope(SearchScope.SUBTREE)
                .attributes("uid", "cn", "mail")
                .countLimit(MAX_RESULTS + 1)
                .timeLimit(1500)
                .where("objectClass").is("inetOrgPerson")
                .and("cn").like("*" + fragment + "*"),
            MAPPER);
    }

    private static void requireToken(String value, int min, int max) {
        if (value == null
                || value.length() < min || value.length() > max
                || !value.matches("[A-Za-z0-9 .'-]+")) {
            throw new IllegalArgumentException(
                "Điều kiện tìm kiếm không hợp lệ");
        }
    }

    private static String stringValue(Attributes attrs, String name)
            throws NamingException {
        Attribute attribute = attrs.get(name);
        if (attribute == null || attribute.size() == 0) {
            return null;
        }
        if (attribute.size() != 1) {
            throw new IllegalArgumentException(
                "Thuộc tính có nhiều giá trị: " + name);
        }
        Object raw = attribute.get();
        if (!(raw instanceof String result)) {
            throw new IllegalArgumentException(
                "Thuộc tính không phải chuỗi: " + name);
        }
        return result;
    }
}
~~~

**Lưu ý quan trọng về code:**

1. **findDirectUserByUid** dùng **ONELEVEL** nên **không tìm thấy** người dùng nằm trong **ou=contractors** dưới **ou=people**. Đây là lựa chọn ngữ nghĩa, không phải một “tối ưu” có thể áp dụng vô điều kiện.
2. **findByCnPrefix** dùng **like(prefix + "*")** và **findByCnContainsForAdmin** dùng **like("*" + fragment + "*")**. Dấu sao được **ứng dụng** thêm có chủ đích; regex giới hạn input để người dùng không cung cấp wildcard tùy ý. Nếu phải hỗ trợ Unicode, xây validation phù hợp, nhưng không bỏ giới hạn độ dài/scope.
3. **LdapQueryBuilder.like(...)** là phép xây dựng substring filter; không đồng nghĩa với **is(...)** cho equality. Không dùng **like(rawUserInput)** khi người dùng có thể tự đưa các ký tự wildcard rồi mở rộng filter theo ý mình.
4. **countLimit(51)** không thay thế paging và **không phải bảo đảm luôn nhận đúng 51 kết quả**. Server có thể áp quota chặt hơn, trả lỗi size limit hoặc các kết quả chưa đầy đủ. Không dựa vào việc nhận đúng MAX_RESULTS + 1 để kết luận chắc chắn kết quả có đầy đủ hay không.
5. **timeLimit(1500)** chỉ định giới hạn thời gian tìm kiếm ở tầng LDAP (mili giây với API đang dùng); không nên coi đây là **timeout end-to-end** cho DNS, TCP, TLS, bind, pooling và toàn bộ HTTP request. Cần thêm timeout kết nối/đọc và ngân sách thời gian ở API.
6. **attributes("uid", "cn", "mail")** tránh trả về mọi thuộc tính của mỗi entry. Khi dữ liệu chứa binary/multi-valued fields, khác biệt băng thông và bộ nhớ càng rõ.

**Đừng dùng ví dụ này như API public search không kiểm soát:** giới hạn kết quả, timeout, regex và scope chỉ là một phần. Ứng dụng còn cần phân quyền sử dụng contains search, rate limiting và bảo vệ tài nguyên directory.

### 6.2. Khi đã biết DN: tránh search không cần thiết

Nếu mô hình người dùng **chắc chắn** đặt RDN theo uid, ta có thể xây DN bằng **LdapNameBuilder** rồi lookup trực tiếp:

~~~java
import javax.naming.Name;
import org.springframework.ldap.support.LdapNameBuilder;

Name relativeDn = LdapNameBuilder.newInstance("ou=people")
    .add("uid", "an")
    .build();

PersonSummary person = ldapTemplate.lookup(
    relativeDn,
    (AttributesMapper<PersonSummary>) attrs ->
        new PersonSummary(
            (String) attrs.get("uid").get(),
            (String) attrs.get("cn").get(),
            attrs.get("mail") == null
                ? null : (String) attrs.get("mail").get()));
~~~

Đoạn code nằm trong service đã có **ldapTemplate**. Lookup theo DN phù hợp cho truy vấn một entry đã biết tên. Tuy nhiên, một LDAP directory có thể dùng **cn** thay vì **uid** làm RDN: khi đó phải **search theo thuộc tính uid để lấy DN thật**, không được dựng DN uid cố định rồi khẳng định người dùng không tồn tại.

### 6.3. Với repository Spring Data LDAP

Entity ODM mẫu:

~~~java
import javax.naming.Name;
import org.springframework.ldap.odm.annotations.Attribute;
import org.springframework.ldap.odm.annotations.Entry;
import org.springframework.ldap.odm.annotations.Id;

@Entry(
    base = "ou=people",
    objectClasses = {"top", "person", "organizationalPerson", "inetOrgPerson"}
)
public class PersonEntry {
    @Id
    private Name dn;

    @Attribute(name = "uid")
    private String uid;

    @Attribute(name = "cn")
    private String commonName;

    public PersonEntry() {}
    public Name getDn() { return dn; }
    public void setDn(Name dn) { this.dn = dn; }
    public String getUid() { return uid; }
    public void setUid(String uid) { this.uid = uid; }
    public String getCommonName() { return commonName; }
    public void setCommonName(String commonName) {
        this.commonName = commonName;
    }
}
~~~

Repository:

~~~java
import java.util.List;
import org.springframework.data.ldap.repository.LdapRepository;

public interface PersonRepository extends LdapRepository<PersonEntry> {
    List<PersonEntry> findByUid(String uid);
}
~~~

**findByUid** giúp code gọn và thông thường phù hợp cho truy vấn equality. Tuy nhiên, nếu cần **scope, giới hạn thời gian/số lượng kết quả, attributes projection** khác nhau cho từng use case, cần xem xét **@Query** của Spring Data LDAP hoặc dùng **LdapTemplate** như trên.

Ví dụ với **@Query** (annotation **org.springframework.data.ldap.repository.Query**):

~~~java
import java.util.List;
import org.springframework.data.ldap.repository.LdapRepository;
import org.springframework.data.ldap.repository.Query;
import org.springframework.ldap.query.SearchScope;

public interface PersonRepository extends LdapRepository<PersonEntry> {
    @Query(
        value = "(&(objectClass=inetOrgPerson)(uid={0}))",
        searchScope = SearchScope.SUBTREE,
        countLimit = 20,
        timeLimit = 1500
    )
    List<PersonEntry> findBoundedByUid(String uid);
}
~~~

Giá trị tham số **{0}** được binding theo cơ chế Spring Data LDAP thay vì nối filter thủ công. Mặc dù **countLimit** và **timeLimit** hỗ trợ giảm nguy cơ kéo quá nhiều kết quả, đây vẫn là thao tác truy cập directory và phải kiểm tra kết quả có bị cắt/giới hạn bởi server hay không. Thuộc tính **base** của **@Query** và **@Entry** cần được đối chiếu với ContextSource base để không tìm nhầm phạm vi.

**Không lấy các tính năng JPA làm mặc định của LDAP repository.** Khả năng phân trang/sắp xếp repository LDAP khác JPA; khi cần trả hết tập kết quả lớn có kiểm soát, nghiên cứu LDAP server-side paging hoặc chia truy vấn theo nhánh thay vì suy rằng **Page<PersonEntry>** tự động làm đúng cho LDAP.

## 7. Tối ưu hóa từ filter đến dữ liệu trả về

Một chiến lược tối ưu thường hiệu quả hơn “thêm index cho mọi thuộc tính” là cải tiến có thứ tự:

### 7.1. Chọn search base nhỏ nhất còn đáp ứng nghiệp vụ

Ví dụ API chỉ quản lý nhân sự chính thức thì dùng **ou=employees** thay vì **dc=example,dc=org**, miễn dữ liệu của nhân viên thật sự nằm dưới nhánh đó. Nếu directory chia theo **ou=engineering**, **ou=sales**, ứng dụng có thể truy vấn đúng các nhánh liên quan hoặc tổ chức lại use case.

**Không thu hẹp scope bằng cách làm mất dữ liệu hợp lệ.** Nếu người dùng nằm dưới nhiều OU lồng nhau, ONELEVEL có thể là lỗi chức năng. Trước khi đổi scope, lập bảng kiểm chứng entry nào phải được trả.

### 7.2. Ưu tiên exact match rồi mới mở rộng

Ví dụ trong giao diện tìm nhân sự:

1. Nếu người dùng nhập **mã nhân viên/uid** đúng định dạng, dùng equality theo thuộc tính định danh.
2. Nếu cần tìm theo tên, ưu tiên prefix đủ dài và kết hợp với nhánh hoặc điều kiện khác.
3. Chỉ bật contains search khi thật sự có yêu cầu nghiệp vụ, được giới hạn theo quyền và đã đo trên dữ liệu thực tế.

Tránh logic “nhập bất kỳ một ký tự là gửi **(cn=*a*)** từ gốc toàn directory”. Một request có thể nhỏ, nhưng số request lớn hoặc nhiều khách hàng đồng thời sẽ khuếch đại chi phí.

### 7.3. Kết hợp điều kiện có ích, không dùng filter rộng để trang trí

Ví dụ:

~~~ldap
(&(objectClass=inetOrgPerson)(uid=an))
(&(objectClass=inetOrgPerson)(department=Engineering)(cn=An*))
~~~

Điều kiện kết hợp có thể giảm tập ứng viên nếu các thuộc tính được index và dữ liệu đủ chọn lọc. Tuy nhiên, **objectClass=inetOrgPerson** thường khớp phần lớn user entries nên không nhất thiết đã giúp đáng kể. Nếu **department** không được lập chỉ mục hoặc không được phép đọc, lợi ích có thể khác dự đoán.

**Không cố gắng điều khiển thứ tự thực thi bằng thứ tự viết các toán hạng trong AND**: server có thể tự tối ưu và lựa chọn cách đánh giá, phụ thuộc backend. Hãy dựa vào log/explain/tracing được nhà cung cấp hỗ trợ.

### 7.4. Chỉ trả các thuộc tính cần thiết

Khi client chỉ hiển thị uid, cn và mail, nên trả ba trường đó thay vì yêu cầu tất cả thuộc tính. Với entity lớn, các thuộc tính đa giá trị (ví dụ membership), hình ảnh hoặc binary data, việc trả toàn bộ có thể tăng đáng kể băng thông và chi phí ánh xạ Java.

Nếu dùng ODM repository luôn ánh xạ một entity đầy đủ, cân nhắc projection/DTO hoặc **AttributesMapper** của LdapTemplate cho endpoint danh sách; không tự đưa mỗi người dùng vào một lần lookup bổ sung nếu có thể lấy các thuộc tính cần ngay trong kết quả search. Kiểu **N+1 lookup** cũng tạo nhiều round trip.

### 7.5. Giới hạn kết quả và thời gian

- **countLimit**: bảo vệ khỏi trả số lượng entry không kiểm soát cho một lần search; không bảo đảm total dataset nhỏ.
- **timeLimit**: hạn chế thời gian xử lý search phía server theo API, nhưng không thay cho timeout kết nối.
- **size/time limits của server**: có thể thấp hơn mức client đề nghị. Server có quyền trả lỗi, kết quả một phần hoặc từ chối operation theo chính sách.
- **Rate limiting và concurrency control**: chặn việc nhiều request nặng cùng làm cạn tài nguyên directory.
- **UI/API contract**: phân biệt “tìm thấy tối đa N kết quả” với “đã lấy đầy đủ mọi kết quả”; không báo sai là không có dữ liệu chỉ vì server cắt truy vấn.

## 8. Paging không đồng nghĩa truy vấn rẻ hơn

**LDAP Simple Paged Results Control** (RFC 2696) cho phép client lấy kết quả theo từng trang nếu server hỗ trợ. Spring LDAP cung cấp API/hỗ trợ phân trang ở tầng template, nhưng cần dùng đúng control và duy trì cookie theo phiên truy vấn.

Các điểm phải nhớ:

1. Paging có thể giảm **bộ nhớ phía client** và số entry trả trong mỗi lượt, đồng thời tạo luồng đọc có kiểm soát.
2. Paging **không tự giảm số entry mà server phải xem xét** để trả toàn bộ tập kết quả. Lấy đủ 50 trang vẫn có thể là một truy vấn tổng rất nặng.
3. Paging có **cookie/trạng thái** do server cung cấp; không tự đặt offset SQL rồi coi đó là LDAP paging.
4. Thứ tự kết quả không nhất thiết ổn định nếu không có cơ chế sort phù hợp và dữ liệu đang thay đổi; không dùng số trang làm bằng chứng không có bản ghi trùng/thiếu trong mọi tình huống.
5. LDAP server có thể có giới hạn riêng về kích thước trang, thời gian, tổng số entry, số paged search đồng thời và quyền của tài khoản.
6. Với Active Directory, các giới hạn như **MaxPageSize** và cách trả thuộc tính đa giá trị theo **ranged retrieval** là vấn đề khác; paging danh sách entry không tự lấy đủ toàn bộ giá trị **member** rất lớn.

Paging nên là **một phần của chiến lược xử lý tập dữ liệu lớn đã được phê duyệt**, không phải cách cho phép mọi client tìm **(objectClass=*)** trên toàn directory liên tục.

## 9. Đo đạc hiệu năng thay vì đoán

Một bài kiểm tra hiệu năng đáng tin phải cố định **server**, **dataset**, **cache trạng thái**, **index**, **truy vấn**, **mức đồng thời**, **base/scope**, **attributes** và **TLS/network conditions**. So sánh hai truy vấn trên hai directory khác nhau mà không kiểm soát yếu tố này dễ dẫn tới kết luận sai.

### 9.1. Chỉ số nên theo dõi

| Chỉ số | Câu hỏi nó giúp trả lời |
| --- | --- |
| **p50/p95/p99 latency** | Phần lớn và phần đuôi request chậm đến mức nào? |
| **Số entry thực trả về** | Filter có rộng hơn yêu cầu không? Kết quả có bị cắt? |
| **Số candidate/entry examined** (nếu server cung cấp) | Server phải xem xét bao nhiêu entry để trả kết quả? |
| **Index hit / unindexed search** (nếu server ghi nhận) | Filter có sử dụng index phù hợp không? |
| **CPU/IO/RAM directory server** | Tải hạ tầng tăng ở đâu? |
| **Kích thước response / số thuộc tính** | Chi phí băng thông và mapping client thế nào? |
| **Timeout / sizeLimitExceeded / referrals** | Truy vấn có bị giới hạn hoặc bị phân tán sang server khác? |
| **Tốc độ request và số kết nối đồng thời** | Một query đơn lẻ chấp nhận được có chịu được tải thực tế không? |

**p95** là phân vị độ trễ của các request đo được, không phải một ngưỡng chung áp dụng cho mọi directory. Ví dụ mục tiêu **p95 ≤ 200 ms** chỉ có ý nghĩa nếu được đội dự án xác lập cùng SLA, quy mô dữ liệu và khoảng đo; không dùng một con số giả định để nhận định server đã tối ưu.

### 9.2. Thiết kế bảng so sánh

Thay vì ghi số đo tưởng tượng, lập bảng để điền từ thử nghiệm:

| Filter | Base/scope | Index đã xác minh | Kết quả | p95 | Ghi chú |
| --- | --- | --- | --- | --- | --- |
| **(uid=an)** | people/ONELEVEL | eq(uid) có/không | Đo | Đo | Điểm tham chiếu exact match |
| **(cn=An*)** | people/SUBTREE | sub(cn) có/không | Đo | Đo | Prefix đủ độ dài? |
| **(cn=*an*)** | people/SUBTREE | subany có/không | Đo | Đo | Contains có thể rất rộng |
| **(cn=*)** | people/SUBTREE | pres(cn) có/không | Đo | Đo | Presence chọn lọc thấp? |
| **(uid=an)** | suffix/SUBTREE | eq(uid) có/không | Đo | Đo | Ảnh hưởng mở rộng base |

Mỗi nhóm đo nên chạy nhiều lần, kiểm soát warm-up, thời gian tải và khối lượng đồng thời; không so sánh một request đầu tiên với một request đã được cache. Ghi lại cả những query bị timeout hoặc bị server từ chối, không chỉ các query thành công.

### 9.3. Kiểm tra qua công cụ ldapsearch

Với một directory test cho phép simple bind qua LDAPS:

~~~bash
# Tìm mã người dùng cụ thể, con trực tiếp của ou=people.
ldapsearch -LLL -x -H ldaps://ldap.example.org:636 \
  -D "uid=svc-reader,ou=service-accounts,dc=example,dc=org" -W \
  -b "ou=people,dc=example,dc=org" -s one -z 50 -l 2 \
  "(&(objectClass=inetOrgPerson)(uid=an))" uid cn mail
~~~

~~~bash
# Tìm tiền tố tên trong subtree people, vẫn đặt giới hạn.
ldapsearch -LLL -x -H ldaps://ldap.example.org:636 \
  -D "uid=svc-reader,ou=service-accounts,dc=example,dc=org" -W \
  -b "ou=people,dc=example,dc=org" -s sub -z 50 -l 2 \
  "(&(objectClass=inetOrgPerson)(cn=An*))" uid cn mail
~~~

Trong **ldapsearch**, **-s one/sub** xác định scope, **-z 50** là size limit được client yêu cầu, **-l 2** là time limit tính theo giây của CLI; trong **LdapQueryBuilder.timeLimit(1500)** giá trị là **mili giây**. Đừng copy giá trị thời gian giữa hai API mà không kiểm tra đơn vị.

Sử dụng tài khoản test chỉ có quyền đọc, nhập password qua **-W** và xác minh certificate. Không in hoặc gửi lên log công khai những thông tin LDAP cá nhân, mật khẩu hay các filter chứa dữ liệu nhạy cảm.

### 9.4. Server log và công cụ quản trị

OpenLDAP có thể hỗ trợ log để quan sát search, candidate và chỉ mục không được sử dụng, tùy backend và mức log. AD DS cung cấp sự kiện/chẩn đoán tìm kiếm riêng, gồm các tình huống expensive/inefficient LDAP search tùy cấu hình auditing. Các dấu hiệu này được đánh giá cùng:

- Search base DN, scope và filter đã được chuẩn hóa/ẩn dữ liệu nhạy cảm.
- Index thực sự tồn tại trên backend đó.
- Số entry trả về so với số candidate được server xem xét.
- Độ trễ và concurrency của hệ thống tại thời điểm đo.
- Mức độ ổn định của kết quả khi paging hoặc replication đang diễn ra.

Chỉ bật log chi tiết theo quy trình giám sát được phê duyệt. **Đừng tăng log toàn directory vô thời hạn** vì log search filter và entry DN có thể chứa dữ liệu cá nhân và làm tăng tải hệ thống.

## 10. Các lỗi và phản mẫu hiệu năng thường gặp

| Phản mẫu | Tác động | Cách sửa |
| --- | --- | --- |
| Tìm **(cn=*a*)** ngay sau một ký tự gõ | Rất nhiều candidate và request liên tục | Debounce UI, yêu cầu prefix tối thiểu, giới hạn nhánh và rate |
| Tìm từ **dc=example,dc=org** khi chỉ cần OU người dùng | Scope chứa nhiều nhánh không liên quan | Chọn **ou=people** hoặc base phù hợp |
| Dùng **SUBTREE** mặc định mà không biết dữ liệu đặt ở đâu | Có thể tìm qua nhiều OU lồng nhau | Xác nhận cấu trúc và chọn ONELEVEL nếu hợp lệ |
| Dùng **ONELEVEL** một cách máy móc | Bỏ sót người dùng nằm trong OU lồng nhau | Đối chiếu yêu cầu chức năng trước khi thu hẹp |
| Dùng **(mail=*)** để “tối ưu” search | Presence có thể chọn lọc rất thấp | Dùng điều kiện nghiệp vụ cụ thể hơn |
| Chỉ tăng **countLimit** để tránh lỗi paging | Server/client vẫn phải xử lý lượng lớn dữ liệu | Paging hoặc chia workload, giới hạn tổng công việc |
| Dùng **(objectClass=*)** cho mọi API danh sách | Duyệt gần như toàn cây và trả dữ liệu không liên quan | Giới hạn loại entry, base và attributes |
| Lấy toàn bộ entry rồi filter bằng Java | Tăng network/memory/CPU ứng dụng | Đưa điều kiện hợp lệ vào LDAP search filter |
| Load entity đầy đủ cho danh sách ngắn | Chuyển dữ liệu/thuộc tính không cần thiết | Chỉ trả attributes phục vụ màn hình |
| Thực hiện N lookup bổ sung sau search N người | Tăng round trips LDAP | Trả đủ thuộc tính trong search, cân nhắc batching phù hợp |
| Tạo index cho mọi thuộc tính | Tăng dung lượng và chi phí cập nhật | Chọn index theo query workload đã đo |
| Ghi nhận **0 kết quả** từ một query bị timeout là “không có user” | Sai nghiệp vụ và có thể gây lỗi phân quyền | Phân biệt thành công-rỗng và lỗi/giới hạn |
| Xây filter bằng nối chuỗi và raw wildcard | Nguy cơ LDAP injection và mở rộng phạm vi search | Dùng filter builder, allowlist và giới hạn input |

## 11. Kiểm thử hiệu năng và tính đúng đắn

Nên dùng OpenLDAP hoặc directory tương đương đích với dataset kiểm thử có nhiều entry, OU lồng nhau, tên trùng nhau, phân bố tiền tố thực tế và cấu hình index đã ghi nhận. Nếu môi trường mục tiêu là Active Directory, cần kiểm thử trên AD DS tương đương, vì index, schema, referral, Global Catalog và giới hạn tìm kiếm không giống OpenLDAP.

| Ca kiểm thử | Thao tác | Kỳ vọng |
| --- | --- | --- |
| Equality | Tìm theo uid cụ thể | Trả entry đúng theo scope, không mở rộng filter |
| Prefix | Tìm **cn=An*** với tiền tố đủ dài | Trả đúng prefix, kiểm tra index và số kết quả |
| Contains | Tìm **cn=*an*** trong môi trường có quyền | Quan sát chi phí thực, kết quả được giới hạn |
| Literal wildcard | Tìm chuỗi chứa ký tự **\*** thực sự | Dấu sao được escape, không biến thành wildcard |
| ONELEVEL | Tìm dưới **ou=people** có OU con | Không thấy user ở OU cháu |
| SUBTREE | Cùng filter nhưng dùng SUBTREE | Thấy user ở OU cháu nếu filter khớp và có quyền |
| Narrow base | Chỉ tìm trong OU nghiệp vụ | Không trả entry ngoài OU |
| Wide base | Tìm từ suffix trong test có kiểm soát | So sánh latency/candidate và số entry với narrow base |
| Result limit | Tạo hơn giới hạn kết quả | Ứng dụng xử lý truncation/size limit đúng cách |
| Time limit | Gửi query test nặng có giới hạn | Không coi timeout là kết quả rỗng hợp lệ |
| Permission | Bind account không được đọc một OU | Không lộ dữ liệu ngoài ACL |
| Missing index | Thử trên server test có/không index được quản trị | Ghi nhận khác biệt sau khi kiểm soát cache và tải |
| Concurrent search | Tăng số worker theo kế hoạch test | Đo p95/p99, server load và lỗi giới hạn |
| Multi-valued attr | Entry có nhiều thuộc tính/giá trị lớn | Projection tránh kéo dữ liệu không cần |

### 11.1. Đo code Java không cần biến test thành benchmark thiếu kiểm soát

Một phép đo đơn lẻ bằng **System.nanoTime** giúp điều tra ban đầu:

~~~java
long started = System.nanoTime();
List<PersonSummary> result = peopleSearchService.findByCnPrefix("An");
long elapsedNanos = System.nanoTime() - started;

// Ghi số entry và thời gian, tránh ghi raw PII/LDAP credentials.
System.out.printf(
    "entries=%d, latencyMs=%.2f%n",
    result.size(), elapsedNanos / 1_000_000.0);
~~~

**Không dùng một lần chạy để tuyên bố p95/p99**, không gộp thời gian tạo Spring context vào một phép đo query, và không cho phép kết quả timeout bị tính như lần thành công có 0 entry. Ứng dụng thật nên dùng **Micrometer/observability** hoặc công cụ đo tải tương đương để lấy phân vị từ nhiều request, kết hợp log server và giám sát network.

### 11.2. Giới hạn tải thử nghiệm

- Chạy trên dataset và LDAP server thử nghiệm được cấp quyền, không gửi truy vấn wildcard rộng với tần suất cao vào production.
- Bắt đầu từ tải thấp, tăng dần có giám sát và dừng khi gặp giới hạn/tác động tới các client khác.
- Ghi lại schema, index, server version, dữ liệu seed, base, scope, filter và cỡ request.
- Đo riêng cold cache/warm cache khi cần, không gộp các trạng thái rồi kết luận sai.
- Sau mỗi thay đổi index, xác nhận quá trình xây index hoàn tất trước khi so sánh.

## 12. Checklist thiết kế trước khi đưa một LDAP search lên production

1. **Mục tiêu:** API cần đúng một entry, danh sách nhỏ hay export quy mô lớn?
2. **Định vị:** DN đã biết thì lookup; không biết DN thì chọn base và scope đúng cấu trúc cây.
3. **Filter:** ưu tiên equality/chọn lọc cao; chỉ dùng wildcard theo yêu cầu được phép.
4. **Input:** không nhận raw filter/DN từ người dùng; validation và escape đúng ngữ cảnh.
5. **Index:** hỏi quản trị viên về index/matching rule thật, không đoán từ tên attribute.
6. **Giới hạn:** count/time, timeout mạng, paging nếu cần, rate và concurrency ở API.
7. **Projection:** chỉ lấy các thuộc tính cần thiết; tránh N+1 reads.
8. **Quyền và TLS:** LDAPS/StartTLS với chứng chỉ hợp lệ, bind account quyền tối thiểu.
9. **Tính đúng đắn:** so kết quả ONELEVEL/SUBTREE, dữ liệu lồng OU, duplicates, referrals, pagination và giới hạn server.
10. **Quan sát:** đo p50/p95/p99, số kết quả, lỗi và tác động CPU/IO của directory.

## 13. Tổng kết và bài tập tự luyện

**Wildcard và tìm kiếm toàn cây không tự động đồng nghĩa với truy vấn xấu.** Chúng trở nên tốn kém khi filter chọn lọc thấp, index không phù hợp, base quá rộng, nhiều thuộc tính phải trả hoặc nhiều client gửi truy vấn cùng lúc. Ngược lại, equality index tốt cũng không bảo đảm rẻ nếu filter khớp gần như toàn bộ directory.

Trong **Spring Data LDAP**, **LdapRepository** giúp viết truy vấn thông dụng ngắn gọn; **LdapTemplate/LdapQueryBuilder** cho phép kiểm soát trực tiếp search base, scope, attributes và các giới hạn. Hãy đo trên directory gần với môi trường thật trước khi đổi cấu hình index, bảo đảm các tối ưu không làm mất dữ liệu và không vô hiệu hóa kiểm tra quyền/TLS.

**Bài tập:**

1. Với cây có **ou=people → ou=contractors → uid=chi**, giải thích vì sao **ONELEVEL** không tìm thấy Chi nhưng **SUBTREE** có thể tìm được.
2. So sánh các filter **(uid=an)**, **(cn=An*)**, **(cn=*an*)**, **(cn=*)** theo mức độ chọn lọc dự kiến. Tại sao phải kiểm tra index trước khi kết luận tốc độ?
3. Nếu người dùng muốn tìm chuỗi **An*Tran** với dấu sao là ký tự literal, filter cần escape như thế nào theo RFC 4515?
4. Viết một query LdapTemplate tìm theo prefix **cn**, base **ou=employees**, scope **ONELEVEL**, chỉ trả **uid/cn**, time limit và count limit hữu hạn.
5. Thiết kế benchmark cho ba truy vấn trên cùng dataset: equality, prefix và contains. Cần đo những chỉ số nào và kiểm soát biến số nào?
6. Vì sao **server-side paging** không cho phép bỏ giới hạn số request hoặc bỏ qua chi phí quét directory?
7. Nêu tình huống đổi **SUBTREE** sang **ONELEVEL** khiến kết quả nghiệp vụ sai. Bạn sẽ viết integration test nào để phát hiện?
8. Phân biệt lỗi **LDAP size limit/time limit** với kết quả tìm kiếm rỗng bình thường và cách API nên trả thông báo.

### Tài liệu tham khảo

- [RFC 4515 — LDAP: String Representation of Search Filters](https://www.rfc-editor.org/rfc/rfc4515) — wildcard, equality/presence/substring và escaping.
- [RFC 4511 — LDAP: The Protocol](https://www.rfc-editor.org/rfc/rfc4511) — search base, scope, filter và các kết quả/giới hạn LDAP.
- [RFC 2696 — LDAP Control Extension for Simple Paged Results](https://www.rfc-editor.org/rfc/rfc2696) — server-side paging.
- [Spring LDAP — Advanced LDAP Queries](https://docs.spring.io/spring-ldap/reference/query-builder-advanced.html) — query builder, searchScope, countLimit, timeLimit và like.
- [Spring LDAP — LdapQueryBuilder API](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/query/LdapQueryBuilder.html) — các phương thức xây truy vấn và các mặc định.
- [Spring Data LDAP — Query annotation API](https://docs.spring.io/spring-data/ldap/reference/api/java/org/springframework/data/ldap/repository/Query.html) — filter binding, scope và giới hạn repository query.
- [OpenLDAP 2.6 Administrator's Guide — Indexing and Tuning](https://project.openldap.org/doc/admin26/guide.html) — equality/presence/substring index và đánh đổi hiệu năng.
