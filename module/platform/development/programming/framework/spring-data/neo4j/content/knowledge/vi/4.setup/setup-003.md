# Chuẩn bị Neo4j bằng Docker, bản cài cục bộ hoặc Aura

Để phát triển ứng dụng Spring Data Neo4j, trước tiên cần có một Neo4j DBMS đang chạy, một database có thể truy cập, tài khoản hợp lệ và địa chỉ kết nối Bolt. Có ba cách chuẩn bị môi trường thường gặp: chạy Neo4j bằng Docker, cài Neo4j trên máy hoặc dùng Neo4j Aura trên cloud. Cả ba cách đều có thể được Spring Data Neo4j truy cập thông qua Neo4j Java Driver; khác nhau chủ yếu ở cách vận hành, địa chỉ kết nối, bảo mật và việc quản lý dữ liệu.

Bài này hướng dẫn tạo môi trường phục vụ học tập và phát triển, kết nối thử bằng Neo4j Browser hoặc Cypher Shell, rồi cấu hình ứng dụng Spring Boot. Các ví dụ dùng database mặc định **neo4j**. Khi triển khai thực tế, hãy chọn phiên bản Neo4j còn được hỗ trợ và tương thích với phiên bản Spring Boot/Spring Data Neo4j của dự án. Nên khóa phiên bản image hoặc phiên bản cài đặt cụ thể trong môi trường dùng chung để các thành viên không vô tình chạy các bản khác nhau.

## Chọn cách chạy Neo4j

| Cách chạy | Phù hợp khi | Điểm cần chuẩn bị |
|---|---|---|
| Docker | Muốn khởi tạo và xóa môi trường phát triển nhanh, dễ tái tạo | Docker Engine hoặc Docker Desktop, cổng host còn trống, volume lưu dữ liệu |
| Neo4j Desktop hoặc cài Neo4j Server | Muốn quản lý DBMS trực tiếp trên máy, học cách vận hành instance cục bộ | Bộ cài phù hợp hệ điều hành, cấu hình database và mật khẩu |
| Neo4j Aura | Muốn dùng database được quản lý trên cloud, không tự vận hành máy chủ Neo4j | Tài khoản Aura, instance đang hoạt động, URI, username/password và kết nối mạng |

Với người mới học Spring Data Neo4j, Docker là lựa chọn thuận tiện để cả nhóm dùng cùng một cấu hình. Neo4j Desktop phù hợp khi muốn thao tác trực quan với nhiều DBMS cục bộ. Aura hữu ích khi ứng dụng cần kết nối tới một database từ xa hoặc khi nhóm không muốn tự quản lý máy chủ.

Dù chọn cách nào, hãy ghi lại bốn thông tin kết nối: URI, username, password và database name. URI thường dùng giao thức Bolt hoặc giao thức Neo4j có định tuyến. Không nhầm địa chỉ giao diện web của Neo4j Browser với địa chỉ Bolt mà ứng dụng Java sử dụng.

## Chuẩn bị bằng Docker Compose

Docker Compose mô tả database cùng các cổng và volume trong một file cấu hình. Khi cần tạo lại môi trường, nhóm chỉ cần dùng cùng cấu hình và phiên bản image.

Tạo một thư mục làm việc riêng, ví dụ **neo4j-local**, rồi đặt hai file sau trong thư mục đó.

File **.env** chứa mật khẩu dùng riêng cho môi trường local:

~~~dotenv
NEO4J_PASSWORD=ChangeThis_Local_Only_2026
~~~

Đổi giá trị mẫu thành mật khẩu mạnh của bạn. Không commit file **.env** lên Git; thêm file này vào **.gitignore** của dự án hoặc lưu nó ở thư mục cấu hình local bên ngoài repository.

Tạo file **compose.yaml**:

~~~yaml
services:
  neo4j:
    image: neo4j:5-community
    container_name: neo4j-local
    restart: unless-stopped
    environment:
      NEO4J_AUTH: neo4j/${NEO4J_PASSWORD}
    ports:
      - "127.0.0.1:7474:7474"
      - "127.0.0.1:7687:7687"
    volumes:
      - neo4j_data:/data
      - neo4j_logs:/logs

volumes:
  neo4j_data:
  neo4j_logs:
~~~

Ví dụ dùng dòng Neo4j 5 Community để minh họa. Hãy kiểm tra phiên bản tương thích với stack Spring Boot đang dùng; với dự án dài hạn, nên khóa cả tag phiên bản cụ thể thay vì để tag trôi theo thời gian. Hai cổng được bind vào loopback **127.0.0.1**, nên chỉ các tiến trình trên máy host truy cập được qua các cổng này. Volume **neo4j_data** giữ dữ liệu sau khi container dừng hoặc được tạo lại. Volume log giữ log của DBMS.

Khởi động từ thư mục chứa **compose.yaml**:

~~~bash
docker compose up -d
docker compose ps
docker compose logs -f neo4j
~~~

Lệnh đầu tải image nếu máy chưa có và chạy container ở chế độ nền. Lệnh thứ hai cho biết container đã chạy hay chưa; lệnh thứ ba theo dõi log để xem quá trình khởi động hoặc lỗi cấu hình. Chờ DBMS khởi động xong trước khi kết nối từ ứng dụng.

Mở Neo4j Browser tại địa chỉ **http://localhost:7474**. Đăng nhập bằng:

- Username: **neo4j**
- Password: giá trị **NEO4J_PASSWORD** trong file **.env**

Trong Browser, chạy truy vấn đơn giản:

~~~cypher
RETURN 1 AS ready;
~~~

Nếu kết quả trả về **ready = 1**, giao diện Browser đã thực thi được truy vấn trên database.

Có thể kiểm tra từ Cypher Shell bên trong container:

~~~bash
docker compose exec neo4j cypher-shell -u neo4j
~~~

Cypher Shell sẽ yêu cầu mật khẩu. Nhập giá trị **NEO4J_PASSWORD**, sau đó chạy **RETURN 1 AS ready;** và thoát bằng lệnh **:exit**. Cách này giúp phân biệt lỗi đăng nhập hoặc trạng thái DBMS với lỗi cấu hình kết nối của ứng dụng Java.

Các lệnh quản lý thường dùng:

~~~bash
docker compose stop
docker compose start
docker compose restart neo4j
docker compose logs --tail=100 neo4j
docker compose down
~~~

Lệnh **docker compose down** dừng và xóa container, nhưng giữ named volume nên dữ liệu vẫn còn cho lần chạy sau. Chỉ dùng lệnh dưới đây khi chủ động muốn xóa cả dữ liệu local:

~~~bash
docker compose down -v
~~~

Lệnh **down -v** xóa volume do Compose quản lý, bao gồm dữ liệu database trong ví dụ này. Hãy chắc chắn dữ liệu không còn cần thiết trước khi chạy.

Nếu ứng dụng Spring Boot cũng chạy trong một container thuộc cùng Compose network, địa chỉ host của Neo4j là tên service **neo4j** và cổng **7687**, ví dụ **bolt://neo4j:7687**. Trong container, **localhost** trỏ về chính container ứng dụng, không phải container Neo4j. Nếu ứng dụng chạy trực tiếp trên máy host, dùng **bolt://localhost:7687**.

## Cài Neo4j trên máy cục bộ

Có thể chạy Neo4j bằng Neo4j Desktop hoặc cài Neo4j Server theo hệ điều hành. Desktop cung cấp giao diện để tạo DBMS, chọn phiên bản, khởi động database và mở Neo4j Browser. Cài đặt Server phù hợp khi muốn làm quen với cách vận hành DBMS như một dịch vụ hoặc tiến trình độc lập.

### Dùng Neo4j Desktop

1. Tải và cài Neo4j Desktop từ trang phân phối chính thức của Neo4j.
2. Tạo một project để gom các DBMS phục vụ bài học.
3. Tạo DBMS mới, chọn phiên bản Neo4j phù hợp với ứng dụng.
4. Đặt mật khẩu cho người dùng **neo4j** và lưu ở nơi an toàn.
5. Khởi động DBMS, sau đó mở Neo4j Browser từ giao diện Desktop.
6. Chạy **RETURN 1 AS ready;** để xác nhận database phản hồi.

Với DBMS cục bộ, URI Bolt thường là **bolt://localhost:7687**, nếu bạn giữ cổng mặc định và ứng dụng chạy trên cùng máy. Nếu đã đổi cổng hoặc địa chỉ listen, hãy dùng giá trị tương ứng trong cấu hình DBMS.

### Dùng Neo4j Server

Sau khi cài gói Neo4j Server, hãy làm theo hướng dẫn của đúng phiên bản và hệ điều hành. Với cài đặt mới, lệnh đặt mật khẩu ban đầu thường được chạy trước lần khởi động DBMS đầu tiên:

~~~bash
neo4j-admin dbms set-initial-password "YourStrongPassword"
~~~

Sau đó khởi động DBMS bằng cơ chế phù hợp với cách cài đặt. Trên môi trường có script quản lý dịch vụ, có thể dùng lệnh **neo4j start**, **neo4j status** và **neo4j stop** nếu các script đó có trong PATH và được cấu hình cho hệ thống.

Kết nối bằng Cypher Shell:

~~~bash
cypher-shell -a bolt://localhost:7687 -u neo4j
~~~

Nhập mật khẩu khi được yêu cầu rồi chạy:

~~~cypher
RETURN 1 AS ready;
~~~

Lệnh đặt mật khẩu ban đầu không phải cách thay mật khẩu cho một database đã khởi tạo và đang sử dụng. Khi DBMS đã có dữ liệu, hãy đổi mật khẩu bằng quy trình quản trị người dùng được Neo4j hỗ trợ. Cũng cần lưu ý rằng việc đổi biến môi trường khởi tạo của một container không tự động thay mật khẩu đã lưu trong volume dữ liệu hiện có.

Nếu ứng dụng chạy trên máy khác, cần cấu hình địa chỉ listen, cổng, firewall và mã hóa kết nối theo hướng dẫn bảo mật của Neo4j. Không mở Bolt trực tiếp ra Internet khi chưa có xác thực, TLS và chính sách mạng phù hợp.

## Chuẩn bị database trên Neo4j Aura

Neo4j Aura là dịch vụ database đồ thị được quản lý trên cloud. Người dùng tạo instance từ trang quản trị Aura, còn Neo4j vận hành hạ tầng của database. Cách này thuận tiện khi máy phát triển không muốn cài hoặc chạy DBMS local.

Quy trình tổng quát:

1. Đăng nhập hoặc tạo tài khoản Neo4j Aura.
2. Tạo một database instance và chọn loại dịch vụ, khu vực triển khai cùng cấu hình phù hợp nhu cầu.
3. Đợi instance chuyển sang trạng thái sẵn sàng.
4. Lưu username, mật khẩu ban đầu và URI kết nối được trang quản trị cung cấp.
5. Mở Aura Query hoặc Neo4j Browser theo hướng dẫn của instance và chạy **RETURN 1 AS ready;**.
6. Kiểm tra chính sách network access hoặc IP allowlist nếu kết nối từ ứng dụng bị chặn.

URI của Aura thường có dạng **neo4j+s://INSTANCE_ID.databases.neo4j.io**. Hãy sao chép URI thực tế từ trang chi tiết instance, không tự đoán hostname. Tiền tố **neo4j+s** yêu cầu kết nối Bolt có TLS và định tuyến; giữ nguyên scheme do Aura cung cấp. Không thay bằng **bolt://** hoặc tắt xác minh TLS để né lỗi chứng chỉ.

Aura cấp thông tin xác thực riêng cho instance. Hãy lưu mật khẩu trong secret manager hoặc biến môi trường của máy chạy ứng dụng. Không đưa mật khẩu, URI chứa thông tin bí mật hay file credential vào Git, ảnh chụp màn hình hoặc log. Nếu cần chia sẻ database cho thành viên khác, cấp quyền theo cơ chế người dùng và vai trò được hỗ trợ thay vì dùng chung tài khoản quản trị.

## Cấu hình Spring Boot kết nối Neo4j

Spring Data Neo4j sử dụng Neo4j Java Driver để giao tiếp với DBMS. Với Spring Boot, dependency starter giúp cấu hình driver và các thành phần Spring Data tương thích theo dependency management của Spring Boot.

Với Maven, thêm dependency sau vào **pom.xml**:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-neo4j</artifactId>
</dependency>
~~~

Với Gradle:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-neo4j")
}
~~~

Khi dự án dùng Spring Boot dependency management hoặc Spring Boot plugin, không tự ý ghim một phiên bản Neo4j Java Driver riêng nếu không có lý do tương thích rõ ràng. Starter sẽ chọn các phiên bản Spring Data Neo4j và driver được quản lý cùng dòng Spring Boot. Nếu dự án không dùng dependency management của Spring Boot, cần quản lý phiên bản các thành phần Spring Data và driver theo ma trận tương thích của chúng.

Trong **src/main/resources/application.yml**, khai báo cấu hình kết nối:

~~~yaml
spring:
  neo4j:
    uri: ${NEO4J_URI:bolt://localhost:7687}
    authentication:
      username: ${NEO4J_USERNAME:neo4j}
      password: ${NEO4J_PASSWORD}
  data:
    neo4j:
      database: ${NEO4J_DATABASE:neo4j}
~~~

Ý nghĩa các thuộc tính:

| Thuộc tính | Ý nghĩa |
|---|---|
| **spring.neo4j.uri** | URI Bolt hoặc URI Neo4j mà driver dùng để kết nối |
| **spring.neo4j.authentication.username** | Tài khoản đăng nhập Neo4j |
| **spring.neo4j.authentication.password** | Mật khẩu của tài khoản |
| **spring.data.neo4j.database** | Database mà Spring Data Neo4j sử dụng |

Giá trị URI mặc định trong ví dụ là DBMS local được expose ở cổng Bolt mặc định. Password không có giá trị mặc định; ứng dụng cần nhận **NEO4J_PASSWORD** từ môi trường. Khi dùng Aura, thay URI bằng URI **neo4j+s://...** của instance và đặt username/password tương ứng. Khi ứng dụng chạy trong cùng Docker Compose network, đặt URI thành **bolt://neo4j:7687**.

Ví dụ thiết lập biến môi trường trên PowerShell trước khi chạy ứng dụng:

~~~powershell
$env:NEO4J_URI = "bolt://localhost:7687"
$env:NEO4J_USERNAME = "neo4j"
$env:NEO4J_PASSWORD = "your-local-password"
$env:NEO4J_DATABASE = "neo4j"
./mvnw spring-boot:run
~~~

Trên macOS hoặc Linux, có thể export biến môi trường trong terminal:

~~~bash
export NEO4J_URI="bolt://localhost:7687"
export NEO4J_USERNAME="neo4j"
export NEO4J_PASSWORD="your-local-password"
export NEO4J_DATABASE="neo4j"
./mvnw spring-boot:run
~~~

Thay giá trị mật khẩu bằng thông tin thực tế của môi trường đang dùng. Không lưu mật khẩu thật trong file cấu hình được commit. Với môi trường triển khai, dùng secret manager hoặc cơ chế quản lý secret của nền tảng chạy ứng dụng.

Spring Boot thường tự cấu hình Neo4j Driver, Neo4jClient và repository scanning dựa trên cấu hình và package ứng dụng. Chỉ khai báo cấu hình bổ sung như **@EnableNeo4jRepositories** khi cần tùy chỉnh package quét hoặc cấu trúc ứng dụng; không cần thêm annotation này một cách máy móc cho dự án tiêu chuẩn.

## Kiểm tra kết nối từ ứng dụng

Trước khi xây dựng entity và repository, hãy xác nhận ứng dụng có thể gửi truy vấn tới database. Có thể dùng Neo4jClient bean do Spring Boot tự cấu hình:

~~~java
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.data.neo4j.core.Neo4jClient;
import org.springframework.stereotype.Component;

@Component
public class Neo4jConnectionCheck implements ApplicationRunner {

    private final Neo4jClient neo4jClient;

    public Neo4jConnectionCheck(Neo4jClient neo4jClient) {
        this.neo4jClient = neo4jClient;
    }

    @Override
    public void run(ApplicationArguments args) {
        long result = neo4jClient.query("RETURN 1 AS ready")
            .fetchAs(Long.class)
            .one()
            .orElseThrow(() -> new IllegalStateException("Neo4j returned no result"));

        if (result != 1) {
            throw new IllegalStateException("Neo4j connection check failed");
        }
    }
}
~~~

Khi ứng dụng khởi động, Spring inject Neo4jClient đã được cấu hình. Client chạy truy vấn đọc đơn giản trên database được chọn trong cấu hình Spring Data Neo4j. Trong ứng dụng thực tế, có thể chuyển kiểm tra này thành health indicator hoặc integration test thay vì chạy ở mọi lần khởi động.

Sau khi kiểm tra kết nối thành công, có thể dùng Browser để xác nhận database và dữ liệu:

~~~cypher
RETURN 1 AS ready;
SHOW DATABASES;
~~~

Nếu có quyền truy cập database mặc định, truy vấn đầu tiên xác nhận thực thi Cypher; truy vấn thứ hai liệt kê các database mà tài khoản được phép xem. Kết quả phụ thuộc quyền của tài khoản và cấu hình DBMS.

## Chọn URI kết nối đúng môi trường

| Môi trường | URI thường dùng | Ghi chú |
|---|---|---|
| Docker, ứng dụng chạy trên host | **bolt://localhost:7687** | Cổng Bolt phải được publish ra host |
| Docker, ứng dụng cùng Compose network | **bolt://neo4j:7687** | **neo4j** là tên service trong ví dụ Compose |
| Neo4j Desktop hoặc Server trên cùng máy | **bolt://localhost:7687** | Dùng cổng thực tế nếu đã thay đổi |
| Neo4j Aura | **neo4j+s://INSTANCE_ID.databases.neo4j.io** | Dùng URI được Aura cấp và giữ TLS |

**bolt://** thường phù hợp với DBMS local trong máy phát triển. **neo4j://** sử dụng cơ chế định tuyến của driver. Các scheme có hậu tố **+s** yêu cầu mã hóa TLS và xác minh chứng chỉ; hậu tố **+ssc** có hành vi chấp nhận chứng chỉ tự ký và chỉ nên cân nhắc trong tình huống kiểm thử được kiểm soát. Với Aura, sử dụng URI TLS được cung cấp sẵn.

Nếu ứng dụng chạy trên cloud hoặc một máy khác với DBMS local, địa chỉ **localhost** sẽ trỏ về máy chạy ứng dụng. Hãy dùng hostname có thể phân giải từ môi trường đó và cấu hình mạng tương ứng. Việc mở cổng trên máy host không tự động làm database có thể truy cập từ Internet.

## Xử lý lỗi kết nối thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra và xử lý |
|---|---|---|
| Connection refused | DBMS chưa khởi động, sai cổng hoặc cổng chưa được publish | Kiểm tra trạng thái container/DBMS, log và mapping cổng |
| Authentication failed | Sai username/password hoặc mật khẩu đã đổi | Xác thực lại bằng Browser hoặc Cypher Shell; cập nhật secret ứng dụng |
| Ứng dụng trong container không kết nối được **localhost:7687** | **localhost** trỏ về container ứng dụng | Dùng hostname service, ví dụ **neo4j**, trong cùng Compose network |
| Aura không kết nối được | Sai URI, instance chưa sẵn sàng, network access chưa cho phép hoặc lỗi TLS | Sao chép lại URI từ Aura, kiểm tra trạng thái instance và chính sách mạng; giữ TLS |
| Không tìm thấy database | Tên database trong cấu hình sai hoặc tài khoản không có quyền | Kiểm tra **spring.data.neo4j.database** và quyền của user |
| Container chạy lại nhưng đăng nhập vẫn dùng mật khẩu cũ | Volume dữ liệu đã khởi tạo trước đó | Đổi mật khẩu bằng quy trình quản trị Neo4j; biến **NEO4J_AUTH** chỉ khởi tạo mật khẩu cho dữ liệu mới |
| Port already allocated | Một tiến trình khác đã chiếm cổng 7474 hoặc 7687 | Dừng tiến trình đang dùng cổng hoặc đổi cổng host trong Compose |

Khi điều tra lỗi, nên kiểm tra theo thứ tự: DBMS có chạy không, cổng có lắng nghe không, có đăng nhập được bằng công cụ Neo4j không, URI từ ứng dụng có trỏ đúng máy và cổng không, cuối cùng mới kiểm tra cấu hình Spring Boot. Cách này giúp khoanh vùng lỗi ở tầng vận hành, mạng, xác thực hay ứng dụng.

## Nguyên tắc bảo mật cho môi trường phát triển và triển khai

- Đổi mật khẩu khởi tạo và không dùng chung mật khẩu mẫu giữa các môi trường.
- Không commit password, file **.env**, credential hoặc URI có chứa bí mật.
- Chỉ publish cổng Neo4j ra địa chỉ cần thiết. Với database local, bind vào loopback như ví dụ Docker Compose.
- Dùng TLS khi kết nối qua mạng không tin cậy. Với Aura, giữ URI TLS do dịch vụ cung cấp.
- Cấp user và quyền tối thiểu cần thiết cho ứng dụng; tránh dùng tài khoản quản trị cho mọi workload nếu mô hình vận hành hỗ trợ user riêng.
- Không tắt xác thực hoặc mở database công khai để khắc phục nhanh lỗi kết nối.
- Dùng volume hoặc cơ chế lưu trữ bền vững cho database local; sao lưu dữ liệu quan trọng trước khi xóa hoặc nâng cấp môi trường.
- Pin phiên bản Neo4j và kiểm tra tương thích với Spring Boot/Spring Data Neo4j trước khi nâng cấp.

## Bài tập thực hành

Thực hiện lần lượt các bước sau để xác nhận môi trường đã sẵn sàng:

1. Chọn Docker, Neo4j Desktop/Server hoặc Aura và tạo một database có thể truy cập.
2. Đăng nhập bằng Neo4j Browser hoặc Cypher Shell, chạy **RETURN 1 AS ready;**.
3. Ghi lại URI, username, database name và nơi lưu secret; không đưa password vào Git.
4. Thêm **spring-boot-starter-data-neo4j** vào ứng dụng Spring Boot.
5. Khai báo các thuộc tính **spring.neo4j** và **spring.data.neo4j.database** bằng biến môi trường.
6. Chạy ứng dụng và thực hiện kiểm tra kết nối qua Neo4jClient.
7. Nếu ứng dụng và Neo4j cùng chạy bằng Docker Compose, thử cấu hình URI bằng tên service thay cho **localhost**.

Bạn đã hoàn thành bước chuẩn bị khi DBMS ở trạng thái sẵn sàng, truy vấn Cypher chạy được bằng công cụ Neo4j và ứng dụng Spring Boot mở được kết nối với đúng database. Khi đó có thể tiếp tục khai báo node entity, relationship, repository và các truy vấn Cypher trong tầng dữ liệu của ứng dụng.

