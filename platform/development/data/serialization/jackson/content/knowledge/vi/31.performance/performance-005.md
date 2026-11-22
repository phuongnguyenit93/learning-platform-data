# Đánh giá chi phí phản chiếu, serializer cache và khởi tạo lần đầu

Jackson được thiết kế để tái sử dụng metadata và bộ chuyển đổi đã xây dựng, vì vậy chi phí của lần serialize hoặc deserialize đầu tiên thường khác đáng kể so với những lần tiếp theo. Khi một kiểu Java được dùng lần đầu, Jackson cần phân tích class, phát hiện property, đọc annotation, xác định kiểu lồng nhau và tạo serializer hoặc deserializer phù hợp. Các handler đã tạo có thể được lưu trong cache của mapper để tái sử dụng.

Để đánh giá hiệu năng đúng, cần phân biệt ba phần: **chi phí introspection/khởi tạo handler**, **chi phí truy cập property trong mỗi object**, và **chi phí xử lý dữ liệu thực tế** như parse token, chuyển kiểu, ghi byte, cấp phát object và I/O. Serializer cache giảm phần xây dựng handler lặp lại; nó không cache kết quả JSON và cũng không loại bỏ mọi lời gọi getter hoặc thao tác parser.

Bài này giải thích chi phí reflection trong pipeline Jackson, cách serializer/deserializer cache hoạt động, vì sao cold start khác steady state, cách tái sử dụng ObjectMapper/Reader/Writer, và cách đo bằng JMH để quyết định có cần tối ưu accessor hay không.

## 1. Ba nhóm chi phí cần tách biệt

Một thao tác serialize có thể bao gồm:

1. Tìm serializer phù hợp với kiểu Java.
2. Nếu chưa có, introspect class và xây dựng serializer.
3. Duyệt object graph, đọc từng property.
4. Chuyển giá trị thành JSON/YAML/CSV token.
5. Ghi token qua generator ra byte stream hoặc writer.

Deserialize có cấu trúc tương tự: tìm deserializer, xây dựng metadata nếu cần, đọc token, chuyển kiểu, gọi constructor/setter và tạo object graph.

~~~text
                    ObjectMapper
                         |
             +-----------+-----------+
             |                       |
        Serializer path         Deserializer path
             |                       |
       Lookup cache              Lookup cache
             |                       |
        Cache hit?                Cache hit?
          /   \                    /   \
        yes   no                  yes   no
         |     |                   |     |
         |  Introspect           |  Introspect
         |  Build handler        |  Build handler
         |     |                   |     |
         +-----+                   +-----+
             |                       |
       Read properties          Read input tokens
       and write tokens         and create objects
             |                       |
          Output                  Java graph
~~~

Có thể chia chi phí thành ba nhóm:

| Nhóm | Thời điểm | Ví dụ |
|---|---|---|
| Khởi tạo/introspection | Lần đầu dùng kiểu hoặc cấu hình mới | Quét getter/field, đọc annotation, dựng property metadata |
| Truy cập property và binding | Mỗi lần xử lý object | Gọi getter, setter/constructor, chuyển scalar |
| Xử lý format và I/O | Mỗi lần xử lý payload | Parse token, escape string, encode UTF-8, ghi stream |

Cache chủ yếu giúp giảm chi phí nhóm đầu. Nếu payload lớn, phần parse/format, allocation và I/O có thể chiếm phần lớn thời gian dù serializer đã được cache.

## 2. Reflection xuất hiện ở đâu trong Jackson?

Jackson Databind cần hiểu cấu trúc class Java để ánh xạ property. Trong quá trình introspection, nó có thể xem xét:

- Getter như getName() hoặc isEnabled().
- Setter như setName(...).
- Field nếu visibility/configuration cho phép.
- Constructor và factory method.
- Annotation như JsonProperty, JsonIgnore, JsonCreator, JsonFormat.
- Generic type như List<OrderLine> hoặc Map<String, BigDecimal>.
- Naming strategy, visibility và mix-in.
- Polymorphic metadata và custom serializer/deserializer.

Các thông tin này được dùng để tạo property model và handler. Với một bean thông thường, serializer có thể chứa danh sách property writer; deserializer có thể chứa các property setter/creator tương ứng.

### 2.1. Introspection không lặp lại toàn bộ ở mỗi request

Khi mapper gặp một kiểu lần đầu, Jackson cần phân tích metadata và xây serializer/deserializer. Sau khi tạo, handler thường được cache để các lần tiếp theo tra cứu và tái sử dụng.

Do đó, không nên hình dung Jackson mỗi request đều quét lại toàn bộ class bằng reflection từ đầu. Phần introspection thường nằm ở cold path và được amortize qua nhiều lần sử dụng cùng mapper.

### 2.2. Truy cập property vẫn diễn ra cho từng object

Cache serializer không có nghĩa Jackson lưu sẵn giá trị của object. Với mỗi instance được serialize, Jackson vẫn phải lấy giá trị property:

~~~java
String name = user.getName();
int age = user.getAge();
~~~

Tùy accessor và module được sử dụng, việc truy cập có thể đi qua reflection-based accessor hoặc cơ chế tối ưu khác. Sau đó Jackson vẫn phải chuyển giá trị thành token và ghi ra generator.

Nếu một batch có một triệu object, getter và thao tác ghi vẫn diễn ra trên từng object. Cache chỉ giúp tránh xây lại cấu trúc serializer cho mỗi phần tử.

### 2.3. Reflection cost không đồng nghĩa toàn bộ serialization cost

Một payload có nhiều chuỗi dài, nested collection hoặc custom serializer có thể tốn thời gian chủ yếu ở việc duyệt graph, escape ký tự, encode và cấp phát. Tối ưu reflection trong trường hợp đó có thể chỉ cải thiện một phần nhỏ.

Hãy đo theo workload thực tế trước khi kết luận reflection là nút thắt.

## 3. Serializer được tạo như thế nào?

Ở chiều serialize, Jackson dùng serializer factory để tìm hoặc xây serializer cho kiểu cần ghi. Với bean, quy trình khái quát gồm:

1. Xác định JavaType và serializer phù hợp.
2. Introspect bean để lấy BeanDescription/property metadata.
3. Phát hiện các property có thể serialize.
4. Tạo BeanPropertyWriter cho từng property.
5. Áp dụng annotation, mix-in, modifier và custom serializer nếu có.
6. Dựng bean serializer.
7. Cache serializer nếu handler có thể cache theo quy tắc của Jackson.

Một serializer bean đã xây dựng có thể tái sử dụng cho nhiều instance cùng kiểu. Nếu object graph chứa nhiều kiểu khác nhau, Jackson tiếp tục tra cứu hoặc tạo serializer cho các kiểu con.

### 3.1. Serializer không chỉ là một hàm phản chiếu

Serializer đã xây dựng chứa metadata về property, thứ tự, kiểu và handler cần thiết. Khi serialize một object, nó sử dụng cấu trúc đó để đọc giá trị và ghi output.

Một số property có serializer riêng, ví dụ:

- String serializer.
- Number serializer.
- Enum serializer.
- Date/time serializer.
- Collection serializer.
- Map serializer.
- Custom serializer được đăng ký qua module hoặc annotation.

Serializer của root bean có thể dẫn tới các serializer cho kiểu lồng nhau. Khi graph chứa nhiều kiểu, cache có thể tích lũy handler cho các kiểu đó theo thời gian.

## 4. Deserializer được tạo như thế nào?

Ở chiều đọc, Jackson cũng cần introspect kiểu đích:

1. Xác định JavaType từ class hoặc TypeReference.
2. Tìm deserializer tương ứng.
3. Phân tích property, constructor và creator parameter.
4. Xây settable property hoặc creator metadata.
5. Liên kết deserializer cho kiểu lồng nhau.
6. Áp dụng contextualization, annotation và custom deserializer.
7. Cache handler có thể tái sử dụng.

Ví dụ:

~~~java
Order order = mapper.readValue(json, Order.class);
~~~

Lần đầu đọc Order, Jackson có thể cần xây deserializer cho Order và các kiểu liên quan như Customer, Address hoặc OrderLine. Các lần tiếp theo có thể lấy handler từ cache.

Deserializer còn phải xử lý token thực tế, chuyển kiểu và tạo object mới cho mỗi lần đọc. Cache không tái sử dụng object đã deserialize trước đó.

### 4.1. Generic type là một phần của kiểu cần xử lý

Các kiểu sau có cấu trúc khác nhau:

~~~java
List<Order> orders;
List<Invoice> invoices;
Map<String, Payment> payments;
~~~

Jackson cần giữ thông tin generic để chọn deserializer phần tử phù hợp. Khi đọc collection, hãy cung cấp JavaType đầy đủ bằng TypeReference hoặc TypeFactory thay vì chỉ truyền List.class:

~~~java
List<Order> orders = mapper.readValue(
        json,
        new TypeReference<List<Order>>() {}
);
~~~

Nếu chỉ truyền raw type List.class, phần tử có thể trở thành LinkedHashMap hoặc kiểu không như mong đợi. Đây là vấn đề type information và correctness, không phải cách tối ưu cache.

## 5. Serializer cache giúp tiết kiệm điều gì?

Jackson Databind có cache cho serializer đã xây dựng. Khi một kiểu được yêu cầu serialize lần tiếp theo, provider có thể tra cứu serializer tương ứng thay vì chạy lại toàn bộ quy trình introspection và construction.

Lợi ích chính:

- Giảm số lần phân tích class và annotation.
- Giảm số lần tạo BeanPropertyWriter.
- Tái sử dụng handler cho nested types.
- Giảm allocation trong giai đoạn xây serializer.
- Giảm latency của các lần gọi sau khi mapper đã warm.

Serializer cache là cache handler theo kiểu/configuration, không phải cache nội dung JSON.

Ví dụ, cùng một User instance được serialize hai lần, Jackson vẫn đọc property và ghi output ở cả hai lần. Nếu User instance thay đổi tên giữa hai lần, JSON lần sau phản ánh giá trị mới. Cache không giữ bản JSON cũ.

### 5.1. Serializer cache thuộc mapper/provider

Cache được quản lý trong hạ tầng serializer provider/cache của mapper. Các mapper độc lập có cache độc lập; tạo mapper mới đồng nghĩa phải xây handler cho các kiểu dùng trong mapper đó.

Vì vậy, nếu ứng dụng tạo một ObjectMapper mới cho từng request, lợi ích cache bị mất phần lớn. Việc tạo mapper còn làm tăng allocation và có thể lặp đăng ký module/configuration.

### 5.2. Không phải handler nào cũng được cache giống nhau

Jackson có các handler có thể cache và handler có trạng thái phụ thuộc property/context. Serializer có thể khai báo khả năng cache; một số serializer được contextualize theo property, annotation hoặc format.

Do đó, không nên giả định mọi serializer đều có một cache entry duy nhất cho mọi tình huống. Cấu hình property-level, generic type, polymorphism hoặc custom handler có thể tạo các biến thể handler khác nhau.

### 5.3. Cache hit vẫn có chi phí

Ngay cả khi serializer đã có sẵn, Jackson vẫn cần:

- Tra cứu handler.
- Duyệt object graph.
- Lấy giá trị property.
- Xử lý null/include/filter.
- Chuyển scalar và ghi token.
- Cấp phát output buffer hoặc object trung gian nếu có.

Cache cải thiện cold setup và lookup, không biến serialize thành thao tác O(1) hay bỏ qua kích thước payload.

## 6. Deserializer cache và root deserializer cache

Ở chiều deserialize, Jackson cũng cache deserializer để tái sử dụng. ObjectMapper trong Jackson 2.x còn có cơ chế cache riêng cho root deserializer theo JavaType. Điều này giúp các lời gọi readValue() lặp lại với cùng root type tránh phải resolve toàn bộ handler graph từ đầu.

Ví dụ:

~~~java
Order first = mapper.readValue(firstJson, Order.class);
Order second = mapper.readValue(secondJson, Order.class);
~~~

Lần đọc đầu có thể kích hoạt việc dựng deserializer. Lần đọc sau thường dùng lại root deserializer đã được cache.

### 6.1. Root cache không phải cache kết quả đọc

Hai JSON khác nhau vẫn tạo hai object khác nhau. Cache lưu cách đọc kiểu Order, không lưu Order instance của lần trước.

### 6.2. Cache có thể phụ thuộc JavaType

Root type List<Order> khác List<Invoice>. Cùng raw class nhưng khác generic parameter có thể cần handler khác nhau. Khi đánh giá cache behavior, hãy dùng đúng kiểu thực tế của ứng dụng.

### 6.3. Custom deserializer và cacheability

Custom deserializer có thể được tái sử dụng nếu được thiết kế stateless hoặc giữ cấu hình bất biến. Nếu deserializer cần cấu hình theo property, Jackson có thể contextualize nó để tạo instance phù hợp.

Không lưu parser, request context hoặc dữ liệu của lần deserialize trước vào field mutable của deserializer. Handler được cache và có thể được dùng bởi nhiều request/thread.

## 7. Cache không phải cache dữ liệu và không bảo đảm không có allocation

Cần phân biệt ba loại cache:

| Loại | Nội dung được giữ | Jackson Databind mặc định có cung cấp? |
|---|---|---|
| Serializer/deserializer cache | Handler để chuyển đổi một JavaType | Có |
| Object/data cache | Kết quả object đã đọc hoặc JSON đã ghi | Không phải chức năng của serializer cache |
| Application cache | Kết quả nghiệp vụ, response, lookup | Ứng dụng tự thiết kế |

Ví dụ:

~~~java
String json1 = mapper.writeValueAsString(user);
String json2 = mapper.writeValueAsString(user);
~~~

Jackson có thể dùng lại serializer, nhưng vẫn tạo output cho cả json1 và json2. Nếu muốn cache response bytes, ứng dụng phải có cache riêng và tự xử lý invalidation, key, quyền truy cập và freshness.

Không nên nhầm serializer cache với HTTP response cache hoặc cache của database.

## 8. Lần khởi tạo đầu tiên tốn thời gian ở đâu?

Cold path có thể bao gồm nhiều chi phí cùng lúc:

- Khởi tạo ObjectMapper và factory.
- Đăng ký module và cấu hình.
- Load class và dependency lần đầu.
- Introspection bean và annotation.
- Xây serializer/deserializer graph.
- Resolve subtype, generic type và custom handler.
- Khởi tạo buffer hoặc symbol table của parser/generator.
- JIT compilation và class initialization của JVM.

Không phải tất cả chi phí này xảy ra trong constructor ObjectMapper. Nhiều serializer/deserializer chỉ được tạo lười khi ứng dụng lần đầu dùng kiểu tương ứng.

Vì vậy, đo thời gian new ObjectMapper() không đại diện đầy đủ cho cold cost của lần serialize đầu tiên.

### 8.1. Cold start khác steady state

Ví dụ một service vừa khởi động và nhận request đầu tiên:

~~~text
Startup
  |
  v
Create/configure ObjectMapper
  |
  v
First request for Order
  |
  +-- introspect Order
  +-- build Order serializer/deserializer
  +-- resolve nested types
  +-- populate caches
  |
  v
Subsequent requests
  |
  +-- cache lookup
  +-- process values/tokens
  |
  v
Steady state
~~~

Nếu hệ thống có nhiều loại payload hiếm khi dùng, cold cost có thể xuất hiện rải rác trong suốt vòng đời ứng dụng khi mỗi kiểu được dùng lần đầu, không chỉ ngay sau startup.

### 8.2. Warm-up có thể giảm latency request đầu

Nếu một số kiểu quan trọng gần như chắc chắn sẽ được dùng, ứng dụng có thể chủ động serialize/deserialize một fixture nhỏ sau khi cấu hình mapper để kích hoạt handler creation.

Ví dụ:

~~~java
void warmUp(ObjectMapper mapper) throws JsonProcessingException {
    mapper.writerFor(Order.class)
            .writeValueAsBytes(new Order());

    mapper.readerFor(Order.class)
            .readValue("{\"id\":\"warmup\"}");
}
~~~

Ví dụ này chỉ minh họa ý tưởng; JSON warm-up phải hợp lệ với DTO thật. Warm-up nên chạy trước khi readiness báo service nhận traffic nếu startup latency được phép.

Warm-up có chi phí CPU và allocation ở startup. Nếu có hàng nghìn kiểu ít dùng, warm-up tất cả có thể làm startup lâu hơn và tăng memory. Chỉ warm các root type quan trọng đã đo được.

## 9. Vì sao nên tái sử dụng ObjectMapper?

ObjectMapper là đối tượng cấu hình và điều phối serializer/deserializer cache. Tạo mapper mới liên tục khiến ứng dụng mất lợi ích tái sử dụng handler và lặp chi phí cấu hình.

Một pattern thường dùng:

~~~java
public final class JsonSupport {
    private static final ObjectMapper MAPPER =
            JsonMapper.builder()
                    .addModule(new JavaTimeModule())
                    .build();

    private static final ObjectWriter ORDER_WRITER =
            MAPPER.writerFor(Order.class);

    private static final ObjectReader ORDER_READER =
            MAPPER.readerFor(Order.class);

    private JsonSupport() {
    }

    public static byte[] writeOrder(Order order)
            throws JsonProcessingException {
        return ORDER_WRITER.writeValueAsBytes(order);
    }

    public static Order readOrder(byte[] json)
            throws IOException {
        return ORDER_READER.readValue(json);
    }
}
~~~

Sau khi mapper được cấu hình hoàn chỉnh, Jackson cho phép tái sử dụng mapper cho nhiều thread. ObjectReader và ObjectWriter là đối tượng cấu hình bất biến, phù hợp để giữ và tái sử dụng cho các kiểu/operation cụ thể.

### 9.1. Cấu hình xong trước khi dùng

Không nên:

~~~java
ObjectMapper mapper = sharedMapper;
mapper.registerModule(new JavaTimeModule());
~~~

nếu sharedMapper đã được dùng bởi request khác. Thay đổi cấu hình mapper sau khi bắt đầu sử dụng có thể dẫn đến hành vi khó dự đoán và cache không nhất quán theo kỳ vọng.

Hãy đăng ký module, mix-in, visibility, naming strategy, serializer/deserializer và feature trước khi publish mapper cho các thread.

### 9.2. Không tạo mapper trong vòng lặp xử lý record

Ví dụ không tốt:

~~~java
for (Event event : events) {
    ObjectMapper mapper = new ObjectMapper();
    output.add(mapper.writeValueAsString(event));
}
~~~

Ví dụ tốt hơn:

~~~java
ObjectMapper mapper = sharedConfiguredMapper;

for (Event event : events) {
    output.add(mapper.writeValueAsString(event));
}
~~~

Mapper được tái sử dụng, serializer của Event và các kiểu liên quan có cơ hội được cache sau lần đầu.

### 9.3. ObjectMapper.copy() cũng tạo mapper mới

Copy mapper có thể hữu ích khi cần cấu hình độc lập, nhưng không nên dùng copy cho mỗi request với kỳ vọng chia sẻ cache. Mapper copy có lifecycle/cache riêng. Nếu cần nhiều policy khác nhau, tạo một số mapper cố định theo trust boundary hoặc format, cấu hình một lần rồi tái sử dụng.

## 10. ObjectReader và ObjectWriter giúp cố định kiểu và cấu hình

ObjectReader/ObjectWriter cho phép chuẩn bị cấu hình đọc/ghi cụ thể:

~~~java
ObjectReader orderReader = mapper.readerFor(Order.class);
ObjectWriter orderWriter = mapper.writerFor(Order.class);

Order order = orderReader.readValue(json);
byte[] bytes = orderWriter.writeValueAsBytes(order);
~~~

Chúng bất biến và thread-safe, nên có thể dùng chung. Chúng giúp:

- Tránh lặp việc tạo reader/writer ở mỗi call site.
- Cố định root type rõ ràng.
- Tách format/configuration theo use case.
- Dễ review contract serialize/deserialize.
- Kết hợp với schema, view hoặc feature riêng mà không thay đổi mapper global.

Tạo ObjectReader/ObjectWriter mới thường nhẹ hơn tạo ObjectMapper mới, nhưng nếu cấu hình được dùng lặp lại, giữ sẵn instance vẫn làm code rõ và tránh tạo object không cần thiết.

## 11. Nhiều mapper có thể làm cache phân mảnh

Một ứng dụng có thể có mapper cho JSON, YAML và CSV:

~~~java
ObjectMapper jsonMapper = JsonMapper.builder().build();
XmlMapper xmlMapper = new XmlMapper();
YAMLMapper yamlMapper = new YAMLMapper();
CsvMapper csvMapper = new CsvMapper();
~~~

Các mapper/format factory này có cấu hình và cache riêng. Nếu cùng một DTO được dùng ở nhiều mapper, mỗi mapper có thể cần xây handler riêng cho format tương ứng.

Điều này bình thường vì JSON generator, XML token adapter, YAML backend và CSV schema có behavior khác nhau. Không nên cố dùng chung một serializer cache giữa các format.

Tuy nhiên, đừng tạo nhiều mapper cho cùng một format chỉ vì mỗi service muốn một vài feature khác nhau. Có thể dùng ObjectReader/ObjectWriter hoặc cấu hình mapper theo boundary để giảm số mapper cần giữ.

## 12. Reflection và accessor optimization

Sau khi serializer đã được tạo và cache, việc đọc property vẫn có thể là một phần chi phí của mỗi object. Jackson có thể sử dụng accessor dựa trên reflection; các module tối ưu có thể thay đổi cách gọi getter/setter.

Hai module từng được dùng trong hệ sinh thái Jackson:

- **Afterburner:** tạo bytecode hỗ trợ truy cập property nhanh hơn cho một số kiểu bean.
- **Blackbird:** dùng các cơ chế MethodHandle trên JVM hiện đại để tối ưu property access trong những trường hợp phù hợp.

Việc hỗ trợ và hiệu quả phụ thuộc Jackson version, JDK, class visibility, module system, kiểu model và workload. Không nên đăng ký module tối ưu chỉ vì benchmark tổng quát của một dự án khác cho thấy cải thiện.

### 12.1. Ví dụ đăng ký Afterburner

~~~java
ObjectMapper mapper = JsonMapper.builder()
        .addModule(new AfterburnerModule())
        .build();
~~~

### 12.2. Ví dụ đăng ký Blackbird

~~~java
ObjectMapper mapper = JsonMapper.builder()
        .addModule(new BlackbirdModule())
        .build();
~~~

Hai ví dụ trên là các lựa chọn thay thế để đánh giá theo dependency và JDK của ứng dụng. Không mặc định đăng ký cả hai cùng lúc. Kiểm tra tài liệu tương thích của module đang chọn và đo kết quả với model thật.

### 12.3. Những giới hạn cần kiểm tra

Accessor optimization có thể bị ảnh hưởng bởi:

- Class hoặc member không public.
- Package/module không mở quyền truy cập cần thiết.
- Security và class-loading constraints của môi trường.
- Native image hoặc AOT compilation.
- Constructor/record/creator pattern đặc biệt.
- Custom serializer/deserializer vốn đã thay thế đường truy cập mặc định.
- Phiên bản module không tương thích với Jackson core/databind.

Nếu module tối ưu không thể truy cập một member, nó có thể fallback hoặc gây lỗi tùy module/version. Chạy integration test trên đúng JDK và runtime production.

### 12.4. Tối ưu accessor không loại bỏ chi phí format

Ngay cả khi getter/setter nhanh hơn, Jackson vẫn phải xử lý token, escape, number formatting, buffer và I/O. Nếu bottleneck nằm ở output size hoặc allocation, accessor module có thể không đem lại cải thiện đáng kể.

## 13. Mapper feature và reflection

Một số MapperFeature ảnh hưởng cách Jackson khám phá và truy cập property, ví dụ:

- AUTO_DETECT_FIELDS.
- AUTO_DETECT_GETTERS.
- AUTO_DETECT_IS_GETTERS.
- AUTO_DETECT_SETTERS.
- USE_ANNOTATIONS.
- CAN_OVERRIDE_ACCESS_MODIFIERS.
- OVERRIDE_PUBLIC_ACCESS_MODIFIERS.

Những feature này chủ yếu điều khiển contract introspection và visibility. Tắt auto-detection có thể làm giảm số member được xem xét trong một model, nhưng thay đổi đó cũng có thể khiến property biến mất khỏi JSON. Không nên thay đổi chỉ để hy vọng tăng tốc nếu chưa xác nhận schema.

Ví dụ cấu hình visibility rõ ràng:

~~~java
ObjectMapper mapper = JsonMapper.builder()
        .visibility(PropertyAccessor.ALL, JsonAutoDetect.Visibility.NONE)
        .visibility(PropertyAccessor.FIELD, JsonAutoDetect.Visibility.ANY)
        .build();
~~~

Cấu hình này chuyển sang field visibility rộng. Nó thay đổi contract access và có thể truy cập field private tùy cấu hình/module. Hãy dùng khi muốn một model contract dựa trên field một cách có chủ đích, không phải như một micro-optimization chung.

### 13.1. Reflection và Java module system

Trên JDK hiện đại, strong encapsulation có thể giới hạn việc truy cập reflective vào một số package/module. CAN_OVERRIDE_ACCESS_MODIFIERS hoặc việc gọi setAccessible không đảm bảo luôn vượt qua được module boundary.

Nếu Jackson không thể truy cập constructor, field hoặc method, hãy kiểm tra:

- Class và member có public phù hợp không?
- Package có cần được mở bằng module-info hoặc runtime option không?
- DTO có thể dùng constructor/creator public thay thế không?
- Có đang dựa vào private member của thư viện bên thứ ba không?

Không nên thêm --add-opens rộng chỉ để che một thiết kế DTO khó truy cập nếu có thể cung cấp API constructor/property rõ ràng hơn.

## 14. Cache size và memory trade-off

Serializer/deserializer cache giúp giảm CPU cho handler creation nhưng cần bộ nhớ để giữ metadata và handler. Khi ứng dụng dùng nhiều loại JavaType, generic specialization hoặc dynamic model, số entry có thể tăng.

Các điểm cần hiểu:

- Cache thuộc mapper/provider, không phải cache toàn JVM cho mọi ObjectMapper.
- Các kiểu được dùng thường xuyên có khả năng được tái sử dụng.
- Các handler không cacheable hoặc phụ thuộc context có behavior riêng.
- Cache implementation và giới hạn cụ thể có thể thay đổi theo Jackson version.
- Một mapper sống lâu có thể giữ metadata của nhiều kiểu đã gặp.
- Tạo nhiều mapper làm phân mảnh cache và tăng tổng memory.

Không nên dựa vào một con số cache capacity lấy từ tài liệu của version khác. Nếu memory là vấn đề, đo heap và kiểm tra đúng version Jackson đang dùng.

### 14.1. Dynamic type và cache cardinality

Nếu ứng dụng tạo class proxy hoặc kiểu chuyên biệt hóa động liên tục, cache có thể gặp nhiều JavaType khác nhau. Một ứng dụng thông thường với DTO cố định thường không gặp vấn đề lớn, nhưng framework/plugin system hoặc runtime-generated class có thể tạo áp lực cache.

Không tạo DTO/class động theo từng request chỉ để biểu diễn dữ liệu. Dùng cấu trúc ổn định như Map, JsonNode hoặc một số model đã định nghĩa nếu schema thực sự động.

### 14.2. Không tự xây cache serializer ở application layer

Thông thường không cần viết Map<Class<?>, JsonSerializer<?>> riêng để cache handler mà Jackson đã quản lý. Việc tự cache có thể gây lỗi generic type, contextualization, thread safety hoặc classloader retention.

Chỉ tạo cache application-level nếu có một yêu cầu cụ thể và đã chứng minh bằng profiling rằng Jackson cache không đáp ứng. Trước tiên hãy tái sử dụng mapper đúng cách.

## 15. Đo cold start và steady state bằng JMH

Để đánh giá reflection, cache và first-use cost, nên dùng JMH thay vì viết vòng lặp với System.nanoTime(). JMH xử lý warm-up, fork, measurement và các vấn đề tối ưu hóa JVM tốt hơn benchmark thủ công.

Cần đo ít nhất:

1. Mapper construction.
2. First serialization/deserialization của một kiểu.
3. Steady-state serialization/deserialization với mapper đã warm.
4. Workload có nested graph hoặc batch.
5. Allocation và GC.
6. Payload nhỏ/lớn theo dữ liệu thực tế.

### 15.1. Benchmark steady state

~~~java
@State(Scope.Thread)
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.MICROSECONDS)
@Warmup(iterations = 5)
@Measurement(iterations = 8)
@Fork(2)
public class JacksonWarmBenchmark {

    private ObjectMapper mapper;
    private ObjectWriter writer;
    private ObjectReader reader;
    private Order sample;
    private byte[] json;

    @Setup(Level.Trial)
    public void setup() throws Exception {
        mapper = configuredMapper();
        sample = sampleOrder();

        writer = mapper.writerFor(Order.class);
        reader = mapper.readerFor(Order.class);

        json = writer.writeValueAsBytes(sample);

        // Tạo handler trước khi measurement bắt đầu.
        reader.readValue(json);
    }

    @Benchmark
    public byte[] serializeWarm() throws Exception {
        return writer.writeValueAsBytes(sample);
    }

    @Benchmark
    public Order deserializeWarm() throws Exception {
        return reader.readValue(json);
    }
}
~~~

Mapper và reader/writer được tạo ở setup, sau đó handler được kích hoạt trước measurement. Benchmark này gần với steady state hơn first request.

### 15.2. Benchmark mapper creation cộng first write

~~~java
@State(Scope.Thread)
public class JacksonColdMapperBenchmark {

    private Order sample;

    @Setup(Level.Trial)
    public void setup() {
        sample = sampleOrder();
    }

    @Benchmark
    public byte[] createMapperAndWriteFirstTime() throws Exception {
        ObjectMapper mapper = configuredMapper();
        return mapper.writeValueAsBytes(sample);
    }
}
~~~

Benchmark này đo cả mapper construction, cấu hình và first serialization. Không nên gọi kết quả là “chỉ chi phí reflection”, vì nhiều chi phí khác nằm trong phép đo.

### 15.3. Cô lập first-use handler với mapper mới

Có thể tạo mapper mới ở invocation setup rồi đo lần write đầu tiên:

~~~java
@State(Scope.Thread)
public class JacksonFirstUseBenchmark {

    private ObjectMapper mapper;
    private Order sample;

    @Setup(Level.Trial)
    public void setupSample() {
        sample = sampleOrder();
    }

    @Setup(Level.Invocation)
    public void resetMapper() {
        mapper = configuredMapper();
    }

    @Benchmark
    public byte[] firstWriteForFreshMapper() throws Exception {
        return mapper.writeValueAsBytes(sample);
    }
}
~~~

Trong cách này, thời gian setup invocation không nằm trong method benchmark theo quy tắc JMH, còn lần serialize đầu được đo. Tuy nhiên, setup mỗi invocation có thể ảnh hưởng đến cache CPU, GC và overhead tổng thể của harness. Hãy ghi rõ đây là benchmark first-use, không dùng nó thay cho latency end-to-end của startup.

Nếu cần đo first deserialization, tạo mapper mới cho mỗi invocation và đọc cùng một JSON fixture hợp lệ.

### 15.4. Đừng trộn cold và warm trong cùng một con số

Nếu benchmark chạy nhiều vòng trên cùng mapper mà không reset cache, chỉ iteration đầu có thể cold; các iteration sau đã warm. Kết quả trung bình sẽ không đại diện chính xác cho cold start hoặc steady state.

Hãy đặt tên benchmark rõ ràng, dùng state/setup phù hợp và báo cáo riêng từng loại.

## 16. Thiết kế benchmark công bằng

Một benchmark hữu ích cần giữ các điều kiện so sánh tương đương:

- Cùng JDK, Jackson version và dependency.
- Cùng model và dữ liệu đầu vào.
- Cùng module và feature configuration.
- Cùng kích thước payload.
- Cùng kiểu output (byte[] hay String).
- Cùng số lượng record và độ sâu object graph.
- Cùng warm-up/fork/measurement.
- Chạy trên máy tương đối nhàn rỗi.
- Ghi lại JVM flags và phần cứng.

Nếu so sánh mapper mặc định với Afterburner/Blackbird, chỉ thay module accessor, giữ các yếu tố còn lại giống nhau.

### 16.1. Đo allocation, không chỉ thời gian

Dùng GC profiler của JMH:

~~~text
java -jar target/benchmarks.jar JacksonWarmBenchmark -prof gc
~~~

Các chỉ số allocation/op và GC giúp biết module tối ưu có giảm thời gian bằng cách tạo thêm object hay không. Một kết quả nhanh hơn nhưng allocation tăng mạnh có thể gây áp lực heap trong production.

### 16.2. Tránh benchmark không đại diện

Các lỗi thường gặp:

- Serialize một object quá nhỏ rồi suy rộng cho payload lớn.
- Dùng một mapper mới cho benchmark steady state.
- Dùng mapper đã warm cho benchmark cold start.
- Không tiêu thụ kết quả nên JVM có thể tối ưu bỏ phần tính toán.
- Tự đo bằng vòng lặp và nanoTime mà không warm JVM.
- Chạy benchmark đồng thời với build hoặc tác vụ CPU nặng.
- Chỉ nhìn average, bỏ qua tail latency và allocation.
- So sánh hai cấu hình có module/feature khác nhau ngoài ý muốn.

JMH xử lý một số vấn đề harness nhưng không thể tự chọn workload đúng cho ứng dụng. Payload và model vẫn phải đại diện thực tế.

## 17. Đọc kết quả: cold latency, throughput và allocation

Một bảng kết quả nên tách:

| Metric | Ý nghĩa | Dùng để đánh giá |
|---|---|---|
| First-use latency | Thời gian lần đầu dùng kiểu | Startup/first request |
| Average time | Thời gian trung bình mỗi operation | Chi phí steady state |
| Throughput | Operations/second | Batch hoặc service capacity |
| p50/p95/p99 | Phân phối latency | Tail latency production |
| Allocation/op | Byte được cấp phát mỗi operation | Áp lực heap/GC |
| GC count/time | Tần suất và thời gian GC | Tác động dài hạn |
| Mapper startup time | Thời gian tạo/cấu hình mapper | Application startup |

JMH benchmark micro có thể cung cấp average và throughput; tail latency của request production nên được đo ở tầng service bằng telemetry phù hợp. Không suy ra p99 production chỉ từ một microbenchmark.

### 17.1. Cách diễn giải

- Cold cao, warm thấp: handler construction/introspection có thể đáng chú ý; cân nhắc warm-up cho kiểu quan trọng.
- Cold và warm đều cao: chi phí per-value, payload, custom handler hoặc I/O có thể là nút thắt.
- Time giảm nhưng allocation tăng: kiểm tra GC và tải đồng thời.
- Afterburner/Blackbird cải thiện ít: accessor reflection không phải phần lớn tổng chi phí.
- Mapper mới mỗi request chậm rõ: tái sử dụng mapper có thể là thay đổi hiệu quả nhất.
- Warm throughput tốt nhưng p99 production cao: tìm contention, I/O, GC, payload outlier hoặc queueing ngoài Jackson.

Không có một tỷ lệ tăng tốc cố định áp dụng cho mọi model. Kết quả phụ thuộc JDK, Jackson version, kiểu DTO, module và kích thước dữ liệu.

## 18. Warm-up ở startup có đáng làm không?

Warm-up hữu ích khi:

- Có một số root type chắc chắn được dùng ngay sau readiness.
- First request latency là yêu cầu quan trọng.
- Việc dựng handler cho các kiểu đó có chi phí đo được.
- Startup có đủ CPU và thời gian để xử lý warm-up.
- Warm-up payload không kích hoạt side effect nghiệp vụ.

Warm-up ít hữu ích khi:

- Ứng dụng có hàng nghìn type hiếm dùng.
- Handler được tạo nhanh và first-use latency không đáng kể.
- Startup time quan trọng hơn request đầu.
- Warm-up phải tạo graph lớn hoặc gọi dịch vụ ngoài.
- Hệ thống autoscale liên tục và warm-up làm tăng CPU startup đáng kể.

### 18.1. Warm-up không phải benchmark

Warm-up trong ứng dụng nhằm chuyển một phần chi phí first-use ra trước readiness. JMH warm-up nhằm giúp JVM đạt trạng thái ổn định trước measurement. Hai mục tiêu khác nhau và không thay thế nhau.

### 18.2. Warm-up phải an toàn và xác định

Dùng fixture nội bộ nhỏ, không gọi database, không phát event và không thực hiện side effect. Có thể dùng ObjectReader/ObjectWriter đã cấu hình để kích hoạt handler cho root type quan trọng.

Không cần giữ kết quả JSON warm-up trong cache nghiệp vụ. Chỉ cần tạo handler; sau đó bỏ output.

## 19. Khi nào nên dùng streaming API?

Nếu ứng dụng cần xử lý rất nhiều record đơn giản và không cần object graph đầy đủ, Jackson Streaming API có thể giảm chi phí databinding và allocation.

Databinding:

~~~java
Order order = mapper.readValue(json, Order.class);
~~~

Streaming:

~~~java
try (JsonParser parser = mapper.getFactory().createParser(json)) {
    while (parser.nextToken() != null) {
        // Tự xử lý token theo schema đã biết.
    }
}
~~~

Streaming loại bỏ một số chi phí tạo POJO và property binding nhưng làm code phức tạp hơn, ứng dụng phải tự quản lý token state, validation và path lỗi. Không nên chuyển toàn bộ ứng dụng sang streaming chỉ vì một microbenchmark cho thấy nhanh hơn.

Với YAML/CSV, các dataformat module vẫn có parser/generator riêng; hãy benchmark đúng format và workload. CsvMapper còn có schema và row mapping cost, YAML có parser backend và scalar handling. Kết quả benchmark JSON không tự động đại diện cho YAML hoặc CSV.

## 20. Tác động của annotation, polymorphism và custom handlers

Một số cấu hình làm handler phức tạp hơn:

- @JsonTypeInfo và subtype resolution.
- @JsonIdentityInfo và object ID handling.
- @JsonFormat cho date/number.
- @JsonView và property filters.
- @JsonInclude và null suppression.
- Custom serializer/deserializer.
- Contextual serializer/deserializer.
- Mix-in và BeanSerializerModifier/BeanDeserializerModifier.

Những tính năng này có thể thêm metadata hoặc nhánh xử lý trong lúc xây handler và xử lý từng value. Không nên loại bỏ chúng chỉ để tăng tốc nếu chúng là một phần contract.

Hãy benchmark model thực tế có các annotation/module đang dùng. Một benchmark POJO đơn giản không đại diện cho payload có polymorphic graph hoặc custom conversion.

## 21. Cấu hình và reuse theo format YAML/CSV

YAMLMapper, CsvMapper và XmlMapper đều dựa trên Jackson Databind nhưng có factory/parser/generator riêng. Nên tạo từng mapper theo format, cấu hình module và schema một lần rồi tái sử dụng.

Ví dụ:

~~~java
public final class DataMappers {
    public static final YAMLMapper YAML = createYamlMapper();
    public static final CsvMapper CSV = createCsvMapper();

    private DataMappers() {
    }

    private static YAMLMapper createYamlMapper() {
        YAMLMapper mapper = new YAMLMapper();
        mapper.registerModule(new JavaTimeModule());
        return mapper;
    }

    private static CsvMapper createCsvMapper() {
        CsvMapper mapper = new CsvMapper();
        mapper.registerModule(new JavaTimeModule());
        return mapper;
    }
}
~~~

Đối với CSV, giữ CsvSchema/CsvSchema builder theo contract file và tái sử dụng schema đã build nếu phù hợp. Không build schema và mapper mới cho từng row.

Đối với YAML, dùng mapper đã cấu hình và tránh tạo YAMLFactory/mapper mới mỗi lần đọc file. Nếu các boundary cần policy khác nhau, giữ số mapper cố định theo policy thay vì tạo mapper theo request.

## 22. Theo dõi hiệu năng trong production

Microbenchmark cho biết chi phí của một đoạn code trong điều kiện kiểm soát. Production telemetry cho biết tác động trên request thật.

Có thể theo dõi:

- Thời gian serialize/deserialize theo root type hoặc endpoint.
- Kích thước payload.
- Số record trong batch.
- Allocation/GC ở service.
- First request sau deploy hoặc scale-up.
- Tỷ lệ lỗi mapping và custom handler.
- CPU time theo endpoint nếu profiling cho phép.

Không ghi raw JSON hoặc giá trị nhạy cảm chỉ để đo hiệu năng. Tag metric theo một tập type/route có giới hạn, tránh dùng class name động hoặc dữ liệu người dùng làm metric label gây cardinality tăng cao.

Nếu cần đo first-use, ghi nhận thời điểm mapper/type được dùng lần đầu hoặc thực hiện startup warm-up có metric riêng. Không thêm logging đồng bộ ở mỗi property vì chính logging có thể làm sai số đo.

## 23. Các lỗi tối ưu thường gặp

**Tạo ObjectMapper mới trong mỗi request.** Cache serializer/deserializer không được tái sử dụng. Cấu hình mapper một lần rồi chia sẻ.

**Nghĩ rằng serializer cache giữ JSON output.** Cache giữ handler, mỗi object vẫn được đọc và ghi lại.

**Đo cold và warm chung một benchmark.** Các lần sau dùng cache khiến kết quả không còn phản ánh first-use.

**Đo new ObjectMapper() rồi kết luận đó là first serialization cost.** Serializer thường được tạo lười; cần đo cả lần write/read đầu.

**Cho rằng reflection chạy lại toàn bộ ở mỗi call.** Introspection/handler construction thường được cache; per-value accessor và binding vẫn chạy.

**Bật Afterburner/Blackbird mà không benchmark.** Hiệu quả phụ thuộc JDK, model và workload; module có thể có giới hạn truy cập class.

**Thay đổi visibility để tăng tốc nhưng làm mất property.** MapperFeature là một phần contract mapping; test schema trước khi thay đổi.

**Tạo quá nhiều mapper theo từng service/request.** Cache bị phân mảnh, memory và startup cost tăng.

**Warm-up mọi kiểu trong classpath.** Startup có thể chậm và memory tăng mà không đem lại lợi ích cho kiểu hiếm dùng.

**Tự viết cache serializer riêng.** Có nguy cơ bỏ qua contextualization, generic type và thread safety mà Jackson đã quản lý.

**Tối ưu reflection trong khi bottleneck là I/O hoặc payload size.** Profile toàn pipeline trước khi chọn giải pháp.

**Chỉ xem average latency.** Tail latency, allocation và GC có thể vẫn xấu.

## 24. Quy trình đánh giá chi phí và lựa chọn tối ưu

Khi Jackson bị cho là chậm:

1. Xác định operation cụ thể: serialize hay deserialize, format nào, root type nào.
2. Tái sử dụng một mapper đã cấu hình và so sánh với cấu hình hiện tại.
3. Đo mapper construction riêng.
4. Đo first-use serializer/deserializer với mapper mới.
5. Đo steady state với mapper đã warm.
6. Dùng payload thực tế gồm nested object, collection, string và scalar.
7. Đo allocation/GC bên cạnh thời gian.
8. Kiểm tra mapper có bị tạo mới hoặc copy quá thường xuyên không.
9. Nếu accessor vẫn là bottleneck, benchmark Afterburner/Blackbird phù hợp với JDK.
10. Cân nhắc streaming chỉ khi lợi ích đo được đủ lớn so với độ phức tạp.
11. Warm-up một số root type quan trọng nếu first request latency cần giảm.
12. Chạy integration/performance test trên JDK, Jackson version và format provider production.
13. Giữ nguyên contract mapping và kiểm tra regression sau mỗi tối ưu.

## 25. Kết luận

Chi phí reflection/introspection của Jackson tập trung đáng kể ở lúc xây serializer/deserializer lần đầu cho một JavaType. Serializer cache và deserializer/root cache cho phép mapper tái sử dụng handler, nên các lần gọi sau thường tránh được phần lớn chi phí dựng metadata. Tuy vậy, mỗi object vẫn phải được duyệt, property vẫn phải được đọc hoặc gán, token vẫn phải parse/format và output vẫn phải được ghi. Cache không lưu kết quả JSON hay object đã deserialize.

Cách tối ưu cơ bản nhất là cấu hình ObjectMapper hoàn chỉnh một lần rồi tái sử dụng, đồng thời giữ ObjectReader/ObjectWriter cho những root type thường dùng. Chỉ warm-up các kiểu quan trọng khi first-request latency thực sự đáng kể. Nếu accessor reflection vẫn chiếm phần đáng kể sau profiling, có thể benchmark Afterburner hoặc Blackbird trên đúng JDK/model; nếu chi phí nằm ở object graph, allocation hoặc I/O, cần xử lý đúng bottleneck đó.

Hãy tách benchmark cold-start khỏi steady-state bằng JMH, đo cả thời gian lẫn allocation/GC, và dùng payload đại diện cho ứng dụng. Một kết quả microbenchmark không thay thế telemetry production, nhưng khi kết hợp cả hai, nhóm phát triển có thể quyết định có cần tối ưu accessor, warm-up, streaming hay chỉ cần tái sử dụng mapper đúng cách.

## Tài liệu tham khảo

- [Jackson Databind — ObjectMapper API](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-databind/latest/com/fasterxml/jackson/databind/ObjectMapper.html)
- [Jackson Databind — SerializerCache API](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-databind/latest/com/fasterxml/jackson/databind/ser/SerializerCache.html)
- [Jackson Databind — DeserializerCache API](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-databind/latest/com/fasterxml/jackson/databind/deser/DeserializerCache.html)
- [Jackson Databind — ObjectReader API](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-databind/latest/com/fasterxml/jackson/databind/ObjectReader.html)
- [Jackson Databind — ObjectWriter API](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-databind/latest/com/fasterxml/jackson/databind/ObjectWriter.html)
- [Jackson Afterburner module](https://github.com/FasterXML/jackson-modules-base/tree/2.x/afterburner)
- [Jackson Blackbird module](https://github.com/FasterXML/jackson-modules-base/tree/2.x/blackbird)
- [OpenJDK JMH](https://github.com/openjdk/jmh)

