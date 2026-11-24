# Timer.Sample để tách mốc bắt đầu và kết thúc

## Khi thời điểm bắt đầu và kết thúc nằm ở hai vị trí khác nhau

Micrometer cung cấp **Timer** để đo thời lượng của một thao tác và số lần thao tác được ghi nhận. Với một đoạn mã ngắn, có thể dùng **Timer.record(...)** để đo thời gian thực thi ngay trong một khối lệnh. Tuy nhiên, trong ứng dụng thực tế, mốc bắt đầu và kết thúc của một thao tác đôi khi nằm ở hai vị trí khác nhau: một request bắt đầu trong filter rồi kết thúc ở tầng xử lý, một message được nhận rồi hoàn tất sau khi xử lý, hoặc một tác vụ bất đồng bộ chỉ kết thúc trong callback.

**Timer.Sample** giải quyết trường hợp này bằng cách tách việc bắt đầu đo khỏi việc chọn Timer và ghi nhận kết quả. Ứng dụng tạo sample tại thời điểm bắt đầu, giữ sample trong phạm vi của thao tác, rồi gọi **stop(timer)** khi thao tác kết thúc. Timer được chọn ở thời điểm stop, nên có thể quyết định tên meter hoặc tag dựa trên kết quả vừa biết được.

Đây là điểm hữu ích nhất của Timer.Sample: **mốc bắt đầu được ghi lại trước, còn Timer đích có thể được chọn sau**. Nhờ vậy, ứng dụng có thể đo cùng một luồng xử lý nhưng phân loại kết quả thành success, failure hoặc timeout mà không phải đoán kết quả từ đầu.

## Timer.Sample hoạt động như thế nào?

### Bắt đầu đo

Tạo sample bằng registry sẽ nhận phép đo:

~~~java
Timer.Sample sample = Timer.start(registry);
~~~

Lời gọi này lấy mốc thời gian bắt đầu từ clock của registry. Timer.Sample lưu thông tin cần thiết để tính khoảng thời gian đã trôi qua. Nó chưa ghi một phép đo vào Timer nào tại thời điểm này.

### Kết thúc và ghi vào Timer

Khi thao tác hoàn tất, truyền Timer đích vào **sample.stop(timer)**:

~~~java
Timer.Sample sample = Timer.start(registry);

processOrder();

Timer timer = registry.timer("orders.processing");
sample.stop(timer);
~~~

Tại thời điểm stop, Micrometer tính thời lượng đã trôi qua và ghi nhận một lần đo vào Timer được truyền vào. Timer nhận được count và tổng thời gian; nếu được cấu hình histogram hoặc percentile phù hợp, nó cũng có thể cập nhật dữ liệu phân phối tương ứng.

Cần phân biệt hai bước:

1. **start:** lưu mốc bắt đầu theo clock của registry.
2. **stop:** tính thời lượng và ghi nhận vào Timer đã chọn.

Nếu sample được tạo nhưng không bao giờ stop, phép đo đó không được ghi vào Timer. Vì vậy, mọi đường kết thúc của thao tác cần có cơ chế gọi stop, kể cả khi thao tác thất bại hoặc bị hủy.

### Dùng cùng một registry cho sample và Timer

Nên tạo sample từ registry quản lý Timer đích. Ví dụ, nếu sample bắt đầu từ một **MeterRegistry** được inject trong Spring Boot, Timer nhận ở stop cũng nên được đăng ký trên registry đó. Điều này giúp clock, cấu hình và đích xuất dữ liệu nhất quán.

Không tạo sample trên một registry no-op rồi kỳ vọng ghi vào một registry khác khi stop. Sample dùng clock của registry lúc bắt đầu; Timer đích quyết định nơi dữ liệu được ghi. Thiết kế đơn giản và dễ kiểm thử nhất là sử dụng cùng registry cho cả hai bước.

## Ví dụ cơ bản: đo một thao tác có start và stop tách rời

Giả sử một service nhận message, xử lý message rồi mới xác định được kết quả:

~~~java
Timer.Sample sample = Timer.start(registry);

// Bắt đầu phần công việc cần đo.
messageHandler.handle(message);

// Khi xử lý hoàn tất:
sample.stop(registry.timer("messaging.message.processing"));
~~~

Trong ví dụ này, sample có thể được lưu trong đối tượng đại diện cho lần xử lý message hoặc truyền qua các phương thức liên quan. Điều quan trọng là sample phải gắn với đúng một lần xử lý. Không dùng một biến sample dùng chung cho tất cả message vì các lần xử lý có thể chồng lấn hoặc chạy đồng thời.

Nếu start và stop nằm trong cùng một phương thức, Timer.record thường gọn hơn. Timer.Sample có giá trị khi hai mốc nằm ở những vị trí khác nhau, hoặc khi ứng dụng cần quyết định Timer đích sau khi đã biết kết quả.

## Chọn Timer sau khi biết kết quả xử lý

### Gắn tag outcome tại thời điểm stop

Một thao tác có thể kết thúc thành công hoặc thất bại. Nếu tag outcome chỉ biết được sau khi xử lý xong, Timer.Sample cho phép chọn meter ở cuối thao tác:

~~~java
Timer.Sample sample = Timer.start(registry);
String outcome = "success";

try {
    paymentService.charge(command);
} catch (RuntimeException ex) {
    outcome = "failure";
    throw ex;
} finally {
    Timer timer = Timer.builder("payment.processing")
        .description("Thoi gian xu ly thanh toan")
        .tag("outcome", outcome)
        .register(registry);

    sample.stop(timer);
}
~~~

Nếu xử lý thành công, sample được ghi vào Timer có tag **outcome=success**. Nếu phát sinh RuntimeException, catch cập nhật outcome thành failure, exception tiếp tục được ném ra, còn finally vẫn thực hiện stop và ghi nhận thời lượng vào Timer có tag **outcome=failure**.

Nhờ chọn Timer tại thời điểm kết thúc, ứng dụng không cần tạo một sample riêng cho mỗi kết quả. Cùng một khoảng thời gian được ghi vào đúng meter theo kết quả cuối cùng.

### Chỉ dùng tag có tập giá trị hữu hạn

Tag outcome nên có tập giá trị nhỏ và được kiểm soát, ví dụ:

- success
- failure
- timeout
- cancelled

Không đưa exception message, stack trace, request ID, user ID, order ID hoặc URL đầy đủ vào tag. Những giá trị này có thể khác nhau ở mỗi lần xử lý và làm cardinality tăng rất nhanh. Nếu cần lưu thông tin chi tiết về lỗi hoặc request, hãy dùng log hoặc trace; metrics chỉ nên giữ những chiều phân loại có giá trị tổng hợp.

Cũng nên thống nhất quy tắc phân loại. Nếu một timeout vừa được coi là failure vừa được gắn tag timeout ở một nơi khác, dashboard có thể đếm trùng hoặc khó đối chiếu. Hãy chọn một mô hình outcome rõ ràng, dùng cùng tập giá trị trên mọi instance.

### Tạo Timer một lần hay đăng ký khi stop?

Khi tag đã biết từ đầu, nên lấy Timer một lần rồi dùng Timer.record hoặc sample.stop với Timer đó. Khi tag chỉ biết ở cuối, có thể tạo hoặc lấy Timer tương ứng tại thời điểm stop. Micrometer định danh meter theo tên, loại và tag; các lần đăng ký cùng danh tính sẽ tham chiếu đến cùng meter trong registry.

Với một tập outcome hữu hạn, ứng dụng cũng có thể đăng ký trước các Timer tương ứng rồi chọn một Timer ở cuối:

~~~java
Timer successTimer = Timer.builder("payment.processing")
    .tag("outcome", "success")
    .register(registry);

Timer failureTimer = Timer.builder("payment.processing")
    .tag("outcome", "failure")
    .register(registry);

Timer.Sample sample = Timer.start(registry);

try {
    paymentService.charge(command);
    sample.stop(successTimer);
} catch (RuntimeException ex) {
    sample.stop(failureTimer);
    throw ex;
}
~~~

Cách này phù hợp khi tập kết quả nhỏ, ổn định và có thể chuẩn bị trước. Nếu cần xử lý thêm các đường kết thúc như timeout hoặc cancel, hãy bảo đảm mỗi đường chỉ gọi stop đúng một lần.

## Đảm bảo stop trên mọi đường kết thúc

### Dùng finally để không bỏ sót phép đo

Nếu chỉ gọi stop sau câu lệnh xử lý thành công, các exception sẽ khiến sample không được ghi. Đặt stop trong finally giúp thời lượng được ghi nhận cả khi thao tác kết thúc bất thường.

Ví dụ dùng cờ thành công:

~~~java
Timer.Sample sample = Timer.start(registry);
boolean success = false;

try {
    paymentService.charge(command);
    success = true;
} finally {
    Timer timer = Timer.builder("payment.processing")
        .tag("outcome", success ? "success" : "failure")
        .register(registry);

    sample.stop(timer);
}
~~~

Nếu thao tác ném exception, finally vẫn chạy và ghi nhận failure trước khi exception tiếp tục lan truyền. Cách này phù hợp khi mọi kết thúc không thành công đều được xếp vào một nhóm failure. Nếu nghiệp vụ cần phân biệt timeout, cancel và lỗi nghiệp vụ, hãy cập nhật outcome tương ứng trước khi rời khối try.

### Tránh ghi nhận hai lần

Một sample nên được quản lý như một phép đo có một điểm kết thúc. Không gọi stop trong cả catch lẫn finally cho cùng một luồng thực thi. Nếu đã stop ở catch, finally không được stop lại.

Cũng không nên chia sẻ cùng một sample cho hai thao tác độc lập. Mỗi sample đại diện cho một khoảng thời gian từ lúc start đến lúc stop. Nếu tái sử dụng hoặc gọi stop nhiều lần, ứng dụng có thể ghi nhiều quan sát không đúng với ý định đo lường.

Khi nhiều nhánh xử lý có thể cùng kết thúc một thao tác, chẳng hạn callback thành công và callback timeout chạy gần nhau, cần cơ chế bảo đảm chỉ một nhánh được quyền hoàn tất phép đo. Có thể dùng trạng thái hoàn tất nguyên tử hoặc cơ chế điều phối completion sẵn có của framework.

## Timer.Sample trong xử lý bất đồng bộ

### Kết thúc khi công việc thực sự hoàn tất

Trong xử lý bất đồng bộ, phương thức khởi chạy công việc có thể trả về ngay trong khi tác vụ vẫn đang chạy. Nếu stop sample ngay sau khi gọi phương thức submit, Timer chỉ đo thời gian đưa tác vụ vào hàng đợi hoặc khởi chạy tác vụ, không đo thời gian xử lý thực tế.

Cần giữ sample cùng với vòng đời của tác vụ và gọi stop trong callback hoàn tất:

~~~java
Timer.Sample sample = Timer.start(registry);

CompletableFuture<Result> future = service.processAsync(command);

future.whenComplete((result, error) -> {
    String outcome = error == null ? "success" : "failure";

    Timer timer = Timer.builder("service.async.processing")
        .tag("outcome", outcome)
        .register(registry);

    sample.stop(timer);
});
~~~

Trong ví dụ này, thời lượng bao gồm khoảng từ lúc bắt đầu gọi processAsync đến khi CompletableFuture hoàn tất. Nếu muốn chỉ đo phần xử lý sau khi tác vụ bắt đầu thực sự chạy, hãy tạo sample tại điểm worker bắt đầu thực thi thay vì lúc submit.

Cần xác định rõ ranh giới đo lường:

- **Thời gian chờ hàng đợi:** bắt đầu khi submit và kết thúc khi worker nhận việc.
- **Thời gian xử lý:** bắt đầu khi worker bắt đầu và kết thúc khi xử lý xong.
- **Thời gian end-to-end:** bắt đầu tại điểm tiếp nhận request/message và kết thúc khi toàn bộ luồng hoàn tất.

Có thể dùng các Timer riêng cho từng giai đoạn. Không nên gộp các khoảng thời gian khác ý nghĩa vào cùng một meter chỉ vì chúng cùng đo bằng millisecond hoặc second.

### Xử lý timeout và cancellation

Một tác vụ bất đồng bộ có thể hoàn tất thành công, thất bại, timeout hoặc bị hủy. Mỗi loại kết thúc cần được phân loại theo quy tắc nghiệp vụ. Với CompletableFuture, callback completion thường được gọi khi future hoàn tất bình thường hoặc bất thường; nếu timeout được biểu diễn bằng một exception hoặc thao tác cancel, cần ánh xạ trạng thái đó về outcome tương ứng.

Không để sample bị treo vô thời hạn nếu tác vụ có thể không phát callback hoàn tất. Hãy thiết kế timeout hoặc cancellation path để hoàn tất phép đo. Nếu có nhiều cơ chế completion cạnh tranh, bảo đảm stop chỉ được thực hiện một lần.

Nếu callback chạy trên thread khác, sample vẫn có thể được giữ và truyền đến callback để tính thời lượng. Không cần dùng ThreadLocal để lưu sample. ThreadLocal có thể gây lỗi khi tác vụ chuyển thread hoặc khi thread pool tái sử dụng thread cho nhiều tác vụ.

## Timer.Sample dùng clock đơn điệu

Timer.Sample đo khoảng thời gian đã trôi qua bằng clock của registry, thường dựa trên nguồn thời gian đơn điệu phù hợp để đo duration. Nó không nhằm lưu timestamp lịch, giờ bắt đầu theo múi giờ hay thời điểm kết thúc theo wall clock.

Clock đơn điệu tránh sai lệch do đồng hồ hệ thống bị chỉnh giờ trong lúc thao tác đang chạy. Khi đo elapsed time, điều cần biết là khoảng thời gian trôi qua, không phải hai mốc thời gian lịch.

Nếu cần ghi nhận thời điểm một sự kiện xảy ra, hãy dùng log, trace hoặc một trường timestamp phù hợp. Timer.Sample tập trung vào thời lượng và ghi kết quả đó vào Timer.

Không tự tính duration bằng cách lấy hai giá trị System.currentTimeMillis rồi ghi vào Timer nếu không có lý do đặc biệt. Ưu tiên Timer.Sample hoặc Duration/TimeUnit để Micrometer sử dụng clock và quy ước đo thời gian phù hợp.

## Timer.Sample và Timer.record: chọn cách nào?

| Tình huống | Cách nên dùng | Lý do |
|---|---|---|
| Đo một khối lệnh đồng bộ, start và stop cùng phạm vi | Timer.record(...) | Ngắn gọn, tự ghi nhận cả khi khối lệnh kết thúc bằng exception |
| Đo callable và lấy kết quả trả về | Timer.recordCallable(...) | Đo quanh lời gọi và giữ nguyên kết quả hoặc exception |
| Start và stop ở hai phương thức hoặc callback khác nhau | Timer.Sample | Có thể truyền sample theo vòng đời thao tác |
| Chỉ biết outcome hoặc tag sau khi xử lý xong | Timer.Sample | Chọn Timer đích khi gọi stop |
| Đo tác vụ bất đồng bộ | Timer.Sample | Giữ mốc bắt đầu đến callback hoàn tất |
| Đo nhiều giai đoạn riêng biệt | Nhiều Timer.Sample hoặc Timer tương ứng | Mỗi khoảng có ranh giới và ý nghĩa riêng |

Không cần dùng Timer.Sample cho mọi Timer. Nếu đoạn mã nằm gọn trong một khối lệnh, Timer.record thường dễ đọc và ít trạng thái cần quản lý hơn. Dùng Sample khi việc tách start/stop hoặc lựa chọn Timer sau khi biết kết quả đem lại lợi ích rõ ràng.

## Tích hợp Timer.Sample trong Spring Boot

Nên inject MeterRegistry qua constructor và tạo sample tại điểm bắt đầu thao tác. Ví dụ một service đo thời gian xử lý thanh toán:

~~~java
@Service
public class PaymentServiceMetrics {

    private final MeterRegistry registry;

    public PaymentServiceMetrics(MeterRegistry registry) {
        this.registry = registry;
    }

    public Receipt charge(PaymentCommand command) {
        Timer.Sample sample = Timer.start(registry);
        String outcome = "success";

        try {
            return performCharge(command);
        } catch (RuntimeException ex) {
            outcome = "failure";
            throw ex;
        } finally {
            Timer timer = Timer.builder("payment.processing")
                .description("Thoi gian xu ly thanh toan")
                .tag("outcome", outcome)
                .register(registry);

            sample.stop(timer);
        }
    }

    private Receipt performCharge(PaymentCommand command) {
        // Goi cong thanh toan va tra ve ket qua.
        return gateway.charge(command);
    }
}
~~~

Registry được Spring quản lý theo application context. Service không cần truy cập Metrics.globalRegistry, nhờ đó có thể thay registry trong kiểm thử và giữ cấu hình metrics tập trung.

Trong hệ thống nhiều instance, mọi instance nên dùng cùng tên meter, tập outcome, đơn vị và cấu hình histogram/SLO. Nếu tag khác nhau tùy instance hoặc một instance dùng outcome=error còn instance khác dùng outcome=failure, dashboard sẽ phải xử lý nhiều series không nhất quán.

## Histogram, percentile và SLO của Timer đích

Timer được chọn ở thời điểm stop vẫn có thể được cấu hình histogram, percentile hoặc SLO như Timer thông thường. Ví dụ:

~~~java
Timer timer = Timer.builder("payment.processing")
    .description("Thoi gian xu ly thanh toan")
    .tag("outcome", outcome)
    .publishPercentileHistogram()
    .serviceLevelObjectives(
        Duration.ofMillis(100),
        Duration.ofMillis(300),
        Duration.ofSeconds(1)
    )
    .register(registry);

sample.stop(timer);
~~~

Cấu hình phân phối phải nhất quán giữa các instance nếu cần tổng hợp histogram. Cũng cần cân nhắc số lượng outcome và các tag khác để không làm tăng cardinality quá mức. Một meter có nhiều tag kết hợp với histogram có thể tạo ra rất nhiều chuỗi dữ liệu ở backend.

Không cần bật percentile histogram chỉ vì đang dùng Timer.Sample. Sample chỉ quyết định cách đo khoảng thời gian và thời điểm ghi; khả năng thống kê phân phối đến từ cấu hình Timer và registry.

## Kiểm thử Timer.Sample

### Xác minh một sample tạo đúng một lần ghi

Có thể dùng SimpleMeterRegistry để kiểm tra sample ghi nhận vào Timer đích:

~~~java
SimpleMeterRegistry registry = new SimpleMeterRegistry();

Timer.Sample sample = Timer.start(registry);
Timer timer = Timer.builder("test.operation")
    .tag("outcome", "success")
    .register(registry);

sample.stop(timer);

assertThat(timer.count()).isEqualTo(1);
assertThat(timer.totalTime(TimeUnit.NANOSECONDS))
    .isGreaterThanOrEqualTo(0.0);
~~~

Kiểm thử này xác nhận stop ghi một observation vào Timer. Không nên phụ thuộc vào một thời lượng tối thiểu cụ thể trong kiểm thử đơn vị vì thao tác có thể hoàn tất rất nhanh.

### Xác minh tag được chọn sau khi xử lý

Có thể kiểm tra hai kết quả được ghi vào hai Timer khác nhau:

~~~java
SimpleMeterRegistry registry = new SimpleMeterRegistry();

Timer.Sample successSample = Timer.start(registry);
Timer successTimer = registry.timer(
    "payment.processing",
    "outcome",
    "success"
);
successSample.stop(successTimer);

Timer.Sample failureSample = Timer.start(registry);
Timer failureTimer = registry.timer(
    "payment.processing",
    "outcome",
    "failure"
);
failureSample.stop(failureTimer);

assertThat(registry.get("payment.processing")
    .tag("outcome", "success")
    .timer()
    .count()).isEqualTo(1);

assertThat(registry.get("payment.processing")
    .tag("outcome", "failure")
    .timer()
    .count()).isEqualTo(1);
~~~

Trong kiểm thử thành phần, nên bao phủ cả đường thành công, exception, timeout và cancellation. Với xử lý bất đồng bộ, cần chờ callback hoàn tất trước khi xác minh count. Có thể dùng clock giả lập của Micrometer trong kiểm thử cần xác minh chính xác duration, miễn là phiên bản thư viện và fixture kiểm thử hỗ trợ clock đó.

SimpleMeterRegistry kiểm tra hành vi ở lớp Micrometer. Nó không chứng minh exporter xuất đúng tên, histogram hoặc đơn vị ở backend. Với backend quan trọng, cần thêm kiểm thử tích hợp ở ranh giới exporter.

## Những sai lầm thường gặp

**Bắt đầu sample nhưng quên stop.** Không có lời gọi stop thì phép đo không được ghi vào Timer. Bảo đảm mọi đường kết thúc đều hoàn tất sample.

**Stop ngay sau khi submit tác vụ bất đồng bộ.** Khi đó chỉ đo thời gian gửi tác vụ, không đo thời gian xử lý thực tế. Hãy stop trong callback hoặc tại điểm công việc thực sự kết thúc.

**Dùng chung một sample cho nhiều request.** Các thao tác có thể chồng lấn và ghi sai thời lượng. Mỗi lần xử lý cần sample riêng.

**Gọi stop nhiều lần.** Một sample nên được hoàn tất đúng một lần. Điều phối các callback, timeout và cancellation để tránh ghi trùng.

**Chọn tag từ dữ liệu không giới hạn.** Exception message, request ID và user ID làm cardinality tăng mạnh. Chỉ dùng tag có tập giá trị hữu hạn.

**Dùng Timer.Sample khi Timer.record đã đủ.** Sample tạo thêm trạng thái cần quản lý. Với một khối lệnh đồng bộ, Timer.record thường rõ ràng hơn.

**Đo sai ranh giới nghiệp vụ.** Bắt đầu trước khi submit nhưng kết thúc khi worker bắt đầu sẽ đo thời gian chờ; bắt đầu khi worker chạy và kết thúc sau xử lý sẽ đo thời gian xử lý. Hãy đặt start/stop theo đúng câu hỏi cần trả lời.

**Dùng wall clock để tự tính duration.** Thay đổi giờ hệ thống có thể làm sai khoảng thời gian. Ưu tiên Timer.Sample hoặc API duration của Micrometer.

## Checklist thiết kế Timer.Sample

Trước khi đưa phép đo vào vận hành, hãy xác minh:

1. Mốc bắt đầu có đúng thời điểm cần đo không?
2. Mốc kết thúc có phản ánh lúc thao tác thực sự hoàn tất không?
3. Mọi đường thành công, exception, timeout và cancellation đều gọi stop không?
4. Mỗi thao tác có sample riêng và chỉ hoàn tất một lần không?
5. Timer đích có được chọn theo outcome đã chuẩn hóa không?
6. Tag có tập giá trị hữu hạn và cardinality được kiểm soát không?
7. Sample và Timer có dùng registry phù hợp và cùng cấu hình không?
8. Với tác vụ bất đồng bộ, sample có được giữ đến callback hoàn tất không?
9. Histogram và SLO có cần thiết, đồng thời nhất quán giữa các instance không?
10. Kiểm thử có xác nhận count, tag và các đường kết thúc không?

## Kết luận

Timer.Sample cho phép tách mốc bắt đầu đo khỏi mốc kết thúc và khỏi thời điểm chọn Timer đích. Cơ chế này phù hợp khi một thao tác đi qua nhiều tầng, hoàn tất trong callback bất đồng bộ hoặc chỉ xác định được outcome sau khi xử lý.

Hãy tạo sample từ registry phù hợp, giữ nó theo vòng đời của đúng một thao tác và gọi stop đúng một lần trên Timer đã chọn. Dùng finally hoặc cơ chế completion tương đương để không bỏ sót lỗi, giữ tag có cardinality thấp và đặt ranh giới đo lường đúng với nghiệp vụ. Khi start, stop và outcome được xác định rõ, Timer cung cấp số liệu thời lượng có ý nghĩa cho dashboard, SLO và cảnh báo.
