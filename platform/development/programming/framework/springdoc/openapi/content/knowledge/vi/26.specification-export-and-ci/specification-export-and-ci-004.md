# Tích hợp Maven plugin vào giai đoạn phù hợp của vòng đời build

springdoc-openapi-maven-plugin lấy OpenAPI document từ một ứng dụng Spring Boot đang chạy và ghi nội dung đó thành file trong quá trình build Maven. Vì plugin gọi HTTP endpoint như /v3/api-docs, ứng dụng phải được khởi động trước khi goal generate chạy và cần được dừng sau khi thu thập tài liệu. Đây là lý do plugin phù hợp với giai đoạn integration-test của Maven: Spring Boot Maven Plugin có thể khởi động ứng dụng ở pre-integration-test, springdoc tải tài liệu ở integration-test, rồi Spring Boot Maven Plugin dừng ứng dụng ở post-integration-test.

Chọn đúng phase giúp build tạo được đặc tả phản ánh cấu hình runtime, đồng thời tránh gọi endpoint khi server chưa sẵn sàng hoặc để process ứng dụng chạy sót sau build. Lệnh thường dùng là mvn verify, vì lệnh này đi qua cả các phase chuẩn bị, chạy integration test, dừng ứng dụng và xác minh kết quả.

## 1. Maven plugin làm gì?

Springdoc-openapi runtime tạo tài liệu OpenAPI từ controller, DTO, annotation và cấu hình Spring. Maven plugin không quét source code hay tự phân tích controller. Nó gửi HTTP request tới endpoint tài liệu của ứng dụng đang chạy, nhận JSON hoặc YAML rồi ghi nguyên nội dung nhận được ra file.

Luồng xử lý:

~~~mermaid
flowchart TD
    A[mvn verify] --> B[package: đóng gói ứng dụng]
    B --> C[pre-integration-test: spring-boot:start]
    C --> D[Ứng dụng khởi động và sẵn sàng]
    D --> E[integration-test: springdoc:generate]
    E --> F[GET /v3/api-docs]
    F --> G[ghi target/openapi.json]
    G --> H[post-integration-test: spring-boot:stop]
    H --> I[verify: kiểm tra kết quả build]
~~~

Hai plugin có trách nhiệm riêng:

| Plugin | Goal | Trách nhiệm |
|---|---|---|
| spring-boot-maven-plugin | start | Khởi động ứng dụng ở process riêng, không chặn Maven |
| springdoc-openapi-maven-plugin | generate | Gọi endpoint OpenAPI của ứng dụng và ghi response thành file |
| spring-boot-maven-plugin | stop | Dừng process do goal start khởi động |
| maven-failsafe-plugin (nếu dùng) | integration-test, verify | Chạy và xác minh integration tests với ứng dụng đang hoạt động |

Vì plugin springdoc chỉ gọi HTTP endpoint, nó có thể làm việc với bất kỳ ứng dụng nào cung cấp OpenAPI description tại URL cấu hình. Tuy nhiên, ví dụ tích hợp chuẩn của dự án dùng Spring Boot Maven Plugin để quản lý vòng đời process.

## 2. Vì sao goal generate phù hợp với integration-test?

Maven default lifecycle có các phase theo thứ tự. Một số phase quan trọng:

| Phase | Vai trò | Ứng dụng đã chạy chưa? |
|---|---|---|
| validate | Kiểm tra cấu trúc và thông tin project | Chưa |
| compile | Biên dịch source code | Chưa |
| test | Chạy unit test | Thông thường chưa cần server đóng gói chạy riêng |
| package | Tạo JAR/WAR | Không mặc định |
| pre-integration-test | Chuẩn bị môi trường cho integration test | Goal start có thể khởi động server tại đây |
| integration-test | Chạy các kiểm thử tích hợp và thao tác cần ứng dụng hoạt động | Có |
| post-integration-test | Thu dọn môi trường sau integration test | Goal stop có thể dừng server tại đây |
| verify | Kiểm tra kết quả build và integration test | Server đã được dừng nếu lifecycle hoàn tất bình thường |
| install | Cài artifact vào local repository | Không cần server |
| deploy | Đưa artifact lên repository từ xa | Không cần server |

Goal springdoc-openapi:generate có default phase là integration-test. Tại thời điểm này, ứng dụng có thể đã được khởi động bởi goal spring-boot:start trong pre-integration-test. Nếu gắn goal generate vào compile, package hoặc generate-resources, server thường chưa chạy nên plugin không thể lấy tài liệu.

Không nên chọn verify chỉ vì muốn build thất bại nếu tài liệu sai. Hãy để việc tải OpenAPI diễn ra ở integration-test, sau đó dùng verify làm phase cuối để Maven hoàn tất kiểm tra và xác minh các integration test.

## 3. Vai trò của pre-integration-test, integration-test và post-integration-test

Ba phase này tạo thành một vùng làm việc có mở đầu, thực thi và thu dọn:

1. **pre-integration-test:** chuẩn bị hạ tầng và khởi động ứng dụng.
2. **integration-test:** tải OpenAPI document, chạy kiểm thử HTTP hoặc contract test.
3. **post-integration-test:** dừng ứng dụng và giải phóng tài nguyên.

Spring Boot Maven Plugin cung cấp goal start và stop để thực hiện hai đầu của chu trình. Goal start chạy ứng dụng trong process riêng và trả quyền điều khiển cho Maven để các plugin khác tiếp tục. Goal stop dùng JMX để yêu cầu process đó dừng.

Springdoc Maven Plugin chạy ở phase giữa để gọi endpoint. Nếu không có ứng dụng đang chạy tại URL đó, quá trình tải sẽ thất bại hoặc build có thể vẫn tiếp tục nếu failOnError để mặc định là false.

## 4. Cấu hình hai plugin trong pom.xml

Ví dụ dưới đây dùng Spring Boot Maven Plugin để quản lý ứng dụng và springdoc-openapi-maven-plugin để xuất JSON. Version của Spring Boot Maven Plugin nên được quản lý bởi Spring Boot parent hoặc dependency management. Version của springdoc Maven plugin là version của plugin build, độc lập với version thư viện springdoc runtime trong ứng dụng.

~~~xml
<properties>
    <springdoc-openapi-maven-plugin.version>1.6</springdoc-openapi-maven-plugin.version>
</properties>

<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
            <configuration>
                <jvmArguments>-Dspring.application.admin.enabled=true</jvmArguments>
            </configuration>
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
        </plugin>

        <plugin>
            <groupId>org.springdoc</groupId>
            <artifactId>springdoc-openapi-maven-plugin</artifactId>
            <version>${springdoc-openapi-maven-plugin.version}</version>
            <executions>
                <execution>
                    <id>generate-openapi-description</id>
                    <phase>integration-test</phase>
                    <goals>
                        <goal>generate</goal>
                    </goals>
                </execution>
            </executions>
            <configuration>
                <apiDocsUrl>http://localhost:8080/v3/api-docs</apiDocsUrl>
                <outputDir>${project.build.directory}/openapi</outputDir>
                <outputFileName>openapi.json</outputFileName>
                <timeout>90</timeout>
                <failOnError>true</failOnError>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

Trong ví dụ:

- spring.application.admin.enabled=true bật Spring Application Admin MBean để Spring Boot Maven Plugin có thể quản lý lifecycle của ứng dụng qua JMX.
- start chạy ở pre-integration-test.
- generate chạy ở integration-test.
- stop chạy ở post-integration-test.
- File được ghi tại target/openapi/openapi.json.
- failOnError=true làm build thất bại nếu không tải hoặc ghi được tài liệu.
- timeout=90 tăng thời gian chờ kết nối/đọc lên 90 giây so với mặc định 60 giây của springdoc plugin.

Version 1.6 trong ví dụ là version plugin build theo ví dụ README của dự án. Khi áp dụng, hãy kiểm tra release đang được tổ chức phê duyệt và ghim một version cụ thể; không dùng version động hoặc bỏ trống version plugin.

### Vì sao phải bật Spring Application Admin?

Spring Boot Maven Plugin khởi động ứng dụng trong process riêng. Nó dùng JMX để trao đổi với MBean quản lý vòng đời ứng dụng. spring.application.admin.enabled=true cho phép Spring Boot đăng ký MBean cần thiết. Nếu thiếu cấu hình này, goal start có thể khởi động ứng dụng nhưng goal stop không điều khiển được nó như mong đợi.

Spring Boot Maven Plugin mặc định dùng JMX port 9001. Nếu nhiều ứng dụng cùng chạy trên một agent hoặc port này đã được sử dụng, cấu hình một port khác và dùng chung cấu hình đó cho start/stop.

## 5. Chạy build bằng mvn verify

Sau khi cấu hình plugin, chạy:

~~~bash
mvn clean verify
~~~

Maven thực hiện các phase trước verify theo đúng thứ tự. Với cấu hình ở trên, kết quả mong đợi:

~~~text
target/
└── openapi/
    └── openapi.json
~~~

verify phù hợp cho CI vì nó chạy qua post-integration-test và phase verify, nơi Failsafe có thể xác minh kết quả integration test. Chỉ gọi mvn integration-test có thể làm lifecycle dừng trước khi phần thu dọn chạy trong một số phiên bản Maven, khiến ứng dụng vẫn còn process. Hãy dùng phase cuối như verify thay vì gọi một phase trung gian khi build có môi trường cần start/stop.

Không nhầm lệnh mvn springdoc-openapi:generate với mvn verify. Gọi trực tiếp goal plugin chỉ chạy thao tác tải file; nó không tự khởi động ứng dụng trừ khi bạn tự chuẩn bị server trước đó.

## 6. Thứ tự thực thi khi nhiều goal cùng tham gia lifecycle

Maven chạy các phase theo thứ tự lifecycle. Các goal được gắn vào cùng phase được thực thi theo thứ tự khai báo trong POM. Vì vậy:

- spring-boot:start phải hoàn tất trước khi springdoc-openapi:generate gọi HTTP endpoint.
- springdoc-openapi:generate cần hoàn tất trước khi spring-boot:stop dừng server.
- Nếu Failsafe chạy integration tests, chúng cũng cần ứng dụng đang hoạt động trong phase integration-test.

Trong cấu hình mẫu, các goal nằm ở ba phase khác nhau nên thứ tự được thể hiện rõ ràng mà không phụ thuộc thứ tự khai báo giữa hai plugin.

Nếu nhiều plugin cùng chạy ở integration-test, hãy sắp xếp declaration và execution để server đã sẵn sàng trước khi test hoặc export chạy. Không đặt goal stop vào cùng phase với generate nếu chưa kiểm soát thứ tự, vì ứng dụng có thể bị dừng trước khi tài liệu được tải.

## 7. Cấu hình endpoint và file đầu ra

Các tham số chính của goal generate:

| Tham số | User property | Mặc định | Ý nghĩa |
|---|---|---|---|
| apiDocsUrl | springdoc.apiDocsUrl | http://localhost:8080/v3/api-docs | URL trả OpenAPI JSON hoặc YAML |
| outputDir | springdoc.outputDir | ${project.build.directory} | Thư mục ghi file |
| outputFileName | springdoc.outputFileName | openapi.json | Tên file |
| attachArtifact | springdoc.attachArtifact | false | Gắn file vào Maven project để install/deploy cùng artifact |
| attachArtifactClassifier | springdoc.attachArtifactClassifier | openapi | Classifier khi attach |
| headers | Không có user property riêng | Không có | HTTP headers gửi khi gọi endpoint |
| timeout | springdoc.timeout | 60 giây | Timeout kết nối và đọc response |
| skip | springdoc.skip | false | Bỏ qua goal generate |
| failOnError | Không có user property riêng | false | Làm build thất bại nếu tải/ghi tài liệu lỗi |

outputDir mặc định là ${project.build.directory}, thường tương ứng thư mục target. Nên chọn một thư mục con như ${project.build.directory}/openapi để phân biệt file đặc tả với JAR, test report và các artifact khác.

Không đặt outputDir bằng một path bắt đầu với dấu gạch chéo như một path tuyệt đối tùy ý trong cấu hình plugin. Tài liệu plugin yêu cầu tên thư mục tương đối; có thể dùng ${project.build.directory}/openapi như ví dụ.

## 8. Xuất YAML thay vì JSON

Springdoc runtime cung cấp cả JSON và YAML. Để xuất YAML, đổi URL endpoint và tên file:

~~~xml
<configuration>
    <apiDocsUrl>http://localhost:8080/v3/api-docs.yaml</apiDocsUrl>
    <outputDir>${project.build.directory}/openapi</outputDir>
    <outputFileName>openapi.yaml</outputFileName>
    <failOnError>true</failOnError>
</configuration>
~~~

Plugin lưu response được trả về từ endpoint. Nó không chuyển JSON sang YAML hay ngược lại. Vì vậy, định dạng URL và phần mở rộng file phải tương ứng:

| Endpoint | Tên file gợi ý |
|---|---|
| /v3/api-docs | openapi.json |
| /v3/api-docs.yaml | openapi.yaml |

Nếu ứng dụng đổi springdoc.api-docs.path, hãy cập nhật apiDocsUrl theo path mới. Nếu dùng context path hoặc reverse proxy, cần dùng URL mà process Maven có thể truy cập từ môi trường build.

## 9. Lưu nhiều OpenAPI group trong cùng build

Nếu ứng dụng khai báo nhiều GroupedOpenApi, mỗi group có endpoint riêng, chẳng hạn:

~~~text
/v3/api-docs/public
/v3/api-docs/admin
/v3/api-docs/internal
~~~

Có thể khai báo một execution cho mỗi group. Mỗi execution cần URL và tên file riêng; nếu attach vào Maven artifact, dùng classifier riêng để tránh trùng:

~~~xml
<plugin>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-maven-plugin</artifactId>
    <version>${springdoc-openapi-maven-plugin.version}</version>
    <executions>
        <execution>
            <id>generate-public-api</id>
            <phase>integration-test</phase>
            <goals>
                <goal>generate</goal>
            </goals>
            <configuration>
                <apiDocsUrl>http://localhost:8080/v3/api-docs/public</apiDocsUrl>
                <outputFileName>openapi-public.json</outputFileName>
                <attachArtifact>true</attachArtifact>
                <attachArtifactClassifier>openapi-public</attachArtifactClassifier>
                <failOnError>true</failOnError>
            </configuration>
        </execution>
        <execution>
            <id>generate-admin-api</id>
            <phase>integration-test</phase>
            <goals>
                <goal>generate</goal>
            </goals>
            <configuration>
                <apiDocsUrl>http://localhost:8080/v3/api-docs/admin</apiDocsUrl>
                <outputFileName>openapi-admin.json</outputFileName>
                <attachArtifact>true</attachArtifact>
                <attachArtifactClassifier>openapi-admin</attachArtifactClassifier>
                <failOnError>true</failOnError>
            </configuration>
        </execution>
    </executions>
</plugin>
~~~

Đặt cấu hình chung như version và outputDir ở cấp plugin nếu các execution dùng chung; đặt apiDocsUrl, file name và classifier ở cấp execution khi chúng khác nhau. Kiểm tra plugin version đang dùng hỗ trợ cấu hình theo execution đúng như ví dụ.

Một điểm quan trọng: nếu các endpoint group yêu cầu security khác nhau, process build phải gửi header phù hợp cho từng execution. Không dùng một token admin để export tài liệu public nếu token đó không cần thiết.

## 10. Gắn OpenAPI file vào Maven artifact

Mặc định attachArtifact=false, file chỉ nằm trong output directory của build. Khi bật:

~~~xml
<attachArtifact>true</attachArtifact>
<attachArtifactClassifier>openapi</attachArtifactClassifier>
~~~

Maven gắn file đặc tả vào project như một artifact phụ có classifier openapi. Khi chạy mvn install, artifact có thể được cài vào local repository cùng JAR chính; khi chạy mvn deploy, nó có thể được publish lên repository từ xa cùng các artifact khác.

Ví dụ tọa độ artifact phụ:

~~~text
com.example:catalog-service:1.0.0:openapi:json
~~~

Classifier giúp consumer phân biệt JAR thực thi với file OpenAPI. Với nhiều group, dùng classifier khác nhau như openapi-public và openapi-admin. Tránh để hai execution cùng attach một classifier cho cùng project vì sẽ tạo xung đột hoặc ghi đè artifact.

Không bật attach nếu pipeline chỉ cần upload file như CI artifact hoặc đưa sang bước lint/contract test. Có thể giữ file trong target/openapi rồi dùng cơ chế artifact upload của hệ thống CI.

## 11. Gửi header khi endpoint OpenAPI được bảo vệ

Nếu Spring Security bảo vệ /v3/api-docs, plugin cần gửi authentication header. Cấu hình headers:

~~~xml
<configuration>
    <apiDocsUrl>http://localhost:8080/v3/api-docs</apiDocsUrl>
    <headers>
        <Authorization>Bearer ${env.OPENAPI_EXPORT_TOKEN}</Authorization>
    </headers>
    <failOnError>true</failOnError>
</configuration>
~~~

Đặt token trong biến môi trường của CI, không commit token vào POM. Ví dụ trên minh họa cách truyền header; tên phần tử trong headers trở thành tên HTTP header được gửi. Với endpoint không yêu cầu xác thực, không cần thêm header.

Nếu mỗi OpenAPI group có quyền truy cập khác nhau, cấu hình header phù hợp trong execution tương ứng. Cẩn thận với log Maven: không bật debug hoặc in toàn bộ environment khi có secret.

## 12. Đổi port và truyền argument cho ứng dụng

Nếu cổng 8080 bị chiếm hoặc CI chạy nhiều service, đổi port của ứng dụng và URL plugin cùng lúc:

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <configuration>
        <jvmArguments>-Dspring.application.admin.enabled=true</jvmArguments>
        <arguments>
            <argument>--server.port=9090</argument>
        </arguments>
    </configuration>
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
</plugin>
~~~

Và:

~~~xml
<apiDocsUrl>http://localhost:9090/v3/api-docs</apiDocsUrl>
~~~

arguments truyền tham số ứng dụng vào process được start. Nếu đổi port bằng command line nhưng quên đổi apiDocsUrl, plugin vẫn gọi cổng 8080 và có thể lấy nhầm một ứng dụng khác đang chạy trên máy.

Có thể truyền profile, cấu hình datasource hoặc property môi trường qua arguments, environmentVariables hoặc profiles của Spring Boot Maven Plugin. Hãy dùng đúng profile dành cho việc dựng OpenAPI trong CI; profile có thể ảnh hưởng endpoint, security, feature flag và schema được sinh ra.

## 13. Điều chỉnh thời gian chờ khi ứng dụng khởi động

Spring Boot Maven Plugin start kiểm tra ứng dụng đã sẵn sàng bằng các lần thử cách nhau một khoảng thời gian. Tài liệu hiện hành có các tham số maxAttempts và wait; mặc định 60 lần, mỗi lần 500 ms, tương ứng khoảng 30 giây.

Nếu ứng dụng khởi động chậm do migration database, cache warm-up hoặc tải cấu hình, có thể tăng thời gian chờ:

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <configuration>
        <jvmArguments>-Dspring.application.admin.enabled=true</jvmArguments>
        <maxAttempts>120</maxAttempts>
        <wait>500</wait>
    </configuration>
    <!-- executions start/stop -->
</plugin>
~~~

Không dùng timeout dài để che lỗi startup. Hãy đọc log của process ứng dụng để xác định nguyên nhân như datasource không kết nối, port đã được dùng, profile sai hoặc bean khởi tạo thất bại.

springdoc-openapi-maven-plugin có timeout riêng cho request tới endpoint, mặc định 60 giây. Thời gian startup và thời gian tải OpenAPI là hai giới hạn khác nhau:

- maxAttempts và wait điều khiển việc chờ ứng dụng sẵn sàng.
- timeout của springdoc plugin điều khiển kết nối/đọc response từ apiDocsUrl.

Nếu document lớn, nhiều schema hoặc customizer chạy lâu, có thể tăng timeout mà không cần thay đổi thời gian startup.

## 14. Định dạng đẹp và nội dung file được lưu

Plugin lưu đúng nội dung mà endpoint OpenAPI trả về. Nó không tự format lại JSON, sắp xếp key hoặc chuẩn hóa YAML. Nếu muốn JSON có indentation để dễ review trong Git, cấu hình springdoc runtime:

~~~yaml
springdoc:
  writer-with-default-pretty-printer: true
~~~

Hoặc truyền property khi Spring Boot Maven Plugin khởi động ứng dụng:

~~~xml
<arguments>
    <argument>--springdoc.writer-with-default-pretty-printer=true</argument>
</arguments>
~~~

Không nên chạy một formatter tùy tiện sau khi export nếu pipeline cần so sánh chính xác document mà runtime phục vụ. Nếu có bước chuẩn hóa, hãy coi đó là một bước riêng, được version hóa và kiểm thử trong CI.

## 15. Kết hợp với Maven Failsafe

Spring Boot Maven Plugin start/stop được thiết kế để dùng cùng integration tests. Maven Failsafe có hai goal chính:

- integration-test: chạy test tích hợp khi ứng dụng đang hoạt động.
- verify: tổng hợp kết quả test và làm build thất bại nếu có test lỗi.

Ví dụ cấu hình:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-failsafe-plugin</artifactId>
    <executions>
        <execution>
            <id>run-integration-tests</id>
            <goals>
                <goal>integration-test</goal>
                <goal>verify</goal>
            </goals>
        </execution>
    </executions>
</plugin>
~~~

Failsafe được thiết kế để trì hoãn việc báo build failure đến phase verify. Nhờ vậy, Maven có thể đi qua post-integration-test và chạy goal stop trước khi kết quả test được xác minh. Đây là lợi thế so với việc đặt integration tests vào Surefire ở phase test khi cần một server được quản lý riêng quanh test.

Nếu vừa export OpenAPI vừa chạy integration test, cả hai đều sử dụng ứng dụng đã được start ở pre-integration-test. Hãy quyết định thứ tự goal trong phase integration-test theo nhu cầu. Ví dụ, có thể tải OpenAPI trước để lưu lại contract của ứng dụng, sau đó chạy các test tích hợp.

## 16. Xử lý skip theo môi trường

Plugin springdoc hỗ trợ user property springdoc.skip. Có thể bỏ qua riêng việc export:

~~~bash
mvn verify -Dspringdoc.skip=true
~~~

Lưu ý: lệnh trên chỉ bỏ qua goal generate. Nếu Spring Boot Maven Plugin vẫn được cấu hình start/stop, ứng dụng vẫn được khởi động và dừng theo lifecycle.

Nếu muốn bỏ qua toàn bộ integration environment trong một số lần build, dùng một property chung cho start, stop, Failsafe và springdoc:

~~~xml
<properties>
    <skip.it>false</skip.it>
</properties>

<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <executions>
        <execution>
            <id>start-application-for-tests</id>
            <phase>pre-integration-test</phase>
            <goals>
                <goal>start</goal>
            </goals>
            <configuration>
                <skip>${skip.it}</skip>
            </configuration>
        </execution>
        <execution>
            <id>stop-application-after-tests</id>
            <phase>post-integration-test</phase>
            <goals>
                <goal>stop</goal>
            </goals>
            <configuration>
                <skip>${skip.it}</skip>
            </configuration>
        </execution>
    </executions>
</plugin>
~~~

Áp dụng cùng property vào springdoc plugin và Failsafe:

~~~xml
<configuration>
    <skip>${skip.it}</skip>
</configuration>
~~~

Chạy:

~~~bash
mvn verify -Dskip.it=true
~~~

Không dùng skip riêng của springdoc để biểu thị rằng toàn bộ integration test đã bị tắt. Hãy đảm bảo start, stop và test cùng tuân theo một cờ nếu mục tiêu là bỏ qua cả môi trường.

## 17. Xử lý khi build thất bại và process ứng dụng còn chạy

Goal stop được gắn vào post-integration-test. Nếu build thất bại trước khi Maven đi tới phase này, Maven có thể bỏ qua goal stop. README của springdoc plugin cũng cảnh báo rằng khi build thất bại, ứng dụng do spring-boot:start khởi động có thể tiếp tục chạy và trả lời request cho lần build kế tiếp.

Điều này đặc biệt quan trọng khi:

- Ứng dụng không khởi động hoàn chỉnh.
- springdoc không tải được OpenAPI và failOnError=true làm build dừng.
- Integration test làm build thất bại ngay trong phase integration-test.
- CI agent tái sử dụng cùng máy hoặc cùng port cho nhiều job.

Các biện pháp nên áp dụng:

1. Chạy build trong container hoặc runner dùng một lần nếu có thể.
2. Dùng port riêng cho từng job hoặc từng module.
3. Thêm bước cleanup của CI chạy với điều kiện luôn thực hiện, kể cả khi Maven thất bại.
4. Không giả định post-integration-test luôn chạy sau một lỗi build.
5. Nếu dùng process ngoài Maven hoặc service phụ, quản lý lifecycle của chúng bằng cơ chế cleanup riêng.

Đặt failOnError=true là cần thiết để CI không âm thầm bỏ qua file OpenAPI, nhưng nó cũng làm build dừng ngay khi export lỗi. Vì vậy, bước cleanup ngoài Maven càng cần được thiết kế rõ.

## 18. Goal report và Maven Site khác với goal generate

Plugin có thêm goal report, dùng để đưa trang tài liệu Swagger UI vào phần Project Reports của Maven Site. Goal này có default phase là site, không phải integration-test.

Khác biệt:

| Goal | Phase mặc định | Kết quả |
|---|---|---|
| generate | integration-test | Ghi OpenAPI JSON/YAML thành file |
| report | site | Tạo trang tài liệu hiển thị bằng Swagger UI trong Maven Site |

Để tạo site report, khai báo plugin trong reporting:

~~~xml
<reporting>
    <plugins>
        <plugin>
            <groupId>org.springdoc</groupId>
            <artifactId>springdoc-openapi-maven-plugin</artifactId>
            <version>${springdoc-openapi-maven-plugin.version}</version>
            <reportSets>
                <reportSet>
                    <reports>
                        <report>report</report>
                    </reports>
                </reportSet>
            </reportSets>
        </plugin>
    </plugins>
</reporting>
~~~

Sau khi generate document, có thể chạy:

~~~bash
mvn verify site
~~~

Report mặc định đọc file do goal generate tạo ra, thường là target/openapi.json. Nếu file không tồn tại, report có thể tải document từ apiDocsUrl. Trang được tạo trong Maven Site dưới thư mục springdoc-openapi.

Các giới hạn cần biết:

- Goal report yêu cầu maven-site-plugin phiên bản 3.9.1 trở lên.
- Report hiện chỉ hỗ trợ JSON document, không hỗ trợ YAML.
- Swagger UI assets được tải từ unpkg.com khi trang site được xem, nên trình duyệt cần kết nối Internet.
- Report là trang trình bày tài liệu; nó không thay thế file OpenAPI artifact dùng cho lint, diff hoặc code generation.

Nếu mục tiêu là phát hành file JSON/YAML trong artifact, dùng goal generate. Nếu mục tiêu là tạo trang Project Reports, dùng report; hai mục tiêu có thể cùng xuất hiện trong một build.

## 19. Tích hợp vào CI và kiểm tra file sau export

Trong CI, một bước export chỉ có giá trị khi build xác nhận file tồn tại và có nội dung hợp lệ. Cấu hình failOnError=true để build thất bại nếu plugin không tải hoặc ghi được document.

Một pipeline có thể chia thành các bước:

1. Chạy mvn clean verify để compile, test, package, start ứng dụng, export OpenAPI, chạy integration test và stop ứng dụng.
2. Kiểm tra target/openapi/openapi.json hoặc YAML tương ứng tồn tại và không rỗng.
3. Parse JSON/YAML để phát hiện file bị cắt cụt hoặc sai cú pháp.
4. Chạy OpenAPI lint hoặc validator theo quy tắc của tổ chức.
5. So sánh với contract của release trước để phát hiện breaking change.
6. Lưu file như CI artifact hoặc attach vào Maven artifact.
7. Chỉ publish tài liệu sau khi các bước kiểm tra đạt.

Plugin chỉ chứng minh rằng nó đã lấy được response từ endpoint. Nó không tự xác minh rằng schema đúng với nghiệp vụ, operationId ổn định, mọi response status đã được mô tả hay thay đổi có tương thích ngược. Những kiểm tra đó cần bước lint, diff và contract test riêng.

Ví dụ kiểm tra nhanh bằng shell sau build:

~~~bash
test -s target/openapi/openapi.json
python -m json.tool target/openapi/openapi.json > /dev/null
~~~

Đây chỉ là ví dụ kiểm tra file JSON không rỗng và parse được. Nếu xuất YAML, dùng YAML parser được tổ chức phê duyệt. Trong phạm vi bài này, Maven plugin chỉ tạo artifact; việc chọn công cụ lint/diff phụ thuộc chính sách CI.

## 20. Lưu ý với multi-module Maven và build song song

Trong dự án multi-module, đặt cấu hình start/generate/stop ở module thực sự chứa Spring Boot application và springdoc runtime. Không đặt execution khởi động ứng dụng vào aggregator POM chỉ chứa packaging pom nếu module đó không có application có thể chạy.

Nếu nhiều module service cùng export OpenAPI:

- Mỗi module cần URL, port và output directory phù hợp.
- Không để các process cùng bind vào một HTTP port.
- Nếu Spring Boot Maven Plugin dùng JMX, mỗi process cần JMX port riêng khi chạy đồng thời.
- Dùng classifier riêng khi các file được attach vào Maven artifacts.
- Cẩn thận với Maven parallel build; các service có thể khởi động đồng thời và xung đột tài nguyên.

Với một module duy nhất, cấu hình mặc định localhost:8080 và JMX 9001 thường đủ cho build tuần tự. Với reactor nhiều service, hãy cấp port rõ ràng hoặc tách export thành job riêng.

## 21. Tương thích phiên bản và quản lý dependency

Springdoc Maven Plugin là một build plugin riêng. Version của nó không cần bằng version springdoc runtime. Hãy pin version plugin và đồng thời dùng springdoc runtime tương thích với Spring Boot:

| Spring Boot | Dòng springdoc runtime |
|---|---|
| 4.x | 3.x |
| 3.x | 2.x |
| 2.x và 1.x | 1.x |

Springdoc Maven Plugin chỉ gọi HTTP endpoint, vì vậy nhiệm vụ của nó là lấy document từ ứng dụng. Bảng trên áp dụng cho quan hệ tương thích giữa Spring Boot và thư viện springdoc runtime, không phải quy tắc bắt buộc version plugin build phải trùng version runtime.

README plugin hiện nêu yêu cầu Maven 3.6.3 trở lên và Java 8 trở lên cho chính plugin. Dự án Spring Boot có thể yêu cầu Java cao hơn tùy major version. Luôn kiểm tra compatibility matrix của Spring Boot/springdoc và toolchain CI thực tế.

Nếu dùng spring-boot-starter-parent, version Spring Boot Maven Plugin thường được quản lý bởi parent. Nếu không dùng parent, cần khai báo version plugin Spring Boot rõ ràng hoặc dùng pluginManagement phù hợp. Không để version plugin tự thay đổi theo môi trường.

## 22. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Connection refused tới /v3/api-docs | Ứng dụng chưa chạy hoặc apiDocsUrl sai port | Đặt start ở pre-integration-test và kiểm tra port/path |
| File OpenAPI không được tạo nhưng build vẫn xanh | failOnError đang là false | Đặt failOnError=true trong CI |
| 401 hoặc 403 khi tải document | Endpoint được bảo vệ bằng Spring Security | Cấu hình headers cho plugin bằng token lấy từ CI secret |
| File lấy từ service cũ | Port đã có process cũ đang lắng nghe | Dùng port riêng, kiểm tra process và cleanup job trước |
| 404 khi gọi group | Group name hoặc endpoint URL không đúng | Kiểm tra URL /v3/api-docs/{group} |
| Ứng dụng không dừng sau build | Thiếu Spring Application Admin hoặc JMX port không khớp | Bật spring.application.admin.enabled và dùng cùng JMX config cho start/stop |
| Ứng dụng còn chạy sau khi build lỗi | Maven không đi tới post-integration-test | Thêm cleanup luôn chạy ở CI hoặc dùng runner/container dùng một lần |
| Goal generate chạy trước khi server sẵn sàng | Goal bị gắn sai phase hoặc startup chậm | Gắn generate vào integration-test, tăng maxAttempts/wait nếu có căn cứ |
| Plugin timeout dù server đã chạy | Document tạo lâu hoặc endpoint phản hồi chậm | Tăng timeout của springdoc plugin và kiểm tra log server |
| Export nhầm profile | Process Spring Boot khởi động với profile khác | Truyền profiles/arguments đúng cho goal start |
| Xuất YAML nhưng file có đuôi JSON | apiDocsUrl và outputFileName không tương ứng | Dùng /v3/api-docs.yaml và openapi.yaml |
| Hai file group ghi đè nhau | Cùng outputFileName hoặc classifier | Đặt tên file và classifier duy nhất |
| Build song song bị lỗi port | Nhiều module cùng dùng HTTP/JMX port mặc định | Cấp port riêng hoặc chạy export tuần tự |
| mvn springdoc-openapi:generate không kết nối được | Gọi goal trực tiếp mà không start server | Dùng mvn verify hoặc tự khởi động endpoint trước |
| Maven Site report không hiển thị | Thiếu maven-site-plugin phù hợp hoặc đang dùng YAML | Dùng site plugin >= 3.9.1 và cung cấp JSON |

## 23. Quy trình chọn phase và cấu hình cho một dự án

Khi tích hợp Maven plugin, thực hiện theo trình tự:

1. Xác nhận ứng dụng có springdoc runtime và endpoint OpenAPI hoạt động.
2. Chọn đúng Spring Boot Maven Plugin để start/stop process.
3. Đặt start ở pre-integration-test.
4. Đặt springdoc generate ở integration-test.
5. Đặt stop ở post-integration-test.
6. Bật Spring Application Admin và cấu hình JMX phù hợp.
7. Đặt apiDocsUrl đúng port, context path và group.
8. Chọn outputDir, outputFileName và JSON/YAML phù hợp.
9. Đặt failOnError=true cho CI và cấu hình timeout có căn cứ.
10. Nếu endpoint cần authentication, truyền token qua CI secret.
11. Nếu cần publish cùng artifact, bật attachArtifact và dùng classifier riêng.
12. Chạy mvn clean verify, sau đó kiểm tra file, parse, lint và diff contract.
13. Bảo đảm CI có cleanup khi build dừng trước post-integration-test.

Giai đoạn integration-test là vị trí phù hợp cho goal generate vì tại đó ứng dụng đã được khởi động và vẫn còn hoạt động để springdoc plugin gọi endpoint. Kết hợp pre-integration-test, integration-test và post-integration-test giúp Maven tạo ra tài liệu từ đúng runtime, quản lý process rõ ràng và đưa file OpenAPI vào pipeline kiểm tra hoặc phát hành.

## 24. Tài liệu tham khảo

- [springdoc-openapi-maven-plugin README](https://github.com/springdoc/springdoc-openapi-maven-plugin): goal generate/report, default phase, cấu hình output, headers, attachArtifact, YAML, group và failOnError.
- [Springdoc OpenAPI v2 – Maven Plugin](https://springdoc.org/v2/#maven-plugin): cách tích hợp plugin vào Maven lifecycle.
- [Maven – Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle): thứ tự phase, binding goal và cách Maven thực thi lifecycle.
- [Maven – Lifecycles Reference](https://maven.apache.org/ref/current/maven-core/lifecycles.html): danh sách phase của default lifecycle.
- [Spring Boot Maven Plugin – Running Integration Tests](https://docs.spring.io/spring-boot/maven-plugin/integration-tests.html): goal start/stop, JMX, readiness, Failsafe và cleanup.
- [Spring Boot Maven Plugin – Goals](https://docs.spring.io/spring-boot/maven-plugin/goals.html): tham số và hành vi các goal của Spring Boot Maven Plugin.
- [Springdoc OpenAPI – Compatibility Matrix](https://springdoc.org/#what-is-the-compatibility-matrix-of-spring-boot-with-springdoc-openapi-): tương thích giữa Spring Boot và springdoc runtime.
