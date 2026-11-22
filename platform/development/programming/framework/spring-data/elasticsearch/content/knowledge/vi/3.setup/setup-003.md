# Khởi chạy Elasticsearch phục vụ học tập bằng Docker

Để học Spring Data Elasticsearch, trước hết cần có một Elasticsearch server đang chạy để ứng dụng Java có thể gửi document, tạo index và thực hiện truy vấn. Docker giúp dựng môi trường này nhanh, có thể dừng hoặc tạo lại khi cần, đồng thời giữ dữ liệu trong một volume độc lập với vòng đời container.

Bài học này sử dụng Docker Compose để chạy một Elasticsearch node trên máy cá nhân. Cấu hình được giới hạn cho mục đích học tập: Elasticsearch chỉ lắng nghe qua cổng loopback của máy host và tắt xác thực để các ví dụ HTTP ngắn gọn. Không dùng cấu hình này cho môi trường có dữ liệu thật hoặc có thể truy cập từ mạng bên ngoài.

## 1. Mô hình chạy Elasticsearch bằng Docker

Khi chạy Elasticsearch bằng Docker, có một số thành phần cần phân biệt:

| Thành phần | Vai trò |
| --- | --- |
| Docker Engine | Tạo và quản lý container, network và volume. |
| Elasticsearch image | Bộ image chứa Elasticsearch cùng runtime cần thiết để khởi chạy server. |
| Container | Tiến trình Elasticsearch đang chạy. Container có thể bị xóa và tạo lại. |
| Port mapping | Chuyển kết nối từ cổng máy host vào cổng Elasticsearch trong container. |
| Named volume | Lưu dữ liệu index bên ngoài filesystem có vòng đời của container. |
| Docker Compose | Khai báo cấu hình các service và cách khởi chạy chúng trong một file YAML. |

Sơ đồ kết nối khi ứng dụng Spring Boot chạy trực tiếp trên máy tính:

~~~mermaid
flowchart LR
    A["Ứng dụng Spring Boot"] -->|"http://localhost:9200"| B["Cổng 9200 trên máy host"]
    B --> C["Elasticsearch container :9200"]
    C --> D["Named volume esdata"]
~~~

Ứng dụng Java gửi HTTP request đến `localhost:9200`. Docker chuyển request qua port mapping tới cổng `9200` trong container. Elasticsearch xử lý request và lưu dữ liệu trong thư mục data được gắn với named volume.

Named volume rất quan trọng: xóa container không đồng nghĩa với xóa dữ liệu. Khi tạo lại container và gắn lại volume `esdata`, Elasticsearch có thể đọc lại các index đã lưu trước đó.

## 2. Chuẩn bị Docker

Cần cài Docker Desktop trên Windows/macOS hoặc Docker Engine cùng Docker Compose plugin trên Linux. Docker daemon phải đang hoạt động trước khi chạy lệnh Compose.

Kiểm tra phiên bản Docker và Compose:

~~~bash
docker --version
docker compose version
~~~

Kiểm tra daemon có thể nhận lệnh:

~~~bash
docker info
~~~

Nếu các lệnh trên không chạy được, hãy khởi động Docker Desktop hoặc Docker Engine rồi kiểm tra lại. Docker Compose hiện đại được gọi bằng `docker compose` (có dấu cách).

### 2.1. Kiểm tra tài nguyên máy

Elasticsearch là một dịch vụ Java có sử dụng heap và bộ nhớ native. Với ví dụ bên dưới, heap được đặt ở mức 1 GB. Nên cấp cho Docker Desktop khoảng 2–4 GB RAM trở lên để hệ điều hành container và Elasticsearch còn đủ bộ nhớ ngoài heap. Máy có ít RAM có thể giảm heap xuống `512m` để thử nghiệm nhỏ.

Trên Linux chạy Docker Engine trực tiếp, Elasticsearch cần giới hạn `vm.max_map_count` đủ lớn. Có thể thiết lập tạm thời bằng:

~~~bash
sudo sysctl -w vm.max_map_count=262144
~~~

Để giữ thiết lập sau khi khởi động lại Linux, tạo file cấu hình sysctl chứa dòng:

~~~text
vm.max_map_count=262144
~~~

Sau đó nạp lại cấu hình bằng `sudo sysctl --system`. Docker Desktop chạy trong một Linux VM; nếu log báo lỗi bootstrap check liên quan đến `vm.max_map_count`, hãy kiểm tra cấu hình VM/WSL2 và hướng dẫn dành cho phiên bản Docker Desktop đang dùng.

## 3. Tạo file Docker Compose

Tạo một thư mục riêng cho môi trường học tập, ví dụ `elasticsearch-lab`, sau đó tạo file `compose.yaml` trong thư mục đó.

~~~yaml
services:
  elasticsearch:
    image: docker.elastic.co/elasticsearch/elasticsearch:8.15.5
    environment:
      discovery.type: single-node
      xpack.security.enabled: "false"
      ES_JAVA_OPTS: "-Xms1g -Xmx1g"
    ports:
      - "127.0.0.1:9200:9200"
    volumes:
      - esdata:/usr/share/elasticsearch/data
    restart: unless-stopped

  kibana:
    image: docker.elastic.co/kibana/kibana:8.15.5
    profiles:
      - ui
    depends_on:
      - elasticsearch
    environment:
      ELASTICSEARCH_HOSTS: '["http://elasticsearch:9200"]'
      XPACK_SECURITY_ENABLED: "false"
    ports:
      - "127.0.0.1:5601:5601"

volumes:
  esdata:
~~~

Đây là cấu hình một node Elasticsearch phù hợp cho bài thực hành trên máy cá nhân. Các phần chính:

- `image`: chọn image Elasticsearch phiên bản `8.15.5`. Phiên bản được ghim để mỗi lần tạo lại môi trường có kết quả nhất quán. Nếu thay phiên bản, cần kiểm tra tương thích với Spring Data Elasticsearch đang sử dụng và cập nhật image Kibana cùng phiên bản.
- `discovery.type: single-node`: yêu cầu Elasticsearch chạy ở chế độ một node, không cần cấu hình discovery cho cluster nhiều máy.
- `xpack.security.enabled: "false"`: tắt xác thực và TLS để gọi API HTTP trực tiếp trong các bài học. Chỉ phù hợp với môi trường local.
- `ES_JAVA_OPTS`: đặt heap tối thiểu và tối đa bằng nhau ở mức 1 GB, tránh để JVM tự chọn heap quá lớn hoặc thay đổi giữa lúc chạy.
- `127.0.0.1:9200:9200`: ánh xạ cổng host `9200` vào cổng container `9200`, đồng thời chỉ bind trên loopback. Máy khác trong mạng không thể truy cập Elasticsearch qua mapping này.
- `esdata:/usr/share/elasticsearch/data`: gắn named volume vào thư mục dữ liệu mặc định của Elasticsearch.
- `restart: unless-stopped`: cho phép Docker khởi động lại service sau khi Docker daemon khởi động lại, trừ khi người dùng đã chủ động dừng service.
- `profiles: [ui]`: Kibana là thành phần tùy chọn. Chỉ khi bật profile `ui`, Compose mới khởi chạy Kibana trên cổng `5601`.

Elasticsearch và Kibana nên dùng cùng một phiên bản. Nếu chỉ cần thực hành REST API hoặc kết nối Spring Data, có thể bỏ hẳn service Kibana khỏi file.

### 3.1. Tại sao cần named volume?

Elasticsearch ghi segment, metadata và các dữ liệu index vào `/usr/share/elasticsearch/data`. Nếu không gắn volume, dữ liệu nằm trong writable layer của container. Khi container bị xóa và tạo lại, dữ liệu đó cũng mất.

Với cấu hình `esdata`, Docker quản lý một volume có tên và gắn nó vào container. Có thể xóa container nhưng vẫn giữ volume để lần chạy sau tiếp tục dùng dữ liệu cũ.

### 3.2. Tại sao chỉ bind cổng vào `127.0.0.1`?

`127.0.0.1:9200:9200` giới hạn kết nối đến từ chính máy host. Nếu dùng `9200:9200`, Docker thường bind trên mọi giao diện mạng của host, khiến dịch vụ có thể truy cập từ các máy khác tùy cấu hình firewall và mạng.

Trong ví dụ này Elasticsearch tắt bảo mật. Giới hạn cổng vào loopback giúp tránh vô tình công khai một API không yêu cầu đăng nhập. Không đổi thành `0.0.0.0` hoặc mở cổng ra Internet để tiện truy cập.

## 4. Khởi chạy Elasticsearch

Mở terminal tại thư mục có file `compose.yaml`, rồi chạy:

~~~bash
docker compose up -d
~~~

Lần đầu tiên, Docker tải image nếu máy chưa có. Sau đó Compose tạo network, volume và container rồi chạy Elasticsearch ở chế độ nền (`-d`).

Kiểm tra service:

~~~bash
docker compose ps
~~~

Xem log khởi động:

~~~bash
docker compose logs -f elasticsearch
~~~

Nhấn `Ctrl+C` để thoát chế độ theo dõi log; thao tác này không dừng container. Elasticsearch cần một khoảng thời gian để khởi tạo. Chỉ gửi request sau khi server đã sẵn sàng.

Có thể kiểm tra trực tiếp bằng trình duyệt tại `http://localhost:9200` hoặc gọi từ terminal:

~~~bash
curl http://localhost:9200
~~~

Trên Windows PowerShell, `curl` có thể là alias của `Invoke-WebRequest`; dùng `curl.exe http://localhost:9200` để gọi chương trình curl thật. Một phản hồi thành công thường có JSON chứa tên node, tên cluster, UUID, phiên bản và tagline của Elasticsearch.

Kiểm tra sức khỏe cluster:

~~~bash
curl "http://localhost:9200/_cluster/health?pretty"
~~~

API `_cluster/health` trả về trạng thái cluster cùng số node, shard và thông tin liên quan. Với cấu hình một node, trạng thái `yellow` có thể là bình thường nếu index có replica shard nhưng không có node thứ hai để phân bổ replica. `yellow` có nghĩa primary shard đã được cấp phát nhưng còn replica chưa được cấp phát; không đồng nghĩa Elasticsearch đã ngừng hoạt động.

## 5. Khởi chạy Kibana (tùy chọn)

Kibana cung cấp giao diện web để xem index, document, mapping và thực hiện truy vấn trong Dev Tools. Nếu muốn dùng giao diện này, chạy:

~~~bash
docker compose --profile ui up -d
~~~

Đợi Kibana khởi động rồi mở `http://localhost:5601`. Nếu trang chưa truy cập được ngay, xem log:

~~~bash
docker compose logs -f kibana
~~~

Kibana kết nối tới Elasticsearch bằng tên service `elasticsearch` trong mạng nội bộ Docker. Địa chỉ này chỉ có ý nghĩa bên trong network Compose; trình duyệt trên máy host vẫn truy cập Kibana qua `localhost:5601`.

## 6. Thử nghiệm Elasticsearch REST API

Elasticsearch cung cấp REST API qua HTTP. Thực hành trực tiếp bằng API giúp hiểu rõ server đang nhận và trả dữ liệu gì trước khi Spring Data Elasticsearch tự động hóa các thao tác đó.

### 6.1. Tạo index và mapping

Tạo index `products` với mapping tường minh và không tạo replica trong bài thực hành một node:

~~~http
PUT /products
Content-Type: application/json

{
  "settings": {
    "number_of_replicas": 0
  },
  "mappings": {
    "properties": {
      "name": { "type": "text" },
      "sku": { "type": "keyword" },
      "priceInCents": { "type": "long" },
      "active": { "type": "boolean" }
    }
  }
}
~~~

Có thể gửi nội dung trên bằng Kibana Dev Tools hoặc một HTTP client. Nếu gọi từ terminal với curl, dùng `-X PUT`, header `Content-Type: application/json` và truyền JSON trong phần body. Khi tạo thành công, Elasticsearch trả về thông tin xác nhận index đã được tạo.

Xem mapping vừa tạo:

~~~http
GET /products/_mapping
~~~

Mapping định nghĩa cách Elasticsearch lập chỉ mục cho field. Trong ví dụ, `name` là `text` để tìm kiếm toàn văn, còn `sku` là `keyword` để so khớp chính xác.

### 6.2. Ghi một document

Gửi document có `_id` là `KB-001`:

~~~http
PUT /products/_doc/KB-001
Content-Type: application/json

{
  "name": "Mechanical Keyboard",
  "sku": "KB-001",
  "priceInCents": 129900,
  "active": true
}
~~~

Đọc lại document:

~~~http
GET /products/_doc/KB-001
~~~

Kết quả có metadata `_index`, `_id`, `_version` và nội dung `_source`. Đây là điểm bắt đầu để quan sát quan hệ giữa ID, JSON document và dữ liệu Elasticsearch lưu trữ.

### 6.3. Tìm kiếm document

Tìm theo nội dung tên sản phẩm bằng `match`:

~~~http
GET /products/_search
Content-Type: application/json

{
  "query": {
    "match": {
      "name": "mechanical keyboard"
    }
  }
}
~~~

Tìm theo SKU chính xác bằng `term`:

~~~http
GET /products/_search
Content-Type: application/json

{
  "query": {
    "term": {
      "sku": "KB-001"
    }
  }
}
~~~

Kết quả tìm kiếm chứa mảng `hits.hits`. Mỗi hit có metadata của document và thường có `_source` để trả lại các field JSON. Có thể tiếp tục thử `GET /_cat/indices?v` để xem danh sách index hoặc `GET /_cat/nodes?v` để xem node đang hoạt động.

## 7. Kết nối ứng dụng Spring Data Elasticsearch

Khi ứng dụng Spring Boot chạy trực tiếp trên máy host, cấu hình URI trỏ tới cổng đã publish:

~~~yaml
spring:
  elasticsearch:
    uris: http://localhost:9200
~~~

Đặt cấu hình này trong `application.yml` hoặc profile dành cho môi trường học tập. Ứng dụng cần có dependency Spring Data Elasticsearch phù hợp với phiên bản Spring Boot của dự án. Sau khi ứng dụng khởi động, repository hoặc `ElasticsearchOperations` sẽ dùng client được cấu hình để giao tiếp với server.

Điểm cần chú ý về địa chỉ kết nối:

| Nơi chạy ứng dụng Java | URI thường dùng |
| --- | --- |
| Java chạy trực tiếp trên máy host | `http://localhost:9200` |
| Java chạy trong một service khác cùng Compose network | `http://elasticsearch:9200` |
| Java chạy trong một container độc lập không cùng network | Cần đưa container vào cùng network hoặc cấu hình một địa chỉ mạng có thể truy cập được. |

`localhost` bên trong container Java là chính container Java đó, không phải máy host và cũng không phải container Elasticsearch. Khi hai service cùng một Compose project, tên service `elasticsearch` được Docker DNS phân giải thành địa chỉ container tương ứng.

Ví dụ thêm service ứng dụng vào cùng file Compose:

~~~yaml
services:
  elasticsearch:
    image: docker.elastic.co/elasticsearch/elasticsearch:8.15.5
    environment:
      discovery.type: single-node
      xpack.security.enabled: "false"
      ES_JAVA_OPTS: "-Xms1g -Xmx1g"
    ports:
      - "127.0.0.1:9200:9200"
    volumes:
      - esdata:/usr/share/elasticsearch/data

  app:
    build: .
    environment:
      SPRING_ELASTICSEARCH_URIS: http://elasticsearch:9200
    depends_on:
      - elasticsearch

volumes:
  esdata:
~~~

`depends_on` theo cấu hình đơn giản chỉ đảm bảo thứ tự khởi chạy container, không bảo đảm Elasticsearch đã sẵn sàng nhận request. Ứng dụng thực tế nên có cơ chế retry kết nối hoặc health check phù hợp thay vì giả định server sẵn sàng ngay khi container vừa được tạo.

## 8. Quản lý vòng đời môi trường

Các lệnh thường dùng khi làm bài thực hành:

| Lệnh | Tác dụng |
| --- | --- |
| `docker compose up -d` | Tạo và khởi chạy service ở chế độ nền. |
| `docker compose ps` | Xem trạng thái các container thuộc Compose project. |
| `docker compose logs -f elasticsearch` | Theo dõi log Elasticsearch. |
| `docker compose stop` | Dừng container nhưng giữ container và volume. |
| `docker compose start` | Khởi động lại các container đã dừng. |
| `docker compose restart elasticsearch` | Khởi động lại service Elasticsearch. |
| `docker compose down` | Dừng và xóa container cùng network do Compose tạo; named volume vẫn được giữ. |
| `docker compose down -v` | Xóa cả named volume do Compose quản lý; dữ liệu Elasticsearch trong volume đó bị xóa. |

Phân biệt rõ `down` và `down -v`. Khi chỉ muốn tắt môi trường sau buổi học, dùng:

~~~bash
docker compose down
~~~

Lần sau chạy `docker compose up -d`, Compose tạo container mới và gắn lại volume `esdata`, vì vậy dữ liệu vẫn còn.

Chỉ khi muốn xóa toàn bộ dữ liệu học tập và bắt đầu lại từ đầu mới dùng:

~~~bash
docker compose down -v
~~~

Lệnh này có tác động phá hủy dữ liệu trong volume của Compose project. Nếu chỉ muốn xóa một index, có thể dùng API `DELETE /products` thay vì xóa toàn bộ volume.

## 9. Xử lý một số lỗi thường gặp

### Docker daemon không hoạt động

Dấu hiệu thường thấy là Docker CLI báo không kết nối được daemon hoặc Docker Desktop engine. Hãy mở Docker Desktop hoặc khởi động Docker Engine, chờ trạng thái sẵn sàng rồi thử `docker info` và `docker compose up -d` lại.

### Cổng 9200 đã được sử dụng

Compose có thể báo không bind được cổng host `9200`. Kiểm tra tiến trình hoặc container đang chiếm cổng đó. Có thể đổi cổng host, ví dụ:

~~~yaml
ports:
  - "127.0.0.1:9201:9200"
~~~

Khi đổi như vậy, ứng dụng chạy trên host phải kết nối tới `http://localhost:9201`; cổng bên trong container vẫn là `9200`. Service khác cùng Compose network vẫn kết nối `http://elasticsearch:9200`.

### Elasticsearch khởi động rồi thoát

Đọc log bằng `docker compose logs elasticsearch`. Các nguyên nhân phổ biến gồm thiếu RAM, heap quá lớn so với tài nguyên được cấp, quyền ghi vào data directory hoặc bootstrap check của Linux không đạt. Điều chỉnh tài nguyên Docker và cấu hình theo thông báo lỗi cụ thể; tránh xóa volume ngay vì volume có thể chứa dữ liệu cần giữ.

### Lỗi `vm.max_map_count` trên Linux

Nếu log chỉ rõ giới hạn map count quá thấp, đặt `vm.max_map_count` tối thiểu `262144` trên môi trường Linux chạy Docker rồi khởi động lại service. Trên Docker Desktop, cần kiểm tra Linux VM/WSL2 mà Docker sử dụng.

### Ứng dụng báo connection refused

Kiểm tra `docker compose ps`, log Elasticsearch và gọi `http://localhost:9200` từ chính máy host. Đảm bảo ứng dụng dùng đúng cổng host đã publish. Nếu Java chạy trong container cùng network, dùng hostname service `elasticsearch` thay cho `localhost`.

### Gọi HTTP nhưng server yêu cầu HTTPS hoặc xác thực

Bài học này tắt security trong cấu hình local. Nếu đã bật security hoặc dùng một cấu hình Elasticsearch khác, endpoint có thể yêu cầu HTTPS và thông tin đăng nhập. Khi đó cần cấu hình URI, chứng thư và credentials tương ứng trong ứng dụng; không nên tắt bảo mật của một cluster dùng chung chỉ để làm ví dụ chạy được.

### Cluster ở trạng thái yellow

Với cluster một node, replica shard không thể được phân bổ lên node thứ hai. Nếu primary shard đã hoạt động, trạng thái yellow thường vẫn cho phép ghi và tìm kiếm. Để bài thực hành một node có trạng thái green, đặt `number_of_replicas` bằng `0` khi tạo index, như ví dụ `products` ở phần trên.

## 10. Bảo mật và giới hạn của môi trường học tập

Cấu hình mẫu chủ động đặt `xpack.security.enabled=false` để người học tập trung vào document, mapping, repository và query. Điều đó có nghĩa bất kỳ tiến trình nào truy cập được cổng đã mở đều có thể gọi API Elasticsearch mà không cần xác thực.

Các giới hạn an toàn của cấu hình này:

- Chỉ chạy trên máy cá nhân hoặc môi trường lab cô lập.
- Giữ port mapping ở `127.0.0.1`; không publish cổng ra giao diện mạng công cộng.
- Không lưu dữ liệu nhạy cảm hoặc dữ liệu khách hàng thật trong môi trường này.
- Không dùng cấu hình tắt security cho staging hoặc production.
- Khi cần môi trường dùng chung, bật security, cấu hình TLS và thông tin xác thực theo hướng dẫn triển khai phù hợp.

Việc ghim phiên bản image cũng giúp môi trường học tập tái lập được. Khi nâng cấp Elasticsearch, cần kiểm tra release notes, khả năng tương thích của Spring Data Elasticsearch và quy trình nâng cấp dữ liệu. Không nên tự động đổi tag sang `latest` vì phiên bản server có thể thay đổi mà không có thay đổi tương ứng trong ứng dụng.

## 11. Quy trình thực hành đề xuất

Có thể dùng thứ tự sau cho mỗi lần bắt đầu học:

1. Kiểm tra Docker daemon bằng `docker info`.
2. Mở terminal tại thư mục chứa `compose.yaml`.
3. Chạy `docker compose up -d` và kiểm tra `docker compose ps`.
4. Theo dõi log cho đến khi Elasticsearch sẵn sàng.
5. Gọi `http://localhost:9200` và `_cluster/health` để xác nhận kết nối.
6. Tạo index, mapping và document bằng REST API hoặc Kibana Dev Tools.
7. Kết nối Spring Boot qua `spring.elasticsearch.uris` và thực hành repository/query.
8. Kết thúc buổi học bằng `docker compose down` để giữ lại dữ liệu cho lần sau.

Khi muốn xóa dữ liệu để làm lại từ đầu, xác nhận đúng Compose project rồi mới chạy `docker compose down -v`.

Elasticsearch chạy trong Docker cung cấp một server độc lập cho các bài học Spring Data Elasticsearch. Docker Compose mô tả cách dựng server, port mapping cho phép ứng dụng kết nối, named volume giữ dữ liệu qua các lần tạo container, còn REST API giúp kiểm tra server trước khi đưa Spring Data vào luồng làm việc.
