# Chỉ số danh sách trong tên biến môi trường

## 1. Vì sao chỉ số danh sách cần một cú pháp riêng?

Spring Boot hỗ trợ **externalized configuration**: cùng một ứng dụng có thể lấy cấu hình từ **application.yml**, **application.properties**, biến môi trường, system properties hoặc tham số khởi động. Khi cấu hình chỉ có giá trị đơn như **server.port**, cách đặt biến môi trường tương đối dễ nhớ:

~~~text
server.port       -> SERVER_PORT
app.service-url   -> APP_SERVICEURL
~~~

Nhưng nếu cấu hình chứa một **danh sách** thì sao? Trong file YAML, chúng ta thường khai báo nhiều phần tử bằng dấu gạch đầu dòng. Trong file **.properties**, phần tử thường có chỉ số trong ngoặc vuông như **app.targets[0].url**. Biến môi trường của hệ điều hành lại thường chỉ chấp nhận chữ, số và dấu gạch dưới; ký tự **[**, **]**, dấu chấm **.** và gạch ngang **-** không phù hợp cho cách đặt tên biến môi trường thông thường.

Vì vậy, **Spring Boot relaxed binding** đưa ra một quy tắc riêng:

> Khi bind một **List** từ biến môi trường, số thứ tự của phần tử được đặt giữa các dấu gạch dưới.

Ví dụ chính:

~~~text
Property:         app.targets[0].url
Environment var:  APP_TARGETS_0_URL

Property:         app.targets[1].url
Environment var:  APP_TARGETS_1_URL
~~~

Con số **0**, **1** là **chỉ số phần tử trong danh sách**, bắt đầu từ 0, không phải một đoạn tên property bình thường. Việc giữ dấu gạch dưới trước và sau chỉ số giúp bộ **Binder** xác định ranh giới giữa tên danh sách, phần tử và trường bên trong phần tử.

## 2. Quy tắc chuyển từ property sang biến môi trường

Với tên property ở dạng chuẩn (*canonical name*, thường viết chữ thường và dùng dấu gạch ngang cho từ ghép), Spring Boot hướng dẫn:

1. Thay dấu chấm **.** giữa các phần tên bằng dấu gạch dưới **_**.
2. **Bỏ** dấu gạch ngang **-** bên trong tên property.
3. Chuyển các chữ cái thành **CHỮ HOA**.
4. Nếu là phần tử **List**, chuyển chỉ số **[n]** thành **_n_** ở vị trí thích hợp.

Ví dụ:

| Tên property | Biến môi trường tương ứng |
| --- | --- |
| **app.name** | **APP_NAME** |
| **app.service-url** | **APP_SERVICEURL** |
| **app.targets[0]** | **APP_TARGETS_0** |
| **app.targets[0].name** | **APP_TARGETS_0_NAME** |
| **app.targets[0].url** | **APP_TARGETS_0_URL** |
| **app.targets[1].url** | **APP_TARGETS_1_URL** |
| **app.service-pool[2].connect-timeout** | **APP_SERVICEPOOL_2_CONNECTTIMEOUT** |
| **my.service[0].other** | **MY_SERVICE_0_OTHER** |
| **app.regions[3]** | **APP_REGIONS_3** |

Hãy chú ý hai dạng dễ nhầm:

~~~text
app.service-pool[2].connect-timeout
  -> APP_SERVICEPOOL_2_CONNECTTIMEOUT
~~~

Dấu gạch ngang trong **service-pool** và **connect-timeout** được **loại bỏ**, còn các dấu gạch dưới được dùng để phân cách **cấp property** và **chỉ số**.

**APP_SERVICE_POOL_2_CONNECT_TIMEOUT** nhìn có vẻ dễ đọc nhưng không phải phép chuyển đổi chuẩn từ hai segment **service-pool** và **connect-timeout** theo quy tắc trên. Nếu biến môi trường không bind như dự kiến, kiểm tra trước tiên xem có đang chèn thêm dấu gạch dưới vào giữa một tên kebab-case hay không.

### 2.1. Dấu _ trước và sau số không phải cú pháp [0]

Tên **APP_TARGETS_0_URL** biểu diễn:

~~~text
APP         -> app
TARGETS     -> targets
0           -> [0], phần tử đầu tiên
URL         -> url, trường của phần tử đầu tiên
~~~

Với phần tử cuối của một danh sách scalar, chẳng hạn **app.regions[0]**, tên biến kết thúc bằng số:

~~~text
app.regions[0]  -> APP_REGIONS_0
app.regions[1]  -> APP_REGIONS_1
~~~

Không cần thêm dấu gạch dưới ở cuối biến vì không còn trường tiếp theo. Cách nói “chỉ số được bao bởi dấu gạch dưới” có nghĩa là số phải được phân tách khỏi các segment lân cận; ở cuối tên biến không cần sinh một segment rỗng.

### 2.2. Danh sách lồng nhau

Ví dụ một danh sách nhóm, mỗi nhóm có danh sách máy chủ:

~~~text
app.groups[0].servers[1].host
  -> APP_GROUPS_0_SERVERS_1_HOST
~~~

Mỗi phần tử danh sách có chỉ số riêng. Bộ Binder lần lượt đọc **groups[0]**, rồi **servers[1]**, rồi trường **host**.

Ở ứng dụng thực tế, nếu cấu trúc trở nên quá nhiều cấp, hãy cân nhắc tách cấu hình thành những nhóm dễ quản lý. Dù vậy, quy tắc chuyển tên vẫn nhất quán.

## 3. Cùng một danh sách trong YAML, properties và biến môi trường

Giả sử ứng dụng định nghĩa hai endpoint dự phòng.

**application.yml**:

~~~yaml
app:
  targets:
    - name: primary
      url: https://primary.example.invalid
    - name: backup
      url: https://backup.example.invalid
~~~

Spring Boot chuyển cấu trúc YAML thành các đường property tương đương:

~~~properties
app.targets[0].name=primary
app.targets[0].url=https://primary.example.invalid
app.targets[1].name=backup
app.targets[1].url=https://backup.example.invalid
~~~

Nếu cần cung cấp **cùng danh sách** qua biến môi trường, dùng:

~~~text
APP_TARGETS_0_NAME=primary
APP_TARGETS_0_URL=https://primary.example.invalid
APP_TARGETS_1_NAME=backup
APP_TARGETS_1_URL=https://backup.example.invalid
~~~

Bảng đối chiếu:

| Phần tử | YAML | .properties | Environment |
| --- | --- | --- | --- |
| Tên của phần tử 0 | **targets[0].name** | **app.targets[0].name** | **APP_TARGETS_0_NAME** |
| URL của phần tử 0 | **targets[0].url** | **app.targets[0].url** | **APP_TARGETS_0_URL** |
| Tên của phần tử 1 | **targets[1].name** | **app.targets[1].name** | **APP_TARGETS_1_NAME** |
| URL của phần tử 1 | **targets[1].url** | **app.targets[1].url** | **APP_TARGETS_1_URL** |

Ở cột YAML, **targets[0].name** là đường tham chiếu tương đối dưới nhánh **app** đang hiển thị; đường property đầy đủ vẫn là **app.targets[0].name**.

Các giá trị **.invalid** chỉ để minh họa. Chúng không phải endpoint thật và không yêu cầu kết nối mạng để quan sát cấu hình.

## 4. Ví dụ Java: bind vào List bằng @ConfigurationProperties

**@ConfigurationProperties** là cách được Spring Boot hỗ trợ để ánh xạ cấu hình có cấu trúc sang một đối tượng Java. Nó phù hợp với danh sách các đối tượng hơn việc viết hàng loạt **@Value** theo từng chỉ số.

Giả sử ứng dụng dùng Java 21, Spring Boot 3.3.x và **spring-boot-starter-web**.

### 4.1. Đăng ký quét @ConfigurationProperties

~~~java
package com.example.listenv;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class ListEnvApplication {
    public static void main(String[] args) {
        SpringApplication.run(ListEnvApplication.class, args);
    }
}
~~~

### 4.2. Khai báo kiểu cấu hình

~~~java
package com.example.listenv;

import java.util.List;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app")
public record AppProperties(List<Target> targets) {

    public record Target(String name, String url) {
    }
}
~~~

**Giải thích:**

- **prefix = "app"** yêu cầu bind các key thuộc nhánh **app**.
- **targets** ánh xạ tới một **List<Target>**.
- Mỗi **Target** có hai thuộc tính **name** và **url**.
- Spring Boot hỗ trợ constructor binding với kiểu **record** thông qua configuration property scanning trong trường hợp này.
- Biến **APP_TARGETS_0_NAME** cung cấp trường **name** của phần tử đầu tiên, còn **APP_TARGETS_1_URL** cung cấp trường **url** của phần tử thứ hai.

Nếu dự án dùng class JavaBean thông thường thay record, các getter/setter và cấu hình bind phù hợp cũng có thể được sử dụng. Trọng tâm là binder nhận được một **List**, nên nó có thể diễn giải chỉ số được biểu diễn trong tên biến môi trường.

### 4.3. Một endpoint để quan sát kết quả

~~~java
package com.example.listenv;

import java.util.List;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class TargetController {

    private final AppProperties properties;

    public TargetController(AppProperties properties) {
        this.properties = properties;
    }

    @GetMapping("/targets")
    public List<AppProperties.Target> targets() {
        return properties.targets();
    }
}
~~~

**src/main/resources/application.yml**:

~~~yaml
server:
  port: 8080

app:
  targets:
    - name: built-in-primary
      url: https://built-in-primary.example.invalid
    - name: built-in-backup
      url: https://built-in-backup.example.invalid
~~~

Khi chạy mà không có biến môi trường ghi đè, gọi:

~~~bash
curl http://localhost:8080/targets
~~~

Kết quả minh họa:

~~~json
[
  {
    "name": "built-in-primary",
    "url": "https://built-in-primary.example.invalid"
  },
  {
    "name": "built-in-backup",
    "url": "https://built-in-backup.example.invalid"
  }
]
~~~

Đây là dữ liệu của YAML, được bind qua **@ConfigurationProperties** và trả về qua controller.

Trong ứng dụng thật, không nên xây dựng một API công khai để hiển thị các property nhạy cảm. Ví dụ dùng endpoint đơn giản chỉ với tên và URL giả để người học quan sát kết quả.

## 5. Thay toàn bộ List bằng biến môi trường

Build ứng dụng một lần với Gradle wrapper:

~~~bash
./gradlew bootJar
~~~

Giả sử artifact được đặt tên **app.jar**; nếu Gradle sinh tên khác, thay bằng tên JAR thực tế.

### 5.1. Linux/macOS: cấp biến cho một tiến trình Java

~~~bash
APP_TARGETS_0_NAME=prod-primary \
APP_TARGETS_0_URL=https://prod-primary.example.invalid \
APP_TARGETS_1_NAME=prod-backup \
APP_TARGETS_1_URL=https://prod-backup.example.invalid \
java -jar app.jar
~~~

Sau khi ứng dụng chạy, gọi:

~~~bash
curl http://localhost:8080/targets
~~~

Kết quả minh họa:

~~~json
[
  {
    "name": "prod-primary",
    "url": "https://prod-primary.example.invalid"
  },
  {
    "name": "prod-backup",
    "url": "https://prod-backup.example.invalid"
  }
]
~~~

Lệnh này cấp biến môi trường chỉ cho tiến trình Java được khởi chạy trong ví dụ shell. Nó không sửa YAML trong JAR và không yêu cầu build lại.

### 5.2. PowerShell: cấp biến cho phiên shell

~~~powershell
$env:APP_TARGETS_0_NAME = "local-primary"
$env:APP_TARGETS_0_URL = "https://local-primary.example.invalid"
$env:APP_TARGETS_1_NAME = "local-backup"
$env:APP_TARGETS_1_URL = "https://local-backup.example.invalid"

java -jar app.jar
~~~

PowerShell cho phép gán giá trị dạng chuỗi cho các biến có tên chứa chữ, số và dấu gạch dưới. Những biến này có mặt trong môi trường của tiến trình Java khởi chạy từ shell ấy.

Nếu muốn kiểm tra trường hợp **không có** biến môi trường ghi đè ở lượt chạy sau, hãy gỡ các biến đã đặt hoặc mở shell mới. Nếu không, Spring Boot có thể tiếp tục đọc những giá trị cũ.

### 5.3. Docker: mỗi phần tử là một biến -e

~~~bash
docker run --rm -p 8080:8080 \
  -e APP_TARGETS_0_NAME=container-primary \
  -e APP_TARGETS_0_URL=https://container-primary.example.invalid \
  -e APP_TARGETS_1_NAME=container-backup \
  -e APP_TARGETS_1_URL=https://container-backup.example.invalid \
  my-list-env:1.0.0
~~~

Ví dụ giả định image **my-list-env:1.0.0** đã được tạo từ ứng dụng trên và chạy Java process đọc cấu hình Spring Boot. Thứ tự các tùy chọn **-e** trong lệnh Docker không quyết định thứ tự danh sách; chỉ số **_0_**, **_1_** trong **tên biến** mới quyết định.

## 6. Danh sách scalar: List<String> còn đơn giản hơn

Không phải danh sách nào cũng chứa object. Ví dụ ứng dụng cần danh sách region:

**application.yml**:

~~~yaml
app:
  regions:
    - asia
    - europe
    - america
~~~

Các property tương đương:

~~~properties
app.regions[0]=asia
app.regions[1]=europe
app.regions[2]=america
~~~

Biến môi trường:

~~~text
APP_REGIONS_0=asia
APP_REGIONS_1=europe
APP_REGIONS_2=america
~~~

**Không có _REGION_ ở cuối** vì chính phần tử danh sách là giá trị, không phải một object có trường con.

Kiểu Java:

~~~java
package com.example.listenv;

import java.util.List;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app")
public record RegionProperties(List<String> regions) {
}
~~~

Lưu ý khi sử dụng đoạn ví dụ độc lập này cùng **AppProperties** trước đó: cả hai class đều dùng prefix **app** nhưng chỉ bind những trường được khai báo trong từng record. Để xây dựng một ứng dụng đầy đủ, có thể gom các trường vào một configuration record hoặc đặt prefix riêng cho từng nhóm tùy nhu cầu.

### 6.1. Danh sách có nhiều kiểu giá trị

Spring Boot còn bind các kiểu dữ liệu như số nguyên, boolean, duration, enum hoặc những object lồng nhau theo cơ chế **ConversionService** phù hợp.

Ví dụ:

~~~yaml
app:
  retry-delays:
    - 1s
    - 5s
    - 30s
~~~

Các tên biến môi trường tương ứng là:

~~~text
APP_RETRYDELAYS_0=1s
APP_RETRYDELAYS_1=5s
APP_RETRYDELAYS_2=30s
~~~

Kiểu Java có thể là **List<Duration>** nếu cấu hình được bind qua **@ConfigurationProperties** và giá trị duration được Spring Boot chuyển đổi. Những chuỗi **1s**, **5s**, **30s** là giá trị có đơn vị, không phải một phần tên biến môi trường.

## 7. Thứ tự phần tử dựa trên chỉ số, không dựa trên thứ tự khai báo

Giả sử hệ thống triển khai cấp các biến theo thứ tự khác nhau:

~~~text
APP_TARGETS_1_NAME=backup
APP_TARGETS_0_NAME=primary
APP_TARGETS_1_URL=https://backup.example.invalid
APP_TARGETS_0_URL=https://primary.example.invalid
~~~

Danh sách được bind theo **chỉ số**:

~~~text
targets[0] -> primary
targets[1] -> backup
~~~

Không nên suy ra thứ tự danh sách từ thứ tự dòng trong file khai báo biến môi trường hoặc thứ tự cặp **-e** trong Docker. Nguồn biến môi trường có thể là map không bảo đảm thứ tự.

**Chỉ số bắt đầu từ 0**:

- **_0_** biểu diễn phần tử đầu tiên.
- **_1_** biểu diễn phần tử thứ hai.
- **_2_** biểu diễn phần tử thứ ba.

Nên dùng các chỉ số **liên tiếp**, tránh bắt đầu ở **_1_** rồi bỏ **_0_**. Một danh sách có khoảng trống chỉ số, ví dụ có phần tử 0 và 2 nhưng không có 1, có thể không bind đúng thành một **List** liên tục. Hãy cung cấp đủ phần tử và đủ trường cần thiết của mỗi object.

## 8. Danh sách ở nhiều nguồn cấu hình: thay thế, không ghép từng phần tử

Đây là một quy tắc dễ gây lỗi và rất quan trọng khi dùng biến môi trường.

Giả sử **application.yml** có:

~~~yaml
app:
  targets:
    - name: default-primary
      url: https://default-primary.example.invalid
    - name: default-backup
      url: https://default-backup.example.invalid
~~~

Khi chạy, môi trường triển khai chỉ cấp:

~~~text
APP_TARGETS_0_NAME=production-primary
APP_TARGETS_0_URL=https://production-primary.example.invalid
~~~

Nhiều người mong danh sách cuối cùng sẽ là:

~~~text
[0] production-primary (từ môi trường)
[1] default-backup    (từ YAML)
~~~

Nhưng với **List** trong hệ thống binding của Spring Boot, khi danh sách được cấu hình trong nhiều nguồn khác nhau, **nguồn ưu tiên cao hơn thay thế danh sách của nguồn thấp hơn**. Nó không thực hiện phép merge từng phần tử để tự giữ **targets[1]** trong YAML.

Trong ví dụ trên, kết quả bind mong đợi chỉ còn phần tử **targets[0]** từ nguồn môi trường. **targets[1]** của YAML không được nối vào danh sách mới.

Nếu mỗi object có nhiều trường, cần lưu ý thêm: không nên mong Spring Boot tự dùng **name** từ nguồn môi trường rồi lấy **url** tương ứng từ YAML cho cùng phần tử list. Danh sách từ nguồn ưu tiên cao hơn có thể chứa những trường còn thiếu giá trị; nếu có validation hoặc code yêu cầu trường bắt buộc, việc bind hoặc khởi động có thể không đạt yêu cầu.

### 8.1. Cách cấp cấu hình đầy đủ khi override List

Khi thay danh sách cho môi trường triển khai, nên cấp **toàn bộ phần tử dự kiến**:

~~~text
APP_TARGETS_0_NAME=prod-primary
APP_TARGETS_0_URL=https://prod-primary.example.invalid
APP_TARGETS_1_NAME=prod-backup
APP_TARGETS_1_URL=https://prod-backup.example.invalid
~~~

Nếu thực sự chỉ muốn có một target trong production, chỉ cấp phần tử 0 cũng là một yêu cầu hợp lệ, nhưng phải hiểu đó là **thay toàn danh sách**.

### 8.2. Khi nào Map phù hợp hơn List?

Nếu các mục có **khóa định danh ổn định** và nhu cầu chính là ghi đè từng mục mà giữ các mục khác, **Map** có thể phù hợp hơn **List**. Spring Boot có quy tắc merge cho **Map** từ nhiều nguồn cấu hình; cùng một key map lấy giá trị theo ưu tiên của nguồn.

Ví dụ muốn quản lý các endpoint theo tên **primary** và **backup**:

~~~yaml
app:
  targets-by-name:
    primary:
      url: https://primary.example.invalid
    backup:
      url: https://backup.example.invalid
~~~

Khi khai báo model Java tương ứng là **Map<String, Target>**, ý nghĩa cấu hình là **map theo tên**, không còn phụ thuộc vị trí [0], [1]. Đây là một quyết định thiết kế khác; không chuyển List sang Map chỉ để sửa tên biến môi trường nếu thứ tự phần tử có ý nghĩa nghiệp vụ.

**Quy tắc về thay thế List áp dụng giữa các nguồn PropertySource**, không chỉ giữa hai file YAML. Vì vậy biến môi trường cũng phải được xem như một nguồn có thể thay thế cả danh sách đã khai báo trong Config Data.

## 9. Vì sao nên dùng @ConfigurationProperties thay cho nhiều @Value?

Có thể đọc một giá trị đơn giản qua **Environment.getProperty(...)** hoặc **@Value**, nhưng với danh sách object, **@ConfigurationProperties** mang lại cơ chế bind có cấu trúc và hỗ trợ chuyển đổi kiểu, nested properties, collection.

Ví dụ cấu hình:

~~~text
APP_TARGETS_0_NAME=alpha
APP_TARGETS_0_URL=https://alpha.example.invalid
APP_TARGETS_1_NAME=beta
APP_TARGETS_1_URL=https://beta.example.invalid
~~~

Với record:

~~~java
@ConfigurationProperties(prefix = "app")
public record AppProperties(List<Target> targets) {
    public record Target(String name, String url) {
    }
}
~~~

Binder có thể gom những biến môi trường thuộc cùng prefix thành hai object **Target** trong một danh sách.

Nếu cố đọc từng key bằng **@Value**, code phải biết trước có bao nhiêu phần tử và tự xử lý cả trường hợp một phần tử bị thiếu. Cách đó làm mất lợi ích của việc bind collection động.

Để có cơ chế bind trên, cần đăng ký lớp **@ConfigurationProperties** bằng **@ConfigurationPropertiesScan** hoặc **@EnableConfigurationProperties(...)**. Chỉ thêm annotation lên record nhưng không đăng ký bean cấu hình thì controller có thể không nhận được đối tượng cần tiêm.

### 9.1. Prefix có chữ ghép

Khi dùng:

~~~java
@ConfigurationProperties(prefix = "client-config")
public record ClientConfigProperties(List<Client> clients) {
    public record Client(String baseUrl) {
    }
}
~~~

Key canonical phù hợp là:

~~~text
client-config.clients[0].base-url
~~~

Tên môi trường theo quy tắc relaxed binding:

~~~text
CLIENTCONFIG_CLIENTS_0_BASEURL
~~~

Không phải:

~~~text
CLIENT_CONFIG_CLIENTS_0_BASE_URL
~~~

Chính vì vậy, khi làm việc với property tên dài, nên viết ra đường canonical trước, áp dụng tuần tự bốn bước chuyển tên, rồi mới khai báo biến trên hệ thống triển khai.

## 10. Phân biệt List với Map khi tên khóa có số

Đôi khi một **Map** có key là chuỗi **"0"** hoặc **"1"**, ví dụ:

~~~yaml
app:
  labels:
    "0": zero
    "1": one
~~~

Về mặt ý nghĩa, **labels** là **Map**, còn **targets** ở các ví dụ trước là **List**. Một con số trong tên biến không tự biến mọi dữ liệu thành danh sách; **kiểu đích của @ConfigurationProperties** quyết định cách binder diễn giải cấu hình.

Đặc biệt, Spring Boot chuyển tên key từ biến môi trường về chữ thường khi bind **Map**, điều này đáng chú ý nếu Map có các khóa phân biệt chữ hoa/chữ thường.

Với danh sách, hãy dùng rõ kiểu **List<T>** và chỉ số **[n]** trong file cấu hình. Không dựa vào tên biến để cố mô phỏng key của Map hoặc ngược lại.

Nếu muốn danh sách có thứ tự, **List** cùng chỉ số là lựa chọn tự nhiên. Nếu muốn tra cứu theo tên và override từng khóa, hãy cân nhắc **Map**.

## 11. Cách khai báo trong Docker Compose

Đối với một service Spring Boot chạy trong Docker Compose, có thể truyền các biến như sau:

~~~yaml
services:
  api:
    image: my-list-env:1.0.0
    ports:
      - "8080:8080"
    environment:
      APP_TARGETS_0_NAME: "compose-primary"
      APP_TARGETS_0_URL: "https://compose-primary.example.invalid"
      APP_TARGETS_1_NAME: "compose-backup"
      APP_TARGETS_1_URL: "https://compose-backup.example.invalid"
~~~

Trong ví dụ trên, **environment** là một map YAML của Docker Compose. Các key được chuyển thành biến môi trường trong container; Spring Boot mới thực hiện relaxed binding từ các biến đó sang **AppProperties.targets**.

Đừng viết:

~~~yaml
environment:
  app.targets[0].name: compose-primary
~~~

và mặc nhiên coi đó là cách khai báo chuẩn có thể dùng được trong mọi shell hay nền tảng. Dạng chữ hoa có dấu gạch dưới **APP_TARGETS_0_NAME** là cách được Spring Boot hướng dẫn và phù hợp hơn khi ứng dụng được chuyển qua nhiều công cụ triển khai.

Tương tự, nếu dùng file **.env**, cách khai báo quen thuộc là:

~~~dotenv
APP_TARGETS_0_NAME=compose-primary
APP_TARGETS_0_URL=https://compose-primary.example.invalid
APP_TARGETS_1_NAME=compose-backup
APP_TARGETS_1_URL=https://compose-backup.example.invalid
~~~

**Lưu ý:** file **.env** của Docker Compose chủ yếu hỗ trợ thay thế biến trong cấu hình Compose. Một biến chỉ nằm trong file **.env** không đương nhiên được truyền vào container nếu cấu hình Compose không tham chiếu hoặc đưa nó vào môi trường container theo cơ chế phù hợp. Với ví dụ **environment** phía trên, các key đã được khai báo trực tiếp nên được truyền vào container.

## 12. Dùng với Kubernetes

Trong Kubernetes, mỗi entry của **env** có tên và giá trị:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: list-env-demo
spec:
  replicas: 1
  selector:
    matchLabels:
      app: list-env-demo
  template:
    metadata:
      labels:
        app: list-env-demo
    spec:
      containers:
        - name: app
          image: my-list-env:1.0.0
          ports:
            - containerPort: 8080
          env:
            - name: APP_TARGETS_0_NAME
              value: "k8s-primary"
            - name: APP_TARGETS_0_URL
              value: "https://k8s-primary.example.invalid"
            - name: APP_TARGETS_1_NAME
              value: "k8s-backup"
            - name: APP_TARGETS_1_URL
              value: "https://k8s-backup.example.invalid"
~~~

Kubernetes không cần biết **_0_** là chỉ số danh sách Spring Boot. Nó chỉ cấp chuỗi tên và giá trị môi trường cho container; Spring Boot diễn giải chúng sau khi ứng dụng khởi động.

Khi ứng dụng có nhiều phần tử, số entry env có thể dài. Nếu danh sách phức tạp hoặc cần nhiều object, cân nhắc mount một file cấu hình bên ngoài từ ConfigMap hoặc cơ chế quản lý cấu hình phù hợp thay vì đặt hàng trăm biến môi trường riêng lẻ. Dù dùng ConfigMap hay biến môi trường, nguyên tắc về ưu tiên nguồn và thay thế List vẫn cần được hiểu.

Không đưa mật khẩu thật vào ví dụ hoặc manifest được commit công khai. Hãy dùng cơ chế Secret thích hợp cho giá trị bí mật và giới hạn quyền truy cập.

## 13. Danh sách từ biến môi trường được nạp ở nguồn nào?

Spring Boot áp dụng relaxed binding từ các biến môi trường hệ điều hành thông qua PropertySource tên **systemEnvironment** và một số PropertySource tương thích có tên kết thúc bằng **-systemEnvironment**. Đây là lý do quy tắc tên **APP_TARGETS_0_URL** có tác dụng tự nhiên với môi trường của process Java.

Nhưng nếu bạn tự tạo một **MapPropertySource** có tên bất kỳ, chứa key **APP_TARGETS_0_URL**, đừng mặc nhiên suy luận nó sẽ được xử lý như system environment. Khi viết code tích hợp cấu hình tùy biến, cần xem cách PropertySource đó được đưa vào Environment và binder diễn giải tên key như thế nào.

Trong thứ tự ưu tiên cấu hình Spring Boot thông thường:

- Các file Config Data như **application.yml** cung cấp những giá trị mặc định hoặc theo profile.
- Biến môi trường có thể ghi đè các giá trị tương ứng từ Config Data.
- Java system properties và tham số dòng lệnh cũng có các vị trí ưu tiên riêng.
- Với các test, những nguồn test-specific có thể có ưu tiên cao hơn.

Đừng hiểu relaxed binding là quy tắc **gộp dữ liệu**. Nó chỉ xác định cách **tên property** từ những nguồn khác nhau ánh xạ vào cấu trúc đích; chuyện **List bị thay thế** thuộc quy tắc merge của các collection.

## 14. Cách kiểm tra kết quả bind mà không lộ cấu hình nhạy cảm

Trong ví dụ học tập, endpoint **GET /targets** trả về các trường không nhạy cảm và đủ để thấy thứ tự list. Trong ứng dụng thật, nên kiểm tra bằng integration test hoặc log giới hạn thông tin.

Ví dụ một test khi các biến môi trường đã được cấp từ môi trường chạy của test:

~~~java
package com.example.listenv;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest
class ListEnvironmentBindingTest {

    @Autowired
    AppProperties appProperties;

    @Test
    void bindsTargetsInIndexOrder() {
        assertEquals(2, appProperties.targets().size());
        assertEquals("prod-primary",
                appProperties.targets().get(0).name());
        assertEquals("prod-backup",
                appProperties.targets().get(1).name());
    }
}
~~~

Test trên là ví dụ cho trường hợp **đã có** đúng bộ biến môi trường **APP_TARGETS_0_NAME**, **APP_TARGETS_1_NAME** và các URL tương ứng ở lượt chạy test. Nếu không cấp những biến đó, test sẽ đọc cấu hình mặc định và assertion cần được điều chỉnh.

Trong các bài test độc lập, nếu muốn cố định dữ liệu mà không phụ thuộc shell, có thể dùng **@SpringBootTest(properties = {...})** với tên property dạng **app.targets[0].name** và **app.targets[1].name**, hoặc dùng **ApplicationContextRunner** phù hợp. Tuy nhiên, để kiểm chứng chính xác cú pháp **biến môi trường**, vẫn cần một lượt chạy thực sự cung cấp tên **APP_TARGETS_0_NAME** qua môi trường process.

### 14.1. Đọc nguyên nhân khi bind lỗi

Nếu binding không khớp, kiểm tra:

1. Tên canonical gốc: có đúng **app.targets[0].url** không?
2. Dấu chấm đã thành **_** chưa?
3. Dấu gạch ngang trong tên property đã được **bỏ**, thay vì đổi thành một **_** khác, chưa?
4. Chỉ số đã được đặt ở đúng vị trí **_0_**, **_1_** chưa?
5. Các phần tử có bắt đầu từ **0** và có chỉ số liền nhau không?
6. Đã khai báo **@ConfigurationProperties** và đăng ký scanning/enable chưa?
7. Java field có đúng **List** và đúng kiểu phần tử không?
8. Các biến đã được cấp thực sự cho tiến trình Java/container chưa?
9. Có nguồn ưu tiên cao hơn đang thay cả danh sách không?
10. Những giá trị cần chuyển kiểu có hợp lệ không (số, duration, URI, enum...)?

Trong trường hợp cần điều tra, có thể log những tên biến được sử dụng hoặc thông tin số lượng phần tử đã bind. Không log token, mật khẩu hoặc nội dung secret.

## 15. Sai lầm thường gặp

### 15.1. Dùng ngoặc vuông trong tên biến môi trường

~~~text
APP_TARGETS[0]_URL
~~~

Đây không phải cú pháp Spring Boot khuyến nghị cho biến môi trường. Nhiều shell không chấp nhận dạng tên này như biến bình thường. Cách đúng cho danh sách là:

~~~text
APP_TARGETS_0_URL
~~~

### 15.2. Quên dấu gạch dưới giữa chỉ số và trường

~~~text
APP_TARGETS_0URL       <- không biểu diễn rõ [0].url
APP_TARGETS_0_URL      <- tương ứng app.targets[0].url
~~~

### 15.3. Thêm dấu gạch dưới vào tên kebab-case

~~~text
app.targets[0].base-url
~~~

Cách chuyển theo quy tắc canonical:

~~~text
APP_TARGETS_0_BASEURL
~~~

Không nên tự tách **base-url** thành **BASE_URL** khi mục tiêu là ánh xạ đúng cùng một segment property.

### 15.4. Dùng chỉ số 1 cho phần tử đầu tiên

~~~text
APP_TARGETS_1_NAME=only-target
~~~

Danh sách Spring Boot dùng chỉ số bắt đầu từ 0. Nếu chỉ có một target, hãy dùng:

~~~text
APP_TARGETS_0_NAME=only-target
~~~

### 15.5. Chỉ ghi đè một phần tử, tưởng phần tử còn lại ở YAML vẫn được giữ

Nếu định nghĩa cả **targets[0]** và **targets[1]** trong YAML nhưng môi trường chỉ định **targets[0]**, Spring Boot không mặc nhiên tạo danh sách gồm **targets[0]** mới và **targets[1]** cũ. List ở nguồn ưu tiên cao hơn sẽ thay List ở nguồn thấp hơn.

### 15.6. Quên rằng biến môi trường phải có mặt trong process

Bạn khai báo biến ở terminal khác, trong file .env chưa được chuyển vào container, hoặc trong CI job khác thì tiến trình Java hiện tại có thể không nhìn thấy biến. Kiểm tra cơ chế truyền env của môi trường triển khai thay vì chỉ kiểm tra chính tả tên biến.

### 15.7. Sửa biến môi trường rồi mong ứng dụng đang chạy tự cập nhật

Spring Boot thông thường bind **@ConfigurationProperties** khi khởi động ApplicationContext. Thay đổi môi trường ở shell sau đó thường không tự động làm mới bean của tiến trình đang chạy; cần khởi động lại hoặc một cơ chế refresh được thiết kế rõ ràng.

### 15.8. Trộn nhiều kiểu cấu hình danh sách mà không hiểu ưu tiên

Khai báo một phần List trong **application.yml**, một phần trong **application-prod.yml**, rồi vài phần tử qua env có thể dẫn đến kết quả khác kỳ vọng. Hãy xác định một nguồn chủ đạo cho **toàn bộ danh sách** ở môi trường đích và hạn chế các phần override không đầy đủ.

## 16. Bài thực hành

### Bài A: từ YAML sang bốn biến môi trường

1. Đặt hai target **built-in-primary** và **built-in-backup** trong **application.yml**.
2. Build ứng dụng và gọi **GET /targets** để thấy dữ liệu YAML.
3. Dừng ứng dụng.
4. Cấp đủ **APP_TARGETS_0_NAME**, **APP_TARGETS_0_URL**, **APP_TARGETS_1_NAME**, **APP_TARGETS_1_URL**.
5. Chạy lại cùng JAR và gọi endpoint để quan sát dữ liệu mới.

**Điều cần thấy:** hai phần tử được bind theo chỉ số **0** và **1**, không theo thứ tự các biến được khai báo.

### Bài B: chỉ cấp một phần tử

1. Khởi chạy bằng bộ biến môi trường chỉ có **APP_TARGETS_0_NAME** và **APP_TARGETS_0_URL**.
2. Gọi endpoint **/targets**.
3. So sánh với danh sách hai phần tử trong YAML.

**Điều cần thấy:** danh sách nguồn ưu tiên cao hơn thay thế danh sách YAML; phần tử thứ hai trong YAML không tự nối vào.

### Bài C: kiểm tra trường có dấu gạch ngang

1. Tạo một model có trường **baseUrl** và property canonical **app.targets[0].base-url**.
2. Cấp biến **APP_TARGETS_0_BASEURL**.
3. Kiểm tra giá trị được bind qua **@ConfigurationProperties**.

**Điều cần thấy:** biến môi trường loại bỏ gạch ngang của **base-url**; dấu **_0_** biểu diễn phần tử danh sách.

### Bài D: danh sách các chuỗi

1. Dùng **List<String> regions** trong một configuration properties record.
2. Cấp **APP_REGIONS_0=asia**, **APP_REGIONS_1=europe**, **APP_REGIONS_2=america**.
3. Đọc danh sách và kiểm tra chỉ số tương ứng.

**Điều cần thấy:** với List scalar, tên biến kết thúc ngay sau chỉ số, không có trường con.

### Bài E: quan sát trong container

1. Khai báo các biến bằng Docker Compose **environment** hoặc **docker run -e**.
2. Khởi động image ứng dụng đã build.
3. Gọi endpoint để kiểm tra danh sách được bind.
4. Thay đổi một giá trị env và tạo lại container để thấy tác dụng.

**Điều cần thấy:** Docker truyền biến môi trường; Spring Boot mới là nơi diễn giải **_0_**, **_1_** thành các chỉ số của List.

## 17. Những điều cần nhớ

- Trong **.properties** và đường property đã được flatten từ YAML, phần tử danh sách viết bằng **[0]**, **[1]**, **[2]**.
- Trong biến môi trường, chỉ số được phân tách bằng gạch dưới: **app.targets[0].url → APP_TARGETS_0_URL**.
- Chuyển tên property theo quy tắc: **dấu chấm → gạch dưới; gạch ngang → bỏ; chữ cái → in hoa; chỉ số [n] → _n_**.
- Danh sách bắt đầu từ chỉ số **0**, và nên khai báo các chỉ số liên tiếp.
- **@ConfigurationProperties** hỗ trợ bind List và nested object từ biến môi trường bằng relaxed binding.
- Khi nhiều nguồn định nghĩa cùng một **List**, Spring Boot chọn danh sách của nguồn ưu tiên cao hơn; không merge phần tử từ những nguồn còn lại.
- Nếu cần ghi đè List qua môi trường triển khai, hãy cấp đủ các phần tử và trường mà ứng dụng cần.
- Biến môi trường phải được truyền thật vào tiến trình Java, và thay đổi sau khởi động thường cần restart để được đọc lại.

**Tài liệu tham khảo chính thức:**

- Spring Boot 3.3 — Externalized Configuration, phần *Relaxed Binding*, *Binding From Environment Variables*, *Merging Complex Types*: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- Spring Boot 3.3 — Type-safe Configuration Properties: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.typesafe-configuration-properties
