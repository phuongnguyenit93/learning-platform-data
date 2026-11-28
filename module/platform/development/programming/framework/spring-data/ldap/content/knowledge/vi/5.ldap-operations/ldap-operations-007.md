# Giới hạn thời gian, số lượng kết quả và quyền truy cập

Một chức năng tra cứu danh bạ có thể chỉ cần tìm một nhân viên theo `uid`, nhưng nếu search được phép quét toàn bộ cây LDAP và trả tất cả thuộc tính, một request sai hoặc bị lạm dụng có thể tiêu tốn nhiều tài nguyên, bị LDAP server cắt kết quả, thậm chí làm lộ các entry mà người gọi HTTP không được phép xem. Đặt mỗi một `countLimit(100)` rồi kết luận “an toàn” là chưa đủ: truy vấn vẫn có thể chạy chậm, vượt quyền nghiệp vụ hoặc bị cắt mất dữ liệu mà ứng dụng không nhận ra.

Trong chương **Thao tác LDAP** của module **SPRING_DATA_LDAP**, bài này đi sâu vào ba nhóm giới hạn thường phải phối hợp: **thời gian thực thi**, **số lượng kết quả**, và **quyền truy cập**. Ứng dụng Java dùng `LdapTemplate` hoặc repository để truy vấn entry phân cấp theo DN, `objectClass` và schema; các tham số tìm kiếm phải phù hợp với **giới hạn directory server**, **nguồn lực Spring Boot** và **ủy quyền của người gọi**. Nội dung cũng đề cập filter an toàn, LDAPS, cách xử lý kết quả không đầy đủ và kiểm thử với directory thực tế.

**Luận điểm chính:** Không có một tham số duy nhất vừa chặn truy vấn chậm, vừa bảo đảm kết quả đầy đủ, vừa thực thi phân quyền. Các giới hạn được đặt ở **nhiều tầng** và phục vụ **mục đích khác nhau**.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt `LdapQueryBuilder.timeLimit(...)`, `countLimit(...)`, `SearchControls`, JNDI connect/read timeout và giới hạn của LDAP server.
2. Cấu hình **search base, scope, filter, thuộc tính trả về, thời gian và số lượng** để giới hạn một truy vấn bằng `LdapTemplate`.
3. Hiểu vì sao “nhận 50 entry” chưa chứng minh directory chỉ có 50 entry.
4. Phân biệt **giới hạn kết quả một truy vấn** với **phân trang RFC 2696** khi cần đọc đủ tập dữ liệu lớn.
5. Phân biệt quyền của **người gọi HTTP**, **service/bind account** và **ACL của LDAP server**.
6. Xử lý đúng tình huống timeout, size limit, admin limit, thiếu ACL, base không tồn tại và partial results.
7. Viết unit test/integration test kiểm chứng các giới hạn, đặc biệt với input có ký tự đặc biệt và những trường hợp dữ liệu vượt ngưỡng.

## 2. Bản đồ các giới hạn trong một LDAP search

Hãy theo dõi một request: người dùng muốn tìm nhân viên thuộc bộ phận Engineering. Ứng dụng dùng tài khoản dịch vụ để tìm kiếm directory.

~~~mermaid
flowchart TD
    A["HTTP client"] --> B["Spring Security<br/>authentication + authorization"]
    B --> C["Service<br/>validate input + rate limit"]
    C --> D["LdapQueryBuilder / LdapTemplate<br/>base, scope, filter, attributes"]
    D --> E["Query limits<br/>countLimit + timeLimit"]
    E --> F["ContextSource / JNDI<br/>connect + read timeout, TLS"]
    F --> G["LDAP server<br/>bind ACL + schema + search policy"]
    G --> H["Entries hoặc LDAP result/error"]
    H --> I["Mapper + xử lý kết quả<br/>đầy đủ hay bị giới hạn?"]
~~~

Các tầng này không thay thế nhau:

| Tầng | Ví dụ biện pháp | Bảo vệ điều gì? |
| --- | --- | --- |
| HTTP / Spring Security | `@PreAuthorize`, phân quyền theo OU, tenant hoặc người sở hữu hồ sơ. | Ngăn caller không đủ quyền sử dụng API/dữ liệu. |
| Service | Validation, allowlist, rate limit, giới hạn số yêu cầu đồng thời. | Ngăn truy vấn tùy ý, tránh lạm dụng từ client. |
| LDAP query | `base`, `scope`, `filter`, `attributes`, `countLimit`, `timeLimit`. | Thu hẹp tìm kiếm và yêu cầu tài nguyên cho mỗi search. |
| JNDI / mạng | Connect/read timeout, TLS, kiểm tra chứng chỉ. | Hạn chế chờ kết nối/đọc và bảo vệ credential/dữ liệu trên đường truyền. |
| Directory server | Search size/time/admin limits, ACL, schema, quota. | Thực thi giới hạn và quyền trên nguồn dữ liệu. |
| Downstream | Deadline toàn request/job, bounded queue/batch, memory budget. | Tránh chiếm thread, heap, connection hoặc ghi dữ liệu lỗi. |

**Phân biệt:** Spring Security quyết định **người gọi ứng dụng** có quyền gì; LDAP ACL quyết định **danh tính đang bind với directory** được phép đọc/ghi entry nào. Khi service sử dụng một bind account có quyền đọc rộng, ứng dụng phải tự thực thi giới hạn nghiệp vụ nghiêm ngặt hơn quyền mà account kỹ thuật có.

## 3. Ba tham số đầu tiên cần quyết định: base, scope, filter

Giới hạn số kết quả và thời gian chỉ hiệu quả khi search có **phạm vi đúng**. Một query quét từ root directory có thể phải xem xét nhiều entry trước khi tìm ra vài kết quả phù hợp.

Giả sử directory test:

~~~text
dc=example,dc=org
├── ou=people
│   ├── uid=lan              objectClass=inetOrgPerson
│   ├── uid=minh             objectClass=inetOrgPerson
│   └── ou=contractors
│       └── uid=an          objectClass=inetOrgPerson
├── ou=groups
│   └── cn=developers
└── ou=services
    └── cn=app-reader
~~~

| Tham số | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| **Context base** | `dc=example,dc=org` | Gốc được cấu hình tại `ContextSource`. |
| **Search base** | `ou=people` | Nhánh tương đối với context base. |
| **OBJECT scope** | Chính `ou=people`. | Kiểm tra đúng entry của base. |
| **ONELEVEL scope** | Các entry con trực tiếp của `ou=people`. | Không tìm `uid=an` nằm dưới `ou=contractors`. |
| **SUBTREE scope** | Base và tất cả entry bên dưới. | Có thể bao gồm user ở các OU con. |
| **Filter** | `(&(objectClass=inetOrgPerson)(uid=lan))` | Chỉ những entry phù hợp điều kiện. |
| **Returning attributes** | `uid`, `cn`, `mail`. | Chỉ yêu cầu những trường cần để trả DTO. |

**Tùy use case, chọn scope hẹp nhất đúng nghiệp vụ.** Nếu hệ thống chắc chắn tất cả nhân viên nằm trực tiếp dưới `ou=people`, ONELEVEL có thể phù hợp hơn SUBTREE. Nếu cần cả contractor ở OU con, phải mở rộng scope **có chủ đích** và kiểm soát ACL/authorization theo chính sách.

### 3.1. Filter an toàn là điều kiện bắt buộc

Không xây filter bằng chuỗi ghép từ input HTTP:

~~~java
// KHÔNG AN TOÀN:
String filter = "(&(objectClass=inetOrgPerson)(uid="
        + requestedUid + "))";
~~~

Thay bằng builder:

~~~java
LdapQuery query = LdapQueryBuilder.query()
        .base("ou=people")
        .where("objectClass").is("inetOrgPerson")
        .and("uid").is(requestedUid);
~~~

`.is(requestedUid)` xử lý escape **giá trị filter** phù hợp cú pháp LDAP; không tự dùng `replace("*", ...)` hoặc cho user đưa nguyên filter vào API. Tuy nhiên builder **không tự kiểm tra** caller có được chọn tên attribute, base DN hoặc search scope tùy ý hay không. Ba yếu tố đó cần do server/service chọn từ một tập cho phép.

## 4. Giới hạn số lượng kết quả: `countLimit`

Spring LDAP có `LdapQueryBuilder.countLimit(int)` để đặt giới hạn số entry của một search.

~~~java
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;
import org.springframework.ldap.query.SearchScope;

LdapQuery query = LdapQueryBuilder.query()
        .base("ou=people")
        .searchScope(SearchScope.SUBTREE)
        .attributes("uid", "cn", "mail")
        .countLimit(50)
        .where("objectClass").is("inetOrgPerson");
~~~

Khi search được thực thi, `50` là giới hạn số entry **được yêu cầu cho lần search đó**. Nếu directory có 3.000 người, API không vì thế tự tạo 60 lần truy vấn để lấy hết 3.000.

### 4.1. Count limit ≠ tổng số entry phù hợp

Giả sử ứng dụng nhận 50 kết quả:

| Kết quả trả về | Có thể kết luận điều gì? | Không thể kết luận điều gì? |
| --- | --- | --- |
| 0 entry, không lỗi. | Không có entry nào được trả trong **phạm vi, quyền và điều kiện hiện tại**. | User chắc chắn không tồn tại ở toàn directory. |
| 23 entry, không lỗi. | Client nhận 23 entry trong lần tìm kiếm. | Không có bất kỳ entry nào bị ẩn bởi ACL hoặc giới hạn khác. |
| Đúng 50 entry. | Đã đạt ngưỡng client yêu cầu. | Tập dữ liệu chắc chắn chỉ có 50 entry. |
| LDAP báo `sizeLimitExceeded`. | Server không hoàn thành search theo giới hạn kích thước. | Có thể dùng dữ liệu trả trước lỗi như một danh bạ đầy đủ. |
| LDAP báo `adminLimitExceeded`. | Policy/quota máy chủ không cho thực hiện đầy đủ truy vấn. | Giới hạn app đủ để tránh mọi chính sách admin. |

Tùy server và API, chạm ngưỡng có thể trả lỗi hoặc chỉ trả một số entry. Với chức năng **tra cứu tối đa 50 gợi ý**, kết quả bị giới hạn là chấp nhận được nếu hợp đồng API nói rõ. Nhưng với **đồng bộ toàn bộ nhân sự**, không được tuyên bố quét hoàn tất chỉ vì hàm `search` trả một danh sách có kích thước 50.

### 4.2. Khi `countLimit(2)` hợp lý hơn `countLimit(1)`

Nếu mục tiêu là tìm **duy nhất một** entry theo `uid`, đừng luôn chọn giới hạn 1 rồi lấy phần tử đầu tiên. Trong directory có thể tồn tại nhiều entry trùng username ở các OU; giới hạn 1 làm bạn không phát hiện tình trạng định danh nhập nhằng.

~~~java
LdapQuery query = LdapQueryBuilder.query()
        .base("ou=people")
        .attributes("uid", "cn")
        .countLimit(2)
        .where("objectClass").is("inetOrgPerson")
        .and("uid").is(uid);

// 0 kết quả: không tìm được trong phạm vi/trạng thái quyền hiện tại.
// 1 kết quả: phù hợp kỳ vọng một entry.
// >=2 kết quả: vấn đề tính duy nhất cần xử lý, không chọn bừa.
~~~

**Lưu ý:** `countLimit(2)` chỉ giúp phát hiện việc nhận được nhiều kết quả; nó không bảo đảm mọi entry ở nơi khác ngoài base/scope đều đã được kiểm tra. Cần một chính sách định danh duy nhất trong vùng được cấp quyền và dữ liệu/scheme quản trị đáng tin cậy.

### 4.3. Giá trị mặc định `0` không có nghĩa server không có giới hạn

Theo API Spring LDAP, count limit mặc định có thể là `0`, nghĩa là **không yêu cầu giới hạn từ phía client**. Điều đó **không vô hiệu hóa** `MaxPageSize`, `sizelimit`, ACL hoặc quota do directory/proxy áp đặt. Không đặt `countLimit(0)` để “né” lỗi server size limit.

## 5. Giới hạn thời gian search: `timeLimit`

`LdapQueryBuilder.timeLimit(int)` cho phép đặt time limit **tính bằng mili giây theo API Spring LDAP/JNDI**. Ví dụ:

~~~java
LdapQuery query = LdapQueryBuilder.query()
        .base("ou=people")
        .searchScope(SearchScope.SUBTREE)
        .attributes("uid", "cn", "mail")
        .countLimit(50)
        .timeLimit(2000)
        .where("objectClass").is("inetOrgPerson")
        .and("ou").is("Engineering");
~~~

`timeLimit(2000)` nghĩa là yêu cầu giới hạn search khoảng **2 giây**, không phải 2.000 giây. JNDI/provider và LDAP protocol có thể biểu diễn thời gian theo độ phân giải khác nhau; server có thể thực thi giới hạn theo chính sách riêng. **Đây không phải deadline end-to-end chính xác 2 giây cho cả HTTP request**.

### 5.1. Search time limit khác connection timeout

Trong một request, có nhiều giai đoạn:

~~~text
HTTP authentication/authorization
       |
       v
Chờ tài nguyên / lấy LDAP context
       |
       +-- Mở TCP/TLS, bind service account
       |
       +-- Search ở LDAP server
       |
       +-- Đọc kết quả / network response
       |
       +-- Map entries sang Java DTO
       |
       +-- Xử lý nghiệp vụ / gọi database khác
       |
       v
HTTP response
~~~

| Giới hạn | Cấu hình điển hình | Đo lường / tác động |
| --- | --- | --- |
| **LDAP search time limit** | `.timeLimit(2000)` hoặc `SearchControls.setTimeLimit(2000)`. | Yêu cầu giới hạn tìm kiếm cho một LDAP search; không bao trùm toàn bộ pipeline. |
| **JNDI connect timeout** | `com.sun.jndi.ldap.connect.timeout=3000`. | Giới hạn chờ thiết lập kết nối của JNDI LDAP provider. |
| **JNDI read timeout** | `com.sun.jndi.ldap.read.timeout=5000`. | Giới hạn chờ phản hồi/đọc từ LDAP theo provider. |
| **HTTP / job deadline** | Chính sách ứng dụng, gateway hoặc scheduler. | Ngân sách thời gian cho toàn request/job, gồm map và xử lý downstream. |
| **Server search time limit** | Policy của LDAP server hoặc tài khoản bind. | Có thể áp ngưỡng thấp hơn hoặc xử lý time limit theo cách riêng. |

Nếu TCP/TLS handshake mất nhiều thời gian, `timeLimit(2000)` không thay connect timeout. Nếu server trả nhanh nhưng application mapper xử lý dữ liệu lớn, nó cũng không giới hạn tự động toàn bộ thời gian xử lý Java.

### 5.2. Cấu hình JNDI timeout trong Spring Boot

Gradle Kotlin DSL:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-ldap")
    implementation("org.springframework.boot:spring-boot-starter-security")
}
~~~

`application.yml`:

~~~yaml
spring:
  ldap:
    urls: ${LDAP_URL:ldaps://ldap.example.org:636}
    base: ${LDAP_BASE_DN:dc=example,dc=org}
    username: ${LDAP_BIND_DN}
    password: ${LDAP_BIND_PASSWORD}
    base-environment:
      "com.sun.jndi.ldap.connect.timeout": "3000"
      "com.sun.jndi.ldap.read.timeout": "5000"
~~~

Đây là các thuộc tính môi trường **JNDI LDAP provider của JVM**, không phải option dành cho mọi LDAP library. Spring Boot bind vào `spring.ldap.base-environment` để đưa vào LDAP context khi cấu hình tương thích. Nếu ứng dụng tự định nghĩa `LdapContextSource`, phải đảm bảo custom bean nhận những thuộc tính cần thiết.

**Cẩn thận với TLS:** `ldaps://` cần CA/truststore và hostname hợp lệ. Không tắt xác minh chứng chỉ để “khắc phục timeout”. Nếu dùng `ldap://` với StartTLS, việc nâng cấp kết nối cần được cấu hình tường minh và kiểm chứng.

### 5.3. Time limit ≠ retry vô hạn

Khi search bị timeout hoặc directory trả `timeLimitExceeded`, đừng lập tức retry nhiều lần cùng query nặng. Việc đó có thể nhân tải lên server đang quá sức. Hãy:

1. Phân biệt lỗi mạng, bind, TLS, server time limit và một kết quả search rỗng hợp lệ.
2. Kiểm tra filter/index/base/scope để giảm chi phí truy vấn.
3. Dùng retry có giới hạn, backoff/jitter nếu đây là lỗi tạm thời và việc retry đọc là phù hợp.
4. Áp tổng deadline cho HTTP/job, giữ quota và concurrency rõ ràng.
5. Ghi nhận lỗi để người vận hành thấy query **chưa hoàn tất**, không trả `[]` như thể không có dữ liệu.

## 6. Ví dụ truy vấn có giới hạn bằng `LdapTemplate`

Giả sử API danh bạ trả tối đa 50 người cho một truy vấn tìm kiếm trong `ou=people`. Service phải bảo đảm caller có quyền dùng API, input hợp lệ và giới hạn vẫn do server/application quyết định.

### 6.1. DTO và query builder

~~~java
public record PersonView(
        String uid, String displayName, String email) {
}
~~~

~~~java
import java.util.List;
import javax.naming.NamingException;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;
import org.springframework.ldap.query.SearchScope;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class BoundedDirectorySearchService {
    private final LdapTemplate ldapTemplate;

    public BoundedDirectorySearchService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    @PreAuthorize("hasAuthority('DIRECTORY_READ')")
    public List<PersonView> searchByUid(String uid) {
        if (uid == null || uid.isBlank() || uid.length() > 128) {
            throw new IllegalArgumentException("uid khong hop le");
        }

        LdapQuery query = LdapQueryBuilder.query()
                .base("ou=people")
                .searchScope(SearchScope.SUBTREE)
                .attributes("uid", "cn", "mail")
                .countLimit(50)
                .timeLimit(2000)
                .where("objectClass").is("inetOrgPerson")
                .and("uid").is(uid);

        return ldapTemplate.search(
                query,
                (AttributesMapper<PersonView>) attrs ->
                        new PersonView(
                                optionalText(attrs, "uid"),
                                optionalText(attrs, "cn"),
                                optionalText(attrs, "mail")));
    }

    private static String optionalText(
            Attributes attrs, String name) throws NamingException {
        Attribute attr = attrs.get(name);
        return attr == null ? null : attr.get().toString();
    }
}
~~~

**Giải thích từng lớp bảo vệ:**

1. `@PreAuthorize` kiểm tra authority HTTP trước khi service thực hiện query. Ứng dụng phải bật method security bằng `@EnableMethodSecurity`; kiểm tra này không thay authorization theo từng hồ sơ nếu nghiệp vụ có ownership/tenant.
2. Validation giới hạn kích thước input; đây là **hạn chế tài nguyên**, không thay escaping.
3. `base("ou=people")` chỉ tìm trong nhánh danh bạ. Với context base `dc=example,dc=org`, DN đầy đủ là `ou=people,dc=example,dc=org`.
4. `searchScope(SUBTREE)` có thể tìm trong các OU con. Nếu chỉ cần cấp trực tiếp, dùng `ONELEVEL`.
5. `attributes(...)` không đọc mọi attribute, nhất là các trường nhạy cảm hoặc kích thước lớn.
6. `countLimit(50)` đặt giới hạn số entry, `timeLimit(2000)` đặt giới hạn search khoảng 2 giây.
7. `where(...).is(uid)` escape giá trị filter; nếu uid có ký tự đặc biệt, không biến nó thành toán tử LDAP.
8. `LdapTemplate` lấy context từ `ContextSource`. ACL của bind account vẫn quyết định những entry/attribute nào được phép trả.

Đoạn code cố ý sử dụng `String`/DTO thay vì trả toàn bộ entry ra HTTP. `optionalText` xử lý trường thiếu do projection/schema/ACL; trong ứng dụng thật phải quyết định rõ trường nào bắt buộc, trường nào được null và có nên báo lỗi dữ liệu nếu thiếu `uid`.

### 6.2. Kích hoạt method security

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class DirectoryMethodSecurityConfiguration {
}
~~~

Để annotation `@PreAuthorize` thực sự có hiệu lực, service cần được gọi qua Spring-managed proxy và có Spring Security được cấu hình xác thực request/authority. Một lời gọi nội bộ trong cùng class có thể bỏ qua interceptor. Tài khoản HTTP có authority `DIRECTORY_READ` vẫn cần kiểm tra phạm vi dữ liệu được phép đọc theo chính sách ứng dụng.

### 6.3. Search theo username và yêu cầu duy nhất

Ví dụ trên giới hạn 50 để phục vụ một chức năng gợi ý. Nếu nghiệp vụ là **xác định đúng một danh tính**, nên chọn thiết kế chặt hơn:

~~~java
LdapQuery identityQuery = LdapQueryBuilder.query()
        .base("ou=people")
        .attributes("uid", "cn")
        .countLimit(2)
        .timeLimit(2000)
        .where("objectClass").is("inetOrgPerson")
        .and("uid").is(uid);
~~~

Nhận 2 entry phải được xử lý như lỗi **định danh không duy nhất** trong vùng tìm, không tùy tiện chọn bản ghi đầu tiên. Nhận 0 entry chỉ chứng minh truy vấn không trả kết quả trong phạm vi và ACL hiện tại; nếu LDAP xảy ra lỗi giới hạn/thời gian thì đó là một tình huống hoàn toàn khác.

## 7. Cách khác: dùng `SearchControls` trực tiếp

Đối với các API `LdapTemplate.search(...)` truyền filter và controls tường minh, JNDI `SearchControls` cho phép đặt cùng những giới hạn:

~~~java
import java.util.List;
import javax.naming.NamingException;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;
import javax.naming.directory.SearchControls;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.filter.AndFilter;
import org.springframework.ldap.filter.EqualsFilter;

public List<PersonView> lookupWithControls(
        LdapTemplate ldapTemplate, String uid) {
    if (uid == null || uid.isBlank() || uid.length() > 128) {
        throw new IllegalArgumentException("uid khong hop le");
    }

    SearchControls controls = new SearchControls();
    controls.setSearchScope(SearchControls.ONELEVEL_SCOPE);
    controls.setReturningAttributes(new String[] {"uid", "cn", "mail"});
    controls.setCountLimit(50L);
    controls.setTimeLimit(2000); // mili giây

    AndFilter filter = new AndFilter();
    filter.and(new EqualsFilter("objectClass", "inetOrgPerson"));
    filter.and(new EqualsFilter("uid", uid));

    return ldapTemplate.search(
            "ou=people",
            filter.encode(),
            controls,
            (AttributesMapper<PersonView>) attrs ->
                    new PersonView(
                            stringOrNull(attrs, "uid"),
                            stringOrNull(attrs, "cn"),
                            stringOrNull(attrs, "mail")));
}

private static String stringOrNull(Attributes attrs, String name)
        throws NamingException {
    Attribute attr = attrs.get(name);
    return attr == null ? null : attr.get().toString();
}
~~~

Hai phương thức trên được đặt trong cùng một class service sử dụng `PersonView` đã định nghĩa ở mục 6.1; đoạn này minh họa **API của `SearchControls`**, không phải một service hoàn chỉnh khác.

| `LdapQueryBuilder` | `SearchControls` | Chú ý |
| --- | --- | --- |
| `.searchScope(SearchScope.ONELEVEL)` | `setSearchScope(SearchControls.ONELEVEL_SCOPE)` | Cùng mục đích giới hạn độ sâu search. |
| `.attributes("uid", "cn")` | `setReturningAttributes(new String[]{"uid","cn"})` | Chỉ yêu cầu thuộc tính cần thiết. |
| `.countLimit(50)` | `setCountLimit(50L)` | Giới hạn số entry trả về trong search. |
| `.timeLimit(2000)` | `setTimeLimit(2000)` | Đơn vị API là mili giây. |
| `.where("uid").is(uid)` | `new EqualsFilter("uid", uid)` rồi `encode()` | Cần escape **giá trị filter** đúng ngữ cảnh. |

Đừng ghép filter bằng `"(uid=" + uid + ")"` chỉ vì đang dùng overload `search(String, String, ...)`; `filter.encode()` từ builder giúp giữ cấu trúc filter cố định và escape giá trị.

## 8. Query limit mặc định, giới hạn riêng từng chức năng

`LdapTemplate` có các cấu hình mặc định như `setDefaultCountLimit(...)`, `setDefaultTimeLimit(...)` và `setDefaultSearchScope(...)`. Chúng hữu ích khi một ứng dụng có nhiều search cùng chính sách cơ sở, nhưng **không thay thế giới hạn của từng use case**.

~~~java
// Ví dụ minh họa khi tự cấu hình LdapTemplate:
LdapTemplate template = new LdapTemplate(contextSource);
template.setDefaultCountLimit(100);
template.setDefaultTimeLimit(3000); // milliseconds
template.setDefaultSearchScope(SearchControls.SUBTREE_SCOPE);
~~~

Ví dụ này nằm trong một hàm/bean đã có `contextSource` và import `LdapTemplate`/`SearchControls` phù hợp. Một `LdapQuery` chỉ rõ `countLimit(20)` và `timeLimit(1000)` thường sẽ sử dụng giá trị cụ thể đó thay vì defaults của template.

### 8.1. Chọn giới hạn theo nghiệp vụ

| Chức năng | Ví dụ giới hạn | Tại sao? |
| --- | --- | --- |
| Tra một username duy nhất | `countLimit(2)`, time limit ngắn. | Có thể phát hiện nhiều kết quả bất thường. |
| Gợi ý 20 tên trong autocomplete | `countLimit(20)`, projection nhỏ, rate limit. | Tối ưu phản hồi và không tải cả danh bạ. |
| Danh sách một nhóm nhân sự | `countLimit(100)` hoặc paged API. | Phù hợp UI chỉ xem một trang; cần ghi rõ có thể còn kết quả. |
| Đồng bộ danh bạ lớn | Paging RFC 2696, page size có giới hạn, deadline toàn job. | Cần đọc đủ dữ liệu qua nhiều lần search và kiểm soát bộ nhớ. |
| Tra cứu nhóm/authority lúc đăng nhập | Base hẹp, filter đúng schema, giới hạn thời gian và kết quả phù hợp. | Tránh quá tải authentication, không tự bỏ group khi LDAP lỗi. |
| Chức năng quản trị sửa một entry | Biết DN và gọi API update/modify tường minh. | `countLimit` của search không tự giới hạn thao tác ghi. |

Các ngưỡng chỉ là **ví dụ thiết kế**, không phải cấu hình chuẩn của Spring Data LDAP hay directory. Phải đo SLA, chính sách server, kích thước entry và kỳ vọng dữ liệu của ứng dụng.

## 9. Quyền truy cập: application authorization và LDAP ACL

Một query được giới hạn còn 50 entry và 2 giây **vẫn có thể trái chính sách bảo mật** nếu người gọi không được xem các entry đó.

### 9.1. Hai danh tính trong cùng một request

~~~text
Caller HTTP:  principal = "lan"
                |
                v
Spring Security: lan có role DIRECTORY_READ?
                |
                v
Service: lan được phép xem OU nào, thuộc tenant nào?
                |
                v
LdapTemplate / Repository
                |
                v
LDAP bind identity:
  cn=app-reader,ou=services,dc=example,dc=org
                |
                v
LDAP ACL: tài khoản app-reader được phép đọc gì?
~~~

Nếu `app-reader` được đọc tất cả phòng ban, kết quả `LdapTemplate.search` có thể chứa hồ sơ mà Lan **không được phép** xem theo chính sách của doanh nghiệp. Spring Security hoặc service phải kiểm tra phạm vi dữ liệu trước khi trả DTO. Không xem LDAP ACL của service account như sự thay thế cho authorization của caller HTTP.

Ngược lại, Lan có role `DIRECTORY_READ` ở ứng dụng nhưng `app-reader` chỉ được tìm trong `ou=people` và không được đọc `mail`: directory có thể từ chối, ẩn hoặc không trả thuộc tính. Không nâng quyền LDAP chỉ vì HTTP role hợp lệ.

### 9.2. Thiết kế tài khoản bind theo nguyên tắc ít quyền nhất

Đối với **search danh bạ**:

- Dùng tài khoản kỹ thuật **chỉ đọc**, có quyền bind/search/read ở OU cần thiết.
- Chỉ cho quyền đọc các attribute mà chức năng phải trả: `uid`, `cn`, `mail` khi phù hợp.
- Không yêu cầu đọc `userPassword` chỉ để phục vụ tìm tên nhân viên.
- Không trao quyền tạo, xóa, đổi nhóm, sửa password hoặc quản trị directory nếu API chỉ search.
- Nếu Spring Security dùng LDAP để đăng nhập, có thể có **auth search account** riêng với **data reader account**, bởi phạm vi/user/group và quyền nghiệp vụ khác nhau.
- Luân chuyển secret, giám sát LDAP bind lỗi và tránh in DN/credential nhạy cảm trong log.

### 9.3. Dấu hiệu “không tìm thấy” không đồng nghĩa “không tồn tại”

Một directory có thể thực thi ACL bằng cách không cho thấy entry/attribute hoặc trả lỗi `insufficientAccessRights`. Nếu search với tài khoản A trả 0 entry còn tài khoản B trả 1 entry, vấn đề có thể là **quyền**, không phải do filter. Ngoài ra, search base, scope, replica, referrals và trạng thái đồng bộ cũng ảnh hưởng kết quả.

Vì vậy, logic như sau là sai:

~~~java
// PHẢN VÍ DỤ: query trả empty rồi kết luận user không tồn tại toàn hệ thống.
if (ldapTemplate.search(query, mapper).isEmpty()) {
    deleteAccountFromApplication(uid);
}
~~~

Nếu đây là job đồng bộ, phải có dữ liệu định danh ổn định, full scan hoàn chỉnh và chính sách đối soát; không xóa tài khoản vì một search riêng trả rỗng.

## 10. LDAP server vẫn có quyền áp giới hạn chặt hơn

Các tham số phía client chỉ là một phần của hợp đồng. Directory có thể áp:

| Cơ chế phía server | Tác động | Điều cần làm ở client |
| --- | --- | --- |
| **Size limit** | Giới hạn số entry, có thể trả `sizeLimitExceeded` (LDAP result code 4). | Xem scan không hoàn chỉnh; thu hẹp query hoặc dùng paging nếu cần toàn bộ. |
| **Time limit** | Server ngừng search quá lâu, `timeLimitExceeded` (code 3). | Điều tra filter/index/tải, không biến lỗi thành `[]`. |
| **Admin limit** | Giới hạn tài nguyên/quota khác, `adminLimitExceeded` (code 11). | Điều chỉnh query theo policy, không cố retry liên tục. |
| **Access control** | `insufficientAccessRights` (code 50) hoặc ẩn entry. | Kiểm tra bind identity, quyền search/read, không nâng quyền tùy tiện. |
| **Invalid credentials** | `invalidCredentials` (code 49) khi bind. | Xác minh secret/tài khoản đúng, không coi là user không tồn tại. |
| **No such object** | `noSuchObject` (code 32) cho base/DN không tồn tại. | Kiểm tra context base, DN tương đối, OU/replica. |
| **Referral/partial results** | Kết quả ở nhánh/server khác hoặc chưa đầy đủ. | Chính sách referral rõ, không âm thầm bỏ qua rồi công nhận đầy đủ. |
| **Server/proxy rate limit** | Giảm tốc hoặc từ chối request dồn dập. | Hạn chế concurrency và retry có backoff. |

**Không có một mức giới hạn thống nhất cho mọi server.** Microsoft Active Directory, OpenLDAP và các LDAP proxy có chính sách khác nhau. Tên tham số như `MaxPageSize` hoặc `sizelimit` cũng khác theo hệ thống và không nhất thiết tương ứng trực tiếp với `countLimit` của client.

### 10.1. Partial results phải được coi là trạng thái riêng

Khi server dừng ở giữa search vì time/size/admin limit, có thể đã gửi một số entry trước khi báo lỗi. Tùy API và exception handling, ứng dụng có thể thấy dữ liệu partial hoặc chỉ thấy exception.

Hãy phân biệt:

- **COMPLETE:** truy vấn kết thúc bình thường đúng theo phạm vi/hợp đồng; nếu business muốn “lấy tối đa 20 gợi ý”, không khẳng định danh bạ chỉ có 20.
- **LIMITED:** ứng dụng chủ đích chỉ lấy một tập con, ví dụ top 20 suggestions.
- **PARTIAL/FAILED:** search bị lỗi, cắt theo server policy, timeout, kết nối mất hoặc referral chưa xử lý.

**Đừng cấu hình bỏ qua exception một cách đại trà** rồi dùng dữ liệu partial như hoàn chỉnh. `LdapTemplate` có các tùy chọn liên quan `NameNotFoundException`, `PartialResultException` và `SizeLimitExceededException`; nếu có cấu hình ignore, phải hiểu rõ dữ liệu mất đi và bảo đảm API không khai báo sai tính đầy đủ.

## 11. Phân trang RFC 2696 khi cần đọc đủ danh bạ

`countLimit(100)` chỉ giới hạn một search. Nếu nghiệp vụ cần **đọc toàn bộ 20.000 nhân viên** để đối soát, phải dùng một chiến lược đầy đủ, thường là **LDAP Simple Paged Results** (RFC 2696) nếu server hỗ trợ.

~~~text
Request 1: pageSize=250, cookie=empty -> <=250 entries + cookie A
Request 2: pageSize=250, cookie=A     -> <=250 entries + cookie B
...
Last response: entries + cookie kết thúc
~~~

Các nguyên tắc:

1. Kiểm tra LDAP server hỗ trợ paging control OID `1.2.840.113556.1.4.319`.
2. Đặt **page size riêng**, không nhầm với kết quả `countLimit` hoặc batch size database.
3. Sử dụng processor của Spring LDAP phù hợp phiên bản; một số version có `PagedResultsControlExchangeDirContextProcessor`, version cũ có `PagedResultsDirContextProcessor`.
4. Giữ cùng LDAP connection trong chuỗi truy vấn, ví dụ `SingleContextSource` theo hướng dẫn Spring LDAP; cookie có thể gắn với server/session.
5. Kết thúc theo response cookie/processor, **không** theo `page.size() < pageSize`.
6. Đặt giới hạn tổng thời gian job, max pages, concurrency, rate limit và projection nhỏ.
7. **Không coi paging là snapshot nhất quán**: entry có thể thay đổi giữa các trang; cần chiến lược reconciliation nếu đồng bộ dữ liệu.
8. Không coi một scan bị lỗi giữa chừng là “toàn bộ người dùng”, và không hard-delete account dựa trên kết quả partial.

Phân trang vẫn chịu **ACL, search base, filter, server policy và TLS**. Nó không mở quyền truy cập directory hay tự bỏ size/admin limits của server.

## 12. Timeout cho các thao tác không phải search

Lỗi thường gặp là chỉ cấu hình `timeLimit(...)` trên `LdapQuery` rồi cho rằng **mọi** LDAP operation đều có deadline.

| Thao tác | API thường gặp | Giới hạn nào cần xem xét? |
| --- | --- | --- |
| Search nhiều entry | `LdapTemplate.search(...)`, repository finder. | Search time/count limit, scope, attributes, server policy, read timeout. |
| Lookup một DN | `LdapTemplate.lookup(dn, mapper)`. | Connect/read timeout, quyền đọc; search count limit không phải trọng tâm. |
| Add | `LdapTemplate.bind(...)` hoặc ODM create. | Connect/read timeout, ACL add, schema, xử lý duplicate DN. |
| Modify | `LdapTemplate.modifyAttributes(...)`, ODM update. | Connect/read timeout, ACL modify, schema, giá trị attribute; không do countLimit search chi phối. |
| Delete | `LdapTemplate.unbind(dn)`. | Connect/read timeout, quyền delete, entry con và bảo vệ nghiệp vụ. |
| Rename/Move | `LdapTemplate.rename(oldDn, newDn)`. | Read timeout, ACL Modify DN và ảnh hưởng liên kết nhóm. |

Đặc biệt với **thao tác ghi**, nếu client bị timeout sau khi đã gửi request, server có thể **đã thực hiện thay đổi** nhưng response không về đến ứng dụng. Không retry vô điều kiện; trước hết đối soát trạng thái theo DN/stable ID, rồi quyết định retry/compensation theo nghiệp vụ.

Khi thao tác LDAP nằm trong quy trình cùng database khác, `@Transactional` không tự tạo transaction nguyên tử xuyên LDAP và RDBMS. Phải thiết kế lại trạng thái và phương án khôi phục nếu write nửa chừng.

## 13. Đối chiếu với `ldapsearch` trên directory test

Trên môi trường thử nghiệm được phép, bạn có thể kiểm chứng bộ lọc và giới hạn bằng OpenLDAP command-line client:

~~~bash
ldapsearch -LLL -x \
  -H "ldaps://ldap.example.org:636" \
  -D "cn=app-reader,ou=services,dc=example,dc=org" -W \
  -b "ou=people,dc=example,dc=org" -s sub \
  -z 50 -l 2 \
  "(&(objectClass=inetOrgPerson)(ou=Engineering))" \
  dn uid cn mail
~~~

Các cờ cần hiểu:

| Cờ | Ý nghĩa |
| --- | --- |
| `-H` | LDAP endpoint; ví dụ sử dụng LDAPS. |
| `-D`, `-W` | Bind DN và nhập secret tương tác; `-W` không đặt mật khẩu trên command line. |
| `-b` | Base DN đầy đủ của truy vấn CLI. |
| `-s sub` | Tìm trên toàn bộ cây con (subtree). |
| `-z 50` | Yêu cầu size limit 50 entry cho search. |
| `-l 2` | Yêu cầu time limit 2 **giây** (CLI); tương ứng ý định khoảng 2.000 ms của API Spring trong ví dụ. |
| Filter | Điều kiện LDAP đã cố định, không ghép từ input không tin cậy. |
| `dn uid cn mail` | Các trường yêu cầu trả về. |

Nếu `ldapsearch` thấy kết quả còn Java không thấy, kiểm tra **cùng URL, bind DN, base/scope/filter và trường được yêu cầu**, cũng như truststore TLS riêng của JVM. Sự khác nhau có thể do ACL hoặc schema; không kết luận ngay rằng `LdapTemplate` bỏ mất dữ liệu.

### 13.1. Kết quả trùng hoặc bị cắt

Nếu câu lệnh với `-z 50` nhận đúng 50 entry, nó không chứng minh chỉ có 50 người. Muốn kiểm đếm đầy đủ, dùng cơ chế paging thích hợp dưới quyền được cấp, ví dụ:

~~~bash
ldapsearch -LLL -x \
  -H "ldaps://ldap.example.org:636" \
  -D "cn=app-reader,ou=services,dc=example,dc=org" -W \
  -b "ou=people,dc=example,dc=org" -s sub \
  -E pr=250/noprompt \
  "(objectClass=inetOrgPerson)" dn
~~~

Truy vấn trên chỉ phù hợp để kiểm thử với directory được cho phép. Không thực hiện scan toàn tổ chức chỉ để đo thử query rồi gây tải hoặc xuất dữ liệu ngoài phạm vi ACL.

## 14. Kiểm thử các giới hạn và quyền truy cập

### 14.1. Unit test cấu hình query

Tách cấu hình query thành một hàm thuần, để test không cần kết nối LDAP:

~~~java
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;
import org.springframework.ldap.query.SearchScope;

public final class DirectoryQueries {

    private DirectoryQueries() {}

    public static LdapQuery byUid(String uid) {
        if (uid == null || uid.isBlank() || uid.length() > 128) {
            throw new IllegalArgumentException("uid khong hop le");
        }
        return LdapQueryBuilder.query()
                .base("ou=people")
                .searchScope(SearchScope.ONELEVEL)
                .attributes("uid", "cn")
                .countLimit(2)
                .timeLimit(1500)
                .where("objectClass").is("inetOrgPerson")
                .and("uid").is(uid);
    }
}
~~~

JUnit 5:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.SearchScope;

class DirectoryQueriesTest {

    @Test
    void queryHasBoundedScopeTimeAndResults() {
        LdapQuery q = DirectoryQueries.byUid("lan");

        assertEquals(Integer.valueOf(2), q.countLimit());
        assertEquals(Integer.valueOf(1500), q.timeLimit());
        assertEquals(SearchScope.ONELEVEL, q.searchScope());
        assertArrayEquals(new String[] {"uid", "cn"}, q.attributes());
    }

    @Test
    void rejectsEmptyOrOversizedUid() {
        assertThrows(IllegalArgumentException.class,
                () -> DirectoryQueries.byUid("  "));
        assertThrows(IllegalArgumentException.class,
                () -> DirectoryQueries.byUid("x".repeat(129)));
    }
}
~~~

Test này chứng minh builder **có cấu hình đúng**; không chứng minh server thực thi time limit theo thời gian tuyệt đối, cho phép ACL hay trả đủ dữ liệu. Những điều đó thuộc integration test.

### 14.2. Unit test tránh filter injection

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;
import org.springframework.ldap.filter.EqualsFilter;

class BoundedFilterTest {
    @Test
    void escapesSpecialValueRatherThanChangingFilterStructure() {
        String untrusted = "lan*)(uid=*)";
        String filter = new EqualsFilter("uid", untrusted).encode();

        assertTrue(filter.startsWith("(uid="));
        assertTrue(filter.contains("\\2a")); // literal *
        assertTrue(filter.contains("\\28")); // literal (
        assertTrue(filter.contains("\\29")); // literal )
    }
}
~~~

Giá trị filter có dấu sao/dấu ngoặc phải được escape, nhưng **tên attribute và search base** cũng phải đến từ cấu hình/allowlist của server. Đừng cung cấp API nhận raw LDAP filter từ client và cho rằng count/time limit đủ để an toàn.

### 14.3. Ma trận integration test

Chuẩn bị OU test có số entry rõ ràng, ví dụ `ou=people-test` với ít nhất 125 `inetOrgPerson`, tài khoản `reader-a` và `reader-b` được cấp ACL khác nhau; không dùng tài khoản production.

| Tình huống | Thiết lập | Kỳ vọng cần xác minh |
| --- | --- | --- |
| Truy vấn chỉ 1 entry. | Filter `uid` duy nhất, `countLimit(2)`. | Đọc đúng entry nếu ACL cho phép. |
| Nhiều entry hơn count limit. | 125 entry, `countLimit(50)`. | Chỉ nhận tối đa giới hạn hoặc lỗi policy; **không** coi đây là full scan. |
| Search base sai. | Tìm ở OU không tồn tại. | Phân loại lỗi DN/base, không suy user không tồn tại toàn cây. |
| ONELEVEL và SUBTREE. | Có entry trong OU con. | ONELEVEL không quét cấp sâu, SUBTREE có thể tìm. |
| Time limit rất nhỏ. | Trên môi trường test được kiểm soát. | Có thể phát sinh time limit/error hoặc server xử lý nhanh hơn; không giả định chắc chắn timeout. |
| JNDI connect timeout. | Endpoint không kết nối được. | Có lỗi kết nối được phân loại, không trả `[]`. |
| JNDI read timeout. | Server test phản hồi chậm/mạng mô phỏng. | Request không chờ vô hạn, lỗi được báo đúng. |
| Service bind account thiếu quyền. | `reader-a` không được đọc `mail`. | `mail` có thể vắng hoặc server từ chối; không tự tăng quyền. |
| Caller HTTP thiếu authority. | Role không có `DIRECTORY_READ`. | Bị từ chối trước khi trả dữ liệu, dù service account LDAP có thể đọc. |
| Caller được phép nhưng OU ngoài phạm vi. | API nhận yêu cầu tới OU bị cấm. | Service từ chối theo tenant/OU policy. |
| Server size/admin limit thấp. | Cấu hình server test theo policy. | Nhận diện lỗi/truncation, không đánh dấu complete. |
| LDAP referral hoặc partial result. | Directory test có referral. | Tuân thủ chính sách referral; không bỏ qua rồi tuyên bố đã đọc đủ. |
| Paging cho tập lớn. | Bật RFC 2696, kiểm tra cookie. | Đọc tất cả trang và kết thúc khi response báo hết cookie. |
| Network mất giữa search. | Mô phỏng có kiểm soát. | Thực hiện retry giới hạn nếu phù hợp, không xóa dữ liệu vì scan thiếu. |

### 14.4. Test authorization không phụ thuộc LDAP

Unit/integration test tầng HTTP nên chứng minh rằng người dùng thiếu `DIRECTORY_READ` **không được gọi** chức năng tìm kiếm, kể cả khi bạn mock repository trả entry bình thường. Khi yêu cầu truy cập có dữ liệu nhạy cảm theo đơn vị/nhóm, thêm test ownership hoặc tenant-specific policy; chỉ có role tổng quát không đủ bảo vệ dữ liệu cấp đối tượng.

**Quan trọng:** Không dùng một lần bind bằng tài khoản quản trị thành công làm bằng chứng ACL đã được kiểm tra. Hãy chạy search với **đúng service account production dự kiến** nhưng trên OU test hoặc môi trường staging có policy tương ứng.

## 15. Chẩn đoán lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| API trả đúng 50 entry rồi dừng. | `countLimit(50)` hoặc size limit server. | Xác định hợp đồng API; paging nếu cần tập đầy đủ. |
| Kết quả 0 dù biết có user. | Sai base/scope/filter, ACL, replica hoặc normalization. | Đối chiếu cùng bind account, xem error và schema. |
| Lỗi `timeLimitExceeded` / code 3. | Server ngừng search vì thời gian. | Thu hẹp base/filter, kiểm tra index/tải, không coi là kết quả rỗng. |
| Lỗi `sizeLimitExceeded` / code 4. | Quá nhiều entry theo giới hạn search. | Giới hạn chức năng hoặc paging phù hợp. |
| Lỗi `adminLimitExceeded` / code 11. | Vượt quota/policy máy chủ. | Đo query, tuân thủ policy, giảm tải và chỉnh use case. |
| Lỗi `invalidCredentials` / code 49. | Bind DN hoặc secret sai, account policy. | Xác minh secret và trạng thái account; không log mật khẩu. |
| Lỗi `insufficientAccessRights` / code 50. | ACL account bind không đủ. | Kiểm tra OU/attribute, không dùng admin account để né ACL. |
| Lỗi `noSuchObject` / code 32. | Base DN không tồn tại hoặc đã move. | Kiểm tra context base/DN tương đối. |
| `SSLHandshakeException`. | CA/hostname/truststore không đúng. | Sửa TLS, không tắt verification. |
| HTTP 403 nhưng LDAP search được. | Spring Security/authorization đang từ chối. | Kiểm tra role/ownership, đây có thể là hành vi đúng. |
| HTTP timeout dù LDAP search nhanh. | Mapping, database downstream, queue hoặc tầng HTTP. | Đo toàn pipeline, đặt deadline đúng tầng. |
| Chỉ nhận partial data rồi xóa user. | Lỗi timeout/limit bị chuyển thành empty/completed. | Thiết kế trạng thái FAILED/PARTIAL, reconciliation an toàn. |

Nhiều ngoại lệ JNDI sẽ được Spring LDAP dịch thành những exception thuộc nhóm `DataAccessException` phù hợp. Việc map lỗi thành HTTP status thuộc API boundary; không đưa raw bind DN, mật khẩu, filter có dữ liệu cá nhân hoặc stack trace chi tiết ra phản hồi cho caller.

## 16. Bài tập tình huống

Một ứng dụng nội bộ tìm người dùng dưới `ou=employees,dc=company,dc=internal`. Directory có 8.000 nhân viên, bao gồm OU con `ou=contractors`. Người dùng HTTP chỉ được xem nhân viên thuộc tenant của mình. Nhóm ứng dụng muốn:

- Trả tối đa 30 kết quả cho autocomplete.
- Không để mỗi search chiếm directory quá lâu.
- Tìm danh tính đăng nhập theo `uid` duy nhất khi xác thực.
- Chạy job đồng bộ cần đọc toàn bộ nhân viên theo lịch.
- Dùng tài khoản kỹ thuật chỉ đọc và TLS an toàn.

**Yêu cầu:**

1. Với autocomplete, bạn chọn `countLimit`, `timeLimit`, base/scope và projection như thế nào? Có nên trả toàn bộ 8.000 entry?
2. Với tìm danh tính đăng nhập, vì sao `countLimit(2)` có thể hợp lý hơn `countLimit(1)`?
3. Nếu chỉ cần nhân viên trực tiếp dưới `ou=employees`, chọn ONELEVEL hay SUBTREE? Nếu phải bao gồm contractor ở OU con thì sao?
4. `timeLimit(2000)` có bảo đảm toàn request HTTP hoàn thành trong đúng 2 giây không? Những timeout nào khác cần xem xét?
5. Nếu LDAP search trả 30 entry đúng bằng count limit, được khẳng định chỉ có 30 nhân viên phù hợp không?
6. Nếu 8.000 entry cần đồng bộ, `countLimit(100)` có đọc đủ không? Cần cơ chế gì và lưu ý cookie gì?
7. Khi LDAP server trả `sizeLimitExceeded` sau một số entry, job có nên đánh dấu những user không thấy là đã nghỉ việc?
8. Nếu service account xem được dữ liệu cả hai tenant, nhưng user HTTP chỉ được xem tenant A, lớp nào phải giới hạn?
9. Nếu bind account chỉ được đọc `uid` và `cn` nhưng không có `mail`, mapper cần xử lý thế nào? Có được tự chuyển sang tài khoản quản trị không?
10. Nếu mạng gián đoạn sau khi gửi `modifyAttributes`, tại sao không retry ghi mù quáng giống một search chỉ đọc?

**Gợi ý đáp án:**

- Autocomplete: base và scope phù hợp tenant, filter được builder escape, returning attributes nhỏ, `countLimit(30)` và time limit phù hợp SLA; thêm rate limit và HTTP authorization.
- Tìm UID duy nhất: nhận 2 entry là dấu hiệu nhập nhằng, cần báo lỗi danh tính; không âm thầm chọn một.
- ONELEVEL không xuống OU con; SUBTREE gồm các OU con trong base.
- Search time limit không bao gồm mọi giai đoạn TCP/TLS, map, downstream và HTTP; cần connect/read timeout, tổng deadline, rate/concurrency budget.
- Đúng 30 chỉ có nghĩa **đã nhận 30** dưới giới hạn truy vấn, không chứng minh không còn entry khác.
- Đồng bộ toàn bộ: RFC 2696 Simple Paged Results (nếu server hỗ trợ), cookie và same connection, stable ID/idempotent handling; không coi paging là snapshot.
- Search bị size/time/admin limit hoặc mất kết nối là **PARTIAL/FAILED**; không đánh dấu vắng/xóa user từ dữ liệu thiếu.
- Spring Security và service phải kiểm tra tenant/object policy, trong khi LDAP server vẫn thực thi ACL tài khoản bind.
- Mapper phân biệt attribute thiếu với lỗi ACL/schema; không tự nâng quyền account. Nếu nghiệp vụ bắt buộc mail thì đánh dấu lỗi dữ liệu/không đủ quyền có kiểm soát.
- Sau write timeout, server có thể đã ghi; cần đối soát trạng thái entry trước khi retry.

## 17. Ghi nhớ

**Giới hạn LDAP search là một tổ hợp, không phải một tham số.** Đặt search base/scope/filter đúng trước, chỉ yêu cầu attribute cần thiết, dùng `countLimit` để giới hạn số entry và `timeLimit` để giới hạn thời gian search. Thêm **connect/read timeout**, tổng deadline, quota, rate limit và server-side policy. Đừng coi giới hạn client là cách bỏ qua quy định của directory server.

**Quyền truy cập cũng gồm hai tầng:** Spring Security/service bảo vệ dữ liệu theo caller HTTP, còn LDAP ACL bảo vệ directory theo bind identity. Search trả 0 chưa chứng minh entry không tồn tại, còn search bị cắt/timeout **không phải kết quả đầy đủ**. Nếu phải đọc danh bạ lớn, dùng cơ chế phân trang thích hợp và kiểm thử kỹ với directory. Mọi lỗi giới hạn, filter, schema, ACL và TLS cần được quan sát và xử lý tách biệt để hệ thống vừa an toàn vừa đáng tin cậy.

### Tài liệu tham khảo

- [Spring LDAP Reference — Advanced LDAP Queries](https://docs.spring.io/spring-ldap/reference/query-builder-advanced.html)
- [Spring LDAP API — LdapQueryBuilder](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/query/LdapQueryBuilder.html)
- [Spring LDAP API — LdapTemplate](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/core/LdapTemplate.html)
- [Spring LDAP Reference — Configuration](https://docs.spring.io/spring-ldap/reference/configuration.html)
- [Spring Data LDAP Reference](https://docs.spring.io/spring-data/ldap/reference/)
- [Spring Security Reference — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [RFC 4511 — LDAP Search Request and Results](https://www.rfc-editor.org/rfc/rfc4511)
- [RFC 4515 — String Representation of LDAP Search Filters](https://www.rfc-editor.org/rfc/rfc4515)
- [RFC 2696 — LDAP Simple Paged Results Control](https://www.rfc-editor.org/rfc/rfc2696)
- [Oracle — SearchControls (JNDI)](https://docs.oracle.com/en/java/javase/17/docs/api/java.naming/javax/naming/directory/SearchControls.html)
