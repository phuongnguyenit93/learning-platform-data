# Callback API khi cần quyền kiểm soát thấp hơn

**`LdapTemplate`** là thành phần trung tâm của **Spring LDAP** để làm việc với LDAP directory mà không phải tự lặp lại các bước lấy `DirContext`, xử lý ngoại lệ JNDI và đóng tài nguyên. Những thao tác thường gặp như `search`, `lookup`, `bind`, `modifyAttributes` hoặc `unbind` đã có API mức cao. Tuy nhiên, một số trường hợp cần sử dụng trực tiếp tính năng JNDI, quản lý chi tiết kết quả tìm kiếm hoặc thực hiện nhiều bước trên **cùng một context**. Khi đó, các **callback API** của `LdapTemplate` cho phép mã ứng dụng đi xuống tầng thấp hơn mà vẫn tận dụng cơ chế quản lý context của template.

Bài thuộc chương **LdapTemplate** trong module **SPRING_LDAP**. Người học sẽ phân biệt callback dùng để **ánh xạ dữ liệu** với callback dùng để **thực thi JNDI**, thực hành `executeReadOnly` và `executeReadWrite`, quản lý `NamingEnumeration`, hiểu những giới hạn về giao dịch, quyền truy cập và vòng đời kết nối, sau đó kiểm thử trên LDAP server thử nghiệm. Các nguyên tắc này cũng hữu ích khi quyết định dùng `LdapClient` hoặc LDAP ODM thay vì tự viết lệnh JNDI.

> **Ý tưởng chính:** Chỉ xuống tầng callback mức thấp khi API mức cao chưa đáp ứng yêu cầu. Trong callback, mã ứng dụng có thêm quyền kiểm soát đối với thao tác JNDI, nhưng phải tự chịu trách nhiệm về dữ liệu, phạm vi, giải phóng tài nguyên phụ và cách diễn giải kết quả.

## 1. Vì sao Spring LDAP có `LdapTemplate`?

Một đoạn JNDI trực tiếp thường phải thực hiện nhiều công việc:

1. Lấy `DirContext` hoặc `LdapContext` với URL, base DN và danh tính phù hợp.
2. Gọi `search`, `lookup`, `modifyAttributes` hoặc thao tác khác.
3. Đọc `Attributes` và chuyển thành đối tượng nghiệp vụ.
4. Xử lý `NamingException` từ JNDI.
5. Đóng `NamingEnumeration`, `DirContext` và tránh rò rỉ kết nối.

Nếu tự lặp những bước này trong nhiều lớp DAO, code dễ bị thiếu `finally`, lẫn DN tương đối/tuyệt đối, xử lý lỗi không nhất quán hoặc rò rỉ tài nguyên.

`LdapTemplate` gom phần quản lý tài nguyên và chuyển đổi các lỗi JNDI sang hệ ngoại lệ truy cập LDAP của Spring. Lập trình viên tập trung vào thao tác và dữ liệu cần đọc. Một yêu cầu tìm kiếm thông thường có thể biểu diễn như sau:

~~~java
import java.util.List;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;
import org.springframework.ldap.query.SearchScope;

public final class EmployeeSearch {
    private final LdapTemplate ldapTemplate;

    public EmployeeSearch(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<String> searchUids(String uid) {
        LdapQuery query = LdapQueryBuilder.query()
                .base("ou=people")
                .searchScope(SearchScope.ONELEVEL)
                .attributes("uid")
                .where("objectClass").is("inetOrgPerson")
                .and("uid").is(uid);

        return ldapTemplate.search(
                query,
                (AttributesMapper<String>) attrs ->
                        (String) attrs.get("uid").get());
    }
}
~~~

Ví dụ giả định `ContextSource` đã có base `dc=example,dc=org`, nên `ou=people` là **tên tương đối**. Phần filter được dựng bằng query builder để escape giá trị `uid` thay vì nối trực tiếp dữ liệu người dùng vào chuỗi LDAP. Trong sản phẩm thật cần kiểm tra đầu vào rỗng, thuộc tính thiếu, tính duy nhất, quyền đọc và ngoại lệ.

Ở trường hợp này, **không cần** `DirContext` thủ công. Đi xuống tầng thấp chỉ làm code dài hơn nếu API mức cao đã giải quyết được yêu cầu.

## 2. Ba tầng làm việc với `LdapTemplate`

Từ mức trừu tượng cao đến mức thấp hơn:

| Tầng | API tiêu biểu | Mức kiểm soát | Trách nhiệm của code ứng dụng |
| --- | --- | --- | --- |
| **Thao tác có sẵn** | `lookup`, `search`, `bind`, `modifyAttributes`, `unbind` | Chọn DN, filter, scope và dữ liệu | Xác thực/phân quyền, mapper, validation |
| **Callback ánh xạ / xử lý kết quả** | `AttributesMapper`, `ContextMapper`, handler kết quả tìm kiếm | Quyết định cách đọc từng entry | Xử lý thuộc tính, kiểu dữ liệu, kết quả thiếu |
| **Callback thực thi context** | `ContextExecutor` thông qua `executeReadOnly` / `executeReadWrite` | Truy cập trực tiếp `DirContext` và API JNDI | Quản lý enumeration, thao tác chi tiết, trạng thái và lỗi |

**Chữ “callback” không có nghĩa mọi callback đều cấp toàn quyền truy cập JNDI.** Một `AttributesMapper` chỉ được gọi để biến `Attributes` thành kết quả Java. Muốn thao tác trực tiếp trên `DirContext`, dùng nhóm thực thi context ở mức thấp.

### 2.1. `AttributesMapper` và `ContextMapper`

Hai kiểu mapper thường dùng:

- **`AttributesMapper<T>`:** nhận `Attributes` của một entry và trả về đối tượng kiểu `T`. Phù hợp khi chỉ cần đọc các thuộc tính.
- **`ContextMapper<T>`:** nhận đối tượng context do API mapping cung cấp (thường có thể làm việc với `DirContextOperations`) và trả về `T`. Phù hợp khi cần thông tin tên/context ngoài các thuộc tính cơ bản.

Ví dụ mapper an toàn khi thuộc tính `mail` không bắt buộc:

~~~java
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;
import org.springframework.ldap.core.AttributesMapper;

public final class EmployeeMailMapper implements AttributesMapper<String> {
    @Override
    public String mapFromAttributes(Attributes attrs)
            throws javax.naming.NamingException {
        Attribute mail = attrs.get("mail");
        if (mail == null || mail.size() == 0) {
            return null; // Tầng service cần định nghĩa chính sách cho trường hợp này.
        }
        return String.valueOf(mail.get());
    }
}
~~~

Mapper không nên tự gọi thêm các phép search nặng trong mỗi lần ánh xạ, vì dễ tạo vấn đề **N+1 LDAP queries** và tăng độ trễ. Nếu một phép truy vấn đã trả đủ dữ liệu, hãy ánh xạ ngay những thuộc tính cần thiết.

### 2.2. Khi nào dùng callback mức thấp?

Một số nhu cầu phù hợp:

- Cần gọi một overload của `DirContext.search` hoặc `DirContext.getAttributes` mà API có sẵn khó biểu đạt.
- Cần kiểm soát việc đọc một `NamingEnumeration`, xử lý metadata và bảo đảm đóng enumeration đúng nơi.
- Cần thực hiện nhiều thao tác JNDI **trên một context** thay vì lấy context cho mỗi lời gọi.
- Cần tương tác với JNDI controls hoặc tính năng đặc thù của LDAP provider; nếu sử dụng các LDAP request/response controls, có thể cần `LdapContext` và phải kiểm tra provider hỗ trợ.
- Cần triển khai một adapter cục bộ cho API cũ vốn nhận `DirContext`.

Trước khi dùng callback mức thấp, hãy kiểm tra liệu overload của `LdapTemplate`, `LdapQueryBuilder`, `LdapClient` hoặc `DirContextProcessor` đã giải quyết bài toán an toàn và ngắn gọn hơn chưa. **API mức thấp là lựa chọn có chủ đích, không phải mặc định cho mọi DAO.**

## 3. `ContextExecutor`: điểm vào của callback mức thấp

`ContextExecutor<T>` đại diện cho công việc được thực hiện khi `LdapTemplate` cung cấp một `DirContext`. Hai phương thức thường sử dụng:

- **`executeReadOnly(...)`:** chạy callback với context được lấy theo đường dành cho thao tác đọc.
- **`executeReadWrite(...)`:** chạy callback với context được lấy theo đường dành cho thao tác có thể ghi.

Ví dụ khái niệm:

~~~java
String result = ldapTemplate.executeReadOnly(ctx -> {
    // ctx là DirContext do LdapTemplate cấp cho callback.
    // Thao tác JNDI cụ thể có thể ném NamingException.
    return ctx.getNameInNamespace();
});
~~~

Trong callback, code có thể gọi các phương thức JNDI và trả về giá trị Java. `LdapTemplate` chịu trách nhiệm lấy và đóng context theo vòng đời lời gọi, đồng thời xử lý nhiều ngoại lệ JNDI theo quy ước của Spring LDAP.

**Không gọi `ctx.close()` trong callback** khi context do `LdapTemplate` quản lý. Nếu tự đóng context, bạn có thể làm hỏng bước kế tiếp trong callback hoặc ảnh hưởng cách template quản lý tài nguyên. Nhưng **các tài nguyên phụ** mà chính callback mở ra, như `NamingEnumeration`, vẫn cần được đóng bởi callback.

### 3.1. Vòng đời context

~~~mermaid
sequenceDiagram
    participant S as Service
    participant T as LdapTemplate
    participant C as DirContext
    participant L as LDAP server
    S->>T: executeReadOnly(callback)
    T->>C: Lấy context từ ContextSource
    T->>S: Kích hoạt callback với ctx
    S->>C: ctx.getAttributes(...)
    C->>L: LDAP request trên kết nối phù hợp
    L-->>C: Attributes hoặc lỗi LDAP
    C-->>S: Kết quả JNDI
    S-->>T: Giá trị callback trả về
    T->>C: Giải phóng context do template quản lý
    T-->>S: Giá trị hoặc ngoại lệ được chuyển đổi
~~~

Sơ đồ mô tả **luồng thực thi đồng bộ ở mức khái niệm**; nó không khẳng định mọi provider đều mở TCP socket mới cho mỗi callback. Khi pooling được bật, một context có thể mượn kết nối đã tồn tại.

**Ba giới hạn phải nhớ:**

1. Context được cấp có vòng đời gắn với lời gọi callback. Không cất nó vào field, trả về từ callback để sử dụng sau, hoặc gửi cho thread khác.
2. Cùng một context không đồng nghĩa các thao tác ở đó được **gói thành transaction LDAP**. LDAP thông thường không bảo đảm rollback toàn bộ nhiều thao tác khi bước sau thất bại.
3. Quyền đọc/ghi thực tế do **danh tính bind và ACL trên server** quyết định. Tên `executeReadOnly` không phải một lớp bảo mật thay thế ACL.

## 4. Ví dụ đọc thuộc tính bằng `executeReadOnly`

Giả sử ứng dụng có `LdapContextSource` đặt base `dc=example,dc=org` và cần đọc `mail` của một người dùng đã biết `uid`. Ta xây DN bằng `LdapNameBuilder` rồi đọc trực tiếp `Attributes`:

~~~java
import java.util.Optional;
import javax.naming.Name;
import javax.naming.NameNotFoundException;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;

import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

public final class EmployeeMailReader {
    private final LdapTemplate template;

    public EmployeeMailReader(LdapTemplate template) {
        this.template = template;
    }

    public Optional<String> findMail(String uid) {
        if (uid == null || !uid.matches("[a-z0-9._-]{1,64}")) {
            throw new IllegalArgumentException("uid không hợp lệ");
        }

        Name dn = LdapNameBuilder.newInstance("ou=people")
                .add("uid", uid)
                .build();

        return template.executeReadOnly(ctx -> {
            try {
                Attributes attrs = ctx.getAttributes(
                        dn, new String[] {"mail"});
                Attribute mail = attrs.get("mail");
                if (mail == null || mail.size() == 0) {
                    return Optional.empty();
                }
                return Optional.of(String.valueOf(mail.get()));
            } catch (NameNotFoundException notFound) {
                return Optional.empty();
            }
        });
    }
}
~~~

Đoạn code thực hiện những việc quan trọng:

- **Xây DN bằng thành phần:** tránh nối `"uid=" + uid` thành DN dễ lỗi escaping.
- **Dùng tên tương đối:** với base hiện tại, `uid=linh,ou=people` mới là DN thích hợp, không lặp `dc=example,dc=org`.
- **Chỉ yêu cầu `mail`:** giảm dữ liệu trả về, đặc biệt tránh vô tình tải những thuộc tính không dùng.
- **Phân biệt không tồn tại với hạ tầng:** chỉ bắt `javax.naming.NameNotFoundException`; lỗi mạng, TLS và lỗi quyền không nên biến thành `Optional.empty()`.
- **Không đóng `ctx`:** template quản lý lifecycle context.

Regex trong ví dụ là **quy tắc nghiệp vụ minh họa**, không phải giới hạn cú pháp LDAP. Một danh bạ có Unicode hoặc định dạng `uid` khác sẽ cần validation riêng. Nếu `mail` là thuộc tính đa trị, cần thiết kế DTO và quy tắc chọn giá trị thay vì mặc định chỉ dùng `mail.get()` đầu tiên.

### 4.1. Tại sao không dùng `ldapTemplate.lookup` thông thường?

Với ví dụ đọc `mail` đơn giản, `ldapTemplate.lookup(dn, mapper)` hoặc một overload cho phép chọn thuộc tính thường sẽ **ngắn gọn hơn**. Đoạn callback ở đây được dùng để hiểu cơ chế; nó có ích khi ứng dụng phải dùng overload JNDI cụ thể hoặc ghép nhiều thao tác trên một context. Đừng thay tất cả mapper bằng `executeReadOnly` chỉ vì callback “trông linh hoạt”.

## 5. Dùng `DirContext.search` khi cần tự xử lý enumeration

Một phép tìm kiếm JNDI thường trả **`NamingEnumeration<SearchResult>`**. Callback mức thấp có thể tự đọc từng phần tử, nhưng điều đó đi kèm trách nhiệm **đóng enumeration**, xử lý giới hạn và ngoại lệ phát sinh trong lúc lặp.

Ví dụ tìm tối đa 20 entry theo `uid` chính xác:

~~~java
import java.util.ArrayList;
import java.util.List;

import javax.naming.NamingEnumeration;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;
import javax.naming.directory.SearchControls;
import javax.naming.directory.SearchResult;

import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.filter.AndFilter;
import org.springframework.ldap.filter.EqualsFilter;

public final class JndiEmployeeSearch {
    private final LdapTemplate template;

    public JndiEmployeeSearch(LdapTemplate template) {
        this.template = template;
    }

    public List<String> findUids(String uid) {
        if (uid == null || uid.isBlank() || uid.length() > 64) {
            throw new IllegalArgumentException("uid không hợp lệ");
        }

        AndFilter filter = new AndFilter();
        filter.and(new EqualsFilter("objectClass", "inetOrgPerson"));
        filter.and(new EqualsFilter("uid", uid));

        return template.executeReadOnly(ctx -> {
            SearchControls controls = new SearchControls();
            controls.setSearchScope(SearchControls.ONELEVEL_SCOPE);
            controls.setReturningAttributes(new String[] {"uid"});
            controls.setCountLimit(20L);
            controls.setTimeLimit(2000); // JNDI: mili giây.

            NamingEnumeration<SearchResult> results =
                    ctx.search("ou=people", filter.encode(), controls);
            try {
                List<String> values = new ArrayList<>();
                while (results.hasMore()) {
                    SearchResult entry = results.next();
                    Attributes attrs = entry.getAttributes();
                    Attribute attribute = attrs.get("uid");
                    if (attribute != null && attribute.size() > 0) {
                        values.add(String.valueOf(attribute.get()));
                    }
                }
                return values;
            } finally {
                results.close();
            }
        });
    }
}
~~~

Trong đoạn mã này:

1. `EqualsFilter` mã hóa `uid` làm **giá trị literal**, không cho phép đầu vào chứa `*` hoặc dấu ngoặc thay đổi filter.
2. `SearchControls.ONELEVEL_SCOPE` chỉ tìm các entry con trực tiếp của `ou=people`.
3. `setReturningAttributes` hạn chế thuộc tính yêu cầu.
4. `setCountLimit(20)` yêu cầu server giới hạn số entry trả về; nó **khác** với việc cắt `List` sau khi tìm.
5. `setTimeLimit(2000)` dùng đơn vị **mili giây ở API JNDI**, khác trường `timeLimit` cấp giao thức LDAP tính bằng giây.
6. `results.close()` nằm trong `finally` để đóng enumeration ngay cả khi `hasMore` hay mapping phát sinh lỗi.

Nếu `ctx.search(...)` ném ngoại lệ trước khi trả enumeration, block `finally` của enumeration chưa chạy, vì không có enumeration nào được cấp. Context vẫn do template xử lý theo vòng đời của callback.

**Không trả `NamingEnumeration` ra khỏi callback.** Sau khi callback kết thúc, `LdapTemplate` có thể giải phóng context mà enumeration đang dựa vào. Hãy duyệt và ánh xạ kết quả **ngay trong callback**, rồi trả về DTO hoặc dữ liệu Java độc lập.

### 5.1. Những điều ví dụ không bảo đảm

- Kết quả bị giới hạn bởi server hoặc timeout có thể **không đầy đủ**, đôi khi đã trả một số entry trước khi phát ngoại lệ.
- LDAP search không mặc định trả kết quả theo thứ tự ổn định. Nếu ứng dụng cần sort hoặc paging, phải tìm hiểu LDAP controls và mức hỗ trợ của server.
- Server có thể áp giới hạn chặt hơn `setCountLimit`; đừng coi đúng 20 entry là kết luận về toàn bộ tập dữ liệu.
- `SearchControls` và filter không thay được LDAP ACL; tài khoản kết nối vẫn cần quyền đọc thực tế.
- Một số sản phẩm LDAP có alias/referral và matching rule khác nhau; cần kiểm thử với hệ server dự kiến triển khai.

Trong hầu hết trường hợp tìm kiếm, `LdapTemplate.search(query, mapper)` đã hỗ trợ scope, filter và count/time limit thuận tiện hơn. Chỉ giữ phiên bản JNDI trực tiếp khi cần quyền xử lý chi tiết.

## 6. `executeReadWrite` và thao tác sửa thuộc tính

Khi cần trực tiếp dùng `DirContext.modifyAttributes`, callback có thể được chạy qua `executeReadWrite`. Ví dụ sửa thuộc tính `telephoneNumber`:

~~~java
import javax.naming.Name;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;

import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

public final class EmployeePhoneUpdater {
    private final LdapTemplate template;

    public EmployeePhoneUpdater(LdapTemplate template) {
        this.template = template;
    }

    public void updatePhone(String uid, String phone) {
        if (uid == null || !uid.matches("[a-z0-9._-]{1,64}")) {
            throw new IllegalArgumentException("uid không hợp lệ");
        }
        if (phone == null || phone.isBlank()) {
            throw new IllegalArgumentException("phone không hợp lệ");
        }

        Name dn = LdapNameBuilder.newInstance("ou=people")
                .add("uid", uid)
                .build();

        // Tầng service phải kiểm tra quyền người gọi trước khi cập nhật.
        template.executeReadWrite(ctx -> {
            ModificationItem replace = new ModificationItem(
                    DirContext.REPLACE_ATTRIBUTE,
                    new BasicAttribute("telephoneNumber", phone));

            ctx.modifyAttributes(dn, new ModificationItem[] {replace});
            return null;
        });
    }
}
~~~

Ở đây `executeReadWrite` làm rõ rằng callback cần quyền thực hiện thao tác ghi. Nhưng quyền này không tự động được cấp bởi tên phương thức: **danh tính tài khoản LDAP và ACL của server mới quyết định** thao tác có được phép hay không.

**Cần cân nhắc dùng API mức cao thay thế:** với một thao tác sửa `modifyAttributes` đơn giản, code `ldapTemplate.modifyAttributes(dn, modifications)` thường dễ đọc và ít trách nhiệm hơn. Callback trực tiếp hợp lý khi phải tích hợp thêm thao tác JNDI mà overload mức cao không đáp ứng.

### 6.1. Nhiều thao tác trên một context không đồng nghĩa transaction

Xét quy trình gồm hai bước:

~~~java
template.executeReadWrite(ctx -> {
    ctx.modifyAttributes(employeeDn, firstChange);
    ctx.modifyAttributes(groupDn, secondChange);
    return null;
});
~~~

Dù dùng **cùng `DirContext`**, đây vẫn là **hai yêu cầu LDAP riêng**. Nếu cập nhật nhân viên thành công nhưng cập nhật nhóm thất bại, thao tác đầu **không tự rollback**. Nhiều LDAP server có các extension cho transaction hoặc kiểm soát đồng thời ở mức riêng, nhưng không phải đặc tính mặc định của `LdapTemplate` callback và không được tự giả định.

Nếu nghiệp vụ đòi hỏi tính nhất quán, cần giải pháp phù hợp như thiết kế không phụ thuộc vào cập nhật nhiều entry, xử lý bù trừ được quản lý rõ ràng, thao tác một entry duy nhất, hoặc cơ chế đặc thù có hỗ trợ và được kiểm thử của server.

### 6.2. Tránh các lỗi nguy hiểm trong callback ghi

- **Không nhận DN tùy ý từ HTTP request** rồi gọi `unbind` hoặc `modifyAttributes`. Hãy dựng DN từ định danh nghiệp vụ và giới hạn đúng OU.
- **Không dùng một tài khoản bind đặc quyền** chỉ để callback ghi “chạy được”. Phân quyền tối thiểu ở LDAP server.
- **Không tự chuyển sang kết nối không TLS** khi server trả lỗi chứng chỉ.
- **Không coi `lookup` trước `modify` là khóa dữ liệu**; entry có thể thay đổi giữa hai thao tác.
- **Không thực hiện thao tác I/O ngoài LDAP kéo dài trong callback**, vì có thể giữ context/kết nối quá lâu.
- **Không dùng lại context giữa các thread** hoặc lưu vào cache.
- **Không log credential hoặc toàn bộ thuộc tính nhạy cảm** khi xử lý exception.

## 7. Kiểm soát lỗi: JNDI và Spring LDAP

Ở tầng JNDI, các thao tác thường ném `javax.naming.NamingException` hoặc các kiểu con như `NameNotFoundException`, `AuthenticationException`, `CommunicationException`, `NoPermissionException`. Khi callback chạy dưới `LdapTemplate`, nhiều lỗi được chuyển sang hệ ngoại lệ truy cập LDAP của Spring.

Một số định hướng:

| Tình huống | Phản ứng phù hợp |
| --- | --- |
| DN không tồn tại trong một thao tác đọc tùy chọn | Có thể trả `Optional.empty()` nếu xác định đúng loại lỗi |
| Quyền đọc không đủ | Trả lỗi quyền; không giả là “không tìm thấy” trong hệ thống nội bộ |
| Tài khoản dịch vụ bind thất bại | Báo lỗi cấu hình/xác thực phụ thuộc; giám sát |
| Mất kết nối hoặc TLS thất bại | Phân loại lỗi hạ tầng, có timeout và chính sách retry phù hợp |
| `sizeLimitExceeded` / `timeLimitExceeded` | Không coi kết quả từng phần là dữ liệu đầy đủ |
| Alias/referral chưa được xử lý | Phân biệt kết quả chưa đầy đủ với một danh sách khớp rỗng |
| Schema hoặc kiểu thuộc tính sai | Báo lỗi dữ liệu hoặc tương thích schema; không tự ép kiểu tùy tiện |

**Đừng bắt mọi `RuntimeException` trong DAO rồi trả `List.of()`.** Điều đó khiến ứng dụng không thể biết vì sao không tìm thấy nhân viên: thật sự không có dữ liệu, thiếu quyền, hay LDAP đang ngừng hoạt động.

Trong callback đọc, có thể bắt một lỗi JNDI chuyên biệt **chỉ khi nghiệp vụ có cách xử lý hợp lệ**. Những lỗi không xử lý được nên để template chuyển đổi, rồi phân loại ở ranh giới service/controller. Khi cần audit hoặc metric, chỉ ghi loại lỗi và thông tin không nhạy cảm, không đưa password hay dữ liệu cá nhân vào log công khai.

## 8. Callback và LDAP controls: đi thấp tới đâu là đủ?

Một số chức năng LDAP nâng cao dùng **request/response controls**, chẳng hạn phân trang đơn giản (*Simple Paged Results Control*), server-side sorting hoặc những extension được sản phẩm LDAP hỗ trợ. Để thực hiện chúng ở tầng JNDI có thể cần `LdapContext` thay vì chỉ `DirContext`, đồng thời phải kiểm soát vòng đời controls và cookie giữa các trang.

Tuy nhiên, trước khi viết callback và cast context:

- Kiểm tra phiên bản Spring LDAP có hỗ trợ `DirContextProcessor`, bộ xử lý phân trang hoặc API tiện ích phù hợp không.
- Kiểm tra server có hỗ trợ control mong muốn hay không; các server và proxy LDAP có thể khác nhau.
- Xác định cơ chế pooling, cách mượn context và giới hạn thời gian/số trang.
- Nếu cần cookie phân trang, đảm bảo mỗi lượt tìm kiếm dùng cookie đúng và có điều kiện dừng; không tự tổng hợp hàng triệu entry vô hạn.
- Đối với referral, không tự động chuyển tiếp credential tới endpoint ngoài vùng tin cậy.

**Không cast `DirContext` sang `LdapContext` chỉ vì một ví dụ trên mạng**, vì điều đó có thể thất bại nếu context wrapper/provider không hỗ trợ kiểu mong đợi. Ưu tiên API Spring LDAP đã được thiết kế cho controls; nếu thật sự cần JNDI mức thấp, kiểm thử tích hợp với đúng provider.

### 8.1. Chọn lớp API bằng một quy tắc quyết định

~~~mermaid
flowchart TD
    A["Nhu cầu truy cập LDAP"] --> B{"API mức cao đủ đáp ứng?"}
    B -- "Có" --> C["LdapTemplate lookup/search/modify hoặc LdapClient"]
    B -- "Không" --> D{"Chỉ cần ánh xạ entry?"}
    D -- "Có" --> E["AttributesMapper / ContextMapper"]
    D -- "Không" --> F{"Spring có overload hoặc processor phù hợp?"}
    F -- "Có" --> G["Dùng API Spring chuyên biệt"]
    F -- "Không" --> H["ContextExecutor + JNDI"]
    H --> I["Giải phóng enumeration, xử lý lỗi, kiểm thử tích hợp"]
~~~

Chọn API thấp nhất **đủ để thực hiện tính năng cần thiết**, không phải API thấp nhất có thể truy cập.

## 9. Kiểm thử callback và kết nối thật

Đối với callback, unit test và integration test có giá trị khác nhau:

- **Unit test:** kiểm tra validation, cách dựng DN/filter, cách mapper xử lý thuộc tính thiếu và việc phân nhánh ngoại lệ.
- **Integration test:** xác minh `DirContext` được cấp có base phù hợp, LDAP server trả schema/matching rule như mong đợi, ACL được thực thi, TLS được xác minh, tài nguyên đóng đúng khi lỗi, và giới hạn tìm kiếm được áp dụng.

Ví dụ dữ liệu LDAP thử nghiệm (giả định entry `dc=example,dc=org` và `ou=people` đã tồn tại):

~~~ldif
dn: uid=linh,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: linh
cn: Linh Nguyen
sn: Nguyen
mail: linh@example.org
telephoneNumber: +84123456789

dn: uid=mai,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: mai
cn: Mai Tran
sn: Tran
~~~

| Ca | Thao tác / điều kiện | Kỳ vọng |
| --- | --- | --- |
| 1 | `executeReadOnly` đọc mail Linh | Trả đúng địa chỉ email |
| 2 | `executeReadOnly` đọc mail Mai | Trả `Optional.empty()` theo chính sách vì thuộc tính vắng |
| 3 | Lookup UID không tồn tại | Chỉ chuyển đúng lỗi không tồn tại thành kết quả rỗng |
| 4 | Tài khoản thiếu quyền đọc OU | Trả lỗi quyền, không giả là rỗng |
| 5 | `executeReadOnly` dùng `DirContext.search` | Kết quả đúng filter, scope và base |
| 6 | Enumeration bị lỗi trong lúc lặp | `finally` vẫn đóng enumeration |
| 7 | `executeReadWrite` đổi số điện thoại | Sửa đúng entry nếu ACL cho phép |
| 8 | `executeReadWrite` không có quyền ghi | Server từ chối, không đánh dấu thành công |
| 9 | Hai lệnh modify liên tiếp, lệnh thứ hai lỗi | Không mặc định rollback lệnh đầu |
| 10 | Sai base DN hoặc DN bị lặp suffix | Truy vấn thất bại có lý do rõ |
| 11 | Input chứa `*`, `(`, `)` | Filter builder vẫn giữ input là literal, không mở rộng truy vấn |
| 12 | TLS hoặc LDAP server không kết nối được | Phân loại lỗi mạng, không coi “không có entry” |

Khi unit test callback, có thể mô phỏng `DirContext` và kiểm tra lời gọi `getAttributes`, `search` hoặc `modifyAttributes`, cùng việc đóng `NamingEnumeration`. Nhưng **mock không chứng minh ACL, TLS, schema hay provider JNDI đúng**; những yếu tố đó cần được kiểm thử trên server thật hoặc môi trường tích hợp có hành vi phù hợp.

### 9.1. Bài tập thực hành

**Đề bài:** Tạo một service tìm hai thông tin của nhân viên theo `uid`: `mail` và `telephoneNumber`. Nếu entry không có `telephoneNumber` thì trả trạng thái “chưa khai báo”, không thay thế bằng chuỗi rỗng. Chỉ tra cứu trong `ou=people`, giới hạn tối đa một số lượng kết quả phù hợp và đặt timeout.

**Yêu cầu:**

1. Viết giải pháp A với `LdapTemplate.lookup` và mapper.
2. Viết giải pháp B với `executeReadOnly`, dùng `ctx.getAttributes(dn, attributeIds)`.
3. So sánh hai giải pháp theo tiêu chí: số dòng code, quản lý vòng đời context, tính rõ ràng của ngoại lệ và khả năng mở rộng.
4. Tạo một phép tìm kiếm JNDI với `SearchControls`, đóng `NamingEnumeration` trong `finally` và thử đầu vào chứa ký tự filter đặc biệt.
5. Thử cập nhật `telephoneNumber` trên LDAP test qua `executeReadWrite`, sau đó thử với tài khoản không có quyền ghi.

**Kết luận mong đợi:** Với việc đọc hai thuộc tính ở một DN cụ thể, `lookup` thông thường có thể là lựa chọn tốt hơn. `executeReadOnly` chỉ đáng dùng khi cần trực tiếp điều khiển thao tác JNDI hoặc tương tác với khả năng mà API mức cao chưa bao phủ.

## 10. Những sai lầm cần tránh

1. **“Callback giúp bỏ qua ACL.”** Không. Danh tính bind và LDAP server vẫn quyết định quyền đọc/ghi.
2. **“`executeReadOnly` luôn ngăn mọi lệnh ghi.”** Không dùng tên API như rào chắn an ninh; cần ACL thực.
3. **“Cùng một context thì mọi sửa đổi có transaction.”** Không. LDAP thông thường không tự rollback các lệnh độc lập.
4. **“Không cần đóng `NamingEnumeration` vì template sẽ đóng context.”** Sai; callback nên đóng tài nguyên do chính nó tạo trong `finally`.
5. **“Có thể trả `DirContext` từ callback để dùng sau.”** Không. Context được template quản lý theo vòng đời lời gọi.
6. **“Tự nối filter với input rồi gọi `ctx.search` vẫn an toàn nhờ Spring.”** Không. Khi tự dựng filter raw, ứng dụng phải dùng builder/escaping phù hợp.
7. **“Có kết quả trước khi ngoại lệ nghĩa là search hoàn chỉnh.”** Không. Các giới hạn/timeouts/referral có thể làm dữ liệu chưa đầy đủ.
8. **“Callback càng thấp tầng càng tốt.”** Không. Mức thấp hơn tăng mã và trách nhiệm; chỉ dùng khi có nhu cầu cụ thể.

## 11. Câu hỏi tự đánh giá

**Câu 1.** Khi chỉ cần lấy `cn` và `mail` từ một DN đã biết, nên dùng `lookup` với mapper hay `executeReadOnly`?

**Đáp án:** Thường ưu tiên `lookup` với mapper vì ngắn gọn, rõ ràng và template đã quản lý context. Callback mức thấp phù hợp khi có yêu cầu JNDI đặc biệt.

**Câu 2.** `ContextExecutor` giúp làm gì?

**Đáp án:** Thực thi logic JNDI với `DirContext` do `LdapTemplate` cấp và quản lý, qua các phương thức như `executeReadOnly` / `executeReadWrite`.

**Câu 3.** Callback có nên gọi `ctx.close()` không?

**Đáp án:** Không khi context do `LdapTemplate` quản lý. Nhưng callback phải đóng `NamingEnumeration` do nó mở bằng `finally`.

**Câu 4.** Dùng `executeReadWrite` và chạy hai lệnh `modifyAttributes` liên tiếp có bảo đảm cả hai cùng thành công hoặc cùng rollback không?

**Đáp án:** Không. Chúng vẫn là những thao tác LDAP riêng; phải có chính sách nhất quán và xử lý lỗi ở tầng nghiệp vụ.

**Câu 5.** Có thể sử dụng `executeReadOnly` để tránh phải escape giá trị filter từ HTTP request không?

**Đáp án:** Không. JNDI vẫn diễn giải biểu thức filter theo cú pháp LDAP. Dùng `EqualsFilter`, `LdapQueryBuilder` hoặc cơ chế escape an toàn để giữ dữ liệu là literal.

**Câu 6.** Tại sao `ctx.search("ou=people", ...)` thường không nên đưa kèm `dc=example,dc=org` trong cấu hình minh họa?

**Đáp án:** Vì `ContextSource` đã có base `dc=example,dc=org`; tên dùng trong context phải được diễn giải tương đối với base phù hợp, tránh lặp suffix.

**Câu 7.** Callback có thể chứng minh ứng dụng đã xác thực người dùng thành công chỉ bằng việc tìm thấy entry không?

**Đáp án:** Không. Search/lookup là tra cứu; authentication cần cơ chế bind hoặc IdP riêng, sau đó mới thực hiện authorization.

**Ghi nhớ:** Hãy tận dụng `LdapTemplate` để quản lý vòng đời context, chọn mapper hoặc API mức cao khi có thể, và chỉ dùng `ContextExecutor` cho nhu cầu JNDI mức thấp có lý do cụ thể. Trong callback, không giữ context sau lời gọi, đóng enumeration, xây DN/filter an toàn, phân loại lỗi và luôn duy trì TLS, ACL cùng kiểm thử tích hợp.
