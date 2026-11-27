# LDAP bind authentication là gì?

Trong một ứng dụng dùng **Spring LDAP**, người dùng có thể đăng nhập bằng tài khoản được quản lý ở một dịch vụ thư mục như OpenLDAP hoặc Active Directory. Thay vì tự lưu và so khớp mật khẩu trong ứng dụng, backend yêu cầu máy chủ LDAP xác minh danh tính thông qua thao tác **bind**. Cơ chế này được gọi là **LDAP bind authentication**.

Ví dụ: nhân viên nhập tên đăng nhập `lan` và mật khẩu trên trang nội bộ. Ứng dụng Spring tìm ra Distinguished Name (DN) của tài khoản `lan`, sau đó thử bind đến LDAP bằng DN và mật khẩu được cung cấp. Máy chủ LDAP quyết định bộ thông tin xác thực đó có hợp lệ hay không.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt `bind`, `search` và kiểm tra quyền (authorization) trong LDAP.
- Giải thích được hai cách đăng nhập phổ biến: **bind trực tiếp theo DN** và **tìm DN rồi bind**.
- Mô tả vai trò của tài khoản dịch vụ, `ContextSource` và `LdapTemplate.authenticate(...)` trong Spring LDAP.
- Nhận biết các rủi ro liên quan đến TLS, mật khẩu rỗng, LDAP filter injection, thông báo lỗi và vòng đời kết nối.
- Triển khai một ví dụ xác thực căn bản, đồng thời xác định được các trường hợp cần kiểm thử.

## 1. Bind là thao tác gì trong LDAP?

LDAP là giao thức truy cập dịch vụ thư mục. Mỗi entry có một **DN** định danh vị trí trong cây thư mục, chẳng hạn:

~~~text
uid=lan,ou=people,dc=example,dc=org
~~~

Trong đó, `uid=lan` là Relative Distinguished Name (RDN) của entry; các thành phần `ou=people`, `dc=example` và `dc=org` tạo nên đường dẫn đến entry. Giá trị `uid` là một thuộc tính và **không tự động đồng nghĩa với DN đầy đủ**.

**Bind** là yêu cầu thiết lập danh tính xác thực cho một phiên làm việc LDAP. Ở kiểu **simple bind** thường gặp, client gửi DN (hoặc tên định danh được máy chủ chấp nhận) cùng mật khẩu đến máy chủ; máy chủ trả về kết quả thành công hoặc thất bại. Một số máy chủ cũng hỗ trợ bind qua **SASL** (ví dụ cơ chế dựa trên Kerberos), có quy trình trao đổi thông tin xác thực khác simple bind.

| Khái niệm | Chức năng | Ví dụ |
|---|---|---|
| `Search` | Tìm entry thỏa điều kiện | Tìm tài khoản có `uid=lan` trong `ou=people` |
| `Bind` | Xác lập danh tính trên kết nối LDAP | Bind bằng DN của Lan và mật khẩu vừa nhập |
| `Compare` | Đối chiếu một giá trị thuộc tính theo quy tắc máy chủ | Kiểm tra một thuộc tính có giá trị chỉ định; không thay thế đầy đủ cho quy trình bind xác thực người dùng |
| `Authorization` | Kiểm tra danh tính đã xác thực có quyền thực hiện hành động hay không | Xét nhóm hoặc quyền trước khi truy cập chức năng quản trị |

Khi bind thành công, máy chủ xác nhận thông tin xác thực theo chính sách của nó. **Bind thành công không đồng nghĩa với có mọi quyền**, cũng không tự tạo HTTP session, cookie hay JWT cho ứng dụng. Ứng dụng phải tự quyết định quy tắc phân quyền và cách duy trì phiên đăng nhập.

> **Điểm mấu chốt:** Với bind authentication, ứng dụng không cần đọc thuộc tính `userPassword` để tự so sánh mật khẩu. Máy chủ LDAP thực hiện việc kiểm tra mật khẩu và chính sách tài khoản; cách lưu mật khẩu bên trong thư mục do máy chủ quản lý.

## 2. Luồng xác thực diễn ra như thế nào?

Có hai chiến lược thường gặp, tùy ứng dụng đã biết DN người dùng hay chưa.

### 2.1. Bind trực tiếp khi biết DN

Giả sử tổ chức quy định mỗi người dùng đều nằm dưới `ou=people,dc=example,dc=org`, với RDN luôn là `uid=<tên đăng nhập>`. Ứng dụng có thể dựng DN từ tên đăng nhập rồi thử bind:

1. Nhận `username=lan` và mật khẩu từ biểu mẫu đăng nhập.
2. Tạo DN `uid=lan,ou=people,dc=example,dc=org` bằng API dựng DN an toàn.
3. Mở ngữ cảnh LDAP và thử simple bind với DN cùng mật khẩu của người dùng.
4. Nếu máy chủ chấp nhận, trả về kết quả xác thực thành công; nếu từ chối thì thất bại.
5. Đóng ngữ cảnh xác thực sau khi hoàn thành.

Ưu điểm là không cần tìm kiếm entry trước khi xác thực. Hạn chế là cách này **chỉ phù hợp khi quy tắc DN thực sự ổn định**. Trong thực tế, tài khoản có thể nằm ở các organizational unit (OU) khác nhau, bị chuyển OU hoặc dùng RDN là `cn` thay vì `uid`.

Khi dựng DN từ đầu vào, phải escape giá trị RDN đúng chuẩn, ví dụ dùng `LdapNameBuilder` hoặc API `javax.naming.ldap.Rdn`. Nối chuỗi tùy ý từ dữ liệu người dùng có thể tạo DN sai hoặc gây lỗi về bảo mật.

### 2.2. Tìm DN rồi bind (search + bind)

Trong hệ thống thực tế, người dùng thường chỉ biết tên đăng nhập hoặc email, không biết DN. Khi đó, ứng dụng tìm tài khoản trước rồi mới kiểm tra mật khẩu.

~~~mermaid
sequenceDiagram
    actor U as Người dùng
    participant App as Ứng dụng Spring
    participant Dir as Máy chủ LDAP
    U->>App: Gửi username + password qua HTTPS
    App->>Dir: Bind bằng tài khoản dịch vụ (cho phép tìm kiếm)
    Dir-->>App: Thành công
    App->>Dir: Search uid=lan trong ou=people
    Dir-->>App: DN của entry khớp
    App->>Dir: Bind riêng với DN người dùng + password
    alt Thông tin xác thực hợp lệ
        Dir-->>App: Bind thành công
        App-->>U: Đăng nhập thành công theo chính sách ứng dụng
    else Không hợp lệ
        Dir-->>App: Bind thất bại
        App-->>U: Thông báo đăng nhập không thành công
    end
~~~

Chi tiết từng bước:

1. **Service bind:** backend dùng tài khoản kỹ thuật có quyền tìm kiếm tối thiểu cần thiết (chẳng hạn `cn=svc-reader,ou=system,dc=example,dc=org`). Một số thư mục cho phép tìm kiếm ẩn danh, nhưng ứng dụng doanh nghiệp thường kiểm soát quyền tìm qua tài khoản dịch vụ.
2. **Search:** tìm entry bằng bộ lọc LDAP, ví dụ `(&(objectClass=inetOrgPerson)(uid=lan))` với phạm vi tìm kiếm trong `ou=people`.
3. **Lấy DN:** kết quả có thể là `uid=lan,ou=people,dc=example,dc=org`. Ứng dụng phải thiết kế để mỗi tên đăng nhập ánh xạ tới **đúng một danh tính**; hai entry cùng phù hợp là vấn đề cần xử lý, không nên mặc nhiên chọn ngẫu nhiên.
4. **User bind:** tạo ngữ cảnh xác thực bằng **DN của người dùng** và mật khẩu vừa nhập. Kết quả bind là bằng chứng xác thực do LDAP trả về.
5. **Đóng/ngắt kết nối phù hợp:** kết nối/ngữ cảnh dùng cho user bind không được vô tình trở thành kết nối có quyền dùng cho các thao tác quản trị tiếp theo.

Một entry người dùng có thể có dạng (cố ý bỏ qua thuộc tính mật khẩu):

~~~ldif
dn: uid=lan,ou=people,dc=example,dc=org
objectClass: inetOrgPerson
uid: lan
cn: Lan Tran
sn: Tran
mail: lan@example.org
~~~

Không cần lấy `userPassword` từ entry để xác thực. Việc tìm DN và thử bind cũng là hai bước khác nhau: tìm thấy người dùng **không có nghĩa** người đó đã được xác thực.

### 2.3. So sánh hai chiến lược

| Tiêu chí | Bind trực tiếp | Search rồi bind |
|---|---|---|
| Đầu vào | Tên đăng nhập có thể suy ra DN theo quy tắc cố định | Tên đăng nhập/email; DN được tra cứu |
| Search trước khi xác thực | Không bắt buộc | Có |
| Tài khoản dịch vụ để tìm kiếm | Thường không cần | Thường cần nếu không cho search ẩn danh |
| Dễ thích ứng khi di chuyển entry giữa các OU | Thấp | Cao hơn, nếu phạm vi tìm kiếm đủ rộng |
| Rủi ro thiết kế | Suy DN sai, ghép DN không escape | Bộ lọc không escape, kết quả không duy nhất, quyền search quá rộng |

## 3. LDAP bind authentication trong Spring LDAP

Spring LDAP xây dựng các API trên Java Naming and Directory Interface (JNDI), giúp ứng dụng làm việc với dịch vụ thư mục qua `ContextSource`, `LdapTemplate`, `LdapClient` và các tiện ích thao tác DN, filter. Đối với bài toán đăng nhập bằng bind:

- **`ContextSource`** quản lý cách tạo ngữ cảnh kết nối LDAP, gồm URL, base DN và thông tin xác thực cho hoạt động tra cứu.
- **`LdapTemplate`** cung cấp phương thức `authenticate(...)` cho kịch bản tìm entry bằng filter rồi xác thực bằng mật khẩu người dùng.
- **`LdapClient`** là một API hướng fluent cho nhiều thao tác LDAP; khi chọn API xác thực, cần kiểm tra chữ ký phương thức theo phiên bản Spring LDAP đang dùng.
- **Spring Security LDAP** cung cấp thành phần xác thực cho hệ thống dùng Spring Security. Ví dụ `BindAuthenticator` có thể tham gia vào luồng xác thực bảo mật của web app; nó là một lớp tích hợp khác với việc gọi `LdapTemplate.authenticate(...)` thủ công.

### 3.1. Ví dụ với Spring Boot và `LdapTemplate.authenticate(...)`

Giả định ứng dụng đã khai báo dependency Spring LDAP (chẳng hạn thông qua Spring Boot starter phù hợp) và có `LdapTemplate` được cấu hình. Cấu hình minh họa:

~~~yaml
# application.yml - giá trị minh họa; đặt secret vào biến môi trường
spring:
  ldap:
    urls: ldaps://ldap.example.org:636
    base: dc=example,dc=org
    username: cn=svc-reader,ou=system,dc=example,dc=org
    password: ${LDAP_READER_PASSWORD}
~~~

Trong cấu hình trên, `username` và `password` là thông tin của **tài khoản dịch vụ dùng để truy vấn**, không phải tài khoản người dùng cuối đăng nhập. Máy chủ cần cho phép tài khoản này tìm kiếm những entry phù hợp. Hãy lấy mật khẩu từ biến môi trường hoặc secret manager và cấp quyền đọc tối thiểu.

Đoạn mã Java sau mô tả cách tìm DN qua `uid` và để LDAP kiểm tra mật khẩu:

~~~java
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;
import org.springframework.stereotype.Service;

@Service
public class LdapBindLoginService {

    private final LdapTemplate ldapTemplate;

    public LdapBindLoginService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public boolean authenticate(String username, String password) {
        // Tránh gửi yêu cầu bind với mật khẩu rỗng.
        if (username == null || username.isBlank()
                || password == null || password.isEmpty()) {
            return false;
        }

        LdapQuery userQuery = LdapQueryBuilder.query()
                .base("ou=people")
                .where("objectClass").is("inetOrgPerson")
                .and("uid").is(username);

        return ldapTemplate.authenticate(userQuery, password);
    }
}
~~~

**Giải thích các điểm quan trọng:**

1. `base("ou=people")` giới hạn khu vực tìm kiếm tương đối với `spring.ldap.base`, do đó trong ví dụ này ứng dụng tìm dưới `ou=people,dc=example,dc=org`.
2. `where(...).is(username)` dùng query builder để tạo filter với giá trị đầu vào được xử lý theo quy tắc escape LDAP filter. Không nên tự nối filter kiểu `"(uid=" + username + ")"`.
3. `ldapTemplate.authenticate(userQuery, password)` thực hiện luồng xác thực dựa trên truy vấn: tìm DN phù hợp rồi thử xác thực mật khẩu với máy chủ LDAP. API trả về `boolean` cho kết quả xác thực.
4. Ví dụ là **dịch vụ xác thực ở tầng ứng dụng**, chưa tự tạo `SecurityContext`, session, JWT, chính sách khóa tài khoản hay quyền truy cập endpoint. Với ứng dụng Spring Security, hãy tích hợp kết quả vào cơ chế xác thực/ủy quyền của Spring Security thay vì tự coi giá trị `true` là toàn bộ quy trình bảo mật.
5. Nếu LDAP không kết nối được, TLS lỗi hoặc không đủ quyền tìm kiếm, cần coi đó là **sự cố hệ thống**; không nên tự động kết luận người dùng nhập sai mật khẩu. Phân biệt lỗi khi ghi log/giám sát, đồng thời trả phản hồi bên ngoài đủ trung tính.

Đoạn ví dụ giả định dữ liệu thư mục tuân thủ quy tắc `uid` duy nhất trong phạm vi truy vấn. Nếu thiết kế thực tế cho phép nhiều entry cùng `uid`, phải có bước xác minh tính duy nhất/điều chỉnh mô hình định danh trước khi chấp nhận kết quả xác thực.

### 3.2. Kiểm tra bind bên ngoài ứng dụng

Với bộ công cụ dòng lệnh OpenLDAP, có thể thử một simple bind bằng tài khoản thử nghiệm:

~~~bash
ldapwhoami -x \
  -H ldaps://ldap.example.org:636 \
  -D "uid=lan,ou=people,dc=example,dc=org" \
  -W
~~~

Trong đó `-x` yêu cầu simple authentication, `-H` chỉ máy chủ LDAP qua TLS, `-D` là bind DN và `-W` yêu cầu nhập mật khẩu qua prompt thay vì ghi mật khẩu trực tiếp trong dòng lệnh. Kết quả bind thành công thường trả về danh tính hiện tại (ví dụ `dn:uid=lan,ou=people,dc=example,dc=org`). Với mật khẩu sai, máy chủ có thể trả mã `invalidCredentials (49)`.

Lệnh này kiểm tra trực tiếp hành vi của server và kết nối. Nó không chứng minh riêng phần search, phân quyền hay quản lý session trong ứng dụng Spring đã đúng.

## 4. Những trường hợp dễ nhầm lẫn

### Bind bằng tài khoản dịch vụ khác gì bind người dùng?

Tài khoản dịch vụ giúp ứng dụng **đọc thư mục** (search, lấy DN, lấy thông tin cho phép). Bind của người dùng giúp chứng minh **mật khẩu do người dùng nhập hợp lệ**. Nếu chỉ bind bằng tài khoản dịch vụ thành công rồi thấy entry của người dùng tồn tại, ứng dụng **chưa xác thực người dùng**.

### Mật khẩu sai, không tìm thấy người dùng và LDAP mất kết nối có giống nhau?

Không:

| Tình huống | Ý nghĩa | Xử lý |
|---|---|---|
| Không thấy entry khớp `uid` | Không xác định được danh tính để thử bind | Thất bại xác thực; không tiết lộ tài khoản có tồn tại hay không |
| User bind trả `invalidCredentials (49)` | Máy chủ từ chối thông tin xác thực; có thể còn liên quan chính sách của server | Thất bại xác thực; không ghi lại mật khẩu |
| Search bị chặn do quyền hoặc base DN sai | Ứng dụng tra cứu không hợp lệ | Sửa cấu hình và ACL; ghi log kỹ thuật |
| Lỗi DNS, kết nối, chứng chỉ hoặc TLS | Hạ tầng thư mục chưa sẵn sàng hoặc cấu hình kết nối sai | Phân loại là lỗi dịch vụ, theo dõi và xử lý riêng |
| Có nhiều entry khớp định danh | Quy tắc ánh xạ tên đăng nhập không duy nhất | Từ chối trường hợp mơ hồ và sửa chính sách định danh |
| Bind thành công nhưng không đủ quyền ứng dụng | Người dùng xác thực hợp lệ nhưng chưa được phép truy cập tính năng | Kiểm tra authorization sau authentication |

### Bind ẩn danh hoặc mật khẩu rỗng có nghĩa là đăng nhập thành công?

**Không.** LDAP có các trạng thái kết nối ẩn danh và một số triển khai hỗ trợ *unauthenticated simple bind*: gửi tên định danh khác rỗng với mật khẩu rỗng nhưng phiên vẫn được xem là ẩn danh. Vì vậy, ứng dụng phải từ chối mật khẩu rỗng trước khi gọi bind và phải kiểm tra danh tính được xác thực thực sự đúng yêu cầu. Không được coi một phản hồi bind thành công trong ngữ cảnh ẩn danh là bằng chứng người dùng đã đăng nhập.

### Bind có đồng nghĩa với kiểm tra nhóm LDAP?

Không. Bind xác thực **ai đang đăng nhập**. Sau khi bind thành công, ứng dụng có thể đọc thuộc tính hoặc tra cứu nhóm (ví dụ quan hệ `member` / `memberOf`, tùy schema và máy chủ) để quyết định **được làm gì**. Sự hiện diện của `memberOf` không phải quy tắc chung bắt buộc với mọi LDAP server.

## 5. Yêu cầu an toàn khi triển khai

1. **Bảo vệ đường truyền:** dùng LDAPS (thường cổng `636`) hoặc StartTLS (thường nâng cấp kết nối từ cổng `389`) **trước khi gửi thông tin xác thực**. HTTPS bảo vệ đoạn trình duyệt → backend, còn TLS/LDAPS bảo vệ đoạn backend → LDAP; cần cả hai khi có thông tin bí mật đi qua.
2. **Xác minh máy chủ LDAP:** kiểm tra chuỗi chứng chỉ, tên máy chủ, truststore và thời hạn chứng chỉ. Không tắt kiểm tra TLS để chạy được trên môi trường production.
3. **Không chấp nhận mật khẩu rỗng:** tránh vô tình nhầm bind ẩn danh với user bind hợp lệ. Không gửi mật khẩu qua URL, query string hoặc log.
4. **Hạn chế quyền của tài khoản dịch vụ:** chỉ cấp quyền đọc vùng và thuộc tính cần thiết; không dùng tài khoản quản trị toàn thư mục cho xác thực hằng ngày.
5. **Escape đầu vào đúng ngữ cảnh:** dùng query builder cho **LDAP filter**, dùng API dựng DN cho **RDN/DN**. Đây là hai quy tắc escape khác nhau; escape filter không thay thế cho escape DN.
6. **Đảm bảo định danh duy nhất:** xác định phạm vi search rõ ràng, cố định quy tắc định danh và xử lý trường hợp nhiều entry khớp; với hệ thống nhiều miền/OU cần thiết kế thêm ánh xạ danh tính đáng tin cậy.
7. **Kiểm soát lỗi và brute force:** giới hạn tốc độ đăng nhập, giám sát lỗi, tránh thông báo giúp dò tài khoản, áp dụng chính sách khóa tài khoản theo yêu cầu tổ chức. Không tự suy luận rằng mọi server LDAP có cùng chính sách khóa.
8. **Quản lý ngữ cảnh/kết nối:** trả hoặc đóng đúng context sau mỗi thao tác; không tái sử dụng context đã bind bằng người dùng cho các thao tác cần danh tính tài khoản dịch vụ. Nếu bật pooling, phải hiểu chính sách pooling theo danh tính và bảo mật của cấu hình LDAP.
9. **Tách authentication khỏi authorization:** chỉ cấp session/quyền sau khi bind thành công và các điều kiện bổ sung (nhóm, trạng thái tài khoản, chính sách nội bộ) đều đáp ứng.

## 6. Kịch bản thực hành và cách kiểm chứng

Giả sử môi trường thử nghiệm có hai tài khoản, `uid=lan` và `uid=minh`, dưới `ou=people,dc=example,dc=org`. Tài khoản dịch vụ có quyền search nhưng không có quyền sửa entry.

**Bước 1 — Chuẩn bị kết nối.** Cấu hình địa chỉ LDAPS, base DN, tài khoản dịch vụ và truststore. Xác nhận có thể truy vấn một entry thử nghiệm bằng tài khoản dịch vụ.

**Bước 2 — Thực hiện search + bind.** Gọi `LdapBindLoginService.authenticate("lan", <mật khẩu đúng>)` rồi lặp lại với mật khẩu sai. Bảo đảm code không đọc `userPassword` và không in mật khẩu trong log.

**Bước 3 — Kiểm thử các nhánh khó.** Thử bảng tình huống sau:

| Đầu vào/điều kiện | Kết quả mong đợi |
|---|---|
| `lan` + mật khẩu đúng | Xác thực thành công |
| `lan` + mật khẩu sai | Xác thực thất bại |
| `khong-ton-tai` + mật khẩu bất kỳ | Xác thực thất bại, phản hồi không làm lộ sự tồn tại của tài khoản |
| Mật khẩu rỗng hoặc `null` | Bị chặn trước khi gửi bind |
| `uid` chứa ký tự đặc biệt như `*`, `(`, `)`, dấu `\` | Được mã hóa an toàn trong filter, không làm thay đổi điều kiện search ngoài ý muốn |
| Chứng chỉ LDAP không đáng tin cậy | Kết nối TLS thất bại an toàn |
| Tài khoản dịch vụ mất quyền tìm kiếm | Ghi nhận lỗi cấu hình/quyền truy cập để xử lý |
| Hai entry cùng tên đăng nhập trong vùng search | Phát hiện định danh mơ hồ; không chấp nhận bất kỳ entry nào một cách tùy tiện |
| User bind đúng nhưng không thuộc nhóm được phép dùng ứng dụng | Authentication thành công; authorization từ chối truy cập |

**Bước 4 — Kiểm tra vận hành.** Quan sát log với correlation ID, thời gian phản hồi, tỷ lệ lỗi bind và lỗi kết nối mà không chứa mật khẩu. Kiểm tra việc đóng context sau các nhánh thành công và lỗi.

> **Giới hạn của ví dụ:** Đoạn code Spring ở trên minh họa đường xác thực bằng `LdapTemplate`, không triển khai toàn bộ các bước kiểm tra tính duy nhất, giới hạn tốc độ, session và chính sách phân quyền. Những phần đó cần được bổ sung tùy schema, chính sách tổ chức và tầng bảo mật của ứng dụng.

## 7. Tự kiểm tra kiến thức

1. Tại sao chỉ tìm thấy một entry có `uid=lan` chưa đủ để cho người dùng đăng nhập?
2. Khi tên đăng nhập của một nhân viên giữ nguyên nhưng DN thay đổi do chuyển OU, chiến lược nào thuận tiện hơn: direct bind hay search + bind?
3. Vì sao cần ngăn mật khẩu rỗng ngay từ tầng ứng dụng, dù máy chủ LDAP trả về kết quả bind?
4. Khi `ldapTemplate.authenticate(...)` báo lỗi kết nối TLS, vì sao không nên ghi log rằng “người dùng nhập sai mật khẩu”?
5. Một người dùng bind thành công nhưng không thuộc nhóm được quyền xem báo cáo nội bộ. Bước nào cần quyết định từ chối truy cập?

**Gợi ý trả lời:** (1) Search chỉ chứng minh entry tồn tại; cần user bind để kiểm chứng thông tin xác thực. (2) Search + bind linh hoạt với DN thay đổi. (3) Tránh rơi vào trạng thái anonymous/unauthenticated bind. (4) Đó là lỗi hạ tầng, không phải bằng chứng mật khẩu sai. (5) Authorization sau khi authentication thành công.

## Kết luận

**LDAP bind authentication** là cách để máy chủ thư mục trực tiếp xác minh danh tính cho ứng dụng. Trong Spring LDAP, tình huống thông dụng là tìm DN qua `LdapTemplate` rồi xác thực bằng `authenticate(...)`; với DN đã biết, ứng dụng có thể thực hiện user bind trực tiếp. Một triển khai đúng cần bảo vệ mật khẩu bằng TLS, giới hạn phạm vi tìm kiếm và quyền tài khoản dịch vụ, từ chối mật khẩu rỗng, phân biệt lỗi xác thực với sự cố LDAP và thực hiện phân quyền riêng sau khi xác thực.
