# Phân tích lỗi không tìm thấy vị trí hoặc tài nguyên Config Data trong Spring Boot

Khi khởi động một ứng dụng Spring Boot, đôi khi bạn gặp lỗi liên quan đến **Config Data** như:

~~~text
ConfigDataLocationNotFoundException
ConfigDataResourceNotFoundException
ConfigDataNotFoundException
~~~

Thông báo thường đi kèm một location có dạng `file:./config/custom.yml`, `classpath:/settings.yml`, `configtree:/etc/secrets/` hoặc một địa chỉ import do thư viện bên thứ ba hỗ trợ. Những lỗi này xuất hiện **rất sớm trong startup**, khi Spring Boot đang đọc cấu hình để xây dựng `Environment`, trước khi đa số `@ConfigurationProperties` và bean ứng dụng được tạo.

Đây không phải cùng loại lỗi với một property đã được nạp nhưng sai kiểu dữ liệu (ví dụ chuỗi `abc` được bind vào `int`), hoặc một bean `@Value` thiếu property. Mục tiêu của bài là phân biệt chính xác **không tìm được location**, **không tìm được resource đã phân giải**, **đọc được resource nhưng nội dung hỏng**, và **resource tồn tại nhưng property hiệu lực khác mong đợi**.

Bài học sử dụng **Spring Boot 3.3.x và Java 21**. Các thông báo lỗi bên dưới là ví dụ minh họa: văn bản exception, failure analysis và stack trace có thể khác theo phiên bản, resolver và hệ điều hành.

## 1. Luồng nạp Config Data và vị trí phát sinh lỗi

Trong Spring Boot, một phần cấu hình có thể đến từ:

- `application.properties`, `application.yml` hoặc `application.yaml` trong classpath.
- File nằm ngoài JAR, chẳng hạn `./config/application.yml`.
- Những vị trí được chỉ định bởi `spring.config.location` hoặc `spring.config.additional-location`.
- Tài nguyên được nhập qua `spring.config.import`.
- Thư mục cấu hình dạng `configtree:`, thường dùng với Kubernetes ConfigMap/Secret volume.
- Các nguồn do thư viện riêng triển khai thông qua `ConfigDataLocationResolver` và `ConfigDataLoader`.

Luồng khái niệm:

~~~text
SpringApplication.run(...)
           |
           v
Chuẩn bị Environment
           |
           v
ConfigDataEnvironmentPostProcessor
           |
           v
Xác định vị trí tìm Config Data
           |
           v
ConfigDataLocationResolver
           |
           +-- Location không tồn tại?
           |      -> ConfigDataLocationNotFoundException
           |
           v
ConfigDataResource
           |
           v
ConfigDataLoader
           |
           +-- Resource không tồn tại?
           |      -> ConfigDataResourceNotFoundException
           |
           +-- File tồn tại nhưng parse sai?
           |      -> Lỗi định dạng/đọc dữ liệu khác
           |
           v
ConfigData chứa PropertySource
           |
           v
Environment / Binding / Validation
           |
           v
ApplicationContext
~~~

**Mấu chốt:** nếu hệ thống thất bại trong giai đoạn Config Data, việc thêm một `@Bean` hoặc `@PostConstruct` để “tạo file cấu hình khi khởi động” có thể đã **quá muộn**. Thời điểm Config Data load thường đến trước việc Spring tạo các bean đó.

## 2. Hai exception chính khác nhau ra sao?

### 2.1. ConfigDataLocationNotFoundException

Tên đầy đủ:

~~~java
org.springframework.boot.context.config.ConfigDataLocationNotFoundException
~~~

Đây là subclass của `ConfigDataNotFoundException`. Nó biểu thị một **`ConfigDataLocation` không tìm thấy**. Ví dụ một cấu hình yêu cầu nạp file ở vị trí không tồn tại.

Một tình huống tái hiện:

~~~properties
spring.config.import=file:./config/missing.yml
~~~

Nếu không có file được yêu cầu, quá trình load Config Data có thể thất bại với exception thuộc nhóm not-found, trong đó có `ConfigDataLocationNotFoundException` tùy giai đoạn resolver phát hiện.

### 2.2. ConfigDataResourceNotFoundException

Tên đầy đủ:

~~~java
org.springframework.boot.context.config.ConfigDataResourceNotFoundException
~~~

Exception này cũng kế thừa `ConfigDataNotFoundException`, nhưng dùng cho trường hợp **một `ConfigDataResource` đã được phân giải mà không tìm thấy khi cần dùng**.

Ví dụ custom resolver chuyển `team-config:orders` thành resource đại diện cho document `orders`. Khi loader kiểm tra backend và document đó không tồn tại, nó có thể ném `ConfigDataResourceNotFoundException`.

Với các nguồn file chuẩn, chi tiết exception cuối cùng phụ thuộc cách resolver/loader phát hiện tài nguyên thiếu. **Đừng suy luận tuyệt đối** rằng “file thiếu luôn là LocationNotFound” hoặc “remote thiếu luôn là ResourceNotFound”: hãy đọc exception thật, location và resource được báo cáo.

### 2.3. ConfigDataNotFoundException

Đây là superclass chung của hai trường hợp trên. Nó có API mô tả thứ được tham chiếu nhưng không tìm được. Khi thấy một wrapper exception, nên tìm **root cause** hoặc subclass cụ thể.

| Lỗi | Đối tượng không tìm thấy | Hướng điều tra đầu tiên |
| --- | --- | --- |
| `ConfigDataLocationNotFoundException` | Một `ConfigDataLocation` | Địa chỉ, scheme, đường dẫn, vị trí import |
| `ConfigDataResourceNotFoundException` | Một `ConfigDataResource` | Resource đã resolve, file/backend/document thực |
| `UnsupportedConfigDataLocationException` | Không có resolver phù hợp cho location | Scheme, dependency, `spring.factories` |
| Lỗi YAML/Properties parser | Resource có thể tồn tại nhưng nội dung sai | Cú pháp, encoding, format |
| `BindException` / lỗi conversion | Property đã được tìm nhưng bind không được | Tên key, kiểu Java, giá trị |
| `BindValidationException` / validation | Giá trị có kiểu nhưng vi phạm constraint | `@Validated`, Bean Validation |

Những tên lớp cụ thể trong stack trace có thể thay đổi theo phiên bản. Bảng nhằm phân loại **giai đoạn lỗi**, không khẳng định một ngoại lệ duy nhất cho mọi tình huống.

## 3. Một lỗi missing có thể hiện ra như thế nào?

Ví dụ:

~~~yaml
spring:
  config:
    import: "file:./config/private.yml"
~~~

Khi chạy và file không tồn tại, Spring Boot thường dừng startup. Failure analysis có thể nêu:

~~~text
Description:

Config data location 'file:./config/private.yml' does not exist

Action:

Check that the value 'file:./config/private.yml' is correct,
or prefix it with 'optional:'
~~~

Đây là **nội dung minh họa** gần với cách Spring Boot diễn giải lỗi, không bảo đảm chuỗi chính xác từng chữ trong tất cả phiên bản.

Cách đọc:

1. **Location trong thông báo**: Spring Boot đang cố đọc chính xác địa chỉ nào?
2. **Nguồn đã chỉ định location**: `spring.config.import`, `spring.config.location`, `spring.config.additional-location` hay custom resolver?
3. **Bắt buộc hay tùy chọn**: location có prefix `optional:` không?
4. **Tại môi trường đang chạy**, tài nguyên có tồn tại đúng vị trí không?
5. **Kiểu tài nguyên**: file, directory, classpath, config tree hay remote?
6. **Đó thực sự là missing hay một lỗi khác**: nếu kết nối bị từ chối hoặc YAML sai cú pháp, không coi là missing chỉ vì startup thất bại.

Không nên sửa ngẫu nhiên các `@ConfigurationProperties` bean nếu log cho biết thất bại ngay trong Config Data loader.

## 4. Khi nào một file thiếu không gây lỗi?

Spring Boot có các **vị trí tìm kiếm mặc định** cho application config. Một ứng dụng không bắt buộc phải có mọi file ở mọi vị trí mặc định; việc thiếu `application.yml` ở một thư mục tìm kiếm mặc định không đồng nghĩa startup phải thất bại.

Ngược lại, khi **chỉ định một location bắt buộc tường minh**, ví dụ:

~~~bash
java -jar app.jar --spring.config.location=file:./missing/
~~~

Spring Boot có thể báo lỗi không tìm được location đó.

Sự khác biệt cần ghi nhớ:

~~~text
Không có application.yml trong một vị trí tìm mặc định
    -> Có thể hoàn toàn hợp lệ.

Đã khai báo spring.config.import=file:./must-exist.yml
nhưng file không tồn tại
    -> Có thể dừng startup.

Đã khai báo spring.config.import=optional:file:./maybe.yml
nhưng file không tồn tại
    -> Spring Boot có thể bỏ qua.
~~~

Không dùng `optional:` như một giải pháp tự động cho tất cả file. Trước hết hãy hỏi: **file này có bắt buộc để ứng dụng hoạt động đúng và an toàn không?**

## 5. Quy trình chẩn đoán ngắn theo 8 bước

Khi gặp lỗi not-found, làm theo thứ tự sau:

1. **Chụp lại exception và failure analysis gốc**; ghi rõ location/resource. Nếu thông báo có credential, che trước khi chia sẻ.
2. **Tìm property đã khai báo nguồn**: `spring.config.import`, `spring.config.location`, `spring.config.additional-location` hoặc custom scheme.
3. **Phân loại scheme**: `classpath:`, `file:`, `configtree:` hay scheme của plugin.
4. **Xác định runtime thực tế**: đang chạy Maven, Gradle, JAR, Docker, Kubernetes hay CI? Working directory và classpath có gì?
5. **Kiểm tra đúng path và đúng dạng**: file hay directory, slash cuối, extension, tên file, chữ hoa/thường.
6. **Kiểm tra profile đang active**: có biến thể `application-prod.yml` hoặc import được khai báo trong document chỉ áp dụng cho một profile không?
7. **Chọn chính sách**: sửa location nếu phải có; dùng `optional:` nếu thực sự được phép vắng mặt; tránh cấu hình bỏ qua toàn cục.
8. **Chạy lại trong cùng môi trường** và xác minh những property quan trọng thực sự có giá trị mong đợi.

Khi nói “file có tồn tại trên máy”, phải hỏi **máy nào, thư mục nào và bên trong process/container nào**. Một file trên laptop của developer không có nghĩa file đó tồn tại trong Docker image hoặc Kubernetes Pod.

## 6. Phân biệt classpath: và file:

Hai prefix dễ bị nhầm nhất:

~~~text
classpath:/config/extra.yml
file:./config/extra.yml
~~~

### classpath:

`classpath:` tìm resource trên **classpath** của ứng dụng.

Ví dụ:

~~~text
src/main/resources/config/extra.yml
~~~

sau build thường được copy vào:

~~~text
target/classes/config/extra.yml
~~~

hoặc với Gradle:

~~~text
build/resources/main/config/extra.yml
~~~

Khi đóng gói Spring Boot executable JAR, resource thuộc ứng dụng có thể nằm dưới:

~~~text
BOOT-INF/classes/config/extra.yml
~~~

Để import:

~~~yaml
spring:
  config:
    import: "classpath:/config/extra.yml"
~~~

Nếu chỉ đặt file ở `./config/extra.yml` bên ngoài JAR mà không có trên classpath, `classpath:` không tự tìm đến nó.

### file:

`file:` hướng đến đường dẫn trên filesystem của môi trường tiến trình đang chạy.

~~~yaml
spring:
  config:
    import: "file:./config/extra.yml"
~~~

`./config/extra.yml` là đường dẫn tương đối. Nó được giải quyết theo **working directory của tiến trình**, không tự động theo thư mục chứa JAR.

Ví dụ:

~~~bash
cd /opt/myapp
java -jar app.jar
~~~

thì đường dẫn tương đối thường trỏ đến:

~~~text
/opt/myapp/config/extra.yml
~~~

Nếu chạy:

~~~bash
cd /tmp
java -jar /opt/myapp/app.jar
~~~

thì `file:./config/extra.yml` lại trỏ đến:

~~~text
/tmp/config/extra.yml
~~~

Đây là nguyên nhân phổ biến của lỗi “chạy từ IDE được nhưng chạy service/cron/container thì không”.

### Bảng lựa chọn

| Tình huống | Prefix hợp lý |
| --- | --- |
| Resource đóng gói trong `src/main/resources` | `classpath:` |
| File được mount khi deploy | `file:` |
| File được cấp từ thư mục chạy | `file:./...` |
| Kubernetes Secret/ConfigMap mỗi key một file | `configtree:` |
| Nguồn cloud/config store tùy chỉnh | Scheme do extension hỗ trợ |

Không cố “sửa” bằng cách chuyển từ `file:` sang `classpath:` nếu file thực tế không được đóng gói trong artifact.

## 7. Kiểm tra resource trong JAR

Nếu khai báo:

~~~properties
spring.config.import=classpath:/config/payment.yml
~~~

nhưng gặp not-found, cần kiểm tra **artifact đang chạy**.

Với Maven:

~~~bash
./mvnw clean package
~~~

Với Gradle:

~~~bash
./gradlew clean bootJar
~~~

Liệt kê resource trong JAR thực tế:

~~~bash
jar tf target/myapp.jar
~~~

Hoặc Gradle:

~~~bash
jar tf build/libs/myapp.jar
~~~

Tìm tên:

~~~text
BOOT-INF/classes/config/payment.yml
~~~

Tên JAR `myapp.jar` chỉ là ví dụ. Thay bằng tên artifact thực tế.

Nếu file không có trong JAR:

- Kiểm tra file đã đặt ở `src/main/resources/config/payment.yml` chưa.
- Kiểm tra build tool có cấu hình exclude resource không.
- Kiểm tra module chứa resource có thực sự là dependency của ứng dụng không.
- Kiểm tra bạn chạy đúng phiên bản JAR mới build, không phải bản cache cũ.
- Nếu nằm ở `src/test/resources`, đừng mong nó tự có trong production JAR.

Nếu resource có trong JAR nhưng không được tìm thấy, kiểm tra path classpath được khai báo, chữ hoa/thường và việc dùng slash. Không sửa theo suy đoán rằng mọi JAR đều có cùng layout.

## 8. Kiểm tra working directory và file trên filesystem

### Linux/macOS

~~~bash
pwd
ls -l ./config/
ls -l ./config/extra.yml
~~~

Kiểm tra thư mục thực tế khi chạy:

~~~bash
cd /opt/myapp
java -jar app.jar --spring.config.import=file:./config/extra.yml
~~~

### Windows PowerShell

~~~powershell
Get-Location
Test-Path -LiteralPath .\config\extra.yml
Resolve-Path -LiteralPath .\config\extra.yml
~~~

Đối với Java `-jar` chạy trong Windows service, thư mục làm việc có thể khác thư mục dự án. Không chỉ kiểm tra Explorer đang hiển thị file.

### Docker

Giả sử Dockerfile đặt:

~~~dockerfile
WORKDIR /app
COPY target/app.jar app.jar
ENTRYPOINT ["java", "-jar", "app.jar"]
~~~

Và ứng dụng import `file:./config/extra.yml`. File đó cần xuất hiện trong container tại `/app/config/extra.yml`, chẳng hạn qua COPY hoặc volume:

~~~bash
docker run --rm   --mount type=bind,src=/host/config,dst=/app/config,readonly   myapp:latest
~~~

`/host/config` là đường dẫn ví dụ trên host, không phải path mặc định tồn tại trên mọi máy.

Kiểm tra trong container:

~~~bash
docker exec <container-id> sh -c 'pwd; ls -la /app/config'
~~~

Nếu image/container không có `/app/config`, Spring Boot không thể đọc resource chỉ tồn tại bên ngoài container dù host có file.

### Kubernetes

Với ConfigMap/Secret volume, xác minh:

- Pod có khai báo volume và volumeMount đúng không?
- Mount path trong container có trùng với `file:` hoặc `configtree:` không?
- Namespace và tên ConfigMap/Secret có đúng không?
- Container có quyền đọc thư mục không?
- Ứng dụng có bắt đầu trước khi tài nguyên được cấp đúng cách không?

Dùng công cụ `kubectl describe pod`/`kubectl exec` khi có quyền và đúng namespace. Không in nội dung secret vào log chỉ để chẩn đoán đường dẫn.

## 9. File và directory có cách xử lý khác nhau

`spring.config.location` cho phép khai báo **file cụ thể** hoặc **thư mục chứa application config**.

Ví dụ file:

~~~bash
java -jar app.jar --spring.config.location=file:./config/custom.yml
~~~

File `custom.yml` được tham chiếu trực tiếp, và Spring Boot có thể xét các biến thể theo profile phù hợp.

Ví dụ directory:

~~~bash
java -jar app.jar --spring.config.location=file:./config/
~~~

Với **directory location**, Spring Boot thêm tên được sinh từ `spring.config.name`, mặc định là `application`, và tìm các file có extension được hỗ trợ.

Cần có slash cuối:

~~~text
file:./config/        đúng cho directory
file:./config         không nên dùng để biểu diễn directory
~~~

Nếu file tồn tại trong `./config/custom.yml` nhưng location trỏ đến **directory** `./config/` với basename mặc định `application`, đừng mong Boot tự tìm mọi file YAML có tên bất kỳ. Có thể:

- Đổi tên thành `application.yml`.
- Đặt `spring.config.name=custom` từ nguồn bootstrap sớm.
- Hoặc tham chiếu file cụ thể bằng `file:./config/custom.yml`.

### spring.config.name

~~~bash
java -jar app.jar --spring.config.name=custom
~~~

Khi đó ứng dụng tìm các biến thể file basename `custom` ở những vị trí phù hợp. Đây là property dùng **rất sớm**, nên cấp qua môi trường, system property hoặc CLI, không đặt nó trong một file mà Boot chưa tìm được vì chính tên của file đó.

## 10. spring.config.location và spring.config.additional-location

Hai property có tác động khác nhau:

### spring.config.location

~~~bash
java -jar app.jar   --spring.config.location=optional:file:./config/
~~~

**Thay thế các vị trí tìm cấu hình mặc định** bằng danh sách do bạn cung cấp. Nếu trước đó `application.yml` được nạp từ classpath nhưng giờ bạn thay thế danh sách và không bao gồm classpath, cấu hình đó có thể không còn được nạp.

Đây là nguồn lỗi thường gặp: developer muốn “đọc thêm một file” nhưng dùng `spring.config.location`, dẫn đến vô tình bỏ vị trí mặc định.

### spring.config.additional-location

~~~bash
java -jar app.jar   --spring.config.additional-location=optional:file:./config/
~~~

**Bổ sung** location mà vẫn giữ những vị trí tìm mặc định. Các nguồn bổ sung có thể có mức ưu tiên cao hơn nguồn mặc định.

### Lưu ý về shell và escape

Trong Bash, dấu chấm phẩy `;` có ý nghĩa phân tách lệnh; nếu dùng location group separator, đặt giá trị trong dấu nháy phù hợp. Trong PowerShell, dấu nháy giúp giữ nguyên các ký tự đặc biệt của đối số.

Không sao chép một command nhiều dòng vào shell không hỗ trợ cú pháp nối dòng giống nhau. Các lệnh trên là minh họa cho Bash; Windows PowerShell có cách xuống dòng riêng.

## 11. spring.config.import: vị trí được khai báo trong một document

`spring.config.import` là cách nhập cấu hình bổ sung, ví dụ:

~~~yaml
spring:
  config:
    import: "file:./config/orders.yml"
~~~

Nếu file `orders.yml` thiếu và import bắt buộc, Spring Boot có thể dừng trước khi context khởi tạo.

Thay bằng:

~~~yaml
spring:
  config:
    import: "optional:file:./config/orders.yml"
~~~

chỉ khi file đó **thật sự được phép vắng mặt**.

### Import relative và fixed

Spring Boot phân biệt:

- **Fixed location:** có tiền tố kiểu URL như `file:`, `classpath:` hoặc bắt đầu bằng slash `/`. Không phụ thuộc nơi document import được khai báo.
- **Import-relative location:** không có fixed prefix; được giải quyết tương đối so với file đã khai báo import.

Ví dụ:

~~~text
/demo/application.properties
/demo/core/core.properties
/demo/core/extra/extra.properties
~~~

Trong `/demo/application.properties`:

~~~properties
spring.config.import=optional:core/core.properties
~~~

Khi `core.properties` có:

~~~properties
spring.config.import=optional:extra/extra.properties
~~~

địa chỉ thứ hai được resolve tương đối với thư mục chứa `core.properties`, không tự động với thư mục chứa JAR hoặc project root.

Prefix `optional:` **không quyết định** một import là fixed hay relative.

### Lỗi thường gặp

Nếu viết:

~~~properties
spring.config.import=optional:extra/extra.properties
~~~

trong một document khác với nơi bạn nghĩ, import có thể trỏ sang một thư mục khác. Cần xác định **resource cha đang khai báo import**, đặc biệt khi chuỗi import lồng nhau.

## 12. File không có extension và extension hint

Spring Boot thường nhận diện format từ extension như `.properties`, `.yml` hoặc `.yaml`. Một số volume mount trong container có file không extension, ví dụ:

~~~text
/etc/config/mysettings
~~~

Nếu file chứa YAML nhưng không có extension, import:

~~~yaml
spring:
  config:
    import: "file:/etc/config/mysettings[.yaml]"
~~~

Phần `[.yaml]` là **extension hint** cho Spring Boot biết cách đọc nội dung.

Không tự đổi tên file trên volume nếu platform bắt buộc tên không extension. Hãy dùng cú pháp hint được Spring Boot hỗ trợ.

Nếu thiếu extension và không có hint, lỗi có thể thuộc nhóm **không hỗ trợ loại resource/format**, không nhất thiết đúng là missing file. Kiểm tra exception thực tế thay vì thêm `optional:` để che lỗi.

### File có extension nhưng nội dung không đúng

Một file `config.yml` tồn tại nhưng chứa cú pháp YAML sai sẽ gây lỗi parser, không phải lỗi không tìm thấy. Tương tự, một file `config.properties` dùng định dạng không phù hợp cần được sửa nội dung.

## 13. configtree: và thư mục secret

Spring Boot hỗ trợ import một thư mục có nhiều file, trong đó **tên file trở thành key** và nội dung file trở thành value.

Ví dụ Kubernetes mount:

~~~text
/etc/config/
└── myapp/
    ├── username
    └── password
~~~

Import:

~~~yaml
spring:
  config:
    import: "configtree:/etc/config/"
~~~

Có thể tạo các property `myapp.username` và `myapp.password`.

Nếu muốn tên key chỉ là `username` và `password`, dùng:

~~~yaml
spring:
  config:
    import: "configtree:/etc/config/myapp/"
~~~

### Những lỗi cần điều tra

- Thư mục mount không tồn tại trong container.
- Dùng `file:/etc/config/` để mong nó tự convert file-name thành keys.
- Import `configtree:/etc/config/myapp` nhưng đường dẫn/mount khác với giả định.
- Volume chưa được gắn vào Pod/container đúng namespace.
- Kỳ vọng có `myapp.username` nhưng import từ thư mục con dẫn đến tên key khác.
- Secret thiếu key cần thiết, dù thư mục config tree vẫn tồn tại.

**Phân biệt:** nếu thư mục config tree tồn tại nhưng một file key cụ thể thiếu, cơ chế import thư mục có thể vẫn thành công. Khi đó lỗi có thể xuất hiện **sau** dưới dạng thiếu property hoặc validation fail. Đây không nhất thiết là Config Data location not-found.

### Optional config tree

~~~yaml
spring:
  config:
    import: "optional:configtree:/etc/config/"
~~~

Dùng khi thư mục được phép không tồn tại, ví dụ trong local development. Không nên vô tình đặt optional cho thư mục secret bắt buộc ở production.

### Wildcard config tree

~~~yaml
spring:
  config:
    import: "configtree:/etc/config/*/"
~~~

Spring Boot có thể nạp các immediate subdirectories của thư mục cha. Nếu cần thứ tự ưu tiên riêng, khai báo từng location thay vì chỉ dựa vào wildcard.

## 14. Wildcard locations: cú pháp và giới hạn

Spring Boot hỗ trợ wildcard cho một số **external filesystem locations**.

Ví dụ:

~~~text
file:./config/*/
file:/etc/myapp/*/application.yml
~~~

Quy tắc quan trọng:

- Wildcard chứa **một dấu `*`** trong một path.
- Với directory search, pattern phải kết thúc bằng `*/`.
- Với file search, có thể có dạng `*/filename`.
- Wildcard location chỉ hoạt động với **external directories**.
- Không dùng wildcard trong location `classpath:`.
- Các wildcard locations được mở rộng và sắp theo thứ tự tên đường dẫn tuyệt đối.

Cú pháp không hợp lệ hoặc không hỗ trợ có thể gây lỗi location resolution, **không phải bằng chứng tài nguyên không tồn tại**.

Nếu file nằm ở `/etc/myapp/redis/application.yml`, một wildcard `file:/etc/myapp/*/` có thể quét những thư mục con trực tiếp. Nếu bạn dùng đường dẫn sâu hơn hai cấp, pattern đó không tự đệ quy mọi thư mục lồng nhau.

## 15. Profile-specific Config Data và hiểu nhầm “thiếu file”

Khi active profile là `prod`, Spring Boot có thể xét:

~~~text
application.yml
application-prod.yml
~~~

Tùy vị trí và thứ tự ưu tiên, bản theo profile ghi đè bản chung khi cùng có key.

Ví dụ:

~~~bash
java -jar app.jar --spring.profiles.active=prod
~~~

Nếu `application-prod.yml` không tồn tại trong một vị trí tìm kiếm mặc định, **điều đó không tự động là lỗi**. Một ứng dụng có thể chỉ có `application.yml` và vẫn chạy với profile `prod` nếu các cấu hình cần thiết đã có.

### Khi profile dẫn đến một import bắt buộc

~~~yaml
# application-prod.yml
spring:
  config:
    import: "file:/etc/myapp/production-secrets.yml"
~~~

Nếu profile `prod` được bật, import mới trở nên có hiệu lực. File bí mật chưa được mount có thể gây lỗi Config Data not-found.

Với profile `dev`, document prod không được nạp, nên không phát sinh import đó theo cùng cách.

Điều tra theo thứ tự:

1. Profile nào thực sự active?
2. File/document nào khai báo `spring.config.import`?
3. Document đó có phải profile-specific hoặc được kích hoạt bằng `spring.config.activate.on-profile` không?
4. Import có cố định, tương đối hay optional?
5. Resource có tồn tại trong môi trường chạy của profile đó không?

### Multi-document YAML

~~~yaml
app:
  mode: normal

---
spring:
  config:
    activate:
      on-profile: prod
    import: "file:/etc/myapp/prod-extra.yml"
~~~

Tài liệu thứ hai chỉ tham gia khi profile `prod` phù hợp. Nếu file import thiếu chỉ gây lỗi khi bật prod, đó là kết quả hợp lý của cấu hình có điều kiện.

### Active và default profiles

Khi không có active profiles, Spring sử dụng default profiles (mặc định có tên `default`). Điều đó có thể ảnh hưởng `application-default.yml`. Đừng tự suy luận chỉ từ môi trường có chuỗi `SPRING_PROFILES_ACTIVE`; có thể còn profile được cấp từ CLI, group và configuration.

## 16. Location groups và thứ tự ưu tiên

Khi sử dụng nhiều vị trí:

~~~bash
java -jar app.jar   --spring.config.location=classpath:/cfg/,classpath:/ext/
~~~

các location được xử lý theo thứ tự, với những location sau có thể ghi đè giá trị từ location trước.

Spring Boot cũng có **location groups**, phân tách bằng dấu chấm phẩy `;`:

~~~bash
java -jar app.jar   '--spring.config.location=classpath:/cfg/;classpath:/ext/'
~~~

Group làm thay đổi cách mức ưu tiên và các file theo profile được xử lý. Một giá trị cuối không như mong đợi có thể do order/group chứ không phải file bị thiếu.

**Lỗi not-found và lỗi precedence là hai chuyện khác nhau:**

- Nếu Spring Boot báo không tìm thấy file, kiểm tra địa chỉ tồn tại.
- Nếu không có lỗi mà key lại nhận giá trị từ nguồn khác, kiểm tra property source order, profile và group.

Không lạm dụng `optional:` để xử lý vấn đề thứ tự ưu tiên.

## 17. spring.config.on-not-found=ignore là gì?

Spring Boot cung cấp lựa chọn xử lý các lỗi Config Data not-found ở phạm vi rộng:

~~~properties
spring.config.on-not-found=ignore
~~~

Tài liệu Spring Boot 3.3 nêu cách đặt property này **từ nguồn có sẵn rất sớm**, ví dụ:

~~~bash
java -Dspring.config.on-not-found=ignore -jar app.jar
~~~

Hoặc dùng biến môi trường:

~~~bash
export SPRING_CONFIG_ON_NOT_FOUND=ignore
java -jar app.jar
~~~

Hoặc thiết lập programmatically qua `SpringApplication.setDefaultProperties(...)` trước khi chạy.

### Vì sao không nên mặc định dùng?

Nó có thể che giấu nhiều lỗi location không tìm thấy thay vì chỉ cho phép một nguồn cụ thể vắng mặt. Ở production, điều này nguy hiểm khi nguồn bị bỏ qua lại chứa:

- Database URL.
- Credential hoặc signing secret.
- Danh sách endpoint quan trọng.
- Chính sách thanh toán hoặc giới hạn giao dịch.
- Cấu hình bảo mật.
- Giá trị bắt buộc cho một profile.

**Ưu tiên `optional:` cho từng địa chỉ được phép thiếu**, thay vì bật bỏ qua toàn cục.

### Không coi ignore là giải pháp cho mọi startup error

Ngay cả khi cấu hình bỏ qua not-found, lỗi YAML sai cú pháp, giá trị cấu hình không hợp lệ, lỗi conversion/validation hoặc lỗi ứng dụng vẫn có thể làm startup thất bại.

Property này không làm Spring Boot tự tạo file còn thiếu. Nó chỉ tác động đến cách xử lý một loại lỗi được hỗ trợ.

## 18. optional: có thể dùng ở đâu?

Theo tài liệu Spring Boot 3.3, prefix `optional:` dùng được với:

- `spring.config.import`.
- `spring.config.location`.
- `spring.config.additional-location`.

Ví dụ import:

~~~yaml
spring:
  config:
    import: "optional:file:./local-dev.yml"
~~~

Ví dụ CLI:

~~~bash
java -jar app.jar   --spring.config.additional-location=optional:file:./overrides/
~~~

Ví dụ nhiều location:

~~~properties
spring.config.import=optional:file:./a.yml,optional:file:./b.yml
~~~

**Prefix đặt trước mỗi location tùy chọn.** Nếu danh sách có một location bắt buộc, đừng giả định `optional:` ở location đầu tiên tự áp dụng cho toàn bộ danh sách.

### Khi nào nên dùng?

- Một local override file dành cho lập trình viên.
- Cấu hình bổ sung chỉ được mount ở một số môi trường.
- Secret/configtree hoàn toàn không cần thiết khi một module được tắt bằng cấu hình an toàn.
- Tài nguyên profile-specific thực sự không bắt buộc.

### Khi nào không nên dùng?

- File bắt buộc chứa thông tin xác thực production.
- Cấu hình cơ sở dữ liệu cần có để đảm bảo dữ liệu giao dịch.
- File chứa chính sách bảo mật bắt buộc.
- Remote configuration nguồn sự thật duy nhất nhưng hiện không truy cập được.
- Tình huống lỗi là 403, parse error hoặc cấu hình sai thay vì missing.

## 19. Đối chiếu thông báo lỗi với nguyên nhân thường gặp

| Triệu chứng | Nguyên nhân có thể | Việc làm đầu tiên |
| --- | --- | --- |
| Không tìm thấy `classpath:/config/extra.yml` | Resource không nằm trên classpath/JAR | Xem `src/main/resources` và `jar tf` |
| Không tìm thấy `file:./config/extra.yml` | Sai working directory | Kiểm tra `pwd`, `Get-Location` |
| Không tìm thấy `file:/etc/app/extra.yml` | File không được mount hoặc sai path | Kiểm tra trong container |
| Không tìm thấy directory với `spring.config.location` | Thiếu slash cuối hoặc directory không tồn tại | Dùng `file:./config/` và kiểm tra |
| Không nhận scheme `remote:` | Thiếu resolver/plugin dependency | Kiểm tra classpath và `spring.factories` |
| Chạy dev được, prod lỗi | Import chỉ tồn tại trong document prod | Kiểm tra profile và mounts |
| File có nhưng Boot vẫn báo lỗi | Path case, extension, artifact cũ | Kiểm tra path chính xác và JAR |
| Không có lỗi nhưng property thiếu | File chưa được nạp hoặc key sai | Kiểm tra prefix, profile, precedence |
| Có lỗi parser YAML | Nội dung file sai | Sửa YAML, không thêm optional |
| Không mở được file do quyền | Permission hoặc chính sách bảo mật | Kiểm tra quyền/owner, không giả missing |
| Config tree tồn tại nhưng secret key thiếu | File key trong tree không có | Kiểm tra tên file và Bean Validation |
| Location có wildcard classpath | Loại wildcard không được hỗ trợ | Dùng file location đúng hoặc chỉ định tường minh |

Hãy tránh nhảy ngay đến kết luận “đường dẫn sai” khi thông báo có thể bắt nguồn từ một custom resolver hoặc thiếu dependency hỗ trợ scheme.

## 20. Một ví dụ phân tích lỗi từ đầu đến cuối

### Tình huống

Trong `application.yml`:

~~~yaml
spring:
  config:
    import: "file:./config/credentials.yml"

app:
  remote:
    enabled: true
~~~

Ứng dụng chạy:

~~~bash
cd /srv/app
java -jar build/app.jar
~~~

Nhưng file thật nằm ở:

~~~text
/srv/app/secrets/credentials.yml
~~~

### Phân tích

1. `file:./config/credentials.yml` được resolve theo working directory `/srv/app`.
2. Đường dẫn mà Spring Boot tìm là `/srv/app/config/credentials.yml`.
3. File thực tế `/srv/app/secrets/credentials.yml`, nên không khớp.
4. Vì import bắt buộc, startup báo lỗi not-found.
5. Cách sửa là chỉnh import thành `file:./secrets/credentials.yml` hoặc mount file vào path đã được khai báo.

### Không nên sửa

~~~yaml
spring:
  config:
    import: "optional:file:./config/credentials.yml"
~~~

nếu credential thực sự bắt buộc. Làm vậy chỉ che lỗi đường dẫn; service vẫn có thể thất bại muộn hơn hoặc sử dụng dữ liệu mặc định không an toàn.

### Cách khắc phục tốt hơn

Đặt location đúng và giữ tính bắt buộc:

~~~yaml
spring:
  config:
    import: "file:./secrets/credentials.yml"
~~~

Sau đó test lại với đúng working directory, quyền đọc file và loại profile.

## 21. Ví dụ classpath bị thiếu sau khi đóng gói JAR

### Tình huống

Resource trong project:

~~~text
src/test/resources/config/mock-clients.yml
~~~

Application production:

~~~yaml
spring:
  config:
    import: "classpath:/config/mock-clients.yml"
~~~

Test chạy qua IDE có thể nhìn thấy resource trên test classpath. Nhưng production JAR không chứa `src/test/resources`, dẫn đến not-found.

### Cách sửa

Nếu file thực sự là cấu hình ứng dụng, đưa nó vào:

~~~text
src/main/resources/config/mock-clients.yml
~~~

và đóng gói lại. Nếu chỉ dành cho test, **không import nó trong cấu hình production**. Thay vào đó chỉ import trong `application-test.yml` hoặc dùng test-specific mechanism khi profile test hoạt động.

Ví dụ:

~~~yaml
# src/test/resources/application-test.yml
spring:
  config:
    import: "classpath:/config/mock-clients.yml"
~~~

Test class:

~~~java
@SpringBootTest
@ActiveProfiles("test")
class ClientIntegrationTest {
}
~~~

Những file ở `src/test/resources` có thể được tìm trong test classpath, nhưng không mặc định có trong production artifact.

## 22. Một lỗi liên quan sai tên file theo profile

### Tình huống

Developer đặt file:

~~~text
src/main/resources/application-production.yml
~~~

nhưng chạy:

~~~bash
java -jar app.jar --spring.profiles.active=prod
~~~

Spring Boot tìm biến thể `application-prod.yml` theo quy ước profile `prod`, không tự suy ra `prod` tương đương `production`.

Khi file profile-specific không được tự nạp, các key trong đó vắng mặt. Điều này **có thể không sinh ConfigDataNotFoundException**, vì Spring Boot không nhất thiết yêu cầu file profile tồn tại.

### Chẩn đoán

- Kiểm tra active profile thực tế.
- So tên file và profile.
- Xem có `spring.config.import` trong một document theo profile không.
- Kiểm tra property value hiệu lực trong Environment (không in secret).

### Cách sửa

Chọn một quy ước nhất quán:

~~~text
Profile: prod
File: application-prod.yml
~~~

Hoặc đổi profile được kích hoạt thành `production` nếu toàn bộ cấu hình thực sự sử dụng tên đó.

## 23. Nguồn Config Data tùy chỉnh và phân loại lỗi

Spring Boot cho phép thư viện triển khai:

~~~java
ConfigDataLocationResolver<R extends ConfigDataResource>
ConfigDataLoader<R extends ConfigDataResource>
~~~

Ví dụ:

~~~yaml
spring:
  config:
    import: "team-config:orders"
~~~

Resolver phải:

1. Nhận diện `team-config:` qua `isResolvable(...)`.
2. Chuyển địa chỉ thành resource qua `resolve(...)`.
3. Nếu hỗ trợ profile, tạo resource thích hợp qua `resolveProfileSpecific(...)`.

Loader phải:

1. Kiểm tra có thể nạp loại resource qua `isLoadable(...)` khi cần.
2. Thực hiện `load(...)` để trả `ConfigData`.

Nếu resolver không đăng ký hoặc không nhận scheme, lỗi có thể là **UnsupportedConfigDataLocationException**, không phải resource not-found. Prefix `optional:` không thể bù việc thiếu implementation hỗ trợ location.

Nếu resolver nhận scheme nhưng backend không chứa document, loader có thể ném `ConfigDataResourceNotFoundException` theo ngữ nghĩa.

### Ví dụ xử lý missing trong custom loader

~~~java
@Override
public ConfigData load(
        ConfigDataLoaderContext context,
        TeamConfigResource resource) throws IOException {

    TeamDocument document = client.fetch(resource.id());

    if (document == null) {
        throw new ConfigDataResourceNotFoundException(resource);
    }

    Map<String, Object> values = document.toPropertyMap();

    return new ConfigData(List.of(
            new MapPropertySource("team-config[" + resource.id() + "]",
                    values)));
}
~~~

`TeamConfigResource`, `TeamDocument` và `client` là các abstraction tự định nghĩa, không phải API có sẵn của Spring Boot; snippet minh họa nguyên tắc xử lý.

### Đừng đổi tất cả lỗi thành not-found

Sai về mặt thiết kế:

~~~java
try {
    return loadFromRemote();
} catch (Exception ex) {
    throw new ConfigDataResourceNotFoundException(resource, ex);
}
~~~

Một request remote có thể lỗi do:

- HTTP 401: token sai/hết hạn.
- HTTP 403: không có quyền truy cập.
- HTTP 429: bị giới hạn tốc độ.
- HTTP 500/503: backend không sẵn sàng.
- Network timeout.
- Response sai schema.

Những lỗi này khác với “document không tồn tại”. Nếu tất cả bị gói thành not-found, `optional:` hoặc chính sách ignore có thể che sự cố hạ tầng và bảo mật. Cần phân loại và xử lý theo hợp đồng nguồn dữ liệu thực tế.

## 24. Debug logs cho Config Data

Để quan sát startup, Spring Boot hỗ trợ log theo package:

~~~bash
java -jar app.jar   --logging.level.org.springframework.boot.context.config=TRACE
~~~

Có thể thêm:

~~~bash
java -jar app.jar --debug
~~~

`--debug` bật một số báo cáo chẩn đoán của Spring Boot, nhưng không có nghĩa mọi hành động của Config Data đều được in chi tiết. Khi cần theo dõi location resolution, log level của package `org.springframework.boot.context.config` thường là điểm bắt đầu cụ thể hơn.

**Cần lưu ý:** lỗi xảy ra ở giai đoạn rất sớm khi logging chưa hoàn tất setup; lượng log cụ thể phụ thuộc phiên bản, môi trường và đường khởi động.

Trong production, không nên bật TRACE bừa bãi nếu log có thể chứa location bí mật, property values hoặc quá nhiều thông tin hạ tầng. Khi gửi log để hỗ trợ, che credential, token và đường dẫn nhạy cảm nếu cần.

### Đọc log theo trình tự

Hãy tập trung vào:

1. Dòng nào báo import/location đang được xử lý.
2. Root exception thuộc nhóm nào.
3. Location và resource được tham chiếu.
4. Có cờ optional hay không.
5. Có profile-specific resolution hay không.
6. Failure analysis đề xuất hành động gì.

Đừng bỏ qua nguyên nhân cuối chỉ vì phía trên stack trace có rất nhiều lớp của SpringApplication.

## 25. Dùng Environment để xác minh sau khi sửa

Khi ứng dụng đã khởi động, có thể dùng `ApplicationRunner` để kiểm tra một giá trị **không nhạy cảm**:

~~~java
package com.example.configdemo;

import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;

@Configuration(proxyBeanMethods = false)
public class ConfigDebugConfiguration {

    @Bean
    ApplicationRunner inspectEnvironment(Environment environment) {
        return args -> {
            String origin = environment.getProperty("demo.origin");
            System.out.println("demo.origin=" + origin);
        };
    }
}
~~~

Nếu import đã được nạp và chứa `demo.origin`, giá trị sẽ được đọc từ Environment theo thứ tự ưu tiên.

**Đừng in password, token hoặc toàn bộ các PropertySource** chỉ để kiểm tra một import. Với secrets, có thể chỉ xác nhận **sự hiện diện** hoặc trạng thái validation, không ghi giá trị thực.

### Actuator

Nếu dự án bật Spring Boot Actuator, endpoint `env` hoặc `configprops` có thể hỗ trợ tìm nguồn property sau startup, với điều kiện quyền truy cập và cơ chế che dữ liệu nhạy cảm được cấu hình phù hợp.

Nếu startup thất bại từ giai đoạn Config Data, Actuator chưa có cơ hội hoạt động. Khi đó ưu tiên log bootstrap và kiểm tra filesystem/classpath.

## 26. Property tồn tại nhưng bị ghi đè: không phải lỗi not-found

Ví dụ:

`application.yml`:

~~~yaml
app:
  worker:
    count: 4
~~~

`extra.yml`:

~~~yaml
app:
  worker:
    count: 8
~~~

Khi import `extra.yml`, dữ liệu import có thể được ưu tiên so với document khai báo import.

Nhưng nếu chạy:

~~~bash
java -jar app.jar --app.worker.count=20
~~~

giá trị cuối có thể là 20 do CLI có mức ưu tiên cao hơn Config Data thông thường.

Nếu test chỉ nhìn `count=20` rồi cho rằng import không chạy, kết luận đó có thể sai. Hãy tách hai câu hỏi:

- **Resource được nạp thành công chưa?**
- **Giá trị hiệu lực sau tất cả các nguồn là gì?**

Một resource có thể được nạp thành công nhưng property bị nguồn khác ghi đè.

## 27. Sai path hay sai quyền đọc?

Không phải mọi sự cố mở file đều là “không tồn tại”. Ví dụ trên Linux:

~~~bash
ls -l /etc/myapp/config.yml
~~~

file có thể tồn tại nhưng tiến trình Java không có quyền đọc. Nguyên nhân gốc có thể là `AccessDeniedException`, `FileSystemException` hoặc exception phù hợp khác.

Hãy kiểm tra:

- User/UID của process Java.
- Quyền của file và tất cả thư mục cha.
- Security context của container/Pod.
- Mount read-only có ảnh hưởng đọc không (đọc file read-only thường vẫn hợp lệ).
- SELinux/AppArmor hoặc chính sách filesystem nếu môi trường áp dụng.
- Đường dẫn có symlink trỏ đến target vắng mặt không.

Đừng tự thêm `optional:` khi file tồn tại nhưng không đọc được. Việc đó không khắc phục vấn đề quyền và có thể tạo hành vi khó đoán nếu exception bị phân loại khác với missing.

## 28. Lỗi YAML sai và placeholder chưa được giải quyết

### YAML sai

Ví dụ:

~~~yaml
app:
  client:
    timeout: [1s
~~~

File có thể tồn tại, nhưng cú pháp YAML không hợp lệ. Lỗi parser ở giai đoạn Config Data không được khắc phục chỉ bằng `optional:`.

### Placeholder thiếu

Ví dụ:

~~~yaml
app:
  client:
    endpoint: "${REMOTE_ENDPOINT}"
~~~

File vẫn được nạp nhưng khi một bean truy vấn property này, placeholder có thể không được resolve theo mong muốn và gây lỗi sau đó.

Vấn đề ở đây không phải location/resource missing mà là **giá trị** hoặc **phụ thuộc cấu hình** không được cung cấp. Có thể sử dụng placeholder default khi hợp lý:

~~~yaml
app:
  client:
    endpoint: "${REMOTE_ENDPOINT:http://localhost:8080}"
~~~

Nhưng với credential hoặc production endpoint bắt buộc, default không an toàn có thể che lỗi cấu hình. Chọn cơ chế validation để fail fast nếu dữ liệu phải hiện diện.

## 29. Cách tái hiện và kiểm thử missing Config Data

Một bộ thử nghiệm thủ công rất hữu ích khi cần kiểm chứng chính sách.

### Trường hợp A: import bắt buộc bị thiếu

Tạo `application.yml`:

~~~yaml
spring:
  config:
    import: "file:./not-existing-demo.yml"
~~~

Đảm bảo file `not-existing-demo.yml` không tồn tại trong working directory, rồi chạy ứng dụng.

**Kỳ vọng:** Spring Boot báo lỗi not-found và dừng, nếu không có cấu hình bỏ qua rộng hơn.

### Trường hợp B: import tùy chọn bị thiếu

~~~yaml
spring:
  config:
    import: "optional:file:./not-existing-demo.yml"
~~~

**Kỳ vọng:** riêng việc thiếu file không làm startup thất bại. Bean/application khác vẫn có thể thất bại nếu cần property bắt buộc do file ấy cung cấp.

### Trường hợp C: import bắt buộc tồn tại

Tạo file `local-extra.yml`:

~~~yaml
demo:
  origin: local-extra
~~~

Import:

~~~yaml
spring:
  config:
    import: "file:./local-extra.yml"
~~~

**Kỳ vọng:** resource được nạp, có thể đọc `demo.origin=local-extra` nếu không bị nguồn cao hơn ghi đè.

### Trường hợp D: biến thể theo profile

Tạo:

~~~text
src/main/resources/application.yml
src/main/resources/application-dev.yml
~~~

Chạy `--spring.profiles.active=dev` rồi kiểm tra các property được dự kiến từ bản dev. Nếu `application-dev.yml` bị bỏ, kiểm tra có lỗi missing hay chỉ trở về giá trị từ file chung.

### Trường hợp E: classpath mismatch

Đặt `extra.yml` tại `src/test/resources` nhưng import `classpath:/extra.yml` trong cấu hình production. So sánh kết quả chạy test với chạy packaged JAR và quan sát khác biệt classpath.

## 30. Tự động hóa kiểm thử bằng chạy process thật

Vì Config Data được xử lý rất sớm, thử nghiệm **toàn bộ bootstrap** đáng tin cậy hơn việc chỉ unit-test một `@ConfigurationProperties` bean.

Một kịch bản CI có thể:

1. Build executable JAR.
2. Tạo một thư mục test sạch.
3. Chạy JAR với `--spring.config.import=file:./missing.yml`.
4. Xác nhận exit code khác 0 và log có nhóm not-found.
5. Chạy lại với `optional:file:./missing.yml`.
6. Xác nhận lỗi missing không còn là nguyên nhân dừng.
7. Tạo `missing.yml` có một property sentinel.
8. Chạy import bắt buộc lần nữa.
9. Xác nhận ứng dụng thấy sentinel, không in secret.
10. Chạy với profile `dev` và kiểm tra biến thể.

Không nên chỉ assert một chuỗi exception nguyên văn, vì thông điệp có thể đổi theo patch version. Tập trung vào hành vi: **fail fast khi bắt buộc thiếu, tiếp tục khi optional thiếu, nạp đúng khi resource tồn tại**.

### TestContext và @SpringBootTest

`@SpringBootTest` khởi động Spring context cho integration test. Tuy nhiên, thuộc tính `spring.config.import` cần có mặt từ **giai đoạn bootstrap Config Data**; một property thêm quá muộn có thể không tác động như bạn mong muốn.

Đối với tests cần kiểm chứng hành vi của `spring.config.location`, `spring.config.name` và discovery của custom resolver, hãy dùng startup command/system property hoặc một test harness thật sự kiểm soát giai đoạn Environment preparation thay vì chỉ gọi `Environment.setProperty` sau khi context đã tạo.

## 31. Một sơ đồ quyết định để xử lý nhanh

~~~text
Spring Boot startup thất bại
             |
             v
Có ConfigData...NotFoundException?
   | yes                              | no
   v                                  v
Xem location / resource       Phân tích lỗi khác:
   |                          parser, bind, validation,
   v                          permission, unsupported...
Scheme là gì?
   |
   +-- classpath: -> Kiểm tra JAR/classpath/resources
   |
   +-- file:      -> Kiểm tra working dir, path, mount
   |
   +-- configtree: -> Kiểm tra thư mục volume, key files
   |
   +-- custom:    -> Kiểm tra resolver/loader/backend
   |
   v
Tài nguyên có thật sự được phép thiếu?
   | yes                             | no
   v                                 v
Thêm optional: đúng location  Sửa path/mount/build/dependency
   |                                 |
   +---------------+-----------------+
                   |
                   v
Chạy lại đúng môi trường
                   |
                   v
Kiểm tra property hiệu lực/validation
~~~

Nếu classpath resource chưa có trong JAR, việc sửa import thành optional có thể khiến ứng dụng chạy nhưng thiếu dữ liệu. Nếu file bị mount sai, sửa mount là hành động đúng hơn. Nếu remote trả 403, cần sửa quyền, không gọi nó là missing.

## 32. Những quy tắc cần nhớ khi đưa vào production

1. **Fail fast với cấu hình bắt buộc.** Nếu thiếu secret/database URL hoặc policy cần thiết, startup lỗi rõ ràng thường tốt hơn chạy nửa vời.
2. **Chỉ optional đúng nguồn được phép thiếu.** Dùng `optional:` ở location cụ thể, không mở ignore toàn cục vô điều kiện.
3. **Đảm bảo path là path của runtime.** Container/CI/service có filesystem và working directory khác laptop.
4. **Phân biệt classpath và filesystem.** Resource trong `src/test/resources` không mặc định có trong production JAR.
5. **Thống nhất profile và tên file.** `prod` không đồng nghĩa `production`; profile-specific file thiếu không nhất thiết gây not-found.
6. **Không gộp các lỗi khác nhau.** Parsing, conversion, validation, auth, permission và not-found cần hướng xử lý khác.
7. **Giữ log an toàn.** Không log nội dung Secret/ConfigMap hoặc URL chứa credentials.
8. **Kiểm tra thứ tự ưu tiên.** Import có thể thành công nhưng giá trị hiệu lực bị source khác ghi đè.
9. **Có kiểm thử missing/optional.** Không chỉ test happy path.
10. **Không phụ thuộc bean tạo file quá muộn.** Config Data chạy trước phần lớn application beans.

## 33. Bài tập thực hành

### Bài 1 — Phân biệt location và resource

Giải thích vì sao `ConfigDataLocationNotFoundException` và `ConfigDataResourceNotFoundException` đều thuộc `ConfigDataNotFoundException` nhưng diễn đạt hai giai đoạn khác nhau.

**Đáp án:** location là địa chỉ cần phân giải; resource là đối tượng nguồn cụ thể đã được resolver xác định để loader tải.

### Bài 2 — Classpath

File nằm tại `src/main/resources/config/rules.yml`. Viết import đúng và kiểm tra đường dẫn trong executable JAR.

**Đáp án:** `classpath:/config/rules.yml`; kiểm tra bằng `jar tf`.

### Bài 3 — File tương đối

Ứng dụng chạy từ `/tmp` nhưng JAR nằm ở `/opt/app`. `file:./config/extra.yml` trỏ vào đâu?

**Đáp án:** thư mục `/tmp/config/extra.yml` theo working directory, không tự trỏ đến thư mục chứa JAR.

### Bài 4 — Directory

File cần đọc có tên `custom.yml` trong `./config/`. Với `spring.config.location=file:./config/` và `spring.config.name` mặc định, tại sao không chắc file được nạp?

**Đáp án:** directory search thường tìm basename `application`; cần file cụ thể, đổi tên hoặc cung cấp `spring.config.name=custom` đúng thời điểm.

### Bài 5 — Optional và bắt buộc

Một file `dev-overrides.yml` có thể không tồn tại trên CI. Một file `prod-secrets.yml` bắt buộc phải có trên production. Hãy thiết kế hai location và giải thích vì sao chỉ file đầu nên optional.

### Bài 6 — Extension hint

Một volume có file `/etc/config/appsettings` không có extension nhưng nội dung là YAML. Viết cú pháp import có hint.

**Đáp án:** `file:/etc/config/appsettings[.yaml]`.

### Bài 7 — Config tree

Một volume chứa `/run/secrets/db.password`. Cần đọc key `db.password`. Dùng scheme nào?

**Đáp án:** `configtree:/run/secrets/`, với volume và quyền đọc được cấu hình đúng.

### Bài 8 — Sai profile

File có tên `application-production.yml` nhưng active profile là `prod`. Cách chẩn đoán? Vì sao không nhất thiết xuất hiện ConfigDataNotFoundException?

### Bài 9 — Remote config

Một `ConfigDataLoader` gọi remote API trả HTTP 403. Có nên chuyển thành `ConfigDataResourceNotFoundException` không?

**Đáp án:** không; cần xử lý lỗi authorization thay vì giả tài nguyên không tồn tại.

### Bài 10 — Kiểm tra ưu tiên

Import cung cấp `app.worker.count=5`, nhưng CLI có `--app.worker.count=20`. Tại sao ứng dụng nhận 20 không chứng minh import bị thiếu?

**Đáp án:** property sources có thứ tự ưu tiên; CLI có thể ghi đè giá trị Config Data.

### Bài 11 — File thiếu nhưng ứng dụng vẫn chạy

Một ứng dụng không có `application-prod.yml` nhưng active profile prod. Có nhất thiết lỗi không?

**Đáp án:** không, profile-specific file ở các vị trí tìm mặc định không nhất thiết bắt buộc tồn tại. Lỗi có thể đến từ một import rõ ràng chỉ được kích hoạt trong prod.

### Bài 12 — Đọc log

Tạo một location không tồn tại, chạy ứng dụng và xác định ba dữ kiện: source property đã khai báo location, đường dẫn runtime được dùng, và lỗi nằm ở location resolution hay resource loading.

## 34. Tổng kết

Khi Spring Boot báo lỗi không tìm thấy Config Data, **đừng chỉ nhìn thấy chữ “missing” rồi thêm `optional:`**. Trước hết hãy phân biệt:

- **`ConfigDataLocationNotFoundException`**: địa chỉ Config Data không tìm thấy.
- **`ConfigDataResourceNotFoundException`**: tài nguyên đã được phân giải không tìm thấy.
- **`UnsupportedConfigDataLocationException`**: không có cách xử lý location/scheme phù hợp.
- **Lỗi parse, permission, conversion hoặc validation**: khác về nguyên nhân và hướng sửa.

Công cụ chẩn đoán hữu ích nhất là **location gốc + môi trường chạy thực + quy tắc ưu tiên Config Data + profile**. Kiểm tra classpath/JAR nếu dùng `classpath:`, filesystem và working directory nếu dùng `file:`, volume mount nếu dùng `configtree:`, và resolver/loader/backend nếu dùng custom scheme.

Dùng `optional:` cho tài nguyên thật sự không bắt buộc; hạn chế `spring.config.on-not-found=ignore` vì nó có thể che cấu hình thiếu ở nhiều nơi. Sau khi sửa, chạy lại trong môi trường tương đương production và xác nhận property cần thiết có giá trị hợp lệ, thay vì chỉ kết luận “ứng dụng đã hết exception”.

## Tài liệu tham khảo

- [Spring Boot 3.3 — Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html)
- [Spring Boot 3.3 — ConfigDataLocationNotFoundException API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/config/ConfigDataLocationNotFoundException.html)
- [Spring Boot 3.3 — ConfigDataResourceNotFoundException API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/config/ConfigDataResourceNotFoundException.html)
- [Spring Boot 3.3 — ConfigDataNotFoundException API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/config/ConfigDataNotFoundException.html)
- [Spring Boot 3.3 — ConfigDataEnvironmentPostProcessor API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/config/ConfigDataEnvironmentPostProcessor.html)
- [Spring Boot 3.3 — ConfigDataLocationResolver API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/config/ConfigDataLocationResolver.html)
- [Spring Boot 3.3 — ConfigDataLoader API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/config/ConfigDataLoader.html)
