# LDAP không mã hóa và nguy cơ truyền thông tin

## 1. Vì sao kết nối LDAP cần được bảo vệ?

LDAP (Lightweight Directory Access Protocol) là giao thức truy vấn và quản lý dịch vụ thư mục. Một ứng dụng Java dùng **Spring LDAP** có thể kết nối máy chủ thư mục để xác thực tài khoản, tìm người dùng hoặc nhóm, đọc thuộc tính và cập nhật entry. Đằng sau `LdapTemplate`, `LdapClient` hay ánh xạ đối tượng thư mục (ODM), các yêu cầu này vẫn phải đi qua một kết nối mạng.

**LDAP không tự động mã hóa dữ liệu chỉ vì ứng dụng có xác thực.** Khi sử dụng kết nối LDAP thông thường trên TCP mà không có TLS hoặc lớp bảo vệ tương đương, dữ liệu LDAP được đóng gói để truyền nhưng không được che giấu khỏi bên có khả năng quan sát đường truyền. Đặc biệt, nếu dùng **simple bind** (đăng nhập bằng DN và mật khẩu) trên kết nối này, mật khẩu có thể xuất hiện trực tiếp trong dữ liệu giao thức.

Trong phạm vi chương **TLS và bảo mật kết nối**, bài học tập trung vào: dữ liệu nào bị lộ khi LDAP không mã hóa, các kiểu tấn công có thể xảy ra, dấu hiệu nhận biết cấu hình không an toàn và cách áp dụng nguyên tắc **thiết lập kênh TLS trước khi gửi thông tin nhạy cảm** trong Spring LDAP.

### Phân biệt giao thức, xác thực và mã hóa

| Khái niệm | Vai trò | Điều cần nhớ |
| --- | --- | --- |
| LDAP | Định dạng và xử lý thao tác `Bind`, `Search`, `Add`, `Modify`, `Delete`… | Bản thân thao tác LDAP không bảo đảm bí mật đường truyền. |
| Simple bind | Chứng minh danh tính bằng DN và mật khẩu | Nếu kênh truyền không được bảo vệ, thông tin bind có thể bị đọc trên mạng. |
| TLS | Bảo vệ tính bí mật, toàn vẹn và xác thực máy chủ qua chứng chỉ | Phải hoàn tất và kiểm tra hợp lệ **trước** thao tác bind hoặc truy vấn nhạy cảm. |
| SASL | Cơ chế xác thực có thể thương lượng thêm lớp bảo vệ | Tùy cơ chế và cấu hình; không được mặc định xem mọi phiên SASL đều mã hóa. |
| Spring LDAP | Thư viện Java giúp quản lý kết nối và thao tác với thư mục | An toàn của `LdapTemplate`/`LdapClient` phụ thuộc vào cấu hình `ContextSource` và máy chủ. |

Một kết nối có thể xác thực thành công nhưng **vẫn truyền dữ liệu dưới dạng có thể đọc được**. Ngược lại, mã hóa TLS bảo vệ đường truyền nhưng không tự cấp quyền truy cập: máy chủ vẫn cần xác thực và phân quyền LDAP.

## 2. Điều gì thực sự đi qua mạng?

LDAP thường hoạt động trên TCP. Hai kiểu thiết lập kết nối phổ biến là:

- `ldap://directory.example.org:389`: kết nối LDAP khởi đầu không có TLS; chỉ được bảo vệ nếu client chủ động nâng cấp bằng **StartTLS** thành công trước khi trao đổi dữ liệu nhạy cảm (hoặc có một lớp bảo vệ phù hợp khác).
- `ldaps://directory.example.org:636`: TLS được thương lượng ngay khi bắt đầu kết nối, trước các yêu cầu LDAP; đây là cách triển khai LDAP qua TLS được dùng phổ biến.

Các cổng 389 và 636 là **giá trị quy ước**, không phải chứng cứ về trạng thái mã hóa. Máy chủ có thể được cấu hình cổng khác. Để xác nhận an toàn, cần kiểm tra quá trình thương lượng TLS, chứng chỉ, tên máy chủ và cách ứng dụng xử lý lỗi.

Một phiên LDAP không mã hóa có thể làm lộ:

| Thành phần | Ví dụ minh họa | Rủi ro |
| --- | --- | --- |
| DN của tài khoản bind | `cn=app-reader,ou=services,dc=example,dc=org` | Tiết lộ cấu trúc thư mục và tài khoản dịch vụ. |
| Mật khẩu simple bind | Mật khẩu của `app-reader` | Kẻ nghe lén có thể chiếm quyền truy cập tương ứng với tài khoản đó. |
| Base DN, phạm vi và bộ lọc tìm kiếm | `(uid=an.nguyen)`, `ou=people,dc=example,dc=org` | Cho biết ai đang được tra cứu, cấu trúc và cách ứng dụng sử dụng thư mục. |
| Thuộc tính và giá trị trong kết quả | `mail`, `telephoneNumber`, `memberOf` | Làm lộ dữ liệu cá nhân, thông tin tổ chức, nhóm hoặc quyền. |
| Dữ liệu cập nhật | Thay đổi thuộc tính entry hay thành viên nhóm | Có thể lộ nội dung cập nhật; nếu không có bảo vệ toàn vẹn, còn có nguy cơ bị can thiệp. |
| Phản hồi của máy chủ | `BindResponse`, `SearchResultEntry`, mã lỗi | Có thể tiết lộ sự tồn tại của tài khoản, trạng thái yêu cầu và thông tin phục vụ dò tìm. |

**Ví dụ:** Ứng dụng nội bộ dùng tài khoản dịch vụ để tìm người dùng rồi kiểm tra `memberOf`. Nếu ứng dụng dùng simple bind qua `ldap://` và không bật StartTLS, một bên có quyền quan sát luồng mạng có thể đọc mật khẩu của tài khoản dịch vụ, tên người dùng được tìm kiếm và nhóm do máy chủ trả về.

### Minh họa một phiên không có TLS

~~~mermaid
sequenceDiagram
    participant App as Ứng dụng Spring LDAP
    participant Network as Điểm quan sát trên mạng
    participant Dir as Máy chủ LDAP
    App->>Dir: TCP đến cổng 389
    App->>Dir: BindRequest (DN, mật khẩu)
    Note over Network: Có thể đọc nội dung LDAP khi truyền không mã hóa
    Dir-->>App: BindResponse
    App->>Dir: SearchRequest (base DN, filter, attributes)
    Dir-->>App: SearchResultEntry (các thuộc tính)
    Note over App,Dir: Chưa có kênh bảo mật nếu không thiết lập TLS hoặc lớp bảo vệ khác
~~~

LDAP sử dụng cơ chế mã hóa cấu trúc dữ liệu ASN.1/BER để biểu diễn thông điệp. **Encoding không phải encryption**: bộ bắt gói tin có thể phân tích các trường của thông điệp LDAP ở dạng không có TLS. Với simple bind, mật khẩu nằm trong trường xác thực của thông điệp bind, không phải một hàm băm bí mật được tạo tự động bởi LDAP.

## 3. Các mối đe dọa khi LDAP không mã hóa

### 3.1. Nghe lén thụ động

Người có quyền truy cập lưu lượng trên cùng phân đoạn mạng, thiết bị trung gian hoặc hệ thống giám sát có thể ghi lại phiên LDAP và giải mã cấu trúc thông điệp. Họ không cần thay đổi gói tin để thu thập DN, bộ lọc, kết quả tìm kiếm hoặc thông tin simple bind.

Điều này vẫn có thể xảy ra trên mạng nội bộ, giữa các container, từ ứng dụng đến proxy, hoặc trên liên kết giữa hai trung tâm dữ liệu. Nhãn “internal” của một địa chỉ IP không làm dữ liệu tự mã hóa.

### 3.2. Giả mạo máy chủ và tấn công xen giữa (MITM)

Nếu ứng dụng không xác thực máy chủ bằng chứng chỉ TLS hợp lệ, kẻ tấn công kiểm soát một điểm trên đường truyền có thể tìm cách đứng giữa ứng dụng và dịch vụ thư mục. Trên kết nối LDAP hoàn toàn không được bảo vệ, kẻ tấn công còn có thể can thiệp nội dung yêu cầu/phản hồi, chẳng hạn trả về kết quả nhóm sai để ảnh hưởng quyết định phân quyền của ứng dụng.

TLS giúp bảo vệ khỏi kiểu tấn công này khi **xác thực chuỗi chứng chỉ, kiểm tra tên máy chủ và không bỏ qua lỗi TLS**. Chỉ đổi tiền tố URL sang `ldaps://` là chưa đủ nếu ứng dụng cố ý tin mọi chứng chỉ.

### 3.3. Lộ tài khoản dịch vụ kéo theo rủi ro lớn hơn

Một ứng dụng thường bind bằng tài khoản kỹ thuật có thể đọc nhiều entry. Nếu mật khẩu tài khoản này bị lộ, phạm vi tác động phụ thuộc quyền LDAP thực tế: đọc dữ liệu hàng loạt, tìm nhóm hoặc sửa entry nếu tài khoản có quyền ghi. Việc cấp quyền tối thiểu giảm thiệt hại nhưng không thay thế mã hóa kết nối.

### 3.4. Downgrade và fallback không an toàn

Với StartTLS, client bắt đầu bằng kết nối `ldap://` rồi yêu cầu nâng cấp lên TLS. Nếu máy chủ từ chối, mạng gây lỗi hoặc có can thiệp trên đường truyền, client **phải dừng phiên** khi chính sách yêu cầu TLS. Tiếp tục simple bind qua kết nối chưa nâng cấp sẽ biến sự cố TLS thành lộ thông tin xác thực.

Một lỗi cấu hình tương tự là thử `ldaps://` thất bại rồi tự động chuyển sang `ldap://` để “duy trì dịch vụ”. Trong hệ thống yêu cầu kênh an toàn, hành vi đúng là **fail closed**: từ chối kết nối đến khi TLS hoạt động hợp lệ.

### Bảng đối chiếu tình huống và ảnh hưởng

| Tình huống | Khả năng bị ảnh hưởng | Biện pháp chính |
| --- | --- | --- |
| Simple bind qua `ldap://` không StartTLS | Lộ mật khẩu và DN | Bắt buộc TLS trước khi bind; máy chủ từ chối simple bind không được bảo vệ. |
| Tìm kiếm thuộc tính nhạy cảm trên kênh rõ | Lộ nội dung truy vấn và kết quả | Mã hóa toàn bộ phiên LDAP, kể cả các thao tác đọc. |
| Tin mọi chứng chỉ hoặc bỏ qua hostname | Có thể kết nối nhầm máy chủ giả mạo | Kiểm tra CA tin cậy, tên máy chủ, thời hạn chứng chỉ. |
| StartTLS lỗi rồi client vẫn gửi bind | Rò rỉ do fallback xuống kết nối rõ | Dừng kết nối khi TLS không thành công; kiểm thử nhánh lỗi. |
| TLS kết thúc ở proxy, chặng sau đi rõ | Dữ liệu lộ trên chặng proxy–LDAP | Bảo vệ từng chặng cần thiết, đánh giá điểm kết thúc TLS. |

## 4. Các lựa chọn bảo vệ đường truyền

| Cách kết nối | Thời điểm bảo vệ dữ liệu | Lưu ý khi dùng Spring LDAP |
| --- | --- | --- |
| `ldap://` không StartTLS | Không có bảo vệ TLS | Không dùng cho simple bind và dữ liệu nhạy cảm. |
| `ldap://` + StartTLS | Sau khi yêu cầu StartTLS và bắt tay TLS **thành công** | Phải cấu hình chiến lược StartTLS, không thực hiện bind trước TLS; kiểm tra hành vi khi nâng cấp thất bại. |
| `ldaps://` | TLS được bắt tay ngay sau TCP, trước thông điệp LDAP | Thường là lựa chọn đơn giản khi máy chủ hỗ trợ LDAPS và chứng chỉ hợp lệ. |
| SASL có lớp bảo vệ thương lượng | Phụ thuộc cơ chế và chất lượng bảo vệ đã thương lượng | Cần kiểm chứng cụ thể; không dùng tên cơ chế xác thực như bằng chứng rằng kênh đã mã hóa. |

### Trình tự đúng với StartTLS

~~~mermaid
sequenceDiagram
    participant App as Ứng dụng
    participant Dir as Máy chủ LDAP
    App->>Dir: Mở TCP/389
    App->>Dir: Yêu cầu mở rộng StartTLS
    Dir-->>App: Chấp nhận StartTLS
    App->>Dir: Bắt tay TLS và kiểm tra chứng chỉ
    Note over App,Dir: Chỉ tiếp tục nếu TLS và xác thực máy chủ thành công
    App->>Dir: BindRequest bên trong TLS
    Dir-->>App: BindResponse bên trong TLS
    App->>Dir: SearchRequest bên trong TLS
    Dir-->>App: SearchResultEntry bên trong TLS
~~~

Khi yêu cầu StartTLS bị từ chối, bắt tay TLS lỗi hoặc chứng chỉ không hợp lệ, client phải ngừng quy trình trước thao tác bind. Một cấu hình `ldap://` đơn thuần **không có nghĩa StartTLS đã được kích hoạt**.

TLS còn phải đủ mạnh theo chính sách hệ thống (ví dụ cho phép TLS 1.2/1.3 nếu phù hợp với thành phần triển khai), dùng chứng chỉ hợp lệ, bảo vệ khóa riêng và quản lý vòng đời gia hạn chứng chỉ. Không vô hiệu hóa kiểm tra chứng chỉ để “sửa nhanh” lỗi kết nối.

## 5. Ví dụ cấu hình an toàn trong Spring LDAP

Giả sử một ứng dụng Spring Boot dùng Spring LDAP để tra cứu người dùng. Thay vì khởi tạo kết nối từ URL `ldap://directory.example.org:389` rồi bind ngay, cấu hình URL **LDAPS** và lấy mật khẩu từ biến môi trường:

~~~yaml
# application.yml - minh họa; tên miền và DN là giả định
spring:
  ldap:
    urls: ldaps://directory.example.org:636
    base: dc=example,dc=org
    username: cn=app-reader,ou=services,dc=example,dc=org
    password: ${LDAP_BIND_PASSWORD}
~~~

Với cấu hình tự động tương ứng của Spring Boot, những thao tác qua `LdapTemplate`, `LdapClient` hoặc ODM dùng chung `ContextSource` sẽ đi qua kết nối LDAPS đã cấu hình. Chứng chỉ phía máy chủ phải được Java/JNDI tin cậy qua cấu hình truststore thích hợp, và tên máy chủ trong URL phải phù hợp với chứng chỉ.

Ví dụ một truy vấn Spring LDAP sau khi cấu hình kết nối:

~~~java
import static org.springframework.ldap.query.LdapQueryBuilder.query;

import java.util.List;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;

public class DirectoryLookup {
    private final LdapTemplate ldapTemplate;

    public DirectoryLookup(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<String> findNamesByUid(String uid) {
        return ldapTemplate.search(
            query().base("ou=people").where("uid").is(uid),
            (AttributesMapper<String>) attributes ->
                (String) attributes.get("cn").get()
        );
    }
}
~~~

Đoạn truy vấn dùng bộ xây dựng filter của Spring LDAP, nhưng **filter an toàn không thay thế TLS**. Các DN, bộ lọc và kết quả vẫn cần được bảo vệ trên mạng. Mọi API truy cập thư mục trong ứng dụng phải sử dụng `ContextSource` được cấu hình đúng; nếu có nhiều `ContextSource`, cần rà soát từng cái.

**Lưu ý khi dùng StartTLS với Spring LDAP:** cần cấu hình chiến lược xác thực/kết nối có khả năng nâng cấp TLS và bảo đảm thao tác nâng cấp diễn ra trước khi bind. Việc quản lý lại kết nối và pooling phải tương thích với vòng đời StartTLS; không mặc định rằng đặt URL `ldap://` hay bật connection pool đã đủ để mã hóa. Khi muốn giảm độ phức tạp ban đầu, sử dụng LDAPS với cấu hình chứng chỉ đầy đủ thường dễ kiểm chứng hơn.

## 6. Cách kiểm tra có thực sự dùng TLS hay không

### 6.1. Rà soát ứng dụng và máy chủ

1. Tìm tất cả URL LDAP ứng dụng sử dụng. Với mỗi URL `ldap://`, xác nhận có nâng cấp StartTLS và thành công **trước** bind/truy vấn; không suy đoán từ số cổng.
2. Kiểm tra CA tin cậy, tên máy chủ, thời hạn chứng chỉ, phiên bản TLS được thương lượng và nhánh xử lý lỗi xác thực chứng chỉ.
3. Xác minh máy chủ áp dụng chính sách từ chối simple bind không được bảo vệ và tài khoản ứng dụng chỉ có quyền cần thiết.
4. Kiểm tra cấu hình fallback, kết nối qua proxy/load balancer, kết nối dự phòng, pool và các đường đi khác có thể bỏ qua cấu hình an toàn.
5. Kiểm tra ứng dụng không ghi mật khẩu bind, secret, kết quả nhạy cảm hoặc thông tin xác thực đầy đủ vào log.

### 6.2. Quan sát bắt tay TLS trong môi trường thử nghiệm

Nếu có `openssl`, có thể kiểm tra dịch vụ LDAPS và khả năng nâng cấp StartTLS bằng những lệnh minh họa sau (thay tên miền bằng hostname thật của môi trường thử nghiệm):

~~~bash
# TLS ngay từ đầu kết nối, thường qua cổng 636
openssl s_client -connect directory.example.org:636 -servername directory.example.org -verify_hostname directory.example.org -verify_return_error

# Nâng cấp LDAP sang TLS, thường qua cổng 389
openssl s_client -starttls ldap -connect directory.example.org:389 -verify_hostname directory.example.org -verify_return_error
~~~

Cần kiểm tra **bắt tay thành công, chuỗi chứng chỉ đáng tin cậy và hostname phù hợp**. Lệnh kiểm tra công cụ không thay thế thử nghiệm kết nối thực tế từ tiến trình Java với truststore và cấu hình của ứng dụng.

Trong một môi trường lab dùng **tài khoản giả**, có thể quan sát gói tin trên đường truyền:

- Phiên LDAP không TLS: bộ phân tích gói tin có thể đọc các cấu trúc `BindRequest`, `SearchRequest` và `SearchResultEntry`; simple bind có thể để lộ mật khẩu.
- Phiên LDAPS hoặc phiên đã nâng cấp StartTLS: các thông điệp LDAP được đặt bên trong dữ liệu TLS; có thể còn quan sát metadata kết nối như địa chỉ IP, cổng và đặc điểm bắt tay, nhưng không đọc được nội dung LDAP nếu TLS hoạt động đúng.

Không bắt gói tin mang mật khẩu thật hoặc dữ liệu sản xuất nếu không có quy trình bảo vệ và thẩm quyền phù hợp. Không đưa mật khẩu vào lệnh kiểm tra, ảnh chụp màn hình hay báo cáo.

### 6.3. Các trường hợp lỗi cần thử

| Kiểm thử | Kết quả mong đợi |
| --- | --- |
| Máy chủ trả chứng chỉ do CA không tin cậy ký | Ứng dụng từ chối kết nối. |
| Chứng chỉ không khớp tên máy chủ | Ứng dụng từ chối kết nối. |
| Máy chủ từ chối StartTLS hoặc không thể bắt tay TLS | Không có bind hay truy vấn nhạy cảm trên phiên rõ. |
| Một node dự phòng chỉ hỗ trợ LDAP không TLS | Ứng dụng báo lỗi, không âm thầm chuyển sang kết nối rõ. |
| Xác thực hợp lệ qua LDAPS | Truy vấn hoạt động và toàn bộ các yêu cầu LDAP nhạy cảm nằm trong kênh TLS. |

## 7. Bài tập tình huống

**Bối cảnh:** Một dịch vụ quản lý nhân sự dùng Spring LDAP, có cấu hình:

~~~yaml
spring:
  ldap:
    urls: ldap://directory.example.org:389
    base: dc=example,dc=org
    username: cn=hr-reader,ou=services,dc=example,dc=org
    password: ${LDAP_BIND_PASSWORD}
~~~

Ứng dụng xác thực bằng simple bind, sau đó tìm `(department=HR)` và lấy `mail`, `telephoneNumber`. Nhóm phát triển cho rằng hệ thống an toàn vì chỉ chạy trên mạng nội bộ và mật khẩu nằm trong biến môi trường.

**Yêu cầu phân tích:**

1. Dữ liệu nào có thể bị đọc trên đường truyền nếu ứng dụng không dùng StartTLS?
2. Chuyển mật khẩu sang biến môi trường đã giải quyết được rủi ro truyền mạng chưa?
3. Cần đổi cấu hình và bổ sung kiểm thử nào để tránh tái diễn?

**Gợi ý lời giải:** DN/mật khẩu simple bind, bộ lọc tìm kiếm và các thuộc tính trả về đều có nguy cơ bị quan sát. Biến môi trường giúp tránh ghi cứng mật khẩu trong mã nguồn nhưng không mã hóa thông điệp LDAP. Cần bật LDAPS hoặc StartTLS bắt buộc trước bind, xác minh chứng chỉ/hostname, chặn fallback không mã hóa, giới hạn quyền tài khoản `hr-reader` và kiểm tra nhánh lỗi TLS.

## 8. Ghi nhớ

- **LDAP simple bind thành công không chứng minh đường truyền đã mã hóa.** Một phiên `ldap://` không StartTLS có thể làm lộ mật khẩu, DN, truy vấn, thuộc tính và kết quả.
- **Bảo vệ cả bí mật lẫn toàn vẹn:** TLS hỗ trợ chống nghe lén, giả mạo và sửa đổi thông điệp khi được triển khai và xác thực máy chủ đúng.
- **Mã hóa trước khi bind:** dùng LDAPS hoặc StartTLS bắt buộc và dừng khi TLS thất bại; không tự động fallback sang LDAP rõ.
- **Đúng một đường đi chưa đủ:** rà soát mọi `ContextSource`, server dự phòng, proxy, pool và chặng mạng có chứa dữ liệu LDAP.
- **Kiểm chứng bằng hành vi:** cấu hình, bắt tay TLS, kiểm tra chứng chỉ và thử nghiệm lỗi có giá trị hơn việc chỉ nhìn thấy `:636` hoặc chữ “secure” trong tên biến.
