# Chạy stub trong container theo bộ công cụ được hỗ trợ

## Mục tiêu học tập

Trong **Spring Cloud Contract**, producer và consumer thống nhất cách giao tiếp bằng **Groovy/YAML DSL** cho HTTP hoặc thông điệp. Từ hợp đồng, công cụ có thể **sinh test phía producer**, **đóng gói stub**, để consumer chạy kiểm thử bằng **Stub Runner**; CI dùng kết quả này để phát hiện các thay đổi API không tương thích.

Chương **Stub độc lập** đề cập một nhu cầu rất thực tế: đôi khi consumer không chạy bên trong JVM test của Spring Boot, mà là ứng dụng Node.js, Python, Go, một bài kiểm thử end-to-end hoặc một nhóm dịch vụ trong Docker Compose. Khi ấy, ta muốn chạy **stub như một dịch vụ độc lập trong container**, để consumer gọi qua HTTP hoặc nhận message mà **không phải khởi động producer thật**.

Bài học này giúp bạn:

- Phân biệt **Stub Runner Boot Docker image** với **WireMock Docker image** và **Docker image dùng để kiểm tra producer**.
- Chạy HTTP stub từ artifact Spring Cloud Contract `*-stubs.jar` bằng Stub Runner Boot với repository `REMOTE` hoặc `LOCAL`.
- Cấu hình `STUBRUNNER_IDS`, `STUBRUNNER_STUBS_MODE`, `STUBRUNNER_REPOSITORY_ROOT` và công bố đúng **hai loại cổng**.
- Dùng `docker compose` tổ chức môi trường test, trỏ consumer trong container tới **tên service**, và trỏ consumer trên host tới **cổng đã publish**.
- Chạy WireMock thuần bằng image chính thức với thư mục `mappings` và `__files` khi chỉ cần HTTP.
- Kiểm tra readiness, danh sách stub, request matcher, phản hồi lỗi và các tình huống không tìm thấy mapping.
- Hiểu giới hạn với **messaging**, bảo mật, artifact version, cấu hình broker, trạng thái của stub và test song song.
- Xây dựng CI chỉ dùng **candidate stub đã được producer kiểm chứng**, tránh chạy nhầm artifact cũ.

> **Nguyên tắc xuyên suốt:** container chỉ là phương thức **chạy và phân phối** stub. Nó **không tự kiểm chứng producer**. Producer contract tests phải chạy thành công trên implementation thật trước khi stub được coi là hợp đồng đủ tin cậy để công bố.

## 1. “Stub độc lập” có nghĩa là gì?

Hãy hình dung **Inventory Service** là producer cung cấp API tồn kho, còn **Checkout Service** là consumer.

~~~http
GET /api/inventory/SKU-101 HTTP/1.1
Accept: application/json
~~~

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "sku": "SKU-101",
  "available": true,
  "quantity": 8
}
~~~

Trong production, Checkout gọi một địa chỉ như `https://inventory.internal.example`. Trong test, Checkout cần gửi cùng request vào một **stub server**, ví dụ `http://inventory-stub:9876`, và nhận phản hồi giống hợp đồng.

Các bước có thể được mô tả như sau:

~~~mermaid
flowchart TD
    A["Contract Groovy/YAML"] --> B["Generated producer tests"]
    A --> C["Generated HTTP mappings/message definitions"]
    B --> D{"Producer test thực sự PASS?"}
    D -->|Không| X["Không phát hành stub đã xác nhận"]
    D -->|Có| E["Đóng gói artifact :stubs"]
    C --> E
    E --> F["Repository/local Maven cache"]
    F --> G["Stub Runner Boot container"]
    G --> H["HTTP stub tại cổng 9876"]
    H --> I["Consumer gửi HTTP request"]
    I --> J["Assert hành vi consumer"]
~~~

**Stub Runner Boot container** có thể tự tải artifact theo tọa độ Maven/Ivy, giải quyết mapping và khởi động WireMock servers. **WireMock container thuần** không có trách nhiệm tải một Spring Cloud Contract Maven artifact theo `group:artifact:version:classifier`: bạn phải chuẩn bị mapping và body files để nó đọc.

Cần phân biệt thêm một image khác trong hệ sinh thái Spring Cloud Contract dùng để **tạo/chạy producer contract tests** đối với ứng dụng ngoài JVM. Image này không thay thế Stub Runner Boot khi mục tiêu là chạy **consumer-side stubs**.

## 2. Chọn đúng công cụ

| Công cụ | Input chính | Lợi thế | Giới hạn/cần lưu ý |
|---|---|---|---|
| **Spring Cloud Contract Stub Runner Boot Docker** | Artifact stub có `group:artifact:version:stubs` | Tải và chạy nhiều stub, có HTTP API quản trị stub và trigger message | Cần repository/cache đúng; không dùng như server production công khai |
| **WireMock OSS Docker** | JSON `mappings` + `__files` | Nhẹ về khái niệm, dùng được cho client thuộc mọi ngôn ngữ, fault/latency testing | Không tự resolve Spring Cloud Contract artifact/version |
| **Stub Runner trong test JVM** | Dependency/test annotation `@AutoConfigureStubRunner` | Tiện cho JUnit/Spring Boot, inject cổng bằng `@StubRunnerPort` | Gắn với vòng đời test JVM; không phải server độc lập cho ứng dụng ngoài JVM |
| **Spring Cloud Contract verifier Docker** | Contract DSL + ứng dụng producer đang chạy | Sinh/chạy producer contract tests với giao thức thật | Không phải thay thế trực tiếp cho consumer-side Stub Runner |

Với bài toán “Checkout container cần gọi bản mô phỏng Inventory từ artifact do producer phát hành”, **Stub Runner Boot Docker** thường là lựa chọn giữ liên kết hợp đồng tốt nhất.

Với bài toán “chỉ muốn chạy một vài WireMock mappings đã chuẩn bị sẵn, không cần cơ chế Maven artifact và messaging”, **WireMock Docker** thường đơn giản hơn.

### Vì sao không đóng gói tùy tiện bất kỳ file DSL nào vào WireMock?

Groovy/YAML **Spring Cloud Contract DSL không phải** WireMock mapping JSON. Stub generation phải chuyển DSL thành cấu hình mà WireMock hiểu. Gắn trực tiếp `stockAvailable.groovy` vào thư mục `mappings` của WireMock sẽ không làm WireMock tự biên dịch Spring Cloud Contract DSL.

## 3. Chuẩn bị hợp đồng và artifact phía producer

Ví dụ file hợp đồng tại producer:

~~~text
src/test/resources/contracts/inventory/stockAvailable.groovy
~~~

Nội dung Groovy DSL:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'SKU-101 con 8 san pham'

    request {
        method 'GET'
        url '/api/inventory/SKU-101'
        headers {
            accept(applicationJson())
        }
    }

    response {
        status 200
        headers {
            contentType(applicationJson())
        }
        body(
            sku: 'SKU-101',
            available: true,
            quantity: 8
        )
    }
}
~~~

Nếu nhóm dùng YAML DSL, có thể mô tả **cùng tình huống** bằng:

~~~yaml
description: 'SKU-101 con 8 san pham'
request:
  method: GET
  url: '/api/inventory/SKU-101'
  headers:
    Accept: 'application/json'
response:
  status: 200
  headers:
    Content-Type: 'application/json'
  body:
    sku: 'SKU-101'
    available: true
    quantity: 8
~~~

Trong project thật, **chọn một hợp đồng đại diện** cho tình huống này; đừng tạo hai file trùng điều kiện request chỉ để dùng cả Groovy và YAML.

### Artifact dùng cho consumer

Với producer dùng Maven/Gradle plugin Spring Cloud Contract đã cấu hình đúng, sau quá trình kiểm chứng và đóng gói, có thể có:

~~~text
groupId    = com.example
artifactId = inventory-producer
version    = 1.1.0-rc.1
classifier = stubs
type       = jar
~~~

Tọa độ thường dùng:

~~~text
com.example:inventory-producer:1.1.0-rc.1:stubs
~~~

Tên file minh họa:

~~~text
inventory-producer-1.1.0-rc.1-stubs.jar
~~~

Bên trong thường có metadata theo cấu trúc:

~~~text
META-INF/
└── com.example/
    └── inventory-producer/
        └── 1.1.0-rc.1/
            ├── contracts/
            │   └── inventory/stockAvailable.groovy
            └── mappings/
                └── <generated-mapping>.json
~~~

Các đường dẫn và tên file chính xác **phụ thuộc plugin/version và cấu hình build**. Nếu contract dùng file body ngoài, artifact còn cần kèm các fixture tương ứng.

### Không bỏ qua producer verification

Lệnh tham khảo với Maven trong producer đã cấu hình verifier plugin:

~~~bash
./mvnw -B -ntp clean verify
~~~

Nếu muốn cài artifact vào Maven local repository cho `LOCAL` mode:

~~~bash
./mvnw -B -ntp install
~~~

Với Gradle, chạy những task contract test và stub jar do phiên bản plugin thực tế cung cấp. Không kết luận producer đã được kiểm chứng chỉ vì `*-stubs.jar` tồn tại; cần xem **generated producer test được sinh, đã chạy và PASS**. Tránh công bố artifact được tạo khi `-DskipTests`, `-x test` hoặc cơ chế bỏ qua test tương tự vẫn đang bật.

## 4. Hai cổng khác nhau trong Stub Runner Boot

Stub Runner Boot có ít nhất hai loại endpoint liên quan:

| Cổng | Công dụng | Ví dụ trong bài |
|---|---|---|
| **Cổng quản trị của Stub Runner Boot** | GET danh sách stub, tra cổng, trigger message | `8750` |
| **Cổng HTTP của stub WireMock** | Consumer gọi API Inventory mà producer đã mô tả | `9876` |

**Consumer gọi `http://...:9876/api/inventory/SKU-101`, không gọi `:8750/api/inventory/SKU-101`.** Cổng `8750` là server quản trị/trigger của Stub Runner Boot theo cấu hình ví dụ.

Nếu bạn có hai producer, ví dụ Inventory và Pricing, mỗi producer có thể cần cổng stub riêng:

~~~text
Stub Runner admin :8750
Inventory stub    :9876
Pricing stub      :9877
~~~

### Vì sao cổng động khó dùng hơn với Docker?

Trong JUnit, `@StubRunnerPort` hoặc `StubFinder` có thể lấy cổng runtime. Nhưng nếu một container stub tự chọn cổng ngẫu nhiên, chỉ khai báo `-p 9876:9876` sẽ **không** tự ánh xạ tới cổng ngẫu nhiên đó.

Đối với Docker Compose và consumer nằm ngoài Stub Runner process, **chỉ định cổng cố định cho từng stub** thường dễ hiểu và dễ cấu hình. Tránh xung đột bằng cách tạo một môi trường CI/container cô lập; không chạy nhiều bộ stubs cùng chiếm cổng host.

## 5. Chạy Stub Runner Boot Docker với repository REMOTE

Tài liệu Spring Cloud Contract mô tả image Stub Runner Boot chạy độc lập và dùng **biến môi trường** để cấu hình. Quy tắc đặt tên trong Docker thường là biến chữ hoa, dấu chấm chuyển thành dấu gạch dưới:

~~~text
stubrunner.ids             -> STUBRUNNER_IDS
stubrunner.repositoryRoot  -> STUBRUNNER_REPOSITORY_ROOT
stubrunner.stubsMode       -> STUBRUNNER_STUBS_MODE
~~~

Đây là cách gọi dành cho Docker Stub Runner Boot được tài liệu mô tả; đối với ứng dụng tự xây riêng hoặc các bản cấu hình cũ/mới, hãy đối chiếu property của image/version đang chạy.

### Ví dụ chạy bằng Bash trên Linux/macOS

Ví dụ giả định:

- Artifact `com.example:inventory-producer:1.1.0-rc.1:stubs` đã được công bố trong repository test/artifact.
- Repository có URL truy cập được **từ bên trong container**.
- Stub được chạy trong container ở cổng `9876`.
- Admin API ở cổng mặc định `8750` của bản Stub Runner Boot ví dụ.

~~~bash
# Chọn một image tag CÓ THẬT, tương thích với artifact của dự án.
# Thay giá trị dưới đây trước khi chạy.
export SCC_IMAGE_TAG="REPLACE_WITH_AVAILABLE_TAG"

# Repository giả định: thay bằng URL thật, container phải truy cập được.
export STUB_REPO_URL="https://artifacts.example.invalid/repository/stubs"

docker run --rm --name inventory-stub \
  -e "STUBRUNNER_IDS=com.example:inventory-producer:1.1.0-rc.1:stubs:9876" \
  -e "STUBRUNNER_STUBS_MODE=REMOTE" \
  -e "STUBRUNNER_REPOSITORY_ROOT=${STUB_REPO_URL}" \
  -p "127.0.0.1:8750:8750" \
  -p "127.0.0.1:9876:9876" \
  "springcloud/spring-cloud-contract-stub-runner:${SCC_IMAGE_TAG}"
~~~

**Các giá trị cần thay trước khi chạy:** image tag, tọa độ artifact và repository URL. `artifacts.example.invalid` cố ý là placeholder, không phải dịch vụ truy cập được. Một số tài liệu có sự khác biệt ở cách viết namespace image trong phần mô tả và ví dụ lệnh; nên kiểm tra **image chính thức, registry và tag còn khả dụng** của dòng Spring Cloud Contract đang dùng, rồi ghim tag hoặc digest thay vì đoán `latest`.

Docker ở ví dụ trên bind cả hai cổng vào `127.0.0.1` của **host** để tránh vô tình phơi bày admin API ra mạng ngoài. Nếu consumer cũng ở một container khác, hãy đặt chúng cùng Docker network và truy cập bằng **tên service**, không cần mở cổng admin ra Internet.

### Cách đọc lệnh

| Thành phần | Ý nghĩa |
|---|---|
| `STUBRUNNER_IDS=...:stubs:9876` | Chọn artifact và cổng nội bộ WireMock |
| `STUBRUNNER_STUBS_MODE=REMOTE` | Resolve stub qua repository từ xa |
| `STUBRUNNER_REPOSITORY_ROOT=...` | Nơi lưu artifact |
| `-p 127.0.0.1:8750:8750` | Cho phép máy host truy cập admin API tại localhost |
| `-p 127.0.0.1:9876:9876` | Cho phép máy host gọi HTTP stub tại localhost |
| `springcloud/...:TAG` | Image Stub Runner Boot tương thích, version đã được ghim |
| `--rm` | Dọn container sau khi dừng; không xóa artifact từ repository ngoài |

**Không nhập mật khẩu repository bằng cách viết thẳng vào source code, Dockerfile, Compose file được commit hoặc ví dụ tài liệu.** Nếu cần xác thực, hãy cấu hình cơ chế secret/credentials mà môi trường CI và phiên bản Stub Runner hỗ trợ. Biến môi trường cũng có thể bị lộ qua công cụ quản trị container; quản lý chúng theo chính sách bảo mật của tổ chức.

### Cấu hình cổng quản trị

Các tài liệu Stub Runner Boot thường dùng admin port mặc định `8750`. Nếu image hoặc cấu hình của bạn thay đổi cổng này, phải cập nhật cả **container port** và cách publish. Đừng chỉ đổi số ngoài `-p HOST:CONTAINER` rồi giả định server bên trong cũng tự đổi cổng.

## 6. Kiểm tra Stub Runner đã tải và chạy đúng artifact chưa

Sau khi container thực sự khởi động, có thể kiểm tra log:

~~~bash
docker logs inventory-stub
~~~

Các thông tin nên tìm:

- Stub Runner Boot application đã sẵn sàng.
- Tọa độ `com.example:inventory-producer:1.1.0-rc.1:stubs` được resolve.
- Mappings/contract được phát hiện.
- HTTP WireMock stub được tạo và lắng nghe ở cổng `9876`.
- Không có lỗi kết nối repository hoặc lỗi deserialize mapping.

### Dùng admin API

Stub Runner Boot có HTTP endpoints để truy vấn các stubs:

~~~bash
curl -i http://127.0.0.1:8750/stubs
~~~

Theo API Stub Runner Boot, `GET /stubs` trả danh sách những stubs đang chạy. Có thể tra cổng của một artifact qua `GET /stubs/{ivy}`, trong đó định danh có thể dùng artifact ID đơn ở các tình huống phù hợp:

~~~bash
curl -i http://127.0.0.1:8750/stubs/inventory-producer
~~~

Từ kết quả, xác nhận đúng producer/version và cổng thay vì chỉ xem container có trạng thái `running`.

### Smoke test HTTP stub

~~~bash
curl -i \
  -H "Accept: application/json" \
  http://127.0.0.1:9876/api/inventory/SKU-101
~~~

Kỳ vọng **nếu artifact đúng và mapping match**:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"sku":"SKU-101","available":true,"quantity":8}
~~~

WireMock có thể thay đổi định dạng whitespace, header phụ hoặc thứ tự JSON fields; điều cần kiểm chứng là status, Content-Type và dữ liệu theo hợp đồng, không phải toàn bộ response byte giống y hệt ví dụ.

### Ba cấp độ readiness

~~~text
1. Container process đang chạy
2. Stub Runner Boot đã start và tải được artifacts
3. WireMock mapping của Inventory đang trả kết quả đúng
~~~

**Không đồng nhất 1 với 3.** Đối với CI, nên đợi tới khi `GET /stubs` và **smoke request thật** đạt, rồi mới chạy consumer tests. Một số repository có thể tải chậm hoặc cần xác thực; chỉ `sleep 5` cố định thường không đáng tin.

## 7. Chạy stub LOCAL từ Maven cache gắn vào container

Trong phát triển cá nhân hoặc khi CI đã cài artifact ứng viên vào Maven local repository, có thể dùng chế độ `LOCAL`.

Theo hướng dẫn Docker Stub Runner Boot, thư mục Maven cache ở host thường được mount tới `/home/scc/.m2` của image:

~~~bash
# Trên host: artifact :stubs đã được cài vào ~/.m2/repository.
export SCC_IMAGE_TAG="REPLACE_WITH_AVAILABLE_TAG"

docker run --rm --name inventory-stub-local \
  -e "STUBRUNNER_IDS=com.example:inventory-producer:1.1.0-rc.1:stubs:9876" \
  -e "STUBRUNNER_STUBS_MODE=LOCAL" \
  -v "${HOME}/.m2:/home/scc/.m2:ro" \
  -p "127.0.0.1:8750:8750" \
  -p "127.0.0.1:9876:9876" \
  "springcloud/spring-cloud-contract-stub-runner:${SCC_IMAGE_TAG}"
~~~

**Lưu ý về đường dẫn và quyền:**

- Ví dụ trên là cú pháp shell kiểu Bash. Trên Windows/PowerShell hoặc Docker Desktop, thay cú pháp biến môi trường và volume path cho phù hợp.
- `LOCAL` đọc **Maven local repository trong container**, không tự đọc `target/*-stubs.jar` của producer từ host.
- Mount `:ro` làm nội dung volume chỉ đọc; nếu resolver cần ghi thêm metadata/dependencies chưa có trong cache, mount chỉ đọc có thể không phù hợp. Hãy chuẩn bị cache đầy đủ hoặc dùng môi trường có quyền ghi riêng được kiểm soát.
- Không giả định mọi image/version dùng cùng user home `/home/scc`. Xác nhận bằng tài liệu image đang chạy.
- Cần tránh việc stub cùng version trong cache là **bản cũ**. Với candidate CI, sử dụng version/build ID duy nhất hoặc repository tạm cô lập.

### LOCAL không tự bảo đảm chất lượng

Một artifact lỗi vẫn có thể được install vào `~/.m2`. Producer verification và version consistency là trách nhiệm của build/CI, không phải là thuộc tính của `STUBRUNNER_STUBS_MODE=LOCAL`.

## 8. Dùng Docker Compose cho consumer và stub

Khi consumer chạy trong container khác, Docker Compose giúp tạo mạng và quản lý vòng đời thuận tiện.

Ví dụ `compose.yaml` cho **dịch vụ stub**:

~~~yaml
services:
  inventory-stub:
    image: "springcloud/spring-cloud-contract-stub-runner:${SCC_IMAGE_TAG:?set SCC_IMAGE_TAG}"
    environment:
      STUBRUNNER_IDS: "com.example:inventory-producer:1.1.0-rc.1:stubs:9876"
      STUBRUNNER_STUBS_MODE: "REMOTE"
      STUBRUNNER_REPOSITORY_ROOT: "${STUB_REPO_URL:?set STUB_REPO_URL}"
    ports:
      - "127.0.0.1:8750:8750"
      - "127.0.0.1:9876:9876"
~~~

Lưu ý: cú pháp `${VAR:?message}` là **nội suy biến môi trường của Docker Compose**, không phải cấu hình của Spring Cloud Contract. Nếu chưa cung cấp `SCC_IMAGE_TAG` hoặc `STUB_REPO_URL`, Compose sẽ báo lỗi thay vì âm thầm dùng một giá trị sai.

Chạy bằng:

~~~bash
export SCC_IMAGE_TAG="REPLACE_WITH_AVAILABLE_TAG"
export STUB_REPO_URL="https://artifacts.example.invalid/repository/stubs"

docker compose up -d
docker compose logs inventory-stub
~~~

Hai biến trên **phải thay bằng giá trị thực**. Không dùng placeholder repo để đánh giá việc tải artifact thành công.

### Nếu consumer chạy trên host

Dùng:

~~~properties
inventory.base-url=http://127.0.0.1:9876
~~~

Consumer test/ứng dụng chạy trực tiếp trên máy host gọi cổng đã publish từ container.

### Nếu consumer chạy trong cùng Docker Compose network

Dùng:

~~~properties
inventory.base-url=http://inventory-stub:9876
~~~

Trong network của Compose, tên service `inventory-stub` được dùng để định tuyến tới container. **Không dùng `localhost:9876` trong container consumer**, vì `localhost` lúc này chỉ chính container consumer, không phải container Stub Runner.

| Nơi chạy consumer | URL phù hợp trong ví dụ | Điều kiện |
|---|---|---|
| Host chạy `curl`/JUnit/Node.js | `http://127.0.0.1:9876` | Stub port được publish lên host |
| Container consumer trong cùng Compose network | `http://inventory-stub:9876` | Hai service ở cùng network |
| Container ở network Docker khác | Không tự có URL trên | Cần nối network hoặc route được cấu hình rõ |
| Consumer từ máy khác | Không dùng `127.0.0.1` của máy khác | Cần một endpoint test được bảo vệ và network routing thích hợp |

Không nên mở admin port `8750` ra Internet hoặc môi trường nhiều bên không tin cậy để sửa lỗi kết nối. Stub Runner Boot là **testing utility không được bảo mật như dịch vụ production**.

### Khi thêm consumer service

Một ví dụ fragment nếu Checkout được đóng gói trong container và đã hỗ trợ `INVENTORY_BASE_URL`:

~~~yaml
services:
  checkout-test:
    image: "checkout-consumer-test:${CHECKOUT_TEST_TAG:?set CHECKOUT_TEST_TAG}"
    environment:
      INVENTORY_BASE_URL: "http://inventory-stub:9876"
    depends_on:
      - inventory-stub
~~~

Đoạn trên là **fragment**, không phải compose file hoàn chỉnh khi đứng một mình; nó cần ghép vào cùng file `services` với `inventory-stub`. Image `checkout-consumer-test` là image nội bộ minh họa, không tự tồn tại.

`depends_on` theo cú pháp cơ bản chỉ giúp sắp xếp việc **start container**, không bảo đảm Stub Runner đã tải xong artifacts và mapping sẵn sàng. Consumer test nên có **readiness wait có giới hạn** hoặc một healthcheck thực sự kiểm tra endpoint cần thiết.

## 9. Thêm nhiều producer vào một Stub Runner Boot container

Giả sử Checkout cũng dùng Pricing Service. Có thể khai báo nhiều stub ID trong cùng cấu hình, với cổng cố định khác nhau theo khả năng parse list của phiên bản:

~~~text
com.example:inventory-producer:1.1.0-rc.1:stubs:9876
com.example:pricing-producer:2.0.0-rc.2:stubs:9877
~~~

Theo quy ước `stubrunner.ids`, danh sách được cung cấp dưới dạng collection/list; trong môi trường container cách encode biến môi trường cho collection có thể phụ thuộc cách Spring Boot binder nhận cấu hình. **Hãy đối chiếu log resolved IDs**, không chỉ đặt chuỗi có dấu phẩy rồi giả định mọi phiên bản đều parse giống nhau.

Một cách cấu hình Spring Boot property theo index mà bạn có thể áp dụng **nếu image/version hỗ trợ**:

~~~yaml
environment:
  STUBRUNNER_IDS_0: "com.example:inventory-producer:1.1.0-rc.1:stubs:9876"
  STUBRUNNER_IDS_1: "com.example:pricing-producer:2.0.0-rc.2:stubs:9877"
~~~

Nếu muốn tránh phụ thuộc chi tiết binding mảng, có thể chạy **mỗi producer một Stub Runner Boot container riêng**, nhất là khi chúng có lifecycle/credential và version khác nhau.

Khi dùng nhiều stub trong một container:

- Publish cổng `9876` và `9877` nếu consumer chạy trên host.
- Trong cùng Docker network, consumer gọi `inventory-stub:9876` và `inventory-stub:9877` (nếu cùng server container).
- Đảm bảo không có hai stub cùng chiếm một cổng.
- Kiểm tra `GET /stubs` để xác nhận tất cả artifact đã được khởi động.
- Ghim version cho từng producer, không dùng `+`/`latest` khiến test phụ thuộc artifact mới nhất bất ngờ.

## 10. Dùng WireMock Docker khi chỉ có HTTP mappings

Một lựa chọn khác được **WireMock OSS hỗ trợ chính thức** là image `wiremock/wiremock`. Image này khởi động một WireMock standalone server và đọc các mapping từ filesystem.

Khác với Stub Runner Boot, **WireMock không tự tải `:stubs` theo Maven coordinate**. Bạn cần có:

~~~text
wiremock/
├── mappings/
│   └── stock-available.json
└── __files/
    └── stock-available-body.json
~~~

Mapping JSON mẫu `wiremock/mappings/stock-available.json`:

~~~json
{
  "request": {
    "method": "GET",
    "url": "/api/inventory/SKU-101",
    "headers": {
      "Accept": {
        "contains": "application/json"
      }
    }
  },
  "response": {
    "status": 200,
    "headers": {
      "Content-Type": "application/json"
    },
    "bodyFileName": "stock-available-body.json"
  }
}
~~~

File `wiremock/__files/stock-available-body.json`:

~~~json
{
  "sku": "SKU-101",
  "available": true,
  "quantity": 8
}
~~~

### Chạy image WireMock

~~~bash
# Version mang tính ví dụ từ tài liệu WireMock;
# chọn tag thực tế đã được tổ chức kiểm tra và ghim.
docker run --rm --name inventory-wiremock \
  -p "127.0.0.1:8080:8080" \
  -v "${PWD}/wiremock:/home/wiremock:ro" \
  wiremock/wiremock:3.13.2
~~~

Theo tài liệu WireMock Docker, `/home/wiremock` là thư mục gốc chứa `mappings` và `__files`. Đây là cú pháp volume kiểu Bash; dùng đường dẫn tương ứng nếu chạy PowerShell/Docker Desktop.

Smoke test:

~~~bash
curl -i \
  -H "Accept: application/json" \
  http://127.0.0.1:8080/api/inventory/SKU-101
~~~

Để xem mappings đã load:

~~~bash
curl -i http://127.0.0.1:8080/__admin/mappings
~~~

**Lưu ý bảo mật:** WireMock admin API cũng có khả năng quản lý stubs. Không mở nó ra Internet trong bài kiểm thử này. Nếu chỉ cần mappings tĩnh, mount resource read-only sẽ giảm nguy cơ sửa tệp host từ container, nhưng một số thao tác admin ghi xuống đĩa có thể không hoạt động như môi trường writable.

### Chuyển từ SCC stub JAR sang WireMock filesystem

Nếu đã có artifact `*-stubs.jar` của Spring Cloud Contract, bạn có thể **giải nén và chọn các HTTP mappings/fixtures tương thích** để đặt dưới `wiremock/mappings` và `wiremock/__files`.

**Không giả định** rằng mount nguyên JAR vào `/home/wiremock` sẽ tự tạo ra mappings. Bạn cần:

1. Kiểm tra các entry trong JAR.
2. Xác định các thư mục `META-INF/.../mappings` và body files mà mappings tham chiếu.
3. Copy/giải nén chúng theo root filesystem mà WireMock đọc.
4. Giữ đúng đường dẫn tương đối của `bodyFileName`.
5. Xác nhận WireMock version đọc được mapping syntax đã sinh.
6. Chạy smoke tests để chứng minh request match và response đúng.

Các lệnh kiểm tra artifact trên host:

~~~bash
jar tf inventory-producer-1.1.0-rc.1-stubs.jar
~~~

**Tránh copy bằng cách flatten mọi thư mục** nếu mapping dùng file body path tương đối. Với messaging contract, việc chỉ copy HTTP mappings sang WireMock **không tạo cơ chế phát message theo label**. Hãy dùng Stub Runner Boot có messaging adapter/broker phù hợp.

## 11. Stub Runner Docker hay WireMock Docker: tiêu chí chọn

| Yêu cầu | Nên chọn | Tại sao |
|---|---|---|
| Consumer cần artifact `group:artifact:version:stubs` từ Maven repo | **Stub Runner Boot Docker** | Resolve artifact và khởi chạy stubs theo tọa độ |
| Nhiều consumer/ngôn ngữ cần một HTTP endpoint test | **Cả hai** | Đều có thể phục vụ HTTP stubs độc lập |
| Cần message label `StockChanged` | **Stub Runner Boot Docker** với integration messaging | Có API trigger và tích hợp thông điệp |
| Chỉ có JSON `mappings` và `__files` | **WireMock Docker** | Không cần Spring Boot Stub Runner |
| Cần WireMock fault/delay độc lập do consumer quyết định | **WireMock Docker** | Phù hợp service virtualization và resilience tests |
| Cần producer verification từ Groovy/YAML DSL | **Producer verifier/test pipeline** | Docker stub không tự kiểm chứng producer |
| Cần tối giản số lượng container cho một tập HTTP mappings nhỏ | **WireMock Docker** | Setup trực tiếp với volume filesystem |
| Cần biết artifact version nào đang mô phỏng | **Stub Runner Boot Docker** hoặc mapping kèm metadata CI | Stub Runner có quan hệ rõ hơn với artifact coordinate |

Một chiến lược thực tế có thể dùng **Stub Runner Boot** cho consumer-driven contract tests, và **WireMock Docker** cho fault/timeout tests được consumer thiết kế riêng. Điều quan trọng là biết **nguồn mapping** nào đang phục vụ request.

## 12. Messaging contract trong container: cần broker thật hoặc test adapter đúng

Với Spring Cloud Contract messaging DSL, một hợp đồng có thể có:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    label 'stock_changed'

    input {
        triggeredBy('emitStockChanged()')
    }

    outputMessage {
        sentTo('stock-events')
        body(eventType: 'StockChanged', sku: 'SKU-101', quantity: 0)
        headers {
            messagingContentType(applicationJson())
        }
    }
}
~~~

Producer generated test cần gọi method `emitStockChanged()`, nhận message thực của producer trong test environment rồi assert payload/header.

Ở phía consumer, Stub Runner Boot cung cấp HTTP API kích hoạt label:

~~~bash
curl -i http://127.0.0.1:8750/triggers

curl -i -X POST \
  http://127.0.0.1:8750/triggers/stock_changed
~~~

**Quan trọng:** POST trigger thành công không tự chứng minh consumer đã xử lý xong message. Consumer test cần chờ trạng thái nghiệp vụ, ví dụ projection tồn kho chuyển thành 0, theo timeout có giới hạn.

### Cấu hình messaging trong Stub Runner Docker

Theo tài liệu Docker Project của Spring Cloud Contract, image Stub Runner hỗ trợ biến `MESSAGING_TYPE` cho các kiểu broker/integration được hỗ trợ, ví dụ:

~~~text
MESSAGING_TYPE=rabbit
MESSAGING_TYPE=kafka
~~~

Cấu hình kết nối điển hình:

~~~text
SPRING_RABBITMQ_ADDRESSES=rabbitmq:5672
SPRING_KAFKA_BOOTSTRAP_SERVERS=kafka:9092
~~~

Các giá trị `rabbitmq` và `kafka` ở đây là **tên service trong một Docker network minh họa**; không tự tạo broker. Broker/container tương ứng, authentication, listener, topic/queue và binder phải được cấu hình đầy đủ theo công nghệ.

**Không dùng `localhost:9092` từ trong Stub Runner container** để chỉ Kafka container khác: `localhost` là chính container Stub Runner. Ngoài ra, Kafka advertised listeners phải trả một địa chỉ mà **mọi client trong network test có thể truy cập**; chỉ sửa bootstrap servers mà không xử lý advertised listeners có thể khiến kết nối ban đầu thành công nhưng metadata sau đó trỏ sai.

### Giới hạn của Docker messaging test

Ngay cả khi Stub Runner phát message thành công:

- Chưa chứng minh producer publisher code đã phát đúng (cần producer contract test).
- Chưa chứng minh broker production đáp ứng throughput, partition ordering hoặc durability.
- Chưa chứng minh consumer đã commit state (cần assertion sau khi xử lý).
- Không tự kiểm chứng duplicate delivery, retry, outbox transaction hoặc DLQ.

Các điều đó cần integration/resilience tests phù hợp với broker được dùng thật.

## 13. Kết nối consumer bằng URL đúng môi trường

Một test dễ sai là tiếp tục gọi URL production vì chỉ “khởi động thêm stub” mà không **đổi cấu hình HTTP client**.

### Consumer chạy trên host

~~~bash
# Đây là ví dụ với ứng dụng đọc biến INVENTORY_BASE_URL.
export INVENTORY_BASE_URL="http://127.0.0.1:9876"

# Sau khi stub sẵn sàng mới chạy consumer tests.
./mvnw test
~~~

### Consumer chạy trong Docker network

~~~yaml
environment:
  INVENTORY_BASE_URL: "http://inventory-stub:9876"
~~~

Lưu ý: `INVENTORY_BASE_URL` là biến giả định consumer hỗ trợ, ví dụ Spring Boot property `inventory.base-url` được map từ environment. Nếu consumer không sử dụng property này khi tạo client, đặt env var cũng **không tự thay đổi URL**.

**Không dùng `@StubRunnerPort` trong một ứng dụng consumer container độc lập** rồi chờ inject cổng như trong Spring JUnit test, trừ khi test có Stub Runner embedded được cấu hình tương ứng. Khi Stub Runner chạy như dịch vụ **container bên ngoài**, consumer nên dùng URL/port của container đó.

### Health/readiness của consumer

Nếu consumer application start cùng thời điểm Stub Runner đang tải Maven artifact:

- `depends_on` có thể chỉ bảo đảm tiến trình stub container bắt đầu, không phải mapping đã sẵn sàng.
- Consumer cần retry có giới hạn ở tầng test bootstrap hoặc pipeline chờ readiness trước khi chạy.
- Nếu ứng dụng production có retry thật, tách rõ **logic resilience sản phẩm** với việc test runner “đợi hạ tầng dựng xong”.

Không để một test fail ngẫu nhiên chỉ vì consumer đã gửi request 200 ms trước khi Stub Runner load mapping.

## 14. Viết smoke check có giới hạn cho CI

Với môi trường host có `curl`, có thể kiểm tra readiness theo cả admin và stub HTTP:

~~~bash
#!/usr/bin/env bash
set -euo pipefail

admin="http://127.0.0.1:8750/stubs"
api="http://127.0.0.1:9876/api/inventory/SKU-101"

ready=0
for attempt in $(seq 1 30); do
  if curl --fail --silent "$admin" >/dev/null &&
     curl --fail --silent \
       -H "Accept: application/json" "$api" >/dev/null; then
    ready=1
    break
  fi
  sleep 2
done

if [ "$ready" -ne 1 ]; then
  echo "Stub Runner not ready; inspect container logs" >&2
  exit 1
fi

echo "Stub is ready for consumer tests"
~~~

Đây là **ví dụ script Bash**; cần `curl`, `seq`, `sleep` trên runner. Với PowerShell/Windows, chuyển sang vòng lặp phù hợp. Dù script này có giới hạn số lần thử, nó **chỉ** kiểm tra HTTP status thành công của một request. Với yêu cầu nghiêm ngặt hơn, hãy kiểm tra thêm JSON body bằng JSON parser/consumer test và xác nhận version artifact thông qua log hoặc API của Stub Runner.

**Không nên dùng một `sleep 30` cố định** thay cho readiness: nếu stub ready sau 3 giây, đó là lãng phí; nếu repo tải mất 40 giây, vẫn fail. Vòng lặp có deadline giúp chẩn đoán rõ ràng hơn.

## 15. Một workflow CI dùng container stub

Ví dụ tổ chức pipeline, chưa phụ thuộc vào một dịch vụ CI cụ thể:

~~~mermaid
sequenceDiagram
    participant PR as Pull request
    participant P as Producer verification
    participant A as Candidate stub artifact
    participant D as Docker / Stub Runner
    participant C as Consumer test
    PR->>P: Generate + run producer contract tests
    alt Producer test PASS
      P->>A: Package candidate stubs from same revision
      A->>D: Resolve artifact with pinned version
      D->>D: Start HTTP stub 9876
      C->>D: Smoke-check /stubs and /api/inventory/SKU-101
      C->>D: Send real consumer HTTP requests
      C->>C: Assert business behavior
    else Producer test FAIL
      P-->>PR: Block publish
    end
~~~

Với job consumer ở host, script tổng quát minh họa:

~~~bash
#!/usr/bin/env bash
set -euo pipefail

# Cần set SCC_IMAGE_TAG và STUB_REPO_URL trước.
# compose.yaml cần nội dung như mục 8.
cleanup() {
  docker compose down --remove-orphans
}
trap cleanup EXIT

docker compose up -d inventory-stub

# Gọi script readiness có giới hạn ở mục 14.
./wait-for-inventory-stub.sh

# Ví dụ consumer Spring Boot đọc inventory.base-url qua env.
INVENTORY_BASE_URL="http://127.0.0.1:9876" \
  ./mvnw -B -ntp test
~~~

Đây là **pseudocode pipeline dễ áp dụng**, không phải một bộ file mà bài học đã tạo. Bạn cần tự tạo script readiness, Compose file, cấu hình test và cách truyền candidate artifact cho môi trường thực.

### Năm điều cần kiểm tra ở CI

1. **Producer tests đã chạy và PASS**, không bị skip/disable, không xanh vì `0 tests`.
2. **Stub container dùng đúng candidate artifact**, không dùng `latest` hoặc cache cũ.
3. **Container có thể truy cập repository**, và credentials không bị lộ trong logs.
4. **Cổng/URL khớp nơi consumer chạy** (host khác với Docker network).
5. **Consumer test dùng HTTP client thật**, assert trạng thái/mã lỗi/JSON/message handler phù hợp, không chỉ kiểm tra stub container chạy.

Nếu producer vừa sửa contract và implementation cùng lúc, generated producer test với contract mới vẫn có thể PASS dù consumer cũ bị phá vỡ. Vì vậy consumer tests cần chạy với **candidate stub của revision đó**, và thay đổi breaking phải được đánh giá trước khi phát hành.

## 16. Vấn đề version và nguồn stub

Một môi trường container có thể chạy stubs qua ba nguồn phổ biến, phụ thuộc cấu hình Stub Runner:

| Mode | Nguồn stub | Ứng dụng trong container |
|---|---|---|
| `REMOTE` | Maven/Artifactory/Nexus hoặc nguồn artifact được hỗ trợ | Hợp cho CI hoặc môi trường nhiều đội, cần network và quyền đọc |
| `LOCAL` | Maven local repository đã mount vào container | Hợp khi developer/CI đã cài candidate vào cache riêng |
| `CLASSPATH` | Artifact/resource có trong classpath của app Stub Runner | Cần image/custom runtime chứa đúng resource; không đồng nghĩa mount JAR tùy ý |

Đối với **Docker Stub Runner Boot**, hai trường hợp `REMOTE` và `LOCAL` thường trực tiếp hơn. `CLASSPATH` cần cách đóng gói và cấu hình tương ứng của image/version; không nên kỳ vọng một volume trỏ tới `*.jar` là Stub Runner tự quét được classpath.

### Version bất biến

Một ký hiệu version như `+` hoặc một alias `latest` thuận tiện khi thử nghiệm, nhưng không phù hợp làm bằng chứng CI:

~~~text
Producer commit A -> candidate 1.1.0-rc.1
Consumer test    -> phải dùng 1.1.0-rc.1

Không nên:
Producer commit A -> candidate 1.1.0-rc.1
Consumer test    -> lấy newest/latest bất kỳ
~~~

Với `SNAPSHOT` mutable, tránh tình huống cùng version nhưng byte artifact thay đổi giữa lần verify và lần consumer test. Gắn commit/build ID hoặc checksum, lưu version đã resolve và sử dụng artifact candidate từ đúng job producer.

## 17. Bảo mật: không đưa Stub Runner Boot lên môi trường không tin cậy

Tài liệu Spring Cloud Contract cảnh báo Stub Runner Boot **không được bảo mật theo thiết kế**, bởi đây là công cụ kiểm thử; không nên chạy ở production hoặc môi trường nhiều client không tin cậy.

Các khuyến nghị:

- Bind admin port vào `127.0.0.1` trên host hoặc dùng Docker network test riêng.
- Không tạo ingress/public load balancer cho endpoint `/stubs` và `/triggers`.
- Không mount Docker socket `/var/run/docker.sock` vào stub container khi không có nhu cầu.
- Tránh đưa mật khẩu repository/secret vào Dockerfile, command line lưu lịch sử hoặc Compose file commit.
- Không dùng fixture chứa token, dữ liệu người dùng thật hoặc URL nội bộ nhạy cảm.
- Chạy container với quyền nhỏ nhất mà image và filesystem cho phép.
- Hạn chế quyền ghi lên volume và không reuse state giữa các bộ test không liên quan.
- Chỉ cung cấp HTTP stub cho các client test có quyền truy cập theo mạng test cô lập.
- Không biến Stub Runner Boot thành proxy được dùng bởi production traffic.

Đối với WireMock OSS Docker, `/__admin` cũng là API quản trị. Giới hạn mạng tương tự là một thói quen tốt ngay cả khi chỉ dùng mapping test.

## 18. Các lỗi phổ biến khi chạy stub trong container

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra |
|---|---|---|
| Image không pull được | Sai image repository/tag, registry thiếu quyền hoặc version không tồn tại | Đối chiếu image chính thức và kiểm tra tag thực tế |
| Container chạy nhưng `/stubs` rỗng | Artifact resolve sai, không có mappings, config `ids` sai | Xem log Stub Runner, tọa độ và JAR |
| `/stubs` không truy cập được | Sai admin port hoặc mapping `-p` | Kiểm tra server port thực và Docker published ports |
| `/stubs` có stub nhưng `:9876` từ host lỗi | Chưa publish cổng WireMock hoặc cổng trong `ids` không khớp | Kiểm tra `STUBRUNNER_IDS` và `docker port` |
| Consumer container không tới `localhost:9876` | `localhost` trỏ chính consumer container | Dùng tên Compose service `inventory-stub` |
| Stub trả `404` ngoài ý muốn | Request không match method/path/header/body | Xem mapping, request journal và URL thực |
| Stub trả sai fixture | Dùng artifact version cũ hoặc mapping chồng lấn | Ghim version/digest, kiểm tra contract/mapping |
| Repository bên host chạy được nhưng container không truy cập | DNS, proxy, network, CA hoặc credentials khác | Thử truy cập từ network/container test phù hợp |
| `LOCAL` không tìm được stub | Mount sai `~/.m2` hoặc chưa install artifact | Kiểm tra path volume, artifact/pom và quyền |
| `LOCAL` vẫn dùng bản cũ | Cache có cùng version mutable | Dùng version duy nhất/cache cô lập |
| `bodyFileName` trả lỗi | Thiếu `__files` hoặc sai đường dẫn tương đối | Kiểm tra mapping và filesystem root |
| Container WireMock dùng nhầm JAR | Mount nguyên `*-stubs.jar` thay vì mappings | Giải nén đúng mapping/body files |
| Messaging trigger có nhưng consumer không nhận | Chưa có broker/binder, sai destination hoặc listener | Kiểm tra `MESSAGING_TYPE`, broker routing và consumer handler |
| CI fail ngẫu nhiên lúc start | Chỉ dùng `depends_on`/sleep cố định | Thêm readiness probe có deadline |
| Container tự tắt hoặc port conflict | Nhiều suite cùng dùng host port | Tách môi trường/test network hoặc dùng port mapping khác |
| POST không an toàn bị gọi sang production | Base URL consumer chưa thay | Inject URL stub và chặn egress không cần thiết |

### Vì sao `404` chưa chắc là “not found” theo contract?

WireMock có thể trả `404` khi request **không khớp mapping nào**. Nếu consumer test muốn kiểm tra nghiệp vụ `SKU_NOT_FOUND`, phải có mapping trả `404` với mã lỗi cụ thể, rồi assert **error body/code**. Chỉ assert status 404 có thể tạo test xanh giả do URL bị gõ sai.

### Vì sao tăng timeout không chữa lỗi routing?

Nếu `STUBRUNNER_IDS` dùng cổng `9877` nhưng consumer gọi `9876`, đợi lâu hơn không thay đổi đích. Tương tự, nếu container consumer trỏ `localhost` thay vì service name, tăng read timeout không tạo kết nối sang container khác.

**Thứ tự debug:** artifact → Stub Runner startup → cổng trong container → published port/network → request matcher → response/assertion.

## 19. Bài tập thực hành

### Tình huống A — Chọn đúng công cụ

Nhóm có một `inventory-producer-1.1.0-rc.1-stubs.jar` được producer kiểm chứng và muốn cho một ứng dụng Python trong Compose gọi HTTP API giả lập.

**Chọn gì?** Stub Runner Boot Docker, vì nó hiểu cách resolve artifact và khởi chạy HTTP stubs. Nếu chỉ dùng WireMock Docker, cần giải nén các mappings và body files từ artifact trước.

**Câu hỏi:** Cổng nào consumer gọi?

**Đáp án:** Cổng HTTP stub, ví dụ `9876`, không phải admin port `8750`.

### Tình huống B — Container gọi nhầm localhost

Compose có hai service `checkout-test` và `inventory-stub`. Checkout dùng:

~~~properties
inventory.base-url=http://localhost:9876
~~~

Checkout báo connection refused, dù host dùng `curl http://127.0.0.1:9876` thành công.

**Nguyên nhân:** `localhost` bên trong checkout container chỉ chính checkout container.

**Sửa:**

~~~properties
inventory.base-url=http://inventory-stub:9876
~~~

Hai service phải ở **cùng Docker network**, Stub Runner có stub thực sự lắng nghe trên cổng `9876`.

### Tình huống C — Producer thay đổi nhưng test vẫn xanh

Producer vừa đổi `quantity` từ number `8` sang string `"8"`, nhưng consumer test chạy `wiremock/wiremock` với mapping viết tay cũ luôn trả number `8`. Test vẫn xanh.

**Vấn đề:** mapping tự viết không tự theo kịp producer contract/implementation. Cần generated producer contract tests và consumer test với **candidate stub từ cùng revision**, không lấy màu xanh của mapping cũ làm bằng chứng tương thích.

### Tình huống D — Docker Compose chỉ dùng depends_on

Checkout start sau Stub Runner process nhưng trước khi Stub Runner tải xong artifact; request đầu nhận 404 hoặc connection refused.

**Cách giải:** thêm readiness check thật cho stub endpoint (hoặc healthcheck có ý nghĩa) và giới hạn thời gian chờ. Chỉ khởi chạy consumer tests sau khi stub trả đúng smoke response.

### Tình huống E — Messaging trigger không chạy

Stub Runner Boot trả danh sách label `stock_changed` nhưng consumer không nhận event sau `POST /triggers/stock_changed`.

Hãy kiểm tra:

1. `MESSAGING_TYPE` có phù hợp với broker/binder được sử dụng không?
2. Stub Runner container có kết nối được broker bằng **địa chỉ nội bộ Docker network** không?
3. Destination/topic/queue, header và message converter có đúng không?
4. Consumer listener có chạy và đăng ký đúng destination không?
5. Consumer test có đợi kết quả xử lý bất đồng bộ với timeout hữu hạn không?

### Bài tập nâng cao

Thiết kế một `compose.yaml` gồm hai stub HTTP:

- Inventory ở `9876` và Pricing ở `9877`.
- Consumer chạy trên host cần gọi cả hai bằng `127.0.0.1`.
- Consumer container chạy cùng Compose cần gọi bằng tên service.
- Admin API `8750` chỉ được phép truy cập trong phạm vi test.
- Hai artifact phải có version xác định và được producer tests kiểm chứng.

Giải thích cách bạn chứng minh **đúng version đã nạp**, không trùng cổng, và không vô tình gọi dịch vụ production.

## 20. Checklist triển khai stub container

- [ ] Đã xác định mục đích: **Stub Runner Boot** theo artifact Spring Cloud Contract hay **WireMock Docker** theo JSON mappings.
- [ ] Producer Groovy/YAML contracts và generated tests đã được kiểm chứng thực sự.
- [ ] Candidate stub artifact có tọa độ/version truy vết được, không dùng alias `latest` mơ hồ.
- [ ] Image repository/tag tồn tại, tương thích và được ghim.
- [ ] `STUBRUNNER_IDS` có đúng group/artifact/version/classifier/**container port**.
- [ ] `STUBRUNNER_STUBS_MODE` và repository/cache phù hợp, không dùng artifact stale.
- [ ] Stub Runner admin port và HTTP stub port được phân biệt rõ.
- [ ] Docker publish/bind cổng đúng host và không mở admin API ra Internet.
- [ ] Nếu consumer chạy trong Compose, URL dùng **service name**, không dùng localhost sai ngữ cảnh.
- [ ] Nếu dùng WireMock Docker, có đúng `mappings`/`__files` và relative paths.
- [ ] Repository credentials, broker credentials và fixtures không bị lộ.
- [ ] Với messaging, broker/binder/destination được nối đúng; trigger không thay thế assertion xử lý của consumer.
- [ ] Có readiness wait có deadline, không chỉ `sleep` hoặc `depends_on`.
- [ ] Consumer test gọi HTTP client thật, assert response/error body theo contract.
- [ ] CI chỉ coi candidate là bản đã kiểm chứng sau khi producer test PASS.
- [ ] Stub container được dọn sau test, log/metadata cần thiết được lưu để điều tra.

## 21. Ghi nhớ và tài liệu tham khảo

**Chạy stub trong container là cách phân phối môi trường mô phỏng producer cho consumer test, không phải một bước xác nhận code producer.** Với Spring Cloud Contract, chọn **Stub Runner Boot Docker** khi cần tải artifact `:stubs` theo version, quản lý nhiều stub và kích hoạt message theo label. Chọn **WireMock Docker** khi đã có HTTP mapping JSON và muốn một HTTP server mô phỏng đơn giản, có thể kiểm soát lỗi và độ trễ.

Bất kể lựa chọn nào, hãy kiểm tra **hai địa chỉ**: cổng quản trị công cụ và cổng API mà consumer thực sự gọi; đồng thời phân biệt **localhost của host** với **localhost trong container**. Chỉ chạy consumer tests khi stub đã tải đúng artifact và mapping sẵn sàng, giữ version bất biến và không đưa các endpoint quản trị test lên production/public network.

### Tài liệu chính thức

- [Spring Cloud Contract — Docker Project](https://docs.spring.io/spring-cloud-contract/reference/docker-project.html): image cho producer verification và consumer-side Stub Runner Docker, biến môi trường, LOCAL/REMOTE và messaging.
- [Spring Cloud Contract — Stub Runner Boot](https://docs.spring.io/spring-cloud-contract/reference/project-features-stubrunner/stub-runner-boot.html): HTTP endpoints `/stubs`, `/triggers` và cảnh báo bảo mật.
- [Spring Cloud Contract — Configuration Properties](https://docs.spring.io/spring-cloud-contract/reference/configprops.html): các stubrunner properties, source, fail-on-no-stubs và tùy chọn runtime.
- [WireMock OSS — Running in Docker](https://wiremock.org/docs/standalone/docker/): image `wiremock/wiremock`, cách mount `mappings`, `__files` và Docker Compose.
- [WireMock OSS — Stubbing](https://wiremock.org/docs/stubbing/): cú pháp mapping JSON, body files, request matching và phản hồi.
- [Docker — Networking in Compose](https://docs.docker.com/compose/how-tos/networking/): định tuyến theo tên service trong Compose network.

**Kết luận:** một stub container test đáng tin phải đáp ứng ba câu hỏi: **artifact/mapping nào đang chạy**, **consumer thực sự gọi đến đâu**, và **producer đã chứng minh hợp đồng đó bằng test chưa**. Khi cả ba đều được kiểm tra, container hóa Stub Runner hoặc WireMock giúp hệ thống đa ngôn ngữ kiểm thử độc lập mà vẫn giữ tính tương thích giữa producer và consumer.
