# Ghi nhận trước khi có registry thành phần và việc thêm registry về sau

## Bối cảnh

Micrometer tách mã instrumentation khỏi hệ thống nhận metrics bằng abstraction **MeterRegistry**. Ứng dụng tạo **Counter**, **Gauge**, **Timer** hoặc **DistributionSummary** thông qua registry; registry chịu trách nhiệm lưu giữ hoặc chuyển phép đo đến backend như Prometheus, StatsD, Graphite hay nền tảng giám sát khác.

Trong một số kiến trúc, ứng dụng khởi tạo meter trước khi registry xuất dữ liệu sẵn sàng. Ví dụ, một thư viện dùng API metrics ngay khi được tạo, trong khi cấu hình exporter chỉ được hoàn tất sau đó; ứng dụng cũng có thể thêm backend thứ hai khi đang chạy hoặc chuyển đổi hệ thống giám sát theo từng giai đoạn.

Micrometer hỗ trợ tình huống này thông qua **CompositeMeterRegistry**. Composite registry cho phép đăng ký meter trước, sau đó thêm một hoặc nhiều registry thành phần. Tuy nhiên, cần hiểu chính xác điều gì xảy ra trong khoảng thời gian chưa có registry thành phần: **composite không lưu hàng đợi các lần ghi để phát lại về sau**. Các phép đo được thực hiện khi composite chưa có registry con sẽ không được ghi vào backend được thêm sau đó.

Đây là khác biệt quan trọng giữa việc tạo một meter và việc lưu giữ dữ liệu của meter. API có thể sẵn sàng trước backend, nhưng điều đó không đồng nghĩa mọi sự kiện đã xảy ra đều được bảo toàn.

## Vai trò của MeterRegistry và CompositeMeterRegistry

**MeterRegistry** là điểm đăng ký và truy cập các meter. Một registry cụ thể thường gắn với một cách lưu trữ hoặc xuất dữ liệu:

- **SimpleMeterRegistry** lưu số đo trong bộ nhớ của tiến trình, hữu ích cho kiểm thử hoặc tình huống không cần exporter.
- **PrometheusMeterRegistry** cung cấp dữ liệu theo định dạng để Prometheus scrape.
- Các registry khác có thể gửi dữ liệu theo giao thức push hoặc định dạng riêng của nền tảng.
- **CompositeMeterRegistry** chuyển tiếp meter và các lần ghi nhận đến những registry thành phần đã được thêm vào nó.

Composite registry là một registry điều phối. Bản thân nó không phải một backend lưu trữ bền vững. Khi có nhiều registry thành phần, cùng một meter có thể được chuyển tiếp đến từng registry; mỗi registry áp dụng quy tắc đặt tên, bộ lọc, đơn vị xuất và cách vận chuyển riêng.

Micrometer cũng cung cấp **Metrics.globalRegistry**, một composite registry dùng chung thông qua facade tĩnh **Metrics**. Các lời gọi như **Metrics.counter(...)** hoặc **Metrics.timer(...)** đăng ký meter trên global registry. Registry thành phần có thể được thêm vào global registry sau đó bằng **Metrics.addRegistry(...)**.

Cần phân biệt ba tình huống:

| Tình huống | Hành vi ghi nhận |
|---|---|
| Composite registry chưa có registry thành phần | Các meter vẫn có thể được tạo, nhưng phép ghi không được lưu hoặc đệm để phát lại |
| Composite registry đã có một hoặc nhiều registry thành phần | Các lần ghi được chuyển đến các registry thành phần tương ứng |
| Meter được tạo trực tiếp từ một registry no-op riêng biệt | Meter đó vẫn no-op; thêm registry vào một composite khác không làm meter đã tạo tự chuyển sang composite |

Điểm thứ ba đặc biệt quan trọng. Cơ chế thêm registry về sau chỉ có tác dụng với meter đã đăng ký trên chính **CompositeMeterRegistry** tương ứng, chẳng hạn **Metrics.globalRegistry**. Nếu ứng dụng giữ một meter từ một **NoopMeterRegistry** riêng biệt, việc thêm registry vào global registry không thay đổi meter đó.

## Ghi nhận trước khi có registry thành phần

### Composite rỗng không phải là bộ đệm

Khi composite chưa có registry con, ứng dụng vẫn có thể yêu cầu một meter từ composite. Đối tượng meter trả về thuộc composite, nhưng chưa có meter thành phần nào nhận phép ghi.

Ví dụ:

~~~java
CompositeMeterRegistry composite = new CompositeMeterRegistry();

Counter completed = composite.counter("jobs.completed");

completed.increment(); // Chưa có registry con: phép tăng không được lưu.

SimpleMeterRegistry simple = new SimpleMeterRegistry();
composite.add(simple);

completed.increment(); // Phép tăng này được chuyển đến registry simple.

double count = simple.get("jobs.completed")
    .counter()
    .count();
~~~

Ở ví dụ trên, giá trị trong registry **simple** là 1.0. Lần tăng trước khi gọi **composite.add(simple)** đã bị bỏ qua. Composite không giữ lại giá trị 1 để cộng vào registry mới.

Khi thêm registry thành phần, composite đăng ký các meter đã biết với registry mới. Những đối tượng meter lấy từ composite trước đó có thể tiếp tục được sử dụng; sau khi registry thành phần được thêm, các lần ghi tiếp theo sẽ được chuyển đến registry đó.

Vì thế, cần phân biệt:

- **Đăng ký meter:** tạo danh tính meter gồm tên, loại và các tag.
- **Ghi nhận phép đo:** tăng counter, ghi thời lượng hoặc ghi một giá trị phân phối.
- **Xuất dữ liệu:** registry thành phần cung cấp dữ liệu cho backend theo chu kỳ scrape hoặc push.

Đăng ký meter trước không có nghĩa là các phép ghi trước đó được lưu. Khi registry con xuất hiện, dữ liệu chỉ bắt đầu được ghi từ những lần quan sát tiếp theo.

### Điều gì xảy ra với từng loại meter?

Mức độ ảnh hưởng phụ thuộc ngữ nghĩa của meter:

| Loại meter | Trước khi có registry con | Sau khi thêm registry con |
|---|---|---|
| Counter | Các lần increment không được giữ lại | Counter thành phần bắt đầu nhận các lần increment mới |
| Timer | Các lần record thời lượng không được đệm | Các lần record tiếp theo được ghi vào timer thành phần |
| DistributionSummary | Các giá trị đã record không được phát lại | Các giá trị mới được ghi nhận và tạo phân phối từ thời điểm đó |
| Gauge | Không có backend đọc mẫu từ registry con | Registry mới có thể đọc giá trị hiện tại từ đối tượng hoặc hàm quan sát được đăng ký |

Gauge có điểm khác biệt: nó phản ánh trạng thái hiện tại, không phải lịch sử sự kiện. Nếu Gauge theo dõi một đối tượng vẫn tồn tại và giá trị của đối tượng đã thay đổi trong thời gian composite chưa có registry con, registry mới có thể đọc giá trị hiện tại ở lần scrape hoặc đọc tiếp theo. Nó không tái tạo lịch sử các trạng thái đã đi qua.

Ví dụ, Gauge theo dõi số tác vụ đang chờ. Nếu số tác vụ lần lượt là 2, 5 rồi 3 trước khi registry được thêm, backend chỉ có thể quan sát giá trị hiện tại mà supplier trả về sau khi registry bắt đầu thu thập. Nó không có chuỗi lịch sử 2, 5, 3.

Đối với Counter, Timer và DistributionSummary, các lần ghi trước khi có registry thành phần bị mất khỏi luồng metrics. Không nên xem composite rỗng như một hàng đợi tạm thời.

## Thêm registry thành phần về sau

### Dùng CompositeMeterRegistry trực tiếp

Có thể chủ động quản lý composite registry nếu ứng dụng muốn quyết định thời điểm thêm hoặc gỡ backend:

~~~java
CompositeMeterRegistry composite = new CompositeMeterRegistry();

Counter processed = Counter.builder("worker.messages.processed")
    .description("So message da xu ly")
    .register(composite);

// Các phép ghi ở thời điểm này chưa được xuất.
processed.increment();

SimpleMeterRegistry inMemory = new SimpleMeterRegistry();
composite.add(inMemory);

// Meter đã đăng ký trên composite được kết nối tới registry mới.
processed.increment();
~~~

Mẫu này hữu ích khi cần minh họa lifecycle hoặc viết kiểm thử cho hành vi thêm registry động. Trong ứng dụng thực tế, registry thành phần thường là exporter đã được cấu hình với endpoint, thông tin xác thực, chu kỳ xuất và các tùy chọn tương ứng.

Nếu cần nhiều backend, có thể thêm nhiều registry vào cùng composite:

~~~java
composite.add(prometheusRegistry);
composite.add(statsdRegistry);
~~~

Sau thời điểm này, các phép đo mới được chuyển đến cả hai registry. Tuy nhiên, composite không làm cho hai backend có cùng mô hình dữ liệu. Mỗi registry vẫn có thể áp dụng NamingConvention, MeterFilter, cách chuyển đổi histogram, quy tắc tag và đơn vị xuất riêng.

### Dùng global registry và facade Metrics

Với mã sử dụng facade tĩnh, registry thành phần được thêm vào global composite:

~~~java
Counter completed = Metrics.counter("jobs.completed");

// Nếu globalRegistry chưa có registry con, lần tăng này không được lưu.
completed.increment();

Metrics.addRegistry(prometheusRegistry);

// Meter đã đăng ký trên globalRegistry bắt đầu được chuyển tiếp.
completed.increment();
~~~

Có thể gỡ registry thành phần bằng:

~~~java
Metrics.removeRegistry(prometheusRegistry);
~~~

Sau khi gỡ, composite ngừng chuyển phép ghi mới đến registry đó. Nếu registry sở hữu tài nguyên nền như scheduler, kết nối hoặc publisher, cần quản lý việc đóng tài nguyên theo lifecycle của ứng dụng và cách registry được tạo. Không nên giả định thao tác remove luôn thay thế cho việc đóng registry.

Facade tĩnh tiện lợi cho thư viện hoặc mã không dễ nhận dependency qua constructor. Tuy nhiên, trạng thái global tồn tại xuyên suốt tiến trình, nên cần thận trọng với kiểm thử, nhiều application context trong cùng JVM và vòng đời của registry.

## Thời điểm thêm registry ảnh hưởng dữ liệu thế nào?

Hãy xem một tiến trình có ba mốc:

1. **T0:** ứng dụng tạo meter trên composite rỗng và bắt đầu ghi nhận sự kiện.
2. **T1:** exporter được cấu hình xong và registry thành phần được thêm vào composite.
3. **T2:** ứng dụng tiếp tục ghi nhận và backend bắt đầu scrape hoặc nhận dữ liệu.

Khoảng từ T0 đến T1 không có dữ liệu Counter, Timer hoặc DistributionSummary được lưu bởi registry thành phần. Sau T1, registry nhận các phép ghi mới. Nếu backend dùng pull, dữ liệu sẽ xuất hiện khi backend scrape sau đó; nếu backend dùng push, dữ liệu xuất hiện theo chu kỳ gửi của registry.

Với Counter, giá trị quan sát ở backend bắt đầu từ các phép tăng được nhận sau T1. Do đó, tổng số trong dashboard có thể thấp hơn tổng số sự kiện thực tế kể từ lúc tiến trình khởi động. Với Timer và DistributionSummary, phân phối cũng chỉ phản ánh các quan sát sau khi registry được kết nối.

Đây là một khoảng trống dữ liệu có thật. Nó không phải lỗi truy vấn và cũng không thể được sửa bằng cách đổi tên meter. Nếu cần số liệu lịch sử đầy đủ, cần nguồn dữ liệu khác có khả năng lưu giữ sự kiện hoặc trạng thái bền vững; Micrometer composite không phải hệ thống hàng đợi hay kho dữ liệu lịch sử.

Không nên phát lại toàn bộ sự kiện nghiệp vụ chỉ để làm đầy Counter sau khi thêm registry. Việc phát lại có thể làm tăng gấp đôi số liệu nếu một phần sự kiện đã được ghi ở backend khác hoặc được xử lý bởi tiến trình khác. Chỉ thực hiện backfill khi có thiết kế riêng, có nguồn dữ liệu chuẩn, quy tắc chống trùng và cơ chế nhập dữ liệu được backend hỗ trợ.

## Thêm registry trước khi ứng dụng bắt đầu ghi

Nếu muốn tránh khoảng trống metrics, thứ tự khởi tạo nên là:

1. Đọc cấu hình backend và thông tin kết nối.
2. Tạo registry thành phần.
3. Thêm registry vào composite hoặc hoàn tất cấu hình registry do framework quản lý.
4. Khởi tạo các thành phần nghiệp vụ có thể tạo meter.
5. Bắt đầu nhận request, chạy scheduler hoặc tiêu thụ message.

Thứ tự này đặc biệt quan trọng khi thư viện tạo meter trong constructor, khi listener bắt đầu xử lý ngay sau khi khởi tạo, hoặc khi scheduler có thể chạy tác vụ nền trước khi exporter sẵn sàng.

Nếu không thể đảm bảo thứ tự đó, cần ghi nhận rõ thời điểm bắt đầu thu thập và chấp nhận khoảng trống dữ liệu ở giai đoạn khởi động. Với số liệu có yêu cầu đầy đủ tuyệt đối, metrics không nên là nguồn dữ liệu duy nhất.

## Tích hợp trong Spring Boot

Trong Spring Boot, ứng dụng thường nhận **MeterRegistry** qua dependency injection. Các dependency Actuator, Micrometer và registry exporter, cùng cấu hình của phiên bản Spring Boot đang sử dụng, quyết định những bean registry nào được tạo và cách chúng được kết hợp.

Ví dụ, một thành phần nghiệp vụ nhận registry qua constructor:

~~~java
@Component
public class JobMetrics {

    private final Counter completed;

    public JobMetrics(MeterRegistry registry) {
        this.completed = Counter.builder("jobs.completed")
            .description("So job da hoan tat")
            .register(registry);
    }

    public void onCompleted() {
        completed.increment();
    }
}
~~~

Cách này giúp thành phần nghiệp vụ phụ thuộc vào abstraction MeterRegistry mà Spring cung cấp. Registry được cấu hình và quản lý theo lifecycle của application context. Khi ứng dụng có nhiều registry exporter, cấu hình tự động của Spring Boot có thể kết hợp chúng bằng composite tùy phiên bản và điều kiện classpath.

Không nên mặc định rằng mọi ứng dụng Spring Boot đều có cùng một registry mặc định. Kết quả phụ thuộc phiên bản Spring Boot, các starter/dependency được thêm, điều kiện auto-configuration và cấu hình loại trừ. Hãy kiểm tra bean MeterRegistry thực tế trong application context và cấu hình exporter tương ứng.

Nếu thành phần nghiệp vụ được khởi tạo trước khi registry thật được kết nối, cần xác minh nó đang nhận loại registry nào. Meter được tạo trên một composite có thể được chuyển tiếp khi registry con được thêm vào composite đó. Meter được tạo trực tiếp trên một NoopMeterRegistry riêng thì không tự động chuyển sang registry khác.

### Hạn chế dùng global static trong ứng dụng có dependency injection

Trong ứng dụng Spring Boot, nên ưu tiên inject MeterRegistry vào component hoặc constructor. Cách này giúp:

- Nhìn thấy rõ dependency metrics của thành phần.
- Dễ thay registry trong kiểm thử.
- Tránh trạng thái global dùng chung giữa các application context.
- Để Spring quản lý khởi tạo và đóng registry theo lifecycle.
- Dễ cấu hình chung tag, filter và exporter tại tầng cấu hình.

Global registry vẫn hữu ích cho thư viện cần tích hợp metrics mà không muốn buộc người dùng truyền registry qua mọi API. Nếu dùng cách này, thư viện nên ghi rõ cách ứng dụng thêm registry thành phần và thời điểm cần thực hiện.

## Thêm hoặc gỡ registry trong lúc ứng dụng đang chạy

Composite registry cho phép thay đổi tập registry thành phần trong thời gian chạy. Cách này có thể dùng khi chuyển đổi backend, bật thêm một đích xuất dữ liệu hoặc ngừng một exporter gặp sự cố.

Tuy nhiên, thao tác động cần có quy tắc lifecycle rõ ràng:

- **Thêm registry:** các meter đã đăng ký trên composite được đăng ký vào registry mới; các phép ghi tiếp theo được chuyển tiếp.
- **Gỡ registry:** các phép ghi tiếp theo không còn được gửi đến registry đã gỡ.
- **Meter mới:** tiếp tục được đăng ký trên composite và được chuyển đến các registry thành phần hiện tại.
- **Tài nguyên exporter:** cần được đóng đúng thời điểm sau khi ngừng sử dụng, tránh rò rỉ thread, scheduler hoặc kết nối.
- **Chuyển đổi backend:** trong giai đoạn xuất song song, cùng một phép đo có thể được gửi đến hai nơi; cần kiểm tra chi phí, cardinality và khả năng đối chiếu dữ liệu.

Không nên thay đổi registry thành phần liên tục theo từng request. Registry thường mang cấu hình và tài nguyên nền, nên thay đổi cần được điều phối ở cấp ứng dụng. Nếu dùng xuất kép trong giai đoạn migration, hãy đặt thời điểm bắt đầu và kết thúc rõ ràng, đồng thời xác định backend nào là nguồn dữ liệu chính sau khi chuyển đổi.

Cũng cần lưu ý rằng mỗi registry có thể áp dụng bộ lọc và quy ước tên riêng. Một meter bị MeterFilter từ chối ở registry này vẫn có thể được nhận ở registry khác. Vì thế, việc meter được tạo thành công trên composite không đảm bảo mọi backend đều lưu hoặc xuất meter đó.

## Kiểm thử hành vi thêm registry sau

Có thể dùng **SimpleMeterRegistry** làm registry thành phần để kiểm tra thời điểm dữ liệu bắt đầu được ghi nhận:

~~~java
CompositeMeterRegistry composite = new CompositeMeterRegistry();
Counter counter = composite.counter("test.events");

counter.increment(); // Chưa có registry con: không được lưu.

SimpleMeterRegistry child = new SimpleMeterRegistry();
composite.add(child);

counter.increment();

assertThat(child.get("test.events")
    .counter()
    .count()).isEqualTo(1.0);
~~~

Kiểm thử trên xác nhận phép tăng trước khi thêm registry không được phát lại. Phép tăng sau khi thêm registry được ghi nhận trong registry con.

Có thể mở rộng kiểm thử cho Timer và DistributionSummary để xác minh các lần record trước thời điểm kết nối không xuất hiện trong registry mới. Với Gauge, nên kiểm tra giá trị hiện tại được đọc sau khi registry được thêm, đồng thời tránh kỳ vọng backend có lịch sử các giá trị Gauge trước đó.

Nếu kiểm thử **Metrics.globalRegistry**, cần dọn dẹp registry đã thêm sau mỗi test:

~~~java
SimpleMeterRegistry registry = new SimpleMeterRegistry();

Metrics.addRegistry(registry);
try {
    Metrics.counter("test.global.events").increment();
    assertThat(registry.get("test.global.events")
        .counter()
        .count()).isEqualTo(1.0);
} finally {
    Metrics.removeRegistry(registry);
    registry.close();
}
~~~

Không để registry hoặc meter global của một test ảnh hưởng test khác. Với bộ kiểm thử song song, trạng thái global có thể gây ra kết quả không ổn định nếu nhiều test cùng thêm, gỡ hoặc ghi vào các meter có cùng danh tính.

Ngoài kiểm thử đơn vị, nên có kiểm thử tích hợp xác minh exporter thực sự hoạt động sau khi registry được thêm: endpoint scrape có meter, publisher gửi dữ liệu, tên và tag được chuẩn hóa như dự kiến, và lỗi kết nối được quan sát qua log hoặc cơ chế giám sát phù hợp.

## Những sai lầm thường gặp

**Cho rằng composite rỗng sẽ đệm dữ liệu.** Composite cho phép tạo meter trước registry thành phần nhưng không lưu các phép ghi để phát lại. Counter, Timer và DistributionSummary bị mất các quan sát trong khoảng này.

**Tạo meter từ NoopMeterRegistry rồi thêm registry vào global registry.** Meter đã tạo từ no-op registry riêng vẫn no-op. Muốn hỗ trợ thêm backend về sau, meter phải được đăng ký trên composite sẽ nhận registry thành phần.

**Thêm exporter sau khi scheduler hoặc listener đã chạy mà không đánh giá khoảng trống.** Các sự kiện trước thời điểm thêm registry không có trong dữ liệu xuất. Hãy cấu hình exporter trước khi bắt đầu workload nếu cần tránh khoảng trống.

**Cho rằng mọi meter cũ đều phải tạo lại sau khi thêm registry.** Meter được đăng ký trên composite có thể được kết nối tới registry thành phần mới. Có thể tiếp tục dùng handle composite cũ; các phép ghi sau khi kết nối được chuyển tiếp.

**Dùng metrics làm nguồn dữ liệu lịch sử duy nhất.** Composite registry không phải message queue hay kho lưu trữ bền vững. Số liệu cần đầy đủ phải có nguồn lưu trữ phù hợp với yêu cầu nghiệp vụ.

**Quên quản lý lifecycle khi gỡ registry.** Gỡ registry khỏi composite và đóng tài nguyên exporter là hai trách nhiệm cần được phối hợp. Nếu bỏ qua việc đóng tài nguyên, ứng dụng có thể giữ thread hoặc kết nối không cần thiết.

**Giả định các registry thành phần xuất dữ liệu giống nhau.** Composite chỉ chuyển tiếp phép đo. NamingConvention, MeterFilter, histogram, đơn vị, tag và cơ chế vận chuyển vẫn phụ thuộc từng registry.

## Checklist thiết kế

Trước khi dùng registry có thể được thêm về sau, hãy xác minh:

1. Meter được đăng ký trên CompositeMeterRegistry nào?
2. Composite hiện có registry thành phần nào và thời điểm chúng sẵn sàng là khi nào?
3. Có thành phần nào bắt đầu ghi metrics trước khi exporter được kết nối không?
4. Khoảng ghi nhận trước khi thêm registry có thể bị mất hay không?
5. Có cần cấu hình exporter trước khi khởi động listener, scheduler hoặc consumer không?
6. Nếu dùng Gauge, supplier có còn hợp lệ và phản ánh đúng trạng thái khi registry bắt đầu đọc không?
7. Các registry thành phần có cùng nhận meter sau khi áp dụng filter và naming convention riêng không?
8. Khi thêm hoặc gỡ registry, tài nguyên nền được khởi tạo và đóng như thế nào?
9. Kiểm thử có xác nhận dữ liệu trước và sau thời điểm thêm registry không?
10. Có nguồn dữ liệu bền vững khác nếu nghiệp vụ yêu cầu lịch sử đầy đủ không?

## Kết luận

Micrometer cho phép tạo meter trên CompositeMeterRegistry trước khi có registry thành phần và kết nối các registry về sau. Cơ chế này giúp tách thời điểm instrumentation khỏi thời điểm cấu hình exporter, đồng thời hỗ trợ xuất một meter đến nhiều backend.

Giới hạn cần nhớ là composite không đệm và phát lại các phép ghi đã xảy ra khi chưa có registry con. Counter, Timer và DistributionSummary chỉ được ghi từ lúc registry thành phần kết nối; Gauge có thể cung cấp trạng thái hiện tại khi backend bắt đầu đọc. Muốn tránh khoảng trống metrics, hãy khởi tạo registry trước khi ứng dụng bắt đầu xử lý workload, ưu tiên dependency injection trong Spring Boot và kiểm thử rõ lifecycle thêm/gỡ registry.
