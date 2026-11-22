# Thứ tự provider và cách xử lý thành công, không hỗ trợ hoặc thất bại

> **Ngữ cảnh:** Spring Security → Authentication → Bộ máy xác thực. Bài này đi sâu vào cách `ProviderManager` duyệt các `AuthenticationProvider`, phân biệt “không hỗ trợ”, “không thể quyết định”, “xác thực thành công”, “xác thực thất bại”, và lý do thứ tự provider là một phần quan trọng của thiết kế bảo mật. Các ví dụ API áp dụng cho Spring Security 6.x, Java 17+.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích trách nhiệm của `AuthenticationManager`, `ProviderManager` và `AuthenticationProvider`; biết provider được gọi theo thứ tự nào.
2. Phân biệt rõ ba tín hiệu `supports(...) == false`, `authenticate(...) == null`, và `authenticate(...)` ném `AuthenticationException`.
3. Dự đoán chính xác khi provider đầu trả kết quả thành công, khi nó từ chối credential, khi nó không hỗ trợ token, và khi provider sau có thể thành công.
4. Nhận biết các ngoại lệ khiến `ProviderManager` **dừng ngay**, đặc biệt `AccountStatusException` và `InternalAuthenticationServiceException`.
5. Hiểu cách dùng parent `AuthenticationManager`, điều kiện xuất hiện `ProviderNotFoundException`, cách chọn exception cuối cùng, sự kiện xác thực và xóa credential sau thành công.
6. Chạy ví dụ Java có thứ tự provider quan sát được; thiết kế test để tránh vô tình cho provider sau vượt qua chính sách của provider trước.

## 2. Ba vai trò trong một lần xác thực

`AuthenticationManager` định nghĩa thao tác trung tâm:

~~~java
Authentication authenticate(Authentication authentication)
        throws AuthenticationException;
~~~

Nó nhận một **yêu cầu xác thực** dưới dạng `Authentication`, trả về kết quả đã được xác thực nếu thành công, hoặc ném `AuthenticationException` nếu thất bại.

`ProviderManager` là triển khai thường dùng của `AuthenticationManager`. Nó giữ một **danh sách có thứ tự** các `AuthenticationProvider` và chuyển từng yêu cầu đến provider phù hợp. `AuthenticationProvider` thường xử lý một cơ chế hoặc một tập credential cụ thể: tên/mật khẩu, JWT, token truy cập từ bên ngoài, chứng chỉ, hoặc cơ chế tùy chỉnh.

Giao diện provider có hai phương thức chính:

~~~java
public interface AuthenticationProvider {
    Authentication authenticate(Authentication authentication)
            throws AuthenticationException;

    boolean supports(Class<?> authentication);
}
~~~

| Thành phần | Câu hỏi nó trả lời | Trách nhiệm |
| --- | --- | --- |
| `Authentication` yêu cầu | “Tôi đang đưa bằng chứng gì?” | Chứa principal, credentials và thông tin yêu cầu; ban đầu thường chưa được xác thực |
| `AuthenticationProvider.supports(type)` | “Tôi **có thể xem xét** loại token Java này không?” | Xác định khả năng xử lý theo **kiểu lớp**, chưa kiểm credential |
| `AuthenticationProvider.authenticate(request)` | “Với loại request phù hợp, bằng chứng này có hợp lệ không?” | Xác minh thật, trả kết quả hoặc báo không quyết định/thất bại |
| `ProviderManager.authenticate(request)` | “Provider nào trong danh sách đưa ra kết quả xác thực?” | Chọn provider theo thứ tự và áp dụng chính sách tiếp tục/dừng |
| Security filter hoặc caller tin cậy | “Lấy và lưu kết quả ở đâu?” | Gọi manager, xử lý thành công/thất bại, thiết lập `SecurityContext` theo cơ chế phù hợp |
| Authorization | “Chủ thể có quyền thực hiện hành động này không?” | Kiểm authorities, vai trò, scope, chính sách tài nguyên/tenant |

**Chú ý:** `supports(...) == true` **chỉ xác nhận provider có khả năng đánh giá lớp `Authentication` đó**. Nó không có nghĩa mật khẩu đúng, token hợp lệ hay người dùng có quyền. Phải đi qua `authenticate(...)` và nhận kết quả đáng tin.

Ví dụ hai provider cùng trả `true` cho `UsernamePasswordAuthenticationToken.class`: một provider đối chiếu LDAP, provider kia đối chiếu kho user nội bộ. Khi đó thứ tự và quy tắc fallback sẽ ảnh hưởng đến quyết định cuối cùng.

## 3. Thuật toán duyệt provider theo thứ tự

Với danh sách `[P1, P2, P3]`, `ProviderManager` duyệt từ đầu đến cuối. Mô hình điều khiển khái niệm:

~~~mermaid
flowchart TD
    A["Authentication request"] --> B["Xét provider kế tiếp theo thứ tự"]
    B --> C{"supports(request.getClass())?"}
    C -->|false| D["Bỏ qua; không gọi authenticate"]
    D --> B
    C -->|true| E["Gọi provider.authenticate(request)"]
    E --> F{"Kết quả?"}
    F -->|"Authentication khác null"| G["Thành công; dừng duyệt"]
    F -->|null| H["Không quyết định; thử tiếp"]
    H --> B
    F -->|"AuthenticationException thông thường"| I["Ghi nhận lỗi; thử tiếp"]
    I --> B
    F -->|"AccountStatusException hoặc InternalAuthenticationServiceException"| J["Ném lỗi ngay; dừng"]
    B --> K{"Hết provider?"}
    K -->|có| L["Có parent thì thử parent"]
    L --> M{"Đã có kết quả?"}
    M -->|có| G
    M -->|không| N["Ném lỗi cuối hoặc ProviderNotFoundException"]
~~~

Sơ đồ rút gọn điều kiện kết thúc; quy tắc chi tiết về parent và exception được giải thích ở mục 5–6.

### 3.1. `supports(...) == false`: không hỗ trợ kiểu Authentication

Provider bị **bỏ qua hoàn toàn**, `authenticate(...)` không được gọi. Lệnh gọi sẽ chuyển sang provider tiếp theo. Ví dụ một provider chỉ hỗ trợ `UsernamePasswordAuthenticationToken` thường sẽ bỏ qua token JWT, nếu `supports(...)` được triển khai đúng theo type.

Đây là quyết định **theo lớp token Java**, không phải “username không tồn tại trong kho này”. Không nên dùng `supports(...)` để cố xác nhận mật khẩu hoặc làm request tới hệ thống bên ngoài.

### 3.2. `supports(...) == true` và `authenticate(...)` trả `null`

Provider có thể đánh giá kiểu token nhưng **không đưa ra quyết định** với request cụ thể. `ProviderManager` tiếp tục sang provider sau. Đây là cơ chế “abstain”: không xác nhận thành công, cũng không tuyên bố thất bại.

Ví dụ có hai biến thể khác nhau trong cùng một kiểu token; provider đầu nhận ra request không thuộc cơ chế nó chịu trách nhiệm và trả `null`, sau đó provider khác xem xét.

**Không dùng `null` để che giấu mật khẩu sai** nếu provider thực sự có trách nhiệm đối chiếu credential. Nếu mọi provider không đưa ra kết quả và không có parent có thể xác thực, thường nhận `ProviderNotFoundException`. Nếu có lỗi xác thực thông thường đã xảy ra trước đó, lỗi cuối được giữ lại theo quy tắc ở mục 4.

### 3.3. Trả `Authentication` khác `null`: thành công, dừng duyệt

Provider trả kết quả **khác `null`** thì `ProviderManager` chấp nhận kết quả và **không gọi provider nào phía sau**. Provider phải chỉ trả kết quả này **sau khi thực sự kiểm tra bằng chứng** và tạo `Authentication` đáng tin; `ProviderManager` không tự kiểm lại mật khẩu hoặc chữ ký token thay provider.

Vì sao đây là quyết định quan trọng? Nếu P1 trả kết quả sai do code tạo token “đã authenticated” từ dữ liệu client, P2 không bao giờ có cơ hội sửa. Thiết kế và test của provider có trách nhiệm bảo đảm `Authentication` kết quả là hợp lệ.

### 3.4. Ném `AuthenticationException` thông thường: có thể thử provider tiếp

Một `BadCredentialsException` từ P1 **không mặc nhiên dừng toàn bộ `ProviderManager`**. Manager ghi nhận lỗi rồi có thể thử P2, P3 nếu chúng hỗ trợ cùng loại token. Nếu P2 xác thực thành công, **thành công của P2 được dùng và lỗi P1 bị bỏ qua**. Nếu không có kết quả thành công, lỗi xác thực cuối cùng được ném.

Điều này thường gây bất ngờ: “P1 báo sai password” không đồng nghĩa “request chắc chắn bị từ chối” khi có provider thứ hai hỗ trợ cùng kiểu request.

**Hệ quả bảo mật:** chỉ bật fallback giữa nhiều provider khi đó là chính sách đăng nhập có chủ đích. Nếu “không có user trong LDAP” được cho phép kiểm tiếp ở kho riêng thì phải xác định rõ namespace, tránh va chạm danh tính, cân nhắc khóa tài khoản, điều kiện đăng nhập và khả năng một kho yếu hơn chấp nhận credential mà kho trước từ chối.

### 3.5. Ngoại lệ đặc biệt: dừng tức thì

Hai nhánh trong `ProviderManager` cần được hiểu riêng:

- `AccountStatusException`, ví dụ `LockedException`, `DisabledException`, `AccountExpiredException`, `CredentialsExpiredException`: **dừng ngay**, không truy vấn các provider còn lại và không dùng parent để vượt qua tình trạng khóa/hết hạn.
- `InternalAuthenticationServiceException`: cũng **dừng ngay**, vì provider báo lỗi nội bộ nghiêm trọng của dịch vụ xác thực; không tiếp tục fallback tùy tiện.

Không đánh đồng mọi `AuthenticationException` thành “dừng ngay”; cũng không kết luận rằng **mọi** lỗi dịch vụ đều có cùng hành vi với `InternalAuthenticationServiceException`. Nhánh xử lý dựa trên **lớp exception thực sự được ném**.

## 4. Bảng quyết định theo từng tình huống

Giả sử danh sách `[P1, P2]` và không cấu hình parent. “Kết quả” ở đây là kết quả từ `ProviderManager.authenticate(...)`, **chưa phải quyết định authorization của endpoint**.

| P1 | P2 | P2 có được thử? | Kết quả |
| --- | --- | --- | --- |
| `supports=false` | Thành công | Có | Trả `Authentication` của P2 |
| `supports=true`, trả `null` | Thành công | Có | Trả `Authentication` của P2 |
| Thành công | Bất kỳ | **Không** | Trả kết quả P1, dừng ngay |
| Ném `BadCredentialsException` | Thành công | Có | Trả kết quả P2; lỗi P1 không còn quyết định |
| Ném `BadCredentialsException` | Ném `BadCredentialsException` | Có | Ném lỗi của P2 (lỗi cuối) |
| Ném `BadCredentialsException` | Trả `null` hoặc không hỗ trợ | Có/bỏ qua theo `supports` | Ném lỗi `BadCredentialsException` của P1 |
| `supports=false` | `supports=false` | P2 được kiểm `supports` nhưng không chạy `authenticate` | Ném `ProviderNotFoundException` |
| Trả `null` | Trả `null` | Có | Ném `ProviderNotFoundException` nếu không có lỗi khác |
| Ném `LockedException` | Thành công nếu được gọi | **Không** | Ném `LockedException` ngay |
| Ném `InternalAuthenticationServiceException` | Thành công nếu được gọi | **Không** | Ném lỗi nội bộ ngay |

**Phân biệt “P2 được thử” với “P2 được gọi `authenticate`”:** `supports` thường vẫn được kiểm tra khi vòng lặp đến P2; `authenticate` chỉ được gọi nếu `supports` trả `true`. Nếu P1 đã thành công hoặc ném ngoại lệ dừng ngay, cả bước xét P2 cũng không diễn ra.

### “Exception cuối cùng” nghĩa là gì?

Giả sử P1 ném `BadCredentialsException("password wrong")`, P2 ném `BadCredentialsException("token rejected")`. Nếu không có provider thành công và không có parent xử lý, `ProviderManager` thường ném **exception của P2**, không tổng hợp cả hai thành một lỗi mới. Nếu P1 ném lỗi rồi P2 trả `null`, lỗi của P1 vẫn là lỗi cuối. Điều này hỗ trợ chẩn đoán, nhưng thông điệp lỗi nội bộ không nên trả nguyên văn ra API công khai.

Một số exceptional branch được xử lý đặc biệt trước khi đến quy tắc “lỗi cuối”: `AccountStatusException` và `InternalAuthenticationServiceException` ném ngay. Đồng thời parent có thể tham gia sau khi provider trong danh sách đều không trả kết quả; xem phần tiếp theo.

## 5. Parent AuthenticationManager được gọi khi nào?

`ProviderManager` có thể có **parent `AuthenticationManager`**. Khi các provider con **không tạo ra kết quả thành công**, và không có exception dừng ngay, manager có thể thử parent. Parent không phải “provider cuối cùng” trong danh sách, nhưng được xem xét sau vòng duyệt providers cục bộ.

Ví dụ cấu trúc:

~~~text
HTTP authentication request
    |
    v
Child ProviderManager
    |-- P1
    |-- P2
    |
    +-- nếu chưa có kết quả và được phép tiếp tục
            |
            v
       Parent AuthenticationManager
            |-- P3
            |-- P4
~~~

Những điều cần biết:

- Parent **có thể được gọi ngay cả khi** một provider con đã ném `BadCredentialsException` thông thường, miễn chưa có kết quả và chưa gặp nhánh dừng ngay.
- Parent thành công → sử dụng kết quả của parent.
- Parent ném `AuthenticationException` thông thường → lỗi đó có thể trở thành lỗi cuối.
- Parent ném `ProviderNotFoundException` → `ProviderManager` con có cơ chế tránh ghi đè một lỗi xác thực đã có của provider con bằng lỗi “không tìm thấy provider” của parent; nếu không có lỗi khác thì cuối cùng vẫn là `ProviderNotFoundException`.
- Provider con ném `AccountStatusException` hoặc `InternalAuthenticationServiceException` → dừng trước khi đến parent.
- Một hệ thống có nhiều `SecurityFilterChain` đôi khi dùng nhiều manager con chia sẻ cùng parent. Đó là thiết kế có chủ đích, không phải mặc định mọi request đều chạy qua tất cả chain.

**Ví dụ thiết lập parent (đoạn Java tích hợp, không độc lập):**

~~~java
AuthenticationManager parent = new ProviderManager(
        List.of(sharedProvider));
AuthenticationManager child = new ProviderManager(
        List.of(applicationProviderA, applicationProviderB),
        parent);
~~~

Các biến `sharedProvider`, `applicationProviderA`, `applicationProviderB` ở đây là những `AuthenticationProvider` đã cấu hình, thực sự xác minh credential. Chỉ dùng cấu trúc parent khi chính sách fallback có ý nghĩa an toàn và được kiểm thử. Không dùng parent để né khóa tài khoản hoặc gom toàn bộ danh tính từ các hệ thống không tương thích.

## 6. Ví dụ Java 17 chạy thật: thứ tự và nhánh quyết định

Ví dụ dưới đây dùng **chính lớp `ProviderManager` của Spring Security**, tạo các provider giả lập có thể trả thành công, `null`, từ chối hoặc báo lỗi. Provider “ACCEPT” **không kiểm mật khẩu** vì mục đích chỉ là quan sát thuật toán điều phối; **không được tái sử dụng provider mô phỏng này cho đăng nhập thực tế**. Ứng dụng thực phải xác thực credential, kiểm chính sách account và giới hạn quyền.

Ví dụ là ứng dụng **Java console có dependency Spring Security Core**, không cần Spring Boot hoặc web server; các kết quả được in bởi `main`. Phần `build.gradle` cần Gradle có thể tải dependency từ Maven Central.

### 6.1. Cấu trúc và Gradle

~~~text
provider-order-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/example/providerorder/
    └── ProviderOrderDemo.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'provider-order-demo'
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
    implementation 'org.springframework.security:spring-security-core:6.5.11'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'example.providerorder.ProviderOrderDemo'
}
~~~

### 6.2. Tệp Java đầy đủ

Lưu tại `src/main/java/example/providerorder/ProviderOrderDemo.java`:

~~~java
package example.providerorder;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.InternalAuthenticationServiceException;
import org.springframework.security.authentication.LockedException;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.AuthenticationProvider;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

public class ProviderOrderDemo {

    enum Decision {
        UNSUPPORTED, ABSTAIN, REJECT, LOCKED, INTERNAL_ERROR, ACCEPT
    }

    // Provider mô phỏng luồng điều phối, KHÔNG thực hiện xác thực thật.
    static final class TracedProvider implements AuthenticationProvider {
        private final String name;
        private final Decision decision;
        private final List<String> trace;

        TracedProvider(String name, Decision decision, List<String> trace) {
            this.name = name;
            this.decision = decision;
            this.trace = trace;
        }

        @Override
        public boolean supports(Class<?> authenticationType) {
            boolean supported = decision != Decision.UNSUPPORTED
                    && UsernamePasswordAuthenticationToken.class
                            .isAssignableFrom(authenticationType);
            trace.add(name + ".supports=" + supported);
            return supported;
        }

        @Override
        public Authentication authenticate(Authentication request)
                throws AuthenticationException {
            trace.add(name + ".authenticate");

            return switch (decision) {
                case ABSTAIN -> null;

                case REJECT ->
                        throw new BadCredentialsException("rejected by " + name);

                case LOCKED ->
                        throw new LockedException("locked by " + name);

                case INTERNAL_ERROR ->
                        throw new InternalAuthenticationServiceException(
                                "backend error at " + name);

                case ACCEPT ->
                        UsernamePasswordAuthenticationToken.authenticated(
                                request.getPrincipal(),
                                null,
                                List.of(new SimpleGrantedAuthority("ROLE_DEMO")));

                case UNSUPPORTED ->
                        throw new IllegalStateException(
                                "Unsupported provider should never be called");
            };
        }
    }

    static void runCase(String label, Decision... decisions) {
        List<String> trace = new ArrayList<>();
        List<AuthenticationProvider> providers = new ArrayList<>();

        for (int i = 0; i < decisions.length; i++) {
            providers.add(new TracedProvider(
                    "P" + (i + 1), decisions[i], trace));
        }

        ProviderManager manager = new ProviderManager(providers);

        Authentication request =
                UsernamePasswordAuthenticationToken.unauthenticated(
                        "alice", "demo-credential");

        try {
            Authentication result = manager.authenticate(request);
            System.out.println(label + " => SUCCESS(" + result.getName() + ")");
        }
        catch (AuthenticationException failure) {
            System.out.println(label + " => "
                    + failure.getClass().getSimpleName());
        }

        System.out.println("  trace=" + trace);
    }

    public static void main(String[] args) {
        runCase("first-success",
                Decision.ACCEPT, Decision.REJECT);

        runCase("unsupported-then-success",
                Decision.UNSUPPORTED, Decision.ACCEPT);

        runCase("null-then-success",
                Decision.ABSTAIN, Decision.ACCEPT);

        runCase("bad-then-success",
                Decision.REJECT, Decision.ACCEPT);

        runCase("bad-then-bad",
                Decision.REJECT, Decision.REJECT);

        runCase("locked-stops",
                Decision.LOCKED, Decision.ACCEPT);

        runCase("internal-stops",
                Decision.INTERNAL_ERROR, Decision.ACCEPT);

        runCase("all-unsupported",
                Decision.UNSUPPORTED, Decision.UNSUPPORTED);

        runCase("all-null",
                Decision.ABSTAIN, Decision.ABSTAIN);
    }
}
~~~

Giải thích:

- `Decision.UNSUPPORTED` làm `supports` trả `false` nên phương thức `authenticate` của provider đó không thể được gọi trong cơ chế điều phối bình thường.
- `Decision.ABSTAIN` trả `null`, diễn tả trường hợp provider xét loại token nhưng không thể quyết định.
- `Decision.REJECT` ném `BadCredentialsException`: lỗi thông thường mà `ProviderManager` có thể ghi nhận và thử tiếp.
- `Decision.LOCKED` và `Decision.INTERNAL_ERROR` ném các exception thuộc nhóm dừng ngay.
- `Decision.ACCEPT` tạo kết quả khác `null`: manager dừng duyệt. Đây là **điểm mô phỏng**, không phải mẫu xác thực production.

### 6.3. Chạy chương trình

Từ thư mục `provider-order-demo` với JDK 17+ và Gradle (hoặc Gradle Wrapper đã cấu hình):

~~~bash
gradle run --quiet
~~~

Đầu ra do chính `ProviderOrderDemo.main` tạo ra:

~~~text
first-success => SUCCESS(alice)
  trace=[P1.supports=true, P1.authenticate]
unsupported-then-success => SUCCESS(alice)
  trace=[P1.supports=false, P2.supports=true, P2.authenticate]
null-then-success => SUCCESS(alice)
  trace=[P1.supports=true, P1.authenticate, P2.supports=true, P2.authenticate]
bad-then-success => SUCCESS(alice)
  trace=[P1.supports=true, P1.authenticate, P2.supports=true, P2.authenticate]
bad-then-bad => BadCredentialsException
  trace=[P1.supports=true, P1.authenticate, P2.supports=true, P2.authenticate]
locked-stops => LockedException
  trace=[P1.supports=true, P1.authenticate]
internal-stops => InternalAuthenticationServiceException
  trace=[P1.supports=true, P1.authenticate]
all-unsupported => ProviderNotFoundException
  trace=[P1.supports=false, P2.supports=false]
all-null => ProviderNotFoundException
  trace=[P1.supports=true, P1.authenticate, P2.supports=true, P2.authenticate]
~~~

**Cách đọc trace:** ở `first-success`, P2 thậm chí không được hỏi `supports`. Ở `unsupported-then-success`, P1 được hỏi `supports` nhưng không chạy `authenticate`. Ở `bad-then-success`, lỗi P1 không dừng P2. Ở `locked-stops` và `internal-stops`, P2 hoàn toàn không được hỏi. Hai trường hợp cuối chứng minh `ProviderNotFoundException` có thể xuất hiện vì **không provider nào có khả năng xử lý**, hoặc vì **mọi provider phù hợp đều từ chối đưa ra quyết định**.

Thứ tự các dòng của chương trình do `main` quy định và danh sách `List` giữ nguyên thứ tự chèn. Thông điệp trong exception và log phụ thuộc môi trường; ví dụ chỉ in tên lớp exception để đầu ra dễ kiểm chứng. Những provider mô phỏng trên **không được sử dụng để đưa ra quyết định xác thực thật**, vì chúng cố ý không kiểm credential.

### 6.4. Thử thêm tình huống parent

Thêm vào code (hoặc chạy trong một ví dụ khác) đoạn khái niệm sau khi đã tạo `TracedProvider`:

~~~java
List<String> trace = new ArrayList<>();

ProviderManager parent = new ProviderManager(List.of(
        new TracedProvider("parent", Decision.ACCEPT, trace)));
ProviderManager child = new ProviderManager(
        List.of(new TracedProvider("child", Decision.REJECT, trace)),
        parent);

Authentication result = child.authenticate(
        UsernamePasswordAuthenticationToken.unauthenticated(
                "alice", "demo-credential"));

System.out.println(result.getName());
System.out.println(trace);
~~~

Đây là **đoạn mã tích hợp** (đặt trong phương thức của `ProviderOrderDemo`, không phải một tệp độc lập). Với behavior mô phỏng ở trên, parent vẫn được thử sau `BadCredentialsException` của child và thành công:

~~~text
alice
[child.supports=true, child.authenticate, parent.supports=true, parent.authenticate]
~~~

Thử thay `Decision.REJECT` của child bằng `Decision.LOCKED`: exception bị ném ngay, nên parent không được gọi. Điều này giải thích vì sao không nên dùng lỗi account status như một tín hiệu “thử kho đăng nhập khác”.

## 7. Cấu hình provider trong ứng dụng Spring Security

Thứ tự có thể được xác lập qua danh sách provider truyền vào `ProviderManager` hoặc qua cơ chế cấu hình bảo mật tương ứng. Ví dụ tích hợp với các provider **đã được hiện thực và kiểm tra thật**:

~~~java
@Bean
AuthenticationManager authenticationManager(
        CorporateAuthenticationProvider corporateProvider,
        PartnerAuthenticationProvider partnerProvider) {

    return new ProviderManager(List.of(corporateProvider, partnerProvider));
}
~~~

Đoạn này là **phác thảo cấu hình**: cần có hai lớp provider thật và các import cho `@Bean`, `AuthenticationManager`, `ProviderManager`, `List`. Nó mô tả rõ thứ tự `corporateProvider` trước `partnerProvider`. Với Spring Boot, tự định nghĩa `AuthenticationManager` có thể ảnh hưởng cấu hình tự động; phải xác nhận filter chain nào thực sự sử dụng manager này.

Các câu hỏi cần trả lời trước khi triển khai:

- Hai provider hỗ trợ **cùng một** `Authentication` Java type hay các type khác nhau?
- Nếu cùng hỗ trợ, khi một provider báo user/password sai, provider sau **có được phép** xác thực bằng một kho danh tính khác không?
- Có trường hợp tài khoản bị khóa ở kho thứ nhất nhưng được mở ở kho thứ hai không? Nếu có, hệ thống đang áp dụng chính sách nào?
- Một username trùng nhau ở hai kho có thuộc cùng một người? Làm sao gắn issuer/realm/tenant để không nhập nhằng?
- Ai tạo token kết quả và gán authorities? Quyền có được lấy từ nguồn tin cậy không?
- Có parent manager? Nó được gọi trong tình huống nào và những quyền nào có thể được cấp từ parent?
- Đã kiểm tra thứ tự thực tế ở môi trường chạy chưa?

**Không giả định thứ tự Spring bean được tìm thấy bằng component scan, tên lớp, hoặc `@Order` luôn chính là thứ tự trong manager đang chạy.** Thứ tự quyết định là danh sách providers mà instance `ProviderManager` thực tế sử dụng. Nếu cần thứ tự chính xác, cấu hình danh sách rõ ràng và kiểm chứng bằng integration test.

### 7.1. Các cơ chế khác nhau thường có token request khác nhau

Trong một ứng dụng có nhiều cách đăng nhập, filter phù hợp tạo loại `Authentication` request và chuyển đến manager. Ví dụ:

- Username/password: thường dùng `UsernamePasswordAuthenticationToken` và provider kiểm password như `DaoAuthenticationProvider`.
- Bearer token: thường đi qua `BearerTokenAuthenticationFilter`, với provider/manager phù hợp để kiểm JWT hoặc opaque access token.
- OAuth2/OIDC login: đường xử lý dành cho authorization code/OIDC, có provider và token type riêng.

Khi các provider hỗ trợ type khác nhau, `supports` giúp bỏ qua provider không liên quan. Khi nhiều provider cùng nhận một type, thứ tự/fallback cần được xem là chính sách đăng nhập thực sự, không chỉ là chi tiết hiệu năng.

### 7.2. Thứ tự provider khác thứ tự filter và SecurityFilterChain

Trong ứng dụng Servlet:

1. `FilterChainProxy` chọn `SecurityFilterChain` phù hợp request.
2. Authentication filter tương ứng nhận credential/request và có thể gọi `AuthenticationManager`.
3. `ProviderManager` chọn provider **bên trong danh sách của nó**.
4. Sau thành công, filter/cơ chế bảo mật quản lý kết quả trong `SecurityContext`, xử lý session nếu cần.
5. Authorization filter hoặc method security kiểm chính sách truy cập.

`ProviderManager` **không tự xử lý URL, không tự viết HTTP 401/403, và không tự bảo đảm lưu `Authentication` vào `SecurityContext`**. HTTP response trên web còn phụ thuộc authentication entry point, failure handler và access denied handler. Vì vậy quan sát 401/403 giúp chẩn đoán, nhưng không đủ để khẳng định provider nào đã chạy nếu chưa có trace/test tương ứng.

## 8. Sau kết quả thành công: credentials, details và event

### 8.1. Xóa credentials để giảm rủi ro

Theo mặc định, `ProviderManager` cố gắng xóa thông tin credential nhạy cảm khỏi **kết quả `Authentication`** sau khi xác thực thành công, nếu kết quả triển khai `CredentialsContainer`. Thuộc tính `eraseCredentialsAfterAuthentication` điều khiển hành vi này (mặc định là `true`).

Việc xóa có thể ảnh hưởng object được chia sẻ trong cache nếu chính object đó cũng triển khai `CredentialsContainer`. Khi dùng cache `UserDetails`/principal, cần thiết kế cách copy và cache phù hợp; **không nên tắt xóa credentials chỉ để sửa một bug cache mà chưa đánh giá tác động bảo mật**.

Credential bị xóa sau thành công **không có nghĩa** password/JWT chưa từng được xác minh; cũng không có nghĩa mọi dữ liệu nhạy cảm trong mọi object của ứng dụng đều tự động được xóa.

### 8.2. Sao chép details

Khi provider trả kết quả thành công mà kết quả là `AbstractAuthenticationToken` có `details` chưa được thiết lập, `ProviderManager` có thể sao chép `details` từ request sang result. Đó là thông tin bổ trợ, ví dụ một số thông tin của HTTP request; không được biến details do client tự khai thành authorities đáng tin.

### 8.3. Authentication event

`ProviderManager` có thể gọi `AuthenticationEventPublisher` để phát sự kiện xác thực thành công/thất bại. **Mặc định của bản thân `ProviderManager` là publisher không phát sự kiện**; ứng dụng/framework phải cung cấp publisher phù hợp nếu muốn quan sát các sự kiện đó. Đừng khẳng định luôn có event chỉ vì provider chạy.

Một manager có parent cần tránh ghi nhận trùng event khi parent đã phát sự kiện. Khi thiết lập event publisher riêng cho nhiều manager, kiểm tra trường hợp child gọi parent để bảo đảm đếm audit chính xác.

**Không ghi raw password, API key, access token hoặc secret vào log trace.** Để xem thứ tự provider, chỉ log loại request, tên provider, kết quả phân loại và correlation ID an toàn.

## 9. Thiết kế test có thể bảo vệ chính sách fallback

Ví dụ console ở mục 6 xác minh đường đi thuật toán. Trong ứng dụng thật cần test ít nhất các lớp hành vi sau:

| Test | Dựng tình huống | Điều cần khẳng định |
| --- | --- | --- |
| Bỏ qua provider không hỗ trợ | P1 `supports=false`, P2 hỗ trợ và xác thực | P1 không chạy `authenticate`; P2 được gọi |
| Abstain | P1 trả `null`, P2 xác thực | P2 được gọi; không nhầm null với thành công |
| Thành công sớm | P1 thành công, P2 bất kỳ | P2 không được gọi, kể cả `supports` |
| Credential bị từ chối rồi fallback | P1 ném `BadCredentialsException`, P2 xác thực | P2 **có thể** thành công; kiểm xem nghiệp vụ có cho phép điều đó không |
| Tất cả từ chối | P1/P2 ném lỗi thường | Thất bại; exception cuối được dùng |
| Không provider nào xử lý | Mọi `supports=false` hoặc mọi `authenticate=null` | `ProviderNotFoundException` nếu không có parent và lỗi trước |
| Tài khoản bị khóa | P1 ném `LockedException`, P2 có thể xác thực | P2 và parent không được gọi |
| Lỗi nội bộ | P1 ném `InternalAuthenticationServiceException` | Không thử provider khác; lỗi được truyền lên |
| Parent fallback | Child không tạo result, parent xác thực | Parent được gọi sau các provider con |
| Phân quyền sau xác thực | Provider trả principal đúng nhưng thiếu authority cần thiết | Endpoint bảo vệ vẫn từ chối; xác thực khác phân quyền |

**Test thật nên kiểm provider invocation** (counter/mock/spy an toàn) và loại exception ở tầng `AuthenticationManager`. Một test chỉ kiểm HTTP 401/403 có thể bỏ sót chính sách fallback nguy hiểm. Test đăng nhập thật cần kiểm filter/provider/encoder/decoder bằng dữ liệu credential đã kiểm; việc dùng `@WithMockUser` chỉ giúp test lớp quyền, không chứng minh password/JWT đã được xác minh.

### 9.1. Case nguy hiểm: fallback vô ý thay đổi ý nghĩa “sai mật khẩu”

Giả sử hệ thống dùng hai kho người dùng:

~~~text
P1: CorporatePasswordProvider (username/password)
P2: LegacyPasswordProvider    (cũng username/password)
~~~

Khi P1 thấy username “alice” nhưng password sai, ném `BadCredentialsException`; P2 vẫn có thể chạy và chấp nhận cùng username/password theo kho legacy. Lúc này hành vi thực tế là “chỉ cần **một** trong hai kho chấp nhận”, không phải “corporate là nguồn xác thực bắt buộc”.

Nếu đó là ý định của hệ thống, phải quản lý rõ liên kết danh tính, phân quyền và trạng thái khóa. Nếu không, cần thiết kế phân tuyến danh tính trước xác thực, dùng realm hoặc token type riêng, hoặc tách manager/chain để việc thử provider thứ hai chỉ diễn ra khi hợp lệ theo nghiệp vụ. **Không kỳ vọng `BadCredentialsException` của P1 tự chặn P2**.

### 9.2. Phân biệt “không biết user” và “user sai credential”

Một provider không tìm thấy user ở kho của mình có thể đưa ra các quyết định khác nhau theo hợp đồng và thiết kế bảo mật. Với một số `UserDetailsService`/provider chuẩn, không tìm thấy user được xử lý như lỗi credentials để giảm tiết lộ user enumeration. Không tự coi “không tìm thấy user” luôn phải là `null`, hoặc luôn phải là một loại exception cố định cho mọi provider.

Mục tiêu là **giữ chính sách xác thực nhất quán**, tránh để thông tin lỗi hoặc thời gian phản hồi tiết lộ account tồn tại ở kho nào. Không sử dụng `supports(...)` để kiểm username tồn tại bằng một truy vấn từ xa; phương thức này nhận **Class<?>**, không nhận dữ liệu của request.

## 10. Lỗi thường gặp khi đọc hoặc triển khai ProviderManager

1. **“Provider đầu ném exception nghĩa là manager dừng.”** Sai với nhiều `AuthenticationException` thông thường; provider tiếp theo vẫn có thể được thử, và nếu thành công sẽ thắng.
2. **“`supports=true` nghĩa là password đúng.”** Sai; nó mới kiểm khả năng xử lý một loại `Authentication`.
3. **“Provider muốn nhường nên ném `BadCredentialsException`.”** Đây là kết luận xác thực thất bại, khác với `null` (không thể quyết định); có thể ảnh hưởng lỗi cuối và audit.
4. **“`authenticate=null` nghĩa là đăng nhập ẩn danh được phép.”** Sai; null chỉ là provider không quyết định; toàn bộ manager vẫn cần kết quả thành công.
5. **“Mọi provider đều null thì manager trả null.”** Sai trong tình huống không có parent kết quả: manager ném `ProviderNotFoundException`.
6. **“Tất cả lỗi dịch vụ đều thử provider khác.”** Sai với `InternalAuthenticationServiceException`; manager dừng ngay.
7. **“Tài khoản bị khóa ở P1 thì P2 vẫn có thể thử.”** Không khi provider thực sự ném `AccountStatusException`.
8. **“Sắp xếp class theo tên hoặc chỉ thêm `@Order` là đủ.”** Cần kiểm danh sách và instance manager thực sự được filter sử dụng.
9. **“Provider trả một token khác null là đủ an toàn.”** Provider phải tự kiểm credential/chữ ký/trạng thái và cấp quyền từ nguồn đáng tin; manager không kiểm lại nội dung đó.
10. **“ProviderManager trả success thì endpoint đã có quyền.”** Authorization vẫn cần kiểm authority, scope, ownership và tenant.
11. **“Không thấy event là provider không chạy.”** Event phụ thuộc `AuthenticationEventPublisher` và cấu hình.
12. **“ProviderManager tự trả HTTP 401.”** Manager xử lý kết quả Java; HTTP status do tầng web security/failure handling quyết định.

## 11. Câu hỏi tự kiểm tra

**Câu 1:** P1 `supports=true` nhưng trả `null`, P2 thành công. Điều gì xảy ra?  
**Đáp án:** P2 được gọi; manager trả kết quả P2. `null` của P1 nghĩa là “không quyết định”.

**Câu 2:** P1 ném `BadCredentialsException`, P2 thành công với cùng request. Kết quả là gì?  
**Đáp án:** Theo cách duyệt `ProviderManager`, kết quả P2 được dùng. Cần rà lại liệu fallback đó có đúng chính sách xác thực không.

**Câu 3:** P1 ném `DisabledException`, P2 có thể xác thực. P2 có được thử không?  
**Đáp án:** Không. `DisabledException` là `AccountStatusException`; manager dừng và ném lỗi ngay.

**Câu 4:** P1 và P2 cùng trả `null`; không có parent. Đầu ra của `authenticate` là gì?  
**Đáp án:** `ProviderNotFoundException`, không phải `null`.

**Câu 5:** P1 ném `BadCredentialsException`, P2 không hỗ trợ, parent xác thực thành công. Kết quả cuối là gì?  
**Đáp án:** Parent vẫn có cơ hội xác thực sau khi các provider con không cho kết quả, trừ các nhánh exception dừng ngay.

**Câu 6:** Một provider trả token đã authenticated với `ROLE_ADMIN` nhưng không kiểm password. Có đúng không vì `ProviderManager` nhận kết quả?  
**Đáp án:** Không. Đây là lỗi xác thực nghiêm trọng ở provider. Manager tin kết quả khác `null`; provider có nghĩa vụ xác minh bằng chứng và authorities.

**Câu 7:** Làm sao biết P2 đã được gọi trong lần login thực tế?  
**Đáp án:** Test spy/counter hoặc logging an toàn ở `supports`/`authenticate`; đừng kết luận chỉ từ HTTP status hoặc thứ tự bean mặc định.

**Câu 8:** Vì sao một API trả 403 dù `ProviderManager` đã xác thực thành công?  
**Đáp án:** Principal có thể thiếu authority/quyền trên tài nguyên; xác thực và phân quyền là hai giai đoạn độc lập.

## 12. Checklist thiết kế và ghi nhớ

Trước khi chấp thuận chuỗi provider, hãy trả lời đầy đủ:

- Các provider nhận **type `Authentication` nào**? Có bao nhiêu provider cùng hỗ trợ một type?
- Với từng provider, **`null`, exception thông thường, exception dừng ngay và success** được dùng trong tình huống nghiệp vụ nào?
- Nếu provider trước từ chối credential, provider sau được phép thử theo chính sách nào? Có thể làm vô hiệu chính sách khóa hoặc MFA không?
- Parent `AuthenticationManager` có tham gia không? Khi nào? Có thể thay đổi quyết định xác thực hoặc event không?
- Credential có bị xóa khỏi kết quả sau thành công? Có object cache chia sẻ cần lưu ý không?
- Test đã đo thứ tự gọi provider, các nhánh ngoại lệ và kiểm quyền sau xác thực chưa?

**Quy tắc nhớ nhanh:** `ProviderManager` duyệt provider theo **thứ tự**, bỏ qua provider không hỗ trợ, tiếp tục khi provider trả `null`, **dừng khi nhận kết quả khác null**; lỗi xác thực thường có thể cho phép thử tiếp, trong khi `AccountStatusException` và `InternalAuthenticationServiceException` dừng ngay. Nếu không ai xác thực thành công, manager có thể hỏi parent rồi ném lỗi phù hợp. Thứ tự provider vì thế là một phần của **chính sách xác thực**, cần được thiết kế và kiểm thử.

### Tài liệu chính thức để đối chiếu

- Spring Security — Servlet Authentication Architecture, `ProviderManager`: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html
- `ProviderManager` API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/ProviderManager.html
- `AuthenticationProvider` API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/AuthenticationProvider.html
- `AuthenticationManager` API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/AuthenticationManager.html
- Mã nguồn `ProviderManager` để kiểm tra nhánh exception/parent/event: https://github.com/spring-projects/spring-security/blob/6.5.x/core/src/main/java/org/springframework/security/authentication/ProviderManager.java
