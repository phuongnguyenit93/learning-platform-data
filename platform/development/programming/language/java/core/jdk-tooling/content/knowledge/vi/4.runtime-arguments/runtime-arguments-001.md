# Tham số ứng dụng trong Java

Khi khởi chạy một chương trình Java, có thể truyền dữ liệu đầu vào ngay trên dòng lệnh. Những giá trị này được gọi là **application arguments** (tham số ứng dụng). Java launcher chuyển chúng cho phương thức điểm vào của chương trình, thường là **main(String[] args)**.

Cần phân biệt tham số ứng dụng với tùy chọn của JVM và tùy chọn của Java launcher. Cả ba có thể xuất hiện trên cùng một lệnh, nhưng được xử lý ở các giai đoạn khác nhau. Hiểu ranh giới này giúp cấu hình đúng ứng dụng từ terminal, IDE, build tool, script và container.

## 1. Tham số ứng dụng là gì?

Tham số ứng dụng là các giá trị mà người gọi truyền cho chương trình để thay đổi dữ liệu đầu vào hoặc hành vi của chương trình trong lần chạy đó. Ví dụ:

~~~bash
java -cp out com.example.ReportApp --format csv --output report.csv
~~~

Trong lệnh trên:

- **java** là launcher khởi chạy ứng dụng Java.
- **-cp out** là tùy chọn launcher, chỉ định classpath.
- **com.example.ReportApp** là tên lớp có phương thức main cần chạy.
- **--format csv --output report.csv** là các tham số ứng dụng được truyền vào main.

Ứng dụng tự quyết định ý nghĩa của các tham số. Java không tự hiểu rằng --format là tùy chọn định dạng hoặc --output là tên tệp. Chương trình phải đọc, phân tích, kiểm tra và áp dụng chúng.

Tham số ứng dụng thường được dùng để:

- Chọn chế độ chạy như dev, test hoặc production.
- Chỉ định tệp đầu vào và đầu ra.
- Chọn cổng, host, locale hoặc định dạng dữ liệu.
- Bật/tắt một hành vi của chương trình.
- Truyền tên tác vụ, lệnh con hoặc giá trị cần xử lý.

## 2. Phương thức main và mảng args

Điểm vào truyền thống của một chương trình Java là:

~~~java
public static void main(String[] args) {
    // xử lý tham số tại đây
}
~~~

Khi launcher gọi phương thức này, các tham số ứng dụng được đặt trong mảng String có tên args.

Các đặc điểm cần nhớ:

- Mỗi phần tử của args là một chuỗi String.
- Thứ tự các phần tử được giữ nguyên như thứ tự tham số mà launcher nhận được.
- args[0] là tham số ứng dụng đầu tiên, args[1] là tham số thứ hai, v.v.
- args.length cho biết số tham số.
- Nếu không truyền tham số nào, launcher cung cấp một mảng rỗng có độ dài 0; chương trình không cần giả định args là null.
- Tên lớp, tên JAR, tùy chọn JVM và tùy chọn classpath không nằm trong args.

Java cũng cho phép khai báo main với cú pháp varargs:

~~~java
public static void main(String... args) {
    System.out.println(args.length);
}
~~~

Trong ngữ cảnh khai báo phương thức, String... là dạng biến đối số của String[]. Với launcher Java, đây vẫn là tham số mảng chuỗi của phương thức main.

### In các tham số nhận được

Ví dụ đơn giản:

~~~java
public class ArgsPrinter {
    public static void main(String[] args) {
        System.out.println("count=" + args.length);

        for (int i = 0; i < args.length; i++) {
            System.out.printf("args[%d]=%s%n", i, args[i]);
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 ArgsPrinter.java
java ArgsPrinter alpha beta
~~~

Output:

~~~text
count=2
args[0]=alpha
args[1]=beta
~~~

Ví dụ cho thấy launcher chuyển hai giá trị alpha và beta thành hai phần tử riêng biệt. Nếu không có tham số sau tên lớp, chương trình in count=0.

## 3. Phân biệt JVM options, launcher options và application arguments

Một lệnh chạy Java có thể chứa ba nhóm thông tin:

| Nhóm | Ví dụ | Bên xử lý | Vị trí thường gặp |
|---|---|---|---|
| JVM options | -Xmx512m, -Dapp.env=prod | JVM | Trước tên lớp/JAR/module |
| Launcher options | -cp out, --module-path mods, -jar app.jar | Java launcher | Trước điểm vào, theo cú pháp launcher |
| Application arguments | --port 8080, input.csv | Phương thức main của ứng dụng | Sau tên lớp, JAR hoặc điểm vào module |

Ví dụ:

~~~bash
java -Xmx512m -Dapp.env=production -cp out com.example.Server --port 8080
~~~

Có thể đọc lệnh theo từng phần:

1. -Xmx512m cấu hình heap tối đa của JVM.
2. -Dapp.env=production đặt system property tên app.env.
3. -cp out yêu cầu launcher tìm lớp trong thư mục out.
4. com.example.Server là lớp được khởi chạy.
5. --port 8080 được truyền vào main dưới dạng hai chuỗi.

Trong Java launcher, các tùy chọn phải được đặt đúng vị trí theo cú pháp của lệnh. Khi launcher đã xác định lớp chính, phần đối số theo sau được chuyển cho ứng dụng. Vì vậy, đặt --port trước tên lớp thường không có nghĩa là truyền tham số ứng dụng; launcher có thể hiểu nó là một tùy chọn của chính launcher và báo lỗi.

### Chạy từ JAR

Nếu JAR có manifest chỉ định Main-Class, có thể chạy:

~~~bash
java -jar app.jar --port 8080 --mode batch
~~~

Các giá trị theo sau tên JAR được truyền vào main của lớp chính. Những tùy chọn JVM như -Xmx hoặc -Dapp.env nên được đặt trước -jar:

~~~bash
java -Xmx512m -Dapp.env=production -jar app.jar --port 8080
~~~

Khi dùng -jar, launcher lấy classpath ứng dụng từ cấu hình JAR/manifest; không nên coi -cp là cách bổ sung classpath thông thường cho dạng chạy này.

### Chạy module

Với ứng dụng dùng Java Platform Module System, có thể chạy một module:

~~~bash
java --module-path mods -m com.example.app/com.example.Main --port 8080
~~~

Phần --module-path và -m là tùy chọn launcher. --port 8080 theo sau điểm vào module là tham số ứng dụng.

## 4. Khoảng trắng, dấu nháy và cách shell truyền đối số

Java nhận các đối số sau khi shell của hệ điều hành đã phân tích dòng lệnh. Dấu nháy thường giúp gom nhiều từ thành một đối số duy nhất; bản thân dấu nháy không được đưa vào String trong args.

Ví dụ:

~~~bash
java ArgsPrinter one "two words" three
~~~

Ứng dụng nhận ba phần tử:

~~~text
args[0]=one
args[1]=two words
args[2]=three
~~~

Một số trường hợp cần lưu ý:

- "two words" tạo một đối số có khoảng trắng.
- "" tạo một đối số chuỗi rỗng.
- Không có đối số nào sau tên lớp tạo mảng args rỗng.
- Ký tự escape, dấu nháy đơn và dấu nháy kép được shell xử lý theo quy tắc riêng của từng môi trường.

Cú pháp trích dẫn có khác biệt giữa Bash/Zsh, PowerShell và Windows Command Prompt. Khi viết script dùng nhiều hệ điều hành, cần kiểm thử cách shell tạo đối số thực tế thay vì giả định mọi shell xử lý dấu nháy giống nhau.

Ứng dụng có thể in từng phần tử và độ dài của nó để chẩn đoán vấn đề quoting. Không nên tự tách một chuỗi lệnh bằng khoảng trắng rồi coi kết quả tương đương với mảng args, vì cách đó làm mất ranh giới của đối số có khoảng trắng hoặc ký tự escape.

## 5. Phân tích và kiểm tra tham số

Java cung cấp mảng String; ứng dụng chịu trách nhiệm quy định cú pháp. Một chương trình có thể nhận tham số theo vị trí hoặc theo dạng tên.

### Tham số theo vị trí

Ví dụ:

~~~bash
java CopyFile source.txt backup.txt
~~~

Quy ước của ứng dụng có thể là:

- args[0]: tệp nguồn.
- args[1]: tệp đích.
- Yêu cầu args.length phải bằng 2.

Cách này đơn giản cho lệnh ít tham số, nhưng khi số tùy chọn tăng lên, người dùng phải nhớ thứ tự chính xác.

### Tham số dạng tên

Ví dụ:

~~~bash
java Server --host localhost --port 8080
~~~

Ứng dụng có thể nhận các cặp tên/giá trị và không phụ thuộc thứ tự, miễn là parser được viết để hỗ trợ. Dạng tên dễ đọc hơn khi có nhiều cấu hình, nhưng cần xử lý trường hợp thiếu giá trị, tùy chọn lặp lại hoặc tên không hợp lệ.

### Quy trình parse an toàn

Một parser cơ bản nên thực hiện:

1. Xác định cú pháp hợp lệ và giá trị mặc định.
2. Đọc từng đối số theo đúng thứ tự.
3. Phân biệt option, value và positional argument.
4. Kiểm tra giá trị có tồn tại khi option yêu cầu value.
5. Chuyển đổi kiểu, ví dụ String sang int hoặc Path.
6. Kiểm tra miền giá trị và quan hệ giữa các tùy chọn.
7. Báo lỗi dễ hiểu và hướng dẫn cách gọi khi đầu vào sai.
8. Chỉ thực hiện tác vụ sau khi toàn bộ cấu hình đã hợp lệ.

Không nên truy cập args[0] trước khi kiểm tra args.length. Nếu không có tham số, truy cập chỉ số 0 sẽ gây ArrayIndexOutOfBoundsException.

Không nên ép kiểu dữ liệu trực tiếp từ String. Ví dụ, Integer.parseInt có thể ném NumberFormatException; ứng dụng cần bắt lỗi và thông báo tham số nào không hợp lệ. Với đường dẫn, có thể dùng Path.of rồi kiểm tra file tồn tại, quyền đọc hoặc quyền ghi tùy yêu cầu.

## 6. Ví dụ hoàn chỉnh: parse host, port và tag

Ví dụ sau dùng Java 17, nhận ba tùy chọn dạng tên:

- --host HOST: tên host, mặc định localhost.
- --port PORT: cổng từ 1 đến 65535, mặc định 8080.
- --tag TAG: nhãn chạy, mặc định local.
- -Dapp.env=VALUE: system property của JVM, mặc định local.

Tạo tệp src/AppArgsDemo.java:

~~~java
public final class AppArgsDemo {
    private AppArgsDemo() {
    }

    public static void main(String[] args) {
        try {
            Options options = Options.parse(args);
            String environment = System.getProperty("app.env", "local");

            System.out.printf("environment=%s%n", environment);
            System.out.printf("host=%s%n", options.host());
            System.out.printf("port=%d%n", options.port());
            System.out.printf("tag=%s%n", options.tag());
        } catch (IllegalArgumentException ex) {
            System.err.println("Error: " + ex.getMessage());
            System.err.println(
                "Usage: java -Dapp.env=production -cp out AppArgsDemo "
                + "[--host HOST] [--port PORT] [--tag TAG]"
            );
            System.exit(2);
        }
    }

    private record Options(String host, int port, String tag) {
        static Options parse(String[] args) {
            String host = "localhost";
            int port = 8080;
            String tag = "local";

            for (int i = 0; i < args.length; i++) {
                switch (args[i]) {
                    case "--host" -> {
                        host = requireValue(args, i);
                        i++;
                    }
                    case "--port" -> {
                        String value = requireValue(args, i);
                        i++;

                        try {
                            port = Integer.parseInt(value);
                        } catch (NumberFormatException ex) {
                            throw new IllegalArgumentException(
                                "--port must be an integer: " + value
                            );
                        }

                        if (port < 1 || port > 65535) {
                            throw new IllegalArgumentException(
                                "--port must be between 1 and 65535"
                            );
                        }
                    }
                    case "--tag" -> {
                        tag = requireValue(args, i);
                        i++;
                    }
                    default -> throw new IllegalArgumentException(
                        "Unknown argument: " + args[i]
                    );
                }
            }

            return new Options(host, port, tag);
        }
    }

    private static String requireValue(String[] args, int optionIndex) {
        int valueIndex = optionIndex + 1;

        if (valueIndex >= args.length || args[valueIndex].startsWith("--")) {
            throw new IllegalArgumentException(
                "Missing value for " + args[optionIndex]
            );
        }

        return args[valueIndex];
    }
}
~~~

Từ thư mục dự án, tạo thư mục đầu ra, biên dịch và chạy:

~~~bash
mkdir out
javac --release 17 -d out src/AppArgsDemo.java
java -Dapp.env=production -cp out AppArgsDemo --host api.internal --port 9090 --tag "nightly build"
~~~

Output:

~~~text
environment=production
host=api.internal
port=9090
tag=nightly build
~~~

Điểm cần quan sát:

- System property app.env được đọc bằng System.getProperty; nó không xuất hiện trong args.
- --host, --port và --tag là dữ liệu ứng dụng và xuất hiện trong args.
- Chuỗi "nightly build" được shell truyền thành một đối số có khoảng trắng.
- Record Options giữ cấu hình đã parse và có kiểu rõ ràng.
- Parser kiểm tra thiếu giá trị, số nguyên và giới hạn cổng trước khi chương trình sử dụng cấu hình.

Thử truyền giá trị cổng sai:

~~~bash
java -cp out AppArgsDemo --port abc
~~~

Chương trình in thông báo lỗi ra stderr, hướng dẫn sử dụng và kết thúc với exit code 2. Đây là quy ước của ứng dụng trong ví dụ; Java không tự quy định mã thoát 2 cho mọi lỗi tham số.

Parser này cố ý chỉ hỗ trợ các option đã liệt kê, không hỗ trợ positional argument, option viết gộp, dấu bằng như --port=9090 hoặc option lặp lại. Với CLI phức tạp, nên dùng thư viện chuyên dụng thay vì tự phát triển parser lớn.

## 7. Tham số ứng dụng, system property và environment variable

Ba cơ chế này đều có thể truyền cấu hình cho ứng dụng, nhưng khác nhau về nguồn và cách truy cập.

| Cơ chế | Cách truyền | Cách đọc trong Java | Ví dụ |
|---|---|---|---|
| Application argument | Sau điểm vào lớp/JAR/module | args | --port 8080 |
| System property | Tùy chọn JVM -D trước điểm vào | System.getProperty | -Dapp.env=prod |
| Environment variable | Môi trường của process | System.getenv | APP_ENV=prod |

### Application arguments

Phù hợp với dữ liệu đầu vào cụ thể của một lần chạy: tên tệp, tác vụ, chế độ, tham số truy vấn hoặc tùy chọn CLI. Chúng thường hiển thị trong lệnh gọi chương trình.

### System properties

System property là cặp tên/giá trị gắn với JVM. Có thể đặt từ dòng lệnh bằng -Dname=value:

~~~bash
java -Dapp.region=ap-southeast-1 -cp out AppArgsDemo
~~~

Đọc trong Java:

~~~java
String region = System.getProperty("app.region", "local");
~~~

System property cũng có thể được đặt hoặc thay đổi trong process bằng System.setProperty. Không nên dùng system property như kho lưu trữ bí mật.

### Environment variables

Environment variable được thiết lập trong môi trường process trước khi chương trình chạy. Ví dụ trên shell kiểu POSIX:

~~~bash
APP_ENV=production java -cp out AppArgsDemo
~~~

Đọc trong Java:

~~~java
String environment = System.getenv("APP_ENV");
~~~

Trên Windows, cách đặt biến môi trường trong terminal khác với Bash. Ứng dụng Java vẫn đọc qua System.getenv.

### Chọn cơ chế nào?

- Dùng application arguments cho lệnh và dữ liệu mà người gọi muốn chỉ định rõ ràng ở mỗi lần chạy.
- Dùng system properties cho cấu hình JVM hoặc cấu hình ứng dụng cần truyền theo quy ước -D.
- Dùng environment variables cho cấu hình triển khai được cung cấp bởi môi trường, container hoặc nền tảng vận hành.
- Dùng tệp cấu hình hoặc secret manager khi cấu hình có cấu trúc lớn, cần quản lý vòng đời hoặc chứa thông tin nhạy cảm.

Nếu cùng một giá trị được cung cấp từ nhiều nguồn, ứng dụng phải quy định thứ tự ưu tiên rõ ràng, ví dụ CLI ghi đè environment variable và giá trị mặc định. Java không tự áp dụng một thứ tự ưu tiên cấu hình thống nhất cho mọi ứng dụng.

## 8. Cấu hình trong IDE, Maven và Gradle

Khi chạy từ IDE, thường có hai trường riêng:

- **Program arguments:** tham số được truyền vào main, tức args.
- **VM options / VM arguments:** tùy chọn JVM như -Xmx hoặc -Dapp.env=production.

Không nhập --port 8080 vào VM options nếu đó là tham số mà chương trình cần đọc từ args. Ngược lại, -Dapp.env=production phải nằm ở VM options khi cấu hình chạy ứng dụng trực tiếp.

Trong Maven hoặc Gradle, build tool có thể tạo process Java riêng để chạy ứng dụng hoặc test. Vì vậy, cần xác định tham số đang được truyền cho:

- JVM chạy chính build tool.
- Compiler hoặc plugin.
- JVM con chạy test.
- Ứng dụng Java mà task run khởi chạy.

Một cờ -D truyền cho tiến trình Maven/Gradle không nhất thiết trở thành application argument của ứng dụng. Cần dùng cấu hình của task/plugin để chuyển program arguments đúng nơi. Tên thuộc tính cụ thể tùy phiên bản plugin và build tool.

## 9. Truyền tham số cho ứng dụng trong Docker

Với Dockerfile dùng exec form:

~~~dockerfile
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
CMD ["--port", "8080"]
~~~

CMD cung cấp các tham số mặc định được nối vào ENTRYPOINT. Khi chạy:

~~~bash
docker run --rm my-java-app
~~~

Ứng dụng nhận --port và 8080.

Có thể ghi đè tham số mặc định:

~~~bash
docker run --rm my-java-app --port 9090
~~~

Khi đó, ứng dụng nhận --port 9090. Cách khai báo này giữ JVM là process chính và truyền tham số ứng dụng qua command line.

Nếu dùng shell form hoặc một script entrypoint, script cần chuyển tiếp đối số đúng cách. Trong shell script, cấu trúc exec java ... "$@" giúp thay process script bằng JVM và giữ ranh giới từng đối số. Không nên ghép toàn bộ đối số thành một chuỗi rồi tự tách lại bằng khoảng trắng.

## 10. Bảo mật và lỗi thường gặp

### Không truyền bí mật qua command line

Tham số dòng lệnh có thể xuất hiện trong process listing, log, lịch sử shell, hệ thống giám sát hoặc thông tin chẩn đoán. Tránh truyền password, access token, private key hoặc secret trực tiếp qua args hay system property. Dùng secret manager, file mount được bảo vệ hoặc cơ chế cấp thông tin xác thực phù hợp.

### Không giả định kiểu dữ liệu

Tất cả application arguments đều là String. Nếu cần số nguyên, boolean, enum, ngày giờ hoặc đường dẫn, hãy parse và validate rõ ràng. Xử lý NumberFormatException và lỗi định dạng theo cách giúp người dùng biết tham số nào sai.

### Không giả định thứ tự tùy chọn

Nếu parser hỗ trợ option dạng tên, hãy xác định rõ có cho phép đổi thứ tự hay không. Không nên truy cập args[0] và args[1] theo vị trí nếu cú pháp thực tế cho phép người dùng truyền option linh hoạt.

### Phân biệt thiếu tham số và chuỗi rỗng

args.length == 0 có nghĩa là không truyền đối số. Một phần tử có giá trị chuỗi rỗng có thể được truyền bằng dấu nháy rỗng theo cú pháp shell. Hai trường hợp này không giống nhau.

### Xử lý option lặp lại

Ví dụ --port 8080 --port 9090 có thể bị từ chối hoặc áp dụng quy tắc “giá trị cuối cùng thắng”. Đây là quyết định của parser; cần ghi rõ trong tài liệu sử dụng.

### Báo lỗi và exit code

Khi đầu vào sai, in thông báo ngắn gọn ra stderr, cung cấp cú pháp sử dụng và trả về exit code khác 0. Không nên chỉ in stack trace dài cho lỗi nhập liệu thông thường. Exit code giúp shell script và hệ thống CI nhận biết lệnh thất bại.

## 11. Checklist thiết kế tham số ứng dụng

- Xác định rõ tham số nào là JVM option, launcher option và application argument.
- Viết cú pháp CLI và ví dụ gọi lệnh trong tài liệu.
- Quy định tham số bắt buộc, mặc định, kiểu dữ liệu và miền giá trị.
- Chọn tham số theo vị trí hoặc theo tên phù hợp với số lượng tùy chọn.
- Kiểm tra args.length trước khi truy cập chỉ số.
- Parse và validate toàn bộ đầu vào trước khi bắt đầu tác vụ.
- Xử lý khoảng trắng và quoting đúng với shell mục tiêu.
- Tách program arguments khỏi VM options trong IDE và build tool.
- Quy định thứ tự ưu tiên giữa CLI, system property, environment variable và cấu hình tệp.
- Không truyền bí mật qua command line hoặc log.
- In usage khi có lỗi và trả exit code khác 0.
- Kiểm thử trường hợp không có đối số, thiếu giá trị, giá trị sai, chuỗi có khoảng trắng và option không xác định.

## 12. Thuật ngữ cần nhớ

| Thuật ngữ | Ý nghĩa |
|---|---|
| Application argument | Giá trị được truyền cho chương trình khi khởi chạy |
| args | Mảng String chứa tham số ứng dụng trong main |
| JVM option | Tùy chọn cấu hình máy ảo, ví dụ -Xmx |
| Launcher option | Tùy chọn của Java launcher, ví dụ -cp hoặc -jar |
| System property | Cặp tên/giá trị của JVM, thường đặt bằng -D |
| Environment variable | Biến môi trường được process kế thừa |
| Positional argument | Tham số được diễn giải dựa trên vị trí |
| Named option | Tham số có tên như --port |
| Parser | Thành phần phân tích chuỗi đối số thành cấu hình có ý nghĩa |
| Validation | Kiểm tra đầu vào hợp lệ trước khi sử dụng |
| Exit code | Mã trạng thái process trả về cho hệ điều hành |

Điểm cần nhớ: **mọi tham số ứng dụng trong main đều là String**. Java launcher chỉ chuyển chúng đến điểm vào; chính ứng dụng định nghĩa cú pháp, chuyển đổi kiểu, kiểm tra giá trị và quyết định cách sử dụng. Phân biệt rõ args với JVM options và launcher options sẽ giúp lệnh chạy nhất quán từ terminal, IDE, build tool và container.