# Cấu hình mục tiêu scrape, đường dẫn, cổng và thông tin xác thực

Khi Prometheus thu thập metrics từ Spring Boot, nó cần gọi đúng **URL từ góc nhìn của tiến trình Prometheus**. Một endpoint có thể trả dữ liệu khi gọi trên máy ứng dụng nhưng vẫn báo lỗi trên Prometheus nếu hai bên dùng cổng, đường dẫn hoặc thông tin xác thực khác nhau.

## 1. Tách địa chỉ đích khỏi đường dẫn

Một job scrape kiểu tĩnh ghép URL từ ba thành phần:

~~~text
URL scrape = scheme + "://" + target + metrics_path
~~~

- `static_configs[].targets» liệt kê địa chỉ `host:port», chẳng hạn `shop.ops.example.com:9443». DNS và cổng phải truy cập được từ môi trường chạy Prometheus.
- `metrics_path» là phần đường dẫn tuyệt đối, chẳng hạn `/actuator/prometheus». Prometheus mặc định dùng `/metrics» khi bỏ trường này.
- `scheme» là `http» hoặc `https». Mặc định là `http». Chọn theo giao thức mà máy đích nhận trên cổng đã khai báo.

Nếu Prometheus chạy trong container, `localhost» trỏ về chính container đó. Nếu job thu thập từng bản sao, khai báo địa chỉ từng bản sao hoặc dùng cơ chế khám phá dịch vụ trả về từng đích. Một địa chỉ cân bằng tải có thể dẫn mỗi lần thu thập tới một bản sao khác và làm lẫn số đo của các tiến trình.

## 2. Xác định cổng và đường dẫn Actuator

Ví dụ dùng Spring Boot 3.3 với Spring MVC, Actuator và registry Prometheus đã có trong ứng dụng. Đặt cấu hình sau trong `application.properties»:

~~~properties
server.port=8080
server.servlet.context-path=/shop
management.server.port=9091
management.server.address=127.0.0.1
management.server.base-path=/ops
management.endpoints.web.base-path=/manage
management.endpoints.web.path-mapping.prometheus=metrics
management.endpoints.web.exposure.include=health,prometheus
~~~

Ứng dụng nghe trên cổng 8080. Máy chủ quản lý nghe trên cổng 9091, chỉ trên loopback. Vì hai cổng khác nhau, đường dẫn nội bộ của endpoint ghép từ `/ops» (tiền tố máy chủ quản lý), `/manage» (tiền tố endpoint) và `/metrics» (tên đường dẫn đã ánh xạ). ID để mở qua HTTP vẫn là `prometheus». URL quản lý nội bộ là `http://127.0.0.1:9091/ops/manage/metrics».

| Cách triển khai | Cách tìm đường dẫn |
| --- | --- |
| Dùng chung cổng ứng dụng | Ghép `server.servlet.context-path», `management.endpoints.web.base-path» và phần đường dẫn của endpoint. Với `/shop» và các đường dẫn mặc định, URL kết thúc bằng `/shop/actuator/prometheus». |
| Dùng cổng quản lý riêng | Ghép `management.server.base-path», `management.endpoints.web.base-path» và phần đường dẫn của endpoint. Với cấu hình trên, URL kết thúc bằng `/ops/manage/metrics». |
| Qua proxy ngược | Prometheus gọi địa chỉ và đường dẫn mà proxy công bố. Nếu proxy viết lại đường dẫn, dùng đường dẫn ở phía Prometheus cho `metrics_path». |

Trong ví dụ, proxy chạy trực tiếp trên **cùng máy** với ứng dụng. Proxy nhận HTTPS tại `shop.ops.example.com:9443», yêu cầu HTTP Basic với tài khoản giám sát `prometheus-scraper», rồi chuyển đúng đường dẫn `/ops/manage/metrics» tới `127.0.0.1:9091». Đây là giả định về cấu hình proxy của ví dụ. Khi dùng Spring Security để xác thực ở ứng dụng, quy tắc truy cập cần cấp đúng quyền gọi endpoint cho tài khoản giám sát. Với `SecurityFilterChain» tự định nghĩa, ứng dụng chịu trách nhiệm cấu hình quyền này.

## 3. Cấu hình job và thông tin xác thực

Thêm job sau vào `scrape_configs» trong `prometheus.yml»:

~~~yaml
scrape_configs:
  - job_name: 'shop-actuator'
    scheme: 'https'
    metrics_path: '/ops/manage/metrics'
    scrape_interval: 30s
    scrape_timeout: 5s
    follow_redirects: false
    static_configs:
      - targets: ['shop.ops.example.com:9443']
    basic_auth:
      username: 'prometheus-scraper'
      password_file: '/run/secrets/shop_actuator_password'
    tls_config:
      ca_file: '/etc/prometheus/certs/shop-ops-ca.pem'
~~~

Job gọi `https://shop.ops.example.com:9443/ops/manage/metrics» mỗi 30 giây và chờ tối đa 5 giây. Chọn thời gian chờ phù hợp với endpoint và giữ `scrape_timeout» không vượt `scrape_interval». Ví dụ tắt theo chuyển hướng để lỗi trỏ tới trang đăng nhập hiện rõ ngay ở bước thu thập.

- **HTTP Basic** gửi tên tài khoản và mật khẩu trong tiêu đề `Authorization». Dùng HTTPS trên đường truyền tới proxy và cấp tệp `password_file» cho tiến trình Prometheus đọc. Tệp chứa mật khẩu của tài khoản giám sát và nằm ngoài mã nguồn.
- **TLS** dùng `ca_file» khi proxy sử dụng chứng chỉ do CA nội bộ cấp. Đường dẫn tệp tính trong môi trường Prometheus, chẳng hạn trong container nếu tiến trình chạy trong container. Tên máy trong `targets» phải khớp chứng chỉ mà proxy trình bày.
- **Bearer token** áp dụng khi endpoint hoặc proxy yêu cầu token. Khi đó thay toàn bộ khối `basic_auth» bằng khối dưới đây và cấp tệp token cho tiến trình Prometheus:

~~~yaml
authorization:
  type: 'Bearer'
  credentials_file: '/run/secrets/shop_actuator_token'
~~~

Chọn một cơ chế xác thực cho mỗi job. Nếu hệ thống yêu cầu Prometheus lấy token theo luồng OAuth 2.0 client credentials, dùng cấu hình `oauth2» tương ứng. Trường `basic_auth» và `authorization» ở trên là cấu hình **phía Prometheus gửi yêu cầu**. Quyền chấp nhận yêu cầu do proxy hoặc ứng dụng thực thi.

## 4. Kiểm tra theo thứ tự từ URL đến mẫu dữ liệu

1. Kiểm tra cấu hình trước khi nạp lại Prometheus:

   ~~~bash
   promtool check config /etc/prometheus/prometheus.yml
   ~~~

2. Từ môi trường có cùng tuyến mạng với Prometheus, thử đúng URL, CA và tài khoản. `curl» sẽ hỏi mật khẩu vì lệnh chỉ cung cấp tên tài khoản:

   ~~~bash
   curl -sS -i --max-time 5 --cacert /etc/prometheus/certs/shop-ops-ca.pem --user prometheus-scraper https://shop.ops.example.com:9443/ops/manage/metrics
   ~~~

   Kết quả cần có HTTP 200 và thân phản hồi chứa mẫu theo định dạng Prometheus, chẳng hạn các dòng `# TYPE» và số đo JVM. Nếu nhận HTML, kiểm tra xem proxy có trả trang đăng nhập hoặc ứng dụng có định tuyến nhầm hay không.

3. Sau khi nạp cấu hình, xem URL và lỗi gần nhất của job ở trang Targets của Prometheus. Sau lượt thu thập đầu tiên, truy vấn `up{job="shop-actuator"}». Giá trị 1 xác nhận Prometheus đã thu thập thành công từ đích đó. Giá trị 0 báo lượt thu thập thất bại. Nếu chưa có chuỗi `up» cho job, kiểm tra việc nạp cấu hình, danh sách đích và thời điểm thu thập đầu tiên.

| Dấu hiệu | Kiểm tra tiếp |
| --- | --- |
| `connection refused» hoặc hết thời gian chờ | Kiểm tra DNS, cổng công bố, địa chỉ lắng nghe và khả năng kết nối từ mạng của Prometheus. |
| Lỗi xác minh TLS | Kiểm tra `scheme», CA tin cậy, hạn chứng chỉ và tên máy trong chứng chỉ. |
| HTTP 401 | Kiểm tra cơ chế xác thực mà đích yêu cầu, tài khoản hoặc token và quyền đọc tệp thông tin xác thực. |
| HTTP 403 | Kiểm tra quyền của tài khoản giám sát và chính sách mạng hoặc proxy đang áp dụng cho đường dẫn. |
| HTTP 404 | Đối chiếu cổng và đường dẫn thực tế, quy tắc viết lại của proxy và cấu hình mở ID `prometheus» qua HTTP. |

### Tài liệu tham khảo

- [Spring Boot 3.3 – Đường dẫn và cổng quản lý qua HTTP](https://docs.spring.io/spring-boot/3.3/reference/actuator/monitoring.html)
- [Spring Boot 3.3 – Mở và bảo vệ endpoint Actuator](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html)
- [Prometheus – Cấu hình scrape, HTTP và TLS](https://prometheus.io/docs/prometheus/latest/configuration/configuration/)