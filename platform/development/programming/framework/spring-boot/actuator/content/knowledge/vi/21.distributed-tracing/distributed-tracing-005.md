# Điều chỉnh xác suất lấy mẫu và hiểu giới hạn dữ liệu quan sát được

## 1. Lấy mẫu để giải quyết vấn đề gì?

Một hệ thống có thể xử lý hàng nghìn yêu cầu mỗi giây. Mỗi yêu cầu lại tạo nhiều span ở các dịch vụ và thư viện khác nhau. Nếu giữ mọi trace, lượng dữ liệu cần xử lý, truyền và lưu trữ có thể tăng rất nhanh.

Lấy mẫu (`sampling`) là chính sách lựa chọn dữ liệu truy vết sẽ được ghi nhận/xuất theo cơ chế của tracer và đường thu thập. Xác suất lấy mẫu giúp cân bằng độ bao phủ với lượng dữ liệu.

Điều cần hiểu trước khi chỉnh cấu hình là: **danh sách trace đang xem chỉ là phần dữ liệu đã đi qua chính sách lấy mẫu và toàn bộ đường thu thập. Không thấy một trace không có nghĩa thao tác tương ứng chưa xảy ra.**

Trong bài này:

- `p` là xác suất cấu hình cho quyết định lấy mẫu phù hợp.
- Trace gốc là trace mới được bắt đầu khi chưa có ngữ cảnh cha quyết định việc lấy mẫu.
- Span là một thao tác trong trace; nhiều span có thể dùng chung một quyết định lấy mẫu.
- Lấy mẫu đầu (`head sampling`) quyết định sớm, trước khi biết toàn bộ kết quả của trace.
- Lấy mẫu cuối (`tail sampling`) ra quyết định dựa trên các span đã được thu thập ở bước sau.

Bài tập trung vào cấu hình tracing của Spring Boot 3.3.x và cách diễn giải dữ liệu nhận được. Xác suất tracing không phải tỷ lệ lấy mẫu chung cho mọi metric và log.

## 2. Điều chỉnh xác suất trong Spring Boot 3.3.x

### 2.1. Thuộc tính cấu hình

Trong ứng dụng đã có hạ tầng Micrometer Tracing, bridge và thành phần xuất trace phù hợp:

```yaml
management:
  tracing:
    sampling:
      probability: 0.1
```

Có thể viết dạng properties tương đương:

```properties
management.tracing.sampling.probability=0.1
```

Spring Boot 3.3 mặc định cấu hình xác suất 10%. Để quan sát đầy đủ hơn các trace gốc trong một thí nghiệm nhỏ, có thể dùng `1.0`. [Spring Boot 3.3: cấu hình lấy mẫu tracing](https://docs.spring.io/spring-boot/3.3/reference/actuator/tracing.html).

| Giá trị | Cách hiểu cho trace gốc thuộc chính sách này |
| --- | --- |
| `0.0` | Không chọn ghi nhận theo quyết định lấy mẫu gốc đó |
| `0.01` | Mục tiêu xác suất 1% |
| `0.1` | Mục tiêu xác suất 10% |
| `1.0` | Chọn ghi nhận theo quyết định lấy mẫu gốc đó |

Giá trị thuộc khoảng `[0, 1]`. `0.1` là 10%, còn `0.01` là 1%; không ghi `10` để biểu diễn 10%.

Bảng này không có nghĩa `0.0` tắt toàn bộ tracer, hoặc `1.0` bảo đảm mọi trace từ mọi nơi đều được lưu. Quyết định cha, sampler tùy chỉnh và các bước phía sau vẫn cần được xét.

### 2.2. Giá trị cấu hình phải thực sự được dùng

Cần kiểm tra profile đang hoạt động, tham số khởi động và các nguồn cấu hình có thể ghi đè. Biến môi trường tương ứng là `MANAGEMENT_TRACING_SAMPLING_PROBABILITY`.

Thuộc tính trên có tác dụng trong đường auto-configuration phù hợp của Boot. Nếu ứng dụng tự cung cấp sampler, tự tạo tracer provider hoặc dùng một cơ chế thu trace khác, không mặc định rằng sửa thuộc tính Boot sẽ thay đổi cơ chế ấy.

Ví dụ trong auto-configuration Boot 3.3.0:

- Với Brave, Boot tạo sampler từ xác suất cấu hình khi chưa có sampler thay thế.
- Với OpenTelemetry, Boot dùng sampler theo tỷ lệ cho trace gốc, được bọc bởi chính sách dựa vào cha.

Đối chiếu với triển khai của [BraveAutoConfiguration](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.0/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/tracing/BraveAutoConfiguration.java) và [OpenTelemetryAutoConfiguration](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.0/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/tracing/OpenTelemetryAutoConfiguration.java).

Giá trị này được đọc để cấu hình các thành phần tracing. Sửa một tệp đang nằm trên đĩa không tự chứng minh sampler của tiến trình đang chạy đã đổi. Trong thí nghiệm thông thường, khởi động lại ứng dụng với cấu hình mới và tạo trace mới để kiểm tra.

## 3. Quyết định lấy mẫu của trace cha có ý nghĩa gì?

### 3.1. Không bốc thăm độc lập cho mọi span

Một trace phân tán có thể đi qua nhiều dịch vụ:

```text
Trace T, quyết định được lấy mẫu ở đầu vào
  -> dịch vụ A
     -> dịch vụ B
        -> dịch vụ C
```

Với chính sách dựa vào cha và truyền ngữ cảnh đúng, các span tiếp nối tôn trọng quyết định từ cha. Mục tiêu là giữ mối liên hệ của trace, thay vì dịch vụ nào cũng chọn bỏ các mảnh khác nhau.

Nếu cả ba dịch vụ cấu hình `0.1`, không được tự kết luận xác suất giữ cả trace bằng `0.1 × 0.1 × 0.1`. Phép nhân ấy giả định ba lần lựa chọn độc lập, trong khi chính sách kế thừa quyết định cha không hoạt động như vậy.

Ngược lại, nếu ngữ cảnh bị mất ở một ranh giới, dịch vụ sau có thể bắt đầu trace gốc mới. Lúc đó vừa mất mối liên hệ, vừa có thể có quyết định lấy mẫu khác.

### 3.2. Hai trường hợp dễ gây nhầm

| Quyết định từ cha | Xác suất cục bộ cho trace mới | Hành vi kế thừa thông thường |
| --- | --- | --- |
| Cha đã được lấy mẫu | `0.0` | Span tiếp nối vẫn có thể được ghi nhận theo quyết định cha |
| Cha không được lấy mẫu | `1.0` | Span tiếp nối vẫn có thể không được ghi nhận theo quyết định cha |

Đây là lý do cần phân biệt “lấy mẫu mọi trace gốc mới của dịch vụ này” với “cưỡng bức lưu mọi span nhận từ mọi nguồn”.

OpenTelemetry cung cấp sampler `ParentBased`, trong đó hành vi với cha đã lấy mẫu/không lấy mẫu và không có cha được phân biệt rõ. [OpenTelemetry Java SDK: các sampler](https://opentelemetry.io/docs/languages/java/sdk/#sampler).

Quy tắc tùy chỉnh có thể thay đổi hành vi kế thừa. Khi điều tra một ứng dụng cụ thể, phải kiểm tra sampler, cơ chế truyền ngữ cảnh và các điều kiện ghi đè thực tế.

### 3.3. Có trace ID chưa chứng minh có trace được lưu

Tracer có thể vẫn duy trì ngữ cảnh để truyền tiếp ngay cả khi span không được chọn ghi nhận/xuất. Vì vậy:

- `currentSpan()` khác `null` không tự chứng minh có dữ liệu span sẽ tới hệ thống lưu trữ.
- Log có trace ID không tự chứng minh trace ID đó tìm được ở nơi truy vấn.
- Không có dữ liệu trong giao diện trace cần được phân biệt với việc ứng dụng không có ngữ cảnh trace.

Thí nghiệm Brave ở phần sau kiểm tra trực tiếp trường hợp có ngữ cảnh hiện tại nhưng không thu được span hoàn tất do quyết định lấy mẫu.

## 4. Xác suất không phải cam kết đếm chính xác trong một cửa sổ nhỏ

### 4.1. Kỳ vọng dài hạn khác kết quả của từng nhóm nhỏ

Trong mô hình đơn giản gồm `N` trace gốc độc lập, mỗi trace có cùng xác suất `p` được giữ, số trace được chọn có kỳ vọng:

```text
E[K] = N × p
```

Ví dụ `N = 1.000`, `p = 0.1` cho kỳ vọng 100 trace. Không suy ra một cửa sổ bất kỳ gồm 10 yêu cầu chắc chắn phải hiển thị đúng một trace.

Thuật toán cụ thể có thể dựa trên trace ID hoặc cách lựa chọn khác. Ngoài ra, số yêu cầu, số trace gốc, số span và số bản ghi đang hiển thị là các đại lượng khác nhau. Kế thừa quyết định cha, tải thay đổi và các bước lọc tiếp theo còn có thể làm tỷ lệ quan sát được khác với xác suất cục bộ.

### 4.2. Một lỗi hiếm rất dễ không có trace đại diện

Giả sử một loại lỗi xảy ra trên `n` trace **độc lập**, mỗi trace có cùng xác suất `p` được giữ, và không có mất dữ liệu ở các bước sau:

```text
P(không giữ được trace lỗi nào) = (1 - p)^n

P(giữ được ít nhất một trace lỗi) = 1 - (1 - p)^n
```

Đây là mô hình xác suất để hiểu độ bao phủ, không phải khẳng định mọi sampler hiện thực các quyết định độc lập theo cách tung đồng xu.

| Số trace độc lập có lỗi | Cơ hội thấy ít nhất một trace, p = 1% | Cơ hội thấy ít nhất một trace, p = 10% |
| --- | --- | --- |
| 1 | 1% | 10% |
| 5 | 4,9010% | 40,9510% |
| 10 | 9,5618% | 65,1322% |
| 100 | 63,3968% | 99,9973% |

Với năm trace lỗi và `p = 10%`, xác suất không giữ được trace lỗi nào trong mô hình vẫn là 59,049%. Vì thế, “không tìm được trace lỗi” là bằng chứng yếu nếu không biết chính sách lấy mẫu và số lần lỗi thực tế.

Năm span lỗi trong **cùng một trace** không tương đương năm trace lỗi độc lập. Nếu chúng dùng chung quyết định lấy mẫu, không áp dụng công thức trên với `n = 5` chỉ vì đếm được năm span.

Ngoài ra, nếu có quy tắc giữ riêng trace lỗi hoặc trace chậm, tập dữ liệu không còn là mẫu đồng đều của toàn bộ lưu lượng. Phải diễn giải theo chính sách thực tế, không áp dụng máy móc công thức cho một mẫu đã được ưu tiên.

## 5. Metric, log và trace có giới hạn dữ liệu khác nhau

### 5.1. Thay xác suất tracing không tự lấy mẫu timer

Trong đường Observation có cả handler metric và handler tracing, quyết định lấy mẫu của tracer không tự loại bỏ các lần ghi timer của handler metric.

Ví dụ có năm lần chạy observation:

```text
p = 0:
  timer count = 5
  span được thu trong thí nghiệm = 0

p = 1:
  timer count = 5
  span được thu trong thí nghiệm = 5
```

Điều này nói về metric được ứng dụng ghi qua `MeterRegistry`. Các thống kê do một hệ thống phía sau tính **từ trace** đã lấy mẫu là trường hợp khác: đầu vào của chúng có thể đã thiếu hoặc bị ưu tiên theo chính sách.

Không dùng số span làm số yêu cầu một cách trực tiếp: một yêu cầu có thể tạo nhiều span, một trace có thể đi qua nhiều dịch vụ, và nhiều trace không được giữ.

### 5.2. Dùng đúng tín hiệu cho đúng câu hỏi

| Câu hỏi | Nguồn thường phù hợp |
| --- | --- |
| Tỷ lệ lỗi tổng thể hoặc lưu lượng trong một khoảng thời gian | Metric được thu với phạm vi và nhãn phù hợp |
| Một lần xử lý cụ thể đã đi qua những bước nào | Trace được giữ và có đủ dữ liệu các ranh giới cần xét |
| Chi tiết sự kiện được ứng dụng chủ động ghi | Log tương ứng, theo chính sách ghi và lưu log |
| Có đủ mọi sự kiện nghiệp vụ cần đối soát không | Cơ chế ghi sự kiện chuyên biệt có hợp đồng đầy đủ rõ ràng |

Tăng xác suất tracing không tự làm metric hoặc log đầy đủ hơn. Ngược lại, có đủ metric tổng hợp không giúp tái tạo chính xác mọi trace đã bị bỏ.

Không suy ra tỷ lệ lỗi tổng thể chỉ từ một tập trace được ưu tiên giữ lỗi/chậm. Tập đó rất hữu ích cho điều tra nhưng có thiên lệch so với toàn bộ lưu lượng. Tương tự, phân vị thời gian tính trực tiếp từ tập trace được ưu tiên giữ trace chậm không tự là phân vị của mọi yêu cầu.

## 6. Head sampling và tail sampling

### 6.1. Head sampling quyết định khi chưa biết tương lai

Lấy mẫu đầu ra quyết định sớm trong vòng đời. Nó có thể dùng thông tin đã biết lúc quyết định, nhưng chưa biết toàn bộ các lỗi và độ trễ sẽ xuất hiện ở các bước sau.

Bởi vậy, chỉ đặt xác suất `0.1` không có nghĩa “giữ 10% trace thành công và giữ toàn bộ trace lỗi”. Nếu trace đã không được ghi nhận từ đầu, một lỗi xuất hiện muộn không tự làm các span đã bỏ trước đó quay lại.

Lấy mẫu đầu có lợi thế giảm dữ liệu cần ghi/xử lý từ sớm. Đổi lại, không thể dựa riêng vào nó để bảo đảm thu mọi lỗi phát sinh trong toàn trace. [OpenTelemetry: head sampling và tail sampling](https://opentelemetry.io/docs/concepts/sampling/).

### 6.2. Tail sampling có thêm thông tin nhưng cần hạ tầng

Lấy mẫu cuối tập hợp các span đã nhận, sau đó áp dụng quy tắc như ưu tiên trace có lỗi hoặc độ trễ cao.

```text
Các dịch vụ tạo/xuất dữ liệu span
  -> thành phần thu thập tập hợp theo trace
     -> quyết định giữ/bỏ theo dữ liệu đã nhận
        -> hệ thống lưu trữ và truy vấn
```

Để quyết định hiệu quả, thành phần này cần nhận được các span liên quan, giữ trạng thái đủ lâu và có đủ tài nguyên. Với Tail Sampling Processor của OpenTelemetry Collector, các span cùng trace cần tới cùng một instance xử lý thích hợp. Còn phải xét span đến muộn, thời gian chờ và giới hạn dữ liệu giữ trong bộ nhớ. [Tài liệu Tail Sampling Processor](https://raw.githubusercontent.com/open-telemetry/opentelemetry-collector-contrib/main/processor/tailsamplingprocessor/README.md).

Một giới hạn quan trọng: **tail sampler không khôi phục dữ liệu đã bị bỏ trước khi tới nó**. Nếu head sampler đã chỉ cho 1% trace đi qua, quy tắc “giữ trace lỗi” phía sau chỉ có thể xét phần dữ liệu lỗi trong số đã tới.

Cũng không diễn giải quy tắc giữ lỗi thành cam kết tuyệt đối rằng mọi trace lỗi ở toàn hệ thống đều được lưu: instrumentation thiếu, mất dữ liệu, đến muộn hoặc giới hạn xử lý vẫn có thể tác động.

Bật thuộc tính xác suất trong Boot không tự triển khai tail sampling. Đây là quyết định kiến trúc của đường thu trace, cần thiết kế và kiểm chứng riêng khi có nhu cầu.

## 7. Ước lượng lượng dữ liệu và chọn cách điều chỉnh

Một ước lượng ban đầu, khi số trace gốc mới là `R` mỗi giây, mỗi trace trung bình có `S` span và tỷ lệ được giữ xấp xỉ `p`:

```text
Số trace được chọn mỗi giây ≈ R × p

Số span được chọn mỗi giây ≈ R × p × S
```

Ví dụ giả định `R = 2.000`, `S = 8`, `p = 0.1`:

```text
Trace được chọn mỗi giây ≈ 200
Span được chọn mỗi giây ≈ 1.600
```

Đây là ước lượng dữ liệu được chọn, không phải cam kết số bản ghi được lưu. Kích thước thuộc tính/sự kiện, thay đổi số span mỗi trace, lấy mẫu đầu/cuối và các giới hạn đường xuất đều ảnh hưởng.

Giảm từ `p = 1` xuống `0.1` trong các giả định tương đương có thể giảm mạnh lượng span được chọn. Không suy ra tổng CPU hoặc mọi chi phí hệ thống cũng giảm đúng mười lần: vẫn có phần công việc nghiệp vụ và chi phí quan sát khác.

Một cách điều chỉnh có thể kiểm chứng:

1. Xác định mục tiêu: học/thử một đường gọi, điều tra lỗi hiếm hay theo dõi lưu lượng thường xuyên.
2. Ghi nhận lưu lượng, số span trung bình và khả năng tiếp nhận của đường thu thập.
3. Chọn xác suất cho môi trường và mục tiêu đó; thử thay đổi trong phạm vi có thể kiểm soát.
4. Tạo trace mới và kiểm tra cấu hình có thực sự tác động tới sampler.
5. Đối chiếu metric tổng hợp với trace nhận được, cùng các dấu hiệu mất dữ liệu/giới hạn xử lý.
6. Đánh giá lại khả năng thấy lỗi hiếm; nếu cần, cân nhắc chính sách ưu tiên hoặc tail sampling thay vì chỉ giảm/tăng một con số.

Không có một tỷ lệ sản phẩm chung đúng cho mọi dịch vụ. Một dịch vụ rất ít lưu lượng và một dịch vụ hàng nghìn trace mỗi giây có nhu cầu giữ dữ liệu khác nhau. Khi tăng tạm xác suất để điều tra, cần biết điểm kết thúc của thay đổi và xác minh khối lượng dữ liệu thực tế.

## 8. Thực nghiệm: xác suất gốc, quyết định cha và metric

### 8.1. Mục tiêu

Chương trình dưới đây kiểm tra bốn tình huống bằng Brave và Micrometer:

1. Không có cha, xác suất cục bộ bằng 0.
2. Không có cha, xác suất cục bộ bằng 1.
3. Có cha đã lấy mẫu, xác suất cục bộ bằng 0.
4. Có cha không lấy mẫu, xác suất cục bộ bằng 1.

Mỗi tình huống chạy năm observation. Handler metric ghi timer; handler tracing nối với Brave; một `SpanHandler` thu span hoàn tất trong bộ nhớ. Không có gửi trace qua mạng.

Chương trình cố định hai biên xác suất 0 và 1 để có stdout xác định. Hai phép tính xác suất ở cuối minh họa mô hình toán học, không dùng số lần lấy mẫu ngẫu nhiên để quyết định kiểm thử thành công hay thất bại.

### 8.2. Dependency trong pom.xml

Dùng JDK 21. Tạo thư mục thực nghiệm riêng và lưu `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>sampling-limits-demo</artifactId>
    <version>1.0.0</version>
    <dependencies>
        <dependency>
            <groupId>io.micrometer</groupId>
            <artifactId>micrometer-core</artifactId>
            <version>1.13.0</version>
        </dependency>
        <dependency>
            <groupId>io.micrometer</groupId>
            <artifactId>micrometer-tracing-bridge-brave</artifactId>
            <version>1.3.0</version>
        </dependency>
        <dependency>
            <groupId>org.slf4j</groupId>
            <artifactId>slf4j-nop</artifactId>
            <version>1.7.36</version>
            <scope>runtime</scope>
        </dependency>
    </dependencies>
</project>
```

Maven giải quyết các dependency bắc cầu của bridge, trong đó có Micrometer Tracing và Brave. Các phiên bản Micrometer 1.13.0/Tracing 1.3.0 thuộc thế hệ thư viện của Boot 3.3.0.

Trong ứng dụng Boot hiện có, tiếp tục dùng dependency management của Boot. Chương trình này cấu hình sampler trực tiếp bằng Java; nó không khởi động Boot và không đọc thuộc tính trong `application.yml`.

### 8.3. Toàn bộ SamplingLimitsDemo.java

Lưu cạnh `pom.xml`, không khai báo package:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

import brave.Tracing;
import brave.handler.MutableSpan;
import brave.handler.SpanHandler;
import brave.propagation.TraceContext;
import brave.sampler.Sampler;
import io.micrometer.core.instrument.observation.DefaultMeterObservationHandler;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import io.micrometer.tracing.Tracer;
import io.micrometer.tracing.brave.bridge.BraveCurrentTraceContext;
import io.micrometer.tracing.brave.bridge.BraveTracer;
import io.micrometer.tracing.handler.DefaultTracingObservationHandler;

public class SamplingLimitsDemo {
    private static final int WORK_COUNT = 5;

    public static void main(String[] args) {
        Result rootZero = run(0.0f, null);
        Result rootOne = run(1.0f, null);
        Result sampledParent = run(0.0f, true);
        Result unsampledParent = run(1.0f, false);

        print("root.p0", rootZero);
        print("root.p1", rootOne);
        print("parent.sampled.local.p0", sampledParent);
        print("parent.not.sampled.local.p1", unsampledParent);
        System.out.println("context.present.when.unsampled="
                + (rootZero.contextSeen() == WORK_COUNT));

        System.out.printf(Locale.ROOT, "chance.p0.1.n5=%.6f%n",
                1.0 - Math.pow(1.0 - 0.1, 5));
        System.out.printf(Locale.ROOT, "chance.p0.01.n5=%.6f%n",
                1.0 - Math.pow(1.0 - 0.01, 5));

        if (rootZero.spans() != 0 || rootOne.spans() != WORK_COUNT
                || sampledParent.spans() != WORK_COUNT
                || unsampledParent.spans() != 0) {
            throw new AssertionError("Unexpected sampling decisions");
        }
    }

    static Result run(float localProbability, Boolean incomingSampled) {
        List<MutableSpan> completed = new ArrayList<>();
        var meters = new SimpleMeterRegistry();
        SpanHandler collector = new SpanHandler() {
            @Override
            public boolean end(TraceContext context, MutableSpan span, Cause cause) {
                completed.add(new MutableSpan(span));
                return true;
            }
        };

        try (Tracing engine = Tracing.newBuilder()
                .localServiceName("sampling-demo")
                .sampler(Sampler.create(localProbability))
                .addSpanHandler(collector)
                .build()) {
            Tracer tracer = new BraveTracer(engine.tracer(),
                    new BraveCurrentTraceContext(engine.currentTraceContext()));
            var registry = ObservationRegistry.create();
            registry.observationConfig()
                    .observationHandler(new DefaultMeterObservationHandler(meters))
                    .observationHandler(new DefaultTracingObservationHandler(tracer));

            TraceContext incoming = incomingSampled == null ? null
                    : TraceContext.newBuilder()
                            .traceId(0x1111111111111111L)
                            .spanId(0x2222222222222222L)
                            .sampled(incomingSampled)
                            .build();
            int[] contextSeen = {0};
            try (var scope = engine.currentTraceContext().newScope(incoming)) {
                for (int i = 0; i < WORK_COUNT; i++) {
                    Observation.createNotStarted("work", registry).observe(() -> {
                        if (tracer.currentSpan() != null) {
                            contextSeen[0]++;
                        }
                    });
                }
            }

            long metricCount = meters.get("work").timer().count();
            if (metricCount != WORK_COUNT
                    || registry.getCurrentObservation() != null
                    || tracer.currentSpan() != null) {
                throw new AssertionError("Unexpected metrics or scope");
            }
            return new Result(metricCount, completed.size(), contextSeen[0]);
        } finally {
            meters.close();
        }
    }

    static void print(String label, Result result) {
        System.out.println(label + ": metrics=" + result.metrics()
                + ", spans=" + result.spans());
    }

    record Result(long metrics, int spans, int contextSeen) {
    }
}
```

`incomingSampled = null` biểu diễn trường hợp không cung cấp ngữ cảnh cha. Hai giá trị boolean còn lại tạo một ngữ cảnh cha giả để kiểm tra kế thừa quyết định. Các ID trong ngữ cảnh cha chỉ là dữ liệu thí nghiệm, không phải dữ liệu từ một dịch vụ thật.

Khi có cha, năm observation là năm span con trong cùng trace được mô phỏng. Khi không có cha, mỗi observation có thể bắt đầu một trace gốc riêng. Vì thế, cột `spans` không được đổi tên thành “số trace” một cách tùy ý.

### 8.4. Biên dịch, chạy và stdout

Trong PowerShell, chọn JDK 21 cho cả `javac` và `java`, có Maven, rồi chạy lần lượt khi lệnh trước thành công:

```powershell
mvn org.apache.maven.plugins:maven-dependency-plugin:3.7.0:build-classpath "-Dmdep.outputFile=classpath.txt"
$demoClasspath = (Get-Content -Raw classpath.txt).Trim()
javac --release 21 -encoding UTF-8 -cp "$demoClasspath" SamplingLimitsDemo.java
java -cp ".;$demoClasspath" SamplingLimitsDemo
```

Lần đầu cần truy cập kho Maven để tải dependency. Dấu `;` trong classpath dùng trên Windows; Linux/macOS dùng `:`.

Stdout của chương trình, không tính thông báo Maven:

```text
root.p0: metrics=5, spans=0
root.p1: metrics=5, spans=5
parent.sampled.local.p0: metrics=5, spans=5
parent.not.sampled.local.p1: metrics=5, spans=0
context.present.when.unsampled=true
chance.p0.1.n5=0.409510
chance.p0.01.n5=0.049010
```

### 8.5. Đọc kết quả đúng phạm vi

| Kết quả | Ý nghĩa |
| --- | --- |
| Hai trường hợp root có 0 và 5 span | Sampler cục bộ chọn/không chọn các trace mới theo hai biên 0 và 1 |
| Cha đã lấy mẫu vẫn có 5 span khi cục bộ bằng 0 | Quyết định cha được giữ trong cấu hình Brave của thí nghiệm |
| Cha không lấy mẫu vẫn có 0 span khi cục bộ bằng 1 | Xác suất cục bộ không tự cưỡng bức ghi lại trace cha đã không chọn |
| Mọi trường hợp đều có `metrics=5` | Các timer của observation vẫn ghi đủ năm lượt trong cùng thí nghiệm |
| `context.present.when.unsampled=true` | Brave vẫn cung cấp ngữ cảnh span hiện tại dù không có span hoàn tất được thu |
| `0.409510` | Xấp xỉ 40,9510% cơ hội thấy ít nhất một trong năm trace độc lập khi p = 10% |
| `0.049010` | Xấp xỉ 4,9010% cơ hội tương ứng khi p = 1% |

Thí nghiệm xác minh cơ chế trong bộ nhớ, không kiểm tra exporter, đầu nhận hay giao diện truy vấn. Nó cũng không chứng minh mọi tracer có cùng chi tiết biểu diễn span không lấy mẫu; kết quả về ngữ cảnh hiện tại ở đây được kiểm tra trực tiếp với Brave.

## 9. Vì sao p = 1 vẫn chưa bảo đảm thấy đầy đủ dữ liệu?

Có nhiều bước từ lời gọi nghiệp vụ tới bản ghi đang xem:

```text
Lời gọi thực tế
  -> mã quan sát có chạy và bao phủ ranh giới đó
  -> quyết định lấy mẫu
  -> span được ghi và kết thúc
  -> exporter/đường truyền
  -> processor/bộ lọc/hệ thống lưu trữ
  -> thời hạn lưu và truy vấn hiện tại
```

Xác suất bằng 1 chỉ tác động đúng phần chính sách mà sampler đó điều khiển. Nó không:

- Tạo span cho phần mã chưa có logic quan sát.
- Khôi phục span đã bị bỏ trước khi thay đổi cấu hình.
- Bảo đảm mọi tác vụ bất đồng bộ và lời gọi mạng đều truyền đúng ngữ cảnh.
- Chữa việc mất dữ liệu do hàng đợi, lỗi xuất, tắt tiến trình hoặc đầu nhận từ chối.
- Bỏ qua bộ lọc, chính sách lưu trữ hoặc điều kiện truy vấn ở bước sau.
- Tự ghi mọi giá trị đầu vào, trạng thái nội bộ và toàn bộ diễn biến nghiệp vụ.

Một trace nhìn thấy cũng có thể thiếu một nhánh hoặc một loại thông tin. Hãy nêu phạm vi dữ liệu thực sự có bằng chứng thay vì suy ra rằng trace đó là bản ghi toàn bộ hành vi hệ thống.

## 10. Kiểm tra khi tỷ lệ quan sát được khác mong đợi

| Hiện tượng | Điều cần kiểm tra |
| --- | --- |
| Đặt 1.0 nhưng không thấy mọi yêu cầu | Có phải trace gốc mới không; cha quyết định gì; sampler thực tế và đường xuất dữ liệu |
| Đặt 0.0 nhưng vẫn có span | Có quyết định lấy mẫu kế thừa hoặc quy tắc ghi đè; có dùng đúng sampler không |
| Mỗi lần thử ít yêu cầu cho tỷ lệ rất khác nhau | Cửa sổ nhỏ; cách đếm request/trace/span; thuật toán và chính sách thực tế |
| Metric báo lỗi nhưng không có trace lỗi | Lấy mẫu có thể không giữ lỗi; instrumentation và đường thu thập có thể thiếu dữ liệu |
| Có trace ID trong log nhưng không tìm được trace | Ngữ cảnh không đồng nghĩa với span đã được xuất và lưu |
| Chỉ thấy nhiều trace chậm/lỗi | Có thể đang xem tập dữ liệu được ưu tiên hoặc một truy vấn đã lọc; không coi là tỷ lệ toàn hệ thống |
| Sửa cấu hình nhưng hành vi không đổi | Nguồn cấu hình ghi đè, sampler tùy chỉnh, hoặc thành phần đang chạy chưa được khởi tạo lại |
| Sau khi bật tail sampling vẫn mất lỗi hiếm | Dữ liệu có tới tail sampler không; head sampling trước đó; định tuyến theo trace và giới hạn xử lý |

Quy trình thí nghiệm trong Boot nên bắt đầu từ một đường gọi đã biết, lượng yêu cầu vừa đủ, trace gốc mới và cấu hình lấy mẫu dễ quan sát. Sau khi xác nhận đường thu dữ liệu hoạt động, mới giảm xác suất và đánh giá độ bao phủ. Không vừa thay sampler, exporter, cơ chế truyền ngữ cảnh và bộ lọc truy vấn rồi dùng một kết quả trống để kết luận tất cả đều sai.

## 11. Bài tập thực hành

1. Chạy chương trình và giải thích vì sao cột metric không thay đổi trong bốn tình huống.
2. Chỉ ra hai dòng chứng minh xác suất cục bộ và quyết định cha không phải cùng một loại đầu vào.
3. Với một lỗi xảy ra trên một trace duy nhất, tính cơ hội có trace đại diện khi p = 1%, 10% và 100%, theo mô hình đơn giản và không mất dữ liệu phía sau.
4. Giải thích vì sao năm lỗi trong cùng một trace không cho năm cơ hội lấy mẫu độc lập.
5. Trong môi trường Boot thử nghiệm đã có tracing, đổi từ 1.0 xuống 0.1, tạo các trace gốc mới và so sánh metric với số trace nhận được. Ghi rõ cửa sổ quan sát và đơn vị đếm.
6. Thiết kế cách ưu tiên điều tra lỗi hiếm; nêu dữ liệu nào phải tới điểm quyết định và phần nào không thể khôi phục nếu bị bỏ từ trước.

Kết luận của một lần điều tra cần gắn với chính sách lấy mẫu, phạm vi quan sát và độ đầy đủ của đường thu dữ liệu. “Chưa thấy bằng chứng trong tập trace đang có” và “hệ thống không xảy ra sự kiện đó” là hai nhận định có mức độ chắc chắn khác nhau.
