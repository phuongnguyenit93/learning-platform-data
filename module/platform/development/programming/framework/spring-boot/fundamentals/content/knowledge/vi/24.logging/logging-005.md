# logging.level theo package hoặc logger cụ thể

Khi phát triển ứng dụng Spring Boot, bạn thường muốn nhìn thấy nhiều thông tin hơn ở một khu vực cụ thể mà không làm toàn bộ console ngập trong log. Ví dụ, khi điều tra lỗi thanh toán, bạn cần các dòng `DEBUG` từ package `com.example.payment` nhưng vẫn muốn Spring Framework, Hibernate và các service còn lại giữ mức `INFO`. Hoặc bạn chỉ muốn bật `TRACE` cho đúng một logger khi truy tìm một nhánh xử lý khó tái hiện.

Spring Boot cho phép điều chỉnh điều này bằng nhóm cấu hình **`logging.level.*`**. Bạn có thể đặt mức log cho:

- **Root logger**: mặc định chung cho các logger không có cấu hình cụ thể hơn.
- **Một package hoặc namespace logger**: ví dụ `logging.level.com.example.payment=DEBUG`.
- **Một logger có tên đầy đủ**: ví dụ `logging.level.com.example.payment.PaymentService=TRACE`.
- **Một logging group**: tập nhiều logger hoặc package được điều khiển bằng một tên chung.

Điều quan trọng không chỉ là cú pháp YAML/properties mà còn là **logger được đặt tên như thế nào, mức hiệu lực được kế thừa theo hierarchy ra sao, và một cấu hình có tác động đến những logger nào**.

Bài học sử dụng Spring Boot 3.x, Java và SLF4J/Logback mặc định phổ biến; khi ứng dụng sử dụng Log4j2 hay backend khác, cách cấu hình riêng của backend có thể khác nhưng ý tưởng logger name và mức log vẫn hữu ích.

## 1. Vì sao cần điều chỉnh log theo phạm vi?

Xét một ứng dụng thương mại gồm các module:

~~~text
com.example.shop
├── order
│   ├── OrderService
│   └── OrderController
├── payment
│   ├── PaymentService
│   ├── PaymentGatewayClient
│   └── PaymentRetryScheduler
└── inventory
    ├── InventoryService
    └── StockRepository
~~~

Mọi service đều có thể ghi log, nhưng mỗi lúc bạn chỉ cần quan sát một vùng:

- Đang điều tra timeout từ cổng thanh toán: tăng log của `com.example.shop.payment`.
- Đang điều tra một vấn đề cụ thể trong `PaymentGatewayClient`: tăng mức cho logger tương ứng class đó.
- Muốn kiểm tra toàn hệ thống chỉ ghi cảnh báo/lỗi: đặt root `WARN`.
- Muốn thấy SQL do Hibernate phát sinh: điều chỉnh logger của Hibernate thay vì bật DEBUG cho cả ứng dụng.
- Muốn bật log chuyên sâu trong môi trường dev nhưng giữ production gọn: dùng cấu hình theo profile.

Nếu chỉ đặt:

~~~properties
logging.level.root=DEBUG
~~~

rất nhiều thư viện có thể bắt đầu ghi DEBUG, khiến dữ liệu cần tìm bị chìm trong hàng nghìn dòng log. Cấu hình theo package/logger cụ thể giúp **thu hẹp phạm vi**, giảm chi phí I/O và hạn chế log không cần thiết.

Tuy nhiên, một cấu hình chỉ tác động tới logger **mang đúng tên hoặc nằm dưới namespace đó**. Spring Boot không quét class rồi tự áp level theo thư mục source; nó sử dụng *logger name* mà code thực sự truyền cho logging API.

## 2. Đường đi của một thông điệp log

Ứng dụng thường ghi log qua SLF4J:

~~~java
package com.example.shop.payment;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

@Service
public class PaymentService {

    private static final Logger log =
            LoggerFactory.getLogger(PaymentService.class);

    public void pay(String orderId) {
        log.debug("Starting payment for orderId={}", orderId);
        log.info("Payment request accepted for orderId={}", orderId);
    }
}
~~~

`LoggerFactory.getLogger(PaymentService.class)` tạo hoặc lấy logger có tên tương ứng với class, thường là:

~~~text
com.example.shop.payment.PaymentService
~~~

Khi code gọi `log.debug(...)`, backend logging xác định message có được phép ghi dựa trên **effective log level** của logger rồi mới xử lý formatting và output.

~~~mermaid
flowchart TD
    A["PaymentService gọi log.debug(...)"] --> B["Logger name: com.example.shop.payment.PaymentService"]
    B --> C["Tìm configured/effective level"]
    C --> D{"DEBUG có được bật?"}
    D -->|Không| E["Bỏ qua log event"]
    D -->|Có| F["Tạo log event"]
    F --> G["Appender / encoder / output"]
    G --> H["Console, file hoặc log pipeline"]
~~~

`logging.level.*` chủ yếu điều khiển **ngưỡng phát log theo tên logger**. Nó không tự quyết định log ghi ra file nào, format ra sao, có JSON hay không, hoặc log retention bao lâu. Những việc đó thuộc appender, encoder, logging pattern và cấu hình của backend.

## 3. Các mức log và thứ tự ưu tiên

Các mức thông dụng theo độ chi tiết từ cao tới thấp:

| Level | Ý nghĩa | Tình huống |
| --- | --- | --- |
| `TRACE` | Rất chi tiết; bước xử lý nội bộ | Điều tra luồng xử lý khó |
| `DEBUG` | Thông tin chẩn đoán dành cho developer | Trạng thái, nhánh xử lý, tham số an toàn |
| `INFO` | Sự kiện vận hành bình thường | Khởi động, kết quả nghiệp vụ quan trọng |
| `WARN` | Điều bất thường nhưng hệ thống còn xử lý được | Retry, fallback, cấu hình đáng chú ý |
| `ERROR` | Thất bại cần chú ý | Không thể hoàn tất thao tác |
| `OFF` | Không phát log tại logger đó theo cấu hình mức | Chủ yếu dùng khi cần tắt có chủ đích |

Một logger có **effective level = INFO** thường chấp nhận các event ở `INFO`, `WARN` và `ERROR`, nhưng bỏ qua `DEBUG` và `TRACE`.

Một logger có **effective level = DEBUG** chấp nhận `DEBUG` và các level nghiêm trọng hơn nhưng không chấp nhận `TRACE`.

~~~text
Effective level = INFO
TRACE  -> bị lọc
DEBUG  -> bị lọc
INFO   -> ghi
WARN   -> ghi
ERROR  -> ghi

Effective level = DEBUG
TRACE  -> bị lọc
DEBUG  -> ghi
INFO   -> ghi
WARN   -> ghi
ERROR  -> ghi
~~~

**Mức log không phản ánh mức nghiêm trọng tự động của exception.** Code có thể gọi `log.debug("Cannot connect", exception)` và message đó vẫn bị lọc khi effective level là INFO. Độ nghiêm trọng là quyết định của người viết log, không phải đặc tính được Spring suy ra từ loại exception.

### 3.1. Level càng chi tiết không có nghĩa càng tốt

`TRACE` và `DEBUG` hữu ích lúc chẩn đoán, nhưng có thể tạo rất nhiều dòng, kích thước log lớn, lộ metadata nhạy cảm hoặc tăng chi phí vận hành.

Nên giữ level mặc định hợp lý, chỉ tăng log cho phạm vi cần điều tra và có kế hoạch đưa về level ban đầu sau khi xử lý xong.

## 4. Root logger: logging.level.root

Root logger là điểm gốc của logger hierarchy. Logger không có level cụ thể có thể kế thừa level hiệu lực từ parent và cuối cùng là root.

Ví dụ `application.properties`:

~~~properties
logging.level.root=INFO
~~~

Hoặc `application.yml`:

~~~yaml
logging:
  level:
    root: INFO
~~~

Đây là cách đặt ngưỡng log chung cho ứng dụng và các thư viện khi không có cấu hình cụ thể hơn.

Nếu đặt:

~~~properties
logging.level.root=WARN
~~~

những logger không được override riêng sẽ không phát `INFO` và `DEBUG`. Điều này có thể giúp giảm log, nhưng cũng làm mất các thông báo hoạt động bình thường từ nhiều framework.

### 4.1. Root INFO không xóa cấu hình riêng

Giả sử:

~~~properties
logging.level.root=INFO
logging.level.com.example.shop.payment=DEBUG
~~~

Logger `com.example.shop.payment.PaymentService` có thể phát DEBUG vì nhận level cụ thể từ namespace `com.example.shop.payment`. Root INFO vẫn áp cho các logger không có cấu hình gần hơn.

Không nên hiểu `logging.level.root=INFO` là “mọi logger bắt buộc phải INFO”. Đó là **mức kế thừa ở gốc**, không phải một giới hạn cứng chặn mọi override.

### 4.2. Root DEBUG trong production cần thận trọng

Đặt root DEBUG cho phép rất nhiều thư viện ghi log chi tiết. Điều này có thể tăng lượng log và vô tình tiết lộ dữ liệu không nên ghi nhận.

Với production, thường nên tăng level ở một package hoặc logger cụ thể, hoặc sử dụng Actuator để đổi tạm thời trong phạm vi được kiểm soát, thay vì bật DEBUG toàn bộ.

## 5. logging.level theo package

Bạn có thể đặt mức log cho một namespace giống tên package:

~~~properties
logging.level.com.example.shop.payment=DEBUG
~~~

Hoặc YAML:

~~~yaml
logging:
  level:
    "com.example.shop.payment": DEBUG
~~~

Khi dùng `LoggerFactory.getLogger(SomeClass.class)`, logger name thường là tên class có đầy đủ package. Vì vậy các logger:

~~~text
com.example.shop.payment.PaymentService
com.example.shop.payment.PaymentGatewayClient
com.example.shop.payment.PaymentRetryScheduler
~~~

đều kế thừa level DEBUG từ namespace `com.example.shop.payment`, trừ khi chính logger hoặc parent gần hơn có level riêng.

Một logger trong `com.example.shop.order` không bị ảnh hưởng bởi cấu hình này.

### 5.1. Package ở đây là logger namespace

Backend logging không cần kiểm tra class thực sự nằm trong package Java nào. Nó xử lý **tên logger dạng phân cấp bằng dấu chấm**.

Ví dụ:

~~~java
private static final Logger AUDIT =
        LoggerFactory.getLogger("com.example.shop.payment.audit");
~~~

Logger tùy đặt tên này cũng nằm dưới namespace `com.example.shop.payment`, dù nó không tương ứng với một class Java cụ thể.

Ngược lại:

~~~java
private static final Logger AUDIT =
        LoggerFactory.getLogger("audit.payment");
~~~

không tự kế thừa `logging.level.com.example.shop.payment` chỉ vì được tạo bên trong `PaymentService`. Nó có logger name là `audit.payment`.

**Level bám theo tên logger, không bám theo vị trí dòng code gọi log.**

### 5.2. Hierarchy theo dấu chấm, không phải bắt đầu bằng chuỗi bất kỳ

Một logger tên `com.example.payment.Client` nằm dưới `com.example.payment`. Nhưng logger `com.example.payments.Client` **không** nằm dưới `com.example.payment`, vì segment `payments` khác `payment`.

~~~text
com.example
├── payment
│   ├── Client
│   └── RetryWorker
└── payments
    └── Client
~~~

Điều này tránh hiểu nhầm việc cấu hình prefix theo chuỗi ký tự tùy ý. Backend xử lý quan hệ phân cấp theo các segment tên logger.

## 6. logging.level cho logger hoặc class cụ thể

Nếu chỉ cần xem log từ một service:

~~~properties
logging.level.com.example.shop.payment.PaymentService=TRACE
~~~

Hoặc YAML:

~~~yaml
logging:
  level:
    "com.example.shop.payment.PaymentService": TRACE
~~~

Khi `PaymentService` dùng:

~~~java
private static final Logger log =
        LoggerFactory.getLogger(PaymentService.class);
~~~

logger name khớp với cấu hình. Method gọi `log.trace(...)` có thể ghi ra output nếu backend/appender không áp thêm filter khác.

### 6.1. Một cấu hình cho class là cấu hình theo tên logger

Spring Boot không bắt buộc class `PaymentService` phải tồn tại để bạn khai báo:

~~~properties
logging.level.com.example.shop.payment.PaymentService=TRACE
~~~

Cấu hình đặt level cho **logger category có tên đó**. Nếu code thực tế không dùng tên logger này, thay đổi có thể không tạo ra dòng log nào.

Ví dụ nếu service dùng:

~~~java
private static final Logger log =
        LoggerFactory.getLogger("payments");
~~~

thì logger name là `payments`, không phải `com.example.shop.payment.PaymentService`. Cần cấu hình:

~~~properties
logging.level.payments=TRACE
~~~

Đây là một trong những nguyên nhân phổ biến khi cấu hình tưởng đúng nhưng log không đổi.

### 6.2. Static logger và instance logger

Hai cách đều có thể dùng cùng logger name:

~~~java
private static final Logger log =
        LoggerFactory.getLogger(PaymentService.class);
~~~

~~~java
private final Logger log =
        LoggerFactory.getLogger(getClass());
~~~

Cách thứ hai có thể cho logger name khác khi class được subclass hoặc proxy, nên cần cân nhắc nếu code dựa vào tên logger cố định. Với service thông thường, logger `private static final` gắn với class khai báo là lựa chọn dễ dự đoán.

### 6.3. Logger từ Lombok @Slf4j

Nếu dự án sử dụng Lombok:

~~~java
@Slf4j
@Service
public class PaymentService {
    public void pay(String orderId) {
        log.debug("Paying orderId={}", orderId);
    }
}
~~~

Lombok tạo field logger cho class. Trong thiết lập mặc định, tên logger gắn với class khai báo, nên `logging.level.com.example.shop.payment.PaymentService` là một cấu hình phù hợp.

Annotation `@Slf4j` yêu cầu Lombok được cấu hình trong build. Nó không phải annotation của Spring Boot, và không tự thay đổi logging backend hay mức log.

## 7. Kế thừa và override level: cấu hình nào thắng?

Hãy dùng một ví dụ có nhiều lớp:

~~~properties
logging.level.root=INFO
logging.level.com.example=DEBUG
logging.level.com.example.shop.payment=TRACE
logging.level.com.example.shop.payment.PaymentService=INFO
~~~

Các logger có thể có effective level:

| Logger name | Effective level | Vì sao? |
| --- | --- | --- |
| `org.springframework.web.DispatcherServlet` | INFO | Kế thừa từ root nếu không có override khác |
| `com.example.shop.order.OrderService` | DEBUG | Kế thừa `com.example` |
| `com.example.shop.payment.PaymentGatewayClient` | TRACE | Kế thừa `com.example.shop.payment` |
| `com.example.shop.payment.PaymentService` | INFO | Có level riêng trên logger |
| `com.example.shop.payment.internal.RetryPolicy` | TRACE | Nằm dưới namespace payment |
| `audit.payment` | INFO | Không cùng namespace với com.example |

Backend sẽ tìm **level được cấu hình gần nhất trong logger hierarchy**, sau đó kế thừa đến root nếu không có level gần hơn.

~~~mermaid
flowchart TD
    A["root = INFO"] --> B["com.example = DEBUG"]
    B --> C["com.example.shop.order"]
    B --> D["com.example.shop.payment = TRACE"]
    D --> E["PaymentGatewayClient = TRACE kế thừa"]
    D --> F["PaymentService = INFO override"]
    D --> G["internal.RetryPolicy = TRACE kế thừa"]
~~~

### 7.1. Level cụ thể hơn có thể ít chi tiết hơn

Nhiều người nghĩ chỉ có thể bật thêm log cho một class trong package. Thực ra có thể giảm log của một class ồn ào:

~~~properties
logging.level.com.example.shop.payment=DEBUG
logging.level.com.example.shop.payment.NoisyPollingClient=WARN
~~~

Các class khác dưới payment tiếp tục DEBUG. Riêng `NoisyPollingClient` chỉ phát WARN/ERROR.

Đây là công cụ hữu ích để tránh một logger có tần suất cao làm nghẽn console trong khi vẫn giữ log cần thiết cho phần còn lại của package.

### 7.2. Override không thay đổi cấu hình parent

Đặt logger con `PaymentService=TRACE` không biến level của `com.example.shop.payment` thành TRACE; các logger “anh em” vẫn kế thừa level ở parent.

### 7.3. Tên class lồng nhau

Java có thể tạo nested class với tên nhị phân chứa `$`, chẳng hạn `OrderService$Worker`. Nếu logger được tạo từ nested class, tên thực tế có thể chứa ký tự đó.

Trước khi viết property cho một logger đặc biệt, hãy xác định **tên logger thực**, thay vì đoán từ cách viết nested class trong source. Dùng tên logger in trong pattern hoặc kiểm tra `logger.getName()`.

## 8. Phân biệt logger hierarchy với property-source precedence

Có hai cơ chế dễ bị nhầm với nhau:

1. **Property-source precedence** quyết định giá trị hiệu lực nếu **cùng một property key** xuất hiện ở nhiều nguồn, chẳng hạn `application.yml` và command line.
2. **Logger hierarchy** quyết định logger sẽ kế thừa level nào giữa root, package và logger cụ thể.

Ví dụ file gốc:

~~~yaml
logging:
  level:
    root: INFO
    "com.example.shop.payment.PaymentService": TRACE
~~~

Profile production ghi:

~~~yaml
logging:
  level:
    "com.example.shop.payment": WARN
~~~

Đây là **hai key khác nhau**. Việc profile production có độ ưu tiên cao hơn không tự xóa cấu hình cụ thể của `PaymentService` trong nguồn gốc. Logger cụ thể vẫn có thể nhận TRACE, trong khi các logger khác dưới package payment nhận WARN.

Nếu bạn muốn production thực sự tắt TRACE của class đó, hãy override **chính key cụ thể**:

~~~yaml
logging:
  level:
    "com.example.shop.payment.PaymentService": INFO
~~~

Không thể chỉ nghĩ “file production nằm sau nên package WARN sẽ thắng mọi class-level DEBUG/TRACE”. Phân cấp tên logger và độ ưu tiên nguồn cấu hình là hai trục riêng.

### 8.1. Không nhầm level kế thừa với log additivity

Trong các backend như Logback, **additivity** quyết định một log event có được gửi tiếp tới appender của logger tổ tiên hay không. Nó khác với **effective level**.

- Logger level quyết định event nào được chấp nhận.
- Appender và additivity quyết định event được ghi ra đâu và có thể ghi lặp hay không.

Nếu một dòng log xuất hiện hai lần, nguyên nhân có thể là appender/additivity bị cấu hình trùng, không phải do bạn đặt level ở cả root và package.

## 9. Cấu hình trong application.properties

`application.properties` rất thuận tiện khi muốn thêm từng dòng:

~~~properties
# Mức chung
logging.level.root=INFO

# Tập trung log ứng dụng
logging.level.com.example.shop=DEBUG

# Tăng log package payment
logging.level.com.example.shop.payment=TRACE

# Giảm log từ một logger ồn ào
logging.level.com.example.shop.payment.PaymentRetryScheduler=WARN

# Theo dõi request mapping của Spring
logging.level.org.springframework.web=DEBUG
~~~

Cần viết tên logger/class đúng chính tả, kể cả chữ hoa/chữ thường khi định danh logger có sự khác biệt. Không nên gõ tên class theo cách rút gọn như `PaymentService` nếu logger thực có tên đầy đủ.

### 9.1. Mức level không phân biệt hoa/thường trong cú pháp thường dùng

Trong cấu hình Spring Boot thông thường, các giá trị level như `debug`, `DEBUG`, `Info` được bind/diễn giải về level phù hợp. Tuy nhiên, hãy dùng chữ hoa nhất quán để dễ đọc và phù hợp các ví dụ tài liệu:

~~~properties
logging.level.com.example.shop.payment=DEBUG
~~~

Tên logger không phải tên level; đừng tự ý lowercase tên class khi chuyển cấu hình giữa các nguồn.

### 9.2. Không dùng wildcard như glob tùy ý

Đừng giả định property:

~~~properties
logging.level.com.example.shop.*=DEBUG
~~~

là cú pháp wildcard được Spring Boot áp dụng cho mọi package con. `logging.level` được cấu hình bằng **tên logger hoặc namespace**. Để ảnh hưởng đến các logger con, đặt trực tiếp:

~~~properties
logging.level.com.example.shop=DEBUG
~~~

Bạn không cần `*` vì quan hệ phân cấp logger đã xử lý việc kế thừa.

## 10. Cấu hình trong application.yml

Cùng cấu hình có thể viết dạng YAML:

~~~yaml
logging:
  level:
    root: INFO
    "com.example.shop": DEBUG
    "com.example.shop.payment": TRACE
    "com.example.shop.payment.PaymentRetryScheduler": WARN
    "org.springframework.web": DEBUG
~~~

Có thể viết thành các nhánh lồng nhau nhưng dễ rối khi có logger name chứa chữ hoa hoặc các segment đặc biệt. Để quản lý nhiều tên class/logger chính xác, dùng **dotted key nằm trong dấu nháy** dưới `logging.level` thường rất dễ đọc.

Ví dụ:

~~~yaml
logging:
  level:
    "com.example.shop.payment.PaymentService": DEBUG
    "org.hibernate.SQL": DEBUG
~~~

Dấu nháy ở đây là YAML syntax để bao một key có dấu chấm. Nó không làm thay đổi logger name trong giá trị cấu hình.

### 10.1. Những lỗi YAML hay gặp

Sai indentation:

~~~yaml
logging:
level:
  root: INFO
~~~

YAML này không tạo cấu trúc `logging.level.root` như mong đợi.

Đúng:

~~~yaml
logging:
  level:
    root: INFO
~~~

Sai do lẫn dấu `=` của properties:

~~~yaml
logging:
  level:
    root=INFO
~~~

Trong YAML, key/value phải dùng dấu hai chấm.

### 10.2. Một nguồn cấu hình không phải nơi duy nhất

Spring Boot có thể nhận `logging.level.*` từ nhiều property sources như profile files, environment variables, system properties, command-line arguments và các nguồn cấu hình khác được hỗ trợ.

Khi tìm lý do level không như mong đợi, hãy kiểm tra **giá trị hiệu lực**, không chỉ nhìn vào một file `application.yml`.

## 11. Cấu hình theo profile: dev, test, production

Một nhu cầu phổ biến là giữ log chẩn đoán trong môi trường phát triển nhưng giảm chi tiết trong production.

`application.yml`:

~~~yaml
logging:
  level:
    root: INFO
    "com.example.shop": INFO
~~~

`application-dev.yml`:

~~~yaml
logging:
  level:
    "com.example.shop.payment": DEBUG
~~~

`application-prod.yml`:

~~~yaml
logging:
  level:
    "com.example.shop.payment": WARN
~~~

Khi profile `dev` active, nhóm payment có thể phát DEBUG. Khi profile `prod` active, nhóm này nhận WARN, trừ khi có cấu hình chi tiết hơn hoặc nguồn ưu tiên cao hơn.

### 11.1. Kiểm tra active profiles

Có thể kích hoạt profile bằng property:

~~~properties
spring.profiles.active=dev
~~~

hoặc command-line:

~~~bash
java -jar app.jar --spring.profiles.active=dev
~~~

Khi ứng dụng đọc cấu hình từ file profile, hãy chú ý file có được đóng gói vào artifact, có được nạp từ đúng vị trí và có bị nguồn khác override hay không.

### 11.2. Không lưu cấu hình DEBUG vĩnh viễn trong production

Ngay cả khi logger chỉ nằm ở một package, TRACE/DEBUG vẫn có thể ghi:

- Định danh request hoặc token được truyền nhầm vào tham số log.
- Payload của API hoặc thông tin người dùng.
- Chi tiết truy vấn và tham số database.
- Trạng thái xử lý nội bộ có giá trị nhạy cảm.

Chỉ bật có chủ đích, giới hạn thời gian, bảo vệ đầu ra log và hạ level sau khi điều tra. Cấu hình logging không thay thế chính sách bảo mật dữ liệu.

## 12. Cấu hình bằng command-line và JVM system properties

Bạn không cần sửa file cấu hình để tăng level tạm thời khi chạy một phiên bản ứng dụng.

Với command-line argument của Spring Boot:

~~~bash
java -jar app.jar --logging.level.com.example.shop.payment=DEBUG
~~~

Với logger cụ thể:

~~~bash
java -jar app.jar --logging.level.com.example.shop.payment.PaymentService=TRACE
~~~

JVM system property cũng có thể cung cấp cùng property key:

~~~bash
java -Dlogging.level.com.example.shop.payment.PaymentService=TRACE -jar app.jar
~~~

`-D...` thuộc cú pháp JVM, phải đặt trước `-jar` trong ví dụ này. Còn `--logging.level...` là application argument có thể truyền sau tên JAR.

### 12.1. Ưu điểm của cấu hình khi chạy

- Không cần thay đổi source code.
- Không cần tạo một bản build mới chỉ để tăng một logger.
- Dễ dùng trong môi trường kiểm thử hoặc một instance riêng.
- Có thể kết hợp cùng các công cụ deploy để điều chỉnh cấp độ log.

Nếu bạn sửa start command của production, thay đổi thường yêu cầu restart process để áp dụng lại các tham số khởi động. Trong khi đó, Actuator loggers endpoint cho phép thay đổi level runtime khi được bật và có quyền phù hợp.

### 12.2. Command-line có thể ghi đè file

Nếu cùng key được đặt trong file:

~~~properties
logging.level.com.example.shop.payment=INFO
~~~

và command line truyền:

~~~bash
java -jar app.jar --logging.level.com.example.shop.payment=DEBUG
~~~

trong cấu hình Spring Boot thông thường, command-line property có độ ưu tiên cao nên giá trị hiệu lực của **chính key đó** là DEBUG.

Nhưng như đã phân biệt ở mục hierarchy, override theo source không tự xóa các key logger con khác.

## 13. Environment variables và vấn đề tên class có chữ hoa

Đây là chi tiết quan trọng khi deploy bằng Docker, Kubernetes hoặc hệ thống CI/CD.

Spring Boot hỗ trợ cấu hình logging qua environment variables. Với package logger:

~~~text
LOGGING_LEVEL_COM_EXAMPLE_SHOP_PAYMENT=DEBUG
~~~

có thể tương ứng với:

~~~properties
logging.level.com.example.shop.payment=DEBUG
~~~

Nhưng **cấu hình logger theo tên class đầy đủ qua environment variable thông thường có giới hạn**: relaxed binding từ biến môi trường thường chuyển tên thành chữ thường. Tên logger của một Java class có thể chứa chữ hoa, như `PaymentService`, nên giá trị có thể không tác động lên đúng logger mong đợi.

Ví dụ:

~~~text
LOGGING_LEVEL_COM_EXAMPLE_SHOP_PAYMENT_PAYMENTSERVICE=TRACE
~~~

không phải cách đáng tin cậy để thiết lập level cho đúng tên logger `com.example.shop.payment.PaymentService`. Tên logger có phân biệt các ký tự trong tên; phần class có chữ hoa có thể bị lowercase trong quá trình chuyển đổi tên property.

### 13.1. Dùng environment variable cho package

Nếu muốn cấp log cho cả package, biến môi trường rất phù hợp:

~~~text
LOGGING_LEVEL_ORG_SPRINGFRAMEWORK_WEB=DEBUG
LOGGING_LEVEL_COM_EXAMPLE_SHOP_PAYMENT=TRACE
~~~

Tên package thường viết lowercase, nên tránh được giới hạn liên quan chữ hoa của class name.

### 13.2. Dùng SPRING_APPLICATION_JSON cho tên class chính xác

Nếu cần class-level logger qua environment mà không sửa file, dùng `SPRING_APPLICATION_JSON`:

~~~json
{
  "logging": {
    "level": {
      "com.example.shop.payment.PaymentService": "TRACE"
    }
  }
}
~~~

Trên shell hỗ trợ truyền JSON trong environment variable, đặt nội dung này vào `SPRING_APPLICATION_JSON` trước khi chạy ứng dụng. Ví dụ trên minh họa **giá trị JSON**, không phải tên biến được tạo cho từng key.

Cơ chế JSON cho phép giữ key tên logger với chữ hoa theo đúng ý định. Một lựa chọn khác là truyền command-line argument có tên chính xác.

### 13.3. System properties là lựa chọn khác

JVM system property được đặt với key đầy đủ:

~~~bash
java -Dlogging.level.com.example.shop.payment.PaymentService=DEBUG -jar app.jar
~~~

Khác với environment variable dạng uppercase/underscore, bạn có thể biểu diễn đúng logger name có chữ hoa ngay trong key JVM property.

### 13.4. Không sửa class name để chiều theo biến môi trường

Đừng thay `PaymentService` thành `paymentservice` hoặc ép logger name lowercase trong Java chỉ vì tiện deploy. Hãy chọn một cách cấu hình giữ nguyên tên logger hoặc cấu hình theo package. Class name và logger category nên phản ánh ý định thiết kế, không bị phụ thuộc ngẫu nhiên vào giới hạn biến môi trường.

## 14. logging.group: gom nhiều package/logger

Đôi khi một tính năng trải dài nhiều package khác nhau:

~~~text
com.example.shop.order
com.example.shop.payment
com.example.shop.inventory
~~~

Bạn muốn bật DEBUG cho cả ba chỉ bằng một key. Spring Boot có khái niệm **logging group**.

`application.properties`:

~~~properties
logging.group.shop-flow=com.example.shop.order,com.example.shop.payment,com.example.shop.inventory
logging.level.shop-flow=DEBUG
~~~

YAML tương ứng:

~~~yaml
logging:
  group:
    shop-flow:
      - com.example.shop.order
      - com.example.shop.payment
      - com.example.shop.inventory
  level:
    shop-flow: DEBUG
~~~

Khi Spring Boot xử lý logging group, level gán cho `shop-flow` được áp lên các logger names thuộc group. Điều này cho phép điều chỉnh nhiều namespace không chung một ancestor có phạm vi đủ hẹp.

### 14.1. Group khác logger namespace

Tên `shop-flow` là **tên group do bạn định nghĩa**, không nhất thiết là một logger name thực có hierarchy con. Nó đóng vai trò khóa điều khiển tập logger:

~~~text
logging.level.shop-flow=DEBUG
           |
           v
  +-----------------------+
  | com.example.shop.order|
  | com.example.shop.payment
  | com.example.shop.inventory
  +-----------------------+
~~~

Nếu chỉ muốn áp cho toàn bộ `com.example.shop`, cấu hình một package ancestor có thể đơn giản hơn:

~~~properties
logging.level.com.example.shop=DEBUG
~~~

Group hữu ích hơn khi danh sách namespace không thuộc cùng một parent hoặc muốn đặt tên theo một chức năng vận hành.

### 14.2. Group được định nghĩa nhưng chưa có level

~~~properties
logging.group.shop-flow=com.example.shop.order,com.example.shop.payment
~~~

Chỉ định nghĩa group chưa tự bật DEBUG. Bạn cần cấu hình level cho group khi muốn điều khiển:

~~~properties
logging.level.shop-flow=DEBUG
~~~

### 14.3. Các group tích hợp

Spring Boot cung cấp một số group tiện dụng tùy phiên bản, ví dụ `web` và `sql`, để điều chỉnh tập logger liên quan:

~~~properties
logging.level.web=DEBUG
logging.level.sql=DEBUG
~~~

Các group này không có nghĩa tất cả công cụ web hoặc mọi database đều ghi đầy đủ nội dung request/SQL. Thành phần logger cụ thể mà group chứa phụ thuộc Spring Boot version, backend và dependency có mặt.

Nếu muốn kiểm soát chính xác, hãy xem group definitions của phiên bản đang dùng hoặc cấu hình logger cụ thể theo nhu cầu.

### 14.4. Tránh overlap không chủ đích

Nếu một logger vừa thuộc group vừa được cấu hình level riêng, cần hiểu quá trình Spring Boot áp dụng logging levels cho cấu hình cuối cùng. Với yêu cầu cần bảo đảm level chính xác cho một logger, nên tránh nhiều group và override có thể ghi đè nhau theo thứ tự khó quan sát; hãy giữ một source điều khiển rõ ràng và kiểm tra effective level khi ứng dụng chạy.

## 15. Theo dõi logger của Spring Framework

Nhiều khi bug nằm trong framework chứ không ở code ứng dụng. Bạn có thể tăng log cho một namespace hẹp.

Ví dụ quan sát Spring Web:

~~~properties
logging.level.org.springframework.web=DEBUG
~~~

Quan sát Spring Security:

~~~properties
logging.level.org.springframework.security=DEBUG
~~~

Quan sát transaction infrastructure:

~~~properties
logging.level.org.springframework.transaction=DEBUG
~~~

Quan sát cấu hình bean factory:

~~~properties
logging.level.org.springframework.beans.factory=DEBUG
~~~

Đây là các ví dụ tên logger phổ biến; bạn nên bật theo đúng câu hỏi đang điều tra, thay vì bật tất cả.

### 15.1. Spring Security log có thể rất nhạy cảm

Log liên quan bảo mật có thể phản ánh filter chain, authentication state, request metadata hoặc thông tin sử dụng trong quá trình xác thực. Đừng để DEBUG/TRACE của security package mở rộng trong production mà không kiểm tra đầu ra có dữ liệu nhạy cảm hay không.

### 15.2. Root DEBUG không đồng nghĩa mọi thứ sẽ có log DEBUG

Một framework chỉ phát log khi code của nó có lời gọi log ở level đó. Nếu một method không ghi `DEBUG`, tăng logger level không tạo ra một thông báo mới.

Một số log còn có điều kiện riêng, sampling, filter/appender, hoặc được gửi tới tên logger khác với điều bạn đoán. Vì vậy hãy xác định logger category thực sự khi debug.

## 16. Hibernate và JDBC: tìm đúng logger category

Một tình huống thường gặp là muốn xem câu SQL và các giá trị bind parameter.

Với Hibernate 6 (thường đi cùng Spring Boot 3.x), các logger phổ biến:

~~~properties
# Câu SQL do Hibernate ghi qua logging backend
logging.level.org.hibernate.SQL=DEBUG

# Giá trị bind parameter (cần thận trọng với dữ liệu nhạy cảm)
logging.level.org.hibernate.orm.jdbc.bind=TRACE
~~~

Có thể bổ sung logger liên quan result extraction trong những trường hợp cần chẩn đoán sâu, nhưng không nên bật hàng loạt level TRACE theo thói quen.

### 16.1. logger SQL có chữ hoa

`org.hibernate.SQL` là ví dụ quan trọng của một logger **không có tên class Java thông thường** nhưng chứa chữ hoa. Khi cấu hình bằng environment variable thông thường, giới hạn lowercase vẫn có thể gây sai lệch tên logger.

Dùng properties/YAML, JVM system property hoặc `SPRING_APPLICATION_JSON` khi cần giữ tên chính xác `org.hibernate.SQL`.

### 16.2. Không nhầm logger level với show-sql

Hibernate có tùy chọn `spring.jpa.show-sql` trong Spring Boot. Tùy chọn đó khác với logging qua `org.hibernate.SQL`. In SQL trực tiếp ra console không có đầy đủ các lợi ích của logging backend về level, formatting và routing.

Trong môi trường vận hành, thường nên ưu tiên logger có level rõ ràng, gắn với chính sách log và masking phù hợp.

### 16.3. Spring JDBC có tên logger khác Hibernate

Nếu ứng dụng dùng `JdbcTemplate` thay vì JPA/Hibernate, bật `org.hibernate.SQL` không có tác dụng tới log của Spring JDBC.

Có thể điều tra các namespace như:

~~~properties
logging.level.org.springframework.jdbc.core=DEBUG
~~~

Với log JDBC chi tiết hơn, cần biết lớp và logger name thực tế của phiên bản Spring đang dùng. Hãy chọn một logger cụ thể dựa trên dữ liệu quan sát, không mặc định mọi SQL access đều đi qua Hibernate.

## 17. Debug flag của Spring Boot không tương đương root DEBUG

Spring Boot hỗ trợ:

~~~bash
java -jar app.jar --debug
~~~

hoặc:

~~~properties
debug=true
~~~

Và ở mức chi tiết hơn:

~~~properties
trace=true
~~~

Các flag này bật những nhóm log chẩn đoán do Spring Boot lựa chọn và có thể làm xuất hiện thêm thông tin khởi động/condition evaluation. Chúng **không tương đương** với:

~~~properties
logging.level.root=DEBUG
~~~

hoặc:

~~~properties
logging.level.root=TRACE
~~~

Nếu muốn xem log DEBUG của ứng dụng:

~~~properties
logging.level.com.example.shop=DEBUG
~~~

là cách trực tiếp hơn. Nếu muốn xem condition evaluation report khi auto-configuration hoạt động bất ngờ, `--debug` có thể đặc biệt hữu ích.

### 17.1. Tránh dùng --trace như giải pháp cho mọi lỗi

`--trace` có thể làm nhiều nhóm logger trở nên rất chi tiết. Hãy ưu tiên tăng level cho logger/package cần điều tra để giữ log có thể đọc và tránh dữ liệu nhạy cảm.

## 18. Thay đổi log level khi ứng dụng đang chạy bằng Actuator

Spring Boot Actuator cung cấp **loggers endpoint** để xem và, nếu được phép, thay đổi mức log runtime mà không cần restart ứng dụng.

Thêm Actuator:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
~~~

Expose endpoint qua HTTP nếu môi trường thực sự cần:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,loggers
~~~

Việc expose endpoint chỉ làm nó có khả năng được truy cập qua transport tương ứng; **authentication/authorization vẫn cần được cấu hình phù hợp**. Đừng mở endpoint điều chỉnh log ra mạng công khai mà không bảo vệ.

### 18.1. Xem loggers

Endpoint cơ bản thường là:

~~~http
GET /actuator/loggers
~~~

Để xem một logger cụ thể:

~~~http
GET /actuator/loggers/com.example.shop.payment.PaymentService
~~~

Kết quả điển hình có những trường như:

~~~json
{
  "configuredLevel": "DEBUG",
  "effectiveLevel": "DEBUG"
}
~~~

Nếu logger không có level riêng:

~~~json
{
  "configuredLevel": null,
  "effectiveLevel": "INFO"
}
~~~

`configuredLevel` cho biết level được đặt trực tiếp tại logger; `effectiveLevel` phản ánh level đang có hiệu lực sau khi xét kế thừa.

Các response trên chỉ là ví dụ về cấu trúc dữ liệu; giá trị thực tế phụ thuộc cấu hình và logging backend.

### 18.2. Thay đổi level runtime

Gửi request:

~~~http
POST /actuator/loggers/com.example.shop.payment.PaymentService
Content-Type: application/json

{"configuredLevel":"TRACE"}
~~~

Ví dụ với curl:

~~~bash
curl -X POST \
  -H "Content-Type: application/json" \
  -d '{"configuredLevel":"TRACE"}' \
  http://localhost:8080/actuator/loggers/com.example.shop.payment.PaymentService
~~~

Khi endpoint cho phép thao tác và backend hỗ trợ thay đổi level, logger đó nhận cấu hình TRACE ở runtime.

Một số lưu ý:

- Đây là thay đổi **trong tiến trình đang chạy**, không tự ghi lại `application.yml`.
- Khi ứng dụng restart, cấu hình startup lại quyết định level mặc định.
- Trong hệ thống nhiều replica, thay đổi một instance không tự áp cho mọi instance khác.
- Endpoint cần được bảo vệ; không cung cấp quyền đổi level cho người dùng không được ủy quyền.

### 18.3. Trả về mức kế thừa

Có thể bỏ level cấu hình trực tiếp bằng:

~~~http
POST /actuator/loggers/com.example.shop.payment.PaymentService
Content-Type: application/json

{"configuredLevel":null}
~~~

Sau thao tác này, logger sẽ kế thừa từ namespace parent hoặc root theo cấu hình backend hiện tại. Điều đó **khác** việc gửi `"INFO"`: đặt INFO là một level cụ thể, còn `null` xóa override trực tiếp để nhận level được kế thừa.

### 18.4. Runtime changes có phải cấu hình bền vững?

Không. Nếu cần level được giữ sau restart, cập nhật nguồn cấu hình được deploy như properties/YAML, command-line, config management hoặc logging backend configuration phù hợp.

Actuator phù hợp cho chẩn đoán tạm thời khi ứng dụng đang chạy, có quyền truy cập và cơ chế audit/kiểm soát thời gian thay đổi.

## 19. configuredLevel và effectiveLevel: khác biệt phải hiểu

Giả sử:

~~~properties
logging.level.root=INFO
logging.level.com.example.shop.payment=DEBUG
~~~

Logger `com.example.shop.payment.PaymentService` chưa được cấu hình trực tiếp.

Khi hỏi Actuator (hoặc logging system API), bạn có thể thấy:

~~~json
{
  "configuredLevel": null,
  "effectiveLevel": "DEBUG"
}
~~~

Dù `configuredLevel` là null, DEBUG vẫn hoạt động vì logger **kế thừa** từ package parent.

Nếu bạn đặt:

~~~properties
logging.level.com.example.shop.payment.PaymentService=WARN
~~~

thì:

~~~json
{
  "configuredLevel": "WARN",
  "effectiveLevel": "WARN"
}
~~~

### 19.1. configuredLevel null không có nghĩa logging bị tắt

Nó chỉ nghĩa là **không có level cài trực tiếp ở logger được hỏi**. Backend tiếp tục tính effective level từ hierarchy.

### 19.2. Effective level không nói event sẽ luôn được ghi ra console

Ngoài level, logging backend còn có appender filters, markers, logging configuration và output routing.

Một logger có effective DEBUG có thể tạo DEBUG event, nhưng appender hoặc filter ở nơi khác vẫn có thể quyết định không ghi nó vào console. Khi thấy “effective DEBUG mà không thấy dòng log”, hãy kiểm tra cả việc code có thực sự gọi logger, point runtime, filter và appender.

## 20. Kiểm tra log bằng code

Trong một method có thể hỏi logger hiện tại:

~~~java
private static final Logger log =
        LoggerFactory.getLogger(PaymentService.class);

public void execute(String orderId) {
    if (log.isDebugEnabled()) {
        log.debug("Detailed processing for orderId={}", orderId);
    }
}
~~~

`isDebugEnabled()` giúp kiểm tra level đang được cho phép ở API logger.

Nhưng với placeholder logging thông thường:

~~~java
log.debug("Payment id={}, status={}", paymentId, status);
~~~

SLF4J/backend đã có cơ chế trì hoãn phần lớn formatting đến khi level cho phép; bạn **không cần** bao mọi lời gọi bằng `if (log.isDebugEnabled())`.

### 20.1. Khi nào guard thật sự hữu ích?

Khi tham số log cần tính toán tốn kém:

~~~java
if (log.isDebugEnabled()) {
    String snapshot = buildExpensiveDebugSnapshot();
    log.debug("Payment snapshot={}", snapshot);
}
~~~

Nếu viết:

~~~java
log.debug("Payment snapshot={}", buildExpensiveDebugSnapshot());
~~~

Java sẽ gọi `buildExpensiveDebugSnapshot()` để tạo argument **trước** khi gọi method logger, dù DEBUG đang bị tắt. Guard giúp tránh phần tính toán đó.

Nếu `snapshot` chứa dữ liệu nhạy cảm, việc log có được bật cũng không phải giấy phép ghi toàn bộ snapshot. Hãy lọc thông tin được phép trước khi đưa vào log.

### 20.2. Placeholder logging tốt hơn nối chuỗi

Ưu tiên:

~~~java
log.info("Order {} transitioned to {}", orderId, state);
~~~

Hạn chế:

~~~java
log.info("Order " + orderId + " transitioned to " + state);
~~~

Cách nối chuỗi tạo string trước khi logger quyết định level. Placeholder giúp logging framework xử lý argument theo cách phù hợp và giữ format nhất quán.

### 20.3. Log exception đúng cách

~~~java
try {
    paymentGateway.call();
} catch (GatewayException exception) {
    log.error(
            "Payment gateway failed for orderId={}",
            orderId,
            exception
    );
    throw exception;
}
~~~

Truyền exception làm argument cuối theo convention của SLF4J giúp backend có thể ghi stack trace. Tránh chỉ ghi `exception.getMessage()` nếu cần stack trace để chẩn đoán.

Nhưng cũng đừng log cùng một exception thành ERROR ở mọi tầng rồi ném tiếp nếu tầng phía trên cũng log lại; điều đó dễ tạo nhiều dòng trùng lặp cho cùng một lỗi.

## 21. Level của logger không thay đổi log statement

Giả sử source chỉ có:

~~~java
log.info("Payment accepted");
~~~

Đặt:

~~~properties
logging.level.com.example.shop.payment.PaymentService=TRACE
~~~

không làm Spring tự tạo ra các dòng TRACE/DEBUG. Cấu hình chỉ quyết định **những log statements đã có trong code** được phép phát.

Muốn quan sát thêm trạng thái, cần thêm lời gọi log phù hợp hoặc bật logger của framework có sẵn event chi tiết cần xem.

Điều này cũng giúp định hướng troubleshooting: nếu đã bật DEBUG đúng logger nhưng không có log, hãy xác minh code path có chạy tới lời gọi `log.debug(...)` hay không.

## 22. Logging backend và cấu hình nâng cao

Spring Boot dùng một logging abstraction để tích hợp các backend phổ biến. Trong một project starter tiêu chuẩn, **Logback** thường được cung cấp bởi `spring-boot-starter-logging` qua dependency.

Trong trường hợp ứng dụng dùng Log4j2, hệ thống vẫn có thể nhận `logging.level.*` từ Spring Boot, nhưng file cấu hình backend và quy tắc appender/layout riêng sẽ khác.

### 22.1. Khi nào logging.level là đủ?

Dùng `logging.level.*` cho:

- Đặt ngưỡng root logger.
- Tăng/giảm log của package.
- Tăng/giảm log của logger cụ thể.
- Quản lý logging groups.
- Ghi đè level theo profile hoặc environment.
- Điều chỉnh mức log runtime qua Actuator khi thích hợp.

### 22.2. Khi nào cần logback-spring.xml hoặc backend config?

Nếu cần:

- Nhiều appenders gửi tới file, console và hệ thống tập trung.
- Custom encoder, structured JSON, hoặc masking/filter phức tạp.
- Rolling policies và retention.
- Định dạng khác nhau theo logger, môi trường hoặc appender.
- Định tuyến riêng cho audit/operational logs.

Bạn có thể cần cấu hình backend như `logback-spring.xml`. Điều đó không thay đổi nguyên tắc về tên logger và hierarchy, nhưng tạo thêm các yếu tố có thể ảnh hưởng output.

### 22.3. Đừng cấu hình chồng chéo không chủ đích

Nếu một logger có level trong YAML, lại được điều khiển qua cấu hình native backend và Actuator, trạng thái runtime có thể khác điều bạn dự đoán từ một file.

Khi cần chẩn đoán, hãy kiểm tra hiệu lực thực tế bằng Actuator hoặc logging system inspection, thay vì chỉ kết luận từ một dòng config.

## 23. Startup logging và cấu hình quá muộn

Logging được khởi tạo rất sớm trong quá trình Spring Boot startup, trước khi toàn bộ application context và mọi bean đã sẵn sàng.

Vì thế không phải cơ chế thêm property nào cũng kịp tác động lên logging initialization.

Ví dụ, `@PropertySource` trên một `@Configuration` class thường được xử lý trong giai đoạn refresh; thời điểm đó quá muộn cho một số cấu hình log rất sớm của Boot.

Nên đặt cấu hình logging trong:

- `application.properties` / `application.yml` và nguồn config data mà Boot nạp sớm.
- Environment variables hoặc command-line arguments.
- JVM system properties phù hợp.
- Cơ chế cấu hình logging startup được Spring Boot hỗ trợ.

Nếu log lúc startup không tuân thủ mức bạn mong muốn nhưng log runtime thì có, hãy xem lại **nguồn property và thời điểm nó được nạp**.

### 23.1. Spring Boot logging và logger API không hoàn toàn giống nhau

Code ứng dụng có thể dùng `LoggerFactory.getLogger(...)`, trong khi Boot tổ chức quá trình khởi tạo logging backend bằng hạ tầng riêng.

Sự khác biệt này không ảnh hưởng cách dùng `logging.level.*` thông thường, nhưng giải thích vì sao không nên tự can thiệp vào backend rất sớm trong một bean tạo muộn rồi kỳ vọng thay đổi được mọi log từ lúc JVM bắt đầu.

## 24. Kiểm thử cấu hình logging

Có hai thứ có thể kiểm tra:

1. **Cấu hình có tạo effective level mong đợi không?**
2. **Một lời gọi log ở level đó có được phát theo output được cấu hình không?**

Một context integration test phù hợp hơn unit test tạo service bằng `new` nếu bạn muốn kiểm tra chính xác cách Spring Boot nạp `logging.level.*`.

### 24.1. Test bằng OutputCaptureExtension

Spring Boot test hỗ trợ capture output để kiểm tra một dòng log quan sát được.

Ví dụ giả sử `PaymentService` có method gọi `log.debug("Payment debug marker")`:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.system.CapturedOutput;
import org.springframework.boot.test.system.OutputCaptureExtension;

@SpringBootTest(properties = {
        "logging.level.root=INFO",
        "logging.level.com.example.shop.payment=DEBUG"
})
@ExtendWith(OutputCaptureExtension.class)
class PaymentLoggingTest {

    @Autowired
    private PaymentService paymentService;

    @Test
    void emitsDebugLogWhenPackageIsEnabled(CapturedOutput output) {
        paymentService.emitDebugMarker();

        assertThat(output.getOut()).contains("Payment debug marker");
    }
}
~~~

Code cần method `emitDebugMarker()` trong `PaymentService` có lời gọi debug tương ứng; ví dụ minh họa ý tưởng, không phải toàn bộ source của service.

Test này phụ thuộc việc console appender/logging output được cấu hình phù hợp. Nếu project đổi logging backend hoặc tắt console output, một assertion trên stdout có thể không còn phù hợp mặc dù effective level vẫn đúng.

### 24.2. Tránh so sánh nguyên dòng log

Timestamp, thread name, logger name, ANSI color và pattern có thể thay đổi. Khi test hành vi logging, ưu tiên kiểm tra thông điệp marker hoặc structured field quan trọng thay vì so khớp toàn bộ một dòng console.

### 24.3. Test log level với logging API

Nếu chỉ cần xác nhận debug đã bật cho logger cụ thể trong context:

~~~java
import org.slf4j.LoggerFactory;

boolean debugEnabled = LoggerFactory
        .getLogger("com.example.shop.payment.PaymentService")
        .isDebugEnabled();
~~~

Dùng trong integration test đã khởi tạo logging system với property mong muốn. Không cần tạo service hoặc gọi method thật để hỏi effective logging flag.

Lưu ý test có thể chạy chung JVM và context caching với những cấu hình log khác nhau. Nếu test thay đổi log level runtime bằng backend API hoặc Actuator, cần khôi phục trạng thái sau test để tránh phụ thuộc thứ tự test.

### 24.4. Test loggers endpoint

Nếu dự án expose Actuator loggers endpoint, có thể dùng integration test để đọc configured/effective level hoặc đổi level trong môi trường test cô lập.

Không nên để một test tự động đổi log của instance production. Tất cả thao tác thay đổi runtime level nên diễn ra trong môi trường thử nghiệm có quyền và lifecycle rõ ràng.

## 25. Các lỗi cấu hình phổ biến

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Đặt DEBUG nhưng không có dòng DEBUG | Logger name sai hoặc code không phát log ở DEBUG | Kiểm tra `Logger.getName()` và code path |
| Chỉ một số class trong package phát DEBUG | Logger con có override riêng hoặc backend filter | Kiểm tra effective level từng logger |
| INFO biến mất sau khi đổi root | Root đặt WARN/ERROR | Khôi phục root hoặc đặt override phù hợp |
| Class-level env variable không hoạt động | Tên class bị lowercase do relaxed env binding | Dùng properties/YAML, JVM property hoặc `SPRING_APPLICATION_JSON` |
| `logging.level.com.example.*` không áp như mong đợi | Hiểu nhầm wildcard | Cấu hình `com.example` không có `*` |
| Bật `--debug` nhưng app logger vẫn INFO | Debug flag chỉ bật nhóm logger lựa chọn | Đặt `logging.level.com.example=DEBUG` |
| Log không đổi khi sửa file YAML mà không restart | Cấu hình nạp từ startup | Restart hoặc dùng Actuator runtime |
| Đổi Actuator chỉ ảnh hưởng một pod | Thay đổi level trong một instance | Điều phối thay đổi cho đúng các instance |
| Actuator trả 404 | Endpoint chưa được expose, sai base path hoặc phụ thuộc thiếu | Kiểm tra Actuator/exposure/path |
| Actuator trả 401/403 | Endpoint được bảo vệ | Dùng credentials/quyền được ủy quyền |
| Có hai dòng log giống nhau | Appender/additivity cấu hình trùng | Kiểm tra backend appenders |
| SQL không hiện | Sai logger category cho JDBC/Hibernate version | Xác định framework và logger thực |
| Log quá nhiều sau khi bật TRACE | Phạm vi quá rộng hoặc logger hot path | Hạ level, giới hạn thời gian, áp dụng sampling |
| Logger có effective DEBUG mà không có console output | Appender/filter loại event | Kiểm tra cấu hình backend |
| Test có log khác production | Profile, runtime classpath hoặc test config khác | Kiểm tra active sources và effective level |

### 25.1. Chuỗi kiểm tra thực tế

Khi một cấu hình `logging.level` không có tác dụng, hãy làm theo thứ tự:

1. **Xác định log statement**: code gọi `log.trace`/`log.debug`/`log.info` nào?
2. **Xác định tên logger thực**: `getLogger(Class)`, `getLogger(String)` hay logger do thư viện tạo?
3. **Xác định property level**: key có đúng tên logger/package không?
4. **Kiểm tra nguồn cấu hình**: file, profile, env, system property, command line có ghi đè cùng key không?
5. **Kiểm tra hierarchy**: logger con có configured level riêng không?
6. **Kiểm tra effective level**: qua Actuator/logging API nếu có.
7. **Kiểm tra output pipeline**: appender/filter/pattern có giữ event không?
8. **Kiểm tra instance đang chạy**: đúng pod, process, version, profile và lệnh start chưa?

Không nên sửa nhiều yếu tố cùng lúc; nếu vừa đổi tên logger, vừa chuyển backend và vừa đặt root TRACE, bạn sẽ khó biết thay đổi nào giải quyết vấn đề.

## 26. Một cấu hình mẫu cho hệ thống nhiều module

Giả sử bạn muốn:

- Root ở INFO.
- Application code dưới `com.example.shop` ở INFO.
- Payment package ở DEBUG.
- Gateway HTTP client cụ thể ở TRACE để chẩn đoán.
- Một scheduler ồn ào chỉ WARN.
- Transaction infrastructure ở INFO.

~~~yaml
logging:
  level:
    root: INFO
    "com.example.shop": INFO
    "com.example.shop.payment": DEBUG
    "com.example.shop.payment.PaymentGatewayClient": TRACE
    "com.example.shop.payment.PaymentRetryScheduler": WARN
    "org.springframework.transaction": INFO
~~~

Khi ứng dụng chạy, kết quả lý tưởng:

| Logger | Effective level |
| --- | --- |
| `com.example.shop.order.OrderService` | INFO |
| `com.example.shop.inventory.InventoryService` | INFO |
| `com.example.shop.payment.PaymentService` | DEBUG |
| `com.example.shop.payment.PaymentGatewayClient` | TRACE |
| `com.example.shop.payment.PaymentRetryScheduler` | WARN |
| `org.springframework.transaction.interceptor.TransactionInterceptor` | INFO |
| Logger không có cấu hình riêng | INFO (từ root, nếu không có override khác) |

Trong một ứng dụng thực tế, có thể có auto-configuration hoặc native backend configuration đặt thêm levels. Hãy kiểm tra runtime effective level khi cần xác nhận chính xác, đặc biệt với các thư viện và platform-specific setup.

### 26.1. Cách hạ mức khi đã debug xong

Sau khi xử lý lỗi:

~~~yaml
logging:
  level:
    root: INFO
    "com.example.shop": INFO
    "com.example.shop.payment": INFO
~~~

Hoặc nếu level được thay tạm qua Actuator, xóa configured level trực tiếp bằng `{"configuredLevel": null}` để logger quay lại kế thừa phù hợp.

Quy trình thay đổi cần minh bạch: ai bật, logger nào, trong bao lâu, trên instance nào và lúc nào khôi phục. Điều này đặc biệt quan trọng với logger có thể ghi thông tin nhạy cảm.

## 27. Bài tập thực hành

### Bài tập 1 — Root và package

Tạo hai service ở package `com.example.demo.order` và `com.example.demo.payment`, mỗi service ghi `TRACE`, `DEBUG`, `INFO`, `WARN`. Đặt:

~~~properties
logging.level.root=INFO
logging.level.com.example.demo.payment=DEBUG
~~~

Dự đoán log nào xuất hiện, chạy ứng dụng và giải thích sự khác nhau.

### Bài tập 2 — Logger cụ thể ghi đè package

Giữ package payment DEBUG nhưng đặt một logger cụ thể WARN:

~~~properties
logging.level.com.example.demo.payment=DEBUG
logging.level.com.example.demo.payment.PollingService=WARN
~~~

Quan sát method trong `PollingService` chỉ còn WARN/ERROR, trong khi service khác vẫn phát DEBUG.

### Bài tập 3 — Logger name tùy ý

Trong một service, tạo:

~~~java
Logger audit = LoggerFactory.getLogger("audit.payment");
~~~

Thử `logging.level.com.example.demo.payment=DEBUG` và `logging.level.audit.payment=DEBUG`. Giải thích vì sao chỉ cấu hình thứ hai tác động trực tiếp lên logger tùy đặt tên.

### Bài tập 4 — YAML và properties tương đương

Viết hai cách thể hiện cùng một cấu hình root INFO, package DEBUG và logger class TRACE. Bảo đảm indentation, dotted key và logger name đúng.

### Bài tập 5 — Environment variable có chữ hoa

Thử cấu hình logger package bằng `LOGGING_LEVEL_COM_EXAMPLE_DEMO_PAYMENT=DEBUG`. Sau đó thử tên logger theo class `PaymentService` qua environment variable và giải thích giới hạn lowercase. Dùng `SPRING_APPLICATION_JSON` hoặc command-line để đặt class logger chính xác.

### Bài tập 6 — Group nhiều package

Định nghĩa `logging.group.checkout` gồm `com.example.demo.order` và `com.example.demo.payment`. Đặt `logging.level.checkout=DEBUG`. Quan sát log từ cả hai package mà không cần cấu hình hai khóa level riêng.

### Bài tập 7 — Actuator loggers

Trong môi trường phát triển, bật Actuator loggers endpoint có bảo vệ phù hợp. Lấy `configuredLevel` và `effectiveLevel` của một logger. Đổi level từ INFO sang TRACE, rồi gửi `{"configuredLevel": null}` để xóa override và quan sát effective level kế thừa.

### Bài tập 8 — Phân biệt --debug

Chạy ứng dụng với `--debug` nhưng không thay logging.level ứng dụng. Quan sát các thông tin chẩn đoán của Spring Boot. Sau đó đặt `logging.level.com.example.demo=DEBUG` và giải thích thay đổi trong log service.

### Bài tập 9 — Hibernate SQL logger

Trong một project Spring Boot dùng Hibernate 6, bật `org.hibernate.SQL=DEBUG`. Quan sát SQL được tạo rồi cân nhắc `org.hibernate.orm.jdbc.bind=TRACE` trong môi trường dữ liệu giả lập. Giải thích vì sao không nên bật bind parameters một cách tùy tiện trên production.

### Bài tập 10 — Performance và placeholder

So sánh:

~~~java
log.debug("Snapshot={}", buildExpensiveSnapshot());
~~~

với:

~~~java
if (log.isDebugEnabled()) {
    log.debug("Snapshot={}", buildExpensiveSnapshot());
}
~~~

Khi DEBUG tắt, xác định cách nào vẫn thực hiện hàm tạo snapshot và vì sao placeholder không tự trì hoãn việc tính toán argument.

## 28. Ghi nhớ

`logging.level` trong Spring Boot cho phép bạn thiết lập ngưỡng log theo **logger name**. `logging.level.root` là mức gốc để kế thừa; `logging.level.com.example.shop.payment` áp cho namespace payment; `logging.level.com.example.shop.payment.PaymentService` áp trực tiếp cho logger có tên đó. Logger con có thể override level của parent theo hierarchy phân cách bằng dấu chấm.

Cấu hình theo package không quét bytecode hoặc vị trí thư mục Java; nó tác động tới **logger name được code hoặc thư viện sử dụng**. Hãy kiểm tra `LoggerFactory.getLogger(...)` và tên thực tế khi một cấu hình không có tác dụng. Root INFO không ngăn một logger cụ thể bật DEBUG/TRACE, và một logger cụ thể có thể đặt WARN để giảm log trong package đang bật DEBUG.

Phân biệt **property-source precedence** với **logger hierarchy**: nguồn ưu tiên cao hơn ghi đè giá trị của cùng một property key; còn level hiệu lực của logger được tìm theo tên cụ thể nhất trong hierarchy. Với environment variables, cấu hình package thường thuận tiện, nhưng tên class có chữ hoa có thể cần `SPRING_APPLICATION_JSON`, properties/YAML hoặc JVM/command-line property để giữ tên đúng.

Actuator `/actuator/loggers` có thể kiểm tra `configuredLevel`/`effectiveLevel` và thay đổi level khi ứng dụng đang chạy, nhưng thay đổi đó không tự tồn tại sau restart hoặc đồng bộ cho mọi replica. Trong production, chỉ tăng log theo phạm vi cần thiết, giữ output an toàn và phục hồi level sau khi chẩn đoán. **Log level chỉ quyết định message có được phép phát; nội dung log, appender, format và bảo mật dữ liệu vẫn là trách nhiệm thiết kế riêng.**
