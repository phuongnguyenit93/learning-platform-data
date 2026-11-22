# Dựng môi trường MongoDB bằng Docker: lưu dữ liệu bằng volume và cấu hình kết nối

MongoDB là cơ sở dữ liệu tài liệu (document database), lưu dữ liệu chủ yếu dưới dạng BSON. Khi học MongoDB, việc cài đặt trực tiếp lên hệ điều hành có thể làm môi trường giữa các máy khác nhau và gây khó khăn khi đổi phiên bản. Docker giúp chạy MongoDB trong một container có cấu hình rõ ràng, còn Docker Compose giúp mô tả và khởi động môi trường bằng một file.

Bài thực hành này dựng **một MongoDB độc lập (standalone)** phục vụ phát triển trên máy cá nhân. Dữ liệu được lưu trong **Docker named volume**, tài khoản quản trị được tạo ở lần khởi tạo đầu tiên và ứng dụng kết nối qua một MongoDB connection string. Cuối bài, ta sẽ tắt và tạo lại container để chứng minh dữ liệu vẫn còn.

## 1. Kết quả cần đạt và kiến trúc môi trường

Sau bài học, bạn có thể:

- Khởi động và quản lý MongoDB bằng Docker Compose.
- Phân biệt dữ liệu trong lớp ghi của container với dữ liệu trong Docker volume.
- Cấu hình tài khoản, cổng truy cập và URI kết nối MongoDB.
- Kết nối từ terminal trên máy, từ ứng dụng Java/Spring Boot và từ một container khác.
- Kiểm tra dữ liệu còn tồn tại sau khi container được tạo lại; nhận biết những thao tác có thể xóa volume.
- Xác định các lỗi thường gặp về cổng, tài khoản, địa chỉ host và trạng thái khởi động.

Sơ đồ môi trường:

~~~text
Máy lập trình (Windows/macOS/Linux)
  |
  | MongoDB URI: mongodb://...@localhost:27017/appdb?authSource=...
  v
127.0.0.1:27017  -- ánh xạ cổng Docker -->  mongodb:27017
                                               |
                                    Container MongoDB
                                               |
                                            /data/db
                                               |
                                       Docker named volume
                                   mongo-persistence-lab_mongo_data

Ứng dụng trong cùng mạng Docker Compose
  |
  +-- MongoDB URI dùng hostname mongodb:27017
~~~

Hai điểm cần phân biệt ngay từ đầu:

1. **Container** chứa tiến trình mongod và môi trường chạy; có thể bị dừng, xóa, tạo mới.
2. **Volume** chứa file dữ liệu của MongoDB; vòng đời của nó độc lập với container, miễn là ta không chủ động xóa volume.

## 2. Điều kiện chuẩn bị

Máy cần cài Docker Engine hoặc Docker Desktop, Docker Compose v2 và có thể tải image từ registry. Docker Desktop trên Windows thường sử dụng backend WSL 2. Máy không bắt buộc cài MongoDB Server hay mongosh riêng vì có thể dùng mongosh ngay trong container.

Mở terminal tại thư mục làm việc và kiểm tra:

~~~bash
docker --version
docker compose version
docker info
~~~

Lệnh cuối cần kết nối được đến Docker daemon. Nếu báo daemon chưa chạy, hãy khởi động Docker Desktop hoặc Docker service trước khi tiếp tục.

Trong ví dụ, cổng **27017** của máy được dành cho MongoDB. Nếu cổng đó đã có dịch vụ sử dụng, có thể đổi cổng phía máy sang 27018 ở bước cấu hình mà không phải đổi cổng MongoDB trong container.

Tạo thư mục thực hành:

~~~text
mongo-lab/
├── compose.yaml
├── .env
└── .gitignore
~~~

Chạy mọi lệnh Docker Compose dưới đây từ chính thư mục chứa file compose.yaml. Điều này giúp tránh chọn nhầm Compose project hay volume.

## 3. Viết file cấu hình Docker Compose

Tạo file **compose.yaml**:

~~~yaml
name: mongo-persistence-lab

services:
  mongodb:
    image: mongo:8.0
    restart: unless-stopped
    ports:
      - "127.0.0.1:27017:27017"
    environment:
      MONGO_INITDB_ROOT_USERNAME: ${MONGO_ROOT_USERNAME:?Set MONGO_ROOT_USERNAME in .env}
      MONGO_INITDB_ROOT_PASSWORD: ${MONGO_ROOT_PASSWORD:?Set MONGO_ROOT_PASSWORD in .env}
    volumes:
      - mongo_data:/data/db
    healthcheck:
      test:
        - CMD
        - mongosh
        - --quiet
        - --eval
        - "if (db.adminCommand({ ping: 1 }).ok !== 1) quit(1)"
      interval: 10s
      timeout: 5s
      retries: 10
      start_period: 20s

volumes:
  mongo_data:
~~~

**Ý nghĩa từng thành phần:**

| Thành phần | Vai trò |
|---|---|
| name | Đặt tên Compose project ổn định; volume thực tế thường mang tên mongo-persistence-lab_mongo_data. |
| image | Sử dụng image MongoDB thuộc nhánh 8.0. Với môi trường cần tái lập chặt chẽ, có thể khóa đến một bản vá hoặc image digest sau khi kiểm thử. |
| restart | Docker tự khởi động lại container theo chính sách unless-stopped khi phù hợp. |
| ports | Chỉ công bố cổng 27017 trên địa chỉ loopback 127.0.0.1 của máy, hạn chế truy cập từ máy khác. |
| environment | Image chính thức dùng hai biến MONGO_INITDB_ROOT_USERNAME và MONGO_INITDB_ROOT_PASSWORD để tạo tài khoản quản trị khi dữ liệu còn trống. |
| volumes | Gắn named volume mongo_data vào đường dẫn dữ liệu /data/db bên trong container. |
| healthcheck | Thử lệnh ping để Docker báo trạng thái sẵn sàng đáp ứng ở mức cơ bản. Nó không thay thế việc thử đăng nhập hoặc kiểm tra nghiệp vụ. |

**Vì sao dùng named volume?** Docker tự quản lý vị trí lưu và quyền truy cập dữ liệu, thuận tiện trên cả Windows, macOS và Linux. Bind mount một thư mục máy vào /data/db cũng có thể thực hiện được nhưng dễ gặp khác biệt về quyền file, hiệu năng và filesystem, nhất là với Docker Desktop.

File này chỉ mô tả dịch vụ MongoDB; chưa có ứng dụng Java. Docker Compose tự tạo một mạng mặc định cho project, nên các container cùng project có thể gọi dịch vụ bằng tên **mongodb**.

### 3.1. Khai báo biến môi trường

Tạo file **.env** đặt cùng cấp compose.yaml:

~~~dotenv
MONGO_ROOT_USERNAME=admin
MONGO_ROOT_PASSWORD=DevMongo_2026_Local
MONGO_APP_PASSWORD=AppMongo_2026_Local
~~~

Các giá trị trên chỉ là **ví dụ dành cho máy học tập**; hãy đổi sang mật khẩu riêng. Biến MONGO_APP_PASSWORD sẽ dùng nếu bạn tạo tài khoản ứng dụng ở phần sau. MongoDB image **không tự tạo tài khoản ứng dụng** chỉ vì có biến này trong .env.

File .env được Docker Compose dùng để **thay thế biến trong compose.yaml**. Nó không tự động trở thành biến môi trường của terminal đang chạy Java, và biến không được đưa vào mục environment của service cũng không tự xuất hiện trong container.

Tạo file **.gitignore**:

~~~gitignore
.env
backups/
*.archive
*.archive.gz
~~~

Không commit mật khẩu thật vào repository. Đối với dự án dùng chung, nên thêm một file .env.example chỉ chứa tên biến và placeholder để đồng đội tự tạo .env.

**Lưu ý về lần khởi tạo đầu tiên:** hai biến MONGO_INITDB_ROOT_* chỉ có tác dụng tạo root user khi thư mục dữ liệu MongoDB còn trống. Nếu volume đã được tạo và có dữ liệu, việc đổi mật khẩu trong .env **không đổi mật khẩu tài khoản đã tồn tại**. Cần thay đổi mật khẩu bằng thao tác quản trị trong MongoDB hoặc, chỉ với môi trường thử nghiệm không cần dữ liệu, tạo lại volume.

## 4. Khởi động và quan sát MongoDB

Kiểm tra cú pháp và giá trị cấu hình rồi khởi động:

~~~bash
docker compose config --quiet
docker compose up -d
docker compose ps
docker compose logs --tail 60 mongodb
~~~

Lệnh **config --quiet** xác thực cấu hình Compose mà không in toàn bộ giá trị biến ra terminal; đặc biệt tránh vô tình chia sẻ mật khẩu. Khi khởi động lần đầu, Docker có thể cần tải image và MongoDB cần tạo dữ liệu khởi tạo nên chưa nhận kết nối ngay lập tức.

Ở lệnh **docker compose ps**, cột trạng thái sẽ cho biết service đang chạy và, sau thời gian khởi tạo, có thể hiển thị healthy. Để theo dõi log liên tục:

~~~bash
docker compose logs -f mongodb
~~~

Nhấn Ctrl+C để ngừng xem log; thao tác này không dừng MongoDB đang chạy nền.

Nếu cần xem thông tin volume:

~~~bash
docker volume ls
docker volume inspect mongo-persistence-lab_mongo_data
~~~

Lệnh inspect cho biết thông tin quản lý volume, bao gồm tên và đường dẫn mount do Docker quản lý. Đừng chỉnh sửa trực tiếp các file dữ liệu khi mongod đang chạy; hãy tương tác qua MongoDB client.

### 4.1. Đăng nhập bằng mongosh trong container

Lệnh sau mở MongoDB Shell trong container:

~~~bash
docker compose exec mongodb mongosh --username admin --authenticationDatabase admin
~~~

Nhập mật khẩu khi mongosh yêu cầu; ví dụ trong file .env là **DevMongo_2026_Local**. Tên database xác thực là **admin** vì root user do image khởi tạo nằm trong database admin.

Sau khi vào mongosh, thử:

~~~javascript
db.adminCommand({ ping: 1 })
db.runCommand({ connectionStatus: 1 })
show dbs
~~~

Kết quả ping thành công có trường ok bằng 1. Lệnh connectionStatus giúp quan sát user đã xác thực. Lệnh show dbs hiển thị những database hiện có và bạn có quyền xem.

Gõ exit để thoát mongosh. Bạn cũng có thể cài mongosh trên máy và kết nối đến 127.0.0.1:27017, nhưng đây không phải điều kiện bắt buộc của bài học.

## 5. Thực hành ghi dữ liệu và chứng minh tính bền vững

Trong mongosh đã đăng nhập, chuyển sang database thực hành và tạo một document:

~~~javascript
use appdb

db.products.updateOne(
  { _id: "volume-test-001" },
  {
    $set: {
      name: "Notebook",
      quantity: 3,
      source: "docker-volume-lab"
    }
  },
  { upsert: true }
)

db.products.findOne({ _id: "volume-test-001" })
~~~

MongoDB tạo database và collection khi có dữ liệu ghi đầu tiên; chỉ chạy **use appdb** chưa đảm bảo database được tạo trên đĩa. Ở đây, updateOne với upsert tạo document nếu chưa có, giúp lặp lại bài thực hành mà không gây lỗi trùng _id.

Thoát mongosh rồi thực hiện:

~~~bash
docker compose down
docker compose up -d
docker compose ps
docker compose exec mongodb mongosh --username admin --authenticationDatabase admin
~~~

Trong phiên mongosh mới:

~~~javascript
use appdb
db.products.findOne({ _id: "volume-test-001" })
~~~

Nếu document vẫn có name là Notebook và source là docker-volume-lab, bạn đã kiểm chứng dữ liệu được giữ lại sau khi container cũ bị xóa và tạo lại. MongoDB ghi file dữ liệu ở /data/db; mount volume khiến Docker giữ những file đó bên ngoài lớp ghi của container.

**Phân biệt các lệnh quan trọng:**

| Lệnh | Tác động lên container | Tác động lên named volume |
|---|---|---|
| docker compose stop | Dừng container. | Giữ nguyên. |
| docker compose start | Khởi động container đã có. | Dùng lại volume cũ. |
| docker compose restart mongodb | Khởi động lại dịch vụ MongoDB. | Giữ nguyên. |
| docker compose down | Dừng và xóa container, network của project. | Thông thường giữ lại named volume. |
| docker compose up -d | Tạo hoặc cập nhật container rồi chạy nền. | Gắn lại volume cùng tên nếu còn. |
| docker compose down -v | Xóa container/network và volume do project quản lý theo cấu hình Compose. | **Dữ liệu trong volume có thể bị xóa vĩnh viễn.** |

Trong bài thực hành, **không chạy down -v** nếu bạn muốn giữ dữ liệu vừa tạo. Named volume không phải giải pháp sao lưu: việc xóa volume, mất ổ đĩa hoặc hỏng dữ liệu vẫn có thể làm mất dữ liệu.

### 5.1. Đổi cổng trên máy mà không đổi dữ liệu

Nếu cổng 27017 trên máy đã bị chiếm, sửa duy nhất mục ports thành:

~~~yaml
ports:
  - "127.0.0.1:27018:27017"
~~~

Sau đó:

~~~bash
docker compose up -d
~~~

Giờ client chạy **trên máy** dùng 127.0.0.1:27018; container MongoDB vẫn lắng nghe trên cổng 27017, và container khác cùng Compose project vẫn dùng mongodb:27017. Dữ liệu trong named volume không đổi vì cổng chỉ ảnh hưởng đến đường truy cập mạng.

## 6. Hiểu và cấu hình MongoDB connection string

Một MongoDB URI cơ bản có dạng:

~~~text
mongodb://<username>:<password>@<host>:<port>/<database>?authSource=<authenticationDatabase>
~~~

Các thành phần:

| Phần URI | Ý nghĩa |
|---|---|
| mongodb:// | Dùng giao thức kết nối MongoDB thông thường. |
| username, password | Thông tin user MongoDB cần xác thực. |
| host, port | Địa chỉ dịch vụ nhìn từ **nơi client đang chạy**. |
| database trong path | Database mặc định mà ứng dụng muốn thao tác. |
| authSource | Database lưu thông tin user dùng để xác thực. |

Với tài khoản root của bài thực hành, URI từ máy cá nhân là:

~~~text
mongodb://admin:DevMongo_2026_Local@localhost:27017/appdb?authSource=admin
~~~

Ở đây, **appdb** là database chứa dữ liệu ứng dụng, còn **admin** là database dùng xác thực root user. Hai database này có thể khác nhau; nếu bỏ authSource, driver có thể thử xác thực ở database trong path và trả lỗi Authentication failed.

**Chọn host theo vị trí chạy client:**

| Client chạy ở đâu? | Host/port của MongoDB |
|---|---|
| Java, IDE hoặc mongosh trên máy lập trình | localhost:27017 hoặc 127.0.0.1:27017 |
| Một service khác trong cùng Docker Compose project | mongodb:27017 |
| mongosh chạy ngay trong container MongoDB | localhost:27017 |
| Client ở máy khác | Cần cấu hình mạng, firewall, xác thực và phương án truy cập an toàn riêng; bài này chỉ bind cổng ra loopback. |

**localhost luôn là máy hoặc container của chính client.** Nếu ứng dụng Java được đóng gói vào một container khác, localhost trong URI sẽ trỏ về container ứng dụng, không phải container MongoDB. Trong Compose network, hãy dùng **mongodb** là tên dịch vụ.

Mật khẩu hoặc username chứa ký tự đặc biệt dành riêng cho URI, như @, :, /, ?, # hoặc %, phải được **percent-encode** trong phần userinfo. Ví dụ ký tự @ thành %40. Không thay đổi mật khẩu thực lưu trong MongoDB; chỉ mã hóa biểu diễn của nó trong URI.

### 6.1. Tạo tài khoản riêng cho ứng dụng

Root user thuận tiện để thiết lập ban đầu nhưng không nên dùng cho ứng dụng lâu dài vì có quyền quản trị rộng. Trong mongosh đã đăng nhập bằng root, tạo user chỉ có quyền readWrite với appdb:

~~~javascript
use appdb

db.createUser({
  user: "app_user",
  pwd: "AppMongo_2026_Local",
  roles: [
    { role: "readWrite", db: "appdb" }
  ]
})
~~~

Đây là tài khoản cho môi trường học tập, với mật khẩu trùng MONGO_APP_PASSWORD đã khai báo để sử dụng ở phần Compose ứng dụng sau này. Hãy đổi sang mật khẩu riêng và cấp quyền tối thiểu trong dự án thực.

URI trên máy cho tài khoản ứng dụng:

~~~text
mongodb://app_user:AppMongo_2026_Local@localhost:27017/appdb?authSource=appdb
~~~

Lần này authSource là **appdb** vì user được tạo trong appdb. Có thể kiểm tra bằng cách thoát mongosh và đăng nhập:

~~~bash
docker compose exec mongodb mongosh --username app_user --authenticationDatabase appdb
~~~

Sau khi nhập mật khẩu, chạy:

~~~javascript
use appdb
db.products.findOne({ _id: "volume-test-001" })
~~~

User này được đọc và ghi dữ liệu trong appdb, nhưng không có quyền quản trị toàn hệ thống. Nếu chạy lại lệnh db.createUser với cùng tên user, MongoDB báo user đã tồn tại; khi cần đổi mật khẩu hãy dùng thao tác quản trị thay vì tạo trùng.

## 7. Kết nối từ ứng dụng Java

Khi viết Java, nên đưa URI ra biến môi trường hoặc cơ chế quản lý secret của môi trường triển khai. Điều đó giúp cùng một ứng dụng dùng cấu hình khác nhau khi chạy trên máy, trong container hoặc trên server mà không phải sửa mã nguồn.

### 7.1. Spring Boot với Spring Data MongoDB

Trong dự án **Spring Boot 3.x** có dependency Spring Data MongoDB, file application.yml có thể tham chiếu biến môi trường:

~~~yaml
spring:
  data:
    mongodb:
      uri: ${MONGODB_URI}
~~~

Ví dụ đặt biến MONGODB_URI trong **PowerShell** trước khi chạy ứng dụng trên máy:

~~~powershell
$env:MONGODB_URI = 'mongodb://app_user:AppMongo_2026_Local@localhost:27017/appdb?authSource=appdb'
~~~

Tương đương trên **bash/zsh**:

~~~bash
export MONGODB_URI='mongodb://app_user:AppMongo_2026_Local@localhost:27017/appdb?authSource=appdb'
~~~

Sau đó chạy ứng dụng Java theo cơ chế build của chính dự án. Nếu dùng Spring Boot phiên bản khác, hãy kiểm tra tên property MongoDB tương ứng với phiên bản đang dùng. Biến MONGODB_URI cần có trong môi trường của **tiến trình Java**; việc đặt URI trong .env cho Docker Compose không tự truyền nó sang một Java process chạy ngoài Docker.

Một repository đơn giản để kiểm chứng kết nối có thể viết như sau:

~~~java
import org.springframework.data.mongodb.repository.MongoRepository;

public interface ProductRepository extends MongoRepository<Product, String> {
}
~~~

Trong ví dụ này, Product là một entity do bạn định nghĩa và ánh xạ tới collection tương ứng bằng Spring Data MongoDB. Khi khởi tạo ứng dụng, driver kết nối theo URI; thao tác repository như save hoặc findById sẽ gửi yêu cầu tới MongoDB. Không cần ghi username/password bên trong repository.

### 7.2. Java MongoDB Sync Driver, không dùng Spring

Nếu ứng dụng dùng MongoDB Java Sync Driver, có thể kiểm tra kết nối qua lệnh ping:

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import org.bson.Document;

public class MongoConnectionCheck {
    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalStateException("MONGODB_URI is required");
        }

        try (MongoClient client = MongoClients.create(uri)) {
            Document result = client.getDatabase("appdb")
                    .runCommand(new Document("ping", 1));
            System.out.println(result.toJson());
        }
    }
}
~~~

Ví dụ này cần dependency **org.mongodb:mongodb-driver-sync** với phiên bản tương thích dự án. MongoClient sẽ được đóng đúng cách nhờ try-with-resources. Trong ứng dụng chạy liên tục, thông thường nên tái sử dụng một MongoClient thay vì tạo mới cho từng truy vấn.

### 7.3. Khi cả Java và MongoDB cùng nằm trong Docker Compose

Giả sử dự án Java đã có Dockerfile. Bạn có thể mở rộng danh sách services trong compose.yaml bằng phần minh họa:

~~~yaml
  app:
    build: .
    environment:
      MONGODB_URI: "mongodb://app_user:${MONGO_APP_PASSWORD:?Set MONGO_APP_PASSWORD in .env}@mongodb:27017/appdb?authSource=appdb"
    depends_on:
      mongodb:
        condition: service_healthy
~~~

Service **app** là minh họa, chỉ chạy được khi có Dockerfile thực sự và ứng dụng đọc biến MONGODB_URI. Nó sử dụng hostname mongodb do Compose cung cấp và cần user app_user đã tạo ở mục 6.1. Để chạy app trong container, không dùng localhost:27017 vì đó là loopback của chính app container.

depends_on với condition: service_healthy giúp trì hoãn việc khởi tạo app đến khi healthcheck của MongoDB thành công. Tuy vậy, kết nối vẫn có thể đứt sau khi hệ thống đang chạy; ứng dụng cần xử lý lỗi tạm thời và retry thích hợp ở tầng vận hành.

## 8. Cấu hình khởi tạo, volume và vòng đời dữ liệu

### 8.1. Phân biệt dữ liệu khởi tạo và dữ liệu lâu dài

Image MongoDB chính thức hỗ trợ chạy script trong đường dẫn /docker-entrypoint-initdb.d khi dữ liệu được khởi tạo lần đầu. Ví dụ, có thể mount một file .js dùng để tạo collection hoặc user ứng dụng. Tuy nhiên, các script khởi tạo này **không tự chạy lại trên volume đã có dữ liệu**. Đây là một đặc điểm quan trọng khi thay đổi cấu hình sau khi môi trường đã dùng vài ngày.

Nếu thêm biến MONGO_INITDB_DATABASE vào môi trường, đừng hiểu rằng riêng biến đó luôn tạo ra database có dữ liệu. Database MongoDB chỉ thực sự xuất hiện khi có thao tác ghi dữ liệu hoặc script khởi tạo tạo collection/document.

Đối với schema hoặc seed data cần chạy nhiều lần, nên có migration/seed procedure riêng, có khả năng chạy lại an toàn, thay vì kỳ vọng Docker init script chạy ở mỗi lần docker compose up.

### 8.2. Volume ổn định, nhưng không phải backup

Named volume giữ dữ liệu khi container bị thay thế, nhưng không bảo vệ trước mọi rủi ro. Trước khi nâng cấp MongoDB, thay đổi cấu hình quan trọng hoặc chuyển máy, cần sao lưu dữ liệu bằng công cụ MongoDB phù hợp (ví dụ mongodump/mongorestore hoặc phương án backup nhất quán ở cấp hệ thống), đồng thời kiểm tra có thể khôi phục được.

Không nên coi việc sao chép nóng các file trong /data/db khi mongod đang chạy là một quy trình backup an toàn. Để cập nhật image từ một phiên bản MongoDB sang phiên bản khác, cần đọc hướng dẫn tương thích và đường nâng cấp của đúng phiên bản; tránh đổi major version tùy tiện trên volume dữ liệu quan trọng.

Ở bài tập này, một instance standalone đủ cho CRUD cơ bản. Các giao dịch nhiều document và những tính năng yêu cầu replica set cần cấu hình MongoDB replica set hoặc cluster phù hợp, không thể suy ra chỉ từ việc sử dụng Docker.

### 8.3. Dừng, chạy lại và dọn môi trường

Một số lệnh thường dùng:

~~~bash
# Dừng nhưng giữ container và volume
docker compose stop

# Chạy lại container đã dừng
docker compose start

# Khởi động lại riêng MongoDB
docker compose restart mongodb

# Hủy container/network của project, giữ named volume
docker compose down

# Dựng lại service từ compose.yaml
docker compose up -d
~~~

Chỉ khi thực sự muốn **xóa toàn bộ dữ liệu thực hành** và đã xác nhận volume thuộc đúng project, mới cân nhắc:

~~~bash
docker compose down -v
~~~

Lệnh trên có thể xóa volume chứa dữ liệu MongoDB; không dùng trong chuỗi thao tác kiểm thử lưu bền ở mục 5.

## 9. Các sự cố thường gặp và cách xác định nguyên nhân

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra và xử lý |
|---|---|---|
| Không chạy được docker compose | Docker daemon chưa hoạt động hoặc Compose chưa có | Kiểm tra docker info, docker compose version và trạng thái Docker Desktop/service. |
| Bind port 27017 failed / address already in use | Có MongoDB hay chương trình khác đang chiếm cổng host | Kiểm tra tiến trình đang nghe và đổi ánh xạ thành 127.0.0.1:27018:27017 nếu phù hợp. |
| Connection refused | Container chưa chạy hoặc mongod chưa sẵn sàng; host/port không đúng | Xem docker compose ps, docker compose logs mongodb và URI thực tế của client. |
| Authentication failed | Sai username/password hoặc authSource | Root user của ví dụ dùng authSource=admin; app_user dùng authSource=appdb. Kiểm tra user thực tế trong volume. |
| Đổi mật khẩu .env nhưng vẫn đăng nhập bằng mật khẩu cũ | Volume đã tồn tại nên init root user không chạy lại | Đổi password bằng MongoDB admin command; không xóa volume nếu đang cần dữ liệu. |
| Java container không kết nối được localhost:27017 | localhost trỏ về Java container | Dùng hostname mongodb:27017 trong cùng Compose network. |
| Client trên máy không phân giải được hostname mongodb | Tên dịch vụ Compose chủ yếu được phân giải trong mạng Docker | Dùng localhost cùng cổng host đã publish khi client chạy trên máy. |
| Không thấy database mới sau lệnh use | Chưa có document/collection được tạo | Thử insertOne hoặc updateOne với upsert, sau đó show dbs. |
| Dữ liệu như bị mất khi đổi thư mục/project | Docker Compose tạo volume theo tên project mới | Kiểm tra docker volume ls và giá trị name; tránh vô tình dùng một volume khác. |
| Container chạy nhưng truy vấn giao dịch lỗi | MongoDB standalone không hỗ trợ tính năng yêu cầu replica set | Cấu hình replica set khi bài toán thực sự cần transaction hoặc change stream. |

Khi điều tra, nên dựa vào log và trạng thái thực tế trước khi xóa container hay volume:

~~~bash
docker compose ps
docker compose logs --tail 100 mongodb
docker volume ls
~~~

Thông tin đăng nhập trong URI, .env hay docker compose config có thể là bí mật; khi chia sẻ log hoặc cấu hình để nhờ hỗ trợ, hãy che password và token.

## 10. Bài tập tự kiểm chứng

Thực hiện lần lượt các yêu cầu sau:

1. Dựng MongoDB bằng compose.yaml và xác nhận container chạy, có named volume.
2. Đăng nhập mongosh với root user; tạo database appdb và document có _id là volume-test-001.
3. Dùng docker compose down rồi docker compose up -d; truy vấn lại để xác minh document vẫn tồn tại.
4. Tạo app_user chỉ có readWrite trên appdb; dùng app_user đọc lại document.
5. Đổi cổng host thành 27018; kết nối từ máy bằng localhost:27018 và lý giải vì sao địa chỉ mongodb:27017 bên trong Compose network vẫn đúng.
6. Cấu hình MONGODB_URI cho ứng dụng Java/Spring Boot; kiểm tra đọc dữ liệu hoặc ping thành công bằng driver.

**Tiêu chí hoàn thành:** bạn giải thích được chính xác file dữ liệu đang nằm ở đâu, tại sao down rồi up không làm mất dữ liệu, khi nào authSource là admin hoặc appdb, và vì sao URI của Java chạy trên máy khác URI của Java chạy trong container.

## 11. Những nguyên tắc mang sang dự án thực tế

Docker Compose rất phù hợp cho môi trường học tập, chạy tích hợp ở máy phát triển và tái lập lỗi. Khi mang ứng dụng tới môi trường có dữ liệu quan trọng, cần thiết kế thêm sao lưu và khôi phục, quản lý secret, kiểm soát truy cập mạng, theo dõi sức khỏe, chiến lược nâng cấp và tính sẵn sàng cao theo nhu cầu thực tế.

Ba nguyên tắc cốt lõi xuyên suốt bài là:

- **Giữ dữ liệu ngoài vòng đời container:** mount /data/db vào một volume được quản lý rõ ràng.
- **Định vị server từ góc nhìn client:** ứng dụng trên máy dùng localhost cùng published port; ứng dụng trong cùng Compose project dùng tên service mongodb.
- **Tách xác thực và dữ liệu nghiệp vụ:** root user nằm trong admin, user ứng dụng có quyền nhỏ hơn trên appdb; connection string khai báo authSource đúng nơi user được tạo.

Nắm vững ba điểm này giúp chuyển từ việc “chạy được MongoDB bằng Docker” sang một môi trường phát triển có thể tái lập, kết nối được với ứng dụng Java và kiểm soát được vòng đời dữ liệu.
