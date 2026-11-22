# Classifier và deterministic routing

Trong Spring Batch, Classifier là một abstraction dùng để chọn một kết quả dựa trên một đối tượng đầu vào. Khi xử lý batch, kết quả đó thường là một ItemWriter, ItemProcessor hoặc một chiến lược xử lý khác. Ví dụ, mỗi Order có thể được gửi tới writer theo loại đơn hàng, mỗi event có thể được xử lý theo subtype, hoặc mỗi record được phân tuyến theo tenant.

Deterministic routing nghĩa là cùng một item, trong cùng một bộ quy tắc và cùng một phiên bản cấu hình, luôn được đưa tới cùng một route. Tính ổn định này đặc biệt quan trọng khi chunk được retry hoặc Job được restart. Nếu quyết định route thay đổi giữa các lần xử lý, một record có thể được ghi vào nhiều nơi, bị bỏ sót hoặc không còn khớp với checkpoint và audit metadata.

Classifier nên tập trung vào việc đưa ra quyết định thuần, rõ ràng và có thể kiểm thử. Các side effect như ghi database, ghi file, gửi message hoặc gọi HTTP thuộc về component được chọn. Để routing đáng tin cậy, cần xác định route key, quy tắc mặc định, cách xử lý giá trị không hợp lệ, version của cấu hình và cách giữ nguyên quyết định qua retry/restart.

## 1. Classifier là gì?

Classifier là một strategy nhận một giá trị kiểu C và trả về một kết quả kiểu T. Trong Spring, abstraction này được biểu diễn bởi interface có một phương thức classify:

~~~java
public interface Classifier<C, T> {
    T classify(C classifiable);
}
~~~

Hai generic type có ý nghĩa:

- C là kiểu đầu vào mà classifier cần xem xét.
- T là kiểu kết quả được chọn từ đầu vào đó.

Ví dụ classifier nhận Order và trả về tên route:

~~~java
Classifier<Order, String> orderRoute =
        order -> order.isPriority()
                ? "PRIORITY"
                : "STANDARD";
~~~

Classifier có thể trả về một writer, processor, handler, enum, strategy hoặc một object cấu hình. Nó không bắt buộc phải trả về String. Việc chọn kiểu kết quả phụ thuộc component sử dụng classifier.

Trong Spring Batch, một trường hợp quen thuộc là ClassifierCompositeItemWriter: classifier nhận từng item và trả về ItemWriter phù hợp. Một số phiên bản Spring Batch cũng cung cấp composite processor dựa trên classifier để chọn ItemProcessor. Hãy xác nhận class và API có trong phiên bản dependency của dự án trước khi dùng.

## 2. Routing và xử lý item là hai trách nhiệm riêng

Routing trả lời câu hỏi item sẽ được xử lý ở đâu hoặc bởi chiến lược nào. Component được chọn mới thực hiện công việc.

~~~text
Input item
    |
    v
Normalize / derive route key
    |
    v
Classifier
    |
    +--> Route A --> Writer A
    |
    +--> Route B --> Writer B
    |
    +--> Route C --> Writer C
~~~

Ví dụ:
- Order thuộc kênh PRIORITY được ghi vào file ưu tiên.
- Order thuộc kênh STANDARD được ghi vào bảng thông thường.
- Event kiểu PaymentReceived được xử lý bởi payment processor.
- Record thuộc tenant cụ thể được ghi vào partition tương ứng.

Nếu classifier vừa quyết định route vừa thực hiện ghi dữ liệu, logic routing sẽ khó kiểm thử và có thể tạo side effect ngay cả khi chunk rollback. Giữ classifier tập trung vào quyết định giúp việc quan sát, thay đổi rule và kiểm thử dễ hơn.

## 3. Deterministic routing nghĩa là gì?

Một hàm routing có tính deterministic khi cùng một đầu vào và cùng một bộ quy tắc sẽ luôn trả về cùng một kết quả.

Ví dụ:

~~~java
OrderRoute classify(Order order) {
    return order.getAmount().compareTo(new BigDecimal("10000")) >= 0
            ? OrderRoute.HIGH_VALUE
            : OrderRoute.STANDARD;
}
~~~

Nếu amount của item không thay đổi và ngưỡng được giữ nguyên, route luôn giống nhau.

Ngược lại, các quy tắc sau có thể không deterministic:
- Chọn writer ngẫu nhiên.
- Dùng thời điểm hiện tại để quyết định route.
- Gọi một service ngoài có kết quả thay đổi giữa hai lần gọi.
- Dựa vào counter tăng dần trong singleton classifier.
- Dựa vào cấu hình có thể được cập nhật trong lúc Job đang chạy.
- Dựa vào thứ tự item nếu thứ tự đó không được bảo đảm khi restart.

Deterministic routing không có nghĩa mọi Job phải luôn dùng cùng một route mãi mãi. Một JobInstance mới có thể dùng một bộ quy tắc mới. Yêu cầu là trong một đơn vị xử lý logic, quyết định phải nhất quán theo contract đã chọn.

## 4. Vì sao tính deterministic quan trọng trong Spring Batch?

Spring Batch có retry ở cấp item/chunk và restart sau khi execution thất bại. Một item có thể được xử lý lại sau rollback hoặc sau khi mở lại JobInstance.

Giả sử lần đầu item 100 được route vào writer A, writer A ghi một side effect rồi một writer khác lỗi. Khi retry, classifier lại chọn writer B vì cấu hình ngoài đã thay đổi. Kết quả có thể là:
- Item 100 tồn tại ở cả A và B.
- Item 100 chỉ tồn tại ở A nhưng metadata cho rằng route B.
- Audit record ghi route khác với nơi dữ liệu thực sự được lưu.
- Restart không tiếp tục được output tương ứng với checkpoint cũ.

Vì vậy, classifier phải đưa ra kết quả ổn định trong phạm vi retry/restart. Nếu routing phụ thuộc rule có thể thay đổi, hãy version hóa hoặc chốt rule cho JobInstance.

## 5. Chọn route key ổn định

Một route key tốt nên dựa trên dữ liệu nghiệp vụ ổn định và có ý nghĩa rõ ràng.

Ví dụ:
- Order channel.
- Transaction type.
- Tenant ID.
- Country code đã chuẩn hóa.
- Event type.
- Product category.
- Business date hoặc batch ID.
- Một khóa partition được xác định trước.

Không nên dùng các thuộc tính không ổn định như:
- Thời điểm gọi classifier.
- Random UUID tạo mới mỗi lần classify.
- Số thứ tự item trong một thread nếu thứ tự không được cố định.
- Hash code của object mutable.
- Trạng thái bên ngoài có thể thay đổi giữa retry.

Ví dụ route theo enum:

~~~java
public enum OrderRoute {
    PRIORITY,
    STANDARD,
    INTERNATIONAL,
    REJECTED
}
~~~

Enum giúp giới hạn tập route và làm rõ contract. Khi route key được tạo từ nhiều field, nên chuẩn hóa chúng ở một bước riêng trước khi classifier dùng.

## 6. Chuẩn hóa dữ liệu trước khi phân loại

Dữ liệu đầu vào có thể khác nhau về chữ hoa/thường, khoảng trắng, mã quốc gia hoặc cách biểu diễn enum. Nếu classifier trực tiếp dùng giá trị thô, cùng một ý nghĩa nghiệp vụ có thể bị phân thành nhiều route.

Ví dụ chuẩn hóa country code:

~~~java
String normalizeCountry(String value) {
    if (value == null || value.isBlank()) {
        return "UNKNOWN";
    }

    return value.trim().toUpperCase(Locale.ROOT);
}
~~~

Dùng Locale.ROOT cho chuẩn hóa mã kỹ thuật để kết quả không phụ thuộc locale của máy chạy. Với dữ liệu có quy tắc nghiệp vụ riêng, dùng canonicalization phù hợp thay vì chỉ trim/uppercase.

Có thể chuẩn hóa trong ItemProcessor hoặc một mapper riêng:

~~~java
public record RoutedOrder(
        Order order,
        OrderRoute route) {
}

@Bean
ItemProcessor<Order, RoutedOrder> prepareRoute() {
    return order -> {
        String channel = normalizeChannel(order.getChannel());
        OrderRoute route = switch (channel) {
            case "P" -> OrderRoute.PRIORITY;
            case "I" -> OrderRoute.INTERNATIONAL;
            case "S" -> OrderRoute.STANDARD;
            default -> OrderRoute.REJECTED;
        };

        return new RoutedOrder(order, route);
    };
}
~~~

Khi route đã được xác định và lưu trong RoutedOrder, writer có thể dùng kết quả đó thay vì lặp lại logic chuẩn hóa. Nếu processor có thể chạy lại khi retry, dữ liệu và rule dùng để tính route vẫn phải ổn định.

## 7. Viết classifier thuần và không có side effect

Classifier nên hoạt động như một hàm quyết định:
- Nhận item hoặc route key.
- Đọc các field cần thiết.
- Áp dụng rule đã xác định.
- Trả về route hoặc strategy.
- Không ghi dữ liệu, gọi API hoặc thay đổi item.

Ví dụ:

~~~java
public class OrderClassifier
        implements Classifier<Order, OrderRoute> {

    @Override
    public OrderRoute classify(Order order) {
        if (order == null) {
            throw new IllegalArgumentException("Order must not be null");
        }

        if (order.isRejected()) {
            return OrderRoute.REJECTED;
        }

        if (order.isInternational()) {
            return OrderRoute.INTERNATIONAL;
        }

        if (order.isPriority()) {
            return OrderRoute.PRIORITY;
        }

        return OrderRoute.STANDARD;
    }
}
~~~

Logic trên có thứ tự ưu tiên rõ ràng. Nếu một Order vừa bị rejected vừa international, nhánh rejected thắng. Quy tắc precedence này là một phần của contract và cần được kiểm thử.

Không để classifier tự tăng counter để luân phiên writer A/B nếu route phải ổn định theo item. Nếu cần chia đều tải, hãy dùng một thuật toán phân phối xác định dựa trên key ổn định hoặc một cơ chế load balancing được thiết kế riêng cho mục tiêu đó.

## 8. Classifier phải xử lý đầy đủ các trường hợp

Một classifier nên có định nghĩa cho mọi input hợp lệ. Nếu có route không xác định, phải có chính sách rõ ràng.

Các lựa chọn thường gặp:
- Trả về default route.
- Trả về reject/quarantine route.
- Ném exception để làm Step thất bại.
- Ghi nhận lỗi phân loại ở một luồng kiểm soát riêng.

Ví dụ:

~~~java
OrderRoute classify(Order order) {
    if (order.getChannel() == null) {
        return OrderRoute.REJECTED;
    }

    return switch (order.getChannel()) {
        case PRIORITY -> OrderRoute.PRIORITY;
        case STANDARD -> OrderRoute.STANDARD;
        case INTERNATIONAL -> OrderRoute.INTERNATIONAL;
    };
}
~~~

Nếu route key là String, nên tránh dùng so sánh null hoặc string tùy tiện ở nhiều nơi. Chuẩn hóa và parse thành enum trước sẽ làm các nhánh rõ hơn.

Không trả null nếu consumer của classifier không quy định null có nghĩa gì. Một kết quả null có thể làm lỗi xảy ra sâu hơn ở composite writer và khó chẩn đoán hơn.

## 9. Xử lý route không được hỗ trợ

Khi một giá trị route mới xuất hiện, hệ thống cần hành vi dự đoán được. Ví dụ upstream gửi channel "EXPRESS" nhưng ứng dụng hiện chỉ hỗ trợ PRIORITY và STANDARD.

Có hai cách thiết kế thường gặp.

**Reject rõ ràng:**

~~~java
OrderRoute classify(String channel) {
    return switch (channel) {
        case "P" -> OrderRoute.PRIORITY;
        case "S" -> OrderRoute.STANDARD;
        default -> throw new UnsupportedOperationException(
                "Unsupported channel: " + channel);
    };
}
~~~

Cách này phù hợp khi route mới là lỗi cấu hình hoặc thay đổi contract cần dừng Job.

**Đưa vào quarantine:**

~~~java
OrderRoute classify(String channel) {
    return switch (channel) {
        case "P" -> OrderRoute.PRIORITY;
        case "S" -> OrderRoute.STANDARD;
        default -> OrderRoute.REJECTED;
    };
}
~~~

Cách này phù hợp khi nghiệp vụ cho phép tiếp tục xử lý các record khác và lưu record không nhận diện để điều tra. Cần ghi lý do reject và số lượng record bị cách ly để Job không che giấu chất lượng dữ liệu.

Không dùng default route một cách âm thầm nếu route đó có thể làm dữ liệu đi sai hệ thống. Default phải là một quyết định nghiệp vụ có chủ đích.

## 10. Routing bằng ClassifierCompositeItemWriter

Một ứng dụng có thể dùng ClassifierCompositeItemWriter để chọn writer theo từng item. Classifier nhận item và trả về delegate writer tương ứng.

Ví dụ:

~~~java
@Bean
ClassifierCompositeItemWriter<Order> orderWriterRouter(
        @Qualifier("priorityWriter") ItemWriter<Order> priorityWriter,
        @Qualifier("standardWriter") ItemWriter<Order> standardWriter) {

    ClassifierCompositeItemWriter<Order> composite =
            new ClassifierCompositeItemWriter<>();

    composite.setClassifier(order ->
            order.isPriority()
                    ? priorityWriter
                    : standardWriter);

    return composite;
}
~~~

Khai báo Step:

~~~java
@Bean
Step routeOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> reader,
        ClassifierCompositeItemWriter<Order> orderWriterRouter) {

    return new StepBuilder("routeOrdersStep", jobRepository)
            .<Order, Order>chunk(100, transactionManager)
            .reader(reader)
            .writer(orderWriterRouter)
            .build();
}
~~~

Composite chịu trách nhiệm gọi writer được chọn. Delegate thực hiện việc ghi. Nếu delegate là ItemStream, cần bảo đảm lifecycle của delegate được đăng ký với Step bằng cơ chế stream tương ứng; không giả định mọi wrapper tự động chuyển tiếp open, update và close.

## 11. Phân biệt routing với broadcast

ClassifierCompositeItemWriter chọn một delegate cho mỗi item. CompositeItemWriter thường gửi cùng chunk tới nhiều delegate theo thứ tự cấu hình.

| Yêu cầu | Cơ chế phù hợp |
|---|---|
| Item thuộc route A thì ghi writer A, route B thì ghi writer B | ClassifierCompositeItemWriter |
| Mọi item đều ghi database và audit file | CompositeItemWriter |
| Item thuộc route A phải ghi vào database và audit, route B chỉ ghi database | ClassifierCompositeItemWriter chọn CompositeItemWriter hoặc adapter cho route A |
| Xử lý khác nhau theo subtype trước khi ghi | Classifier kết hợp processor hoặc writer |
| Chia dữ liệu thành worker có lifecycle và checkpoint độc lập | Partitioning |

Không dùng broadcast composite cho bài toán chọn một đích, vì dữ liệu có thể bị ghi vào mọi delegate. Ngược lại, không dùng classifier khi yêu cầu là tất cả hệ thống nhận cùng một bản ghi.

## 12. Phân loại theo nhiều điều kiện và precedence

Classifier thường có nhiều điều kiện. Thứ tự kiểm tra ảnh hưởng kết quả nếu một item thỏa nhiều điều kiện.

Ví dụ:
1. Record bị đánh dấu invalid luôn vào reject route.
2. Record thuộc quốc tế vào international route.
3. Record ưu tiên vào priority route.
4. Các record còn lại vào standard route.

~~~java
OrderRoute classify(Order order) {
    if (!order.isValid()) {
        return OrderRoute.REJECTED;
    }
    if (order.isInternational()) {
        return OrderRoute.INTERNATIONAL;
    }
    if (order.isPriority()) {
        return OrderRoute.PRIORITY;
    }
    return OrderRoute.STANDARD;
}
~~~

Viết precedence dưới dạng rule rõ ràng và kiểm thử các trường hợp giao nhau. Không để thứ tự if/else trở thành một chi tiết vô tình mà không ai biết.

Nếu rule ngày càng phức tạp, tách thành policy object hoặc bảng rule được version hóa. Một classifier nhỏ gọi policy sẽ dễ đọc hơn một lambda chứa hàng chục điều kiện.

## 13. Deterministic routing khi dùng hash

Một cách phân phối item vào một số route cố định là dùng hash của key ổn định. Ví dụ phân chia customer vào một trong bốn bucket:

~~~java
int bucketFor(String customerId, int bucketCount) {
    return Math.floorMod(
            customerId.hashCode(),
            bucketCount);
}
~~~

Điều kiện để kết quả ổn định:
- customerId phải ổn định.
- Chuỗi phải được chuẩn hóa trước khi hash.
- bucketCount phải giữ nguyên trong phạm vi JobInstance.
- Thuật toán hash phải được giữ nguyên giữa các lần chạy cần restart.
- Không dùng hashCode của object mutable hoặc object không có contract ổn định.

Dùng bucketCount khác sẽ thay đổi route của phần lớn key. Vì vậy, không thay số partition giữa lúc restart cùng JobInstance nếu output hoặc checkpoint phụ thuộc route cũ.

Với yêu cầu phân phối lâu dài qua nhiều lần thay đổi số node, có thể cân nhắc consistent hashing hoặc bảng mapping bền vững. Không nên tự triển khai thuật toán phức tạp nếu một bảng phân công partition đơn giản đáp ứng yêu cầu.

## 14. Không dùng counter hoặc random cho routing cần restart

Một classifier dùng counter có thể trông giống load balancing:

~~~java
AtomicInteger counter = new AtomicInteger();

ItemWriter<Order> classify(Order order) {
    return counter.getAndIncrement() % 2 == 0
            ? writerA
            : writerB;
}
~~~

Nhưng kết quả phụ thuộc thứ tự và số lần classifier được gọi. Khi chunk retry hoặc Job restart, counter có thể bắt đầu từ giá trị khác; item có thể đi sang writer khác.

Random routing có cùng vấn đề. Nếu cần chia đều mà vẫn deterministic, dùng một key ổn định:

~~~java
ItemWriter<Order> classify(Order order) {
    int bucket = Math.floorMod(
            order.getCustomerId().hashCode(), 2);

    return bucket == 0 ? writerA : writerB;
}
~~~

Cách này đảm bảo cùng customer key đi vào cùng bucket khi thuật toán và số bucket giữ nguyên. Tuy nhiên, phân phối theo hash không đảm bảo cân bằng tải tuyệt đối. Nếu cần cân bằng tải động, phải chấp nhận và thiết kế rõ tính không deterministic hoặc lưu quyết định phân phối vào một registry bền vững.

## 15. Version hóa rule routing

Rule routing có thể thay đổi theo thời gian: ngưỡng số tiền, danh sách quốc gia, mapping tenant hoặc số partition. Nếu Job restart bằng rule mới, cùng một item có thể chuyển sang route khác.

Một cách kiểm soát là gắn version rule với JobInstance.

Ví dụ JobParameters:

~~~java
JobParameters parameters = new JobParametersBuilder()
        .addString("businessDate", "2026-11-15", true)
        .addString("routingRuleVersion", "v3", true)
        .toJobParameters();
~~~

Khi JobInstance được tạo, version được lưu cùng identifying parameters. Classifier hoặc policy loader sử dụng đúng version đó.

Một cách khác là lưu version trong Job ExecutionContext sau khi khởi tạo Job. Nếu restart, ứng dụng phải kiểm tra version hiện có và dùng lại cùng rule set.

Không tự động đọc "latest configuration" mỗi lần classifier được gọi. Nếu cấu hình đổi giữa các chunk, cùng Job có thể xử lý các record theo hai bộ rule khác nhau.

## 16. Giữ nguyên cấu hình khi restart

Restart cùng JobInstance có nghĩa là tiếp tục cùng một đơn vị công việc logic. Những yếu tố ảnh hưởng routing cần giữ nguyên:

- Route key và cách chuẩn hóa.
- Rule precedence.
- Mapping route tới delegate.
- Số bucket/partition nếu dùng hash.
- Phiên bản cấu hình.
- Danh sách tenant hoặc channel được hỗ trợ.
- Ý nghĩa của default/reject route.
- Schema và tên output của từng route.

Nếu không thể giữ nguyên cấu hình cũ, cần một kế hoạch migration có kiểm soát. Ví dụ tạo JobInstance mới để xử lý lại toàn bộ dữ liệu bằng rule mới, hoặc lưu quyết định route đã chốt vào staging table để restart đọc lại.

Không thay đổi routing rule âm thầm trong khi JobInstance cũ còn có thể restart.

## 17. Lưu route đã xác định khi rule không thể tái tạo

Một số quyết định route phụ thuộc vào dữ liệu bên ngoài hoặc quyết định nghiệp vụ được phê duyệt thủ công. Trong trường hợp đó, chỉ giữ rule version có thể chưa đủ.

Có thể lưu route vào staging table:

~~~text
batch_input
  item_id
  payload
  resolved_route
  routing_rule_version
  job_instance_id
~~~

Luồng xử lý:
1. Chuẩn bị input và tính route.
2. Lưu route đã xác định cùng item key.
3. Job xử lý các item từ staging.
4. Retry/restart đọc lại resolved_route.
5. Audit có thể tra route và rule version đã dùng.

Điều này làm quyết định route bền vững và độc lập với service ngoài tại thời điểm restart. Cần bảo đảm việc tạo staging data và JobInstance được liên kết nhất quán để không dùng nhầm mapping của batch khác.

## 18. Không để classifier gọi service ngoài theo từng item

Nếu classifier gọi HTTP hoặc database để tìm route cho mỗi item, Job có thể gặp:
- Latency cao.
- Service outage làm Step lỗi.
- Kết quả thay đổi giữa retry.
- Rate limit.
- Khó kiểm thử.
- Nhiều request trùng cho cùng key.

Nếu mapping nhỏ và ổn định, tải một lần khi Job bắt đầu và dùng immutable map trong Step. Nếu mapping lớn, có thể đọc từ bảng staging hoặc cache có version. Nếu service ngoài là nguồn quyết định chính thức, hãy chốt kết quả vào metadata bền vững trước khi writer thực hiện side effect.

Không thực hiện remote lookup từ classifier nếu cùng kết quả có thể được chuẩn bị trước bởi một Step hoặc processor chuyên biệt.

## 19. Null, dữ liệu lỗi và route fallback

Classifier cần xử lý rõ các trường hợp:
- Item null.
- Route key null.
- Mã route rỗng hoặc chỉ có khoảng trắng.
- Mã route không được hỗ trợ.
- Mapping không tồn tại.
- Delegate tương ứng chưa được cấu hình.
- Rule version không tồn tại hoặc không tương thích.

Có thể dùng một kết quả REJECTED hoặc UNKNOWN riêng:

~~~java
public enum Route {
    ACCEPTED,
    PRIORITY,
    STANDARD,
    REJECTED,
    UNKNOWN
}
~~~

UNKNOWN và REJECTED không nhất thiết cùng ý nghĩa. REJECTED có thể là kết quả nghiệp vụ đã biết; UNKNOWN có thể biểu thị cấu hình hoặc dữ liệu không nhận diện. Tách hai trạng thái giúp vận hành điều tra đúng nguyên nhân.

Nếu route không xác định là lỗi nghiêm trọng, fail Step thay vì silently fallback vào writer mặc định. Nếu business cho phép quarantine, ghi cả route key gốc và lý do vào reject output.

## 20. Transaction và side effect của route

Classifier chỉ chọn delegate; nó không tạo transaction phân tán. Các delegate được gọi trong write phase của chunk, nhưng khả năng rollback phụ thuộc resource và transaction manager.

Ví dụ:
- Hai delegate JDBC dùng cùng transaction manager và cùng transaction-bound DataSource có thể rollback cùng nhau.
- Một delegate ghi file và một delegate ghi database không có transaction nguyên tử chung mặc định.
- Một delegate gửi HTTP hoặc message có thể đã tạo side effect dù delegate sau thất bại.
- Hai database khác nhau cần cơ chế transaction riêng nếu yêu cầu atomicity.

Nếu route có external side effect, hãy cân nhắc:
- Idempotency key theo item/business key.
- Outbox table ghi trong transaction database.
- Staging output và publish sau commit.
- Retry có giới hạn và reconciliation.
- Lưu trạng thái đã gửi để tránh gửi lặp.

Không giả định rollback chunk sẽ xóa file hoặc thu hồi request đã gửi thành công.

## 21. Deterministic routing và retry

Trong retry, một item có thể được gọi lại nhiều lần. Classifier cần trả cùng route cho item đó.

Ví dụ route dựa trên field trong item:

~~~java
OrderRoute classify(Order order) {
    return order.getRiskLevel() == RiskLevel.HIGH
            ? OrderRoute.REVIEW
            : OrderRoute.AUTO_PROCESS;
}
~~~

Điều này deterministic nếu riskLevel là dữ liệu ổn định trong lần xử lý. Nếu riskLevel được truy vấn lại từ service thay đổi theo thời gian, kết quả có thể khác.

Nếu processor tạo RoutedOrder một lần rồi writer retry, cần xem xét framework có gọi lại processor trong từng fault-tolerance scenario hay không. Đừng giả định mọi object đã được route luôn được giữ nguyên trong mọi retry path. Cách chắc chắn hơn là để route dựa trên input immutable hoặc lưu quyết định route vào dữ liệu bền vững khi yêu cầu nghiệp vụ đòi hỏi.

Delegate writer cũng nên idempotent nếu có khả năng side effect được thực hiện trước khi exception xảy ra.

## 22. Deterministic routing và restart

Khi Job restart, classifier có thể được tạo lại cùng ApplicationContext hoặc trong một process mới. Vì vậy, không dựa vào field trong bộ nhớ để lưu quyết định duy nhất.

Cần tái tạo cùng route từ:
- Identifying JobParameters.
- Dữ liệu nguồn ổn định.
- Rule version được chốt.
- Mapping đã lưu trong Job ExecutionContext hoặc staging.
- Thuật toán và số bucket giữ nguyên.

Nếu output path hoặc writer state phụ thuộc route, tên writer và resource path cũng cần ổn định. Ví dụ mỗi route ghi một file theo JobInstance ID và route name, không tạo UUID mới mỗi lần launch.

Nếu rule đã thay đổi và không thể khôi phục version cũ, cần quyết định rõ: tiếp tục theo route đã lưu, tạo JobInstance mới, hoặc chạy quy trình migration. Không tự chọn rule mới rồi tiếp tục checkpoint cũ.

## 23. Routing và partitioning không giống nhau

Routing chọn handler/delegate cho item trong cùng Step. Partitioning tạo các StepExecution riêng, mỗi worker có ExecutionContext và lifecycle riêng.

| Tiêu chí | Classifier routing | Partitioning |
|---|---|---|
| Đơn vị phân loại | Từng item | Phạm vi dữ liệu hoặc partition |
| StepExecution | Thường cùng StepExecution | Mỗi worker có StepExecution riêng |
| Resource lifecycle | Delegate trong cùng Step | Worker có lifecycle riêng |
| Checkpoint | State của delegate trong Step | State theo worker StepExecution |
| Concurrency | Không tự tạo worker song song | Có thể chạy worker song song |
| Phù hợp | Chọn writer/processor theo item | Chia tập dữ liệu để xử lý độc lập |

Nếu cần một writer cho từng loại item, classifier phù hợp. Nếu mỗi tenant cần transaction, restart, concurrency và resource riêng, partitioning có thể phù hợp hơn.

Không tạo hàng nghìn writer trong classifier chỉ để giả lập partitioning. Hãy xem xét số lượng route, giới hạn file descriptor, connection pool và khả năng quản lý lifecycle.

## 24. Deterministic routing bằng consistent mapping

Với nhiều route hoặc shard, cần cân nhắc cách mapping key tới đích. Một phép modulo đơn giản:

~~~java
int shard = Math.floorMod(customerId.hashCode(), shardCount);
~~~

rất dễ dùng, nhưng khi shardCount thay đổi, phần lớn key có thể đổi shard.

Nếu hệ thống cần thêm/bớt node mà hạn chế di chuyển key, consistent hashing có thể giảm số key phải remap. Tuy nhiên, kết quả vẫn phụ thuộc:
- Thuật toán hash và seed.
- Danh sách node/route.
- Virtual node configuration.
- Canonical key format.
- Version của ring/mapping.

Lưu version của mapping trong JobParameters hoặc metadata để restart dùng đúng ring. Nếu routing phục vụ sharding database lâu dài, nên dùng thư viện/registry đã được kiểm chứng thay vì tự viết thuật toán hash ring sơ sài.

## 25. Logging và audit quyết định route

Khi một item được phân tuyến, có thể ghi nhận metadata đủ để điều tra:
- Job name.
- JobInstance ID và JobExecution ID.
- Step name.
- Item business key.
- Route được chọn.
- Routing rule version.
- Delegate name hoặc output resource.
- Lý do reject nếu có.

Không log toàn bộ payload nếu chứa thông tin cá nhân, credential hoặc dữ liệu nhạy cảm. Dùng business key đã được phép hoặc mã tham chiếu.

Có thể đếm số item theo route bằng StepExecution metrics hoặc custom listener/adapter. Metrics giúp phát hiện:
- Một route đột nhiên không có item.
- Một route nhận lượng item bất thường.
- Tỷ lệ reject tăng.
- Phân phối tenant lệch.
- Delegate có latency hoặc lỗi cao.

Không dùng item ID có cardinality rất lớn làm metric tag. Giữ route name và rule version ở mức cardinality có kiểm soát.

## 26. Kiểm thử classifier

Classifier nên được kiểm thử như một unit riêng. Test cần bao phủ các giá trị biên và các điều kiện giao nhau.

Ví dụ:

~~~java
@Test
void routesHighValueOrdersToReview() {
    OrderClassifier classifier = new OrderClassifier();

    Order order = orderWithRiskLevel(RiskLevel.HIGH);

    assertEquals(
            OrderRoute.REVIEW,
            classifier.classify(order));
}
~~~

Các test quan trọng:
- Mỗi route key hợp lệ chọn đúng route.
- Null và blank được xử lý theo contract.
- Route không hỗ trợ được reject hoặc fail đúng cách.
- Precedence giữa các điều kiện đúng.
- Cùng item cho cùng kết quả nhiều lần.
- Thay đổi thứ tự gọi classifier không làm thay đổi kết quả.
- Rule version khác nhau chỉ thay route theo mapping được định nghĩa.

Một property test có thể gọi classifier nhiều lần với cùng item và xác nhận kết quả không đổi. Test này không chứng minh mọi input deterministic nhưng giúp phát hiện counter/random state vô tình được dùng.

## 27. Kiểm thử retry và restart

Unit test classifier chưa đủ để chứng minh routing nhất quán trong Job thực tế. Cần integration test với JobRepository và delegate writer.

Các kịch bản:

| Kịch bản | Điều cần xác nhận |
|---|---|
| Nhiều route trong một chunk | Mỗi item tới đúng delegate |
| Retry chunk | Cùng item vẫn chọn cùng route |
| Writer lỗi sau side effect | Retry không tạo dữ liệu trùng ngoài chủ đích |
| Restart cùng JobInstance | Rule version và route giữ nguyên |
| Deploy phiên bản mới | Job cũ dùng rule tương thích hoặc fail có kiểm soát |
| Mapping route thiếu | Job reject hoặc fail rõ |
| Rule version không tồn tại | Không tự fallback sang latest |
| Hash partition | Cùng key vào cùng bucket khi version không đổi |
| Số bucket thay đổi | Job phát hiện mapping version khác |
| Multi-threaded Step | Classifier và delegate thread-safe |
| Partitioned Step | Worker dùng mapping và resource đúng partition |
| Audit | Route và rule version được ghi nhận chính xác |

Một integration test điển hình:
1. Launch Job với identifying parameters và routingRuleVersion cố định.
2. Xử lý một số chunk rồi cố ý làm writer thất bại.
3. Lưu lại route của các item đã xử lý và JobInstance ID.
4. Restart cùng JobInstance.
5. Xác nhận classifier dùng cùng rule version và item tiếp tục tới đúng delegate.
6. Kiểm tra output từng route không thiếu hoặc trùng item.
7. Thử launch JobInstance mới với version rule mới và xác nhận thay đổi route chỉ xảy ra theo contract.

## 28. Những lỗi thường gặp

**Classifier dùng random hoặc counter.** Retry/restart có thể đưa cùng item tới route khác.

**Dựa vào thời điểm hiện tại.** Cùng item có thể được phân loại khác khi xử lý lại.

**Đọc latest config ở mỗi lần classify.** Rule có thể đổi giữa các chunk của cùng JobInstance.

**Route key chưa chuẩn hóa.** Các biểu diễn khác nhau của cùng mã nghiệp vụ có thể vào route khác nhau.

**Không có default hoặc reject policy.** Giá trị mới có thể làm lỗi sâu trong writer hoặc bị bỏ qua.

**Classifier có side effect.** Retry có thể lặp side effect và làm quyết định khó kiểm thử.

**Dùng hashCode của object mutable.** Route có thể đổi sau khi field tham gia hash thay đổi.

**Thay bucket count khi restart.** Key có thể chuyển shard và không khớp checkpoint/output cũ.

**Không version hóa mapping.** Deployment mới có thể thay route của Job đang restart.

**Dùng classifier routing để thay partitioning.** Các route không tự có StepExecution và lifecycle độc lập.

**Cho rằng composite writer là distributed transaction.** Side effect bên ngoài có thể không rollback cùng database.

**Không kiểm thử restart.** Unit test route đúng nhưng Job thực tế có thể ghi trùng hoặc dùng nhầm delegate.

## 29. Quy trình thiết kế deterministic routing

Khi triển khai classifier trong Spring Batch, hãy thực hiện theo trình tự:

1. Xác định item type và các route hợp lệ.
2. Chọn route key dựa trên dữ liệu nghiệp vụ ổn định.
3. Chuẩn hóa key trước khi phân loại.
4. Viết classifier thuần, không side effect và có precedence rõ ràng.
5. Định nghĩa null, unknown, reject và default behavior.
6. Nếu rule thay đổi theo thời gian, version hóa rule và chốt version cho JobInstance.
7. Nếu route phụ thuộc dịch vụ ngoài, chuẩn bị hoặc lưu quyết định route bền vững.
8. Chọn ClassifierCompositeItemWriter khi mỗi item cần một delegate; dùng CompositeItemWriter khi cần broadcast.
9. Đăng ký đúng lifecycle cho các delegate ItemStream.
10. Giữ output path, writer name, mapping và số bucket ổn định qua restart.
11. Kiểm tra thread safety và cân nhắc partitioning nếu cần worker/resource độc lập.
12. Thiết kế idempotency hoặc outbox cho side effect ngoài transaction.
13. Ghi audit route và rule version với business key phù hợp.
14. Kiểm thử unit, retry, restart, rule migration và output thực tế.

Classifier cung cấp một điểm quyết định có thể thay thế và kiểm thử độc lập. Deterministic routing bảo đảm cùng item đi tới cùng đích trong cùng một bộ rule đã chốt, kể cả khi chunk retry hoặc Job restart. Khi route key ổn định, rule được version hóa, fallback rõ ràng và delegate có lifecycle/transaction phù hợp, hệ thống batch có thể phân tuyến dữ liệu mà vẫn giữ tính nhất quán và khả năng truy vết.

