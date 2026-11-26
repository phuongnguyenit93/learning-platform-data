# Dọn ngữ cảnh sau test để tránh rò rỉ danh tính

Một bài test chạy với người dùng `lan` và kết thúc thành công. Nhưng bài test kế tiếp, vốn định kiểm tra request vô danh, lại nhìn thấy `lan` trong `SecurityContextHolder`. Đây là dấu hiệu trạng thái bảo mật đã vượt ra ngoài phạm vi mà bài test sở hữu.

Spring Security dùng context để gắn `Authentication` với luồng xử lý hiện tại. Trên Servlet, chiến lược mặc định thường lưu context bằng `ThreadLocal`; JUnit và các executor có thể tái sử dụng cùng một thread cho nhiều công việc. Nếu test tự đặt context mà không dọn, danh tính cũ có thể ảnh hưởng đến assertion, dịch vụ hoặc request tiếp theo. Vì vậy, **dọn context là một phần của tính cô lập giữa các bài kiểm thử**.

Bài học thuộc chương **Ngữ cảnh và vòng đời** của module **SPRING_SECURITY_TESTING**, tập trung vào cơ chế dọn tự động của `WithSecurityContextTestExecutionListener`, cách sử dụng `TestSecurityContextHolder.clearContext()` và `SecurityContextHolder.clearContext()`, quy tắc `@AfterEach`/`try-finally`, cũng như ranh giới của request Servlet, thread pool và Reactive. Mục tiêu là kiểm chứng xác thực, phân quyền và bảo vệ HTTP bằng `spring-security-test` mà không để danh tính của test này tác động tới test khác.

## 1. Rò rỉ danh tính là gì?

Rò rỉ danh tính xảy ra khi một test hoặc một tác vụ đặt `Authentication` vào context nhưng không dọn hoặc khôi phục trạng thái đúng lúc. Một test sau đó vô tình đọc lại context cũ và chạy với người dùng, role hoặc authority không thuộc về nó.

Ví dụ sai:

~~~java
@Test
void testAsLan() {
    Authentication authentication =
            new UsernamePasswordAuthenticationToken(
                    "lan",
                    "N/A",
                    AuthorityUtils.createAuthorityList("ROLE_READER"));

    SecurityContextHolder.getContext().setAuthentication(authentication);

    // Assertions cho người dùng lan.
    // Không có bước cleanup.
}
~~~

Nếu thread chạy test được tái sử dụng, `SecurityContextHolder` vẫn có thể giữ context đã đặt. Test tiếp theo có thể không còn bắt đầu từ trạng thái mong muốn.

Một tình huống khác là dùng test holder:

~~~java
TestSecurityContextHolder.setAuthentication(authentication);
~~~

Lệnh này đặt authentication vào cả `TestSecurityContextHolder` và `SecurityContextHolder`. Nếu chỉ dọn một holder, trạng thái test có thể vẫn còn trong holder kia.

Rò rỉ có thể gây ra các triệu chứng:

- Test vô danh bất ngờ đọc được tên người dùng của test trước.
- Ca kiểm thử thiếu quyền lại được phép vì role cũ còn tồn tại.
- Assertion về `Authentication` phụ thuộc thứ tự chạy test.
- Test chạy riêng thì PASS nhưng chạy cả suite lại FAIL.
- Một tác vụ chạy trong thread pool nhận context không thuộc request/tác vụ hiện tại.

## 2. Ai dọn context trong vòng đời test?

Khi Spring TestContext được sử dụng cùng `spring-security-test` và listener bảo mật mặc định được đăng ký, `WithSecurityContextTestExecutionListener` chịu trách nhiệm dọn context sau mỗi phương thức test. Listener này xử lý các annotation như `@WithMockUser`, `@WithAnonymousUser`, `@WithUserDetails` và annotation tùy biến dựa trên `@WithSecurityContext`.

Trình tự điển hình với JUnit Jupiter:

~~~text
Spring TestContext: beforeTestMethod
  └─ WithSecurityContextTestExecutionListener
       └─ thiết lập context nếu test có annotation bảo mật
JUnit Jupiter: @BeforeEach
JUnit Jupiter: @Test
JUnit Jupiter: @AfterEach
Spring TestContext: afterTestMethod
  └─ WithSecurityContextTestExecutionListener
       └─ TestSecurityContextHolder.clearContext()
            ├─ dọn TestSecurityContextHolder
            └─ dọn SecurityContextHolder
~~~

Điều quan trọng: `@AfterEach` chạy trước callback `afterTestMethod` của Spring TestContext. Do đó, khi dùng `@WithMockUser` theo cơ chế listener mặc định, authentication do annotation tạo thường vẫn có thể đọc được trong `@AfterEach` (trừ khi code test đã thay đổi hoặc xóa nó). Listener dọn sau đó.

Với test dùng annotation, bạn thường **không cần tự dọn lại context** chỉ vì đã dùng `@WithMockUser`. Hãy để listener quản lý vòng đời. Tuy nhiên, nếu test tự thay đổi holder, tự đặt context ngoài cơ chế annotation hoặc không chạy listener mặc định, cần chủ động quản lý cleanup.

Listener chỉ dọn trạng thái bảo mật. Nó không xóa dữ liệu fixture, không rollback transaction ngoài cơ chế transaction test, không đóng executor do test tạo và không hoàn nguyên biến static của ứng dụng.

## 3. Phân biệt hai phương thức clearContext()

Spring Security có hai API thường được dùng khi cleanup. Tên gần giống nhau nhưng phạm vi khác nhau:

| API | Phạm vi dọn | Khi nào dùng |
| --- | --- | --- |
| `SecurityContextHolder.clearContext()` | Dọn context của `SecurityContextHolder` trên chiến lược/luồng hiện tại | Test hoặc mã ứng dụng tự đặt trực tiếp vào security holder |
| `TestSecurityContextHolder.clearContext()` | Dọn context trong `TestSecurityContextHolder` **và** `SecurityContextHolder` | Test đã dùng test holder hoặc cần xóa toàn bộ trạng thái test security |

Ví dụ:

~~~java
// Khi chỉ đặt trực tiếp vào SecurityContextHolder:
SecurityContextHolder.setContext(context);
try {
    // Thực hiện phần kiểm thử cần context.
} finally {
    SecurityContextHolder.clearContext();
}

// Khi đặt qua TestSecurityContextHolder:
TestSecurityContextHolder.setContext(context);
try {
    // Thực hiện phần kiểm thử cần context.
} finally {
    TestSecurityContextHolder.clearContext();
}
~~~

Nếu gọi `SecurityContextHolder.clearContext()` sau khi đã dùng `TestSecurityContextHolder.setContext(...)`, test holder có thể vẫn giữ context. Một request tiếp theo được cấp lại context từ test holder có thể khôi phục danh tính cũ. Vì vậy, hãy chọn API dọn tương ứng với API thiết lập.

Không nên assert rằng `SecurityContextHolder.getContext()` trả về `null` sau khi gọi `clearContext()`. Với chiến lược mặc định, lần gọi `getContext()` tiếp theo có thể tạo một context trống mới. Nếu muốn kiểm tra trạng thái, hãy đọc `getAuthentication()` và xác minh nó chưa có giá trị.

## 4. Dùng @AfterEach cho context tự thiết lập

Nếu test tự tạo context trong `@BeforeEach` hoặc trong thân test, có thể dùng `@AfterEach` để dọn:

~~~java
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.AuthorityUtils;
import org.springframework.security.core.context.SecurityContextHolder;

import static org.assertj.core.api.Assertions.assertThat;

class ManualContextCleanupTest {

    @BeforeEach
    void setUpUser() {
        var authentication =
                new UsernamePasswordAuthenticationToken(
                        "lan",
                        "N/A",
                        AuthorityUtils.createAuthorityList("ROLE_READER"));

        var context = SecurityContextHolder.createEmptyContext();
        context.setAuthentication(authentication);
        SecurityContextHolder.setContext(context);
    }

    @Test
    void currentUserIsLan() {
        assertThat(SecurityContextHolder.getContext()
                .getAuthentication().getName()).isEqualTo("lan");
    }

    @AfterEach
    void clearContext() {
        SecurityContextHolder.clearContext();
    }
}
~~~

Trong ví dụ này, test tự quản lý `SecurityContextHolder` và dọn đúng holder ở `@AfterEach`. Nếu đổi sang `TestSecurityContextHolder.setAuthentication(...)` hoặc `setContext(...)`, hãy đổi cleanup thành `TestSecurityContextHolder.clearContext()`.

Một mẫu khác là đặt context ngay trong test rồi dùng `try/finally`:

~~~java
@Test
void cleanupRunsEvenWhenAssertionFails() {
    Authentication authentication =
            new UsernamePasswordAuthenticationToken(
                    "lan", "N/A",
                    AuthorityUtils.createAuthorityList("ROLE_READER"));

    SecurityContext context = SecurityContextHolder.createEmptyContext();
    context.setAuthentication(authentication);

    try {
        SecurityContextHolder.setContext(context);

        assertThat(SecurityContextHolder.getContext()
                .getAuthentication().getName()).isEqualTo("lan");

        // Những assertion khác có thể ném lỗi.
    } finally {
        SecurityContextHolder.clearContext();
    }
}
~~~

`finally` bảo đảm cleanup được thực hiện ngay cả khi assertion hoặc lời gọi nghiệp vụ ném exception. Đây là cách tốt khi context chỉ cần tồn tại trong một đoạn code nhỏ và bạn muốn giới hạn chính xác phạm vi của nó.

## 5. Dùng TestSecurityContextHolder đúng cách

`TestSecurityContextHolder` được thiết kế để hỗ trợ kiểm thử Spring Security, nhất là khi kết hợp với MockMvc. Nó lưu context dự kiến của test, đồng thời cập nhật `SecurityContextHolder` trên thread hiện tại. Request postprocessor `testSecurityContext()` có thể sử dụng context đó để cấp cho một request MockMvc.

Ví dụ:

~~~java
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.AuthorityUtils;
import org.springframework.security.test.context.TestSecurityContextHolder;

import static org.assertj.core.api.Assertions.assertThat;

class TestHolderCleanupTest {

    @Test
    void usesTestHolderAndClearsBothHolders() {
        var authentication =
                new UsernamePasswordAuthenticationToken(
                        "lan",
                        "N/A",
                        AuthorityUtils.createAuthorityList("ROLE_READER"));

        try {
            TestSecurityContextHolder.setAuthentication(authentication);

            assertThat(TestSecurityContextHolder.getContext()
                    .getAuthentication().getName()).isEqualTo("lan");
        } finally {
            TestSecurityContextHolder.clearContext();
        }
    }
}
~~~

Trong ví dụ đơn giản này, `finally` làm cho phạm vi của context rất rõ. Có thể đặt cleanup trong `@AfterEach` nếu cả lớp thống nhất cách thiết lập context và mọi test đều đi qua JUnit lifecycle.

Nếu dùng `@WithMockUser`, listener bảo mật sẽ tự tạo và dọn context. Nếu test chủ động gọi `TestSecurityContextHolder.setAuthentication(...)` để ghi đè người dùng do annotation tạo, hãy xác định ai là chủ sở hữu cuối cùng của context và dọn đúng nơi. Tránh vừa để listener quản lý, vừa tự dọn ở nhiều callback không cần thiết khiến thứ tự khó hiểu.

## 6. Khi test có @WithMockUser, không cần cleanup thủ công thông thường

Ví dụ:

~~~java
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.context.junit.jupiter.SpringExtension;

import static org.assertj.core.api.Assertions.assertThat;

@ExtendWith(SpringExtension.class)
class ListenerManagedCleanupTest {

    @Test
    @WithMockUser(username = "lan", roles = "READER")
    void runsWithLan() {
        assertThat(SecurityContextHolder.getContext()
                .getAuthentication().getName()).isEqualTo("lan");
    }

    @Test
    @WithMockUser(username = "mai", roles = "ADMIN")
    void nextTestHasItsOwnIdentity() {
        assertThat(SecurityContextHolder.getContext()
                .getAuthentication().getName()).isEqualTo("mai");
    }

    @AfterEach
    void observeBeforeListenerCleanup() {
        // Callback này chạy trước afterTestMethod.
        // Nếu test dùng @WithMockUser và không tự clear,
        // authentication của test hiện tại vẫn thường còn ở đây.
    }
}
~~~

Mỗi test được listener chuẩn bị context theo annotation của chính nó, và listener dọn sau phương thức. Không nên thêm một `@AfterEach` chỉ để gọi `SecurityContextHolder.clearContext()` trong mọi test dùng annotation, trừ khi test có lý do tự quản lý/ghi đè trạng thái.

Cần giữ hạ tầng Spring TestContext mặc định. Nếu `@TestExecutionListeners` tùy chỉnh thay thế danh sách listener mặc định, `WithSecurityContextTestExecutionListener` có thể không còn được gọi. Khi đó, đừng giả định `@WithMockUser` tự dọn; hãy khôi phục listener mặc định bằng merge mode thích hợp hoặc cấu hình đầy đủ các listener cần thiết.

## 7. Dọn context của HTTP request Servlet

Trong ứng dụng Servlet, Spring Security quản lý context theo vòng đời request. Filter chain tải context cho request, cho phép các authentication/authorization filter sử dụng nó, rồi dọn context khỏi holder khi quá trình xử lý kết thúc.

Có thể mô tả khái quát:

~~~text
HTTP request bắt đầu
    │
    ▼
SecurityContextHolderFilter
    └─ nạp SecurityContext cho request
    │
Authentication / Authorization filters
    └─ sử dụng hoặc thay đổi context
    │
Controller / handler
    └─ xử lý request
    │
Kết thúc filter chain (kể cả khi có exception)
    └─ SecurityContextHolder được clear trong finally
    │
HTTP response
~~~

Đây là cơ chế khác với cleanup của test listener. Listener dọn context của **phương thức test**; security filter chain dọn context của **HTTP request**. Không nên trông chờ request filter dọn trạng thái mà test đã đặt trực tiếp trên thread JUnit trước khi gọi request, nhất là khi test holder có thể còn giữ context để cấp lại cho request kế tiếp.

Khi dùng `MockMvc`, hãy tích hợp Spring Security đúng cách:

~~~java
mockMvc = MockMvcBuilders.webAppContextSetup(webApplicationContext)
        .apply(springSecurity())
        .build();
~~~

Hoặc dùng Spring Boot `@AutoConfigureMockMvc` với security filter được bật. Khi đó, mỗi request đi qua filter chain và context của request được quản lý theo vòng đời filter. Nếu tự dựng `standaloneSetup` thiếu filter, test có thể không kiểm tra cleanup hoặc authorization ở HTTP layer.

Ví dụ kiểm tra người dùng riêng cho từng request:

~~~java
mockMvc.perform(get("/api/reports")
        .with(user("lan").roles("READER")))
        .andExpect(status().isOk());

mockMvc.perform(get("/api/reports")
        .with(anonymous()))
        .andExpect(status().isUnauthorized());
~~~

Đoạn trên giả định endpoint yêu cầu xác thực, HTTP Basic entry point trả `401` cho anonymous và MockMvc đã tích hợp filter. Request thứ hai được cấp danh tính anonymous tường minh, không nên phụ thuộc vào trạng thái còn sót lại từ request thứ nhất.

## 8. Ranh giới thread pool và tác vụ bất đồng bộ

`SecurityContextHolder` mặc định dùng `MODE_THREADLOCAL` trên Servlet. Mỗi thread có context riêng, nhưng thread pool tái sử dụng worker thread cho nhiều tác vụ. Nếu tác vụ tự đặt context rồi không dọn, tác vụ chạy sau trên cùng worker có thể đọc nhầm danh tính.

Một tác vụ không được bọc có thể có dạng:

~~~java
executor.submit(() -> {
    SecurityContextHolder.setContext(context);
    return service.readReport();
    // Nếu không clear trong finally, worker có thể giữ context.
});
~~~

Nếu tự quản lý context trong worker, cần cleanup ngay trong chính tác vụ:

~~~java
executor.submit(() -> {
    try {
        SecurityContextHolder.setContext(context);
        return service.readReport();
    } finally {
        SecurityContextHolder.clearContext();
    }
});
~~~

Spring Security cung cấp các wrapper như `DelegatingSecurityContextRunnable`, `DelegatingSecurityContextCallable`, `DelegatingSecurityContextExecutor` và `DelegatingSecurityContextExecutorService`. Các wrapper thiết lập context phù hợp trước khi chạy tác vụ và dọn context trong quá trình kết thúc tác vụ, giúp tránh rò rỉ trên thread pool.

Ví dụ dùng executor service trong một bài test có `@WithMockUser`:

~~~java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.concurrent.DelegatingSecurityContextExecutorService;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.assertj.core.api.Assertions.assertThat;

@SpringJUnitConfig(AsyncSecurityContextTest.Config.class)
class AsyncSecurityContextTest {

    @Test
    @WithMockUser(username = "lan", roles = "READER")
    void taskReceivesTheSubmittingUsersContext() throws Exception {
        ExecutorService delegate = Executors.newFixedThreadPool(2);
        ExecutorService secured =
                new DelegatingSecurityContextExecutorService(delegate);

        try {
            Future<String> result = secured.submit(() ->
                    SecurityContextHolder.getContext()
                            .getAuthentication().getName());

            assertThat(result.get(3, TimeUnit.SECONDS)).isEqualTo("lan");
        } finally {
            delegate.shutdownNow();
        }
    }

    @Configuration
    static class Config {
    }
}
~~~

Ví dụ giả định luồng gửi tác vụ hiện tại có authentication của `lan` khi `submit` được gọi; wrapper chụp context theo cơ chế của nó và đặt vào worker khi thực thi. Khi tác vụ hoàn tất, wrapper khôi phục/dọn trạng thái worker để không làm nhiễm tác vụ kế tiếp. Trong code ứng dụng, hãy cấu hình executor phù hợp với cách truyền context mong muốn thay vì tự sao chép ThreadLocal.

Không nên chuyển toàn JVM sang `MODE_GLOBAL` để tránh lỗi context; cũng không nên dựa vào `MODE_INHERITABLETHREADLOCAL` như giải pháp chung cho thread pool. Inheritable thread-local sao chép giá trị tại thời điểm tạo thread, không giải quyết đúng vòng đời của từng tác vụ được gửi vào worker tái sử dụng.

## 9. Cleanup trong Reactive khác với ThreadLocal

Trong WebFlux, Spring Security sử dụng Reactor Context để truyền security context theo subscriber/pipeline. Đây không phải một ThreadLocal gắn cố định với thread. Khi một subscription kết thúc, context gắn với subscription đó không tự trở thành context mặc định của một subscription mới.

Tuy nhiên, vẫn cần tránh:

- Lưu `Authentication` hoặc `SecurityContext` vào biến static/global.
- Tự tái sử dụng một Reactor Context chứa danh tính cũ cho request khác.
- Chia sẻ đối tượng context mutable giữa các pipeline độc lập.
- Giả định việc dọn `SecurityContextHolder` trên thread JUnit sẽ dọn Reactor Context của một pipeline.

Với reactive method security test, listener `ReactorContextTestExecutionListener` hỗ trợ cung cấp context test. Với HTTP Reactive, `WebTestClient` và các configurer Spring Security cung cấp danh tính ở phạm vi request. Hãy dùng đúng API theo mô hình Reactive thay vì áp dụng cleanup ThreadLocal một cách máy móc.

Ví dụ request WebTestClient cấp user cho riêng request:

~~~java
webTestClient.mutateWith(mockUser("lan").roles("READER"))
        .get().uri("/api/reports")
        .exchange()
        .expectStatus().isOk();
~~~

Khi request kết thúc, context thuộc pipeline/request được quản lý theo vòng đời Reactive. Nếu test tự tạo context hoặc giữ tham chiếu để dùng lại, phải bảo đảm không chia sẻ danh tính đó sang test khác.

## 10. Test song song và chiến lược SecurityContextHolder

JUnit hoặc build tool có thể chạy test song song. Mặc định `MODE_THREADLOCAL` giúp các thread độc lập có context riêng, nhưng không bảo vệ khỏi việc một test để lại context trên thread sẽ được tái sử dụng. Các vấn đề thường đến từ:

- Test dùng biến static lưu `Authentication` hoặc `SecurityContext`.
- Test đổi chiến lược `SecurityContextHolder` trong lúc các test khác đang chạy.
- Tác vụ async không dọn context trên worker thread.
- Một test thủ công dùng `setContext` nhưng thiếu cleanup.
- Test dùng chung một context mutable giữa nhiều luồng.

Không thay đổi `SecurityContextHolder.setStrategyName(...)` trong từng phương thức test. Đây là cấu hình chiến lược tĩnh ở phạm vi JVM, có thể ảnh hưởng đến các test chạy song song và những thành phần đã giữ strategy trước đó. Nếu ứng dụng cần chiến lược khác, hãy cấu hình ở mức ứng dụng và kiểm thử riêng, không bật/tắt liên tục theo từng test.

Nếu một test cần tạm thay context rồi khôi phục trạng thái trước đó, hãy lưu context hiện hành trước khi thay và phục hồi trong `finally`. Tuy nhiên, với test độc lập, cách đơn giản và an toàn hơn thường là tạo context mới, sử dụng trong phạm vi test rồi `clearContext()`. Đừng chia sẻ cùng một `SecurityContext` mutable giữa các test chỉ để tiết kiệm vài dòng setup.

## 11. Những lỗi cleanup thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Test anonymous đọc được user của test trước | Test trước tự đặt context nhưng không clear | Dùng `@AfterEach` hoặc `try/finally` |
| Đã gọi `SecurityContextHolder.clearContext()` nhưng request sau vẫn có user cũ | `TestSecurityContextHolder` vẫn giữ context | Dùng `TestSecurityContextHolder.clearContext()` |
| Test có `@WithMockUser` bị rò rỉ khi chạy cả suite | Listener mặc định bị thay thế hoặc test tự ghi đè context | Kiểm tra `WithSecurityContextTestExecutionListener` và cleanup của phần code thủ công |
| `@AfterEach` vẫn thấy Authentication | Listener dọn ở `afterTestMethod` sau `@AfterEach` | Đây là thứ tự thông thường; kiểm tra ở callback/test phù hợp |
| Test chạy riêng PASS nhưng suite FAIL | Thread hoặc executor được tái sử dụng, trạng thái cũ tồn tại | Dọn holder và worker task, bỏ biến static |
| Request đầu dùng đúng user, request sau dùng nhầm user | Test holder hoặc request postprocessor giữ context ngoài ý muốn | Cấp danh tính rõ cho từng request và dọn test holder |
| Worker thread đọc user của tác vụ trước | Tác vụ tự set context mà không clear | Dùng DelegatingSecurityContext wrapper hoặc finally |
| Test Reactive thấy context cũ | Chia sẻ context/Authentication qua biến toàn cục hoặc tái dùng pipeline sai cách | Giữ context theo subscription/request và tránh mutable global state |
| Dùng `@DirtiesContext` nhưng lỗi vẫn còn | Context bảo mật nằm ở holder/thread hoặc worker, không chỉ ở ApplicationContext | Dọn đúng holder và executor |

## 12. Quy trình kiểm tra tính cô lập

Khi nghi ngờ rò rỉ danh tính, thực hiện lần lượt:

1. Tìm mọi nơi gọi `SecurityContextHolder.setContext(...)`, `setAuthentication(...)` hoặc `TestSecurityContextHolder.setContext(...)`.
2. Với mỗi điểm thiết lập thủ công, xác định API cleanup tương ứng.
3. Kiểm tra cleanup có chạy khi assertion thất bại hay exception xảy ra; ưu tiên `try/finally` hoặc callback cleanup phù hợp.
4. Kiểm tra `@WithMockUser` và listener mặc định có còn hoạt động trong Spring TestContext hay không.
5. Kiểm tra executor/task wrapper và bảo đảm worker thread được dọn sau tác vụ.
6. Kiểm tra các biến static, singleton mutable và việc thay đổi chiến lược holder toàn cục.
7. Chạy riêng test và chạy lại cả lớp/suite; thay đổi thứ tự test để tìm phụ thuộc ngầm.
8. Với MockMvc, xác minh filter chain đã được tích hợp; với WebTestClient, kiểm tra context theo Reactor pipeline.

Có thể viết một test kiểm tra trạng thái ban đầu bằng cách assert `SecurityContextHolder.getContext().getAuthentication()` là `null` trước khi thiết lập context, nhưng assertion đó chỉ hợp lệ nếu không có listener/extension khác đã đặt danh tính. Không dùng thứ tự chạy test để tạo điều kiện cho test khác; mỗi bài phải tự thiết lập và dọn trạng thái mà nó sở hữu.

## 13. Bài thực hành

Tạo hai bài test độc lập:

- Bài thứ nhất đặt `Authentication` của `lan` trực tiếp vào `SecurityContextHolder` và kiểm tra dịch vụ đọc được tên người dùng.
- Bài thứ hai giả lập người dùng anonymous và xác minh một hành động yêu cầu `ROLE_READER` bị từ chối.

Thực hiện các biến thể:

1. Bỏ cleanup ở bài thứ nhất, chạy cả hai bài và quan sát nguy cơ phụ thuộc thread/test order.
2. Thêm `@AfterEach` gọi `SecurityContextHolder.clearContext()`; chạy lại suite.
3. Đổi bài thứ nhất sang `TestSecurityContextHolder.setAuthentication(...)`, nhưng tạm chỉ gọi `SecurityContextHolder.clearContext()`. Giải thích vì sao test holder vẫn có thể giữ danh tính.
4. Đổi cleanup thành `TestSecurityContextHolder.clearContext()` và xác minh cả hai holder được dọn.
5. Chuyển phần thiết lập vào một helper dùng `try/finally`, cố tình làm assertion thất bại và quan sát cleanup vẫn chạy.
6. Gửi một tác vụ qua `DelegatingSecurityContextExecutorService`; xác minh worker thấy user mong đợi và không giữ context sau khi tác vụ kết thúc.
7. Dùng `MockMvc` và `WebTestClient` để xác minh mỗi request có danh tính được cấp riêng, không phụ thuộc request trước.

Kết quả cần đạt: mỗi test bắt đầu với trạng thái đã biết, chỉ dùng danh tính mà test đó yêu cầu, và kết thúc mà không để lại context ngoài phạm vi sở hữu. Đó là điều kiện quan trọng để bộ kiểm thử xác thực, phân quyền và bảo vệ HTTP có thể chạy ổn định theo từng test, từng lớp và toàn bộ suite.

## Tài liệu tham khảo

- [Spring Security — Testing Method Security](https://docs.spring.io/spring-security/reference/servlet/test/method.html)
- [Spring Security API — TestSecurityContextHolder](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/test/context/TestSecurityContextHolder.html)
- [Spring Security API — WithSecurityContextTestExecutionListener](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/test/context/support/WithSecurityContextTestExecutionListener.html)
- [Spring Security — Concurrency Support](https://docs.spring.io/spring-security/reference/features/integrations/concurrency.html)
- [Spring Security — Persisting Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/persistence.html)
- [Spring Security — MockMvc Authentication](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/authentication.html)
- [Spring Security — Reactive Testing](https://docs.spring.io/spring-security/reference/reactive/test/index.html)
