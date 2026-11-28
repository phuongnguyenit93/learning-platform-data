# Kiểm tra thay đổi artifact Insight starter

## Mục tiêu và phạm vi

**Spring Modulith Insight starter** là điểm tích hợp thuận tiện để quan sát cấu trúc và hoạt động của các application module trong ứng dụng Spring Boot. Starter kết hợp hỗ trợ **Actuator** để công bố cấu trúc module với **observability** để ghi nhận tương tác giữa các module thông qua Micrometer. Khi nâng phiên bản Spring Modulith, tên starter có thể vẫn giữ nguyên nhưng **những artifact mà starter kéo theo, scope và API có sẵn lúc biên dịch** có thể thay đổi.

Bài này thuộc chương **Phiên bản** của module **SPRING_MODULITH_DOCUMENTATION_OBSERVABILITY**: sử dụng Spring Modulith để sinh tài liệu ranh giới application module, xem module graph qua Actuator, kiểm tra event metrics, tracing và context propagation khi hệ thống vận hành.

Sau bài học, bạn có thể:

1. Xác định đúng Maven coordinates của Insight starter theo phiên bản, phân biệt tên starter với artifact phụ thuộc bắc cầu.
2. So sánh cấu trúc dependency của Insight starter giữa nhánh Spring Modulith **1.4.x** và **2.x**, đặc biệt phần observability.
3. Khóa và đồng bộ phiên bản bằng Spring Modulith BOM trên Maven hoặc Gradle.
4. Kiểm tra dependency tree ở **compile classpath** và **runtime classpath**, phát hiện bản cũ, bản trùng và conflict.
5. Xác minh trên ứng dụng chạy thực tế rằng module Actuator, event metrics và module spans còn hoạt động sau nâng cấp.
6. Soạn checklist migration và rollback để tránh ngộ nhận rằng build xanh nghĩa là observability tương thích.

> **Mốc tài liệu:** các ví dụ so sánh Spring Modulith **1.4.x** và **2.2.0**. Theo thông báo phát hành ngày **19/11/2026**, Spring Modulith 2.2.0 là bản GA và được build cùng Spring Boot 4.2/Spring Framework 7.1. Nếu dự án đang ở nhánh khác, hãy xem lại BOM, compatibility matrix và POM của đúng phiên bản đó. Các cấu hình triển khai chỉ là ví dụ minh họa, chưa có thông tin về phiên bản đang dùng trong dự án của người học.

## 1. Insight starter giải quyết việc gì?

Một ứng dụng bán hàng có các application module **orders**, **payments** và **shipping**. Công cụ phân tích tĩnh có thể sinh tài liệu module graph để mô tả quan hệ giữa các package, API công khai và listener. Khi ứng dụng chạy, đội vận hành còn muốn biết:

- Những module nào đang được Spring Modulith nhận diện?
- Orders có gọi API module payments trong một giao dịch thực tế không?
- Các application event xuất hiện với tần suất nào?
- Đường xử lý đồng bộ hay bất đồng bộ có xuất hiện trong distributed trace không?
- Sau khi cập nhật Spring Modulith, ranh giới module hiển thị ở Actuator và các số liệu runtime có còn như trước?

**Insight starter** tập hợp phần cần thiết để đưa thông tin đó vào môi trường vận hành. Tuy nhiên, nó không tự cung cấp toàn bộ hệ thống observability: để xem trace trong Zipkin, Grafana hoặc backend OTLP, ứng dụng vẫn cần tracing bridge, exporter/collector tương ứng và cấu hình phù hợp.

Các thành phần có vai trò khác nhau:

| Thành phần | Trách nhiệm |
|---|---|
| **spring-modulith-starter-insight** | Starter tổng hợp các dependency để dùng Actuator và observability |
| **spring-modulith-actuator** | Đăng ký endpoint Modulith cung cấp mô hình module tại runtime |
| **spring-modulith-observability** trong nhánh 1.4 | Hạ tầng quan sát tương tác module ở cấu trúc artifact cũ |
| **spring-modulith-observability-api** trong nhánh 2.x | Các API mở rộng/tuỳ biến observability được tách ra riêng |
| **spring-modulith-observability-core** trong nhánh 2.x | Triển khai instrumentation và các thành phần observability runtime |
| **spring-boot-starter-actuator** | Hạ tầng Actuator và Micrometer chung của Spring Boot |
| **Micrometer Tracing bridge + exporter** | Chuyển observation/span thành dữ liệu tracing gửi tới backend |

**Không nhầm:** dependency **spring-modulith-docs** phục vụ sinh tài liệu kiến trúc bằng Documenter, thường ở test scope. Insight starter hướng tới Actuator và observability runtime; nó không thay thế hoàn toàn dependency tạo tài liệu hoặc các bài test kiểm chứng module boundary.

## 2. Thay đổi quan trọng: tên starter giữ nguyên, artifact observability đổi

Theo danh sách starter POM trong tài liệu chính thức:

| Tiêu chí | Spring Modulith 1.4.x | Spring Modulith 2.2.0 |
|---|---|---|
| Maven group | `org.springframework.modulith` | `org.springframework.modulith` |
| Starter artifact | `spring-modulith-starter-insight` | **Vẫn là** `spring-modulith-starter-insight` |
| Scope thường dùng của starter | `runtime` | `runtime` |
| Module Actuator | `spring-modulith-actuator` | `spring-modulith-actuator` |
| Observability implementation | `spring-modulith-observability` | **`spring-modulith-observability-core`** |
| API quan sát tách riêng | Chưa là artifact độc lập tương ứng | **`spring-modulith-observability-api`** |
| Spring Boot Actuator | `spring-boot-starter-actuator` | `spring-boot-starter-actuator` |

Nguồn đối chiếu là bảng **Spring Modulith modules / starter POMs** trong tài liệu [1.4](https://docs.spring.io/spring-modulith/reference/1.4/appendix.html) và [2.2](https://docs.spring.io/spring-modulith/reference/2.2/appendix.html). Các tên dependency ở bảng là những tên được công bố trong tài liệu; muốn khẳng định chính xác **phiên bản đã resolve**, phải xem POM hoặc dependency tree của build thực tế.

Sơ đồ thay đổi:

~~~mermaid
flowchart TB
    subgraph OLD["Spring Modulith 1.4.x"]
        S1["spring-modulith-starter-insight"]
        S1 --> A1["spring-modulith-actuator"]
        S1 --> O1["spring-modulith-observability"]
        S1 --> B1["spring-boot-starter-actuator"]
    end
    subgraph NEW["Spring Modulith 2.2.x"]
        S2["spring-modulith-starter-insight"]
        S2 --> A2["spring-modulith-actuator"]
        S2 --> OAPI["spring-modulith-observability-api"]
        S2 --> OCORE["spring-modulith-observability-core"]
        S2 --> B2["spring-boot-starter-actuator"]
    end
~~~

Điều cần học ở đây là sự khác nhau giữa **địa chỉ phụ thuộc khai báo trực tiếp** và **đồ thị phụ thuộc bắc cầu**:

- Nếu ứng dụng chỉ khai báo `spring-modulith-starter-insight`, tên dependency trực tiếp có thể vẫn dùng được trong phiên bản mới; cấu trúc transitive dependency đã thay đổi.
- Nếu ứng dụng có khai báo riêng artifact cũ `spring-modulith-observability`, cần kiểm tra và chuyển sang artifact mới tương ứng khi đi từ 1.4 sang 2.x.
- Nếu mã nguồn tự sử dụng các API tuỳ biến observability, hãy kiểm tra package, Java API, signature và **compile classpath**; artifact chỉ có ở runtime không nhất thiết sẵn sàng cho import lúc compile.

**Không được kết luận starter đã bị xóa hoặc đổi tên** chỉ vì không còn thấy `spring-modulith-observability` trong dependency tree của bản mới.

## 3. Tại sao thay đổi artifact ảnh hưởng đến dự án?

Hãy xét ba ứng dụng đều có Insight starter, nhưng dùng theo cách khác nhau.

### Trường hợp A: chỉ dùng Actuator và module spans

Ứng dụng chỉ khai báo starter, không import các class observability trong Java. Khi nâng cấp, công việc chủ yếu là cập nhật **BOM**, đảm bảo các artifact tương ứng được resolve và kiểm chứng chức năng runtime. Thay đổi transitive artifact có thể hoàn toàn không yêu cầu sửa mã nghiệp vụ.

### Trường hợp B: import API tuỳ biến metrics/observations

Ứng dụng tạo bean tuỳ biến convention hoặc event metrics bằng API do Spring Modulith cung cấp. Nếu starter được khai báo `runtimeOnly`, compile classpath **không tự nhận** các class này. Ở nhánh 2.x, khai báo `spring-modulith-observability-api` ở compile scope là lựa chọn rõ ràng khi mã nguồn cần import API tương ứng.

Ví dụ Gradle về nguyên tắc:

~~~groovy
dependencies {
    runtimeOnly 'org.springframework.modulith:spring-modulith-starter-insight'

    // Chỉ bổ sung nếu code ứng dụng dùng API observability.
    implementation 'org.springframework.modulith:spring-modulith-observability-api'
}
~~~

Việc cần khai báo artifact nào ở compile scope phải dựa vào class thực tế được import và API của phiên bản đang dùng. Nếu một ví dụ trong tài liệu cũ nhập class không còn tồn tại hoặc chuyển package, chỉ thêm dependency không nhất thiết khắc phục; phải chỉnh code theo API mới.

### Trường hợp C: thêm riêng observability, không dùng Insight starter

Một ứng dụng muốn chỉ có module spans, không cần `/actuator/modulith`, có thể khai báo **`spring-modulith-observability-core`** trực tiếp trong nhánh 2.x. Trong nhánh 1.4.x tên tương ứng là **`spring-modulith-observability`**. Nếu dùng starter tổng hợp rồi thêm lại tất cả artifact runtime tương đương một cách vô điều kiện, sẽ làm cấu hình khó hiểu và tăng khả năng version conflict.

## 4. Đồng bộ phiên bản với Spring Modulith BOM

**BOM (Bill of Materials)** quản lý phiên bản của một tập artifact liên quan. Nó giúp tránh trường hợp starter được resolve ở phiên bản mới nhưng observability/actuator khác nhánh vì dependency trực tiếp, plugin hoặc transitive override.

Ví dụ dùng **Spring Modulith 2.2.0** như một mốc minh họa. Trước khi áp dụng, xác nhận Spring Boot version hiện tại tương thích với nhánh Modulith đích và các thư viện đi kèm, đặc biệt khi nâng từ Boot 3 sang Boot 4.

### 4.1. Maven

Thêm BOM vào `dependencyManagement`:

~~~xml
<dependencyManagement>
  <dependencies>
    <dependency>
      <groupId>org.springframework.modulith</groupId>
      <artifactId>spring-modulith-bom</artifactId>
      <version>2.2.0</version>
      <type>pom</type>
      <scope>import</scope>
    </dependency>
  </dependencies>
</dependencyManagement>
~~~

Thêm starter mà không cần ghi lại phiên bản ở từng dependency:

~~~xml
<dependencies>
  <dependency>
    <groupId>org.springframework.modulith</groupId>
    <artifactId>spring-modulith-starter-insight</artifactId>
    <scope>runtime</scope>
  </dependency>
</dependencies>
~~~

Nếu code thực sự import observability customization API trong nhánh 2.x, khai báo thêm:

~~~xml
<dependency>
  <groupId>org.springframework.modulith</groupId>
  <artifactId>spring-modulith-observability-api</artifactId>
</dependency>
~~~

Maven scope mặc định là compile. Không thay `spring-modulith-observability-api` bằng `spring-modulith-observability-core` ở compile một cách tùy tiện; vai trò của hai artifact khác nhau.

### 4.2. Gradle

Ví dụ **Gradle Groovy DSL** dùng BOM như một `platform`:

~~~groovy
dependencies {
    implementation platform('org.springframework.modulith:spring-modulith-bom:2.2.0')
    runtimeOnly 'org.springframework.modulith:spring-modulith-starter-insight'

    // Dùng khi mã nguồn gọi trực tiếp API tuỳ biến:
    implementation 'org.springframework.modulith:spring-modulith-observability-api'
}
~~~

Các dự án sử dụng plugin `io.spring.dependency-management` cũng có thể import BOM qua khối `dependencyManagement`. Chọn **một chiến lược dependency management được dự án dùng nhất quán**, đồng thời xem effective dependencies vì Spring Boot plugin, các platform và ràng buộc phiên bản khác có thể tác động đến việc resolve.

**Đừng trộn kiểu cố định:**

~~~groovy
// Ví dụ dễ gây lệch nhánh, cần tránh khi nâng cấp:
runtimeOnly 'org.springframework.modulith:spring-modulith-starter-insight:2.2.0'
runtimeOnly 'org.springframework.modulith:spring-modulith-observability:1.4.14'
~~~

Khi một artifact cũ vẫn ở runtime classpath, build có thể báo lỗi resolve hoặc xuất hiện hành vi không tương thích. Cần xác định nguyên nhân từ dependency tree và loại bỏ khai báo cũ sau khi cập nhật theo BOM; không dùng exclusion bừa bãi để che conflict.

### 4.3. Kiểm tra tương thích Spring Boot

Spring Modulith 1.4.x được tài liệu hóa trong hệ Spring Boot 3.x; đợt phát hành 2.2.0 công bố nâng nền build sang Spring Boot 4.2/Spring Framework 7.1. Điều này liên quan đến nhiều thay đổi khác ngoài starter, ví dụ Java baseline, Micrometer, Spring Framework và dependency Jakarta/Jackson trong ứng dụng.

Vì vậy:

1. Xác định Spring Boot version đang dùng và nhánh Modulith đang dùng.
2. Xác định đích nâng cấp hỗ trợ Boot version tương ứng theo **compatibility matrix chính thức**.
3. Đổi BOM và dependency cùng nhau, kiểm tra classpath.
4. Chạy kiểm thử kiến trúc, Actuator và tracing trước khi coi việc nâng cấp hoàn thành.

Một câu lệnh `mvn package` thành công chỉ chứng minh các phần đã được biên dịch/đóng gói theo cấu hình build đó; nó không chứng minh các auto-configuration quan sát được kích hoạt hoặc các span thực sự đi tới tracing backend.

## 5. Xem chính xác artifact nào đang được resolve

Trước khi thay dependency, lưu kết quả dependency tree làm **baseline**. Chạy lại các lệnh sau khi đổi BOM và so sánh. Các lệnh dưới đây dành cho người học chạy tại root của dự án dùng Maven hoặc Gradle, không phải kết quả đã chạy trong bài.

### 5.1. Maven dependency tree

~~~bash
mvn dependency:tree -Dincludes=org.springframework.modulith
~~~

Để lưu toàn bộ dữ liệu kiểm tra:

~~~bash
mvn dependency:tree -DoutputFile=target/modulith-dependency-tree.txt
~~~

Lệnh thứ hai ghi báo cáo của ứng dụng vào thư mục `target` khi được thực thi. Nếu chỉ thấy một phần dependency mong đợi, bỏ filter để nhìn cả Spring Boot Actuator, Micrometer và exporter tương ứng.

Khi có class được import không tìm thấy, ngoài dependency tree còn có thể dùng:

~~~bash
mvn help:effective-pom
~~~

Để kiểm tra BOM và phiên bản thực sự được áp dụng bởi parent hoặc `dependencyManagement`, thay vì chỉ đọc POM con.

### 5.2. Gradle: runtimeClasspath và compileClasspath

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencies --configuration compileClasspath
~~~

Tra cứu một artifact cụ thể:

~~~bash
./gradlew dependencyInsight \
  --configuration runtimeClasspath \
  --dependency spring-modulith-starter-insight

./gradlew dependencyInsight \
  --configuration runtimeClasspath \
  --dependency spring-modulith-observability-core
~~~

Trên Windows PowerShell, có thể viết lệnh trên một dòng và dùng `.\gradlew.bat` thay cho `./gradlew`.

**Tại sao xem cả hai classpath?** Vì `runtimeOnly` starter thường xuất hiện ở runtime classpath, không nhất thiết ở compile classpath. Nếu source code trực tiếp dùng một API trong observability, cần thấy API đó trong compile classpath qua dependency có scope phù hợp.

### 5.3. Kỳ vọng ở hai nhánh

Một bản dependency tree **rút gọn theo ý nghĩa**, không phải output nguyên văn, nên có dạng:

~~~text
Spring Modulith 1.4.x
  spring-modulith-starter-insight
    spring-modulith-actuator
    spring-modulith-observability
    spring-boot-starter-actuator

Spring Modulith 2.2.0
  spring-modulith-starter-insight
    spring-modulith-actuator
    spring-modulith-observability-api
    spring-modulith-observability-core
    spring-boot-starter-actuator
~~~

Sơ đồ trên chỉ minh họa thành phần; số phiên bản, nhánh transitives và cách Maven/Gradle hiển thị cây có thể khác. Khi đọc output thực, kiểm tra các mục:

| Câu hỏi | Bằng chứng |
|---|---|
| Starter nào đang được dùng? | Group, artifact, resolved version của `spring-modulith-starter-insight` |
| BOM đã được áp dụng? | Effective POM hoặc Gradle dependency constraints |
| Actuator có mặt? | `spring-modulith-actuator` và `spring-boot-starter-actuator` trong runtime |
| Observability dùng artifact cũ hay mới? | `spring-modulith-observability` so với `-observability-api`/`-core` |
| Có trộn 1.4.x và 2.x? | Các version thực tế của toàn bộ `org.springframework.modulith` |
| Source dùng customization API có compile? | API xuất hiện trong compileClasspath, import biên dịch được |
| Tracer/exporter có đủ? | Micrometer tracing bridge, backend exporter và cấu hình |
| Version bị ép bởi ai? | Phần “selection reason” của Gradle dependencyInsight, Maven effective POM/tree |

**Một dấu hiệu cần điều tra:** starter là 2.2.0 nhưng `spring-modulith-observability:1.4.x` vẫn tồn tại. Dù classpath có thể không xung đột tức thì, đây là cấu trúc chưa được thiết kế theo BOM đích; phải xác định dependency nào còn kéo artifact cũ trước khi triển khai.

## 6. Kiểm chứng chức năng runtime sau khi sửa artifact

Dependency tree là bước cần thiết nhưng chưa đủ. Insight starter liên quan trực tiếp đến **những gì ứng dụng expose và quan sát được lúc chạy**, vì vậy phải có kiểm thử chức năng tối thiểu.

### 6.1. Kiểm tra Actuator Modulith

Khi đã có support và HTTP exposure được cấp phép phù hợp, có thể thử:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,modulith
~~~

Trên môi trường kiểm thử có quyền truy cập:

~~~bash
curl -i http://localhost:8080/actuator
curl -i http://localhost:8080/actuator/modulith
~~~

Endpoint `/actuator/modulith` phản ánh mô hình application module mà ứng dụng nhận diện ở runtime, trong đó có display name, base package và các dependency. Ví dụ rút gọn:

~~~json
{
  "orders": {
    "displayName": "Orders",
    "basePackage": "com.example.shop.orders",
    "dependencies": []
  },
  "billing": {
    "displayName": "Billing",
    "basePackage": "com.example.shop.billing",
    "dependencies": [
      { "target": "orders", "types": ["EVENT_LISTENER"] }
    ]
  }
}
~~~

Đây là **JSON minh họa**, không phải dữ liệu lấy từ một ứng dụng đã chạy. Nếu một module thiếu hoặc dependency không khớp baseline, kiểm tra lại cách nhận diện application module, package structure và các customization được đặt trong source runtime.

Nếu endpoint trả **404**, hãy xem việc đăng ký Actuator, dependency/auto-configuration, exposure và management base path. Nếu trả **401/403**, có thể đang bị Spring Security chặn; đây chưa phải bằng chứng thiếu starter. Trong production, không expose endpoint thông tin kiến trúc chỉ để thử nhanh mà chưa có chính sách bảo vệ.

### 6.2. Kiểm tra event metrics

Spring Modulith observability hỗ trợ các metric về application event publications, ví dụ:

- **module.events.published**: tổng số lần event được phát.
- **module.events.published.<moduleIdentifier>.<simpleEventTypeName>**: metric theo loại event/module tùy cách naming registry.
  
Thực hiện một hành động nghiệp vụ (ví dụ hoàn tất đơn hàng) để phát event và xem:

~~~bash
curl -i http://localhost:8080/actuator/metrics/module.events.published
~~~

Nếu metric chưa xuất hiện, hãy chắc chắn event đã thực sự được phát, Micrometer/Actuator có mặt, registry đã được cấu hình và tên metric được tra đúng theo phiên bản. Các metric này cho biết **event được publish trong ứng dụng**, không tự chứng minh một event externalized đã tới Kafka hoặc consumer đã hoàn thành.

Khi tùy biến event metrics qua API phiên bản mới, kiểm tra import và method signatures của `ModulithEventMetricsCustomizer` theo API version tương ứng. Tag có cardinality thấp như module/type phù hợp với metric; tránh dùng `orderId`, `eventId` hoặc `traceId` làm tag do số lượng time series rất lớn.

### 6.3. Kiểm tra trace/span của module

Với observability infrastructure hoạt động, Spring Modulith có thể ghi nhận **module entry spans** khi đi vào thành phần public API của application module. Một span có thể mang các thuộc tính:

| Thuộc tính | Ý nghĩa |
|---|---|
| `module.identifier` | Định danh kỹ thuật của module |
| `module.name` | Tên module |
| `module.method` | Phương thức được quan sát |
| `module.invocation-type` | Kiểu gọi, chẳng hạn lời gọi bean hoặc event listener |

Hãy tạo một request đi từ orders qua API của billing. Trong tracing backend, so sánh trước/sau nâng cấp:

1. Có module span/observation tương ứng với luồng được instrument?
2. Các thuộc tính module vẫn có ý nghĩa đúng?
3. Parent/child hoặc span links có phản ánh quan hệ theo instrumentation không?
4. Span có được gửi tới backend không, hay chỉ có trong process vì chưa cấu hình exporter?

Insight starter cung cấp thành phần quan sát module; **không tự cấu hình tracing backend**. Với Spring Boot, cần tracing bridge (OpenTelemetry hoặc Brave), exporter phù hợp, sampling và đường gửi telemetry. Nếu trace không xuất hiện, phân biệt lỗi dependency, sampling, exporter, network và cơ chế propagation.

### 6.4. Context propagation qua asynchronous event

Nếu orders phát `OrderCompleted` và billing xử lý qua `@ApplicationModuleListener`, lời gọi có thể chuyển sang thread khác và transaction khác. Khi đó, một số thread-local observation context không tự di chuyển sang executor mới.

Sau nâng artifact, phải kiểm tra riêng executor/context propagation và tracing instrumentation; việc starter xuất hiện trong dependency tree **không bảo đảm** trace context được giữ qua thread, broker hoặc một lần retry sau restart. Khi event đi tới Kafka/AMQP, consumer cần instrument phù hợp để inject/extract trace headers. Dùng `eventId`/`correlationId` để đối chiếu nghiệp vụ qua các lần giao lại; không thay chúng bằng traceId.

## 7. Test và bằng chứng migration

Một thay đổi dependency thường ảnh hưởng trên ba cấp độ: **resolve**, **bootstrap** và **quan sát thật**. Vì thế thiết kế tối thiểu ba nhóm kiểm thử.

### 7.1. Kiểm thử graph và ranh giới module

Giữ một test kiểm tra kiến trúc:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModuleStructureTest {

    @Test
    void verifiesModuleBoundaries() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

Đây là ví dụ cần điều chỉnh package và main application class của dự án. Test này kiểm tra cấu trúc module, **không chứng minh Insight starter đang phát metrics hoặc spans**.

### 7.2. Kiểm thử Actuator

Với integration test có Actuator dependency trong runtime classpath, khởi động ứng dụng ở random port, bật endpoint `modulith` trong test profile và gọi HTTP tới endpoint. Kiểm tra:

- HTTP response hợp lệ.
- JSON có các module kỳ vọng và các dependency đã biết.
- Security policy test phản ánh cấu hình thử nghiệm, không làm lộ endpoint trong production.

Nếu ứng dụng chỉ chạy test bằng classpath thiếu các `runtimeOnly` dependencies hoặc loại trừ auto-configuration, kết quả test phải được diễn giải tương ứng. Trong Gradle, test runtime classpath thông thường chứa runtime dependencies của source set main, nhưng vẫn nên kiểm tra cấu hình build tùy chỉnh.

### 7.3. Kiểm thử metric và trace

Chạy một workload cố định gồm request hoặc event phát từ module orders sang billing, rồi thu:

- `/actuator/metrics/module.events.published` hoặc dữ liệu tương đương từ MeterRegistry.
- Một module entry span có thuộc tính module phù hợp.
- Log và trace backend thể hiện chuỗi xử lý.
- Nếu bất đồng bộ, xác nhận context propagation hoặc liên kết span hợp lệ.
- Nếu có externalization, kiểm chứng publication/broker riêng với module event metric.

**Đừng dùng một bộ assertions đếm chính xác số span nội bộ** nếu implementation instrumentation thay đổi giữa hai phiên bản; test cần xác nhận điều kiện nghiệp vụ và tính quan sát cốt lõi, tránh lệ thuộc hình dạng một trace không được cam kết.

### 7.4. Ma trận nghiệm thu

| Mã | Kiểm tra | Tiêu chí đạt |
|---|---|---|
| A1 | Starter được resolve | Đúng group/artifact và đúng version theo BOM |
| A2 | Artifact observability của nhánh đích | Có `-api` và `-core` đối với 2.x; không còn phụ thuộc 1.4.x không chủ đích |
| A3 | Compile classpath với custom API | Mã import API có dependency compile thích hợp và biên dịch |
| A4 | Runtime classpath | Có actuator, observability core, Boot actuator; không có version conflict |
| A5 | Boot compatibility | Phiên bản Spring Boot/Framework phù hợp với nhánh Modulith |
| A6 | Endpoint `/actuator/modulith` | Trả cấu trúc module hợp lệ trong môi trường kiểm thử được phép truy cập |
| A7 | Application event metric | Metric tăng khi event test được phát |
| A8 | Tracing instrumentation | Có module span với thuộc tính đúng khi tracer/exporter hoạt động |
| A9 | Context propagation | Không mất liên kết ngoài dự kiến khi qua executor/broker |
| A10 | Rollback | Có thể quay lại BOM/artifact trước với cấu hình triển khai đã lưu |

Nếu một hàng chưa được kiểm chứng, ghi trạng thái **chưa kiểm tra** cùng lý do. Tránh đánh dấu toàn bộ migration thành công chỉ vì dependency tree đã có đúng tên starter.

## 8. Chẩn đoán lỗi thường gặp

| Triệu chứng | Nguyên nhân khả dĩ | Cách điều tra |
|---|---|---|
| Gradle/Maven không tìm thấy `spring-modulith-observability` ở 2.x | Dùng tên artifact từ nhánh 1.4 | Đổi sang `-observability-core` hoặc starter; đối chiếu POM đúng phiên bản |
| Build thiếu class customization | Starter ở runtimeOnly, API không có ở compile | Thêm `spring-modulith-observability-api` ở compile scope nếu code dùng |
| Class/method không tồn tại sau update | API đã thay đổi hoặc import từ JAR cũ | Tra API docs và chỉnh code; không ép version cũ |
| `/actuator/modulith` trả 404 | Actuator module chưa được đăng ký, chưa expose hoặc base path thay đổi | Kiểm tra dependency, auto-config, expose và path |
| `/actuator/modulith` trả 401/403 | Security hoặc network hạn chế | Kiểm tra quyền truy cập trong môi trường test |
| Có endpoint nhưng không có spans | Thiếu observability core, tracer, exporter hoặc workload không đi qua module API instrumented | Kiểm tra runtime tree, instrumentation và backend |
| Metric `module.events.published` không xuất hiện | Chưa phát event, chưa đủ metrics integration hoặc meter chưa tạo | Phát event test và xem MeterRegistry/Actuator |
| Trace bị tách sau `@ApplicationModuleListener` | Thiếu context propagation qua executor | Kiểm tra executor thực tế và tracing context |
| Dependency tree có 1.4.x và 2.x | BOM hoặc dependency trực tiếp xung đột | Dùng dependencyInsight/effective POM để tìm nguồn ép version |
| Test module graph đạt nhưng runtime instrumentation lỗi | Test tĩnh chưa kiểm tra Actuator/Micrometer | Thêm runtime integration test và trace verification |

### 8.1. Vì sao không nên áp dụng exclusion mù quáng?

Khi thấy hai artifact phiên bản khác nhau, nhiều người thêm:

~~~groovy
configurations.all {
    exclude group: 'org.springframework.modulith',
            module: 'spring-modulith-observability'
}
~~~

Đây chỉ là ví dụ về **cách làm cần tránh như giải pháp đầu tiên**. Exclusion không chứng minh rằng starter đã kéo đủ artifact thay thế và có thể che mất nguyên nhân: dependency trực tiếp chưa được đổi, BOM sai hoặc starter khác kéo lại thư viện cũ. Hãy xác định nguồn trước, sau đó sửa dependency declaration/constraint tương ứng và chạy lại dependency tree lẫn integration tests.

## 9. Quy trình nâng phiên bản có thể kiểm toán

Áp dụng quy trình sau để thay đổi artifact Insight starter trong một hệ thống đang vận hành:

1. **Ghi baseline:** lưu Spring Boot/Modulith versions, Maven/Gradle dependency tree (compile/runtime), output `/actuator/modulith`, tên metrics, một vài trace mẫu và kết quả module boundary tests.
2. **Đọc release notes và BOM:** chọn phiên bản đích dựa trên compatibility matrix. Khi đi từ 1.4 sang 2.x, ghi rõ việc tách `spring-modulith-observability` thành `-api` và `-core`.
3. **Sửa khai báo dependency:** cập nhật BOM, giữ đúng tên `spring-modulith-starter-insight`; xóa các khai báo artifact cũ không còn phù hợp; chỉ thêm API compile khi mã thực sự sử dụng.
4. **Kiểm tra resolve:** lưu dependency tree mới, đảm bảo mọi artifact Spring Modulith thuộc cùng nhánh và các dependency framework không bị ép phiên bản ngoài dự kiến.
5. **Chạy kiểm thử:** unit/architecture test, Actuator endpoint, event metrics, module spans và event flow có context propagation.
6. **Đối chiếu staging:** kiểm tra tracing exporter, management endpoint exposure, Spring Security và chi phí/khối lượng metric. Xem sự khác biệt thật so với baseline.
7. **Quản lý rollback:** lưu nhánh BOM/config cũ và artifact triển khai cũ; xác định điều kiện quay về nếu endpoint/tracing/metrics không được bảo toàn.

Một thay đổi có thể được coi là đạt khi cả **dependency resolution** và **hành vi quan sát runtime** đều đáp ứng tiêu chí đã thống nhất. Bảng so sánh POM là bằng chứng về cấu trúc artifact, còn Actuator/metrics/traces là bằng chứng chức năng.

## 10. Bài tập vận dụng

Bạn tiếp nhận ứng dụng Spring Boot dùng Spring Modulith 1.4.x, có dependencies:

~~~groovy
dependencies {
    runtimeOnly 'org.springframework.modulith:spring-modulith-starter-insight'
    runtimeOnly 'org.springframework.modulith:spring-modulith-observability'
}
~~~

Yêu cầu là đánh giá nâng lên Spring Modulith 2.2.0 và kiểm chứng module observability. Hãy thực hiện lần lượt:

1. Ghi **dependency tree cũ**, chỉ ra artifact nào được kéo theo từ starter và artifact nào được khai báo trùng trực tiếp.
2. Import BOM cho 2.2.0 trong một nhánh thử nghiệm phù hợp Spring Boot đích.
3. Bỏ khai báo `spring-modulith-observability` của nhánh 1.4; giữ `spring-modulith-starter-insight`; nếu code dùng customization API thì thêm `spring-modulith-observability-api` ở compile.
4. Dùng Maven/Gradle xác nhận runtime có `spring-modulith-observability-core`, `spring-modulith-observability-api`, `spring-modulith-actuator` và Boot Actuator theo POM đích.
5. Khởi động ứng dụng thử nghiệm; so sánh `/actuator/modulith`, `module.events.published` và module spans với baseline.
6. Gửi event qua một listener bất đồng bộ. Chỉ ra nơi trace context có thể mất và cách xác nhận propagation độc lập với cấu trúc starter.
7. Hoàn thành ma trận A1–A10, ghi ảnh/log đã lược bỏ dữ liệu nhạy cảm và quyết định tiếp tục hay rollback dựa trên bằng chứng.

**Kết quả cần nộp:** bảng trước/sau theo artifact và scope, resolved versions, một bản module graph, snapshot Actuator và một trace mẫu có thuộc tính module. Trình bày rõ ba kết luận khác nhau: *artifact có trên classpath*, *tính năng đã được khởi tạo* và *tính năng có tạo dữ liệu quan sát chính xác*.

## Tài liệu tham khảo chính thức

- [Spring Modulith 1.4 — Appendix: Spring Modulith modules](https://docs.spring.io/spring-modulith/reference/1.4/appendix.html): danh sách starter và artifact observability ở nhánh 1.4.
- [Spring Modulith 2.2 — Appendix: Spring Modulith modules](https://docs.spring.io/spring-modulith/reference/2.2/appendix.html): thành phần `spring-modulith-starter-insight` và `observability-api`/`observability-core`.
- [Spring Modulith 2.2 — Production-ready Features](https://docs.spring.io/spring-modulith/reference/2.2/production-ready.html): cách dùng starter, module Actuator, spans và event metrics.
- [Spring Modulith — Main reference](https://docs.spring.io/spring-modulith/reference/): Spring Modulith BOM và các nhánh phiên bản.
- [Spring — Release 2.2 GA (19/11/2026)](https://spring.io/blog/2026/11/19/spring-modulith-2-2-ga-2-1-3-and-2-0-10-released/): bối cảnh bản GA và nền Spring Boot/Framework.
- [Spring Boot — Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html): endpoint exposure và security.
- [Spring Boot — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html): cách tích hợp metrics, tracing bridge, exporter và context propagation.
