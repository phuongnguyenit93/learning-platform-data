# Thứ tự listener và đối xứng callback trước hoặc sau

Spring TestContext Framework cho phép mở rộng vòng đời kiểm thử thông qua `TestExecutionListener`. Listener có thể chuẩn bị dữ liệu trước test, ghi nhận kết quả sau test, quản lý transaction, inject dependency hoặc tích hợp thêm hạ tầng kiểm thử. Khi nhiều listener cùng tham gia, thứ tự callback ảnh hưởng trực tiếp đến việc tài nguyên được chuẩn bị, sử dụng và giải phóng.

Spring bảo đảm một quy tắc quan trọng: các callback dạng **before** được gọi theo thứ tự listener đã đăng ký, còn callback dạng **after** được gọi theo thứ tự ngược lại. Đây là hành vi wrapping, tương tự cách các lớp lồng nhau mở và đóng tài nguyên theo kiểu stack. Listener đứng trước có thể mở một phạm vi cho listener đứng sau; khi kết thúc, listener đứng sau đóng phạm vi của nó trước, rồi listener đứng trước mới đóng phạm vi bên ngoài.

Hiểu đúng thứ tự này giúp viết custom listener tương thích với listener mặc định của Spring, đặc biệt khi test dùng transaction, SQL script, context lifecycle hoặc tài nguyên cần cleanup.

## 1. `TestExecutionListener` và `TestContextManager`

`TestExecutionListener` là một interface trong `org.springframework.test.context`. Nó nhận các sự kiện trong vòng đời test thông qua `TestContextManager`. Listener không phải JUnit extension thay thế cho Spring; nó là một điểm mở rộng bên trong Spring TestContext Framework.

`TestContextManager` quản lý `TestContext` của một test class và điều phối listener tại những thời điểm xác định. `TestContext` cung cấp thông tin về test class, test instance, test method, application context và exception của lần thực thi hiện tại.

Một số trách nhiệm thường được triển khai bằng listener:

- Chuẩn bị mock servlet request/response cho web test.
- Inject dependency vào test instance.
- Bắt đầu hoặc kết thúc transaction kiểm thử.
- Chạy SQL script trước hoặc sau test method.
- Làm mới hoặc đánh dấu application context cần loại khỏi cache.
- Ghi log, đo thời gian hoặc thu thập dữ liệu chẩn đoán.
- Tích hợp resource lifecycle của một thư viện kiểm thử.

Các callback trong `TestExecutionListener` có implementation mặc định rỗng. Vì vậy, custom listener có thể kế thừa `AbstractTestExecutionListener` và chỉ override những callback cần thiết.

## 2. Các callback trong vòng đời test

`TestExecutionListener` định nghĩa các callback chính sau:

| Callback | Thời điểm được gọi | Công việc thường phù hợp |
| --- | --- | --- |
| `beforeTestClass(TestContext)` | Trước các callback `@BeforeAll` của framework kiểm thử. | Chuẩn bị tài nguyên cấp class. |
| `prepareTestInstance(TestContext)` | Sau khi tạo test instance, trước các callback setup của method. | Xử lý test instance hoặc chuẩn bị dữ liệu cần thiết cho instance. |
| `beforeTestMethod(TestContext)` | Trước callback `@BeforeEach` và trước test method. | Chuẩn bị trạng thái cho một test method. |
| `beforeTestExecution(TestContext)` | Ngay trước khi thực thi test method, sau setup như `@BeforeEach`. | Đo thời gian hoặc ghi nhận thời điểm bắt đầu phần thân test. |
| `afterTestExecution(TestContext)` | Ngay sau phần thân test method, trước teardown như `@AfterEach`. | Đo thời gian thực thi method hoặc thu thập kết quả ngay sau method. |
| `afterTestMethod(TestContext)` | Sau callback `@AfterEach` của framework kiểm thử. | Cleanup cần chạy sau teardown của test method. |
| `afterTestClass(TestContext)` | Sau callback `@AfterAll` của framework kiểm thử. | Giải phóng tài nguyên cấp class. |

Với JUnit Jupiter tích hợp qua `SpringExtension`, trình tự khái quát như sau:

```text
Test class bắt đầu
    |
    v
beforeTestClass
    |
    v
@BeforeAll
    |
    v
Tạo test instance
    |
    v
prepareTestInstance
    |
    v
beforeTestMethod
    |
    v
@BeforeEach
    |
    v
beforeTestExecution
    |
    v
Test method
    |
    v
afterTestExecution
    |
    v
@AfterEach
    |
    v
afterTestMethod
    |
    v
@AfterAll
    |
    v
afterTestClass
```

Sơ đồ mô tả thứ tự ở mức khái quát. Các extension khác của JUnit có thể tham gia vòng đời riêng, nhưng các hook của Spring TestContext được đặt ở những ranh giới tương ứng như trên.

`prepareTestInstance` không có callback đối xứng tên `afterPrepareTestInstance`. Các cặp callback có ý nghĩa mở/đóng phạm vi gồm `beforeTestClass`/`afterTestClass`, `beforeTestMethod`/`afterTestMethod` và `beforeTestExecution`/`afterTestExecution`.

## 3. Quy tắc thứ tự: before xuôi, after ngược

Giả sử có ba listener được đăng ký theo thứ tự `ListenerA`, `ListenerB`, `ListenerC`.

Khi bắt đầu một lifecycle phase, callback `before` được gọi theo thứ tự đăng ký:

```text
ListenerA.before...
    ListenerB.before...
        ListenerC.before...
            Test / phần xử lý được bọc
```

Khi kết thúc phase, callback `after` được gọi theo thứ tự ngược:

```text
            ListenerC.after...
        ListenerB.after...
    ListenerA.after...
```

Có thể hình dung listener A bao ngoài B, B bao ngoài C. A mở tài nguyên trước; B mở tài nguyên sau; C mở tài nguyên cuối cùng. Khi đóng, C giải phóng trước, rồi B, cuối cùng A. Quy tắc này tránh trường hợp tài nguyên bên ngoài bị đóng khi tài nguyên bên trong vẫn còn cần sử dụng.

Tài liệu Spring gọi hành vi này là **wrapping behavior**. Nếu A được đăng ký trước B:

- Mọi callback `before` của A được gọi trước callback `before` của B.
- Callback `after` của A được gọi sau callback `after` của B.

Đây là quy tắc thứ tự giữa các listener cho cùng lifecycle phase. Nó không có nghĩa mọi callback `before...` luôn chạy trước mọi callback `after...` của một listener khác; mỗi callback vẫn được gọi tại thời điểm riêng trong vòng đời test.

## 4. Ví dụ thứ tự với hai listener

Ta có thể tạo listener ghi log để quan sát thứ tự:

```java
public class FirstListener extends AbstractTestExecutionListener {

    @Override
    public void beforeTestMethod(TestContext testContext) {
        System.out.println("A beforeTestMethod");
    }

    @Override
    public void afterTestMethod(TestContext testContext) {
        System.out.println("A afterTestMethod");
    }
}

public class SecondListener extends AbstractTestExecutionListener {

    @Override
    public void beforeTestMethod(TestContext testContext) {
        System.out.println("B beforeTestMethod");
    }

    @Override
    public void afterTestMethod(TestContext testContext) {
        System.out.println("B afterTestMethod");
    }
}
```

Nếu A được đăng ký trước B, log theo thứ tự dự kiến là:

```text
A beforeTestMethod
B beforeTestMethod
... test method và lifecycle của framework ...
B afterTestMethod
A afterTestMethod
```

Điều quan trọng không nằm ở log cụ thể mà ở tính đối xứng: callback before mở phạm vi theo thứ tự A rồi B; callback after đóng phạm vi B rồi A.

## 5. Vì sao Spring cần wrapping behavior?

Listener thường phụ thuộc vào tài nguyên do listener khác quản lý. Một ví dụ trong Spring là `TransactionalTestExecutionListener` và `SqlScriptsTestExecutionListener`.

`TransactionalTestExecutionListener` quản lý transaction kiểm thử. `SqlScriptsTestExecutionListener` thực thi SQL script được khai báo bằng `@Sql`. Spring đăng ký SQL listener sau transaction listener để script có thể chạy bên trong transaction do transaction listener quản lý.

Thứ tự có thể hình dung:

```text
TransactionalTestExecutionListener.before...
    Bắt đầu transaction
    |
    v
SqlScriptsTestExecutionListener.before...
    Chạy SQL setup trong transaction
    |
    v
Test method
    |
    v
SqlScriptsTestExecutionListener.after...
    Chạy SQL teardown trong transaction nếu cấu hình yêu cầu
    |
    v
TransactionalTestExecutionListener.after...
    Commit hoặc rollback theo cấu hình test
```

SQL listener cần chạy sau khi transaction đã bắt đầu. Ở chiều ngược lại, cleanup SQL của nó cần chạy trước khi transaction listener hoàn tất transaction. Nếu thứ tự after không được đảo ngược, transaction có thể kết thúc trước khi SQL teardown được thực thi.

Đây là lý do thứ tự listener không chỉ để sắp xếp log. Nó định nghĩa phạm vi tài nguyên mà listener khác có thể sử dụng.

## 6. Đăng ký custom listener bằng `@TestExecutionListeners`

Với listener chỉ dùng trong một test class hoặc một nhóm class, có thể đăng ký tường minh:

```java
@SpringJUnitConfig(TestConfig.class)
@TestExecutionListeners(
        listeners = {
                FirstListener.class,
                SecondListener.class
        },
        mergeMode = TestExecutionListeners.MergeMode.MERGE_WITH_DEFAULTS
)
class ListenerOrderTest {

    @Test
    void shouldRunWithCustomListeners() {
        // Test body.
    }
}
```

`MERGE_WITH_DEFAULTS` yêu cầu Spring giữ các listener mặc định và hợp nhất custom listener vào danh sách. Đây thường là lựa chọn phù hợp khi muốn bổ sung một listener cho test mà vẫn cần dependency injection, transaction, servlet mock hoặc các tính năng mặc định khác.

Nếu khai báo `@TestExecutionListeners` mà không chọn merge mode, mặc định là `REPLACE_DEFAULTS`. Khi đó danh sách listener mặc định có thể bị thay thế bởi danh sách được khai báo, khiến các tính năng như dependency injection hoặc transaction không còn hoạt động như trước. Hãy chỉ thay thế defaults khi thật sự muốn tự quản lý toàn bộ danh sách listener.

`inheritListeners` cho phép cấu hình listener được kế thừa theo hierarchy test class. Khi có superclass chứa `@TestExecutionListeners`, cần quyết định rõ có muốn kế thừa listener đó hay không. Nếu override cấu hình, hãy xem xét cả `inheritListeners` và `mergeMode` để tránh vô tình bỏ mất listener cần thiết.

## 7. Đặt thứ tự bằng `Ordered` hoặc `@Order`

Các listener được Spring phát hiện mặc định được sắp xếp bằng `AnnotationAwareOrderComparator`. Có thể khai báo thứ tự bằng cách implement `Ordered` hoặc gắn annotation `@Order`.

Ví dụ dùng `Ordered`:

```java
public class AuditTestExecutionListener
        extends AbstractTestExecutionListener
        implements Ordered {

    @Override
    public int getOrder() {
        return 500;
    }

    @Override
    public void beforeTestMethod(TestContext testContext) {
        // Ghi nhận thông tin trước test method.
    }

    @Override
    public void afterTestMethod(TestContext testContext) {
        // Ghi nhận thông tin sau test method.
    }
}
```

Hoặc dùng `@Order`:

```java
@Order(500)
public class AuditTestExecutionListener
        extends AbstractTestExecutionListener {
    // Callback cần thiết.
}
```

Giá trị order nhỏ hơn được ưu tiên đứng trước trong danh sách. Do đó, listener có order `500` được gọi trước listener có order `1000` ở callback before, và được gọi sau listener `1000` ở callback after.

Khi cần listener chạy bên trong một listener khác, đặt nó sau listener bao ngoài. Khi cần tài nguyên được chuẩn bị trước cho các listener khác, đặt listener quản lý tài nguyên ở vị trí sớm hơn. Hãy chọn giá trị order có chủ đích và tránh phụ thuộc vào thứ tự không xác định giữa các listener có cùng order.

### Minh họa order và wrapping

Giả sử:

| Listener | Order |
| --- | ---: |
| `OuterListener` | 100 |
| `AuditListener` | 500 |
| `InnerListener` | 900 |

Thứ tự callback:

```text
before: Outer(100) -> Audit(500) -> Inner(900)
after:  Inner(900) -> Audit(500) -> Outer(100)
```

Nếu `OuterListener` mở transaction hoặc resource scope và `InnerListener` thực thi SQL cần transaction đó, order như trên cho phép SQL chạy trong phạm vi transaction.

## 8. Kết hợp custom listener với listener mặc định

Spring cung cấp nhiều `TestExecutionListener` mặc định, ví dụ listener cho servlet mock, dependency injection, transaction, SQL script, application event, bean override và reset Mockito mock. Danh sách cụ thể thay đổi theo phiên bản Spring và các module có trên classpath.

Không nên sao chép một danh sách order cố định từ một phiên bản rồi coi đó là hợp đồng cho mọi phiên bản. Hãy xem Javadoc và tài liệu của phiên bản Spring đang dùng, đồng thời chỉ phụ thuộc vào quan hệ thứ tự mà ứng dụng thực sự cần.

Khi thêm custom listener, thông thường nên merge với defaults:

```java
@TestExecutionListeners(
        listeners = AuditTestExecutionListener.class,
        mergeMode = TestExecutionListeners.MergeMode.MERGE_WITH_DEFAULTS
)
```

Nếu listener cần được dùng rộng rãi trong nhiều module hoặc test suite, có thể đăng ký nó như default listener qua cơ chế `SpringFactoriesLoader` của Spring Test. Cách đăng ký mặc định cần được thực hiện đúng theo cơ chế metadata và phiên bản Spring đang dùng. Listener tự đăng ký cần có constructor public không tham số để Spring có thể khởi tạo.

Với một custom listener chỉ phục vụ một test class, đăng ký qua annotation thường dễ hiểu và giới hạn phạm vi ảnh hưởng hơn.

## 9. Viết listener có callback trước và sau cân xứng

Một listener thường mở tài nguyên ở callback before và đóng tài nguyên tương ứng ở callback after. Ví dụ listener đo thời gian test method:

```java
public class TimingTestExecutionListener
        extends AbstractTestExecutionListener {

    private static final String START_TIME =
            TimingTestExecutionListener.class.getName() + ".START_TIME";

    @Override
    public void beforeTestExecution(TestContext testContext) {
        testContext.setAttribute(START_TIME, System.nanoTime());
    }

    @Override
    public void afterTestExecution(TestContext testContext) {
        Long start = (Long) testContext.removeAttribute(START_TIME);
        if (start != null) {
            long elapsedNanos = System.nanoTime() - start;
            System.out.println("Test duration: " + elapsedNanos + " ns");
        }
    }
}
```

Listener lưu thời điểm bắt đầu trong `TestContext` và xóa thuộc tính khi hoàn tất. `TestContext` là nơi phù hợp để lưu state gắn với lần thực thi test thay vì dùng static mutable map dùng chung toàn JVM.

Callback `beforeTestExecution` và `afterTestExecution` bao quanh phần thân test method. Do đó thời gian đo không bao gồm `@BeforeEach` và `@AfterEach`. Nếu muốn tính cả setup và teardown của từng method, dùng cặp `beforeTestMethod` và `afterTestMethod`.

Với tài nguyên cần cleanup, hãy đảm bảo callback after có thể giải phóng tài nguyên ngay cả khi test method thất bại. Không chỉ cleanup trong nhánh thành công. Spring TestContext cung cấp thông tin về exception trong `TestContext`, vì vậy listener có thể ghi nhận trạng thái test để log hoặc cleanup phù hợp.

## 10. Phân biệt các cặp callback theo phạm vi

Không nên chọn callback chỉ dựa trên tên before/after. Hãy xem phần nào của test lifecycle mà listener cần bao quanh.

| Nhu cầu | Callback nên xem xét | Phạm vi được bao quanh |
| --- | --- | --- |
| Chuẩn bị tài nguyên dùng cho toàn test class | `beforeTestClass` / `afterTestClass` | Toàn bộ class, bao gồm các method trong class. |
| Chuẩn bị trước từng test method và cleanup sau teardown | `beforeTestMethod` / `afterTestMethod` | Setup method, test method và teardown method. |
| Đo hoặc quan sát riêng phần thân test method | `beforeTestExecution` / `afterTestExecution` | Chỉ phần thực thi test method. |
| Inject hoặc hậu xử lý test instance | `prepareTestInstance` | Sau khi instance được tạo, trước method setup. Không có callback after đối xứng. |

Ví dụ: nếu một listener mở transaction trước `@BeforeEach`, callback phù hợp thường là `beforeTestMethod`; nếu chỉ muốn bắt đầu đồng hồ ngay trước assertion/test logic, dùng `beforeTestExecution`.

## 11. Thứ tự callback khi listener có exception

Callback listener là một phần của test infrastructure. Nếu callback after ném exception, Spring TestContext vẫn cố gắng gọi các listener after còn lại; exception đầu tiên được ném lại và các exception tiếp theo có thể được gắn dưới dạng suppressed exception. Điều này giúp cleanup của listener khác vẫn có cơ hội chạy.

Vì vậy:

- Callback after nên cleanup theo kiểu an toàn khi được gọi sau test thất bại.
- Không nên để một lỗi cleanup đơn lẻ ngăn các resource khác được giải phóng.
- Khi cần nhiều bước cleanup trong cùng listener, dùng `try/finally` để đảm bảo các bước sau vẫn được thực hiện.
- Giữ exception gốc của test trong thông tin chẩn đoán; tránh thay thế nó bằng một lỗi cleanup thiếu ngữ cảnh.

Ví dụ:

```java
@Override
public void afterTestMethod(TestContext testContext) {
    try {
        closeTemporarySession(testContext);
    }
    finally {
        removeTemporaryState(testContext);
    }
}
```

Không nên giả định callback after chỉ chạy khi test thành công. Cleanup cần được thiết kế để xử lý cả trường hợp test method ném exception.

## 12. Quan hệ với JUnit lifecycle và giới hạn framework

`TestExecutionListener` thuộc Spring TestContext Framework, còn `@BeforeEach`, `@AfterEach`, `@BeforeAll` và `@AfterAll` thuộc JUnit Jupiter. Spring tích hợp hai hệ lifecycle bằng `SpringExtension`.

Điều này có nghĩa listener callback và JUnit lifecycle method là hai lớp hook khác nhau:

- `beforeTestMethod` chạy trước `@BeforeEach`.
- `beforeTestExecution` chạy sau `@BeforeEach` và ngay trước test method.
- `afterTestExecution` chạy ngay sau test method và trước `@AfterEach`.
- `afterTestMethod` chạy sau `@AfterEach`.

Không dùng listener để thay thế mọi `@BeforeEach` hoặc `@AfterEach`. Listener phù hợp khi muốn tích hợp ở cấp TestContext, áp dụng cho nhiều test class hoặc cần phối hợp với listener khác. JUnit lifecycle method phù hợp với setup/teardown cục bộ của test class.

Không phải mọi testing framework adapter đều hỗ trợ mọi callback. Ví dụ, một số cấu hình JUnit 4 dùng `SpringMethodRule` không hỗ trợ `beforeTestExecution` và `afterTestExecution`. Khi chọn callback, kiểm tra khả năng hỗ trợ của framework integration đang dùng.

## 13. Listener order trong test có transaction và SQL script

Xét test dùng `@Transactional` và `@Sql`:

```java
@SpringJUnitConfig(DatabaseTestConfig.class)
@Transactional
@Sql(
        scripts = "/sql/insert-person.sql",
        executionPhase = Sql.ExecutionPhase.BEFORE_TEST_METHOD
)
@Sql(
        scripts = "/sql/delete-person.sql",
        executionPhase = Sql.ExecutionPhase.AFTER_TEST_METHOD
)
class PersonSqlTest {

    @Test
    void shouldReadPersonInsertedBySqlScript() {
        // Đọc dữ liệu đã được SQL script chuẩn bị.
    }
}
```

`TransactionalTestExecutionListener` và `SqlScriptsTestExecutionListener` phối hợp nhờ thứ tự đăng ký và wrapping behavior. Transaction listener mở transaction trước; SQL listener chạy script setup trong transaction đó. Ở chiều after, SQL listener được gọi trước transaction listener, nên script teardown có thể chạy trong cùng transaction trước khi transaction kết thúc.

Đối với test transaction mặc định rollback, script setup và thao tác test có thể được rollback cùng transaction. Hành vi cụ thể còn phụ thuộc `@SqlConfig`, transaction manager và cấu hình execution phase. Không nên suy ra rằng mọi SQL script đều luôn được rollback nếu script được cấu hình chạy ngoài transaction hoặc dùng transaction mode khác.

## 14. AOT và custom listener

Ahead-of-Time processing có thể ảnh hưởng đến cách ứng dụng hoặc test context được chuẩn bị, nhưng không thay đổi ý nghĩa wrapping của thứ tự listener: `TestContextManager` vẫn điều phối các callback theo danh sách listener đã được cấu hình.

Khi test chạy trong môi trường có AOT processing hoặc native image, custom listener và các class mà listener sử dụng cần nằm trong test runtime và có thể được khởi tạo theo cơ chế mà môi trường đó hỗ trợ. Nếu listener được đăng ký qua metadata, bảo đảm metadata được đóng gói và discovery hoạt động trong môi trường build/run tương ứng. Với test native/AOT, không nên dựa vào classpath scanning hoặc reflection động tùy tiện mà không xác nhận các yêu cầu runtime hints của ứng dụng.

Thứ tự listener nên được khai báo tường minh bằng `Ordered` hoặc `@Order` khi thứ tự có ý nghĩa. Không dựa vào thứ tự ngẫu nhiên của classpath hoặc thứ tự file metadata để thiết lập quan hệ phụ thuộc quan trọng.

## 15. Những lỗi thường gặp khi cấu hình listener

**Cho rằng callback after chạy cùng chiều với callback before.**

Spring dùng wrapping behavior: before theo thứ tự đăng ký, after theo thứ tự ngược. Hãy thiết kế listener theo mô hình mở trước, đóng sau.

**Đặt order ngược với dependency tài nguyên.**

Listener cần mở transaction hoặc resource scope phải đứng trước listener sử dụng nó. Listener sử dụng resource sẽ cleanup trước khi listener quản lý resource đóng nó.

**Đăng ký custom listener nhưng vô tình thay thế defaults.**

`@TestExecutionListeners` mặc định dùng `REPLACE_DEFAULTS`. Nếu cần giữ dependency injection, transaction và listener mặc định, chọn `MERGE_WITH_DEFAULTS`.

**Dùng cùng order cho nhiều listener rồi dựa vào thứ tự tình cờ.**

Nếu quan hệ thứ tự quan trọng, khai báo giá trị order rõ ràng và không phụ thuộc vào thứ tự không được cam kết giữa các listener có cùng order.

**Dùng `beforeTestMethod` để đo riêng thời gian test method.**

Callback này chạy trước `@BeforeEach`. Nếu muốn bỏ thời gian setup khỏi phép đo, dùng `beforeTestExecution` và `afterTestExecution`.

**Chỉ cleanup khi test thành công.**

Callback after phải được thiết kế cho cả trường hợp test ném exception. Dùng `try/finally` để đảm bảo cleanup trong listener.

**Dùng listener toàn cục cho logic chỉ thuộc một test.**

Listener mặc định được áp dụng rộng có thể ảnh hưởng nhiều test class. Nếu chỉ cần một nhóm nhỏ, đăng ký bằng `@TestExecutionListeners` tại phạm vi phù hợp.

## 16. Quy trình thiết kế và xác nhận thứ tự listener

Khi tạo custom listener, có thể làm theo các bước:

1. Xác định callback phù hợp với phạm vi: class, method setup/teardown hay riêng phần thân test.
2. Xác định listener cần chạy trước và listener nào cần sử dụng tài nguyên của nó.
3. Đặt `Ordered` hoặc `@Order` để tạo danh sách rõ ràng.
4. Đăng ký listener bằng `@TestExecutionListeners`; dùng `MERGE_WITH_DEFAULTS` nếu vẫn cần listener mặc định.
5. Override callback before để chuẩn bị state hoặc mở resource.
6. Override callback after tương ứng để cleanup theo thứ tự ngược.
7. Dùng `TestContext` để lưu state gắn với lần thực thi, tránh static mutable state.
8. Thử nghiệm bằng listener ghi log hoặc assertion thứ tự ở phạm vi test nhỏ.
9. Kiểm tra cả trường hợp test method thất bại để bảo đảm callback cleanup vẫn xử lý tài nguyên.
10. Nếu dùng JUnit adapter hoặc môi trường AOT/native, xác nhận callback và listener discovery được hỗ trợ trong cấu hình đó.

## Kết luận

`TestExecutionListener` mở rộng vòng đời test thông qua `TestContextManager`. Spring bảo đảm wrapping behavior: callback before chạy theo thứ tự listener đã đăng ký, callback after chạy theo thứ tự ngược. Quy tắc này cho phép listener mở resource scope theo thứ tự lồng nhau và đóng chúng an toàn theo kiểu stack.

Hãy chọn đúng cặp callback theo phạm vi cần bao quanh, đặt thứ tự bằng `Ordered` hoặc `@Order`, và dùng `MERGE_WITH_DEFAULTS` khi bổ sung custom listener mà vẫn cần listener mặc định của Spring. Thiết kế callback after để cleanup cả khi test thất bại sẽ giúp hạ tầng kiểm thử ổn định và dễ mở rộng.

Tài liệu tham khảo: [Spring Framework Reference — TestExecutionListener Configuration](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tel-config.html) và [TestExecutionListener Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/test/context/TestExecutionListener.html).
