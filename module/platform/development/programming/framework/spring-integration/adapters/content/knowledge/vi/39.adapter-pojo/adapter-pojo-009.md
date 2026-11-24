# Expression adapter

Trong `SPRING_INTEGRATION_ADAPTERS`, inbound và outbound adapter đảm nhiệm việc trao đổi dữ liệu với hệ thống ngoài; `MessageChannel` kết nối các endpoint trong ứng dụng. Ở giữa các bước đó, nhiều tác vụ chỉ cần đọc một giá trị, chuẩn hóa payload, kiểm tra điều kiện hoặc chọn channel đích. Spring Integration cho phép cấu hình các tác vụ này bằng biểu thức SpEL (Spring Expression Language), thay vì phải viết một lớp POJO riêng cho từng thao tác nhỏ.

Một **expression adapter** trong ngữ cảnh bài học này là endpoint hoặc message source được cấu hình để đánh giá một biểu thức. Đây là cách khai báo hành vi tích hợp trong flow, không phải một giao thức truyền tải mới. Biểu thức có thể lấy dữ liệu từ message, headers hoặc gọi một bean Spring đã đăng ký. Cách này phù hợp với phép biến đổi và định tuyến ngắn, dễ đọc; nghiệp vụ phức tạp, cần trạng thái hoặc cần kiểm thử độc lập vẫn nên được đặt trong POJO/service chuyên trách.

## 1. SpEL được đánh giá trên message như thế nào?

Một Spring message có hai phần chính:

- **Payload:** dữ liệu nghiệp vụ, chẳng hạn chuỗi, DTO, `Map`, byte array hoặc đối tượng được adapter chuyển đổi.
- **Headers:** metadata như ID, timestamp, correlation, content type, tenant hoặc thông tin transport do adapter ánh xạ.

Trong các expression endpoint của Spring Integration, có thể truy cập payload bằng `payload` và headers bằng `headers`. Ví dụ:

| Biểu thức | Ý nghĩa |
|---|---|
| `payload` | Lấy toàn bộ payload |
| `payload.orderId` | Đọc thuộc tính `orderId` của payload |
| `payload['status']` | Đọc key `status` nếu payload là map |
| `headers['tenantId']` | Đọc header `tenantId` |
| `headers['correlationId']` | Đọc correlation ID |
| `payload.amount > 1000` | So sánh giá trị nghiệp vụ |
| `@orderService.find(payload.orderId)` | Gọi method của bean `orderService` |

Biểu thức được phân tích và đánh giá trong Spring Expression Language evaluation context do Spring Integration cung cấp. Context đó cho phép truy cập message, một số biến và bean theo cấu hình của ứng dụng. Một số cú pháp SpEL thường dùng:

```text
payload.status == 'READY'
payload.amount >= 1000 and headers['trusted'] == true
headers['region'] ?: 'default'
payload.customer?.email
payload.type matches 'ORDER|RETURN'
```

Toán tử `?:` cung cấp giá trị mặc định khi biểu thức bên trái không có giá trị phù hợp; `?.` truy cập an toàn khi đối tượng có thể là `null`. Có thể dùng toán tử so sánh, logic, toán học, truy cập thuộc tính, index của map và gọi method. Tùy endpoint và evaluation context, biểu thức cũng có thể tham chiếu bean bằng cú pháp `@beanName` hoặc kiểu Java bằng `T(...)`.

Hãy xác định rõ kiểu payload trước khi viết expression. `payload.orderId` chỉ phù hợp khi payload có thuộc tính đó; nếu payload thực tế là chuỗi JSON chưa được deserialize, biểu thức này không tự biến chuỗi thành DTO. Hãy dùng converter hoặc transformer để tạo kiểu dữ liệu đúng trước, rồi mới truy cập thuộc tính.

## 2. Các vai trò expression endpoint

Một expression có ý nghĩa khác nhau tùy endpoint sử dụng nó:

| Endpoint | Giá trị expression được dùng để làm gì? | Ví dụ |
|---|---|---|
| Inbound channel adapter dùng expression | Tạo payload cho message được phát theo lịch poll | `@inventoryService.loadSnapshot()` |
| Transformer | Tạo payload mới từ message hiện tại | `payload.trim().toUpperCase()` |
| Filter | Quyết định message có được chuyển tiếp hay bị loại | `payload.active == true` |
| Router | Chọn đích dựa trên kết quả expression | `headers['region']` |
| Service activator | Gọi bean hoặc đánh giá logic xử lý và có thể tạo reply | `@orderService.process(payload)` |
| Header enricher | Tạo hoặc bổ sung header | `'partner-api'` |

Với transformer, kết quả expression trở thành payload tiếp theo. Với filter, kết quả phải biểu diễn điều kiện đúng/sai. Với router, kết quả được dùng làm routing key để chọn channel. Với service activator, kết quả có thể trở thành reply nếu endpoint có output channel. Với header enricher, expression được đánh giá cho giá trị header tương ứng.

### Ví dụ: tạo message từ một inbound expression

Một nguồn dữ liệu nội bộ có thể được đọc định kỳ bằng inbound channel adapter. Biểu thức gọi bean để lấy snapshot, còn poller quyết định thời điểm gọi:

```xml
<int:inbound-channel-adapter id="inventorySnapshotSource"
        channel="inventorySnapshotChannel"
        expression="@inventoryService.loadSnapshot()">
    <int:poller fixed-delay="10000" />
</int:inbound-channel-adapter>
```

Trong ví dụ, `inventoryService` là bean do ứng dụng đăng ký. Mỗi lần poll thành công, expression được đánh giá để lấy payload cho message gửi vào `inventorySnapshotChannel`. Nếu method truy vấn dữ liệu ngoài hoặc có side effect, cần cân nhắc timeout, lỗi, retry và tính idempotent. Poller có thể gọi lại sau lỗi hoặc ở lần poll tiếp theo; expression không tự bảo đảm mỗi lần chỉ chạy một lần.

## 3. Transformer, filter và router bằng SpEL

Giả sử inbound HTTP adapter đã nhận JSON và một converter đã chuyển nội dung thành DTO hoặc map. Flow cần chuẩn hóa mã đơn hàng, chỉ cho phép message hợp lệ, rồi định tuyến theo khu vực.

Có thể khai báo các endpoint bằng XML namespace:

```xml
<int:channel id="rawOrders" />
<int:channel id="normalizedOrders" />
<int:channel id="acceptedOrders" />
<int:channel id="rejectedOrders" />
<int:channel id="northOrders" />
<int:channel id="southOrders" />

<int:transformer input-channel="rawOrders"
        output-channel="normalizedOrders"
        expression="payload.orderCode.trim().toUpperCase()" />

<int:filter input-channel="normalizedOrders"
        output-channel="acceptedOrders"
        discard-channel="rejectedOrders"
        expression="payload matches 'ORDER-[0-9]+'" />

<int:router input-channel="acceptedOrders"
        expression="headers['region']">
    <int:mapping value="north" channel="northOrders" />
    <int:mapping value="south" channel="southOrders" />
</int:router>
```

Đây là minh họa về cách các expression endpoint nối tiếp nhau; trong ứng dụng thực tế, hãy bảo đảm transformer trả về đúng kiểu mà filter và router mong đợi. Nếu cần giữ cả DTO thay vì chỉ giữ chuỗi `orderCode`, hãy dùng một biểu thức hoặc transformer trả về đối tượng mới chứa trường đã chuẩn hóa.

Filter có hai kết quả cần phân biệt. Khi expression đánh giá thành `false`, message bị loại khỏi luồng chính và có thể được gửi tới `discard-channel`. Khi expression ném exception do payload sai kiểu, thuộc tính không tồn tại hoặc method thất bại, đó là lỗi xử lý; nó đi theo cơ chế error flow của endpoint. Không nên coi exception là một kết quả filter `false`.

Router dùng giá trị expression để tìm mapping. Nếu giá trị không khớp mapping nào, hãy quyết định rõ hành vi: cấu hình default output channel, xử lý route không xác định hoặc báo lỗi khi route là bắt buộc. Không để message không hợp lệ quay về channel đầu vào để thử lại vô hạn.

### Cùng ý tưởng trong Java DSL

Java DSL cho phép viết expression trực tiếp ở những endpoint có overload nhận chuỗi SpEL:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.integration.dsl.IntegrationFlow;

@Bean
IntegrationFlow orderValidationFlow() {
    return IntegrationFlow.from("rawOrders")
            .transform("payload.orderCode.trim().toUpperCase()")
            .filter("payload matches 'ORDER-[0-9]+'").channel("acceptedOrders")
            .get();
}
```

Ví dụ trên tập trung vào cú pháp expression trong flow. Với dự án đang dùng phiên bản Spring Integration khác nhau, hãy kiểm tra overload của DSL tương ứng với phiên bản dependency; nếu endpoint hoặc overload không hỗ trợ expression string, có thể cấu hình endpoint bằng XML hoặc dùng lambda/POJO theo API của phiên bản đó.

## 4. Gọi bean và làm giàu header

Expression có thể gọi bean Spring khi cần tái sử dụng một thao tác đã được đóng gói trong service. Ví dụ service activator dùng expression để chuyển message tới bean xử lý:

```xml
<int:service-activator input-channel="acceptedOrders"
        output-channel="processedOrders"
        expression="@orderService.process(payload, headers['tenantId'])" />
```

`orderService` phải là bean hợp lệ và method `process` phải nhận được kiểu payload cùng giá trị tenant thực tế. Nếu method trả về một đối tượng, kết quả có thể trở thành reply gửi tới `processedOrders`. Nếu method trả về `void` hoặc không có kết quả, hành vi output của endpoint sẽ phụ thuộc cấu hình channel và kiểu handler; hãy thiết kế request-reply rõ ràng.

Header enricher dùng expression để thêm metadata vào message. Ví dụ:

```xml
<int:header-enricher input-channel="processedOrders"
        output-channel="outboundOrders">
    <int:header name="sourceSystem" expression="'order-service'" />
    <int:header name="tenantRegion" expression="headers['region'] ?: 'unknown'" />
</int:header-enricher>
```

Message headers là metadata bất biến theo mô hình message của Spring; header enricher tạo message tiếp theo có headers được bổ sung hoặc cập nhật theo cấu hình. Khi message rời ứng dụng qua HTTP, JMS, AMQP, Kafka, file hoặc SFTP adapter, không giả định mọi header nội bộ đều tự động được truyền sang hệ thống ngoài. Hãy kiểm tra header mapper và ánh xạ rõ các trường thuộc hợp đồng transport. Nếu metadata là một phần bắt buộc của hợp đồng liên hệ thống, có thể đặt nó trong event envelope thay vì chỉ giữ ở header nội bộ.

## 5. Dùng expression trong luồng adapter ngoài

Expression endpoint thường nằm giữa inbound adapter và outbound adapter. Chẳng hạn một đối tác gửi HTTP webhook, ứng dụng chuẩn hóa payload, xác định tenant và gửi sang channel để outbound Kafka adapter phát event:

```text
HTTP inbound adapter
        |
        v
  rawPartnerEvents
        |
        v
  expression transformer
        |
        v
  expression filter
        |
        v
  expression router
        |
        +------> tenantAEvents ------> Kafka outbound adapter
        |
        +------> tenantBEvents ------> Kafka outbound adapter
```

Expression có thể đọc metadata được adapter ánh xạ, nhưng tên header và kiểu dữ liệu phụ thuộc transport. Ví dụ HTTP có thể mang header request; Kafka có record key, topic và partition metadata; file/SFTP có tên file và đường dẫn; JMS/AMQP có thuộc tính message riêng. Hãy xem header mapper và hợp đồng adapter đang dùng để biết trường nào thực sự hiện diện. Không suy ra header chỉ từ tên protocol.

Một số điểm áp dụng theo adapter:

- **HTTP:** dùng expression để chuẩn hóa trường trong payload hoặc chọn route dựa trên header đã được ánh xạ. Xác thực chữ ký, quyền truy cập và cấu trúc request trước khi gọi service nghiệp vụ.
- **Kafka, JMS và AMQP:** có thể định tuyến theo event type, tenant hoặc header đã ánh xạ. Giữ event ID và correlation ID theo hợp đồng; expression không thay thế idempotency khi broker redelivery.
- **File và SFTP:** có thể dựa vào metadata tên file hoặc thư mục để phân loại message. Kiểm tra trường metadata thực tế do adapter tạo; không ghép đường dẫn đích từ dữ liệu không đáng tin cậy.
- **Database:** expression có thể chọn nhánh theo giá trị đã đọc hoặc chuẩn hóa dữ liệu. Truy vấn, transaction và cập nhật nhiều bước nên đặt trong repository/service để kiểm soát hiệu năng và tính nhất quán.

Expression trong một endpoint adapter cụ thể cũng có thể được dùng để tính một thuộc tính cấu hình, chẳng hạn tên file hoặc remote directory. Các thuộc tính được hỗ trợ phụ thuộc loại adapter và phiên bản Spring Integration; hãy tra cứu thuộc tính expression của đúng adapter thay vì giả định mọi outbound adapter đều có chung một thuộc tính `expression`.

## 6. Chọn expression hay POJO?

Expression có lợi thế khi quy tắc ngắn, khai báo được và dễ hiểu ngay tại endpoint. Ví dụ đọc `headers['region']`, so sánh `payload.status`, chuẩn hóa một chuỗi hoặc gọi một method service đã có. Khi biểu thức dài, lồng nhiều điều kiện, cần vòng lặp, cần nhiều bước truy cập dữ liệu hoặc có nhiều nhánh lỗi, hãy chuyển logic vào POJO/service.

| Dùng expression khi… | Dùng POJO/service khi… |
|---|---|
| Điều kiện hoặc phép biến đổi ngắn, rõ ràng | Quy tắc nghiệp vụ nhiều bước hoặc khó đọc trong một dòng |
| Cần lấy một trường payload/header | Cần validate nhiều trường và trả về lỗi theo từng trường |
| Cần chọn channel theo một giá trị | Cần điều phối nhiều hệ thống hoặc nhiều thao tác có thứ tự |
| Gọi một method bean đã có | Cần transaction, quản lý trạng thái hoặc xử lý retry chuyên biệt |
| Muốn cấu hình flow ngắn gọn | Cần unit test chi tiết và tái sử dụng logic ngoài IntegrationFlow |

Một nguyên tắc hữu ích là giữ expression có tính khai báo và dễ dự đoán. Hạn chế gọi method gây side effect trong transformer, filter hoặc router. Router có thể được đánh giá lại khi message được xử lý lại; filter có thể chạy nhiều lần nếu retry. Nếu expression gọi một method ghi dữ liệu hoặc gửi request ra ngoài, phải bảo đảm thao tác đó idempotent và có cơ chế lỗi phù hợp.

## 7. Xử lý lỗi và bảo vệ expression

Expression được đánh giá trong lúc endpoint xử lý message. Những lỗi phổ biến gồm payload `null`, sai kiểu, thiếu key, method bean ném exception, giá trị không thể chuyển đổi hoặc router không tìm được đích. Hãy xử lý chúng như lỗi tích hợp có thể quan sát và truy vết.

- Validate payload và hợp đồng message trước khi truy cập thuộc tính sâu trong expression.
- Dùng safe navigation `?.` và giá trị mặc định khi trường có thể vắng mặt; không dùng giá trị mặc định để che giấu dữ liệu bắt buộc bị thiếu.
- Phân biệt message bị filter loại có chủ đích với exception khi đánh giá expression.
- Cấu hình error channel, retry có giới hạn và dead-letter/quarantine channel cho lỗi phù hợp. Tránh route message lỗi trở lại cùng endpoint mà không có điều kiện dừng.
- Ghi nhận endpoint, message ID, correlation ID và loại lỗi. Tránh ghi toàn bộ payload nhạy cảm vào log.

Biểu thức SpEL nên được xem là cấu hình có quyền thực thi trong ứng dụng. Không nhận nguyên văn một expression từ HTTP request, file đối tác, Kafka message hoặc người dùng rồi đánh giá trực tiếp. Tùy evaluation context, SpEL có thể truy cập bean, gọi method hoặc tham chiếu kiểu Java; expression không tin cậy có thể mở ra hành vi ngoài ý muốn. Hãy đặt expression trong cấu hình do đội phát triển kiểm soát, giới hạn bean được phép gọi, và truyền dữ liệu ngoài vào như giá trị payload/header thay vì ghép chúng thành mã expression.

## 8. Kiểm thử và quan sát

Khi kiểm thử expression endpoint, hãy kiểm tra cả giá trị bình thường và dữ liệu biên:

1. Payload đúng kiểu, có đủ thuộc tính và header cần thiết: transformer trả đúng payload; filter chấp nhận; router chọn đúng channel.
2. Payload thiếu trường hoặc có giá trị `null`: xác nhận safe navigation/default hoạt động đúng hoặc validation từ chối message theo hợp đồng.
3. Payload sai kiểu: xác nhận exception được đưa vào error flow và không bị hiểu nhầm là filter trả `false`.
4. Header không được transport mapper chuyển tiếp: xác nhận ứng dụng dùng nhánh thiếu metadata hoặc báo lỗi rõ ràng.
5. Router nhận giá trị không có mapping: xác nhận default route hoặc lỗi theo chính sách đã định.
6. Bean được gọi từ expression phát sinh lỗi: xác nhận retry có giới hạn, log có correlation ID và message cuối cùng được xử lý qua error channel phù hợp.
7. Gửi lại cùng message: xác nhận các thao tác nghiệp vụ được bảo vệ idempotency nếu flow có retry hoặc broker redelivery.

Có thể dùng Spring Integration test support, `MockIntegration`, test channel hoặc adapter giả lập để kiểm tra flow mà không cần kết nối hệ thống ngoài thật. Với expression quan trọng, kiểm thử riêng biểu thức cùng các kiểu payload/header đại diện, sau đó kiểm thử tích hợp toàn flow để xác nhận định tuyến và error channel.

### Bài tập thực hành

Một HTTP inbound adapter nhận message từ đối tác. Payload sau deserialize có các trường `orderCode`, `amount`, `status`; header `tenantId` có thể vắng mặt. Hãy xây dựng flow dùng expression để:

1. Chuẩn hóa `orderCode` thành chữ hoa và bỏ khoảng trắng.
2. Chỉ nhận message có `status == 'READY'` và `amount > 0`; chuyển message bị filter loại sang channel `rejectedOrders`.
3. Định tuyến message theo `headers['tenantId']`, có nhánh xử lý rõ ràng khi tenant không được cung cấp hoặc không có mapping.
4. Gọi `orderService` để lưu đơn hàng sau khi message đã qua kiểm tra.
5. Kiểm thử payload thiếu trường, header thiếu, bean ném exception và message được gửi lại.

**Tiêu chí hoàn thành:** expression đọc đúng payload và headers theo hợp đồng; transformer, filter và router có hành vi phân biệt rõ; lỗi đánh giá đi vào error flow; message không hợp lệ có đường xử lý kết thúc; logic phức tạp được đặt trong POJO/service; không đánh giá expression do hệ thống ngoài cung cấp.
