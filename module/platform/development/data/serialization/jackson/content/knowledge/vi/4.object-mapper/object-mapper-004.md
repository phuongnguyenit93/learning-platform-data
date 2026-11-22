# Phân biệt cấu hình toàn cục và cấu hình theo một lần đọc ghi

`ObjectMapper` thường được dùng như thành phần dùng chung để đọc và ghi JSON trong một ứng dụng Java. Tuy nhiên, không phải lần đọc hoặc ghi nào cũng cần đúng một bộ quy tắc. Có lúc toàn ứng dụng cần dùng chung naming strategy, module ngày giờ hoặc quy tắc ánh xạ mặc định; có lúc chỉ một luồng nhập dữ liệu cần kiểm tra nghiêm ngặt hơn, một lần xuất dữ liệu cần pretty print, hoặc một lần đọc cần áp dụng JSON View riêng.

Jackson cung cấp hai phạm vi cấu hình chính để giải quyết nhu cầu đó:

- **Cấu hình toàn cục** được đặt trên `ObjectMapper`, định nghĩa hành vi mặc định cho các thao tác đọc/ghi sử dụng mapper đó.
- **Cấu hình theo thao tác** được tạo thông qua `ObjectReader` hoặc `ObjectWriter`, áp dụng một bộ tùy chọn cho một kiểu hoặc một nhóm thao tác cụ thể.

Hiểu rõ hai phạm vi này giúp ứng dụng có cấu hình nhất quán, đồng thời vẫn hỗ trợ những trường hợp cần hành vi khác biệt mà không phải thay đổi mapper dùng chung trong lúc ứng dụng đang chạy.

## 1. Cấu hình toàn cục trên ObjectMapper

`ObjectMapper` là điểm cấu hình trung tâm của Jackson Databind. Mapper giữ các thiết lập dùng làm mặc định khi serialize và deserialize, đồng thời quản lý các thành phần như module, naming strategy và quy tắc nhận diện thuộc tính.

Ví dụ, ứng dụng có thể cấu hình mapper một lần khi khởi tạo:

```java
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;

ObjectMapper mapper = new ObjectMapper();

mapper.registerModule(new JavaTimeModule());
mapper.setPropertyNamingStrategy(PropertyNamingStrategies.SNAKE_CASE);
mapper.disable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);
mapper.enable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS);
```

Các thiết lập trên có ý nghĩa ở phạm vi mapper:

- `registerModule(...)` bổ sung hỗ trợ cho kiểu dữ liệu hoặc khả năng ánh xạ.
- `setPropertyNamingStrategy(...)` đặt quy tắc tên property mặc định, ví dụ `customerName` thành `customer_name`.
- `disable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES)` cho phép bỏ qua thuộc tính JSON không được mô hình Java nhận diện.
- `enable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS)` chọn cách biểu diễn ngày giờ theo timestamp cho những kiểu được hỗ trợ và chịu ảnh hưởng bởi feature này.

Khi gọi trực tiếp `mapper.readValue(...)` hoặc `mapper.writeValueAsString(...)`, các thao tác sử dụng cấu hình mặc định hiện hành của mapper.

### 1.1. Khi nào nên cấu hình toàn cục?

Đặt cấu hình trên `ObjectMapper` khi quy tắc đó là chính sách chung cho phần lớn hoặc toàn bộ dữ liệu được mapper xử lý. Ví dụ:

- Toàn ứng dụng thống nhất tên thuộc tính JSON theo `snake_case`.
- Các kiểu `LocalDate`, `Instant` cần được xử lý theo một quy tắc chung.
- Một bộ module phải có mặt trong mọi lần đọc/ghi.
- Quy tắc nhận diện getter, field hoặc constructor được thống nhất cho mô hình dữ liệu.
- Các feature mặc định của serialization/deserialization được chuẩn hóa cho ứng dụng.

Cấu hình chung giúp các nơi sử dụng mapper không phải lặp lại cùng một thiết lập. Khi nhiều controller hoặc service dùng chung mapper đã được cấu hình, hành vi mặc định sẽ nhất quán hơn.

## 2. Cấu hình theo từng lần đọc: ObjectReader

`ObjectReader` là đối tượng chuyên dùng để deserialize. Nó có thể giữ kiểu đích và các tùy chọn đọc riêng, dựa trên cấu hình của `ObjectMapper` đã tạo ra nó.

Ví dụ, giả sử mapper toàn cục được cấu hình để bỏ qua các trường JSON không được biết đến:

```java
ObjectMapper mapper = new ObjectMapper();
mapper.disable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);
```

Đây là chính sách dễ tiếp nhận dữ liệu từ các hệ thống có thể bổ sung trường mới. Nhưng một luồng nhập dữ liệu quan trọng có thể cần kiểm tra nghiêm ngặt để phát hiện trường ngoài hợp đồng. Ta có thể tạo reader riêng:

```java
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectReader;

ObjectReader lenientReader = mapper.readerFor(Order.class);

ObjectReader strictReader = mapper.readerFor(Order.class)
        .with(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);
```

Hai reader dùng cùng mapper nền, nhưng có chính sách xử lý thuộc tính không nhận diện khác nhau. `lenientReader` kế thừa mặc định bỏ qua trường lạ; `strictReader` bật lại feature để phát hiện dữ liệu không khớp mô hình.

Ví dụ JSON có thêm trường `campaign`:

```json
{
  "id": "DH-1001",
  "amount": 129.50,
  "paid": true,
  "campaign": "SUMMER"
}
```

Với `Order` không khai báo thuộc tính `campaign`, reader lenient có thể đọc được dữ liệu và bỏ qua trường đó. Reader strict sẽ phát sinh lỗi `UnrecognizedPropertyException` do feature được bật. Điều này hữu ích khi một API cần tương thích với phần mở rộng dữ liệu, còn một luồng khác cần xác thực cấu trúc đầu vào chặt chẽ.

Ngoài feature, `ObjectReader` còn có thể giữ kiểu đích, JSON View, injectable values, root name, schema hoặc các attribute phục vụ ngữ cảnh đọc. Nhờ đó, code gọi đọc dữ liệu không phải thay đổi cấu hình trên mapper dùng chung.

## 3. Cấu hình theo từng lần ghi: ObjectWriter

`ObjectWriter` là đối tượng chuyên dùng để serialize. Nó giữ kiểu dữ liệu hoặc các tùy chọn ghi riêng, dựa trên cấu hình của mapper gốc.

Giả sử mapper mặc định ghi JSON dạng compact. Một nơi cần log hoặc xuất file để con người đọc có thể dùng writer bật pretty print; một nơi khác vẫn dùng writer compact:

```java
import com.fasterxml.jackson.databind.ObjectWriter;
import com.fasterxml.jackson.databind.SerializationFeature;

ObjectWriter compactWriter = mapper.writerFor(Order.class)
        .without(SerializationFeature.INDENT_OUTPUT);

ObjectWriter prettyWriter = mapper.writerFor(Order.class)
        .with(SerializationFeature.INDENT_OUTPUT);
```

Sử dụng hai writer:

```java
String compactJson = compactWriter.writeValueAsString(order);
String readableJson = prettyWriter.writeValueAsString(order);
```

`compactJson` không thêm khoảng trắng và xuống dòng để định dạng; `readableJson` được trình bày nhiều dòng, dễ đọc khi kiểm tra thủ công. Cả hai cùng serialize một object bằng cấu hình mapper nền, chỉ khác feature ghi được đặt trên writer.

`ObjectWriter` cũng hỗ trợ các tùy chọn như JSON View, root name, pretty printer, filter provider, schema và attribute. Đây là cách phù hợp khi cùng một kiểu Java cần được xuất theo nhiều mục đích, chẳng hạn response API, file báo cáo hoặc dữ liệu log.

## 4. ObjectReader và ObjectWriter là cấu hình bất biến

Một đặc điểm quan trọng là `ObjectReader` và `ObjectWriter` có thiết kế bất biến (immutable). Các phương thức như `with(...)`, `without(...)`, `withView(...)` hoặc `withAttribute(...)` trả về một reader/writer đã cấu hình, thay vì sửa đối tượng hiện có.

Ví dụ:

```java
ObjectWriter baseWriter = mapper.writerFor(Order.class);

ObjectWriter prettyWriter = baseWriter
        .with(SerializationFeature.INDENT_OUTPUT);

ObjectWriter compactWriter = baseWriter
        .without(SerializationFeature.INDENT_OUTPUT);
```

`baseWriter` vẫn giữ cấu hình ban đầu. Hai writer mới có thể được sử dụng độc lập. Vì reader/writer bất biến và an toàn cho nhiều thread sử dụng, ứng dụng có thể tạo trước rồi tái sử dụng các biến thể cấu hình thường gặp.

Điều này đặc biệt hữu ích trong ứng dụng web có nhiều request đồng thời. Một request cần chế độ strict không phải bật/tắt feature trên mapper toàn cục, khiến request khác có thể vô tình nhận chính sách mới. Mỗi request hoặc service có thể dùng reader/writer riêng.

## 5. So sánh hai phạm vi cấu hình

| Tiêu chí | Cấu hình toàn cục | Cấu hình theo thao tác |
| --- | --- | --- |
| Điểm cấu hình | `ObjectMapper` | `ObjectReader`, `ObjectWriter` |
| Phạm vi ảnh hưởng | Các thao tác dùng mapper theo mặc định | Reader hoặc writer được tạo ra |
| Mục đích | Chính sách chung của ứng dụng hoặc một nhóm dữ liệu | Ngoại lệ có chủ đích cho một lần đọc/ghi hoặc một luồng xử lý |
| Ví dụ | Đăng ký module, naming strategy, feature mặc định | Strict/lenient reader, pretty/compact writer, JSON View |
| Khả năng tái sử dụng | Mapper được chia sẻ sau khi cấu hình xong | Reader/writer bất biến có thể được tái sử dụng |
| Thay đổi cấu hình | Các lệnh cấu hình thay đổi trạng thái mapper | `with`/`without` tạo biến thể mới |

Một quy tắc hữu ích là đặt những gì thực sự dùng chung ở mapper; đặt lựa chọn phụ thuộc vào mục đích của lần đọc/ghi ở reader hoặc writer.

## 6. Những cấu hình nào phù hợp với mapper, reader hoặc writer?

Không phải mọi cấu hình của Jackson đều có thể chuyển tùy ý sang `ObjectReader` hoặc `ObjectWriter`.

**Thường thuộc cấu hình nền của mapper:**

- Đăng ký module như `JavaTimeModule`.
- Naming strategy mặc định.
- Mix-in annotations.
- Visibility rules để xác định field/getter/creator được nhận diện.
- Subtype registration và các thiết lập định hình cách khám phá mô hình.
- Những quy tắc mặc định dùng chung cho serializer/deserializer.

**Thường có thể đặt trên reader/writer:**

- `DeserializationFeature` trên `ObjectReader`.
- `SerializationFeature` trên `ObjectWriter`.
- Kiểu đích, JSON View và root name.
- Attribute, injectable values hoặc schema phù hợp với thao tác.
- Pretty printer hoặc filter provider ở chiều ghi.

Ví dụ, nếu toàn ứng dụng cần hiểu `LocalDate`, hãy đăng ký `JavaTimeModule` ở mapper dùng chung. Nếu chỉ một lần ghi cần pretty print, hãy tạo `ObjectWriter` riêng. Nếu chỉ một luồng đọc cần từ chối trường không biết, hãy tạo `ObjectReader` strict.

Khi cần một tập hợp module, naming strategy hoặc mô hình introspection hoàn toàn khác, hãy cân nhắc một `ObjectMapper` riêng được khởi tạo và cấu hình độc lập. Reader/writer không phải cơ chế thay thế mọi cấu hình nền của mapper.

## 7. Thread safety và thời điểm cấu hình

`ObjectMapper` được thiết kế để dùng chung giữa nhiều thread nếu cấu hình của nó đã hoàn tất trước khi bắt đầu các thao tác đọc/ghi. Vì vậy, cách sử dụng thông thường là:

1. Tạo mapper trong giai đoạn khởi tạo ứng dụng.
2. Đăng ký module và đặt naming strategy, feature cùng các quy tắc mặc định.
3. Sau khi mapper bắt đầu phục vụ đọc/ghi, không tiếp tục thay đổi cấu hình dùng chung.
4. Tạo các `ObjectReader` và `ObjectWriter` cho những nhu cầu đọc/ghi khác nhau.
5. Chia sẻ và tái sử dụng reader/writer bất biến khi phù hợp.

Không nên thực hiện kiểu cấu hình sau trong code xử lý request:

```java
// Không nên: thay đổi mapper dùng chung cho một request.
mapper.enable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);
Order order = mapper.readValue(json, Order.class);
mapper.disable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);
```

Nếu mapper được nhiều thread sử dụng, một request có thể thay đổi hành vi mà request khác đang dựa vào. Hơn nữa, thay đổi cấu hình sau khi mapper đã được sử dụng có thể không an toàn do Jackson có cơ chế cache serializer/deserializer.

Hãy thay bằng reader riêng:

```java
ObjectReader strictOrderReader = mapper.readerFor(Order.class)
        .with(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);

Order order = strictOrderReader.readValue(json);
```

Reader mang cấu hình strict riêng mà không làm thay đổi mặc định của mapper dùng chung.

## 8. Tổ chức trong ứng dụng Spring Boot

Trong Spring Boot, `ObjectMapper` thường được cấu hình tập trung và sử dụng bởi HTTP message converter. Các controller không nên tự ý bật/tắt feature trên mapper dùng chung theo từng request.

Nếu một endpoint cần chính sách đọc đặc biệt, có thể thiết kế service hoặc thành phần chuyển đổi chuyên biệt sử dụng `ObjectReader`. Nếu một tác vụ xuất file cần định dạng JSON dễ đọc, hãy sử dụng `ObjectWriter` riêng. Còn module dùng chung, naming strategy và các quy tắc mô hình nên được đặt ở cấu hình mapper trong giai đoạn khởi tạo.

Khi tạo nhiều mapper trong ứng dụng, hãy có lý do rõ ràng cho mỗi mapper, chẳng hạn một mapper cho JSON API và một mapper cho XML tích hợp với hệ thống đối tác. Tránh tạo mapper mới tùy tiện trong từng request vì việc xây dựng cấu hình và cache serializer/deserializer có chi phí.

## 9. Ghi nhớ

- `ObjectMapper` định nghĩa cấu hình mặc định dùng chung; hoàn tất cấu hình trước khi chia sẻ cho các thao tác đồng thời.
- `ObjectReader` dành cho deserialize; có thể đặt feature và ngữ cảnh đọc riêng.
- `ObjectWriter` dành cho serialize; có thể đặt feature và cách trình bày đầu ra riêng.
- Reader/writer bất biến: `with` và `without` tạo biến thể mới, không thay đổi mapper gốc.
- Cấu hình module, naming strategy, mix-in và visibility thường thuộc mapper nền; feature theo lần đọc/ghi phù hợp với reader/writer.
- Không bật/tắt cấu hình trên mapper dùng chung trong lúc xử lý request. Hãy chọn reader/writer riêng hoặc mapper riêng được khởi tạo trước nếu chính sách nền thực sự khác nhau.

Khi cần thay đổi hành vi của đúng một lần đọc hoặc ghi, hãy bắt đầu bằng câu hỏi: thiết lập này có được `ObjectReader` hoặc `ObjectWriter` hỗ trợ không? Nếu có, dùng biến thể bất biến để giới hạn phạm vi ảnh hưởng. Nếu thay đổi cấu trúc ánh xạ nền như module hay naming strategy, hãy cấu hình mapper riêng từ đầu và chia sẻ nó sau khi cấu hình hoàn tất.
