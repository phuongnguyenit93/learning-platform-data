# Truyền tham số `--key=value` và phân biệt với đối số thông thường trong Spring Boot

## 1. Vì sao cần phân biệt các đối số khi khởi chạy?

Một ứng dụng Spring Boot có thể được chạy như sau:

~~~bash
java -jar demo.jar --server.port=9090 --app.batch-size=200 import customers.csv
~~~

Sau tên JAR có bốn chuỗi được truyền tới chương trình:

~~~text
--server.port=9090
--app.batch-size=200
import
customers.csv
~~~

Nhìn chúng đều là “tham số dòng lệnh”, nhưng Spring Boot xử lý theo **hai nhóm khác nhau**:

- `--server.port=9090` và `--app.batch-size=200` là **đối số tùy chọn** (*option arguments*). Mỗi đối số có tên và giá trị. Spring Boot mặc định đưa chúng vào `Environment` như các thuộc tính cấu hình.
- `import` và `customers.csv` là **đối số thông thường** (*non-option arguments*). Chúng biểu diễn lệnh nghiệp vụ và dữ liệu đầu vào của chương trình; Spring Boot không tự chuyển chúng thành thuộc tính có tên trong `Environment`.

Sự phân biệt này đặc biệt hữu ích khi ứng dụng vừa có cấu hình kỹ thuật vừa nhận một công việc cần thực hiện: chọn profile, địa chỉ dịch vụ, giới hạn xử lý, rồi nhận tên tác vụ và đường dẫn tệp.

Mục tiêu của bài:

1. Hiểu cú pháp `--key=value`, `--flag`, `key=value` và các đối số không có tiền tố.
2. Biết đối số nào tham gia `Environment`, đối số nào chỉ thuộc danh sách đầu vào.
3. Đọc chính xác chúng qua `ApplicationArguments`, `Environment`, `@Value` và `@ConfigurationProperties`.
4. Phân biệt tham số Spring Boot, Java System properties và biến môi trường của hệ điều hành.
5. Biết cách truyền chuỗi có dấu cách, nhiều đối số, profile và tùy chọn khi chạy từ terminal, IDE hoặc Gradle.
6. Nhận diện lỗi thường gặp khi viết `--key value` thay vì `--key=value` hoặc nhầm một đối số thông thường với thuộc tính cấu hình.

## 2. Luồng đi của tham số từ terminal đến ứng dụng

Khi gõ lệnh trong shell, shell chia câu lệnh thành các đối số theo quy tắc trích dẫn. JVM nhận các tùy chọn riêng của Java, sau đó chuyển các chuỗi sau tên JAR tới phương thức `main(String[] args)` của ứng dụng.

~~~text
Terminal / shell
       |
       | java -Duser.timezone=UTC -jar demo.jar --app.mode=fast import data.csv
       v
JVM xử lý -Duser.timezone=UTC và -jar demo.jar
       |
       | main(String[] args):
       |   ["--app.mode=fast", "import", "data.csv"]
       v
SpringApplication.run(DemoApplication.class, args)
       |
       +--> ApplicationArguments
       |      +--> option: app.mode = ["fast"]
       |      +--> non-option: ["import", "data.csv"]
       |
       +--> Command-line PropertySource (mặc định)
              +--> app.mode = fast
                        |
                        v
                   Environment
                        |
                        +--> getProperty("app.mode")
                        +--> @Value
                        +--> @ConfigurationProperties
~~~

Lệnh `-Duser.timezone=UTC` được JVM xử lý thành một **Java System property**, không phải một phần tử `--key=value` trong `args`. Ngược lại, `--app.mode=fast` là đối số ứng dụng mà Spring Boot có thể chuyển thành thuộc tính trong `Environment`.

Lớp khởi chạy tối thiểu:

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

Việc **truyền nguyên `args`** vào `SpringApplication.run(...)` rất quan trọng. Nếu gọi một API khởi chạy khác mà bỏ qua `args`, các tham số bạn gõ sau tên JAR sẽ không được Spring Boot nhận theo luồng thông thường.

## 3. Cú pháp của một đối số tùy chọn

Dạng thông dụng của Spring Boot là:

~~~text
--key=value
~~~

Trong đó:

- `--`: dấu hiệu nhận diện **option argument**.
- `key`: tên tùy chọn hoặc tên thuộc tính.
- `=`: ranh giới giữa tên và giá trị.
- `value`: giá trị được truyền dưới dạng chuỗi; Spring Boot có thể chuyển kiểu sau đó.

Ví dụ:

~~~bash
java -jar demo.jar --server.port=9090 --spring.profiles.active=dev --app.retries=3
~~~

Spring Boot mặc định tạo các thuộc tính cấu hình:

| Tên thuộc tính | Giá trị chuỗi ban đầu | Mục đích |
| --- | --- | --- |
| `server.port` | `9090` | Thiết lập cổng máy chủ nhúng. |
| `spring.profiles.active` | `dev` | Kích hoạt profile. |
| `app.retries` | `3` | Cấu hình riêng của ứng dụng. |

Giá trị chuỗi có thể được chuyển sang kiểu đích khi gắn cấu hình: `server.port` thành số, `app.retries` thành `int` nếu có lớp `@ConfigurationProperties` thích hợp.

**Không phải mọi khóa `--key=value` đều được Spring Boot hiểu như thiết lập tích hợp.** Ví dụ `--app.retries=3` là thuộc tính do ứng dụng tự đặt; muốn sử dụng, mã của bạn cần đọc từ `Environment`, gắn vào bean hoặc xử lý theo quy tắc của ứng dụng.

### Tên khóa có dấu chấm và gạch ngang

Cách viết phổ biến là dùng cùng tên thuộc tính trong tệp YAML/Properties:

~~~yaml
app:
  export:
    output-dir: "./out"
    max-items: 100
~~~

Có thể ghi đè bằng:

~~~bash
java -jar demo.jar --app.export.output-dir=./results --app.export.max-items=500
~~~

Với `@ConfigurationProperties(prefix = "app.export")`, Spring Boot thực hiện gắn kết linh hoạt (*relaxed binding*) giữa tên cấu hình và thuộc tính Java tương ứng. Với `Environment.getProperty(...)`, hãy ưu tiên tên khóa chuẩn mà bạn thật sự khai báo.

## 4. Đối số thông thường (non-option argument) là gì?

Đối số không được Spring Boot phân loại là option sẽ thuộc nhóm **non-option**. Chúng thường là từ khóa nghiệp vụ, tên tệp, thư mục hoặc thông tin mà ứng dụng tự diễn giải theo vị trí.

Ví dụ:

~~~bash
java -jar demo.jar import customers.csv
~~~

Danh sách non-option là:

~~~text
["import", "customers.csv"]
~~~

Spring Boot không tự tạo thuộc tính có tên `import` hoặc `customers.csv`. Ứng dụng có thể quy ước:

- Phần tử thứ nhất: tên hành động, ví dụ `import`, `export` hoặc `validate`.
- Phần tử thứ hai: đường dẫn tệp.
- Phần tử tiếp theo: các tham số vị trí khác.

Đó là **quy ước do bạn viết trong mã ứng dụng**, không phải phép ánh xạ tự động thành thuộc tính Config Data.

### Một chuỗi dạng key=value chưa chắc là option

Lệnh:

~~~bash
java -jar demo.jar app.retries=3
~~~

chứa chuỗi `app.retries=3` **không có hai dấu gạch ngang đầu**. Spring Boot xem đây là non-option. Nó không tương đương với:

~~~bash
java -jar demo.jar --app.retries=3
~~~

Ở lệnh thứ hai, `app.retries` là một option và mặc định tham gia `Environment`.

Điều này giải thích lỗi thường gặp: người vận hành nghĩ “mình đã truyền `app.retries=3` rồi”, nhưng `Environment.getProperty("app.retries")` vẫn trả về giá trị trong tệp hoặc `null` vì thiếu `--`.

## 5. `--key value` không phải dạng ghép tên–giá trị

Một nhầm lẫn rất phổ biến:

~~~bash
java -jar demo.jar --app.mode fast
~~~

Ở dạng cú pháp `ApplicationArguments` của Spring Boot, chuỗi `--app.mode` là **option không có giá trị**, còn `fast` là một **non-option argument** riêng.

Nó khác với:

~~~bash
java -jar demo.jar --app.mode=fast
~~~

Trong ví dụ thứ hai, `app.mode` có giá trị `fast`.

Để biết vì sao, nhìn các chuỗi được shell truyền đến Java:

| Lệnh sau tên JAR | Mảng `args` | Diễn giải |
| --- | --- | --- |
| `--app.mode=fast` | `["--app.mode=fast"]` | Một option có giá trị `fast`. |
| `--app.mode fast` | `["--app.mode", "fast"]` | Một option không có giá trị và một non-option `fast`. |
| `app.mode=fast` | `["app.mode=fast"]` | Một non-option, không thêm thuộc tính CLI. |
| `fast` | `["fast"]` | Một non-option. |
| `--verbose` | `["--verbose"]` | Một option có mặt nhưng không kèm giá trị. |
| `--verbose=true` | `["--verbose=true"]` | Một option có giá trị chuỗi `true`. |

Đối với cấu hình cần giá trị rõ ràng, hãy dùng `--key=value`. Cú pháp `--flag` thuận tiện cho tình huống chỉ cần kiểm tra sự có mặt bằng `ApplicationArguments.containsOption(...)`.

### Option không có giá trị có nghĩa gì?

Lệnh:

~~~bash
java -jar demo.jar --verbose
~~~

cho biết **option `verbose` tồn tại**. Nó không đồng nghĩa với việc mọi mã Java tự động nhận Boolean `true` từ một thuộc tính được gắn kết. Nếu bạn muốn một cờ cấu hình kiểu Boolean có ý nghĩa rõ ràng, thường nên viết:

~~~bash
java -jar demo.jar --app.verbose=true
~~~

Với cờ nghiệp vụ chỉ cần hiện diện, dùng:

~~~java
boolean verboseRequested = args.containsOption("verbose");
~~~

Trong đoạn trên, `args` là đối tượng `ApplicationArguments` được cung cấp cho ứng dụng.

## 6. ApplicationArguments: API để phân loại đối số

Spring Boot cung cấp giao diện `org.springframework.boot.ApplicationArguments`. Nó cho phép truy cập **mảng đầu vào gốc** và **các đối số đã phân loại**.

Các phương thức chính:

| Phương thức | Kết quả |
| --- | --- |
| `getSourceArgs()` | `String[]` đầu vào gốc của ứng dụng, trước khi phân loại. |
| `getOptionNames()` | Tập tên các option đã xuất hiện. |
| `containsOption("name")` | `true` nếu có option với tên đó. |
| `getOptionValues("name")` | Danh sách giá trị của option; xem chi tiết bên dưới. |
| `getNonOptionArgs()` | Danh sách đối số không phải option, theo thứ tự đầu vào. |

Bạn có thể tiêm `ApplicationArguments` vào một bean hoặc nhận nó trong `ApplicationRunner.run(...)`.

### Ví dụ chạy và đọc đối số

Chạy:

~~~bash
java -jar demo.jar --app.mode=fast --verbose import customers.csv
~~~

Một bean đọc dữ liệu:

~~~java
package com.example.demo;

import java.util.Arrays;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;

@Component
public class ArgumentReporter implements ApplicationRunner {

    @Override
    public void run(ApplicationArguments args) {
        System.out.println("Raw: " +
                Arrays.toString(args.getSourceArgs()));

        System.out.println("Option names: " +
                args.getOptionNames());

        System.out.println("app.mode values: " +
                args.getOptionValues("app.mode"));

        System.out.println("Verbose flag: " +
                args.containsOption("verbose"));

        System.out.println("Non-option: " +
                args.getNonOptionArgs());
    }
}
~~~

Kết quả về mặt nội dung:

~~~text
Raw: [--app.mode=fast, --verbose, import, customers.csv]
Option names: [app.mode, verbose]
app.mode values: [fast]
Verbose flag: true
Non-option: [import, customers.csv]
~~~

Tập `getOptionNames()` không nên được dùng như một danh sách có thứ tự cố định. Cách hiển thị tên trong `Set` có thể khác giữa các lần chạy; việc phân loại và các giá trị mới là điều cần quan tâm.

### Các trường hợp của getOptionValues

Giả sử ta đọc `args.getOptionValues("app.mode")`:

| Đối số đầu vào | `containsOption("app.mode")` | `getOptionValues("app.mode")` |
| --- | --- | --- |
| `--app.mode=fast` | `true` | `["fast"]` |
| `--app.mode=fast --app.mode=safe` | `true` | `["fast", "safe"]` |
| `--app.mode` | `true` | Danh sách rỗng `[]`. |
| Không truyền `--app.mode` | `false` | `null`. |
| `app.mode=fast` | `false` | `null`. |

Điểm cần nhớ: **không có option** và **có option nhưng không có giá trị** khác nhau. Một trường hợp trả về `null`, trường hợp kia trả về danh sách rỗng. Với `--key=` có dấu bằng nhưng không có nội dung, ứng dụng cần kiểm tra chuỗi rỗng theo nhu cầu nghiệp vụ.

### Đọc đối số một cách có kiểm soát

~~~java
import java.util.List;
import org.springframework.boot.ApplicationArguments;

public final class Options {

    private Options() {
    }

    public static String requiredSingleValue(
            ApplicationArguments args, String name) {

        List<String> values = args.getOptionValues(name);

        if (values == null || values.size() != 1
                || values.get(0).isBlank()) {
            throw new IllegalArgumentException(
                    "Yêu cầu đúng một giá trị cho --" + name + "=...");
        }

        return values.get(0);
    }
}
~~~

Cách này phù hợp khi một tham số **phải có đúng một giá trị**. Nó phát hiện thiếu option, option không có giá trị, giá trị trắng và trường hợp truyền nhiều lần.

Đối với cấu hình thông thường của Spring Boot, bạn không nhất thiết cần viết hàm trên; `@ConfigurationProperties` và cơ chế validation có thể xử lý kiểu dữ liệu và tính hợp lệ của thuộc tính. Hàm chỉ minh họa cách đọc tham số như một giao diện lệnh do ứng dụng tự định nghĩa.

## 7. Tùy chọn lặp lại nhiều lần

Spring Boot cho phép một tên option xuất hiện nhiều lần trong chuỗi đầu vào:

~~~bash
java -jar demo.jar --tag=java --tag=spring --tag=boot import source.csv
~~~

Với `ApplicationArguments`:

~~~java
List<String> tags = args.getOptionValues("tag");
~~~

Danh sách `tags` chứa ba giá trị theo thứ tự xuất hiện:

~~~text
[java, spring, boot]
~~~

Điều này hữu ích khi bạn muốn lệnh nghiệp vụ nhận nhiều bộ lọc hoặc nhãn. Nhưng đừng mặc định rằng một **thuộc tính đơn** được gắn qua `@Value` hoặc `Environment` sẽ có cùng ngữ nghĩa với một danh sách option lặp lại. Cơ chế chuyển `CommandLinePropertySource` có thể biểu diễn nhiều giá trị theo quy tắc riêng; để bảo toàn ý nghĩa “lặp lại ba lần”, hãy đọc trực tiếp `ApplicationArguments.getOptionValues(...)`.

Nếu bạn muốn một thuộc tính cấu hình mang danh sách, hãy thiết kế cú pháp và kiểu dữ liệu thích hợp cho `@ConfigurationProperties`, rồi xác minh quy tắc gắn kết tương ứng. Không nên tùy tiện kết hợp hai cách xử lý trong cùng một tham số mà không xác định hợp đồng rõ ràng.

## 8. Environment: vì sao `--key=value` có thể ghi đè application.yaml?

Theo mặc định, `SpringApplication` chuyển các **option arguments** bắt đầu bằng `--` thành một `CommandLinePropertySource` trong `Environment`.

Ví dụ tệp cấu hình:

~~~yaml
# src/main/resources/application.yaml
app:
  mode: safe
  batch-size: 50
  greeting: "Xin chào"
~~~

Khởi chạy:

~~~bash
java -jar demo.jar --app.mode=fast --app.batch-size=300
~~~

Giá trị có hiệu lực thường là:

| Khóa | Tệp YAML | Dòng lệnh | Giá trị có hiệu lực |
| --- | --- | --- | --- |
| `app.mode` | `safe` | `fast` | `fast` |
| `app.batch-size` | `50` | `300` | `300` |
| `app.greeting` | `Xin chào` | Không có | `Xin chào` |

Dòng lệnh ghi đè **theo từng khóa**. Nó không xóa toàn bộ nội dung `application.yaml`.

Đọc từ Java:

~~~java
package com.example.demo;

import org.springframework.core.env.Environment;
import org.springframework.stereotype.Service;

@Service
public class RuntimeSettings {
    private final Environment environment;

    public RuntimeSettings(Environment environment) {
        this.environment = environment;
    }

    public String mode() {
        return environment.getProperty("app.mode", "safe");
    }

    public int batchSize() {
        return environment.getProperty(
                "app.batch-size", Integer.class, 50);
    }
}
~~~

`getProperty("app.mode")` trả về giá trị đã được Spring phân giải từ các nguồn có hiệu lực. Nếu không có nguồn CLI cho khóa này, nó vẫn có thể lấy từ biến môi trường, Java System property hoặc tệp cấu hình.

### Lý do thứ tự ưu tiên quan trọng

Trong một lần chạy thông thường, Spring Boot đặt các thuộc tính dòng lệnh cao hơn nhiều nguồn phổ biến khác, bao gồm tệp `application.yaml`, biến môi trường của hệ điều hành và Java System properties.

Ví dụ trên shell kiểu Unix:

~~~bash
APP_MODE=environment \
java -Dapp.mode=system -jar demo.jar --app.mode=cli
~~~

Khi không có nguồn đặc biệt khác can thiệp, `Environment.getProperty("app.mode")` là `cli`.

Bỏ `--app.mode=cli`, Java System property `app.mode=system` có thể thắng biến môi trường; bỏ tiếp `-Dapp.mode=system`, biến môi trường có thể thắng giá trị mặc định trong tệp.

Lưu ý các nguồn cấu hình riêng của kiểm thử, hoặc Devtools khi được bật, có thể có thứ tự ưu tiên đặc biệt. Quy tắc trên mô tả **lần chạy ứng dụng thông thường**, không phải mọi ngữ cảnh test.

## 9. Truy cập qua @Value và @ConfigurationProperties

Dữ liệu `--key=value` có thể được sử dụng như những thuộc tính cấu hình khác.

### 9.1. @Value cho một thuộc tính đơn

~~~java
package com.example.demo;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class GreetingConfig {

    private final String greeting;

    public GreetingConfig(
            @Value("${app.greeting:Xin chào}") String greeting) {
        this.greeting = greeting;
    }

    public String greeting() {
        return greeting;
    }
}
~~~

Nếu chạy:

~~~bash
java -jar demo.jar --app.greeting="Chào từ dòng lệnh"
~~~

giá trị `greeting` được tiêm từ `Environment` và có nội dung `Chào từ dòng lệnh`. Nếu không có thuộc tính, biểu thức `@Value` dùng giá trị mặc định `Xin chào` như đã khai báo.

### 9.2. @ConfigurationProperties cho một nhóm có kiểu

~~~java
package com.example.demo;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app")
public record AppCliProperties(
        String mode,
        int batchSize,
        boolean verbose) {
}
~~~

Đăng ký record này bằng `@ConfigurationPropertiesScan` ở lớp ứng dụng hoặc `@EnableConfigurationProperties(AppCliProperties.class)` trong cấu hình.

Tệp mặc định:

~~~yaml
app:
  mode: safe
  batch-size: 100
  verbose: false
~~~

Lệnh:

~~~bash
java -jar demo.jar --app.mode=fast --app.batch-size=500 --app.verbose=true
~~~

Bộ gắn kết nhận các giá trị hiệu lực và chuyển thành `String`, `int` và `boolean` tương ứng. `app.batch-size` được gắn vào trường Java `batchSize` theo quy tắc relaxed binding.

Khi một nhóm tham số phục vụ cấu hình hành vi của ứng dụng và cần kiểm tra giá trị, `@ConfigurationProperties` thường giúp tổ chức rõ hơn việc gọi `getProperty(...)` rải rác.

**Khác với đối số nghiệp vụ:** hai non-option `import customers.csv` không được `@ConfigurationProperties` tự gắn vào `mode` hay `batchSize`. Chúng vẫn phải được ứng dụng phân tích riêng, ví dụ qua `ApplicationArguments`.

## 10. @Value không phải API để đọc danh sách đối số thông thường

Có người thử:

~~~java
@Value("${customers.csv}")
String fileName;
~~~

khi chạy:

~~~bash
java -jar demo.jar import customers.csv
~~~

Cách này không hợp lệ theo mục đích: `customers.csv` là một **non-option argument**, không phải tên thuộc tính đã được Spring Boot tạo. `@Value` chỉ truy vấn khóa trong `Environment`.

Muốn đọc tệp đầu vào, hãy dùng:

~~~java
List<String> operands = args.getNonOptionArgs();
~~~

hoặc tự định nghĩa một option có tên:

~~~bash
java -jar demo.jar --input=customers.csv
~~~

khi đó có thể đọc:

~~~java
String input = environment.getProperty("input");
~~~

Cách đặt tên giúp gọi ở bất kỳ vị trí nào trên dòng lệnh; đối số vị trí lại giúp thiết kế cú pháp lệnh ngắn gọn. Tùy tác vụ, bạn có thể dùng cả hai theo hợp đồng rõ ràng.

## 11. Ví dụ hoàn chỉnh: lệnh nhập dữ liệu với option và non-option

Thiết kế một ứng dụng nhận câu lệnh:

~~~bash
java -jar importer.jar \
  --spring.main.web-application-type=none \
  --app.batch-size=250 \
  --dry-run \
  import customers.csv
~~~

Ý định:

- `--spring.main.web-application-type=none`: cấu hình Spring Boot không khởi động máy chủ web.
- `--app.batch-size=250`: giá trị cấu hình giới hạn kích thước lô.
- `--dry-run`: cờ nghiệp vụ báo chỉ mô phỏng.
- `import`: tên công việc.
- `customers.csv`: đường dẫn dữ liệu nguồn.

### 11.1. Cấu hình chung

~~~yaml
# application.yaml
app:
  batch-size: 100
~~~

### 11.2. Runner nhận cả hai nhóm đối số

~~~java
package com.example.importer;

import java.util.List;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class ImportRunner implements ApplicationRunner {

    private final Environment environment;

    public ImportRunner(Environment environment) {
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        List<String> operands = args.getNonOptionArgs();

        if (operands.size() != 2 ||
                !"import".equals(operands.get(0))) {
            throw new IllegalArgumentException(
                    "Cách dùng: [options] import <file>");
        }

        String file = operands.get(1);
        boolean dryRun = args.containsOption("dry-run");

        Integer batchSize = environment.getProperty(
                "app.batch-size", Integer.class, 100);

        if (batchSize == null || batchSize <= 0) {
            throw new IllegalArgumentException(
                    "app.batch-size phải là số nguyên dương");
        }

        System.out.println("Operation = import");
        System.out.println("File = " + file);
        System.out.println("Batch size = " + batchSize);
        System.out.println("Dry run = " + dryRun);

        // Minh họa cách phân loại đầu vào; chưa đọc hoặc sửa file thật.
    }
}
~~~

Đầu ra chính:

~~~text
Operation = import
File = customers.csv
Batch size = 250
Dry run = true
~~~

Lưu ý: thành phần `ImportRunner` chỉ minh họa xử lý đối số. Nếu muốn một công cụ CLI thực thụ, cần thiết kế mã lỗi khi tham số không hợp lệ, cơ chế dừng ứng dụng và xử lý lỗi nghiệp vụ; Spring Boot không tự sinh hệ thống lệnh con cho bạn.

### 11.3. Nếu người dùng gõ sai dấu bằng

Lệnh:

~~~bash
java -jar importer.jar --app.batch-size 250 import customers.csv
~~~

được phân loại thành:

- Option `app.batch-size`: **có mặt nhưng không có giá trị**.
- Non-option: `250`, `import`, `customers.csv`.

Runner ở trên sẽ thấy **ba** non-option, nên ném lỗi sử dụng thay vì âm thầm hiểu `250` là kích thước lô.

Cú pháp đúng là:

~~~bash
java -jar importer.jar --app.batch-size=250 import customers.csv
~~~

Thí dụ này cho thấy việc phân loại rõ ràng giúp báo lỗi có ích thay vì tiếp tục chạy với giá trị ngoài dự kiến.

## 12. Phân biệt với Java System properties: -Dkey=value

Dễ nhầm hai cú pháp:

~~~bash
java -Dapp.mode=fast -jar demo.jar
~~~

và:

~~~bash
java -jar demo.jar --app.mode=fast
~~~

Cả hai **có thể cung cấp thuộc tính `app.mode` cho `Environment`**, nhưng đến từ nguồn khác nhau.

| Cú pháp | Do thành phần nào đọc trước? | Xuất hiện trong `main(String[] args)`? | Nguồn trong Spring `Environment` |
| --- | --- | --- | --- |
| `-Dapp.mode=fast` đặt trước `-jar` | JVM | Không | Java System properties. |
| `--app.mode=fast` đặt sau `demo.jar` | Ứng dụng/Spring Boot | Có | Command-line property source mặc định. |
| `app.mode=fast` đặt sau `demo.jar` | Ứng dụng | Có, dạng non-option | Không tự thành một thuộc tính. |

Ví dụ:

~~~bash
java -Dapp.mode=system -jar demo.jar --app.mode=cli
~~~

`ApplicationArguments.getOptionValues("app.mode")` phản ánh giá trị `cli` từ option. `System.getProperty("app.mode")` phản ánh `system`. `Environment.getProperty("app.mode")` thường phản ánh `cli` vì command-line property source có ưu tiên cao hơn Java System properties trong lần chạy bình thường.

Nếu bạn đặt `-Dapp.mode=system` **sau** tên JAR, nó không còn là tùy chọn JVM ở vị trí thông thường mà là một chuỗi truyền cho ứng dụng. Hãy giữ tùy chọn JVM trước `-jar` và đối số ứng dụng sau tên JAR.

## 13. Phân biệt với biến môi trường hệ điều hành

Biến môi trường là thuộc tính của tiến trình mà hệ điều hành hoặc môi trường triển khai cung cấp. Nó **không cần** xuất hiện trong `String[] args`.

Trong shell kiểu Unix:

~~~bash
export APP_BATCHSIZE=120
java -jar demo.jar
~~~

Theo quy tắc ánh xạ tên biến môi trường dành cho `@ConfigurationProperties`, thuộc tính chuẩn `app.batch-size` tương ứng `APP_BATCHSIZE`: thay dấu chấm bằng dấu gạch dưới, bỏ gạch ngang, rồi viết hoa.

Nếu đồng thời chạy:

~~~bash
APP_BATCHSIZE=120 java -jar demo.jar --app.batch-size=300
~~~

thì cấu hình có hiệu lực từ CLI thường là `300`, vì nguồn command-line được ưu tiên hơn biến môi trường.

So sánh:

| Nguồn | Cách truyền điển hình | Cần có trong `main(args)`? |
| --- | --- | --- |
| Biến môi trường | `APP_BATCHSIZE=120` | Không |
| Java System property | `-Dapp.batch-size=120` trước `-jar` | Không |
| Spring Boot command-line option | `--app.batch-size=120` sau JAR | Có |
| Non-option argument | `customers.csv` sau JAR | Có |

**Không đồng nhất biến môi trường và command-line option.** Chúng đều có thể cấp giá trị cho `Environment` nhưng khác cách khai báo, thời điểm cung cấp và độ ưu tiên. Chính vì vậy bài này nằm trong mạch học về các nguồn cấu hình bên ngoài của Spring Boot.

## 14. Cú pháp có dấu cách, dấu bằng và ký tự đặc biệt

Shell cần biến mỗi giá trị nhiều từ thành một đối số duy nhất. Ví dụ:

~~~bash
java -jar demo.jar --app.message="Xin chào người dùng" import "my data.csv"
~~~

Trên nhiều shell thông dụng, Java nhận:

~~~text
["--app.message=Xin chào người dùng", "import", "my data.csv"]
~~~

Dấu nháy giúp shell giữ dấu cách bên trong một đối số. Spring Boot sau đó phân loại `--app.message=...` là option có giá trị và `my data.csv` là một non-option.

### Một dấu bằng trong giá trị

Ví dụ URL chứa truy vấn:

~~~bash
java -jar demo.jar '--app.endpoint=https://example.test/search?q=java&sort=asc'
~~~

Với shell Unix, nháy đơn bao quanh toàn đối số để các ký tự `&` không bị shell hiểu như ký hiệu điều khiển. Spring Boot tách tên option ở dấu bằng đầu tiên; phần sau tiếp tục thuộc giá trị:

~~~text
Option name: app.endpoint
Value: https://example.test/search?q=java&sort=asc
~~~

Nếu chuỗi đầu vào đến từ môi trường Windows hoặc công cụ chạy khác, hãy áp dụng cú pháp trích dẫn của chính môi trường đó. Trình phân tích của Spring Boot chỉ nhìn thấy các đối số **sau khi shell đã xử lý**.

### Giá trị rỗng và giá trị không được truyền

~~~bash
java -jar demo.jar --app.label=
~~~

và:

~~~bash
java -jar demo.jar --app.label
~~~

khác nhau. Trường hợp thứ nhất chủ động truyền dấu bằng với giá trị rỗng; trường hợp thứ hai có option nhưng không kèm giá trị. Cần thiết kế quy tắc validation theo mục đích ứng dụng, đặc biệt với chuỗi bắt buộc và Boolean.

### Dấu cách xung quanh dấu bằng

Không nên viết:

~~~bash
java -jar demo.jar --app.mode = fast
~~~

vì shell thường chia chúng thành ba đối số riêng: `--app.mode`, `=` và `fast`. Dạng đúng là:

~~~bash
java -jar demo.jar --app.mode=fast
~~~

## 15. Nhiều option và non-option trong cùng một lệnh

Các option có thể xen giữa các đối số thông thường trong một lệnh ứng dụng:

~~~bash
java -jar demo.jar import --app.batch-size=500 customers.csv --dry-run
~~~

Khi được Spring Boot phân tích, các option theo cú pháp `--...` vẫn là option:

- `app.batch-size` có giá trị `500`.
- `dry-run` có mặt nhưng không có giá trị.
- Non-option là `import` và `customers.csv`.

Điều này không có nghĩa mọi **thư viện CLI bên ngoài** đều dùng đúng quy tắc giống `ApplicationArguments`. Nếu sau này tích hợp Picocli, Spring Shell hoặc một thư viện parser khác, hãy tuân theo hợp đồng của parser đang dùng.

Với một ứng dụng thuần Spring Boot, việc dựa trên `ApplicationArguments` giúp giải thích cách phân loại được Spring Boot cung cấp sẵn.

## 16. Cách làm việc với SpringApplication.run và ApplicationRunner

`SpringApplication.run(...)` tạo ứng dụng, chuẩn bị `Environment`, xây dựng `ApplicationContext` và cuối cùng gọi những runner phù hợp.

Hai giao diện thường gặp:

~~~java
ApplicationRunner
CommandLineRunner
~~~

Cả hai đều chạy sau khi Spring Boot khởi tạo context, nhưng nhận đối số khác nhau:

| Giao diện | Phương thức | Đầu vào |
| --- | --- | --- |
| `ApplicationRunner` | `run(ApplicationArguments args)` | Dữ liệu đã phân loại option/non-option. |
| `CommandLineRunner` | `run(String... args)` | Các chuỗi đối số gốc. |

Ví dụ với `CommandLineRunner`:

~~~java
import java.util.Arrays;
import org.springframework.boot.CommandLineRunner;
import org.springframework.stereotype.Component;

@Component
class RawRunner implements CommandLineRunner {

    @Override
    public void run(String... args) {
        System.out.println(Arrays.toString(args));
    }
}
~~~

Lệnh:

~~~bash
java -jar demo.jar --app.mode=fast import customers.csv
~~~

in ra:

~~~text
[--app.mode=fast, import, customers.csv]
~~~

Ở đây bạn phải tự phân tích ý nghĩa của mỗi chuỗi nếu muốn tách option khỏi non-option. Với nhu cầu đó, `ApplicationRunner` và `ApplicationArguments` có sẵn chức năng, thường ít mã hơn.

Có thể sử dụng `ApplicationArguments` bằng constructor injection mà không cần trở thành `ApplicationRunner`:

~~~java
import org.springframework.boot.ApplicationArguments;
import org.springframework.stereotype.Service;

@Service
class JobSelection {
    private final ApplicationArguments args;

    JobSelection(ApplicationArguments args) {
        this.args = args;
    }

    String operationOrDefault() {
        return args.getNonOptionArgs().isEmpty()
                ? "help"
                : args.getNonOptionArgs().get(0);
    }
}
~~~

Spring Boot có thể cung cấp đối tượng `ApplicationArguments` cho bean để bạn truy vấn ở nơi cần thiết.

## 17. Tắt việc đưa command-line options vào Environment

Thông thường `--app.mode=fast` có hai vai trò:

1. Là option trong `ApplicationArguments`.
2. Được thêm như một thuộc tính cấu hình vào `Environment`.

Spring Boot cho phép tắt **vai trò thứ hai**:

~~~java
import org.springframework.boot.SpringApplication;

public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(DemoApplication.class);

        application.setAddCommandLineProperties(false);
        application.run(args);
    }
}
~~~

Khi đó, option của ứng dụng không còn được thêm làm `CommandLinePropertySource` mặc định. Tệp `application.yaml`, biến môi trường hoặc Java System properties vẫn có thể cung cấp cùng một tên thuộc tính.

Tuy nhiên, đối số vẫn được chuyển đến `SpringApplication.run(args)` và vẫn có thể đọc từ `ApplicationArguments`; việc tắt nguồn thuộc tính dòng lệnh không đồng nghĩa xóa các chuỗi đầu vào.

### Khi nào nên cân nhắc tắt?

- Ứng dụng muốn dùng `--...` làm một ngôn ngữ lệnh nghiệp vụ riêng, nhưng không muốn những chuỗi đó vô tình ghi đè cấu hình Spring.
- Một phần mềm cần kiểm soát tập khóa cấu hình cho phép thay đổi từ người vận hành.
- Một thiết kế đặc biệt muốn mọi cấu hình được lấy từ nguồn đã chọn và xử lý CLI bằng parser riêng.

Đa số ứng dụng Spring Boot giữ hành vi mặc định vì nó rất tiện cho triển khai và kiểm thử. Nếu tắt, cần đặc biệt chú ý: một tham số như `--spring.profiles.active=dev` sẽ không còn có hiệu lực qua nguồn command-line chuẩn, nên hãy cung cấp profile bằng nguồn khác hoặc chủ động xử lý theo thiết kế của ứng dụng.

## 18. Tham số Spring Boot tích hợp và tham số do ứng dụng tự định nghĩa

Không phải mọi đối số bắt đầu bằng `--` đều là lệnh đặc biệt của Spring Boot.

Một số thuộc tính tích hợp thường gặp:

| Ví dụ | Vai trò |
| --- | --- |
| `--server.port=9090` | Chọn cổng HTTP của ứng dụng web Spring Boot. |
| `--spring.profiles.active=prod` | Kích hoạt profile production. |
| `--spring.config.location=optional:file:./config/` | Chỉ rõ nơi tìm Config Data từ giai đoạn khởi động sớm. |
| `--spring.main.web-application-type=none` | Không khởi tạo ứng dụng web. |
| `--logging.level.root=DEBUG` | Chọn mức log nền. |

Các thuộc tính tự định nghĩa:

~~~bash
java -jar demo.jar --app.export.format=csv --app.export.max-items=1000
~~~

Spring Boot đưa chúng vào `Environment`, nhưng ứng dụng phải biết đọc và dùng. Nếu không có bean hay mã nào tham chiếu `app.export.format`, việc truyền nó có thể không gây thay đổi hành vi rõ ràng. **Không nên xem mọi option là một câu lệnh đã được Spring Boot tự thực thi.**

### Lưu ý về --debug

~~~bash
java -jar demo.jar --debug
~~~

Đây là ví dụ một cờ quen thuộc mà Spring Boot nhận để bật thông tin chẩn đoán. Nhưng `--debug` không chứng minh rằng **mọi** option không có giá trị đều được tự chuyển thành Boolean `true` khi gắn vào các thuộc tính của ứng dụng. Với Boolean nghiệp vụ tự định nghĩa, hãy dùng một quy ước rõ ràng:

~~~bash
java -jar demo.jar --app.trace-enabled=true
~~~

Hoặc chủ động kiểm tra sự có mặt:

~~~java
boolean requested = args.containsOption("trace");
~~~

## 19. Chạy từ IDE, Gradle và trình triển khai

Sự khác biệt của option/non-option **không phụ thuộc** việc bạn chạy JAR trực tiếp hay nhờ công cụ khác; điều quan trọng là các chuỗi cuối cùng đi đến phương thức `main(args)`.

### 19.1. Trong IDE

Thông thường trình cấu hình chạy có các mục riêng:

- **Program arguments / Application arguments**: nhập `--app.mode=fast import data.csv`.
- **VM options / JVM arguments**: nhập `-Dapp.mode=system`.
- **Environment variables**: khai báo `APP_MODE=environment`.

Nếu nhập `--app.mode=fast` vào ô VM options thay vì Program arguments, JVM có thể từ chối vì đây không phải tùy chọn JVM. Ngược lại, nếu nhập `-Dapp.mode=system` vào Program arguments, nó chỉ là một chuỗi ứng dụng và không trở thành Java System property theo cách thông thường.

Tên các ô khác nhau giữa IntelliJ IDEA, Eclipse, VS Code hoặc trình chạy khác, nhưng **ranh giới JVM–ứng dụng** vẫn giữ nguyên.

### 19.2. Với Gradle bootRun

Khi dùng task `bootRun` của Spring Boot Gradle plugin, có thể truyền program arguments qua tùy chọn Gradle `--args`:

~~~bash
./gradlew bootRun --args='--app.mode=fast import data.csv'
~~~

Trong shell Unix, nháy đơn giúp toàn bộ giá trị của `--args` được chuyển cho Gradle như một chuỗi để nó tách thành các đối số của ứng dụng. Với PowerShell hoặc CMD, cần áp dụng cú pháp trích dẫn tương ứng của hệ điều hành.

Lưu ý `--args` là tùy chọn **của Gradle task chạy Java**, còn `--app.mode=fast` là tùy chọn **được chuyển tới ứng dụng Spring Boot**. Đừng lẫn việc truyền đối số cho Gradle với việc truyền đối số cho tiến trình Java.

### 19.3. Container và hệ thống điều phối

Khi triển khai trong Docker hoặc Kubernetes, một hệ thống điều phối có thể truyền argument của tiến trình dưới dạng danh sách. Hãy đảm bảo mỗi option là một chuỗi chính xác:

~~~text
--spring.profiles.active=prod
--app.batch-size=500
import
/data/customers.csv
~~~

Không tự thêm dấu nháy như ký tự thực tế trong phần tử argument nếu hệ thống đã hỗ trợ mảng chuỗi. Với bí mật, dùng cơ chế quản lý bí mật thay vì truyền mật khẩu trên command line.

## 20. Khi nào dùng option, khi nào dùng đối số vị trí?

Lựa chọn nên bắt đầu từ **ý nghĩa dữ liệu**.

| Nhu cầu | Cách biểu diễn gợi ý | Lý do |
| --- | --- | --- |
| Cổng HTTP, profile, mức log | `--server.port=9090` | Là thuộc tính cấu hình của Spring Boot. |
| Giá trị ứng dụng có tên và có thể được ghi đè qua nguồn khác | `--app.batch-size=300` | Dễ truy cập qua `Environment` hoặc `@ConfigurationProperties`. |
| Chỉ định hành động nghiệp vụ | `import` | Từ khóa vị trí có ý nghĩa theo quy ước CLI. |
| Đường dẫn đầu vào sau tên công việc | `customers.csv` | Đơn giản khi vị trí đã rõ ràng. |
| Chỉ định đường dẫn không phụ thuộc vị trí | `--input=customers.csv` | Tên khóa làm rõ ý nghĩa. |
| Cờ chỉ cần bật/tắt theo sự có mặt | `--dry-run` | Đọc bằng `containsOption(...)`. |
| Boolean muốn dùng bộ gắn kết cấu hình | `--app.dry-run=true` | Có giá trị Boolean rõ ràng. |

Một thiết kế CLI tốt cần mô tả rõ **cú pháp chấp nhận**, **giá trị bắt buộc**, **giá trị mặc định**, **cách báo lỗi** và **xử lý trường hợp option lặp lại**.

Chẳng hạn với công cụ nhập dữ liệu:

~~~text
Cách dùng:
  importer.jar [options] import <file>

Options:
  --app.batch-size=<positive-integer>
  --app.mode=<safe|fast>
  --dry-run
~~~

Đây là một bản hợp đồng đầu vào dễ đọc. Mọi trường hợp như thiếu tệp, thiếu giá trị hoặc kích thước lô không hợp lệ đều có thể được báo lỗi tường minh.

## 21. Lỗi thường gặp và cách nhận diện

### Lỗi 1: Thiếu hai dấu gạch ngang

~~~bash
java -jar demo.jar app.mode=fast
~~~

`app.mode=fast` là non-option. Nếu bạn muốn ghi đè thuộc tính trong `Environment`, hãy dùng:

~~~bash
java -jar demo.jar --app.mode=fast
~~~

### Lỗi 2: Tách key và value thành hai đối số

~~~bash
java -jar demo.jar --app.mode fast
~~~

`fast` là non-option. Hãy dùng `--app.mode=fast`.

### Lỗi 3: Đặt -D sau tên JAR

~~~bash
java -jar demo.jar -Dapp.mode=fast
~~~

Chuỗi `-Dapp.mode=fast` lúc này là đầu vào ứng dụng và không phải tùy chọn JVM ở vị trí hợp lệ. Dùng:

~~~bash
java -Dapp.mode=fast -jar demo.jar
~~~

### Lỗi 4: Đọc non-option bằng @Value

~~~bash
java -jar demo.jar import customers.csv
~~~

`customers.csv` không tự thành thuộc tính. Đọc bằng `ApplicationArguments.getNonOptionArgs()`.

### Lỗi 5: Tự cho rằng --flag có giá trị true

Một option không kèm giá trị có thể được nhận diện qua `containsOption("flag")`. Nếu muốn cấu hình Boolean trong `@ConfigurationProperties`, hãy chủ động truyền `--app.flag=true` hoặc `--app.flag=false`.

### Lỗi 6: Cho rằng option được dùng tự động

Truyền `--app.some-key=abc` vào ứng dụng không có nghĩa Spring Boot tạo một tính năng tên `some-key`. Nó chỉ cung cấp một thuộc tính; mã ứng dụng hoặc thành phần cấu hình phải sử dụng thuộc tính đó.

### Lỗi 7: Không xử lý option lặp lại

~~~bash
java -jar demo.jar --tag=a --tag=b
~~~

`ApplicationArguments` cung cấp nhiều giá trị. Nếu nghiệp vụ yêu cầu đúng một, cần báo lỗi; nếu cho phép nhiều, xử lý danh sách. Không chọn ngẫu nhiên giá trị đầu/cuối mà không có quy tắc.

### Lỗi 8: Quên dấu nháy khi giá trị có khoảng trắng

~~~bash
java -jar demo.jar --app.message=Xin chào
~~~

Shell có thể chia thành một option `--app.message=Xin` và một non-option `chào`. Hãy dùng:

~~~bash
java -jar demo.jar --app.message="Xin chào"
~~~

### Lỗi 9: Dùng dòng lệnh để truyền dữ liệu bí mật

Các đối số quá trình có thể xuất hiện trong công cụ quan sát tiến trình, log của môi trường chạy hoặc lịch sử lệnh. Tránh truyền trực tiếp token, mật khẩu hay khóa bí mật trong `--password=...`. Dùng giải pháp secrets phù hợp của hạ tầng, giới hạn quyền đọc và không in dữ liệu nhạy cảm từ `ApplicationArguments` ra log.

### Lỗi 10: Nghĩ bật setAddCommandLineProperties(false) làm biến mất args

Việc tắt command-line property source không xóa các đối số được truyền đến ứng dụng. `ApplicationArguments` vẫn là công cụ phù hợp để đọc những chuỗi đầu vào của lệnh nghiệp vụ.

### Lỗi 11: Nhầm tài liệu cấu hình với một cú pháp CLI đầy đủ

Spring Boot cung cấp cơ chế phân loại option và thuộc tính. Nó không tự xây dựng chức năng `--help`, kiểm tra toàn bộ tham số bắt buộc, gợi ý lệnh con, mô tả thông báo lỗi hay khôi phục từ thiếu tệp theo đúng nghiệp vụ. Những yêu cầu này thuộc về thiết kế CLI của ứng dụng hoặc thư viện CLI được tích hợp.

## 22. Thực hành: quan sát cách Spring phân loại

Tạo một ứng dụng Spring Boot có runner:

~~~java
import java.util.Arrays;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
class ArgumentExplorer implements ApplicationRunner {
    private final Environment environment;

    ArgumentExplorer(Environment environment) {
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        System.out.println("RAW: " +
                Arrays.toString(args.getSourceArgs()));
        System.out.println("OPTIONS: " + args.getOptionNames());
        System.out.println("NON_OPTIONS: " + args.getNonOptionArgs());

        System.out.println("app.mode values: " +
                args.getOptionValues("app.mode"));

        System.out.println("effective app.mode: " +
                environment.getProperty("app.mode", "(missing)"));
    }
}
~~~

Dùng tệp:

~~~properties
app.mode=default
~~~

### Bài 1: truyền option hợp lệ

~~~bash
java -jar demo.jar --app.mode=fast import file.csv
~~~

Dự đoán:

- `getOptionValues("app.mode")` trả danh sách một phần tử `fast`.
- `getNonOptionArgs()` trả `["import", "file.csv"]`.
- `Environment.getProperty("app.mode")` nhận `fast` theo quy tắc thông thường.

### Bài 2: thiếu dấu --

~~~bash
java -jar demo.jar app.mode=fast import file.csv
~~~

Dự đoán:

- Danh sách option không có `app.mode`.
- Các non-option là `["app.mode=fast", "import", "file.csv"]`.
- Giá trị `app.mode` từ tệp vẫn là `default`.

### Bài 3: thiếu dấu bằng

~~~bash
java -jar demo.jar --app.mode fast import file.csv
~~~

Dự đoán:

- `containsOption("app.mode")` là `true`.
- `getOptionValues("app.mode")` là danh sách rỗng.
- Các non-option là `["fast", "import", "file.csv"]`.
- Không có giá trị CLI `fast` được gắn cho `app.mode` từ chuỗi này.

### Bài 4: đối chiếu nguồn

~~~bash
java -Dapp.mode=system -jar demo.jar --app.mode=cli import file.csv
~~~

Dự đoán:

- `System.getProperty("app.mode")` là `system`.
- `getOptionValues("app.mode")` chứa `cli`.
- `Environment.getProperty("app.mode")` là `cli` ở lần chạy mặc định.

### Bài 5: option trùng tên

~~~bash
java -jar demo.jar --tag=one --tag=two export result.csv
~~~

Dự đoán:

- `getOptionValues("tag")` chứa hai phần tử `one` và `two`.
- `getNonOptionArgs()` chứa `export` và `result.csv`.
- Ứng dụng tự quyết định nhận nhiều tag hay báo lỗi.

### Bài 6: tắt nguồn command-line

Trong lớp khởi chạy, dùng `setAddCommandLineProperties(false)` và chạy:

~~~bash
java -jar demo.jar --app.mode=cli
~~~

Quan sát `ApplicationArguments.getOptionValues("app.mode")` vẫn có `cli`, nhưng `Environment` không còn nhận ghi đè đó thông qua nguồn CLI mặc định. Nếu tệp vẫn có `app.mode=default`, giá trị hiệu lực từ tệp sẽ là `default` khi không có nguồn khác ghi đè.

### Bài 7: dùng chung option và non-option

Thiết kế lệnh:

~~~bash
java -jar demo.jar --spring.profiles.active=dev --app.batch-size=150 --dry-run import "input data.csv"
~~~

Hãy phân loại từng chuỗi và giải thích:

- Vì sao `spring.profiles.active` có tác dụng trong giai đoạn khởi động?
- Vì sao `app.batch-size` có thể đọc qua `@ConfigurationProperties`?
- Vì sao `--dry-run` phù hợp với `containsOption("dry-run")`?
- Vì sao `import` và `input data.csv` phải được đọc từ `getNonOptionArgs()`?

Đáp án: ba chuỗi bắt đầu bằng `--` là option; `import` và `input data.csv` là non-option. Các option cấu hình có thể tham gia `Environment`; cờ chỉ cần sự hiện diện được kiểm tra qua `ApplicationArguments`; hai non-option chứa yêu cầu nghiệp vụ theo quy ước của ứng dụng.

## 23. Bảng tổng hợp: nhìn cú pháp để đoán đích đến

| Dữ liệu truyền vào | Được JVM xử lý hay SpringApplication nhận? | Đọc ở đâu? |
| --- | --- | --- |
| `-Dapp.mode=fast` trước `-jar` | JVM xử lý thành System property. | `System.getProperty(...)`, `Environment`. |
| `--app.mode=fast` sau JAR | SpringApplication nhận như option. | `ApplicationArguments`; mặc định cả `Environment`. |
| `--dry-run` sau JAR | SpringApplication nhận như option không có giá trị. | `ApplicationArguments.containsOption(...)`. |
| `app.mode=fast` sau JAR | Ứng dụng nhận như non-option. | `ApplicationArguments.getNonOptionArgs()`. |
| `import` sau JAR | Ứng dụng nhận như non-option. | `ApplicationArguments.getNonOptionArgs()`. |
| `APP_MODE=fast` do hệ điều hành cung cấp | Biến môi trường của tiến trình. | `System.getenv(...)`; `Environment` theo ánh xạ. |
| `app.mode=fast` trong application.properties | Config Data nạp từ tệp. | `Environment`; `@Value`; `@ConfigurationProperties`. |

Tóm lại, **cú pháp và vị trí của đối số quyết định cách Spring Boot xử lý nó**. `--key=value` cung cấp một option có tên, mặc định được chuyển thành thuộc tính cấu hình; đối số thông thường giữ vai trò đầu vào nghiệp vụ và được đọc từ `ApplicationArguments`. `-Dkey=value` là cơ chế của JVM, còn biến môi trường thuộc hệ điều hành; tất cả có thể liên quan đến cấu hình cuối cùng nhưng không phải cùng một loại đầu vào.

Khi viết công cụ CLI bằng Spring Boot, nên tách rõ ba việc: **cấu hình ứng dụng**, **cờ điều khiển lệnh**, và **đối số nghiệp vụ theo vị trí**. Dùng đúng API cho mỗi việc giúp việc khởi chạy dễ hiểu, xử lý lỗi minh bạch và tránh các cấu hình vô tình bị ghi đè.

## Tài liệu tham khảo

- [Spring Boot 3.3 — Externalized Configuration: Accessing Command Line Properties](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html).
- [Spring Boot 3.3 — SpringApplication: Accessing Application Arguments](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html).
- [Spring Boot — ApplicationArguments API](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/ApplicationArguments.html).