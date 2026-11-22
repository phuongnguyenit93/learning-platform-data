# Kiểu giá trị và phạm vi giá trị được hỗ trợ

Spring Boot cung cấp `RandomValuePropertySource` để ứng dụng tham chiếu giá trị ngẫu nhiên ngay trong cấu hình. Cơ chế này hỗ trợ số nguyên, số nguyên dài, UUID và một giá trị ngẫu nhiên dạng chuỗi. Với `random.int` và `random.long`, bạn còn có thể giới hạn miền kết quả bằng cú pháp một cận hoặc hai cận.

Đây là tiện ích của Spring Boot, không phải API tạo số ngẫu nhiên riêng của Spring Cloud. Ứng dụng Spring Cloud vẫn dùng được các placeholder này thông qua `Environment` và cơ chế externalized configuration của Spring Boot. Chúng hữu ích cho dữ liệu thử nghiệm, mã định danh tạm thời và giá trị khởi tạo lúc ứng dụng khởi động.

Bài học thuộc chương **Giá trị ngẫu nhiên** của module **SPRING_CLOUD_CORE**. Ta sẽ phân biệt từng kiểu, đọc đúng quy tắc cận dưới/cận trên, dùng placeholder trong YAML và properties, bind sang kiểu Java, kiểm thử miền giá trị và nhận diện giới hạn bảo mật theo phiên bản Spring Boot.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích vai trò của `RandomValuePropertySource` trong Spring `Environment`.
- Nhận biết bốn nhóm placeholder được tài liệu hóa: `random.int`, `random.long`, `random.uuid` và `random.value`.
- Phân biệt số ngẫu nhiên không giới hạn với số nằm trong một miền xác định.
- Giải thích cận dưới được bao gồm và cận trên bị loại khỏi miền.
- Dùng cú pháp một cận và hai cận cho cả `int` lẫn `long`.
- Viết placeholder trong `application.yml` và `application.properties`.
- Bind giá trị ngẫu nhiên vào `@Value` và `@ConfigurationProperties`.
- Kiểm tra kiểu dữ liệu và miền kết quả mà không phụ thuộc vào một con số ngẫu nhiên cố định.
- Hiểu thời điểm tạo giá trị, tính ổn định qua lần khởi động và ảnh hưởng của việc đọc lại property.
- Nhận diện giới hạn của random values khi dùng làm ID, mật khẩu hoặc khóa bảo mật.

## 2. RandomValuePropertySource nằm ở đâu?

`RandomValuePropertySource` là một `PropertySource` đặc biệt của Spring Boot. Nó xử lý các property có tên bắt đầu bằng `random.`. Spring Boot thêm property source này vào `Environment` trong quá trình chuẩn bị môi trường khởi động.

Bạn có thể tiêu thụ giá trị thông qua:

- Placeholder trong file cấu hình, ví dụ property `random.uuid`.
- Annotation `@Value`.
- `Environment.getProperty(...)`.
- Binding sang bean `@ConfigurationProperties`.

Luồng cơ bản:

~~~mermaid
flowchart TD
    A[application.yml or application.properties] --> B[Placeholder random.*]
    B --> C[Spring Environment]
    C --> D[RandomValuePropertySource]
    D --> E[Generate requested type]
    E --> F[Property placeholder resolution]
    F --> G[@Value / Binder / Environment]
    G --> H[Application bean]
~~~

Ví dụ:

~~~yaml
app:
  instance-id: "${random.uuid}"
  test-number: "${random.int}"
  sample-code: "${random.int[1000,9999]}"
~~~

Spring Boot phân giải các placeholder khi giá trị cấu hình được sử dụng. Bean nhận được kiểu dữ liệu tương ứng sau khi property resolver và conversion service xử lý giá trị.

### 2.1. Đây không phải một danh sách property tĩnh

Tên `random.*` là một không gian property đặc biệt được sinh theo yêu cầu. Bạn không cần khai báo từng khóa `random.int` hoặc `random.uuid` trong file cấu hình trước khi dùng.

Mỗi lần `RandomValuePropertySource` được hỏi về một property ngẫu nhiên, nó tạo kết quả theo hậu tố của tên property. Vì thế, không nên xem một placeholder UUID như một biến có giá trị cố định có thể tham chiếu ở mọi nơi và mọi thời điểm. Nếu cần dùng cùng một ID ở nhiều thành phần, hãy tạo một lần, lưu vào bean hoặc kho dữ liệu, rồi truyền giá trị đã tạo cho các thành phần đó.

### 2.2. Property source và cấu hình ghi đè

Random value được phân giải trong hệ thống thứ tự ưu tiên `PropertySource` của Spring Boot. Các nguồn cấu hình có độ ưu tiên cao hơn có thể cung cấp giá trị thay thế cho một property. Khi chẩn đoán giá trị không như mong đợi, hãy kiểm tra `Environment` và nguồn cấu hình thực tế, thay vì mặc định mọi placeholder đều được sinh lại.

## 3. Các kiểu giá trị được hỗ trợ

Spring Boot tài liệu hóa bốn nhóm giá trị chính:

| Placeholder | Kiểu/kết quả | Mục đích thường gặp |
| --- | --- | --- |
| `random.int` | `Integer` ngẫu nhiên trong toàn miền `int` | Số thử nghiệm, giá trị số tạm |
| `random.long` | `Long` ngẫu nhiên trong toàn miền `long` | Giá trị số lớn, dữ liệu thử nghiệm |
| `random.uuid` | UUID dạng chuỗi | ID tạm thời, correlation ID khi khởi động |
| `random.value` | Chuỗi ngẫu nhiên | Giá trị khởi tạo hoặc dữ liệu thử nghiệm |

Hai nhóm số có thể dùng hậu tố giới hạn miền. UUID và value không nhận tham số miền kiểu số.

### 3.1. random.int

`random.int` tạo một số nguyên Java `int`. Miền của kiểu `int` là:

~~~text
-2,147,483,648 đến 2,147,483,647
~~~

Khi không chỉ định giới hạn, giá trị có thể âm, bằng 0 hoặc dương. Không giả định `random.int` chỉ tạo số dương.

~~~yaml
app:
  random-int: "${random.int}"
~~~

Khi bind vào Java:

~~~java
@Value("${app.random-int}")
private int randomInt;
~~~

### 3.2. random.long

`random.long` tạo một số nguyên Java `long` trong toàn miền 64 bit có dấu:

~~~text
-9,223,372,036,854,775,808
đến
 9,223,372,036,854,775,807
~~~

~~~yaml
app:
  random-long: "${random.long}"
~~~

Kiểu Java tương ứng:

~~~java
@Value("${app.random-long}")
private long randomLong;
~~~

Chọn `long` khi property cần miền số lớn hơn `int`. Nếu nghiệp vụ cần một miền cụ thể, hãy dùng cú pháp giới hạn thay vì lấy toàn miền rồi tự sửa kết quả.

### 3.3. random.uuid

`random.uuid` tạo một UUID và trả về dạng chuỗi chuẩn. UUID thông dụng có dạng:

~~~text
xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx
~~~

Các ký tự đại diện cho chữ số hex; dạng UUID v4 có nhóm version là `4` và nhóm variant theo quy tắc UUID.

~~~yaml
app:
  instance-id: "${random.uuid}"
  correlation-seed: "${random.uuid}"
~~~

Trong Java:

~~~java
@Value("${app.instance-id}")
private UUID instanceId;
~~~

Spring có thể chuyển chuỗi UUID sang kiểu `java.util.UUID` khi bind. Nếu cần kiểm soát rõ ràng, có thể nhận `String` rồi gọi `UUID.fromString(...)`.

UUID phù hợp cho mã định danh cần xác suất trùng rất thấp. Nó không phải số thứ tự tăng dần và không nên được dùng thay cho khóa bí mật chuyên dụng.

### 3.4. random.value

`random.value` tạo một giá trị ngẫu nhiên dạng chuỗi. Trong implementation Spring Boot 4.1.2, cơ chế này tạo 16 byte ngẫu nhiên rồi biểu diễn thành 32 ký tự hexadecimal chữ thường.

~~~yaml
app:
  sample-token: "${random.value}"
~~~

Định dạng đầu ra cụ thể cần được đối chiếu với phiên bản Spring Boot đang chạy. Không tự viết code phụ thuộc vào một độ dài hoặc bảng ký tự nếu ứng dụng phải chạy trên nhiều release train khác nhau.

## 4. Cú pháp giới hạn miền cho int và long

`random.int` và `random.long` hỗ trợ hai dạng giới hạn:

1. Một cận: `random.int(10)`.
2. Hai cận: `random.int[1024,65536]`.

Ký tự mở và đóng có thể là bất kỳ ký tự nào theo cú pháp parser; tài liệu thường dùng ngoặc tròn hoặc ngoặc vuông để dễ đọc. Dù dùng ký tự nào, quy tắc cận dưới/cận trên vẫn như nhau.

### 4.1. Một cận: từ 0 đến cận trên

Với placeholder `random.int(10)`, `10` là cận trên loại trừ. Kết quả thuộc miền:

~~~text
[0, 10) = 0, 1, 2, 3, 4, 5, 6, 7, 8, 9
~~~

Tương tự:

~~~yaml
app:
  retry-sample: "${random.int(5)}"
  worker-sample: "${random.long(100000)}"
~~~

`random.int(5)` chỉ có thể tạo `0` đến `4`. `random.long(100000)` tạo số `long` từ `0` đến `99999`.

### 4.2. Hai cận: min bao gồm, max loại trừ

Với placeholder `random.int[1024,65536]`, `1024` là cận dưới được bao gồm; `65536` là cận trên bị loại. Miền kết quả:

~~~text
[1024, 65536)
~~~

Nghĩa là số nhỏ nhất có thể nhận là `1024` và số lớn nhất là `65535`.

~~~yaml
app:
  port-candidate: "${random.int[10000,20000]}"
  batch-size: "${random.int[20,101]}"
  long-sequence-sample: "${random.long[10000000000,20000000000]}"
~~~

| Property | Miền kết quả |
| --- | --- |
| `port-candidate` | `10000` đến `19999` |
| `batch-size` | `20` đến `100` |
| `long-sequence-sample` | `10000000000` đến `19999999999` |

### 4.3. Cận âm và miền có cả số âm

Hai cận có thể là số âm nếu cận dưới nhỏ hơn cận trên:

~~~yaml
app:
  signed-offset: "${random.int[-10,11]}"
  signed-long-offset: "${random.long(-5000000000,5000000001)}"
~~~

`signed-offset` có thể nhận các giá trị từ `-10` đến `10`. `signed-long-offset` có thể nhận từ `-5000000000` đến `5000000000`.

Điều kiện quan trọng là `min < max`. Nếu hai cận bằng nhau hoặc cận dưới lớn hơn cận trên, miền không hợp lệ và việc tạo giá trị sẽ thất bại.

### 4.4. Cú pháp tương đương với properties

~~~properties
app.random-int=${random.int}
app.random-long=${random.long}
app.random-uuid=${random.uuid}
app.random-value=${random.value}
app.number-under-ten=${random.int(10)}
app.number-in-range=${random.int[1024,65536]}
app.negative-range=${random.int[-10,11]}
~~~

Trong YAML, nên đặt placeholder trong dấu nháy kép để parser xử lý các ký tự ngoặc và dấu phẩy nhất quán:

~~~yaml
app:
  number-under-ten: "${random.int(10)}"
  number-in-range: "${random.int[1024,65536]}"
~~~

## 5. Bảng tổng hợp cú pháp và miền giá trị

| Cú pháp | Kiểu | Cận dưới | Cận trên | Miền |
| --- | --- | ---: | ---: | --- |
| `random.int` | int | Giá trị nhỏ nhất của int | Giá trị lớn nhất của int | Toàn miền int |
| `random.int(10)` | int | 0 | 10 | `[0,10)` |
| `random.int[10,20]` | int | 10 | 20 | `[10,20)` |
| `random.long` | long | Giá trị nhỏ nhất của long | Giá trị lớn nhất của long | Toàn miền long |
| `random.long(100)` | long | 0 | 100 | `[0,100)` |
| `random.long[1000,2000]` | long | 1000 | 2000 | `[1000,2000)` |
| `random.uuid` | String/UUID | Không áp dụng | Không áp dụng | UUID |
| `random.value` | String | Không áp dụng | Không áp dụng | Chuỗi ngẫu nhiên |

Ký hiệu `[min,max)` có nghĩa là min được bao gồm, max không được bao gồm. Miền `[10,20)` có đúng 10 giá trị nguyên.

## 6. Dùng random values trong Spring configuration

### 6.1. Cấu hình YAML đầy đủ

~~~yaml
app:
  runtime:
    instance-id: "${random.uuid}"
    startup-number: "${random.int}"
    startup-counter: "${random.long}"
    test-code: "${random.int[100000,999999]}"
    sample-value: "${random.value}"
    retry-count: "${random.int(5)}"
~~~

Ví dụ này cho thấy nhiều kiểu có thể được khai báo cùng lúc. Giá trị được phân giải khi property được tiêu thụ trong quá trình khởi động hoặc khi có thành phần truy vấn nó.

### 6.2. Kết hợp prefix và suffix

Có thể kết hợp một giá trị ngẫu nhiên với chuỗi cố định:

~~~yaml
app:
  instance-name: "worker-${random.int[100,1000]}"
  request-seed: "req-${random.uuid}"
  temporary-code: "TMP-${random.int[100000,1000000]}"
~~~

Placeholder được thay bằng kết quả ngẫu nhiên, phần chuỗi còn lại được giữ nguyên.

### 6.3. Dùng giá trị mặc định cho property nghiệp vụ

Có thể dùng random placeholder làm giá trị mặc định trong placeholder khác:

~~~yaml
app:
  instance-id: "${APP_INSTANCE_ID:${random.uuid}}"
~~~

Nếu nguồn cấu hình cung cấp `APP_INSTANCE_ID`, giá trị được cung cấp sẽ được dùng. Nếu không có, Spring Boot phân giải fallback random UUID.

Đây là cách kết hợp cấu hình bên ngoài với giá trị mặc định. Nếu ID phải ổn định qua restart, hãy cấp ID từ nền tảng triển khai hoặc lưu ID đã sinh; không dựa vào fallback ngẫu nhiên.

## 7. Bind sang Java bằng @Value và @ConfigurationProperties

### 7.1. Dùng @Value

~~~java
import java.util.UUID;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class StartupValues {

    @Value("${app.runtime.instance-id}")
    private UUID instanceId;

    @Value("${app.runtime.startup-number}")
    private int startupNumber;

    @Value("${app.runtime.startup-counter}")
    private long startupCounter;

    @Value("${app.runtime.test-code}")
    private int testCode;

    public UUID getInstanceId() {
        return instanceId;
    }

    public int getStartupNumber() {
        return startupNumber;
    }

    public long getStartupCounter() {
        return startupCounter;
    }

    public int getTestCode() {
        return testCode;
    }
}
~~~

Spring chuyển kết quả property sang kiểu đích khi conversion được hỗ trợ. Nếu placeholder số nằm ngoài miền của kiểu Java đích, việc bind có thể thất bại.

### 7.2. Dùng @ConfigurationProperties

Khi có nhiều giá trị liên quan, gom chúng thành một nhóm cấu hình:

~~~java
package com.example.demo.config;

import java.util.UUID;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.runtime")
public record RuntimeProperties(
        UUID instanceId,
        int startupNumber,
        long startupCounter,
        int testCode,
        String sampleValue,
        int retryCount) {
}
~~~

Đăng ký configuration properties bằng scanning:

~~~java
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class DemoApplication {
}
~~~

Với YAML ở phần trước, Spring Boot phân giải placeholder và bind các giá trị vào record. Đây là cấu hình được tạo khi application context khởi động; record không tự sinh lại các giá trị mỗi lần getter được gọi.

### 7.3. Truy vấn Environment trực tiếp

~~~java
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class RandomValueReader {

    private final Environment environment;

    public RandomValueReader(Environment environment) {
        this.environment = environment;
    }

    public int nextSample() {
        return environment.getProperty(
                "random.int[10,20]", Integer.class);
    }
}
~~~

Đoạn code minh họa việc đọc một random property theo tên. Mỗi lần gọi lại property source có thể tạo một kết quả mới. Nếu cần dùng cùng một kết quả cho nhiều thao tác, hãy lưu kết quả trả về vào biến hoặc bean thay vì gọi `getProperty` nhiều lần.

## 8. Thời điểm tạo và tính ổn định của giá trị

### 8.1. Giá trị không phải cấu hình cố định

Random value được tạo khi property source xử lý yêu cầu đọc property. Một giá trị được bind vào field hoặc constructor của bean thường được giữ trong instance bean đó sau khi bind. Tuy nhiên, nếu một thành phần tiếp tục đọc trực tiếp `Environment`, lần đọc tiếp theo có thể nhận kết quả ngẫu nhiên mới.

~~~java
int first = environment.getProperty("random.int", Integer.class);
int second = environment.getProperty("random.int", Integer.class);
~~~

Không nên giả định `first` và `second` bằng nhau. Nếu nghiệp vụ yêu cầu một giá trị duy nhất:

~~~java
int startupSeed = environment.getProperty(
        "random.int[1000,2000]", Integer.class);

processA(startupSeed);
processB(startupSeed);
~~~

### 8.2. Qua lần khởi động mới

Random values không phải dữ liệu được lưu bền vững. Khi ứng dụng khởi động lại và property được phân giải lại, kết quả có thể khác. Điều này hữu ích cho dữ liệu tạm thời nhưng không phù hợp với ID cần giữ nguyên để hệ thống khác tham chiếu lâu dài, mã hóa dữ liệu cần dùng lại cùng một key sau restart, password cần chia sẻ giữa nhiều replica hoặc giá trị cần tái tạo chính xác trong lần replay.

Nếu cần ổn định, hãy tạo giá trị bên ngoài ứng dụng, lưu vào database/secret manager/config store, rồi inject lại như một property thông thường.

### 8.3. Spring Cloud refresh và random values

Spring Cloud Context có thể refresh các nguồn cấu hình và rebind bean. Tuy nhiên, không nên xem `random.*` là một nguồn ID ổn định hoặc một secret store có vòng đời được quản lý. Nếu một bean được rebind hoặc một placeholder được phân giải lại, giá trị random có thể được tạo lại tùy đường đọc và vòng đời bean. Với ID hoặc key cần ổn định, hãy lưu giá trị ở nguồn cấu hình bền vững trước khi refresh.

## 9. Kiểm tra miền giá trị và cách viết test

Không nên viết test yêu cầu random property phải trả về đúng một con số ngẫu nhiên cụ thể. Test nên xác minh kiểu, miền giá trị và định dạng UUID.

### 9.1. Unit test kiểm tra cận

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.env.RandomValuePropertySource;
import org.springframework.core.env.StandardEnvironment;

import static org.assertj.core.api.Assertions.assertThat;

class RandomRangeTest {

    @Test
    void generatesIntegerWithinInclusiveExclusiveRange() {
        StandardEnvironment environment = new StandardEnvironment();
        RandomValuePropertySource.addToEnvironment(environment);

        for (int i = 0; i < 100; i++) {
            Integer value = environment.getProperty(
                    "random.int[10,20]", Integer.class);

            assertThat(value).isNotNull();
            assertThat(value).isBetween(10, 19);
        }
    }
}
~~~

Test dùng vòng lặp để kiểm tra miền, không kiểm tra tính phân phối thống kê. Không thể chứng minh chất lượng ngẫu nhiên bằng vài chục lần lấy mẫu; kiểm thử ở đây chỉ xác nhận hợp đồng cận.

### 9.2. Kiểm tra UUID và random.value

~~~java
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.boot.env.RandomValuePropertySource;
import org.springframework.core.env.StandardEnvironment;

import static org.assertj.core.api.Assertions.assertThat;

class RandomFormatTest {

    @Test
    void createsUuidAndRandomString() {
        StandardEnvironment environment = new StandardEnvironment();
        RandomValuePropertySource.addToEnvironment(environment);

        String uuid = environment.getProperty("random.uuid");
        String value = environment.getProperty("random.value");

        assertThat(UUID.fromString(uuid)).isNotNull();
        assertThat(value).isNotBlank();
    }
}
~~~

Nếu muốn kiểm tra chính xác độ dài/charset của `random.value`, hãy viết test gắn với phiên bản Spring Boot cụ thể và implementation đã được xác minh. Đừng biến chi tiết implementation thành hợp đồng tương thích cho mọi release train.

### 9.3. Kiểm tra cấu hình YAML khi chạy ứng dụng

Với ứng dụng có Actuator, endpoint `/actuator/env` có thể giúp chẩn đoán nguồn property và giá trị đã được phân giải. Endpoint này có thể hiển thị dữ liệu cấu hình nhạy cảm; chỉ expose trong management network và dùng cơ chế sanitization, authorization phù hợp. Trong test, ưu tiên kiểm tra trực tiếp bean cấu hình hoặc `Environment` thay vì mở endpoint quản trị.

## 10. Lỗi thường gặp khi đặt phạm vi

| Cú pháp | Vấn đề | Kết quả cần hiểu |
| --- | --- | --- |
| `random.int(0)` | Cận trên một tham số phải lớn hơn 0 | Miền rỗng, không thể sinh giá trị |
| `random.int[10,10]` | Cận dưới bằng cận trên | Miền rỗng |
| `random.int[20,10]` | Cận dưới lớn hơn cận trên | Miền không hợp lệ |
| `random.int[10]` | Hợp lệ | `[0,10)` |
| `random.int[-5,5]` | Hợp lệ | `[-5,5)` |
| `random.long[100,200]` | Hợp lệ | `[100,200)` |
| `random.uuid[10,20]` | Không phải cú pháp miền được hỗ trợ cho UUID | Không dùng range với UUID |

Với cú pháp một cận, giá trị cận phải dương. Với hai cận, cận dưới phải nhỏ hơn cận trên. Các số cũng phải parse được vào kiểu tương ứng; giá trị vượt quá miền `int` hoặc `long` sẽ gây lỗi phân tích.

### 10.1. Nhầm lẫn cận trên bao gồm

Một lỗi phổ biến là nghĩ `random.int[1,100]` có thể trả về `100`. Thực tế miền là `[1,100)`, nên kết quả lớn nhất là `99`.

Nếu cần các số từ 1 đến 100, hãy đặt cận trên là 101:

~~~yaml
app:
  percentage: "${random.int[1,101]}"
~~~

## 11. Giới hạn bảo mật và CVE-2026-40975

Random values là tiện ích cấu hình, nhưng không phải mọi kiểu đều phù hợp làm bí mật. Chất lượng của nguồn ngẫu nhiên cũng phụ thuộc phiên bản Spring Boot.

### 11.1. Không dùng int/long làm secret

`random.int` chỉ có 32 bit và `random.long` chỉ có 64 bit. Chúng có miền số hữu hạn, có thể đoán hoặc vét cạn trong một số kịch bản. Dù nguồn phát sinh là bộ sinh ngẫu nhiên mật mã, miền số này vẫn không phù hợp để làm password, API key hoặc encryption key.

Không dùng:

~~~yaml
spring:
  security:
    user:
      password: "${random.int}"
app:
  signing-key: "${random.long}"
~~~

### 11.2. CVE-2026-40975 ảnh hưởng random.value ở các bản cũ

Spring đã công bố `CVE-2026-40975` vào ngày 23-04-2026. Các phiên bản Spring Boot bị ảnh hưởng dùng PRNG yếu cho `random.value`, nên giá trị này không phù hợp làm secret. Advisory xác nhận `random.uuid` không bị ảnh hưởng; `random.int` và `random.long` không nên dùng làm secret trong bất kỳ phiên bản nào vì miền số có thể đoán được.

Trong mã nguồn Spring Boot 4.1.2, `RandomValuePropertySource` dùng `SecureRandom` cho bộ sinh nền. Nâng cấp lên bản sửa lỗi tương ứng là biện pháp khắc phục mà advisory Spring đưa ra; không nên tự thay generator hoặc vá class này trong ứng dụng.

Các nhánh và bản vá được Spring công bố:

| Nhánh Spring Boot | Phiên bản bị ảnh hưởng | Phiên bản sửa lỗi |
| --- | --- | --- |
| 4.0.x | 4.0.0–4.0.5 | 4.0.6 |
| 3.5.x | 3.5.0–3.5.13 | 3.5.14 |
| 3.4.x | 3.4.0–3.4.15 | 3.4.16 (Enterprise Support) |
| 3.3.x | 3.3.0–3.3.18 | 3.3.19 (Enterprise Support) |
| 2.7.x | 2.7.0–2.7.32 | 2.7.33 (Enterprise Support) |

Các phiên bản đã hết hỗ trợ cũng nằm trong nhóm cần được đánh giá. Hãy kiểm tra dependency tree để xác định chính xác phiên bản Spring Boot runtime, không chỉ nhìn version của Spring Cloud BOM.

### 11.3. Khuyến nghị cho secret thật

- Dùng Vault, cloud secret manager, KMS hoặc cơ chế quản lý secret của nền tảng.
- Tạo khóa bằng API mật mã phù hợp khi ứng dụng thực sự cần tự sinh key material.
- Không lưu secret vừa sinh vào log, Actuator endpoint hoặc file cấu hình được commit.
- Nếu dùng `random.value` trong ngữ cảnh nhạy cảm, phải dùng phiên bản đã vá và đánh giá vòng đời, nơi lưu trữ và cách chia sẻ giá trị.
- Không dùng UUID làm encryption key chỉ vì UUID không bị CVE này ảnh hưởng.

`random.uuid` phù hợp hơn cho identifier. Khóa mã hóa cần độ dài, thuật toán, nguồn entropy, lưu trữ và rotation theo chuẩn mật mã; không nên thay bằng một placeholder cấu hình.

## 12. Ví dụ hoàn chỉnh: tạo mã thử nghiệm lúc khởi động

Giả sử một worker cần ID riêng cho lần khởi động, số lần retry mẫu từ 1 đến 5 và mã thử nghiệm gồm sáu chữ số.

Cấu hình:

~~~yaml
worker:
  startup:
    id: "${random.uuid}"
    retry-limit: "${random.int[1,6]}"
    test-code: "${random.int[100000,1000000]}"
~~~

Bean cấu hình:

~~~java
package com.example.worker;

import java.util.UUID;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "worker.startup")
public record WorkerStartupProperties(
        UUID id,
        int retryLimit,
        int testCode) {
}
~~~

Đăng ký:

~~~java
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class WorkerApplication {

    public static void main(String[] args) {
        SpringApplication.run(WorkerApplication.class, args);
    }
}
~~~

Kiểm tra trong service:

~~~java
import org.springframework.stereotype.Service;

@Service
public class WorkerService {

    private final WorkerStartupProperties properties;

    public WorkerService(WorkerStartupProperties properties) {
        this.properties = properties;
    }

    public void start() {
        System.out.println("workerId=" + properties.id());
        System.out.println("retryLimit=" + properties.retryLimit());
        System.out.println("testCode=" + properties.testCode());
    }
}
~~~

Trong production, tránh log ID hoặc mã nếu chúng được dùng như credential. Ví dụ trên dành cho dữ liệu khởi tạo không nhạy cảm và minh họa cách bind giá trị.

## 13. Troubleshooting

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Placeholder vẫn còn dạng random.int | Property chưa được phân giải trong nguồn/đường đọc hiện tại hoặc placeholder bị escape | Kiểm tra file cấu hình, dấu nháy và cách tiêu thụ property |
| Giá trị không nằm trong miền mong đợi | Đọc nhầm cận trên là inclusive | Nhớ rằng max bị loại; dùng max = giá trị mong muốn + 1 |
| Startup lỗi với range | Cận không hợp lệ hoặc số vượt miền kiểu | Kiểm tra min < max, bound dương ở cú pháp một cận và giới hạn int/long |
| Bind vào UUID thất bại | Giá trị không phải UUID hợp lệ hoặc property bị ghi đè | Kiểm tra nguồn property và gọi `UUID.fromString()` trong test |
| Hai lần đọc cho hai kết quả khác nhau | Property source sinh giá trị khi được đọc | Lưu kết quả vào bean/biến nếu cần dùng lại |
| Giá trị thay đổi sau restart | Random value không được lưu bền vững | Dùng ID/secret được lưu ở external store nếu cần ổn định |
| random.value được dùng làm secret trên Boot cũ | Phiên bản có thể bị CVE-2026-40975 | Kiểm tra Boot version và nâng lên bản đã vá |
| Không thể dùng int/long làm key | Miền số không đủ cho mục đích mật mã | Dùng secret manager hoặc API tạo key phù hợp |

### 13.1. Quy trình chẩn đoán

1. Xác định placeholder đầy đủ và kiểu mong đợi.
2. Kiểm tra dấu ngoặc, số lượng cận và quan hệ min/max.
3. Kiểm tra giá trị có bị nguồn cấu hình ưu tiên cao hơn ghi đè không.
4. Kiểm tra kiểu đích trong `@Value` hoặc `@ConfigurationProperties`.
5. Gọi `Environment.getProperty()` trong test để xác minh kiểu và miền.
6. Kiểm tra phiên bản Spring Boot runtime nếu giá trị được dùng trong ngữ cảnh bảo mật.

## 14. Bài tập thực hành

### Bài 1 — Phân loại kiểu

Khai báo bốn property: một `int` không giới hạn, một `long` không giới hạn, một UUID và một giá trị random dạng chuỗi. Bind chúng vào bean Java và xác nhận kiểu dữ liệu.

### Bài 2 — Kiểm tra cận

Tạo ba property `random.int(10)`, `random.int[10,20]` và `random.long[-100,100]`. Lấy mỗi giá trị 100 lần trong test và xác nhận mọi kết quả nằm trong miền tương ứng.

### Bài 3 — Sửa lỗi off-by-one

Yêu cầu tạo phần trăm từ 1 đến 100. Viết placeholder đúng và giải thích vì sao cận trên phải là 101.

### Bài 4 — Ổn định qua nhiều lần đọc

Đọc `random.uuid` hai lần từ `Environment` và so sánh. Sau đó đọc một lần, lưu vào field của bean rồi sử dụng field đó ở hai method. Giải thích khác biệt giữa việc đọc lại property và dùng lại giá trị đã lưu.

### Bài 5 — Đánh giá bảo mật

Kiểm tra một phiên bản Spring Boot thuộc danh sách ảnh hưởng của CVE-2026-40975. Xác định bản vá tương ứng và giải thích vì sao `random.int`/`random.long` không phải lựa chọn tạo secret.

**Tiêu chí hoàn thành:** bạn có thể chọn đúng kiểu random, tính chính xác miền `[min,max)`, bind sang Java, kiểm thử cận và xác định khi nào phải dùng secret manager thay cho random placeholder.

## 15. Tổng kết

Spring Boot cung cấp `RandomValuePropertySource` để phân giải các placeholder `random.*` trong Environment. Bốn nhóm thường dùng là `int`, `long`, `uuid` và `value`. Hai kiểu số hỗ trợ miền không giới hạn, cú pháp một cận `[0,n)` và cú pháp hai cận `[min,max)`. Cận dưới được bao gồm, cận trên bị loại.

Các giá trị có thể được dùng trong YAML, properties, `@Value`, `Environment` và `@ConfigurationProperties`. Giá trị được tạo khi property source xử lý yêu cầu; nếu cần dùng cùng một kết quả nhiều lần hoặc cần ổn định qua restart, hãy lưu và quản lý giá trị đó ở một nơi phù hợp.

Không dùng `int` hoặc `long` làm secret. Với `random.value`, cần kiểm tra phiên bản Spring Boot do CVE-2026-40975 ảnh hưởng các nhánh cũ; nâng cấp lên bản đã vá và dùng secret manager/KMS cho bí mật có giá trị lâu dài.

## Tài liệu tham khảo

- [Spring Boot — Externalized Configuration, Configuring Random Values](https://docs.spring.io/spring-boot/reference/features/external-config.html): ví dụ `random.int`, `random.long`, `random.uuid`, `random.value` và quy tắc cận.
- [RandomValuePropertySource API](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/env/RandomValuePropertySource.html): các kiểu được hỗ trợ và cú pháp miền số.
- [RandomValuePropertySource source, Spring Boot 4.1.2](https://github.com/spring-projects/spring-boot/blob/v4.1.2/spring-boot-project/spring-boot/src/main/java/org/springframework/boot/env/RandomValuePropertySource.java): implementation tạo giá trị, xử lý range và biểu diễn random bytes.
- [Spring Security Advisory — CVE-2026-40975](https://spring.io/security/cve-2026-40975/): các phiên bản Spring Boot bị ảnh hưởng, bản sửa lỗi và lưu ý về việc dùng random values làm secret.
- [Spring Boot 4.0.6 release announcement](https://spring.io/blog/2026/04/23/spring-boot-4-0-6-available-now/): xác nhận bản phát hành sửa CVE-2026-40975.

Luôn kiểm tra phiên bản Spring Boot runtime thực tế và ma trận tương thích của Spring Cloud BOM. Cú pháp range ổn định trong tài liệu Spring Boot, nhưng chi tiết biểu diễn `random.value` và mức an toàn phụ thuộc phiên bản.
