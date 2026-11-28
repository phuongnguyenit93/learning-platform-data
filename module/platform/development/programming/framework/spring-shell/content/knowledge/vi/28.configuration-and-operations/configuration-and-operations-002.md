# Profile, biến môi trường và ưu tiên nguồn cấu hình

Một ứng dụng Spring Shell thường được chạy ở nhiều môi trường: máy phát triển, kiểm thử, staging và production. Cùng một bộ command có thể cần endpoint khác nhau, thư mục xuất báo cáo khác nhau, giới hạn xử lý khác nhau hoặc cách bật tính năng khác nhau. Nếu phải sửa code hoặc đóng gói một JAR riêng cho từng môi trường, việc phát hành và bảo trì sẽ nhanh chóng trở nên khó kiểm soát.

Spring Shell chạy trên Spring Environment và, trong ứng dụng Spring Boot, sử dụng cơ chế externalized configuration của Spring Boot. Cấu hình có thể đến từ file YAML/properties, profile, biến môi trường, JVM system property, JSON, file được import hoặc command-line property. Khi cùng một key xuất hiện ở nhiều nguồn, thứ tự ưu tiên quyết định giá trị cuối cùng.

Bài học này tập trung vào cách tổ chức profile, cách ánh xạ biến môi trường và cách dự đoán nguồn nào ghi đè nguồn nào. Đây là nền tảng để một CLI có thể dùng cùng artifact ở nhiều môi trường mà vẫn kiểm soát được cấu hình.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích vai trò của Spring Environment và externalized configuration trong ứng dụng Spring Shell.
- Tổ chức cấu hình chung và cấu hình theo profile bằng YAML hoặc properties.
- Kích hoạt profile qua biến môi trường hoặc JVM system property.
- Phân biệt active profile, default profile, included profile và profile group.
- Giải thích thứ tự ưu tiên của các PropertySource phổ biến trong Spring Boot.
- Hiểu thứ tự ưu tiên bên trong nhóm Config Data: file đóng gói, file bên ngoài và file theo profile.
- Ánh xạ property name sang biến môi trường theo relaxed binding.
- Bind cấu hình có cấu trúc bằng ConfigurationProperties và kiểm tra giá trị.
- Dùng spring.config.location, spring.config.additional-location và spring.config.import đúng mục đích.
- Đưa cấu hình bí mật ra ngoài JAR và tránh commit secret vào repository.
- Chẩn đoán giá trị cấu hình đang được áp dụng khi có nhiều nguồn cùng khai báo.
- Kiểm thử cấu hình theo profile và theo từng nguồn ghi đè.

## 1. Spring Shell sử dụng Spring Environment

Spring Environment là nơi Spring tập hợp các nguồn cấu hình dưới dạng PropertySource. Khi một bean cần giá trị, Spring có thể phân giải property từ Environment hoặc bind nhiều property thành một object có cấu trúc.

Spring Shell không tạo một hệ thống ưu tiên cấu hình riêng cho command. Trong ứng dụng Spring Boot dùng Spring Shell, các thuộc tính như profile, biến môi trường, file cấu hình và JVM property được nạp theo cơ chế của Spring Boot. Các bean command, service và component khác có thể đọc cấu hình từ cùng Environment.

Ví dụ, CLI quản trị có thể cần:

- Tên môi trường hiện tại để hiển thị trong prompt.
- URL API backend.
- Thư mục xuất file.
- Giới hạn số bản ghi cho một lần export.
- Timeout khi gọi dịch vụ từ xa.
- Tính năng được bật trong môi trường staging nhưng tắt ở production.

Không nên viết các giá trị này cố định trong command method. Hãy đặt chúng trong cấu hình và bind vào bean để cùng một artifact có thể chạy với giá trị khác nhau.

~~~mermaid
flowchart TD
    A[application.yml trong JAR] --> E[Spring Environment]
    B[application-prod.yml] --> E
    C[Biến môi trường / JVM properties] --> E
    D[Config file bên ngoài / command-line properties] --> E
    E --> F[ConfigurationProperties binding]
    F --> G[Service và command beans]
    G --> H[Spring Shell command]
~~~

Sơ đồ mô tả ý tưởng tổng quát. Thứ tự cụ thể giữa các nguồn được Spring Boot xác định; giá trị ở nguồn có ưu tiên cao hơn sẽ ghi đè giá trị ở nguồn thấp hơn.

## 2. Tách cấu hình chung và cấu hình theo môi trường

Một cách tổ chức thông dụng là đặt giá trị mặc định trong application.yml và chỉ ghi đè những giá trị khác biệt trong application-{profile}.yml.

Ví dụ cấu trúc:

~~~text
src/main/resources/
  application.yml
  application-dev.yml
  application-test.yml
  application-staging.yml
  application-prod.yml
~~~

File application.yml chứa cấu hình dùng chung:

~~~yaml
spring:
  application:
    name: support-cli

support:
  cli:
    environment-name: local
    output-directory: ./reports
    max-export-rows: 500
  backend:
    connect-timeout: 3s
    read-timeout: 10s
~~~

File application-dev.yml ghi đè endpoint dành cho môi trường phát triển:

~~~yaml
support:
  cli:
    environment-name: development
  backend:
    base-url: http://localhost:8081
~~~

File application-prod.yml chứa cấu hình production:

~~~yaml
support:
  cli:
    environment-name: production
    output-directory: /var/lib/support-cli/reports
    max-export-rows: 2000
  backend:
    base-url: https://api.example.internal
    connect-timeout: 2s
    read-timeout: 8s
~~~

Khi profile prod hoạt động, Spring Boot nạp cấu hình chung và cấu hình theo profile. Giá trị trong application-prod.yml ghi đè giá trị tương ứng trong application.yml.

Đây là cấu hình dữ liệu của môi trường, không phải nơi đặt password hoặc token trực tiếp trong source repository. Secret cần được cung cấp qua secret manager, environment variable hoặc config tree được bảo vệ.

## 3. Kích hoạt profile

Profile cho phép chọn nhóm bean và cấu hình phù hợp với một môi trường hoặc một chức năng.

Nếu không chỉ định active profile, Spring Boot sử dụng profile mặc định tên là default. Có thể đổi profile mặc định bằng spring.profiles.default.

### 3.1. Kích hoạt bằng biến môi trường

Linux/macOS:

~~~bash
SPRING_PROFILES_ACTIVE=prod java -jar support-cli.jar
~~~

PowerShell:

~~~powershell
$env:SPRING_PROFILES_ACTIVE = 'prod'
java -jar support-cli.jar
~~~

Command Prompt:

~~~bat
set SPRING_PROFILES_ACTIVE=prod
java -jar support-cli.jar
~~~

Biến môi trường có hiệu lực trong process con được khởi chạy từ shell hiện tại. Trong PowerShell, biến đặt bằng $env: chỉ tồn tại trong session đó và các process con của nó.

### 3.2. Kích hoạt bằng JVM system property

~~~bash
java -Dspring.profiles.active=prod -jar support-cli.jar
~~~

JVM system property phải đặt trước -jar. Nếu đặt sau tên JAR, Java launcher chuyển nó thành application argument thay vì system property của JVM.

### 3.3. Kích hoạt bằng Spring Boot command-line property

Spring Boot cho phép truyền option argument bắt đầu bằng --:

~~~bash
java -jar support-cli.jar --spring.profiles.active=prod
~~~

Trong ứng dụng Spring Boot thông thường, argument này được đưa vào Environment và có thể ghi đè giá trị profile trong file cấu hình. Tuy nhiên, Spring Shell cũng có runner nhận process arguments để phân tích command. Nếu cùng lần chạy vừa truyền startup property vừa truyền command của Spring Shell, cần kiểm tra cách runner của phiên bản đang dùng phân tách các arguments. Với CLI non-interactive, biến môi trường hoặc JVM property thường giúp tách cấu hình khởi động khỏi arguments dành cho command rõ ràng hơn.

## 4. Active profile, default profile và included profile

Các thuộc tính profile có mục đích khác nhau:

| Thuộc tính | Mục đích |
|---|---|
| spring.profiles.active | Chọn profile đang hoạt động |
| spring.profiles.default | Profile dùng khi không có active profile |
| spring.profiles.include | Bổ sung profile vào danh sách profile hoạt động |
| spring.profiles.group | Định nghĩa nhóm profile để kích hoạt cùng nhau |

Ví dụ:

~~~yaml
spring:
  profiles:
    active: staging
    include:
      - common
      - observability
~~~

Trong ví dụ, staging là profile được chọn; common và observability được thêm vào danh sách active profiles. Included profiles được thêm trước các profile được kích hoạt bằng spring.profiles.active.

Có thể đặt profile mặc định khác:

~~~yaml
spring:
  profiles:
    default: local
~~~

Nếu không có active profile, local được dùng thay cho default. Nếu muốn ứng dụng không tự bật profile default, có thể đặt:

~~~yaml
spring:
  profiles:
    default: none
~~~

Không nên mặc định production chỉ vì đó là môi trường triển khai chính. Khi chạy nhầm trên máy phát triển, một default profile production có thể kết nối tới hệ thống thật hoặc ghi dữ liệu vào môi trường không mong muốn.

### 4.1. Profile group

Khi có nhiều profile nhỏ, có thể gom chúng thành một nhóm logic. Ví dụ production cần database, messaging và metrics:

~~~yaml
spring:
  profiles:
    group:
      production:
        - proddb
        - prodmq
        - metrics
~~~

Khi kích hoạt production:

~~~bash
SPRING_PROFILES_ACTIVE=production java -jar support-cli.jar
~~~

Spring Boot kích hoạt production cùng các profile thành viên. Cách này giúp launcher và tài liệu vận hành chỉ cần dùng một tên profile cấp cao.

### 4.2. Profile activation có giới hạn vị trí

spring.profiles.active, spring.profiles.default, spring.profiles.include và spring.profiles.group phải được khai báo trong tài liệu cấu hình không phụ thuộc profile. Không đặt chúng bên trong application-prod.yml hoặc YAML document đã được kích hoạt bằng spring.config.activate.on-profile.

Nếu cần điều kiện áp dụng một phần cấu hình theo profile, hãy dùng spring.config.activate.on-profile:

~~~yaml
support:
  cli:
    color-output: true
---
spring:
  config:
    activate:
      on-profile: prod
support:
  cli:
    color-output: false
    environment-name: production
~~~

Document đầu tiên luôn được xét. Document thứ hai chỉ được đưa vào cấu hình khi profile prod hoạt động.

Tài liệu: [Spring Boot Profiles](https://docs.spring.io/spring-boot/reference/features/profiles.html).

## 5. Thứ tự ưu tiên của các nguồn cấu hình

Spring Boot có thứ tự PropertySource xác định. Nguồn được liệt kê sau có ưu tiên cao hơn và có thể ghi đè giá trị từ nguồn trước.

Bảng dưới đây trình bày thứ tự từ ưu tiên thấp lên ưu tiên cao theo tài liệu Spring Boot hiện hành:

| Thứ tự | Nguồn | Ví dụ |
|---:|---|---|
| 1 | Default properties | SpringApplication.setDefaultProperties(...) |
| 2 | @PropertySource | File được nạp qua annotation trên @Configuration |
| 3 | Config Data | application.yml, application-prod.yml, file import |
| 4 | RandomValuePropertySource | random.* |
| 5 | OS environment variables | SUPPORT_BACKEND_BASEURL |
| 6 | Java System properties | -Dsupport.backend.base-url=... |
| 7 | JNDI attributes | java:comp/env/... |
| 8 | ServletContext init parameters | Tham số context của servlet |
| 9 | ServletConfig init parameters | Tham số servlet |
| 10 | SPRING_APPLICATION_JSON | JSON được truyền qua env/system property |
| 11 | Command-line properties | --support.backend.base-url=... |
| 12 | Test properties | properties của @SpringBootTest |
| 13 | @DynamicPropertySource | Dynamic property trong test |
| 14 | @TestPropertySource | Property source của test |
| 15 | Devtools global settings | Cấu hình Devtools trong thư mục home |

Ứng dụng Spring Shell chạy như CLI thường không dùng JNDI, ServletContext hoặc ServletConfig. Các mục này vẫn xuất hiện trong thứ tự chung của Spring Boot vì cùng cơ chế cấu hình được dùng trong nhiều loại ứng dụng.

Với một CLI thông thường, hãy tập trung vào các nguồn sau:

1. Default properties trong code.
2. application.yml và file profile.
3. File cấu hình bên ngoài hoặc file import.
4. Biến môi trường.
5. JVM system properties.
6. SPRING_APPLICATION_JSON.
7. Command-line properties của Spring Boot.

Lưu ý rằng thứ tự tổng thể và thứ tự bên trong Config Data là hai cấp khác nhau. File profile-specific bên ngoài JAR có thể ghi đè file mặc định bên ngoài JAR; sau khi Config Data được xử lý, biến môi trường và các nguồn có ưu tiên cao hơn tiếp tục ghi đè giá trị cuối cùng.

Nguồn chính thức: [Spring Boot Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html).

## 6. Thứ tự bên trong Config Data

Trong nhóm Config Data, Spring Boot tìm và nạp các file theo vị trí. Với cấu hình mặc định, thứ tự quan trọng gồm:

1. application.properties hoặc YAML nằm trong JAR.
2. File profile-specific nằm trong JAR, ví dụ application-prod.yml.
3. application.properties hoặc YAML bên ngoài JAR.
4. File profile-specific bên ngoài JAR.

Giá trị ở vị trí sau có thể ghi đè giá trị ở vị trí trước. Vì vậy, file application-prod.yml đặt cạnh JAR có thể ghi đè giá trị trong application-prod.yml được đóng gói bên trong JAR.

Các vị trí tìm kiếm mặc định thường gồm:

- Classpath root.
- Thư mục config trên classpath.
- Thư mục làm việc hiện tại.
- Thư mục config bên dưới working directory.
- Các thư mục con trực tiếp của config bên ngoài theo wildcard location mặc định.

Đây là lý do cùng một JAR có thể được đóng gói với cấu hình mặc định rồi được triển khai bằng một application-prod.yml nằm cạnh artifact. Người vận hành có thể thay đổi endpoint hoặc output directory mà không cần build lại JAR.

Nếu có cả application.properties và application.yml trong cùng một vị trí, Spring Boot ưu tiên application.properties. Để tránh bất ngờ, nên chọn một định dạng chính cho toàn ứng dụng thay vì duy trì hai file tương đương.

## 7. Biến môi trường và relaxed binding

Tên property trong file thường dùng chữ thường và kebab-case:

~~~yaml
support:
  backend:
    base-url: https://api.example.internal
    connect-timeout: 2s
  cli:
    output-directory: /var/lib/support-cli/reports
    max-export-rows: 2000
~~~

Khi ánh xạ sang biến môi trường, Spring Boot áp dụng relaxed binding. Quy tắc cơ bản:

- Chuyển tên thành chữ hoa.
- Thay dấu chấm bằng dấu gạch dưới.
- Bỏ dấu gạch ngang.
- Với index của list, dùng số nằm giữa dấu gạch dưới.

| Property | Environment variable |
|---|---|
| support.backend.base-url | SUPPORT_BACKEND_BASEURL |
| support.backend.connect-timeout | SUPPORT_BACKEND_CONNECTTIMEOUT |
| support.cli.output-directory | SUPPORT_CLI_OUTPUTDIRECTORY |
| support.cli.max-export-rows | SUPPORT_CLI_MAXEXPORTROWS |
| spring.profiles.active | SPRING_PROFILES_ACTIVE |
| spring.shell.interactive.enabled | SPRING_SHELL_INTERACTIVE_ENABLED |

Không giữ dấu gạch ngang trong tên biến môi trường. Ví dụ SUPPORT_BACKEND_BASE_URL không phải dạng canonical được relaxed binding quy định cho support.backend.base-url; dạng chuyển đổi chính xác là SUPPORT_BACKEND_BASEURL.

Với list:

~~~yaml
support:
  allowed-environments:
    - dev
    - staging
    - prod
~~~

Biến môi trường tương ứng có thể dùng dạng:

~~~text
SUPPORT_ALLOWEDENVIRONMENTS_0=dev
SUPPORT_ALLOWEDENVIRONMENTS_1=staging
SUPPORT_ALLOWEDENVIRONMENTS_2=prod
~~~

Khi bind environment variable vào Map, tên biến được chuyển thành chữ thường; điều này có thể ảnh hưởng đến key của Map. Nếu key cần phân biệt chữ hoa/chữ thường hoặc chứa dấu gạch ngang, hãy kiểm tra kỹ quy tắc binding và cân nhắc nguồn cấu hình khác.

Tài liệu: [Binding From Environment Variables](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.relaxed-binding.environment-variables).

## 8. Ví dụ ghi đè cấu hình từ nhiều nguồn

Giả sử application.yml có:

~~~yaml
support:
  backend:
    base-url: http://localhost:8081
  cli:
    max-export-rows: 500
~~~

File application-prod.yml có:

~~~yaml
support:
  backend:
    base-url: https://api.example.internal
  cli:
    max-export-rows: 2000
~~~

Environment variable:

~~~bash
SUPPORT_CLI_MAXEXPORTROWS=3000
~~~

JVM property:

~~~bash
-Dsupport.cli.max-export-rows=4000
~~~

Command-line property của Spring Boot:

~~~text
--support.cli.max-export-rows=5000
~~~

Nếu tất cả cùng được cung cấp và property name được phân giải đúng, giá trị cuối cùng của max-export-rows là 5000. Property base-url không bị ghi đè bởi các nguồn chỉ khai báo max-export-rows, nên vẫn là https://api.example.internal từ profile prod.

| Nguồn | max-export-rows |
|---|---:|
| application.yml trong JAR | 500 |
| application-prod.yml | 2000 |
| Environment variable | 3000 |
| JVM system property | 4000 |
| Spring Boot command-line property | 5000 |
| **Giá trị cuối cùng** | **5000** |

Không nên tạo quá nhiều lớp ghi đè cho cùng một property. Hãy dùng file cho cấu hình mặc định, profile cho khác biệt môi trường, environment variable cho deployment và command-line property cho một lần chạy có chủ đích.

## 9. Dùng SPRING_APPLICATION_JSON

Khi tên property phức tạp hoặc cần truyền nhiều giá trị cùng lúc, Spring Boot hỗ trợ JSON thông qua spring.application.json hoặc SPRING_APPLICATION_JSON.

Linux/macOS:

~~~bash
SPRING_APPLICATION_JSON='{"support":{"backend":{"base-url":"https://api.example.internal"},"cli":{"max-export-rows":2500}}}' java -jar support-cli.jar
~~~

PowerShell:

~~~powershell
$env:SPRING_APPLICATION_JSON = '{"support":{"backend":{"base-url":"https://api.example.internal"},"cli":{"max-export-rows":2500}}}'
java -jar support-cli.jar
~~~

JSON được phân tích và thêm vào Environment. Có thể cung cấp JSON qua JVM system property hoặc command-line property theo cơ chế Spring Boot.

Một điểm đặc biệt: giá trị null trong JSON được thêm vào PropertySource nhưng được xem như missing value khi phân giải. Vì vậy, null không thể dùng để xóa hoặc ghi đè một giá trị có sẵn ở nguồn ưu tiên thấp hơn.

Không đưa secret trực tiếp vào command line nếu hệ điều hành, process monitor hoặc công cụ vận hành có thể ghi lại command line. Dùng secret store hoặc cơ chế cấp secret của nền tảng triển khai.

## 10. Định vị file cấu hình bên ngoài

Spring Boot có ba property thường dùng để điều khiển vị trí và tên file cấu hình:

| Property | Tác dụng |
|---|---|
| spring.config.name | Thay basename application bằng tên khác |
| spring.config.location | Chỉ định vị trí tìm kiếm và thay thế vị trí mặc định |
| spring.config.additional-location | Bổ sung vị trí ngoài các vị trí mặc định |

### 10.1. Đổi tên file cấu hình

Nếu muốn dùng support-cli.yml thay cho application.yml:

~~~bash
SPRING_CONFIG_NAME=support-cli java -jar support-cli.jar
~~~

Spring Boot sẽ tìm file theo basename support-cli và các biến thể theo profile.

### 10.2. Thay thế vị trí tìm kiếm mặc định

~~~bash
java -Dspring.config.location=file:/etc/support-cli/ -jar support-cli.jar
~~~

spring.config.location thay thế các vị trí mặc định. Nếu chỉ định thư mục, giá trị nên kết thúc bằng dấu slash để Spring Boot thêm tên file cấu hình vào vị trí đó.

Khi dùng property này, hãy bảo đảm các file mặc định cần thiết đã được đặt trong vị trí mới hoặc được import. Nếu quên, ứng dụng có thể không còn nạp cấu hình mong đợi từ classpath.

### 10.3. Bổ sung vị trí ngoài

~~~bash
java -Dspring.config.additional-location=optional:file:/etc/support-cli/ -jar support-cli.jar
~~~

additional-location giữ các vị trí mặc định và bổ sung vị trí mới. Giá trị từ vị trí bổ sung có thể ghi đè giá trị đã nạp từ vị trí mặc định.

### 10.4. Vị trí tùy chọn

Tiền tố optional: cho phép ứng dụng tiếp tục khởi động khi file không tồn tại:

~~~bash
java -Dspring.config.additional-location=optional:file:/etc/support-cli/ -jar support-cli.jar
~~~

Chỉ dùng optional khi file thật sự không bắt buộc. Nếu cấu hình chứa thông tin cần thiết để kết nối production, để file thiếu mà ứng dụng vẫn chạy với giá trị mặc định có thể gây lỗi khó phát hiện. Với cấu hình bắt buộc, hãy để ứng dụng thất bại sớm khi file không tồn tại.

Các property spring.config.name, spring.config.location và spring.config.additional-location được xử lý rất sớm khi ứng dụng khởi động. Vì vậy, hãy cung cấp chúng qua environment variable, JVM system property hoặc startup argument trước khi Config Data được nạp; không đặt chúng trong một file mà chính chúng đang quyết định cách tìm.

## 11. Import file cấu hình

Có thể khai báo file bổ sung ngay trong application.yml bằng spring.config.import:

~~~yaml
spring:
  config:
    import:
      - optional:file:./config/cli-overrides.yml
      - optional:file:./config/backend.yml
~~~

Spring Boot nạp các file được import và cho phép giá trị trong file import ghi đè giá trị của document đã khai báo import. Nếu có nhiều import, thứ tự import ảnh hưởng đến giá trị cuối cùng; import được xử lý sau có thể ghi đè import trước.

Import có thể dùng classpath, file hoặc loại location được hỗ trợ bởi Config Data API. Một số ví dụ:

~~~yaml
spring:
  config:
    import:
      - optional:classpath:/defaults/cli.yml
      - optional:file:./config/local.yml
~~~

Không khai báo cùng một file qua nhiều đường dẫn khác nhau nếu không có lý do rõ ràng. Properties files chỉ được nạp một lần, nhưng cấu hình import phức tạp có thể làm người vận hành khó dự đoán nguồn giá trị.

## 12. Đưa secret ra khỏi file cấu hình đóng gói

Không commit password database, API token, private key hoặc client secret vào application-prod.yml. JAR có thể được tải xuống, sao chép, giải nén hoặc kiểm tra bởi nhiều người; secret đóng gói bên trong không còn là bí mật.

Một cách đơn giản là cấp secret qua environment variable:

~~~bash
SUPPORT_BACKEND_API_TOKEN=... java -jar support-cli.jar
~~~

File cấu hình có thể tham chiếu biến môi trường:

~~~yaml
support:
  backend:
    api-token: ${SUPPORT_BACKEND_API_TOKEN}
~~~

Có thể đặt giá trị mặc định cho môi trường phát triển:

~~~yaml
support:
  backend:
    api-token: ${SUPPORT_BACKEND_API_TOKEN:}
~~~

Với secret bắt buộc trong production, không nên dùng giá trị mặc định rỗng rồi tiếp tục chạy. Hãy xác thực cấu hình khi khởi động để ứng dụng báo lỗi rõ ràng nếu secret thiếu.

### 12.1. Configuration tree

Spring Boot hỗ trợ config tree để đọc cấu hình từ một cây thư mục, thường phù hợp với secret được mount bởi container hoặc nền tảng triển khai.

Ví dụ cấu trúc:

~~~text
/run/secrets/
  support.backend.api-token
  support.backend.client-secret
~~~

Import:

~~~yaml
spring:
  config:
    import: configtree:/run/secrets/
~~~

Tên file được dùng làm property name và nội dung file trở thành property value. Nhờ đó, secret có thể được mount thành file mà không cần ghi vào application.yml.

Không đưa nội dung secret vào log khi debug cấu hình. Cần kiểm soát quyền đọc thư mục secret và không hiển thị giá trị nhạy cảm trong help, command output hoặc exception.

## 13. Bind cấu hình có cấu trúc bằng ConfigurationProperties

Với một nhóm property có quan hệ, nên dùng @ConfigurationProperties thay vì rải nhiều @Value trong command và service.

Ví dụ:

~~~java
package com.example.support.config;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

import java.net.URI;
import java.nio.file.Path;
import java.time.Duration;

@Validated
@ConfigurationProperties(prefix = "support")
public record SupportProperties(
        @NotBlank String environmentName,
        @Valid Backend backend,
        @Valid Cli cli) {

    public record Backend(
            URI baseUrl,
            Duration connectTimeout,
            Duration readTimeout,
            String apiToken) {
    }

    public record Cli(
            Path outputDirectory,
            @Min(1) @Max(100000) int maxExportRows) {
    }
}
~~~

Đăng ký configuration properties bằng scanning:

~~~java
@SpringBootApplication
@ConfigurationPropertiesScan
public class SupportCliApplication {
    public static void main(String[] args) {
        SpringApplication.run(SupportCliApplication.class, args);
    }
}
~~~

Nếu không dùng scanning, có thể đăng ký bằng @EnableConfigurationProperties(SupportProperties.class) trên một configuration class.

Inject bean vào service:

~~~java
@Service
public class ReportExportService {

    private final SupportProperties properties;

    public ReportExportService(SupportProperties properties) {
        this.properties = properties;
    }

    public Path outputPath(String fileName) {
        return properties.cli().outputDirectory().resolve(fileName);
    }
}
~~~

Khi dùng Jakarta Bean Validation, cần có dependency validation phù hợp, chẳng hạn spring-boot-starter-validation. Các constraint như @NotBlank, @Min và @Max giúp ứng dụng từ chối cấu hình sai ngay khi khởi động.

Không dùng cấu hình đã bind mà bỏ qua validation cho thao tác nguy hiểm. Ví dụ max-export-rows bằng 0 hoặc output-directory trỏ vào vị trí không được phép có thể làm command vận hành sai.

## 14. Dùng @Value khi chỉ cần một giá trị

@Value phù hợp cho một property đơn giản:

~~~java
@Component
public class CliBanner {

    private final String environmentName;

    public CliBanner(
            @Value("${support.cli.environment-name:local}") String environmentName) {
        this.environmentName = environmentName;
    }
}
~~~

Placeholder có thể cung cấp giá trị mặc định sau dấu hai chấm. Ví dụ trên dùng local nếu property không tồn tại.

Với nhóm cấu hình có nhiều thuộc tính, nested object, list hoặc validation, @ConfigurationProperties thường dễ quản lý và kiểm thử hơn.

Lưu ý: giá trị mặc định trong field hoặc constructor của configuration object không nhất thiết xuất hiện như một property trong Environment. Nếu code khác gọi Environment.getProperty(), cần hiểu rằng default trong object binding và property thực sự có mặt trong Environment là hai điều khác nhau.

## 15. Placeholder và tham chiếu giữa các property

Một property có thể tham chiếu property khác:

~~~yaml
support:
  backend:
    host: api.example.internal
    base-url: https://${support.backend.host}
  cli:
    output-directory: ${SUPPORT_OUTPUT_DIR:./reports}
~~~

Trong ví dụ:

- base-url được tạo từ host.
- output-directory lấy từ SUPPORT_OUTPUT_DIR nếu có, nếu không dùng ./reports.

Placeholder có thể tham chiếu biến môi trường và property khác. Khi dùng giá trị mặc định, hãy chọn giá trị an toàn cho môi trường chạy.

Không tham chiếu vòng lặp giữa các property. Tránh tạo một chuỗi placeholder quá phức tạp khiến người vận hành khó hiểu giá trị cuối cùng đến từ đâu.

## 16. Collection và quy tắc merge

Khi cùng một property phức hợp được khai báo ở nhiều nguồn, cách merge phụ thuộc kiểu dữ liệu.

**List:** giá trị từ nguồn có ưu tiên cao hơn thay thế toàn bộ list ở nguồn thấp hơn, không tự nối thêm từng phần tử.

Ví dụ application.yml:

~~~yaml
support:
  allowed-environments:
    - dev
    - staging
    - prod
~~~

application-prod.yml:

~~~yaml
support:
  allowed-environments:
    - prod
~~~

Khi profile prod hoạt động, list chỉ còn prod.

**Map:** các entry khác key có thể được kết hợp từ nhiều nguồn; nếu cùng key xuất hiện nhiều nơi, giá trị ở nguồn ưu tiên cao hơn thắng.

Điều này đặc biệt quan trọng với cấu hình quyền hoặc danh sách môi trường. Không giả định một list được khai báo trong file profile chỉ bổ sung phần tử. Nếu cần hợp nhất, hãy dùng map có key rõ ràng hoặc tự xây dựng quy tắc merge trong code.

## 17. Chẩn đoán property đang được áp dụng

Khi một command kết nối sai endpoint hoặc dùng giới hạn export không mong muốn, bước đầu tiên là xác định giá trị thực tế và nguồn đã cung cấp nó.

Trong code có thể đọc qua Environment:

~~~java
@Component
public class ConfigurationDiagnostics {

    private final Environment environment;

    public ConfigurationDiagnostics(Environment environment) {
        this.environment = environment;
    }

    public String currentBackendUrl() {
        return environment.getProperty("support.backend.base-url");
    }
}
~~~

Spring Boot Actuator cung cấp các endpoint hỗ trợ chẩn đoán:

- env: xem Environment và các PropertySource.
- configprops: xem các bean đã bind bằng ConfigurationProperties.

Các endpoint này có thể tiết lộ tên property, giá trị cấu hình hoặc metadata nhạy cảm. Chỉ bật trong môi trường cần thiết, bảo vệ bằng authentication/authorization và dùng cơ chế sanitization phù hợp. Không mở endpoint env hoặc configprops công khai cho mọi người dùng CLI.

Trong ứng dụng CLI không dùng web server, có thể tạo command diagnostics nội bộ để hiển thị một số property đã cho phép, nhưng cần ẩn token, password, private key và các giá trị bí mật khác.

Một bảng chẩn đoán hữu ích:

| Triệu chứng | Nguồn cần kiểm tra |
|---|---|
| Profile không đúng | SPRING_PROFILES_ACTIVE, JVM property, startup arguments |
| Endpoint khác file YAML | Environment variable, JVM property, command-line property |
| File ngoài không được nạp | Working directory, spring.config.location/additional-location |
| File import bị thiếu | spring.config.import và tiền tố optional |
| List bị mất phần tử | Quy tắc thay thế list giữa các nguồn |
| Bean cấu hình không có giá trị | Prefix, relaxed binding, scan/enable configuration properties |
| Ứng dụng dùng giá trị mặc định | Property name sai, nguồn không được nạp hoặc placeholder có default |

## 18. Profile không phải cơ chế phân quyền

Profile giúp chọn cấu hình hoặc bean theo môi trường. Nó không xác thực người dùng và không thay thế authorization.

Ví dụ, một profile admin có thể đăng ký command quản trị, nhưng người dùng không được phép chạy command chỉ vì process khởi động với profile admin. Nếu chức năng cần giới hạn theo danh tính, service phải kiểm tra quyền của actor tại thời điểm thực thi.

Tương tự:

- Không đặt secret trực tiếp trong application-prod.yml rồi cho rằng chỉ profile prod mới đọc được.
- Không dùng profile dev để tắt mọi kiểm tra bảo mật trong code dùng chung.
- Không xem tên profile là bằng chứng môi trường đáng tin cậy.
- Không để người dùng cuối tự chọn profile có thể bật command phá hoại mà không có authorization.

Profile là lựa chọn cấu hình do người triển khai kiểm soát. Authorization là chính sách bảo vệ tài nguyên do ứng dụng thực thi.

## 19. Một cấu hình triển khai mẫu cho Spring Shell

Giả sử ứng dụng hỗ trợ command:

~~~text
report export --format csv --output reports/daily.csv
backend status
customer search --limit 100
~~~

File application.yml:

~~~yaml
spring:
  application:
    name: support-cli

support:
  cli:
    environment-name: local
    output-directory: ./reports
    max-export-rows: 500
  backend:
    base-url: http://localhost:8081
    connect-timeout: 3s
    read-timeout: 10s
~~~

File application-staging.yml:

~~~yaml
support:
  cli:
    environment-name: staging
    output-directory: /var/lib/support-cli/staging-reports
    max-export-rows: 1500
  backend:
    base-url: https://staging-api.example.internal
~~~

Khởi chạy trên Linux:

~~~bash
SPRING_PROFILES_ACTIVE=staging \
SUPPORT_CLI_MAXEXPORTROWS=2500 \
java -jar support-cli.jar
~~~

Trong ví dụ, profile staging cung cấp endpoint và output directory. Environment variable ghi đè max-export-rows thành 2500.

Nếu cần ghi đè một lần chạy bằng JVM system property:

~~~bash
SPRING_PROFILES_ACTIVE=staging \
java -Dsupport.cli.max-export-rows=3000 -jar support-cli.jar
~~~

JVM property có ưu tiên cao hơn environment variable theo thứ tự Spring Boot, nên giá trị cuối là 3000.

Với Windows PowerShell:

~~~powershell
$env:SPRING_PROFILES_ACTIVE = 'staging'
$env:SUPPORT_CLI_MAXEXPORTROWS = '2500'
java -Dsupport.cli.max-export-rows=3000 -jar .\support-cli.jar
~~~

Hãy kiểm tra working directory nếu output-directory là đường dẫn tương đối. Giá trị ./reports được phân giải theo working directory của process, không mặc nhiên theo thư mục chứa JAR.

## 20. Kiểm thử profile và ưu tiên nguồn cấu hình

Kiểm thử cấu hình nên xác nhận cả giá trị bind lẫn hành vi của command/service.

Một số cách:

- Dùng @ActiveProfiles("test") để kích hoạt profile test.
- Dùng properties của @SpringBootTest để ghi đè property trong một test.
- Dùng @DynamicPropertySource khi cần cung cấp URL hoặc port động của dependency.
- Dùng ApplicationContextRunner cho các test cấu hình nhỏ nếu phù hợp với loại auto-configuration.

Ví dụ:

~~~java
@SpringBootTest(properties = {
        "support.cli.environment-name=test",
        "support.cli.max-export-rows=25"
})
class SupportPropertiesTests {

    @Autowired
    SupportProperties properties;

    @Test
    void bindsTestProperties() {
        assertThat(properties.environmentName()).isEqualTo("test");
        assertThat(properties.cli().maxExportRows()).isEqualTo(25);
    }
}
~~~

Với test cần kiểm tra precedence, tạo cùng một property ở nhiều nguồn rồi xác nhận nguồn có ưu tiên cao hơn thắng. Không chỉ test một file YAML riêng lẻ nếu hành vi triển khai phụ thuộc environment variable hoặc JVM property.

Ma trận test gợi ý:

| Kịch bản | Cấu hình | Kết quả mong đợi |
|---|---|---|
| Không active profile | application.yml | Dùng cấu hình chung/default |
| Active dev | application-dev.yml | Giá trị dev ghi đè cấu hình chung |
| Active prod | application-prod.yml | Giá trị prod ghi đè cấu hình chung |
| Có env variable | Env ghi đè Config Data | Env value được bind |
| Có JVM property | JVM property ghi đè env | JVM value được bind |
| Có Boot command-line property | Command-line property ghi đè nguồn thấp hơn | CLI property thắng |
| Có file external profile-specific | File ngoài profile ghi đè file trong JAR | Giá trị file ngoài được dùng |
| Import file bắt buộc bị thiếu | Không có optional prefix | Khởi động thất bại |
| Import file optional bị thiếu | Có optional prefix | Ứng dụng tiếp tục nếu các cấu hình khác hợp lệ |
| List khai báo nhiều nguồn | Nguồn ưu tiên cao có list | Toàn bộ list thấp hơn bị thay thế |

Không đưa secret thật vào test fixture. Dùng token giả và kiểm tra log/output không vô tình in giá trị nhạy cảm.

## 21. Những lỗi thường gặp

### Đã sửa application-prod.yml nhưng giá trị không thay đổi

Kiểm tra environment variable, JVM system property, SPRING_APPLICATION_JSON và command-line property. Nguồn có ưu tiên cao hơn có thể ghi đè file profile.

### Profile prod không được kích hoạt

Kiểm tra SPRING_PROFILES_ACTIVE, -Dspring.profiles.active và vị trí đặt -D trước -jar. Kiểm tra profile có bị một nguồn ưu tiên cao hơn thay thế không.

### Đặt spring.profiles.active trong application-prod.yml

Đây là vị trí không hợp lệ cho thuộc tính kích hoạt profile. Đặt active profile trong tài liệu cấu hình không phụ thuộc profile, environment variable, system property hoặc startup argument.

### Dùng spring.config.location nhưng mất cấu hình mặc định

location thay thế các vị trí tìm kiếm mặc định. Nếu chỉ muốn thêm file bên ngoài, dùng additional-location.

### File external không được nạp

Kiểm tra working directory, URL file:, dấu slash cuối khi chỉ định thư mục, quyền đọc file và tên file. Với file tùy chọn, dùng optional: có chủ đích.

### Biến môi trường không bind được

Kiểm tra tên biến theo relaxed binding: chữ hoa, dấu chấm thành underscore, bỏ dấu gạch ngang và dùng index phù hợp cho list. Kiểm tra prefix của ConfigurationProperties.

### List trong profile chỉ còn một phần tử

Đây là hành vi override list, không phải lỗi parser. List ở nguồn ưu tiên cao hơn thay thế toàn bộ list thấp hơn.

### @ConfigurationProperties bean không được tạo

Kiểm tra @ConfigurationPropertiesScan hoặc @EnableConfigurationProperties, prefix, package scan và dependency validation nếu dùng constraint.

### Giá trị default trong record không xuất hiện khi gọi Environment.getProperty

Default của object binding không nhất thiết là property thật trong Environment. Nếu cần truy vấn Environment, khai báo property default trong nguồn cấu hình hoặc placeholder tương ứng.

### Secret xuất hiện trong log diagnostics

Ẩn hoặc sanitize giá trị nhạy cảm, giới hạn quyền truy cập endpoint env/configprops và không in toàn bộ ConfigurationProperties object trong command diagnostics.

## 22. Checklist cấu hình và vận hành

- [ ] Giá trị dùng chung nằm trong application.yml hoặc application.properties.
- [ ] Mỗi môi trường chỉ ghi đè các giá trị thực sự khác biệt.
- [ ] Profile được kích hoạt rõ ràng qua deployment environment.
- [ ] Default profile không trỏ production ngoài ý muốn.
- [ ] spring.profiles.active/include/group được đặt trong tài liệu không phụ thuộc profile.
- [ ] Hiểu thứ tự ưu tiên PropertySource và Config Data.
- [ ] Đã kiểm tra biến môi trường theo relaxed binding.
- [ ] JVM system property được đặt trước -jar.
- [ ] Đã phân biệt startup properties với arguments của command Spring Shell.
- [ ] Dùng additional-location khi cần bổ sung file, location khi cần thay vị trí mặc định.
- [ ] Chỉ dùng optional: cho file thật sự không bắt buộc.
- [ ] Secret không được commit hoặc đóng gói trong JAR.
- [ ] ConfigurationProperties có kiểu dữ liệu và validation phù hợp.
- [ ] Không dùng profile làm cơ chế phân quyền.
- [ ] Diagnostics không tiết lộ password, token hoặc private key.
- [ ] Có test cho profile, environment variable, system property và precedence.

## 23. Tự kiểm tra

**Câu 1.** Spring Shell lấy cấu hình profile và biến môi trường từ đâu trong ứng dụng Spring Boot?

**Gợi ý trả lời:** Từ Spring Environment và cơ chế externalized configuration của Spring Boot; command và service cùng đọc các property đã được phân giải.

**Câu 2.** application-prod.yml có thể ghi đè application.yml không?

**Gợi ý trả lời:** Có. Khi profile prod hoạt động, file profile-specific được nạp và ghi đè giá trị tương ứng trong file chung.

**Câu 3.** Trong thứ tự ưu tiên thông thường của Spring Boot, environment variable hay JVM system property có ưu tiên cao hơn?

**Gợi ý trả lời:** JVM system property có ưu tiên cao hơn environment variable.

**Câu 4.** Biến môi trường nào tương ứng với spring.shell.interactive.enabled?

**Gợi ý trả lời:** SPRING_SHELL_INTERACTIVE_ENABLED.

**Câu 5.** Khác biệt giữa spring.config.location và spring.config.additional-location là gì?

**Gợi ý trả lời:** location thay thế vị trí tìm kiếm mặc định; additional-location bổ sung vị trí ngoài các vị trí mặc định.

**Câu 6.** Có thể đặt spring.profiles.active trong application-prod.yml không?

**Gợi ý trả lời:** Không. Thuộc tính active profile phải được khai báo trong tài liệu không phụ thuộc profile hoặc nguồn bên ngoài như environment/system property.

**Câu 7.** Nếu list được khai báo trong application.yml và application-prod.yml, các phần tử có tự merge không?

**Gợi ý trả lời:** Không. List từ nguồn ưu tiên cao hơn thay thế toàn bộ list từ nguồn thấp hơn.

**Câu 8.** Vì sao profile prod không thay thế authorization?

**Gợi ý trả lời:** Profile chỉ chọn cấu hình hoặc bean. Service vẫn phải xác thực danh tính và kiểm tra quyền trên hành động/tài nguyên tại thời điểm thực thi.

## Kết luận

Profile, biến môi trường và ưu tiên nguồn cấu hình giúp một ứng dụng Spring Shell sử dụng cùng code và artifact ở nhiều môi trường. Hãy đặt giá trị chung trong application.yml, ghi đè khác biệt bằng application-{profile}.yml và kích hoạt profile từ môi trường triển khai. Khi nhiều nguồn cùng khai báo một property, hãy dựa vào thứ tự PropertySource của Spring Boot thay vì đoán nguồn nào thắng.

Với cấu hình có cấu trúc, dùng ConfigurationProperties và validation để phát hiện giá trị sai ngay khi khởi động. Dùng environment variable hoặc JVM property cho cấu hình triển khai, additional-location/import cho file ngoài và config tree hoặc secret manager cho bí mật. Cuối cùng, kiểm thử cả profile lẫn thứ tự ghi đè trong môi trường gần với triển khai. Cách tổ chức này giúp CLI vận hành nhất quán và tránh việc một giá trị cấu hình ngoài ý muốn làm thay đổi hành vi của command.

## Tài liệu tham khảo

- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [Spring Boot — Profiles](https://docs.spring.io/spring-boot/reference/features/profiles.html)
- [Spring Boot — Properties and Configuration](https://docs.spring.io/spring-boot/how-to/properties-and-configuration.html)
- [Spring Boot — Type-safe Configuration Properties](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties)
- [Spring Framework — Environment Abstraction](https://docs.spring.io/spring-framework/reference/core/beans/environment.html)
