# Giữ tập khóa tag nhất quán cho các meter cùng tên

Trong Micrometer, tag biến một meter thành các chuỗi số liệu theo từng chiều phân loại. Với cùng một tên meter, các lần đăng ký cần tuân theo một **hợp đồng khóa tag ổn định**: cùng những khóa, cùng cách viết và cùng ý nghĩa. Giá trị của các khóa có thể thay đổi theo từng lần đo, nhưng cấu trúc khóa phải nhất quán ở mọi nhánh mã tạo ra meter đó.

Ví dụ, meter **orders.process** có thể phân loại theo **operation**, **result** và **channel**. Lần xử lý thành công và lần xử lý thất bại vẫn dùng đủ ba khóa này; chỉ giá trị **result** thay đổi. Nếu nhánh thành công chỉ gửi **result**, còn nhánh thất bại gửi thêm **exception**, cùng một tên meter sẽ có hai cấu trúc nhãn khác nhau. Một số registry hoặc backend chấp nhận các meter ID khác nhau, nhưng hệ thống như Prometheus yêu cầu các chuỗi trong cùng metric family có cùng tập label name. Schema không ổn định có thể làm đăng ký hoặc xuất dữ liệu thất bại, khiến truy vấn và dashboard khó duy trì.

## 1. Phân biệt tên meter, khóa tag và giá trị tag

Một meter được nhận diện bởi tên, loại meter và các tag đi kèm. Tên mô tả đại lượng được đo; khóa tag mô tả những chiều phân loại; giá trị tag xác định một nhóm cụ thể trong chiều đó.

| Thành phần | Ví dụ | Ý nghĩa |
|---|---|---|
| Tên meter | **orders.process** | Số lần xử lý đơn hàng |
| Khóa tag | **operation** | Loại thao tác |
| Giá trị tag | **create**, **cancel** | Nhóm thao tác cụ thể |
| Khóa tag | **result** | Kết quả xử lý |
| Giá trị tag | **success**, **failure**, **rejected** | Nhóm kết quả |
| Khóa tag | **channel** | Kênh tiếp nhận |
| Giá trị tag | **web**, **mobile**, **batch** | Nhóm kênh |

Có thể hình dung cấu trúc này như một bảng dữ liệu: tên meter là đại lượng, khóa tag là các cột phân loại, còn giá trị tag là dữ liệu của từng cột. Tập cột nên ổn định để các chuỗi số liệu có thể được so sánh và tổng hợp cùng nhau.

**Khóa tag** và **giá trị tag** có vai trò khác nhau:

- Khóa tag thuộc schema của meter. Với một tên meter, tập khóa phải được giữ cố định.
- Giá trị tag thay đổi theo hoạt động thực tế, nhưng nên lấy từ tập giá trị hữu hạn và có ý nghĩa.
- Thêm hoặc bỏ khóa ở một nhánh mã làm thay đổi schema.
- Thêm một giá trị mới vào khóa hiện có mở rộng số chuỗi thời gian, nhưng không thay đổi tập khóa.

Tập khóa là một tập hợp; thứ tự truyền các cặp tag không nên được dùng để biểu diễn ý nghĩa. Điều cần nhất quán là tên khóa chính xác và ý nghĩa của chúng.

## 2. Vì sao cùng tên meter cần cùng tập khóa?

Tên meter thường được dùng để nhóm dữ liệu thành một đại lượng logic. Khi các meter cùng tên có schema khác nhau, hệ thống nhận dữ liệu phải xử lý những chuỗi có cấu trúc không giống nhau.

Các hệ quả thường gặp gồm:

- **Không tương thích với backend**: một số backend yêu cầu cùng metric name phải có cùng tập label name. Prometheus là ví dụ điển hình.
- **Truy vấn phức tạp**: dashboard phải xử lý những chuỗi có các nhãn khác nhau, làm biểu thức truy vấn khó đọc và khó tái sử dụng.
- **Thiếu dữ liệu khi lọc**: truy vấn dựa trên một khóa chỉ tồn tại ở một nhánh có thể bỏ qua các chuỗi còn lại.
- **Khó đặt cảnh báo**: quy tắc cảnh báo dựa trên một chiều phân loại không có mặt đồng đều sẽ tạo kết quả thiếu nhất quán.
- **Khó bảo trì**: thay đổi một nhánh nghiệp vụ có thể vô tình làm thay đổi schema metrics của toàn ứng dụng.

Với cùng một tên, cũng cần giữ cùng ý nghĩa đo lường. Không nên dùng **orders.process** lúc thì đếm số đơn, lúc thì đo thời gian xử lý, hoặc dùng cùng tên cho hai đơn vị không tương thích. Nếu đại lượng, loại meter hoặc đơn vị thay đổi về bản chất, hãy thiết kế tên meter riêng phù hợp.

## 3. Thiết kế schema trước khi đăng ký meter

Trước khi viết instrumentation, hãy xác định tên meter và tập khóa tag cần thiết. Mỗi khóa cần trả lời một câu hỏi vận hành cụ thể.

Ví dụ với **orders.process**:

| Khóa tag | Ý nghĩa | Tập giá trị gợi ý |
|---|---|---|
| **operation** | Thao tác nghiệp vụ | **create**, **update**, **cancel** |
| **result** | Kết quả xử lý | **success**, **failure**, **rejected**, **unknown** |
| **channel** | Nguồn tiếp nhận | **web**, **mobile**, **batch**, **unknown** |
| **error_type** | Nhóm lỗi đã phân loại | **none**, **validation**, **dependency**, **timeout**, **other** |

Nếu cần dùng cả bốn chiều, mọi lần đăng ký **orders.process** đều phải cung cấp đủ bốn khóa. Khi không có lỗi, **error_type** có thể nhận giá trị **none**. Khi không xác định được kênh, dùng **unknown**. Những giá trị thay thế này phải được quy ước trước để tất cả call site sử dụng giống nhau.

Không nên thêm khóa chỉ khi có dữ liệu. Thay vào đó, giữ khóa hiện diện và biểu diễn trạng thái không áp dụng bằng một giá trị có nghĩa, chẳng hạn **none** hoặc **not_applicable**. Chọn một giá trị duy nhất cho mỗi tình huống và dùng nhất quán.

### Chọn khóa theo câu hỏi vận hành

Một khóa tag tốt giúp phân nhóm số liệu theo một chiều có ích:

- **operation** giúp so sánh các thao tác nghiệp vụ.
- **result** giúp tính tỷ lệ thành công và thất bại.
- **channel** giúp xác định kênh có tỷ lệ lỗi hoặc độ trễ cao.
- **error_type** giúp phân biệt nhóm lỗi mà không phải đưa thông điệp lỗi cụ thể vào metrics.

Không đưa các định danh của từng request, người dùng, đơn hàng hoặc chuỗi URL chứa ID vào tag. Các giá trị như request ID và order ID có thể hữu ích khi điều tra trace, nhưng không phù hợp làm chiều phân loại metrics vì số lượng giá trị có thể tăng theo lưu lượng.

## 4. Ví dụ lỗi: mỗi nhánh tạo một tập khóa khác nhau

Đoạn mã sau tạo meter cùng tên với cấu trúc tag không giống nhau:

~~~java
if (exception == null) {
    registry.counter(
        "orders.process",
        "result", "success"
    ).increment();
} else {
    registry.counter(
        "orders.process",
        "result", "failure",
        "exception", exception.getClass().getSimpleName()
    ).increment();
}
~~~

Nhánh thành công chỉ có khóa **result**. Nhánh thất bại có hai khóa **result** và **exception**. Tên meter giống nhau nhưng tập khóa khác nhau. Giá trị của **exception** còn phụ thuộc vào lớp exception thực tế; nếu ứng dụng có nhiều loại exception, số chuỗi có thể tăng và schema trở nên khó kiểm soát.

Một backend có thể từ chối meter thứ hai vì label name không khớp với metric family đã đăng ký. Backend khác có thể lưu được cả hai dạng, nhưng dashboard và truy vấn sẽ phải xử lý hai cấu trúc khác nhau. Cả hai đều là dấu hiệu instrumentation cần được chuẩn hóa.

## 5. Ví dụ đúng: mọi nhánh dùng cùng tập khóa

Có thể tạo một hàm chung để đăng ký meter, buộc mọi nhánh nghiệp vụ đi qua cùng schema:

~~~java
public final class OrderMetrics {

    private final MeterRegistry registry;

    public OrderMetrics(MeterRegistry registry) {
        this.registry = registry;
    }

    public void record(
            String result,
            String channel,
            String errorType) {

        registry.counter(
            "orders.process",
            "operation", "create",
            "result", normalizeResult(result),
            "channel", normalizeChannel(channel),
            "error_type", normalizeErrorType(errorType)
        ).increment();
    }

    private String normalizeResult(String value) {
        if ("success".equals(value) || "failure".equals(value)
                || "rejected".equals(value)) {
            return value;
        }
        return "unknown";
    }

    private String normalizeChannel(String value) {
        if ("web".equals(value) || "mobile".equals(value)
                || "batch".equals(value)) {
            return value;
        }
        return "unknown";
    }

    private String normalizeErrorType(String value) {
        if ("none".equals(value) || "validation".equals(value)
                || "dependency".equals(value) || "timeout".equals(value)
                || "other".equals(value)) {
            return value;
        }
        return "other";
    }
}
~~~

Mỗi lần gọi **record** đều đăng ký meter với các khóa **operation**, **result**, **channel** và **error_type**. Các hàm chuẩn hóa đưa dữ liệu đầu vào về tập giá trị đã quy định. Điều này giúp tránh việc một giá trị tùy ý từ exception, request hoặc dữ liệu bên ngoài trở thành tag.

Ví dụ cách sử dụng:

~~~java
try {
    orderService.create(command);
    orderMetrics.record("success", command.channel(), "none");
} catch (ValidationException exception) {
    orderMetrics.record("rejected", command.channel(), "validation");
} catch (TimeoutException exception) {
    orderMetrics.record("failure", command.channel(), "timeout");
} catch (RuntimeException exception) {
    orderMetrics.record("failure", command.channel(), "other");
    throw exception;
}
~~~

Cả ba nhánh đều dùng chung hàm ghi nhận. Khóa tag không phụ thuộc loại exception hoặc kết quả. Các giá trị **success**, **rejected**, **failure**, **validation**, **timeout** và **other** thuộc tập giá trị được kiểm soát.

Trong mã sản xuất, nên dùng enum hoặc kiểu dữ liệu miền nghiệp vụ cho các giá trị đã biết thay vì truyền chuỗi tùy ý. Hàm chuẩn hóa là lớp bảo vệ cuối cùng khi đầu vào đến từ nguồn không đáng tin cậy hoặc có thể thiếu.

## 6. Giá trị thay thế khi dữ liệu không có

Một số chiều phân loại không có giá trị trong mọi trường hợp. Ví dụ, một thao tác nội bộ có thể không có channel, hoặc một lần xử lý thành công không có lỗi.

Cách xử lý cần được quy định thống nhất:

| Tình huống | Giá trị tag nên dùng | Ghi chú |
|---|---|---|
| Không biết kênh tiếp nhận | **unknown** | Có thông tin về chiều nhưng chưa xác định được giá trị |
| Chiều không áp dụng | **not_applicable** | Không có ý nghĩa trong hoạt động này |
| Xử lý thành công, không có lỗi | **none** | Không có nhóm lỗi |
| Có lỗi nhưng chưa phân loại được | **other** | Có lỗi, nhưng không thuộc nhóm đã định nghĩa |
| Thiếu dữ liệu do lỗi đầu vào | **unknown** | Không tạo một schema riêng bằng cách bỏ khóa |

Không nên tùy tiện dùng lẫn **null**, chuỗi rỗng, **unknown**, **none** và **not_applicable** cho cùng một ý nghĩa. Các giá trị này có thể tạo thành các chuỗi riêng biệt, làm phân tán số liệu và gây nhầm lẫn khi truy vấn.

Cũng cần tránh biến giá trị thay thế thành nơi chứa nội dung tự do. Ví dụ, không dùng nguyên văn thông báo lỗi làm giá trị **error_type**. Hãy phân loại thông báo thành một nhóm hữu hạn như **validation**, **dependency**, **timeout** hoặc **other**.

## 7. Giữ khóa nhất quán giữa nhiều call site

Trong một ứng dụng, cùng meter có thể được ghi từ controller, service, consumer message hoặc tác vụ nền. Nếu mỗi nơi tự chọn khóa, schema sẽ dễ bị lệch.

Có thể áp dụng các quy tắc sau:

1. Đặt tên meter và tập khóa trong một tài liệu hoặc class quy ước chung.
2. Tập trung việc tạo meter vào component instrumentation hoặc hàm factory dùng chung.
3. Tạo hằng số cho tên meter và khóa tag để tránh lỗi chính tả.
4. Chuẩn hóa giá trị qua enum hoặc hàm phân loại có giới hạn.
5. Viết kiểm thử cho từng nhánh tạo meter để xác nhận tập khóa.
6. Khi thêm chiều mới, cập nhật đồng bộ mọi call site và đánh giá tác động đến backend, dashboard, truy vấn và cảnh báo.

Ví dụ khai báo hằng số:

~~~java
public final class OrderMetricNames {

    public static final String PROCESS = "orders.process";

    public static final String OPERATION = "operation";
    public static final String RESULT = "result";
    public static final String CHANNEL = "channel";
    public static final String ERROR_TYPE = "error_type";

    private OrderMetricNames() {
    }
}
~~~

Hằng số giúp các call site dùng cùng tên khóa. Tuy nhiên, chỉ tạo hằng số chưa đủ để bảo đảm schema nhất quán nếu từng nơi vẫn tự quyết định khóa nào được thêm vào. Tốt nhất là kết hợp hằng số với một API ghi nhận chung, trong đó mọi tham số bắt buộc đều được truyền vào.

## 8. Common tags và ảnh hưởng đến schema

Micrometer cho phép cấu hình common tags trên MeterRegistry. Những tag này được thêm vào các meter thuộc registry, thường dùng cho các chiều chung như service, environment hoặc region.

Ví dụ cấu hình trong Spring:

~~~java
@Bean
MeterRegistryCustomizer<MeterRegistry> commonTags(Environment environment) {

    return registry -> registry.config().commonTags(
        "service", environment.getProperty("spring.application.name", "application"),
        "environment", environment.getProperty("app.environment", "unknown")
    );
}
~~~

Các common tags tạo thành một phần của schema xuất dữ liệu. Vì vậy:

- Cấu hình common tags một cách tập trung, trước khi meter được đăng ký.
- Giữ cùng tập common tag keys giữa các registry xuất cùng một metric family.
- Không thêm một common tag chỉ trong một nhánh hoặc một instance nếu backend yêu cầu label schema đồng nhất.
- Không trùng khóa common tag với khóa do meter tự khai báo.
- Chỉ chọn những chiều chung thật sự cần thiết; mỗi chiều mới có thể nhân số chuỗi thời gian.

Trong môi trường nhiều instance, hãy xác định rõ tag nào là chiều dùng chung của ứng dụng và tag nào mô tả từng instance. Việc gắn định danh instance có thể cần thiết cho một số mục đích vận hành, nhưng phải cân nhắc số lượng instance, vòng đời triển khai và khả năng truy vấn của backend. Dù chọn cấu hình nào, các khóa vẫn phải ổn định trong phạm vi metric name.

## 9. Kiểm soát schema ở registry và backend

Thiết kế ở call site là lớp kiểm soát chính. Có thể bổ sung MeterFilter hoặc cơ chế kiểm tra của backend làm lớp bảo vệ để giới hạn số meter, loại bỏ tag không cần thiết hoặc từ chối một số cấu hình vượt giới hạn.

Các lớp kiểm soát có mục tiêu khác nhau:

| Lớp | Nhiệm vụ | Giới hạn |
|---|---|---|
| API instrumentation dùng chung | Bắt buộc các khóa và chuẩn hóa giá trị | Phụ thuộc mọi call site có dùng API chung hay không |
| Unit test | Phát hiện nhánh đăng ký meter thiếu hoặc thừa khóa | Chỉ bao phủ những nhánh được kiểm thử |
| MeterFilter | Giới hạn, bỏ hoặc điều chỉnh một số meter/tag theo cấu hình | Không thay thế thiết kế schema rõ ràng ở cấp nghiệp vụ |
| Registry/backend | Kiểm tra ràng buộc tên, kiểu và label của hệ thống nhận | Hành vi khác nhau giữa các implementation |

Không nên dựa vào backend để tự sửa một schema không nhất quán. Nếu backend từ chối dữ liệu, số đo có thể không được xuất. Nếu backend âm thầm chuẩn hóa hoặc bỏ một số tag, ý nghĩa dữ liệu cũng có thể bị thay đổi. Hãy giữ hợp đồng tag ngay từ nơi tạo meter và xác minh ở đầu ra thực tế.

## 10. Kiểm thử tập khóa tag

Có thể dùng SimpleMeterRegistry để tạo meter trong bộ nhớ và kiểm tra tất cả meter có cùng tên đều có cùng tập khóa.

~~~java
@Test
void metersWithSameNameUseTheSameTagKeys() {
    try (SimpleMeterRegistry registry = new SimpleMeterRegistry()) {

        registry.counter(
            "orders.process",
            "operation", "create",
            "result", "success",
            "channel", "web",
            "error_type", "none"
        ).increment();

        registry.counter(
            "orders.process",
            "operation", "create",
            "result", "failure",
            "channel", "batch",
            "error_type", "timeout"
        ).increment();

        Set<Set<String>> keySets = registry.getMeters().stream()
            .filter(meter ->
                "orders.process".equals(meter.getId().getName()))
            .map(meter -> meter.getId().getTags().stream()
                .map(Tag::getKey)
                .collect(Collectors.toCollection(TreeSet::new)))
            .collect(Collectors.toSet());

        assertEquals(
            Set.of(Set.of("channel", "error_type", "operation", "result")),
            keySets
        );
    }
}
~~~

Kiểm thử này gom các khóa của từng meter có tên **orders.process** thành một tập hợp, rồi xác nhận chỉ có đúng một schema. Nó sẽ phát hiện trường hợp một nhánh đăng ký meter với tập khóa khác. Trong dự án thực tế, nên đóng registry trong khối try-with-resources hoặc cấu hình cleanup của test để tài nguyên luôn được giải phóng kể cả khi assertion thất bại.

Ngoài kiểm thử tập khóa, nên kiểm tra:

- Tất cả giá trị tag đều thuộc tập giá trị được cho phép.
- Giá trị thiếu được thay bằng **unknown**, **none** hoặc **not_applicable** theo quy ước.
- Không có request ID, user ID, order ID hoặc thông báo lỗi tự do trong tag metrics.
- Common tags xuất hiện đồng nhất trên các meter cần so sánh.
- Registry đích có thể đăng ký và xuất các meter mà không báo lỗi schema.
- Dashboard và truy vấn vẫn hoạt động sau khi thêm hoặc thay đổi tag.

## 11. Khi cần thay đổi schema tag

Một khi dashboard, cảnh báo và truy vấn đã phụ thuộc vào metric name cùng tập khóa, việc thay đổi schema là một thay đổi hợp đồng dữ liệu. Ví dụ, thêm khóa **payment_method** vào **orders.process** cần được xem xét như một thay đổi có ảnh hưởng đến toàn bộ nơi tiêu thụ metric.

Trước khi triển khai, hãy xác định:

1. Khóa mới có trả lời câu hỏi vận hành thực sự cần thiết không?
2. Tập giá trị có hữu hạn và được kiểm soát không?
3. Mọi nơi tạo meter cùng tên đã được cập nhật chưa?
4. Các instance chạy song song trong giai đoạn rolling deployment có xuất schema khác nhau không?
5. Dashboard, truy vấn, cảnh báo và quy trình lưu trữ có cần cập nhật không?

Nếu backend yêu cầu label schema cố định, việc triển khai đồng thời phiên bản cũ và mới có thể làm cùng một metric name xuất ra hai tập khóa. Khi thay đổi không thể triển khai đồng bộ, hãy cân nhắc tạo metric name mới cho schema mới, chuyển dashboard và cảnh báo theo lộ trình, rồi ngừng metric cũ sau khi các consumer đã chuyển đổi. Không thêm một tag **schema_version** chỉ để che giấu việc các tập khóa khác nhau; khóa version cũng làm tăng số chuỗi và không giải quyết ràng buộc label name của backend.

## 12. Checklist cho mỗi meter name

Trước khi đưa meter vào sử dụng, hãy xác nhận:

- [ ] Tên meter biểu thị một đại lượng và ý nghĩa thống nhất.
- [ ] Các meter cùng tên có cùng loại đo lường và đơn vị tương thích.
- [ ] Tập khóa tag được định nghĩa rõ ràng và không thay đổi giữa các nhánh.
- [ ] Mọi call site dùng cùng cách viết và ý nghĩa của từng khóa.
- [ ] Giá trị tag lấy từ tập hữu hạn hoặc được chuẩn hóa về nhóm có giới hạn.
- [ ] Trường hợp thiếu hoặc không áp dụng có giá trị thay thế nhất quán.
- [ ] Không đưa định danh riêng của request, người dùng, đơn hàng hoặc thông báo lỗi tự do vào tag.
- [ ] Common tags được cấu hình tập trung và không xung đột với tag riêng.
- [ ] Unit test kiểm tra tập khóa của mọi meter cùng tên.
- [ ] Registry/backend đích chấp nhận schema và dữ liệu được xuất đúng.

Tập khóa tag nhất quán giúp một tên meter duy trì hợp đồng dữ liệu ổn định từ mã Java đến registry và hệ thống giám sát. Hãy thiết kế khóa trước, kiểm soát giá trị, dùng chung API ghi nhận và kiểm thử các nhánh nghiệp vụ. Nhờ đó, metrics có thể được tổng hợp, truy vấn và cảnh báo một cách đáng tin cậy khi ứng dụng phát triển.

