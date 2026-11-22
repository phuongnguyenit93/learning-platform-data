# Tài nguyên cần restart, tài nguyên loại trừ và trigger file

Trong quá trình phát triển một ứng dụng Spring Boot, chúng ta thường phải sửa Java class, file YAML, template HTML, CSS hoặc JavaScript rồi kiểm tra kết quả. Nếu mỗi lần thay đổi đều phải dừng JVM và khởi động thủ công, vòng lặp phát triển sẽ chậm, nhất là khi ứng dụng có nhiều bean, repository, security configuration và kết nối hạ tầng.

**Spring Boot DevTools** hỗ trợ vòng lặp phát triển ngắn hơn bằng cách theo dõi các thay đổi ở những đường dẫn thích hợp và tự **restart ApplicationContext** khi cần. Tuy nhiên, không phải mọi thay đổi đều phải khởi tạo lại ứng dụng. Thay một service Java khác với thay một file CSS hoặc template. DevTools vì vậy có các cơ chế:

- **Tài nguyên cần restart:** thay đổi đủ quan trọng để phải tạo lại application context và nạp lại class.
- **Tài nguyên loại trừ khỏi restart:** thay đổi có thể phục vụ trực tiếp hoặc cập nhật trình duyệt mà không cần khởi động lại toàn bộ context.
- **Đường dẫn theo dõi bổ sung:** thông báo cho DevTools về tài nguyên nằm ngoài những classpath directories thông thường.
- **Trigger file:** một file đóng vai trò công tắc; chỉ khi chủ động cập nhật file này, các thay đổi đang chờ mới dẫn đến restart theo cơ chế DevTools.

Để dùng đúng, cần hiểu **DevTools quan sát những file nào**, **IDE/build tool có đưa thay đổi vào runtime classpath chưa**, và **khác biệt giữa restart, LiveReload và tự làm mới giao diện**.

Bài học tập trung vào các property như `spring.devtools.restart.exclude`, `spring.devtools.restart.additional-exclude`, `spring.devtools.restart.additional-paths` và `spring.devtools.restart.trigger-file`, cùng ví dụ Maven, Gradle, IDE, multi-module và những lỗi thường gặp.

## 1. DevTools là công cụ dành cho vòng lặp phát triển

Spring Boot DevTools là một tập tiện ích hỗ trợ development. Một khả năng đáng chú ý là **automatic restart**: khi các file được theo dõi thay đổi, DevTools đóng application context hiện tại, tạo lại context và sử dụng cơ chế classloader thích hợp để nạp phiên bản class mới.

Ví dụ vòng lặp:

~~~text
Sửa OrderService.java
        |
        v
IDE hoặc build tool biên dịch
        |
        v
OrderService.class trong output directory thay đổi
        |
        v
DevTools phát hiện thay đổi trên classpath
        |
        v
Đóng context cũ, tạo context mới
        |
        v
Ứng dụng chạy với code đã thay đổi
~~~

Điểm quan trọng: DevTools **không phải compiler**. Nó không tự biến file `.java` đang sửa thành bytecode. Nếu IDE chưa biên dịch hoặc output classes chưa đổi, DevTools có thể chưa thấy lý do để restart.

### Restart không phải khởi động lại JVM từ đầu

Trong một đợt restart thông thường, JVM đang chạy được giữ lại, còn các thành phần phù hợp của Spring application được tạo lại. DevTools sử dụng cơ chế nhiều classloader nhằm giảm chi phí nạp lại thư viện không đổi.

Điều này khác với:

~~~text
Dừng java process
        |
        v
Khởi động một java process mới
        |
        v
Nạp toàn bộ JVM, classpath, framework và ứng dụng
~~~

Nhờ giữ JVM và những thư viện nền không cần nạp lại trong mỗi lượt, restart có thể nhanh hơn một lần khởi động lạnh. Nhưng nó không có nghĩa mọi trạng thái runtime đều được reset hoàn hảo: static state của class thuộc base classloader hoặc tài nguyên không được dọn đúng có thể tạo khác biệt so với chạy process mới.

### DevTools chỉ nên dùng khi phát triển

Auto restart và các tiện ích DevTools không phải một cơ chế hot deployment production. Trong ứng dụng đóng gói hoàn chỉnh, Spring Boot thường vô hiệu hóa cơ chế DevTools phù hợp với môi trường packaged application; đồng thời cần cấu hình dependency để không vô tình lan truyền DevTools sang sản phẩm deploy.

Production nên sử dụng quy trình deploy, restart và health checks chính thức của nền tảng vận hành.

## 2. Thêm DevTools vào dự án

Trong dự án Maven đã dùng dependency management của Spring Boot:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-devtools</artifactId>
    <optional>true</optional>
</dependency>
~~~

`optional=true` giúp tránh việc DevTools vô tình trở thành dependency transitive bắt buộc của những module phụ thuộc vào dự án này. Việc DevTools có được đưa vào artifact cuối hay không còn phụ thuộc packaging plugin và cấu hình build.

Trong Gradle Kotlin DSL, có thể dùng configuration dành cho development:

~~~kotlin
dependencies {
    developmentOnly(
        "org.springframework.boot:spring-boot-devtools"
    )
}
~~~

Với Gradle Groovy DSL:

~~~groovy
dependencies {
    developmentOnly 'org.springframework.boot:spring-boot-devtools'
}
~~~

`developmentOnly` thường có ý nghĩa rõ ràng hơn việc đưa DevTools vào dependency runtime production. Các plugin và phiên bản build tool cần hỗ trợ configuration tương ứng.

### Một cấu trúc dự án minh họa

~~~text
store-service/
├── pom.xml
├── src/
│   └── main/
│       ├── java/
│       │   └── com/example/store/
│       │       ├── StoreApplication.java
│       │       └── OrderService.java
│       └── resources/
│           ├── application.yml
│           ├── static/
│           │   ├── css/site.css
│           │   └── js/app.js
│           └── templates/
│               └── order.html
└── target/
    └── classes/
        ├── com/example/store/...
        ├── application.yml
        ├── static/
        └── templates/
~~~

Với Maven, `target/classes` thường là classpath output directory. Với Gradle, có thể có các output directories như `build/classes/java/main` và `build/resources/main`. DevTools quan sát các classpath entries thực tế mà ứng dụng được chạy bằng, không phải chỉ nhìn tên thư mục `src`.

## 3. DevTools theo dõi classpath, không đơn thuần theo dõi source

Một nhầm lẫn thường gặp:

> Tôi sửa `OrderService.java` và lưu rồi, vì sao Spring Boot chưa restart?

Nguyên nhân có thể là DevTools đang quan sát `OrderService.class` trong runtime classpath, nhưng IDE chưa biên dịch lại file source.

Luồng đầy đủ:

~~~text
src/main/java/OrderService.java
                  |
                  | IDE/build tool compile
                  v
target/classes/.../OrderService.class
                  |
                  | DevTools FileSystemWatcher quan sát
                  v
            Restart trigger
~~~

Tương tự với resource:

~~~text
src/main/resources/templates/order.html
                  |
                  | Resource copy hoặc IDE output sync
                  v
target/classes/templates/order.html
                  |
                  v
           DevTools quan sát
~~~

Nếu resource nằm trên một external classpath directory và được runtime dùng trực tiếp, luồng sao chép có thể khác. Nhưng nguyên tắc vẫn là kiểm tra **đường dẫn thực sự được đưa vào classpath và được theo dõi**.

### Những môi trường làm việc điển hình

- **Eclipse / Spring Tools:** chức năng automatic build thường cập nhật output classes khi lưu file.
- **IntelliJ IDEA:** có thể cần build project hoặc cấu hình auto-build thích hợp trong lúc ứng dụng đang chạy.
- **VS Code với Java tooling:** cần xác định Java extension hoặc build workflow có cập nhật output directories hay không.
- **Maven / Gradle CLI:** cách chạy và cơ chế biên dịch ảnh hưởng việc các output file được thay đổi lúc nào.

Nếu đang chạy một JAR đã đóng gói và chỉ sửa source bên ngoài, JAR không tự thay đổi. Không nên kỳ vọng DevTools trong một packaged application tự đọc source và nạp lại.

## 4. Hai classloader trong DevTools restart

Cơ chế restart tiêu biểu sử dụng hai classloader:

1. **Base classloader:** giữ những thư viện/đầu vào có thể tái sử dụng.
2. **Restart classloader:** giữ những classpath entries của ứng dụng đang phát triển, thường là những thư mục mở.

Sơ đồ:

~~~text
                     JVM vẫn tồn tại
                            |
       +--------------------+--------------------+
       |                                         |
       v                                         v
 Base classloader                         Restart classloader
       |                                         |
       +--> Spring Framework jars                +--> OrderService.class
       +--> Hibernate / Jackson jars             +--> OrderController.class
       +--> Các dependency jars                  +--> App configuration
       |                                         |
       +------------- Runtime context -----------+
                            |
                 Khi phát hiện thay đổi
                            |
                            v
                   Đóng context hiện tại
                            |
                            v
                  Thay restart classloader
                            |
                            v
                   Tạo context mới
~~~

Mô hình này giải thích vì sao DevTools restart có thể nhanh hơn cold start, và cũng giải thích một nhóm vấn đề với classloading trong multi-module hoặc thư viện dùng reflection/serialization.

**Lưu ý:** các classloader này liên quan đến phân chia classpath entries; chúng không trực tiếp quyết định một file CSS có được exclude khỏi restart hay không. Quy tắc loại trừ tài nguyên và phân chia classloader là hai nhóm cấu hình khác nhau.

## 5. Restart khác LiveReload thế nào?

DevTools thường được nhắc cùng **LiveReload**, nhưng hai khái niệm khác nhau.

**Restart** là tạo lại phần ứng dụng Spring:

~~~text
Classpath thay đổi
       |
       v
Đóng ApplicationContext
       |
       v
Tạo context mới
       |
       v
Server/beans sẵn sàng trở lại
~~~

**LiveReload** là cơ chế thông báo cho client hỗ trợ LiveReload làm mới trang khi tài nguyên thay đổi:

~~~text
CSS / template / static asset thay đổi
       |
       v
DevTools phát hiện thay đổi
       |
       v
Gửi thông báo LiveReload
       |
       v
Browser/plugin phù hợp reload trang
~~~

Không phải mọi trình duyệt tự nhận LiveReload event. Thường cần extension hoặc client integration phù hợp. Nếu không có, bạn vẫn có thể nhấn refresh thủ công để thấy resource mới.

### Một restart cũng có thể dẫn đến LiveReload

DevTools có thể thông báo LiveReload khi ứng dụng restart hoặc resource thay đổi theo cơ chế hỗ trợ. Nhưng “browser reload” và “Spring context restart” vẫn là hai sự kiện riêng. Khi tìm nguyên nhân một thay đổi không xuất hiện, cần phân biệt:

- Ứng dụng đã restart chưa?
- Server có đang phục vụ resource mới không?
- Trình duyệt đã reload chưa?
- Trình duyệt hoặc template engine có đang cache nội dung cũ không?

## 6. Những tài nguyên nào thường cần restart?

Một số loại thay đổi thông thường:

| Thay đổi | Hành vi mong đợi thường gặp | Vì sao? |
|---|---|---|
| `OrderService.class` được biên dịch lại | Restart | Code nghiệp vụ thay đổi |
| `@Configuration` class đổi | Restart | Bean definitions/configuration thay đổi |
| `@Component` mới xuất hiện | Restart | Component scan cần chạy lại |
| `application.yml` nằm trong classpath đổi | Thường restart | Environment và bean config cần nạp lại |
| `application.properties` đổi | Thường restart | Property binding/condition có thể thay đổi |
| Template Thymeleaf trong vùng exclude mặc định | Không cần full restart | Template engine có thể đọc lại template khi cache được cấu hình phù hợp |
| CSS/JS trong `static` | Không cần full restart | Static resource không cần dựng lại bean graph |
| File nằm ngoài mọi đường dẫn được quan sát | Không có restart tự động | DevTools chưa được báo về thay đổi |
| Source Java đổi nhưng output `.class` chưa đổi | Có thể chưa restart | DevTools không phải Java compiler |

Các kết quả trong bảng phụ thuộc vào cấu hình thật: đường dẫn có được theo dõi, có bị exclude, IDE đã copy/build và chế độ DevTools có được kích hoạt hay không.

### Vì sao application.yml nên làm restart?

Property có thể quyết định bean nào được đăng ký:

~~~yaml
app:
  billing:
    mode: simulation
~~~

Một bean configuration:

~~~java
@Configuration
public class BillingConfiguration {

    @Bean
    @ConditionalOnProperty(
            prefix = "app.billing",
            name = "mode",
            havingValue = "simulation"
    )
    BillingGateway simulationGateway() {
        return new SimulationBillingGateway();
    }
}
~~~

Nếu `app.billing.mode` thay đổi, chỉ thay nội dung file trên đĩa không có nghĩa Spring tự chạy lại toàn bộ bean condition. Restart context cho phép các configuration conditions và property binding được xử lý lại.

### Vì sao CSS không cần restart?

Một file:

~~~text
src/main/resources/static/css/site.css
~~~

thường được web server phục vụ như static asset. Nếu bản mới đã tới runtime resource location, ứng dụng không phải tạo lại bean `OrderService` chỉ vì một thuộc tính CSS đổi. Đây là một lý do DevTools mặc định loại một số resource directories khỏi **restart**, nhưng vẫn có thể phát thông báo LiveReload.

## 7. Những tài nguyên được loại trừ khỏi restart theo mặc định

Spring Boot DevTools thường đã có một số **default restart exclusions** cho những resource không cần restart context. Những nhóm thường gặp gồm đường dẫn classpath tương ứng:

~~~text
/META-INF/maven
/META-INF/resources
/resources
/static
/public
/templates
~~~

Đây là các nhóm đường dẫn minh họa theo tài liệu Spring Boot; cú pháp pattern/exclusion cụ thể có thể thay đổi giữa phiên bản. Khi cần biết danh sách chính xác, dùng hướng dẫn của phiên bản Spring Boot mà dự án đang chạy.

Ý nghĩa thông thường:

- `static` và `public` thường chứa file tĩnh phục vụ HTTP.
- `templates` thường chứa template như Thymeleaf.
- `META-INF/resources` có thể chứa các static web resources.
- `META-INF/maven` chứa metadata Maven.
- `resources` là một location resource dùng trong web serving theo convention.

Khi các resource bị loại trừ khỏi restart thay đổi, DevTools có thể vẫn theo dõi thay đổi và phát LiveReload. **Exclude khỏi restart không phải lúc nào cũng là bỏ qua file hoàn toàn.**

### Default exclude không phải xóa resource khỏi classpath

Một file trong `static` vẫn có thể được ứng dụng phục vụ. Quy tắc DevTools exclude chỉ ảnh hưởng cơ chế quyết định có restart ApplicationContext khi file thay đổi hay không.

Đừng hiểu nhầm:

~~~text
Exclude khỏi DevTools restart
          !=
Loại resource khỏi JAR hoặc runtime classpath
          !=
Cấm truy cập static resource
          !=
Bỏ qua hoàn toàn mọi thay đổi của resource
~~~

Đó là những vấn đề riêng thuộc build packaging, resource handling và DevTools.

## 8. spring.devtools.restart.exclude: thay danh sách loại trừ

Có thể cấu hình:

~~~properties
spring.devtools.restart.exclude=static/**,public/**
~~~

Hoặc YAML:

~~~yaml
spring:
  devtools:
    restart:
      exclude: "static/**,public/**"
~~~

Property `spring.devtools.restart.exclude` quy định các pattern của resource không cần kích hoạt restart.

**Điểm dễ mắc lỗi:** khi tự cấu hình `exclude`, bạn đang cung cấp danh sách exclude được dùng **thay cho những mặc định tương ứng**. Nếu bạn chỉ ghi hai pattern nhưng hệ thống trước đó còn exclude template, metadata và những nhóm khác, thay đổi này có thể khiến các nhóm mặc định không còn được đối xử như mong muốn.

Do đó, không nên dùng `spring.devtools.restart.exclude` chỉ để “thêm đúng một folder”, trừ khi bạn chủ động muốn quản lý toàn bộ danh sách exclude.

### Khi nào nên chủ động thay toàn bộ exclude?

Ví dụ dự án có runtime resource đặc biệt: một số template hoặc metadata thay đổi phải khiến context restart thay vì chỉ LiveReload. Bạn có thể thiết kế lại danh sách exclude và chủ động **không loại trừ** nhóm đó.

Nhưng phải xác định hậu quả: file không còn excluded sẽ có thể khiến ứng dụng restart thường xuyên khi developer sửa giao diện.

### Pattern là đường dẫn resource, không phải URL route

Ví dụ:

~~~properties
spring.devtools.restart.exclude=static/**,public/**
~~~

Pattern dùng cho path tương ứng trong khu vực theo dõi, không đơn thuần là URL request như `/css/site.css`. Cấu hình phải được so sánh với cấu trúc classpath thực tế.

Nếu file không có trong output location hoặc nằm ngoài monitored roots, một exclude pattern đúng cũng không khiến DevTools phát hiện nó.

## 9. spring.devtools.restart.additional-exclude: bổ sung vào mặc định

Nếu muốn **giữ default excludes** và thêm một số pattern mới, dùng:

~~~properties
spring.devtools.restart.additional-exclude=generated-docs/**,frontend-cache/**
~~~

YAML:

~~~yaml
spring:
  devtools:
    restart:
      additional-exclude: "generated-docs/**,frontend-cache/**"
~~~

Đây là lựa chọn phù hợp khi dự án có một thư mục resource được cập nhật liên tục nhưng không ảnh hưởng tới bean graph.

Ví dụ cấu trúc:

~~~text
src/main/resources/
├── application.yml
├── templates/
├── static/
├── generated-docs/
│   ├── api-index.html
│   └── search-data.json
└── frontend-cache/
    └── manifest.json
~~~

Nếu tài liệu `generated-docs` chỉ được phục vụ như file tĩnh, việc phát LiveReload hoặc refresh riêng có thể đủ. Restart toàn bộ context mỗi lần file được tạo lại sẽ lãng phí thời gian.

### So sánh exclude và additional-exclude

| Property | Mục tiêu | Tác động tới mặc định |
|---|---|---|
| `spring.devtools.restart.exclude` | Định nghĩa nhóm resource loại trừ | Có thể thay danh sách exclude mặc định |
| `spring.devtools.restart.additional-exclude` | Thêm pattern loại trừ | Giữ những default exclusions |
| `spring.devtools.restart.additional-paths` | Thêm các đường dẫn cần quan sát | Không phải danh sách loại trừ |
| `spring.devtools.restart.trigger-file` | Chỉ cho restart khi file kích hoạt được cập nhật | Không thay thế logic phân loại file |

**Quy tắc thực hành:** nếu chỉ cần thêm một hoặc hai folder không nên làm context restart, hãy bắt đầu bằng `additional-exclude`.

## 10. Ví dụ: tài nguyên frontend được build liên tục

Giả sử frontend build tool ghi artifact vào:

~~~text
store-service/
├── src/main/java/...
├── src/main/resources/
│   └── static/
└── frontend/
    ├── src/
    └── dist/
        ├── index.html
        ├── app.js
        └── site.css
~~~

Nếu pipeline development copy `frontend/dist` vào classpath mỗi lần build, mỗi lần frontend compile có thể tạo hàng loạt file changes.

Giải pháp thường gồm:

1. Đưa tài nguyên đã build đến location mà backend phục vụ.
2. Tránh full Spring context restart chỉ vì HTML/CSS/JS được ghi lại.
3. Để browser reload bằng LiveReload hoặc refresh thủ công.
4. Kiểm soát cache để thay đổi thực sự được phục vụ.

Ví dụ nếu output đích là `static` thì default exclude có thể đã đủ. Nếu output được copy vào một folder khác nằm trên classpath, có thể bổ sung pattern phù hợp:

~~~yaml
spring:
  devtools:
    restart:
      additional-exclude: "frontend-build/**"
~~~

Điểm quan trọng: pattern phải match **đường dẫn mà watcher nhìn thấy**, không chỉ tên folder trong source repository.

### Không exclude nhầm file cấu hình backend

Nếu đưa cả `application.yml` vào folder excluded, việc đổi các property điều khiển bean có thể không khiến context restart. Vì vậy, chỉ exclude những resource thực sự có thể được tiêu thụ mà không khởi tạo lại ứng dụng.

Một folder chứa lẫn Java configuration output và static assets thường cần tách cấu trúc trước khi thêm một pattern exclude quá rộng.

## 11. spring.devtools.restart.additional-paths: theo dõi thêm đường dẫn

Mặc định DevTools theo dõi những classpath directories thích hợp. Một dự án có thể còn dùng resource hoặc file cấu hình nằm ngoài classpath thông thường.

Ví dụ:

~~~text
workspace/
├── store-service/
│   ├── src/main/java/...
│   └── src/main/resources/...
└── shared-development-config/
    ├── banner.txt
    └── mock-partners.yml
~~~

Nếu muốn DevTools theo dõi `shared-development-config`, có thể cấu hình:

~~~properties
spring.devtools.restart.additional-paths=../shared-development-config
~~~

YAML:

~~~yaml
spring:
  devtools:
    restart:
      additional-paths:
        - ../shared-development-config
~~~

Những đường dẫn ví dụ được hiểu theo môi trường chạy và cách property được giải quyết; nên kiểm tra working directory, đường dẫn tuyệt đối/tương đối và quyền đọc thật của process.

### Theo dõi thêm không có nghĩa tự đưa resource vào classpath

Đây là khác biệt rất quan trọng:

~~~text
Thêm vào additional-paths
         |
         +--> DevTools có thể phát hiện file change
         |
         X--> Không mặc nhiên biến file thành classpath resource
         X--> Không tự inject file vào Spring Environment
         X--> Không tự định nghĩa bean hoặc config import
~~~

Nếu ứng dụng cần nạp file cấu hình bên ngoài, phải có cơ chế nạp tương ứng, ví dụ Config Data import hoặc mã ứng dụng đọc file. `additional-paths` chỉ tham gia vào việc **theo dõi và kích hoạt hành vi phát triển**, không thay thế cơ chế load dữ liệu.

### Khi nào dùng additional-paths?

Một số trường hợp:

- Template được phát triển trong thư mục ngoài module chính.
- Cấu hình test/mock nằm ngoài classpath output.
- Một frontend build directory được backend sử dụng trực tiếp khi phát triển.
- Tài nguyên dùng chung giữa các module không có trong watched classpath directory.
- File được generated bởi công cụ bên ngoài cần kích hoạt reload/restart khi thay đổi.

Nếu thay đổi file không ảnh hưởng trạng thái ứng dụng và cũng không cần reload browser, không nhất thiết phải theo dõi nó.

## 12. Kết hợp additional-paths với exclusion

Các file trong `additional-paths` có thể thay đổi thường xuyên. DevTools cho phép dùng quy tắc loại trừ để kiểm soát thay đổi nào cần restart và thay đổi nào chỉ nên làm LiveReload.

Ví dụ ý tưởng:

~~~text
../shared-dev-assets/
├── templates/
│   └── invoice.html
├── images/
│   └── logo.svg
└── config/
    └── invoice-rules.yml
~~~

Yêu cầu mong muốn:

- Đổi `invoice.html` hoặc `logo.svg`: không cần restart.
- Đổi `invoice-rules.yml`: context phải nạp lại nếu rule được bind khi startup.

Cấu hình minh họa:

~~~yaml
spring:
  devtools:
    restart:
      additional-paths:
        - ../shared-dev-assets
      additional-exclude: "templates/**,images/**"
~~~

**Cần xác minh pattern với cấu trúc được watcher nhìn thấy.** Khi đường dẫn theo dõi bổ sung ở ngoài classpath, cách matching có thể phụ thuộc vị trí gốc mà watcher sử dụng. Không nên giả định một pattern viết theo URL hoặc source tree luôn match đúng.

Mục tiêu của kết hợp này là tách:

~~~text
Additional paths
      |
      +--> Thay đổi có ý nghĩa cho Spring configuration -> restart
      |
      +--> Static/template changes được exclude     -> reload không restart
~~~

### Một folder ngoài classpath có được reload mà không restart không?

Không phải cứ thay file rồi phát LiveReload là backend chắc chắn đã đọc được nội dung mới. Nếu ứng dụng đã copy file đó lúc startup, việc chỉ reload trình duyệt không khiến bản copy tự thay đổi. Phải thiết kế đúng luồng sử dụng tài nguyên: runtime đọc trực tiếp external directory, hoặc có bước copy/sync phù hợp.

## 13. Trigger file là gì?

Trong một dự án lớn, một lần build có thể ghi **rất nhiều class và resource file** trong vài giây. Nếu watcher phản ứng trước khi quá trình ghi file hoàn tất, ứng dụng có thể restart khi classpath còn đang thay đổi.

Ngoài việc điều chỉnh poll interval và quiet period, DevTools cung cấp **trigger file**: file được theo dõi như một tín hiệu “tôi đã sẵn sàng để restart”.

Ví dụ cấu hình:

~~~properties
spring.devtools.restart.trigger-file=.reloadtrigger
~~~

Hoặc YAML:

~~~yaml
spring:
  devtools:
    restart:
      trigger-file: ".reloadtrigger"
~~~

Sau khi xác định được trigger file trên classpath, DevTools chỉ thực hiện restart dựa trên thay đổi trigger file, thay vì restart ngay mỗi khi các file khác thay đổi.

### Vì sao trigger file hữu ích?

Không dùng trigger file:

~~~text
Compile A.class
      |
      +--> Restart
Compile B.class
      |
      +--> Restart tiếp
Copy config
      |
      +--> Restart tiếp
~~~

Đây là mô hình minh họa một build có nhiều đợt ghi file; watcher thực tế có khoảng lặng để gom thay đổi, nên không nhất thiết restart mỗi file.

Dùng trigger file:

~~~text
Compile A.class
Compile B.class
Copy config
         |
         | Build hoàn tất
         v
Cập nhật .reloadtrigger
         |
         v
DevTools restart một lần
~~~

Trigger file đặc biệt hữu ích khi developer muốn kiểm soát **thời điểm restart** thay vì muốn bỏ qua các thay đổi.

## 14. Tạo và đặt trigger file đúng nơi

Một cấu trúc thông dụng:

~~~text
src/main/resources/
├── application.yml
└── .reloadtrigger
~~~

File `.reloadtrigger` có thể rỗng. Tên file được cấu hình bằng:

~~~properties
spring.devtools.restart.trigger-file=.reloadtrigger
~~~

Thông thường property này chỉ định **tên file**, không yêu cầu đưa cả đường dẫn thư mục vào giá trị. DevTools cần tìm thấy trigger file trên classpath.

Với Maven, sau khi resource được copy:

~~~text
target/classes/.reloadtrigger
~~~

Với Gradle, nó có thể nằm trong:

~~~text
build/resources/main/.reloadtrigger
~~~

Tùy cách IDE/build tool cấu hình runtime classpath.

### Chỉ có file trong src/main/resources chưa đủ

Nếu bạn tạo:

~~~text
src/main/resources/.reloadtrigger
~~~

nhưng build tool hoặc IDE chưa copy nó vào output directory được ứng dụng sử dụng, DevTools có thể **không tìm thấy trigger file trên classpath**.

Vì vậy, cần xác minh ba điều:

1. File tồn tại trong source hoặc location được quản lý.
2. File xuất hiện trong **classpath runtime**.
3. Khi thay đổi file, mốc thời gian/nội dung được cập nhật ở nơi watcher theo dõi.

### Không dùng một đường dẫn tuyệt đối vào trigger-file một cách tùy tiện

Ví dụ này không phải cấu hình đúng ý thông thường:

~~~properties
spring.devtools.restart.trigger-file=/home/user/project/target/classes/.reloadtrigger
~~~

Property trigger file được thiết kế để chỉ định một tên file tìm trên classpath. Nếu muốn quan sát một thư mục bên ngoài, đó là trách nhiệm của `additional-paths`; hai cơ chế có ý nghĩa khác nhau.

## 15. Cách kích hoạt restart bằng trigger file

Sau khi DevTools và trigger file được cấu hình, quy trình phát triển có thể là:

1. Sửa một hoặc nhiều Java class.
2. Để IDE/build tool biên dịch/copy đầy đủ ra output directory.
3. Cập nhật trigger file mà ứng dụng đang quan sát.
4. DevTools nhận thay đổi và thực hiện restart theo cơ chế của nó.

Ví dụ trong shell Unix, nếu Maven output đang được ứng dụng dùng:

~~~bash
touch target/classes/.reloadtrigger
~~~

Hoặc với Gradle:

~~~bash
touch build/resources/main/.reloadtrigger
~~~

Cần chắc chắn file đó tồn tại và nằm trong classpath runtime; đường dẫn chỉ là ví dụ.

Trong PowerShell trên Windows:

~~~powershell
$p = "target/classes/.reloadtrigger"
(Get-Item -LiteralPath $p).LastWriteTime = Get-Date
~~~

Nếu chỉ sửa file source:

~~~bash
touch src/main/resources/.reloadtrigger
~~~

thì phải có cơ chế copy/sync sang output directory để watcher thấy mốc thời gian mới. Đối với IDE tự động copy resources khi lưu, thay đổi source có thể đủ; với một workflow khác, cần kích hoạt resource processing.

### Có thể đổi nội dung thay vì chỉ cập nhật timestamp

Một số hệ thống đồng bộ file hoặc version control có quy tắc timestamp riêng. Ghi một nội dung mới vào trigger file là cách làm rõ ràng để bảo đảm file thực sự thay đổi:

~~~bash
date > target/classes/.reloadtrigger
~~~

Đây chỉ là thao tác trong môi trường phát triển. Không nên đưa lệnh thay đổi file vào code production.

## 16. Trigger file không phải lệnh deploy

Trigger file chỉ điều phối automatic restart của DevTools trong một development runtime đang chạy. Nó không:

- Tự biên dịch Java source.
- Tự bảo đảm resource copy đã hoàn tất.
- Tự thực hiện database migration theo cách an toàn.
- Tự triển khai JAR sang server production.
- Tự yêu cầu Kubernetes restart pod.
- Tự reload mọi cache hoặc tài nguyên ngoài Spring context.
- Tạo một JVM mới từ đầu.

Sơ đồ phân biệt:

~~~text
Sửa source
   |
   v
Build/compile/copy
   |
   v
Cập nhật trigger file
   |
   v
DevTools context restart
   |
   v
Ứng dụng local/dev dùng class/resource mới
~~~

Nếu ứng dụng chạy trong container production từ image bất biến, không nên dùng trigger file để thay thế quy trình rollout image mới.

## 17. Trigger file và tài nguyên được exclude

Giả sử một đợt thay đổi chỉ gồm:

~~~text
static/css/site.css
templates/order.html
~~~

và những path này đang được exclude khỏi restart. Nếu trình duyệt chỉ cần nhận resource mới, không cần yêu cầu full Spring context restart.

Nếu bạn cấu hình trigger file, đừng nhầm rằng **mỗi lần touch trigger file là bắt buộc phải restart** theo mọi tình huống. Hành vi cuối phụ thuộc DevTools đã quan sát những thay đổi nào, chúng có thuộc nhóm cần restart không và cách trigger file được xử lý ở phiên bản đang dùng.

Điều cần thiết kế là:

- Resource-only changes nên phục vụ/LiveReload đúng.
- Java class hoặc application configuration changes cần restart khi được kích hoạt.
- Trigger file không nên vô tình bị loại khỏi vùng theo dõi cần thiết.
- Không nên dùng một pattern exclude quá rộng làm vô hiệu hóa ý định sử dụng trigger.

### Khi cấu hình trigger mà đổi Java không restart ngay

Đó có thể là **hành vi đúng**: DevTools đang đợi trigger file thay đổi. Hãy kiểm tra đã cập nhật đúng file ở runtime classpath chưa trước khi kết luận restart bị lỗi.

## 18. Dùng trigger file trong IDE

Một vài IDE có thể tự compile và copy hàng loạt file ngay khi developer lưu. Điều này tiện nhưng có thể khiến DevTools restart khi ta chưa hoàn tất một chuỗi chỉnh sửa.

Trigger file cho phép một vòng lặp chủ động:

~~~text
Sửa một nhóm source files
          |
          v
IDE build / compile
          |
          v
Chạy/unit-check theo workflow dự án nếu muốn
          |
          v
Chủ động touch .reloadtrigger
          |
          v
Quan sát Spring Boot restart
~~~

Đây là một cách làm hữu ích khi ứng dụng có thời gian startup đáng kể hoặc editor tạo nhiều file changes liên tục.

### Chọn tên trigger file dễ nhận biết

Những tên như:

~~~text
.reloadtrigger
.restart-trigger
.spring-restart
~~~

đều có thể dùng nếu phù hợp với property và classpath. Nên chọn một tên và tài liệu hóa thống nhất để các thành viên nhóm không tạo nhiều trigger files cạnh tranh.

### File rỗng có thể bị tooling bỏ qua

Một vài resource filters, packaging rules hoặc IDE sẽ bỏ qua dotfile hoặc file rỗng theo cấu hình riêng. Nếu trigger không được nhận diện, hãy kiểm tra file thực tế trong runtime output directory.

Đừng mặc nhiên suy ra rằng vì file nằm trong repository thì JVM đang chạy cũng nhìn thấy nó.

## 19. Điều chỉnh nhịp theo dõi: poll-interval và quiet-period

DevTools sử dụng cơ chế watcher để phát hiện file changes. Nếu toolchain ghi class/resource theo nhiều đợt, cần tránh restart khi file vẫn đang được cập nhật.

Có thể điều chỉnh:

~~~properties
spring.devtools.restart.poll-interval=2s
spring.devtools.restart.quiet-period=1s
~~~

Ý nghĩa khái quát:

- **`poll-interval`:** khoảng thời gian watcher kiểm tra thay đổi.
- **`quiet-period`:** khoảng thời gian hệ thống cần tương đối yên lặng trước khi coi một đợt ghi đã ổn định.

Đây là các giá trị minh họa, không phải khuyến nghị cố định cho mọi máy.

### Ví dụ quan sát

~~~text
0.0s  Build bắt đầu ghi A.class
0.3s  Build ghi B.class
0.6s  Build ghi application.yml
1.1s  Build hoàn tất
         |
         v
Watcher chờ quiet period phù hợp
         |
         v
Restart khi thay đổi đã ổn định
~~~

Nếu watcher bắt đầu restart quá sớm hoặc liên tục, có thể điều chỉnh hai property này theo thời gian ghi file thực tế.

### Đừng tăng mọi timeout lên quá lớn

Nếu tăng quiet period quá nhiều, vòng lặp sửa–chạy sẽ trở nên chậm. Nếu giảm quá nhỏ, classpath có thể chưa ổn định và restart nhiều lần. Cần cân bằng độ nhạy với đặc điểm IDE và build tool.

### Khi nào trigger file tốt hơn thay đổi polling?

Nếu vấn đề chỉ là build mất vài giây để copy file, điều chỉnh quiet period có thể đủ. Nếu developer **muốn chủ động chọn khi nào restart**, trigger file đúng mục đích hơn.

Có thể kết hợp cả hai nhưng không nên thêm cấu hình phức tạp nếu mặc định đã ổn định.

## 20. Cấu hình ví dụ cho nhiều tình huống

### Trường hợp A: ứng dụng nhỏ, dùng mặc định

~~~yaml
spring:
  application:
    name: store-service
~~~

Nếu DevTools đã có trên development classpath, thường không cần thêm bất kỳ property restart nào. Java class thay đổi sẽ được xử lý theo automatic restart khi output được cập nhật; tài nguyên mặc định như static/templates đã có exclude phù hợp.

Đây là lựa chọn nên thử trước. Tùy chỉnh quá sớm có thể tạo những pattern khó chẩn đoán.

### Trường hợp B: thêm folder không cần restart

~~~yaml
spring:
  devtools:
    restart:
      additional-exclude: "generated-docs/**,assets-cache/**"
~~~

Giữ default excludes và thêm hai folder tạo ra trong quá trình phát triển.

### Trường hợp C: quản lý danh sách exclude tùy chỉnh

~~~yaml
spring:
  devtools:
    restart:
      exclude: "static/**,public/**,templates/**"
~~~

Cấu hình này chủ động quy định danh sách loại trừ. Cần hiểu đây không chỉ là bổ sung một folder vào mặc định; những default exclusions khác có thể không còn có hiệu lực.

### Trường hợp D: theo dõi external configuration

~~~yaml
spring:
  devtools:
    restart:
      additional-paths:
        - ../shared-dev-config
~~~

DevTools có thể nhận biết file changes trong thư mục bổ sung. Nếu ứng dụng muốn đọc các file đó, vẫn cần cơ chế load config riêng.

### Trường hợp E: build nhiều bước, dùng trigger file

~~~yaml
spring:
  devtools:
    restart:
      trigger-file: ".reloadtrigger"
      poll-interval: 2s
      quiet-period: 1s
~~~

Sau khi compile/copy xong, cập nhật `.reloadtrigger` tại output directory được watcher quan sát.

### Trường hợp F: kết hợp đường dẫn và exclusions

~~~yaml
spring:
  devtools:
    restart:
      additional-paths:
        - ../shared-dev-assets
      additional-exclude: "static/**,generated-docs/**"
      trigger-file: ".reloadtrigger"
~~~

Trường hợp này phù hợp khi dự án lớn có nhiều nguồn thay đổi. Cần xác minh semantics path matching và trigger trên phiên bản Boot cụ thể, không nên sao chép thành “cấu hình chuẩn” cho mọi dự án.

## 21. Một dự án Maven thực hành

Giả sử cấu trúc:

~~~text
inventory-service/
├── pom.xml
├── src/main/java/com/example/inventory/
│   ├── InventoryApplication.java
│   ├── InventoryController.java
│   └── InventoryService.java
├── src/main/resources/
│   ├── application.yml
│   ├── .reloadtrigger
│   ├── static/css/site.css
│   └── templates/inventory.html
└── target/classes/...
~~~

Dependency:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-devtools</artifactId>
    <optional>true</optional>
</dependency>
~~~

Cấu hình development:

~~~yaml
spring:
  application:
    name: inventory-service
  devtools:
    restart:
      additional-exclude: "generated-reports/**"
      trigger-file: ".reloadtrigger"
~~~

Quy trình minh họa:

1. Chạy ứng dụng từ IDE hoặc một task phát triển với classpath là những output directories.
2. Xác minh `.reloadtrigger` có trong output directory.
3. Sửa logic `InventoryService.java`.
4. Biên dịch để tạo class file mới.
5. Cập nhật `target/classes/.reloadtrigger`.
6. Quan sát việc context restart trong log.
7. Gọi lại endpoint để kiểm tra behavior mới.

Nếu chỉ sửa `static/css/site.css`, backend có thể phục vụ file mới mà không restart context; trình duyệt cần reload hoặc LiveReload client.

### Vì sao không sửa trực tiếp file trong target/classes như source lâu dài?

`target/classes` là build output. Một lần clean/build có thể ghi đè hoặc xóa file do bạn sửa thủ công. Trigger có thể được touch tại đây vì nó là tín hiệu tạm thời cho watcher; source chuẩn vẫn phải nằm trong `src/main/resources` nếu muốn nó tồn tại ổn định qua build.

## 22. Một dự án Gradle thực hành

Với Gradle:

~~~kotlin
plugins {
    id("org.springframework.boot") version "<spring-boot-version>"
    java
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    developmentOnly("org.springframework.boot:spring-boot-devtools")
}
~~~

Đoạn trên là khung minh họa; version thực tế và dependency management cần dùng theo dự án đang xây dựng.

Cấu hình:

~~~yaml
spring:
  devtools:
    restart:
      additional-exclude: "ui-build/**"
      trigger-file: ".reloadtrigger"
~~~

Đường dẫn output thường thấy:

~~~text
build/classes/java/main
build/resources/main
~~~

Sau khi build/copy, cần xác minh trigger file thực sự nằm trên classpath của tiến trình phát triển.

### Một điểm hay nhầm về Gradle

Lệnh build có thể tạo output classes mới, nhưng điều đó chỉ giúp DevTools restart nếu **tiến trình đang chạy sử dụng các classpath entries đã thay đổi**. Nếu ứng dụng được khởi động từ một JAR cũ tách biệt, việc build ra directory mới không tự thay đổi JAR đang chạy.

### Multi-project Gradle

Trong một dự án gồm `api`, `domain` và `shared`, tùy cách chạy, các module có thể xuất hiện trên classpath dưới dạng:

- Output directories của từng module.
- Những JAR đã build.

Điều này ảnh hưởng những class nào nằm trong restart classloader và file change nào được watcher quan sát. Nếu một module chỉ xuất hiện dưới dạng JAR, DevTools có thể không xử lý nó như một open project output directory.

## 23. Multi-module: vì sao module chung đổi mà ứng dụng không restart?

Giả sử:

~~~text
workspace/
├── store-api/
│   └── Spring Boot application
├── store-domain/
│   └── Domain classes
└── store-common/
    └── Shared utilities
~~~

Khi chạy `store-api` từ IDE, `store-domain` có thể được đưa vào classpath như một output directory nên thay đổi class file được theo dõi.

Nhưng nếu `store-common` được tải từ một JAR trong local Maven repository, khi bạn sửa source của `store-common` mà chưa build lại hoặc cập nhật runtime classpath, process đang chạy vẫn có thể thấy JAR cũ.

Cần phân biệt hai vấn đề:

1. **Thay đổi có được copy/compile vào classpath đang sử dụng không?**
2. **Classpath entry đó được DevTools restart classloader và watcher quản lý thế nào?**

Không phải mọi vấn đề multi-module đều được sửa bằng `additional-paths`. Nếu process vẫn nạp class cũ từ JAR, việc chỉ quan sát source folder không làm classloader có phiên bản class mới.

### Kiểm tra classpath thực tế

Một quy trình điều tra:

- Xác định dependency đang là project/module output hay packaged JAR.
- Xác định output path chứa class vừa biên dịch.
- Xác nhận process phát triển có sử dụng path đó.
- Kiểm tra DevTools có nhận classpath change không.
- Nếu có classloading conflict, xem cấu hình restart classloader ở phần sau.

## 24. Phân biệt resource restart exclusion và classloader exclusion

Đây là hai nhóm cấu hình khác nhau nhưng rất dễ nhầm vì cùng có chữ *exclude*.

**Nhóm thứ nhất: thay đổi file nào nên kích hoạt restart?**

~~~properties
spring.devtools.restart.exclude=static/**,public/**
spring.devtools.restart.additional-exclude=generated-docs/**
~~~

Nhóm này kiểm soát **file change behavior**.

**Nhóm thứ hai: classpath entry nào đi vào base hoặc restart classloader?**

Spring Boot DevTools có cơ chế cấu hình classloader qua file:

~~~text
META-INF/spring-devtools.properties
~~~

Với các key kiểu:

~~~properties
restart.include.project-common=/project-common-[^/]+\.jar
restart.exclude.vendor-library=/vendor-library-[^/]+\.jar
~~~

Đây là ví dụ minh họa regex trên classpath entries. Pattern thực tế cần match URL/path của entry trong runtime classpath mà DevTools xử lý; không phải glob relative path của `static/**`.

Bảng phân biệt:

| Cấu hình | Đối tượng tác động |
|---|---|
| `spring.devtools.restart.exclude` | Những resource changes không cần context restart |
| `spring.devtools.restart.additional-exclude` | Những resource exclusions bổ sung |
| `spring.devtools.restart.additional-paths` | Những đường dẫn bổ sung được watcher theo dõi |
| `spring.devtools.restart.trigger-file` | Khi nào watcher được phép thực hiện restart |
| `restart.include.*` trong `spring-devtools.properties` | Classpath entry đưa vào restart classloader |
| `restart.exclude.*` trong `spring-devtools.properties` | Classpath entry giữ ngoài restart classloader |

**Không dùng `spring.devtools.restart.exclude` để sửa lỗi class identity giữa base và restart classloader.** Khi có `ClassCastException` giữa những class cùng tên nhưng do hai classloader khác nhau nạp, cần phân tích phân chia classloader và dependency, không chỉ các đường dẫn static resources.

## 25. Lỗi classloader thường gặp khi restart

Một số thư viện dùng reflection, serialization, custom classloader hoặc caching theo class object. Khi DevTools restart một phần classpath, chúng có thể gặp vấn đề như:

- `ClassCastException` dù tên class trong thông báo giống nhau.
- Một object được deserialize với classloader cũ.
- Một thread giữ reference tới bean/class của context đã đóng.
- Một thư viện dùng static registry trên base classloader giữ object thuộc restart classloader cũ.
- Classpath module chung nằm ở classloader không như mong muốn.

Ví dụ khái niệm:

~~~text
com.example.Order (BaseClassLoader)
          !=
com.example.Order (RestartClassLoader)
~~~

Hai class cùng fully-qualified name nhưng khác defining classloader có thể là hai kiểu Java khác nhau.

### Cách xử lý

1. Xác định class nào do classloader nào nạp.
2. Kiểm tra entry chứa class là directory hay JAR.
3. Xem có cache/static registry giữ reference cũ không.
4. Xem có background thread chưa dừng sau context restart không.
5. Nếu cần, điều chỉnh `restart.include.*` / `restart.exclude.*` trong `META-INF/spring-devtools.properties`.
6. Kiểm tra cold start khi nghi ngờ restart-only problem.

Không nên tắt DevTools mãi mãi để che một lỗi cleanup/lifecycle nghiêm trọng, nhưng có thể tạm vô hiệu hóa restart để so sánh behavior và khoanh vùng nguyên nhân.

## 26. Vô hiệu hóa DevTools restart khi cần

Khi DevTools có mặt nhưng bạn không muốn tự restart:

~~~properties
spring.devtools.restart.enabled=false
~~~

Hoặc:

~~~yaml
spring:
  devtools:
    restart:
      enabled: false
~~~

Cấu hình này hữu ích khi đang debug startup, chạy integration workflow đặc biệt hoặc khi restart tạo nhiễu trong một môi trường phát triển.

### Tắt restart qua property khác với tắt hoàn toàn từ rất sớm

Spring Boot có thể vẫn khởi tạo một số hạ tầng restart classloader dù property được đọc trong quá trình bootstrap và vô hiệu hóa restart sau đó.

Nếu cần **vô hiệu hóa hoàn toàn cơ chế restart ngay từ đầu**, có thể thiết lập system property trước khi `SpringApplication.run(...)`:

~~~java
public static void main(String[] args) {
    System.setProperty(
            "spring.devtools.restart.enabled",
            "false"
    );

    SpringApplication.run(StoreApplication.class, args);
}
~~~

Hoặc cung cấp JVM system property khi chạy ứng dụng:

~~~bash
java -Dspring.devtools.restart.enabled=false \
     -jar store-service.jar
~~~

Trong ứng dụng đóng gói, DevTools restart thông thường không hoạt động như khi chạy exploded development classpath. Ví dụ ở đây nhằm phân biệt **đọc cấu hình lúc chạy** với **disable thật sớm**, không phải khuyến nghị đưa DevTools vào packaged production application.

### Không nhầm với LiveReload

Vô hiệu hóa restart khác với vô hiệu hóa LiveReload:

~~~properties
spring.devtools.livereload.enabled=false
~~~

Một ứng dụng có thể muốn giữ restart nhưng tắt LiveReload browser notification. Đây là hai tính năng riêng.

## 27. Khi nào không cần restart?

Một số thay đổi có thể được phục vụ mà không cần tạo lại ApplicationContext:

- CSS/JS được phục vụ trực tiếp từ static resource location.
- Template engine được cấu hình để không cache template trong development.
- Một file tài liệu hoặc hình ảnh được web server đọc tại request time.
- Một resource có external watcher/loader tự áp dụng thay đổi theo thiết kế.

Nhưng cần chú ý: **không restart không bảo đảm code đang dùng sẽ nhìn thấy dữ liệu mới**.

Ví dụ:

~~~java
@Service
public class RuleService {

    private final String rule;

    public RuleService(ResourceLoader loader) {
        this.rule = loadRuleOnce(loader);
    }
}
~~~

Nếu rule được đọc **một lần trong constructor**, thay file trên đĩa nhưng exclude khỏi restart có thể khiến `RuleService` tiếp tục giữ rule cũ.

Ngược lại:

~~~java
public String currentRule() {
    return loadRuleFromExternalFile();
}
~~~

có thể đọc lại file mỗi lần, nhưng cách này có chi phí I/O và yêu cầu xử lý đồng bộ/consistency phù hợp.

Vì vậy, trước khi exclude một tài nguyên, hãy hỏi: **ứng dụng có cơ chế thực sự đọc lại nó sau khi file thay đổi không?**

## 28. Template caching và LiveReload

Spring Boot DevTools thường áp dụng những development-time defaults hỗ trợ thấy thay đổi nhanh hơn, trong đó có cấu hình giảm hoặc tắt cache cho một số template engine khi tương ứng.

Ví dụ khi dùng Thymeleaf, một cấu hình development thường thấy:

~~~properties
spring.thymeleaf.cache=false
~~~

Khi template mới được đưa vào location mà Thymeleaf đọc, yêu cầu HTTP tiếp theo có thể dùng template mới mà không cần context restart.

### Vì sao tôi đã sửa HTML nhưng trình duyệt vẫn hiển thị cũ?

Có thể do:

1. File chưa được copy vào output classpath.
2. Template engine vẫn cache bản cũ.
3. Browser cache đang giữ nội dung cũ.
4. Request đang dùng một view template khác.
5. LiveReload client không được kết nối.
6. File nằm ngoài resource locations được Spring sử dụng.
7. Một reverse proxy hoặc CDN đang cache response.

Không nên tăng restart frequency để giải quyết một vấn đề browser cache. Hãy xác định lớp đang giữ bản cũ.

## 29. LiveReload không phải lúc nào cũng cần

Nếu chỉ phát triển REST API và kiểm tra bằng curl/Postman, có thể không cần browser LiveReload. Khi đó, tắt LiveReload là lựa chọn đơn giản:

~~~yaml
spring:
  devtools:
    livereload:
      enabled: false
~~~

Nếu phát triển HTML/CSS trực tiếp, LiveReload có thể giúp cập nhật giao diện nhanh. Tuy nhiên, nếu dùng frontend framework có development server/hot module replacement riêng, có thể có **hai cơ chế reload cạnh tranh**.

Ví dụ:

~~~text
Vite / frontend dev server
         |
         +--> HMR cho JS/CSS
         |
Spring Boot DevTools
         |
         +--> Restart backend context
         +--> LiveReload notification
~~~

Trong kiến trúc đó, có thể chỉ cần DevTools cho Java backend và để frontend tooling quản lý HMR/browser refresh. Không nên dùng thêm LiveReload nếu làm mất state giao diện mỗi lần frontend rebuild.

## 30. Kích thước build và các đợt thay đổi liên tiếp

Một build có thể ghi:

~~~text
OrderController.class
OrderService.class
OrderRepository.class
application.yml
schema.json
templates/order.html
static/css/site.css
~~~

Watcher có thể thấy nhiều thay đổi trong một khoảng ngắn. Tùy cấu hình, một số chỉ LiveReload, một số yêu cầu restart. Nếu build ghi chậm hoặc từng file không liên tục, DevTools có thể restart nhiều lần.

Để giảm hiện tượng này:

- Đảm bảo IDE/build tool không sao chép lặp vô hạn.
- Dùng quiet period phù hợp.
- Thêm trigger file nếu muốn restart sau build hoàn chỉnh.
- Exclude nhóm generated assets không ảnh hưởng context.
- Không đặt build output trong một directory được chính build tool theo dõi đầu vào để tránh vòng lặp.
- Tránh một script cứ ghi lại timestamp của `application.yml` mà không có thay đổi nội dung thực.

### Lỗi vòng lặp restart

Ví dụ:

~~~text
Context startup
    |
    v
Một startup job ghi file dưới watched classpath
    |
    v
DevTools phát hiện thay đổi
    |
    v
Restart
    |
    v
Startup job ghi file lại
    |
    v
Restart tiếp...
~~~

Đây là lỗi thiết kế workflow. Cần chuyển file generated ra nơi không bị theo dõi, exclude đúng path hoặc tránh ghi file không cần thiết mỗi lần startup.

## 31. Chẩn đoán: sửa Java nhưng không restart

Giả sử bạn sửa:

~~~java
@Service
public class PriceService {

    public BigDecimal price() {
        return new BigDecimal("10.00");
    }
}
~~~

sang:

~~~java
@Service
public class PriceService {

    public BigDecimal price() {
        return new BigDecimal("12.00");
    }
}
~~~

Nhưng endpoint vẫn trả `10.00`.

Kiểm tra lần lượt:

1. Ứng dụng có `spring-boot-devtools` trên development runtime classpath không?
2. Automatic restart có đang enabled không?
3. Đang chạy từ IDE/exploded classpath hay một packaged JAR cũ?
4. IDE có biên dịch `PriceService.java` thành `PriceService.class` mới không?
5. File `.class` mới có nằm ở output directory được process đang chạy sử dụng không?
6. Output directory đó có bị phân chia classloader hoặc watcher khác dự kiến không?
7. Có cấu hình `trigger-file` khiến restart phải đợi cập nhật file kích hoạt không?
8. Có startup log thể hiện context restart không?
9. Ứng dụng có nhiều instance và bạn đang gửi request tới instance cũ không?
10. Có layer cache hoặc route khác đang trả dữ liệu cũ không?

**Đừng sửa `spring.devtools.restart.exclude` ngay ở bước đầu.** Nếu runtime classpath không đổi, nguyên nhân nằm ở compile/copy hoặc nơi chạy, không phải pattern exclusion.

## 32. Chẩn đoán: sửa CSS mà Spring lại restart toàn bộ

Nếu thay CSS mà Spring context restart:

- Kiểm tra CSS được copy tới path nào trong classpath.
- Xác định default exclusions có bị thay bằng `spring.devtools.restart.exclude` hay không.
- Kiểm tra artifact có nằm dưới `static`, `public` hoặc group default phù hợp không.
- Nếu CSS nằm trong một folder custom, thêm pattern qua `additional-exclude`.
- Xác định build tool có đồng thời thay class/config file khác không.

Ví dụ build frontend có thể vô tình ghi lại `application.yml` hoặc một generated Java class, khiến restart xảy ra dù CSS bản thân nó nằm trong folder excluded.

### Cách cấu hình thường phù hợp

~~~yaml
spring:
  devtools:
    restart:
      additional-exclude: "ui-output/**"
~~~

Điều này giữ default exclusions và bổ sung folder mới.

## 33. Chẩn đoán: trigger file không hoạt động

Một số nguyên nhân:

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Sửa Java vẫn restart ngay | Property trigger-file chưa được áp dụng hoặc file chưa được phát hiện | Kiểm tra Environment và classpath |
| Sửa Java không restart, touch trigger cũng không | Touch nhầm file source, output file không đổi | Xác định runtime trigger file |
| File tồn tại trong repository nhưng không được nhận | Build/IDE bỏ qua dotfile hoặc chưa copy | Kiểm tra output resources |
| Touch đúng file nhưng không thấy thay đổi | Timestamp resolution hoặc watcher không nhận | Thay đổi nội dung, kiểm tra mtime |
| Trigger hoạt động không đều | Nhiều output directories/instances, working directory khác | Xác định process và classpath thực |
| Restart xảy ra quá sớm khi build | Trigger được IDE cập nhật trước khi các file khác copy xong | Chỉ cập nhật sau build hoặc dùng script có thứ tự |
| Có browser reload nhưng không context restart | Chỉ có thay đổi thuộc nhóm excluded | Phân biệt LiveReload với restart |
| Không thấy browser reload | LiveReload client không kết nối hoặc disabled | Kiểm tra browser integration |

### Trigger file là tên file được tìm trên classpath

Nếu dùng:

~~~properties
spring.devtools.restart.trigger-file=.reloadtrigger
~~~

thì tên file cần khớp và file phải xuất hiện trong runtime classpath. Một file nằm ở thư mục cha không tự trở thành trigger chỉ vì tên đúng.

## 34. Chẩn đoán: additional-paths không được theo dõi

Cấu hình:

~~~properties
spring.devtools.restart.additional-paths=../shared-config
~~~

nhưng thay file trong đó không có tác dụng.

Nguyên nhân có thể:

- Relative path được giải quyết từ working directory khác dự kiến.
- Thư mục không tồn tại khi ứng dụng khởi động.
- Process không có quyền đọc hoặc truy cập.
- Đường dẫn là symlink/network mount với behavior khác local watcher.
- File bị exclude bởi một pattern hiện có.
- Trigger file đang yêu cầu chủ động kích hoạt.
- DevTools restart đang disabled.
- App không đọc lại nội dung file dù context đã restart.
- App đọc một bản copy khác của file đang chỉnh.

Để khoanh vùng, có thể thử dùng một đường dẫn tuyệt đối trong môi trường phát triển, xác định sự tồn tại và quyền truy cập, rồi quay về cách cấu hình portable hơn. Không hard-code đường dẫn máy cá nhân vào cấu hình chung của production.

### additional-paths không phải spring.config.import

Đặt:

~~~yaml
spring:
  devtools:
    restart:
      additional-paths:
        - ../shared-config
~~~

không khiến `shared-config/application.yml` tự được nhập vào Environment. Nếu muốn Spring Boot đọc một external config location, cần dùng property của cơ chế Config Data như `spring.config.import` hoặc `spring.config.additional-location` ở vị trí phù hợp.

## 35. Những hiểu nhầm quan trọng

### “DevTools tự compile Java khi tôi lưu”

Không đúng. DevTools quan sát các thay đổi trong những classpath directories phù hợp. Việc compile source thuộc về IDE hoặc build tool.

### “Exclude là không cho ứng dụng truy cập file”

Không đúng. Exclude của DevTools liên quan quyết định restart, không phải một bộ lọc HTTP hoặc cấu hình resource packaging.

### “Đổi template mà không restart nghĩa là DevTools bị lỗi”

Không nhất thiết. Template và static assets thường thuộc nhóm tài nguyên không cần full restart. Nếu browser không thấy thay đổi, kiểm tra output resource, cache và LiveReload.

### “additional-paths đưa file vào classpath”

Không đúng. Nó thêm đường dẫn được theo dõi, không tự biến tài nguyên thành classpath resource hoặc Spring configuration.

### “Trigger file làm Java source tự nạp lại”

Không đúng. Source phải được compile/copy thành runtime output trước; trigger chỉ quyết định thời điểm restart.

### “Có trigger-file thì mọi lần touch đều chắc chắn restart”

Không nên giả định. Kết quả phụ thuộc file được tìm và theo dõi thế nào, thay đổi nào đã được ghi nhận và configuration của phiên bản DevTools.

### “spring.devtools.restart.exclude và restart.exclude.* có cùng nghĩa”

Không đúng. Property thứ nhất là resource change exclusion; `restart.exclude.*` trong `META-INF/spring-devtools.properties` liên quan việc phân chia classloader.

### “Đổi file YAML sẽ tự cập nhật bean mà không restart”

Không nhất thiết. Bean đã được khởi tạo và bound thường không tự nhận giá trị mới chỉ vì file trên đĩa đổi. Restart tạo lại context là cách DevTools thường giúp cập nhật cấu hình phát triển.

### “DevTools restart giống triển khai nóng trên production”

Không đúng. DevTools là công cụ phát triển, không thay thế deployment strategy, rolling update hoặc process supervision.

## 36. Khi kết hợp DevTools với test và build

Một vòng lặp development thông thường gồm:

~~~text
Sửa code
   |
   v
Compile / build output
   |
   +--> DevTools restart để thử nhanh thủ công
   |
   +--> Unit/integration tests để xác nhận hành vi
   |
   +--> Build artifact phục vụ deployment
~~~

DevTools restart **không chứng minh code mới compile đúng toàn bộ module**, không kiểm tra mọi test và không thay thế một build sạch trước khi release.

Nếu đang debug một hành vi chỉ xuất hiện khi DevTools restart mà không xuất hiện khi cold start, cần xem:

- Trạng thái static/cache giữ trong base classloader.
- Bean cleanup có giải phóng thread/resource không.
- Thư viện dùng custom classloader hoặc serialization.
- File generated bị thay đổi giữa các lượt.
- Môi trường chạy local khác packaged deployment ở đâu.

Để so sánh, có thể tạm tắt restart và khởi động một process mới. Đây là kỹ thuật chẩn đoán, không phải lời khuyên tắt DevTools trong mọi tình huống.

## 37. Cấu hình theo môi trường phát triển

DevTools hướng tới môi trường local. Một nhóm phát triển có thể thống nhất cấu hình:

~~~yaml
spring:
  devtools:
    restart:
      additional-exclude: "generated-docs/**,ui-build/**"
      trigger-file: ".reloadtrigger"
      poll-interval: 2s
      quiet-period: 1s
    livereload:
      enabled: false
~~~

Nhưng không nhất thiết mọi dự án đều cần toàn bộ property này. Ví dụ:

- Dự án nhỏ có thể chỉ cần DevTools mặc định.
- Dự án nhiều resource generated nên có `additional-exclude`.
- Dự án build nhiều đợt nên cân nhắc `trigger-file`.
- Dự án có frontend HMR riêng có thể tắt LiveReload.
- Dự án có external templates nên dùng `additional-paths` nếu thực sự cần quan sát.

Nên đặt cấu hình theo workflow của nhóm và phân biệt rõ local-only defaults với cấu hình cần triển khai.

### Không đưa cấu hình máy cá nhân vào bản phát hành

Tránh:

~~~yaml
spring:
  devtools:
    restart:
      additional-paths: "C:/Users/someone/Desktop/shared-config"
~~~

trong cấu hình chung của ứng dụng. Mỗi developer có thể có working directory khác nhau. Hãy ưu tiên đường dẫn tương đối ổn định, environment-specific properties hoặc launcher configuration phù hợp.

## 38. Một bài thực hành theo từng loại thay đổi

Giả sử ứng dụng có endpoint:

~~~java
@RestController
@RequestMapping("/api/greeting")
public class GreetingController {

    @GetMapping
    public Map<String, String> greeting() {
        return Map.of("message", "Hello");
    }
}
~~~

Và static file:

~~~text
src/main/resources/static/css/site.css
~~~

Cấu hình:

~~~yaml
spring:
  devtools:
    restart:
      additional-exclude: "generated-docs/**"
      trigger-file: ".reloadtrigger"
~~~

### Thí nghiệm A: sửa controller

Thay:

~~~java
return Map.of("message", "Hello");
~~~

thành:

~~~java
return Map.of("message", "Hello, DevTools");
~~~

Sau đó biên dịch để output `GreetingController.class` đổi. Nếu dùng trigger-file, cập nhật file trigger trên classpath sau build. Khi context restart hoàn tất, lời gọi endpoint mới có thể trả nội dung mới.

### Thí nghiệm B: sửa CSS

Thay một thuộc tính:

~~~css
body {
    background-color: #fafafa;
}
~~~

sang:

~~~css
body {
    background-color: #f0f0f0;
}
~~~

Đảm bảo file được copy hoặc phục vụ từ location có nội dung mới. Nếu static path được loại trừ khỏi restart, Spring context không cần được dựng lại chỉ vì CSS đổi. Trình duyệt có thể cần refresh hoặc LiveReload client.

### Thí nghiệm C: sửa cấu hình

Thêm vào `application.yml`:

~~~yaml
app:
  greeting:
    message: "Good morning"
~~~

Nếu bean đọc cấu hình này khi khởi tạo, context cần được tạo lại để binding và điều kiện bean phản ánh giá trị mới, trừ khi ứng dụng có cơ chế refresh runtime riêng. Nếu dùng trigger, cập nhật trigger sau khi resource output mới sẵn sàng.

### Thí nghiệm D: sửa file generated-docs

Tạo một file trong output resource folder:

~~~text
generated-docs/index.html
~~~

Nếu pattern `generated-docs/**` match, thay file này không nên làm full context restart chỉ vì resource change. Cần đảm bảo ứng dụng thực sự có khả năng phục vụ/đọc file mới nếu muốn thấy kết quả.

### Thí nghiệm E: kiểm tra đúng trigger

Khi sửa Java mà chưa cập nhật trigger, quan sát ứng dụng có đang đợi hay không. Sau đó cập nhật đúng trigger file trên classpath; điều này giúp xác nhận hai cơ chế đã được phân biệt.

Bài thực hành trên có mục tiêu hiểu **quan hệ giữa file change, compile/copy, watcher, restart và browser reload**, không phải chỉ nhìn thấy một dòng log và kết luận toàn bộ hệ thống hoạt động.

## 39. Bảng chẩn đoán nhanh

| Hiện tượng | Khả năng thường gặp | Việc nên làm |
|---|---|---|
| Java code đã sửa nhưng behavior cũ | Chưa compile hoặc process dùng JAR cũ | Kiểm tra output `.class` và runtime classpath |
| Java đã compile nhưng chưa restart | Trigger đang đợi hoặc watcher disabled | Kiểm tra `trigger-file` và restart setting |
| Mọi lần đổi CSS đều restart | Exclude mặc định bị thay hoặc build cũng đổi file khác | Dùng `additional-exclude` và kiểm tra output |
| CSS mới không thấy | File chưa copy, browser cache hoặc LiveReload chưa nối | Kiểm tra resource runtime và client |
| Template mới không thấy | Template cache hoặc path sai | Kiểm tra engine/cache/output |
| External config đổi không có tác dụng | Chưa được theo dõi hoặc chưa được load | Phân biệt `additional-paths` và Config Data |
| Trigger file không được tìm | File chỉ tồn tại trong source | Xác minh classpath output |
| Restart nhiều lần trong một build | Build ghi theo nhiều đợt | Quiet period hoặc trigger file |
| ClassCastException chỉ sau restart | Classloader split hoặc static reference cũ | Xem `spring-devtools.properties` và lifecycle |
| Restart loop | Startup ghi file bị theo dõi | Chuyển location hoặc exclude đúng tài nguyên |
| Không có LiveReload | Chưa có browser client hoặc tính năng disabled | Kiểm tra browser/DevTools configuration |
| Behavior khác khi chạy JAR | Packaged classpath và DevTools behavior khác | So sánh môi trường phát triển và release |
| Tắt restart qua YAML nhưng còn restart-related classloader | Khởi tạo restart infrastructure từ sớm | Dùng system property trước run nếu cần disable hoàn toàn |
| Tài nguyên bị loại trừ nhưng vẫn restart | Class/config khác cũng thay đổi trong build | Xem toàn bộ đợt file changes |
| `additional-paths` không thấy file | Relative path/permission/symlink sai | Xác nhận working directory và path thực |

## 40. Các nguyên tắc thiết kế cần nhớ

1. **DevTools không phải compiler.** Đảm bảo IDE hoặc build tool cập nhật runtime classpath trước khi mong restart.
2. **Restart dựa trên thay đổi của những đường dẫn được theo dõi.** Không phải mọi source file đều được watcher nhìn trực tiếp.
3. **Giữ default excludes nếu chỉ muốn thêm loại trừ.** Dùng `additional-exclude` trước `exclude`.
4. **Không loại trừ tài nguyên ảnh hưởng bean graph mà không có chiến lược reload.** Ví dụ configuration properties cần được bind lại.
5. **Dùng `additional-paths` để theo dõi nguồn ngoài**, nhưng nhớ nó không tự load file vào Environment/classpath.
6. **Dùng trigger file khi muốn kiểm soát thời điểm restart.** Nó hữu ích cho build nhiều bước hoặc IDE tự build liên tục.
7. **Trigger file phải được tìm thấy trên runtime classpath.** Tạo file trong source thôi chưa đủ nếu output chưa cập nhật.
8. **Phân biệt LiveReload với ApplicationContext restart.** Browser refresh không có nghĩa bean đã được tạo lại.
9. **Tính đến caching của template/browser.** Một resource mới có thể tồn tại trên disk nhưng chưa được client nhìn thấy.
10. **Điều chỉnh poll interval và quiet period có chủ đích.** Tránh restart quá sớm hoặc bị trì hoãn không cần thiết.
11. **Phân biệt resource exclusions với classloader include/exclude.** Hai nhóm property giải quyết hai vấn đề khác nhau.
12. **Kiểm tra runtime classpath trong multi-module.** JAR dependency và open project directory có behavior khác nhau.
13. **Đảm bảo lifecycle cleanup.** Restart lặp lại có thể làm lộ lỗi background thread hoặc static cache bị giữ.
14. **Không coi DevTools là hot deployment production.** Quy trình release dùng artifact và orchestration riêng.
15. **Dùng cấu hình đơn giản nhất đáp ứng workflow.** Không thêm mọi property chỉ vì DevTools hỗ trợ chúng.
16. **Khi có lỗi, xác định lớp nào chưa cập nhật.** Source, build output, watcher, context, resource cache và browser là các giai đoạn khác nhau.

## Kết luận

Spring Boot DevTools giúp rút ngắn vòng lặp phát triển bằng cách quan sát các thay đổi trên development classpath và **restart ApplicationContext khi cần**. Những thay đổi ở class Java hoặc cấu hình Spring thường cần restart, trong khi static assets và templates thường không cần khởi tạo lại toàn bộ bean graph. Vì vậy DevTools có các mặc định loại trừ tài nguyên khỏi restart.

`spring.devtools.restart.exclude` cho phép định nghĩa danh sách exclusions, còn `spring.devtools.restart.additional-exclude` dùng khi muốn **bổ sung** mà vẫn giữ các mặc định. `spring.devtools.restart.additional-paths` mở rộng vùng theo dõi sang thư mục ngoài classpath thông thường, nhưng không tự nạp dữ liệu từ thư mục đó vào ứng dụng. `spring.devtools.restart.trigger-file` cho phép developer chủ động đánh dấu thời điểm phù hợp để restart sau khi build/copy hoàn tất.

Khi gặp tình huống “đã sửa file nhưng ứng dụng chưa thay đổi”, hãy đi theo chuỗi **source → compile/copy → runtime classpath → DevTools watcher → context restart hoặc LiveReload → browser/cache**. Xác định đúng giai đoạn chưa được cập nhật sẽ giúp giải quyết vấn đề nhanh hơn nhiều so với việc tăng số lần restart hoặc thêm exclusions không có căn cứ. Sử dụng đúng những cơ chế này giúp Spring Boot giữ được tốc độ phản hồi cao trong development mà vẫn tách biệt rõ với vòng đời triển khai production.
