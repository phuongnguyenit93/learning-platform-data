# Chuẩn bị cơ sở dữ liệu phát triển bằng Docker Compose

## 1. Mục tiêu của môi trường cơ sở dữ liệu phát triển

Một ứng dụng Spring Data R2DBC cần kết nối đến một hệ quản trị cơ sở dữ liệu quan hệ có R2DBC driver tương thích. Khi phát triển trên máy cá nhân, việc cài đặt và cấu hình database trực tiếp trên hệ điều hành có thể tạo ra khác biệt giữa máy của từng thành viên: phiên bản database, cổng kết nối, tài khoản, cấu hình và dữ liệu mẫu.

**Docker Compose** giúp mô tả database và các thành phần phụ trợ bằng một file cấu hình có thể lưu cùng source code. Thành viên trong nhóm có thể khởi động cùng một loại database với cấu hình nhất quán bằng một lệnh. Container cung cấp môi trường chạy cô lập; named volume giữ dữ liệu qua những lần tạo lại container.

Trong bài này sử dụng **PostgreSQL** làm ví dụ vì hệ sinh thái có R2DBC driver phổ biến và Spring Data R2DBC hỗ trợ mapping dữ liệu quan hệ. Nếu dự án dùng MySQL, MariaDB hoặc hệ quản trị khác, cần thay image, tham số khởi tạo và driver tương ứng.

Mục tiêu của môi trường phát triển là:

- Khởi động database nhanh mà không phải cài database server trực tiếp trên máy.
- Dùng phiên bản database thống nhất giữa các thành viên.
- Lưu dữ liệu phát triển qua những lần dừng hoặc tạo lại container.
- Cung cấp cổng và hostname rõ ràng để ứng dụng Spring Boot kết nối.
- Có healthcheck để nhận biết database đã sẵn sàng nhận kết nối.
- Có cách nạp schema và dữ liệu mẫu cho quá trình phát triển.

Docker Compose phù hợp với môi trường local và tích hợp kiểm thử. Cấu hình phát triển cần được đánh giá lại trước khi dùng cho production, nơi có yêu cầu riêng về secret, backup, bảo mật mạng, giám sát, HA và quản lý dữ liệu.

## 2. Docker Compose tổ chức database như thế nào?

Docker Compose mô tả một ứng dụng nhiều container trong file YAML, thường có tên **compose.yaml**. Mỗi thành phần chạy được khai báo thành một service. Compose tạo network để các service giao tiếp bằng tên service, đồng thời quản lý volume và port mapping.

Với một ứng dụng Spring Data R2DBC, mô hình phát triển đơn giản có thể gồm:

~~~text
Máy phát triển
    |
    | Spring Boot chạy trực tiếp trên máy
    | R2DBC URL: localhost:5432
    v
127.0.0.1:5432  (port được publish)
    |
    v
Docker Compose network
    |
    v
Service: db (PostgreSQL container)
    |
    +---- Named volume: postgres_data
           dữ liệu database được lưu bền vững
~~~

Nếu ứng dụng Spring Boot cũng chạy trong một container thuộc cùng Compose project, ứng dụng kết nối đến hostname **db** và port nội bộ **5432**. Trong mạng Compose, service name được dùng làm DNS name.

Cần phân biệt ba khái niệm:

- **Service** mô tả cách chạy một thành phần, ví dụ image, biến môi trường, port, volume và healthcheck.
- **Container** là instance thực tế được tạo từ service.
- **Volume** là nơi lưu dữ liệu độc lập với vòng đời container. Xóa và tạo lại container không đồng nghĩa với xóa volume.

## 3. Chuẩn bị công cụ

Cần cài Docker Engine hoặc Docker Desktop có hỗ trợ Docker Compose plugin. Trên Windows, Docker Desktop thường là cách thiết lập thuận tiện; cần bảo đảm Docker daemon đã khởi động trước khi chạy lệnh Compose.

Kiểm tra phiên bản:

~~~bash
docker --version
docker compose version
~~~

Lệnh thứ hai phải nhận diện được Docker Compose plugin. Trong hướng dẫn này dùng cú pháp **docker compose** (Compose V2). Nếu terminal báo không tìm thấy lệnh hoặc không kết nối được Docker daemon, hãy kiểm tra Docker Desktop và trạng thái engine trước khi xử lý file Compose.

Nên đặt file compose.yaml tại thư mục gốc của dự án hoặc trong một thư mục devops có quy ước rõ ràng. Các lệnh bên dưới giả định terminal đang đứng tại thư mục chứa file đó.

## 4. Tạo file compose.yaml cho PostgreSQL

Tạo file **compose.yaml**:

~~~yaml
services:
  db:
    image: postgres:17
    environment:
      POSTGRES_DB: ${DB_NAME:-app}
      POSTGRES_USER: ${DB_USER:-app}
      POSTGRES_PASSWORD: ${DB_PASSWORD:?Set DB_PASSWORD in .env}
    ports:
      - "127.0.0.1:5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./db/init:/docker-entrypoint-initdb.d:ro
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U $$POSTGRES_USER -d $$POSTGRES_DB"]
      interval: 5s
      timeout: 5s
      retries: 10
      start_period: 5s

volumes:
  postgres_data:
~~~

Ví dụ dùng image **postgres:17** để cố định major version của PostgreSQL. Dự án thực tế nên chọn major version phù hợp với môi trường đích và pin phiên bản đã được kiểm thử. Tránh dùng tag **latest** nếu cần kết quả phát triển có thể tái lập.

Ý nghĩa các cấu hình:

| Cấu hình | Mục đích |
|---|---|
| **image** | Chọn image PostgreSQL và phiên bản cụ thể |
| **POSTGRES_DB** | Tạo database mặc định khi khởi tạo data directory lần đầu |
| **POSTGRES_USER** | Tạo user quản trị ban đầu của container |
| **POSTGRES_PASSWORD** | Đặt mật khẩu cho user khởi tạo |
| **ports** | Publish cổng database ra loopback của máy phát triển |
| **postgres_data** | Lưu dữ liệu database trong named volume |
| **./db/init** | Chứa script SQL khởi tạo, được mount chỉ đọc |
| **healthcheck** | Kiểm tra PostgreSQL đã sẵn sàng nhận kết nối hay chưa |

Cổng được bind vào **127.0.0.1** để database chỉ nhận kết nối từ máy phát triển qua loopback. Nếu nhóm có nhu cầu truy cập từ máy khác trong mạng, cần chủ động thiết kế lại việc publish port và quy tắc firewall; không nên mở database ra mọi interface một cách vô tình.

Trong healthcheck, ký hiệu **$$** giúp Compose chuyển biến môi trường cho shell bên trong container thay vì cố nội suy biến ở máy host. Lệnh **pg_isready** kiểm tra PostgreSQL có đang nhận kết nối hay không. Healthcheck thành công là dấu hiệu database sẵn sàng về mặt kết nối, không bảo đảm schema nghiệp vụ hoặc dữ liệu mẫu đã đúng.

Mount **./db/init** là tùy chọn. Nếu chưa có script khởi tạo, có thể tạo thư mục rỗng hoặc bỏ dòng volume đó.

## 5. Quản lý biến môi trường và thông tin kết nối

Không nên ghi mật khẩu thật trực tiếp vào file compose được commit lên Git. Có thể dùng file **.env** ở cùng thư mục với compose.yaml để Compose nội suy các biến cấu hình.

Tạo file **.env** cho máy phát triển:

~~~dotenv
DB_NAME=app
DB_USER=app
DB_PASSWORD=local-dev-password
~~~

Mật khẩu trong ví dụ chỉ dành cho môi trường local. Mỗi nhóm có thể tạo mật khẩu phát triển riêng theo quy ước của dự án. File .env chứa thông tin cục bộ cần được đưa vào **.gitignore**. Thay vào đó, commit một file **.env.example** không chứa secret thật:

~~~dotenv
DB_NAME=app
DB_USER=app
DB_PASSWORD=replace-with-a-local-password
~~~

Thành viên mới sao chép .env.example thành .env rồi cập nhật giá trị phù hợp. Docker Compose tự đọc file .env ở project directory để thay thế các biểu thức như **${DB_NAME:-app}** trong compose.yaml.

Cú pháp **${DB_PASSWORD:?Set DB_PASSWORD in .env}** yêu cầu biến DB_PASSWORD phải có giá trị. Nếu thiếu, Compose báo lỗi ngay khi phân tích cấu hình thay vì âm thầm khởi động database với mật khẩu rỗng.

Có thể kiểm tra cấu hình Compose sau khi biến đã được cung cấp:

~~~bash
docker compose config
~~~

Lệnh này hiển thị cấu hình sau nội suy. Vì đầu ra có thể chứa thông tin nhạy cảm, không nên đăng nguyên kết quả lên issue hoặc log công khai. Khi chia sẻ cấu hình, cần che giá trị password và token.

## 6. Khởi động và kiểm tra database

Tại thư mục có compose.yaml, chạy:

~~~bash
docker compose up -d db
~~~

Compose sẽ tải image nếu máy chưa có, tạo network, tạo volume và khởi động service **db** ở chế độ nền.

Kiểm tra trạng thái:

~~~bash
docker compose ps
~~~

Cột trạng thái health có thể hiển thị **starting**, **healthy** hoặc **unhealthy**. Nếu container chưa healthy, xem log:

~~~bash
docker compose logs -f db
~~~

Nhấn Ctrl+C để thoát chế độ theo dõi log; thao tác này không dừng container.

Có thể kiểm tra PostgreSQL từ bên trong container:

~~~bash
docker compose exec db pg_isready -U app -d app
~~~

Hoặc chạy một truy vấn SQL:

~~~bash
docker compose exec db psql -U app -d app -c "SELECT version();"
~~~

Các lệnh trên dùng giá trị app theo file .env mẫu. Nếu đổi DB_NAME hoặc DB_USER, hãy thay tham số tương ứng.

Để xem danh sách database:

~~~bash
docker compose exec db psql -U app -d app -c "\l"
~~~

Để vào interactive shell:

~~~bash
docker compose exec db psql -U app -d app
~~~

Trong psql có thể chạy SQL và thoát bằng lệnh **\q**.

## 7. Kết nối Spring Data R2DBC với PostgreSQL

Cách viết R2DBC URL phụ thuộc vào nơi ứng dụng Spring Boot đang chạy.

### 7.1. Ứng dụng chạy trực tiếp trên máy phát triển

Nếu Spring Boot chạy bằng IDE hoặc Gradle trên host, ứng dụng truy cập cổng đã publish qua **localhost:5432**.

Ví dụ trong application.properties:

~~~properties
spring.r2dbc.url=r2dbc:postgresql://localhost:5432/app
spring.r2dbc.username=app
spring.r2dbc.password=${DB_PASSWORD}
~~~

Có thể đặt user và database theo biến môi trường nếu dự án cần hỗ trợ nhiều cấu hình:

~~~properties
spring.r2dbc.url=${R2DBC_URL:r2dbc:postgresql://localhost:5432/app}
spring.r2dbc.username=${DB_USER:app}
spring.r2dbc.password=${DB_PASSWORD}
~~~

Đảm bảo tiến trình Spring Boot nhận được các biến môi trường tương ứng. File .env được Docker Compose tự đọc cho mục đích nội suy compose.yaml; nó không tự động trở thành environment của một tiến trình Java chạy trực tiếp trên host. Có thể cấu hình environment trong IDE, terminal hoặc công cụ chạy ứng dụng theo quy ước của dự án.

### 7.2. Ứng dụng Spring Boot cũng chạy trong Docker Compose

Nếu ứng dụng và database cùng nằm trong một Compose network, dùng tên service **db** làm hostname:

~~~properties
spring.r2dbc.url=r2dbc:postgresql://db:5432/app
spring.r2dbc.username=app
spring.r2dbc.password=${DB_PASSWORD}
~~~

Trong trường hợp này, không dùng localhost. Bên trong container ứng dụng, localhost trỏ về chính container ứng dụng. Tên **db** được Docker Compose phân giải thành địa chỉ của container database.

Có thể bổ sung service ứng dụng vào compose.yaml theo dạng:

~~~yaml
services:
  db:
    image: postgres:17
    environment:
      POSTGRES_DB: ${DB_NAME:-app}
      POSTGRES_USER: ${DB_USER:-app}
      POSTGRES_PASSWORD: ${DB_PASSWORD:?Set DB_PASSWORD in .env}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U $$POSTGRES_USER -d $$POSTGRES_DB"]
      interval: 5s
      timeout: 5s
      retries: 10
      start_period: 5s

  app:
    build: .
    environment:
      SPRING_R2DBC_URL: r2dbc:postgresql://db:5432/${DB_NAME:-app}
      SPRING_R2DBC_USERNAME: ${DB_USER:-app}
      SPRING_R2DBC_PASSWORD: ${DB_PASSWORD:?Set DB_PASSWORD in .env}
    depends_on:
      db:
        condition: service_healthy

volumes:
  postgres_data:
~~~

Đây là phần minh họa cách kết nối; service app yêu cầu dự án có Dockerfile phù hợp. Nếu chỉ chạy database trong Compose và chạy ứng dụng bằng IDE, không cần khai báo service app.

**depends_on với condition: service_healthy** giúp Compose chờ healthcheck của database đạt trạng thái healthy trước khi khởi động app. Nó giảm lỗi kết nối do database chưa sẵn sàng ở lần khởi động đầu. Ứng dụng vẫn nên có chiến lược retry hoặc xử lý lỗi kết nối khi database khởi động lại trong lúc app đang chạy.

### 7.3. Dependency R2DBC trong dự án Spring Boot

Với Gradle Groovy DSL, một ứng dụng Spring Data R2DBC dùng PostgreSQL thường cần:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-r2dbc'
    runtimeOnly 'org.postgresql:r2dbc-postgresql'
}
~~~

Starter cung cấp tích hợp Spring Data R2DBC; driver PostgreSQL cung cấp giao tiếp theo R2DBC SPI. Cần để Spring Boot dependency management quản lý các phiên bản tương thích, tránh tự ghép những phiên bản driver và framework không tương thích.

Chỉ chạy PostgreSQL trong Docker không tự tạo R2DBC driver trong ứng dụng. Container database và dependency của ứng dụng là hai phần cấu hình độc lập, đều phải có.

## 8. Tạo schema và dữ liệu mẫu

Một database mới cần có bảng và dữ liệu để ứng dụng có thể phát triển, chạy thử API và kiểm tra repository. Có thể dùng init script của image PostgreSQL cho môi trường local đơn giản.

Tạo thư mục:

~~~text
project/
├── compose.yaml
├── .env
├── .env.example
└── db/
    └── init/
        └── 001-schema.sql
~~~

Ví dụ file **db/init/001-schema.sql**:

~~~sql
CREATE TABLE IF NOT EXISTS customers (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    name VARCHAR(150) NOT NULL,
    email VARCHAR(255) NOT NULL UNIQUE,
    status VARCHAR(30) NOT NULL
);

INSERT INTO customers (name, email, status)
VALUES
    ('An Nguyen', 'an@example.test', 'ACTIVE'),
    ('Binh Tran', 'binh@example.test', 'INACTIVE')
ON CONFLICT (email) DO NOTHING;
~~~

Image PostgreSQL chính thức chạy các script trong **/docker-entrypoint-initdb.d** khi khởi tạo một data directory mới. Các file script được thực thi theo thứ tự tên. Mount read-only giúp container đọc script mà không ghi ngược vào source code của dự án.

Kiểm tra bảng và dữ liệu sau khi database khởi tạo:

~~~bash
docker compose exec db psql -U app -d app -c "SELECT id, name, email, status FROM customers ORDER BY id;"
~~~

**Lưu ý quan trọng về vòng đời init script:** các script trong thư mục init chỉ chạy khi data directory được khởi tạo lần đầu và còn trống. Nếu volume postgres_data đã có dữ liệu, thay đổi file 001-schema.sql rồi chạy lại docker compose up không khiến script tự chạy lần nữa.

Đối với dự án cần quản lý thay đổi schema theo thời gian, nên dùng công cụ migration như Flyway hoặc Liquibase với migration được version control. Init script của container tiện cho bootstrap database mới, nhưng không thay thế quy trình migration của ứng dụng. Một số công cụ migration sử dụng JDBC; điều đó có thể được cấu hình riêng ngay cả khi đường truy cập dữ liệu runtime của ứng dụng dùng R2DBC.

## 9. Vòng đời container và dữ liệu trong volume

Container và dữ liệu database có vòng đời khác nhau. Named volume giúp dữ liệu tồn tại khi container bị dừng hoặc xóa rồi tạo lại.

Các lệnh thường dùng:

| Lệnh | Tác dụng |
|---|---|
| **docker compose up -d db** | Tạo hoặc khởi động service database ở chế độ nền |
| **docker compose stop db** | Dừng container nhưng giữ container và volume |
| **docker compose start db** | Khởi động lại container đã dừng |
| **docker compose restart db** | Khởi động lại service |
| **docker compose down** | Dừng và xóa container cùng network của project; named volume mặc định được giữ |
| **docker compose down -v** | Xóa container, network và named volume của project |
| **docker compose logs -f db** | Theo dõi log database |
| **docker compose exec db psql -U app -d app** | Mở psql trong container |

Chỉ dùng **docker compose down -v** khi chủ động muốn xóa dữ liệu database phát triển và tạo lại từ đầu. Đây là thao tác xóa volume; dữ liệu lưu trong volume đó sẽ mất. Nếu chỉ muốn dừng môi trường cuối ngày, dùng **docker compose stop** hoặc **docker compose down**.

Có thể xem volume mà Compose tạo:

~~~bash
docker volume ls
~~~

Tên thực tế thường có tiền tố theo tên project Compose. Không nên chỉnh sửa trực tiếp file dữ liệu PostgreSQL trong volume khi container đang chạy.

## 10. Cấu hình và quy ước cho nhóm phát triển

Để mọi thành viên có thể dựng môi trường giống nhau, nên thống nhất một số quy ước trong repository:

- Lưu compose.yaml cùng dự án hoặc ở thư mục devops đã được quy định.
- Pin major version của PostgreSQL và thay đổi phiên bản có chủ đích.
- Commit .env.example nhưng không commit .env chứa mật khẩu cục bộ.
- Đưa .env, file dump có dữ liệu nhạy cảm và các file secret vào .gitignore.
- Đặt tên database, user, port và volume theo quy ước nhất quán.
- Để script khởi tạo trong thư mục có cấu trúc rõ ràng; dùng migration có version cho thay đổi schema lâu dài.
- Viết hướng dẫn lệnh khởi động, kiểm tra và dừng database trong README của dự án.
- Không dùng dữ liệu cá nhân hoặc dữ liệu production thật trong môi trường local nếu chưa được xử lý và cho phép.

Ví dụ các dòng phù hợp trong .gitignore:

~~~gitignore
.env
.env.*
!.env.example
~~~

Quy tắc này bỏ qua file .env và các biến thể, nhưng vẫn cho phép commit .env.example. Nếu dự án đã có quy tắc ignore riêng, cần kết hợp để không vô tình bỏ qua các file cấu hình mẫu khác.

## 11. Xử lý những lỗi thường gặp

### 11.1. Port 5432 đã được sử dụng

Thông báo thường gặp là Docker không thể bind cổng host vì cổng đã được một PostgreSQL cài trực tiếp hoặc một container khác sử dụng.

Kiểm tra container:

~~~bash
docker compose ps
docker ps
~~~

Có thể đổi cổng host trong compose.yaml, ví dụ:

~~~yaml
ports:
  - "127.0.0.1:5433:5432"
~~~

Khi đó, ứng dụng chạy trực tiếp trên máy phải kết nối **localhost:5433**. Ứng dụng trong cùng Compose network vẫn kết nối **db:5432**, vì port nội bộ của container không thay đổi.

### 11.2. Ứng dụng không kết nối được database

Kiểm tra theo thứ tự:

1. Container có đang chạy không bằng **docker compose ps**?
2. Healthcheck đã báo healthy chưa?
3. Log PostgreSQL có báo lỗi khởi tạo hoặc xác thực không?
4. Ứng dụng chạy trên host hay trong container?
5. Hostname và port có đúng với vị trí chạy ứng dụng không?
6. Database, username và password có khớp với cấu hình đã khởi tạo volume không?

Một lỗi rất phổ biến là dùng **localhost** trong container ứng dụng. Trong Compose network, hãy dùng tên service **db**. Ngược lại, ứng dụng chạy trực tiếp trên máy phát triển phải dùng địa chỉ host đã publish, ví dụ **localhost:5432**.

### 11.3. Password trong .env đã đổi nhưng database vẫn từ chối đăng nhập

Các biến POSTGRES_DB, POSTGRES_USER và POSTGRES_PASSWORD của image chính thức được dùng để khởi tạo database khi data directory còn trống. Nếu named volume đã chứa database, thay đổi biến môi trường không tự đổi password hoặc tạo lại user trong database hiện có.

Có hai hướng xử lý:

- Nếu cần giữ dữ liệu, đăng nhập bằng tài khoản có quyền phù hợp và cập nhật user/password bằng SQL.
- Nếu đây là database phát triển có thể tạo lại, xóa volume có chủ đích rồi khởi động lại để image khởi tạo data directory mới.

Không xóa volume chỉ để thử một cấu hình khi chưa xác nhận dữ liệu trong đó có thể bỏ đi.

### 11.4. Healthcheck liên tục unhealthy

Xem log:

~~~bash
docker compose logs --tail=200 db
~~~

Kiểm tra giá trị database và user được nội suy, cú pháp healthcheck, trạng thái khởi tạo volume và tài nguyên máy. Healthcheck dùng user/database phải tồn tại trong instance. Nếu cấu hình healthcheck khác với tài khoản đã được khởi tạo trong volume, lệnh kiểm tra có thể thất bại dù server vẫn đang chạy.

### 11.5. Sửa init SQL nhưng schema không thay đổi

Init script không được chạy lại trên data directory đã khởi tạo. Để cập nhật schema của database hiện tại, dùng migration hoặc thực thi SQL có kiểm soát. Chỉ tạo lại volume nếu muốn reset toàn bộ database phát triển và chấp nhận mất dữ liệu hiện tại.

### 11.6. Ứng dụng khởi động trước database

Chỉ khai báo **depends_on** dạng danh sách đơn thuần không đồng nghĩa database đã sẵn sàng nhận kết nối. Dùng healthcheck và **condition: service_healthy** khi app cũng do Compose quản lý. Ngoài ra, ứng dụng nên có khả năng thử kết nối lại khi database khởi động chậm hoặc được restart.

## 12. Quy trình làm việc đề xuất hằng ngày

Một vòng làm việc local thường có thể thực hiện như sau:

~~~text
Lần đầu clone dự án
       |
       v
Sao chép .env.example thành .env
       |
       v
Cập nhật cấu hình local
       |
       v
docker compose up -d db
       |
       v
Kiểm tra healthcheck và log
       |
       v
Chạy migration / chuẩn bị schema
       |
       v
Khởi động Spring Boot
       |
       v
Phát triển và kiểm thử repository
       |
       v
docker compose stop (khi cần dừng)
~~~

Các lệnh cốt lõi:

~~~bash
# Khởi động database
docker compose up -d db

# Kiểm tra trạng thái
docker compose ps

# Xem log
docker compose logs -f db

# Kiểm tra PostgreSQL
docker compose exec db pg_isready -U app -d app

# Dừng database, giữ dữ liệu
docker compose stop db
~~~

Khi quay lại làm việc, chạy **docker compose start db** hoặc **docker compose up -d db**. Volume giữ database để không phải nạp lại dữ liệu từ đầu.

## 13. Checklist bàn giao môi trường cho thành viên mới

Một môi trường phát triển có thể xem là sẵn sàng để thành viên khác sử dụng khi:

- Docker Engine và Docker Compose plugin chạy được.
- compose.yaml có thể được phân tích bằng **docker compose config** sau khi thiết lập .env.
- Image PostgreSQL được pin phiên bản.
- Database khởi động và healthcheck đạt trạng thái healthy.
- Có thể kết nối bằng psql từ container.
- Spring Boot dùng đúng R2DBC URL theo vị trí chạy (localhost từ host hoặc db từ container).
- Dependency R2DBC driver tương thích với database đã chọn.
- Schema và dữ liệu mẫu được tạo bằng init script hoặc migration.
- Dừng rồi khởi động lại container không làm mất dữ liệu trong named volume.
- README chỉ rõ cách khởi động, kiểm tra, dừng và reset database phát triển.

## 14. Kết luận

Docker Compose giúp chuẩn hóa database phục vụ phát triển bằng cách mô tả service, network, port, volume, biến môi trường và healthcheck trong cấu hình có thể chia sẻ cùng repository. Với Spring Data R2DBC, PostgreSQL có thể chạy trong một container riêng, còn ứng dụng kết nối qua R2DBC URL.

Điểm cần nhớ nhất khi cấu hình kết nối là hostname phụ thuộc vào nơi ứng dụng chạy: **localhost** khi Spring Boot chạy trên host và **tên service Compose** khi Spring Boot chạy trong cùng network container. Named volume giữ dữ liệu qua vòng đời container; init script của PostgreSQL chỉ chạy khi data directory được khởi tạo lần đầu. Khi nắm rõ các quy tắc này, nhóm có thể dựng lại môi trường phát triển nhất quán và tập trung vào việc triển khai, kiểm thử tầng truy cập dữ liệu.

