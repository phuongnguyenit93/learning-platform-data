# Giới hạn mạng và quyền của tiến trình chạy stub

## 1. Vì sao một stub phục vụ dữ liệu giả vẫn cần bảo mật?

Trong **Spring Cloud Contract**, producer và consumer thống nhất hành vi HTTP hoặc thông điệp bằng **Groovy/YAML DSL**. Công cụ có thể sinh kiểm thử để xác minh producer, đóng gói các stubs tương ứng và dùng **Stub Runner** cho consumer tests. Trong trường hợp HTTP, **WireMock** thường được dùng để phục vụ các request/response mẫu; CI kết hợp producer verification và consumer tests để phát hiện API thay đổi không tương thích.

Một WireMock server trả dữ liệu giả có vẻ không nguy hiểm như production service. Tuy nhiên, **tiến trình chạy stub vẫn là một tiến trình mạng**, có thể:

- Mở **cổng TCP** và nhận request từ một phạm vi rộng hơn dự tính.
- Cung cấp **WireMock Admin API** để xem, thêm, sửa hoặc reset mappings và request journal.
- Ghi lại **header, URL, body** mà consumer gửi, trong đó có thể có cookie, bearer token hoặc dữ liệu riêng tư.
- Tải stubs JAR từ **artifact repository**, sử dụng credentials của CI.
- Đọc/ghi file, khởi tạo extension, chạy logic phụ thuộc vào cấu hình và quyền hệ điều hành.
- Gây ảnh hưởng lẫn nhau nếu nhiều test jobs chia sẻ chung cổng hoặc server có trạng thái.

Vì vậy, mục tiêu của bài không chỉ là làm test chạy xanh, mà là **chỉ cho những tiến trình cần thiết truy cập stub, chỉ cấp quyền cần thiết cho stub, và không để mock server trở thành cửa ngõ vào mạng hoặc bí mật của CI**.

> **Nguyên tắc:** Stub là **hạ tầng kiểm thử không đáng tin như production**, không phải dịch vụ công khai. Cô lập theo thời gian sống, mạng, danh tính, filesystem, quyền truy cập artifacts và dữ liệu log.

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Vẽ đúng **ranh giới tin cậy** giữa consumer test, Stub Runner, WireMock Admin API, registry và các hệ thống thật.
2. Phân biệt bind vào `127.0.0.1` với bind vào `0.0.0.0`, cổng host với cổng container, ingress với egress.
3. Giới hạn quyền của tiến trình, container hoặc Kubernetes Pod chạy stub bằng nguyên tắc **least privilege**.
4. Nhận ra nguy cơ của **Admin API, request journal, proxy mappings, Groovy DSL và extensions**.
5. Sử dụng fixture giả, giữ secrets an toàn và phân biệt **mock authentication** với **security verification**.
6. Thiết kế kiểm thử/CI có thể xác nhận những ranh giới bảo mật thực sự đang được áp dụng.

## 2. Mô hình đe dọa: những ai có thể giao tiếp với stub?

Xét `checkout-service` kiểm thử client gọi `order-service`:

```mermaid
flowchart TD
    A[Consumer test process] -->|HTTP request| B[Stub Runner / WireMock]
    B -->|Response mẫu| A
    C[CI producer đã verify contracts] --> D[Stubs JAR repository]
    D -->|Resolve artifact| B
    E[Người/tiến trình khác trên mạng] -.->|Không nên được phép| B
    B -.->|Không được proxy vô ý| F[Production APIs / metadata service]
    B -->|Request journal / files| G[CI workspace và logs]
    H[Người quản trị test] -->|Chỉ khi thật sự cần| I[WireMock Admin API]
    I --> B
```

Sơ đồ cho thấy ba luồng tách biệt:

| Luồng | Mục đích hợp lệ | Ranh giới cần bảo vệ |
| --- | --- | --- |
| **Consumer → HTTP stub** | Gọi endpoint được giả lập, nhận response theo contract | Chỉ client/test được cho phép tiếp cận port |
| **Stub Runner → artifact registry** | Lấy stubs JAR được producer xác minh | Chỉ truy cập registry cần thiết, dùng credentials đọc |
| **Tester/CI → Admin API và logs** | Kiểm tra mappings, reset scenario, điều tra mismatch | Không mở quyền cho máy khác hoặc người ngoài nhóm |
| **Stub → mạng khác** | Thường **không cần** sau khi nạp artifact | Không proxy/egress tới production hoặc metadata service |
| **Stub → filesystem/container** | Đọc mappings, ghi dữ liệu tạm nếu runtime cần | Không cho đọc secrets ngoài phạm vi hoặc ghi toàn bộ workspace |

**Một mô hình bảo mật đúng bắt đầu từ phạm vi sử dụng**: stub chỉ được gọi trong cùng process, cùng máy, cùng Docker network, hay cần được một consumer test ở Pod khác gọi? Những trường hợp này phải dùng cách hạn chế kết nối khác nhau.

### Tài sản cần bảo vệ

Không chỉ có request body; cần xem xét **CI secrets**, token artifact registry, credentials production bị cấu hình nhầm, request/response logs, source code hoặc volume mounted, mạng nội bộ và khả năng chạy extension không đáng tin.

Nếu consumer vô tình gửi một bearer token production vào mock server, nó có thể xuất hiện trong **WireMock request journal** hoặc CI log, dù response trả về chỉ là JSON giả. Bảo mật dữ liệu test phải bắt đầu từ **client và fixture**, không chờ đến bước xóa log.

## 3. Bind address, port và khả năng truy cập

Một ứng dụng HTTP lắng nghe trên địa chỉ IP và cổng:

| Bind address | Ý nghĩa phổ biến | Lưu ý |
| --- | --- | --- |
| `127.0.0.1:8089` | Chỉ qua giao diện loopback IPv4 của cùng network namespace | Thích hợp cho test chạy cùng host |
| `[::1]:8089` | Loopback IPv6 | Cần kiểm tra client/hệ điều hành dùng IPv4 hay IPv6 |
| `0.0.0.0:8089` | Mọi giao diện IPv4 của network namespace | Có thể tới được từ mạng ngoài nếu firewall/routing cho phép |
| `<private-ip>:8089` | Một giao diện cụ thể | Vẫn cần firewall và giới hạn bên gọi |

**Bind vào `0.0.0.0` không tự chứng minh cổng đã public**, nhưng là một lựa chọn **rộng hơn** loopback: nếu máy có route/port forwarding, máy khác có thể kết nối. Ngược lại, `127.0.0.1` chỉ giới hạn trong **network namespace của tiến trình**; nó không làm tiến trình an toàn với mọi phần mềm đã có quyền chạy cùng namespace.

### Khi consumer và stub cùng chạy trong một máy

Ưu tiên **loopback** nếu framework/distribution cho phép. Ví dụ với bản WireMock standalone hỗ trợ tùy chọn tương ứng:

```bash
# Ví dụ minh họa; thay tên JAR và kiểm tra --help của WireMock đang dùng.
java -jar wiremock-standalone.jar \
  --bind-address 127.0.0.1 \
  --port 8089
```

Sau khi server khởi động, kiểm tra thực tế socket chỉ listen trên loopback. Tên CLI option và khả năng bind có thể khác giữa WireMock versions/packaging; **không suy từ câu lệnh minh họa rằng Stub Runner tự truyền bind address giống hệt**.

Khi dùng `@AutoConfigureStubRunner`, port và lifecycle có thể do framework quản lý. Nếu API/phiên bản không cho thiết lập bind address trực tiếp, hãy dùng **firewall, network namespace, Docker/Kubernetes isolation hoặc chạy test trong một host không có inbound public**. Đừng tự đoán có một property `stubrunner.bind-address` nếu chưa được tài liệu bản đó xác nhận.

### Cổng cố định và cổng động

`ids = "com.example:order-service:1.7.0:stubs:9090"` là cách minh họa gán port cố định cho stub. Port cố định dễ hiểu nhưng có thể bị chiếm khi nhiều test chạy song song. Port động giảm xung đột; consumer cần lấy **port thực tế** từ Stub Runner theo lifecycle, không tiếp tục dùng URL `9090`.

**Port động không phải một biện pháp xác thực hoặc ủy quyền.** Nó giúp tránh va chạm, nhưng một tiến trình khác trên cùng máy/network namespace vẫn có thể phát hiện và gọi cổng đang mở. Phải kết hợp với giới hạn mạng và vòng đời test.

## 4. WireMock Admin API là bề mặt tấn công riêng

Khi được bật, WireMock Admin API thường nằm dưới `/__admin` và có thể thực hiện các tác vụ mạnh như:

```http
GET /__admin/mappings HTTP/1.1
GET /__admin/requests HTTP/1.1
POST /__admin/scenarios/reset HTTP/1.1
```

Tùy phiên bản/cấu hình, Admin API còn có thể thêm, xóa hoặc cập nhật mappings và reset server/request log. Vì vậy nếu một người ngoài test có thể truy cập admin:

- Họ có thể làm consumer test **trả sai response**, gây false positive hoặc false negative.
- Họ có thể xem request journal đã ghi các dữ liệu client gửi.
- Họ có thể thay mapping hoặc trạng thái scenario giữa các bước test.
- Họ có thể làm các test dùng chung server **không còn cô lập**, gây kết quả không tái lập.

**Không mặc định Admin API có authentication hoặc authorization như production API.** Nhiều cấu hình WireMock sử dụng các endpoint quản trị để phục vụ kiểm thử và cần được bảo vệ ở **biên mạng/proxy** nếu server dùng chung.

### Những biện pháp phù hợp

1. Ưu tiên **stub ephemeral trong test job**, không chạy server dùng chung lâu dài.
2. Không publish port admin ra mạng ngoài. Nếu API HTTP thường và `/__admin` chung cổng, **không thể chỉ dựa vào cấu hình một port riêng để cách ly admin**.
3. Với shared remote stub server, dùng **reverse proxy có access control** và quy tắc route chặn `/__admin` từ consumer không được phép; nếu reverse proxy dùng authentication, phải kiểm tra rule thực tế.
4. Nếu WireMock version cho phép vô hiệu hóa/quản lý Admin API theo cách hỗ trợ, áp dụng khi test không cần admin, nhưng không tự bịa CLI/property.
5. Không dùng `/__admin` như endpoint nghiệp vụ. Test cần reset state thì thực hiện qua test fixture tin cậy và cô lập quyền truy cập.

**Cảnh báo:** Nếu consumer được phép kết nối trực tiếp vào WireMock port, chỉ chặn `/__admin` trên một gateway khác **không bảo vệ** được admin nếu còn đường đi trực tiếp. Kiểm tra topology và network policy đầy đủ.

## 5. Nhật ký request có thể chứa secrets dù stub không gọi production

WireMock có thể ghi lại **received requests** để phục vụ matching diagnostics. Một request test vô tình chứa:

```http
GET /api/orders/42 HTTP/1.1
Authorization: Bearer TEST_TOKEN_DO_NOT_USE_REAL
Cookie: session=SYNTHETIC_SESSION
X-Correlation-Id: req-test-001
```

Đoạn trên dùng **giá trị giả**. Trong dự án thật, nếu CI dùng token production ở header `Authorization` hoặc cookie người dùng thật, các giá trị ấy có thể nằm trong journal, log hoặc artifact báo cáo.

### Quy tắc dữ liệu và log

- Chỉ gửi **test credentials** có phạm vi hẹp, hạn dùng ngắn hoặc token giả được tạo riêng, không gửi bearer token production.
- Không đưa password, access key, API key thật vào Groovy/YAML contracts, stub mapping JSON hoặc những file test có thể được publish.
- Chỉ bật request journal khi cần debug; giới hạn dữ liệu/retention và tắt hoặc kiểm soát theo API của phiên bản đang dùng.
- Khi cần xuất request journal để điều tra, **ẩn Authorization, Cookie, Set-Cookie và những field nhạy cảm**, kể cả query parameters mang token.
- Không dump toàn bộ request/response body vào log công khai. Artifact CI có thể được lưu nhiều ngày hoặc chia sẻ cho người có quyền đọc repository.
- Xóa hoặc reset state sau mỗi test/job theo lifecycle, nhưng nhớ rằng **reset không thu hồi log đã xuất**, bản sao trong storage và telemetry khác.

### “Response mẫu” cũng có thể là dữ liệu nhạy cảm

Một file `__files/order.json` chứa số tài khoản thật hay thông tin khách hàng thực vẫn gây rủi ro nếu được đưa vào stubs JAR. Sử dụng **synthetic data** đủ giống schema để kiểm thử nhưng không tái sử dụng dữ liệu nhận dạng người dùng. Cần review fixtures như review code.

## 6. Hợp đồng bảo mật HTTP: mô phỏng khác với xác thực thật

Giả sử `order-service` yêu cầu quyền `orders:read` để đọc đơn hàng. Consumer cần biết cách xử lý:

| Tình huống | HTTP response có thể được cam kết | Điều consumer cần kiểm tra |
| --- | --- | --- |
| Không có credential | `401 Unauthorized` | Client yêu cầu đăng nhập/refresh token đúng quy trình |
| Có danh tính nhưng thiếu quyền | `403 Forbidden` | Client không tiếp tục thao tác trái quyền |
| Có quyền và đơn tồn tại | `200 OK` | Client đọc được body đúng schema |
| Có quyền nhưng đơn không tồn tại | `404 Not Found` | Client hiểu mã lỗi nghiệp vụ |
| Token hết hạn | `401` hoặc response khác theo API policy | Client xử lý retry/refresh có giới hạn |

Những status ở đây là **ví dụ thiết kế API**, không có quy định mọi hệ thống bắt buộc xử lý credential theo đúng cách này. Với OAuth2/OIDC hoặc mTLS, trạng thái và header có thể phụ thuộc architecture/security policy.

### 6.1. Contract DSL cho nhánh thiếu token

Ví dụ YAML mô tả một request **không có `Authorization`** theo kịch bản API đã thống nhất:

```yaml
description: Đọc đơn hàng khi chưa xác thực
request:
  method: GET
  url: /api/orders/42
response:
  status: 401
  headers:
    Content-Type: application/json
  body:
    code: UNAUTHENTICATED
    message: Yêu cầu xác thực
```

Đây là mô tả response khi request không đưa credential trong test đã thiết kế. Nhưng **một contract không có matcher bắt buộc vắng mặt header chưa chắc tạo WireMock mapping chỉ match request không có Authorization**. Nếu cùng method/path có contract `200` khác mà không có điều kiện phân biệt, hai mappings có thể cạnh tranh.

Khi API có nhiều nhánh 200/401/403 trên cùng URL, cần **phân biệt input có chủ đích** bằng request header/body matcher, kịch bản test hoặc fixture mà producer verification thực sự dùng. Không dùng một stub trả `401` cho mọi request GET rồi kết luận client auth đã được kiểm tra đầy đủ.

### 6.2. Ví dụ WireMock mapping phân biệt token giả

Một mapping WireMock HTTP minh họa **success chỉ khi test gửi token giả cố định**:

```json
{
  "name": "Authorized request in the test fixture",
  "request": {
    "method": "GET",
    "urlPath": "/api/orders/42",
    "headers": {
      "Authorization": {
        "equalTo": "Bearer SYNTHETIC_ORDERS_READ_TOKEN"
      }
    }
  },
  "response": {
    "status": 200,
    "headers": {
      "Content-Type": "application/json"
    },
    "jsonBody": {
      "orderId": "ord-42",
      "status": "CONFIRMED"
    }
  }
}
```

**Đây là một fixture WireMock, không phải một trình kiểm tra JWT/OAuth.** WireMock chỉ so chuỗi header; nó không xác minh chữ ký, issuer, audience, expiration hoặc scope của token thật. Nếu muốn phản hồi `401` cho request thiếu token, cần mapping khác **được phân biệt rõ**, hoặc một test setup chủ động; một request không match mapping `200` có thể nhận **404 mặc định của WireMock**, không phải 401.

### 6.3. Contract test làm được và không làm được

- **Làm được:** xác minh consumer đặt header/đọc response 401/403/200 theo kịch bản; producer contract test có thể phát hiện sai status/body khi đường security thực sự được chạy trong base class.
- **Không tự làm được:** kiểm chứng chữ ký JWT, key rotation, tenant isolation, authorization theo tài nguyên, replay protection, audit policy hoặc gateway/WAF.
- **Cần test khác:** security integration tests đi qua `SecurityFilterChain`/gateway thực, tests role/scope/ownership, kiểm thử token hết hạn và negative auth cases trong môi trường kiểm soát.

**Nếu producer base class tắt security filters bằng cấu hình test hoặc mock toàn bộ authentication**, generated contract test có thể vẫn xác minh HTTP response schema nhưng **chưa kiểm chứng authentication thật**. Phạm vi ấy phải được ghi rõ; không được tuyên bố “API đã an toàn vì contract test pass”.

## 7. Phân biệt quyền truy cập API giả lập với quyền quản trị stub

Một test consumer cần gọi `GET /api/orders/42` không có nghĩa nó cần quyền:

- `GET /__admin/requests` để đọc toàn bộ request journal;
- `POST /__admin/mappings` để thay đổi response;
- Xóa trạng thái scenario của test khác;
- Đọc file credentials của CI;
- Kết nối tới production APIs từ bên trong stub.

Nếu WireMock đang để nghiệp vụ và Admin API **trên cùng listener**, không có khái niệm tách quyền chỉ bằng việc consumer gửi token vào endpoint `/api/orders`. Giới hạn quyền quản trị cần ở **reverse proxy, network topology, runner isolation hoặc khả năng tắt admin của runtime hỗ trợ**.

### Quy ước phân vai trong một test environment

| Vai trò | Quyền cần thiết | Quyền nên tránh |
| --- | --- | --- |
| Consumer client | HTTP endpoint nghiệp vụ giả lập | Gọi admin, ghi mappings hoặc duyệt request logs |
| Test fixture/setup process | Nạp mappings, reset state khi cần | Truy cập production secrets, mạng ngoài không cần |
| Stub server process | Đọc artifact/mapping, lắng nghe port giới hạn | Quyền admin OS, ghi toàn workspace, gọi production |
| CI orchestrator | Tải artifact, quản lý job, đọc test reports | Chia credentials registry ghi với tất cả consumer jobs |
| Artifact registry token | **Read-only** cho consumer CI | Publish/overwrite producer stubs artifacts |

Một nhóm có thể dùng cùng Java process chạy both test fixture và server, nhưng vẫn phải **giảm phạm vi quyền bên ngoài process**. Không chỉ vì các component nằm cùng JVM mà mặc định có thể dùng quyền root hoặc network unrestricted.

### Những giả định sai về HTTP status

Mặc định WireMock không nhất thiết trả `401` cho request thiếu Authorization. Nếu không có mapping, WireMock có thể trả `404`. Nếu một mapping quá rộng chỉ match path, request không có credential **vẫn có thể nhận `200`**. Vì vậy trong consumer tests, phải khẳng định **đúng mapping và đúng response**; không dùng response của mock server để suy ra hệ thống xác thực production.

## 8. Artifact registry và nguồn stub: giới hạn quyền từ trước khi server mở cổng

Stub Runner có thể lấy stubs JAR từ local repository (`LOCAL`), artifact registry (`REMOTE`) hoặc classpath (`CLASSPATH`). **Nơi lấy artifact** là một phần của bề mặt tin cậy:

```text
Producer contract + code revision
       -> producer verification PASS
       -> stubs artifact: group:artifact:version:stubs
       -> registry có provenance/digest
       -> consumer CI resolve đúng artifact
       -> Stub Runner / WireMock nạp mappings
```

Một artifact độc hại hoặc không đúng revision có thể khiến stub phản hồi dữ liệu không mong đợi, chèn response header bất thường hoặc tải/khởi chạy extension qua cơ chế cấu hình của hệ thống. **Đừng coi stubs JAR từ nguồn không tin cậy là dữ liệu vô hại**.

### Các biện pháp tối thiểu

1. Pin **group, artifact, version, classifier** và registry được phép; không tùy tiện dùng `latest`/version range trong release gate.
2. Đối chiếu **SHA-256 hoặc checksum/attestation** với artifact được producer CI phát hành.
3. Ưu tiên immutable release repository; quản lý SNAPSHOT/candidate tách biệt.
4. Consumer CI chỉ có quyền **read**; không cấp quyền publish/overwrite artifact của producer.
5. Credentials registry nằm trong CI secret store, Maven settings hoặc Gradle credentials; không viết vào contract DSL, log hay URL.
6. Giảm quyền outbound của tiến trình sau khi artifact đã được tải, nếu workflow cho phép.
7. Chỉ cho phép **extensions, transformers hoặc plugin classes** được review rõ ràng.

### Hợp đồng Groovy không giống dữ liệu JSON tĩnh

**Groovy DSL có khả năng thực thi biểu thức/script trong quá trình sinh contract**, không nên nhận và đánh giá nguồn Groovy không tin cậy trong một CI runner có quyền truy cập production secrets hoặc toàn mạng nội bộ. YAML DSL thường mang dạng dữ liệu khai báo hơn nhưng **không làm toàn bộ build tool/plugin chain tự an toàn**.

Khi nhận PR contract từ contributor bên ngoài tổ chức, cần xem **độ tin cậy của source và CI permissions**. Có thể chạy generation/verification trong runner cô lập, không cấp secrets cho pull request không tin cậy, kiểm soát dependencies/extensions và chỉ publish sau review + producer verification.

### LOCAL cũng có rủi ro

Artifact trong Maven local repository có thể do một job khác để lại, không phải producer version mục tiêu. Một `LOCAL` stub cũ làm test xanh giả, trong khi một artifact bị nhiễm độc có thể không đến từ publisher chính thức. CI nghiêm ngặt có thể dùng **repository local riêng cho từng job** và kiểm tra digest thay vì chia sẻ `~/.m2` tùy tiện.

## 9. Giới hạn outbound: stub không nên trở thành proxy tới hệ thống thật

WireMock có các khả năng như **proxying** hoặc extension/transformer để tạo response linh hoạt. Khi bài test chỉ cần response mẫu từ contract, những tính năng đó thường **không cần**.

### Nguy cơ của proxy mappings

Một mapping được cấu hình để forward request tới host thật có thể:

- Vô tình đưa `Authorization` hoặc body chứa dữ liệu nhạy cảm tới dịch vụ production.
- Khiến test consumer gọi endpoint thật, làm thay đổi dữ liệu ngoài môi trường test.
- Che sự khác biệt giữa mock và producer, khiến test không còn tái lập.
- Tạo đường kết nối ra mạng nội bộ, metadata endpoint hoặc nơi mà test runner không được phép truy cập.

**Không nên nạp tùy tiện mapping có proxy/forward URL do người ngoài cung cấp**. Nếu bài kiểm thử cần mô phỏng network failure hoặc proxy một sandbox service, phải dùng allowlist egress, synthetic credentials, host cố định và review mappings/extensions.

### Mô hình egress mong muốn

| Giai đoạn | Egress tối thiểu |
| --- | --- |
| Producer/CI tải dependencies | Chỉ artifact registries cần thiết qua kết nối được quản lý |
| Stub Runner resolve stubs | Chỉ registry chứa exact stubs artifact |
| WireMock phục vụ static mappings | **Thường không cần outbound** |
| Consumer test gọi stub | Chỉ mạng nội bộ test/loopback; tránh gọi production |
| Test teardown/reporting | Chỉ endpoint lưu artifact/log đã duyệt, nếu cần |

Nếu tách **bước tải artifact** và **bước chạy server**, container serving static mappings có thể bị giới hạn egress mạnh hơn. Một `--network` Docker thông thường hoặc một Kubernetes Service nội bộ **không tự chặn outbound**; phải kiểm tra egress policy/firewall thực tế.

### Metadata/localhost không phải mục tiêu thử nghiệm

Một mapping/test có thể chứa URL nội bộ hoặc địa chỉ metadata của cloud VM. Không đưa những địa chỉ ấy vào các proxy mappings; **block egress** tới metadata services và các dải mạng không cần thiết theo policy hạ tầng. Khi có yêu cầu debug request forwarding, dùng sandbox endpoint được cho phép, không lấy token hoặc cấu hình từ environment thật.

## 10. Quyền tiến trình trên developer workstation và CI runner

Ngay cả khi mock chỉ bind loopback, tiến trình vẫn có quyền của tài khoản OS đang chạy nó. Nếu CI user có quyền đọc `~/.aws/credentials`, Docker socket hoặc mã nguồn nhiều dự án, một extension bị lỗi/độc hại có thể gây hậu quả vượt xa một stub test.

### Nguyên tắc least privilege

- Chạy bằng **tài khoản không phải root/admin** khi runtime/container hỗ trợ.
- Không cấp Docker socket, Kubernetes service-account token có quyền rộng hay host filesystem mount không cần thiết.
- Chỉ mount **mappings và response files** ở chế độ **read-only** nếu không cần sửa trong runtime.
- Cấp thư mục tạm **riêng cho job** với quyền ghi tối thiểu; xóa sau khi hoàn tất.
- Không chia sẻ workspace/maven cache có quyền ghi với những PR không tin cậy.
- Giới hạn CPU, RAM, số process/file descriptors phù hợp để một test sai không ảnh hưởng máy chạy chung.
- Chạy mỗi test job với vòng đời riêng, tránh giữ server quản trị mở sau khi job kết thúc.

**Giới hạn tài nguyên không thay thế giới hạn quyền.** Một stub có quota RAM 512 MiB vẫn có thể đọc file secret nếu process có quyền OS. Ngược lại, read-only root filesystem không chặn việc truy cập mạng nếu egress không bị hạn chế.

### “Không chạy root” cũng cần kiểm tra thực tế

Một image Java có thể được đóng gói để chạy dưới non-root, nhưng cũng có image/extension đòi ghi file tại đường dẫn cố định. Nếu chỉ ép user ID tùy ý, test có thể fail vì permission. Cách sửa không phải quay về root vô điều kiện, mà là **bổ sung writable temporary volume đúng chỗ, chỉnh ownership khi build image và kiểm tra runtime startup**.

## 11. Docker: giới hạn host port, filesystem và capabilities

Trong bài lab chạy WireMock standalone dưới Docker, có thể tách các yếu tố:

- **Network:** container nằm trong network dành riêng cho test và publish port host **chỉ trên loopback**.
- **Filesystem:** image/mappings read-only; chỉ `/tmp` có quyền ghi cần thiết.
- **Capabilities:** bỏ Linux capabilities không cần thiết, chặn privilege escalation.
- **Artifact:** dùng image version/digest xác định, không vô tình dùng `latest`.
- **Lifecycle:** container bị xóa khi test kết thúc.

Ví dụ **Linux/macOS shell với Docker Linux container**:

```bash
# Chỉ tạo network test nếu chưa tồn tại.
docker network create contract-test-net

# Ví dụ lệnh triển khai; cần thay digest image bằng giá trị đã xác minh.
docker run --rm --name order-stub \
  --network contract-test-net \
  -p 127.0.0.1:8089:8080 \
  --cap-drop ALL \
  --security-opt no-new-privileges \
  --read-only \
  --tmpfs /tmp:rw,nosuid,size=64m \
  --memory 512m --cpus 1 \
  -v "${PWD}/wiremock:/home/wiremock:ro" \
  wiremock/wiremock@sha256:<PINNED_IMAGE_DIGEST>
```

**Đây là mẫu hướng dẫn, không phải lệnh đã chạy:** cần chuẩn bị thư mục `wiremock/mappings`, kiểm tra image tag/digest, quyền truy cập file, những đường dẫn cần ghi của đúng image và cách Docker Desktop xử lý mount path nếu dùng Windows. Một image có thể cần writable directory khác `/tmp`; khi đó cấp volume ghi tối thiểu ở đúng thư mục, không bỏ `--read-only` một cách máy móc.

### Ba điều dễ hiểu nhầm

1. `-p 127.0.0.1:8089:8080` giới hạn **host-published port** vào loopback của host, nhưng **container khác trong cùng Docker network** vẫn có thể kết nối vào **container port 8080**. Cần kiểm soát membership của network test.
2. `--network contract-test-net` là network riêng theo cấu hình bridge thông thường nhưng **không tự chặn outbound internet**. Nếu yêu cầu không egress, cần network/firewall policy tương ứng, hoặc mô hình mạng nội bộ phù hợp.
3. `--read-only` và `--cap-drop ALL` giảm đặc quyền, nhưng **không kiểm tra danh tính HTTP client** hoặc chặn Admin API qua port đã mở.

### Đừng mount Docker socket

Một mount như `/var/run/docker.sock` có thể cho container quyền điều khiển Docker daemon host, thường tương đương một đặc quyền rất lớn. Stub HTTP không cần quyền ấy để trả JSON. Không dùng `--privileged` hoặc mount toàn bộ project/host home directory chỉ để nạp vài mappings.

### Docker container làm sidecar cho consumer test

Nếu consumer test cũng chạy trong `contract-test-net`, dùng tên service/container và **container port 8080** thay vì `127.0.0.1:8089` của host:

```text
Consumer chạy trên host:
  http://127.0.0.1:8089

Consumer chạy trong container khác cùng Docker network:
  http://order-stub:8080
```

`127.0.0.1` bên trong consumer container trỏ tới **chính consumer container**, không trỏ sang WireMock container hoặc Docker host. Sai khác network namespace này là nguyên nhân phổ biến của lỗi `Connection refused`.

## 12. Kubernetes: hạn chế ingress và egress của Pod chạy stub

Với CI sử dụng Kubernetes, WireMock/Stub Runner có thể chạy trong Pod, bên cạnh Pod test consumer. Khi đó, **loopback** chỉ thích hợp nếu chúng ở **cùng Pod/network namespace**; các Pod khác muốn gọi sẽ cần một địa chỉ/Service nội bộ và listener phù hợp.

Một `NetworkPolicy` cho Pod WireMock có thể giới hạn **ingress chỉ từ consumer test Pod** và **deny egress** sau khi các mappings đã có sẵn:

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: order-stub-test-only
  namespace: contract-ci
spec:
  podSelector:
    matchLabels:
      app: order-stub
  policyTypes:
    - Ingress
    - Egress
  ingress:
    - from:
        - podSelector:
            matchLabels:
              app: checkout-contract-test
      ports:
        - protocol: TCP
          port: 8080
  egress: []
```

**Giải thích:**

- Policy chỉ áp dụng cho Pod `app=order-stub` trong namespace `contract-ci`.
- Ingress cho phép từ các Pod được chọn bởi `app=checkout-contract-test` **trong cùng namespace** tới port TCP 8080.
- `egress: []` không cấp đường outbound cho Pod được chọn; phù hợp khi stubs đã nằm trong image/volume và stub server không phải tải thêm dependencies.

**Đây là chính sách minh họa, cần kiểm tra với CNI/network plugin thực tế.** Kubernetes NetworkPolicy chỉ có hiệu lực nếu hệ thống mạng hỗ trợ enforcement; nhãn Pod không phải cơ chế xác thực người dùng. Người có quyền tạo Pod và chọn nhãn trong namespace có thể cần RBAC/namespace isolation bổ sung. Một rule ingress cho cổng WireMock cũng **không tách Admin API khỏi business API** nếu chúng dùng cùng cổng.

### Nếu Stub Runner cần tải artifact ở runtime

`egress: []` có thể làm quá trình resolve `REMOTE` stubs JAR thất bại vì không gọi được registry/DNS. Có hai cách:

1. **Download trước** trong một bước CI tin cậy, kiểm checksum và đóng gói/bind-mount vào Pod; serving Pod không cần egress.
2. Cấp **egress allowlist tối thiểu** cho DNS và artifact repository trong giai đoạn cần tải, rồi xác minh policy không mở thêm mạng ngoài.

Chọn cách nào tùy topology. Không nên tự thêm rule `to: 0.0.0.0/0` để chữa lỗi artifact resolution khi mục tiêu là hạn chế outbound. Kiểm tra thực tế **service endpoints, DNS, proxy và network policy**.

### Security context của Pod

Một Pod/container chạy mock server nên cân nhắc những thuộc tính như:

```yaml
securityContext:
  runAsNonRoot: true
  allowPrivilegeEscalation: false
  readOnlyRootFilesystem: true
  capabilities:
    drop:
      - ALL
  seccompProfile:
    type: RuntimeDefault
```

Đây là **trích đoạn container-level `securityContext`**, không phải Kubernetes Pod manifest hoàn chỉnh. `runAsNonRoot` có thể yêu cầu image có user không phải root hoặc đặt `runAsUser` phù hợp. Writable temporary volumes, resource limits, service account permissions và container image digest vẫn cần được cấu hình. Không đặt Kubernetes admin credentials trong container environment chỉ để Stub Runner đọc artifact.

## 13. Shared stub server và test isolation

Một số đội muốn một WireMock server chạy lâu, nhiều consumer jobs cùng dùng để giảm startup time. Mô hình này tăng rủi ro:

- Test A reset mappings/scenario làm test B fail ngẫu nhiên.
- Request journal lẫn dữ liệu giữa hai nhóm và dễ bị đọc chéo.
- Một mapping `priority` cao được thêm bởi test A làm test B nhận response khác.
- Artifact version cũ/mới cùng tồn tại nhưng consumer không biết server đang phục vụ cái nào.
- Nhiều người có thể gọi `/__admin` nếu cổng quản trị không được bảo vệ.

**Ưu tiên mỗi job một stub instance** (in-process, container hoặc Pod ephemeral), có port/namespace và temp directory riêng. Chỉ dùng shared stub server khi có lý do rõ và các biện pháp cô lập:

| Khía cạnh | Yêu cầu nếu chia sẻ server |
| --- | --- |
| Artifact version | Không thay mappings giữa job khi chưa có cơ chế version isolation |
| Admin API | Chỉ fixture/admin đáng tin được truy cập; consumer thường không có quyền |
| State và request journal | Không để job này đọc/reset state của job khác |
| Mạng | Chỉ những CI namespaces/groups được duyệt |
| Dữ liệu | Synthetic only; xóa/giới hạn thời gian lưu |
| Log | Có phân tách job/tenant và che dữ liệu nhạy cảm |
| Quản lý lỗi | Một test fail không được làm thay đổi test khác |

Nếu không bảo đảm được điều này, lợi ích tốc độ thường không xứng với kết quả không tái lập và rủi ro rò rỉ dữ liệu.

## 14. Bảo mật CI: quyền chạy test khác quyền publish artifact

Một pipeline producer và consumer có những trách nhiệm khác nhau:

```mermaid
flowchart LR
    A[Producer CI] -->|Verify contracts| B[Producer tests]
    B -->|Pass| C[Publish signed/versioned stubs]
    C --> D[Artifact registry]
    D -->|Read-only token| E[Consumer CI]
    E -->|Resolve exact stub| F[Ephemeral Stub Runner]
    E -->|Run client tests| F
    F --> G[Restricted logs + reports]
```

**Nên tách quyền:**

- **Producer CI**: có quyền publish vào đúng namespace artifact sau khi verification pass.
- **Consumer CI**: chỉ có quyền đọc artifact cần thiết; không có khả năng ghi đè stub producer.
- **Pull request workflow từ nguồn không tin cậy**: không được tiếp cận release secrets/production networks một cách mặc định.
- **Release job**: kiểm tra producer verification report, artifact digest, consumer tests và deployed artifact identity.

### Quy tắc tối thiểu cho GitHub Actions hoặc nền tảng tương tự

Một workflow chỉ checkout mã/test mà không cần sửa repository có thể giảm quyền token về **read**:

```yaml
permissions:
  contents: read
```

Đây là đoạn **GitHub Actions workflow-level permissions** minh họa, không đủ tự bảo vệ cả job. Với artifact repository riêng, credential cần được cấp qua secrets manager và chỉ cho phép job tin cậy. Không dùng PR từ fork để chạy Groovy contract không tin cậy trên runner có production credentials.

### Test reports cũng cần kiểm soát

Một JUnit XML report, HTTP trace, WireMock request journal hoặc attachment có thể chứa URL, header, payload và thông tin tài khoản thử nghiệm. Dùng masking/redaction, retention và quyền đọc artifacts. **Không coi upload test report là bước vô hại** nếu report có thể chứa bí mật từ request thực.

## 15. Stub Runner consumer test: kiểm tra đúng server, không chỉ response

Một consumer Spring Boot có thể dùng `@AutoConfigureStubRunner` để nạp stubs JAR đã được producer verify. Ví dụ:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.contract.stubrunner.StubRunnerProperties;
import org.springframework.cloud.contract.stubrunner.spring.AutoConfigureStubRunner;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(properties =
    "clients.orders.base-url=http://localhost:9090")
@AutoConfigureStubRunner(
    ids = "com.example:order-service:1.7.0:stubs:9090",
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
class OrderConsumerContractTest {

    @Autowired
    OrderClient orderClient;

    @Test
    void canReadOrderFromStub() {
        OrderDto result = orderClient.findById("42");
        assertThat(result.status()).isEqualTo("CONFIRMED");
    }
}
```

`OrderClient`, `OrderDto` và `clients.orders.base-url` là các kiểu/property của **ứng dụng minh họa**, không phải API được Stub Runner tự tạo. Bài test có ý nghĩa khi:

1. `1.7.0:stubs` đã được producer verification kiểm chứng và cài vào local repository của **đúng test job**.
2. Stub Runner thực sự nạp WireMock mapping cho `GET /api/orders/42`.
3. HTTP client thật của consumer gọi đúng server/port `9090`.
4. Assertions kiểm tra kết quả và nhánh lỗi cần thiết.
5. Mạng của stub chỉ tiếp cận những tiến trình test được phép.

**Điểm giới hạn:** `@AutoConfigureStubRunner` không phải công cụ cấu hình Kubernetes firewall, Docker capability, OAuth2 policy hay hệ thống phân quyền OS. Những chính sách bảo mật này phải được thực thi ở môi trường chạy stub, ngoài annotation.

### Kiểm tra security contract với hai lớp riêng

| Lớp | Bài test cụ thể | Kết luận hợp lệ |
| --- | --- | --- |
| Consumer + stub | Client xử lý `401 UNAUTHENTICATED` và `403 FORBIDDEN` | Client hiểu response lỗi mô phỏng |
| Producer + verifier | Producer implementation trả response theo contract | HTTP/security behavior trong **phạm vi base class** đã chạy |
| Security integration | JWT validation, permissions, resource ownership, gateway/filter | Quy tắc xác thực/ủy quyền thật đã được kiểm tra |
| Infrastructure policy | Pod/firewall/container chặn caller hoặc egress không cho phép | Ranh giới **mạng và đặc quyền** có hiệu lực |

Kết quả bốn lớp bổ sung nhau. Không dùng một test `401` trong WireMock để khẳng định Kubernetes NetworkPolicy đang an toàn hoặc token issuer thật được xác minh.

## 16. Cách kiểm tra ranh giới mạng và quyền bằng các phép thử

**Định nghĩa trước** những luồng được phép:

| Tác nhân | Đích | Cho phép? | Bằng chứng |
| --- | --- | --- | --- |
| Consumer test trong cùng job | `GET /api/orders/42` | **Có** | Nhận response đúng stub |
| Máy/Pod khác không nằm trong test scope | Port stub | **Không** | Connection bị từ chối/timeout theo policy |
| Consumer test thông thường | `/__admin` qua đường mạng của consumer | **Không** | Bị chặn trước khi tới WireMock |
| Stub serving static mappings | Internet/production API | **Không** | Egress test/log firewall |
| Consumer CI | Artifact registry read endpoint | **Có** nếu được phép | Resolve artifact đúng digest |
| Consumer CI | Artifact registry publish endpoint | **Không** | Quyền upload bị từ chối |
| Stub process | Production secrets files | **Không** | Quyền OS, mount và service-account scope |

### Kiểm tra listener trên máy test

Sau khi khởi động WireMock standalone được cấu hình bind loopback:

```bash
# Linux: xem process/listener thực tế.
ss -lnt

# Kiểm thử endpoint mock hợp lệ trên chính máy được phép.
curl -i --max-time 3 http://127.0.0.1:8089/api/orders/42
```

Trên Windows PowerShell, có thể kiểm tra:

```powershell
Get-NetTCPConnection -LocalPort 8089 -State Listen
```

Quan sát **LocalAddress**; nếu đang là `0.0.0.0` thay vì `127.0.0.1`, cần xem lại bind address và firewall. Với IPv6, kiểm tra listener tương ứng. **Lệnh xem cổng không chứng minh firewall hay container network đã bị chặn**.

### Negative network test

Trong **môi trường do nhóm sở hữu và được phép kiểm tra**, từ một máy/Pod không được cấp quyền, thử kết nối vào **địa chỉ test host/Service đã biết**. Kết quả kỳ vọng là không kết nối được theo network policy. Không thực hiện scan tùy tiện mạng doanh nghiệp hoặc endpoint không thuộc quyền quản lý.

Nếu dùng Kubernetes, tạo một **Pod kiểm thử từ namespace hoặc nhãn không được phép** và kiểm tra nó không thể gọi Service WireMock, trong khi Pod consumer được cấp quyền vẫn gọi được. Cần xác minh CNI có hỗ trợ NetworkPolicy và xem cả ingress/egress trong trường hợp topology có nhiều thành phần.

### Kiểm tra quyền tệp và process

Trong container/Pod test:

- Xem user ID/UID thực tế và group, đảm bảo không chạy root nếu không có ngoại lệ được duyệt.
- Xem mounted volumes: chỉ có mapping/config, không có Docker socket, host home directory hoặc secret mount không cần thiết.
- Xem capability/securityContext và writable directories.
- Kiểm tra process có cần egress không; nếu phục vụ static mappings, cắt egress và chạy smoke test.
- Xác minh container/job bị dừng và tài nguyên tạm được thu dọn sau test.

**Không nên dùng việc cố đọc một production credential làm “bài kiểm tra bảo mật”**. Dùng tệp canary giả trong môi trường sandbox hoặc policy review để xác minh filesystem boundary.

## 17. Security smoke test trong CI: kiểm tra policy, không chỉ chức năng

Một quality gate có thể chạy những thử nghiệm tối thiểu:

```mermaid
flowchart TD
    A[CI tạo isolated test environment] --> B[Resolve exact verified stub]
    B --> C[Kiểm SHA-256 + quyền registry]
    C --> D[Khởi động stub non-root, restricted network]
    D --> E{Consumer hợp lệ gọi được mock?}
    E -->|Không| X[Fail: network/port/config]
    E -->|Có| F{Caller không được phép bị chặn?}
    F -->|Không| Y[Fail: ingress isolation]
    F -->|Có| G{Admin API không lộ qua đường consumer?}
    G -->|Không| Z[Fail: admin exposure]
    G -->|Có| H{Không outbound ngoài allowlist?}
    H -->|Không| Q[Fail: egress leakage]
    H -->|Có| I[Chạy consumer assertions]
    I --> J[Redact logs, thu hồi tài nguyên]
```

### Một checklist smoke test thực tế

1. **Trước startup:** Kiểm tra artifact digest, image version, namespace/ports/volumes/secrets.
2. **Sau startup:** Xác nhận process chạy dưới UID dự kiến, listener ở địa chỉ đúng.
3. **Positive ingress:** Consumer được phép gọi stub thành công với request mẫu.
4. **Negative ingress:** Caller không thuộc network/test scope bị chặn.
5. **Admin:** Consumer network không thể quản trị mappings; fixture/setup đáng tin vẫn có cách reset nếu cần.
6. **Egress:** Serving process không đến được production/internal resources không nằm trong allowlist.
7. **Secrets/logging:** Token giả không bị đưa vào public test reports; không phát sinh credential production.
8. **Teardown:** Stub server/port, namespace, temporary volumes và test data được thu dọn.

Đây không phải một bộ security scanning tự động có sẵn của Spring Cloud Contract; nhóm phải thiết kế job checks theo Docker/Kubernetes/firewall/runtime thực tế. **Nếu chính sách mạng khiến test hợp lệ không chạy**, đó là lỗi configuration cần sửa ở allowlist cần thiết; không nên mở toàn bộ mạng làm biện pháp tạm rồi để nguyên.

### Phân biệt lỗi của chức năng và lỗi của policy

| Kết quả | Giải thích có thể | Điều cần làm |
| --- | --- | --- |
| Consumer gọi mock thất bại | Port sai, firewall quá hẹp, Stub Runner chưa nạp mapping | Xem listener/port và request path |
| Caller không được phép vẫn gọi được | Bind/network policy/Service exposure quá rộng | Xem firewall, NetworkPolicy, host-published port |
| Consumer gọi `/__admin` được | Admin exposure | Chặn đường direct access hoặc dùng proxy/auth phù hợp |
| Stub static mapping vẫn truy cập internet | Egress chưa bị giới hạn | Đánh giá CNI/firewall/bridge network |
| Test auth 401 pass nhưng JWT test thật fail | Stub chỉ mô phỏng status | Bổ sung/fix security integration tests |
| Test pipeline báo PASS nhưng không có policy checks | Chưa có bằng chứng hạ tầng | Đánh dấu security scope chưa được xác minh |

## 18. Một trường hợp lỗi thực tế: stub vô tình mở cho cả LAN

### Triệu chứng

Developer chạy WireMock server trên máy CI với listener `0.0.0.0:9090`. Consumer tests chạy thành công, nhưng một máy khác trên mạng nội bộ cũng truy cập được `http://ci-host:9090/__admin/mappings`.

Nếu Admin API còn bật và không có lớp bảo vệ phù hợp, máy khác có thể xem/đổi mappings hoặc request journal. Đây là lỗi **exposure của hạ tầng test**, không phải lỗi Spring Cloud Contract Groovy DSL.

### Phân tích nguyên nhân

1. **Bind address:** server nghe trên mọi giao diện của network namespace.
2. **Firewall:** cổng `9090` không giới hạn caller.
3. **Admin API:** dùng chung listener với business stub endpoints.
4. **CI lifecycle:** server còn chạy sau job thay vì được teardown.
5. **Dữ liệu:** request journal có thể giữ header/token giả hoặc dữ liệu không được phép lưu.

### Cách khắc phục theo phạm vi

- Nếu consumer chạy **cùng host**: bind loopback và chặn inbound ngoài host.
- Nếu consumer ở **container/Pod khác**: dùng network/namespace riêng, ingress allowlist và kiểm tra admin không lộ qua network consumer.
- Nếu **bắt buộc dùng server chia sẻ**: reverse proxy có auth và chặn `/__admin` cho caller thường; chặn mọi đường bypass trực tiếp.
- Cấp credentials registry read-only, tránh lưu tokens trong request journal và hạn chế log retention.
- Đưa lệnh teardown/quota/timeout và negative network test vào pipeline.

**Kết luận của ca:** Việc HTTP contract test trả đúng `200` chưa cung cấp bằng chứng nào rằng mạng và quyền của stub đã được giới hạn. Chỉ **network/policy tests** mới có thể xác nhận ranh giới ấy.

## 19. Bài thực hành: cô lập stub của order-service

### Bối cảnh

`checkout-service` có consumer test đọc đơn hàng từ `order-service`. Producer đã verify hợp đồng và phát hành `com.example:order-service:1.7.0:stubs`. Nhóm muốn thực hành hai cấu hình:

1. **Development:** WireMock standalone và consumer client chạy trên cùng máy, không cho máy khác truy cập.
2. **CI:** Consumer test Pod và WireMock Pod nằm trong namespace `contract-ci`, chỉ các Pod có nhãn được phép gọi stub, stub phục vụ **static mappings** và không cần outbound.

Mục tiêu không phải kiểm thử hệ thống production thật. Tất cả URL, token và dữ liệu là **synthetic**, và chỉ thực hiện những phép thử mạng trong môi trường sandbox do nhóm quản lý.

### Phần A — Xây contract HTTP có hành vi rõ ràng

Một Groovy DSL nguồn dành cho producer:

```groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Tra cứu đơn hàng đã xác nhận'

    request {
        method GET()
        url '/api/orders/42'
        headers {
            accept(applicationJson())
        }
    }

    response {
        status OK()
        headers {
            contentType(applicationJson())
        }
        body([
            orderId: 'ord-42',
            status: 'CONFIRMED'
        ])
    }
}
```

Contract này bảo vệ response HTTP mẫu; **không tự bảo vệ API authentication**, bởi nó không khai báo/kiểm tra token hay security filter. Nếu endpoint thật yêu cầu đăng nhập, khi triển khai producer verification phải cấu hình request/base class để tái hiện đúng policy hoặc bổ sung security-focused contracts/tests riêng.

### Phần B — Dùng WireMock mapping cho nhánh 401

Để tránh nhầm 404 unmatched với 401 nghiệp vụ, một mapping WireMock **được thiết kế riêng cho bài lab** có thể mô tả trường hợp **thiếu `Authorization`**:

```json
{
  "name": "Unauthenticated read order",
  "request": {
    "method": "GET",
    "urlPath": "/api/orders/42",
    "headers": {
      "Authorization": {"absent": true}
    }
  },
  "response": {
    "status": 401,
    "headers": {
      "Content-Type": "application/json"
    },
    "jsonBody": {
      "code": "UNAUTHENTICATED"
    }
  }
}
```

**Đây là mapping WireMock minh họa, không phải output tự động từ Groovy contract ở phần A.** Nếu hai mapping cùng `GET /api/orders/42` đang có ở server và một mapping thành công không ràng buộc Authorization, cần sửa contract/mappings để tránh cạnh tranh. Trong luồng Spring Cloud Contract chính thức, nên đưa trường hợp 401 vào **contract nguồn** và chạy producer verification, thay vì chỉ giữ một mapping viết tay rồi cho rằng producer đã thực thi 401.

### Phần C — Kiểm tra mạng trên máy local

1. Khởi động mock server trên **loopback** bằng cấu hình hỗ trợ của WireMock standalone đang dùng.
2. Xác nhận socket chỉ listen trên `127.0.0.1` (hoặc loopback IPv6 đã chọn).
3. Gọi stub qua client/test được phép; xác nhận response thuộc **mapping đã nạp**.
4. Dùng một caller trong sandbox nhưng **không cùng host/network namespace** để xác nhận không thể truy cập địa chỉ mạng của máy test trên port đó.
5. Đọc `/__admin/requests` **chỉ trên máy có quyền quản trị**, quan sát dữ liệu test được journal ghi và xác minh không có credentials thật.
6. Dừng tiến trình, kiểm tra cổng đã được đóng và file/log không tồn tại lâu hơn retention policy.

**Điểm tự kiểm tra:** Loopback hạn chế inbound từ bên ngoài namespace, nhưng **không tự ẩn `/__admin` khỏi một tiến trình khác chạy cùng máy**. Vì vậy không chạy mã không tin cậy cùng tài khoản/namespace với stub nếu cần cô lập nghiêm ngặt.

### Phần D — Giới hạn Docker/container

Sử dụng mô hình `--read-only`, `--cap-drop ALL`, `--security-opt no-new-privileges`, port host loopback và mappings volume read-only như mục 11. Sau đó tự trả lời:

- Image có đang chạy non-root không, hay cần build image phù hợp?
- Runtime có chỉ ghi vào writable temp volume đã cấp không?
- Container có mount Docker socket/host secrets không?
- Nếu consumer cũng là container, nó phải gọi `order-stub:8080` hay `127.0.0.1:8089`?
- Stub server có thể kết nối mạng ngoài hay không? **Đừng suy ra từ `--network contract-test-net`.**

Đây là các câu hỏi buộc người học **kiểm tra runtime thật**, không chỉ đọc cấu hình Docker rồi tự đánh dấu PASS.

### Phần E — NetworkPolicy trong CI

1. Áp dụng chính sách Kubernetes ở mục 12 lên Pod `app=order-stub`.
2. Tạo một consumer Pod hợp lệ `app=checkout-contract-test` trong namespace phù hợp; xác minh nó gọi được port 8080.
3. Tạo một Pod không thuộc tập cho phép trong sandbox; xác minh nó **không thể** gọi stub.
4. Kiểm tra `egress: []` không chặn tác vụ không liên quan trước startup; preload stubs nếu cần.
5. Xác minh test Pod, không chỉ WireMock Pod, cũng không có quyền truy cập không cần tới production/internal services.
6. Ghi lại CNI/plugin và những policy áp dụng trong CI report.

Để loại bỏ tác động của network policy khi debug, chỉ sửa **allowlist tối thiểu** và hoàn nguyên theo review. Không xóa toàn bộ policy rồi coi test đã xác minh thành công.

### Phần F — Kết quả mong đợi

| Thử nghiệm | Kết quả cần chứng minh |
| --- | --- |
| Consumer hợp lệ gọi HTTP stub | Được phản hồi theo contract đã nạp |
| Caller ngoài scope gọi host port local-only | Bị ngăn trước khi tới server |
| Caller thường gọi WireMock Admin API qua đường public/shared | Bị chặn |
| Test với token synthetic | Không làm lộ credential production |
| WireMock serving static mappings thử outbound ngoài allowlist | Không được phép |
| Container process đọc host secrets giả ngoài volume được cấp | Không có quyền theo policy |
| CI sử dụng artifact `1.7.0:stubs` | Version/digest đúng producer đã verify |
| Stub trả 401 giả lập | Consumer xử lý đúng mã lỗi, **không coi là JWT validation thật** |
| Sau teardown | Port/Pod/temp state được thu hồi |

## 20. Bảng chẩn đoán sự cố bảo mật của stub

| Triệu chứng | Nguyên nhân khả dĩ | Điều tra và khắc phục |
| --- | --- | --- |
| Máy khác truy cập được stub trên LAN | Bind `0.0.0.0` hoặc port publish/firewall quá rộng | Kiểm tra listener, host firewall, Pod Service/ingress |
| Business API bị chặn nhưng `/__admin` vẫn mở | Chỉ lọc route nghiệp vụ, không giới hạn đường admin | Chặn admin và đường bypass trực tiếp |
| WireMock request journal có token thật | Consumer CI dùng credential thật hoặc log chưa redact | Thu hồi token theo policy, sửa test fixture, hạn chế retention |
| CI không resolve REMOTE artifact sau khi deny egress | Registry/DNS chưa có allowlist hoặc cần preload | Tách download trước serving; allowlist đúng nguồn |
| Stub server phản hồi dữ liệu production | Proxy mapping hoặc client trỏ nhầm backend thật | Kiểm tra request destinations, mappings, egress và credentials |
| Container không start sau `--read-only` | Runtime cần thư mục ghi | Cấp writable temp volume tối thiểu |
| Container vẫn chạy root | Image user/securityContext chưa phù hợp | Dùng non-root image, UID và quyền volume đúng |
| NetworkPolicy đã khai báo nhưng caller ngoài scope vẫn gọi được | CNI không enforce, selector sai hoặc có bypass | Kiểm tra enforcement, labels, Service/hostNetwork paths |
| Test chạy ở host pass, trong Docker báo connection refused | Dùng nhầm `localhost` giữa network namespaces | Dùng container DNS name/port hoặc cùng Pod namespace |
| Hai consumer jobs làm thay đổi cùng mapping | Shared stub server và Admin API chung | Chạy ephemeral instances hoặc phân tách jobs |
| Consumer 401 test pass dù producer chưa có security | WireMock mô phỏng status; producer filter chưa được test | Chạy producer/security integration tests |
| Consumer vẫn dùng stub cũ nhưng không phát hiện | Artifact cache/version không đúng | Pin coordinates, kiểm digest, cô lập local repo |
| Plugin/extension yêu cầu quyền ghi hoặc outbound rộng | Custom extension không phù hợp least privilege | Review hoặc loại extension, cấp quyền cụ thể nếu cần |
| CI log phơi bày registry credential | In URL/token trong debug | Redact, xoay credential, giảm quyền token |

### Trình tự điều tra an toàn

```text
1. Xác định process/Pod/container nào đang phục vụ stub.
2. Xác định listener, host-published port và các đường mạng đi vào.
3. Kiểm tra truy cập tới /__admin và quyền của client bình thường.
4. Kiểm tra request journal, logs và fixture có dữ liệu nhạy cảm không.
5. Xác định outbound destinations và artifact registry identity.
6. Đọc UID, capabilities, mounts, securityContext và service account.
7. Xác nhận artifact version/digest và contract verification provenance.
8. Thực hiện negative policy tests trong sandbox được cấp quyền.
9. Sửa root cause, chạy lại consumer + security smoke tests.
10. Thu hồi/rotate credentials nếu phát hiện secret exposure.
```

**Khi có dấu hiệu lộ bí mật thật, ưu tiên xử lý theo quy trình incident response của tổ chức.** Việc xóa request journal cục bộ có thể không thu hồi được bản sao đã ghi vào CI logs hoặc artifacts.

## 21. Checklist trước khi cho tiến trình stub chạy trong CI

### Ranh giới mạng

- [ ] Biết consumer và stub chạy **cùng process, cùng host, cùng Docker network hay khác Kubernetes Pod**.
- [ ] Địa chỉ bind và port được kiểm tra thực tế, không chỉ suy từ cấu hình.
- [ ] Nếu test cùng host, ưu tiên loopback; nếu khác host/Pod, dùng ingress allowlist tối thiểu.
- [ ] Không publish WireMock port ra public internet hoặc LAN khi không có yêu cầu được phê duyệt.
- [ ] Nếu nghiệp vụ và `/__admin` dùng cùng cổng, đường mạng của consumer **không cho phép** truy cập admin ngoài ý định.
- [ ] Đã kiểm tra không có đường bypass trực tiếp qua host port/Pod IP/Service.
- [ ] Có negative ingress test từ một caller không được cấp quyền.
- [ ] Có kiểm tra egress để mock server không vô tình proxy hoặc gọi production/internal resources.
- [ ] Với Kubernetes, CNI thực sự hỗ trợ NetworkPolicy; nhãn Pod, RBAC và namespace được kiểm soát.
- [ ] Với Docker, hiểu khác biệt giữa host loopback và container network; network test không được coi là firewall outbound.

### Đặc quyền tiến trình và container

- [ ] Stub server chạy dưới identity không phải root/admin nếu có thể.
- [ ] Không cấp `--privileged`, Docker socket, hostNetwork hoặc service-account token quyền rộng khi không cần.
- [ ] Mappings và response files được mount read-only nếu không cần cập nhật runtime.
- [ ] Root filesystem read-only hoặc writable paths được giới hạn theo nhu cầu thực.
- [ ] Linux capabilities được giảm; privilege escalation bị ngăn trong runtime hỗ trợ.
- [ ] CPU/RAM, log retention, port lifecycle và teardown được cấu hình phù hợp.
- [ ] Không chia sẻ stub instance/request journal giữa những jobs không tin cậy.

### Nguồn artifact và dữ liệu

- [ ] Stubs JAR đến từ **producer contract source** đã xác định và producer verification đã chạy/pass.
- [ ] Consumer CI tải đúng `group:artifact:version:stubs` và kiểm checksum/provenance.
- [ ] Registry token của consumer chỉ có quyền đọc; quyền publish thuộc producer CI.
- [ ] Không dùng mutable `latest`/SNAPSHOT không kiểm soát để quyết định release.
- [ ] Không chạy Groovy contracts, custom WireMock extensions hoặc build scripts không tin cậy trong runner có secrets rộng.
- [ ] Chỉ dùng test credentials và synthetic fixture data, không copy dữ liệu production.
- [ ] Request journal và CI artifacts được redact, giới hạn truy cập và retention.
- [ ] Nếu có proxy/response templating, đã review endpoint outbound và khả năng làm lộ headers/body.

### Bằng chứng kiểm thử

- [ ] Consumer client/listener thực sự gọi **đúng stub server** và assert những response/message cần thiết.
- [ ] Contract về `401`/`403` không được hiểu nhầm là JWT/OAuth/security verification đầy đủ.
- [ ] Producer contract test đi qua đường triển khai đúng phạm vi; security integration tests có mặt khi cần.
- [ ] Smoke test hợp lệ kết nối được, smoke test ngoài scope **bị chặn**, Admin API không lộ.
- [ ] CI fail hoặc báo `INCOMPLETE` nếu thiếu artifact, digest, test results hoặc policy tests bắt buộc.
- [ ] Báo cáo phân biệt **chất lượng giao diện hợp đồng** với **bảo mật hạ tầng test**.
- [ ] Sau khi kết thúc job, tiến trình/port, container/Pod, temp files và test state được thu hồi.

## 22. Kết luận và hướng đọc tiếp

Một tiến trình Stub Runner/WireMock có thể rất đơn giản về chức năng nhưng vẫn có nhiều bề mặt rủi ro. Cần giữ **bốn ranh giới độc lập**:

| Ranh giới | Câu hỏi phải trả lời |
| --- | --- |
| **Mạng** | Ai có thể kết nối tới stub và Admin API? Stub có thể gọi đi đâu? |
| **Quyền OS/container** | Tiến trình đọc/ghi được gì, có quyền root, host socket hoặc service account không? |
| **Nguồn artifact và dữ liệu** | Stub/extension có đáng tin? Có mang secrets hoặc response thật vào test không? |
| **Phạm vi bằng chứng** | Test chỉ mô phỏng `401` hay đã kiểm tra authentication/authorization thật? |

Về thực hành, ưu tiên mô hình **mỗi consumer test job một stub instance ngắn hạn**, nạp **stubs artifact đúng version và checksum**, giới hạn mạng trong scope job, không public Admin API, chạy non-root với filesystem tối thiểu, dùng synthetic data và dọn tài nguyên ngay sau test.

Tài liệu chính thức để đối chiếu theo phiên bản:

- [Spring Cloud Contract Reference](https://docs.spring.io/spring-cloud-contract/reference/) — Contract Verifier, Stub Runner, nguồn hợp đồng, cách nạp stubs và cấu hình test.
- [WireMock Documentation](https://wiremock.org/docs/) — standalone/server configuration, request matching, Admin API, request journal và proxying.
- [Kubernetes NetworkPolicy](https://kubernetes.io/docs/concepts/services-networking/network-policies/) — ingress/egress selectors và yêu cầu CNI enforcement.
- [Docker Networking](https://docs.docker.com/engine/network/) — network namespaces, bridge networks và published ports.

Các ví dụ CLI, Docker, Kubernetes và Java trong bài phải được đối chiếu với **phiên bản thực tế, cấu hình mạng và security policy** của dự án. Không thay một chính sách an toàn bằng việc copy lệnh mẫu mà chưa kiểm tra kết quả thực thi.

**Ghi nhớ:** Spring Cloud Contract giúp **xác minh hợp đồng producer–consumer**; WireMock/Stub Runner giúp **mô phỏng giao diện**. Chúng **không tự cách ly network, không phân quyền Admin API, không bảo vệ secrets và không thay thế kiểm thử security thật**. Để mock server an toàn trong CI, cần thực thi **least privilege, giới hạn ingress/egress, quản lý artifact đáng tin và kiểm tra ranh giới bằng positive/negative tests**. Một consumer test xanh chỉ có giá trị khi nó vừa sử dụng đúng stub, vừa không tạo ra một tiến trình kiểm thử có quyền hoặc khả năng truy cập vượt quá phạm vi cần thiết.
