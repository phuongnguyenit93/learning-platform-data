# Xử lý bộ lọc tùy chọn mà không vô tình mở rộng phạm vi tìm kiếm

Trong một màn hình tra cứu directory, người dùng thường chỉ nhập một vài tiêu chí: UID, họ, email hoặc trạng thái. Những tiêu chí chưa nhập được gọi là **bộ lọc tùy chọn**. Khi xây LDAP filter động, ứng dụng thường bỏ qua điều kiện tương ứng với giá trị rỗng. Cách làm này tiện lợi, nhưng nếu bỏ qua mọi điều kiện mà vẫn chạy search, truy vấn có thể chỉ còn `objectClass` hoặc một điều kiện rất rộng và trả về hàng nghìn entry.

Với **Spring Data LDAP**, cần thiết kế rõ ranh giới giữa **điều kiện bắt buộc**, **điều kiện tùy chọn**, **search base**, **search scope** và **quyền truy cập**. Bài này hướng dẫn xây filter động bằng Spring LDAP Filter API, xử lý `null`/chuỗi trắng, kết hợp AND/OR, giới hạn thuộc tính được tìm, từ chối truy vấn không đủ điều kiện và kiểm thử để bảo đảm bỏ trống một ô tìm kiếm không vô tình mở rộng dữ liệu mà người gọi có thể truy cập.

Trong phạm vi **SPRING_DATA_LDAP**, các ví dụ dùng directory phân cấp với DN, `objectClass`, schema và service Java/Spring. Bộ lọc được thực thi qua `LdapTemplate`; repository vẫn phù hợp với query method cố định, còn truy vấn động có nhiều tổ hợp điều kiện thường dễ kiểm soát hơn khi tách thành một query builder riêng.

> **Nguyên tắc:** thiếu một tiêu chí tùy chọn chỉ được bỏ qua chính tiêu chí đó. Nó không được làm thay đổi base DN, scope, tenant boundary, ACL hoặc các điều kiện bắt buộc. Nếu người dùng không cung cấp tiêu chí đủ để thực hiện nghiệp vụ tra cứu, hãy từ chối yêu cầu hoặc chuyển sang một luồng browse riêng đã được phân quyền và giới hạn.

## 1. Vì sao bộ lọc tùy chọn có thể mở rộng kết quả?

Giả sử trang quản trị tìm nhân viên theo ba trường:

- UID.
- Họ.
- Email.

Người dùng nhập UID `u1001`, để trống họ và email. Truy vấn dự kiến chỉ cần điều kiện UID:

```ldap
(&(objectClass=inetOrgPerson)(uid=u1001))
```

Nếu cả ba trường đều rỗng mà code vẫn dựng filter, kết quả có thể chỉ còn:

```ldap
(objectClass=inetOrgPerson)
```

Đây là một truy vấn hợp lệ về cú pháp, nhưng có thể trả về toàn bộ người dùng trong search base. Khi base là một naming context lớn và scope là `SUBTREE`, số entry có thể rất lớn.

Một lỗi khác là biến giá trị rỗng thành wildcard:

```ldap
(&(objectClass=inetOrgPerson)(mail=*))
```

Điều kiện `mail=*` có nghĩa attribute `mail` hiện diện. Nó không có nghĩa người dùng muốn tìm tất cả nhân viên. Việc thay `null`/blank thành wildcard làm thay đổi ý nghĩa nghiệp vụ.

### Hậu quả

- Search tốn tài nguyên LDAP server và connection pool.
- Người dùng nhận nhiều dữ liệu hơn nhu cầu.
- Có thể lộ thông tin trong những nhánh directory không cần thiết.
- API trả kết quả lớn, tăng memory và latency.
- Search có thể chạm size/time limit và tạo cảm giác dữ liệu bị thiếu.
- Một lỗi UI gửi form rỗng có thể biến thành thao tác liệt kê directory.

Vì vậy, kiểm soát filter tùy chọn là một phần của correctness, authorization và performance.

## 2. Tách bốn lớp điều kiện

Một truy vấn an toàn cần phân biệt các lớp sau:

| Lớp | Ví dụ | Ai kiểm soát? |
|---|---|---|
| **Search base** | `ou=people` | Cấu hình ứng dụng hoặc scope resolver đã xác thực |
| **Search scope** | `ONELEVEL`, `SUBTREE` | Use case/service |
| **Điều kiện bắt buộc** | `objectClass=inetOrgPerson`, tenant boundary | Schema và policy ứng dụng |
| **Điều kiện tùy chọn** | UID, họ, email, trạng thái | Input đã validate từ người dùng |

Ví dụ filter đầy đủ:

```ldap
(&
  (objectClass=inetOrgPerson)
  (tenantId=tenant-42)
  (uid=u1001)
  (mail=*)
)
```

Trong ví dụ:

- Base DN và scope xác định nhánh directory được phép tìm.
- `objectClass` giới hạn loại entry.
- `tenantId` là điều kiện phân vùng bắt buộc nếu schema/thiết kế directory dùng thuộc tính này.
- UID và mail là điều kiện nghiệp vụ tùy chọn theo yêu cầu màn hình.

Không phải directory nào cũng có `tenantId`; khi đó ranh giới tenant có thể được thể hiện bằng DN/OU riêng. Chọn cơ chế theo schema thực tế, nhưng không bỏ ranh giới truy cập chỉ vì request không truyền tenant.

## 3. Quy tắc logic khi bỏ qua điều kiện

Bỏ một điều kiện khỏi biểu thức có ảnh hưởng khác nhau tùy phép logic.

### 3.1 Điều kiện nằm trong nhóm AND

Với:

```ldap
(&(A)(B)(C))
```

Nếu bỏ B, biểu thức còn:

```ldap
(&(A)(C))
```

Tập kết quả thường **rộng hơn hoặc bằng** tập ban đầu vì entry chỉ cần thỏa ít điều kiện hơn. Đây là lý do bỏ qua tất cả trường tìm kiếm có thể làm search rộng đột ngột.

### 3.2 Điều kiện nằm trong nhóm OR

Với:

```ldap
(|(A)(B)(C))
```

Nếu bỏ B, biểu thức còn:

```ldap
(|(A)(C))
```

Tập kết quả thường **hẹp hơn hoặc bằng** tập ban đầu vì mất một nhánh có thể khớp. Nếu không còn nhánh nào, không tạo một OR rỗng và không thay bằng wildcard.

### 3.3 NOT cần được xử lý riêng

Filter:

```ldap
(!(mail=blocked@example.org))
```

có thể khớp cả entry không có `mail`. Nếu nghiệp vụ yêu cầu có email và không phải email bị chặn, phải viết:

```ldap
(&(mail=*)(!(mail=blocked@example.org)))
```

Không tự động biến điều kiện vắng mặt thành NOT; hai trường hợp mang nghĩa khác nhau.

**Kết luận về logic:** bỏ điều kiện chỉ là thao tác cấu trúc. Trước khi bỏ, phải biết điều kiện nằm trong AND, OR hay NOT và tập kết quả sẽ thay đổi theo hướng nào.

## 4. Xác định hợp đồng input: null, blank và wildcard

Một API tìm kiếm nên định nghĩa rõ ý nghĩa của từng dạng input:

| Input | Cách xử lý khuyến nghị |
|---|---|
| `null` | Không cung cấp tiêu chí; bỏ qua nếu field là optional |
| `""` | Coi là không cung cấp hoặc từ chối theo contract |
| Chuỗi chỉ có whitespace | Coi là không cung cấp hoặc từ chối |
| Chuỗi có giá trị | Trim/normalize theo quy tắc nghiệp vụ rồi validate |
| `"*"` | Không tự hiểu là “tìm tất cả”; từ chối hoặc xử lý trong mode wildcard riêng |
| Chuỗi quá dài | Từ chối trước khi gọi LDAP |
| Attribute name tùy ý | Từ chối; chỉ chấp nhận field trong allowlist |
| Base DN/scope do client gửi | Không nhận trực tiếp; lấy từ policy/cấu hình đã xác thực |

### Vì sao không dùng empty string làm wildcard?

Trong LDAP, equality với giá trị rỗng và presence filter có semantics riêng. Chuỗi rỗng không phải ký hiệu chung để nói “bỏ qua điều kiện”. Nếu ứng dụng muốn bỏ qua tiêu chí, hãy **không tạo filter node**.

### Chuẩn hóa input có chủ đích

Có thể dùng `String.strip()` để bỏ whitespace đầu/cuối (Java 11+). Tuy nhiên, không phải field nào cũng nên normalize giống nhau. UID có thể cần lowercase theo quy tắc hệ thống; common name có thể cần giữ nguyên Unicode. Chỉ chuẩn hóa theo quy tắc login/schema đã thống nhất, không tự thay đổi dữ liệu tùy tiện.

## 5. Giữ base DN và scope cố định

Không để việc một input tùy chọn bị bỏ qua làm thay đổi vị trí tìm kiếm.

Ví dụ service chỉ tìm trong nhánh:

```text
ou=people,dc=example,dc=org
```

Với `ContextSource` có base `dc=example,dc=org`, query có thể dùng base tương đối `ou=people`:

```java
LdapQuery request = query()
        .base("ou=people")
        .searchScope(SearchScope.SUBTREE)
        .filter(filter);
```

Cần lưu ý:

- `base("ou=people")` là search base tương đối theo context base trong cấu hình tương ứng.
- `SUBTREE` tìm base và các descendant; nó không có nghĩa tìm mọi domain/forest.
- Nếu user thuộc OU khác, service này không tự mở rộng sang root naming context.
- Không đổi sang `SUBTREE` chỉ vì `ONELEVEL` không tìm thấy kết quả.
- Không nhận base DN từ request để người gọi tự mở rộng vùng tìm kiếm.

Nếu ứng dụng đa tenant, base DN cần được resolve từ danh tính đã xác thực hoặc tenant mapping tin cậy. Giá trị `tenantId` do client gửi không tự chứng minh caller có quyền truy cập tenant đó.

## 6. Phân biệt điều kiện bắt buộc và tùy chọn trong thiết kế

Trước khi viết code, lập bảng cho use case:

| Field | Bắt buộc? | Ý nghĩa khi thiếu | Nguồn giá trị |
|---|---|---|---|
| `objectClass` | Có | Không được bỏ | Cấu hình/schema |
| Search base | Có | Không thực hiện search | Cấu hình/scope resolver |
| Scope | Có | Không thực hiện search | Service policy |
| Tenant/OU boundary | Có nếu ứng dụng phân vùng | Không được bỏ | Principal đã xác thực |
| UID | Không | Bỏ qua điều kiện UID | Request |
| Họ | Không | Bỏ qua điều kiện họ | Request |
| Email | Không | Bỏ qua điều kiện email | Request |
| Search mode | Có nếu có exact/prefix/browse | Không tự suy diễn | API contract/permission |

Một nguyên tắc dễ kiểm tra: **mọi query phải có các điều kiện bắt buộc, và phải có ít nhất một tiêu chí nghiệp vụ nếu use case là tìm kiếm theo tiêu chí**.

Nếu sản phẩm cần chức năng “xem danh sách nhân viên”, hãy xây một use case browse riêng có quyền riêng, paging và giới hạn. Không để một form search rỗng vô tình trở thành browse endpoint.

## 7. Biểu diễn tiêu chí tìm kiếm bằng DTO

Không truyền raw LDAP filter từ controller. Controller nhận một DTO có các field nghiệp vụ đã biết:

```java
public record PeopleSearchCriteria(
        String uid,
        String surname,
        String email
) {}
```

Một DTO rõ ràng giúp:

- Tách API contract khỏi LDAP syntax.
- Biết field nào optional.
- Validate độ dài/định dạng từng field.
- Không cho client chọn tùy ý attribute hoặc operator.
- Có thể thay đổi schema mà không làm API lộ chi tiết directory.

Nếu cần thêm chế độ prefix, hãy biểu diễn bằng một field/mode riêng đã được allowlist. Không nhận chuỗi filter như `(&(uid=...)(...))` từ client.

## 8. Chuẩn hóa và kiểm tra tiêu chí tùy chọn

Một helper có thể chuyển `null`, chuỗi rỗng và whitespace thành “không có giá trị”:

```java
private static String optionalValue(String raw, int maxLength) {
    if (raw == null) {
        return null;
    }

    String value = raw.strip();
    if (value.isEmpty()) {
        return null;
    }

    if (value.length() > maxLength) {
        throw new IllegalArgumentException(
                "Search value is too long");
    }

    return value;
}
```

Helper này chỉ thực hiện quy tắc chung. Từng field vẫn cần validation riêng:

- UID có thể chỉ cho phép ký tự theo quy tắc tài khoản.
- Email nên được kiểm tra định dạng ở mức nghiệp vụ.
- Họ/tên có thể chứa Unicode và dấu cách bên trong.
- Prefix search cần giới hạn wildcard.
- Không ghi giá trị nhạy cảm vào exception message.

Đừng âm thầm chuyển một giá trị không hợp lệ thành `null`. Ví dụ, email quá dài phải bị từ chối; nếu chuyển thành null, ứng dụng lại chạy search với ít điều kiện hơn và kết quả rộng hơn.

## 9. Từ chối khi tất cả tiêu chí tìm kiếm đều vắng mặt

Đây là guard quan trọng nhất:

```java
String uid = optionalValue(criteria.uid(), 64);
String surname = optionalValue(criteria.surname(), 128);
String email = optionalValue(criteria.email(), 254);

boolean hasSearchCriterion =
        uid != null || surname != null || email != null;

if (!hasSearchCriterion) {
    throw new IllegalArgumentException(
            "At least one search criterion is required");
}
```

Guard phải chạy **trước khi gọi LDAP**. Không đợi query trả quá nhiều kết quả rồi mới cắt danh sách trong Java; lúc đó server đã phải xử lý search rộng.

Một lựa chọn khác là trả lỗi validation của API, ví dụ HTTP 400. Nếu nghiệp vụ cho phép browse, hãy yêu cầu mode browse tường minh và kiểm tra quyền riêng. Không tự động coi form trống là browse.

## 10. Xây nhóm AND từ các tiêu chí đã có

Với màn hình có ý nghĩa “tất cả tiêu chí được nhập đều phải khớp”, dùng AND:

```java
import org.springframework.ldap.filter.AndFilter;
import org.springframework.ldap.filter.EqualsFilter;
import org.springframework.ldap.filter.Filter;
import org.springframework.ldap.filter.PresentFilter;

public final class PeopleFilterFactory {

    public Filter buildAndFilter(
            String uid,
            String surname,
            String email) {

        AndFilter root = new AndFilter();

        // Điều kiện bắt buộc do ứng dụng kiểm soát.
        root.and(new EqualsFilter(
                "objectClass", "inetOrgPerson"));

        // Các điều kiện tùy chọn.
        if (uid != null) {
            root.and(new EqualsFilter("uid", uid));
        }

        if (surname != null) {
            root.and(new EqualsFilter("sn", surname));
        }

        if (email != null) {
            root.and(new EqualsFilter("mail", email));
        }

        return root;
    }
}
```

Nếu chỉ có UID, filter sẽ gồm `objectClass` và UID. Nếu có UID và họ, cả hai điều kiện đều được thêm. Mỗi điều kiện được tạo bằng Filter class, nên giá trị được encode theo ngữ cảnh LDAP filter.

Tuy nhiên, hàm này **không thay thế guard ở phần 9**. Nếu cả ba tham số đều null, root chỉ còn `objectClass`, có thể rất rộng. Hãy kiểm tra có tiêu chí nghiệp vụ trước khi gọi factory hoặc thực hiện query.

## 11. Một service hoàn chỉnh có guard và giới hạn search

Ví dụ sau kết hợp chuẩn hóa, guard, base/scope cố định, filter bắt buộc và giới hạn kết quả:

```java
import java.util.List;
import javax.naming.NamingException;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;

import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.filter.AndFilter;
import org.springframework.ldap.filter.EqualsFilter;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.SearchScope;

import static org.springframework.ldap.query.LdapQueryBuilder.query;

public final class DirectoryPeopleSearchService {

    public record SearchCriteria(
            String uid, String surname, String email) {}

    public record PersonSummary(
            String uid, String commonName, String email) {}

    private final LdapTemplate ldapTemplate;

    public DirectoryPeopleSearchService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<PersonSummary> search(SearchCriteria criteria) {
        if (criteria == null) {
            throw new IllegalArgumentException(
                    "Search criteria are required");
        }

        String uid = optionalValue(criteria.uid(), 64);
        String surname = optionalValue(criteria.surname(), 128);
        String email = optionalValue(criteria.email(), 254);

        if (uid == null && surname == null && email == null) {
            throw new IllegalArgumentException(
                    "At least one search criterion is required");
        }

        AndFilter filter = new AndFilter();
        filter.and(new EqualsFilter(
                "objectClass", "inetOrgPerson"));

        if (uid != null) {
            filter.and(new EqualsFilter("uid", uid));
        }
        if (surname != null) {
            filter.and(new EqualsFilter("sn", surname));
        }
        if (email != null) {
            filter.and(new EqualsFilter("mail", email));
        }

        LdapQuery request = query()
                .base("ou=people")
                .searchScope(SearchScope.SUBTREE)
                .countLimit(100)
                .timeLimit(3000)
                .attributes("uid", "cn", "mail")
                .filter(filter);

        return ldapTemplate.search(request, (AttributesMapper<PersonSummary>)
                attrs -> new PersonSummary(
                        read(attrs, "uid"),
                        read(attrs, "cn"),
                        read(attrs, "mail")));
    }

    private static String optionalValue(String raw, int maxLength) {
        if (raw == null) {
            return null;
        }
        String value = raw.strip();
        if (value.isEmpty()) {
            return null;
        }
        if (value.length() > maxLength) {
            throw new IllegalArgumentException(
                    "Search value is too long");
        }
        return value;
    }

    private static String read(Attributes attrs, String name)
            throws NamingException {
        Attribute attribute = attrs.get(name);
        return attribute == null || attribute.size() == 0
                ? null
                : String.valueOf(attribute.get());
    }
}
```

Đây là ví dụ minh họa với schema `inetOrgPerson`, base `ou=people` và context base đã cấu hình. Trong ứng dụng thật, thay tên attribute, base và scope theo directory đích; bổ sung validation email/UID theo contract. Không expose `SearchCriteria` như một cách chọn raw attribute.

**Điểm quan trọng:** guard chạy trước khi tạo filter và trước khi gọi `ldapTemplate.search`. `countLimit(100)` và `timeLimit(3000)` là giới hạn bổ sung, không phải cách sửa một truy vấn quá rộng.

## 12. Khi nào dùng OR cho các tiêu chí tùy chọn?

Một màn hình khác có thể có ý nghĩa “tìm theo bất kỳ định danh nào đã nhập”: UID **hoặc** email. Khi đó cần OR:

```ldap
(&
  (objectClass=inetOrgPerson)
  (|(uid=u1001)(mail=an@example.org))
)
```

Chỉ thêm nhánh tương ứng với giá trị đã có:

```java
import org.springframework.ldap.filter.OrFilter;

OrFilter alternatives = new OrFilter();
int branchCount = 0;

if (uid != null) {
    alternatives.or(new EqualsFilter("uid", uid));
    branchCount++;
}
if (email != null) {
    alternatives.or(new EqualsFilter("mail", email));
    branchCount++;
}

if (branchCount == 0) {
    throw new IllegalArgumentException(
            "At least one identifier is required");
}
```

Nếu chỉ có một nhánh, có thể dùng trực tiếp filter đó; không cần tạo OR một nhánh. Nếu không có nhánh, từ chối thay vì tạo một OR rỗng hoặc filter wildcard.

**AND và OR là lựa chọn nghiệp vụ, không phải tối ưu hóa kỹ thuật.** Không tự chuyển từ AND sang OR khi người dùng nhập ít tiêu chí vì điều đó làm thay đổi ý nghĩa tìm kiếm và có thể mở rộng kết quả.

## 13. Kết hợp điều kiện bắt buộc với nhóm OR tùy chọn

Ví dụ tìm nhân viên thuộc `inetOrgPerson`, có email, và UID hoặc email khớp:

```java
AndFilter root = new AndFilter();

root.and(new EqualsFilter(
        "objectClass", "inetOrgPerson"));
root.and(new PresentFilter("mail"));

OrFilter identifiers = new OrFilter();
int branches = 0;

if (uid != null) {
    identifiers.or(new EqualsFilter("uid", uid));
    branches++;
}
if (email != null) {
    identifiers.or(new EqualsFilter("mail", email));
    branches++;
}

if (branches == 0) {
    throw new IllegalArgumentException(
            "At least one identifier is required");
}

root.and(identifiers);
```

Filter logic:

```ldap
(&(objectClass=inetOrgPerson)
  (mail=*)
  (|(uid=u1001)(mail=an@example.org)))
```

Nếu nghiệp vụ chỉ yêu cầu tìm UID **hoặc** email, điều kiện `mail=*` có thể khiến nhánh UID loại người không có email. Đó là lý do phải xác định rõ điều kiện nào thật sự bắt buộc, không sao chép ví dụ rồi thêm presence một cách máy móc.

## 14. Xử lý filter tùy chọn lồng nhau

Giả sử màn hình cho phép:

- Bắt buộc thuộc `inetOrgPerson`.
- Họ là Nguyen hoặc tên là An.
- Nếu người dùng nhập trạng thái, trạng thái phải là active.
- Nếu người dùng nhập email, email phải khớp chính xác.

Có thể xây:

```java
AndFilter root = new AndFilter();
root.and(new EqualsFilter(
        "objectClass", "inetOrgPerson"));

OrFilter name = new OrFilter();
name.or(new EqualsFilter("sn", surname));
name.or(new EqualsFilter("givenName", givenName));
root.and(name);

if (status != null) {
    root.and(new EqualsFilter("employeeStatus", status));
}

if (email != null) {
    root.and(new EqualsFilter("mail", email));
}
```

Điều kiện tên là nhóm OR bắt buộc của use case này, vì vậy phải bảo đảm ít nhất một trong `surname` hoặc `givenName` được cung cấp trước khi tạo nhóm. Nếu cả hai rỗng, không được để OR rỗng hoặc bỏ cả nhóm rồi tiếp tục query chỉ theo objectClass.

Nếu trạng thái và email đều optional, bỏ chúng có thể mở rộng tập kết quả. Điều đó chỉ hợp lệ khi tiêu chí tên vẫn đủ chọn lọc và giới hạn truy cập không đổi.

## 15. Tên attribute và toán tử phải nằm trong allowlist

Giá trị của filter có thể được encode, nhưng tên attribute và loại toán tử không phải dữ liệu tự do.

Không làm:

```java
// Không an toàn: client điều khiển tên attribute.
Filter filter = new EqualsFilter(
        request.attributeName(),
        request.value());
```

Thay vào đó, ánh xạ field API sang LDAP attribute cố định:

```java
public enum PeopleSearchField {
    UID("uid"),
    SURNAME("sn"),
    EMAIL("mail"),
    COMMON_NAME("cn");

    private final String ldapAttribute;

    PeopleSearchField(String ldapAttribute) {
        this.ldapAttribute = ldapAttribute;
    }

    public String ldapAttribute() {
        return ldapAttribute;
    }
}
```

Tương tự, nếu API hỗ trợ exact/prefix/contains, hãy dùng enum hoặc endpoint riêng để chọn operator. Không nhận một chuỗi operator tùy ý rồi biến nó thành cú pháp filter.

Allowlist giúp ứng dụng biết attribute nào tồn tại trong schema và được phép tìm kiếm. Tuy nhiên, allowlist không thay thế ACL của directory server.

## 16. Prefix và wildcard là chế độ tìm kiếm riêng

Exact match và prefix search có ý nghĩa khác nhau:

- `EqualsFilter("uid", "u1001")` tìm giá trị bằng chính xác.
- `LikeFilter("cn", "An*")` tìm tên bắt đầu bằng An.
- `PresentFilter("mail")` tìm entry có mail.

Không biến chuỗi rỗng thành `LikeFilter("cn", "*")`. Nếu muốn prefix search:

1. Yêu cầu prefix có độ dài tối thiểu theo nghiệp vụ.
2. Không cho người dùng tự cung cấp wildcard nếu không cần.
3. Chỉ thêm wildcard do ứng dụng kiểm soát ở cuối.
4. Giới hạn base/scope và số kết quả.
5. Kiểm tra index/matching rule trên server.

Ví dụ:

```java
if (prefix == null || prefix.length() < 2
        || prefix.contains("*")) {
    throw new IllegalArgumentException(
            "A valid prefix is required");
}

Filter prefixFilter = new LikeFilter("cn", prefix + "*");
```

Ký tự filter đặc biệt trong giá trị vẫn phải được encode đúng theo API. Việc cấm `*` ở input là quy tắc riêng để caller không tự mở rộng pattern.

## 17. Phân biệt “không nhập tiêu chí” với “muốn browse”

Hai use case này nên có contract riêng:

| Use case | Hành vi |
|---|---|
| Search theo tiêu chí | Yêu cầu ít nhất một tiêu chí; thiếu tất cả thì trả validation error |
| Browse danh sách | Cho phép không có tiêu chí theo quyền riêng; luôn paging và giới hạn |
| Export directory | Quy trình đặc quyền, audit, phê duyệt và giới hạn rõ ràng |
| Admin lookup theo DN | DN phải được xác thực/allowlist và chỉ đọc trong phạm vi được phép |

Nếu cần browse, hãy tạo method riêng như `browsePeople(PageRequest page)` với base/scope cố định, quyền riêng, paging và giới hạn page size. Không dùng cùng `search(criteria)` rồi diễn giải mọi trường rỗng là browse.

Một giới hạn kết quả đơn giản:

```java
private static final int MAX_PAGE_SIZE = 100;

public int validatePageSize(int requested) {
    if (requested < 1 || requested > MAX_PAGE_SIZE) {
        throw new IllegalArgumentException(
                "Invalid page size");
    }
    return requested;
}
```

Đây chỉ là validation page size; cần triển khai LDAP paged-results control phù hợp. `countLimit` không phải offset pagination.

## 18. Multi-tenant: không để optional tenant mở rộng phạm vi

Với ứng dụng nhiều tenant, ranh giới tenant phải đến từ principal/session đã xác thực hoặc một authorization service tin cậy:

- Tenant A chỉ search base/OU của A.
- Tenant B chỉ search base/OU của B.
- Request không được gửi `tenantId` tùy ý để chọn tenant.
- Nếu principal không có tenant scope hợp lệ, từ chối search.
- Optional UID/email không được thay đổi tenant base.
- Không fallback lên `dc=example,dc=org` khi tenant OU không tìm thấy kết quả.

Có thể dùng một `DirectoryScopeResolver` nhận principal đã xác thực và trả `Name`/base DN được phép. Query builder dùng base đã resolve đó. Resolver phải kiểm tra quyền; không chỉ ghép `ou=` với một chuỗi request.

**Không có kết quả trong phạm vi tenant hiện tại không phải lý do để thử lại ở root directory.**

## 19. Giới hạn search và kết quả không đầy đủ

Ngay cả query đã có guard vẫn cần giới hạn:

- `countLimit` giới hạn số entry trong search request.
- `timeLimit` giới hạn thời gian search theo JNDI controls.
- `attributes(...)` chỉ yêu cầu những field cần dùng.
- Paged results control phù hợp khi cần duyệt tập lớn.
- Base/scope và filter cần đủ chọn lọc.
- Server có thể áp dụng size/time limit thấp hơn hoặc trả referral/partial result.

Không coi danh sách trả về là đầy đủ nếu operation kết thúc bằng size-limit/time-limit error hoặc partial result. Không bắt exception rồi trả danh sách một phần như kết quả thành công mà không đánh dấu trạng thái. Một truy vấn rộng bị cắt không đồng nghĩa với một truy vấn chính xác.

## 20. Kiểm thử để chứng minh không mở rộng ngoài ý muốn

Cần kiểm tra cả **filter được tạo**, **việc có gọi LDAP hay không**, **base/scope** và **kết quả thực tế**.

### 20.1 Unit test cho guard

Các trường hợp tối thiểu:

| UID | Họ | Email | Kết quả mong đợi |
|---|---|---|---|
| `u1001` | null | null | Có query theo UID |
| null | `Nguyen` | null | Có query theo họ |
| null | null | `an@example.org` | Có query theo email |
| `u1001` | `Nguyen` | null | AND gồm UID và họ |
| null | `""` | whitespace | Từ chối vì không có tiêu chí |
| null | null | null | Từ chối, không gọi LDAP |
| UID quá dài | null | null | Validation error, không gọi LDAP |
| UID chứa ký tự filter | null | null | Encode thành literal equality value |

Nếu dùng Mockito, test trường hợp tất cả input rỗng nên xác minh `ldapTemplate.search(...)` **không được gọi**. Đây là assertion quan trọng hơn việc chỉ kiểm tra exception.

### 20.2 Unit test cho logic AND/OR

- AND có hai criteria phải encode cả hai nhánh.
- Bỏ một optional field chỉ bỏ nhánh đó.
- OR có một nhánh thì không tạo OR rỗng.
- OR không có nhánh thì từ chối.
- NOT phải có semantics rõ khi attribute vắng mặt.
- Mandatory `objectClass` luôn có trong mọi filter của use case.

### 20.3 Integration test với LDAP test server

Chuẩn bị các entry:

| DN | UID | SN | Mail | OU |
|---|---|---|---|---|
| `uid=u1001,ou=people,...` | u1001 | Nguyen | an@example.org | people |
| `uid=u1002,ou=people,...` | u1002 | Nguyen | Không có | people |
| `uid=u1003,ou=people,...` | u1003 | Tran | tran@example.org | people |
| `uid=u1004,ou=contractors,ou=people,...` | u1004 | Le | le@example.org | contractors |
| `uid=svc1,ou=service-accounts,...` | svc1 | Service | svc@example.org | service-accounts |

Xác minh:

1. Search theo UID chỉ trả đúng entry.
2. Bỏ email không làm base/scope thay đổi.
3. Tất cả tiêu chí rỗng bị từ chối trước search.
4. Entry service account không xuất hiện do base/scope và objectClass policy.
5. ONELEVEL/SUBTREE trả kết quả khác nhau theo cấu trúc cây dự kiến.
6. Ký tự `*`, `(`, `)`, backslash và Unicode không làm thay đổi cấu trúc filter.
7. Tenant A không thể search tenant B.
8. Search vượt size/time limit được báo không đầy đủ.
9. Browse endpoint yêu cầu quyền và page size riêng.

### 20.4 Kiểm thử trên đúng directory server

Mock hữu ích cho logic service. Tuy nhiên, schema, matching rule, ACL, referral, paging và limit khác nhau giữa OpenLDAP, Active Directory và các directory thương mại. Chạy integration test trên đúng sản phẩm/version triển khai.

## 21. Những lỗi thường gặp

| Lỗi | Vì sao nguy hiểm | Cách sửa |
|---|---|---|
| Bỏ mọi criteria rỗng rồi vẫn search | Chỉ còn filter bắt buộc quá rộng | Guard ít nhất một search criterion |
| Chuyển blank thành `*` | Biến input rỗng thành presence/wildcard | Không tạo node cho field vắng mặt |
| Dùng `OR` thay `AND` để “dễ tìm hơn” | Thay đổi nghiệp vụ, có thể tăng kết quả | Chốt semantics theo use case |
| Không giữ `objectClass` | Có thể tìm nhầm loại entry | Thêm mandatory filter phù hợp |
| Bỏ tenant filter khi tenant input rỗng | Có thể vượt tenant boundary | Resolve tenant từ principal, không từ request |
| Đổi base lên root khi không có kết quả | Mở rộng vùng dữ liệu | Giữ base cố định |
| Đổi ONELEVEL thành SUBTREE tự động | Tìm thêm OU con ngoài dự kiến | Scope do service policy quyết định |
| Cho client chọn attribute | Có thể truy vấn field nhạy cảm/không hỗ trợ | Allowlist field |
| Dùng LikeFilter cho exact search | Wildcard có thể trả nhiều entry | Dùng EqualsFilter |
| Tự động browse khi form rỗng | Search endpoint trở thành directory enumeration | Tách browse use case và quyền riêng |
| Cắt danh sách sau khi LDAP trả về | Server vẫn phải xử lý search rộng | Giới hạn query ngay từ LDAP |
| Nuốt partial-result exception | Trả dữ liệu thiếu như thể đầy đủ | Phân loại và báo incomplete |

## 22. Bài tập thực hành

Một ứng dụng quản trị nhân sự có form tìm kiếm gồm UID, họ và email. Người dùng có thể nhập một hoặc nhiều trường. Yêu cầu:

- Chỉ tìm trong `ou=people`.
- Chỉ lấy `inetOrgPerson`.
- Các trường được nhập phải khớp theo AND.
- Không có tiêu chí nào thì trả lỗi validation.
- Chỉ trả `uid`, `cn`, `mail`.
- Giới hạn 100 entry và 3 giây.
- Không cho người dùng tự chọn attribute, base DN hoặc scope.

Hãy thực hiện:

1. Tạo DTO `PeopleSearchCriteria`.
2. Viết helper xử lý null/blank và giới hạn độ dài.
3. Viết guard từ chối khi mọi tiêu chí đều vắng mặt.
4. Tạo `AndFilter` với mandatory `objectClass`.
5. Thêm `EqualsFilter` tương ứng với từng optional field có giá trị.
6. Tạo `LdapQuery` với base và scope cố định.
7. Thực thi bằng `LdapTemplate.search` và mapper DTO.
8. Viết unit test xác minh search không được gọi khi criteria rỗng.
9. Viết integration test với entry có/không có mail và entry nằm ở OU con.
10. Thử payload có wildcard/ngoặc và xác minh không thể mở rộng filter.
11. Tạo một browse endpoint riêng nếu sản phẩm thật sự cần liệt kê toàn bộ người dùng.
12. Viết test phân quyền để chứng minh tenant boundary không phụ thuộc request parameter.

**Gợi ý:** bắt đầu từ mandatory conditions và guard. Sau đó mới thêm optional nodes. Đừng viết query bằng cách nối chuỗi rồi tìm cách sửa các trường hợp đặc biệt về sau.

## 23. Checklist trước khi phát hành

- [ ] Đã phân loại rõ điều kiện bắt buộc và tùy chọn.
- [ ] Đã định nghĩa ý nghĩa của null, empty, whitespace và wildcard.
- [ ] Giá trị không hợp lệ bị từ chối, không bị âm thầm chuyển thành tiêu chí vắng mặt.
- [ ] Nếu mọi optional criteria đều vắng mặt, search endpoint từ chối trước khi gọi LDAP.
- [ ] `objectClass` và tenant/OU boundary bắt buộc không bị bỏ.
- [ ] Base DN và scope do service/cấu hình/scope resolver kiểm soát.
- [ ] AND/OR/NOT có semantics được ghi rõ và test.
- [ ] Attribute name và operator nằm trong allowlist.
- [ ] Giá trị filter được encode qua Filter objects hoặc API tham số.
- [ ] Wildcard search là chế độ riêng, có giới hạn.
- [ ] Có count/time limit và paging khi cần.
- [ ] Mapper chỉ trả các attribute được phép.
- [ ] Partial result, referral và server limit không bị coi là thành công đầy đủ.
- [ ] Browse/export là use case riêng có quyền, audit và giới hạn.
- [ ] Unit test xác minh không gọi LDAP khi input rỗng.
- [ ] Integration test xác minh base, scope, ACL và tenant boundary trên server phù hợp.

### Tài liệu tham khảo

- [Spring LDAP — Advanced LDAP Queries](https://docs.spring.io/spring-ldap/reference/query-builder-advanced.html).
- [Spring LDAP API — LdapQueryBuilder](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/query/LdapQueryBuilder.html).
- [Spring LDAP API — Filter package](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/filter/package-summary.html).
- [Spring LDAP API — AndFilter](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/filter/AndFilter.html).
- [Spring LDAP API — OrFilter](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/filter/OrFilter.html).
- [Spring LDAP API — EqualsFilter](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/filter/EqualsFilter.html).
- [RFC 4511 — LDAP: The Protocol](https://www.rfc-editor.org/rfc/rfc4511).
- [RFC 4515 — LDAP Search Filter String Representation](https://www.rfc-editor.org/rfc/rfc4515).

**Kết luận:** xử lý filter tùy chọn an toàn bắt đầu bằng việc xác định điều kiện bắt buộc, hợp đồng input và ý nghĩa AND/OR. Chỉ bỏ node tương ứng với một field thực sự vắng mặt; từ chối search khi mọi tiêu chí đều trống; giữ base DN, scope và tenant boundary cố định; encode giá trị bằng Filter API; giới hạn kết quả và kiểm thử rằng LDAP không được gọi trong trường hợp không hợp lệ. Nếu cần liệt kê dữ liệu, hãy thiết kế browse riêng với quyền và paging phù hợp.
