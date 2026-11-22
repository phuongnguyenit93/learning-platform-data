# Giới hạn số giá trị tag và xử lý URI có số lượng giá trị quá lớn

## 1. Vì sao một nhãn URI có thể làm hệ thống giám sát quá tải?

Giả sử ứng dụng có một tuyến xem đơn hàng:

```text
/orders/{id}
```

Nếu dùng đường dẫn đã thay mã đơn làm giá trị nhãn, mỗi tài nguyên có thể tạo một nhóm số đo riêng:

```text
uri=/orders/101
uri=/orders/102
uri=/orders/103
...
```

Trong khi đó, câu hỏi vận hành thường là “tuyến xem đơn hàng có chậm không?”, không phải “mỗi mã đơn có một biểu đồ thời lượng riêng không?”. Cùng một loại thao tác đã bị chia thành quá nhiều nhóm.

**Số lượng giá trị phân biệt (cardinality)** của nhãn `uri` là số giá trị URI khác nhau được sử dụng. Cardinality cao có thể làm tăng số meter trong tiến trình Java, số chuỗi thời gian ở hệ thống nhận, lượng bộ nhớ, chi phí lưu trữ và độ khó khi truy vấn.

Cần phân biệt:

- Số request là số lần một thao tác xảy ra.
- Số giá trị `uri` là số nhóm đường dẫn khác nhau.
- Số meter phụ thuộc tên cùng toàn bộ tập nhãn.
- Số chuỗi xuất ra còn phụ thuộc loại meter và các thống kê, chẳng hạn histogram.

Một triệu request cùng giá trị `uri=/orders/{id}` không tự tạo một triệu meter. Nhưng một triệu URI khác nhau được đưa vào nhãn có thể tạo vấn đề dù mỗi URI chỉ được gọi một lần.

Cách xử lý có hai phần: **tạo nhãn có số giá trị được kiểm soát ngay tại nguồn**, rồi **đặt giới hạn để bảo vệ khi dữ liệu vượt dự kiến**. Chỉ đặt giới hạn mà giữ nguyên URI thô có thể làm dữ liệu giám sát bị thiếu.

## 2. Đặt ngân sách nhãn dựa trên ý nghĩa của số đo

### 2.1. Giới hạn số giá trị khác với giới hạn số khóa

Một meter có ba khóa nhãn `method`, `status` và `uri` vẫn có thể tạo rất nhiều tổ hợp:

```text
4 phương thức × 6 trạng thái × 50 URI = tối đa 1.200 tổ hợp
```

Đây là phép ước lượng khi mọi tổ hợp đều xuất hiện; dữ liệu thực tế có thể ít hơn. Khi có nhiều instance, những chuỗi của từng instance còn góp vào tổng toàn hệ thống.

Do đó, giới hạn `uri` ở 50 giá trị không có nghĩa toàn bộ hệ thống chỉ còn 50 meter hoặc 50 chuỗi. Những nhãn khác vẫn có thể tăng, và mỗi timer có thể xuất nhiều thống kê.

Cũng không nhầm số giá trị với độ dài của chuỗi. Cắt mỗi URI xuống 100 ký tự không bảo đảm số URI khác nhau sẽ nhỏ. Băm URI thành mã ngắn cũng thường giữ nguyên số giá trị phân biệt nếu mỗi đầu vào vẫn có một mã riêng.

### 2.2. Nhãn phải phục vụ phân nhóm, không phải tra cứu từng sự kiện

Các chiều có tập giá trị được định nghĩa rõ thường phù hợp hơn:

| Nhu cầu | Nhãn có thể dùng | Dữ liệu không nên đưa nguyên vào metric |
| --- | --- | --- |
| So sánh tuyến HTTP | Mẫu tuyến như `/orders/{id}` | Mã đơn đã thay vào đường dẫn |
| So sánh kết quả xử lý | Nhóm thành công/thất bại đã thống nhất | Toàn văn thông báo lỗi |
| So sánh nhà cung cấp | Tập nhà cung cấp hữu hạn | Chuỗi tự do từ đầu vào |
| So sánh nhóm người dùng | Hạng dịch vụ đã định nghĩa | User ID hoặc email |
| Xem hành vi tìm kiếm | Nhóm thao tác tìm kiếm | Toàn bộ câu truy vấn người dùng |

Khi cần tra cứu một giao dịch hay request cụ thể, dùng cơ chế phù hợp như log hoặc trace với chính sách dữ liệu của ứng dụng. Không biến metric tổng hợp thành danh mục của mọi sự kiện.

Prometheus cũng khuyến nghị cân nhắc kỹ các nhãn có nhiều giá trị vì mỗi tổ hợp tạo thêm chuỗi số liệu. [Hướng dẫn Instrumentation — Do not overuse labels](https://prometheus.io/docs/practices/instrumentation/#do-not-overuse-labels).

### 2.3. Dành chỗ cho nhóm dự phòng

Nếu chính sách nhãn cho phép ba giá trị `primary`, `backup` và `other`, ngân sách phải tính cả `other`. Nếu chỉ chừa chỗ cho các giá trị thường gặp, nhóm dự phòng có thể bị từ chối đúng lúc cần nó nhất.

Ngân sách nên xuất phát từ tập tuyến, nhóm trạng thái và giá trị nghiệp vụ hợp lệ, có phần dành cho thay đổi dự kiến. Không tăng ngưỡng liên tục để chạy theo từng ID mới.

## 3. Sửa URI tại nguồn bằng mẫu tuyến

### 3.1. Phía máy chủ: dùng tuyến đã khớp

Với Spring MVC, một khai báo như sau thể hiện mẫu tuyến:

```java
@GetMapping("/orders/{id}")
```

Đây là phần annotation của một handler hiện có, không phải một chương trình độc lập. Mã đơn thật được dùng để xử lý nghiệp vụ; nhãn metric nên mô tả mẫu tuyến.

Các tích hợp quan sát HTTP của Spring sử dụng thông tin tuyến đã khớp khi có thể. Nếu thấy metric mang hàng nghìn giá trị như `/orders/101`, hãy kiểm tra:

- Mã đo thủ công có đang dùng `request.getRequestURI()` làm nhãn không.
- Observation convention tùy chỉnh có ghi đè mẫu tuyến bằng đường dẫn thật không.
- Gateway, router hoặc một tích hợp ngoài có còn giữ thông tin mẫu tuyến không.
- Các request không khớp handler có bị gắn nguyên đường dẫn tùy ý vào nhãn không.

Với request không khớp, cần nhóm dự phòng hữu hạn. Những giá trị như `NOT_FOUND` hoặc `UNKNOWN` có thể xuất hiện tùy tích hợp, trạng thái và phiên bản; không tự suy ra rằng mọi request lỗi đều phải có cùng một nhãn cụ thể.

Điểm cần giữ là không tạo một nhóm mới cho từng đường dẫn 404 do người gọi gửi vào. [Tài liệu Observability Support của Spring Framework](https://docs.spring.io/spring-framework/reference/integration/observability.html) mô tả `uri` ở cấp quan sát HTTP và các thông tin có độ phân biệt cao.

### 3.2. Phía HTTP client: truyền mẫu và biến tách biệt

Với một `RestClient` đã được cấu hình đo lường, so sánh hai cách viết:

```java
// Đường dẫn đã bị ghép thành một chuỗi cụ thể.
client.get()
        .uri("/orders/" + orderId)
        .retrieve()
        .toBodilessEntity();

// Mẫu URI và giá trị biến được truyền tách biệt.
client.get()
        .uri("/orders/{id}", orderId)
        .retrieve()
        .toBodilessEntity();
```

Đây là đoạn minh họa với `client` và `orderId` đã tồn tại. Cách thứ hai giữ được mẫu trước khi thay biến cho tích hợp quan sát có hỗ trợ nó.

Dùng builder do Spring Boot cấu hình cho client tương ứng để nhận tích hợp quan sát của ứng dụng. Không kết luận rằng mọi client tự tạo đều đã có metric.

URI tuyệt đối được tạo sẵn, đường dẫn ghép chuỗi, UUID, slug, token phân trang hoặc giá trị truy vấn được nhúng trực tiếp có thể khiến mẫu bị mất hoặc tập giá trị tăng nếu được đưa nguyên vào nhãn. Kiểm tra nhãn `uri` thực tế, vì một số API có thể dùng giá trị dự phòng khi không có mẫu thay vì xuất đường dẫn thật.

Không chỉ xóa mọi chữ số bằng một biểu thức chính quy dùng chung. Cách đó có thể vẫn bỏ sót UUID/slug, hoặc gộp sai các tuyến có ý nghĩa khác nhau như một đoạn phiên bản API. Thông tin từ router hay mẫu được truyền tại lời gọi đáng tin hơn việc đoán từ chuỗi đường dẫn.

### 3.3. Với metric tự viết, chuẩn hóa trước khi đăng ký meter

Nếu ứng dụng tự ghi `Timer` hoặc `Counter`, xác định giá trị nhãn trước khi gọi builder/register. Dùng bảng ánh xạ hữu hạn hoặc thông tin nghiệp vụ có cấu trúc.

Ví dụ, mọi request đã được router xác định là “xem một đơn” cùng dùng `/orders/{id}`. Các đường dẫn không khớp dùng nhóm đã thống nhất. Không giữ một bản đồ tăng không giới hạn từ mọi URI thô sang URI đã chuẩn hóa chỉ để phục vụ metric.

Chuẩn hóa là một quyết định về ý nghĩa dữ liệu: sau khi gộp, metric không còn phân biệt từng ID. Đó là chủ đích để quan sát tổng hợp, không phải một sự thay thế cho nơi lưu chi tiết.

## 4. MeterFilter giới hạn giá trị tag hoạt động như thế nào?

Micrometer có API:

```java
MeterFilter.maximumAllowableTags(
        "http.server.requests",
        "uri",
        100,
        MeterFilter.deny());
```

Đây là ví dụ cấu hình bộ lọc, với bốn thành phần:

| Tham số | Ý nghĩa |
| --- | --- |
| `"http.server.requests"` | Tiền tố tên meter được áp dụng |
| `"uri"` | Khóa nhãn cần giới hạn |
| `100` | Số giá trị khác nhau được cho phép theo cơ chế của bộ lọc |
| `MeterFilter.deny()` | Từ chối đăng ký meter khi gặp giá trị mới vượt ngưỡng |

Tên đầu tiên là **tiền tố**, không phải biểu thức chính quy hay một bộ lọc URI. Nếu có nhiều tên meter cùng khớp tiền tố, phải tính tới phạm vi chung của bộ lọc này.

Các điểm cần hiểu:

- Giới hạn là số giá trị nhãn, không phải số request mỗi giây.
- Meter dùng giá trị đã được chấp nhận vẫn có thể ghi thêm nhiều lần.
- Giá trị URI mới vượt ngưỡng không được tự chuyển thành `other` bởi `deny()`.
- Việc từ chối meter không từ chối request HTTP hoặc hủy nghiệp vụ.
- Với `DENY`, registry trả về bộ đo không ghi dữ liệu (NOOP); lệnh ghi số đo vẫn có thể chạy mà không đưa mẫu đó vào dữ liệu thu thập.
- Bộ lọc này không hứa hẹn lấy mẫu ngẫu nhiên, giữ top N tuyến quan trọng hay áp dụng một cửa sổ N phút.

Vì thế, đây là cơ chế bảo vệ, không phải giải pháp duy nhất để sửa URI có cardinality cao. [Tài liệu Meter Filters của Micrometer](https://docs.micrometer.io/micrometer/reference/1.13/concepts/meter-filters.html) mô tả API giới hạn và hành vi của meter bị từ chối.

Nếu các URI thô đầu tiên đã dùng hết ngân sách, một tuyến hợp lệ xuất hiện sau đó có thể không có số đo. Dữ liệu còn lại không nhất thiết đại diện cho toàn bộ lưu lượng và không nên được xem là mẫu thống kê ngẫu nhiên.

## 5. Thí nghiệm Java: giới hạn thô và chuẩn hóa cho kết quả khác nhau

Ví dụ dùng Java 21 và Micrometer 1.13.0. Nó mô phỏng tám lượt ghi số đo, không khởi động máy chủ HTTP. Tên `demo.http.requests` được chọn riêng để phân biệt với metric HTTP tự động của Spring Boot.

Ba kịch bản chạy trên ba registry mới:

1. `RAW`: dùng URI thô, không giới hạn.
2. `LIMIT_ONLY`: dùng URI thô, chỉ cho hai giá trị `uri`.
3. `TEMPLATE_AND_LIMIT`: chuẩn hóa tại nguồn rồi đặt cùng giới hạn hai giá trị.

### 5.1. Dependency

Tạo `pom.xml` trong thư mục thực hành độc lập:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>uri-tag-budget-lab</artifactId>
    <version>1.0.0</version>
    <dependencies>
        <dependency>
            <groupId>io.micrometer</groupId>
            <artifactId>micrometer-core</artifactId>
            <version>1.13.0</version>
        </dependency>
    </dependencies>
</project>
```

Phiên bản được cố định để tái lập thí nghiệm. Trong ứng dụng Spring Boot, dùng phiên bản Micrometer do Spring Boot quản lý.

### 5.2. Chương trình hoàn chỉnh

Lưu tại `src/main/java/demo/UriTagBudgetDemo.java`:

```java
package demo;

import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.config.MeterFilter;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

import java.time.Duration;
import java.util.Collection;
import java.util.List;
import java.util.stream.Collectors;

public class UriTagBudgetDemo {
    private static final String METRIC = "demo.http.requests";
    private static final List<String> PATHS = List.of(
            "/orders/101", "/orders/102", "/orders/103",
            "/orders/104", "/orders/105",
            "/missing/a", "/missing/b", "/orders/101");

    public static void main(String[] args) {
        run("RAW", false, 0);
        run("LIMIT_ONLY", false, 2);
        run("TEMPLATE_AND_LIMIT", true, 2);
    }

    private static void run(String label, boolean useTemplate, int limit) {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        try {
            if (limit > 0) {
                registry.config().meterFilter(MeterFilter.maximumAllowableTags(
                        METRIC, "uri", limit, MeterFilter.deny()));
            }

            for (String path : PATHS) {
                boolean matched = path.matches("/orders/[0-9]+");
                String uri = useTemplate
                        ? (matched ? "/orders/{id}" : "NOT_FOUND")
                        : path;
                String status = matched ? "200" : "404";
                Timer.builder(METRIC)
                        .tags("method", "GET", "status", status, "uri", uri)
                        .register(registry)
                        .record(Duration.ofMillis(1));
            }

            Collection<Timer> timers = registry.find(METRIC).timers();
            long recorded = timers.stream().mapToLong(Timer::count).sum();
            String uris = timers.stream()
                    .map(timer -> timer.getId().getTag("uri"))
                    .distinct().sorted()
                    .collect(Collectors.joining(", ", "[", "]"));

            System.out.printf("%s attempts=%d meters=%d recorded=%d%n",
                    label, PATHS.size(), timers.size(), recorded);
            System.out.println(label + " uris=" + uris);
        } finally {
            registry.close();
        }
    }
}
```

Quy tắc `/orders/[0-9]+` là một mô phỏng router rất nhỏ, chỉ dành cho tập đầu vào của thí nghiệm. Nó không phải thuật toán chuẩn hóa mọi URI trong ứng dụng thật. Trong hệ thống thực, ưu tiên thông tin tuyến đã khớp hoặc mẫu đã biết tại điểm gọi.

Các đường dẫn không khớp trong mô phỏng được gán trạng thái 404 và nhóm `NOT_FOUND` khi chuẩn hóa. Không có request thật nào bị chặn bởi bộ lọc trong chương trình.

### 5.3. Biên dịch và chạy

Từ thư mục chứa `pom.xml`, dùng Maven tải dependency và JDK 21 biên dịch. Lần tải thư viện đầu cần truy cập kho Maven.

Trên PowerShell/Windows:

```powershell
mvn -q dependency:copy-dependencies -DoutputDirectory=target/dependency
javac --release 21 -cp "target/dependency/*" -d target/classes src/main/java/demo/UriTagBudgetDemo.java
java -cp "target/classes;target/dependency/*" demo.UriTagBudgetDemo
```

Trên Linux/macOS, dùng hai lệnh đầu tương tự và thay lệnh chạy bằng:

```bash
java -cp "target/classes:target/dependency/*" demo.UriTagBudgetDemo
```

Stdout chính xác:

```text
RAW attempts=8 meters=7 recorded=8
RAW uris=[/missing/a, /missing/b, /orders/101, /orders/102, /orders/103, /orders/104, /orders/105]
LIMIT_ONLY attempts=8 meters=2 recorded=3
LIMIT_ONLY uris=[/orders/101, /orders/102]
TEMPLATE_AND_LIMIT attempts=8 meters=2 recorded=8
TEMPLATE_AND_LIMIT uris=[/orders/{id}, NOT_FOUND]
```

### 5.4. Giải thích kết quả

Ở `RAW`, bảy đường dẫn khác nhau tạo bảy timer. `/orders/101` được ghi hai lần nên tổng count bằng tám, dù số meter chỉ bằng bảy.

Ở `LIMIT_ONLY`, `/orders/101` và `/orders/102` được chấp nhận trước. Các URI mới sau đó bị từ chối. Lượt cuối dùng lại `/orders/101` nên vẫn được ghi; tổng count còn ba.

Ở `TEMPLATE_AND_LIMIT`, năm mã đơn khác nhau đều trở thành `/orders/{id}`, còn hai đường dẫn không khớp cùng thành `NOT_FOUND`. Chỉ có hai giá trị URI nhưng giữ đủ tám lượt ghi nhận.

| Kịch bản | Số meter | Tổng lượt ghi nhận | Điều học được |
| --- | --- | --- | --- |
| URI thô | 7 | 8 | Giữ dữ liệu nhưng số nhóm tăng theo đầu vào |
| Chỉ giới hạn | 2 | 3 | Bảo vệ số nhóm bằng cách mất các mẫu vượt ngưỡng |
| Chuẩn hóa rồi giới hạn | 2 | 8 | Tập nhóm nhỏ vẫn mô tả đủ các lượt của thí nghiệm |

Không diễn giải “recorded=3” là ứng dụng chỉ xử lý ba lượt. Cả tám lượt đều đi qua vòng lặp; năm lượt không còn đóng góp vào số đo được giữ lại.

## 6. Cấu hình bảo vệ trong Spring Boot

### 6.1. Giới hạn URI của HTTP server và client

Spring Boot 3.3 cung cấp hai thuộc tính:

```properties
management.metrics.web.server.max-uri-tags=100
management.metrics.web.client.max-uri-tags=100
```

Hai giá trị 100 ở đây là mặc định được tài liệu hóa của nhánh phiên bản này, không phải khuyến nghị ngân sách tối ưu cho mọi ứng dụng. Các URI mới vượt ngưỡng sẽ bị bộ lọc từ chối đối với metric thuộc tích hợp tương ứng.

Kiểm tra đúng phiên bản, tên metric và tích hợp đang dùng khi thay đổi cấu hình. Hai thuộc tính cho HTTP không tự trở thành giới hạn cho mọi nhãn của mọi metric nghiệp vụ. [Common Application Properties của Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/index.html) liệt kê cả thuộc tính, mặc định và hành vi từ chối.

Nếu có nhiều tuyến hợp lệ hơn ngân sách, phải thiết kế lại ngân sách hoặc phạm vi đo. Nếu chỉ có một tuyến nhưng hàng nghìn URI chứa ID, phải sửa cách tạo nhãn trước. Hai tình huống không nên được xử lý giống nhau bằng việc tăng số.

### 6.2. Giới hạn một nhãn nghiệp vụ tùy chỉnh

Với metric của ứng dụng, có thể đăng ký `MeterFilter` thành bean. Ví dụ dưới đây giả sử hợp đồng nhãn `provider` chỉ gồm `primary`, `backup` và `other`:

```java
@Bean
MeterFilter checkoutProviderBudget() {
    return MeterFilter.maximumAllowableTags(
            "checkout.", "provider", 3, MeterFilter.deny());
}
```

Đây là phương thức đặt trong một lớp `@Configuration` của ứng dụng, với import `org.springframework.context.annotation.Bean` và `io.micrometer.core.instrument.config.MeterFilter`. Nó không phải một chương trình Java độc lập.

Nguồn tạo nhãn phải ánh xạ đúng vào ba nhóm trên. Nếu vẫn đưa chuỗi nhà cung cấp tự do vào nhãn, ba giá trị bất kỳ xuất hiện đầu tiên có thể dùng hết ngân sách; bộ lọc không tự tạo hợp đồng nghiệp vụ thay bạn.

Cấu hình filter trong giai đoạn khởi tạo, trước khi đăng ký meter liên quan. Không gắn filter lặp lại trong mỗi request hoặc tạo một registry mới trong service để né giới hạn.

### 6.3. Đừng bỏ qua thứ tự và phạm vi filter

Filter có thể đổi danh tính, chấp nhận hoặc từ chối meter. Một filter chấp nhận toàn bộ một nhóm có thể làm các bước kiểm tra chấp nhận/từ chối phía sau không được áp dụng như dự kiến. Cần kiểm tra chuỗi filter thay vì chỉ nhìn thấy bean giới hạn là kết luận đã được bảo vệ.

Nếu dùng filter ánh xạ nhãn như một biện pháp chuyển tiếp, logic phải nhất quán với danh tính meter và không phụ thuộc ngẫu nhiên vào request hiện tại. Ưu tiên tạo nhãn có cấu trúc tại nguồn để chính sách dễ kiểm chứng và ít phụ thuộc cơ chế ánh xạ nội bộ.

## 7. Những cách xử lý chưa giải quyết đúng nguyên nhân

### 7.1. Đổi tên metric hoặc đổi kiểu tên

Chuyển dấu chấm sang gạch dưới, đổi `uri` thành `path` hoặc tạo tên metric khác không làm giảm số giá trị URI. Nếu dữ liệu vẫn chứa mọi ID, vấn đề chỉ chuyển sang một tên mới.

### 7.2. Băm hoặc cắt ngắn URI

Băm là thay biểu diễn; nó không tự giảm số giá trị khác nhau. Cắt ngắn có thể gây gộp nhầm mà vẫn để lại rất nhiều nhóm. Cần chuẩn hóa theo tuyến hoặc nhóm nghiệp vụ có ý nghĩa.

### 7.3. Xóa toàn bộ nhãn URI ngay lập tức

Bỏ nhãn có thể giảm số chuỗi, nhưng cũng mất khả năng phân biệt endpoint. Đây có thể là quyết định có chủ đích cho một phép đo tổng hợp, không phải lựa chọn mặc định cho mọi metric HTTP.

Thông thường nên giữ mẫu tuyến hữu hạn trước khi cân nhắc bỏ hẳn chiều phân loại này.

### 7.4. Dùng regex của dashboard để gộp sau khi thu thập

Gộp các URI bằng truy vấn giúp biểu đồ dễ đọc nhưng không ngăn ứng dụng đã tạo nhiều meter hay hệ thống giám sát đã lưu nhiều chuỗi.

Tương tự, loại nhãn ở tầng thu thập có thể giảm dữ liệu phía sau nhưng không tự sửa lượng meter đã được tạo trong JVM. Cần biết biện pháp đang bảo vệ tầng nào.

### 7.5. Tăng ngưỡng hoặc khởi động lại để tạm hết cảnh báo

Tăng ngưỡng chỉ phù hợp khi tập giá trị hợp lệ đã được đánh giá. Nếu giá trị tăng theo ID tài nguyên, một ngưỡng mới vẫn có thể sớm bị lấp đầy.

Khởi động lại không làm URI thô trở thành mẫu tuyến. Thay đổi filter cũng không phải thao tác tự động viết lại mọi meter đã có hoặc xóa lịch sử đã lưu ở hệ thống giám sát. Cần một thay đổi cấu hình/mã đã kiểm chứng và theo dõi dữ liệu mới.

## 8. Kiểm chứng sau khi sửa: ít nhóm nhưng vẫn đủ số đo

Không chỉ kiểm tra “số meter đã giảm”. Bộ lọc từ chối cũng làm số meter ít đi, nhưng có thể đồng thời làm mất một phần lưu lượng như thí nghiệm đã cho thấy.

Một lượt kiểm tra có ích gồm:

1. Chọn một instance và một nhóm đầu vào có thể kiểm soát.
2. Gửi nhiều ID khác nhau vào cùng một tuyến hợp lệ.
3. Gửi các request không khớp với nhiều đường dẫn khác nhau.
4. Đọc các giá trị `uri` xuất hiện trong metric.
5. Đối chiếu tổng count tăng thêm với số request đã hoàn tất theo phạm vi đang đo.
6. Kiểm tra thêm nhãn như method, status và các nhãn nghiệp vụ khác có tăng ngoài dự kiến không.

Nếu endpoint `metrics` đã được expose, có thể đọc:

```bash
curl "http://127.0.0.1:8080/actuator/metrics/http.server.requests"
curl --get "http://127.0.0.1:8080/actuator/metrics/http.server.requests" --data-urlencode "tag=uri:/orders/{id}"
```

Đây là lệnh cho một ứng dụng Spring Boot đang chạy, không phải cho chương trình Java độc lập ở phần 5. Trên PowerShell có thể dùng `curl.exe`. Dùng đúng cổng, đường dẫn management và giá trị nhãn mà ứng dụng thực tế cung cấp.

Ở response chi tiết, xem các giá trị nhãn khả dụng và các thống kê. So sánh count trước/sau thay vì so giá trị tích lũy với số request mới. Khi tính tổng nhiều nhóm, giữ cùng phạm vi và tránh trộn request đọc Actuator vào request nghiệp vụ đang thử.

Các mục tiêu nên đồng thời đúng:

| Điều cần kiểm chứng | Kết quả mong muốn |
| --- | --- |
| Cùng tuyến, nhiều mã tài nguyên | Cùng giá trị mẫu tuyến |
| Nhiều đường dẫn không khớp | Tập nhóm dự phòng hữu hạn |
| Lưu lượng hợp lệ trong ngân sách | Tổng lượt đo vẫn đầy đủ |
| Giá trị mới vượt ngân sách | Hành vi từ chối được phát hiện và hiểu rõ |
| Các nhãn còn lại | Không chứa một chiều tăng không kiểm soát khác |

Khi giới hạn đã kích hoạt, không tính tỷ lệ lỗi hay lưu lượng toàn ứng dụng chỉ từ phần metric còn được giữ rồi coi đó là dữ liệu đầy đủ. Đối chiếu nguồn khác và xác định phạm vi bị thiếu.

## 9. Theo dõi để giới hạn không trở thành điểm mù

Vận hành cần biết khi nào số liệu đang bị từ chối. Có thể dùng cảnh báo của tích hợp hoặc một cơ chế ghi nhận vi phạm có tập nhãn hữu hạn.

Nếu tự viết phần thông báo khi vượt ngưỡng, không tạo một metric mới có nhãn là chính URI bị từ chối; cách đó tái tạo vấn đề dưới một tên khác. Việc ghi log cho mọi request vượt ngưỡng cũng có thể quá nhiều, nên cần kiểm soát tần suất và mức tổng hợp.

Đánh giá số nhóm theo thời gian cùng số request và thay đổi tuyến của ứng dụng. Một lần triển khai có thêm tuyến hợp lệ khác với một chuỗi request ngẫu nhiên tạo hàng nghìn đường dẫn mới.

Với Observation, phân biệt dữ liệu có độ phân biệt thấp dùng cho metric và dữ liệu chi tiết có độ phân biệt cao. Chuyển ID sang trường chi tiết phù hợp không có nghĩa dữ liệu đó không còn chi phí; nó chỉ tránh dùng ID làm chiều tổng hợp của metric.

Một chính sách có thể ghi rõ:

- Nhãn nào được phép tồn tại và tập giá trị dự kiến.
- Mẫu URI lấy từ router hay mẫu tại lời gọi client.
- Nhóm dự phòng khi không xác định được tuyến.
- Giới hạn bảo vệ cho từng metric/nhóm metric.
- Cách nhận biết mẫu bị từ chối và cách kiểm tra độ đầy đủ.

## 10. Tự kiểm tra cách hiểu

1. Có một triệu request đều dùng `uri=/orders/{id}`. Riêng nhãn URI có cardinality bằng bao nhiêu?
2. Vì sao chỉ giới hạn hai URI thô trong thí nghiệm lại chỉ giữ ba trên tám lượt đo?
3. `MeterFilter.deny()` có tự đưa những URI còn lại vào `other` không?
4. Giới hạn URI ở 100 có bảo đảm toàn registry chỉ có tối đa 100 meter không?
5. Chuẩn hóa ở dashboard có ngăn bộ nhớ JVM đã dùng để giữ meter theo URI thô không?

Đối chiếu: một giá trị; hai URI đầu được chấp nhận và lần cuối dùng lại một URI đã có; không tự gộp; không vì còn các tên và chiều nhãn khác; không vì truy vấn chạy sau giai đoạn tạo/thu thập số đo.

Cách xử lý đầy đủ là giữ nhãn mô tả nhóm thao tác có ý nghĩa, chuẩn hóa trước khi tạo số đo, thêm ngưỡng bảo vệ và kiểm chứng rằng số liệu vẫn đại diện đúng cho phạm vi cần quan sát.
