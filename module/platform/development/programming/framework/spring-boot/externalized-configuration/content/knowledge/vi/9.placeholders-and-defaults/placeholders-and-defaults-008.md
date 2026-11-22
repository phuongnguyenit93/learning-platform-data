# Giá trị ngẫu nhiên từ random.* và giới hạn sử dụng

> **Chủ đề:** Spring Boot Externalized Configuration  
> **Nhóm:** Placeholder và mặc định

## 1. Khi nào cần giá trị ngẫu nhiên trong cấu hình?

Trong Spring Boot, một giá trị trong `application.properties` hoặc `application.yml` không nhất thiết phải được viết cố định. Cơ chế placeholder cho phép tham chiếu tới các property khác, dùng giá trị mặc định, hoặc yêu cầu một giá trị ngẫu nhiên thông qua nhóm khóa đặc biệt **`random.*`**.

Chẳng hạn, khi chạy thử một ứng dụng, ta muốn có một ID tạm để phân biệt những lần khởi động, một số nguyên phục vụ demo hoặc một cổng trong một khoảng thử nghiệm. Spring Boot cung cấp `RandomValuePropertySource` để tạo ra các giá trị như vậy mà không cần tự viết mã Java tạo số ngẫu nhiên trong mỗi ví dụ.

Tuy nhiên, từ “ngẫu nhiên” không có nghĩa là “duy nhất”, “bí mật”, “ổn định” hay “an toàn trong mọi môi trường”. Nắm được ranh giới của `random.*` là điều cần thiết khi chuyển từ ví dụ học tập sang ứng dụng thật.

Sau bài học, bạn sẽ:

- Nhận biết các biểu thức `random.value`, `random.int`, `random.long` và `random.uuid`.
- Dùng placeholder `${random.*}` trong cấu hình Spring Boot và bind sang các kiểu Java phù hợp.
- Chọn giá trị số có giới hạn và hiểu ý nghĩa biên của khoảng.
- Phân biệt giá trị được khởi tạo từ random placeholder với một property có giá trị cố định do môi trường cung cấp.
- Hiểu tại sao không thể dựa vào `random.*` để có một identifier bền vững, một secret production hoặc một cổng chắc chắn chưa bị chiếm.
- Kiểm soát tính tái lập của test và xác định nguồn cấu hình khi có nhiều cấp precedence.

## 2. `RandomValuePropertySource` là gì?

Spring Boot thêm một nguồn property có thể tạo các giá trị ngẫu nhiên, thường gọi là `RandomValuePropertySource`. Những khóa bắt đầu bằng `random.` được nguồn này hiểu theo cú pháp hỗ trợ. Khi một placeholder tham chiếu tới khóa như `random.int`, hệ thống property resolution có thể lấy giá trị từ nguồn đó.

Ví dụ trong `src/main/resources/application.properties`:

~~~properties
demo.instance-id=${random.uuid}
demo.seed=${random.long}
demo.sample-number=${random.int}
~~~

Trong `application.yml`:

~~~yaml
demo:
  instance-id: "${random.uuid}"
  seed: "${random.long}"
  sample-number: "${random.int}"
~~~

Cả hai ví dụ đều dùng các property của ứng dụng thuộc prefix `demo`. Các khóa `random.uuid`, `random.long` và `random.int` là **nguồn tạo giá trị** mà những property đó tham chiếu.

Phân biệt hai vai trò:

- **`random.uuid`**: khóa đặc biệt của nguồn random.
- **`demo.instance-id`**: khóa cấu hình nghiệp vụ do ứng dụng đặt, có thể đọc qua `Environment` hoặc bind vào `@ConfigurationProperties`.

Không nên giả định một khóa mang tên `random.my-custom-secret` có ý nghĩa “tạo secret” theo tên tự đặt. Hãy dùng những dạng biểu thức được Spring Boot hỗ trợ và kiểm tra kiểu dữ liệu của chúng.

## 3. Các biểu thức random thông dụng

| Biểu thức | Loại giá trị | Dùng cho |
| --- | --- | --- |
| `${random.value}` | Chuỗi giá trị ngẫu nhiên | Dữ liệu minh họa hoặc tên tạm |
| `${random.int}` | Số nguyên dạng `int` | Ví dụ số nguyên |
| `${random.long}` | Số nguyên dạng `long` | Ví dụ số nguyên lớn |
| `${random.uuid}` | UUID ngẫu nhiên | Định danh tạm cho ví dụ hoặc lần khởi tạo |
| `${random.int(10)}` | Số nguyên từ 0 đến dưới 10 | Ví dụ giới hạn trên |
| `${random.int[1024,65536]}` | Số nguyên trong khoảng có hai biên | Ví dụ chọn số trong một dải |

Các dạng trên thể hiện cú pháp thường được tài liệu Spring Boot sử dụng. `random.value` là một giá trị ngẫu nhiên ở dạng chuỗi; không nên thiết kế code dựa trên độ dài hoặc bộ ký tự cụ thể nếu tài liệu của phiên bản không cam kết định dạng đó. `random.uuid` có dạng biểu diễn UUID khi chuyển thành chuỗi.

Dấu ngoặc trong ví dụ số có ý nghĩa của **bộ phân tích biểu thức random**, không phải cú pháp placeholder fallback. Dấu `:` mới thường phân cách phần giá trị mặc định của một placeholder, ví dụ `${demo.timeout:5s}`.

### 3.1. Một file cấu hình minh họa đầy đủ

~~~properties
demo.random-text=${random.value}
demo.random-int=${random.int}
demo.random-long=${random.long}
demo.random-uuid=${random.uuid}
demo.digit=${random.int(10)}
demo.port-candidate=${random.int[10000,20000]}
~~~

Khi một giá trị được truy vấn và giải quyết từ những placeholder này, Spring có thể nhận một mẫu kết quả như sau:

~~~text
demo.random-text   = <chuỗi ngẫu nhiên>
demo.random-int    = <số nguyên>
demo.random-long   = <số nguyên dài>
demo.random-uuid   = <UUID>
demo.digit         = <số từ 0 đến 9>
demo.port-candidate= <số từ 10000 đến 19999>
~~~

Các giá trị thực tế thay đổi; những dòng trong khối kết quả chỉ mô tả loại và khoảng. Không đưa một UUID cố định vào ví dụ rồi giả định người học sẽ nhận cùng UUID đó.

### 3.2. Tại sao cần đặt placeholder bên trong property nghiệp vụ?

Khi viết:

~~~properties
client.retry-jitter=${random.int[0,1000]}
~~~

ứng dụng có thể đọc `client.retry-jitter` như một cấu hình riêng. Ở môi trường cần tái lập hành vi, có thể cung cấp `CLIENT_RETRY_JITTER=250` hoặc `--client.retry-jitter=250` để thay thế. Cách thiết kế này giữ quyền kiểm soát cấu hình tại nơi triển khai.

Nếu mọi component tự gọi `Environment.getProperty("random.int")` trực tiếp trong logic nghiệp vụ, việc kiểm soát thời điểm tạo giá trị và cùng chia sẻ một giá trị sẽ khó rõ ràng hơn. Với một thông số cấu hình, hãy đặt một tên property có ý nghĩa trước rồi mới quyết định fallback.

## 4. Giới hạn số nguyên: một biên và hai biên

### 4.1. Dạng có một giới hạn

~~~properties
demo.index=${random.int(10)}
~~~

Ở cách dùng thông thường, biểu thức này tạo một số nguyên **từ 0 (bao gồm) đến 10 (không bao gồm)**. Tập giá trị có thể là 0, 1, ..., 9.

Một vài ví dụ:

~~~properties
demo.coin=${random.int(2)}
demo.test-shard=${random.int(8)}
~~~

`random.int(2)` có thể cho 0 hoặc 1. `random.int(8)` có thể cho 0 đến 7. Không dùng giới hạn 0 hoặc giới hạn âm với kỳ vọng một khoảng số ngẫu nhiên có nghĩa; các biên cần thỏa điều kiện của bộ tạo giá trị.

### 4.2. Dạng có hai giới hạn

~~~properties
demo.batch-size=${random.int[10,20]}
~~~

Ý nghĩa điển hình là giá trị nguyên nằm trong khoảng **[10, 20)**: cận dưới 10 được bao gồm, cận trên 20 không được bao gồm. Các kết quả có thể là 10, 11, ..., 19.

Ví dụ khác:

~~~properties
demo.ephemeral-port-candidate=${random.int[10000,20000]}
demo.initial-counter=${random.int[1,100]}
~~~

Với dải `[10000,20000]`, giá trị được tạo là một số trong vùng 10000 đến 19999 theo quy tắc biên trên không bao gồm. Cú pháp dấu ngoặc vuông ở đây là một phần của biểu thức random trong Spring Boot, **không phải** một YAML list.

Nếu muốn một giá trị thuộc dải 1–100 bao gồm cả 100, cận trên trong biểu thức theo quy tắc này phải lớn hơn 100, ví dụ `random.int[1,101]`.

### 4.3. Kiểu `long` và giới hạn

`random.long` phù hợp khi cần một giá trị nguyên thuộc kiểu `long`. Khi sử dụng các biến thể có giới hạn, phải bảo đảm cận nằm trong phạm vi kiểu và cận trên lớn hơn cận dưới. Tránh dựa vào những cách viết không được tài liệu phiên bản Spring Boot đang dùng hỗ trợ.

Ví dụ cơ bản, không đặt khoảng:

~~~properties
demo.session-number=${random.long}
~~~

Bind sang `long` hoặc `Long` khi cần, thay vì tự parse bằng những đoạn code giả định cụ thể về định dạng.

### 4.4. Random chỉ tạo ứng viên, không xác nhận tài nguyên có thể dùng

Một số nguyên ngẫu nhiên trong dải cổng TCP **không bảo đảm cổng đang rảnh**. Chẳng hạn:

~~~properties
server.port=${random.int[10000,20000]}
~~~

có thể chọn một giá trị bị tiến trình khác chiếm. Với Spring Boot chạy embedded server và muốn để hệ điều hành chọn một cổng còn trống, thông thường dùng:

~~~properties
server.port=0
~~~

Rồi nhận cổng thực tế sau khi server bind thành công (ví dụ trong integration test). Tương tự, `random.int` không bảo đảm index của tài nguyên hợp lệ, không cam kết một số chưa từng được dùng và không phải một bộ phân bổ ID phân tán.

## 5. UUID ngẫu nhiên: có ích nhưng không bền vững

### 5.1. Dùng `random.uuid`

Ví dụ:

~~~yaml
demo:
  run-id: "${random.uuid}"
~~~

Khi property này được giải quyết, giá trị có dạng UUID. Nó hữu ích để phân biệt các lần chạy **trong ví dụ**, hoặc gắn nhãn tạm cho một quá trình thử nghiệm.

Code có thể bind vào `String`:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "demo")
public record DemoProperties(String runId) {}
~~~

Hoặc có thể dùng kiểu `UUID` nếu đường chuyển đổi giá trị trong Spring ứng dụng hỗ trợ:

~~~java
import java.util.UUID;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "demo")
public record DemoIdProperties(UUID runId) {}
~~~

Trong cả hai trường hợp, bản chất vẫn là một **giá trị được tạo ra khi giải quyết cấu hình**, không phải một ID đã được hệ thống lưu trữ và quản lý vòng đời.

### 5.2. Không nhầm UUID ngẫu nhiên với ID ổn định

Giả sử một ứng dụng dùng:

~~~properties
app.node-id=${random.uuid}
~~~

Nếu mỗi lần startup tạo ID mới, một máy chủ có thể đổi `node-id` sau restart. Điều này không phù hợp nếu hệ thống dùng ID để liên kết dữ liệu dài hạn, đăng ký vào cluster cần identity bền vững hoặc xác định một instance xuyên suốt các lần triển khai.

Các lựa chọn phù hợp hơn tùy trường hợp:

- **ID cần tồn tại xuyên restart:** được cấp một lần và lưu trong database, file cấu hình bền vững hoặc hệ thống identity.
- **ID của pod/instance trong orchestration:** dùng metadata hoặc cơ chế identity do nền tảng triển khai cung cấp.
- **ID mỗi request:** tạo ở thời điểm xử lý request và gắn với một request context; không dùng một property ngẫu nhiên toàn ứng dụng.
- **ID của lần chạy demo:** một giá trị khởi tạo như `random.uuid` có thể đủ nếu không đòi hỏi định danh ổn định.

### 5.3. Random không đồng nghĩa tuyệt đối không trùng

UUID ngẫu nhiên thường có xác suất va chạm rất thấp theo mô hình phù hợp, nhưng điều đó không cung cấp cam kết không trùng tuyệt đối ở cấp nghiệp vụ. Với dữ liệu cần duy nhất về mặt lưu trữ, vẫn nên có ràng buộc unique ở database hoặc cơ chế cấp phát/đối chiếu ID phù hợp.

Không dùng xác suất thấp để thay thế một ràng buộc mà tính toàn vẹn dữ liệu yêu cầu.

## 6. Thời điểm tạo giá trị: điều quan trọng của `random.*`

`RandomValuePropertySource` là một nguồn **tạo giá trị khi được yêu cầu**, không phải một bảng hằng số bất biến được lưu bền vững. Do đó, không nên giả định rằng mọi lần đọc `random.uuid` sẽ nhận đúng một UUID chung, hoặc hai placeholder độc lập tham chiếu `random.int` sẽ chia sẻ cùng một số.

Ví dụ:

~~~properties
demo.first=${random.uuid}
demo.second=${random.uuid}
~~~

Đừng coi `demo.first` và `demo.second` là cùng một định danh. Ngay cả khi cả hai được giải quyết trong cùng lần khởi động, không có lý do để thiết kế chúng phải bằng nhau. Cũng không nên đặt yêu cầu “mỗi lần đọc chắc chắn phải khác”; hai số ngẫu nhiên có thể tình cờ giống nhau.

### 6.1. Giá trị được bind vào một bean có thể ổn định trong vòng đời bean

Nếu `@ConfigurationProperties` được bind một lần khi startup, field trong bean giữ giá trị đã được bind cho đến khi bean được thay đổi hoặc tạo lại theo cơ chế ứng dụng. Ví dụ:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "demo")
public record DemoProperties(String runId, int sampleNumber) {}
~~~

Cấu hình:

~~~properties
demo.run-id=${random.uuid}
demo.sample-number=${random.int(1000)}
~~~

Một bean `DemoProperties` bình thường nhận các giá trị tại thời điểm binding. Các lời gọi `properties.runId()` sau đó đọc field của bean đó, **không phải mỗi lần đều gọi bộ sinh random**.

Nhưng hai điều khác nhau cần tách biệt:

1. **Giá trị field đã được lưu trong object Java** có thể giữ nguyên.
2. **Một lần resolve placeholder hoặc truy vấn random property mới** có thể tạo giá trị mới.

Nếu ứng dụng có cơ chế refresh/rebind đặc biệt, lifecycle của bean còn phụ thuộc vào cơ chế đó. Không dùng giả định “random chỉ chạy một lần” như hợp đồng mặc định cho mọi đường đọc cấu hình.

### 6.2. Muốn chia sẻ đúng một giá trị? Hãy giữ nó ở một nơi

Một cách đơn giản là bind một lần vào một bean và truyền bean đó tới những thành phần cần dùng. Ví dụ:

~~~java
import org.springframework.stereotype.Service;

@Service
public class DemoRunService {
    private final DemoProperties properties;

    public DemoRunService(DemoProperties properties) {
        this.properties = properties;
    }

    public String runIdForLogging() {
        return properties.runId();
    }
}
~~~

Các thành phần dùng cùng bean sẽ có một giá trị đã bind, với lifecycle của bean đó. Nếu cần **cố định giữa nhiều tiến trình**, việc chia sẻ một bean trong một JVM vẫn chưa đủ: phải cấp giá trị qua cấu hình triển khai, storage hoặc một dịch vụ chung.

### 6.3. Không xem random property như hàm chọn số cho từng lần gọi nghiệp vụ

Nếu nghiệp vụ yêu cầu random cho từng thao tác, chẳng hạn tạo token tạm, lấy một mẫu hoặc quyết định jitter trên từng lần retry, nên sử dụng một API random phù hợp **trong logic nghiệp vụ tại thời điểm cần tạo**. `random.*` là một tiện ích externalized configuration, không phải một thay thế tổng quát cho thư viện random của Java hay một dịch vụ cấp phát ID.

## 7. Placeholder, mặc định và cách ghi đúng cú pháp

### 7.1. Property có fallback về random

Một ví dụ thực tế trong môi trường demo:

~~~properties
demo.run-id=${APP_RUN_ID:${random.uuid}}
~~~

Ý tưởng: nếu có property `APP_RUN_ID` trong môi trường giải quyết placeholder thì dùng giá trị đó; nếu không, fallback tạo UUID. Tuy nhiên, khi thiết kế cấu hình Spring Boot, nên sử dụng tên property canonical (ví dụ `app.run-id`) rồi cung cấp biến môi trường `APP_RUN_ID` thông qua relaxed binding:

~~~properties
app.run-id=${app.assigned-run-id:${random.uuid}}
~~~

Ở đây `app.assigned-run-id` là property được cấp từ môi trường nếu có; nếu thiếu thì dùng một giá trị ngẫu nhiên. Kết quả vẫn chịu precedence của toàn hệ thống. Nếu chính `app.run-id` được cung cấp bởi một nguồn cao hơn, biểu thức nằm ở file cấu hình thấp hơn có thể không được dùng.

Trong mọi trường hợp, fallback ngẫu nhiên chỉ nên được chọn nếu nghiệp vụ thực sự cho phép ID thay đổi khi chưa có cấu hình. Một ID bắt buộc ổn định không nên có fallback ngẫu nhiên âm thầm.

### 7.2. Dùng trong YAML

Vì một số placeholder chứa ký tự đặc biệt như `[`, `]`, `{` hoặc `}`, cách trình bày an toàn, dễ đọc là quote scalar trong YAML:

~~~yaml
demo:
  run-id: "${random.uuid}"
  sample-index: "${random.int(10)}"
  service-port-candidate: "${random.int[10000,20000]}"
~~~

YAML có thể đọc các giá trị trên như string trước khi Spring resolve placeholder. Khi bind sang `int` hoặc `long`, Spring Boot thực hiện conversion dựa trên kiểu đích. Không kết luận rằng vì YAML đặt dấu nháy kép nên bean bắt buộc phải có kiểu `String`.

### 7.3. Phân biệt hai dấu hai chấm

Trong:

~~~properties
demo.mode=${demo.explicit-mode:local}
~~~

dấu `:` phân cách **property name** và **default value** của placeholder: nếu `demo.explicit-mode` không có thì dùng `local`.

Trong:

~~~properties
demo.mode=${demo.explicit-mode:${random.uuid}}
~~~

phần sau `:` là một **placeholder khác** để tạo giá trị fallback.

Còn:

~~~properties
demo.number=${random.int[10,20]}
~~~

là cách yêu cầu nguồn random tạo số trong khoảng. Hai dạng này phục vụ những mục đích khác nhau.

### 7.4. Một property có thể bị nguồn cao hơn ghi đè

`application.yml`:

~~~yaml
demo:
  run-id: "${random.uuid}"
~~~

Khởi động với:

~~~bash
java -jar app.jar --demo.run-id=run-fixed-2026
~~~

Theo cơ chế precedence mặc định, command-line property `demo.run-id` có thể thắng giá trị từ YAML. Điều này là mong muốn nếu triển khai cần xác định một giá trị cụ thể.

Không cần tìm cách vô hiệu hóa `RandomValuePropertySource` để ép ứng dụng dùng giá trị cố định; hãy cấp đúng property nghiệp vụ ở nguồn có ưu tiên cao hơn.

## 8. Thứ tự ưu tiên so với những nguồn khác

Spring Boot sắp xếp nhiều property sources. Với cách cấu hình mặc định và bỏ qua nguồn dành riêng cho test hoặc cấu hình tùy chỉnh, thứ tự **cao → thấp** liên quan tới bài này có thể hình dung:

| Mức ưu tiên tương đối | Nguồn |
| --- | --- |
| Cao | Tham số dòng lệnh của ứng dụng |
| Cao | `SPRING_APPLICATION_JSON` và các JSON application properties |
| Cao | Các nguồn thuộc môi trường Servlet/JNDI khi hiện diện |
| Cao hơn random | Java system properties |
| Cao hơn random | Biến môi trường của hệ điều hành |
| **Random** | `RandomValuePropertySource` |
| Thấp hơn random | Config data: `application.properties`, `application.yml`, import/profile |
| Thấp | `@PropertySource` và default properties |

Điểm cốt lõi là: `random.*` không phải nguồn “có quyền ưu tiên tuyệt đối”; nó là một nguồn property trong chuỗi tra cứu. Một property nghiệp vụ như `demo.run-id` được cấp ở CLI/OS env có thể ghi đè biểu thức đặt trong file.

Cũng không nên nhầm **vị trí random trong precedence** với việc “mọi property ở file sẽ luôn bị random ghi đè”. `RandomValuePropertySource` chỉ cung cấp các khóa mà nó hỗ trợ, thông thường là namespace `random.*`. Nó không tự sinh giá trị cho bất kỳ khóa `demo.*` nào nếu file không khai báo placeholder hoặc ứng dụng không yêu cầu.

### 8.1. Ví dụ có ba nguồn

`application.properties`:

~~~properties
demo.run-id=${random.uuid}
demo.retries=3
~~~

Biến môi trường:

~~~bash
export DEMO_RETRIES=5
~~~

Chạy:

~~~bash
java -jar app.jar --demo.retries=8
~~~

Khi cả ba nguồn hoạt động với cấu hình mặc định, `demo.retries` nhận `8` từ CLI. `demo.run-id` có thể nhận một UUID do placeholder trong file yêu cầu, nếu không có nguồn ưu tiên cao hơn đặt `demo.run-id`.

Nếu triển khai cấp `DEMO_RUN_ID=deployment-7`, đó là property nghiệp vụ được cấp rõ ràng, có thể khiến giá trị cố định thắng fallback `random.uuid` trong file.

### 8.2. Các nguồn test cũng có precedence riêng

Trong Spring Boot test, `@TestPropertySource`, `@DynamicPropertySource` hoặc cấu hình cho test slice có thể góp những nguồn ưu tiên cao. Vì vậy, khi test muốn tái lập kết quả, nên thiết lập trực tiếp `demo.run-id=test-run` hoặc một giá trị tương tự, rồi xác nhận thuộc tính đó thực sự được dùng trong context của test.

Không nên dự đoán kết quả test chỉ bằng bảng cấu hình runtime thông thường khi test đã thêm nhiều property sources.

## 9. Đọc và bind giá trị trong Java

### 9.1. Đọc qua `Environment`

Ví dụ:

~~~java
package com.example.demo;

import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class DemoOptions {
    private final Environment environment;

    public DemoOptions(Environment environment) {
        this.environment = environment;
    }

    public String runId() {
        return environment.getProperty("demo.run-id");
    }

    public Integer index() {
        return environment.getProperty(
                "demo.sample-index", Integer.class);
    }
}
~~~

`Environment` tra cứu thuộc tính theo tên `demo.*`. Trong ví dụ ứng dụng, chúng được khai báo thông qua placeholder `random.*` trong `application.yml`. Nếu cần kết quả giữ nguyên trong vòng đời của một object, bind cấu hình vào một bean theo cách phù hợp rồi đọc field của bean đó.

### 9.2. Bind bằng `@ConfigurationProperties`

`application.yml`:

~~~yaml
demo:
  run-id: "${random.uuid}"
  sample-index: "${random.int[0,100]}"
  enabled: true
~~~

Record cho Spring Boot 3, Java 17+:

~~~java
package com.example.demo;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "demo")
public record DemoProperties(
        String runId,
        int sampleIndex,
        boolean enabled
) {}
~~~

Bật scanning từ ứng dụng:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

Sử dụng:

~~~java
import org.springframework.stereotype.Service;

@Service
public class DemoService {
    private final DemoProperties properties;

    public DemoService(DemoProperties properties) {
        this.properties = properties;
    }

    public String describe() {
        return properties.runId()
                + " / index=" + properties.sampleIndex();
    }
}
~~~

Nếu không có override cao hơn, `runId` nhận UUID dạng chuỗi, `sampleIndex` nhận số trong dải 0–99 và `enabled` nhận `true`. Java bean thông thường giữ các field sau khi được tạo, do đó đây là cách hợp lý để dùng **một giá trị cấu hình tại một thời điểm**.

### 9.3. Chọn kiểu dữ liệu hợp lý

- `random.int`: bind vào `int` hoặc `Integer`.
- `random.long`: bind vào `long` hoặc `Long`.
- `random.uuid`: thường có thể lấy dạng `String` hoặc bind vào `UUID` khi conversion hỗ trợ.
- `random.value`: dùng như giá trị dạng chuỗi; không giả định hình thức cố định nếu không được hợp đồng API đảm bảo.
- Với một khoảng số, loại Java của field vẫn phải phù hợp với kích thước cận và phạm vi thực tế.

Khi có điều kiện nghiệp vụ, áp dụng validation riêng. Ví dụ một giá trị `sampleIndex` phải không âm và nhỏ hơn số lượng phần tử hiện có; khoảng random của cấu hình có thể hợp lệ tại lúc startup nhưng không phù hợp nếu số phần tử thực tế thay đổi.

## 10. Vì sao `random.*` không nên được xem là hệ thống quản lý secret?

Tên “random” dễ tạo cảm giác an toàn, nhưng yêu cầu bảo mật cao hơn nhiều so với việc tạo một chuỗi trông ngẫu nhiên.

### 10.1. Sinh giá trị ngẫu nhiên không tự tạo quy trình bảo mật

Ví dụ:

~~~properties
security.api-token=${random.value}
~~~

Có nhiều rủi ro dù giá trị nhìn có vẻ khó đoán:

- Không có cam kết từ cách dùng này rằng định dạng, độ dài, entropy hoặc thuật toán thỏa một yêu cầu bảo mật cụ thể.
- Giá trị có thể thay đổi sau khi ứng dụng restart, khiến client dùng token cũ không còn tương thích.
- Nếu nhiều instance tự tạo secret riêng, chúng có thể không thể xác thực token hoặc session do instance khác tạo.
- Không có quy trình phân phối cho client, cấp mới, thu hồi, xoay vòng hoặc khôi phục secret.
- Việc in cấu hình ra log hoặc mở endpoint chẩn đoán có thể để lộ giá trị.

Vì vậy, **không dùng `random.value` làm mặc định cho production password, signing key, encryption key, API token hoặc secret liên instance** chỉ vì nó có chữ “random”.

### 10.2. Cần secret thì lấy từ nguồn quản lý thích hợp

Trong production, nên dùng một nguồn secret đã được vận hành:

- Secret manager có chính sách truy cập và cơ chế rotation.
- Secret volume được mount với quyền đọc giới hạn, có thể đưa vào Spring Boot qua `configtree:` khi phù hợp.
- Cấu hình được cấp qua một deployment pipeline bảo vệ thông tin nhạy cảm.

Một ứng dụng có thể dùng `@ConfigurationProperties` để bind secret giống property khác, nhưng nguồn cấp secret cần đáp ứng yêu cầu về vòng đời, giới hạn quyền truy cập và khả năng đồng bộ giữa instance.

Nếu thực sự cần **tạo cryptographic secret mới**, hãy dùng API hoặc hệ thống có đặc tính bảo mật được xác nhận, ví dụ `SecureRandom` đúng cách cho code Java, đồng thời lưu/phân phối secret theo yêu cầu. `random.*` là tiện ích cấu hình, không cung cấp trọn vòng đời quản lý secret.

### 10.3. UUID không phải password

UUID có thể phù hợp làm định danh, nhưng không nên tự coi `random.uuid` là password hoặc khóa ký. Việc một giá trị khó đoán không tự quyết định nó có entropy hoặc tính chất bảo mật đúng cho thuật toán và threat model của hệ thống.

Hơn nữa, việc dùng UUID như token bí mật đòi hỏi quy tắc sử dụng, thời hạn, thu hồi, lưu trữ và truy cập riêng; các yêu cầu đó không nằm trong chức năng của `RandomValuePropertySource`.

## 11. Giới hạn trong môi trường nhiều instance và production

### 11.1. Mỗi instance có thể nhận một giá trị khác

Với ba pod ứng dụng cùng dùng:

~~~properties
app.instance-id=${random.uuid}
~~~

mỗi pod có thể tạo identifier riêng trong quá trình khởi tạo cấu hình. Điều này có thể hữu ích nếu chỉ cần một nhãn tạm trong log demo. Nhưng nếu ứng dụng cần cluster node identity có thể khôi phục, identifier phải đến từ cơ chế phân bổ ổn định của hạ tầng hoặc storage.

Không nên mong các pod nhận cùng một “default random secret” để xác thực chung. Nếu mỗi pod tạo khác nhau, người dùng có thể bị lỗi khi request được cân bằng qua instance khác.

### 11.2. Khởi động lại có thể đổi hành vi

Một giá trị `demo.random-delay=${random.int[100,500]}` được bind khi startup có thể khác ở lần deploy kế tiếp. Nếu đây là tuning parameter quan trọng, việc đổi ngẫu nhiên khiến quan sát performance, phát hiện hồi quy hoặc so sánh giữa môi trường khó hơn.

Chỉ dùng random mặc định cho cấu hình mà sự biến động là một phần **được mong đợi** của hành vi. Với timeout, quota, retry count hoặc thông số vận hành chính, thông thường nên đặt giá trị có chủ đích và có thể audit.

### 11.3. Số ngẫu nhiên không tự giải quyết xung đột

Dùng một `random.int` làm mã đơn hàng có thể tạo va chạm. Dùng nó để cấp cổng server cũng có thể tạo va chạm. Trong các bài toán cần uniqueness thật sự, cần database unique constraint, identifier allocator, cơ chế lock/lease hoặc quyết định của hệ điều hành tùy loại tài nguyên.

Ví dụ: trong test server port, `server.port=0` giúp OS cấp cổng còn trống tại lúc bind tốt hơn một phép thử số ngẫu nhiên độc lập. Trong phân tán, cần phối hợp tại nguồn dữ liệu dùng chung thay vì hy vọng hai số không trùng.

### 11.4. Không dùng làm cách thay thế feature rollout có kiểm soát

Một tính năng được bật bằng:

~~~properties
feature.new-ui=${random.int(2)}
~~~

dễ khiến trạng thái tùy tiện đổi giữa những lần chạy. Nó không đảm bảo tỷ lệ người dùng, nhóm thử nghiệm, tính nhất quán qua các request hay khả năng rollback. Nếu cần rollout 10% người dùng, dùng cơ chế feature flag hoặc deterministic bucketing theo user ID phù hợp, thay vì biến random tại startup.

## 12. Test và khả năng tái lập

### 12.1. Test cần cấu hình xác định

Giả sử logic cần dựa vào `demo.bucket`. Với:

~~~properties
demo.bucket=${random.int[0,100]}
~~~

test có thể nhận những giá trị khác ở các lần khởi tạo context. Nếu assertion giả định `bucket=12`, test sẽ không ổn định.

Cách kiểm soát tốt hơn:

~~~java
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest(properties = {
        "demo.bucket=12",
        "demo.run-id=test-run-001"
})
class DemoApplicationTests {
    // Test kiểm tra hành vi dựa trên cấu hình xác định.
}
~~~

Hoặc dùng một cấu hình `application-test.yml` với giá trị cố định và kích hoạt profile `test`. Cần kiểm tra precedence nếu test đồng thời dùng command-line, `@DynamicPropertySource` hay cấu hình tùy chỉnh khác.

### 12.2. Khi muốn kiểm thử khoảng số

Nếu mục tiêu là kiểm tra việc ứng dụng chấp nhận một giá trị trong phạm vi, test nên kiểm tra **điều kiện phạm vi** hoặc logic xử lý value chứ không dự đoán một số ngẫu nhiên cụ thể.

Ví dụ nhận `demo.sample-index` ở `@ConfigurationProperties`:

~~~java
int sample = properties.sampleIndex();
if (sample < 0 || sample >= 100) {
    throw new IllegalStateException("sample index ngoài phạm vi");
}
~~~

Đây là ví dụ minh họa kiểm tra bất biến. Khi cần test thực sự có tính lặp lại, hãy inject giá trị cố định. Việc lấy nhiều mẫu random rồi đòi tất cả số đều xuất hiện không phải một cách test bền vững.

### 12.3. Test logic ngẫu nhiên nên tách nguồn tạo số

Nếu nghiệp vụ yêu cầu mỗi lần retry chọn jitter mới, nên tách một component hoặc interface cấp số ngẫu nhiên khỏi logic retry. Trong test, cấp một fake/deterministic generator; trong production, cấp generator phù hợp mục đích. Cách này kiểm tra thuật toán mà không phụ thuộc vào trạng thái không dự đoán được của `random.*`.

Property `random.*` chủ yếu dành cho **khởi tạo giá trị cấu hình ngẫu nhiên** trong các ví dụ hoặc tình huống có chủ đích.

## 13. Chẩn đoán khi kết quả khác mong đợi

### 13.1. Đọc một giá trị đã được bind

Một cách an toàn để quan sát với khóa demo không nhạy cảm:

~~~java
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;

@Component
public class RandomConfigProbe implements ApplicationRunner {

    private final DemoProperties properties;

    public RandomConfigProbe(DemoProperties properties) {
        this.properties = properties;
    }

    @Override
    public void run(ApplicationArguments args) {
        System.out.println("demo.sample-index = "
                + properties.sampleIndex());
    }
}
~~~

Đoạn code đọc **field đã bind** thay vì gọi nguồn random trực tiếp nhiều lần. Nó minh họa một giá trị tại thời điểm startup, không yêu cầu người học phải dự đoán trước số chính xác.

Chỉ log giá trị thử nghiệm không nhạy cảm. Không log các secret hoặc toàn bộ `Environment` trong môi trường dùng thật.

### 13.2. Phân biệt nguồn tạo giá trị và nguồn override

Giả sử:

~~~properties
demo.run-id=${random.uuid}
~~~

mà ứng dụng luôn nhận `fixed-run`. Hãy kiểm tra các nguồn ưu tiên cao hơn: có `DEMO_RUN_ID=fixed-run`, `--demo.run-id=fixed-run`, `-Ddemo.run-id=fixed-run` hoặc test property nào không?

Nếu đang dùng một bean `@ConfigurationProperties`, cũng cần xác nhận bean đã được scan/đăng ký và được bind từ đúng context. Nếu ứng dụng đọc trực tiếp `random.uuid` bằng `Environment.getProperty(...)`, đó là hành vi khác với việc đọc `demo.run-id` là property có placeholder trong file.

### 13.3. Bảng lỗi thường gặp

| Hiện tượng | Nguyên nhân cần xem |
| --- | --- |
| `${random.int(10)}` không nằm trong 1–10 | Khoảng bắt đầu từ 0 và cận trên 10 không bao gồm |
| Giá trị khác mỗi lần khởi động | Random property được tạo lại; không có cơ chế lưu bền vững |
| Hai component dùng giá trị khác dù đều tham chiếu random | Có thể giải quyết các placeholder ở thời điểm khác; nên bind/chia sẻ một giá trị nếu cần đồng nhất |
| Gặp lỗi bind số hoặc kiểu `UUID` | Kiểm tra biểu thức, dữ liệu override và kiểu Java đích |
| Chọn cổng ngẫu nhiên nhưng server không chạy | Cổng có thể bị chiếm; dùng `server.port=0` nếu muốn OS chọn cổng |
| Test không ổn định | Dùng placeholder ngẫu nhiên trong cấu hình mà assertion lại đòi kết quả cố định |
| Secret thay đổi sau restart | Đã dùng random như nguồn cấp secret không bền vững |
| Kết quả không ngẫu nhiên như mong đợi | Có thể một nguồn ưu tiên cao hơn đã cung cấp giá trị cố định |
| Log hiển thị nhiều UUID khác nhau | Có thể đang resolve `random.uuid` nhiều lần thay vì đọc một field đã bind |
| Biểu thức không được phân giải | Code đang đọc raw file như text, chưa qua cơ chế placeholder resolution của Spring |

### 13.4. Những thứ nên kiểm tra theo thứ tự

1. **Tên placeholder:** có đúng `${random.int}`, `${random.uuid}` hoặc cú pháp giới hạn được hỗ trợ không?
2. **Nơi đặt placeholder:** trong config data Spring Boot đang thực sự nạp, hay chỉ trong một file text được mở bằng `Files.readString`?
3. **Tên property nghiệp vụ:** ứng dụng cần `demo.run-id` hay đang tra cứu thẳng `random.uuid`?
4. **Nguồn ưu tiên cao hơn:** có env var, system property, JSON hoặc CLI override không?
5. **Thời điểm đọc:** đang bind một bean lúc khởi động hay resolve random property trong nhiều lần?
6. **Loại dữ liệu:** số có hợp lệ với `int`/`long` và giới hạn kinh doanh không?
7. **Yêu cầu nghiệp vụ:** cần một giá trị random tạm thời hay cần ID/secret/port bền vững?
8. **Môi trường test:** có nguồn giá trị cố định để test tái lập không?

## 14. Bài tập thực hành

### Bài tập A: quan sát bốn loại giá trị

Tạo `application.yml`:

~~~yaml
lesson:
  random-value: "${random.value}"
  random-int: "${random.int}"
  random-long: "${random.long}"
  random-uuid: "${random.uuid}"
~~~

Bind qua `@ConfigurationProperties(prefix = "lesson")` hoặc đọc bằng `Environment`. In các giá trị **demo không nhạy cảm** khi startup và quan sát loại giá trị. Khởi động lại ứng dụng để so sánh các lần chạy, không viết assertion đòi một giá trị cụ thể.

### Bài tập B: giới hạn trên độc quyền

Dùng:

~~~properties
lesson.digit=${random.int(10)}
lesson.two-digit=${random.int[10,100]}
~~~

Dự đoán khoảng hợp lệ: `digit` thuộc 0–9; `two-digit` thuộc 10–99. Trong code dùng `Integer` hoặc `int` để bind. Thử một cận trên không hợp lệ để quan sát lỗi khi biểu thức được giải quyết, rồi trả về một khoảng đúng.

### Bài tập C: override random bằng giá trị được cấp

`application.properties`:

~~~properties
lesson.run-id=${random.uuid}
~~~

Chạy không có override và quan sát giá trị. Sau đó chạy:

~~~bash
java -jar lesson.jar --lesson.run-id=known-test-run
~~~

Kết quả thứ hai mong đợi là `known-test-run` vì CLI cấp giá trị nghiệp vụ có ưu tiên cao. Việc random placeholder vẫn tồn tại trong tệp không có nghĩa nó phải thắng mọi nguồn.

### Bài tập D: giả lập yêu cầu chia sẻ một ID

Tạo hai service dùng cùng một `LessonProperties` bean chứa `runId` đã bind từ `${random.uuid}`. Quan sát hai service cùng đọc một field trong cùng context. Sau đó thử gọi trực tiếp `Environment.getProperty("random.uuid")` ở nhiều nơi và giải thích vì sao không nên lấy kết quả đó làm hợp đồng đồng nhất.

### Bài tập E: chọn cổng trong integration test

Thử cấu hình `server.port=${random.int[10000,20000]}`, rồi đối chiếu với `server.port=0`. Trong test cần server chạy thật, hãy dùng cơ chế random port do Spring Boot test và embedded server hỗ trợ, đọc cổng thực tế sau khi server khởi tạo thay vì tự đoán một cổng bằng số ngẫu nhiên.

### Bài tập F: phân loại yêu cầu

Chọn cơ chế phù hợp cho mỗi tình huống:

| Yêu cầu | Gợi ý |
| --- | --- |
| Sinh số tạm trong demo startup | `random.int` |
| Một nhãn UUID tạm cho lần khởi tạo | `random.uuid`, nếu chấp nhận thay đổi |
| ID của tài khoản cần tồn tại lâu dài | Bộ cấp ID/lưu trữ có ràng buộc |
| Server port tự động chọn khi test | `server.port=0` hoặc cơ chế test tương đương |
| Secret ký token dùng chung nhiều pod | Secret manager hoặc nguồn secret được phân phối đồng bộ |
| Jitter mới cho mỗi retry | Logic ngẫu nhiên tại runtime, không phải property cấu hình startup |
| Giá trị chính xác để test tái lập | Test property cố định |

## 15. Nguyên tắc thiết kế cần nhớ

**Giá trị ngẫu nhiên là một lựa chọn có chủ đích.** Đừng đưa `random.*` làm fallback mặc định cho mọi cấu hình thiếu, nhất là những giá trị mà sự thay đổi có thể gây lỗi hoặc khó chẩn đoán.

**Nghĩ về vòng đời của giá trị trước khi chọn nguồn.** Một giá trị có thể cần cố định cho một request, một JVM, một lần deploy hay toàn bộ vòng đời dữ liệu. `random.*` tự nó không mô tả những vòng đời đó; code và hệ thống triển khai phải đảm bảo.

**Phân biệt uniqueness và randomness.** Một số khó dự đoán vẫn có thể bị trùng. Khi yêu cầu uniqueness là ràng buộc nghiệp vụ, cần cơ chế cưỡng chế ở storage hoặc dịch vụ cấp phát.

**Phân biệt convenience và security.** `RandomValuePropertySource` tiện trong cấu hình và ví dụ, nhưng không phải secret-management system hay hợp đồng về chất lượng mật mã.

**Giữ khả năng override và kiểm thử.** Đặt random placeholder sau một tên property nghiệp vụ, ví dụ `demo.sample-index`, để test và deployment có thể cấp giá trị rõ ràng khi cần.

## Tài liệu tham khảo

- [Spring Boot Reference — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html): thứ tự nguồn cấu hình và `RandomValuePropertySource`.
- [Spring Boot Reference — Configuring Random Values](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.random-values): các biểu thức `random.value`, `random.int`, `random.long`, `random.uuid` và giới hạn số.
- [Spring Boot Reference — Type-safe Configuration Properties](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties): binding property vào object Java.
- [Spring Framework — Property Placeholder Resolution](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/value-annotations.html): placeholder và fallback.
- [Java SE — SecureRandom](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/SecureRandom.html): API cho trường hợp cần tạo bytes ngẫu nhiên với mục đích bảo mật.
