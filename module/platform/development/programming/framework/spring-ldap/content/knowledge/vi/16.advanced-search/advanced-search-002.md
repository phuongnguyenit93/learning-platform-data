# Search result iteration và callback handler trong Spring LDAP

## 1. Vấn đề: xử lý từng kết quả mà không cần giữ toàn bộ List

Một dịch vụ quản trị danh bạ cần duyệt tất cả tài khoản thuộc `ou=people` để tính số lượng hồ sơ, ghi thống kê hoặc chuyển từng hồ sơ sang một thành phần xử lý khác. Nếu dùng:

~~~java
List<String> names = ldapTemplate.search(
        "ou=people",
        "(objectClass=inetOrgPerson)",
        (AttributesMapper<String>) attributes ->
                String.valueOf(attributes.get("cn").get())
);
~~~

`LdapTemplate` thu thập các giá trị do mapper trả về vào một `List`. Cách này rất thuận tiện khi cần danh sách nhỏ để trả cho controller. Nhưng nếu truy vấn khớp hàng chục nghìn entry, việc lưu cả danh sách trong bộ nhớ có thể không cần thiết.

Trong **Spring LDAP**, giao diện `NameClassPairCallbackHandler` cung cấp cách **xử lý lần lượt từng kết quả** trong khi `LdapTemplate.search(...)` đang duyệt kết quả trả về từ LDAP provider. Với overload callback, phương thức `search` trả về `void` thay vì gom tất cả đối tượng đã map vào một `List`.

Điểm quan trọng: **callback không đồng nghĩa truy vấn bất đồng bộ, reactive stream hoặc server-side pagination**. Nó chỉ mô tả cách chương trình nhận và xử lý từng phần tử của một lần tìm kiếm.

Bài học thuộc chương **Search nâng cao** của module **Spring LDAP**, nối từ DN, schema, LDAP filter, scope, `ContextSource` và `LdapTemplate` tới xử lý dữ liệu an toàn, xác thực/TLS, giới hạn truy vấn, paging và kiểm thử.

**Mục tiêu sau bài học:** bạn sẽ phân biệt ba API mapping/iteration; dùng `NameClassPairCallbackHandler` đúng chữ ký; nhận `SearchResult` và đọc `Attributes`; kiểm soát tải bộ nhớ, lỗi callback và side effect; không nhầm iteration với paging; và kiểm thử trên LDAP server có ACL/TLS phù hợp.

## 2. Luồng Search trong Spring LDAP

~~~text
Ứng dụng gọi ldapTemplate.search(...)
             |
             v
ContextSource cung cấp read-only DirContext
             |
             v
LDAP Search(base, scope, filter, attributes, limits)
             |
             v
JNDI NamingEnumeration<SearchResult>
             |
     +-------+--------+
     |                |
  List mapper     Callback handler
     |                |
  map entry         xử lý entry
  và gom List       ngay trong lượt duyệt
     |                |
     +-------+--------+
             |
             v
LdapTemplate đóng enumeration/context,
dịch lỗi JNDI theo hợp đồng framework
~~~

Trên đường đi này có ba lớp trách nhiệm:

| Thành phần | Trách nhiệm |
| --- | --- |
| **LDAP server** | Xác định entry thỏa base/scope/filter/schema/ACL, áp giới hạn server |
| **JNDI provider và LdapTemplate** | Gửi Search, duyệt các phần tử và quản lý tài nguyên kết nối/enumeration |
| **Mapper hoặc callback của ứng dụng** | Chuyển `SearchResult` thành DTO, đếm, tổng hợp hoặc chuyển mỗi entry tới một consumer |

Mọi chiến lược đều phụ thuộc dữ liệu server thực sự trả về. Nếu ACL che một số entry hoặc thuộc tính, callback không thể tự xem lại dữ liệu đó.

### 2.1. Ba khái niệm cần phân biệt

**Iteration:** duyệt từng kết quả của một LDAP Search, có thể gọi callback cho mỗi kết quả.

**Materialization:** thu thập toàn bộ những kết quả đã map trong một `List<T>` ở client.

**Paging:** yêu cầu server trả từng **trang** của một tập kết quả theo LDAP control, quản lý cookie và nhiều Search request.

Một callback có thể tránh tự gom một `List` lớn, nhưng nếu một Search quá rộng thì server, provider và mạng vẫn có thể chịu tải. Paging giúp giới hạn cách **nhận dữ liệu từ server**; callback định nghĩa **xử lý từng entry trong phần dữ liệu nhận được**.

## 3. Những kiểu dữ liệu và callback quan trọng

Với JNDI, các kiểu liên quan là:

| Kiểu | Vai trò |
| --- | --- |
| `javax.naming.NameClassPair` | Tên và lớp của phần tử được liệt kê; kiểu cha chung |
| `javax.naming.directory.SearchResult` | Kết quả Search; kế thừa `NameClassPair`, có `getAttributes()` |
| `javax.naming.directory.Attributes` | Tập thuộc tính được trả về cho entry |
| `javax.naming.directory.Attribute` | Một loại thuộc tính, có thể chứa nhiều giá trị |
| `javax.naming.NamingEnumeration` | Cơ chế duyệt kết quả JNDI |
| `org.springframework.ldap.core.NameClassPairCallbackHandler` | Callback xử lý mỗi `NameClassPair` |
| `org.springframework.ldap.core.AttributesMapper<T>` | Chuyển `Attributes` của entry thành một đối tượng Java |
| `org.springframework.ldap.core.ContextMapper<T>` | Chuyển đối tượng context của entry, có thể kèm DN |
| `org.springframework.ldap.core.LdapTemplate` | Thực hiện Search, gọi mapper/callback và quản lý tài nguyên |

Chữ ký thiết yếu của handler:

~~~java
import javax.naming.NameClassPair;
import javax.naming.NamingException;

import org.springframework.ldap.core.NameClassPairCallbackHandler;

public class MyHandler implements NameClassPairCallbackHandler {

    @Override
    public void handleNameClassPair(NameClassPair pair)
            throws NamingException {
        // Được gọi với từng phần tử kết quả.
    }
}
~~~

Với `LdapTemplate.search(...)`, phần tử được truyền thường là `SearchResult`. Với `list(...)` hoặc `listBindings(...)`, nó có thể là `NameClassPair` hoặc `Binding` tương ứng. **Đừng cast mọi `NameClassPair` thành `SearchResult` trong một handler dùng chung cho các kiểu liệt kê khác nhau.**

### 3.1. SearchResult khác AttributesMapper

`AttributesMapper` chỉ nhận `Attributes`; nó thuận tiện khi cần `uid`, `cn`, `mail` nhưng không cần DN của entry.

`NameClassPairCallbackHandler` nhận phần tử `NameClassPair`; trong Search, có thể ép kiểu kiểm tra thành `SearchResult` rồi đọc `getAttributes()` cùng tên kết quả. Với DN, `getName()` và `getNameInNamespace()` có semantics phụ thuộc provider và môi trường tìm kiếm; **đừng tự ghép một DN từ chuỗi chưa kiểm tra**.

Nếu nghiệp vụ cần DN chuẩn để sửa entry về sau, dùng API phù hợp như `ContextMapper`/`DirContextOperations` và xác minh DN tương đối/tuyệt đối theo `ContextSource.base`.

## 4. Cấu hình ContextSource và SearchControls

Ví dụ này dùng Spring Java Config, LDAP directory **thử nghiệm**, base DN `dc=example,dc=org` và kết nối LDAPS.

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.core.support.LdapContextSource;

@Configuration
public class LdapConfiguration {

    @Bean
    public LdapContextSource ldapContextSource(
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
    public LdapTemplate ldapTemplate(LdapContextSource contextSource) {
        return new LdapTemplate(contextSource);
    }
}
~~~

~~~yaml
# application.yml — minh họa, không chứa mật khẩu thật
app:
  ldap:
    url: ${LDAP_URL:ldaps://ldap.example.org:636}
    base: dc=example,dc=org
    bind-dn: ${LDAP_BIND_DN}
    bind-password: ${LDAP_BIND_PASSWORD}
~~~

`app.ldap.*` là thuộc tính cấu hình **do ví dụ tự định nghĩa**. Dự án dùng Spring Boot auto-configuration có thể chọn nhóm `spring.ldap.*` thay vì tự khai báo bean, tùy dependency và phiên bản. Tránh tạo hai bean hạ tầng không rõ nơi sử dụng.

Chỉ đọc qua LDAP account được cấp quyền tối thiểu, xác minh chứng chỉ TLS và hostname. `ldap://` không tự kích hoạt StartTLS; cần nâng cấp kết nối đúng cách **trước khi simple bind** nếu dùng StartTLS.

### 4.1. Đặt phạm vi và thuộc tính được trả

~~~java
import javax.naming.directory.SearchControls;

SearchControls controls = new SearchControls();
controls.setSearchScope(SearchControls.SUBTREE_SCOPE);
controls.setReturningAttributes(new String[] {
        "uid", "cn", "mail"
});
controls.setCountLimit(200L);
controls.setTimeLimit(5000);
controls.setReturningObjFlag(false);
~~~

Các tham số:

- `SUBTREE_SCOPE`: tìm tại base và mọi entry con bên dưới.
- `setReturningAttributes(...)`: chỉ yêu cầu các thuộc tính mà callback cần; không làm thay đổi filter.
- `setCountLimit(200L)`: giới hạn tối đa các kết quả cần nhận ở client, không tự tạo trang tiếp theo.
- `setTimeLimit(5000)`: giới hạn thời gian Search ở lớp API JNDI, đơn vị mili-giây; khác timeout kết nối/đọc socket.
- `setReturningObjFlag(false)`: đủ cho callback chỉ đọc `SearchResult.getAttributes()`; không cần trả về đối tượng JNDI được bind.

**Count limit hoặc time limit có thể dẫn đến kết quả không đầy đủ hoặc lỗi giới hạn.** Không coi số entry đã được callback xử lý là số lượng đầy đủ trong directory khi có giới hạn hay paging chưa hoàn tất.

Nếu `ContextSource.base = dc=example,dc=org`, truyền `"ou=people"` vào search tương ứng với nhánh đầy đủ `ou=people,dc=example,dc=org`. DN tương đối này không tự tìm sang `ou=groups`.

## 5. Ví dụ chính: gọi callback cho mỗi SearchResult

Giả sử LDAP có các entry:

~~~text
dc=example,dc=org
├── ou=people
│   ├── uid=alice
│   ├── uid=bob
│   └── ou=engineering
│       └── uid=carol
└── ou=groups
    └── cn=developers
~~~

Các entry người dùng có object class `inetOrgPerson`; UID và tên được lưu dưới `uid`, `cn`. Mục tiêu: **đếm tất cả entry có UID đọc được**, không lưu lại toàn bộ kết quả vào List.

~~~java
import java.util.concurrent.atomic.AtomicInteger;
import javax.naming.NameClassPair;
import javax.naming.NamingException;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;
import javax.naming.directory.SearchControls;
import javax.naming.directory.SearchResult;

import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.core.NameClassPairCallbackHandler;

public class DirectoryCounter {
    private final LdapTemplate ldapTemplate;

    public DirectoryCounter(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public int countVisiblePeople() {
        SearchControls controls = new SearchControls();
        controls.setSearchScope(SearchControls.SUBTREE_SCOPE);
        controls.setReturningAttributes(new String[] {"uid"});
        controls.setReturningObjFlag(false);

        AtomicInteger count = new AtomicInteger();

        NameClassPairCallbackHandler handler = pair -> {
            if (!(pair instanceof SearchResult)) {
                throw new NamingException(
                        "Expected SearchResult from LDAP search");
            }

            SearchResult result = (SearchResult) pair;
            Attributes attributes = result.getAttributes();
            Attribute uid = attributes.get("uid");

            if (uid != null && uid.size() > 0) {
                count.incrementAndGet();
            }
        };

        ldapTemplate.search(
                "ou=people",
                "(objectClass=inetOrgPerson)",
                controls,
                handler
        );

        return count.get();
    }
}
~~~

**Cách đọc mã:** `ldapTemplate.search(...)` gọi handler cho từng phần tử Search. Handler không trả lại một DTO để template gom List; nó thực hiện tác vụ trực tiếp trên một counter được tạo cho **mỗi lần gọi**.

`AtomicInteger` ở đây chủ yếu giúp biến được lambda tham chiếu và thay đổi được; ví dụ **không khẳng định callback được gọi song song**. Có thể dùng một object accumulator khác nếu cần. Không dùng chung counter singleton cho các request đồng thời nếu muốn số đếm riêng.

**Định nghĩa của con số:** phương thức đếm **những entry có `objectClass=inetOrgPerson` và có ít nhất một `uid` được trả về cho bind identity**. Nó không phải tổng số tài khoản toàn LDAP, không đếm những entry ngoài `ou=people`, không đếm những entry bị ACL che và không xác nhận duy nhất trên toàn subtree.

### 5.1. Callback làm việc với SearchResult, không phải một String

Không viết callback như thể tham số của `handleNameClassPair` là tên người dùng:

~~~java
// Sai về kiểu và ngữ nghĩa:
// handler.handleNameClassPair("alice");
~~~

Handler nhận một `NameClassPair` (Search thường đưa `SearchResult`). Cần lấy `Attributes` rồi đọc giá trị:

~~~java
SearchResult result = (SearchResult) pair;
Attributes attrs = result.getAttributes();

Attribute cn = attrs.get("cn");
String displayName = cn == null || cn.size() == 0
        ? null
        : String.valueOf(cn.get());
~~~

Với thuộc tính đa trị, `Attribute.get()` chỉ lấy một giá trị, không phải toàn bộ tập. Có thể đọc bằng `Attribute.getAll()` nếu nghiệp vụ yêu cầu; xem phần 8.

### 5.2. Có thể bỏ qua một entry trong callback

Handler có thể dùng `return;` để bỏ qua phần xử lý của entry hiện tại:

~~~java
NameClassPairCallbackHandler handler = pair -> {
    SearchResult result = (SearchResult) pair;
    Attribute mail = result.getAttributes().get("mail");

    if (mail == null || mail.size() == 0) {
        return; // Bỏ qua entry này; Search vẫn tiếp tục.
    }

    // Xử lý mail cho entry có thuộc tính được trả.
};
~~~

**`return` ở lambda không yêu cầu LDAP server dừng trả kết quả**, nó chỉ kết thúc callback của entry đang xử lý. Giao diện `handleNameClassPair` trả `void`; không có cờ boolean chuẩn “dừng sau N entry”.

Muốn giới hạn số kết quả từ Search, nên dùng filter, base/scope, `SearchControls` hoặc server-side paging/controls phù hợp, thay vì hy vọng return sớm trong callback sẽ ngắt server.

## 6. So sánh callback và các mapper trả List

Ba API thường gặp:

### 6.1. AttributesMapper: chuyển mỗi entry thành DTO

~~~java
import java.util.List;
import org.springframework.ldap.core.AttributesMapper;

List<String> uids = ldapTemplate.search(
        "ou=people",
        "(objectClass=inetOrgPerson)",
        (AttributesMapper<String>) attrs -> {
            Attribute uid = attrs.get("uid");
            return uid == null ? null : String.valueOf(uid.get());
        }
);
~~~

`AttributesMapper` ánh xạ `Attributes` thành `String`. `LdapTemplate` thu thập các giá trị trả về vào `List<String>`. Phù hợp khi ứng dụng **thật sự cần giữ danh sách kết quả**.

### 6.2. ContextMapper: dùng context và DN

~~~java
import java.util.List;
import org.springframework.ldap.core.ContextMapper;
import org.springframework.ldap.core.DirContextOperations;

List<String> dns = ldapTemplate.search(
        "ou=people",
        "(objectClass=inetOrgPerson)",
        (ContextMapper<String>) context -> {
            DirContextOperations entry = (DirContextOperations) context;
            return entry.getDn().toString();
        }
);
~~~

`ContextMapper` phù hợp khi muốn map **DN và thông tin của entry/context** thay vì chỉ thuộc tính. Cần phân biệt DN tương đối từ `entry.getDn()` với DN đầy đủ theo `ContextSource.base`. Trong một số overload Search/JNDI, việc trả object phải được bật; các overload mapper được framework thiết kế để chuẩn bị ngữ cảnh phù hợp.

### 6.3. NameClassPairCallbackHandler: thao tác mỗi entry

~~~java
NameClassPairCallbackHandler handler = pair -> {
    SearchResult result = (SearchResult) pair;
    // Xử lý entry và trả void.
};

ldapTemplate.search(
        "ou=people",
        "(objectClass=inetOrgPerson)",
        controls,
        handler
);
~~~

| Tiêu chí | `AttributesMapper<T>` | `ContextMapper<T>` | `NameClassPairCallbackHandler` |
| --- | --- | --- | --- |
| Đầu vào | `Attributes` | Context của entry | `NameClassPair`, Search thường là `SearchResult` |
| Giá trị callback trả | `T` | `T` | `void` |
| Kết quả của `search` thông dụng | `List<T>` | `List<T>` | `void` |
| Đọc DN | Không trực tiếp qua chỉ `Attributes` | Thuận tiện qua `DirContextOperations` | Có thể dùng thông tin SearchResult, phải kiểm tra semantics |
| Dùng để tổng hợp/đếm | Được, nhưng thường gom List | Được, nhưng thường gom List | Phù hợp cho một accumulator |
| Có tự paging không? | Không | Không | Không |
| Có tự chạy async không? | Không | Không | Không |

**Không có lựa chọn nào vượt được ACL hoặc giới hạn phía server.** Sự khác biệt chính nằm ở cách ứng dụng **tiêu thụ kết quả đã được trả**.

## 7. Tính số lượng bằng callback có sẵn

Spring LDAP có `CountNameClassPairCallbackHandler` để đếm số phần tử handler đã nhận, tránh tự viết counter nếu yêu cầu chỉ là đếm những entry tìm được.

~~~java
import javax.naming.directory.SearchControls;

import org.springframework.ldap.core.support.CountNameClassPairCallbackHandler;

SearchControls controls = new SearchControls();
controls.setSearchScope(SearchControls.SUBTREE_SCOPE);
controls.setReturningAttributes(new String[] {"uid"});

CountNameClassPairCallbackHandler counter =
        new CountNameClassPairCallbackHandler();

ldapTemplate.search(
        "ou=people",
        "(objectClass=inetOrgPerson)",
        controls,
        counter
);

int returnedCount = counter.getNoOfRows();
~~~

**Tên biến `returnedCount` được chọn có chủ đích:** đây là số phần tử **được handler xử lý**, không phải một lệnh LDAP count có bảo đảm rằng server đã kiểm kê đầy đủ mọi entry. Nếu Search bị giới hạn, chưa phân trang đủ hoặc không thấy toàn bộ entry vì ACL, số này không thể được dùng như “tổng số người dùng của tổ chức”.

Khi muốn đếm theo nhiều điều kiện, có thể viết handler riêng hoặc dùng filter chọn lọc trên server thay vì lấy mọi entry rồi tính trong Java.

## 8. Xử lý attribute thiếu và đa trị trong callback

LDAP entry không phải mọi thuộc tính đều đơn trị hoặc luôn được trả về. `mail` có thể tùy chọn, `telephoneNumber` có thể đa trị, và ACL/returning attributes có thể che giá trị.

### 8.1. Phân biệt thiếu thuộc tính với không có entry

~~~java
Attribute mail = result.getAttributes().get("mail");

if (mail == null) {
    // Không được trả về trong kết quả, chưa đủ kết luận server không lưu.
}
~~~

Một attribute vắng có thể do entry không có dữ liệu, query không yêu cầu trường đó, ACL chặn đọc hoặc thuộc tính thuộc loại operational. Còn **không có kết quả Search** là trường hợp không có entry nào được handler gọi đến.

### 8.2. Đọc đủ thuộc tính đa trị

~~~java
import java.util.ArrayList;
import java.util.List;
import javax.naming.NamingEnumeration;
import javax.naming.NamingException;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;

public static List<String> readTextValues(
        Attributes attrs, String attributeId) throws NamingException {

    Attribute attribute = attrs.get(attributeId);
    if (attribute == null || attribute.size() == 0) {
        return List.of();
    }

    List<String> values = new ArrayList<>();
    NamingEnumeration<?> items = attribute.getAll();

    try {
        while (items.hasMore()) {
            Object value = items.next();
            if (!(value instanceof String)) {
                throw new NamingException(
                        "Unexpected non-text attribute: " + attributeId);
            }
            values.add((String) value);
        }
    } finally {
        items.close();
    }

    return List.copyOf(values);
}
~~~

`Attribute.getAll()` trả `NamingEnumeration` và có `close()`. Khi tự mở enumeration này trong callback, hãy đóng bằng `finally`. Với kết quả Search tổng thể, `LdapTemplate` chịu trách nhiệm duyệt và đóng `NamingEnumeration` của JNDI, không nên cố lưu giữ hoặc dùng nó sau khi method search kết thúc.

**Các giá trị thuộc tính đa trị thông thường không có thứ tự nghiệp vụ được bảo đảm.** Với `telephoneNumber`, không nên coi phần tử đầu là “số chính”. Nếu nghiệp vụ cần ưu tiên, thiết kế field/policy riêng.

### 8.3. Không giữ trực tiếp object JNDI để dùng sau callback

Một handler không nên lưu reference đến `SearchResult`, `Attributes` hoặc context được quản lý để xử lý tùy ý ở thread khác sau khi Search đóng tài nguyên. Hãy **chuyển dữ liệu cần thiết thành DTO bất biến** trong callback rồi bàn giao DTO đó theo một cơ chế được thiết kế rõ.

Tương tự, thuộc tính nhị phân có thể là `byte[]`; không dùng `toString()` để chuyển mọi kiểu sang text. Kiểm tra schema/provider và giới hạn dữ liệu trước khi sao chép, lưu hoặc gửi đi.


## 9. Callback có side effect: tại sao lỗi giữa vòng duyệt rất nguy hiểm?

Callback có thể được dùng để ghi kết quả ra một kho dữ liệu khác, cập nhật bộ đếm nghiệp vụ, xuất báo cáo hay gửi thông điệp. Đây là những **side effect** không được LDAP Search quản lý như một transaction.

Giả sử:

~~~text
Search trả: Alice, Bob, Carol, David
                   |
                   v
callback(Alice) -> ghi CSV thành công
callback(Bob)   -> ghi CSV thành công
callback(Carol) -> ghi CSV thất bại
callback(David) -> không được gọi

Kết quả: CSV đã có một phần dữ liệu.
~~~

LDAP Search không bảo đảm sẽ tự rollback các side effect đã tạo trước lỗi callback. Tương tự, callback không nằm trong một transaction bao trùm LDAP server và database bên ngoài.

**Nguyên tắc thiết kế:** callback nên làm công việc nhỏ, nhanh, dễ kiểm tra; nếu cần cập nhật hệ thống bên ngoài, hãy thiết kế **idempotency, checkpoint và trạng thái partial/failed** rõ ràng.

### 9.1. Không bắt mọi exception rồi tiếp tục mù quáng

Ví dụ cần tránh:

~~~java
NameClassPairCallbackHandler handler = pair -> {
    try {
        externalSystem.save(pair);
    } catch (Exception ex) {
        // Bỏ qua mọi lỗi: kết quả có thể thiếu nhưng báo "thành công".
    }
};
~~~

Cách này làm cho `ldapTemplate.search(...)` có thể kết thúc bình thường dù một số kết quả **không được xử lý**. Nếu có lỗi trên một entry, cần một chính sách rõ: fail toàn job, ghi vào dead-letter/danh sách lỗi, retry theo entry hay cho phép partial result. Mỗi chính sách cần log/audit có kiểm soát và chỉ báo tình trạng không đầy đủ.

### 9.2. Ví dụ handler giao DTO cho Consumer

~~~java
import java.util.Objects;
import java.util.function.Consumer;
import javax.naming.NameClassPair;
import javax.naming.NamingException;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;
import javax.naming.directory.SearchResult;

import org.springframework.ldap.core.NameClassPairCallbackHandler;

record PersonRow(String uid, String displayName) {}

public final class PersonRowHandler
        implements NameClassPairCallbackHandler {

    private final Consumer<PersonRow> consumer;
    private int processed;

    public PersonRowHandler(Consumer<PersonRow> consumer) {
        this.consumer = Objects.requireNonNull(consumer);
    }

    @Override
    public void handleNameClassPair(NameClassPair pair)
            throws NamingException {

        if (!(pair instanceof SearchResult)) {
            throw new NamingException("Expected SearchResult");
        }

        Attributes attrs = ((SearchResult) pair).getAttributes();

        String uid = requiredOne(attrs, "uid");
        String cn = requiredOne(attrs, "cn");

        PersonRow row = new PersonRow(uid, cn);
        consumer.accept(row);
        processed++;
    }

    public int getProcessed() {
        return processed;
    }

    private static String requiredOne(
            Attributes attrs, String name) throws NamingException {

        Attribute attr = attrs.get(name);
        if (attr == null || attr.size() != 1) {
            throw new NamingException(
                    "Expected exactly one readable value: " + name);
        }
        Object value = attr.get();
        if (!(value instanceof String)) {
            throw new NamingException(
                    "Expected text value: " + name);
        }
        return (String) value;
    }
}
~~~

Cách sử dụng:

~~~java
PersonRowHandler handler = new PersonRowHandler(row -> {
    // Ví dụ: chuyển DTO sang một writer/buffer do job quản lý.
    // Không dùng SearchResult hoặc Attributes bên ngoài callback.
    System.out.println(row.uid());
});

ldapTemplate.search(
        "ou=people",
        "(objectClass=inetOrgPerson)",
        controls,
        handler
);

int completedRows = handler.getProcessed();
~~~

**Lưu ý:** `System.out.println` là demo đơn giản; trong production, tránh in UID/dữ liệu cá nhân không cần thiết. Với Consumer gửi dữ liệu qua network/queue, cần chính sách retry và khả năng xảy ra duplicate. Nếu `consumer.accept(row)` ném lỗi, số `processed` chưa tăng cho row đó, nhưng consumer có thể đã **thực hiện một phần side effect** trước khi ném — vì thế bộ đếm không phải bằng chứng giao dịch thành công tuyệt đối.

Vì handler là object có trạng thái `processed`, hãy **tạo instance mới cho mỗi job Search**, không dùng một bean singleton có bộ đếm dùng chung giữa nhiều request.

### 9.3. Callback không phải cơ chế xử lý background

`LdapTemplate.search(...)` chạy thao tác tìm kiếm và gọi handler trong luồng xử lý của lời gọi đó theo API thông thường. Nó không tự tạo background job hay chuyển data sang reactive `Flux`. Không đẩy toàn bộ `SearchResult` sang thread pool mà không có cơ chế đồng bộ/lifecycle.

Nếu ứng dụng dùng hàng đợi hoặc executor, hãy map DTO sớm, giới hạn queue để tránh tăng bộ nhớ không kiểm soát, và xác định rõ tín hiệu hoàn thành/đã xử lý. Callback không tự cung cấp backpressure xuyên LDAP provider và server theo giao thức reactive.

## 10. Xử lý exception và vòng đời tài nguyên

Điểm thuận lợi của `LdapTemplate` là xử lý phần “plumbing” của LDAP Search: lấy context, duyệt `NamingEnumeration`, gọi callback và đóng tài nguyên. Nhiều `NamingException` được framework dịch sang hệ exception phù hợp.

### 10.1. Callback có thể ném NamingException

Giao diện cho phép:

~~~java
@Override
public void handleNameClassPair(NameClassPair pair)
        throws NamingException {
    // Có thể ném NamingException nếu dữ liệu không hợp lệ.
}
~~~

Nếu callback phát hiện một entry thiếu thuộc tính mà **nghiệp vụ bắt buộc**, nó có thể báo lỗi thay vì tự bịa dữ liệu. Nhưng ném exception thường **ngắt quá trình xử lý kết quả**, và những side effect đã thực hiện trước đó ở các callback khác **không được rollback**.

Với lỗi từ consumer hoặc SQL, exception runtime cũng có thể làm search thất bại. Không nên đổi mọi lỗi đọc/ghi thành danh sách kết quả rỗng, vì như vậy ứng dụng nhầm “thất bại giữa chừng” với “LDAP không có entry”.

### 10.2. Không đóng context mà template đang quản lý

Khi gọi overload `LdapTemplate.search(...)` thông thường, template chịu trách nhiệm quản lý context và enumeration của Search. Handler **không** nên đóng `DirContext` do framework cấp, cũng không nên giữ reference tới kết quả provider để dùng sau khi callback kết thúc.

Nếu tự dùng JNDI `DirContext.search(...)` trực tiếp:

~~~java
// Phác thảo vòng đời khi dùng JNDI thô:
NamingEnumeration<SearchResult> results =
        directoryContext.search(baseDn, filter, controls);

try {
    while (results.hasMore()) {
        SearchResult result = results.next();
        // Xử lý từng entry.
    }
} finally {
    results.close();
}
~~~

Đoạn trên giả định `directoryContext` đã được tạo và thuộc quyền quản lý của code gọi; nó cũng phải được đóng đúng hợp đồng sau khi sử dụng. Đó là một phần công việc mà `LdapTemplate` giúp giảm bớt.

### 10.3. Lỗi search chưa chắc là lỗi callback

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Handler không được gọi | Không có entry khớp, scope/base/filter/ACL không phù hợp | Xác minh query và dữ liệu |
| Handler được gọi một số lần rồi lỗi | Mapper/consumer lỗi, mạng, giới hạn server | Phân biệt partial processing và error |
| Thiếu `mail` | Entry không có, không yêu cầu trả hoặc ACL che | Kiểm tra returning attributes/visibility |
| `sizeLimitExceeded`, LDAP **4** | Server/client chạm giới hạn kết quả | Thu hẹp query hoặc thiết kế paging |
| `timeLimitExceeded`, LDAP **3** | Quá giới hạn tìm kiếm | Tối ưu base/filter/index, time limit |
| `noSuchObject`, LDAP **32** | Base không tồn tại hoặc không thể thấy | Kiểm tra DN/base; một số API xử lý name-not-found như không có kết quả |
| LDAP **50** | Thiếu quyền tìm/đọc | Kiểm tra ACL, không tự nâng quyền |
| LDAP **87** | Filter sai cú pháp | Dùng filter builder/escaping |
| Bind/TLS/connection error | Credentials, truststore, network | Xử lý như sự cố kết nối, không thành danh sách rỗng |

**Không giả định cứ gọi callback ít hơn dự kiến là lỗi framework.** Có thể server trả ít entry vì filter, ACL, hạn mức hoặc dữ liệu hiện tại. Ngược lại, nếu có lỗi sau một phần kết quả, cần coi **toàn bộ job chưa hoàn tất** trừ khi nghiệp vụ định nghĩa và ghi nhận được partial result.

## 11. Filter an toàn khi giá trị đến từ người dùng

Filter LDAP có cú pháp riêng. Đừng nối input vào chuỗi filter:

~~~java
String unsafeFilter = "(uid=" + userProvidedUid + ")";
~~~

Nếu `userProvidedUid` là `*`, biểu thức trở thành `(uid=*)` — một **presence filter**, có thể khớp mọi entry có UID, thay vì tìm literal dấu sao.

Với overload callback dùng chuỗi filter, ta có thể dùng lớp `EqualsFilter` hoặc `AndFilter` của Spring LDAP:

~~~java
import org.springframework.ldap.filter.AndFilter;
import org.springframework.ldap.filter.EqualsFilter;

AndFilter safeFilter = new AndFilter();
safeFilter.and(new EqualsFilter("objectClass", "inetOrgPerson"));
safeFilter.and(new EqualsFilter("uid", userProvidedUid));

ldapTemplate.search(
        "ou=people",
        safeFilter.encode(),
        controls,
        handler
);
~~~

`EqualsFilter` encode **giá trị LDAP filter**; `LdapNameBuilder` là công cụ khác để dựng **DN/RDN**. Đừng dùng filter escaping để tạo DN hoặc ngược lại.

Ngay cả khi giá trị được encode, ứng dụng vẫn cần validate UID, hạn chế tên attribute và base DN, giới hạn độ dài/tần suất truy vấn, phân quyền người gọi và tránh các filter quá rộng.

### 11.1. Base/scope quyết định tập entry được duyệt

Giả sử `uid=carol` nằm dưới `ou=engineering,ou=people`:

- `SearchControls.OBJECT_SCOPE` chỉ xét entry tại base.
- `ONELEVEL_SCOPE` chỉ xét con trực tiếp của base.
- `SUBTREE_SCOPE` bao gồm base và mọi hậu duệ, nên mới xét Carol ở OU sâu.

Một filter đúng `(uid=carol)` cũng không tìm Carol nếu scope không bao phủ entry đó. Không nên thay scope bằng việc mở rộng filter.

### 11.2. Tối ưu truy vấn trước khi tối ưu callback

Callback có thể giảm việc giữ dữ liệu ở client, nhưng một subtree Search với `(objectClass=*)` trên root rất rộng vẫn có thể gây tải lớn. Hãy ưu tiên base hẹp, filter có tính chọn lọc, các thuộc tính cần thiết, index server phù hợp và giới hạn kết quả.

Nếu ứng dụng chỉ cần một trang nhỏ cho người dùng, đừng quét toàn directory rồi bỏ phần lớn kết quả trong callback.

## 12. Paging: xử lý nhiều trang và cookie

Khi tập kết quả lớn và server hỗ trợ LDAP Simple Paged Results control, ứng dụng có thể gửi **nhiều Search request**, mỗi request trả một trang. Server cung cấp cookie để tiếp tục trang kế tiếp. Spring LDAP có cơ chế `DirContextProcessor` giúp gắn request control trước Search và đọc response control sau Search.

Sơ đồ:

~~~text
LDAP Search + page size = 100 + cookie trống
        |
        v
100 SearchResult -> handler xử lý từng entry
        |
        v
Server trả cookie K1
        |
        v
LDAP Search tiếp + cookie K1
        |
        v
Trang tiếp theo -> handler xử lý từng entry
        |
        v
...
        |
        v
Cookie hết / không còn trang -> kết thúc
~~~

**Mấu chốt:** mỗi trang có thể dùng callback để tránh giữ toàn bộ tập kết quả, nhưng callback **không tự tạo trang hay quản lý cookie**. Muốn paging, cần cấu hình request/response controls, vòng lặp qua trang và connection lifecycle phù hợp.

### 12.1. DirContextProcessor làm gì?

Với overload hỗ trợ `DirContextProcessor`:

~~~java
ldapTemplate.search(
        "ou=people",
        "(objectClass=inetOrgPerson)",
        controls,
        handler,
        processor
);
~~~

`processor` ở đây là một `DirContextProcessor` đã tạo và cấu hình theo nhu cầu. Framework gọi `preProcess` trước Search và `postProcess` sau khi xử lý enumeration, giúp làm việc với LDAP controls.

Spring LDAP có bộ xử lý dành cho paged results; tùy phiên bản có tên `PagedResultsControlExchangeDirContextProcessor` (được tài liệu phiên bản mới khuyến nghị) hoặc `PagedResultsDirContextProcessor` ở các phiên bản cũ hơn. Khi triển khai hãy đối chiếu **đúng API và trạng thái deprecated của phiên bản đang dùng**.

Đoạn trên chỉ mô tả overload; **chưa phải paging runnable** khi chưa tạo processor, giữ connection giữa các request và viết vòng lặp cookie.

### 12.2. Giữ cùng kết nối cho các trang

Trong những triển khai Spring LDAP/JNDI paged results cổ điển, cookie gắn với **cùng kết nối/context LDAP**. `LdapTemplate` thông thường có thể đóng context sau mỗi lời gọi, vì vậy chỉ gọi nhiều lần với một processor mà không quản lý connection có thể khiến paging sai hoặc bị từ chối.

Tài liệu Spring LDAP mô tả các cách như `SingleContextSource.doWithSingleContext(...)` hoặc cơ chế transaction-aware context phù hợp nhằm giữ kết nối dùng cho chuỗi trang. Cần xác nhận server có hỗ trợ control, cookie còn hiệu lực, thứ tự/consistency dữ liệu trong lúc paging và chính sách timeout.

**Pooling không tự bảo đảm cùng kết nối cho mọi trang** nếu mỗi lần mượn context có thể trả một connection khác.

### 12.3. Paging không tự tạo snapshot nhất quán

Nếu directory thay đổi trong lúc bạn duyệt nhiều trang, entry có thể được thêm, xóa hoặc đổi nhóm. Đừng mặc định tập kết quả nhiều trang là một snapshot transaction. Khi đồng bộ dữ liệu cần độ chính xác cao, phải thiết kế chiến lược reconciliation, checkpoint, xử lý trùng/thiếu theo DN/entry identity và đặc tính của server.

### 12.4. Count limit không phải paging

`setCountLimit(100)` không tương đương “lấy trang đầu rồi tự mở trang hai”. Nó chỉ đặt giới hạn cho Search hiện tại; ứng dụng vẫn phải dùng paging control hoặc một cơ chế chia nhỏ truy vấn hợp lệ để lấy đủ dữ liệu. Kết quả dừng vì limit **không thể được báo là đã đọc hết thư mục**.

## 13. Tại sao không nên bỏ qua kết quả bất thường?

Trong pipeline xử lý nhiều entry, có thể gặp một entry không có thuộc tính mà DTO yêu cầu. Có ba chiến lược, nhưng phải chọn có chủ đích:

| Chiến lược | Khi nào phù hợp | Rủi ro cần kiểm soát |
| --- | --- | --- |
| **Fail fast** | Thiếu UID là vi phạm hợp đồng dữ liệu | Job có thể đã thực hiện side effect với entry trước |
| **Skip with audit** | Thuộc tính tùy chọn vắng và nghiệp vụ cho phép bỏ qua | Thống kê số entry bỏ qua, không báo “đầy đủ” sai |
| **Dead-letter/retry** | Ghi hệ thống ngoài lỗi tạm thời | Cần payload tối thiểu, idempotency, giới hạn retry, retention |

Không có chiến lược nào biến LDAP Search thành transaction xuyên hệ thống. Nếu cần báo cáo chính xác số entry, hãy lưu `processed`, `skipped`, `failed`, `unknown` và trạng thái trang đã nhận thay vì chỉ một số tổng đơn giản.

### 13.1. Không lưu dữ liệu nhạy cảm vào log

Với exception trong callback, log nên có loại thao tác, correlation ID, mã LDAP, tên trường theo allowlist và vị trí job ở mức phù hợp. Tránh in toàn bộ `SearchResult`, `Attributes`, mật khẩu, hash, chứng chỉ, danh sách nhóm hoặc DN chứa dữ liệu cá nhân khi không cần.

Nếu cần tái xử lý, có thể lưu một định danh entry được bảo vệ hoặc checkpoint tại kho riêng thay vì sao chép toàn bộ hồ sơ sang log.

## 14. Kiểm thử callback không cần LDAP server

Ta có thể **gọi handler trực tiếp** bằng một `SearchResult` giả lập để kiểm tra mapping và side effect ở Java.

### 14.1. Test xử lý entry có đủ uid/cn

~~~java
import java.util.ArrayList;
import java.util.List;

import javax.naming.directory.BasicAttributes;
import javax.naming.directory.SearchResult;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class PersonRowHandlerTest {

    @Test
    void handlesOneSearchResult() throws Exception {
        List<PersonRow> rows = new ArrayList<>();
        PersonRowHandler handler = new PersonRowHandler(rows::add);

        BasicAttributes attrs = new BasicAttributes(true);
        attrs.put("uid", "alice");
        attrs.put("cn", "Alice Nguyen");

        SearchResult result = new SearchResult(
                "uid=alice", null, attrs);

        handler.handleNameClassPair(result);

        assertEquals(1, handler.getProcessed());
        assertEquals(1, rows.size());
        assertEquals("alice", rows.get(0).uid());
        assertEquals("Alice Nguyen", rows.get(0).displayName());
    }
}
~~~

`BasicAttributes(true)` là đối tượng JNDI dùng cho test, xử lý tên thuộc tính không phân biệt hoa thường theo cách cấu hình object. Test này kiểm tra logic handler, **không xác minh** ACL, filter, networking hay khả năng paging của server.

### 14.2. Test thuộc tính bắt buộc thiếu

~~~java
import javax.naming.NamingException;
import javax.naming.directory.BasicAttributes;
import javax.naming.directory.SearchResult;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class PersonRowHandlerMissingAttributeTest {

    @Test
    void missingCnIsRejected() {
        PersonRowHandler handler =
                new PersonRowHandler(row -> fail("Must not consume"));

        BasicAttributes attrs = new BasicAttributes(true);
        attrs.put("uid", "alice");

        SearchResult result = new SearchResult(
                "uid=alice", null, attrs);

        assertThrows(NamingException.class,
                () -> handler.handleNameClassPair(result));
        assertEquals(0, handler.getProcessed());
    }
}
~~~

Nếu nghiệp vụ cho phép thiếu `cn`, test và handler cần chọn policy khác, ví dụ lưu `null` trong DTO hoặc bỏ qua có ghi nhận. **Không nên sửa test để che một hợp đồng dữ liệu chưa được định nghĩa rõ.**

### 14.3. Test callback khi consumer thất bại

~~~java
import javax.naming.directory.BasicAttributes;
import javax.naming.directory.SearchResult;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class PersonRowHandlerFailureTest {

    @Test
    void consumerFailureStopsTheHandler() {
        PersonRowHandler handler =
                new PersonRowHandler(row -> {
                    throw new IllegalStateException(
                            "Downstream unavailable");
                });

        BasicAttributes attrs = new BasicAttributes(true);
        attrs.put("uid", "alice");
        attrs.put("cn", "Alice Nguyen");

        SearchResult result = new SearchResult(
                "uid=alice", null, attrs);

        assertThrows(IllegalStateException.class,
                () -> handler.handleNameClassPair(result));

        assertEquals(0, handler.getProcessed());
    }
}
~~~

Unit test này không thể kết luận external sink chắc chắn chưa ghi gì nếu sink có side effect một phần trước khi throw. Đó là bài toán **idempotency/transaction của downstream** và cần một bài integration/failure-injection test riêng.

## 15. Kiểm thử tích hợp với LDAP server

Hãy dùng một directory **dành cho test** với dữ liệu:

~~~text
ou=people,dc=example,dc=org
├── uid=alice
├── uid=bob
└── ou=engineering
    └── uid=carol
~~~

Giả sử cả ba là `inetOrgPerson` hợp schema, đều có `uid` và `cn`. Cấu hình reader identity được phép xem ba entry. Khi đó:

| Ca kiểm thử | Kết quả kỳ vọng |
| --- | --- |
| Base `ou=people`, scope SUBTREE | Handler nhận cả Alice, Bob, Carol |
| Base `ou=people`, scope ONELEVEL | Handler nhận Alice, Bob |
| Filter `(uid=alice)` | Chỉ Alice trong nhánh đã chọn |
| Không có entry khớp | Handler không được gọi |
| Returning attributes chỉ có `uid` | Handler yêu cầu `cn` sẽ báo thiếu theo policy |
| `mail` tùy chọn vắng | Logic cho mail tùy chọn xử lý được |
| Attr đa trị `telephoneNumber` | Dùng `getAll()` và không dựa vào thứ tự |
| Count limit thấp | Không kết luận đã duyệt toàn bộ entry |
| Callback ném lỗi ở entry thứ hai | Job thất bại; kiểm tra side effect entry trước |
| ACL che `cn` hoặc một OU | Handler không tự truy cập dữ liệu bị che |
| TLS hoặc bind credentials sai | Thất bại kết nối/xác thực, không biến thành “0 entry” |
| Paging nhiều trang | Cookie được duy trì; tập kết quả đúng theo server/consistency |
| Hai job đồng thời | State handler độc lập, không lẫn số đếm |

### 15.1. Một test integration tối giản

~~~java
import javax.naming.directory.SearchControls;

import org.junit.jupiter.api.Test;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.core.support.CountNameClassPairCallbackHandler;

import static org.junit.jupiter.api.Assertions.assertEquals;

class LdapCallbackIntegrationTest {
    private final LdapTemplate template;

    // Spring Test/fixture phải cung cấp template đã cấu hình.
    LdapCallbackIntegrationTest(LdapTemplate template) {
        this.template = template;
    }

    @Test
    void countsVisiblePeopleInSubtree() {
        SearchControls controls = new SearchControls();
        controls.setSearchScope(SearchControls.SUBTREE_SCOPE);
        controls.setReturningAttributes(new String[] {"uid"});

        CountNameClassPairCallbackHandler handler =
                new CountNameClassPairCallbackHandler();

        template.search(
                "ou=people",
                "(objectClass=inetOrgPerson)",
                controls,
                handler
        );

        assertEquals(3, handler.getNoOfRows());
    }
}
~~~

Đây là **khung test**, chỉ phù hợp khi directory test chứa **đúng ba** entry khớp filter, reader thấy đầy đủ và Spring Test/fixture inject được template. Nếu môi trường có thêm entry, không được giữ assertion `3` như chân lý phổ quát.

Khi cần kiểm tra tập đối tượng, so sánh **tập DN hoặc UID đã xác minh** thay vì thứ tự callback: LDAP Search thông thường không mặc định trả kết quả theo thứ tự nghiệp vụ. Với UID có thể trùng ở nhiều OU, dùng DN/định danh entry thay vì chỉ UID.

### 15.2. Test lỗi giữa vòng duyệt

Cần test khi handler ném exception ở entry thứ hai:

1. Xác nhận luồng xử lý không báo job `COMPLETE`.
2. Xác nhận số entry đã xử lý trước đó được ghi nhận đúng (hoặc trạng thái UNKNOWN nếu downstream chưa chắc).
3. Không giả định các side effect của entry thứ nhất tự rollback.
4. Xác nhận LDAP context/enumeration được framework quản lý/giải phóng theo hợp đồng.
5. Xác nhận cơ chế thử lại không sinh duplicate ở downstream.

Tình huống này kiểm tra **độ tin cậy của pipeline**, không chỉ chức năng trích xuất thuộc tính.

## 16. Bài thực hành: báo cáo danh bạ bằng callback

**Bối cảnh:** phòng vận hành cần duyệt người dùng LDAP để thống kê số tài khoản theo OU, đồng thời hạn chế bộ nhớ và xử lý những entry thiếu thông tin.

1. Chuẩn bị LDAP test có ba người dùng ở hai cấp OU; thêm một entry không có `mail` và một entry có hai số điện thoại nếu schema cho phép.
2. Cấu hình `LdapContextSource` với LDAPS, chứng chỉ tin cậy và read-only bind identity.
3. Viết `SearchControls` với base `ou=people`, scope SUBTREE, returning attrs `uid`, `cn`, `mail`; không dùng filter quá rộng ngoài nhu cầu.
4. Gọi `LdapTemplate.search(..., NameClassPairCallbackHandler)` và đếm các kết quả đã nhận.
5. In thử `NameClassPair`/`SearchResult` ở mức kiểm soát, phân biệt tên tương đối với DN đầy đủ.
6. Dùng `AttributesMapper` để thu List UID trên cùng filter; đối chiếu số phần tử với handler trong directory test nhỏ.
7. Đổi scope sang ONELEVEL và giải thích vì sao user trong OU con sâu bị bỏ qua.
8. Thử một thuộc tính đa trị và đọc đủ bằng `Attribute.getAll()`, đóng enumeration ở `finally`.
9. Mô phỏng một lỗi trong callback; ghi nhận số entry đã xử lý và lý do không nên báo job hoàn tất.
10. Thêm count/time limit và giải thích vì sao không thể coi số callback là tổng user của toàn LDAP.
11. Nếu server hỗ trợ paging, triển khai vòng lặp cookie với `DirContextProcessor` thích hợp và giữ kết nối theo hướng dẫn của phiên bản Spring LDAP.
12. Thử input UID có dấu `*`; dùng `EqualsFilter` để tránh biến thành wildcard/presence filter.
13. Thử tài khoản reader bị hạn chế ACL hoặc truststore TLS sai; không đổi lỗi kết nối thành “0 entry”.
14. Viết unit test handler và integration test thư mục, so sánh tập giá trị mà không dựa vào thứ tự search.
15. Đánh giá có cần callback hay nên giữ mapper/List cho màn hình chỉ trả vài kết quả.

### Câu hỏi tự kiểm tra

1. `NameClassPairCallbackHandler` nhận kiểu dữ liệu gì và phương thức xử lý tên là gì?
2. Tại sao `SearchResult` khác `NameClassPair` khi đọc thuộc tính?
3. Vì sao `AttributesMapper<T>` và callback thường dẫn đến hai kiểu kết quả khác nhau của `LdapTemplate.search`?
4. Callback có tự làm truy vấn thành bất đồng bộ hoặc tự paging không?
5. `return;` trong handler có dừng LDAP Search trên server không?
6. Vì sao cùng filter nhưng OBJECT, ONELEVEL, SUBTREE có thể có số callback khác nhau?
7. Khi `Attribute.get("mail")` trả null, có thể khẳng định server không lưu email không?
8. Tại sao phải đọc thuộc tính đa trị bằng `getAll()` và đóng enumeration?
9. Khi callback thứ ba thất bại, hai side effect đầu có tự rollback không?
10. Vì sao count limit khác server-side paging?
11. Cookie paging và connection/context lifecycle liên quan thế nào?
12. Khi nào `DirContextProcessor` được sử dụng?
13. Vì sao cần `EqualsFilter` cho input động thay vì nối chuỗi?
14. Đếm số callback có đồng nghĩa số entry toàn directory không?
15. Nếu cần DN cho một thao tác Modify tiếp theo, làm sao tránh nhầm DN tương đối và đầy đủ?

## 17. Tổng kết

**Search result iteration và callback handler** trong Spring LDAP cho phép xử lý mỗi kết quả Search ngay khi `LdapTemplate` duyệt `NamingEnumeration`, thay vì luôn thu thập `List<T>`. Giao diện `NameClassPairCallbackHandler` cung cấp `handleNameClassPair(NameClassPair)`; với Search, phần tử được xử lý là `SearchResult` và có thể đọc `Attributes`, trong khi `AttributesMapper`/`ContextMapper` thích hợp để chuyển kết quả sang đối tượng và gom danh sách.

Callback **không** tự cấp paging, streaming reactive, quyền truy cập hay transaction cho side effect. Với tập dữ liệu lớn, cần lọc hẹp, giới hạn tài nguyên, paging đúng cookie/kết nối khi server hỗ trợ, xử lý lỗi giữa vòng duyệt và đối soát khi downstream chưa hoàn tất. Kết hợp filter escaping, TLS được xác minh, ACL tối thiểu, mapper dữ liệu thiếu/đa trị và kiểm thử tích hợp sẽ giúp chương trình duyệt kết quả LDAP chính xác, hiệu quả và an toàn.

### Tài liệu tham khảo

- Spring LDAP API — `LdapTemplate`: https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/LdapTemplate.html
- Spring LDAP API — `NameClassPairCallbackHandler`: https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/NameClassPairCallbackHandler.html
- Spring LDAP Reference — `Processing the DirContext` (bao gồm paged results): https://docs.spring.io/spring-ldap/reference/processing-the-dircontext.html
