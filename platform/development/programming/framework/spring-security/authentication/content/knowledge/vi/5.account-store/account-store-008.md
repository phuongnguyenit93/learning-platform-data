# Phân biệt không tìm thấy người dùng với lỗi kết nối kho tài khoản

> **Bối cảnh:** Spring Security — Authentication → **Kho tài khoản**. Trong luồng đăng nhập bằng username/password, “đã tìm kiếm thành công nhưng không có bản ghi người dùng” và “không thể tìm kiếm vì database/LDAP/dịch vụ danh tính đang lỗi” là **hai kết quả khác bản chất**. Nhầm chúng có thể làm sai thông báo lỗi, che giấu sự cố vận hành, cho phép fallback xác thực ngoài ý muốn hoặc tạo kết luận sai rằng tài khoản không tồn tại. Bài dùng Java 17 và Spring Security 6.3.x cho ví dụ chạy được.

## 1. Mục tiêu

Sau bài này, bạn có thể:

1. Phân biệt **not found đáng tin**, **credential không hợp lệ**, **lỗi kho tài khoản** và **lỗi dữ liệu/hợp đồng** bằng dấu hiệu cụ thể.
2. Dùng đúng `UserDetailsService.loadUserByUsername`, `UsernameNotFoundException`, `BadCredentialsException` và `InternalAuthenticationServiceException`.
3. Hiểu giá trị mặc định `hideUserNotFoundExceptions = true` trong `AbstractUserDetailsAuthenticationProvider`: che sự khác biệt “username không tồn tại” với “password sai” ở tầng lỗi thông thường.
4. Giải thích tại sao **không được biến mọi exception của database thành `UsernameNotFoundException`**, hoặc trả `null` khi backend lỗi.
5. Phân biệt kết quả Java của `AuthenticationManager` với mã HTTP 401/500/503; biết vì sao **lỗi kho không tự động sinh HTTP 503**.
6. Viết một adapter kho tài khoản và một chương trình có thể chạy để thấy bốn nhánh thành công, thiếu user, sai mật khẩu và mất kết nối.
7. Thiết kế logging, metric, kiểm thử và chính sách nhiều provider an toàn khi nguồn danh tính bị sự cố.

## 2. Vấn đề trong một truy vấn

Giả sử hệ thống nhận đăng nhập `username=linh`. Một thao tác tìm kiếm có thể có các kết quả:

| Kết quả từ kho gốc | Ý nghĩa | Hành động phù hợp |
| --- | --- | --- |
| Truy vấn **thành công**, tìm thấy đúng account | Có dữ liệu đủ để kiểm trạng thái, hash mật khẩu và authorities | Chuyển thành `UserDetails` hợp lệ cho provider kiểm tiếp |
| Truy vấn **thành công**, xác nhận không có account | Không có người dùng với key được tra trong phạm vi tenant/realm đó | `UserDetailsService` ném `UsernameNotFoundException` |
| Không truy cập được DB/LDAP/identity API, timeout, pool cạn | **Không biết** account có tồn tại hay không | Ném lỗi dịch vụ/nguồn dữ liệu, để cơ chế xác thực từ chối vì không đủ bằng chứng |
| Kho trả dữ liệu lỗi, thiếu trường bắt buộc, ánh xạ sai hoặc `null` trái hợp đồng | Không thể tạo `UserDetails` đáng tin | Báo lỗi dữ liệu/dịch vụ; không biến thành tài khoản “không tồn tại” khi chưa chắc |
| Tìm thấy user nhưng password nhập sai | Account có thể tồn tại; credential không hợp lệ | `DaoAuthenticationProvider` ném `BadCredentialsException` |
| Tìm thấy user nhưng `enabled=false` hoặc bị khóa | Account tồn tại nhưng bị chặn bởi chính sách | Provider ném lỗi trạng thái như `DisabledException` hoặc `LockedException` |

**Câu phân loại quan trọng:** “Tôi **đã kiểm tra thành công** và kết luận không có người dùng” khác “Tôi **không thể kiểm tra** nên chưa biết có người dùng hay không”.

Dùng `Optional.empty()` là đúng khi truy vấn thực sự hoàn tất và trả 0 bản ghi trong phạm vi xác định. Dùng `Optional.empty()` như giá trị thay thế cho timeout là **lỗi logic bảo mật**.

## 3. Hợp đồng UserDetailsService

Spring Security định nghĩa:

~~~java
public interface UserDetailsService {
    UserDetails loadUserByUsername(String username)
            throws UsernameNotFoundException;
}
~~~

Đây là chữ ký rút gọn của giao diện. `UserDetailsService` **chỉ tải dữ liệu tài khoản**. Nó không phải toàn bộ engine đăng nhập và không được tự coi rằng username xuất hiện trong database đồng nghĩa credential đã hợp lệ.

Các điều kiện cần giữ:

- Nếu tải thành công, trả **`UserDetails` khác `null`**, chứa username, password hash, trạng thái và authorities theo nguồn tin cậy.
- Nếu **không xác định được** user theo username: ném `UsernameNotFoundException`. Javadoc cũng cho phép lỗi này khi user không có `GrantedAuthority` trong một số tình huống; ứng dụng cần hợp đồng ánh xạ rõ ràng.
- Nếu không thể truy vấn do hạ tầng: **không giả mạo kết quả không tìm thấy**; để lỗi nổi lên hoặc chuyển đổi sang exception dịch vụ bảo toàn nguyên nhân.
- Không trả `new User(...)` với mật khẩu/rule mặc định khi dữ liệu bị lỗi, không cấp quyền tạm thời cho user chưa kiểm chứng.
- Không tự đánh dấu `Authentication.isAuthenticated=true` trong service; cơ chế provider phải xác minh credential.

Trong Spring Security Servlet khi dùng username/password, một chuỗi điển hình là:

~~~mermaid
sequenceDiagram
    participant C as HTTP client
    participant F as Authentication filter
    participant M as ProviderManager
    participant P as DaoAuthenticationProvider
    participant S as UserDetailsService
    participant D as DB / LDAP / user API
    C->>F: Username + password
    F->>M: UsernamePasswordAuthenticationToken (chưa xác thực)
    M->>P: authenticate(request)
    P->>S: loadUserByUsername(username)
    S->>D: Truy vấn account
    alt Tìm thấy account
        D-->>S: Account
        S-->>P: UserDetails
        P->>P: Kiểm trạng thái và PasswordEncoder.matches
        P-->>M: Authentication kết quả hoặc exception
    else Truy vấn thành công, không có account
        D-->>S: Không có bản ghi
        S-->>P: UsernameNotFoundException
        P-->>M: Mặc định BadCredentialsException
    else Kho không truy cập được
        D--xS: Timeout / connection failure
        S-->>P: Exception hạ tầng/đã chuyển đổi
        P-->>M: InternalAuthenticationServiceException
    end
~~~

Trong nhánh **tìm thấy**, nếu password sai thì vẫn thất bại: `UserDetailsService` trả đúng đối tượng không tự động cấp một lần đăng nhập thành công.

## 4. Ba nhóm exception khác nhau

### 4.1. `UsernameNotFoundException`: lookup hoàn tất, không định danh được user

Đây là tín hiệu của hợp đồng `UserDetailsService`. Chỉ dùng khi backend đã trả lời đủ đáng tin rằng key người dùng không tồn tại trong phạm vi tra cứu. Một truy vấn SQL thành công với 0 hàng có thể là trường hợp này.

Ví dụ Java **minh họa phương thức tích hợp**:

~~~java
@Override
public UserDetails loadUserByUsername(String username)
        throws UsernameNotFoundException {
    Account account = repository.findByUsername(username)
            .orElseThrow(() -> new UsernameNotFoundException(
                    "Account not found"));
    return toUserDetails(account);
}
~~~

Biến `repository` và hàm `toUserDetails` phải được định nghĩa bởi ứng dụng. Phương thức trên chỉ đúng nếu `findByUsername` **ném exception khi kho lỗi** và chỉ trả `Optional.empty()` khi truy vấn thành công nhưng không có account.

**Không đưa nguyên nhân “username nào không tồn tại” vào response client**, kể cả khi backend đang giữ `UsernameNotFoundException`. Việc phân biệt người dùng tồn tại qua lỗi hoặc thời gian phản hồi có thể tạo user enumeration.

### 4.2. `BadCredentialsException`: thông tin đăng nhập bị từ chối

`DaoAuthenticationProvider` kiểm password bằng `PasswordEncoder`. Password không khớp hash hợp lệ sẽ dẫn đến `BadCredentialsException`.

Ngoài ra, `AbstractUserDetailsAuthenticationProvider` **mặc định đặt `hideUserNotFoundExceptions=true`**: khi `UserDetailsService` ném `UsernameNotFoundException`, provider thường chuyển lỗi đó thành **`BadCredentialsException`**. Nhờ vậy người dùng bên ngoài không dễ phân biệt “username không tồn tại” với “password sai” chỉ qua class/thông báo lỗi bề mặt.

Hệ quả:

~~~text
Username không tồn tại
  -> UserDetailsService: UsernameNotFoundException
  -> DaoAuthenticationProvider mặc định: BadCredentialsException

Username tồn tại, password sai
  -> UserDetailsService: UserDetails
  -> DaoAuthenticationProvider: BadCredentialsException
~~~

**Cùng class lỗi cuối không có nghĩa cùng nguyên nhân gốc.** Trong debug nội bộ, có thể phân biệt bằng luồng truy vấn hoặc exception cause có kiểm soát, nhưng không xuất ra thông điệp chi tiết cho client.

### 4.3. `InternalAuthenticationServiceException`: nguồn xác thực gặp lỗi nghiêm trọng

Khi `UserDetailsService` ném một exception khác `UsernameNotFoundException` do DB/LDAP/HTTP client hỏng, `DaoAuthenticationProvider.retrieveUser(...)` có đường chuyển lỗi đó thành `InternalAuthenticationServiceException`. Nếu service chủ động ném `InternalAuthenticationServiceException`, provider truyền nó lên. Việc `UserDetailsService` trả `null` là vi phạm hợp đồng; provider cũng coi là lỗi dịch vụ.

Đây là tín hiệu: **không thể xác minh danh tính vì dịch vụ nền có vấn đề**, không phải người dùng đã nhập sai bằng chứng hoặc chắc chắn không có trong kho.

`InternalAuthenticationServiceException` là một `AuthenticationException`; trong `ProviderManager`, nhóm lỗi này có **nhánh dừng ngay**, để không tiếp tục hỏi provider sau hoặc parent như một cơ chế che giấu sự cố. Ngược lại, một `BadCredentialsException` thông thường có thể cho phép provider tiếp theo thử khi manager cấu hình nhiều provider.

**Không phải mọi lỗi đều được tạo trực tiếp dưới class `InternalAuthenticationServiceException`**: hệ thống có thể dùng `AuthenticationServiceException`, exception từ thư viện data hoặc error tùy biến ở các ranh giới khác nhau. Khi cần đo lường, phân loại theo **exception thực tế và nguyên nhân**, không chỉ một chuỗi thông báo.

### Bảng nhìn nhanh

| Sự kiện | Service/adapter nên làm gì? | Provider có thể trả gì? | Ý nghĩa nội bộ |
| --- | --- | --- | --- |
| Không có user, lookup thành công | `UsernameNotFoundException` | Thường `BadCredentialsException` theo cấu hình mặc định | Không tìm thấy account |
| User tồn tại, password sai | Trả `UserDetails` đúng | `BadCredentialsException` | Bằng chứng sai |
| DB timeout/connection refused | Ném lỗi hạ tầng hoặc `InternalAuthenticationServiceException` | `InternalAuthenticationServiceException` | Không thể xác minh do hạ tầng |
| `loadUserByUsername` trả `null` | Đây là bug hợp đồng | Lỗi dịch vụ, không thành công | Source trả dữ liệu không hợp lệ |
| User disabled/locked | Trả `UserDetails` đúng trạng thái | `DisabledException` / `LockedException` | Bị chặn bởi chính sách account |
| User hợp lệ, password đúng | Trả `UserDetails` chính xác | `Authentication` đã xác thực | Có thể chuyển sang authorization |

## 5. Tại sao phải tránh `catch (Exception) { throw new UsernameNotFoundException(...) }`?

Một anti-pattern phổ biến:

~~~java
// SAI: chuyển mọi lỗi thành "không có người dùng".
@Override
public UserDetails loadUserByUsername(String username) {
    try {
        return mapAccount(repository.findByUsername(username));
    }
    catch (Exception exception) {
        throw new UsernameNotFoundException("No user");
    }
}
~~~

Nếu DB hết connection, mạng đứt, LDAP trả 503 hay mapper gặp bug, code vẫn nói “không có user”. Điều này làm mất phân biệt “đã tìm thấy kết quả phủ định” với “không thể tìm kiếm”.

Các tác hại chính:

1. **Sai sự thật về danh tính:** account có thể tồn tại, nhưng hệ thống ghi nhận là không có.
2. **Che giấu sự cố:** metric “user not found” tăng, dashboard không phát hiện database outage, operator xử lý sai hướng.
3. **Fallback ngoài ý muốn:** nếu `ProviderManager` có nhiều provider cùng hỗ trợ kiểu token, kết quả `BadCredentialsException` do “ẩn user không tồn tại” có thể để một provider sau tiếp tục thử; chính sách xác thực của hệ thống có thể bị thay đổi khi DB bị lỗi.
4. **Khó phục hồi:** ứng dụng có thể cache negative lookup hoặc áp dụng chính sách “tạo mới tài khoản” dựa trên kết luận không có user, dù chỉ bị timeout.
5. **Khó debug:** exception gốc và stack trace bị mất nếu không giữ cause.
6. **Mất cơ hội báo động:** quy trình cảnh báo, retry, circuit breaker và health check không nhận đúng nhóm lỗi.

Cách sửa là **bắt ngoại lệ đủ hẹp**, bảo toàn cause và giữ phân biệt ở tầng vận hành:

~~~java
// Đoạn tích hợp minh họa: DB query trả Optional<Account>.
try {
    Account account = repository.findByUsername(username)
            .orElseThrow(() -> new UsernameNotFoundException(
                    "Account not found"));
    return mapAccount(account);
}
catch (DataAccessException ex) {
    throw new InternalAuthenticationServiceException(
            "Account repository unavailable", ex);
}
~~~

`DataAccessException` là nhóm exception thuộc Spring DAO; ví dụ này cần `spring-tx`/các dependency JDBC hoặc JPA phù hợp và import tương ứng. Nó không xử lý mọi kiểu lỗi hạ tầng: một HTTP/LDAP client có thể ném loại exception khác. Xác định rõ các loại exception của **nguồn dữ liệu bạn đang dùng**, thay vì catch mọi exception rồi giả định tất cả là mất kết nối.

**Chọn đúng thứ tự catch:** `UsernameNotFoundException` nằm ở nhánh nghiệp vụ của lookup; đừng vô tình quấn nó bằng catch quá rộng. Trong chương trình hoàn chỉnh dưới đây, ta dùng custom store exception để tránh phải thêm framework database.

## 6. Sai lệch phổ biến khi dùng Optional, SQL, LDAP và API

### 6.1. SQL/JPA

Một truy vấn `SELECT ... WHERE username = ?` đã chạy thành công và có **0 hàng** có thể được map sang `Optional.empty()`. Nhưng `SQLException` do kết nối bị từ chối, timeout, mạng không ổn định hoặc pool hết connection không có giá trị tương đương.

Ví dụ phân loại:

~~~text
SELECT trả 0 rows        -> không có bản ghi (nếu truy vấn đúng scope)
SELECT trả 1 row         -> có account, đọc dữ liệu
CannotGetJdbcConnection  -> lỗi truy cập DB
QueryTimeout             -> không có kết luận account tồn tại hay không
Data mapping bị lỗi      -> lỗi dữ liệu/hợp đồng, phải điều tra
~~~

Không sửa `DataAccessException` thành `Optional.empty()` chỉ để tránh ném lỗi lên controller.

### 6.2. LDAP/Active Directory

Một kết quả tìm kiếm hoàn tất với filter/base DN đúng và 0 entry có thể được coi là không tìm thấy. Mất kết nối LDAP, bind service credential thất bại, TLS negotiation lỗi, server trả unavailable hoặc referral không truy cập được **không chứng minh user không tồn tại**.

Cần chú ý namespace, base DN và quyền đọc: quyền thiếu có thể khiến lookup không đủ dữ liệu hoặc bị từ chối. Không âm thầm đổi “không được phép truy vấn” thành “không có account”.

### 6.3. Remote identity API

Ví dụ API danh tính:
- `200` với kết quả phù hợp → có user.
- `404` trong **hợp đồng endpoint tra cứu cụ thể** → có thể đại diện “không có user”, khi API đảm bảo 404 thực sự mang nghĩa đó.
- `401/403` từ upstream → authentication/permission của **ứng dụng gọi upstream** có vấn đề, không phải chứng cứ account người dùng không tồn tại.
- `429`, `500/502/503/504` hoặc timeout → không kết luận username không tồn tại.
- `200` nhưng schema/required fields lỗi → dữ liệu không đáng tin; phải báo lỗi hệ thống hoặc hợp đồng.

**Không mặc định mọi HTTP 404 có cùng ý nghĩa**: endpoint và gateway có thể dùng 404 cho route không tồn tại, tenant bị ẩn hoặc resource không lộ thông tin. Chỉ map sang `UsernameNotFoundException` khi hợp đồng API cho phép và request đã được thực hiện thành công trong đúng namespace.

### 6.4. Reactor/WebFlux hoặc CompletableFuture

Trong code reactive, `onErrorResume(error -> Mono.empty())` có thể biến timeout thành “lookup không có người dùng”. Tương tự, `exceptionally(error -> Optional.empty())` ở Java CompletableFuture có thể nuốt lỗi mạng. Giữ **empty** cho tra cứu thành công không có kết quả, **error** cho sự cố. Đây là nguyên tắc phân loại bất kể ứng dụng dùng Servlet hay Reactive.

## 7. Cách Spring Security che giấu “user có tồn tại không”

### 7.1. Mặc định hideUserNotFoundExceptions

`AbstractUserDetailsAuthenticationProvider` có thuộc tính `hideUserNotFoundExceptions`, mặc định `true`. Với cấu hình ấy, `UsernameNotFoundException` và password không khớp đều đi ra ngoài provider như `BadCredentialsException` thông thường.

Có thể thay thành `false`:

~~~java
DaoAuthenticationProvider provider = new DaoAuthenticationProvider();
provider.setHideUserNotFoundExceptions(false);
~~~

Đây là **đoạn tích hợp**; chỉ có ý nghĩa khi provider được cấu hình hoàn chỉnh với `UserDetailsService` và `PasswordEncoder`. Không nên bật `false` trong ứng dụng công khai chỉ để debug, vì khác biệt lỗi có thể hỗ trợ user enumeration.

**Điều không được hiểu sai:** che exception là biện pháp giảm lộ thông tin, không làm cho truy vấn database tự đáng tin hơn. Vẫn phải giữ nguyên nhóm lỗi dịch vụ khi kết nối hỏng. Che thông tin cho client và phân loại chính xác cho operator **có thể đồng thời đạt được**.

### 7.2. Thời gian phản hồi cũng có thể tiết lộ user

Ngay cả khi hai trường hợp cùng trả “Bad credentials”, đường chạy khác nhau có thể khác thời gian: có user phải kiểm hash thực, không có user có thể kết thúc sớm. `DaoAuthenticationProvider` có cơ chế giảm chênh lệch thời gian trong một số đường code bằng kiểm password với hash giả; đó là giảm rủi ro, **không bảo đảm thời gian hoàn toàn bằng nhau** qua cache, DB, network và môi trường.

Cần thêm rate limiting, cảnh báo brute-force và chính sách thông báo thống nhất. Đừng tự tạo secret hash cố định dễ đoán hoặc “sleep 500ms” rồi coi đó là giải pháp hoàn chỉnh.

### 7.3. Thông điệp gửi client và sự kiện nội bộ khác nhau

Một lỗi response công khai có thể chỉ nói:

> Không thể đăng nhập bằng thông tin đã cung cấp.

Trong khi hệ thống vận hành phân biệt:
- `BAD_CREDENTIALS`;
- `ACCOUNT_LOOKUP_MISS` (nội bộ, quyền truy cập hạn chế);
- `IDENTITY_STORE_UNAVAILABLE`;
- `ACCOUNT_DISABLED`;
- `IDENTITY_DATA_INVALID`.

Các mã nội bộ cần được chuẩn hóa và bảo vệ khỏi việc lộ danh tính, mật khẩu, SQL/JDBC URL hoặc thông tin thiết kế cụ thể. Các nhóm metric có thể dùng nhãn hữu hạn để tránh cardinality cao.

## 8. ProviderManager và nguy cơ fallback khi kho bị lỗi

`ProviderManager` duyệt danh sách `AuthenticationProvider` theo thứ tự. Khi provider ném `BadCredentialsException` thông thường, manager có thể tiếp tục thử provider sau; nếu provider sau thành công, kết quả thành công được dùng. `InternalAuthenticationServiceException` được xử lý theo nhánh dừng ngay để tránh cố xác thực tiếp bằng provider khác.

Ví dụ:

~~~text
P1: corporate-user-provider    -> LDAP/DB chính
P2: legacy-user-provider       -> kho cũ có một số username trùng

Nếu P1 truy vấn thành công: không có user
    -> UsernameNotFoundException
    -> mặc định BadCredentialsException
    -> P2 có thể được thử (tùy supports và cấu hình)

Nếu P1 mất kết nối nhưng code nhầm lỗi thành UsernameNotFoundException
    -> mặc định BadCredentialsException
    -> P2 cũng có thể được thử: chính sách fallback bị kích hoạt ngoài ý muốn

Nếu P1 mất kết nối và ném InternalAuthenticationServiceException
    -> ProviderManager dừng ngay
    -> không xác thực qua P2 như thể lookup thành công
~~~

**Hệ quả:** phân loại lỗi đúng không chỉ giúp log rõ ràng mà còn giúp giữ **chính sách xác thực**. Nếu hệ thống muốn phương án dự phòng thật sự khi một kho hỏng, cần thiết kế tường minh cách chuyển tuyến, điều kiện nhận diện cùng một subject, chính sách quyền và mức bảo đảm tương đương; không để một catch block vô tình quyết định.

Không cố ý ném `BadCredentialsException` cho lỗi database nhằm ép hệ thống “thử nhà cung cấp khác” nếu điều đó chưa được thiết kế và kiểm thử.

## 9. HTTP status: 401 không nhất thiết là “password sai”

`AuthenticationManager.authenticate(...)` là API Java: trả `Authentication` đã xác thực hoặc ném `AuthenticationException`. Nó **không tự trả HTTP status**.

Trong Servlet, `BasicAuthenticationFilter` và các thành phần xử lý failure/`AuthenticationEntryPoint` có thể bắt `AuthenticationException` và đưa đến phản hồi **401** cho HTTP Basic. Kể cả khi nguyên nhân gốc là lỗi kho tài khoản, cấu hình mặc định **không nhất thiết tự chuyển thành 503**.

Đối chiếu từng lớp:

| Lớp | Thấy gì? | Việc cần phân loại |
| --- | --- | --- |
| Database/LDAP/client | Có account, không có account hoặc lỗi truy cập | Kết quả nguồn gốc |
| `UserDetailsService` | `UserDetails`, `UsernameNotFoundException` hoặc lỗi hạ tầng | Bảo toàn phân biệt lookup và outage |
| `DaoAuthenticationProvider` | Auth success, `BadCredentialsException`, `InternalAuthenticationServiceException`... | Kiểm credential và chuyển exception |
| `ProviderManager` | Kết quả hoặc exception cuối; một số lỗi dừng ngay | Chính sách provider/fallback |
| Servlet auth filter/entry point | Phản hồi 401/redirect/custom error | Chính sách giao thức HTTP |
| Monitoring | Metric, log và traces an toàn | Phát hiện outage và điều tra riêng |

**Nguyên tắc khi trả status:** 401 là phù hợp cho thiếu/sai credential trong nhiều API; 503 có thể phù hợp cho **dịch vụ xác thực tạm thời không khả dụng** nếu thiết kế HTTP/security handler có nhánh xử lý tương ứng. Nhưng không tự suy ra status chỉ từ tên exception, và không trả 503 bằng một `@RestControllerAdvice` thông thường nếu lỗi đã xảy ra ở authentication filter **trước khi** controller được gọi.

Nếu cần phân biệt 503 ở tầng HTTP, hãy thiết kế tại đúng authentication entry point/failure handler/filter boundary, kiểm đường đi thực và cấu hình client retry để tránh thundering herd. Trong một số hệ thống, trả thông điệp công khai chung kết hợp metric nội bộ riêng là lựa chọn được quyết định theo chính sách an toàn.

## 10. Demo Java 17 chạy được với DaoAuthenticationProvider thật

Chương trình dưới đây cố tình không dùng DB hoặc web server. Một kho account trong bộ nhớ mô phỏng **ba trạng thái tra cứu**: tìm thấy, không tìm thấy, và không truy cập được. Sau đó `DaoAuthenticationProvider` thật kiểm `BCryptPasswordEncoder` và `ProviderManager` phân loại exception.

Điểm quan trọng: **provider và việc so khớp password là cơ chế thật của Spring Security**, còn “mạng database bị ngắt” là tình huống được mô phỏng bằng trạng thái `available=false`. Không đưa kho giả vào production.

### 10.1. Cấu trúc và Gradle

~~~text
account-store-errors-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/example/store/
    └── AccountStoreErrorsDemo.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'account-store-errors-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.security:spring-security-core:6.3.5'
    implementation 'org.springframework.security:spring-security-crypto:6.3.5'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'example.store.AccountStoreErrorsDemo'
}
~~~

Chạy khi có JDK 17+ và Gradle tương thích hoặc Gradle Wrapper. Dependency cố định để tái hiện ví dụ; ứng dụng thực nên sử dụng Spring Boot BOM cùng các bản vá bảo mật hiện hành.

### 10.2. Tệp Java hoàn chỉnh

`src/main/java/example/store/AccountStoreErrorsDemo.java`:

~~~java
package example.store;

import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;

import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.InternalAuthenticationServiceException;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;

public class AccountStoreErrorsDemo {

    record StoredAccount(String username, String passwordHash) {}

    // Giống sự cố connection/timeout của kho thật, không phải user missing.
    static final class StoreUnavailableException extends RuntimeException {
        StoreUnavailableException(String message) {
            super(message);
        }
    }

    static final class AccountStore {
        private final Map<String, StoredAccount> accounts =
                new ConcurrentHashMap<>();

        private volatile boolean available = true;

        AccountStore(PasswordEncoder encoder) {
            accounts.put("linh",
                    new StoredAccount(
                            "linh", encoder.encode("demo-password")));
        }

        void setAvailable(boolean available) {
            this.available = available;
        }

        Optional<StoredAccount> findByUsername(String username) {
            if (!available) {
                throw new StoreUnavailableException("Simulated outage");
            }
            // Optional.empty chỉ có nghĩa lookup thành công nhưng không có row.
            return Optional.ofNullable(accounts.get(username));
        }
    }

    static final class AccountUserDetailsService
            implements UserDetailsService {
        private final AccountStore store;

        AccountUserDetailsService(AccountStore store) {
            this.store = store;
        }

        @Override
        public UserDetails loadUserByUsername(String username)
                throws UsernameNotFoundException {
            try {
                StoredAccount account = store.findByUsername(username)
                        .orElseThrow(() -> new UsernameNotFoundException(
                                "User missing in account store"));

                return User.withUsername(account.username())
                        .password(account.passwordHash())
                        .authorities("reports.read")
                        .build();
            }
            catch (StoreUnavailableException ex) {
                // Giữ nguyên cause để operator điều tra nội bộ.
                throw new InternalAuthenticationServiceException(
                        "Account store unavailable", ex);
            }
        }
    }

    static void expectSuccess(AuthenticationManager manager) {
        Authentication input =
                UsernamePasswordAuthenticationToken.unauthenticated(
                        "linh", "demo-password");

        Authentication output = manager.authenticate(input);
        if (!output.isAuthenticated()
                || !"linh".equals(output.getName())) {
            throw new AssertionError("Unexpected result");
        }
        System.out.println("known-user => SUCCESS authenticated=true");
    }

    static void expectFailure(
            AuthenticationManager manager,
            String label,
            String username,
            String password,
            Class<? extends AuthenticationException> expected) {

        Authentication input =
                UsernamePasswordAuthenticationToken.unauthenticated(
                        username, password);

        try {
            manager.authenticate(input);
            throw new AssertionError(label + " unexpectedly succeeded");
        }
        catch (AuthenticationException failure) {
            if (!expected.isInstance(failure)) {
                throw new AssertionError(
                        label + " wrong exception: "
                        + failure.getClass().getSimpleName(), failure);
            }
            // Chỉ in loại lỗi, tuyệt đối không in mật khẩu hoặc raw request.
            System.out.println(label + " => "
                    + failure.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) {
        PasswordEncoder encoder = new BCryptPasswordEncoder();
        AccountStore store = new AccountStore(encoder);

        UserDetailsService users = new AccountUserDetailsService(store);
        DaoAuthenticationProvider provider =
                new DaoAuthenticationProvider();
        provider.setUserDetailsService(users);
        provider.setPasswordEncoder(encoder);

        // Mặc định hideUserNotFoundExceptions = true.
        AuthenticationManager manager =
                new ProviderManager(List.of(provider));

        expectSuccess(manager);

        expectFailure(manager, "unknown-user",
                "khong-ton-tai", "anything",
                BadCredentialsException.class);

        expectFailure(manager, "wrong-password",
                "linh", "not-the-password",
                BadCredentialsException.class);

        store.setAvailable(false);
        expectFailure(manager, "store-down",
                "linh", "demo-password",
                InternalAuthenticationServiceException.class);
    }
}
~~~

**Giải thích từng điểm quan trọng của mã:**

1. `AccountStore.findByUsername(...)` trả `Optional.empty()` **chỉ khi store đang available** và key không có trong map. Khi `available=false`, method ném `StoreUnavailableException`.
2. `AccountUserDetailsService` phân biệt hai nhánh: không có account → `UsernameNotFoundException`, lỗi kho → `InternalAuthenticationServiceException` với cause giữ lại.
3. `DaoAuthenticationProvider` chuẩn dùng `PasswordEncoder` thật để so credential. Không có token “authenticated” nào được code tự cấp từ username.
4. `ProviderManager` chỉ có một provider; các kết quả thất bại không thể bị provider khác làm thay đổi. Với multi-provider phải thiết kế policy riêng.
5. `expectFailure` chỉ xác minh exception class. Chương trình **không in username/password hash/credential**, không ghi log của store giả.
6. `UserDetailsService` có thể ném runtime `InternalAuthenticationServiceException` dù method interface chỉ khai báo `UsernameNotFoundException`: cả hai đều là exception unchecked trong Java.

### 10.3. Chạy chương trình và diễn giải kết quả

~~~bash
gradle run --quiet
~~~

Nếu đã thiết lập Gradle Wrapper, dùng `./gradlew run --quiet` (trên Windows PowerShell: `.\gradlew.bat run --quiet`).

Các dòng do `System.out.println` in ra, không tính những log của build tool hoặc thư viện:

~~~text
known-user => SUCCESS authenticated=true
unknown-user => BadCredentialsException
wrong-password => BadCredentialsException
store-down => InternalAuthenticationServiceException
~~~

Kết quả cho thấy cùng một credential request type nhưng khác **nguyên nhân dữ liệu** và **exception** cuối. Ở lỗi unknown user, default `hideUserNotFoundExceptions=true` làm bề mặt giống password sai. Ở lỗi kho, provider không có bằng chứng để kết luận user không tồn tại, nên phát tín hiệu lỗi dịch vụ.

**Điều demo chưa làm:** không có mạng thật, SQL pool, retry, TLS, servlet filters, HTTP status, session hoặc nhiều provider. Chạy console này để học lớp `UserDetailsService`/provider trước; sau đó cần integration test ở ứng dụng thật cho ranh giới DB, filter, entry point và monitoring.

## 11. Test quan trọng ở cấp provider, DB adapter và HTTP

Một bộ test tốt phải có **test dữ liệu** và **test luồng xác thực**. Chỉ assert HTTP 401 trong cả hai tình huống không giúp biết hệ thống đã phân loại lỗi đúng hay chưa.

| Case | Giả lập/fixture | Kỳ vọng ở adapter | Kỳ vọng ở manager |
| --- | --- | --- | --- |
| Account tồn tại, đúng password | DB có row và hoạt động | Trả `UserDetails` | Success `Authentication` |
| Account không tồn tại | Query thành công và 0 row | `UsernameNotFoundException` | `BadCredentialsException` mặc định |
| Password sai | Query có row và hash đúng | Trả `UserDetails` | `BadCredentialsException` |
| Connection refused | Store throws connection exception | Lỗi dịch vụ, cause được giữ | `InternalAuthenticationServiceException` |
| Query timeout | Store throws timeout | Lỗi dịch vụ, không biến thành empty | Lỗi dịch vụ |
| Repository trả null trái contract | Bug trong adapter | Bị phát hiện | Không được trả success |
| Account locked/disabled | Row có trạng thái khóa | Trả `UserDetails` thể hiện trạng thái | `LockedException`/`DisabledException` |
| Pool cạn hoặc LDAP unavailable | Nguồn xác thực lỗi | Không có quyết định tồn tại user | Lỗi dịch vụ và metric |
| Có P2 fallback | P1 gặp lỗi kho | P1 không che thành bad credentials | P2 không được bypass lỗi dừng ngay |
| HTTP Basic thiếu credential | Không gọi lookup | Không có lookup bắt buộc | Endpoint bảo vệ thường 401 |
| HTTP Basic store down | Lỗi phát sinh trong filter | Adapter ném lỗi dịch vụ | HTTP tùy entry point; metric phải ghi outage |

### 11.1. Test adapter trực tiếp

Ví dụ pseudo-assertions cho repository đã khai báo:

~~~java
// Các biến store, users, manager thuộc fixture test.
store.setAvailable(true);

assertThrows(UsernameNotFoundException.class,
        () -> users.loadUserByUsername("missing"));

store.setAvailable(false);

assertThrows(InternalAuthenticationServiceException.class,
        () -> users.loadUserByUsername("linh"));
~~~

Đây là **đoạn tích hợp dùng JUnit 5**: cần import `org.junit.jupiter.api.Assertions.assertThrows` và fixture phù hợp; không phải chương trình độc lập. Ở adapter, test cả exception cause để bảo toàn thông tin chẩn đoán; ở public HTTP thì không gửi cause ra ngoài.

### 11.2. Test manager thực sự

Ngoài kiểm exception adapter, cần test provider:

~~~java
// Kho hoạt động, nhưng username không tồn tại:
assertThrows(BadCredentialsException.class,
        () -> manager.authenticate(
                UsernamePasswordAuthenticationToken.unauthenticated(
                        "missing", "password")));

// Mất kho:
store.setAvailable(false);
assertThrows(InternalAuthenticationServiceException.class,
        () -> manager.authenticate(
                UsernamePasswordAuthenticationToken.unauthenticated(
                        "linh", "password")));
~~~

Các assertions trên cũng là **đoạn JUnit tích hợp**. Demo `main` hoàn chỉnh ở mục 10 đã thực hiện logic kiểm tương đương mà không cần JUnit.

### 11.3. Test HTTP riêng, không suy diễn từ exception

Nếu application sử dụng Spring Security Servlet HTTP Basic, làm integration test (ví dụ `MockMvc` với security filters bật) để đo HTTP status mà entry point thực sự trả. Cùng một `InternalAuthenticationServiceException` trong provider có thể dẫn tới phản hồi 401 theo Basic entry point mặc định, hoặc mã khác nếu ứng dụng có cơ chế phân loại riêng. Ghi nhận hành vi hiện tại và kiểm thử đúng chính sách công khai.

Không dùng test `@WithMockUser` rồi kết luận database exception đã được xử lý: annotation đặt user giả vào security context, bỏ qua bước `UserDetailsService` và `DaoAuthenticationProvider` cần kiểm.

### 11.4. Test khi có nhiều instance và nhiều nguồn user

Giả lập database down trong một replica, LDAP timeout trong replica khác và thay đổi kết nối lúc request đang xác thực. Khẳng định:
- Không có instance nào tạo kết quả authenticated từ dữ liệu không đáng tin.
- Không nhầm lỗi hạ tầng thành account missing.
- Fallback chỉ xảy ra trong trường hợp được chính sách cho phép.
- Các metric giúp operator phân biệt outage với việc nhiều user nhập sai.
- Cache không trả user cũ quá hạn khi chính sách đòi dữ liệu mới; phải có cách invalidation/stale-policy cụ thể.

## 12. Observability: phân biệt sự cố mà không tiết lộ người dùng

Để vận hành, cần ít nhất một số thông tin:

| Nhóm sự kiện | Metric/log nội bộ nên có | Không nên ghi |
| --- | --- | --- |
| Lookup miss | `account_lookup_outcome=NOT_FOUND` | Raw username/PII nếu không cần |
| Store unavailable | `account_lookup_outcome=STORE_UNAVAILABLE`, loại timeout/connection, dependency name | Connection string có credential |
| Bad password | `auth_outcome=BAD_CREDENTIALS` | Password, password hash, Basic/Bearer header |
| Account disabled | `auth_outcome=ACCOUNT_DISABLED` | Nội dung nhạy cảm của hồ sơ |
| Success | `auth_outcome=SUCCESS`, cơ chế, elapsed time | Toàn bộ `Authentication.toString()` |
| Data contract violation | `account_lookup_outcome=INVALID_DATA`, lỗi schema được chuẩn hóa | Response body nhạy cảm từ upstream |

**Đừng ghi nhãn metric theo username** để tránh cardinality lớn và rò rỉ danh tính. Nếu cần audit theo principal, dùng định danh đã kiểm chứng/pseudonym phù hợp, giữ quyền truy cập và retention theo chính sách.

### 12.1. Đặt cảnh báo theo nhóm lỗi đúng

Tỷ lệ `STORE_UNAVAILABLE` tăng trong vài phút có thể cho thấy database/LDAP/API danh tính bị hỏng. Tỷ lệ `BAD_CREDENTIALS` tăng có thể cho thấy user nhập sai hoặc hành vi brute force. Hai hiện tượng đòi hướng xử lý khác nhau.

Nếu code biến tất cả thành `UsernameNotFoundException`, metric và incident response mất ý nghĩa. Thiết kế dashboard theo outcome riêng từ tầng adapter, nhưng giữ phản hồi client nhất quán để giảm user enumeration.

### 12.2. Correlation ID và exception cause

Có thể gắn request/correlation ID an toàn từ gateway tới service và provider logs. Khi ghi lỗi kho, giữ nguyên **exception cause** trong log có kiểm soát, tránh in secret hoặc query chứa PII. Trả cho client thông điệp chung, không đẩy stack trace hay tên server nội bộ ra ngoài.

Nếu gọi remote identity API, thêm timeout có hạn, retry/circuit breaker chọn lọc, exponential backoff và giám sát dependency. Retry không được biến thất bại cuối cùng thành `Optional.empty()`; nếu exhausted, vẫn là lỗi dịch vụ.

## 13. Đọc log theo trường hợp thực tế

### Tình huống A — Không tìm thấy user

~~~text
request=R-101
store.lookup outcome=NOT_FOUND
provider.failure=BadCredentialsException
http.response=401  (ví dụ cấu hình Basic)
~~~

**Giải thích:** kho có kết quả âm đáng tin; service ném `UsernameNotFoundException` nhưng provider che ở bề mặt. Log nội bộ có thể thấy miss; client không cần biết tên user có tồn tại hay không.

### Tình huống B — Password sai

~~~text
request=R-102
store.lookup outcome=FOUND
provider.failure=BadCredentialsException
http.response=401
~~~

**Giải thích:** khác A ở **kết quả lookup nội bộ**, nhưng kết quả xác thực gửi client có thể giống nhau.

### Tình huống C — Kho tài khoản bị lỗi

~~~text
request=R-103
store.lookup outcome=STORE_UNAVAILABLE
provider.failure=InternalAuthenticationServiceException
http.response=<phụ thuộc cấu hình failure/entry point>
dependency_alert=IDENTITY_STORE_UNAVAILABLE
~~~

Đây là **dấu vết minh họa có chủ đích**, không phải format log mặc định. Nếu ứng dụng trả 401 cho cả lỗi hệ thống, log/metric vẫn phải phân loại sự cố riêng; nếu thiết kế trả 503, kiểm đường đi filter và chính sách retry.

**Không kết luận:** một request 401 nghĩa là user không tồn tại, hoặc một HTTP 500/503 nghĩa password sai. HTTP status là lớp biểu diễn; nguyên nhân gốc nằm ở tầng account lookup/provider.

## 14. Những lỗi thiết kế cần tránh

1. **Catch mọi exception rồi ném `UsernameNotFoundException`.** Che outage thành kết quả không tìm thấy, làm sai fallback và monitoring.
2. **Trả `null` khi truy vấn lỗi.** Vi phạm hợp đồng `UserDetailsService` và vẫn không giúp xác thực an toàn.
3. **Trả user mặc định/guest có password cố định khi DB down.** Cho phép bypass và cấp quyền không có nguồn tin cậy.
4. **Trả `Optional.empty()` khi timeout.** Đánh đồng “không có” với “chưa thể biết”.
5. **Lấy HTTP 404 từ API danh tính làm bằng chứng vĩnh viễn mà không xét hợp đồng.** Có thể là route lỗi, tenant ẩn, upstream không được phép truy cập.
6. **Bật `setHideUserNotFoundExceptions(false)` trên sản phẩm công khai để dễ debug.** Có thể tiết lộ user enumeration.
7. **Trả nguyên exception message/cause qua HTTP.** Lộ thông tin nội bộ, username, SQL, network.
8. **Tin rằng database down luôn trả HTTP 503.** Filter/entry point có thể trả 401 hoặc response khác; phải cấu hình/test.
9. **Đo số lượng đăng nhập lỗi chỉ bằng HTTP 401.** Trộn thiếu credential, sai mật khẩu và outage theo một chỉ số.
10. **Dùng `BadCredentialsException` để đại diện lỗi kết nối.** Có thể khiến `ProviderManager` tiếp tục fallback ngoài dự kiến.
11. **Tin cache user cũ là bằng chứng kết nối nguồn danh tính hiện tại vẫn tốt.** Cache hit có thể che outage, và dữ liệu account có thể đã thay đổi.
12. **Chỉ test account not found, không test timeout/pool exhausted.** Bỏ sót nhánh lỗi quan trọng nhất.
13. **Có nhiều provider cùng username nhưng không định nghĩa realm và thứ tự.** Một kho có thể xác thực thay kho khác theo chính sách không mong muốn.
14. **Cố retry vô hạn khi nguồn danh tính down.** Có thể làm quá tải và mở rộng sự cố; áp dụng timeout, retry có giới hạn, circuit breaker.
15. **Thay root cause bằng message chung mà không log an toàn.** Operator không có dấu vết để sửa lỗi.
16. **Bỏ phân quyền sau authentication.** Dù user đúng mật khẩu, endpoint vẫn phải kiểm authority/quyền cụ thể.

## 15. Câu hỏi tự kiểm tra

**Câu 1:** `UserDetailsService` trả `Optional.empty()` khi database query hoàn tất với 0 row. Nên làm gì?  
**Trả lời:** Map sang `UsernameNotFoundException` nếu username/tenant đã tra đúng phạm vi và kết quả có nghĩa chính xác là không có account.

**Câu 2:** Cùng query đó bị `CannotGetJdbcConnectionException`. Có được ném `UsernameNotFoundException` để tiện xử lý không?  
**Trả lời:** Không. Không truy cập được database không nói gì về sự tồn tại của account. Giữ lỗi hạ tầng hoặc chuyển thành `InternalAuthenticationServiceException` có cause.

**Câu 3:** Vì sao username không tồn tại và password sai thường cùng ra `BadCredentialsException`?  
**Trả lời:** `hideUserNotFoundExceptions=true` là mặc định của provider username/password, giúp hạn chế tiết lộ account qua lỗi công khai. Đây là che thông tin ở tầng xác thực, không làm mất khả năng phân biệt nguyên nhân trong tầng vận hành.

**Câu 4:** Store báo timeout nhưng code catch `Exception` rồi ném `UsernameNotFoundException`. Nếu có provider đăng nhập legacy sau đó, điều gì nguy hiểm?  
**Trả lời:** Lỗi có thể bị che thành `BadCredentialsException` và `ProviderManager` cho thử provider tiếp, vô tình thay đổi chính sách fallback. Lỗi dịch vụ phù hợp phải giữ trạng thái “không thể xác thực” và nhánh dừng.

**Câu 5:** Lỗi kho làm provider ném `InternalAuthenticationServiceException`. Có chắc client nhận HTTP 503 không?  
**Trả lời:** Không. Filter, entry point và failure handler quyết định response; HTTP Basic mặc định có thể trả 401 cho `AuthenticationException`. Cần test nếu sản phẩm đòi status khác.

**Câu 6:** Vì sao không ghi raw username/password trong log khi cần phân biệt user missing và store down?  
**Trả lời:** Outcome, request ID và loại lỗi đã đủ hỗ trợ triage. Credential và PII trong log gây rủi ro; dùng mã nội bộ, masking/hashed identifier có chính sách nếu cần.

**Câu 7:** Kho trả một row nhưng `enabled=false`. Có phải “user not found” không?  
**Trả lời:** Không. Account tồn tại nhưng bị chặn bởi trạng thái, thường dẫn tới `DisabledException`. Không nên xóa thông tin trạng thái để giả vờ không có account ở tầng service.

**Câu 8:** Test `@WithMockUser` chạy xanh có chứng minh adapter DB phân loại lỗi đúng không?  
**Trả lời:** Không. Nó bypass đường `UserDetailsService` và `DaoAuthenticationProvider`; phải test adapter/provider với các lỗi truy vấn thực tế hoặc fault injection.

**Câu 9:** Remote identity API trả 403 cho service đang truy vấn. Đó có phải user không tồn tại?  
**Trả lời:** Không. Thường là quyền/trạng thái xác thực của client gọi upstream. Chỉ một lookup được thực hiện đúng quyền và trả kết quả đáng tin mới cho phép kết luận absence.

**Câu 10:** Một response công khai giống nhau cho thiếu user, sai password và kho down có nhất thiết là sai?  
**Trả lời:** Không nhất thiết; một số chính sách cố ý che khác biệt. Nhưng **metrics, logging an toàn, retry và phân loại exception nội bộ** vẫn phải giữ đúng, nếu không sẽ che sự cố hoặc khiến fallback sai.

## 16. Checklist khi tích hợp kho tài khoản thật

Trước khi đưa `UserDetailsService` vào authentication flow:

- **Chìa khóa tra cứu:** username/tenant/realm được xác định duy nhất và tin cậy chưa?
- **Lookup thành công:** có phân biệt rõ 0 row với lỗi dữ liệu không?
- **Hợp đồng nguồn:** DB/LDAP/identity API báo timeout, 401/403/429/503 và schema error như thế nào?
- **Exception adapter:** chỉ ném `UsernameNotFoundException` khi xác nhận absence, giữ cause với lỗi hạ tầng chưa?
- **Provider mặc định:** `hideUserNotFoundExceptions` đang được đặt an toàn? Có kiểm timing/user enumeration chưa?
- **Fallback:** các provider khác hoặc parent manager có thể xác thực khi nguồn chính lỗi không?
- **Public HTTP:** response có tiết lộ user tồn tại, hạ tầng hoặc stack trace không? Test handler/filter thực tế chưa?
- **Observability:** có các outcome riêng cho lookup miss, bad credential, store unavailable, disabled không?
- **Resilience:** timeout/retry/circuit breaker có giới hạn và không chuyển outage thành empty không?
- **Cache:** nếu có `UserCache`, có policy stale data, eviction và invalidation khi account đổi không?
- **Authorization:** authentication success còn được kiểm authority/tenant/resource theo nghiệp vụ không?
- **Kiểm thử:** có đủ case missing, wrong password, locked/disabled, DB down, timeout, wrong mapping, multi-provider và cache chưa?

**Điều phải ghi nhớ:** **“Không có người dùng” là kết luận của một lần tra cứu thành công; “lỗi kết nối” là việc chưa thể đưa ra kết luận.** Spring Security có thể cố ý che “user missing” thành `BadCredentialsException` để bảo vệ thông tin tài khoản, nhưng code ứng dụng phải giữ nguyên khác biệt với lỗi dịch vụ. Chỉ khi phân loại đúng, hệ thống mới có thể xác thực an toàn, quan sát đúng tình trạng vận hành và không tự thay đổi chính sách khi kho danh tính gặp sự cố.

### Tài liệu tham khảo

- Spring Security — `DaoAuthenticationProvider`: https://docs.spring.io/spring-security/reference/6.3/servlet/authentication/passwords/dao-authentication-provider.html
- Spring Security — `UserDetailsService`: https://docs.spring.io/spring-security/reference/6.3/servlet/authentication/passwords/user-details-service.html
- Spring Security — `AbstractUserDetailsAuthenticationProvider` Javadoc: https://docs.spring.io/spring-security/site/docs/6.3.10/api/org/springframework/security/authentication/dao/AbstractUserDetailsAuthenticationProvider.html
- Spring Security — `InternalAuthenticationServiceException` Javadoc: https://docs.spring.io/spring-security/site/docs/6.3.10/api/org/springframework/security/authentication/InternalAuthenticationServiceException.html
- Spring Security — `AuthenticationManager` / `ProviderManager`: https://docs.spring.io/spring-security/reference/6.3/servlet/authentication/architecture.html
- Spring Security — source `DaoAuthenticationProvider`: https://github.com/spring-projects/spring-security/blob/6.3.5/core/src/main/java/org/springframework/security/authentication/dao/DaoAuthenticationProvider.java
