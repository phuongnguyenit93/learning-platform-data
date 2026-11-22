# Phân biệt key-value có cardinality thấp và cardinality cao

## 1. Một thao tác cần hai mức thông tin

Giả sử ứng dụng xử lý đơn hàng. Người vận hành muốn biết:

- Kênh WEB và MOBILE khác nhau thế nào về số lần xử lý, độ trễ và tỷ lệ lỗi?
- Đơn hàng cụ thể `demo-102` đã đi qua những bước nào?

Câu hỏi thứ nhất cần **nhóm các lần xử lý** thành một số nhóm ổn định. Câu hỏi thứ hai cần **chi tiết của một lần xử lý**. Nếu đưa cả hai mức thông tin vào tag metrics theo cùng một cách, số nhóm có thể tăng theo số đơn hàng.

Micrometer Observation phân biệt hai nhóm key-value để biểu đạt mục đích này:

| Nhóm | Ý nghĩa trong thiết kế | Ví dụ |
| --- | --- | --- |
| Cardinality thấp (low cardinality) | Một tập giá trị nhỏ, có giới hạn và được kiểm soát, thích hợp để chia nhóm metrics | `channel=WEB`, `result=SUCCESS` |
| Cardinality cao (high cardinality) | Giá trị đa dạng hoặc có thể tiếp tục tăng theo dữ liệu thực tế, phục vụ chi tiết điều tra | `order.id=demo-102`, mã yêu cầu riêng |

**Key-value** là một cặp tên và giá trị, ví dụ key `channel` và value `WEB`. Trong ngữ cảnh metrics, các cặp này thường được gọi là tag hoặc label. “Thấp” và “cao” nói về **số giá trị khác nhau có thể xuất hiện**, không phải độ dài chuỗi.

Trong cách tích hợp Observation thông thường của Spring Boot 3.3, các key-value low-cardinality được dùng cho metrics và trace; các key-value high-cardinality chỉ đi theo trace trong cơ chế này. Việc tạo và xuất trace vẫn cần hệ thống tracing được cấu hình phù hợp. Xem [Observability của Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/observability.html).

## 2. Hiểu đúng cardinality trước khi chọn API

### 2.1. Đếm giá trị phân biệt

Với chuỗi giá trị của `channel`:

```text
WEB, WEB, MOBILE, WEB, MOBILE
```

có năm lần xuất hiện nhưng chỉ có **hai giá trị phân biệt**. Cardinality quan sát được trong dữ liệu này là 2.

Với `order.id`:

```text
demo-101, demo-102, demo-103, demo-104, demo-105
```

có năm giá trị phân biệt. Khi số đơn hàng tăng, tập giá trị có thể tiếp tục tăng; không có một danh sách nhỏ, ổn định mà ứng dụng cam kết giữ.

Một chuỗi UUID dài không phải nguyên nhân duy nhất gây cardinality cao. Mã ngắn `A1`, `A2`, `A3`… vẫn có thể tạo ra rất nhiều giá trị. Ngược lại, chuỗi `PAYMENT_AUTHORIZATION_REJECTED` khá dài nhưng có thể thuộc một tập nhỏ các mã kết quả đã định nghĩa.

### 2.2. Một ảnh chụp nhỏ chưa đủ kết luận

Hôm nay mới có ba người dùng không làm `user.id` trở thành một tag low-cardinality tốt. Cần đánh giá **miền giá trị tiềm năng và tốc độ sinh giá trị mới** trong suốt vòng đời ứng dụng.

Tương tự, nói “chỉ có hữu hạn giá trị” chưa đủ. Một danh mục có hàng triệu sản phẩm vẫn quá lớn cho nhiều mục tiêu phân nhóm metrics, dù về mặt toán học danh mục đó hữu hạn.

Không có một ngưỡng duy nhất như “dưới 100 luôn là thấp” dùng đúng cho mọi hệ thống. Quyết định còn phụ thuộc vào:

- Số tổ hợp với các tag khác.
- Số metric cùng mang tập tag đó.
- Số instance và cách hệ thống lưu trữ phân biệt instance.
- Cấu hình histogram, thời gian lưu và chi phí truy vấn.
- Câu hỏi vận hành thực sự cần trả lời.

### 2.3. API là lời khai báo của người viết mã

`lowCardinalityKeyValue` không kiểm tra nội dung rồi tự xác minh rằng giá trị có cardinality thấp. Nếu đưa mã đơn hàng vào đó, thư viện vẫn có thể dùng mã ấy làm một chiều phân nhóm metrics.

`highCardinalityKeyValue` cũng không phải bộ phát hiện hay cơ chế mã hóa dữ liệu. Nó khai báo cách phân loại metadata cho các thành phần xử lý phù hợp. Người viết instrumentation chịu trách nhiệm chọn đúng nhóm.

Tài liệu [Micrometer Observation 1.13](https://docs.micrometer.io/micrometer/reference/1.13/observation/introduction.html) dùng đường dẫn HTTP có mã thực thể và đường dẫn mẫu để minh họa sự khác nhau giữa miền giá trị tăng theo dữ liệu và miền giá trị được giới hạn.

## 3. Vì sao quyết định này ảnh hưởng trực tiếp đến metrics?

### 3.1. Mỗi tổ hợp tag tạo một danh tính đo riêng

Xét metric `order.lookup`. Với tag `channel`, hai tổ hợp có thể là:

```text
order.lookup{channel=WEB}
order.lookup{channel=MOBILE}
```

Hai lần gọi WEB có thể cùng đóng góp vào một timer WEB. Thêm `order.id` vào tag làm danh tính trở thành:

```text
order.lookup{channel=WEB, order.id=demo-101}
order.lookup{channel=WEB, order.id=demo-102}
order.lookup{channel=MOBILE, order.id=demo-103}
```

Đây là cách viết minh họa danh tính, không phải định dạng xuất bắt buộc của mọi backend. Với metrics, tên và tập tag xác định các nhóm đo riêng. Nếu ID thay đổi liên tục, ứng dụng và hệ thống lưu trữ phải quản lý nhiều nhóm nhỏ thay vì một số nhóm tổng hợp hữu ích.

Tác động có thể xuất hiện ở nhiều nơi: bộ nhớ của registry, kích thước dữ liệu xuất, số chuỗi được lưu, chỉ mục truy vấn và độ phức tạp của dashboard. Việc query tổng hợp lại sau đó không làm chi phí tạo và lưu các chuỗi chi tiết trước đó biến mất.

Prometheus cũng lưu ý rằng mỗi tổ hợp label riêng tạo ra một chuỗi thời gian riêng, và tránh các chiều như user ID hoặc email. Xem [hướng dẫn đặt metric và label](https://prometheus.io/docs/practices/naming/).

### 3.2. Các chiều kết hợp theo tích, không theo tổng

Giả sử một metric có:

| Tag | Số giá trị tối đa đã thiết kế |
| --- | ---: |
| `channel` | 4 |
| `result` | 3 |
| `region` | 5 |

Số tổ hợp lý thuyết tối đa là:

```text
4 × 3 × 5 = 60
```

Số tổ hợp thực tế có thể ít hơn nếu một số kết hợp không bao giờ xảy ra. Đây là giới hạn dựa trên giả định miền giá trị đã biết, không phải lời khẳng định ứng dụng luôn tạo đúng 60 meter.

Nếu thêm một tag có 100.000 giá trị và các tổ hợp tương ứng đều xuất hiện, giới hạn lý thuyết trở thành:

```text
60 × 100.000 = 6.000.000
```

Với `order.id` duy nhất toàn hệ thống, không nhất thiết mỗi ID xuất hiện cùng mọi tổ hợp của ba tag còn lại. Khi đó công thức tích có thể phóng đại số tổ hợp thực. Tuy nhiên, nó cho thấy vì sao phải xem tương quan và **đếm tổ hợp thực tế**, đồng thời vẫn đánh giá nguy cơ tăng không giới hạn.

Một tag riêng lẻ có vẻ nhỏ cũng có thể tốn kém khi kết hợp với nhiều tag nhỏ khác.

### 3.3. Meter và số chuỗi xuất ra không luôn bằng nhau

Một timer có thể xuất nhiều loại thống kê. Với histogram cổ điển kiểu Prometheus, ngoài các bucket còn có tổng và số lần đo; vì vậy một tổ hợp tag có thể ứng với nhiều chuỗi xuất ra.

Ví dụ giả định có 12 bucket hữu hạn, một bucket `+Inf`, một chuỗi sum và một chuỗi count: riêng nhóm thống kê đó đã có 15 chuỗi cho mỗi tổ hợp tag. Với 60 tổ hợp là 900 chuỗi; nếu backend phân biệt 20 instance có cùng các tổ hợp, con số minh họa thành 18.000.

Ví dụ này chỉ tính những thành phần đã nêu, không bao gồm thống kê bổ sung; không áp nguyên hệ số 15 cho native histogram hoặc mọi kiểu xuất OTLP. Điều cần giữ là **chi phí phân nhóm có thể được nhân thêm bởi cách biểu diễn thống kê**. Xem [histogram và percentile của Micrometer 1.13](https://docs.micrometer.io/micrometer/reference/1.13/concepts/histogram-quantiles.html).

## 4. Hai nhóm key-value đi đâu trong Observation?

### 4.1. Context giữ metadata, handler quyết định cách sử dụng

Một observation có ngữ cảnh `Observation.Context`. Các thành phần xử lý (handler) phản ứng với vòng đời bắt đầu, lỗi, kết thúc hoặc các sự kiện khác.

Có thể hình dung luồng tiêu thụ thông thường:

```text
Observation.Context
├── Low-cardinality key-values
│   ├── thành phần metrics -> tag của meter
│   └── thành phần tracing -> thuộc tính span
└── High-cardinality key-values
    └── thành phần tracing -> chi tiết span
```

`ObservationRegistry` quản lý các handler và cấu hình observation; `MeterRegistry` quản lý meter. Không có tracing handler và exporter phù hợp thì thêm high-cardinality metadata chưa đủ để có một trace ở hệ thống bên ngoài.

Một handler tùy biến vẫn có thể đọc metadata và dùng theo cách riêng. Vì thế quy tắc phân loại không phải ranh giới bảo mật ngăn tuyệt đối mọi mã tùy biến chuyển high-cardinality sang metrics. Ví dụ trong bài kiểm chứng hành vi của `DefaultMeterObservationHandler`, thành phần metrics chuẩn đang dùng.

Cơ chế context và handler được giải thích trong [Observation Components 1.13](https://docs.micrometer.io/micrometer/reference/1.13/observation/components.html).

### 4.2. Đặt đúng nhóm không đồng nghĩa dữ liệu đã được bảo vệ

`highCardinalityKeyValue("token", token)` vẫn có thể đưa bí mật vào hệ thống trace. Đây không phải cách ẩn token khỏi hệ thống quan sát.

Cần tách hai câu hỏi:

1. Dữ liệu này có được phép thu thập và có ích để điều tra không?
2. Nếu được thu thập, nó có thích hợp làm một chiều phân nhóm metrics không?

Token, mật khẩu, cookie phiên và toàn bộ thông tin thanh toán không trở nên phù hợp chỉ vì được xếp vào high-cardinality. Các mã liên kết điều tra cũng cần được lựa chọn theo chính sách dữ liệu của ứng dụng.

Ngược lại, một giá trị low-cardinality có thể vẫn nhạy cảm. Số lượng giá trị nhỏ không quyết định ai được xem dữ liệu.

### 4.3. Không tự tạo quan hệ truyền ngữ cảnh

Thêm `order.id` vào high-cardinality metadata không tự đưa nó vào header của mọi yêu cầu gửi sang dịch vụ khác. Metadata của observation, thuộc tính span và baggage/truyền context là các cơ chế liên quan nhưng khác nhau.

Cũng không cần thêm Trace ID làm tag metrics để “nối” hai hệ thống. Nếu dùng liên kết điều hướng như exemplar, cần kiểm tra khả năng hỗ trợ tương ứng; không biến mỗi Trace ID thành một chiều metrics mới.

## 5. Cách chọn nhóm cho dữ liệu thường gặp

| Metadata dự kiến | Đánh giá ban đầu | Cách thiết kế phù hợp |
| --- | --- | --- |
| `channel` từ enum WEB/MOBILE/BATCH | Miền nhỏ, có thể kiểm soát | Có thể dùng low-cardinality |
| `result` từ một tập mã kết quả cố định | Miền nhỏ nếu thực sự được giới hạn | Dùng low-cardinality khi cần phân nhóm |
| Route `/orders/{orderId}` | Tập route do ứng dụng định nghĩa | Thường phù hợp low-cardinality |
| Path thật `/orders/demo-102` | Tăng theo mã đơn hàng | Không dùng nguyên giá trị làm tag metrics |
| `order.id` hoặc `request.id` | Nhiều giá trị, thường sinh mới liên tục | Chi tiết trace nếu cần và được phép |
| `exception.message` | Có thể chứa ID, đầu vào và câu văn khác nhau | Ưu tiên mã lỗi/loại lỗi ổn định để phân nhóm |
| `tenant.id` | Phụ thuộc quy mô và tốc độ tăng tenant | Không mặc định low chỉ vì hệ thống hiện có ít tenant |
| `product.id` | Danh mục có thể rất lớn | Cân nhắc nhóm sản phẩm được kiểm soát hoặc chi tiết trace |
| URL đầy đủ có query string | Có thể chứa nhiều giá trị và bí mật | Dùng route/đích đã chuẩn hóa; chỉ thu thập chi tiết cần thiết |
| Thời gian chính xác hoặc UUID ngẫu nhiên | Giá trị mới liên tục | Không dùng như chiều metrics thông thường |

Đây là cách đánh giá ban đầu; quyết định cuối cùng cần gắn với câu hỏi vận hành và ngân sách cardinality. Một tag có miền nhỏ nhưng không giúp truy vấn nào vẫn có thể không cần thu thập.

Ví dụ, thay vì phân nhóm thời gian xử lý theo từng đơn hàng, chọn `channel` và `result` cho metrics; mã liên kết của từng đơn hàng chỉ phục vụ điều tra trace. Không nhất thiết mọi thông tin đều phải xuất hiện ở cả hai loại dữ liệu.

## 6. Ví dụ Java: đo trực tiếp ảnh hưởng của cách phân loại

Ví dụ sau chạy độc lập bằng JDK 21 và Micrometer 1.13.15. Không cần Spring MVC, HTTP server, Collector hoặc tài khoản giám sát. Mục tiêu là quan sát ngay trong bộ nhớ:

- Metadata high-cardinality có còn trong context không?
- Metadata đó có trở thành tag của timer chuẩn không?
- Số timer thay đổi thế nào khi đặt nhầm metadata vào nhóm low?

Đây là chương trình mô phỏng: phần việc được quan sát chỉ thêm mã đơn hàng giả vào một danh sách. Nó không thực hiện tra cứu đơn hàng thật và không xuất trace ra ngoài.

### 6.1. Chuẩn bị hai tệp

Cấu trúc:

```text
cardinality-demo/
├── pom.xml
└── src/main/java/CardinalityDemo.java
```

`pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>cardinality-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>21</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>io.micrometer</groupId>
            <artifactId>micrometer-core</artifactId>
            <version>1.13.15</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>CardinalityDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

Dependency `micrometer-core` của phiên bản này kéo theo các thành phần Observation/Common cần cho ví dụ. Với ứng dụng Boot thật, ưu tiên tập phiên bản do Boot quản lý thay vì tự thay phiên bản thư viện chỉ để chép ví dụ.

`src/main/java/CardinalityDemo.java`:

```java
import io.micrometer.common.KeyValue;
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.observation.DefaultMeterObservationHandler;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationHandler;
import io.micrometer.observation.ObservationRegistry;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;

public class CardinalityDemo {
    record Input(String channel, String orderId) {}

    private static final List<Input> INPUTS = List.of(
            new Input("WEB", "demo-101"),
            new Input("WEB", "demo-102"),
            new Input("MOBILE", "demo-103")
    );

    public static void main(String[] args) {
        run("correct", false);
        run("wrong-low", true);
    }

    private static void run(String mode, boolean orderIdAsLow) {
        SimpleMeterRegistry meters = new SimpleMeterRegistry();
        try {
            ObservationRegistry observations = ObservationRegistry.create();
            List<String> completed = new ArrayList<>();
            List<String> highValues = new ArrayList<>();

            observations.observationConfig()
                    .observationHandler(new DefaultMeterObservationHandler(meters))
                    .observationHandler(new ObservationHandler<Observation.Context>() {
                        @Override
                        public boolean supportsContext(Observation.Context context) {
                            return true;
                        }

                        @Override
                        public void onStop(Observation.Context context) {
                            String value = "absent";
                            for (KeyValue keyValue : context.getHighCardinalityKeyValues()) {
                                if ("order.id".equals(keyValue.getKey())) {
                                    value = keyValue.getValue();
                                }
                            }
                            highValues.add(value);
                        }
                    });

            for (Input input : INPUTS) {
                Observation observation = Observation.createNotStarted(
                                "order.lookup", observations)
                        .lowCardinalityKeyValue("channel", input.channel());

                if (orderIdAsLow) {
                    observation.lowCardinalityKeyValue("order.id", input.orderId());
                }
                else {
                    observation.highCardinalityKeyValue("order.id", input.orderId());
                }

                observation.observe(() -> {
                    completed.add(input.orderId());
                });
            }

            var timers = meters.find("order.lookup").timers();
            Map<String, Long> counts = new TreeMap<>();
            boolean orderIdOnTimer = false;

            for (Timer timer : timers) {
                counts.merge(timer.getId().getTag("channel"), timer.count(), Long::sum);
                orderIdOnTimer |= timer.getId().getTag("order.id") != null;
            }

            System.out.println("mode=" + mode);
            System.out.println("completed=" + completed.size());
            System.out.println("timer-series=" + timers.size());
            System.out.println("counts-by-channel=" + counts);
            System.out.println("order-id-on-timer=" + orderIdOnTimer);
            System.out.println("high-values=" + highValues);

            int expectedTimers = orderIdAsLow ? 3 : 2;
            if (completed.size() != 3 || timers.size() != expectedTimers
                    || !counts.equals(Map.of("WEB", 2L, "MOBILE", 1L))
                    || orderIdOnTimer != orderIdAsLow) {
                throw new IllegalStateException("Unexpected observation result");
            }
        }
        finally {
            meters.close();
        }
    }
}
```

Ba dữ liệu đầu vào chỉ có hai giá trị `channel` nhưng ba `order.id` khác nhau. Mỗi chế độ tạo một registry mới để kết quả của lần trước không bị trộn sang lần sau.

Trong `correct`:

```java
observation.lowCardinalityKeyValue("channel", input.channel());
observation.highCardinalityKeyValue("order.id", input.orderId());
```

Trong `wrong-low`, chương trình cố ý đặt `order.id` vào nhóm low-cardinality. Đây là đối chứng với ba dữ liệu giả trong bộ nhớ, không phải mẫu thiết kế nên áp dụng.

Handler tùy biến chỉ đọc các high-cardinality key-value khi observation kết thúc rồi ghi lại chuỗi cho phần in kết quả. Nó **không phải tracing handler**. Chính sự tách biệt này cho phép kiểm tra metadata mà không nhầm việc có context với việc đã xuất được span.

### 6.2. Biên dịch và chạy

Trong thư mục chứa `pom.xml`, dùng Maven với JDK 21:

```shell
mvn -q compile exec:java
```

Nếu chưa có dependency trong cache, Maven cần truy cập kho thư viện. Đây không phải tệp Java chỉ dùng thư viện chuẩn, nên lệnh `javac CardinalityDemo.java` thiếu classpath sẽ không đủ; Maven xử lý phần dependency và classpath trong lệnh trên.

Stdout của chương trình:

```text
mode=correct
completed=3
timer-series=2
counts-by-channel={MOBILE=1, WEB=2}
order-id-on-timer=false
high-values=[demo-101, demo-102, demo-103]
mode=wrong-low
completed=3
timer-series=3
counts-by-channel={MOBILE=1, WEB=2}
order-id-on-timer=true
high-values=[absent, absent, absent]
```

`TreeMap` giữ thứ tự hiển thị MOBILE rồi WEB để kết quả không phụ thuộc thứ tự duyệt registry. Thời gian đo thực tế không được in vì nó phụ thuộc môi trường chạy.

### 6.3. Đọc kết quả theo từng bằng chứng

| Kết quả | Điều được chứng minh |
| --- | --- |
| `completed=3` ở cả hai chế độ | Phần việc vẫn chạy ba lần; phân loại metadata không thay đổi số lần gọi nghiệp vụ mô phỏng |
| `timer-series=2` ở chế độ correct | Hai lần WEB dùng chung timer; MOBILE dùng timer khác |
| `order-id-on-timer=false` | Handler metrics chuẩn không đưa high-cardinality `order.id` vào tag timer |
| `high-values=[demo-101, ...]` | Metadata vẫn có trong context để handler phù hợp sử dụng |
| `timer-series=3` ở chế độ wrong-low | Tag `order.id` chia ba lần gọi thành ba danh tính timer khác nhau |
| `high-values=[absent, ...]` ở chế độ wrong-low | Giá trị đã được đặt vào tập low, không nằm trong tập high mà handler tùy biến đang đọc |

`timer-series` trong chương trình là **số Timer có đúng tên `order.lookup` trong registry**. Nó không phải tổng số chuỗi thời gian một backend bất kỳ sẽ lưu sau khi xuất histogram hoặc thêm metadata khác.

Ở chế độ sai, `counts-by-channel` vẫn cho kết quả WEB=2 và MOBILE=1 vì chương trình cộng số lần của các timer cùng kênh. Phép cộng đó không chứng minh thiết kế tag vẫn hiệu quả: đã có ba timer khác nhau phải được tạo và duyệt. Khi số ID tăng, cách “tổng hợp lại ở bước query” vẫn phải gánh chi phí của các chuỗi chi tiết.

Ba ID trong ví dụ không tự gây một sự cố bộ nhớ; chúng chỉ làm khác biệt về danh tính đo trở nên nhìn thấy được. Nguy cơ vận hành nằm ở việc áp dụng cùng quy tắc cho lượng ID tăng theo dữ liệu thật.

### 6.4. Điều ví dụ chưa chứng minh

Ví dụ không tạo span, không kiểm tra sampling và không kiểm tra exporter. Muốn xác nhận dữ liệu high-cardinality có trên span ở ứng dụng Boot, cần thêm hệ thống tracing phù hợp rồi kiểm tra span thực tế.

Ví dụ cũng không đo chi phí lưu trữ hay độ trễ truy vấn production. Nó kiểm chứng cơ chế phân nhóm ở Micrometer; đánh giá ngân sách cardinality cần số liệu và cấu hình của hệ thống triển khai thật.

## 7. Thiết kế metadata có giới hạn thật sự

### 7.1. Bắt đầu từ câu hỏi, rồi mới chọn tag

Một quy trình thiết kế có thể đi theo thứ tự:

1. Viết câu hỏi cần trả lời: “Kênh nào có tỷ lệ lỗi cao?”.
2. Chọn tên observation ổn định và các chiều cần thiết: `channel`, `result`.
3. Xác định tập giá trị hợp lệ và nguồn sinh từng giá trị.
4. Ước lượng số tổ hợp cùng các tag đã có từ framework hoặc cấu hình chung.
5. Quyết định chi tiết nào chỉ cần cho trace, chi tiết nào không nên thu thập.
6. Kiểm tra hành vi bằng dữ liệu có nhiều giá trị khác nhau.

Không thêm tag chỉ vì giá trị sẵn có trong request. Một ID rất tiện khi nhìn một log không có nghĩa nó là chiều phù hợp để chia metrics toàn hệ thống.

### 7.2. Chuẩn hóa giá trị tại điểm tạo metadata

Nếu đọc `channel` trực tiếp từ request, người gọi có thể gửi `web`, `WEB`, `Web`, khoảng trắng hoặc một chuỗi hoàn toàn khác. Dù tác giả nghĩ chỉ có ba kênh, dữ liệu đầu vào có thể làm miền giá trị mở rộng.

Một phương thức Java có thể chuẩn hóa **metadata dùng cho quan sát**:

```java
private static String normalizeChannel(String raw) {
    if (raw == null) {
        return "UNKNOWN";
    }

    String value = raw.trim().toUpperCase(java.util.Locale.ROOT);
    return switch (value) {
        case "WEB", "MOBILE", "BATCH" -> value;
        default -> "UNKNOWN";
    };
}
```

Đây là phương thức đặt trong một class, không phải tệp Java độc lập. Dùng kết quả của nó cho low-cardinality `channel`. Miền đầu ra được giới hạn ở WEB, MOBILE, BATCH và UNKNOWN.

Việc gộp giá trị lạ vào UNKNOWN làm mất khả năng phân biệt từng chuỗi lạ trong metric; đó là đánh đổi cần hiểu. Mã kiểm tra và từ chối đầu vào nghiệp vụ vẫn phải theo quy tắc của ứng dụng. Chuẩn hóa tag quan sát không có nghĩa chấp nhận đầu vào không hợp lệ cho nghiệp vụ.

Giữ cùng tập key cho một họ metric, thay vì lúc có `channel` lúc đổi thành một tên key khác theo request. Nếu cần biểu diễn giá trị chưa xác định, chọn một giá trị quy ước có kiểm soát và dùng nhất quán.

### 7.3. Dùng thông tin phân nhóm có ngữ nghĩa

Một số thay đổi thường hữu ích:

| Dữ liệu chi tiết | Chiều phân nhóm có thể xem xét | Thông tin bị mất khi gộp |
| --- | --- | --- |
| Mã đơn hàng | Kênh hoặc nhóm loại đơn được quản lý | Không phân biệt từng đơn |
| Thời gian cụ thể | Không thêm làm tag; để timestamp của dữ liệu biểu đạt thời gian | Không coi từng thời điểm là một nhóm |
| Số tiền chính xác | Nhóm khoảng giá trị được định nghĩa theo nhu cầu | Không giữ giá trị tiền chính xác trong chiều tag |
| Thông báo lỗi đầy đủ | Mã lỗi/nhóm lỗi ổn định | Không giữ câu văn hay dữ liệu động trong chiều metrics |
| URL chứa ID và query | Route mẫu hoặc tên thao tác | Không giữ từng URL cụ thể |

Không tự gộp ngẫu nhiên chỉ để số chuỗi nhỏ hơn. Mỗi nhóm cần có ý nghĩa khi truy vấn hoặc cảnh báo; nếu không giải thích được ý nghĩa của nhóm, có thể không nên thêm chiều đó.

### 7.4. Những cách giảm kích thước không giảm cardinality

- **Băm ID:** nếu các ID khác nhau vẫn cho kết quả băm khác nhau, số giá trị vẫn gần như giữ nguyên.
- **Cắt chuỗi ngắn hơn:** giảm độ dài không bảo đảm giảm đủ số giá trị phân biệt.
- **Chuyển ID từ tag sang tên metric:** vẫn tạo rất nhiều danh tính metric, đồng thời làm cấu trúc metric khó quản lý.
- **Đổi tên key:** `customer.id` thành `customer` không thay đổi miền giá trị.
- **Chỉ giảm chu kỳ xuất:** tác động số lần truyền, không tự thay đổi tập danh tính meter đã được tạo.
- **Chỉ giảm sampling trace:** không làm các tag metrics được sinh ra ít đi trong cơ chế đo thông thường.

Chia ID vào một số bucket cố định có thể giới hạn số nhóm, nhưng đó là một phép tổng hợp làm mất khả năng nhận dạng từng ID và chưa chắc có ý nghĩa nghiệp vụ. Nó cũng không mặc nhiên là biện pháp bảo vệ dữ liệu. Không xem đây là cách thay thế phổ quát cho thiết kế tag đúng.

## 8. Giới hạn bảo vệ là lớp hỗ trợ

Micrometer có `MeterFilter` để kiểm soát việc đăng ký meter và biến đổi danh tính meter. Ví dụ cấu hình khi đã có biến `meters` là một `MeterRegistry`:

```java
meters.config().meterFilter(
        io.micrometer.core.instrument.config.MeterFilter.maximumAllowableTags(
                "order.",
                "channel",
                4,
                io.micrometer.core.instrument.config.MeterFilter.deny()
        )
);
```

Ví dụ chọn 4 vì schema metadata ở trên đã định nghĩa ba kênh cùng UNKNOWN; con số này không phải giới hạn khuyến nghị cho mọi ứng dụng. Filter nhắm tới các tên bắt đầu bằng `order.` và tag `channel`. Cần cấu hình trước khi các meter liên quan được đăng ký.

Khi đạt giới hạn và chính sách `deny` từ chối một meter mới, registry trả về meter không ghi nhận dữ liệu thực (NOOP). Điều đó:

- Không tự chuyển giá trị thừa sang UNKNOWN.
- Không bảo đảm tổng số lần đo vẫn đầy đủ.
- Không tự sửa các điểm gắn đo lường tạo tag sai.
- Không nên được xem như một hạn mức lưu trữ chung cho mọi tiến trình và backend.

Vì vậy phải kiểm tra tác động lên dữ liệu, thay vì coi việc ứng dụng không ném exception là bằng chứng giới hạn không làm mất phép đo.

Các công cụ khác như `ignoreTags` hoặc `replaceTagValues` có thể loại bỏ/gộp chiều khi cần xử lý vấn đề. Chúng thay đổi danh tính và ý nghĩa phân nhóm của metric, nên cần đối chiếu truy vấn, dashboard và dữ liệu cũ. Cài filter sau sự cố không đồng nghĩa dữ liệu lịch sử hoặc toàn bộ chi phí trước đó đã được xóa.

Xem [Meter Filters của Micrometer 1.13](https://docs.micrometer.io/micrometer/reference/1.13/concepts/meter-filters.html). Lớp bảo vệ hữu ích khi đi cùng schema metadata rõ ràng; nó không thay trách nhiệm giới hạn miền giá trị tại nguồn.

## 9. Kiểm tra trong ứng dụng Spring Boot thực tế

### 9.1. Đọc đúng lớp bằng chứng

Nếu ứng dụng đã có endpoint chẩn đoán `metrics` và quyền truy cập phù hợp, kiểm tra meter cần quan sát bằng tên của nó. Trong ứng dụng gắn observation `order.lookup`, đường chẩn đoán tương ứng thường là:

```text
/actuator/metrics/order.lookup
```

Đường dẫn thực còn phụ thuộc port và base path đang cấu hình. Không cần công khai thêm endpoint trên production chỉ để thử bài học.

Quan sát các tag khả dụng có thể giúp phát hiện tag không mong muốn. Tuy nhiên:

- Một phản hồi liệt kê các giá trị tag chưa chắc cho biết đủ mọi tổ hợp của chúng.
- Endpoint chẩn đoán phản ánh ứng dụng/registry đang xét, không phải toàn bộ lịch sử của backend.
- High-cardinality key-value không xuất hiện trong tag metrics chuẩn có thể là hành vi đúng.
- Muốn kiểm tra nó trên trace, phải xem span thực tế và điều kiện tracing, lấy mẫu, lọc và xuất dữ liệu.

Cách dùng endpoint chẩn đoán meter được mô tả trong [Metrics của Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html).

### 9.2. Phân biệt một số triệu chứng

| Triệu chứng | Hướng kiểm tra |
| --- | --- |
| Số meter tăng gần theo số đơn hàng | Tìm ID, timestamp hoặc chuỗi tự do trong low-cardinality tag và tên meter |
| Cùng một kênh nhưng xuất hiện nhiều biến thể | Kiểm tra chuẩn hóa chữ hoa/thường, khoảng trắng và nguồn giá trị |
| Chỉ có hai key nhưng vẫn rất nhiều chuỗi | Đếm miền giá trị và tổ hợp, không chỉ đếm số key |
| High-cardinality metadata không thấy trong `metrics` | Đối chiếu hợp đồng handler; sự vắng mặt này có thể đúng |
| Metadata có trong context nhưng không thấy ở hệ thống trace | Kiểm tra tracing handler, sampling, exporter và bộ lọc dữ liệu |
| Thêm giới hạn xong số đếm giảm | Kiểm tra meter bị từ chối và phép đo bị bỏ qua |
| Tổng hợp query cho kết quả đúng nhưng chi phí vẫn lớn | Kiểm tra số chuỗi phải tạo/lưu trước khi tổng hợp |
| Mỗi instance ít giá trị nhưng backend có nhiều chuỗi | Kiểm tra tổng instance, thời gian lưu và các chiều do backend thêm |

Với một nghi vấn cardinality, ghi lại tên metric, các key, miền giá trị, tốc độ xuất hiện giá trị mới và số tổ hợp quan sát được. Không đưa token hoặc dữ liệu người dùng thô vào báo cáo chẩn đoán.

## 10. Thực hành và tự giải thích

**Bài tập 1: Thêm `new Input("WEB", "demo-104")` vào chương trình.**

Ở chế độ đúng, số timer `order.lookup` vẫn là 2 và tổng count WEB thành 3. Ở chế độ sai, số timer thành 4 vì có một tổ hợp tag mới. Cả hai chế độ vẫn thực hiện đủ bốn lần phần việc mô phỏng. Khi thay dataset cần cập nhật các điều kiện kiểm tra cuối chương trình cho phù hợp.

**Bài tập 2: Thay đầu vào cuối bằng một bản sao của `WEB/demo-101`.**

Ở chế độ sai, lần lặp lại đúng cùng tập tag không tạo thêm một danh tính timer mới; count của timer cũ tăng. Điều này giúp tách “số sự kiện” khỏi “số tổ hợp giá trị phân biệt”.

**Bài tập 3: Chọn cách lưu `customer.id`, `customer.tier` và `result`.**

`customer.id` thường tăng theo khách hàng, nên không mặc định dùng làm chiều metrics. `customer.tier` có thể phù hợp nếu lấy từ một tập phân hạng nhỏ, được quản lý. `result` có thể phù hợp nếu là mã kết quả ổn định, không phải toàn bộ thông báo lỗi. Chỉ thu thập ID chi tiết trong trace khi cần và được phép.

**Bài tập 4: Một hệ thống mới có 10 tenant. Có thể dùng `tenant.id` làm low-cardinality không?**

Chưa đủ thông tin. Cần biết số tenant có thể tăng tới đâu, số tổ hợp cùng các chiều khác, nhu cầu giám sát từng tenant và ngân sách lưu trữ. Số hiện tại chỉ là ảnh chụp; quyết định phải dựa trên cam kết miền giá trị cùng chi phí dự kiến.

**Bài tập 5: Một giá trị được đưa vào high-cardinality có tự xuất hiện trên mọi trace không?**

Không. Nó cần nằm trong observation/span phù hợp, được handler sử dụng và đi qua các điều kiện ghi, lấy mẫu, lọc, xuất dữ liệu. Phân loại metadata không phải cam kết mọi dữ liệu đều được lưu.

Khi thêm một key-value mới, hãy giải thích được **giá trị lấy từ đâu, có thể tạo bao nhiêu nhóm, nhóm đó phục vụ câu hỏi nào và cần xuất hiện ở metrics hay chỉ ở chi tiết trace**.
