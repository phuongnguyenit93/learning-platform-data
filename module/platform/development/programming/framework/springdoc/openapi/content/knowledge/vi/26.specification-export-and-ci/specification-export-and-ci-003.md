# Nguyên lý plugin Springdoc: chạy ứng dụng rồi lấy đặc tả qua HTTP

Plugin xuất đặc tả của springdoc-openapi hoạt động theo một nguyên lý đơn giản: **ứng dụng Spring Boot phải chạy trước, sau đó plugin gửi HTTP request tới endpoint OpenAPI và lưu response thành file**. Plugin không đọc mã nguồn controller để tự dựng tài liệu, không thay thế thư viện springdoc chạy trong ứng dụng và cũng không tự khởi động một server chỉ bằng việc khai báo dependency plugin.

Điều này có ý nghĩa quan trọng khi đưa việc xuất OpenAPI vào Maven hoặc CI. Kết quả được lấy từ ứng dụng đang chạy với profile, cấu hình, bean, route, security, dữ liệu và dependency thực tế của lần khởi động đó. Nếu ứng dụng chưa sẵn sàng, endpoint bị chặn hoặc đang chạy sai profile, file được xuất có thể thất bại hoặc không phản ánh hợp đồng mà nhóm mong muốn.

Bài học sử dụng springdoc-openapi-maven-plugin để minh họa. Plugin này gọi endpoint HTTP như /v3/api-docs, nhận nội dung OpenAPI JSON và ghi ra thư mục build. Vì vậy, cần phối hợp ba phần: springdoc runtime trong ứng dụng, cơ chế khởi động/dừng ứng dụng trong Maven và plugin HTTP fetch ở giai đoạn thích hợp của Maven lifecycle.

## 1. Có hai thành phần Springdoc khác nhau

Trong một dự án Maven, cần phân biệt thư viện chạy cùng ứng dụng và plugin chạy trong quá trình build:

| Thành phần | Nơi hoạt động | Trách nhiệm |
|---|---|---|
| springdoc runtime starter | Classpath của Spring Boot application | Phát hiện controller, DTO, annotation và sinh OpenAPI document tại runtime |
| springdoc-openapi-maven-plugin | Maven build process | Gửi HTTP request tới URL OpenAPI và lưu response thành file |

Ví dụ dependency runtime cho Spring MVC:

~~~xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
    <version>${springdoc.version}</version>
</dependency>
~~~

Nếu ứng dụng không cần Swagger UI nhưng vẫn cần endpoint JSON/YAML, có thể chọn starter API tương ứng với web stack. Điều quan trọng là ứng dụng phải có springdoc runtime để cung cấp endpoint mà plugin sẽ gọi.

Plugin Maven được khai báo trong phần build/plugins, không thay thế dependency runtime:

~~~xml
<plugin>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-maven-plugin</artifactId>
    <version>1.4</version>
</plugin>
~~~

Version của plugin Maven và version của starter runtime thuộc hai artifact khác nhau. Không suy ra rằng chúng phải có cùng số version. Hãy chọn từng version theo tài liệu tương thích và dependency management của dự án.

## 2. Plugin không phân tích source code để tạo tài liệu

Khi Maven chạy plugin, plugin không quét các file Java như @RestController, @GetMapping hoặc @Schema để tự tạo OpenAPI. Việc phân tích controller và mô hình dữ liệu đã được springdoc runtime thực hiện khi ứng dụng khởi động và xử lý request tài liệu.

Luồng thực tế:

~~~text
Maven build
   |
   | 1. Khởi động Spring Boot application
   v
Spring Boot process
   |
   | springdoc runtime phát hiện controller, DTO,
   | annotation, cấu hình và các route đang hoạt động
   v
OpenAPI endpoint: /v3/api-docs
   ^
   | 2. HTTP GET từ Maven plugin
   |
springdoc-openapi-maven-plugin
   |
   | 3. Lưu response body
   v
target/openapi.json
~~~

Nếu ứng dụng không khởi động, không có endpoint OpenAPI để lấy. Nếu ứng dụng chạy nhưng springdoc runtime không được nạp, plugin không thể tự bổ sung khả năng sinh tài liệu.

Do đó, câu hỏi đầu tiên khi plugin thất bại là: URL được cấu hình có trả về OpenAPI document hợp lệ từ một ứng dụng đang chạy hay không?

## 3. HTTP fetch là bước trung tâm

Với cấu hình mặc định của springdoc, endpoint JSON thường là:

~~~text
http://localhost:8080/v3/api-docs
~~~

Plugin thực hiện request HTTP tới URL này. Response body thường là một OpenAPI document dạng JSON. Plugin ghi nội dung nhận được vào file được cấu hình qua outputFileName và outputDir.

Có thể mô phỏng bước plugin bằng curl:

~~~bash
curl -i http://localhost:8080/v3/api-docs
~~~

Một response thành công thường có:

- HTTP status thuộc nhóm 2xx, thông thường là 200.
- Content-Type tương ứng với JSON.
- Body có trường openapi, info và paths.
- Nội dung là OpenAPI document, không phải trang HTML đăng nhập hoặc trang lỗi.

Plugin thực hiện HTTP fetch nên phụ thuộc vào network, host, port, context path, authentication và trạng thái sẵn sàng của ứng dụng. Nó không có khả năng bỏ qua các lớp đó để đọc trực tiếp bean hoặc controller.

## 4. Endpoint phải tồn tại khi plugin chạy

Ứng dụng cần bật endpoint OpenAPI:

~~~yaml
springdoc:
  api-docs:
    enabled: true
~~~

Nếu đặt springdoc.api-docs.enabled: false, endpoint /v3/api-docs không còn được cung cấp theo cấu hình mặc định. Khi đó plugin không thể lấy đặc tả từ URL này.

Swagger UI không bắt buộc đối với việc xuất JSON. Có thể tắt giao diện và giữ endpoint tài liệu:

~~~yaml
springdoc:
  swagger-ui:
    enabled: false
  api-docs:
    enabled: true
~~~

Đây thường là lựa chọn phù hợp cho CI: ứng dụng chỉ cần cung cấp OpenAPI document để plugin tải xuống. Không cần đóng gói tài nguyên giao diện nếu pipeline không dùng Swagger UI.

Nếu thay đổi springdoc.api-docs.path, URL trong cấu hình plugin phải đổi theo. Ví dụ:

~~~yaml
springdoc:
  api-docs:
    path: /internal/openapi
~~~

Khi đó, plugin cần gọi /internal/openapi, không thể tiếp tục mặc định /v3/api-docs.

## 5. Vì sao cần khởi động ứng dụng trước?

Springdoc thường sinh tài liệu từ ApplicationContext đang hoạt động. Quá trình này có thể phụ thuộc vào:

- Bean controller và handler được tạo theo profile.
- Jackson configuration và module serialize.
- Bean Validation và metadata DTO.
- GroupedOpenApi và các OpenApiCustomizer.
- Security scheme và cấu hình OAuth2.
- Web stack MVC hoặc WebFlux.
- Context path, server port và forwarded headers.
- Feature flag, conditional bean và cấu hình môi trường.

Các thông tin này chỉ có đầy đủ sau khi ứng dụng khởi tạo. Việc chạy plugin khi server chưa bắt đầu phục vụ request sẽ không tạo được tài liệu.

Ngoài ra, nếu một controller hoặc bean chỉ được đăng ký trong profile contract, profile phải được bật khi ứng dụng khởi động. Plugin không tự suy luận profile mong muốn từ tên file OpenAPI.

## 6. Plugin Maven không tự khởi động Spring Boot

Đây là nhầm lẫn phổ biến. springdoc-openapi-maven-plugin chỉ lấy tài liệu qua HTTP. Để tự động hóa toàn bộ trong một lệnh Maven, cần một thành phần khác khởi động ứng dụng.

Spring Boot Maven Plugin cung cấp các goal start và stop, có thể gắn vào Maven lifecycle:

| Maven phase | Công việc |
|---|---|
| pre-integration-test | Khởi động Spring Boot application |
| integration-test | Springdoc Maven plugin gọi OpenAPI endpoint và lưu file |
| post-integration-test | Dừng ứng dụng đã khởi động |
| verify | Hoàn tất các bước kiểm tra và xác minh build |

Việc tách trách nhiệm giúp dễ chẩn đoán: Spring Boot Maven Plugin quản lý tiến trình ứng dụng, còn Springdoc Maven Plugin chỉ thực hiện HTTP fetch.

## 7. Cấu hình Maven tối thiểu cho việc xuất OpenAPI

Ví dụ dưới đây minh họa một ứng dụng Spring Boot Maven project chạy trên cổng 8080:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.springdoc</groupId>
            <artifactId>springdoc-openapi-maven-plugin</artifactId>
            <version>1.4</version>
            <executions>
                <execution>
                    <id>export-openapi</id>
                    <phase>integration-test</phase>
                    <goals>
                        <goal>generate</goal>
                    </goals>
                </execution>
            </executions>
            <configuration>
                <apiDocsUrl>http://localhost:8080/v3/api-docs</apiDocsUrl>
                <outputFileName>openapi.json</outputFileName>
                <outputDir>${project.build.directory}</outputDir>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

Các thuộc tính chính:

| Thuộc tính | Ý nghĩa |
|---|---|
| apiDocsUrl | URL HTTP mà plugin gọi để lấy đặc tả |
| outputFileName | Tên file được tạo |
| outputDir | Thư mục lưu file |
| phase | Giai đoạn Maven lifecycle chạy goal |
| goal generate | Thực hiện việc lấy và lưu tài liệu |

Ví dụ dùng project.build.directory nên file thường nằm ở target/openapi.json. Không ghi file sinh tự động vào src/main/resources hoặc thư mục source chỉ để tiện tìm; thư mục build phù hợp hơn vì file có thể được tạo lại ở mỗi lần chạy.

## 8. Kết hợp Spring Boot Maven Plugin để start và stop

Để một lệnh mvn verify có thể tự khởi động ứng dụng, cấu hình Spring Boot Maven Plugin:

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <executions>
        <execution>
            <id>start-application-for-openapi</id>
            <phase>pre-integration-test</phase>
            <goals>
                <goal>start</goal>
            </goals>
        </execution>
        <execution>
            <id>stop-application-after-openapi</id>
            <phase>post-integration-test</phase>
            <goals>
                <goal>stop</goal>
            </goals>
        </execution>
    </executions>
    <configuration>
        <jvmArguments>-Dspring.profiles.active=contract</jvmArguments>
    </configuration>
</plugin>
~~~

Goal start khởi chạy ứng dụng ở tiến trình riêng để Maven tiếp tục thực hiện các goal trong lifecycle. Goal stop yêu cầu tiến trình đã được plugin quản lý dừng lại.

Profile contract trong ví dụ là profile dành cho việc tạo hợp đồng. Hãy định nghĩa profile này trong cấu hình ứng dụng sao cho endpoint OpenAPI hoạt động và các phụ thuộc cần thiết đã sẵn sàng.

Kết hợp cấu hình start/stop này với plugin Springdoc ở mục trước. Khi chạy mvn verify, Maven đi qua pre-integration-test, khởi động ứng dụng, tới integration-test để fetch OpenAPI, rồi tới post-integration-test để dừng ứng dụng nếu lifecycle hoàn tất bình thường.

Nếu goal export hoặc một bước integration test thất bại sớm, Maven có thể dừng lifecycle trước khi đến post-integration-test. CI nên có cơ chế cleanup tiến trình ở mức job hoặc runner để tránh để lại server chạy nền sau một build lỗi.

## 9. Thứ tự Maven lifecycle quyết định kết quả

Một cấu hình đúng nhưng gắn sai phase vẫn có thể thất bại. Ví dụ, nếu plugin generate chạy ở package nhưng ứng dụng chỉ được start ở pre-integration-test, thứ tự lifecycle không còn phù hợp với ý định.

Thứ tự thông thường nên là:

~~~text
validate
  |
compile
  |
test
  |
package
  |
pre-integration-test
  |-- spring-boot:start
  |
integration-test
  |-- springdoc-openapi:generate
  |
post-integration-test
  |-- spring-boot:stop
  |
verify
~~~

Đặt goal generate tại integration-test giúp nó chạy sau bước start ở pre-integration-test. Nếu có thêm Failsafe hoặc plugin kiểm thử tích hợp, hãy xem thứ tự execution trong POM và bảo đảm server đã sẵn sàng trước khi các request được gửi.

Không nên chỉ chạy mvn package rồi mong plugin gắn ở integration-test tự chạy. package dừng trước pre-integration-test và integration-test. Dùng mvn verify để đi qua đầy đủ các phase cần thiết.

## 10. Kiểm tra ứng dụng đã sẵn sàng nhận request

Goal start quản lý tiến trình Spring Boot, nhưng việc một tiến trình đã khởi chạy không đồng nghĩa mọi phụ thuộc nghiệp vụ đã sẵn sàng.

Ứng dụng có thể cần:

- Kết nối database và chạy migration.
- Khởi tạo cache hoặc message broker.
- Đăng ký client với dịch vụ khác.
- Tải cấu hình từ secret/config server.
- Khởi tạo bean tùy biến được dùng khi sinh schema.
- Chờ một cổng hoặc endpoint health sẵn sàng.

Nếu plugin fetch ngay khi endpoint chưa sẵn sàng, build có thể nhận connection refused, timeout hoặc lỗi 5xx.

Có thể kiểm tra readiness trước khi fetch:

~~~bash
curl --fail --silent --show-error http://localhost:8080/actuator/health/readiness
~~~

Endpoint readiness chỉ có nếu ứng dụng đã bật và cấu hình Spring Boot Actuator phù hợp. Nếu không dùng Actuator, có thể dùng một health endpoint riêng hoặc script polling endpoint OpenAPI với timeout hữu hạn.

Không dùng vòng lặp polling vô hạn. CI cần thời hạn chờ rõ ràng và phải in log ứng dụng khi hết thời gian để người phát triển tìm được nguyên nhân.

## 11. Cổng và địa chỉ phải khớp

apiDocsUrl phải trỏ tới đúng host, port, context path và endpoint của ứng dụng đã khởi động.

Ví dụ:

~~~yaml
server:
  port: 8091
  servlet:
    context-path: /store
~~~

Với Spring MVC, URL tài liệu sẽ gồm context path:

~~~text
http://localhost:8091/store/v3/api-docs
~~~

Khi đó, cấu hình apiDocsUrl phải dùng URL đầy đủ tương ứng. Nếu cấu hình vẫn gọi http://localhost:8080/v3/api-docs, plugin sẽ gọi nhầm địa chỉ.

Với WebFlux, cách cấu hình context path có thể khác tùy phiên bản Spring Boot; hãy xác định URL thực tế mà server đang phục vụ thay vì sao chép cấu hình servlet MVC.

Trong CI, dùng một cổng riêng và ổn định cho tiến trình export. Nếu dùng server.port=0, Spring chọn cổng ngẫu nhiên; plugin không thể tự đoán cổng đó từ một URL cố định. Muốn dùng cổng ngẫu nhiên, cần một bước điều phối lấy cổng thực tế rồi truyền URL tương ứng cho plugin.

## 12. Profile và cấu hình môi trường ảnh hưởng tới đặc tả

OpenAPI được lấy từ ứng dụng đang chạy, vì vậy tài liệu phụ thuộc profile đang active.

Ví dụ:

~~~yaml
spring:
  config:
    activate:
      on-profile: contract

springdoc:
  api-docs:
    enabled: true
  swagger-ui:
    enabled: false
~~~

Trong profile contract, nhóm có thể bật endpoint tài liệu và tắt giao diện UI. Các controller hoặc bean cần có mặt trong hợp đồng phải được đăng ký trong profile này.

Nếu ứng dụng dùng profile prod khi export, tài liệu có thể phản ánh route, security hoặc feature flag dành cho production. Nếu dùng profile dev, có thể xuất hiện endpoint thử nghiệm không được phép công bố.

Hãy tạo profile dành riêng cho contract nếu cần một cấu hình ổn định, có chủ đích. Không nên dựa vào profile mặc định của máy phát triển vì nó có thể khác CI.

## 13. Dữ liệu và dịch vụ phụ thuộc trong lúc khởi động

Mặc dù springdoc không cần gọi mọi operation nghiệp vụ để sinh schema, ApplicationContext vẫn phải khởi động thành công. Nếu bean controller phụ thuộc database, service discovery hoặc secret manager, các phụ thuộc đó có thể ảnh hưởng khả năng start.

Một số cách chuẩn bị môi trường:

- Dùng database riêng cho contract test.
- Dùng Testcontainers hoặc service container do CI quản lý.
- Dùng dữ liệu khởi tạo cố định và có thể tái tạo.
- Stub các dịch vụ bên ngoài nếu chúng không liên quan tới việc tạo schema.
- Không dùng dữ liệu production để export hợp đồng.
- Đảm bảo migration và seed data hoàn tất trước khi gọi endpoint.

Nếu schema được tùy biến dựa trên dữ liệu runtime, hãy xác định rõ dữ liệu nào ảnh hưởng tới kết quả. OpenAPI lý tưởng nên ổn định theo version code và cấu hình contract, không thay đổi bất ngờ theo dữ liệu cá nhân trong database.

## 14. Chọn JSON hoặc YAML làm output

Endpoint mặc định /v3/api-docs thường trả JSON. Nếu ứng dụng hỗ trợ endpoint YAML, có thể cấu hình plugin lấy URL đó:

~~~xml
<configuration>
    <apiDocsUrl>http://localhost:8080/v3/api-docs.yaml</apiDocsUrl>
    <outputFileName>openapi.yaml</outputFileName>
    <outputDir>${project.build.directory}</outputDir>
</configuration>
~~~

Kết quả mong đợi là file YAML trong thư mục build. Cần kiểm tra endpoint YAML thực sự được cung cấp bởi phiên bản và cấu hình runtime đang dùng.

JSON thường thuận tiện cho script, công cụ tự động và xử lý bằng jq. YAML dễ đọc khi review thủ công. Cả hai định dạng phải mô tả cùng một OpenAPI document.

Không đổi đuôi file JSON thành .yaml để giả lập YAML. Định dạng file phải khớp response body nhận được từ endpoint.

## 15. Đặt tên và vị trí file xuất

Plugin cho phép cấu hình tên file và thư mục đầu ra:

~~~xml
<configuration>
    <apiDocsUrl>http://localhost:8080/v3/api-docs</apiDocsUrl>
    <outputFileName>store-openapi.json</outputFileName>
    <outputDir>${project.build.directory}/openapi</outputDir>
</configuration>
~~~

Với cấu hình này, file dự kiến nằm ở:

~~~text
target/openapi/store-openapi.json
~~~

Nên lưu file sinh tự động trong target hoặc một thư mục build tương đương. Maven có thể xóa thư mục này khi chạy clean, nên không đặt tài liệu nguồn duy nhất ở đây.

Nếu muốn commit một bản hợp đồng vào Git, hãy tạo một bước copy có chủ đích từ artifact build sang thư mục được quản lý phiên bản sau khi validation thành công. Không để plugin ghi đè trực tiếp tài liệu đang được review trong source tree ở mỗi lần build.

## 16. Xuất nhiều document group

Nếu ứng dụng khai báo nhiều GroupedOpenApi, mỗi group có endpoint riêng, thường theo dạng:

~~~text
/v3/api-docs/public
/v3/api-docs/partner
/v3/api-docs/internal
~~~

Plugin chỉ lấy URL được cấu hình cho lần chạy đó. Nếu cần xuất nhiều group, cần tạo các execution riêng với URL và tên file khác nhau, hoặc chạy plugin nhiều lần với cấu hình tương ứng.

Ví dụ về ý tưởng cấu hình:

~~~xml
<executions>
    <execution>
        <id>export-public-api</id>
        <phase>integration-test</phase>
        <goals>
            <goal>generate</goal>
        </goals>
        <configuration>
            <apiDocsUrl>http://localhost:8080/v3/api-docs/public</apiDocsUrl>
            <outputFileName>public-api.json</outputFileName>
            <outputDir>${project.build.directory}/openapi</outputDir>
        </configuration>
    </execution>
    <execution>
        <id>export-partner-api</id>
        <phase>integration-test</phase>
        <goals>
            <goal>generate</goal>
        </goals>
        <configuration>
            <apiDocsUrl>http://localhost:8080/v3/api-docs/partner</apiDocsUrl>
            <outputFileName>partner-api.json</outputFileName>
            <outputDir>${project.build.directory}/openapi</outputDir>
        </configuration>
    </execution>
</executions>
~~~

Đây là mẫu tổ chức các execution; hãy kiểm tra cách plugin version đang dùng áp dụng cấu hình theo từng execution và tránh để cấu hình cấp plugin ghi đè ngoài ý muốn. Tên output phải duy nhất để các execution không ghi đè file của nhau.

Group internal có thể chứa endpoint nhạy cảm. Chỉ xuất và lưu trữ group đó trong artifact hoặc pipeline có quyền truy cập phù hợp.

## 17. Authentication và bảo vệ endpoint tài liệu

Plugin là một HTTP client. Nếu /v3/api-docs yêu cầu authentication, request từ plugin cũng phải đáp ứng chính sách đó.

Các lỗi thường gặp:

- HTTP 401 vì request không có credential.
- HTTP 403 vì tài khoản CI thiếu authority.
- HTTP 302 tới trang đăng nhập HTML.
- Gateway chặn request từ runner.
- Token hết hạn trước khi plugin fetch.

Trong môi trường contract test, có thể chọn một trong các cách:

1. Cho phép endpoint tài liệu từ network nội bộ của runner và chỉ trong profile contract.
2. Cấp quyền đọc tài liệu cho một service identity dành riêng cho CI.
3. Cấu hình HTTP header xác thực nếu phiên bản plugin đang dùng hỗ trợ truyền headers.
4. Dùng một bước HTTP fetch riêng có thể truyền credential an toàn, rồi lưu response thành artifact.

Không hardcode token hoặc password trong POM được commit vào Git. Dùng secret store của CI và giới hạn quyền của credential chỉ đủ để đọc tài liệu. Không vô hiệu hóa toàn bộ Spring Security trong profile export nếu không cần thiết.

Nếu dùng một profile chỉ cho phép tài liệu từ localhost, hãy bảo đảm server chỉ được mở trong môi trường build cô lập và không phát hành profile đó vào production.

## 18. Network và môi trường chạy CI

localhost trong apiDocsUrl là máy hoặc network namespace nơi Maven plugin đang chạy. Trong CI container, localhost trỏ tới chính container đó, không nhất thiết trỏ tới máy host hoặc container Spring Boot khác.

Nếu ứng dụng và Maven chạy trong cùng container, localhost thường phù hợp. Nếu chạy trong hai container khác nhau:

- Dùng hostname service trong network của CI, ví dụ http://store-app:8080/v3/api-docs.
- Đảm bảo service container đã start và health check thành công.
- Mở đúng port giữa các container.
- Không dùng địa chỉ localhost từ container Maven để gọi container ứng dụng khác.

Nếu dùng Kubernetes job hoặc môi trường runner phân tán, xác định rõ DNS và network policy. Một request chạy được trên máy lập trình viên chưa chắc chạy được từ runner.

## 19. Một lệnh build hoàn chỉnh

Khi đã cấu hình Spring Boot start/stop và Springdoc generate theo các phase tương ứng, lệnh thường dùng là:

~~~bash
mvn clean verify
~~~

Lệnh này thực hiện các phase trước đó, gồm compile, test, package, khởi động ứng dụng ở pre-integration-test, lấy OpenAPI ở integration-test, dừng ứng dụng ở post-integration-test và chạy các bước verify được cấu hình.

Nếu chỉ chạy:

~~~bash
mvn springdoc-openapi:generate
~~~

thì goal generate được gọi trực tiếp, nhưng không có nghĩa Maven đã tự chạy Spring Boot trước đó. Ứng dụng phải được khởi động riêng và URL phải truy cập được.

Khi debug, có thể chạy ứng dụng ở terminal riêng rồi gọi plugin. Sau khi đã xác nhận HTTP endpoint hoạt động, mới đưa bước start/fetch/stop vào lifecycle tự động.

## 20. Xác minh file được tạo

Sau khi build, kiểm tra file output:

~~~text
target/openapi/openapi.json
~~~

Có thể kiểm tra nhanh bằng:

~~~bash
test -s target/openapi/openapi.json
jq -e '.openapi and .info and .paths' target/openapi/openapi.json
~~~

Lệnh đầu xác nhận file tồn tại và không rỗng. Lệnh thứ hai kiểm tra một số cấu trúc cơ bản trong JSON. Đây mới là smoke check; nó không thay thế OpenAPI validator.

Hãy kiểm tra thêm:

- openapi có version dự kiến.
- info.title và info.version đúng.
- Các path quan trọng có mặt.
- Method và operationId không bị thiếu.
- Request body và response schema đúng.
- Security scheme và scope không bị mất.
- Group chứa đúng endpoint.
- Không có HTML login page hoặc nội dung lỗi trong file.

Nếu file có nội dung nhưng JSON parser báo lỗi, kiểm tra response gốc từ URL và log của plugin. Đừng chỉ đổi tên file hoặc chỉnh tay output trước khi tìm nguyên nhân.

## 21. Plugin fetch không thay thế validation hợp đồng

Plugin có nhiệm vụ lấy response HTTP và ghi file. Việc tạo file thành công không chứng minh đặc tả hợp lệ về mặt OpenAPI, cũng không chứng minh hợp đồng tương thích với phiên bản trước.

Pipeline nên có các bước riêng:

~~~text
Start application
      |
      v
Fetch OpenAPI over HTTP
      |
      v
Check file exists and is not empty
      |
      v
Parse JSON/YAML
      |
      v
Validate OpenAPI document
      |
      v
Compare contract with baseline
      |
      v
Publish build artifact
~~~

Có thể dùng OpenAPI Generator CLI để kiểm tra cấu trúc:

~~~bash
openapi-generator-cli validate -i target/openapi/openapi.json
~~~

Hãy chọn phiên bản validator có hỗ trợ OpenAPI version và các Schema Object mà dự án sử dụng. Một validator cũ có thể báo lỗi hoặc bỏ qua keyword mới dù document được tạo hợp lệ theo đặc tả mới.

Nếu cần kiểm tra breaking change, thêm công cụ so sánh OpenAPI với bản baseline. Việc fetch thành công và việc contract tương thích là hai tiêu chí khác nhau.

## 22. Tích hợp vào CI pipeline

Một job CI điển hình có thể thực hiện:

1. Checkout mã nguồn và cài JDK/Maven đúng version.
2. Resolve dependency và chạy unit test.
3. Khởi động các service phụ thuộc cần thiết.
4. Chạy Spring Boot ở profile contract.
5. Chờ readiness endpoint.
6. Gọi Springdoc Maven Plugin để xuất JSON/YAML.
7. Kiểm tra file tồn tại và parse được.
8. Validate OpenAPI và kiểm tra breaking change.
9. Upload file như build artifact.
10. Dừng ứng dụng và dọn các service test.

Ví dụ một đoạn script CI:

~~~bash
mvn clean verify
test -s target/openapi/openapi.json
openapi-generator-cli validate -i target/openapi/openapi.json
~~~

Lệnh cụ thể phụ thuộc cách plugin đã được gắn vào Maven lifecycle và vị trí output đã cấu hình. Nếu plugin ghi file vào target/openapi, pipeline phải dùng đúng path đó.

Không publish file nếu bước fetch hoặc validation thất bại. Artifact cần được gắn với commit/build cụ thể để nhóm có thể truy vết phiên bản hợp đồng.

## 23. So sánh đặc tả với bản baseline

Để kiểm soát thay đổi API, CI có thể so sánh file vừa xuất với bản OpenAPI của release trước.

Các thay đổi cần quan tâm:

- Xóa path hoặc HTTP method.
- Xóa request parameter bắt buộc hoặc thay đổi kiểu dữ liệu.
- Thêm một request field bắt buộc.
- Thu hẹp enum hoặc miền giá trị.
- Thay đổi response schema theo hướng client cũ không đọc được.
- Thay đổi security requirement hoặc scope.
- Thay đổi status code hoặc media type.

Không phải mọi thay đổi đều là breaking change. Thêm một response field tùy chọn thường ít rủi ro hơn xóa field hoặc đổi kiểu. Công cụ diff cần được cấu hình theo chính sách tương thích của tổ chức.

Baseline nên là artifact đã được review hoặc phát hành. Không tự động lấy file mới nhất từ một nhánh không ổn định làm baseline vì điều đó có thể che mất thay đổi phá vỡ hợp đồng.

## 24. Các lỗi thường gặp khi export

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Connection refused | Ứng dụng chưa start hoặc sai port | Kiểm tra tiến trình, log và apiDocsUrl |
| Timeout | Ứng dụng chưa ready hoặc phụ thuộc bị treo | Thêm readiness check và timeout hữu hạn |
| HTTP 404 | Sai endpoint hoặc context path | Kiểm tra springdoc.api-docs.path và URL |
| HTTP 401/403 | Security yêu cầu credential hoặc authority | Cấp quyền phù hợp cho CI |
| HTTP 302 | Request bị chuyển tới trang login | Kiểm tra security matcher và authentication |
| File rỗng | Response rỗng hoặc fetch thất bại | Kiểm tra status, body và log plugin |
| File chứa HTML | Gateway hoặc login page trả HTML | Kiểm tra Content-Type, Location và xác thực |
| Thiếu controller trong tài liệu | Sai profile, component scan hoặc group filter | Kiểm tra cấu hình runtime |
| Thiếu schema hoặc field | DTO, Jackson hoặc validation metadata khác dự kiến | Kiểm tra OpenAPI JSON thực tế |
| Export chạy trước khi app start | Gắn goal sai Maven phase | Start ở pre-integration-test, generate ở integration-test |
| Chạy mvn package nhưng không có file | Lifecycle chưa đi tới integration-test | Chạy mvn verify |
| CI container không gọi được localhost | Ứng dụng nằm ở container khác | Dùng hostname service trong CI network |
| File bị ghi đè giữa các group | Nhiều execution dùng chung outputFileName | Đặt tên file riêng cho từng group |
| Build lỗi để lại tiến trình | Lifecycle không chạy tới post-integration-test | Thêm cleanup ở cấp CI job |
| JSON hợp lệ nhưng hợp đồng sai | Chưa có validation hoặc contract diff | Thêm OpenAPI validation và baseline comparison |

Khi chẩn đoán, luôn tách ba câu hỏi: ứng dụng có chạy không, URL có trả đúng OpenAPI document không, và file sau khi lưu có hợp lệ không. Cách tách này giúp xác định lỗi nằm ở Spring Boot, HTTP/network/security hay ở bước kiểm tra artifact.

## 25. Quy trình triển khai từ local tới CI

Thực hiện theo trình tự:

1. Thêm springdoc runtime starter đúng với Spring MVC hoặc WebFlux.
2. Khởi động ứng dụng và xác nhận /v3/api-docs trả OpenAPI JSON.
3. Xác định profile và cấu hình sẽ dùng khi export.
4. Thêm Springdoc Maven Plugin với apiDocsUrl, outputFileName và outputDir.
5. Thêm Spring Boot Maven Plugin start/stop ở đúng lifecycle phase.
6. Đặt goal generate ở integration-test.
7. Cấu hình cổng, context path, readiness và các service phụ thuộc.
8. Chạy mvn clean verify trên máy local.
9. Xác nhận file output không rỗng, parse được và chứa đúng endpoint.
10. Thêm OpenAPI validator và contract diff.
11. Cấu hình CI secrets, network và artifact retention.
12. Chạy pipeline trên runner sạch để xác minh không phụ thuộc server đang chạy trên máy phát triển.

Khi pipeline đã ổn định, ghi lại version của JDK, Maven, Spring Boot, springdoc runtime và Springdoc Maven Plugin. Những version này giúp tái tạo kết quả export và chẩn đoán khác biệt giữa các lần build.

## 26. Ghi nhớ

- Springdoc runtime sinh OpenAPI từ ứng dụng đang chạy; Maven plugin chỉ lấy tài liệu qua HTTP.
- Plugin không quét source code và không tự khởi động Spring Boot.
- apiDocsUrl phải trỏ tới endpoint đang hoạt động và trả đúng OpenAPI document.
- Spring Boot Maven Plugin có thể quản lý start và stop trong Maven lifecycle.
- Start ứng dụng ở pre-integration-test, fetch ở integration-test, stop ở post-integration-test.
- Dùng mvn verify để đi qua các phase tích hợp; mvn package không chạy tới integration-test.
- Profile, port, context path, readiness, database và service phụ thuộc ảnh hưởng kết quả export.
- Có thể xuất JSON hoặc YAML bằng cách chọn endpoint và tên file tương ứng.
- Mỗi document group cần URL và output file riêng.
- Bảo vệ endpoint tài liệu bằng policy phù hợp và cung cấp credential CI an toàn nếu cần.
- HTTP fetch thành công không đồng nghĩa OpenAPI hợp lệ hoặc không có breaking change.
- Thêm bước parse, validate, diff và publish artifact vào CI.

Nguyên lý cốt lõi của plugin Springdoc là lấy đặc tả từ một ứng dụng Spring Boot đang phục vụ HTTP request. Hãy bảo đảm ứng dụng khởi động đúng profile và đã sẵn sàng, cấu hình plugin gọi đúng endpoint, rồi xác minh file output trước khi dùng nó làm artifact hoặc đầu vào cho các bước kiểm thử hợp đồng trong CI.
