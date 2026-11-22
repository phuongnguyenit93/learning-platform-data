# Đối chiếu triệu chứng với conditions, cấu hình có hiệu lực và bộ phiên bản thư viện

## 1. Vì sao cần ba nguồn bằng chứng?

Một endpoint Actuator trả `404` có thể do chưa được tạo, chưa được công bố qua HTTP, đi nhầm cổng hoặc bị proxy đổi đường dẫn. Một registry không xuất dữ liệu có thể do điều kiện tự cấu hình không khớp, thuộc tính đang bị ghi đè hoặc thư viện thực tế khác với thư viện người viết mã nghĩ đang dùng.

Vì vậy, chẩn đoán không bắt đầu bằng việc thêm một thuộc tính bất kỳ. Hãy đối chiếu ba nguồn:

| Nguồn bằng chứng | Trả lời câu hỏi nào? | Không tự chứng minh điều gì? |
| --- | --- | --- |
| Báo cáo đánh giá điều kiện (conditions) | Vì sao một cấu hình tự động hoặc bean có/không được áp dụng trong application context? | Không chứng minh request tới được endpoint, qua được bảo mật hoặc nghiệp vụ hoạt động |
| Cấu hình có hiệu lực | Tiến trình đang đọc giá trị nào, từ nguồn nào, sau khi áp dụng ưu tiên và binding? | Không chứng minh mọi cấu hình được dùng để tạo bean, hoặc thư viện tương thích |
| Bộ phiên bản thư viện thực tế | Những lớp và phiên bản nào có mặt, được đóng gói và được nạp khi chạy? | Không chứng minh thuộc tính đúng hoặc endpoint đã expose |

**Conditions** ở đây là điều kiện của Spring Boot, như điều kiện có class, có bean, thiếu bean hoặc giá trị thuộc tính. Nó không phải trạng thái sức khỏe của dịch vụ.

**Cấu hình có hiệu lực** là kết quả mà ứng dụng đang dùng sau khi kết hợp các nguồn cấu hình. File `application.yml` trong source chỉ là một trong các đầu vào.

**Bộ phiên bản thư viện** là tập phiên bản phối hợp với nhau: Spring Boot, Spring Framework, Micrometer, registry, client và các dependency liên quan. Một thư viện có version mới hơn không tự làm cả tập trở nên tương thích hơn.

Các ví dụ dưới đây lấy Spring Boot 3.3.x làm mốc. Với phiên bản khác, cần kiểm tra hợp đồng cấu hình tương ứng; không trộn tên thuộc tính và cơ chế của nhiều thế hệ Spring Boot.

## 2. Đặt ba nguồn vào đúng vòng đời khởi động

Có thể hình dung các bước liên quan như sau:

```text
Các nguồn cấu hình và profile
             |
             v
Environment được chuẩn bị
             |
             v
Đánh giá điều kiện, đăng ký định nghĩa bean
             |
             v
Tạo bean, bind các bean cấu hình, thiết lập endpoint
             |
             v
Công bố HTTP/JMX, áp dụng bảo mật và hạ tầng mạng
             |
             v
Request thực tế và hoạt động lúc chạy
```

Sơ đồ này mô tả quan hệ chẩn đoán, không có nghĩa mọi loại điều kiện đều được đánh giá tại một thời điểm duy nhất. Một số điều kiện được xử lý khi phân tích cấu hình; một số phụ thuộc vào thông tin bean ở giai đoạn đăng ký.

Có bốn hệ quả quan trọng:

1. Một cấu hình tự động khớp điều kiện vẫn có thể gặp lỗi khi tạo bean.
2. Bean tồn tại vẫn có thể chưa có đường HTTP được expose.
3. Endpoint được expose vẫn có thể trả `401` hoặc `403` do bảo mật.
4. Endpoint đã hoạt động vẫn có thể báo `DOWN` vì tài nguyên bên ngoài thực sự lỗi.

Báo cáo conditions chủ yếu giải thích các quyết định cấu hình của application context. Nó không liên tục đánh giá lại toàn bộ điều kiện sau mỗi request. Thay đổi một nguồn cấu hình trong hệ thống triển khai cũng không tự làm tiến trình cũ nhận giá trị mới hoặc tự tạo lại mọi bean. Cơ chế cập nhật động, nếu có, phải được xác minh riêng.

## 3. Chuẩn hóa triệu chứng trước khi đọc báo cáo

Ghi một mô tả có thể kiểm chứng:

```text
Instance: service-a, lần khởi động đang điều tra
Thao tác: GET vào địa chỉ quản trị đã xác minh
Kỳ vọng: có phản hồi metric
Thực tế: HTTP 404
Thời điểm: sau lần triển khai gần nhất
Phạm vi: chỉ một replica bị lỗi
```

Đây là mẫu cách mô tả một tình huống, không phải dữ liệu thật của một hệ thống cụ thể. Khi áp dụng, ghi giá trị quan sát được của chính instance đang điều tra.

Bổ sung mã định danh bản triển khai, thời điểm khởi động, Java runtime, profile active, cổng ứng dụng và cổng quản trị. Với nhiều replica, lấy log, cấu hình và phản hồi HTTP từ **cùng một tiến trình**. Nếu request qua load balancer, có thể đang luân phiên đọc những instance khác nhau.

### Phân loại để chọn bằng chứng đầu tiên

| Triệu chứng | Bằng chứng ưu tiên | Vì sao? |
| --- | --- | --- |
| Ứng dụng không khởi động | Exception gốc, runtime classpath, cấu hình liên quan | HTTP Actuator có thể chưa tồn tại để truy vấn |
| HTTP 404 | URL/cổng/base path, conditions, enablement và exposure | Cần tách chưa tạo endpoint khỏi chưa công bố endpoint |
| HTTP 401/403 | Security chain, danh tính và quyền truy cập | Conditions không phải báo cáo phân quyền của request |
| HTTP 500 hoặc lỗi liên kết class | Stack trace, dependency và lớp được nạp | Có thể bean đã tồn tại nhưng gọi vào binary không tương thích |
| Health trả DOWN | Chi tiết contributor và tài nguyên nó kiểm tra | Điều kiện tạo contributor khớp không bảo đảm tài nguyên khỏe |
| Có registry nhưng không có meter cần tìm | Registry thực tế, filter, cấu hình và hoạt động tạo meter | Không phải mọi lỗi metric đều do auto-configuration |

Không diễn giải `404` như bằng chứng chắc chắn rằng bean không tồn tại. Một proxy hoặc lớp bảo mật cũng có thể thay đổi phản hồi. Cần đối chiếu với đường request thực tế.

## 4. Nguồn thứ nhất: đọc conditions đúng cách

### 4.1. Lấy báo cáo từ log khởi động

Với ứng dụng đóng gói executable JAR, thêm `--debug` khi chạy giúp Spring Boot in báo cáo đánh giá điều kiện:

```bash
java -jar build/libs/conditions-lab.jar --debug
```

Tên JAR này sẽ được dùng trong bài thực hành phía dưới. Với ứng dụng khác, dùng artifact thực tế của lần triển khai đang điều tra.

Nếu khởi động qua Gradle trong một dự án đã có Boot plugin:

```bash
./gradlew bootRun --args='--debug'
```

Trên Windows có thể dùng `gradlew.bat`; cách đặt dấu nháy phụ thuộc shell. Trong multi-project build, dùng task path của đúng ứng dụng.

`--debug` của Spring Boot bật một tập log chẩn đoán được chọn, không đồng nghĩa mọi logger của mọi thư viện đều chuyển sang mức DEBUG. Nếu ứng dụng thất bại quá sớm, trước khi tới giai đoạn tạo context phù hợp, báo cáo có thể không đầy đủ. Khi đó exception gốc và log trước thời điểm lỗi quan trọng hơn việc cố truy cập một endpoint chưa chạy.

### 4.2. Lấy báo cáo qua Actuator khi tiến trình đã chạy

Trong môi trường chẩn đoán đã kiểm soát quyền truy cập, có thể công bố endpoint `conditions`. Ví dụ dùng management server riêng, chỉ lắng nghe loopback:

```yaml
management:
  server:
    port: 9091
    address: 127.0.0.1
  endpoints:
    web:
      exposure:
        include: health,conditions
```

Với giả định không đổi base path và không có cấu hình loại trừ khác:

```bash
curl -i http://127.0.0.1:9091/actuator/conditions
```

Đây là cấu hình dành cho một phiên chẩn đoán cục bộ, không phải chỉ dẫn bật endpoint trên mọi môi trường. Nếu tiến trình nằm trong container, loopback là loopback của container; request từ máy host không tự truy cập được cổng đó. Nếu có Spring Security, request vẫn phải đáp ứng rule bảo mật hiện hành.

Endpoint `conditions` cũng chịu quy tắc bật/tắt và exposure. Việc không đọc được chính endpoint này không chứng minh toàn bộ auto-configuration bị hỏng. Có thể dùng log khởi động thay thế mà không cần thay đổi bề mặt HTTP.

### 4.3. Đọc kết quả theo từng lớp cấu hình và từng context

Báo cáo thường tổ chức kết quả theo application context, với các nhóm như:

- `positiveMatches`: cấu hình hoặc phương thức cấu hình khớp các điều kiện đã đánh giá.
- `negativeMatches`: cấu hình không khớp; bên trong có thể có cả điều kiện đã khớp và chưa khớp.
- `unconditionalClasses`: các cấu hình không được liệt kê theo dạng có điều kiện như các nhóm trên.

Dạng log có cách trình bày khác JSON của endpoint. Không dựa vào một đường dẫn JSON chép từ phiên bản khác mà bỏ qua cấu trúc thực tế đang nhận.

Với management server riêng hoặc hệ thống nhiều context, đọc đúng context và quan hệ cha/con. Một điều kiện tìm bean có thể phụ thuộc phạm vi tìm kiếm của chính điều kiện đó; không suy luận rằng bean ở bất kỳ context nào cũng thỏa điều kiện.

Bắt đầu từ cấu hình gần triệu chứng nhất, rồi đọc nguyên văn thông điệp điều kiện. Không cần đọc toàn bộ danh sách negative matches như một danh sách lỗi.

### 4.4. Các loại điều kiện hay gặp

| Điều kiện | Cần kiểm tra gì? | Cách hiểu sai thường gặp |
| --- | --- | --- |
| `@ConditionalOnClass` | Class yêu cầu có trên classpath phù hợp không? | Có tên dependency trong source là đủ |
| `@ConditionalOnMissingBean` | Có bean nào khiến cấu hình mặc định lùi lại không? | Negative match luôn là lỗi |
| `@ConditionalOnBean` | Bean tiên quyết đã có theo phạm vi và giai đoạn đánh giá chưa? | Có class của bean là tương đương có bean |
| `@ConditionalOnProperty` | Tên thuộc tính, giá trị có hiệu lực, `havingValue`, `matchIfMissing` | Mọi chuỗi khác rỗng đều có cùng ý nghĩa |
| Điều kiện ứng dụng web | Servlet, reactive hay không có web runtime? | Có Actuator thì mặc nhiên là Servlet |
| Điều kiện endpoint | Endpoint có đáp ứng quy tắc availability liên quan không? | Khớp điều kiện đồng nghĩa request luôn trả 200 |

Một negative match có thể là hành vi đúng. Ví dụ ứng dụng cung cấp bean tùy chỉnh và auto-configuration dùng `@ConditionalOnMissingBean` để tránh tạo thêm bean mặc định. Đây thường là cơ chế nhường quyền cho cấu hình của ứng dụng, không phải hỏng Spring Boot.

Ngược lại, có class trên classpath không chứng minh binary của nó tương thích với mọi caller. `@ConditionalOnClass` không phải bộ kiểm tra toàn diện cho mọi method mà ứng dụng có thể gọi sau đó.

### 4.5. Lần theo nguyên nhân thay vì sửa mọi negative match

Ví dụ một tính năng cần một bean tiên quyết nhưng bean đó không được tạo:

```text
Tính năng đích không được cấu hình
        |
        v
Thiếu bean tiên quyết
        |
        v
Cấu hình tạo bean tiên quyết không khớp
        |
        v
Thiếu class / sai property / có bean tùy chỉnh / sai loại ứng dụng
```

Hãy đi tới điều kiện nguyên thủy có thể kiểm chứng. Dừng ở câu “không tìm thấy bean” thường mới mô tả một mắt xích trung gian.

Không suy luận ngược rằng cứ thêm `@Bean` cho loại đang thiếu là sửa được gốc rễ. Có thể làm vậy sẽ che lỗi dependency, thay đổi hành vi hoặc làm cấu hình mặc định tiếp tục lùi lại.

## 5. Nguồn thứ hai: xác định cấu hình có hiệu lực

### 5.1. Tách file nguồn, Environment và đối tượng đã bind

Ba thứ sau có liên quan nhưng không đồng nhất:

1. Dòng YAML/properties được viết trong source hoặc file triển khai.
2. Giá trị được tra cứu trong Spring `Environment`.
3. Giá trị đã bind vào một bean `@ConfigurationProperties`.

Một bean cấu hình có thể có giá trị mặc định trong Java, chuyển đổi kiểu hoặc validation. Nếu thuộc tính không có trong Environment, bean vẫn có thể nhận giá trị mặc định của nó. Nếu bean không được đăng ký hoặc không được bind, việc file có key đúng cũng không làm đối tượng tự tồn tại.

`@Value` và `@ConfigurationProperties` cũng không phải một cơ chế hoàn toàn giống nhau. Khi điều tra lỗi binding của một bean cụ thể, hãy kiểm tra đúng kiểu bean và cơ chế mà nó dùng.

### 5.2. Kiểm tra nguồn ghi đè và profile

Những nguồn thường cần đối chiếu:

- Cấu hình mặc định đóng trong JAR.
- File cấu hình bên ngoài và file theo profile.
- Các nguồn được nạp qua `spring.config.import`.
- Biến môi trường của tiến trình.
- Java system properties.
- Tham số dòng lệnh.
- Các nguồn do test hoặc framework mở rộng thêm vào, nếu đang chạy trong những môi trường đó.

Trong các ví dụ thông thường của Spring Boot, tham số `--ten-thuoc-tinh=gia-tri` có thể ghi đè giá trị trong file cấu hình và biến môi trường. Nhưng không biến nhận xét này thành một bảng ưu tiên tuyệt đối cho mọi PropertySource tùy chỉnh. Khi có nghi ngờ, đọc thứ tự nguồn thực tế và giá trị đã bind.

Đặc biệt kiểm tra:

- Profile active có đúng với instance đang lỗi không.
- Có nhiều profile không và thứ tự áp dụng có ảnh hưởng không.
- Container có nhận biến môi trường mới sau khi triển khai lại không.
- Đối số dòng lệnh có còn giữ giá trị từ lần chạy cũ không.
- File ngoài có nằm đúng vị trí được Spring Boot nạp không.
- `spring.config.location` có thay thế tập vị trí mặc định, hay `spring.config.additional-location` chỉ bổ sung vị trí không.
- Một key có đang được viết theo tên thuộc tính cũ mà phiên bản hiện tại không dùng không.

Không coi một file tên `.env` là nguồn được Spring Boot tự động đọc trong mọi môi trường. Nó chỉ có tác dụng khi công cụ triển khai hoặc mã tích hợp thực sự nạp và truyền giá trị cho ứng dụng.

### 5.3. Dùng env và configprops có mục tiêu

Nếu endpoint đã được cấp quyền cho phiên chẩn đoán, `env` giúp đối chiếu PropertySource và nguồn gốc giá trị khi dữ liệu đó có sẵn. `configprops` giúp xem các bean cấu hình đã được bind.

Ví dụ chỉ dành cho môi trường cục bộ được kiểm soát:

```yaml
management:
  server:
    port: 9091
    address: 127.0.0.1
  endpoints:
    web:
      exposure:
        include: health,conditions,env,configprops
  endpoint:
    env:
      show-values: never
    configprops:
      show-values: never
```

Tìm đúng thuộc tính thay vì thu thập toàn bộ cấu hình:

```bash
curl -i http://127.0.0.1:9091/actuator/env/management.endpoints.web.exposure.include
curl -i http://127.0.0.1:9091/actuator/configprops
```

Chế độ `show-values: never` giữ giá trị được che. Một giá trị bị che không đồng nghĩa nó rỗng hoặc không tồn tại. Có thể vẫn dùng thông tin tên nguồn và origin khi được trả về; nếu cần xác nhận giá trị cụ thể, ưu tiên chẩn đoán có giới hạn với những key không nhạy cảm trong nội bộ tiến trình.

Không đổi thành hiển thị mọi giá trị để tiện xem. Ngay cả khi một số giá trị được che, tên nguồn, đường dẫn file hoặc cấu trúc cấu hình vẫn có thể là thông tin nội bộ.

Endpoint `configprops` không phải bản liệt kê mọi key mà ứng dụng có thể đọc. Các property chỉ được truy cập qua `Environment` hoặc `@Value` không tự trở thành một bean `@ConfigurationProperties` trong báo cáo đó.

Nếu không được phép expose các endpoint chẩn đoán, dùng log có chọn lọc hoặc một phiên chạy cục bộ với cùng cấu hình không nhạy cảm. Không cần bật endpoint chỉ để hoàn thành quy trình suy luận.

### 5.4. Đừng nhầm truy vấn một key với binding cả collection

Một danh sách YAML có thể được biểu diễn bằng các key có chỉ số, ví dụ:

```yaml
management:
  endpoints:
    web:
      exposure:
        include:
          - health
          - prometheus
```

Khi đó, tra cứu chuỗi ở key cha `management.endpoints.web.exposure.include` không phải lúc nào cũng cho cùng kết quả như binding danh sách. Việc một phép tra cứu đơn key không trả chuỗi chưa đủ để kết luận danh sách rỗng.

Để đối chiếu binding trong mã chẩn đoán, có thể dùng Spring Boot Binder:

```java
List<String> exposed = Binder.get(environment)
        .bind("management.endpoints.web.exposure.include",
                Bindable.listOf(String.class))
        .orElseGet(List::of);
```

Đây là đoạn minh họa trong ứng dụng Spring Boot, cần `Environment environment` và các import `java.util.List`, `org.springframework.boot.context.properties.bind.Binder`, `org.springframework.boot.context.properties.bind.Bindable`.

Kết quả binding này cho thấy giá trị danh sách ở key đang kiểm tra. Nó chưa bao gồm mọi quyết định khác như danh sách exclude hoặc endpoint có tồn tại không.

### 5.5. Tách enablement, exposure và authorization

Với Actuator theo mô hình cấu hình Spring Boot 3.3.x:

| Câu hỏi | Cấu hình/bằng chứng liên quan |
| --- | --- |
| Endpoint có bị tắt không? | `management.endpoint.<id>.enabled`, cấu hình mặc định endpoint và conditions tương ứng |
| Endpoint có được công bố qua HTTP không? | `management.endpoints.web.exposure.include/exclude` |
| Request có được đọc endpoint không? | Spring Security, bảo mật proxy và danh tính của request |
| Request có vào đúng nơi không? | Port, base path, path mapping, context path và định tuyến |

Danh sách exclude được ưu tiên hơn include. Vì vậy, nhìn thấy `prometheus` trong include vẫn chưa đủ nếu một nguồn khác đặt nó trong exclude.

Cũng cần phân biệt `management.endpoint.<id>.enabled` với cấu hình của subsystem đứng sau endpoint. Ví dụ thuộc tính bật exporter Prometheus của Boot 3.3.x là `management.prometheus.metrics.export.enabled`; đây không phải cùng một công tắc với HTTP exposure.

Không chép các thuộc tính `access` hoặc quy tắc endpoint của một thế hệ Spring Boot khác rồi mặc định chúng có hiệu lực trên 3.3.x. Hãy xác định phiên bản trước, rồi mới giải nghĩa tên key.

## 6. Nguồn thứ ba: xác định bộ phiên bản thực sự đang chạy

### 6.1. Phân biệt khai báo, resolve, đóng gói và nạp lớp

Có ít nhất bốn mức bằng chứng:

```text
build.gradle khai báo dependency
                 |
                 v
Gradle resolve runtimeClasspath
                 |
                 v
Các thư viện thực sự nằm trong artifact được triển khai
                 |
                 v
Class thực sự được JVM nạp trong tiến trình đang chạy
```

Nếu chỉ xem build file, bạn mới biết ý định khai báo. Một dependency bắc cầu, constraint, platform, rule `force`, dependency substitution hoặc cấu hình đóng gói có thể làm kết quả khác đi.

Nếu chỉ build thành công trên máy cá nhân, bạn chưa chứng minh server đang chạy đúng JAR vừa build. Nếu có nhiều replica, chúng có thể đang chạy các thế hệ artifact khác nhau trong lúc rollout.

### 6.2. Kiểm tra dependency graph đã resolve

Với Gradle, chạy task trên đúng project ứng dụng:

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-boot-actuator-autoconfigure --configuration runtimeClasspath
./gradlew dependencyInsight --dependency micrometer-core --configuration runtimeClasspath
./gradlew dependencyInsight --dependency micrometer-registry-prometheus --configuration runtimeClasspath
```

Trên Windows dùng `gradlew.bat`. Nếu là multi-project build, thêm project path phù hợp vào tên task.

Trong kết quả, đọc cả:

- Phiên bản cuối cùng được chọn.
- Đường dependency nào đưa thư viện vào.
- Constraint hoặc rule nào quyết định phiên bản.
- Có dependency cũ bị thay thế bởi phiên bản khác không.
- Thư viện có ở runtime classpath hay chỉ ở test/compile configuration.

Không chỉ tìm một dòng có tên artifact. Hai người cùng nói “đã có Micrometer” vẫn có thể đang nhìn vào các configuration khác nhau.

Spring Boot cung cấp bộ dependency được phối hợp thông qua dependency management/BOM. Xác minh cơ chế quản lý đó thực sự được áp dụng và có bị override không. Boot Gradle plugin, dependency-management plugin và việc import platform/BOM có vai trò khác nhau; không coi riêng việc có một plugin tên Spring Boot là bằng chứng đầy đủ rằng mọi phiên bản đang được quản lý đúng.

### 6.3. Kiểm tra artifact và bản triển khai

Với executable JAR thông thường của Spring Boot, có thể xem danh sách mục bằng công cụ JDK:

```bash
jar tf build/libs/conditions-lab.jar
```

Các dependency thường nằm dưới `BOOT-INF/lib/`. Đối chiếu các JAR liên quan với dependency graph đã resolve.

Nếu triển khai bằng container, lớp JAR được tách ra hoặc một kiểu classpath khác, kiểm tra cấu trúc thực tế của artifact/image tương ứng; không mặc định mọi ứng dụng đều có cùng bố cục executable JAR.

Đối chiếu checksum hoặc mã artifact của bản build với bản đang triển khai. Không cần in toàn bộ biến môi trường để chứng minh việc này. Kiểm tra cả:

- Tiến trình có khởi động từ đúng artifact không.
- Container tag có trỏ tới đúng image digest không.
- `bootRun`, chạy từ IDE và `java -jar` có dùng cùng tập dependency/cấu hình không.
- JAR cũ có còn trên classpath do script chạy hoặc thư mục thư viện ngoài không.
- Các replica có cùng mã bản dựng và cùng thời điểm rollout dự kiến không.

### 6.4. Khi cần, xác minh nguồn lớp đã được nạp

Với lỗi binary khó xác định, nguồn lớp JVM đang sử dụng có giá trị hơn tên dependency trong build file.

Đoạn sau minh họa cách lấy thông tin cho một lớp đã nạp, dùng trong mã chẩn đoán nội bộ:

```java
static void printClassOrigin(Class<?> type) {
    var domain = type.getProtectionDomain();
    var source = domain == null ? null : domain.getCodeSource();
    var location = source == null
            ? "unavailable"
            : source.getLocation().toExternalForm();

    System.out.println("class=" + type.getName());
    System.out.println("source=" + location);
    System.out.println("version="
            + type.getPackage().getImplementationVersion());
}
```

Ví dụ gọi `printClassOrigin(io.micrometer.core.instrument.MeterRegistry.class)` trong một dự án có Micrometer.

Đây là phương thức hỗ trợ, không phải chương trình độc lập. Vị trí và version phụ thuộc cách đóng gói; version có thể là `null`. Không tự điền một phiên bản suy đoán khi metadata không có. Không biến đường dẫn nội bộ của máy chủ thành thông tin công khai.

Với kiểu nạp lớp đặc biệt, CodeSource có thể không đủ để kết luận. Khi đó cần kết hợp thông tin classloader và cơ chế logging lớp của JVM trong phiên chẩn đoán phù hợp.

### 6.5. Đọc đúng nhóm lỗi phiên bản

| Lỗi | Ý nghĩa định hướng | Cần đối chiếu |
| --- | --- | --- |
| `ClassNotFoundException` | Classloader không tìm được lớp được yêu cầu | Tên lớp, dependency runtime, cơ chế nạp lớp |
| `NoClassDefFoundError` | JVM không có định nghĩa lớp sử dụng được khi cần | Dependency thiếu hoặc lỗi khởi tạo lớp trước đó; đọc cause |
| `NoSuchMethodError` | Caller gọi method mà binary đích được nạp không cung cấp | Lớp gọi, lớp đích, chữ ký method và nguồn JAR của cả hai |
| `AbstractMethodError` | Không đáp ứng được hợp đồng method lúc liên kết/thực thi | Bộ binary interface/implementation đang phối hợp |
| `UnsupportedClassVersionError` | Bytecode yêu cầu Java mới hơn runtime hiện tại | Java dùng để biên dịch, toolchain và JVM dùng để chạy |

`NoClassDefFoundError` không luôn đồng nghĩa “chỉ cần thêm một JAR”. Nếu lần khởi tạo static trước đó thất bại, cần tìm exception ban đầu.

`NoSuchMethodError` không thường được sửa bằng thay giá trị exposure của endpoint. Conditions có thể đã khớp vì class tồn tại, nhưng chữ ký method giữa các binary vẫn không tương thích.

Java 21 tạo class file version 65; Java 17 dùng version 61. Một ứng dụng được biên dịch target Java 21 không tự chạy được trên JVM 17 chỉ vì Spring Boot 3.3 hỗ trợ Java 17 làm mức tối thiểu.

Không nâng một thư viện ngẫu nhiên lên bản mới nhất để thử vận may. Trước hết xác định bộ version được Boot quản lý, các override và lý do tồn tại của override; sau đó sửa theo một tập tương thích có thể kiểm chứng.

## 7. Ghép ba nguồn thành một chuỗi nguyên nhân

Một kết luận có sức thuyết phục cần nối được:

```text
Triệu chứng quan sát được
          |
          v
Cơ chế có thể tạo triệu chứng đó
          |
          v
Conditions / cấu hình / binary xác nhận cơ chế
          |
          v
Thay đổi nhỏ nhất dựa trên bằng chứng
          |
          v
Kiểm chứng lại trên cùng loại bản triển khai
```

### 7.1. Tình huống A: conditions khớp nhưng endpoint trả 404

Giả sử đã xác nhận gọi đúng cổng và đường dẫn quản trị. Báo cáo cho thấy cấu hình endpoint liên quan được áp dụng. Trong source, include có `prometheus`, nhưng nguồn cấu hình bên ngoài đặt:

```properties
management.endpoints.web.exposure.exclude=prometheus
```

Chuỗi lập luận:

1. Có endpoint/bean không đồng nghĩa có HTTP exposure.
2. Cấu hình có hiệu lực chứa exclude cho endpoint đang hỏi.
3. Exclude được ưu tiên hơn include.
4. Vì vậy, sửa include trong file mặc định không loại bỏ được exclude đang thắng.

Cách sửa dựa trên bằng chứng là chỉnh đúng nguồn exclude theo yêu cầu vận hành, khởi động/triển khai lại theo cơ chế của hệ thống, rồi kiểm tra URL và cấu hình có hiệu lực. Không cần thêm bean endpoint thủ công hoặc bật mọi endpoint.

Nếu sau khi loại trừ giả thuyết exposure mà vẫn 404, tiếp tục kiểm tra mapping và proxy. Không giữ nguyên kết luận chỉ vì nó từng phù hợp với một instance khác.

### 7.2. Tình huống B: không có registry được kỳ vọng

Ứng dụng mong có exporter Prometheus nhưng điều kiện liên quan cho thấy không đáp ứng một tiền đề.

Các nhánh cần phân biệt:

- Thiếu class: kiểm tra runtimeClasspath và artifact có registry không.
- Thuộc tính tắt exporter: tìm giá trị thắng trong Environment.
- Cấu hình mặc định lùi lại vì bean tùy chỉnh: xác định bean đó có chủ ý hay không.
- Loại ứng dụng hoặc điều kiện khác không phù hợp: đọc nguyên văn điều kiện, không gán mọi negative match cho dependency.

Với Boot 3.3.x, exporter Prometheus thông thường dùng `micrometer-registry-prometheus` của nhánh Prometheus Java client mới; lớp registry ở package `io.micrometer.prometheusmetrics`. Nhánh tương thích client cũ dùng artifact `micrometer-registry-prometheus-simpleclient` và package `io.micrometer.prometheus`.

Nếu mã tùy chỉnh, dependency và cấu hình auto-configuration đang nhắm vào hai họ client khác nhau, “đã có thư viện Prometheus” là một kết luận quá rộng. Cần xác định đúng artifact, package và registry mà endpoint sử dụng.

Cũng cần tách trường hợp exporter có sẵn nhưng meter được ghi vào một registry riêng. Conditions của exporter không chứng minh mọi meter trong ứng dụng đã được đăng ký vào nó.

### 7.3. Tình huống C: khởi động lỗi NoSuchMethodError sau khi thêm thư viện

Giả sử stack trace chỉ tới lời gọi giữa một extension và thư viện nền:

1. Xác định class caller và class đích từ stack trace.
2. Dùng dependencyInsight tìm phiên bản được resolve của cả hai phía.
3. Kiểm tra JAR đóng gói và artifact thực sự triển khai.
4. Nếu còn nghi ngờ, kiểm tra nguồn lớp được nạp.
5. Đối chiếu hợp đồng binary và cơ chế quản lý phiên bản của Boot.
6. Loại bỏ/chỉnh override hoặc thay extension bằng phiên bản tương thích.
7. Build và khởi động lại chính artifact sẽ triển khai.

Không khẳng định báo cáo conditions “đúng” thì mọi dependency phải tương thích. Báo cáo đó không thay thế kiểm tra liên kết binary.

Nếu ứng dụng chưa khởi động được, không yêu cầu gọi `/actuator/conditions` như điều kiện bắt buộc để tiếp tục. Log và artifact là bằng chứng khả dụng ở giai đoạn này.

### 7.4. Tình huống D: endpoint trả 401 nhưng có nhiều negative matches

Một báo cáo chứa nhiều cấu hình không khớp là bình thường: ứng dụng Servlet không cần khớp tất cả cấu hình reactive; không dùng một database thì cấu hình database tương ứng có thể không được áp dụng.

Với HTTP `401`, kiểm tra danh tính, kiểu xác thực và security chain áp dụng cho request. Nếu request tới đúng endpoint và bị yêu cầu xác thực, việc cố làm mọi negative match thành positive không giúp cấp quyền cho request.

Conditions có thể hữu ích khi xác định bean bảo mật nào được tạo hoặc cấu hình mặc định nào đã lùi lại. Nó không phải trace quyết định cấp quyền của từng HTTP request.

### 7.5. Tình huống E: health contributor tồn tại nhưng status là DOWN

Một datasource hoặc health contributor được auto-configure thành công chỉ chứng minh các tiền đề để tạo nó đã được đáp ứng. Database, broker hoặc dịch vụ bên ngoài vẫn có thể không kết nối được khi kiểm tra sức khỏe.

Đọc chi tiết lỗi được phép xem, đối chiếu cấu hình kết nối có hiệu lực và trạng thái tài nguyên. Không ép health thành UP hoặc xóa contributor chỉ để làm báo cáo trông tốt hơn.

## 8. Thực hành: một thuộc tính, ba bằng chứng

Bài thực hành sau giúp thấy rõ quan hệ giữa:

- Giá trị trong Environment.
- Giá trị đã bind vào bean cấu hình.
- Quyết định tạo bean theo `@ConditionalOnProperty`.

### 8.1. Điều kiện chạy

Dùng một dự án Spring Boot 3.3.x có Gradle wrapper, Java 17+ và cơ chế quản lý dependency của Boot. Phần dependency cần có:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}

tasks.named('bootJar') {
    archiveFileName = 'conditions-lab.jar'
}
```

Đây là phần cấu hình bổ sung cho dự án đã có plugin Boot, không phải toàn bộ build file. Với repository dùng orchestration riêng, áp dụng qua cơ chế build của repository thay vì tạo cấu hình trùng.

Để kết quả không bị nhiễu, bài thực hành tối giản không thêm Spring Security, không thêm PropertySource tùy chỉnh và không thêm cấu hình cùng prefix từ nguồn khác.

### 8.2. Mã Java

Tệp `src/main/java/demo/conditions/ConditionalLabApplication.java`:

```java
package demo.conditions;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;

@SpringBootApplication
@EnableConfigurationProperties(
        ConditionalLabApplication.SampleProperties.class)
public class ConditionalLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(ConditionalLabApplication.class, args);
    }

    @Bean
    @ConditionalOnProperty(
            prefix = "diagnostics.sample",
            name = "enabled",
            havingValue = "true",
            matchIfMissing = false)
    SampleMarker sampleMarker() {
        return new SampleMarker();
    }

    @Bean
    ApplicationRunner printEvidence(
            Environment environment,
            SampleProperties properties,
            ApplicationContext context) {
        return args -> {
            System.out.println("environment.enabled="
                    + environment.getProperty("diagnostics.sample.enabled"));
            System.out.println("bound.enabled=" + properties.isEnabled());
            System.out.println("sampleMarker.present="
                    + context.containsBean("sampleMarker"));
        };
    }

    static final class SampleMarker {
    }

    @ConfigurationProperties(prefix = "diagnostics.sample")
    public static class SampleProperties {
        private boolean enabled;

        public boolean isEnabled() {
            return enabled;
        }

        public void setEnabled(boolean enabled) {
            this.enabled = enabled;
        }
    }
}
```

Tệp `src/main/resources/application.yml`:

```yaml
diagnostics:
  sample:
    enabled: true

management:
  endpoints:
    web:
      exposure:
        include: health,conditions
```

Đây là ứng dụng Spring Boot cần dependency đầy đủ; không biên dịch riêng tệp bằng `javac` mà thiếu classpath của framework.

### 8.3. Lần chạy một: chỉ dùng cấu hình trong file

```bash
./gradlew bootJar
java -jar build/libs/conditions-lab.jar --debug
```

Trên Windows, thay lệnh Gradle bằng `gradlew.bat bootJar`.

Trong các log khác của Spring Boot, ba dòng do runner của ví dụ in ra là:

```text
environment.enabled=true
bound.enabled=true
sampleMarker.present=true
```

Conditions sẽ cho thấy phương thức cấu hình `sampleMarker` khớp điều kiện thuộc tính. Nội dung thông điệp cụ thể có thể khác theo phiên bản; điều cần đối chiếu là tên thuộc tính, yêu cầu giá trị `true` và kết quả khớp.

Nếu cần đọc qua HTTP trong bài thực hành không có Security và dùng cổng mặc định:

```bash
curl -i http://localhost:8080/actuator/conditions
```

Không coi toàn bộ JSON hoặc timestamp log là stdout cố định của bài tập.

### 8.4. Lần chạy hai: ghi đè bằng dòng lệnh

Dừng tiến trình của lần chạy một rồi chạy cùng JAR:

```bash
java -jar build/libs/conditions-lab.jar --debug --diagnostics.sample.enabled=false
```

Ba dòng do runner in ra:

```text
environment.enabled=false
bound.enabled=false
sampleMarker.present=false
```

Dòng `enabled: true` trong file không thay đổi, nhưng tham số dòng lệnh đã thắng. Conditions cho biết điều kiện tạo `sampleMarker` không khớp. Không cần sửa dependency để giải thích sự khác biệt này.

Đây là ví dụ một negative match hoàn toàn đúng với cấu hình được yêu cầu.

### 8.5. Lần chạy ba: bỏ hẳn thuộc tính khỏi file

Trong bản thử nghiệm riêng, bỏ phần `diagnostics.sample.enabled`, build lại JAR rồi chạy không truyền thuộc tính đó:

```bash
./gradlew bootJar
java -jar build/libs/conditions-lab.jar --debug
```

Ba dòng do runner in ra:

```text
environment.enabled=null
bound.enabled=false
sampleMarker.present=false
```

Giải thích:

- `Environment.getProperty(...)` không tìm được key nên trả `null`.
- Trường boolean trong `SampleProperties` giữ giá trị mặc định Java là `false`.
- `matchIfMissing=false` khiến bean không được tạo khi key thiếu.

Vì thế, một giá trị `false` trong bean cấu hình chưa đủ để kết luận Environment có một key với chuỗi `"false"`. Phải đối chiếu cả trạng thái thiếu key và giá trị mặc định.

### 8.6. Kiểm tra vị trí của JVM system property

Đây là cú pháp truyền Java system property:

```bash
java -Ddiagnostics.sample.enabled=false -jar build/libs/conditions-lab.jar
```

Còn đây là cú pháp tham số ứng dụng Spring Boot:

```bash
java -jar build/libs/conditions-lab.jar --diagnostics.sample.enabled=false
```

`-D...` phải nằm ở phần đối số JVM trước `-jar`. Đặt nó sau tên JAR không biến nó thành Java system property.

Để mỗi lần thử có một giả thuyết rõ ràng, không truyền cùng lúc nhiều nguồn ghi đè cho cùng key. Khi cần thử ưu tiên giữa hai nguồn, ghi lại chính xác hai nguồn đó và kết quả Environment quan sát được.

## 9. Quy trình điều tra có thể lặp lại

### Bước 1: khóa đúng bản triển khai và triệu chứng

Ghi instance, artifact/image digest hoặc mã bản dựng, thời điểm khởi động, request và phản hồi. Chọn một sự cố cụ thể, chẳng hạn “endpoint metrics trả 404 trên replica B”, thay vì “Actuator không hoạt động”.

### Bước 2: xác định lớp cần giải thích

Tách mạng, HTTP mapping, bảo mật, tạo bean, binding, binary và tài nguyên ngoài. Chọn evidence đầu tiên theo bảng phân loại triệu chứng; không truy vấn một endpoint chưa thể tồn tại trong tiến trình đang crash.

### Bước 3: lấy conditions liên quan

Đọc cấu hình đích, điều kiện không khớp và chuỗi tiền đề. Phân biệt negative match có chủ ý với thiếu điều kiện ngoài ý muốn. Nếu không tìm thấy cấu hình trong báo cáo, kiểm tra cả dependency, exclusion và phạm vi báo cáo; vắng một tên chưa đủ để kết luận một lý do duy nhất.

### Bước 4: truy ra cấu hình có hiệu lực

Xác nhận tên key đúng phiên bản, profile, nguồn thắng và giá trị đã bind nếu có. Với collection, xem binding của collection. Với giá trị bị che, không suy luận nó rỗng và không yêu cầu xuất toàn bộ secrets.

### Bước 5: xác minh thư viện thực tế

Chỉ đào sâu dependency khi triệu chứng hoặc conditions đưa tới giả thuyết về classpath/binary. So sánh graph đã resolve, artifact và runtime. Đừng biến mọi lỗi `401` thành một cuộc nâng cấp thư viện.

### Bước 6: thay đổi một nguyên nhân đã có bằng chứng

Ví dụ sửa đúng nguồn exclude, bỏ một override phiên bản gây xung đột hoặc điều chỉnh rule cấp quyền cho danh tính scrape. Giữ phạm vi sửa gắn với giả thuyết đang kiểm chứng.

### Bước 7: kiểm tra lại từ đầu đường quan sát

Build/triển khai lại khi cần, xác nhận đúng artifact, đọc giá trị có hiệu lực và thử lại hành vi từng lỗi. Nếu có nhiều replica, kiểm tra đủ phạm vi bị ảnh hưởng. Gỡ cấu hình/log chẩn đoán tạm thời theo cách vận hành của môi trường.

## 10. Viết kết luận từ bằng chứng

Một biên bản ngắn nên trả lời được:

| Nội dung | Ví dụ cách ghi |
| --- | --- |
| Triệu chứng | Endpoint trả 404 trên đúng cổng quản trị của instance đã xác minh |
| Kỳ vọng | Endpoint được công bố cho bên giám sát được cấp quyền |
| Conditions | Cấu hình liên quan đã được áp dụng; không thiếu tiền đề tạo bean đang xét |
| Cấu hình có hiệu lực | Exclude từ nguồn cấu hình bên ngoài loại endpoint khỏi HTTP exposure |
| Bộ phiên bản | Graph và artifact không có thay đổi liên quan giải thích triệu chứng này |
| Nguyên nhân | Cấu hình exclude có hiệu lực, không phải thiếu dependency |
| Cách sửa | Chỉnh nguồn exclude đúng theo yêu cầu triển khai |
| Kiểm chứng | Sau triển khai lại, URL phản hồi đúng và kiểm tra được từ phía giám sát |

Bảng là ví dụ cho một nguyên nhân cụ thể; không dùng nó như kết luận mặc định của mọi sự cố.

Nếu chưa đủ bằng chứng, ghi giả thuyết và phép kiểm tra tiếp theo. Chẳng hạn “nghi xung đột binary; cần xác minh nguồn class được nạp” chính xác hơn việc gọi mọi lỗi khởi động là “sai version”.

Ba câu hỏi nên được trả lời bằng bằng chứng của cùng tiến trình: **Spring Boot đã quyết định tạo gì, tiến trình thực sự đọc cấu hình nào, và JVM đang chạy bộ thư viện nào?** Khi ba câu trả lời nhất quán với triệu chứng, cách sửa mới có cơ sở và có thể kiểm chứng lại.
