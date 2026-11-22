# Phân biệt biến của tiến trình, tùy chọn IDE và tệp .env không tự được Boot nạp

## 1. Vấn đề cần hiểu

Khi học **Spring Boot Externalized Configuration**, người học thường gặp ba thao tác trông có vẻ giống nhau:

1. Đặt một biến môi trường trong terminal rồi chạy `java -jar app.jar`.
2. Nhập biến môi trường ở phần **Run/Debug Configuration** của IDE.
3. Tạo tệp `.env` trong thư mục dự án, ví dụ ghi `DEMO_MESSAGE=hello`.

Cả ba đều có thể xuất hiện trong quy trình phát triển, nhưng **không phải ba cách tương đương về mặt cơ chế**.

- **Biến môi trường của tiến trình (process environment variable)** là một cặp tên–giá trị thực sự được hệ điều hành/công cụ khởi chạy cung cấp cho tiến trình Java.
- **Tùy chọn IDE** là cấu hình mà IDE sử dụng **khi tạo tiến trình chạy hoặc debug**. Một ô nhập “Environment variables” có thể khiến IDE truyền biến vào tiến trình Java; còn “VM options” và “Program arguments” là những kênh khác.
- **Tệp `.env`** chỉ là một tệp văn bản theo quy ước được nhiều công cụ hỗ trợ. **Spring Boot không mặc định quét và tự nạp tệp `.env` thành biến môi trường của tiến trình.**

Điểm mấu chốt là: **Spring Boot đọc những nguồn cấu hình thực sự được cung cấp cho ứng dụng, không suy ra biến môi trường chỉ vì tồn tại một tệp tên `.env`.**

Xét dự án:

```text
my-app/
├── .env
├── build.gradle
└── src/main/resources/application.yml
```

Tệp `.env`:

```dotenv
DEMO_MESSAGE=Hello from .env
SPRING_PROFILES_ACTIVE=dev
```

Nếu chỉ tạo tệp như vậy rồi chạy:

```bash
java -jar build/libs/my-app.jar
```

thì **không thể kết luận** Spring Boot sẽ nhận `DEMO_MESSAGE` và profile `dev` từ tệp đó. Một công cụ khác phải đọc `.env` và truyền giá trị cho tiến trình Java, hoặc ứng dụng phải được cấu hình để nạp dữ liệu qua cơ chế được hỗ trợ.

## 2. Biến môi trường thực sự thuộc tiến trình nào?

### 2.1. Process environment là gì?

Một tiến trình có **môi trường thực thi** riêng, trong đó có tập biến môi trường do tiến trình cha/công cụ khởi chạy truyền xuống khi tạo tiến trình con.

Ví dụ sơ đồ:

```text
Terminal / shell
    |
    | export DEMO_MESSAGE="Hello"
    |
    +--> java -jar app.jar
              |
              +--> tiến trình JVM nhận DEMO_MESSAGE=Hello
                        |
                        +--> System.getenv("DEMO_MESSAGE")
                        |
                        +--> Spring Environment
                                 |
                                 +--> demo.message
```

Trong một chương trình Java bình thường, bạn có thể đọc trực tiếp:

```java
String value = System.getenv("DEMO_MESSAGE");
System.out.println(value);
```

Nếu tiến trình Java có biến này, `System.getenv("DEMO_MESSAGE")` trả về giá trị tương ứng. Nếu không có, kết quả là `null`.

Spring Boot thường đưa các biến môi trường của hệ điều hành vào hệ thống `Environment` để các thuộc tính có thể được truy cập qua khóa cấu hình kiểu Spring, chẳng hạn `demo.message`.

### 2.2. Biến của shell chưa chắc là biến xuất sang tiến trình con

Trên Bash hoặc shell tương thích POSIX, hai thao tác sau **khác nhau**:

```bash
# Chỉ tạo một biến trong shell hiện tại
DEMO_MESSAGE="Hello"

# In biến của shell
echo "$DEMO_MESSAGE"
```

Lệnh `echo` có thể in `Hello`, nhưng điều đó **chưa chứng minh** biến được truyền cho chương trình Java chạy sau đó. Muốn xuất biến sang tiến trình con, cần `export`:

```bash
export DEMO_MESSAGE="Hello"
java -jar app.jar
```

Hoặc đặt biến chỉ cho một lệnh:

```bash
DEMO_MESSAGE="Hello" java -jar app.jar
```

Cách thứ hai thuận tiện khi muốn thử nghiệm mà không để biến tồn tại trong môi trường của shell cho các lệnh tiếp theo.

Bạn có thể xem biến đã xuất trong terminal hiện tại:

```bash
printenv DEMO_MESSAGE
```

Nếu chỉ gõ `DEMO_MESSAGE=Hello` mà chưa `export`, `printenv` có thể không thấy giá trị, dù `echo "$DEMO_MESSAGE"` vẫn thấy.

### 2.3. Các terminal không tự chia sẻ mọi thay đổi

Giả sử mở hai terminal A và B:

- Ở A: `export DEMO_MESSAGE=A`.
- Ở B: chạy `java -jar app.jar`.

Không thể mặc định ứng dụng khởi chạy từ B nhận giá trị `A`. Mỗi shell là một tiến trình với môi trường của riêng nó; thay đổi ở một shell đang chạy không tự truyền ngược sang shell khác đã tồn tại.

Tương tự, đổi biến ở terminal **sau khi JVM đã khởi động** không tự làm thay đổi môi trường của JVM đang chạy. Với cấu hình Spring Boot thông thường, bạn cần khởi động lại ứng dụng sau khi đổi biến đầu vào.

Đây là nguồn gốc của lỗi “tôi đã export rồi nhưng ứng dụng vẫn không nhận”: cần kiểm tra **terminal hoặc công cụ nào thực sự tạo tiến trình Java**.

## 3. Spring Boot ánh xạ biến môi trường thành thuộc tính như thế nào?

Một điểm hay gây nhầm lẫn là tên biến môi trường và tên thuộc tính Spring có thể có cách viết khác nhau.

Ví dụ:

| Biến môi trường được cấp cho JVM | Thuộc tính Spring Boot thường nhận |
| --- | --- |
| `SERVER_PORT` | `server.port` |
| `SPRING_PROFILES_ACTIVE` | `spring.profiles.active` |
| `SPRING_DATASOURCE_URL` | `spring.datasource.url` |
| `DEMO_MESSAGE` | `demo.message` |
| `MANAGEMENT_ENDPOINTS_WEB_EXPOSURE_INCLUDE` | `management.endpoints.web.exposure.include` |

Spring Boot hỗ trợ **relaxed binding** cho nhiều cách biểu diễn khóa. Với các thuộc tính cấu hình theo tên chuẩn, quy tắc chuyển sang biến môi trường thường là:

1. Thay dấu chấm `.` bằng dấu gạch dưới `_`.
2. Bỏ dấu gạch ngang `-` trong tên thuộc tính.
3. Đổi chữ thành chữ hoa.

Ví dụ `spring.main.log-startup-info` tương ứng với dạng biến môi trường `SPRING_MAIN_LOGSTARTUPINFO` theo quy tắc đặt tên chuẩn đó. Vì vậy không nên tự chèn dấu gạch dưới tùy ý vào giữa mọi từ rồi giả định trình liên kết của Spring Boot sẽ hiểu đúng từng thuộc tính.

Trong bài này, ta dùng thuộc tính đơn giản `demo.message`, có ánh xạ dễ quan sát là `DEMO_MESSAGE`.

**Lưu ý:** tên biến môi trường có thể phân biệt chữ hoa/chữ thường tùy hệ điều hành, còn cách ánh xạ tên thuộc tính phụ thuộc cơ chế Spring `Environment` và binder. Dùng tên chuẩn theo tài liệu của Spring Boot giúp tránh bất ngờ khi chuyển giữa Windows và Linux.

## 4. Một ví dụ Spring Boot chạy được

Giả sử ta cần hiển thị lời chào cấu hình từ bên ngoài ứng dụng.

### 4.1. Tệp application.yml

Tạo `src/main/resources/application.yml`:

```yaml
demo:
  message: "Lời chào mặc định trong YAML"
  retries: 2
```

Ở đây `demo.message` và `demo.retries` là hai thuộc tính minh họa.

### 4.2. Thành phần Java kiểm tra nguồn giá trị

Trong một ứng dụng đã có `@SpringBootApplication`, thêm:

```java
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class EnvironmentPrinter implements ApplicationRunner {

    private final Environment environment;

    public EnvironmentPrinter(Environment environment) {
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        String rawEnvironmentValue = System.getenv("DEMO_MESSAGE");
        String springValue = environment.getProperty("demo.message");

        System.out.println("OS DEMO_MESSAGE = " + rawEnvironmentValue);
        System.out.println("Spring demo.message = " + springValue);
        System.out.println("Spring demo.retries = "
                + environment.getProperty("demo.retries", Integer.class));
    }
}
```

Điểm quan sát:

- `System.getenv("DEMO_MESSAGE")` trả lời: **JVM này có nhận biến môi trường mang tên chính xác `DEMO_MESSAGE` không?**
- `environment.getProperty("demo.message")` trả lời: **Spring đang chọn giá trị nào cho thuộc tính `demo.message` sau khi xét các nguồn cấu hình?**
- Hai kết quả có thể khác nhau nếu một nguồn Spring có ưu tiên cao hơn đã ghi đè, hoặc nếu tên biến môi trường không tồn tại nhưng YAML cung cấp giá trị.

### 4.3. Trường hợp A: không cấp biến môi trường

Chạy:

```bash
java -jar app.jar
```

Giả sử không có `DEMO_MESSAGE` trong môi trường JVM và không có nguồn ghi đè khác:

```text
OS DEMO_MESSAGE = null
Spring demo.message = Lời chào mặc định trong YAML
Spring demo.retries = 2
```

Spring vẫn đọc được giá trị từ tệp cấu hình, dù không có biến môi trường.

### 4.4. Trường hợp B: cấp biến qua shell

Bash:

```bash
DEMO_MESSAGE="Lời chào từ terminal" java -jar app.jar
```

Kết quả dự kiến:

```text
OS DEMO_MESSAGE = Lời chào từ terminal
Spring demo.message = Lời chào từ terminal
Spring demo.retries = 2
```

Giá trị môi trường ghi đè cùng khóa trong `application.yml` khi không có nguồn ưu tiên cao hơn.

### 4.5. Trường hợp C: có thêm đối số dòng lệnh

```bash
DEMO_MESSAGE="Từ môi trường" java -jar app.jar --demo.message="Từ dòng lệnh"
```

Hai phép đọc có thể cho:

```text
OS DEMO_MESSAGE = Từ môi trường
Spring demo.message = Từ dòng lệnh
Spring demo.retries = 2
```

Không có mâu thuẫn: `System.getenv` chỉ đọc biến môi trường, trong khi Spring `Environment` xét nhiều nguồn. Trong cấu hình Spring Boot thông thường, đối số `--demo.message=...` có ưu tiên cao hơn biến môi trường.

Từ đây có thể phân biệt được **biến có được truyền đến JVM hay không** và **giá trị nào đang có hiệu lực trong ứng dụng Spring**.

## 5. Tùy chọn Run/Debug của IDE không phải tệp .env

Khi bấm nút **Run** hoặc **Debug** trong IDE như IntelliJ IDEA, Eclipse hoặc VS Code, IDE hay tiện ích Java thường là công cụ tạo tiến trình chạy ứng dụng. Giá trị mà Java nhận phụ thuộc vào **cấu hình lần chạy đó**.

Thường có ba nhóm tùy chọn quan trọng.

| Mục cấu hình của lần chạy | Ví dụ nhập | Java/Spring tiếp nhận qua |
| --- | --- | --- |
| Environment variables | `DEMO_MESSAGE=from-ide` | Môi trường tiến trình, `System.getenv("DEMO_MESSAGE")` |
| VM options / JVM arguments | `-Ddemo.message=from-jvm` | Java system property, `System.getProperty("demo.message")` |
| Program arguments / Application arguments | `--demo.message=from-cli` | Đối số ứng dụng, Spring Boot command-line properties |

Tên nhãn cụ thể thay đổi theo IDE và kiểu cấu hình Run/Debug. Tuy nhiên, **bản chất ba kênh là khác nhau**.

### 5.1. Environment variables trong IDE

Nếu thêm biến:

```text
DEMO_MESSAGE=Hello from IDE
```

vào vùng **Environment variables** của cấu hình chạy ứng dụng, IDE sẽ có thể truyền biến đó vào tiến trình Java mới được tạo. Khi ấy:

```java
System.getenv("DEMO_MESSAGE")
```

có thể trả về `Hello from IDE`, và Spring có thể liên kết nó với `demo.message`.

Đó vẫn là một **biến môi trường thật của tiến trình Java**. Sự khác nhau là **IDE cấp giá trị thay cho terminal**.

### 5.2. VM options trong IDE

Nếu nhập:

```text
-Ddemo.message=HelloFromJvm
```

vào **VM options**, đây là một **thuộc tính hệ thống Java**, không phải biến môi trường mang tên `DEMO_MESSAGE`.

Do đó:

```java
System.getProperty("demo.message")
```

có thể có giá trị `HelloFromJvm`, nhưng:

```java
System.getenv("DEMO_MESSAGE")
```

không tự nhiên có giá trị chỉ vì tùy chọn `-D` này được thiết lập.

Spring Boot thường đọc được `demo.message` từ thuộc tính hệ thống Java, vì Java system properties cũng là một nguồn cấu hình được hỗ trợ.

### 5.3. Program arguments trong IDE

Nếu nhập:

```text
--demo.message=HelloFromArguments
```

vào **Program arguments**, IDE sẽ truyền chuỗi đó vào danh sách đối số ứng dụng. Spring Boot mặc định hỗ trợ cú pháp đối số thuộc tính bắt đầu bằng `--`.

Đây cũng **không phải** biến môi trường của JVM. Mã `System.getenv("DEMO_MESSAGE")` sẽ không phản ánh giá trị này, còn Spring `Environment` có thể đọc `demo.message=HelloFromArguments`.

### 5.4. Trình chạy IDE có môi trường riêng

Một lỗi khó nhận ra:

1. Mở IDE từ màn hình desktop.
2. Sau đó mở một terminal khác và chạy `export DEMO_MESSAGE=updated`.
3. Bấm **Run** trong IDE.
4. Thấy ứng dụng không nhận `updated`.

Lý do: việc `export` trong terminal **không thay đổi môi trường của tiến trình IDE đã mở trước đó**. Nếu muốn đảm bảo giá trị, hãy điền vào Run/Debug Configuration, hoặc khởi chạy IDE bằng một môi trường đã được thiết lập phù hợp.

Một số IDE có thể cung cấp chức năng nạp tệp môi trường, plugin hỗ trợ `.env` hoặc cấu hình `envFile`. Đó là **tính năng của IDE/extension/công cụ chạy**, không phải bằng chứng Spring Boot có cơ chế tự quét `.env`.

## 6. Tệp .env thực chất là gì?

Một tệp `.env` thường là tệp văn bản chứa các dòng tên–giá trị:

```dotenv
DEMO_MESSAGE=Hello from dotenv
DEMO_RETRIES=5
SPRING_PROFILES_ACTIVE=dev
```

Nó có thể được dùng bởi Docker, Docker Compose, công cụ quản lý tác vụ, framework khác hoặc thư viện đọc dotenv. Nhưng về bản chất, khi vừa tạo tệp, hệ điều hành **chưa biến các dòng bên trong thành biến môi trường của một tiến trình bất kỳ**.

Hãy phân biệt ba bước:

```text
1. Có tệp .env trên đĩa
           |
           | chưa chắc có tác dụng
           v
2. Một công cụ đọc .env và đưa dữ liệu vào process environment
           |
           | JVM được tạo với các biến đã truyền
           v
3. Spring Boot đọc biến môi trường từ JVM/Environment
```

Nếu **bước 2 không xảy ra**, Spring Boot không thể suy ra giá trị chỉ từ việc tệp tồn tại.

Ví dụ thư mục:

```text
my-app/
├── .env
├── pom.xml
└── src/main/resources/
    └── application.yml
```

Tệp `.env`:

```dotenv
DEMO_MESSAGE=From dotenv
```

Tệp `application.yml`:

```yaml
demo:
  message: "From YAML"
```

Nếu chạy ứng dụng Java trực tiếp mà không có công cụ nào đọc `.env` và không có biến `DEMO_MESSAGE` trong môi trường JVM, Spring sẽ dùng `From YAML` theo ví dụ này.

Đặt `.env` trong thư mục gốc dự án, trong `src/main/resources` hoặc cạnh JAR **không tự biến nó thành một tệp cấu hình được Spring Boot nạp mặc định**.

## 7. Cách dùng dữ liệu trong .env mà Spring Boot thực sự nhìn thấy

Muốn sử dụng giá trị trong `.env`, cần lựa chọn một cơ chế rõ ràng. Có nhiều cách, và mỗi cách có phạm vi khác nhau.

### 7.1. Cách đơn giản nhất: truyền biến trực tiếp khi khởi chạy

Bash:

```bash
DEMO_MESSAGE="From process environment" java -jar app.jar
```

Hoặc:

```bash
export DEMO_MESSAGE="From process environment"
java -jar app.jar
```

Ở đây không cần tệp `.env`. Spring Boot đọc biến mà tiến trình JVM nhận.

### 7.2. Dùng công cụ chạy hỗ trợ env file

Một số IDE hoặc công cụ task runner cho phép chỉ định đường dẫn đến `.env`. Công cụ đó có trách nhiệm:

1. Đọc tệp.
2. Phân tích nội dung theo cú pháp của công cụ.
3. Đặt các biến thích hợp khi tạo tiến trình Java.

Khi ấy Spring Boot nhận biến theo cơ chế chuẩn. Nếu đổi sang lệnh `java -jar` trực tiếp không qua công cụ, các giá trị có thể biến mất vì bước nạp file không còn diễn ra.

Vì vậy trong hướng dẫn dự án, hãy nói rõ **công cụ nào chịu trách nhiệm đọc tệp `.env`** và cấu hình nào kích hoạt tính năng đó.

### 7.3. Dùng Docker với --env-file

Ví dụ tệp `.env`:

```dotenv
DEMO_MESSAGE=Hello from Docker
SPRING_PROFILES_ACTIVE=prod
```

Chạy một container có ứng dụng Java:

```bash
docker run --rm --env-file .env my-spring-app:local
```

Lựa chọn `--env-file` là tính năng của **Docker CLI**: Docker đọc tệp và truyền các biến phù hợp vào môi trường container. Spring Boot chỉ nhìn thấy những gì đã được cấp cho tiến trình JVM **bên trong container**.

Lệnh trên giả định image `my-spring-app:local` có sẵn và được cấu hình chạy ứng dụng.

**Cảnh báo cú pháp:** tệp biến dùng cho Docker CLI không nhất thiết chấp nhận mọi quy tắc trích dẫn hoặc nội suy của Bash, Docker Compose hay thư viện dotenv. Cần soạn đúng định dạng của công cụ đọc tệp.

### 7.4. Dùng một tệp cấu hình Spring Boot thực thụ

Nếu nhu cầu là **nạp tệp cấu hình ứng dụng**, một lựa chọn trực tiếp là dùng `application-local.properties` hoặc `application-local.yml` theo Config Data:

```properties
# config/application-local.properties
demo.message=Hello from local properties
demo.retries=4
```

Chẳng hạn, sau khi bố trí tệp trong vị trí cấu hình thích hợp và bật profile `local`:

```bash
java -jar app.jar --spring.profiles.active=local
```

Đây là **cấu hình Spring Boot theo profile**, khác với việc tạo `.env`. Nó có quy tắc chọn tệp, vị trí và ưu tiên riêng trong Config Data.

Một cách khác là chỉ định tài nguyên Properties/YAML thông qua `spring.config.import` hoặc `spring.config.additional-location` khi phù hợp. Tuy nhiên, không nên ngầm đồng nhất cú pháp dotenv với YAML hay Properties trong mọi tình huống: các công cụ có thể có quy tắc đọc khác nhau.

## 8. Cẩn thận khi dùng source cho tệp .env trên Bash

Bạn có thể gặp mẹo:

```bash
set -a
. ./.env
set +a
java -jar app.jar
```

Cơ chế:

- `. ./.env` bảo shell đọc và thực thi nội dung file như **mã shell**.
- `set -a` khiến các biến gán trong giai đoạn đó được tự động đánh dấu để xuất sang tiến trình con.
- `set +a` khôi phục hành vi gán biến thông thường của shell.

Điều này **chỉ phù hợp khi tệp có cú pháp shell hợp lệ và đáng tin cậy**. Tệp theo định dạng dotenv của các công cụ khác có thể chứa các quy tắc nháy, khoảng trắng, nội suy hoặc comment không hoàn toàn tương thích Bash.

Đặc biệt, lệnh `source` hoặc `.` **thực thi nội dung tệp**, vì vậy tuyệt đối không sử dụng nó với tệp không tin cậy chỉ để đọc vài biến. Trong hệ thống thật, nên ưu tiên cấu hình môi trường trực tiếp, một công cụ đọc env file có cú pháp được định nghĩa rõ, hoặc dịch vụ quản lý secret phù hợp.

Đừng viết script nạp `.env` bằng cách cắt chuỗi theo dấu `=` đầu tiên mà không xét ký tự đặc biệt, dấu nháy, khoảng trắng hoặc giá trị nhiều dòng; cách làm này thường hỏng ở những cấu hình không đơn giản.

## 9. Phân biệt tệp .env của Docker Compose và biến trong container

Docker Compose thường dùng một tệp `.env` cho **nội suy biến vào tệp Compose**. Nhưng việc Compose đọc `.env` ở phía công cụ **không có nghĩa tất cả biến trong đó tự xuất hiện trong tiến trình ứng dụng bên trong container**.

Ví dụ:

```dotenv
# .env
DEMO_MESSAGE=Value from dotenv
```

Và:

```yaml
# compose.yaml
services:
  app:
    image: my-spring-app:local
```

Trong cấu hình này không có khai báo nào yêu cầu cấp `DEMO_MESSAGE` cho container. Việc có tệp `.env` cạnh `compose.yaml` **chưa đủ** để kết luận ứng dụng nhận biến đó.

Muốn truyền vào container, có thể sử dụng `env_file`:

```yaml
services:
  app:
    image: my-spring-app:local
    env_file:
      - .env
```

Hoặc dùng `environment` và nội suy:

```yaml
services:
  app:
    image: my-spring-app:local
    environment:
      DEMO_MESSAGE: ${DEMO_MESSAGE}
```

Trong hai ví dụ này, Docker Compose có trách nhiệm cấp biến cho container theo cơ chế tương ứng. Spring Boot nhận biến của tiến trình Java và ánh xạ `DEMO_MESSAGE` sang `demo.message`.

Sự phân biệt quan trọng:

| Thành phần | Vai trò |
| --- | --- |
| Tệp `.env` cho Compose | Cung cấp dữ liệu đầu vào cho Compose, thường được dùng để nội suy |
| `env_file:` trong `compose.yaml` | Yêu cầu Compose đọc một tệp và thiết lập môi trường cho container |
| `environment:` trong `compose.yaml` | Đặt các biến cụ thể cho container |
| `Environment` trong Spring Boot | Đọc nguồn thuộc tính thực tế của ứng dụng Java trong container |

Nếu chạy cùng JAR bằng IDE hoặc terminal bên ngoài Docker, cấu hình `env_file` của Compose không có tác dụng đối với lần chạy ấy.

## 10. Quy tắc ưu tiên: có biến chưa chắc đó là giá trị cuối cùng

Spring Boot có nhiều nguồn thuộc tính cấu hình. Với các tình huống phổ biến, mức ưu tiên giữa một số nguồn là:

```text
Đối số ứng dụng --demo.message=...
       >
SPRING_APPLICATION_JSON (nếu cấp thuộc tính tương ứng)
       >
Java system property -Ddemo.message=...
       >
Biến môi trường DEMO_MESSAGE
       >
Config Data: application.yml / application.properties
```

Đây là sơ đồ rút gọn, không liệt kê tất cả nguồn đặc thù như cấu hình kiểm thử, servlet/JNDI, Devtools hay các nguồn do ứng dụng bổ sung.

Ví dụ:

```bash
DEMO_MESSAGE="env" java -Ddemo.message=jvm -jar app.jar --demo.message=cli
```

Trong ví dụ thông thường:

```text
System.getenv("DEMO_MESSAGE")      = env
System.getProperty("demo.message") = jvm
Spring Environment demo.message   = cli
```

Không có lỗi nào ở đây. Ba cơ chế truyền giá trị khác nhau đang cùng tồn tại; Spring chọn giá trị có ưu tiên cao nhất cho khóa `demo.message`.

Vì vậy khi một người nói “biến môi trường của tôi không chạy”, cần chia thành hai câu hỏi:

1. **Biến có thật sự vào JVM không?** Hãy kiểm tra `System.getenv("DEMO_MESSAGE")`.
2. **Nếu đã vào JVM, nguồn nào đang thắng trong Spring?** Hãy kiểm tra `Environment#getProperty("demo.message")` và các `PropertySource` liên quan.

Câu hỏi thứ nhất không thể giải thích chỉ bằng thứ tự ưu tiên. Câu hỏi thứ hai không thể giải thích chỉ bằng việc nhìn nội dung tệp `.env`.

## 11. Phân biệt terminal, IDE, Maven và Gradle

Một dự án Spring Boot có thể được chạy bằng nhiều lệnh, và mỗi lần chạy có tiến trình cha khác nhau.

| Cách khởi chạy | Ai tạo tiến trình Java? | Cần quan sát ở đâu? |
| --- | --- | --- |
| `java -jar app.jar` trong terminal | Shell/terminal | Môi trường shell đã xuất |
| Run/Debug từ IDE | IDE hoặc trình chạy của IDE | Environment variables trong Run Configuration |
| `mvn spring-boot:run` | Maven và Spring Boot Maven Plugin | Môi trường của tiến trình Maven và cấu hình plugin |
| `./gradlew bootRun` | Gradle và tác vụ `bootRun` | Môi trường nơi Gradle chạy và các tùy chỉnh của tác vụ |
| Docker container | Docker hoặc Compose | `--env`, `--env-file`, `environment`, `env_file` |
| CI/CD | Runner, job hoặc orchestration | Cấu hình biến/secret tại bước tạo tiến trình |

Maven/Gradle có thể khởi tạo hoặc quản lý tiến trình Java với cấu hình riêng. Trong các dự án có daemon, profile chạy hoặc task custom, không nên khẳng định mọi biến trong một terminal chắc chắn sẽ đến đúng tiến trình ứng dụng mà không kiểm tra quy trình khởi chạy.

Một cách thực tế là in tạm **một biến không nhạy cảm** bằng `System.getenv` ngay trong ứng dụng để xác nhận biến có tới JVM hay không. Cách này thường hữu ích hơn việc kiểm tra `printenv` trong một terminal không phải nơi tạo tiến trình Java.

Trong IDE, cũng nên kiểm tra đã chọn **đúng Run Configuration** hay chưa. Cùng một dự án có thể có nhiều cấu hình chạy, chẳng hạn `Application`, `Spring Boot`, một cấu hình JUnit và một tác vụ Gradle, mỗi cấu hình có bộ biến môi trường riêng.

## 12. Tình huống với IntelliJ IDEA

Giả sử ứng dụng đọc `demo.message` và bạn muốn gán:

```text
DEMO_MESSAGE=Hello from IntelliJ
```

Quy trình tổng quát:

1. Mở **Run → Edit Configurations**.
2. Chọn cấu hình ứng dụng Spring Boot thực sự dùng để chạy.
3. Tìm mục **Environment variables** và khai báo `DEMO_MESSAGE`.
4. Lưu cấu hình, chạy lại ứng dụng.
5. Kiểm tra `System.getenv("DEMO_MESSAGE")` và `environment.getProperty("demo.message")`.

Nếu chỉ đặt:

```text
-Ddemo.message=HelloFromJvm
```

trong **VM options** thì kết quả đến từ Java system property, không phải biến môi trường `DEMO_MESSAGE`.

Nếu chỉ đặt:

```text
--demo.message=HelloFromArgs
```

trong **Program arguments**, Spring nhận đối số ứng dụng, không phải biến môi trường.

Nếu dự án có plugin hoặc chức năng hỗ trợ đọc `.env`, cần kiểm tra plugin ấy có được bật cho **đúng cấu hình chạy** hay không. Không nên mặc định mọi bản cài đặt IDE đều có cùng tính năng hoặc tự đọc mọi tệp `.env` trong thư mục dự án.

## 13. Tình huống với VS Code và công cụ có envFile

Một số kiểu launch configuration của VS Code hoặc extension cho phép khai báo đường dẫn `envFile`. Chẳng hạn, một cấu hình chạy Java do extension hỗ trợ có thể dùng:

```json
{
  "type": "java",
  "name": "Run Spring Boot",
  "request": "launch",
  "mainClass": "com.example.demo.DemoApplication",
  "envFile": "${workspaceFolder}/.env"
}
```

Đây chỉ là **ví dụ cho một kiểu cấu hình launch có hỗ trợ `envFile`**, không phải cấu hình Java bất biến cho mọi extension và phiên bản.

Điều quan trọng nằm ở **trình chạy**:

- Trình chạy đọc tệp `.env`.
- Trình chạy cấp biến cho tiến trình Java.
- Spring Boot đọc biến môi trường đã nhận.

Nếu chuyển sang chạy JAR bằng `java -jar` trực tiếp mà không qua trình chạy đó, Boot không tự sử dụng cài đặt `envFile` của VS Code.

Vì vậy, khi hướng dẫn nhóm phát triển, nên ghi rõ IDE, extension và kiểu cấu hình chạy thay vì nói chung chung “Spring Boot có `envFile`”.

## 14. Một ví dụ cấu hình theo môi trường mà không cần .env

Để nhìn rõ sự khác nhau, ta có thể cấu hình một ứng dụng web qua biến môi trường thật.

Tệp `application.yml`:

```yaml
server:
  port: 8080

demo:
  message: "Default message"
```

Chạy với biến môi trường Bash:

```bash
SERVER_PORT=9090 DEMO_MESSAGE="Hello local" java -jar app.jar
```

Trong tình huống không có nguồn ưu tiên cao hơn ghi đè:

```text
server.port  = 9090
demo.message = Hello local
```

Không có tệp `.env` nào tham gia. Môi trường tiến trình đã cung cấp hai giá trị thay cho cấu hình trong YAML.

Tương tự với PowerShell:

```powershell
$env:SERVER_PORT = "9090"
$env:DEMO_MESSAGE = "Hello local"

java -jar app.jar

Remove-Item Env:SERVER_PORT
Remove-Item Env:DEMO_MESSAGE
```

Việc xóa biến cuối ví dụ nhằm tránh tác dụng phụ ở các lệnh chạy tiếp theo trong cùng phiên PowerShell.

Không nên dùng `setx` trên Windows để thử nhanh biến cho **tiến trình hiện tại**: `setx` ghi giá trị cho các phiên tương lai, không tự thay đổi môi trường của shell đang chạy theo cách `$env:...` trong PowerShell thực hiện.

## 15. Bí mật cấu hình và an toàn khi dùng env

Nhiều người chọn biến môi trường để truyền tên người dùng, mật khẩu hoặc token cho ứng dụng. Ví dụ Spring Boot có thể nhận:

```text
SPRING_DATASOURCE_URL
SPRING_DATASOURCE_USERNAME
SPRING_DATASOURCE_PASSWORD
```

Tuy nhiên, cần nhớ:

- **Biến môi trường không tự động là kho bí mật an toàn.** Chúng có thể bị lộ qua nhật ký, bản dump, giao diện quản lý tiến trình, thông tin chẩn đoán hoặc công cụ có quyền đọc môi trường.
- **Không commit `.env` chứa secret thực vào Git.** Dùng tệp `.env.example` chỉ chứa tên khóa và các giá trị mẫu không nhạy cảm nếu nhóm cần tài liệu thiết lập.
- **Không in mật khẩu/token để chẩn đoán.** Hãy thử với một khóa giả như `DEMO_MESSAGE` hoặc chỉ kiểm tra sự có mặt của secret, không in giá trị.
- Trong CI/CD hoặc hạ tầng production, ưu tiên cơ chế secret management phù hợp và cấp giá trị cho tiến trình khi khởi chạy.
- Biến đặt ở IDE hoặc terminal cục bộ không mặc nhiên được triển khai sang server hay container.

Cần phân biệt việc **không lưu secret trong tệp cấu hình được commit** với việc **secret đã được bảo vệ hoàn toàn**. Quản lý phân quyền, vòng đời secret, tránh lộ log và cách cấp cho ứng dụng vẫn rất quan trọng.

## 16. Cách chẩn đoán khi đặt .env nhưng ứng dụng không nhận

Nếu một nhóm báo: “Tôi đã thêm `DEMO_MESSAGE` vào `.env` mà Spring Boot vẫn lấy giá trị mặc định”, hãy xử lý theo thứ tự.

### Bước 1: xác định lệnh chạy thực tế

Ứng dụng được mở bằng:

- terminal `java -jar`;
- nút Run/Debug của IDE;
- Maven/Gradle;
- Docker/Docker Compose;
- runner hoặc môi trường triển khai khác?

Đừng giả định người dùng đang chạy qua công cụ đọc `.env` chỉ vì tệp tồn tại.

### Bước 2: xác định công cụ nào đã đọc .env

Hãy hỏi bằng chứng kỹ thuật: Run Configuration có `envFile` không? Docker có `--env-file` không? Compose có `env_file` hoặc `environment` không? Có script khởi động nào xuất biến không?

Nếu câu trả lời là không, rất có thể `.env` **chưa được chuyển thành môi trường của JVM**.

### Bước 3: kiểm tra trực tiếp trong tiến trình Java

Thêm mã tạm cho khóa không nhạy cảm:

```java
System.out.println("DEMO_MESSAGE present? "
        + (System.getenv("DEMO_MESSAGE") != null));
```

Nếu in `false`, JVM không có biến tên chính xác `DEMO_MESSAGE`. Hãy sửa kênh cấp biến thay vì cố thay đổi thứ tự ưu tiên của Spring Config Data.

### Bước 4: kiểm tra thuộc tính Spring

```java
System.out.println("demo.message = "
        + environment.getProperty("demo.message"));
```

Nếu `System.getenv` có biến nhưng `Environment` cho giá trị khác, có thể tồn tại một nguồn ưu tiên cao hơn, ví dụ đối số dòng lệnh.

### Bước 5: kiểm tra cấu hình run và khởi động lại

Xem đã đổi đúng Run Configuration, đúng container, đúng tiến trình và đúng tên biến chưa. Đảm bảo ứng dụng được **khởi động lại** sau khi thay đổi đầu vào.

### Bước 6: kiểm tra cách viết tên và giá trị

Với khóa `demo.message`, sử dụng tên chuẩn `DEMO_MESSAGE`. Kiểm tra khoảng trắng, nháy kép, dấu bằng, ký tự xuống dòng và khả năng công cụ đọc dotenv có quy tắc khác kỳ vọng.

### Bước 7: không nhầm “profile không hoạt động” với “biến bị bỏ qua”

Nếu `.env` chứa `SPRING_PROFILES_ACTIVE=prod` nhưng profile `prod` không xuất hiện, hãy xác nhận biến này có mặt trong môi trường JVM. Nếu không có, các tệp `application-prod.yml` hoặc tài liệu `on-profile: prod` cũng không được kích hoạt chỉ bởi sự tồn tại của tệp `.env`.

## 17. Bảng so sánh ba cách thiết lập

| Câu hỏi | Biến môi trường của tiến trình | Environment variables trong IDE | Tệp `.env` tự đứng một mình |
| --- | --- | --- | --- |
| Có được JVM nhận ngay khi khởi chạy? | Có, nếu được cấp đúng cho tiến trình | Có, nếu cấu hình Run/Debug truyền vào JVM | **Không tự động** |
| `System.getenv` có thể đọc? | Có | Có, nếu IDE thực sự cấp biến | Không, nếu chưa có công cụ nạp |
| Spring `Environment` có thể sử dụng? | Có, với khóa ánh xạ phù hợp | Có, khi JVM nhận biến | Chỉ khi dữ liệu đã được nạp qua một cơ chế thực tế |
| Có phụ thuộc công cụ khởi chạy? | Có: terminal/runner phải cấp biến | Có: phụ thuộc cấu hình IDE | Có: cần loader, script, Docker hoặc cấu hình rõ ràng |
| Có thể ghi đè `application.yml`? | Có, theo thứ tự ưu tiên nguồn | Có, nếu được cấp thành biến | Không chỉ vì file tồn tại |
| Cần khởi động lại để nhận biến mới? | Thông thường có | Thông thường có | Sau khi loader và môi trường đã cập nhật, thường cần chạy lại |

Bảng này tập trung vào **cơ chế**. Một lần chạy có thể kết hợp nhiều kênh, chẳng hạn IDE truyền biến môi trường đồng thời truyền thêm đối số `--demo.message=...`. Khi đó cần xét cả việc biến có tồn tại lẫn thứ tự ưu tiên của các nguồn Spring.

## 18. Bài tập thực hành

### Bài tập A: chỉ có .env

Cấu trúc:

```text
demo/
├── .env
└── src/main/resources/application.yml
```

Tệp `.env`:

```dotenv
DEMO_MESSAGE=from-dotenv
```

Tệp `application.yml`:

```yaml
demo:
  message: "from-yaml"
```

Chạy `java -jar app.jar` mà không có loader hoặc biến `DEMO_MESSAGE` trong môi trường.

**Câu hỏi:** giá trị `demo.message` là gì?

**Đáp án:** `from-yaml`. Sự tồn tại của `.env` chưa khiến Spring Boot mặc định nạp nó.

### Bài tập B: shell variable và exported variable

Trên Bash:

```bash
DEMO_MESSAGE=first
java -jar app.jar
```

Sau đó:

```bash
export DEMO_MESSAGE=second
java -jar app.jar
```

**Câu hỏi:** vì sao lần thứ nhất có thể không truyền `DEMO_MESSAGE` cho ứng dụng, còn lần thứ hai có?

**Đáp án:** gán biến trong shell chưa đồng nghĩa với việc xuất biến sang tiến trình con. `export` đánh dấu biến để truyền cho chương trình được tạo từ shell đó.

### Bài tập C: IDE có nhiều loại tham số

Trong Run Configuration có:

```text
Environment variables:
  DEMO_MESSAGE=env

VM options:
  -Ddemo.message=jvm

Program arguments:
  --demo.message=cli
```

Giả sử không có nguồn đặc biệt nào thay đổi thứ tự ưu tiên, hãy dự đoán:

| Cách đọc | Kết quả |
| --- | --- |
| `System.getenv("DEMO_MESSAGE")` | `env` |
| `System.getProperty("demo.message")` | `jvm` |
| `environment.getProperty("demo.message")` | `cli` |

**Giải thích:** kênh cấp dữ liệu khác nhau; Spring chọn đối số ứng dụng cho giá trị cuối vì độ ưu tiên cao hơn.

### Bài tập D: Docker Compose có .env nhưng thiếu khai báo truyền biến

Có:

```dotenv
# .env
DEMO_MESSAGE=compose-value
```

Và:

```yaml
services:
  app:
    image: my-spring-app:local
```

**Câu hỏi:** có thể chắc chắn rằng JVM trong container nhận `DEMO_MESSAGE=compose-value` không?

**Đáp án:** không. Nếu muốn đưa giá trị vào môi trường container, cần cấu hình phù hợp như `env_file:` hoặc `environment:`, hay một cơ chế cấp biến khác. Tệp `.env` dùng cho nội suy Compose không mặc nhiên cấp mọi biến cho container.

### Bài tập E: xác định lỗi trong một chuỗi thao tác

Một lập trình viên:

1. Mở IDE vào buổi sáng.
2. Chiều mở một terminal mới và chạy `export SPRING_PROFILES_ACTIVE=prod`.
3. Bấm Run trong IDE cũ.
4. Thấy ứng dụng vẫn chạy ở profile khác.

**Câu hỏi:** điều gì cần kiểm tra đầu tiên?

**Đáp án:** môi trường thực tế của tiến trình Java mà IDE tạo. Một biến được export ở terminal khác không tự cập nhật môi trường của IDE đã mở. Hãy đặt biến vào đúng Run Configuration, hoặc đảm bảo IDE được tạo với môi trường mong muốn.

## 19. Ghi nhớ

- **Process environment** là dữ liệu thật được cấp cho tiến trình JVM; `System.getenv` cho biết JVM có nhận biến cụ thể hay không.
- **Environment variables của IDE** có thể trở thành biến của JVM khi IDE khởi chạy ứng dụng. Chúng khác với **VM options** (Java system properties) và **Program arguments** (đối số ứng dụng).
- **Tệp `.env` không tự được Spring Boot nạp mặc định.** Một công cụ hoặc cơ chế rõ ràng phải đọc file và truyền các giá trị thích hợp, hoặc ứng dụng phải được cấu hình nạp tài nguyên qua một cơ chế được hỗ trợ.
- **Terminal, IDE, Docker và CI/CD không tự chia sẻ môi trường của mọi tiến trình.** Cần xác định chính xác ai tạo tiến trình Java và đã cấp những biến nào.
- **Giá trị có trong `System.getenv` chưa chắc là giá trị có hiệu lực của Spring**: `Environment` còn xét đối số dòng lệnh, system properties và các nguồn Config Data.
- Dùng `spring.profiles.active`, `spring.config.import` và cấu hình theo profile cho đúng mục đích; không coi việc đặt chúng trong `.env` là đủ nếu `.env` chưa được loader đọc.
- Với secret, tránh commit `.env` chứa dữ liệu thật, tránh in giá trị nhạy cảm và sử dụng công cụ cấp secret phù hợp cho môi trường triển khai.
