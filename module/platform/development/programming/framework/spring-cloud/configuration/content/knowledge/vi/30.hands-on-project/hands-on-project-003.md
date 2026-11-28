# Tạo xung đột giữa Git, biến môi trường và tham số dòng lệnh

Trong bài thực hành này, bạn dựng một Spring Cloud Config Server đọc cấu hình từ Git và một Config Client nhỏ. Cùng một property `lab.message` được khai báo trong Git, truyền qua biến môi trường của hệ điều hành và truyền qua tham số dòng lệnh. Bạn sẽ chạy ứng dụng nhiều lần để quan sát giá trị nào thắng, kiểm tra property source và giải thích vì sao kết quả thay đổi.

Mục tiêu là nắm được hai tầng ưu tiên:

1. **Bên trong Git repository:** file dùng chung, file theo application và file theo profile có thể cùng khai báo một key. Config Server hợp nhất chúng theo quy tắc application/profile.
2. **Bên trong Config Client:** khi dùng Spring Boot Config Data import, cấu hình từ Config Server được nạp như Config Data. Biến môi trường có độ ưu tiên cao hơn Config Data và tham số dòng lệnh có độ ưu tiên cao hơn biến môi trường.

Phần cuối có một biến thể legacy bootstrap. Biến thể này có quy tắc remote property source khác và cần cấu hình cho phép override từ chính Git repository.

## 1. Kết quả cần đạt

Sau khi hoàn thành, bạn có thể:

- Tạo một Git repository chứa cấu hình dùng chung, cấu hình riêng application và cấu hình profile.
- Cấu hình Config Server đọc Git branch `main`.
- Cấu hình Config Client tải đúng application, profile và label.
- Tạo xung đột có chủ đích giữa Git, environment variable và command-line argument.
- Dự đoán giá trị hiệu lực trước khi chạy ứng dụng.
- Xác minh giá trị và nguồn property bằng Spring Environment/Actuator.
- Giải thích sự khác nhau giữa Config Data import và legacy bootstrap.

## 2. Kiến trúc phòng thực hành

~~~mermaid
flowchart TD
    G[Git config repository] -->|branch main| CS[Spring Cloud Config Server :8888]
    CS -->|Environment: precedence-client / dev / main| CL[Config Client]
    ENV[OS environment: LAB_MESSAGE] --> CL
    CLI[Command line: --lab.message] --> CL
    CL --> B[LabProperties]
    B --> OUT[Giá trị lab.message hiệu lực]
~~~

Tổ chức workspace:

~~~text
config-precedence-lab/
├── config-repo/                 # Git repository chứa cấu hình
│   ├── application.yml
│   ├── application-dev.yml
│   ├── precedence-client.yml
│   └── precedence-client-dev.yml
├── config-server/               # Spring Boot + Config Server
└── precedence-client/           # Spring Boot + Config Client
~~~

Config Server đọc repository ở thư mục `config-repo`. Config Client yêu cầu cấu hình cho:

| Thành phần | Giá trị |
|---|---|
| Application | `precedence-client` |
| Active profile | `dev` |
| Git label | `main` |
| Property thử nghiệm | `lab.message` |

Bạn có thể dùng Maven hoặc Gradle. Các ví dụ dưới đây dùng Maven và Spring Boot 3 với Spring Cloud release train tương thích. Quản lý phiên bản bằng Spring Boot parent và Spring Cloud BOM của cùng một bộ tương thích; không tự chọn các phiên bản starter rời rạc.

## 3. Tạo Git configuration repository

Tạo thư mục `config-repo` và bốn file YAML. Các giá trị đều là dữ liệu giả, không phải secret.

`application.yml` — cấu hình dùng chung mặc định:

~~~yaml
lab:
  message: "git-shared-default"
  shared-note: "from application.yml"
~~~

`application-dev.yml` — cấu hình dùng chung cho profile dev:

~~~yaml
lab:
  message: "git-shared-dev"
  profile-note: "from application-dev.yml"
~~~

`precedence-client.yml` — cấu hình mặc định riêng cho ứng dụng:

~~~yaml
lab:
  message: "git-app-default"
  app-note: "from precedence-client.yml"
~~~

`precedence-client-dev.yml` — cấu hình riêng cho ứng dụng và profile dev:

~~~yaml
lab:
  message: "git-app-dev"
  timeout: 4s
  app-profile-note: "from precedence-client-dev.yml"
~~~

Bốn file cố ý khai báo cùng key `lab.message` với các giá trị khác nhau. Với application `precedence-client` và profile `dev`, file application/profile-specific có độ ưu tiên cao nhất trong nhóm Git trên. Vì vậy giá trị remote mong đợi là `git-app-dev`.

### 3.1. Khởi tạo Git repository

Mở terminal tại `config-repo`:

~~~powershell
git init -b main
git add .
git commit -m "Add configuration precedence lab"
git status
git log -1 --oneline
~~~

Nếu Git cũ chưa hỗ trợ `git init -b main`, dùng:

~~~powershell
git init
git branch -M main
git add .
git commit -m "Add configuration precedence lab"
~~~

Xác nhận branch hiện tại là `main` và working tree sạch. Config Server sẽ dùng branch này làm label.

## 4. Tạo Config Server

Tạo ứng dụng Spring Boot tên `config-server`, thêm dependency:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-config-server</artifactId>
</dependency>
~~~

Khai báo lớp khởi động:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.config.server.EnableConfigServer;

@SpringBootApplication
@EnableConfigServer
public class ConfigServerApplication {

    public static void main(String[] args) {
        SpringApplication.run(ConfigServerApplication.class, args);
    }
}
~~~

Trong `config-server/src/main/resources/application.yml`, khai báo:

~~~yaml
server:
  port: 8888

spring:
  application:
    name: config-server
  cloud:
    config:
      server:
        git:
          uri: "file:///C:/work/config-precedence-lab/config-repo"
          default-label: main
~~~

Thay `C:/work/config-precedence-lab/config-repo` bằng đường dẫn tuyệt đối tới Git repository trên máy của bạn. Với Windows, URI file có dạng `file:///C:/...`; với Linux/macOS, ví dụ `file:///home/your-user/config-precedence-lab/config-repo`. Đường dẫn có khoảng trắng cần được encode đúng theo URI.

Với URI có tiền tố `file:`, Config Server thao tác trực tiếp trên Git repository cục bộ và không clone repository. Vì vậy bài lab này không thực hành `clone-on-start` hoặc `refresh-rate` của remote Git backend. Hai thuộc tính đó áp dụng khi Config Server làm việc với Git repository từ xa: `clone-on-start` yêu cầu clone khi server khởi động, còn `refresh-rate` điều khiển chu kỳ fetch cập nhật từ remote. Nếu dùng Git remote thật, cần cấu hình credential và TLS phù hợp; không ghi password vào file YAML.

Khởi động Config Server:

~~~powershell
cd .\config-server
mvn spring-boot:run
~~~

Hoặc build rồi chạy JAR:

~~~powershell
mvn clean package
java -jar .\target\config-server-0.0.1-SNAPSHOT.jar
~~~

Lệnh JAR trên giả định `pom.xml` đặt `artifactId` là `config-server` và `version` là `0.0.1-SNAPSHOT`. Nếu project dùng tên hoặc version khác, thay bằng tên file JAR Maven tạo trong thư mục `target`.

Giữ terminal này chạy trong suốt bài thực hành.

### 4.1. Kiểm tra Environment từ Config Server

Mở terminal khác và gọi endpoint:

~~~powershell
curl.exe http://localhost:8888/precedence-client/dev/main
~~~

Response là Environment JSON. Kiểm tra các trường:

- `name` là `precedence-client`.
- `profiles` có profile `dev`.
- `label` là `main`.
- `propertySources` có các file `precedence-client-dev`, `application-dev`, `precedence-client` và `application`.
- Giá trị `lab.message` hiệu lực ở phía Config Server là `git-app-dev`.

Thứ tự và tên hiển thị chính xác của property source phụ thuộc backend và phiên bản. Với Git repository dạng file, quy tắc hợp nhất application/profile của Config Server đặt file riêng application theo profile ở mức cụ thể nhất. Endpoint này kiểm tra phần hợp nhất tại server; nó chưa tính environment variable hay command line của client.

## 5. Tạo Config Client

Tạo ứng dụng Spring Boot tên `precedence-client`. Thêm các dependency:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-config</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
</dependencies>
~~~

Trong `precedence-client/src/main/resources/application.yml`:

~~~yaml
spring:
  application:
    name: precedence-client
  profiles:
    active: dev
  config:
    import: "configserver:http://localhost:8888"
  cloud:
    config:
      label: main

management:
  endpoints:
    web:
      exposure:
        include: health,env
  endpoint:
    env:
      show-values: always
~~~

`spring.config.import` dùng Config Data API, cơ chế nạp cấu hình hiện đại của Spring Boot 2.4 trở lên. Với cách này, không cần `bootstrap.yml` hoặc `spring-cloud-starter-bootstrap`. Vì import không có tiền tố `optional:`, ứng dụng sẽ thất bại khi không thể kết nối Config Server — phù hợp với bài lab yêu cầu cấu hình tập trung phải có mặt. Biến thể legacy ở mục 13 là một cách khởi động riêng: phải bật bootstrap context tường minh và dùng `bootstrap.yml`; không cấu hình đồng thời cả hai cơ chế trong cùng lần chạy.

Phần Actuator `env` và `show-values: always` chỉ dùng trong môi trường local với dữ liệu không nhạy cảm để quan sát property source. Không đưa cấu hình hiển thị giá trị này vào production. Ở môi trường thật, giới hạn endpoint, yêu cầu xác thực và che giá trị nhạy cảm.

### 5.1. Tạo lớp cấu hình có kiểu

Tạo record:

~~~java
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "lab")
public record LabProperties(
        String message,
        Duration timeout,
        String sharedNote,
        String profileNote,
        String appNote,
        String appProfileNote) {
}
~~~

Đăng ký scan properties:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class PrecedenceClientApplication {

    public static void main(String[] args) {
        SpringApplication.run(PrecedenceClientApplication.class, args);
    }
}
~~~

### 5.2. In giá trị hiệu lực trong bài lab

Tạo runner để quan sát kết quả:

~~~java
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;

@Component
public class PrecedenceReport implements ApplicationRunner {

    private final LabProperties properties;

    public PrecedenceReport(LabProperties properties) {
        this.properties = properties;
    }

    @Override
    public void run(ApplicationArguments args) {
        System.out.println("lab.message = " + properties.message());
        System.out.println("lab.timeout = " + properties.timeout());
        System.out.println("lab.shared-note = " + properties.sharedNote());
        System.out.println("lab.profile-note = " + properties.profileNote());
        System.out.println("lab.app-note = " + properties.appNote());
        System.out.println("lab.app-profile-note = "
                + properties.appProfileNote());
    }
}
~~~

Runner chỉ in dữ liệu không nhạy cảm trong bài lab. Ứng dụng production không nên in toàn bộ cấu hình hoặc secret vào log.

Build client:

~~~powershell
cd .\precedence-client
mvn clean package
~~~

Các lệnh bên dưới giả định `pom.xml` đặt `artifactId` là `precedence-client` và `version` là `0.0.1-SNAPSHOT`, vì vậy JAR có tên `precedence-client-0.0.1-SNAPSHOT.jar`. Thay tên file nếu project dùng version khác.

Client có `spring-boot-starter-web`, vì vậy mỗi lệnh `java -jar` khởi động embedded server và giữ port `8080` cho đến khi process dừng. Khi chạy tuần tự các phần 6–13, giữ Config Server ở port `8888` hoạt động; mở terminal thứ hai để gọi Actuator nếu cần, sau đó quay lại terminal chạy client và nhấn **Ctrl+C** để dừng client. Chờ process kết thúc và port `8080` được giải phóng rồi mới chạy lệnh client tiếp theo. Không khởi động instance mới khi instance trước vẫn đang lắng nghe port này.

## 6. Chạy lần một: chỉ có cấu hình từ Git

Đảm bảo biến môi trường `LAB_MESSAGE` chưa được đặt và không truyền tham số `--lab.message`.

Trong PowerShell:

~~~powershell
Remove-Item Env:LAB_MESSAGE -ErrorAction SilentlyContinue
java -jar .\target\precedence-client-0.0.1-SNAPSHOT.jar
~~~

Kết quả mong đợi:

~~~text
lab.message = git-app-dev
lab.timeout = PT4S
lab.profile-note = from application-dev.yml
lab.app-note = from precedence-client.yml
lab.app-profile-note = from precedence-client-dev.yml
~~~

`lab.message` là `git-app-dev` vì Config Server đã hợp nhất các file Git theo application `precedence-client` và profile `dev`. Các property khác cho thấy ứng dụng nhận được dữ liệu từ nhiều context.

Nếu kết quả không phải `git-app-dev`, kiểm tra lần lượt:

1. Config Server có trỏ đúng thư mục repository không?
2. `git branch --show-current` có trả về `main` không?
3. Client có `spring.application.name=precedence-client` không?
4. Active profile có phải `dev` không?
5. `spring.cloud.config.label` có phải `main` không?
6. Endpoint `/precedence-client/dev/main` trên Config Server trả giá trị nào?

## 7. Chạy lần hai: Git xung đột với biến môi trường

Đặt biến môi trường cho process Java:

~~~powershell
$env:LAB_MESSAGE = "from-env"
java -jar .\target\precedence-client-0.0.1-SNAPSHOT.jar
~~~

Kết quả mong đợi:

~~~text
lab.message = from-env
~~~

Biến `LAB_MESSAGE` được Spring Boot relaxed binding ánh xạ tới property `lab.message`: chuyển tên thành chữ hoa và thay dấu chấm bằng dấu gạch dưới. Trong Config Data import hiện đại, environment variable có độ ưu tiên cao hơn các giá trị thuộc Config Data, bao gồm dữ liệu đã import từ Config Server.

Xóa biến môi trường sau lần chạy:

~~~powershell
Remove-Item Env:LAB_MESSAGE
~~~

Nếu không xóa, các lần chạy tiếp theo trong cùng terminal vẫn nhận `from-env`, khiến bạn tưởng rằng Git hoặc command line không hoạt động.

Trên Bash/zsh, cách chạy tương đương:

~~~bash
LAB_MESSAGE=from-env java -jar target/precedence-client-0.0.1-SNAPSHOT.jar
~~~

Cú pháp này chỉ đặt biến cho một process, nên không cần xóa sau khi chạy.

## 8. Chạy lần ba: Git và environment cùng xung đột với command line

Giữ environment variable và thêm tham số bắt đầu bằng hai dấu gạch ngang:

~~~powershell
$env:LAB_MESSAGE = "from-env"
java -jar .\target\precedence-client-0.0.1-SNAPSHOT.jar --lab.message=from-cli
~~~

Kết quả mong đợi:

~~~text
lab.message = from-cli
~~~

Command-line argument được Spring Boot đưa vào Environment dưới dạng property source có độ ưu tiên cao hơn environment variable và Config Data. Vì vậy, khi cả ba nguồn cùng khai báo `lab.message`, giá trị từ `--lab.message=from-cli` thắng.

Xóa environment variable:

~~~powershell
Remove-Item Env:LAB_MESSAGE
~~~

Trên Bash/zsh:

~~~bash
LAB_MESSAGE=from-env java -jar target/precedence-client-0.0.1-SNAPSHOT.jar --lab.message=from-cli
~~~

## 9. Ma trận kết quả

| Git Config Server | Environment | Command line | Giá trị hiệu lực |
|---|---|---|---|
| `git-app-dev` | Không có | Không có | `git-app-dev` |
| `git-app-dev` | `from-env` | Không có | `from-env` |
| `git-app-dev` | Không có | `from-cli` | `from-cli` |
| `git-app-dev` | `from-env` | `from-cli` | `from-cli` |

Với Config Data import, thứ tự liên quan trong bài lab là:

~~~text
Command-line arguments
        ↓
OS environment variables
        ↓
Imported Config Data (Config Server/Git)
~~~

Mũi tên hướng xuống biểu diễn độ ưu tiên giảm dần. Java system properties nằm giữa OS environment variables và command-line arguments trong thứ tự property source mặc định của Spring Boot.

Đây là kết quả cho Config Data import. Không áp dụng máy móc bảng này cho legacy bootstrap, vì remote property source trong bootstrap có quy tắc override riêng.

## 10. Xác minh property source bằng Actuator

Trong lúc client đang chạy, mở endpoint:

~~~powershell
curl.exe http://localhost:8080/actuator/env/lab.message
~~~

Response `env` cho biết giá trị hiệu lực và các property source chứa key đó. Kiểm tra tên nguồn tương ứng với:

- Config Server/Config Data khi không có override cục bộ.
- `systemEnvironment` khi `LAB_MESSAGE` thắng.
- `commandLineArgs` khi `--lab.message` thắng.

Tên hiển thị có thể có prefix hoặc wrapper tùy Spring Boot version. Điều cần xác nhận là nguồn có độ ưu tiên cao nhất chứa key đang cung cấp giá trị hiệu lực.

Nếu không muốn expose Actuator, có thể dùng debugger hoặc một diagnostic test đọc `Environment.getProperty("lab.message")`. Trong production, chỉ mở endpoint `env` trên management network có bảo vệ và không bật hiển thị plaintext cho secret.

## 11. Thử thay đổi giá trị trong Git

Thay `lab.message` trong `precedence-client-dev.yml`:

~~~yaml
lab:
  message: "git-app-dev-v2"
  timeout: 4s
  app-profile-note: "from precedence-client-dev.yml"
~~~

Commit thay đổi:

~~~powershell
cd ..\config-repo
git add precedence-client-dev.yml
git commit -m "Change dev message for precedence lab"
git log -1 --oneline
~~~

Đảm bảo `LAB_MESSAGE` đã được xóa và không truyền `--lab.message`. Vì Config Server đang dùng URI `file:`, nó đọc trực tiếp repository cục bộ đã commit và không tạo local clone. Gọi lại endpoint để xác nhận Config Server nhìn thấy commit mới:

~~~powershell
curl.exe http://localhost:8888/precedence-client/dev/main
~~~

Trong response, kiểm tra `version` và `lab.message` là `git-app-dev-v2`. Sau khi endpoint trả giá trị mới, khởi động lại Config Client để nó nạp Config Data mới trong lần startup tiếp theo:

~~~powershell
cd ..\precedence-client
java -jar .\target\precedence-client-0.0.1-SNAPSHOT.jar
~~~

Nếu endpoint vẫn trả giá trị cũ:

1. Kiểm tra commit mới đã được tạo trong đúng thư mục `config-repo` và branch `main`.
2. Kiểm tra `spring.cloud.config.server.git.uri` trỏ đúng đường dẫn repository đó.
3. Kiểm tra request dùng đúng application `precedence-client`, profile `dev` và label `main`.
4. Xác minh client không còn environment variable hoặc command-line argument ghi đè.

Không restart Config Server để buộc clone lại trong bài lab này: với URI `file:`, không có local clone. Nếu cần thực hành `clone-on-start` hoặc `refresh-rate`, hãy cấu hình một remote Git URI trong một biến thể riêng; các thuộc tính đó không được kiểm tra ở bài lab dùng repository cục bộ.

## 12. Phân biệt command-line argument với Java system property

Hai cách truyền sau đều có thể đặt property nhưng thuộc hai nguồn khác nhau:

~~~powershell
# Spring Boot command-line argument
java -jar .\target\precedence-client-0.0.1-SNAPSHOT.jar --lab.message=from-cli

# JVM system property
java -Dlab.message=from-system-property -jar .\target\precedence-client-0.0.1-SNAPSHOT.jar
~~~

Trong thứ tự mặc định của Spring Boot, Java system properties có độ ưu tiên cao hơn OS environment variables nhưng thấp hơn command-line arguments. Vì vậy nếu truyền đồng thời:

~~~powershell
$env:LAB_MESSAGE = "from-env"
java -Dlab.message=from-system-property -jar .\target\precedence-client-0.0.1-SNAPSHOT.jar --lab.message=from-cli
~~~

Giá trị hiệu lực vẫn là `from-cli`.

Trong IDE, `--lab.message=...` phải được đặt ở mục Program arguments; `-Dlab.message=...` đặt ở mục VM options. Đặt nhầm vị trí là nguyên nhân phổ biến khiến bài thực hành cho kết quả khác dự đoán.

## 13. Biến thể: kiểm tra legacy bootstrap

Spring Boot 2.4 trở lên dùng Config Data API với `spring.config.import` làm cơ chế nạp cấu hình hiện đại. Legacy bootstrap là cơ chế cũ, dùng bootstrap context riêng và không tự bật mặc định trong các phiên bản Spring Boot mới. Để thử biến thể này, tạm thời bỏ `spring.config.import` khỏi `application.yml` của client và bật legacy bootstrap bằng **một** trong hai cách sau.

Cách A — thêm dependency vào `pom.xml` của Config Client (giữ dependency `spring-cloud-starter-config` hiện có):

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-bootstrap</artifactId>
</dependency>
~~~

Cách B — bật bootstrap bằng system property hoặc environment variable, không cần thêm starter:

~~~powershell
# PowerShell: đặt biến trong terminal sẽ dùng để chạy client
$env:SPRING_CLOUD_BOOTSTRAP_ENABLED = "true"
~~~

Nếu dùng Cách B với environment variable, giữ biến này trong terminal cho tất cả lần chạy legacy và xóa sau khi hoàn tất. Cách dùng JVM system property sẽ truyền `-Dspring.cloud.bootstrap.enabled=true` vào từng lệnh khởi chạy.

Tạo `precedence-client/src/main/resources/bootstrap.yml` để khai báo Config Server, application và profile cho bootstrap context:

~~~yaml
spring:
  application:
    name: precedence-client
  profiles:
    active: dev
  cloud:
    config:
      uri: http://localhost:8888
      label: main
~~~

Tên ứng dụng và profile trong `bootstrap.yml` quyết định context mà client yêu cầu; ở đây client tải `precedence-client/dev/main`. Không giữ `spring.config.import` trong `application.yml` khi chạy biến thể legacy, để tránh khởi tạo đồng thời hai cơ chế nạp cấu hình.

**Lưu ý phiên bản:** Với Spring Cloud `2022.0.0`–`2022.0.2`, `PropertySourceLocator` (bao gồm locator của Spring Cloud Config) mặc định chạy trong main application context thay vì bootstrap context. Nếu dùng legacy bootstrap trên các phiên bản này, thêm thuộc tính sau vào `bootstrap.yml` để buộc locator chạy trong bootstrap context:

~~~yaml
spring:
  cloud:
    config:
      initialize-on-context-refresh: true
~~~

Hoặc chọn một Spring Cloud release train mới hơn nhưng vẫn tương thích với phiên bản Spring Boot đang dùng. Từ Spring Cloud `2022.0.3`, hành vi gọi `PropertySourceLocator` đã được điều chỉnh.

Sau khi đã sửa `application.yml`, thêm dependency vào `pom.xml` nếu chọn Cách A, và tạo `bootstrap.yml`, build lại client từ thư mục dự án `precedence-client` (nơi chứa `pom.xml`). Bước này bảo đảm JAR chứa dependency và cấu hình mới trước khi chạy:

~~~powershell
mvn clean package
~~~

Chỉ sau khi build hoàn tất mới khởi chạy JAR bằng đúng một cách kích hoạt legacy đã chọn:

~~~powershell
# Cách A: đã thêm spring-cloud-starter-bootstrap vào pom.xml
java -jar .\target\precedence-client-0.0.1-SNAPSHOT.jar

# Cách B: đã đặt SPRING_CLOUD_BOOTSTRAP_ENABLED=true trong terminal
java -jar .\target\precedence-client-0.0.1-SNAPSHOT.jar

# Hoặc Cách B: truyền JVM system property trực tiếp
java -Dspring.cloud.bootstrap.enabled=true -jar .\target\precedence-client-0.0.1-SNAPSHOT.jar
~~~

Trên Bash/zsh, Cách B có thể chạy bằng `SPRING_CLOUD_BOOTSTRAP_ENABLED=true java -jar target/precedence-client-0.0.1-SNAPSHOT.jar` hoặc `java -Dspring.cloud.bootstrap.enabled=true -jar target/precedence-client-0.0.1-SNAPSHOT.jar`. Sau khi hoàn tất các lần chạy dùng environment variable, xóa biến trong PowerShell bằng `Remove-Item Env:SPRING_CLOUD_BOOTSTRAP_ENABLED`.

Trong legacy bootstrap, remote property source được nạp trong bootstrap context và mặc định có ưu tiên cao, nên local environment variable hoặc command line có thể không ghi đè được remote property. Nếu muốn environment/system/command line được ghi đè remote, đặt các cờ sau trong **remote property source trên Git**, ví dụ file `precedence-client.yml`:

~~~yaml
spring:
  cloud:
    config:
      allow-override: true
      override-system-properties: false
~~~

Ý nghĩa:

- `allow-override: true` cấp quyền cho client override remote property source.
- `override-system-properties: false` đặt remote property source sao cho system properties, environment variables và command-line arguments có thể thắng; local config files vẫn không được ghi đè remote.
- Nếu đặt `override-none: true`, mọi local property source có thể ghi đè remote, bao gồm cả local configuration files.

Các cờ này phải nằm trong cấu hình từ xa. Đặt `spring.cloud.config.allow-override=true` trong `application.yml` hoặc `bootstrap.yml` cục bộ của client không cấp quyền override cho remote source. Sau khi thêm chúng vào `precedence-client.yml`, chạy client bằng một trong hai cách kích hoạt legacy ở trên, lần lượt thử `LAB_MESSAGE=from-env` và `--lab.message=from-cli`, rồi dùng `/actuator/env/lab.message` để xem property source thắng. Nếu chọn Cách B bằng environment variable, đặt lại `SPRING_CLOUD_BOOTSTRAP_ENABLED=true` trước mỗi lần chạy; khi kiểm tra environment override, đặt đồng thời `LAB_MESSAGE=from-env`. Nếu chọn system property, thêm `-Dspring.cloud.bootstrap.enabled=true` vào từng lệnh Java. Kết quả của biến thể này có thể khác phần chính vì remote property source có quy tắc override riêng.

## 14. Bài tập mở rộng

Thực hiện các thử nghiệm sau và ghi lại giá trị hiệu lực cùng property source thắng:

1. Đổi active profile từ `dev` sang `prod`; tạo `application-prod.yml` và `precedence-client-prod.yml` với các giá trị khác nhau.
2. Giữ `LAB_MESSAGE=from-env`, nhưng truyền `--lab.message=from-cli`; xác nhận command line thắng.
3. Đặt thêm `-Dlab.message=from-system-property`; so sánh system property với environment variable và command line.
4. Truyền `--spring.cloud.config.label=<git-branch>` để đọc một branch cấu hình khác.
5. Tạo branch `experiment` trong config repo, thay `lab.message` và khởi động client với label đó.
6. Xóa `LAB_MESSAGE` và bỏ command line để kiểm tra Git trở lại làm nguồn thắng.
7. Chạy client khi Config Server dừng; xác nhận import bắt buộc làm startup thất bại.
8. Đổi import thành `optional:configserver:http://localhost:8888` và quan sát fallback. Chỉ dùng fallback không nhạy cảm, không dùng giá trị mặc định để che thiếu secret bắt buộc.
9. Bổ sung một key mới `lab.release-note` trong Git và kiểm tra nó bind vào một field mới của `LabProperties`.
10. Thử truyền property không tồn tại trong Git qua command line để thấy nguồn local có thể thêm key mới, không chỉ ghi đè key đã tồn tại.

## 15. Bảng chẩn đoán khi kết quả không như dự đoán

| Hiện tượng | Nguyên nhân có thể có | Cách kiểm tra |
|---|---|---|
| Client luôn nhận giá trị Git | Biến môi trường đặt sai tên hoặc command line không được truyền vào process | Kiểm tra `LAB_MESSAGE`, Program arguments và `/actuator/env/lab.message` |
| Environment variable không ghi đè | Đang dùng legacy bootstrap với remote override chưa được cho phép, hoặc tên biến sai | Xác nhận Config Data import/legacy bootstrap và kiểm tra `allow-override` nếu dùng legacy |
| Command line không ghi đè | Tham số đặt ở VM options thay vì Program arguments, hoặc SpringApplication tắt command-line properties | Chạy trực tiếp `java -jar ... --lab.message=...` |
| Git trả giá trị mặc định thay vì profile | Active profile sai hoặc thiếu file profile-specific | Kiểm tra `spring.profiles.active` và endpoint `/application/profile/label` |
| Config Server chưa thấy commit mới với URI `file:` | Commit vào nhầm thư mục/branch hoặc URI/application/profile/label không khớp | Kiểm tra commit trong `config-repo`, `spring.cloud.config.server.git.uri` và endpoint `/precedence-client/dev/main` |
| Client không khởi động | Config Server không sẵn sàng hoặc import bắt buộc không truy cập được | Kiểm tra Config Server health và log Config Client |
| Actuator không hiện nguồn | Endpoint `env` chưa expose hoặc không đủ quyền | Kiểm tra management exposure và authorization |
| Kết quả khác khi chạy IDE | IDE có environment/program/VM arguments riêng | Xem cấu hình Run/Debug và xóa giá trị cũ |
| Kết quả khác giữa hai terminal | Environment variable chỉ được đặt trong một shell hoặc một process | Kiểm tra environment tại đúng terminal chạy Java |

## 16. Checklist hoàn thành

- [ ] Git repository có `application.yml`, `application-dev.yml`, `precedence-client.yml` và `precedence-client-dev.yml`.
- [ ] Git branch `main` có commit và working tree sạch.
- [ ] Config Server đọc trực tiếp repository cục bộ qua URI `file:` và trả đúng application/profile/label.
- [ ] Config Client dùng `spring.config.import=configserver:...`.
- [ ] `LabProperties` bind được property từ Git.
- [ ] Chạy chỉ Git cho kết quả `git-app-dev`.
- [ ] Chạy environment variable cho kết quả `from-env`.
- [ ] Chạy command line cùng environment variable cho kết quả `from-cli`.
- [ ] Actuator/debugger xác nhận được property source thắng.
- [ ] Đã thay đổi Git, commit và quan sát client nhận giá trị mới.
- [ ] Đã phân biệt `--property=value` với `-Dproperty=value`.
- [ ] Hiểu vì sao legacy bootstrap cần remote override flags nếu muốn local override.
- [ ] Đã bật legacy bootstrap, cấu hình `bootstrap.yml` và chạy riêng biến thể không dùng `spring.config.import`.
- [ ] Đã xóa environment variable sau khi thực hành.

## 17. Kết luận

Khi dùng Spring Boot Config Data import, Git cung cấp giá trị nền đã được Config Server hợp nhất theo application và profile. Environment variable có thể thay thế giá trị đó tại runtime, còn command-line argument có ưu tiên cao hơn và thường phù hợp cho override tạm thời khi debug hoặc chạy tác vụ đặc biệt. Khi kết quả khác dự đoán, hãy kiểm tra property source đang thắng thay vì chỉ đọc file YAML trong Git.

Legacy bootstrap có quy tắc remote override riêng: mặc định remote source có ưu tiên cao và chỉ cho phép local override khi remote repository cấp quyền bằng `spring.cloud.config.allow-override`. Việc ghi rõ đang dùng cơ chế nào là điều kiện cần để quản lý cấu hình nhất quán giữa nhiều ứng dụng và môi trường.

## Tài liệu tham khảo

- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [Spring Cloud Config — Config Client và Config Data import](https://docs.spring.io/spring-cloud-config/reference/client.html)
- [Spring Cloud Commons — Overriding remote properties trong bootstrap context](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/application-context-services.html)
- [Spring Cloud 2022.0.3 — Application Context Hierarchies và PropertySourceLocator](https://docs.spring.io/spring-cloud/docs/2022.0.3/reference/htmlsingle/)
- [Spring Cloud Config — Environment Repository và profile precedence](https://docs.spring.io/spring-cloud-config/reference/server/environment-repository.html)
