# URI bolt/neo4j, cổng kết nối và thông tin xác thực

Để Spring Data Neo4j làm việc với cơ sở dữ liệu, ứng dụng Java phải biết máy chủ Neo4j nằm ở đâu, dùng giao thức nào, kết nối qua cổng nào và xác thực bằng tài khoản nào. Những thông tin này được gom trong connection URI và cấu hình xác thực của Neo4j Java Driver. Spring Boot đưa chúng vào cấu hình `spring.neo4j`, sau đó Spring Data Neo4j sử dụng driver để thực hiện truy vấn Cypher và ánh xạ dữ liệu.

Trong bài này, ta sẽ phân biệt kết nối Bolt với giao diện HTTP của Neo4j, hiểu các scheme `bolt://` và `neo4j://`, chọn cổng đúng, cấu hình TLS và thông tin xác thực, rồi kiểm tra kết nối từ ứng dụng Spring Boot.

## 1. Một kết nối Neo4j gồm những thành phần nào?

Một connection URI thông thường có dạng:

```text
<scheme>://<host>[:<port>]
```

Trong đó:

- `scheme` chọn giao thức, cơ chế định tuyến và cách mã hóa kết nối.
- `host` là tên DNS hoặc địa chỉ IP mà tiến trình ứng dụng có thể truy cập.
- `port` là cổng dịch vụ. Nếu bỏ qua, driver dùng cổng mặc định của scheme.

Ví dụ kết nối tới Neo4j đang chạy trên cùng máy với ứng dụng:

```text
bolt://localhost:7687
```

Ở đây, `bolt` là scheme, `localhost` là máy chủ và `7687` là cổng Bolt. URI này chỉ cho driver biết cách tìm và kết nối tới máy chủ. Tên người dùng, mật khẩu và cơ sở dữ liệu đích được cấu hình riêng.

Một kết nối hoàn chỉnh còn phụ thuộc vào các điều kiện sau:

1. Tiến trình Neo4j đang chạy và dịch vụ Bolt được bật.
2. Máy chạy ứng dụng phân giải được `host` và có đường mạng tới `port`.
3. Cấu hình TLS của client tương thích với chứng chỉ phía máy chủ nếu dùng kết nối mã hóa.
4. Tài khoản được cung cấp có thông tin xác thực hợp lệ và đủ quyền trên database cần truy cập.

Kết nối thành công ở một lớp chưa chứng minh các lớp còn lại đều đúng. Chẳng hạn, mở được Neo4j Browser qua HTTP không đồng nghĩa ứng dụng Java đã truy cập được cổng Bolt.

## 2. Phân biệt Bolt và HTTP

Neo4j cung cấp nhiều cổng cho các mục đích khác nhau. Với cài đặt phổ biến, các cổng mặc định là:

| Cổng | Giao thức/dịch vụ | Mục đích thường dùng |
|---|---|---|
| `7687` | Bolt | Kết nối nhị phân từ Neo4j Java Driver, Spring Data Neo4j và các ứng dụng driver khác |
| `7474` | HTTP | Giao diện web Neo4j Browser và HTTP endpoint khi được bật |
| `7473` | HTTPS | Truy cập web/HTTP được mã hóa TLS khi được bật |

Ứng dụng Spring Data Neo4j dùng Java Driver và kết nối qua Bolt, thường là cổng `7687`. Neo4j Browser là giao diện web, thường truy cập qua `http://localhost:7474` trong môi trường phát triển. Hai dịch vụ có mục đích khác nhau.

Ví dụ, cấu hình sau trỏ nhầm ứng dụng Java vào cổng HTTP:

```text
bolt://localhost:7474
```

URI này khai báo giao thức Bolt nhưng lại dùng cổng HTTP mặc định. Driver sẽ không thể hoàn tất bắt tay Bolt với dịch vụ HTTP. Cấu hình đúng cho máy Neo4j cục bộ thường là:

```text
bolt://localhost:7687
```

Không cần mở tất cả các cổng cho mọi ứng dụng. Nếu chỉ có backend Spring Boot truy cập cơ sở dữ liệu, mạng giữa backend và Neo4j cần cho phép Bolt. Cổng HTTP/HTTPS chỉ cần mở cho người dùng hoặc hệ thống thật sự truy cập các endpoint web tương ứng.

## 3. Chọn scheme `bolt://` hay `neo4j://`

Neo4j Java Driver hỗ trợ hai kiểu kết nối cơ bản:

| Scheme | Hành vi | Trường hợp thường dùng |
|---|---|---|
| `bolt://` | Kết nối trực tiếp tới máy chủ được chỉ định | Máy Neo4j đơn lẻ hoặc khi ứng dụng cần kết nối trực tiếp tới một endpoint cụ thể |
| `neo4j://` | Kết nối có hỗ trợ routing; driver lấy thông tin định tuyến từ máy chủ và chọn máy phù hợp | Cụm Neo4j hoặc triển khai cần routing theo vai trò máy chủ |

Với Neo4j cục bộ dạng standalone, URI sau là lựa chọn đơn giản:

```text
bolt://localhost:7687
```

URI sau dùng cơ chế routing:

```text
neo4j://localhost:7687
```

Trong môi trường cụm, `neo4j://` cho phép driver nhận routing table và gửi thao tác đọc/ghi tới máy phù hợp theo topology của cụm. Ứng dụng không cần tự quản lý danh sách máy đọc và máy ghi trong từng truy vấn.

Routing chỉ hoạt động tốt nếu các địa chỉ mà Neo4j quảng bá cho driver đều có thể truy cập từ mạng của ứng dụng. Một lỗi thường gặp khi chạy trong Docker hoặc sau NAT là ứng dụng kết nối được seed address ban đầu nhưng không kết nối được địa chỉ nội bộ mà cụm trả về. Khi triển khai routing, hãy kiểm tra cấu hình advertised address, DNS, firewall và định tuyến mạng cho tất cả máy trong cụm.

Chọn scheme theo kiến trúc triển khai. Dùng `bolt://` cho kết nối trực tiếp khi đó là chủ đích; dùng `neo4j://` khi muốn driver thực hiện routing. Scheme không thay thế việc cấu hình đúng host, cổng và quyền truy cập.

## 4. TLS và các biến thể URI

Khi dữ liệu đi qua mạng, TLS giúp mã hóa đường truyền và xác thực danh tính máy chủ. Driver cung cấp các biến thể scheme sau:

| Scheme | Kết nối | Ý nghĩa chứng chỉ |
|---|---|---|
| `bolt://` | Bolt trực tiếp, không bật TLS theo scheme | Phù hợp cho mạng phát triển tin cậy hoặc cấu hình không mã hóa được cho phép |
| `neo4j://` | Bolt có routing, không bật TLS theo scheme | Dùng khi routing được cấu hình mà môi trường không yêu cầu TLS |
| `bolt+s://` | Bolt trực tiếp, có TLS | Xác minh chứng chỉ theo chuỗi CA tin cậy |
| `neo4j+s://` | Routing, có TLS | Xác minh chứng chỉ theo chuỗi CA tin cậy |
| `bolt+ssc://` | Bolt trực tiếp, có TLS | Chấp nhận chứng chỉ tự ký; thường chỉ dùng trong môi trường kiểm thử có kiểm soát |
| `neo4j+ssc://` | Routing, có TLS | Chấp nhận chứng chỉ tự ký; thường chỉ dùng trong môi trường kiểm thử có kiểm soát |

Ví dụ URI dùng TLS với chứng chỉ được CA tin cậy cấp:

```text
neo4j+s://graph.example.com:7687
```

Ví dụ dùng kết nối Bolt trực tiếp với chứng chỉ tự ký:

```text
bolt+ssc://localhost:7687
```

Hậu tố `+s` và `+ssc` đều bật mã hóa TLS, nhưng khác nhau ở cách tin cậy chứng chỉ. `+s` xác minh chứng chỉ theo CA tin cậy; `+ssc` chấp nhận chứng chỉ tự ký. Không dùng chế độ chấp nhận chứng chỉ tự ký như một cách né lỗi chứng chỉ trong production. Với môi trường thật, hãy cài đặt chứng chỉ hợp lệ và cấu hình trust chain đúng.

Các scheme TLS vẫn thường sử dụng cổng Bolt `7687`, trừ khi máy chủ được cấu hình một cổng khác. TLS bảo vệ đường truyền, nhưng không thay thế xác thực tài khoản, phân quyền database hoặc quản lý bí mật.

## 5. Cài Neo4j cục bộ và ánh xạ cổng

Khi chạy Neo4j bằng Docker, có thể ánh xạ cổng Bolt và cổng HTTP từ container ra máy host. Ví dụ Compose tối giản cho môi trường học tập:

```yaml
services:
  neo4j:
    image: neo4j:5
    environment:
      NEO4J_AUTH: neo4j/${NEO4J_PASSWORD}
    ports:
      - "7474:7474"
      - "7687:7687"
    volumes:
      - neo4j_data:/data

volumes:
  neo4j_data:
```

Tạo biến môi trường `NEO4J_PASSWORD` trước khi chạy Compose. Giá trị ví dụ ở đây được thay bằng mật khẩu riêng của môi trường; không đưa mật khẩu thật vào Git. `NEO4J_AUTH` thiết lập tài khoản ban đầu cho image Neo4j. Nếu volume đã chứa một database được khởi tạo trước đó, thay đổi biến môi trường không nhất thiết đặt lại mật khẩu đã lưu trong database.

Với ánh xạ `"7687:7687"`, tiến trình chạy trên máy host kết nối tới `localhost:7687`. Nếu Spring Boot cũng chạy trong cùng Docker Compose network, nó nên kết nối bằng tên service:

```text
bolt://neo4j:7687
```

Trong container backend, `localhost` trỏ về chính container backend, không phải container Neo4j. Đây là nguyên nhân phổ biến khiến cấu hình chạy được trên máy cá nhân nhưng thất bại khi đóng gói ứng dụng thành container.

Sau khi container khởi động, mở `http://localhost:7474` để vào Neo4j Browser. Dùng cổng Bolt `7687` cho backend Java. Trong môi trường thật, chỉ công khai các cổng cần thiết và giới hạn nguồn truy cập bằng cấu hình mạng hoặc firewall.

## 6. Cấu hình URI và thông tin xác thực trong Spring Boot

Spring Boot tự cấu hình Neo4j Java Driver từ các thuộc tính `spring.neo4j`. Spring Data Neo4j dùng driver đó cho repository và các thao tác với graph. Một cấu hình `application.yml` có thể viết như sau:

```yaml
spring:
  neo4j:
    uri: ${NEO4J_URI:bolt://localhost:7687}
    authentication:
      username: ${NEO4J_USERNAME:neo4j}
      password: ${NEO4J_PASSWORD}
  data:
    neo4j:
      database: ${NEO4J_DATABASE:neo4j}
```

Ý nghĩa từng thuộc tính:

- `spring.neo4j.uri`: URI kết nối gồm scheme, host và port.
- `spring.neo4j.authentication.username`: tên tài khoản Neo4j.
- `spring.neo4j.authentication.password`: mật khẩu của tài khoản.
- `spring.data.neo4j.database`: database mà Spring Data Neo4j sử dụng. Nếu không khai báo, driver/server áp dụng database mặc định theo cấu hình Neo4j.

Các biểu thức `${TEN_BIEN:gia_tri_mac_dinh}` cho phép thay đổi cấu hình theo môi trường. Ví dụ, khi phát triển trên máy cá nhân, `NEO4J_URI` có thể không được đặt và ứng dụng dùng `bolt://localhost:7687`. Trong môi trường container hoặc staging, đặt `NEO4J_URI` thành URI tương ứng. `NEO4J_PASSWORD` không có giá trị mặc định để tránh vô tình chạy ứng dụng với một mật khẩu mẫu.

Đặt các biến môi trường trước khi khởi động ứng dụng. Ví dụ trong PowerShell:

```powershell
$env:NEO4J_URI = "bolt://localhost:7687"
$env:NEO4J_USERNAME = "neo4j"
$env:NEO4J_PASSWORD = "<mat-khau-cua-moi-truong>"
$env:NEO4J_DATABASE = "neo4j"
```

Trong Linux hoặc macOS, có thể export các biến tương ứng trong môi trường chạy ứng dụng. Hệ thống triển khai nên lấy mật khẩu từ secret manager hoặc cơ chế quản lý bí mật của nền tảng, thay vì ghi trực tiếp vào file cấu hình được commit.

Nếu chạy backend trong Docker Compose cùng Neo4j, đặt `NEO4J_URI` thành `bolt://neo4j:7687`. Nếu kết nối tới cụm có routing và TLS, dùng URI `neo4j+s://...` theo địa chỉ được nhà cung cấp hoặc quản trị viên cấp.

## 7. Tài khoản, mật khẩu và quyền truy cập

Neo4j xác thực người dùng trước khi cho phép thực hiện truy vấn. Trong cấu hình cơ bản, ứng dụng dùng username và password thông qua cơ chế xác thực mà driver hỗ trợ. Với tài khoản mặc định của một cài đặt mới, username thường là `neo4j`; mật khẩu được thiết lập trong quá trình khởi tạo hoặc theo cách triển khai.

Một số nguyên tắc cần áp dụng:

1. **Không nhúng bí mật vào mã nguồn.** Không ghi mật khẩu thật vào `application.yml`, Dockerfile, file Compose được commit hoặc câu lệnh được lưu trong lịch sử shell. Dùng biến môi trường hoặc secret manager.
2. **Tách tài khoản theo ứng dụng.** Không dùng tài khoản quản trị cho mọi backend. Tạo tài khoản riêng với quyền tối thiểu cần thiết trên database.
3. **Phân biệt xác thực và phân quyền.** Kết nối có thể xác thực thành công nhưng vẫn bị từ chối khi tài khoản không có quyền đọc hoặc ghi dữ liệu cần thiết.
4. **Luân chuyển bí mật có kế hoạch.** Khi thay đổi mật khẩu, cập nhật secret của ứng dụng và triển khai đồng bộ. Kiểm tra kết nối sau khi cập nhật để tránh backend tiếp tục dùng thông tin cũ.
5. **Mã hóa kết nối qua mạng không tin cậy.** Chọn scheme TLS thích hợp và quản lý chứng chỉ đúng cách.

Không nên đặt username và password trực tiếp trong URI như một chuỗi cấu hình tự ghép. Spring Boot cung cấp các thuộc tính xác thực riêng, giúp tách vị trí máy chủ khỏi bí mật và tránh lộ thông tin trong log hoặc thông báo lỗi chứa URI.

## 8. Kiểm tra kết nối trước khi chạy ứng dụng

Khi cấu hình mới, kiểm tra theo từng lớp giúp khoanh vùng lỗi nhanh hơn.

**Bước 1: kiểm tra Neo4j đã chạy.** Xác nhận container hoặc service đang hoạt động. Với Docker, xem trạng thái container và log khởi động để biết database đã sẵn sàng hay chưa.

**Bước 2: kiểm tra cổng từ máy chạy ứng dụng.** Trên PowerShell, có thể dùng:

```powershell
Test-NetConnection localhost -Port 7687
```

Nếu `TcpTestSucceeded` là `False`, hãy kiểm tra ánh xạ cổng Docker, cấu hình Bolt, firewall, host và đường mạng. Kiểm tra TCP thành công chỉ chứng minh cổng có thể truy cập; nó chưa xác nhận handshake Bolt, TLS hoặc xác thực thành công.

**Bước 3: thử đăng nhập bằng Cypher Shell.** Nếu đã cài `cypher-shell`, kết nối tới endpoint Bolt và nhập mật khẩu khi được hỏi:

```bash
cypher-shell -a bolt://localhost:7687 -u neo4j
```

Sau khi đăng nhập, chạy một truy vấn đơn giản:

```cypher
RETURN 1 AS connection_ok;
```

Nếu truy vấn trả về `connection_ok = 1`, kết nối Bolt và xác thực cơ bản đã hoạt động. Hãy thoát shell trước khi kiểm tra cấu hình Spring Boot.

**Bước 4: khởi động ứng dụng Spring Boot.** Kiểm tra log khởi động để xác nhận driver tạo được kết nối. Sau đó gọi một repository hoặc service có truy vấn đơn giản để xác nhận ứng dụng truy cập đúng database.

## 9. Các lỗi cấu hình thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| `Connection refused` | Neo4j chưa chạy, Bolt chưa bật, sai host hoặc cổng chưa được publish | Kiểm tra trạng thái server, cấu hình Bolt và port mapping `7687` |
| Timeout | Firewall chặn, DNS sai, route mạng không tới được server hoặc server quá tải | Kiểm tra DNS, đường mạng, firewall và thời gian sẵn sàng của server |
| Lỗi handshake hoặc protocol | Dùng scheme Bolt với cổng HTTP, hoặc kết nối tới dịch vụ không phải Bolt | Xác nhận URI dùng cổng Bolt, thường là `7687` |
| Authentication failure | Sai username/password, mật khẩu đã thay đổi hoặc secret của ứng dụng chưa cập nhật | Thử đăng nhập bằng Cypher Shell và đối chiếu secret runtime |
| TLS certificate error | Chứng chỉ hết hạn, hostname không khớp hoặc CA chưa được tin cậy | Kiểm tra certificate chain, hostname và trust store; dùng scheme TLS phù hợp |
| Kết nối ban đầu được nhưng routing thất bại | Địa chỉ máy trong routing table không thể truy cập từ ứng dụng | Kiểm tra advertised address, DNS, firewall và các cổng của cụm |
| Login được nhưng truy vấn bị từ chối | Tài khoản thiếu quyền trên database hoặc thao tác | Kiểm tra role và quyền tối thiểu cần cấp |
| Browser truy cập được nhưng ứng dụng lỗi | HTTP hoạt động nhưng Bolt có thể chưa mở hoặc URI backend sai | Kiểm tra riêng cổng `7687` và kết nối bằng Cypher Shell |

Khi đọc log, không chia sẻ công khai password, token, URI chứa thông tin nhạy cảm hoặc thông tin định danh nội bộ. Hãy che các giá trị bí mật trước khi gửi log cho người khác.

## 10. Checklist cấu hình cho một môi trường mới

Trước khi đưa ứng dụng Spring Data Neo4j vào chạy, hãy xác nhận:

- [ ] Neo4j đang chạy và database đích đã sẵn sàng.
- [ ] URI dùng đúng scheme: kết nối trực tiếp hay routing, có TLS hay không.
- [ ] Host có thể được phân giải và truy cập từ chính môi trường chạy Spring Boot.
- [ ] Backend kết nối tới Bolt, thường ở cổng `7687`; không nhầm với HTTP `7474` hoặc HTTPS `7473`.
- [ ] Username và password được nạp từ môi trường hoặc secret manager.
- [ ] Tài khoản có quyền tối thiểu cần thiết trên database được chọn.
- [ ] Nếu dùng TLS, chứng chỉ và hostname được xác minh đúng.
- [ ] Nếu dùng routing, mọi địa chỉ được quảng bá trong routing table đều truy cập được.
- [ ] Đã thử kết nối bằng driver/Cypher Shell và kiểm tra truy vấn từ ứng dụng.

## 11. Tự kiểm tra

1. Vì sao Spring Data Neo4j kết nối tới cổng `7687` thay vì cổng Neo4j Browser `7474`?
2. Khác biệt chính giữa `bolt://` và `neo4j://` là gì? Khi nào cần routing?
3. Scheme `neo4j+s://` khác `neo4j+ssc://` ở cách xác minh chứng chỉ như thế nào?
4. Vì sao `localhost` trong container Spring Boot không trỏ tới container Neo4j khác?
5. Thuộc tính nào trong Spring Boot cấu hình URI, username, password và database?
6. Nếu Neo4j Browser truy cập được nhưng ứng dụng báo `Connection refused`, bạn sẽ kiểm tra những thành phần nào trước?
