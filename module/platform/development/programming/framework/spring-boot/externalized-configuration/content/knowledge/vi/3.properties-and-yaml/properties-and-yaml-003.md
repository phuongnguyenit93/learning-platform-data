# Cấu trúc phân cấp và quy tắc thụt lề trong YAML

YAML (*YAML Ain't Markup Language*) là định dạng dữ liệu dễ đọc, thường được Spring Boot dùng trong `application.yml` hoặc `application.yaml`. Đặc điểm quan trọng nhất của YAML là **cấu trúc được thể hiện bằng thụt lề**: những dòng nằm dưới và thụt vào sâu hơn một khóa sẽ thuộc về khóa đó. Thụt lề sai có thể làm ứng dụng đọc thành một cấu hình khác hoặc khiến file không thể phân tích cú pháp.

Bài học tập trung vào cách viết cấu hình phân cấp đúng, đọc được ý nghĩa của từng mức thụt lề và vận dụng trong Spring Boot 3.3.x với Java 21.

## 1. YAML biểu diễn cấu trúc như thế nào?

Ba kiểu dữ liệu tổ chức thường gặp:

- **Scalar:** một giá trị đơn như chuỗi, số, boolean hoặc `null`.
- **Mapping:** tập cặp `key: value`; gần giống đối tượng hoặc `Map`.
- **Sequence:** danh sách phần tử, thường được đánh dấu bằng `-`.

Ví dụ:

~~~yaml
app:
  name: order-service
  enabled: true
  retry-count: 3
  tags:
    - backend
    - orders
  database:
    host: localhost
    port: 5432
~~~

Trong đoạn trên:

- `app` là mapping cấp cao nhất.
- `name`, `enabled`, `retry-count`, `tags` và `database` cùng cấp, nằm dưới `app` vì thụt vào hai dấu cách.
- `database` tiếp tục chứa `host` và `port` ở cấp sâu hơn.
- `tags` là danh sách gồm hai phần tử, mỗi phần tử bắt đầu bằng dấu `-`.

Có thể hình dung cây cấu hình:

~~~text
app
├── name = "order-service"
├── enabled = true
├── retry-count = 3
├── tags
│   ├── [0] = "backend"
│   └── [1] = "orders"
└── database
    ├── host = "localhost"
    └── port = 5432
~~~

Cách biểu diễn này giúp nhóm các thuộc tính liên quan thay vì viết mọi tên khóa dài lặp đi lặp lại.

## 2. Quy tắc thụt lề: dùng khoảng trắng, không dùng Tab

### 2.1. Mức thụt lề thể hiện quan hệ cha – con

Ví dụ đúng:

~~~yaml
server:
  port: 8081
  servlet:
    context-path: /api
spring:
  application:
    name: config-demo
~~~

Ở đây:

- `server` và `spring` cùng mức cao nhất.
- `port`, `servlet` là khóa con của `server`.
- `context-path` là khóa con của `servlet`.
- `application` là khóa con của `spring`, còn `name` là khóa con của `application`.

Nếu hai khóa cùng thuộc một mapping, hãy căn chúng ở **cùng cột**. Nếu khóa con thuộc một khóa cha, hãy thụt sâu hơn khóa cha.

Một quy ước phổ biến là **hai dấu cách mỗi cấp**. YAML không bắt buộc chính xác hai dấu cách, nhưng thụt lề phải nhất quán để cấu trúc rõ ràng. Với dự án nhiều người cùng sửa, nên thống nhất hai dấu cách để tránh khó đọc hoặc sai cấp.

### 2.2. Không dùng ký tự Tab để thụt lề

Ví dụ **không hợp lệ** nếu dấu thụt đầu dòng là Tab:

~~~text
server:
→port: 8081
~~~

Ký hiệu `→` ở đây minh họa **một ký tự Tab**, không phải nội dung cần nhập trong file. YAML dùng khoảng trắng ở phần thụt lề; Tab để thụt lề sẽ khiến parser báo lỗi. Bật chế độ hiển thị whitespace trong IDE hoặc cấu hình editor chuyển Tab thành spaces.

### 2.3. Cùng cấp phải thẳng hàng

Đúng:

~~~yaml
app:
  database:
    host: db.internal
    port: 5432
    pool-size: 10
~~~

Sai về **ý định cấu trúc**:

~~~yaml
app:
  database:
    host: db.internal
    port: 5432
  pool-size: 10
~~~

Đoạn thứ hai vẫn có thể là YAML hợp lệ, nhưng `pool-size` hiện nằm ở `app.pool-size`, **không** còn ở `app.database.pool-size`. Đây là loại lỗi dễ bỏ sót vì ứng dụng có thể khởi động thành công nhưng không bind đúng thuộc tính mong muốn.

### 2.4. Dòng khóa cha có thể không có giá trị trực tiếp

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info
~~~

`management:` không gán scalar tại chính dòng đó. Những dòng thụt vào sau nó xác định mapping bên dưới. Tương tự, `endpoints:`, `web:`, `exposure:` là các lớp tổ chức, còn `include:` là nơi có giá trị.

Nếu bạn viết:

~~~yaml
app:
  database:
~~~

`database` không chứa các khóa con và được hiểu như giá trị rỗng/null theo cách parser xử lý, không phải một đối tượng database đã được điền cấu hình. Đừng để khóa cha trống khi chương trình cần các thuộc tính cụ thể bên dưới.

## 3. Cú pháp mapping: cặp khóa và giá trị

Mapping được viết với dấu hai chấm, tiếp theo là khoảng trắng rồi đến giá trị:

~~~yaml
app:
  title: "Cấu hình đơn giản"
  timeout-seconds: 30
  enabled: true
  environment: development
~~~

Nên phân biệt:

~~~yaml
# Đúng: dấu ":" ngăn giữa key và value
port: 8080

# Không nên: thiếu khoảng trắng, có thể thành scalar thay vì mapping
port:8080
~~~

Với giá trị scalar có dấu hai chấm, dấu thăng hoặc khoảng trắng đặc biệt, có thể đặt trong dấu nháy:

~~~yaml
app:
  message: "Kết quả: thành công"
  token-placeholder: "abc#123"
  description: "Giữ nguyên dấu : và # trong chuỗi"
~~~

Dấu `#` bên ngoài chuỗi có thể mở đầu comment khi xuất hiện đúng ngữ cảnh cú pháp. Dùng dấu nháy khi muốn tránh việc parser diễn giải dữ liệu dạng đặc biệt. Các URL như `https://example.org/api` thường có thể dùng không cần nháy, nhưng nháy chúng vẫn giúp người đọc phân biệt chuỗi rõ ràng.

Ví dụ comment:

~~~yaml
app:
  # Số lần thử lại mặc định
  retry-count: 3
  active: true # bật chức năng trong môi trường này
~~~

Comment không trở thành thuộc tính khi Spring Boot đọc file.

## 4. Biểu diễn cấu hình phân cấp trong `application.yml`

Giả sử ứng dụng cần một nhóm thuộc tính cho API và một nhóm cho bộ nhớ đệm:

~~~yaml
spring:
  application:
    name: catalog-service

server:
  port: 8085

app:
  api:
    base-url: https://api.example.org
    timeout: 5s
    enabled: true
  cache:
    enabled: false
    ttl: 10m
~~~

Ở mức khái niệm, Spring Boot có thể sử dụng các tên thuộc tính tương ứng:

| Đường dẫn cấu hình | Giá trị |
| --- | --- |
| `spring.application.name` | `catalog-service` |
| `server.port` | `8085` |
| `app.api.base-url` | `https://api.example.org` |
| `app.api.timeout` | `5s` |
| `app.api.enabled` | `true` |
| `app.cache.enabled` | `false` |
| `app.cache.ttl` | `10m` |

Đây chính là lợi ích của cấu trúc phân cấp: thay vì lặp tiền tố `app.api.`, file YAML nhóm các khóa theo cấp. Spring Boot nạp file YAML bằng cơ chế cấu hình, đưa các thuộc tính đã được diễn giải vào `Environment` để đọc hoặc bind.

Viết cấu hình tương đương bằng `application.properties`:

~~~properties
spring.application.name=catalog-service
server.port=8085

app.api.base-url=https://api.example.org
app.api.timeout=5s
app.api.enabled=true
app.cache.enabled=false
app.cache.ttl=10m
~~~

Hai cách biểu diễn có thể cung cấp cùng các thuộc tính cho ứng dụng. YAML phù hợp khi nhiều khóa có chung tiền tố, còn properties thuận tiện khi chỉ có ít khóa.

Không nên giữ cả `application.properties` và `application.yml` cùng chứa một thuộc tính trong một vị trí cấu hình nếu không có chủ đích về thứ tự ưu tiên; rất dễ hiểu nhầm giá trị thực tế đến từ đâu.

## 5. Danh sách (sequence) và mức thụt lề của dấu `-`

### 5.1. Danh sách các scalar

~~~yaml
app:
  allowed-origins:
    - https://app.example.org
    - https://admin.example.org
  supported-locales:
    - vi
    - en
~~~

`allowed-origins` là một danh sách có hai chuỗi, tương tự `supported-locales`. Dấu gạch ngang phải đứng ở vị trí nhất quán giữa các phần tử **cùng danh sách**.

Một dạng viết ngắn cũng hợp lệ:

~~~yaml
app:
  supported-locales: [vi, en]
~~~

Tuy nhiên, dạng nhiều dòng dễ mở rộng hơn và thuận tiện khi có comment cho từng phần tử.

### 5.2. Danh sách các đối tượng

~~~yaml
app:
  endpoints:
    - name: primary
      url: https://primary.example.org
      enabled: true
    - name: fallback
      url: https://fallback.example.org
      enabled: false
~~~

Mỗi dấu `-` bắt đầu một phần tử mapping mới. `name`, `url`, `enabled` thuộc cùng một phần tử khi được căn đúng mức. Phần tử thứ hai bắt đầu tại dấu `-` thứ hai.

Có thể hình dung giá trị:

~~~text
app.endpoints
  [0].name    = primary
  [0].url     = https://primary.example.org
  [0].enabled = true
  [1].name    = fallback
  [1].url     = https://fallback.example.org
  [1].enabled = false
~~~

Trong Spring Boot, các đường dẫn này thường được biểu diễn tương ứng như `app.endpoints[0].name`, `app.endpoints[1].url` khi flatten cấu hình. Khi dùng `@ConfigurationProperties`, chúng có thể bind vào `List<Endpoint>`.

### 5.3. Danh sách bên trong danh sách hoặc đối tượng

~~~yaml
app:
  teams:
    - name: platform
      members:
        - an
        - binh
    - name: backend
      members:
        - chi
~~~

Ở ví dụ trên, mỗi team là một mapping, mỗi mapping lại có danh sách `members`. Mỗi lần đi xuống một cấp danh sách hoặc mapping, hãy quan sát chính xác vị trí dấu `-` và vị trí khóa.

### 5.4. Sai cấp trong danh sách

Ví dụ dễ gây hiểu nhầm:

~~~yaml
app:
  endpoints:
    - name: primary
      url: https://primary.example.org
  enabled: true
~~~

`enabled` ở đây là `app.enabled`, không phải thuộc tính của phần tử `app.endpoints[0]`. Để đặt vào phần tử danh sách, hãy căn nó cùng cột với `url`:

~~~yaml
app:
  endpoints:
    - name: primary
      url: https://primary.example.org
      enabled: true
~~~

Lỗi này thường không tạo thông báo lỗi YAML, nhưng cấu trúc dữ liệu không còn đúng như dự định.

## 6. Mapping lồng nhau, map động và khóa đặc biệt

Ngoài các nhóm thuộc tính cố định, YAML có thể biểu diễn một map có tên khóa động:

~~~yaml
app:
  labels:
    region: southeast-asia
    team: backend
    stage: development
~~~

Có thể bind nhóm `labels` thành `Map<String, String>`. Khi khóa chỉ chứa các ký tự thông dụng, cách viết đơn giản là đủ.

Với những khóa **có ký tự đặc biệt** như dấu gạch chéo hoặc cần giữ nguyên dấu chấm trong tên map key, Spring Boot có quy tắc map binding riêng. Ví dụ:

~~~yaml
app:
  routes:
    "[/internal/health]": "health-route"
    "[api.v1]": "v1-route"
~~~

Dấu ngoặc vuông nằm trong **tên khóa YAML được đặt trong dấu nháy**. Đây là cú pháp bracket notation của Spring Boot để bảo toàn tên key khi bind vào map; không phải một cấp mapping YAML mới. Nếu không cần các key đặc biệt, ưu tiên tên khóa đơn giản để giảm nhầm lẫn.

Nếu thiết lập cùng một mapping key trùng hai lần trong một mapping, cách xử lý có thể phụ thuộc parser và cấu hình kiểm tra; tránh khai báo khóa trùng:

~~~yaml
# Tránh kiểu viết này
app:
  mode: fast
  mode: safe
~~~

Thay vào đó, chỉ giữ một giá trị có chủ đích, hoặc dùng cấu hình theo profile để mô tả biến thể môi trường.

## 7. Bind YAML vào đối tượng Java với `@ConfigurationProperties`

Giả sử `src/main/resources/application.yml` chứa:

~~~yaml
app:
  api:
    base-url: https://api.example.org
    timeout: 5s
    enabled: true
  endpoints:
    - name: primary
      url: https://primary.example.org
    - name: fallback
      url: https://fallback.example.org
  labels:
    region: asia
    team: platform
~~~

Tạo cấu hình dạng record:

~~~java
package com.example.configdemo;

import java.time.Duration;
import java.util.List;
import java.util.Map;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app")
public record AppProperties(
        Api api,
        List<Endpoint> endpoints,
        Map<String, String> labels) {

    public record Api(
            String baseUrl,
            Duration timeout,
            boolean enabled) {
    }

    public record Endpoint(String name, String url) {
    }
}
~~~

Trong lớp main:

~~~java
package com.example.configdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class ConfigDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(ConfigDemoApplication.class, args);
    }
}
~~~

Spring Boot quét `@ConfigurationProperties` và tạo bean `AppProperties`. Khi inject bean này, bạn có thể truy cập:

~~~java
@Component
class ConfigPrinter implements ApplicationRunner {

    private final AppProperties properties;

    ConfigPrinter(AppProperties properties) {
        this.properties = properties;
    }

    @Override
    public void run(ApplicationArguments args) {
        System.out.println(properties.api().baseUrl());
        System.out.println(properties.api().timeout());
        System.out.println(properties.endpoints().get(0).name());
        System.out.println(properties.labels().get("team"));
    }
}
~~~

Import `org.springframework.stereotype.Component`, `org.springframework.boot.ApplicationArguments` và `org.springframework.boot.ApplicationRunner`. Các biểu thức trên cho kết quả tương ứng là:

~~~text
https://api.example.org
PT5S
primary
platform
~~~

`PT5S` là cách `Duration` hiển thị năm giây theo ISO-8601. Spring Boot hỗ trợ bind `5s` sang `java.time.Duration`. Tên YAML `base-url` được bind vào thuộc tính Java `baseUrl` theo cơ chế *relaxed binding*, giúp giữ cách viết YAML dạng kebab-case.

**Quan trọng:** YAML xác định cấu trúc dữ liệu; `@ConfigurationProperties` xác định cách ánh xạ cấu trúc này sang kiểu Java. Nếu thụt lề khiến `api` hoặc `endpoints` rơi sang cấp khác, binder có thể không nhận dữ liệu vào đúng trường.

## 8. Chuỗi có dấu nháy, nhiều dòng và dấu đặc biệt

### 8.1. Giá trị nên có dấu nháy khi cần giữ nguyên kiểu chuỗi

~~~yaml
app:
  build-number: "0012"
  feature-name: "true"
  error-message: "Không thể kết nối: thử lại"
  text-with-hash: "mã #1"
~~~

Không phải scalar nào cũng luôn được parser hiểu là chuỗi. Ví dụ `true` có thể được biểu diễn là boolean; giá trị `"true"` có chủ đích là chuỗi. Với mã định danh có số 0 đầu, dùng dấu nháy để giữ nguyên ý nghĩa chuỗi.

### 8.2. Chuỗi nhiều dòng với `|` và `>`

~~~yaml
app:
  email-template: |
    Xin chào,
    Đơn hàng của bạn đã được ghi nhận.
    Cảm ơn bạn.
  summary: >
    Đây là một đoạn văn dài
    được viết trên nhiều dòng
    để dễ đọc trong YAML.
~~~

- `|` (*literal block scalar*) giữ dấu xuống dòng giữa các dòng nội dung.
- `>` (*folded block scalar*) thường gộp những lần xuống dòng thông thường thành khoảng trắng.
- Nội dung của block scalar phải thụt vào sâu hơn dòng chứa `|` hoặc `>`.

Mặc định dấu xuống dòng ở cuối block còn có quy tắc *chomping*; có thể dùng `|-` hoặc `>-` để loại bỏ dấu xuống dòng cuối nếu ứng dụng cần so khớp chuỗi chính xác.

## 9. Nhiều YAML document trong cùng một file

YAML hỗ trợ phân tách nhiều document bằng dòng `---`. Spring Boot có thể dùng tính năng này để kích hoạt nhóm cấu hình theo profile.

Ví dụ:

~~~yaml
app:
  api:
    timeout: 5s
    base-url: https://api.example.org

---
spring:
  config:
    activate:
      on-profile: dev
app:
  api:
    timeout: 20s
    base-url: http://localhost:8089
~~~

Document đầu cung cấp cấu hình chung. Document thứ hai chỉ được áp dụng khi profile `dev` hoạt động; có thể chạy ứng dụng với `--spring.profiles.active=dev`. Lúc đó, các giá trị `app.api.timeout` và `app.api.base-url` ở document phù hợp sẽ ghi đè cấu hình chung.

`---` phải đứng ở vị trí phân tách document, không thụt vào như khóa con. Đây là cú pháp YAML ở cấp document; không phải giá trị của một key.

Đối với cấu hình theo profile, cũng có thể sử dụng các file riêng như `application-dev.yml`. Chọn cách tổ chức phù hợp quy mô dự án và tránh khai báo lặp khó theo dõi.

## 10. Những lỗi dễ gặp

### Lỗi A: dùng Tab trong indentation

~~~text
app:
→name: demo
~~~

Hãy thay Tab bằng spaces; bật tùy chọn hiển thị khoảng trắng của IDE để nhận ra.

### Lỗi B: một khóa bị đưa ra sai cấp

~~~yaml
# Có thể parse được, nhưng sai ý định
app:
  database:
    host: localhost
  port: 5432
~~~

Nếu mục tiêu là `app.database.port` thì phải thụt `port` vào cùng cấp với `host`.

### Lỗi C: không căn các khóa trong cùng một phần tử list

~~~yaml
# Minh họa cấu trúc sai với yêu cầu mỗi endpoint có url
app:
  endpoints:
    - name: primary
      url: https://one.example.org
    - name: secondary
  url: https://two.example.org
~~~

`url` cuối là `app.url`. Chuyển nó vào dưới `- name: secondary` và căn đúng cột với `name` của phần tử đó.

### Lỗi D: nhầm một chuỗi với một mapping

~~~yaml
# Dễ bị hiểu như chuỗi scalar
server.port:8080

# Nên viết
server:
  port: 8080
~~~

Khi cần dùng khóa phẳng, `server.port: 8080` cũng là cú pháp mapping YAML hợp lệ và được Spring Boot diễn giải thành tên thuộc tính tương ứng; nhưng trong bài cấu trúc phân cấp, dùng dạng nested cho rõ quan hệ.

### Lỗi E: khoảng trắng của chuỗi multiline

~~~yaml
app:
  template: |
    First line
    Second line
~~~

Trong block scalar, các khoảng trắng và xuống dòng có ý nghĩa đối với nội dung. Đừng tự ý thay đổi thụt lề của dòng nội dung hoặc đổi `|` thành `>` nếu chương trình phụ thuộc định dạng chuỗi.

### Lỗi F: coi YAML như phép cộng dồn danh sách ở các nguồn cấu hình

Nếu một danh sách được khai báo lại ở nguồn cấu hình có ưu tiên cao hơn, Spring Boot thường **thay danh sách**, không ghép các phần tử của hai nguồn. Điều này khác với kỳ vọng “thêm một phần tử vào danh sách mặc định”.

Ví dụ chung:

~~~yaml
app:
  servers:
    - main.example.org
    - secondary.example.org
~~~

Nếu cấu hình theo profile ghi đè `app.servers` thành một danh sách mới chỉ có `dev.example.org`, danh sách hiệu lực sẽ là danh sách của profile đang được áp dụng. Để tránh mất phần tử, khai báo toàn bộ tập mục tiêu trong nguồn ghi đè.

## 11. Cách kiểm tra cấu hình hiệu lực

Khi gặp sai lệch giữa giá trị dự kiến và giá trị ứng dụng sử dụng, phân biệt hai trường hợp:

1. **YAML không hợp lệ:** ứng dụng không thể nạp file; thường có thông báo parse error kèm vị trí dòng/cột. Kiểm tra dấu hai chấm, Tab, khoảng trắng và dấu nháy.
2. **YAML hợp lệ nhưng sai cấu trúc:** ứng dụng có thể chạy, nhưng thuộc tính không nằm ở đường dẫn mà chương trình mong đợi. Kiểm tra indentation và mapping path, sau đó kiểm tra nguồn cấu hình đang có hiệu lực.

Có thể quan sát một giá trị bằng `Environment`:

~~~java
@Bean
ApplicationRunner inspect(Environment environment) {
    return args -> {
        System.out.println(environment.getProperty("app.api.base-url"));
        System.out.println(environment.getProperty("app.api.timeout"));
        System.out.println(environment.getProperty("app.endpoints[0].name"));
    };
}
~~~

Imports cần thiết: `org.springframework.boot.ApplicationRunner`, `org.springframework.context.annotation.Bean` và `org.springframework.core.env.Environment`. Đoạn ví dụ này thuộc một lớp `@Configuration` hoặc `@SpringBootApplication`; tùy vào nguồn cấu hình hiệu lực, kết quả có thể thay đổi. Với đối tượng phức tạp, `@ConfigurationProperties` giúp kiểm tra việc bind dễ dàng hơn.

Nếu dự án sử dụng Spring Boot Actuator, endpoint `env` hoặc `configprops` có thể hỗ trợ chẩn đoán khi đã được bật và bảo vệ phù hợp; không nên xuất công khai thông tin cấu hình nhạy cảm.

## 12. Bài tập thực hành

**Bài 1 — Dự đoán đường dẫn thuộc tính.** Cho YAML:

~~~yaml
library:
  name: central
  storage:
    provider: local
    root: /data/books
  categories:
    - java
    - spring
~~~

Hãy xác định giá trị của `library.storage.provider`, `library.storage.root`, `library.categories[1]`. Đáp án: `local`, `/data/books`, `spring`.

**Bài 2 — Sửa indentation.** Mục tiêu là mỗi `worker` có `name` và `concurrency`:

~~~yaml
app:
  workers:
    - name: importer
    concurrency: 2
    - name: exporter
    concurrency: 4
~~~

Hãy sửa thành:

~~~yaml
app:
  workers:
    - name: importer
      concurrency: 2
    - name: exporter
      concurrency: 4
~~~

**Bài 3 — Chuyển properties sang YAML.** Cho:

~~~properties
spring.application.name=payment-demo
server.port=9092
app.job.enabled=true
app.job.interval=30s
~~~

Một cách chuyển tương đương:

~~~yaml
spring:
  application:
    name: payment-demo
server:
  port: 9092
app:
  job:
    enabled: true
    interval: 30s
~~~

**Bài 4 — Thử profile.** Tạo `application.yml` có document chung đặt `app.api.timeout: 5s` và document `dev` đặt `20s`. Chạy ứng dụng một lần không có profile và một lần với `--spring.profiles.active=dev`; quan sát giá trị từ `Environment` hoặc bean cấu hình.

## 13. Ghi nhớ khi viết `application.yml`

- Dùng **spaces**, ưu tiên hai dấu cách mỗi cấp; tuyệt đối tránh Tab cho indentation.
- Cùng cấp thì căn cùng cột; một dòng thụt sâu hơn thuộc cấp cha gần nhất theo cấu trúc YAML.
- `key: value` tạo mapping, `- value` tạo phần tử sequence.
- List của object yêu cầu căn các trường của từng phần tử chính xác.
- Tên đường dẫn như `app.database.host` xuất phát từ cây mapping đã được diễn giải; sai cấp có thể tạo một thuộc tính khác hoàn toàn.
- Dùng dấu nháy khi muốn giữ chuỗi có ký tự đặc biệt hoặc tránh tự động diễn giải kiểu scalar.
- Đọc được YAML hợp lệ chưa đủ: còn phải bảo đảm đúng đường dẫn thuộc tính và kết quả bind trong Spring Boot.

## Tài liệu tham khảo

- [Spring Boot 3.3 — Externalized Configuration: YAML Mapping to Properties](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.files.yaml)
- [Spring Boot 3.3 — Type-safe Configuration Properties](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.typesafe-configuration-properties)
- [YAML 1.2.2 Specification](https://yaml.org/spec/1.2.2/)
