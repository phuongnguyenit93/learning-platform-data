# Chạy môi trường học tập nhiều dịch vụ bằng Docker Compose

## 1. Mục tiêu

Khi học Java, Spring Boot và kiến trúc Microservices, một service hiếm khi chạy độc lập. Một API có thể cần database, cache, message broker, một service khác và hệ thống quan sát. Nếu mỗi lần học phải cài đặt PostgreSQL, Redis, RabbitMQ, cấu hình port, tạo user, dựng schema và khởi động từng ứng dụng thủ công, người học sẽ dành nhiều thời gian xử lý môi trường thay vì hiểu luồng nghiệp vụ.

**Docker Compose** giúp khai báo một nhóm container liên quan trong file cấu hình, kết nối chúng bằng network, cấp volume và mô tả dependency. Với vài lệnh, người học có thể dựng, quan sát, dừng và khởi tạo lại môi trường gồm nhiều service trên máy cá nhân.

Bài học xây dựng một môi trường có thể tái tạo, dễ debug và đủ gần với cách các thành phần giao tiếp trong hệ thống phân tán. Ví dụ gồm hai ứng dụng Spring Boot là Catalog Service và Order Service, hai database riêng, Redis và RabbitMQ.

Sau bài học, người đọc có thể:

- Giải thích vai trò của Docker Engine, image, container, network, volume và Compose project.
- Thiết kế topology local nhiều service với ranh giới dữ liệu rõ.
- Khai báo service, build, image, ports, environment, networks, volumes và healthcheck.
- Hiểu service discovery qua DNS nội bộ của Compose.
- Phân biệt host port và container port, cũng như vì sao localhost bên trong container không phải máy host.
- Dùng depends_on và healthcheck đúng mục đích, không nhầm thứ tự khởi động với khả năng phục vụ ổn định.
- Cấu hình Spring Boot kết nối database, Redis và message broker bằng biến môi trường.
- Quản lý cấu hình local, secrets, dữ liệu persistent và profiles.
- Khởi động, theo dõi logs, chạy lệnh trong container và xử lý lỗi phổ biến.
- Viết smoke tests và integration tests cho môi trường nhiều dịch vụ.
- Dọn dẹp môi trường có kiểm soát, tránh xóa nhầm dữ liệu cần giữ.
- Phân biệt môi trường học tập Compose với nền tảng triển khai production.

Các ví dụ YAML và lệnh hướng tới Docker Compose V2 và Docker Engine hiện đại. Phiên bản image, JDK, Spring Boot và công cụ cần được pin theo môi trường dự án thực tế; các giá trị trong bài là ví dụ học tập, không phải cấu hình production mặc định.

## 2. Vì sao cần môi trường nhiều dịch vụ có thể tái tạo?

Một hệ thống ví dụ có thể gồm:

~~~text
                  Browser / API Client
                          |
              +-----------+-----------+
              |                       |
              v                       v
       Catalog Service          Order Service
              |                       |
       +------+-----+            +----+------+
       |            |            |           |
       v            v            v           v
   Catalog DB     Redis       Order DB    RabbitMQ
                                           |
                                           v
                                  Event Consumers
~~~

Catalog Service quản lý thông tin sản phẩm. Order Service tạo đơn hàng và phát sự kiện. Mỗi service có database riêng; Redis phục vụ cache catalog; RabbitMQ truyền sự kiện giữa các service.

Một môi trường local hữu ích cần:

- Có thể dựng lại từ repository mới clone.
- Không phụ thuộc thứ tự người học nhớ phải mở terminal nào trước.
- Cấu hình port và hostname nhất quán.
- Có dữ liệu persistent khi restart container.
- Có health status để nhận biết dependency đã sẵn sàng.
- Log có thể truy cập theo từng service.
- Có thể chạy một service riêng khi debug.
- Có cách reset dữ liệu rõ ràng.
- Không yêu cầu credential production.
- Không public database hoặc management UI ra mạng ngoài nếu không cần.

Compose cung cấp một cách khai báo tập trung cho các thành phần này, đồng thời vẫn cho phép từng container có lifecycle và logs riêng.

## 3. Docker và Docker Compose là gì?

### 3.1. Docker Engine

Docker Engine cung cấp môi trường để build và chạy container. Container là một tiến trình được cô lập bằng các cơ chế của hệ điều hành, sử dụng image làm filesystem/runtime base.

Một số khái niệm:

- **Image:** gói bất biến chứa filesystem, runtime và metadata cần để tạo container.
- **Container:** instance đang chạy hoặc đã dừng của image.
- **Volume:** vùng lưu trữ do Docker quản lý, có thể tồn tại qua vòng đời container.
- **Bind mount:** ánh xạ một đường dẫn trên máy host vào container.
- **Network:** kênh giao tiếp giữa các container và host theo cấu hình.
- **Registry:** nơi lưu và phân phối image.
- **Dockerfile:** các bước build một image.

Container không phải máy ảo đầy đủ. Nó chia sẻ kernel với host, vì vậy bảo mật và isolation cần được hiểu theo nền tảng chạy thực tế.

### 3.2. Docker Compose

Docker Compose là công cụ khai báo và quản lý một ứng dụng nhiều container. File Compose mô tả:

- Service nào cần chạy.
- Image nào được sử dụng hoặc build từ source.
- Port nào được publish.
- Environment variables nào được cấp.
- Container kết nối network nào.
- Dữ liệu được lưu vào volume nào.
- Healthcheck và dependency ra sao.
- Service nào chỉ bật khi chọn profile.

Lệnh thường dùng:

~~~bash
docker compose up -d
~~~

Compose đọc file cấu hình mặc định (thường là compose.yaml hoặc docker-compose.yml), tạo network/volume cần thiết và khởi động các service.

### 3.3. Compose project

Một Compose project nhóm các resource theo project name. Nếu hai thư mục khác nhau chạy Compose với tên project khác nhau, network/volume/resource thường được tách riêng theo project scope.

Tên project có thể được xác định bằng tùy chọn -p, biến COMPOSE_PROJECT_NAME, thuộc tính name trong file hoặc tên thư mục theo quy tắc Compose. Nên đặt tên ổn định để tránh vô tình tạo nhiều bộ database local không biết bộ nào đang được dùng.

## 4. Chuẩn bị công cụ

Trên máy phát triển, cần:

1. Docker Desktop trên Windows/macOS hoặc Docker Engine + Compose plugin trên Linux.
2. Docker Compose V2, dùng lệnh docker compose.
3. Git để clone repository.
4. JDK/Maven hoặc Gradle nếu muốn chạy ứng dụng trực tiếp từ IDE.
5. Một IDE như IntelliJ IDEA hoặc VS Code.
6. API client như curl, HTTP client trong IDE hoặc Postman.
7. Đủ dung lượng đĩa cho images, volumes và logs.

Kiểm tra cài đặt:

~~~bash
docker --version
docker compose version
docker info
~~~

Nếu docker info không kết nối được daemon, kiểm tra Docker Desktop/Engine đã khởi động và user có quyền truy cập Docker socket/daemon chưa.

### 4.1. Windows và WSL2

Trên Windows, Docker Desktop thường chạy Linux containers thông qua WSL2 backend. Nên thống nhất nơi lưu repository và cách truy cập filesystem; thao tác build trên filesystem của WSL2 thường cho trải nghiệm tốt khi dự án dùng Linux containers.

Một số lưu ý:

- Dùng dấu / trong đường dẫn Compose để giảm khác biệt giữa môi trường.
- Tránh mount thư mục chứa quá nhiều file nhỏ từ filesystem chậm nếu hot reload bị trễ.
- Kiểm tra line endings của shell scripts; LF thường phù hợp trong Linux container.
- Không giả định đường dẫn C:\... có thể dùng nguyên văn bên trong container.
- Không chạy đồng thời nhiều Docker daemons mà không biết context đang trỏ tới đâu.

Kiểm tra Docker context:

~~~bash
docker context ls
docker context show
~~~

### 4.2. Pin phiên bản

Một môi trường học tập nên ghi rõ phiên bản Docker Compose, JDK, Spring Boot, PostgreSQL, Redis và RabbitMQ đã được thử nghiệm. Không dùng tag latest cho mọi image nếu muốn kết quả có thể tái tạo.

Tag version vẫn có thể được cập nhật ở registry trong một số trường hợp; với môi trường cần tính bất biến cao hơn, có thể pin image digest. Cân bằng khả năng tái lập với quy trình cập nhật security patches.

## 5. Cấu trúc repository cho môi trường học tập

Một layout dễ hiểu:

~~~text
java-microservices-lab/
├── compose.yaml
├── .env.example
├── .gitignore
├── README.md
├── catalog-service/
│   ├── Dockerfile
│   ├── pom.xml
│   └── src/
├── order-service/
│   ├── Dockerfile
│   ├── pom.xml
│   └── src/
├── infra/
│   ├── postgres/
│   └── rabbitmq/
├── scripts/
│   ├── wait-for-lab.sh
│   └── smoke-test.sh
└── docs/
    ├── architecture.md
    └── troubleshooting.md
~~~

Không cần tạo mọi thư mục ngay từ đầu. Hãy thêm thành phần khi có bài học sử dụng chúng.

Vai trò:

- compose.yaml: mô tả topology local.
- .env.example: danh sách biến cấu hình mẫu, không chứa credential thật.
- .gitignore: loại .env, local data, log và file IDE không cần commit.
- catalog-service/: source và Dockerfile của Catalog.
- order-service/: source và Dockerfile của Order.
- infra/: config khởi tạo dependency nếu cần.
- scripts/: thao tác lặp lại như smoke test.
- docs/: sơ đồ và hướng dẫn vận hành.

Giữ file Compose ở root giúp người mới tìm được entry point nhanh. Nếu môi trường lớn lên, có thể tách file theo profile hoặc dùng nhiều Compose files với cách override được document.

## 6. Xác định topology và ranh giới dữ liệu

Trước khi viết YAML, liệt kê thành phần và trách nhiệm:

| Thành phần | Trách nhiệm | Lưu trữ |
|---|---|---|
| catalog-service | API sản phẩm và danh mục | catalog-db |
| order-service | Tạo đơn và trạng thái đơn | order-db |
| catalog-db | Dữ liệu thuộc Catalog | named volume riêng |
| order-db | Dữ liệu thuộc Order | named volume riêng |
| redis | Cache read model Catalog | named volume tùy nhu cầu |
| rabbitmq | Broker sự kiện giữa service | named volume riêng |
| API client | Gọi API từ host | Không cần volume |

Hai service không nên cùng ghi trực tiếp một database schema chỉ vì đang dùng chung một PostgreSQL server. Có thể dùng hai database với user quyền riêng trong lab để minh họa data ownership; khi tiến tới production, việc tách instance, cluster hoặc schema phụ thuộc yêu cầu isolation và vận hành.

### 6.1. Không phải mọi dependency đều cần container

Một số thành phần có thể chạy từ máy host hoặc dùng mock:

- IDE chạy Spring Boot trên host, DB và broker chạy trong Compose.
- Dùng Testcontainers cho integration tests thay vì giữ cả stack luôn chạy.
- Dùng WireMock/mock server cho external provider.
- Chỉ khởi động profile observability khi cần.

Chọn cách giúp người học quan sát được ranh giới cần học mà không làm môi trường phức tạp không cần thiết.

## 7. File Compose mẫu cho hai Spring Boot services

Một ví dụ tương đối đầy đủ:

~~~yaml
name: java-microservices-lab

services:
  catalog-db:
    image: postgres:16.4
    environment:
      POSTGRES_DB: catalog
      POSTGRES_USER: catalog
      POSTGRES_PASSWORD: ${CATALOG_DB_PASSWORD:?Set CATALOG_DB_PASSWORD in .env}
    volumes:
      - catalog-db-data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U catalog -d catalog"]
      interval: 5s
      timeout: 3s
      retries: 10
      start_period: 10s
    networks:
      - lab-network

  order-db:
    image: postgres:16.4
    environment:
      POSTGRES_DB: orders
      POSTGRES_USER: orders
      POSTGRES_PASSWORD: ${ORDER_DB_PASSWORD:?Set ORDER_DB_PASSWORD in .env}
    volumes:
      - order-db-data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U orders -d orders"]
      interval: 5s
      timeout: 3s
      retries: 10
      start_period: 10s
    networks:
      - lab-network

  redis:
    image: redis:7.4
    command: ["redis-server", "--appendonly", "yes"]
    volumes:
      - redis-data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 10
    networks:
      - lab-network

  rabbitmq:
    image: rabbitmq:3.13-management
    environment:
      RABBITMQ_DEFAULT_USER: labuser
      RABBITMQ_DEFAULT_PASS: ${RABBITMQ_PASSWORD:?Set RABBITMQ_PASSWORD in .env}
    volumes:
      - rabbitmq-data:/var/lib/rabbitmq
    ports:
      - "127.0.0.1:15672:15672"
    healthcheck:
      test: ["CMD", "rabbitmq-diagnostics", "-q", "ping"]
      interval: 10s
      timeout: 5s
      retries: 10
      start_period: 20s
    networks:
      - lab-network

  catalog-service:
    build:
      context: ./catalog-service
      dockerfile: Dockerfile
    environment:
      SERVER_PORT: 8080
      SPRING_DATASOURCE_URL: jdbc:postgresql://catalog-db:5432/catalog
      SPRING_DATASOURCE_USERNAME: catalog
      SPRING_DATASOURCE_PASSWORD: ${CATALOG_DB_PASSWORD:?Set CATALOG_DB_PASSWORD in .env}
      SPRING_DATA_REDIS_HOST: redis
      SPRING_DATA_REDIS_PORT: 6379
      SPRING_RABBITMQ_HOST: rabbitmq
      SPRING_RABBITMQ_PORT: 5672
      SPRING_RABBITMQ_USERNAME: labuser
      SPRING_RABBITMQ_PASSWORD: ${RABBITMQ_PASSWORD:?Set RABBITMQ_PASSWORD in .env}
    ports:
      - "127.0.0.1:8081:8080"
    depends_on:
      catalog-db:
        condition: service_healthy
      redis:
        condition: service_healthy
      rabbitmq:
        condition: service_healthy
    healthcheck:
      test: ["CMD-SHELL", "wget -q --spider http://127.0.0.1:8080/actuator/health/readiness || exit 1"]
      interval: 10s
      timeout: 3s
      retries: 10
      start_period: 30s
    networks:
      - lab-network

  order-service:
    build:
      context: ./order-service
      dockerfile: Dockerfile
    environment:
      SERVER_PORT: 8080
      SPRING_DATASOURCE_URL: jdbc:postgresql://order-db:5432/orders
      SPRING_DATASOURCE_USERNAME: orders
      SPRING_DATASOURCE_PASSWORD: ${ORDER_DB_PASSWORD:?Set ORDER_DB_PASSWORD in .env}
      SPRING_RABBITMQ_HOST: rabbitmq
      SPRING_RABBITMQ_PORT: 5672
      SPRING_RABBITMQ_USERNAME: labuser
      SPRING_RABBITMQ_PASSWORD: ${RABBITMQ_PASSWORD:?Set RABBITMQ_PASSWORD in .env}
    ports:
      - "127.0.0.1:8082:8080"
    depends_on:
      order-db:
        condition: service_healthy
      rabbitmq:
        condition: service_healthy
    healthcheck:
      test: ["CMD-SHELL", "wget -q --spider http://127.0.0.1:8080/actuator/health/readiness || exit 1"]
      interval: 10s
      timeout: 3s
      retries: 10
      start_period: 30s
    networks:
      - lab-network

volumes:
  catalog-db-data:
  order-db-data:
  redis-data:
  rabbitmq-data:

networks:
  lab-network:
    driver: bridge
~~~

Đây là ví dụ học tập; cần kiểm tra tag image còn được registry cung cấp và tương thích với máy. Wget phải có trong image của ứng dụng để healthcheck hoạt động; nếu runtime image không cài công cụ này, hãy dùng healthcheck phù hợp hoặc bỏ healthcheck ở tầng container và triển khai kiểm tra readiness ở nơi thích hợp. Spring Boot Actuator readiness endpoint phải được bật và expose trên port mà container kiểm tra.

Compose không tự tạo schema nghiệp vụ cho ứng dụng. Migration tool như Flyway/Liquibase hoặc bước khởi tạo phù hợp cần được cấu hình trong từng service. RabbitMQ user/password ở đây chỉ dành cho lab local.

### 7.1. Vì sao mỗi service có database riêng?

Order Service không nên query trực tiếp bảng products của Catalog chỉ vì hai ứng dụng đang chạy trong cùng một máy. Nếu Order cần tên/giá sản phẩm, nó có thể gọi Catalog API hoặc lưu snapshot thông tin cần thiết vào order theo contract nghiệp vụ.

Tách database giúp minh họa:

- Data ownership.
- Migrations độc lập.
- Quyền truy cập riêng.
- Khả năng thay đổi schema theo service.
- Giới hạn blast radius.
- Khác biệt giữa giao dịch và read model.

Trong một lab nhỏ, hai database có thể nằm trên cùng một PostgreSQL container để giảm tài nguyên, nhưng cần nhận thức rằng đó chỉ là tối ưu môi trường học tập; không tương đương isolation của hai database clusters.

## 8. Tạo file môi trường local

Compose hỗ trợ nội suy biến từ shell environment và file .env mặc định. Tạo .env.example:

~~~dotenv
CATALOG_DB_PASSWORD=local-catalog-password
ORDER_DB_PASSWORD=local-order-password
RABBITMQ_PASSWORD=local-rabbit-password
~~~

Sao chép thành .env trên máy phát triển, rồi chỉnh các giá trị local:

~~~bash
cp .env.example .env
~~~

Trên PowerShell:

~~~powershell
Copy-Item .env.example .env
~~~

Thêm .env vào .gitignore:

~~~gitignore
.env
.env.*
!.env.example
target/
.idea/
.vscode/
*.log
~~~

Kiểm tra docker compose config để xem cấu hình sau khi nội suy. Lệnh này có thể hiển thị giá trị biến đã được thay thế; không chia sẻ output chứa secret.

### 8.1. Không nhầm .env với biến môi trường của container

.env chủ yếu được Compose dùng để nội suy file cấu hình. Biến chỉ xuất hiện trong .env không nhất thiết tự động được đưa vào container. Muốn container nhận giá trị, cần khai báo environment hoặc env_file trong service.

Ví dụ:

~~~yaml
services:
  catalog-service:
    env_file:
      - .env
~~~

Cách này đưa nhiều biến vào container, có thể cấp thừa các secret không liên quan. Với lab, nên cân nhắc khai báo rõ từng biến trong environment để thấy service nào cần giá trị nào.

### 8.2. Compose secrets trong môi trường local

Compose có hỗ trợ secrets được mount vào container theo cấu hình, nhưng cách lưu trữ và bảo vệ secret phụ thuộc môi trường triển khai. Với file-backed secrets local, file nguồn vẫn là file trên host; Compose không tự biến nó thành một secret manager production.

Không commit secret file. Trong môi trường thật, dùng secret manager hoặc nền tảng quản lý credentials phù hợp, có rotation, audit và least privilege.

### 8.3. Không dùng credential production cho lab

Dữ liệu local có thể bị xóa, dump, chia sẻ hoặc gửi vào issue. Chỉ dùng tài khoản giả lập với quyền giới hạn. Không kết nối local container với database production bằng cách sao chép mật khẩu thật vào .env.

## 9. Service discovery và DNS nội bộ

Compose tạo network cho các service. Container trên cùng network có thể tìm nhau bằng service name.

Trong ví dụ:

- Catalog Service kết nối catalog-db:5432.
- Order Service kết nối order-db:5432.
- Hai service kết nối RabbitMQ bằng rabbitmq:5672.
- Catalog kết nối Redis bằng redis:6379.

Tên catalog-db, rabbitmq, redis là DNS names nội bộ trong network Compose.

**Không dùng localhost để gọi container khác.** Bên trong catalog-service, localhost là chính container Catalog. Vì vậy:

~~~text
jdbc:postgresql://localhost:5432/catalog
~~~

thường là sai khi ứng dụng chạy trong container, trừ khi database thực sự chạy cùng container, một thiết kế không nên dùng cho topology này.

Cấu hình đúng:

~~~text
jdbc:postgresql://catalog-db:5432/catalog
~~~

### 9.1. Từ host tới container

Nếu Compose publish:

~~~yaml
ports:
  - "127.0.0.1:8081:8080"
~~~

thì:

- Host gọi http://localhost:8081.
- Container trong network gọi http://catalog-service:8080.
- Host port là 8081.
- Container port là 8080.

Hai port có thể khác nhau. Không nên cấu hình Spring Boot lắng nghe 8081 chỉ vì host mapping là 8081; ứng dụng trong container vẫn lắng nghe 8080 theo ví dụ.

### 9.2. Không publish database port nếu không cần

Nếu không khai báo ports cho catalog-db, host không thể truy cập trực tiếp database qua localhost:5432, nhưng các container cùng network vẫn có thể kết nối qua catalog-db:5432.

Khi cần dùng IDE/database client từ host, có thể tạm publish:

~~~yaml
ports:
  - "127.0.0.1:15432:5432"
~~~

Sau đó host dùng localhost:15432. Bind vào 127.0.0.1 để hạn chế lắng nghe trên interface mạng khác. Không publish DB port ra 0.0.0.0 theo mặc định.

## 10. Networks và phân vùng giao tiếp

Một network bridge mặc định đủ cho nhiều lab. Với hệ thống cần minh họa isolation, có thể tạo các network riêng:

~~~yaml
networks:
  catalog-net:
  order-net:
  messaging-net:
~~~

Service chỉ tham gia network cần thiết:

~~~yaml
services:
  catalog-service:
    networks:
      - catalog-net
      - messaging-net

  catalog-db:
    networks:
      - catalog-net

  order-service:
    networks:
      - order-net
      - messaging-net

  order-db:
    networks:
      - order-net

  rabbitmq:
    networks:
      - messaging-net
~~~

Với cách này, Order Service không trực tiếp nhìn thấy Catalog DB qua network. Nó chỉ giao tiếp với Catalog qua API/event nếu có network path và contract cho phép.

### 10.1. Network segmentation không thay thế authorization

Việc hai container không cùng network giúp giảm bề mặt kết nối, nhưng không thay thế authentication/authorization ở application hoặc database. Ai có quyền truy cập Docker daemon thường có khả năng rất lớn trên môi trường host; không coi network Compose là ranh giới bảo mật tuyệt đối.

### 10.2. Internal network

Compose có thể tạo network internal: true để hạn chế kết nối ra ngoài theo semantics của Docker network. Không bật mù nếu service cần tải dependency, gọi API bên ngoài hoặc gửi telemetry; hiểu rõ đường egress và DNS trước.

## 11. Volumes và dữ liệu persistent

Container có thể bị xóa và tạo lại. Dữ liệu trong writable layer của container không nên được coi là persistent storage.

Named volume:

~~~yaml
volumes:
  catalog-db-data:
~~~

Gắn vào PostgreSQL:

~~~yaml
services:
  catalog-db:
    volumes:
      - catalog-db-data:/var/lib/postgresql/data
~~~

Khi chạy docker compose down, named volume thường vẫn tồn tại. Khi tạo lại container, database có thể tiếp tục dùng dữ liệu đã lưu.

### 11.1. Named volume và bind mount

| Loại | Ví dụ | Phù hợp |
|---|---|---|
| Named volume | catalog-db-data:/var/lib/postgresql/data | Database, dữ liệu container cần giữ |
| Bind mount | ./catalog-service:/workspace | Source code, cấu hình dev |
| Anonymous volume | Docker tự tạo volume không tên rõ | Trường hợp đặc biệt, khó quản trị hơn |

Không mount toàn bộ thư mục source vào production container. Bind mount cho development có thể làm thay đổi code bên trong container mà không build image mới, nhưng cách này cần profile riêng.

### 11.2. Quyền sở hữu file

PostgreSQL/Redis có thể cần UID/GID cụ thể để ghi vào volume. Nếu volume được tạo từ một image khác hoặc bind mount host có quyền không phù hợp, container có thể báo permission denied.

Không giải quyết bằng cách chmod 777 toàn bộ thư mục. Kiểm tra user của container, ownership, mount path và cách Docker Desktop ánh xạ filesystem.

### 11.3. Backup và restore

Volume local vẫn có thể hỏng hoặc bị xóa. Nếu dữ liệu bài học quan trọng, export bằng công cụ database như pg_dump/pg_restore, ghi rõ phiên bản và kiểm tra restore. Không coi named volume là backup.

## 12. depends_on: thứ tự khởi động và readiness

depends_on cho biết một service phụ thuộc vào service khác trong lifecycle Compose.

Ví dụ:

~~~yaml
services:
  catalog-service:
    depends_on:
      catalog-db:
        condition: service_healthy
~~~

Với long-form condition service_healthy, Compose có thể chờ healthcheck của dependency đạt trạng thái healthy trước khi tạo/khởi động service phụ thuộc theo quy trình Compose.

Nhưng cần phân biệt:

- Container đã được tạo.
- Process đã chạy.
- Port đã mở.
- Database đã nhận kết nối.
- Schema đã migrate.
- Application đã sẵn sàng phục vụ business request.

depends_on dạng đơn giản chỉ điều khiển thứ tự start; nó không đảm bảo dependency hoạt động ổn định sau đó. Healthcheck cũng chỉ kiểm tra điều mà command được cấu hình kiểm tra.

### 12.1. Healthcheck database

PostgreSQL:

~~~yaml
healthcheck:
  test: ["CMD-SHELL", "pg_isready -U catalog -d catalog"]
  interval: 5s
  timeout: 3s
  retries: 10
  start_period: 10s
~~~

pg_isready kiểm tra khả năng nhận kết nối của PostgreSQL; nó không xác minh schema, quyền ứng dụng hay migration đã hoàn tất.

Redis:

~~~yaml
healthcheck:
  test: ["CMD", "redis-cli", "ping"]
  interval: 5s
  timeout: 3s
  retries: 10
~~~

RabbitMQ:

~~~yaml
healthcheck:
  test: ["CMD", "rabbitmq-diagnostics", "-q", "ping"]
  interval: 10s
  timeout: 5s
  retries: 10
  start_period: 20s
~~~

### 12.2. Healthcheck ứng dụng

Spring Boot có thể expose:

- /actuator/health/liveness
- /actuator/health/readiness

Ứng dụng phải có Actuator và cấu hình probe tương ứng. Container image cần có công cụ mà healthcheck command sử dụng, ví dụ wget hoặc curl. Nếu không có, command sẽ fail dù ứng dụng vẫn chạy.

Readiness của app không nên phụ thuộc vô điều kiện vào tất cả hệ thống bên ngoài. Nếu RabbitMQ outage làm readiness fail cho toàn bộ service, routing có thể loại hết instance trong khi service vẫn có thể phục vụ một số endpoint read-only. Chọn semantics theo khả năng phục vụ thực tế.

### 12.3. Ứng dụng vẫn cần retry reconnect

Compose có thể khởi động dependency trước, nhưng database/broker vẫn có thể restart sau đó. Spring Boot service cần pool/client có reconnect, timeout và error handling. Không dựa vào depends_on như cơ chế resilience runtime.

## 13. Cấu hình Spring Boot chạy trong container

Spring Boot hỗ trợ externalized configuration, trong đó biến môi trường có thể map vào properties.

Ví dụ application.yaml:

~~~yaml
spring:
  application:
    name: catalog-service
  datasource:
    url: ${SPRING_DATASOURCE_URL}
    username: ${SPRING_DATASOURCE_USERNAME}
    password: ${SPRING_DATASOURCE_PASSWORD}
  data:
    redis:
      host: ${SPRING_DATA_REDIS_HOST:localhost}
      port: ${SPRING_DATA_REDIS_PORT:6379}
  rabbitmq:
    host: ${SPRING_RABBITMQ_HOST:localhost}
    port: ${SPRING_RABBITMQ_PORT:5672}
    username: ${SPRING_RABBITMQ_USERNAME:guest}
    password: ${SPRING_RABBITMQ_PASSWORD:guest}

server:
  port: ${SERVER_PORT:8080}
~~~

Đây là ví dụ mapping cho Spring Boot. Trong production, không nên dùng fallback localhost, guest hoặc credential yếu; có thể yêu cầu biến bắt buộc và fail fast. Default ở trên nhằm giải thích property binding, không phải cấu hình bảo mật khuyến nghị.

### 13.1. Tên biến môi trường và property binding

| Spring property | Environment variable |
|---|---|
| server.port | SERVER_PORT |
| spring.datasource.url | SPRING_DATASOURCE_URL |
| spring.datasource.username | SPRING_DATASOURCE_USERNAME |
| spring.data.redis.host | SPRING_DATA_REDIS_HOST |
| spring.rabbitmq.host | SPRING_RABBITMQ_HOST |
| management.endpoints.web.exposure.include | MANAGEMENT_ENDPOINTS_WEB_EXPOSURE_INCLUDE |

Nếu property path hoặc Spring Boot version khác, kiểm tra tài liệu đúng version. Tránh đặt một biến tên gần đúng nhưng framework không bind, khiến ứng dụng âm thầm dùng default.

### 13.2. Local IDE và container có hostname khác

Khi chạy Spring Boot từ IDE trên host:

~~~text
SPRING_DATASOURCE_URL=jdbc:postgresql://localhost:15432/catalog
SPRING_DATA_REDIS_HOST=localhost
SPRING_RABBITMQ_HOST=localhost
~~~

Khi chạy Spring Boot trong Compose:

~~~text
SPRING_DATASOURCE_URL=jdbc:postgresql://catalog-db:5432/catalog
SPRING_DATA_REDIS_HOST=redis
SPRING_RABBITMQ_HOST=rabbitmq
~~~

Hai bộ cấu hình khác nhau vì network namespace khác nhau. Có thể dùng Spring profiles hoặc environment overrides, nhưng không nên hardcode một hostname dùng cho cả hai trường hợp.

## 14. Dockerfile cho Spring Boot service

Một multi-stage Dockerfile mẫu:

~~~dockerfile
FROM maven:3.9.9-eclipse-temurin-21 AS build
WORKDIR /workspace

COPY pom.xml .
COPY .mvn .mvn
COPY mvnw .
RUN ./mvnw -B -q dependency:go-offline

COPY src src
RUN ./mvnw -B -DskipTests package

FROM eclipse-temurin:21-jre-alpine
WORKDIR /app

RUN addgroup -S app && adduser -S app -G app
COPY --from=build /workspace/target/*.jar /app/app.jar

USER app
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

Đây là ví dụ học tập. Cần xác minh các tag image tồn tại và tương thích; pin digest nếu yêu cầu reproducible build. Có thể thay cách cài user theo base image. Build stage với DskipTests chỉ để minh họa tạo artifact; test bắt buộc phải chạy ở CI trước khi build/release.

### 14.1. Build context và .dockerignore

Ví dụ .dockerignore:

~~~text
.git
.idea
.vscode
.env
.env.*
target
build
*.log
.DS_Store
~~~

Không gửi .env, source history hoặc build output không cần thiết vào Docker build context. Build context nhỏ hơn giúp build nhanh và giảm nguy cơ secret bị đưa vào image layer.

### 14.2. Image cho development và production

Development có thể cần source bind mount, debugger port hoặc hot reload. Production nên chạy artifact đã build, không mount source từ host. Tách Compose override/profile thay vì làm một container image vừa debug vừa production.

## 15. Profiles: bật thành phần khi cần

Compose profiles giúp khai báo service tùy chọn. Ví dụ Jaeger chỉ chạy khi học distributed tracing:

~~~yaml
services:
  jaeger:
    image: jaegertracing/all-in-one:1.62
    profiles:
      - observability
    ports:
      - "127.0.0.1:16686:16686"
~~~

Khởi động stack cơ bản:

~~~bash
docker compose up -d
~~~

Bật thêm observability:

~~~bash
docker compose --profile observability up -d
~~~

Profiles phù hợp với:

- UI quản trị local.
- Tracing backend.
- Mock provider.
- Load generator.
- Migration utility.
- Debug tools.

Không nên đặt database bắt buộc của ứng dụng vào profile mà người học thường quên bật. Profile là cơ chế lựa chọn service, không phải dependency management thay cho depends_on.

## 16. Khởi động môi trường

Sau khi tạo .env và các Dockerfiles, kiểm tra cấu hình:

~~~bash
docker compose config
~~~

Lệnh này render cấu hình cuối sau khi nội suy và merge các file. Cẩn thận khi chia sẻ output nếu có secrets.

Build và khởi động:

~~~bash
docker compose up -d --build
~~~

Xem trạng thái:

~~~bash
docker compose ps
~~~

Theo dõi logs:

~~~bash
docker compose logs -f
~~~

Chỉ xem logs của Catalog:

~~~bash
docker compose logs -f catalog-service
~~~

Xem 100 dòng gần nhất:

~~~bash
docker compose logs --tail=100 order-service
~~~

Khi các service đã ready, gọi từ host:

~~~bash
curl http://localhost:8081/actuator/health/readiness
curl http://localhost:8082/actuator/health/readiness
~~~

Các endpoint trên chỉ tồn tại nếu service bật Actuator và expose đúng path/port. Có thể thay bằng API health route của ứng dụng.

### 16.1. Up, start và restart

- up tạo/cập nhật resource và khởi động service.
- start khởi động container đã tồn tại nhưng đang dừng.
- restart restart container hiện tại; không tự build image mới.
- build tạo image từ Dockerfile.
- pull tải image được tham chiếu từ registry.
- stop dừng service nhưng giữ container.
- down dừng và xóa container/network của project theo mặc định; named volumes thường vẫn được giữ nếu không chỉ định xóa.

Hiểu khác biệt này giúp tránh tưởng restart đã nhận source code vừa sửa hoặc tưởng down đã xóa toàn bộ dữ liệu.

## 17. Các lệnh vận hành thường dùng

| Nhu cầu | Lệnh |
|---|---|
| Xem service | docker compose ps |
| Xem logs tất cả | docker compose logs -f |
| Xem logs một service | docker compose logs -f catalog-service |
| Khởi động một service và dependencies | docker compose up -d catalog-service |
| Rebuild một image | docker compose build catalog-service |
| Recreate một service | docker compose up -d --no-deps --force-recreate catalog-service |
| Chạy lệnh trong container | docker compose exec catalog-service sh |
| Chạy one-off command | docker compose run --rm catalog-service ... |
| Xem resource usage | docker stats |
| Xem network | docker network ls |
| Xem volume | docker volume ls |
| Kiểm tra cấu hình | docker compose config |
| Dừng project | docker compose down |

Lệnh up -d --no-deps --force-recreate chỉ nên dùng khi hiểu rõ dependency đã sẵn sàng và service mới không cần khởi động lại các thành phần khác. Không dùng nó như một cách sửa mọi lỗi.

### 17.1. Exec và run

exec chạy lệnh bên trong container đang chạy:

~~~bash
docker compose exec catalog-db psql -U catalog -d catalog
~~~

run tạo container one-off cho một service, thường dùng migration hoặc task:

~~~bash
docker compose run --rm catalog-service java -version
~~~

Lệnh thực tế phụ thuộc image và entrypoint. Nếu entrypoint là java -jar, cần override command/entrypoint đúng cách khi muốn chạy shell hoặc công cụ khác.

### 17.2. Không chạy mọi service ở chế độ detached khi đang học debug

Khi mới dựng môi trường, chạy docker compose up có thể hữu ích vì logs hiển thị ngay trong terminal. Khi đã ổn định, dùng -d rồi theo dõi từng service. Nhấn Ctrl+C ở foreground sẽ dừng project theo semantics Compose; hãy đọc thông báo và trạng thái trước khi tiếp tục.

## 18. Quan sát log và luồng request nhiều service

Một request tạo order có thể đi qua:

~~~text
Client
  |
  v
Order Service
  |
  +----> Order DB
  |
  +----> RabbitMQ: OrderCreated
                 |
                 v
          Catalog/Notification consumer
~~~

Khi request thất bại, không chỉ xem log Order Service. Cần xác định:

- Request đã tới container chưa?
- Service có kết nối được database không?
- Transaction commit hay rollback?
- Message có publish vào broker không?
- Consumer có nhận message không?
- Consumer có xử lý thành công hay vào retry/DLQ?
- Response trả về trước hay sau khi công việc async hoàn tất?

Nên gắn correlation ID/trace context xuyên HTTP và message. Với một lab, có thể bắt đầu bằng request ID trong logs, sau đó tích hợp OpenTelemetry để xem distributed trace.

### 18.1. Structured logging

Log có cấu trúc giúp tìm theo service, level, operation và correlation ID. Ví dụ:

~~~json
{
  "timestamp": "2026-11-12T07:30:00Z",
  "level": "INFO",
  "service": "order-service",
  "operation": "order.create",
  "traceId": "example-trace",
  "orderId": "local-order-1001",
  "message": "Order persisted"
}
~~~

Đây là log giả lập. Không đưa access token, password, cookie hoặc dữ liệu cá nhân nhạy cảm vào log. ID nghiệp vụ trong log cần tuân theo chính sách dữ liệu của môi trường.

## 19. Kiểm tra network từ trong container

Khi app không kết nối được database, có thể kiểm tra DNS và TCP từ chính container:

~~~bash
docker compose exec catalog-service sh
~~~

Sau đó dùng công cụ có sẵn trong image (ví dụ getent, nslookup, nc, wget) để kiểm tra:

~~~text
catalog-db resolves to an address?
Can TCP connect to catalog-db:5432?
Does Redis resolve as redis?
Can the application reach rabbitmq:5672?
~~~

Không phải runtime image nào cũng có shell hoặc network utilities. Với image tối giản, có thể chạy một debug container trên cùng network:

~~~bash
docker run --rm -it --network java-microservices-lab_lab-network busybox:1.36 sh
~~~

Tên network thực tế phụ thuộc Compose project name và network key. Xem bằng:

~~~bash
docker network ls
docker network inspect <network-name>
~~~

Không cài thêm debug tools vào production image chỉ để xử lý một sự cố nhất thời. Dùng debug container có kiểm soát và xóa sau khi hoàn tất.

## 20. Healthcheck không thay thế test nghiệp vụ

Database healthy chỉ cho biết healthcheck của nó thành công. Điều đó không chứng minh:

- User ứng dụng có quyền login.
- Database đã có schema/migration.
- Index đã tồn tại.
- Seed data đã được nạp.
- Một query nghiệp vụ chạy được.
- Service có thể phục vụ đúng dữ liệu.

Một chuỗi readiness thực tế:

~~~text
Container running
    |
    v
Database accepts connections
    |
    v
Migration completed
    |
    v
Spring application ready
    |
    v
Smoke test business API passes
~~~

Có thể tách startup migration thành một job/container riêng nếu cần, hoặc để Flyway chạy trong app startup với quy tắc lock/concurrency phù hợp. Tránh để nhiều replica cùng chạy migration không được thiết kế cho concurrency.

## 21. Database initialization và migrations

PostgreSQL official image hỗ trợ script khởi tạo trong thư mục /docker-entrypoint-initdb.d khi data directory được tạo lần đầu. Ví dụ:

~~~yaml
services:
  catalog-db:
    image: postgres:16.4
    volumes:
      - catalog-db-data:/var/lib/postgresql/data
      - ./infra/postgres/catalog-init:/docker-entrypoint-initdb.d:ro
~~~

Các script này không chạy lại mỗi lần container restart nếu volume đã được khởi tạo. Thay file init SQL sau khi volume tồn tại không tự áp dụng thay đổi.

Với schema ứng dụng thay đổi theo thời gian, nên dùng migration tool:

- Flyway: versioned SQL migrations.
- Liquibase: changelog có nhiều format.
- Migration job riêng hoặc app startup tùy chiến lược.
- CI test migration từ schema cũ sang schema mới.

Không sửa schema thủ công trong database local rồi quên đưa migration vào Git; người khác clone repository sẽ không tái tạo được trạng thái đó.

### 21.1. Expand-and-contract khi có nhiều version

Ngay cả trong local lab, có thể học cách migration tương thích:

1. Thêm cột mới nullable.
2. Deploy code đọc được cũ và mới.
3. Backfill dữ liệu.
4. Chuyển write/read logic.
5. Sau khi không còn code cũ, xóa cột cũ ở migration riêng.

Điều này phản ánh tình huống production rolling update, nơi hai phiên bản ứng dụng có thể cùng chạy.

## 22. RabbitMQ trong môi trường học tập

RabbitMQ giúp minh họa asynchronous communication:

~~~text
Order Service
   |
   | publish OrderCreated
   v
Exchange
   |
   v
Queue
   |
   v
Consumer (Notification / Analytics)
~~~

Trong Compose, container rabbitmq có thể mở:

- 5672: AMQP port nội bộ cho ứng dụng.
- 15672: management UI, nếu dùng image management.

Nếu mapping management UI ra host, bind 127.0.0.1 trong lab và dùng credential riêng. Không public management UI ra mạng không tin cậy.

### 22.1. Queue, exchange và binding

- **Exchange:** nhận message và định tuyến theo loại exchange/routing key.
- **Queue:** giữ message chờ consumer.
- **Binding:** liên kết queue với exchange và routing rule.
- **Consumer:** nhận và xử lý message.
- **Ack/Nack:** xác nhận đã xử lý hoặc yêu cầu xử lý lại tùy semantics.
- **DLQ:** nơi đưa message không thể xử lý sau chính sách retry phù hợp.

Compose chỉ khởi động broker. Ứng dụng cần khai báo exchange/queue/binding bằng configuration hoặc provisioning script có thể tái tạo.

### 22.2. Idempotency và redelivery

Consumer có thể nhận cùng message nhiều lần nếu xử lý xong nhưng crash trước ack hoặc broker redeliver. Side effect phải idempotent hoặc có deduplication. Không giả định mỗi message chỉ được giao đúng một lần.

### 22.3. Queue không phải database

Không dùng queue làm nơi truy vấn trạng thái nghiệp vụ lâu dài. Nếu người dùng cần xem trạng thái order, lưu state trong Order Service database; message chỉ truyền sự kiện/chỉ thị theo contract.

## 23. Redis trong môi trường học tập

Redis có thể dùng cho:

- Cache dữ liệu Catalog.
- Session store khi thiết kế phù hợp.
- Rate limiting.
- Distributed coordination, cần hiểu semantics.
- Temporary state/short-lived data.

Ví dụ key cache:

~~~text
catalog:item:sku-123
catalog:category:books:page:1
~~~

Key nên có namespace/version và tenant scope nếu dữ liệu phân vùng theo tenant. TTL và invalidation cần được định nghĩa.

Redis local có thể restart hoặc mất dữ liệu tùy persistence configuration. Không dùng Redis như nguồn sự thật duy nhất cho nghiệp vụ quan trọng nếu chưa thiết kế durability, backup, failover và consistency.

### 23.1. Cache invalidation

Khi Catalog cập nhật sản phẩm, cần invalidation hoặc update cache theo event/transaction contract. Một bài học tốt là mô phỏng:

1. GET item lần đầu, cache miss.
2. GET lần hai, cache hit.
3. PATCH item.
4. Cache invalidated/updated.
5. GET lại trả dữ liệu mới theo freshness contract.

Không để cache che lỗi vì local volume giữ dữ liệu cũ qua nhiều lần restart.

## 24. Service-to-service HTTP

Order Service có thể gọi Catalog API để xác nhận snapshot thông tin sản phẩm theo contract. Trong Compose, URL nội bộ:

~~~text
http://catalog-service:8080
~~~

Không dùng http://localhost:8081 từ bên trong Order Service; localhost trỏ tới container Order.

Cấu hình Spring:

~~~yaml
app:
  clients:
    catalog:
      base-url: ${CATALOG_SERVICE_URL:http://catalog-service:8080}
      connect-timeout: 500ms
      response-timeout: 2s
~~~

Giá trị timeout chỉ là ví dụ. Ứng dụng phải có HTTP client cấu hình timeout thật; chỉ khai báo YAML không tự áp dụng nếu code không bind/use property.

Cần kiểm tra:

- Timeout connect/read/overall deadline.
- Error mapping.
- Retry chỉ với operation an toàn.
- Circuit breaker/bulkhead khi phù hợp.
- Trace context propagation.
- Authorization service-to-service.
- API contract compatibility.

## 25. Tách cấu hình theo môi trường

Một project có thể dùng:

- compose.yaml: cấu hình chung.
- compose.dev.yaml: bind mounts, debug ports, hot reload.
- compose.observability.yaml: collector, trace backend, metrics.
- .env: giá trị local không commit.

Chạy nhiều file:

~~~bash
docker compose -f compose.yaml -f compose.dev.yaml up -d
~~~

File được merge theo thứ tự; file sau có thể bổ sung hoặc ghi đè cấu hình. Cần kiểm tra kết quả bằng docker compose config để tránh nghĩ override hoạt động theo cách khác.

Không tạo hàng chục file override mà không có README mô tả thứ tự và mục đích.

### 25.1. Profiles hay nhiều Compose files?

- Dùng profiles khi bật/tắt một nhóm service tùy chọn.
- Dùng override file khi cùng service cần cấu hình khác theo môi trường/dev workflow.
- Dùng file riêng cho topology khác biệt đáng kể nếu việc merge trở nên khó hiểu.

Một project nhỏ thường chỉ cần một file chính và một override dev.

## 26. Hot reload và phát triển từ IDE

Có hai cách:

### Cách A — Chạy app trong container

Compose build image và chạy service. Phù hợp để học network/service discovery giống topology container.

Ưu điểm: môi trường gần với container runtime. Hạn chế: build/rebuild mỗi lần thay đổi có thể chậm, debug cần remote debugger.

### Cách B — Chạy app trên host, dependency trong Compose

Khởi động:

~~~bash
docker compose up -d catalog-db order-db redis rabbitmq
~~~

Sau đó chạy Spring Boot từ IDE với cấu hình hostname/port của host, ví dụ database localhost:15432 nếu đã publish port tương ứng.

Ưu điểm: debug breakpoint, hot reload và test code nhanh. Hạn chế: app không nằm trong network namespace Compose, cần dùng host ports và cấu hình khác.

### 26.1. Bind mount source

Một dev override có thể mount source/build artifacts, nhưng cách hot reload phụ thuộc framework/build tool. Không mặc định bind mount toàn bộ repository vào production container.

### 26.2. Remote debugging

Nếu mở debug port, bind vào localhost và chỉ dùng ở local. Không mở debugger port public hoặc để JDWP không xác thực trên production network.

## 27. Kiểm tra môi trường bằng smoke tests

Sau khi stack khởi động, chạy một chuỗi kiểm tra ngắn:

1. Catalog readiness trả thành công.
2. Order readiness trả thành công.
3. Catalog có thể tạo hoặc đọc một sản phẩm mẫu.
4. Order API có thể tạo order hợp lệ.
5. Order record được lưu trong Order DB.
6. Event được publish tới RabbitMQ.
7. Consumer nhận message và hoàn thành side effect mẫu.
8. Cache hit/miss hoạt động theo thiết kế.
9. Logs có correlation ID.
10. Khi một dependency dừng, lỗi được trả về có kiểm soát.

Ví dụ shell smoke test:

~~~bash
#!/usr/bin/env bash
set -euo pipefail

curl --fail --silent http://localhost:8081/actuator/health/readiness
curl --fail --silent http://localhost:8082/actuator/health/readiness

echo "Local services are responding"
~~~

Đây chỉ là smoke test readiness, chưa kiểm tra business workflow. Cần thêm request phù hợp với API thực và xác nhận kết quả qua service owner, database hoặc event consumer.

### 27.1. Chạy test trong container

~~~bash
docker compose exec catalog-service java -version
docker compose exec catalog-db pg_isready -U catalog -d catalog
~~~

Các lệnh chỉ hữu ích nếu image có executable tương ứng. Với test suite, thường tốt hơn chạy Maven/Gradle test từ CI hoặc one-off container, thay vì đưa toàn bộ test tooling vào runtime image.

## 28. Integration tests với Testcontainers

Docker Compose phù hợp dựng cả môi trường cho người học. Trong automated tests, Testcontainers có thể khởi tạo PostgreSQL, Redis hoặc broker tạm thời, rồi tự dọn container sau test.

Lợi ích:

- Mỗi test suite có dependency version được khai báo.
- Không phải giả định máy developer đang có DB ở port cố định.
- Có thể test với database thật thay vì H2/in-memory có semantics khác.
- CI có thể chạy environment tương tự local.
- Container lifecycle được quản lý theo test.

Không cần chọn Compose hay Testcontainers độc quyền. Compose phù hợp chạy stack tương tác dài hạn; Testcontainers phù hợp kiểm thử tự động và isolation. Một project có thể dùng cả hai với image versions đồng bộ.

### 28.1. Test schema/migrations

Integration test nên khởi động DB trống, chạy migration và xác nhận query/repository. Nếu chỉ chạy trên volume đã tồn tại nhiều tuần, test có thể bỏ qua migration mới hoặc dựa vào dữ liệu thủ công.

## 29. Debug một số tình huống thường gặp

### 29.1. Port đã được sử dụng

Triệu chứng: Compose báo bind port failed.

Cách xử lý:

- Kiểm tra process đang dùng host port.
- Đổi host port mapping, giữ container port.
- Dừng ứng dụng local không cần thiết.
- Xác nhận không có Compose project khác dùng cùng port.

Ví dụ đổi 8081:8080 thành 18081:8080; host gọi localhost:18081, container vẫn nghe 8080.

### 29.2. Service không kết nối được database

Kiểm tra:

- App có dùng catalog-db thay vì localhost không?
- Hai container có cùng network không?
- Port nội bộ có đúng 5432 không?
- DB healthcheck đã healthy chưa?
- User/password/database có khớp?
- Spring property có bind đúng?
- Firewall hoặc Docker context có vấn đề?

### 29.3. Database khởi động lại nhưng app vẫn lỗi

depends_on chỉ hỗ trợ startup order. App cần reconnect pool, retry có giới hạn và timeout. Xem logs DB, logs app, health status và connection pool.

### 29.4. Container healthy nhưng endpoint trả lỗi

Healthcheck có thể chỉ kiểm tra process hoặc endpoint kỹ thuật. Kiểm tra migration, authorization, data, downstream dependencies và business endpoint. Không coi healthy là chứng minh toàn bộ workflow đúng.

### 29.5. Sửa source nhưng container vẫn chạy code cũ

docker compose restart không build lại image. Dùng docker compose up -d --build service hoặc build rồi recreate theo cách phù hợp. Kiểm tra image ID và version endpoint để xác nhận artifact mới đang chạy.

### 29.6. Database vẫn còn dữ liệu cũ sau khi rebuild

Named volume tồn tại qua container rebuild. Nếu cần dữ liệu sạch, phải hiểu volume nào thuộc service nào và chỉ xóa volume local tương ứng sau khi chắc chắn không cần dữ liệu.

### 29.7. Migration chạy hai lần hoặc app khởi động quá sớm

Dùng migration tool có versioning/locking và cấu hình startup order/one-off job hợp lý. Healthcheck DB không đồng nghĩa migration hoàn tất.

### 29.8. RabbitMQ consumer không nhận message

Kiểm tra:

- Exchange, queue, binding và routing key.
- Consumer group/channel/connection.
- Ack/Nack và prefetch.
- Message có vào queue không?
- Consumer có lỗi deserialize hoặc authorization?
- Message có vào DLQ không?
- App có kết nối đúng hostname rabbitmq và port 5672?

### 29.9. Redis trả dữ liệu cũ

Kiểm tra TTL, invalidation, key namespace, volume persistence và event propagation. Xóa key local chỉ để debug sau khi biết rõ side effect; không dùng FLUSHALL nếu Redis được dùng chung bởi nhiều bài học hoặc project.

### 29.10. Máy thiếu tài nguyên

Kiểm tra docker stats, số container, memory usage, disk usage, build cache và image/volume không còn cần. Giảm số service bật đồng thời hoặc cấu hình resource hợp lý. Không giảm memory quá thấp khiến PostgreSQL/RabbitMQ restart liên tục.

## 30. Quan sát tài nguyên và log

Các lệnh hữu ích:

~~~bash
docker stats
docker compose top
docker compose events
docker system df
~~~

- docker stats: CPU, memory, network và block I/O của container.
- docker compose top: process đang chạy trong service containers.
- docker compose events: sự kiện lifecycle của project.
- docker system df: dung lượng image/container/volume/build cache.

docker system prune có thể xóa resource không còn dùng; đọc kỹ phạm vi trước khi thực hiện. docker system prune --volumes có thể xóa volume không còn được container tham chiếu và làm mất dữ liệu local. Không chạy lệnh cleanup rộng như phản xạ khi chỉ một service lỗi.

## 31. Resource limits và khả năng tái lập

Một môi trường học tập nên cân nhắc giới hạn tài nguyên để không chiếm toàn bộ laptop. Tuy nhiên cú pháp và semantics resource limits của Compose phụ thuộc phiên bản/runtime và cách khai báo. Xác minh bằng docker compose config và đo docker stats; không giả định mọi trường trong deploy.resources luôn có hiệu lực giống nhau trên mọi môi trường Compose.

Những điểm cần ghi trong README dự án:

- JDK/Java version.
- Docker Engine/Desktop và Compose version.
- Image tags/digests.
- Port mapping.
- RAM/CPU tối thiểu ước tính.
- Volume nào giữ dữ liệu.
- Profile nào bật service tùy chọn.
- Cách seed/reset dữ liệu.
- Lệnh smoke tests.
- Cách dọn dẹp.
- Các dependency external/mock.

Một file Compose đúng nhưng không ghi rõ prerequisites vẫn khó dùng lại giữa các máy.

## 32. Bảo mật trong môi trường local

Dù chỉ học tập, nên giữ thói quen tốt:

- Chỉ bind port cần thiết vào 127.0.0.1.
- Không commit .env hoặc secret files.
- Không sử dụng credential production.
- Dùng non-root user cho app container nếu phù hợp.
- Pin image versions, cập nhật security patches.
- Không mount Docker socket vào app containers.
- Không expose management UI nếu không cần.
- Không lưu PII thật trong sample data.
- Giới hạn quyền database user theo service.
- Không mở debug port ra mạng.
- Không tắt TLS validation trong code dùng chung chỉ để local dễ chạy.
- Không cho container chạy privileged nếu không có lý do rõ.

Docker daemon có quyền mạnh trên host. Việc một container được cấp quyền truy cập /var/run/docker.sock thường gần tương đương trao quyền điều khiển Docker host; không đưa mount này vào service template thông thường.

### 32.1. Local secret khác production secret

File .env local giúp người học bắt đầu nhanh nhưng không phải secret management hoàn chỉnh. Trong production, cần workload identity, secret manager, rotation, audit, encryption và quyền tối thiểu theo nền tảng.

### 32.2. Sample data

Dùng dữ liệu giả lập, không copy database production về laptop chỉ để chạy demo. Nếu cần dataset gần thực tế, hãy dùng data masking/anonymization theo chính sách và kiểm tra khả năng tái nhận diện.

## 33. Compose không thay thế Kubernetes hoặc production platform

Docker Compose rất phù hợp local development, demo và integration environment nhỏ. Nó không tự cung cấp đầy đủ những năng lực production như:

- Scheduler phân phối workload qua nhiều node.
- High availability và failover.
- Autoscaling theo metrics.
- Service discovery/load balancing ở quy mô cluster.
- Network policies và identity controls ở cấp tổ chức.
- Progressive delivery/canary orchestration.
- Centralized secret lifecycle.
- Resource quotas và multi-tenant isolation.
- Backup/disaster recovery có mục tiêu.
- Multi-zone topology và disruption management.

Có thể triển khai Compose trên một máy chủ trong một số tình huống giới hạn, nhưng không nên suy ra rằng local stack chạy tốt thì đã đủ cho production. Khi hệ thống cần nhiều node, nhiều team, HA và governance, hãy dùng nền tảng container orchestration phù hợp.

### 33.1. Những gì nên giống production và những gì không cần giống

Nên giữ giống về contract, database engine, event semantics, auth behavior và cách đo observability nếu có thể. Không nhất thiết local phải giống production về số node, replica, TLS topology hoặc HA, nhưng mọi khác biệt quan trọng cần được document.

## 34. Dọn dẹp môi trường an toàn

Dừng và xóa container/network của project:

~~~bash
docker compose down
~~~

Named volumes thường vẫn được giữ.

Nếu muốn xóa cả volume của project để reset database local:

~~~bash
docker compose down -v
~~~

**Lệnh down -v xóa named volumes thuộc project và có thể làm mất toàn bộ dữ liệu local trong đó.** Chỉ dùng khi đã chắc chắn không cần dữ liệu. Với volume external, semantics khác; không giả định Compose sẽ xóa chúng.

### 34.1. Xóa một service hay một volume cụ thể

Trước khi xóa, xem tên volume và project:

~~~bash
docker volume ls
docker compose config
~~~

Không xóa volume dựa trên tên đoán. Nếu cần giữ catalog nhưng reset order, xác định volume mapping chính xác rồi xử lý theo lệnh Docker có phạm vi cụ thể.

### 34.2. Giữ dữ liệu hay reset?

Nên có hai thao tác rõ trong tài liệu dự án:

- Stop/start: dừng và chạy lại container, giữ data.
- Reset lab: xóa dữ liệu local được chọn, seed lại từ đầu.

Không gộp hai thao tác thành một lệnh cleanup mơ hồ.

## 35. Ví dụ workflow học một luồng nghiệp vụ

Một bài thực hành có thể là tạo Order và phát event:

1. Khởi động catalog-db, order-db, redis, rabbitmq.
2. Khởi động Catalog Service và tạo sản phẩm mẫu.
3. Khởi động Order Service.
4. Gọi API tạo order với một SKU hợp lệ.
5. Order Service kiểm tra thông tin sản phẩm qua Catalog API hoặc snapshot theo contract.
6. Order Service ghi order vào order-db.
7. Order Service phát OrderCreated event.
8. Consumer nhận event và thực hiện side effect mẫu.
9. Xem message/queue trên RabbitMQ Management UI.
10. Theo dõi logs theo correlation ID.
11. Dừng RabbitMQ trong lúc tạo một order mới để quan sát error handling.
12. Khởi động lại RabbitMQ và xem retry/recovery theo thiết kế.
13. Xác nhận order không bị tạo trùng.
14. Dừng và chạy lại Compose, xác nhận database volume giữ dữ liệu.
15. Reset lab có chủ đích và xác nhận seed data được nạp lại.

Luồng này dạy service discovery, data ownership, synchronous call, asynchronous event, persistence, retry, idempotency và observability trong cùng một môi trường.

## 36. Mẫu README cho một môi trường Compose trong repository

~~~markdown
# Java Microservices Lab

## Prerequisites
- Docker Engine/Desktop:
- Docker Compose:
- Available ports:
- Required RAM/disk:

## Services
| Service | Host URL/Port | Internal address | Data |
|---|---|---|---|
| Catalog API | localhost:8081 | catalog-service:8080 | catalog-db |
| Order API | localhost:8082 | order-service:8080 | order-db |
| RabbitMQ UI | localhost:15672 | rabbitmq:15672 | rabbitmq-data |

## Setup
1. Copy .env.example to .env.
2. Set local-only passwords.
3. Run docker compose config.
4. Run docker compose up -d --build.
5. Wait for required services to become healthy.

## Useful commands
- docker compose ps
- docker compose logs -f SERVICE
- docker compose exec SERVICE sh
- docker compose down

## Data lifecycle
- Named volumes:
- Seed data:
- Backup/reset instructions:

## Smoke tests
- Catalog readiness:
- Order readiness:
- Create order:
- Verify event:

## Troubleshooting
- Port conflict:
- Database connection:
- Broker connection:
- Migration:
- Stale volume:

## Security
- .env is not committed.
- No production credentials or production data.
- Local management ports bind to loopback.
~~~

Một README tốt cho lab giúp người mới tự xử lý vấn đề thường gặp mà không phải hỏi lại người tạo môi trường.

## 37. Bài tập thực hành

### Bài 1 — Hostname

Catalog Service chạy trong container nhưng JDBC URL là jdbc:postgresql://localhost:5432/catalog. PostgreSQL cũng là container riêng.

**Câu hỏi:** Vì sao kết nối thất bại?

**Đáp án:** localhost bên trong Catalog Service là chính container đó. Dùng catalog-db:5432 nếu hai service cùng network Compose.

### Bài 2 — Port mapping

Compose khai báo 127.0.0.1:18081:8080. Spring Boot lắng nghe 8080 trong container.

**Câu hỏi:** Host và container gọi port nào?

**Đáp án:** Host gọi localhost:18081; container khác gọi service DNS và port 8080.

### Bài 3 — depends_on

Order Service có depends_on: rabbitmq, nhưng startup đôi khi báo connection refused.

**Câu hỏi:** Vì sao?

**Đáp án:** Dạng ngắn chỉ sắp thứ tự start, không chờ broker thật sự ready. Cần healthcheck + condition service_healthy, đồng thời app vẫn phải reconnect khi dependency restart.

### Bài 4 — Persistence

Chạy docker compose down, sau đó up lại; dữ liệu PostgreSQL vẫn còn.

**Câu hỏi:** Dữ liệu nằm ở đâu?

**Đáp án:** Trong named volume được gắn vào data directory của PostgreSQL. Container được tạo lại nhưng volume còn tồn tại.

### Bài 5 — Rebuild

Sửa code Java nhưng chạy docker compose restart catalog-service; endpoint vẫn trả logic cũ.

**Câu hỏi:** Vì sao?

**Đáp án:** Restart không build image mới. Cần rebuild image và recreate container bằng docker compose up -d --build catalog-service hoặc quy trình tương đương.

### Bài 6 — Healthcheck

PostgreSQL báo healthy nhưng app startup fail vì relation products không tồn tại.

**Câu hỏi:** Healthcheck đã chứng minh điều gì?

**Đáp án:** Nó chỉ chứng minh pg_isready thành công; không chứng minh schema/migration đã chạy.

### Bài 7 — Secret

Một developer commit .env có password dùng chung cho team.

**Câu hỏi:** Rủi ro và cách xử lý?

**Đáp án:** Credential có thể lộ qua Git history và artifacts. Thu hồi/rotate, loại secret khỏi repo theo quy trình, dùng local values riêng và secret manager phù hợp.

### Bài 8 — RabbitMQ redelivery

Consumer xử lý message, ghi dữ liệu xong rồi crash trước khi ack. Sau restart, message được gửi lại.

**Câu hỏi:** Cần thiết kế gì?

**Đáp án:** Consumer phải idempotent/deduplicate, dùng event ID hoặc business key và transaction semantics phù hợp để không tạo side effect trùng.

### Bài 9 — Compose hay Testcontainers?

Một integration test chạy trong CI cần PostgreSQL sạch cho mỗi test suite.

**Đáp án gợi ý:** Testcontainers có thể phù hợp hơn vì quản lý lifecycle dependency theo test; Compose vẫn hữu ích để chạy cả stack và debug tương tác thủ công.

### Bài 10 — Production readiness

Một lab chạy ổn trên laptop có 2 service, một database và RabbitMQ. Có thể dùng nguyên file Compose để triển khai production?

**Đáp án:** Không tự động. Cần đánh giá HA, secrets, identity, network, backup, scaling, monitoring, rollout, disaster recovery và multi-tenant governance trên nền tảng production.

## 38. Checklist trước khi chia sẻ môi trường cho team

- [ ] Docker/Compose version và prerequisites được document.
- [ ] Một lệnh khởi động tạo đúng các service cần thiết.
- [ ] Image versions được pin phù hợp.
- [ ] Service names và network topology nhất quán.
- [ ] Host ports bind vào loopback khi chỉ cần local access.
- [ ] Database ports không publish nếu không cần.
- [ ] Mỗi service có data ownership và volume phù hợp.
- [ ] .env bị ignore; .env.example không chứa secret thật.
- [ ] Biến bắt buộc được kiểm tra khi chạy docker compose config.
- [ ] Healthchecks kiểm tra đúng điều kiện và công cụ có trong image.
- [ ] depends_on được dùng đúng, app vẫn xử lý dependency restart.
- [ ] Migration/seed data có thể tái tạo.
- [ ] Logs và trạng thái từng service có thể quan sát.
- [ ] Smoke tests xác minh business workflow.
- [ ] Có cách debug DNS, port, volume và dependency.
- [ ] Có hướng dẫn stop/start khác với reset/delete data.
- [ ] Không mount Docker socket hoặc dùng privileged nếu không cần.
- [ ] Không dùng production credentials/data.
- [ ] Profiles và override files được document.
- [ ] Có hướng dẫn dọn dẹp an toàn và backup dữ liệu cần giữ.

## 39. Những sai lầm thường gặp

1. Dùng localhost để service trong container gọi container khác.
2. Nhầm host port với container port.
3. Publish tất cả database ports ra mọi network interface.
4. Nghĩ depends_on đơn giản bảo đảm dependency sẵn sàng.
5. Không có healthcheck hoặc healthcheck chỉ kiểm tra process.
6. Cho rằng container restart sẽ build code mới.
7. Quên named volume nên mất dữ liệu khi xóa container, hoặc quên volume cũ làm test dùng dữ liệu stale.
8. Dùng down -v theo thói quen và xóa mất dữ liệu cần giữ.
9. Commit .env, secret hoặc production dump vào repository.
10. Cho mọi service dùng chung database credential/quyền quá rộng.
11. Gắn source bind mount vào image production.
12. Dùng tag latest làm môi trường khó tái lập.
13. Bật quá nhiều service mặc định làm laptop cạn RAM.
14. Không kiểm tra Compose file sau khi merge override.
15. Chạy migration thủ công trong container rồi không lưu script.
16. Dùng Redis như nguồn sự thật dù chỉ cấu hình cache.
17. Không xử lý duplicate message/redelivery.
18. Không phân biệt readiness với business correctness.
19. Coi Compose local là tương đương Kubernetes production.
20. Dùng cleanup command rộng mà không kiểm tra phạm vi volumes/images.

## 40. Ghi nhớ

Docker Compose giúp người học dựng một nhóm service có cấu hình, network, volume và lifecycle rõ ràng trên máy cá nhân. Giá trị lớn nhất là **môi trường có thể tái tạo và quan sát được**, nơi mỗi service chạy trong container riêng, giao tiếp qua DNS nội bộ và sử dụng dependency theo đúng ranh giới.

Khi viết Compose, cần hiểu host/container ports, service discovery, healthcheck, depends_on, environment variables, volumes và profiles. Spring Boot phải dùng hostname nội bộ khi chạy trong container; khi chạy từ IDE trên host, cấu hình endpoint lại khác. Database volume giữ dữ liệu qua container recreation, nên reset cần được thực hiện có chủ đích.

Một môi trường học tập tốt còn có README, smoke tests, migration, logs, hướng dẫn debug và cách dọn dẹp. Nó giúp học service-to-service communication, persistence, cache, messaging, failure handling và observability. Tuy vậy, Compose không tự cung cấp toàn bộ HA, autoscaling, security governance hay disaster recovery của production platform.

**Nguyên tắc cốt lõi: mô tả topology nhiều dịch vụ bằng cấu hình có thể version-control, giữ dữ liệu và secrets có chủ đích, dùng service DNS đúng network boundary, kiểm tra readiness thực tế và luôn phân biệt môi trường local phục vụ học tập với hệ thống production cần vận hành có kiểm soát.**