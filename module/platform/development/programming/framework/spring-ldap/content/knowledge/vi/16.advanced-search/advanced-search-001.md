# SearchControls và các tham số quan trọng trong Spring LDAP

Một LDAP filter đúng chưa đủ để có một truy vấn tốt. Hai yêu cầu cùng dùng `(objectClass=inetOrgPerson)` có thể khác nhau rất lớn về lượng dữ liệu, thời gian chạy và mức độ an toàn: yêu cầu thứ nhất chỉ tra cứu một entry tại DN cụ thể; yêu cầu thứ hai duyệt toàn bộ cây người dùng, tải mọi thuộc tính và trả hàng chục nghìn kết quả. Trong Java, **`javax.naming.directory.SearchControls`** là công cụ JNDI quan trọng để đặt phạm vi tìm kiếm, giới hạn kết quả, thời gian và tập thuộc tính cần lấy.

Bài học thuộc chương **Search nâng cao** trong lộ trình **Spring LDAP**. Người học sẽ thực hành cấu hình `SearchControls`, hiểu ảnh hưởng của từng tham số đến giao thức và tài nguyên, sử dụng nó với JNDI hoặc `LdapTemplate`, đồng thời nhận biết những giới hạn riêng của máy chủ LDAP. Kiến thức này liên kết trực tiếp với cách cấu hình `ContextSource`, tìm theo DN/filter, ánh xạ entry, pooling, TLS và xử lý lỗi khi truy cập dịch vụ thư mục.

## 1. SearchControls nằm ở đâu trong một truy vấn LDAP?

Một yêu cầu LDAP search thường gồm các phần:

1. **Search base**: DN gốc để bắt đầu tìm kiếm, ví dụ `ou=people,dc=example,dc=org`.
2. **Search scope**: xét chính base, các con trực tiếp hay toàn bộ nhánh.
3. **Filter**: biểu thức xác định entry khớp điều kiện, ví dụ `(&(objectClass=inetOrgPerson)(uid=linh))`.
4. **Attribute projection**: tên các thuộc tính cần nhận, chẳng hạn `uid`, `cn` và `mail`.
5. **Limits**: giới hạn số entry và thời gian xử lý.
6. **Tùy chọn xử lý liên kết/kết quả**: ví dụ trả đối tượng Java hay dereference JNDI link, tùy provider.

Với JNDI, **base** và **filter** thường được truyền trực tiếp vào phương thức `DirContext.search(...)`; `SearchControls` gói các tùy chọn còn lại:

~~~java
NamingEnumeration<SearchResult> results =
        ctx.search("ou=people", "(uid=linh)", controls);
~~~

Trong Spring LDAP, `LdapTemplate` có thể nhận `SearchControls` trực tiếp qua overload tìm kiếm hoặc nhận một `LdapQuery` được tạo bằng `LdapQueryBuilder`. Cả hai cách đều phải quy về các đặc tính tìm kiếm mà LDAP server hỗ trợ.

~~~mermaid
flowchart TD
    A["Ứng dụng Java"] --> B["Search base + LDAP filter"]
    A --> C["SearchControls"]
    C --> D["Scope"]
    C --> E["Time / count limit"]
    C --> F["Returning attributes"]
    C --> G["Tùy chọn JNDI"]
    B --> H["JNDI DirContext.search()"]
    D --> H
    E --> H
    F --> H
    G --> H
    H --> I["LDAP server: schema + ACL + giới hạn server"]
    I --> J["NamingEnumeration<SearchResult>"]
    J --> K["Đọc và ánh xạ DTO"]
    K --> L["Đóng enumeration và context"]
~~~

**SearchControls không phải là LDAP filter** và cũng không chứa thông tin xác thực. Danh tính kết nối, endpoint, TLS và thông tin bind thường đến từ `ContextSource`/JNDI context. SearchControls chỉ mô tả cách thực hiện một lần tìm kiếm.

## 2. Các thuộc tính của SearchControls

Các setter/getter quan trọng trong JNDI chuẩn:

| Setter | Giá trị/kiểu | Mục đích |
|---|---|---|
| `setSearchScope(int)` | `OBJECT_SCOPE`, `ONELEVEL_SCOPE` hoặc `SUBTREE_SCOPE` | Xác định phần DIT được duyệt |
| `setCountLimit(long)` | Số nguyên không âm; `0` là không đặt giới hạn từ control | Giới hạn số entry trả về |
| `setTimeLimit(int)` | Số nguyên không âm, **mili giây**; `0` là không đặt giới hạn từ control | Giới hạn thời gian tìm kiếm yêu cầu |
| `setReturningAttributes(String[])` | Danh sách tên attribute, `null` hoặc mảng rỗng | Chọn tập thuộc tính trả về |
| `setReturningObjFlag(boolean)` | `true`/`false` | Quyết định có yêu cầu trả đối tượng Java liên kết với kết quả JNDI hay không |
| `setDerefLinkFlag(boolean)` | `true`/`false` | Điều khiển xử lý **JNDI links** theo cơ chế provider hỗ trợ |

Ví dụ cấu hình rõ ràng để tìm người dùng trong một nhánh:

~~~java
import javax.naming.directory.SearchControls;

SearchControls controls = new SearchControls();

controls.setSearchScope(SearchControls.SUBTREE_SCOPE);
controls.setCountLimit(100);
controls.setTimeLimit(5_000);
controls.setReturningAttributes(new String[] {
        "uid", "cn", "mail"
});
controls.setReturningObjFlag(false);
controls.setDerefLinkFlag(false);
~~~

Đây là một đối tượng Java **mutable**: các setter thay đổi trạng thái của chính instance đó. Đối với ứng dụng nhiều request, nên tạo cấu hình SearchControls cho từng lời gọi hoặc dùng đối tượng được quản lý riêng theo phạm vi request; đừng để nhiều thread cùng chỉnh sửa một instance dùng chung.

### Giá trị mặc định đáng nhớ

Khi dùng constructor không tham số `new SearchControls()`, các giá trị mặc định trong API JNDI là:

| Thuộc tính | Mặc định | Hệ quả |
|---|---|---|
| Search scope | `ONELEVEL_SCOPE` | Chỉ các entry con trực tiếp của search base |
| Count limit | `0` | Không đặt giới hạn số entry bằng SearchControls |
| Time limit | `0` | Không đặt giới hạn thời gian bằng SearchControls |
| Returning attributes | `null` | Yêu cầu các attribute thông thường theo ngữ nghĩa của provider/server |
| Returning object flag | `false` | Không yêu cầu trả đối tượng Java liên kết |
| Dereference link flag | `false` | Không yêu cầu dereference JNDI link |

**Không đặt giới hạn trong SearchControls không đồng nghĩa với “không bao giờ bị giới hạn”.** LDAP server có thể áp hạn mức riêng theo tài khoản, cấu hình hoặc loại truy vấn; proxy/network cũng có timeout riêng. Khi debug một truy vấn khó hiểu, hãy ghi rõ cấu hình thay vì dựa vào mặc định.

## 3. Search scope: OBJECT, ONELEVEL, SUBTREE

Giả sử cây LDAP có dữ liệu:

~~~text
dc=example,dc=org
├── ou=people
│   ├── uid=linh
│   ├── uid=an
│   └── ou=contractors
│       ├── uid=binh
│       └── uid=mai
└── ou=groups
    └── cn=developers
~~~

Chọn search base là `ou=people,dc=example,dc=org`.

### 3.1. OBJECT_SCOPE: chỉ xét base

~~~java
controls.setSearchScope(SearchControls.OBJECT_SCOPE);
~~~

Phạm vi gồm **chính entry `ou=people`**, không gồm người dùng `uid=linh` hoặc `uid=binh`. Scope này hữu ích để đọc một entry đã biết DN, chẳng hạn kiểm tra attribute `ou` của phòng ban.

Nếu filter là `(objectClass=inetOrgPerson)` và base là organizational unit, kết quả có thể rỗng vì chính base không phải entry người.

### 3.2. ONELEVEL_SCOPE: con trực tiếp

~~~java
controls.setSearchScope(SearchControls.ONELEVEL_SCOPE);
~~~

Phạm vi xét `uid=linh`, `uid=an` và `ou=contractors`. Nó **không đi xuống** `uid=binh` hay `uid=mai` vì các entry đó là cháu của base.

Đây là mặc định của `new SearchControls()`. Vì thế một truy vấn “thiếu người dùng ở thư mục con” có thể bắt nguồn từ scope chưa được đặt, không phải LDAP server mất dữ liệu.

### 3.3. SUBTREE_SCOPE: cả base và mọi cấp dưới

~~~java
controls.setSearchScope(SearchControls.SUBTREE_SCOPE);
~~~

Phạm vi xét base và tất cả các entry nằm dưới nó, bao gồm người dùng trong `ou=contractors`. Scope này phù hợp khi nghiệp vụ cần tìm toàn bộ người dùng ở mọi đơn vị dưới nhánh đã chọn.

| Scope | Base `ou=people` | Con trực tiếp | Cháu/nhiều cấp | Trường hợp sử dụng |
|---|---|---|---|---|
| `OBJECT_SCOPE` | Có | Không | Không | Đọc/kiểm tra entry tại DN cụ thể |
| `ONELEVEL_SCOPE` | Không | Có | Không | Liệt kê các tài khoản trực thuộc một OU |
| `SUBTREE_SCOPE` | Có | Có | Có | Tìm xuyên các OU con |

**Chọn base hẹp trước, sau đó mới chọn scope phù hợp.** Một `SUBTREE_SCOPE` trên toàn miền `dc=example,dc=org` thường tốn nhiều dữ liệu hơn cùng filter dưới `ou=people`. Việc dùng subtree không tự động gây chậm, nhưng kết quả có thể lớn hơn và phụ thuộc index, filter, schema, ACL.

## 4. Count limit: giới hạn số entry

Cấu hình:

~~~java
controls.setCountLimit(50L);
~~~

`setCountLimit(long)` đặt mức tối đa **số entry** yêu cầu trả về trong một thao tác search. Giá trị `0` là không áp đặt giới hạn từ SearchControls, không phải “trả về 0 kết quả”.

Ví dụ:

- Nhánh có 20 entry khớp, đặt `50`: dự kiến có thể nhận đủ 20 entry, nếu không có giới hạn khác.
- Nhánh có 2.000 entry khớp, đặt `50`: kết quả bị giới hạn; **không được kết luận chỉ có 50 entry**.
- Đặt `0`: không yêu cầu giới hạn phía client qua thuộc tính này, nhưng server có thể giới hạn ở 100, 1.000 hoặc một mức khác tùy cấu hình.

**Count limit không phải phân trang.** Nó không có thông tin offset, số trang hoặc cookie. Nếu tìm kiếm yêu cầu nhiều đợt kết quả, cần thiết kế paging với cơ chế server hỗ trợ, chẳng hạn LDAP Simple Paged Results (RFC 2696), chứ không tăng count limit hoặc giả định rằng lần gọi tiếp theo lấy phần còn lại.

### Kết quả có thể không đầy đủ

Khi vượt giới hạn số lượng do client/server áp đặt, provider có thể thông báo lỗi dạng `SizeLimitExceededException` hoặc mã LDAP `sizeLimitExceeded` (4), tùy bối cảnh. Dữ liệu được đọc trước khi exception phát sinh có thể chỉ là **kết quả một phần**.

Không nên viết nghiệp vụ:

~~~java
if (results.size() == 50) {
    // Sai: kết luận LDAP chỉ có đúng 50 tài khoản.
}
~~~

Mặt khác, nếu nhận ít hơn 50 entry cũng không đủ để chứng minh tất cả dữ liệu đã được thấy: còn phải tính đến quyền đọc, filter, timeout và giới hạn server. Nên thiết kế API trả kèm trạng thái đầy đủ/chưa đầy đủ khi việc thiếu kết quả gây hậu quả nghiệp vụ.

### Count limit không thay thế giới hạn ứng dụng

Nếu endpoint web công bố một API tìm kiếm tổng quát, vẫn cần giới hạn số phần tử trả cho client, request rate, kích thước payload và tập thuộc tính. Cấu hình count limit giúp giảm chi phí LDAP search, nhưng không tự kiểm soát toàn bộ bộ nhớ, JSON serialization hoặc lưu lượng từ ứng dụng ra internet.

## 5. Time limit: giới hạn thời gian xử lý

Cấu hình:

~~~java
controls.setTimeLimit(3_000); // 3.000 mili giây theo API JNDI.
~~~

Tham số của `setTimeLimit(int)` được diễn giải bằng **milliseconds**, không phải giây. Giá trị `0` nghĩa là không đặt giới hạn thời gian qua SearchControls. Cần phân biệt với **LDAP protocol timeLimit**, được biểu diễn bằng đơn vị giây khi gửi trên giao thức; việc chuyển đổi/áp dụng giới hạn phụ thuộc LDAP provider và server.

| Cơ chế | Ví dụ | Phạm vi ảnh hưởng |
|---|---|---|
| `SearchControls.setTimeLimit(3000)` | 3 giây ở mức API JNDI | Giới hạn thời gian cho yêu cầu tìm kiếm; provider/server quyết định cách thực thi |
| JNDI connect timeout | `com.sun.jndi.ldap.connect.timeout` | Chờ thiết lập kết nối của JDK LDAP provider |
| JNDI read timeout | `com.sun.jndi.ldap.read.timeout` | Chờ phản hồi mạng ở JDK LDAP provider |
| Server search time limit | Chính sách server theo user/search | Máy chủ từ chối hoặc kết thúc truy vấn vượt hạn mức |
| Timeout ở tầng HTTP/business | Ví dụ request deadline 5 giây | Toàn bộ chuỗi nghiệp vụ, không chỉ một thao tác LDAP |

**Search time limit không phải một deadline tuyệt đối cho toàn bộ HTTP request.** Thời gian tạo kết nối, bind, retry, đọc phản hồi, ánh xạ kết quả và thực thi nhiều truy vấn có thể góp phần vào tổng độ trễ. Đặt SearchControls time limit không thay thế read/connect timeout.

Khi quá thời gian, có thể gặp `TimeLimitExceededException` (JNDI) hoặc kết quả LDAP `timeLimitExceeded` (3). Một số entry có thể đã được trả trước khi exception xuất hiện; cần quyết định nghiệp vụ có chấp nhận dữ liệu một phần không.

### Không đặt timeout tùy tiện theo một phép thử nhỏ

Giới hạn quá thấp khiến kết quả chập chờn trên mạng chậm; quá cao có thể khiến tài nguyên bị giữ lâu khi LDAP server không phản hồi. Hãy đo các truy vấn điển hình, dùng filter/index hợp lý và tính đến hạn mức của server. Với dữ liệu nhạy cảm hoặc thao tác trước khi xóa hàng loạt, **kết quả timeout không đủ để chứng minh nhánh đã được duyệt hết**.

## 6. Returning attributes: chỉ lấy dữ liệu cần dùng

Nếu không giới hạn, một search có thể kéo về nhiều attribute không cần thiết. Chẳng hạn màn hình danh sách nhân viên chỉ hiển thị mã, tên và email:

~~~java
controls.setReturningAttributes(new String[] {
        "uid", "cn", "mail"
});
~~~

Điều này giúp giảm payload và tránh lấy thêm dữ liệu mà ứng dụng không cần, nhưng không thay thế ACL của server. Cần phân biệt ba trường hợp:

| Thiết lập | Ý nghĩa thông thường |
|---|---|
| `setReturningAttributes(null)` | Không chỉ định danh sách cụ thể; yêu cầu các attribute mặc định của provider/server, thường là các user attributes |
| `setReturningAttributes(new String[0])` | Yêu cầu **không trả attribute**, chỉ lấy thông tin về entry theo khả năng của API |
| `setReturningAttributes(new String[] {"uid", "cn"})` | Chỉ yêu cầu hai attribute được nêu |

Một số **operational attributes** (như `modifyTimestamp`, `entryUUID` khi được hỗ trợ) không nhất thiết có trong kết quả “lấy tất cả” thông thường; cần yêu cầu rõ tên và có quyền truy cập. Cú pháp đặc biệt như `*` cho user attributes hoặc `+` cho operational attributes phụ thuộc chuẩn LDAP/protocol và mức hỗ trợ của server/provider.

### Không được nhầm projection với filter

Một filter vẫn có thể sử dụng attribute không nằm trong `returningAttributes`. Ví dụ:

~~~text
Filter:             (&(objectClass=inetOrgPerson)(uid=linh))
Returning attrs:    cn, mail
~~~

Máy chủ lọc theo `uid`, nhưng kết quả không bắt buộc chứa `uid` vì client không yêu cầu. Nếu mapper Java đọc `attrs.get("uid").get()`, nó có thể gặp `NullPointerException`. Hãy đồng bộ danh sách attribute trả về với thứ mà callback thực sự sử dụng.

### Trường hợp đặc biệt: chỉ cần biết entry có tồn tại

Một truy vấn kiểm tra sự tồn tại có thể dùng scope phù hợp, filter hẹp và không yêu cầu attribute:

~~~java
SearchControls existsControls = new SearchControls();
existsControls.setSearchScope(SearchControls.OBJECT_SCOPE);
existsControls.setReturningAttributes(new String[0]);
existsControls.setCountLimit(1);
~~~

Ví dụ này chỉ mô tả **cấu hình truy vấn**; việc kết quả trả về hay không còn phụ thuộc search base, filter và quyền đọc. Không dùng “không tìm thấy trong search” để khẳng định entry không tồn tại về mặt vật lý nếu caller không có quyền đọc.

## 7. Returning object flag: khi nào cần trả object Java?

Mặc định:

~~~java
controls.setReturningObjFlag(false);
~~~

`returningObjFlag` liên quan cơ chế trả **Java object liên kết với kết quả JNDI**, nếu provider/namespace có cách biểu diễn các đối tượng đó. Trong LDAP directory thông thường, ứng dụng Spring LDAP phần lớn chỉ cần `Attributes` của entry và DN, nên để `false` là lựa chọn đơn giản và phù hợp.

Đặt `true` không làm máy chủ trả về DTO Java của ứng dụng, cũng không tự động ánh xạ LDAP entry sang entity ODM. Các cơ chế JNDI object binding/deserialization tùy môi trường có thể mang rủi ro bảo mật nếu cấu hình không an toàn.

Với Spring LDAP, nếu cần DTO Java, hãy dùng:

- `AttributesMapper<T>` để ánh xạ attribute được trả về.
- `ContextMapper<T>` khi cần cả thông tin DN/context của entry.
- ODM của Spring LDAP khi mô hình dữ liệu và phiên bản thư viện phù hợp.

**Mapping là công việc của ứng dụng**, khác với cờ `returningObjFlag` của JNDI.

## 8. Dereference link flag và LDAP alias không hoàn toàn giống nhau

Cờ:

~~~java
controls.setDerefLinkFlag(false);
~~~

`derefLinkFlag` thuộc hợp đồng **JNDI links**, chẳng hạn các tên liên kết kiểu `LinkRef` mà một naming provider hỗ trợ. Không nên mặc định rằng chuyển cờ này sang `true` sẽ điều khiển toàn bộ cách LDAP server xử lý **alias entries** theo giao thức.

LDAPv3 có trường **derefAliases** trong SearchRequest với các lựa chọn như:

- Không dereference alias.
- Dereference alias khi tìm base.
- Dereference alias trong quá trình search.
- Dereference trong cả hai trường hợp.

Cách thiết lập những tùy chọn alias này trong JNDI LDAP provider có thể qua cấu hình môi trường provider (ví dụ thuộc tính `java.naming.ldap.derefAliases` của JDK provider) hoặc cơ chế riêng, không chỉ cờ link của SearchControls. Với Spring LDAP, hãy kiểm tra cấu hình provider và cách framework chuyển yêu cầu.

**Khi nào cần quan tâm?** Directory có alias/referral hoặc liên kết tên có thể trả kết quả khác dự kiến, phát sinh vòng lặp tham chiếu hoặc vượt phạm vi dự kiến nếu provider theo liên kết. Tránh bật dereference tùy tiện trong truy vấn cần giới hạn nghiêm ngặt nhánh dữ liệu.

## 9. Ví dụ JNDI hoàn chỉnh: search có kiểm soát và dọn tài nguyên

Giả sử `ContextSource` đã đặt base DN `dc=example,dc=org`. Yêu cầu: tìm trong `ou=people`, bao gồm OU con, chỉ lấy `uid`, `cn`, `mail`, tối đa 100 kết quả và giới hạn search 4 giây.

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.logging.Level;
import java.util.logging.Logger;

import javax.naming.NamingEnumeration;
import javax.naming.NamingException;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;
import javax.naming.directory.DirContext;
import javax.naming.directory.SearchControls;
import javax.naming.directory.SearchResult;

import org.springframework.ldap.core.ContextSource;
import org.springframework.ldap.support.LdapUtils;

public final class ControlledSearchRepository {
    private static final Logger LOGGER =
            Logger.getLogger(ControlledSearchRepository.class.getName());

    public record Person(String uid, String name, String mail) {}

    private final ContextSource contextSource;

    public ControlledSearchRepository(ContextSource contextSource) {
        this.contextSource = contextSource;
    }

    public List<Person> findByUid(String uid) throws NamingException {
        SearchControls controls = new SearchControls();
        controls.setSearchScope(SearchControls.SUBTREE_SCOPE);
        controls.setCountLimit(100L);
        controls.setTimeLimit(4_000);
        controls.setReturningAttributes(new String[] {"uid", "cn", "mail"});
        controls.setReturningObjFlag(false);

        DirContext ctx = null;
        NamingEnumeration<SearchResult> results = null;

        try {
            ctx = contextSource.getReadOnlyContext();

            // filterArgs để JNDI escape giá trị uid trong biểu thức filter.
            results = ctx.search(
                    "ou=people",
                    "(&(objectClass=inetOrgPerson)(uid={0}))",
                    new Object[] {uid},
                    controls
            );

            List<Person> people = new ArrayList<>();
            while (results.hasMore()) {
                SearchResult entry = results.next();
                Attributes attrs = entry.getAttributes();

                people.add(new Person(
                        firstString(attrs.get("uid")),
                        firstString(attrs.get("cn")),
                        firstString(attrs.get("mail"))
                ));
            }
            return people;
        } finally {
            if (results != null) {
                try {
                    results.close();
                } catch (NamingException e) {
                    LOGGER.log(Level.WARNING,
                            "Cannot close LDAP search results", e);
                }
            }
            LdapUtils.closeContext(ctx);
        }
    }

    private static String firstString(Attribute attribute)
            throws NamingException {
        return attribute == null
                ? null
                : (String) attribute.get();
    }
}
~~~

Giải thích mối liên hệ giữa SearchControls và code:

- **Search base** `ou=people` là DN tương đối so với base của `ContextSource` trong ví dụ.
- **Filter** chọn đúng `inetOrgPerson` với UID mong muốn. Mảng `filterArgs` giúp xử lý ký tự đặc biệt của giá trị; không ghép user input trực tiếp thành chuỗi LDAP filter.
- **Scope subtree** cho phép tìm ở cả các OU bên dưới `ou=people`.
- **Count/time limit** tạo ranh giới chi phí truy vấn; nếu provider/server kết thúc do limit, tầng trên cần xử lý tình trạng kết quả không đầy đủ thay vì tin danh sách là hoàn chỉnh.
- **Projection** lấy đúng ba attribute mapper cần dùng.
- **Enumeration** được đóng trước context, kể cả nếu `hasMore()`, `next()` hoặc mapping ném exception.
- **Context** được đóng/trả pool bởi đoạn code lấy context từ `ContextSource`. Dùng `LdapTemplate` thì framework sẽ thực hiện vòng đời này.

> Trong JNDI tiêu chuẩn, `DirContext` và `NamingEnumeration` có phương thức `close()` nhưng không phải lúc nào cũng dùng trực tiếp được trong `try-with-resources` vì các interface này không mở rộng `AutoCloseable`. Dùng `try/finally` khi trực tiếp quản lý chúng.

### Vì sao không trả `NamingEnumeration` cho controller?

Kết quả JNDI có thể được lấy **từng phần trong lúc duyệt**, nên enumeration có thể còn phụ thuộc kết nối hoặc trạng thái server. Nếu trả enumeration ra khỏi phương thức và đóng context ở `finally`, code ở controller có thể không đọc tiếp được. Nếu không đóng context, lại có nguy cơ rò rỉ tài nguyên.

Cách làm phù hợp là duyệt/map thành danh sách DTO trong phạm vi context còn mở rồi trả dữ liệu độc lập.

## 10. Spring LDAP: cấu hình tìm kiếm qua LdapQueryBuilder

Khi không có yêu cầu JNDI cấp thấp, **`LdapTemplate`** thường giúp code ngắn và quản lý vòng đời tài nguyên tốt hơn. Spring LDAP có API dựng query, dùng những khái niệm giống SearchControls:

~~~java
import java.util.List;

import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.SearchScope;

import static org.springframework.ldap.query.LdapQueryBuilder.query;

public final class PersonSearchService {
    private final LdapTemplate ldapTemplate;

    public PersonSearchService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<String> findNames(String uid) {
        LdapQuery ldapQuery = query()
                .base("ou=people")
                .searchScope(SearchScope.SUBTREE)
                .countLimit(100)
                .timeLimit(4_000)
                .attributes("uid", "cn")
                .where("objectClass").is("inetOrgPerson")
                .and("uid").is(uid);

        return ldapTemplate.search(
                ldapQuery,
                (AttributesMapper<String>) attrs -> {
                    if (attrs.get("cn") == null) {
                        return null;
                    }
                    return (String) attrs.get("cn").get();
                }
        );
    }
}
~~~

Ở đây, `searchScope`, `countLimit`, `timeLimit` và `attributes` tương ứng trực tiếp với các lựa chọn của SearchControls. `LdapQueryBuilder` tạo filter từ các điều kiện đã mô tả và xử lý escape giá trị theo API; `LdapTemplate.search(...)` lấy context, chạy truy vấn và trả kết quả đã ánh xạ.

Trong một số phiên bản hoặc overload của Spring LDAP, có thể truyền `SearchControls` trực tiếp cho `LdapTemplate.search(...)`:

~~~java
SearchControls controls = new SearchControls();
controls.setSearchScope(SearchControls.SUBTREE_SCOPE);
controls.setCountLimit(100);
controls.setReturningAttributes(new String[] {"uid", "cn"});

List<String> names = ldapTemplate.search(
        "ou=people",
        "(objectClass=inetOrgPerson)",
        controls,
        (AttributesMapper<String>) attrs -> (String) attrs.get("cn").get()
);
~~~

Lựa chọn giữa `LdapQueryBuilder` và `SearchControls` phụ thuộc phiên bản Spring LDAP cũng như kiểu API cần dùng. Hãy kiểm tra signature của thư viện đang chạy. Mô hình JNDI vẫn là cơ sở để hiểu filter, scope, count/time limit và attribute projection của truy vấn.

### Chú ý khi ánh xạ kết quả

Nếu mapper yêu cầu DN, `AttributesMapper` chỉ nhận attribute được chọn, không phải luôn có DN của entry. Trong Spring LDAP, `ContextMapper` (hoặc API mapper có context thích hợp) giúp lấy thông tin về entry và tên. Không thể giả định DN xuất hiện như một attribute `dn` trong `returningAttributes`; DN là tên entry, không phải attribute schema thông thường.

Một số attribute có nhiều giá trị: mapper không nên luôn ép thành một chuỗi. Với `member` hoặc `objectClass`, cần duyệt các giá trị theo API `Attribute.getAll()` nếu ứng dụng thật sự cần đầy đủ.

## 11. Phân biệt SearchControls với cấu hình kết nối và giới hạn server

Một số vấn đề tìm kiếm chỉ được giải quyết bằng cấu hình khác:

| Vấn đề | Tham số/cơ chế liên quan | Không nên nhầm với |
|---|---|---|
| Chỉ muốn tìm một OU | Search base và scope | URL máy chủ LDAP |
| Muốn giảm số entry trả về | Count limit và filter hẹp | Paging đầy đủ |
| Muốn ngừng search lâu | Time limit, chính sách server | Connect/read timeout của provider |
| Muốn giảm dữ liệu mỗi entry | Returning attributes | ACL và quy tắc bảo mật |
| Muốn kết quả nhiều trang | LDAP Simple Paged Results/control phù hợp | `setCountLimit` |
| Muốn kết quả có thứ tự | Server-side sort control nếu được hỗ trợ hoặc sắp xếp tại ứng dụng | `setSearchScope` |
| Muốn bảo mật kết nối | LDAPS/StartTLS, xác thực chứng chỉ | SearchControls |
| Muốn tái sử dụng kết nối | Pooling của provider/Spring LDAP | SearchControls |
| Muốn điều khiển referral | Cấu hình JNDI/server/LDAP controls | Mặc định của scope |
| Muốn thao tác đúng DN | DN builder và base DN đúng | Filter tìm kiếm |

### Giới hạn server có thể chặt hơn client

Ví dụ client đặt count limit 2.000 và time limit 10 giây, nhưng LDAP server quy định trả tối đa 500 entry và xử lý search tối đa 5 giây. Truy vấn vẫn chịu giới hạn phía server. Cần thống nhất chính sách với quản trị directory và xử lý lỗi một cách rõ ràng.

Ngoài ra, hiệu năng có thể bị ảnh hưởng bởi:

- Attribute được filter có được lập index hay không.
- Filter có sử dụng substring đầu chuỗi `(cn=*linh*)`, thường đắt hơn equality nếu cấu hình index không phù hợp.
- Search base có bao trùm quá nhiều entry không liên quan.
- Độ phức tạp của filter kết hợp `AND`, `OR`, `NOT`.
- Quyền đọc của tài khoản bind và số attribute yêu cầu trả về.
- Độ trễ mạng, cấu hình pool, chính sách alias/referral và khả năng xử lý song song của server.

Điều chỉnh SearchControls nên đi kèm đo lường search latency, lượng kết quả, tần suất lỗi và tải phía server, thay vì chỉ tăng timeout sau mỗi lỗi.

## 12. Kết quả một phần và ngoại lệ khi duyệt

Một điểm dễ bỏ sót: **`DirContext.search(...)` có thể trả về `NamingEnumeration` trước khi toàn bộ dữ liệu đã được đọc**. Lỗi do time/size limit, kết nối, referral hoặc quyền đọc có thể xảy ra trong `hasMore()` và `next()`.

Ví dụ nguy hiểm:

~~~java
NamingEnumeration<SearchResult> results =
        ctx.search(base, filter, controls);

while (results.hasMore()) {
    process(results.next());
}

// Nếu hasMore() ném lỗi, việc đóng có thể bị bỏ qua.
// Nếu process() ghi DB từng entry, có thể đã ghi một phần dữ liệu.
~~~

Vì vậy cần:

1. Đóng enumeration và context trong `finally` hoặc để Spring LDAP quản lý qua template.
2. Xác định nghiệp vụ có chấp nhận **kết quả một phần** hay phải coi cả truy vấn là thất bại.
3. Nếu đang đồng bộ hoặc chuẩn bị xóa hàng loạt, chỉ áp dụng thay đổi khi tập dữ liệu được xác minh đủ và phù hợp giới hạn.
4. Phân biệt `NameNotFoundException`/`noSuchObject`, `SizeLimitExceededException`, `TimeLimitExceededException`, lỗi quyền và lỗi mạng.
5. Ghi log loại query, base/scope và chỉ số vận hành phù hợp, nhưng tránh ghi mật khẩu hoặc attribute nhạy cảm.

Đối với nghiệp vụ hiển thị danh sách kết quả gợi ý, một tập hữu hạn có thể chấp nhận được nếu giao diện ghi rõ “chỉ hiển thị tối đa N kết quả”. Nhưng với nghiệp vụ đối soát toàn bộ tài khoản, **không thể âm thầm coi danh sách cắt ở N là dữ liệu đầy đủ**.

## 13. Truy vấn thực tế: cân bằng độ chính xác, hiệu năng và an toàn

Giả sử hệ thống quản lý nhân viên hỗ trợ ba tác vụ:

| Tác vụ | Base | Scope | Count limit | Trả attribute |
|---|---|---|---|---|
| Kiểm tra một entry theo DN | DN người dùng cụ thể | `OBJECT_SCOPE` | `1` | Chỉ attribute cần xác minh |
| Liệt kê nhân viên trực tiếp thuộc OU | `ou=sales,ou=people` | `ONELEVEL_SCOPE` | Theo giới hạn màn hình | `uid`, `cn`, `mail` |
| Tìm nhân viên toàn bộ công ty | `ou=people` | `SUBTREE_SCOPE` | Có giới hạn hoặc paging | Chỉ trường phục vụ kết quả |

### A. Kiểm tra tồn tại tại DN cụ thể

Nếu đã biết DN, search scope `OBJECT_SCOPE` tránh duyệt các entry con. Khi chỉ cần biết có entry nào khớp filter, request có thể dùng mảng returning attributes rỗng.

### B. Liệt kê một OU trực tiếp

Đặt `ONELEVEL_SCOPE` để không vô tình lấy tài khoản ở các OU con. Nếu danh sách có thể dài, kết hợp paging và giới hạn output; count limit một lần không cung cấp nhiều trang.

### C. Tìm toàn bộ nhánh nhân viên

Dùng `SUBTREE_SCOPE` nhưng giới hạn base ở `ou=people`, không tìm trên toàn bộ naming context khi không cần. Có filter đúng schema, dựa trên attribute được index nếu có, chỉ lấy những trường cần hiển thị.

**Khi input là dữ liệu người dùng**, dùng builder của Spring LDAP hoặc tham số JNDI `filterArgs`. Các ký tự `*`, `(`, `)`, backslash và NUL có ý nghĩa đặc biệt trong LDAP filter theo RFC 4515. Không ghép chuỗi filter thủ công để tránh kết quả sai hoặc LDAP filter injection.

## 14. Lỗi cấu hình SearchControls thường gặp

| Triệu chứng | Nguyên nhân khả dĩ | Cách xử lý |
|---|---|---|
| Không thấy entry ở OU con | Dùng `ONELEVEL_SCOPE` mặc định | Chọn `SUBTREE_SCOPE` khi thực sự cần |
| Trả quá nhiều entry | Base rộng, filter yếu, count limit = 0 | Thu hẹp base/filter; đặt giới hạn thích hợp |
| Mapper đọc `mail` bị null | Không yêu cầu attribute hoặc bị ACL che | Kiểm tra `returningAttributes` và xử lý attribute vắng mặt |
| Có đúng 100 kết quả nhưng biết còn nhiều | `setCountLimit(100)` hoặc giới hạn server | Kiểm tra limit và dùng paging phù hợp |
| Search dừng sau 3 giây | `setTimeLimit(3000)` hoặc giới hạn/timeout khác | Tách bạch search time, connect/read và server limit |
| Search vẫn chậm dù đặt time limit | Chờ kết nối, networking hoặc nhiều thao tác | Kiểm tra toàn bộ pipeline và timeout của provider |
| Kết quả không theo thứ tự mong muốn | SearchControls không quy định sort | Sử dụng server sort hoặc sort trong ứng dụng |
| Bật `setDerefLinkFlag(true)` mà alias không đổi | Nhầm JNDI link với LDAP alias | Kiểm tra cấu hình alias dereferencing của provider |
| Có kết quả một phần rồi ném exception | Server/client limit hoặc lỗi trong khi duyệt | Cleanup, phân loại lỗi và không dùng dữ liệu như tập đầy đủ |
| Gọi cùng SearchControls ở nhiều thread bị thay đổi bất thường | Instance mutable bị chỉnh sửa đồng thời | Tạo SearchControls riêng theo request |

## 15. Thực hành tự kiểm tra

**Tình huống:** Directory có cấu trúc:

~~~text
ou=people,dc=example,dc=org
├── uid=mai
├── uid=an
└── ou=contractors
    ├── uid=binh
    └── uid=linh
~~~

Một trang quản trị cần tìm tối đa 20 tài khoản, kể cả tài khoản trong `ou=contractors`, chỉ hiển thị mã và tên. Tài khoản sử dụng có quyền đọc phù hợp. Giới hạn thời gian xử lý search ở mức 2.500 ms.

**Bài tập 1.** Chọn search base, scope, count limit, time limit và danh sách returning attributes.

**Đáp án gợi ý:**

~~~java
SearchControls controls = new SearchControls();
controls.setSearchScope(SearchControls.SUBTREE_SCOPE);
controls.setCountLimit(20L);
controls.setTimeLimit(2_500);
controls.setReturningAttributes(new String[] {"uid", "cn"});
~~~

Search base là `ou=people` (tương đối với `ContextSource` có base `dc=example,dc=org`). Filter thích hợp có thể là `(objectClass=inetOrgPerson)` hoặc thêm điều kiện tìm kiếm người dùng. Cấu hình này cho **tối đa** 20 kết quả, không chứng minh chỉ có 20 entry trong directory.

**Bài tập 2.** Nếu đổi scope thành `ONELEVEL_SCOPE`, những entry nào không còn thuộc phạm vi truy vấn?

**Đáp án:** `uid=binh` và `uid=linh` nằm dưới `ou=contractors` sẽ không được xét. `uid=mai` và `uid=an` vẫn thuộc phạm vi tìm kiếm.

**Bài tập 3.** Khi chỉ muốn trả DN, không cần attribute, bạn dùng returning attributes như thế nào?

**Đáp án:** Có thể đặt `new String[0]`. DN của kết quả được truy cập qua thông tin tên của `SearchResult`/context theo API/provider; đừng giả định DN có sẵn dưới attribute `dn`.

**Bài tập 4.** Sau khi lấy 20 entry, có thể khẳng định không còn entry nào không?

**Đáp án:** Không. `countLimit(20)` chỉ giới hạn tập trả về trong lần search, và server có thể áp các giới hạn khác. Nếu cần đầy đủ, phải kiểm tra trạng thái kết thúc của search và dùng cơ chế paging phù hợp.

**Bài tập 5.** Nếu LDAP server timeout sau khi đã nhận 12 entry, tầng service đồng bộ danh sách người dùng nên làm gì?

**Đáp án:** Đánh dấu truy vấn thất bại hoặc chưa hoàn chỉnh, giải phóng tài nguyên, ghi log an toàn và có chiến lược thử lại dựa trên trạng thái thực. Không dùng 12 entry đó làm danh sách toàn bộ để xóa hoặc vô hiệu hóa những người không xuất hiện.

**Bài tập 6.** `setDerefLinkFlag(true)` có đảm bảo mọi alias LDAP sẽ được dereference không?

**Đáp án:** Không. Cần phân biệt JNDI link với LDAP alias và xem cơ chế cấu hình alias dereferencing của provider/server.

## 16. Câu hỏi ôn tập

**1. `SearchControls` chứa search base và filter không?**

Không. Trong JNDI, base và filter thường được truyền vào `DirContext.search(...)`; SearchControls mô tả scope, projection, giới hạn và vài tùy chọn kết quả.

**2. Search scope nào cho phép tìm cả trong các OU con nhiều cấp?**

`SUBTREE_SCOPE`, bao gồm cả entry base.

**3. `setCountLimit(0)` có nghĩa là không trả entry?**

Không. Nó có nghĩa không đặt giới hạn số lượng qua tham số này; server vẫn có thể áp hạn mức riêng.

**4. `setTimeLimit(2000)` có nghĩa là hai nghìn giây?**

Không. Đơn vị của API JNDI là mili giây; `2000` tương ứng 2 giây theo yêu cầu từ client.

**5. Truy vấn có filter theo `uid` nhưng mapper không đọc được `uid` vì sao?**

Nếu `uid` không nằm trong danh sách `returningAttributes`, server không nhất thiết trả giá trị attribute đó, dù filter vẫn dùng được nó. ACL cũng có thể hạn chế.

**6. `NamingEnumeration` đã trả một vài kết quả rồi ném `TimeLimitExceededException` có được coi là truy vấn thành công không?**

Không mặc nhiên. Đó là dữ liệu có thể chưa đầy đủ; nghiệp vụ phải quyết định cách xử lý và giải phóng tài nguyên.

**7. Spring LDAP có thể cấu hình scope và giới hạn mà không tạo SearchControls trực tiếp không?**

Có. Với phiên bản hỗ trợ, `LdapQueryBuilder` cung cấp các lựa chọn tương ứng để xây dựng `LdapQuery`, sau đó thực thi qua `LdapTemplate`.

## Tài liệu tham khảo

- [Java JNDI SearchControls](https://docs.oracle.com/en/java/javase/17/docs/api/java.naming/javax/naming/directory/SearchControls.html): ý nghĩa các setter, kiểu giá trị và mặc định.
- [Java JNDI DirContext](https://docs.oracle.com/en/java/javase/17/docs/api/java.naming/javax/naming/directory/DirContext.html): các overload `search()`.
- [Java NamingEnumeration](https://docs.oracle.com/en/java/javase/17/docs/api/java.naming/javax/naming/NamingEnumeration.html): cơ chế duyệt và đóng kết quả.
- [Spring LDAP Reference](https://docs.spring.io/spring-ldap/reference/): `ContextSource`, `LdapTemplate` và các mẫu tìm kiếm.
- [Spring LDAP API — LdapQueryBuilder](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/query/LdapQueryBuilder.html): các lựa chọn query builder trong phiên bản sử dụng.
- [RFC 4511 — LDAP: The Protocol](https://www.rfc-editor.org/rfc/rfc4511): SearchRequest, scope, limit và kết quả truy vấn.
- [RFC 4515 — LDAP: String Representation of Search Filters](https://www.rfc-editor.org/rfc/rfc4515): cú pháp và cách escape LDAP filter.
- [RFC 2696 — LDAP Control Extension for Simple Paged Results](https://www.rfc-editor.org/rfc/rfc2696): phân trang phía LDAP server.

## Ghi nhớ

**`SearchControls` xác định một truy vấn LDAP được mở rộng đến đâu, lấy bao nhiêu entry, được xử lý trong khoảng thời gian nào và trả những attribute gì.** Ba lựa chọn quan trọng nhất là **scope**, **count/time limit** và **returning attributes**; các cờ returning object và dereference link là chi tiết JNDI cần hiểu đúng mục đích. Trong Spring LDAP, có thể dùng các ý tưởng này qua `LdapTemplate`, `LdapQueryBuilder` hoặc JNDI trực tiếp. Chọn base hẹp, filter được escape đúng, giới hạn phù hợp, ánh xạ dữ liệu cần thiết và luôn xử lý tình trạng kết quả một phần sẽ giúp tìm kiếm thư mục hiệu quả, an toàn và dễ chẩn đoán hơn.
