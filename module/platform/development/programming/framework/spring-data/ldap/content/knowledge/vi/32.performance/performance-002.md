# Thu hẹp search base, scope và thuộc tính trả về trong Spring Data LDAP

Trong **Spring Data LDAP**, mỗi lần tìm kiếm có thể khiến directory xét một phần cây LDAP, áp dụng bộ lọc (*search filter*) và gửi về các entry phù hợp. Nếu ứng dụng luôn tìm từ gốc lớn nhất, quét cả cây và nhận mọi thuộc tính, một màn hình chỉ cần mã người dùng cùng tên hiển thị cũng có thể tạo tải không cần thiết. Ba lựa chọn quan trọng ở phía client là **search base**, **search scope** và **thuộc tính trả về** (*returning attributes*).

Bài học trình bày cách điều chỉnh ba lựa chọn này bằng **Spring LDAP `LdapTemplate`**, liên hệ với repository/ODM của Spring Data LDAP, đồng thời hướng dẫn đo lường để xác định cải thiện hiệu năng thực tế.

## 1. Mục tiêu

Sau bài học, bạn có thể:

- Phân biệt search base của phép tìm kiếm với base DN đã cấu hình trong `ContextSource`.
- Chọn đúng scope `OBJECT`, `ONELEVEL` và `SUBTREE` cho từng yêu cầu nghiệp vụ.
- Giới hạn thuộc tính gửi về bằng `LdapQueryBuilder.attributes(...)` và `SearchControls.setReturningAttributes(...)`.
- Dùng `LdapTemplate` trả DTO chỉ có thông tin cần thiết thay vì ánh xạ toàn bộ entry.
- Nhận diện ảnh hưởng đến tính đầy đủ kết quả, bộ lọc, index, ACL và giới hạn của directory.
- Thiết kế phép đo trước/sau, kiểm thử phạm vi và trường hợp thuộc tính bị thiếu.

## 2. Base, scope và attributes ảnh hưởng đến điều gì?

Giả sử cây thư mục:

```text
dc=example,dc=com
├── ou=people
│   ├── uid=alice
│   ├── uid=bob
│   └── ou=contractors
│       └── uid=carol
├── ou=groups
│   └── cn=engineering
└── ou=systems
    └── cn=service-a
```

DN đầy đủ của Alice là `uid=alice,ou=people,dc=example,dc=com`. Giả sử ứng dụng cần liệt kê **người dùng là con trực tiếp dưới `ou=people`**, và UI chỉ hiển thị `uid`, `cn`.

| Tham số | Câu hỏi | Ví dụ phù hợp |
| --- | --- | --- |
| **Search base** | Bắt đầu tìm ở entry nào? | `ou=people,dc=example,dc=com` |
| **Search scope** | Tìm tại base, con trực tiếp hay mọi hậu duệ? | `ONELEVEL` |
| **Returning attributes** | Mỗi kết quả cần trả những trường gì? | `uid`, `cn` |
| **Search filter** | Entry nào thỏa điều kiện? | `(objectClass=inetOrgPerson)` |

Filter quyết định điều kiện so khớp; ba tham số trên xác định miền tìm kiếm và dữ liệu trả về. Thay đổi chúng có thể làm thay đổi **tập kết quả**, nên cần bảo đảm tính đúng đắn trước khi đo hiệu năng.

## 3. Thu hẹp search base

**Search base** là DN gốc của phép tìm kiếm. Với ví dụ trên, tìm từ `dc=example,dc=com` có thể bao gồm cả các nhánh `groups` và `systems`; nếu ứng dụng chỉ quan tâm người dùng, chọn `ou=people` giúp giới hạn miền tìm kiếm có chủ đích.

Giả sử cấu hình Spring Boot:

```yaml
spring:
  ldap:
    urls: ldaps://ldap.example.com:636
    base: dc=example,dc=com
    username: ${LDAP_BIND_DN}
    password: ${LDAP_BIND_PASSWORD}
```

`spring.ldap.base` xác định **base của ngữ cảnh LDAP**. Trong các lời gọi `LdapTemplate` sử dụng `ContextSource` đó, search base `ou=people` là **tên tương đối** so với `dc=example,dc=com`:

```text
Search base truyền cho LdapTemplate: ou=people
Base của ContextSource:          dc=example,dc=com
Base thực tế trên directory:     ou=people,dc=example,dc=com
```

Không tự nối `dc=example,dc=com` vào search base tương đối lần nữa, vì có thể tạo tên bị lặp hoặc trỏ tới nhánh không tồn tại.

### 3.1. Cùng một filter, hai search base

```java
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.SearchScope;
import static org.springframework.ldap.query.LdapQueryBuilder.query;

LdapQuery broadQuery = query()
        .base("")                       // base của ContextSource
        .searchScope(SearchScope.SUBTREE)
        .where("uid").is("alice");

LdapQuery narrowQuery = query()
        .base("ou=people")              // nhánh liên quan
        .searchScope(SearchScope.SUBTREE)
        .where("uid").is("alice");
```

Cả hai truy vấn đều có thể tìm Alice, nhưng `narrowQuery` giới hạn việc tìm kiếm vào nhánh người dùng. **Không có bảo đảm** thời gian chạy sẽ giảm theo tỷ lệ số entry nằm ngoài nhánh đó: directory có thể dùng index, cache và bộ tối ưu khác nhau.

Nếu dữ liệu nghiệp vụ nằm ở nhiều nhánh (ví dụ người dùng cũng nằm trong `ou=alumni`), không được thu hẹp base tùy tiện rồi bỏ sót kết quả. Hãy xác định miền dữ liệu hợp lệ trước khi tối ưu.

### 3.2. Đã biết chính xác DN: cân nhắc `lookup`

Nếu ứng dụng đã biết DN của entry, nó có thể đọc theo DN mà không cần tìm subtree theo giá trị thuộc tính:

```java
import javax.naming.Name;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.support.LdapNameBuilder;

Name dn = LdapNameBuilder.newInstance()
        .add("ou", "people")
        .add("uid", "alice")
        .build();

String commonName = ldapTemplate.lookup(
        dn,
        (AttributesMapper<String>) attrs ->
                attrs.get("cn").get().toString()
);
```

`lookup` hợp với trường hợp đã biết DN; `search` hợp với truy vấn theo điều kiện và có thể trả nhiều entry. Khi dùng `lookup`, ứng dụng vẫn cần kiểm soát DN, ACL và những thuộc tính nó muốn lấy; phiên bản API dùng thực tế có thể có overload chỉ định thuộc tính cần đọc.

## 4. Search scope: tìm sâu bao nhiêu cấp?

LDAP có ba mức phạm vi:

| Scope | Entry được xét | Với base `ou=people` trong ví dụ |
| --- | --- | --- |
| **OBJECT** | Chỉ chính entry base. | `ou=people`. |
| **ONELEVEL** | Các con trực tiếp, không gồm chính base. | `uid=alice`, `uid=bob`, `ou=contractors`. |
| **SUBTREE** | Entry base và tất cả hậu duệ. | Có thêm `uid=carol` trong OU con. |

Điểm dễ nhầm: `ou=contractors` là con trực tiếp của `ou=people`, nên nằm trong `ONELEVEL`; `uid=carol` là con của `ou=contractors`, nên chỉ nằm trong phạm vi `SUBTREE` tính từ `ou=people`. Filter `(objectClass=inetOrgPerson)` sau đó có thể loại `ou=contractors` vì nó không phải entry người dùng.

### 4.1. Cấu hình scope với query builder

```java
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.SearchScope;
import static org.springframework.ldap.query.LdapQueryBuilder.query;

LdapQuery directPeople = query()
        .base("ou=people")
        .searchScope(SearchScope.ONELEVEL)
        .where("objectClass").is("inetOrgPerson");

LdapQuery nestedPeople = query()
        .base("ou=people")
        .searchScope(SearchScope.SUBTREE)
        .where("objectClass").is("inetOrgPerson");
```

Trong cây mẫu, `directPeople` tìm Alice và Bob; `nestedPeople` có thể tìm thêm Carol. Sự khác biệt là **hành vi nghiệp vụ**. Nếu người dùng có thể được lưu trong nhiều OU con, `SUBTREE` có thể là bắt buộc.

Nên chỉ định scope tường minh ở truy vấn mà độ sâu quyết định kết quả. Đừng giả định mọi overload của `LdapTemplate.search` hoặc mọi loại repository có cùng scope mặc định.

## 5. Giảm thuộc tính được trả về

Một entry `inetOrgPerson` có thể có nhiều thuộc tính như `uid`, `cn`, `sn`, `mail`, `telephoneNumber`, nhiều giá trị nhóm, mô tả và metadata khác. Nếu UI chỉ hiển thị hai trường, yêu cầu tất cả có thể làm tăng dữ liệu truyền qua mạng và chi phí tạo đối tượng.

`LdapQueryBuilder` hỗ trợ chỉ định các thuộc tính cần trả về:

```java
LdapQuery compactQuery = query()
        .base("ou=people")
        .searchScope(SearchScope.ONELEVEL)
        .attributes("uid", "cn")
        .where("objectClass").is("inetOrgPerson");
```

**Thuộc tính dùng trong filter không nhất thiết phải được trả về.** Trong ví dụ, directory có thể dùng `objectClass` để so khớp dù `objectClass` không nằm trong `attributes("uid", "cn")`. Tập thuộc tính gửi về còn bị ảnh hưởng bởi ACL của server.

### 5.1. Ánh xạ sang DTO nhỏ

Thay vì tạo một entity ODM có nhiều trường, một màn hình danh sách có thể dùng record:

```java
package com.example.directory;

public record PersonSummary(String uid, String commonName) {}
```

Ví dụ service chỉ yêu cầu và ánh xạ hai thuộc tính:

```java
package com.example.directory;

import java.util.List;
import javax.naming.NamingException;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;

import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.SearchScope;
import org.springframework.stereotype.Service;

import static org.springframework.ldap.query.LdapQueryBuilder.query;

@Service
public class PersonSummarySearch {
    private final LdapTemplate ldapTemplate;

    public PersonSummarySearch(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<PersonSummary> directPeople() {
        LdapQuery q = query()
                .base("ou=people")
                .searchScope(SearchScope.ONELEVEL)
                .attributes("uid", "cn")
                .where("objectClass").is("inetOrgPerson");

        return ldapTemplate.search(
                q,
                (AttributesMapper<PersonSummary>) attrs ->
                        new PersonSummary(
                                valueOrNull(attrs, "uid"),
                                valueOrNull(attrs, "cn")
                        )
        );
    }

    private static String valueOrNull(Attributes attrs, String id)
            throws NamingException {
        Attribute attr = attrs.get(id);
        return attr == null || attr.size() == 0
                ? null : String.valueOf(attr.get());
    }
}
```

Đoạn code trả `null` khi một thuộc tính vắng mặt vì ACL hoặc dữ liệu không như mong đợi. Ứng dụng thực tế cần chọn chính sách cho trường hợp thiếu `uid`/`cn`: báo dữ liệu không hợp lệ, bỏ qua entry hoặc dùng giá trị thay thế có chủ đích.

**Cảnh báo với ODM:** Không lấy entity chỉ tải một phần thuộc tính rồi gọi `save(...)` như thể đó là entity đầy đủ. Tùy cơ chế ghi, các trường chưa được tải về có thể bị xử lý không đúng. Một **DTO chỉ đọc** làm rõ các trường thực sự cần và tránh tái sử dụng dữ liệu không hoàn chỉnh cho thao tác ghi.

### 5.2. Thuộc tính vận hành và dữ liệu nhiều giá trị

Không phải tất cả thuộc tính vận hành (*operational attributes*) đều được trả về theo cách mặc định như thuộc tính người dùng. Nếu ứng dụng cần `modifyTimestamp` hoặc một định danh máy chủ như `entryUUID`, phải kiểm tra directory hỗ trợ, quyền đọc và cách yêu cầu chúng. Đừng mở rộng tập thuộc tính chỉ để “dự phòng”.

Giảm thuộc tính được trả về **không làm giảm số entry mà filter khớp**. Nó thường giúp giảm payload và công ánh xạ, nhưng server vẫn cần xử lý filter (có thể dựa trên index) để xác định entry phù hợp.

## 6. Kết hợp base, scope, attributes với filter an toàn

API tìm một `uid`, chỉ dưới cấp trực tiếp của `ou=people`, lấy hai trường:

```java
import java.util.List;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.SearchScope;
import static org.springframework.ldap.query.LdapQueryBuilder.query;

// Method đặt trong PersonSummarySearch ở phần trên.
public List<PersonSummary> findDirectPerson(String requestedUid) {
    if (requestedUid == null || requestedUid.isBlank()) {
        throw new IllegalArgumentException("uid không được rỗng");
    }

    LdapQuery q = query()
            .base("ou=people")
            .searchScope(SearchScope.ONELEVEL)
            .attributes("uid", "cn")
            .where("objectClass").is("inetOrgPerson")
            .and("uid").is(requestedUid);

    return ldapTemplate.search(
            q,
            (AttributesMapper<PersonSummary>) attrs ->
                    new PersonSummary(
                            valueOrNull(attrs, "uid"),
                            valueOrNull(attrs, "cn")
                    )
    );
}
```

`base`, scope và tên thuộc tính do ứng dụng quyết định; `requestedUid` là **giá trị** truyền vào query builder. Biểu thức `.is(requestedUid)` xử lý escaping filter, giúp dữ liệu như `*` không bị hiểu thành wildcard. Thu hẹp base/scope không thay thế kiểm soát input hoặc quyền truy cập.

Nếu nghiệp vụ cho phép tìm các entry trong mọi OU con, đổi `ONELEVEL` thành `SUBTREE` có chủ đích; vẫn giữ projection nhỏ và filter chọn lọc.

## 7. Lựa chọn khác: `SearchControls` của JNDI

`LdapTemplate` hỗ trợ sử dụng `javax.naming.directory.SearchControls`. Cách này hữu ích khi code đang dùng filter dạng chuỗi và muốn chỉ định scope, returning attributes, giới hạn số lượng và thời gian:

```java
import java.util.List;
import javax.naming.directory.SearchControls;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.filter.AndFilter;
import org.springframework.ldap.filter.EqualsFilter;

SearchControls controls = new SearchControls();
controls.setSearchScope(SearchControls.ONELEVEL_SCOPE);
controls.setReturningAttributes(new String[] {"uid", "cn"});
controls.setCountLimit(100);
controls.setTimeLimit(2_000);  // millisecond

AndFilter filter = new AndFilter();
filter.and(new EqualsFilter("objectClass", "inetOrgPerson"));
filter.and(new EqualsFilter("uid", requestedUid));

List<PersonSummary> rows = ldapTemplate.search(
        "ou=people",
        filter.encode(),
        controls,
        (AttributesMapper<PersonSummary>) attrs ->
                new PersonSummary(
                        valueOrNull(attrs, "uid"),
                        valueOrNull(attrs, "cn")
                )
);
```

Ý nghĩa:

- `ONELEVEL_SCOPE`: chỉ các entry con trực tiếp.
- `setReturningAttributes(...)`: chỉ yêu cầu các trường DTO dùng.
- `setCountLimit(100)`: giới hạn số entry client mong nhận; ứng dụng phải xử lý trường hợp kết quả không đầy đủ.
- `setTimeLimit(2_000)`: giới hạn thời gian search trong `SearchControls`, tính bằng mili giây; hiệu quả thực tế tùy LDAP provider/server, không thay thế timeout socket/kết nối.
- `EqualsFilter` và `AndFilter` tạo bộ lọc có cấu trúc, tránh ghép chuỗi input không đáng tin.

Giới hạn số lượng/thời gian bảo vệ hệ thống trước truy vấn quá lớn, nhưng **không** sửa được việc chọn base hoặc scope sai nhu cầu. Dùng `LdapQueryBuilder` hoặc `SearchControls` thống nhất cho từng đường truy vấn để tránh cấu hình phân tán.

## 8. Quan hệ với Spring Data LDAP repository và ODM

Một entity LDAP có thể khai báo:

```java
import javax.naming.Name;
import org.springframework.ldap.odm.annotations.Attribute;
import org.springframework.ldap.odm.annotations.Entry;
import org.springframework.ldap.odm.annotations.Id;

@Entry(
    base = "ou=people",
    objectClasses = {
        "top", "person", "organizationalPerson", "inetOrgPerson"
    }
)
public class PersonEntry {
    @Id
    private Name dn;

    @Attribute(name = "uid")
    private String uid;

    @Attribute(name = "cn")
    private String commonName;

    @Attribute(name = "sn")
    private String surname;

    // Constructor/getter/setter phục vụ ODM.
}
```

`@Entry(base = "ou=people")` chỉ rõ nhánh của entity so với `ContextSource`, nhưng **không đồng nghĩa** mọi truy vấn repository luôn là tìm `ONELEVEL` hoặc chỉ tải một số trường. Repository phù hợp cho CRUD và truy vấn theo domain, ví dụ `findByUid(String uid)`; khi hiệu năng một endpoint tra cứu quan trọng, cần xác minh hành vi thực tế của repository và các truy vấn mà nó tạo ra.

Nếu API danh sách chỉ cần một số trường, một service `LdapTemplate` trả DTO có thể giúp kiểm soát trực tiếp base/scope/returning attributes. Hai kiểu truy cập có thể cùng tồn tại: repository cho thao tác domain và `LdapTemplate` cho các truy vấn đọc chuyên biệt.

## 9. Đo hiệu năng có kiểm soát

Không nên giả định một truy vấn hẹp hơn sẽ nhanh hơn một lượng cố định. Kết quả phụ thuộc vào index của directory, mật độ entry, filter, cache, ACL, tải server và mạng. Nên đo trước/sau **với cùng tập kết quả mà nghiệp vụ yêu cầu**.

| Phương án | Search base | Scope | Thuộc tính trả về | Số entry | p95 latency | Dữ liệu nhận |
| --- | --- | --- | --- | --- | --- | --- |
| A – ban đầu | `""` | `SUBTREE` | Mặc định/nhiều | Đo | Đo | Đo |
| B – thu hẹp base | `ou=people` | `SUBTREE` | Như A | Đo | Đo | Đo |
| C – đổi scope | `ou=people` | `ONELEVEL` | Như A | Đo | Đo | Đo |
| D – thêm projection | `ou=people` | `ONELEVEL` | `uid`, `cn` | Đo | Đo | Đo |

Trong cây ví dụ, C/D **bỏ qua Carol**. Nếu nghiệp vụ cần Carol, không được coi giảm số kết quả là tối ưu hợp lệ; cần giữ `SUBTREE` và chỉ giảm base/thuộc tính hoặc cải thiện filter/index.

Quy trình đánh giá:

1. Xác định tập entry hợp lệ và những thuộc tính UI thực sự sử dụng. Có fixture gồm entry ở cả một cấp và nhiều cấp OU.
2. Giữ nguyên filter, tài khoản LDAP, môi trường mạng và đặc điểm tải; chỉ đổi **một tham số** mỗi lần.
3. Chạy warm-up và nhiều lần đo; ghi `p50`/`p95`/`p99`, số entry, bytes phản hồi nếu đo được, timeout/error và CPU/memory client.
4. So sánh tập kết quả bằng DN hoặc định danh bền vững. Kiểm tra mapper không phụ thuộc trường đã bị loại khỏi projection.
5. Kiểm tra metrics/log phía server nếu có: entries examined, index hit, CPU/IO, cache và giới hạn directory.
6. Đo thêm ở mức concurrency gần với tải dự kiến vì lợi ích ở một request không luôn phản ánh tải tổng thể.

Giảm returning attributes thường giúp **network/payload và mapping**, không nhất thiết giảm số entry server phải xét. Giảm base/scope có thể giảm miền tìm kiếm nhưng index tốt đôi khi đã tối ưu phần lớn công việc. Vì vậy, hãy dùng số đo thay cho suy đoán.

## 10. Lỗi và đánh đổi thường gặp

| Tình huống | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Dùng `ONELEVEL` dù dữ liệu nằm trong các OU con | Bỏ sót entry hợp lệ. | Dùng `SUBTREE` nếu nghiệp vụ cần mọi cấp. |
| Nối lại context base vào search base | Truy vấn sai nhánh hoặc `noSuchObject`. | Chọn DN tương đối đúng với `ContextSource`. |
| Yêu cầu `uid`, `cn` rồi đọc `attrs.get("mail").get()` | Thuộc tính có thể `null`. | Đồng bộ mapper với returning attributes; xử lý thiếu giá trị. |
| Lưu lại entity ODM được tải thiếu trường | Có nguy cơ cập nhật sai dữ liệu. | Dùng DTO chỉ đọc; với ghi cần luồng mapping/cập nhật đúng. |
| Giảm thuộc tính nhưng truy vấn vẫn chậm | Nút thắt ở index, filter hoặc server. | Đo metrics server và chỉnh index/filter phù hợp. |
| Kết quả khác giữa test và production | ACL, schema, index và fixture khác nhau. | Kiểm thử với điều kiện tương đương, không cấp quyền rộng quá mức. |
| Chạm giới hạn số entry/time của directory | Kết quả có thể bị cắt hoặc trả lỗi limit. | Xử lý giới hạn rõ ràng; cân nhắc LDAP paged results khi cần. |

**Index:** các thuộc tính như `uid`, `mail`, `objectClass` có thể được index tùy directory và chính sách quản trị. Tối ưu index thường thuộc quản trị server; client nên phối hợp với người quản trị dựa trên workload đo được.

**Giới hạn và paging:** server có size/time limit riêng. Khi cần duyệt lượng lớn entry, tìm hiểu LDAP paged results control và khả năng hỗ trợ của directory. Đừng giả định cơ chế phân trang ở Spring Data LDAP repository hoàn toàn giống Spring Data JPA.

**Bảo mật:** giữ ACL quyền tối thiểu, cố định nhánh nghiệp vụ, dùng TLS và encode giá trị filter. Một search hẹp giúp hạn chế phạm vi dữ liệu xử lý nhưng không thay thế authorization trên server.

## 11. Kiểm thử scope và returning attributes

Một test tích hợp cần directory thử nghiệm có cấu trúc biết trước:

```text
dc=example,dc=com
└── ou=people
    ├── uid=direct
    └── ou=contractors
        └── uid=nested
```

Giả sử hai entry người dùng đều có `objectClass=inetOrgPerson` hợp lệ, test `ONELEVEL` dưới `ou=people` phải chỉ tìm `direct`:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.SearchScope;
import static org.springframework.ldap.query.LdapQueryBuilder.query;

@SpringBootTest
class LdapSearchScopeIT {
    @Autowired LdapTemplate ldapTemplate;

    @Test
    void oneLevelDoesNotReturnNestedPerson() {
        var q = query()
                .base("ou=people")
                .searchScope(SearchScope.ONELEVEL)
                .attributes("uid")
                .where("objectClass").is("inetOrgPerson");

        List<String> ids = ldapTemplate.search(q,
                (AttributesMapper<String>) attrs ->
                        attrs.get("uid").get().toString());

        assertEquals(List.of("direct"), ids);
    }
}
```

Ví dụ chỉ đúng khi fixture **có duy nhất một entry người dùng con trực tiếp**; không có giả định rằng directory bất kỳ chỉ có entry đó. Nếu có nhiều kết quả, LDAP không bảo đảm thứ tự trả về: dùng so sánh **tập giá trị** thay cho thứ tự. Có thể tạo truy vấn `SUBTREE` cùng filter/base để xác minh cả `direct` và `nested`; đồng thời thử mapper yêu cầu đúng thuộc tính dự kiến.

Chạy kiểm thử/benchmark trên directory riêng với schema và quyền tương ứng, tránh ghi/xóa vào dữ liệu production.

## 12. Bài thực hành

**Bài 1.** Cấu hình `spring.ldap.base = dc=example,dc=com`. API cần các người dùng là con trực tiếp của `ou=people`. Base và scope nên là gì?

**Đáp án:** `base("ou=people")` và `searchScope(SearchScope.ONELEVEL)`. DN thực tế của search base là `ou=people,dc=example,dc=com`.

**Bài 2.** Carol nằm dưới `ou=contractors,ou=people`. Vì sao `ONELEVEL` không tìm Carol? Làm gì nếu nghiệp vụ cần cả nhân sự trong OU con?

**Đáp án:** Carol không phải con trực tiếp của `ou=people`; dùng `SUBTREE` và giữ filter/returning attributes chọn lọc để bao phủ các cấp con.

**Bài 3.** UI chỉ dùng `uid` và `cn`, filter dùng `objectClass`. Có cần yêu cầu trả `objectClass` không?

**Đáp án:** Không bắt buộc. Directory có thể so khớp `objectClass` dù nó không thuộc returning attributes; chỉ lấy thêm nếu ứng dụng cần đọc giá trị đó.

**Bài 4.** Sau khi thêm `.attributes("uid", "cn")`, mapper lỗi khi đọc `attrs.get("mail").get()`. Nguyên nhân?

**Đáp án:** `mail` không được yêu cầu, nên có thể vắng mặt. Chỉ đọc các trường đã yêu cầu hoặc bổ sung `mail` nếu thực sự cần; xử lý thuộc tính thiếu.

**Bài 5.** Benchmark cho thấy chuyển `SUBTREE` thành `ONELEVEL` giảm từ 800 xuống 100 entry, đồng thời latency giảm. Có thể khẳng định tối ưu thành công không?

**Đáp án:** Chỉ khi 100 entry con trực tiếp là **toàn bộ** kết quả nghiệp vụ cần. Nếu 700 entry trong OU con vẫn hợp lệ, truy vấn mới sai chức năng; phải giữ scope đúng rồi tối ưu base, filter/index và thuộc tính trả về.

## 13. Ghi nhớ

- **Search base** là điểm bắt đầu; cần hiểu DN tương đối so với `spring.ldap.base`.
- **OBJECT** xét base, **ONELEVEL** xét con trực tiếp, **SUBTREE** xét cả base và mọi hậu duệ; chọn scope theo nghiệp vụ.
- **Returning attributes** giúp giảm payload/mapping nhưng không tự thay đổi filter hoặc tập entry khớp.
- Dùng `LdapQueryBuilder.base(...).searchScope(...).attributes(...)` hoặc `SearchControls` để cấu hình cụ thể và kiểm soát filter đầu vào.
- Với API chỉ đọc ít trường, dùng **DTO nhỏ** thay vì tái sử dụng entity ODM thiếu thuộc tính cho luồng ghi.
- Đo **latency, số kết quả, payload và metrics server**, đồng thời xác minh không bỏ sót entry, trước khi kết luận hiệu năng tốt hơn.
