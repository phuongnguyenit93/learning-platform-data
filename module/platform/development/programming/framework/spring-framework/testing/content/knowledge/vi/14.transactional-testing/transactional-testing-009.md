# TestTransaction để kết thúc, bắt đầu và đánh dấu commit

Spring TestContext hỗ trợ transaction gắn với từng test method. Khi test được đánh dấu `@Transactional` và có transaction manager phù hợp, Spring thường bắt đầu một test-managed transaction trước khi chạy test và rollback transaction đó sau khi test kết thúc. Cơ chế rollback mặc định giúp dữ liệu kiểm thử không tồn tại sau mỗi method.

Có những trường hợp cần kiểm tra dữ liệu sau khi commit thật, hoặc cần kết thúc transaction hiện tại rồi mở một transaction mới ngay trong cùng test method. Spring cung cấp lớp tiện ích `TestTransaction` cho những thao tác này. Test có thể kiểm tra trạng thái transaction, đánh dấu commit hoặc rollback, kết thúc transaction hiện tại và bắt đầu một test-managed transaction mới.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích test-managed transaction và vai trò của `TransactionalTestExecutionListener`.
- Hiểu các phương thức `isActive`, `isFlaggedForRollback`, `flagForCommit`, `flagForRollback`, `end` và `start`.
- Phân biệt việc đánh dấu commit với thời điểm commit thực sự diễn ra.
- Chủ động commit transaction của test rồi mở transaction mới để xác nhận dữ liệu.
- Ghi đè quyết định commit/rollback mặc định từ `@Commit` hoặc `@Rollback`.
- Xử lý trường hợp test không có transaction đang hoạt động.
- Hiểu giới hạn của test transaction với HTTP request chạy ở thread khác và transaction độc lập.
- Dọn dữ liệu sau khi chủ động commit để các test khác vẫn độc lập.

## 1. Test-managed transaction là gì?

Spring TestContext có thể quản lý transaction cho test thông qua `TransactionalTestExecutionListener`. Khi test class hoặc test method được đánh dấu `@Transactional`, listener bắt đầu một transaction trước khi test method chạy và kết thúc transaction sau khi method hoàn tất.

Ví dụ:

~~~java
@SpringBootTest
@Transactional
class OrderRepositoryTest {

    @Autowired
    OrderRepository orderRepository;

    @Test
    void savesAnOrderInsideTestTransaction() {
        orderRepository.save(new Order("ORD-1001"));

        assertEquals(1, orderRepository.count());
    }
}
~~~

Trong cấu hình thông thường, transaction của test được rollback sau method. Vì vậy, bản ghi được tạo trong test không được giữ lại sau khi test kết thúc, miễn là thao tác ghi thực sự tham gia vào transaction đó.

Có ba khái niệm cần phân biệt:

| Khái niệm | Ý nghĩa |
|---|---|
| Test-managed transaction | Transaction do Spring TestContext bắt đầu và kết thúc quanh test |
| Application-managed transaction | Transaction do code ứng dụng hoặc transaction boundary của service quản lý |
| Transaction của tài nguyên ngoài | Transaction trên database, message broker hoặc hệ thống khác có cơ chế quản lý riêng |

`TestTransaction` điều khiển test-managed transaction hiện tại. Nó không phải API tổng quát để commit mọi transaction đang chạy trong ứng dụng, cũng không thay thế `TransactionTemplate` hay `PlatformTransactionManager` trong code production.

Test-managed transaction thường gắn với thread thực thi test. Khi test method chạy trong transaction, các repository hoặc service tham gia cùng transaction manager có thể nhìn thấy thay đổi chưa commit của test.

## 2. Vì sao cần điều khiển transaction bằng TestTransaction?

Rollback tự động là lựa chọn tốt cho phần lớn integration test. Tuy nhiên, một số hành vi chỉ xuất hiện sau khi transaction kết thúc:

- Database chỉ phát hành một số constraint hoặc trigger khi commit.
- Cần xác nhận dữ liệu đã commit có thể được đọc trong transaction mới.
- Cần kiểm tra hành vi của code khi transaction trước đã kết thúc.
- Cần tạo một transaction mới trong cùng test method để kiểm tra trạng thái sau commit.
- Cần commit một phần dữ liệu chuẩn bị rồi tiếp tục kiểm tra một luồng khác.

Ví dụ, nếu chỉ gọi repository rồi assert trong cùng transaction, test có thể đọc dữ liệu từ persistence context hoặc transaction hiện tại. Kết quả đó chưa luôn chứng minh dữ liệu đã được commit và nhìn thấy từ transaction khác.

`TestTransaction` cho phép kết thúc transaction hiện tại theo quyết định đã đánh dấu. Sau đó, test có thể bắt đầu transaction mới để kiểm tra dữ liệu đã được commit hoặc thực hiện một phần công việc tiếp theo.

~~~mermaid
flowchart TD
    A["Spring bắt đầu test-managed transaction"] --> B["Test ghi dữ liệu"]
    B --> C["TestTransaction.flagForCommit()"]
    C --> D["TestTransaction.end()"]
    D --> E["Transaction được commit"]
    E --> F["TestTransaction.start()"]
    F --> G["Transaction mới bắt đầu"]
    G --> H["Đọc và kiểm tra dữ liệu đã commit"]
    H --> I["Đánh dấu rollback"]
    I --> J["TestTransaction.end()"]
~~~

Điểm quan trọng là `flagForCommit` chỉ thay đổi quyết định kết thúc transaction. Lệnh commit thực sự diễn ra khi transaction được kết thúc bằng `end`.

## 3. Các phương thức của TestTransaction

`TestTransaction` nằm trong package:

~~~java
import org.springframework.test.context.transaction.TestTransaction;
~~~

Các phương thức chính đều là static:

| Phương thức | Chức năng |
|---|---|
| `TestTransaction.isActive()` | Kiểm tra hiện có test-managed transaction đang hoạt động hay không |
| `TestTransaction.isFlaggedForRollback()` | Kiểm tra transaction hiện tại đang được đánh dấu rollback hay không |
| `TestTransaction.flagForCommit()` | Đánh dấu transaction hiện tại sẽ commit khi kết thúc |
| `TestTransaction.flagForRollback()` | Đánh dấu transaction hiện tại sẽ rollback khi kết thúc |
| `TestTransaction.end()` | Kết thúc test-managed transaction hiện tại theo cờ commit/rollback |
| `TestTransaction.start()` | Bắt đầu một test-managed transaction mới |

Các phương thức này chỉ có ý nghĩa trong test được tích hợp với Spring TestContext và có hỗ trợ transaction. Nếu không có test-managed transaction đang hoạt động, các thao tác yêu cầu transaction hiện tại có thể ném `IllegalStateException`.

Hãy kiểm tra `isActive()` trước khi thao tác trong những test có nhiều nhánh hoặc có thể chạy với cấu hình transaction khác nhau.

## 4. Kiểm tra transaction hiện tại bằng isActive và isFlaggedForRollback

`isActive()` cho biết test-managed transaction có đang hoạt động hay không.

~~~java
@Test
@Transactional
void checksTransactionState() {
    assertTrue(TestTransaction.isActive());
}
~~~

Trong một test có `@Transactional`, listener thường đã bắt đầu transaction trước khi test method chạy. Vì vậy, `isActive()` thường trả về `true` trong phần thân method.

`isFlaggedForRollback()` cho biết transaction hiện tại được đánh dấu rollback hay commit khi kết thúc. Với hành vi mặc định của test-managed transaction, transaction thường được đánh dấu rollback.

~~~java
@Test
@Transactional
void rollsBackByDefault() {
    assertTrue(TestTransaction.isActive());
    assertTrue(TestTransaction.isFlaggedForRollback());
}
~~~

Nếu test được đánh dấu `@Commit` hoặc `@Rollback(false)`, quyết định mặc định sẽ là commit. Có thể dùng `isFlaggedForRollback()` để xác nhận trạng thái hiện tại trước khi gọi `end`.

Đừng nhầm trạng thái này với việc transaction đã kết thúc. Một transaction có thể đang active nhưng đã được đánh dấu commit; dữ liệu chỉ được commit khi transaction được kết thúc.

## 5. Đánh dấu commit bằng flagForCommit

`flagForCommit()` yêu cầu Spring commit test-managed transaction khi transaction được kết thúc.

~~~java
@Test
@Transactional
void commitsTheCurrentTestTransaction() {
    orderRepository.save(new Order("ORD-1001"));

    TestTransaction.flagForCommit();

    assertFalse(TestTransaction.isFlaggedForRollback());

    TestTransaction.end();

    assertFalse(TestTransaction.isActive());
}
~~~

Trình tự:

1. Spring bắt đầu transaction trước test method.
2. Test ghi dữ liệu vào transaction.
3. `flagForCommit()` thay đổi quyết định kết thúc từ rollback sang commit.
4. `end()` kết thúc transaction và thực hiện commit.
5. Sau khi `end()` hoàn tất, không còn test-managed transaction đang hoạt động.

`flagForCommit()` không commit ngay tại thời điểm được gọi. Nếu test gọi phương thức này rồi tiếp tục ghi dữ liệu, các thay đổi tiếp theo vẫn thuộc transaction hiện tại và sẽ được commit khi `end()` được gọi.

Vì commit có thể làm dữ liệu tồn tại trong database sau khi test kết thúc, hãy dùng nó có chủ đích. Test nên có chiến lược dọn dữ liệu hoặc dùng database/schema riêng.

## 6. Đánh dấu rollback bằng flagForRollback

`flagForRollback()` đặt transaction hiện tại về quyết định rollback khi kết thúc.

~~~java
@Test
@Transactional
void explicitlyMarksTransactionForRollback() {
    orderRepository.save(new Order("ORD-1002"));

    TestTransaction.flagForRollback();

    assertTrue(TestTransaction.isFlaggedForRollback());

    TestTransaction.end();

    assertFalse(TestTransaction.isActive());
}
~~~

Với test-managed transaction thông thường, rollback vốn là mặc định. Gọi `flagForRollback()` hữu ích khi:

- Trước đó test đã gọi `flagForCommit()`.
- Test có annotation `@Commit` hoặc `@Rollback(false)`.
- Test muốn thể hiện rõ quyết định rollback ở một điểm cụ thể.
- Test bắt đầu transaction mới và muốn bảo đảm transaction mới được rollback.

`flagForRollback()` cũng chỉ đặt cờ. Rollback thực sự diễn ra khi transaction được kết thúc bằng `end`.

## 7. Kết thúc transaction bằng end

`end()` kết thúc test-managed transaction đang hoạt động. Spring dựa vào cờ rollback/commit hiện tại để quyết định kết quả.

~~~java
@Test
@Transactional
void endsTheCurrentTransaction() {
    orderRepository.save(new Order("ORD-1003"));

    TestTransaction.flagForRollback();
    TestTransaction.end();

    assertFalse(TestTransaction.isActive());
}
~~~

Nếu transaction được đánh dấu rollback, `end()` rollback. Nếu transaction được đánh dấu commit, `end()` commit.

Khi không có transaction đang hoạt động, không thể kết thúc một transaction hiện tại. Vì vậy, hãy tránh gọi `end()` lặp lại mà không kiểm tra trạng thái.

Sau khi `end()` hoàn tất:

- Transaction hiện tại không còn active.
- Persistence context gắn với transaction đã kết thúc không còn là nơi để tiếp tục ghi dữ liệu như trước.
- Các thao tác repository tiếp theo có thể mở transaction riêng theo cấu hình của repository.
- Test có thể gọi `start()` để mở một test-managed transaction mới nếu method hỗ trợ transaction.

Đừng dùng `end()` như cách đóng toàn bộ `ApplicationContext` hoặc kết thúc mọi transaction trong ứng dụng. Nó chỉ điều khiển test-managed transaction hiện tại.

## 8. Bắt đầu transaction mới bằng start

`start()` bắt đầu một test-managed transaction mới trong cùng test method.

~~~java
@Test
@Transactional
void endsOneTransactionAndStartsAnother() {
    orderRepository.save(new Order("ORD-1004"));

    TestTransaction.flagForRollback();
    TestTransaction.end();

    assertFalse(TestTransaction.isActive());

    TestTransaction.start();

    assertTrue(TestTransaction.isActive());

    orderRepository.save(new Order("ORD-1005"));
}
~~~

Trong ví dụ này, transaction đầu tiên được rollback. Sau đó, `start()` bắt đầu transaction mới để test tiếp tục thao tác với repository.

Không gọi `start()` khi test-managed transaction hiện tại vẫn active. Nếu muốn bắt đầu transaction mới, hãy kết thúc transaction hiện tại trước.

Test method cần được cấu hình để chạy với test-managed transaction và phải có transaction manager phù hợp. Nếu test không có `@Transactional` hoặc listener transaction không được kích hoạt, `TestTransaction.start()` không thể tự tạo một ngữ cảnh kiểm thử transaction đầy đủ.

Nếu transaction mới vẫn active khi method kết thúc, Spring TestContext sẽ kết thúc nó theo cơ chế quản lý test transaction. Để thể hiện rõ mục tiêu và tránh phụ thuộc vào cờ mặc định, hãy đánh dấu commit hoặc rollback một cách tường minh trước khi kết thúc thủ công.



## 9. Ví dụ hoàn chỉnh: commit rồi mở transaction mới để xác nhận dữ liệu

Đây là tình huống tiêu biểu cho `TestTransaction`. Test tạo order trong transaction đầu tiên, commit, rồi bắt đầu transaction thứ hai để đọc lại dữ liệu đã commit.

~~~java
@SpringBootTest
@Transactional
class OrderCommitIntegrationTest {

    @Autowired
    OrderRepository orderRepository;

    @Test
    void commitsOrderAndReadsItInANewTransaction() {
        Order order = new Order("ORD-2001");

        Order saved = orderRepository.saveAndFlush(order);
        Long orderId = saved.getId();

        assertTrue(TestTransaction.isActive());

        TestTransaction.flagForCommit();
        TestTransaction.end();

        assertFalse(TestTransaction.isActive());

        TestTransaction.start();

        try {
            Order reloaded = orderRepository.findById(orderId)
                .orElseThrow();

            assertEquals("ORD-2001", reloaded.getNumber());
        } finally {
            TestTransaction.flagForRollback();
            TestTransaction.end();
        }
    }
}
~~~

Ví dụ sử dụng Spring Data JPA để minh họa. Tên thuộc tính và constructor của `Order` cần phù hợp với domain model của dự án.

Điểm quan trọng:

- `saveAndFlush` đẩy thay đổi xuống database trong transaction đầu tiên; nó chưa tự commit transaction.
- `flagForCommit` đánh dấu transaction đầu tiên sẽ commit.
- `end` thực hiện commit và kết thúc transaction đó.
- `start` bắt đầu transaction mới.
- `findById` đọc lại dữ liệu từ transaction mới, giúp xác nhận dữ liệu đã được commit.
- Khối `finally` đánh dấu rollback và kết thúc transaction thứ hai để không giữ lại trạng thái kiểm thử ngoài ý muốn.

Nếu assertion trong transaction thứ hai thất bại, khối `finally` vẫn cố gắng kết thúc transaction đang active bằng rollback. Với test thực tế, cần bảo đảm phần cleanup chỉ gọi `end()` khi transaction mới đã được bắt đầu và vẫn còn active.

Transaction đầu tiên đã commit nên rollback transaction thứ hai không thể hoàn tác order đã lưu. Đây là lý do test commit cần có dữ liệu riêng hoặc cleanup rõ ràng sau đó.

## 10. Kết hợp TestTransaction với @Commit và @Rollback

Spring TestContext cung cấp annotation để thiết lập quyết định mặc định khi test transaction kết thúc:

- `@Rollback` mặc định đặt quyết định rollback.
- `@Rollback(false)` đặt quyết định commit.
- `@Commit` là cách diễn đạt rõ ràng cho việc commit transaction của test.

Ví dụ:

~~~java
@Test
@Transactional
@Commit
void commitsWhenTheTestFinishes() {
    orderRepository.save(new Order("ORD-3001"));
}
~~~

Test này để Spring kết thúc transaction sau method và commit theo cấu hình annotation.

Có thể dùng `TestTransaction` để thay đổi quyết định trong lúc chạy:

~~~java
@Test
@Transactional
@Commit
void overridesCommitAndRollsBackExplicitly() {
    orderRepository.save(new Order("ORD-3002"));

    TestTransaction.flagForRollback();
    TestTransaction.end();
}
~~~

Ở đây, test đánh dấu rollback trước khi kết thúc transaction. Quyết định được đặt trực tiếp cho transaction hiện tại.

Ngược lại, test có mặc định rollback vẫn có thể yêu cầu commit:

~~~java
@Test
@Transactional
void commitsOnlyAfterExplicitRequest() {
    orderRepository.save(new Order("ORD-3003"));

    TestTransaction.flagForCommit();
    TestTransaction.end();
}
~~~

Điểm cần nhớ là annotation thiết lập chính sách mặc định của test transaction; các phương thức flag của `TestTransaction` cho phép test điều chỉnh quyết định của transaction hiện tại trước khi gọi `end()`.

## 11. Bắt đầu nhiều transaction trong cùng một test method

Một test có thể kết thúc transaction này rồi bắt đầu transaction khác nhiều lần, miễn là mỗi transaction được kết thúc trước khi transaction kế tiếp bắt đầu.

Ví dụ:

~~~java
@Test
@Transactional
void runsTwoSeparateTestManagedTransactions() {
    orderRepository.save(new Order("ORD-4001"));

    TestTransaction.flagForCommit();
    TestTransaction.end();

    TestTransaction.start();

    try {
        assertTrue(orderRepository.existsByNumber("ORD-4001"));

        orderRepository.save(new Order("ORD-4002"));

        TestTransaction.flagForRollback();
        TestTransaction.end();
    } finally {
        if (TestTransaction.isActive()) {
            TestTransaction.flagForRollback();
            TestTransaction.end();
        }
    }
}
~~~

Ví dụ minh họa hai giai đoạn:

- Transaction đầu tiên commit order thứ nhất.
- Transaction thứ hai đọc order đã commit và tạo order thứ hai.
- Transaction thứ hai rollback nên order thứ hai không được giữ lại.

Trong test production, hãy điều chỉnh repository method cho đúng API thực tế. Mẫu cleanup kiểm tra `isActive()` giúp tránh bỏ quên transaction thứ hai nếu assertion hoặc thao tác trong test ném exception trước khi gọi `end()`.

Không cần tạo nhiều transaction nếu test chỉ xác nhận một hành vi đơn giản. Mỗi lần commit thật đều làm dữ liệu tồn tại ngoài transaction hiện tại và tăng yêu cầu cleanup.

## 12. TestTransaction và @BeforeTransaction, @AfterTransaction

Spring TestContext có hai callback hữu ích khi cần chuẩn bị hoặc xác minh trạng thái bên ngoài test-managed transaction:

- `@BeforeTransaction` chạy trước khi test-managed transaction bắt đầu.
- `@AfterTransaction` chạy sau khi test-managed transaction kết thúc.

Ví dụ:

~~~java
@SpringBootTest
@Transactional
class TransactionBoundaryTest {

    @Autowired
    OrderRepository orderRepository;

    @BeforeTransaction
    void verifyDatabaseBeforeTransaction() {
        // Chạy trước test-managed transaction.
    }

    @Test
    void createsAnOrder() {
        orderRepository.save(new Order("ORD-5001"));
    }

    @AfterTransaction
    void verifyDatabaseAfterTransaction() {
        // Chạy sau khi test-managed transaction đã kết thúc.
    }
}
~~~

Các callback này hữu ích khi muốn kiểm tra dữ liệu trước hoặc sau transaction tự động của test. Chúng không phải callback được gọi mỗi lần test gọi `TestTransaction.end()` hoặc `start()` trong thân method. Chúng thuộc lifecycle transaction do Spring TestContext quản lý quanh test method.

Nếu test kết thúc transaction thủ công giữa method rồi bắt đầu transaction mới, hãy thực hiện assertion tương ứng ngay tại vị trí đó. Đừng dựa vào `@AfterTransaction` để chạy sau từng lần gọi `end()`.

## 13. Điều kiện để TestTransaction hoạt động

`TestTransaction` cần Spring TestContext transaction support. Một số điều kiện quan trọng:

- Test phải được tích hợp với Spring TestContext, ví dụ bằng `@SpringBootTest` hoặc `@SpringJUnitConfig`.
- `TransactionalTestExecutionListener` phải được đăng ký. Listener này thường có trong cấu hình listener mặc định của Spring TestContext.
- Test method hoặc class phải được cấu hình `@Transactional` để có test-managed transaction.
- Spring phải tìm được transaction manager phù hợp, thường là bean triển khai `PlatformTransactionManager`.
- Thao tác dữ liệu phải tham gia đúng transaction manager nếu muốn commit/rollback ảnh hưởng tới chúng.

Nếu ứng dụng có nhiều transaction manager, cần xác định rõ transaction manager được dùng cho test bằng cấu hình `@Transactional` phù hợp, chẳng hạn thuộc tính `transactionManager` hoặc qualifier theo phiên bản Spring.

Nếu test không chạy trong transaction, `isActive()` sẽ không báo một transaction test-managed đang hoạt động. Các thao tác như flag hoặc end không thể điều khiển một transaction không tồn tại.

## 14. TestTransaction chỉ quản lý test-managed transaction

Không nhầm `TestTransaction` với transaction được mở độc lập trong code ứng dụng.

Ví dụ service dùng `TransactionTemplate`:

~~~java
@Service
public class ImportService {

    private final TransactionTemplate transactionTemplate;

    public ImportService(TransactionTemplate transactionTemplate) {
        this.transactionTemplate = transactionTemplate;
    }

    public void importBatch() {
        transactionTemplate.executeWithoutResult(status -> {
            // Ghi dữ liệu trong transaction do template quản lý.
        });
    }
}
~~~

`TestTransaction.end()` kết thúc test-managed transaction hiện tại. Nếu code ứng dụng mở một transaction độc lập bằng propagation hoặc transaction manager riêng, kết quả của nó tuân theo transaction boundary của ứng dụng.

Đặc biệt, transaction với propagation `REQUIRES_NEW` có thể commit độc lập với transaction ngoài. Rollback test transaction không tự động hoàn tác một transaction độc lập đã commit.

Nếu cần kiểm tra hành vi transaction của service, hãy gọi service qua Spring proxy để transaction advice hoạt động. Việc gọi trực tiếp target hoặc tạo object bằng `new` có thể bỏ qua proxy và làm test không kiểm tra đúng transaction boundary của production.



## 15. Thread-bound transaction và HTTP request

Test-managed transaction thường gắn với thread chạy test. Vì vậy, nó không tự động bao trùm công việc chạy trên thread khác.

Một ví dụ quan trọng là:

~~~java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@Transactional
class OrderHttpIntegrationTest {

    @Autowired
    TestRestTemplate restTemplate;

    @Test
    void postsOrder() {
        // Request được xử lý bởi embedded server trên thread riêng.
    }
}
~~~

Test method chạy trên thread của JUnit và có thể nằm trong test-managed transaction. Nhưng HTTP request được xử lý trên thread của server, với transaction riêng do service hoặc repository quản lý. Transaction của test method không tự động rollback các thao tác ghi được thực hiện trong request.

Nếu endpoint tạo dữ liệu, hãy dọn dữ liệu bằng repository hoặc API cleanup sau request, dùng database/schema/container riêng, hoặc áp dụng chiến lược kiểm thử phù hợp.

Tương tự, các timeout kiểu chạy test body trên thread khác có thể khiến code trong callback không tham gia test-managed transaction. Hãy tránh giả định transaction tự truyền qua thread.

## 16. Commit thật và trách nhiệm dọn dữ liệu

Khi gọi `flagForCommit()` rồi `end()`, dữ liệu đã commit sẽ tồn tại theo chính sách của database. Rollback transaction mới không xóa dữ liệu đã commit trước đó.

Có thể chọn một trong các chiến lược:

- Dùng database riêng cho test và reset schema hoặc dữ liệu sau suite.
- Tạo dữ liệu với ID hoặc mã duy nhất để cleanup chính xác.
- Xóa bản ghi đã commit trong một transaction cleanup.
- Dùng database container riêng cho từng suite hoặc test class nếu thời gian và hạ tầng cho phép.
- Dùng migration/fixture để thiết lập trạng thái ban đầu rõ ràng.

Ví dụ cleanup có thể dùng repository:

~~~java
try {
    // Thực hiện test và commit dữ liệu cần kiểm tra.
} finally {
    orderRepository.deleteByNumber("ORD-2001");
}
~~~

Nếu cleanup chạy trong một transaction mới, hãy xác nhận transaction đó được commit theo cách phù hợp. Nếu cleanup chỉ chạy trong test-managed transaction mặc định rollback, thao tác xóa cũng có thể bị rollback và dữ liệu đã commit vẫn còn.

Một cách tổ chức rõ hơn là dùng helper cleanup riêng với transaction được quản lý tường minh, hoặc reset database sau test class/suite.

Không dùng mã định danh cố định nếu test có thể chạy song song trên cùng database. Hãy tạo mã duy nhất hoặc cô lập dữ liệu để tránh test này xóa dữ liệu của test khác.

## 17. Những lỗi thường gặp

- **Gọi flagForCommit nhưng quên end:** transaction vẫn đang hoạt động; cờ commit chưa làm dữ liệu được lưu ngay.
- **Gọi end khi không có transaction active:** không có test-managed transaction để kết thúc; kiểm tra cấu hình và trạng thái trước khi gọi.
- **Gọi start khi transaction cũ vẫn active:** phải kết thúc transaction hiện tại trước khi bắt đầu transaction mới.
- **Cho rằng start tạo transaction lồng nhau:** start mở một test-managed transaction mới sau khi transaction trước đã kết thúc.
- **Cho rằng rollback transaction mới xóa dữ liệu đã commit:** commit trước đó đã được database xác nhận và không thể bị rollback ngược lại.
- **Dùng TestTransaction trong test không có @Transactional:** không có test-managed transaction được thiết lập để điều khiển.
- **Nhầm flush với commit:** flush gửi thay đổi tới database trong transaction; commit mới kết thúc transaction và xác nhận thay đổi.
- **Dùng TestTransaction để điều khiển mọi transaction của ứng dụng:** API này chỉ quản lý test-managed transaction.
- **Bỏ qua transaction manager đang được chọn:** nhiều transaction manager có thể khiến test dùng nhầm boundary.
- **Cho rằng HTTP request dùng transaction của test method:** request trên server thường chạy ở thread khác và có transaction riêng.
- **Quên cleanup sau commit:** dữ liệu có thể ảnh hưởng tới test chạy sau hoặc lần chạy suite tiếp theo.
- **Gọi end nhiều lần trong cleanup mà không kiểm tra active:** có thể phát sinh lỗi nếu transaction đã được kết thúc trước đó.

## 18. Quy trình dùng TestTransaction trong test

Khi cần kết thúc, bắt đầu hoặc commit transaction giữa test method, hãy làm theo trình tự:

1. Tích hợp test với Spring TestContext và cấu hình `@Transactional`.
2. Xác nhận transaction manager phù hợp đã có trong context.
3. Kiểm tra `TestTransaction.isActive()` trước khi điều khiển transaction.
4. Tạo hoặc cập nhật dữ liệu trong transaction hiện tại.
5. Chọn `flagForCommit()` hoặc `flagForRollback()` theo mục tiêu.
6. Gọi `end()` để thực sự kết thúc transaction.
7. Kiểm tra transaction đã kết thúc bằng `isActive()`.
8. Nếu cần, gọi `start()` để mở test-managed transaction mới.
9. Thực hiện assertion trong transaction mới và quyết định rõ cách kết thúc nó.
10. Nếu đã commit dữ liệu, chuẩn bị cleanup bền vững và độc lập với thứ tự test.
11. Nếu thao tác chạy trên thread khác hoặc qua HTTP server, xác định transaction boundary riêng của nó.

## Kết luận

`TestTransaction` cho phép test điều khiển test-managed transaction trong lúc method đang chạy. `flagForCommit` và `flagForRollback` đặt quyết định kết thúc; `end` thực hiện commit hoặc rollback; `start` mở transaction kiểm thử mới; `isActive` và `isFlaggedForRollback` giúp quan sát trạng thái hiện tại.

Mẫu thường dùng là ghi dữ liệu trong transaction đầu, đánh dấu commit, gọi `end`, bắt đầu transaction mới bằng `start` rồi đọc lại dữ liệu đã commit. Hãy kết thúc transaction mới một cách tường minh và dọn dữ liệu đã commit để các test vẫn độc lập. Nhớ rằng TestTransaction chỉ điều khiển transaction do Spring TestContext quản lý; transaction độc lập, HTTP request ở thread khác và tài nguyên ngoài database cần được xử lý theo boundary riêng.

