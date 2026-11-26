# Cấu trúc data của ConfigMap và kiểu dữ liệu thực tế

Trong chương **ConfigMap** của module **Spring Cloud Kubernetes (SPRING_CLOUD_KUBERNETES)**, điều cần phân biệt đầu tiên là kiểu dữ liệu được Kubernetes lưu và kiểu dữ liệu mà ứng dụng Java sử dụng. Một giá trị `"20"` trong ConfigMap có thể trở thành `Integer` trong ứng dụng, nhưng Kubernetes không vì thế có một trường cấu hình kiểu số nguyên.

Bài học tập trung vào cấu trúc `data`, cách biểu diễn giá trị và đường đi từ ConfigMap đến Spring. Phần đọc ConfigMap qua API lấy **Spring Cloud Kubernetes 3.3.3 với client Fabric8** làm mốc minh họa; không trộn cơ chế Config Data với bootstrap cũ. Những tính năng như DiscoveryClient, Spring Cloud LoadBalancer và Configuration Watcher chỉ cần bổ sung khi triển khai thực sự có yêu cầu tương ứng.

## 1. `data` là một bảng ánh xạ từ chuỗi sang chuỗi

Cấu trúc cốt lõi có thể hình dung như sau:

~~~text
ConfigMap
├── metadata
│   ├── name
│   └── namespace
├── data: Map<String, String>
└── binaryData: dữ liệu nhị phân
~~~

Trong định nghĩa API Kubernetes, `Data` có kiểu `map[string]string`; mỗi khóa và mỗi giá trị của trường này đều là chuỗi. Cấu trúc này được thể hiện trực tiếp trong [định nghĩa ConfigMap của Kubernetes](https://github.com/kubernetes/api/blob/v0.34.0/core/v1/types.go#L7417).

Ví dụ đầy đủ cho một ConfigMap chứa các thuộc tính trực tiếp:

~~~yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: order-settings
  namespace: cm-types-lab
data:
  app.orders.enabled: "true"
  app.orders.max-items: "20"
  app.orders.timeout: "3s"
  app.orders.tenant-code: "00123"
  app.orders.allowed-regions: "vn-south,vn-north"
  app.orders.routing-weights.standard: "80"
  app.orders.routing-weights.express: "20"
  app.orders.message: "Đơn hàng đang được xử lý"
  app.orders.metadata-json: '{"channel":"web","level":2}'
~~~

Ở tầng Kubernetes:

| Khóa trong `data` | Nội dung giá trị | Kiểu được lưu trong `data` |
| --- | --- | --- |
| `app.orders.enabled` | `true` | Chuỗi |
| `app.orders.max-items` | `20` | Chuỗi |
| `app.orders.timeout` | `3s` | Chuỗi |
| `app.orders.tenant-code` | `00123` | Chuỗi |
| `app.orders.allowed-regions` | `vn-south,vn-north` | Chuỗi |
| `app.orders.metadata-json` | `{"channel":"web","level":2}` | Chuỗi chứa văn bản JSON |

Dấu nháy trong manifest YAML xác định cách parser hiểu giá trị; dấu nháy bao quanh `"20"` không trở thành một phần của chuỗi được lưu. Với ví dụ JSON, các dấu nháy đơn bên ngoài thuộc cú pháp YAML, còn các dấu nháy kép bên trong thuộc nội dung JSON.

`metadata.name` là tên đối tượng ConfigMap. `app.orders.max-items` là một khóa dữ liệu bên trong đối tượng ấy. Hai loại tên này có nhiệm vụ khác nhau và không thay thế cho nhau.

## 2. Vì sao manifest YAML hợp cú pháp vẫn có thể sai kiểu?

YAML có thể biểu diễn số, boolean, mapping và sequence. Tuy nhiên, schema của `ConfigMap.data` chỉ chấp nhận giá trị chuỗi. Một tài liệu có thể đúng cú pháp YAML nhưng không phù hợp với schema tài nguyên Kubernetes.

### 2.1. Số và boolean trực tiếp phải được biểu diễn thành chuỗi

Đoạn sau là **ví dụ sai**, không dùng làm manifest triển khai:

~~~yaml
data:
  app.orders.enabled: true
  app.orders.max-items: 20
~~~

Parser có thể đọc `true` thành boolean và `20` thành số. Khi đối chiếu với `data` của ConfigMap, đó không phải các giá trị chuỗi mà trường này yêu cầu.

Biểu diễn phù hợp:

~~~yaml
data:
  app.orders.enabled: "true"
  app.orders.max-items: "20"
~~~

Điều này áp dụng khi dùng công cụ sinh manifest: phải kiểm tra manifest cuối cùng mà công cụ gửi lên Kubernetes. Giá trị đầu vào của template là một số không có nghĩa công cụ sẽ tự chuyển kết quả sang chuỗi đúng với `data`.

### 2.2. Không đặt mapping hoặc sequence trực tiếp làm giá trị của `data`

Ví dụ sai với một mapping:

~~~yaml
data:
  app.orders:
    max-items: 20
    enabled: true
~~~

Ví dụ sai với một danh sách:

~~~yaml
data:
  app.orders.allowed-regions:
    - vn-south
    - vn-north
~~~

Cả hai đều không phải `Map<String, String>`. Có thể chuyển sang các khóa phẳng có giá trị chuỗi hoặc đặt toàn bộ YAML vào một chuỗi nhiều dòng, như ở phần 4.

### 2.3. Quy tắc khóa của Kubernetes khác quy tắc tên thuộc tính Spring

Khóa của `data` dùng chữ cái, chữ số, dấu `-`, `_` và `.`. Chẳng hạn, `app.orders.max-items` là tên khóa phù hợp. Dấu `[`, `]` hoặc `/` không thuộc tập ký tự này; xem [mô tả trường data trong API ConfigMap](https://kubernetes.io/docs/reference/kubernetes-api/core/config-map-v1/).

Vì vậy, không đưa trực tiếp khóa sau vào `data`:

~~~yaml
data:
  "app.orders.allowed-regions[0]": "vn-south"
~~~

Dấu nháy chỉ giữ tên khóa ở dạng chuỗi; nó không làm các ký tự `[0]` trở nên hợp lệ theo quy tắc khóa Kubernetes.

Nếu cần danh sách đơn giản, có thể dùng chuỗi phân tách bằng dấu phẩy và để Spring Boot bind sang danh sách. Nếu cần danh sách đối tượng hoặc cấu trúc lồng nhau, dùng YAML nhúng để các khóa có chỉ số được tạo ra sau khi ứng dụng đọc nội dung.

### 2.4. Mã định danh nên giữ dưới dạng chuỗi

Giá trị như `00123` có thể là mã khách hàng, không phải số để tính toán. Hãy giữ cả hai điều kiện:

- Manifest hoặc nội dung YAML nhúng biểu diễn giá trị là `"00123"`.
- Thuộc tính Java đích có kiểu `String`.

Chỉ thêm dấu nháy ở YAML nhưng bind sang `Integer` vẫn khiến ứng dụng nhận một con số và mất ý nghĩa về các số 0 ở đầu. Việc lựa chọn kiểu Java phải đi theo ý nghĩa nghiệp vụ.

## 3. Ba lớp biểu diễn trên đường đến ứng dụng

Một ConfigMap đi vào Spring thường trải qua các lớp sau:

~~~mermaid
flowchart LR
    A["Manifest YAML"] --> B["Kubernetes: data chứa chuỗi"]
    B --> C["Đọc khóa trực tiếp hoặc phân tích file nhúng"]
    C --> D["Spring PropertySource và Environment"]
    D --> E["Binder chuyển sang kiểu Java"]
    E --> F["Validation kiểm tra giá trị"]
~~~

Ví dụ với `app.orders.max-items`:

| Lớp | Điều đang tồn tại |
| --- | --- |
| Manifest | Giá trị YAML viết là `"20"` |
| API ConfigMap | Chuỗi `20` |
| Thuộc tính trực tiếp được đưa vào Spring | Giá trị nguồn là chuỗi `20` |
| Truy vấn `Environment` không yêu cầu kiểu | Kết quả là `String` |
| Bind vào `Integer maxItems` | Kết quả là số nguyên `20` |
| Kiểm tra nghiệp vụ | Xác định 20 có nằm trong giới hạn cho phép hay không |

`Environment.getProperty(key)` trả về chuỗi; overload nhận `Class<T>` có thể trả về giá trị đã chuyển sang kiểu đích. Hai lời gọi khác nhau không chứng minh Kubernetes lưu hai kiểu khác nhau. Xem [PropertyResolver của Spring Framework](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/core/env/PropertyResolver.html).

Cũng cần tách hai khái niệm:

- **Chuyển kiểu thành công:** văn bản `20` chuyển được sang `Integer`.
- **Giá trị hợp lệ:** số 20 đáp ứng giới hạn và quy tắc của ứng dụng.

Văn bản `abc` không chuyển được sang số nguyên. Văn bản `-1` có thể chuyển được nhưng vẫn sai nếu ứng dụng yêu cầu số dương.

## 4. Một chuỗi trong `data` có thể chứa cả file YAML

Thay vì nhiều khóa phẳng, có thể lưu một file cấu hình bên trong một giá trị chuỗi:

~~~yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: order-settings
  namespace: cm-types-lab
data:
  order-service.yaml: |-
    app:
      orders:
        enabled: true
        max-items: 20
        timeout: 3s
        tenant-code: "00123"
        allowed-regions:
          - vn-south
          - vn-north
        routing-weights:
          standard: 80
          express: 20
        message: "Đơn hàng đang được xử lý"
        metadata-json: '{"channel":"web","level":2}'
~~~

Đây là **một phương án thay thế** cho ConfigMap ở phần 1. Không cần tạo hai ConfigMap cùng tên để chạy đồng thời.

### 4.1. Có hai lần hiểu YAML với hai mục đích

Lần đầu, công cụ Kubernetes đọc manifest bên ngoài. Nhờ `|-`, giá trị của `data["order-service.yaml"]` là một chuỗi nhiều dòng. Kubernetes không biến các phần `app`, `orders` hay `allowed-regions` bên trong chuỗi thành cấu trúc của tài nguyên ConfigMap.

Lần sau, Spring Cloud Kubernetes nhận diện nội dung như một file YAML và phân tích chuỗi ấy. Khi đó số, boolean, danh sách và mapping bên trong mới tham gia quá trình tạo thuộc tính cho Spring.

Vì thế:

~~~yaml
data:
  enabled: true
~~~

và:

~~~yaml
data:
  order-service.yaml: |-
    enabled: true
~~~

không tương đương về kiểu của giá trị trực tiếp trong `data`. Đoạn đầu có giá trị boolean ở tầng ngoài; đoạn sau có một giá trị chuỗi chứa văn bản YAML.

### 4.2. Cấu trúc lồng nhau được đưa về đường dẫn thuộc tính

Sau khi nội dung được phân tích, có thể hình dung các đường dẫn ứng dụng nhận được là:

~~~text
app.orders.enabled
app.orders.max-items
app.orders.timeout
app.orders.tenant-code
app.orders.allowed-regions[0]
app.orders.allowed-regions[1]
app.orders.routing-weights.standard
app.orders.routing-weights.express
app.orders.message
app.orders.metadata-json
~~~

Các dấu ngoặc vuông ở đây là một phần của đường dẫn thuộc tính tạo ra trong Spring. Chúng không phải các khóa đã được gửi trực tiếp trong `ConfigMap.data`, nên không vi phạm quy tắc khóa ở phần 2.

Ở Spring Cloud Kubernetes 3.3.3, parser YAML có thể giữ các giá trị scalar như số hoặc boolean trong map thuộc tính và làm phẳng danh sách thành đường dẫn có chỉ số. Không nên suy ra rằng mọi giá trị nội bộ của một `PropertySource` đều luôn là `String` chỉ vì dữ liệu đi vào API Kubernetes là chuỗi. Cách xử lý này có trong [ProfileActivationAwareYamlPropertiesFactoryBean tại v3.3.3](https://github.com/spring-cloud/spring-cloud-kubernetes/blob/v3.3.3/spring-cloud-kubernetes-commons/src/main/java/org/springframework/cloud/kubernetes/commons/config/ProfileActivationAwareYamlPropertiesFactoryBean.java).

Đối với mã nghiệp vụ, nên dựa vào hợp đồng kiểu đích của `@ConfigurationProperties` thay vì phụ thuộc lớp Java nội bộ của parser YAML.

### 4.3. Chọn đúng cú pháp chuỗi nhiều dòng

Với file YAML nhúng:

- `|` giữ các dòng; thông thường giữ một ký tự xuống dòng cuối.
- `|-` giữ các dòng và bỏ xuống dòng ở cuối.
- `>` là kiểu gấp dòng, có thể biến các ngắt dòng thành khoảng trắng theo quy tắc YAML.

Nội dung cấu hình có thụt lề và cấu trúc nhiều dòng nên dùng kiểu literal `|` hoặc `|-`. Không đổi sang `>` chỉ để làm manifest ngắn hơn. Quy tắc literal, folded và chomping được mô tả trong [đặc tả YAML 1.2.2](https://yaml.org/spec/1.2.2/#chapter-8-block-style-productions).

Thụt lề của nội dung file phải sâu hơn khóa `order-service.yaml`. Một file YAML bên trong bị lỗi thụt lề vẫn có thể được Kubernetes chấp nhận, vì đối với Kubernetes nó chỉ là chuỗi; lỗi sẽ lộ ra ở bước phân tích trong ứng dụng.

## 5. File properties nhúng cũng là một chuỗi

Một mẫu rút gọn dùng định dạng properties:

~~~yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: order-settings
  namespace: cm-types-lab
data:
  order-service.properties: |-
    app.orders.enabled=true
    app.orders.max-items=20
    app.orders.timeout=3s
    app.orders.tenant-code=00123
    app.orders.allowed-regions=vn-south,vn-north
~~~

Mẫu này chỉ minh họa định dạng, chưa chứa tất cả thuộc tính của ứng dụng đầy đủ ở phần 7.

Định dạng properties dùng quy tắc riêng. Chẳng hạn:

~~~properties
app.orders.max-items=20
~~~

khác với:

~~~properties
app.orders.max-items="20"
~~~

Ở dòng thứ hai, dấu nháy kép thuộc giá trị properties; không mặc nhiên được loại bỏ như dấu nháy bao quanh scalar YAML. Không sao chép nguyên cách thêm dấu nháy của manifest vào nội dung properties rồi kỳ vọng chuyển kiểu vẫn giống nhau.

Đường xử lý properties trong Spring Cloud Kubernetes đi qua `java.util.Properties`, trong khi đường YAML dùng parser riêng; xem [PropertySourceUtils tại v3.3.3](https://github.com/spring-cloud/spring-cloud-kubernetes/blob/v3.3.3/spring-cloud-kubernetes-commons/src/main/java/org/springframework/cloud/kubernetes/commons/config/PropertySourceUtils.java). Với nội dung tiếng Việt hoặc ký tự ngoài ASCII, cần kiểm tra encoding của cả đường đọc; không giả định mọi loader properties và YAML có cùng quy tắc.

Chuỗi chứa JSON cũng không tự trở thành một đối tượng Java chỉ vì có dấu `{` và `}`. Ví dụ `app.orders.metadata-json` vẫn có thể bind vào `String`. Muốn nó trở thành một mô hình JSON, ứng dụng phải chọn và thực hiện bước phân tích phù hợp.

## 6. Nhận diện file nhúng và sự khác nhau giữa tên đối tượng, tên khóa

Giả sử ứng dụng có:

~~~yaml
spring:
  application:
    name: order-service
  config:
    import: "kubernetes:"
  cloud:
    kubernetes:
      config:
        enabled: true
        name: order-settings
        namespace: cm-types-lab
        include-profile-specific-sources: false
        fail-fast: true
        retry:
          enabled: false
      secrets:
        enabled: false
~~~

Ba tên cần phân biệt:

| Thành phần | Giá trị trong ví dụ | Mục đích |
| --- | --- | --- |
| `spring.application.name` | `order-service` | Tên ứng dụng; tham gia quy tắc chọn tên file nhúng |
| `spring.cloud.kubernetes.config.name` | `order-settings` | Tên đối tượng ConfigMap cần tra cứu |
| Khóa trong `data` | `order-service.yaml` | Tên mục dữ liệu chứa nội dung file |

Nếu mount thành volume, khóa `order-service.yaml` còn có thể trở thành tên file. Nếu đọc API bằng Spring Cloud Kubernetes, không cần tạo file vật lý trong container để parser đọc nội dung ấy.

### 6.1. Trường hợp ConfigMap chỉ có một khóa file

Trong Spring Cloud Kubernetes 3.3.3, khi `data` chỉ có đúng một mục và tên khóa kết thúc bằng `.yaml`, `.yml` hoặc `.properties`, mục đó được xử lý như file tương ứng, kể cả tên khác tên ứng dụng.

Ví dụ:

~~~yaml
data:
  custom-settings.yaml: |-
    app:
      orders:
        max-items: 20
~~~

### 6.2. Thêm một khóa có thể làm thay đổi cách nhận diện

Nếu đổi thành:

~~~yaml
data:
  custom-settings.yaml: |-
    app:
      orders:
        max-items: 20
  owner: "training"
~~~

thì `data` không còn chỉ có một mục. Với `spring.application.name=order-service`, không còn được dựa vào ngoại lệ “một file tùy tên” để khẳng định `custom-settings.yaml` sẽ được đọc. Cần dùng tên theo quy tắc, chẳng hạn `order-service.yaml` trong ví dụ này.

Điều kiện số lượng mục và cách lọc tên được thể hiện trong [SourceDataEntriesProcessor tại v3.3.3](https://github.com/spring-cloud/spring-cloud-kubernetes/blob/v3.3.3/spring-cloud-kubernetes-commons/src/main/java/org/springframework/cloud/kubernetes/commons/config/SourceDataEntriesProcessor.java). Đây là hành vi của loader, không phải quy tắc đặt tên do Kubernetes áp đặt.

### 6.3. Tránh khai báo cùng một thuộc tính ở nhiều chỗ trong một ConfigMap

Ví dụ rút gọn:

~~~yaml
data:
  order-service.yaml: |-
    app:
      orders:
        max-items: 20
  app.orders.max-items: "25"
~~~

Theo thứ tự xử lý được mô tả cho Spring Cloud Kubernetes 3.3, thuộc tính trực tiếp có ưu tiên hơn giá trị trùng trong file nhúng; ví dụ này cho giá trị hiệu lực là 25. Không dùng thứ tự dòng nhìn thấy trong manifest để suy luận ghi đè. Xem [quy tắc xử lý ConfigMap PropertySource](https://docs.spring.io/spring-cloud-kubernetes/reference/3.3/property-source-config/configmap-propertysource.html).

Khi học cấu trúc dữ liệu, nên chọn một cách biểu diễn cho cùng một nhóm thuộc tính. Cách này giúp việc xác định nguồn của giá trị đơn giản hơn.

## 7. Từ dữ liệu văn bản đến mô hình Java có kiểu

Với hai phương án đầy đủ ở phần 1 và phần 4, ứng dụng có thể dùng chung một hợp đồng cấu hình.

### 7.1. Dependency và điều kiện mẫu

Dùng Java 17 trở lên, Spring Boot 3.x và Spring Cloud BOM tương thích với Spring Cloud Kubernetes 3.3.3. Các dependency chính trong ví dụ:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-kubernetes-fabric8-config</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
~~~

Đây là đoạn dependency để tích hợp vào dự án đã quản lý phiên bản bằng BOM, không phải file build hoàn chỉnh. Khi chạy trong cluster, Pod cần ServiceAccount có quyền đọc ConfigMap trong namespace `cm-types-lab`. Với đường đọc Fabric8 3.3.3, cần chú ý quyền `list` chứ không chỉ `get` theo tên.

Nếu chọn đọc file đã mount bằng Spring Boot thay vì API, nhu cầu dependency và quyền của ứng dụng sẽ khác. Không cần bật đọc Secret, discovery hoặc theo dõi thay đổi chỉ để học cách bind các giá trị này.

### 7.2. Mô hình cấu hình

~~~java
package example.orders;

import java.time.Duration;
import java.util.List;
import java.util.Map;

import jakarta.validation.constraints.AssertTrue;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.orders")
public record OrderSettings(
        @NotNull Boolean enabled,
        @NotNull @Min(1) @Max(100) Integer maxItems,
        @NotNull Duration timeout,
        @NotBlank String tenantCode,
        @NotEmpty List<@NotBlank String> allowedRegions,
        @NotEmpty Map<String, @Min(0) Integer> routingWeights,
        @NotBlank String message,
        @NotBlank String metadataJson) {

    @AssertTrue(message = "app.orders.timeout must be positive")
    public boolean isTimeoutPositive() {
        return timeout == null
                || (!timeout.isNegative() && !timeout.isZero());
    }
}
~~~

Những lựa chọn đáng chú ý:

- `Boolean` và `Integer` đi cùng `@NotNull` giúp phát hiện thiếu giá trị; tránh để mặc định của primitive che khuất sự vắng mặt.
- `String tenantCode` giữ ý nghĩa của mã `00123`.
- `Duration timeout` thể hiện thời lượng; biểu diễn `3s` ghi rõ đơn vị.
- `List<String>` dành cho vùng được chấp nhận, `Map<String, Integer>` dành cho trọng số theo tên.
- `metadataJson` có kiểu `String`; `@NotBlank` chỉ kiểm tra không trống, không chứng minh chuỗi là JSON hợp lệ.
- `@AssertTrue` kiểm tra thời lượng dương. `@NotNull` chịu trách nhiệm phát hiện thiếu thời lượng.

Spring Boot thực hiện chuyển đổi khi bind `@ConfigurationProperties`, bao gồm định dạng thời lượng có đơn vị; xem [Properties Conversion và Converting Durations](https://docs.spring.io/spring-boot/3.5/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.conversion).

### 7.3. Đăng ký cấu hình và quan sát kiểu trả về

~~~java
package example.orders;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;

@SpringBootApplication
@ConfigurationPropertiesScan
public class OrderApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrderApplication.class, args);
    }

    @Bean
    ApplicationRunner showConfigTypes(
            Environment environment,
            OrderSettings settings) {

        return args -> {
            String text = environment.getRequiredProperty(
                    "app.orders.max-items");
            Integer number = environment.getRequiredProperty(
                    "app.orders.max-items", Integer.class);

            System.out.printf(
                    "text=%s (%s), number=%d (%s)%n",
                    text, text.getClass().getSimpleName(),
                    number, number.getClass().getSimpleName());

            System.out.printf(
                    "tenant=%s, timeout=%s, regions=%s%n",
                    settings.tenantCode(),
                    settings.timeout(),
                    settings.allowedRegions());

            System.out.printf(
                    "metadataJsonType=%s%n",
                    settings.metadataJson().getClass().getSimpleName());
        };
    }
}
~~~

Với dữ liệu đầy đủ của bài và không có nguồn ưu tiên cao hơn ghi đè, kết quả quan sát dự kiến:

~~~text
text=20 (String), number=20 (Integer)
tenant=00123, timeout=PT3S, regions=[vn-south, vn-north]
metadataJsonType=String
~~~

Đây là đầu ra dự kiến để người học đối chiếu, không phải khẳng định rằng Kubernetes lưu `Duration` hoặc `Integer`. Phần chuyển đổi diễn ra trong Spring và kiểu thuộc tính Java.

### 7.4. Bảng đối chiếu kiểu đích

| Biểu diễn đầu vào | Kiểu Java đích | Kết quả dự kiến |
| --- | --- | --- |
| Chuỗi `true` | `Boolean` | `true` |
| Chuỗi `20` | `Integer` | `20` |
| Chuỗi `3s` | `Duration` qua Boot Binder | Thời lượng 3 giây |
| Chuỗi `00123` | `String` | Giữ `00123` |
| Chuỗi phân tách bằng dấu phẩy | `List<String>` qua Boot Binder | Hai phần tử trong ví dụ |
| YAML nhúng có sequence | `List<String>` | Danh sách từ các đường dẫn có chỉ số |
| Các khóa `routing-weights.standard` và `routing-weights.express` | `Map<String, Integer>` | Map với hai khóa và hai số |
| Chuỗi chứa JSON | `String` | Vẫn là văn bản JSON |
| Chuỗi `abc` | `Integer` | Lỗi chuyển kiểu |
| Chuỗi `-1` | `Integer` có `@Min(1)` | Chuyển kiểu được, validation thất bại |

Đối với một cấu trúc phức tạp, ưu tiên YAML nhúng thay cho một chuỗi JSON cần thêm quy trình giải mã riêng, nếu mô hình thuộc tính của ứng dụng đã diễn tả được cấu trúc đó.

## 8. `binaryData` không phải cách khai báo số hoặc boolean

`binaryData` dành cho byte nhị phân, chẳng hạn nội dung không phải UTF-8. Trong manifest JSON/YAML, giá trị nhị phân được biểu diễn bằng Base64. Khóa ở `data` và `binaryData` không được trùng nhau.

Ví dụ có cả hai trường:

~~~yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: auxiliary-config
  namespace: cm-types-lab
data:
  description: "Dữ liệu mẫu"
binaryData:
  sample.bin: "AAECAw=="
~~~

Không chuyển `app.orders.max-items` sang `binaryData` chỉ vì Java muốn một `Integer`. Số lượng mặt hàng vẫn là cấu hình văn bản; Spring chuyển kiểu sau khi đọc.

ConfigMap dành cho dữ liệu không nhạy cảm và có giới hạn dữ liệu 1 MiB. Không dùng Base64 như một cách bảo vệ mật khẩu hay token. Các quy tắc về dữ liệu văn bản, dữ liệu nhị phân, kích thước và phạm vi sử dụng nằm trong [tài liệu ConfigMaps](https://kubernetes.io/docs/concepts/configuration/configmap/).

## 9. Cùng một `data` nhưng cách tiêu thụ khác nhau

### 9.1. Đọc trực tiếp qua API

Spring Cloud Kubernetes đọc ConfigMap rồi đưa thuộc tính vào Spring. Cấu hình ở phần 6 minh họa đường này. Nếu dùng khóa file nhúng, loader phân tích nội dung theo quy tắc nhận diện tương ứng.

Lỗi `Forbidden` ở đây liên quan đến quyền API. Thay đổi `"20"` thành `20` trong manifest không sửa được quyền truy cập, mà còn có thể tạo thêm lỗi schema.

### 9.2. Đưa một khóa vào biến môi trường

Có thể ánh xạ một khóa cụ thể thành biến môi trường của container:

~~~yaml
env:
  - name: APP_ORDERS_MAXITEMS
    valueFrom:
      configMapKeyRef:
        name: order-settings
        key: app.orders.max-items
~~~

Đây là đoạn trích cấu hình container. Kubernetes chọn giá trị của khóa; tên biến môi trường được khai báo riêng. Spring Boot có quy tắc relaxed binding để ánh xạ tên biến môi trường tới thuộc tính ứng dụng.

Một khóa ConfigMap có dấu chấm không tự biến thành tên biến môi trường viết hoa mà ứng dụng mong muốn. Cũng không dùng toàn bộ chuỗi YAML nhúng làm một biến môi trường rồi kỳ vọng nó tự được tách thành mọi thuộc tính con.

### 9.3. Mount thành file

Nếu mount một ConfigMap làm volume, mỗi khóa được ánh xạ thành một file theo cách cấu hình volume. Ví dụ, khóa `order-service.yaml` có thể xuất hiện ở `/etc/order-config/order-service.yaml`. Nội dung file vẫn là chuỗi YAML đã lưu.

Spring Boot có thể đọc file đó bằng:

~~~yaml
spring:
  config:
    import: "file:/etc/order-config/order-service.yaml"
~~~

Việc có file trong container chưa đồng nghĩa Spring tự nạp đúng đường dẫn. Ngược lại, đọc qua API không đòi hỏi phải có file mount tương ứng.

Nếu khóa là `app.orders.max-items`, một lần mount thông thường tạo file mang tên khóa đó; dấu chấm trong tên không tạo cây thư mục `app/orders/max-items`. Cách tiêu thụ qua biến môi trường và volume được minh họa trong [Configure a Pod to Use a ConfigMap](https://kubernetes.io/docs/tasks/configure-pod-container/configure-pod-configmap/).

## 10. Kiểm tra đúng lớp dữ liệu khi thực hành

Các lệnh dưới đây là hướng dẫn cho một môi trường lab của người học. Chúng chỉ có ý nghĩa sau khi namespace, manifest và ứng dụng mẫu đã được chuẩn bị.

### 10.1. Kiểm tra manifest bên ngoài

Với manifest đã lưu thành `order-settings.yaml` trong môi trường thực hành:

~~~shell
kubectl apply --dry-run=server -f order-settings.yaml
~~~

Namespace `cm-types-lab` phải tồn tại và người chạy lệnh phải có quyền phù hợp. Dry-run phía server giúp phát hiện lỗi schema hoặc admission của tài nguyên, nhưng không kiểm tra hộ kiểu Java hay quy tắc nghiệp vụ bên trong ứng dụng.

Đặc biệt, YAML sai bên trong `data["order-service.yaml"]` vẫn có thể đi qua bước này vì nó là một chuỗi hợp lệ đối với schema ConfigMap.

### 10.2. Quan sát dữ liệu API dưới dạng JSON

Sau khi ConfigMap đã được tạo:

~~~shell
kubectl get configmap order-settings --namespace=cm-types-lab -o json
~~~

Với phương án thuộc tính trực tiếp, phần `data` phải thể hiện các giá trị JSON dạng chuỗi. Ví dụ:

~~~json
{
  "app.orders.enabled": "true",
  "app.orders.max-items": "20",
  "app.orders.tenant-code": "00123"
}
~~~

Đây là phần trích dữ liệu, không phải toàn bộ phản hồi API.

Trên PowerShell, có thể quan sát kiểu giá trị sau khi đọc JSON:

~~~powershell
$configMap = kubectl get configmap order-settings --namespace=cm-types-lab -o json | ConvertFrom-Json
$configMap.data.'app.orders.max-items'.GetType().FullName
~~~

Kết quả dự kiến cho phương án thuộc tính trực tiếp là `System.String`.

Với phương án YAML nhúng, thay dòng quan sát bằng:

~~~powershell
$configMap.data.'order-service.yaml'.GetType().FullName
~~~

Kết quả vẫn là `System.String`. API không có các mục `app.orders.allowed-regions[0]` ở tầng `data`; những đường dẫn đó chỉ được tạo trong quá trình phân tích nội dung của ứng dụng.

### 10.3. Đối chiếu lỗi với đúng nơi xử lý

| Hiện tượng | Lớp cần kiểm tra trước | Hướng xử lý |
| --- | --- | --- |
| Manifest bị từ chối vì giá trị không phải chuỗi | YAML ngoài và schema ConfigMap | Biểu diễn số/boolean trực tiếp bằng chuỗi |
| Khóa có `[0]` bị từ chối | Quy tắc tên khóa `data` | Dùng YAML nhúng hoặc chuỗi phù hợp cho Binder |
| Tạo ConfigMap được nhưng ứng dụng lỗi parse YAML | Nội dung file nhúng | Kiểm tra thụt lề, cú pháp và đúng file đang được đọc |
| Không có thuộc tính mong đợi sau khi thêm khóa `owner` | Nhận diện file nhúng | Kiểm tra ngoại lệ một khóa và tên theo ứng dụng |
| Bind `Integer` lỗi với `abc` | Chuyển kiểu của Spring | Sửa giá trị, không sửa schema Kubernetes |
| Giá trị `-1` bị từ chối | Validation của ứng dụng | Sửa giá trị theo ràng buộc nghiệp vụ |
| Mã `00123` bị mất số 0 đầu | Biểu diễn và kiểu đích | Giữ chuỗi qua cả YAML và Java |
| API báo `Forbidden` | ServiceAccount và RBAC | Kiểm tra quyền đọc ConfigMap của Pod |
| Giá trị trong ứng dụng khác ConfigMap vừa xem | Phạm vi đọc và ưu tiên cấu hình | Kiểm tra namespace, tên nguồn, profile và nguồn ghi đè |
| ConfigMap đã thay đổi nhưng bean còn giá trị cũ | Cơ chế cập nhật của ứng dụng | Xác định restart/rollout hoặc refresh phù hợp |

Việc Kubernetes lưu thay đổi không tự chứng minh bean Java đã nhận thay đổi. Configuration Watcher và refresh là một quyết định riêng; không cần thêm chúng để kiểm tra cấu trúc và lần bind ban đầu của bài này.

Khi xác nhận kết quả, quan sát cả giá trị hiệu lực lẫn kiểu đích mà ứng dụng sử dụng. Trạng thái Pod `Running` không đủ để chứng minh rằng ConfigMap đúng tên, đúng nội dung và đã được bind đúng kiểu.

## 11. Chọn cách biểu diễn cho nhóm cấu hình

| Nhu cầu | Cách biểu diễn phù hợp | Điểm cần giữ rõ |
| --- | --- | --- |
| Một vài số, cờ và chuỗi độc lập | Khóa phẳng trong `data` | Mỗi giá trị trực tiếp là chuỗi |
| Danh sách chuỗi đơn giản | Chuỗi phân tách bằng dấu phẩy hoặc YAML nhúng | Biết quy tắc chuyển sang danh sách của ứng dụng |
| Danh sách đối tượng và cấu trúc lồng nhau | Một file YAML nhúng | Cấu trúc ở bên trong chuỗi, không nằm trực tiếp dưới `data` |
| Ứng dụng đã dùng properties | File properties nhúng | Tuân theo dấu nháy, escape và encoding của loader |
| Nội dung phải được đọc nguyên văn | Một giá trị chuỗi hoặc file mount | Không mặc định rằng loader sẽ phân tích cấu trúc bên trong |
| Byte không phải UTF-8 | `binaryData` hoặc cơ chế lưu trữ phù hợp | Không dùng cho việc biểu diễn các scalar thông thường |
| Mật khẩu hoặc token | Secret hoặc hệ thống quản lý bí mật thích hợp | Không lưu thành ConfigMap chỉ vì đã mã hóa Base64 |

Trước khi đưa cấu hình vào triển khai, cần xác định được:

- Kiểu của từng giá trị ngay dưới `data`.
- Khóa nào là thuộc tính trực tiếp, khóa nào là nội dung file cần phân tích.
- Tên đối tượng và namespace mà ứng dụng tra cứu.
- Kiểu Java mong muốn, đơn vị đo và quy tắc cho phép thiếu hoặc rỗng.
- Những nơi có thể ghi đè cùng thuộc tính.
- Cách phát hiện lỗi chuyển kiểu, dữ liệu ngoài miền và cấu hình chưa được nạp.
