# Thêm trường, đổi tên trường và xử lý giá trị mặc định

Thông điệp sự kiện thường tồn tại lâu hơn một phiên bản ứng dụng. Producer có thể đã phát hàng triệu sự kiện theo cấu trúc cũ trong khi consumer mới đang được triển khai. Một số consumer khác vẫn chạy phiên bản cũ, hoặc một tác vụ phát lại đọc lại dữ liệu được lưu từ nhiều tháng trước. Vì vậy, thay đổi schema phải tính đến cả dữ liệu mới lẫn dữ liệu đã phát.

Trong Spring Cloud Stream, function thường nhận payload đã được chuyển đổi thành DTO, String hoặc byte[]. Binder vận chuyển thông điệp qua Kafka, RabbitMQ hoặc Pulsar; binder không tự làm cho mọi thay đổi schema trở nên tương thích. Producer và consumer cần một hợp đồng chung về tên trường, kiểu dữ liệu, ý nghĩa, giá trị mặc định và phiên bản schema.

Bài học này tập trung vào ba thay đổi thường gặp: thêm trường, đổi tên trường và xử lý trường bị thiếu hoặc có giá trị mặc định. Nguyên tắc quan trọng là thay đổi hợp đồng theo từng bước, giữ khả năng đọc dữ liệu cũ trong thời gian chuyển tiếp và kiểm thử bằng payload của nhiều phiên bản.

## 1. Hợp đồng sự kiện và khả năng tương thích

Schema mô tả cấu trúc dữ liệu: tên trường, kiểu, trường bắt buộc, trường tùy chọn, enum, cấu trúc lồng nhau và đôi khi cả quy tắc mặc định. Hợp đồng sự kiện còn rộng hơn schema. Nó phải mô tả ý nghĩa nghiệp vụ, đơn vị đo, múi giờ, quy tắc null, quyền sở hữu trường và hành vi khi consumer gặp giá trị chưa biết.

Ví dụ sự kiện tạo đơn hàng:

~~~json
{
  "eventId": "evt-1001",
  "eventType": "OrderCreated",
  "schemaVersion": 1,
  "orderId": "ORD-1001",
  "customerId": "CUS-42",
  "total": 125000,
  "currency": "VND"
}
~~~

Một phiên bản sau có thể bổ sung trường **channel** để biết đơn hàng được tạo từ web, ứng dụng di động hay cửa hàng:

~~~json
{
  "eventId": "evt-1002",
  "eventType": "OrderCreated",
  "schemaVersion": 2,
  "orderId": "ORD-1002",
  "customerId": "CUS-42",
  "total": 125000,
  "currency": "VND",
  "channel": "MOBILE"
}
~~~

Consumer cũ có thể không biết trường **channel**. Consumer mới phải xử lý được sự kiện phiên bản 1 chưa có trường này. Cả hai chiều đều cần được đánh giá.

Hai khái niệm tương thích thường dùng:

| Khả năng | Ý nghĩa | Câu hỏi khi thay đổi |
|---|---|---|
| Backward compatibility | Consumer dùng schema mới có thể đọc dữ liệu được ghi theo schema cũ. | Consumer mới có đọc được sự kiện chưa có trường mới không? |
| Forward compatibility | Consumer dùng schema cũ có thể đọc dữ liệu được ghi theo schema mới. | Consumer cũ có chịu được trường mới hoặc giá trị mới không? |
| Full compatibility | Đáp ứng cả hai chiều. | Có thể triển khai producer và consumer theo thứ tự khác nhau mà vẫn đọc được dữ liệu không? |

Tên các chế độ và phạm vi kiểm tra cụ thể tùy schema registry. Một registry có thể kiểm tra tương thích với phiên bản ngay trước đó hoặc với toàn bộ lịch sử schema. Hãy xác nhận chế độ đang bật thay vì chỉ dựa vào tên chế độ.

## 2. Thêm trường mới một cách tương thích

Thêm một trường tùy chọn thường ít rủi ro hơn xóa trường hoặc thay đổi kiểu dữ liệu. Tuy vậy, trường mới vẫn có thể làm consumer cũ lỗi nếu parser được cấu hình từ chối thuộc tính không biết. Ngược lại, consumer mới có thể lỗi khi đọc sự kiện cũ nếu trường mới được coi là bắt buộc mà không có cách xử lý khi trường vắng mặt.

Trước khi thêm trường, hãy quyết định:

1. Trường có bắt buộc đối với mọi sự kiện mới không?
2. Dữ liệu cũ không có trường này sẽ được diễn giải như thế nào?
3. Giá trị null, chuỗi rỗng, số 0 và trường bị bỏ qua có ý nghĩa khác nhau không?
4. Consumer cũ có bỏ qua trường không biết hay cần nâng cấp trước?
5. Có cần backfill dữ liệu đã lưu hoặc phát lại sự kiện cũ không?

### Thêm trường tùy chọn vào JSON

Giả sử DTO phiên bản mới có thêm **channel**:

~~~java
public record OrderCreated(
        String orderId,
        String customerId,
        BigDecimal total,
        String currency,
        String channel) {
}
~~~

Một sự kiện cũ không có thuộc tính **channel** có thể được ánh xạ với giá trị null, tùy constructor, Jackson configuration và converter đang dùng. Consumer nên xử lý trường hợp đó rõ ràng:

~~~java
@Bean
public Consumer<OrderCreated> orderConsumer(OrderService service) {
    return event -> {
        String channel = event.channel() == null || event.channel().isBlank()
                ? "UNKNOWN"
                : event.channel();

        service.process(event, channel);
    };
}
~~~

Trong ví dụ này, **UNKNOWN** là giá trị thay thế ở tầng ứng dụng. Nó giúp consumer mới tiếp tục đọc sự kiện cũ mà không giả vờ biết chính xác kênh tạo đơn hàng. Nếu nghiệp vụ quy định mọi đơn hàng cũ được coi là **WEB**, hãy dùng giá trị đó và ghi rõ đây là quy tắc chuyển đổi dữ liệu lịch sử.

Không nên dùng kiểu primitive cho trường có thể vắng mặt nếu cần phân biệt giá trị chưa được gửi với giá trị bằng không. Ví dụ, **int quantity** có thể nhận 0 khi thuộc tính bị thiếu trong một số đường chuyển đổi. Dùng **Integer** hoặc kiểu nullable phù hợp cho phép phân biệt null với số 0, rồi xác thực theo nghiệp vụ.

### Quy tắc JSON Schema

Trong JSON Schema, thuộc tính không nằm trong mảng **required** là tùy chọn. Một thuộc tính tùy chọn có thể vắng mặt; điều đó khác với thuộc tính hiện diện nhưng có giá trị null. Nếu cần cho phép null, schema phải khai báo kiểu hoặc union có chứa null theo phiên bản JSON Schema được sử dụng.

Ví dụ minh họa:

~~~json
{
  "type": "object",
  "properties": {
    "orderId": { "type": "string" },
    "customerId": { "type": "string" },
    "channel": {
      "type": ["string", "null"],
      "default": "UNKNOWN"
    }
  },
  "required": ["orderId", "customerId"]
}
~~~

Trong JSON Schema, từ khóa **default** chủ yếu là metadata/annotation mô tả giá trị mặc định. Bản thân validator không bắt buộc phải chèn giá trị đó vào JSON khi trường bị thiếu. Muốn áp dụng mặc định, consumer cần thực hiện trong code hoặc dùng công cụ có hỗ trợ xử lý default và kiểm tra rõ hành vi của công cụ đó.

Điều này rất quan trọng khi một đội nghĩ rằng chỉ thêm **default** vào schema là mọi consumer sẽ tự nhận được giá trị. Schema có thể hợp lệ nhưng payload vẫn không chứa trường đó.

## 3. Đặt giá trị mặc định ở đúng tầng

Giá trị mặc định có thể xuất hiện ở schema, DTO, mapper hoặc logic nghiệp vụ. Các vị trí này không có cùng ngữ nghĩa.

| Vị trí | Tác dụng | Điều cần chú ý |
|---|---|---|
| Schema | Mô tả giá trị mặc định hoặc quy tắc đọc dữ liệu theo định dạng. | Cách áp dụng phụ thuộc định dạng và thư viện. |
| DTO/constructor | Khởi tạo trường khi đối tượng được tạo. | Constructor hoặc deserializer có thể ghi đè giá trị khởi tạo. |
| Mapper | Chuyển dữ liệu phiên bản cũ sang mô hình nội bộ hiện tại. | Tốt để tập trung quy tắc chuyển đổi. |
| Domain service | Áp dụng quy tắc nghiệp vụ khi dữ liệu thiếu. | Phải phân biệt thiếu dữ liệu với dữ liệu sai. |

Không nên gán mặc định tùy tiện trong producer chỉ để schema mới luôn đầy đủ. Nếu producer không biết giá trị thật, gửi **UNKNOWN** có thể chính xác hơn gửi **WEB** hoặc **0**. Giá trị mặc định phải phản ánh ý nghĩa nghiệp vụ, không chỉ làm cho quá trình deserialize thành công.

### Phân biệt absent, null, empty và zero

Với JSON, các trạng thái sau có thể mang ý nghĩa khác nhau:

~~~json
{}
~~~

~~~json
{"channel": null}
~~~

~~~json
{"channel": ""}
~~~

~~~json
{"channel": "WEB"}
~~~

Trường hợp đầu tiên là thuộc tính không xuất hiện. Trường hợp thứ hai là thuộc tính có mặt với giá trị null. Trường hợp thứ ba là chuỗi rỗng. Trường hợp cuối cùng có một giá trị cụ thể. Nếu nghiệp vụ cần phân biệt các trường hợp này, đừng gom chúng vào một nhánh fallback duy nhất.

Ví dụ mapper có thể thể hiện rõ quy tắc:

~~~java
static String resolveChannel(OrderCreated event) {
    if (event.channel() == null) {
        return "UNKNOWN";
    }
    if (event.channel().isBlank()) {
        throw new IllegalArgumentException("channel không được để trống");
    }
    return event.channel();
}
~~~

Trong ví dụ, thiếu trường được chấp nhận và ánh xạ thành **UNKNOWN**, còn chuỗi rỗng bị xem là dữ liệu không hợp lệ. Chỉ chọn cách này nếu đó là hợp đồng nghiệp vụ đã thống nhất.

## 4. Thêm trường với Avro

Avro hỗ trợ schema resolution giữa writer schema và reader schema. Khi consumer đọc một bản ghi được ghi theo schema cũ bằng reader schema mới, reader schema có thể cung cấp giá trị mặc định cho trường mới mà writer schema không có.

Ví dụ writer schema phiên bản 1:

~~~json
{
  "type": "record",
  "name": "OrderCreated",
  "fields": [
    { "name": "orderId", "type": "string" },
    { "name": "customerId", "type": "string" },
    { "name": "total", "type": "double" }
  ]
}
~~~

Reader schema phiên bản 2 bổ sung **channel** với default:

~~~json
{
  "type": "record",
  "name": "OrderCreated",
  "fields": [
    { "name": "orderId", "type": "string" },
    { "name": "customerId", "type": "string" },
    { "name": "total", "type": "double" },
    {
      "name": "channel",
      "type": ["null", "string"],
      "default": null
    }
  ]
}
~~~

Khi reader schema phiên bản 2 đọc bản ghi được ghi bằng writer schema phiên bản 1, Avro có thể cung cấp **null** cho trường **channel** theo default đã khai báo. Nếu trường mới không có default phù hợp, schema resolution có thể thất bại khi đọc dữ liệu cũ.

Lưu ý: với union của Avro, giá trị default phải phù hợp với nhánh đầu tiên của union theo quy tắc Avro. Vì vậy, ví dụ đặt **null** ở vị trí đầu tiên của union và default là null. Không áp dụng quy tắc default của Avro cho JSON Schema hoặc Protobuf vì mỗi định dạng có semantics riêng.

Spring Cloud Stream có thể tích hợp schema registry và Avro tùy phiên bản, dependency và cấu hình ứng dụng. Nếu dùng registry, cần xác minh writer schema được đăng ký, cách producer gửi schema ID và cách consumer lấy schema khi đọc. Binder vận chuyển payload; schema registry và Avro serializer/deserializer mới chịu trách nhiệm về schema resolution.

## 5. Đổi tên trường là một thay đổi hợp đồng

Đổi tên trường có vẻ chỉ là thay đổi thẩm mỹ trong code, nhưng với dữ liệu đã phát thì đó là thay đổi cấu trúc. Producer mới có thể gửi **buyerId** trong khi consumer cũ vẫn tìm **customerId**. Nếu trường cũ biến mất ngay lập tức, consumer cũ có thể nhận null, giá trị mặc định hoặc lỗi parse.

Không nên triển khai đổi tên theo kiểu thay tên trong một commit rồi phát hành đồng thời mọi producer và consumer. Hãy dùng quy trình chuyển tiếp:

1. Mở rộng schema để chấp nhận cả tên cũ và tên mới.
2. Triển khai consumer có thể đọc cả hai tên.
3. Triển khai producer ghi trường mới; trong thời gian tương thích có thể tiếp tục ghi trường cũ.
4. Theo dõi tỷ lệ consumer và producer đã chuyển đổi, cũng như dữ liệu cũ còn trong retention.
5. Chỉ ngừng trường cũ sau khi mọi consumer liên quan đã nâng cấp và dữ liệu cần phát lại không còn phụ thuộc trường cũ.
6. Xóa trường cũ trong một thay đổi schema tiếp theo, nếu registry và chính sách tương thích cho phép.

### Ví dụ chuyển tiếp với JSON và Jackson

Trong giai đoạn chuyển tiếp, DTO có thể nhận cả hai tên:

~~~java
public class CustomerReference {

    private String buyerId;
    private String customerId;

    public void setBuyerId(String buyerId) {
        this.buyerId = buyerId;
    }

    public void setCustomerId(String customerId) {
        this.customerId = customerId;
    }

    public String effectiveBuyerId() {
        if (buyerId != null && !buyerId.isBlank()
                && customerId != null && !customerId.isBlank()
                && !buyerId.equals(customerId)) {
            throw new IllegalArgumentException(
                    "buyerId và customerId không khớp");
        }
        if (buyerId != null && !buyerId.isBlank()) {
            return buyerId;
        }
        return customerId;
    }
}
~~~

Trong ví dụ này, hai setter tách tên cũ và mới để consumer có thể phát hiện khi cả hai cùng xuất hiện nhưng mang giá trị khác nhau. Nếu DTO chỉ giữ thuộc tính mới **buyerId**, có thể dùng **@JsonAlias("customerId")** để Jackson chấp nhận tên cũ khi deserialize. Alias không tự động khiến serializer ghi cả hai tên. Nếu producer cần dual-write, hãy tạo payload chuyển tiếp có cả **buyerId** và **customerId** một cách tường minh, hoặc dùng DTO có cả hai thuộc tính và mapper kiểm soát việc phát.

Ví dụ mapper tạo payload chuyển tiếp:

~~~java
Map<String, Object> toTransitionPayload(String buyerId) {
    return Map.of(
            "buyerId", buyerId,
            "customerId", buyerId
    );
}
~~~

Không dual-write vô thời hạn. Hai trường đại diện cùng một thông tin có thể lệch nhau nếu producer cập nhật một trường mà quên trường còn lại. Hãy xác định trường nào là nguồn chuẩn, quy tắc ưu tiên khi cả hai xuất hiện nhưng khác giá trị, và thời điểm kết thúc giai đoạn chuyển tiếp.

## 6. Quy tắc đổi tên trong Avro và Protobuf

Các định dạng schema có cơ chế riêng cho việc đổi tên. Không thể áp dụng cách xử lý của JSON/Jackson cho mọi định dạng.

### Avro aliases

Avro hỗ trợ **aliases** để reader schema có thể nhận diện tên cũ trong một số tình huống schema resolution. Ví dụ reader schema đổi record name hoặc field name nhưng khai báo alias tương ứng:

~~~json
{
  "type": "record",
  "name": "OrderCreated",
  "fields": [
    { "name": "orderId", "type": "string" },
    {
      "name": "buyerId",
      "type": "string",
      "aliases": ["customerId"]
    }
  ]
}
~~~

Alias là thông tin phục vụ schema resolution; nó không có nghĩa producer mới sẽ phát đồng thời cả hai trường. Hãy kiểm tra khả năng hỗ trợ aliases trong serializer, deserializer và schema registry đang dùng. Kiểm thử bằng writer schema cũ và reader schema mới trước khi triển khai.

### Protobuf field number

Trong Protocol Buffers, field number là định danh trên wire. Khi đổi tên field trong file .proto, giữ nguyên field number thường giữ được khả năng đọc binary wire của field đó, nhưng tên trong mã nguồn sinh ra và tên trong JSON mapping có thể thay đổi. Hệ thống phụ thuộc tên JSON hoặc reflection vẫn có thể bị ảnh hưởng.

Ví dụ:

~~~protobuf
message OrderCreated {
  string buyer_id = 2;
}
~~~

Nếu trường trước đây tên **customer_id** và mang số 2, việc đổi tên thành **buyer_id** nhưng giữ số 2 có thể tương thích ở binary wire. Tuy nhiên, không được tái sử dụng số 2 cho một trường khác. Khi xóa field, hãy đánh dấu số và tên đã dùng là reserved:

~~~protobuf
message OrderCreated {
  reserved 2;
  reserved "customer_id", "buyer_id";
  string order_id = 1;
}
~~~

Đoạn minh họa reserved dùng khi field số 2 đã bị xóa sau giai đoạn đổi tên; cả tên cũ và tên mới đều được giữ lại trong danh sách reserved để tránh tái sử dụng. Trong schema thực tế cần giữ đúng các field còn lại và không khai báo lại số hoặc tên đã reserve. Không tái sử dụng field number đã phát hành, kể cả khi trường cũ không còn xuất hiện trong code.

Với Protobuf proto3, scalar field có thể trả về giá trị mặc định như 0, false hoặc chuỗi rỗng khi không có mặt. Nếu cần phân biệt rõ trường vắng mặt với giá trị mặc định, dùng cơ chế presence phù hợp, chẳng hạn **optional** hoặc message wrapper tùy phiên bản và ngôn ngữ. Đừng diễn giải 0 là giá trị người dùng đã gửi nếu schema không bảo đảm presence.

## 7. Thay đổi kiểu dữ liệu và ý nghĩa trường

Thay đổi tên không phải rủi ro duy nhất. Thay kiểu có thể làm consumer không deserialize được hoặc làm thay đổi ý nghĩa giá trị.

| Thay đổi | Rủi ro | Hướng xử lý |
|---|---|---|
| Thêm trường tùy chọn | Consumer mới gặp dữ liệu cũ không có trường. | Cung cấp fallback rõ ràng và kiểm thử schema cũ. |
| Thêm trường bắt buộc | Dữ liệu cũ không có trường. | Tránh nếu cần đọc lịch sử; cân nhắc version mới hoặc migration. |
| Đổi String thành số | Payload cũ có thể chứa chuỗi không parse được. | Thêm trường mới, chuyển đổi có kiểm soát và giữ trường cũ trong giai đoạn chuyển tiếp. |
| Đổi đơn vị từ đồng sang nghìn đồng | Cùng kiểu nhưng khác ý nghĩa. | Tạo trường mới hoặc event version mới; không đổi nghĩa âm thầm. |
| Xóa trường | Consumer cũ và replay có thể vẫn cần trường đó. | Ngừng sử dụng trước, theo dõi rồi mới xóa sau cửa sổ tương thích. |
| Thêm giá trị enum | Consumer cũ có thể từ chối giá trị chưa biết. | Thiết kế consumer có nhánh unknown/other và kiểm thử giá trị mới. |
| Đổi null thành chuỗi rỗng | Có thể làm mất thông tin về trạng thái chưa xác định. | Chốt semantics và chuyển đổi dữ liệu có chủ đích. |

Nếu một trường thay đổi ý nghĩa nghiệp vụ, nên xem đó là thay đổi hợp đồng dù tên và kiểu không đổi. Ví dụ **total** trước đây là tổng trước thuế nhưng sau đó được hiểu là tổng sau thuế. Consumer cũ vẫn parse thành công nhưng tính toán sai. Hãy tạo trường mới như **totalBeforeTax** và **totalAfterTax**, hoặc phát một event type/version mới nếu thay đổi làm hợp đồng cũ không còn đúng.

## 8. Triển khai theo chiến lược expand, migrate, contract

Một quy trình an toàn cho thay đổi schema thường có ba giai đoạn:

### Expand — mở rộng

- Thêm trường mới theo cách tùy chọn hoặc có default phù hợp với định dạng.
- Nâng cấp consumer để đọc cả payload cũ lẫn payload mới.
- Kiểm thử producer mới với consumer cũ và consumer mới với payload cũ.

### Migrate — chuyển đổi

- Triển khai producer bắt đầu ghi trường mới.
- Nếu cần, dual-write trường cũ và trường mới trong khoảng thời gian đã xác định.
- Backfill dữ liệu lưu trữ hoặc phát lại sự kiện nếu nghiệp vụ yêu cầu.
- Theo dõi lỗi parse, tỷ lệ fallback và consumer chưa nâng cấp.

### Contract — thu hẹp

- Xác nhận mọi consumer còn hoạt động đã chuyển sang trường mới.
- Xác nhận dữ liệu trong retention, DLQ, bản sao lưu và quy trình replay không còn phụ thuộc trường cũ hoặc có mapper tương thích.
- Ngừng phát trường cũ, sau đó mới xóa khỏi schema theo chính sách registry.

Mermaid dưới đây minh họa trình tự triển khai:

~~~mermaid
flowchart LR
    A[Schema cũ] --> B[Expand: thêm trường tùy chọn]
    B --> C[Consumer đọc cũ và mới]
    C --> D[Producer ghi trường mới]
    D --> E[Migrate: backfill và theo dõi]
    E --> F[Ngừng dùng trường cũ]
    F --> G[Contract: xóa trường cũ]
~~~

Không phải thay đổi nào cũng cần dual-write hoặc backfill. Nếu trường mới chỉ bổ sung metadata không bắt buộc và không cần lịch sử, consumer có thể dùng fallback cho sự kiện cũ. Hãy chọn quy trình dựa trên yêu cầu replay, thời gian retention và số lượng consumer thực tế.

## 9. Quản lý schema version và registry

Một schema registry giúp lưu schema theo subject hoặc định danh tương đương, quản lý phiên bản và kiểm tra quy tắc tương thích trước khi producer đăng ký schema mới. Registry giảm nguy cơ producer phát một schema phá vỡ consumer, nhưng không thay thế kiểm thử ứng dụng.

Khi dùng registry:

- Chọn chiến lược đặt subject phù hợp với việc nhiều event type dùng chung topic hay mỗi event type có subject riêng.
- Bật chế độ compatibility đúng với thứ tự triển khai producer và consumer.
- Xác định registry kiểm tra phiên bản liền trước hay toàn bộ lịch sử.
- Quản lý schema ID và quyền truy cập registry như một phần của cấu hình triển khai.
- Không xóa schema cũ khi còn dữ liệu cần replay hoặc consumer cũ còn hoạt động.
- Kiểm tra schema compatibility trong CI trước khi phát hành.

Spring Cloud Stream có hỗ trợ schema registry trong một số thế hệ và cấu hình nhất định; hệ sinh thái Kafka, Pulsar hoặc nền tảng ngoài cũng có thể cung cấp registry riêng. Cách cấu hình subject, serializer, schema ID và dependency thay đổi theo phiên bản. Hãy chọn một cơ chế rõ ràng và xác minh producer/consumer đang dùng cùng quy tắc schema, tránh trộn lẫn serializer không tương thích.

Trường **schemaVersion** trong payload có thể hữu ích cho ứng dụng tự quản lý version, nhưng không thay thế schema ID hoặc cơ chế schema resolution của định dạng. Nếu có schema registry, hãy làm rõ version ứng dụng, version event và version schema có cùng một số hay là ba khái niệm độc lập.

## 10. Kiểm thử thay đổi schema trong Spring Cloud Stream

Kiểm thử chỉ bằng một payload mới không phát hiện được lỗi tương thích với dữ liệu lịch sử. Mỗi thay đổi cần có fixture cho phiên bản cũ và mới, bao gồm trường hợp thiếu, null, giá trị mặc định và giá trị bất thường.

Ví dụ một consumer xử lý sự kiện có trường mới:

~~~java
public record OrderCreated(
        String orderId,
        String customerId,
        BigDecimal total,
        String channel) {
}

@Bean
public Consumer<OrderCreated> orderConsumer(OrderService service) {
    return event -> {
        String channel = event.channel() == null
                ? "UNKNOWN"
                : event.channel();
        service.process(event.orderId(), event.customerId(),
                event.total(), channel);
    };
}
~~~

Các fixture kiểm thử:

~~~json
{
  "orderId": "ORD-OLD",
  "customerId": "CUS-1",
  "total": 100000,
  "currency": "VND"
}
~~~

~~~json
{
  "orderId": "ORD-NEW",
  "customerId": "CUS-1",
  "total": 100000,
  "currency": "VND",
  "channel": "MOBILE"
}
~~~

Consumer cần xử lý được cả hai payload. Trong ví dụ, trường **currency** có trong JSON nhưng không có trong record minh họa; trong dự án thực tế DTO phải khai báo trường đó nếu cần dùng hoặc converter phải được cấu hình để xử lý thuộc tính không biết. Đây là lý do phải kiểm thử với DTO và Jackson configuration thực tế thay vì chỉ kiểm tra JSON bằng mắt.

Ma trận kiểm thử đề xuất:

| Ca kiểm thử | Đầu vào | Kết quả cần xác nhận |
|---|---|---|
| Payload cũ | Không có trường mới. | Consumer mới áp dụng fallback theo hợp đồng. |
| Payload mới | Có trường mới hợp lệ. | Consumer nhận đúng giá trị được gửi. |
| Trường null | Trường hiện diện nhưng null. | Hành vi đúng với quy tắc null đã công bố. |
| Trường rỗng | Chuỗi rỗng hoặc khoảng trắng. | Được chấp nhận hoặc từ chối đúng quy tắc nghiệp vụ. |
| Trường sai kiểu | Chuỗi thay cho số hoặc object thay cho chuỗi. | Lỗi chuyển đổi được ghi nhận và đi theo retry/DLQ phù hợp. |
| Trường không biết | Producer mới thêm thuộc tính khác. | Consumer cũ xử lý theo chính sách unknown field của parser. |
| Đổi tên trường | Chỉ có tên cũ, chỉ có tên mới, hoặc cả hai. | Mapper/alias chọn đúng giá trị; xung đột được phát hiện. |
| Replay | Sự kiện cũ được phát lại sau khi consumer nâng cấp. | Kết quả nghiệp vụ không sai hoặc tạo tác động trùng lặp. |
| Schema registry | Đăng ký schema mới. | Registry chấp nhận hoặc từ chối đúng theo compatibility mode. |

Với Spring Cloud Stream test binder, có thể kiểm thử function và binding trong tiến trình. Với Avro, Protobuf hoặc JSON Schema, hãy bổ sung kiểm thử serializer/deserializer thật và schema resolution. Integration test với Kafka, RabbitMQ hoặc Pulsar xác nhận payload qua broker, nhưng không thay thế kiểm tra tương thích schema ở CI.

## 11. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Consumer mới lỗi khi đọc sự kiện cũ | Trường mới bắt buộc hoặc không có default phù hợp. | Làm trường tùy chọn, bổ sung default theo định dạng hoặc mapper fallback. |
| Consumer cũ lỗi khi producer thêm trường | Parser từ chối thuộc tính không biết hoặc schema registry không cho phép thay đổi. | Kiểm tra chính sách unknown field và compatibility mode; triển khai consumer tương thích trước. |
| Trường mới luôn nhận null | Producer chưa gửi trường, tên không khớp hoặc converter không ánh xạ. | Kiểm tra payload trên wire, DTO và mapper. |
| Giá trị 0 bị hiểu là dữ liệu đã cung cấp | Dùng primitive hoặc định dạng không có presence rõ ràng. | Dùng wrapper/optional/presence phù hợp và định nghĩa semantics. |
| Đổi tên làm mất dữ liệu | Chỉ đổi tên ở producer hoặc consumer mà không có giai đoạn chuyển tiếp. | Dùng alias hoặc dual-read/dual-write có thời hạn. |
| Hai trường cũ và mới khác nhau | Producer ghi hai trường bằng logic riêng hoặc không có trường chuẩn. | Chọn nguồn chuẩn, xác định ưu tiên và cảnh báo xung đột. |
| Registry từ chối schema mới | Schema không đáp ứng chế độ compatibility hoặc so sánh với lịch sử. | Xem diff schema và điều chỉnh quy trình thay đổi. |
| Replay sự kiện lỗi sau khi xóa trường cũ | Dữ liệu cũ vẫn tồn tại trong retention, backup hoặc DLQ. | Giữ mapper tương thích hoặc đợi hết cửa sổ replay trước khi contract. |

Khi xử lý lỗi, hãy lấy một payload thực tế từ producer, xác định writer schema hoặc version của nó, rồi chạy đúng consumer version đang lỗi. Đừng chỉ nhìn DTO mới và kết luận payload cũ phải được chuyển đổi tự động.

## 12. Checklist trước khi phát hành schema mới

- [ ] Đã ghi rõ trường được thêm, đổi tên, xóa hoặc đổi kiểu và lý do nghiệp vụ.
- [ ] Đã xác định absent, null, empty và zero có ý nghĩa gì.
- [ ] Trường mới có cách xử lý cho dữ liệu cũ.
- [ ] Consumer mới đọc được payload cũ và payload mới.
- [ ] Consumer cũ được kiểm tra với payload mới, nếu cần duy trì forward compatibility.
- [ ] Quy tắc default phù hợp với định dạng JSON Schema, Avro hoặc Protobuf đang dùng.
- [ ] Đổi tên trường có kế hoạch alias hoặc dual-read/dual-write và thời điểm kết thúc.
- [ ] Field number của Protobuf không bị tái sử dụng; field đã xóa được reserve.
- [ ] Schema registry đã kiểm tra compatibility theo đúng phạm vi lịch sử.
- [ ] Fixture cũ/mới, null, thiếu trường, sai kiểu và replay đã được kiểm thử.
- [ ] Dữ liệu trong retention, DLQ và backup đã được tính đến trước khi xóa trường cũ.
- [ ] Consumer có metric hoặc log cho fallback, schema parse error và giá trị không được hỗ trợ.

Thêm trường, đổi tên trường và đặt giá trị mặc định đều là thay đổi hợp đồng giữa các dịch vụ. Hãy xác định ý nghĩa của trường trước khi chọn cú pháp schema, kiểm tra cách định dạng xử lý dữ liệu bị thiếu, rồi triển khai theo từng giai đoạn để producer và consumer có thể cùng tồn tại trong thời gian chuyển tiếp. Với Spring Cloud Stream, việc kiểm thử payload lịch sử qua đúng converter, serializer và binder đang triển khai là điều kiện cần để thay đổi schema an toàn.
