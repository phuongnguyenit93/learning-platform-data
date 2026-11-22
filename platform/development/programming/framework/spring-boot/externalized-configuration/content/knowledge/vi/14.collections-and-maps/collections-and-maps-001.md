# Liên kết mảng, List và Set từ properties hoặc YAML trong Spring Boot

## 1. Tổng quan

Khi cấu hình ứng dụng Spring Boot, một thuộc tính không phải lúc nào cũng là một giá trị đơn như `String`, `int` hoặc `Duration`. Có những nhóm giá trị tự nhiên cần một **collection**: danh sách máy chủ dự phòng, các CORS origin được cho phép, những tác vụ cần chạy, danh sách module kích hoạt, tập nhãn, hoặc danh sách endpoint của hệ thống phụ trợ.

Spring Boot hỗ trợ **type-safe configuration properties binding**: chuyển dữ liệu từ `application.properties`, `application.yml`, biến môi trường, system properties, command-line arguments và các nguồn cấu hình khác thành các kiểu Java có cấu trúc, trong đó có:

- Mảng: `String[]`, `int[]`, `URI[]` hoặc mảng object phù hợp.
- `java.util.List<T>`: collection có thứ tự và cho phép trùng phần tử.
- `java.util.Set<T>`: collection không chứa các phần tử trùng nhau theo quy tắc `equals`/`hashCode` của kiểu phần tử.
- Các collection chứa object lồng nhau, ví dụ `List<Server>`, `List<Duration>` hoặc `Set<Region>` khi converter và cơ chế binding phù hợp.

Ví dụ cấu hình:

~~~yaml
app:
  endpoints:
    - https://api-a.example.test
    - https://api-b.example.test
~~~

Được liên kết vào class:

~~~java
import java.net.URI;
import java.util.List;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app")
public record AppProperties(List<URI> endpoints) {
}
~~~

Nếu class đã được đăng ký đúng cơ chế configuration properties, `endpoints()` là một `List<URI>` gồm hai phần tử đã được chuyển đổi kiểu. Ứng dụng không cần tự đọc YAML hay tự tách chuỗi.

**Mục tiêu của bài:** hiểu cú pháp mảng/list/set trong `.properties` và YAML, cách Spring Boot binder làm việc với indexed properties và comma-separated values, những điểm khác nhau giữa `List` và `Set`, quy tắc ghi đè giữa các nguồn Config Data, và cách kiểm thử cấu hình collection.

## 2. Sơ đồ từ tệp cấu hình đến Java object

Luồng xử lý tổng quát:

~~~text
application.properties / application.yml
             +
biến môi trường, JVM properties, command line
             |
             v
      Spring Environment
       (PropertySources)
             |
             v
 Spring Boot ConfigurationProperties Binder
  - relaxed binding tên khóa
  - phân giải giá trị phù hợp
  - chuyển đổi kiểu phần tử
  - lắp ghép chỉ số collection
             |
             v
     Java properties object
    String[] / List<T> / Set<T>
             |
             v
        Service, Bean, Validator
~~~

Spring Boot không ràng buộc collection bằng cách hiểu YAML như code Java. YAML được đọc thành những property phù hợp, thường có **chỉ số** như `app.endpoints[0]` và `app.endpoints[1]`; Binder dùng các khóa đó để tạo collection tương ứng.

Cùng một target Java có thể được cung cấp từ nhiều cách biểu diễn:

~~~properties
app.endpoints[0]=https://api-a.example.test
app.endpoints[1]=https://api-b.example.test
~~~

hoặc:

~~~yaml
app:
  endpoints:
    - https://api-a.example.test
    - https://api-b.example.test
~~~

hoặc trong những trường hợp converter hỗ trợ giá trị phân tách bằng dấu phẩy:

~~~properties
app.endpoints=https://api-a.example.test,https://api-b.example.test
~~~

Các cách này có ý nghĩa tương tự trong tình huống list chuỗi/URI đơn giản, nhưng không hoàn toàn tương đương ở mọi tình huống: dấu phẩy bên trong một phần tử, object lồng nhau, shell quoting và cách Binder xử lý từng PropertySource có thể làm khác kết quả. Với collection phức tạp, dùng indexed properties hoặc YAML sequence thường rõ ràng hơn.

## 3. Chuẩn bị một configuration properties class

Ví dụ dùng Spring Boot 3.x và Java record:

~~~java
package com.example.catalog.config;

import java.net.URI;
import java.time.Duration;
import java.util.List;
import java.util.Set;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app")
public record AppProperties(
        String[] regions,
        List<URI> endpoints,
        Set<String> tags,
        List<RemoteServer> servers
) {
    public record RemoteServer(
            String name,
            URI baseUrl,
            Duration timeout
    ) {}
}
~~~

Đăng ký class bằng scanning:

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

`@ConfigurationPropertiesScan` quét các lớp có `@ConfigurationProperties` phù hợp theo package. Nếu các class ở ngoài package mặc định, có thể dùng `basePackages` hoặc `basePackageClasses`. Cũng có thể đăng ký tường minh bằng `@EnableConfigurationProperties(AppProperties.class)`.

Đối với record constructor-bound, không nên gắn `@Component` rồi kỳ vọng Spring dùng cơ chế constructor binding của configuration properties; component scanning thông thường tạo bean bằng cơ chế dependency injection khác.

Trong `application.yml`:

~~~yaml
app:
  regions:
    - ap-southeast-1
    - eu-west-1
  endpoints:
    - https://api-a.example.test
    - https://api-b.example.test
  tags:
    - inventory
    - catalog
  servers:
    - name: primary
      base-url: https://primary.example.test
      timeout: 2s
    - name: backup
      base-url: https://backup.example.test
      timeout: 5s
~~~

Sau binding:

- `regions()` là một mảng hai phần tử.
- `endpoints()` là `List<URI>` gồm hai URI.
- `tags()` là `Set<String>` gồm hai tag khác nhau.
- `servers()` là `List<RemoteServer>` gồm hai record, mỗi record chứa ba thành phần có kiểu riêng.

**Quan trọng:** bản thân một lớp được gắn `@ConfigurationProperties` vẫn phải được đăng ký thành bean trước khi có thể inject vào các service. Tài liệu tiếp tục dùng class này để minh họa nhiều dạng nguồn dữ liệu.

## 4. Liên kết mảng (`array`) từ `application.properties`

### 4.1. Dùng chỉ số `[0]`, `[1]`, ...

Ví dụ:

~~~properties
app.regions[0]=ap-southeast-1
app.regions[1]=eu-west-1
app.regions[2]=us-east-1
~~~

Tương ứng với target:

~~~java
@ConfigurationProperties(prefix = "app")
public record RegionProperties(String[] regions) {
}
~~~

Giá trị hiệu lực của `regions` là mảng ba phần tử theo thứ tự chỉ số:

~~~text
regions[0] = ap-southeast-1
regions[1] = eu-west-1
regions[2] = us-east-1
~~~

Chỉ số bắt đầu từ **0**. Cách đặt `[0]` rồi `[2]` nhưng thiếu `[1]` có thể tạo lỗi binding hoặc kết quả không mong muốn; khi khai báo một danh sách bằng chỉ số, hãy dùng các chỉ số liên tục.

### 4.2. Dùng giá trị phân tách dấu phẩy

Với collection đơn giản, có thể viết:

~~~properties
app.regions=ap-southeast-1,eu-west-1,us-east-1
~~~

Spring Boot Binder có khả năng chuyển đổi chuỗi phân tách dấu phẩy thành mảng hoặc collection các giá trị tương ứng. Tuy nhiên, khi một phần tử **tự chứa dấu phẩy**, cách viết này dễ tạo nhầm lẫn về ranh giới phần tử. Lúc đó, nên dùng dạng indexed.

### 4.3. Mảng kiểu số

Ví dụ:

~~~properties
app.retry.delays[0]=100
app.retry.delays[1]=250
app.retry.delays[2]=500
~~~

Target:

~~~java
@ConfigurationProperties(prefix = "app.retry")
public record RetryProperties(int[] delays) {
}
~~~

Binder cần chuyển mỗi phần tử thành số nguyên hợp lệ. Nếu phần tử chứa chuỗi như `fast`, binding có thể thất bại. Dùng kiểu `long[]` nếu miền giá trị vượt phạm vi `int`; với thời gian thực tế, `Duration[]` hoặc `List<Duration>` thường rõ nghĩa hơn vì có đơn vị đo.

### 4.4. Mảng object

Một số trường hợp có thể bind mảng các object, chẳng hạn `Server[]`. Tuy nhiên, mảng có độ dài cố định và khả năng thao tác collection kém linh hoạt hơn `List<Server>`. Với configuration properties phức tạp, `List<T>` thường là lựa chọn dễ phát triển và kiểm thử.

## 5. Liên kết `List<T>` từ properties

### 5.1. Danh sách chuỗi

~~~properties
app.allowed-origins[0]=https://shop.example.test
app.allowed-origins[1]=https://admin.example.test
~~~

Target:

~~~java
import java.util.List;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app")
public record WebProperties(List<String> allowedOrigins) {
}
~~~

Khi bind thành công, danh sách có thứ tự:

~~~text
0 -> https://shop.example.test
1 -> https://admin.example.test
~~~

`List` phù hợp khi:

- thứ tự ưu tiên giữa các endpoint có ý nghĩa;
- phần tử trùng nhau có thể có ý nghĩa;
- cần truy cập phần tử theo vị trí hoặc lặp theo thứ tự khai báo;
- cấu hình chứa một chuỗi bước xử lý liên tiếp.

### 5.2. List chứa các kiểu số và `Duration`

~~~properties
app.retry.delays[0]=100ms
app.retry.delays[1]=500ms
app.retry.delays[2]=2s
~~~

Target:

~~~java
import java.time.Duration;
import java.util.List;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.retry")
public record RetryProperties(List<Duration> delays) {
}
~~~

Giá trị có thể nhận:

~~~text
[PT0.1S, PT0.5S, PT2S]
~~~

Các phần tử `100ms`, `500ms` và `2s` được chuyển sang `Duration` nhờ conversion của Spring Boot. Cách này rõ nghĩa hơn khai báo `List<Integer>` rồi ngầm hiểu đơn vị là millisecond.

### 5.3. List các object có nhiều trường

~~~properties
app.servers[0].name=primary
app.servers[0].base-url=https://primary.example.test
app.servers[0].timeout=2s

app.servers[1].name=backup
app.servers[1].base-url=https://backup.example.test
app.servers[1].timeout=5s
~~~

Target:

~~~java
import java.net.URI;
import java.time.Duration;
import java.util.List;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app")
public record ServerCatalog(List<Server> servers) {
    public record Server(String name, URI baseUrl, Duration timeout) {}
}
~~~

Ở đây `[0]` và `[1]` xác định các phần tử, còn `.name`, `.base-url` và `.timeout` là các field của từng object.

Đây là một ưu điểm quan trọng của indexed properties so với một chuỗi dài phân tách dấu phẩy: mỗi phần tử có thể mang cả một cấu trúc bean/record.

### 5.4. List chứa enum

Ví dụ:

~~~java
public enum AlertChannel {
    EMAIL, SMS, WEBHOOK
}
~~~

~~~java
@ConfigurationProperties(prefix = "alerts")
public record AlertProperties(List<AlertChannel> channels) {
}
~~~

~~~properties
alerts.channels[0]=email
alerts.channels[1]=webhook
~~~

Spring Boot có cơ chế chuyển đổi enum cho nhiều cách viết thông dụng. Tuy nhiên, nếu giá trị không khớp một hằng enum hỗ trợ, binding có thể thất bại. Không nên coi một chuỗi tùy ý là enum hợp lệ chỉ vì Binder hỗ trợ relaxed naming.

## 6. YAML sequence cho mảng và List

YAML biểu diễn danh sách bằng dấu `-`:

~~~yaml
app:
  regions:
    - ap-southeast-1
    - eu-west-1
    - us-east-1
~~~

Hoặc dạng inline:

~~~yaml
app:
  regions: [ap-southeast-1, eu-west-1, us-east-1]
~~~

Khi Spring Boot nạp Config Data từ YAML, các phần tử được biểu diễn thành các property tương ứng như `app.regions[0]`, `app.regions[1]` và `app.regions[2]`. Từ đó, Binder có thể tạo `String[]` hoặc `List<String>`.

### 6.1. YAML list chứa object

~~~yaml
app:
  servers:
    - name: primary
      base-url: https://primary.example.test
      timeout: 2s
    - name: backup
      base-url: https://backup.example.test
      timeout: 5s
~~~

Cách viết YAML này tương đương về ý nghĩa với các khóa indexed `app.servers[0].name`, `app.servers[1].name`, v.v.

Cần dùng indentation **nhất quán**; những dòng thuộc cùng một phần tử phải nằm dưới dấu `-` tương ứng. Trong `application.properties`, indentation không tạo cấu trúc lồng nhau; cú pháp indexed mới là yếu tố quyết định.

### 6.2. Quote cho phần tử chứa ký tự đặc biệt

Ví dụ:

~~~yaml
app:
  patterns:
    - "type:order"
    - "origin,region"
    - "#internal"
    - "https://api.example.test/v1?mode=fast"
~~~

Đây là bốn phần tử chuỗi. Trong YAML, ký tự `#` có thể bắt đầu comment ở vị trí thích hợp, dấu `:` có ý nghĩa đặc biệt trong một số ngữ cảnh, và `,` có ý nghĩa trong flow sequence. Đặt quote giúp parser giữ chuỗi theo đúng ý định.

Đối với `.properties`, một phần tử chứa dấu phẩy nên khai báo bằng chỉ số thay vì dùng giá trị tổng hợp phân tách dấu phẩy:

~~~properties
app.patterns[0]=type:order
app.patterns[1]=origin,region
app.patterns[2]=#internal
~~~

Trong ví dụ này, dấu `#` nằm sau dấu `=` nên thuộc giá trị; nó không phải comment cuối dòng. Nếu cần literal có backslash hoặc newline, xem thêm quy tắc escape riêng của định dạng properties.

### 6.3. Không nhầm YAML scalar với YAML sequence

Hai cấu hình này không phải một dạng dữ liệu YAML giống hệt nhau:

~~~yaml
app:
  hosts: "host-a,host-b"
~~~

và:

~~~yaml
app:
  hosts:
    - host-a
    - host-b
~~~

Dạng thứ nhất là **scalar string** chứa dấu phẩy. Spring Boot Binder có thể tách nó để bind vào collection tùy converter. Dạng thứ hai là **YAML sequence** hai phần tử, được mô hình hóa thành indexed properties rõ ràng.

Nếu muốn đảm bảo ranh giới phần tử ở cấp YAML, dùng sequence.

## 7. Liên kết `Set<T>`: đặc trưng và khác biệt với List

`Set` là collection không chứa các phần tử trùng nhau theo quan hệ bằng nhau của kiểu phần tử. Ví dụ:

~~~java
import java.util.Set;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app")
public record FeatureProperties(Set<String> tags) {
}
~~~

Cấu hình:

~~~yaml
app:
  tags:
    - catalog
    - inventory
    - catalog
~~~

Về ý nghĩa của một `Set<String>`, phần tử `catalog` lặp lại không cần tồn tại hai lần. Object sau khi bind chỉ biểu diễn tập các giá trị duy nhất theo quy tắc `String.equals`.

### 7.1. So sánh `String[]`, `List<String>` và `Set<String>`

| Tiêu chí | `String[]` | `List<String>` | `Set<String>` |
| --- | --- | --- | --- |
| Giữ thứ tự theo chỉ số | Có | Có | Không nên dựa vào thứ tự nếu không có contract rõ |
| Cho phép phần tử trùng | Có | Có | Không |
| Truy cập theo chỉ số | Có | Có | Không |
| Kích thước sau khi tạo | Cố định | Có thể thay đổi với implementation mutable | Có thể thay đổi với implementation mutable |
| Thích hợp khi | API cần array | Danh sách endpoint, bước chạy, ưu tiên | Tag, tập quyền, giá trị duy nhất |
| Cấu hình từ YAML sequence | Có thể | Có thể | Có thể |

**Không chọn `Set` nếu thứ tự là yêu cầu nghiệp vụ.** Dù một implementation Set có thể giữ insertion order trong một số trường hợp, contract chung của `Set` không buộc mọi implementation phải bảo đảm trình tự. Khi cần vị trí và độ ưu tiên, dùng `List`.

### 7.2. Duplicates trong `Set`

~~~properties
app.tags[0]=catalog
app.tags[1]=inventory
app.tags[2]=catalog
~~~

Binder chuyển giá trị thành Set; phần tử trùng theo `equals` không còn được biểu diễn lặp. Nếu ứng dụng cần phát hiện việc khai báo trùng để báo lỗi cấu hình, việc bind thẳng vào Set có thể khiến dấu hiệu trùng bị mất.

Một phương án là bind thành `List<String>`, kiểm tra duplicate trong validation, rồi chuyển thành Set khi sử dụng nếu hợp lệ.

### 7.3. Set của object phức tạp

`Set<MyType>` sử dụng `equals` và `hashCode` của `MyType` để xác định trùng phần tử. Nếu `MyType` là một class Java thông thường không override hai phương thức này, hai object có cùng nội dung vẫn có thể được coi là khác nhau. Record thường cung cấp value-based `equals`/`hashCode` cho các component.

Vì thế, khi bind `Set<Server>`, cần xác định thật sự muốn “trùng” theo những field nào. Nếu muốn giữ mọi object theo thứ tự cấu hình, `List<Server>` thường ít gây bất ngờ hơn.

### 7.4. Một số field phù hợp với Set

- Danh sách nhãn bật tính năng, nếu thứ tự không quan trọng.
- Tập tên namespace hoặc region duy nhất.
- Các kiểu mã định danh không trùng được.
- Tập permission/role trong một cấu hình tĩnh, với giả định không dùng Set như cơ chế bảo mật tự thân.

Dù sử dụng Set, cần validation nếu yêu cầu không rỗng, không có phần tử blank hoặc chỉ nhận một nhóm giá trị hợp lệ.

## 8. Kiểu collection trong JavaBean setter binding

Không nhất thiết dùng record. Có thể tạo JavaBean có setter và đăng ký bằng `@Component`:

~~~java
package com.example.catalog.config;

import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

@Component
@ConfigurationProperties(prefix = "app")
public class AppCollectionProperties {

    private List<String> hosts = new ArrayList<>();
    private Set<String> tags = new LinkedHashSet<>();

    public List<String> getHosts() {
        return hosts;
    }

    public void setHosts(List<String> hosts) {
        this.hosts = hosts;
    }

    public Set<String> getTags() {
        return tags;
    }

    public void setTags(Set<String> tags) {
        this.tags = tags;
    }
}
~~~

Cấu hình:

~~~properties
app.hosts[0]=host-a.example.test
app.hosts[1]=host-b.example.test
app.tags[0]=catalog
app.tags[1]=search
~~~

Spring tạo JavaBean qua component scanning, sau đó Binder gán các collection tương ứng. Việc khởi tạo trước `new ArrayList<>()` hoặc `new LinkedHashSet<>()` giúp class có trạng thái mặc định rõ ràng ngay cả khi không có khóa tương ứng.

### 8.1. Có nhất thiết cần setter?

Với những collection đã được khởi tạo sẵn và có thể thay đổi, Spring Boot có thể bind thông qua getter trong một số tình huống. Tuy nhiên, để JavaBean dễ hiểu và tránh phụ thuộc chi tiết về mutability, hãy khai báo getter/setter thích hợp khi chọn mô hình mutable setter binding.

Đừng cho rằng mọi collection `final`, immutable list hoặc instance do `List.of()` tạo đều có thể được Binder cập nhật tại chỗ. Nếu muốn bất biến sau khi tạo, constructor binding/record là một lựa chọn có chủ đích hơn.

### 8.2. Tránh mutable configuration bị thay đổi sau startup

Nếu bean singleton trả về `List<String>` mutable, service khác có thể thực hiện:

~~~java
properties.getHosts().clear();
~~~

Lệnh này đổi trạng thái runtime của bean cấu hình, không phải cập nhật property source và không được bảo đảm an toàn trong môi trường nhiều luồng.

Nếu không muốn consumer thay đổi dữ liệu:

~~~java
public List<String> hostsView() {
    return List.copyOf(hosts);
}
~~~

Hoặc thiết kế record có compact constructor tạo bản sao phòng thủ phù hợp. Cần chú ý rằng `List.copyOf` từ chối phần tử null; khi dữ liệu có thể chứa null thì phải có chính sách khác.

Spring Boot không tự bật live reload chỉ vì collection có setter; thay đổi `application.yml` khi ứng dụng chạy thường cần restart hoặc cơ chế refresh được thiết kế riêng.

## 9. Constructor binding và collection trong record

Record phù hợp để diễn tả dữ liệu cấu hình immutable về **tham chiếu**:

~~~java
import java.util.List;
import java.util.Set;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "catalog")
public record CatalogProperties(
        List<String> categories,
        Set<String> tags
) {
}
~~~

Có thể khai báo constructor compact để bảo vệ khỏi việc consumer sửa collection sau khi bind:

~~~java
@ConfigurationProperties(prefix = "catalog")
public record CatalogProperties(
        List<String> categories,
        Set<String> tags
) {
    public CatalogProperties {
        categories = categories == null ? List.of() : List.copyOf(categories);
        tags = tags == null ? Set.of() : Set.copyOf(tags);
    }
}
~~~

Ví dụ này cung cấp **chính sách ứng dụng**: khi collection không được cấu hình, sử dụng collection rỗng; khi có, tạo bản sao unmodifiable. Tuy nhiên:

- `List.copyOf` và `Set.copyOf` không chấp nhận phần tử null.
- `Set.copyOf` loại các phần tử trùng và không cam kết duy trì thứ tự duyệt theo cách mà mọi consumer có thể dựa vào.
- Copy các collection ngoài không tự deep-copy những object mutable nằm bên trong.

Nếu cần ràng buộc danh sách không được trống, hãy dùng validation thay vì mặc định thành `List.of()`.

### 9.1. Khi collection thiếu hoàn toàn

Nếu không có `catalog.categories` trong bất kỳ nguồn cấu hình nào, giá trị constructor binding phụ thuộc cơ chế Binder và default phù hợp của target. Với record component kiểu collection, cần tránh tự giả định “chắc chắn là danh sách rỗng” ở tất cả phiên bản/cách binding.

Có thể thiết kế rõ fallback bằng constructor như ví dụ hoặc dùng cơ chế default được Spring Boot hỗ trợ cho constructor binding. Nếu danh sách là bắt buộc, dùng Bean Validation để phát hiện thiếu hoặc rỗng.

### 9.2. Kết hợp với `@DefaultValue`

`@DefaultValue` hỗ trợ default cho tham số constructor binding; cách sử dụng có thể khác nhau giữa scalar, nested object và collection tùy phiên bản Boot và conversion. Không nên tự suy ra rằng `@DefaultValue("a,b")` luôn tương đương YAML sequence hai phần tử trong mọi ngữ cảnh phức tạp.

Đối với collection phức tạp, một giá trị mặc định được khai báo trong `application.yml` hoặc logic constructor rõ ràng thường dễ theo dõi hơn việc nhét nhiều dữ liệu vào một annotation.

## 10. Tên property, relaxed binding và chỉ số

Spring Boot Binder hỗ trợ **relaxed binding** đối với tên property. Ví dụ Java field `allowedOrigins` có thể được liên kết với tên canonical `allowed-origins`:

~~~properties
app.allowed-origins[0]=https://a.example.test
app.allowed-origins[1]=https://b.example.test
~~~

Với Java:

~~~java
@ConfigurationProperties(prefix = "app")
public record WebProperties(List<String> allowedOrigins) {
}
~~~

Trong YAML:

~~~yaml
app:
  allowed-origins:
    - https://a.example.test
    - https://b.example.test
~~~

### 10.1. Indexed environment variables

Trong biến môi trường, dấu chấm thường đổi thành underscore, dấu gạch nối bị loại bỏ, tên được viết hoa, và index của list thường đặt giữa dấu underscore.

Ví dụ với Java record:

~~~java
@ConfigurationProperties(prefix = "app")
public record AppProperties(List<Client> remoteClients) {
    public record Client(String name, String url) {}
}
~~~

Dạng canonical:

~~~properties
app.remote-clients[0].name=primary
app.remote-clients[0].url=https://primary.example.test
app.remote-clients[1].name=backup
app.remote-clients[1].url=https://backup.example.test
~~~

Có thể biểu diễn bằng các biến môi trường theo quy tắc của Boot:

~~~text
APP_REMOTECLIENTS_0_NAME=primary
APP_REMOTECLIENTS_0_URL=https://primary.example.test
APP_REMOTECLIENTS_1_NAME=backup
APP_REMOTECLIENTS_1_URL=https://backup.example.test
~~~

Dạng có `_0_` và `_1_` tương ứng các chỉ số collection. Với nhiều công cụ triển khai, dùng YAML hoặc file properties cho danh sách object dài sẽ dễ đọc và ít lỗi hơn việc đặt nhiều biến môi trường.

### 10.2. Một biến môi trường phân tách bằng dấu phẩy

Với danh sách đơn giản:

~~~bash
APP_REGIONS=ap-southeast-1,eu-west-1 java -jar app.jar
~~~

Khi Binder cần `List<String>` hoặc `String[]` tại `app.regions`, giá trị có thể được chuyển thành collection. Tính năng này tiện cho collection ngắn nhưng khó biểu diễn phần tử chứa dấu phẩy hoặc object có nhiều field.

Trên Windows PowerShell, không dùng cú pháp gán biến Linux trước command; thay bằng cách đặt `$env:APP_REGIONS` thích hợp.

### 10.3. Không coi tên bean field là khóa đầy đủ

Một field `List<String> hosts` nằm trong `@ConfigurationProperties(prefix = "app.client")` tương ứng với `app.client.hosts`, không tự tương ứng với `hosts` ở root. Kiểm tra cả prefix lẫn tên field khi binding thất bại.

## 11. Khi cấu hình nằm ở nhiều nguồn: List được thay thế, không được cộng dồn

Đây là quy tắc đặc biệt quan trọng trong **Spring Boot Externalized Configuration**:

> Khi `List` được khai báo ở nhiều property sources, Spring Boot Binder thường **chọn danh sách từ nguồn có độ ưu tiên cao hơn**; nó không tự ghép các phần tử của mọi nguồn để tạo một danh sách tổng hợp.

Ví dụ file cơ sở:

~~~yaml
# application.yml
app:
  servers:
    - name: api-a
      base-url: https://a.example.test
      timeout: 2s
    - name: api-b
      base-url: https://b.example.test
      timeout: 3s
~~~

File profile-specific:

~~~yaml
# application-prod.yml
app:
  servers:
    - name: api-prod
      base-url: https://prod.example.test
      timeout: 5s
~~~

Khi profile `prod` được kích hoạt và nguồn này có độ ưu tiên cao hơn trong tình huống nạp thông thường, kết quả ở `app.servers` là **danh sách một phần tử** `api-prod`. Hai server từ file cơ sở không được tự động giữ lại.

Cần đối chiếu:

~~~text
Base list:     [api-a, api-b]
Prod list:     [api-prod]
Effective:     [api-prod]
NOT:           [api-a, api-b, api-prod]
~~~

### 11.1. Ghi đè từng field không có nghĩa merge từng phần tử

Giả sử:

~~~yaml
# application.yml
app:
  servers:
    - name: primary
      base-url: https://primary.example.test
      timeout: 2s
~~~

và:

~~~yaml
# application-prod.yml
app:
  servers:
    - name: prod-primary
~~~

Đừng kỳ vọng `base-url` và `timeout` của phần tử cũ tự được merge vào phần tử mới theo cùng vị trí 0. Với quy tắc list replacement, phần tử từ nguồn ưu tiên cao hơn có thể chỉ có `name=prod-primary`, còn các field không khai báo có thể nhận null/default/giá trị khác tùy kiểu Java và logic khởi tạo.

Nếu một phần tử list có các field bắt buộc, khai báo đủ các field trong source thay thế và dùng validation. Việc chỉ override một field ở index 0 không phải cơ chế patch an toàn cho list.

### 11.2. Không dùng thêm `[1]` ở source ưu tiên cao để “append”

Ví dụ file cơ sở có `app.servers[0]` và `app.servers[1]`; nguồn bên ngoài có `app.servers[2]`. Đừng giả định nguồn bên ngoài có thể nối phần tử thứ ba vào cuối danh sách cũ. Theo quy tắc replacement, chỉ số thiếu liên tục ở một source có thể làm binding không như mong đợi.

Nếu muốn append động, cần thiết kế một cơ chế cấu hình riêng, ví dụ merge list rõ ràng trong code, hoặc sử dụng `Map` cho các mục có định danh ổn định. Không coi Config Data Binder là công cụ JSON Patch.

## 12. `Map` khác `List` trong việc kết hợp nhiều nguồn

Mặc dù bài này tập trung vào array/List/Set, sự khác biệt với Map rất quan trọng vì đây là nguyên nhân thường gặp gây hiểu nhầm.

Ví dụ:

~~~yaml
# application.yml
app:
  clients:
    primary:
      url: https://primary.example.test
      timeout: 2s
    backup:
      url: https://backup.example.test
      timeout: 3s
~~~

Nguồn ưu tiên cao hơn:

~~~yaml
# application-prod.yml
app:
  clients:
    primary:
      timeout: 5s
~~~

Nếu target Java là một `Map<String, Client>` phù hợp, Binder có thể kết hợp các **khóa Map** từ nhiều nguồn: `primary` vẫn tồn tại với cấu hình được ghi đè theo property tương ứng, `backup` vẫn tồn tại từ nguồn thấp hơn. Đây là hành vi khác về bản chất so với list replacement.

**Tóm tắt:**

- Với `List`, nguồn ưu tiên cao hơn thay thế toàn bộ danh sách về mặt binding.
- Với `Map`, các entry có thể được gom theo key và property cùng key được ưu tiên theo nguồn.
- Với `Set`, không nên xem việc chọn Set là cách tự động merge collection từ nhiều nguồn. Xác nhận hành vi cụ thể nếu ứng dụng dùng source chồng lấp, và thiết kế công khai chính sách thay thế thay vì dựa vào trùng phần tử.

Khi cần giữ các mục theo định danh ổn định giữa môi trường, `Map<String, Client>` thường là mô hình tốt hơn `List<Client>` với ý định chỉnh sửa một phần tử theo chỉ số.

## 13. Profile-specific files và danh sách

Ví dụ file cơ sở:

~~~properties
# application.properties
app.allowed-origins[0]=https://dev.example.test
app.allowed-origins[1]=https://preview.example.test
~~~

File dành cho profile production:

~~~properties
# application-prod.properties
app.allowed-origins[0]=https://shop.example.test
~~~

Trong tình huống profile `prod` được chọn và file profile-specific có độ ưu tiên cao hơn, danh sách hiệu lực thường là:

~~~text
[https://shop.example.test]
~~~

Không phải:

~~~text
[https://shop.example.test, https://preview.example.test]
~~~

Các nguyên tắc tương tự áp dụng khi có file external với thứ tự ưu tiên cao hơn classpath hoặc import khác. Nhưng thứ tự nguồn chính xác còn phụ thuộc location groups, `spring.config.location`, `spring.config.additional-location`, `spring.config.import` và những nguồn ngoài Config Data.

### 13.1. Multi-document YAML

~~~yaml
app:
  modes:
    - standard
    - debug

---
spring:
  config:
    activate:
      on-profile: prod
app:
  modes:
    - standard
    - audit
~~~

Khi `prod` hoạt động và document tương ứng có độ ưu tiên cao hơn document cơ sở trong file này, list `app.modes` được lấy từ document `prod`. Không phải `[standard, debug, standard, audit]`.

### 13.2. Một file theo profile không có list

Nếu file `application-prod.yml` chỉ ghi đè một property hoàn toàn khác, `app.modes` từ file cơ sở vẫn có thể được sử dụng. “List replacement” xảy ra khi nguồn ưu tiên cao hơn **có đóng góp giá trị cho list đó**, không có nghĩa mọi list trong file cơ sở đều bị xóa khi bật profile.

## 14. Dấu phẩy bên trong phần tử và cách cấu hình an toàn

Một chuỗi cấu hình:

~~~properties
app.labels=type:order,region:asia
~~~

thường được hiểu là hai phần tử khi bind thành `List<String>`. Nếu ý định thực sự là **một phần tử** `type:order,region:asia`, cách này có thể gây sai.

Dùng indexed properties:

~~~properties
app.labels[0]=type:order,region:asia
~~~

Hoặc YAML sequence:

~~~yaml
app:
  labels:
    - "type:order,region:asia"
~~~

Điểm chính: khi phần tử có ký tự `,`, hãy biểu diễn ranh giới phần tử ở cấp định dạng file thay vì phó mặc cho converter của comma-separated string.

### 14.1. URL có dấu phẩy

Một số URL có query string hoặc path chứa dấu phẩy. Nếu dùng:

~~~properties
app.urls=https://example.test/search?q=a,b
~~~

và target là `List<URI>`, có khả năng dấu phẩy bị xem như dấu phân cách collection. Đừng kết luận sau khi nhìn chuỗi rằng đây chắc chắn là một URL duy nhất.

Cách rõ ràng:

~~~properties
app.urls[0]=https://example.test/search?q=a,b
~~~

Hoặc:

~~~yaml
app:
  urls:
    - "https://example.test/search?q=a,b"
~~~

### 14.2. Dấu cách quanh dấu phẩy

Khi viết:

~~~properties
app.regions=ap-southeast-1, eu-west-1
~~~

việc trim khoảng trắng phụ thuộc đường đi conversion và kiểu phần tử. Để tránh tạo giá trị `" eu-west-1"` ngoài ý định, viết nhất quán không có khoảng trắng khi dùng một scalar phân tách dấu phẩy, hoặc dùng YAML sequence. Không nên dựa vào việc mọi converter đều trim đúng như mình mong muốn.

## 15. Collection rỗng, không khai báo và `null`

Cần phân biệt ba trạng thái:

1. **Không có property**: không có khóa list trong bất kỳ source nào.
2. **Có collection rỗng**: ứng dụng chủ động muốn một tập/danh sách không phần tử.
3. **Có phần tử rỗng**: collection có phần tử là chuỗi rỗng, khác với không có phần tử.

Ví dụ YAML:

~~~yaml
app:
  tags: []
~~~

Đây là cú pháp YAML biểu diễn một sequence rỗng. Tuy nhiên, việc Binder quan sát sequence rỗng từ YAML thế nào cần xét các chi tiết flattening và phiên bản Boot; không nên dựa vào sự hiện diện của một sequence rỗng để khẳng định mọi target Java chắc chắn nhận `Set.of()`.

Trong Java:

~~~java
@ConfigurationProperties(prefix = "app")
public record TagProperties(Set<String> tags) {
    public TagProperties {
        tags = tags == null ? Set.of() : Set.copyOf(tags);
    }
}
~~~

Ví dụ này định nghĩa rõ fallback rỗng trong chính object. Nhưng nếu “không có tag” là lỗi cấu hình, hãy dùng validation thay vì biến trạng thái thiếu thành collection rỗng.

Đối với JavaBean:

~~~java
private List<String> hosts = new ArrayList<>();
~~~

Field initializer là một lựa chọn khác để biểu diễn default khi nguồn không cung cấp giá trị. Nó không đồng nghĩa Binder sẽ merge các giá trị list từ nhiều nguồn.

## 16. Validation cho List và Set

Spring Boot có thể tích hợp Jakarta Bean Validation khi cấu hình `@ConfigurationProperties` đã được đăng ký và có provider phù hợp, thường qua `spring-boot-starter-validation`.

Ví dụ:

~~~java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.Size;
import java.util.List;
import java.util.Set;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app")
public record AppProperties(
        @NotEmpty List<@NotBlank String> allowedOrigins,
        @Size(max = 10) Set<@NotBlank String> tags
) {}
~~~

Ý nghĩa:

- `@NotEmpty`: danh sách bắt buộc có ít nhất một phần tử.
- `@NotBlank` trên phần tử: mỗi chuỗi không được null/rỗng/toàn khoảng trắng.
- `@Size(max = 10)`: tập tag không được vượt quá 10 phần tử.
- Ký hiệu `List<@NotBlank String>` là **container element constraint**; cần Bean Validation implementation hỗ trợ.

Không nên chỉ kiểm tra `allowedOrigins != null`: một danh sách có một chuỗi rỗng vẫn có thể không phù hợp cho cấu hình CORS.

### 16.1. Validation object lồng nhau

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import java.net.URI;
import java.util.List;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app")
public record ServerProperties(
        @NotEmpty List<@Valid Server> servers
) {
    public record Server(
            @NotBlank String name,
            @NotNull URI baseUrl
    ) {}
}
~~~

Trong một dự án hoàn chỉnh, cần import `jakarta.validation.constraints.NotEmpty` phù hợp. `@Valid` trên phần tử giúp validation đi vào object `Server`; việc `baseUrl` là một `URI` không tự kiểm tra hostname có thật hoặc endpoint có phản hồi.

### 16.2. Kiểm tra phần tử trùng

Nếu cấu hình dùng `List<String>` nhưng yêu cầu tất cả phần tử là duy nhất, `@NotEmpty` không đủ. Có thể xây một custom Bean Validation constraint hoặc một invariant trong constructor/ứng dụng.

Đừng chuyển sang `Set` chỉ để “xóa trùng một cách im lặng” nếu việc khai báo trùng là lỗi cấu hình cần báo cho người triển khai.

## 17. Lỗi conversion của từng phần tử

Giả sử:

~~~properties
app.retry.delays[0]=100ms
app.retry.delays[1]=fast
app.retry.delays[2]=2s
~~~

Target là `List<Duration>`. Phần tử `fast` không có dạng Duration hợp lệ theo converter tương ứng, nên binding có thể báo lỗi. Tùy cấu trúc lỗi, Spring Boot cung cấp thông tin về property, index và giá trị không chuyển đổi được.

Tương tự:

~~~properties
app.ports[0]=8080
app.ports[1]=eight-thousand
~~~

với `List<Integer>` có thể thất bại ở chỉ số 1.

Việc đổi target sang `List<String>` giúp parse được chuỗi nhưng **không giải quyết yêu cầu dữ liệu phải hợp lệ**. Nếu port thật sự là số, giữ kiểu số và validation phù hợp để lỗi được phát hiện sớm.

Với array, list và set có object lồng nhau, lỗi có thể nằm ở một field sâu, ví dụ `app.servers[1].timeout`. Khi debug, nhìn đầy đủ tên property và chỉ số thay vì chỉ xem thông điệp chung “Failed to bind properties”.

## 18. `@Value` khác `@ConfigurationProperties` khi đọc danh sách

`@Value` rất tiện với một property đơn:

~~~java
@Value("${app.client.timeout:5s}")
private String timeout;
~~~

Với danh sách đơn giản được biểu diễn bằng một chuỗi dấu phẩy, một số trường hợp `@Value` và conversion service có thể xử lý:

~~~properties
app.regions=eu-west-1,ap-southeast-1
~~~

Nhưng với YAML sequence:

~~~yaml
app:
  regions:
    - eu-west-1
    - ap-southeast-1
~~~

các phần tử được flatten thành các khóa indexed như `app.regions[0]`, `app.regions[1]`. `@Value("${app.regions}")` không được bảo đảm nhận toàn bộ collection như Binder của `@ConfigurationProperties`.

Do đó, **ưu tiên `@ConfigurationProperties` cho array/List/Set**, nhất là khi:

- cần binding từ YAML sequence;
- có nested list của object;
- cần validation trên phần tử;
- cần hỗ trợ nhiều nguồn cấu hình với relaxed binding;
- muốn một object cấu hình tập trung, dễ kiểm thử.

Không cố ghép nhiều `@Value` theo chỉ số nếu danh sách có độ dài thay đổi. Khi dùng SpEL để tách chuỗi, dễ phát sinh phụ thuộc vào cú pháp string và không mô phỏng đầy đủ Binder.

## 19. Một ví dụ đầy đủ: danh sách upstream và tag

### 19.1. Cấu hình YAML

~~~yaml
# application.yml
gateway:
  upstreams:
    - name: catalog
      url: https://catalog.example.test
      timeout: 2s
    - name: payments
      url: https://payments.example.test
      timeout: 4s
  tags:
    - customer-facing
    - auditable
~~~

### 19.2. Record cấu hình

~~~java
package com.example.gateway.config;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import java.net.URI;
import java.time.Duration;
import java.util.List;
import java.util.Set;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "gateway")
public record GatewayProperties(
        @NotEmpty List<@Valid Upstream> upstreams,
        Set<@NotBlank String> tags
) {
    public record Upstream(
            @NotBlank String name,
            @NotNull URI url,
            @NotNull Duration timeout
    ) {}
}
~~~

### 19.3. Đăng ký

~~~java
package com.example.gateway;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class GatewayApplication {

    public static void main(String[] args) {
        SpringApplication.run(GatewayApplication.class, args);
    }
}
~~~

Với cấu trúc package trong ví dụ, `@ConfigurationPropertiesScan` tìm `GatewayProperties` thuộc package con `com.example.gateway.config`.

### 19.4. Sử dụng trong service

~~~java
import com.example.gateway.config.GatewayProperties;
import java.util.List;
import org.springframework.stereotype.Service;

@Service
public class GatewayRoutingService {

    private final GatewayProperties properties;

    public GatewayRoutingService(GatewayProperties properties) {
        this.properties = properties;
    }

    public List<String> targetNames() {
        return properties.upstreams().stream()
                .map(GatewayProperties.Upstream::name)
                .toList();
    }
}
~~~

`targetNames()` trả `["catalog", "payments"]` theo thứ tự danh sách. Còn `tags()` biểu diễn một tập các nhãn khác nhau.

Ví dụ service minh họa cách đọc cấu hình, không tự triển khai routing, retry hoặc request HTTP. Nếu nghiệp vụ cần ưu tiên upstream theo thứ tự, `List` là lựa chọn hợp lý hơn `Set`.

### 19.5. Tương đương bằng properties

~~~properties
gateway.upstreams[0].name=catalog
gateway.upstreams[0].url=https://catalog.example.test
gateway.upstreams[0].timeout=2s

gateway.upstreams[1].name=payments
gateway.upstreams[1].url=https://payments.example.test
gateway.upstreams[1].timeout=4s

gateway.tags[0]=customer-facing
gateway.tags[1]=auditable
~~~

Trong dự án có nhiều source, chọn một cách biểu diễn thống nhất cho từng danh sách để tránh cấu hình khó đọc, đặc biệt khi có profile overrides.

## 20. Kiểm thử binding collection

Có thể viết test trên Spring Boot application context để kiểm tra mảng, list và set đã được bind theo mong muốn.

Ví dụ giả sử `GatewayProperties` và `GatewayApplication` đã được định nghĩa như phần trên:

~~~java
package com.example.gateway;

import com.example.gateway.config.GatewayProperties;
import java.time.Duration;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(properties = {
    "gateway.upstreams[0].name=one",
    "gateway.upstreams[0].url=https://one.example.test",
    "gateway.upstreams[0].timeout=750ms",
    "gateway.upstreams[1].name=two",
    "gateway.upstreams[1].url=https://two.example.test",
    "gateway.upstreams[1].timeout=2s",
    "gateway.tags[0]=internal",
    "gateway.tags[1]=audit"
})
class GatewayPropertiesTest {

    @Autowired
    GatewayProperties properties;

    @Test
    void bindsIndexedCollections() {
        assertEquals(List.of("one", "two"),
                properties.upstreams().stream()
                        .map(GatewayProperties.Upstream::name)
                        .toList());

        assertEquals(Duration.ofMillis(750),
                properties.upstreams().get(0).timeout());

        assertTrue(properties.tags().contains("internal"));
        assertTrue(properties.tags().contains("audit"));
    }
}
~~~

Test này minh họa cấu hình indexed trong một nguồn property test. Với project thực, cần Spring Boot Test, JUnit, ứng dụng chính và cơ chế đăng ký `GatewayProperties` thích hợp.

### 20.1. Kiểm thử list replacement giữa profile

Có thể tạo hai file `application.yml` và `application-prod.yml` như ví dụ ở phần 11, chạy test với `@ActiveProfiles("prod")` và xác nhận chỉ còn danh sách từ nguồn ưu tiên cao hơn.

Cần lưu ý rằng test framework cũng cung cấp property sources riêng; nếu test đặt một phần danh sách qua `@SpringBootTest(properties=...)`, source test đó có thể có độ ưu tiên cao hơn file và làm kết quả khác tình huống deployment thật.

### 20.2. Kiểm thử Set không dựa trên iteration order

Nếu target là `Set<String>`, hãy so sánh tập giá trị:

~~~java
assertEquals(Set.of("internal", "audit"), properties.tags());
~~~

Không nên viết test yêu cầu `properties.tags().iterator().next()` luôn là `internal` trừ khi contract của ứng dụng chủ động quy định và bảo đảm thứ tự.

### 20.3. Kiểm thử validation

Với `@NotEmpty List<@Valid Upstream>`, thử danh sách rỗng hoặc một phần tử thiếu tên/URL để xác nhận ứng dụng báo lỗi startup. Đó là cách ghi nhận hợp đồng cấu hình bằng test thay vì để lỗi xuất hiện khi service sử dụng phần tử.

## 21. Chẩn đoán khi collection bind sai

Nếu cấu hình YAML hiển thị ba phần tử nhưng Java nhận `null`, một danh sách thiếu phần tử hoặc lỗi conversion:

1. **Kiểm tra bean có được đăng ký không.** `@ConfigurationProperties` một mình không luôn tạo bean; xem `@ConfigurationPropertiesScan`, `@EnableConfigurationProperties` hoặc `@Component` cho JavaBean phù hợp.
2. **Kiểm tra prefix.** Lớp khai báo `prefix = "gateway"` thì cần `gateway.upstreams`, không phải `app.upstreams`.
3. **Kiểm tra tên property canonical.** Ví dụ `remote-clients` với Java `remoteClients`; khi dùng env vars, tên chuyển đổi có quy tắc riêng.
4. **Kiểm tra YAML syntax.** Dấu `-`, indentation, quote và document separator phải đúng.
5. **Kiểm tra chỉ số.** Danh sách indexed nên bắt đầu từ 0 và liên tục.
6. **Kiểm tra có mix comma-separated và indexed trong các nguồn không.** Cách biểu diễn khác nhau có thể làm behavior khó suy luận, nhất là khi source override.
7. **Kiểm tra profile và document activation.** Property có thể nằm trong file `application-prod.yml` nhưng profile `prod` chưa active.
8. **Kiểm tra độ ưu tiên property sources.** Một file external hoặc command-line property có thể thay thế cả danh sách.
9. **Kiểm tra target type.** `List<Duration>` yêu cầu giá trị parse được thành Duration, `List<URI>` yêu cầu URI có cú pháp phù hợp.
10. **Kiểm tra nested type.** Nếu dùng JavaBean, getter/setter và cấu trúc object phải bind được; nếu dùng record, phải đăng ký theo cơ chế constructor binding phù hợp.
11. **Kiểm tra validation.** `@NotEmpty`, `@NotBlank`, `@Valid` có thể từ chối một collection vốn parse được nhưng không hợp lệ.
12. **Kiểm tra phần tử chứa dấu phẩy.** Chuyển sang dạng indexed hoặc YAML sequence nếu một phần tử bị tách thành nhiều phần.
13. **Kiểm tra ứng dụng đã restart chưa.** Spring Boot thông thường không tự rebind collection khi file thay đổi.
14. **Chỉ quan sát an toàn.** Không in các collection chứa token, credential, API key vào log.

Trong môi trường được bảo vệ, Spring Boot Actuator `/actuator/configprops` hoặc `/actuator/env` có thể giúp quan sát các property sources và binding; cần che giá trị nhạy cảm và hạn chế quyền truy cập.

## 22. Các tình huống thường gây nhầm lẫn

### 22.1. “List ở file prod sẽ nối thêm vào list ở file cơ sở”

Không. Quy tắc Spring Boot Binder cho List từ nhiều nguồn là replacement theo nguồn có độ ưu tiên cao hơn, không phải append.

### 22.2. “Ghi một index ở source cao hơn sẽ chỉ sửa phần tử đó”

Không nên dựa vào cách hiểu này. Khi list thuộc source cao hơn, nó không phải cơ chế patch phần tử từ source thấp hơn. Dùng một list đầy đủ trong source ghi đè hoặc chuyển mô hình sang Map khi cần override theo key.

### 22.3. “Set là List và sẽ giữ nguyên thứ tự”

Set không có contract chung bảo đảm iteration order. Nếu thứ tự khai báo quan trọng, dùng List.

### 22.4. “Set tự xác định duplicate theo một field tên”

Không. Duplicate phụ thuộc `equals`/`hashCode` của kiểu phần tử. Hai object cùng `name` nhưng khác `endpoint` có thể hoặc không thể được coi là trùng tùy định nghĩa equality.

### 22.5. “YAML sequence và chuỗi chứa dấu phẩy luôn giống nhau”

Không. YAML sequence phân biệt từng phần tử ở cấp cấu trúc. Chuỗi dấu phẩy cần conversion và có thể gặp vấn đề khi dấu phẩy là dữ liệu của một phần tử.

### 22.6. “Dùng `@Value` cho YAML list là đủ”

Không nên mặc định. `@ConfigurationProperties` được thiết kế để bind cấu trúc collection và nested object; `@Value` dành cho biểu thức hoặc khóa đơn, có thể không nhìn thấy dạng flattened indexed list như dự kiến.

### 22.7. “Thiếu collection luôn nhận list rỗng”

Không thể giả định cho mọi target, constructor và phiên bản. Hãy định nghĩa chính sách default/validation rõ ràng.

### 22.8. “Một array có thể tự mở rộng sau khi bind”

Array có kích thước cố định. Nếu cần thay đổi collection ở runtime, phải thiết kế rõ và thường không nên thay đổi trực tiếp configuration object dùng chung.

## 23. Bảng lựa chọn nhanh

| Nhu cầu | Kiểu đề xuất | Cú pháp nguồn dễ đọc | Lưu ý |
| --- | --- | --- | --- |
| Danh sách có thứ tự | `List<T>` | YAML sequence hoặc indexed properties | List từ source ưu tiên cao thay thế list thấp |
| Dữ liệu có thể trùng | `List<T>` / array | Indexed properties | Giữ phần tử trùng nếu có |
| API yêu cầu array | `T[]` | Indexed properties hoặc YAML sequence | Kích thước cố định |
| Tập giá trị duy nhất | `Set<T>` | YAML sequence | Không giả định thứ tự |
| Danh sách object phức tạp | `List<Server>` | YAML sequence các mapping | Dùng `@Valid` cho object con khi cần |
| Muốn override từng object theo ID | `Map<String, Server>` | YAML mapping theo ID | Map khác list về cách kết hợp nhiều source |
| Chỉ vài chuỗi ngắn | `List<String>` | Có thể dùng comma-separated | Tránh khi phần tử có dấu phẩy |
| Collection bắt buộc | `List<T>`/`Set<T>` + validation | YAML sequence rõ ràng | `@NotEmpty`, constraints trên phần tử |
| Cấu hình bất biến | Record constructor binding + copy phòng thủ | YAML / indexed | Record chỉ bất biến về tham chiếu nếu collection mutable |

## 24. Checklist áp dụng

- Chọn **array** khi API cần mảng, **List** khi có thứ tự và có thể trùng, **Set** khi cần duy nhất và không phụ thuộc thứ tự.
- Trong `.properties`, dùng `app.items[0]`, `app.items[1]` cho các phần tử; với object dùng `app.items[0].name`.
- Trong YAML, dùng sequence `- item` hoặc flow sequence khi các phần tử đơn giản.
- Với collection đơn giản, dấu phẩy có thể tiện; nếu phần tử tự chứa dấu phẩy, dùng indexed properties hoặc YAML sequence.
- Đặt Java type phù hợp để Binder chuyển đổi `String`, `URI`, `Duration`, số, enum và nested object.
- Dùng `@ConfigurationProperties` thay vì dựa hoàn toàn vào `@Value` cho YAML sequence hoặc collection lồng nhau.
- Đăng ký record bằng `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties`; dùng `@Component` cho JavaBean setter binding khi thích hợp.
- Nhớ rằng **List không tự merge qua các PropertySource**; source ưu tiên cao hơn thay thế list nguồn thấp.
- Với Set, hiểu ý nghĩa duplicate theo `equals`/`hashCode` và tránh phụ thuộc iteration order.
- Thiết kế rõ trường hợp **thiếu collection**, **rỗng**, **có phần tử rỗng** và **sai kiểu**.
- Dùng `@NotEmpty`, `@NotBlank`, `@Valid` và validation khác khi cấu hình là bắt buộc.
- Với nested list cần override theo ID, cân nhắc dùng Map thay vì patch theo index.
- Tránh để consumer tự sửa configuration collection nếu không có chủ đích.
- Khi kết quả sai, kiểm tra prefix, index, active profile, property-source precedence và cách biểu diễn nguồn.

## 25. Kết luận

Spring Boot Binder có khả năng **liên kết mảng, `List` và `Set`** từ nhiều biểu diễn cấu hình: indexed keys trong `application.properties`, YAML sequences, chuỗi phân tách dấu phẩy và các nguồn externalized configuration phù hợp.

Khả năng này không chỉ nằm ở việc chuyển nhiều chuỗi thành một Java collection. Nó còn bao gồm relaxed binding tên khóa, conversion từng phần tử, xây dựng nested object, điều kiện theo profile và độ ưu tiên giữa các nguồn. Những chi tiết như **List replacement**, **Set uniqueness**, **YAML sequence vs comma-separated string** và **thiếu giá trị vs rỗng** có thể thay đổi đáng kể hành vi ứng dụng.

Để cấu hình an toàn và dễ bảo trì, hãy ưu tiên `@ConfigurationProperties` với type rõ ràng, biểu diễn danh sách có cấu trúc bằng YAML hoặc indexed properties, đặt validation tại lớp properties và kiểm chứng giá trị hiệu lực ở đúng môi trường khởi động.

### Tài liệu tham khảo

- [Spring Boot Reference — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [Spring Boot Reference — Binding Lists](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.merging-complex-types)
- [Spring Boot Reference — Type-safe Configuration Properties](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties)
- [Spring Boot Reference — Relaxed Binding](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.relaxed-binding)
