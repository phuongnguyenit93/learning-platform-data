# Khi nên dùng starter và khi khai báo artifact riêng

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích vai trò của **Spring Modulith Insight starter** trong quan sát các application module của ứng dụng Spring Boot.
- Chọn giữa **`spring-modulith-starter-insight`** và các artifact riêng lẻ như **`spring-modulith-actuator`**, **`spring-modulith-observability-core`**, **`spring-modulith-observability-api`**.
- Phân biệt công cụ quan sát lúc ứng dụng chạy với công cụ **sinh tài liệu module** lúc build/test.
- Khai báo dependency Maven hoặc Gradle đúng **scope**, tránh lặp starter, nhầm phạm vi compile/runtime hoặc thiếu phần xuất telemetry.
- Kiểm tra lựa chọn của mình bằng dependency tree, Actuator endpoint và dữ liệu quan sát thực tế.

## 1. Đặt bài toán đúng: ta muốn thấy gì ở application module?

Giả sử ứng dụng bán hàng có ba application module: `orders`, `inventory` và `payments`. Nhóm phát triển có ba nhu cầu:

1. **Xem cấu trúc:** module nào tồn tại và module nào phụ thuộc module nào?
2. **Quan sát luồng chạy:** khi `orders` gọi API của `inventory`, có tạo span/trace để tìm nguyên nhân chậm hoặc lỗi không?
3. **Sinh tài liệu lâu dài:** tạo sơ đồ component, Application Module Canvas để review trên pull request hoặc đưa vào tài liệu kiến trúc.

Cả ba nhu cầu đều liên quan đến kiến trúc module, nhưng không nhất thiết dùng cùng một dependency. Spring Modulith cung cấp một **starter tiện dụng cho runtime insight**, đồng thời công bố những artifact riêng cho từng khả năng.

Trong bài này:

- **Starter** là artifact gom nhiều dependency thường dùng cùng nhau, giúp bật nhanh một tập khả năng.
- **Artifact riêng** là một thư viện cụ thể được khai báo trực tiếp để sử dụng đúng tính năng cần thiết.
- **Application module** là đơn vị tổ chức nghiệp vụ trong ứng dụng. Đây không phải tên gọi khác của Maven artifact hay Gradle module.

Phân biệt ba khái niệm này rất quan trọng: một ứng dụng có 10 application module vẫn có thể chỉ cần **một** dependency `spring-modulith-starter-insight` ở runtime.

## 2. Insight starter thực sự mang theo gì?

Theo tài liệu Spring Modulith, `spring-modulith-starter-insight` gom các thành phần sau (chi tiết dependency và scope nội bộ có thể khác theo dòng phiên bản):

| Artifact được gom | Trách nhiệm |
| --- | --- |
| `spring-modulith-actuator` | Đưa thông tin cấu trúc application module ra thông qua Spring Boot Actuator. |
| `spring-modulith-observability-core` | Instrument tương tác giữa các module để tạo thông tin quan sát, bao gồm Micrometer observations/spans. |
| `spring-modulith-observability-api` | Các API tùy biến observability, chẳng hạn tùy biến metrics cho event publication hoặc observation convention. |
| `spring-boot-starter-actuator` | Hạ tầng Actuator chung của Spring Boot để đăng ký và quản lý các endpoint, tích hợp quan sát vận hành. |

Trong bảng dependency công bố bởi Spring Modulith 2.2, starter mang `spring-modulith-observability-api` ở compile scope **trong POM của starter**, còn các thành phần khác ở runtime scope. Tuy nhiên, nếu **dự án của bạn khai báo chính starter ở runtime scope**, API đó không tự nhiên có mặt trong **compile classpath của chính dự án**. Khi viết code dùng lớp tùy biến thuộc API, vẫn cần khai báo API ở compile scope tại dự án. Đây là lý do thực tế để kết hợp starter với một artifact riêng có chủ đích.

### 2.1. Những gì starter không tự cung cấp

Thêm Insight starter **không đồng nghĩa** với:

- Có ngay giao diện Zipkin, Grafana hay Jaeger hoặc một exporter đã kết nối;
- Tự sinh sơ đồ PlantUML/Asciidoc thành tài liệu versioned trong repository;
- Tự công khai mọi Actuator endpoint qua HTTP cho bên ngoài;
- Tự truyền trace context qua mọi executor, message broker hoặc giao thức tùy chỉnh;
- Tự đảm bảo nghiệp vụ đúng hoặc mọi event được xử lý đúng một lần;
- Tự thay thế các artifact riêng về event publication registry/persistence, testing hoặc documentation.

Starter kích hoạt **phần hỗ trợ Insight trong ứng dụng**. Để gửi trace tới hệ thống ngoài, ứng dụng vẫn cần bridge/exporter và cấu hình hạ tầng tương ứng với phiên bản Spring Boot. Để tạo tài liệu kiến trúc trong build/test, dùng `spring-modulith-docs` hoặc starter-test có chứa artifact đó.

## 3. Khi nào nên dùng `spring-modulith-starter-insight`?

**Ưu tiên starter** nếu nhóm muốn cả hai năng lực sau trong môi trường đang chạy:

- Đưa cấu trúc application module ra qua Actuator.
- Quan sát lời gọi đi qua API application module và event publication bằng tích hợp observability của Spring Modulith.

Đây là lựa chọn phù hợp cho:

- **Dự án mới** đang xây modular monolith và muốn nhìn tổng thể kiến trúc cùng tương tác module.
- **Môi trường staging** để kiểm tra module graph, luồng xử lý khi tạo đơn, thanh toán hoặc xuất kho.
- **Hệ thống production** có nhu cầu điều tra qua Actuator/metrics/traces và đã có cấu hình phân quyền, exporter, sampling và lưu trữ telemetry phù hợp.
- **Nhóm muốn cấu hình đơn giản**, sử dụng bộ tính năng phổ biến thay vì quản lý các dependency runtime riêng lẻ.

### 3.1. Maven: bắt đầu bằng starter

Giả sử dự án đã quản lý phiên bản Spring Modulith bằng BOM tương thích với Spring Boot đang dùng:

~~~xml
<dependencies>
    <!-- Gom Actuator và observability của Spring Modulith -->
    <dependency>
        <groupId>org.springframework.modulith</groupId>
        <artifactId>spring-modulith-starter-insight</artifactId>
        <scope>runtime</scope>
    </dependency>
</dependencies>
~~~

Không cần thêm `spring-modulith-actuator` và `spring-modulith-observability-core` một lần nữa khi chỉ muốn các tính năng mặc định do starter đã kéo vào.

### 3.2. Gradle: cùng mục đích, tương đương runtimeOnly

~~~groovy
dependencies {
    runtimeOnly 'org.springframework.modulith:spring-modulith-starter-insight'
}
~~~

Ví dụ trên cũng giả định dự án đã import BOM hoặc cơ chế quản lý phiên bản tương đương. Chọn **runtime** vì các hook quan sát và endpoint cần hoạt động lúc ứng dụng chạy, không nhất thiết phải được mã nghiệp vụ import ở compile time.

### 3.3. Vì sao “nhanh bật” vẫn cần kiểm tra?

Sau khi thêm dependency, nhóm cần xác minh ít nhất:

1. Ứng dụng khởi động và các component/module được phát hiện như dự kiến.
2. Endpoint `modulith` có được đăng ký; khả năng truy cập HTTP phù hợp cấu hình Actuator và bảo mật.
3. Có dữ liệu Micrometer observation/trace cho những tương tác module thực sự được instrument.
4. Pipeline xuất và thu thập telemetry đang hoạt động nếu nhóm muốn xem traces ở một backend ngoài.

**Dependency có trên classpath là điều kiện khởi đầu, không phải bằng chứng cả chuỗi quan sát đã hoạt động.**

## 4. Khi nào khai báo artifact riêng?

Chọn artifact riêng khi **chỉ cần một phần** của gói Insight, hoặc cần API ở compile scope cho logic cấu hình tùy biến. Mục tiêu chính là làm rõ năng lực ứng dụng phải mang ở runtime, không thêm hạ tầng dư thừa.

| Nhu cầu thực tế | Lựa chọn ưu tiên | Ghi chú bắt buộc |
| --- | --- | --- |
| Cần **cả Actuator module** lẫn **observability module** | `spring-modulith-starter-insight` | Tối giản dependency; vẫn cấu hình endpoint/exporter khi cần. |
| **Chỉ cần /actuator/modulith**, chưa cần trace module | `spring-modulith-actuator` + `spring-boot-starter-actuator` | Cấu hình HTTP exposure và security phù hợp. |
| **Chỉ muốn instrument tương tác module** | `spring-modulith-observability-core` | Bổ sung hạ tầng Micrometer/Actuator/exporter phù hợp; không cần module actuator endpoint nếu không dùng. |
| Muốn **code Java tham chiếu customizer/convention** | `spring-modulith-observability-api` ở compile scope, cùng core hoặc starter ở runtime | Một runtime-only starter không đủ để compile mã import API. |
| Muốn **sinh sơ đồ và canvas trong test/build** | `spring-modulith-docs` ở test scope, hoặc `spring-modulith-starter-test` | Đây là nhu cầu documentation, khác runtime Insight. |
| Chỉ cần **kiểm thử ranh giới module** | `spring-modulith-starter-test` hoặc artifact test thích hợp | Không cần Insight starter chỉ để test kiến trúc. |
| Muốn **lưu và phát lại event publication** | Chọn artifact events/persistence theo datastore | Insight starter không thay thế event publication registry. |

### 4.1. Trường hợp A: chỉ cần xem module graph qua Actuator

Một ứng dụng triển khai trong mạng nội bộ muốn cung cấp thông tin module cho công cụ giám sát kiến trúc, nhưng tạm thời không cần instrument module method calls. Có thể chọn hai dependency:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.modulith</groupId>
        <artifactId>spring-modulith-actuator</artifactId>
        <scope>runtime</scope>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
</dependencies>
~~~

Tương đương Gradle:

~~~groovy
dependencies {
    runtimeOnly 'org.springframework.modulith:spring-modulith-actuator'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
~~~

Spring Boot Actuator và Spring Modulith actuator có hai trách nhiệm khác nhau: Boot cung cấp cơ chế endpoint; Modulith cung cấp endpoint đặc thù mô tả application module. Chỉ thêm `spring-modulith-actuator` mà không có Actuator hạ tầng phù hợp sẽ không đáp ứng đầy đủ mục tiêu.

Ví dụ cấu hình **chủ động** đưa endpoint `modulith` ra HTTP, bên cạnh hai endpoint được chọn:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,modulith
~~~

Với cổng và base path mặc định, thử:

~~~bash
curl -i http://localhost:8080/actuator/modulith
~~~

Phản hồi điển hình mô tả module, base package và các quan hệ phụ thuộc dưới dạng **JSON**. Nó **không phải** hình PlantUML hay sơ đồ auto-generated sẵn hiển thị như ảnh. Ở production, việc expose endpoint phải đi cùng chính sách xác thực, phân quyền và giới hạn mạng; đừng mở rộng tập endpoint chỉ để thử nghiệm.

### 4.2. Trường hợp B: chỉ cần observability, không cần endpoint cấu trúc

Một nhóm đã có công cụ theo dõi HTTP, database và message processing; họ muốn bổ sung span cho **các tương tác ở ranh giới application module** nhưng không muốn bật `/actuator/modulith`.

Có thể dùng:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.modulith</groupId>
        <artifactId>spring-modulith-observability-core</artifactId>
        <scope>runtime</scope>
    </dependency>

    <!-- Hạ tầng Spring Boot observability trong ví dụ này -->
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
</dependencies>
~~~

Gradle:

~~~groovy
dependencies {
    runtimeOnly 'org.springframework.modulith:spring-modulith-observability-core'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
~~~

**Ranh giới trách nhiệm:**

- `spring-modulith-observability-core` thêm instrumentation liên quan tới application module.
- Spring Boot/Micrometer tạo hạ tầng observation và tích hợp hệ thống quan sát.
- Bridge/exporter và backend cụ thể là phần chọn riêng theo chiến lược tracing/metrics.

Nếu chỉ muốn xem số liệu bên trong một hệ thống quan sát hiện có, không nhất thiết cần thêm endpoint module graph. Tuy nhiên, **không nên suy ra rằng mọi method ở mọi package sẽ thành một span**: phạm vi instrumentation của Spring Modulith tập trung vào các thành phần thuộc **API của application module** và hành vi framework hỗ trợ.

### 4.3. Trường hợp C: muốn tùy biến metric hoặc observation từ code ứng dụng

Đây là tình huống rất hay gặp lỗi scope. Ví dụ nhóm muốn thêm nhãn **channel** (tập hữu hạn như WEB/STORE) vào metric của một loại event, hoặc thay đổi convention hiển thị span.

Nếu dự án đã dùng Insight starter ở **runtime**:

~~~groovy
dependencies {
    runtimeOnly 'org.springframework.modulith:spring-modulith-starter-insight'

    // Cho phép mã Java của ứng dụng import các interface customization
    implementation 'org.springframework.modulith:spring-modulith-observability-api'
}
~~~

Hoặc khi không muốn starter:

~~~groovy
dependencies {
    runtimeOnly 'org.springframework.modulith:spring-modulith-observability-core'
    implementation 'org.springframework.modulith:spring-modulith-observability-api'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
~~~

Mẫu tùy biến được Spring Modulith hỗ trợ thông qua `ModulithEventMetricsCustomizer`. Đoạn mã dưới đây là minh họa ý tưởng cho một event do ứng dụng tự định nghĩa:

~~~java
@Configuration(proxyBeanMethods = false)
class ModulithObservabilityConfiguration {

    @Bean
    ModulithEventMetricsCustomizer eventMetricsCustomizer() {
        return metrics -> metrics.customize(
            OrderCompleted.class,
            (event, meter) -> meter.tags("channel", event.channel())
        );
    }
}
~~~

**Giả định của ví dụ:** `OrderCompleted` là kiểu event tự định nghĩa; `event.channel()` trả về một giá trị **String** thuộc tập nhỏ, ổn định (ví dụ `WEB` hoặc `STORE`). Các import đã được lược bớt; mã cần được ghép với mô hình event thực tế của dự án.

Không đưa `orderId`, mã khách hàng, email hoặc request ID vào **metric tags**, vì số giá trị khác nhau có thể tăng không kiểm soát (high cardinality). Khi cần tra cứu một đơn cụ thể, dùng log/trace với chính sách dữ liệu thích hợp; metric tag ưu tiên dữ liệu tổng hợp.

Trường hợp API cần thiết trong compile scope **không chứng minh phải thay hẳn starter**. Chỉ cần thêm artifact API phù hợp cho phần code tùy biến.

## 5. Sinh tài liệu module là một công việc khác với bật Insight

Tên học phần có cả **documentation** và **observability**, nên rất dễ nhầm rằng chỉ dùng Insight starter là đủ để sinh tài liệu PlantUML và Canvas. Thực tế:

- **Insight starter:** tác động ở **runtime**; giúp quan sát cấu trúc module qua Actuator và tương tác module qua telemetry.
- **`spring-modulith-docs`:** phục vụ **test/build**; API `Documenter` tạo tài liệu (ví dụ PlantUML và Application Module Canvas) từ mô hình module.
- **`spring-modulith-starter-test`:** gói hỗ trợ kiểm thử, có thể kéo theo `spring-modulith-docs`; khi đã dùng starter-test thì thường không phải khai báo docs thêm lần nữa.

### 5.1. Thêm artifact documentation

~~~xml
<dependency>
    <groupId>org.springframework.modulith</groupId>
    <artifactId>spring-modulith-docs</artifactId>
    <scope>test</scope>
</dependency>
~~~

Gradle:

~~~groovy
dependencies {
    testImplementation 'org.springframework.modulith:spring-modulith-docs'
}
~~~

Ví dụ test sinh tài liệu (thay `ShopApplication` bằng application class thực tế):

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;
import org.springframework.modulith.docs.Documenter;

class ModuleDocumentationTest {

    @Test
    void generatesArchitectureDocumentation() {
        var modules = ApplicationModules.of(ShopApplication.class);

        new Documenter(modules)
            .writeModulesAsPlantUml()
            .writeIndividualModulesAsPlantUml()
            .writeModuleCanvases();
    }
}
~~~

Các file kết quả được ghi trong thư mục **`spring-modulith-docs`** bên dưới output directory của build (ví dụ `target/spring-modulith-docs` hoặc `build/spring-modulith-docs`, tùy công cụ và phiên bản). Thư viện tạo **tệp tài liệu**, không tự động triển khai một website documentation và không cần phải chạy trong production chỉ để sinh file này.

### 5.2. Hai thứ có thể dùng cùng nhau

Một dự án muốn sinh tài liệu lúc CI và quan sát lúc chạy có thể cấu hình:

~~~groovy
dependencies {
    runtimeOnly 'org.springframework.modulith:spring-modulith-starter-insight'
    testImplementation 'org.springframework.modulith:spring-modulith-docs'
}
~~~

Hai dependency đảm nhận hai thời điểm khác nhau trong vòng đời ứng dụng. Nếu dự án đã có `spring-modulith-starter-test`, hãy kiểm tra cây dependency trước khi khai báo thêm `spring-modulith-docs`.

## 6. Ra quyết định bằng sơ đồ

~~~mermaid
flowchart TD
    A["Cần khả năng nào?"] --> B{"Có cần runtime insight?"}
    B -->|"Không"| C{"Cần sinh sơ đồ/canvas hay test?"}
    C -->|"Có"| D["spring-modulith-docs hoặc starter-test ở test scope"]
    C -->|"Không"| E["Không thêm Insight chỉ vì dùng application module"]
    B -->|"Có"| F{"Cần cả module Actuator và observability?"}
    F -->|"Có"| G["spring-modulith-starter-insight ở runtime"]
    F -->|"Chỉ Actuator"| H["spring-modulith-actuator + Boot Actuator"]
    F -->|"Chỉ observability"| I["spring-modulith-observability-core + hạ tầng telemetry"]
    G --> J{"Code có import API customization?"}
    I --> J
    J -->|"Có"| K["Thêm spring-modulith-observability-api ở compile"]
    J -->|"Không"| L["Kiểm tra runtime và cách xuất dữ liệu"]
    K --> L
    H --> L
~~~

**Cách đọc sơ đồ:** chọn theo **tính năng phải có và thời điểm sử dụng**. Không cần cố loại bỏ starter chỉ vì ứng dụng lớn; cũng không nên thêm starter vào mọi service nếu chỉ cần một endpoint cấu trúc.

## 7. Ví dụ quyết định theo yêu cầu thực tế

### Tình huống 1 — Dự án demo modular monolith

**Yêu cầu:** muốn xem `/actuator/modulith`, đồng thời tìm trace khi `orders` gọi `inventory`.

**Lựa chọn:** `spring-modulith-starter-insight` ở runtime.

**Công việc kèm theo:** bật/giới hạn endpoint mong muốn và cấu hình hệ thống xuất telemetry nếu cần xem traces trên backend.

**Lý do:** đây là đúng nhóm tính năng mà starter gom sẵn.

### Tình huống 2 — Bộ phận kiến trúc chỉ cần danh sách module lúc chạy

**Yêu cầu:** một dashboard nội bộ đọc JSON mô tả module để đối chiếu với kiến trúc đã duyệt, chưa cần module spans.

**Lựa chọn:** `spring-modulith-actuator` và Spring Boot Actuator.

**Lý do:** giới hạn phạm vi triển khai ở tính năng cần dùng; tránh mang thêm instrumentation module khi chưa có yêu cầu.

### Tình huống 3 — Hệ thống đã có distributed tracing nhưng thiếu ranh giới module

**Yêu cầu:** giữ pipeline telemetry hiện tại và bổ sung span tại giao điểm giữa các application module. Nhóm không muốn công khai module graph endpoint.

**Lựa chọn:** `spring-modulith-observability-core` cùng hạ tầng Micrometer đã có.

**Lý do:** nâng độ chi tiết của trace theo module mà không cần gói toàn bộ Insight. Kiểm tra khả năng context propagation tại các luồng bất đồng bộ riêng.

### Tình huống 4 — CI cần sơ đồ kiến trúc cho reviewer

**Yêu cầu:** tạo component diagram và module canvas trên mỗi lần chạy kiểm thử; production không cần Actuator `modulith` hoặc module spans.

**Lựa chọn:** `spring-modulith-docs` ở test scope (hoặc `spring-modulith-starter-test` nếu cũng cần test module).

**Lý do:** tài liệu sinh ra là **build artifact**; Insight starter không phải công cụ thay thế cho `Documenter`.

### Tình huống 5 — Production dùng Insight và cần metric tùy biến

**Yêu cầu:** có sẵn module spans và Actuator, cần bổ sung một tag nghiệp vụ có giá trị hữu hạn cho event metric.

**Lựa chọn:** giữ `spring-modulith-starter-insight` ở runtime, **thêm** `spring-modulith-observability-api` ở compile scope.

**Lý do:** mã cấu hình phải biên dịch được với kiểu API công khai; scope runtime không cấp quyền truy cập compile cho nguồn ứng dụng.

## 8. Scope và phiên bản: nơi cấu hình dễ sai nhất

### 8.1. Dùng dependency đúng vòng đời

| Scope | Thường dùng cho | Vì sao |
| --- | --- | --- |
| Maven `runtime` / Gradle `runtimeOnly` | Insight starter, Modulith actuator, observability core | Hỗ trợ được tạo và sử dụng khi ứng dụng chạy. |
| Maven `compile` / Gradle `implementation` | API observability được import trực tiếp; hạ tầng Boot dùng từ mã/config ứng dụng | Cần hiện diện khi biên dịch hoặc được dự án dùng như phụ thuộc triển khai. |
| Maven `test` / Gradle `testImplementation` | `spring-modulith-docs`, hỗ trợ test module | Không cần đóng gói sinh tài liệu/kiểm thử vào runtime production. |

Đừng áp dụng máy móc “mọi artifact của Modulith đều là runtime”: artifact cung cấp annotation, interface mà code ứng dụng import phải có ở **compile classpath**; thư viện tạo test/documentation thường chỉ cần trong **test classpath**.

### 8.2. Quản lý version bằng BOM

Spring Modulith có BOM để các artifact cùng họ dùng phiên bản tương thích. Với Maven, có thể khai báo (ví dụ dưới dùng phiên bản minh họa, phải chọn phiên bản tương thích với Spring Boot của dự án):

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

Khi BOM đã được import, các dependency của Spring Modulith ở ví dụ trên không cần ghi `<version>` riêng. Với Gradle, một hướng tiếp cận là:

~~~groovy
dependencies {
    implementation platform('org.springframework.modulith:spring-modulith-bom:2.2.0')
    runtimeOnly 'org.springframework.modulith:spring-modulith-starter-insight'
}
~~~

Ví dụ này chỉ minh họa cách dùng BOM; dependency management thực tế có thể do Spring Boot plugin hoặc build chung của tổ chức cung cấp. **Không mặc định dự án sử dụng Spring Boot nào cũng phù hợp với Modulith 2.2.0**: phải kiểm tra compatibility matrix của phiên bản đang chọn. Đồng thời, phiên bản tài liệu Spring Modulith thay đổi theo thời gian; tên artifact hoặc khả năng cụ thể cần đối chiếu với release thực tế.

### 8.3. Tránh thêm dependency trùng về mục đích

Hai khai báo dưới đây thường không cần thiết khi không tùy biến:

~~~groovy
dependencies {
    runtimeOnly 'org.springframework.modulith:spring-modulith-starter-insight'

    // Starter đã mang những phần hỗ trợ này theo:
    runtimeOnly 'org.springframework.modulith:spring-modulith-actuator'
    runtimeOnly 'org.springframework.modulith:spring-modulith-observability-core'
}
~~~

Gradle/Maven thường giải quyết cùng một artifact thành một phiên bản trong graph, nên “khai báo trùng” không có nghĩa chắc chắn sẽ đóng gói hai bản JAR. Vấn đề chính là **ý định cấu hình trở nên khó hiểu**, dễ phát sinh version override và khiến người bảo trì khó biết dependency nào thực sự cần thiết.

Nếu bắt buộc loại trừ hoặc thay một transitive dependency vì xung đột, cần kiểm tra kỹ cây phụ thuộc và thử vận hành tính năng liên quan trước khi quyết định. **Đừng exclude một thành phần chỉ vì nó có vẻ chưa dùng** khi chưa hiểu starter cần thành phần đó ở đâu.

## 9. Kiểm chứng cấu hình sau khi chọn

Lựa chọn dependency được xem là hợp lý khi vừa **đúng mục tiêu** vừa **được kiểm chứng ở runtime/build**.

| Kiểm chứng | Cách làm | Kết quả kỳ vọng |
| --- | --- | --- |
| **Classpath** | Với Maven dùng `mvn dependency:tree`; với Gradle dùng `./gradlew dependencies --configuration runtimeClasspath`. | Có đúng các artifact cần thiết, phiên bản đồng bộ; không có phụ thuộc bất ngờ đáng chú ý. |
| **Actuator module** | Kiểm tra endpoint Actuator và thử `GET /actuator/modulith` trong môi trường được cấp quyền. | Nhìn thấy JSON mô tả module khi đã bật dependency và exposure đúng. |
| **Observability** | Chạy nghiệp vụ đi từ `orders` sang `inventory` qua API module và kiểm tra spans/metrics trong công cụ đã cấu hình. | Có tín hiệu thực tế từ instrumentation tương ứng; không chỉ chứng minh ứng dụng startup thành công. |
| **Context propagation** | Gửi event bất đồng bộ hoặc qua executor/broker và quan sát liên hệ giữa các spans. | Có tương quan đúng nếu cấu hình propagation hỗ trợ đường đi đó. |
| **Documentation** | Chạy test gọi `Documenter` và kiểm tra thư mục output. | Có file PlantUML/Canvas được sinh, đúng bản mã nguồn được test. |
| **Bảo mật và chi phí** | Xem những endpoint thực sự exposed, lượng spans/metrics, sampling và cardinality. | Chỉ bật/thu thập những dữ liệu cần thiết, có kiểm soát truy cập. |

### 9.1. Khi “starter đã thêm nhưng không thấy trace”

Đi theo các câu hỏi theo thứ tự:

1. **Có đường gọi được instrument không?** Truy vết một lời gọi đi qua API của application module thay vì chỉ gọi private method trong nội bộ.
2. **Có Micrometer observation/tracing bridge không?** Hạ tầng ghi span trong ứng dụng khác với việc exporter gửi span đi.
3. **Exporter và backend có hoạt động không?** Địa chỉ, xác thực, giao thức và khả năng kết nối có thể sai.
4. **Sampling có bỏ mẫu không?** Tracing có thể chỉ ghi một tỷ lệ request.
5. **Có đi qua ranh giới async không?** Cần xác minh context propagation phù hợp với cơ chế thực tế.

Thay `spring-modulith-starter-insight` bằng một loạt artifact riêng **không phải cách mặc định để sửa vấn đề exporter hoặc sampling**. Hãy phân loại lỗi theo lớp trước khi đổi dependency.

### 9.2. Khi “đã có Modulith nhưng không thấy sơ đồ”

Hỏi rõ **sơ đồ cần xem ở đâu**:

- Nếu muốn **JSON cấu trúc module trong ứng dụng đang chạy**, sử dụng Actuator module.
- Nếu muốn **file diagram/canvas đưa vào tài liệu**, chạy `Documenter` với `spring-modulith-docs` trong test/build.

Đây là hai đầu ra khác nhau. Cấu hình cái này không tự tạo đầu ra của cái kia.

## 10. Bài tập quyết định dependency

**Bài 1.** Dự án Spring Boot đã có Actuator, chỉ muốn mở thêm endpoint mô tả module, không muốn thêm module spans. Nên chọn artifact nào? Cần xác minh thêm cấu hình nào?

**Bài 2.** Nhóm thêm `spring-modulith-starter-insight` bằng Gradle `runtimeOnly`. Một class cấu hình import `ModulithEventMetricsCustomizer` nhưng không compile. Hãy giải thích nguyên nhân và viết thay đổi dependency nhỏ nhất.

**Bài 3.** CI cần sinh PlantUML mỗi lần build nhưng production không được có module Actuator endpoint. Có cần starter Insight không? Lựa chọn scope nào phù hợp?

**Bài 4.** Trên production đã có Insight starter và HTTP success metrics nhưng không thấy trace của lời gọi module trong backend. Hãy liệt kê các giả thuyết về instrumentation, tracing bridge, exporter và sampling.

**Bài 5.** Nhóm muốn dùng một dependency duy nhất để vừa thu trace vừa bảo đảm event publication không bao giờ mất. Vì sao kỳ vọng đó vượt phạm vi của Insight starter? Tính năng nào cần thiết kế riêng?

## 11. Ghi nhớ và tài liệu tham khảo

**Nguyên tắc chọn dependency:** Khi cần **cả Actuator module và observability ở runtime**, chọn **`spring-modulith-starter-insight`** để cấu hình gọn. Khi chỉ cần **một năng lực** hoặc phải **import API customization lúc compile**, khai báo **artifact tương ứng**. Khi mục tiêu là **sinh sơ đồ hoặc Canvas**, dùng **`spring-modulith-docs` trong test/build**. Luôn kiểm tra tương thích phiên bản, scope và khả năng quan sát thực tế, kể cả exporter, context propagation và bảo mật Actuator.

Nguồn đọc thêm (tài liệu chính thức Spring Modulith; nội dung có thể khác giữa các release):

- [Production-ready Features — Insight starter, Actuator và Observability](https://docs.spring.io/spring-modulith/reference/production-ready.html).
- [Appendix — danh sách starter/artifact và scope](https://docs.spring.io/spring-modulith/reference/appendix.html).
- [Documenting Application Modules — Documenter và Application Module Canvas](https://docs.spring.io/spring-modulith/reference/documentation.html).
- [Spring Modulith Reference — phiên bản, BOM và hướng dẫn chung](https://docs.spring.io/spring-modulith/reference/).
