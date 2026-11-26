# Kiểm thử commit, rollback, ghi cạnh tranh và tính nhất quán

Một ca sử dụng có thể chạy đúng khi kiểm thử từng phương thức riêng lẻ nhưng vẫn làm hỏng dữ liệu khi nhiều transaction cùng cập nhật hoặc khi một bước giữa chừng thất bại. Ví dụ, chuyển tiền cần trừ số dư tài khoản nguồn và cộng vào tài khoản đích trong cùng một transaction. Nếu chỉ một thay đổi được lưu, dữ liệu sẽ mất cân bằng. Nếu hai request cùng đọc số dư cũ rồi ghi, một cập nhật có thể ghi đè cập nhật còn lại.

Vì vậy, kiểm thử kiến trúc phân tầng cần đi xa hơn việc xác nhận service đã gọi repository. Cần kiểm tra ranh giới transaction thật sự, trạng thái sau commit và rollback, hành vi khi có ghi cạnh tranh, cùng các bất biến dữ liệu mà nghiệp vụ phải giữ. Bài học này tập trung vào những kiểm thử đó trong ứng dụng Java/Spring dùng JPA và cơ sở dữ liệu quan hệ.

Trong module SOFTWARE_DESIGN_ARCHITECTURE_ARCHITECTURAL_PATTERN_LAYERED, mục tiêu là học tổ chức phần mềm theo kiến trúc phân tầng. Tầng ứng dụng thường sở hữu ca sử dụng và ranh giới transaction; tầng truy cập dữ liệu hiện thực thao tác lưu trữ; database thực thi tính nguyên tử, constraint và khóa. Kiểm thử cần xác nhận các tầng phối hợp đúng ở ranh giới thực tế, không chỉ kiểm tra từng lớp cô lập.

## 1. Kiểm thử điều gì ở transaction?

Transaction gom nhiều thao tác dữ liệu thành một đơn vị công việc. Với một transaction cơ sở dữ liệu quan hệ, hai kết quả quan trọng là:

- **Commit:** các thay đổi được xác nhận và trở nên nhìn thấy theo quy tắc cô lập của database.
- **Rollback:** các thay đổi trong transaction bị hủy khi transaction thất bại hoặc được đánh dấu rollback-only.

Một transaction thường được mô tả bằng các thuộc tính ACID:

| Thuộc tính | Ý nghĩa | Điều cần kiểm thử |
|---|---|---|
| Atomicity | Các thay đổi trong transaction cùng thành công hoặc cùng bị hủy | Không có trạng thái cập nhật dở dang sau lỗi |
| Consistency | Transaction đưa dữ liệu từ trạng thái hợp lệ sang trạng thái hợp lệ | Các bất biến nghiệp vụ và constraint vẫn đúng |
| Isolation | Các transaction đồng thời không quan sát hoặc ghi đè lẫn nhau ngoài mức được phép | Hành vi đọc/ghi cạnh tranh phù hợp với isolation và locking đã chọn |
| Durability | Sau commit, thay đổi được database xác nhận bền vững theo cam kết của hệ thống | Kết quả vẫn đọc được sau khi transaction kết thúc; độ bền vật lý sâu hơn cần kiểm thử vận hành riêng |

Kiểm thử transaction không chỉ xác nhận phương thức được gắn @Transactional. Annotation có thể không được áp dụng nếu lời gọi không đi qua Spring proxy, transaction có thể bị đánh dấu rollback-only, và lỗi có thể chỉ xuất hiện lúc flush hoặc commit. Bài kiểm thử cần quan sát trạng thái dữ liệu sau khi ranh giới transaction thực sự kết thúc.

## 2. Chọn đúng tầng kiểm thử

Mỗi loại kiểm thử nên xác nhận một trách nhiệm cụ thể:

| Tầng/phạm vi | Công cụ hoặc cách làm | Câu hỏi cần trả lời |
|---|---|---|
| Domain | Unit test thuần Java | Quy tắc số dư, số lượng, trạng thái và bất biến có đúng không? |
| Application | Unit test với fake/mock port | Ca sử dụng có điều phối đúng và yêu cầu các thao tác cần thiết không? |
| Data access | Repository integration test | Mapping, câu truy vấn, constraint và locking có đúng với database không? |
| Transaction boundary | Spring integration test với transaction manager thật | Commit/rollback có xảy ra đúng phạm vi và đúng thời điểm không? |
| API | MVC/integration test | Lỗi transaction và conflict được chuyển thành phản hồi phù hợp không? |

Không cần dùng database cho mọi unit test. Một unit test của domain nên nhanh và tập trung vào bất biến. Một unit test của application có thể dùng repository giả lập để xác nhận thứ tự điều phối. Nhưng mock repository không thể chứng minh transaction commit, rollback, unique constraint hoặc lock hoạt động đúng. Những hành vi đó cần integration test với persistence provider và database thực tế hoặc tương thích.

## 3. Kiểm thử commit: xác nhận dữ liệu sau khi transaction kết thúc

Giả sử TransferService chuyển một khoản tiền giữa hai tài khoản. Cả thao tác trừ và cộng phải nằm trong cùng một transaction:

~~~java
@Service
public class TransferService {
    private final AccountRepository accounts;

    public TransferService(AccountRepository accounts) {
        this.accounts = accounts;
    }

    @Transactional
    public void transfer(UUID sourceId, UUID targetId, BigDecimal amount) {
        if (amount == null || amount.signum() <= 0) {
            throw new IllegalArgumentException("Amount must be positive");
        }

        Account source = accounts.findById(sourceId)
            .orElseThrow(() -> new AccountNotFoundException(sourceId));
        Account target = accounts.findById(targetId)
            .orElseThrow(() -> new AccountNotFoundException(targetId));

        source.debit(amount);
        target.credit(amount);
    }
}
~~~

Giả sử repository trả về entity đang được quản lý trong persistence context. JPA dirty checking sẽ phát hiện thay đổi và ghi chúng khi flush. Kiểm thử commit nên gọi service qua Spring bean đã được proxy, để transaction interceptor thật sự bao quanh phương thức.

~~~java
@SpringBootTest
class TransferTransactionIT {
    @Autowired TransferService transfers;
    @Autowired AccountRepository accounts;
    @Autowired TransactionTemplate transactionTemplate;

    @Test
    void commitsBothSidesOfTransfer() {
        UUID sourceId = createAccount(new BigDecimal("100.00"));
        UUID targetId = createAccount(new BigDecimal("20.00"));

        transfers.transfer(
            sourceId, targetId, new BigDecimal("30.00")
        );

        AccountBalances balances = transactionTemplate.execute(status -> {
            Account source = accounts.findById(sourceId).orElseThrow();
            Account target = accounts.findById(targetId).orElseThrow();
            return new AccountBalances(
                source.getBalance(), target.getBalance()
            );
        });

        assertEquals(new BigDecimal("70.00"), balances.source());
        assertEquals(new BigDecimal("50.00"), balances.target());
    }
}
~~~

Đây là ví dụ cấu trúc; createAccount cần tạo dữ liệu trong transaction riêng và AccountBalances là kiểu kết quả kiểm thử. TransactionTemplate ở phần đọc tạo một transaction/persistence context mới sau khi lời gọi service đã trả về. Việc đọc lại từ ngữ cảnh mới giúp xác nhận kết quả đã được commit, thay vì chỉ nhìn thấy thay đổi còn nằm trong bộ nhớ của persistence context ban đầu.

Một kiểm thử có thể chỉ assert rằng service không ném exception, nhưng như vậy chưa đủ. Hãy đọc lại các bản ghi liên quan và xác nhận cả hai phía của giao dịch đều thay đổi đúng. Với tiền tệ, nên dùng kiểu decimal phù hợp và scale rõ ràng, tránh so sánh bằng số thực nhị phân.

## 4. Kiểm thử rollback: lỗi giữa chừng không để lại thay đổi một phần

Nếu tài khoản nguồn không đủ tiền, thao tác chuyển tiền phải thất bại và số dư của cả hai tài khoản phải giữ nguyên. Kiểm thử cần kích hoạt lỗi sau khi transaction đã bắt đầu và xác nhận trạng thái từ transaction mới.

~~~java
@Test
void rollsBackWhenBusinessOperationFails() {
    UUID sourceId = createAccount(new BigDecimal("10.00"));
    UUID targetId = createAccount(new BigDecimal("20.00"));

    assertThrows(
        InsufficientFundsException.class,
        () -> transfers.transfer(
            sourceId, targetId, new BigDecimal("30.00")
        )
    );

    AccountBalances balances = transactionTemplate.execute(status -> {
        Account source = accounts.findById(sourceId).orElseThrow();
        Account target = accounts.findById(targetId).orElseThrow();
        return new AccountBalances(
            source.getBalance(), target.getBalance()
        );
    });

    assertEquals(new BigDecimal("10.00"), balances.source());
    assertEquals(new BigDecimal("20.00"), balances.target());
}
~~~

Kiểm thử này xác nhận tầng ứng dụng không để lại một phần thay đổi khi ca sử dụng bị từ chối. Có thể bổ sung một lỗi giả lập phát sinh sau khi đã thay đổi tài khoản nguồn nhưng trước khi hoàn tất tài khoản đích, để xác nhận rollback vẫn hủy toàn bộ cập nhật trong cùng transaction.

### 4.1. Quy tắc rollback của Spring

Theo mặc định, Spring đánh dấu rollback khi phương thức transactional kết thúc bằng unchecked exception (RuntimeException hoặc Error). Checked exception không tự động gây rollback theo mặc định. Nếu ca sử dụng cần rollback cho checked exception, có thể khai báo rõ:

~~~java
@Transactional(rollbackFor = ExternalTransferException.class)
public void transfer(...) throws ExternalTransferException {
    // Các thay đổi cần được rollback nếu lỗi này xảy ra.
}
~~~

Kiểm thử nên bao gồm loại exception thực tế mà ứng dụng dùng, tránh giả định mọi exception đều rollback giống nhau. Cũng cần kiểm tra trường hợp một thành phần bắt exception rồi tiếp tục; transaction có thể đã bị đánh dấu rollback-only và cuối cùng phát sinh UnexpectedRollbackException khi commit.

### 4.2. Không để transaction của test che khuất kết quả

Các test slice như @DataJpaTest thường tự chạy mỗi test trong một transaction và rollback khi test kết thúc. Điều đó tiện cho việc cô lập dữ liệu, nhưng có thể che khuất việc transaction của service có commit thật hay không. Nếu test method cũng có @Transactional, lời gọi service có thể tham gia transaction bên ngoài của test theo propagation mặc định.

Khi kiểm thử commit/rollback của service:

- Không bọc toàn bộ test trong một transaction ngoài nếu mục tiêu là kiểm tra commit của service.
- Gọi service bean từ Spring context để lời gọi đi qua proxy.
- Đọc lại dữ liệu trong transaction hoặc persistence context mới.
- Nếu dùng @DataJpaTest, cân nhắc tách test transaction, dùng transaction programmatic phù hợp hoặc thiết kế test integration không có transaction bao ngoài.

Không nên gọi trực tiếp một đối tượng service được tạo bằng new rồi mong @Transactional hoạt động. Annotation chỉ có hiệu lực khi lời gọi đi qua cơ chế transaction của Spring hoặc một cơ chế tương đương đã được cấu hình.

## 5. Kiểm thử ghi cạnh tranh bằng hai transaction độc lập

Một test chạy tuần tự không thể chứng minh hệ thống xử lý đúng khi hai request cập nhật cùng dữ liệu. Cần tạo ít nhất hai transaction độc lập, mỗi transaction có persistence context riêng và được chạy đồng thời có kiểm soát.

Với entity có @Version, kịch bản optimistic locking nên đảm bảo:

1. T1 đọc entity với version ban đầu.
2. T2 cũng đọc cùng entity/version trước khi T1 ghi.
3. T1 cập nhật và commit thành công.
4. T2 cố cập nhật theo version cũ và nhận optimistic locking conflict.
5. Đọc lại dữ liệu cho thấy thay đổi của T1 vẫn được giữ và không bị ghi đè.

Ví dụ dưới đây minh họa cách đồng bộ hai thread. Phần helper executeInNewTransaction đại diện cho việc chạy mỗi tác vụ trong một transaction mới thông qua TransactionTemplate hoặc một bean transactional riêng:

~~~java
CountDownLatch bothRead = new CountDownLatch(2);
CountDownLatch allowWrite = new CountDownLatch(1);

Callable<Void> updateA = () -> executeInNewTransaction(() -> {
    Product product = products.findById(productId).orElseThrow();
    bothRead.countDown();
    allowWrite.await();
    product.reduceStock(2);
    return null;
});

Callable<Void> updateB = () -> executeInNewTransaction(() -> {
    Product product = products.findById(productId).orElseThrow();
    bothRead.countDown();
    allowWrite.await();
    product.reduceStock(3);
    return null;
});

Future<?> first = executor.submit(updateA);
Future<?> second = executor.submit(updateB);

assertTrue(bothRead.await(5, TimeUnit.SECONDS));
allowWrite.countDown();

// Thu thập kết quả của cả hai Future và xác nhận một commit,
// một optimistic locking conflict, rồi đọc lại trạng thái.
~~~

Đây là phác thảo kiểm thử, cần bổ sung executor, cleanup, timeout và cách phân loại exception theo dự án. Điểm quan trọng là barrier buộc cả hai transaction đọc cùng trạng thái trước khi được phép ghi. Nếu không đồng bộ, test có thể chạy tuần tự và không tái hiện xung đột.

Khi dùng hai thread, cần bảo đảm connection pool có đủ kết nối cho các transaction đồng thời. Mỗi thread không được dùng chung EntityManager hoặc managed entity của thread khác. Thu thập kết quả Future để không bỏ sót exception phát sinh trong thread nền; luôn giải phóng latch và shutdown executor trong finally.

## 6. Kiểm thử pessimistic locking, timeout và deadlock

Với pessimistic locking, kiểm thử nên xác nhận transaction thứ hai không thể lấy khóa xung đột trong khi transaction thứ nhất còn giữ khóa:

1. T1 mở transaction và lấy PESSIMISTIC_WRITE trên một hàng.
2. T1 giữ transaction mở sau khi đã lấy khóa.
3. T2 mở transaction độc lập và yêu cầu PESSIMISTIC_WRITE trên cùng hàng.
4. T2 phải chờ, hoặc nhận lỗi lock timeout theo cấu hình.
5. Khi T1 commit/rollback, T2 có thể tiếp tục nếu chưa timeout.

Để test ổn định, dùng latch báo hiệu khi T1 đã lấy khóa và khi T2 bắt đầu yêu cầu khóa. Không dựa duy nhất vào Thread.sleep để suy đoán thứ tự. Có thể dùng timeout của test để phát hiện T2 đang chờ, nhưng cần phân biệt timeout của test runner với lock timeout từ database.

Deadlock test có thể tạo hai transaction khóa hai hàng theo thứ tự ngược nhau. Database thường chọn một transaction làm nạn nhân và rollback nó. Đây là kiểm thử nhạy với database, isolation, timeout và lịch thực thi; nên chạy trên hệ quản trị tương thích môi trường triển khai, tránh giả định H2 mô phỏng chính xác production.

Các test này cần giới hạn thời gian chờ và luôn giải phóng transaction/lock trong finally. Một test bị treo do không đóng transaction có thể làm cạn connection pool và khiến các test sau thất bại dây chuyền.

## 7. Kiểm thử tính nhất quán: xác nhận bất biến, không chỉ xác nhận câu lệnh

Tính nhất quán trong kiểm thử nên được diễn đạt thành bất biến có thể kiểm tra. Ví dụ với chuyển tiền:

~~~text
balance(source) >= 0
balance(target) >= 0
totalBalanceAfter = totalBalanceBefore
Nếu transfer thất bại: cả hai số dư không đổi
~~~

Với tồn kho:

~~~text
availableQuantity >= 0
Tổng số lượng đã giữ + đã xuất không vượt lượng được phép
Một đơn hàng không bị ghi hai lần cho cùng idempotency key
~~~

Với đặt chỗ có giới hạn:

~~~text
confirmedReservations <= capacity
Mỗi yêu cầu đặt chỗ chỉ tạo tối đa một reservation đang hiệu lực
~~~

Những bất biến này có thể liên quan nhiều hàng hoặc nhiều bảng. Chỉ kiểm tra từng entity riêng lẻ có thể không đủ. Hãy tạo test chạy các ca sử dụng cạnh tranh và kiểm tra trạng thái tổng thể sau khi tất cả transaction kết thúc.

Database constraint như CHECK, UNIQUE và FOREIGN KEY là lớp bảo vệ quan trọng. Integration test nên xác nhận constraint thật sự được áp dụng. Tuy nhiên, không nên phụ thuộc hoàn toàn vào constraint để thay thế quy tắc nghiệp vụ: tầng ứng dụng vẫn cần phản hồi dễ hiểu và database constraint bảo vệ tính toàn vẹn ở lớp lưu trữ.

## 8. Kiểm thử isolation và các hiện tượng đọc/ghi

Isolation level quyết định transaction có thể quan sát thay đổi của transaction khác đến mức nào. Những hiện tượng thường được nhắc đến:

- **Dirty read:** đọc dữ liệu mà transaction khác chưa commit.
- **Non-repeatable read:** cùng một truy vấn đọc một hàng hai lần trong một transaction nhưng nhận giá trị khác vì transaction khác đã commit cập nhật.
- **Phantom read:** truy vấn theo điều kiện trả về tập hàng khác ở lần đọc sau vì transaction khác thêm hoặc xóa hàng phù hợp.
- **Lost update:** một thay đổi ghi đè thay đổi khác do cả hai transaction cùng dựa trên trạng thái cũ.

Không nên suy ra chính xác hành vi từ tên isolation level mà không biết database. Cách hiện thực READ COMMITTED, REPEATABLE READ, SERIALIZABLE, predicate lock và snapshot có thể khác nhau giữa hệ quản trị. Test cần chạy với database đích hoặc database có semantics tương thích, và cần đồng bộ các transaction để tái hiện đúng hiện tượng.

Ví dụ, nếu ca sử dụng cần bảo đảm không có hai reservation vượt quá capacity, một test chỉ kiểm tra từng transaction riêng lẻ sẽ không đủ. Cần khởi chạy nhiều transaction cùng đọc số chỗ còn lại, cùng thử đặt, rồi xác nhận tổng reservation sau cùng không vượt giới hạn. Tùy mô hình, giải pháp có thể là optimistic version trên hàng tổng hợp, pessimistic lock, cập nhật nguyên tử có điều kiện, unique constraint hoặc isolation mạnh hơn.

## 9. Transaction và side effect ngoài database

Một database transaction không tự rollback được email đã gửi, HTTP request tới dịch vụ khác hoặc message đã được publish ra broker. Nếu service làm theo thứ tự:

1. Ghi đơn hàng.
2. Gửi email xác nhận.
3. Transaction database bị rollback.

Người dùng có thể nhận email cho một đơn hàng không tồn tại. Kiểm thử rollback chỉ nhìn database sẽ không phát hiện side effect này.

Với message hoặc event cần nhất quán cùng dữ liệu, một giải pháp phổ biến là transactional outbox: trong cùng transaction, ghi cả dữ liệu nghiệp vụ và một bản ghi outbox; một worker riêng đọc outbox rồi publish message. Test cần xác nhận:

- Khi transaction nghiệp vụ rollback, bản ghi outbox cũng không tồn tại.
- Khi transaction commit, dữ liệu nghiệp vụ và outbox cùng được lưu.
- Publisher có thể gửi lại khi lỗi, nên consumer cần xử lý idempotent hoặc khử trùng lặp.
- Việc publish thành công không bị giả định là xảy ra nguyên tử cùng commit database.

Với quy trình nhiều dịch vụ, có thể cần saga và hành động bù thay vì một transaction ACID xuyên suốt. Kiểm thử phải xác nhận trạng thái cuối và hành vi bù khi một bước thất bại, chứ không kỳ vọng rollback database cục bộ có thể hoàn tác mọi dịch vụ bên ngoài.

## 10. Chọn database kiểm thử phù hợp

Database nhúng như H2 có thể giúp test nhanh mapping và truy vấn cơ bản. Nhưng hành vi khóa, isolation, SQL dialect, constraint trì hoãn, kiểu dữ liệu và deadlock có thể khác database production.

Với các kiểm thử commit/rollback đơn giản, database nhúng có thể đủ nếu semantics liên quan tương thích. Với ghi cạnh tranh, pessimistic lock, deadlock, isolation hoặc câu SQL đặc thù, nên dùng database thật qua Testcontainers hoặc môi trường tích hợp tương đương. Cấu hình phiên bản và chế độ database càng gần production càng tăng độ tin cậy của kết quả.

Không cần chạy mọi unit test trên container. Hãy phân tầng bộ test:

- Unit test domain/application chạy nhanh, không cần database.
- Repository và transaction integration test dùng database phù hợp.
- Một số end-to-end test xác nhận wiring từ API đến database.
- Kiểm thử tải hoặc chaos ở môi trường phù hợp nếu cần đánh giá hành vi khi tải cao hoặc sự cố hạ tầng.

## 11. Tránh các bẫy trong kiểm thử transaction

- **Test method tự có transaction:** transaction của test có thể bao ngoài transaction của service và rollback cuối test, khiến không kiểm tra được commit thật.
- **Đọc lại trong cùng persistence context:** entity cache có thể trả trạng thái trong bộ nhớ thay vì đọc từ database sau commit. Dùng transaction/context mới hoặc clear persistence context.
- **Dùng mock để chứng minh ACID:** mock repository chỉ chứng minh lời gọi; nó không chứng minh database rollback hoặc khóa.
- **Chỉ test một transaction:** không thể phát hiện lost update hoặc deadlock bằng test tuần tự.
- **Dùng sleep để điều phối:** thứ tự thread không được bảo đảm; dùng latch/barrier và timeout có chủ đích.
- **Không thu thập exception từ Future:** lỗi trong thread nền có thể bị bỏ qua và test báo thành công giả.
- **Chỉ kiểm tra số hàng:** một hàng tồn tại không chứng minh tổng số dư, số lượng hoặc giới hạn nghiệp vụ vẫn đúng.
- **Không dọn dữ liệu và khóa:** test cạnh tranh thất bại giữa chừng có thể để lại thread, transaction hoặc dữ liệu làm hỏng test sau.
- **Giả định database test giống production:** test có thể xanh nhưng hành vi lock/constraint ở production khác biệt.

## 12. Checklist xây dựng bộ kiểm thử

Với mỗi ca sử dụng có ghi dữ liệu, hãy xác định:

1. Ranh giới transaction nằm ở phương thức hoặc thành phần nào?
2. Thành công cần commit những thay đổi nào cùng nhau?
3. Các lỗi nào phải rollback và exception nào cần rollbackFor?
4. Có thể xảy ra ghi cạnh tranh trên một hàng hay nhiều hàng?
5. Cơ chế isolation, version, lock hoặc constraint nào bảo vệ bất biến?
6. Có test với hai transaction độc lập và đồng bộ được thời điểm cạnh tranh không?
7. Kết quả có được đọc lại từ transaction/persistence context mới không?
8. Side effect ngoài database được tổ chức bằng outbox, idempotency hoặc saga như thế nào?
9. Database kiểm thử có đủ tương thích với môi trường triển khai cho hành vi đang xác nhận không?

Một bộ kiểm thử tốt không cố chứng minh toàn bộ database bằng mock hoặc chỉ một test end-to-end. Nó kết hợp unit test cho quy tắc, integration test cho persistence và transaction, cùng test cạnh tranh có kiểm soát cho các bất biến quan trọng. Khi kiểm tra cả commit, rollback, xung đột và trạng thái tổng thể, nhóm phát triển có bằng chứng đáng tin cậy rằng các tầng phối hợp đúng và dữ liệu vẫn nhất quán khi hệ thống gặp lỗi hoặc nhiều request cùng hoạt động.
