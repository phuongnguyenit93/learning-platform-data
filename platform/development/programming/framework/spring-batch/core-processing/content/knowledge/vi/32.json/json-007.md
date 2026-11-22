# Unknown field và schema evolution

Trong Spring Batch, dữ liệu JSON thường được đọc thành Java object rồi chuyển qua processor và writer. Khi hệ thống nguồn thay đổi cấu trúc JSON, file mới có thể chứa field mà phiên bản ứng dụng hiện tại chưa biết, thiếu field cũ hoặc đổi kiểu dữ liệu của một property. Nếu không có chính sách tương thích rõ ràng, Job có thể thất bại giữa chừng hoặc âm thầm bỏ mất dữ liệu.

**Unknown field** là property xuất hiện trong JSON nhưng không có mapping tương ứng trong Java model đang dùng. **Schema evolution** là quá trình thay đổi cấu trúc hoặc ý nghĩa schema theo thời gian, chẳng hạn thêm field, bỏ field, đổi tên, đổi kiểu hoặc thay đổi quy tắc bắt buộc.

Với Spring Batch, việc xử lý unknown field thường được quyết định ở tầng JSON deserialization, chẳng hạn Jackson được dùng bởi **JsonItemReader** thông qua **JacksonJsonObjectReader**. Spring Batch điều khiển việc đọc theo item và chunk; ObjectMapper quyết định JSON object có thể được ánh xạ vào model hay không. Cần chọn chính sách phù hợp với hợp đồng dữ liệu, yêu cầu audit và khả năng triển khai độc lập giữa hệ thống nguồn và hệ thống nhận.

## 1. JSON schema thay đổi như thế nào?

Giả sử phiên bản đầu của nguồn gửi JSON:

~~~json
[
  {
    "customerId": "C-001",
    "fullName": "An Nguyen",
    "email": "an@example.test"
  },
  {
    "customerId": "C-002",
    "fullName": "Binh Tran",
    "email": "binh@example.test"
  }
]
~~~

Java model ban đầu:

~~~java
public class Customer {
    private String customerId;
    private String fullName;
    private String email;

    // Getters and setters
}
~~~

Sau đó, hệ thống nguồn bổ sung field loyaltyTier:

~~~json
{
  "customerId": "C-003",
  "fullName": "Chi Le",
  "email": "chi@example.test",
  "loyaltyTier": "GOLD"
}
~~~

Ứng dụng nhận file vẫn dùng model Customer cũ. loyaltyTier là unknown field đối với model đó.

Những thay đổi schema thường gặp:

| Thay đổi | Ví dụ | Vấn đề có thể phát sinh |
|---|---|---|
| Thêm field | Thêm loyaltyTier | Consumer cũ có thể từ chối field lạ |
| Bỏ field | Không còn email | Consumer có thể nhận null hoặc thất bại nếu field bắt buộc |
| Đổi tên field | fullName thành displayName | Consumer có thể không tìm thấy property cũ |
| Đổi kiểu | age từ number thành string | Lỗi chuyển đổi |
| Đổi cardinality | address từ object thành array | Model cũ không ánh xạ được cấu trúc mới |
| Đổi ý nghĩa | amount chuyển từ gross sang net | JSON vẫn parse nhưng kết quả nghiệp vụ sai |
| Thêm enum value | Tier có PLATINUM | Enum cũ có thể ném lỗi |
| Thay đổi nullability | email từ bắt buộc thành nullable | Logic downstream có thể không còn đúng |

Schema evolution không chỉ là việc thêm hoặc bỏ property. Thay đổi kiểu, đơn vị đo, ý nghĩa nghiệp vụ và quy tắc validation cũng có thể làm dữ liệu cũ hoặc mới không còn tương thích.

## 2. Unknown field trong Jackson

Jackson ánh xạ property JSON sang field, setter, constructor parameter hoặc cấu trúc được annotation khai báo trong Java model. Nếu JSON chứa property không được nhận diện, Jackson có thể:

- Ném lỗi và dừng deserialization.
- Bỏ qua property lạ.
- Chuyển property vào một vùng chứa extension fields nếu model hỗ trợ.
- Dùng custom deserializer để áp dụng quy tắc riêng.

Mặc định của ObjectMapper phụ thuộc cấu hình và cách Spring Boot/Spring Batch tạo mapper. Trong Jackson, feature **FAIL_ON_UNKNOWN_PROPERTIES** quyết định có ném lỗi khi gặp property không được xử lý hay không. Không nên suy luận hành vi chỉ từ việc dùng JsonItemReader; hãy kiểm tra ObjectMapper thực tế được truyền vào JsonObjectReader.

Ví dụ JSON có field lạ:

~~~json
{
  "customerId": "C-003",
  "fullName": "Chi Le",
  "loyaltyTier": "GOLD"
}
~~~

Model chỉ có customerId và fullName. Nếu strict unknown-property handling được bật, Jackson có thể ném UnrecognizedPropertyException khi gặp loyaltyTier. Nếu lenient handling được bật, property đó được bỏ qua trong object Customer.

## 3. Strict mode: từ chối unknown field

Strict mode phù hợp khi hợp đồng dữ liệu yêu cầu producer và consumer phải đồng bộ schema. Một field mới có thể là dấu hiệu producer đã triển khai phiên bản không tương thích hoặc consumer đang nhận nhầm loại file.

Có thể cấu hình ObjectMapper:

~~~java
ObjectMapper objectMapper = new ObjectMapper();
objectMapper.enable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);
~~~

Hoặc cấu hình tường minh trong Spring:

~~~java
@Bean
ObjectMapper batchObjectMapper() {
    return JsonMapper.builder()
            .enable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES)
            .build();
}
~~~

Khi dùng strict mode:

- Field mới chưa được model hỗ trợ làm item lỗi khi deserialize.
- Job có thể thất bại nếu exception không được xử lý.
- Producer và consumer phát hiện sớm việc lệch schema.
- Một thay đổi additive ở producer cũng có thể làm consumer cũ ngừng chạy.

Strict mode hữu ích cho luồng dữ liệu nội bộ có quy trình release đồng bộ, file theo schema version cố định hoặc dữ liệu mà field lạ có thể biểu thị lỗi nghiêm trọng. Nó ít phù hợp hơn khi consumer cần tiếp nhận nhiều phiên bản producer độc lập và việc thêm field mới được xem là thay đổi tương thích.

## 4. Lenient mode: bỏ qua unknown field

Nếu producer thường xuyên bổ sung field tùy chọn và consumer chỉ cần một phần dữ liệu, có thể tắt FAIL_ON_UNKNOWN_PROPERTIES:

~~~java
@Bean
ObjectMapper batchObjectMapper() {
    return JsonMapper.builder()
            .disable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES)
            .build();
}
~~~

Khi đó, JSON có thể chứa field mà model chưa khai báo mà vẫn được ánh xạ:

~~~json
{
  "customerId": "C-003",
  "fullName": "Chi Le",
  "loyaltyTier": "GOLD",
  "preferredLanguage": "vi"
}
~~~

Object Customer vẫn nhận customerId và fullName; loyaltyTier và preferredLanguage không xuất hiện trong object nếu model không có nơi lưu chúng.

Lenient mode có lợi khi:

- Producer và consumer được triển khai độc lập.
- Field mới là optional và không ảnh hưởng logic consumer hiện tại.
- Consumer chỉ cần một tập property ổn định.
- Có yêu cầu tiếp tục xử lý file khi producer thêm metadata.

Nhưng bỏ qua unknown field cũng có rủi ro:

- Dữ liệu mới có thể bị mất mà không có cảnh báo.
- Consumer có thể không biết producer đã thay đổi hợp đồng.
- Một field quan trọng bị đặt sai tên có thể bị bỏ qua âm thầm.
- Job có thể hoàn tất nhưng output thiếu thông tin cần thiết.

Vì vậy, lenient không có nghĩa là mọi thay đổi schema đều an toàn. Hãy ghi nhận schema version, số field lạ hoặc metadata của nguồn nếu cần theo dõi tiến hóa schema.

## 5. Cấu hình JacksonJsonObjectReader cho JsonItemReader

Trong Spring Batch, **JsonItemReader<T>** đọc một JSON array và phát từng object thành item. Việc chuyển mỗi object JSON thành Java type được giao cho một **JsonObjectReader<T>**, chẳng hạn JacksonJsonObjectReader.

Ví dụ cấu hình:

~~~java
@Bean
ObjectMapper batchObjectMapper() {
    return JsonMapper.builder()
            .disable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES)
            .build();
}

@Bean
JacksonJsonObjectReader<Customer> customerObjectReader(
        ObjectMapper batchObjectMapper) {
    return new JacksonJsonObjectReader<>(
            Customer.class, batchObjectMapper);
}

@Bean
JsonItemReader<Customer> customerJsonReader(
        Resource inputResource,
        JacksonJsonObjectReader<Customer> customerObjectReader) {

    return new JsonItemReaderBuilder<Customer>()
            .name("customerJsonReader")
            .resource(inputResource)
            .jsonObjectReader(customerObjectReader)
            .saveState(true)
            .strict(true)
            .build();
}
~~~

Ở đây có hai loại strictness khác nhau:

- strict của ObjectMapper liên quan đến property JSON không có trong Java model.
- strict của JsonItemReaderBuilder liên quan đến việc kiểm tra resource đầu vào, chẳng hạn resource có tồn tại hay không theo hành vi của reader.

Không nhầm hai thiết lập này. Tắt FAIL_ON_UNKNOWN_PROPERTIES không có nghĩa reader chấp nhận file không tồn tại hoặc JSON sai cú pháp. Ngược lại, strict resource checking không quyết định Jackson xử lý unknown property ra sao.

API constructor và builder có thể thay đổi theo phiên bản Spring Batch/Jackson. Dùng đúng overload trong dependency của ứng dụng và truyền cùng ObjectMapper đã cấu hình; không tạo một mapper khác vô tình giữ strict defaults.

## 6. JsonItemReader mong đợi cấu trúc JSON nào?

JsonItemReader thường đọc một array gồm các object:

~~~json
[
  {
    "customerId": "C-001",
    "fullName": "An Nguyen"
  },
  {
    "customerId": "C-002",
    "fullName": "Binh Tran"
  }
]
~~~

Mỗi object trong array là một item được chuyển qua JsonObjectReader.

Nếu nguồn gửi envelope:

~~~json
{
  "schemaVersion": 2,
  "generatedAt": "2026-11-15T10:00:00Z",
  "data": [
    {
      "customerId": "C-001",
      "fullName": "An Nguyen"
    }
  ]
}
~~~

Đây không phải cùng cấu trúc với một top-level array. Không nên giả định JsonItemReader tự động tìm property data để đọc các object bên trong. Có thể dùng bước tiền xử lý, custom JsonObjectReader/ItemReader hoặc một reader chuyên biệt để xử lý envelope. Khi chọn giải pháp, cần giữ được schemaVersion và metadata của file thay vì bỏ chúng một cách vô tình.

## 7. Bỏ qua unknown field không đồng nghĩa bỏ qua mọi lỗi JSON

FAIL_ON_UNKNOWN_PROPERTIES chỉ xử lý property không được model nhận diện. Nó không làm Jackson bỏ qua mọi lỗi deserialize.

Những lỗi vẫn có thể xảy ra:

- JSON không hợp lệ cú pháp, chẳng hạn thiếu dấu ngoặc hoặc dấu phẩy.
- Kiểu dữ liệu không tương thích, chẳng hạn object nhận một array.
- Chuỗi ngày không parse được.
- Giá trị bắt buộc bị thiếu khi constructor hoặc validation yêu cầu.
- Enum chứa giá trị không được hỗ trợ.
- Custom deserializer ném exception.
- JSON token có cấu trúc không phù hợp với Java model.

Ví dụ:

~~~json
{
  "customerId": "C-003",
  "age": "not-a-number"
}
~~~

Nếu age là Integer, việc tắt FAIL_ON_UNKNOWN_PROPERTIES không giúp chuyển chuỗi not-a-number thành số. Đây là lỗi type conversion.

Phân loại exception rõ ràng giúp quyết định lỗi nào được skip và lỗi nào phải dừng Job. Không nên cấu hình skip rộng mọi JacksonException hoặc Exception chỉ để Job tiếp tục, vì JSON hỏng cú pháp hoặc sai kiểu có thể làm dữ liệu đầu ra không đáng tin cậy.

## 8. Giữ lại unknown field thay vì bỏ mất

Trong một số hệ thống, consumer cần tiếp nhận field mới ngay cả khi chưa hiểu ý nghĩa của chúng. Bỏ qua field giúp parse thành công nhưng làm mất dữ liệu nếu object được serialize hoặc ghi tiếp sang hệ thống khác.

Có thể dùng @JsonAnySetter để thu thập property không được khai báo vào một Map:

~~~java
public class Customer {

    private String customerId;
    private String fullName;
    private Map<String, JsonNode> additionalProperties = new HashMap<>();

    // Getters and setters for known fields

    @JsonAnySetter
    public void addAdditionalProperty(String name, JsonNode value) {
        additionalProperties.put(name, value);
    }

    @JsonAnyGetter
    public Map<String, JsonNode> getAdditionalProperties() {
        return additionalProperties;
    }
}
~~~

Với @JsonAnySetter, Jackson chuyển những property chưa được ánh xạ vào phương thức nhận tên và giá trị. Dùng JsonNode giúp giữ cấu trúc value linh hoạt nếu field lạ có thể là string, number, object hoặc array.

Có thể lưu extension fields vào JSON column, raw payload hoặc audit record để xử lý về sau. Cần đặt giới hạn kích thước và kiểm soát tên key; không nên cho phép extension field ghi đè property nghiệp vụ hoặc điều khiển tên cột SQL.

Một lựa chọn khác là đọc mỗi item thành JsonNode trước, sau đó lấy các field đã biết và giữ lại phần còn lại. Cách này tăng tính linh hoạt nhưng làm ứng dụng chịu trách nhiệm nhiều hơn về type checking và validation.

## 9. Thêm field mới: backward compatibility

Một thay đổi additive thường tương thích ngược nếu field mới là tùy chọn và consumer cũ có thể bỏ qua nó.

Ví dụ version 1:

~~~json
{
  "customerId": "C-001",
  "fullName": "An Nguyen"
}
~~~

Version 2 thêm optional field:

~~~json
{
  "customerId": "C-001",
  "fullName": "An Nguyen",
  "preferredLanguage": "vi"
}
~~~

Consumer cũ có thể tiếp tục đọc nếu unknown field được bỏ qua. Consumer mới có thể đọc cả file cũ và file mới nếu preferredLanguage được xem là optional hoặc có default phù hợp.

Để giữ backward compatibility:

- Thêm field mới dưới dạng optional nếu có thể.
- Xác định default có ý nghĩa khi field vắng mặt.
- Không đổi ý nghĩa của field cũ.
- Không đổi kiểu dữ liệu hiện hữu mà không có kế hoạch migration.
- Kiểm tra consumer cũ có bật strict unknown-property handling hay không.

Việc thêm field không tự động luôn tương thích. Nếu field mới bắt buộc để tính kết quả đúng, consumer cũ bỏ qua nó có thể tạo dữ liệu sai dù parse thành công.

## 10. Bỏ field và thay đổi nullability

Nếu producer ngừng gửi một field, consumer có thể nhận null hoặc giá trị mặc định tùy kiểu property và cách binding.

Ví dụ JSON cũ có email:

~~~json
{
  "customerId": "C-001",
  "email": "an@example.test"
}
~~~

JSON mới bỏ email:

~~~json
{
  "customerId": "C-001"
}
~~~

Nếu model dùng String email, giá trị thường là null khi không có property, trừ khi constructor, initializer hoặc custom deserializer áp dụng logic khác. Nếu model dùng primitive int, property thiếu có thể giữ giá trị mặc định của Java là 0; giá trị 0 có thể bị hiểu nhầm là dữ liệu thực.

Với field có thể thiếu:

- Dùng wrapper type như Integer thay vì int nếu cần phân biệt missing/null với zero.
- Validate trước khi processor dùng giá trị.
- Đặt default rõ ràng nếu default phản ánh đúng nghiệp vụ.
- Phân biệt property không có trong JSON với property có giá trị null nếu nghiệp vụ cần.

Nếu field từng bắt buộc nay trở thành tùy chọn, cập nhật validation và downstream logic. Không chỉ thay kiểu Java rồi cho rằng mọi luồng đã tương thích.

## 11. Đổi tên field bằng JsonAlias

Đổi tên property là thay đổi dễ gây mất tương thích. Ví dụ producer đổi fullName thành displayName.

Có thể hỗ trợ cả tên cũ và mới bằng @JsonAlias:

~~~java
public class Customer {

    private String customerId;

    @JsonAlias({"fullName", "displayName"})
    private String name;

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }
}
~~~

Trong cấu hình phù hợp, Jackson có thể nhận fullName hoặc displayName để điền property name. Khi serialize, tên property đầu ra vẫn theo cấu hình JsonProperty/property chính, không phải tất cả alias đều được xuất ra.

Khi cả hai tên cùng xuất hiện trong một object, cần xác định hành vi mong muốn và kiểm thử. Không nên để producer gửi cả fullName lẫn displayName với giá trị khác nhau mà không có quy tắc ưu tiên.

Một chiến lược an toàn:

1. Consumer hỗ trợ đồng thời tên cũ và tên mới.
2. Producer bắt đầu gửi tên mới, có thể giữ tên cũ trong giai đoạn chuyển tiếp nếu hợp đồng yêu cầu.
3. Theo dõi việc sử dụng tên cũ.
4. Chỉ loại alias cũ khi mọi producer đã chuyển đổi và dữ liệu tồn lưu không còn cần hỗ trợ.

## 12. Thay đổi kiểu dữ liệu

Đổi kiểu của field thường khó tương thích hơn thêm field. Ví dụ amount trước đây là JSON number:

~~~json
{
  "amount": 125000.50
}
~~~

Sau đó producer gửi amount dưới dạng string:

~~~json
{
  "amount": "125000.50"
}
~~~

Jackson có thể hỗ trợ một số coercion tùy cấu hình, nhưng không nên dựa vào chuyển đổi ngầm nếu hợp đồng yêu cầu kiểu rõ ràng. Dữ liệu như "unknown", chuỗi rỗng hoặc định dạng số có dấu phẩy có thể gây lỗi hoặc kết quả không mong muốn.

Các lựa chọn:

- Giữ kiểu JSON ổn định trong contract.
- Dùng custom deserializer nếu phải hỗ trợ cả hai định dạng.
- Đọc vào JsonNode/String trung gian rồi parse theo quy tắc được định nghĩa.
- Version hóa schema khi thay đổi không thể hỗ trợ an toàn trong cùng model.

Ví dụ custom deserializer cần xử lý rõ null, number token và string token; từ chối các giá trị không hợp lệ thay vì tự thay bằng 0. Với tiền tệ, dùng BigDecimal và kiểm soát scale/rounding.

## 13. Enum mới và giá trị chưa biết

Giả sử model cũ có:

~~~java
public enum LoyaltyTier {
    STANDARD,
    SILVER,
    GOLD
}
~~~

Producer bổ sung PLATINUM. Khi Jackson gặp PLATINUM, deserialization có thể thất bại vì enum Java hiện tại không có constant tương ứng.

Có thể thêm enum default:

~~~java
public enum LoyaltyTier {
    STANDARD,
    SILVER,
    GOLD,
    @JsonEnumDefaultValue
    UNKNOWN
}
~~~

Và cấu hình:

~~~java
objectMapper.enable(
        DeserializationFeature.READ_UNKNOWN_ENUM_VALUES_USING_DEFAULT_VALUE);
~~~

Khi gặp giá trị enum không biết, Jackson có thể dùng constant được đánh dấu JsonEnumDefaultValue. Một lựa chọn khác là READ_UNKNOWN_ENUM_VALUES_AS_NULL, nhưng khi dùng null cần validation downstream rõ ràng.

Không nên ánh xạ mọi enum lạ thành một trạng thái hợp lệ như STANDARD. Điều đó có thể thay đổi ý nghĩa nghiệp vụ. UNKNOWN chỉ phù hợp nếu consumer có thể giữ trạng thái chưa biết và xử lý an toàn, chẳng hạn ghi nhận rồi chờ cập nhật.

## 14. Schema version trong payload

Với hệ thống có nhiều producer hoặc thay đổi không tương thích, nên đưa schema version vào envelope:

~~~json
{
  "schemaVersion": 2,
  "generatedAt": "2026-11-15T10:00:00Z",
  "data": [
    {
      "customerId": "C-001",
      "displayName": "An Nguyen"
    }
  ]
}
~~~

schemaVersion giúp consumer xác định cấu trúc payload và chọn mapping tương ứng. Nó không thay thế validation, nhưng tránh phải suy đoán version dựa trên việc field nào tình cờ xuất hiện.

Có thể định nghĩa các model theo version:

~~~java
public record CustomerV1(
        String customerId,
        String fullName) {
}

public record CustomerV2(
        String customerId,
        String displayName,
        String preferredLanguage) {
}
~~~

Sau khi đọc envelope, một adapter có thể chuyển CustomerV1 hoặc CustomerV2 về model nội bộ ổn định:

~~~java
public record CustomerRecord(
        String customerId,
        String name,
        String preferredLanguage) {
}
~~~

Điểm chuyển đổi version là nơi áp dụng default, rename, type conversion và validation. Processor phía sau có thể chỉ làm việc với CustomerRecord, không phải biết mọi phiên bản schema bên ngoài.

## 15. Xử lý nhiều schema version trong Spring Batch

JsonItemReader tiêu chuẩn đọc array theo một JsonObjectReader với target type xác định. Nếu mỗi file chỉ có một schema version, có thể chọn reader/model tương ứng theo JobParameters hoặc metadata của file.

Ví dụ cấu hình reader cho version đã biết:

~~~java
@Bean
@StepScope
JsonItemReader<CustomerV2> customerV2Reader(
        @Value("#{jobParameters['input.file']}") String inputFile,
        JacksonJsonObjectReader<CustomerV2> objectReader) {

    return new JsonItemReaderBuilder<CustomerV2>()
            .name("customerV2Reader")
            .resource(new FileSystemResource(inputFile))
            .jsonObjectReader(objectReader)
            .saveState(true)
            .build();
}
~~~

Nếu file có thể thuộc nhiều version, có thể dùng Step chuẩn bị để đọc schemaVersion, xác thực rồi chọn flow/Step phù hợp. Một cách khác là dùng custom reader đọc envelope và dispatch từng object theo version.

Không nên dùng một ObjectMapper lenient cho mọi version nếu các version có thay đổi ý nghĩa hoặc kiểu dữ liệu không tương thích. Bỏ qua unknown field chỉ giải quyết property dư; nó không chuyển đổi đúng một schema khác về model nội bộ.

## 16. Chuẩn hóa về canonical model

Một chiến lược hữu ích là giữ model nội bộ ổn định và tạo adapter cho từng schema bên ngoài:

~~~text
JSON schema v1 ----> V1 DTO ----\
                                \
JSON schema v2 ----> V2 DTO -----> Version adapter
                                  |
JSON schema v3 ----> V3 DTO ----/
                                  |
                                  v
                           Canonical model
                                  |
                                  v
                        ItemProcessor / Writer
~~~

Canonical model biểu diễn khái niệm nghiệp vụ mà Job cần, không nhất thiết trùng hoàn toàn với JSON của producer.

Lợi ích:

- Thay đổi bên ngoài không lan khắp processor và writer.
- Có thể hỗ trợ nhiều schema version đồng thời.
- Mapping và default được kiểm thử riêng.
- Dễ lưu source version để audit.
- Có thể loại bỏ alias cũ theo kế hoạch.

Không nên biến canonical model thành một DTO chứa mọi field của mọi producer. Chỉ giữ dữ liệu cần thiết cho nghiệp vụ và lưu extension payload riêng nếu cần bảo toàn thông tin ngoài hợp đồng hiện tại.

## 17. Phân biệt missing, null và default

Ba trạng thái này có thể mang ý nghĩa khác nhau:

~~~json
{}
~~~

Property không xuất hiện.

~~~json
{"email": null}
~~~

Property xuất hiện với giá trị null.

~~~json
{"email": ""}
~~~

Property xuất hiện với chuỗi rỗng.

Trong nhiều model Java đơn giản, hai trường hợp đầu có thể đều trở thành null, còn chuỗi rỗng vẫn là "". Nếu nghiệp vụ cần phân biệt missing với explicit null, cần dùng cấu trúc trung gian như JsonNode, custom deserializer hoặc wrapper biểu diễn presence.

Không nên áp dụng default một cách máy móc. Ví dụ, missing quantity không nhất thiết có nghĩa quantity bằng 0; missing status không nhất thiết có nghĩa ACTIVE. Default phải được quy định trong contract hoặc adapter version.

## 18. Unknown field và validation nghiệp vụ

Deserialization thành công chỉ chứng minh JSON có thể được chuyển thành Java object. Nó không chứng minh object hợp lệ theo nghiệp vụ.

Ví dụ object parse thành công nhưng:

- customerId rỗng.
- amount âm.
- currency không được hỗ trợ.
- ngày hiệu lực nằm ngoài phạm vi.
- hai field mới và cũ mâu thuẫn nhau.

Hãy tách các tầng:

1. **JSON syntax:** payload có cú pháp JSON hợp lệ không?
2. **Deserialization:** token có thể ánh xạ sang Java model không?
3. **Schema validation:** property, kiểu và cấu trúc có phù hợp version không?
4. **Business validation:** dữ liệu có đáp ứng quy tắc nghiệp vụ không?
5. **Persistence validation:** dữ liệu có đáp ứng constraint của hệ thống đích không?

Một unknown field có thể được bỏ qua ở tầng deserialization nhưng vẫn cần cảnh báo ở tầng contract monitoring. Ngược lại, một property đã biết có thể parse thành công nhưng vẫn không hợp lệ về nghiệp vụ.

## 19. Kết hợp unknown field với skip policy

Nếu strict mode được bật, unknown field có thể gây lỗi khi đọc item. Có thể cấu hình skip exception cụ thể nếu hợp đồng nghiệp vụ cho phép loại item đó. Tuy nhiên, cần cân nhắc liệu một file có nhiều unknown fields có phải dấu hiệu schema version sai hay không.

Ví dụ:

~~~java
return new StepBuilder("importCustomersStep", jobRepository)
        .<Customer, Customer>chunk(100, transactionManager)
        .reader(customerJsonReader)
        .processor(customerProcessor)
        .writer(customerWriter)
        .faultTolerant()
        .skip(UnrecognizedPropertyException.class)
        .skipLimit(10)
        .build();
~~~

Đây là minh họa phân loại exception; exception thực tế có thể được bọc bởi Spring Batch hoặc JsonObjectReader tùy phiên bản và đường gọi. Hãy kiểm tra root cause trong test trước khi khai báo skip rule.

Skip một item có unknown property đồng nghĩa loại toàn bộ object khỏi luồng xử lý, không phải chỉ bỏ riêng field đó. Nếu các field còn lại vẫn hợp lệ và muốn tiếp tục, lenient mapping hoặc extension-field capture có thể phù hợp hơn.

Không nên skip lỗi unknown field ở mức rộng nếu field mới có thể chứa dữ liệu quan trọng hoặc cho thấy producer gửi nhầm schema. Hãy đặt skip limit thấp và ghi nhận file/version/field lỗi nếu chọn cách này.

## 20. Theo dõi schema drift

Khi consumer bật lenient mode, Job có thể tiếp tục chạy dù producer thêm property. Điều này tốt cho tính sẵn sàng nhưng làm thay đổi schema dễ bị bỏ qua. Nên có quan sát để biết payload thực tế đang tiến hóa ra sao.

Có thể ghi nhận:

- schemaVersion từ envelope.
- Producer name hoặc source system.
- File ID, batch ID và thời điểm tạo.
- Số lượng record theo version.
- Tên unknown field và tần suất xuất hiện.
- Số item deserialize lỗi theo exception type.
- Số item thiếu field quan trọng.
- Số enum value chưa được nhận diện.

Không nhất thiết log raw payload. Tên field, version và số lượng thường đủ để phát hiện drift; raw data nên được lưu ở vùng bảo vệ nếu cần điều tra.

Có thể đặt cảnh báo khi:

- schemaVersion mới xuất hiện.
- Unknown field xuất hiện lần đầu.
- Một field bắt buộc đột ngột bị thiếu.
- Tỷ lệ deserialize failure tăng bất thường.
- Một enum value chưa biết xuất hiện.

Lenient mode nên đi cùng schema monitoring nếu dữ liệu có ý nghĩa nghiệp vụ hoặc audit.

## 21. Kiểm thử schema evolution

Không chỉ test với JSON của version hiện tại. Nên giữ fixture đại diện cho các version mà consumer cam kết hỗ trợ.

Test matrix gợi ý:

| Trường hợp | Hành vi mong đợi |
|---|---|
| JSON version cũ, đủ field | Parse và mapping thành công |
| JSON có thêm optional unknown field | Strict fail hoặc lenient thành công theo policy |
| JSON có unknown field cần bảo toàn | Extension map giữ đúng tên và value |
| JSON thiếu optional field | Default/null theo contract |
| JSON thiếu required field | Validation/deserialization thất bại |
| Field đổi tên | Alias hoặc version adapter ánh xạ đúng |
| Field đổi kiểu | Chuyển đổi tường minh hoặc fail rõ ràng |
| Enum mới | UNKNOWN/default hoặc fail theo contract |
| Explicit null | Xử lý khác missing nếu nghiệp vụ yêu cầu |
| JSON syntax sai | Item/Step thất bại theo policy |
| Version không hỗ trợ | Dừng sớm với thông báo rõ |

Ví dụ unit test cho lenient unknown field:

~~~java
@Test
void ignoresUnknownPropertyWhenLenientModeIsConfigured()
        throws Exception {

    ObjectMapper mapper = JsonMapper.builder()
            .disable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES)
            .build();

    Customer customer = mapper.readValue("""
            {
              "customerId": "C-003",
              "fullName": "Chi Le",
              "loyaltyTier": "GOLD"
            }
            """, Customer.class);

    assertEquals("C-003", customer.getCustomerId());
    assertEquals("Chi Le", customer.getFullName());
}
~~~

Test strict mode:

~~~java
@Test
void rejectsUnknownPropertyWhenStrictModeIsConfigured() {
    ObjectMapper mapper = JsonMapper.builder()
            .enable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES)
            .build();

    assertThrows(UnrecognizedPropertyException.class, () ->
            mapper.readValue("""
                    {
                      "customerId": "C-003",
                      "loyaltyTier": "GOLD"
                    }
                    """, Customer.class));
}
~~~

Ví dụ test trên giả định model Customer không có loyaltyTier, không có @JsonAnySetter và mapper không đăng ký handler khác cho unknown properties. Với Spring Boot, hãy test chính ObjectMapper bean được ứng dụng sử dụng, vì auto-configuration hoặc module có thể thay đổi hành vi.

## 22. Kiểm thử tích hợp với Spring Batch

Unit test ObjectMapper xác nhận mapping, nhưng chưa kiểm tra JsonItemReader, chunk, skip policy, metadata hoặc restart. Cần có Step integration test với resource fixture.

Ví dụ khung:

~~~java
@SpringBatchTest
@SpringJUnitConfig(JsonImportTestConfiguration.class)
class JsonSchemaEvolutionStepTest {

    @Autowired
    JobLauncherTestUtils jobLauncherTestUtils;

    @Autowired
    CustomerRepository customerRepository;

    @Test
    void importsOldAndExtendedPayload() throws Exception {
        JobParameters parameters = new JobParametersBuilder()
                .addString("input.file", "src/test/resources/customers-v1-plus-field.json", true)
                .toJobParameters();

        JobExecution execution = jobLauncherTestUtils.launchJob(parameters);

        assertEquals(BatchStatus.COMPLETED, execution.getStatus());
        assertEquals(2, customerRepository.count());
    }
}
~~~

Fixture cần có một array hợp lệ với các object thuộc schema mà consumer hỗ trợ. Ngoài trạng thái Job, hãy kiểm tra giá trị đã ghi để bảo đảm field cũ không bị mất hoặc bị gán sai.

Với restart, giữ cùng identifying JobParameters và JobRepository qua hai lần launch. Xác nhận file/schema version vẫn ổn định, checkpoint được khôi phục và writer không tạo duplicate.

## 23. Quản lý version và rollout producer/consumer

Một thay đổi schema an toàn thường cần kế hoạch rollout:

1. Xác định thay đổi additive hay breaking.
2. Cập nhật consumer để đọc cả cấu trúc cũ và mới.
3. Triển khai consumer tương thích trước nếu producer có thể phát hành độc lập.
4. Cập nhật producer theo contract mới.
5. Theo dõi version, unknown field và lỗi mapping.
6. Loại bỏ alias hoặc model cũ sau khi hết thời gian tương thích.

Với breaking change, cân nhắc version hóa rõ ràng thay vì cố ép một model xử lý mọi dạng. Có thể lưu schemaVersion trong JobParameters hoặc metadata của JobExecution để audit; nếu version quyết định cấu trúc dữ liệu, nó cần được cố định trong suốt restart.

Không thay đổi mapping giữa một lần chạy và lần restart theo cách khiến cùng checkpoint được diễn giải bằng schema khác. Nếu cần xử lý lại bằng schema mới, cân nhắc tạo JobInstance mới và đối soát dữ liệu đã commit.

## 24. Các lỗi thường gặp

**Tắt FAIL_ON_UNKNOWN_PROPERTIES mà không theo dõi drift:** Job có thể hoàn tất nhưng field mới bị bỏ qua âm thầm. Ghi nhận schema version và unknown field khi cần.

**Nhầm unknown field với sai kiểu dữ liệu:** bỏ qua property lạ không xử lý được property đã biết nhưng có token sai kiểu.

**Cho rằng strict của JsonItemReader là strict unknown field:** resource strictness và Jackson unknown-property handling là hai cấu hình riêng.

**Bỏ qua field cần thiết cho nghiệp vụ:** parse thành công không chứng minh output đúng. Xác định field nào optional và field nào bắt buộc.

**Dùng primitive cho field có thể thiếu:** giá trị mặc định 0/false có thể bị hiểu nhầm là dữ liệu thật. Dùng wrapper và validation khi cần.

**Đổi tên property mà không alias/version adapter:** dữ liệu cũ có thể không còn được ánh xạ.

**Ánh xạ enum mới thành một trạng thái hợp lệ sai nghĩa:** dùng UNKNOWN hoặc fail rõ ràng, không tự thay bằng trạng thái mặc định có ý nghĩa nghiệp vụ khác.

**Bật lenient cho mọi schema version:** thay đổi kiểu hoặc cấu trúc không tương thích vẫn có thể gây lỗi hoặc sai dữ liệu.

**Skip mọi Jackson exception:** có thể bỏ qua cả JSON hỏng cú pháp hoặc lỗi dữ liệu quan trọng. Phân loại exception và đặt giới hạn.

**Không giữ fixture version cũ:** thay đổi producer có thể làm consumer mất khả năng đọc file tồn lưu.

**Không cố định schema version khi restart:** cùng JobInstance có thể đọc lại dữ liệu bằng mapping khác với lần chạy đầu.

## Kết luận

Unknown field xuất hiện khi JSON chứa property mà Java model hiện tại chưa ánh xạ. Với Spring Batch, JsonItemReader đọc từng object còn JacksonJsonObjectReader và ObjectMapper quyết định cách deserialize property đó. Bật FAIL_ON_UNKNOWN_PROPERTIES để phát hiện schema drift nghiêm ngặt; tắt nó khi field mới là optional và consumer có thể bỏ qua an toàn; dùng @JsonAnySetter hoặc JsonNode nếu cần bảo toàn extension fields. Schema evolution còn bao gồm field bị thiếu, đổi tên, đổi kiểu, enum mới, nullability và thay đổi ý nghĩa nghiệp vụ. Hãy version hóa breaking change, chuẩn hóa nhiều phiên bản về canonical model, theo dõi schema drift và kiểm thử fixture cũ/mới ở cả tầng mapper lẫn Step integration. Thành công về parsing chỉ là bước đầu; dữ liệu sau khi processor và writer xử lý vẫn phải đáp ứng contract nghiệp vụ.
