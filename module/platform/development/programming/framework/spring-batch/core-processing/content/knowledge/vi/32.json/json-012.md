# Kiểm thử JSON input và output

Trong Spring Batch, dữ liệu JSON thường được dùng làm nguồn nhập từ API/export hoặc làm định dạng trao đổi với hệ thống khác. Một job có thể đọc một mảng JSON, chuyển từng object thành item Java, xử lý nghiệp vụ rồi ghi kết quả thành một tài liệu JSON mới. Để bảo đảm pipeline hoạt động đúng, cần kiểm thử cả quá trình đọc, ánh xạ, xử lý, ghi và khả năng phục hồi khi chunk hoặc job gặp lỗi.

Kiểm thử JSON input và output không chỉ là kiểm tra file có parse được hay không. Cần xác nhận cấu trúc JSON, kiểu dữ liệu, giá trị null, field lạ/thiếu, thứ tự và số lượng item, nội dung sau processor, định dạng output, encoding, hành vi khi dữ liệu sai và tính đúng đắn khi restart.

Spring Batch cung cấp **JsonItemReader<T>** cùng **JsonObjectReader<T>** để đọc từng object từ JSON resource, và **JsonFileItemWriter<T>** cùng **JsonObjectMarshaller<T>** để ghi item thành JSON. Có thể dùng implementation dựa trên Jackson như **JacksonJsonObjectReader** và **JacksonJsonObjectMarshaller**. Các component này cho phép test mapping JSON riêng, test writer riêng và chạy integration test qua một job thật.

## 1. Phân biệt kiểm thử input và output

Một job JSON có thể có luồng như sau:

~~~mermaid
flowchart LR
    A[JSON input file] --> B[JsonItemReader]
    B --> C[ItemProcessor]
    C --> D[JsonFileItemWriter]
    D --> E[JSON output file]
    E --> F[Parse và assert output]
~~~

Mỗi phần cần các assertion khác nhau:

| Phần | Điều cần kiểm tra |
|---|---|
| Input resource | File đúng, encoding đúng, resource có thể mở |
| JSON parser/object reader | JSON hợp lệ, object được ánh xạ đúng kiểu |
| JsonItemReader | Trả đúng số item, đúng thứ tự và kết thúc bằng null |
| Processor | Quy tắc chuyển đổi, lọc và validation |
| JsonFileItemWriter | Tạo đúng cấu trúc JSON, serialize đúng field và giá trị |
| Job/step | Read/process/write counts, status, exception và transaction |
| Restart | Không mất hoặc nhân đôi item đã commit |
| Consumer contract | Output parse được và phù hợp schema/hợp đồng downstream |

Nên tách unit test cho mapping nhỏ với integration test cho reader/writer và job. Test càng gần boundary cần xác minh thì càng dễ chỉ ra lỗi thuộc parser, processor, writer hay orchestration.

## 2. Định dạng JSON mà JsonItemReader thường xử lý

**JsonItemReader<T>** được thiết kế để đọc một JSON array gồm các object. Ví dụ:

~~~json
[
  {
    "orderId": 1001,
    "customerId": "C001",
    "amount": 250.00
  },
  {
    "orderId": 1002,
    "customerId": "C002",
    "amount": 175.50
  }
]
~~~

Reader đọc từng phần tử object và trả về một item Java cho mỗi object. Mảng ngoài cùng là container của các item. Đây là cấu trúc phù hợp cho chunk-oriented processing.

Một JSON object đơn lẻ:

~~~json
{
  "orderId": 1001,
  "customerId": "C001"
}
~~~

không tương đương với JSON array trong cấu hình reader này. Nếu nguồn là một object wrapper như {"orders": [...]}, cần xử lý wrapper bằng bước chuyển đổi, custom reader/object reader hoặc một định dạng input phù hợp. Không nên giả định JsonItemReader tự tìm array ở mọi vị trí trong object.

## 3. Model Java dùng trong test

Nên dùng DTO có kiểu rõ ràng để test JSON mapping. Ví dụ:

~~~java
public class OrderInput {

    private Long orderId;
    private String customerId;
    private BigDecimal amount;

    public OrderInput() {
    }

    public Long getOrderId() {
        return orderId;
    }

    public void setOrderId(Long orderId) {
        this.orderId = orderId;
    }

    public String getCustomerId() {
        return customerId;
    }

    public void setCustomerId(String customerId) {
        this.customerId = customerId;
    }

    public BigDecimal getAmount() {
        return amount;
    }

    public void setAmount(BigDecimal amount) {
        this.amount = amount;
    }
}
~~~

Trong test, BigDecimal phù hợp hơn double khi cần kiểm tra giá trị tiền vì tránh sai số nhị phân. Model có constructor không tham số và accessor theo convention giúp Jackson binding hoạt động trong cấu hình thông dụng.

Nếu ứng dụng dùng Java record, constructor-based binding hoặc annotation Jackson, hãy test đúng model thực tế thay vì đổi sang POJO chỉ để test dễ hơn. Fixture cần phản ánh hợp đồng JSON mà hệ thống thực sự nhận.

## 4. Cấu hình JsonItemReader

Spring Batch cung cấp builder để tạo JsonItemReader<T>. Với Jackson, có thể dùng JacksonJsonObjectReader<T> làm delegate đọc từng object:

~~~java
@Bean
@StepScope
public JsonItemReader<OrderInput> orderJsonReader(
        @Value("#{jobParameters['inputFile']}") String inputFile) {

    return new JsonItemReaderBuilder<OrderInput>()
            .name("orderJsonReader")
            .resource(new FileSystemResource(inputFile))
            .jsonObjectReader(new JacksonJsonObjectReader<>(OrderInput.class))
            .saveState(true)
            .build();
}
~~~

Các thành phần chính:

- resource(...): nguồn JSON cần đọc.
- name(...): tên ổn định để lưu state reader.
- jsonObjectReader(...): chuyển từng JSON object thành kiểu OrderInput.
- saveState(true): cho phép lưu checkpoint phục vụ restart.

Đối với test unit reader, có thể dùng resource tạm hoặc ByteArrayResource thay cho job parameter. Với job production, StepScope cho phép late-bind input path theo execution.

## 5. Kiểm thử JsonItemReader độc lập

Test reader riêng giúp xác nhận JSON được parse thành item đúng mà không cần khởi chạy toàn bộ job.

Ví dụ với file fixture trên classpath:

~~~java
class OrderJsonReaderTest {

    private JsonItemReader<OrderInput> reader;

    @BeforeEach
    void setUp() {
        reader = new JsonItemReaderBuilder<OrderInput>()
                .name("testOrderJsonReader")
                .resource(new ClassPathResource("json/orders-valid.json"))
                .jsonObjectReader(new JacksonJsonObjectReader<>(OrderInput.class))
                .saveState(true)
                .build();
    }

    @Test
    void readsEachObjectFromArray() throws Exception {
        reader.open(new ExecutionContext());
        try {
            OrderInput first = reader.read();
            OrderInput second = reader.read();

            assertEquals(1001L, first.getOrderId());
            assertEquals("C001", first.getCustomerId());
            assertEquals(new BigDecimal("250.00"), first.getAmount());

            assertEquals(1002L, second.getOrderId());
            assertEquals("C002", second.getCustomerId());
            assertEquals(new BigDecimal("175.50"), second.getAmount());

            assertNull(reader.read());
        } finally {
            reader.close();
        }
    }
}
~~~

Test mở reader bằng ExecutionContext, gọi read() cho đến khi nhận null, rồi đóng reader. Cần dùng try/finally để giải phóng resource ngay cả khi assertion thất bại.

Test này kiểm tra cả số item, thứ tự và mapping từng field. Chỉ assert first != null là chưa đủ để chứng minh JSON được ánh xạ đúng.

## 6. Kiểm tra thứ tự và số lượng item

JSON array có thứ tự. Reader thường trả item theo thứ tự phần tử trong array. Nếu thứ tự đầu vào có ý nghĩa, test cần xác nhận sequence đó được giữ qua reader và các bước xử lý liên quan.

Có thể đọc tất cả item trong test:

~~~java
List<OrderInput> items = new ArrayList<>();
OrderInput item;
while ((item = reader.read()) != null) {
    items.add(item);
}

assertEquals(2, items.size());
assertEquals(
        List.of(1001L, 1002L),
        items.stream().map(OrderInput::getOrderId).toList());
~~~

Với fixture lớn, không nên tạo một danh sách toàn bộ chỉ để test reader nếu mục tiêu là xác minh streaming. Có thể đọc một số item đầu, kiểm tra item cuối hoặc đếm bằng vòng lặp để giảm bộ nhớ.

Nếu processor lọc item bằng cách trả về null, số item ghi có thể nhỏ hơn số item đọc. Test cần phân biệt readCount, filterCount, writeCount thay vì giả định ba số luôn bằng nhau.

## 7. Tổ chức JSON fixtures

Nên lưu fixture thành các file riêng theo mục đích:

~~~text
src/test/resources/json/
  orders-valid.json
  orders-empty.json
  orders-null-fields.json
  orders-missing-field.json
  orders-unknown-field.json
  orders-wrong-type.json
  orders-malformed.json
  orders-wrapper-object.json
  orders-large.json
~~~

Tên file nên nói rõ tình huống. Khi một test thất bại, người đọc có thể mở đúng fixture mà không phải tìm một JSON khổng lồ chứa nhiều trường hợp không liên quan.

Các fixture nên nhỏ và có dữ liệu cụ thể, dễ hiểu. Ví dụ orders-valid.json chỉ cần hai hoặc ba object; fixture lớn dùng riêng cho kiểm tra streaming/performance. Không dùng dữ liệu production có thông tin cá nhân hoặc bí mật làm fixture test.

## 8. Kiểm thử JSON array rỗng

JSON array rỗng là:

~~~json
[]
~~~

Reader nên kết thúc mà không trả item. Test cần xác nhận:

- read() trả null ngay lần đầu.
- Không phát sinh exception nếu empty array là input hợp lệ theo hợp đồng.
- Step kết thúc với trạng thái phù hợp.
- Write count bằng 0 nếu không có item nào được ghi.

Nếu nghiệp vụ yêu cầu ít nhất một record, empty array nên bị từ chối bằng validation/preflight hoặc business rule. Đừng nhầm empty array hợp lệ về cú pháp với input hợp lệ về nghiệp vụ.

## 9. Kiểm thử JSON null và field thiếu

JSON có thể biểu diễn giá trị null:

~~~json
[
  {
    "orderId": 1001,
    "customerId": null,
    "amount": 250.00
  }
]
~~~

Field có thể bị bỏ hẳn:

~~~json
[
  {
    "orderId": 1001,
    "amount": 250.00
  }
]
~~~

Hai trường hợp có thể cho kết quả Java tương tự nếu property là nullable reference, nhưng ý nghĩa hợp đồng có thể khác. Nếu cần phân biệt field không được gửi với field được gửi null, DTO thông thường với một nullable field có thể không đủ; cần custom deserialization, presence flag hoặc JsonNode/wrapper phù hợp.

Test nên xác định rõ:

- customerId null có được chấp nhận không?
- Field thiếu có dùng default value không?
- Field bắt buộc có bị từ chối ngay lúc parse hay ở processor validation?
- Null có được ghi ra output thành JSON null, bị bỏ qua hay thay bằng giá trị mặc định?

Không để Jackson default behavior vô tình quyết định quy tắc nghiệp vụ mà chưa có test xác nhận.

## 10. Kiểm thử kiểu dữ liệu không đúng

Ví dụ JSON có amount là chuỗi:

~~~json
[
  {
    "orderId": 1001,
    "customerId": "C001",
    "amount": "two hundred"
  }
]
~~~

Nếu model yêu cầu BigDecimal, Jackson có thể ném lỗi mapping tùy cấu hình coercion. Test cần xác nhận job xử lý lỗi theo policy đã chọn:

- Từ chối toàn bộ file nếu JSON không đúng schema.
- Dừng step khi gặp object không thể deserialize.
- Hoặc dùng một mô hình đọc linh hoạt để ghi nhận record lỗi và tiếp tục nếu nghiệp vụ cho phép.

Không nên mặc định lỗi JSON parse sẽ được xử lý giống exception trong ItemProcessor. Khi JsonItemReader không thể tạo item, lỗi xảy ra ở reader boundary và cần cấu hình/test tương ứng.

## 11. Kiểm thử JSON malformed

Các ví dụ malformed:

~~~json
[
  {"orderId": 1001, "amount": 250.00},
~~~

hoặc:

~~~json
[
  {"orderId": 1001 "amount": 250.00}
]
~~~

Các lỗi thường gặp gồm thiếu dấu ngoặc, thiếu dấu phẩy, dấu nháy không đóng, token không hợp lệ hoặc nội dung bị cắt giữa chừng.

Test malformed input nên kiểm tra:

- Reader/step thất bại theo dự kiến.
- Exception chain có nguyên nhân parse hữu ích.
- Không có output hoàn chỉnh được publish.
- Staging artifact được giữ hoặc cleanup theo chính sách.
- Job metadata phản ánh trạng thái thất bại.
- Không có item hợp lệ trước đó bị publish như một file hoàn chỉnh nếu hợp đồng yêu cầu all-or-nothing output.

Một JSON array có thể chứa nhiều object trước vị trí malformed. Reader có thể đã trả một số item trước khi lỗi được phát hiện. Nếu writer đã commit một số chunk, cần có staging/publish strategy để downstream không tiêu thụ một phần output chưa hoàn chỉnh.

## 12. Unknown fields và schema evolution

Một hệ thống upstream có thể thêm field mới vào JSON:

~~~json
[
  {
    "orderId": 1001,
    "customerId": "C001",
    "amount": 250.00,
    "salesChannel": "WEB"
  }
]
~~~

Model OrderInput cũ chưa có salesChannel. Tùy cấu hình Jackson, unknown property có thể bị bỏ qua hoặc làm deserialize thất bại.

Test cần quyết định rõ chiến lược tương thích:

- **Forward-compatible:** chấp nhận field không biết và bỏ qua nếu không ảnh hưởng nghiệp vụ.
- **Strict schema:** từ chối file khi xuất hiện field lạ.
- **Versioned schema:** đọc version rồi chọn DTO/mapper tương ứng.
- **Flexible mapping:** giữ field động trong map hoặc JsonNode để xử lý có chủ đích.

Nếu chọn bỏ qua unknown fields, hãy kiểm thử để xác nhận dữ liệu quan trọng không bị mất âm thầm. Nếu chọn strict mode, lỗi phải nêu được property nào không được hỗ trợ.

## 13. Kiểm thử nested object và array

JSON item có thể chứa object hoặc array lồng nhau:

~~~json
[
  {
    "orderId": 1001,
    "customer": {
      "id": "C001",
      "name": "An"
    },
    "lines": [
      {"sku": "P01", "quantity": 2},
      {"sku": "P02", "quantity": 1}
    ]
  }
]
~~~

Test cần xác nhận:

- customer.id được ánh xạ đúng.
- lines có đúng số phần tử và thứ tự.
- Kiểu số lượng là integer nếu model yêu cầu.
- Null hoặc thiếu customer được xử lý đúng.
- Processor không làm mất nested data ngoài ý muốn.
- Writer serialize lại nested object theo schema đích.

Với object graph lớn, cần cân nhắc kích thước item. Chunk size giới hạn số item mỗi transaction, nhưng một item chứa hàng chục nghìn nested objects vẫn có thể tiêu thụ nhiều bộ nhớ.

## 14. Kiểm thử ngày giờ, decimal và enum

Các kiểu dữ liệu dễ gây khác biệt giữa môi trường:

- BigDecimal: kiểm tra giá trị số và scale theo yêu cầu; JSON number không có dấu nháy nếu hợp đồng quy định numeric.
- Ngày: xác định format, ví dụ yyyy-MM-dd.
- Timestamp: xác định timezone/offset, ví dụ ISO-8601 với Z hoặc offset rõ ràng.
- Enum: xác định JSON dùng tên enum, code nghiệp vụ hay một giá trị khác.
- UUID: xác định format chuẩn và cách xử lý giá trị sai.

Ví dụ timestamp:

~~~json
{
  "createdAt": "2026-11-15T10:30:00Z"
}
~~~

Test nên chạy với timezone JVM khác nhau nếu code có nguy cơ dùng timezone mặc định. Không để cùng một input tạo output khác nhau chỉ vì server chạy ở timezone khác.

Nếu Jackson dùng custom serializer/deserializer, cần test hai chiều: input chuyển thành Java đúng và Java được serialize ra đúng định dạng hợp đồng.

## 15. Cấu hình JsonFileItemWriter

JsonFileItemWriter<T> ghi các item thành JSON array. Nó sử dụng JsonObjectMarshaller<T> để chuyển từng item thành JSON representation.

Với Jackson, có thể dùng JacksonJsonObjectMarshaller<T>:

~~~java
@Bean
@StepScope
public JsonFileItemWriter<OrderOutput> orderJsonWriter(
        @Value("#{jobParameters['outputFile']}") String outputFile) {

    return new JsonFileItemWriterBuilder<OrderOutput>()
            .name("orderJsonWriter")
            .resource(new FileSystemResource(outputFile))
            .jsonObjectMarshaller(new JacksonJsonObjectMarshaller<>())
            .saveState(true)
            .build();
}
~~~

Writer quản lý việc tạo JSON array và ghi object theo từng item. JacksonJsonObjectMarshaller chuyển một item thành JSON object; writer ghép các object thành tài liệu output.

Tên builder method và overload cụ thể có thể khác giữa các phiên bản Spring Batch. Hãy dùng API của phiên bản dependency trong dự án; không trộn class JSON reader/writer của các major version khác nhau.

## 16. Kiểm thử JsonFileItemWriter độc lập

Có thể test writer với file tạm và đọc lại kết quả bằng Jackson ObjectMapper hoặc parser JSON khác.

Ví dụ khung test:

~~~java
class OrderJsonWriterTest {

    @TempDir
    Path tempDir;

    @Test
    void writesItemsAsJsonArray() throws Exception {
        Path output = tempDir.resolve("orders.json");

        JsonFileItemWriter<OrderOutput> writer =
                new JsonFileItemWriterBuilder<OrderOutput>()
                        .name("testOrderJsonWriter")
                        .resource(new FileSystemResource(output))
                        .jsonObjectMarshaller(new JacksonJsonObjectMarshaller<>())
                        .saveState(true)
                        .build();

        writer.open(new ExecutionContext());
        try {
            writer.write(new Chunk<>(List.of(
                    new OrderOutput(1001L, "C001", new BigDecimal("250.00")),
                    new OrderOutput(1002L, "C002", new BigDecimal("175.50")))));
            writer.update(new ExecutionContext());
        } finally {
            writer.close();
        }

        JsonNode root = new ObjectMapper().readTree(output.toFile());
        assertTrue(root.isArray());
        assertEquals(2, root.size());
        assertEquals(1001L, root.get(0).get("orderId").asLong());
        assertEquals("C002", root.get(1).get("customerId").asText());
    }
}
~~~

Đây là khung minh họa lifecycle của writer; constructor Chunk và cách gọi writer có thể cần điều chỉnh theo phiên bản Spring Batch. Trong test thực tế, dùng try/finally hoặc try-with-resources phù hợp để luôn đóng writer. Một cách đáng tin cậy hơn cho behavior transaction/restart là chạy writer bên trong step integration test.

Điểm quan trọng là parse output thành cây JSON rồi assert cấu trúc và giá trị. Không nên chỉ kiểm tra file tồn tại hoặc chuỗi output chứa một đoạn text.

## 17. Assert JSON theo cấu trúc thay vì so sánh chuỗi

JSON object không yêu cầu thứ tự key có ý nghĩa. Hai tài liệu sau có thể tương đương về dữ liệu:

~~~json
{"orderId":1001,"customerId":"C001"}
~~~

~~~json
{"customerId":"C001","orderId":1001}
~~~

So sánh chuỗi nguyên văn có thể làm test thất bại chỉ vì serializer thay đổi thứ tự property hoặc whitespace. Thay vào đó, parse JSON thành JsonNode rồi assert theo field:

~~~java
JsonNode actual = objectMapper.readTree(outputFile);

assertEquals(1001L, actual.get(0).get("orderId").asLong());
assertEquals("C001", actual.get(0).get("customerId").asText());
assertEquals(new BigDecimal("250.00"),
        actual.get(0).get("amount").decimalValue());
~~~

Nếu thứ tự phần tử trong array là yêu cầu nghiệp vụ, vẫn phải assert index hoặc sequence. Chỉ thứ tự key trong object thường không phải contract.

Nếu format whitespace, indentation hoặc key order là một phần của hợp đồng ngoài (ví dụ snapshot file được so sánh nguyên văn), có thể có golden-file test riêng. Không dùng snapshot string làm cách duy nhất kiểm tra tính đúng đắn JSON.

## 18. Kiểm tra field thừa, field thiếu và null trong output

Output cần kiểm tra cả dữ liệu có mặt và dữ liệu không được phép xuất hiện.

Ví dụ:

~~~java
JsonNode order = actual.get(0);

assertTrue(order.has("orderId"));
assertFalse(order.has("internalPassword"));
assertTrue(order.has("note"));
assertTrue(order.get("note").isNull());
~~~

has(...) có thể trả true cho field có giá trị JSON null; hasNonNull(...) có semantics khác. Test cần chọn assertion đúng với contract.

Nếu serializer được cấu hình bỏ qua null, output có thể không có field thay vì có "note": null. Cả hai biểu diễn đều hợp lệ về cú pháp nhưng khác nhau về ý nghĩa đối với consumer. Hãy kiểm thử behavior được quy định.

Không để field nội bộ như password, token, database key hoặc debug data lọt vào JSON output. Có thể dùng DTO output riêng và assertion rằng các field nhạy cảm không tồn tại.

## 19. Kiểm thử escaping và ký tự Unicode

JSON serializer phải escape dấu nháy, backslash và các ký tự điều khiển theo chuẩn JSON. Ví dụ tên khách hàng có dấu nháy:

~~~json
[
  {
    "customerName": "An \"The Builder\" Nguyen",
    "note": "Line 1\nLine 2",
    "city": "Thành phố Hồ Chí Minh"
  }
]
~~~

Test nên parse lại output và so sánh giá trị Java sau khi parse. Điều đó chứng minh serializer và parser bảo toàn dữ liệu, không chỉ tạo một chuỗi nhìn có vẻ hợp lệ.

Với tiếng Việt hoặc ký tự ngoài ASCII, cần kiểm tra encoding byte thực tế. Nếu output yêu cầu UTF-8, đọc file bằng StandardCharsets.UTF_8 hoặc parser nhận đúng encoding. Không dựa vào encoding mặc định của máy test.

## 20. Kiểm tra định dạng output và schema contract

JSON không có schema bắt buộc trong cú pháp cơ bản. Hệ thống có thể dùng JSON Schema hoặc một contract riêng để định nghĩa:

- Field bắt buộc.
- Kiểu dữ liệu.
- Giá trị enum hợp lệ.
- Giới hạn số và chuỗi.
- Cấu trúc object/array lồng nhau.
- Field bổ sung được phép hay không.
- Version của schema.

Sau khi writer đóng file, có thể validate JSON output với JSON Schema validator. Test cần xác nhận output vừa parse được vừa thỏa schema.

Parse thành công chỉ chứng minh cú pháp JSON hợp lệ. Ví dụ {"amount":"abc"} là JSON hợp lệ nhưng không phù hợp schema nếu amount phải là number.

## 21. Kiểm thử JSON output rỗng

Khi không có item nào được ghi, writer có thể tạo một JSON array rỗng theo behavior của implementation:

~~~json
[]
~~~

Hãy test trường hợp không có item và xác nhận consumer mong đợi file rỗng, array rỗng hay không tạo file. Ba hành vi này khác nhau.

Nếu job yêu cầu luôn tạo artifact, test cần xác nhận file tồn tại và parse thành array rỗng. Nếu job không nên publish output khi không có dữ liệu, bước publish phải kiểm tra count và áp dụng policy phù hợp.

Không tự giả định writer tạo đúng artifact mong muốn khi chưa có integration test với phiên bản Spring Batch đang dùng.

## 22. Kiểm thử processor giữa JSON input và output

Reader/writer có thể hoạt động đúng nhưng processor vẫn làm sai dữ liệu. Ví dụ processor tính tổng tiền, chuẩn hóa mã khách hàng hoặc lọc order bị hủy.

Unit test processor nên tập trung vào business rule:

~~~java
class OrderProcessorTest {

    private final OrderProcessor processor = new OrderProcessor();

    @Test
    void calculatesNetAmount() {
        OrderInput input = new OrderInput(1001L, "C001",
                new BigDecimal("250.00"));

        OrderOutput output = processor.process(input);

        assertEquals(1001L, output.getOrderId());
        assertEquals(new BigDecimal("225.00"), output.getNetAmount());
    }
}
~~~

Trong end-to-end test, dùng fixture JSON input, chạy job và parse JSON output để xác nhận cả mapping lẫn business transformation.

Nếu processor trả null để filter item, test cần xác nhận filterCount và số phần tử output đúng. Nếu processor ném exception, test xác nhận skip/retry policy theo loại lỗi.

## 23. Integration test chạy job thật

Test reader và writer riêng chưa xác nhận job wiring, transaction manager, step configuration và job parameters. Có thể dùng SpringBatchTest cùng JobLauncherTestUtils để launch job với file fixture và output tạm.

Ví dụ cấu trúc test:

~~~java
@SpringBatchTest
@SpringJUnitConfig(OrderJsonJobTestConfiguration.class)
class OrderJsonJobIntegrationTest {

    @Autowired
    private JobLauncherTestUtils jobLauncherTestUtils;

    @TempDir
    Path tempDir;

    @Test
    void transformsJsonInputIntoExpectedOutput() throws Exception {
        Path output = tempDir.resolve("orders-output.json");

        JobParameters parameters = new JobParametersBuilder()
                .addString("inputFile", "src/test/resources/json/orders-valid.json", true)
                .addString("outputFile", output.toString(), false)
                .addString("runKey", "test-001", true)
                .toJobParameters();

        JobExecution execution = jobLauncherTestUtils.launchJob(parameters);

        assertEquals(BatchStatus.COMPLETED, execution.getStatus());
        assertTrue(Files.exists(output));

        JsonNode root = new ObjectMapper().readTree(output.toFile());
        assertTrue(root.isArray());
        assertEquals(2, root.size());
    }
}
~~~

Đây là cấu trúc minh họa. Cấu hình test cần inject đúng job, datasource/repository và các bean scoped. Với StepScope, job parameter được resolve trong execution; không nên tạo reader/writer target trực tiếp trước khi job context hoạt động.

Nên dùng output path riêng trong TempDir để test không ghi đè file khác và dễ cleanup.

## 24. Kiểm tra BatchStatus và StepExecution metrics

Sau khi launch job, test có thể kiểm tra:

- JobExecution.getStatus() là COMPLETED hoặc trạng thái mong đợi.
- StepExecution.getReadCount() phản ánh số item reader trả về.
- getWriteCount() phản ánh số item writer ghi thành công.
- getFilterCount() phản ánh item processor lọc bằng null.
- getSkipCount() phản ánh item bị skip theo policy.
- getRollbackCount() phản ánh rollback đã xảy ra.

Ví dụ:

~~~java
StepExecution step = execution.getStepExecutions()
        .stream()
        .filter(s -> s.getStepName().equals("transformOrdersStep"))
        .findFirst()
        .orElseThrow();

assertEquals(2, step.getReadCount());
assertEquals(2, step.getWriteCount());
assertEquals(0, step.getSkipCount());
~~~

Các count có semantics riêng. readCount không nhất thiết bằng writeCount nếu processor filter item hoặc step skip record. Với retry, read/write attempt và commit semantics có thể khiến log/metric trong quá trình chạy khác với số item cuối cùng; hãy assert theo contract và dữ liệu output, không dựa vào một count duy nhất.

## 25. Kiểm thử input file không tồn tại hoặc không đọc được

Job nên xử lý rõ khi resource không tồn tại, đường dẫn sai hoặc quyền đọc bị từ chối.

Test nên xác nhận:

- Job/step thất bại với lỗi resource có thể chẩn đoán.
- Không có output được publish.
- Nếu staging file đã được tạo trước khi reader mở, cleanup/retention theo policy.
- Thông báo lỗi không để lộ đường dẫn hoặc dữ liệu nhạy cảm ngoài mức cần thiết.

Có thể kiểm tra file existence trong JobParametersValidator hoặc preflight step, nhưng reader vẫn cần xử lý race condition: file có thể biến mất sau preflight và trước khi mở.

## 26. Kiểm thử chunk rollback và output không hoàn chỉnh

Giả sử job đọc 1.000 object và ghi theo chunk 100. Một chunk giữa chừng gặp lỗi. Test cần xác định output của các chunk đã commit và chưa commit được xử lý như thế nào.

Các điểm cần xác minh:

- Item trong chunk rollback không được xuất hiện như dữ liệu đã commit nếu writer hỗ trợ transactional buffering.
- Khi retry thành công, mỗi item chỉ xuất hiện một lần trong output cuối.
- Nếu job thất bại vĩnh viễn, file staging không được publish như một kết quả hoàn chỉnh.
- Nếu writer/đích không tham gia cùng transaction, cần cơ chế idempotency hoặc staging để xử lý crash window.

File system không phải database transaction tổng quát. Đừng chỉ assert rollbackCount > 0; hãy parse output và xác nhận business keys cùng record count.

## 27. Kiểm thử restart và checkpoint

JsonItemReader và JsonFileItemWriter hỗ trợ lưu state trong ExecutionContext khi được cấu hình đúng. Restart cần dùng cùng JobInstance và nguồn input ổn định.

Một integration test restart có thể:

1. Launch job với identifying parameters cố định.
2. Cho một số chunk commit rồi làm step thất bại.
3. Xác nhận output staging có dữ liệu của chunk đã commit.
4. Restart cùng identifying parameters.
5. Xác nhận reader tiếp tục từ checkpoint và writer tiếp tục đúng resource/state.
6. Parse output cuối và xác nhận mỗi business key xuất hiện đúng một lần.

Không thay input JSON giữa lần chạy đầu và restart. Nếu file thay đổi, checkpoint theo vị trí có thể trỏ tới nội dung khác. Có thể lưu checksum/version của input và từ chối restart nếu nguồn không còn giống ban đầu.

Không thêm identifying parameter mới như timestamp ngẫu nhiên khi restart, vì nó có thể tạo JobInstance mới và làm reader đọc lại từ đầu.

## 28. Kiểm thử output path và không ghi đè

Test nên sử dụng output path riêng cho từng JobInstance hoặc output version. Nếu một job mới cần tạo artifact mới, xác nhận file cũ không đổi.

Một số assertion hữu ích:

- File output của lần chạy trước vẫn tồn tại.
- Checksum file cũ không đổi sau khi job mới hoàn tất.
- File mới được tạo tại path/version riêng.
- Restart cùng instance tiếp tục staging resource cũ.
- File đích đã tồn tại với nội dung khác làm publish thất bại thay vì overwrite âm thầm.
- Manifest chỉ chuyển sang PUBLISHED khi output đã hoàn tất và được xác minh.

Đối với test writer đơn lẻ, dùng TempDir và file tạm để tránh ảnh hưởng output thật. Đối với integration test nhiều execution, dùng output key ổn định và có kiểm soát collision.

## 29. Test schema bằng JSON Schema

Nếu hệ thống trao đổi theo JSON Schema, có thể validate output sau khi ghi. Ví dụ schema rút gọn:

~~~json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "array",
  "items": {
    "type": "object",
    "required": ["orderId", "customerId", "amount"],
    "properties": {
      "orderId": {"type": "integer"},
      "customerId": {"type": "string"},
      "amount": {"type": "number", "minimum": 0}
    },
    "additionalProperties": false
  }
}
~~~

Schema kiểm tra cấu trúc và constraint của tài liệu. Trong test, dùng validator JSON Schema phù hợp với draft đang sử dụng và lưu schema như test resource versioned.

Không chỉ kiểm tra JSON parse được. Một tài liệu có amount là chuỗi vẫn là JSON hợp lệ nhưng không đáp ứng schema trên.

Nếu schema cho phép field mới, cấu hình additionalProperties phù hợp. Nếu không, test cần xác nhận writer không xuất các field ngoài contract.

## 30. So sánh output với expected fixture

Với output nhỏ và contract ổn định, có thể có expected JSON fixture. Nên parse cả actual và expected thành JsonNode rồi so sánh cấu trúc.

Ví dụ:

~~~java
JsonNode expected = objectMapper.readTree(
        new ClassPathResource("json/orders-expected.json").getInputStream());
JsonNode actual = objectMapper.readTree(output.toFile());

assertEquals(expected, actual);
~~~

So sánh tree thường không phụ thuộc whitespace hoặc thứ tự key object, nhưng vẫn giữ thứ tự array. Đây là lựa chọn tốt cho output có cấu trúc nhỏ.

Với output lớn, không nhất thiết lưu một expected file khổng lồ. Có thể kiểm tra count, business key, một số record đại diện, schema và checksum theo quy tắc. Nếu checksum được dùng, cần bảo đảm serialization deterministic và không chứa timestamp/ngẫu nhiên không ổn định.

## 31. Kiểm thử JSON streaming và file lớn

Batch thường xử lý input lớn. Test cần xác nhận reader hoạt động theo luồng và không buộc ứng dụng nạp toàn bộ file vào heap.

Các cách kiểm tra:

- Dùng fixture lớn được tạo trong test hoặc test performance riêng.
- Đọc item tuần tự và đếm, không giữ toàn bộ danh sách trong bộ nhớ.
- Quan sát heap/allocation trong benchmark phù hợp.
- Kiểm tra chunk size và thời gian xử lý với kích thước đại diện.
- Xác nhận output writer không dựng toàn bộ array trong một object graph trước khi ghi.

Một unit test với ba object không chứng minh khả năng xử lý file vài GB. Performance/load test nên tách khỏi unit test để không làm suite thông thường chậm và không ổn định.

## 32. Kiểm thử encoding và file bytes

JSON thường được trao đổi bằng UTF-8. Test nên xác nhận byte output được ghi bằng encoding đã chọn và parser đọc đúng các ký tự Unicode.

Ví dụ:

~~~java
byte[] bytes = Files.readAllBytes(output);
String json = new String(bytes, StandardCharsets.UTF_8);

JsonNode root = objectMapper.readTree(json);
assertEquals("Thành phố Hồ Chí Minh",
        root.get(0).get("city").asText());
~~~

Nếu JSON được đọc từ resource có BOM hoặc encoding khác, hãy xác định behavior mong muốn và test riêng. Không dùng charset mặc định của hệ điều hành.

## 33. Kiểm thử unknown fields và strict deserialization

Jackson có thể được cấu hình strict hoặc permissive khi gặp property không biết. Hai chế độ phục vụ các hợp đồng khác nhau.

Với strict schema, test fixture có field lạ phải làm reader thất bại. Với permissive schema, test phải xác nhận field lạ bị bỏ qua có chủ đích và các field đã biết vẫn được map chính xác.

Không thay đổi global ObjectMapper của ứng dụng test chỉ để một test pass. Cấu hình JSON reader/marshaller nên dùng cùng ObjectMapper hoặc Jackson settings với production để test phản ánh hành vi thật.

## 34. Kiểm thử lỗi theo từng item và skip policy

Nếu JSON array parse được nhưng một object không thỏa business rule, processor có thể ném exception. Đây khác với JSON syntax error hoặc deserialization error tại reader.

Ví dụ:

- JSON malformed: parser không thể đọc cấu trúc.
- JSON hợp lệ nhưng orderId là string trong khi model yêu cầu number: lỗi binding.
- JSON bind thành công nhưng amount < 0: lỗi business validation ở processor.

Test nên phân biệt các tầng này. Nếu business validation exception được cấu hình skip, xác nhận item bị skip, skip listener ghi nhận đúng business key và các item hợp lệ vẫn được ghi. Nếu lỗi reader không thể được skip theo cách mong muốn, hãy cân nhắc đọc object linh hoạt rồi validate ở processor hoặc dùng một cơ chế error record riêng.

Không skip lỗi JSON malformed một cách rộng rãi vì parser có thể không khôi phục được ranh giới object tiếp theo một cách an toàn.

## 35. Các lỗi thường gặp

| Tình huống | Nguyên nhân | Cách xử lý |
|---|---|---|
| Reader không đọc JSON object đơn | Reader mong đợi top-level array | Bọc item trong array hoặc dùng reader phù hợp với wrapper |
| Field Java luôn null | JSON key không khớp property hoặc binding config sai | Kiểm tra tên field, accessor và Jackson annotations |
| Decimal sai giá trị | Dùng double hoặc coercion không mong muốn | Dùng BigDecimal và test giá trị chính xác |
| Unknown field làm job fail | Jackson strict unknown-property setting | Quy định strict/permissive theo contract |
| Malformed JSON làm step fail | Cấu trúc JSON không hợp lệ | Validate input, lưu lỗi parse và không publish output dở dang |
| Null và field thiếu bị nhầm | DTO không giữ thông tin presence | Dùng wrapper/presence flag/JsonNode nếu cần phân biệt |
| Output không phải array | Writer/marshaller hoặc consumer expectation không khớp | Parse output và xác nhận root type |
| Test fail do whitespace/key order | So sánh chuỗi JSON nguyên văn | Parse thành JsonNode và assert cấu trúc |
| Output có field nhạy cảm | Serialize toàn bộ entity/model nội bộ | Dùng DTO output và assert field bị loại |
| Unicode bị lỗi | Encoding mặc định không thống nhất | Dùng UTF-8 rõ ràng và test byte output |
| Restart tạo duplicate | Reader/writer checkpoint không đồng bộ hoặc path thay đổi | Restart cùng JobInstance và resource ổn định |
| Output cũ bị ghi đè | Nhiều instance dùng cùng output path | Dùng staging path/version riêng và publish có kiểm soát |
| Chunk rollback vẫn để output một phần | File không tham gia transaction như mong đợi | Dùng writer transactional support, staging và idempotency |
| Test pass nhưng production khác | Test dùng ObjectMapper/configuration khác | Dùng cấu hình binding giống production |

## 36. Quy trình xây dựng bộ test JSON

1. **Chốt contract JSON:** top-level array hay wrapper, field bắt buộc, kiểu, null và schema version.
2. **Tạo fixture nhỏ:** valid, empty, null/missing, unknown, wrong type và malformed.
3. **Test object reader:** xác nhận mapping từng field, nested object, date/decimal/enum.
4. **Test JsonItemReader:** xác nhận số item, thứ tự, end-of-input và lỗi resource.
5. **Test processor:** kiểm tra business transformation, filter và exception.
6. **Test marshaller/writer:** ghi item, parse output lại và xác nhận cấu trúc/value.
7. **Validate schema:** kiểm tra output bằng JSON Schema nếu contract yêu cầu.
8. **Test job end-to-end:** launch bằng input fixture và output path tạm, kiểm tra status/count/artifact.
9. **Test failure/restart:** gây lỗi giữa chunk, restart cùng JobInstance và xác nhận không mất/trùng item.
10. **Test output isolation:** chạy instance mới hoặc version mới và xác nhận output cũ không thay đổi.
11. **Test kích thước/encoding:** dùng file đại diện, UTF-8 và dữ liệu Unicode.
12. **Giữ test deterministic:** không phụ thuộc timestamp, timezone mặc định, thứ tự key JSON hoặc filesystem path cố định.

## 37. Những nguyên tắc cần nhớ

- JsonItemReader<T> đọc từng object từ JSON array; kiểm tra rõ top-level shape của nguồn.
- JsonObjectReader<T> chịu trách nhiệm ánh xạ một object JSON thành kiểu Java; Jackson implementation là lựa chọn thông dụng.
- JsonFileItemWriter<T> ghi item thành JSON output và dùng JsonObjectMarshaller<T> để serialize.
- Test reader riêng để kiểm tra parse, số lượng, thứ tự và kiểu dữ liệu.
- Test writer bằng cách parse output thành JSON tree; đừng chỉ kiểm tra file tồn tại hoặc so sánh chuỗi whitespace.
- Phân biệt JSON syntax error, deserialization error và business validation error.
- Quy định rõ cách xử lý field thiếu, null, unknown field, enum, decimal, ngày giờ và nested data.
- Dùng DTO output để kiểm soát field được công bố và tránh lộ dữ liệu nội bộ.
- Kiểm tra UTF-8, escaping và ký tự Unicode bằng cách đọc lại file theo encoding rõ ràng.
- JSON parse được chưa chắc phù hợp JSON Schema hoặc hợp đồng downstream.
- Integration test qua job thật để xác nhận wiring, metrics, transaction và job parameters.
- Kiểm thử chunk rollback/restart với cùng JobInstance và input/output resource ổn định.
- Dùng staging/publish để tránh công bố file JSON chưa hoàn chỉnh.
- Performance test cho file lớn nên tách khỏi unit test nhỏ và ổn định.

Kiểm thử JSON input và output cần bao phủ cả cú pháp, mapping, business transformation và vòng đời file. Khi test reader/writer độc lập, xác nhận output bằng parser/schema, rồi chạy integration test có rollback và restart, ứng dụng Spring Batch có thể phát hiện sớm lỗi dữ liệu và bảo đảm artifact JSON cuối cùng đúng hợp đồng, không mất hoặc nhân đôi record.
