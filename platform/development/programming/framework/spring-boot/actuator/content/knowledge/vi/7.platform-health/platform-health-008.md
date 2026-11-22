# Nhận diện health indicator tự cấu hình cho cơ sở dữ liệu, Redis, ổ đĩa và dịch vụ liên quan

## 1. Một kết quả health được tạo ra từ đâu?

Một ứng dụng khởi động thành công chưa chắc đã sử dụng được cơ sở dữ liệu, kết nối được Redis hoặc còn đủ dung lượng để ghi tệp. Trong Spring Boot Actuator, bộ kiểm tra sức khỏe (health indicator) thực hiện một phép kiểm tra có phạm vi xác định và trả về trạng thái như `UP` hoặc `DOWN`. Nhờ đó, người vận hành có thêm bằng chứng về những tài nguyên ứng dụng đang phụ thuộc.

Ví dụ, một ứng dụng quản lý đơn hàng có thể cần ba câu trả lời khác nhau:

- `db`: ứng dụng có lấy và kiểm tra được kết nối JDBC tới cơ sở dữ liệu không?
- `redis`: ứng dụng có thực hiện được phép kiểm tra Redis bằng cấu hình kết nối đang dùng không?
- `diskSpace`: hệ thống tệp tại đường dẫn được chọn có còn đủ dung lượng khả dụng không?

Mỗi câu trả lời chỉ có ý nghĩa trong giới hạn của phép kiểm tra đó. `db=UP` không chứng minh mọi bảng và truy vấn nghiệp vụ đều đúng; `redis=UP` không chứng minh toàn bộ dữ liệu đệm là chính xác; `diskSpace=UP` không chứng minh mọi thư mục đều ghi được.

Bài này dùng Spring Boot **3.3.x**, với ví dụ độc lập ghim **3.3.0**, chạy bằng **JDK 21**. Mục tiêu là biết indicator nào có thể được tạo tự động, vì sao nó có hoặc không có, và cách đọc kết quả. Thiết kế indicator tùy biến và chính sách probe cho hệ điều phối là những phạm vi riêng.

### Các thuật ngữ cần nối với nhau

| Thuật ngữ | Vai trò |
| --- | --- |
| `HealthIndicator` | Thực hiện một phép kiểm tra và trả về `Health`. |
| `HealthContributor` | Thành phần tham gia vào cây health; có thể là một indicator hoặc một thành phần tổng hợp. |
| `CompositeHealthContributor` | Gom nhiều thành phần con, chẳng hạn nhiều `DataSource` dưới nhánh `db`. |
| `HealthContributorRegistry` | Nơi tra cứu các thành phần đã đăng ký theo tên. |
| Health endpoint | Đọc cây health và công bố kết quả; đường dẫn HTTP mặc định là `/actuator/health`. |

Hãy hình dung theo thứ tự: **tài nguyên đã được cấu hình → thành phần kiểm tra được đăng ký → phép kiểm tra chạy → trạng thái được tổng hợp → thông tin được phép hiển thị**. Thiếu một mắt xích sẽ tạo ra triệu chứng khác nhau.

## 2. “Tự cấu hình” là có điều kiện

Actuator không quét mạng để tự tìm MySQL, Redis hay máy chủ thư. Nó dựa vào các lớp có trên classpath, các bean đã tồn tại và cấu hình của ứng dụng.

Đối với một tài nguyên bên ngoài, có thể lần theo bốn lớp điều kiện:

1. **Thư viện:** ứng dụng có thư viện tích hợp phù hợp, thường được đưa vào qua một starter.
2. **Bean tài nguyên:** Spring đã tạo được bean như `DataSource`, `RedisConnectionFactory` hoặc bean tương ứng.
3. **Điều kiện health:** indicator được bật và cấu hình tự động chưa phải nhường chỗ cho bean do ứng dụng cung cấp.
4. **Quan sát:** health endpoint được công bố, yêu cầu được phép truy cập và chính sách hiển thị cho phép thấy thành phần hoặc chi tiết.

Lớp thứ tư quyết định điều người dùng nhìn thấy qua HTTP; nó không thay thế ba lớp tạo indicator. Chỉ thêm dòng `management.health.redis.enabled=true` sẽ không tự tạo Redis client khi thiếu thư viện hoặc bean kết nối.

Ví dụ từ cấu hình JDBC của Spring Boot 3.3: `DataSourceHealthContributorAutoConfiguration` đòi hỏi các lớp JDBC liên quan, một bean `DataSource` và điều kiện bật health có khóa `db`. Phương thức tạo contributor còn kiểm tra sự vắng mặt của các bean tên `dbHealthIndicator` và `dbHealthContributor`. Vì vậy, không thể kết luận “đã thêm Actuator thì chắc chắn có `db`”. Xem [mã cấu hình tự động JDBC của Spring Boot 3.3](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.13/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/jdbc/DataSourceHealthContributorAutoConfiguration.java).

### Ba trạng thái dễ bị đánh đồng

| Quan sát | Có thể kết luận gì? | Bằng chứng cần tìm tiếp |
| --- | --- | --- |
| Không thấy `db` trong JSON | Chưa đủ để nói cơ sở dữ liệu hỏng hoặc indicator chưa tồn tại. | Chính sách hiển thị, nhóm health đang gọi, registry, báo cáo điều kiện. |
| Có `db` và trạng thái `DOWN` | Contributor tồn tại; phép kiểm tra không đạt. | Lỗi kết nối, xác thực, pool, truy vấn kiểm tra và log liên quan. |
| Ứng dụng không khởi động được | Chưa có endpoint đang phục vụ để hỏi health. | Lỗi tạo bean, driver, cấu hình tài nguyên hoặc lỗi khởi động khác. |

## 3. Bản đồ nhận diện nhanh

Bảng dưới đây chọn các trường hợp thường gặp. Các bean là đầu mối để kiểm tra, không phải danh sách đầy đủ mọi annotation điều kiện của từng cấu hình.

| Tài nguyên | Khóa cấu hình health | Tên thành phần thường thấy | Dấu hiệu tài nguyên đã được tích hợp |
| --- | --- | --- | --- |
| Cơ sở dữ liệu qua JDBC | `db` | `db` | Có `DataSource` và hạ tầng Spring JDBC phù hợp. |
| Redis | `redis` | `redis` | Có `RedisConnectionFactory` hoặc `ReactiveRedisConnectionFactory`. |
| Dung lượng ổ đĩa | `diskspace` | `diskSpace` | Không cần dịch vụ mạng; dùng đường dẫn trên hệ thống tệp của tiến trình. |
| Kiểm tra đơn giản luôn thành công | `ping` | `ping` | `PingHealthIndicator` không kiểm tra máy chủ bên ngoài. |
| MongoDB | `mongo` | `mongo` | Có hạ tầng Mongo tương ứng, chẳng hạn `MongoTemplate` hoặc biến thể reactive. |
| RabbitMQ | `rabbit` | `rabbit` | Có hạ tầng Spring AMQP, chẳng hạn `RabbitTemplate`. |
| Máy chủ thư | `mail` | `mail` | Có `JavaMailSenderImpl` phù hợp. |
| Elasticsearch | `elasticsearch` | `elasticsearch` | Có client tương thích mà Actuator hỗ trợ. |
| JMS | `jms` | `jms` | Có `jakarta.jms.ConnectionFactory`. |
| LDAP | `ldap` | `ldap` | Có hạ tầng Spring LDAP phù hợp, chẳng hạn `LdapOperations`. |

Spring Boot còn có các tích hợp như Cassandra, Couchbase, Neo4j, Hazelcast và InfluxDB. Không cần thêm chúng chỉ để làm cây health dài hơn: chỉ những tài nguyên ứng dụng thực sự sử dụng mới có ý nghĩa vận hành. Danh sách phụ thuộc phiên bản; tra [danh mục indicator của Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.health.auto-configured-health-indicators) khi làm việc với một tích hợp cụ thể.

**Chú ý cách viết:** khóa thuộc tính là `management.health.diskspace.enabled`, còn tên thành phần mặc định và đoạn đường dẫn là `diskSpace`, ví dụ `/actuator/health/diskSpace`. Đừng lấy cách viết của tên thành phần để suy ra một khóa cấu hình bất kỳ.

## 4. JDBC: nhánh `db` kiểm tra được điều gì?

### Điều kiện xuất hiện

Một ứng dụng thường có `DataSource` khi đã có driver, hạ tầng JDBC và cấu hình kết nối hợp lệ. JPA cũng có thể sử dụng `DataSource`, nên ứng dụng JPA có thể có nhánh `db` mà không cần tự viết indicator.

Điểm quan trọng là bean tài nguyên thực tế. Chỉ có một chuỗi URL trong cấu hình chưa đảm bảo đã tạo được `DataSource`; ngược lại, một `DataSource` do ứng dụng tự khai báo vẫn có thể được cấu hình health nhận diện nếu đủ các điều kiện khác.

### Phép kiểm tra và giới hạn

`DataSourceHealthIndicator` làm việc thông qua `DataSource` của ứng dụng. Trong nhánh Spring Boot 3.3 được đối chiếu ở đây, nó lấy tên sản phẩm cơ sở dữ liệu và kiểm tra kết nối bằng truy vấn xác thực được cung cấp, hoặc bằng `Connection.isValid(...)` khi không có truy vấn đó. Cấu hình tự động có thể lấy truy vấn từ thông tin của pool. Không nên ghi nhớ rằng mọi hệ quản trị đều chạy đúng một câu `SELECT 1`. Xem [cơ chế của DataSourceHealthIndicator](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.13/spring-boot-project/spring-boot-actuator/src/main/java/org/springframework/boot/actuate/jdbc/DataSourceHealthIndicator.java).

Khi nhận `UP`, ta có bằng chứng rằng phép kiểm tra kết nối vừa thực hiện đạt yêu cầu. Ta chưa có bằng chứng rằng migration đã tạo đủ bảng, tài khoản có mọi quyền nghiệp vụ, giao dịch dài sẽ không deadlock hoặc truy vấn báo cáo sẽ chạy nhanh.

Một tình huống điển hình: kết nối hợp lệ nhưng bảng `orders` chưa được tạo. Nhánh `db` vẫn có thể `UP`, còn API đọc đơn hàng thất bại vì không tìm thấy bảng. Hai kết quả không mâu thuẫn vì chúng kiểm tra hai việc khác nhau.

### Nhiều nguồn dữ liệu

Nếu có nhiều bean `DataSource`, nhánh `db` có thể chứa nhiều thành phần con thay vì một indicator phẳng. Tên con giúp xác định nguồn nào gặp sự cố. Ví dụ cấu trúc minh họa, không phải kết quả cố định của mọi ứng dụng:

```json
{
  "status": "DOWN",
  "components": {
    "db": {
      "status": "DOWN",
      "components": {
        "ordersDataSource": { "status": "UP" },
        "reportingDataSource": { "status": "DOWN" }
      }
    }
  }
}
```

Đừng sửa thông tin kết nối của `ordersDataSource` chỉ vì trạng thái tổng của `db` là `DOWN`. Trước hết phải đọc thành phần con thất bại. Với nguồn dữ liệu định tuyến, còn cần xem các nguồn đích và cấu hình `management.health.db.ignore-routing-data-sources`; không được mặc định coi nhánh tổng là một kết nối duy nhất.

### Vì sao ứng dụng đang chạy mà `db` vẫn có thể `DOWN`?

Sau khi khởi động, cơ sở dữ liệu có thể mất mạng, tài khoản bị thu hồi quyền hoặc pool không còn cấp được kết nối trong thời gian chờ. Health phản ánh phép thử tại thời điểm được gọi, không phải chứng nhận có hiệu lực vĩnh viễn từ lúc khởi động.

Cũng không được giả định mọi lỗi kết nối đều đợi tới lúc gọi health: một cấu hình pool, bước migration hoặc công việc khởi tạo có thể làm ứng dụng thất bại ngay khi khởi động.

## 5. Redis: kiểm tra bằng chính client của ứng dụng

### Nhận diện đường đồng bộ và reactive

Nhánh đồng bộ sử dụng `RedisConnectionFactory`. Nhánh reactive dựa vào `ReactiveRedisConnectionFactory` và Reactor. Cả hai cùng gắn với khóa cấu hình `redis`; đừng suy ra rằng phải có hai thành phần JSON chỉ vì hai kiểu API cùng hiện diện.

Với cấu hình Lettuce thông thường, bean kết nối có thể đáp ứng cả hai kiểu. Trong cấu hình tự động của Spring Boot 3.3, nhánh reactive được xem xét trước; điều kiện bean tên `redisHealthIndicator` hoặc `redisHealthContributor` giúp cấu hình đồng bộ nhường chỗ. Vì vậy, một ứng dụng dùng Spring MVC cũng có thể gặp implementation `RedisReactiveHealthIndicator`; không nên đoán implementation chỉ từ lựa chọn MVC/WebFlux. Có thể đối chiếu [cấu hình Redis đồng bộ](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.0/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/data/redis/RedisHealthContributorAutoConfiguration.java) và [cấu hình Redis reactive](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.13/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/data/redis/RedisReactiveHealthContributorAutoConfiguration.java).

### Không đồng nhất health với lệnh `PING`

Ở mã Spring Boot 3.3.0:

- `RedisHealthIndicator` đồng bộ lấy kết nối rồi đọc `INFO`; nếu là kết nối cluster, nó đọc thông tin cluster.
- `RedisReactiveHealthIndicator` dùng `INFO server` cho trường hợp không phải cluster và đọc thông tin cluster cho trường hợp cluster.

Do đó, chạy `redis-cli PING` nhận `PONG` chưa chứng minh tài khoản ứng dụng được phép chạy lệnh mà indicator cần. Một tài khoản có thể được phép `PING`, `GET`, `SET` nhưng bị ACL chặn `INFO`, khiến health thất bại. Hãy kiểm tra cùng địa chỉ, cổng, TLS, tài khoản và quyền lệnh với client của ứng dụng. Xem [indicator Redis đồng bộ](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.0/spring-boot-project/spring-boot-actuator/src/main/java/org/springframework/boot/actuate/data/redis/RedisHealthIndicator.java) và [indicator Redis reactive](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.0/spring-boot-project/spring-boot-actuator/src/main/java/org/springframework/boot/actuate/data/redis/RedisReactiveHealthIndicator.java).

Một máy chủ Redis có thể đang chạy nhưng ứng dụng không kết nối được do DNS, mạng, chứng chỉ hoặc mật khẩu. Vì thế, health được đọc theo góc nhìn của tiến trình ứng dụng, không phải theo việc người quản trị nhìn thấy tiến trình Redis trên một máy khác.

`redis=UP` cũng chưa kiểm chứng dữ liệu cần đọc có tồn tại, cấu trúc khóa đúng, script Lua chạy được hay nghiệp vụ dùng transaction hoạt động như mong muốn. Với nhiều connection factory, cần đọc từng thành phần con để xác định cấu hình nào thất bại.

### Cấu hình kết nối không phải cấu hình indicator

Đoạn cấu hình dưới đây dành cho Spring Boot 3.3, khi ứng dụng đã có starter Redis và một Redis cục bộ đang chạy:

```properties
spring.data.redis.host=127.0.0.1
spring.data.redis.port=6379
spring.data.redis.connect-timeout=1s
spring.data.redis.timeout=1s
management.health.redis.enabled=true
```

Các khóa `spring.data.redis.*` cấu hình client; khóa `management.health.redis.enabled` điều khiển việc tự cấu hình phép kiểm tra. Giá trị timeout ở đây là lựa chọn cho môi trường học tập, không phải cam kết rằng toàn bộ HTTP health luôn hoàn tất trong đúng một giây.

## 6. Ổ đĩa: nhánh `diskSpace` đo nơi tiến trình đang nhìn thấy

`DiskSpaceHealthIndicator` không cần MySQL hay Redis. Nó đọc dung lượng khả dụng của hệ thống tệp tại một đường dẫn, rồi so sánh với ngưỡng tối thiểu. Với Spring Boot 3.3.0, mặc định đường dẫn là `.` và ngưỡng là `10MB`, tương ứng `10 × 1024 × 1024 = 10.485.760` byte.

Điều kiện trạng thái là:

```text
usableSpace >= threshold  → UP
usableSpace < threshold   → DOWN
```

Đường dẫn `.` được hiểu theo thư mục làm việc của tiến trình. Nó không tự động trỏ vào thư mục chứa mã nguồn, thư mục dữ liệu của cơ sở dữ liệu hoặc mọi ổ đĩa trên máy. Xem [giá trị mặc định của DiskSpaceHealthIndicatorProperties](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.0/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/system/DiskSpaceHealthIndicatorProperties.java) và [phép so sánh trong DiskSpaceHealthIndicator](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.0/spring-boot-project/spring-boot-actuator/src/main/java/org/springframework/boot/actuate/system/DiskSpaceHealthIndicator.java).

Ví dụ cấu hình để kiểm tra một thư mục dữ liệu đã tồn tại:

```properties
management.health.diskspace.path=/var/lib/orders
management.health.diskspace.threshold=500MB
```

Trên Windows, thay đường dẫn bằng một đường dẫn hợp lệ của môi trường đang chạy, chẳng hạn `C:/orders-data`. Thuộc tính này không tạo thư mục. Chọn sai đường dẫn có thể dẫn tới kết quả không phản ánh phân vùng mà ứng dụng cần dùng.

Trong container, phép kiểm tra dùng hệ thống tệp mà container nhìn thấy. Nếu dữ liệu quan trọng nằm trên volume khác với thư mục làm việc, hãy chỉ định đường dẫn trên volume đó. Không được lấy dung lượng ổ đĩa của máy cá nhân để suy ra kết quả bên trong container.

Khi được phép hiển thị chi tiết, có thể thấy các trường `total`, `free`, `threshold`, `path`, `exists`. `free` là dung lượng khả dụng được Java đọc cho đường dẫn đó. Các con số và đường dẫn phụ thuộc máy chạy; chúng không phải output có thể sao chép cố định.

Phép kiểm tra này không thay cho thử ghi tệp, kiểm tra quyền thư mục, độ trễ I/O hoặc tính toàn vẹn dữ liệu. Một hệ thống tệp còn nhiều dung lượng nhưng chỉ đọc vẫn có thể không đáp ứng công việc cần ghi của ứng dụng.

## 7. Thực hành: nhìn thấy indicator được tạo tự động

Ví dụ sau là **một dự án Maven độc lập**, không cần thêm controller. Nó bắt đầu với web và Actuator để quan sát `diskSpace` và `ping`, sau đó mới thêm JDBC hoặc Redis để thấy ảnh hưởng của tài nguyên lên cây health.

### 7.1. Tạo ba tệp

Tệp `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.0</version>
        <relativePath/>
    </parent>
    <groupId>learning</groupId>
    <artifactId>health-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>21</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

Tệp `src/main/java/learning/healthdemo/HealthDemoApplication.java`:

```java
package learning.healthdemo;

import java.util.TreeSet;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.actuate.health.HealthContributorRegistry;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class HealthDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(HealthDemoApplication.class, args);
    }

    @Bean
    ApplicationRunner printHealthContributors(HealthContributorRegistry registry) {
        return args -> {
            var names = new TreeSet<String>();
            registry.forEach(contributor -> names.add(contributor.getName()));
            System.out.println("contributors=" + names);
        };
    }
}
```

`TreeSet` sắp xếp tên để dòng quan sát ổn định. Việc liệt kê tên không gọi `health()` và không chứng minh các tài nguyên đều đang `UP`; nó chỉ cho biết những contributor nào đã được đăng ký.

Tệp `src/main/resources/application.properties`:

```properties
server.address=127.0.0.1
server.port=8080
management.endpoints.web.exposure.include=health
management.endpoint.health.show-components=always
management.endpoint.health.show-details=always
```

`show-details=always` dùng cho ví dụ chạy trên loopback để xem bằng chứng. Khi triển khai, cần chọn chính sách hiển thị và quyền truy cập phù hợp vì chi tiết health có thể lộ đường dẫn, tên sản phẩm và lỗi kết nối.

### 7.2. Chạy và đọc trạng thái ban đầu

Trong thư mục chứa `pom.xml`, kiểm tra Maven đang dùng JDK 21 rồi chạy:

```shell
java -version
mvn -version
mvn spring-boot:run
```

Trên Windows có thể gọi `mvn.cmd`. Đây là ứng dụng Spring Boot nhiều tệp và có thư viện phụ thuộc, vì vậy không biên dịch bằng lệnh `javac HealthDemoApplication.java` đơn lẻ. Maven giải quyết classpath và biên dịch mã Java của dự án.

Với đúng cấu hình mẫu, không chạy trong môi trường Kubernetes và không thêm contributor nào khác, dòng ứng dụng tự in ra là:

```text
contributors=[diskSpace, ping]
```

Các dòng khởi động Spring Boot khác vẫn xuất hiện xung quanh. Mở terminal thứ hai và gọi:

```shell
curl -i http://127.0.0.1:8080/actuator/health
curl -i http://127.0.0.1:8080/actuator/health/ping
```

Trên Windows PowerShell, dùng `curl.exe` nếu `curl` đang là bí danh của lệnh PowerShell. Với đường dẫn `/ping`, mặc định HTTP là `200` và phần thân là:

```json
{"status":"UP"}
```

Ở đường dẫn tổng, tìm nhánh `diskSpace` và `ping`. Nếu dung lượng tại đường dẫn kiểm tra đạt ngưỡng thì cả hai là `UP`. Không mong đợi `db` hoặc `redis`: ví dụ hiện tại chưa tích hợp hai tài nguyên đó. `ping=UP` ở đây cũng không có nghĩa ứng dụng đã ping MySQL, Redis hay một địa chỉ mạng.

### 7.3. Thêm JDBC và H2 để nhận diện `db`

Dừng ứng dụng, bổ sung hai dependency sau **bên trong phần `dependencies` đang có**, giữ nguyên hai dependency ban đầu:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-jdbc</artifactId>
</dependency>
<dependency>
    <groupId>com.h2database</groupId>
    <artifactId>h2</artifactId>
    <scope>runtime</scope>
</dependency>
```

Thêm vào tệp properties:

```properties
spring.datasource.url=jdbc:h2:mem:healthdemo
spring.datasource.username=sa
spring.datasource.password=
```

Chạy lại cùng lệnh Maven. Khi không có thay đổi môi trường hay contributor khác, dòng tên trở thành:

```text
contributors=[db, diskSpace, ping]
```

Sau đó gọi:

```shell
curl -i http://127.0.0.1:8080/actuator/health/db
```

Kết quả mong đợi là trạng thái `UP` khi kết nối H2 hợp lệ; chi tiết nhận diện sản phẩm là H2. Thứ tự khóa JSON không mang ý nghĩa. Phép thử này minh họa rằng **có hạ tầng JDBC và `DataSource` thì có thêm `db`**, không phải Actuator tự tạo một cơ sở dữ liệu nghiệp vụ cho ứng dụng.

### 7.4. Tùy chọn thêm Redis

Chỉ thực hiện bước này khi có một Redis phục vụ môi trường học tập. Dừng ứng dụng, thêm dependency sau vào phần `dependencies`:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-redis</artifactId>
</dependency>
```

Thêm cấu hình Redis ở mục 5, khởi động lại rồi gọi `/actuator/health/redis`. Nếu client được tạo và contributor được đăng ký, nhánh `redis` xuất hiện; trạng thái phụ thuộc kết nối và phép kiểm tra thực tế. Đừng chép một số phiên bản Redis cố định vào output mong đợi vì máy học của mỗi người có thể khác nhau.

Nếu Redis không truy cập được nhưng ứng dụng vẫn khởi động, nhánh có thể trả `DOWN`. Nếu chính giai đoạn khởi tạo đã thất bại thì phải giải quyết lỗi khởi động trước; chưa thể dùng HTTP health của tiến trình đó.

## 8. Bật/tắt indicator khác với ẩn thông tin

Ba lựa chọn sau giải quyết ba vấn đề khác nhau:

| Cấu hình | Ý nghĩa |
| --- | --- |
| `management.health.redis.enabled=false` | Ngăn cấu hình tự động tạo contributor Redis thuộc cơ chế này. |
| `management.endpoint.health.show-details=never` | Ẩn chi tiết trong phản hồi; không làm phép kiểm tra biến mất. |
| `management.endpoints.web.exposure.include=health` | Công bố health endpoint qua HTTP; không thêm thư viện hay bean tài nguyên. |

Muốn xem tên các thành phần mà không hiển thị chi tiết, có thể dùng:

```properties
management.endpoint.health.show-components=always
management.endpoint.health.show-details=never
```

Khi đó vẫn có thể thấy `db` hoặc `redis` cùng trạng thái, nhưng không nhận toàn bộ trường chi tiết. Không suy ra tài nguyên khỏe chỉ vì lỗi chi tiết đã bị ẩn.

Có thể tắt mặc định rồi chọn bật một số indicator do cấu hình tự động quản lý:

```properties
management.health.defaults.enabled=false
management.health.diskspace.enabled=true
management.health.ping.enabled=true
```

Lựa chọn này không phải công tắc xóa mọi bean health do ứng dụng tự khai báo. Tương tự, đặt `management.health.db.enabled=false` không xóa `DataSource`, không ngắt nhu cầu dùng cơ sở dữ liệu và không sửa kết nối bị lỗi; nó thay đổi điều kiện tham gia kiểm tra tự động. Tra tên khóa tại [các thuộc tính Actuator của Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/).

## 9. Quy trình chẩn đoán theo bằng chứng

### Khi không thấy một indicator mong đợi

1. Xác nhận đang gọi đúng tiến trình, cổng, context path và đường dẫn management. Ví dụ chỉ dùng `/actuator` mặc định; dự án thật có thể đã đổi.
2. Kiểm tra chính sách `show-components` và `show-details`, quyền truy cập, và có đang gọi một nhóm health đã lọc thành phần hay không.
3. Kiểm tra thư viện ở runtime, bean tài nguyên và profile/cấu hình đang có hiệu lực. Có file cấu hình trong mã nguồn chưa đủ chứng minh tiến trình đã nạp nó.
4. Kiểm tra `management.health.<key>.enabled`, giá trị mặc định chung, cấu hình loại trừ auto-configuration và bean tùy biến có thể thay thế thành phần mặc định.
5. Chạy ứng dụng với báo cáo điều kiện để xem điều kiện nào khớp hoặc không khớp. Với dự án Maven mẫu có thể dùng:

```shell
mvn spring-boot:run -Dspring-boot.run.arguments=--debug
```

Tìm các lớp như `DataSourceHealthContributorAutoConfiguration`, `RedisHealthContributorAutoConfiguration`, `RedisReactiveHealthContributorAutoConfiguration` và `DiskSpaceHealthContributorAutoConfiguration`. Báo cáo điều kiện giúp giải thích **vì sao bean được hoặc không được tạo**; nó không thay cho kết quả health khi tài nguyên được kiểm tra.

### Khi indicator tồn tại nhưng trả `DOWN`

| Thành phần | Bằng chứng ưu tiên | Kết luận không nên vội đưa ra |
| --- | --- | --- |
| `db` | Thành phần con, lỗi lấy kết nối, xác thực, pool, driver và truy vấn kiểm tra. | “Toàn bộ cơ sở dữ liệu đã chết.” |
| `redis` | Client đang dùng, DNS/TLS, tài khoản, ACL với `INFO` hoặc lệnh cluster, timeout. | “PING thành công nên Actuator chắc chắn sai.” |
| `diskSpace` | `path`, `exists`, `free`, `threshold`, volume nhìn từ tiến trình. | “Ổ đĩa trên máy chủ còn trống nên nhánh này không thể DOWN.” |
| `mail`, `rabbit` hoặc dịch vụ khác | Đúng client, endpoint, quyền và thao tác kiểm tra của implementation tương ứng. | “Một phép kiểm tra kết nối đã chứng minh mọi chức năng nghiệp vụ.” |

Khi HTTP trả `503`, vẫn cần đọc JSON để biết nhánh nào thất bại; khi HTTP trả `401`, `403` hoặc `404`, trước hết kiểm tra truy cập và định tuyến thay vì coi đó là bằng chứng cơ sở dữ liệu hỏng. Với cấu hình ánh xạ mặc định, `DOWN` và `OUT_OF_SERVICE` của health được trả qua HTTP `503`. Nếu ứng dụng đã tùy chỉnh ánh xạ hoặc cách tổng hợp, phải đọc cấu hình thật.

Không có một thuộc tính timeout chung bảo đảm mọi indicator dừng đúng hạn. Thời gian chờ còn phụ thuộc client, pool, thao tác kiểm tra và môi trường mạng. Ngưỡng ghi cảnh báo indicator chậm là cơ chế quan sát; không được nhầm nó với cơ chế hủy thao tác đang chạy.

## 10. Tự kiểm tra khả năng đọc cây health

**Tình huống 1:** `/actuator/health` chỉ trả `{"status":"UP"}`. Có thể khẳng định ứng dụng không có Redis indicator không?

Không. Trước hết phải kiểm tra chính sách hiển thị và contributor đã đăng ký. Phản hồi tổng đã ẩn thành phần không cho biết danh sách phép kiểm tra.

**Tình huống 2:** `db=UP` nhưng API thất bại vì thiếu bảng `orders`. Indicator có sai không?

Chưa có bằng chứng indicator sai. Kiểm tra kết nối JDBC không kiểm tra sự tồn tại và tính đúng của toàn bộ schema nghiệp vụ.

**Tình huống 3:** `redis-cli PING` thành công nhưng nhánh `redis` báo lỗi quyền với `INFO`. Nên kiểm tra gì?

Xác nhận CLI và ứng dụng có dùng cùng cấu hình hay không, rồi đối chiếu quyền lệnh mà implementation health thực sự gọi. Thành công của `PING` không cấp thêm quyền cho `INFO`.

**Tình huống 4:** ứng dụng ghi dữ liệu trên một volume riêng, nhưng `diskSpace.path=.` kiểm tra phân vùng khác. Kết quả `UP` có đủ để bảo đảm nơi ghi dữ liệu còn dung lượng không?

Không. Phải chọn đường dẫn phản ánh hệ thống tệp cần quan sát; kiểm tra dung lượng vẫn chưa thay thế kiểm tra quyền ghi và hành vi I/O.

Sau các tình huống này, hãy tự chỉ ra được ba thông tin cho mỗi thành phần trong ứng dụng: **bean tài nguyên nào làm nó xuất hiện, thao tác nào tạo ra trạng thái, và điều gì nằm ngoài phạm vi chứng minh của thao tác đó**.
