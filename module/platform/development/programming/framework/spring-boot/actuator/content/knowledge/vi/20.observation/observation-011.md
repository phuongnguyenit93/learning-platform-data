# Tránh tạo observation lồng không cần thiết khi framework đã tự quan sát

## 1. Vấn đề: thêm điểm đo nhưng không thêm thông tin

Khi muốn biết một API chạy nhanh hay chậm, ta dễ bọc toàn bộ controller bằng một observation tự tạo. Tuy nhiên, trong ứng dụng Spring Boot có cơ chế quan sát Spring MVC hoạt động, yêu cầu HTTP đã có observation ở tầng framework.

Nếu observation mới chỉ bao lại gần như cùng phần xử lý, ta có thêm một vòng đời quan sát nhưng chưa có câu trả lời mới về hệ thống. Vết truy vết (trace) có thể dài hơn, số bộ đo tăng lên và người đọc khó biết hai phép đo khác nhau ở đâu.

Ví dụ một yêu cầu đã được quan sát:

~~~text
http.server.requests
└── xử lý controller và trả phản hồi
~~~

Sau khi bọc controller một lần nữa:

~~~text
http.server.requests
└── app.controller
    └── vẫn cùng phần xử lý controller
~~~

Observation `app.controller` ở đây đáng nghi vì mục tiêu của nó vẫn là “đo toàn bộ API”. Ngược lại, một observation con chỉ đo bước tính giá có thể trả lời câu hỏi riêng: “Trong thời gian xử lý API, bước tính giá chiếm bao nhiêu?”.

Mục tiêu của bài là biết **khi nào dùng lại observation hiện có, khi nào bổ sung thông tin và khi nào tạo một observation con có ý nghĩa**. Số observation ít nhất không phải tiêu chí duy nhất; mỗi ranh giới quan sát cần có mục đích rõ ràng.

Trước khi tự thêm mã quan sát, Micrometer khuyến nghị kiểm tra thành phần đang dùng đã có sẵn cơ chế đo hay chưa. [Micrometer: Instrumentation](https://docs.micrometer.io/micrometer/reference/1.13/observation/instrumenting.html).

## 2. Framework đã quan sát phần nào?

### 2.1. Observation HTTP của Spring MVC

Với Spring Boot 3.3 và các điều kiện cấu hình phù hợp, cơ chế tự cấu hình Spring MVC quan sát các yêu cầu được xử lý bởi controller và bộ xử lý theo hàm (functional handler). Tên mặc định là `http.server.requests`. [Spring Boot 3.3: Spring MVC Metrics](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html#actuator.metrics.supported.spring-mvc).

Trong Servlet stack, `ServerHttpObservationFilter` tham gia vòng đời yêu cầu. Observation HTTP bao quanh chuỗi xử lý phía sau filter, trong đó có quá trình xử lý của Spring MVC. Nó không đồng nhất với riêng thời gian của một phương thức Java trong controller.

Spring Boot có `WebMvcObservationAutoConfiguration` để đăng ký filter tương ứng khi ứng dụng Servlet, các lớp cần thiết và bean `ObservationRegistry` hiện diện. Vì vậy cần kiểm tra cấu hình thực tế thay vì suy luận rằng chỉ cần có một controller là chắc chắn có dữ liệu quan sát. [Javadoc WebMvcObservationAutoConfiguration](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/autoconfigure/observation/web/servlet/WebMvcObservationAutoConfiguration.html).

### 2.2. Ranh giới có sẵn cần được hiểu trước khi bọc thêm

| Thành phần đang xem xét | Điều cần kiểm tra trước khi tự đo |
| --- | --- |
| Controller Spring MVC | Observation HTTP của framework có đang hoạt động không? |
| Lời gọi HTTP ra ngoài | HTTP client đã được cấu hình registry và cơ chế quan sát chưa? |
| Phương thức có `@Observed` | Aspect xử lý annotation có hoạt động và lời gọi có đi qua proxy không? |
| Thư viện truy cập dữ liệu hoặc messaging | Phiên bản và cấu hình hiện tại có cung cấp điểm đo cho thao tác này không? |
| Tác vụ ngoài yêu cầu HTTP | Có ranh giới quan sát từ scheduler, listener hoặc mã gọi phía ngoài chưa? |

Bảng này là các câu hỏi kiểm tra, không khẳng định mọi thư viện đều được Spring Boot tự quan sát với mọi cấu hình. Cần xem đúng phiên bản và cách khởi tạo thành phần.

Các annotation cũng cần được phân biệt. `@Observed` khi được xử lý có thể tạo observation; `@Timed` có thể bổ sung phép đo thời gian ở tầng metric. Không quy mọi dữ liệu bị trùng về một cơ chế duy nhất.

## 3. Observation lồng hợp lệ và observation lồng dư thừa

**Observation lồng (nested observation)** là observation được tạo trong khi một observation khác đang là observation hiện hành trong phạm vi thực thi. Observation phía trong có thể liên kết với observation cha.

Quan hệ cha–con mô tả cấu trúc xử lý, không tự chứng minh việc thêm observation là đúng hoặc sai.

### 3.1. Ba tiêu chí để quyết định

Trước khi thêm observation, hãy xác định:

1. **Đơn vị công việc:** Nó đại diện cho yêu cầu HTTP, lời gọi dịch vụ hay một bước nghiệp vụ cụ thể?
2. **Ranh giới thời gian:** Nó bắt đầu và kết thúc khác phần đã được đo ở điểm nào?
3. **Câu hỏi chẩn đoán:** Nếu bỏ nó đi, thông tin cần thiết nào sẽ mất?

Nếu cả ba câu trả lời gần như trùng với observation có sẵn, ưu tiên dùng dữ liệu hiện có hoặc bổ sung siêu dữ liệu (metadata).

| Tình huống | Đánh giá | Hướng xử lý |
| --- | --- | --- |
| Bọc toàn bộ controller chỉ để biết API mất bao lâu | Thường đo lại mục tiêu của HTTP server observation | Dùng observation HTTP |
| Thêm `@Observed` vào controller đã được framework quan sát, không có mục đích riêng | Có nguy cơ tạo thêm observation dư thừa | Bỏ điểm đo bổ sung hoặc thiết kế lại ranh giới |
| Thêm nhãn “loại nghiệp vụ” vào yêu cầu HTTP | Cần thêm thông tin, không nhất thiết cần thêm vòng đời | Bổ sung vào observation/ngữ cảnh hiện có |
| Đo bước định giá bên trong quy trình thanh toán | Có thể trả lời câu hỏi riêng | Tạo observation nghiệp vụ tại bước đó |
| Một lời gọi HTTP client nằm trong yêu cầu HTTP server | Hai thao tác khác nhau | Giữ quan hệ cha–con nếu cấu hình đúng |
| Bọc từng hàm định dạng, getter và phép tính nhỏ | Dễ tăng nhiễu mà ít giá trị | Chọn những bước thực sự cần chẩn đoán |

Spring Boot cảnh báo việc áp dụng annotation quan sát lên các lớp/phương thức đã được đo bởi framework có thể tạo dữ liệu quan sát trùng. Cần lựa chọn cơ chế sở hữu điểm đo theo mục đích của ứng dụng. [Spring Boot 3.3: Observability](https://docs.spring.io/spring-boot/3.3/reference/actuator/observability.html).

### 3.2. Chi phí và ý nghĩa dữ liệu

Observation dư thừa có thể làm tăng số lần gọi bộ xử lý (handler), số bộ đo (meter) hoặc số span khi các thành phần tương ứng được cài đặt. Mức tăng phụ thuộc cấu hình thực tế; không có quy tắc rằng mọi observation luôn xuất đúng một span ra ngoài.

Một hậu quả khác là **diễn giải sai**:

- Hai timer tên khác nhau có thể cùng đo phần lớn thời gian của một yêu cầu.
- Tổng số lần ghi của tất cả timer không tương đương số yêu cầu HTTP.
- Thời gian cha thường đã bao gồm thời gian con; cộng cả hai sẽ đếm chồng khoảng thời gian.
- Đổi tên observation bọc controller làm nó khác tên observation HTTP, nhưng không tự tạo thêm ý nghĩa nghiệp vụ.

Ví dụ giả định: yêu cầu HTTP mất 25 ms, trong đó bước tính giá mất 15 ms. Không được suy ra tổng xử lý là 40 ms bằng cách cộng hai phép đo. Cũng không lấy các phân vị p95 của hai timer để trừ ra một “p95 thời gian còn lại”.

## 4. Bổ sung thông tin vào observation đang có

### 4.1. Dùng observation hiện hành khi cần đúng phạm vi hiện hành

Đoạn mã sau minh họa việc bổ sung một nhãn trong mã đã có `ObservationRegistry` được tiêm:

~~~java
Observation current = registry.getCurrentObservation();
if (current != null) {
    current.lowCardinalityKeyValue("business.operation", "checkout.preview");
}
~~~

Đây là đoạn tích hợp vào một phương thức hiện có, không phải chương trình độc lập.

Nó không tạo observation mới. Tuy nhiên, `current` là observation hiện hành gần nhất: nếu đã ở trong observation con của một thư viện hoặc bước nghiệp vụ, nhãn sẽ được gắn vào observation đó. Vì vậy cần xác định đúng đối tượng muốn bổ sung thông tin.

Không gọi `start()`, `stop()` hoặc tự kết thúc scope của observation do framework sở hữu. Framework chịu trách nhiệm đóng vòng đời của nó. Mã ứng dụng chỉ bổ sung dữ liệu khi cần.

### 4.2. Chọn đúng ngữ cảnh của yêu cầu HTTP trong Spring MVC

Khi đang xử lý một yêu cầu Servlet và muốn bổ sung thông tin cho chính observation HTTP, có thể tìm ngữ cảnh qua request:

~~~java
ServerHttpObservationFilter.findObservationContext(request)
        .ifPresent(context -> context.addLowCardinalityKeyValue(
                KeyValue.of("business.operation", "checkout.preview")));
~~~

Các kiểu cần dùng:

~~~java
import jakarta.servlet.http.HttpServletRequest;
import io.micrometer.common.KeyValue;
import org.springframework.web.filter.ServerHttpObservationFilter;
~~~

API trả về `Optional` vì ngữ cảnh có thể không tồn tại. Không coi việc không tìm thấy ngữ cảnh là lý do tự động tạo một observation HTTP thay thế ngay trong controller.

Spring Framework cung cấp ngữ cảnh request và các điểm mở rộng như `ServerRequestObservationConvention` để đóng góp metadata cho observation HTTP. [Spring Framework: Observability Support](https://docs.spring.io/spring-framework/reference/integration/observability.html).

### 4.3. Chọn điểm mở rộng phù hợp

| Phạm vi bổ sung thông tin | Cách tiếp cận |
| --- | --- |
| Một nhãn của yêu cầu đang xử lý | Bổ sung vào ngữ cảnh request hiện có |
| Quy tắc nhãn HTTP dùng thống nhất cho ứng dụng | Tùy biến `ServerRequestObservationConvention` |
| Bổ sung/xử lý ngữ cảnh ở cuối observation | Cân nhắc `ObservationFilter` với kiểm tra đúng loại context |
| Đo một bước nghiệp vụ có ranh giới riêng | Tạo observation mới tại bước đó |

Nếu mở rộng convention mặc định và muốn giữ các nhãn mặc định, cần giữ phần dữ liệu từ convention gốc. Việc thay toàn bộ convention có thể làm mất thông tin như method, status hoặc mẫu đường dẫn nếu không triển khai đầy đủ.

Nhãn `business.operation` nên có tập giá trị hữu hạn, chẳng hạn `checkout.preview` hoặc `checkout.submit`. Không dùng mã đơn hàng hay toàn bộ URL có định danh làm nhãn low cardinality.

### 4.4. Observation hiện hành không phải cơ chế chống trùng toàn cục

Không áp dụng quy tắc “có current observation thì bỏ mọi observation mới”. Một yêu cầu đang có observation HTTP vẫn có thể cần observation con cho bước định giá hoặc một lời gọi ra ngoài.

Ngược lại, `getCurrentObservation() == null` có thể đến từ việc không có phạm vi hiện hành (scope), cơ chế quan sát bị tắt, dùng sai registry hoặc mất ngữ cảnh khi đổi luồng. Tạo một observation gốc mới có thể che giấu lỗi truyền ngữ cảnh thay vì giải quyết nó.

Micrometer phân biệt việc tạo observation và truyền ngữ cảnh; quan hệ cha–con cần được bảo toàn theo đúng phạm vi thực thi. [Micrometer: Instrumentation](https://docs.micrometer.io/micrometer/reference/1.13/observation/instrumenting.html).

## 5. Thực hành: quan sát ba cách xử lý một yêu cầu

### 5.1. Mục tiêu và giới hạn của thí nghiệm

Chương trình dùng Spring MVC **6.1.8** và Micrometer **1.13.0**, tương ứng bộ phiên bản do Spring Boot **3.3.0** quản lý. Mã biên dịch với `--release 17` và đã chạy trên JDK 21.

Ba endpoint trong thí nghiệm có mục đích khác nhau:

- `/duplicate` tạo thêm observation bao quanh xử lý controller.
- `/enrich` chỉ thêm một nhãn vào observation HTTP.
- `/business` tạo observation con cho bước tính giá.

Ta dùng `MockMvc` để gửi yêu cầu qua cơ chế xử lý Spring MVC mà không mở cổng mạng. Nó sử dụng `DispatcherServlet` và các đối tượng Servlet giả lập, không chỉ gọi trực tiếp phương thức controller. [Spring Framework: MockMvc Overview](https://docs.spring.io/spring-framework/reference/testing/mockmvc/overview.html).

**Trong thí nghiệm độc lập này, ta chủ động đăng ký đúng một `ServerHttpObservationFilter` vào MockMvc.** Filter thật của Spring tạo observation HTTP cho mỗi yêu cầu. Đây là cách dựng môi trường kiểm chứng; trong ứng dụng Spring Boot thực tế đã được tự cấu hình, không sao chép việc đăng ký filter này để thêm một filter quan sát nữa.

MockMvc cho phép đăng ký filter vào chuỗi xử lý yêu cầu bằng `addFilters(...)`. [Spring Framework: Filter Registrations](https://docs.spring.io/spring-framework/reference/testing/mockmvc/hamcrest/filters.html).

### 5.2. Tệp dependency

Tạo cấu trúc:

~~~text
observation-boundary-lab/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── example/
                └── ObservationBoundaryLab.java
~~~

Nội dung `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.0</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>observation-boundary-lab</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-webmvc</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-test</artifactId>
        </dependency>
        <dependency>
            <groupId>io.micrometer</groupId>
            <artifactId>micrometer-core</artifactId>
        </dependency>
        <dependency>
            <groupId>jakarta.servlet</groupId>
            <artifactId>jakarta.servlet-api</artifactId>
        </dependency>
    </dependencies>
</project>
~~~

Parent được dùng để quản lý phiên bản thư viện. Chương trình này không khởi động một ứng dụng Spring Boot bằng `SpringApplication`; registry và filter được dựng rõ ràng trong môi trường thí nghiệm.

`spring-test` được đặt ở classpath của chương trình vì chính hàm `main` sử dụng MockMvc. Trong dự án ứng dụng thông thường, thư viện kiểm thử nên nằm ở phạm vi kiểm thử phù hợp.

### 5.3. Chương trình đầy đủ

Nội dung `src/main/java/example/ObservationBoundaryLab.java`:

~~~java
package example;

import java.util.ArrayList;
import java.util.List;
import java.util.logging.Level;
import java.util.logging.Logger;

import jakarta.servlet.http.HttpServletRequest;
import io.micrometer.common.KeyValue;
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.observation.DefaultMeterObservationHandler;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationHandler;
import io.micrometer.observation.ObservationRegistry;

import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.test.web.servlet.request.MockMvcRequestBuilders;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.filter.ServerHttpObservationFilter;

public class ObservationBoundaryLab {
    public static void main(String[] args) throws Exception {
        Logger.getLogger("").setLevel(Level.OFF);
        SimpleMeterRegistry meters = new SimpleMeterRegistry();
        try {
            ObservationRegistry registry = ObservationRegistry.create();
            Recorder recorder = new Recorder();
            registry.observationConfig()
                    .observationHandler(new DefaultMeterObservationHandler(meters))
                    .observationHandler(recorder);
            PricingService pricing = new PricingService(registry);
            MockMvc mvc = MockMvcBuilders
                    .standaloneSetup(new CheckoutController(registry, pricing))
                    .addFilters(new ServerHttpObservationFilter(registry))
                    .build();
            for (String path : List.of("/duplicate", "/enrich", "/business")) {
                MvcResult result = mvc.perform(MockMvcRequestBuilders.get(path)).andReturn();
                List<Stopped> events = recorder.drain();
                System.out.println("REQUEST " + path + " status="
                        + result.getResponse().getStatus() + " body="
                        + result.getResponse().getContentAsString());
                for (Stopped event : events) {
                    System.out.println("STOP " + event.name() + " parent="
                            + event.parent() + " operation=" + event.operation());
                }
                Timer timer = meters.find("http.server.requests").tag("uri", path).timer();
                System.out.println("OBSERVATIONS " + path + "=" + events.size());
                System.out.println("SERVER_TIMER " + path + "="
                        + (timer == null ? 0 : timer.count()));
            }
            long requests = meters.find("http.server.requests").timers().stream()
                    .mapToLong(Timer::count).sum();
            System.out.println("TOTAL_SERVER_REQUESTS=" + requests);
        } finally {
            meters.close();
        }
    }

    record Stopped(String name, String parent, String operation) { }

    static class Recorder implements ObservationHandler<Observation.Context> {
        private final List<Stopped> stopped = new ArrayList<>();

        @Override
        public boolean supportsContext(Observation.Context context) {
            return true;
        }

        @Override
        public void onStop(Observation.Context context) {
            String parent = context.getParentObservation() == null ? "none"
                    : context.getParentObservation().getContextView().getName();
            KeyValue operation = context.getLowCardinalityKeyValue("business.operation");
            stopped.add(new Stopped(context.getName(), parent,
                    operation == null ? "none" : operation.getValue()));
        }

        List<Stopped> drain() {
            List<Stopped> events = new ArrayList<>(stopped);
            stopped.clear();
            return events;
        }
    }

    static class PricingService {
        private final ObservationRegistry registry;

        PricingService(ObservationRegistry registry) {
            this.registry = registry;
        }

        int calculate() {
            return Observation.createNotStarted("demo.price.calculate", registry)
                    .observe(() -> 2 * 50 + 20);
        }
    }

    @RestController
    static class CheckoutController {
        private final ObservationRegistry registry;
        private final PricingService pricing;

        CheckoutController(ObservationRegistry registry, PricingService pricing) {
            this.registry = registry;
            this.pricing = pricing;
        }

        @GetMapping("/duplicate")
        String duplicate() {
            return Observation.createNotStarted("demo.controller", registry)
                    .observe(() -> "120");
        }

        @GetMapping("/enrich")
        String enrich(HttpServletRequest request) {
            ServerHttpObservationFilter.findObservationContext(request)
                    .ifPresent(context -> context.addLowCardinalityKeyValue(
                            KeyValue.of("business.operation", "checkout.preview")));
            return "120";
        }

        @GetMapping("/business")
        String business() {
            return Integer.toString(pricing.calculate());
        }
    }
}
~~~

Trong mã:

- `DefaultMeterObservationHandler` ghi timer vào registry trong bộ nhớ.
- `Recorder` ghi nhận sự kiện `onStop` để kiểm tra tên, observation cha và nhãn nghiệp vụ.
- Cả filter, controller và service dùng chung một `ObservationRegistry`.
- Các yêu cầu MockMvc được chạy đồng bộ, tuần tự; vì vậy `Recorder` dùng `ArrayList` trong thí nghiệm này.
- `PricingService.calculate()` là một bước độc lập có tên riêng. Phép tính nhỏ chỉ giúp ví dụ chạy được; trong hệ thống thật, chỉ thêm điểm đo nếu có nhu cầu phân tích bước đó.

`Recorder` không phải bộ thu thập dùng cho môi trường phục vụ nhiều yêu cầu đồng thời. Không sao chép cấu trúc lưu danh sách đơn giản này làm cơ chế giám sát cho môi trường vận hành thực tế.

### 5.4. Biên dịch và chạy

Với Maven và JDK 17 trở lên, chạy tại thư mục chứa `pom.xml`. Ví dụ lệnh PowerShell/Windows:

~~~powershell
mvn -q dependency:copy-dependencies -DoutputDirectory=lib
New-Item -ItemType Directory -Path out -Force | Out-Null
javac --release 17 -encoding UTF-8 -cp "lib/*" -d out src/main/java/example/ObservationBoundaryLab.java
java -cp "out;lib/*" example.ObservationBoundaryLab
~~~

Trên Linux/macOS:

~~~shell
mvn -q dependency:copy-dependencies -DoutputDirectory=lib
mkdir -p out
javac --release 17 -encoding UTF-8 -cp "lib/*" -d out src/main/java/example/ObservationBoundaryLab.java
java -cp "out:lib/*" example.ObservationBoundaryLab
~~~

Lần đầu cần tải dependency nếu máy chưa có sẵn. Chương trình không cần hệ thống giám sát bên ngoài. Nó kết thúc sau ba yêu cầu và đóng `SimpleMeterRegistry` trong `finally`.

### 5.5. Stdout

~~~text
REQUEST /duplicate status=200 body=120
STOP demo.controller parent=http.server.requests operation=none
STOP http.server.requests parent=none operation=none
OBSERVATIONS /duplicate=2
SERVER_TIMER /duplicate=1
REQUEST /enrich status=200 body=120
STOP http.server.requests parent=none operation=checkout.preview
OBSERVATIONS /enrich=1
SERVER_TIMER /enrich=1
REQUEST /business status=200 body=120
STOP demo.price.calculate parent=http.server.requests operation=none
STOP http.server.requests parent=none operation=none
OBSERVATIONS /business=2
SERVER_TIMER /business=1
TOTAL_SERVER_REQUESTS=3
~~~

## 6. Đọc bằng chứng và rút ra quyết định

### 6.1. `/duplicate`: có thêm vòng đời nhưng chưa có mục tiêu riêng

~~~text
http.server.requests
└── demo.controller
~~~

`demo.controller` được tạo trong scope HTTP nên nhận `http.server.requests` làm cha. Observation con dừng trước observation cha, đúng với các dòng `STOP`.

Endpoint chỉ trả `"120"` và không đo một bước nghiệp vụ tách biệt. Nếu mục tiêu chỉ là theo dõi toàn bộ API này, observation HTTP đã cung cấp ranh giới phù hợp.

`OBSERVATIONS /duplicate=2` đếm hai vòng đời observation trong thí nghiệm. `SERVER_TIMER /duplicate=1` cho biết timer HTTP ghi đúng một yêu cầu. **Hai observation tên khác nhau không có nghĩa timer `http.server.requests` đã bị tăng thành hai lần.**

Vấn đề ở đây là một điểm đo bổ sung ít ý nghĩa và khả năng người dùng tổng hợp nhầm dữ liệu, không phải khẳng định mọi observation lồng đều làm bộ đếm HTTP tăng gấp đôi.

### 6.2. `/enrich`: bổ sung thông tin, giữ một observation

~~~text
http.server.requests
  business.operation=checkout.preview
~~~

Không có observation con. Nhãn nghiệp vụ được tìm thấy trong ngữ cảnh HTTP tại thời điểm dừng:

~~~text
STOP http.server.requests parent=none operation=checkout.preview
OBSERVATIONS /enrich=1
~~~

Đây là cách phù hợp khi nhu cầu chỉ là phân loại thêm yêu cầu hiện có.

Trong ứng dụng thật, cần chọn bộ nhãn và tập giá trị thống nhất. Một nhãn mới có thể phân tách metric thành các chuỗi dữ liệu mới, dù không tạo thêm observation.

### 6.3. `/business`: observation con có mục đích riêng

~~~text
http.server.requests
└── demo.price.calculate
~~~

Observation HTTP trả lời câu hỏi về yêu cầu ở tầng web. `demo.price.calculate` trả lời câu hỏi về bước định giá và có thể được dùng khi bước này được gọi từ nhiều luồng nghiệp vụ khác nhau.

Kết quả có hai observation giống về số lượng với `/duplicate`, nhưng ý nghĩa khác nhau. Không thể đánh giá chất lượng chỉ bằng số node trong cây.

Trong thí nghiệm không có tracing bridge/exporter. Quan hệ `parent=...` được đọc từ ngữ cảnh observation; nó là bằng chứng về quan hệ observation, không phải ảnh chụp một trace đã gửi tới backend.

### 6.4. Ba yêu cầu, năm observation

Kết quả gồm:

| Endpoint | Số observation dừng | Số lần ghi timer HTTP |
| --- | --- | --- |
| `/duplicate` | 2 | 1 |
| `/enrich` | 1 | 1 |
| `/business` | 2 | 1 |
| Tổng | 5 | 3 |

`TOTAL_SERVER_REQUESTS=3` khớp số yêu cầu gửi vào. Không cộng số lần ghi của mọi timer hoặc mọi observation rồi gọi đó là “số request”.

## 7. Sở hữu vòng đời và bảo toàn ngữ cảnh

### 7.1. Thành phần tạo observation chịu trách nhiệm vòng đời

Với observation HTTP, framework bắt đầu và kết thúc observation. Controller có thể đóng góp thông tin, nhưng không tự dừng observation đó trước khi framework hoàn tất phản hồi.

Với observation nghiệp vụ do mình tạo, mã ứng dụng chịu trách nhiệm quản lý vòng đời. Trong mã đồng bộ, `observe(...)` giúp bao thao tác, quản lý scope và kết thúc observation theo luồng thực thi.

Nếu quản lý thủ công, cần mở/đóng scope, ghi nhận lỗi và dừng observation đầy đủ. Một observation đã được `start()` chưa đồng nghĩa rằng nó đã trở thành observation hiện hành cho mọi đoạn mã phía sau. [Micrometer: Observation Components](https://docs.micrometer.io/micrometer/reference/1.13/observation/components.html).

### 7.2. Dùng cùng registry phù hợp

Trong ứng dụng Spring Boot, nhận `ObservationRegistry` qua dependency injection. Không tạo một registry mới trong mỗi service chỉ để tránh quan hệ cha–con. Cách đó có thể tách điểm đo khỏi các handler và cấu hình của ứng dụng.

Thí nghiệm tạo registry thủ công vì nó là chương trình độc lập. Trong thí nghiệm, tất cả thành phần vẫn dùng chung registry đó và các handler được đăng ký rõ ràng.

### 7.3. Đổi luồng không làm mất nhu cầu về quan hệ cha–con

Ví dụ chỉ bao phủ xử lý đồng bộ của Spring MVC. Khi chuyển sang executor hoặc chuỗi reactive, cần truyền ngữ cảnh bằng cơ chế phù hợp.

Không chữa việc mất parent bằng cách tạo một root observation mới ở mỗi luồng. Trước hết hãy kiểm tra cơ chế truyền ngữ cảnh và thời điểm subscription/thực thi. Với xử lý bất đồng bộ, vòng đời thực tế của công việc có thể kéo dài hơn lời gọi phương thức trả về.

Spring Boot có hỗ trợ truyền ngữ cảnh, đồng thời lưu ý rằng khôi phục giá trị `ThreadLocal` trong chuỗi reactive phụ thuộc cấu hình. [Spring Boot 3.3: Observability](https://docs.spring.io/spring-boot/3.3/reference/actuator/observability.html).

## 8. Quy trình xử lý khi phát hiện điểm đo trùng

1. **Ghi nhận một lần thực thi cụ thể.** Xác định yêu cầu hoặc thao tác nào tạo ra những observation nào, thay vì chỉ nhìn tổng số meter.
2. **Tìm nơi sở hữu từng điểm đo.** Phân biệt framework, annotation đã được kích hoạt, mã thủ công, interceptor và agent.
3. **So sánh mục đích và ranh giới.** Cùng một khoảng xử lý nhưng hai tên khác nhau vẫn có thể là dư thừa.
4. **Chọn cách giữ thông tin cần thiết.** Bỏ lớp bọc không có mục đích riêng; chuyển nhãn vào context/convention; giữ observation con đo bước nghiệp vụ cần phân tích.
5. **Kiểm tra lại bằng chứng.** Đảm bảo số yêu cầu, nhãn, quan hệ cha–con và việc ghi nhận lỗi vẫn đúng sau thay đổi.

Nếu chưa thể sửa ngay mã tạo observation thừa, có thể dùng chính sách chặn observation có mục tiêu trong registry do Spring Boot quản lý. Đây là giải pháp cần được kiểm chứng theo đúng tên và phạm vi; nó không làm đoạn mã bọc thừa tự biến mất.

Không tắt toàn bộ observation HTTP chỉ vì xuất hiện một lớp bọc controller dư thừa. Quyết định giữ hoặc thay cơ chế framework cần tính tới metadata HTTP, vòng đời lỗi và truyền ngữ cảnh mà cơ chế đó cung cấp.

Nếu chỉ lọc metric, vòng đời observation hoặc phần tracing vẫn có thể còn. Phải xác định đang xử lý trùng ở tầng observation, meter hay span. Các điểm đo do agent độc lập cung cấp cũng cần được kiểm tra ở chính cơ chế của agent.

## 9. Lỗi thường gặp

| Cách làm | Vì sao dễ sai | Cách xử lý |
| --- | --- | --- |
| Gắn `@Observed` lên mọi controller cho chắc | Có thể bọc lại thao tác framework đã quan sát | Kiểm tra điểm đo có sẵn và mục tiêu từng annotation |
| Vừa dùng `@Observed` vừa gọi `Observation.observe(...)` quanh cùng thao tác | Có thể tạo hai ranh giới cùng ý nghĩa khi aspect hoạt động | Chọn một nơi sở hữu điểm đo |
| Đặt tên mới cho lớp bọc rồi coi là đã hết trùng | Tên khác không thay đổi phần công việc được đo | So sánh ranh giới và câu hỏi chẩn đoán |
| Tạo observation mới chỉ để thêm một nhãn | Thêm vòng đời không cần thiết | Bổ sung metadata vào ngữ cảnh phù hợp |
| Luôn bỏ observation con khi current khác null | Mất khả năng phân tích bước nghiệp vụ riêng | Đánh giá ý nghĩa của thao tác con |
| Tự dừng observation HTTP trong controller | Kết thúc vòng đời do framework sở hữu quá sớm | Để framework quản lý vòng đời |
| Tạo registry mới để không thấy parent | Tách khỏi cấu hình và handler chung | Dùng registry được tiêm |
| Kiểm thử bằng cách gọi thẳng phương thức controller rồi kết luận framework không tạo observation | Không đi qua chuỗi filter của yêu cầu | Kiểm thử đúng luồng MVC với filter hoặc chạy ứng dụng đầy đủ |
| Thấy hai observation và kết luận số request bị gấp đôi | Nhầm đơn vị đếm giữa các phép đo | Đọc timer HTTP và tên từng observation riêng |
| Dùng `ArrayList` của thí nghiệm cho máy chủ nhiều luồng | Bộ ghi sự kiện của ví dụ chỉ dành cho luồng kiểm chứng tuần tự | Dùng handler/exporter phù hợp và cấu trúc an toàn khi đồng thời |

## 10. Bài tập tự kiểm chứng

Thay đổi từng yếu tố trong chương trình và chạy lại:

1. Bỏ lớp bọc `demo.controller` ở `duplicate()`, chỉ trả `"120"`. Endpoint phải còn một observation HTTP và timer HTTP vẫn ghi một lần.
2. Đổi giá trị nhãn ở `enrich()` thành `checkout.submit`. Tên observation và số observation không đổi; chỉ dữ liệu phân loại nghiệp vụ thay đổi.
3. Thêm một nhãn riêng có tập giá trị hữu hạn vào `demo.price.calculate`. Kiểm tra nhãn thuộc bước nghiệp vụ; không mặc định rằng nó tự được sao chép lên observation HTTP.
4. Thử gọi trực tiếp `duplicate()` ngoài chuỗi MockMvc và đối chiếu. Đây là một lần gọi Java khác với yêu cầu đi qua filter; không dùng nó để phủ nhận cơ chế HTTP của framework.
5. Giải thích vì sao tổng có thể là năm observation nhưng chỉ có ba yêu cầu HTTP.
6. Với một endpoint trong dự án thật, ghi ra ba điều trước khi thêm điểm đo: đơn vị công việc, điểm bắt đầu/kết thúc và câu hỏi cần trả lời. Nếu cả ba đều trùng với observation sẵn có, chọn cách bổ sung thông tin thay vì bọc thêm.

Một thiết kế quan sát dễ sử dụng cần có ranh giới rõ, người sở hữu vòng đời rõ và dữ liệu đủ để trả lời câu hỏi chẩn đoán. Observation con hữu ích khi nó làm rõ một phần công việc; metadata hữu ích khi ta chỉ cần hiểu thêm về observation đã tồn tại.
