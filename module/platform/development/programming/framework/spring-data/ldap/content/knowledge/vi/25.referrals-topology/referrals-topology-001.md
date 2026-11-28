# Referral và continuation reference trong kết quả tìm kiếm

Trong **SPRING_DATA_LDAP**, ứng dụng Java có thể đọc cây thư mục LDAP bằng Spring Data LDAP repository hoặc `LdapTemplate`, ánh xạ entry phân cấp theo DN (*Distinguished Name*), `objectClass` và schema thành đối tượng Java. Tuy nhiên, không phải mọi nhánh trong một cây tên logic đều do cùng một LDAP server quản lý. Khi truy vấn đi qua ranh giới giữa các vùng dữ liệu, server có thể trả về **referral** hoặc **search continuation reference** để báo cho client biết cần hỏi nơi khác.

Đây là điểm đặc biệt quan trọng với truy vấn phạm vi rộng: nhận được một số entry không nhất thiết có nghĩa là đã tìm kiếm hết tất cả nhánh. Bài học này giúp bạn phân biệt hai loại phản hồi, hiểu mối quan hệ với topology LDAP, cấu hình xử lý trong JNDI/Spring LDAP, nhận diện nguy cơ trả dữ liệu thiếu và xây dựng cách kiểm thử phù hợp.

## 1. Topology LDAP: Một cây tên có thể trải trên nhiều server

LDAP tổ chức entry theo cây thông tin thư mục (*Directory Information Tree* — DIT). Mỗi entry có DN duy nhất **trong namespace được quản lý**, ví dụ:

```text
dc=example,dc=org
├── ou=people
│   ├── uid=mai
│   └── uid=an
└── ou=remote
    ├── uid=linh
    └── uid=hoa
```

Đường dẫn đầy đủ đến một entry là `uid=linh,ou=remote,dc=example,dc=org`. Sơ đồ trên chỉ thể hiện **cây tên logic**; cách dữ liệu được lưu trữ có thể khác:

```text
                 Ứng dụng Spring Data LDAP
                            |
                            v
             Server A: ldap-a.example.org
             Naming context: dc=example,dc=org
                  |                 |
                  | ou=people       | ou=remote: nhánh được chuyển giao
                  v                 v
             Entry tại A      Server B: ldap-b.example.org
                              Naming context: ou=remote,
                                              dc=example,dc=org
```

**Naming context** là một phần cây DN mà directory server phục vụ. Các server có thể biết cách định tuyến đến naming context khác bằng dữ liệu hoặc cấu hình referral. Root DSE thường công bố thuộc tính `namingContexts`, nhưng mức độ hiển thị, phân quyền và hỗ trợ tùy server.

Giả sử client gửi tìm kiếm:

```text
base DN: dc=example,dc=org
scope:   SUBTREE
filter:  (objectClass=inetOrgPerson)
```

Server A có thể trả các entry tại `ou=people`, đồng thời hướng dẫn client tiếp tục tìm tại Server B để bao phủ `ou=remote`. Một số hệ thống có thể **tự chuyển tiếp truy vấn (chaining/proxying)** thay vì gửi referral, hoặc sử dụng replica cho cùng một naming context. Cần phân biệt:

- **Referral:** server giới thiệu một đích LDAP khác để client tiếp tục.
- **Chaining/proxying:** server tự hỏi server khác và trả kết quả như một truy vấn do chính nó xử lý.
- **Replication/failover:** nhiều server chứa bản sao hoặc phục vụ cùng vùng dữ liệu; việc chọn server dự phòng không đồng nghĩa với LDAP search reference.

Sự xuất hiện của referral phụ thuộc topology và cấu hình thực tế; không phải mọi tìm kiếm `SUBTREE` đều có referral.

## 2. Phân biệt referral và search continuation reference

Giao thức LDAPv3 định nghĩa các thông điệp khác nhau cho kết quả tìm kiếm:

| Thành phần giao thức | Khi nào xuất hiện | Ý nghĩa đối với client |
|---|---|---|
| `SearchResultEntry` | Tìm thấy một entry phù hợp | Đọc `objectName` (DN) và các `attributes` của entry |
| `SearchResultReference` | Trong luồng kết quả tìm kiếm, có một nhánh/vùng cần được tiếp tục ở nơi khác | Nhận một hoặc nhiều LDAP URL, có thể cần gửi thêm truy vấn |
| `SearchResultDone` với mã `success (0)` | Server hoàn tất phần tìm kiếm do nó xử lý | Chưa tự chứng minh rằng client đã theo mọi continuation reference |
| `SearchResultDone` với mã `referral (10)` | Server không thực hiện được yêu cầu tại chỗ, nhưng biết đích có thể xử lý | Client được giới thiệu sang LDAP server/context khác |

### 2.1. Referral: Đích thay thế cho thao tác hiện tại

Khi yêu cầu nhắm đến vùng mà server đang nhận truy vấn không phục vụ, nó có thể kết thúc thao tác bằng LDAP result code **10 (`referral`)** cùng danh sách URL. Ví dụ tìm trực tiếp entry có base `ou=remote,dc=example,dc=org` tại Server A nhưng A chỉ biết Server B phục vụ vùng này.

Phản hồi minh họa theo cách hiển thị của công cụ `ldapsearch`:

```text
# search result
result: 10 Referral
ref: ldap://ldap-b.example.org/ou=remote,dc=example,dc=org
```

Đây là **phản hồi của thao tác LDAP**. Nó không phải một entry người dùng, cũng không phải thuộc tính `ref` trong DTO.

### 2.2. Continuation reference: Cần tiếp tục một phần tìm kiếm

Trong một tìm kiếm `SUBTREE` rộng, Server A có thể trả entry thuộc vùng mình quản lý và xen kẽ thông điệp `SearchResultReference` trỏ sang Server B.

```text
Client gửi SearchRequest đến A
       |
       +-- SearchResultEntry: uid=mai,ou=people,...
       |
       +-- SearchResultEntry: uid=an,ou=people,...
       |
       +-- SearchResultReference:
       |      ldap://ldap-b.example.org/ou=remote,dc=example,dc=org
       |
       +-- SearchResultDone: success (0)
```

Các dòng hiển thị tương đương có thể là:

```text
dn: uid=mai,ou=people,dc=example,dc=org
uid: mai

# search reference
ref: ldap://ldap-b.example.org/ou=remote,dc=example,dc=org

# search result
result: 0 Success
```

**Điểm mấu chốt:** `SearchResultReference` là một **thông điệp giao thức riêng**, không phải `SearchResultEntry`. `SearchResultDone: success` có thể xuất hiện ngay cả khi client chưa tìm kiếm ở đích được tham chiếu. Nếu bỏ qua continuation reference, tập kết quả ứng dụng thu được có thể **không đầy đủ**.

Hai loại cùng cung cấp LDAP URL, nhưng hoàn cảnh khác nhau: referral báo chuyển hướng thao tác; continuation reference cho biết còn vùng cần tiếp tục trong **khi** tìm kiếm đang thu kết quả. Server và thư viện client có thể xử lý, hiển thị hoặc báo lỗi khác nhau với hai trường hợp này.

## 3. Đọc LDAP URL được trả về

Referral và continuation reference thường chứa một hoặc nhiều **LDAP URL**. Ví dụ:

```text
ldap://ldap-b.example.org:389/ou=remote,dc=example,dc=org??sub?(objectClass=inetOrgPerson)
```

Định dạng khái quát (các thành phần sau DN là tùy chọn):

```text
ldap://host:port/baseDN?attributes?scope?filter?extensions
```

| Thành phần | Ví dụ | Vai trò |
|---|---|---|
| Scheme/host/port | `ldap://ldap-b.example.org:389` | Endpoint mà client được đề xuất kết nối |
| Base DN | `ou=remote,dc=example,dc=org` | Vị trí bắt đầu thao tác bên server đích |
| Attributes | Trống giữa hai dấu `?` | Những thuộc tính yêu cầu trả về, nếu có |
| Scope | `sub` | Phạm vi `base`, `one` hoặc `sub` |
| Filter | `(objectClass=inetOrgPerson)` | Điều kiện tìm kiếm |
| Extensions | Có thể vắng mặt | Phần mở rộng LDAP URL theo quy định giao thức |

Các trường có thể không được chỉ định đầy đủ; client và LDAP provider phải diễn giải theo quy định LDAP URL và ngữ cảnh thao tác. Đừng tự nối chuỗi DN, filter hoặc host để tạo lại yêu cầu khi đã có URL. Nếu xây dựng công cụ xử lý referral riêng, dùng bộ phân tích LDAP URL và cơ chế escape đúng chuẩn.

Một response có thể chứa **nhiều URL** để client thử, nên không được mặc định chỉ có đúng một đích. `ldaps://` sử dụng TLS ngay khi kết nối; `ldap://` thường không mã hóa kết nối trừ khi đã nâng cấp bằng StartTLS theo cơ chế được hỗ trợ. Chính sách bảo mật phải xét scheme và host thực tế.

## 4. JNDI quyết định xử lý referral như thế nào?

Spring LDAP hoạt động trên nền **JNDI** (`javax.naming`). Thuộc tính môi trường `java.naming.referral`, tương đương hằng `Context.REFERRAL`, thường nhận ba giá trị:

| Chế độ | Hành vi mong đợi | Rủi ro/cần lưu ý |
|---|---|---|
| `ignore` | Không chủ động đi theo referral; đây cũng là mặc định JNDI nếu không cấu hình | Kết quả có thể chỉ chứa phần tại server hiện tại; một số provider/server phát sinh `PartialResultException` |
| `follow` | Provider cố tự động theo các đích referral được trả về | Phát sinh kết nối mới; có thể lỗi DNS, TLS, xác thực, vòng lặp hoặc timeout |
| `throw` | Provider báo `ReferralException` để mã gọi chủ động xử lý | Cần luồng xử lý ngoại lệ và chính sách lựa chọn đích rõ ràng |

Giá trị cấu hình được áp dụng trên **JNDI context** và do provider thực thi; các ngoại lệ thực tế còn phụ thuộc thao tác, server và phiên bản thư viện. Trong môi trường dùng Active Directory, cấu hình `ignore` đôi khi dẫn tới **`PartialResultException`** khi tìm kiếm chạm tới referral/continuation reference. Đừng diễn giải ngoại lệ này như một lỗi cú pháp của `AttributesMapper`.

Ví dụ minh họa với JNDI thuần:

```java
import javax.naming.Context;
import java.util.Hashtable;

Hashtable<String, Object> env = new Hashtable<>();
env.put(Context.INITIAL_CONTEXT_FACTORY,
        "com.sun.jndi.ldap.LdapCtxFactory");
env.put(Context.PROVIDER_URL, "ldaps://ldap-a.example.org:636");
env.put(Context.REFERRAL, "throw"); // "ignore", "follow" hoặc "throw"
// Ví dụ chỉ thể hiện cấu hình referral;
// cấu hình xác thực và TLS thực tế được quản lý riêng.
```

Đối với `throw`, lớp `javax.naming.ReferralException` cho phép ứng dụng xem thông tin referral và lựa chọn cách xử lý qua JNDI; khi dùng `LdapTemplate`, ngoại lệ JNDI được Spring LDAP chuyển đổi sang hệ ngoại lệ của Spring. **Không giả định** có thể bắt trực tiếp ngoại lệ JNDI bên ngoài mọi lời gọi `LdapTemplate`.

## 5. Cấu hình trong Spring LDAP / Spring Data LDAP

Các repository của Spring Data LDAP và `LdapTemplate` đều dựa vào thông tin kết nối directory; việc theo hay không theo referral chủ yếu thuộc **`ContextSource`/JNDI provider**. `AttributesMapper` chỉ nhận thuộc tính của entry đã tìm thấy, nên tự nó **không nhận** `SearchResultReference` và không thể quyết định có truy vấn Server B hay không.

Ví dụ cấu hình tường minh để *quan sát và xử lý* referral thay vì tự động đi theo:

**`LdapConfiguration.java`**

```java
package com.example.ldap;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.core.support.LdapContextSource;

@Configuration
public class LdapConfiguration {
    @Bean
    LdapContextSource ldapContextSource(
            @Value("${app.ldap.url}") String url,
            @Value("${app.ldap.base}") String base,
            @Value("${app.ldap.bind-dn}") String bindDn,
            @Value("${app.ldap.bind-password}") String bindPassword) {

        LdapContextSource source = new LdapContextSource();
        source.setUrl(url);
        source.setBase(base);
        source.setUserDn(bindDn);
        source.setPassword(bindPassword);
        source.setReferral("throw");
        return source;
    }

    @Bean
    LdapTemplate ldapTemplate(LdapContextSource source) {
        return new LdapTemplate(source);
    }
}
```

Với ví dụ này, các giá trị `app.ldap.*` được cung cấp từ cấu hình ứng dụng; mật khẩu bind cần lấy từ cơ chế quản lý bí mật, không ghi giá trị thật vào mã nguồn. Khi Spring khởi tạo bean, `LdapContextSource` được khởi tạo theo vòng đời Spring thông thường.

Để đổi sang chế độ tự động theo referral, đặt:

```java
source.setReferral("follow");
```

Chỉ bật `follow` khi hệ thống đã xác định các server đích đáng tin cậy, cách xác thực/TLS và giới hạn tài nguyên phù hợp. Cần cân nhắc giải pháp định tuyến truy vấn chủ động sang các context nguồn được cho phép nếu topology vượt nhiều ranh giới bảo mật.

### 5.1. Truy vấn tìm kiếm và ý nghĩa tập kết quả

Giả sử base DN của `LdapContextSource` là `dc=example,dc=org`. Một lời gọi tìm kiếm:

**`PersonDirectoryReader.java`**

```java
package com.example.ldap;

import java.util.List;
import javax.naming.directory.Attribute;
import javax.naming.directory.InvalidAttributeValueException;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.SearchScope;
import org.springframework.stereotype.Repository;

import static org.springframework.ldap.query.LdapQueryBuilder.query;

@Repository
public class PersonDirectoryReader {
    private final LdapTemplate ldapTemplate;

    public PersonDirectoryReader(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<String> findUids() {
        LdapQuery ldapQuery = query()
                .base("")
                .searchScope(SearchScope.SUBTREE)
                .attributes("uid")
                .countLimit(100)
                .timeLimit(5000)
                .where("objectClass").is("inetOrgPerson");

        AttributesMapper<String> mapper = attrs -> {
            Attribute uid = attrs.get("uid");
            if (uid == null || uid.size() == 0) {
                throw new InvalidAttributeValueException("Entry thiếu uid");
            }
            return (String) uid.get();
        };
        return ldapTemplate.search(ldapQuery, mapper);
    }
}
```

Ở đây, `base("")` là DN rỗng **tương đối với base đã cấu hình**; tìm kiếm có thể đi qua nhiều nhánh nếu topology phân tán. Các giới hạn `countLimit` và `timeLimit` là mức trần cho thao tác tìm kiếm, **không chứng minh** kết quả đã đầy đủ. Bản thân `List<String>` không chứa trạng thái “đã theo hết referral”.

Nếu server trả SearchResultReference, tập kết quả phụ thuộc chế độ JNDI, khả năng truy cập endpoint đích và cách provider xử lý. Nếu yêu cầu nghiệp vụ là “toàn bộ người dùng trong nhiều naming context”, cần kiểm tra đã tìm hết các context dự kiến hoặc thực hiện nhiều truy vấn chủ động và hợp nhất có quy tắc; không suy ra tính đầy đủ chỉ từ việc `search(...)` trả một danh sách.

### 5.2. Có nên bỏ qua PartialResultException?

`LdapTemplate` có cấu hình:

```java
LdapTemplate template = new LdapTemplate(source);
template.setIgnorePartialResultException(true);
```

Tùy cấu hình provider/server, tùy chọn trên có thể hữu ích khi ứng dụng **chấp nhận** chỉ lấy entry từ nhánh mà server hiện tại đã xử lý (thường gặp trong một số tích hợp Active Directory). Nhưng điều này **chỉ bỏ qua ngoại lệ `PartialResultException`**, không làm client theo referral, không khôi phục entry còn thiếu và không biến một truy vấn phân tán thành truy vấn đầy đủ.

Không dùng tùy chọn này làm cách “sửa nhanh” nếu kết quả cần đầy đủ cho phân quyền, đồng bộ danh tính, kiểm kê tài khoản hoặc báo cáo quan trọng. Với các use case đó, nên xác định rõ các nguồn directory, theo dõi nhánh thất bại và chỉ công bố dữ liệu khi đáp ứng yêu cầu hoàn chỉnh.

## 6. Chiến lược xử lý trên topology nhiều máy

Có ba cách tiếp cận điển hình:

1. **Tìm kiếm tại một naming context xác định.** Khi ứng dụng chỉ cần dữ liệu thuộc vùng Server A, giới hạn `base` và `scope` để tránh đi qua nhánh phân tán. Kết quả dễ giải thích, đồng thời giảm nguy cơ dữ liệu bị phân mảnh.
2. **Cho provider theo referral trong miền tin cậy.** Dùng `follow` khi các đích đã được quản trị, mạng/TLS và quyền truy cập đã kiểm tra. Cần đo độ trễ, giới hạn vòng lặp/timeout và xác nhận kết quả từ các vùng dự kiến.
3. **Định tuyến và hợp nhất ở tầng ứng dụng.** Với nhiều forest/domain hoặc các vùng tin cậy khác nhau, lưu danh sách endpoint được phép, chạy truy vấn riêng theo base DN từng vùng, rồi hợp nhất kết quả theo khóa định danh phù hợp. Cách này dễ kiểm soát hơn nếu phải quy định quyền, phạm vi và trạng thái thành công từng vùng.

Trong cách hợp nhất, **DN chỉ có ý nghĩa cùng namespace**; không nên dùng riêng thuộc tính `uid` làm khóa toàn cục nếu nhiều domain có thể trùng `uid`. Có thể cần cặp `(directoryId, DN)` hoặc mã định danh bất biến do directory cung cấp, tùy schema và nghiệp vụ. Phải làm rõ cách xử lý duplicate khi các vùng chứa bản sao dữ liệu.

Nếu dùng Spring Data LDAP repository cho entity gắn `@Entry` và `@Id`, repository vẫn tuân theo phạm vi và khả năng của `ContextSource` đã cấu hình. Không mặc định rằng `findAll()` tự hợp nhất mọi naming context có liên kết referral. Những thao tác ghi (CRUD) qua referral còn cần quy tắc riêng về ownership, quyền và tính nhất quán, không nên suy từ hành vi đọc.

## 7. Bảo mật khi theo referral

**Referral URL là dữ liệu do directory trả về**, nên cần đối xử như một địa chỉ điều hướng có rủi ro trong hệ thống phân tán:

- **Endpoint:** xác định host/domain/port nào được phép. Đừng tự kết nối đến một referral URL không tin cậy hoặc host bên ngoài môi trường quản trị.
- **TLS và xác thực:** dùng LDAPS hoặc StartTLS có xác thực chứng chỉ, tên máy và chuỗi tin cậy; kiểm tra cơ chế JNDI/provider dùng thông tin xác thực nào trên kết nối theo referral. Không mặc định kết nối đến server đích giữ nguyên chính sách bảo mật của server nguồn.
- **Quyền tối thiểu:** tài khoản bind chỉ được phép đọc đúng thuộc tính/nhánh cần thiết; không chuyển tài khoản có quyền quản trị qua các ranh giới directory.
- **Giới hạn:** đặt timeout kết nối/đọc, giới hạn lượt theo referral và phát hiện vòng lặp bằng các cặp endpoint/base DN đã thăm nếu bạn tự triển khai. Một referral có thể dẫn tới referral tiếp theo hoặc endpoint không phản hồi.
- **Dữ liệu:** tránh ghi log mật khẩu, credential, token hoặc nguyên dữ liệu cá nhân; log đủ URL đã làm sạch, mã lỗi, correlation ID và nhánh DN để điều tra.

Đặc biệt, chế độ `follow` là lựa chọn tiện lợi chứ **không phải chính sách allowlist bảo mật**. Nếu buộc phải thực thi danh sách server đích, chính sách xác thực riêng và giới hạn phức tạp, nên sử dụng điều phối kết nối do ứng dụng kiểm soát hoặc tầng directory proxy đáng tin cậy.

## 8. Kiểm thử referral và continuation reference

**Unit test** với `BasicAttributes` chỉ kiểm tra ánh xạ entry; nó không thể tạo ra một `SearchResultReference` của giao thức LDAP. Để kiểm tra referral cần LDAP test server/cụm directory thực sự hỗ trợ topology liên quan, hoặc mock ở mức giao tiếp phù hợp với JNDI provider.

Một ma trận kiểm thử tích hợp:

| Kịch bản | Thiết lập | Điều cần xác minh |
|---|---|---|
| Không có referral | Tìm trên một naming context chỉ có entry cục bộ | Trả đúng entry và các thuộc tính được phép đọc |
| Referral của thao tác | Tìm base DN chỉ được phục vụ bởi B, nhưng gửi tới A | Quan sát result code 10/referral URL hoặc ngoại lệ được provider chuyển đổi |
| Continuation reference | Tìm `SUBTREE` tại A, có nhánh con do B quản lý | Nhận entry ở A và tham chiếu B; hiểu trạng thái kết quả khi chưa theo B |
| `ignore` | Tắt theo referral | Xác định dữ liệu thiếu hay `PartialResultException` tùy server/provider; không giả định một kiểu phản hồi |
| `follow` | B có thể truy cập, TLS/credential hợp lệ | Kiểm tra entry ở B được trả về theo phạm vi mong đợi, không trùng hoặc mất ngoài ý muốn |
| `throw` | Server trả referral | Kiểm tra đường đi ngoại lệ, cách ứng dụng báo kết quả chưa hoàn chỉnh |
| B gặp sự cố | Chặn mạng, DNS sai hoặc chứng chỉ không hợp lệ | Timeout/error được xử lý rõ ràng; không công bố kết quả thiếu như thể hoàn chỉnh |
| Vòng lặp A → B → A | Hai server giới thiệu lẫn nhau (môi trường test) | Không bị lặp vô hạn; có giới hạn thời gian/lượt theo referral |

Có thể thực nghiệm từ command line bằng `ldapsearch` (OpenLDAP client):

```bash
ldapsearch -x -H ldaps://ldap-a.example.org:636 \
  -D "uid=reader,ou=service,dc=example,dc=org" -W \
  -b "dc=example,dc=org" -s sub "(objectClass=inetOrgPerson)" uid cn
```

Trong môi trường kiểm thử, so sánh kết quả khi thay base sang `ou=remote,dc=example,dc=org` và khi bật/tắt cơ chế theo referral tương ứng của công cụ. Chú ý công cụ dòng lệnh và JNDI **không nhất thiết** xử lý referral giống nhau; kết quả từ công cụ chỉ là một bằng chứng về hành vi server.

Nên thu thập cho từng test: endpoint và base DN đã truy vấn, scope/filter, mã kết quả, số entry cục bộ, các continuation/reference được phát hiện, số entry sau khi theo referral, và nhánh bị lỗi. Với API cần dữ liệu hoàn chỉnh, đưa ra quyết định rõ: **thành công đầy đủ**, **thất bại**, hoặc **kết quả một phần có đánh dấu**.

## 9. Các lỗi hiểu nhầm thường gặp

| Hiểu nhầm | Cách hiểu đúng |
|---|---|
| “Có `List<T>` trả về là đã đọc đủ mọi server.” | Chỉ biết mapper đã ánh xạ các entry thực tế được trả về; có thể còn nhánh chưa theo |
| “`SearchResultReference` là một entry LDAP.” | Nó là thông điệp tiếp tục tìm kiếm; không phải dữ liệu entry đưa vào `AttributesMapper` |
| “`SearchResultDone: success` nghĩa là không còn referral.” | Vẫn có thể đã nhận continuation reference cần xử lý |
| “Bật `ignorePartialResultException` sẽ lấy đủ dữ liệu.” | Tùy chọn chỉ bỏ qua một loại ngoại lệ; không theo các đích còn lại |
| “Server B là replica dự phòng của A.” | B có thể sở hữu một naming context khác; referral và failover là hai bài toán |
| “`follow` luôn bảo đảm hoạt động.” | Còn phụ thuộc quyền, endpoint, TLS, network, loop, giới hạn và provider |
| “Repository tự quản lý topology phân tán.” | Repository sử dụng khả năng kết nối và phạm vi của `ContextSource` |

## 10. Câu hỏi tự đánh giá

1. Trong tìm kiếm `SUBTREE`, server trả hai `SearchResultEntry`, một `SearchResultReference` và `SearchResultDone: success`. Vì sao hai entry chưa chắc là toàn bộ kết quả?
2. Phân biệt tình huống dẫn tới LDAP result code `referral (10)` với tình huống xuất hiện `SearchResultReference`.
3. Khi dùng `LdapTemplate.search(...)`, vì sao `AttributesMapper` không phải chỗ phù hợp để xử lý referral URL?
4. Điểm khác nhau giữa `LdapContextSource.setReferral("follow")` và `LdapTemplate.setIgnorePartialResultException(true)` là gì?
5. Khi nào nên chủ động truy vấn nhiều naming context và hợp nhất dữ liệu thay vì bật theo referral tự động?
6. Điều gì phải kiểm chứng trước khi client kết nối đến host được đề xuất qua referral?

**Ghi nhớ:** LDAP referral điều hướng **thao tác** sang một đích khác, còn search continuation reference báo **một phần tìm kiếm** cần được tiếp tục. Trong SPRING_DATA_LDAP, độ đầy đủ của danh sách kết quả phụ thuộc topology, phạm vi tìm kiếm, cấu hình `ContextSource`/JNDI và khả năng truy cập các server liên quan. Luôn thiết kế chính sách xử lý tham chiếu, bảo mật và kiểm thử dựa trên yêu cầu dữ liệu đầy đủ của ứng dụng.

### Tài liệu tham khảo

- IETF [RFC 4511 — Lightweight Directory Access Protocol (LDAP): The Protocol](https://www.rfc-editor.org/rfc/rfc4511), phần tìm kiếm, `SearchResultReference` và result code `referral`.
- IETF [RFC 4516 — Lightweight Directory Access Protocol (LDAP): Uniform Resource Locator](https://www.rfc-editor.org/rfc/rfc4516), cú pháp LDAP URL.
- Oracle Java SE API: [`Context.REFERRAL`](https://docs.oracle.com/en/java/javase/17/docs/api/java.naming/javax/naming/Context.html#REFERRAL), [`ReferralException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.naming/javax/naming/ReferralException.html).
- Spring LDAP API: [`LdapTemplate`](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/core/LdapTemplate.html), [`LdapContextSource`](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/core/support/LdapContextSource.html).
