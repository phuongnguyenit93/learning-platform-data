# Cấu hình key-value chung và bật hoặc tắt nhóm observation

## 1. Bài toán: cùng một ứng dụng, nhiều phép đo

Giả sử dịch vụ thanh toán có các thao tác `checkout.calculate`, `checkout.audit.persist` và `checkout.audit.preview`. Khi xem dữ liệu giám sát, ta muốn trả lời hai câu hỏi:

- Phép đo này đến từ dịch vụ, môi trường và khu vực nào?
- Trong môi trường hiện tại, những nhóm thao tác nào cần được quan sát?

**Key-value chung** giải quyết câu hỏi thứ nhất bằng các cặp khóa–giá trị dùng chung. **Cấu hình bật/tắt observation** giải quyết câu hỏi thứ hai bằng chính sách theo tên phép quan sát.

Một observation là sự kiện quan sát một thao tác cùng vòng đời và ngữ cảnh của nó. `ObservationRegistry` giữ các thành phần xử lý observation; `MeterRegistry` giữ các bộ đo như timer, counter. Hai registry có trách nhiệm khác nhau.

Trong bài này, “nhóm observation” là các tên có chung một nhánh, ví dụ `checkout.audit`. Đây là cách tổ chức tên để áp dụng chính sách; không phải một loại bean riêng, nhóm health hay nhóm endpoint Actuator.

Bài thực hành dùng Spring Boot **3.3.0**, Micrometer **1.13.0** và mã Java tương thích **Java 17 trở lên**. Ví dụ đã được biên dịch với `javac --release 17` và chạy bằng JDK 21. Các kết quả bên dưới gắn với cấu hình và phiên bản của ví dụ.

## 2. Hai nhóm thuộc tính cần phân biệt

| Thuộc tính | Câu hỏi được giải quyết | Ví dụ |
| --- | --- | --- |
| `management.observations.key-values.<key>` | Gắn thông tin chung gì vào observation? | `region=vn-south` |
| `management.observations.enable.<name>` | Cho phép observation thuộc tên/nhánh nào? | `checkout.audit=false` |

Spring Boot liên kết cấu hình dưới `management.observations` vào `ObservationProperties`. `key-values` là bản đồ chuỗi–chuỗi; `enable` là bản đồ chuỗi–boolean. [Javadoc ObservationProperties](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/autoconfigure/observation/ObservationProperties.html).

### 2.1. Key-value chung là nhãn có ít giá trị khác nhau

Cấu hình trong `application.properties`:

~~~properties
spring.application.name=checkout-demo

management.observations.key-values.service=${spring.application.name}
management.observations.key-values.region=vn-south
management.observations.key-values.environment=lab
~~~

Ý nghĩa trong ví dụ:

- `service` nhận giá trị `checkout-demo` từ cấu hình tên ứng dụng.
- `region` phân biệt khu vực triển khai.
- `environment` phân biệt môi trường chạy.

Tên nhãn `service` do ta chọn; dòng `spring.application.name` tự nó không có nghĩa rằng mọi meter đều có nhãn `service`. Chính dòng `management.observations.key-values.service` tạo liên kết đó trong ví dụ.

Spring Boot thêm các cặp này dưới dạng khóa–giá trị có số lượng giá trị khác nhau thấp, gọi là **low cardinality**. Chúng có thể trở thành nhãn metric và thông tin của trace khi các bộ xử lý tương ứng được cấu hình. [Spring Boot 3.3: Common Tags](https://docs.spring.io/spring-boot/3.3/reference/actuator/observability.html#actuator.observability.common-tags).

Nhãn chung nên mô tả ứng dụng hoặc môi trường và ổn định trong quá trình chạy. Không đặt `orderId`, `requestId`, email, token hoặc URL chứa mã định danh vào cấu hình nhãn chung. Một nhãn có tên bình thường vẫn gây tăng số chuỗi dữ liệu nếu giá trị của nó thay đổi theo từng yêu cầu.

Ví dụ thiết kế: nếu có 2 khu vực, 3 môi trường và 2 kênh giao dịch, một tên metric có thể phân thành tới `2 × 3 × 2 = 12` tổ hợp nhãn nếu mọi tổ hợp đều xuất hiện. Thêm 100.000 mã đơn hàng có thể làm số tổ hợp tăng rất lớn. Đây là lý do phải kiểm soát tập giá trị, không chỉ số lượng khóa. [Micrometer: Naming Meters và Tags](https://docs.micrometer.io/micrometer/reference/1.13/concepts/naming.html).

Giá trị riêng của một thao tác vẫn được khai báo tại nơi tạo observation, ví dụ `channel=web`. Giá trị chung và giá trị riêng nên có khóa khác nhau. Tránh dùng nhãn chung để tranh quyền quản lý các khóa như `error`, `status` hoặc `method` vốn do cơ chế đo cụ thể cung cấp.

### 2.2. Phạm vi “chung” có giới hạn

Các thuộc tính trên áp dụng qua registry được Spring Boot cấu hình. Nếu tự gọi `ObservationRegistry.create()` rồi dùng registry đó độc lập, ta không tự nhận được chính sách từ `application.properties`. Hãy tiêm `ObservationRegistry` do Spring quản lý vào mã ứng dụng.

Cũng không nên suy ra rằng một meter được tạo trực tiếp bằng `Counter.builder(...)` hoặc `Timer.builder(...)` sẽ nhận nhãn từ `management.observations.key-values`. Meter đó có thể không đi qua observation. Muốn gắn nhãn chung ở tầng metric, xem `management.metrics.tags.<key>` hoặc `MeterRegistryCustomizer`. [Spring Boot 3.3: Metrics](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html).

Ví dụ phân biệt hai ý định:

~~~properties
# Nhãn chung của observation:
management.observations.key-values.region=vn-south

# Nhãn chung ở tầng metric:
management.metrics.tags.environment=lab
~~~

Không cần cấu hình cả hai dòng cho cùng một mục đích một cách máy móc. Trước hết hãy xác định dữ liệu cần xuất hiện ở tầng observation, metric hay cả hai.

## 3. Bật/tắt theo tên và nhánh tên

Chính sách minh họa của bài:

~~~properties
management.observations.enable.all=false
management.observations.enable.checkout=true
management.observations.enable.checkout.audit=false
management.observations.enable.checkout.audit.preview=true
~~~

Ta muốn mặc định tắt, mở nhánh `checkout`, tắt nhánh con `checkout.audit` nhưng mở lại nhánh nhỏ hơn `checkout.audit.preview`.

### 3.1. Cách tra cứu trong Spring Boot 3.3.0

Với tên `checkout.audit.preview`, phần triển khai tra cứu lần lượt:

~~~text
checkout.audit.preview
checkout.audit
checkout
all
giá trị mặc định true nếu không có cấu hình phù hợp
~~~

**Cấu hình cụ thể nhất tìm thấy quyết định kết quả của chính sách thuộc tính.** Thứ tự viết các dòng trong file không thay cho mức độ cụ thể của tên.

Với tên dài hơn `checkout.audit.preview.render`, lần tra cứu đầu là toàn bộ tên đó, rồi lần lượt bỏ đoạn cuối sau dấu chấm. Vì vậy nó có thể kế thừa cấu hình của `checkout.audit.preview`.

Điểm cần lưu ý đã được kiểm chứng trong ví dụ: đây là tra cứu theo các đoạn phân cách bởi dấu chấm. `checkout.auditExtra` không kế thừa `checkout.audit=false`; nó tìm `checkout.auditExtra`, rồi `checkout`. Không coi `enable` là phép so khớp chuỗi con bất kỳ.

| Tên observation | Cấu hình cụ thể nhất khớp | Kết quả |
| --- | --- | --- |
| `checkout.calculate` | `checkout=true` | Bật |
| `checkout.audit.persist` | `checkout.audit=false` | Tắt |
| `checkout.audit.preview` | `checkout.audit.preview=true` | Bật |
| `checkout.auditExtra` | `checkout=true` | Bật |
| `shipping.quote` | `all=false` | Tắt |

Bảng này sẽ được đối chiếu bằng chương trình chạy thật ở phần 5.

### 3.2. Mặc định và các quy tắc hay dùng

Nếu không cấu hình `enable`, chính sách thuộc tính mặc định cho phép observation. Tuy nhiên, “cho phép” không tự tạo điểm đo hoặc tự cài các bộ xử lý còn thiếu.

Tắt một nhánh nhưng giữ các tên khác theo mặc định:

~~~properties
management.observations.enable.checkout.audit=false
~~~

Tắt mặc định, mở những nhánh được chọn:

~~~properties
management.observations.enable.all=false
management.observations.enable.checkout=true
~~~

`all` là khóa dự phòng đặc biệt. `all=true` không thắng một cấu hình cụ thể như `checkout.audit=false`. Muốn bật lại nhánh đó, sửa chính cấu hình của nhánh hoặc thêm một cấu hình con cụ thể hơn.

Không viết `checkout.*` với ý định dùng wildcard. Bản đồ này không phải biểu thức chính quy hoặc cú pháp glob. Hãy dùng `checkout` để điều khiển nhánh, và đặt các tên nghiệp vụ nhất quán ngay từ đầu.

Với các phép đo do thư viện tạo, phải dùng đúng tên observation thực tế của thư viện. Ví dụ, tài liệu Spring Boot dùng `management.observations.enable.spring.security=false` để ngăn observation của Spring Security. [Spring Boot 3.3: Preventing Observations](https://docs.spring.io/spring-boot/3.3/reference/actuator/observability.html#actuator.observability.preventing-observations).

### 3.3. Viết tương đương bằng YAML

Các khóa có dấu chấm có thể được trình bày rõ dưới dạng khóa bản đồ:

~~~yaml
management:
  observations:
    key-values:
      service: "${spring.application.name}"
      region: "vn-south"
      environment: "lab"
    enable:
      all: false
      checkout: true
      "checkout.audit": false
      "checkout.audit.preview": true
~~~

Đây là cấu hình tương đương để lựa chọn thay cho phần `management.observations` trong file properties, không phải một bộ chính sách thứ hai cần áp dụng thêm. Dùng boolean `true`/`false` cho `enable`, và giữ các giá trị nhãn dưới dạng chuỗi.

## 4. Chính sách tác động ở đâu trong vòng đời?

Có thể hình dung luồng xử lý như sau:

~~~text
Mã ứng dụng hoặc thư viện bắt đầu một thao tác
        |
        v
Tạo observation với tên và ngữ cảnh
        |
        v
Các ObservationPredicate quyết định có quan sát hay không
        |
        +-- từ chối --> observation NOOP --> mã nghiệp vụ vẫn chạy
        |
        +-- chấp nhận --> start --> chạy mã nghiệp vụ --> stop
                                                   |
                                                   v
                                         ObservationFilter cập nhật ngữ cảnh
                                                   |
                                                   v
                                         handler xử lý onStop
~~~

`NOOP` là đối tượng không thực hiện việc quan sát. Nó không phải lệnh hủy nghiệp vụ. Với `observation.observe(action)`, `action` vẫn chạy ngay cả khi observation bị từ chối.

Trong Micrometer, `ObservationPredicate` quyết định có dùng observation thực hay phiên bản NOOP; `ObservationFilter` có thể cập nhật ngữ cảnh trước các lời gọi `onStop`. Vì vậy không dựa vào nhãn chung được thêm bằng filter để mặc định rằng nhãn đó đã tồn tại lúc chạy predicate hoặc `onStart`. [Micrometer: Observation Components](https://docs.micrometer.io/micrometer/reference/1.13/observation/components.html).

Nếu yêu cầu lọc phụ thuộc loại ngữ cảnh hoặc điều kiện phức tạp hơn tên, có thể đăng ký bean `ObservationPredicate`. Một quyết định `true` từ thuộc tính không ép các predicate khác phải chấp nhận. Khi cần điều kiện theo môi trường, hãy lấy cấu hình môi trường trực tiếp thay vì trông chờ nhãn được gắn ở cuối vòng đời.

Tắt observation cũng không đồng nghĩa rằng mọi chi phí trước điểm đo đều biến mất. Mã đã chạy trước khi gọi API quan sát, mã nghiệp vụ và các điểm đo độc lập vẫn thực hiện theo luồng của chúng.

## 5. Thực hành: kiểm chứng nhãn chung và chính sách nhóm

Ví dụ này là một ứng dụng dòng lệnh, không mở HTTP server và không cần Prometheus, Zipkin hoặc hệ thống giám sát bên ngoài. Ta đọc timer ngay trong `MeterRegistry` để tách việc **có phép đo hay không** khỏi việc **xuất phép đo đi đâu**.

### 5.1. Cấu trúc và dependency

Tạo một thư mục thực hành độc lập:

~~~text
observation-policy-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── example/
        │       └── ObservationPolicyDemo.java
        └── resources/
            └── application.properties
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
    <artifactId>observation-policy-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Không khai báo riêng phiên bản Micrometer trong ví dụ này; dùng các phiên bản do Spring Boot quản lý để giữ bộ dependency nhất quán.

### 5.2. Cấu hình hoàn chỉnh

Nội dung `src/main/resources/application.properties`:

~~~properties
spring.application.name=checkout-demo
spring.main.web-application-type=none
spring.main.banner-mode=off
logging.level.root=OFF

management.observations.key-values.service=${spring.application.name}
management.observations.key-values.region=vn-south
management.observations.key-values.environment=lab

management.observations.enable.all=false
management.observations.enable.checkout=true
management.observations.enable.checkout.audit=false
management.observations.enable.checkout.audit.preview=true
~~~

Tắt banner và log nền để phần stdout nghiệp vụ dễ đối chiếu. Chính sách quan sát nằm ở các dòng `management.observations`; các dòng log không quyết định observation có được tạo hay không.

### 5.3. Chương trình Java đầy đủ

Nội dung `src/main/java/example/ObservationPolicyDemo.java`:

~~~java
package example;

import java.util.List;
import java.util.TreeMap;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;

@SpringBootApplication
public class ObservationPolicyDemo {
    public static void main(String[] args) {
        try (ConfigurableApplicationContext context =
                SpringApplication.run(ObservationPolicyDemo.class, args)) {
            ObservationRegistry observations = context.getBean(ObservationRegistry.class);
            MeterRegistry meters = context.getBean(MeterRegistry.class);
            List<String> names = List.of(
                    "checkout.calculate",
                    "checkout.audit.persist",
                    "checkout.audit.preview",
                    "checkout.auditExtra",
                    "shipping.quote");
            for (String name : names) {
                Observation observation = Observation.createNotStarted(name, observations)
                        .lowCardinalityKeyValue("channel", "web");
                System.out.println("BEGIN " + name + " noop=" + observation.isNoop());
                observation.observe(() -> System.out.println("WORK " + name));
                Timer timer = meters.find(name).timer();
                System.out.println("METER " + name + " count="
                        + (timer == null ? 0 : timer.count()));
                if (timer != null) {
                    TreeMap<String, String> tags = new TreeMap<>();
                    timer.getId().getTags().forEach(tag ->
                            tags.put(tag.getKey(), tag.getValue()));
                    System.out.println("TAGS " + name + " " + tags);
                }
            }
        }
    }
}
~~~

Các điểm cần đọc trong mã:

1. Lấy cả hai registry từ application context để sử dụng cấu hình Spring Boot.
2. `channel=web` là nhãn riêng của các thao tác trong ví dụ; ba nhãn môi trường lấy từ cấu hình chung.
3. `observe(...)` quản lý vòng đời của thao tác đồng bộ. Khi hàm bên trong hoàn tất, có thể đọc timer sau khi observation dừng.
4. `isNoop()` giúp phân biệt quyết định ở tầng observation với việc chỉ thiếu meter.
5. Dùng `TreeMap` để in nhãn theo thứ tự khóa ổn định, không suy đoán thứ tự do registry trả về.
6. `try-with-resources` đóng application context khi kết thúc.

Biểu thức `timer == null ? 0 : timer.count()` chỉ quy ước cách in của ví dụ. Dòng `count=0` ở một thao tác bị chặn không chứng minh có một timer thật với số đếm bằng 0; nhánh đó có thể không tìm thấy timer.

### 5.4. Biên dịch và chạy

Tại thư mục chứa `pom.xml`, với JDK 17 trở lên và Maven:

~~~shell
mvn -q -DskipTests package
java -jar target/observation-policy-demo-1.0.0.jar
~~~

Maven biên dịch mã và Spring Boot Maven Plugin đóng gói JAR thực thi. Lần đầu cần truy cập các kho dependency nếu máy chưa có sẵn.

Nếu muốn nhìn rõ bước `javac`, có thể dùng cách chạy trực tiếp sau **thay cho** cách đóng gói trên. Ví dụ lệnh cho PowerShell/Windows:

~~~powershell
mvn -q dependency:copy-dependencies -DoutputDirectory=lib
New-Item -ItemType Directory -Path out -Force | Out-Null
javac --release 17 -encoding UTF-8 -cp "lib/*" -d out src/main/java/example/ObservationPolicyDemo.java
java -cp "out;src/main/resources;lib/*" example.ObservationPolicyDemo
~~~

Trên Linux/macOS, tạo thư mục `out` bằng `mkdir -p out` và thay dấu phân cách classpath `;` bằng `:` ở lệnh `java`. Không chạy riêng file Java khi chưa cung cấp thư viện Spring Boot/Micrometer.

### 5.5. Stdout của cấu hình gốc

Các dòng do chương trình in:

~~~text
BEGIN checkout.calculate noop=false
WORK checkout.calculate
METER checkout.calculate count=1
TAGS checkout.calculate {channel=web, environment=lab, error=none, region=vn-south, service=checkout-demo}
BEGIN checkout.audit.persist noop=true
WORK checkout.audit.persist
METER checkout.audit.persist count=0
BEGIN checkout.audit.preview noop=false
WORK checkout.audit.preview
METER checkout.audit.preview count=1
TAGS checkout.audit.preview {channel=web, environment=lab, error=none, region=vn-south, service=checkout-demo}
BEGIN checkout.auditExtra noop=false
WORK checkout.auditExtra
METER checkout.auditExtra count=1
TAGS checkout.auditExtra {channel=web, environment=lab, error=none, region=vn-south, service=checkout-demo}
BEGIN shipping.quote noop=true
WORK shipping.quote
METER shipping.quote count=0
~~~

Đối chiếu kết quả:

- `checkout.calculate` có timer và đủ ba nhãn chung cùng nhãn riêng `channel`.
- `checkout.audit.persist` bị từ chối quan sát nhưng vẫn có dòng `WORK`.
- `checkout.audit.preview` được mở lại bởi cấu hình cụ thể hơn.
- `checkout.auditExtra` được cho phép theo `checkout=true`, xác nhận ranh giới theo đoạn tên.
- `shipping.quote` không có quy tắc riêng nên nhận `all=false`.
- `error=none` do cơ chế ghi metric cung cấp trong lần chạy thành công; nó không phải nhãn chung ta khai báo.

Chương trình không cài tracing bridge hoặc exporter trace. Các dòng `TAGS` xác minh nhãn của timer, không phải bằng chứng rằng trace đã được gửi tới một hệ thống ngoài.

## 6. Hai phép thử để tránh hiểu sai công tắc

### 6.1. Bật lại cả nhóm audit

Chạy một tiến trình mới:

~~~shell
java -jar target/observation-policy-demo-1.0.0.jar --management.observations.enable.checkout.audit=true
~~~

Các dòng tương ứng với `checkout.audit.persist` trở thành:

~~~text
BEGIN checkout.audit.persist noop=false
WORK checkout.audit.persist
METER checkout.audit.persist count=1
TAGS checkout.audit.persist {channel=web, environment=lab, error=none, region=vn-south, service=checkout-demo}
~~~

`checkout.audit.preview` vẫn bật. `shipping.quote` vẫn tắt do `all=false`.

Đây là hai tầng ưu tiên riêng: tham số dòng lệnh thay giá trị `checkout.audit` lấy từ file; sau đó chính sách theo tên vẫn tìm khóa cụ thể nhất. Một tham số đặt `all=true` không tự xóa các khóa cụ thể khác trong bản đồ. Cơ chế nguồn cấu hình và cơ chế chọn nhánh phải được xét riêng. [Spring Boot 3.3: Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html).

### 6.2. Chỉ tắt metric, giữ observation

Chạy lại cấu hình gốc trong một tiến trình mới, chỉ thêm công tắc metric:

~~~shell
java -jar target/observation-policy-demo-1.0.0.jar --management.metrics.enable.checkout.calculate=false
~~~

Phần stdout tương ứng:

~~~text
BEGIN checkout.calculate noop=false
WORK checkout.calculate
METER checkout.calculate count=0
~~~

`noop=false` cho biết observation vẫn được tạo. Cơ chế lọc meter ngăn timer được đăng ký nên không có dòng `TAGS` của timer đó. Đây là lý do không dùng riêng việc “không thấy metric” để kết luận observation đã bị tắt. [Micrometer: Meter Filters](https://docs.micrometer.io/micrometer/reference/1.13/concepts/meter-filters.html).

Các phép thử đều dùng tiến trình mới để tránh việc meter cũ còn nằm trong registry làm kết quả khó đọc.

## 7. Phân biệt observation, metric, trace và endpoint

| Nhu cầu | Cơ chế phù hợp | Phạm vi cần hiểu |
| --- | --- | --- |
| Chặn việc quan sát một nhóm thao tác | `management.observations.enable.<name>=false` | Chặn observation và các kết quả do các handler của observation đó tạo ra |
| Chặn một nhóm metric | `management.metrics.enable.<name>=false` | Lọc ở tầng meter; observation có thể vẫn tồn tại |
| Gắn nhãn chung cho observation | `management.observations.key-values.<key>` | Đi qua registry và xử lý observation |
| Gắn nhãn chung cho metric | `management.metrics.tags.<key>` | Đi qua cấu hình metric |
| Cho HTTP client truy cập endpoint Actuator | `management.endpoints.web.exposure.include` | Điều khiển công bố endpoint, không thay chính sách observation |
| Điều chỉnh tỷ lệ lấy mẫu trace | `management.tracing.sampling.probability` | Điều khiển lấy mẫu trace, không thay thế chính sách observation theo tên |

Observation là điểm nối có thể sinh metric và span khi có handler phù hợp. Nếu chặn ngay observation đó, các handler không xử lý vòng đời của nó. Tuy nhiên, meter được ghi trực tiếp, span được tạo độc lập hoặc dữ liệu do agent khác thu thập có thể vẫn tồn tại.

Ngược lại, chỉ lọc metric không tự tắt tracing. Khi bổ sung Micrometer Tracing vào ứng dụng, cần cấu hình tracer/bridge và nơi xuất trace phù hợp; starter Actuator trong ví dụ không chứng minh đã có toàn bộ đường truyền trace. [Spring Boot 3.3: Tracing](https://docs.spring.io/spring-boot/3.3/reference/actuator/tracing.html).

Tỷ lệ lấy mẫu trace bằng 0 không đồng nghĩa mã nghiệp vụ ngừng chạy hoặc mọi metric đều biến mất. Không dùng công tắc tracing để thay thế quyết định bật/tắt observation theo nhóm.

## 8. Lỗi thường gặp và cách chẩn đoán

| Hiện tượng hoặc cách cấu hình | Nguyên nhân có thể gặp | Cách kiểm tra/sửa |
| --- | --- | --- |
| `management.observation...` không có hiệu lực | Sai tên nhánh; thiếu chữ `s` | Dùng đúng `management.observations` |
| `enable.checkout.*=false` không chặn nhóm như mong muốn | Hiểu nhầm có wildcard | Dùng khóa `checkout` và tên phân đoạn nhất quán |
| `all=false` nhưng vẫn có observation | Có nhánh cụ thể được bật | Liệt kê chuỗi tra cứu của đúng tên |
| Tắt `checkout.audit` nhưng `checkout.auditExtra` vẫn bật | Hai tên không cùng nhánh phân đoạn | Đối chiếu bảng và stdout của ví dụ |
| `enable...=true` nhưng không có dữ liệu | Thiếu điểm đo/handler, dùng sai registry hoặc bị predicate khác từ chối | Kiểm tra nơi tạo observation và registry được tiêm |
| Không thấy nhãn chung khi kiểm tra đầu thao tác | Kiểm tra trước giai đoạn filter thêm nhãn | Kiểm tra ngữ cảnh tại `onStop` hoặc timer sau khi dừng |
| Không thấy metric và kết luận observation bị tắt | Có thể chỉ bị lọc meter hoặc chưa xuất dữ liệu | Tách kiểm tra observation, registry và exporter |
| Tắt observation nhưng nghiệp vụ vẫn chạy | Đó là hành vi bình thường của NOOP | Dùng cơ chế nghiệp vụ riêng nếu muốn dừng chức năng |
| Sửa file cấu hình trong lúc JVM đang chạy và chờ thay đổi ngay | Không có cơ chế tự nạp lại được thiết lập | Khởi động lại để kiểm chứng cấu hình mới |

Một trình tự chẩn đoán hữu ích là: xác định **tên observation thực tế**, đối chiếu **giá trị cấu hình có hiệu lực**, kiểm tra **quyết định NOOP**, rồi kiểm tra **meter/span và nơi xuất dữ liệu**. Làm theo chuỗi này giúp biết lỗi nằm ở chính sách, điểm đo hay đường xuất dữ liệu.

Không đổi tên observation thành mã đơn hàng hay URI chứa định danh chỉ để dễ tìm một giao dịch. Giữ tên biểu diễn loại thao tác, ví dụ `checkout.calculate`; đưa dữ liệu cụ thể vào ngữ cảnh thích hợp với kiểm soát cardinality và quyền riêng tư.

Không dùng chính sách observation như cơ chế bảo mật hoặc bật/tắt chức năng. Quyết định cho phép thanh toán, ghi nhận kiểm toán nghiệp vụ hay truy cập API phải do logic và chính sách tương ứng kiểm soát.

## 9. Bài tập tự kiểm chứng

Thực hiện từng thay đổi độc lập trên cấu hình gốc và khởi động lại:

1. Đổi `region` thành `vn-north`. Các timer được tạo phải có nhãn khu vực mới; danh sách thao tác được phép quan sát không đổi.
2. Đổi `checkout.audit.preview` thành `false`. Cả `checkout.audit.persist` và `checkout.audit.preview` phải có `noop=true` nhưng vẫn in `WORK`.
3. Giữ `checkout.audit=false`, thêm `checkout.audit.persist=true`. Chỉ thao tác `persist` được mở lại trong nhánh audit theo thay đổi này.
4. Đổi `all=true`, giữ các khóa cụ thể khác như cấu hình gốc. `shipping.quote` được bật, còn `checkout.audit.persist` vẫn bị tắt.
5. Tắt metric `checkout.calculate` như phần 6.2. Giải thích được vì sao `noop=false` đi cùng `count=0`.
6. Bỏ dòng `management.observations.key-values.service`. Quan sát tên ứng dụng vẫn là `checkout-demo` nhưng timer không còn nhận nhãn `service` từ cấu hình chung này.

Sau các thử nghiệm, người học cần giải thích được ba mối liên hệ: tên quyết định nhánh chính sách; key-value mô tả dữ liệu quan sát; handler và registry quyết định dữ liệu được ghi thành metric/trace như thế nào.
