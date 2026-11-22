# Độc lập với thứ tự chạy và dữ liệu của bài khác

Một test tốt phải tự mô tả điều kiện cần kiểm chứng và tự chuẩn bị dữ liệu mà nó cần. Kết quả của test không nên phụ thuộc vào việc một test khác đã chạy trước đó, đã tạo một bản ghi trong database, đã thay đổi một bean hay đã thiết lập một biến toàn cục.

Trong thiết kế kiểm thử, yêu cầu này thường được gọi là tính độc lập của test. Một test độc lập có thể chạy riêng, chạy cùng toàn bộ test suite, chạy lặp lại và chạy theo thứ tự khác mà vẫn cho cùng kết quả khi môi trường đầu vào không đổi. Với các test được cấu hình chạy song song, tính độc lập còn đòi hỏi chúng không tranh chấp dữ liệu hoặc tài nguyên dùng chung.

## Vì sao test phải độc lập?

Hãy hình dung hai test sau:

- Test A tạo khách hàng có mã `C-100`.
- Test B tìm khách hàng có mã `C-100` và xác nhận tên là Lan.

Nếu test B chỉ thành công sau khi test A chạy, test B đang phụ thuộc vào trạng thái do một test khác tạo ra. Khi chạy riêng B, chạy B trước A, hoặc chạy lại B sau khi dữ liệu đã bị thay đổi, kết quả có thể khác.

Một test suite có phụ thuộc ẩn thường biểu hiện qua các vấn đề:

- Test chạy riêng thì xanh nhưng chạy cả suite lại thất bại.
- Thay đổi thứ tự test khiến kết quả thay đổi.
- Chạy lại cùng một test nhiều lần tạo dữ liệu trùng hoặc lỗi khóa duy nhất.
- Chạy song song làm test lúc thành công, lúc thất bại.
- Một test thất bại khiến nhiều test sau thất bại dây chuyền.
- Test phải chạy theo một lệnh hoặc một nhóm cố định mới có thể tái hiện kết quả.

Những lỗi này làm giảm độ tin cậy của tín hiệu kiểm thử. Khi test thất bại, nhóm phát triển khó xác định nguyên nhân nằm ở nghiệp vụ vừa sửa hay ở trạng thái còn sót lại từ lần chạy trước.

## Bốn nguồn phụ thuộc cần nhận diện

Tính độc lập không chỉ liên quan đến thứ tự gọi phương thức. Một test có thể phụ thuộc vào nhiều dạng trạng thái khác nhau:

| Nguồn phụ thuộc | Ví dụ | Hướng xử lý |
|---|---|---|
| Thứ tự thực thi | Test B cần bản ghi do test A tạo | Mỗi test tự chuẩn bị dữ liệu của nó |
| Dữ liệu dùng chung | Nhiều test cùng sửa một khách hàng hoặc một bảng | Dùng dữ liệu riêng, khóa định danh riêng và dọn dẹp có phạm vi |
| Trạng thái trong bộ nhớ | Bean singleton giữ bộ đếm, cache hoặc danh sách đã thay đổi | Tránh state mutable dùng chung; reset rõ ràng khi cần |
| Môi trường bên ngoài | File cố định, message broker, API thật, thời gian hiện tại hoặc cấu hình JVM | Cô lập tài nguyên và kiểm soát đầu vào môi trường |

Một test có thể không gọi test khác nhưng vẫn phụ thuộc gián tiếp vào dữ liệu, cache, cấu hình hoặc tài nguyên mà test trước đã để lại.

## Không thiết kế test theo thứ tự chạy

JUnit Jupiter quản lý lifecycle và thực thi các phương thức test. Thứ tự mặc định của các phương thức test không phải một hợp đồng nghiệp vụ để các test dựa vào. JUnit có hỗ trợ sắp xếp thứ tự bằng `@TestMethodOrder`, nhưng annotation này không nên được dùng để biến một chuỗi test phụ thuộc trạng thái thành một quy trình kiểm thử.

Ví dụ, cách thiết kế sau có vấn đề:

~~~java
@TestMethodOrder(MethodOrderer.OrderAnnotation.class)
class CustomerFlowTest {

    @Test
    @Order(1)
    void createsCustomer() {
        // Tạo khách hàng C-100 trong database.
    }

    @Test
    @Order(2)
    void findsCreatedCustomer() {
        // Giả định C-100 đã được test phía trên tạo ra.
    }
}
~~~

Test thứ hai không tự tạo điều kiện đầu vào của nó. Nếu chạy riêng, nó có thể thất bại vì không tìm thấy dữ liệu. Nếu test thứ nhất thay đổi hoặc bị bỏ qua, test thứ hai cũng bị ảnh hưởng.

Nếu cần kiểm tra một quy trình gồm nhiều bước, hãy đặt các bước trong cùng một test case để thể hiện một kịch bản thống nhất:

~~~java
@Test
void createsAndFindsCustomer() {
    var customer = customerService.create("C-100", "Lan");

    var found = customerService.findByCode(customer.code());

    assertThat(found).isPresent();
    assertThat(found.get().name()).isEqualTo("Lan");
}
~~~

Ở đây test chủ động tạo khách hàng rồi kiểm tra kết quả của chính hành động đó. Các bước có quan hệ nhân quả thuộc cùng một kịch bản; những hành vi độc lập khác nên được kiểm tra trong các test riêng.

Nếu nghiệp vụ thật sự yêu cầu kiểm tra một chuỗi trạng thái, chẳng hạn tạo đơn hàng rồi thanh toán rồi hủy, có thể giữ chuỗi đó trong cùng test hoặc xây dựng fixture rõ ràng cho từng trạng thái. Đừng chia một kịch bản thành nhiều test method chỉ để tạo cảm giác mỗi bước là một test độc lập.

## Mỗi test tự chuẩn bị dữ liệu của mình

Một test nên khai báo rõ dữ liệu đầu vào mà nó cần. Không nên dựa vào một bản ghi có sẵn trong database dùng chung, một file được test khác tạo ra hoặc một biến static được cập nhật ở nơi khác.

Một số nguyên tắc hữu ích:

- Tạo dữ liệu tối thiểu đủ để kiểm tra hành vi đang xét.
- Dùng factory hoặc fixture builder để tạo object mới cho từng test.
- Ưu tiên dữ liệu định danh duy nhất khi nhiều test dùng chung database hoặc dịch vụ.
- Tránh sửa trực tiếp một bản ghi dùng chung mà không khôi phục trạng thái.
- Đặt tên dữ liệu thể hiện mục đích của test, giúp đọc lỗi dễ hơn.
- Không để test phụ thuộc vào thứ tự ID tự tăng nếu thứ tự đó không phải điều đang kiểm tra.

Ví dụ repository test có thể tự tạo email riêng cho mỗi lần chạy:

~~~java
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;
import org.springframework.transaction.annotation.Transactional;

import static org.assertj.core.api.Assertions.assertThat;

@SpringJUnitConfig(PersistenceTestConfig.class)
@Transactional
class CustomerRepositoryTest {

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @Autowired
    private CustomerRepository customerRepository;

    @Test
    void findsCustomerByEmail() {
        String email = "row39-" + UUID.randomUUID() + "@example.test";

        jdbcTemplate.update(
            "insert into customer(email, name) values (?, ?)",
            email,
            "Lan"
        );

        var customer = customerRepository.findByEmail(email);

        assertThat(customer).hasValueSatisfying(found ->
            assertThat(found.getName()).isEqualTo("Lan")
        );
    }
}
~~~

Ví dụ giả định schema có bảng `customer`, cấu hình test đã tạo datasource và repository, và phương thức `findByEmail` trả về `Optional<Customer>`. Email ngẫu nhiên giúp test không đụng vào bản ghi của lần chạy trước hoặc của test khác. `@Transactional` cho phép Spring Test quản lý transaction của test và mặc định rollback khi test kết thúc.

Dữ liệu duy nhất không thay thế hoàn toàn việc dọn dẹp. Nó giảm xung đột và giúp test có thể chạy lặp lại, nhưng nếu test ghi dữ liệu đã commit vào database dùng chung thì vẫn cần chiến lược xóa dữ liệu hoặc cô lập database/schema.

## Transaction rollback giúp gì và không giúp gì?

Spring Test hỗ trợ test-managed transaction. Khi một test được đánh dấu `@Transactional` và có transaction manager phù hợp, Spring Test bắt đầu transaction trước test và mặc định rollback sau test. Cơ chế này đặc biệt hữu ích cho repository test và các integration test làm việc với database.

~~~java
@SpringJUnitConfig(PersistenceTestConfig.class)
@Transactional
class OrderRepositoryTest {

    @Autowired
    private OrderRepository orderRepository;

    @Test
    void savesOrder() {
        var order = orderRepository.save(new Order("ORD-TEST-1"));

        assertThat(order.getId()).isNotNull();
        assertThat(orderRepository.findById(order.getId())).isPresent();
    }
}
~~~

Mỗi test chạy trong transaction riêng do test quản lý sẽ không để lại các thay đổi đã rollback cho test kế tiếp. Tuy nhiên, rollback có phạm vi cụ thể:

1. Nó chỉ hoàn tác thay đổi thuộc transaction được quản lý và tham gia vào transaction đó.
2. Một transaction độc lập, chẳng hạn luồng dùng propagation `REQUIRES_NEW`, có thể commit riêng.
3. Công việc chạy ở thread khác hoặc tác vụ bất đồng bộ không tự động tham gia transaction gắn với thread của test.
4. Gọi HTTP sang dịch vụ khác, gửi message ra broker, ghi file hoặc gửi email không thể được database rollback thu hồi.
5. Các thay đổi đã commit ngoài transaction của test vẫn còn sau khi test kết thúc.

Vì vậy, không nên kết luận rằng thêm `@Transactional` là mọi test đã được cô lập. Hãy xác định dữ liệu và side effect nào nằm trong transaction, dữ liệu nào được commit độc lập, và tài nguyên nào cần dọn dẹp riêng.

Khi test cần commit thật để kiểm tra một hành vi cụ thể, có thể sử dụng `@Commit` hoặc cấu hình `@Rollback(false)`. Khi đó, test phải có kế hoạch tạo dữ liệu riêng và xóa dữ liệu sau khi chạy, hoặc sử dụng database/schema được tạo riêng cho lần kiểm thử.

## Dùng Spring Test để chuẩn bị và dọn dữ liệu có chủ đích

Spring Test cung cấp `@Sql` để chạy SQL script trong các giai đoạn của test method. Nó hữu ích khi một test cần fixture database có cấu trúc rõ ràng:

~~~java
@Test
@Sql(
    scripts = "/sql/customer-fixture.sql",
    executionPhase = Sql.ExecutionPhase.BEFORE_TEST_METHOD
)
@Sql(
    scripts = "/sql/customer-cleanup.sql",
    executionPhase = Sql.ExecutionPhase.AFTER_TEST_METHOD
)
void findsConfiguredCustomer() {
    var customer = customerRepository.findByEmail("fixture@example.test");

    assertThat(customer).isPresent();
}
~~~

Script chuẩn bị và script dọn dẹp phải có phạm vi hẹp, chỉ tác động đến dữ liệu thuộc test. Không nên dùng lệnh xóa toàn bộ bảng hoặc truncate database dùng chung nếu test khác có thể đang sử dụng cùng dữ liệu. Nếu nhiều test chạy song song, fixture có khóa cố định có thể gây xung đột; khi đó hãy dùng dữ liệu định danh riêng hoặc database/schema riêng.

Tùy cách cấu hình transaction, SQL script có thể chạy trong transaction hiện tại hoặc theo transaction riêng. Cần chọn execution phase và transaction mode phù hợp với mục tiêu kiểm thử, đặc biệt khi test có dữ liệu cần commit độc lập.

Với các hệ thống lớn hơn, một số cách cô lập thường được áp dụng:

- Database riêng cho từng test suite hoặc từng worker.
- Schema riêng cho mỗi nhóm test.
- Container dịch vụ được tạo và hủy theo vòng đời của test suite.
- Bộ dữ liệu có namespace riêng theo test run.
- Cleanup theo khóa định danh hoặc namespace do test tạo ra.

Mục tiêu là để một test không xóa, sửa hoặc đọc nhầm dữ liệu của test khác.

## Cẩn thận với ApplicationContext và bean singleton dùng chung

Spring Test có TestContext Framework để quản lý ApplicationContext. Context có thể được cache và tái sử dụng giữa các test có cùng cấu hình. Điều này giúp giảm thời gian khởi động, nhưng cũng có nghĩa nhiều test có thể nhìn thấy cùng một instance bean.

Mặc định, bean Spring thường có scope singleton trong một ApplicationContext. Nếu bean giữ trạng thái mutable, thay đổi từ một test có thể ảnh hưởng đến test chạy sau:

~~~java
@Component
class RequestCounter {
    private int count;

    void increment() {
        count++;
    }

    int value() {
        return count;
    }
}
~~~

Nếu test gọi `increment()` rồi giả định `value()` bắt đầu từ 0, kết quả sẽ phụ thuộc vào việc bean đã được sử dụng bởi test khác hay chưa. Trong ứng dụng thật, bean singleton có trạng thái mutable cũng có thể tạo vấn đề về tính an toàn luồng.

Nên ưu tiên bean stateless hoặc trạng thái được truyền qua tham số và trả về từ phương thức. Nếu cần cache hay bộ nhớ tạm có thể thay đổi, hãy cung cấp cơ chế reset rõ ràng trong phạm vi test, hoặc tạo context riêng khi đó là yêu cầu thực sự của kịch bản.

`@DirtiesContext` có thể đánh dấu ApplicationContext là không còn phù hợp để tái sử dụng, khiến Spring loại context đó khỏi cache và tạo lại khi cần. Đây là công cụ dành cho tình huống test đã làm thay đổi trạng thái context mà không thể khôi phục đáng tin cậy. Nó không phải cơ chế dọn database, xóa file, thu hồi message hoặc hoàn tác side effect bên ngoài Spring. Lạm dụng annotation này còn khiến suite chậm do phải khởi tạo context nhiều lần.

## Tránh trạng thái toàn cục và fixture mutable

Trạng thái toàn cục thường khó nhận ra vì nó nằm ngoài vòng đời của object test:

- Biến `static` chứa danh sách hoặc bộ đếm dùng chung.
- System property, default locale, timezone hoặc cấu hình JVM bị thay đổi.
- Cache static được khởi tạo một lần.
- Singleton bean giữ collection mutable.
- File tạm có tên cố định.
- Cổng mạng hoặc tên queue cố định được nhiều test cùng sử dụng.

Nếu test phải thay đổi một thiết lập toàn cục, hãy lưu giá trị cũ và khôi phục trong `finally` hoặc lifecycle cleanup tương ứng. Tuy vậy, khôi phục giá trị sau test vẫn không ngăn được xung đột nếu test khác chạy song song trong lúc thiết lập đó đang bị thay đổi. Những test cùng thay đổi tài nguyên toàn cục cần được tuần tự hóa hoặc thiết kế lại để không chia sẻ tài nguyên.

Fixture builder cũng nên tạo object mới thay vì trả lại một object dùng chung:

~~~java
class CustomerFixture {

    static Customer newCustomer() {
        return new Customer(
            "customer-" + UUID.randomUUID(),
            "Lan"
        );
    }
}
~~~

Mỗi lần gọi `newCustomer()` tạo ra một customer riêng. Nếu dùng một object static rồi sửa tên hoặc mã của nó trong từng test, các test có thể vô tình chia sẻ cùng một tham chiếu và làm thay đổi dữ liệu của nhau.

## Tính độc lập khi chạy song song

Chạy test song song giúp giảm thời gian feedback, nhưng làm lộ các phụ thuộc dùng chung. Hai test có thể cùng:

- Chèn một email hoặc mã đơn hàng cố định vào cùng bảng.
- Xóa cùng một nhóm bản ghi.
- Ghi vào cùng một file.
- Dùng chung queue, topic, bucket hoặc tên resource.
- Thay đổi cùng system property hoặc trạng thái singleton bean.

Để chạy song song an toàn, mỗi test nên sở hữu dữ liệu và tài nguyên riêng. Ví dụ, tạo tên file từ UUID trong thư mục tạm, tạo khóa database có namespace của test run, hoặc cấp riêng database/schema cho mỗi worker.

Nếu một tài nguyên thật sự không thể chia sẻ an toàn, hãy giới hạn vùng test sử dụng tài nguyên đó chạy tuần tự bằng cơ chế đồng bộ phù hợp. Việc khóa nên thể hiện rõ tài nguyên nào cần bảo vệ; không nên tuần tự hóa toàn bộ test suite chỉ để che giấu một nguồn phụ thuộc chưa được xử lý.

Cũng cần phân biệt giữa một test dùng chung immutable fixture và một test dùng chung mutable fixture. Dữ liệu bất biến, chỉ đọc thường có thể chia sẻ an toàn. Dữ liệu có thể bị thay đổi cần được sao chép, tạo mới hoặc bảo vệ bằng cơ chế đồng bộ.

## Kiểm soát thời gian, ngẫu nhiên và dịch vụ bên ngoài

Một test có thể phụ thuộc vào môi trường ngay cả khi không dùng chung database. Ví dụ, test kiểm tra hóa đơn hết hạn bằng cách đọc trực tiếp thời gian hiện tại sẽ cho kết quả khác khi chạy vào ngày khác hoặc đúng sát ranh giới thời gian.

Với logic phụ thuộc thời gian, hãy đưa nguồn thời gian thành dependency để test có thể cung cấp thời gian cố định:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

Clock fixedClock = Clock.fixed(
    Instant.parse("2026-01-15T10:00:00Z"),
    ZoneOffset.UTC
);

var service = new ExpirationService(fixedClock);
~~~

Trong ứng dụng Spring, `Clock` có thể được khai báo thành bean và thay bằng một clock cố định trong cấu hình test. Khi đó, test có thể kiểm tra chính xác ranh giới hết hạn mà không phụ thuộc đồng hồ máy đang chạy.

Với dữ liệu ngẫu nhiên, dùng seed cố định nếu cần tái hiện cùng một chuỗi giá trị; dùng UUID hoặc khóa ngẫu nhiên khi mục tiêu là tránh đụng dữ liệu giữa các test. Hai mục đích này khác nhau: seed cố định hỗ trợ khả năng tái hiện, còn định danh duy nhất hỗ trợ cô lập.

Không nên để test nghiệp vụ gọi API bên ngoài thật nếu phản hồi và trạng thái dịch vụ không thuộc quyền kiểm soát của test. Hãy thay dependency từ xa bằng stub, fake hoặc mock phù hợp với tầng đang kiểm thử. Nếu cần kiểm chứng giao tiếp thật, hãy tạo một nhóm integration test riêng với môi trường và dữ liệu được kiểm soát.

Tránh dùng `Thread.sleep()` để chờ một điều kiện không chắc chắn. Sleep chỉ trì hoãn test; nó không đảm bảo trạng thái mong muốn đã xuất hiện. Với tác vụ bất đồng bộ, nên chờ một điều kiện cụ thể bằng cơ chế đồng bộ hoặc polling có giới hạn thời gian, đồng thời dọn dẹp tác vụ và tài nguyên sau khi hoàn tất.

## Nhận biết và xử lý một test đang phụ thuộc

Khi một test chỉ thất bại trong toàn suite, có thể khoanh vùng bằng cách chạy test riêng, chạy lặp lại test, chạy cả class và thay đổi thứ tự hoặc bật chạy song song nếu cấu hình cho phép. Mục đích là tìm trạng thái mà test đang vô tình nhận từ bên ngoài.

Một số dấu hiệu và hướng điều tra:

| Dấu hiệu | Câu hỏi cần kiểm tra |
|---|---|
| Chạy riêng thành công, chạy suite thất bại | Test nào chạy trước đã sửa dữ liệu, bean hoặc cấu hình nào? |
| Chạy lần đầu thành công, lần hai thất bại | Dữ liệu đã commit hoặc file/resource nào còn sót lại? |
| Chỉ thất bại khi chạy song song | Có tài nguyên hoặc định danh nào đang được chia sẻ? |
| Kết quả phụ thuộc thời điểm chạy | Test có đọc clock, timezone, locale hoặc dịch vụ ngoài không? |
| Thêm `@DirtiesContext` thì hết lỗi | Có bean mutable hoặc trạng thái trong context bị rò rỉ không? |
| Rollback rồi vẫn còn dữ liệu | Có transaction độc lập, thread khác hoặc side effect ngoài database không? |

Khi tìm thấy nguyên nhân, hãy sửa tại nguồn phụ thuộc: tạo fixture riêng, dùng định danh duy nhất, khôi phục trạng thái, cô lập tài nguyên hoặc bỏ state mutable không cần thiết. Chỉ thêm thứ tự chạy hay reset toàn bộ context có thể làm triệu chứng biến mất trong một cấu hình nhưng vẫn giữ nguyên nguyên nhân.

## Nguyên tắc thiết kế có thể áp dụng ngay

Khi viết một test mới, hãy tự trả lời những câu hỏi sau:

1. Test có thể chạy một mình mà không cần test khác tạo dữ liệu trước không?
2. Test có tự tạo những bản ghi và object mà nó cần không?
3. Dữ liệu do test tạo ra có thể va chạm với test khác hoặc lần chạy trước không?
4. Test có thay đổi bean singleton, biến static, system property, file hoặc resource dùng chung không?
5. Nếu có transaction, mọi thao tác ghi có thực sự tham gia transaction đó không?
6. Nếu test chạy song song, mỗi test có sở hữu dữ liệu và tài nguyên riêng không?
7. Thời gian, số ngẫu nhiên và phản hồi dịch vụ bên ngoài có được kiểm soát không?
8. Sau khi test kết thúc, dữ liệu và tài nguyên mà test sở hữu có được rollback hoặc dọn dẹp không?

Một test độc lập không cần biết test nào đã chạy trước nó. Nó tự chuẩn bị đầu vào, thực hiện một hành vi có phạm vi rõ ràng, kiểm tra kết quả và quản lý những thay đổi mà nó tạo ra. Khi duy trì nguyên tắc này, test suite có thể chạy riêng lẻ, lặp lại, đổi thứ tự hoặc mở rộng sang chạy song song mà vẫn cung cấp kết quả đáng tin cậy.
