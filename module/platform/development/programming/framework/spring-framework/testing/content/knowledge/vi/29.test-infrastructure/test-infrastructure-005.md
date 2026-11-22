# Phân biệt container đã chạy với dịch vụ đã sẵn sàng

## Container running chưa có nghĩa dịch vụ đã sẵn sàng

Trong kiểm thử tích hợp, Testcontainers hoặc Docker Compose thường khởi động database, message broker, cache hay một service HTTP để ứng dụng Spring kết nối tới. Một container chuyển sang trạng thái running chỉ cho biết tiến trình chính của container đang chạy theo góc nhìn của Docker. Điều đó chưa chứng minh dịch vụ bên trong đã khởi tạo xong và có thể xử lý request.

Ví dụ, PostgreSQL có thể đã có process chạy nhưng vẫn đang phục hồi dữ liệu hoặc khởi tạo database. Redis có thể đã mở process nhưng chưa hoàn tất nạp dữ liệu. Một ứng dụng HTTP có thể đã bind port nhưng chưa tạo xong connection pool, chưa chạy migration hoặc chưa nạp cấu hình nghiệp vụ.

Nếu test bắt đầu gửi request ngay khi container vừa running, kết quả có thể phụ thuộc tốc độ máy, tải CI hoặc thời gian khởi động của image. Test có thể thất bại ngẫu nhiên với connection refused, timeout hoặc lỗi database chưa sẵn sàng.

Hãy phân biệt các mức trạng thái:

| Mức quan sát | Điều nó chứng minh | Điều nó chưa chứng minh |
| --- | --- | --- |
| Container được tạo | Docker đã tạo container | Process đã chạy |
| Container running | Process chính đang chạy | Dịch vụ đã mở cổng hoặc hoàn tất khởi tạo |
| Port đang lắng nghe | Có TCP listener tại cổng kiểm tra | Protocol và ứng dụng đã xử lý được request |
| Health check thành công | Probe được cấu hình báo dịch vụ khỏe theo tiêu chí của nó | Mọi API hoặc nghiệp vụ cần cho test đều hoạt động |
| Readiness probe thành công | Dịch vụ tuyên bố đã sẵn sàng nhận loại traffic được probe kiểm tra | Các dependency bên ngoài không nằm trong probe cũng sẵn sàng |
| Kiểm tra nghiệp vụ thành công | Một hành vi cụ thể của dịch vụ hoạt động | Mọi đường xử lý khác đều hoạt động |

Mục tiêu của test là chờ đúng mức sẵn sàng mà nó cần. Một test chỉ cần xác nhận TCP kết nối được có thể dùng port check. Test cần truy vấn database phải chờ database chấp nhận kết nối và có schema cần thiết. Test gọi API của service khác nên chờ health endpoint hoặc một probe thể hiện service thực sự xử lý được request.

## Readiness là điều kiện của dịch vụ, không phải trạng thái của Docker

Readiness là một tiêu chí do hệ thống định nghĩa. Probe nên phản ánh điều kiện tối thiểu để dịch vụ nhận loại request mà test sẽ gửi.

Với database, các mức kiểm tra có thể gồm:

- TCP port đã mở.
- Database chấp nhận kết nối và xác thực.
- Database/schema mà ứng dụng cần đã tồn tại.
- Migration và dữ liệu khởi tạo cần thiết đã hoàn tất.

Với HTTP service, các mức kiểm tra có thể gồm:

- Port HTTP đang lắng nghe.
- Endpoint health trả status thành công.
- Readiness health group báo trạng thái sẵn sàng.
- Endpoint nghiệp vụ tối thiểu có thể xử lý request với dependency cần thiết.

Không phải test nào cũng cần probe nghiệp vụ sâu. Một probe quá sâu có thể tạo phụ thuộc vòng: service A chờ service B, service B lại chờ service A, khiến cả hai không bao giờ báo ready. Hãy chọn probe ngắn, ổn định và kiểm tra đúng dependency bắt buộc.

### Phân biệt liveness và readiness

Hai khái niệm này thường xuất hiện trong health endpoint:

- **Liveness** trả lời tiến trình có còn sống và có thể tiếp tục chạy hay không. Nếu liveness thất bại liên tục, nền tảng có thể khởi động lại container.
- **Readiness** trả lời service có thể nhận traffic hay chưa. Nếu readiness thất bại, nền tảng có thể tạm ngừng gửi traffic tới service mà không cần restart.

Một service có thể liveness thành công nhưng readiness thất bại trong lúc đang khởi tạo hoặc mất kết nối tới dependency bắt buộc. Vì vậy, nếu mục tiêu là chờ API sẵn sàng nhận request, probe readiness thường phù hợp hơn probe liveness.

Trong Spring Boot Actuator, các health group như readiness có thể được cung cấp qua endpoint tương ứng khi đã bật và expose theo cấu hình. Đường dẫn, quyền truy cập và nội dung phản hồi phụ thuộc cấu hình ứng dụng. Test phải dùng đúng endpoint thực sự được bật; không mặc định mọi ứng dụng đều có sẵn đường dẫn readiness.

## Testcontainers: chờ bằng WaitStrategy

Testcontainers cung cấp các wait strategy để chờ điều kiện sẵn sàng sau khi container được khởi động. Có thể cấu hình chiến lược chờ trên GenericContainer bằng waitingFor(...).

### Chờ port lắng nghe

~~~java
GenericContainer<?> service = new GenericContainer<>(
        DockerImageName.parse("example/service:1.0"))
        .withExposedPorts(8080)
        .waitingFor(Wait.forListeningPort())
        .withStartupTimeout(Duration.ofSeconds(60));
~~~

Wait.forListeningPort() đợi cổng được expose có TCP listener. Nó hữu ích khi test chỉ cần biết process đã mở cổng và có thể chấp nhận kết nối ở tầng TCP.

Port open không chứng minh endpoint HTTP trả response đúng. Ứng dụng có thể mở connector trước khi hoàn tất khởi tạo handler, migration hoặc dependency. Nếu test cần gọi HTTP API, hãy cân nhắc HTTP wait strategy.

### Chờ HTTP endpoint

~~~java
GenericContainer<?> service = new GenericContainer<>(
        DockerImageName.parse("example/service:1.0"))
        .withExposedPorts(8080)
        .waitingFor(
                Wait.forHttp("/actuator/health/readiness")
                        .forPort(8080)
                        .forStatusCode(200)
                        .withStartupTimeout(Duration.ofSeconds(90))
        );
~~~

Wait.forHttp(...) gửi HTTP probe tới container và chờ response thỏa điều kiện. Trong ví dụ, container chỉ được xem là ready khi readiness endpoint trả HTTP 200.

Để cách này hoạt động, image phải chạy ứng dụng có endpoint đó, endpoint phải được expose và probe phải truy cập được. Nếu actuator được bảo vệ bằng authentication hoặc chỉ bind trên interface khác, cần cấu hình probe phù hợp hoặc cung cấp một health endpoint riêng cho môi trường test.

Một HTTP 200 đơn thuần cũng có thể chưa đủ. Nếu endpoint luôn trả 200 kể cả khi health status là DOWN, hãy cấu hình probe hoặc strategy kiểm tra nội dung phản hồi phù hợp với hợp đồng health của ứng dụng. Đừng chỉ dựa vào mã HTTP nếu body mới chứa trạng thái cần xác nhận.

### Chờ log báo khởi tạo xong

Một số image phát log ổn định khi dịch vụ sẵn sàng:

~~~java
GenericContainer<?> database = new GenericContainer<>(
        DockerImageName.parse("example/database:1.0"))
        .withExposedPorts(5432)
        .waitingFor(
                Wait.forLogMessage(".*ready for connections.*\\n", 1)
                        .withStartupTimeout(Duration.ofSeconds(90))
        );
~~~

Wait.forLogMessage(...) chờ một mẫu log xuất hiện đủ số lần. Đây có thể là lựa chọn phù hợp khi image không có health endpoint nhưng có log khởi tạo đáng tin cậy.

Log chỉ là tín hiệu do ứng dụng phát ra. Một dòng “Started” có thể xuất hiện trước khi dependency nghiệp vụ sẵn sàng; format log cũng có thể thay đổi theo phiên bản image. Chỉ dùng log làm readiness signal khi dòng đó thực sự đánh dấu điều kiện mà test cần và ổn định qua các phiên bản được hỗ trợ.

### Dùng Docker healthcheck có sẵn

Nếu image khai báo Docker HEALTHCHECK, Testcontainers có thể chờ trạng thái health bằng:

~~~java
GenericContainer<?> service = new GenericContainer<>(
        DockerImageName.parse("example/service:1.0"))
        .waitingFor(Wait.forHealthcheck())
        .withStartupTimeout(Duration.ofSeconds(90));
~~~

Wait.forHealthcheck() dựa vào healthcheck được định nghĩa trong image hoặc cấu hình container. Nếu image không có HEALTHCHECK, chiến lược này không có probe để đánh giá.

Healthcheck cần kiểm tra đúng điều kiện readiness. Một lệnh chỉ kiểm tra process tồn tại hoặc port mở có thể báo healthy quá sớm. Hãy đọc nội dung HEALTHCHECK của image trước khi tin rằng nó đại diện cho khả năng phục vụ request.

### Chờ lệnh kiểm tra thành công

Nếu image có command kiểm tra nội bộ, Testcontainers có thể chờ command thành công:

~~~java
GenericContainer<?> database = new GenericContainer<>(
        DockerImageName.parse("example/database:1.0"))
        .waitingFor(
                Wait.forSuccessfulCommand("database-cli", "ping")
                        .withStartupTimeout(Duration.ofSeconds(90))
        );
~~~

Command được chạy bên trong container. Nó hữu ích khi dịch vụ có CLI hoặc health utility riêng và không cần mở endpoint công khai. Lệnh phải kết thúc với exit code thành công khi điều kiện readiness đạt; không nên dùng command chỉ kiểm tra process nếu test cần kết nối database thực tế.

## Startup check và wait strategy giải quyết hai câu hỏi khác nhau

Testcontainers phân biệt kiểm tra container đã khởi động theo lifecycle của Docker với việc chờ dịch vụ sẵn sàng theo WaitStrategy.

- Startup check xác định container có đi vào trạng thái chạy theo điều kiện startup strategy hay không.
- WaitStrategy xác định điều kiện dịch vụ mà test yêu cầu đã đạt chưa, ví dụ port mở, HTTP health trả 200 hoặc log báo ready.

Một container có thể vượt qua startup check nhưng vẫn chưa vượt qua readiness wait. Đây là tình huống bình thường: Docker đã chạy process nhưng ứng dụng bên trong vẫn đang khởi tạo.

Khi cấu hình Testcontainers, không nên coi việc start() trả về là một tín hiệu mơ hồ. Lệnh start hoàn tất sau khi các điều kiện startup và wait strategy được đáp ứng. Nếu container không đạt readiness trong startup timeout, Testcontainers sẽ báo lỗi thay vì để test tiếp tục gửi request tới dịch vụ chưa sẵn sàng.

## Ví dụ Spring integration test với container HTTP service

Một test có thể khởi động service container và chờ readiness endpoint trước khi dùng host cùng mapped port:

~~~java
static final GenericContainer<?> catalogService =
        new GenericContainer<>(DockerImageName.parse("example/catalog:1.0"))
                .withExposedPorts(8080)
                .waitingFor(
                        Wait.forHttp("/actuator/health/readiness")
                                .forPort(8080)
                                .forStatusCode(200)
                )
                .withStartupTimeout(Duration.ofSeconds(90));

@BeforeAll
static void startCatalogService() {
    catalogService.start();
}

@AfterAll
static void stopCatalogService() {
    catalogService.stop();
}

@Test
void callsCatalogAfterItIsReady() {
    String baseUrl = "http://" + catalogService.getHost()
            + ":" + catalogService.getMappedPort(8080);

    // Dùng baseUrl để tạo HTTP client và thực hiện request cần kiểm tra.
}
~~~

Đây là ví dụ về lifecycle thủ công; trong dự án JUnit 5 có thể dùng Testcontainers extension với @Testcontainers và @Container để quản lý start/stop. Dù dùng cách nào, container phải hoàn tất readiness wait trước khi test thực hiện request nghiệp vụ.

Nếu service là dependency của một Spring Boot application đang được kiểm thử, hãy đảm bảo container được khởi động và sẵn sàng trước khi ApplicationContext tạo client hoặc thực hiện kết nối đầu tiên. Có thể cung cấp URL/credential qua DynamicPropertySource hoặc dùng ServiceConnection trong các phiên bản Spring Boot hỗ trợ. Cơ chế truyền property không thay thế readiness wait: nó chỉ cung cấp thông tin kết nối.

## Database: port mở, connection được và schema sẵn sàng

Database minh họa rõ sự khác nhau giữa các mức readiness. Giả sử test dùng PostgreSQL:

1. Container running: tiến trình PostgreSQL đang chạy.
2. Port 5432 lắng nghe: TCP connection có thể được mở.
3. Database accept connection: PostgreSQL đã sẵn sàng nhận lệnh đăng nhập.
4. Schema sẵn sàng: migration đã tạo bảng và constraint mà ứng dụng cần.
5. Fixture sẵn sàng: dữ liệu seed mà test dựa vào đã được nạp.

Test truy vấn repository cần ít nhất mức 3 và 4; test cần dữ liệu seed cần thêm mức 5. Chỉ chờ port mở có thể không đủ.

Với image PostgreSQL, Docker healthcheck thường có thể dùng pg_isready để kiểm tra server chấp nhận kết nối:

~~~yaml
services:
  database:
    image: postgres:16
    environment:
      POSTGRES_DB: app
      POSTGRES_USER: app
      POSTGRES_PASSWORD: secret
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U app -d app"]
      interval: 2s
      timeout: 3s
      retries: 30
      start_period: 5s
~~~

pg_isready kiểm tra trạng thái server PostgreSQL có nhận kết nối hay không. Nó không chứng minh migration của ứng dụng đã chạy hoặc các bảng cần thiết đã tồn tại. Migration thường là bước khởi tạo riêng; test cần đợi bước đó hoàn tất trước khi truy vấn repository.

Một cách tổ chức rõ ràng là để migration chạy như một bước setup có thể chờ hoàn tất, sau đó mới bắt đầu test. Nếu migration chạy trong Spring ApplicationContext, cần chờ context hoàn tất startup trước khi thực hiện test method. Nếu migration chạy trong một container/job riêng, hãy chờ job đó kết thúc thành công.

## Docker Compose: depends_on và service_healthy

Trong Docker Compose, cú pháp depends_on dạng ngắn chủ yếu xác định thứ tự khởi động service. Nó không mặc nhiên chứng minh dependency đã sẵn sàng nhận request.

Nếu service phụ thuộc cần được healthcheck trước khi service khác khởi động, dùng depends_on dạng dài với condition service_healthy:

~~~yaml
services:
  database:
    image: postgres:16
    environment:
      POSTGRES_DB: app
      POSTGRES_USER: app
      POSTGRES_PASSWORD: secret
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U app -d app"]
      interval: 2s
      timeout: 3s
      retries: 30

  application:
    image: example/application:1.0
    depends_on:
      database:
        condition: service_healthy
~~~

Compose sẽ chờ healthcheck của database đạt trước khi tạo service application theo quan hệ dependency này. Healthcheck vẫn phải phản ánh đúng readiness; nếu chỉ kiểm tra process thì Compose cũng chỉ chờ process.

Compose còn hỗ trợ điều kiện service_completed_successfully cho dependency dạng job chạy xong, ví dụ migration container. Cách này phù hợp khi ứng dụng chỉ nên khởi động sau khi bước chuẩn bị schema hoàn tất.

Khi chạy test bằng Compose, hãy phân biệt:

- Compose đã tạo hoặc start service.
- Healthcheck của service đã thành công.
- Job migration đã exit thành công.
- Ứng dụng đã hoàn tất khởi tạo và sẵn sàng nhận traffic.

Các tín hiệu này có thể xảy ra ở những thời điểm khác nhau. Test chỉ nên bắt đầu khi điều kiện cần thiết của chính nó đã đạt.

## Chọn probe phù hợp với dependency

| Dependency hoặc mục tiêu | Probe thường phù hợp | Giới hạn cần nhớ |
| --- | --- | --- |
| TCP service đơn giản | Listening port | Chỉ kiểm tra kết nối TCP |
| HTTP service | HTTP endpoint | Cần endpoint có ý nghĩa readiness và có thể truy cập |
| Spring Boot service | Actuator readiness health group | Phải bật/expose endpoint và cấu hình dependency health phù hợp |
| Database | Healthcheck bằng CLI hoặc truy vấn thật | Server accept connection chưa chứng minh schema/migration sẵn sàng |
| Message broker | Healthcheck hoặc command/protocol probe của broker | Port mở chưa chứng minh broker nhận publish/consume |
| Cache | Protocol ping/auth probe | Ping không nhất thiết xác nhận keyspace hoặc dữ liệu fixture |
| Service không có health endpoint | Log startup đáng tin cậy hoặc command nội bộ | Log/command có thể không phản ánh readiness nghiệp vụ |
| Migration job | Chờ process/job hoàn tất thành công | Job exit 0 không chứng minh dữ liệu seed của test khác đã sẵn sàng |

Một probe nên nhanh, có timeout, có kết quả xác định và ít side effect. Tránh probe ghi dữ liệu nghiệp vụ hoặc tạo tài nguyên mới mỗi lần được gọi.

## Timeout và lỗi readiness cần được xử lý rõ ràng

Mọi readiness wait nên có startup timeout hữu hạn. Nếu service không sẵn sàng, test phải dừng với thông tin đủ để tìm nguyên nhân thay vì chờ vô hạn.

Khi timeout xảy ra, hãy xem:

- Container có thực sự running hay đã exit?
- Port được probe có đúng cổng bên trong container không?
- HTTP path, protocol, status code và authentication có chính xác không?
- Healthcheck có được khai báo trong image hoặc Compose không?
- Service có đang chờ dependency khác, migration hoặc dữ liệu seed không?
- Log container cho thấy lỗi cấu hình, thiếu biến môi trường hay lỗi khởi tạo nào?

Không tăng timeout một cách máy móc để che lỗi cấu hình. Nếu service cần nhiều thời gian khởi động hơn trong CI, có thể điều chỉnh timeout có căn cứ, nhưng probe vẫn phải kiểm tra điều kiện readiness thật.

## Vì sao Thread.sleep không phải readiness check?

Một test thường dễ được viết như sau:

~~~java
container.start();
Thread.sleep(5_000);
callService();
~~~

Đoạn code giả định dịch vụ luôn sẵn sàng trong năm giây. Trên máy nhanh, test lãng phí thời gian; trên CI chậm, năm giây vẫn có thể không đủ. Sleep không kiểm tra được service đã sẵn sàng hay chưa.

WaitStrategy hoạt động theo hướng ngược lại: liên tục kiểm tra một điều kiện có ý nghĩa cho đến khi điều kiện đạt hoặc timeout. Test tiếp tục ngay khi readiness đạt, thay vì đợi hết một khoảng thời gian cố định.

Nếu tự viết polling, hãy dùng deadline và interval có giới hạn, xử lý exception tạm thời như connection refused, và trả lỗi cuối cùng kèm nguyên nhân khi hết thời gian. Không tạo vòng lặp vô hạn hoặc nuốt mọi exception rồi tiếp tục chờ.

## Những lỗi thường gặp

### Chỉ kiểm tra container.isRunning()

isRunning chỉ cho biết container đang chạy theo Docker. Nó không chứng minh database, broker hoặc HTTP server đã sẵn sàng xử lý request. Hãy dùng probe phù hợp với dịch vụ.

### Chỉ chờ port mở

Port có thể mở trước khi ứng dụng hoàn tất initialization. Với HTTP service, chờ readiness endpoint; với database, xác nhận server chấp nhận kết nối và schema cần thiết đã sẵn sàng.

### Dùng liveness endpoint làm readiness

Liveness thành công có thể chỉ chứng minh process còn sống. Nếu service vẫn đang khởi tạo hoặc dependency bắt buộc chưa kết nối, readiness có thể chưa đạt.

### Dùng healthcheck quá nông

Healthcheck chỉ kiểm tra process hoặc port có thể báo healthy quá sớm. Hãy xác định chính xác điều kiện mà healthcheck kiểm tra và liệu điều kiện đó có đủ cho test.

### Quên migration và seed data

Database accept connection không đồng nghĩa bảng hoặc dữ liệu test đã tồn tại. Hãy chờ bước migration/seed hoàn tất riêng biệt.

### Cấu hình timeout quá ngắn hoặc vô hạn

Timeout quá ngắn gây lỗi trên môi trường CI chậm; timeout vô hạn làm pipeline treo. Chọn giới hạn hữu hạn dựa trên startup time thực tế và giữ probe có ý nghĩa.

### Dùng Thread.sleep thay cho polling readiness

Sleep phụ thuộc tốc độ môi trường và không chứng minh điều kiện cần. Dùng WaitStrategy, Docker healthcheck hoặc polling có deadline.

### Nghĩ depends_on dạng ngắn chờ service healthy

depends_on dạng ngắn không phải health gate. Dùng healthcheck và condition service_healthy khi Compose cần chờ dependency sẵn sàng.

## Quy trình thiết lập hạ tầng kiểm thử đáng tin cậy

1. Xác định hành vi đầu tiên của test cần dependency ở trạng thái nào: port mở, protocol accept, API ready, schema migrated hay dữ liệu seed sẵn sàng.
2. Chọn probe phản ánh đúng trạng thái đó: listening port, HTTP, healthcheck, log hoặc command.
3. Khai báo probe cùng startup timeout hữu hạn trong Testcontainers hoặc Docker Compose.
4. Bảo đảm container và dependency được khởi động trước khi Spring ApplicationContext hoặc test client sử dụng chúng.
5. Chờ migration và fixture initialization hoàn tất riêng nếu healthcheck của database không bao gồm các bước này.
6. Khi timeout, thu thập container state, logs và kết quả probe để tìm nguyên nhân.
7. Chỉ thực hiện request hoặc truy vấn nghiệp vụ sau khi readiness condition cần thiết đã đạt.
8. Dừng và dọn container theo lifecycle của test để các lần chạy không giữ lại tài nguyên ngoài ý muốn.

Container running là một tín hiệu lifecycle; service ready là một điều kiện vận hành cần được kiểm chứng. Khi test định nghĩa readiness bằng probe đúng với dependency mà nó sử dụng, bộ test tránh được các lỗi khởi động ngẫu nhiên và phản ánh rõ ranh giới giữa hạ tầng đã chạy với dịch vụ thực sự có thể phục vụ yêu cầu.
