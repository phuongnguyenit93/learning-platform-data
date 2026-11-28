# Xây CLI chào hỏi với tùy chọn, đối số và trợ giúp rõ ràng

Một CLI nhỏ là cách tốt để kiểm tra toàn bộ đường đi của một command: người dùng gõ tên lệnh, parser tách đối số và tùy chọn, Spring Shell chuyển giá trị vào method, command kiểm tra dữ liệu rồi trả kết quả ra terminal. Bài thực hành này xây dựng một ứng dụng chào hỏi bằng Spring Shell 4.x. Người dùng có thể nhập tên, chọn ngôn ngữ, bật chữ hoa và tự xem hướng dẫn ngay trong shell.

Ứng dụng chỉ có một command nghiệp vụ là greet. Dù nhỏ, command này thể hiện những phần cơ bản cần có trong một CLI dễ dùng: tên command dễ nhớ, đối số vị trí có giá trị mặc định, tùy chọn có tên và viết tắt, kiểm tra giá trị đầu vào, mô tả ngắn và phần help có ví dụ.

## Mục tiêu thực hành

Sau bài học, bạn có thể:

- Tạo một ứng dụng Spring Boot có Spring Shell starter.
- Đăng ký command bằng @Component và @Command.
- Khai báo đối số vị trí bằng @Argument.
- Khai báo tùy chọn dài và tùy chọn ngắn bằng @Option.
- Đặt mô tả, nhóm lệnh và phần hướng dẫn cho command.
- Hiểu cách giá trị mặc định được áp dụng khi người dùng bỏ qua input.
- Phân tích cú pháp command có dấu cách và dấu nháy.
- Validate tên và ngôn ngữ trước khi tạo lời chào.
- Dùng command help tích hợp để xem danh sách và hướng dẫn chi tiết.
- Kiểm thử command bằng ShellTestClient.
- Chạy ứng dụng trong terminal và thử các tình huống hợp lệ, không hợp lệ.

## 1. Kết quả mong đợi

Ứng dụng cung cấp command:

~~~text
greet [name] [--language <vi|en>] [--uppercase]
~~~

Trong đó:

| Thành phần | Ý nghĩa | Giá trị mặc định |
|---|---|---|
| name | Tên người được chào, là đối số vị trí | bạn |
| --language, -l | Ngôn ngữ của lời chào | vi |
| --uppercase, -u | Chuyển toàn bộ lời chào thành chữ hoa | false |

Ví dụ:

~~~text
shell:> greet
Xin chào, bạn!

shell:> greet An
Xin chào, An!

shell:> greet "Nguyễn An" --language en
Hello, Nguyễn An!

shell:> greet Linh -l vi -u
XIN CHÀO, LINH!
~~~

Command cũng có hướng dẫn tích hợp:

~~~text
shell:> help
~~~

Lệnh help liệt kê các command đã đăng ký và mô tả ngắn của chúng. Để xem riêng command chào hỏi:

~~~text
shell:> help greet
~~~

Phần trợ giúp chi tiết hiển thị cú pháp, đối số, tùy chọn và mô tả đã khai báo trong annotation.

## 2. Tạo project và thêm dependency

Tạo một ứng dụng Spring Boot với Java tương thích với phiên bản Spring Shell đang chọn. Thêm starter của Spring Shell vào Maven:

~~~xml
<dependency>
    <groupId>org.springframework.shell</groupId>
    <artifactId>spring-shell-starter</artifactId>
    <version>4.0.3</version>
</dependency>
~~~

Nếu dự án đã quản lý phiên bản Spring Shell bằng dependency management hoặc BOM tương ứng, bỏ thẻ version ở dependency và để bộ quản lý phiên bản cung cấp giá trị nhất quán. Không trộn các module Spring Shell thuộc những phiên bản khác nhau.

Starter cung cấp tích hợp Spring Boot và các command chuẩn, trong đó có help. Nếu dùng các module thấp hơn thay cho starter, cần tự bảo đảm những thành phần command chuẩn mà ứng dụng mong đợi đã có mặt.

Cấu trúc source tối thiểu:

~~~text
src/
  main/
    java/
      com/example/greeting/
        GreetingApplication.java
        GreetingCommands.java
  test/
    java/
      com/example/greeting/
        GreetingCommandsTests.java
~~~

## 3. Tạo lớp khởi động Spring Boot

Tạo GreetingApplication.java:

~~~java
package com.example.greeting;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class GreetingApplication {

    public static void main(String[] args) {
        SpringApplication.run(GreetingApplication.class, args);
    }
}
~~~

@SpringBootApplication bật auto-configuration và component scanning từ package chứa lớp khởi động trở xuống. Vì GreetingCommands nằm trong cùng package, Spring sẽ phát hiện bean command khi ứng dụng khởi động.

Với ứng dụng Spring Boot, không cần thêm @EnableCommand thủ công cho lớp command được component scan. Nếu xây ứng dụng Spring không dùng Spring Boot, cần đăng ký command target bằng @EnableCommand trên một configuration class.

## 4. Viết command chào hỏi

Tạo GreetingCommands.java:

~~~java
package com.example.greeting;

import java.util.Locale;

import org.springframework.shell.core.command.annotation.Argument;
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.Option;
import org.springframework.stereotype.Component;

@Component
public class GreetingCommands {

    @Command(
            name = "greet",
            description = "Chào một người bằng ngôn ngữ được chọn.",
            group = "Chào hỏi",
            help = "Hiển thị lời chào cho một tên. Ví dụ: greet; "
                    + "greet An; greet \"Nguyễn An\" --language en; "
                    + "greet Linh -l vi -u")
    public String greet(
            @Argument(
                    index = 0,
                    description = "Tên người được chào",
                    defaultValue = "bạn")
            String name,
            @Option(
                    shortName = 'l',
                    longName = "language",
                    description = "Ngôn ngữ lời chào: vi hoặc en",
                    defaultValue = "vi")
            String language,
            @Option(
                    shortName = 'u',
                    longName = "uppercase",
                    description = "Chuyển lời chào thành chữ hoa",
                    defaultValue = "false")
            boolean uppercase) {

        String normalizedName = name.strip();
        if (normalizedName.isBlank()) {
            throw new IllegalArgumentException(
                    "Tên người được chào không được để trống.");
        }

        String message = switch (language.toLowerCase(Locale.ROOT)) {
            case "vi" -> "Xin chào, " + normalizedName + "!";
            case "en" -> "Hello, " + normalizedName + "!";
            default -> throw new IllegalArgumentException(
                    "Ngôn ngữ không được hỗ trợ: " + language
                            + ". Hãy chọn vi hoặc en.");
        };

        return uppercase ? message.toUpperCase(Locale.ROOT) : message;
    }
}
~~~

Đây là toàn bộ command nghiệp vụ của bài thực hành. Method trả về String; Spring Shell sẽ ghi giá trị trả về vào output của shell. Vì vậy, command không cần tự gọi System.out.println().

### 4.1. Vì sao dùng @Component?

Annotation @Component đăng ký GreetingCommands thành Spring bean. Spring Shell tìm các method được đánh dấu @Command trong những bean phù hợp và tạo command tương ứng.

Nếu class không được Spring quản lý, method có @Command sẽ không tự xuất hiện trong shell. Khi command không hiển thị trong help, hãy kiểm tra package scan và việc class có được đăng ký thành bean hay không.

### 4.2. Đặt tên và mô tả command

Phần annotation:

~~~java
@Command(
        name = "greet",
        description = "Chào một người bằng ngôn ngữ được chọn.",
        group = "Chào hỏi",
        help = "Hiển thị lời chào cho một tên. Ví dụ: ...")
~~~

Các thuộc tính có mục đích riêng:

| Thuộc tính | Mục đích |
|---|---|
| name | Tên mà người dùng gõ để gọi command |
| description | Mô tả ngắn hiển thị trong danh sách help |
| group | Nhóm dùng để tổ chức command trong tài liệu trợ giúp |
| help | Hướng dẫn dài hơn, có thể kèm ví dụ sử dụng |

group là nhãn phân nhóm trong help; nó không tự thêm tiền tố vào cú pháp command. Người dùng vẫn gọi greet, không phải chao-hoi greet.

Tên command nên ngắn, ổn định và dùng từ mà người vận hành dễ nhớ. Mô tả nên nói rõ hành động của command. Phần help có thể giải thích thêm cách kết hợp option và đưa ra ví dụ copy được.

### 4.3. Khai báo đối số vị trí bằng @Argument

Đối số đầu tiên:

~~~java
@Argument(
        index = 0,
        description = "Tên người được chào",
        defaultValue = "bạn")
String name
~~~

@Argument dùng cho giá trị được xác định theo vị trí trong command line. index bắt đầu từ 0:

- index = 0 là đối số vị trí thứ nhất.
- index = 1 là đối số vị trí thứ hai.
- Các đối số tiếp theo tăng dần theo thứ tự.

name có defaultValue là bạn. Vì vậy, khi người dùng chỉ gõ greet, Spring Shell đưa giá trị mặc định vào tham số name.

Khi người dùng gõ greet An, giá trị An được dùng thay cho mặc định.

Đối số vị trí phù hợp với một giá trị tự nhiên, thường xuyên xuất hiện và dễ hiểu từ vị trí của nó. Nếu command có nhiều giá trị dễ nhầm lẫn, hãy ưu tiên option có tên rõ ràng.

### 4.4. Khai báo tùy chọn bằng @Option

Tùy chọn ngôn ngữ:

~~~java
@Option(
        shortName = 'l',
        longName = "language",
        description = "Ngôn ngữ lời chào: vi hoặc en",
        defaultValue = "vi")
String language
~~~

Tùy chọn có hai cách gọi:

- Dạng dài: --language vi
- Dạng ngắn: -l vi

Tùy chọn có tên giúp người đọc hiểu ý nghĩa giá trị ngay cả khi command có nhiều tham số. shortName là một ký tự; longName là tên dài dễ đọc.

Tùy chọn uppercase:

~~~java
@Option(
        shortName = 'u',
        longName = "uppercase",
        description = "Chuyển lời chào thành chữ hoa",
        defaultValue = "false")
boolean uppercase
~~~

Đây là option kiểu boolean. Mặc định false nên lời chào giữ nguyên kiểu chữ. Người dùng có thể bật cờ bằng:

~~~text
greet An --uppercase
greet An -u
~~~

Có thể truyền giá trị boolean tường minh:

~~~text
greet An --uppercase=true
greet An --uppercase false
~~~

Trong cú pháp Spring Shell 4.x, boolean option có thể được dùng như cờ không kèm giá trị để bật true. Những option khác cần có giá trị theo kiểu dữ liệu của chúng.

## 5. Phân biệt đối số và tùy chọn

Đối số vị trí và option đều cung cấp dữ liệu cho method command, nhưng cách người dùng biểu đạt khác nhau:

| Đặc điểm | Đối số vị trí | Tùy chọn |
|---|---|---|
| Annotation | @Argument | @Option |
| Nhận diện | Vị trí trong command | Tên option |
| Cú pháp ví dụ | greet An | greet --language en |
| Giá trị mặc định | Có thể khai báo | Có thể khai báo |
| Dạng ngắn | Không có | Có thể có, ví dụ -l |
| Phù hợp | Giá trị chính, đơn giản | Cấu hình bổ sung hoặc giá trị có thể tùy chỉnh |

Với command greet:

~~~text
greet "Nguyễn An" --language en --uppercase
~~~

Nguyễn An là đối số vị trí. en là giá trị của option language. uppercase là cờ boolean.

Spring Shell hỗ trợ option và argument theo cú pháp dài/ngắn. Option và argument có thể xuất hiện theo thứ tự khác nhau trong command line. Tuy nhiên, để command dễ đọc, hãy giữ cách trình bày nhất quán trong tài liệu và ví dụ.

## 6. Cách parser xử lý giá trị có dấu cách

Parser chia input thành các từ theo khoảng trắng. Nếu giá trị chứa dấu cách, hãy đặt toàn bộ giá trị trong dấu nháy đơn hoặc nháy kép.

Ví dụ đúng:

~~~text
greet "Nguyễn An"
greet 'Nguyễn An'
greet --language en "Nguyễn An"
~~~

Trong các ví dụ này, command nhận name là một chuỗi Nguyễn An.

Nếu bỏ dấu nháy:

~~~text
greet Nguyễn An
~~~

parser có thể hiểu Nguyễn và An là hai đối số riêng. Vì command hiện chỉ khai báo một đối số name, input đó không còn đúng hợp đồng.

Có thể dùng dấu nháy kép khi giá trị chứa dấu nháy đơn và ngược lại:

~~~text
greet "An's team"
greet 'An nói "Xin chào"'
~~~

Nếu cần đưa chính dấu nháy đang bao quanh vào giá trị, escape dấu nháy bằng dấu gạch chéo ngược theo quy tắc parser. Không dùng cách quoting của Bash hoặc PowerShell để suy luận máy móc cách parser nội bộ của Spring Shell xử lý chuỗi; hai lớp parser có thể khác nhau khi command được gọi từ terminal bên ngoài.

## 7. Validate dữ liệu đầu vào

Một CLI dễ dùng phải báo lỗi rõ khi người dùng truyền dữ liệu không hợp lệ. Trong ví dụ này có hai quy tắc:

1. Tên người được chào không được rỗng hoặc chỉ có khoảng trắng.
2. language chỉ nhận vi hoặc en.

Kiểm tra tên:

~~~java
String normalizedName = name.strip();
if (normalizedName.isBlank()) {
    throw new IllegalArgumentException(
            "Tên người được chào không được để trống.");
}
~~~

strip() loại bỏ khoảng trắng ở hai đầu chuỗi. isBlank() phát hiện chuỗi rỗng hoặc chỉ chứa whitespace.

Kiểm tra ngôn ngữ:

~~~java
String message = switch (language.toLowerCase(Locale.ROOT)) {
    case "vi" -> "Xin chào, " + normalizedName + "!";
    case "en" -> "Hello, " + normalizedName + "!";
    default -> throw new IllegalArgumentException(
            "Ngôn ngữ không được hỗ trợ: " + language
                    + ". Hãy chọn vi hoặc en.");
};
~~~

Locale.ROOT giúp chuẩn hóa mã ngôn ngữ theo quy tắc không phụ thuộc locale mặc định của máy đang chạy. Nếu người dùng gõ EN hoặc En, command vẫn chấp nhận và xử lý như en.

Validation diễn ra trước khi tạo kết quả. Khi input không hợp lệ, command ném IllegalArgumentException để Spring Shell xử lý lỗi thực thi và hiển thị thông báo. Không tiếp tục trả lời như thể thao tác thành công.

Với command thực tế, validation có thể được khai báo bằng Bean Validation annotation trên tham số nếu ứng dụng đã có dependency validation phù hợp. Bài này dùng kiểm tra trực tiếp để làm rõ quy tắc nghiệp vụ và không yêu cầu thêm dependency.

## 8. Trợ giúp rõ ràng ngay trong shell

Trợ giúp của Spring Shell được tạo từ metadata command và tham số. Hãy khai báo mô tả ở cả cấp command và cấp từng tham số.

### 8.1. Danh sách command

Gõ:

~~~text
help
~~~

Spring Shell hiển thị danh sách command đã đăng ký cùng mô tả ngắn. Người dùng có thể nhận ra greet làm gì mà chưa cần đọc source code.

### 8.2. Trợ giúp chi tiết

Gõ:

~~~text
help greet
~~~

Phần help chi tiết lấy thông tin từ:

- @Command.description: mô tả ngắn.
- @Command.help: giải thích và ví dụ.
- @Argument.description: ý nghĩa đối số name.
- @Option.description: ý nghĩa language và uppercase.
- defaultValue: giá trị được dùng khi input bị bỏ qua.

Định dạng và cách sắp xếp các mục có thể thay đổi theo phiên bản hoặc terminal theme. Điều quan trọng là nội dung mô tả và cú pháp phải rõ ràng, nhất quán với hành vi thật.

### 8.3. Viết help hướng tới người sử dụng

Một phần help tốt nên trả lời:

- Command thực hiện việc gì?
- Đối số nào có thể hoặc phải truyền?
- Option nào có sẵn?
- Giá trị mặc định là gì?
- Các giá trị nào được chấp nhận?
- Có ví dụ nào cho cách gọi phổ biến?

Ví dụ help của greet nêu rõ hai ngôn ngữ được hỗ trợ và cung cấp cách gọi với cả tên có dấu cách. Người dùng có thể sao chép ví dụ và điều chỉnh tên của mình.

Với command được khai báo theo annotation như bài này, dùng built-in command help để xem hướng dẫn. Không giả định mọi method command đều tự có option --help hoặc -h; cách xử lý các cờ help đó phụ thuộc loại command và cơ chế đăng ký tương ứng.

## 9. Chạy ứng dụng

Từ thư mục project, chạy bằng Maven:

~~~bash
./mvnw spring-boot:run
~~~

Trên Windows:

~~~powershell
.\mvnw.cmd spring-boot:run
~~~

Khi shell khởi động, thử các lệnh:

~~~text
greet
greet An
greet "Nguyễn An"
greet "Nguyễn An" --language en
greet Linh -l vi -u
help
help greet
~~~

Nếu muốn chạy artifact đã đóng gói:

~~~bash
./mvnw package
java -jar target/greeting-cli-0.0.1-SNAPSHOT.jar
~~~

Tên JAR thực tế phụ thuộc artifactId và version trong pom.xml. Hãy thay đường dẫn ví dụ bằng file được build của project.

## 10. Kiểm tra các trường hợp lỗi

Thử ngôn ngữ không hỗ trợ:

~~~text
greet An --language fr
~~~

Command phải báo rằng fr không nằm trong tập giá trị hỗ trợ và gợi ý vi hoặc en.

Thử tên chỉ có khoảng trắng:

~~~text
greet "   "
~~~

Command phải báo tên không được để trống.

Thử truyền option thiếu giá trị:

~~~text
greet An --language
~~~

Parser sẽ báo lỗi cú pháp hoặc thiếu giá trị option trước khi command chạy. Đây là lỗi ở ranh giới cú pháp, khác với lỗi validation do method command tự phát hiện.

Phân biệt hai nhóm lỗi:

| Nhóm | Ví dụ | Nơi xử lý |
|---|---|---|
| Lỗi cú pháp | Thiếu giá trị --language, option không tồn tại | Command parser và framework |
| Lỗi nghiệp vụ | language=fr, tên chỉ có khoảng trắng | Logic validation trong command |

Thông báo lỗi cần giúp người dùng biết nên sửa phần nào. Không nên để lỗi nội bộ như NullPointerException trở thành phản hồi thông thường cho input sai.

## 11. Kiểm thử command bằng ShellTestClient

Spring Shell cung cấp test utilities để gửi command như thể người dùng nhập vào shell và kiểm tra output.

Để dùng @ShellTest, thêm các module test của Spring Shell cùng phiên bản với starter:

~~~xml
<dependency>
    <groupId>org.springframework.shell</groupId>
    <artifactId>spring-shell-test</artifactId>
    <version>4.0.3</version>
    <scope>test</scope>
</dependency>
<dependency>
    <groupId>org.springframework.shell</groupId>
    <artifactId>spring-shell-test-autoconfigure</artifactId>
    <version>4.0.3</version>
    <scope>test</scope>
</dependency>
~~~

Đồng thời, dự án cần dependency kiểm thử Spring/JUnit phù hợp, thường được cung cấp qua spring-boot-starter-test.

Tạo GreetingCommandsTests.java:

~~~java
package com.example.greeting;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.shell.test.ShellAssertions;
import org.springframework.shell.test.ShellScreen;
import org.springframework.shell.test.ShellTestClient;
import org.springframework.shell.test.autoconfigure.ShellTest;
import org.springframework.test.context.ContextConfiguration;

@ShellTest
@ContextConfiguration(classes = GreetingApplication.class)
class GreetingCommandsTests {

    @Autowired
    ShellTestClient client;

    @Test
    void usesDefaultNameAndLanguage() throws Exception {
        ShellScreen screen = client.sendCommand("greet");

        ShellAssertions.assertThat(screen)
                .containsText("Xin chào, bạn!");
    }

    @Test
    void acceptsNameAndLanguageOption() throws Exception {
        ShellScreen screen = client.sendCommand(
                "greet \"Nguyễn An\" --language en");

        ShellAssertions.assertThat(screen)
                .containsText("Hello, Nguyễn An!");
    }

    @Test
    void acceptsShortBooleanOption() throws Exception {
        ShellScreen screen = client.sendCommand("greet Linh -l vi -u");

        ShellAssertions.assertThat(screen)
                .containsText("XIN CHÀO, LINH!");
    }

    @Test
    void exposesDetailedHelp() throws Exception {
        ShellScreen screen = client.sendCommand("help greet");

        ShellAssertions.assertThat(screen)
                .containsText("greet")
                .containsText("--language")
                .containsText("--uppercase");
    }
}
~~~

@ShellTest thiết lập test context dành cho Spring Shell. @ContextConfiguration chỉ rõ ứng dụng chứa command. ShellTestClient gửi chuỗi command và trả về ShellScreen để kiểm tra nội dung.

Các test trên kiểm tra bốn hợp đồng quan trọng:

- Không truyền name và language thì dùng mặc định.
- Có thể truyền đối số chứa dấu cách cùng option dài.
- Có thể dùng option ngắn và cờ boolean.
- Trợ giúp chi tiết hiển thị command cùng các option.

Nếu muốn kiểm tra lỗi validation, có thể gửi input không hợp lệ rồi xác nhận shell hiển thị diagnostic tương ứng. Hãy tránh phụ thuộc vào toàn bộ câu chữ hoặc stack trace nếu chúng không phải hợp đồng công khai.

## 12. Đọc kết quả test và sửa lỗi thường gặp

### Command không xuất hiện trong help

Kiểm tra:

- Lớp chứa command có @Component hoặc được đăng ký thành bean không.
- Package của command có nằm trong phạm vi component scan không.
- Method có annotation @Command không.
- Ứng dụng có đang chạy đúng Spring context không.

### Tên command khác với dự kiến

Kiểm tra thuộc tính name trong @Command. Nếu bỏ name, Spring Shell có thể lấy tên method làm tên command. Với CLI có hợp đồng công khai, khai báo name rõ ràng giúp tránh thay đổi ngoài ý muốn khi đổi tên method Java.

### Đối số name không nhận cả họ tên

Đặt toàn bộ giá trị có khoảng trắng trong dấu nháy đơn hoặc kép:

~~~text
greet "Nguyễn An"
~~~

### Option không nhận dạng

Kiểm tra longName và shortName trong @Option. Tên dài được gọi bằng hai dấu gạch ngang; tên ngắn dùng một dấu gạch ngang và một ký tự.

### Option boolean luôn false

Kiểm tra giá trị mặc định và cách gọi cờ. Với ví dụ này, dùng --uppercase hoặc -u để bật. Nếu truyền giá trị tường minh, dùng true hoặc false.

### Help thiếu phần giải thích

Kiểm tra description và help của @Command, description của từng @Argument/@Option. Mô tả ngắn và hướng dẫn dài có vai trò khác nhau; không nên để trống tất cả rồi kỳ vọng help tự suy ra ý nghĩa nghiệp vụ.

### Test không tìm thấy ShellTestClient

Kiểm tra hai dependency spring-shell-test và spring-shell-test-autoconfigure đã có trong test scope và cùng phiên bản với Spring Shell starter. Kiểm tra import package org.springframework.shell.test và org.springframework.shell.test.autoconfigure.

## 13. Mở rộng bài thực hành

Sau khi command cơ bản hoạt động, hãy thử các thay đổi sau:

**Bài tập A — Thêm ngôn ngữ mới**

Thêm ngôn ngữ ja với lời chào tiếng Nhật. Cập nhật validation, mô tả option và help để phản ánh tập giá trị mới. Viết test cho giá trị ja.

**Bài tập B — Thêm option tên dài**

Thêm option --title để thêm danh xưng trước tên người được chào. Ví dụ:

~~~text
greet An --title "chị"
~~~

Kết quả có thể là:

~~~text
Xin chào, chị An!
~~~

Xác định rõ title có giá trị mặc định hay không và cập nhật phần help.

**Bài tập C — Thêm option đảo ngược**

Thêm --lowercase để chuyển output thành chữ thường. Xác định hành vi khi người dùng truyền cả --uppercase và --lowercase. Có thể từ chối tổ hợp xung đột bằng validation hoặc định nghĩa một quy tắc ưu tiên rõ ràng.

**Bài tập D — Chào nhiều người**

Tạo command greet-many nhận một tập đối số tên bằng @Arguments. Dùng String.join để tạo lời chào cho nhiều người. Đọc tài liệu API của @Arguments để hiểu cách thu thập phần còn lại của command line và thuộc tính arity.

**Bài tập E — Làm help thân thiện hơn**

Viết lại help để có ví dụ cho:

- Lời chào mặc định.
- Lời chào bằng tiếng Anh.
- Tên chứa khoảng trắng.
- Chế độ chữ hoa.

Sau đó kiểm tra help greet trong test.

## 14. Nguyên tắc thiết kế command dễ dùng

Một command tốt nên:

- Có tên ngắn, rõ nghĩa và ổn định.
- Dùng argument cho dữ liệu vị trí chính, option cho cấu hình bổ sung.
- Đặt defaultValue có chủ đích và mô tả mặc định trong help.
- Có short option dễ nhớ nhưng tránh trùng lặp trong cùng command.
- Nêu rõ giá trị hợp lệ trong description.
- Báo lỗi validation gần với ngôn ngữ người dùng.
- Không bắt người dùng đoán thứ tự tham số nếu có thể dùng option có tên.
- Cung cấp ví dụ có thể sao chép.
- Được kiểm thử cả hành vi thành công và input sai.

Không nên thêm option chỉ vì framework hỗ trợ. Mỗi option mới làm tăng số cách kết hợp mà người dùng phải hiểu và đội phát triển phải duy trì.

## 15. Checklist hoàn thành

- [ ] Project có Spring Boot và spring-shell-starter tương thích.
- [ ] Lớp khởi động có @SpringBootApplication.
- [ ] Lớp command được đăng ký thành Spring bean.
- [ ] Command có tên greet rõ ràng.
- [ ] Command có description, group và help.
- [ ] Tên người được chào là đối số vị trí có mô tả và mặc định.
- [ ] language là option có tên dài, tên ngắn, mô tả và mặc định.
- [ ] uppercase là option boolean có mặc định false.
- [ ] Tên rỗng bị từ chối.
- [ ] Chỉ vi và en được chấp nhận.
- [ ] Tên có dấu cách được truyền trong dấu nháy.
- [ ] help liệt kê command.
- [ ] help greet hiển thị hướng dẫn và tham số.
- [ ] Test xác minh mặc định, option dài, option ngắn và help.
- [ ] Ứng dụng chạy được từ Maven hoặc JAR đã đóng gói.

## 16. Tự kiểm tra

**Câu 1.** Annotation nào đánh dấu một method thành command của Spring Shell 4.x?

**Gợi ý trả lời:** @Command. Method phải thuộc một bean Spring được phát hiện trong application context.

**Câu 2.** Khác biệt giữa @Argument và @Option là gì?

**Gợi ý trả lời:** @Argument nhận giá trị theo vị trí; @Option nhận giá trị theo tên dài hoặc tên ngắn.

**Câu 3.** index của @Argument bắt đầu từ số nào?

**Gợi ý trả lời:** Bắt đầu từ 0.

**Câu 4.** Trong ví dụ, vì sao greet không cần truyền tên?

**Gợi ý trả lời:** Đối số name có defaultValue là bạn, nên Spring Shell cung cấp giá trị mặc định khi người dùng bỏ qua đối số.

**Câu 5.** Làm thế nào bật option boolean uppercase?

**Gợi ý trả lời:** Gõ --uppercase hoặc -u. Có thể truyền tường minh --uppercase=true.

**Câu 6.** Dùng command nào để xem hướng dẫn chi tiết của greet?

**Gợi ý trả lời:** help greet.

**Câu 7.** Vì sao phải đặt Nguyễn An trong dấu nháy?

**Gợi ý trả lời:** Parser tách input theo khoảng trắng. Dấu nháy làm cả cụm có khoảng trắng trở thành một đối số.

**Câu 8.** Spring Shell test client nào dùng để gửi command trong test?

**Gợi ý trả lời:** ShellTestClient; sendCommand() nhận chuỗi command và trả về ShellScreen để kiểm tra bằng ShellAssertions.

## Kết luận

Bài thực hành đã xây dựng một CLI chào hỏi hoàn chỉnh bằng Spring Shell 4.x. Command greet nhận tên bằng @Argument, nhận ngôn ngữ và chế độ chữ hoa bằng @Option, kiểm tra dữ liệu trước khi tạo kết quả và trả String để shell hiển thị.

Trợ giúp được tạo từ mô tả command, mô tả tham số và ví dụ trong thuộc tính help. Người dùng có thể dùng help để xem danh sách lệnh và help greet để đọc cách gọi cụ thể. Cuối cùng, ShellTestClient xác nhận các đường chạy mặc định, option dài, option ngắn và phần help. Đây là nền tảng để mở rộng CLI sang nhiều command mà vẫn giữ cú pháp nhất quán và dễ tự khám phá.

## Tài liệu tham khảo

- [Spring Shell 4.0.3 — Command Registration](https://docs.spring.io/spring-shell/reference/commands/registration.html)
- [Spring Shell 4.0.3 — Command Syntax](https://docs.spring.io/spring-shell/reference/commands/syntax.html)
- [Spring Shell 4.0.3 — Option Validation](https://docs.spring.io/spring-shell/reference/commands/validation.html)
- [Spring Shell 4.0.3 — Option Help](https://docs.spring.io/spring-shell/reference/commands/help.html)
- [Spring Shell 4.0.3 — Testing](https://docs.spring.io/spring-shell/reference/testing.html)
- [Spring Shell 4.0.3 — Command annotation API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/annotation/Command.html)
- [Spring Shell 4.0.3 — Argument annotation API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/annotation/Argument.html)
- [Spring Shell 4.0.3 — Option annotation API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/annotation/Option.html)
