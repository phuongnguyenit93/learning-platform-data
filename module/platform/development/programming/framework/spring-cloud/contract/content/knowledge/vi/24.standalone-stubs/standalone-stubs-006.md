# Dùng stub cho phát triển cục bộ hoặc môi trường tạm thời

## 1. Vì sao cần một stub chạy độc lập?

Trong hệ thống microservices, một nhóm thường muốn phát triển hoặc chạy thử **consumer** trước khi **producer** triển khai xong, hoặc khi producer đang phụ thuộc vào database, broker và dịch vụ ngoài chưa có trong môi trường test. Với **Spring Cloud Contract**, hai phía thống nhất hành vi qua **Groovy/YAML DSL**: producer sinh và chạy kiểm thử xác minh hợp đồng, sau đó đóng gói các stub. Consumer có thể dùng các stub này để gọi HTTP hoặc nhận thông điệp trong môi trường thử nghiệm.

Ví dụ **Checkout Service** cần gọi **Inventory Service** để kiểm tra tồn kho:

~~~http
GET /api/inventory/SKU-100 HTTP/1.1
Accept: application/json
~~~

Phản hồi mà Checkout mong đợi:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "sku": "SKU-100",
  "available": true,
  "quantity": 8
}
~~~

Khi lập trình tại máy cá nhân, người viết Checkout không nhất thiết phải khởi động Inventory Service thật. Thay vào đó, có thể chạy một **stub HTTP server riêng biệt** trên `localhost:10080`, sau đó cho InventoryClient của Checkout gọi vào đó. Một **môi trường tạm thời (ephemeral environment)** cho pull request cũng có thể sử dụng cách tiếp cận tương tự: chỉ deploy Checkout cùng các stub cần thiết, rồi chạy smoke/integration tests.

Bài học này thuộc chương **Stub độc lập** của module `SPRING_CLOUD_CONTRACT`. Trọng tâm là **dùng stub trong phát triển cục bộ hoặc môi trường tạm thời**: cách chuẩn bị dữ liệu, khởi chạy Stub Runner Boot hoặc WireMock từ mapping, nối consumer với stub, quản lý phiên bản, cô lập môi trường và thu hồi tài nguyên.

### Kết quả học tập

Sau bài này, bạn có thể:

1. Phân biệt **embedded Stub Runner** chạy trong JUnit với **Stub Runner Boot** chạy như một ứng dụng độc lập.
2. Chuẩn bị stub JAR từ producer contract đã được xác minh.
3. Chọn `LOCAL` hoặc `REMOTE` để chạy stub độc lập, biết khi nào dùng nguồn classpath.
4. Phân biệt **cổng quản lý Stub Runner Boot** với **cổng WireMock stub**.
5. Sử dụng Docker để cấp một stub server riêng cho máy cá nhân hoặc môi trường pull request.
6. Định tuyến HTTP client của consumer tới đúng địa chỉ từ máy host, container hoặc network nội bộ.
7. Kiểm tra readiness, mappings và các nhánh success/error mà consumer thực sự dùng.
8. Thiết kế lifecycle tạo–sử dụng–dọn dẹp stub có kiểm soát, không phơi bày server ra Internet.
9. Hiểu giới hạn: stub không thay thế producer verification, database integration, broker hoặc end-to-end tests.

> **Nguyên tắc:** Dùng stub để **cô lập dependency và kiểm tra giao diện**, không dùng stub làm bằng chứng rằng producer thật hoặc toàn bộ hệ thống phân tán đang chạy đúng.

## 2. Stub độc lập khác gì Stub Runner trong JUnit?

Các thành phần dễ nhầm:

| Thành phần | Chạy ở đâu? | Vai trò |
| --- | --- | --- |
| **Contract DSL** | Trong nguồn producer hoặc repository hợp đồng | Định nghĩa request/response hay message được cam kết |
| **Generated producer tests** | Trong build/test context của producer | Kiểm tra implementation thật có đáp ứng contract không |
| **Stub JAR** | Maven local repo hoặc artifact repository | Chứa các mappings/contracts đã đóng gói |
| **Stub Runner nhúng trong JUnit** | Bên trong process chạy consumer test | Tải stubs, khởi động WireMock và cung cấp port cho test |
| **Stub Runner Boot (standalone)** | Một process/container riêng | Tải stubs và chạy những WireMock servers có thể được consumer khác gọi |
| **WireMock standalone trực tiếp** | Một process/container riêng | Dùng HTTP mappings có sẵn, không tự có toàn bộ cơ chế Maven stub resolution của Stub Runner |

**Embedded Stub Runner** thường dùng `@AutoConfigureStubRunner` hoặc `StubRunnerExtension` trong test. Test framework quản lý thời gian sống của stub và có thể lấy cổng động bằng `@StubRunnerPort`.

**Stub Runner Boot** thích hợp khi cần một server tồn tại **ngoài process JUnit**, để cả IDE, ứng dụng chạy thủ công, trình duyệt/curl hoặc một nhóm ứng dụng ở môi trường tạm thời đều có thể gọi chung.

**WireMock standalone** phù hợp nếu bạn đã có các mappings JSON và chỉ muốn chạy trực tiếp chúng. Nhưng nếu muốn lấy stubs theo Maven coordinates từ Nexus/Artifactory hoặc `~/.m2`, Stub Runner Boot cung cấp workflow chuyên biệt cho Spring Cloud Contract.

### 2.1. “Standalone” không có nghĩa “producer thật”

Stub Runner Boot có thể khởi động WireMock mà không nạp controller, service, repository hay database của Inventory Service. Nó trả response theo mapping đã được sinh từ contract. Một request không có mapping phù hợp có thể nhận `404` mặc dù producer thật trả response khác.

Để phát hiện khác biệt giữa mapping và implementation, **producer phải tiếp tục chạy generated contract tests** trong build của mình.

## 3. Luồng từ hợp đồng đến môi trường thử nghiệm

~~~mermaid
flowchart TD
    A["Producer: Groovy/YAML contract"] --> B["Sinh producer tests"]
    B --> C{"Producer verification đạt?"}
    C -- "Không" --> X["Không phát hành stub"]
    C -- "Có" --> D["Đóng gói -stubs.jar"]
    D --> E["Maven local hoặc repository chung"]
    E --> F["Stub Runner Boot: LOCAL / REMOTE"]
    F --> G["WireMock: mỗi producer một HTTP port"]
    G --> H["Checkout trỏ InventoryClient vào stub"]
    H --> I["Manual test / smoke test / integration test"]
    I --> J["Dọn dẹp sau khi dùng"]
~~~

Hai nhánh kiểm thử vẫn độc lập nhưng bổ trợ:

- **Producer verification:** Contract Verifier sinh test phía producer rồi kiểm tra response từ code producer thật/test context của producer.
- **Consumer verification:** Consumer gửi request thật từ client của mình tới stub và xác minh kết quả nghiệp vụ khi nhận response mẫu.

**Stub server chạy được** không đồng nghĩa hai nhánh trên đã chạy. Vì vậy khi tạo môi trường tạm thời, nên ghi rõ stub đang lấy từ **artifact phiên bản nào**, và artifact đó đã vượt qua các kiểm chứng nào trong pipeline producer.

## 4. Ví dụ xuyên suốt: một API Inventory có hai kịch bản

Để sử dụng stub có ý nghĩa, trước hết cần một contract nguồn đại diện cho điều Checkout thực sự cần.

### 4.1. Contract Groovy cho SKU còn hàng

Ví dụ tệp `src/test/resources/contracts/inventory/get_available_inventory.groovy`:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name('get_available_inventory')

    request {
        method GET()
        urlPath('/api/inventory/SKU-100')
        headers {
            accept(applicationJson())
        }
    }

    response {
        status OK()
        headers {
            contentType(applicationJson())
        }
        body(
            sku: 'SKU-100',
            available: true,
            quantity: 8
        )
    }
}
~~~

Tương tác này có thể tạo một WireMock mapping khớp `GET /api/inventory/SKU-100` và trả JSON tương ứng.

### 4.2. Contract Groovy cho SKU không tồn tại

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name('get_inventory_not_found')

    request {
        method GET()
        urlPath('/api/inventory/SKU-404')
        headers {
            accept(applicationJson())
        }
    }

    response {
        status NOT_FOUND()
        headers {
            contentType(applicationJson())
        }
        body(
            code: 'INVENTORY_NOT_FOUND',
            message: 'SKU not found'
        )
    }
}
~~~

Checkout có thể dùng response `404` kèm `code` để hiển thị lỗi nghiệp vụ. Nếu chỉ thấy HTTP `404` vì WireMock không khớp request, đó **không phải** bằng chứng rằng producer đã công bố lỗi `INVENTORY_NOT_FOUND`.

### 4.3. YAML DSL có ý nghĩa tương đương

~~~yaml
name: get_available_inventory
request:
  method: GET
  urlPath: /api/inventory/SKU-100
  headers:
    Accept: application/json
response:
  status: 200
  headers:
    Content-Type: application/json
  body:
    sku: SKU-100
    available: true
    quantity: 8
~~~

Ví dụ Groovy và YAML chỉ nhằm học cách đọc contract. Trong dự án thật, không để hai bản **trùng tương tác cùng được kích hoạt** nếu không có ý định rõ ràng. Tập trung quản lý **một nguồn hợp đồng chuẩn**.

### 4.4. Stub phản ánh những gì?

Với contract trên, stub thường bảo vệ **request matching** và **response sample**:

- Method `GET`.
- Path `/api/inventory/SKU-100`.
- Header `Accept` nếu được contract ràng buộc.
- Status `200`, media type JSON, body có `available`/`quantity`.
- Case `SKU-404` với `404` và error body.

Stub không tự tính tồn kho từ database và không tự nhận mọi SKU ngoài các matchers được khai báo. Nếu consumer cần các giá trị động hoặc nhiều trường hợp biên, hãy thiết kế contract/matcher/stub scenario phù hợp thay vì giả định nó xử lý nghiệp vụ như Inventory Service thật.

## 5. Chuẩn bị stub artifact từ producer

Với Spring Cloud Contract, build producer có thể tạo một artifact kiểu:

~~~text
com.example:inventory-producer:1.2.3:stubs
~~~

Tên file Maven classifier thường là:

~~~text
inventory-producer-1.2.3-stubs.jar
~~~

Thông thường JAR có các mappings/contracts nằm trong layout được plugin và Stub Runner hỗ trợ, ví dụ các vị trí dưới `META-INF/.../mappings`. File chính `inventory-producer-1.2.3.jar` **không phải** stub classifier JAR.

### 5.1. Cần xác nhận trước khi dùng

1. Producer có nguồn Groovy/YAML contract cho tương tác cần thử.
2. Plugin và generator thực sự tạo **generated producer tests**.
3. Những test này **đã được thực thi**; build không xanh vì skip hoặc 0 tests.
4. Mappings được tạo và được đưa vào `-stubs.jar` theo đúng tọa độ Maven.
5. Artifact version và classifier đã biết, ví dụ `1.2.3:stubs`.
6. Artifact đã được **install local** hoặc **publish** theo chế độ sẽ dùng.

Ví dụ lệnh Maven **chỉ có hiệu lực nếu producer đã cấu hình plugin và attach stub artifact**:

~~~bash
# Kiểm tra producer; không coi BUILD SUCCESS với 0 tests là đủ.
./mvnw -B clean verify

# Nếu dự án cấu hình install stub artifact:
./mvnw -B install
~~~

Một dự án Java thông thường không tự tạo `-stubs.jar` chỉ vì chạy `mvn install`. Nếu chưa thấy artifact, cần kiểm tra cấu hình producer plugin chứ không đổi Stub Runner để che lỗi.

### 5.2. Không đưa artifact thiếu provenance vào môi trường tạm thời

Nếu ai đó tự viết file WireMock JSON để thử UI, nó vẫn hữu ích cho phát triển, nhưng nên gọi rõ là **stub thủ công**. Đừng gắn nhãn “đã được producer verification xác nhận” nếu file chưa xuất phát từ contract hoặc chưa chạy đúng bước producer test. Việc phân biệt giúp tránh false confidence khi demo hoặc review pull request.

## 6. Chọn nguồn stubs: CLASSPATH, LOCAL và REMOTE

Stub Runner dùng `StubRunnerProperties.StubsMode` để chọn cách lấy stub:

| Mode | Nguồn | Thích hợp |
| --- | --- | --- |
| `CLASSPATH` | Stub JAR/mappings đã nằm trên classpath | Test nhúng, test dependency đã được resolve |
| `LOCAL` | Maven local repository như `~/.m2/repository` | Developer đã build/install producer trên cùng máy |
| `REMOTE` | Repository bên ngoài như Nexus/Artifactory hoặc supported location | CI, nhiều nhóm chia sẻ artifact, môi trường tạm thời |
 
**CLASSPATH là mặc định theo tài liệu**, nhưng với một Stub Runner Boot container chạy độc lập, stub JAR của dự án **không tự nằm trên classpath của image**. Vì vậy các workflow standalone phổ biến thường chọn rõ `LOCAL` hoặc `REMOTE`.

ID của stub thường dùng quy ước:

~~~text
groupId:artifactId:version:classifier:port
com.example:inventory-producer:1.2.3:stubs:10080
~~~

- `groupId` và `artifactId` xác định producer artifact.
- `version` pin phiên bản giao diện.
- `classifier` thường là `stubs`.
- `port` là cổng **WireMock** được khởi động cho producer đó, không phải cổng của Stub Runner Boot.

Version, classifier và port có thể được bỏ qua theo quy tắc mặc định; bỏ version thường khiến resolver dùng `+` để tìm phiên bản mới nhất. **Trong CI và preview environment cần tái lập, nên pin version cụ thể** thay vì dùng `+`.

### 6.1. Đừng nhầm REMOTE với URL của producer

Nếu `repositoryRoot` là `https://repo.example.test/repository/maven-releases/`, đây là **kho chứa artifact**. Nó không phải URL Inventory Service thật và cũng không phải địa chỉ để Checkout gửi request tồn kho.

Checkout cần trỏ tới **WireMock HTTP port** mà Stub Runner Boot đã mở.

### 6.2. Khi nào dùng stubs://file://?

Spring Cloud Contract có thể dùng `stubs://file://...` để tải stub definitions từ một thư mục thông qua downloader được hỗ trợ, nhưng chế độ phù hợp vẫn là **REMOTE**, không phải Maven `LOCAL`. Cần tuân thủ layout và URI syntax được phiên bản plugin hỗ trợ; không mặc định bất kỳ thư mục chứa JSON nào cũng được resolver nhận ra.

## 7. Lựa chọn chạy độc lập: Docker, ứng dụng Boot hay WireMock

Có ba lựa chọn thường gặp:

| Cách chạy | Ưu điểm | Giới hạn |
| --- | --- | --- |
| **Stub Runner Boot Docker image** | Cô lập runtime, dễ tạo và xóa, phù hợp local/preview | Phải cấp artifact access, quản lý ports và container networking |
| **Stub Runner Boot tự build/chạy** | Tùy biến Spring configuration và service discovery | Cần ứng dụng được đóng gói tương thích; phụ thuộc phiên bản |
| **WireMock standalone với mappings trực tiếp** | Đơn giản khi đã có JSON mappings | Tự quản lý nguồn mapping, phiên bản và cơ chế copy/sync |

**Lưu ý phiên bản quan trọng:** Tài liệu hiện tại của Spring Cloud Contract cho biết **executable Stub Runner Boot JAR không được phát hành từ phiên bản 4.1.6** do giới hạn của công cụ phát hành artifact; tài liệu khuyến nghị sử dụng Docker image hoặc tự build ứng dụng từ nguồn. Do đó **không nên viết hướng dẫn hiện đại dựa trên giả định luôn download được fat JAR mới từ Maven Central**.

Các lệnh `java -jar stub-runner.jar ...` trong tài liệu cũ chỉ dùng khi bạn đã có **JAR khả dụng và tương thích**, hoặc đã tự build ứng dụng Boot. Spring Cloud CLI `spring cloud stubrunner` là một lựa chọn lịch sử, cũng cần xác nhận CLI/version trước khi sử dụng.

### 7.1. Vì sao Docker thường phù hợp cho môi trường tạm thời?

Một container có thể:

- Tải đúng phiên bản stubs được pin.
- Chạy một hoặc nhiều WireMock servers.
- Cung cấp HTTP ports cho Checkout hoặc công cụ test.
- Được tạo lại từ cấu hình khai báo trong pipeline.
- Được xóa khi pull request đóng hoặc job kết thúc.

**Không cần giữ stub server chạy vĩnh viễn.** Với môi trường preview, thời gian sống nên gắn với vòng đời PR, job CI hoặc phiên làm việc của developer.

## 8. Dùng Stub Runner Boot Docker với REMOTE stubs

Ví dụ môi trường minh họa:

| Giá trị | Ý nghĩa |
| --- | --- |
| `com.example:inventory-producer:1.2.3:stubs` | Artifact đã được producer xác minh và publish |
| `https://repo.example.test/repository/maven-releases/` | Repository lưu stub artifacts, URL mẫu |
| `10080` | WireMock HTTP port của Inventory stub |
| `8750` | Port quản lý Stub Runner Boot theo ví dụ tài liệu |
| `springcloud/spring-cloud-contract-stub-runner` | Tên image dùng trong một số ví dụ Docker chính thức; kiểm tra registry/tag hiện hành |

Ví dụ lệnh cho Bash/POSIX shell (thay `<compatible-tag>` và URL kho bằng giá trị thực tế; lệnh **minh họa**, không chạy trực tiếp trong bài):

~~~bash
docker run --rm --name inventory-stubs \
  -e SPRING_CLOUD_CONTRACT_STUBRUNNER_IDS="com.example:inventory-producer:1.2.3:stubs:10080" \
  -e SPRING_CLOUD_CONTRACT_STUBRUNNER_STUBS_MODE=REMOTE \
  -e SPRING_CLOUD_CONTRACT_STUBRUNNER_REPOSITORY_ROOT="https://repo.example.test/repository/maven-releases/" \
  -p 127.0.0.1:8750:8750 \
  -p 127.0.0.1:10080:10080 \
  springcloud/spring-cloud-contract-stub-runner:<compatible-tag>
~~~

**Giải thích:**

1. `SPRING_CLOUD_CONTRACT_STUBRUNNER_IDS` chọn artifact và cổng WireMock `10080`.
2. `...STUBS_MODE=REMOTE` yêu cầu resolver lấy stub từ repository.
3. `...REPOSITORY_ROOT` là kho phân phối artifacts.
4. `-p 127.0.0.1:8750:8750` ánh xạ **cổng quản lý** vào loopback của máy host.
5. `-p 127.0.0.1:10080:10080` ánh xạ **cổng stub** vào loopback.
6. `--rm` tự xóa container sau khi dừng; `--name` giúp tìm container để xem log hoặc dừng.
7. `<compatible-tag>` phải là tag image thực sự tồn tại và tương thích với repository/plugin của dự án.

Tài liệu Spring Cloud Contract có cả cách ghi tên image `spring-cloud/spring-cloud-contract-stub-runner` và các ví dụ `springcloud/spring-cloud-contract-stub-runner`. **Kiểm tra tên repository, registry và tag đang được tổ chức dùng trước khi copy lệnh**, không lấy ví dụ làm cam kết artifact luôn khả dụng.

**Không đưa username/password của artifact repository vào shell history hoặc source code**. Khi cần xác thực, dùng secrets/credential injection theo hệ thống container hoặc CI. Lệnh trên giả sử repository thử nghiệm không yêu cầu xác thực.

### 8.1. Vì sao cần ánh xạ hai cổng?

Đây là nhầm lẫn rất phổ biến:

~~~text
localhost:8750         → Stub Runner Boot management REST API
localhost:10080        → Inventory WireMock HTTP API
~~~

Checkout gửi:

~~~http
GET http://localhost:10080/api/inventory/SKU-100
~~~

Chứ **không** gửi HTTP inventory tới `localhost:8750`. Cổng `8750` có các endpoint như `/stubs` và `/triggers` phục vụ quản lý/kiểm tra stub.

Nếu bạn chỉ publish cổng `8750` trong Docker nhưng không publish cổng `10080`, máy host có thể thấy danh sách stubs mà **không thể gọi WireMock** từ host. Với consumer chạy cùng Docker network, có thể không cần publish WireMock ra host, nhưng phải dùng DNS/container networking đúng.

### 8.2. Nếu runner ở LOCAL trong Docker?

`LOCAL` tìm trong **Maven local repository của container**, không tự thấy `~/.m2` trên máy host. Muốn dùng artifact local, phải mount repository của máy host vào đúng đường dẫn bên trong image và bảo đảm quyền đọc.

Ví dụ mang tính minh họa cho image dùng home `/home/scc`:

~~~bash
docker run --rm --name inventory-stubs-local \
  -v "$HOME/.m2:/home/scc/.m2:ro" \
  -e SPRING_CLOUD_CONTRACT_STUBRUNNER_IDS="com.example:inventory-producer:1.2.3:stubs:10080" \
  -e SPRING_CLOUD_CONTRACT_STUBRUNNER_STUBS_MODE=LOCAL \
  -p 127.0.0.1:8750:8750 \
  -p 127.0.0.1:10080:10080 \
  springcloud/spring-cloud-contract-stub-runner:<compatible-tag>
~~~

Tài liệu Docker có ví dụ mount `.m2` tới `/home/scc/.m2`. Nếu image/version dùng user hoặc Maven local path khác, **phải kiểm tra và điều chỉnh đường dẫn**, không mặc định mọi image đều giống nhau.

Gắn `:ro` giúp bảo vệ kho Maven local khỏi thay đổi ngoài ý muốn; nhưng nếu image cần ghi cache/resolution, có thể phải dùng một volume khác có quyền ghi và quản lý ownership thích hợp. Đừng gắn cả thư mục home hoặc token nhạy cảm vào container nếu không cần.

### 8.3. Không mặc định các lệnh đã được thực thi

Tất cả ví dụ trong bài là hướng dẫn. Chỉ khi **bạn chạy container và xác nhận image, artifact và cổng** mới có thể tuyên bố stub server đang hoạt động. Một câu lệnh cấu hình đúng về mặt ý tưởng chưa bảo đảm artifact trong URL mẫu tồn tại.

## 9. Kiểm tra Stub Runner Boot đã sẵn sàng chưa?

Khi container chạy, nên kiểm tra theo các bước độc lập:

~~~mermaid
flowchart TD
    A["Start Stub Runner Boot"] --> B{"Management API trả lời?"}
    B -- "Không" --> C["Kiểm tra startup logs, port 8750, image"]
    B -- "Có" --> D{"Danh sách /stubs có Inventory?"}
    D -- "Không" --> E["Kiểm tra coordinates/repository/classifier"]
    D -- "Có" --> F{"WireMock port 10080 gọi được?"}
    F -- "Không" --> G["Kiểm tra Docker port mapping/network"]
    F -- "Có" --> H{"Request khớp contract?"}
    H -- "Không" --> I["Kiểm tra method/path/header/mappings"]
    H -- "Có" --> J["Cho consumer test chạy"]
~~~

Thay vì `sleep 30` rồi cho là đã khởi động xong, hãy **chờ một điều kiện quan sát được với timeout hữu hạn**.

### 9.1. Kiểm tra management API

Stub Runner Boot có endpoint HTTP quản lý, theo tài liệu:

~~~bash
# Danh sách các stubs đang chạy.
curl --fail --silent --show-error http://localhost:8750/stubs
~~~

Ví dụ response có thể là một JSON object ánh xạ tọa độ stub sang port:

~~~json
{
  "com.example:inventory-producer:1.2.3:stubs": 10080
}
~~~

**Đây là JSON minh họa**, không phải response đã được nhận từ server thật. Nếu `/stubs` trả rỗng, cần kiểm tra artifact resolution và startup logs, không chỉ nhìn container có trạng thái running.

Để hỏi port theo ID (URL-encode các ký tự cần thiết nếu client/HTTP library yêu cầu):

~~~bash
curl --fail --silent --show-error \
  "http://localhost:8750/stubs/inventory-producer"
~~~

Endpoint `GET /stubs/{ivy}` có thể nhận Ivy notation hoặc chỉ artifactId theo tài liệu; trả về port của stub đã chạy. Nếu không tìm thấy, trả lỗi và cần điều tra ID.

### 9.2. Gọi trực tiếp WireMock

~~~bash
curl --fail --silent --show-error \
  -H "Accept: application/json" \
  "http://localhost:10080/api/inventory/SKU-100"
~~~

Response nên có `sku: SKU-100`, `available: true` và `quantity: 8` theo contract mẫu. `curl --fail` có thể trả exit status lỗi với HTTP `4xx`; khi kiểm tra **nhánh 404 có chủ đích**, dùng tùy chọn xem status/headers thay vì coi mọi 404 là lỗi hạ tầng.

### 9.3. Kiểm tra nhánh 404 có body đúng

~~~bash
curl --silent --show-error \
  -H "Accept: application/json" \
  -i "http://localhost:10080/api/inventory/SKU-404"
~~~

Cần kiểm tra **cả HTTP 404 và JSON `code: INVENTORY_NOT_FOUND`**. Một request không khớp WireMock mapping cũng có thể trả 404, nhưng không có nghĩa consumer đã gặp đúng lỗi nghiệp vụ.

### 9.4. Xem mappings đang hoạt động

WireMock admin API thường có:

~~~http
GET /__admin/mappings HTTP/1.1
Host: localhost:10080
~~~

Dùng endpoint này **trong môi trường test tin cậy** để kiểm tra có mapping tương ứng, không mở admin API ra Internet. Không sửa mappings qua admin API rồi mặc định thay đổi đó đã được lưu lại vào stub JAR; các chỉnh sửa runtime có thể mất khi khởi động lại container.

## 10. Kết nối Checkout với địa chỉ stub đúng mạng

Một trong các nguyên nhân phổ biến khiến stub “đã chạy” nhưng ứng dụng vẫn báo `Connection refused` là **nhầm ý nghĩa localhost**.

| Checkout chạy ở đâu? | Địa chỉ Inventory stub thường cần dùng |
| --- | --- |
| Checkout chạy trên host, stub Docker đã publish port ra loopback | `http://localhost:10080` |
| Checkout cùng Docker Compose network với container `stubrunner` | `http://stubrunner:10080` (theo DNS service name) |
| Checkout ở một container khác nhưng không cùng network | Phải kết nối qua network chung/gateway được cấu hình; `localhost` không trỏ sang stub container |
| Checkout ở Kubernetes pod khác trong namespace preview | Dùng Kubernetes Service DNS hoặc địa chỉ nội bộ của stub |
| Test chạy từ browser của người dùng | Phải cân nhắc origin, CORS, URL được trình duyệt truy cập; không đưa management API ra ngoài |

Nếu Checkout nằm trong container riêng, `localhost` của nó là **container Checkout**, không phải máy host và cũng không phải container Stub Runner. Vì vậy `INVENTORY_BASE_URL=http://localhost:10080` chỉ đúng khi client thực sự chạy trên host hoặc trong một network namespace phù hợp.

### 10.1. Nối base URL qua cấu hình, không sửa business code

Ví dụ Checkout nhận cấu hình:

~~~yaml
inventory:
  base-url: http://localhost:10080
~~~

Trong preview environment chạy qua service discovery hoặc container network, giá trị tương ứng có thể là:

~~~yaml
inventory:
  base-url: http://stubrunner:10080
~~~

Cách đặt key `inventory.base-url` là **quy ước do ứng dụng Checkout tự định nghĩa**, không phải property mặc định của Spring Cloud Contract. Checkout cần bind nó đúng vào WebClient/RestClient/Feign của mình.

**Đừng hard-code URL trong code nghiệp vụ**; một flag/configuration profile giúp chuyển giữa producer thật và stub theo môi trường mà không cần rebuild application.


## 11. Dùng Docker Compose cho nhóm stub phục vụ local development

Nếu Checkout Service phụ thuộc hai producers, việc gõ nhiều lệnh `docker run` sẽ khó bảo trì. Có thể dùng một Stub Runner Boot container chạy hai WireMock instances:

~~~text
com.example:inventory-producer:1.2.3:stubs:10080
com.example:pricing-producer:2.1.0:stubs:10081
~~~

Một file `compose.yaml` minh họa (phải thay địa chỉ repository và image tag):

~~~yaml
services:
  stubrunner:
    image: springcloud/spring-cloud-contract-stub-runner:<compatible-tag>
    environment:
      SPRING_CLOUD_CONTRACT_STUBRUNNER_STUBS_MODE: REMOTE
      SPRING_CLOUD_CONTRACT_STUBRUNNER_REPOSITORY_ROOT: "https://repo.example.test/repository/maven-releases/"
      SPRING_CLOUD_CONTRACT_STUBRUNNER_IDS: "com.example:inventory-producer:1.2.3:stubs:10080,com.example:pricing-producer:2.1.0:stubs:10081"
    ports:
      - "127.0.0.1:8750:8750"
      - "127.0.0.1:10080:10080"
      - "127.0.0.1:10081:10081"
~~~

Trong `ids`, mỗi tọa độ xác định một producer artifact và port stub. Kiểm tra cơ chế parser/danh sách của phiên bản image đang chạy. **Không kết luận hai stubs đã nạp chỉ vì Compose đã chấp nhận file**; kiểm tra `GET /stubs` và gọi hai WireMock ports.

Có thể khởi động/dừng bằng:

~~~bash
docker compose up -d stubrunner
docker compose logs --follow stubrunner
docker compose down
~~~

`up -d` chỉ khởi tạo container, **không chờ tất cả mappings đã tải xong**. Một quy trình đúng phải đợi `/stubs` hiển thị đủ artifacts rồi mới chạy consumer tests. Khi dọn dẹp, tránh tùy tiện xóa `-v` hoặc các volumes dùng chung nếu project có dữ liệu cần giữ.

### 11.1. Checkout trên host và Checkout trong container có URL khác nhau

Khi Checkout chạy trên máy host với ports đã publish:

~~~text
INVENTORY_BASE_URL=http://localhost:10080
PRICING_BASE_URL=http://localhost:10081
~~~

Khi Checkout cũng chạy trên **cùng Docker Compose network**:

~~~text
INVENTORY_BASE_URL=http://stubrunner:10080
PRICING_BASE_URL=http://stubrunner:10081
~~~

`localhost` của container Checkout không trỏ sang container Stub Runner. Đây là nguyên nhân thường gặp của lỗi `Connection refused`. Trong một Docker network chung, tên service `stubrunner` được dùng làm DNS nội bộ.

### 11.2. Không public management API khi không cần

Nếu cả Checkout và test runner đều truy cập qua network nội bộ, không cần publish port `8750` ra Internet. Những dòng `127.0.0.1` trong ví dụ chỉ cho phép kết nối từ máy host qua loopback. Trong môi trường chia sẻ, ưu tiên network isolation, firewall và internal-only services.

## 12. Môi trường tạm thời theo pull request

Một **ephemeral preview environment** được tạo cho một pull request/commit và dọn dẹp sau khi kiểm thử xong. Nó có thể chạy Checkout cùng các stub của Inventory, Pricing mà không triển khai hai producers thật.

~~~mermaid
flowchart LR
    PR["Pull request Checkout"] --> PREV["Preview namespace/network"]
    PREV --> APP["Checkout application"]
    PREV --> RUN["Stub Runner Boot"]
    RUN --> INV["Inventory WireMock"]
    RUN --> PRI["Pricing WireMock"]
    APP --> INV
    APP --> PRI
    PREV --> TEST["Smoke/consumer tests"]
    TEST --> CLEAN["Teardown + TTL"]
~~~

### 12.1. Quy trình tạo preview có thể tái lập

1. Xác định commit Checkout và **version stub đã được producer xác minh** cho các dependencies.
2. Tạo một namespace, Docker network hoặc Compose project riêng theo PR/run ID.
3. Khởi động Stub Runner Boot với image tag và stub coordinates được pin.
4. Chờ management API hoạt động và `GET /stubs` liệt kê **đúng Inventory/Pricing artifacts**.
5. Cấp base URLs nội bộ cho các HTTP clients của Checkout.
6. Đợi Checkout sẵn sàng, chạy smoke/consumer behavior tests.
7. Thu thập logs, stub versions, HTTP failures và kết quả test nếu có lỗi.
8. Dừng process/containers, xóa namespace sau khi job xong; áp dụng TTL cho tài nguyên bị bỏ quên.

Một môi trường ví dụ có tên:

~~~text
checkout-pr-4821
checkout-pr-4821-stubs
checkout-pr-4821-network
~~~

Các tên này chỉ để phân biệt tài nguyên. Không để hai PR thay đổi chung một WireMock scenario state hoặc một database giả dùng chung nếu không có chủ ý.

### 12.2. Preview xác minh được gì?

Một preview với stubs có thể chứng minh Checkout khởi động được, đọc configuration, định tuyến HTTP clients đúng, parse JSON và xử lý một vài tình huống success/error mẫu. Nó **không tự chứng minh**:

- Inventory Service thật xử lý transaction/database đúng.
- Cơ chế bảo mật xuyên hệ thống production đã đúng.
- Broker redelivery/order/exactly-once effects đã được kiểm tra.
- Độ trễ và khả năng chịu tải thật được tái hiện.
- Producer deployment có dùng đúng cùng version, configuration và dữ liệu runtime.

Vì vậy preview phù hợp cho **smoke/integration ở biên consumer**, không thay thế tất cả E2E, performance hoặc reliability tests.

## 13. Lifecycle và trạng thái của stub

Một stub server cần quản lý đầy đủ từ lúc tạo đến khi thu hồi:

| Giai đoạn | Kiểm tra | Kết quả |
| --- | --- | --- |
| Prepare | Artifact JAR, classifier, version, nguồn phát hành | Biết rõ provenance |
| Start | Container/image, repository access, cổng | Boot khởi động |
| Ready | `/stubs` có đủ mappings? | Có thể nhận request |
| Use | Consumer client gọi đúng WireMock | Assertions đúng nghiệp vụ |
| Observe | Logs, unmatched requests, HTTP status | Có dữ kiện debug |
| Stop | Process/container được dừng | Không chiếm port |
| Cleanup | Namespace, secrets, temporary volumes | Không còn orphaned resources |

### 13.1. Stateless và stateful stubs

Một stub đơn giản là **stateless**: cùng request nhận response mẫu cố định.

~~~text
GET /api/inventory/SKU-100 → 200, quantity=8
~~~

Đừng mặc định các tương tác sau có liên hệ trạng thái:

~~~text
POST /api/reservations
GET /api/reservations/RES-123
DELETE /api/reservations/RES-123
~~~

Nếu chỉ có mappings tĩnh, stub không tự tạo record sau POST. WireMock hỗ trợ **Scenarios** và response templating cho mô phỏng stateful khi cấu hình tương ứng; Spring Cloud Contract không tự biến mọi tập hợp contract độc lập thành một database giả.

Với stateful tests, tránh chia sẻ cùng một WireMock state giữa nhiều PR/tests song song; dùng instance hoặc reset state có chủ đích.

### 13.2. Có thể giả lập lỗi và độ trễ không?

Có thể thiết kế mappings/fault scenarios với delay, `500`, invalid body hoặc connection faults theo khả năng WireMock/test setup. Nhưng test phải kiểm chứng rõ nhánh retry, timeout, circuit breaker của **consumer**; không mặc định một stub mẫu có phân phối độ trễ hoặc xác suất lỗi giống production.

Nếu mục tiêu là latency SLA, outage resilience hoặc load, hãy dùng test chuyên biệt ngoài phạm vi contract sample.

## 14. Dùng nhiều stubs và messaging triggers

Ngoài HTTP stubs, Stub Runner Boot có endpoints phục vụ **messaging labels** trong các tích hợp được hỗ trợ. Những endpoints này nằm trên **management port**, không nằm trên WireMock port.

| Method/path | Ý nghĩa |
| --- | --- |
| `GET /stubs` | Liệt kê stubs và port đang chạy |
| `GET /stubs/{ivy}` | Tìm port cho một artifact |
| `GET /triggers` | Liệt kê labels messaging có thể trigger |
| `POST /triggers/{label}` | Trigger một label |
| `POST /triggers/{ivy}/{label}` | Trigger label của artifact xác định |

Ví dụ contract messaging:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    label 'paymentCaptured'

    input {
        triggeredBy('publishCapturedPayment()')
    }

    outputMessage {
        sentTo('payments.captured')
        body(
            eventType: 'PaymentCaptured',
            paymentId: 'PAY-123'
        )
    }
}
~~~

Với messaging integration và broker/binder đã được cấu hình đúng, có thể gọi:

~~~bash
curl --silent --show-error http://localhost:8750/triggers

curl --request POST --fail --silent --show-error \
  http://localhost:8750/triggers/paymentCaptured
~~~

**Không suy ra** việc một POST trigger được chấp nhận có nghĩa broker đã giao xong, consumer đã ack hoặc business effect xảy ra đúng một lần. Muốn kiểm chứng delivery, retry và idempotency cần tests ở các tầng tương ứng.

## 15. Bảo mật: chỉ dùng Stub Runner Boot ở mạng tin cậy

Tài liệu chính thức cảnh báo **Stub Runner Boot không được bảo vệ truy cập theo mặc định và không dành cho production hoặc môi trường không tin cậy**. Điều này càng quan trọng với preview environments vì chúng có thể vô tình được triển khai sau một public ingress.

### 15.1. Rủi ro cần tránh

- Người lạ truy cập management API có thể xem stubs hoặc kích hoạt messaging labels.
- WireMock admin API có thể để lộ hoặc cho phép thay đổi mappings khi bị mở sai.
- Test data vô tình chứa thông tin cá nhân, access tokens hoặc production payload.
- Repository credentials bị lộ qua environment, logs hoặc image layers.
- Orphan containers vẫn tồn tại sau khi PR đóng và trở thành endpoints không quản lý.
- Consumer trong test profile có thể vẫn trỏ tới live production URL của một dependency.

### 15.2. Biện pháp

1. Giữ management port và WireMock admin **nội bộ**, bind port host vào `127.0.0.1` khi chỉ dùng local.
2. Dùng Docker network/namespace riêng và network policy chặn truy cập ngoài khi ở preview.
3. Dùng fixtures giả, không dùng data hay tokens production.
4. Inject repository credentials bằng secret manager/CI secrets với quyền tối thiểu.
5. Pin image tag và artifact versions; dùng registry/repository đã được phê duyệt.
6. Gắn TTL và teardown vào vòng đời PR/job.
7. Kiểm tra base URLs ở consumer không bao giờ chuyển sang production ngoài ý muốn.
8. Nếu cần đường truy cập chung, thêm lớp auth/network control được quản lý riêng; không dựa vào bảo mật mặc định của Stub Runner Boot.

**Không nên public management endpoints** chỉ vì muốn tiện mở `GET /stubs` từ trình duyệt. Hãy truy cập qua internal network hoặc công cụ được ủy quyền.


## 16. Các lỗi thường gặp trong local và preview environments

| Triệu chứng | Nguyên nhân có thể | Kiểm tra |
| --- | --- | --- |
| Không pull được image | Sai image repository/tag, registry yêu cầu quyền | Tên image, version, registry access |
| Stub Runner Boot không start | Cấu hình/dependency không tương thích | Container startup logs, image/Java compatibility |
| `GET /stubs` không kết nối | Boot chưa sẵn sàng, quản lý port sai | Port `8750`, mapping, process status |
| `/stubs` trả danh sách rỗng | `ids` sai, artifact chưa resolve | Effective environment, resolver logs |
| Artifact download trả `404` | Sai version, group/artifact/classifier | Maven coordinates, repositoryRoot |
| Artifact download trả `401/403` | Thiếu hoặc sai repository credentials | Secrets, permission scope |
| LOCAL không tìm thấy stub trong Docker | Chưa mount `.m2` hoặc mount sai user path | Image home, local Maven layout |
| WireMock trên host không kết nối được | Chưa publish cổng hoặc bind khác | `docker ps`, `-p`, firewall |
| Checkout container báo Connection refused | Dùng `localhost` của sai container | Service DNS, Docker network |
| WireMock trả `404` khi gọi success path | Method, path, Accept header hoặc mapping sai | Request logs, `/__admin/mappings` |
| Stub response đúng nhưng Checkout fail | DTO/deserializer hoặc use case code sai | Consumer stack trace/assertions |
| Stub cho dữ liệu cũ | Cache hoặc artifact version đã thay đổi | Coordinates, artifact checksum, restart |
| CI chạy xanh mà không có stub | Checks/contract tests bị skip hoặc tắt fail on no stubs | Test counts và `/stubs` |
| Preview xanh nhưng production lỗi | Hành vi thật ngoài phạm vi stub | Integration, E2E, performance tests |

### 16.1. Ba loại HTTP 404 cần phân biệt

~~~text
Repository HTTP 404:
    Stub Runner không tải được artifact; không có mapping.

WireMock unmatched request HTTP 404:
    Stub server đã chạy nhưng request không khớp.

Contract business HTTP 404:
    Request khớp mapping cố ý trả 404,
    thường kèm JSON code như INVENTORY_NOT_FOUND.
~~~

Nếu Checkout hiển thị “SKU không tồn tại” khi gọi nhầm path `/api/inventories/SKU-404`, có nguy cơ **test xanh sai** vì không phân biệt unmatched stub với lỗi nghiệp vụ.

### 16.2. Quy trình khoanh vùng theo tầng

1. **Image/process:** Stub Runner Boot start thành công?
2. **Artifact:** Tọa độ và version có tồn tại trong local/remote repository?
3. **Loaded stubs:** `GET /stubs` liệt kê đúng artifact và port?
4. **Network:** Từ network namespace của Checkout, có gọi được WireMock?
5. **Matching:** Mapping có khớp method, path, headers, query/body?
6. **Response:** Status, Content-Type, JSON schema có đúng cam kết?
7. **Consumer:** Code Checkout thực sự xử lý response đúng không?
8. **Provenance:** Artifact có đến từ producer version đã được verified?

Nếu một bước thất bại, hãy sửa đúng lớp thay vì nới contract matchers hoặc đổi business logic cho vừa response sai.

### 16.3. Tránh sleep cố định để kiểm tra readiness

~~~bash
docker compose up -d stubrunner
sleep 30
# Chạy tests sau 30 giây, dù mappings chưa chắc đã nạp.
~~~

Cách này vừa lãng phí vừa dễ flaky khi mạng repository chậm. Thay bằng **poll `GET /stubs` và một WireMock endpoint mẫu có timeout hữu hạn**, trả lỗi rõ nếu không thấy artifact/cổng mong đợi. Không nên đợi vô hạn khi image hoặc artifact không khả dụng.

## 17. CI, versioning và release gates

Một quy trình đáng tin cậy nên tách **producer pipeline** khỏi **consumer/preview pipeline**.

~~~mermaid
flowchart TD
    A["Producer source + contracts"] --> B["Sinh và chạy producer tests"]
    B --> C{"Verification đạt?"}
    C -- "Không" --> X["Chặn publish"]
    C -- "Có" --> D["Đóng gói + publish stubs artifact"]
    D --> E["Consumer/preview pin stub version"]
    E --> F["Start Stub Runner Boot"]
    F --> G["Kiểm tra /stubs + WireMock readiness"]
    G --> H["Checkout smoke/integration tests"]
    H --> I["Lưu logs, teardown"]
~~~

Các gates cần xem xét:

| Gate | Điều cần khẳng định |
| --- | --- |
| **Producer verification** | Generated tests thật sự được sinh, biên dịch và chạy; không 0 tests |
| **Artifact packaging** | JAR `-stubs` có đúng mappings, groupId, artifactId, version |
| **Artifact publish** | Chỉ publish bản được duyệt; release artifact không bị overwrite ngầm |
| **Preview provisioning** | Docker image/repository credentials/network/ports đúng |
| **Stub readiness** | `/stubs` có đúng danh sách và từng endpoint mẫu gọi được |
| **Consumer behavior** | Checkout client/use case xử lý đúng 2xx và các lỗi cam kết |
| **Cleanup** | Container, namespace và credentials tạm không bị giữ lâu |

### 17.1. Pin version

Nên dùng:

~~~text
com.example:inventory-producer:1.2.3:stubs:10080
~~~

Thay vì luôn:

~~~text
com.example:inventory-producer:+:stubs:10080
~~~

`+` có thể chọn một artifact mới giữa hai lần chạy. Cùng một commit Checkout vì vậy có thể dùng hai contract versions khác nhau, khiến lỗi khó tái lập. Với CI, preview và bug reproduction, **pin stub artifact version cùng Docker image tag**.

### 17.2. Các tests nào cần nằm ngoài Stub Runner?

| Nhu cầu | Kiểm thử phù hợp |
| --- | --- |
| Producer đáp ứng contract thật | Spring Cloud Contract generated producer tests |
| Checkout gửi request/parse response đúng | Consumer tests dùng stubs |
| Inventory DB thực hiện reservation atomic | Producer integration/transaction tests |
| Retry/circuit breaker của Checkout | Fault simulation có kiểm soát và resilience tests |
| Kafka event ordering, redelivery | Broker integration/failure tests |
| P99 latency dưới tải thực | Performance/load tests |
| Authentication/authorization toàn tuyến | Security/integration tests |
| Deployment compatibility với hạ tầng thật | Smoke/E2E tests phù hợp |

**Không báo “done” chỉ vì Stub Runner Boot có process còn chạy**. Độ tin cậy nằm ở assertions đúng ranh giới và những gates đã thực sự được thực thi.

## 18. Bài thực hành: tạo một môi trường Checkout tạm thời

### 18.1. Đề bài

Inventory Service cung cấp:

~~~http
GET /api/inventory/SKU-100 HTTP/1.1
Accept: application/json
~~~

với response:

~~~json
{
  "sku": "SKU-100",
  "available": true,
  "quantity": 8
}
~~~

Khi SKU không tồn tại:

~~~http
GET /api/inventory/SKU-404 HTTP/1.1
Accept: application/json
~~~

phản hồi `404` cùng JSON `{"code":"INVENTORY_NOT_FOUND"}`.

Checkout Service cần đọc số lượng, từ chối đơn yêu cầu quá 8 và phân biệt lỗi SKU không tồn tại.

### 18.2. Nhiệm vụ A — Chuẩn bị artifact

1. Viết hoặc chọn hai contract Groovy/YAML theo Mục 4.
2. Cấu hình Spring Cloud Contract plugin trong producer.
3. Sinh và **chạy** producer verification.
4. Đóng gói stub classifier `stubs`.
5. Chọn `LOCAL` (nếu install vào Maven local) hoặc `REMOTE` (nếu publish artifact).
6. Ghi tọa độ đúng `com.example:inventory-producer:1.2.3:stubs`.

**Câu hỏi:** Vì sao một stub JAR tự tạo chưa đủ để chứng minh implementation producer đang đáp ứng những gì consumer cần?

### 18.3. Nhiệm vụ B — Chạy standalone server

Khởi động Stub Runner Boot Docker theo Mục 8 với cổng:

~~~text
Management: 8750
Inventory:  10080
~~~

Ghi tên image và tag thực tế, stub coordinates, mode, repositoryRoot (không ghi credentials). Sau đó kiểm tra:

~~~bash
curl --silent --show-error http://localhost:8750/stubs

curl --fail --silent --show-error \
  -H "Accept: application/json" \
  http://localhost:10080/api/inventory/SKU-100
~~~

Không coi lệnh HTTP `/stubs` trả response là đủ: artifact Inventory phải xuất hiện và WireMock cần trả đúng status/body.

### 18.4. Nhiệm vụ C — Kiểm tra not-found

~~~bash
curl --silent --show-error --include \
  -H "Accept: application/json" \
  http://localhost:10080/api/inventory/SKU-404
~~~

Xác minh **cả status 404 lẫn code INVENTORY_NOT_FOUND**, rồi cố tình gọi sai path `/api/inventories/SKU-404`. Giải thích vì sao matched business 404 khác unmatched WireMock 404.

### 18.5. Nhiệm vụ D — Chạy Checkout trên host và container

Khi Checkout chạy trên host:

~~~text
INVENTORY_BASE_URL=http://localhost:10080
~~~

Khi Checkout chạy trong container cùng network:

~~~text
INVENTORY_BASE_URL=http://stubrunner:10080
~~~

Dùng **InventoryClient và Checkout use case thật** để kiểm tra:

- Yêu cầu 3 sản phẩm với quantity 8 được phép (nếu còn điều kiện khác đạt).
- Yêu cầu 9 sản phẩm bị từ chối.
- `SKU-404` được nhận diện như not-found, không phải out-of-stock.
- Checkout không vô ý gọi production Inventory Service.

### 18.6. Nhiệm vụ E — Chuyển sang preview PR

1. Tạo môi trường có tên theo PR/run ID.
2. Pin image tag và version stub `1.2.3`.
3. Giới hạn truy cập management API vào mạng nội bộ.
4. Chờ readiness, chạy smoke tests và lưu kết quả.
5. Teardown sau PR/job hoặc theo TTL.

**Câu hỏi:** Điều gì có thể khiến một PR bắt đầu fail khi code không đổi nếu image tag hoặc stub version không được pin?

### 18.7. Tự đánh giá

| Nhận định | Đúng/Sai |
| --- | --- |
| Standalone Stub Runner có thể chạy tách khỏi JUnit và producer thật | **Đúng** |
| Cổng quản lý Boot và cổng WireMock có cùng mục đích | **Sai** |
| Dùng `LOCAL` trong Docker tự đọc Maven repo của host mà không mount | **Sai** |
| Một preview dùng stubs thay thế được mọi E2E/integration tests | **Sai** |
| Stub Runner Boot nên mở public vì không chứa business code thật | **Sai** |
| WireMock unmatched request có thể trả HTTP `404` | **Đúng** |
| Producer verification cần được thực hiện riêng trước publish | **Đúng** |
| Pin artifact version giúp tái lập kết quả CI | **Đúng** |

### 18.8. Kết quả cần nộp

Một báo cáo ngắn gồm: artifact version; image/mode; management và WireMock ports; các request/response đã thử; consumer behavior assertions; log lỗi nếu có; giới hạn kiểm chứng; trạng thái cleanup.

## 19. Checklist trước khi dùng stub độc lập

- [ ] Nhu cầu consumer đã được phản ánh trong Groovy/YAML contract.
- [ ] Producer generated tests thực sự được sinh và thực thi.
- [ ] Stub artifact có groupId/artifactId/version/classifier/mappings đúng.
- [ ] Đã chọn công cụ: Stub Runner Boot Docker, Boot tự build hoặc WireMock trực tiếp.
- [ ] Không mặc định executable Stub Runner Boot JAR phiên bản mới luôn có sẵn.
- [ ] Chọn `LOCAL`/`REMOTE` và repositoryRoot phù hợp.
- [ ] Version stub và Docker image tag được pin trong CI/preview.
- [ ] Phân biệt cổng Boot management và cổng WireMock.
- [ ] `GET /stubs` liệt kê đúng artifact và cổng.
- [ ] Có smoke request xác nhận mappings trả đúng status/header/body.
- [ ] Consumer client trỏ đúng URL trong host/container network.
- [ ] Có kiểm tra nhánh lỗi 404 với error body, tránh unmatched request pass giả.
- [ ] Không mở management/admin endpoints công khai.
- [ ] Không dùng PII/production data hay secrets trong stub.
- [ ] Repository credential được cấp qua secrets và quyền tối thiểu.
- [ ] Ephemeral environments cách ly theo PR, có TTL và teardown.
- [ ] Readiness dùng điều kiện thực tế có timeout, không chỉ sleep cố định.
- [ ] Consumer test kiểm tra code consumer thật, không chỉ ping stub.
- [ ] Có các tests khác cho performance, security, DB transaction và messaging delivery.
- [ ] Không phát hành stub từ producer chưa đạt verification.

## 20. Tài liệu tham khảo

- [Spring Cloud Contract — Using the Stub Runner Boot Application](https://docs.spring.io/spring-cloud-contract/reference/project-features-stubrunner/stub-runner-boot.html): standalone Boot, API `/stubs` và `/triggers`, bảo mật và giới hạn executable JAR.
- [Spring Cloud Contract — Docker Project](https://docs.spring.io/spring-cloud-contract/reference/docker-project.html): Docker image Stub Runner, environment variables, ports, messaging.
- [Spring Cloud Contract — Stub Runner Core](https://docs.spring.io/spring-cloud-contract/reference/project-features-stubrunner/stub-runner-core.html): `CLASSPATH`, `LOCAL`, `REMOTE` và cách lấy mappings.
- [Spring Cloud Contract — Common Properties](https://docs.spring.io/spring-cloud-contract/reference/project-features-stubrunner/stub-runner-common.html): `ids`, classifier, port range, repositoryRoot và defaults.
- [Spring Cloud Contract — HTTP Contracts](https://docs.spring.io/spring-cloud-contract/reference/project-features-contract/http.html): định nghĩa request/response Groovy/YAML.
- [WireMock — Documentation](https://wiremock.org/docs/): request matching, JSON mappings, scenarios và admin API.

**Ghi nhớ:** Stub độc lập giúp phát triển Checkout hoặc chạy preview mà không cần triển khai mọi dependency producer thật. Kết quả chỉ đáng tin khi stub xuất phát từ hợp đồng đã được producer xác minh, artifact có version rõ ràng, Stub Runner Boot được chạy trong mạng tin cậy và consumer test thực sự kiểm tra hành vi. Hãy phân biệt cổng quản lý với HTTP stub, kiểm tra readiness, giữ mạng/credentials an toàn và dọn dẹp sau khi dùng. **Một môi trường stub chạy xanh không thay thế bằng chứng producer verification và các integration tests cần thiết.**
