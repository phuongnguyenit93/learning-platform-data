# Quản lý vòng đời, cấu hình và phiên bản stub độc lập

## 1. Stub độc lập giải quyết vấn đề gì?

Trong **Spring Cloud Contract**, producer và consumer thống nhất hành vi API bằng **Groovy DSL** hoặc **YAML DSL**. Bộ **Spring Cloud Contract Verifier** có thể sinh kiểm thử cho producer và tạo stub; consumer dùng **Stub Runner** hoặc một WireMock server để chạy kiểm thử mà không phải khởi động producer thật. Khi đưa các thành phần ấy vào CI, nhóm phát triển có thể phát hiện thay đổi API không tương thích từ trước lúc triển khai.

Thông thường, một consumer test có thể dùng `@AutoConfigureStubRunner` để khởi động stub ngay trong vòng đời kiểm thử. Nhưng có những tình huống cần **stub chạy độc lập như một tiến trình hoặc container**:

- Frontend, ứng dụng di động hoặc một dịch vụ không dùng Java cần một HTTP endpoint giả lập ổn định.
- Nhiều nhóm cùng kiểm tra một bản hợp đồng đã phát hành mà không chạy ứng dụng producer thật.
- Kiểm thử tích hợp cần khởi động stub **trước** khi khởi động consumer.
- CI muốn cấp phát, kiểm tra readiness và thu hồi các stub như những dịch vụ test riêng.
- Nhóm cần tái hiện một bug bằng đúng **stub artifact/version** đã dùng trong một lần build trước.

**Stub độc lập** không có nghĩa “chạy production service ở chế độ test”. Đó là một server mô phỏng các hành vi đã được mô tả, chẳng hạn WireMock nhận `GET /api/orders/42` rồi trả JSON mẫu. Nó **không có database hoặc logic nghiệp vụ của producer**, trừ khi bạn tự triển khai thêm mô phỏng có trạng thái.

Mục tiêu bài học là quản lý được **vòng đời** (start → ready → serve → reset → stop), **cấu hình** (artifact, repository, cổng, mạng, file root, chế độ chạy) và **phiên bản** (đúng hợp đồng, đúng classifier, có thể truy vết và tái lập).

## 2. Hai mô hình chạy stub độc lập: đừng đánh đồng

Trong thực tế có hai đường triển khai phổ biến:

| Mô hình | Tài nguyên đầu vào | Runtime | Phù hợp với |
|---|---|---|---|
| **WireMock standalone** | `mappings/` và `__files/` đã chuẩn bị | WireMock chạy trong JVM/container | Test/mock API HTTP với file mapping cụ thể |
| **Stub Runner Boot/standalone** | Artifact `group:artifact:version:stubs` trong kho Maven tương thích | Một ứng dụng Stub Runner độc lập nạp và chạy stubs | Tái sử dụng stubs do producer Spring Cloud Contract publish |

Chúng liên quan nhưng không hoàn toàn giống nhau:

- WireMock standalone **không tự suy ra artifact Maven** hoặc tự chạy generated producer tests; nó đọc mapping tại file root mà bạn chỉ định.
- Stub Runner có trách nhiệm **resolve các stub artifacts** theo tọa độ/cấu hình và khởi động cơ chế phục vụ tương ứng. Với stub HTTP, runtime thường dùng WireMock.
- Gói `-stubs.jar` **không phải** ứng dụng executable; không nên giả định chạy được bằng `java -jar order-service-1.4.0-stubs.jar`.
- Với hợp đồng **messaging**, không thể lấy một WireMock HTTP standalone server rồi mặc định nó phát được Kafka/RabbitMQ messages; cần messaging adapter/test binder hoặc cơ chế stub phù hợp.

Trong bài này, ví dụ chính là **HTTP**. Những giới hạn của messaging và stateful scenarios được phân tích riêng để tránh hiểu nhầm.

```mermaid
flowchart LR
    A["Hợp đồng Groovy/YAML"] --> B["Spring Cloud Contract Verifier"]
    B --> C["Generated producer tests"]
    B --> D["WireMock mappings + body files"]
    D --> E["-stubs.jar có version"]
    E --> F["Stub Runner độc lập"]
    D --> G["WireMock standalone<br/>sau khi chuẩn bị file root"]
    F --> H["Consumer tests"]
    G --> H
    C --> I["Producer thật"]
```

**Nguyên tắc:** Stub độc lập chỉ đem lại một **API giả lập**; việc producer thật tuân thủ hợp đồng vẫn phải được xác minh bằng generated producer tests.

## 3. Một hợp đồng nguồn xuyên suốt

Giả sử producer `order-service` công bố:

```http
GET /api/orders/42
Accept: application/json
```

Trả về:

```http
HTTP/1.1 200 OK
Content-Type: application/json

{"id":42,"state":"PAID","currency":"VND"}
```

### 3.1. Groovy DSL

```groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Tìm một đơn hàng đã thanh toán'

    request {
        method GET()
        url '/api/orders/42'
        headers {
            header 'Accept', 'application/json'
        }
    }

    response {
        status OK()
        headers {
            contentType(applicationJson())
        }
        body(
            id: 42,
            state: 'PAID',
            currency: 'VND'
        )
    }
}
```

### 3.2. YAML DSL tương đương

```yaml
description: Tìm một đơn hàng đã thanh toán
request:
  method: GET
  url: /api/orders/42
  headers:
    Accept: application/json
response:
  status: 200
  headers:
    Content-Type: application/json
  body:
    id: 42
    state: PAID
    currency: VND
```

Đây là **hai cách biểu đạt cùng kịch bản**, không yêu cầu cùng lưu cả hai để tránh tạo hai contract trùng lặp. Verifier sinh test producer và mapping cho stub theo cấu hình build.

Để consumer kiểm tra lỗi nghiệp vụ, nên có contract riêng, ví dụ `GET /api/orders/9999` trả `404` với body `{"code":"ORDER_NOT_FOUND"}`. **Không nhầm 404 do WireMock không tìm thấy mapping** với response lỗi nghiệp vụ đã được producer cam kết.

## 4. Vòng đời của một stub server độc lập

Vòng đời nên được quản lý như một tài nguyên kiểm thử, không phải một tiến trình chạy mãi không rõ chủ sở hữu:

```mermaid
stateDiagram-v2
    [*] --> Stopped
    Stopped --> Starting: Khởi động process/container
    Starting --> Ready: Bind port, nạp mappings, kiểm tra được
    Starting --> Failed: Bind/resolve/config lỗi
    Ready --> Serving: Consumer bắt đầu test
    Serving --> Ready: Dọn request journal/scenarios phù hợp
    Ready --> Stopping: Kết thúc suite/CI
    Serving --> Stopping: Kết thúc suite/CI
    Failed --> Stopping: Thu hồi tài nguyên
    Stopping --> Stopped: Dừng và giải phóng cổng
```

| Giai đoạn | Công việc | Bằng chứng mong đợi |
|---|---|---|
| **Resolve/configure** | Chọn artifact hoặc file root, version, repository, port | Tọa độ và cấu hình đúng, có thể truy vết |
| **Start** | Tạo process/container, bind cổng, load stubs | Runtime đang sống, không có lỗi khởi tạo |
| **Ready** | Kiểm tra server chấp nhận request **đúng mapping** | Request thăm dò nhận response/status/body mong đợi |
| **Serve** | Consumer gửi HTTP vào URL stub | Request đúng được match, assertions ở consumer đạt |
| **Reset/isolate** | Làm sạch request history/scenario hoặc cấp instance mới | Test sau không phụ thuộc test trước |
| **Stop/cleanup** | Dừng server/container, dọn resource test | Port và tài nguyên được giải phóng |

**Process đã tồn tại không đồng nghĩa server đã sẵn sàng.** Một ứng dụng Stub Runner Boot có thể mở cổng quản trị nhưng chưa resolve được artifact, hoặc WireMock đang chạy nhưng chưa load đúng mappings. Cổng mở chỉ là kiểm tra sơ bộ; một probe tới **endpoint mẫu** có giá trị hơn.

### 4.1. Ai sở hữu vòng đời?

Nên có **một chủ sở hữu rõ ràng** cho từng stub instance:

- Test class hoặc test suite, nếu stub chỉ phục vụ một bộ test.
- CI job, nếu nhiều test/process dùng chung stub trong cùng job.
- Container orchestration/test environment, nếu stub phục vụ một môi trường tích hợp.

Chủ sở hữu chịu trách nhiệm start, chờ ready, cấp URL cho consumer, reset phù hợp và stop. Không để nhiều bộ test cùng xóa mappings của một instance dùng chung hoặc tự tắt server mà test khác còn cần.

## 5. Phiên bản, classifier và tính tái lập của artifact

Một dạng tọa độ phổ biến cho Stub Runner:

```text
com.example:order-service:1.4.0:stubs:8090
|_________|_____________|_____|_____|____|
    group     artifact   version classifier port
```

| Trường | Ví dụ | Ý nghĩa |
|---|---|---|
| Group | `com.example` | Tổ chức/module phát hành |
| Artifact | `order-service` | Producer có stub |
| Version | `1.4.0` | Bản hợp đồng được lấy |
| Classifier | `stubs` | Biến thể JAR chứa mappings/tài nguyên stub |
| Port | `8090` | Cổng HTTP được yêu cầu cho stub này khi chạy |

**Cổng không phải metadata của JAR.** Nó được chọn ở môi trường runtime; cùng một artifact `1.4.0:stubs` có thể phục vụ ở các cổng khác nhau.

### 5.1. Cố định phiên bản thay vì luôn lấy “mới nhất”

| Cách dùng | Ưu điểm | Rủi ro | Khuyến nghị |
|---|---|---|---|
| `1.4.0` | Kết quả dễ tái lập | Cần chủ động nâng version | **Ưu tiên** cho CI phát hành |
| `+` trong cấu hình hỗ trợ | Dễ thử bản mới được resolver tìm thấy | Thay đổi theo repository/cache/thời điểm | Dùng ở job canary, ghi resolved version |
| `1.5.0-SNAPSHOT` | Hữu ích trong phát triển | Nội dung snapshot có thể thay đổi | Ghi commit/build/checksum, kiểm soát cache |
| Release bất biến | Có thể audit và rollback | Đòi quy trình publish | Phù hợp pipeline nghiêm ngặt |

Không mặc định version mới hơn là **tương thích ngược**. Thay đổi `state` thành một enum mới, đổi kiểu JSON number sang string hoặc đổi `404` thành `200` có thể làm consumer hỏng dù producer tăng minor/patch version.

### 5.2. Chọn đúng artifact thay vì JAR ứng dụng

Ví dụ producer có:

```text
order-service-1.4.0.jar
order-service-1.4.0-stubs.jar
```

JAR đầu là ứng dụng/library producer; JAR thứ hai là **artifact để phục vụ stub** theo classifier `stubs`. Chỉ thấy `order-service-1.4.0.jar` trong repository **không chứng minh** `-stubs.jar` đã được attach và publish.

Với file đã tải từ artifact repository, có thể quan sát:

```bash
# Minh họa kiểm tra một artifact đã có trên đĩa.
jar tf order-service-1.4.0-stubs.jar
```

Hãy đọc các entry thực tế của JAR, nhất là thư mục `mappings`, `__files` (nếu cần), các định danh artifact/version, không chỉ nhìn tên file bên ngoài.

### 5.3. Bất biến artifact và provenance

Trong log CI hoặc bản ghi cấu hình môi trường test nên giữ:

```text
Producer       : com.example:order-service
Requested      : 1.4.0:stubs
Resolved       : 1.4.0:stubs
Artifact SHA256: <checksum thực tế nếu pipeline có thu thập>
Producer commit: <commit tương ứng nếu có>
Repository     : <địa chỉ kho, không bao gồm credential>
Stub port      : <port thực tế>
```

Các dấu ngoặc trên là **placeholder cần điền bằng dữ liệu quan sát thật**, không phải giá trị mặc định của Stub Runner. Nếu publisher cho phép ghi đè release cùng version, chỉ pin `1.4.0` chưa đủ để tái lập hoàn toàn: nên áp dụng **release bất biến** hoặc đối chiếu checksum.

## 6. Mô hình A: chạy WireMock standalone với thư mục stub

Trường hợp bạn đã có WireMock mappings và muốn chạy server độc lập mà không cần Maven resolver, hãy chuẩn bị một **file root** theo bố cục:

```text
wiremock-root/
├── mappings/
│   ├── get-order-42.json
│   └── get-order-not-found.json
└── __files/
    └── orders/
        └── order-42.json
```

Ví dụ `mappings/get-order-42.json`:

```json
{
  "request": {
    "method": "GET",
    "urlPath": "/api/orders/42",
    "headers": {
      "Accept": { "equalTo": "application/json" }
    }
  },
  "response": {
    "status": 200,
    "headers": {
      "Content-Type": "application/json; charset=utf-8"
    },
    "bodyFileName": "orders/order-42.json"
  }
}
```

Ví dụ `__files/orders/order-42.json`:

```json
{
  "id": 42,
  "state": "PAID",
  "currency": "VND"
}
```

Ở đây `bodyFileName` được hiểu **tương đối với `__files/`**, không phải đường dẫn tuyệt đối đến ổ đĩa. Một mapping cũng có thể chứa `response.body`/`jsonBody` inline; **không phải mapping nào cũng cần body file**.

### 6.1. Khởi động WireMock standalone JAR

Khi đã có **WireMock standalone runnable JAR** tương thích với Java runtime của bạn:

```bash
# Lệnh ví dụ; thay tên JAR, root-dir và port theo môi trường.
java -jar wiremock-standalone-<VERSION>.jar \
  --port 8090 \
  --root-dir ./wiremock-root
```

`<VERSION>` là placeholder; **không** phải tên file được cung cấp sẵn. Khi server bắt đầu, consumer có thể gọi:

```bash
curl -i \
  -H "Accept: application/json" \
  http://127.0.0.1:8090/api/orders/42
```

Phản hồi phải có `200` và JSON đã mô tả. Nếu nhận `404`, đừng vội kết luận API nghiệp vụ không có order `42`: đó có thể chỉ là **WireMock không khớp mapping** vì file root sai, method/path/header sai hoặc mapping chưa load.

**Không cố chạy** `order-service-1.4.0-stubs.jar` bằng lệnh trên: JAR đó là tài nguyên stub, không phải WireMock executable. Muốn dùng file root, cần chuẩn bị/extract tài nguyên đúng cấu trúc từ artifact được publish hoặc lấy mappings/body files qua quy trình build được kiểm soát.

### 6.2. Khởi động bằng container

Ví dụ Docker Compose tối giản:

```yaml
services:
  order-stub:
    image: wiremock/wiremock:REPLACE_WITH_PINNED_VERSION
    ports:
      - "127.0.0.1:8090:8080"
    volumes:
      - ./wiremock-root:/home/wiremock:ro
```

Trong ví dụ này:

- Image tag `REPLACE_WITH_PINNED_VERSION` phải được thay bằng tag/digest hợp lệ đã xác minh trước khi chạy; tránh dùng `latest` cho CI cần tái lập.
- Đường dẫn `/home/wiremock` là file root thông dụng của image WireMock chính thức; xác minh theo image/version mà nhóm triển khai.
- Mapping từ host `127.0.0.1:8090` vào cổng HTTP `8080` **bên trong container**. Consumer chạy trên host dùng `127.0.0.1:8090`.
- Nếu consumer chạy trong **container khác cùng Docker Compose network**, nó thường phải gọi `http://order-stub:8080`, **không** phải `http://localhost:8090`.
- Mount `:ro` hạn chế sửa fixture từ container; request journal và state runtime vẫn cần được cô lập qua vòng đời server.

Đây là **cấu hình minh họa**, không được thực thi trong bài. Khi chọn cách dùng container, CI cần quản lý quyền bind, mạng, resource cleanup và policy pull image để tránh chạy một image khác bản đã kiểm chứng.

### 6.3. Lúc nào không nên dùng WireMock standalone?

Nếu mục tiêu là **tự lấy artifact `group:artifact:version:stubs` mới publish từ Maven repository**, WireMock standalone thuần túy không chịu trách nhiệm làm điều đó. Bạn sẽ phải có bước **resolve JAR → giải nén/định vị mappings, body files → cấu hình file root**. Nếu không muốn quản lý bước này, **Stub Runner độc lập** thường phù hợp hơn.

## 7. Mô hình B: Stub Runner Boot như một ứng dụng riêng

Trong hệ sinh thái Spring Cloud Contract có thể sử dụng **Stub Runner Boot** (hoặc runtime standalone được dự án đóng gói với chức năng Stub Runner) để chạy stubs ngoài JUnit test của consumer. Cần có **runnable application JAR/container đúng phiên bản** và cấu hình repository/artifact hợp lệ.

Một cách khai báo minh họa ở cấp ứng dụng:

```yaml
stubrunner:
  ids:
    - com.example:order-service:1.4.0:stubs:8090
  stubs-mode: REMOTE
  repository-root: https://repo.example.org/maven-releases
server:
  port: 8999
```

**Phân biệt hai cổng trong ví dụ:**

- `8090` nằm **trong tọa độ stub**: cổng HTTP mà WireMock của `order-service` được yêu cầu sử dụng.
- `server.port: 8999`: cổng HTTP của **ứng dụng Stub Runner Boot**, nếu bản phân phối đó khởi động server quản trị/application HTTP riêng. Nó **không nhất thiết là cổng nhận request `GET /api/orders/42`**.

Khi dùng Spring Boot relaxed binding, tên property có thể được biểu diễn ở dạng kebab/camel tùy công cụ, nhưng cần **xác minh tên và khả năng hỗ trợ theo phiên bản thực tế**. Đừng sao chép một sample từ release khác rồi giả định resolver, port hoặc REST endpoints vẫn hoạt động y hệt.

### 7.1. Lệnh khởi động có ý nghĩa

Giả sử dự án đã có một **runnable Stub Runner Boot JAR** được đặt tên cục bộ là `stub-runner-boot.jar`:

```bash
java -jar ./runtime/stub-runner-boot.jar \
  --stubrunner.ids=com.example:order-service:1.4.0:stubs:8090 \
  --stubrunner.stubs-mode=REMOTE \
  --stubrunner.repository-root=https://repo.example.org/maven-releases \
  --server.port=8999
```

Đây là **lệnh mẫu với artifact runtime đã được chuẩn bị trước**, không phải lời khẳng định mọi dự án đều tự sinh `./runtime/stub-runner-boot.jar`. Để sử dụng, phải kiểm tra **cách lấy/build launcher được hỗ trợ bởi version Spring Cloud Contract của nhóm**, yêu cầu Java, dependency và khả năng resolve artifact.

Với `LOCAL`, runtime tìm stub từ Maven local repository của **máy/container đang chạy**. Với `REMOTE`, cần repository URL và cơ chế xác thực. Với `CLASSPATH`, các tài nguyên stub phải **thực sự có trên classpath** theo cách runtime nhận diện; không phải đổi mode là tự tải stub từ mạng.

### 7.2. Nạp nhiều stub trong một runtime

Một môi trường kiểm thử có thể cần nhiều producer:

```properties
stubrunner.ids=com.example:order-service:1.4.0:stubs:8090,com.example:payment-service:2.1.0:stubs:8091
stubrunner.stubs-mode=REMOTE
stubrunner.repository-root=https://repo.example.org/maven-releases
```

Đây là **minh họa thuộc tính dạng danh sách phân tách dấu phẩy**; hãy kiểm tra cách parse của phiên bản và cấu hình thực tế. Không gán cùng cổng `8090` cho hai stub servers trong cùng namespace mạng.

Khi có nhiều stubs, consumer phải có base URL riêng cho `order-service` và `payment-service`. Không dùng một config `upstream.base-url` cho cả hai chỉ vì chúng được khởi động từ cùng launcher.

### 7.3. Khi nào không nên dùng một Stub Runner chung?

Một tiến trình chung giúp tiết kiệm chi phí, nhưng có thể gây:

- Khó cô lập request journal/scenario state theo từng test suite.
- Một lần restart làm gián đoạn nhiều nhóm consumer.
- Version của một stub thay đổi làm ảnh hưởng nhiều test không liên quan.
- Nguy cơ xung đột cổng và thao tác reset mang tính toàn cục.

Nếu các suite cần chạy song song độc lập, nên **cấp một stub environment riêng theo job** hoặc bảo đảm mỗi nhóm có namespace và quyền reset tách biệt.

## 8. Quản lý cấu hình: tách phần bất biến và phần runtime

Một cấu hình tốt phân biệt:

| Nhóm cấu hình | Ví dụ | Chiến lược |
|---|---|---|
| **Contract provenance** | `com.example:order-service:1.4.0:stubs` | Pin version, lưu commit/checksum |
| **Artifact source** | `REMOTE` + URL Maven repository | Config theo môi trường, bảo mật credentials |
| **Runtime network** | Hostname, port, container DNS | Cấp phát ở runtime, thông báo consumer |
| **Test behavior** | Scenarios, fixture, response delays | Cô lập theo suite, reset có chủ đích |
| **Operations** | Readiness timeout, logs, resource limits | Quản lý theo CI/orchestrator |

Không đưa token truy cập artifact repository vào contract, mapping hoặc commit:

```text
# Sai: credential nằm trong URL hoặc trong source.
https://username:password@repo.example.org/releases

# Tốt hơn: URL không có secret, credential được inject
# từ secrets manager/CI environment theo cơ chế resolver hỗ trợ.
https://repo.example.org/releases
```

Đối với stub runtime phục vụ nhiều ứng dụng, cần xác định **ai có quyền đổi mappings, reset scenarios và tắt server**. WireMock Admin API là giao diện có thể thay đổi trạng thái; **không nên phơi ra mạng công cộng** nếu không có cơ chế bảo vệ phù hợp.

### 8.1. Truyền địa chỉ vào consumer

Giả sử consumer có property:

```yaml
clients:
  orders:
    base-url: http://order-stub:8080
```

Trong Docker Compose, `order-stub` là hostname nội bộ của service. Trong test chạy trên host với port mapping `127.0.0.1:8090:8080`, base URL phải là `http://127.0.0.1:8090`.

**Đừng hardcode URL vào Java code production**. Sử dụng configuration/property injection và thay base URL **trước khi HTTP client bean được tạo**. Nếu dùng `WebClient` hoặc `RestClient` được tạo lúc Spring context khởi tạo, việc thay một biến trong `@BeforeEach` có thể quá muộn.

### 8.2. Cổng ngẫu nhiên và cổng cố định

- **Cổng cố định** thuận tiện cho một môi trường test riêng có địa chỉ rõ ràng, nhưng dễ xung đột khi CI chạy song song.
- **Cổng động** hữu ích với test harness tạo stub theo job, miễn consumer nhận được địa chỉ thực tế sau khi server bind thành công.
- `server.port` của Stub Runner Boot (nếu có) và cổng WireMock của từng stub có thể là **hai loại cổng khác nhau**.
- Không suy ra port từ JAR classifier/version; port là thông tin **runtime**, không được đóng trong artifact.

Nếu thử cấp cổng bằng cách “tìm số trống → đóng socket → mở stub trên số đó”, có race condition. Hãy để server bind cổng `0` khi runtime hỗ trợ, rồi đọc **cổng thực tế sau bind**, hoặc để orchestration cấp endpoint/port có kiểm soát.

## 9. Readiness, liveness và kiểm thử thực sự khác nhau

Một environment có thể đi qua ba mức xác nhận:

| Mức | Câu hỏi | Bằng chứng minh họa |
|---|---|---|
| **Liveness** | Process/container còn sống không? | PID/container đang chạy |
| **Readiness** | Stub đã sẵn sàng nhận request có ý nghĩa không? | Endpoint mẫu trả status/body đã cam kết |
| **Consumer verification** | HTTP client và nghiệp vụ consumer có tương thích không? | Consumer test report có assertions đạt |

Kiểm tra nhanh với một WireMock standalone server:

```bash
curl --fail --silent --show-error \
  -H "Accept: application/json" \
  http://127.0.0.1:8090/api/orders/42
```

`curl --fail` chỉ xác nhận status HTTP thuộc lớp không lỗi theo quy tắc của curl; nó **không tự chứng minh JSON body có `state=PAID`**. Một readiness check chặt hơn nên parse/so sánh trường quan trọng hoặc dùng kịch bản probe đã được xác minh.

### 9.1. Không dùng `sleep 10` làm readiness

```text
Sai:
  start stub
  sleep 10
  chạy consumer test

Đúng:
  start stub
  poll endpoint có giới hạn thời gian
  xác nhận status + mẫu response mong đợi
  chạy consumer test
  luôn cleanup ở cuối job
```

Một delay cố định có thể thừa trên máy nhanh và vẫn thiếu trên CI chậm. Poll có giới hạn giúp phân biệt server **chưa ready** với server **start thất bại**.

### 9.2. Thứ tự start/stop đáng tin

1. Cấp workspace/network và chọn artifact hoặc file root.
2. Start stub process/container.
3. Đợi readiness tới deadline có giới hạn; nếu không ready thì fail job.
4. Công bố **URL thực tế** cho consumer.
5. Chạy consumer tests; lưu logs/request journal khi thất bại.
6. Stop server/container và thu hồi tài nguyên trong bước cleanup **dù test pass hay fail**.

Nếu nhiều test cùng sử dụng stub, không được tắt instance sau test A trong khi test B vẫn đang chạy.

## 10. Tính trạng thái: request journal, mappings và scenarios

WireMock có nhiều loại state **khác nhau**:

- **Stub mappings:** danh sách quy tắc request/response được nạp từ file hoặc tạo động.
- **Request journal:** lịch sử request đã nhận, hữu ích để xác minh consumer gọi endpoint bao nhiêu lần.
- **Scenario state:** trạng thái của những WireMock scenarios dùng mô phỏng chuỗi hành vi.
- **Response files/templates:** dữ liệu hoặc cấu hình template dùng tạo response.

Reset sai loại có thể phá bộ test:

| Muốn làm sạch | Cách tiếp cận | Nguy cơ |
|---|---|---|
| Chỉ xóa lịch sử request | Reset request journal riêng | Không sửa mappings cần dùng |
| Đưa scenario về trạng thái ban đầu | Reset scenarios theo API/thư viện đang dùng | Có thể ảnh hưởng test khác chung server |
| Thay đổi mappings động | Xóa mapping test tạo hoặc tạo instance mới | Xóa hết mappings có thể làm stub trả unmatched 404 |
| Dọn toàn bộ state | Restart instance riêng theo test/job | Tốn thời gian, nhưng dễ cô lập |

**Không gọi reset-all tràn lan** nếu mapping từ artifact đã được nạp và bạn không có cơ chế nạp lại nó. Một test xóa toàn bộ mappings có thể khiến test khác gọi cùng server nhận `404` dù artifact đúng.

### 10.1. Stub tĩnh không phải database giả lập có state machine

Nếu consumer gọi:

```text
POST /api/orders/42/pay  → trả 200
GET  /api/orders/42      → mong state mới PAID
```

hai mapping tĩnh **không tự lưu thay đổi trạng thái**. Để mô phỏng chuỗi có trạng thái, có thể dùng **WireMock scenarios** hoặc dựng một integration test với producer thật. Nếu cần chính sách ordering, idempotency và side effect bền vững, đừng suy ra mọi thứ đã được xác minh từ một stub scenario đơn giản.

### 10.2. Test song song với scenario state

Hai test cùng dùng `scenarioName=payment-flow` trên một server có thể giẫm lên trạng thái của nhau. Ngay cả khi reset scenarios ở `@AfterEach`, chúng vẫn có thể xung đột **trong lúc đang chạy**.

Giải pháp ưu tiên là **mỗi suite/job có stub server riêng**, hoặc namespace scenario/test fixture riêng nếu adapter cho phép. Nếu buộc dùng chung server, cần đồng bộ test và phân định quyền reset, không chỉ tăng delay.

## 11. Bảo mật và cô lập mạng cho standalone stubs

Một stub server thường **không có cùng lớp bảo mật** với producer production. Nếu mở ra mạng ngoài, kẻ khác có thể đọc fixture, gọi endpoint giả hoặc truy cập API quản trị để sửa mappings/response.

Các biện pháp nên áp dụng:

1. **Chỉ bind loopback** khi consumer chạy cùng máy; với container, sử dụng network nội bộ và giới hạn published ports.
2. Không publish WireMock Admin API ra Internet công cộng hoặc mạng không tin cậy; dùng network ACL, reverse proxy hoặc cơ chế bảo vệ thích hợp.
3. **Không chứa dữ liệu cá nhân thật**, API token, mật khẩu hoặc thông tin nội bộ nhạy cảm trong stub responses.
4. Container chạy với quyền tối thiểu và volume fixture read-only khi có thể.
5. Kho artifact yêu cầu đúng quyền đọc, không viết credentials vào URL hay log.
6. Làm sạch container, ports và file tạm sau CI để không có môi trường test “mồ côi”.
7. Nếu stub cần mô phỏng lỗi authentication, chỉ dùng **token giả**, không dùng production secrets.

Stub là **mô phỏng theo hợp đồng**, không phải phương án cung cấp API công khai thay producer. Các đáp ứng giả có thể không có rate limit, authorization hoặc validation thật nếu những điều đó không được mô tả trong mappings.

## 12. Giữ tương thích giữa stub, producer và consumer

```mermaid
sequenceDiagram
    participant P as Producer CI
    participant R as Artifact repository
    participant S as Standalone stub runtime
    participant C as Consumer CI
    P->>P: Sinh và chạy producer contract tests
    alt Tests thực sự đạt
        P->>R: Publish versioned -stubs.jar
        S->>R: Resolve đúng group/artifact/version/classifier
        S->>S: Nạp mappings và kiểm tra readiness
        C->>S: HTTP qua client thật
        S-->>C: Response mẫu theo contract
        C->>C: Assert DTO, lỗi và workflow
    else Producer tests fail hoặc bị skip
        P-->>P: Không publish stub mới
    end
```

### 12.1. Vì sao stub trả đúng không chứng minh producer thật đúng?

Stub chỉ trả dữ liệu được mô tả trong artifact. Nếu producer code đã đổi `{"state":"PAID"}` thành `{"state":"PENDING"}` nhưng generated producer tests không chạy, stub cũ vẫn trả `PAID` và consumer test có thể pass.

Vì vậy, cần kiểm tra **cả hai bằng chứng**:

- **Producer verification:** generated contract tests đã được sinh, biên dịch, phát hiện, thực thi và đạt các assertions tương ứng.
- **Consumer verification:** consumer tests gọi đúng standalone stub version, kiểm tra deserialize và hành vi nghiệp vụ có ý nghĩa.

Với consumer cần một phiên bản producer đang deploy, cần đối chiếu **stub version ↔ producer build ↔ deployment manifest**. Chỉ cùng tên `order-service` không bảo đảm đúng bản hợp đồng.

### 12.2. Canary để phát hiện thay đổi mới

Có thể có hai job:

- **Release gate:** dùng version `1.4.0` cố định, archive checksum và reports.
- **Compatibility canary:** thử `+`/snapshot hoặc phiên bản chuẩn bị phát hành, ghi đúng resolved artifact.

Không trộn job canary “lấy bản mới nhất” vào release gate cố định mà không kiểm soát; nếu dependency thay đổi giữa hai lần chạy, test không còn tái lập được.

## 13. Tạo script CI quản lý vòng đời WireMock độc lập

Với WireMock standalone và file root đã có, một script **minh họa cho Linux/bash** có thể quản lý start/ready/test/stop:

```bash
#!/usr/bin/env bash
set -euo pipefail

STUB_JAR="./runtime/wiremock-standalone.jar"
STUB_ROOT="./wiremock-root"
STUB_PORT="8090"
STUB_URL="http://127.0.0.1:${STUB_PORT}"
STUB_PID=""

cleanup() {
  if [ -n "${STUB_PID}" ]; then
    kill "${STUB_PID}" 2>/dev/null || true
    wait "${STUB_PID}" 2>/dev/null || true
  fi
}
trap cleanup EXIT

# Cần bảo đảm JAR và file root đã được tạo từ nguồn kiểm soát.
java -jar "${STUB_JAR}" --port "${STUB_PORT}" \
  --root-dir "${STUB_ROOT}" > wiremock.log 2>&1 &
STUB_PID=$!

READY=0
for attempt in $(seq 1 30); do
  if curl --fail --silent --show-error \
       -H "Accept: application/json" \
       "${STUB_URL}/api/orders/42" > /dev/null 2>&1; then
    READY=1
    break
  fi
  if ! kill -0 "${STUB_PID}" 2>/dev/null; then
    echo "WireMock process stopped unexpectedly" >&2
    break
  fi
  sleep 1
done

if [ "${READY}" -ne 1 ]; then
  echo "Stub not ready; inspect wiremock.log" >&2
  exit 1
fi

# Chuyển STUB_URL vào bước chạy consumer tests theo build tool dự án.
echo "Stub ready at ${STUB_URL}"
# Ví dụ: STUB_BASE_URL="${STUB_URL}" ./gradlew test
```

**Cảnh báo vận hành:**

- Script là ví dụ để hiểu **vòng đời**, chưa chạy thực tế và chưa chứa lệnh consumer test thật; phải thay các đường dẫn, công cụ và pipeline phù hợp.
- Cổng `8090` phải được cấp độc quyền cho job; nếu CI chạy song song cùng namespace mạng, dùng cổng động hoặc container/service networking phù hợp.
- Probe `curl --fail` chỉ kiểm tra status 2xx/3xx của endpoint mẫu. Một job nghiêm ngặt nên **kiểm tra body/schema** hoặc dùng test thăm dò mạnh hơn.
- `trap cleanup EXIT` xử lý phần lớn đường thoát của shell, nhưng **không bảo đảm chạy khi tiến trình bị kill không thể bắt**; dùng cleanup cấp CI/container orchestration làm lớp bảo vệ bổ sung.
- Khi pipeline test fail, nên lưu `wiremock.log` và reports trước khi môi trường bị thu hồi.
- `sleep 1` trong vòng **poll readiness có deadline** là hợp lý; khác với `sleep 10` cố định rồi giả định server chắc chắn ready.

Nếu test chạy trên Windows, cần dùng cơ chế quản lý process/cleanup tương ứng; không sao chép nguyên script Bash vào PowerShell.

## 14. Quan sát và chẩn đoán sự cố

| Hiện tượng | Nguyên nhân khả dĩ | Điều cần xác minh |
|---|---|---|
| `Address already in use` | Cổng stub bị chiếm hoặc server cũ chưa dừng | PID/container đang bind, phân bổ port |
| Process đang chạy nhưng consumer nhận `404` | Mappings không được load hoặc request không khớp | File root, method/path/query/header |
| Stub Runner không tải được JAR | Sai coordinates/classifier hoặc quyền repo | Group/artifact/version/`stubs`, URL, auth |
| LOCAL chạy, REMOTE thất bại | Artifact chưa publish hoặc repository config sai | Repo thực sự có `-stubs.jar` không |
| Trả response thuộc version cũ | Cache, `+`, snapshot, sai môi trường | Resolved version/checksum của artifact |
| Body file không tìm thấy | `bodyFileName` sai đường dẫn hoặc JAR thiếu `__files` | Mapping và file relative path |
| Consumer gọi nhầm port | Lẫn stub port với launcher port/app port | URL runtime mà consumer thực dùng |
| Container consumer không gọi được `localhost` | Hai container có network namespace khác nhau | Hostname service, container port |
| Trả `404` nhưng test vẫn xanh | Unmatched 404 bị hiểu là business error | Assert error code/schema |
| Test riêng pass, suite fail | Scenario/request journal chưa reset | Isolation, reset policy |
| Cùng artifact nhưng test khác kết quả | Config/mapping overrides hoặc stateful scenario | Checksums, startup arguments, state |
| Stub khởi động nhưng không phục vụ mapping | Runtime chỉ liveness, chưa readiness | Probe endpoint cụ thể |
| Producer deploy khác stub | Version không gắn với deployment | Release manifest, producer verification |
| CI job kết thúc nhưng port còn bận | Process/container chưa bị dọn | Trap/cleanup job, resource owner |

### 14.1. Thứ tự điều tra có hiệu quả

1. **Runtime nào?** WireMock standalone hay Stub Runner Boot?
2. **Đúng artifact nào?** Tên/version/classifier/checksum, hay file root nào?
3. **Cấu hình startup nào?** Repo mode, port, host, mappings, volume.
4. **Runtime đã ready chưa?** Endpoint probe có phản hồi mong đợi không?
5. **Consumer nhìn thấy URL nào?** Đúng network namespace, scheme, host và port?
6. **Request có khớp mapping không?** So method/path/query/header/body.
7. **Có state rò rỉ không?** Scenario, journal hoặc mapping override.
8. **Producer generated tests đã chạy chưa?** Stub test pass không thay thế được chúng.

Không sửa contract hoặc nới rộng matcher ngay khi thấy `404`; có thể lỗi nằm ở **chọn sai artifact hoặc gọi nhầm server**.

## 15. Bài thực hành: triển khai môi trường stub độc lập cho checkout

**Bối cảnh:** `checkout-service` đang gọi `order-service` thật trong quá trình phát triển, khiến test thất bại khi producer tạm bảo trì. Nhóm muốn chạy một stub độc lập, ổn định trên CI và có thể chuyển sang artifact mới trong một job kiểm tra tương thích.

### 15.1. Nhiệm vụ

1. Tạo contract `GET /api/orders/42` trả `200` với `id=42`, `state=PAID` và `currency=VND`; thêm contract `GET /api/orders/9999` trả `404 + ORDER_NOT_FOUND`.
2. Trên producer, chạy generated contract tests và xác minh **tests thật sự đã thực thi và đạt**, không chỉ sinh mappings.
3. Đóng gói/publish `com.example:order-service:1.4.0:stubs`, lưu checksum/commit hoặc metadata tương đương.
4. **Phương án A:** chuẩn bị `mappings` và `__files`, chạy WireMock standalone ở một test environment riêng; đợi readiness.
5. **Phương án B:** dùng Stub Runner Boot runtime có phiên bản phù hợp, cấu hình resolve `com.example:order-service:1.4.0:stubs` từ repository và chạy stub ở cổng được cấp.
6. Cấu hình `checkout-service` dùng **URL stub runtime**, không dùng production DNS.
7. Kiểm tra consumer HTTP client thật deserialize được order `PAID` và xử lý đúng body lỗi `ORDER_NOT_FOUND`.
8. Ghi lại artifact version, cổng, URL, log và test report; chạy lại cùng version để kiểm tra tính tái lập.
9. Nếu test cần scenario có state, reset scenario/request history giữa test hoặc cấp server riêng cho suite.
10. Kết thúc job, stop stub và xác nhận tài nguyên được thu hồi. Thử cố ý chặn cổng hoặc xóa body file trong môi trường test để xem readiness/CI báo lỗi rõ ràng.
11. Tạo job canary dùng phiên bản chuẩn bị phát hành `1.5.0`, chạy lại consumer tests; so sánh thay đổi schema/status thay vì chỉ nhìn stub startup thành công.

### 15.2. Câu hỏi tự kiểm tra

| Câu hỏi | Trả lời |
|---|---|
| `-stubs.jar` có mặc định là executable HTTP server không? | **Không**, đó thường là artifact chứa tài nguyên stub |
| WireMock standalone có tự tải artifact Maven theo coordinates không? | **Không** nếu không có bước resolver/cấu hình bổ sung |
| Stub Runner Boot có phải chính producer application không? | **Không**, nó khởi chạy stub theo tài nguyên đã resolve |
| `server.port` của launcher luôn là cổng WireMock của `order-service` không? | **Không**, phải phân biệt hai loại cổng |
| Có thể chỉ kiểm tra process sống để kết luận stub ready không? | **Không**, nên probe endpoint mẫu và mapping |
| `+` có bảo đảm mọi lần chạy dùng cùng artifact không? | **Không**, cần log resolved version hoặc pin |
| Một mapping có `bodyFileName` nhưng thiếu `__files` có chạy đúng không? | **Không**, phải cung cấp tệp body được tham chiếu |
| Reset-all trên shared WireMock server có an toàn không? | **Không mặc nhiên**, có thể xóa mappings của test khác |
| Stub pass có chứng minh producer thật đang chạy đúng không? | **Không**, cần generated producer tests |
| Có nên chạy standalone stub public trên Internet để “tiện test” không? | **Không**, cần kiểm soát mạng, quyền quản trị và dữ liệu |

## 16. Checklist vận hành và phát hành standalone stubs

- [ ] Đã chọn đúng **mô hình WireMock standalone hoặc Stub Runner Boot**, hiểu cách lấy tài nguyên stub của mỗi mô hình.
- [ ] Contract nguồn Groovy/YAML là nguồn sự thật; generated producer tests đã được thực thi và đạt.
- [ ] Artifact dùng đúng group/artifact/version/classifier `stubs`, có provenance/checksum khi cần.
- [ ] Phiên bản cho CI chính được pin, release bất biến; `+`/snapshot được quản lý ở job riêng nếu có.
- [ ] File root/mappings/body files hợp lệ, `bodyFileName` không trỏ nhầm đường dẫn.
- [ ] Cấu hình repository mode, URL và quyền truy cập phù hợp; không ghi secrets vào source hoặc logs.
- [ ] Có **resource owner** chịu trách nhiệm start, wait-ready, cấp URL, reset và stop.
- [ ] Phân biệt cổng runtime của stub với cổng launcher/consumer/producer thật; tránh xung đột.
- [ ] Consumer nhận đúng base URL theo network namespace và trước khi HTTP client được khởi tạo.
- [ ] Readiness probe xác minh một endpoint có ý nghĩa, không chỉ đợi cố định hoặc nhìn PID.
- [ ] Nếu dùng scenarios, request journal và dynamic mappings được reset đúng phạm vi.
- [ ] Test song song được cô lập bằng process/container/namespace khi có thể.
- [ ] Stub server và Admin API không phơi ra mạng không tin cậy; fixture không chứa dữ liệu nhạy cảm.
- [ ] Consumer tests gọi client thật và assert response body/error schema, không chỉ khởi động được stub.
- [ ] CI lưu resolved version, artifact provenance, logs và test reports để tái hiện lỗi.
- [ ] Cleanup có cả lớp bảo vệ ở test/job/container level, không để lại process hoặc port mồ côi.

**Ghi nhớ:** Quản lý **stub độc lập** không chỉ là chạy một JAR hay container. Cần **chọn đúng phiên bản hợp đồng, nạp đúng mappings, khởi động và kiểm tra readiness, truyền đúng địa chỉ cho consumer, cô lập state và dọn tài nguyên sau test**. Khi quy trình đó được kết hợp với producer contract verification và consumer tests có ý nghĩa, Spring Cloud Contract mới giúp phát hiện thay đổi API không tương thích theo cách **có thể lặp lại, truy vết và vận hành an toàn**.
