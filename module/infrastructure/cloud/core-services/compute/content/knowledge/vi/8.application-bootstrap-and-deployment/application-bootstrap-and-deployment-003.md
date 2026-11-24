# Tách cấu hình ứng dụng khỏi image và mã nguồn

## Mục tiêu bài học

Một ứng dụng thường chạy ở nhiều môi trường như development, testing, staging và production. Các môi trường có thể dùng cùng một phiên bản mã nguồn nhưng khác địa chỉ cơ sở dữ liệu, endpoint dịch vụ, mức log, giới hạn kết nối và thông tin xác thực. Nếu những giá trị này được ghi cố định trong mã nguồn hoặc đóng gói vào image, việc triển khai sẽ khó kiểm soát và dễ gây lỗi khi chuyển môi trường.

Tách cấu hình ứng dụng khỏi image và mã nguồn (externalized configuration) giúp một artifact đã kiểm thử có thể được triển khai ở nhiều môi trường bằng cách cung cấp cấu hình phù hợp tại thời điểm chạy.

Sau bài học này, bạn có thể:

- Phân biệt cấu hình ứng dụng, mã nguồn, image triển khai và bí mật.
- Chọn cách cung cấp cấu hình qua file, biến môi trường hoặc dịch vụ quản lý cấu hình.
- Quản lý secret bằng secret manager và danh tính workload.
- Tổ chức cấu hình theo môi trường, kiểm tra giá trị bắt buộc và xử lý thứ tự ưu tiên.
- Cập nhật cấu hình an toàn cho máy ảo, container và workload trên Kubernetes.

## 1. Vì sao cần tách cấu hình?

Giả sử một dịch vụ Java kết nối tới PostgreSQL và một dịch vụ thanh toán. Trong môi trường staging, ứng dụng cần dùng database staging và endpoint sandbox. Trong production, ứng dụng dùng database production, endpoint thật, mức log phù hợp và giới hạn kết nối lớn hơn.

Nếu các địa chỉ này được ghi trực tiếp trong mã nguồn, mỗi lần đổi môi trường có thể phải sửa code, build lại và phát hành artifact mới. Cách làm đó làm tăng nguy cơ:

- Build staging và production vô tình khác nhau dù cùng một phiên bản ứng dụng.
- Một endpoint thử nghiệm hoặc tài khoản sandbox bị đưa vào production.
- Thông tin nhạy cảm bị commit vào Git hoặc xuất hiện trong image.
- Thay đổi cấu hình nhỏ cũng buộc phải build và triển khai lại toàn bộ ứng dụng.
- Khó xác định cấu hình thực tế mà một instance đang sử dụng khi xảy ra sự cố.

Khi tách cấu hình, nhóm phát triển build một artifact đã xác định phiên bản. Môi trường triển khai cung cấp các giá trị phù hợp khi chạy ứng dụng. Nhờ vậy, cùng một artifact có thể chạy ở nhiều môi trường mà không phải thay đổi nội dung mã nguồn hoặc image.

~~~mermaid
flowchart LR
    A["Mã nguồn"] --> B["Build một lần"]
    B --> C["Artifact / container image"]
    C --> D["Triển khai staging"]
    C --> E["Triển khai production"]
    F["Cấu hình staging"] --> D
    G["Cấu hình production"] --> E
    H["Secret manager / workload identity"] --> D
    H --> E
~~~

Nguyên tắc này thường được gọi là build once, deploy many: build một artifact có thể truy vết, sau đó triển khai artifact đó với cấu hình riêng của từng môi trường.

## 2. Phân biệt mã nguồn, cấu hình và secret

Không phải mọi giá trị thay đổi theo môi trường đều có cùng mức độ nhạy cảm. Cần phân loại trước khi chọn nơi lưu trữ.

| Loại thông tin | Ví dụ | Cách quản lý phù hợp |
|---|---|---|
| Mã nguồn và logic | Quy tắc tính phí, luồng xử lý đơn hàng | Git và quy trình build/release |
| Cấu hình không bí mật | Tên môi trường, mức log, timeout, feature flag, endpoint công khai | File cấu hình, biến môi trường hoặc config service |
| Secret | Mật khẩu DB, API token, private key, credential | Secret manager hoặc kho bí mật được kiểm soát |
| Tham số tài nguyên | CPU, RAM, port, số replica, giới hạn kết nối | Deployment manifest, machine template hoặc IaC |
| Dữ liệu vận hành | Trạng thái đơn hàng, hồ sơ người dùng, giao dịch | Database hoặc hệ thống lưu trữ dữ liệu phù hợp |

Cấu hình mô tả ứng dụng cần hoạt động như thế nào trong môi trường hiện tại. Secret là dữ liệu cấp quyền hoặc xác thực, có thể cho phép truy cập tài nguyên nếu bị lộ. Vì vậy, secret cần quyền truy cập chặt chẽ, audit và cơ chế xoay vòng.

Không nên coi mọi giá trị trong file cấu hình đều an toàn. Một file có thể chứa endpoint nội bộ, tên tài khoản, thông tin topology hoặc dữ liệu vận hành cần giới hạn truy cập. Hãy phân loại theo mức độ nhạy cảm thực tế của từng giá trị.

## 3. Các cách cung cấp cấu hình lúc chạy

### 3.1. File cấu hình

Ứng dụng đọc cấu hình từ file YAML, JSON, TOML, properties hoặc định dạng phù hợp với framework. File có thể được đưa vào máy ảo, mount vào container hoặc lấy từ hệ thống quản lý cấu hình khi khởi động.

Ví dụ file application.yaml:

~~~yaml
server:
  port: 8080

app:
  environment: production
  log-level: INFO
  request-timeout: 3s

database:
  host: db.internal.example
  port: 5432
  name: orders
  pool:
    max-size: 30

payment:
  endpoint: https://payments.example.com
~~~

File trên chỉ chứa cấu hình minh họa không phải secret. Mật khẩu và token nên được lấy riêng từ secret manager hoặc cơ chế secret của nền tảng.

Ưu điểm của file cấu hình:

- Có cấu trúc phân cấp, dễ đọc và dễ kiểm tra.
- Có thể quản lý theo phiên bản và review thay đổi.
- Phù hợp với ứng dụng có nhiều nhóm cấu hình.
- Có thể mount vào container mà không cần đóng gói lại image.

Hạn chế cần lưu ý:

- File phải được phân phối và cập nhật tới đúng máy hoặc workload.
- Nếu chứa secret, cần bảo vệ quyền đọc, mã hóa và quy trình lưu trữ.
- Ứng dụng cần quy định rõ khi nào đọc lại file và xử lý lỗi cú pháp.

### 3.2. Biến môi trường

Biến môi trường (environment variable) truyền giá trị vào tiến trình khi khởi chạy. Đây là cách phổ biến để cung cấp cấu hình cho container và ứng dụng cloud-native.

Ví dụ:

~~~bash
export APP_ENV=production
export APP_LOG_LEVEL=INFO
export DB_HOST=db.internal.example
export DB_PORT=5432
export DB_NAME=orders
export PAYMENT_ENDPOINT=https://payments.example.com
java -jar orders-service.jar
~~~

Ứng dụng đọc các biến này khi khởi động. Với Java, có thể truy cập bằng System.getenv("DB_HOST"); framework như Spring Boot cũng hỗ trợ ánh xạ biến môi trường vào thuộc tính cấu hình.

Ưu điểm:

- Đơn giản, được hỗ trợ rộng rãi trong Linux, Windows, container và các dịch vụ triển khai.
- Dễ truyền giá trị từ machine template, service manager hoặc container orchestrator.
- Cho phép dùng cùng image với nhiều bộ cấu hình khác nhau.

Hạn chế:

- Biến môi trường thường được cố định cho một tiến trình tại thời điểm khởi chạy; thay đổi bên ngoài không tự động cập nhật giá trị tiến trình đang chạy.
- Giá trị có thể bị lộ qua công cụ debug, dump tiến trình, cấu hình chẩn đoán hoặc log nếu vận hành không cẩn thận.
- Không thuận tiện cho cấu hình lớn, cấu trúc phức tạp hoặc dữ liệu cần cập nhật liên tục.
- Tên biến và kiểu dữ liệu cần được chuẩn hóa để tránh sai chính tả hoặc chuyển đổi không hợp lệ.

Không nên đưa secret vào câu lệnh shell theo cách làm lộ giá trị trong history hoặc danh sách tiến trình. Khi nền tảng hỗ trợ, ưu tiên workload identity kết hợp secret manager hoặc mount secret vào file với quyền truy cập giới hạn.

### 3.3. Dịch vụ quản lý cấu hình tập trung

Một config service lưu và phân phối cấu hình cho nhiều ứng dụng hoặc nhiều instance. Ví dụ, tổ chức có thể dùng dịch vụ quản lý tham số của nhà cung cấp cloud, hệ thống configuration management hoặc nền tảng nội bộ.

Các khả năng thường gặp:

- Lưu cấu hình theo ứng dụng, môi trường, vùng hoặc phiên bản.
- Phân quyền đọc và sửa theo danh tính.
- Theo dõi lịch sử thay đổi và người phê duyệt.
- Phân phối cấu hình đến nhiều instance.
- Hỗ trợ rollout, cache và khôi phục phiên bản trước.
- Tích hợp với secret manager hoặc hệ thống quản lý khóa.

Config service giúp giảm tình trạng mỗi máy giữ một bản cấu hình khác nhau. Tuy nhiên, ứng dụng cần xử lý khi dịch vụ cấu hình không truy cập được, chẳng hạn dùng cache hợp lệ, timeout rõ ràng và chính sách khởi động an toàn.

### 3.4. Metadata và user data

Trên máy ảo cloud, metadata service có thể cung cấp thông tin về instance như ID, zone, network interface hoặc danh tính workload. User data/startup script có thể truyền tham số khởi tạo khi tạo máy.

Metadata và user data có vai trò khác nhau:

- Metadata thường chứa thông tin do nền tảng cung cấp về tài nguyên đang chạy.
- User data thường chứa nội dung hoặc tham số do người triển khai truyền vào để bootstrap máy.
- Không nên mặc định metadata hoặc user data là kho lưu secret an toàn. Khả năng truy cập, lưu trữ và bảo vệ phụ thuộc nền tảng và cấu hình.

Chỉ đưa dữ liệu khởi tạo cần thiết vào user data. Nếu cần bí mật, dùng danh tính workload để truy cập secret manager và lấy secret khi chạy.

## 4. Quản lý cấu hình theo môi trường

Một ứng dụng thường có nhiều môi trường, nhưng không nên duy trì các nhánh mã nguồn riêng chỉ để thay đổi địa chỉ database hoặc mức log.

Có thể tổ chức cấu hình theo cấu trúc:

~~~text
config/
  defaults.yaml
  development.yaml
  staging.yaml
  production.yaml
~~~

defaults.yaml chứa giá trị chung an toàn. File môi trường chỉ ghi đè những thuộc tính thực sự khác nhau. Ví dụ:

~~~yaml
# defaults.yaml
server:
  port: 8080
app:
  log-level: INFO
database:
  port: 5432
  pool:
    max-size: 10
~~~

~~~yaml
# production.yaml
app:
  log-level: WARN
database:
  host: db-prod.internal
  name: orders
  pool:
    max-size: 40
~~~

Giá trị phụ thuộc môi trường có thể được cung cấp từ deployment manifest hoặc config service thay vì lưu toàn bộ trong repository. Với production, cần xác định ai có quyền đọc và thay đổi cấu hình, đồng thời lưu audit cho thay đổi.

Một số nguyên tắc:

- Dùng cùng một artifact đã kiểm thử giữa các môi trường.
- Tách cấu hình dùng chung và cấu hình riêng của môi trường.
- Không dùng giá trị mặc định nguy hiểm cho production, ví dụ endpoint sandbox hoặc mật khẩu mẫu.
- Không lưu secret production trong repository, kể cả repository private, trừ khi có cơ chế mã hóa và quy trình quản lý secret được phê duyệt.
- Mỗi môi trường có danh tính và quyền truy cập riêng.
- Ghi nhận phiên bản cấu hình được triển khai cùng phiên bản ứng dụng.

## 5. Thứ tự ưu tiên và hợp nhất cấu hình

Một ứng dụng có thể nhận cùng một thuộc tính từ nhiều nguồn: giá trị mặc định trong ứng dụng, file cấu hình, biến môi trường, tham số dòng lệnh hoặc config service. Nếu không quy định thứ tự ưu tiên, hai môi trường có thể cho kết quả khác nhau khó giải thích.

Một thứ tự minh họa thường gặp:

1. Giá trị mặc định an toàn trong ứng dụng.
2. File cấu hình chung.
3. File cấu hình theo môi trường.
4. Biến môi trường do nền tảng triển khai cung cấp.
5. Tham số dòng lệnh được truyền có chủ đích.

Config service có thể nằm ở một vị trí khác trong thứ tự tùy thiết kế. Đây không phải quy tắc bắt buộc cho mọi framework; cần chọn và ghi rõ thứ tự mà ứng dụng thực sự hỗ trợ.

Ví dụ, nếu DB_POOL_MAX được đặt là 10 trong file chung và là 40 trong biến môi trường production, ứng dụng có thể dùng 40 nếu quy tắc ưu tiên quy định biến môi trường cao hơn.

Cần kiểm soát việc hợp nhất:

- Xác định rõ nguồn nào có quyền ghi đè nguồn nào.
- Kiểm tra kiểu dữ liệu, miền giá trị và trường bắt buộc.
- Không tự động dùng giá trị mặc định khi thiếu một cấu hình bảo mật quan trọng.
- Khi hai nguồn có giá trị mâu thuẫn, có thể ghi log tên thuộc tính và nguồn cấu hình nhưng không ghi secret.
- Hạn chế nhiều nguồn cùng điều khiển một giá trị nếu không cần thiết.

## 6. Ví dụ: ứng dụng Java đọc cấu hình bên ngoài

Một cách đơn giản là lấy cấu hình từ biến môi trường và kiểm tra ngay khi ứng dụng khởi động:

~~~java
public final class DatabaseConfig {
    private final String host;
    private final int port;
    private final String database;

    public DatabaseConfig() {
        this.host = required("DB_HOST");
        this.port = Integer.parseInt(
            System.getenv().getOrDefault("DB_PORT", "5432")
        );
        this.database = required("DB_NAME");

        if (port < 1 || port > 65535) {
            throw new IllegalArgumentException("DB_PORT is out of range");
        }
    }

    private static String required(String name) {
        String value = System.getenv(name);
        if (value == null || value.trim().isEmpty()) {
            throw new IllegalStateException(
                "Missing required configuration: " + name
            );
        }
        return value;
    }

    public String host() { return host; }
    public int port() { return port; }
    public String database() { return database; }
}
~~~

Ví dụ chỉ minh họa cách đọc và kiểm tra cấu hình không bí mật. Trong ứng dụng thực tế, nên dùng framework cấu hình phù hợp, kiểm tra định dạng hostname, timeout, pool size và các thuộc tính bắt buộc khác. Password cần được lấy qua secret manager hoặc cơ chế secret của nền tảng, không nên thêm getter để in password ra log.

Một nguyên tắc hữu ích là **fail fast**: nếu thiếu cấu hình bắt buộc hoặc giá trị không hợp lệ, ứng dụng báo lỗi rõ ràng và không nhận traffic. Việc khởi động với endpoint mặc định sai có thể khiến dịch vụ kết nối nhầm hệ thống.

## 7. Secret và danh tính workload

Secret cần được quản lý khác với cấu hình thông thường. Các ví dụ gồm:

- Mật khẩu database.
- API token hoặc OAuth client secret.
- Private key và chứng thư có khóa riêng.
- Credential truy cập registry hoặc hệ thống bên ngoài.

Quy trình nên ưu tiên:

1. Gán danh tính cho workload, chẳng hạn service account, instance role hoặc managed identity.
2. Cấp quyền tối thiểu để danh tính đó chỉ đọc đúng secret cần dùng.
3. Khi ứng dụng khởi động, dùng SDK hoặc agent được hỗ trợ để lấy secret từ secret manager.
4. Giữ secret trong bộ nhớ hoặc mount vào file với quyền đọc hạn chế theo yêu cầu ứng dụng.
5. Tránh ghi secret vào log, trace, metric label, exception message hoặc crash dump.
6. Theo dõi việc đọc secret và xoay vòng khi có dấu hiệu lộ hoặc đến kỳ thay đổi.

Ví dụ luồng truy cập:

~~~mermaid
sequenceDiagram
    participant App as Ứng dụng
    participant Id as Workload identity
    participant SM as Secret manager
    participant DB as Database
    App->>Id: Yêu cầu token theo danh tính workload
    Id-->>App: Token ngắn hạn
    App->>SM: Đọc secret với token
    SM-->>App: Secret được cấp quyền
    App->>DB: Kết nối bằng credential
    DB-->>App: Kết nối được xác thực
~~~

Danh tính workload giúp giảm nhu cầu nhúng access key dài hạn vào image hoặc file triển khai. Token ngắn hạn cũng cần được bảo vệ trong quá trình sử dụng; không nên đưa token vào log hoặc truyền qua kênh không an toàn.

### Vì sao không nên đóng gói secret vào image?

Image thường được sao chép giữa vùng, tài khoản, pipeline và môi trường. Nếu secret nằm trong image, bất kỳ ai có quyền tải hoặc khởi chạy image có thể tìm cách trích xuất nó. Xóa secret khỏi file ở lớp cuối của image cũng chưa chắc loại bỏ được dữ liệu ở các layer trước.

Khi nghi ngờ secret đã bị đóng gói vào image, cần xem đó là khả năng lộ credential: thu hồi hoặc xoay vòng secret, xây dựng image sạch và kiểm tra lịch sử phân phối. Không chỉ xóa dòng cấu hình trong image mới.

## 8. Cấu hình trong container và Kubernetes

### 8.1. Docker

Docker cho phép truyền cấu hình bằng biến môi trường hoặc mount file:

~~~bash
docker run --rm \
  -e APP_ENV=production \
  -e DB_HOST=db-prod.internal \
  -e DB_PORT=5432 \
  -v /etc/orders/config.yaml:/app/config/config.yaml:ro \
  orders-service:1.8.2
~~~

Trong ví dụ, image orders-service:1.8.2 không cần thay đổi giữa staging và production. Giá trị môi trường và file được cung cấp khi chạy container. Ứng dụng phải được cấu hình để đọc file tại đường dẫn /app/config/config.yaml; chỉ mount file không tự làm ứng dụng nạp nội dung đó.

Không nên đưa password trực tiếp vào lệnh -e trong shell dùng chung hoặc hệ thống ghi lại lịch sử lệnh. Với secret, hãy dùng cơ chế secret được nền tảng điều phối hỗ trợ hoặc một secret manager.

### 8.2. Kubernetes ConfigMap

ConfigMap lưu dữ liệu cấu hình không bí mật để Pod sử dụng qua biến môi trường hoặc volume mount.

~~~yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: orders-config
data:
  APP_ENV: production
  LOG_LEVEL: INFO
  DB_HOST: db-prod.internal
  DB_PORT: "5432"
~~~

Deployment có thể đưa các giá trị này vào container:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders
spec:
  replicas: 3
  selector:
    matchLabels:
      app: orders
  template:
    metadata:
      labels:
        app: orders
    spec:
      containers:
        - name: app
          image: registry.example.com/orders:1.8.2
          envFrom:
            - configMapRef:
                name: orders-config
          ports:
            - containerPort: 8080
~~~

ConfigMap phù hợp với endpoint, mức log và tham số không bí mật. Không nên dùng ConfigMap để lưu mật khẩu hoặc token.

### 8.3. Kubernetes Secret

Secret dành cho dữ liệu nhạy cảm như password hoặc token:

~~~yaml
apiVersion: v1
kind: Secret
metadata:
  name: orders-db-credentials
type: Opaque
stringData:
  username: orders_app
  password: REPLACE_WITH_SECRET
~~~

Có thể tham chiếu một trường Secret vào biến môi trường:

~~~yaml
env:
  - name: DB_USERNAME
    valueFrom:
      secretKeyRef:
        name: orders-db-credentials
        key: username
  - name: DB_PASSWORD
    valueFrom:
      secretKeyRef:
        name: orders-db-credentials
        key: password
~~~

Các đoạn YAML chỉ minh họa cấu trúc. Không commit password thật vào Git. Trường stringData giúp nhập giá trị dạng chuỗi; Kubernetes sẽ chuyển đổi khi lưu đối tượng Secret. Dữ liệu Secret trong manifest/API thường được biểu diễn bằng base64, nhưng base64 chỉ là mã hóa biểu diễn, không phải mã hóa bảo mật. Cần cấu hình encryption at rest cho datastore của cluster, giới hạn RBAC, bảo vệ backup và cân nhắc tích hợp external secret manager.

Nếu workload dùng CSI driver hoặc external secret operator, có thể mount secret từ hệ thống bên ngoài. Cần kiểm tra cơ chế cập nhật và cách ứng dụng đọc lại file sau khi secret được xoay vòng.

### 8.4. Cập nhật cấu hình và rollout Pod

Cách ứng dụng nhận cấu hình phụ thuộc nguồn:

- Biến môi trường được gán khi container khởi chạy; Pod hiện tại không tự nhận giá trị mới chỉ vì ConfigMap thay đổi.
- ConfigMap/Secret được mount thành volume có thể được cập nhật theo cơ chế của Kubernetes, nhưng ứng dụng cần đọc lại file hoặc được restart để áp dụng.
- ConfigMap/Secret dùng qua subPath có hành vi cập nhật khác; không nên giả định file mount sẽ tự thay đổi.
- Một số ứng dụng chỉ đọc cấu hình một lần khi khởi động, do đó cần rollout Pod để nạp giá trị mới.

Có thể dùng checksum cấu hình trong Pod template hoặc công cụ rollout để tạo Pod mới khi cấu hình thay đổi. Trước khi triển khai, hãy xác định ứng dụng hỗ trợ reload động hay cần restart.

## 9. Thay đổi cấu hình an toàn

Thay đổi cấu hình có thể gây tác động tương tự thay đổi mã nguồn. Một endpoint sai, pool size quá lớn hoặc timeout không phù hợp có thể làm dịch vụ mất kết nối hoặc cạn tài nguyên.

Quy trình đề xuất:

1. **Tạo thay đổi có truy vết:** lưu người thay đổi, lý do, môi trường, phiên bản và thời điểm.
2. **Kiểm tra schema:** xác nhận trường bắt buộc, kiểu dữ liệu, giới hạn số và định dạng.
3. **Kiểm tra liên kết:** xác nhận endpoint, DNS, chứng thư, quyền IAM và dependency có thể truy cập.
4. **Triển khai thử:** áp dụng cho một instance hoặc nhóm canary.
5. **Theo dõi:** kiểm tra lỗi, độ trễ, tỷ lệ kết nối, log và metric.
6. **Mở rộng:** rollout theo từng nhóm nếu kết quả đạt yêu cầu.
7. **Rollback:** khôi phục phiên bản cấu hình trước nếu có lỗi.
8. **Ghi nhận:** cập nhật inventory và trạng thái cấu hình thực tế.

Không nên sửa trực tiếp cấu hình trên từng máy mà không cập nhật nguồn quản lý chuẩn. Cách sửa thủ công dễ tạo configuration drift: các máy cùng vai trò nhưng chạy với giá trị khác nhau.

## 10. Cấu hình tĩnh và cấu hình động

Không phải cấu hình nào cũng cần cập nhật ngay khi ứng dụng đang chạy.

**Cấu hình tĩnh** thường được đọc lúc khởi động, ví dụ port lắng nghe, pool size hoặc cấu hình thread. Thay đổi chúng thường cần restart hoặc rollout.

**Cấu hình động** có thể được ứng dụng tải lại trong lúc chạy, ví dụ feature flag, ngưỡng giới hạn hoặc danh sách chặn. Ứng dụng phải được thiết kế để kiểm tra phiên bản mới, xác thực giá trị và áp dụng an toàn.

| Tiêu chí | Cấu hình tĩnh | Cấu hình động |
|---|---|---|
| Thời điểm áp dụng | Thường lúc khởi động | Có thể trong lúc chạy |
| Cách cập nhật | Restart/redeploy hoặc khởi động lại tiến trình | Polling, push event, watcher hoặc API |
| Độ phức tạp | Thấp hơn | Cao hơn do cần đồng bộ và xử lý lỗi |
| Rủi ro | Gián đoạn ngắn khi rollout | Trạng thái giữa instance có thể lệch nếu cập nhật không đồng bộ |
| Ví dụ | Port, heap size, DB pool size | Feature flag, ngưỡng nghiệp vụ, danh sách cho phép |

Với cấu hình động, cần định nghĩa hành vi khi config service mất kết nối, phiên bản mới không hợp lệ hoặc hai lần cập nhật đến gần nhau. Ứng dụng nên giữ bản cấu hình hợp lệ cuối cùng hoặc chuyển về chế độ an toàn theo yêu cầu nghiệp vụ.

## 11. Kiểm tra cấu hình trước khi nhận traffic

Ứng dụng nên kiểm tra cấu hình ngay khi khởi động và trước khi báo trạng thái sẵn sàng.

Những kiểm tra hữu ích:

- Trường bắt buộc không được rỗng.
- Port nằm trong khoảng hợp lệ.
- Timeout và retry limit không âm hoặc quá lớn.
- Pool size phù hợp với giới hạn kết nối database.
- URL có scheme và hostname hợp lệ.
- Mức log thuộc tập giá trị được hỗ trợ.
- Feature flag có kiểu boolean hoặc enum đúng.
- Danh tính workload có thể truy cập secret và tài nguyên cần thiết.

Tách hai loại kiểm tra:

- **Liveness:** tiến trình còn hoạt động và không bị treo.
- **Readiness:** ứng dụng đã nạp cấu hình cần thiết và có thể nhận traffic.

Nếu thiếu secret hoặc không thể kết nối dependency bắt buộc, ứng dụng có thể không đạt readiness để tránh nhận yêu cầu rồi trả lỗi hàng loạt. Tuy nhiên, readiness không nên phụ thuộc quá chặt vào mọi dịch vụ phụ trợ không thiết yếu, nếu không một lỗi ở dependency phụ có thể làm toàn bộ workload bị loại khỏi traffic.

## 12. Lỗi thường gặp và cách tránh

**Hardcode endpoint hoặc credential trong mã nguồn:** tạo khác biệt giữa môi trường và tăng nguy cơ lộ secret. Đưa cấu hình ra nguồn bên ngoài, secret vào kho bí mật.

**Build image riêng cho từng môi trường:** làm artifact staging và production khác nhau, gây khó truy vết. Build một artifact có version rồi cung cấp cấu hình lúc triển khai.

**Đóng gói secret trong image hoặc layer build:** secret có thể còn trong layer cũ, cache hoặc registry. Xoay vòng credential đã lộ và build image sạch.

**Dùng biến môi trường cho mọi loại dữ liệu:** biến môi trường phù hợp với giá trị nhỏ và đơn giản, nhưng file mount hoặc config service phù hợp hơn với cấu trúc lớn và cập nhật phức tạp.

**Dùng Kubernetes Secret như thể base64 là mã hóa:** base64 không bảo vệ bí mật. Cấu hình encryption at rest, RBAC, audit và tích hợp secret manager.

**Thiếu quy tắc ưu tiên:** cùng một biến được đặt ở nhiều nguồn có thể tạo hành vi khó dự đoán. Ghi rõ nguồn chuẩn và thứ tự override.

**Thiếu xác thực đầu vào:** giá trị sai có thể làm ứng dụng chạy với cấu hình nguy hiểm. Kiểm tra schema và fail fast với trường bắt buộc.

**Thay đổi config mà không rollout hoặc reload:** tiến trình có thể tiếp tục dùng giá trị cũ. Xác định cơ chế áp dụng cho từng nguồn cấu hình.

**Sửa thủ công từng máy:** gây configuration drift. Quản lý cấu hình qua IaC, config service hoặc pipeline có truy vết.

**Ghi secret vào log để gỡ lỗi:** log thường được chuyển tới nhiều hệ thống và người dùng. Chỉ log tên trường, nguồn và trạng thái kiểm tra; che hoặc loại bỏ giá trị nhạy cảm.

## 13. Checklist thiết kế externalized configuration

- [ ] Đã phân loại mã nguồn, cấu hình không bí mật, secret và dữ liệu ứng dụng.
- [ ] Cùng một artifact được dùng cho các môi trường cần triển khai.
- [ ] Cấu hình có nguồn chuẩn và quy tắc ưu tiên rõ ràng.
- [ ] Giá trị bắt buộc được kiểm tra trước khi ứng dụng nhận traffic.
- [ ] Secret được lưu trong secret manager hoặc cơ chế secret phù hợp.
- [ ] Workload dùng danh tính riêng và quyền truy cập tối thiểu.
- [ ] Secret không xuất hiện trong Git, image, user data hoặc log.
- [ ] Cấu hình có version, audit và người chịu trách nhiệm.
- [ ] Đã xác định ứng dụng cần restart hay hỗ trợ reload khi cấu hình thay đổi.
- [ ] Có canary, theo dõi và rollback cho thay đổi quan trọng.
- [ ] Các môi trường được kiểm tra để phát hiện configuration drift.
- [ ] Readiness phản ánh khả năng phục vụ với cấu hình hiện tại.

Tách cấu hình khỏi image và mã nguồn giúp cùng một artifact chạy nhất quán ở nhiều môi trường. File cấu hình, biến môi trường và config service cung cấp tham số vận hành; secret manager cùng workload identity bảo vệ thông tin xác thực. Khi thiết kế nguồn cấu hình, thứ tự ưu tiên, kiểm tra đầu vào và quy trình rollout rõ ràng, nhóm vận hành có thể thay đổi môi trường an toàn mà không phải build lại ứng dụng cho mỗi thay đổi cấu hình.
