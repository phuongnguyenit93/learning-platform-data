# ApplicationArguments, option argument và non-option argument

Khi chạy một ứng dụng Spring Boot từ terminal, bạn có thể truyền tham số để chọn chế độ chạy, bật/tắt một tính năng, chỉ định file đầu vào hoặc thay đổi cấu hình mà không cần sửa source code. Spring Boot nhận các tham số đó qua **SpringApplication** và cung cấp API **ApplicationArguments** để ứng dụng đọc chúng một cách có cấu trúc.

ApplicationArguments phân biệt hai nhóm:

- **Option arguments**: tham số bắt đầu bằng hai dấu gạch ngang **--**, thường có dạng **--name=value**.
- **Non-option arguments**: tham số không bắt đầu bằng **--**, thường dùng cho các giá trị đầu vào theo vị trí như tên file hoặc mã tác vụ.

Ví dụ:

~~~bash
java -jar app.jar --dry-run --format=csv input.csv --tag=urgent --tag=nightly
~~~

Spring Boot có thể đọc **dry-run**, **format**, **tag** như các option và **input.csv** như một non-option argument. API này hữu ích khi xây dựng command-line tool bằng Spring Boot, chạy import/export, thực hiện tác vụ quản trị hoặc điều khiển chế độ khởi động của ứng dụng.

## 1. Tham số đi vào SpringApplication như thế nào?

Một ứng dụng Spring Boot thường bắt đầu từ phương thức main:

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

**args** là mảng String mà JVM chuyển cho phương thức main. Khi gọi **SpringApplication.run(...)**, ứng dụng chuyển tiếp mảng đó cho Spring Boot.

Ví dụ chạy JAR:

~~~bash
java -jar demo.jar --app.mode=import --dry-run orders.csv
~~~

Các chuỗi đứng sau tên JAR được truyền vào ứng dụng dưới dạng đối số dòng lệnh. Spring Boot phân tích chúng và tạo đối tượng **ApplicationArguments** để cung cấp cho startup runner.

Nếu bạn không truyền args vào SpringApplication.run, Spring Boot không thể đọc các tham số đó qua ApplicationArguments:

~~~java
public static void main(String[] args) {
    SpringApplication.run(DemoApplication.class);
}
~~~

Trong trường hợp này, mảng args không được chuyển tiếp. Hãy dùng overload nhận args khi ứng dụng cần xử lý command-line arguments.

## 2. ApplicationArguments là gì?

**ApplicationArguments** là interface trong package:

~~~java
org.springframework.boot.ApplicationArguments
~~~

Spring Boot cung cấp implementation mặc định là **DefaultApplicationArguments**. Đối tượng này biểu diễn các tham số đã được truyền vào SpringApplication.run(...) và cho phép truy cập cả dữ liệu gốc lẫn các nhóm tham số đã phân tích.

Các API chính:

| Phương thức | Ý nghĩa |
|---|---|
| **getSourceArgs()** | Lấy mảng tham số gốc được truyền vào SpringApplication. |
| **getOptionNames()** | Lấy tập tên các option đã được nhận diện. |
| **containsOption(name)** | Kiểm tra một option có xuất hiện hay không. |
| **getOptionValues(name)** | Lấy các giá trị gắn với một option. |
| **getNonOptionArgs()** | Lấy danh sách đối số không phải option. |

Ví dụ, khi nhận:

~~~text
--format=csv input.csv --dry-run
~~~

ta có thể lấy:

- **getSourceArgs()**: các chuỗi gốc theo thứ tự được truyền vào.
- **getOptionNames()**: tên các option như format, dry-run.
- **containsOption("dry-run")**: true.
- **getOptionValues("format")**: danh sách chứa csv.
- **getNonOptionArgs()**: danh sách chứa input.csv.

ApplicationArguments chỉ phân tích chuỗi đối số. Nó không tự thực hiện import file, xác thực nghiệp vụ hay chuyển mọi giá trị thành kiểu Java mong muốn.

## 3. Option argument là gì?

Một **option argument** là đối số bắt đầu bằng hai dấu gạch ngang **--**.

Ví dụ:

~~~text
--profile=production
--server.port=8085
--app.mode=import
--dry-run
~~~

Tên option là phần nằm sau --. Với cú pháp có dấu bằng, phần sau dấu = là giá trị:

~~~text
--app.mode=import
    └──────┘ └───┘
      name   value
~~~

Option name có thể chứa dấu chấm hoặc dấu gạch ngang, nên các tên như server.port, app.mode, dry-run đều thường gặp.

### 3.1. Option có giá trị: --name=value

Đây là cú pháp rõ ràng nhất để truyền giá trị:

~~~bash
java -jar app.jar --app.mode=import --batch.size=500
~~~

Spring Boot nhận diện:

| Option name | Value |
|---|---|
| app.mode | import |
| batch.size | 500 |

Giá trị được đọc qua getOptionValues(...) dưới dạng String. Nếu cần số nguyên, boolean, enum hoặc kiểu domain, bạn phải chuyển đổi hoặc dùng cơ chế bind property của Spring.

### 3.2. Option dạng cờ: --name

Một option có thể xuất hiện mà không có giá trị:

~~~bash
java -jar app.jar --dry-run
~~~

Trong trường hợp này:

- **containsOption("dry-run")** trả về true.
- Option dry-run được nhận diện là có mặt.
- Nó không có một giá trị văn bản thông thường như true hoặc false.

Đối với option dạng cờ, nên kiểm tra sự hiện diện bằng containsOption(...) thay vì giả định rằng mọi option đều có một giá trị không null.

Ví dụ:

~~~java
if (args.containsOption("dry-run")) {
    System.out.println("Chạy thử, không ghi dữ liệu");
}
~~~

Nếu muốn truyền một giá trị boolean tường minh để bind vào cấu hình, dùng:

~~~text
--app.dry-run=true
~~~

Hai cách có ý nghĩa khác nhau ở tầng parser: --dry-run là option không có giá trị; --app.dry-run=true là option có tên app.dry-run và giá trị chuỗi true.

### 3.3. Một option có thể xuất hiện nhiều lần

Spring Boot cho phép một option xuất hiện nhiều lần:

~~~bash
java -jar app.jar --tag=urgent --tag=nightly --tag=finance
~~~

getOptionNames() chỉ biểu diễn tập tên option, nên tag xuất hiện một lần trong tập. Để lấy tất cả giá trị, dùng:

~~~java
List<String> tags = args.getOptionValues("tag");
~~~

Kết quả có thể là:

~~~text
["urgent", "nightly", "finance"]
~~~

Điều này hữu ích cho filter, danh sách môi trường, nhiều file cấu hình hoặc các nhãn mà người chạy muốn truyền lặp lại.

### 3.4. Option có giá trị rỗng

Với:

~~~text
--app.label=
~~~

option app.label có mặt và giá trị là chuỗi rỗng. Đây khác với trường hợp option không có giá trị:

~~~text
--app.label
~~~

Vì vậy, khi xử lý option, hãy phân biệt:

- Option không xuất hiện.
- Option xuất hiện nhưng không có value.
- Option xuất hiện với value rỗng.
- Option xuất hiện với một hoặc nhiều value thực tế.

Nếu giá trị bắt buộc, nên xác thực rõ ràng trước khi thực hiện tác vụ.

## 4. Non-option argument là gì?

**Non-option argument** là đối số không bắt đầu bằng **--**.

Ví dụ:

~~~bash
java -jar app.jar orders.csv customers.csv
~~~

Hai chuỗi orders.csv và customers.csv là non-option arguments.

Chúng thường được dùng cho dữ liệu theo vị trí:

- Tên file đầu vào.
- Tên lệnh con.
- Mã đối tượng cần xử lý.
- Đường dẫn thư mục.
- Tham số positional của một command-line tool.

Lấy danh sách bằng:

~~~java
List<String> inputFiles = args.getNonOptionArgs();
~~~

Ví dụ:

~~~java
@Component
public class FileImportRunner implements ApplicationRunner {

    @Override
    public void run(ApplicationArguments args) {
        List<String> files = args.getNonOptionArgs();

        for (String file : files) {
            System.out.println("File đầu vào: " + file);
        }
    }
}
~~~

Non-option arguments không có tên do parser gán. Nếu cần biết một chuỗi là input, output hay config, ứng dụng phải quy định thứ tự hoặc tự xây một command parser có cấu trúc phù hợp.

## 5. Cách Spring Boot phân tích option và non-option

Quy tắc cơ bản:

1. Đối số bắt đầu bằng -- được xem là option.
2. Với dạng --name=value, phần trước dấu = là tên, phần sau là giá trị.
3. Với dạng --name không có dấu =, option được nhận diện nhưng không có giá trị.
4. Đối số không bắt đầu bằng -- được đưa vào danh sách non-option.

Ví dụ:

~~~text
--dry-run --format=csv input.csv --tag=urgent
~~~

Được phân tích như sau:

| Chuỗi đầu vào | Phân loại | Tên | Giá trị |
|---|---|---|---|
| --dry-run | Option | dry-run | Không có giá trị |
| --format=csv | Option | format | csv |
| input.csv | Non-option | — | input.csv |
| --tag=urgent | Option | tag | urgent |

### 5.1. Không giả định --name value tương đương --name=value

Đây là điểm dễ gây lỗi khi mới dùng ApplicationArguments.

Với parser của Spring Boot:

~~~text
--format=csv
~~~

là một option có tên format và giá trị csv.

Trong khi:

~~~text
--format csv
~~~

được phân tích thành:

- Option format không có giá trị.
- Non-option argument csv.

Parser không tự tiêu thụ token kế tiếp làm giá trị cho option không có dấu bằng. Vì vậy, khi viết lệnh cho ứng dụng Spring Boot, hãy dùng --name=value để tránh hiểu nhầm.

Nếu muốn hỗ trợ cú pháp --name value, bạn cần tự xây parser khác hoặc dùng một thư viện command-line chuyên dụng và quy định rõ cách parse.

### 5.2. Short option như -p không phải option theo quy tắc này

ApplicationArguments nhận diện option theo tiền tố --. Chuỗi:

~~~text
-p
~~~

không được coi là option theo cú pháp đó; nó là non-option argument. ApplicationArguments không tự cung cấp hệ thống alias short option kiểu -p tương đương --port.

Nếu command-line interface cần short option, nhóm option bắt buộc, subcommand, help text hoặc kiểm tra kiểu dữ liệu phức tạp, hãy cân nhắc thư viện chuyên dụng như picocli.

## 6. Đọc ApplicationArguments trong ApplicationRunner

**ApplicationRunner** là nơi thuận tiện để đọc ApplicationArguments sau khi Spring ApplicationContext đã được refresh.

Ví dụ:

~~~java
package com.example.demo.startup;

import java.util.List;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;

@Component
public class ImportRunner implements ApplicationRunner {

    @Override
    public void run(ApplicationArguments args) {
        if (args.containsOption("dry-run")) {
            System.out.println("Chế độ dry-run được bật");
        }

        List<String> formats = args.getOptionValues("format");
        if (!formats.isEmpty()) {
            String format = formats.get(0);
            System.out.println("Định dạng: " + format);
        }

        List<String> inputFiles = args.getNonOptionArgs();
        System.out.println("Số file đầu vào: " + inputFiles.size());
    }
}
~~~

Chạy:

~~~bash
java -jar app.jar --dry-run --format=csv orders.csv
~~~

Runner có thể:

- Kiểm tra chế độ chạy.
- Đọc các option có giá trị.
- Lấy danh sách file hoặc đối số vị trí.
- Xác thực đầu vào.
- Gọi service thực hiện tác vụ.

### 6.1. Vì sao dùng ApplicationRunner?

ApplicationRunner nhận trực tiếp đối tượng ApplicationArguments nên code không cần tự tách chuỗi --, dấu = hoặc danh sách giá trị lặp lại.

Spring Boot gọi runner sau khi ApplicationContext đã refresh và trước khi phát ApplicationReadyEvent. Nếu runner thực hiện tác vụ đồng bộ, tác vụ đó hoàn tất trước khi ứng dụng đi tới mốc ready theo luồng startup thông thường.

Nếu runner ném exception không được xử lý, quá trình startup có thể thất bại. Đây là điều phù hợp nếu tham số đầu vào không hợp lệ hoặc tác vụ bắt buộc không thể hoàn thành.

### 6.2. Nhiều runner và thứ tự thực thi

Ứng dụng có thể khai báo nhiều ApplicationRunner. Khi cần thứ tự cụ thể, dùng @Order hoặc Ordered.

~~~java
@Component
@Order(10)
public class ValidateArgumentsRunner implements ApplicationRunner {
    @Override
    public void run(ApplicationArguments args) {
        // Xác thực tham số.
    }
}
~~~

~~~java
@Component
@Order(20)
public class ExecuteImportRunner implements ApplicationRunner {
    @Override
    public void run(ApplicationArguments args) {
        // Thực hiện import sau bước xác thực.
    }
}
~~~

Các runner được sắp xếp theo cơ chế order của Spring. Nếu hai bước có quan hệ phụ thuộc chặt chẽ, một runner điều phối duy nhất có thể làm trình tự dễ hiểu hơn.

## 7. ApplicationRunner và CommandLineRunner khác nhau thế nào?

Spring Boot có hai interface thường dùng để chạy tác vụ startup:

**ApplicationRunner**:

~~~java
@Component
public class AppRunner implements ApplicationRunner {
    @Override
    public void run(ApplicationArguments args) {
        // Đọc option và non-option đã phân tích.
    }
}
~~~

**CommandLineRunner**:

~~~java
@Component
public class RawArgsRunner implements CommandLineRunner {
    @Override
    public void run(String... args) {
        // Nhận mảng String gốc.
    }
}
~~~

So sánh:

| Tiêu chí | ApplicationRunner | CommandLineRunner |
|---|---|---|
| Tham số nhận được | ApplicationArguments | String... args |
| Option names | Có API getOptionNames() | Tự phân tích |
| Option values | Có API getOptionValues() | Tự phân tích |
| Non-option args | Có API getNonOptionArgs() | Tự phân tích |
| Raw args | Có getSourceArgs() | Nhận trực tiếp |
| Phù hợp | Tác vụ cần đọc option có cấu trúc | Tác vụ đơn giản cần chuỗi gốc |

Nếu cần xử lý --format=csv, option lặp lại hoặc phân biệt option với positional argument, ApplicationRunner thường thuận tiện hơn.

CommandLineRunner vẫn phù hợp khi chương trình chỉ cần chuyển tiếp nguyên mảng tham số cho một API khác hoặc tự dùng parser riêng.

## 8. Ví dụ hoàn chỉnh: chương trình import file

Ta xây một runner nhận:

~~~bash
java -jar importer.jar --format=csv --dry-run --tag=nightly --tag=finance orders.csv customers.csv
~~~

Quy ước:

- --format=csv: định dạng file.
- --dry-run: chỉ kiểm tra, không ghi dữ liệu.
- --tag=...: có thể xuất hiện nhiều lần.
- Các non-option arguments là danh sách file đầu vào.

### 8.1. Tạo lớp xử lý

~~~java
package com.example.importer;

import java.util.List;
import org.springframework.stereotype.Service;

@Service
public class ImportService {

    public void importFiles(
            List<String> files,
            String format,
            List<String> tags,
            boolean dryRun) {

        System.out.println("Format: " + format);
        System.out.println("Tags: " + tags);
        System.out.println("Dry run: " + dryRun);

        for (String file : files) {
            System.out.println("Processing: " + file);
            if (!dryRun) {
                // Gọi logic đọc và ghi dữ liệu thật.
            }
        }
    }
}
~~~

### 8.2. Tạo runner để đọc arguments

~~~java
package com.example.importer;

import java.util.List;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;

@Component
public class ImportApplicationRunner implements ApplicationRunner {

    private final ImportService importService;

    public ImportApplicationRunner(ImportService importService) {
        this.importService = importService;
    }

    @Override
    public void run(ApplicationArguments args) {
        List<String> formats = args.getOptionValues("format");
        if (formats.isEmpty() || formats.get(0) == null
                || formats.get(0).isBlank()) {
            throw new IllegalArgumentException(
                    "Cần truyền --format=csv hoặc định dạng được hỗ trợ");
        }

        String format = formats.get(0);
        List<String> tags = args.getOptionValues("tag");
        List<String> files = args.getNonOptionArgs();
        boolean dryRun = args.containsOption("dry-run");

        if (files.isEmpty()) {
            throw new IllegalArgumentException(
                    "Cần truyền ít nhất một file đầu vào");
        }

        if (formats.size() > 1) {
            throw new IllegalArgumentException(
                    "Chỉ được truyền một --format");
        }

        importService.importFiles(files, format, tags, dryRun);
    }
}
~~~

Ví dụ này kiểm tra option format có giá trị và không rỗng, lấy các tag lặp lại, xác nhận có file đầu vào, rồi chuyển dữ liệu đã parse sang service.

Trong một CLI thực tế, cần xác thực thêm:

- File có tồn tại và có quyền đọc không?
- Format có nằm trong tập được hỗ trợ không?
- Có cho phép truyền nhiều file không?
- --dry-run có được phép kết hợp với các option khác không?
- Nếu một file lỗi, có dừng toàn bộ batch hay tiếp tục file tiếp theo?

Không nên để logic parsing, validation và xử lý file dồn vào một phương thức run quá dài. Runner nên đóng vai trò điều phối startup.

## 9. Một ví dụ phân tích arguments bằng bảng

Giả sử lệnh:

~~~text
java -jar app.jar --mode=export --compress --format=json report.json --tag=daily --tag=finance
~~~

Các giá trị sau app.jar được đưa vào SpringApplication:

~~~text
--mode=export
--compress
--format=json
report.json
--tag=daily
--tag=finance
~~~

Kết quả:

| API | Kết quả |
|---|---|
| getOptionNames() | mode, compress, format, tag |
| containsOption("compress") | true |
| getOptionValues("mode") | ["export"] |
| getOptionValues("format") | ["json"] |
| getOptionValues("tag") | ["daily", "finance"] |
| getNonOptionArgs() | ["report.json"] |

getOptionNames() là một tập tên nên không giữ số lần xuất hiện của option. getOptionValues("tag") mới cho biết tất cả giá trị được truyền.

getSourceArgs() giữ lại các chuỗi nguồn theo thứ tự đầu vào. Nếu cần ghi log hoặc chuyển tiếp nguyên danh sách, API này phù hợp hơn việc ghép lại từ option và non-option lists.

## 10. Option arguments và Spring Environment

Ngoài ApplicationArguments, Spring Boot mặc định còn đưa command-line option arguments vào **Environment** dưới dạng một property source.

Ví dụ:

~~~bash
java -jar app.jar --server.port=8090 --demo.greeting.prefix=Chào
~~~

Các property có giá trị có thể được đọc qua:

~~~java
import org.springframework.core.env.Environment;

@Component
public class GreetingSettingsReader {
    private final Environment environment;

    public GreetingSettingsReader(Environment environment) {
        this.environment = environment;
    }

    public String prefix() {
        return environment.getProperty("demo.greeting.prefix");
    }
}
~~~

hoặc bind bằng @ConfigurationProperties.

Điều này tạo ra hai cách truy cập cùng một nguồn đầu vào:

- **ApplicationArguments**: đọc option và non-option theo cấu trúc command line.
- **Environment**: đọc các option có ý nghĩa như property cấu hình Spring.

### 10.1. Khi nào dùng ApplicationArguments?

Dùng ApplicationArguments khi tham số có ý nghĩa như một command:

- Tên file đầu vào.
- --dry-run.
- --format=csv.
- Nhiều --tag=....
- Các tham số positional cần xác thực.

### 10.2. Khi nào dùng Environment hoặc @ConfigurationProperties?

Dùng Environment hoặc @ConfigurationProperties khi giá trị là cấu hình ứng dụng:

- server.port.
- spring.profiles.active.
- demo.greeting.prefix.
- app.import.batch-size.
- Timeout, retry, endpoint hoặc feature flags.

Ví dụ properties:

~~~java
@ConfigurationProperties(prefix = "app.import")
public class ImportProperties {
    private int batchSize = 500;

    public int getBatchSize() {
        return batchSize;
    }

    public void setBatchSize(int batchSize) {
        this.batchSize = batchSize;
    }
}
~~~

Khi chạy:

~~~bash
java -jar app.jar --app.import.batch-size=1000
~~~

Spring Boot có thể bind giá trị 1000 vào batchSize.

### 10.3. Tắt command-line property source

SpringApplication cho phép tắt việc thêm command-line arguments vào Environment:

~~~java
SpringApplication application =
        new SpringApplication(DemoApplication.class);
application.setAddCommandLineProperties(false);
application.run(args);
~~~

Khi cấu hình này được tắt, command-line arguments không được thêm như property source vào Environment. Điều đó không có nghĩa mảng đối số gốc biến mất; ApplicationArguments vẫn là API phân tích tham số mà Spring Boot tạo từ các đối số truyền vào.

Chỉ tắt command-line property source khi bạn có lý do rõ ràng, vì nhiều ứng dụng dựa vào khả năng ghi đè cấu hình bằng --property=value.

### 10.4. Command-line option có độ ưu tiên cấu hình cao

Khi command-line property source được bật, các giá trị dạng:

~~~text
--server.port=8090
~~~

có thể ghi đè giá trị tương ứng trong application.yml theo thứ tự ưu tiên property source của Spring Boot. Đây là cách thuận tiện để triển khai cùng một artifact ở nhiều môi trường mà không phải sửa file cấu hình.

Không nên truyền secret nhạy cảm trực tiếp qua command line nếu hệ điều hành, process listing, shell history hoặc công cụ giám sát có thể ghi lại tham số. Với secret, hãy dùng cơ chế quản lý secret phù hợp môi trường triển khai.

## 11. Phân biệt tham số của JVM và tham số của ứng dụng

Khi chạy:

~~~bash
java -Dapp.region=ap-southeast-1 -jar app.jar --mode=import input.csv
~~~

có hai nhóm đối số khác nhau:

- **-Dapp.region=ap-southeast-1** nằm trước -jar, là system property của JVM.
- **--mode=import** và **input.csv** nằm sau tên JAR, là đối số được truyền cho phương thức main của ứng dụng.

Có thể đọc system property:

~~~java
String region = System.getProperty("app.region");
~~~

Có thể đọc application option:

~~~java
args.getOptionValues("mode");
~~~

Đây là hai nguồn khác nhau. Nếu đặt -D... sau tên JAR, chuỗi đó không còn được JVM xử lý như system property; nó trở thành tham số của ứng dụng.

## 12. Xác thực và chuyển đổi giá trị

ApplicationArguments trả về giá trị dạng String. Ứng dụng cần xác thực trước khi sử dụng.

Ví dụ đọc số batch:

~~~java
private int readBatchSize(ApplicationArguments args) {
    List<String> values = args.getOptionValues("batch-size");

    if (values.isEmpty() || values.get(0) == null) {
        return 500;
    }

    try {
        int size = Integer.parseInt(values.get(0));
        if (size <= 0) {
            throw new IllegalArgumentException(
                    "--batch-size phải lớn hơn 0");
        }
        return size;
    } catch (NumberFormatException ex) {
        throw new IllegalArgumentException(
                "--batch-size phải là số nguyên", ex);
    }
}
~~~

Lệnh:

~~~bash
java -jar app.jar --batch-size=1000
~~~

đưa chuỗi 1000 cho ứng dụng; code chuyển đổi thành int và xác nhận miền giá trị.

Nếu giá trị là cấu hình dài hạn, dùng @ConfigurationProperties với kiểu dữ liệu cụ thể và validation thường gọn hơn việc tự parse từng option trong runner.

### 12.1. Xử lý option bắt buộc

Ví dụ yêu cầu --source:

~~~java
private String requireOption(ApplicationArguments args, String name) {
    List<String> values = args.getOptionValues(name);
    if (values.isEmpty() || values.get(0) == null
            || values.get(0).isBlank()) {
        throw new IllegalArgumentException(
                "Thiếu option --" + name + "=<value>");
    }
    if (values.size() > 1) {
        throw new IllegalArgumentException(
                "Option --" + name + " chỉ được truyền một lần");
    }
    return values.get(0);
}
~~~

Helper này kiểm tra:

- Option có tồn tại không?
- Có value không?
- Value có rỗng không?
- Có bị truyền lặp không?

Với option dạng cờ, không dùng helper này vì cờ không cần giá trị.

## 13. Kiểm thử ApplicationArguments

Có thể kiểm tra parser trực tiếp bằng **DefaultApplicationArguments**, không cần khởi động toàn bộ Spring Boot application.

Ví dụ JUnit 5 và AssertJ:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.DefaultApplicationArguments;

class ApplicationArgumentsTests {

    @Test
    void separatesOptionsAndNonOptions() {
        ApplicationArguments args = new DefaultApplicationArguments(
                "--dry-run",
                "--format=csv",
                "input.csv",
                "--tag=urgent",
                "--tag=nightly"
        );

        assertThat(args.containsOption("dry-run")).isTrue();
        assertThat(args.getOptionValues("format"))
                .containsExactly("csv");
        assertThat(args.getOptionValues("tag"))
                .containsExactly("urgent", "nightly");
        assertThat(args.getNonOptionArgs())
                .containsExactly("input.csv");
    }
}
~~~

Test này xác nhận:

- Option không có value vẫn được nhận diện.
- Option có value được tách thành name và value.
- Option lặp lại giữ nhiều giá trị.
- Chuỗi không bắt đầu bằng -- được đưa vào non-option list.

### 13.1. Kiểm thử cú pháp --name value

~~~java
@Test
void doesNotConsumeNextTokenAsOptionValue() {
    ApplicationArguments args = new DefaultApplicationArguments(
            "--format",
            "csv"
    );

    assertThat(args.containsOption("format")).isTrue();
    assertThat(args.getNonOptionArgs()).containsExactly("csv");
}
~~~

Test này nhấn mạnh rằng parser không coi token kế tiếp là value của option không có dấu bằng. Nếu muốn format có value, hãy truyền --format=csv.

### 13.2. Kiểm thử option bị lặp

~~~java
@Test
void collectsRepeatedOptionValues() {
    ApplicationArguments args = new DefaultApplicationArguments(
            "--tag=one",
            "--tag=two",
            "--tag=three"
    );

    assertThat(args.getOptionNames()).contains("tag");
    assertThat(args.getOptionValues("tag"))
            .containsExactly("one", "two", "three");
}
~~~

Không nên chỉ kiểm tra getOptionNames() khi cần xác nhận số lượng hoặc thứ tự value của một option được lặp.

### 13.3. Kiểm thử runner bằng context

Nếu muốn kiểm tra logic runner cùng dependency injection, có thể tạo Spring test context và cung cấp ApplicationArguments/runner phù hợp. Với test đơn giản về parsing, DefaultApplicationArguments nhẹ hơn và tập trung hơn.

Với một ứng dụng thực tế, có thể dùng @SpringBootTest để xác nhận runner được gọi với tham số truyền vào khi khởi chạy context test. Cần tránh để test vô tình thực hiện import thật, ghi dữ liệu hoặc gọi dịch vụ ngoài; hãy dùng service giả hoặc cấu hình test phù hợp.

## 14. Giới hạn của ApplicationArguments

ApplicationArguments phù hợp với cách parse đơn giản của Spring Boot, nhưng không phải một framework CLI đầy đủ.

Nó không tự cung cấp:

- Short option như -p.
- Cú pháp tự động --name value.
- Kiểu dữ liệu mạnh cho mọi option.
- Help text và tài liệu CLI tự sinh.
- Kiểm tra option không được hỗ trợ theo một schema khai báo.
- Subcommand và nhóm option phức tạp.
- Default value và validation theo annotation cho mọi tham số positional.
- Tự động ánh xạ positional argument vào tên tham số nghiệp vụ.

Nếu ứng dụng chỉ có vài option và một số file đầu vào, ApplicationArguments thường đủ dùng. Nếu CLI trở thành một giao diện sản phẩm có nhiều lệnh và cú pháp, nên cân nhắc công cụ chuyên dụng.

## 15. Khi nào nên dùng picocli hoặc thư viện CLI chuyên dụng?

Một command-line tool lớn có thể cần:

- Lệnh con như import, export, validate.
- Short option và long option.
- Required option.
- Default value.
- Kiểu dữ liệu và converter.
- File/path validation.
- Help và usage text.
- Completion cho shell.
- Error message nhất quán.

Thư viện như **picocli** cung cấp mô hình command/subcommand và annotation để khai báo CLI. Spring Boot có thể tích hợp với picocli thông qua starter hoặc cấu hình thích hợp.

Không cần đưa thư viện CLI vào mọi ứng dụng Spring Boot. Hãy bắt đầu với ApplicationArguments khi nhu cầu nhỏ; chuyển sang parser chuyên dụng khi quy tắc command line trở nên phức tạp và cần được mô tả, kiểm thử như một API.

## 16. Những lỗi thường gặp

### 16.1. Quên truyền args vào SpringApplication.run

**Dấu hiệu:** getOptionNames() rỗng dù lệnh chạy có tham số.

**Nguyên nhân:** phương thức main không chuyển tiếp mảng args.

**Cách sửa:**

~~~java
SpringApplication.run(DemoApplication.class, args);
~~~

### 16.2. Dùng --format csv rồi mong nhận value

**Dấu hiệu:** getOptionValues("format") không có value như mong đợi và csv xuất hiện trong non-option list.

**Nguyên nhân:** parser tách option theo dấu =; token kế tiếp không tự trở thành value.

**Cách sửa:** dùng --format=csv.

### 16.3. Gọi getOptionValues mà không kiểm tra danh sách

**Dấu hiệu:** code truy cập phần tử đầu tiên và gặp lỗi index hoặc xử lý null.

**Nguyên nhân:** option có thể không xuất hiện hoặc xuất hiện mà không có value.

**Cách sửa:** kiểm tra danh sách rỗng, null và chuỗi rỗng trước khi sử dụng.

### 16.4. Chỉ đọc getOptionNames và làm mất giá trị lặp

**Dấu hiệu:** chỉ biết tag xuất hiện nhưng không lấy được toàn bộ tag.

**Nguyên nhân:** getOptionNames trả tập tên, không phải danh sách từng lần xuất hiện.

**Cách sửa:** dùng getOptionValues("tag").

### 16.5. Nhầm non-option argument với giá trị option

**Dấu hiệu:** file đầu vào bị đọc như value của --format.

**Nguyên nhân:** lệnh truyền option không có dấu bằng rồi đặt value ở token kế tiếp.

**Cách sửa:** quy định cú pháp --name=value và kiểm tra non-option list riêng.

### 16.6. Dùng ApplicationArguments cho cấu hình dài hạn

**Dấu hiệu:** nhiều runner tự parse timeout, batch size, endpoint và retry count.

**Nguyên nhân:** trộn command parameters với application configuration.

**Cách sửa:** dùng Environment hoặc @ConfigurationProperties cho cấu hình có kiểu dữ liệu và giá trị mặc định.

### 16.7. Nhầm -D với option của ứng dụng

**Dấu hiệu:** không tìm thấy system property trong getOptionNames hoặc không thấy --mode trong System.getProperty.

**Nguyên nhân:** -D... trước -jar là JVM system property; --... sau tên JAR là application argument.

**Cách sửa:** đọc từ đúng nguồn: System.getProperty, Environment hoặc ApplicationArguments.

### 16.8. Thực hiện tác vụ nguy hiểm ngay khi parse

**Dấu hiệu:** ứng dụng bắt đầu ghi dữ liệu trước khi xác thực đủ các tham số.

**Nguyên nhân:** runner trộn parsing, validation và execution.

**Cách sửa:** phân tách các bước: parse → validate → gọi service. Với --dry-run, bảo đảm service thật sự không ghi dữ liệu.

## 17. Những hiểu nhầm thường gặp

**“Mọi đối số sau tên JAR đều là option.”**  
Không. Chuỗi bắt đầu bằng -- là option; các chuỗi khác là non-option theo parser của Spring Boot.

**“--name value tương đương --name=value.”**  
Không. Token value được phân loại là non-option nếu option trước đó không có dấu =.

**“-p là short option tương đương --port.”**  
Không. ApplicationArguments không tự hỗ trợ short-option alias.

**“Option không có value là false.”**  
Không. --dry-run biểu thị option có mặt nhưng không có giá trị văn bản. Kiểm tra bằng containsOption.

**“getOptionNames cho biết option xuất hiện bao nhiêu lần.”**  
Không. Nó trả tập tên; dùng getOptionValues để lấy các giá trị lặp.

**“ApplicationArguments tự chuyển chuỗi thành int hoặc boolean.”**  
Không. Các giá trị được cung cấp dưới dạng String; cần tự parse hoặc dùng property binding.

**“CommandLineRunner và ApplicationRunner nhận cùng một kiểu tham số.”**  
Không. ApplicationRunner nhận ApplicationArguments; CommandLineRunner nhận mảng String.

**“Command-line arguments chỉ có thể đọc trong runner.”**  
Không. Có thể dùng ApplicationArguments trong runner; các option phù hợp còn có thể được đưa vào Environment như command-line property source mặc định.

**“Tắt addCommandLineProperties nghĩa ApplicationArguments không còn dữ liệu.”**  
Không. Cài đặt đó tắt việc thêm command-line property source vào Environment; nó không thay đổi bản chất mảng arguments được truyền cho SpringApplication.

**“ApplicationReadyEvent xảy ra trước runner.”**  
Không. ApplicationRunner và CommandLineRunner chạy trước ApplicationReadyEvent trong luồng startup thông thường.

## Ghi nhớ cốt lõi

**ApplicationArguments** là API Spring Boot dùng để đọc tham số truyền vào SpringApplication.run(...). Option argument bắt đầu bằng **--**; cú pháp có giá trị rõ ràng là **--name=value**; option dạng cờ như **--dry-run** chỉ cần kiểm tra bằng containsOption. Non-option argument không bắt đầu bằng -- và thường dùng cho tham số theo vị trí như tên file.

getOptionNames() trả tập tên option, getOptionValues(name) trả các giá trị tương ứng, getNonOptionArgs() trả danh sách positional arguments và getSourceArgs() giữ mảng chuỗi gốc. **ApplicationRunner** thuận tiện khi cần các tham số đã phân tích; **CommandLineRunner** nhận chuỗi thô. Hãy dùng ApplicationArguments cho command-line input, Environment hoặc @ConfigurationProperties cho cấu hình ứng dụng, và kiểm tra rõ trường hợp option thiếu value, value rỗng hoặc xuất hiện nhiều lần trước khi thực hiện tác vụ.
