# Truyền cấu hình có cấu trúc qua SPRING_APPLICATION_JSON

> **Chủ đề:** Spring Boot Externalized Configuration  
> **Nhóm:** Biến môi trường

## 1. Bài toán: truyền cả một nhóm thuộc tính chỉ bằng một chuỗi

Một ứng dụng Spring Boot thường nhận cấu hình từ `application.yml`, biến môi trường, Java system properties và tham số dòng lệnh. Khi cần khai báo nhiều khóa liên quan, chẳng hạn endpoint, timeout, danh sách máy chủ và cờ tính năng, việc tạo một biến môi trường riêng cho mỗi khóa có thể trở nên cồng kềnh. Các cấu trúc lồng nhau cũng không phải lúc nào cũng dễ biểu diễn bằng tên biến môi trường của hệ điều hành.

Spring Boot cung cấp một lựa chọn khác: đặt **một JSON object** trong biến môi trường có tên **`SPRING_APPLICATION_JSON`**. Boot phân tích JSON, biến các giá trị lồng nhau thành những property và đưa chúng vào `Environment` như một nguồn cấu hình.

Ví dụ:

~~~bash
export SPRING_APPLICATION_JSON='{"catalog":{"endpoint":"https://catalog.internal","timeout":"5s","features":{"audit":true}}}'
java -jar catalog.jar
~~~

Về mặt ý nghĩa, ứng dụng nhận được những khóa:

~~~properties
catalog.endpoint=https://catalog.internal
catalog.timeout=5s
catalog.features.audit=true
~~~

Đoạn `.properties` trên là hình dung về các khóa được tạo ra, **không phải** một tệp mà bạn phải tự sinh. Các giá trị trong JSON được đưa vào cơ chế externalized configuration thông thường của Spring Boot.

### Sau bài học, bạn có thể

- Viết JSON object hợp lệ để cung cấp cấu hình lồng nhau từ một biến môi trường.
- Giải thích cách một nhánh JSON như `catalog.features.audit` trở thành property có thể đọc qua `Environment` hoặc `@ConfigurationProperties`.
- Truyền JSON trên Linux/macOS, Windows PowerShell, Docker và Kubernetes mà không nhầm giữa quoting của shell và cú pháp JSON.
- Xác định độ ưu tiên của `SPRING_APPLICATION_JSON` so với `application.yml`, biến môi trường thường, Java system properties và command-line arguments.
- Hiểu hành vi của mảng, map, giá trị `null` và chuyển kiểu dữ liệu.
- Chẩn đoán lỗi JSON, lỗi binding, lỗi override và lựa chọn cách cung cấp dữ liệu nhạy cảm.

## 2. Cơ chế hoạt động

### 2.1. JSON là phương tiện truyền, không phải tên một property nghiệp vụ

Có hai lớp cần phân biệt:

1. Biến môi trường `SPRING_APPLICATION_JSON` chứa một **chuỗi JSON hợp lệ**.
2. Spring Boot đọc chuỗi đó, phân tích đối tượng JSON và công bố các khóa bên trong thành properties.

Ví dụ giá trị biến môi trường:

~~~json
{
  "gateway": {
    "endpoint": "https://api.internal",
    "connect-timeout": "2s",
    "retry": {
      "max-attempts": 4,
      "enabled": true
    }
  }
}
~~~

Các property logic gồm:

| Đường dẫn trong JSON | Property của Spring | Giá trị |
| --- | --- | --- |
| `gateway.endpoint` | `gateway.endpoint` | `https://api.internal` |
| `gateway.connect-timeout` | `gateway.connect-timeout` | `2s` |
| `gateway.retry.max-attempts` | `gateway.retry.max-attempts` | số `4` |
| `gateway.retry.enabled` | `gateway.retry.enabled` | boolean `true` |

Spring có cơ chế chuyển kiểu khi bind hoặc yêu cầu một loại dữ liệu cụ thể. JSON cung cấp dữ liệu gốc, còn `Environment` và `Binder` giải quyết cách lấy giá trị phù hợp với Java code.

Ví dụ:

~~~java
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Service;

@Service
public class GatewayOptionsReader {
    private final Environment environment;

    public GatewayOptionsReader(Environment environment) {
        this.environment = environment;
    }

    public String endpoint() {
        return environment.getRequiredProperty("gateway.endpoint");
    }

    public Boolean retryEnabled() {
        return environment.getRequiredProperty(
                "gateway.retry.enabled", Boolean.class);
    }

    public Integer maxAttempts() {
        return environment.getRequiredProperty(
                "gateway.retry.max-attempts", Integer.class);
    }
}
~~~

Không cần gọi một JSON parser trong service để đọc lại biến môi trường. Spring Boot đã đăng ký các thuộc tính từ JSON vào `Environment`.

### 2.2. Cấu trúc lồng nhau được ánh xạ theo đường dẫn

JSON:

~~~json
{
  "service": {
    "http": {
      "host": "0.0.0.0",
      "port": 8088
    },
    "limits": {
      "requests-per-minute": 120
    }
  }
}
~~~

tương ứng với các khóa như:

~~~text
service.http.host
service.http.port
service.limits.requests-per-minute
~~~

Nhánh object lồng nhau giúp tổ chức cấu hình theo miền nghiệp vụ, còn tên khóa vẫn có thể truy cập bằng dấu chấm. Tên key thường nên dùng dạng **kebab-case** cho `@ConfigurationProperties`, ví dụ `requests-per-minute`, vì đây là quy ước dễ thống nhất với Spring Boot relaxed binding.

Một JSON object không tạo ra Java bean tự động. Bean cấu hình được tạo khi ứng dụng có `@ConfigurationProperties` và đã đăng ký hoặc bật cơ chế scan/enable tương ứng.

### 2.3. Có thể biểu diễn cả scalar, boolean, số và mảng

JSON cho phép:

~~~json
{
  "demo": {
    "name": "demo-service",
    "enabled": true,
    "attempts": 3,
    "ratio": 0.25,
    "regions": ["ap-southeast-1", "ap-northeast-1"]
  }
}
~~~

Khác biệt cần nhớ:

- `"3"` là JSON string; `3` là JSON number.
- `"true"` là JSON string; `true` là JSON boolean.
- Mảng `[...]` đại diện cho các phần tử có chỉ số và có thể bind vào list/array Java.
- `null` có ngữ nghĩa đặc biệt trong Spring Boot; không nên dùng như một cách xóa property ưu tiên thấp.
- Một trường `"limits": {"x": 1}` là object lồng nhau; nó khác với chuỗi `"limits": "{\"x\":1}"` chứa JSON được escape bên trong một string.

## 3. Ví dụ hoàn chỉnh: cấu hình client có cấu trúc

Giả sử ứng dụng có cấu hình mặc định trong `application.yml`:

~~~yaml
catalog:
  client:
    endpoint: "https://default.example"
    connect-timeout: 3s
    retry-count: 2
    enabled: false
    regions:
      - local
    labels:
      source: "file"
      team: "backend"
~~~

Trong một lần triển khai, ta muốn thay đổi bằng JSON:

~~~json
{
  "catalog": {
    "client": {
      "endpoint": "https://catalog.internal",
      "connect-timeout": "1500ms",
      "retry-count": 5,
      "enabled": true,
      "regions": ["sg", "jp"],
      "labels": {
        "source": "json",
        "environment": "staging"
      }
    }
  }
}
~~~

Khi truyền JSON dưới `SPRING_APPLICATION_JSON`, những thuộc tính ở nguồn JSON có thể ghi đè các khóa trùng từ `application.yml`.

### 3.1. Bind vào `@ConfigurationProperties`

Ví dụ với Spring Boot 3 và Java 17+:

~~~java
package com.example.catalog;

import java.net.URI;
import java.time.Duration;
import java.util.List;
import java.util.Map;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "catalog.client")
public record CatalogClientProperties(
        URI endpoint,
        Duration connectTimeout,
        int retryCount,
        boolean enabled,
        List<String> regions,
        Map<String, String> labels
) {}
~~~

Kích hoạt scanning:

~~~java
package com.example.catalog;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class CatalogApplication {
    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }
}
~~~

Một service có thể inject trực tiếp:

~~~java
import org.springframework.stereotype.Service;

@Service
public class CatalogService {
    private final CatalogClientProperties properties;

    public CatalogService(CatalogClientProperties properties) {
        this.properties = properties;
    }

    public String describe() {
        return properties.endpoint() + " / "
                + properties.connectTimeout()
                + " / retry=" + properties.retryCount();
    }
}
~~~

Các giá trị `"1500ms"`, số `5` và boolean `true` được Spring Boot chuyển sang `Duration`, `int` và `boolean` tương ứng trong quá trình binding. Nếu nội dung không thể chuyển kiểu, ứng dụng có thể báo lỗi bind khi khởi tạo cấu hình.

### 3.2. Kết quả của ví dụ

Giả sử không có một nguồn ưu tiên cao hơn JSON ghi đè các key đang xét:

| Trường | Giá trị ban đầu trong YAML | Giá trị sau khi áp dụng JSON |
| --- | --- | --- |
| `endpoint` | `https://default.example` | `https://catalog.internal` |
| `connectTimeout` | `3s` | `1500ms` |
| `retryCount` | `2` | `5` |
| `enabled` | `false` | `true` |
| `regions` | `[local]` | `[sg, jp]` |
| `labels.source` | `file` | `json` |
| `labels.team` | `backend` | `backend` |
| `labels.environment` | chưa có | `staging` |

Với `@ConfigurationProperties`, các thuộc tính map có thể được kết hợp theo khóa, trong khi list thường được **thay thế** bởi list từ nguồn ưu tiên cao, thay vì nối tất cả phần tử. Không áp dụng quy tắc nối chung cho mọi collection.

## 4. Truyền bằng biến môi trường trên các nền tảng

### 4.1. Linux và macOS (Bash hoặc shell tương thích)

Đặt JSON trong cặp **nháy đơn của shell** giúp giữ nguyên dấu nháy kép của JSON:

~~~bash
export SPRING_APPLICATION_JSON='{"catalog":{"client":{"endpoint":"https://catalog.internal","retry-count":5,"enabled":true}}}'
java -jar catalog.jar
~~~

Hoặc chỉ áp dụng cho một lần chạy:

~~~bash
SPRING_APPLICATION_JSON='{"catalog":{"client":{"retry-count":5}}}' \
java -jar catalog.jar
~~~

Dấu `'...'` trong shell là lớp quoting bên ngoài; nội dung thật mà Spring Boot nhận được vẫn là JSON bắt đầu bằng `{` và kết thúc bằng `}`. Không gửi cặp nháy đơn shell thành một phần của giá trị biến.

Với JSON lớn, có thể dùng công cụ tạo JSON để tránh lỗi dấu nháy, sau đó truyền kết quả qua biến môi trường của tiến trình. Khi làm như vậy, hãy lưu ý giới hạn kích thước biến môi trường và khả năng dữ liệu xuất hiện trong môi trường thực thi/diagnostics.

### 4.2. Windows PowerShell

Trong PowerShell:

~~~powershell
$env:SPRING_APPLICATION_JSON = '{"catalog":{"client":{"endpoint":"https://catalog.internal","enabled":true}}}'
java -jar catalog.jar
~~~

Cú pháp gán environment variable khác Bash nhưng giá trị JSON được truyền cho Boot vẫn có cấu trúc như nhau. Biến `$env:SPRING_APPLICATION_JSON` chỉ ảnh hưởng tới môi trường của phiên PowerShell hiện tại và các tiến trình con được khởi động từ đó; nó không đồng nghĩa đã thay đổi biến môi trường ở cấp máy cho mọi phiên chạy.

Nếu ứng dụng được khởi chạy bằng IDE hoặc service manager, cần đặt biến môi trường **ở đúng tiến trình khởi động**, không chỉ ở một terminal không liên quan.

### 4.3. Docker

Ví dụ chạy image minh họa:

~~~bash
docker run --rm \
  -e SPRING_APPLICATION_JSON='{"catalog":{"client":{"endpoint":"https://catalog.internal","enabled":true}}}' \
  example/catalog:1.0
~~~

Image trên chỉ là ví dụ. Docker đặt biến môi trường trong container; Spring Boot đọc biến đó khi tiến trình Java bắt đầu.

Với ứng dụng thực, có thể khai báo environment variable trong cấu hình container/deployment. Nếu chuỗi JSON chứa dữ liệu nhạy cảm, cần cân nhắc vì biến môi trường hoặc thông số triển khai có thể bị quan sát qua một số công cụ quản trị.

### 4.4. Kubernetes

Trong Pod template của Deployment, có thể truyền JSON từ phần `env`:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: catalog
spec:
  replicas: 1
  selector:
    matchLabels:
      app: catalog
  template:
    metadata:
      labels:
        app: catalog
    spec:
      containers:
        - name: catalog
          image: example/catalog:1.0
          env:
            - name: SPRING_APPLICATION_JSON
              value: '{"catalog":{"client":{"endpoint":"https://catalog.internal","retry-count":5,"enabled":true}}}'
~~~

YAML `value` là **một string chứa JSON**. Kubernetes không tự chuyển nội dung này thành các biến riêng. Spring Boot của container nhận `SPRING_APPLICATION_JSON` rồi xử lý JSON.

Đối với cấu hình nhiều dòng hoặc có thay đổi riêng theo môi trường, bạn cũng có thể quản lý chuỗi JSON trong ConfigMap (nếu không nhạy cảm) hoặc sử dụng phương thức quản lý secret thích hợp và tham chiếu đến đó. Một ConfigMap khai báo JSON không tự được nạp nếu không mount/truyền tới ứng dụng theo cấu hình triển khai.

### 4.5. Đặt JSON bằng Java system property hoặc command-line argument

Ngoài tên biến môi trường `SPRING_APPLICATION_JSON`, Spring Boot cũng có thể xử lý JSON thông qua system property tên `spring.application.json`:

~~~bash
java -Dspring.application.json='{"catalog":{"client":{"enabled":true}}}' \
  -jar catalog.jar
~~~

Với command-line option:

~~~bash
java -jar catalog.jar \
  --spring.application.json='{"catalog":{"client":{"enabled":true}}}'
~~~

Các câu lệnh dùng cú pháp quoting của shell kiểu Unix; Windows cmd và PowerShell có quy tắc khác. Dù JSON được truyền qua các kênh khác nhau, nội dung được phân tích thành nguồn JSON của Spring Boot.

Cần phân biệt hai tên:

- `SPRING_APPLICATION_JSON`: tên biến môi trường phù hợp với môi trường của tiến trình.
- `spring.application.json`: tên property ở dạng dotted notation, có thể dùng với Java system properties hoặc command-line arguments.

Cũng cần phân biệt **phương tiện cấp JSON** với các **thuộc tính bên trong JSON**: ví dụ `--spring.application.json=...` tạo nguồn cho `catalog.client.enabled`, nhưng không có nghĩa khóa nghiệp vụ phải bắt đầu bằng `spring.application.json.`.

## 5. Cú pháp JSON chính xác: lỗi phổ biến

### 5.1. JSON bắt buộc có cú pháp chuẩn

Ví dụ hợp lệ:

~~~json
{
  "app": {
    "name": "orders",
    "enabled": true,
    "port": 8080,
    "servers": ["a.internal", "b.internal"]
  }
}
~~~

Các lỗi thường gặp:

| Cú pháp | Vấn đề |
| --- | --- |
| `{app: {enabled: true}}` | JSON yêu cầu tên key trong nháy kép |
| `{'app': {'enabled': true}}` | JSON chuẩn không dùng nháy đơn cho tên key/string |
| `{"app":{"enabled":True}}` | Boolean JSON là `true` / `false` viết thường |
| `{"app":{"count":3,}}` | Dấu phẩy thừa cuối object không hợp lệ |
| `{"app":{"port":8080} // comment}` | JSON chuẩn không hỗ trợ comment |
| `{"app":{"timeout":5s}}` | `5s` phải là string, ví dụ `"5s"` |

JSON không phải YAML hay JavaScript object literal. Nên dùng một trình kiểm tra JSON hoặc thư viện JSON trong công cụ tạo cấu hình khi có nhiều dấu ngoặc và chuỗi escape.

### 5.2. Quoting của shell và escaping trong JSON là hai lớp khác nhau

Giả sử giá trị chứa dấu nháy kép:

~~~json
{
  "app": {
    "message": "He said \"hello\""
  }
}
~~~

Dấu `\"` bên trong chuỗi JSON là escaping **của JSON**. Bao toàn bộ JSON trong nháy đơn của Bash hoặc PowerShell giúp shell không bỏ mất dấu nháy kép. Khi truyền qua YAML manifest hoặc ứng dụng CI/CD, có thêm lớp encoding của định dạng trung gian; cần bảo đảm cuối cùng biến môi trường chứa JSON chuẩn, không có phần quote dư ngoài object.

### 5.3. JSON string được truyền qua môi trường, không phải file path

Nếu gán:

~~~bash
export SPRING_APPLICATION_JSON=/etc/catalog/settings.json
~~~

Spring Boot sẽ không mặc định coi đây là đường dẫn file để đọc; nó cố diễn giải giá trị theo cơ chế JSON. Muốn nạp một tài liệu cấu hình từ file, hãy dùng các vị trí config data và `spring.config.import` thích hợp, chẳng hạn YAML/properties hoặc loại loader được hỗ trợ.

Tương tự, việc có một file tên `settings.json` trên ổ đĩa không tự khiến Boot nạp file đó dưới dạng `SPRING_APPLICATION_JSON`. Cơ chế nhận JSON qua environment variable khác với tìm kiếm file cấu hình mặc định.

## 6. Thứ tự ưu tiên: khi JSON và các nguồn khác trùng khóa

### 6.1. JSON thường có ưu tiên cao hơn system properties và OS environment

Trong Spring Boot externalized configuration mặc định, một số nguồn được sắp theo thứ tự **cao đến thấp** như sau (bỏ qua nguồn dùng riêng cho test và một số tình huống đặc biệt):

| Thứ tự tương đối | Nguồn |
| --- | --- |
| Cao hơn | Command-line arguments, ví dụ `--app.mode=from-cli` |
| Tiếp theo | Các thuộc tính được phân tích từ `SPRING_APPLICATION_JSON` / `spring.application.json` |
| Sau đó | ServletConfig/ServletContext init params và JNDI nếu có trong môi trường Servlet |
| Sau đó | Java system properties, ví dụ `-Dapp.mode=from-jvm` |
| Sau đó | Biến môi trường thông thường, ví dụ `APP_MODE=from-env` |
| Thấp hơn | Config data như `application.yml` / `application.properties` (tùy vị trí và profile) |
| Thấp hơn nữa | `@PropertySource` và default properties |

Đây là **thứ tự tra cứu nguồn cấu hình**, không phải thứ tự những dòng nằm trong file. Application code có thể thay đổi thứ tự bằng custom property sources, hoặc loại bỏ command-line properties, nên kết quả chính xác cần xét runtime thực tế.

### 6.2. Ví dụ ghi đè qua nhiều lớp

`application.yml`:

~~~yaml
app:
  mode: "from-file"
  region: "local"
~~~

Biến môi trường:

~~~bash
export APP_MODE=from-env
export SPRING_APPLICATION_JSON='{"app":{"mode":"from-json","region":"cluster"}}'
~~~

Và chạy:

~~~bash
java -jar catalog.jar --app.mode=from-cli
~~~

Kết quả thường là:

~~~text
app.mode   = from-cli
app.region = cluster
~~~

Giải thích: với `app.mode`, command-line argument thắng JSON; với `app.region`, JSON thắng giá trị từ file vì không có nguồn cao hơn ghi đè.

Nếu bỏ `--app.mode=from-cli`, giá trị `app.mode` là `from-json` vì JSON có ưu tiên cao hơn biến môi trường `APP_MODE`.

### 6.3. Khi một key có mặt trong JSON nhưng giá trị là null

Ví dụ:

~~~yaml
# application.yml
app:
  name: "catalog"
~~~

Và JSON:

~~~json
{
  "app": {
    "name": null
  }
}
~~~

Không nên kỳ vọng `null` của JSON sẽ xóa hoặc ghi đè `app.name` từ nguồn ưu tiên thấp. Trong cơ chế property resolution của Spring Boot, JSON `null` được đưa vào dưới dạng missing value, nên nguồn thấp hơn vẫn có thể cung cấp giá trị. Ở ví dụ này, `app.name` vẫn có thể là `catalog`.

Nếu muốn chủ động vô hiệu hóa một hành vi, thiết kế thuộc tính rõ ràng như `app.enabled=false` thay vì dùng `null` để biểu thị “xóa giá trị của các nguồn dưới”.

### 6.4. Mảng và map khi có nhiều nguồn

Giả sử `application.yml` khai báo:

~~~yaml
app:
  servers:
    - "default-a"
    - "default-b"
  labels:
    team: "core"
    region: "local"
~~~

JSON:

~~~json
{
  "app": {
    "servers": ["json-a"],
    "labels": {
      "region": "apac",
      "source": "json"
    }
  }
}
~~~

Với `@ConfigurationProperties` thông thường:

- List `app.servers` từ nguồn ưu tiên cao thường **thay thế toàn bộ list**, nên nhận `[json-a]` thay vì nối `[default-a, default-b, json-a]`.
- Map `app.labels` có thể được kết hợp theo từng entry: `team=core` từ file, `region=apac` từ JSON, `source=json` từ JSON.

Binding của các kiểu phức tạp có các quy tắc riêng; không nên suy từ precedence của scalar rằng tất cả cấu trúc đều deep merge.

## 7. Cấu hình lồng nhau và tên property trong Java

### 7.1. Dùng `@Value` cho vài khóa

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class CatalogFlags {
    private final boolean auditEnabled;

    public CatalogFlags(
            @Value("${catalog.features.audit:false}")
            boolean auditEnabled) {
        this.auditEnabled = auditEnabled;
    }

    public boolean auditEnabled() {
        return auditEnabled;
    }
}
~~~

Biểu thức `:false` cung cấp fallback khi không có property. Dữ liệu JSON có thể tham gia vào cùng cơ chế placeholder resolution với các nguồn khác. Tuy vậy, với nhiều khóa liên quan hoặc cấu hình chứa list/map, `@ConfigurationProperties` thường dễ quản lý và kiểm tra hơn.

### 7.2. Dùng `@ConfigurationProperties` cho nhóm nhiều khóa

Ví dụ:

~~~json
{
  "worker": {
    "pool": {
      "enabled": true,
      "size": 8,
      "shutdown-timeout": "10s"
    }
  }
}
~~~

Record:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "worker.pool")
public record WorkerPoolProperties(
        boolean enabled,
        int size,
        Duration shutdownTimeout
) {}
~~~

Sau khi bean được đăng ký qua `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties`, Spring Boot bind các property thành các field tương ứng. Giá trị `"10s"` dùng Spring conversion để thành `Duration`.

Khi cần kiểm soát hợp lệ, thêm các ràng buộc như kích thước pool phải dương, timeout không âm; các constraint có thể được triển khai qua Bean Validation khi dependency và annotation phù hợp đã được cấu hình.

### 7.3. Tên key và relaxed binding

Spring Boot khuyến nghị canonical property names ở dạng kebab-case, chẳng hạn:

~~~text
worker.pool.shutdown-timeout
~~~

Một Java field `shutdownTimeout` có thể bind từ key đó. Với JSON, đặt các key theo dạng kebab-case ngay từ nguồn giúp nhất quán giữa `application.yml`, system properties và JSON. Không coi khác biệt viết hoa hoặc dấu gạch dưới của environment variables là lý do để đặt mọi key JSON theo quy tắc tên biến môi trường.

## 8. JSON giúp giải quyết cấu hình khó biểu diễn bằng biến môi trường thường

Một khó khăn của environment variables là tên biến thường chỉ chấp nhận các ký tự như chữ, số và dấu gạch dưới, đồng thời các hệ thống có quy tắc chuyển chữ hoa/chữ thường khác nhau. Vì vậy, một số property có dấu chấm, key của map hoặc tên package có thể khó giữ nguyên ý nghĩa.

Ví dụ cấu hình mức log cho package:

~~~json
{
  "logging": {
    "level": {
      "com.example.catalog": "DEBUG",
      "org.springframework.web": "WARN"
    }
  }
}
~~~

Có thể truyền qua:

~~~bash
export SPRING_APPLICATION_JSON='{"logging":{"level":{"com.example.catalog":"DEBUG","org.springframework.web":"WARN"}}}'
java -jar catalog.jar
~~~

Những khóa log có dấu chấm được truyền qua JSON object keys mà không cần mã hóa toàn bộ dấu chấm vào tên biến môi trường. Với các logging level theo package hoặc tên class nhạy chữ hoa/chữ thường, JSON là một lựa chọn dễ biểu diễn hơn biến môi trường chuẩn. Ứng dụng vẫn cần dùng đúng tên property và cấu hình logging được hỗ trợ ở phiên bản Spring Boot hiện hành.

**Không phải JSON nào cũng phải lồng theo từng segment của tên property.** Ví dụ một key JSON đã có dấu chấm như `"com.example.catalog"` có thể được giữ trong đường dẫn property khi Spring flatten cấu trúc. Chọn cách đặt key phù hợp với binding hoặc tính năng Boot đang dùng.

## 9. Hạn chế và lựa chọn thay thế

### 9.1. Dùng một JSON lớn có thể khó bảo trì

Một JSON nhỏ rất tiện cho việc truyền một nhóm cấu hình. Nhưng khi tăng đến hàng trăm key, sẽ khó theo dõi khác biệt giữa các môi trường, khó sửa bằng tay và khó tránh lỗi cú pháp. Những lựa chọn thường phù hợp hơn khi cấu hình lớn:

- `application.yml` ngoài JAR, được nạp qua cơ chế config data.
- `spring.config.import` để nhập file cấu hình bổ sung.
- `configtree:` khi hệ thống triển khai cung cấp mỗi khóa dưới dạng một file.
- ConfigMap hoặc một giải pháp quản lý cấu hình tập trung phù hợp hạ tầng.

Chọn phương án theo nhu cầu triển khai: cần override vài khóa bằng một biến môi trường hay cần quản lý nhiều file, profile, kiểm soát thay đổi và cấu hình nhạy cảm.

### 9.2. Giới hạn kích thước và tính quan sát được

Biến môi trường và command-line arguments chịu giới hạn của hệ điều hành, shell, container runtime và hệ thống quản lý triển khai. Một JSON quá lớn có thể vượt giới hạn, khó debug hoặc bị cắt/escape sai khi qua pipeline. Không dựa vào một kích thước tối đa chung cho mọi môi trường.

Command-line arguments có thể xuất hiện trong các công cụ xem danh sách tiến trình, CI logs hoặc hệ thống giám sát. Biến môi trường cũng có thể lộ qua cấu hình triển khai, process diagnostics hoặc tài khoản có quyền thích hợp. Vì vậy, **không mặc định đặt password hoặc private key trực tiếp trong JSON** chỉ vì JSON được truyền qua môi trường. Với bí mật quan trọng, xem xét secret manager, file mount với quyền truy cập giới hạn, `configtree:` hoặc cơ chế được nền tảng hỗ trợ.

### 9.3. Sự thay đổi giá trị sau khi ứng dụng khởi động

Spring Boot phân tích cấu hình khi ứng dụng khởi tạo. Đổi giá trị biến môi trường ở shell khác, thay manifest Kubernetes hoặc sửa ConfigMap không có nghĩa các bean cấu hình của tiến trình Java đang chạy sẽ tự cập nhật. Thông thường cần restart/rollout hoặc một cơ chế refresh được thiết kế riêng.

### 9.4. JSON không thay thế profile và config data

`SPRING_APPLICATION_JSON` góp một property source ưu tiên tương đối cao; nó không biến các object con thành những tài liệu YAML có điều kiện `spring.config.activate.on-profile`. Khi cần tổ chức cấu hình theo profile, file `application-{profile}.yml`, multi-document YAML hoặc các cơ chế config data khác vẫn có vai trò riêng.

Bạn có thể truyền một property chọn profile qua nguồn cấu hình thích hợp nếu nền tảng và giai đoạn khởi động cho phép, nhưng không nên tự coi mỗi nhánh JSON là một document có activation giống multi-document YAML.

## 10. Chẩn đoán khi JSON không có hiệu lực

### 10.1. Quy trình chẩn đoán

1. **Xác định đúng tiến trình Java.** Biến `SPRING_APPLICATION_JSON` có được đặt ở môi trường của tiến trình đang chạy, không chỉ trong một terminal khác?
2. **Xác nhận JSON hợp lệ.** Kiểm tra dấu nháy kép, dấu phẩy, escaping, kiểu dữ liệu, và không để thêm dấu quote shell vào nội dung JSON.
3. **Kiểm tra tên khóa.** Ví dụ `"catalog":{"client":{"enabled":true}}` tương ứng `catalog.client.enabled`; đừng đọc nhầm `catalog.enabled`.
4. **Kiểm tra nguồn ưu tiên cao hơn.** Tham số `--catalog.client.enabled=false` có thể thắng JSON.
5. **Kiểm tra binding.** Giá trị `"five"` không thể chuyển thành `int` trong một bean có `retryCount` là số.
6. **Kiểm tra cấu trúc collection.** List có thể bị thay thế thay vì nối từ các nguồn.
7. **Kiểm tra trạng thái khởi động.** Ứng dụng đã được restart sau khi thay environment/deployment config chưa?
8. **Không in secrets khi điều tra.** Chỉ dùng khóa demo để thử cơ chế precedence.

### 10.2. Quan sát một khóa không nhạy cảm tại runtime

~~~java
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.stereotype.Component;

@Component
public class JsonConfigProbe implements ApplicationRunner {

    private final ConfigurableEnvironment environment;

    public JsonConfigProbe(ConfigurableEnvironment environment) {
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        String key = "catalog.client.retry-count";

        System.out.println("Resolved " + key + " = "
                + environment.getProperty(key));

        environment.getPropertySources().forEach(source -> {
            Object value = source.getProperty(key);
            if (value != null) {
                System.out.println(source.getName() + " -> " + value);
            }
        });
    }
}
~~~

Nếu JSON đang đóng góp một giá trị, nguồn JSON thường xuất hiện trong danh sách `PropertySource` mà `ConfigurableEnvironment` cung cấp. Tên cụ thể của nguồn có thể phụ thuộc phiên bản Spring Boot; không dựa vào một tên string cố định để viết logic nghiệp vụ.

Có thể dùng Spring Boot Actuator `env` và `configprops` để hỗ trợ tra cứu khi endpoint được bảo vệ và cấu hình cơ chế che giấu các giá trị nhạy cảm. Không hiển thị trực tiếp mọi môi trường hoặc thông tin bí mật trong endpoint công khai.

### 10.3. Các triệu chứng thường gặp

| Triệu chứng | Điều cần kiểm tra |
| --- | --- |
| Ứng dụng báo lỗi phân tích JSON | Quote của shell/YAML, dấu phẩy thừa, thiếu dấu ngoặc, key không có dấu nháy kép |
| `Environment.getProperty(...)` trả null | Sai key lồng nhau, biến chưa tới tiến trình, nguồn JSON không được nạp |
| Giá trị vẫn theo CLI dù JSON khác | Command-line property có precedence cao hơn |
| Giá trị vẫn từ `application.yml` | JSON không có key đó, JSON key là `null`, hoặc nguồn JSON chưa được nạp |
| `@ConfigurationProperties` bind lỗi | Sai kiểu số, boolean, duration, URI hoặc collection |
| List bị mất các phần tử từ file mặc định | Binding list của nguồn ưu tiên cao thay thế list ưu tiên thấp |
| Chạy trong terminal đúng, chạy trên Kubernetes sai | Manifest/env source khác, quoting YAML khác, chưa rollout image/pod mới |
| Một secret xuất hiện trong log | Công cụ chẩn đoán, startup script hoặc logging đang in raw env/args |

## 11. Thực hành từng bước

### Bài tập A: từ YAML mặc định sang JSON override

Tạo `application.yml`:

~~~yaml
lesson:
  title: "Default lesson"
  enabled: false
  retries: 1
  timeout: 2s
~~~

Chạy:

~~~bash
export SPRING_APPLICATION_JSON='{"lesson":{"title":"Environment lesson","enabled":true,"retries":3,"timeout":"6s"}}'
java -jar lesson.jar
~~~

Tạo một bean đọc `lesson.title`, `lesson.enabled` và `lesson.retries`. Nếu không có nguồn ưu tiên cao hơn, kết quả mong đợi lần lượt là `Environment lesson`, `true` và `3`. `lesson.timeout` có thể bind thành `Duration` 6 giây.

### Bài tập B: xem precedence với CLI

Giữ biến JSON của bài tập A, chạy:

~~~bash
java -jar lesson.jar --lesson.retries=9
~~~

Khi ứng dụng có command-line properties mặc định, `lesson.retries` từ CLI thắng giá trị `3` trong JSON. Nếu bỏ CLI, giá trị JSON thắng bản YAML.

### Bài tập C: đối tượng lồng nhau

Truyền:

~~~json
{
  "lesson": {
    "cache": {
      "enabled": true,
      "ttl": "30s"
    }
  }
}
~~~

Tạo `@ConfigurationProperties(prefix = "lesson.cache")` có hai field `boolean enabled` và `Duration ttl`. Dự đoán kết quả khi JSON được cấp đúng môi trường và khi không được cấp.

### Bài tập D: mảng và map

Trong `application.yml` có:

~~~yaml
lesson:
  regions: ["local", "backup"]
  labels:
    owner: "learning"
    stage: "default"
~~~

JSON:

~~~json
{
  "lesson": {
    "regions": ["apac"],
    "labels": {
      "stage": "staging",
      "source": "json"
    }
  }
}
~~~

Bind `regions` vào `List<String>` và `labels` vào `Map<String,String>`. Kiểm tra danh sách vùng có một phần tử `apac` và map có thể giữ `owner`, cập nhật `stage` và thêm `source`.

### Bài tập E: JSON null

Đặt trong `application.yml`:

~~~properties
lesson.greeting=Hello
~~~

Sau đó truyền:

~~~json
{
  "lesson": {
    "greeting": null
  }
}
~~~

Đọc `lesson.greeting`. Nếu giá trị vẫn là `Hello`, điều đó phản ánh `null` không được dùng để ghi đè xóa property từ nguồn thấp trong cơ chế lookup của Spring Boot. Thay bằng một chuỗi cụ thể, ví dụ `"Hi"`, rồi quan sát precedence.

### Bài tập F: thực hành Docker

Khởi động cùng một image hai lần: lần đầu không cấp `SPRING_APPLICATION_JSON`, lần sau đặt biến này thành JSON có `lesson.retries=4`. Đối chiếu với giá trị trong `application.yml`. Khi dùng Kubernetes, thử sửa `env.value` rồi rollout lại để thấy rằng tiến trình mới mới nhận cấu hình tương ứng.

## 12. Những nhầm lẫn cần tránh

**“`SPRING_APPLICATION_JSON` chỉ là một property tên `spring.application.json`.”** Đây là kênh truyền JSON; Spring Boot phân tích object bên trong và công bố những property nghiệp vụ như `lesson.timeout`, `catalog.endpoint`.

**“Truyền JSON giúp mọi thứ cao ưu tiên nhất.”** Command-line properties vẫn thường có precedence cao hơn nguồn JSON; test property sources hoặc cấu hình tùy chỉnh có thể thay đổi bức tranh này.

**“JSON null dùng để xóa giá trị cũ.”** Không nên dựa vào giả định đó; trong property resolution của Spring Boot, JSON null được xem là thiếu giá trị và có thể rơi về nguồn thấp hơn.

**“Hai list ở hai nguồn tự nối nhau.”** Với binding list của Spring Boot, nguồn ưu tiên cao thường thay thế list của nguồn dưới.

**“Chỉ cần tên biến có chữ JSON thì nội dung kiểu YAML cũng chạy.”** Giá trị `SPRING_APPLICATION_JSON` cần là chuỗi JSON hợp lệ, không phải YAML hoặc object literal JavaScript.

**“Gán biến môi trường ở terminal hiện tại là đủ cho mọi kiểu triển khai.”** Tiến trình Java do IDE, Docker, Kubernetes hoặc service manager khởi động phải thực sự nhận được biến môi trường.

**“Có thể đặt mọi secret trong JSON vì nó không nằm trong Git.”** Biến môi trường và tham số dòng lệnh vẫn có các bề mặt quan sát riêng; cần chọn kênh quản lý secret có kiểm soát.

## 13. Ghi nhớ

- `SPRING_APPLICATION_JSON` cho phép truyền **một JSON object có cấu trúc** qua biến môi trường. Spring Boot flatten các nhánh thành property keys có thể được đọc từ `Environment` và bind bằng `@ConfigurationProperties`.
- JSON object cho phép lồng nhau, boolean, số, mảng; cần cú pháp JSON chính xác và shell quoting phù hợp.
- JSON properties thường có ưu tiên **cao hơn** config data, OS environment variables và Java system properties; command-line application arguments thường **cao hơn** JSON.
- `null` trong JSON không phải thao tác xóa property từ các nguồn thấp hơn. List, map và scalar có semantics binding khác nhau.
- Có thể cung cấp JSON qua environment variable `SPRING_APPLICATION_JSON`, system property `spring.application.json` hoặc command-line option `--spring.application.json=...`.
- Với cấu hình lớn hoặc dữ liệu nhạy cảm, cân nhắc file config data, config tree/secret mount và quản lý vòng đời cấu hình phù hợp.

## Tài liệu tham khảo

- [Spring Boot Reference — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html): thứ tự ưu tiên các nguồn, JSON application properties và cách đọc cấu hình.
- [Spring Boot Reference — JSON Application Properties](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.application-json): `SPRING_APPLICATION_JSON`, `spring.application.json` và cách Spring Boot xử lý `null`.
- [Spring Boot Reference — Type-safe Configuration Properties](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties): binding object lồng nhau, collection và relaxed binding.
- [Spring Boot Reference — Working With Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.java-bean-binding): ví dụ cấu hình có cấu trúc qua `@ConfigurationProperties`.
