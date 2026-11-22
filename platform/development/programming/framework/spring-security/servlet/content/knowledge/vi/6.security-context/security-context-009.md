# Tạo SecurityContext mới để tránh chia sẻ đối tượng giữa các request

## 1. Vấn đề cần giải quyết

Trong Spring Security trên **Servlet stack**, thông tin bảo mật của luồng xử lý thường được truy cập qua `SecurityContextHolder`. Đối tượng `SecurityContext` chứa `Authentication` hiện tại: danh tính, các quyền và trạng thái xác thực. Khi lập trình viên tự xử lý đăng nhập, thay đổi danh tính hoặc viết filter riêng, một thao tác rất dễ nhầm là lấy context có sẵn rồi sửa trực tiếp:

~~~java
// Dễ gây vấn đề nếu context hiện tại đang được chia sẻ qua repository/session.
SecurityContextHolder.getContext().setAuthentication(authentication);
~~~

Cú pháp này có thể chạy bình thường nhưng **đang thay đổi nội dung của đối tượng context hiện có**. Trong một số cấu hình, đặc biệt khi `SecurityContext` được lấy từ cùng `HttpSession` cho các request đồng thời, các request có thể nhận **tham chiếu tới cùng một đối tượng**. Thay đổi `Authentication` ngay trên đối tượng đó có thể khiến request khác quan sát danh tính/quyền bị đổi giữa chừng.

Khi thực sự cần đặt một `Authentication` mới, cách an toàn hơn là:

~~~java
SecurityContext freshContext = SecurityContextHolder.createEmptyContext();
freshContext.setAuthentication(authenticated);
SecurityContextHolder.setContext(freshContext);
~~~

Nếu đây là **đăng nhập cần duy trì sang request tiếp theo**, còn phải lưu context bằng `SecurityContextRepository` phù hợp. **Tạo context mới** và **lưu context** là hai việc khác nhau.

Bài này giúp hiểu vì sao mẫu trên giảm nguy cơ chia sẻ đối tượng, cách dùng trong Spring Security 6/Spring Boot 3, điều gì vẫn phải xử lý ở tầng session/async, và các lỗi thường xảy ra. Trọng tâm là **ngữ cảnh bảo mật Servlet**, không phải mô hình `ReactiveSecurityContextHolder` của WebFlux.

## 2. Phân biệt SecurityContextHolder, SecurityContext và Authentication

| Thành phần | Chức năng | Lưu ý |
| --- | --- | --- |
| `SecurityContextHolder` | Cung cấp API `getContext()`, `setContext()`, `clearContext()` và strategy lưu context cho mã hiện tại | Là nơi truy cập context, không phải danh tính người dùng |
| `SecurityContextHolderStrategy` | Xác định cách liên kết context với luồng xử lý, mặc định thường là `ThreadLocal` | Strategy không đảm bảo đối tượng được đặt vào nó không bị chia sẻ |
| `SecurityContext` | Đối tượng chứa `Authentication` | Có thể là đối tượng mutable; các request có thể cùng trỏ vào một instance nếu được cấp như vậy |
| `Authentication` | Đại diện principal, authorities, credentials và trạng thái authentication | Có thể chứa dữ liệu/đối tượng mutable; chỉ dùng kết quả từ cơ chế xác thực tin cậy |
| `SecurityContextRepository` | Tải/lưu context giữa request và response theo chính sách đã cấu hình | Có thể sử dụng request attribute, HTTP session hoặc repository khác |
| `SecurityContextHolderFilter` | Trên Spring Security 6, thường thiết lập cách đọc context cho request và dọn holder sau khi xử lý | Không được mặc định cho rằng mọi `setContext` đều được tự động lưu vĩnh viễn |

Ví dụ đọc thông tin người dùng trong một phương thức đã được bảo vệ:

~~~java
Authentication current =
    SecurityContextHolder.getContext().getAuthentication();

if (current != null) {
    String username = current.getName();
    // Chỉ đọc thông tin thích hợp; không tự suy ra đủ quyền truy cập dữ liệu.
}
~~~

Mã trên là **mảnh Java minh họa**, không phải ứng dụng độc lập. Một số request có anonymous authentication; vì vậy `getAuthentication() != null` **không đủ** để kết luận người dùng đã đăng nhập thật. Khi đặt quy tắc bảo vệ endpoint, ưu tiên `authenticated()`, `hasRole(...)`, `hasAuthority(...)` và kiểm tra quyền nghiệp vụ thích hợp.

### ThreadLocal không đồng nghĩa mỗi request có một đối tượng context riêng

Theo mặc định trên Servlet stack, `SecurityContextHolder` thường dùng strategy dựa trên `ThreadLocal`. Điều đó giúp mã trên thread A và thread B có **ô lưu tham chiếu khác nhau**, nhưng không ngăn hai ô này cùng chứa **một tham chiếu đến cùng object**.

~~~text
Thread xử lý request A             Thread xử lý request B
       |                                  |
ThreadLocal của A                  ThreadLocal của B
       |                                  |
       +----------- cùng tham chiếu ------+
                       |
                       v
                SecurityContext X
                       |
                       v
               Authentication hiện tại
~~~

Giả sử hai request của một phiên đăng nhập cùng lấy context X từ một nguồn lưu trữ trả về cùng tham chiếu, hoặc code tự chuyển cùng đối tượng X cho hai thread. Nếu request B chạy `X.setAuthentication(bob)`, request A cũng có thể nhìn thấy `bob` khi đọc từ X sau đó. Đó là **chia sẻ đối tượng mutable**, không phải Spring Security “trộn” hai `ThreadLocal` thành một.

Cũng cần tránh kết luận cực đoan: **không phải mọi request mặc định đều dùng chung chính một `SecurityContext`**. Điều đó phụ thuộc repository, phiên đăng nhập, cách nạp/lưu và việc chuyển tham chiếu của ứng dụng. Hãy phân biệt **khả năng xảy ra khi có đối tượng dùng chung** với hành vi chắc chắn của mọi deployment.

## 3. Vì sao sửa trực tiếp context cũ có thể gây race condition?

Đoạn mã:

~~~java
SecurityContext context = SecurityContextHolder.getContext();
context.setAuthentication(newAuthentication);
~~~

không tạo `SecurityContext` mới. Nó sửa instance được trả về. Nếu instance đó vẫn đang được request khác sử dụng, bạn đã thay đổi dữ liệu mà request khác có thể đọc đồng thời.

Hệ quả có thể bao gồm:

1. **Danh tính thay đổi trong lúc xử lý:** request A bắt đầu với `alice`, nhưng trong một lần đọc context sau đó lại thấy `bob`.
2. **Quyền bị đọc lệch:** một nhánh authorization hoặc code nghiệp vụ dùng `Authentication` cũ, nhánh khác dùng authentication mới.
3. **Rò rỉ trạng thái giữa các request cùng session:** đặc biệt khi có đăng nhập lại, đổi tài khoản, nâng quyền, thay danh tính hoặc code tự sửa context.
4. **Khó tái hiện:** lỗi phụ thuộc thời điểm chạy của nhiều thread nên có thể chỉ xuất hiện khi tải cao.
5. **Khó kiểm tra bằng code review đơn giản:** nhìn `ThreadLocal` dễ tưởng mọi thứ đã hoàn toàn cách ly, nhưng aliasing nằm ở **object được lưu**, không nằm ở biến ThreadLocal.

Một ví dụ lập luận theo thời gian:

| Thời điểm | Request A | Request B |
| --- | --- | --- |
| T1 | Nhận tham chiếu context X, authentication là alice | Chưa xử lý |
| T2 | Đang thực hiện kiểm tra nghiệp vụ | Cũng nhận context X |
| T3 | Chưa thay đổi local reference | Gọi `X.setAuthentication(bob)` |
| T4 | Đọc lại `X.getAuthentication()` và có thể thấy bob | Tiếp tục xử lý với bob |

Đây là mô hình **minh họa có điều kiện**: bảng giả định A và B đã cùng giữ X. Mục tiêu là nhận ra lỗi object sharing, không khẳng định rằng Spring Security luôn tự tạo lỗi này.

### Không “sửa” bằng synchronized quanh mọi request

Khóa đồng bộ trên context có thể khiến các request cùng session phải chờ nhau, khó mở rộng và vẫn không giải quyết chuyện một request quan sát trạng thái do request khác chủ động ghi. Thay vào đó, đối với lần **thay đổi authentication**, hãy tạo **một context mới** rồi đặt context mới vào holder của luồng hiện tại; thiết kế riêng chính sách lưu phiên khi cần.

## 4. Mẫu đúng: createEmptyContext → setAuthentication → setContext

Khi đã xác thực credentials qua cơ chế tin cậy, dùng:

~~~java
Authentication authenticated = authenticationManager.authenticate(
    UsernamePasswordAuthenticationToken.unauthenticated(
        username, rawPassword
    )
);

// Quan trọng: context mới, không chỉnh context đang tồn tại.
SecurityContext newContext = SecurityContextHolder.createEmptyContext();
newContext.setAuthentication(authenticated);
SecurityContextHolder.setContext(newContext);
~~~

Đây là **snippet tích hợp**; `authenticationManager`, `username`, `rawPassword` phải được khai báo/được cấp từ luồng authentication thật. Cần có import các kiểu từ Spring Security. Nó **không phải một endpoint đăng nhập hoàn chỉnh**.

Ý nghĩa của từng bước:

- **`authenticationManager.authenticate(...)`:** xác minh thông tin đầu vào qua `AuthenticationProvider` tương ứng. Kết quả được trả về nếu thành công; nếu thất bại thường có `AuthenticationException`. Không dùng tên do client tự nhập làm `Authentication` đã xác thực.
- **`SecurityContextHolder.createEmptyContext()`:** tạo đối tượng context mới thông qua `SecurityContextHolderStrategy` hiện hành, tránh sửa instance context đã lấy từ repository/session.
- **`newContext.setAuthentication(authenticated)`:** đặt kết quả authentication đã được kiểm chứng vào context mới.
- **`SecurityContextHolder.setContext(newContext)`:** thay **tham chiếu context** đang gắn với luồng thực thi hiện tại bằng instance mới.
- **Lưu context nếu cần:** quyết định sau đó của `SecurityContextRepository`/cơ chế xác thực liệu danh tính mới cần tồn tại qua các HTTP request.

Mẫu này tương ứng với hướng dẫn của Spring Security khi lập trình viên chủ động thay authentication: tạo context mới để tránh race condition giữa các thread dùng chung một `SecurityContext`.

### Vì sao không dùng new SecurityContextImpl() mọi nơi?

`new SecurityContextImpl()` có thể tạo context mặc định trực tiếp. Tuy nhiên `SecurityContextHolder.createEmptyContext()` biểu đạt ý định tốt hơn và tôn trọng `SecurityContextHolderStrategy` được ứng dụng lựa chọn. Nếu ứng dụng thay strategy, code dùng factory của holder dễ tương thích hơn. Điểm cốt lõi vẫn là **một instance mới**.

### Mẫu sai rất nguy hiểm: tự cấp quyền cho client

~~~java
// KHÔNG sử dụng trong ứng dụng: client tự khai "admin" rồi được tin ngay.
Authentication forged = new UsernamePasswordAuthenticationToken(
    "admin", null, List.of(new SimpleGrantedAuthority("ROLE_ADMIN"))
);
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(forged);
SecurityContextHolder.setContext(context);
~~~

Đây là **ví dụ phản diện**. Constructor ba tham số tạo token đã được đánh dấu authenticated; nó chỉ phù hợp cho dữ liệu đã được hệ thống kiểm chứng hoặc bài test có chủ đích. Đưa username/role do request tự gửi vào constructor này sẽ tạo lỗ hổng giả mạo danh tính. **Context mới không biến credentials sai thành đúng**; authentication phải đến từ provider/manager được tin cậy.

## 5. Bước thường bị quên: lưu SecurityContext sau đăng nhập

**Chỉ gọi `SecurityContextHolder.setContext(newContext)`** thường làm context mới hiện diện trong *luồng xử lý hiện tại*. Nó **không bảo đảm** request tiếp theo sẽ được nhận diện là đã đăng nhập. Muốn duy trì authentication bằng session, hãy để flow đăng nhập chuẩn của Spring Security quản lý hoặc lưu context qua repository phù hợp.

Trong Spring Security 6, cấu hình phổ biến dùng `SecurityContextHolderFilter` và yêu cầu **explicit save**: nếu ứng dụng **tự thực hiện authentication**, cần gọi `SecurityContextRepository.saveContext(...)` khi muốn lưu. Không nên dựa vào việc chỉ set holder rồi giả định framework sẽ ghi session cho bạn.

Snippet kết hợp khi ứng dụng tự xác thực:

~~~java
Authentication authenticated = authenticationManager.authenticate(
    UsernamePasswordAuthenticationToken.unauthenticated(
        username, rawPassword
    )
);

SecurityContext newContext = SecurityContextHolder.createEmptyContext();
newContext.setAuthentication(authenticated);
SecurityContextHolder.setContext(newContext);

// Chỉ khi muốn giữ authentication qua các request với repository đã cấu hình.
securityContextRepository.saveContext(newContext, request, response);
~~~

Các biến `securityContextRepository`, `request` (`HttpServletRequest`) và `response` (`HttpServletResponse`) phải có trong luồng xử lý Servlet. Đây là **mảnh tích hợp trong custom authentication flow**, không phải hướng dẫn bỏ qua các bước xử lý session fixation, CSRF, remember-me, failure handler hoặc success handler. Nếu dùng `formLogin()` hay cơ chế chuẩn của Spring Security, hãy ưu tiên để filter/handler chuẩn làm đúng quy trình thay vì viết lại thủ công.

### SecurityContextRepository có thể lưu ở đâu?

| Repository hoặc nguồn | Dùng cho điều gì | Hệ quả cần hiểu |
| --- | --- | --- |
| `RequestAttributeSecurityContextRepository` | Giữ context trong thuộc tính request, hữu ích qua một số dispatcher type | Không tự tạo login session tồn tại qua HTTP request mới |
| `HttpSessionSecurityContextRepository` | Lưu context vào HTTP session khi có điều kiện phù hợp | Request cùng session có thể truy cập thông tin trạng thái chung; tránh sửa trực tiếp context được chia sẻ |
| `DelegatingSecurityContextRepository` | Kết hợp nhiều repository theo cách cấu hình | Cần hiểu delegate nào đọc/lưu context và khi nào |
| `NullSecurityContextRepository` | Không lưu authentication giữa các request | Thích hợp cho một số mô hình stateless; request mới phải xác thực lại |

Spring Security 6 có thể cấu hình `DelegatingSecurityContextRepository` gồm request-attribute và HTTP-session repository trong các cấu hình thông thường. Nhưng danh sách mặc định thực tế còn phụ thuộc filter chain và framework version. Không tự đoán repository hiện hành chỉ từ việc ứng dụng có `spring-boot-starter-security`.

### Context mới không đồng nghĩa Session mới

Tạo `SecurityContext` mới là tạo **đối tượng Java mới**; không đồng nghĩa tạo `HttpSession` mới hoặc đổi session ID. Chính sách session fixation protection (ví dụ thay session ID sau login) là một cơ chế **khác**. Khi xây custom login, cần tính tới cả việc lưu context, session fixation, CSRF, lỗi đăng nhập và logout đúng cách.

### Điều gì xảy ra khi có hai request đồng thời thay đổi cùng phiên?

Hai request đồng thời có thể tạo **hai context khác nhau**, cả hai đều gọi `saveContext` và dẫn tới kết quả lưu sau cùng có hiệu lực trong session. Điều đó tránh được việc cùng sửa **một instance đang được sử dụng**, nhưng không tự giải quyết xung đột logic “request nào được phép thay đổi trạng thái phiên sau cùng”. Ứng dụng yêu cầu chuyển tài khoản, nâng quyền hoặc login nhiều thiết bị cần thiết kế quy tắc session và đồng bộ nghiệp vụ tương ứng.

## 6. Code Java 17+ chạy được: mô phỏng lỗi chia sẻ và cách tạo context riêng

Để quan sát rõ sự khác nhau giữa **hai thread có ThreadLocal riêng nhưng trỏ cùng object** và **mỗi thread dùng context mới**, ví dụ sau sử dụng `spring-security-core` và Java concurrency chuẩn. Nó **không** mở HTTP server hoặc xác thực credentials thật; token giả lập chỉ nhằm kiểm chứng identity trong một phép mô phỏng có kiểm soát.

### Cấu trúc project

~~~text
security-context-isolation/
├── pom.xml
└── src/main/java/demo/ContextIsolationDemo.java
~~~

**`pom.xml`**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>security-context-isolation</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-core</artifactId>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Boot parent ở đây chỉ quản lý phiên bản dependency và compiler; demo chạy như một **chương trình Java main**, không tạo ứng dụng web. Vì không có Servlet request thực, mã cố ý đặt context vào thread để mô phỏng những tham chiếu được cấp từ session hoặc từ ứng dụng.

**`src/main/java/demo/ContextIsolationDemo.java`**

~~~java
package demo;

import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;

public class ContextIsolationDemo {

    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newFixedThreadPool(2);
        try {
            sharedObjectCase(executor);
            independentObjectsCase(executor);
        } finally {
            executor.shutdownNow();
        }
    }

    // Chỉ phục vụ mô phỏng; KHÔNG dùng constructor authenticated
    // với principal/role chưa được AuthenticationManager kiểm chứng.
    private static Authentication testOnlyAuthentication(String name) {
        return new UsernamePasswordAuthenticationToken(
            name,
            null,
            List.of(new SimpleGrantedAuthority("ROLE_USER"))
        );
    }

    private static void sharedObjectCase(ExecutorService executor)
            throws Exception {

        // Cả hai tác vụ sẽ được cấp CÙNG tham chiếu SecurityContext.
        SecurityContext shared = SecurityContextHolder.createEmptyContext();
        shared.setAuthentication(testOnlyAuthentication("alice"));

        CountDownLatch firstBound = new CountDownLatch(1);
        CountDownLatch secondChanged = new CountDownLatch(1);

        Future<String> requestA = executor.submit(() -> {
            SecurityContextHolder.setContext(shared);
            try {
                firstBound.countDown();
                if (!secondChanged.await(5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException("Request B timed out");
                }
                return SecurityContextHolder.getContext()
                    .getAuthentication().getName();
            } finally {
                SecurityContextHolder.clearContext();
            }
        });

        Future<String> requestB = executor.submit(() -> {
            if (!firstBound.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Request A timed out");
            }
            SecurityContextHolder.setContext(shared);
            try {
                // Sửa tại chỗ đối tượng mà request A cũng đang dùng.
                SecurityContextHolder.getContext().setAuthentication(
                    testOnlyAuthentication("bob")
                );
                secondChanged.countDown();
                return SecurityContextHolder.getContext()
                    .getAuthentication().getName();
            } finally {
                SecurityContextHolder.clearContext();
            }
        });

        String b = requestB.get();
        String a = requestA.get();
        System.out.println("Shared - request A sees: " + a);
        System.out.println("Shared - request B sees: " + b);
    }

    private static void independentObjectsCase(ExecutorService executor)
            throws Exception {

        CountDownLatch bothReady = new CountDownLatch(2);

        Future<String> requestA = executor.submit(() -> {
            SecurityContext fresh = SecurityContextHolder.createEmptyContext();
            fresh.setAuthentication(testOnlyAuthentication("alice"));
            SecurityContextHolder.setContext(fresh);
            try {
                bothReady.countDown();
                if (!bothReady.await(5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException("Request B timed out");
                }
                return SecurityContextHolder.getContext()
                    .getAuthentication().getName();
            } finally {
                SecurityContextHolder.clearContext();
            }
        });

        Future<String> requestB = executor.submit(() -> {
            SecurityContext fresh = SecurityContextHolder.createEmptyContext();
            fresh.setAuthentication(testOnlyAuthentication("bob"));
            SecurityContextHolder.setContext(fresh);
            try {
                bothReady.countDown();
                if (!bothReady.await(5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException("Request A timed out");
                }
                return SecurityContextHolder.getContext()
                    .getAuthentication().getName();
            } finally {
                SecurityContextHolder.clearContext();
            }
        });

        System.out.println("Independent - request A sees: " + requestA.get());
        System.out.println("Independent - request B sees: " + requestB.get());
    }
}
~~~

### Chạy chương trình

Yêu cầu JDK 17+, Maven và có mạng khi lần đầu tải dependency. Từ thư mục chứa `pom.xml`:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.ContextIsolationDemo
~~~

**Kết quả chuẩn kỳ vọng** từ mã này:

~~~text
Shared - request A sees: bob
Shared - request B sees: bob
Independent - request A sees: alice
Independent - request B sees: bob
~~~

Giải thích từng trường hợp:

- **Shared:** request A đặt cùng `shared` vào ThreadLocal của mình; request B cũng đặt **chính tham chiếu đó** rồi sửa `Authentication` thành bob. Latch bắt buộc B sửa trước khi A đọc lại, nên A thấy bob, dù A không từng gọi `setAuthentication(bob)`.
- **Independent:** mỗi request gọi `createEmptyContext()` và tạo authentication riêng. Hai thread có context instance khác nhau; A tiếp tục nhìn alice, B nhìn bob.
- **`clearContext()` trong finally:** vì đây là thread pool tự quản lý, phải dọn holder sau khi hoàn thành để luồng được tái sử dụng không mang trạng thái cũ.

Đây là **mô phỏng minh họa race do object aliasing**, không phải tuyên bố mọi session repository luôn chia sẻ cùng context. Mã dùng latch để cố định trình tự quan sát, nên stdout không phụ thuộc vào việc request nào được scheduler chạy nhanh hơn (nếu không có timeout hoặc sự cố hệ thống). Token test đã được tạo ở trạng thái authenticated **chỉ để mô phỏng**; không làm thế với dữ liệu HTTP chưa xác minh.

## 7. Đưa nguyên tắc vào ứng dụng Servlet thật

Trong ứng dụng Servlet, bạn thường **không tự viết code gán context tại mọi controller**. `SecurityFilterChain` và authentication filter chuẩn của Spring Security đã quản lý security context theo cơ chế của chúng. Việc chủ động tạo context mới hữu ích nhất khi bạn **tự xây quy trình xác thực**, ví dụ custom authentication filter hoặc một endpoint login đặc thù.

Pseudo-flow đúng về mặt trách nhiệm:

~~~text
HTTP POST login
  -> Spring Security / custom authentication component nhận credentials
  -> AuthenticationManager xác minh thông tin
  -> Nhận Authentication đã xác thực từ provider
  -> Tạo SecurityContext MỚI
  -> Gắn Authentication vào context mới
  -> SecurityContextHolder.setContext(context mới)
  -> Xử lý bảo vệ session fixation / success / failure theo flow
  -> SecurityContextRepository.saveContext nếu login cần session
  -> Trả response
  -> Spring Security dọn holder của request
~~~

Đoạn mã lõi để đặt sau bước xác thực thành công:

~~~java
Authentication result = authenticationManager.authenticate(
    UsernamePasswordAuthenticationToken.unauthenticated(
        username, rawPassword
    )
);

SecurityContext fresh = SecurityContextHolder.createEmptyContext();
fresh.setAuthentication(result);
SecurityContextHolder.setContext(fresh);

// Với login session thủ công, dùng repository đã cấu hình:
securityContextRepository.saveContext(fresh, request, response);
~~~

Trong snippet trên, `username` và `rawPassword` là dữ liệu đầu vào đăng nhập cần được kiểm tra, không được dùng để tự tạo authenticated token. Các biến `authenticationManager`, `securityContextRepository`, `request` và `response` cần có trong lớp Servlet tích hợp. Đây **không phải ví dụ endpoint độc lập**, và không bao quát đầy đủ CSRF, session fixation, error handling, rate limit hoặc remember-me. Hệ thống production nên dùng các filter và flow login chuẩn trừ khi có yêu cầu tích hợp thật sự đặc thù.

**Phân biệt hai trường hợp quan trọng:**

1. **Chỉ muốn quan sát current user:** đọc `Authentication` từ controller/service hoặc method argument phù hợp. Không cần tạo context mới.
2. **Muốn thay đổi current Authentication:** dùng kết quả từ nguồn tin cậy, **tạo context mới**, đặt vào holder rồi lưu đúng chính sách nếu muốn tồn tại qua request.

Đừng thay authentication trên context cũ chỉ để “đổi vai” trong một request. Nếu nghiệp vụ hỗ trợ impersonation/privilege elevation, cần thiết kế audit, scope, thời hạn, quyền khởi tạo và rollback riêng; context mới chỉ giải quyết một phần vấn đề chia sẻ đối tượng.

## 8. Async, thread pool và việc lan truyền context

`SecurityContextHolder` mặc định gắn context với thread. Khi bạn tạo một `Thread`, dùng `ExecutorService` hoặc `@Async`, code trên thread mới **không nhất thiết** thấy authentication của request gốc. Đồng thời, một thread pool có thể tái sử dụng worker thread cho nhiều tác vụ.

Các rủi ro đối lập:

- **Không truyền context:** tác vụ nền có thể mất danh tính, gây lỗi thiếu quyền hoặc chạy dưới anonymous.
- **Truyền trực tiếp cùng instance rồi sửa:** hai task có thể chia sẻ một `SecurityContext` mutable và gây race giống ví dụ ở phần 6.
- **Không clear context ở worker thread:** dữ liệu danh tính của tác vụ trước có thể còn hiện diện khi thread được tái sử dụng.

Spring Security cung cấp các wrapper như `DelegatingSecurityContextRunnable`, `DelegatingSecurityContextCallable` và `DelegatingSecurityContextExecutor` để thiết lập context khi thực thi và dọn sau đó. Tuy nhiên, khi dùng chúng vẫn phải hiểu **context nào được truyền**: wrapper không biến một đối tượng mutable được chia sẻ thành immutable. Tránh sửa cùng context được chuyển cho nhiều tác vụ, và cân nhắc snapshot/copy các thuộc tính cần thiết theo chính sách nghiệp vụ.

Không nên coi `MODE_INHERITABLETHREADLOCAL` là giải pháp mặc định cho thread pool. Kế thừa ThreadLocal gắn với thời điểm tạo thread, còn pool liên tục tái sử dụng thread; vì thế có thể tạo những kỳ vọng sai về danh tính và vòng đời. Chọn cơ chế propagation được Spring Security hỗ trợ, giới hạn scope và clear đúng cách.

Với request Servlet có async dispatch, error dispatch hoặc forward, security context repository và các filter có thể ảnh hưởng cách context được duy trì qua dispatch. Khi debug, quan sát **dispatcher type**, filter chain và cơ chế lưu context thực tế. Không mặc định mỗi dispatch là request mới hoặc mọi dispatch tự nhận cùng tham chiếu an toàn.

## 9. Context mới có giải quyết mọi vấn đề concurrency không?

**Không.** Nó giải quyết việc **không sửa trực tiếp một instance context đang có thể bị chia sẻ**. Những nguồn xung đột khác vẫn tồn tại:

- **Authentication object dùng chung:** dù tạo hai `SecurityContext` khác nhau, nếu cả hai giữ cùng một instance `Authentication` mutable (hoặc principal chứa mutable fields), sửa đối tượng bên trong vẫn có thể gây race. Ưu tiên immutable snapshot/dữ liệu principal được kiểm soát, không tự thay đổi authorities trong object dùng chung.
- **HttpSession dùng chung:** các attribute khác trong session vẫn có thể mutable và được truy cập đồng thời. Tạo mới security context không tự đồng bộ mọi dữ liệu trong session.
- **Hai request cùng đăng nhập lại hoặc logout:** có thể tranh chấp quyền ghi context vào session/repository; cần quyết định chính sách phiên, revoke và xử lý thứ tự cập nhật.
- **Đổi quyền ở database:** context có thể giữ authorities được cấp ở thời điểm authentication. Khi quyền thay đổi, ứng dụng có thể cần refresh/re-authenticate hoặc policy ở service, không chỉ tạo context mới tùy ý.
- **Cross-request caching:** không đặt `SecurityContext` hoặc `Authentication` hiện hành vào singleton field, static mutable field, shared cache theo biến toàn cục hoặc thread pool mà không có thiết kế scope.
- **Session fixation và CSRF:** ngữ cảnh mới không tự thay session ID, chống CSRF hoặc ràng buộc token với đúng người dùng.
- **Method security và quyền dữ liệu:** context có danh tính đúng không tự có nghĩa user được xem mọi đơn hàng/tenant. Cần authorization phù hợp ở HTTP và tầng nghiệp vụ.

Một nguyên tắc hữu ích: **lưu thông tin được phép dùng chung, bất biến khi có thể; nếu cần thay đổi Authentication, tạo SecurityContext mới thay vì sửa context cũ; nếu có shared state thực sự, thiết kế đồng bộ và vòng đời riêng cho shared state đó.**

## 10. Chẩn đoán và kiểm thử ứng dụng thực tế

### Dấu hiệu cần điều tra

- Cùng HTTP session phát hai request đồng thời, một request nhìn danh tính/authorities thay đổi bất thường.
- Endpoint login hoặc switch-user ghi `setAuthentication` vào context cũ; lỗi chỉ xuất hiện khi nhiều tab cùng hoạt động.
- Sau khi custom login thành công, request tiếp theo lại anonymous vì context chỉ được set trong holder nhưng không được lưu bằng repository phù hợp.
- Task `@Async` không thấy principal, hoặc thấy principal từ tác vụ trước do dùng thread pool mà không clear.
- Các endpoint trả 401/403 không nhất quán với trạng thái session; log cho thấy context repository hoặc filter sequence khác dự kiến.

### Quy trình kiểm tra

1. **Xác định code thay đổi authentication:** tìm `SecurityContextHolder.getContext().setAuthentication(...)`, `setContext(...)`, `saveContext(...)` và các custom authentication filters. Không cần thay đổi các đoạn chỉ đọc.
2. **Xác định repository/strategy thật:** kiểm tra `SecurityContextRepository`, session policy, filter chain và `SecurityContextHolderStrategy`. Tránh đoán từ mỗi dependency.
3. **Phân biệt object identity:** khi viết test, so sánh `contextA == contextB` và kiểm tra hậu quả khi một task thay đổi authentication; không chỉ so sánh `getName()` ở thời điểm đầu.
4. **Kiểm thử hai request đồng thời trong cùng session:** ràng buộc thời điểm bằng `CountDownLatch`/barrier để tái hiện xung đột, không viết test dựa vào `Thread.sleep(...)` ngẫu nhiên.
5. **Kiểm tra persistence:** sau custom login, gửi request mới dùng cùng session cookie và xác minh authentication còn tồn tại theo thiết kế; nếu stateless thì kiểm tra xác thực lại theo token.
6. **Kiểm tra cleanup và propagation:** khi request kết thúc hoặc task được trả về pool, context phải được dọn theo cơ chế phù hợp. Không để token/password trong log debug.
7. **Kiểm tra quyền nghiệp vụ:** hai principal khác nhau không được truy cập chéo tài nguyên chỉ vì một bản ghi ID có thể đoán được.

Trong phát triển có thể bật:

~~~properties
logging.level.org.springframework.security=DEBUG
~~~

Log giúp quan sát bước security filter, authentication, authorization và một số quyết định về context theo phiên bản. Khi cần chi tiết hơn mới dùng `TRACE` có kiểm soát; không bật trên production khi có nguy cơ lộ dữ liệu bí mật. Không in nguyên session ID, credential hoặc bearer token trong báo cáo debug.

### Bài kiểm tra tối thiểu để xác nhận đã xử lý đúng

| Tình huống | Kỳ vọng |
| --- | --- |
| Hai task giữ cùng instance context rồi một task sửa authentication | Test tái hiện được việc task kia quan sát thay đổi (mô phỏng lỗi) |
| Hai task tạo `createEmptyContext()` độc lập và gắn auth riêng | Không đọc nhầm danh tính |
| Custom login cần session nhưng chỉ `setContext`, không save | Không được kỳ vọng tự tồn tại qua request tiếp theo |
| Custom login tạo context mới và `saveContext` phù hợp | Request tiếp theo dùng cùng session nhận thông tin xác thực theo chính sách |
| Task nền hoàn thành | Holder được clear; lần tái sử dụng thread không mang context cũ |
| Cùng session thay đổi trạng thái đồng thời | Cần thêm policy xử lý xung đột lưu session, ngoài tách context object |

## 11. Những lỗi thường gặp

**Lỗi 1 — “ThreadLocal đảm bảo hoàn toàn không thể chia sẻ context.”** ThreadLocal tách **ô lưu tham chiếu**, không tách object mà hai ô cùng trỏ đến. Xác định object identity và repository.

**Lỗi 2 — “`getContext().setAuthentication(...)` lúc nào cũng sai.”** Nó là API hợp lệ, nhưng **nguy hiểm khi context có thể được chia sẻ**. Khi chủ động thay authentication, ưu tiên `createEmptyContext` rồi `setContext` để có instance riêng và tránh race.

**Lỗi 3 — “Chỉ `createEmptyContext()` đã đăng nhập được.”** Context mới ban đầu rỗng, chưa có `Authentication`. Phải sử dụng kết quả authentication từ provider/manager đáng tin, không tự phong role từ input.

**Lỗi 4 — “`setContext()` đồng nghĩa đã lưu session.”** Thay holder là thay cho luồng hiện tại. Với explicit-save flow, cần `SecurityContextRepository.saveContext(...)` nếu muốn persist login; session policy có thể khiến việc lưu không áp dụng.

**Lỗi 5 — “Có context mới là có session mới.”** Hai cơ chế độc lập; tạo mới Java object không tự đổi session ID hoặc bảo vệ session fixation.

**Lỗi 6 — “Context mới cũng clone sâu Authentication.”** `setAuthentication(authenticated)` chỉ lưu tham chiếu đến `Authentication` được đưa vào. Đừng dùng chung/đột biến authentication hoặc principal mutable mà không có chính sách.

**Lỗi 7 — “Request chính đã có context nên mọi `@Async` task tự thấy context.”** Thread mới/pool không tự nhận đúng context theo mặc định. Dùng propagation có kiểm soát và cleanup.

**Lỗi 8 — “Dùng InheritableThreadLocal cho pool là xong.”** Worker thread tái sử dụng có thể gây dữ liệu stale. Cơ chế propagation có scope và `finally` cleanup phù hợp hơn.

**Lỗi 9 — “Spring Security luôn chia sẻ cùng một context cho mọi request.”** Không đúng; nguồn lưu trữ và cấu hình quyết định tham chiếu nào được cấp. Dù vậy, tránh sửa context cũ vẫn là lựa chọn phòng lỗi tốt khi tự thay authentication.

**Lỗi 10 — “Mỗi context riêng thì business authorization khỏi cần.”** Context trả lời danh tính và quyền được biểu diễn; vẫn phải kiểm tra ai được truy cập tài nguyên/tenant cụ thể.

## 12. Tự kiểm tra hiểu biết

**Câu 1:** Vì sao hai thread dùng `ThreadLocal` riêng vẫn có thể cùng thấy principal bị đổi?

**Đáp:** Hai ThreadLocal có thể chứa cùng tham chiếu tới một `SecurityContext` mutable, ví dụ do shared session/repository hoặc ứng dụng tự truyền đối tượng đó.

**Câu 2:** Khi custom authentication thành công, thứ tự ba lệnh cốt lõi để không sửa context cũ là gì?

**Đáp:** `SecurityContextHolder.createEmptyContext()` → `newContext.setAuthentication(authenticated)` → `SecurityContextHolder.setContext(newContext)`.

**Câu 3:** Vì sao `SecurityContextHolder.setContext(newContext)` chưa đủ cho login dựa trên session?

**Đáp:** Nó chỉ đặt context cho luồng xử lý hiện hành. Nếu cấu hình yêu cầu explicit save, phải gọi `SecurityContextRepository.saveContext(newContext, request, response)` và thực hiện đầy đủ quy trình login an toàn.

**Câu 4:** Tạo SecurityContext mới có tự sao chép/đóng băng Authentication được gắn vào không?

**Đáp:** Không. `setAuthentication` lưu tham chiếu. Nếu cùng một object mutable được gắn vào nhiều context, race vẫn có thể xuất hiện ở object con.

**Câu 5:** Có nên gọi `clearContext()` ở mọi controller sau khi đọc thông tin user không?

**Đáp:** Không. Security filter chain chuẩn quản lý vòng đời request. `clearContext()` là việc cần thiết khi code tự quản lý thread/tác vụ ngoài vòng đời filter, thường trong `finally`.

**Câu 6:** Nếu hai request đồng thời lưu hai context mới khác nhau vào cùng HttpSession thì đã hết mọi tranh chấp chưa?

**Đáp:** Chưa. Hai object riêng tránh sửa chung cùng instance, nhưng vẫn có thể có xung đột logic về trạng thái phiên và thứ tự ghi. Cần thêm chính sách session phù hợp.

**Ghi nhớ:** **`SecurityContextHolder` quản lý nơi tham chiếu context được gắn; `SecurityContext` là đối tượng có thể mutable. Khi thay `Authentication`, tạo một `SecurityContext` mới, đặt vào holder và lưu qua repository khi cần. Đừng nhầm ThreadLocal với bảo đảm không có object dùng chung hoặc nhầm context mới với session mới.**