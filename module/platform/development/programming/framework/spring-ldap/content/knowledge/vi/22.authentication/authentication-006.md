# Bind DN quản trị với quyền tìm kiếm trong Spring LDAP

Để xác thực người dùng bằng LDAP, ứng dụng thường phải **tìm đúng entry của người dùng** trước khi thử bind bằng mật khẩu họ nhập. Muốn tìm được entry, ứng dụng cần mở kết nối LDAP với một danh tính có quyền **search** trên vùng thư mục tương ứng. Danh tính đó thường được gọi là **bind DN**, **search account**, **service account** hoặc trong một số tài liệu là **admin bind DN**.

Ví dụ, nhân viên đăng nhập bằng `uid=lan` nhưng DN thực tế của họ là `uid=lan,ou=people,dc=example,dc=org`. Ứng dụng Spring LDAP có thể dùng tài khoản kỹ thuật `cn=svc-ldap-reader,ou=system,dc=example,dc=org` để tra cứu DN, sau đó thực hiện **user bind** riêng với DN của Lan và mật khẩu do Lan nhập.

Từ “quản trị” trong cách gọi *bind DN quản trị* **không bắt buộc có nghĩa là tài khoản quản trị toàn bộ thư mục**. Một tài khoản chuyên dụng có **quyền tìm kiếm tối thiểu** là lựa chọn phù hợp hơn cho ứng dụng production. Bài học thuộc chương **Authentication** của **SPRING_LDAP** này trình bày cách phân biệt các danh tính bind, cấu hình `ContextSource` / `LdapTemplate`, cấp quyền search, bảo vệ kết nối và xử lý những trường hợp thường gặp.

## Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích vai trò của **bind DN** và **bind password** khi LDAP client kết nối với máy chủ.
2. Phân biệt **service/admin bind** dùng để search và **user bind** dùng để xác thực người dùng cuối.
3. Hiểu quyền tìm kiếm phụ thuộc vào ACL, search base, scope, filter và schema.
4. Cấu hình Spring Boot/Spring LDAP để tài khoản dịch vụ thực hiện tìm kiếm bằng `LdapTemplate`.
5. Thiết kế luồng *search rồi bind* mà không cấp quyền quản trị không cần thiết hoặc nhầm kết quả search với đăng nhập thành công.
6. Kiểm tra kết nối, quyền, TLS và các lỗi phổ biến bằng công cụ dòng lệnh và bài kiểm thử.

## 1. Bind DN là gì?

Trong LDAP, **Distinguished Name (DN)** xác định một entry theo vị trí của nó trong cây thư mục. Một số DN minh họa:

~~~text
dc=example,dc=org
├── ou=people
│   ├── uid=lan
│   └── uid=minh
└── ou=system
    └── cn=svc-ldap-reader
~~~

Khi biểu diễn đầy đủ:

~~~text
uid=lan,ou=people,dc=example,dc=org
cn=svc-ldap-reader,ou=system,dc=example,dc=org
~~~

**Bind** là thao tác thiết lập danh tính xác thực trên một kết nối LDAP. Với **simple bind**, client gửi tên định danh (thường là DN, hoặc tên đăng nhập thuộc dạng mà server chấp nhận) và mật khẩu. Sau khi server chấp nhận, các thao tác LDAP trên kết nối/ngữ cảnh đó được kiểm soát theo danh tính đã bind.

Ba khái niệm cần tách biệt:

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| **Bind DN** | Danh tính mà LDAP client dùng khi xác thực kết nối | `cn=svc-ldap-reader,ou=system,dc=example,dc=org` |
| **Bind password** | Mật khẩu của danh tính trên; không phải mật khẩu người dùng cuối | Secret của `svc-ldap-reader` |
| **Base DN** | Điểm gốc để tìm kiếm hoặc thao tác trong thư mục; **không phải danh tính đăng nhập** | `dc=example,dc=org` |

Tài khoản có DN chứa `cn=admin` không tự động có quyền quản trị; **quyền thực tế do máy chủ và cấu hình ACL quyết định**. Ngược lại, tài khoản có tên trông bình thường vẫn có thể sở hữu quyền quá rộng nếu ACL cấp sai.

## 2. Vì sao ứng dụng cần bind DN có quyền tìm kiếm?

Ứng dụng thường chỉ nhận `username` hoặc email khi người dùng đăng nhập, trong khi các thao tác LDAP cần DN thực của entry.

Ví dụ:

~~~text
Username do người dùng nhập: lan
Filter tìm kiếm:             (&(objectClass=inetOrgPerson)(uid=lan))
Search base:                 ou=people,dc=example,dc=org
DN tìm được:                 uid=lan,ou=people,dc=example,dc=org
~~~

Để thực hiện search, LDAP server cần biết **ai đang yêu cầu** và người đó được phép nhìn thấy gì. Trong nhiều hệ thống doanh nghiệp, thao tác search ẩn danh bị tắt hoặc giới hạn; backend cần bind bằng một tài khoản kỹ thuật được phép tra cứu các entry và thuộc tính cần thiết.

Việc **tìm thấy DN** mới giải quyết câu hỏi “đây là entry nào?”. Nó **không trả lời** câu hỏi “người đang đăng nhập có biết mật khẩu đúng không?”. Câu hỏi thứ hai chỉ được giải quyết khi ứng dụng kiểm tra thông tin xác thực, thông thường bằng **user bind**.

### 2.1. Các loại danh tính thường gặp

| Danh tính bind | Dùng để làm gì? | Quyền được đề xuất |
|---|---|---|
| **Anonymous bind** | Search không cần tài khoản, nếu server cho phép | Chỉ phù hợp với dữ liệu được phép công khai; thường không đủ cho tra cứu tài khoản doanh nghiệp |
| **Search/service bind** | Tìm DN và các thuộc tính cần cho luồng đăng nhập | Đọc/tìm kiếm tối thiểu trên các OU và thuộc tính được phép |
| **Administrator bind** | Quản trị schema, entry, ACL hoặc thao tác đặc quyền | Chỉ dành cho tác vụ vận hành được ủy quyền; tránh đưa thông tin này vào ứng dụng đăng nhập |
| **User bind** | Xác thực chính người dùng cuối bằng mật khẩu của họ | Quyền theo danh tính người dùng và chính sách LDAP |

Trong môi trường thử nghiệm, có thể bắt gặp cấu hình dùng `cn=admin,dc=example,dc=org` để tiện tra cứu. Tuy nhiên, mô hình production nên tạo **search account chuyên dụng**, ví dụ `cn=svc-ldap-reader,ou=system,dc=example,dc=org`, với quyền hạn có giới hạn.

### 2.2. Quyền search không đồng nghĩa quyền quản trị

Một tài khoản có thể:

- Được quyền tìm các entry dưới `ou=people` và đọc một số thuộc tính như `uid`, `cn`, `mail`.
- Bị từ chối đọc thuộc tính mật khẩu và các thông tin nhạy cảm khác.
- Không có quyền tạo, sửa, xóa hoặc đổi tên entry.
- Không có quyền sửa ACL, schema hoặc cấu hình LDAP server.
- Không có quyền tìm kiếm ngoài các OU được phê duyệt.

Đây là mô hình **least privilege**: backend chỉ được làm những việc thực sự cần để phục vụ luồng xác thực.

## 3. Luồng search bằng service bind và xác thực bằng user bind

Giả sử backend cần hỗ trợ nhân viên nhập `uid` và mật khẩu.

~~~mermaid
sequenceDiagram
    actor U as Người dùng
    participant App as Backend Spring LDAP
    participant LDAP as LDAP server
    U->>App: Gửi uid=lan và mật khẩu qua HTTPS
    App->>LDAP: Kết nối TLS, bind bằng service DN
    LDAP-->>App: Service bind thành công
    App->>LDAP: Search uid=lan trong ou=people
    LDAP-->>App: DN người dùng phù hợp
    App->>LDAP: User bind riêng bằng DN Lan và mật khẩu Lan
    alt User bind hợp lệ
        LDAP-->>App: Bind thành công
        App->>App: Kiểm tra chính sách và phân quyền
        App-->>U: Đăng nhập theo cơ chế phiên ứng dụng
    else User bind bị từ chối
        LDAP-->>App: Xác thực thất bại
        App-->>U: Thông báo đăng nhập thất bại
    end
~~~

Phân tích:

1. **Backend → LDAP:** thiết lập kết nối tin cậy với server bằng LDAPS hoặc StartTLS.
2. **Service bind:** xác thực bằng tài khoản kỹ thuật có quyền tìm kiếm.
3. **LDAP search:** tìm entry người dùng dựa trên filter có escape an toàn. Bộ lọc được xác định ở phía backend; dữ liệu người dùng chỉ được đưa vào vị trí **giá trị**.
4. **Kiểm tra danh tính:** phải bảo đảm username ánh xạ đến đúng một người dùng theo chính sách thư mục, tránh trường hợp trùng `uid` giữa nhiều OU.
5. **User bind:** thử xác thực bằng **mật khẩu của người dùng**, không phải mật khẩu tài khoản dịch vụ.
6. **Authorization và session:** sau khi bind thành công, ứng dụng còn phải áp dụng điều kiện tài khoản, nhóm/role, session hoặc token theo chính sách của mình.

**Hai lần bind có mục đích khác nhau.** Service bind thành công chỉ chứng minh backend có quyền tra cứu; user bind thành công mới là bằng chứng LDAP đã chấp nhận credential của người đăng nhập. Kết quả search cũng không tự tạo HTTP session hoặc JWT.

### 3.1. Bảng các trường hợp

| Kết quả service bind | Kết quả search | Kết quả user bind | Kết luận |
|---|---|---|---|
| Thành công | Có đúng một entry | Thành công | Người dùng được LDAP xác thực; tiếp tục kiểm tra quyền ứng dụng |
| Thành công | Có đúng một entry | Thất bại | Không xác thực người dùng |
| Thành công | Không có entry | Chưa thực hiện | Không xác định được danh tính để xác thực |
| Thành công | Nhiều entry cùng tên | Không được chọn tùy ý | Danh tính mơ hồ, cần từ chối và sửa quy tắc định danh |
| Thất bại | Không thể search | Chưa thực hiện | Lỗi kết nối/cấu hình/credential của service account |
| Thành công | Lỗi quyền search | Chưa thực hiện | Cần kiểm tra ACL và phạm vi search, không mặc định là mật khẩu người dùng sai |

## 4. Cấu hình bind DN trong Spring Boot và Spring LDAP

Trong Spring LDAP, **`ContextSource`** chịu trách nhiệm tạo ngữ cảnh kết nối đến LDAP, còn **`LdapTemplate`** cung cấp các phương thức thao tác với thư mục. Khi cấu hình Spring Boot bằng `spring.ldap`, ứng dụng có thể khai báo thông tin tài khoản kỹ thuật để sử dụng cho các thao tác search.

### 4.1. Cấu hình `application.yml`

~~~yaml
spring:
  ldap:
    urls: ${LDAP_URL:ldaps://ldap.example.org:636}
    base: dc=example,dc=org
    username: ${LDAP_BIND_DN}
    password: ${LDAP_BIND_PASSWORD}
~~~

Ví dụ giá trị của các biến môi trường:

~~~text
LDAP_URL=ldaps://ldap.example.org:636
LDAP_BIND_DN=cn=svc-ldap-reader,ou=system,dc=example,dc=org
LDAP_BIND_PASSWORD=<secret được cấp và lưu an toàn>
~~~

Ý nghĩa:

| Thuộc tính | Chức năng | Lưu ý |
|---|---|---|
| `spring.ldap.urls` | URL của một hoặc nhiều LDAP endpoint | Trong ví dụ dùng LDAPS; cần xác thực chứng chỉ máy chủ |
| `spring.ldap.base` | Base DN chung của ngữ cảnh LDAP | `dc=example,dc=org` không phải DN của tài khoản dịch vụ |
| `spring.ldap.username` | Danh tính dùng cho các kết nối/hoạt động mặc định của `ContextSource` | Thường là DN đầy đủ của tài khoản dịch vụ hoặc tên bind hợp lệ theo server |
| `spring.ldap.password` | Credential tương ứng với tài khoản trên | Lưu bằng biến môi trường/secret manager, không commit vào repository |

Ví dụ đang giả định ứng dụng đã cài thư viện Spring LDAP và cấu hình tự động thích hợp để inject `LdapTemplate`. Tên các property áp dụng cho Spring Boot có hỗ trợ Spring LDAP; nếu tự tạo `ContextSource`, phải cấu hình tương đương qua API của phiên bản đang sử dụng.

Không nhầm `spring.ldap.username` với tên người dùng cuối gửi từ biểu mẫu. Cấu hình cố định này là **danh tính của backend để tìm kiếm**, còn credential người dùng được truyền vào bước xác thực riêng.

> **Lưu ý bảo mật:** Không đặt mật khẩu thật vào tài liệu, ví dụ chia sẻ, repository hoặc log. Nếu thay đổi secret của service account, cần cập nhật backend/secret manager đồng bộ theo quy trình rotation để tránh lỗi bind toàn hệ thống.

### 4.2. Ví dụ Spring LDAP thực hiện search bằng tài khoản kỹ thuật

Đoạn code dùng `LdapTemplate` và `LdapQueryBuilder` để tìm tài khoản theo `uid`. Các entry và schema bên dưới chỉ là dữ liệu minh họa.

~~~java
import java.util.List;

import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;
import org.springframework.ldap.query.SearchScope;
import org.springframework.stereotype.Service;

@Service
public class LdapUserLookupService {

    private final LdapTemplate ldapTemplate;

    public LdapUserLookupService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<String> findUsernames(String username) {
        if (username == null || username.isBlank()
                || username.length() > 128) {
            return List.of();
        }

        LdapQuery query = LdapQueryBuilder.query()
                .base("ou=people")
                .searchScope(SearchScope.SUBTREE)
                .attributes("uid")
                .where("objectClass").is("inetOrgPerson")
                .and("uid").is(username);

        return ldapTemplate.search(
                query,
                (AttributesMapper<String>) attrs ->
                        attrs.get("uid").get().toString()
        );
    }
}
~~~

**Giải thích:**

1. Vì `spring.ldap.base=dc=example,dc=org`, `base("ou=people")` chỉ tìm dưới `ou=people,dc=example,dc=org`.
2. `searchScope(SearchScope.SUBTREE)` bao gồm entry base và các OU con. Nếu người dùng chỉ nằm trực tiếp dưới một OU, cân nhắc scope hẹp hơn.
3. `attributes("uid")` giảm lượng dữ liệu trả về. Những thuộc tính dùng trong filter vẫn phải có quyền tìm kiếm theo ACL của server.
4. `where(...).is(username)` giữ username ở vai trò **giá trị literal được escape theo cú pháp LDAP filter**. Không tự nối `username` vào chuỗi `"(uid=" + username + ")"`.
5. Trong cấu hình minh họa, `ldapTemplate.search(...)` sẽ sử dụng các ngữ cảnh do `ContextSource` tạo ra với credential tài khoản dịch vụ. Quyền search do LDAP server xác định, Spring LDAP không tự mở rộng ACL.
6. `List<String>` chỉ là danh sách `uid` tìm được, **không phải trạng thái đã đăng nhập**. Trong luồng xác thực thực tế cần chính sách định danh duy nhất và bước user bind tiếp theo.

Các entry không có `uid`, có schema khác hoặc tài khoản đặt ở OU khác sẽ cần query phù hợp. Không nên mở rộng phạm vi tìm kiếm sang toàn bộ directory chỉ để “cho tìm thấy”.

### 4.3. Tiếp tục bằng `LdapTemplate.authenticate(...)`

Sau khi thiết kế đúng search base, schema và quyền tài khoản dịch vụ, có thể dùng API xác thực dựa trên search + bind:

~~~java
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;
import org.springframework.stereotype.Service;

@Service
public class LdapLoginService {
    private final LdapTemplate ldapTemplate;

    public LdapLoginService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public boolean authenticate(String username, String password) {
        if (username == null || username.isBlank()
                || username.length() > 128
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

Ở phương thức `authenticate(...)`, `LdapTemplate` dùng query để xác định danh tính ứng viên rồi thực hiện kiểm tra credential qua user bind. Ứng dụng **không lấy mật khẩu người dùng cuối để thay vào cấu hình `spring.ldap.password`**, cũng không dùng service password để kết luận user đã đăng nhập.

Đây là ví dụ dịch vụ tối giản, chưa tích hợp Spring Security, rate limiting, quản lý session, chính sách tài khoản hay cơ chế kiểm soát các entry trùng định danh. Với ứng dụng production, các điều kiện đó phải được thực thi trong thiết kế xác thực/ủy quyền và ở tầng dữ liệu directory.

## 5. Thiết kế ACL để tài khoản bind chỉ có quyền tìm kiếm

**ACL (Access Control List)** hoặc các quy tắc truy cập tương đương quyết định service account có thể nhìn thấy entry/attribute nào. Cú pháp ACL của **OpenLDAP**, **Active Directory** và các máy chủ LDAP khác không giống nhau; vì vậy không thể lấy một đoạn quy tắc ACL duy nhất áp dụng nguyên xi cho mọi môi trường.

Ví dụ tổ chức muốn backend tìm người dùng theo `uid` nhưng tuyệt đối không sửa dữ liệu thư mục:

| Tài nguyên / thao tác | Quyền mong muốn cho `svc-ldap-reader` | Lý do |
|---|---|---|
| Search dưới `ou=people,dc=example,dc=org` | Cho phép, theo đúng vùng cần đăng nhập | Xác định entry người dùng |
| Search/evaluate `uid`, `objectClass` | Cho phép theo ACL của máy chủ | Cần để filter khớp |
| Đọc `uid` hoặc một số thông tin cần thiết | Cho phép có giới hạn | Lấy định danh để xử lý |
| Đọc `userPassword` hoặc hash password | Không | Không cần cho luồng search + bind |
| Đọc thông tin nhạy cảm khác | Không, trừ khi được phê duyệt rõ ràng | Giảm bề mặt lộ dữ liệu |
| Add/modify/delete/rename entry | Không | Xác thực không phải thao tác quản lý tài khoản |
| Sửa ACL/schema/cấu hình LDAP | Không | Tránh leo thang đặc quyền |
| Search các OU ngoài phạm vi | Không hoặc chỉ theo yêu cầu rõ ràng | Ngăn truy cập dữ liệu không liên quan |

Một số máy chủ phân biệt quyền **discover/traverse**, **search**, **compare**, **read** và quyền xem DN/attribute. Vì thế, lỗi search có thể xảy ra ngay cả khi tài khoản được phép bind thành công. Cần kiểm tra cụ thể **ACL của entry, attribute, nhánh cha và chính sách ẩn danh** trong hệ thống đang sử dụng.

### 5.1. Một tài khoản bind được nhưng không tìm được user

Giả sử chạy bind bằng `svc-ldap-reader` và server trả thành công. Sau đó search `(&(objectClass=inetOrgPerson)(uid=lan))` không có kết quả. Các nguyên nhân có thể là:

- Entry của Lan không nằm dưới base DN hoặc scope đã chọn.
- Server từ chối quyền xem entry/attribute cần cho filter.
- Filter dùng attribute không tồn tại hoặc không đúng schema.
- `uid` không phải định danh đăng nhập được sử dụng trên server này.
- Dữ liệu thực sự không có entry khớp.

Vì một số server cố tình **ẩn entry không có quyền truy cập**, “không có kết quả” chưa đủ để phân biệt chắc chắn “entry không tồn tại” với “không được phép nhìn thấy”. Cần chẩn đoán bằng cấu hình ACL và tài khoản kiểm thử được ủy quyền, không tự cấp quyền admin cho backend.

### 5.2. Có nên dùng bind DN quản trị toàn quyền?

Tài khoản quản trị có thể hữu ích khi dựng môi trường thử nghiệm hoặc thực hiện công việc bảo trì được ủy quyền, nhưng dùng nó cho luồng đăng nhập thường ngày có rủi ro:

1. Nếu credential bị lộ, kẻ tấn công có thể thực hiện các thao tác vượt xa nhu cầu tìm người dùng.
2. Một lỗi lập trình có thể dẫn đến sửa/xóa entry hoặc truy cập thuộc tính nhạy cảm.
3. Việc chia sẻ credential admin giữa nhiều hệ thống làm khó audit và rotation.
4. Khó chứng minh ứng dụng tuân thủ nguyên tắc quyền tối thiểu.

**Cách làm nên chọn:** tạo tài khoản kỹ thuật riêng cho từng ứng dụng hoặc nhóm ứng dụng có phạm vi truy cập giống nhau; chỉ cấp quyền search/read tối thiểu, lưu secret trong kho bí mật và có lịch thay đổi credential.

## 6. Kiểm tra bind DN và search bằng công cụ dòng lệnh

Trước khi chẩn đoán mã Spring, có thể kiểm tra kết nối LDAP và ACL bằng công cụ OpenLDAP trên máy có quyền truy cập server. Các lệnh dưới đây dành cho **môi trường thử nghiệm được phép**.

### 6.1. Xác minh service bind

~~~bash
ldapwhoami -x \
  -H ldaps://ldap.example.org:636 \
  -D "cn=svc-ldap-reader,ou=system,dc=example,dc=org" \
  -W
~~~

Trong đó:

- `-x` sử dụng simple authentication.
- `-H` chỉ URL LDAP, ở đây là LDAPS.
- `-D` là bind DN của tài khoản dịch vụ.
- `-W` yêu cầu nhập mật khẩu qua prompt, tránh để password xuất hiện trong lịch sử shell.

Nếu thành công, `ldapwhoami` thường trả về danh tính đã xác thực, ví dụ:

~~~text
dn:cn=svc-ldap-reader,ou=system,dc=example,dc=org
~~~

Kết quả chỉ xác minh **service bind**, chưa xác nhận tài khoản có quyền search.

### 6.2. Kiểm tra search dưới vùng cho phép

~~~bash
ldapsearch -x \
  -H ldaps://ldap.example.org:636 \
  -D "cn=svc-ldap-reader,ou=system,dc=example,dc=org" \
  -W \
  -b "ou=people,dc=example,dc=org" \
  -s sub \
  "(&(objectClass=inetOrgPerson)(uid=lan))" \
  uid cn
~~~

Kết quả kỳ vọng trong ví dụ:

~~~ldif
dn: uid=lan,ou=people,dc=example,dc=org
uid: lan
cn: Lan Tran
~~~

Nếu `ldapwhoami` thành công nhưng `ldapsearch` không thể trả về entry, cần xem lại base DN, scope, filter và ACL. Khi đối chiếu với ứng dụng Spring, hãy dùng cùng service DN, base DN, filter và môi trường kết nối; khác biệt về cấu hình có thể khiến kết quả không giống nhau.

Các lệnh shell này minh họa filter cố định cho tài khoản thử nghiệm. **Không sao chép cách nối dữ liệu do người dùng nhập trực tiếp vào chuỗi filter trong code ứng dụng.** Với dữ liệu request, dùng query builder hoặc filter builder có escape.

### 6.3. Kiểm tra giới hạn quyền

Người vận hành nên xác nhận service account:

- Tìm được đúng những entry được phê duyệt trong `ou=people`.
- Không đọc được thuộc tính mật khẩu hoặc các attribute đã được khóa.
- Không thực hiện được `add`, `modify` hay `delete` trên entry người dùng.
- Không truy vấn được khu vực khác nếu không có lý do nghiệp vụ.

Những phép kiểm tra quyền ghi/chỉnh sửa phải chạy trong **directory thử nghiệm** với dữ liệu có thể khôi phục, không tự tạo thử nghiệm phá hoại trên production.

## 7. Kết nối an toàn, secret và pooling

Bind password của service account là bí mật có quyền truy cập tập trung. Nếu bị lộ, kẻ tấn công có thể khai thác quyền search và các quyền khác mà ACL đã cấp. Vì vậy, các biện pháp sau cần thực hiện đồng thời:

### 7.1. Bảo vệ dữ liệu trên đường truyền

| Đường truyền | Phương thức phù hợp | Mục tiêu |
|---|---|---|
| Trình duyệt → Backend Spring | HTTPS | Bảo vệ username/password người dùng |
| Backend Spring → LDAP | LDAPS hoặc LDAP + StartTLS | Bảo vệ service password, user password và dữ liệu thư mục |

LDAPS thường dùng `ldaps://...:636`; StartTLS thường nâng cấp kết nối từ `ldap://...:389` trước khi gửi credential. Không gửi simple bind password qua kết nối không mã hóa. Ứng dụng cần **xác minh chuỗi chứng chỉ và hostname** bằng truststore tin cậy; không tắt kiểm tra chứng chỉ để khắc phục lỗi cấu hình.

Khi dùng StartTLS, cấu hình `ContextSource` phải thực hiện nâng cấp bảo mật trước thao tác bind. Chi tiết API tùy phiên bản Spring LDAP/JNDI. Nếu có pooling, cần kiểm tra tương thích với StartTLS và cách quản lý danh tính của kết nối.

### 7.2. Lưu và xoay credential

- Đặt mật khẩu service account trong secret manager hoặc biến môi trường được quản lý.
- Không ghi mật khẩu vào source code, log, trace, thông báo lỗi hoặc tham số URL.
- Tách tài khoản và quyền giữa development, staging và production.
- Xây quy trình rotation để ứng dụng và server dùng cùng credential trong quá trình thay đổi.
- Theo dõi lịch sử service bind bất thường, lần đăng nhập thất bại và truy vấn vượt phạm vi.

### 7.3. Không trộn danh tính giữa các kết nối

Trong luồng search + bind, các connection/context dùng cho service account và người dùng cuối phải được quản lý đúng vòng đời. Không để một context đã bind bằng user được **dùng lại như context của service account**, hoặc ngược lại. Việc bật JNDI/Spring LDAP pooling đòi hỏi cấu hình theo danh tính và cách xử lý context; không giả định mọi pool an toàn cho mọi kiểu bind.

## 8. Xử lý lỗi và chẩn đoán

Một điểm rất quan trọng là phân biệt lỗi tài khoản dịch vụ với lỗi thông tin xác thực của người dùng.

| Biểu hiện | Nguyên nhân khả dĩ | Hướng xử lý |
|---|---|---|
| `invalidCredentials (49)` khi service bind | Sai service DN/password, tài khoản hết hạn/khóa hoặc quy tắc server | Kiểm tra secret, trạng thái tài khoản và cấu hình directory |
| Service bind thành công, search trả 0 entry | Sai base/scope/filter, ACL ẩn entry hoặc entry không tồn tại | Kiểm tra vùng search/schema/ACL bằng dữ liệu thử nghiệm |
| `insufficientAccessRights (50)` khi search | Thiếu quyền trên entry/attribute/vùng search | Điều chỉnh ACL tối thiểu theo yêu cầu nghiệp vụ |
| `noSuchObject (32)` | Base DN hoặc DN được truy vấn không tồn tại | Kiểm tra cấu trúc cây và base DN |
| Search ra nhiều entry | `uid` không duy nhất hoặc scope quá rộng | Áp dụng chính sách uniqueness, tránh chọn entry đầu tiên |
| Timeout hoặc LDAP không phản hồi | Mạng, DNS, server quá tải hoặc cấu hình timeout | Giám sát hạ tầng và điều chỉnh giới hạn truy vấn |
| TLS handshake thất bại | Chứng chỉ, truststore, hostname hoặc giao thức sai | Khắc phục TLS; không tự hạ cấp sang plaintext |
| Service search thành công nhưng user bind thất bại | Sai mật khẩu người dùng hoặc chính sách LDAP từ chối | Trả thông báo đăng nhập chung; ghi log kỹ thuật phù hợp |
| Mật khẩu người dùng rỗng | Một số triển khai cho phép unauthenticated/anonymous simple bind | Từ chối password rỗng **trước khi gửi bind** |

Mã lỗi LDAP phổ biến như `32`, `49`, `50` giúp định hướng chẩn đoán, nhưng không bảo đảm đủ để xác định duy nhất nguyên nhân trên mọi server. Một số server có diagnostic message bổ sung; log nội bộ có thể giữ mã/loại lỗi vừa đủ, nhưng không được ghi mật khẩu hoặc dữ liệu nhạy cảm.

Để tránh **username enumeration**, API đăng nhập nên dùng phản hồi trung tính khi username không tồn tại hoặc mật khẩu sai. Tuy nhiên, cần giám sát tách riêng lỗi hạ tầng của service bind/search với lỗi xác thực người dùng, tránh che khuất sự cố LDAP chung bằng một kết quả `false` duy nhất.

## 9. Tình huống thực hành

Giả sử LDAP thử nghiệm có:

~~~text
Service DN:
  cn=svc-ldap-reader,ou=system,dc=example,dc=org

Allowed search base:
  ou=people,dc=example,dc=org

User DN:
  uid=lan,ou=people,dc=example,dc=org
~~~

Tài khoản `svc-ldap-reader` có quyền search `uid`, `cn` và `objectClass` dưới `ou=people`, không có quyền đọc mật khẩu hoặc sửa entry.

**Bước 1 — Kết nối:** cấu hình LDAPS, truststore, service DN và secret trong Spring Boot.

**Bước 2 — Service bind:** chạy `ldapwhoami` để xác nhận tài khoản kỹ thuật có thể xác thực với LDAP server.

**Bước 3 — Search:** chạy `ldapsearch` với cùng DN, filter `(uid=lan)` và search base như ứng dụng; xác minh trả về đúng entry.

**Bước 4 — Spring LDAP:** gọi `LdapUserLookupService.findUsernames("lan")`; xác minh search sử dụng `ContextSource` của service account. Thử username chứa dấu `*` để chắc chắn không chuyển thành wildcard.

**Bước 5 — User bind:** gọi `LdapLoginService.authenticate(...)` với mật khẩu đúng và sai. Kiểm tra kết quả trả về và xác nhận không thay đổi cấu hình credential của service account.

**Bước 6 — Quyền tối thiểu:** xác minh service account không đọc/sửa được entry ngoài quyền, thử timeout và lỗi TLS trong môi trường kiểm thử có kiểm soát.

### 9.1. Ma trận kiểm thử

| Trường hợp | Kết quả mong đợi |
|---|---|
| Service DN và password hợp lệ | Bind tài khoản kỹ thuật thành công |
| Service password sai | Service bind thất bại; không thực hiện search |
| Service bind đúng nhưng thiếu quyền search `uid` | Search không đáp ứng nhu cầu; có lỗi quyền hoặc không nhìn thấy entry theo cơ chế server |
| Base DN không bao gồm user | Không tìm thấy entry, dù user thực sự tồn tại ở vùng khác |
| Filter có `uid=lan` và quyền phù hợp | Tìm đúng entry theo matching rule/schema |
| Username người dùng là `*` | Filter builder xem `*` là dữ liệu literal, không tự mở rộng thành `(uid=*)` |
| Nhiều entry cùng username trong vùng search | Phát hiện định danh mơ hồ; không tự chọn một DN |
| User password đúng | User bind được LDAP chấp nhận theo chính sách server |
| User password sai hoặc rỗng | Bị từ chối; password rỗng bị ứng dụng chặn trước bind |
| Service bind thành công nhưng user bind sai | **Không đăng nhập thành công** |
| User bind thành công nhưng user không đủ role | Authorization từ chối chức năng được bảo vệ |
| Service account thử đọc `userPassword` hoặc sửa entry | Bị ACL từ chối theo mô hình quyền tối thiểu |
| LDAP certificate không hợp lệ | Kết nối TLS thất bại an toàn |

### 9.2. Câu hỏi tự kiểm tra

1. Vì sao service bind thành công chưa chứng minh người dùng cuối đăng nhập hợp lệ?
2. `spring.ldap.base` khác `spring.ldap.username` ở chỗ nào?
3. Một tài khoản có DN là `cn=admin,...` có mặc nhiên được mọi quyền LDAP không? Điều gì quyết định quyền?
4. Vì sao production nên dùng search account có quyền tối thiểu thay vì tài khoản quản trị toàn thư mục?
5. Nếu service bind thành công nhưng search không trả entry, cần kiểm tra các thành phần nào?
6. Khi backend thực hiện user bind, có được thay `spring.ldap.password` bằng mật khẩu người dùng cuối không?
7. Vì sao mật khẩu của service account và của người dùng cuối đều phải được bảo vệ bằng TLS trên đoạn backend → LDAP?

**Gợi ý:** (1) Service bind chỉ xác thực backend; user bind mới kiểm tra credential người dùng. (2) `base` là gốc search, `username` là danh tính bind. (3) Không; ACL/chính sách server quyết định. (4) Giảm tác hại nếu secret hoặc mã ứng dụng bị khai thác. (5) Base DN, scope, filter, schema, ACL và dữ liệu thực. (6) Không; hai danh tính có vòng đời riêng. (7) Cả hai đều là thông tin xác thực cần tránh truyền plaintext hoặc bị nghe lén.

## Kết luận

**Bind DN có quyền tìm kiếm** là danh tính của backend Spring LDAP dùng để tìm thông tin tài khoản trong thư mục. Tài khoản này có thể mang tên “admin bind” trong tài liệu, nhưng ứng dụng thực tế nên sử dụng **service account chuyên dụng, chỉ có quyền search/read cần thiết**. Với `ContextSource` và `LdapTemplate`, ứng dụng thực hiện service bind để tìm đúng DN rồi user bind để xác thực mật khẩu. Thiết kế an toàn phải giới hạn ACL, base DN, scope và thuộc tính, bảo vệ credential bằng TLS, quản lý kết nối đúng danh tính và phân biệt lỗi service search với thất bại đăng nhập của người dùng.
