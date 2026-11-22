# Chuẩn bị dịch vụ phụ trợ cho kiểm thử tích hợp

Kiểm thử tích hợp (integration test) xác minh nhiều thành phần hoạt động đúng khi giao tiếp với nhau. Một ứng dụng có thể chạy tốt trong unit test nhưng vẫn thất bại khi kết nối cơ sở dữ liệu, cache, message broker, object storage hoặc API của dịch vụ khác. Vì vậy, môi trường kiểm thử cần cung cấp các dịch vụ phụ trợ có phiên bản, cấu hình, dữ liệu và vòng đời được kiểm soát.

Trong CI/CD, chuẩn bị dịch vụ phụ trợ không chỉ là khởi động một container. Pipeline phải bảo đảm dịch vụ đã sẵn sàng nhận yêu cầu, ứng dụng kết nối đúng địa chỉ, dữ liệu kiểm thử không xung đột, lỗi được ghi nhận đủ để điều tra và tài nguyên được dọn dẹp sau mỗi lần chạy. Đây là một phần của năng lực **DEVOPS_CI_CD_FUNDAMENTALS**: thiết kế môi trường thực thi có thể tái lập để build và kiểm thử tự động cung cấp bằng chứng đáng tin cậy trước khi phát hành.

## 1. Dịch vụ phụ trợ trong kiểm thử tích hợp là gì?

Dịch vụ phụ trợ (supporting service hoặc dependency) là hệ thống mà thành phần đang kiểm thử cần giao tiếp để hoàn thành một luồng nghiệp vụ. Tùy ứng dụng, chúng có thể gồm:

| Nhóm dịch vụ | Ví dụ | Điều cần kiểm chứng |
| --- | --- | --- |
| Cơ sở dữ liệu quan hệ | PostgreSQL, MySQL, SQL Server | Kết nối, SQL, transaction, constraint, migration và kiểu dữ liệu |
| Cơ sở dữ liệu NoSQL | MongoDB, Cassandra | Giao thức, schema/document, index và truy vấn |
| Cache và key-value store | Redis | Đọc/ghi, TTL, serialization, eviction và hành vi khi cache mất kết nối |
| Message broker | RabbitMQ, Kafka | Publish/consume, routing, acknowledgement, retry và thứ tự xử lý |
| Object storage | S3-compatible storage, MinIO | Upload/download, quyền truy cập, metadata và xử lý lỗi |
| Dịch vụ tìm kiếm | Elasticsearch, OpenSearch | Mapping, indexing, truy vấn và eventual consistency |
| API bên ngoài | Dịch vụ thanh toán, vận chuyển, định danh | Hợp đồng HTTP, timeout, xác thực, retry và phản hồi lỗi |
| Dịch vụ hỗ trợ | SMTP server, fake OAuth/OIDC provider | Gửi email, callback, token và luồng xác thực |

Không phải mọi integration test đều cần khởi động toàn bộ hệ sinh thái. Hãy chọn đúng dịch vụ cần thiết cho hành vi đang xác minh. Ví dụ, test repository cần cơ sở dữ liệu thật tương thích với production; test xử lý timeout của API thanh toán có thể dùng HTTP stub có khả năng mô phỏng độ trễ và lỗi. Test luồng publish/consume nên dùng broker thật hoặc môi trường tương thích để kiểm tra giao thức và semantics quan trọng.

Phân biệt rõ ba loại kiểm thử:

- **Unit test:** cô lập một đơn vị nhỏ, thường thay dependency bằng mock hoặc fake.
- **Integration test:** kiểm tra tương tác giữa các thành phần, thường cần một hoặc nhiều dịch vụ thật hoặc tương thích.
- **End-to-end test:** xác minh luồng xuyên suốt qua nhiều lớp, có thể cần môi trường gần production hơn và tốn thời gian hơn.

Một mock có thể hữu ích để ép một API trả lỗi cụ thể, nhưng không chứng minh ứng dụng tương thích với database engine, broker hoặc giao thức thật. Chọn mức độ thật của dịch vụ dựa trên rủi ro cần kiểm chứng.

## 2. Lập danh sách dependency trước khi tạo môi trường

Trước khi viết pipeline, lập bản đồ những dịch vụ mà test cần. Với mỗi dependency, ghi rõ:

- Dịch vụ và phiên bản cần dùng.
- Giao thức, cổng, hostname hoặc network alias.
- Cách xác thực và các quyền cần thiết.
- Cấu hình bắt buộc, chẳng hạn database name, topic, bucket hoặc virtual host.
- Điều kiện readiness: khi nào dịch vụ thực sự nhận được thao tác nghiệp vụ.
- Cách tạo dữ liệu ban đầu, migration và reset dữ liệu.
- Giới hạn tài nguyên và thời gian khởi động.
- Cách thu log, trạng thái và dọn dẹp.

Ví dụ, một ứng dụng đặt hàng có thể cần PostgreSQL để lưu đơn hàng, Redis để cache tồn kho, RabbitMQ để phát sự kiện và một HTTP stub để giả lập dịch vụ vận chuyển. Hãy xác định test nào cần cả bốn dịch vụ và test nào chỉ cần một phần. Việc chia test theo nhóm giúp pipeline không phải khởi động broker nặng cho một kiểm tra đơn giản chỉ đọc database.

Một bảng dependency ngắn có thể dùng làm hợp đồng giữa người viết test và người quản lý pipeline:

| Thành phần kiểm thử | Dịch vụ cần có | Cấu hình đầu vào | Điều kiện sẵn sàng |
| --- | --- | --- | --- |
| Order repository | PostgreSQL | URL, user, password, database | Kết nối thành công và migration hoàn tất |
| Inventory cache | Redis | Host, port, namespace | Ping thành công, thao tác set/get hoạt động |
| Event publisher | RabbitMQ | Host, port, user, virtual host, exchange | Broker sẵn sàng và exchange được khai báo |
| Shipping adapter | HTTP stub | Base URL, API key giả lập | Health endpoint trả trạng thái sẵn sàng |

Đưa cấu hình không nhạy cảm vào file cấu hình kiểm thử có phiên bản. Mật khẩu, token và chứng thư riêng phải được cấp qua secret store hoặc cơ chế bảo mật của nền tảng CI.

## 3. Chọn cách cung cấp dịch vụ phụ trợ

Có nhiều cách chuẩn bị dịch vụ cho integration test. Không có một lựa chọn phù hợp với mọi nhóm; hãy cân nhắc mức độ tương đồng production, thời gian khởi động, khả năng cô lập, yêu cầu Docker và chi phí vận hành.

### 3.1. Service container do nền tảng CI quản lý

Một số nền tảng CI cho phép khai báo container phụ trợ ngay trong pipeline. Bộ máy CI hoặc runner khởi động container, kết nối nó với job và dọn dẹp theo vòng đời của job.

Ưu điểm:

- Khai báo dịch vụ ngay cạnh pipeline, dễ xem và review.
- Có thể gắn service với một job cụ thể.
- Dễ tạo database, cache hoặc broker tạm thời cho mỗi lần chạy.
- Giảm nhu cầu quản lý một máy kiểm thử dùng chung.

Hạn chế:

- Cách phân giải hostname và ánh xạ port phụ thuộc nền tảng, executor và kiểu job.
- Không phải nền tảng nào cũng hỗ trợ cùng loại service hoặc cùng tùy chọn health check.
- Cấu hình nhiều container, volume, network hoặc bootstrap phức tạp có thể khó biểu diễn trực tiếp.

### 3.2. Docker Compose

Docker Compose phù hợp khi môi trường cần nhiều container có quan hệ với nhau: ứng dụng, database, broker, cache, stub API và công cụ quan sát. Một file Compose có thể mô tả image, network, port, volume, environment, health check và phụ thuộc.

Ưu điểm là nhóm có thể dùng cùng cấu hình ở máy cá nhân và CI. Hạn chế là runner cần Docker Engine hoặc runtime tương thích; pipeline phải quản lý việc chờ dịch vụ, thu log và dọn tài nguyên.

Ví dụ file Compose tối giản:

~~~yaml
services:
  postgres:
    image: postgres:16
    environment:
      POSTGRES_DB: orders_test
      POSTGRES_USER: test_user
      POSTGRES_PASSWORD: test_password
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U test_user -d orders_test"]
      interval: 5s
      timeout: 3s
      retries: 20

  redis:
    image: redis:7
    ports:
      - "6379:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 20
~~~

Đây là cấu hình minh họa. Trong môi trường thực, hãy pin phiên bản image theo chính sách của nhóm; với yêu cầu truy vết nghiêm ngặt, pin digest thay vì chỉ dùng tag có thể thay đổi. Không dùng mật khẩu minh họa cho môi trường chia sẻ hoặc production.

Compose có thể biểu diễn thứ tự phụ thuộc và điều kiện health:

~~~yaml
services:
  api:
    build: .
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
~~~

depends_on với service_healthy giúp chờ health check của dependency đạt trước khi khởi động service phụ thuộc, trong các phiên bản Compose hỗ trợ cú pháp này. Tuy nhiên, health check chỉ phản ánh điều kiện đã khai báo; nó không bảo đảm toàn bộ luồng nghiệp vụ đã sẵn sàng. Ứng dụng và test vẫn nên có retry có giới hạn khi kết nối.

### 3.3. Testcontainers

Testcontainers là thư viện cho phép test code tự khởi động và dừng container dependency theo vòng đời test. Cách này hữu ích cho dự án Java dùng JUnit: test có thể khai báo PostgreSQL, Redis, Kafka hoặc container khác ngay trong mã kiểm thử.

Ưu điểm:

- Môi trường kiểm thử được khai báo gần test cần dùng.
- Có thể tạo container riêng theo class hoặc suite.
- Dễ chạy cùng một kiểu test ở máy phát triển và CI nếu môi trường có Docker API phù hợp.
- Có thể dùng phiên bản dịch vụ gần production hơn database in-memory.

Hạn chế:

- Runner phải cung cấp Docker daemon/socket hoặc runtime tương thích.
- Container startup làm tăng thời gian test.
- Cần quản lý phiên bản image và khả năng tương thích của Docker environment.
- Chạy nhiều test song song cần kiểm soát tài nguyên và dữ liệu.

Ví dụ JUnit 5 với PostgreSQL:

~~~java
import org.junit.jupiter.api.Test;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import java.sql.DriverManager;

import static org.junit.jupiter.api.Assertions.assertTrue;

@Testcontainers
class OrderRepositoryIT {

    @Container
    static final PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16")
            .withDatabaseName("orders_test")
            .withUsername("test_user")
            .withPassword("test_password");

    @Test
    void databaseStartsAndAcceptsConnections() throws Exception {
        try (var connection = DriverManager.getConnection(
                postgres.getJdbcUrl(),
                postgres.getUsername(),
                postgres.getPassword())) {
            assertTrue(connection.isValid(2));
        }
    }
}
~~~

Ví dụ minh họa vòng đời container và kiểm tra kết nối; trong dự án thật, nên cấu hình DataSource từ JDBC URL, username và password mà Testcontainers cung cấp, chạy migration, rồi kiểm tra repository hoặc luồng nghiệp vụ. Các dependency Testcontainers cần có phiên bản tương thích với JUnit và Java của dự án. Không hardcode cổng host vì Testcontainers có thể ánh xạ sang cổng ngẫu nhiên.

### 3.4. Môi trường dùng chung được quản lý riêng

Một nhóm có thể dùng database hoặc broker chạy ở môi trường test dùng chung. Cách này có thể giảm thời gian khởi động nhưng tăng rủi ro:

- Test của nhóm khác có thể làm thay đổi dữ liệu hoặc cấu hình.
- Một lần chạy có thể ảnh hưởng kết quả của lần chạy khác.
- Môi trường có thể bị thay đổi ngoài pipeline, làm kết quả khó tái lập.
- Secret và quyền truy cập phải được quản lý chặt hơn.

Nếu buộc phải dùng môi trường chia sẻ, tạo database/schema/topic/bucket hoặc namespace riêng cho từng pipeline, dùng tài khoản quyền tối thiểu, có quy tắc reset và theo dõi người sử dụng. Không để test tự động ghi vào dữ liệu staging hoặc production đang phục vụ người dùng.

## 4. Khởi động dịch vụ chưa có nghĩa là dịch vụ đã sẵn sàng

Đây là nguyên nhân phổ biến khiến integration test chập chờn. Container có thể ở trạng thái running nhưng ứng dụng bên trong vẫn đang khởi tạo:

- Database đang phục hồi WAL, chạy migration hoặc tạo user.
- Broker đang bầu chọn leader, tạo topic hoặc khôi phục log.
- Redis đã mở cổng nhưng chưa tải xong dữ liệu hoặc cấu hình.
- HTTP service đã bind port nhưng chưa kết nối được dependency.

Cần phân biệt các mức trạng thái:

1. **Process started:** tiến trình đã được khởi chạy.
2. **Container running:** runtime báo container đang chạy.
3. **Port reachable:** TCP connection đến cổng thành công.
4. **Service ready:** giao thức hoặc health endpoint báo dịch vụ có thể nhận yêu cầu.
5. **Application ready:** thao tác nghiệp vụ mà test cần đã thực hiện được, chẳng hạn query database hoặc publish/consume message.

Chỉ chờ container running hoặc port mở thường chưa đủ.

### 4.1. Dùng health check có ý nghĩa

Health check nên kiểm tra điều kiện gần với cách ứng dụng sử dụng dịch vụ:

| Dịch vụ | Kiểm tra yếu | Kiểm tra tốt hơn |
| --- | --- | --- |
| PostgreSQL | TCP port 5432 mở | pg_isready với đúng database/user |
| Redis | TCP port 6379 mở | redis-cli ping trả PONG |
| RabbitMQ | Cổng AMQP mở | Broker báo ready và ứng dụng có thể kết nối |
| HTTP stub | Tiến trình đang chạy | Health endpoint trả HTTP status mong đợi |
| Kafka | Port broker mở | Metadata request thành công, topic cần dùng có sẵn |

Health check không nên thực hiện thao tác phá hủy dữ liệu hoặc tiêu thụ thông điệp nghiệp vụ. Hãy giữ nó nhanh, lặp lại được và có timeout.

### 4.2. Retry có giới hạn và backoff

Ngay cả khi health check đạt, ứng dụng vẫn có thể gặp một khoảng thời gian ngắn lỗi kết nối. Dùng retry có giới hạn, delay tăng dần và timeout tổng thể:

~~~bash
#!/usr/bin/env bash
set -euo pipefail

attempt=1
max_attempts=20

until pg_isready -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME"; do
  if (( attempt >= max_attempts )); then
    echo "Database chưa sẵn sàng sau $max_attempts lần thử" >&2
    exit 1
  fi

  delay=$((attempt < 5 ? attempt : 5))
  echo "Database chưa sẵn sàng; thử lại sau ${delay}s (lần $attempt)"
  sleep "$delay"
  attempt=$((attempt + 1))
done

echo "Database đã sẵn sàng"
~~~

Đoạn script dùng Bash và công cụ pg_isready có trong môi trường chạy. Trong thực tế, giới hạn tổng thời gian phải phù hợp với thời gian khởi động bình thường của dịch vụ. Nếu vượt timeout, hãy làm pipeline thất bại kèm log; không retry vô hạn vì sẽ chiếm runner và che giấu lỗi cấu hình.

Nếu dịch vụ có startup lâu, hãy xem log để phân biệt khởi động chậm với lỗi thật như sai cấu hình, thiếu RAM, port bị chiếm hoặc image không tương thích.

## 5. Thiết lập mạng và địa chỉ kết nối đúng

Container có thể chạy nhưng test vẫn không kết nối được vì hostname và port khác nhau tùy topology:

- Test chạy trực tiếp trên runner host thường kết nối qua host address và port đã publish/mapped.
- Test chạy bên trong job container có thể kết nối bằng service alias hoặc container name trên network chung.
- Container này không thể mặc định dùng localhost để truy cập container khác. localhost luôn chỉ máy/network namespace của tiến trình hiện tại.
- Port trong container và port trên host có thể khác nhau.

Ví dụ, Compose tạo service tên postgres và api cùng network mặc định. Từ container api, hostname thường là postgres và port là cổng nội bộ 5432. Từ tiến trình chạy trên host, test có thể dùng localhost và cổng host đã publish, chẳng hạn 5432.

Vì vậy, cấu hình kết nối nên được truyền từ pipeline hoặc test framework thay vì hardcode localhost:

~~~text
DB_HOST=<hostname hoặc service alias>
DB_PORT=<port có thể truy cập từ tiến trình test>
DB_NAME=orders_test
DB_USER=test_user
DB_PASSWORD=<credential kiểm thử>
~~~

Với Testcontainers, lấy host và mapped port từ container API. Không giả định cổng host cố định. Với GitHub Actions service container, khi job chạy trực tiếp trên runner host, cổng service thường cần được publish/map để truy cập qua localhost; khi job chạy trong container, có thể dùng label của service làm hostname trên network do Actions tạo. Với GitLab CI, service thường được truy cập qua hostname alias trong network job; chi tiết phụ thuộc executor và runner configuration.

Khi không kết nối được, kiểm tra theo thứ tự: container có chạy không, health check đạt chưa, hostname có phân giải được không, port nào được publish, test chạy trên host hay container, firewall/network policy có chặn không và credential có đúng không. Không giải quyết lỗi mạng bằng cách mở tất cả port ra bên ngoài.

## 6. Quản lý phiên bản và cấu hình của dịch vụ

Kết quả test chỉ đáng tin khi biết chính xác dịch vụ nào đã được sử dụng. Pin phiên bản database, broker, cache và image của stub API theo chính sách dự án. Tránh dùng tag di động như latest trong pipeline quan trọng vì cùng một commit có thể chạy trên image khác nhau vào những ngày khác nhau.

Hãy quản lý đồng bộ:

- Phiên bản image và digest khi cần tính bất biến.
- Phiên bản extension, plugin hoặc feature flag của dịch vụ.
- Cấu hình database, collation, timezone và encoding.
- Cấu hình broker như topic, partition, retention và acknowledgement.
- Cấu hình cache như eviction policy và TTL.
- Phiên bản schema hoặc hợp đồng API của dịch vụ giả lập.

Không nhất thiết phải giống hoàn toàn production, nhưng khác biệt phải có chủ đích. Ví dụ, dùng PostgreSQL thật cùng major version với production thường cung cấp bằng chứng tốt hơn H2 nếu ứng dụng phụ thuộc vào cú pháp SQL, kiểu dữ liệu hoặc behavior riêng của PostgreSQL.

Đưa cấu hình kiểm thử vào repository để reviewer nhìn thấy thay đổi. Tách thông tin không nhạy cảm khỏi secret. Credential kiểm thử nên có phạm vi nhỏ, thời hạn ngắn nếu có thể và không được tái sử dụng cho môi trường production.

## 7. Tạo và cô lập dữ liệu kiểm thử

Một dịch vụ đã sẵn sàng vẫn có thể tạo kết quả không ổn định nếu dữ liệu đầu vào thay đổi giữa các lần chạy. Mỗi integration test cần biết dữ liệu nào được tạo, dữ liệu nào được đọc và cách dọn dẹp.

### 7.1. Chọn phạm vi cô lập phù hợp

Một số chiến lược thường dùng:

- **Database riêng cho mỗi job:** dễ reset toàn bộ, phù hợp khi tạo database nhanh.
- **Schema riêng cho mỗi job hoặc test suite:** giảm chi phí tạo instance nhưng cần đảm bảo migration và search path đúng.
- **Namespace riêng:** dùng prefix cho Redis key, topic, bucket hoặc object.
- **Transaction rollback:** phù hợp với test có thể chạy trong cùng transaction; không đủ cho tác vụ bất đồng bộ, nhiều connection hoặc hệ thống đã commit ngoài transaction.
- **Dữ liệu fixture có định danh duy nhất:** tạo dữ liệu theo run ID/UUID và xóa theo namespace sau khi test.

Chọn chiến lược phù hợp với semantics của dịch vụ. Không phải mọi hệ thống đều hỗ trợ rollback hoặc reset nhanh. Với message broker, cần tránh dùng chung topic và consumer group giữa các job song song nếu chúng có thể đọc thông điệp của nhau.

### 7.2. Dùng dữ liệu xác định và tránh phụ thuộc thứ tự

Test nên tự tạo dữ liệu cần thiết và không dựa vào trạng thái còn sót từ lần chạy trước. Dữ liệu fixture cần đủ nhỏ để dễ hiểu, nhưng bao gồm cả trường hợp hợp lệ, không hợp lệ, ranh giới và lỗi.

Ví dụ:

1. Tạo một customer có ID riêng cho test.
2. Tạo order liên kết với customer đó.
3. Gọi API hoặc repository cần kiểm chứng.
4. Xác minh dữ liệu được lưu và sự kiện được phát.
5. Xóa dữ liệu theo ID hoặc hủy môi trường test.

Tránh hardcode ID dễ va chạm như 1 hoặc 100 trong database dùng chung. Dùng UUID, prefix chứa pipeline/job ID hoặc database riêng. Không dùng dữ liệu cá nhân thật; fixture nên là dữ liệu tổng hợp và không chứa thông tin nhạy cảm.

### 7.3. Xử lý test chạy song song

Khi CI chạy nhiều job hoặc nhiều test cùng lúc, cần bảo vệ khỏi xung đột:

- Mỗi job có database/schema/namespace riêng.
- Port host được runtime cấp tự động nếu có thể.
- Topic, queue, bucket và object key có tên duy nhất.
- Không dùng một tài khoản test chung có trạng thái thay đổi giữa các job.
- Chỉ dùng lock khi tài nguyên thật sự không thể cô lập.
- Giới hạn concurrency nếu dịch vụ có giới hạn connection hoặc CPU/RAM.

Một test chạy ổn khi chạy đơn lẻ nhưng thất bại ngẫu nhiên khi chạy song song thường là dấu hiệu của shared state, tên tài nguyên trùng hoặc phụ thuộc thứ tự.

## 8. Chạy migration và bootstrap theo trình tự

Database cần được chuẩn bị theo một trình tự rõ ràng:

1. Khởi động database và chờ readiness.
2. Tạo database/schema và tài khoản với quyền phù hợp.
3. Chạy migration bằng đúng công cụ và phiên bản của ứng dụng.
4. Nạp fixture hoặc dữ liệu tham chiếu cần thiết.
5. Khởi động ứng dụng hoặc test.
6. Xác minh hành vi và thu thập log.

Không nên để mỗi test tự tạo schema theo cách khác nhau. Hãy dùng cùng migration code mà ứng dụng sử dụng trong triển khai để kiểm chứng migration thật. Nếu test chỉ dùng schema viết tay, nó có thể bỏ sót lỗi migration trong pipeline.

Với broker, bootstrap có thể cần tạo exchange, queue, topic hoặc permission trước khi test. Với object storage, cần tạo bucket và policy. Với stub API, cần nạp expectation hoặc scenario. Các bước bootstrap nên idempotent nếu có thể: chạy lại không tạo trạng thái trùng hoặc làm hỏng môi trường.

Không chạy migration phá hủy trên dịch vụ dùng chung. Nếu migration cần kiểm thử nâng cấp, tạo một database tạm từ fixture phiên bản cũ hoặc snapshot đã được kiểm soát, rồi thực hiện nâng cấp trong phạm vi riêng.

## 9. Ví dụ chuẩn bị service trong CI

### 9.1. GitHub Actions với PostgreSQL service container

Ví dụ sau cho thấy một job chạy trực tiếp trên runner host, sử dụng PostgreSQL service và chờ database sẵn sàng trước khi chạy test:

~~~yaml
name: Integration tests

on:
  pull_request:
  push:
    branches:
      - main

jobs:
  integration:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_DB: orders_test
          POSTGRES_USER: test_user
          POSTGRES_PASSWORD: test_password
        ports:
          - 5432:5432
        options: >-
          --health-cmd "pg_isready -U test_user -d orders_test"
          --health-interval 5s
          --health-timeout 3s
          --health-retries 20
    env:
      DB_HOST: localhost
      DB_PORT: 5432
      DB_NAME: orders_test
      DB_USER: test_user
      DB_PASSWORD: test_password
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '21'
      - name: Run integration tests
        run: ./gradlew integrationTest
~~~

Đây là ví dụ minh họa cho runner host và port được publish. Health check trong options giúp GitHub Actions chờ service khỏe trước khi bắt đầu job; test vẫn nên xử lý timeout kết nối trong ứng dụng. Với job chạy bên trong container, cách kết nối thường dùng service label làm hostname và port nội bộ; hãy điều chỉnh theo network topology của job. Mật khẩu trong ví dụ chỉ dành cho môi trường test tạm thời, không dùng cho dịch vụ chia sẻ.

### 9.2. GitLab CI/CD với service

GitLab CI cho phép khai báo service container trong job. Service alias được dùng làm hostname từ môi trường job theo cấu hình runner:

~~~yaml
integration-test:
  image: gradle:8-jdk21
  stage: test
  services:
    - name: postgres:16
      alias: postgres
  variables:
    POSTGRES_DB: orders_test
    POSTGRES_USER: test_user
    POSTGRES_PASSWORD: test_password
    DB_HOST: postgres
    DB_PORT: "5432"
    DB_NAME: orders_test
    DB_USER: test_user
    DB_PASSWORD: test_password
  script:
    - ./gradlew integrationTest
~~~

Khả năng truyền biến vào service và cơ chế health check phụ thuộc phiên bản GitLab Runner, executor và image. Cần xác minh runner có thể kết nối service, service nhận đúng biến khởi tạo và job chờ readiness trước khi test bắt đầu. Nếu runner không cung cấp health check phù hợp, thêm bước chờ có timeout trong script.

### 9.3. Docker Compose trong pipeline

Khi cần nhiều dependency, pipeline có thể khởi động Compose, chạy test, thu log khi thất bại và luôn dọn tài nguyên:

~~~bash
#!/usr/bin/env bash
set -euo pipefail

cleanup() {
  docker compose logs --no-color > compose-test.log || true
  docker compose down --volumes --remove-orphans
}
trap cleanup EXIT

docker compose up --detach --wait
./gradlew integrationTest
~~~

trap EXIT bảo đảm cleanup được gọi khi script kết thúc bình thường hoặc do lỗi. Lệnh lưu log trước khi down giúp giữ bằng chứng điều tra. Trong pipeline thật, cần upload compose-test.log như artifact ngay cả khi job thất bại; việc upload nên được cấu hình bằng cơ chế luôn chạy của nền tảng CI.

Lệnh down --volumes xóa volume của project Compose. Chỉ dùng khi dữ liệu thuộc môi trường tạm của job. Không chạy cleanup này với project hoặc volume dùng chung mà nhóm khác đang cần.

## 10. Thu log, chẩn đoán và dọn dẹp

Khi integration test thất bại, log từ test runner có thể chỉ nói connection refused hoặc timeout. Để xác định nguyên nhân, cần giữ bằng chứng từ cả dịch vụ:

- Trạng thái container/service và health check.
- Log khởi động của database, broker, cache hoặc stub.
- Thông tin network và port mapping.
- Kết quả migration và bootstrap.
- Thời điểm test bắt đầu, thời gian chờ và số lần retry.
- Commit SHA, job ID, image tag/digest và phiên bản công cụ.

Pipeline nên thu thập log khi test thất bại trước khi dừng hoặc xóa service. Tránh ghi credential, token, dữ liệu cá nhân hoặc payload nhạy cảm vào log. Có thể dùng log đã lọc, request ID và metadata để điều tra.

Cleanup là một phần của thiết kế môi trường:

- Dừng container và network do job tạo.
- Xóa volume, database, schema, topic, bucket hoặc namespace tạm.
- Thu hồi credential tạm nếu hệ thống hỗ trợ.
- Giải phóng port, process và file tạm.
- Giữ lại artifact chẩn đoán trong thời hạn cần thiết.

Nếu cleanup thất bại, cần ghi nhận để tránh tài nguyên rò rỉ làm cạn runner hoặc gây xung đột cho lần chạy tiếp theo. Dùng tên project/namespace riêng theo pipeline để có thể xác định tài nguyên thuộc lần chạy nào.

## 11. Các lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Cách điều tra hoặc khắc phục |
| --- | --- | --- |
| Connection refused ngay khi test bắt đầu | Dịch vụ chưa mở port hoặc test dùng sai host | Chờ readiness; kiểm tra network và port mapping |
| Port mở nhưng query thất bại | Process đã bind port nhưng service chưa ready hoặc chưa có database | Dùng health check theo giao thức, kiểm tra log và bootstrap |
| Test chạy local nhưng fail trên CI | Khác image, phiên bản, shell, network hoặc biến môi trường | Pin dependency, ghi rõ cấu hình và tái tạo topology tương đương |
| Test thất bại ngẫu nhiên | Shared data, startup race, concurrency hoặc timeout quá ngắn | Cô lập namespace, retry có giới hạn và kiểm tra thứ tự |
| Migration fail trên CI | Database version/collation khác, migration không idempotent hoặc quyền thiếu | Dùng engine/version phù hợp và chạy migration bằng tài khoản đúng |
| Job không phân giải được hostname service | Test chạy ở network khác hoặc alias không đúng | Xác định tiến trình chạy trên host hay container, sửa hostname |
| Container hết RAM hoặc bị kill | Quá nhiều service hoặc concurrency cao | Giảm số service, giới hạn concurrency, cấp tài nguyên phù hợp |
| Lần chạy sau bị ảnh hưởng bởi lần trước | Cleanup không hoàn tất hoặc dùng volume/database chung | Dùng project riêng và reset tài nguyên tạm |
| Không tìm được nguyên nhân sau khi job kết thúc | Log service đã bị xóa trước khi thu thập | Upload log và trạng thái trước cleanup |

Không tăng timeout vô hạn để xử lý mọi lỗi. Nếu một dịch vụ thường mất 10 giây để sẵn sàng nhưng job chờ 2 giây, tăng timeout có thể hợp lý. Nếu log cho thấy service crash vì thiếu cấu hình, chờ lâu hơn chỉ làm pipeline chậm và khó hiểu hơn.

## 12. Những thực hành nên duy trì

- Dùng dependency thật hoặc tương thích ở những nơi test cần xác minh giao thức, SQL, transaction hay semantics của broker.
- Dùng mock/stub có chủ đích cho các tình huống khó tái tạo như timeout, lỗi mạng, rate limit hoặc phản hồi bên thứ ba.
- Pin phiên bản image và cấu hình dịch vụ; ghi lại phiên bản trong log/artifact kiểm thử.
- Chờ readiness theo giao thức, có retry và timeout tổng thể.
- Cô lập dữ liệu và tài nguyên theo job/test suite; hỗ trợ chạy song song an toàn.
- Dùng migration và bootstrap giống quy trình của ứng dụng.
- Truyền credential qua secret store, giới hạn quyền và dùng dữ liệu tổng hợp.
- Thu log trước khi cleanup và luôn dọn tài nguyên tạm.
- Theo dõi thời gian khởi động, thời gian test, tỷ lệ flaky và nguyên nhân thất bại.
- Giữ cấu hình local và CI gần nhau để giảm khác biệt môi trường.

## 13. Checklist chuẩn bị dịch vụ phụ trợ

**Trước khi chạy test**

- [ ] Đã xác định đủ dependency cho từng nhóm integration test.
- [ ] Phiên bản image và cấu hình dịch vụ được pin, quản lý bằng mã.
- [ ] Hostname, port, network và credential được truyền đúng cho test process.
- [ ] Health check phản ánh readiness cần thiết.
- [ ] Có timeout và retry hữu hạn.
- [ ] Migration, topic, bucket, exchange hoặc fixture được bootstrap đúng trình tự.
- [ ] Dữ liệu và namespace được cô lập giữa các job song song.

**Sau khi chạy test**

- [ ] Kết quả test và phiên bản dịch vụ được lưu để truy vết.
- [ ] Log dịch vụ được thu thập khi thất bại.
- [ ] Container, volume và dữ liệu tạm được dọn dẹp.
- [ ] Secret không xuất hiện trong log hoặc artifact.
- [ ] Thời gian khởi động và lỗi flaky được theo dõi.

## Kết luận

Chuẩn bị dịch vụ phụ trợ là một phần thiết yếu của môi trường kiểm thử tích hợp. Một pipeline đáng tin cậy phải cung cấp đúng dependency, chờ dịch vụ sẵn sàng theo giao thức, thiết lập mạng và credential chính xác, tạo dữ liệu xác định, cô lập các lần chạy và dọn dẹp sau khi hoàn tất. Service container, Docker Compose, Testcontainers hoặc môi trường dùng chung đều có thể phù hợp nếu vòng đời và rủi ro của chúng được kiểm soát.

Khi dịch vụ và dữ liệu kiểm thử được khai báo bằng mã, có phiên bản rõ ràng và có log để truy vết, kết quả integration test sẽ dễ tái lập hơn giữa máy phát triển và CI. Điều đó giúp pipeline phát hiện lỗi tích hợp sớm, giảm test chập chờn và cung cấp bằng chứng tốt hơn trước khi artifact được đưa sang môi trường tiếp theo.
