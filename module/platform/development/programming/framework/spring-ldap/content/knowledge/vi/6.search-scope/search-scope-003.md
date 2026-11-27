# Subtree search và toàn bộ nhánh bên dưới trong LDAP

## 1. Bài toán: tìm người dùng ở nhiều cấp OU

Trong một hệ thống quản lý nhân sự, các tài khoản LDAP có thể được đặt trực tiếp ở `ou=people` hoặc nằm sâu hơn trong các đơn vị tổ chức như `ou=engineering`, `ou=sales`. Khi ứng dụng tìm người dùng theo `uid`, một tìm kiếm chỉ xét các entry con trực tiếp có thể bỏ sót nhân sự ở những OU con.

**Subtree search** giải quyết trường hợp này: truy vấn xét **entry tại base DN và tất cả entry hậu duệ ở mọi độ sâu** trong nhánh đó, rồi trả về những entry thỏa bộ lọc (*LDAP filter*) và quyền truy cập. Trong Spring LDAP, ta có thể thiết lập phạm vi này thông qua `LdapQuery` hoặc `SearchControls` khi dùng `LdapTemplate`.

Bài học thuộc chương **Search scope** và đặt trọng tâm vào câu hỏi: *Khi nào cần tìm toàn bộ nhánh bên dưới, phạm vi thực sự bao gồm những gì và làm thế nào thực hiện an toàn, hiệu quả?* Các khái niệm DN, base DN, schema, filter, `ContextSource`, TLS, pooling và xử lý lỗi vẫn là nền tảng để truy vấn đúng.

Sau bài học, bạn có thể:

- Giải thích sự khác nhau giữa **base**, **one-level** và **subtree** scope bằng cây LDAP cụ thể.
- Viết lệnh `ldapsearch` và mã Spring LDAP tìm qua nhiều cấp OU.
- Phân biệt **phạm vi duyệt cây** với **điều kiện lọc entry**.
- Xác định nguyên nhân khi kết quả thiếu, thừa hoặc truy vấn subtree quá chậm.
- Đặt ranh giới tìm kiếm, quyền đọc, TLS, giới hạn và kiểm thử phù hợp cho môi trường thực tế.

## 2. Cây thư mục mẫu và ý nghĩa của “toàn bộ nhánh”

Giả sử dịch vụ thư mục có cấu trúc sau:

```text
dc=example,dc=org                     (gốc naming context)
|
+-- ou=people                         (base tìm kiếm được chọn)
|   |
|   +-- uid=alice                     (người dùng cấp trực tiếp)
|   |
|   +-- ou=engineering                (OU con cấp 1)
|   |   |
|   |   +-- uid=bob                   (người dùng cấp 2)
|   |   |
|   |   +-- ou=platform               (OU con cấp 2)
|   |       |
|   |       +-- uid=carol             (người dùng cấp 3)
|   |
|   +-- ou=sales
|       |
|       +-- uid=david
|
+-- ou=groups                         (nhánh bên cạnh people)
    |
    +-- cn=developers
```

DN của một số entry ở cây trên:

```text
ou=people,dc=example,dc=org
uid=alice,ou=people,dc=example,dc=org
uid=bob,ou=engineering,ou=people,dc=example,dc=org
uid=carol,ou=platform,ou=engineering,ou=people,dc=example,dc=org
uid=david,ou=sales,ou=people,dc=example,dc=org
cn=developers,ou=groups,dc=example,dc=org
```

Khi chọn `ou=people,dc=example,dc=org` làm base DN, **subtree** bao gồm chính `ou=people` cùng `alice`, `ou=engineering`, `bob`, `ou=platform`, `carol`, `ou=sales` và `david`. Nó **không bao gồm** `ou=groups` hoặc `cn=developers`, vì đây là nhánh ngang hàng, không phải hậu duệ của `ou=people`.

Lưu ý: phạm vi bao gồm một entry không đồng nghĩa entry đó sẽ xuất hiện trong kết quả. Một LDAP search trả về các entry **vừa nằm trong phạm vi, vừa thỏa filter, vừa được máy chủ cho phép hiển thị**. Chẳng hạn `(objectClass=inetOrgPerson)` thường khớp người dùng, không khớp các OU có `objectClass=organizationalUnit`.

## 3. So sánh ba search scope

LDAP định nghĩa ba phạm vi tìm kiếm phổ biến:

| Search scope | Ký hiệu `ldapsearch` | Entry được xét với base `ou=people` | Điểm cần nhớ |
| --- | --- | --- | --- |
| **Base / object** | `-s base` | Chỉ entry `ou=people` | Không tìm các entry con |
| **One-level** | `-s one` | `uid=alice`, `ou=engineering`, `ou=sales` | Chỉ con trực tiếp; không gồm base |
| **Subtree** | `-s sub` | `ou=people` và toàn bộ entry con ở mọi cấp | **Gồm cả base** và mọi hậu duệ |

Nếu filter là `(objectClass=*)`, kết quả lý tưởng của từng scope có thể bao gồm tất cả những entry được liệt kê trong cột tương ứng, khi tài khoản có quyền đọc và máy chủ không áp giới hạn. Nếu filter chuyển thành `(objectClass=inetOrgPerson)`:

| Scope | Các tài khoản có thể trả về trong cây mẫu |
| --- | --- |
| Base | Không có, vì `ou=people` không phải `inetOrgPerson` |
| One-level | `alice` |
| Subtree | `alice`, `bob`, `carol`, `david` |

Như vậy, `subtree` **không có nghĩa** “tìm trên toàn bộ LDAP server”. Nó chỉ duyệt toàn bộ nhánh bắt đầu ở **base DN đã chọn**. Một máy chủ có thể phục vụ nhiều naming context, và truy vấn subtree không tự đi qua tất cả những naming context khác nhau.

### 3.1. Base DN, scope và filter là ba thành phần độc lập

Một yêu cầu tìm kiếm LDAP có thể hình dung là:

```text
search(base DN, search scope, LDAP filter, attributes, limits, ...)

base DN     = ou=people,dc=example,dc=org
scope       = subtree
filter      = (objectClass=inetOrgPerson)
attributes  = uid, cn, mail
```

Ba quyết định không thay thế nhau:

1. **Base DN:** bắt đầu ở đâu trong cây thư mục?
2. **Scope:** xét chính entry base, một cấp con hay tất cả cấp con?
3. **Filter:** trong những entry đã được xét, entry nào thỏa điều kiện?

Nếu người dùng `bob` không được trả về, chỉ đổi filter có thể không giúp ích khi scope đang là one-level. Ngược lại, đổi scope thành subtree cũng không giúp truy vấn `(uid=nonexistent)` tìm được một tài khoản không tồn tại.

### 3.2. Subtree có luôn lấy được mọi hậu duệ không?

Không. Đây là **phạm vi logic** mà client yêu cầu. Kết quả thực tế có thể bị ảnh hưởng bởi:

- **ACL và chính sách bảo mật:** client chỉ nhìn thấy những entry/thuộc tính mà tài khoản bind được phép đọc; một số máy chủ cố ý che giấu sự tồn tại của entry.
- **Size limit, time limit, paging:** máy chủ có thể dừng trước khi trả hết dữ liệu hoặc yêu cầu client phân trang.
- **Referral, alias và naming context:** việc đi theo tham chiếu hoặc alias phụ thuộc cấu hình client và khả năng máy chủ; subtree không tự đảm bảo tìm ở server hoặc partition khác.
- **Schema và filter:** entry trong nhánh nhưng không khớp filter sẽ không xuất hiện.

Vì vậy, hãy tránh phát biểu rằng subtree luôn trả về “mọi entry có mặt trên máy chủ”. Cách diễn đạt đúng là *subtree yêu cầu tìm trong entry base và mọi hậu duệ thuộc phạm vi server cho phép xử lý*.

## 4. Thử với `ldapsearch`: nhìn rõ kết quả theo scope

Ví dụ dưới đây dùng OpenLDAP command-line tools. Mọi hostname, DN và tài khoản đều là dữ liệu giả định dành cho LDAP thử nghiệm.

### 4.1. Chỉ xét entry base

```bash
ldapsearch -LLL -x \
  -H "ldaps://ldap.example.org:636" \
  -D "cn=directory-reader,ou=system,dc=example,dc=org" -W \
  -b "ou=people,dc=example,dc=org" -s base \
  "(objectClass=*)" dn objectClass ou
```

Lệnh này chỉ yêu cầu entry `ou=people,dc=example,dc=org`. Không có người dùng bên dưới nào được duyệt, kể cả `alice`.

### 4.2. Chỉ xét con trực tiếp

```bash
ldapsearch -LLL -x \
  -H "ldaps://ldap.example.org:636" \
  -D "cn=directory-reader,ou=system,dc=example,dc=org" -W \
  -b "ou=people,dc=example,dc=org" -s one \
  "(objectClass=inetOrgPerson)" dn uid cn
```

Nếu mô hình cây giống phần 2, truy vấn này tìm được `alice`, nhưng **không tìm thấy** `bob`, `carol`, `david` vì các entry này nằm dưới OU con. Các entry OU cấp trực tiếp cũng bị lọc ra vì không thuộc `inetOrgPerson`.

### 4.3. Tìm trong toàn bộ subtree

```bash
ldapsearch -LLL -x \
  -H "ldaps://ldap.example.org:636" \
  -D "cn=directory-reader,ou=system,dc=example,dc=org" -W \
  -b "ou=people,dc=example,dc=org" -s sub \
  "(objectClass=inetOrgPerson)" dn uid cn mail
```

Truy vấn này có thể tìm `alice`, `bob`, `carol`, `david` bất kể độ sâu OU, miễn là entry thỏa filter và được phép đọc. Thứ tự trả về **không được bảo đảm** chỉ bởi scope; nếu giao diện cần sắp xếp ổn định, ứng dụng phải sắp xếp hoặc dùng khả năng sort phù hợp của LDAP server.

Ở cả ba lệnh, `-D` xác định danh tính bind, `-W` yêu cầu nhập mật khẩu qua lời nhắc và `-H ldaps://...` yêu cầu kết nối qua TLS. Ứng dụng và công cụ phải xác minh chứng chỉ, hostname và chuỗi tin cậy; không tắt kiểm tra TLS để tiện thử nghiệm.

### 4.4. Tìm một UID trong toàn bộ OU con

Nếu chỉ cần tìm một người dùng có `uid=bob` mà chưa biết họ đang ở OU nào:

```bash
ldapsearch -LLL -x \
  -H "ldaps://ldap.example.org:636" \
  -D "cn=directory-reader,ou=system,dc=example,dc=org" -W \
  -b "ou=people,dc=example,dc=org" -s sub \
  "(&(objectClass=inetOrgPerson)(uid=bob))" dn cn uid
```

LDAP không bắt buộc `uid` là duy nhất trong toàn bộ subtree. Hai entry ở hai OU khác nhau có thể cùng một giá trị `uid`, tùy chính sách server. Nếu nghiệp vụ yêu cầu một tài khoản duy nhất, phải xử lý trường hợp nhiều kết quả hoặc áp dụng ràng buộc định danh độc lập.

## 5. Subtree search trong Spring LDAP

Spring LDAP cung cấp `LdapTemplate` để làm việc với LDAP qua `ContextSource`, cùng `LdapQueryBuilder` để biểu đạt base, scope, attributes và filter. Phần này minh họa cách tìm người dùng ở nhiều OU mà không cần trực tiếp quản lý `DirContext` hay `NamingEnumeration` như khi dùng JNDI thuần.

### 5.1. Cấu hình `LdapContextSource`

```java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.core.support.LdapContextSource;

@Configuration
class DirectoryConfig {
    @Bean
    LdapContextSource ldapContextSource(
            @Value("${app.ldap.url}") String url,
            @Value("${app.ldap.base}") String base,
            @Value("${app.ldap.bind-dn}") String bindDn,
            @Value("${app.ldap.bind-password}") String password) {
        LdapContextSource source = new LdapContextSource();
        source.setUrl(url);
        source.setBase(base);
        source.setUserDn(bindDn);
        source.setPassword(password);
        return source;
    }

    @Bean
    LdapTemplate ldapTemplate(LdapContextSource ldapContextSource) {
        return new LdapTemplate(ldapContextSource);
    }
}
```

```yaml
# application.yml
app:
  ldap:
    url: ${LDAP_URL:ldaps://ldap.example.org:636}
    base: dc=example,dc=org
    bind-dn: ${LDAP_BIND_DN}
    bind-password: ${LDAP_BIND_PASSWORD}
```

Trong cấu hình này, `app.ldap.base` là **DN gốc được dùng chung** bởi `ContextSource`. Những DN base truyền vào `LdapTemplate` hoặc `LdapQuery` thông thường được hiểu **tương đối** với `dc=example,dc=org`. Vì vậy, base truy vấn `ou=people` tương ứng với `ou=people,dc=example,dc=org` trên máy chủ.

Đừng truyền lại cả `dc=example,dc=org` vào vị trí base tương đối nếu `ContextSource` đã đặt đúng hậu tố đó, vì có thể vô tình tạo DN không đúng như dự kiến. Ngược lại, nếu muốn tìm trong `ou=groups`, chỉ cần thay base truy vấn phù hợp trong cùng naming context.

### 5.2. Viết `LdapQuery` với `SearchScope.SUBTREE`

Ví dụ repository dưới đây tìm tên hiển thị của tất cả entry có object class `inetOrgPerson` ở mọi cấp dưới `ou=people`:

```java
import java.util.List;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.SearchScope;
import org.springframework.stereotype.Repository;

import static org.springframework.ldap.query.LdapQueryBuilder.query;

@Repository
class UserDirectoryRepository {
    private final LdapTemplate ldapTemplate;

    UserDirectoryRepository(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    List<String> listDisplayNamesFromAllSubOus() {
        LdapQuery ldapQuery = query()
                .base("ou=people")
                .searchScope(SearchScope.SUBTREE)
                .attributes("cn")
                .where("objectClass").is("inetOrgPerson");

        return ldapTemplate.search(
                ldapQuery,
                (AttributesMapper<String>) attrs ->
                        String.valueOf(attrs.get("cn").get())
        );
    }
}
```

Trong schema chuẩn, `inetOrgPerson` kế thừa `person` có thuộc tính `cn` bắt buộc; ví dụ vì vậy đọc `cn` trực tiếp. Với schema khác hoặc filter khác, mapper nên kiểm tra thuộc tính tồn tại, có nhiều giá trị hay không trước khi dùng `.get()`.

Các phần trong query có vai trò độc lập:

| Câu lệnh | Ý nghĩa |
| --- | --- |
| `.base("ou=people")` | Chọn nhánh bắt đầu (tương đối với base của `ContextSource`) |
| `.searchScope(SearchScope.SUBTREE)` | Xét `ou=people` và mọi hậu duệ ở bất kỳ cấp nào |
| `.attributes("cn")` | Chỉ yêu cầu thuộc tính `cn` của entry trả về |
| `.where("objectClass").is("inetOrgPerson")` | Chỉ chọn các entry có object class yêu cầu |
| `ldapTemplate.search(...)` | Gửi truy vấn và ánh xạ danh sách entry thành `List<String>` |

Mặc dù subtree xét cả OU base, query trên chỉ trả về entry người dùng phù hợp filter. Một tìm kiếm không có kết quả thường trả danh sách rỗng, nhưng **base không tồn tại, lỗi kết nối hoặc lỗi quyền** có thể phát sinh ngoại lệ và phải được xử lý riêng.

### 5.3. Tìm người dùng với dữ liệu nhập từ API

Khi người dùng nhập `uid`, hãy xây filter qua builder thay vì ghép chuỗi LDAP trực tiếp:

```java
List<String> findDisplayNamesByUid(String uid) {
    if (uid == null || uid.isBlank()) {
        throw new IllegalArgumentException("uid must not be blank");
    }

    LdapQuery ldapQuery = query()
            .base("ou=people")
            .searchScope(SearchScope.SUBTREE)
            .where("uid").is(uid);

    return ldapTemplate.search(
            ldapQuery,
            (AttributesMapper<String>) attrs ->
                    String.valueOf(attrs.get("cn").get())
    );
}
```

Đoạn mã này là phương thức bổ sung trong lớp repository có biến `ldapTemplate` và các import như ở ví dụ trước. Giá trị `uid` được đưa vào query builder để escape theo cú pháp **LDAP filter**, tránh biến dấu `*`, dấu ngoặc hay ký tự đặc biệt trong đầu vào thành một phần cú pháp filter ngoài ý muốn. Nếu muốn kết quả luôn có `cn`, có thể bổ sung điều kiện object class hoặc xử lý vắng thuộc tính trong mapper.

### 5.4. Dùng `SearchControls.SUBTREE_SCOPE`

Đối với trường hợp cần tùy chỉnh giới hạn và danh sách thuộc tính bằng API quen thuộc của JNDI, `LdapTemplate` có thể nhận `SearchControls`:

```java
import java.util.List;
import javax.naming.directory.SearchControls;
import org.springframework.ldap.core.AttributesMapper;

SearchControls controls = new SearchControls();
controls.setSearchScope(SearchControls.SUBTREE_SCOPE);
controls.setCountLimit(200L);
controls.setTimeLimit(5000); // mili-giây
controls.setReturningAttributes(new String[] {"cn", "uid"});

List<String> names = ldapTemplate.search(
        "ou=people",
        "(objectClass=inetOrgPerson)",
        controls,
        (AttributesMapper<String>) attrs ->
                String.valueOf(attrs.get("cn").get())
);
```

Đây là đoạn minh họa trong một lớp đã có `ldapTemplate`. `SearchControls.SUBTREE_SCOPE` của JNDI và `SearchScope.SUBTREE` của Spring LDAP cùng diễn đạt **phạm vi subtree**, chỉ thuộc về hai kiểu API khác nhau. Mức giới hạn 200 entry hoặc 5.000 mili-giây là số **minh họa**, không phải mặc định khuyến nghị cho mọi hệ thống. Quy định giới hạn phía server có thể nghiêm ngặt hơn; khi bị vượt giới hạn, API có thể trả lỗi thay vì lặng lẽ cho một danh sách hoàn chỉnh.

### 5.5. `LdapClient` và ODM có thay đổi ý nghĩa scope không?

Không. `LdapClient` cung cấp cách gọi fluent ở các phiên bản Spring LDAP có hỗ trợ, còn ODM ánh xạ entry thành đối tượng Java. Chúng có thể làm mã dễ đọc hơn, nhưng yêu cầu LDAP vẫn phải chọn base DN, scope và filter phù hợp. ODM không làm subtree tự vượt qua ACL hoặc khác naming context. Khi sử dụng API mới, hãy đối chiếu tên phương thức và cách cấu hình scope theo phiên bản thư viện đang chạy.

## 6. Khi nào nên chọn subtree và khi nào không?

Subtree phù hợp khi **độ sâu OU không cố định** hoặc entry có thể thay đổi vị trí theo cơ cấu tổ chức. Ví dụ, một hệ thống đăng nhập cần tìm tài khoản qua nhiều OU mà không muốn phải liệt kê từng nhánh phòng ban bằng tay.

Tuy nhiên, subtree không mặc nhiên là lựa chọn tối ưu cho mọi thao tác:

| Tình huống | Scope nên cân nhắc | Lý do |
| --- | --- | --- |
| Kiểm tra thuộc tính của một entry có DN đã biết | Base hoặc `lookup` theo DN | Không cần duyệt các hậu duệ |
| Danh sách các OU con trực tiếp của một OU | One-level | Không lẫn OU cháu và các cấp sâu hơn |
| Tìm người dùng rải trong nhiều OU con | Subtree | Bao phủ các cấp tổ chức khác nhau |
| Tìm nhóm chỉ nằm trực tiếp trong `ou=groups` | One-level | Giới hạn phạm vi đủ dùng |
| Tìm trong cả người dùng và nhóm ở hai nhánh ngang cấp | Chọn base cha phù hợp hoặc tách truy vấn | Subtree trên riêng `ou=people` sẽ không đến `ou=groups` |
| Tìm một entry cụ thể đã biết DN | `lookup` | Chính xác theo định danh, không cần filter subtree |

Nếu chỉ cần kiểm tra xem một entry DN cụ thể tồn tại hay không, `LdapTemplate.lookup(...)` hoặc cách truy cập theo DN thường diễn đạt đúng mục tiêu hơn một subtree search rộng với filter `uid`.

### 6.1. Chọn base hẹp nhất vẫn bao phủ nhu cầu

Với cây mẫu, dùng base `dc=example,dc=org` và subtree sẽ xét cả `ou=people` và `ou=groups`. Nếu nghiệp vụ chỉ tìm người dùng, `ou=people` là base tốt hơn vì không quét các nhánh không liên quan và dễ giới hạn ACL. Nhưng nếu người dùng thực sự được lưu ở nhiều naming context độc lập, chọn một base hẹp đơn lẻ có thể bỏ sót dữ liệu; cần thiết kế nhiều truy vấn hoặc cơ chế truy cập liên miền đúng khả năng server.

Đừng suy luận base DN chỉ từ tên miền ứng dụng. Cần kiểm tra cấu trúc LDAP thực, naming context, vị trí entry và phạm vi cấp quyền của tài khoản bind.

## 7. Hiệu năng, giới hạn và tính đầy đủ của kết quả

Subtree có thể bao phủ hàng nghìn hoặc hàng triệu entry. Việc dùng đúng scope về mặt cú pháp chưa đảm bảo thời gian phản hồi, tài nguyên máy chủ hay tính đầy đủ của kết quả.

### 7.1. Filter có tính chọn lọc và chỉ mục

Hãy kết hợp subtree với filter đủ hẹp và thuộc tính được máy chủ lập chỉ mục phù hợp. Ví dụ, tìm một `uid` cụ thể thường có thể ít tốn tài nguyên hơn lấy toàn bộ `(objectClass=*)` rồi lọc trong Java. Việc có index trên `uid` hoặc `objectClass` tùy cách quản trị LDAP; Spring LDAP không tự tạo index.

Ưu tiên chỉ yêu cầu các thuộc tính cần thiết như `uid`, `cn`, `mail`, thay vì đọc mọi thuộc tính. Một số thuộc tính như `createTimestamp` là thuộc tính vận hành và có thể phải yêu cầu tường minh mới xuất hiện trong kết quả.

### 7.2. Giới hạn kết quả, phân trang và thời gian chờ

Với danh sách người dùng lớn, cần xem xét **server-side size limit**, client-side count/time limit và phân trang LDAP (ví dụ Simple Paged Results control nếu máy chủ hỗ trợ). Những giới hạn này có mục đích khác nhau:

| Cơ chế | Mục tiêu | Điều cần chú ý |
| --- | --- | --- |
| Count limit | Không nhận quá nhiều entry trong một thao tác | Giới hạn không phải bằng chứng mọi entry đã được duyệt |
| Time limit | Không để truy vấn chiếm tài nguyên vô hạn | Quá hạn có thể gây lỗi và không có toàn bộ kết quả |
| Paging | Đọc tập kết quả lớn theo từng trang | Cần xử lý cookie/trạng thái phiên đúng cách và xác nhận server hỗ trợ |
| Thu hẹp base/filter | Giảm tập entry phải xét | Thường hiệu quả hơn dựa hoàn toàn vào tăng giới hạn |

**Không coi kết quả đã bị cắt do giới hạn là danh sách đầy đủ.** Nếu API xuất báo cáo kiểm toán hoặc đồng bộ người dùng, nên có chiến lược phát hiện giới hạn, tiếp tục phân trang và xác minh tổng số/điều kiện hoàn tất theo khả năng máy chủ.

### 7.3. Pooling và TLS

`ContextSource` có thể được cấu hình để dùng lại context trong một số trường hợp, nhưng pooling không sửa được filter quá rộng. Khi sử dụng nhiều danh tính bind hoặc StartTLS, cần đánh giá cơ chế tái sử dụng kết nối tương ứng để tránh chia sẻ context không đúng danh tính hoặc trạng thái bảo mật. Mọi truy vấn chứa dữ liệu danh tính nên dùng TLS đã xác minh chứng chỉ và hostname.

## 8. Quyền truy cập và các lỗi thường gặp

Search scope chỉ xác định **những entry có thể được xét về vị trí**. Máy chủ LDAP vẫn kiểm tra quyền đọc của tài khoản bind đối với entry và từng thuộc tính, cùng quy định schema và chính sách tìm kiếm.

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| One-level tìm `alice` nhưng không tìm `bob` | `bob` nằm dưới OU con | Dùng subtree nếu cần tìm nhiều cấp |
| Subtree vẫn không tìm `bob` | Base sai, filter không khớp, entry bị ACL che, hoặc giới hạn server | Kiểm tra DN thực, quyền, filter và kết quả ldapsearch |
| Không tìm được `ou=groups` | `ou=groups` nằm ngoài subtree của `ou=people` | Chọn base cha phù hợp hoặc truy vấn riêng |
| LDAP **32 / `noSuchObject`** | Base DN không tồn tại hoặc máy chủ không thể trả về đối tượng | Xác minh base DN và cấu trúc cây |
| LDAP **50 / `insufficientAccessRights`** | Thiếu quyền cho thao tác hoặc tài nguyên | Xem chính sách ACL bằng tài khoản thử nghiệm đúng quyền |
| LDAP **4 / `sizeLimitExceeded`** | Kết quả vượt giới hạn máy chủ/client | Thu hẹp truy vấn, thiết kế paging nếu phù hợp |
| LDAP **3 / `timeLimitExceeded`** | Truy vấn vượt giới hạn thời gian | Kiểm tra index, tải máy chủ, filter và thời hạn |
| Lỗi bind hoặc TLS | Thông tin xác thực, truststore, chứng chỉ hay mạng không hợp lệ | Phân biệt lỗi kết nối với “không có người dùng” |

Thông báo và mã lỗi cụ thể có thể thay đổi theo sản phẩm LDAP và chính sách ẩn thông tin. Một số server không hiển thị entry không có quyền cho client, khiến truy vấn trả danh sách rỗng thay vì báo lỗi ACL. Vì thế, luôn kiểm tra với tài khoản kiểm thử được cấp quyền phù hợp trước khi kết luận dữ liệu không tồn tại.

Spring LDAP dịch ngoại lệ từ JNDI sang hệ ngoại lệ của Spring LDAP để ứng dụng xử lý nhất quán hơn. Khi bắt lỗi, nên phân biệt **kết quả rỗng hợp lệ** với **không thể truy vấn**; đừng nuốt mọi ngoại lệ rồi trả `Collections.emptyList()` vì có thể che giấu sự cố bảo mật hoặc đồng bộ dữ liệu.

## 9. Kiểm thử: chứng minh subtree bao phủ đúng độ sâu

Hãy chuẩn bị một thư mục LDAP **dành cho kiểm thử**, không sử dụng tài khoản và dữ liệu thật. Tạo nhánh `ou=people` và các OU con như sơ đồ ở phần 2, cùng ít nhất ba người dùng ở những độ sâu khác nhau. Các entry cần tuân thủ schema (`inetOrgPerson` yêu cầu `cn`, `sn`, v.v.) và tài khoản thử nghiệm phải có quyền đọc phù hợp.

### 9.1. Ma trận kết quả mong đợi

Giả sử có bốn người dùng `alice`, `bob`, `carol`, `david` như sơ đồ và filter `(objectClass=inetOrgPerson)`:

| Base DN | Scope | Kết quả mong đợi |
| --- | --- | --- |
| `ou=people,...` | Base | Không có tài khoản |
| `ou=people,...` | One-level | `alice` |
| `ou=people,...` | Subtree | `alice`, `bob`, `carol`, `david` |
| `ou=engineering,ou=people,...` | Subtree | `bob`, `carol` |
| `ou=platform,ou=engineering,ou=people,...` | Subtree | `carol` |
| `ou=groups,...` | Subtree | Không có tài khoản của nhánh `people` |

Khi kiểm thử, hãy so sánh tập DN hoặc `uid` nhận được, **không phụ thuộc thứ tự** trả về của LDAP. Nếu môi trường LDAP cho phép trùng `uid` ở những OU khác nhau, nên so sánh DN thực của các entry để tránh nhầm lẫn.

### 9.2. Các trường hợp cần kiểm tra

1. **Base là entry OU:** dùng `(objectClass=*)` với subtree và xác nhận `ou=people` cũng thuộc phạm vi (nếu ACL cho phép).
2. **Filter chỉ chọn user:** đổi sang `(objectClass=inetOrgPerson)` và xác nhận OU bị loại dù scope vẫn là subtree.
3. **Độ sâu:** đưa `carol` vào OU con cấp sâu, đối chiếu one-level với subtree.
4. **Nhánh ngang hàng:** xác nhận `cn=developers,ou=groups` không thuộc subtree `ou=people`.
5. **Thiếu quyền:** dùng tài khoản có quyền đọc giới hạn để xác minh kết quả có thể khác tài khoản kiểm thử đầy đủ quyền.
6. **Sai DN:** dùng base không tồn tại để ghi nhận lỗi và đối chiếu với một lần tìm không khớp filter.
7. **Giới hạn:** đặt count limit thấp trên tập dữ liệu có nhiều entry, kiểm tra ứng dụng không coi kết quả bị giới hạn là đầy đủ.
8. **Input chứa ký tự đặc biệt:** tìm `uid` chứa `*`, dấu ngoặc hoặc dấu gạch chéo ngược bằng query builder, xác nhận không biến thành wildcard hoặc biểu thức filter bất ngờ.
9. **Kết nối:** chạy qua LDAPS/StartTLS có chứng chỉ tin cậy, mật khẩu bind từ biến môi trường và log không chứa dữ liệu nhạy cảm.

Nếu bộ test có thao tác tạo và xóa entry, hãy dùng một OU kiểm thử riêng, tạo DN duy nhất cho từng ca và dọn dữ liệu sau test. Thử nghiệm đọc với tài khoản không có quyền cần được thực hiện trên môi trường cho phép kiểm tra ACL, tránh sửa cấu hình quyền trên hệ thống thật chỉ để test.

## 10. Bài thực hành có hướng dẫn

**Bối cảnh:** Ứng dụng Spring cần tra cứu người dùng trên toàn bộ cấu trúc phòng ban, nhưng không được quét nhánh nhóm và không được bỏ sót nhân viên nằm dưới OU con.

1. Từ cây thư mục ở phần 2, viết ra DN đầy đủ của `alice`, `bob`, `carol`, `david` và xác định entry nào là con trực tiếp của `ou=people`.
2. Với base `ou=people,dc=example,dc=org`, dự đoán các kết quả cho `-s base`, `-s one`, `-s sub` trước khi chạy `ldapsearch`.
3. Thực thi cả ba truy vấn trên LDAP thử nghiệm với filter `(objectClass=inetOrgPerson)`. Giải thích vì sao chỉ subtree tìm được `carol`.
4. Trong Spring LDAP, cấu hình `ContextSource` với base `dc=example,dc=org` và xây `LdapQuery` có `.base("ou=people")`, `.searchScope(SearchScope.SUBTREE)`.
5. Tạo một phương thức tìm UID bằng `where("uid").is(uid)`; thử UID có thật ở OU sâu, UID không tồn tại và chuỗi có ký tự đặc biệt.
6. Giới hạn attributes trả về còn `cn` và `uid`. Đặt time/count limit phù hợp với dữ liệu thử nghiệm, xác nhận ứng dụng phân biệt kết quả đầy đủ và kết quả bị giới hạn.
7. Di chuyển một entry thử nghiệm sang OU con khác trong cùng nhánh `people` bằng công cụ quản trị phù hợp; kiểm tra subtree vẫn tìm thấy entry trong khi truy vấn one-level có thể thay đổi kết quả.
8. Thử truy vấn dưới `ou=groups` và giải thích vì sao filter đúng vẫn không tìm được người dùng ở `ou=people`.

**Câu hỏi tự kiểm tra:**

- Scope nào gồm cả entry base lẫn tất cả hậu duệ? One-level có bao gồm entry base không?
- Nếu `(objectClass=*)` trả về `ou=people`, vì sao `(objectClass=inetOrgPerson)` có thể không trả về entry đó?
- Khi dùng `ContextSource` base `dc=example,dc=org`, `.base("ou=people")` thực chất tìm từ DN nào?
- Vì sao subtree không tự tìm được dữ liệu ở một naming context khác hoặc nhánh ngang hàng?
- Một subtree search trả ít kết quả hơn dự kiến có thể do những nguyên nhân nào ngoài filter?
- Vì sao không nên coi size-limit/time-limit là một kết quả tìm kiếm đầy đủ?

## 11. Ghi nhớ

**Subtree search** là phạm vi LDAP bao gồm **entry tại base DN và toàn bộ entry bên dưới ở mọi độ sâu**. Nó khác one-level (chỉ con trực tiếp) và base (chỉ entry gốc), đồng thời **không tự mở rộng sang các nhánh ngang hàng hay toàn bộ máy chủ**. Trong Spring LDAP, bạn có thể dùng `LdapQueryBuilder` với `SearchScope.SUBTREE` hoặc `SearchControls.SUBTREE_SCOPE` cùng `LdapTemplate`. Kết quả còn phụ thuộc vào filter, schema, ACL, giới hạn server và trạng thái kết nối. Chọn base phù hợp, dùng query builder để escape giá trị, giới hạn số lượng/thuộc tính trả về, xác minh TLS và kiểm thử với entry ở nhiều cấp OU sẽ giúp truy vấn subtree đầy đủ theo yêu cầu và an toàn khi vận hành.
