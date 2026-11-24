# Classifier, group ID, artifact ID và version

## Mục tiêu bài học

Trong **Spring Cloud Contract**, producer khai báo hành vi HTTP hoặc thông điệp bằng **Groovy DSL** hay **YAML DSL**. Từ các hợp đồng, **Contract Verifier** sinh kiểm thử phía producer và tạo **stub** để consumer dùng qua **Stub Runner**. Khi producer được xây dựng và phát hành, các stub thường được đóng gói thành một **artifact riêng có classifier**, được quản lý và tải theo tọa độ tương tự dependency Maven.

Tọa độ của stub là một phần thiết yếu trong quy trình CI phát hiện thay đổi API không tương thích. Nếu consumer vô tình tải stub của service khác, phiên bản khác hoặc artifact không có classifier `stubs`, bộ kiểm thử có thể thất bại vì không tìm thấy stub; nguy hiểm hơn, consumer có thể PASS với **stub cũ** và kết luận sai rằng producer mới vẫn tương thích.

Trong chương **Sinh và đóng gói stub**, bài này tập trung vào bốn thành phần **group ID, artifact ID, version và classifier**, cách chúng liên kết với tệp stub JAR, artifact repository, Stub Runner và bằng chứng kiểm thử.

Sau bài học, bạn có thể:

- Đọc và giải thích tọa độ `groupId:artifactId:version:classifier`.
- Phân biệt artifact chính của producer với stub artifact cùng version, thường có classifier `stubs`.
- Hiểu cách một bản hợp đồng tạo ra generated producer tests, stub mapping và stub JAR.
- Cấu hình consumer test dùng đúng stub bằng Stub Runner trong các chế độ tìm artifact phù hợp.
- Xử lý các lỗi thiếu artifact, sai classifier, sai version hoặc trùng tên giữa nhiều service.
- Xây dựng release gate bảo đảm stub và producer build xuất phát từ cùng revision hợp đồng đã được kiểm thử.

## 1. Vì sao cần tọa độ riêng cho stub?

Hãy hình dung hai service:

- **Order Service** là producer của endpoint `GET /api/orders/{id}`.
- **Checkout Service** là consumer, gọi Order Service trong quy trình thanh toán.

Khi viết consumer tests, Checkout Service không nhất thiết phải khởi động toàn bộ Order Service với database, queue và các dependency của nó. Thay vào đó, Checkout có thể dùng **stub HTTP** mô phỏng những request/response đã được thỏa thuận.

~~~mermaid
flowchart TD
    A["Hợp đồng Groovy/YAML<br/>Order Service"] --> B["Spring Cloud Contract Verifier"]
    B --> C["Generated producer tests"]
    B --> D["Stub mappings + responses"]
    C --> E["Order Service build<br/>producer test PASS"]
    D --> F["Stub JAR có classifier stubs"]
    E --> G["Release gate"]
    F --> G
    G --> H["Artifact repository<br/>tọa độ G:A:V:stubs"]
    H --> I["Checkout CI<br/>Stub Runner tải stub đúng version"]
    I --> J["Consumer integration tests"]
~~~

**Artifact repository** ở đây có thể là Maven repository nội bộ hoặc kho artifact tương thích với cơ chế phân giải của Stub Runner. Nó khác với chính HTTP endpoint mà stub sẽ phục vụ khi chạy test.

Một stub JAR cần có danh tính để nhiều consumer tải đúng bản. Tên tệp một mình chưa đủ vì nhiều nhóm có thể có module cùng tên hoặc nhiều lần phát hành khác nhau.

## 2. Bốn thành phần của tọa độ artifact

Giả sử producer được khai báo với tọa độ Maven:

~~~xml
<groupId>com.example.orders</groupId>
<artifactId>order-service</artifactId>
<version>1.4.2</version>
~~~

Stub được phát hành cùng tọa độ cơ sở nhưng có classifier `stubs`:

~~~text
groupId     = com.example.orders
artifactId  = order-service
version     = 1.4.2
classifier  = stubs

Tọa độ ngắn cho stub:
com.example.orders:order-service:1.4.2:stubs
~~~

| Thành phần | Ví dụ | Nhiệm vụ |
| --- | --- | --- |
| **group ID / groupId** | `com.example.orders` | Nhóm định danh sở hữu artifact, giúp phân biệt các module ở những namespace khác nhau |
| **artifact ID / artifactId** | `order-service` | Tên module/artifact cụ thể được phát hành |
| **version** | `1.4.2` | Phân biệt các bản build/phát hành có thể có hành vi khác nhau |
| **classifier** | `stubs` | Phân biệt biến thể stub với artifact chính có cùng group ID, artifact ID và version |

**Cần nhớ:** classifier **không phải** là một phần của tên HTTP endpoint, package Java hay tên class. Nó là thuộc tính của **artifact được xuất bản**.

### So sánh artifact chính và stub

~~~text
Artifact chính của producer:
  com.example.orders:order-service:1.4.2
  order-service-1.4.2.jar

Stub artifact:
  com.example.orders:order-service:1.4.2:stubs
  order-service-1.4.2-stubs.jar
~~~

Thông thường, hai artifact có cùng `groupId`, `artifactId` và `version` nhưng khác `classifier`. Artifact chính chứa ứng dụng/thư viện; stub artifact chứa nội dung cần thiết để consumer test mô phỏng hành vi đã công bố.

Tên tệp là **ví dụ theo quy ước Maven thông dụng**. Đầu ra cụ thể và cơ chế đóng gói phụ thuộc plugin, cấu hình dự án và loại artifact.

## 3. Tọa độ Maven không phải tọa độ Docker hay địa chỉ stub server

Những định danh sau có mục đích khác nhau:

| Định danh | Ví dụ | Đại diện cho |
| --- | --- | --- |
| Maven group ID | `com.example.orders` | Namespace của artifact trong repository |
| Maven artifact ID | `order-service` | Tên module/artifact |
| Maven version | `1.4.2` | Phiên bản artifact |
| Classifier | `stubs` | Biến thể stub JAR |
| Docker image tag | `order-service:1.4.2` | Phiên bản image triển khai, không tự động là stub coordinate |
| Stub server port | `8090` | Cổng mà stub server lắng nghe khi consumer test chạy |
| HTTP URL | `/api/orders/ORD-1001` | Endpoint được mô phỏng bởi stub |

Một consumer có thể dùng cổng `8090` để gọi stub của producer version `1.4.2`. **8090 không phải version**. Tương tự, tên Spring Boot application hoặc package Java không phải nguồn đáng tin duy nhất để suy ra group/artifact ID.

Nếu hệ thống có nhiều module, hãy xác minh **module nào thực sự phát hành stub**. Một module `order-contracts` có thể được sử dụng làm nguồn hợp đồng, trong khi artifact stub mà Stub Runner cần lại được publish dưới `order-service`.

## 4. Stub JAR thường chứa gì?

Một HTTP stub được tạo từ contract có thể bao gồm:

- **Request mapping:** điều kiện match HTTP method, URL, query parameters, headers và body.
- **Response definition:** status, headers, body, file body hoặc các thành phần response tương ứng.
- **Contract source:** bản sao DSL hoặc metadata để truy vết nội dung hợp đồng, tùy cách đóng gói.
- **Thông tin tổ chức/đường dẫn:** giúp cơ chế Stub Runner tìm mapping cho đúng artifact.

Ví dụ một cách tổ chức thường gặp dưới `META-INF`:

~~~text
order-service-1.4.2-stubs.jar
└── META-INF/
    └── com.example.orders/
        └── order-service/
            └── 1.4.2/
                ├── mappings/
                │   └── get-paid-order.json
                └── contracts/
                    └── get-paid-order.yml
~~~

Đây là **cấu trúc minh họa**. Tên file, thư mục chính xác và việc có thêm tài nguyên phụ trợ phụ thuộc vào version/plugin/cấu hình; cần kiểm tra **nội dung JAR thực tế** đã sinh. Không nên dựa vào một sơ đồ minh họa để kết luận JAR của dự án đã được đóng gói đúng.

Ví dụ mapping rút gọn cho endpoint:

~~~json
{
  "request": {
    "method": "GET",
    "url": "/api/orders/ORD-1001"
  },
  "response": {
    "status": 200,
    "headers": {
      "Content-Type": "application/json"
    },
    "jsonBody": {
      "id": "ORD-1001",
      "status": "PAID"
    }
  }
}
~~~

Đây là **bản minh họa WireMock-style**, không phải output nguyên văn của một phiên bản Contract Verifier. Mapping thực có thể có thêm matcher cho header/body, điều kiện priority hoặc cách khai báo response khác.

**Stub JAR không phải bản sao toàn bộ producer.** Stub mô phỏng các kịch bản được khai báo, không tự mang theo database, logic nghiệp vụ và tất cả hành vi production.

## 5. Từ contract đến artifact: hai việc phải kiểm chứng riêng

Producer có hợp đồng:

~~~yaml
description: "Lấy đơn hàng đã thanh toán"
name: get_paid_order
request:
  method: GET
  url: /api/orders/ORD-1001
response:
  status: 200
  headers:
    Content-Type: application/json
  body:
    id: ORD-1001
    status: PAID
~~~

Build cần thực hiện hai việc **có liên quan nhưng không thay thế nhau**:

1. **Sinh và chạy producer contract tests**: xác minh phiên bản producer đang được build đáp ứng request/response như hợp đồng.
2. **Sinh và đóng gói stubs**: tạo artifact chứa mapping/response để consumer có thể sử dụng.

| Câu hỏi | Loại bằng chứng cần có |
| --- | --- |
| Producer có trả 200/JSON đúng không? | Kết quả generated producer tests đã được thực thi |
| Stub JAR có mapping đó không? | Kiểm tra nội dung JAR đã đóng gói |
| Consumer có tải đúng stub không? | Tọa độ, phiên bản và log phân giải artifact |
| Consumer xử lý response đúng không? | Consumer integration tests với Stub Runner |
| Producer mới tương thích mọi consumer không? | Kết quả từ các consumer và kịch bản cần hỗ trợ, không chỉ một stub test |

Một test producer PASS không tự chứng minh artifact đã được publish đúng repository; một JAR tồn tại cũng không tự chứng minh producer đã chạy contract tests.

## 6. Sinh và đóng gói với Maven

Trong dự án Maven, Spring Cloud Contract thường được cấu hình bằng `spring-cloud-contract-maven-plugin`.

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-contract-maven-plugin</artifactId>
            <version>VERSION_PHU_HOP</version>
            <extensions>true</extensions>
            <configuration>
                <contractsDirectory>
                    src/test/resources/contracts
                </contractsDirectory>
                <baseClassForTests>
                    com.example.orders.contract.OrderContractBase
                </baseClassForTests>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

`VERSION_PHU_HOP` là placeholder cần thay bằng version tương thích với bộ Spring Boot/Spring Cloud và cấu hình dự án. Đây **chưa phải POM hoàn chỉnh**, vì còn phụ thuộc thư viện test và các phần cấu hình khác.

Khi plugin và vòng đời build được nối đúng, quá trình build có thể sinh tests/stubs, rồi tạo artifact có classifier `stubs` ở pha đóng gói. Các mục tiêu/lifecycle cụ thể cần kiểm tra theo version plugin. Đừng suy luận rằng một Maven command đã phát hành stub chỉ vì nó kết thúc với exit code 0.

Một quy trình minh họa ở môi trường phát triển:

~~~text
./mvnw clean verify
  -> sinh và chạy producer contract tests
  -> kiểm tra số lượng generated tests thực thi
  -> kiểm tra stub được tạo/đóng gói theo lifecycle

./mvnw install
  -> cài artifact đã đóng gói vào local Maven repository
  -> cần xác minh cả stub classifier đã được cài
~~~

Trong CI, bước publish lên artifact repository thường là một pha được kiểm soát riêng, chỉ cho phép sau các kiểm tra producer và artifact đã PASS. Một số cấu hình dùng Maven `deploy` hoặc cơ chế phát hành của tổ chức; điều quan trọng là kiểm tra **tọa độ và nội dung** sau publish.

### Phụ thuộc Maven vào stub

Nếu một test consumer cần khai báo stub như dependency Maven, có thể dùng:

~~~xml
<dependency>
    <groupId>com.example.orders</groupId>
    <artifactId>order-service</artifactId>
    <version>1.4.2</version>
    <classifier>stubs</classifier>
    <type>jar</type>
    <scope>test</scope>
</dependency>
~~~

Đây là cách thể hiện đầy đủ các thành phần trong **dependency declaration**. Stub Runner có cú pháp ID riêng để chọn artifact và port khi chạy test; không sao chép thứ tự các trường trong một dạng tọa độ sang dạng khác một cách máy móc.

## 7. Sinh và đóng gói với Gradle

Với Gradle, có thể sử dụng plugin Spring Cloud Contract cùng cấu hình contracts:

~~~groovy
plugins {
    id 'org.springframework.cloud.contract' version 'VERSION_PHU_HOP'
}

group = 'com.example.orders'
version = '1.4.2'

contracts {
    contractsDslDir = file('src/test/resources/contracts')
    baseClassForTests =
        'com.example.orders.contract.OrderContractBase'
}
~~~

Đây là **Gradle Groovy DSL**, không phải cú pháp của Kotlin DSL. Ngoài ra, ứng dụng thật cần các dependencies, test framework và cấu hình source set tương ứng.

Ở các phiên bản hỗ trợ, Spring Cloud Contract Gradle plugin cung cấp task liên quan đến sinh test và đóng gói stub, thường thấy tên như `generateContractTests` hoặc `verifierStubsJar`. **Tên task, quan hệ phụ thuộc, classifier và cách đưa stub JAR vào publication phải được xác minh trên version plugin đang dùng**.

Không nên mặc định `./gradlew build` sẽ publish artifact. Build nội bộ, publish vào Maven local và publish lên remote repository là ba hoạt động khác nhau:

~~~text
Sinh và test:
  ./gradlew clean build

Đưa artifact vào kho local nếu dự án có maven-publish:
  ./gradlew publishToMavenLocal

Publish remote:
  dùng task publication/repository đã cấu hình và phê duyệt
~~~

**Trước khi publish**, kiểm tra artifact có classifier `stubs` thật sự được gắn vào Maven publication. Nếu Gradle chỉ publish JAR chính, consumer sẽ không thể tải `order-service:1.4.2:stubs` dù producer tests đều PASS.

### Phân biệt tên Gradle project và artifact ID

`group` và `version` là metadata thường gặp trong Gradle, nhưng `artifactId` của publication có thể phụ thuộc vào tên project hoặc `MavenPublication` đã cấu hình. Một project tên `order-service-app` có thể phát hành artifact ID `order-service` nếu publication được cấu hình như vậy.

**Không suy artifact ID từ tên thư mục build**. Kiểm tra metadata của Maven publication sau khi publish và dùng chính tọa độ đó trong Stub Runner.

## 8. Stub Runner chọn đúng artifact như thế nào?

Ở phía consumer, **Stub Runner** có thể tải stub JAR từ local Maven repository hoặc remote artifact repository và khởi động stub server.

Ví dụ consumer integration test:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.contract.stubrunner.spring.AutoConfigureStubRunner;
import org.springframework.cloud.contract.stubrunner.spring.StubRunnerProperties;

@SpringBootTest
@AutoConfigureStubRunner(
    ids = {"com.example.orders:order-service:1.4.2:stubs:8090"},
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
class CheckoutContractIntegrationTest {

    @Test
    void checkoutShouldHandlePaidOrder() {
        // Cấu hình HTTP client của Checkout gọi stub trên cổng 8090.
        // Thực hiện nghiệp vụ Checkout và assert kết quả consumer.
    }
}
~~~

Đoạn mã chỉ minh họa **cách khai báo Stub Runner**, không phải một test hoàn chỉnh. Consumer còn cần các dependencies và cấu hình test phù hợp để trỏ HTTP client đến stub server đã được khởi động.

Trong ví dụ này, Stub Runner ID có năm phần:

~~~text
com.example.orders:order-service:1.4.2:stubs:8090
        |               |       |     |    |
      group           artifact version classifier port
~~~

| Thành phần | Giá trị | Cần hiểu |
| --- | --- | --- |
| group | `com.example.orders` | Namespace artifact |
| artifact | `order-service` | Artifact cung cấp stub |
| version | `1.4.2` | Version cụ thể được kiểm tra |
| classifier | `stubs` | Chọn stub JAR, không phải JAR ứng dụng chính |
| port | `8090` | Cổng stub server dùng trong test |

**Port không thuộc tọa độ Maven của artifact.** Port là tham số chạy Stub Runner trong cú pháp ID này. Khi thay port sang `8091`, không có nghĩa artifact đã đổi version hoặc classifier.

### Một số trường có thể được bỏ qua

Các phiên bản Stub Runner hỗ trợ dạng ID với những thành phần tùy chọn và khả năng chọn port động. Đừng tự đoán cách parser hiểu một chuỗi thiếu field khi làm ví dụ quan trọng; hãy dùng **tọa độ đầy đủ, tường minh** để giảm nhầm lẫn, rồi điều chỉnh theo tài liệu của phiên bản đang dùng.

## 9. Chế độ LOCAL, REMOTE và CLASSPATH

Tọa độ giống nhau chưa đủ; cần biết **Stub Runner sẽ lấy artifact từ đâu**.

| Chế độ | Ý nghĩa khái quát | Điểm cần chú ý |
| --- | --- | --- |
| **LOCAL** | Tìm stub trong Maven repository trên máy chạy test | Cần cài/publish local artifact đúng version trước khi test |
| **REMOTE** | Phân giải từ repository được cấu hình | Phụ thuộc repository URL, quyền truy cập, metadata và chính sách cache |
| **CLASSPATH** | Sử dụng stub hiện diện trong classpath theo cơ chế hỗ trợ | Cần bảo đảm đúng resource/JAR trên classpath và giải quyết tên/phiên bản phù hợp |

Ví dụ chọn remote repository bằng cấu hình annotation khi phiên bản hỗ trợ:

~~~java
@AutoConfigureStubRunner(
    ids = {"com.example.orders:order-service:1.4.2:stubs:8090"},
    stubsMode = StubRunnerProperties.StubsMode.REMOTE,
    repositoryRoot = "https://repo.example.test/maven-releases"
)
~~~

Địa chỉ `repo.example.test` là **URL minh họa**, không phải repository thực. Khi triển khai, credential của kho artifact cần được quản lý qua cơ chế secret của môi trường CI; không ghi username/password hoặc token production vào source contract.

Nếu consumer chạy LOCAL mà chỉ publish stub lên remote, Stub Runner có thể báo không tìm thấy artifact; nếu chạy REMOTE nhưng repositoryRoot trỏ sai hoặc token không đủ quyền, lỗi có thể là lỗi phân giải, không phải lỗi hành vi API.

## 10. Stub JAR có classifier khác JAR chính như thế nào?

Một lỗi hay gặp là consumer chỉ dùng:

~~~text
com.example.orders:order-service:1.4.2
~~~

trong khi bản cần tải là:

~~~text
com.example.orders:order-service:1.4.2:stubs
~~~

Hai tọa độ không chỉ khác ký tự. Chúng yêu cầu **hai biến thể artifact**:

- Artifact không có classifier có thể là JAR ứng dụng producer.
- Artifact với classifier `stubs` là bộ stub được thiết kế để consumer test.

Không nên sửa artifact ID thành `order-service-stubs` nếu dự án phát hành đúng một artifact có classifier `stubs`, vì đó là một tọa độ khác. Ngược lại, nếu một nhóm **cố ý** publish stubs như artifact ID riêng, cần dùng chính tọa độ được publication khai báo thay vì suy từ quy ước mặc định.

### Phân giải trong Maven repository

Giả sử groupId `com.example.orders`, artifactId `order-service`, version `1.4.2`. Một Maven repository chuẩn có thể tổ chức:

~~~text
com/example/orders/order-service/1.4.2/
├── order-service-1.4.2.pom
├── order-service-1.4.2.jar
└── order-service-1.4.2-stubs.jar
~~~

Đường dẫn Maven repository phân chia group ID theo dấu chấm thành thư mục; đó là **quy ước lưu trữ artifact**, khác với cách nội dung `META-INF` được đóng gói bên trong JAR.

Nếu `order-service-1.4.2.jar` tồn tại nhưng `order-service-1.4.2-stubs.jar` không tồn tại, cần kiểm tra pha sinh stub, gắn artifact classifier và publication. Không tự kết luận stub bị lỗi matcher.

## 11. Group ID và artifact ID trong dự án nhiều module

Giả sử hệ thống có cấu trúc:

~~~text
commerce-platform/
├── order-api/
├── order-domain/
├── order-service/
├── order-contracts/
└── checkout-service/
~~~

Cần trả lời **artifact nào thực sự publish stubs**:

| Module | Có thể làm gì? | Không nên suy luận |
| --- | --- | --- |
| `order-api` | Chứa interface/DTO công khai | Không nhất thiết là nơi phát hành stub |
| `order-domain` | Logic nghiệp vụ | Không nhất thiết có HTTP/message contract |
| `order-service` | Producer chạy endpoint | Có thể publish stubs theo tọa độ của service |
| `order-contracts` | Chứa nguồn DSL dùng chung | Không mặc định có một Stub Runner artifact giống tên module |
| `checkout-service` | Consumer | Không tải stub theo artifact ID của chính consumer |

Với hợp đồng lưu ở repository riêng, vị trí source contract và tọa độ stub xuất bản có thể khác nhau. CI phải ghi lại:

- Revision của repository hợp đồng.
- Producer module/build đã sinh và xác minh tests.
- Artifact có classifier `stubs` được publish từ build đó.
- Consumer version dùng stub artifact nào.

Nếu có hai producer cùng artifactId `service-api` nhưng thuộc hai groupId khác nhau, Stub Runner phải dùng **group ID đúng** để không tải nhầm.

## 12. Versioning: vì sao không nên dùng phiên bản động trong CI release?

Trong giai đoạn phát triển, người viết test có thể dùng phiên bản động hoặc `+` trong cú pháp Stub Runner (nếu phiên bản thư viện hỗ trợ). Cách này thuận tiện khi thử nhanh, nhưng không phù hợp với mọi release gate.

Ví dụ **không nên dùng làm bằng chứng phát hành không thay đổi**:

~~~java
@AutoConfigureStubRunner(
    ids = {"com.example.orders:order-service:+:stubs:8090"}
)
~~~

Nếu `+` phân giải sang phiên bản mới nhất theo repository/cơ chế hỗ trợ, cùng một consumer commit có thể tải **hai stub khác nhau** ở hai lần chạy. Kết quả CI sẽ khó tái lập.

Đối với xác minh trước phát hành, nên chọn version cố định:

~~~text
Producer build chuẩn bị phát hành: order-service 1.4.2
Contract revision:            contracts commit def456
Stub artifact:                com.example.orders:order-service:1.4.2:stubs
Consumer dùng stub version:   1.4.2
~~~

**Version cố định không tự đảm bảo artifact bất biến.** Nếu repository cho phép ghi đè release cùng version, cùng tọa độ có thể trỏ tới bytes mới. Release gate nên dùng chính sách artifact immutable, checksum và metadata truy vết.

### SNAPSHOT và release version

| Loại version | Ví dụ | Đặc điểm cần xét |
| --- | --- | --- |
| **SNAPSHOT** | `1.4.3-SNAPSHOT` | Thường được dùng trong quá trình phát triển và có thể cập nhật nội dung theo thời gian |
| **Release** | `1.4.2` | Nên gắn một tập bytes cố định sau khi phát hành |
| **Dynamic/range** | `+` hoặc dạng mà công cụ hỗ trợ | Có thể phân giải tới artifact khác ở lần chạy tiếp theo |

Không có quy tắc “cứ tăng patch/minor thì chắc chắn tương thích”. **Tương thích là thuộc tính được kiểm chứng bằng hợp đồng và các consumer còn hoạt động**, không thể suy ra chỉ từ quy ước đánh số.

## 13. Tính tương thích giữa các version cần được kiểm tra theo cặp

Giả sử producer chuẩn bị phát hành `1.5.0`. Consumer cũ `checkout-service:2.8.0` vẫn cần endpoint và schema của `1.4.2`.

| Producer/stub được xem xét | Consumer đang kiểm tra | Câu hỏi |
| --- | --- | --- |
| Producer 1.4.2 + stubs 1.4.2 | Checkout 2.8.0 | Baseline cũ hoạt động không? |
| Producer 1.5.0 + stubs 1.5.0 | Checkout 2.8.0 | Consumer cũ còn tương thích với producer mới không? |
| Producer 1.5.0 + stubs 1.5.0 | Checkout 2.9.0 | Consumer mới có hoạt động với giao diện mới không? |

Nếu Checkout 2.8.0 PASS với stub 1.4.2, **không thể kết luận** nó PASS với producer 1.5.0. Muốn biết tương thích ngược, phải kiểm thử Checkout 2.8.0 với **stub mới** từ producer 1.5.0, cùng với bằng chứng producer test tương ứng.

Một thay đổi như:

~~~text
Trước: GET /api/orders/ORD-1001 -> {"status":"PAID"}
Sau:   GET /api/orders/ORD-1001 -> {"paymentStatus":"PAID"}
~~~

có thể phá consumer dù HTTP status và URL không đổi. Chính phiên bản stub mới giúp consumer test nhận ra khác biệt, miễn là hợp đồng mới đã được thiết kế đúng và consumer thực sự kiểm tra trường đang dùng.

## 14. CI cần kiểm chứng điều gì trước khi xuất bản stubs?

### Pipeline khuyến nghị

~~~mermaid
flowchart TD
    A["Checkout producer + contract revision"] --> B["Xác minh đúng tọa độ G:A:V"]
    B --> C["Sinh producer contract tests và stubs"]
    C --> D{"Generated tests thực sự chạy PASS?"}
    D -->|Không| X["BLOCK"]
    D -->|Có| E["Kiểm tra JAR classifier stubs"]
    E --> F{"Mapping/response đúng và đủ?"}
    F -->|Không| X
    F -->|Có| G["Publish artifact/version bất biến"]
    G --> H["Consumer CI phân giải G:A:V:stubs"]
    H --> I{"Đúng artifact và checksum?"}
    I -->|Không| X
    I -->|Có| J["Chạy Stub Runner và consumer tests"]
    J --> K{"Consumer PASS?"}
    K -->|Không| X
    K -->|Có| L["Lưu evidence và quyết định rollout"]
~~~

Những điều nên kiểm tra:

1. **Group/artifact/version** thực sự là của producer cần kiểm chứng, không phải module giả định.
2. **Contracts được phát hiện đầy đủ**, không phải 0 hợp đồng vì sai thư mục.
3. **Generated producer tests được chạy**, không bị skip hoặc exclude.
4. **Stub JAR có classifier chính xác**, không chỉ có application JAR.
5. **Stub JAR chứa đúng các mapping** từ revision hợp đồng đã test và không có dữ liệu production nhạy cảm.
6. **Artifact publish thành công** đến repository mong muốn, metadata/version/checksum có thể truy vết.
7. **Consumer CI chạy với stub mới**, không vô tình dùng local cache hay một bản cũ.
8. **Consumer tests có assertion về logic consumer**, thay vì chỉ xác nhận stub server đã khởi động.

### Ví dụ biên bản build

~~~yaml
# Minh họa evidence do dự án tự thiết kế,
# không phải output mặc định của Spring Cloud Contract.
producer_module: order-service
producer_revision: "producer@abc123"
contracts_revision: "contracts@def456"
group_id: com.example.orders
artifact_id: order-service
version: "1.4.2"
classifier: stubs
expected_contracts:
  - get_paid_order
  - get_missing_order
generated_producer_tests: PASS
stub_jar_verified: true
stub_artifact: "com.example.orders:order-service:1.4.2:stubs"
consumer_version: "checkout-service:2.8.0"
consumer_stub_tests: PASS
~~~

Một dòng `stub_jar_verified: true` chỉ có giá trị khi CI thực sự kiểm tra nội dung, không phải do người viết YAML tự khai báo cho đẹp. Cần có báo cáo build/test và bước kiểm tra artifact làm bằng chứng.

## 15. Lỗi thường gặp khi resolve stub artifact

| Triệu chứng | Nguyên nhân khả dĩ | Cách kiểm tra |
| --- | --- | --- |
| Stub Runner báo không thấy artifact | Sai group ID, artifact ID, version hoặc classifier | Đối chiếu publication metadata và tọa độ consumer dùng |
| Có application JAR nhưng không có stubs JAR | Stub classifier chưa được đóng gói/publish | Kiểm tra plugin task/lifecycle, publication |
| Đúng artifact ID nhưng tải nhầm service | Group ID khác hoặc trùng tên giữa namespace | Dùng đầy đủ group ID |
| Test dùng `latest`/`+` và thay kết quả | Version động phân giải tới artifact mới | Chốt version và checksum |
| Consumer CI vẫn PASS sau breaking change | Đang dùng stub cũ hoặc không assert trường thay đổi | Kiểm tra log tải artifact, contract revision và assertions |
| LOCAL không tìm thấy stub | Stub chưa install vào Maven local của môi trường chạy | Cài đúng artifact hoặc dùng REMOTE được cấu hình |
| REMOTE thất bại nhưng LOCAL PASS | Sai repositoryRoot, quyền hoặc metadata | Kiểm tra URL repository, credential, proxy, cache |
| Stub server chạy nhưng endpoint trả 404 | Mapping không match request hoặc stub sai | Kiểm tra method/URL/headers/body và mapping trong JAR |
| Test chỉ chạy trên máy người viết | Phụ thuộc artifact trong Maven local không publish | Dùng repository CI có kiểm soát và build độc lập |
| Không thấy sự thay đổi khi đã publish lại | Repository/cache vẫn giữ bytes cũ hoặc release bị ghi đè | So sánh checksum/metadata, tránh overwrite release |

Đừng vội sửa contract khi lỗi là **phân giải artifact**. Cần tách bốn câu hỏi:

- Artifact có tồn tại không?
- Nó có đúng classifier và version không?
- Bên trong có mapping mong muốn không?
- Mapping có match request consumer gửi hay không?

Nếu ba bước đầu sai, việc nới lỏng matcher thường chỉ che đi nguyên nhân thực sự.

## 16. Phân biệt hợp đồng HTTP và thông điệp khi đóng gói

Với HTTP, stub artifact thường chứa mapping để stub server mô phỏng response. Với **message contract**, artifact có thể chứa những thông tin/stub được Stub Runner messaging hỗ trợ nhằm phát message mẫu qua **label/trigger** theo tích hợp tương ứng.

| Đặc điểm | HTTP contract | Message contract |
| --- | --- | --- |
| Input thường gặp | Method/URL/header/body | `triggeredBy` hoặc `messageFrom` |
| Output | HTTP response | `outputMessage` với body, headers, `sentTo` |
| Consumer test | Gọi HTTP stub server | Kích hoạt/nhận message stub tùy adapter |
| Artifact | Có thể dùng stub classifier `stubs` | Cũng cần artifact/version đúng; cơ chế message trigger phụ thuộc hỗ trợ |
| Hạ tầng bổ sung | Stub server HTTP | Binder/broker/message verifier theo cấu hình |

Đừng suy luận rằng stub JAR chứa message contract thì Stub Runner **tự tạo** Kafka topic, RabbitMQ exchange hoặc JMS queue production. Consumer cần cấu hình môi trường test tương thích với adapter và kịch bản message stub được dùng.

Group ID, artifact ID, version và classifier vẫn giúp xác định **đúng nguồn stub**, nhưng chúng không mô tả toàn bộ cấu hình broker.

## 17. Bảo mật và quản trị artifact

Stub JAR thường được chia sẻ rộng hơn source code của producer. Nó có thể chứa payload mẫu, headers, response body và metadata. Vì vậy:

- Dùng **dữ liệu tổng hợp**; không sao chép email, tài khoản, token hoặc giao dịch production vào hợp đồng.
- Không đưa API key, bearer token, mật khẩu hoặc URL quản trị bí mật vào stub mappings.
- Rà soát artifact đã đóng gói, không chỉ rà soát source Groovy/YAML.
- Quản lý quyền đọc/ghi của repository và credential CI theo nguyên tắc cấp quyền tối thiểu.
- Không ghi token truy cập repository vào test source hoặc log khi phân giải artifact thất bại.
- Giữ chính sách retention và quy trình thu hồi/đổi secret nếu artifact cũ từng chứa dữ liệu nhạy cảm.

Việc nâng version mới không tự xóa dữ liệu từng bị rò rỉ trong artifact version cũ. Nếu phát hiện secret trong stubs JAR đã phát hành, cần xử lý theo quy trình sự cố, không chỉ chỉnh file hợp đồng.

## 18. Bài tập thực hành

### Bài tập A — Đọc tọa độ

Cho Stub Runner ID:

~~~text
vn.learning.platform:inventory-service:3.2.1:stubs:8100
~~~

**Yêu cầu:** xác định group ID, artifact ID, version, classifier và cổng; giải thích thành phần nào **không** thuộc tọa độ artifact Maven.

**Gợi ý:** `8100` là port của stub server. Bốn thành phần trước đó xác định stub artifact.

### Bài tập B — Tìm lý do thiếu JAR

Maven repository có:

~~~text
inventory-service-3.2.1.pom
inventory-service-3.2.1.jar
~~~

Consumer cấu hình `vn.learning.platform:inventory-service:3.2.1:stubs:8100` nhưng không tải được.

**Yêu cầu:** xác định file còn thiếu và nơi cần kiểm tra trong pipeline producer.

**Gợi ý:** thiếu `inventory-service-3.2.1-stubs.jar`. Kiểm tra sinh stub, gắn classifier, publish và phiên bản thực tế.

### Bài tập C — Chọn artifact đúng trong multi-module

Một repository có `order-api`, `order-domain`, `order-service` và `checkout-service`. Hợp đồng ở module `order-api` nhưng build `order-service` mới sinh và publish stubs.

**Yêu cầu:** consumer phải dùng artifact ID nào? Tại sao không chọn tự động theo thư mục chứa file DSL?

**Gợi ý:** dùng tọa độ của publication thật sự chứa stub, được metadata và CI xác minh.

### Bài tập D — Rủi ro version động

Consumer CI dùng `com.example.orders:order-service:+:stubs:8090`. Hôm thứ Hai CI PASS; hôm thứ Ba có producer version mới và CI FAIL dù commit Checkout không đổi.

**Yêu cầu:** giải thích tính không tái lập và cách sửa release gate.

**Gợi ý:** chốt version stub, kiểm tra checksum/provenance, ghi rõ producer/contract revision và chạy lại consumer test theo cặp version cần hỗ trợ.

### Bài tập E — Breaking change bị bỏ sót

Order Service 1.5.0 đổi response JSON từ `status` thành `paymentStatus`. Checkout 2.8.0 vẫn dùng stub 1.4.2 và báo PASS.

**Yêu cầu:** có thể phát hành Order Service 1.5.0 không? Cần những kiểm tra nào?

**Gợi ý:** phải test producer với contract revision tương ứng, sinh/publish stub 1.5.0 rồi chạy Checkout 2.8.0 với stub mới. Cần xem các consumer đang phụ thuộc trường cũ và kế hoạch tương thích ngược.

### Bài tập F — Tạo checklist kiểm tra artifact

Thiết kế bước CI xác nhận:

1. Producer contract tests có chạy và PASS.
2. Stub artifact đúng `group:artifact:version:stubs`.
3. Artifact chứa đủ HTTP mappings mong đợi.
4. Artifact không có dữ liệu production nhạy cảm.
5. Consumer test tải đúng version và không dùng bản cache cũ.

**Gợi ý:** kết hợp test reports, danh sách contract/stub mappings, Maven publication metadata, checksum và log phân giải của Stub Runner. Đừng coi việc tồn tại một file `-stubs.jar` là đủ.

## 19. Checklist trước khi công bố stub artifact

- [ ] Biết rõ group ID và artifact ID của **publication chứa stub**, không suy từ tên package hoặc thư mục.
- [ ] Version của producer build, contract revision và stub artifact được gắn với nhau.
- [ ] Classifier đúng `stubs` theo quy ước/cấu hình của dự án.
- [ ] Stub JAR được phân biệt với application JAR cùng group/artifact/version.
- [ ] Cấu hình Maven hoặc Gradle thực sự sinh và gắn stub artifact vào publication.
- [ ] Hợp đồng mong đợi được phát hiện đầy đủ; generated producer tests thực sự được chạy PASS.
- [ ] Stub artifact chứa đúng mappings/responses hoặc message stub được kỳ vọng.
- [ ] Artifact không chứa dữ liệu production nhạy cảm hoặc credentials thật.
- [ ] Repository URL/quyền truy cập và stubsMode của consumer được cấu hình phù hợp.
- [ ] Consumer Stub Runner dùng đúng tọa độ, classifier và version; port không bị nhầm với version.
- [ ] Release gate không phụ thuộc phiên bản động khi cần kết quả có thể tái lập.
- [ ] Tọa độ release bất biến hoặc ít nhất được xác minh bằng checksum và metadata.
- [ ] Consumer test assert logic thật, không chỉ kiểm tra stub server đã khởi động.
- [ ] Các consumer cũ được kiểm tra với **stub mới** khi producer có thay đổi có thể phá vỡ API.
- [ ] Báo cáo CI lưu producer build, contract revision, stub version và consumer versions đã kiểm tra.

**Ghi nhớ:** `group ID` xác định namespace, `artifact ID` xác định module được phát hành, `version` chọn đúng bản, còn `classifier = stubs` chọn **bộ stub** thay vì JAR chính. Stub Runner cần đúng tọa độ và nguồn phân giải để consumer test có ích. Tương thích API chỉ có bằng chứng đáng tin khi stub artifact được sinh từ cùng hợp đồng đã kiểm chứng producer, phát hành có truy vết và thực sự được consumer dùng ở phiên bản mong muốn.
