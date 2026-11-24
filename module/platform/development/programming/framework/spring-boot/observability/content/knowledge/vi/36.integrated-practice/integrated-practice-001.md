# Tạo custom observation cho use case

Trong module **SPRING_BOOT_OBSERVABILITY**, Micrometer Observation cung cấp một API thống nhất để ghi nhận hoạt động của ứng dụng và kết nối dữ liệu đó với metrics, logs và distributed tracing. Spring Boot đã tích hợp instrumentation cho nhiều thành phần như HTTP server, HTTP client và một số thư viện truy cập dữ liệu. Tuy nhiên, các instrumentation kỹ thuật này không thể hiện đầy đủ ý nghĩa của nghiệp vụ. Một use case như tạo đơn hàng, giữ chỗ tồn kho hoặc xác nhận thanh toán cần có observation riêng để đội ngũ hiểu thao tác nghiệp vụ nào đang chạy và mất bao lâu.

Bài thực hành này xây dựng custom observation cho use case tạo reservation trong hệ thống inventory. Observation bao quanh ranh giới nghiệp vụ, dùng tên ổn định, gắn các thuộc tính có cardinality phù hợp và để ObservationRegistry chuyển dữ liệu đến các handler đã cấu hình. Cùng một cách làm có thể áp dụng cho các use case khác trong Spring Boot.

## 1. Chọn đúng ranh giới cần quan sát

Trước khi viết mã, cần xác định hoạt động nào thực sự có giá trị vận hành. Với luồng tạo reservation, request có thể đi qua các bước:

1. REST controller nhận lệnh tạo reservation.
2. Use case kiểm tra thông tin và điều phối nghiệp vụ.
3. Inventory gateway gọi kho dữ liệu hoặc một dịch vụ inventory khác.
4. Use case trả kết quả về controller.

Spring Boot có thể đã tạo observation cho HTTP request và HTTP client. Custom observation nên mô tả bước nghiệp vụ do ứng dụng sở hữu, ví dụ **inventory.reservation.create**. Nhờ vậy, trace có thể hiển thị cả request HTTP lẫn hoạt động tạo reservation bên trong request.

Không nên tạo custom observation chỉ để lặp lại toàn bộ thời gian của HTTP request. Hãy chọn ranh giới có ý nghĩa độc lập, có thể cần đo latency, phân loại kết quả hoặc điều tra lỗi. Nếu một use case gọi nhiều thành phần, observation nghiệp vụ có thể trở thành span cha cho các span kỹ thuật do client hoặc repository instrumentation tạo ra.

Một tên tốt cần giữ ổn định qua các lần triển khai. Dùng tên mô tả domain và hành động, không ghép ID của đơn hàng, SKU, URL hoặc dữ liệu request vào tên.

## 2. Chọn tên và thuộc tính cho observation

Với use case tạo reservation, có thể xác định các thông tin như sau:

| Thành phần | Giá trị ví dụ | Mục đích |
| --- | --- | --- |
| Observation name | inventory.reservation.create | Nhận diện loại hoạt động nghiệp vụ |
| Contextual name | create inventory reservation | Giúp trace dễ đọc |
| Low-cardinality key | inventory.channel | Phân nhóm theo web, mobile hoặc partner |
| High-cardinality key | order.id | Hỗ trợ tìm một lần thực thi cụ thể trong trace |

Observation name và contextual name có vai trò khác nhau. Observation name là định danh ổn định được dùng trong convention và các handler. Contextual name cung cấp mô tả dễ đọc hơn cho người xem trace.

Low-cardinality key-value phải có tập giá trị hữu hạn và được kiểm soát. Ví dụ, kênh bán hàng chỉ có các giá trị web, mobile và partner. Những thuộc tính này phù hợp để phân nhóm metrics. High-cardinality key-value như order.id có thể có rất nhiều giá trị; chỉ nên dùng khi tracing backend cần thuộc tính đó để điều tra một trace cụ thể. Không đưa ID động vào metric label.

Không đưa thông tin nhạy cảm như access token, mật khẩu, email, số điện thoại hoặc dữ liệu thanh toán vào observation. High-cardinality không có nghĩa là có thể lưu mọi dữ liệu tùy ý.

## 3. Chuẩn bị dependency và ObservationRegistry

Với ứng dụng Spring Boot, thêm Actuator để sử dụng các khả năng observability được Spring Boot tích hợp. Ví dụ Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
~~~

Để xuất metrics, ứng dụng cần thêm registry phù hợp với backend đang dùng, chẳng hạn Micrometer Prometheus registry. Để xuất distributed traces, cần tracing bridge và exporter tương ứng, chẳng hạn Micrometer Tracing bridge cho OpenTelemetry cùng cấu hình OTLP. Các dependency cụ thể phụ thuộc backend và phiên bản Spring Boot của dự án.

Trong cấu hình Spring Boot có Actuator, ObservationRegistry được cung cấp qua auto-configuration. Hãy inject registry do Spring quản lý vào use case. Không tạo một ObservationRegistry riêng cho từng request hoặc từng service, vì observation cần đi qua cùng hệ thống handler và context propagation của ứng dụng.

Ví dụ constructor injection:

~~~java
@Service
public class CreateReservationUseCase {

    private final ObservationRegistry observationRegistry;
    private final InventoryGateway inventoryGateway;

    public CreateReservationUseCase(
            ObservationRegistry observationRegistry,
            InventoryGateway inventoryGateway) {
        this.observationRegistry = observationRegistry;
        this.inventoryGateway = inventoryGateway;
    }
}
~~~

Các import trong ví dụ được lược bớt để tập trung vào phần observability. Trong mã dự án, dùng đúng package của domain model và gateway hiện có.

## 4. Tạo custom observation cho use case

Đầu tiên, định nghĩa dữ liệu đầu vào và kết quả của use case. Ví dụ này giả định domain đã có các kiểu dữ liệu tương ứng:

~~~java
public record ReservationCommand(
        String orderId,
        String sku,
        int quantity,
        SalesChannel channel) {
}

public record ReservationResult(
        String reservationId,
        ReservationStatus status) {
}
~~~

InventoryGateway đại diện cho cổng giao tiếp với kho dữ liệu hoặc inventory service:

~~~java
public interface InventoryGateway {

    ReservationResult reserve(
            String orderId,
            String sku,
            int quantity);
}
~~~

Tạo observation ngay tại ranh giới của use case:

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import java.util.Locale;
import org.springframework.stereotype.Service;

@Service
public class CreateReservationUseCase {

    private final ObservationRegistry observationRegistry;
    private final InventoryGateway inventoryGateway;

    public CreateReservationUseCase(
            ObservationRegistry observationRegistry,
            InventoryGateway inventoryGateway) {
        this.observationRegistry = observationRegistry;
        this.inventoryGateway = inventoryGateway;
    }

    public ReservationResult execute(ReservationCommand command) {
        return Observation
                .createNotStarted(
                        "inventory.reservation.create",
                        observationRegistry)
                .contextualName("create inventory reservation")
                .lowCardinalityKeyValue(
                        "inventory.channel",
                        command.channel().name().toLowerCase(Locale.ROOT))
                .highCardinalityKeyValue("order.id", command.orderId())
                .observe(() -> inventoryGateway.reserve(
                        command.orderId(),
                        command.sku(),
                        command.quantity()));
    }
}
~~~

Phần quan trọng là chuỗi tạo observation và gọi **observe**. API thực hiện vòng đời observation cho supplier: bắt đầu observation, mở scope trong khi chạy nghiệp vụ, ghi nhận lỗi nếu supplier ném exception, rồi dừng observation khi supplier hoàn tất. Nhờ đó, không phải tự viết try/finally để đóng observation trong trường hợp thông thường.

Tên **inventory.reservation.create** không thay đổi theo orderId hoặc sku. Kênh bán hàng được ghi như low-cardinality key-value vì tập giá trị của enum được kiểm soát. order.id được ghi như high-cardinality key-value để hỗ trợ điều tra trace nếu tracing handler và backend được cấu hình nhận thuộc tính này.

Ví dụ trên giả định SalesChannel là enum do ứng dụng kiểm soát. Dùng Locale.ROOT khi chuyển enum thành chữ thường để tránh kết quả phụ thuộc locale của máy chủ.

## 5. Observation hoạt động cùng các lớp kỹ thuật

Khi use case chạy trong scope của observation, các instrumentation được gọi bên trong có thể tiếp tục dùng context hiện tại. Nếu InventoryGateway dùng HTTP client đã được instrument, client observation có thể trở thành span con của observation nghiệp vụ. Nếu gateway truy cập database qua thư viện có instrumentation, span database cũng có thể xuất hiện trong cùng trace.

Một trace minh họa:

~~~text
HTTP POST /reservations
└── inventory.reservation.create
    └── HTTP inventory-service
        └── database query
~~~

Đây là quan hệ minh họa; span thực tế phụ thuộc các thư viện, handler và exporter đang được cấu hình. Nếu gateway gọi một dịch vụ chưa được instrument, custom observation vẫn ghi nhận thời gian tổng thể của use case, nhưng không tự tạo chi tiết cho từng thao tác bên trong gateway.

ObservationRegistry điều phối các ObservationHandler đã đăng ký. Một registry có thể có handler tạo meter, handler tạo span hoặc handler tùy chỉnh. Việc tạo observation bằng API không tự bảo đảm dữ liệu đã được xuất đến backend: ứng dụng phải có handler và exporter tương ứng.

Trong cấu hình có metrics handler, observation có thể được ánh xạ thành timer hoặc meter theo convention. Trong cấu hình tracing, observation có thể trở thành span. Logs có thể liên kết trace ID/span ID khi logging và tracing integration được bật. Từng tín hiệu có cách ánh xạ riêng, vì vậy cần kiểm tra đầu ra thực tế của hệ thống.

## 6. Xử lý kết quả nghiệp vụ và lỗi

Observation API tự ghi nhận exception phát sinh trong supplier được truyền cho observe và kết thúc vòng đời observation trước khi exception được truyền tiếp ra caller. Vì vậy, nếu InventoryGateway ném exception khi không thể truy cập inventory service, tracing handler có thể nhận được thông tin lỗi và span thể hiện trạng thái phù hợp theo cấu hình.

Không phải mọi kết quả nghiệp vụ không thành công đều là exception. Ví dụ, hết hàng có thể là một kết quả hợp lệ của use case với status REJECTED. Nếu cần phân tích các kết quả như SUCCESS, REJECTED hoặc RETRYABLE, hãy biểu diễn chúng bằng một low-cardinality key-value có tập giá trị hữu hạn. Chỉ thêm thuộc tính sau khi đã xác định được kết quả và trước khi observation dừng; trong trường hợp cần điều khiển chính xác thời điểm này, có thể quản lý vòng đời bằng start, openScope và stop trong try/finally.

Ví dụ về quy tắc phân loại:

| Kết quả | Giá trị low-cardinality gợi ý |
| --- | --- |
| Tạo reservation thành công | success |
| Không đủ tồn kho | rejected |
| Dịch vụ inventory tạm thời không khả dụng | unavailable |

Không đưa thông báo exception, stack trace, orderId hoặc SKU vào low-cardinality key-value. Những dữ liệu có giá trị biến thiên lớn sẽ làm cardinality tăng mạnh nếu được dùng làm metric label. Nội dung lỗi chi tiết nên được ghi qua logs có kiểm soát và span event/attribute phù hợp với chính sách dữ liệu.

## 7. Khi nào cần custom Observation.Context hoặc convention?

Ví dụ ở trên dùng API trực tiếp vì use case chỉ cần tên, contextual name và một số key-value đơn giản. Khi nhiều use case có cùng cấu trúc hoặc cần chia sẻ logic đặt tên, có thể xây dựng context và convention riêng.

Custom context phù hợp khi observation cần mang dữ liệu nghiệp vụ có cấu trúc trong suốt vòng đời, ví dụ loại reservation, kênh bán hàng và kết quả xử lý. Convention tập trung cách chuyển dữ liệu trong context thành observation name, contextual name, low-cardinality key-values và high-cardinality key-values.

Khi xây dựng convention:

- Chỉ đưa các thuộc tính có miền giá trị hữu hạn vào low-cardinality key-values.
- Giữ observation name ổn định, không phụ thuộc ID hoặc nội dung request.
- Dùng high-cardinality key-values có chọn lọc và tuân thủ chính sách dữ liệu.
- Dùng supportsContext để convention chỉ áp dụng cho đúng loại context của nó.
- Tái sử dụng convention khi nhiều use case có cùng ngữ nghĩa, tránh tạo một convention tổng quát khó kiểm soát.

Không cần tạo custom context hoặc convention chỉ để thay đổi một tên observation. Hãy bắt đầu bằng API trực tiếp, sau đó trích xuất convention khi có nhu cầu dùng chung rõ ràng.

## 8. Kiểm thử custom observation

Kiểm thử use case cần xác minh cả kết quả nghiệp vụ lẫn việc observation được tạo với tên dự kiến. Có thể dùng ObservationRegistry độc lập trong unit test và đăng ký một handler đơn giản để thu tên observation:

~~~java
ObservationRegistry registry = ObservationRegistry.create();
List<String> observationNames = new ArrayList<>();

registry.observationConfig().observationHandler(
        new ObservationHandler<Observation.Context>() {
            @Override
            public boolean supportsContext(Observation.Context context) {
                return true;
            }

            @Override
            public void onStart(Observation.Context context) {
                observationNames.add(context.getName());
            }
        });

CreateReservationUseCase useCase =
        new CreateReservationUseCase(registry, inventoryGateway);

useCase.execute(command);

assertThat(observationNames)
        .contains("inventory.reservation.create");
~~~

Đoạn mã là phần thân minh họa của một test JUnit; cần khai báo các fixture, mock InventoryGateway và import phù hợp trong dự án. Có thể mở rộng handler để kiểm tra low-cardinality key-values và xác minh observation được dừng sau khi use case hoàn tất.

Nên bổ sung các trường hợp:

1. Use case trả kết quả thành công và gateway được gọi đúng tham số.
2. Gateway ném exception; exception được truyền ra caller và observation vẫn kết thúc.
3. Gọi cùng use case với nhiều orderId và SKU; observation name vẫn giữ nguyên.
4. Thay đổi channel trong tập enum; giá trị low-cardinality phản ánh đúng kênh.
5. Kiểm tra ID động không xuất hiện trong low-cardinality key-values.

Unit test xác nhận ứng dụng tạo observation. Integration test mới xác nhận cấu hình handler và exporter thực sự gửi meter hoặc span đến backend. Khi chạy integration test, kiểm tra trace có span nghiệp vụ, span kỹ thuật có quan hệ cha-con hợp lý và các thuộc tính xuất hiện ở đúng loại tín hiệu.

## 9. Kiểm tra trong môi trường chạy

Sau khi tích hợp custom observation, thực hiện một request tạo reservation và kiểm tra lần lượt:

- **Metrics:** tìm timer hoặc meter tương ứng với convention của observation; kiểm tra tag chỉ chứa các giá trị có cardinality được kiểm soát.
- **Traces:** tìm span nghiệp vụ có tên ổn định và kiểm tra span con của HTTP client hoặc database nếu các thành phần đó đã được instrument.
- **Logs:** xác nhận log trong phạm vi xử lý có trace ID/span ID khi correlation được cấu hình.
- **Lỗi:** tạo một tình huống gateway thất bại trong môi trường kiểm thử và xác nhận span thể hiện lỗi, thời gian thực thi vẫn được ghi nhận.
- **Cardinality:** gửi nhiều request với orderId và SKU khác nhau; xác nhận số nhóm metric không tăng theo số ID.

Nếu metrics xuất hiện nhưng trace không có, kiểm tra tracing handler, bridge, exporter, endpoint và sampling probability. Nếu trace có span nghiệp vụ nhưng thiếu span con, kiểm tra instrumentation của gateway và context propagation. Nếu không có tín hiệu nào, kiểm tra ObservationRegistry có handler tương ứng và dependency/configuration đã được nạp hay chưa.

Sampling có thể khiến một số trace không được export dù observation vẫn chạy. Do đó, không dùng việc thiếu một trace đơn lẻ để kết luận custom observation không hoạt động. Hãy dùng test handler để kiểm tra vòng đời observation và metrics để theo dõi tổng thể; sau đó kiểm tra trace với tỷ lệ sampling phù hợp trong môi trường kiểm thử.

## 10. Các lỗi thiết kế thường gặp

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Đặt tên observation bằng orderId hoặc SKU | Tạo nhiều nhóm metric và khó tổng hợp | Dùng tên nghiệp vụ cố định |
| Đưa ID vào low-cardinality key | Cardinality tăng mạnh | Chuyển sang high-cardinality nếu trace thật sự cần |
| Tạo registry mới trong từng use case | Không dùng chung handler và context | Inject ObservationRegistry do Spring quản lý |
| Tạo observation trùng với HTTP instrumentation | Trace có span lặp và metrics khó diễn giải | Chọn ranh giới nghiệp vụ có ý nghĩa |
| Quên kết thúc observation khi tự quản lý lifecycle | Scope hoặc span có thể bị rò rỉ | Dùng observe hoặc try/finally với stop |
| Cho rằng tạo observation đồng nghĩa đã export | Không có dữ liệu ở backend khi thiếu handler/exporter | Kiểm tra handler, bridge và exporter |
| Dùng dữ liệu nhạy cảm làm attribute | Rủi ro lộ dữ liệu trong telemetry | Lọc, che hoặc loại bỏ dữ liệu nhạy cảm |

## 11. Hoàn thiện use case theo quy ước của nhóm

Khi đưa custom observation vào production, hãy thống nhất tên và key-value với các nhóm sở hữu service liên quan. Danh mục observation nên ghi tên, ý nghĩa nghiệp vụ, vị trí instrument, low-cardinality keys được phép và chủ sở hữu. Điều này giúp dashboard, alert và truy vấn tracing duy trì tính nhất quán qua nhiều phiên bản.

Một custom observation tốt có ba đặc điểm: mô tả đúng ranh giới nghiệp vụ, cung cấp thuộc tính đủ để phân tích và giữ cardinality trong giới hạn vận hành. Hãy bắt đầu từ use case cụ thể, dùng Observation API với registry được Spring Boot quản lý, rồi kiểm tra metrics, traces và logs ở đầu ra. Khi nhiều use case chia sẻ cùng cách biểu diễn, mới tách context hoặc convention dùng chung.
