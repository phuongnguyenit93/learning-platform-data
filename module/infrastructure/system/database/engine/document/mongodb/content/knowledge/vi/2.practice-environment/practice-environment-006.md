# Đọc connection string MongoDB: `mongodb://`, `mongodb+srv://` và các tùy chọn URI

Connection string (chuỗi kết nối) là địa chỉ kèm cấu hình để ứng dụng hoặc công cụ như `mongosh` tìm đến MongoDB, xác thực, chọn các máy chủ phù hợp và thiết lập cách giao tiếp. Đọc đúng URI giúp phân biệt lỗi mạng, lỗi chứng chỉ, lỗi tài khoản và lỗi cấu hình cụm mà không phải thử thay đổi tùy tiện.

Trong bài này, ta sử dụng hai dạng URI: `mongodb://` (liệt kê máy chủ trực tiếp) và `mongodb+srv://` (khám phá máy chủ qua DNS). Các tên máy chủ `example.net` trong ví dụ chỉ mang tính minh họa; cần thay bằng địa chỉ thật của môi trường thực hành.

## 1. Cấu trúc tổng quát của connection string

### Dạng tiêu chuẩn: `mongodb://`

```text
mongodb://[username:password@]host1[:port1][,host2[:port2],...]/[database][?option1=value1&option2=value2]
└─scheme─┘ └────user info────┘ └──────────hosts───────────────┘ └─path──┘ └──────────query───────────────┘
```

| Thành phần | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `mongodb://` | Lược đồ kết nối tiêu chuẩn; khai báo máy chủ trực tiếp | `mongodb://` |
| `username:password@` | Thông tin xác thực, có thể không có nếu máy chủ cho phép truy cập không cần tài khoản | `reader:secret@` |
| `host:port` | Địa chỉ MongoDB và cổng TCP; cổng mặc định của MongoDB là `27017` | `localhost:27017` |
| Danh sách `host1,host2,...` | Nhiều địa chỉ hạt giống (seed hosts), thường dùng để khám phá replica set | `db1:27017,db2:27017` |
| `/database` | Tên cơ sở dữ liệu mặc định trong URI; có thể là nguồn xác thực mặc định nếu chưa đặt `authSource` | `/inventory` |
| `?key=value&...` | Các tùy chọn kết nối dạng cặp khóa–giá trị, cách nhau bởi `&` | `?tls=true&appName=demo` |

Đọc một URI minh họa:

```text
mongodb://reporter:p%40ss%3A2026@db1.example.net:27017/sales?authSource=admin&tls=true&appName=report-lab
```

- **Scheme:** `mongodb://`.
- **Tài khoản:** `reporter`; mật khẩu trong URI là `p%40ss%3A2026`, được giải mã thành `p@ss:2026`.
- **Đích:** máy chủ `db1.example.net`, cổng `27017`.
- **Database path:** `sales`.
- **Tùy chọn:** xác thực trên `admin`, bật TLS, đặt tên ứng dụng `report-lab`.

Chú ý sự khác nhau giữa **database path** và **authentication database**. Ví dụ `/sales?authSource=admin` có thể dùng `sales` cho thao tác dữ liệu, nhưng tra thông tin tài khoản ở `admin`. Nếu không có `authSource`, với cơ chế xác thực username/password thông thường, MongoDB dùng database trong path làm nguồn xác thực; nếu path không có database thì mặc định là `admin`. Một số cơ chế đặc biệt, chẳng hạn `MONGODB-X509`, có quy tắc riêng.

### Dạng DNS seed list: `mongodb+srv://`

```text
mongodb+srv://[username:password@]hostname/[database][?option1=value1&option2=value2]
```

Ví dụ:

```text
mongodb+srv://appuser:<password>@cluster.example.net/catalog?retryWrites=true&w=majority
```

`<password>` ở đây là ký hiệu chỗ cần thay, **không phải** mật khẩu thực tế và không được giữ nguyên dấu `<`/`>` khi sử dụng URI. Nếu mật khẩu có ký tự đặc biệt, phải mã hóa như phần tiếp theo.

Với `mongodb+srv://`, URI chỉ khai báo **một hostname**, **không viết cổng** và **không liệt kê nhiều host bằng dấu phẩy**. Driver tra cứu bản ghi DNS SRV (thường ở `_mongodb._tcp.cluster.example.net`) để lấy các máy chủ cùng cổng kết nối, đồng thời có thể đọc một số thiết lập từ DNS TXT. Máy chủ DNS phải được cấu hình phù hợp, nên không thể tùy ý đổi `mongodb://localhost` thành `mongodb+srv://localhost`.

## 2. Phân biệt `mongodb://` và `mongodb+srv://`

| Tiêu chí | `mongodb://` | `mongodb+srv://` |
| --- | --- | --- |
| Khai báo đích | Một hoặc nhiều `host[:port]` | Một hostname dùng để truy vấn DNS SRV |
| Nguồn danh sách máy chủ | Đọc trực tiếp từ URI, sau đó driver có thể khám phá topology | Đọc từ bản ghi SRV, sau đó driver khám phá topology |
| Cổng trong URI | Cho phép khai báo, không ghi thì mặc định `27017` | Không được khai báo cổng trong URI |
| DNS TXT | Không dùng để lấy tùy chọn URI | Có thể lấy một số tùy chọn được hỗ trợ |
| TLS mặc định | Thường tắt nếu URI/cấu hình không yêu cầu | Mặc định bật, trừ khi bị ghi đè rõ ràng |
| Thường gặp | MongoDB local, máy chủ riêng, replica set có danh sách seed | Cụm được cấu hình DNS SRV, thường gặp trên dịch vụ MongoDB quản lý |

**Chọn dạng nào?** Với MongoDB chạy trên máy cá nhân, bắt đầu từ `mongodb://localhost:27017`. Với cụm có URI `mongodb+srv://` do người quản trị hay nhà cung cấp cấp, nên dùng nguyên dạng đó: driver sẽ truy vấn DNS và chọn máy chủ thích hợp. Cả hai đều có thể kết nối an toàn khi được cấu hình TLS và xác thực phù hợp.

Luồng xử lý được giản lược như sau:

```text
Đọc URI
   |
   +-- mongodb:// ------> đọc host/cổng trong URI -------+
   |                                                      |
   +-- mongodb+srv:// --> tra DNS SRV/TXT ----------------+
                                                          |
                                          giải quyết TLS, xác thực, topology
                                                          |
                                          chọn máy chủ và mở kết nối
                                                          |
                                          gửi lệnh (ping, find, insert, ...)
```

## 3. Cách đọc những URI thường gặp

### 3.1. MongoDB local chưa bật xác thực

```text
mongodb://localhost:27017
```

URI dùng cho MongoDB chạy trên cùng máy với chương trình. Không thấy `username:password@` nghĩa là **URI không cung cấp thông tin đăng nhập**, chứ không có nghĩa mọi MongoDB đều chấp nhận truy cập ẩn danh.

### 3.2. Chỉ định database và nguồn xác thực

```text
mongodb://student:demoPass@localhost:27017/lab?authSource=admin
```

Ứng dụng thao tác với `lab`, còn tài khoản `student` được xác thực trên `admin`. Nếu thực tế tài khoản được tạo trong `lab`, phải dùng `authSource=lab` (hoặc cấu hình phù hợp); đổi database path một cách ngẫu nhiên không sửa được lỗi đăng nhập.

### 3.3. Replica set có nhiều máy chủ

```text
mongodb://db1.example.net:27017,db2.example.net:27017,db3.example.net:27017/orders?replicaSet=rs0&tls=true
```

Ba host là **điểm bắt đầu khám phá**, không bắt buộc là ba kết nối độc lập mà ứng dụng phải tự luân phiên. Driver nhận topology từ các máy chủ, phát hiện primary/secondary và chọn đích dựa trên yêu cầu đọc/ghi. `replicaSet=rs0` yêu cầu replica set có tên phù hợp; các tên host mà cụm quảng bá cũng phải được máy khách phân giải và truy cập được.

### 3.4. Cụm dùng DNS SRV

```text
mongodb+srv://reader:encodedPassword@cluster.example.net/analytics?authSource=admin&readPreference=secondaryPreferred
```

Driver tra DNS để tìm các thành viên cụm. `readPreference=secondaryPreferred` ưu tiên đọc từ secondary khi phù hợp nhưng có thể dùng primary; dữ liệu đọc từ secondary có thể chậm hơn dữ liệu mới ghi vì độ trễ sao chép. Không nên đặt tùy chọn này chỉ nhằm “tăng tốc” nếu bài toán cần đọc ngay dữ liệu vừa cập nhật.

## 4. Mã hóa ký tự đặc biệt trong username/password

Ký tự dùng để phân chia URI (`@`, `:`, `/`, `?`, `#`, `%`, ...) phải được **percent-encode** khi xuất hiện như dữ liệu của username hoặc password. Nếu không, parser có thể hiểu một phần mật khẩu thành host, path hoặc query.

| Ký tự thực | Giá trị viết trong URI |
| --- | --- |
| `@` | `%40` |
| `:` | `%3A` |
| `/` | `%2F` |
| `?` | `%3F` |
| `#` | `%23` |
| `%` | `%25` |
| `&` | `%26` |
| `+` | `%2B` |

Ví dụ mật khẩu gốc là `a@b:c/42`, phần password trong URI phải là `a%40b%3Ac%2F42`:

```text
mongodb://student:a%40b%3Ac%2F42@localhost:27017/lab?authSource=admin
```

Chỉ mã hóa **giá trị** cần truyền, không mã hóa dấu `://`, `@` ngăn cách userinfo và host hoặc dấu `&` phân cách các option. Một ký tự đã mã hóa thành `%40` không được mã hóa lần hai thành `%2540` nếu muốn khôi phục đúng `@`.

Nếu hostname là IPv6 literal, cần ngoặc vuông để phân biệt dấu `:` trong địa chỉ với dấu `:` trước cổng, chẳng hạn:

```text
mongodb://[::1]:27017/lab
```

**Bảo mật:** Không đưa URI chứa mật khẩu thật vào Git, README công khai, ảnh chụp terminal hoặc log. Hãy đọc từ biến môi trường, secret store hoặc cấu hình bí mật của môi trường chạy; khi chia sẻ lỗi, che username/password và mọi thông tin nhạy cảm trước.

## 5. Các nhóm tùy chọn URI quan trọng

Tùy chọn nối sau dấu `?`; nhiều tùy chọn được phân cách bằng `&`. Ví dụ:

```text
mongodb://localhost:27017/lab?appName=mongo-lab&serverSelectionTimeoutMS=5000&maxPoolSize=30
```

### 5.1. Xác thực và mã hóa kênh truyền

| Tùy chọn | Tác dụng | Ví dụ |
| --- | --- | --- |
| `authSource` | Database lưu thông tin xác thực cho cơ chế username/password thông thường | `authSource=admin` |
| `authMechanism` | Chọn cơ chế xác thực khi cần chỉ rõ; ví dụ SCRAM | `authMechanism=SCRAM-SHA-256` |
| `tls` | Bật/tắt TLS cho kết nối; tên tùy chọn `ssl` là dạng tương thích cũ | `tls=true` |
| `tlsCAFile` | Đường dẫn tệp CA tin cậy, được hỗ trợ tùy driver/công cụ | `tlsCAFile=/path/to/ca.pem` |
| `appName` | Gửi tên ứng dụng trong metadata kết nối để thuận tiện theo dõi | `appName=order-service` |

Với URI `mongodb+srv://`, TLS được bật mặc định nếu không bị ghi đè. Với `mongodb://`, hãy bật `tls=true` khi kết nối đến máy chủ triển khai TLS, đặc biệt qua mạng không tin cậy. Một số driver hỗ trợ chứng chỉ khách hàng, thời gian bắt tay và tùy chọn TLS bằng đối tượng cấu hình riêng thay vì truyền mọi thứ qua URI; tra tài liệu phiên bản driver đang dùng.

Không dùng `tlsAllowInvalidCertificates=true`, `tlsAllowInvalidHostnames=true` hoặc `tlsInsecure=true` như cách “sửa nhanh” lỗi chứng chỉ. Những lựa chọn này làm suy yếu việc xác minh danh tính máy chủ; cần sửa chứng chỉ, CA hoặc hostname cho khớp.

### 5.2. Nhận diện cụm và định tuyến kết nối

| Tùy chọn | Tác dụng | Lưu ý |
| --- | --- | --- |
| `replicaSet` | Chỉ định tên replica set kỳ vọng | Phải khớp tên replica set thực tế |
| `directConnection` | Buộc driver làm việc trực tiếp với một máy chủ, không khám phá toàn cụm như thông thường | Chỉ dùng cho tình huống có chủ đích, thường là một host |
| `loadBalanced` | Bật chế độ topology load-balanced khi phía máy chủ/điểm cuối hỗ trợ | Không thay thế cho thiết lập replica set thông thường |
| `srvServiceName` | Đổi tên dịch vụ DNS dùng trong truy vấn SRV nếu driver hỗ trợ | Chủ yếu dành cho cấu hình SRV đặc biệt |

Ví dụ `directConnection=true` có thể hữu ích khi kiểm tra một MongoDB đơn lẻ trong lab. Nếu dùng nhầm với replica set nhiều node, ứng dụng có thể không tự tìm primary mới khi topology thay đổi.

### 5.3. Hành vi đọc và ghi

| Tùy chọn | Tác dụng | Ví dụ |
| --- | --- | --- |
| `readPreference` | Chọn ưu tiên máy chủ cho thao tác đọc: `primary`, `primaryPreferred`, `secondary`, `secondaryPreferred`, `nearest` | `readPreference=primary` |
| `readConcernLevel` | Mức bảo đảm nhất quán/hiển thị của dữ liệu đọc, ví dụ `local`, `majority` | `readConcernLevel=majority` |
| `w` | Write concern: mức xác nhận ghi, ví dụ `1`, `majority` | `w=majority` |
| `wTimeoutMS` | Giới hạn thời gian chờ đáp ứng write concern | `wTimeoutMS=5000` |
| `retryWrites` | Cho phép driver tự thử lại một số thao tác ghi đủ điều kiện khi gặp lỗi có thể thử lại | `retryWrites=true` |
| `retryReads` | Cho phép thử lại một số thao tác đọc đủ điều kiện | `retryReads=true` |

`w=majority` chỉ nói về mức xác nhận ghi theo replica set; nó không tự bảo đảm mọi lần đọc sẽ thấy ngay giá trị mới nhất. Các thuộc tính `readPreference`, `readConcern` và `writeConcern` tác động lên các khía cạnh khác nhau của hệ thống phân tán. Đồng thời, việc retry có giới hạn theo loại thao tác, khả năng hỗ trợ của máy chủ và phiên bản driver.

### 5.4. Pool kết nối và timeout

| Tùy chọn | Tác dụng | Đơn vị |
| --- | --- | --- |
| `maxPoolSize` | Số kết nối tối đa trong một pool đến một máy chủ | Số kết nối |
| `minPoolSize` | Số kết nối tối thiểu mà pool cố gắng duy trì | Số kết nối |
| `maxConnecting` | Giới hạn số kết nối được tạo đồng thời trong một pool (nếu driver hỗ trợ) | Số kết nối |
| `waitQueueTimeoutMS` | Thời gian tối đa chờ lấy kết nối từ pool (nếu driver hỗ trợ) | Millisecond |
| `serverSelectionTimeoutMS` | Khoảng thời gian tìm một máy chủ phù hợp cho một thao tác | Millisecond |
| `connectTimeoutMS` | Giới hạn thời gian thiết lập kết nối mạng | Millisecond |
| `socketTimeoutMS` | Giới hạn chờ hoạt động đọc/ghi mạng trên socket (hành vi cụ thể tùy driver) | Millisecond |

Ba loại timeout thường bị nhầm:

- **Server selection timeout:** driver chưa tìm thấy node có thể phục vụ yêu cầu.
- **Connect timeout:** không hoàn tất việc mở kết nối TCP đến node được chọn trong thời gian cho phép.
- **Socket timeout:** kết nối đã mở nhưng một hoạt động mạng không hoàn thành đúng hạn.

Giảm timeout quá thấp có thể gây lỗi giả khi mạng chậm; tăng timeout quá cao lại kéo dài thời gian chờ của request. Đặt giá trị dựa trên môi trường và yêu cầu của ứng dụng. Pool kết nối thường được giữ bởi `MongoClient` dùng chung, thay vì tạo một client mới cho mỗi lần truy vấn.

## 6. Tìm hiểu DNS SRV và TXT thực tế

Giả sử URI là:

```text
mongodb+srv://user:password@cluster.example.net/shop?retryWrites=true
```

Driver sẽ tìm các bản ghi tương ứng với tên dịch vụ MongoDB, chẳng hạn:

```text
_mongodb._tcp.cluster.example.net.  SRV  0 0 27017 db-a.example.net.
_mongodb._tcp.cluster.example.net.  SRV  0 0 27017 db-b.example.net.
_mongodb._tcp.cluster.example.net.  SRV  0 0 27017 db-c.example.net.
```

Đây chỉ là dữ liệu DNS minh họa. Driver dùng hostname/port trong các bản ghi SRV để khởi tạo khám phá cụm; bản ghi TXT của hostname gốc có thể cung cấp một nhóm tùy chọn hỗ trợ như `authSource` hoặc `replicaSet`. Driver phải kiểm tra các ràng buộc DNS của chuẩn SRV; không phải mọi bản ghi TXT tùy ý đều trở thành tùy chọn hợp lệ.

Hệ quả thực hành:

1. Máy khách cần phân giải được DNS SRV/TXT, không chỉ bản ghi A/AAAA thông thường.
2. Các hostname do SRV trả về phải truy cập được từ mạng của ứng dụng.
3. Tên miền, CA và chứng chỉ phải phù hợp với cấu hình TLS.
4. Những tùy chọn ghi trực tiếp trên URI sẽ được driver xử lý cùng cấu hình DNS theo quy tắc của driver; cần kiểm tra khi có xung đột.

Nếu `mongodb://host:27017` hoạt động nhưng `mongodb+srv://host` lỗi, hãy kiểm tra SRV/TXT và các giới hạn cú pháp trước khi thay đổi tài khoản.

## 7. Thực hành kết nối bằng `mongosh` và Java

### 7.1. Kiểm tra kết nối từ `mongosh`

Kết nối local:

```bash
mongosh "mongodb://localhost:27017"
```

Trong shell:

```javascript
db.adminCommand({ ping: 1 })
```

Phản hồi có `ok: 1` cho biết lệnh `ping` được máy chủ xử lý thành công. Nó chưa khẳng định tài khoản có quyền đọc/ghi mọi collection; cần thử riêng các thao tác theo phân quyền của ứng dụng.

Với URI có thông tin nhạy cảm, tốt hơn hãy truyền thông qua biến môi trường hoặc cơ chế cung cấp bí mật của máy, tránh lưu mật khẩu vào lịch sử lệnh shell.

### 7.2. Dùng MongoDB Java Sync Driver

Ví dụ dưới đây đọc URI và tên database từ biến môi trường, tạo client, thực hiện `ping`, rồi đóng tài nguyên:

```java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoDatabase;
import org.bson.Document;

public class MongoConnectionExample {
    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalStateException("Missing MONGODB_URI");
        }

        String databaseName = System.getenv().getOrDefault("MONGODB_DATABASE", "lab");

        try (MongoClient client = MongoClients.create(uri)) {
            MongoDatabase database = client.getDatabase(databaseName);
            Document result = database.runCommand(new Document("ping", 1));
            System.out.println("MongoDB ping: " + result.get("ok"));
        }
    }
}
```

Cần thêm dependency `mongodb-driver-sync` với phiên bản tương thích vào build của ứng dụng. Lệnh `MongoClients.create(uri)` tạo cấu hình client, còn việc truy cập mạng có thể chỉ được thực hiện khi gửi thao tác như `ping`; do đó chỉ tạo đối tượng client chưa đủ để chứng minh URI hợp lệ về mặt kết nối.

Trong dịch vụ chạy lâu, nên dùng một `MongoClient` xuyên suốt vòng đời ứng dụng vì client quản lý connection pool và an toàn cho truy cập đồng thời; đóng client khi ứng dụng dừng. Ví dụ `try-with-resources` ở trên phù hợp cho chương trình kiểm tra ngắn.

## 8. Tình huống lỗi và cách khoanh vùng

| Dấu hiệu | Khả năng cần kiểm tra | Cách kiểm tra hợp lý |
| --- | --- | --- |
| `Invalid connection string` hoặc lỗi parse URI | Thiếu dấu `/`, sai dấu `?`/`&`, ký tự mật khẩu chưa encode, `mongodb+srv` có port/nhiều host | Tách URI thành scheme, userinfo, host, path và query; kiểm tra mã hóa từng giá trị |
| Không tìm thấy DNS SRV | Domain không có bản ghi `_mongodb._tcp` hoặc DNS chặn truy vấn | Kiểm tra bản ghi DNS SRV/TXT và DNS resolver từ chính môi trường chạy |
| `ServerSelectionTimeout` | Không tìm được node phù hợp; sai host/port, firewall, IP allowlist, replica set hoặc TLS | Xem chi tiết lỗi driver, kiểm tra network đến các host được cụm công bố |
| `Authentication failed` | Sai username/password, sai `authSource`, cơ chế xác thực không phù hợp | Xác minh nơi tạo tài khoản và mã hóa ký tự đặc biệt trong password |
| TLS handshake/certificate error | Chưa bật TLS, CA chưa tin cậy, hostname không khớp chứng chỉ | Kiểm tra chế độ TLS và chuỗi chứng chỉ đúng với tên máy chủ |
| Ghi lỗi `not primary` hoặc không tìm thấy writable server | Topology thay đổi, kết nối nhầm secondary, `directConnection` không phù hợp | Kiểm tra danh sách node, `replicaSet`, khả năng khám phá primary |
| Kết nối được nhưng không có dữ liệu hoặc bị từ chối quyền | Chọn nhầm database/collection hoặc tài khoản thiếu quyền | Kiểm tra database được sử dụng và roles; đừng nhầm với `authSource` |

Trong môi trường có container, `localhost` luôn chỉ **chính container hoặc máy đang chạy client**, không tự trỏ đến một container MongoDB khác. Cần dùng tên dịch vụ Docker/network hoặc địa chỉ mà client thật sự nhìn thấy. Tương tự, nếu replica set quảng bá hostname nội bộ, máy bên ngoài có thể kết nối tới một seed host nhưng không liên lạc được với các member được khám phá.

## 9. Bài tập đọc và phân tích URI

**Bài tập 1.** Phân tích:

```text
mongodb://user:pa%23ss@mongo.example.net:27018/training?authSource=admin&tls=true
```

Câu hỏi: host và port là gì, mật khẩu sau giải mã là gì, database path và authentication database có giống nhau không?

**Đáp án:** host `mongo.example.net`, cổng `27018`; mật khẩu là `pa#ss`; database path là `training`, còn authentication database là `admin`, nên không giống nhau.

**Bài tập 2.** Phát hiện lỗi trong URI:

```text
mongodb+srv://db1.example.net:27017,db2.example.net:27017/catalog
```

**Đáp án:** `mongodb+srv://` chỉ nhận một hostname và không ghi cổng. Nếu muốn kê khai `db1` và `db2` trực tiếp, phải dùng `mongodb://`. Nếu muốn dùng SRV, cần một hostname có DNS SRV/TXT được cấu hình đúng.

**Bài tập 3.** Hai URI này có thể khác nhau ở đâu?

```text
mongodb://student:secret@localhost:27017/lab
mongodb://student:secret@localhost:27017/lab?authSource=admin
```

**Đáp án:** cả hai có database path `lab`, nhưng URI đầu thường xác thực `student` trên `lab` còn URI sau trên `admin`. URI đúng phụ thuộc vào database nơi tài khoản được tạo.

## 10. Ghi nhớ khi cấu hình môi trường thực hành

- Đọc URI theo thứ tự **scheme → credentials → hosts → database path → options**; không suy ra quyền truy cập chỉ từ tên database.
- `mongodb://` dùng danh sách host/cổng; `mongodb+srv://` dùng DNS SRV/TXT, một hostname và mặc định TLS.
- Percent-encode ký tự đặc biệt trong username/password, tránh encode nhầm dấu phân tách URI.
- Xác định rõ `authSource`, TLS, replica set và khả năng truy cập các hostname do cụm cung cấp trước khi điều chỉnh timeout.
- Giữ URI chứa bí mật ngoài mã nguồn, sử dụng `MongoClient` có pool phù hợp và kiểm tra kết nối bằng một thao tác thực tế như `ping`.

Khi đọc được từng thành phần theo cách này, connection string trở thành bản mô tả có thể kiểm tra được về **địa chỉ**, **danh tính**, **bảo mật**, **định tuyến** và **hành vi của driver**.
