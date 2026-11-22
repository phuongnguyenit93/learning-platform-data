# @TestExecutionListeners và quy tắc merge với listener mặc định

## 1. Vai trò của TestExecutionListener

Spring TestContext Framework cung cấp `TestExecutionListener` để mở rộng vòng đời kiểm thử của Spring. Listener nhận một `TestContext` và được gọi tại các thời điểm như trước/sau test class, khi chuẩn bị test instance, trước/sau test method hoặc ngay trước/sau phần thân test method.

Listener có thể dùng để thực hiện những công việc chung cho nhiều test, ví dụ:

- Chuẩn bị dữ liệu hoặc trạng thái trước khi test method chạy.
- Ghi nhận thời gian thực thi, thông tin test class và test method.
- Lưu hoặc đọc metadata trong `TestContext`.
- Tích hợp tài nguyên kiểm thử với Spring application context.
- Dọn dẹp tài nguyên sau test hoặc sau test class.

`@TestExecutionListeners` là annotation để đăng ký các implementation của `TestExecutionListener` với `TestContextManager`. Annotation này thường được dùng cùng `@ContextConfiguration`, `@SpringJUnitConfig` hoặc các annotation kiểm thử Spring khác.

Điểm quan trọng khi thêm listener là phải hiểu cách annotation tương tác với các listener mặc định của Spring. Nếu cấu hình không đúng, test có thể mất các chức năng vốn được Spring tự động cung cấp như dependency injection, quản lý transaction hoặc xử lý `@DirtiesContext`.

## 2. Listener mặc định của Spring TestContext Framework

Khi test dùng Spring TestContext Framework mà không tự khai báo `@TestExecutionListeners`, Spring tự đăng ký danh sách listener mặc định được phát hiện qua cơ chế `SpringFactoriesLoader`.

Các listener mặc định đảm nhiệm những chức năng phổ biến, chẳng hạn:

| Listener | Vai trò chính |
|---|---|
| `ServletTestExecutionListener` | Chuẩn bị web request context cho kiểm thử Servlet khi cấu hình web phù hợp. |
| `DirtiesContextBeforeModesTestExecutionListener` | Xử lý các chế độ `@DirtiesContext` yêu cầu đánh dấu context trước test method hoặc class. |
| `ApplicationEventsTestExecutionListener` | Ghi nhận application event trong phạm vi test khi tính năng application events được sử dụng. |
| `DependencyInjectionTestExecutionListener` | Thực hiện dependency injection vào test instance, ví dụ các field có `@Autowired`. |
| `DirtiesContextTestExecutionListener` | Đánh dấu application context bị dirty theo cấu hình `@DirtiesContext`. |
| `TransactionalTestExecutionListener` | Quản lý test-managed transaction cho các test được đánh dấu `@Transactional`. |
| `SqlScriptsTestExecutionListener` | Thực thi script SQL được khai báo bằng `@Sql`. |
| `EventPublishingTestExecutionListener` | Phát các event của vòng đời test để thành phần khác có thể lắng nghe. |
| `MockitoResetTestExecutionListener` | Reset mock được Spring quản lý theo cấu hình reset tương ứng. |

Danh sách cụ thể phụ thuộc phiên bản Spring Framework và các thư viện có trên test classpath. Một số listener chỉ hoạt động khi loại application context hoặc tính năng tương ứng có mặt. Vì vậy, bảng trên mô tả các listener tiêu biểu trong các phiên bản Spring hiện đại, không phải danh sách bất biến cho mọi phiên bản.

Khi sử dụng `@SpringBootTest`, `@WebMvcTest` hoặc các annotation test slice, Spring vẫn dựa trên TestContext Framework. Những listener mặc định cần thiết cho Spring Test vẫn là một phần của cơ chế chuẩn bị và thực thi test.

## 3. Đăng ký listener tùy chỉnh bằng @TestExecutionListeners

Ví dụ, một test cần listener ghi nhận thời gian chạy của phần thân test method. Có thể tạo listener bằng cách kế thừa `AbstractTestExecutionListener` để chỉ override các callback cần thiết:

```java
import org.springframework.test.context.TestContext;
import org.springframework.test.context.support.AbstractTestExecutionListener;

public class TestTimingListener extends AbstractTestExecutionListener {

    private static final String START_TIME =
            TestTimingListener.class.getName() + ".startTime";

    @Override
    public void beforeTestExecution(TestContext testContext) {
        testContext.setAttribute(START_TIME, System.nanoTime());
    }

    @Override
    public void afterTestExecution(TestContext testContext) {
        Object value = testContext.removeAttribute(START_TIME);
        if (value instanceof Long startTime) {
            long elapsedNanos = System.nanoTime() - startTime;
            System.getLogger(getClass().getName()).log(
                    System.Logger.Level.INFO,
                    "Test {0} took {1} ms",
                    testContext.getTestMethod().getName(),
                    elapsedNanos / 1_000_000);
        }
    }
}
```

`AbstractTestExecutionListener` cung cấp các implementation rỗng cho callback, nên listener không phải override tất cả phương thức. Ví dụ lưu thời điểm bắt đầu bằng `TestContext.setAttribute(...)`, sau đó lấy và xóa giá trị bằng `removeAttribute(...)`. Cách này tránh dùng biến toàn cục để giữ trạng thái giữa các test method.

Đăng ký listener cho một test class:

```java
import org.springframework.test.context.TestExecutionListeners;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(TestConfiguration.class)
@TestExecutionListeners(
        listeners = TestTimingListener.class,
        mergeMode = TestExecutionListeners.MergeMode.MERGE_WITH_DEFAULTS
)
class OrderServiceTests {
    // Các test method của class.
}
```

Ví dụ dùng `MERGE_WITH_DEFAULTS` để listener tùy chỉnh được bổ sung cùng các listener mặc định. Đây là cách thường dùng khi chỉ muốn mở rộng vòng đời test mà vẫn cần các chức năng tiêu chuẩn của Spring.

## 4. Hai chế độ merge: REPLACE_DEFAULTS và MERGE_WITH_DEFAULTS

`TestExecutionListeners.MergeMode` có hai giá trị:

| Chế độ | Hành vi | Khi nên dùng |
|---|---|---|
| `REPLACE_DEFAULTS` | Thay danh sách listener mặc định bằng các listener được khai báo trong annotation (kết hợp quy tắc kế thừa nếu có). Đây là giá trị mặc định của `mergeMode`. | Chỉ khi chủ đích kiểm soát toàn bộ listener cần dùng và chấp nhận tự chịu trách nhiệm với các chức năng mặc định bị thay thế. |
| `MERGE_WITH_DEFAULTS` | Gộp listener được khai báo với danh sách listener mặc định do Spring phát hiện. | Khi muốn thêm listener tùy chỉnh nhưng vẫn giữ hành vi chuẩn của Spring Test. |

### REPLACE_DEFAULTS

Nếu viết:

```java
@TestExecutionListeners(
        listeners = TestTimingListener.class
)
class OrderServiceTests {
}
```

`mergeMode` không được chỉ định nên Spring dùng `REPLACE_DEFAULTS`. Danh sách mặc định không còn tự động được giữ lại chỉ vì test class có annotation này.

Hậu quả có thể là:

- Field `@Autowired` trong test instance không được inject nếu thiếu `DependencyInjectionTestExecutionListener`.
- Test-managed transaction không được bắt đầu/kết thúc như mong đợi nếu thiếu `TransactionalTestExecutionListener`.
- Các quy tắc làm mới context của `@DirtiesContext` không được áp dụng nếu thiếu listener tương ứng.
- Script `@Sql` có thể không được thực thi nếu thiếu `SqlScriptsTestExecutionListener`.

`REPLACE_DEFAULTS` không có nghĩa là Spring ngừng tạo application context hoặc bỏ qua toàn bộ Spring Test. Nó chỉ điều khiển danh sách `TestExecutionListener` được đăng ký. Tuy nhiên, việc bỏ listener có thể làm thay đổi đáng kể hành vi kiểm thử.

Nếu thực sự cần thay thế listener mặc định, hãy khai báo đầy đủ những listener mà test cần:

```java
@TestExecutionListeners(
        listeners = {
                DependencyInjectionTestExecutionListener.class,
                DirtiesContextTestExecutionListener.class,
                TransactionalTestExecutionListener.class,
                TestTimingListener.class
        },
        mergeMode = TestExecutionListeners.MergeMode.REPLACE_DEFAULTS
)
class SpecializedInfrastructureTests {
}
```

Danh sách trên chỉ là ví dụ rút gọn. Test có dùng `@Sql`, web context, application events, Mockito reset hoặc tính năng khác có thể cần thêm listener tương ứng. Khi thay toàn bộ defaults, phải căn cứ vào tính năng thực sự dùng và phiên bản Spring đang chạy.

### MERGE_WITH_DEFAULTS

Với:

```java
@TestExecutionListeners(
        listeners = TestTimingListener.class,
        mergeMode = TestExecutionListeners.MergeMode.MERGE_WITH_DEFAULTS
)
class OrderServiceTests {
}
```

Spring gộp `TestTimingListener` với các listener mặc định. Nhờ vậy, test vừa có thể ghi nhận thời gian, vừa tiếp tục sử dụng dependency injection, transaction test, `@Sql`, `@DirtiesContext` và các chức năng mặc định khác khi phù hợp.

Trong phần lớn trường hợp thêm một listener cho một test class, `MERGE_WITH_DEFAULTS` là lựa chọn phù hợp.

## 5. Phân biệt merge với kế thừa listener

`mergeMode` và `inheritListeners` điều khiển hai vấn đề khác nhau:

- `mergeMode` quyết định danh sách listener mặc định của Spring có được gộp với listener khai báo hay bị thay thế.
- `inheritListeners` quyết định listener khai báo trên lớp cha có được kế thừa xuống lớp con hay không.

`inheritListeners` mặc định là `true`. Khi test class kế thừa một base test class có `@TestExecutionListeners`, các listener từ lớp cha được kế thừa theo quy tắc của annotation. Có thể đặt `inheritListeners = false` để ngăn việc kế thừa listener từ lớp cha.

Ví dụ base class đăng ký listener dùng chung:

```java
@TestExecutionListeners(
        listeners = BaseAuditListener.class,
        mergeMode = TestExecutionListeners.MergeMode.MERGE_WITH_DEFAULTS
)
abstract class BaseIntegrationTests {
}
```

Lớp con có thể bổ sung listener riêng và vẫn giữ listener kế thừa:

```java
@TestExecutionListeners(
        listeners = TestTimingListener.class,
        inheritListeners = true,
        mergeMode = TestExecutionListeners.MergeMode.MERGE_WITH_DEFAULTS
)
class OrderIntegrationTests extends BaseIntegrationTests {
}
```

Trong ví dụ, lớp con kế thừa cấu hình listener từ base class, đồng thời khai báo listener đo thời gian. `MERGE_WITH_DEFAULTS` tiếp tục yêu cầu gộp với các listener mặc định của Spring.

Nếu một lớp con cần bộ listener riêng và không muốn nhận listener từ base class:

```java
@TestExecutionListeners(
        listeners = IsolatedTestListener.class,
        inheritListeners = false,
        mergeMode = TestExecutionListeners.MergeMode.MERGE_WITH_DEFAULTS
)
class IsolatedRepositoryTests extends BaseIntegrationTests {
}
```

Ở đây `inheritListeners = false` chỉ tắt việc kế thừa listener từ lớp cha. Vì `mergeMode` vẫn là `MERGE_WITH_DEFAULTS`, listener mặc định của Spring vẫn được gộp vào danh sách. Không nên nhầm hai thuộc tính này thành một lựa chọn duy nhất.

## 6. Thứ tự thực thi listener

Spring sắp xếp `TestExecutionListener` theo cơ chế ordering. Listener có thể triển khai `Ordered` hoặc dùng annotation `@Order` để xác định thứ tự. Các listener mặc định cũng có thứ tự được thiết kế để các bước như dependency injection và transaction management phối hợp đúng.

Ví dụ:

```java
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.test.context.support.AbstractTestExecutionListener;

@Order(Ordered.LOWEST_PRECEDENCE)
public class DiagnosticTestExecutionListener extends AbstractTestExecutionListener {
    // Chỉ ghi nhận thông tin chẩn đoán.
}
```

Hãy chọn thứ tự dựa trên phụ thuộc thực tế. Chẳng hạn, listener cần đọc bean đã được inject vào test instance không nên chạy trước listener chịu trách nhiệm dependency injection. Listener cần quan sát transaction test phải được đặt phù hợp với thời điểm transaction listener bắt đầu hoặc kết thúc transaction.

Các callback có ý nghĩa thời gian khác nhau:

| Callback | Thời điểm điển hình | Dùng cho |
|---|---|---|
| `beforeTestClass` | Trước khi chạy test methods của class | Chuẩn bị tài nguyên cấp class. |
| `prepareTestInstance` | Sau khi tạo test instance và trước khi test method chạy | Chuẩn bị hoặc bổ sung trạng thái cho test instance. |
| `beforeTestMethod` | Trước vòng đời thực thi từng test method | Chuẩn bị dữ liệu hoặc trạng thái cho một method. |
| `beforeTestExecution` | Ngay trước phần thân test method | Đo thời gian thực thi method hoặc bắt đầu tracing. |
| `afterTestExecution` | Ngay sau phần thân test method | Kết thúc tracing hoặc ghi nhận kết quả thực thi method. |
| `afterTestMethod` | Sau vòng đời test method | Dọn dẹp trạng thái sau method. |
| `afterTestClass` | Sau khi test methods của class hoàn tất | Giải phóng tài nguyên cấp class. |

`beforeTestExecution` và `afterTestExecution` hữu ích khi muốn đo riêng phần thân test method. Nếu cần đo cả fixture setup/teardown hoặc công việc của các callback khác, hãy chọn callback phù hợp với phạm vi thời gian cần ghi nhận.

## 7. Dùng TestContext để lưu trạng thái của listener

`TestContext` là đối tượng Spring truyền cho listener. Nó cung cấp thông tin về test class, test instance, test method, application context và một vùng attribute để listener lưu trạng thái theo ngữ cảnh test.

Một số thao tác thường dùng:

```java
testContext.getTestClass();
testContext.getTestInstance();
testContext.getTestMethod();
testContext.getApplicationContext();
testContext.setAttribute("my.key", value);
testContext.getAttribute("my.key");
testContext.removeAttribute("my.key");
```

Chỉ gọi `getApplicationContext()` trong callback mà test context đã có application context sẵn sàng. Không nên buộc context phải khởi tạo sớm chỉ để listener ghi log hoặc đo thời gian, vì điều đó có thể làm tăng chi phí hoặc thay đổi hành vi lazy loading của test.

Đặt tên attribute có namespace riêng, ví dụ dùng tên đầy đủ của listener làm prefix, để tránh đụng key với listener khác. Dọn attribute sau khi sử dụng, đặc biệt nếu giá trị giữ tham chiếu đến test instance, request hoặc tài nguyên có vòng đời ngắn.

## 8. Đăng ký listener mặc định trên toàn bộ test suite

Nếu một listener cần được áp dụng rộng rãi cho nhiều test class, có thể đăng ký nó như listener mặc định thông qua cơ chế Spring factories thay vì lặp lại `@TestExecutionListeners` trên từng class.

Trong các cấu hình Spring TestContext dùng `SpringFactoriesLoader`, file `META-INF/spring.factories` có thể khai báo:

```properties
org.springframework.test.context.TestExecutionListener=\
com.example.testing.TestTimingListener
```

Spring phát hiện listener này như một listener mặc định cùng với các listener mặc định khác. Cần kiểm tra cơ chế đăng ký được hỗ trợ trong phiên bản Spring Framework của dự án và bảo đảm file metadata nằm đúng vị trí trên test runtime classpath.

Đăng ký toàn cục có phạm vi rộng: mọi test context phù hợp có thể nhận listener đó. Vì vậy, listener toàn cục nên có mục đích chung, chi phí thấp và không phụ thuộc một bean hoặc cấu hình chỉ tồn tại trong một module. Với hành vi chỉ dành cho một nhóm test, annotation trên base test class hoặc test class thường rõ ràng hơn.

## 9. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| `@Autowired` trong test instance trở thành `null` | Khai báo `@TestExecutionListeners` nhưng dùng `REPLACE_DEFAULTS`, làm mất `DependencyInjectionTestExecutionListener`. | Dùng `MERGE_WITH_DEFAULTS` hoặc khai báo listener dependency injection nếu thực sự thay toàn bộ defaults. |
| `@Transactional` test không rollback như mong đợi | `TransactionalTestExecutionListener` không được đăng ký. | Kiểm tra `mergeMode` và danh sách listener được đăng ký. |
| `@Sql` không chạy | Thiếu `SqlScriptsTestExecutionListener` sau khi thay defaults. | Giữ defaults hoặc khai báo listener SQL tương ứng. |
| `@DirtiesContext` không đánh dấu context | Listener xử lý `@DirtiesContext` bị loại khỏi danh sách. | Dùng `MERGE_WITH_DEFAULTS` hoặc đăng ký các listener cần thiết. |
| Listener của base class không chạy ở lớp con | Lớp con đặt `inheritListeners = false` hoặc khai báo cấu hình kế thừa không như dự định. | Kiểm tra `inheritListeners` và cấu trúc kế thừa test class. |
| Listener chạy sai thứ tự | Ordering của listener không phù hợp với phụ thuộc giữa các callback. | Dùng `Ordered` hoặc `@Order`, kiểm tra tương tác với thứ tự listener mặc định. |
| Listener không được phát hiện toàn cục | File `spring.factories` sai key, sai vị trí hoặc không có trên test runtime classpath. | Kiểm tra metadata trong `META-INF` và cơ chế factories của phiên bản Spring đang dùng. |
| Trạng thái listener rò rỉ giữa các test | Lưu dữ liệu trong static field hoặc không dọn `TestContext` attribute. | Lưu trạng thái theo `TestContext`, dùng key riêng và xóa sau khi hoàn tất. |

## 10. Quy tắc lựa chọn thực tế

Khi thêm `TestExecutionListener`, hãy quyết định theo phạm vi áp dụng:

1. Chỉ một test class: khai báo `@TestExecutionListeners` trên class và thường chọn `MERGE_WITH_DEFAULTS`.
2. Một nhóm test dùng chung: đặt annotation trên abstract base test class và để `inheritListeners = true` nếu lớp con cần kế thừa.
3. Cả test suite: cân nhắc đăng ký listener mặc định qua Spring factories, với điều kiện listener không phụ thuộc cấu hình riêng của một test.
4. Cần thay toàn bộ hành vi mặc định: dùng `REPLACE_DEFAULTS` và chủ động khai báo mọi listener cần thiết; đây là trường hợp chuyên biệt.

Trong hầu hết tình huống, khi mục tiêu chỉ là bổ sung logging, timing, metadata hoặc chuẩn bị dữ liệu riêng, hãy giữ listener mặc định. Điều đó giúp test tiếp tục nhận được hành vi nhất quán của Spring TestContext Framework.

## 11. Kết luận

`@TestExecutionListeners` đăng ký listener tùy chỉnh vào vòng đời Spring TestContext. `mergeMode` quyết định listener tùy chỉnh được gộp với listener mặc định hay thay thế chúng; `inheritListeners` quyết định cấu hình từ lớp cha có được kế thừa hay không. Khi chỉ muốn bổ sung một listener, `MERGE_WITH_DEFAULTS` thường là lựa chọn an toàn vì vẫn giữ dependency injection, transaction test, SQL scripts và các chức năng chuẩn khác. Chỉ dùng `REPLACE_DEFAULTS` khi thật sự muốn tự quản lý danh sách listener và hiểu rõ những hành vi mặc định cần đăng ký lại.

## Tài liệu tham khảo

- [Spring Framework Reference — TestExecutionListener](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tel.html)
- [Spring Framework Javadoc — `@TestExecutionListeners`](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/test/context/TestExecutionListeners.html)
- [Spring Framework Javadoc — `TestExecutionListener`](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/test/context/TestExecutionListener.html)
