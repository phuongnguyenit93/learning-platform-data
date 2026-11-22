# Kiểm chứng hành vi sau commit bằng giao dịch riêng

Khi kiểm thử tầng dữ liệu, việc gọi `save()` thành công chưa đủ để chứng minh dữ liệu đã được lưu bền vững. Một đối tượng có thể vẫn nằm trong persistence context của JPA, câu lệnh SQL có thể chưa được gửi xuống cơ sở dữ liệu, hoặc transaction có thể bị rollback sau khi test kết thúc. Muốn kiểm chứng hành vi sau commit, hãy để transaction ghi hoàn tất, sau đó đọc lại dữ liệu trong một transaction mới.

Kỹ thuật này đặc biệt hữu ích khi kiểm tra repository, service có `@Transactional`, ràng buộc dữ liệu được kiểm tra lúc commit, trigger của cơ sở dữ liệu, hoặc các xử lý chỉ chạy sau khi transaction commit.

## Vì sao phải đọc bằng transaction mới?

JPA quản lý các entity đã tải hoặc đã thay đổi trong persistence context. Nếu test lưu một entity rồi đọc lại ngay trong cùng persistence context, Hibernate có thể trả về đối tượng đang được quản lý mà không cần tải lại trạng thái đã commit từ cơ sở dữ liệu. Kết quả đó chứng minh rằng ứng dụng đang nhìn thấy thay đổi của chính transaction hiện tại, nhưng chưa chứng minh transaction đã commit thành công và một transaction khác có thể nhìn thấy dữ liệu.

Cần phân biệt ba thời điểm:

| Thời điểm | Điều xảy ra | Điều chưa được chứng minh |
|---|---|---|
| `save()` | Entity được đưa vào trạng thái được quản lý hoặc được đánh dấu để lưu | SQL có thể chưa được thực thi; transaction chưa commit |
| `flush()` | Persistence context đồng bộ các thay đổi xuống cơ sở dữ liệu bằng SQL | Transaction vẫn có thể rollback; transaction khác thường chưa nhìn thấy thay đổi |
| `commit()` | Transaction kết thúc thành công và thay đổi được commit theo cơ chế của cơ sở dữ liệu | Cần đọc từ một transaction mới để kiểm tra khả năng quan sát sau commit |

`flush()` không thay thế cho `commit()`. Một lệnh `INSERT` đã chạy vẫn có thể bị rollback. Vì vậy, kiểm tra ngay sau `flush()` trong cùng transaction không phải là kiểm chứng sau commit.

Spring TestContext cũng có một đặc điểm cần lưu ý: test được đánh dấu `@Transactional` thường chạy trong test-managed transaction và mặc định rollback khi test kết thúc. Điều đó giúp test cô lập dữ liệu, nhưng cũng có nghĩa là một lần `save()` trong test không tự động tạo ra dữ liệu đã commit.

## Quy trình kiểm chứng

Một bài test sau commit nên có hai ranh giới transaction độc lập:

1. Transaction ghi tạo hoặc cập nhật dữ liệu. Transaction này phải commit thành công trước khi bước tiếp theo bắt đầu.
2. Transaction xác minh bắt đầu sau khi transaction ghi đã kết thúc. Nó truy vấn lại bằng khóa chính hoặc khóa nghiệp vụ và kiểm tra giá trị được lưu.

Đọc lại trong transaction mới giúp test sử dụng persistence context mới theo vòng đời transaction thông thường của JPA. Nếu mục tiêu là xác minh trực tiếp trạng thái bảng và tránh cả cache cấp hai của ORM, có thể dùng `JdbcTemplate` để truy vấn trong transaction xác minh.

## Cách 1: Dùng `TransactionTemplate`

`TransactionTemplate` cho phép đặt ranh giới transaction ngay trong test. Mỗi lần gọi `execute()` sẽ chạy callback trong transaction do `PlatformTransactionManager` quản lý. Khi callback trả về bình thường, template commit transaction trước khi trả kết quả cho đoạn code gọi nó.

Ví dụ dưới đây dùng Spring Boot, Spring Data JPA và AssertJ. `Order` là entity minh họa có trường `code`; `OrderRepository` là repository kế thừa `JpaRepository<Order, Long>`.

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class OrderCommitIntegrationTest {

    @Autowired
    private PlatformTransactionManager transactionManager;

    @Autowired
    private OrderRepository orderRepository;

    @Test
    void readsOrderInANewTransactionAfterCommit() {
        TransactionTemplate writeTransaction =
                new TransactionTemplate(transactionManager);

        Long orderId = writeTransaction.execute(status -> {
            Order saved = orderRepository.saveAndFlush(
                    new Order("ORD-203")
            );
            return saved.getId();
        });

        assertThat(orderId).isNotNull();

        try {
            // execute() của writeTransaction đã commit trước khi tới đây.
            TransactionTemplate verificationTransaction =
                    new TransactionTemplate(transactionManager);
            verificationTransaction.setReadOnly(true);

            String storedCode = verificationTransaction.execute(status ->
                    orderRepository.findById(orderId)
                            .orElseThrow()
                            .getCode()
            );

            assertThat(storedCode).isEqualTo("ORD-203");
        } finally {
            // Dữ liệu đã commit nên cần dọn dẹp bằng một transaction riêng.
            new TransactionTemplate(transactionManager)
                    .executeWithoutResult(status ->
                            orderRepository.deleteById(orderId)
                    );
        }
    }
}
```

Test này không được đặt `@Transactional` ở class hoặc method. Nếu có một transaction test bên ngoài, propagation mặc định `REQUIRED` của `TransactionTemplate` có thể tham gia transaction đang tồn tại. Khi đó lời gọi ghi chưa tạo ra ranh giới commit như ví dụ yêu cầu.

`saveAndFlush()` trong ví dụ giúp SQL được gửi xuống cơ sở dữ liệu và thường bảo đảm ID đã được tạo trước khi callback trả về. Việc commit vẫn diễn ra sau callback, do `TransactionTemplate` quản lý. Nếu commit thất bại, `execute()` sẽ ném exception và phần xác minh không chạy.

## Cách 2: Dùng `TestTransaction` với `@DataJpaTest`

`@DataJpaTest` thường tự mở một test-managed transaction và rollback transaction đó khi test kết thúc. Khi cần giữ đúng cấu trúc này nhưng vẫn muốn kiểm tra dữ liệu sau commit, Spring Test cung cấp `TestTransaction` để điều khiển transaction của test.

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.test.context.transaction.TestTransaction;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

import static org.assertj.core.api.Assertions.assertThat;

@DataJpaTest
class OrderRepositoryCommitTest {

    @Autowired
    private OrderRepository orderRepository;

    @Autowired
    private PlatformTransactionManager transactionManager;

    @Test
    void readsCommittedOrderAfterEndingTestTransaction() {
        Order saved = orderRepository.saveAndFlush(
                new Order("ORD-203")
        );
        Long orderId = saved.getId();

        // Đánh dấu transaction test hiện tại để commit, rồi kết thúc nó.
        TestTransaction.flagForCommit();
        TestTransaction.end();

        // Transaction xác minh bắt đầu sau khi transaction test đã commit.
        TransactionTemplate verificationTransaction =
                new TransactionTemplate(transactionManager);
        verificationTransaction.setReadOnly(true);

        try {
            String storedCode = verificationTransaction.execute(status ->
                    orderRepository.findById(orderId)
                            .orElseThrow()
                            .getCode()
            );

            assertThat(storedCode).isEqualTo("ORD-203");
        } finally {
            // Transaction test đã commit nên cần xóa dữ liệu đã tạo.
            new TransactionTemplate(transactionManager)
                    .executeWithoutResult(status ->
                            orderRepository.deleteById(orderId)
                    );
        }
    }
}
```

`TestTransaction.flagForCommit()` chỉ đánh dấu quyết định kết thúc transaction; `TestTransaction.end()` mới thực sự kết thúc và commit transaction đó. Sau `end()`, lời gọi `TransactionTemplate` không tham gia transaction test đã kết thúc mà mở transaction xác minh mới.

Vì dữ liệu ghi đã commit, cơ chế rollback mặc định của `@DataJpaTest` không thể tự hoàn tác phần ghi đó. Ví dụ chủ động xóa entity bằng transaction riêng. Trong test suite lớn, hãy bảo đảm bước dọn dữ liệu vẫn chạy khi assertion thất bại, chẳng hạn chuyển việc dọn dẹp vào `finally` hoặc một fixture cleanup phù hợp.

Một lựa chọn khác là đánh dấu test bằng `@Commit` rồi đặt phần đọc xác minh trong phương thức `@AfterTransaction`. Callback `@AfterTransaction` được Spring gọi sau khi test-managed transaction đã kết thúc. Không nên đặt phần xác minh trong thân test method nếu transaction chỉ được commit tự động sau khi method đó trả về.

## Dùng `REQUIRES_NEW` đúng thời điểm

`Propagation.REQUIRES_NEW` buộc Spring mở transaction độc lập, tạm treo transaction hiện tại nếu có. Tuy nhiên, việc dùng `REQUIRES_NEW` tự nó không làm cho dữ liệu chưa commit trở nên nhìn thấy được.

Ví dụ, nếu transaction ghi vẫn đang mở và test gọi một service đọc có `@Transactional(propagation = Propagation.REQUIRES_NEW)`, Spring sẽ tạm treo transaction ghi rồi mở transaction đọc. Transaction đọc không nhìn thấy thay đổi chưa commit của transaction ghi theo quy tắc cô lập thông thường của cơ sở dữ liệu. Sau khi transaction đọc kết thúc, transaction ghi mới tiếp tục.

Vì vậy, thứ tự đúng là:

```text
Gọi service ghi
    |
    v
Transaction ghi commit thành công
    |
    v
Gọi service đọc / mở transaction xác minh
    |
    v
Đọc dữ liệu và assert
```

Nếu không có transaction bên ngoài, propagation mặc định `REQUIRED` đã đủ để `TransactionTemplate` hoặc một phương thức repository mở transaction mới. Chỉ chọn `REQUIRES_NEW` khi cần bảo đảm một ranh giới transaction độc lập trong khi có thể đang tồn tại transaction của caller, và phải chắc chắn dữ liệu cần đọc đã commit trước đó.

## Các lỗi kiểm thử thường gặp

| Cách làm | Vấn đề | Cách xử lý |
|---|---|---|
| Gọi `save()` rồi assert trên chính entity vừa lưu | Có thể chỉ kiểm tra trạng thái object đang được quản lý | Đọc lại bằng ID trong transaction mới |
| Gọi `flush()` rồi cho rằng dữ liệu đã commit | SQL đã chạy nhưng transaction vẫn có thể rollback | Kết thúc transaction ghi thành công trước khi xác minh |
| Đọc lại trong cùng test-managed transaction | Persistence context có thể trả entity từ bộ nhớ; transaction khác chưa thấy dữ liệu | Commit hoặc kết thúc transaction test rồi mở transaction mới |
| Dùng `REQUIRES_NEW` khi transaction ghi còn mở | Transaction đọc độc lập không thấy dữ liệu chưa commit | Để transaction ghi commit xong rồi mới đọc |
| Dùng `@Transactional` trên test và trông chờ dữ liệu tồn tại sau test | Spring TestContext mặc định rollback test-managed transaction | Dùng `TestTransaction`, `@Commit` kết hợp `@AfterTransaction`, hoặc điều khiển transaction tường minh |
| Bỏ qua dữ liệu đã commit trong bước dọn dẹp | Dữ liệu test có thể ảnh hưởng các test chạy sau | Xóa dữ liệu bằng transaction cleanup hoặc dùng cơ sở dữ liệu test được cô lập |

## Khi cần xác minh trực tiếp dữ liệu cơ sở dữ liệu

Một transaction mới thường tạo persistence context mới, nhưng cache cấp hai của JPA/Hibernate vẫn có thể tham gia vào quá trình đọc. Nếu yêu cầu kiểm thử là xác minh giá trị thực tế trong bảng, có thể dùng `JdbcTemplate` trong transaction xác minh. Ví dụ sau giả định `jdbcTemplate` đã được inject và `orderId` là ID của bản ghi vừa commit:

```java
TransactionTemplate verificationTransaction =
        new TransactionTemplate(transactionManager);
verificationTransaction.setReadOnly(true);

String storedCode = verificationTransaction.execute(status ->
        jdbcTemplate.queryForObject(
                "select code from orders where id = ?",
                String.class,
                orderId
        )
);

assertThat(storedCode).isEqualTo("ORD-203");
```

Truy vấn JDBC bỏ qua persistence context và cache entity của JPA. Hãy dùng tên bảng, tên cột và kiểu dữ liệu thực tế của schema dự án. Transaction xác minh vẫn cần bắt đầu sau khi transaction ghi commit.

## Kiểm chứng xử lý chạy sau commit

Với listener dùng `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)`, việc publish event trong transaction chưa chứng minh listener đã chạy. Test cần để transaction phát event commit thành công, sau đó kiểm tra side effect mà listener tạo ra. Nếu side effect được ghi vào cùng cơ sở dữ liệu, hãy đọc nó trong transaction mới theo các cách ở trên.

Nếu listener còn dùng `@Async`, việc commit chỉ kích hoạt xử lý bất đồng bộ; test phải chờ điều kiện hoàn tất bằng cơ chế đồng bộ hoặc chờ có giới hạn thời gian phù hợp. Không nên dùng `Thread.sleep()` cố định vì nó không bảo đảm listener đã hoàn tất và khiến test chậm, thiếu ổn định.

## Tiêu chí hoàn thành bài kiểm thử

- Transaction ghi đã kết thúc bằng commit thành công trước khi bắt đầu xác minh.
- Truy vấn xác minh chạy trong transaction mới và đọc theo ID hoặc khóa nghiệp vụ ổn định.
- Assertion kiểm tra giá trị được tải từ tầng dữ liệu, không chỉ kiểm tra entity đang nằm trong persistence context cũ.
- Test có chiến lược dọn dẹp rõ ràng đối với dữ liệu đã commit.
- Nếu cần chứng minh trạng thái bảng, test dùng truy vấn JDBC hoặc cơ chế đọc phù hợp để tránh kết quả bị cache ORM che khuất.

Khi đáp ứng các điều kiện này, bài test mới kiểm chứng được rằng thay đổi đã vượt qua ranh giới commit và có thể được quan sát từ một transaction độc lập.
