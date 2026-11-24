# Xử lý hợp đồng không hợp lệ và trường hợp không có hợp đồng

## 1. Vì sao “build xanh” chưa đủ để tin Contract Verifier?

**Spring Cloud Contract (SCC)** cho phép producer và consumer mô tả cách giao tiếp qua HTTP hoặc message bằng **Groovy DSL** hoặc **YAML DSL**. Trong hướng tiếp cận producer-side verification, **Contract Verifier** đọc hợp đồng, sinh test với những request/response đã cam kết và thực thi chúng với code producer. Từ cùng hợp đồng, công cụ còn có thể tạo **stub** để consumer kiểm tra qua **Stub Runner**. Trong CI, chuỗi đó giúp phát hiện API thay đổi không tương thích.

Tuy nhiên, có những tình huống mà kết quả build dễ gây hiểu lầm:

- Contract **sai cú pháp** khiến quá trình đọc/generate bị lỗi.
- Contract parse được nhưng **thiếu trường bắt buộc** hoặc dùng DSL không hợp lệ.
- Contract hợp lệ nhưng **generated test không biên dịch** do cấu hình test base sai.
- Generated test chạy và đỏ vì **producer không đáp ứng hợp đồng**.
- **Không có contract nào được phát hiện**, hoặc plugin/task không chạy: build có thể vẫn xanh tùy phiên bản và cấu hình, nhưng không có hành vi giao tiếp nào được kiểm chứng.
- Stub được đóng gói nhưng **không mang hợp đồng mới**, khiến test consumer chạy với bản cũ hoặc mapping rỗng.

Bài này tập trung vào hai nhóm sự cố dễ bị bỏ sót: **hợp đồng không hợp lệ** và **không có hợp đồng**. Mục tiêu là chẩn đoán được nguyên nhân, khôi phục việc kiểm thử và đưa quy tắc **fail fast / fail closed** phù hợp vào pipeline.

### Kết quả học tập

Sau bài học, bạn có thể:

1. Phân biệt lỗi **parse**, lỗi **DSL/schema**, lỗi **generate/compile**, lỗi **verification** và tình huống **zero contracts**.
2. Kiểm tra một hợp đồng HTTP Groovy/YAML tối thiểu, nhận diện các lỗi thường gặp và biết sửa ở tầng nào.
3. Xác định khi nào dự án **có chủ đích không có contract**, khi nào **không tìm thấy contract** là lỗi cấu hình.
4. Thiết kế cổng CI xác nhận **contract được tìm thấy → test được sinh → test được chạy → stub đúng phiên bản**.
5. Phân biệt lỗi producer verification với lỗi consumer Stub Runner, tránh sửa sai hoặc “làm xanh” giả bằng cách skip test.
6. Ghi lại bằng chứng đủ để nhóm phát hiện thay đổi API không tương thích trước khi phát hành.

## 2. Tư duy chẩn đoán theo các cổng kiểm chứng

~~~mermaid
flowchart TD
    A["Có kỳ vọng module này chứa contract?"] --> B{"Có contract source được phát hiện?"}
    B -- "Không" --> C{"Module cố ý chưa có contract?"}
    C -- "Không" --> X["BLOCK: sửa vị trí/cấu hình/discovery"]
    C -- "Có" --> Y["Áp dụng chính sách no-contract đã được phê duyệt"]
    B -- "Có" --> D{"DSL parse và validate được?"}
    D -- "Không" --> E["BLOCK: sửa cú pháp, field, tài nguyên"]
    D -- "Có" --> F{"Generated test compile và được chạy?"}
    F -- "Không" --> G["BLOCK: sửa base test, framework, task/lifecycle"]
    F -- "Có" --> H{"Producer đáp ứng assertion?"}
    H -- "Không" --> I["BLOCK: xử lý code, contract hoặc data lệch"]
    H -- "Có" --> J{"Stub ứng viên đúng contract/commit?"}
    J -- "Không" --> K["BLOCK: sửa packaging/publication"]
    J -- "Có" --> L["Consumer chạy với stub ứng viên"]
    L --> M{"Consumer test đạt?"}
    M -- "Không" --> N["BLOCK: phối hợp thay đổi tương thích/migration"]
    M -- "Có" --> O["Qua cổng tương thích; tiếp tục release checks"]
~~~

Không nên đọc toàn bộ lỗi như “Contract Verifier hỏng”. Mỗi nhánh có **dấu hiệu, người sửa và cách khôi phục khác nhau**.

| Tầng lỗi | Thời điểm thường xảy ra | Điều cần xem |
|---|---|---|
| **Discovery** | Plugin quét đường dẫn hợp đồng | Thư mục, file extension, config, log số hợp đồng |
| **Parsing** | Đọc Groovy/YAML | Thông báo syntax, dòng/cột lỗi |
| **Validation/DSL** | Chuyển DSL thành mô hình contract | Field hợp lệ, request/response, matcher, fixture |
| **Generation/compilation** | Sinh/compile test | Generated Java, base class, imports, test mode |
| **Execution/verification** | Chạy test với producer | HTTP response/message thật so với kỳ vọng |
| **Stub packaging** | Đóng gói artifact | Mapping và body file có trong stub JAR không |
| **Consumer** | Stub Runner và client test | Đúng artifact, mapping, hành vi client thật |

## 3. Hợp đồng HTTP hợp lệ tối thiểu để đối chiếu

Ví dụ **Inventory Service** có endpoint trả tồn kho:

~~~http
GET /api/inventory/SKU-123 HTTP/1.1
Accept: application/json
~~~

Response đã cam kết:

~~~json
{
  "sku": "SKU-123",
  "available": true,
  "quantity": 12
}
~~~

Trong dự án producer đã tích hợp SCC, có thể đặt contract tại vị trí convention, ví dụ:

~~~text
src/test/resources/contracts/inventory/get-stock.groovy
~~~

Nội dung Groovy DSL:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Trả tồn kho cho Checkout Service'

    request {
        method GET()
        url '/api/inventory/SKU-123'
    }

    response {
        status OK()
        headers {
            contentType(applicationJson())
        }
        body(
            sku: 'SKU-123',
            available: true,
            quantity: 12
        )
    }
}
~~~

Nếu chọn YAML DSL, tạo **một** contract tương đương thay cho tệp Groovy, ví dụ `get-stock.yml`:

~~~yaml
description: Trả tồn kho cho Checkout Service
name: get_stock

request:
  method: GET
  url: /api/inventory/SKU-123

response:
  status: 200
  headers:
    Content-Type: application/json
  body:
    sku: SKU-123
    available: true
    quantity: 12
~~~

**Lưu ý:** Hai đoạn trên là **hai lựa chọn**, không cần tạo cả hai contract trùng tình huống trong project. Plugin phải được cấu hình để đọc đúng thư mục và định dạng đang dùng. Một project không tích hợp plugin SCC thì đặt file ở đây **chưa đủ** để sinh test.

Hợp đồng hợp lệ ở bước này có nghĩa là: mô tả có thể được xử lý và mang kỳ vọng cụ thể. Nó **chưa chứng minh** controller producer đã tồn tại hoặc trả dữ liệu đúng; cần generated test để kiểm chứng điều đó.

## 4. Nhóm lỗi A — Groovy DSL không parse được

Ví dụ sai:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    request {
        method GET()
        url '/api/inventory/SKU-123'
    }
    response {
        status OK()
        body(
            sku: 'SKU-123',
            available: true
        )
    // Thiếu dấu đóng của response và Contract.make
~~~

Khi trình xử lý Groovy không thể phân tích cú pháp, Contract Verifier không thể xây dựng đầy đủ mô hình contract. Log thường có thông tin dòng/cột liên quan đến dấu ngoặc hoặc cú pháp.

Một số lỗi phổ biến:

- Thiếu `}` hoặc `)`; đặt body/matcher ra ngoài closure đúng.
- Viết sai tên hàm DSL, ví dụ method không tồn tại hoặc sử dụng sai cú pháp.
- Dùng quy tắc của YAML trong Groovy mà không chuyển đổi đúng kiểu DSL.
- Thêm mã Groovy phụ thuộc thư viện hoặc biến không có trong classpath dùng để đánh giá contract.
- Chèn phần xử lý phức tạp vào contract, khiến người đọc không còn thấy rõ cam kết giao tiếp.

Cách xử lý: xem **thông báo lỗi đầu tiên có vị trí trong source**, xác nhận dấu ngoặc và API DSL, chạy lại generation trên đúng file. Đừng sửa controller hoặc nới assertion nếu quá trình **chưa tạo được test**.

## 5. Nhóm lỗi B — YAML parse lỗi hoặc parse được nhưng sai schema

YAML đặc biệt nhạy với **thụt lề** và cách suy kiểu.

### 5.1. Sai cấu trúc thụt lề

~~~yaml
# SAI: method không nằm trong request như dự kiến
request:
method: GET
  url: /api/inventory/SKU-123
response:
  status: 200
~~~

Sửa bằng cách đưa các field thuộc cùng khối về đúng mức:

~~~yaml
request:
  method: GET
  url: /api/inventory/SKU-123
response:
  status: 200
~~~

### 5.2. YAML hợp lệ nhưng không phải hợp đồng SCC hợp lệ

~~~yaml
# YAML parser có thể đọc được, nhưng tên nhánh bị viết sai:
request:
  method: GET
  endpoint: /api/inventory/SKU-123
response:
  code: 200
~~~

`endpoint` và `code` không thể tùy tiện thay cho `url` và `status` theo schema contract HTTP mong muốn. Công cụ có thể từ chối, bỏ qua phần không hiểu hoặc sinh ra mô hình không mong muốn tùy phiên bản/đường xử lý. Vì vậy:

- **YAML parse thành công ≠ contract hợp lệ.**
- **Contract hợp lệ về schema ≠ hành vi producer đúng.**
- **Build exit 0 ≠ generated test đã thực thi.**

Một dạng sai khác là `request`/`response` đặt nhầm cấp, `matchers` nằm ngoài khối cần kiểm tra, `bodyFromFile` trỏ tệp không tồn tại, hoặc YAML được lưu với extension không được plugin quét.

### 5.3. Sai kiểu dữ liệu do YAML tự suy

~~~yaml
response:
  status: "200"   # Chuỗi, không phải số nguyên mong muốn trong schema
  body:
    available: "true"  # Chuỗi, không phải JSON boolean true
    quantity: "12"     # Chuỗi, không phải JSON number 12
~~~

Contract có thể tạo kỳ vọng **sai về kiểu** nếu không được phát hiện sớm. Với response đã cam kết `available` là boolean và `quantity` là number, hãy dùng:

~~~yaml
response:
  status: 200
  body:
    available: true
    quantity: 12
~~~

Những giá trị thực chất là **chuỗi** nhưng nhìn giống number/boolean nên đặt trong dấu nháy; ngược lại, không quote những giá trị thuộc kiểu JSON number/boolean.

## 6. Nhóm lỗi C — Thiếu trường, matcher hoặc body resource

Một hợp đồng HTTP cần đủ thông tin cho tình huống được mô tả. Những rủi ro thường gặp:

| Dấu hiệu | Nguyên nhân tiềm năng | Hướng giải quyết |
|---|---|---|
| Không tạo được request xác định | Thiếu method hoặc URL/path cần thiết | Bổ sung `request.method` và `url`/`urlPath` |
| Test không xác nhận status mong muốn | `response.status` không được mô tả hoặc sai vị trí | Khai báo status theo DSL được hỗ trợ |
| Trường body quan trọng không được kiểm tra | Body/matcher quá rộng hoặc JSONPath sai | Bổ sung field cần thiết và kiểm tra generated assertion |
| Không tìm được fixture | `bodyFromFile`/`file(...)` trỏ sai đường dẫn | Đặt file gần contract, kiểm tra đường dẫn tương đối thực tế |
| Sinh test gặp lỗi khi dùng matcher | Matcher sai phía/sai tên type hoặc `path` trỏ field không tồn tại | Dùng cú pháp đúng của Groovy/YAML và kiểm tra test sinh ra |
| Stub chứa body cũ | Fixture đổi nhưng không được nạp/đóng gói lại | Tạo artifact mới, kiểm tra mapping và body file |
| Hai tình huống cùng match một request | Các matcher body/header/query quá lỏng | Thu hẹp điều kiện, thêm test âm tính trên stub |

Ví dụ YAML tham chiếu file không có trong thư mục tài nguyên:

~~~yaml
request:
  method: GET
  url: /api/inventory/SKU-123
response:
  status: 200
  headers:
    Content-Type: application/json
  bodyFromFile: payloads/missing-stock.json
~~~

Ngay cả khi YAML hợp lệ, generation hoặc packaging có thể thất bại vì **không tìm được tài nguyên body**. Cách sửa không phải tạo file tên giống bất kỳ với nội dung rỗng, mà là khôi phục **đúng dữ liệu contract cần kiểm tra** rồi chạy lại test.

## 7. Nhóm lỗi D — Contract hợp lệ nhưng generated test compile lỗi

Một contract có thể parse/generate thành công nhưng **source test được tạo không biên dịch**. Ví dụ các nguyên nhân:

- `baseClassForTests` trỏ nhầm package hoặc lớp không tồn tại.
- Test base có method matcher như `assertBusinessRule($it)` nhưng tên/chữ ký Java không khớp.
- Dự án thiếu dependency test cần cho mode mà SCC sinh ra.
- Plugin, Spring Boot, Spring Cloud Release Train, JUnit hoặc Java toolchain không tương thích.
- Generated test được cấu hình dùng MockMvc/WebTestClient/HTTP nhưng test base thiết lập công cụ khác.
- Thay đổi package hoặc class name mà quên cập nhật plugin config.

Ví dụ với Maven plugin:

~~~xml
<plugin>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-contract-maven-plugin</artifactId>
    <version>4.x.y</version>
    <extensions>true</extensions>
    <configuration>
        <baseClassForTests>com.example.inventory.ContractTestBase</baseClassForTests>
    </configuration>
</plugin>
~~~

`4.x.y` là **ký hiệu minh họa**, phải thay bằng phiên bản plugin thật tương thích với BOM Spring Cloud đã chọn. Kiểm tra class được khai báo trong test sources:

~~~java
package com.example.inventory;

import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
public abstract class ContractTestBase {
    // Cấu hình MockMvc, WebTestClient hoặc HTTP theo test mode thực tế.
}
~~~

Đoạn Java trên minh họa **vị trí/tên lớp** chứ chưa phải test base chạy được với mọi test mode. Khi có lỗi compile, đọc **generated source + lỗi compiler**, xác nhận lời gọi method/import/extends có khớp nhau hay không.

Không nên đánh dấu contract “không hợp lệ” chỉ vì thiếu test base; đó là lỗi **tích hợp môi trường sinh test** và cần giải quyết đúng tầng.

## 8. Nhóm lỗi E — Generated test chạy nhưng producer không đáp ứng

Ví dụ contract yêu cầu:

~~~json
{
  "sku": "SKU-123",
  "available": true
}
~~~

Nhưng implementation mới trả:

~~~json
{
  "sku": "SKU-123",
  "inStock": true
}
~~~

Generated producer test **phải thất bại** ở assertion liên quan nếu đã mô tả trường `available`. Đây là dấu hiệu Contract Verifier đang làm đúng chức năng, không phải lỗi syntax.

Phân biệt ba câu hỏi:

1. **Contract có mô tả đúng cam kết đã thống nhất không?** Nếu đúng, code producer phải sửa để đáp ứng.
2. **Đội có chủ ý thay đổi cam kết không?** Khi đó cần sửa contract, nhưng cũng phải kiểm tra consumer cũ.
3. **Test có sử dụng dữ liệu giả định không ổn định không?** Nếu body chứa timestamp/ID động, cần matcher phù hợp chứ không sửa bỏ assertion quan trọng.

Không giải quyết producer test đỏ bằng `skipTests`, bỏ contract hoặc nới matcher vô điều kiện. Các cách đó làm mất bằng chứng tương thích mà pipeline cần.

## 9. Trường hợp no-contract: bốn tình huống khác nhau

**Không có hợp đồng** không luôn là lỗi. Cần xác định vì sao số contract bằng 0.

| Tình huống | Ví dụ | Cách quyết định |
|---|---|---|
| **Có chủ đích không có contract** | Module thư viện thuần, chưa cung cấp API/message | Có thể cho phép, nhưng cần cấu hình/chính sách rõ ràng |
| **Chưa triển khai contract** | Dịch vụ mới đã có API nhưng đội chưa tạo contract | Không được coi là đã kiểm chứng; yêu cầu hoàn thiện trước khi bật compatibility gate |
| **Có file nhưng plugin không phát hiện** | Đặt nhầm thư mục, extension không đúng, task/plugin chưa được bật | Phải sửa discovery; nên chặn trong module kỳ vọng có contract |
| **File có nhưng bị loại khỏi bước build** | CI profile tắt plugin, skip tests, source set sai, điều kiện pipeline bỏ qua | Phải khôi phục pipeline, kiểm tra số test chạy |

Một module **consumer-only** có thể không chứa contract producer tại cùng vị trí; nhiệm vụ của nó là kiểm thử với stub đã phát hành. Ngược lại, **producer đã được quy định dùng Contract Verifier** thì 0 hợp đồng thường là lỗi quy trình cần phát hiện sớm.

Cách đặt chính sách nên dựa trên **vai trò module**, không áp một điều kiện cứng cho toàn bộ repository nhiều module.

## 10. Vì sao “không có contract” có thể tạo false green?

Một pipeline có thể trả mã thành công khi:

- Plugin không quét được tệp nào.
- Không có generated test nào, nhưng test runner vẫn kết thúc bình thường.
- Toàn bộ test bị tắt vì profile, flag hoặc điều kiện CI.
- Stub artifact có thể được đóng gói ở dạng không chứa mapping hữu ích.
- Consumer test vẫn dùng **stub phiên bản cũ**, vì artifact ứng viên mới không xuất hiện.

Khi đó, một dòng `BUILD SUCCESS` chỉ cho thấy **lệnh build hoàn tất theo cấu hình hiện tại**, không cho thấy hợp đồng nào đã được bảo vệ.

**Bằng chứng tối thiểu cần thu thập:** hợp đồng được phát hiện, generated test được sinh và chạy, kết quả assertions, stub mappings hiện diện, và consumer dùng đúng stub của commit/version ứng viên.

Không kết luận “Contract Verifier có lỗi” hay “mặc định luôn fail khi 0 contract”: **hành vi khi không có contract phụ thuộc plugin/version và cấu hình**. Điều an toàn là xây cổng CI độc lập với giả định về mặc định đó.

## 11. Kiểm tra nguyên nhân zero contracts theo thứ tự

Khi module đáng lẽ có hợp đồng nhưng log cho thấy không có gì được sinh, hãy kiểm tra:

1. **Thư mục:** convention thông dụng là `src/test/resources/contracts/` ở producer; nếu đã đổi `contractsDslDir` hoặc cấu hình tương đương, kiểm tra giá trị hiệu lực.
2. **Phần mở rộng:** các tệp Groovy/YAML được nhận diện theo quy tắc và version plugin; đừng đặt nội dung YAML trong tệp `.txt` rồi kỳ vọng được quét.
3. **Plugin đã áp dụng:** Maven/Gradle có thực sự khai báo SCC plugin ở module producer đúng nơi không?
4. **Lifecycle/task:** lệnh CI có chạy bước generate tests và bước chạy test không, hay chỉ compile package theo nhánh khác?
5. **Profile và skip flags:** có điều kiện chỉ bật plugin ở local mà tắt trên CI, hoặc `skipTests`/`maven.test.skip` đang được sử dụng không?
6. **Source set và test runner:** generated tests có được đưa vào test sources, có tên/annotation JUnit phù hợp và được chạy không?
7. **Đầu ra stub:** mapping và artifact classifier `stubs` có được tạo từ chính phiên bản ứng viên không?

Trong dự án nhiều module, phải kiểm tra **đúng submodule producer**. Một lệnh chạy ở root tạo báo cáo thành công cho module không có contract không chứng minh module producer đã được kiểm thử.

## 12. Maven: kiểm tra generation, test và artifact

Trong dự án Maven đã cấu hình Spring Cloud Contract plugin:

~~~bash
# Kiểm tra Maven và Java thực sự đang dùng.
./mvnw --version

# Xem cấu hình plugin và lifecycle hiệu lực.
./mvnw help:effective-pom

# Sinh, biên dịch và chạy những test thuộc vòng build đã cấu hình.
./mvnw clean verify
~~~

Với Maven, generated contract test thường nằm dưới vùng output của plugin trong `target/generated-test-sources/contracts/`, nhưng đường dẫn cụ thể có thể thay đổi theo phiên bản/cấu hình. Đừng chỉ đi tìm một tên thư mục cố định rồi suy ra plugin thất bại nếu nó không tồn tại.

Cần kiểm tra ít nhất:

- Log xác nhận plugin đọc **đúng contracts directory** và có đầu vào.
- Có generated source/test cho contract cụ thể, ví dụ case GET stock.
- Test runner (Surefire/Failsafe theo cấu hình) **đã chạy những generated tests đó** và báo số case khác 0.
- Nếu có cấu hình sinh stub, artifact có classifier `stubs` chứa mapping tương ứng.
- Nếu Maven chạy nhiều module, output đang kiểm tra thuộc đúng `artifactId` producer.

**Đặc biệt:** Maven có thể cấu hình `skipTests` để bỏ qua thực thi test; `maven.test.skip` còn ảnh hưởng compile test. Không dùng các cờ này trong gate xác nhận tương thích; nếu phải chạy vì mục đích khác, pipeline phải nói rõ stage nào **không kiểm chứng hợp đồng**.

## 13. Gradle: xác định task nào thực sự chạy

Trong dự án Gradle có Spring Cloud Contract plugin:

~~~bash
# Kiểm tra Gradle/JVM.
./gradlew --version

# Xem task liên quan đến contract trong phiên bản plugin hiện tại.
./gradlew tasks --all

# Chạy test theo lifecycle của dự án.
./gradlew clean test
~~~

Khi dùng plugin, tên task sinh test, tạo stubs hoặc nối chúng vào `test` có thể thay đổi theo version và cấu hình. Hãy xem danh sách task/log để biết chính xác pipeline đã chạy gì, thay vì dựa vào một tên task được ghi trong hướng dẫn cũ.

Nếu build có nhiều subproject, nên kiểm chứng đúng subproject producer. Ví dụ cách gọi một task module:

~~~bash
./gradlew :inventory-service:test
~~~

Đó là cú pháp minh họa cho một subproject có tên `inventory-service`; tên thực tế có thể khác. Kiểm tra generated sources, test reports và artifacts của đúng subproject.

## 14. Chiến lược fail fast khi không có hợp đồng

Một chính sách **fail fast** phù hợp giúp phát hiện no-contract ngay ở đầu pipeline, thay vì phát hành artifact rồi mới nhận ra không có mapping.

### Lựa chọn A — Dùng cấu hình hỗ trợ bởi phiên bản plugin

Một số dòng/cấu hình Contract Verifier có cơ chế điều khiển hành vi khi **không tìm thấy hợp đồng**. Tên option và giá trị mặc định cần được **đối chiếu tài liệu của đúng phiên bản plugin**. Không sao chép một cờ từ blog cũ hoặc tự đoán tên cấu hình; nếu plugin không nhận, cổng kiểm tra có thể không có tác dụng.

Nếu dự án sử dụng một lựa chọn tương tự **fail on no contracts**, phải chứng minh bằng test âm tính: **tạm chuyển contract ra khỏi nguồn trong một nhánh thử**, chạy pipeline và xác nhận stage liên quan **thất bại thật**. Sau đó khôi phục contract. Không chỉ nhìn vào config rồi kết luận đã được bảo vệ.

### Lựa chọn B — Cổng riêng theo module

Đối với module producer bắt buộc có contract, CI có thể kiểm tra:

- Số tệp hợp đồng thực sự được phát hiện **lớn hơn 0**.
- Số generated test cases được **runner thực thi lớn hơn 0**, không chỉ số file source.
- Những contract quan trọng dự kiến có tên trong test report.
- Stub artifact ứng viên có số mapping thực tế **lớn hơn 0**.

Ví dụ một **kiểm tra sơ bộ** trong môi trường POSIX khi dùng convention thư mục:

~~~bash
# Chỉ kiểm tra có source DSL theo convention; KHÔNG thay thế kiểm tra generation.
test -n "$(find src/test/resources/contracts \
  -type f \( -name '*.groovy' -o -name '*.yml' -o -name '*.yaml' \) \
  -print -quit)"
~~~

Lệnh trên chỉ cho biết có file có đuôi phù hợp. Nó **không chứng minh** plugin nhận diện được file, DSL hợp lệ hay test đã chạy. Một cổng đầy đủ vẫn phải kiểm tra output/log/test report/stub. Với Windows, cần dùng cơ chế tương đương của môi trường build, không sao chép lệnh POSIX sang PowerShell mà không chuyển cú pháp.

### Lựa chọn C — Ngoại lệ có chủ đích cho module chưa dùng Contract Verifier

Nếu một module **thực sự không sở hữu contract**, có thể miễn gate no-contract **cho module đó** sau khi ghi nhận rõ vai trò. Không nên đặt `skip` toàn cục cho toàn repository, vì nó sẽ che mất việc một producer đánh rơi hợp đồng khi refactor.

## 15. Kiểm chứng chính sách bằng các tình huống âm tính

Một pipeline chỉ được xem là có cổng ngăn “false green” khi đã được thử bằng các trường hợp sai có chủ đích trong nhánh thử nghiệm:

| Thao tác thử | Kỳ vọng với producer bắt buộc có contract |
|---|---|
| Xóa/di chuyển toàn bộ contract khỏi đường quét | **FAIL** ở gate no-contract/discovery |
| Viết sai cú pháp Groovy hoặc YAML | **FAIL** ở parse/generate |
| Đổi matcher sang trường body không tồn tại | **FAIL** ở generation/compile/test, hoặc phát hiện bằng kiểm tra generated source |
| Giữ contract nhưng xóa controller/method tương ứng | **FAIL** khi producer test chạy |
| Đổi `available` sang `inStock` chỉ trong code producer | **FAIL** ở producer verification nếu field cũ được assert |
| Đổi cả code + contract sang `inStock` | Producer có thể PASS; **consumer cũ phải được thử với stub mới** |
| Chạy test consumer với stub phiên bản trước | Cổng phải cảnh báo/lỗi vì sai artifact ứng viên, không được coi là đã xác nhận PR |

Trong nhánh thử, phục hồi dữ liệu sau khi xác nhận pipeline chuyển đỏ. Không để các lỗi giả vào nhánh chính. Kiểm tra failure mode **định kỳ** khi nâng plugin, chỉnh profile hoặc thay pipeline giúp duy trì tính tin cậy của cổng.

## 16. Không có generated test khác với không có contract source

Bốn số liệu có thể khác nhau:

1. **Contract source count:** tệp Groovy/YAML trong vùng đầu vào.
2. **Contract parsed count:** số hợp đồng mà SCC thực sự nhận và đánh giá.
3. **Generated test count:** số test source/test cases được sinh.
4. **Executed test count:** số test cases được runner thực thi.

Ví dụ: có 5 tệp `.yml` nhưng chỉ 3 được plugin quét vì 2 nằm sai thư mục; trong 3 tệp đó có một hợp đồng không hợp lệ; khi parse/generate thất bại, có thể không có test chạy. Cũng có thể tất cả được sinh nhưng cấu hình runner làm **0 test được thực thi**.

Do đó **đếm file** chỉ là điểm kiểm tra đầu tiên. Chứng cứ mạnh nhất cho producer-side verification là:

> “Contract X đã sinh generated test Y, test Y đã được chạy với producer commit Z và assertions đạt.”

Nếu có contract message và HTTP, cần chắc chắn cả hai loại được nối đúng với test base/adapter. Một trong hai loại không sinh test cũng có thể để lại khoảng trống kiểm chứng.

## 17. Lỗi body matcher, payload và test base không nên bị “fix” bằng skip

Giả sử một contract YAML mô tả:

~~~yaml
request:
  method: GET
  url: /api/inventory/SKU-123
response:
  status: 200
  body:
    sku: SKU-123
    quantity: 12
  matchers:
    body:
      - path: $.missingField
        type: by_type
~~~

`$.missingField` không nằm trong body mẫu. Khi sinh test, matcher này có thể gây lỗi hoặc trở nên vô nghĩa. Cách xử lý đúng là xác định **field nào consumer thật sự phụ thuộc**, rồi đổi path và body cho khớp, không xóa matcher để pipeline xanh.

Tương tự với custom command:

~~~groovy
bodyMatchers {
    jsonPath('$.quantity', byCommand('assertQuantityAllowed($it)'))
}
~~~

Generated test cần truy cập được `assertQuantityAllowed` từ base class hoặc test support. Nếu method không tồn tại hoặc không accessible, đó là lỗi compile/test integration cần sửa **tên method, visibility, package hoặc cấu hình base test**.

Khi test fail vì producer trả quantity 101 thay vì tối đa 100, cần phân biệt lỗi implementation với thay đổi business rule. Không tự nới quy tắc Java helper để vượt qua CI nếu consumer chưa chấp nhận giá trị mới.

## 18. Contract messaging: dạng lỗi tương tự nhưng biểu hiện khác

Với message contract, có thể mô tả input/trigger và output message. Ví dụ minh họa Groovy DSL:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    label 'inventoryChanged'

    input {
        triggeredBy('triggerInventoryChanged()')
    }

    outputMessage {
        sentTo('inventory.events')
        headers {
            header('contentType', 'application/json')
        }
        body(
            eventType: 'InventoryChanged',
            sku: 'SKU-123',
            available: true
        )
    }
}
~~~

Để test được sinh và chạy có ý nghĩa, project phải cung cấp **cách trigger** như method `triggerInventoryChanged()` trong test base, cùng messaging test infrastructure phù hợp với stack.

Các lỗi thường gặp:

- Contract message parse được nhưng **trigger method không tồn tại**.
- Thiếu destination/topic, header hoặc serialization phù hợp với consumer.
- Test base không cấu hình messaging adapter/test binder; generated test không quan sát được message.
- Pipeline chỉ kiểm tra HTTP contracts, bỏ sót message contracts.
- Không có contract messaging nào được phát hiện nhưng job vẫn chạy phần còn lại.

Đừng kết luận từ body JSON hợp lệ rằng message đã được phát tới broker hoặc consumer xử lý được. Cần xác nhận **generated message test thực sự chạy** và consumer handler được kiểm tra với stub/message thích hợp.

## 19. Stub packaging: contract hợp lệ chưa chắc artifact được phân phối đúng

Một đường đi đáng tin cậy là:

~~~text
Contract source của producer commit ABC
   -> generation thành công
   -> generated producer tests đạt
   -> stub mapping/body được đóng gói
   -> artifact có classifier "stubs" + version ứng viên
   -> consumer Stub Runner tải đúng artifact
   -> test client thật của consumer đạt
~~~

Những điểm cần xác nhận ở stub artifact:

| Điều cần kiểm tra | Nguy cơ nếu bỏ qua |
|---|---|
| Có mapping đúng contract vừa sửa | Stub mới thiếu tình huống và consumer test không phát hiện đổi API |
| Response body/header/status phản ánh DSL mới | Consumer nhận giả lập sai hành vi producer ứng viên |
| Có mọi body resource được tham chiếu | Stub có thể fail lúc chạy hoặc trả body sai |
| Version/commit xác định rõ | Stub Runner tải nhầm artifact cũ trong local cache |
| Client test sử dụng đúng endpoint/stub port | Test xanh vì gọi mock khác hoặc service cũ |
| Consumer test dùng HTTP client/handler thật | Bài test chỉ kiểm tra stub có thể trả JSON, không kiểm tra integration của consumer |

Ví dụ coordinate minh họa:

~~~text
com.example:inventory-service:1.3.0-rc1:stubs
~~~

Version `1.3.0-rc1` chỉ là ví dụ ứng viên. Trong CI cần ghim artifact đúng với commit cần kiểm tra. Một consumer test xanh với stub của phiên bản **trước thay đổi** không xác nhận tương thích của API **đang được đề xuất**.

## 20. Quy trình xử lý sự cố theo từng bước

Khi CI báo lỗi contract hoặc báo không có test, làm theo thứ tự:

**Bước 1 — Xác định tình huống:** đang thất bại ở parsing, generation, compile, execution, stub packaging hay consumer? Không gộp tất cả thành “contract test đỏ”.

**Bước 2 — Xác minh source:** contract có nằm ở thư mục plugin đọc không? Tệp có extension/encoding phù hợp? Groovy/YAML có đúng cấu trúc `request` và `response`?

**Bước 3 — Xác minh input phụ:** fixture có tồn tại, matcher đúng path/type, base class và custom command sẵn sàng không?

**Bước 4 — Xác minh generated tests:** có source mới, có test cho đúng contract, được compile và thực thi? Test report có số case mong đợi không?

**Bước 5 — Đọc assertion failure:** request producer nhận là gì; response thực khác kỳ vọng ở status/header/body/message nào? Đây là lỗi code hay thay đổi contract cần phối hợp?

**Bước 6 — Đánh giá stub:** mapping có được đóng gói đúng commit, version, classifier không? Stub Runner thực sự tải gì?

**Bước 7 — Chạy consumer verification:** test client thật với stub ứng viên; nếu lỗi tương thích, chọn phương án giữ API cũ, triển khai chuyển đổi hoặc versioning.

**Bước 8 — Ghi nhận nguyên nhân gốc:** không chỉ sửa triệu chứng; bổ sung guard hoặc test âm tính để sự cố tương tự không lặp lại.

## 21. Bài thực hành: tạo lỗi có chủ đích và sửa đúng tầng

Chuẩn bị hai ứng dụng mẫu:

- **Inventory Service** (producer) có endpoint `GET /api/inventory/SKU-123`.
- **Checkout Service** (consumer) đọc `available` từ response, chạy với Stub Runner.

### Vòng A — Baseline hợp lệ

1. Chọn bộ Spring Boot–Spring Cloud–Contract tương thích.
2. Tạo một contract Groovy hoặc YAML từ phần 3.
3. Cấu hình producer test base và plugin.
4. Chạy generation/test, xác nhận generated test thật sự có mặt và được chạy.
5. Tạo stub ứng viên; consumer test đọc được `available: true`.

**Bằng chứng:** tên contract, generated test, test report và stub coordinate.

### Vòng B — Invalid contract

1. Tạm bỏ một dấu `}` trong Groovy hoặc làm sai thụt lề YAML.
2. Chạy lại generation và ghi nhận lỗi parse.
3. Sửa lỗi, đưa contract về trạng thái hợp lệ.
4. Trỏ `bodyFromFile` đến một file không tồn tại, quan sát lỗi nạp resource.
5. Sửa đường dẫn và xác nhận generated test được sinh lại.

**Bằng chứng:** lỗi cụ thể ở tầng parse/resource; tránh nhầm chúng với lỗi controller.

### Vòng C — Không có hợp đồng

1. Trong một **nhánh thử nghiệm**, tạm chuyển toàn bộ contract của producer khỏi thư mục quét.
2. Chạy build và ghi số contract, số generated tests, số executed tests.
3. Quan sát hành vi thực tế của plugin khi không có contract.
4. Thiết lập cổng CI theo chính sách producer: yêu cầu số contract và executed test **lớn hơn 0**.
5. Chạy lại và xác nhận pipeline **thất bại** như mong đợi.
6. Khôi phục tệp contract trước khi tiếp tục.

**Bằng chứng:** cổng CI báo rõ “không có contract” thay vì cho build xanh giả.

### Vòng D — Contract mới có thể phá consumer cũ

1. Đổi producer trả `inStock` thay `available`, **giữ contract cũ**: producer test phải đỏ.
2. Đồng bộ contract theo field mới: producer test có thể xanh.
3. Tạo stub ứng viên mới từ commit thay đổi.
4. Consumer cũ chạy với stub mới; nếu còn phụ thuộc `available`, test phải phát hiện lỗi.
5. Đề xuất kế hoạch mở rộng–chuyển đổi–thu hẹp, hoặc API versioning phù hợp.

**Bằng chứng:** kết quả producer/consumer cho cả hai giai đoạn, giúp xác định lỗi được phát hiện ở đâu.

## 22. Checklist trước khi hợp nhất hoặc phát hành

- [ ] Module producer được xác định rõ **có bắt buộc có contract không**.
- [ ] Các tệp Groovy/YAML nằm đúng vùng plugin thực sự quét.
- [ ] Contract parse/validate được; `request` và `response` diễn đạt hành vi cần bảo vệ.
- [ ] Body fixture, JSONPath và custom matcher có thể được xử lý.
- [ ] Generated test biên dịch được với đúng base class và test mode.
- [ ] **Số executed contract tests > 0** đối với producer được yêu cầu có contract.
- [ ] Không có `skipTests` hoặc profile làm vô hiệu hóa cổng kiểm chứng.
- [ ] Có bằng chứng generated tests chạy và assert status/header/body/message.
- [ ] Contract fail ở tầng nào được log/chẩn đoán rõ, không bị “làm xanh” bằng cách xóa test.
- [ ] Stub artifact chứa mapping/body của **đúng commit ứng viên**.
- [ ] Consumer test chạy với **Stub Runner và client/handler thật**.
- [ ] Dùng đúng stub version; không phụ thuộc `+` hoặc latest động để xác nhận PR cụ thể.
- [ ] Pipeline đã được thử với tình huống cố ý không có contract và invalid DSL.
- [ ] Những thay đổi API/message có nguy cơ breaking có kế hoạch chuyển đổi cho consumer.

## 23. Những câu hỏi tự kiểm tra

**1. YAML parse thành công có chứng minh hợp đồng hợp lệ và producer tuân thủ không?**

Không. YAML parser chỉ kiểm tra hình thức dữ liệu. SCC còn phải hiểu schema và sinh test. Chỉ khi generated test thực sự chạy với producer và assertions đạt mới có bằng chứng producer đáp ứng contract.

**2. Tại sao không nên xem build success là bằng chứng có contract?**

Bởi vì plugin có thể không phát hiện hợp đồng hoặc test runner không chạy generated tests; hành vi no-contract phụ thuộc cấu hình/phiên bản. Cần xác nhận số contract, generated test và executed test.

**3. Khi nào số lượng contract bằng 0 được xem là hợp lệ?**

Khi module thật sự không có trách nhiệm cung cấp contract (ví dụ thư viện hoặc consumer-only module) và chính sách đã ghi rõ ngoại lệ. Đối với producer bắt buộc có contract, đó là lỗi cần chặn.

**4. Generated producer test đỏ vì field `available` bị đổi thành `inStock` có nghĩa contract sai không?**

Không nhất thiết. Nếu consumer vẫn cần `available`, test đỏ là tín hiệu producer phá cam kết. Chỉ sửa contract khi đã thống nhất thay đổi hành vi và kiểm chứng các consumer bị ảnh hưởng.

**5. Vì sao cần xem stub mapping sau khi contract mới được sinh thành công?**

Vì mapping có thể bị thiếu, chồng lấn hoặc đóng gói sai. Một contract test xanh không đảm bảo Stub Runner đã phát đúng hành vi cho consumer; phải kiểm tra artifact và chạy test consumer thực tế.

**6. Làm cách nào kiểm tra guard no-contract có hoạt động?**

Trong nhánh thử, tạm chuyển mọi contract khỏi vùng plugin quét rồi chạy CI. Pipeline producer phải chuyển đỏ ở gate được thiết kế, sau đó khôi phục contract và xác nhận xanh trở lại.

## 24. Tài liệu tham khảo và lưu ý phiên bản

- [Spring Cloud Contract Reference](https://docs.spring.io/spring-cloud-contract/reference/): quy trình Contract Verifier, generated producer tests và Stub Runner.
- [Spring Cloud Contract – Contract DSL](https://docs.spring.io/spring-cloud-contract/reference/project-features-contract.html): Groovy/YAML DSL, tổ chức request/response và matcher.
- [Spring Cloud Contract – HTTP Contracts](https://docs.spring.io/spring-cloud-contract/reference/project-features-contract/http.html): mô tả hợp đồng HTTP.
- [Spring Cloud Contract – Maven Project Features](https://docs.spring.io/spring-cloud-contract/reference/project-features-maven.html): hướng dẫn tích hợp plugin và vòng đời build; cấu trúc tài liệu có thể thay đổi theo phiên bản.
- [Spring Cloud Contract – Gradle Project Features](https://docs.spring.io/spring-cloud-contract/reference/project-features-gradle.html): cách cấu hình Gradle plugin và các task.
- [Spring Cloud Contract – Stub Runner](https://docs.spring.io/spring-cloud-contract/reference/project-features-stubrunner.html): chạy stub trong consumer tests.

**Lưu ý:** Những option quyết định hành vi **zero contracts**, tên task/goal, đường dẫn generated source và mặc định của plugin có thể thay đổi theo phiên bản. Hãy chọn đúng tài liệu Spring Cloud Contract đi cùng phiên bản **Spring Boot + Spring Cloud Release Train** mà dự án đã chốt; xác minh bằng kết quả build thực tế. Tránh phụ thuộc vào một flag chưa được plugin hiện tại hỗ trợ.

---

**Điểm cần nhớ:** Hợp đồng không hợp lệ phải bị phát hiện đúng tầng; **không có hợp đồng** trong producer cần kiểm chứng là tình trạng nguy hiểm nếu pipeline vẫn xanh. Cổng tin cậy phải nối đủ **contract được phát hiện → DSL được xử lý → generated test chạy → producer đáp ứng → stub ứng viên có mapping → consumer test đạt**. Chỉ khi đó Spring Cloud Contract mới giúp CI phát hiện sớm những thay đổi API hoặc message không tương thích.
