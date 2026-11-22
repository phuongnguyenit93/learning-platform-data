# Quan hệ giữa nhóm luồng, connection pool và khả năng xử lý đồng thời

## 1. Mục tiêu học tập

Một ứng dụng Spring Boot có thể nhận nhiều HTTP request cùng lúc nhưng vẫn phản hồi chậm, dù CPU còn rảnh. Nguyên nhân thường nằm ở giới hạn của các tài nguyên được chia sẻ: **luồng xử lý (thread)**, **kết nối cơ sở dữ liệu (connection)**, **hàng đợi (queue)**, thời gian giữ tài nguyên, và khả năng phục vụ của hệ thống phía sau.

Sau bài này, bạn cần giải thích được:

- Nhóm luồng (thread pool) quản lý công việc gì, connection pool quản lý tài nguyên gì, và tại sao hai nhóm này **không cùng một đơn vị đo**.
- Một HTTP request đồng bộ trong Spring MVC/Tomcat có thể giữ luồng trong khi chờ lấy kết nối JDBC; điều gì xảy ra khi một trong hai pool cạn.
- Vì sao tăng số luồng hoặc số kết nối không mặc nhiên tăng throughput, thậm chí có thể khiến hệ thống chậm hơn.
- Cách ước tính nhu cầu đồng thời bằng thời gian xử lý và định luật Little, nhận diện nút thắt qua metric, đo tải và điều chỉnh có kiểm chứng.
- Sự khác nhau giữa mô hình servlet blocking, xử lý bất đồng bộ, virtual threads và WebFlux ở góc nhìn tài nguyên.

Phạm vi chính là **Spring Boot Web MVC với embedded Tomcat và HikariCP/JDBC**. Những nguyên tắc về hàng đợi và tài nguyên hữu hạn cũng áp dụng cho connection pool gọi dịch vụ HTTP hoặc Redis, nhưng mỗi loại pool có cách vận hành riêng.

## 2. Ba khái niệm cần tách biệt

| Thành phần | Đối tượng được quản lý | Vai trò | Khi đạt giới hạn |
| --- | --- | --- | --- |
| **HTTP worker thread pool** của Tomcat | Các luồng thực thi tác vụ xử lý HTTP | Chạy controller, service, thao tác blocking | Request có thể phải chờ trong cơ chế tiếp nhận/xếp hàng hoặc bị từ chối khi các giới hạn phía trước cùng đầy |
| **JDBC connection pool** (thường là HikariCP) | Kết nối đã mở đến database, có thể cho mượn và tái sử dụng | Cho phép code mượn kết nối để truy vấn/transaction | `getConnection()` có thể **đợi** đến `connectionTimeout` rồi ném `SQLException` nếu không có kết nối |
| **Connection pool của HTTP client** | Kết nối mạng từ ứng dụng đến dịch vụ khác | Tái sử dụng kết nối đi ra ngoài, tùy client có cơ chế giới hạn riêng | Có thể chờ slot, mở kết nối mới hoặc lỗi tùy thư viện và cấu hình |

**Thread không phải connection.** Một luồng có thể xử lý HTTP mà không truy vấn database. Một request có thể mượn rồi trả nhiều kết nối theo từng bước. Một kết nối JDBC có thể được các request khác nhau tái sử dụng **theo thời gian**, nhưng tại một thời điểm một kết nối đang được mượn không phải slot tự do cho request khác.

“Nhóm luồng” ở đây là **thread pool/executor**. Khái niệm lớp `java.lang.ThreadGroup` tồn tại trong Java nhưng **không phải** bộ điều phối tài nguyên được đề cập trong tối ưu hóa HTTP thread pool.

Cần phân biệt thêm ba chữ “connection”:

1. **HTTP connection đi vào**: socket giữa client/proxy và Tomcat; HTTP keep-alive có thể giữ socket mở khi không có request đang chạy.
2. **JDBC connection**: kết nối từ ứng dụng đến database, do pool cho mượn.
3. **HTTP connection đi ra**: socket từ ứng dụng đến API khác, do HTTP client quản lý.

Một socket HTTP keep-alive đang rảnh **không đồng nghĩa** với một Tomcat worker thread đang bị giữ liên tục. Với HTTP/2, quan hệ giữa connection và các request còn có multiplexing. Vì thế đừng đánh đồng `max-connections` với `threads.max` hoặc `hikari.maximum-pool-size`.

## 3. Một request đồng bộ đi qua các tài nguyên như thế nào?

Xét endpoint Spring MVC gọi JDBC đồng bộ:

~~~text
Client
  |
  | HTTP connection
  v
Reverse proxy / Tomcat connector
  |
  | Chọn worker thread cho request
  v
Spring MVC: Controller -> Service
  |
  | dataSource.getConnection()
  +--> HikariCP có connection rảnh?
       | Có
       |   v
       | Database query / transaction
       |   |
       |   v
       | close() -> TRẢ connection về pool
       |
       ' Không
           |
           | Worker thread vẫn đang chờ getConnection()
           | (giới hạn bởi connectionTimeout)
           v
       Có connection -> tiếp tục
       Hết thời gian -> SQLException
  |
  v
Ghi response -> giải phóng worker thread
~~~

Điểm then chốt: trong một controller **blocking**, khi `getConnection()` phải chờ vì pool hết kết nối, **luồng servlet thường vẫn bị chiếm** trong thời gian chờ đó. Tức là nghẽn ở JDBC pool có thể kéo theo nghẽn ở HTTP thread pool. Client nhìn thấy response chậm, nhưng việc tăng `threads.max` chỉ có thể làm **nhiều luồng chờ** hơn nếu database không thể xử lý thêm.

Ví dụ với một request:

- Nhận và xử lý HTTP trước truy vấn: 20 ms, có worker thread nhưng chưa có kết nối JDBC.
- Chờ lấy kết nối: 150 ms, **có worker thread**, chưa mượn được connection.
- Truy vấn và giữ kết nối: 80 ms, **có cả worker thread lẫn JDBC connection**.
- Tạo và gửi response: 10 ms, vẫn có worker thread; connection đã trả nếu mã đóng đúng lúc.

Tổng thời gian đáp ứng gần 260 ms, nhưng thời gian giữ JDBC connection chỉ 80 ms. Hai pool có **thời gian chiếm dụng khác nhau**, nên không thể chọn kích thước bằng cách đặt chúng bằng nhau.

Thực tế phụ thuộc vùng transaction và thời điểm lấy/trả kết nối. Với JDBC, `Connection.close()` trên connection do pool cấp thường **trả connection về pool** thay vì đóng socket vật lý ngay. Nếu code quên đóng connection hoặc transaction kéo dài không cần thiết, các slot bị giữ lâu và hàng đợi sẽ tăng.

## 4. Giới hạn đồng thời là giới hạn theo từng công đoạn

Giả sử một instance Spring Boot được cấu hình:

- Tomcat tối đa **12** worker thread thông thường.
- HikariCP tối đa **3** JDBC connection trong pool.
- Database đủ khả năng xử lý ba truy vấn đồng thời trong thí nghiệm, chưa xét tài nguyên khác.

Nếu **12 request đồng bộ** gần như cùng lúc đều cần giữ một JDBC connection:

| Thời điểm minh họa | Worker đang phục vụ request | Connection JDBC được mượn | Request đang chờ mượn JDBC |
| --- | ---: | ---: | ---: |
| Ngay sau khi request vào đến đoạn JDBC (giả sử đủ worker đã được tạo) | 12 | 3 | 9 |
| Sau khi ba request đầu trả connection | Tối đa 12 | Tối đa 3 | Giảm dần |
| Khi tất cả hoàn tất | 0 | 0 đang mượn | 0 |

Đây là **kịch bản minh họa**, không phải cam kết về lịch chạy, số socket hoặc thời gian thực tế. Tomcat có thể tăng số worker dần dần; request có thể đến không đồng đều, timeout hoặc đi theo các nhánh không dùng database.

Khi pool kết nối chỉ có ba slot, chỉ tối đa ba request trong **cùng instance** được mượn connection tại một thời điểm. Tuy nhiên, đó không phải giới hạn “chỉ có ba HTTP request chạy”: các request còn lại có thể chạy logic khác, đợi connection hoặc đang nằm ở hàng đợi khác. Ngược lại, tăng pool lên 30 cũng không đảm bảo 30 truy vấn có ích nếu database chỉ đủ CPU, I/O hoặc khóa để xử lý vài truy vấn nhanh chóng.

Cách nhìn theo công đoạn:

~~~text
HTTP arrival
  -> [Tomcat worker: thời gian xử lý + thời gian đợi]
  -> [DB pool: chờ slot -> giữ connection -> trả slot]
  -> [Database: CPU / I-O / locks / network]
  -> [Response]
~~~

**Thông lượng (throughput)** được đo bằng request/giây hoàn thành; **độ đồng thời (concurrency)** là số công việc đang diễn ra ở cùng thời điểm; **độ trễ (latency)** là thời gian mỗi request chờ đến khi hoàn thành. Đây là ba số khác nhau.

Một instance còn chịu giới hạn bên ngoài: số kết nối tối đa mà database cho phép, tải của các instance khác, số connection tối đa của API downstream, CPU core, bộ nhớ, lock và network. Nút thắt thay đổi khi tải tăng.

## 5. Định luật Little: ước tính nhu cầu, không chọn “số đẹp”

Ở hệ thống tương đối ổn định, định luật Little viết:

\[
L = \lambda W
\]

Trong đó `L` là số công việc trung bình **đang ở trong phạm vi đo**, `λ` là thông lượng trung bình (công việc/giây), và `W` là thời gian trung bình một công việc tồn tại trong phạm vi đó (giây).

Cần nhất quán về **phạm vi**:

- Nếu đo tất cả request đang trong ứng dụng: `L_request ≈ RPS × response_time`, tính cả thời gian chờ.
- Nếu đo riêng các connection JDBC **đang được mượn**: `L_db_lease ≈ số lượt mượn connection/giây × thời gian mượn trung bình`. Không cộng thời gian chờ **trước** khi mượn vào thời gian giữ connection.
- Nếu mỗi request mượn connection nhiều lần, số lượt mượn/giây **khác** số request/giây.

**Ví dụ tính nhẩm:** hệ thống hoàn thành ổn định 60 request/giây; mỗi request dùng một lần JDBC trong trung bình 100 ms (=0,1 giây). Nhu cầu connection **đang được mượn trung bình** khoảng:

\[
60\ \text{request/s} \times 0{,}1\ \text{s/request} = 6\ \text{connection}
\]

Pool ba connection không thể duy trì **cùng** nhịp 60 lượt mượn/giây nếu mỗi lượt thực sự giữ connection trung bình 0,1 giây và không có yếu tố khác làm thay đổi phép tính. Nhưng chọn pool chỉ dựa vào trung bình sáu vẫn có thể thiếu khi tải theo đợt, thời gian truy vấn dao động hoặc database bị khóa. Đồng thời, tăng số pool phải có giới hạn theo năng lực database và tổng các instance.

Giả sử response time trung bình là 300 ms khi xử lý đồng bộ kiểu servlet: số request ở trong hệ thống trung bình gần `60 × 0,3 = 18`. Con số 18 **không đồng nhất** với “cần chính xác 18 worker thread” trong mọi kiến trúc: hàng đợi, bất đồng bộ, keep-alive và cách xử lý I/O đều tác động đến số thread thực sự bận.

Không diễn giải công thức thành lời hứa về p95/p99 hay số slot tối ưu. Little mô tả **giá trị trung bình ở trạng thái ổn định**; quá tải kéo dài làm hàng đợi phình lên, thời gian đợi tăng và các phép tính tại một khoảng đo ngắn có thể gây hiểu lầm.

## 6. Thí nghiệm Spring Boot 3.x / Java 17+: hai pool với kích thước khác nhau

Tạo một dự án Maven bằng Spring Initializr với **Java 17 trở lên**, **Spring Boot 3.x**, dependencies:

- **Spring Web** (`spring-boot-starter-web`): Spring MVC và embedded Tomcat.
- **JDBC API** (`spring-boot-starter-jdbc`): JDBC và HikariCP mặc định trong cấu hình thông dụng.
- **H2 Database** (`com.h2database:h2`): database trong bộ nhớ cho bài thực hành.

Giữ dependency/version được Spring Initializr quản lý. Ví dụ này là ứng dụng độc lập; không cần Spring Data JPA hay dịch vụ database ngoài. Cấu trúc tệp:

~~~text
src/main/java/com/example/poollab/
  PoolLabApplication.java
  PoolLabController.java
src/main/resources/
  application.properties
load-test/
  LoadClient.java
~~~

### 6.1. Cấu hình hai giới hạn khác nhau

**`src/main/resources/application.properties`**

~~~properties
server.port=8080

# Thí nghiệm: tối đa 12 Tomcat worker threads
server.tomcat.threads.max=12
server.tomcat.threads.min-spare=4

# JDBC pool: tối đa 3 connection
spring.datasource.url=jdbc:h2:mem:poollab;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.datasource.hikari.maximum-pool-size=3
spring.datasource.hikari.connection-timeout=2000
~~~

`server.tomcat.threads.max` áp dụng cho Tomcat worker threads thông thường; cấu hình này **không phải** kích thước Hikari pool. `spring.datasource.hikari.maximum-pool-size` giới hạn tổng connection JDBC **idle + active** của pool. `connection-timeout=2000` đặt thời gian chờ mượn connection tối đa là 2.000 ms; khi hết hạn Hikari có thể ném `SQLException`. Không nhầm thuộc tính này với timeout thực thi SQL hay timeout HTTP.

Các con số nhỏ dùng **để dễ quan sát nghẽn trong thí nghiệm**, không phải cấu hình sản xuất được khuyến nghị. Cấu hình Tomcat này cũng không có cùng tác dụng khi ứng dụng dùng virtual threads.

### 6.2. Lớp khởi động ứng dụng

**`src/main/java/com/example/poollab/PoolLabApplication.java`**

~~~java
package com.example.poollab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PoolLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(PoolLabApplication.class, args);
    }
}
~~~

### 6.3. Hai endpoint có thời gian ngủ giống nhau nhưng giữ tài nguyên khác nhau

**`src/main/java/com/example/poollab/PoolLabController.java`**

~~~java
package com.example.poollab;

import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

import com.zaxxer.hikari.HikariDataSource;
import com.zaxxer.hikari.HikariPoolMXBean;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/lab")
public class PoolLabController {
    private final HikariDataSource dataSource;

    public PoolLabController(HikariDataSource dataSource) {
        this.dataSource = dataSource;
    }

    // Giữ một servlet worker khoảng 400 ms,
    // nhưng KHÔNG mượn connection JDBC.
    @GetMapping("/no-db")
    public String noDb() throws InterruptedException {
        Thread.sleep(400);
        return "no-db";
    }

    // Mượn connection, chạy SQL rồi CỐ Ý GIỮ
    // connection thêm 400 ms để mô phỏng công đoạn DB chậm.
    @GetMapping("/db")
    public String withDb() throws SQLException, InterruptedException {
        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement =
                     connection.prepareStatement("SELECT 1");
             ResultSet result = statement.executeQuery()) {
            result.next();
            int value = result.getInt(1);
            Thread.sleep(400);
            return "db=" + value;
        }
    }

    // Đọc trạng thái pool; gọi /lab/db ít nhất một lần
    // trước khi đọc để Hikari khởi tạo pool.
    @GetMapping("/pool")
    public PoolState pool() {
        HikariPoolMXBean bean = dataSource.getHikariPoolMXBean();
        if (bean == null) {
            return new PoolState(0, 0, 0, 0);
        }
        return new PoolState(
                bean.getActiveConnections(),
                bean.getIdleConnections(),
                bean.getTotalConnections(),
                bean.getThreadsAwaitingConnection()
        );
    }

    public record PoolState(
            int active, int idle, int total, int waiting
    ) {}
}
~~~

Hai endpoint đều dùng `Thread.sleep(400)` và do đó **giữ worker thread** trong thời gian ngủ. Điểm khác biệt là:

- `GET /lab/no-db`: không mượn JDBC connection; nút thắt trong thí nghiệm chủ yếu là worker thread và chi phí khác.
- `GET /lab/db`: mượn connection trước khi ngủ, nên tối đa ba request có thể giữ connection cùng lúc; các request khác nếu vào đoạn `getConnection()` sẽ đợi.
- `GET /lab/pool`: quan sát số `active` (đang mượn), `idle` (rảnh), `total` và `waiting` (thread đang chờ mượn). Các con số là **ảnh chụp tức thời**, có thể đổi ngay sau response; sau khi tải ngừng, `active` thường về 0.

**Cảnh báo quan trọng cho thực hành:** cố tình ngủ khi đang giữ connection là thao tác **chỉ để mô phỏng**. Trong ứng dụng thật, cần giữ connection và transaction ngắn nhất hợp lý, tránh gọi API mạng, sleep hoặc xử lý CPU kéo dài khi transaction vẫn giữ connection. `try-with-resources` đảm bảo trả tài nguyên về pool khi đi hết khối, kể cả khi có ngoại lệ.

Chạy từ thư mục dự án Maven:

~~~bash
./mvnw spring-boot:run
~~~

Trên Windows PowerShell:

~~~powershell
.\mvnw.cmd spring-boot:run
~~~

Kiểm tra một request (trong terminal khác):

~~~bash
curl -s http://localhost:8080/lab/db
curl -s http://localhost:8080/lab/no-db
curl -s http://localhost:8080/lab/pool
~~~

Hai response đầu lần lượt có body **chính xác**:

~~~text
db=1
no-db
~~~

Response `/lab/pool` là JSON gồm `active`, `idle`, `total`, `waiting`. Giá trị cụ thể thay đổi theo thời điểm gọi; không nên chép một bộ số làm kết quả cố định.

### 6.4. Tạo chín request đồng thời bằng Java 17

Đặt chương trình **độc lập** sau tại `load-test/LoadClient.java`:

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;

public class LoadClient {
    public static void main(String[] args) {
        String endpoint = args.length == 0 ? "db" : args[0];
        if (!endpoint.equals("db") && !endpoint.equals("no-db")) {
            System.err.println("Chon endpoint: db hoac no-db");
            return;
        }

        HttpClient client = HttpClient.newHttpClient();
        URI uri = URI.create("http://localhost:8080/lab/" + endpoint);
        List<CompletableFuture<String>> pending = new ArrayList<>();

        long batchStart = System.nanoTime();
        for (int index = 1; index <= 9; index++) {
            final int requestNumber = index;
            long start = System.nanoTime();
            HttpRequest request = HttpRequest.newBuilder(uri)
                    .timeout(Duration.ofSeconds(10))
                    .GET()
                    .build();

            pending.add(client.sendAsync(
                    request, HttpResponse.BodyHandlers.ofString()
            ).handle((response, error) -> {
                long ms = TimeUnit.NANOSECONDS.toMillis(
                        System.nanoTime() - start
                );
                if (error != null) {
                    return requestNumber + ": ERROR "
                            + error.getClass().getSimpleName()
                            + " (" + ms + " ms)";
                }
                return requestNumber + ": HTTP "
                        + response.statusCode()
                        + " " + response.body()
                        + " (" + ms + " ms)";
            }));
        }

        CompletableFuture.allOf(
                pending.toArray(new CompletableFuture[0])
        ).join();

        for (CompletableFuture<String> result : pending) {
            System.out.println(result.join());
        }
        long totalMs = TimeUnit.NANOSECONDS.toMillis(
                System.nanoTime() - batchStart
        );
        System.out.println("Total: " + totalMs + " ms");
    }
}
~~~

Đây là chương trình Java chuẩn, **không phụ thuộc Spring**. Nó khởi tạo chín request HTTP bất đồng bộ, thu status và thời gian từng request, rồi đợi đủ chín request. Chạy trong thư mục `load-test`:

~~~bash
javac LoadClient.java
java LoadClient no-db
java LoadClient db
~~~

Để phép thử dễ so sánh, gọi cả hai endpoint một lần trước khi đo nhằm giảm ảnh hưởng khởi tạo lazy; chạy nhiều lượt và quan sát giá trị trung vị/p95 nếu muốn đo nghiêm túc.

**Kết quả dự đoán theo cơ chế**, không phải stdout thời gian cố định:

- Với `no-db`, chín request có thể cùng ngủ trên các worker sẵn có và hoàn thành gần một lượt 400 ms, cộng chi phí HTTP/khởi động thread.
- Với `db`, chỉ ba request giữ connection JDBC cùng lúc. Nếu chín request vào đủ nhanh và mỗi lượt giữ connection 400 ms, chúng có xu hướng tạo **ba đợt**, tổng thời gian gần khoảng `3 × 400 ms = 1.200 ms` cộng overhead.
- Nếu tăng số request, thời gian giữ connection hoặc áp tải thêm các nguồn khác, request có thể chờ vượt `connectionTimeout`. Khi đó code sẽ nhận `SQLException`; HTTP status phụ thuộc cách ứng dụng xử lý exception (mặc định có thể thành 500), **không tự động là 429 hay 503**.

Thời gian trong kết quả thực tế không quyết định “Spring lỗi” hay “DB lỗi” nếu thiếu số đo queue và resource. OS scheduler, H2, socket, thời gian khởi tạo connection, JIT, garbage collector và năng lực máy chạy đều làm số đo thay đổi.

## 7. Hàng đợi và hiệu ứng nghẽn dây chuyền

Có thể có **nhiều chỗ chờ**:

1. Trước khi request lấy được worker thread hoặc được ứng dụng xử lý, tùy connector, giới hạn socket, backlog, proxy và load balancer.
2. Trong ứng dụng khi worker đồng bộ chờ `getConnection()`.
3. Tại database khi nhiều truy vấn cạnh tranh CPU, I/O, lock hoặc tài nguyên khác.
4. Khi gọi downstream HTTP service hay đọc/ghi dữ liệu mạng.

Khi tốc độ request đến cao hơn tốc độ hoàn thành trong thời gian dài, hàng đợi tăng. Độ trễ p95/p99 thường xấu đi trước khi phần lớn request lỗi. Timeout ở tầng client có thể xảy ra **trước** `connectionTimeout` hoặc trước khi server xử lý xong, tạo ra retry và tăng tải thêm.

Ví dụ vòng khuếch đại:

~~~text
DB chậm -> giữ connection lâu
       -> Hikari active chạm giới hạn, pending tăng
       -> servlet workers chờ getConnection()
       -> request mới bị chậm ở tầng HTTP
       -> client timeout / retry
       -> thêm request -> nghẽn nặng hơn
~~~

Với workload hỗn hợp, một endpoint truy vấn DB chậm có thể làm các endpoint khác bị chậm do cạnh tranh **chung HTTP workers**, ngay cả khi endpoint khác không cần truy vấn DB. Đây là lý do cần giới hạn tải, quản lý timeout và có thể tách tài nguyên/workload khi cần.

Không dùng **tổng số connection đang mở** làm đại diện trực tiếp cho throughput: connection idle vẫn tính vào `total`; truy vấn chậm có thể khiến `active` cao nhưng số query hoàn thành thấp.

## 8. Đọc metric để xác định đúng nút thắt

Trong dự án thật, nên bật **Spring Boot Actuator** và hệ thống metrics/trace phù hợp; kiểm tra tên meter/tags khả dụng ở đúng phiên bản và môi trường. Các tín hiệu thường hữu ích:

| Tín hiệu | Điều muốn biết | Diễn giải cần thận trọng |
| --- | --- | --- |
| Tomcat busy/current threads | Bao nhiêu worker đang bận so với hiện có/giới hạn | Busy cao kéo dài kèm latency cao gợi ý nghẽn hoặc blocking trong worker |
| Hikari active connections | Bao nhiêu JDBC connection được mượn | Active gần max liên tục chỉ là dấu hiệu; cần xem pending và thời gian giữ |
| Hikari idle connections | Còn slot kết nối sẵn có không | Idle=0 không tự chứng minh lỗi nếu pending=0 và throughput tốt |
| Hikari pending / awaiting connections | Có bao nhiêu thread đang chờ mượn | Pending tăng kèm thời gian acquire cao là bằng chứng mạnh cho cạnh tranh pool |
| Connection acquisition time / timeout | Việc lấy connection đang mất bao lâu | Đừng nhầm acquire wait với thời gian thực thi SQL |
| SQL/transaction duration, DB CPU/I-O/locks | Database có xử lý kịp, có khóa không | Tăng pool khi DB đã bão hòa thường làm tình hình xấu đi |
| HTTP RPS, status, p50/p95/p99 | Người dùng thấy thời gian đáp ứng và lỗi gì | Cần chia theo endpoint và loại request, tránh chỉ nhìn trung bình |

Tùy cấu hình Micrometer/Actuator, có thể thấy tên như `hikaricp.connections.active`, `hikaricp.connections.pending`, `tomcat.threads.busy` và `http.server.requests`; việc metric Tomcat xuất hiện còn phụ thuộc instrumentation/MBean. **Không giả định** mọi meter đều có nếu chưa kiểm tra môi trường.

Ở bài lab, `/lab/pool` cung cấp ảnh chụp để minh họa mối quan hệ giữa `active` và `waiting`. Trong production, nên thu metrics định kỳ qua hệ thống giám sát để không phải cố chụp đúng một khoảnh khắc.

## 9. Các tình huống chẩn đoán và hướng xử lý

| Triệu chứng quan sát | Giả thuyết cần kiểm chứng | Hướng xử lý |
| --- | --- | --- |
| Hikari `active≈maximumPoolSize`, `pending>0`, thời gian mượn tăng | Connection pool là điểm chờ trực tiếp | Tối ưu query/transaction, trả connection sớm, xem giới hạn DB, rồi mới cân nhắc tăng pool |
| Tomcat worker bận gần tối đa, Hikari còn idle | Tốn thời gian ở code/CPU, mạng, khóa khác hoặc blocking ngoài JDBC | Profile stack/trace, phân biệt CPU và blocking, kiểm tra pool outbound và timeout |
| Hikari active cao, DB CPU/locks cũng cao | DB không hoàn thành đủ nhanh | Tối ưu chỉ mục/truy vấn, lock và transaction; hạn chế concurrency, scale DB có kiểm chứng |
| Nhiều timeout nhưng CPU app thấp | Có thể đang chờ tài nguyên I/O/pool/downstream | Đo waiting, latency theo công đoạn; đừng kết luận “cần thêm CPU” |
| Tăng pool mà throughput không tăng, p99 xấu hơn | Đã chuyển nút thắt sang DB hoặc gây tranh chấp | Giảm về cấu hình tốt hơn, đo query/DB saturation, đặt ngưỡng backpressure |
| Chỉ sau khi tăng số instance DB mới quá tải | Tổng JDBC connections của các instance vượt ngân sách DB | Tính tổng pool theo replicas, reserve connection cho admin/maintenance, giới hạn riêng từng instance |

**Quy trình tuning có kiểm soát:**

1. Xác định mục tiêu: RPS, p95/p99, tỷ lệ lỗi, số request đồng thời dự kiến và độ dài spike.
2. Đo baseline của từng công đoạn: thời gian chờ mượn JDBC, thời gian giữ connection, thời gian SQL, thread busy, DB utilization và lỗi timeout.
3. Xác định nút thắt **thực**. Trước hết sửa query chậm, connection leak, transaction giữ connection lâu hoặc gọi downstream trong transaction.
4. Điều chỉnh **một giới hạn liên quan** với tăng nhỏ có lý do; đo cùng workload và cùng số instance. Dừng nếu throughput không cải thiện, p99 xấu đi, DB bão hòa hoặc lỗi tăng.
5. Phối hợp timeout và hạn chế tải: HTTP/client deadline, JDBC acquire timeout, query timeout, giới hạn số tác vụ xuống DB; tránh retry đồng loạt không backoff.
6. Kiểm tra tổng connection budget: nếu có bốn replica, mỗi replica `maximumPoolSize=20` thì ứng dụng **có thể** mở tới 80 JDBC connection, chưa tính các dịch vụ khác. Database phải có dư địa kết nối và năng lực xử lý tương ứng.

**Không** suy diễn rằng `Tomcat maxThreads = Hikari maximumPoolSize` là quy tắc vàng. Một ứng dụng có nhiều request dùng cache hoặc không truy cập DB có thể cần worker nhiều hơn pool DB; ứng dụng có transaction rất ngắn có thể luân chuyển connection nhanh. Ngược lại, một connection pool lớn nhưng database chậm vẫn là cấu hình kém.

## 10. Async, virtual threads và WebFlux có giải quyết được vấn đề không?

**Spring MVC đồng bộ (blocking):** trong luồng thực thi controller thông thường, mỗi request đang thực thi chiếm một servlet worker. Đoạn gọi JDBC chặn luồng cho tới khi trả kết quả hoặc timeout. Bài lab sử dụng mô hình này.

**Spring MVC async:** với `Callable`/`DeferredResult` và cơ chế servlet async, servlet worker ban đầu có thể được nhả trong lúc chờ kết quả; `Callable` có thể chạy trên executor khác. Việc chuyển công việc blocking sang một executor khác **không làm JDBC tự thành non-blocking**. Vẫn phải giới hạn executor, DB connections và lượng công việc chờ. Chuyển chỗ giữ thread đôi khi chỉ chuyển nút thắt sang pool khác.

**Virtual threads (Java 21+):** phù hợp với nhiều tác vụ blocking I/O; chúng có thể giảm chi phí giữ **platform thread** cho mỗi request so với mô hình truyền thống. Nhưng chúng không tạo thêm connection DB hay làm query nhanh hơn. Khi dùng virtual threads, một số thuộc tính giới hạn worker pool truyền thống như `server.tomcat.threads.max` có thể không còn tác dụng; vẫn phải đặt giới hạn số truy vấn/connection, quan sát pinning và đo hiệu năng thực tế.

**Spring WebFlux:** sử dụng event loop và I/O không chặn khi toàn bộ chuỗi xử lý thực sự non-blocking. Reactor Netty có nhóm event-loop threads và có thể có HTTP connection pool riêng. Nếu gọi **JDBC blocking** ngay trên event loop, bạn có thể chặn khả năng xử lý nhiều kết nối; việc chuyển blocking code sang scheduler phù hợp có thể giúp bảo vệ event loop nhưng vẫn **không bỏ qua** giới hạn JDBC pool. Với R2DBC, quản lý kết nối và semantics khác JDBC; đừng dùng thuộc tính Hikari để cấu hình R2DBC pool.

Do đó, lựa chọn async, virtual threads hay reactive là **lựa chọn mô hình thực thi**, không thay thế cho kiểm soát concurrency ở database và downstream.

## 11. Lỗi phổ biến khi suy luận về khả năng xử lý đồng thời

1. **“200 threads nghĩa là 200 query song song.”** Sai: mỗi request có thể không truy vấn DB; số JDBC connection mượn bị giới hạn độc lập và DB có thể xử lý ít hơn.
2. **“Hikari max 10 nghĩa là chỉ có 10 user online.”** Sai: user/session, request đang thực thi và connection JDBC đang mượn không cùng khái niệm.
3. **“Tăng maxThreads đến 1.000 sẽ xử lý nhanh hơn.”** Không nhất thiết: có thể tạo thêm luồng chờ, tăng context switching, bộ nhớ và thời gian đợi tài nguyên.
4. **“Tăng connection pool luôn tăng RPS.”** Không đúng khi DB bị giới hạn CPU/I/O/lock hoặc khi nhiều app replica tranh cùng DB.
5. **“Gọi close() là đóng mất kết nối nên chậm.”** Với connection do Hikari cấp, `close()` thông thường trả connection về pool để tái sử dụng và là việc cần làm.
6. **“Mỗi socket keep-alive chiếm một Tomcat request worker mãi mãi.”** Sai với mô hình connector non-blocking thông dụng; socket rảnh và request đang thực thi không đồng nhất.
7. **“Async/WebFlux/virtual thread xóa mọi hàng đợi.”** Không: tài nguyên downstream, timeout, công suất database và backpressure vẫn quan trọng.
8. **“Chỉ nhìn CPU app đủ biết nguyên nhân.”** Sai: ứng dụng có thể rảnh CPU vì đang đợi DB/network/lock trong hàng trăm thread.
9. **“Một lần load test có số ms đẹp là đủ.”** Sai: cần warm-up, kiểm soát workload, quan sát nhiều percentile và kiểm tra errors để tránh tối ưu dựa vào nhiễu.

## 12. Bài tập tự kiểm tra

**Câu 1.** Tomcat có 20 worker thread; Hikari pool có 5 connection. Có 20 request đồng bộ đều đang gọi `getConnection()`, năm request đã mượn thành công. Mười lăm request còn lại đang dùng tài nguyên gì?

**Câu 2.** Tại sao `Hikari active=5` và `pending=12` cùng p99 tăng có thể làm cả endpoint không dùng DB chậm theo?

**Câu 3.** Một dịch vụ hoàn thành ổn định 100 request/s; mỗi request mượn connection đúng một lần và giữ trung bình 40 ms. Theo Little, trung bình có bao nhiêu connection đang được mượn? Vì sao con số đó chưa đủ để chốt `maximumPoolSize`?

**Câu 4.** Một ứng dụng có ba replica, mỗi replica cấu hình `maximumPoolSize=30`. Chỉ riêng các replica này có thể sử dụng tối đa khoảng bao nhiêu connection JDBC đồng thời? Khi DB bắt đầu quá tải sau khi scale, nên đo gì?

**Câu 5.** Vì sao chuyển một controller dùng JDBC blocking sang `Callable` hoặc virtual threads vẫn không khiến mười connection xử lý được 100 query đồng thời?

**Đáp án gợi ý:**

1. Mười lăm request chưa mượn connection; trong đoạn chờ blocking thông thường, chúng vẫn giữ worker thread, chờ Hikari cấp slot hoặc timeout.
2. Nhiều worker bị chặn khi đợi DB, cạnh tranh worker với endpoint khác; cần kiểm chứng bằng busy threads, thời gian chờ pool và trace.
3. `100 × 0,04 = 4` connection **trung bình**. Phải xét burst, phương sai thời gian giữ, năng lực DB, các pool/replica khác và mục tiêu p99.
4. `3 × 30 = 90` connection theo ngân sách cấu hình, ngoài các dịch vụ khác; đo active/pending, DB connection count, CPU/I/O, lock, độ trễ SQL và RPS thực.
5. Các mô hình đó có thể giảm chi phí sử dụng worker/platform thread hoặc chuyển nơi xử lý, nhưng pool vẫn chỉ cấp tối đa mười JDBC connection cùng lúc.

## 13. Tài liệu tham khảo

- Spring Boot 3.3 — Common Application Properties (Tomcat, Hikari, R2DBC): https://docs.spring.io/spring-boot/3.3/appendix/application-properties/
- Spring Boot — Data Access / SQL (connection pool và JDBC): https://docs.spring.io/spring-boot/docs/3.2.1/reference/htmlsingle/index.html
- HikariCP — cấu hình `maximumPoolSize`, `connectionTimeout`: https://github.com/brettwooldridge/HikariCP
- Spring Framework — Asynchronous Requests (Spring MVC): https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-async.html
- Java 17 — HttpClient: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html
