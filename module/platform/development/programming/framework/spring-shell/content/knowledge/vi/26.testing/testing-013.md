# Chờ có điều kiện thay vì phụ thuộc khoảng dừng cố định

Trong kiểm thử ứng dụng Spring Shell, một command có thể khởi chạy tác vụ nền, gửi message, cập nhật dữ liệu bất đồng bộ hoặc tạo output sau khi một thành phần khác hoàn tất. Nếu test dùng Thread.sleep(1000) rồi mới kiểm tra, kết quả phụ thuộc vào tốc độ máy, tải CI và lịch chạy thread. Máy nhanh làm test chờ lâu không cần thiết; máy chậm có thể khiến test kiểm tra quá sớm.

Thay vì đoán tác vụ cần bao nhiêu mili giây, hãy đợi đến khi điều kiện mong đợi thực sự đúng, đồng thời đặt giới hạn thời gian rõ ràng. Với Spring Shell 3.4, tài liệu kiểm thử dùng Awaitility để đợi shell session hiển thị prompt hoặc output. Với Spring Shell 4.x, ShellTestClient cung cấp kết quả sau khi command đồng bộ hoàn tất; nếu command khởi chạy công việc nền, test vẫn cần đợi trạng thái nghiệp vụ hoặc kết quả bất đồng bộ riêng.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích vì sao khoảng dừng cố định làm test chậm và không ổn định.
- Phân biệt chờ theo điều kiện, chờ theo tín hiệu và chờ theo thời gian.
- Dùng Awaitility để đợi một điều kiện hoặc assertion đạt được trong giới hạn thời gian.
- Đặt timeout, poll interval và poll delay phù hợp.
- Kiểm thử output của interactive shell session trong Spring Shell 3.4.
- Dùng ShellTestClient, ShellScreen và ShellInputProvider trong Spring Shell 4.x.
- Phân biệt command hoàn tất đồng bộ với tác vụ nền do command khởi chạy.
- Chọn CountDownLatch hoặc CompletableFuture khi có tín hiệu hoàn tất trực tiếp.
- Tránh polling có tác dụng phụ, điều kiện không thread-safe và việc bỏ qua exception quá rộng.
- Tạo thông báo lỗi hữu ích khi điều kiện không đạt trước timeout.

## 1. Vì sao Thread.sleep() làm test không ổn định?

Một test thường gặp:

~~~java
@Test
void importsCustomer() throws Exception {
    importService.startImport("customers.csv");

    Thread.sleep(1_000);

    assertThat(customerRepository.count()).isEqualTo(100);
}
~~~

Test này giả định import luôn hoàn tất trong một giây. Nếu máy chạy nhanh, test vẫn chờ hết một giây dù dữ liệu đã sẵn sàng từ trước. Nếu CI đang tải cao hoặc database phản hồi chậm, import có thể cần hơn một giây và assertion thất bại dù hệ thống vẫn hoạt động đúng.

Tăng sleep lên năm hoặc mười giây chỉ làm test chậm hơn; nó không chứng minh công việc đã hoàn tất. Một khoảng dừng chỉ cho biết test thread đã ngừng chạy trong một khoảng thời gian. Nó không đồng bộ với thread xử lý nền, không xác nhận trạng thái hệ thống và không bảo đảm dữ liệu đã được ghi.

| Cách chờ | Hành vi | Hạn chế |
|---|---|---|
| Thread.sleep(1000) | Dừng test thread trong một giây | Không kiểm tra trạng thái; có thể chờ thừa hoặc kiểm tra quá sớm |
| Vòng lặp polling tự viết | Đọc lại điều kiện cho đến khi đúng | Dễ quên timeout, gây busy loop hoặc tạo thông báo lỗi kém |
| Awaitility | Poll điều kiện với timeout và interval có cấu hình | Cần điều kiện an toàn khi gọi lặp và có thể quan sát được |
| CountDownLatch / CompletableFuture | Chờ tín hiệu hoàn tất cụ thể | Cần có callback hoặc future đại diện đúng công việc |

Mục tiêu là đồng bộ với điều mà test cần xác nhận. Nếu cần biết import đã ghi đủ 100 bản ghi, hãy đợi trạng thái repository đạt 100. Nếu công việc phát ra callback hoàn tất, hãy chờ callback đó. Không chọn một con số thời gian rồi hy vọng tác vụ đã xong.

## 2. Chờ theo điều kiện là gì?

Chờ theo điều kiện là lặp lại việc đánh giá một điều kiện cho đến khi điều kiện đúng hoặc hết thời gian cho phép. Test không cần biết chính xác tác vụ hoàn tất sau bao nhiêu mili giây.

Ví dụ:

~~~java
import static java.util.concurrent.TimeUnit.SECONDS;
import static org.awaitility.Awaitility.await;

@Test
void importsCustomer() {
    importService.startImport("customers.csv");

    await().atMost(5, SECONDS)
            .until(() -> customerRepository.count() == 100);
}
~~~

Test bắt đầu import rồi kiểm tra repository nhiều lần. Khi số lượng bản ghi đạt 100, Awaitility kết thúc ngay. Nếu điều kiện không đạt trong năm giây, test thất bại bằng timeout exception thay vì chờ vô hạn.

Điều kiện cần thể hiện chính xác kết quả cuối cùng mà test quan tâm. Một điều kiện như “thread đã chạy” hoặc “command đã trả về” có thể chưa đủ nếu mục tiêu là xác nhận dữ liệu đã được ghi hoặc message đã được xử lý.

## 3. Awaitility và cách đọc điều kiện

Awaitility là thư viện Java hỗ trợ chờ có điều kiện trong test. Cấu trúc cơ bản:

~~~java
await()
        .atMost(5, SECONDS)
        .until(() -> repository.count() == 100);
~~~

Các thành phần:

- **await():** bắt đầu một thao tác chờ.
- **atMost(...):** giới hạn tổng thời gian chờ.
- **until(...):** điều kiện boolean hoặc supplier/matcher cần đạt.
- **pollInterval(...):** khoảng cách giữa các lần kiểm tra.
- **pollDelay(...):** thời gian trì hoãn trước lần kiểm tra đầu tiên.
- **untilAsserted(...):** chạy assertion lặp lại cho đến khi assertion thành công hoặc timeout.

Awaitility 4.x mặc định dùng timeout 10 giây và poll interval/poll delay 100 mili giây nếu không cấu hình khác. Trong test quan trọng, nên khai báo timeout rõ ràng để người đọc hiểu kỳ vọng của tác vụ và tránh phụ thuộc cấu hình mặc định. [Awaitility — Usage](https://github.com/awaitility/awaitility/wiki/Usage).

### 3.1. Đợi bằng predicate

Khi điều kiện đơn giản, dùng lambda trả về boolean:

~~~java
await().atMost(5, SECONDS)
        .until(() -> jobRepository.findStatus(jobId) == JobStatus.COMPLETED);
~~~

Điều kiện chỉ trả true khi job đã hoàn tất. Nếu trạng thái có nhiều bước như CREATED, RUNNING, COMPLETED và FAILED, hãy đợi trạng thái kết thúc cụ thể theo mục tiêu của test.

### 3.2. Đợi bằng assertion

Khi cần kiểm tra nhiều thuộc tính, dùng untilAsserted:

~~~java
await().atMost(5, SECONDS).untilAsserted(() -> {
    ImportJob job = jobRepository.findById(jobId).orElseThrow();
    assertThat(job.getStatus()).isEqualTo(JobStatus.COMPLETED);
    assertThat(job.getImportedCount()).isEqualTo(100);
});
~~~

Mỗi lần assertion chưa đạt, Awaitility sẽ tiếp tục chờ và đánh giá lại cho đến timeout. Cách này thường dễ đọc hơn khi cần kiểm tra object hoặc nhiều giá trị liên quan.

### 3.3. Dùng method reference hoặc matcher

Có thể tách supplier để tái sử dụng:

~~~java
await().atMost(5, SECONDS)
        .until(customerRepository::count, count -> count == 100);
~~~

Nếu dự án dùng Hamcrest:

~~~java
await().atMost(5, SECONDS)
        .until(customerRepository::count, is(100L));
~~~

Chọn cách viết giúp điều kiện dễ hiểu và không lặp logic trong nhiều test.

## 4. Chọn timeout và poll interval

Timeout là giới hạn tối đa test chấp nhận chờ. Poll interval là khoảng thời gian giữa hai lần đánh giá điều kiện. Poll delay là thời gian trước lần đánh giá đầu tiên.

Ví dụ:

~~~java
await()
        .pollDelay(Duration.ofMillis(50))
        .pollInterval(Duration.ofMillis(100))
        .atMost(Duration.ofSeconds(5))
        .untilAsserted(() ->
                assertThat(jobRepository.isCompleted(jobId)).isTrue());
~~~

Chọn các giá trị dựa trên đặc tính của hệ thống:

- Tác vụ nội bộ trong cùng JVM thường có thể dùng timeout ngắn.
- Tác vụ qua message broker, database hoặc process bên ngoài cần tính đến độ trễ của dependency.
- Poll interval quá nhỏ có thể tạo nhiều truy vấn và tăng tải.
- Poll interval quá lớn làm test phát hiện điều kiện đạt chậm hơn.
- Timeout quá ngắn gây lỗi giả khi CI tải cao; timeout quá dài làm lỗi thật mất nhiều thời gian mới được phát hiện.

Không dùng một timeout rất lớn để che việc hệ thống không tiến triển. Nếu tác vụ dự kiến hoàn tất trong vài giây nhưng thường xuyên chạm timeout, hãy điều tra deadlock, dependency chậm hoặc lỗi xử lý nền.

### 4.1. Đặt tên cho thao tác chờ

Khi test có nhiều điều kiện chờ, đặt alias để thông báo timeout dễ hiểu:

~~~java
await()
        .alias("customer import completion")
        .atMost(Duration.ofSeconds(8))
        .untilAsserted(() ->
                assertThat(importRepository.countByJob(jobId)).isEqualTo(100));
~~~

Alias giúp xác định điều kiện nào hết thời gian khi test có nhiều lần await.

### 4.2. Polling phải quan sát, không gây tác dụng phụ

Lambda trong until hoặc untilAsserted có thể được gọi nhiều lần. Không đặt hành động chỉ được phép chạy một lần trong lambda:

~~~java
// Sai: mỗi lần polling lại gửi thêm một request.
await().atMost(5, SECONDS).until(() -> {
    paymentService.charge(orderId);
    return paymentRepository.isPaid(orderId);
});
~~~

Thực hiện hành động một lần trước, sau đó chỉ quan sát trạng thái:

~~~java
paymentService.charge(orderId);

await().atMost(5, SECONDS)
        .until(() -> paymentRepository.isPaid(orderId));
~~~

Điều kiện nên nhẹ, có thể gọi lặp và không thay đổi trạng thái của hệ thống.

## 5. Kiểm thử interactive shell session trong Spring Shell 3.4

Spring Shell 3.4 có test client hỗ trợ tạo interactive session. Test có thể khởi chạy shell, gửi chuỗi phím và kiểm tra màn hình sau khi shell xử lý input. Vì session có vòng lặp riêng, output có thể xuất hiện sau khi test gửi lệnh; đây là tình huống phù hợp để đợi theo điều kiện.

Ví dụ theo tài liệu Spring Shell 3.4.1:

~~~java
@ShellTest
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class InteractiveShellTests {

    @Autowired
    ShellTestClient client;

    @Test
    void displaysHelpAfterCommand() {
        InteractiveShellSession session = client.interactive().run();

        await().atMost(2, SECONDS).untilAsserted(() ->
                ShellAssertions.assertThat(session.screen())
                        .containsText("shell"));

        session.write(
                session.writeSequence()
                        .text("help")
                        .carriageReturn()
                        .build());

        await().atMost(2, SECONDS).untilAsserted(() ->
                ShellAssertions.assertThat(session.screen())
                        .containsText("AVAILABLE COMMANDS"));
    }
}
~~~

Test đợi shell screen thể hiện prompt trước khi gửi command. Sau khi gửi help, test tiếp tục đợi output xuất hiện trên screen. Nó không giả định rằng shell luôn xử lý lệnh trong một khoảng thời gian cố định.

@DirtiesContext được dùng trong ví dụ để tạo context mới sau mỗi test method, tránh session tương tác còn trạng thái từ test trước ảnh hưởng test sau. Có thể chọn chiến lược quản lý context khác nếu test suite có cách đóng session và cô lập trạng thái phù hợp.

Tài liệu Spring Shell 3.4.1 dùng chính Awaitility để chờ output của interactive và non-interactive session. Xem [Spring Shell 3.4.1 — Testing Basics](https://docs.spring.io/spring-shell/reference/testing/basics.html).

## 6. Kiểm thử command không tương tác trong Spring Shell 3.4

Test non-interactive cũng có thể trả về session có màn hình được cập nhật sau khi runner xử lý command. Ví dụ tài liệu 3.4.1:

~~~java
@ShellTest
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class NonInteractiveShellTests {

    @Autowired
    ShellTestClient client;

    @Test
    void executesHelp() {
        NonInteractiveShellSession session = client
                .nonInterative("help")
                .run();

        await().atMost(2, SECONDS).untilAsserted(() ->
                ShellAssertions.assertThat(session.screen())
                        .containsText("AVAILABLE COMMANDS"));
    }
}
~~~

Tên method nonInterative trong ví dụ API của tài liệu 3.4.1 được viết như vậy. Khi sử dụng, hãy đối chiếu đúng minor version và IDE autocomplete của dependency đang cài.

Chờ output có ý nghĩa khi test đang tương tác với session bất đồng bộ. Nếu API thực thi command đã trả kết quả hoàn chỉnh đồng bộ, hãy assert trực tiếp thay vì thêm một lần chờ không cần thiết.

## 7. Spring Shell 4.x: phân biệt command hoàn tất và tác vụ nền hoàn tất

Spring Shell 4.0.3 cung cấp @ShellTest, ShellTestClient, ShellScreen, ShellAssertions và ShellInputProvider. Với command đồng bộ, ShellTestClient.sendCommand(...) thực thi command và trả về ShellScreen sau khi command kết thúc:

~~~java
@ShellTest
@ContextConfiguration(classes = ExampleShellApplication.class)
class CustomerCommandTests {

    @Autowired
    ShellTestClient client;

    @Test
    void listsCustomers() throws Exception {
        ShellScreen screen = client.sendCommand("customer list");

        ShellAssertions.assertThat(screen)
                .containsText("Customer list");
    }
}
~~~

Trong trường hợp này, command trả kết quả đồng bộ nên assertion trên screen có thể thực hiện ngay sau sendCommand.

Tình huống khác là command chỉ gửi yêu cầu rồi trả về ngay:

~~~java
@Command(command = "report refresh")
public String refreshReport(@Option String reportId) {
    reportService.startRefresh(reportId);
    return "Refresh started: " + reportId;
}
~~~

sendCommand chỉ bảo đảm command đã chạy và trả thông báo “Refresh started”. Nó không có nghĩa tác vụ refresh nền đã hoàn tất. Test cần đợi trạng thái report ở repository hoặc một điều kiện nghiệp vụ tương đương:

~~~java
@ShellTest
class ReportCommandTests {

    @Autowired
    ShellTestClient client;

    @Autowired
    ReportRepository reports;

    @Test
    void refreshesReportAsynchronously() throws Exception {
        ShellScreen screen = client.sendCommand("report refresh --report-id R-100");

        ShellAssertions.assertThat(screen)
                .containsText("Refresh started: R-100");

        await().atMost(10, SECONDS).untilAsserted(() ->
                assertThat(reports.findStatus("R-100"))
                        .isEqualTo(ReportStatus.READY));
    }
}
~~~

Điều kiện cuối kiểm tra kết quả công việc nền, không chỉ kiểm tra output của command. Đây là khác biệt quan trọng khi command khởi chạy một job, publish message hoặc giao việc cho executor.

Tài liệu Spring Shell 4.0.3: [Testing](https://docs.spring.io/spring-shell/reference/testing.html), [ShellTestClient API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/test/ShellTestClient.html).

## 8. Mô phỏng input bằng ShellInputProvider

Một command có thể yêu cầu người dùng nhập thêm dữ liệu sau khi command bắt đầu. Spring Shell 4.0.3 có ShellInputProvider để cung cấp input và password trong test.

Ví dụ command đọc input:

~~~java
@Bean
Command ask() {
    return new AbstractCommand("ask", "Ask for user input") {
        @Override
        public ExitStatus doExecute(CommandContext context) throws Exception {
            String message = context.inputReader().readInput();
            context.outputWriter().println("You said: " + message);
            return ExitStatus.OK;
        }
    };
}
~~~

Test cung cấp input:

~~~java
@Test
void readsInput() throws Exception {
    ShellInputProvider input = ShellInputProvider
            .providerFor("ask")
            .withInput("hello")
            .build();

    ShellScreen screen = client.sendCommand(input);

    ShellAssertions.assertThat(screen).containsText("You said: hello");
}
~~~

ShellInputProvider giúp test tái hiện input tương tác mà không cần đọc từ bàn phím thật. Nếu command đọc nhiều giá trị hoặc password, thêm các giá trị theo thứ tự mà command yêu cầu. Không ghi password thật vào fixture hoặc log test.

Nếu command khởi chạy tác vụ nền sau khi nhận input, việc input đã được cung cấp và command đã trả screen vẫn không chứng minh tác vụ nền hoàn tất. Tiếp tục đợi điều kiện nghiệp vụ sau lệnh gửi.

Tài liệu: [ShellInputProvider API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/test/ShellInputProvider.html) và [ShellInputProvider.Builder API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/test/ShellInputProvider.Builder.html).

## 9. Khi nào dùng Awaitility, khi nào dùng tín hiệu hoàn tất?

Polling không phải lựa chọn duy nhất. Nếu test kiểm soát được API bất đồng bộ và API cung cấp tín hiệu hoàn tất, chờ tín hiệu thường rõ ràng và ít truy vấn hơn.

| Tình huống | Cách chờ phù hợp |
|---|---|
| Đợi repository cập nhật sau message | Awaitility kiểm tra trạng thái repository |
| Đợi output xuất hiện trên interactive screen | Awaitility kiểm tra ShellScreen |
| Tác vụ trả CompletableFuture | future.get(timeout) hoặc assert future hoàn tất |
| Worker báo hoàn tất qua callback | CountDownLatch hoặc CompletableFuture |
| Đợi service ngoài chuyển trạng thái | Poll health/status endpoint với timeout và interval phù hợp |
| Đợi một khoảng thời gian tối thiểu là hành vi cần kiểm thử | Dùng clock/scheduler giả nếu có thể; nếu không, kiểm tra thời lượng với timeout phù hợp |

### 9.1. CompletableFuture

Nếu service trả về future, test có thể chờ chính future:

~~~java
CompletableFuture<ImportResult> result =
        importService.startImport("customers.csv");

ImportResult completed = result.get(5, SECONDS);

assertThat(completed.importedCount()).isEqualTo(100);
~~~

get(timeout, unit) giới hạn thời gian chờ và ném TimeoutException nếu future chưa hoàn tất. Nếu future hoàn tất bằng exception, test nhận được ExecutionException và có thể kiểm tra nguyên nhân.

### 9.2. CountDownLatch

Nếu API báo hoàn tất qua callback:

~~~java
CountDownLatch completed = new CountDownLatch(1);

importService.startImport("customers.csv", result -> completed.countDown());

assertThat(completed.await(5, SECONDS)).isTrue();
~~~

Latch giúp test chờ một sự kiện cụ thể. Nếu cần kiểm tra kết quả, lưu kết quả callback vào một cấu trúc thread-safe hoặc dùng future chứa kết quả.

Không tạo latch chỉ để đợi một thời gian. Latch cần được giảm count khi sự kiện thật sự xảy ra.

## 10. Đợi trạng thái ổn định, không chỉ đạt đúng một lần

Một số điều kiện có thể đúng trong thời gian rất ngắn rồi thay đổi lại. Ví dụ, trạng thái worker chuyển READY trước khi một bước cleanup tiếp tục đặt nó về STOPPING. Nếu yêu cầu của test là trạng thái phải duy trì, chỉ đợi điều kiện đúng một lần là chưa đủ.

Awaitility 4.x có during(...) để xác nhận điều kiện được duy trì trong một khoảng thời gian nằm trong giới hạn tổng:

~~~java
await()
        .during(Duration.ofMillis(500))
        .atMost(Duration.ofSeconds(3))
        .untilAsserted(() ->
                assertThat(service.health()).isEqualTo(Health.UP));
~~~

Dùng cách này khi hợp đồng thật sự yêu cầu điều kiện ổn định trong khoảng thời gian. Không thêm during vào mọi test vì nó làm test phải chờ lâu hơn và có thể che mất một thiết kế test chưa đúng.

Nếu trạng thái chỉ là một mốc chuyển tiếp, hãy lưu một terminal state hoặc event có thể truy vấn thay vì cố quan sát một giá trị thoáng qua bằng polling.

## 11. Xử lý điều kiện chưa sẵn sàng và exception tạm thời

Một số hệ thống trả exception trong giai đoạn khởi động hoặc trong khi dữ liệu chưa được tạo. Awaitility có thể bỏ qua một exception được xác định rõ trong lúc đánh giá điều kiện:

~~~java
await()
        .ignoreException(TransientDataNotReadyException.class)
        .atMost(5, SECONDS)
        .until(() -> repository.loadStatus(jobId) == JobStatus.COMPLETED);
~~~

Chỉ bỏ qua exception mà test biết là trạng thái tạm thời và có thể phục hồi. Không dùng ignoreExceptions() cho tất cả exception nếu điều đó có thể che lỗi lập trình, lỗi kết nối vĩnh viễn hoặc lỗi dữ liệu.

Nếu trạng thái chưa sẵn sàng được biểu diễn bằng Optional, null hoặc trạng thái PENDING, nên kiểm tra trực tiếp thay vì dùng exception làm tín hiệu:

~~~java
await().atMost(5, SECONDS).untilAsserted(() -> {
    Optional<Job> job = jobRepository.findById(jobId);
    assertThat(job).isPresent();
    assertThat(job.orElseThrow().getStatus()).isEqualTo(JobStatus.COMPLETED);
});
~~~

## 12. Timeout phải làm test thất bại với thông tin hữu ích

Timeout không nên chỉ cho biết “test chờ quá lâu”. Điều kiện cần đủ rõ để người đọc hiểu điều gì chưa xảy ra.

Nên:

- Đặt alias có ý nghĩa cho lần await.
- Dùng assertion mô tả trạng thái mong đợi.
- Đưa job ID, command hoặc resource ID vào thông báo khi phù hợp.
- Giữ log của worker hoặc message consumer để điều tra.
- Phân biệt timeout chờ kết quả với exception thực sự từ tác vụ.

Ví dụ:

~~~java
await()
        .alias("report R-100 becomes READY")
        .atMost(Duration.ofSeconds(10))
        .untilAsserted(() ->
                assertThat(reportRepository.findStatus("R-100"))
                        .as("status of report R-100")
                        .isEqualTo(ReportStatus.READY));
~~~

Khi timeout, kiểm tra trạng thái hiện tại và log của worker để biết công việc chưa được nhận, đang chạy, bị retry hay đã thất bại. Không tăng timeout một cách máy móc nếu điều kiện không bao giờ có khả năng đạt.

## 13. Điều kiện polling phải thread-safe

Awaitility đánh giá điều kiện trên thread do thư viện quản lý theo cấu hình. Nó không tự bảo đảm các biến được đọc có visibility hoặc synchronization đúng. Tài liệu Awaitility nhấn mạnh trách nhiệm đồng bộ thuộc về ứng dụng và test.

Nếu thread nền cập nhật một biến dùng chung, hãy dùng:

- AtomicInteger, AtomicBoolean hoặc cấu trúc atomic tương ứng.
- ConcurrentHashMap hoặc collection thread-safe.
- volatile cho trạng thái đơn giản khi phù hợp.
- Future, latch hoặc cơ chế đồng bộ đã được thiết kế cho luồng đó.
- Repository hoặc API đọc trạng thái có bảo đảm nhất quán phù hợp.

Không dùng một ArrayList hoặc field thường được nhiều thread đọc/ghi mà không có đồng bộ rồi kỳ vọng Awaitility làm cho dữ liệu an toàn.

Điều kiện polling cũng không nên sửa dữ liệu. Việc đọc trạng thái cần có tính lặp lại và không tạo ra race condition mới.

## 14. Không dùng polling cho mọi bài toán thời gian

Có những test cần kiểm tra một quy tắc thời gian cụ thể, ví dụ:

- Một thao tác không được phép chạy trước thời điểm mở khóa.
- Debounce phải chờ khoảng im lặng sau lần input cuối.
- Retry chỉ được phép sau backoff.
- Cache phải hết hạn sau TTL.

Nếu có thể, inject Clock, Scheduler hoặc TimeSource để test tiến thời gian giả lập mà không phải chờ thật:

~~~java
class TokenService {
    private final Clock clock;

    TokenService(Clock clock) {
        this.clock = clock;
    }

    boolean isExpired(Instant expiresAt) {
        return !clock.instant().isBefore(expiresAt);
    }
}
~~~

Test có thể dùng Clock cố định hoặc clock có thể điều khiển để kiểm tra trước/sau thời điểm hết hạn. Cách này nhanh và xác định hơn việc sleep cho đến khi TTL trôi qua.

Nếu mục tiêu là xác nhận một tác vụ bất đồng bộ cuối cùng hoàn tất, hãy đợi trạng thái cuối cùng. Nếu mục tiêu là xác nhận thời gian thực tế đã trôi qua hoặc một timer được kích hoạt đúng lúc, hãy kiểm soát clock/scheduler hoặc dùng kiểm thử thời gian có chủ đích.

## 15. Những lỗi thường gặp

### Dùng Thread.sleep() trước mọi assertion

Thay sleep bằng điều kiện có timeout. Nếu command đồng bộ và đã trả kết quả hoàn chỉnh, assert trực tiếp; nếu tác vụ nền còn chạy, đợi trạng thái nền.

### Chờ output của command nhưng bỏ qua công việc nền

Thông báo “Job started” chỉ chứng minh command đã khởi chạy job. Đợi trạng thái COMPLETED hoặc kết quả nghiệp vụ, không dừng ở output khởi chạy.

### Timeout quá ngắn

Test có thể thất bại ngẫu nhiên trên CI. Chọn timeout dựa trên độ trễ hợp lý của dependency và quan sát lịch sử thời gian chạy.

### Timeout quá dài

Lỗi thật mất nhiều thời gian mới xuất hiện. Đặt timeout theo hợp đồng của test và cung cấp diagnostics.

### Poll interval quá nhỏ

Test có thể tạo tải lớn lên database hoặc service. Chọn interval vừa đủ để phát hiện chuyển trạng thái mà không liên tục gọi hệ thống.

### Điều kiện polling thực hiện mutation

Lambda được gọi nhiều lần và có thể lặp tác động. Chuyển hành động ra ngoài await; lambda chỉ đọc trạng thái.

### Bỏ qua mọi exception

Lỗi thật có thể bị xem như trạng thái chưa sẵn sàng. Chỉ ignore exception tạm thời đã xác định.

### Đọc field không thread-safe

Test có thể không nhìn thấy cập nhật của thread nền hoặc gặp data race. Dùng atomic, concurrent collection, volatile hoặc cơ chế đồng bộ phù hợp.

### Dùng Awaitility để đo performance chính xác

Polling không phải công cụ benchmark độ trễ chính xác. Dùng công cụ đo hiệu năng phù hợp; Awaitility phục vụ kiểm tra điều kiện cuối cùng.

### Chờ điều kiện thoáng qua

Polling có thể bỏ lỡ trạng thái chỉ tồn tại giữa hai lần kiểm tra. Hãy đợi terminal state, event bền vững hoặc dùng latch/future khi cần nhận đúng tín hiệu.

## 16. Checklist cho test có tác vụ bất đồng bộ

- [ ] Đã xác định test cần chờ command kết thúc hay tác vụ nền kết thúc.
- [ ] Đã chọn điều kiện có thể quan sát và thể hiện đúng kết quả mong đợi.
- [ ] Đã dùng timeout hữu hạn.
- [ ] Poll interval phù hợp với tải của dependency.
- [ ] Điều kiện polling chỉ đọc, không tạo side effect.
- [ ] Điều kiện và dữ liệu chia sẻ giữa thread có đồng bộ/visibility đúng.
- [ ] Chỉ bỏ qua exception tạm thời đã xác định.
- [ ] Có thông tin job/resource ID trong assertion hoặc alias.
- [ ] Với Spring Shell 3.4 interactive session, đã đợi output trên screen trước khi thao tác tiếp.
- [ ] Với Spring Shell 4.x, đã phân biệt sendCommand hoàn tất với công việc nền hoàn tất.
- [ ] Input bổ sung được mô phỏng bằng test input provider phù hợp.
- [ ] Đã dùng latch/future khi có tín hiệu hoàn tất trực tiếp.
- [ ] Đã cân nhắc fake clock/scheduler cho logic phụ thuộc thời gian.
- [ ] Không dùng Awaitility như công cụ benchmark.

## 17. Tự kiểm tra

**Câu 1.** Vì sao Thread.sleep(1000) không chứng minh tác vụ nền đã hoàn tất?

**Gợi ý trả lời:** Nó chỉ dừng test thread trong một giây. Tốc độ xử lý có thể thay đổi và test không kiểm tra trạng thái của tác vụ.

**Câu 2.** Khi nào nên dùng untilAsserted thay vì until?

**Gợi ý trả lời:** Khi cần chạy một hoặc nhiều assertion cho đến khi tất cả đạt, ví dụ kiểm tra trạng thái và số lượng bản ghi.

**Câu 3.** Trong Spring Shell 4.x, sendCommand trả về screen có nghĩa job nền đã hoàn tất không?

**Gợi ý trả lời:** Không. Nó xác nhận command đã thực thi và trả screen; nếu command chỉ khởi chạy job, test phải đợi trạng thái nghiệp vụ của job.

**Câu 4.** Vì sao lambda trong until không nên gọi mutation?

**Gợi ý trả lời:** Awaitility có thể gọi lambda nhiều lần; mutation có thể bị thực hiện lặp và làm thay đổi kết quả test.

**Câu 5.** Khi API cung cấp CompletableFuture, nên chờ gì?

**Gợi ý trả lời:** Chờ future bằng get với timeout hữu hạn hoặc kiểm tra trạng thái future; sau đó xác nhận kết quả.

**Câu 6.** Awaitility có tự bảo đảm thread safety cho biến được polling không?

**Gợi ý trả lời:** Không. Test và ứng dụng phải dùng atomic, volatile, concurrent collection hoặc cơ chế đồng bộ phù hợp.

**Câu 7.** Khi cần kiểm tra TTL, cách nào có thể tốt hơn việc chờ thật?

**Gợi ý trả lời:** Inject Clock hoặc Scheduler để test điều khiển thời gian và kiểm tra trước/sau mốc hết hạn.

## Kết luận

Test nên chờ điều kiện cần xác nhận thay vì đoán một khoảng thời gian đủ dài. Awaitility giúp đợi trạng thái, assertion hoặc output đạt được trong timeout hữu hạn. Spring Shell 3.4 dùng cách này để kiểm tra interactive session và output bất đồng bộ; Spring Shell 4.x có ShellTestClient để thực thi command và trả ShellScreen, nhưng tác vụ nền do command khởi chạy vẫn cần được kiểm tra riêng.

Khi có callback hoặc future, hãy chờ tín hiệu hoàn tất trực tiếp. Khi phải quan sát trạng thái bên ngoài, dùng polling có timeout, interval hợp lý và điều kiện chỉ đọc. Bảo đảm dữ liệu thread-safe, không bỏ qua exception quá rộng và cung cấp thông tin hữu ích khi timeout. Cách làm này giúp test nhanh hơn trên máy bình thường, ổn định hơn trên CI và chỉ thất bại khi điều kiện thực sự không đạt.

## Tài liệu tham khảo

- [Spring Shell 3.4.1 — Testing Basics](https://docs.spring.io/spring-shell/reference/testing/basics.html)
- [Spring Shell 4.0.3 — Testing](https://docs.spring.io/spring-shell/reference/testing.html)
- [Spring Shell 4.0.3 — ShellTestClient API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/test/ShellTestClient.html)
- [Spring Shell 4.0.3 — ShellInputProvider API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/test/ShellInputProvider.html)
- [Awaitility 4.x — Usage and polling](https://github.com/awaitility/awaitility/wiki/Usage)
