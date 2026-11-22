# Giới hạn liên kết tên và cấu trúc phức tạp của `@Value` trong Spring Boot 3.3

## 1. Mục tiêu và bối cảnh

Spring Boot cho phép đưa cấu hình từ `application.properties`, YAML, biến môi trường, thuộc tính JVM và đối số dòng lệnh vào mã Java. Một cách đơn giản là dùng `@Value`:

```java
@Value("${app.name}")
private String name;
```

Với vài khóa đơn lẻ, cách viết này ngắn gọn. Nhưng khi hệ thống có hàng chục thuộc tính, tên khóa thay đổi giữa `kebab-case`, `camelCase` và biến môi trường, hoặc cấu hình bắt đầu có **danh sách, `Map`, đối tượng lồng nhau và ràng buộc dữ liệu**, `@Value` không còn thuận tiện như cơ chế `@ConfigurationProperties`.

Bài này làm rõ **giới hạn liên kết tên và cấu trúc phức tạp của `@Value`** trong Spring Boot 3.3, tập trung vào những câu hỏi:

1. `@Value("${demo.item-price}")` và `@Value("${demo.itemPrice}")` có thực sự tương đương?
2. Vì sao một danh sách YAML có thể truy cập từng phần tử nhưng không tự liên kết thành `List<Endpoint>` qua một `@Value` đơn giản?
3. Vì sao `Map<String, String>`, `Map<String, Object>` và danh sách đối tượng có cách liên kết khác nhau?
4. Lúc nào nên tiếp tục dùng `@Value`, lúc nào nên chuyển sang `@ConfigurationProperties`?
5. Cách sử dụng cấu hình có kiểu, giá trị mặc định, validation và kiểm tra giá trị cuối cùng ra sao?

Các ví dụ minh họa sử dụng **Java 17 trở lên**, **Spring Boot 3.3.x** và cú pháp Spring Framework tương ứng. Người học nên biết Java record/class, constructor injection, bean và các định dạng cấu hình cơ bản.

**Thông điệp chính:** `@Value` là cơ chế **chèn một biểu thức/giá trị vào điểm tiêm** của Spring; nó không phải là một phiên bản thu nhỏ nhưng tương đương hoàn toàn với bộ **Binder** dành cho `@ConfigurationProperties`.

## 2. Ba cơ chế truy cập cấu hình cần phân biệt

Spring Boot cung cấp nhiều cách đọc cấu hình, nhưng chúng không có cùng giao diện hoặc mức trừu tượng.

| Cách truy cập | Ví dụ | Tình huống phù hợp |
| --- | --- | --- |
| `@Value` | `@Value("${app.timeout:5s}")` | Một hoặc vài giá trị đơn lẻ; đôi khi cần SpEL |
| `Environment` | `env.getProperty("app.timeout")` | Tra cứu giá trị động bằng khóa, xử lý điều kiện trong mã |
| `@ConfigurationProperties` | `@ConfigurationProperties(prefix = "app.client")` | Cả nhóm cấu hình có kiểu, nhiều trường, `List`, `Map`, đối tượng lồng nhau |

Tất cả đều làm việc với hệ thống cấu hình của Spring, nhưng:

- `Environment` cho phép tra cứu một khóa bằng chương trình. Nó không tự chuyển cả một cây khóa thành một đối tượng Java nghiệp vụ.
- `@Value` dùng cơ chế placeholder `${...}` hoặc biểu thức SpEL `#{...}` tại **điểm tiêm**. Nó phụ thuộc vào cách giải quyết biểu thức và cách chuyển đổi kiểu ở điểm đó.
- `@ConfigurationProperties` dùng Binder của Spring Boot để **liên kết một nhóm khóa theo prefix** vào cấu trúc Java có kiểu. Nó hỗ trợ relaxed binding, các cấu trúc phức tạp, metadata cấu hình và tích hợp validation.

Ví dụ dữ liệu phẳng:

```properties
app.title=Inventory API
app.retry-count=3
```

Dùng `@Value` rất đơn giản:

```java
@Component
public class Banner {

    private final String title;
    private final int retryCount;

    public Banner(
            @Value("${app.title}") String title,
            @Value("${app.retry-count:3}") int retryCount
    ) {
        this.title = title;
        this.retryCount = retryCount;
    }
}
```

Dùng constructor injection giúp các phụ thuộc và giá trị bắt buộc được thể hiện rõ ngay khi tạo bean. Khi một bean chỉ cần hai giá trị độc lập, cách này hoàn toàn hợp lý.

Tuy nhiên, nếu `app` có 20 trường và nhiều mức lồng nhau, constructor đầy những `@Value` riêng lẻ sẽ khó đọc, khó kiểm thử và khó thay đổi đồng bộ.

## 3. `@Value` dùng placeholder, không phải Binder kiểu `@ConfigurationProperties`

Cú pháp cơ bản của placeholder:

```java
@Value("${app.title}")
String title;
```

Spring tìm thuộc tính `app.title` rồi dùng giá trị tìm được để tiêm. Cú pháp mặc định thường dùng:

```java
@Value("${app.retry-count:3}")
int retryCount;
```

Nếu thuộc tính không có giá trị và không được nguồn khác cung cấp, placeholder có thể dùng `3`. Giá trị chuỗi được chuyển thành `int` khi tiêm thông qua cơ chế chuyển đổi kiểu thích hợp.

Nếu không khai báo mặc định:

```java
@Value("${app.required-name}")
String requiredName;
```

thì placeholder không giải quyết được thường làm quá trình tạo bean thất bại trong ngữ cảnh ứng dụng Spring Boot thông thường. Vì vậy, `@Value` cũng có thể làm ứng dụng thất bại sớm khi thiếu một khóa bắt buộc.

Điều cần phân biệt là **giải quyết một placeholder** không đồng nghĩa với **quét nhiều thuộc tính chung prefix, tạo cấu trúc Java và liên kết từng thuộc tính thành phần**.

Ví dụ:

```yaml
app:
  mail:
    from: noreply@example.test
    timeout: 5s
    recipients:
      - ops@example.test
      - support@example.test
```

`@Value("${app.mail.from}")` thường truy cập một khóa đơn giản. `@Value("${app.mail.recipients[0]}")` có thể truy cập phần tử tại chỉ số cụ thể nếu nguồn cấu hình tạo ra khóa tương ứng. Nhưng `@Value("${app.mail}")` **không có nghĩa** Spring sẽ tự tạo `MailProperties` đầy đủ gồm `from`, `timeout` và `recipients`.

### 3.1. Đừng nhầm tên thuộc tính với tên trường Java

Tên trường Java:

```java
private int retryCount;
```

không bảo đảm `@Value("${app.retryCount}")` sẽ có cùng khả năng nhận biến môi trường hoặc mọi biến thể khóa như Binder. Ở `@Value`, **chuỗi nằm trong `${...}`** mới là điều quyết định cách tra cứu.

Vì thế, cần chọn tên placeholder theo dạng chuẩn, thay vì sao chép tùy ý tên biến Java.

## 4. Giới hạn relaxed binding của `@Value`

### 4.1. Relaxed binding là gì?

Cơ chế relaxed binding cho phép những cách đặt tên khác nhau biểu diễn cùng một thuộc tính logic khi Binder liên kết cấu hình.

Ví dụ thuộc tính `app.client.connect-timeout` có thể xuất hiện trong tệp như:

```properties
app.client.connect-timeout=3s
```

hoặc:

```properties
app.client.connectTimeout=3s
```

Và biến môi trường tương ứng theo quy tắc chuẩn là:

```text
APP_CLIENT_CONNECTTIMEOUT
```

Khi dùng `@ConfigurationProperties(prefix = "app.client")`, Spring Boot Binder hiểu các biến thể hợp lệ ấy để điền vào trường Java `connectTimeout`.

### 4.2. Điểm quan trọng: `@Value` chỉ hỗ trợ ở mức hạn chế

Tài liệu **Spring Boot 3.3 — Externalized Configuration** nêu rõ `@Value` là tính năng của Spring container và **không có cùng toàn bộ tính năng** của type-safe configuration properties. Với `@Value`, Spring Boot khuyến nghị tham chiếu thuộc tính bằng **tên canonical dạng kebab-case, chữ thường**.

So sánh:

```java
@Value("${demo.item-price}")
private BigDecimal price;
```

và:

```java
@Value("${demo.itemPrice}")
private BigDecimal price;
```

Giả sử cấu hình có:

```properties
demo.itemPrice=12.50
```

Hoặc một môi trường khác chỉ cung cấp:

```text
DEMO_ITEMPRICE=12.50
```

Với dạng canonical `${demo.item-price}`, Spring Boot có thể áp dụng logic tra cứu tương thích với relaxed binding để nhận các biến thể phù hợp.

Ngược lại, nếu viết `${demo.itemPrice}`, **không được giả định** nó sẽ xét cả `demo.item-price` và `DEMO_ITEMPRICE` theo cùng cách. Đây là ví dụ chính thức cho giới hạn của `@Value`.

**Quy tắc thực hành:**

```java
// Nên dùng dạng canonical cho placeholder
@Value("${app.client.connect-timeout:5s}")
private Duration timeout;
```

Thay vì:

```java
// Không nên phụ thuộc vào các dạng tên tùy ý
@Value("${app.client.connectTimeout:5s}")
private Duration timeout;
```

Dạng canonical không biến `@Value` thành Binder đầy đủ, nhưng giúp tránh một nhóm lỗi quan trọng khi cấu hình đổi từ file sang biến môi trường.

### 4.3. Bảng so sánh khả năng tên khóa

| Khả năng | `@Value` | `@ConfigurationProperties` |
| --- | --- | --- |
| Đọc một khóa chính xác | Có | Có, thông qua nhóm binding |
| Nhận nhiều biến thể tên thuộc tính | **Hạn chế**, nên dùng placeholder canonical | **Có**, relaxed binding là tính năng chính |
| Tự liên kết nguyên nhóm thuộc tính | Không theo cách của Binder | Có |
| Metadata cấu hình được sinh cho IDE | Không từ chính `@Value` | Có thể dùng configuration processor |
| SpEL | Có | Không hỗ trợ SpEL như `@Value` |
| Liên kết đối tượng lồng nhau | Không tự động chỉ với một placeholder | Có |
| Liên kết cấu trúc danh sách/`Map` | Chỉ một số trường hợp thủ công hoặc qua chuyển đổi/SpEL | Có hỗ trợ chính thức |
| Validation theo cấu trúc | Không có mô hình tương đương trực tiếp từ `@Value` | Có thể tích hợp Bean Validation |

Vì vậy, một chuỗi `${app.some-key}` có thể hoạt động hôm nay không bảo đảm mọi biến thể đặt tên hoặc kiểu nguồn cấu hình sau này sẽ hoạt động giống hệt.

## 5. Tên biến môi trường: vị trí dễ thấy nhất của giới hạn này

Spring Boot có quy tắc đặt tên biến môi trường cho Binder:

1. Thay dấu `.` bằng `_`.
2. Bỏ dấu `-`.
3. Đổi tên thành chữ in hoa.

Ví dụ:

| Thuộc tính chuẩn | Biến môi trường tương ứng |
| --- | --- |
| `app.region` | `APP_REGION` |
| `app.mail.retry-count` | `APP_MAIL_RETRYCOUNT` |
| `app.client.connect-timeout` | `APP_CLIENT_CONNECTTIMEOUT` |
| `spring.main.log-startup-info` | `SPRING_MAIN_LOGSTARTUPINFO` |

Ví dụ trong Bash:

```bash
export APP_MAIL_RETRYCOUNT=6
java -jar app.jar
```

Trong PowerShell:

```powershell
$env:APP_MAIL_RETRYCOUNT = '6'
java -jar .\app.jar
```

Một điểm tiêm dùng dạng canonical:

```java
@Value("${app.mail.retry-count:3}")
int retryCount;
```

có thể nhận biến thể phù hợp. Nhưng nếu viết placeholder không chuẩn:

```java
@Value("${app.mail.retryCount:3}")
int retryCount;
```

thì không thể suy ra nó sẽ xét đầy đủ mọi dạng như Binder.

### Danh sách trong biến môi trường

Với Binder, chỉ số danh sách được đặt giữa các dấu `_`. Ví dụ:

```text
app.nodes[0].host  -> APP_NODES_0_HOST
app.nodes[1].host  -> APP_NODES_1_HOST
```

Đây là cơ chế liên kết danh sách của `@ConfigurationProperties`. Không nên biến nó thành một loạt `@Value("${app.nodes[0].host}")`, `@Value("${app.nodes[1].host}")` cố định khi số phần tử có thể thay đổi. Cấu hình danh sách nên được biểu diễn thành `List<Node>`.

## 6. `@Value` xử lý tốt giá trị đơn lẻ đến đâu?

Những loại dữ liệu đơn giản thường phù hợp:

```properties
app.display-name=Demo API
app.enabled=true
app.retry-count=4
app.request-timeout=3s
app.endpoint=https://api.example.test
```

Ví dụ:

```java
@Component
public class SimpleOptions {

    private final String displayName;
    private final boolean enabled;
    private final int retryCount;
    private final Duration timeout;
    private final URI endpoint;

    public SimpleOptions(
            @Value("${app.display-name}") String displayName,
            @Value("${app.enabled:false}") boolean enabled,
            @Value("${app.retry-count:3}") int retryCount,
            @Value("${app.request-timeout:5s}") Duration timeout,
            @Value("${app.endpoint}") URI endpoint
    ) {
        this.displayName = displayName;
        this.enabled = enabled;
        this.retryCount = retryCount;
        this.timeout = timeout;
        this.endpoint = endpoint;
    }
}
```

Các import liên quan:

```java
import java.net.URI;
import java.time.Duration;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
```

Việc chuyển đổi chuỗi thành `int`, `boolean`, `Duration` hoặc `URI` phụ thuộc vào bộ chuyển đổi kiểu khả dụng trong ApplicationContext. Trong một ứng dụng Spring Boot tiêu chuẩn, nhiều chuyển đổi phổ biến được hỗ trợ.

Nhưng **có thể chuyển đổi kiểu đơn lẻ** không đồng nghĩa với **có thể liên kết mọi cấu trúc**. Một chuỗi `"3s"` chuyển thành `Duration` đơn giản hơn rất nhiều so với việc đọc hàng chục khóa lồng nhau thành `List<Gateway>`.

### Mặc định không thay thế validation

Ví dụ:

```java
@Value("${app.pool-size:10}")
private int poolSize;
```

Mặc định `10` chỉ giải quyết trường hợp không có giá trị. Nó **không** tự bảo đảm `poolSize > 0`. Nếu cấu hình là `-4`, một chuyển đổi thành công vẫn có thể cho giá trị không phù hợp nghiệp vụ. Cần validation ở mức cấu hình hoặc logic riêng để kiểm soát điều kiện này.

## 7. Danh sách: vì sao một placeholder không phải phép binding `List<T>`

Xét YAML:

```yaml
app:
  notification:
    recipients:
      - ops@example.test
      - support@example.test
```

Spring Boot nạp YAML thành các thuộc tính có thể truy cập theo đường dẫn/phần tử thích hợp. Nếu biết chắc vị trí, có thể viết:

```java
@Value("${app.notification.recipients[0]}")
String firstRecipient;
```

Điều này khác hoàn toàn mục tiêu:

```java
List<String> recipients;
```

Bạn không nên mặc định rằng:

```java
@Value("${app.notification.recipients}")
List<String> recipients;
```

sẽ lấy nguyên cấu trúc danh sách YAML như Binder. Với YAML được flatten theo chỉ số, không nhất thiết tồn tại một khóa scalar `app.notification.recipients` chứa toàn bộ chuỗi để placeholder đơn lẻ giải quyết.

### 7.1. Vì sao ví dụ CSV có thể tạo hiểu nhầm?

Nếu tệp `.properties` chứa:

```properties
app.notification.recipients=ops@example.test,support@example.test
```

thì tùy ConversionService, một điểm tiêm `List<String>` hoặc mảng có thể chuyển đổi từ **một chuỗi CSV** thành nhiều phần tử:

```java
@Value("${app.notification.recipients}")
private List<String> recipients;
```

Đó là **chuyển đổi từ một giá trị chuỗi**, không phải Binder duyệt một cây cấu hình YAML phức tạp. Nếu đổi từ CSV sang YAML list, cùng đoạn `@Value` có thể không còn hoạt động như mong đợi.

Trong hệ thống cần danh sách thực sự, hãy dùng:

```java
@ConfigurationProperties(prefix = "app.notification")
public record NotificationProperties(List<String> recipients) {
}
```

Binder có thể xử lý các biểu diễn danh sách được Spring Boot hỗ trợ trong properties, YAML và biến môi trường.

### 7.2. Danh sách đối tượng còn khác xa CSV

Xét:

```yaml
app:
  integrations:
    gateways:
      - id: primary
        url: https://primary.example.test
        timeout: 2s
      - id: backup
        url: https://backup.example.test
        timeout: 5s
```

Bạn cần Java:

```java
List<Gateway> gateways;
```

Ở đây mỗi phần tử có **nhiều trường và nhiều kiểu**, không thể hiểu đầy đủ chỉ từ một chuỗi `app.integrations.gateways` thông thường.

Nếu chỉ dùng `@Value`:

```java
@Value("${app.integrations.gateways[0].id}")
String primaryId;
```

bạn phải chọn chỉ số cố định và viết thêm một điểm tiêm cho từng trường. Cấu hình tăng thêm phần tử thứ ba sẽ làm mã Java phải thay đổi, đi ngược mục đích externalized configuration.

## 8. `Map`: đọc một khóa con không phải liên kết toàn bộ bảng

YAML:

```yaml
app:
  limits:
    standard: 50
    premium: 500
    enterprise: 5000
```

Một giá trị riêng lẻ có thể được tra cứu như:

```java
@Value("${app.limits.standard}")
private int standardLimit;
```

Nhưng yêu cầu thực tế thường là:

```java
Map<String, Integer> limits;
```

Để ứng dụng tự đọc số lượng gói không cố định.

`@Value("${app.limits}")` không tự động duyệt các khóa `app.limits.standard`, `app.limits.premium`, `app.limits.enterprise` rồi tạo `Map` theo quy tắc chính thức của Binder. Nếu có trường hợp SpEL hoặc bộ chuyển đổi chuyên biệt làm được, đó là một giải pháp riêng với quy ước dữ liệu riêng, không nên nhầm với cơ chế cấu trúc của `@ConfigurationProperties`.

Dùng Binder:

```java
@ConfigurationProperties(prefix = "app")
public record LimitsProperties(Map<String, Integer> limits) {
}
```

### 8.1. Khóa `Map` có ký tự đặc biệt

Spring Boot có quy tắc **bracket notation** để giữ nguyên các ký tự đặc biệt trong khóa `Map`.

Ví dụ `.properties`:

```properties
app.labels[/red]=high
app.labels[/blue]=low
```

Hoặc YAML (bọc bracket trong dấu nháy):

```yaml
app:
  labels:
    "[/red]": high
    "[/blue]": low
```

Với `Map<String, String> labels`, các khóa `/red`, `/blue` được giữ nguyên. Nếu bỏ bracket, các ký tự không phải chữ, số, dấu gạch nối hoặc dấu chấm có thể bị loại trong quá trình binding.

Một trường hợp đặc biệt khác là dấu `.` trong khóa: với `Map<String, String>` dấu chấm có thể được giữ trong khóa scalar, nhưng với `Map<String, Object>` dấu chấm có thể tạo cấu trúc lồng nhau nếu không dùng bracket.

Đây là ví dụ cho thấy **Binding Map có quy tắc riêng**, không thể thay thế bằng ý tưởng “dùng `@Value` lấy một chuỗi là xong”.

## 9. `@Value` và SpEL: mạnh ở biểu thức, không thay thế object binding

`@Value` còn có thể dùng **Spring Expression Language (SpEL)**:

```java
@Value("#{2 * 3}")
int six;
```

Hoặc tính toán từ một giá trị placeholder:

```java
@Value("#{'${app.allowed-regions:us,eu}'.split(',')}")
List<String> regions;
```

Nếu `app.allowed-regions` là chuỗi CSV như:

```properties
app.allowed-regions=us,eu,apac
```

biểu thức trên có thể tạo danh sách chuỗi qua `split(',')`.

Tuy nhiên:

- SpEL chỉ biết dữ liệu bạn đưa vào biểu thức, không tự trở thành Binder của Spring Boot.
- Giá trị chứa dấu nháy hoặc ký tự đặc biệt có thể làm biểu thức nội suy thủ công khó kiểm soát.
- `split(',')` không phải trình phân tích tổng quát của CSV có quote, dấu phẩy escaped hay cấu trúc lồng.
- Nếu dữ liệu được chuyển từ CSV thành YAML list, biểu thức cũ có thể không phù hợp.
- Các biểu thức quá dài, lặp ở nhiều bean làm cấu hình khó theo dõi, khó tái sử dụng và khó chẩn đoán.

Ví dụ một số mã nguồn sử dụng:

```java
@Value("#{${app.prices}}")
Map<String, Integer> prices;
```

Cách này chỉ có ý nghĩa nếu giá trị `app.prices` được cung cấp dưới **cú pháp SpEL tương thích**, không phải bất kỳ Map YAML nào cũng tự chuyển thành biểu thức tương ứng.

Nếu yêu cầu là **bản đồ cấu hình** đúng nghĩa, dùng `@ConfigurationProperties` dễ dự đoán hơn.

### 9.1. Bảng tính năng chính thức của Spring Boot

| Tính năng | `@ConfigurationProperties` | `@Value` |
| --- | --- | --- |
| Relaxed binding | Có | Hạn chế |
| Metadata cấu hình | Có | Không |
| Đánh giá biểu thức SpEL | Không | Có |

Sự khác biệt này mang tính **thiết kế**. Không phải `@Value` “bị lỗi” vì không tự liên kết cây cấu hình; nó được thiết kế cho tiêm giá trị và biểu thức, trong khi `@ConfigurationProperties` được thiết kế cho cấu hình có kiểu.

## 10. Lựa chọn chuẩn: `@ConfigurationProperties` cho cấu hình có cấu trúc

Xây dựng một ví dụ thực tế về cổng dịch vụ với các thành phần:

- `enabled`: bật/tắt một chức năng.
- `retryCount`: số lần thử lại.
- `connectTimeout`: thời gian chờ kết nối.
- `gateways`: danh sách cổng có `name`, `url`, `timeout`.
- `quotas`: `Map` từ tên gói đến một đối tượng hạn mức.

Cấu hình YAML:

```yaml
app:
  access:
    enabled: true
    retry-count: 3
    connect-timeout: 2s

    gateways:
      - name: primary
        url: https://primary.example.test
        timeout: 2s
      - name: backup
        url: https://backup.example.test
        timeout: 5s

    quotas:
      standard:
        max-requests: 100
        window: 1m
      premium:
        max-requests: 1000
        window: 10m
```

Java record:

```java
package example.configaccess;

import java.net.URI;
import java.time.Duration;
import java.util.List;
import java.util.Map;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.access")
public record AccessProperties(
        boolean enabled,
        int retryCount,
        Duration connectTimeout,
        List<Gateway> gateways,
        Map<String, Quota> quotas
) {
    public record Gateway(
            String name,
            URI url,
            Duration timeout
    ) {
    }

    public record Quota(
            int maxRequests,
            Duration window
    ) {
    }
}
```

Ý nghĩa:

- `retry-count` liên kết vào trường record `retryCount`.
- `connect-timeout` liên kết vào `Duration connectTimeout`.
- Các phần tử dưới `gateways` liên kết thành `List<Gateway>` có hai đối tượng.
- Các khóa `standard`, `premium` liên kết thành `Map<String, Quota>` với giá trị là record `Quota`.
- Lớp cấu hình mang **một mô hình dữ liệu rõ ràng**, không phải nhiều điểm tiêm rời rạc.

Trong Spring Boot 3.3, record có một constructor phù hợp có thể dùng constructor binding mà không cần thêm `@ConstructorBinding` riêng. Nếu lớp có nhiều constructor, có thể cần chỉ định constructor được dùng; bean cấu hình theo constructor binding cần được đăng ký qua cơ chế configuration properties phù hợp.

### 10.1. Đăng ký configuration properties

Lớp ứng dụng:

```java
package example.configaccess;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class ConfigAccessApplication {

    public static void main(String[] args) {
        SpringApplication.run(ConfigAccessApplication.class, args);
    }
}
```

`@ConfigurationPropertiesScan` giúp Spring Boot phát hiện và đăng ký các kiểu cấu hình trong phạm vi quét. Trong dự án có ít lớp, có thể dùng `@EnableConfigurationProperties(AccessProperties.class)` tại một lớp cấu hình thích hợp.

**Lưu ý:** không tùy tiện thêm `@Component` vào record định dùng constructor binding của Spring Boot. Constructor binding cho `@ConfigurationProperties` có cơ chế đăng ký khác với việc tạo bean bằng `@Component`, `@Bean` hoặc `@Import`.

### 10.2. Dùng constructor injection trong bean khác

```java
package example.configaccess;

import org.springframework.stereotype.Service;

@Service
public class GatewaySummaryService {

    private final AccessProperties properties;

    public GatewaySummaryService(AccessProperties properties) {
        this.properties = properties;
    }

    public int gatewayCount() {
        return properties.gateways().size();
    }

    public int standardQuota() {
        return properties.quotas().get("standard").maxRequests();
    }
}
```

Một bean chỉ cần phụ thuộc vào `AccessProperties`, không phải sáu hay tám tham số `@Value`. Nếu cấu hình có thêm `Gateway`, Spring Boot liên kết danh sách theo nội dung bên ngoài mà không cần thêm trường `@Value` mới cho từng phần tử.

Trong ví dụ, các giá trị được định nghĩa đầy đủ. Khi ứng dụng thật có thể thiếu danh sách hay khóa `standard`, hãy kết hợp validation và cách xử lý giá trị khuyết phù hợp, tránh dereference `null`.

## 11. Cùng cấu trúc đó trong `.properties`

Không phải YAML mới dùng được Binder. Cùng cấu hình có thể viết:

```properties
app.access.enabled=true
app.access.retry-count=3
app.access.connect-timeout=2s

app.access.gateways[0].name=primary
app.access.gateways[0].url=https://primary.example.test
app.access.gateways[0].timeout=2s

app.access.gateways[1].name=backup
app.access.gateways[1].url=https://backup.example.test
app.access.gateways[1].timeout=5s

app.access.quotas.standard.max-requests=100
app.access.quotas.standard.window=1m
app.access.quotas.premium.max-requests=1000
app.access.quotas.premium.window=10m
```

Binder hiểu các chỉ số `[0]`, `[1]` để xây dựng danh sách; `standard`, `premium` để xây dựng `Map`.

Nếu đổi `.properties` sang YAML, mã Java `AccessProperties` vẫn giữ nguyên. Đây chính là giá trị của cấu hình có kiểu: **mô hình Java ổn định trong khi dữ liệu có thể đến từ nhiều nguồn**.

Trong trường hợp dùng `@Value` cho từng phần tử, bạn sẽ phải biết trước tên và vị trí từng phần tử — điều này làm mất lợi ích của việc đưa danh sách ra cấu hình.

## 12. Có nhiều nguồn cấu hình: danh sách và Map không ghi đè giống nhau

Hãy xét cấu hình chung:

```yaml
app:
  access:
    gateways:
      - name: primary
        url: https://primary.example.test
        timeout: 2s
      - name: backup
        url: https://backup.example.test
        timeout: 5s

    quotas:
      standard:
        max-requests: 100
        window: 1m
```

Thêm tài liệu theo profile `dev`:

```yaml
---
spring:
  config:
    activate:
      on-profile: dev

app:
  access:
    gateways:
      - name: local
        url: http://localhost:8081
        timeout: 1s

    quotas:
      standard:
        max-requests: 20
```

Với Binder của Spring Boot:

- **`List`** ở nguồn ưu tiên cao hơn thường **thay thế toàn bộ danh sách** ở nguồn thấp hơn; không tự ghép `local` với `primary`, `backup`. Trong ví dụ `dev`, danh sách `gateways` sẽ chỉ còn phần tử `local` nếu không có nguồn khác ưu tiên hơn.
- **`Map`** có thể nhận dữ liệu từ nhiều nguồn ở mức khóa con. `standard.max-requests` từ `dev` có thể ghi đè thành `20`, còn `standard.window` từ tài liệu chung vẫn có thể đóng góp `1m`.

Đây là quy tắc liên kết cấu trúc của Spring Boot. Dùng `@Value` truy cập thủ công từng `app.access.gateways[0].name` hoặc `app.access.quotas.standard.max-requests` có thể che mất toàn cảnh cấu trúc và khiến việc lý giải ghi đè khó khăn.

**Quan trọng:** kết quả cuối còn phụ thuộc vị trí tệp, các profile được bật, biến môi trường, đối số khởi động và những PropertySource khác. Không nên đánh giá ưu tiên chỉ dựa trên một đoạn YAML.

## 13. Default và thiếu cấu hình: khác biệt giữa giá trị đơn và nhóm dữ liệu

### 13.1. `@Value` có mặc định đơn giản

```java
@Value("${app.retry-count:3}")
private int retryCount;
```

Khi thiếu khóa, `3` là mặc định có thể dùng. Đây là cách viết ngắn nếu có một giá trị nhỏ, độc lập.

Nhưng với nhiều trường có quan hệ:

```java
@Value("${app.tls.enabled:false}")
private boolean tlsEnabled;

@Value("${app.tls.keystore:}")
private String keystore;

@Value("${app.tls.protocol:TLSv1.3}")
private String protocol;
```

Bạn dễ tạo ra tổ hợp trạng thái thiếu nhất quán, chẳng hạn `tlsEnabled=true` nhưng `keystore` rỗng. Khi đó mặc định ở từng trường riêng lẻ không giải quyết được việc **xác thực tính nhất quán của một nhóm cấu hình**.

### 13.2. `@DefaultValue` cho constructor binding

Với `@ConfigurationProperties`, Spring Boot có `@DefaultValue` cho tham số constructor hoặc thành phần record:

```java
package example.configaccess;

import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "app.worker")
public record WorkerProperties(
        @DefaultValue("3") int maxRetries,
        @DefaultValue("5s") Duration timeout,
        @DefaultValue("true") boolean enabled
) {
}
```

Ở đây các mặc định thuộc về **kiểu dữ liệu cấu hình**, thay vì được rải trong nhiều điểm tiêm của các bean nghiệp vụ.

Khi có cấu trúc phức tạp hoặc cần đảm bảo một số trường luôn có giá trị, có thể thiết kế constructor/record và ràng buộc phù hợp, thay vì tự chèn hàng loạt chuỗi mặc định `${...:...}`.

### 13.3. Giá trị `null` và thiếu tài liệu không giống nhau

Khi thiếu một nhóm cấu hình lồng nhau, Binder có thể để trường tham chiếu là `null` nếu không có mặc định hoặc cơ chế khởi tạo thích hợp. Đừng mặc định rằng `List`, `Map` hoặc record lồng nhau luôn khác `null`.

Với `@Value`, một placeholder không tồn tại có thể làm bean thất bại khi tạo nếu không có mặc định. Với `@ConfigurationProperties`, việc thiếu giá trị được xử lý theo mô hình binding và validation. Hai cơ chế có những quy tắc khác nhau, nên không nên kết luận rằng dùng Binder thì mọi dữ liệu thiếu đều tự động được chấp nhận hoặc bị từ chối.

## 14. Validation: điểm mạnh của cấu hình có kiểu

Một nhóm cấu hình có thể có các ràng buộc như:

- Số lần thử lại không âm.
- Tên gateway không được trống.
- Danh sách gateway phải có ít nhất một phần tử.
- Mỗi hạn mức phải lớn hơn 0.

Khi ứng dụng có dependency `spring-boot-starter-validation`, có thể kết hợp Bean Validation với `@ConfigurationProperties`.

Ví dụ:

```java
package example.configaccess;

import java.net.URI;
import java.time.Duration;
import java.util.List;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.integration")
public record IntegrationProperties(
        @Min(0) int retryCount,
        @NotEmpty List<@Valid Gateway> gateways
) {
    public record Gateway(
            @NotBlank String name,
            @NotNull URI url,
            @NotNull Duration timeout
    ) {
    }
}
```

Giải thích:

- `@Validated` yêu cầu validation cho configuration properties.
- `@Min(0)` kiểm tra `retryCount`.
- `@NotEmpty` yêu cầu danh sách không rỗng.
- `@Valid` giúp validation đi vào phần tử phức tạp trong danh sách.
- `@NotBlank` và `@NotNull` thể hiện các trường bắt buộc.

Nếu cấu hình không thỏa ràng buộc, ứng dụng có thể thất bại trong giai đoạn binding/validation với thông báo hướng tới nhóm cấu hình. Điều này hữu ích hơn việc một bean nghiệp vụ phát hiện muộn rằng `url` rỗng hoặc thiếu danh sách.

Cấu hình mẫu:

```yaml
app:
  integration:
    retry-count: 2
    gateways:
      - name: primary
        url: https://primary.example.test
        timeout: 2s
```

Ràng buộc của kiểu `IntegrationProperties` tập trung một chỗ, không lặp đi lặp lại trong nhiều constructor hoặc field được `@Value`.

**Giới hạn cần nhớ:** Bean Validation kiểm tra những điều kiện được khai báo và cần provider phù hợp. Nó không tự bảo đảm URL thực sự truy cập được, hay hệ thống bên ngoài sẵn sàng.

## 15. Metadata cấu hình và hỗ trợ của IDE

`@ConfigurationProperties` có thể kết hợp **Spring Boot Configuration Processor** để tạo metadata cấu hình. Trong dự án Maven, có thể khai báo annotation processor theo cấu hình build tương ứng; trong Gradle, thường dùng cấu hình `annotationProcessor` thích hợp.

Metadata giúp IDE nhận biết các khóa như:

```text
app.access.retry-count
app.access.connect-timeout
app.access.gateways
app.access.quotas
```

và cung cấp gợi ý, mô tả, kiểu dữ liệu hoặc mặc định tùy thông tin khai báo.

Với `@Value("${app.retry-count}")`, bản thân annotation đó **không tạo ra metadata nhóm cấu hình tương đương**. Nếu một hệ thống có nhiều khóa tự định nghĩa, đây là lý do thiết thực để gom chúng vào `@ConfigurationProperties`.

Metadata giúp phát triển và tài liệu hóa, nhưng **không thay thế kiểm tra giá trị chạy thực tế**. Việc IDE gợi ý một khóa không bảo đảm môi trường triển khai đã cấp giá trị đúng.

## 16. Bài thực hành: so sánh cùng dữ liệu với `@Value` và `@ConfigurationProperties`

Thực hành này dùng Java 17, Spring Boot 3.3.x với `spring-boot-starter`. Các tệp và class đều nằm trong package `example.bindinglab`.

### Bước 1 — tạo `application.yaml`

Tại `src/main/resources/application.yaml`:

```yaml
spring:
  application:
    name: binding-lab

demo:
  item-price: 12.50

app:
  access:
    enabled: true
    retry-count: 4
    connect-timeout: 3s

    gateways:
      - name: primary
        url: https://primary.example.test
        timeout: 2s
      - name: backup
        url: https://backup.example.test
        timeout: 5s

    quotas:
      standard:
        max-requests: 50
        window: 1m
      premium:
        max-requests: 500
        window: 5m
```

### Bước 2 — tạo record chứa cấu hình có cấu trúc

`src/main/java/example/bindinglab/AccessProperties.java`:

```java
package example.bindinglab;

import java.net.URI;
import java.time.Duration;
import java.util.List;
import java.util.Map;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.access")
public record AccessProperties(
        boolean enabled,
        int retryCount,
        Duration connectTimeout,
        List<Gateway> gateways,
        Map<String, Quota> quotas
) {
    public record Gateway(
            String name,
            URI url,
            Duration timeout
    ) {
    }

    public record Quota(
            int maxRequests,
            Duration window
    ) {
    }
}
```

### Bước 3 — ứng dụng có cả hai cách truy cập

`src/main/java/example/bindinglab/BindingLabApplication.java`:

```java
package example.bindinglab;

import java.math.BigDecimal;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
@ConfigurationPropertiesScan
public class BindingLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(BindingLabApplication.class, args);
    }

    @Bean
    ApplicationRunner showConfig(
            AccessProperties access,
            @Value("${demo.item-price}") BigDecimal itemPrice,
            @Value("${app.access.retry-count}") int retries,
            @Value("${app.access.gateways[0].name}") String firstGateway
    ) {
        return args -> {
            System.out.println("itemPrice=" + itemPrice);
            System.out.println("retryCountByValue=" + retries);
            System.out.println("firstGatewayByValue=" + firstGateway);

            System.out.println("enabled=" + access.enabled());
            System.out.println("connectTimeout=" + access.connectTimeout());
            System.out.println("gateways=" + access.gateways().size());
            System.out.println("firstGatewayUrl="
                    + access.gateways().get(0).url());
            System.out.println("standardQuota="
                    + access.quotas().get("standard").maxRequests());
        };
    }
}
```

Quan sát:

- `@Value` đọc ba giá trị đơn lẻ, trong đó có một khóa theo chỉ số `[0]`.
- `AccessProperties` đại diện toàn bộ cây cấu hình.
- Cấu trúc `List<Gateway>` và `Map<String, Quota>` được Binder xử lý.
- Cùng một `Environment` cung cấp dữ liệu, nhưng hai API có khả năng và mục đích khác nhau.

### Bước 4 — chạy ứng dụng

Qua Maven wrapper:

```bash
./mvnw spring-boot:run
```

Hoặc đóng gói và chạy tên JAR thực tế của dự án:

```bash
java -jar app.jar
```

Các dòng kết quả chính dự kiến:

```text
itemPrice=12.50
retryCountByValue=4
firstGatewayByValue=primary
enabled=true
connectTimeout=PT3S
gateways=2
firstGatewayUrl=https://primary.example.test
standardQuota=50
```

Đây là dữ liệu không nhạy cảm dùng để minh họa; không in mật khẩu hoặc token khi thử nghiệm trong dự án thật.

### Bước 5 — thử thay đổi nguồn qua biến môi trường

Đối với thuộc tính `app.access.retry-count`, biến môi trường dạng canonical là:

```text
APP_ACCESS_RETRYCOUNT
```

Bash:

```bash
APP_ACCESS_RETRYCOUNT=9 java -jar app.jar
```

PowerShell:

```powershell
$env:APP_ACCESS_RETRYCOUNT = '9'
java -jar .\app.jar
```

Khi không có nguồn khác ưu tiên hơn, cả Binder và placeholder dạng canonical có thể nhận giá trị `9`.

Ví dụ này giúp thấy lợi ích của cách viết:

```java
@Value("${app.access.retry-count}")
```

thay vì buộc mã Java phụ thuộc vào cách viết `retryCount` theo camelCase.

### Bước 6 — thêm một gateway

Bổ sung phần tử:

```yaml
      - name: reporting
        url: https://reporting.example.test
        timeout: 10s
```

vào danh sách `gateways` trong đúng mức thụt lề YAML. Sau khi chạy lại ứng dụng, `AccessProperties.gateways()` có thể chứa ba phần tử mà không cần bổ sung một điểm tiêm mới cho từng trường.

Đây chính là sự khác biệt về khả năng mở rộng: **dữ liệu có thể thay đổi kích thước mà mô hình Java vẫn giữ nguyên**.

### Bước 7 — tăng số lượng gói quota

Thêm trong `quotas`:

```yaml
      enterprise:
        max-requests: 5000
        window: 10m
```

Khi binder nhận cấu hình mới, `access.quotas()` có thêm entry `enterprise`. Nếu dùng nhiều `@Value` riêng lẻ, bạn sẽ phải tạo code bổ sung để truy cập khóa mới, hoặc tự xây dựng cơ chế đọc động.

## 17. Có khi nào vẫn nên dùng `@Value`?

Có. Không nên cực đoan rằng mọi lần đọc cấu hình đều phải tạo một class `@ConfigurationProperties`.

Ví dụ `@Value` phù hợp:

- Một bean nhỏ cần một chuỗi đã biết như tên bucket thử nghiệm, cờ đơn giản hoặc timeout.
- Một cấu hình dùng tại đúng một vị trí, không có cấu trúc lồng.
- Một biểu thức SpEL thật sự cần thiết, ví dụ tính toán hoặc truy cập một bean theo quy tắc của Spring Framework.
- Một tham số đơn lẻ trong một phương thức `@Bean` cấu hình thành phần bên thứ ba.

Ví dụ:

```java
@Configuration
class HttpClientSetup {

    @Bean
    MyClient myClient(
            @Value("${app.client.base-url}") String baseUrl
    ) {
        return new MyClient(baseUrl);
    }
}
```

Ở đây `MyClient` là lớp minh họa do dự án hoặc thư viện cung cấp. Khi chỉ có một khóa rõ nghĩa, việc thêm class cấu hình mới có thể không cần thiết.

Nhưng nếu `MyClient` cần `baseUrl`, `readTimeout`, `connectTimeout`, `retryCount`, danh sách header, proxy và TLS, việc tạo một nhóm `@ConfigurationProperties` thường có lợi hơn.

Một lựa chọn trung gian là tiêm `Environment` khi bạn thật sự cần tra cứu khóa được quyết định lúc chạy:

```java
@Service
class DynamicLookupService {

    private final Environment environment;

    DynamicLookupService(Environment environment) {
        this.environment = environment;
    }

    String getLabel(String name) {
        return environment.getProperty("app.labels." + name);
    }
}
```

Đây là ví dụ cho **tra cứu động**, không phải thay thế chung cho type-safe binding. Với tên khóa do đầu vào bên ngoài quyết định, cần kiểm soát đầu vào và không để người gọi tự do truy cập bí mật cấu hình.

## 18. Các lỗi phổ biến khi dùng `@Value`

| Biểu hiện | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| Biến môi trường đã đặt nhưng `@Value` không nhận | Placeholder không dùng canonical form | Viết `${app.item-price}` thay vì `${app.itemPrice}` nếu khóa canonical là `item-price` |
| Đọc được `list[0]` nhưng không có `List<...>` | Placeholder chỉ truy cập một phần tử | Dùng `@ConfigurationProperties` cho danh sách |
| `@Value("${app.map}")` không tạo Map | Không có một khóa scalar chứa toàn bộ Map | Dùng Binder để liên kết các khóa con |
| JSON/SpEL có dấu nháy phức tạp làm lỗi | Ghép chuỗi vào biểu thức thủ công | Dùng typed configuration thay vì chuỗi SpEL lồng nhau |
| Bean báo thiếu placeholder | Khóa không có giá trị hoặc viết sai tên | Kiểm tra nguồn, tên chuẩn và mặc định phù hợp |
| Chuyển chuỗi sang số/Duration thất bại | Giá trị sai kiểu hoặc không có converter | Sửa giá trị nguồn, khai báo kiểu rõ, thêm validation |
| Giá trị `@Value` khác trong YAML | Nguồn khác ưu tiên cao hơn | Kiểm tra profile, biến môi trường, JVM và đối số |
| Cấu hình danh sách theo profile mất các phần tử cũ | Binder thay toàn bộ list từ nguồn ưu tiên cao | Khai báo danh sách hoàn chỉnh cho profile hoặc thiết kế lại |
| `Map` mất dấu `/` trong key | Chưa dùng bracket notation | Dùng `[/key]` hoặc YAML `"[/key]"` |
| IDE không gợi ý khóa tự định nghĩa | Chỉ dùng `@Value`, thiếu metadata | Gom cấu hình vào `@ConfigurationProperties`, cấu hình processor |
| Field injection khó test | Bean bị ràng buộc với Spring context | Ưu tiên constructor injection hoặc bean cấu hình |
| Có giá trị nhưng nghiệp vụ vẫn sai | Thiếu validation nhóm cấu hình | Áp dụng `@Validated` và ràng buộc phù hợp |

### 18.1. Khi chẩn đoán, phân biệt lỗi tên và lỗi ưu tiên

Ví dụ:

```properties
app.client.connect-timeout=3s
```

Và:

```bash
java -jar app.jar --app.client.connect-timeout=8s
```

Nếu ứng dụng nhận `8s`, đó là **quy tắc ưu tiên nguồn** chứ không phải lỗi liên kết tên. Nhưng nếu biến môi trường `APP_CLIENT_CONNECTTIMEOUT` có mặt mà placeholder camelCase không nhận, có thể là do **cách viết placeholder**.

Phân biệt đúng nguyên nhân giúp tránh đổi nhầm định dạng tệp hoặc thêm các khóa trùng nhau để “sửa” một vấn đề khác.

### 18.2. Quan sát giá trị cuối bằng `Environment`

Trong một bean ở môi trường thử nghiệm:

```java
@Bean
ApplicationRunner inspect(Environment env) {
    return args -> {
        System.out.println(
                env.getProperty("app.access.retry-count")
        );
    };
}
```

Đây là phương thức `@Bean` đặt bên trong lớp `@Configuration` hoặc `@SpringBootApplication`, không phải chương trình Java độc lập. Nó giúp bạn quan sát một khóa. Khi cần tìm nguyên nhân, có thể kết hợp với actuator `env` và `configprops` nếu dự án đã bật và bảo vệ những endpoint thích hợp.

**Lưu ý bảo mật:** không hiển thị bí mật trong log hoặc mở actuator endpoints nhạy cảm cho truy cập công khai. Endpoint chẩn đoán có thể làm lộ cấu trúc và metadata cấu hình nếu không có giới hạn phù hợp.

## 19. Cách chuyển từ nhiều `@Value` sang một model có kiểu

Một mã ban đầu có thể như:

```java
@Service
public class MailSender {

    @Value("${app.mail.host}")
    private String host;

    @Value("${app.mail.port:25}")
    private int port;

    @Value("${app.mail.retry-count:3}")
    private int retryCount;

    @Value("${app.mail.from-address}")
    private String fromAddress;
}
```

Với số lượng giá trị tăng, muốn sửa tên prefix phải sửa từng điểm tiêm. Hãy nhóm thành:

```java
package example.mail;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "app.mail")
public record MailProperties(
        String host,
        @DefaultValue("25") int port,
        @DefaultValue("3") int retryCount,
        String fromAddress
) {
}
```

Sau khi đăng ký bằng `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties`, đổi bean thành constructor injection:

```java
@Service
public class MailSender {

    private final MailProperties config;

    public MailSender(MailProperties config) {
        this.config = config;
    }

    // Khi gửi mail, sử dụng config.host(), config.port(), ...
}
```

Khi ứng dụng tăng thêm cấu hình người nhận, TLS hoặc nhóm kết nối, bạn có thể mở rộng `MailProperties` thay vì gắn thêm hàng loạt `@Value` vào bean xử lý nghiệp vụ.

Cách chuyển đổi thực hành:

1. Liệt kê những khóa `@Value` đang dùng trong cùng nhóm chức năng.
2. Chuẩn hóa tên canonical (`app.mail.retry-count`) và prefix (`app.mail`).
3. Tạo kiểu `@ConfigurationProperties` có các trường tương ứng.
4. Đưa default về model cấu hình hoặc tài liệu cấu hình, theo quy ước dự án.
5. Thêm validation nếu có ràng buộc nghiệp vụ.
6. Đăng ký bean cấu hình.
7. Tiêm model cấu hình vào những bean đang dùng các giá trị đó.
8. Chạy ứng dụng với cấu hình mặc định và một cấu hình theo profile để quan sát giá trị thực tế.

Không nên tạo hai mô hình cạnh tranh — một nửa cấu hình nằm trong nhiều `@Value`, nửa còn lại trong `@ConfigurationProperties` — nếu các giá trị thuộc cùng một đối tượng nghiệp vụ.

## 20. Kiểm tra kiến thức qua các tình huống

### Tình huống 1 — cách viết tên khóa

Có các nguồn:

```properties
demo.itemPrice=14.50
```

hoặc:

```text
DEMO_ITEMPRICE=14.50
```

Bạn có hai điểm tiêm:

```java
@Value("${demo.item-price}")
BigDecimal a;
```

```java
@Value("${demo.itemPrice}")
BigDecimal b;
```

**Câu hỏi:** Cách viết nào được Spring Boot khuyến nghị khi cần áp dụng logic relaxed lookup tương thích với Binder?

**Đáp án:** `${demo.item-price}`, vì đó là dạng canonical kebab-case. `${demo.itemPrice}` không nên được giả định nhận đủ những biến thể `demo.item-price` và `DEMO_ITEMPRICE`.

### Tình huống 2 — YAML list

```yaml
app:
  regions:
    - apac
    - eu
```

**Câu hỏi:** Vì sao không nên mặc định rằng `@Value("${app.regions}") List<String>` luôn làm việc như `@ConfigurationProperties`?

**Đáp án:** Dữ liệu YAML list thường được biểu diễn bằng các khóa có chỉ số khi tạo thuộc tính, không nhất thiết có một scalar `app.regions` để placeholder chuyển đổi. Binder có cơ chế đọc toàn bộ danh sách; `@Value` không tự cung cấp cùng khả năng đó.

### Tình huống 3 — danh sách đối tượng

```yaml
app:
  nodes:
    - host: a.example.test
      weight: 3
    - host: b.example.test
      weight: 1
```

**Câu hỏi:** Mô hình nào hợp lý?

**Đáp án:**

```java
@ConfigurationProperties(prefix = "app")
public record AppProperties(List<Node> nodes) {
    public record Node(String host, int weight) {}
}
```

Vì số phần tử và cấu trúc có thể thay đổi mà không cần thêm code `@Value` cố định theo chỉ số.

### Tình huống 4 — Map với ký tự đặc biệt

```yaml
app:
  labels:
    "[/core]": critical
```

**Câu hỏi:** Vì sao phải giữ `[/core]` dưới dạng key YAML có dấu nháy?

**Đáp án:** Bracket notation hướng dẫn Binder bảo toàn ký tự `/` trong khóa Map; YAML cần nháy khóa bracket để biểu diễn đúng.

### Tình huống 5 — CSV và YAML không phải một nguồn giống nhau

Nguồn A:

```properties
app.names=a,b,c
```

Nguồn B:

```yaml
app:
  names:
    - a
    - b
    - c
```

**Câu hỏi:** Nếu `@Value` chuyển được chuỗi của nguồn A thành `List<String>`, có được kết luận nó cũng tự liên kết dữ liệu nguồn B không?

**Đáp án:** Không. Nguồn A có một scalar CSV, nguồn B có cấu trúc YAML list. `@ConfigurationProperties` là lựa chọn ổn định hơn nếu muốn dữ liệu danh sách hỗ trợ nhiều định dạng.

### Tình huống 6 — danh sách bị ghi đè theo profile

Cấu hình chung có 2 node; tài liệu `dev` chỉ khai báo 1 node. Binder cho `List<Node>` thường tạo danh sách nào trong `dev`?

**Đáp án:** Danh sách một phần tử từ nguồn ưu tiên cao, không tự nối thêm các phần tử từ danh sách chung. Tài liệu profile cần khai báo danh sách hoàn chỉnh theo yêu cầu.

### Tình huống 7 — tính năng SpEL

**Câu hỏi:** Nếu ứng dụng thật sự cần tính một biểu thức SpEL khi tạo bean, `@ConfigurationProperties` có thay thế trực tiếp `@Value("#{...}")` không?

**Đáp án:** Không. SpEL là khả năng của `@Value`, còn Binder của `@ConfigurationProperties` không xử lý biểu thức theo cùng cách. Hãy chọn theo nhu cầu thật sự; tránh dùng SpEL như một cách phức tạp để thay thế cấu hình có cấu trúc.

### Tình huống 8 — cấu hình có ràng buộc

Một dịch vụ yêu cầu `retry-count >= 0` và mọi gateway phải có URL. Chỉ đưa mặc định vào `@Value` đã đủ chưa?

**Đáp án:** Chưa. Mặc định chỉ giúp khi thiếu giá trị, không thay thế validation. Nên biểu diễn nhóm cấu hình có kiểu, thêm các ràng buộc Bean Validation tương ứng và xử lý lỗi cấu hình khi khởi động.

## 21. Quy tắc lựa chọn dành cho dự án

Khi thêm cấu hình, có thể dùng chuỗi câu hỏi:

```text
Chỉ một giá trị scalar độc lập?
      |
      +-- Có --> Có thể dùng @Value hoặc Environment
      |
      +-- Không
            |
            v
Nhiều trường có cùng prefix / cùng nghiệp vụ?
      |
      +-- Có --> @ConfigurationProperties
            |
            v
Có List / Map / object lồng nhau / validation?
      |
      +-- Có --> Ưu tiên @ConfigurationProperties
```

Các thực hành nên giữ:

1. Dùng **tên canonical kebab-case** cho khóa trong file và placeholder của `@Value`.
2. Không giả định `@Value` có **relaxed binding đầy đủ** như Binder.
3. Không dùng một placeholder để ngầm biến cả cây YAML thành đối tượng Java.
4. Với danh sách cấu hình, dùng `List<T>` được Binder liên kết; không hardcode các chỉ số bằng nhiều `@Value`.
5. Với `Map`, chú ý bracket notation khi khóa chứa ký tự đặc biệt.
6. Nếu cần SpEL thật sự, dùng `@Value` có chủ ý và tránh biểu thức không cần thiết.
7. Với nhóm thuộc tính, sử dụng `@ConfigurationProperties` và constructor injection để giảm sự phân tán.
8. Dùng default và validation như hai cơ chế khác nhau.
9. Kiểm tra nguồn cấu hình có hiệu lực trước khi kết luận lỗi nằm ở tên khóa.
10. Không in hoặc phơi bày thông tin bí mật khi chẩn đoán.

## 22. Tổng kết

Điều quan trọng nhất không phải là `@Value` có thể chuyển được bao nhiêu loại chuỗi, mà là **nó không có cùng mô hình liên kết cấu hình với `@ConfigurationProperties`**.

```text
@Value("${app.some-key}")
       |
       v
Giải quyết placeholder / SpEL
       |
       v
Chuyển giá trị cho một điểm tiêm
```

Trong khi đó:

```text
@ConfigurationProperties(prefix = "app")
       |
       v
Binder đọc một nhóm khóa theo prefix
       |
       +-- relaxed binding
       +-- kiểu dữ liệu đơn
       +-- List / Map
       +-- object lồng nhau
       +-- default / validation phù hợp
       |
       v
Một đối tượng Java cấu hình có kiểu
       |
       v
Các bean khác sử dụng qua DI
```

Trong Spring Boot 3.3, hãy xem `@Value` như công cụ tốt cho **một vài giá trị đơn lẻ hoặc SpEL**, còn `@ConfigurationProperties` là công cụ chủ đạo cho **cấu hình ứng dụng có cấu trúc**. Dùng placeholder canonical giúp `@Value` tránh lỗi liên kết tên, nhưng không biến nó thành Binder đầy đủ. Khi cấu hình phát triển thành danh sách, bản đồ, các đối tượng lồng và ràng buộc, hãy chuyển sang mô hình có kiểu để giảm việc sửa mã và tăng khả năng hiểu giá trị cuối cùng.

## Tài liệu tham khảo

- Spring Boot 3.3 Reference — Externalized Configuration, phần **@ConfigurationProperties vs. @Value**, **Relaxed Binding**, **Binding Maps**, **Merging Complex Types**: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- Spring Boot 3.3 Reference — Constructor Binding và Default Values: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- Spring Framework Reference — Using `@Value`: https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/value-annotations.html
