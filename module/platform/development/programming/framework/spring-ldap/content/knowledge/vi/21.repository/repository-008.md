# Không che giấu phạm vi search trong abstraction Repository của Spring LDAP

## Mục tiêu

Sau bài học, bạn có thể:

1. Mô tả chính xác một LDAP search bằng **base DN, search scope và filter**, thay vì chỉ nói “tìm theo tên người dùng”.
2. Giải thích vì sao một phương thức Repository nhìn giống truy vấn cơ sở dữ liệu quan hệ có thể tìm sai nhánh LDAP, trả về nhiều entry, hoặc bỏ sót dữ liệu.
3. Thiết kế hợp đồng Repository/service để **người gọi biết phạm vi tìm kiếm**, và chỉ cho phép các vùng directory được phê duyệt.
4. Sử dụng `@Query`, `LdapQueryBuilder`, `LdapRepository` và `LdapTemplate` đúng vai trò để thể hiện base, scope, filter và giới hạn truy vấn.
5. Viết kiểm thử chứng minh phạm vi search, xử lý kết quả trùng, giới hạn tài nguyên và quyền truy cập hoạt động đúng.

> **Thông điệp chính:** Repository giúp che giấu chi tiết thực thi LDAP, nhưng **không được che giấu phạm vi dữ liệu mà thao tác tìm kiếm có thể truy cập**. Base DN và search scope là một phần của ý nghĩa nghiệp vụ; một phương thức chỉ tên là `findByUid` chưa trả lời được “tìm uid này ở đâu?”.

## 1. Tình huống: cùng một `uid`, kết quả khác nhau theo phạm vi

Giả sử directory có cấu trúc sau. `ContextSource` được cấu hình với base DN `dc=example,dc=org`; tất cả DN mà ứng dụng truyền vào trong ví dụ là **tương đối** so với base đó.

```text
dc=example,dc=org                     <-- ContextSource base
├── ou=people
│   ├── uid=lan                       <-- Người ở ngay dưới ou=people
│   └── ou=engineering
│       └── uid=lan                   <-- Người cùng uid ở nhánh con
└── ou=service-accounts
    └── uid=lan                       <-- Tài khoản dịch vụ cùng uid
```

Giả sử cả ba entry đều có attribute `uid: lan` và thuộc object class `inetOrgPerson`. Filter `(uid=lan)` chỉ thể hiện **điều kiện trên attribute**, không chỉ ra nên tìm ở đâu trong cây.

| Base DN (tương đối) | Scope | Kết quả dự kiến với `(uid=lan)` |
| --- | --- | --- |
| `ou=people` | `OBJECT` | Không có entry khớp (chính entry OU không có uid này) |
| `ou=people` | `ONELEVEL` | `uid=lan,ou=people` |
| `ou=people` | `SUBTREE` | `uid=lan,ou=people` **và** `uid=lan,ou=engineering,ou=people` |
| `ou=engineering,ou=people` | `ONELEVEL` | `uid=lan,ou=engineering,ou=people` |
| `ou=service-accounts` | `SUBTREE` | `uid=lan,ou=service-accounts` |
| DN rỗng (chính gốc đã cấu hình trong `ContextSource`) | `SUBTREE` | Cả ba entry dưới `dc=example,dc=org` |

Dòng cuối minh họa rủi ro tìm quá rộng: **khi `ContextSource` đã có base**, không truyền lặp lại hậu tố `dc=example,dc=org` vào một search base tương đối. Muốn tìm toàn bộ cây trong ngữ cảnh này, search base tương đối là DN rỗng.

Kết luận từ ví dụ: cùng một filter nhưng có thể nhận 0, 1 hoặc nhiều entry. Vì vậy, ý nghĩa của truy vấn **không thể tách rời khỏi base DN và search scope**.

## 2. Một LDAP search gồm những gì?

Hãy xem một search như một **hợp đồng** gồm các thành phần sau:

| Thành phần | Câu hỏi cần trả lời | Ví dụ |
| --- | --- | --- |
| `ContextSource` base | Các DN tương đối được neo vào gốc directory nào? | `dc=example,dc=org` |
| Search base | Bắt đầu tìm ở nhánh nào trong gốc trên? | `ou=people` |
| Search scope | Chỉ entry gốc, con trực tiếp hay toàn bộ cây con? | `ONELEVEL` |
| Search filter | Entry cần có những attribute/giá trị gì? | `(&(objectClass=inetOrgPerson)(uid=lan))` |
| Giới hạn | Một truy vấn tối đa bao nhiêu entry, trong bao lâu? | `countLimit=50`, `timeLimit=2000` |
| Attribute trả về | Cần lấy trường nào để tránh truy xuất thừa? | `uid`, `cn`, `mail` |
| Danh tính truy cập | Bind bằng tài khoản nào và ACL cho phép thấy gì? | Service account chỉ có quyền đọc nhánh people |

**Search scope** của Spring LDAP nằm trong enum `org.springframework.ldap.query.SearchScope`:

- `OBJECT`: chỉ xét entry tại search base.
- `ONELEVEL`: chỉ xét các entry **con trực tiếp** của search base; không xét chính base hoặc các cháu sâu hơn.
- `SUBTREE`: xét cả base lẫn các entry bên dưới ở mọi độ sâu.

Không nhầm scope với filter: `(objectClass=inetOrgPerson)` lọc *loại entry*, còn `ONELEVEL` giới hạn *độ sâu*. Một filter có `ou=engineering` không đương nhiên thu hẹp search base; một filter chỉ kiểm tra attribute không thay thế được ràng buộc vị trí trong cây.

### Ba cấp base dễ bị nhầm

**Cấp kết nối**: `ContextSource` có thể cấu hình `base=dc=example,dc=org`. Khi đã có base, các thao tác Spring LDAP thường nhận DN tương đối theo gốc này.

**Cấp ánh xạ entity**: `@Entry(base = "ou=people", objectClasses = ...)` mô tả vị trí và loại entry ODM quản lý. Đây là metadata của mapping; không nên suy diễn mọi phương thức tùy biến đều có cùng phạm vi chỉ từ tên lớp.

**Cấp một truy vấn**: `@Query(base = "...", searchScope = ...)` hoặc `LdapQueryBuilder.query().base(...).searchScope(...)` thể hiện cụ thể vị trí/độ sâu cho search đó.

Khi phối hợp entity có `@Entry(base=...)` với truy vấn có base riêng, cần đối chiếu cách Spring Data LDAP và Spring LDAP ODM xử lý metadata **theo phiên bản đang dùng**. Để ví dụ truy vấn bên dưới minh bạch, entity chỉ khai báo `objectClasses`, còn **search base được đặt tường minh ở query**.

Nếu không nêu scope trong `LdapQuery`, `LdapTemplate` áp dụng cấu hình mặc định của nó (thông thường là `SUBTREE`). Nếu một dự án thay đổi cấu hình này, cùng mã gọi có thể cho tập kết quả khác. Đó là lý do các truy vấn nghiệp vụ nhạy với phạm vi nên chỉ rõ scope ngay trong hợp đồng.

## 3. Repository abstraction nên che giấu điều gì?

Spring Data LDAP giúp khai báo interface thay cho viết nhiều đoạn gọi JNDI. Ví dụ:

```java
public interface PersonRepository extends LdapRepository<DirectoryPerson> {
    List<DirectoryPerson> findByUid(String uid);
}
```

Chữ ký trên mô tả được **điều kiện attribute** nhưng không cho người dùng biết:

- Nó tìm dưới `ou=people`, `ou=service-accounts` hay toàn bộ cây?
- Nó chỉ tìm con trực tiếp (`ONELEVEL`) hay đi sâu vào các OU con (`SUBTREE`)?
- Nếu có nhiều entry cùng uid trong các OU, API trả danh sách hay đòi một kết quả duy nhất?
- Có giới hạn khối lượng truy vấn? Khi server từ chối/trả kết quả thiếu thì xử lý ra sao?
- Nếu ứng dụng phục vụ nhiều tổ chức, ai được phép quyết định search base?

Giao diện `findByUid` không tự động gây lỗi, nhưng **nguy hiểm khi tầng nghiệp vụ tưởng rằng nó luôn tìm trong một nhánh cố định**. Repository cũng kế thừa các thao tác như `findAll()`; vô tình phơi bày một Repository rộng ở controller có thể cho phép truy cập nhiều entry hơn mức nghiệp vụ dự định.

Trừu tượng hóa tốt là trừu tượng giúp người gọi không quan tâm JNDI, cách escape LDAP filter và cách map ODM **nhưng vẫn thấy được ranh giới dữ liệu**, qua tên phương thức, kiểu tham số và tài liệu hợp đồng.

## 4. Cách 1: cố định phạm vi trong `@Query` và nói rõ ở tên phương thức

Giả sử `ContextSource` đã dùng gốc `dc=example,dc=org`, cùng một entity ánh xạ các person entry:

```java
package example.directory;

import javax.naming.Name;
import org.springframework.ldap.odm.annotations.Attribute;
import org.springframework.ldap.odm.annotations.Entry;
import org.springframework.ldap.odm.annotations.Id;

@Entry(objectClasses = {
    "top", "person", "organizationalPerson", "inetOrgPerson"
})
public class DirectoryPerson {
    @Id
    private Name dn;

    @Attribute(name = "uid")
    private String uid;

    @Attribute(name = "cn")
    private String commonName;

    public DirectoryPerson() {}

    public Name getDn() { return dn; }
    public String getUid() { return uid; }
    public String getCommonName() { return commonName; }
}
```

Đây là ODM entity của Spring LDAP; `@Id` nhập từ `org.springframework.ldap.odm.annotations` và có kiểu `javax.naming.Name`. `LdapRepository` chỉ có **một** type parameter là entity. Tài khoản bind, chứng thư TLS và cấu hình `ContextSource`/`LdapTemplate` được chuẩn bị ở tầng hạ tầng.

```java
package example.directory;

import java.util.List;
import org.springframework.data.ldap.repository.LdapRepository;
import org.springframework.data.ldap.repository.Query;
import org.springframework.ldap.query.SearchScope;

public interface PersonRepository extends LdapRepository<DirectoryPerson> {

    // Chỉ entry ngay dưới ou=people.
    @Query(
        value = "(&(objectClass=inetOrgPerson)(uid=?0))",
        base = "ou=people",
        searchScope = SearchScope.ONELEVEL,
        countLimit = 20,
        timeLimit = 2000
    )
    List<DirectoryPerson> findDirectPeopleByUid(String uid);

    // Bao gồm cả các OU con của ou=people.
    @Query(
        value = "(&(objectClass=inetOrgPerson)(uid=?0))",
        base = "ou=people",
        searchScope = SearchScope.SUBTREE,
        countLimit = 100,
        timeLimit = 2000
    )
    List<DirectoryPerson> findPeopleTreeByUid(String uid);
}
```

Ý nghĩa của hai phương thức có thể kiểm tra được bằng mắt và bằng test:

| Phương thức | Search base | Search scope | Với dữ liệu mục 1 |
| --- | --- | --- | --- |
| `findDirectPeopleByUid("lan")` | `ou=people` | `ONELEVEL` | Chỉ người ở con trực tiếp |
| `findPeopleTreeByUid("lan")` | `ou=people` | `SUBTREE` | Người ở nhánh trực tiếp và OU con |

Ở đây tên phương thức không chỉ nói *lọc gì* mà còn gợi rõ *tìm ở đâu*. Annotation xác nhận hợp đồng ở tầng kỹ thuật. `?0` là vị trí tham số đầu tiên; Spring Data LDAP thực hiện binding/escape giá trị để tránh biến các ký tự đặc biệt từ input thành cấu trúc filter.

Tuy vậy, chỉ tên phương thức **không phải** một cơ chế phân quyền. Một phương thức khác, chẳng hạn `findAll()` kế thừa từ repository, vẫn có hợp đồng phạm vi riêng. Vì thế, ở ranh giới API cho controller/use case, nên chỉ phơi bày các thao tác đã được giới hạn thay vì toàn bộ hạ tầng CRUD.

### Viết interface hướng nghiệp vụ

```java
package example.directory;

import java.util.List;

// Cổng mà tầng nghiệp vụ được phép gọi.
public interface PeopleDirectory {
    /**
     * Tìm uid ở các entry con trực tiếp của ou=people,
     * tương đối với ContextSource base dc=example,dc=org.
     * Không tìm trong ou=engineering hoặc ou=service-accounts.
     */
    List<DirectoryPerson> findDirectPeopleByUid(String uid);
}
```

Một implementation có thể ủy quyền cho `PersonRepository.findDirectPeopleByUid`. Phần thiết kế quan trọng là người gọi **chỉ phụ thuộc vào `PeopleDirectory`** và không tự suy diễn phạm vi từ cấu hình LDAP ẩn bên trong. Đặt repository kỹ thuật ở package hạ tầng và tránh inject nó trực tiếp vào controller giúp giảm khả năng vô tình gọi search quá rộng.

## 5. Cách 2: đưa phạm vi vào kiểu tham số khi có nhiều nhánh

Nếu người dùng chọn loại danh bạ, không nên truyền thẳng DN tùy ý từ request như `base=ou=...,dc=...`. Thay vào đó, mô hình hóa **các vùng tìm kiếm được phép** rồi ánh xạ chúng đến DN được quản lý ở server.

```java
package example.directory;

public enum PeopleArea {
    STAFF,
    CONTRACTORS
}
```

Ví dụ service phía server dùng `LdapTemplate` và `LdapQueryBuilder`:

```java
package example.directory;

import java.util.List;
import java.util.Map;
import java.util.Objects;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;
import org.springframework.ldap.query.SearchScope;
import org.springframework.stereotype.Service;

@Service
public class ScopedPeopleDirectory {
    // Các DN này tương đối với ContextSource base dc=example,dc=org.
    private static final Map<PeopleArea, String> BASE_BY_AREA = Map.of(
        PeopleArea.STAFF, "ou=staff,ou=people",
        PeopleArea.CONTRACTORS, "ou=contractors,ou=people"
    );

    private final LdapTemplate ldapTemplate;

    public ScopedPeopleDirectory(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<DirectoryPerson> findDirectPeople(PeopleArea area, String uid) {
        String base = BASE_BY_AREA.get(Objects.requireNonNull(area));
        if (uid == null || uid.isBlank()) {
            throw new IllegalArgumentException("uid must not be blank");
        }

        LdapQuery query = LdapQueryBuilder.query()
            .base(base)
            .searchScope(SearchScope.ONELEVEL)
            .countLimit(50)
            .timeLimit(2000)
            .where("objectClass").is("inetOrgPerson")
            .and("uid").is(uid);

        return ldapTemplate.find(query, DirectoryPerson.class);
    }
}
```

Với phương thức này:

1. **Area là một lựa chọn có kiểm soát**, không phải chuỗi DN người dùng nhập. Hệ thống phải kiểm tra quyền chọn `STAFF` hoặc `CONTRACTORS` của người gọi trước khi thực hiện.
2. `base` lấy từ map cố định; `ONELEVEL` bảo đảm không tự tìm sâu vào OU con.
3. `uid` đi qua `.is(uid)` của builder, được xử lý như một **giá trị filter**, không dùng phép nối chuỗi filter.
4. `countLimit` và `timeLimit` giới hạn tài nguyên của một search. Chúng không tạo ra phân trang hay thứ tự ổn định.
5. `ldapTemplate.find(query, DirectoryPerson.class)` dùng ODM ánh xạ entry phù hợp; đây là lựa chọn khi search có base thay đổi theo input nghiệp vụ.

Nếu muốn giữ cách gọi thông qua `LdapRepository`, cùng đối tượng `LdapQuery` có thể được đưa vào `repository.findAll(query)` vì `LdapRepository<T>` có API này. Điểm thiết kế không đổi: **tầng ứng dụng phải biết chính sách phạm vi**, cho dù truy vấn được chạy qua Repository hay Template.

Lưu ý về hiệu lực thực tế: map base cố định chỉ kiểm soát lựa chọn nhánh tại tầng ứng dụng; LDAP server vẫn quyết định quyền đọc qua bind identity/ACL. Không coi kiểm tra input trong Java là sự thay thế cho phân quyền server. Trong hệ thống nhiều tenant, mỗi tenant còn cần được **ủy quyền** đối với area đã chọn.

## 6. So sánh các cách định nghĩa hợp đồng tìm kiếm

| Thiết kế | Tác động đối với phạm vi search | Khi nên dùng |
| --- | --- | --- |
| `findByUid(uid)` dẫn xuất | Base và scope phụ thuộc metadata/cấu hình nằm ngoài chữ ký | Chỉ khi phạm vi cố định đã được quy ước và kiểm thử rõ |
| `@Query(base=..., searchScope=...)` | Chính sách cố định gắn trực tiếp vào phương thức | Tìm trong một nhánh nghiệp vụ xác định |
| `LdapQueryBuilder` bên trong service | Chính sách có thể được tạo từ lựa chọn đã kiểm soát | Nhiều nhánh hợp lệ, filter và giới hạn động |
| `LdapTemplate` / `LdapClient` | Kiểm soát search và hoạt động thư mục ở tầng thấp hơn | Cần tùy biến search, mapping, LDAP controls hoặc xử lý đặc thù |
| Cho controller nhận chuỗi `baseDn` bất kỳ | Cho phép caller mở rộng/đổi search root ngoài ý định | **Tránh**; thay bằng enum/allowlist và kiểm tra quyền |

Không đánh đồng `countLimit` với cách “lấy 50 bản ghi đầu tiên” như `LIMIT 50` của SQL. LDAP không mặc nhiên trả theo thứ tự ổn định; máy chủ có thể áp size limit/time limit và báo lỗi tùy kết quả, driver, server. Spring LDAP Repository không cung cấp phân trang và sắp xếp theo mô hình thông thường của Spring Data JPA; nếu cần LDAP paged-results hoặc server-side sort control, phải thiết kế và kiểm tra riêng theo khả năng directory.

### Cách viết hợp đồng có thể kiểm tra

Trước khi công bố một API tìm kiếm cho ứng dụng, nên ghi rõ:

```text
Use case: Tìm nhân viên trong phòng ban đang được chọn
ContextSource base: dc=example,dc=org
Allowed search bases: ou=staff,ou=people | ou=contractors,ou=people
Scope: ONELEVEL
Filter: objectClass=inetOrgPerson AND uid=<giá trị được escape>
Maximum results: 50
Search time limit: 2000 ms
Result type: danh sách; có thể có 0/nhiều entry
Authorization: area phải nằm trong quyền của người gọi
Completeness: kết quả có thể không đầy đủ nếu bị giới hạn
```

Một bảng hợp đồng như vậy rất hữu ích cho code review, kiểm thử và vận hành. Dù repository implementation có thay đổi, các ranh giới base/scope/authorization vẫn là điều hệ thống phải giữ.

## 7. Những lỗi thường gặp khi trừu tượng hóa Repository

### Lỗi 1: coi `uid` là ID toàn cục

`uid` có thể trùng ở các nhánh LDAP khác nhau. ID của ODM entity là **DN**, thường là một `javax.naming.Name`; `findById` xác định entry bằng DN, trong khi `findByUid` là search theo attribute. Nếu logic đăng nhập/tìm người dùng đòi một kết quả nhưng filter khớp nhiều entry, không nên tùy tiện lấy phần tử đầu tiên. Hãy thu hẹp base/scope hoặc xác định quy tắc duy nhất theo schema, rồi xử lý rõ kết quả 0, 1 và nhiều.

### Lỗi 2: lấy toàn cây để lọc lại trong Java

Code kiểu `repository.findAll().stream().filter(...)` có thể đọc quá nhiều dữ liệu, chịu giới hạn server và gây tải lớn. Chuyển điều kiện vào LDAP filter, giới hạn base/scope và chỉ lấy attribute cần thiết. Lưu ý rằng `@Query` và `LdapQueryBuilder` có thể kiểm soát search, còn việc hạn chế attribute trả về phụ thuộc API cụ thể (ví dụ `LdapQueryBuilder.attributes("uid", "cn")`). Với ODM, cần xem mapping khi không tải đủ attribute.

### Lỗi 3: dùng `SUBTREE` ở nơi chỉ cần một cấp

`SUBTREE` dưới `ou=people` sẽ chạm cả các nhánh `ou=engineering`, `ou=external`... Nếu cần chỉ user gắn trực tiếp dưới OU, dùng `ONELEVEL`. Nếu ứng dụng cố ý tìm mọi cấp, ghi rõ điều đó trong hợp đồng; không dựa vào mặc định.

### Lỗi 4: ghép sai DN do nhầm base

Khi `ContextSource` có base `dc=example,dc=org`, `.base("ou=people")` xác định nhánh thực tế `ou=people,dc=example,dc=org`. Truyền một DN đầy đủ vào chỗ mong đợi DN tương đối dễ tạo đường dẫn sai hoặc khiến truy vấn thất bại. Kiểm tra cấu hình base trước khi đưa truy vấn vào production.

### Lỗi 5: cho input điều khiển cấu trúc filter hoặc vị trí tìm kiếm

Không viết:

```java
// Tránh: input có thể sửa cấu trúc filter LDAP.
String filter = "(uid=" + userInput + ")";
// Tránh: caller có thể tùy ý đổi gốc tìm kiếm.
String base = requestedBaseDn;
```

Dùng `LdapQueryBuilder.where("uid").is(userInput)` hoặc `@Query` với tham số bind để escape ký tự trong filter (theo các quy tắc LDAP filter). Đối với base DN, dùng danh sách lựa chọn đã định nghĩa và quyền truy cập rõ ràng; việc escape filter **không** giải quyết bài toán ủy quyền chọn base.

### Lỗi 6: tưởng không có dữ liệu vì search rỗng

Một danh sách rỗng có thể do sai base, scope, object class, quyền đọc, referral hoặc thật sự không có entry. Kết quả bị cắt, time limit và size limit có thể gây ngoại lệ hoặc trạng thái riêng; đừng tự động biến mọi lỗi LDAP thành “không tìm thấy”. Ghi log gọn về tên thao tác, base, scope, giới hạn và loại lỗi, nhưng tránh ghi credential hoặc thông tin cá nhân không cần thiết.

## 8. Kiểm thử phạm vi search như một hành vi nghiệp vụ

Tạo fixture bằng LDAP server thử nghiệm/embedded test directory phù hợp, không dùng tài khoản production. Dữ liệu tối thiểu:

```ldif
dn: ou=people,dc=example,dc=org
objectClass: organizationalUnit
ou: people

dn: uid=lan,ou=people,dc=example,dc=org
objectClass: inetOrgPerson
uid: lan
cn: Lan Direct
sn: Direct

dn: ou=engineering,ou=people,dc=example,dc=org
objectClass: organizationalUnit
ou: engineering

dn: uid=lan,ou=engineering,ou=people,dc=example,dc=org
objectClass: inetOrgPerson
uid: lan
cn: Lan Engineering
sn: Engineering

dn: ou=service-accounts,dc=example,dc=org
objectClass: organizationalUnit
ou: service-accounts

dn: uid=lan,ou=service-accounts,dc=example,dc=org
objectClass: inetOrgPerson
uid: lan
cn: Lan Service
sn: Service
```

> Đây là fixture minh họa; tùy LDAP server, có thể cần bổ sung các object class cha `top`, `person`, `organizationalPerson`, schema phù hợp và các entry cha `dc=example,dc=org` trước khi import.

Thiết lập `ContextSource` base `dc=example,dc=org` và bind tài khoản thử nghiệm có quyền đọc các nhánh. Sau đó kiểm tra:

| Ca kiểm thử | Gọi | Điều cần xác nhận |
| --- | --- | --- |
| Phân biệt con trực tiếp | `findDirectPeopleByUid("lan")` | Chỉ DN `uid=lan,ou=people` |
| Tìm sâu | `findPeopleTreeByUid("lan")` | Có hai DN dưới `ou=people` |
| Không rò sang nhánh ngoài | Hai phương thức trên | Không có DN chứa `ou=service-accounts` |
| Không có kết quả | Tìm uid không tồn tại | Danh sách rỗng; không coi là lỗi mạng |
| Trùng `uid` | Tìm trong subtree | Không tùy tiện chọn một entry làm “duy nhất” |
| Filter injection | uid chứa `*`, `(`, `)` hoặc ký tự escape | Điều kiện coi input là giá trị, không đổi cấu trúc filter |
| Giới hạn | Tạo hơn 50 entry cùng điều kiện | Kiểm tra giới hạn/error thực tế; không giả định danh sách đầy đủ |
| Authorization | Chọn area không được cấp quyền | Tầng ứng dụng từ chối trước search; ACL server vẫn được kiểm tra |
| Sai base/scope | Đổi base hoặc scope trong test | Kết quả thay đổi đúng như sơ đồ cây |

Khi kiểm thử qua `LdapTemplate`, có thể log query ở môi trường thử nghiệm để xác nhận **base tương đối**, scope và filter. Khi kiểm thử repository annotated, ưu tiên assertion trên **DN thực tế** được trả về, vì hai entry khác DN có thể có cùng `uid` và `cn`. Dùng các test case này để ngăn một lần refactor vô tình mở rộng phạm vi sang OU con hoặc nhánh khác.

## 9. Bài thực hành thiết kế API

Ứng dụng có một màn hình tra cứu nhân sự. Nó chỉ được tìm người ở ngay dưới `ou=staff,ou=people`; màn hình quản trị mới được tìm trong cả các OU con của `ou=people`. Cả hai màn hình có thể nhận `uid` giống nhau.

**Yêu cầu:**

1. Giải thích vì sao dùng chung `List<Person> findByUid(String uid)` cho hai màn hình sẽ làm hợp đồng khó kiểm chứng.
2. Đề xuất hai phương thức có tên thể hiện vùng tìm kiếm, scope và giới hạn trả về.
3. Dùng `@Query` cho màn hình nhân sự (base `ou=staff,ou=people`, scope `ONELEVEL`, tối đa 30 entry, 2 giây).
4. Dùng `LdapQueryBuilder` cho màn hình quản trị (base `ou=people`, scope `SUBTREE`, tối đa 100 entry, 3 giây) và giải thích yêu cầu phân quyền của thao tác này.
5. Nêu ít nhất ba kiểm thử phân biệt được hai hợp đồng.

**Gợi ý:**

```java
// Trong LdapRepository<DirectoryPerson>:
@Query(
    value = "(&(objectClass=inetOrgPerson)(uid=?0))",
    base = "ou=staff,ou=people",
    searchScope = SearchScope.ONELEVEL,
    countLimit = 30,
    timeLimit = 2000
)
List<DirectoryPerson> findDirectStaffByUid(String uid);

// Trong service quản trị có quyền phù hợp:
LdapQuery query = LdapQueryBuilder.query()
    .base("ou=people")
    .searchScope(SearchScope.SUBTREE)
    .countLimit(100)
    .timeLimit(3000)
    .where("objectClass").is("inetOrgPerson")
    .and("uid").is(uid);

List<DirectoryPerson> matches = ldapTemplate.find(query, DirectoryPerson.class);
```

Kiểm thử nên có ít nhất: một `uid` trùng ở hai độ sâu khác nhau; một account dưới nhánh `service-accounts` bị loại; và một yêu cầu không có quyền quản trị bị từ chối trước search. Mở rộng bằng ca kích hoạt size/time limit và input chứa ký tự đặc biệt LDAP.

## Tài liệu tham khảo

- [Spring LDAP — Advanced LDAP Queries](https://docs.spring.io/spring-ldap/reference/query-builder-advanced.html): `base`, `searchScope`, `countLimit`, `timeLimit`, filter.
- [Spring LDAP — LdapQueryBuilder API](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/query/LdapQueryBuilder.html): mặc định và cách dùng builder.
- [Spring LDAP — SearchScope API](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/query/SearchScope.html): `OBJECT`, `ONELEVEL`, `SUBTREE`.
- [Spring Data LDAP — @Query API](https://docs.spring.io/spring-data/ldap/reference/api/java/org/springframework/data/ldap/repository/Query.html): annotation cố định search base, scope, time/count limit.
- [Spring Data LDAP — LdapRepository API](https://docs.spring.io/spring-data/ldap/reference/api/java/org/springframework/data/ldap/repository/LdapRepository.html): `findAll(LdapQuery)` và `findOne(LdapQuery)`.
- [Spring LDAP — Repositories](https://docs.spring.io/spring-ldap/reference/repositories.html): kiểu DN ID, ODM, ràng buộc phân trang/sắp xếp.
- [Spring LDAP — Configuration](https://docs.spring.io/spring-ldap/reference/configuration.html): `ContextSource` base và mặc định `LdapTemplate`.
