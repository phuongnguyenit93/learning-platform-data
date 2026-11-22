# Manager cha và điều kiện chuyển tiếp khi manager con không xử lý được

## Mục tiêu và bối cảnh

Trong Spring Security, một `AuthenticationManager` nhận yêu cầu xác thực (đối tượng `Authentication`) và trả về danh tính đã xác thực hoặc ném `AuthenticationException`. Implementation phổ biến nhất là `ProviderManager`: nó lần lượt hỏi các `AuthenticationProvider`. Một `ProviderManager` còn có thể khai báo **manager cha** (`parent AuthenticationManager`) để xử lý những yêu cầu mà manager con chưa trả được kết quả thành công.

Bài này trả lời chính xác **khi nào manager con gọi manager cha, khi nào dừng ngay, kết quả hoặc ngoại lệ nào được trả về**. Đây là cơ chế điều phối bộ máy xác thực, không phải quy tắc kế thừa role hay tự động đổi sang security filter chain khác.

Sau bài học, bạn có thể:

1. Phân biệt `AuthenticationManager`, `ProviderManager`, `AuthenticationProvider` và quan hệ cha–con giữa các manager.
2. Theo dõi cách `supports(Class<?>)`, giá trị `null`, authentication thành công và các nhóm `AuthenticationException` ảnh hưởng đến luồng xử lý.
3. Hiểu tại sao **`BadCredentialsException` từ provider con vẫn có thể được manager cha xử lý tiếp**, nhưng `AccountStatusException` và `InternalAuthenticationServiceException` dừng ngay.
4. Dự đoán kết quả khi cha thành công, cha báo `ProviderNotFoundException`, hoặc cả hệ thống không có provider xử lý.
5. Cấu hình một `ProviderManager` có parent, thử các nhánh điều khiển bằng ví dụ Java 17+ và tránh cấu hình fallback vô tình cho phép xác thực sai miền danh tính.

Phạm vi là Spring Security 6.x / Spring Boot 3.x, đặc biệt cách `ProviderManager.authenticate(...)` hoạt động. Hành vi chính được mô tả dựa trên hợp đồng API và implementation `ProviderManager`; các `AuthenticationManager` tự viết có thể có logic khác.

## 1. Mô hình cha–con trong bộ máy xác thực

Ba thành phần cần phân biệt:

| Thành phần | Trách nhiệm | Ví dụ |
| --- | --- | --- |
| `AuthenticationManager` | Giao diện nhận `authenticate(Authentication)`, trả `Authentication` đã xác thực hoặc ném ngoại lệ | `ProviderManager`, manager tự viết |
| `AuthenticationProvider` | Kiểm tra một loại token hoặc phương thức xác thực cụ thể; khai báo `supports(Class<?>)` | `DaoAuthenticationProvider`, custom API-key provider |
| `ProviderManager` | Chọn và thử các provider theo thứ tự; tùy chọn chuyển yêu cầu sang một `AuthenticationManager` cha | Manager cho một vùng đăng nhập riêng |

Sơ đồ một cây manager đơn giản:

~~~text
Authentication request
         |
         v
  ProviderManager CHILD
    |-- Provider #1: supports? -> authenticate(...)
    |-- Provider #2: supports? -> authenticate(...)
    |-- ...
    |
    +-- Nếu chưa có kết quả hợp lệ
          |
          v
    AuthenticationManager PARENT
          |
          +-- ProviderManager khác (nếu parent cũng là ProviderManager)
          |      |-- Parent provider A
          |      +-- Parent provider B
          |
          +-- Kết quả thành công HOẶC AuthenticationException
~~~

`parent` là một thuộc tính **tùy chọn** của `ProviderManager`. Nó có thể là một `ProviderManager` khác hoặc một implementation `AuthenticationManager` bất kỳ. Việc một ứng dụng có nhiều HTTP security chain không tự bảo đảm rằng mọi chain đều có một parent chung; phải căn cứ vào cấu hình manager thực sự.

Cách khởi tạo tường minh:

~~~java
AuthenticationManager parent =
    new ProviderManager(List.of(sharedProvider));

ProviderManager child =
    new ProviderManager(List.of(localProvider), parent);
~~~

Đây là đoạn minh họa đặt trong một phương thức có hai `AuthenticationProvider` hợp lệ là `sharedProvider` và `localProvider`. Constructor nhận danh sách provider của con và manager cha. Ví dụ chạy đầy đủ có ở mục 5.

**Đừng nhầm:** manager cha–con **khác** quan hệ class inheritance, quan hệ parent/child `ApplicationContext`, và khác việc `FilterChainProxy` chọn `SecurityFilterChain`. Một request HTTP thường chỉ được chain đầu tiên khớp xử lý; fallback sang parent trong chain đã chọn không tự chuyển request sang chain thứ hai.

## 2. Hợp đồng của từng AuthenticationProvider

Khi nhận một `Authentication` đầu vào, `ProviderManager` đi theo thứ tự danh sách `providers`. Với mỗi provider:

1. Gọi `provider.supports(authentication.getClass())`. Nếu `false`, bỏ qua provider; **không gọi** `authenticate(...)` của provider đó.
2. Nếu `true`, gọi `provider.authenticate(authentication)`. Điều này chỉ có nghĩa provider có thể đánh giá thêm, **chưa phải cam kết sẽ xác thực được instance cụ thể**.
3. Provider có thể trả một `Authentication` **khác `null`**: manager coi đây là kết quả xác thực, dừng thử provider tiếp theo và **không gọi parent**.
4. Provider có thể trả `null`: “không thể quyết định/xử lý request này”; manager chuyển sang provider kế tiếp. Nếu hết danh sách và vẫn không có kết quả, parent (nếu có) được thử.
5. Provider có thể ném `AuthenticationException`: cách tiếp tục tùy loại ngoại lệ, xem mục 3.

Điểm dễ nhầm: `supports(...) == true` không loại trừ khả năng `authenticate(...)` trả `null`. Đây là cơ chế được ghi trong JavaDoc của `AuthenticationProvider`.

### Kết quả khác null có nghĩa gì?

Provider phải chỉ trả một `Authentication` được đánh dấu xác thực sau khi đã **kiểm chứng bằng chứng hợp lệ**. Khi manager nhận kết quả khác null, nó không gọi các provider sau hoặc manager cha để “xác thực lần nữa”. Không có khái niệm “parent luôn phải phê duyệt thành công của child”. Nếu một provider trả token đã xác thực sai, vấn đề nằm ở implementation/chính sách trust của provider đó.

`ProviderManager` còn có thể sao chép details từ token đầu vào sang kết quả thuộc `AbstractAuthenticationToken` nếu kết quả chưa có details, và theo mặc định xóa credentials nhạy cảm trên kết quả thành công nếu nó triển khai `CredentialsContainer`. Đây là hành vi của `ProviderManager`, không chứng minh việc parent bắt buộc được gọi.

## 3. Điều kiện thật sự để gọi manager cha

Điều kiện trung tâm trong implementation có thể diễn giải thành:

~~~text
Nếu result vẫn null sau khi thử provider của child
    VÀ child có parent:
        thử parent.authenticate(originalAuthentication)
~~~

Đây là **mô tả thuật toán**, không phải đoạn Java được sao chép từ thư viện. Điểm quan trọng là `result == null` sau vòng lặp, **không phải** “chỉ khi tất cả provider đều `supports == false`”.

Các trường hợp dẫn đến `result == null` bao gồm:

- Không có provider của child nào hỗ trợ class token.
- Một hay nhiều provider hỗ trợ token, nhưng tất cả trả `null`.
- Một hay nhiều provider ném `AuthenticationException` loại có thể tiếp tục; sau đó không provider nào trả thành công.
- Kết hợp các trường hợp trên: một provider trả null, provider khác thất bại bằng ngoại lệ thường, rồi không có kết quả.

Vì vậy, câu “parent chỉ được gọi nếu không provider nào của child hỗ trợ token” là **quá hẹp**. Cũng không đúng khi nói “child thất bại thì chắc chắn luôn gọi parent”: có các ngoại lệ làm dừng ngay, và child có thể không được cấu hình parent.

### 3.1. Ngoại lệ thường: ghi nhận rồi tiếp tục

`BadCredentialsException`, một `AuthenticationException` thông thường, có thể xảy ra nếu provider con cho rằng username/password không đúng. Trong `ProviderManager`, ngoại lệ thường được lưu vào biến “lỗi cuối cùng”, nhưng vòng lặp **tiếp tục thử provider sau**; nếu không có provider con nào thành công thì có thể thử parent.

Điều này có hệ quả quan trọng:

~~~text
child provider: BadCredentialsException
child providers còn lại: không thành công
parent manager: thành công
=> kết quả cuối cùng: XÁC THỰC THÀNH CÔNG
~~~

Nếu provider sau hoặc parent thành công thì lỗi trước đó không quyết định kết quả cuối. Cơ chế này hữu ích khi các provider thực sự đại diện những nguồn xác thực hợp lệ có thể thay thế nhau; nó cũng có thể tạo lỗ hổng nếu parent là một “cửa sau” chấp nhận credentials mà child có chủ đích từ chối.

**Không sử dụng `BadCredentialsException` với kỳ vọng mặc định sẽ ngăn mọi fallback.** Hãy thiết kế miền thông tin đăng nhập, loại token và phạm vi manager rõ ràng nếu không được phép thử nguồn khác.

### 3.2. Ngoại lệ dừng ngay: AccountStatusException

Những exception kế thừa `AccountStatusException` (ví dụ `DisabledException`, `LockedException`, `AccountExpiredException` và `CredentialsExpiredException`) khiến `ProviderManager` **ném ngay**. Các provider còn lại trong child không được gọi và **manager cha cũng không được thử**.

Ý nghĩa: khi đã biết tài khoản bị khóa hoặc bị vô hiệu hóa, không được tiếp tục thử provider khác như thể đây chỉ là “không quyết định được”. Không nên dùng giả `LockedException` làm mẹo điều khiển routing; nó có ý nghĩa nghiệp vụ riêng về trạng thái account.

### 3.3. Ngoại lệ dừng ngay: InternalAuthenticationServiceException

`InternalAuthenticationServiceException` cũng khiến `ProviderManager` dừng và ném ngay. Ví dụ nguồn danh tính gặp sự cố nội bộ không thể phân loại thành tài khoản sai/missing. Việc cố coi lỗi dịch vụ xác thực là tín hiệu “được chuyển tiếp tự do” có thể biến sự cố thành cơ chế bypass.

Các loại `RuntimeException` không thuộc `AuthenticationException` nói chung cũng không phải cơ chế fallback hợp lệ của `ProviderManager`; đừng trông đợi manager sẽ nuốt mọi lỗi lập trình rồi gọi parent.

### 3.4. Bảng quyết định ở child

| Hành vi của child | Còn thử child provider kế? | Thử parent nếu đã hết child provider? |
| --- | --- | --- |
| `supports(...) == false` | Có, bỏ qua provider đó | Có, nếu chưa có kết quả và đã cấu hình parent |
| `supports(...) == true`, `authenticate(...) == null` | Có | Có, nếu vẫn chưa có kết quả |
| Provider trả `Authentication` khác null | Không | **Không** |
| Provider ném `BadCredentialsException` hoặc `AuthenticationException` thông thường | Có | Có, nếu không provider nào thành công |
| Provider ném `AccountStatusException` | **Không** | **Không** |
| Provider ném `InternalAuthenticationServiceException` | **Không** | **Không** |
| Lỗi lập trình không phải `AuthenticationException` | Không có quy tắc fallback | Không được mặc định kỳ vọng parent chạy |

Khi có nhiều provider, “provider kế” nghĩa là **những provider còn lại theo thứ tự và có hỗ trợ class token**, không phải mọi provider đều được gọi `authenticate`.

## 4. Sau khi gọi parent, hệ thống trả kết quả gì?

Parent được gọi với `Authentication` đầu vào ban đầu của child. Nó có thể có các provider riêng và thậm chí có parent khác, tạo thành một cây nhiều cấp; nên thiết kế cấu hình không tạo vòng lặp.

Các kết quả cần phân biệt:

| Kết quả của parent | Kết quả từ child ProviderManager |
| --- | --- |
| Parent trả `Authentication` khác null | **Thành công**, trả authentication đó; lỗi bình thường trước đó của child bị bỏ qua |
| Parent ném `BadCredentialsException` hoặc `AuthenticationException` khác | Khi không có kết quả thành công, ngoại lệ của parent được dùng làm lỗi cuối và ném ra |
| Parent ném `ProviderNotFoundException` | Trong implementation `ProviderManager`, exception loại này từ parent được bỏ qua để giữ ngoại lệ đã có ở child (nếu có) |
| Parent cũng không có provider phù hợp và child chưa ghi nhận lỗi nào | Kết thúc bằng `ProviderNotFoundException` |
| Child không có parent, không provider nào thành công | Ném ngoại lệ xác thực cuối cùng, hoặc `ProviderNotFoundException` nếu không có ngoại lệ trước đó |

### 4.1. Chi tiết dễ bị bỏ sót: ProviderNotFoundException của parent

Giả sử một child provider hỗ trợ token nhưng ném `BadCredentialsException`. Parent lại không có provider nào xử lý được token và ném `ProviderNotFoundException`. Với `ProviderManager` tiêu chuẩn, lỗi “không tìm thấy provider” từ parent **không ghi đè** lỗi `BadCredentialsException` đã ghi nhận từ child; lỗi của child có thể trở thành kết quả thất bại cuối cùng.

Ngược lại, nếu child chỉ gặp `supports == false` hoặc `null`, không ghi nhận lỗi nào, và parent cũng không xử lý được, kết quả cuối là `ProviderNotFoundException`.

`ProviderNotFoundException` mô tả thiếu cơ chế hỗ trợ **loại authentication request**; không nhất thiết nói mật khẩu người dùng sai. Trong API HTTP, status cụ thể phụ thuộc bộ lọc/entry point và mapping exception, không suy ra luôn một status duy nhất chỉ từ class exception.

### 4.2. Nếu provider sau thành công thì lỗi trước có còn ý nghĩa không?

Lỗi trước vẫn có thể có ý nghĩa cho logging nội bộ hoặc quan sát bảo mật ở từng provider, nhưng `ProviderManager` trả **thành công cuối cùng** và không ném lỗi ấy. Không xây logic nghiệp vụ giả định mọi `BadCredentialsException` từ một provider sẽ chắc chắn xuất hiện ở HTTP response.

### 4.3. Sự kiện xác thực khi có parent

`ProviderManager` hỗ trợ `AuthenticationEventPublisher`. Mặc định publisher của nó không phát sự kiện nếu chưa cấu hình. Nếu cả child và parent đều được cấu hình phát authentication events, cần chú ý khả năng sự kiện trùng lặp, nhất là nhánh thất bại; JavaDoc khuyến nghị không cấu hình parent phát sự kiện riêng trong những tình huống có thể trùng. Khi cần audit, xác định **ai là chủ sở hữu việc phát sự kiện** và kiểm thử thực tế, không đếm một lần `authenticate(...)` như một lần event chắc chắn.

## 5. Ví dụ Java 17+ chạy được: năm nhánh của parent fallback

Ví dụ dưới đây là **chương trình Spring Boot chạy dòng lệnh, không tạo HTTP endpoint**. Mục tiêu là quan sát trực tiếp semantics của `ProviderManager`. Nó dùng provider mô phỏng để điều khiển chính xác từng nhánh; **không kiểm tra password thật, không được dùng làm hệ thống đăng nhập production**.

Tạo một project từ Spring Initializr với Java 17+, Spring Boot 3.x, build Maven và dependency **Spring Security** (không cần Spring Web). Đặt file `src/main/java/com/example/demo/ParentManagerDemoApplication.java`:

~~~java
package com.example.demo;

import java.util.List;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.authentication.AuthenticationProvider;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.LockedException;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

@SpringBootApplication
public class ParentManagerDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ParentManagerDemoApplication.class, args);
    }

    @Bean
    CommandLineRunner demonstrateFallback() {
        return args -> {
            AuthenticationProvider localProvider =
                new AuthenticationProvider() {
                    @Override
                    public Authentication authenticate(Authentication request) {
                        return switch (request.getName()) {
                            case "local" -> success("local", "ROLE_LOCAL");
                            case "fallback" -> null;
                            case "retry" ->
                                throw new BadCredentialsException("local rejected");
                            case "locked" ->
                                throw new LockedException("account locked");
                            default -> null;
                        };
                    }

                    @Override
                    public boolean supports(Class<?> type) {
                        return UsernamePasswordAuthenticationToken.class
                            .isAssignableFrom(type);
                    }
                };

            AuthenticationProvider sharedProvider =
                new AuthenticationProvider() {
                    @Override
                    public Authentication authenticate(Authentication request) {
                        System.out.println("PARENT tried: " + request.getName());
                        return switch (request.getName()) {
                            case "fallback", "retry", "locked" ->
                                success(request.getName(), "ROLE_SHARED");
                            default -> null;
                        };
                    }

                    @Override
                    public boolean supports(Class<?> type) {
                        return UsernamePasswordAuthenticationToken.class
                            .isAssignableFrom(type);
                    }
                };

            ProviderManager parent =
                new ProviderManager(List.of(sharedProvider));

            ProviderManager child =
                new ProviderManager(List.of(localProvider), parent);

            for (String username :
                List.of("local", "fallback", "retry", "locked", "unknown")) {
                demonstrateCase(child, username);
            }
        };
    }

    private static Authentication success(String name, String role) {
        return UsernamePasswordAuthenticationToken.authenticated(
            name,
            null,
            List.of(new SimpleGrantedAuthority(role))
        );
    }

    private static void demonstrateCase(
        ProviderManager child,
        String username
    ) {
        try {
            Authentication result = child.authenticate(
                UsernamePasswordAuthenticationToken.unauthenticated(
                    username, "demo"
                )
            );
            String authority =
                result.getAuthorities().iterator().next().getAuthority();
            System.out.println(username + " -> OK / " + authority);
        }
        catch (AuthenticationException failure) {
            System.out.println(
                username + " -> " + failure.getClass().getSimpleName()
            );
        }
    }
}
~~~

### 5.1. Cách chạy

Trong thư mục chứa `pom.xml` do Initializr tạo:

~~~bash
./mvnw spring-boot:run
~~~

Trên Windows PowerShell, dùng `.\mvnw.cmd spring-boot:run`. Nếu chọn Gradle thay vì Maven, lệnh tương ứng là `./gradlew bootRun` (Windows: `.\gradlew.bat bootRun`).

Các dòng do demo in ra, **không tính log khởi động Spring Boot**:

~~~text
local -> OK / ROLE_LOCAL
PARENT tried: fallback
fallback -> OK / ROLE_SHARED
PARENT tried: retry
retry -> OK / ROLE_SHARED
locked -> LockedException
PARENT tried: unknown
unknown -> ProviderNotFoundException
~~~

### 5.2. Giải thích từng lần gọi

**`local`:** child provider trả authentication thành công có `ROLE_LOCAL`. `ProviderManager` dừng ngay; parent không in dòng `PARENT tried: local`.

**`fallback`:** child `supports(...) == true` nhưng `authenticate(...) == null`. Sau khi hết local providers, parent được gọi, trả `ROLE_SHARED`.

**`retry`:** child ném `BadCredentialsException`. `ProviderManager` ghi nhận ngoại lệ thông thường nhưng tiếp tục. Không có child provider thành công, nên parent vẫn được gọi và thành công. Ví dụ này **cố ý làm rõ rủi ro fallback sau khi credentials đã bị từ chối**.

**`locked`:** child ném `LockedException`, là `AccountStatusException`. `ProviderManager` dừng và ném ngay; dù parent đã được viết để có khả năng chấp nhận username `locked`, nó **không được gọi**. Vì thế cũng không có dòng `PARENT tried: locked`.

**`unknown`:** local provider trả null, parent cũng trả null. Khi không có provider nào trả authentication và không có exception chi tiết nào được giữ, kết quả cuối là `ProviderNotFoundException`.

Ví dụ dùng một provider ở child và một provider ở parent để hiển thị rõ luồng; bạn có thể bổ sung nhiều provider để thấy thứ tự xử lý. Khi làm điều đó, nhớ rằng thứ tự trong `List` ảnh hưởng provider nào được thử trước và provider nào có thể quyết định thành công.

### 5.3. Vì sao ví dụ không kiểm tra mật khẩu?

Mỗi `switch` trong demo cố tình chọn kết quả theo username để minh họa contract. Đây **không phải cách xây provider thật**: `success(...)` đang tạo một token `authenticated(...)` mà không xác minh bằng chứng. Trong ứng dụng production, chỉ tạo authentication thành công sau khi đã kiểm tra credentials, trạng thái account và policy đúng loại. Với username/password, ưu tiên các cơ chế đã kiểm chứng như `DaoAuthenticationProvider` và `PasswordEncoder` thích hợp.

## 6. Mô phỏng thêm: khác nhau giữa null và sai mật khẩu

Giả sử child phục vụ user thuộc hệ thống nội bộ, parent phục vụ user thuộc nguồn danh tính chia sẻ.

**Nhánh A — child không biết xử lý token:**

~~~text
ChildProvider.supports(TokenX) == false
-> bỏ qua ChildProvider
-> parent được thử nếu không có kết quả khác
~~~

Đây là nơi cần mở rộng phạm vi hợp lệ của parent nếu parent hỗ trợ `TokenX`.

**Nhánh B — child biết loại token nhưng user không thuộc miền nó quản lý:**

~~~text
ChildProvider.supports(TokenX) == true
ChildProvider.authenticate(request) == null
-> manager thử provider tiếp theo / parent
~~~

Chỉ nên trả null khi provider thực sự **không thể quyết định** cho request đó. Đây là hợp đồng “nhường lượt”, cần phân định rõ dữ liệu như domain/issuer/tenant đã được xác thực, tránh logic routing dựa trên header tự khai báo.

**Nhánh C — child quản lý chính danh tính nhưng password sai:**

~~~text
ChildProvider.authenticate(request)
    throws BadCredentialsException
-> Manager có thể thử provider tiếp theo / parent
~~~

Nếu chính sách sản phẩm cấm xác thực user này bằng nguồn khác, **đừng chỉ hy vọng exception sẽ ngăn fallback**. Thiết kế manager/chain và loại token sao cho parent không chấp nhận chéo cùng thông tin đăng nhập sai, hoặc không cấu hình parent cho dòng xác thực đó. Phân vùng bằng các `Authentication` token type chuyên biệt khi phù hợp thường rõ nghĩa hơn cố phân biệt trong `supports` chỉ bằng username.

**Nhánh D — account đã bị khóa:**

~~~text
ChildProvider.authenticate(request)
    throws LockedException
-> ProviderManager dừng và ném ngay
-> parent không được gọi
~~~

Đây là tính chất của `AccountStatusException`. Đừng lạm dụng status exception như một câu lệnh `break` giả tạo; nếu tài khoản không thực sự bị khóa, thông báo và semantics trở nên sai.

## 7. Manager cha trong ứng dụng có nhiều SecurityFilterChain

Một cấu trúc có thể gặp là:

~~~text
HTTP request
  -> FilterChainProxy
       |-- /api/** -> SecurityFilterChain API
       |                -> AuthenticationManager child-API
       |                   -> API-specific providers
       |
       |-- /admin/** -> SecurityFilterChain ADMIN
                        -> AuthenticationManager child-ADMIN
                           -> Admin-specific providers

child-API   ----+
                +----> Shared AuthenticationManager parent
child-ADMIN ----+      -> Shared providers
~~~

`FilterChainProxy` chọn **chain khớp đầu tiên** cho request. Một khi filter của chain đó gọi `authenticate(...)` trên child manager, logic parent fallback diễn ra **bên trong quá trình xác thực của chain ấy**. Nó không yêu cầu `FilterChainProxy` thử lại các URL matcher hoặc chuyển filter sang chain khác.

Có thể dùng parent để chia sẻ xác thực chung và child để thêm cơ chế chuyên biệt, nhưng chỉ khi các cơ chế được phép chia sẻ cùng ranh giới tin cậy. Không tự động kết nối tất cả chain vào một parent rồi nghĩ rằng các endpoint admin/API đã được tách hoàn toàn: một parent chấp nhận token vượt phạm vi có thể làm lu mờ sự phân chia.

Với DSL cấu hình HTTP, phương thức và builder được dùng để lắp manager phụ thuộc cấu hình cụ thể của Spring Security. Ví dụ `new ProviderManager(providers, parent)` ở trên là cách **rõ ràng, trực tiếp và kiểm thử được** để tìm hiểu quan hệ cha–con; không khẳng định Spring Boot luôn tạo cấu trúc này thay bạn.

### 7.1. Tách authentication domain theo ranh giới

Giả sử hai nhóm user có username giống nhau, nhưng thuộc identity store khác nhau. Nếu child và parent đều hỗ trợ `UsernamePasswordAuthenticationToken`, `supports(Class<?>)` chỉ giúp xác định **kiểu token**, không tự biết username thuộc nhóm nào. Vì vậy, thiết kế tránh một tài khoản nội bộ bị từ chối ở child nhưng “đăng nhập được” bằng dữ liệu của parent ngoài ý muốn.

Các cách giảm nhầm lẫn:

- Phân loại cơ chế qua token class/issuer/nguồn đáng tin; đảm bảo loại authentication request và nguồn dữ liệu được nhận đúng phạm vi.
- Chỉ cấu hình parent ở những child manager thật sự cho phép fallback.
- Không đưa một credential không hợp lệ qua nhiều backend một cách vô hạn định; chú ý rate limiting, lockout, audit và phòng chống user enumeration.
- Kiểm thử luồng **provider child thất bại + parent có credential hợp lệ**, vì đây là trường hợp dễ bỏ sót nhất.
- Không lạm dụng `supports(...)` để xác thực credentials: nó nhận **Class**, chưa nhận request instance hoặc bí mật đã xác minh.

## 8. Lỗi thường gặp và hướng chẩn đoán

| Hiện tượng | Cơ chế có thể gây ra | Cách kiểm tra |
| --- | --- | --- |
| Tưởng child trả `null` sẽ fail ngay | Parent được thử sau khi mọi child provider không thành công | Kiểm tra parent thực sự được cấu hình và hỗ trợ token nào |
| Child ném `BadCredentialsException` nhưng user vẫn đăng nhập thành công | Provider sau hoặc parent xác thực thành công | Truy dấu thứ tự provider, phân vùng identity store, test tài khoản trùng |
| Child trả authentication nhưng parent không được gọi | Kết quả khác null khiến manager dừng | Đây là hành vi bình thường nếu provider child xác thực hợp lệ |
| Tài khoản bị khóa và parent không chạy | `LockedException` thuộc `AccountStatusException` | Kiểm tra luồng dừng sớm và chính sách account |
| Xảy ra lỗi hạ tầng xác thực và không fallback | `InternalAuthenticationServiceException` dừng ngay | Sửa nguồn lỗi, không chuyển lỗi nội bộ thành cơ chế bỏ qua xác thực |
| Kết quả cuối là `ProviderNotFoundException` | Không provider nào xử lý được token, hoặc parent cũng không hỗ trợ | Kiểm tra `supports(Class<?>)`, token class và danh sách providers |
| Client có lỗi child nhưng server báo lỗi khác | Parent trả một `AuthenticationException` mới | Xác định lỗi cuối và bộ lọc/entry point đang ánh xạ phản hồi |
| Audit ghi nhiều event bất ngờ | Event publisher ở nhiều tầng manager | Kiểm tra ownership của `AuthenticationEventPublisher` |
| Token thành công không còn password | `ProviderManager` xóa credentials trên `CredentialsContainer` sau xác thực | Đây là mặc định bảo mật; không dựa vào password còn tồn tại sau login |

Khi cần debug, có thể bật logging Spring Security ở mức thích hợp cho môi trường thử nghiệm và đặt breakpoint tại `ProviderManager.authenticate(...)`, `AuthenticationProvider.supports(...)`, `AuthenticationProvider.authenticate(...)`. Không log password, bearer token, session cookie hoặc toàn bộ `Authentication` nếu có thể chứa bí mật.

## 9. Câu hỏi tự kiểm tra

**Câu 1.** Child có hai provider: P1 trả `null`; P2 ném `BadCredentialsException`; parent xác thực thành công. Kết quả?

Đáp án: thành công từ parent vì không provider con nào trả kết quả khác null và đây là ngoại lệ thuộc nhóm có thể tiếp tục.

**Câu 2.** Child P1 ném `LockedException`, P2 có thể xác thực, parent cũng có thể xác thực. P2 hoặc parent có được gọi không?

Đáp án: không; `LockedException` kế thừa `AccountStatusException` làm `ProviderManager` dừng ngay.

**Câu 3.** Child ném `BadCredentialsException`; parent ném `ProviderNotFoundException`. Ngoại lệ nào thường được phát ra từ child `ProviderManager`?

Đáp án: child giữ lỗi `BadCredentialsException` đã ghi nhận; `ProviderNotFoundException` của parent không nhất thiết ghi đè. Đây là hành vi cụ thể của `ProviderManager` tiêu chuẩn.

**Câu 4.** Child provider `supports(TokenA.class)` trả false, parent có provider hỗ trợ `TokenA`. Có nhất thiết thất bại không?

Đáp án: không. Child bỏ qua provider không hỗ trợ và có thể ủy quyền cho parent; parent có thể xác thực thành công nếu đúng cơ chế.

**Câu 5.** Child trả token đã xác thực, nhưng policy muốn parent kiểm tra thêm. Parent có tự chạy không?

Đáp án: không. Kết quả khác null làm `ProviderManager` dừng. Nếu cần xác thực đa bước/multi-factor, hãy thiết kế flow có các bước kiểm chứng rõ ràng; quan hệ parent fallback không phải quy trình bắt buộc parent phê duyệt.

**Câu 6.** Hai security chain có parent manager chung thì request sẽ chạy qua cả hai chain?

Đáp án: không. Việc chọn chain và việc gọi parent manager là hai cơ chế khác nhau. Chain khớp đầu tiên được chọn cho request; trong chain ấy, authentication có thể dùng child rồi parent.

## 10. Checklist trước khi dùng parent fallback thực tế

1. Parent có thực sự được cấu hình trên `ProviderManager` con chưa? Ai khởi tạo và sở hữu nó?
2. Những `AuthenticationProvider` nào có thể xử lý loại token đang gửi? Thứ tự của chúng là gì?
3. Các trường hợp `supports == false`, `authenticate == null` và `BadCredentialsException` có được phân biệt trong test?
4. Có thể một child provider từ chối credentials nhưng parent lại xác thực cùng username từ nguồn khác không? Điều đó có đúng yêu cầu bảo mật?
5. Các lỗi account status và internal service có dừng ngay như thiết kế không?
6. Có case parent ném `ProviderNotFoundException` và case cả hai manager không xử lý được không?
7. Các security chain của API/admin/web có đang dùng đúng authentication manager và identity domain không?
8. Logging, event publishing, rate limiting và credential erasure có nhất quán khi kết quả đến từ parent không?
9. Có kiểm thử theo thứ tự provider thực tế để bắt sự thay đổi khi cấu hình mới được thêm vào không?

**Kết luận cốt lõi:** manager cha là **fallback khi `ProviderManager` con vẫn chưa có kết quả xác thực** và được cấu hình parent. Điều kiện này vẫn có thể đúng sau một `BadCredentialsException` thông thường. Một kết quả authentication khác null chặn fallback; `AccountStatusException` và `InternalAuthenticationServiceException` cũng chặn fallback bằng cách dừng ngay. Hiểu chính xác ba nhánh này giúp chia sẻ cơ chế xác thực mà không vô tình mở thêm đường đăng nhập trái chính sách.

## Tài liệu tham khảo

- [Spring Security — Servlet Authentication Architecture / ProviderManager](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html)
- [Spring Security 6.5 — ProviderManager API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/ProviderManager.html)
- [Spring Security 6.5 — AuthenticationProvider API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/AuthenticationProvider.html)
- [Spring Security — Servlet Security Architecture / Multiple Filter Chains](https://docs.spring.io/spring-security/reference/servlet/architecture.html)
- [Spring Security — ProviderManager source code](https://github.com/spring-projects/spring-security/blob/6.5.x/core/src/main/java/org/springframework/security/authentication/ProviderManager.java)
