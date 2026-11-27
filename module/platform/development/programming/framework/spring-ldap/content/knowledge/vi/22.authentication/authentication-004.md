# Password compare và khác biệt với bind trong Spring LDAP

Khi ứng dụng xác thực người dùng qua LDAP, hai khái niệm dễ bị nhầm lẫn là **password compare** (so sánh mật khẩu) và **LDAP bind** (thiết lập danh tính xác thực cho phiên kết nối). Cả hai có thể liên quan tới mật khẩu, nhưng **không có cùng ngữ nghĩa**, không luôn áp dụng cùng chính sách của máy chủ và không tạo ra cùng trạng thái xác thực.

Giả sử nhân viên đăng nhập bằng `uid=lan`. Ứng dụng phải quyết định có chấp nhận mật khẩu vừa nhập hay không. Cách thông dụng là **user bind**: gửi DN của Lan cùng mật khẩu để máy chủ LDAP trực tiếp xác thực. Một phương án khác trong một số hệ thống là dùng cơ chế **LDAP Compare** để kiểm tra giá trị một thuộc tính, hoặc đọc giá trị băm của mật khẩu và so khớp tại ứng dụng. Các phương án password compare này chỉ khả dụng khi chính sách, schema và máy chủ hỗ trợ; không nên mặc nhiên xem kết quả so sánh là một lần đăng nhập LDAP thành công.

Bài học này thuộc chương **Authentication** của **Spring LDAP** và tập trung vào cách chọn cơ chế đúng, gọi API phù hợp, nhận biết giới hạn của so sánh thuộc tính, bảo vệ mật khẩu và kiểm thử ứng dụng một cách an toàn.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt LDAP `Compare`, so sánh mật khẩu tại ứng dụng và `Bind`.
- Giải thích vì sao `compareTrue` **không tạo ra phiên LDAP đã bind với danh tính người dùng**.
- Mô tả ảnh hưởng của schema, matching rule, ACL và cách lưu mật khẩu tới khả năng so sánh `userPassword`.
- Sử dụng `LdapTemplate.compare(...)` cho bài toán so sánh thuộc tính và `LdapTemplate.authenticate(...)` cho xác thực bằng bind.
- Chọn đúng phương án trong Spring LDAP và hiểu vị trí của `BindAuthenticator` / `PasswordComparisonAuthenticator` trong Spring Security LDAP.
- Phân biệt kết quả so sánh sai, lỗi quyền truy cập, lỗi TLS và lỗi hạ tầng khi kiểm thử.

## 1. Ba thao tác dễ bị nhầm lẫn

### 1.1. LDAP Bind: chứng minh danh tính

**Bind** là thao tác giao thức LDAP dùng để xác thực và thiết lập danh tính cho phiên làm việc trên kết nối. Với **simple bind**, client trình bày thông tin định danh (thường là DN) và mật khẩu; máy chủ quyết định có chấp nhận hay không.

Ví dụ DN:

~~~text
uid=lan,ou=people,dc=example,dc=org
~~~

Khi user bind thành công, các thao tác LDAP tiếp theo trên chính ngữ cảnh đã xác thực sẽ chịu sự kiểm soát truy cập theo danh tính đó. Khi bind thất bại, ứng dụng không thể coi người dùng đã được xác thực. Máy chủ có thể áp dụng chính sách mật khẩu, trạng thái tài khoản hoặc hạn chế đăng nhập; các quy tắc cụ thể tùy sản phẩm và cấu hình.

**Bind không tự tạo HTTP session hoặc JWT cho ứng dụng web.** Spring Security hoặc tầng bảo mật của ứng dụng vẫn phải thực hiện các bước cấp phiên và phân quyền cần thiết.

### 1.2. LDAP Compare: hỏi máy chủ về một giá trị thuộc tính

LDAP có thao tác **Compare** được mô tả trong RFC 4511. Client gửi tới máy chủ:

1. **DN của entry** cần kiểm tra.
2. **Tên attribute** cần so sánh.
3. **Assertion value**: giá trị muốn kiểm tra.

Máy chủ so sánh theo quy tắc của attribute và trả kết quả chuyên biệt như `compareTrue` hoặc `compareFalse`. Nếu thiếu quyền, không tìm thấy entry hoặc không thể thực hiện phép so sánh, máy chủ có thể trả lỗi LDAP tương ứng.

Ví dụ: tài khoản dịch vụ muốn kiểm tra `employeeType` của Lan có bằng `internal` hay không:

~~~text
CompareRequest
  entry:     uid=lan,ou=people,dc=example,dc=org
  attribute: employeeType
  value:     internal
~~~

Đây là một phép kiểm tra **thuộc tính của entry**, không phải đăng nhập bằng tài khoản Lan. Nếu tài khoản dịch vụ đang bind với DN `cn=svc-reader,...`, thì sau `compareTrue` phiên đó **vẫn là phiên của tài khoản dịch vụ**.

### 1.3. So sánh mật khẩu tại ứng dụng

Một kiểu “password compare” khác là:

1. Ứng dụng tìm entry bằng tài khoản có quyền đọc.
2. Đọc thuộc tính chứa giá trị mật khẩu đã được lưu, thường là một chuỗi băm.
3. Dùng thuật toán xác minh phù hợp để kiểm tra mật khẩu do người dùng cung cấp.

Ví dụ dữ liệu có thể lưu dưới dạng mã hóa một chiều có salt; để xác minh, ứng dụng phải dùng **đúng** thuật toán, định dạng, tham số và chính sách lưu trữ. So sánh hai chuỗi plaintext hoặc băm một cách tùy tiện không tương đương với xác thực LDAP. Nhiều dịch vụ thư mục **không cho phép đọc** thuộc tính mật khẩu; Active Directory cũng không cung cấp `unicodePwd` như một thuộc tính đọc bình thường để xác thực ở ứng dụng.

Phương án đọc và so khớp tại ứng dụng làm tăng trách nhiệm bảo vệ bí mật, quyền truy cập thuộc tính và tương thích với chính sách mật khẩu của thư mục. Không nên chọn phương án này chỉ vì có thể gọi một hàm so sánh chuỗi trong Java.

## 2. Bảng so sánh Bind, LDAP Compare và local password check

| Tiêu chí | User bind | LDAP Compare | So khớp tại ứng dụng |
|---|---|---|---|
| Ý nghĩa chính | Xác thực danh tính trên kết nối LDAP | Kiểm tra giá trị một attribute của entry | Kiểm tra dữ liệu mật khẩu mà ứng dụng đọc được |
| Đầu vào điển hình | DN người dùng và mật khẩu | DN, attribute, assertion value | Giá trị băm đã lưu, mật khẩu được nhập |
| Nơi xử lý phép kiểm tra | Máy chủ LDAP | Máy chủ LDAP | Ứng dụng |
| Danh tính phiên LDAP sau thao tác | Có thể trở thành danh tính người dùng nếu bind thành công | Giữ nguyên danh tính của kết nối gửi Compare | Giữ nguyên danh tính của kết nối dùng để search |
| Cần đọc giá trị mật khẩu từ LDAP? | Không | Không nhất thiết; server nhận assertion value | Có, và cần quyền đọc |
| Phụ thuộc ACL đọc/so sánh mật khẩu? | Theo quyền và chính sách cho bind | Có thể cần quyền `compare` và cấu hình attribute | Cần quyền đọc attribute và cơ chế mã băm tương thích |
| Tương thích mật khẩu băm? | Thường do máy chủ xử lý đúng cách lưu của nó | Không bảo đảm; tùy cách server triển khai compare trên attribute mật khẩu | Chỉ khi ứng dụng hiểu định dạng và thuật toán hash |
| Có thể tự xem là “user đã bind”? | Có, nếu bind thành công dưới danh tính phù hợp | Không | Không |
| Sử dụng phổ biến | Xác thực đăng nhập | Kiểm tra thuộc tính phù hợp ACL/schema | Một số hệ thống legacy hoặc cơ chế được thiết kế riêng |

**Điểm quan trọng nhất:** `compareTrue` không có nghĩa LDAP đã xác thực phiên làm việc với danh tính của người dùng; nó chỉ nói máy chủ chấp nhận phép so sánh thuộc tính **theo danh tính đã có trên kết nối**.

## 3. Password compare trên LDAP hoạt động ra sao?

### 3.1. Compare thông thường là so sánh theo matching rule

LDAP lưu attribute theo schema và có các **matching rule** quy định cách đối chiếu. Chẳng hạn, so sánh thuộc tính tên có thể chịu quy tắc phân biệt hoặc không phân biệt chữ hoa; so sánh thuộc tính nhị phân có thể đòi hỏi khớp byte.

Trong ví dụ:

~~~text
dn: uid=lan,ou=people,dc=example,dc=org
objectClass: inetOrgPerson
uid: lan
cn: Lan Tran
sn: Tran
employeeType: internal
~~~

Yêu cầu `Compare(employeeType, "internal")` có thể trả `compareTrue` nếu quyền truy cập và schema cho phép. Đây là cách dùng Compare phù hợp để giải thích giao thức vì không liên quan tới bí mật.

### 3.2. Compare với `userPassword` không mặc nhiên giống Bind

Một số hệ thống lưu giá trị `userPassword` theo cách không phải plaintext, ví dụ chuỗi băm kèm định danh thuật toán như `{SSHA}...`. Hãy lưu ý:

- LDAP Compare về nguyên tắc yêu cầu **so khớp giá trị attribute**. Nếu server áp dụng matching rule byte/literal cho giá trị đã băm, gửi mật khẩu plaintext vào yêu cầu Compare **không thể tự động bằng** giá trị băm đã lưu.
- Một số server hoặc cơ chế xác thực có thể triển khai xử lý đặc biệt cho việc kiểm tra mật khẩu. Việc Compare với `userPassword` có thể được phép, bị cấm, hoặc có hành vi phụ thuộc sản phẩm/cấu hình. **Phải xác minh tài liệu và hành vi thực tế của directory đang dùng.**
- ACL có thể cho phép user bind nhưng **không** cho service account compare hoặc đọc `userPassword`. Đây là chính sách bình thường để hạn chế lộ bí mật; không nên tăng quyền chỉ nhằm làm cho Compare hoạt động.
- Máy chủ có thể áp dụng chính sách trạng thái tài khoản, hết hạn mật khẩu hoặc khóa tài khoản cho **bind** theo cách không giống một phép compare attribute. Do đó Compare trả true không phải lúc nào cũng chứng minh người dùng được phép đăng nhập.
- Với một số hệ thống thư mục (đặc biệt khi dùng cơ chế riêng cho credential như Active Directory), thao tác compare/password read đơn giản không phải con đường phù hợp để xác thực.

Khi cần xác thực người dùng với mật khẩu do LDAP quản lý, **user bind là lựa chọn nền tảng, dễ hiểu và dễ tương thích hơn**.

### 3.3. Vì sao không nên đọc `userPassword` để so sánh?

Đọc mật khẩu hoặc hash về backend có những hệ quả:

1. Tài khoản dịch vụ có quyền quá rộng có thể làm lộ dữ liệu xác thực của nhiều người.
2. Hash có thể bị lưu nhầm trong log, trace, cache hoặc phản hồi lỗi, tạo cơ hội tấn công offline.
3. Ứng dụng phải theo kịp thay đổi thuật toán, salt, work factor và định dạng hash của server.
4. Có thể bỏ qua quy tắc khóa tài khoản, hết hạn, đổi mật khẩu và các chính sách server khi chỉ kiểm tra hash.
5. Không phù hợp với môi trường mà server không cho phép đọc hoặc tiết lộ password attribute.

Ngay cả khi ứng dụng có thể đọc một hash LDAP, không nên trả nó về trình duyệt hay dùng `equals` giữa chuỗi plaintext và hash. Nếu kiến trúc bắt buộc kiểm tra hash ở ứng dụng, phải thiết kế riêng và đánh giá chính sách bảo mật, lưu trữ và vận hành; đó không phải mặc định của Spring LDAP bind authentication.

## 4. Luồng thực hiện của hai phương án

### 4.1. Search rồi user bind

Khi người dùng chỉ nhập username (không biết DN), ứng dụng có thể search entry rồi thực hiện user bind:

~~~mermaid
sequenceDiagram
    actor U as Người dùng
    participant App as Spring application
    participant Dir as LDAP server
    U->>App: Username và mật khẩu qua HTTPS
    App->>Dir: Bind bằng tài khoản dịch vụ
    Dir-->>App: Đã xác thực tài khoản dịch vụ
    App->>Dir: Search (uid=lan) trong ou=people
    Dir-->>App: DN của người dùng
    App->>Dir: User bind bằng DN và mật khẩu
    alt Bind thành công
        Dir-->>App: Success
        App-->>U: Tiếp tục chính sách ứng dụng và đăng nhập
    else Bind bị từ chối
        Dir-->>App: Invalid credentials hoặc lỗi chính sách
        App-->>U: Đăng nhập không thành công
    end
~~~

Các thao tác tìm DN và bind có thể diễn ra trên **ngữ cảnh/kết nối khác nhau**. Ứng dụng phải bảo đảm context xác thực bằng mật khẩu người dùng được quản lý và đóng/trả an toàn, không làm nhiễm danh tính của tài khoản dịch vụ hoặc các request khác.

### 4.2. Service bind rồi Compare password attribute

~~~mermaid
sequenceDiagram
    actor U as Người dùng
    participant App as Spring application
    participant Dir as LDAP server
    U->>App: Username và mật khẩu qua HTTPS
    App->>Dir: Bind bằng tài khoản dịch vụ
    Dir-->>App: Đã xác thực tài khoản dịch vụ
    App->>Dir: Search DN người dùng
    Dir-->>App: DN của người dùng
    App->>Dir: Compare DN + password attribute + assertion
    Dir-->>App: compareTrue / compareFalse / LDAP error
    Note over App,Dir: Context LDAP vẫn mang danh tính tài khoản dịch vụ
    App-->>U: Xử lý theo chính sách được cấu hình
~~~

Luồng thứ hai chỉ khả thi nếu server thực sự cho phép và hỗ trợ cơ chế so sánh mật khẩu mong muốn. Ứng dụng không được coi một lần Compare thành công là bằng chứng chính sách **bind** và trạng thái phiên của người dùng đã được áp dụng.

## 5. Spring LDAP: phân biệt `compare(...)` và `authenticate(...)`

### 5.1. Cấu hình kết nối minh họa

Để thao tác LDAP, Spring Boot có thể cấu hình `ContextSource` qua thuộc tính `spring.ldap`. Ví dụ:

~~~yaml
spring:
  ldap:
    urls: ldaps://ldap.example.org:636
    base: dc=example,dc=org
    username: cn=svc-reader,ou=system,dc=example,dc=org
    password: ${LDAP_READER_PASSWORD}
~~~

Trong ví dụ này, ứng dụng đã khai báo dependency Spring LDAP phù hợp với phiên bản Spring Boot đang sử dụng; `LdapTemplate` được cấu hình để tạo kết nối tới LDAP. Thông tin đăng nhập trong cấu hình là của **service account**, chỉ dùng cho các thao tác tra cứu/so sánh được cấp phép. Mật khẩu phải được cung cấp từ secret manager hoặc biến môi trường, không hardcode trong mã nguồn.

### 5.2. Dùng `LdapTemplate.compare(...)` để kiểm tra một thuộc tính

Ví dụ sau cho thấy Compare hoạt động đúng với một thuộc tính nghiệp vụ **không chứa mật khẩu**:

~~~java
import javax.naming.Name;

import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;
import org.springframework.stereotype.Service;

@Service
public class DirectoryAttributeService {
    private final LdapTemplate ldapTemplate;

    public DirectoryAttributeService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public boolean isInternalEmployee() {
        // DN tương đối với spring.ldap.base (dc=example,dc=org).
        Name relativeDn = LdapNameBuilder.newInstance()
                .add("ou", "people")
                .add("uid", "lan")
                .build();

        // Kết quả true/false thể hiện Compare trên employeeType.
        return ldapTemplate.compare(
                relativeDn,
                "employeeType",
                "internal"
        );
    }
}
~~~

Ở đây:

- `LdapNameBuilder` dựng DN đúng cú pháp; DN ví dụ tương đối với base DN đã cấu hình.
- `compare(...)` tạo yêu cầu kiểm tra thuộc tính trên máy chủ LDAP theo context đang sử dụng. Không có mật khẩu của Lan trong lời gọi.
- `true` cho biết điều kiện so sánh được chấp nhận, **không phải Lan vừa đăng nhập**.
- Các lỗi khác như thiếu quyền, không tìm thấy DN hoặc lỗi kết nối cần được xử lý riêng; không nên biến mọi ngoại lệ thành `false` rồi gọi đó là “mật khẩu sai”.

Nếu muốn kiểm tra trạng thái tài khoản theo attribute, phải biết chính xác schema và matching rule. Ngay cả `employeeType=internal` cũng không tự thay thế được một hệ thống **authorization** đầy đủ.

### 5.3. Dùng `LdapTemplate.authenticate(...)` cho xác thực mật khẩu

Để xác thực người dùng cuối, Spring LDAP cung cấp phương thức `authenticate(...)` thực hiện quy trình dựa trên search và bind. Ví dụ:

~~~java
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;
import org.springframework.stereotype.Service;

@Service
public class DirectoryLoginService {
    private final LdapTemplate ldapTemplate;

    public DirectoryLoginService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public boolean authenticate(String username, String password) {
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

**Cách đọc ví dụ:**

1. Ứng dụng nhận `username` và `password` từ kênh HTTPS và kiểm tra đầu vào; đặc biệt **từ chối mật khẩu rỗng** để không vô tình chấp nhận anonymous/unauthenticated bind.
2. Query builder tạo filter equality an toàn; không nối username trực tiếp vào chuỗi filter.
3. `base("ou=people")` giới hạn search tương đối với cấu hình `spring.ldap.base`; nên chọn đúng phạm vi cần thiết và bảo đảm tên định danh **duy nhất**.
4. `ldapTemplate.authenticate(...)` tìm DN phù hợp và dùng password để LDAP xác thực bằng bind. Kết quả boolean mô tả xác thực, còn lỗi dịch vụ hoặc lỗi TLS cần được xử lý ở tầng gọi.
5. Kết quả `true` chưa tự cấp session, JWT hoặc quyền truy cập tài nguyên; tích hợp với Spring Security hoặc cơ chế authorization của ứng dụng.

**Đừng thay `authenticate(...)` bằng `compare(dn, "userPassword", password)` chỉ vì chữ ký API có vẻ tương đồng.** So sánh `userPassword` chỉ đúng trong những triển khai LDAP hỗ trợ và cho phép điều đó, và vẫn không có cùng ngữ nghĩa phiên/kết nối của bind.

### 5.4. Spring Security LDAP: hai hướng tích hợp

Nếu ứng dụng dùng Spring Security, có hai lớp xác thực LDAP thường được nhắc tới:

| Thành phần | Ý tưởng | Khi cân nhắc |
|---|---|---|
| `BindAuthenticator` | Tìm hoặc suy ra DN người dùng rồi thử bind bằng credential người dùng | Phù hợp với xác thực tài khoản LDAP thông thường |
| `PasswordComparisonAuthenticator` | Sử dụng cơ chế so sánh mật khẩu đối với dữ liệu/thuộc tính do thư mục quản lý | Chỉ dùng khi đã biết chính xác cách lấy hoặc compare password, thuật toán mã hóa, ACL và giới hạn của server |

Đây là những thành phần của **Spring Security LDAP**, không nên nhầm với lớp `LdapTemplate` của Spring LDAP. Tùy phiên bản Spring Security và cấu hình, đường so sánh mật khẩu có thể liên quan tới LDAP Compare và/hoặc so khớp giá trị thuộc tính ở tầng ứng dụng. Cần tham chiếu API và hành vi của **đúng phiên bản đang sử dụng**, thay vì giả định mọi máy chủ LDAP đều cho phép đọc/compare mật khẩu.

Trong trường hợp tiêu chuẩn, phương án bind có xu hướng phù hợp hơn với chính sách xác thực do LDAP server thực thi và tránh yêu cầu cấp quyền đọc thuộc tính mật khẩu cho backend.

## 6. Điểm khác biệt về security và authorization

### 6.1. Danh tính của kết nối là ai?

Ví dụ service account `cn=svc-reader,...` có quyền search và Compare. Nó gửi `Compare(uid=lan, employeeType=internal)` và nhận `compareTrue`.

**Kết luận đúng:** Thuộc tính `employeeType` của entry tương ứng khớp với giá trị đã hỏi theo quyền và matching rule của server.

**Kết luận sai:** “Tài khoản Lan đã bind thành công” hoặc “mọi thao tác LDAP tiếp theo đều chạy dưới quyền của Lan”.

Khi cần thực hiện tác vụ LDAP **dưới quyền của người dùng cuối**, phải thiết kế rõ ngữ cảnh người dùng đã bind và quản lý vòng đời nó. Dùng một context của service account để so sánh không thay đổi danh tính đó.

### 6.2. Mật khẩu đúng chưa chắc đủ điều kiện đăng nhập

Một directory có thể triển khai các chính sách: tài khoản bị khóa, mật khẩu hết hạn, chỉ cho đăng nhập tại một số thời điểm hoặc cơ chế xác thực khác. Bind có thể đi qua các quy tắc này, trong khi phép so sánh attribute không được bảo đảm áp dụng cùng bộ quy tắc.

Do đó, một phép compare plaintext hoặc hash có thể báo “khớp” nhưng ứng dụng vẫn phải từ chối phiên đăng nhập theo chính sách LDAP hoặc chính sách nghiệp vụ. Không tự suy luận từ `compareTrue` rằng toàn bộ chính sách xác thực đã hoàn tất.

### 6.3. Authentication khác authorization

Ngay cả khi user bind trả thành công, ứng dụng vẫn cần quyết định người dùng được xem báo cáo, sửa dữ liệu hay vào trang quản trị hay không. Có thể phải tìm nhóm LDAP (ví dụ `member`/`memberOf`, tùy schema), map role và áp dụng policy của ứng dụng.

Đặc biệt, việc so sánh `employeeType=internal` hoặc `accountStatus=active` chỉ là một **điều kiện thuộc tính**, không thay thế mô hình kiểm soát quyền truy cập.

## 7. Lỗi thường gặp và cách xử lý

| Tình huống | Vì sao xảy ra? | Hướng xử lý |
|---|---|---|
| User bind thành công nhưng Compare `userPassword` thất bại | Server không hỗ trợ compare plaintext với hash, ACL khác hoặc chính sách attribute khác | Dùng bind để xác thực; không nới ACL chỉ để ép Compare hoạt động |
| Compare trả `compareFalse` | Attribute không khớp theo quy tắc server | Phân biệt với lỗi không đủ quyền hoặc lỗi kết nối |
| LDAP trả `insufficientAccessRights` | Account gửi Compare không đủ quyền trên entry/attribute | Kiểm tra ACL và thiết kế quyền tối thiểu, không tự nâng lên tài khoản admin |
| `noSuchObject` | DN không tồn tại hoặc vượt ngoài vùng được phép | Kiểm tra base DN, DN đã tìm và vòng đời entry |
| Mật khẩu rỗng nhưng bind không báo lỗi theo cách dự kiến | Một số server có chế độ anonymous/unauthenticated simple bind | Từ chối password rỗng tại ứng dụng trước khi gọi LDAP |
| Mật khẩu đúng nhưng login bị từ chối | Tài khoản khóa/hết hạn hoặc chính sách server khác | Đọc mã lỗi và log kỹ thuật phù hợp; phản hồi bên ngoài trung tính |
| Không tìm thấy người dùng | Search filter, base hoặc scope không khớp | Kiểm tra schema và vùng search; không tiết lộ tài khoản có tồn tại |
| Hai entry khớp cùng username | Định danh mơ hồ trong vùng tìm kiếm | Thiết kế uniqueness hoặc từ chối an toàn, không chọn entry đầu tiên |
| SSL handshake lỗi | Truststore, tên host, chứng chỉ hoặc TLS sai | Sửa cấu hình tin cậy, không tắt kiểm tra TLS |
| Timeout/kết nối từ chối | LDAP server hoặc mạng không sẵn sàng | Xử lý như lỗi hạ tầng; không ghi là “sai mật khẩu” |

Khi dùng API ở tầng ứng dụng, các ngoại lệ LDAP có thể được Spring dịch sang hệ ngoại lệ riêng. Không nên dùng duy nhất một khối `catch (Exception) { return false; }` cho mọi lỗi vì sẽ che mất sự cố hạ tầng và làm việc hỗ trợ vận hành khó hơn.

## 8. Quy tắc triển khai an toàn

1. **Ưu tiên user bind khi cần đăng nhập.** Đây là cách tự nhiên để server xác minh credential của người dùng theo cơ chế xác thực được cấu hình.
2. **Không dùng password compare như một cách né chính sách LDAP.** Nếu server không cho đọc `userPassword` hoặc không cho Compare, hãy tôn trọng thiết kế đó.
3. **Bảo vệ kênh truyền:** dùng LDAPS hoặc StartTLS và xác minh chứng chỉ LDAP server **trước khi truyền mật khẩu**. HTTPS giữa trình duyệt với ứng dụng không thay thế TLS giữa backend với LDAP.
4. **Giữ secret trong secret manager/biến môi trường;** không hardcode trong tài liệu cấu hình thực, log, URL hoặc command-line argument có thể bị lưu lại.
5. **Giới hạn quyền service account.** Cấp quyền search/compare thuộc tính nghiệp vụ tối thiểu; tránh cấp quyền đọc/compare password nếu không thực sự có thiết kế và phê duyệt cần thiết.
6. **Escape LDAP filter và DN đúng ngữ cảnh.** Dùng `LdapQueryBuilder` để tìm DN và `LdapNameBuilder` để dựng DN; không ghép trực tiếp dữ liệu người dùng vào filter hay DN.
7. **Kiểm tra uniqueness và phạm vi search.** Username phải định danh đúng một entry trong vùng hợp lệ; dữ liệu trùng phải được xử lý như tình huống mơ hồ.
8. **Không lưu password/hash vào log hoặc cache.** Nếu cần quan sát, log loại sự cố, correlation ID và trạng thái kỹ thuật vừa đủ.
9. **Kiểm soát brute force và phân quyền:** giới hạn tốc độ xác thực, theo dõi lỗi đăng nhập, sau bind vẫn kiểm tra quyền tài nguyên.
10. **Quản lý connection/context an toàn.** Không chia sẻ một user-bound context giữa request hoặc lẫn vào pool service connection; cấu hình pooling phải tôn trọng danh tính và chính sách bảo mật.

## 9. Thực hành và kiểm thử

### 9.1. Tình huống thực hành

Môi trường ví dụ:

~~~text
dc=example,dc=org
├── ou=people
│   ├── uid=lan
│   └── uid=minh
└── ou=system
    └── cn=svc-reader
~~~

Tài khoản `svc-reader` có quyền tìm `uid` và so sánh một thuộc tính thử nghiệm như `employeeType`, nhưng không có quyền đọc mật khẩu của nhân viên. Kết nối LDAP dùng TLS đã xác minh chứng chỉ.

**Bước 1 — Search.** Dùng `LdapQueryBuilder` để tìm entry `uid=lan` và kiểm tra vùng tìm kiếm trả về đúng DN.

**Bước 2 — Compare thuộc tính.** Dùng `LdapTemplate.compare(...)` với `employeeType=internal`. Kiểm tra trả `true` khi khớp và `false` khi không khớp. Xác nhận ngữ cảnh vẫn dùng service account.

**Bước 3 — User bind.** Gọi `LdapTemplate.authenticate(...)` với `uid=lan` và mật khẩu đúng/sai. Phân biệt kết quả bind với bước Compare thuộc tính.

**Bước 4 — Tình huống lỗi.** Thử tài khoản không có quyền compare, DN không tồn tại, mật khẩu rỗng và lỗi TLS. Quan sát kết quả và log kỹ thuật; không ghi credential.

### 9.2. Ma trận kết quả mong đợi

| Kiểm thử | Kết quả kỳ vọng |
|---|---|
| Compare `employeeType=internal` với entry có giá trị tương ứng | `true` nếu ACL/schema cho phép; không đổi danh tính của kết nối |
| Compare `employeeType=external` trên entry có `internal` | `false` nếu phép so sánh hợp lệ và không khớp |
| Compare khi thiếu quyền | Lỗi LDAP liên quan quyền; không coi là “mật khẩu sai” |
| User bind với password đúng | Thành công theo chính sách server |
| User bind với password sai | Thất bại xác thực |
| User bind với mật khẩu rỗng | Bị ứng dụng từ chối trước khi gửi |
| Search username chứa dấu `*` hoặc dấu ngoặc | Bộ lọc giữ giá trị literal, không biến thành wildcard hay điều kiện khác |
| Có hai DN trong vùng search khớp username | Từ chối trường hợp mơ hồ, không chọn phần tử đầu |
| Tắt quyền đọc `userPassword` nhưng vẫn cho bind | Đăng nhập bằng bind vẫn có thể hoạt động bình thường |
| Server chứa hash mật khẩu nhưng không hỗ trợ plaintext Compare | Không ép so sánh; xác thực bằng bind |
| TLS không hợp lệ | Dừng kết nối an toàn, không chuyển về plaintext |
| Bind thành công nhưng không đủ quyền ứng dụng | Authentication thành công, authorization từ chối chức năng |

### 9.3. Câu hỏi tự kiểm tra

1. Nếu `ldapTemplate.compare(dn, "employeeType", "internal")` trả `true`, danh tính của kết nối có đổi thành DN người dùng không?
2. Vì sao `compareTrue` trên một thuộc tính mật khẩu không luôn tương đương với user bind thành công?
3. Nếu `userPassword` lưu dưới dạng hash, tại sao không thể mặc nhiên gửi plaintext vào LDAP Compare và đòi kết quả khớp?
4. Khi nào nên dùng `LdapTemplate.authenticate(...)` thay cho `LdapTemplate.compare(...)`?
5. Tài khoản dịch vụ không được phép đọc `userPassword`. Có nên tăng quyền đọc để tự so sánh mật khẩu không? Vì sao?
6. Vì sao mật khẩu rỗng và lỗi kết nối LDAP phải được xử lý khác mật khẩu sai?
7. Khi đã xác thực bằng bind thành công, bước nào quyết định nhân viên có quyền vào trang quản trị?

**Gợi ý trả lời:** (1) Không; Compare giữ nguyên danh tính của context đang gửi. (2) Compare là phép so sánh attribute, có ACL và matching rule riêng, không tạo phiên user-bound hay chắc chắn áp dụng cùng chính sách bind. (3) Hash không bằng plaintext nếu server không có hỗ trợ riêng. (4) Khi cần LDAP xác thực credential của người dùng bằng bind. (5) Không; hạn chế quyền tiếp cận password và ưu tiên bind. (6) Anonymous bind và lỗi hạ tầng có ý nghĩa khác thông tin xác thực không hợp lệ. (7) Authorization của ứng dụng/Spring Security.

## Kết luận

Trong Spring LDAP, **password compare** có thể chỉ việc gửi LDAP Compare tới một attribute hoặc kiểm tra giá trị mật khẩu tại ứng dụng; cả hai khác bản chất với **LDAP user bind**. `LdapTemplate.compare(...)` phù hợp cho so sánh thuộc tính được schema và ACL hỗ trợ, trong khi `LdapTemplate.authenticate(...)` là API rõ nghĩa để xác thực thông tin đăng nhập bằng tìm DN rồi bind. Khi xây dựng hệ thống Authentication, cần ưu tiên cơ chế do LDAP server hỗ trợ chính thức, bảo vệ đường truyền bằng TLS, hạn chế quyền đọc dữ liệu xác thực và giữ bước phân quyền độc lập với kết quả bind.
