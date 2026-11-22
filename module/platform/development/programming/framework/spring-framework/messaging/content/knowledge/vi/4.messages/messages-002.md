# Hợp đồng Message và kiểu dữ liệu của payload

## 1. Message là một envelope

Trong Spring Messaging, `Message<T>` biểu diễn một thông điệp gồm hai phần: **payload** và **headers**. Payload là nội dung chính mà consumer cần xử lý; headers là metadata đi kèm để định danh, tương quan, định tuyến hoặc mô tả cách diễn giải nội dung.

- `Message<T>`: abstraction của thông điệp; `T` là kiểu payload ở mức Java.
- `MessageHeaders`: tập metadata có tên, truy cập theo key; giá trị header có kiểu tổng quát `Object`.
- `MessageBuilder`: cách tạo message mới hoặc tạo message dựa trên một message hiện có.

Ví dụ, sự kiện `OrderPlaced` có thể mang payload chứa mã đơn hàng, khách hàng, tổng tiền và thời điểm tạo. Headers có thể mang `eventId`, `correlationId` và `schemaVersion`. Nhờ vậy consumer có thể xử lý dữ liệu nghiệp vụ mà vẫn theo dõi được thông điệp trong một luồng xử lý lớn hơn.

Message là abstraction ở tầng ứng dụng. Một `Message` được tạo thành công trong bộ nhớ không chứng minh rằng nó đã được gửi tới broker, lưu bền vững hoặc được consumer xử lý. Các bảo đảm giao nhận phụ thuộc channel, adapter, broker và cấu hình.

## 2. Cấu trúc và vai trò của payload

Payload là dữ liệu chính của message. `Message<T>` giúp mã Java thể hiện kiểu dữ liệu mong đợi, ví dụ `Message<OrderPlaced>` hoặc `Message<String>`. Kiểu này hỗ trợ compiler và người đọc hiểu hợp đồng giữa producer và handler.

Các dạng payload thường gặp:

| Kiểu payload | Khi phù hợp | Lưu ý |
| --- | --- | --- |
| DTO hoặc Java `record` | Sự kiện/command có cấu trúc và hợp đồng rõ | Nên có trường cụ thể, tên ổn định và quy tắc versioning |
| `String` | Văn bản đơn giản, lệnh ngắn hoặc nội dung text | Quy định encoding và ý nghĩa của chuỗi |
| `byte[]` hoặc `ByteBuffer` | Dữ liệu nhị phân, file hoặc payload đã encode | Cần xác định format, kích thước tối đa và cách quản lý bộ nhớ |
| Kiểu số, boolean hoặc giá trị đơn | Message nhỏ có một ý nghĩa duy nhất | Tránh dùng kiểu quá mơ hồ nếu sau này cần mở rộng hợp đồng |
| Collection hoặc cấu trúc map | Danh sách hoặc dữ liệu linh hoạt có schema rõ | Kiểm tra phần tử, kiểu runtime và tương thích khi thay đổi |

Với message nghiệp vụ được trao đổi giữa nhiều thành phần, DTO hoặc record thường dễ quản lý hơn việc gửi trực tiếp entity của ORM. Entity có thể chứa proxy lazy, quan hệ vòng, trạng thái persistence hoặc chi tiết nội bộ của database. Những chi tiết đó khiến serialization khó dự đoán và làm producer/consumer phụ thuộc vào mô hình lưu trữ.

Không nên dùng `Object` làm kiểu payload chung cho mọi message nếu consumer cần biết cấu trúc thực tế. `Object` làm yếu hợp đồng và buộc consumer phải ép kiểu hoặc suy luận kiểu runtime. Tương tự, `Map<String, Object>` linh hoạt nhưng cần schema, quy tắc tên field và validation rõ ràng nếu được dùng qua ranh giới dịch vụ.

### 2.1. Kiểu generic và kiểu runtime

`Message<OrderPlaced>` giúp compiler kiểm tra phần lớn thao tác trong mã nguồn Java, nhưng generic type bị type erasure ở runtime. Khi message được nhận từ broker hoặc được deserialize từ JSON, khai báo generic tại producer không tự bảo đảm payload đã trở lại đúng kiểu.

Consumer cần biết kiểu đích và dùng converter/serializer thích hợp. Sau khi chuyển đổi, vẫn cần kiểm tra dữ liệu thực tế: field bắt buộc, miền giá trị, phiên bản schema và các bất biến nghiệp vụ. Không ép kiểu một payload không rõ nguồn gốc chỉ dựa trên header do producer gửi.

## 3. Vai trò của headers

Headers là metadata gắn với envelope. Chúng nên mô tả thông điệp hoặc quá trình truyền tải, thay vì trở thành nơi chứa toàn bộ dữ liệu nghiệp vụ.

Các header thường hữu ích:

| Header | Mục đích | Quy tắc sử dụng |
| --- | --- | --- |
| `eventId` hoặc `messageId` nghiệp vụ | Định danh ổn định của sự kiện/thông điệp | Giữ nguyên khi retry hoặc phát lại cùng một sự kiện để consumer chống trùng |
| `correlationId` | Liên kết các message/request thuộc cùng một luồng nghiệp vụ | Truyền qua các bước downstream; không dùng làm khóa chống trùng nếu một luồng có nhiều message |
| `causationId` | Cho biết message được tạo ra do message/sự kiện nào | Hữu ích khi dựng quan hệ nguyên nhân trong trace/audit |
| `schemaVersion` | Phiên bản hợp đồng payload | Phải có chính sách tương thích và nâng cấp consumer |
| `contentType` | Mô tả dạng nội dung như JSON hoặc text | Phải phản ánh representation thực tế và được converter hiểu |
| Header định tuyến | Chọn destination, channel hoặc loại handler theo cấu hình | Kiểm soát giá trị cho phép; không coi header bên ngoài là lệnh đáng tin cậy |

`MessageHeaders` cũng có các header do framework quản lý như ID và timestamp. Chúng hữu ích cho việc nhận diện message object và thời điểm tạo theo cơ chế framework. Không nên mặc định ID do framework tạo là ID nghiệp vụ ổn định qua retry, serialize hoặc publish lại. Nếu cần chống xử lý trùng, hãy tạo `eventId`/idempotency key có vòng đời được quy định rõ.

Header có kiểu giá trị tổng quát `Object`, nhưng không có nghĩa mọi kiểu Java đều có thể truyền qua mọi transport. Adapter/broker có thể chỉ hỗ trợ một tập kiểu header nhất định, chuyển đổi chúng thành metadata của giao thức hoặc loại bỏ header không được hỗ trợ. Hãy ưu tiên giá trị đơn giản, có thể serialize và thống nhất kiểu giữa producer/consumer.

Không đặt mật khẩu, access token, dữ liệu cá nhân không cần thiết hoặc payload lớn vào headers. Metadata thường xuất hiện trong log, tracing, broker management UI và công cụ vận hành. Chỉ truyền thông tin tối thiểu và áp dụng chính sách bảo vệ phù hợp.

## 4. Tạo message bằng MessageBuilder

`MessageBuilder` giúp tạo message với payload và thêm metadata trước khi build. Sau khi build, message và `MessageHeaders` được thiết kế theo hướng immutable: không sửa trực tiếp map headers của message đã tạo. Nếu cần thay đổi metadata, hãy tạo message mới từ message cũ bằng builder.

Ví dụ tạo message:

~~~java
Message<OrderPlaced> message = MessageBuilder
        .withPayload(event)
        .setHeader("eventId", "evt-1001")
        .setHeader("correlationId", "corr-77")
        .setHeader("schemaVersion", 1)
        .build();
~~~

Để tạo message dựa trên một message đã có, có thể dùng `MessageBuilder.fromMessage(existing)` rồi thay hoặc bổ sung header trước khi gọi `build()`. Chỉ sao chép những metadata cần giữ; khi tạo một sự kiện nghiệp vụ mới, phải cân nhắc tạo ID mới thay vì vô tình dùng lại ID của message cũ.

Message envelope immutable không đồng nghĩa payload luôn immutable. Nếu payload là một object mutable, code khác vẫn có thể thay đổi các field của object đó sau khi message được build. Ưu tiên record, immutable DTO, collection không thể sửa hoặc sao chép dữ liệu tại ranh giới gửi/nhận khi cần bảo đảm snapshot nhất quán.

## 5. Hợp đồng payload cần được thiết kế như API

Payload là hợp đồng giữa producer và consumer. Khi hai bên được triển khai độc lập, việc đổi field có thể làm hỏng consumer cũ giống như thay đổi một REST API.

Một hợp đồng tốt nên xác định:

1. **Tên và ý nghĩa:** field mô tả điều gì, dùng đơn vị nào, có phân biệt null với không có field hay không.
2. **Kiểu dữ liệu:** string, integer, decimal, boolean, timestamp, enum, object hoặc danh sách; quy định format và giới hạn.
3. **Bắt buộc/tùy chọn:** field nào luôn có, field nào có thể thiếu, giá trị mặc định là gì.
4. **Định danh:** event ID, aggregate ID, correlation/causation ID và quy tắc duy nhất.
5. **Thời gian:** timezone, format, độ chính xác và ý nghĩa của thời điểm phát sinh so với thời điểm gửi.
6. **Phiên bản:** cách consumer nhận biết schema và cách rollout producer/consumer.
7. **Validation:** miền giá trị, bất biến nghiệp vụ, giới hạn kích thước và cách phản hồi khi dữ liệu sai.
8. **Bảo mật:** trường nào nhạy cảm, ai được đọc và có cần mã hóa hoặc che dữ liệu trong log không.

Đặt tên sự kiện theo điều đã xảy ra, chẳng hạn `OrderPlaced`, và mô tả dữ liệu cần thiết để consumer hiểu sự kiện độc lập. Đừng buộc consumer phải truy cập trực tiếp object nội bộ hoặc database của producer để diễn giải payload.

### 5.1. Thay đổi schema có tương thích

Những thay đổi thường dễ tương thích hơn:

- Thêm field tùy chọn mà consumer cũ có thể bỏ qua.
- Consumer chấp nhận field không biết tới và dùng default rõ ràng cho field mới bị thiếu.
- Thêm một giá trị enum chỉ khi consumer có chiến lược xử lý giá trị chưa biết.

Những thay đổi thường phá vỡ tương thích:

- Đổi tên hoặc xóa field đang được consumer dùng.
- Đổi kiểu dữ liệu hoặc ý nghĩa/đơn vị của field mà vẫn giữ tên cũ.
- Biến field tùy chọn thành bắt buộc mà producer cũ chưa gửi.
- Thay đổi cách biểu diễn timestamp, decimal hoặc enum mà không có quy tắc chuyển đổi.

Với thay đổi không tương thích, hãy phát hành schema/version mới hoặc có giai đoạn chuyển tiếp: consumer hỗ trợ cả hai phiên bản, producer triển khai sau, theo dõi tỷ lệ message cũ rồi mới bỏ hỗ trợ. Không chỉ đổi `schemaVersion` trong header mà không thay đổi hoặc kiểm tra nội dung thực tế.

## 6. Chuyển đổi kiểu và serialization

Cần phân biệt ba bước:

- **Tạo payload trong ứng dụng:** producer tạo object Java hoặc dữ liệu gốc.
- **Message conversion:** chuyển payload sang kiểu mà handler đích yêu cầu hoặc tạo message từ dữ liệu khác.
- **Serialization theo transport:** biến dữ liệu thành byte representation để gửi qua mạng/lưu trong broker; phía nhận deserialize trở lại.

Spring Messaging có abstraction `MessageConverter` cho việc chuyển đổi payload của message. Converter có thể dùng metadata như `contentType` để chọn cách diễn giải. Các converter JSON thường cần thư viện JSON tương ứng; lựa chọn converter và cấu hình cụ thể phụ thuộc phiên bản Spring và adapter.

`contentType` nên phản ánh representation thật. Ví dụ, nếu payload đã được serialize thành JSON bytes, `application/json` là metadata phù hợp. Nếu payload vẫn là một Java object trong bộ nhớ, việc gắn `application/json` không tự serialize object thành JSON. Đừng nhầm khai báo content type với thao tác chuyển đổi.

Serialization là ranh giới cần được thiết kế rõ:

- JSON dễ quan sát và tương thích rộng, nhưng cần quy định kiểu số, timestamp, enum, null và unknown fields.
- Avro/Protocol Buffers hoặc format schema-based có thể cung cấp schema và kiểm soát tương thích tốt hơn, nhưng cần quản lý registry/tooling và version.
- Java native serialization thường làm hai bên phụ thuộc sâu vào class/version và có rủi ro bảo mật; không nên dùng làm hợp đồng mặc định giữa các dịch vụ không cùng vòng đời.
- Với binary payload, cần ghi rõ encoding, compression, checksum nếu cần và giới hạn kích thước.

Không gửi trực tiếp object Java qua broker với giả định consumer ở ngôn ngữ khác sẽ hiểu được. Hãy thống nhất wire format, schema và cách xử lý phiên bản trước khi tích hợp.

## 7. Validation ở producer và consumer

Validation cần diễn ra ở cả hai phía vì producer có thể có bug, message có thể cũ, bị gửi lại hoặc đến từ một hệ thống khác.

**Trước khi publish:** kiểm tra field bắt buộc, miền giá trị, quyền phát sự kiện và các bất biến có thể xác minh trong transaction hiện tại. Không phát event `OrderPlaced` nếu đơn hàng chưa được commit ở trạng thái hợp lệ theo quy tắc nghiệp vụ.

**Khi nhận:** kiểm tra payload đã convert đúng kiểu, schema version được hỗ trợ, ID có hợp lệ, field bắt buộc có mặt và message có được phép xử lý trong trạng thái hiện tại hay không. Không tin cậy hoàn toàn header định tuyến hoặc tenant ID do bên ngoài gửi; xác thực theo ranh giới bảo mật của hệ thống.

Validation dữ liệu và validation nghiệp vụ là hai việc khác nhau. Một `amount` có thể là số hợp lệ nhưng không được âm theo nghiệp vụ; một `orderId` có thể đúng format nhưng không tồn tại hoặc không thuộc tenant hiện tại.

Khi message sai, hãy phân loại lỗi:

- Lỗi tạm thời như database/network không sẵn sàng: retry có giới hạn và backoff.
- Lỗi schema hoặc dữ liệu không hợp lệ: cách ly/DLQ để kiểm tra, không retry vô hạn.
- Vi phạm nghiệp vụ vĩnh viễn: ghi nhận kết quả từ chối theo hợp đồng, tránh để message quay vòng.
- Lỗi lập trình bất ngờ: log đầy đủ ngữ cảnh an toàn, phát cảnh báo và áp dụng chính sách retry/DLQ.

## 8. Payload và headers trong hệ thống nhiều thành phần

### 8.1. Phân chia dữ liệu đúng chỗ

Payload nên chứa dữ liệu nghiệp vụ cần để xử lý message. Headers nên chứa metadata điều phối và quan sát. Ví dụ, `orderId`, `items` và `totalAmount` là dữ liệu của sự kiện; `eventId`, `correlationId`, `schemaVersion` và `contentType` là metadata.

Không đặt `totalAmount` chỉ trong header vì đó là dữ liệu nghiệp vụ. Cũng không cần lặp toàn bộ payload trong headers. Nếu một giá trị vừa cần cho nghiệp vụ vừa dùng để định tuyến, hãy định nghĩa rõ nguồn dữ liệu chuẩn và cách đồng bộ giữa payload/header để tránh lệch nhau.

### 8.2. Correlation và tracing

`correlationId` giúp liên kết nhiều message của một luồng nghiệp vụ; `causationId` giúp xác định message trực tiếp tạo ra message hiện tại. Trace ID/span ID phục vụ tracing phân tán và có vòng đời riêng. Chúng có thể liên hệ với correlation ID nhưng không nên gộp thành một khái niệm duy nhất.

Khi một consumer tạo message mới, hãy quyết định metadata nào cần truyền tiếp, metadata nào cần tạo mới. Ví dụ correlation ID có thể được giữ xuyên suốt một workflow; event ID phải mới cho một sự kiện mới; causation ID có thể tham chiếu event vừa xử lý. Không copy toàn bộ headers một cách mù quáng vì có thể mang theo reply channel, error channel, routing hoặc dữ liệu nội bộ không phù hợp với destination mới.

### 8.3. Kích thước payload

Payload lớn làm tăng thời gian serialize, truyền tải, lưu trữ, memory pressure và chi phí retry. Nếu message chứa file hoặc blob lớn, cân nhắc lưu nội dung ở object storage rồi gửi reference có kiểm soát như object key, checksum, media type và kích thước. Reference phải có quyền truy cập, thời hạn và quy tắc dọn dẹp phù hợp; không dùng URL công khai không giới hạn cho dữ liệu riêng tư.

Đặt giới hạn kích thước ở producer và broker/consumer. Tránh gửi cả object graph lớn chỉ vì thuận tiện. Chỉ giữ field cần thiết để consumer hoàn thành nhiệm vụ.

## 9. Ví dụ Java 17 + Spring Messaging 6.2

Ví dụ sau tạo một message có payload kiểu `OrderPlaced` và một số metadata. Đây là message object trong bộ nhớ để minh họa hợp đồng; ví dụ không kết nối broker, không serialize JSON và không chứng minh delivery guarantee.

Tạo Maven project với cấu trúc:

~~~text
message-contract-demo/
  pom.xml
  src/main/java/com/example/messaging/MessageContractDemo.java
~~~

`pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>message-contract-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <spring.version>6.2.8</spring.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-messaging</artifactId>
            <version>${spring.version}</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`src/main/java/com/example/messaging/MessageContractDemo.java`:

~~~java
package com.example.messaging;

import java.math.BigDecimal;
import java.time.Instant;

import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.support.MessageBuilder;

public final class MessageContractDemo {
    private MessageContractDemo() {
    }

    public record OrderPlaced(
            String orderId,
            String customerId,
            BigDecimal totalAmount,
            Instant occurredAt) {
    }

    public static void main(String[] args) {
        OrderPlaced event = new OrderPlaced(
                "ORD-1001",
                "CUS-42",
                new BigDecimal("125.50"),
                Instant.parse("2026-11-07T03:00:00Z"));

        Message<OrderPlaced> message = MessageBuilder
                .withPayload(event)
                .setHeader("eventId", "evt-1001")
                .setHeader("correlationId", "corr-77")
                .setHeader("schemaVersion", 1)
                .build();

        OrderPlaced payload = message.getPayload();
        MessageHeaders headers = message.getHeaders();

        System.out.println("orderId=" + payload.orderId());
        System.out.println("totalAmount=" + payload.totalAmount().toPlainString());
        System.out.println("eventId=" + headers.get("eventId"));
        System.out.println("schemaVersion=" + headers.get("schemaVersion"));
        System.out.println("correlationId=" + headers.get("correlationId"));
    }
}
~~~

Biên dịch và chạy từ thư mục chứa `pom.xml` bằng JDK 17+ và Maven:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=com.example.messaging.MessageContractDemo
~~~

Stdout:

~~~text
orderId=ORD-1001
totalAmount=125.50
eventId=evt-1001
schemaVersion=1
correlationId=corr-77
~~~

Điểm cần quan sát:

- `Message<OrderPlaced>` thể hiện kiểu payload dự kiến trong mã nguồn.
- Record `OrderPlaced` gom dữ liệu nghiệp vụ thành hợp đồng có cấu trúc.
- `eventId` và `correlationId` nằm trong headers vì chúng phục vụ định danh và theo dõi luồng.
- `schemaVersion` giúp consumer biết phiên bản hợp đồng cần diễn giải.
- `MessageHeaders` được đọc như metadata; không cần và không nên sửa trực tiếp map headers sau khi build.

Trong tích hợp thực tế, adapter/converter sẽ quyết định object này được chuyển thành JSON, byte array hoặc wire format khác. Consumer phải deserialize và validate trước khi áp dụng nghiệp vụ.

## 10. Những lỗi thường gặp

- **Đưa toàn bộ dữ liệu vào headers:** headers là metadata, không phải nơi thay thế payload có schema.
- **Dùng `Object` hoặc map không có hợp đồng:** consumer phải đoán kiểu và field, dễ phát sinh lỗi runtime.
- **Cho rằng generic type bảo vệ dữ liệu lúc nhận:** type erasure và deserialize có thể tạo payload khác kiểu dự kiến; cần kiểm tra runtime.
- **Dùng framework message ID làm idempotency key:** ID của message object có thể thay đổi khi tạo message mới; dùng ID nghiệp vụ ổn định.
- **Đổi field hoặc kiểu dữ liệu mà không versioning:** consumer cũ có thể lỗi hoặc diễn giải sai dữ liệu.
- **Gắn `contentType=application/json` nhưng payload chưa được serialize:** metadata không tự biến Java object thành JSON.
- **Gửi JPA entity hoặc object graph lớn:** serialization có thể kéo theo lazy loading, vòng tham chiếu và phụ thuộc persistence.
- **Tin header từ bên ngoài:** header có thể bị giả mạo hoặc không được adapter bảo toàn; xác thực dữ liệu tại consumer.
- **Giữ payload mutable rồi sửa sau khi publish:** handler khác có thể quan sát trạng thái thay đổi ngoài dự kiến.
- **Copy tất cả headers sang message mới:** có thể mang theo ID, reply/error channel hoặc routing metadata không phù hợp.
- **Không đặt giới hạn kích thước:** message lớn gây áp lực bộ nhớ, mạng, broker và thời gian retry.

## 11. Checklist review hợp đồng Message

1. Payload có kiểu cụ thể, tên và ý nghĩa field rõ ràng không?
2. Consumer có thể hiểu payload mà không truy cập nội bộ producer không?
3. Field bắt buộc, nullable, đơn vị, timestamp và enum đã được định nghĩa chưa?
4. `eventId`/idempotency key có ổn định qua retry và replay không?
5. `correlationId` và `causationId` có được truyền theo đúng vòng đời không?
6. `schemaVersion` có quy tắc tương thích và rollout không?
7. `contentType` có khớp với representation thực tế không?
8. Converter/serializer có được cấu hình giống nhau ở producer và consumer không?
9. Consumer có validate schema, quyền truy cập và bất biến nghiệp vụ không?
10. Payload/header có chứa bí mật, dữ liệu nhạy cảm hoặc nội dung quá lớn không?
11. Adapter/broker có hỗ trợ kiểu header và payload đã chọn không?
12. Message mới có cần giữ metadata từ message cũ hay phải tạo ID/causation mới không?

## 12. Ghi nhớ

Spring `Message<T>` là envelope gồm payload và headers. Payload mang dữ liệu nghiệp vụ với kiểu được thể hiện trong mã Java; headers mang metadata định danh, tương quan, định tuyến và mô tả nội dung. `MessageBuilder` tạo message mới, còn `MessageHeaders` được thiết kế immutable; tuy nhiên payload mutable vẫn có thể bị thay đổi nếu dùng chung object. Generic type không thay thế deserialize và validation tại consumer. Khi message đi qua broker, cần thống nhất wire format, content type, schema version, giới hạn kích thước và khả năng tương thích. Hãy thiết kế payload như một API có vòng đời, dùng ID nghiệp vụ ổn định để chống trùng và chỉ đưa metadata cần thiết vào headers.