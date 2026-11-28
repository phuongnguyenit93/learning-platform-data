# Lựa chọn web starter Spring MVC hoặc Spring WebFlux

Khi khởi tạo một ứng dụng **SPRING_CLOUD_SERVICE_BROKER**, bạn cần chọn web stack để tiếp nhận các HTTP request từ nền tảng cloud. Spring Boot cung cấp hai lựa chọn phổ biến: **Spring MVC** thông qua **spring-boot-starter-web** và **Spring WebFlux** thông qua **spring-boot-starter-webflux**.

Cả hai đều có thể được dùng để xây dựng ứng dụng HTTP, nhưng khác nhau về mô hình xử lý request, cách sử dụng thread và yêu cầu đối với các thư viện gọi hệ thống bên ngoài. Lựa chọn phù hợp phụ thuộc vào kiểu I/O của broker, khả năng của các SDK nhà cung cấp, kinh nghiệm của nhóm và yêu cầu vận hành.

Trong module **SPRING_CLOUD_SERVICE_BROKER**, ứng dụng broker triển khai Open Service Broker API (OSB API) để cung cấp catalog, service plan và các thao tác provision, update, bind, unbind, deprovision. Các request này thuộc control plane: chúng điều khiển vòng đời tài nguyên như database, cache hoặc message broker. Web starter đảm nhiệm lớp HTTP của ứng dụng; nghiệp vụ cấp phát và quản lý trạng thái vẫn do các service của broker thực hiện.

## 1. Web starter quyết định điều gì?

Spring Boot starter là dependency tập hợp các thư viện và cấu hình mặc định để đưa một nhóm chức năng vào ứng dụng. Với web application, starter ảnh hưởng đến web runtime được Spring Boot tự động cấu hình.

Hai lựa chọn chính:

- **Spring MVC** chạy trên Servlet API, thường dùng embedded Tomcat khi khởi tạo ứng dụng Spring Boot mặc định.
- **Spring WebFlux** cung cấp mô hình reactive, non-blocking và thường dùng Reactor Netty làm server mặc định khi không có web stack khác chi phối.

Cả hai đều có thể tiếp nhận HTTP request, ánh xạ endpoint, đọc JSON, kiểm tra dữ liệu, áp dụng bảo mật và trả HTTP response. Khác biệt nằm ở cách framework tổ chức việc xử lý request và cách ứng dụng tương tác với I/O.

Web starter không tự tạo ra nghiệp vụ OSB. Bạn vẫn cần khai báo catalog, triển khai xử lý service instance và binding, tích hợp API của nhà cung cấp, lưu trạng thái operation và bảo vệ credentials.

## 2. Spring MVC với spring-boot-starter-web

Spring MVC là lựa chọn dựa trên Servlet API. Trong mô hình thông thường, request được tiếp nhận bởi server và xử lý trên một thread thuộc worker pool. Khi handler gọi một thư viện đồng bộ để truy vấn database hoặc gọi API nhà cung cấp, thread xử lý request thường chờ thao tác đó hoàn tất.

Ví dụ, broker nhận yêu cầu provision PostgreSQL. Handler gọi SDK quản trị của nhà cung cấp, SDK gửi HTTP request đồng bộ và chờ kết quả. Với MVC, cách lập trình này tương đối tự nhiên vì nhiều thư viện Java truyền thống được thiết kế theo kiểu blocking.

Dependency web cơ bản trong Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
~~~

### Khi nào MVC phù hợp?

MVC thường là lựa chọn phù hợp khi:

- Broker sử dụng SDK của nhà cung cấp có API blocking.
- Tầng persistence dùng JDBC hoặc thư viện đồng bộ.
- Nghiệp vụ provision, update và binding chủ yếu được viết theo cách tuần tự.
- Lưu lượng request ở mức mà Servlet worker pool có thể đáp ứng.
- Nhóm phát triển quen với Spring MVC, Servlet Filter và mô hình Spring Security trên Servlet.
- Ưu tiên cách triển khai dễ đọc, dễ gỡ lỗi và tương thích với hệ sinh thái Java hiện có.

Một service broker thường thực hiện các thao tác quản trị có xác thực, kiểm tra tham số, ghi trạng thái và gọi API bên ngoài. Nếu các thành phần tích hợp đều blocking, MVC giúp tránh việc phải chuyển đổi toàn bộ chuỗi xử lý sang reactive chỉ để sử dụng một web runtime.

### Điều cần quản lý với MVC

Mỗi request đang chờ I/O có thể chiếm một thread trong worker pool. Nếu nhà cung cấp phản hồi chậm hoặc có nhiều thao tác đồng thời, pool có thể bị cạn. Khi đó, request mới phải chờ, độ trễ tăng và broker có thể từ chối hoặc timeout request.

Vì vậy, cần:

- Cấu hình giới hạn kết nối, timeout và thread pool theo tải thực tế.
- Không để request HTTP chờ quá lâu cho một quy trình cấp phát kéo dài.
- Dùng operation bất đồng bộ theo OSB API khi thao tác cần nhiều thời gian.
- Theo dõi số request đang xử lý, thời gian chờ nhà cung cấp, timeout và tỷ lệ lỗi.
- Đảm bảo thao tác blocking có giới hạn và có khả năng hủy hoặc kết thúc theo timeout.

MVC không có nghĩa là ứng dụng không thể dùng các API reactive. Spring MVC có thể hỗ trợ một số kiểu trả về reactive như Mono. Tuy nhiên, nếu phần xử lý bên dưới vẫn gọi JDBC hoặc SDK blocking, request vẫn phụ thuộc vào I/O blocking và không tự trở thành non-blocking chỉ vì handler trả về một kiểu reactive.

## 3. Spring WebFlux với spring-boot-starter-webflux

Spring WebFlux là web stack reactive của Spring. Nó sử dụng mô hình non-blocking I/O và Project Reactor, với hai kiểu dữ liệu thường gặp là **Mono** cho kết quả không hoặc một phần tử và **Flux** cho một chuỗi phần tử.

Trong mô hình WebFlux, server có thể xử lý nhiều kết nối đồng thời mà không cần giữ một thread riêng bị chặn cho từng thao tác I/O. Khi handler gọi một client reactive, luồng xử lý có thể tiếp tục khi chờ phản hồi; callback hoặc pipeline reactive tiếp tục khi dữ liệu sẵn sàng.

Dependency web cơ bản trong Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webflux</artifactId>
</dependency>
~~~

Ví dụ minh họa một pipeline reactive gọi dịch vụ bên ngoài:

~~~java
public Mono<ProviderResult> provision(ProvisionCommand command) {
    return webClient.post()
        .uri("/resources")
        .bodyValue(command)
        .retrieve()
        .bodyToMono(ProviderResult.class);
}
~~~

Đây là ví dụ về cách một client reactive có thể trả kết quả mà không cần chặn thread trong lúc chờ I/O. Trong ứng dụng thực tế, cần bổ sung xử lý lỗi, timeout, xác thực, retry có điều kiện và ghi nhận trạng thái operation.

### Khi nào WebFlux phù hợp?

WebFlux có thể phù hợp khi:

- Broker thực hiện nhiều I/O đồng thời đến các API quản trị hoặc hệ thống lưu trữ.
- Các client HTTP, driver database và thư viện tích hợp quan trọng đều có phiên bản non-blocking.
- Nhóm đã có kinh nghiệm với Reactor, Mono, Flux và cách gỡ lỗi reactive pipeline.
- Ứng dụng cần xử lý nhiều kết nối đồng thời với tài nguyên thread hạn chế.
- Các tầng từ HTTP handler đến persistence và provider client có thể duy trì mô hình non-blocking.

Lợi ích của WebFlux rõ hơn khi toàn bộ chuỗi I/O có khả năng non-blocking. Nếu handler gọi một SDK blocking trực tiếp trên event-loop thread, thao tác đó có thể chặn thread đang phục vụ nhiều request khác. Khi phải dùng thư viện blocking, cần cô lập nó trên scheduler phù hợp, giới hạn mức đồng thời và quản lý timeout. Cách làm này có thể giảm lợi ích của WebFlux và làm hệ thống khó vận hành hơn.

### Điều cần quản lý với WebFlux

Reactive pipeline không tự bảo đảm rằng thao tác nghiệp vụ an toàn hoặc có thể retry. Broker vẫn phải xử lý các vấn đề như:

- Chỉ retry thao tác có tính idempotent hoặc đã có cơ chế chống tạo tài nguyên trùng.
- Không retry mù quáng một lệnh provision khi không biết nhà cung cấp đã tạo tài nguyên hay chưa.
- Đặt timeout cho từng lời gọi I/O và cho toàn bộ quy trình phù hợp.
- Xử lý lỗi trong pipeline, chuyển lỗi thành trạng thái operation có ý nghĩa và ghi nhận correlation ID.
- Tránh gọi API blocking trên event-loop thread.
- Quản lý backpressure khi một pipeline có thể phát sinh hoặc nhận dữ liệu nhanh hơn tốc độ xử lý.

WebFlux không thay thế cơ chế lưu trạng thái bền vững. Nếu broker cần phục hồi sau khi tiến trình bị dừng, operation và trạng thái tài nguyên vẫn phải được lưu vào nơi lưu trữ phù hợp.

## 4. So sánh Spring MVC và Spring WebFlux

| Tiêu chí | Spring MVC | Spring WebFlux |
|---|---|---|
| Dependency phổ biến | spring-boot-starter-web | spring-boot-starter-webflux |
| Nền tảng web | Servlet API | Reactive web stack |
| Mô hình I/O | Thường blocking | Non-blocking khi dùng đúng thư viện |
| Xử lý đồng thời | Worker thread xử lý request; cần quản lý pool | Event loop và reactive pipeline |
| Kiểu lập trình | Imperative, tuần tự | Reactive với Mono và Flux |
| Thư viện tích hợp | Thuận tiện với JDBC và SDK blocking | Phù hợp với client và driver reactive |
| Độ phức tạp | Thường dễ tiếp cận hơn với nhóm Spring truyền thống | Cần hiểu Reactor, scheduler, backpressure và cách xử lý lỗi |
| Khi có I/O blocking | Mô hình tự nhiên, vẫn cần timeout và giới hạn pool | Phải cô lập blocking I/O, tránh chặn event loop |
| Trường hợp phù hợp | Broker dùng nhiều thư viện đồng bộ | Broker có chuỗi I/O non-blocking và tải đồng thời cao |

Không nên chọn WebFlux chỉ vì nó mới hơn hoặc nghe có vẻ nhanh hơn. Cũng không nên mặc định MVC luôn đủ cho mọi tải. Cần đánh giá loại I/O, độ trễ của nhà cung cấp, số thao tác đồng thời, giới hạn tài nguyên và khả năng của thư viện đang sử dụng.

## 5. Chọn web starter cho Spring Cloud Service Broker

Hãy kiểm tra các thành phần thực tế của broker trước khi thêm dependency. Một broker có thể tích hợp nhiều loại hệ thống:

| Thành phần tích hợp | Đặc điểm cần kiểm tra |
|---|---|
| API quản trị cloud | SDK cung cấp client blocking hay reactive? Có hỗ trợ timeout và retry không? |
| Database lưu instance và operation | Dùng JDBC/JPA hay reactive database driver? |
| Kho bí mật | API truy cập đồng bộ hay non-blocking? |
| Hệ thống queue/job | Có cần đưa provision dài hạn sang worker riêng không? |
| Xác thực và bảo mật | Đang dùng Servlet security hay reactive security? |
| Observability | Có thể truyền trace, correlation ID và metric xuyên suốt request, operation không? |

Một quy trình chọn có thể thực hiện như sau:

1. Liệt kê các thao tác OSB mà broker hỗ trợ: catalog, provision, update, bind, unbind, deprovision và tra cứu last operation.
2. Xác định thư viện mà từng thao tác cần gọi, đặc biệt là SDK nhà cung cấp và driver persistence.
3. Kiểm tra API blocking hoặc non-blocking của từng thư viện.
4. Chọn web stack phù hợp với mô hình I/O chủ đạo và năng lực của nhóm.
5. Kiểm tra dependency tree để biết starter nào được kéo vào trực tiếp hoặc gián tiếp.
6. Chạy thử các endpoint OSB và đo độ trễ, mức sử dụng thread, kết nối, timeout và khả năng chịu tải.
7. Ghi lại quyết định kiến trúc để các thành viên không thêm nhầm web starter khi mở rộng module.

### Ví dụ chọn MVC

Giả sử broker quản lý PostgreSQL trên một cloud provider. Ứng dụng dùng SDK quản trị blocking để tạo database, JDBC để lưu service instance và binding, đồng thời dùng một worker nền để xử lý các thao tác provision kéo dài.

Trong trường hợp này, MVC thường là lựa chọn đơn giản và phù hợp:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-open-service-broker</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
</dependencies>
~~~

Đoạn cấu hình minh họa cách khai báo web starter MVC cùng starter của Spring Cloud Open Service Broker. Phiên bản của Spring Boot và Spring Cloud cần được quản lý bằng bộ BOM hoặc release train tương thích với nhau. Cần kiểm tra tài liệu đúng phiên bản framework đang sử dụng để xác nhận web runtime và các dependency được framework yêu cầu.

### Ví dụ chọn WebFlux

Giả sử broker quản lý nhiều dịch vụ cloud, mỗi thao tác cần gọi nhiều API bên ngoài bằng WebClient, lưu trạng thái qua reactive database driver và xử lý nhiều request I/O đồng thời. Nhóm phát triển đã sử dụng Reactor trong các service khác và có khả năng vận hành reactive pipeline.

Khi đó, WebFlux có thể là lựa chọn hợp lý:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-open-service-broker</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-webflux</artifactId>
    </dependency>
</dependencies>
~~~

Đây cũng là cấu hình minh họa. Cần xác nhận phiên bản Spring Cloud Open Service Broker đang dùng hỗ trợ web stack đã chọn và không có dependency khác khiến Spring Boot tự cấu hình sang web stack còn lại.

## 6. Không nhầm reactive với xử lý bất đồng bộ của OSB API

Đây là điểm rất quan trọng khi xây dựng service broker.

**Reactive/non-blocking** mô tả cách ứng dụng sử dụng thread và chờ I/O. **Thao tác bất đồng bộ của OSB API** mô tả hợp đồng giữa nền tảng và broker khi một thao tác vòng đời không thể hoàn tất trong thời gian của request HTTP ban đầu.

Hai khái niệm này độc lập:

- Một broker dùng MVC vẫn có thể hỗ trợ provision bất đồng bộ theo OSB API.
- Một broker dùng WebFlux vẫn phải triển khai trạng thái operation, lưu trữ bền vững và endpoint tra cứu tiến độ.
- Trả về Mono không có nghĩa là tài nguyên cloud đã được tạo xong.
- Dùng worker nền không bắt buộc phải dùng WebFlux.

Ví dụ, nền tảng gửi yêu cầu provision một database lớn. Broker xác thực request, kiểm tra service plan, ghi operation vào database rồi đưa công việc vào hàng đợi. Broker trả phản hồi cho biết thao tác đã được tiếp nhận và nền tảng có thể truy vấn trạng thái qua endpoint last operation. Worker thực hiện lời gọi đến nhà cung cấp, cập nhật tiến độ và lưu kết quả.

~~~mermaid
sequenceDiagram
    participant P as Nền tảng cloud
    participant B as Service broker
    participant DB as Kho trạng thái
    participant W as Worker
    participant C as Cloud provider

    P->>B: Provision request
    B->>DB: Lưu instance và operation
    B-->>P: Chấp nhận thao tác bất đồng bộ
    B->>W: Đưa công việc vào hàng đợi
    W->>C: Tạo tài nguyên
    C-->>W: Kết quả cấp phát
    W->>DB: Cập nhật operation
    P->>B: Last operation
    B->>DB: Đọc trạng thái
    B-->>P: Trạng thái hiện tại
~~~

Mô hình này có thể triển khai phía HTTP bằng MVC hoặc WebFlux. Việc xử lý công việc dài hạn nên được thiết kế sao cho có thể phục hồi sau lỗi, tránh tạo tài nguyên trùng và không phụ thuộc vào việc request HTTP ban đầu còn mở hay không.

## 7. Lưu ý khi có cả hai web starter trong dependency

Một ứng dụng không nên thêm đồng thời hai web starter mà không có chủ đích. Spring Boot phải xác định loại web application để cấu hình server, dispatcher và các thành phần tự động.

Trong cấu hình Spring Boot thông thường, nếu cả MVC và WebFlux cùng có mặt trên classpath, auto-configuration thường ưu tiên Spring MVC. Điều này có thể khiến ứng dụng khởi động bằng Servlet stack dù người phát triển dự định dùng WebFlux.

Một số dự án MVC vẫn cần WebClient để gọi API bên ngoài. Việc cần một HTTP client reactive không đồng nghĩa ứng dụng phải chuyển toàn bộ web server sang WebFlux. Hãy kiểm tra dependency và loại ứng dụng được Spring Boot nhận diện, đồng thời xác nhận cách cấu hình phù hợp với phiên bản đang dùng.

Có thể kiểm tra dependency bằng Maven:

~~~bash
mvn dependency:tree
~~~

Hoặc với Gradle:

~~~bash
./gradlew dependencies
~~~

Khi phát hiện cả hai starter, hãy xác định dependency nào kéo chúng vào và quyết định web stack có chủ đích. Tránh loại trừ dependency một cách tùy tiện nếu framework broker đang cần nó.

## 8. Bảo mật, kiểm thử và vận hành theo web stack

Dù chọn MVC hay WebFlux, broker vẫn phải bảo vệ các endpoint OSB và tài nguyên được quản lý.

**Xác thực và phân quyền**

- Chỉ cho phép nền tảng hoặc caller đã được xác thực truy cập API quản trị broker.
- Áp dụng chính sách phân quyền cho các thao tác đọc catalog, provision, update, bind, unbind và deprovision.
- Bảo vệ endpoint và dữ liệu credentials; không đưa secrets vào log hoặc thông báo lỗi.
- Cấu hình TLS và quản lý vòng đời chứng thư phù hợp với môi trường triển khai.

**Kiểm soát request và lỗi**

- Kiểm tra service ID, plan ID, instance ID, binding ID và parameters.
- Giới hạn kích thước request và thời gian xử lý.
- Trả mã HTTP và cấu trúc lỗi theo hợp đồng OSB API.
- Ghi correlation ID để nối request HTTP với operation nền và lời gọi provider.
- Không tiết lộ thông tin nhạy cảm từ exception của nhà cung cấp.

**Kiểm thử endpoint**

Nên kiểm thử tối thiểu các nhóm tình huống sau:

| Nhóm kiểm thử | Nội dung xác minh |
|---|---|
| Catalog | Danh sách service và plan có đúng cấu trúc, ID ổn định |
| Provision | Request hợp lệ, request sai plan, retry cùng instance ID |
| Update | Plan và parameters được kiểm tra theo khả năng hỗ trợ |
| Bind và unbind | Credentials được tạo, trả về và thu hồi đúng |
| Deprovision | Tài nguyên được thu hồi và retry không gây xóa nhầm |
| Last operation | Trạng thái đang chạy, thành công và thất bại được phản ánh đúng |
| Timeout và lỗi provider | Broker xử lý lỗi có kiểm soát và không báo thành công giả |
| Bảo mật | Request chưa xác thực hoặc không đủ quyền bị từ chối |
| Tải đồng thời | Không cạn thread, connection pool hoặc event loop khi tải tăng |

Với MVC, quan sát worker thread pool, thời gian chờ và số request đang bị chặn. Với WebFlux, quan sát event-loop, scheduler, số tác vụ blocking bị offload, connection pool và độ trễ của reactive pipeline. Cả hai đều cần metric cho operation và provider API vì đó thường là nơi phát sinh độ trễ đáng kể của broker.

## 9. Quyết định lựa chọn cho dự án

Có thể dùng các câu hỏi sau để chốt lựa chọn:

| Câu hỏi | Nếu câu trả lời là Có |
|---|---|
| Hầu hết SDK provider và persistence đang dùng là blocking? | Ưu tiên đánh giá Spring MVC |
| Nhóm đã vận hành tốt Reactor và các thư viện tích hợp đều non-blocking? | Đánh giá Spring WebFlux |
| Broker chủ yếu thực hiện request quản trị với tải vừa phải và dùng thư viện Java đồng bộ? | MVC thường là điểm khởi đầu hợp lý |
| Broker có nhiều I/O đồng thời và toàn bộ chuỗi gọi hỗ trợ reactive? | WebFlux có thể đem lại lợi ích |
| Chỉ muốn xử lý provision lâu dài mà không giữ HTTP request? | Thiết kế operation bất đồng bộ và worker; không cần đổi web stack chỉ vì lý do này |

Không có lựa chọn đúng cho mọi service broker. Hãy chọn stack tương thích với thư viện và mô hình vận hành thực tế, sau đó xác nhận bằng kiểm thử tích hợp và tải. Nếu dự án bắt đầu với MVC, bạn vẫn có thể tổ chức service layer rõ ràng để thay đổi client hoặc persistence sau này. Nếu chọn WebFlux, hãy duy trì non-blocking từ đầu đến cuối và cô lập những thành phần blocking không thể thay thế.

Với Spring Cloud Open Service Broker, chất lượng của broker cuối cùng phụ thuộc vào việc tuân thủ OSB API, quản lý trạng thái bền vững, idempotency, xử lý lỗi provider và bảo vệ credentials. MVC hay WebFlux là quyết định ở lớp web runtime; nó cần hỗ trợ các yêu cầu đó một cách ổn định và dễ vận hành.

