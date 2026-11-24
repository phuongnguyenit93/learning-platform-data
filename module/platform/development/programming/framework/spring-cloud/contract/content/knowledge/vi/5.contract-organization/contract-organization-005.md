# Quy ước đường dẫn ảnh hưởng đến kiểm thử được sinh

## Mục tiêu bài học

Trong **Spring Cloud Contract**, hợp đồng HTTP hoặc thông điệp được định nghĩa bằng **Groovy DSL** hoặc **YAML DSL**, rồi được dùng để sinh kiểm thử phía **producer** và tạo stub cho phía **consumer**. Tuy nhiên, việc đặt tệp hợp đồng ở đâu, đặt tên như thế nào và nhóm chúng vào thư mục nào có thể quyết định:

- Công cụ có **tìm thấy** hợp đồng để xử lý hay không.
- Hợp đồng thuộc **nhóm kiểm thử** nào và được liên kết với **lớp nền (base test class)** nào.
- Tên, package hoặc cấu trúc của kiểm thử sinh ra **trong cấu hình/bản Spring Cloud Contract đang dùng**.
- Hợp đồng nào được lấy vào bộ stub và sau đó được consumer dùng qua **Stub Runner**.
- Một lần di chuyển hoặc đổi tên tệp có khiến CI bỏ sót test hay không.

Mục tiêu của bài thuộc chương **Tổ chức hợp đồng** là thiết kế đường dẫn dễ hiểu, ổn định và có thể kiểm chứng trong CI. Không có quy ước tên thư mục nào tự chứng minh API tương thích; chính các test được sinh và được **chạy thành công** mới góp phần tạo bằng chứng đó.

## 1. Phân biệt ba loại đường dẫn dễ bị nhầm lẫn

Khi xem một hợp đồng, cần phân biệt:

| Loại đường dẫn | Vai trò | Ví dụ |
| --- | --- | --- |
| **Đường dẫn tệp DSL** | Nơi Spring Cloud Contract tìm và đọc định nghĩa hợp đồng | src/test/resources/contracts/orders/get_paid_order.yml |
| **Đường dẫn HTTP hoặc destination của message** | Giao diện producer công bố cho consumer | GET /api/orders/ORD-1001 |
| **Đường dẫn đầu ra của build** | Nơi plugin tạo test/stub; thông thường thuộc thư mục build | target/… hoặc build/… |

Điểm quan trọng: **di chuyển tệp** từ thư mục orders sang thư mục checkout **không tự động đổi URL** từ /api/orders sang /api/checkout. URL HTTP được đặc tả trong nội dung hợp đồng. Ngược lại, chỉ sửa URL trong YAML mà giữ nguyên đường dẫn tệp cũng có thể làm hành vi consumer bị phá vỡ.

Quy ước đường dẫn chủ yếu tác động đến **cơ chế tìm, nhóm, ánh xạ và sinh artifact**; nội dung hợp đồng quyết định **hành vi tích hợp**.

## 2. Thư mục gốc hợp đồng: công cụ phải tìm thấy tệp trước

Với dự án producer dùng bố cục Maven/Gradle thông dụng, thư mục hợp đồng cục bộ thường là:

~~~text
order-service/
├── pom.xml                 # Hoặc build.gradle
├── src/
│   ├── main/
│   │   └── java/
│   └── test/
│       ├── java/
│       └── resources/
│           └── contracts/
│               └── orders/
│                   ├── get_paid_order.yml
│                   └── get_missing_order.yml
└── ...
~~~

**src/test/resources/contracts** là vị trí mặc định thường gặp khi hợp đồng được lưu trong chính dự án producer. Nếu nhóm chọn nơi khác hoặc lấy hợp đồng từ repository/artifact riêng, phải khai báo nguồn và đường dẫn cho plugin đang sử dụng.

Ví dụ các cách tổ chức nguồn hợp đồng:

| Cách đặt hợp đồng | Cần đảm bảo |
| --- | --- |
| Trong producer tại src/test/resources/contracts | Plugin quét đúng thư mục mặc định hoặc thư mục đã cấu hình |
| Trong thư mục tùy chỉnh của producer | Cấu hình thư mục DSL tương ứng cho Maven/Gradle |
| Trong artifact/repository hợp đồng độc lập | Cấu hình dependency/nguồn hợp đồng cùng đường dẫn tương đối bên trong artifact |
| Trong monorepo nhiều producer | Mỗi lần build chỉ chọn tập hợp hợp đồng đúng producer được xác minh |

Trong các plugin Spring Cloud Contract, cách khai báo có thể khác nhau theo công cụ và phiên bản: ví dụ **contractsDirectory** trong ngữ cảnh Maven plugin, hoặc **contractsDslDir** trong ngữ cảnh Gradle plugin. Các tùy chọn dành cho hợp đồng được tải từ artifact, như nguồn dependency và **contractsPath**, lại có mục đích khác với đường dẫn DSL cục bộ. Cần tra cú pháp chính xác theo **phiên bản plugin của dự án** trước khi áp dụng.

Một hợp đồng hợp lệ về cú pháp nhưng nằm **ngoài thư mục được quét** có thể không được đưa vào tập kiểm thử. Đây là lỗi nguy hiểm vì build có thể vẫn chạy các test khác và hiển thị màu xanh.

### Bài học từ một lần chuyển thư mục

Giả sử bạn đổi:

~~~text
src/test/resources/contracts/orders/get_paid_order.yml
~~~

thành:

~~~text
src/contract-spec/orders/get_paid_order.yml
~~~

Nếu không cập nhật cấu hình nguồn hợp đồng, công cụ có thể không tìm thấy tệp tại vị trí mới. Cần xác nhận **số lượng hợp đồng được phát hiện, danh sách test được sinh và kết quả test thực sự chạy** sau lần di chuyển.

## 3. Quy ước phân nhóm thư mục: theo miền nghiệp vụ và kiểu tích hợp

Một cấu trúc dễ mở rộng có thể là:

~~~text
src/test/resources/contracts/
├── orders/
│   ├── http/
│   │   ├── get_paid_order.yml
│   │   ├── get_missing_order.yml
│   │   └── cancel_order.groovy
│   └── messaging/
│       └── order_paid_event.groovy
├── payments/
│   ├── http/
│   │   └── get_payment.yml
│   └── messaging/
│       └── payment_failed_event.groovy
└── shipping/
    └── http/
        └── get_shipment.yml
~~~

Ở đây:

- **orders, payments, shipping** thể hiện các miền nghiệp vụ mà đội phát triển hiểu rõ.
- **http** và **messaging** tách những contract cần cách setup và kiểm thử khác nhau.
- Tên tệp gợi đúng **hành vi** hoặc tình huống cần kiểm chứng, không phải tên implementation class.

Đây là **quy ước đề xuất của dự án**, không phải cấu trúc lồng thư mục bắt buộc do Spring Cloud Contract áp đặt. Một dự án nhỏ có thể chỉ cần một cấp thư mục; dự án lớn có thể nhóm thêm theo consumer, phiên bản giao diện hoặc loại use case nếu việc đó giúp truy vết rõ ràng.

Không nên tạo nhiều cấp thư mục chỉ để mô phỏng package Java. Hãy chọn số cấp cần thiết cho việc **sở hữu, tìm kiếm, phân nhóm setup kiểm thử và quản lý thay đổi**.

### Đặt tên có chủ đích

Tên nên thể hiện hành vi:

| Tên khó hiểu | Tên rõ mục đích hơn | Lý do |
| --- | --- | --- |
| test1.yml | get_paid_order.yml | Dễ nhận diện kịch bản |
| ok.yml | create_order_success.yml | Phân biệt hành vi tạo với truy vấn |
| error.yml | get_missing_order.yml | Cho biết điều kiện gây lỗi |
| controller_contract.groovy | cancel_order.groovy | Không gắn với tên class nội bộ |

Nên dùng tên thống nhất, chỉ gồm chữ thường, số và dấu gạch dưới khi có thể. Với **tên thư mục** có thể tham gia tạo package Java hoặc ánh xạ tên package, ưu tiên các thành phần phù hợp quy tắc định danh Java (ví dụ orders, http, messaging), tránh khoảng trắng, dấu gạch nối và ký tự đặc biệt. Điều này cũng giúp tránh khác biệt về chữ hoa/chữ thường giữa máy Windows và môi trường CI Linux.

## 4. Đường dẫn tương đối có thể ảnh hưởng đến cấu trúc test được sinh

Tùy phiên bản Spring Cloud Contract, DSL và cấu hình Verifier, tên tệp, tên hợp đồng và cấu trúc thư mục tương đối có thể ảnh hưởng đến **tên lớp, tên phương thức, package hoặc cách nhóm test sinh ra**.

Ví dụ:

~~~text
contracts/
└── orders/
    └── http/
        ├── get_paid_order.yml
        └── get_missing_order.yml
~~~

Cả hai hợp đồng thuộc nhóm orders/http. Việc generator đưa chúng vào một hay nhiều lớp test, dùng tên lớp/phương thức nào và tổ chức package ra sao là **chi tiết phải xác nhận bằng đầu ra build thực tế**, thay vì giả định mọi phiên bản công cụ xử lý giống nhau.

Điều có thể khẳng định ở cấp tổ chức là: **đường dẫn tương đối phải được kiểm soát như một phần đầu vào của quá trình sinh test**. Nếu một quy tắc ánh xạ dựa trên thư mục, việc đổi tên thư mục có thể khiến test chọn sai lớp nền hoặc không được sinh theo dự kiến.

### Tên trong hợp đồng và tên tệp không thay thế nhau

Hợp đồng YAML có thể có trường định danh **name**. Chẳng hạn:

~~~yaml
description: "Checkout xem đơn hàng đã thanh toán"
name: get_paid_order
request:
  method: GET
  url: /api/orders/ORD-1001
  headers:
    Accept: application/json
response:
  status: 200
  headers:
    Content-Type: application/json
  body:
    id: ORD-1001
    status: PAID
~~~

Hợp đồng ở trên có thể lưu tại:

~~~text
src/test/resources/contracts/orders/http/get_paid_order.yml
~~~

**name** giúp định danh kịch bản; **tên tệp và vị trí** giúp tổ chức và chọn nguồn đầu vào; **url** là đường dẫn HTTP mà consumer gọi. Không nên dùng ba khái niệm này thay thế cho nhau.

Nếu đổi tên tệp hoặc giá trị name, hãy kiểm tra lại đầu ra sinh test. Nếu đổi url, phải kiểm tra cả tác động đến consumer vì đó là thay đổi giao diện HTTP.

## 5. Lớp nền kiểm thử và quy tắc ánh xạ theo thư mục

Trong kiểm thử hợp đồng phía producer, generated test cần có môi trường thực thi: controller hoặc ứng dụng được khởi tạo, dữ liệu mẫu, cấu hình HTTP test client, đôi khi cả broker hoặc message verifier. Một dự án có thể định nghĩa **base test class** để chuẩn bị các điều kiện này.

Ví dụ:

~~~text
src/test/resources/contracts/
├── orders/
│   ├── http/get_paid_order.yml
│   └── messaging/order_paid_event.groovy
└── payments/
    └── http/get_payment.yml

src/test/java/com/example/contract/
├── OrderHttpBase.java
├── OrderMessagingBase.java
└── PaymentHttpBase.java
~~~

Một lớp nền chung có thể dùng cho tất cả test khi setup giống nhau. Nhưng với nhiều nhóm contract, đội thường cần ánh xạ **mỗi nhóm đến lớp nền riêng**, ví dụ:

| Nhóm hợp đồng | Lớp nền kỳ vọng | Trách nhiệm setup |
| --- | --- | --- |
| orders/http | com.example.contract.OrderHttpBase | HTTP client/test context, dữ liệu đơn hàng |
| orders/messaging | com.example.contract.OrderMessagingBase | Điều kiện kích hoạt event và xác minh message |
| payments/http | com.example.contract.PaymentHttpBase | HTTP context và fixture thanh toán |

Trong Spring Cloud Contract, dự án có thể dùng một cấu hình **baseClassForTests** chung hoặc quy tắc lựa chọn lớp nền như **baseClassMappings**; một số kiểu cấu hình còn hỗ trợ đặt tên lớp nền theo package thông qua **packageWithBaseClasses**. Cách khai báo và ngữ nghĩa match cần đối chiếu đúng Maven/Gradle plugin đang chạy.

Để minh họa ý tưởng của **baseClassMappings**, hãy xem *bảng quy tắc giả lập* sau; bảng không phải cú pháp cấu hình có thể dán trực tiếp vào build:

~~~text
Phạm vi contract           -> Lớp nền test được chọn
orders/http/**             -> com.example.contract.OrderHttpBase
orders/messaging/**        -> com.example.contract.OrderMessagingBase
payments/http/**           -> com.example.contract.PaymentHttpBase
~~~

Nếu cấu hình thật match **tên package** được suy từ đường dẫn thay vì đường dẫn tệp thô, biểu thức match phải được viết theo dạng mà plugin nhận, có thể dùng dấu chấm và regex. **Không sao chép nguyên dấu /** vào biểu thức regex** nếu plugin không định nghĩa dấu đó như glob.

Khi di chuyển hợp đồng từ orders/http sang payments/http:

1. Hợp đồng có thể thuộc phạm vi ánh xạ khác.
2. Test sinh ra có thể kế thừa lớp nền thanh toán thay vì lớp nền đơn hàng.
3. Fixture hoặc ứng dụng được khởi tạo có thể không đúng, khiến test lỗi hoặc kiểm tra sai đối tượng.
4. Việc sửa bằng cách đổi luôn URL chỉ để test chạy sẽ làm che đi nguyên nhân thực sự.

Do đó, sau mỗi thay đổi thư mục cần xem **lớp nền thực tế của generated test**, không chỉ nhìn màu xanh của build.

## 6. Ví dụ cụ thể: cùng hợp đồng, khác nơi lưu

Giả sử producer có endpoint:

~~~http
GET /api/orders/ORD-1001
Accept: application/json
~~~

Phản hồi đã thỏa thuận:

~~~json
{
  "id": "ORD-1001",
  "status": "PAID"
}
~~~

Đội phát triển lưu DSL ở:

~~~text
contracts/orders/http/get_paid_order.yml
~~~

Sau đó tái tổ chức thành:

~~~text
contracts/checkout/http/get_paid_order.yml
~~~

Về **hợp đồng HTTP**, request và response vẫn có thể không đổi. Nhưng với quá trình sinh test:

| Hạng mục | Trước khi đổi chỗ | Sau khi đổi chỗ cần kiểm tra |
| --- | --- | --- |
| Phát hiện DSL | Quét được dưới orders/http | Quét được dưới checkout/http hay không |
| Lớp nền | Có thể map đến OrderHttpBase | Có còn map đúng không |
| Package/tên test | Theo quy tắc generator hiện tại | Có thay đổi ngoài dự kiến không |
| Dữ liệu thử nghiệm | Có ORD-1001 ở trạng thái PAID | Fixture mới có giữ tình huống này không |
| Stub | Có mapping từ hợp đồng | Stub build mới còn mapping đó không |
| Consumer CI | Dùng stub của bản đã kiểm chứng | Có dùng artifact mới đúng phiên bản không |

Nếu thư mục checkout có ý nghĩa “consumer Checkout sở hữu hợp đồng”, cần thống nhất cách xử lý khi nhiều consumer cùng dùng endpoint. Nếu thư mục orders có ý nghĩa “producer/domain sở hữu hợp đồng”, cách đặt này thường ổn định hơn trước thay đổi danh sách consumer. Không có lựa chọn duy nhất cho mọi dự án; hãy ghi rõ **trục phân nhóm** được chọn.

## 7. Hợp đồng HTTP và message có thể cần lớp nền khác nhau

Trong Spring Cloud Contract, HTTP contract và message contract đều có thể được viết bằng Groovy/YAML DSL, nhưng cách kiểm chứng khác nhau:

- **HTTP:** generated test gửi request và đối chiếu HTTP status, header, body.
- **Messaging:** generated test kích hoạt hoặc xác minh tương tác thông điệp theo contract; có thể cần setup message verifier/broker và điều kiện phát event.

Ví dụ một hợp đồng Groovy mô tả thông điệp được phát:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description "Phát sự kiện khi đơn hàng được thanh toán"

    label "order_paid_event"

    input {
        triggeredBy("triggerOrderPaid()")
    }

    outputMessage {
        sentTo("order-events")
        body(
            eventType: "ORDER_PAID",
            orderId: "ORD-1001"
        )
        headers {
            contentType(applicationJson())
        }
    }
}
~~~

Đây là **mẫu minh họa**. Phương thức **triggerOrderPaid()** phải được định nghĩa trong ngữ cảnh test phía producer và việc gửi message đến **order-events** cần phù hợp với cấu hình messaging thực tế. Một hợp đồng Groovy nằm đúng thư mục chưa bảo đảm test chạy được nếu lớp nền không có phương thức kích hoạt hoặc hạ tầng xác minh.

Nhóm contract trong thư mục messaging giúp người review nhận ra ngay sự khác nhau về setup. Tuy nhiên, chỉ đặt tên thư mục là messaging **không khiến công cụ tự dựng broker hoặc sinh fixture đúng**. Vẫn phải cấu hình base class và kiểm thử phù hợp.

## 8. Đường dẫn hợp đồng và stub artifact là hai khái niệm khác nhau

Spring Cloud Contract có thể sinh các stub/mapping từ tập hợp hợp đồng đã được xử lý. Stub được đóng gói và phát hành, sau đó **Stub Runner** giúp consumer tải/chạy stub phục vụ kiểm thử tích hợp.

Luồng điển hình:

~~~mermaid
flowchart TD
    A["Contracts trong thư mục được quét"] --> B["Spring Cloud Contract"]
    B --> C["Generated producer tests"]
    B --> D["Stub/mapping"]
    C --> E["Chạy producer test trong CI"]
    D --> F["Đóng gói stub artifact có version"]
    E --> G{"Bằng chứng producer PASS?"}
    G -->|Có| H["Phát hành artifact đã kiểm chứng"]
    G -->|Không| X["Dừng, sửa lỗi"]
    F --> H
    H --> I["Consumer dùng Stub Runner"]
    I --> J["Kiểm thử consumer"]
~~~

Tệp DSL trong thư mục nguồn có đường dẫn như:

~~~text
src/test/resources/contracts/orders/http/get_paid_order.yml
~~~

Nhưng Stub Runner **không điều hướng HTTP bằng đường dẫn của tệp YAML**. Nó vận hành stub được tạo ra; request được match theo đặc tả HTTP (ví dụ GET /api/orders/ORD-1001) và các quy tắc của stub. Các đường dẫn vật lý trong artifact stub, tên thư mục mapping, tên file trong JAR là **đầu ra do công cụ tạo**, có thể khác cấu trúc DSL ban đầu.

Vì vậy sau khi đổi đường dẫn tệp contract:

- Xác nhận producer vẫn phát hiện và kiểm thử hợp đồng.
- Xác nhận stub artifact mới thực sự chứa mapping/định nghĩa mong muốn.
- Chạy consumer test với **phiên bản stub mới, xác định rõ**.
- Không kết luận an toàn từ một lần consumer test dùng lại stub cũ.

## 9. Thư mục hợp đồng riêng và monorepo: xác định nguồn của từng producer

Trong tổ chức có nhiều producer, một repository hợp đồng dùng chung có thể có dạng:

~~~text
contracts-repository/
├── order-service/
│   ├── orders/http/get_paid_order.yml
│   └── orders/messaging/order_paid_event.groovy
└── payment-service/
    ├── payments/http/get_payment.yml
    └── payments/messaging/payment_failed_event.groovy
~~~

Đây là cách **tổ chức nội bộ** minh họa, không phải cấu trúc bắt buộc của artifact hợp đồng từ Spring Cloud Contract.

Khi producer order-service lấy hợp đồng từ nguồn ngoài, cấu hình phải chọn đúng nhánh order-service. Nếu chọn toàn bộ repository rồi đem test trên order-service, các hợp đồng của payment-service có thể bị xử lý nhầm hoặc tạo ra generated tests không thể thực thi.

Nên ghi rõ cho mỗi producer:

| Cấu hình cần quản lý | Mục đích |
| --- | --- |
| Nguồn contract (local hoặc external) | Xác định nơi tìm DSL |
| Phiên bản nguồn hợp đồng | Đảm bảo tái lập kiểm thử |
| Đường dẫn tương đối trong nguồn | Chỉ lấy hợp đồng thuộc producer đó |
| Quy tắc base class | Chọn setup đúng cho từng nhóm contract |
| Tên, phiên bản và tọa độ stub artifact | Consumer lấy đúng stubs đã kiểm chứng |

Trong trường hợp hợp đồng lấy từ artifact, đường dẫn bên trong artifact và đường dẫn nguồn cục bộ **không nhất thiết trùng nhau**. Cần xem đúng cấu hình plugin đang dùng, thay vì giả định mọi repository được quét từ src/test/resources/contracts.

## 10. CI cần phát hiện hợp đồng bị “rơi khỏi” quá trình sinh test

Một đường dẫn sai đôi khi nguy hiểm hơn một test thất bại: test không được sinh thì cũng không thể báo lỗi.

Quy trình kiểm tra sau một thay đổi về đường dẫn có thể tổ chức như sau:

~~~mermaid
flowchart TD
    A["Đổi/di chuyển thư mục contract"] --> B["Kiểm tra cấu hình contracts root"]
    B --> C["Sinh lại test từ hợp đồng hiện tại"]
    C --> D{"Đủ contract/test mong đợi?"}
    D -->|Không| X["BLOCK: tìm nguyên nhân thiếu test"]
    D -->|Có| E["Kiểm tra package/base class của test"]
    E --> F{"Setup đúng?"}
    F -->|Không| X
    F -->|Có| G["Chạy producer contract tests"]
    G --> H{"PASS?"}
    H -->|Không| X
    H -->|Có| I["Kiểm tra stub sinh ra"]
    I --> J["Consumer test đúng stub version"]
~~~

Điểm cần quan sát không phải chỉ một con số test cố định. Một file có thể khai báo nhiều kịch bản, và cấu trúc sinh test khác nhau giữa cấu hình/phiên bản. Tốt hơn là đối chiếu **danh sách hợp đồng mong đợi** với **những kịch bản thực sự được xử lý**.

Một bản ghi CI hữu ích có thể thể hiện:

~~~yaml
# Mẫu biên bản kiểm tra do nhóm tự thiết kế,
# không phải cấu hình mặc định của Spring Cloud Contract.
contract_source_revision: contracts-commit-abc123
producer_revision: producer-commit-def456
expected_contracts:
  - orders/http/get_paid_order.yml
  - orders/http/get_missing_order.yml
  - orders/messaging/order_paid_event.groovy
generated_tests_reviewed: true
base_class_mapping_reviewed: true
producer_contract_tests: PASS
stub_artifact_version: 2.4.0
consumer_stub_tests: PASS
~~~

Nếu đường dẫn chuyển từ orders/http sang checkout/http, cả danh sách hợp đồng mong đợi và ánh xạ base class cần được review. **Không nên tự động xóa hợp đồng khỏi danh sách mong đợi chỉ để làm CI xanh**.

### Những kiểm tra thực hành quan trọng

1. **Xác nhận root:** generator quét đúng thư mục hợp đồng sau khi thay đổi cấu hình.
2. **Xác nhận phát hiện:** mọi hợp đồng mới, đổi tên hoặc di chuyển đều có mặt trong đầu ra.
3. **Xác nhận test:** xem generated test thực tế, tên package và lớp nền được chọn.
4. **Xác nhận thực thi:** test sinh ra chạy trên producer, không bị skip hoặc lọc nhầm.
5. **Xác nhận stub:** artifact mới chứa đúng kịch bản cần consumer sử dụng.
6. **Xác nhận CI:** consumer dùng artifact stub đúng phiên bản, không trôi sang bản cũ hoặc latest không kiểm soát.

Đối với Maven/Gradle, các đầu ra sinh thường nằm trong thư mục build tương ứng (target hoặc build), nhưng **tên task/goal và thư mục cụ thể phụ thuộc phiên bản plugin**. Khi cần kiểm tra, hãy xem log của quá trình sinh test và các file đầu ra của chính bản build đang dùng.

## 11. Những lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân đường dẫn có thể có | Cách kiểm chứng/khắc phục |
| --- | --- | --- |
| Thêm contract nhưng không thấy test mới | Tệp nằm ngoài contracts root | Đối chiếu root hiệu lực, cấu hình nguồn và danh sách DSL được đọc |
| Test sinh ra nhưng không build | Package hoặc lớp nền không phù hợp | Kiểm tra generated test, baseClassForTests/baseClassMappings |
| Chuyển thư mục xong test dùng sai fixture | Quy tắc mapping dựa trên thư mục đã đổi | Điều chỉnh ánh xạ; xác minh lớp nền thật |
| Test HTTP chạy nhưng message test lỗi | Hợp đồng message chọn setup HTTP | Phân nhóm và ánh xạ lớp nền phù hợp với messaging |
| CI Linux lỗi nhưng máy Windows chạy được | Khác biệt chữ hoa/chữ thường hoặc dấu phân cách đường dẫn | Chuẩn hóa tên và kiểm tra đường dẫn theo môi trường CI |
| Có generated tests nhưng CI không chạy | Bộ lọc, task, cấu hình source-set/test engine không đưa generated tests vào | Kiểm tra test runner và báo cáo số lượng test thực thi |
| Consumer test chỉ PASS với stub cũ | Artifact/version chưa cập nhật sau khi đổi contract | Sinh lại stub, chốt version và chạy lại consumer test |
| Stub không match request dù file ở thư mục đúng | Method/path/header/body match trong DSL không khớp request thực | Kiểm tra nội dung hợp đồng và mapping sinh ra |
| Hai contract có tên giống nhau | Naming không rõ hoặc quy tắc sinh tên gây trùng trong phạm vi nào đó | Đặt tên kịch bản phân biệt; xem lỗi sinh test và artifact |

Không nên xử lý một lỗi đường dẫn bằng cách đổi hành vi nghiệp vụ trong hợp đồng, bỏ test hoặc sửa generated test bằng tay. Generated test là **đầu ra**, nguồn cần sửa thường là DSL, cấu hình phát hiện/mapping hoặc setup của base test class.

## 12. Bài tập thực hành

### Bài tập A — Chẩn đoán contract không được phát hiện

Dự án có thư mục gốc hợp đồng đang cấu hình là src/test/resources/contracts. Một thành viên thêm:

~~~text
src/test/resources/contract/orders/create_order.yml
~~~

Build vẫn xanh và không có test mới cho create_order.

**Yêu cầu:** Xác định lỗi, cách xác nhận test mới đã thực sự được sinh và vì sao không được xem trạng thái build xanh là bằng chứng tương thích.

**Gợi ý:** Tên thư mục contract đang khác contracts. Cần chuyển đúng vị trí hoặc cấu hình lại root có chủ đích, sau đó kiểm tra cả sự hiện diện và thực thi của generated test.

### Bài tập B — Di chuyển hợp đồng làm sai base class

Đội có hai nhóm orders/http và orders/messaging. Một hợp đồng order_paid_event.groovy được chuyển từ messaging sang http nhưng nội dung vẫn mô tả sự kiện.

**Yêu cầu:** Trình bày những điều cần kiểm tra trong generated test, fixture, cách xác minh message và artifact stub trước khi chấp nhận thay đổi.

**Gợi ý:** Rà soát quy tắc base class mapping: test message có thể cần phương thức kích hoạt và verifier riêng. Không đổi contract sang HTTP chỉ vì thư mục mới mang tên http.

### Bài tập C — Đổi thư mục nhưng giữ API

Hợp đồng get_paid_order.yml chuyển từ orders/http sang checkout/http, không đổi request hay response. CI sinh test khác package, test không chạy vì cấu hình bộ lọc cũ.

**Yêu cầu:** Phân biệt thay đổi cấu trúc test với thay đổi hành vi API; đề xuất bước xác minh trước khi công bố producer tương thích.

**Gợi ý:** API chưa chắc đổi, nhưng bằng chứng xác minh bị thiếu do test không thực thi. Chỉnh cấu hình test discovery, chạy lại producer tests, xác nhận stub được sinh và consumer test dùng đúng artifact.

## 13. Checklist khi tổ chức hoặc đổi đường dẫn hợp đồng

- [ ] Mọi Groovy/YAML contract thuộc đúng nguồn và thư mục gốc đã cấu hình.
- [ ] Cấu trúc thư mục phản ánh miền nghiệp vụ hoặc kiểu tích hợp theo quy ước thống nhất.
- [ ] Tên folder phù hợp khi có khả năng dùng để sinh package hoặc ánh xạ base class.
- [ ] Tên file và name của contract mô tả kịch bản rõ ràng, không gây nhầm lẫn hoặc trùng.
- [ ] Đường dẫn tệp, URL HTTP và destination của message được phân biệt rõ.
- [ ] Cấu hình baseClassForTests hoặc baseClassMappings vẫn chọn đúng lớp nền cho mỗi nhóm.
- [ ] Generated tests được sinh **và thực thi**, không chỉ tồn tại trong thư mục build.
- [ ] Sau khi đổi thư mục, so sánh các kịch bản được xử lý để phát hiện test bị rơi khỏi quá trình sinh.
- [ ] Stub được sinh/đóng gói từ đúng contract revision và producer build đã xác minh.
- [ ] Consumer kiểm thử lại với stub version xác định qua Stub Runner.
- [ ] CI chạy được trên môi trường chuẩn, kể cả khác biệt hệ điều hành về đường dẫn.
- [ ] Mọi thay đổi tổ chức đã được xem xét tác động tới test, fixture và quy tắc sở hữu contract.

**Ghi nhớ:** Trong Spring Cloud Contract, quy ước đường dẫn là một phần của **hệ thống sinh và tổ chức kiểm thử**. Đặt DSL đúng nơi chỉ là bước đầu; hãy xác minh nó được phát hiện, gắn đúng lớp nền, sinh ra test/stub mong đợi và được chạy trong CI. Chỉ khi có đủ các bằng chứng này, việc đổi hoặc mở rộng cấu trúc thư mục mới không làm mất âm thầm khả năng phát hiện thay đổi API không tương thích.
