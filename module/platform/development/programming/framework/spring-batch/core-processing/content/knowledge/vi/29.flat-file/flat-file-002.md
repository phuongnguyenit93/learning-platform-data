# LineMapper và FieldSetMapper

Trong Spring Batch, khi đọc file văn bản bằng FlatFileItemReader, mỗi dòng được chuyển thành một object để các bước tiếp theo xử lý. LineMapper chịu trách nhiệm ánh xạ một dòng văn bản thành một item. Trong cách triển khai phổ biến, DefaultLineMapper phối hợp hai thành phần: LineTokenizer tách dòng thành các trường và FieldSetMapper chuyển các trường đó thành object Java.

Hai interface này có trách nhiệm khác nhau:

- LineMapper<T> nhận toàn bộ dòng cùng số dòng và trả về một item kiểu T.
- FieldSetMapper<T> nhận FieldSet đã được tokenizer tạo ra và ánh xạ các trường thành object kiểu T.

Pipeline thường gặp là:

FlatFileItemReader → LineMapper → LineTokenizer → FieldSet → FieldSetMapper → domain/input object.

Tách các trách nhiệm này giúp xử lý nhiều định dạng file, kiểm soát tên cột, chuyển đổi kiểu dữ liệu, báo lỗi theo dòng và tái sử dụng logic mapping. Khi hiểu rõ ranh giới của từng thành phần, ta có thể chọn tokenizer có sẵn hoặc viết mapper tùy chỉnh mà không phải tự xây toàn bộ reader.

## 1. Vai trò trong pipeline đọc file

FlatFileItemReader đọc file theo từng dòng. Với mỗi dòng dữ liệu, reader gọi LineMapper.mapLine(line, lineNumber). Mapper trả về object để reader đưa vào chunk.

Sơ đồ xử lý:

~~~mermaid
flowchart TD
    A[FlatFileItemReader] --> B[Đọc một dòng]
    B --> C[LineMapper.mapLine]
    C --> D[LineTokenizer]
    D --> E[FieldSet]
    E --> F[FieldSetMapper.mapFieldSet]
    F --> G[Input object]
    G --> H[ItemProcessor]
    H --> I[ItemWriter]
~~~

Ví dụ file CSV:

~~~text
orderId,customerId,amount,orderDate
ORD-1001,CUS-01,125.50,2026-11-14
ORD-1002,CUS-02,89.90,2026-11-14
~~~

Với dòng dữ liệu thứ hai, tokenizer tách thành bốn trường. FieldSetMapper đọc các trường theo tên và tạo một OrderInput. Sau đó processor có thể kiểm tra nghiệp vụ, chuyển đổi thành entity hoặc loại item; writer chịu trách nhiệm ghi kết quả.

Không nên đưa toàn bộ logic nghiệp vụ vào LineMapper. Nhiệm vụ của nó là chuyển biểu diễn văn bản thành dữ liệu có cấu trúc. Các quyết định nghiệp vụ như đơn hàng có được phép nhập, khách hàng có đang hoạt động hoặc hạn mức có hợp lệ thường thuộc processor hoặc service nghiệp vụ.

## 2. LineMapper<T>

LineMapper<T> là interface nhận một dòng và số dòng trong file:

~~~java
public interface LineMapper<T> {
    T mapLine(String line, int lineNumber) throws Exception;
}
~~~

Số dòng giúp mapper hoặc exception cung cấp ngữ cảnh khi dữ liệu sai. FlatFileItemReader sử dụng mapper để tạo item từ từng dòng mà reader coi là dữ liệu.

Spring Batch cung cấp DefaultLineMapper<T> để kết hợp tokenizer với field set mapper. Khi định dạng dòng đơn giản, đây thường là lựa chọn nên dùng. Khi file có nhiều loại record, quy tắc phân tích đặc biệt hoặc cấu trúc không phù hợp tokenizer có sẵn, có thể triển khai LineMapper<T> tùy chỉnh.

Ví dụ mapper tùy chỉnh tối giản:

~~~java
public class OrderLineMapper implements LineMapper<OrderInput> {

    @Override
    public OrderInput mapLine(String line, int lineNumber) {
        String[] parts = line.split(",", -1);
        if (parts.length != 4) {
            throw new IllegalArgumentException(
                    "Expected 4 columns at line " + lineNumber);
        }

        return new OrderInput(
                parts[0].trim(),
                parts[1].trim(),
                new BigDecimal(parts[2].trim()),
                LocalDate.parse(parts[3].trim()));
    }
}
~~~

Đây chỉ là ví dụ cho thấy mapper nhận được line number. String.split đơn giản không phải parser CSV đầy đủ: nó không xử lý đúng mọi trường hợp dấu phẩy nằm trong dấu ngoặc kép, quote escape hoặc multiline field. Với CSV thực tế, nên dùng DelimitedLineTokenizer hoặc parser có semantics phù hợp thay vì tự tách chuỗi.

## 3. DefaultLineMapper<T>

DefaultLineMapper<T> là triển khai chuẩn kết hợp một LineTokenizer và một FieldSetMapper<T>. Nó thực hiện hai bước:

1. Gọi tokenizer để chuyển dòng thành FieldSet.
2. Gọi field set mapper để chuyển FieldSet thành object.

Ví dụ cấu hình:

~~~java
@Bean
LineMapper<OrderInput> orderLineMapper(
        LineTokenizer orderLineTokenizer,
        FieldSetMapper<OrderInput> orderFieldSetMapper) throws Exception {

    DefaultLineMapper<OrderInput> mapper = new DefaultLineMapper<>();
    mapper.setLineTokenizer(orderLineTokenizer);
    mapper.setFieldSetMapper(orderFieldSetMapper);
    mapper.afterPropertiesSet();
    return mapper;
}
~~~

afterPropertiesSet() kiểm tra các dependency bắt buộc của mapper đã được cấu hình. Khi dùng Spring bean, có thể để container quản lý lifecycle hoặc gọi phương thức khởi tạo theo cách cấu hình phù hợp.

Việc tách tokenizer và field set mapper giúp thay đổi định dạng đầu vào mà không phải viết lại logic tạo object nếu hợp đồng trường vẫn tương thích. Ngược lại, có thể thay mapper để thay đổi cách chuyển kiểu hoặc cấu trúc object mà không phải viết lại quy tắc tokenization.

## 4. LineTokenizer và FieldSet

LineTokenizer phân tích một dòng thành FieldSet. FieldSet là abstraction tương tự một hàng dữ liệu có tên trường và giá trị đã được tách. Nó cung cấp các phương thức đọc theo vị trí hoặc theo tên, bao gồm chuyển đổi sang kiểu số, boolean và ngày tháng.

Một số phương thức thường dùng:

| Phương thức | Kết quả |
|---|---|
| readString("orderId") | Chuỗi |
| readInt("quantity") | Số nguyên |
| readLong("customerNumber") | Số nguyên dài |
| readBigDecimal("amount") | Số thập phân chính xác |
| readBoolean("active") | Boolean |
| readDate("orderDate", "yyyy-MM-dd") | java.util.Date theo pattern |

Đọc theo tên thường dễ bảo trì hơn đọc theo index:

~~~java
String orderId = fieldSet.readString("orderId");
BigDecimal amount = fieldSet.readBigDecimal("amount");
~~~

Khi đọc theo vị trí, code phụ thuộc thứ tự cột trong file. Nếu file đổi thứ tự cột nhưng tokenizer vẫn tạo FieldSet theo cùng một tên mapping, code đọc theo tên ít bị ảnh hưởng hơn.

Tokenizer cũng chịu trách nhiệm phát hiện số lượng token không phù hợp theo cấu hình strictness. Khi cấu trúc dòng không đúng, nó có thể ném exception thay vì tạo một FieldSet thiếu trường. Hãy quyết định rõ cách xử lý dòng thiếu/thừa cột; không nên âm thầm coi chuỗi rỗng là dữ liệu hợp lệ nếu nghiệp vụ yêu cầu trường bắt buộc.

## 5. DelimitedLineTokenizer cho CSV hoặc file phân tách

DelimitedLineTokenizer tách dòng theo delimiter, thường là dấu phẩy. Có thể khai báo tên các cột để FieldSet mang tên rõ ràng.

Ví dụ cấu hình:

~~~java
@Bean
LineTokenizer orderLineTokenizer() {
    DelimitedLineTokenizer tokenizer = new DelimitedLineTokenizer();
    tokenizer.setDelimiter(",");
    tokenizer.setNames(
            "orderId",
            "customerId",
            "amount",
            "orderDate");
    tokenizer.setQuoteCharacter('"');
    tokenizer.setStrict(true);
    return tokenizer;
}
~~~

Với dòng:

~~~text
ORD-1003,CUS-03,125.50,2026-11-14
~~~

FieldSet sẽ có các trường orderId, customerId, amount và orderDate.

Nếu giá trị chứa delimiter, ví dụ tên khách hàng là Nguyen, An, cần dùng quy tắc quote:

~~~text
ORD-1004,CUS-04,"Nguyen, An",125.50
~~~

Trong ví dụ này, tokenizer cần được cấu hình phù hợp với định dạng file để dấu phẩy bên trong trường có quote không bị coi là dấu phân cách. Với file CSV có escape rule, newline trong quoted field hoặc dialect đặc biệt, hãy xác nhận parser đang dùng hỗ trợ đúng định dạng được tạo bởi hệ thống nguồn.

setNames(...) gắn tên cho các token theo thứ tự. Nếu file có header, việc bỏ qua header là trách nhiệm của reader, không phải tokenizer tự động suy ra tên cột từ dòng đầu.

## 6. FixedLengthTokenizer cho file độ dài cố định

Không phải file nào cũng phân tách bằng dấu phẩy. Một số hệ thống xuất file fixed-width, trong đó mỗi trường chiếm một khoảng ký tự xác định.

Ví dụ:

~~~text
ORD0000123CUS0000450000012550
~~~

Giả sử định dạng:

- Ký tự 1–10: order ID.
- Ký tự 11–20: customer ID.
- Ký tự 21–30: amount theo đơn vị cent.

Có thể dùng FixedLengthTokenizer:

~~~java
@Bean
LineTokenizer fixedWidthOrderTokenizer() {
    FixedLengthTokenizer tokenizer = new FixedLengthTokenizer();
    tokenizer.setColumns(
            new Range(1, 10),
            new Range(11, 20),
            new Range(21, 30));
    tokenizer.setNames("orderId", "customerId", "amountInCents");
    tokenizer.setStrict(true);
    return tokenizer;
}
~~~

Các khoảng Range được đánh số theo vị trí ký tự của dòng. Cần xác nhận quy ước vị trí của file nguồn và độ dài thực tế của mỗi record. Nếu file có khoảng trống, trường optional hoặc record có độ dài khác nhau, cần cấu hình ranges và strictness theo đúng đặc tả.

Sau tokenization, FieldSetMapper có thể chuyển amountInCents thành BigDecimal bằng cách chia cho 100. Việc chuyển đổi đơn vị nên được đặt ở mapper nếu đó là chuyển đổi biểu diễn file sang kiểu dữ liệu chuẩn; quy tắc nghiệp vụ về mức tiền hợp lệ thuộc bước validation tiếp theo.

## 7. FieldSetMapper<T>

FieldSetMapper<T> là interface chuyển một FieldSet thành object:

~~~java
public interface FieldSetMapper<T> {
    T mapFieldSet(FieldSet fieldSet) throws BindException;
}
~~~

Nó không cần biết dòng ban đầu được tách bằng dấu phẩy hay fixed-width. Nó làm việc với các trường đã được tokenizer đặt tên. Vì vậy, cùng một mapper có thể được dùng với nhiều định dạng file nếu chúng tạo ra cùng tên trường và cùng semantics dữ liệu.

Một custom mapper thường thực hiện:

1. Đọc các giá trị theo tên trường.
2. Chuyển kiểu dữ liệu.
3. Chuẩn hóa biểu diễn, ví dụ trim chuỗi hoặc chuyển mã trạng thái.
4. Tạo object input.
5. Báo lỗi binding nếu giá trị không thể chuyển đổi.

Ví dụ:

~~~java
@Bean
FieldSetMapper<OrderInput> orderFieldSetMapper() {
    DateTimeFormatter dateFormat =
            DateTimeFormatter.ofPattern("yyyy-MM-dd");

    return fieldSet -> {
        String orderId = fieldSet.readString("orderId").trim();
        String customerId = fieldSet.readString("customerId").trim();
        BigDecimal amount = fieldSet.readBigDecimal("amount");
        LocalDate orderDate = LocalDate.parse(
                fieldSet.readString("orderDate").trim(),
                dateFormat);

        if (orderId.isEmpty()) {
            throw new IllegalArgumentException("orderId is required");
        }

        return new OrderInput(
                orderId,
                customerId,
                amount,
                orderDate);
    };
}
~~~

Trong ứng dụng thực tế, có thể dùng exception binding phù hợp để báo trường nào lỗi và vì sao. Không nên dùng một exception tổng quát cho mọi trường hợp nếu cần phân loại lỗi để retry, skip hoặc reject.

## 8. BeanWrapperFieldSetMapper

Nếu object đích là JavaBean có constructor rỗng và setter, Spring Batch cung cấp BeanWrapperFieldSetMapper<T> để bind giá trị của FieldSet vào property theo tên.

Ví dụ JavaBean:

~~~java
public class CustomerInput {

    private String customerId;
    private String customerName;
    private Integer age;

    public CustomerInput() {
    }

    public String getCustomerId() {
        return customerId;
    }

    public void setCustomerId(String customerId) {
        this.customerId = customerId;
    }

    public String getCustomerName() {
        return customerName;
    }

    public void setCustomerName(String customerName) {
        this.customerName = customerName;
    }

    public Integer getAge() {
        return age;
    }

    public void setAge(Integer age) {
        this.age = age;
    }
}
~~~

Cấu hình mapper:

~~~java
@Bean
FieldSetMapper<CustomerInput> customerFieldSetMapper() throws Exception {
    BeanWrapperFieldSetMapper<CustomerInput> mapper =
            new BeanWrapperFieldSetMapper<>();
    mapper.setTargetType(CustomerInput.class);
    mapper.setStrict(true);
    mapper.afterPropertiesSet();
    return mapper;
}
~~~

Tên field trong FieldSet phải khớp với property JavaBean, chẳng hạn customerId và customerName. Mapper dùng cơ chế bean property binding để chuyển giá trị sang kiểu property khi có converter/editor phù hợp.

BeanWrapperFieldSetMapper thuận tiện cho object đơn giản. Với record Java bất biến, constructor nhiều tham số, mapping lồng nhau phức tạp hoặc quy tắc chuyển đổi đặc thù, custom FieldSetMapper thường rõ ràng và dễ kiểm soát hơn.

## 9. Chuyển đổi kiểu và định dạng ngày tháng

File thường lưu mọi giá trị dưới dạng text, trong khi object Java cần kiểu dữ liệu cụ thể. Cần xác định định dạng của từng trường thay vì dựa vào locale hoặc cấu hình máy chạy.

| Trường file | Biểu diễn | Kiểu trong object |
|---|---|---|
| orderId | ORD-1001 | String |
| quantity | 12 | int hoặc Integer |
| amount | 1250.75 | BigDecimal |
| orderDate | 2026-11-14 | LocalDate |
| active | Y hoặc N | boolean |

Với ngày tháng, nên dùng formatter có pattern tường minh:

~~~java
private static final DateTimeFormatter ORDER_DATE_FORMAT =
        DateTimeFormatter.ofPattern("uuuu-MM-dd");

LocalDate orderDate = LocalDate.parse(
        fieldSet.readString("orderDate").trim(),
        ORDER_DATE_FORMAT);
~~~

Với số tiền, dùng BigDecimal thay vì double để tránh sai số biểu diễn nhị phân. Nếu file dùng dấu phẩy làm dấu thập phân và dấu chấm làm phân cách hàng nghìn, phải cấu hình locale/NumberFormat phù hợp hoặc tự parse theo format hợp đồng của file. Không dựa vào locale mặc định của server.

Với giá trị boolean dạng Y/N, có thể chuyển rõ ràng:

~~~java
private boolean parseYesNo(String value) {
    return switch (value.trim().toUpperCase(Locale.ROOT)) {
        case "Y" -> true;
        case "N" -> false;
        default -> throw new IllegalArgumentException(
                "Expected Y or N but got: " + value);
    };
}
~~~

Mapper nên phân biệt trường rỗng, null, giá trị mặc định và giá trị không hợp lệ. Nếu trường bắt buộc bị rỗng, báo lỗi rõ thay vì tự gán 0 hoặc chuỗi rỗng khiến dữ liệu sai đi sâu vào pipeline.

## 10. Mapping nested object và cấu trúc phức tạp

Một dòng file phẳng có thể biểu diễn nhiều thuộc tính của object lồng nhau. Ví dụ:

~~~text
orderId,customerId,customerName,shippingCity,shippingPostalCode
ORD-1001,CUS-01,An Nguyen,Da Nang,550000
~~~

Custom mapper có thể tạo object lồng nhau:

~~~java
return fieldSet -> {
    Customer customer = new Customer(
            fieldSet.readString("customerId"),
            fieldSet.readString("customerName"));

    Address address = new Address(
            fieldSet.readString("shippingCity"),
            fieldSet.readString("shippingPostalCode"));

    return new OrderInput(
            fieldSet.readString("orderId"),
            customer,
            address);
};
~~~

Đây là mapping cấu trúc từ file sang object. Những quy tắc như địa chỉ có thuộc vùng giao hàng hay khách hàng có được phép đặt đơn vẫn nên được xử lý trong processor/service nghiệp vụ.

Nếu file có danh sách con lặp lại trong một dòng hoặc cấu trúc phân cấp nhiều record, một FieldSetMapper đơn giản có thể không đủ. Khi đó, có thể cần custom LineMapper, reader chuyên biệt hoặc một bước parse trước để tạo record chuẩn.

## 11. File có nhiều loại record

Một file có thể chứa nhiều loại dòng, ví dụ:

~~~text
HDR,ORDERS,2026-11-14
CUS,CUS-01,An Nguyen
ORD,ORD-1001,CUS-01,125.50
TRL,1,125.50
~~~

Ký tự đầu dòng xác định loại record. Có thể dùng PatternMatchingCompositeLineTokenizer để chọn tokenizer theo pattern, sau đó dùng mapper tương ứng; hoặc PatternMatchingCompositeLineMapper để kết hợp cả tokenizer và FieldSetMapper theo từng loại record.

Ví dụ cấu hình composite mapper cho một kiểu output chung:

~~~java
@Bean
LineMapper<ImportRecord> importRecordLineMapper() throws Exception {
    PatternMatchingCompositeLineMapper<ImportRecord> mapper =
            new PatternMatchingCompositeLineMapper<>();

    Map<String, LineTokenizer> tokenizers = new HashMap<>();
    tokenizers.put("HDR*", headerTokenizer());
    tokenizers.put("CUS*", customerTokenizer());
    tokenizers.put("ORD*", orderTokenizer());
    tokenizers.put("TRL*", trailerTokenizer());
    mapper.setTokenizers(tokenizers);

    Map<String, FieldSetMapper<ImportRecord>> fieldSetMappers =
            new HashMap<>();
    fieldSetMappers.put("HDR*", headerFieldSetMapper());
    fieldSetMappers.put("CUS*", customerFieldSetMapper());
    fieldSetMappers.put("ORD*", orderFieldSetMapper());
    fieldSetMappers.put("TRL*", trailerFieldSetMapper());
    mapper.setFieldSetMappers(fieldSetMappers);

    return mapper;
}
~~~

ImportRecord là interface hoặc kiểu cha chung cho các loại record. Các mapper cụ thể tạo HeaderRecord, CustomerRecord, OrderRecord hoặc TrailerRecord.

Khi dùng pattern, cần bảo đảm pattern cụ thể hơn được ưu tiên đúng và mọi loại record hợp lệ đều có tokenizer/mapper tương ứng. Dòng không khớp pattern cần trở thành lỗi dữ liệu có thể truy vết, không nên bị gán nhầm sang một mapper mặc định nếu điều đó che giấu record type không hợp lệ.

## 12. Gắn LineMapper vào FlatFileItemReader

Sau khi cấu hình mapper, gắn nó vào reader:

~~~java
@Bean
FlatFileItemReader<OrderInput> orderFileReader(
        Resource inputFile,
        LineMapper<OrderInput> orderLineMapper) {

    return new FlatFileItemReaderBuilder<OrderInput>()
            .name("orderFileReader")
            .resource(inputFile)
            .linesToSkip(1)
            .skippedLinesCallback(line ->
                    log.info("Skipped header: {}", line))
            .lineMapper(orderLineMapper)
            .strict(true)
            .saveState(true)
            .build();
}
~~~

linesToSkip(1) bỏ qua một dòng đầu, thường là header. skippedLinesCallback cho phép ghi nhận dòng bị bỏ qua. lineMapper chuyển mỗi dòng dữ liệu thành OrderInput. saveState(true) cho phép reader lưu vị trí đọc để hỗ trợ restart khi nguồn và cấu hình ổn định.

Trong job cần truyền đường dẫn file theo JobParameters, thường khai báo reader là @StepScope và bind giá trị từ jobParameters. Không giữ resource hoặc file path thay đổi trong singleton field nếu nhiều execution có thể chạy đồng thời.

## 13. Header, blank line và comment

Header không nhất thiết phải được đưa qua LineMapper. Nếu file có một dòng tiêu đề cố định, reader có thể bỏ qua bằng linesToSkip. Nếu cần kiểm tra header, dùng skippedLinesCallback để xác nhận tên cột hoặc version file.

Blank line và comment cần có quy tắc rõ ràng:

- Bỏ qua dòng trống nếu đặc tả file cho phép.
- Xử lý comment theo prefix đã định nghĩa.
- Không bỏ qua dòng lỗi chỉ vì mapper không parse được.
- Nếu header không đúng version, nên fail sớm thay vì tiếp tục mapping theo vị trí cột sai.

Nếu cần bỏ qua dòng theo điều kiện phức tạp, có thể dùng RecordSeparatorPolicy, LineCallbackHandler cho header hoặc custom reader/mapper phù hợp. Cần phân biệt dòng bị loại có chủ đích với record dữ liệu bị lỗi.

## 14. Lỗi mapping và thông tin dòng

Lỗi trong tokenizer hoặc FieldSetMapper thường xảy ra trước khi item được chuyển tới processor. Reader có thể báo lỗi parse, số lượng token không đúng hoặc lỗi chuyển đổi kiểu.

Một lỗi parse cần đủ ngữ cảnh:

- Tên file hoặc nguồn dữ liệu.
- Số dòng.
- Nội dung dòng hoặc reference tới raw record.
- Tên trường bị lỗi.
- Giá trị đầu vào và định dạng mong đợi.
- Loại lỗi và nguyên nhân.

Spring Batch có FlatFileParseException để mang thông tin dòng và nội dung đầu vào trong các trường hợp parse file. Khi bắt lỗi ở tầng vận hành, tránh chỉ ghi Invalid input; hãy giữ line number và source reference để tìm lại record.

Không nên bắt mọi exception trong LineMapper rồi trả về null. Trả null thường làm reader coi như không có item, khiến dữ liệu biến mất mà skip count/reject tracking không phản ánh đúng lỗi. Hãy ném exception có ý nghĩa để step áp dụng retry/skip/fail policy đã cấu hình.

## 15. LineMapper và skip policy

Lỗi tokenizer hoặc FieldSetMapper là lỗi ở giai đoạn read. Nếu ứng dụng cho phép bỏ qua một số dòng dữ liệu sai, có thể cấu hình skip exception phù hợp:

~~~java
return new StepBuilder("importOrdersStep", jobRepository)
        .<OrderInput, Order>chunk(100, transactionManager)
        .reader(orderFileReader)
        .processor(orderProcessor)
        .writer(orderWriter)
        .faultTolerant()
        .skip(FlatFileParseException.class)
        .skipLimit(10)
        .listener(importSkipListener)
        .build();
~~~

Chỉ skip parse error khi nghiệp vụ cho phép output thiếu record đó và ứng dụng ghi nhận được dòng bị reject. Với file đối soát, thanh toán hoặc sổ cái cần đầy đủ tuyệt đối, một dòng không parse được có thể phải làm step thất bại để tránh công bố kết quả thiếu.

Lỗi kết nối nguồn file, file không tồn tại hoặc lỗi cấu hình không nên bị coi là lỗi item để skip. Phân loại exception theo bản chất: lỗi riêng của dòng, lỗi hạ tầng hay lỗi định dạng toàn file.

## 16. Tái sử dụng tokenizer và mapper

Tokenizer thường có thể được cấu hình như bean dùng chung nếu sau khi khởi tạo nó chỉ đọc và không giữ state theo từng dòng. Tương tự, FieldSetMapper stateless có thể được chia sẻ.

Không lưu currentLine, currentFieldSet, số thứ tự record hoặc item hiện tại trong field mutable của singleton mapper. Nếu nhiều reader hoặc step chạy đồng thời, state đó có thể bị trộn.

Ví dụ mapper stateless:

~~~java
public class CustomerFieldSetMapper
        implements FieldSetMapper<CustomerInput> {

    @Override
    public CustomerInput mapFieldSet(FieldSet fieldSet) {
        return new CustomerInput(
                fieldSet.readString("customerId").trim(),
                fieldSet.readString("customerName").trim(),
                fieldSet.readInt("age"));
    }
}
~~~

Mapper chỉ đọc FieldSet được truyền vào và tạo object mới. Nếu cần cấu hình khác nhau theo file hoặc step, dùng bean scope/late binding phù hợp thay vì thay đổi mutable fields trên một mapper singleton trong lúc job chạy.

## 17. Kiểm thử LineMapper và FieldSetMapper

Nên kiểm thử tokenizer, mapper và reader ở các mức khác nhau:

1. Tokenizer test: delimiter, quote, field names, fixed ranges và số lượng cột.
2. FieldSetMapper test: chuyển đổi kiểu, trim, trường rỗng, ngày tháng, enum và lỗi binding.
3. LineMapper test: ghép tokenizer và mapper, xác nhận line mapping cho một record hợp lệ.
4. Reader integration test: đọc file nhỏ, bỏ qua header, xác nhận số item và thứ tự dữ liệu.
5. Malformed input test: dòng thiếu/thừa cột, số tiền sai, ngày sai định dạng và record type không nhận diện.
6. Line number test: xác nhận lỗi có số dòng và source location chính xác.
7. Skip test: parse error được skip theo policy và được lưu trong reject store nếu nghiệp vụ cho phép.
8. Restart test: reader tiếp tục từ checkpoint mà không bỏ sót hoặc đọc trùng dòng đã commit.
9. Concurrent execution test: nhiều step đọc các file khác nhau không chia sẻ mutable mapper state.
10. Header/version test: header không tương thích phải được phát hiện trước khi mapping dữ liệu sai.

Ví dụ kiểm thử mapper qua một dòng:

~~~java
@Test
void mapsDelimitedOrderLine() throws Exception {
    LineTokenizer tokenizer = orderLineTokenizer();
    FieldSetMapper<OrderInput> fieldSetMapper =
            orderFieldSetMapper();

    DefaultLineMapper<OrderInput> mapper = new DefaultLineMapper<>();
    mapper.setLineTokenizer(tokenizer);
    mapper.setFieldSetMapper(fieldSetMapper);
    mapper.afterPropertiesSet();

    OrderInput result = mapper.mapLine(
            "ORD-1001,CUS-01,125.50,2026-11-14",
            2);

    assertEquals("ORD-1001", result.orderId());
    assertEquals("CUS-01", result.customerId());
    assertEquals(new BigDecimal("125.50"), result.amount());
    assertEquals(LocalDate.of(2026, 11, 14), result.orderDate());
}
~~~

Ví dụ giả định OrderInput là record có các accessor tương ứng và mapper đã được cấu hình date format. Test này kiểm tra mapping một dòng; cần thêm reader integration test để kiểm tra header, file resource, line number và restart behavior.

## 18. Những lỗi thường gặp

**Nhầm LineMapper với FieldSetMapper.** LineMapper nhận dòng văn bản và line number; FieldSetMapper nhận các trường đã tokenized. Giữ mỗi thành phần đúng trách nhiệm.

**Tự split CSV bằng String.split.** Cách này không xử lý đầy đủ quoted delimiter và escape. Dùng DelimitedLineTokenizer hoặc parser phù hợp.

**Đọc FieldSet theo index ở mọi nơi.** Code dễ sai khi thứ tự cột thay đổi. Đặt tên trường và đọc theo tên khi có thể.

**Không khai báo tên cột hoặc range rõ ràng.** Mapping phụ thuộc vị trí khó bảo trì. Khai báo names/columns theo đặc tả file.

**Để BeanWrapperFieldSetMapper bind sai property.** Tên token không khớp JavaBean property hoặc kiểu dữ liệu không chuyển được. Kiểm tra target type, setter và converter.

**Dùng locale mặc định để parse tiền/ngày.** Kết quả có thể khác giữa môi trường. Định nghĩa format tường minh.

**Bắt exception rồi trả null.** Record lỗi biến mất mà không được ghi nhận. Ném exception có ngữ cảnh để skip/reject/fail policy xử lý.

**Đưa validation nghiệp vụ vào mapper.** Mapper trở nên khó tái sử dụng. Giữ mapping ở reader và quy tắc nghiệp vụ trong processor/service.

**Dùng mapper singleton có mutable state.** Nhiều step có thể trộn dữ liệu. Giữ mapper stateless hoặc tạo instance theo execution.

**Bỏ qua header mà không kiểm tra version.** File thay đổi cột có thể bị map sai nhưng không báo lỗi. Xác thực header trước khi đọc dữ liệu.

## 19. Quy trình xây dựng mapping cho file

Khi tích hợp một định dạng file mới, có thể thực hiện theo trình tự:

1. Đọc đặc tả file: delimiter, quote, encoding, header, line ending, fixed ranges và record types.
2. Xác định object input chuẩn mà processor cần nhận.
3. Chọn tokenizer phù hợp: delimited, fixed-length hoặc composite.
4. Đặt tên trường để mapping không phụ thuộc index nếu có thể.
5. Viết FieldSetMapper hoặc dùng BeanWrapperFieldSetMapper cho JavaBean đơn giản.
6. Chuyển kiểu với format tường minh và kiểm soát giá trị rỗng.
7. Kết hợp bằng DefaultLineMapper hoặc composite mapper.
8. Gắn LineMapper vào FlatFileItemReader và cấu hình header, resource, state.
9. Phân loại lỗi parse theo read/skip/fail policy và ghi source location.
10. Kiểm thử dữ liệu hợp lệ, malformed input, restart và các file version khác nhau.

## Kết luận

LineMapper chuyển một dòng văn bản thành item; FieldSetMapper chuyển FieldSet đã được tokenizer tạo ra thành object Java. Với DefaultLineMapper, LineTokenizer tách dòng thành trường, còn FieldSetMapper chịu trách nhiệm chuyển kiểu và tạo object. DelimitedLineTokenizer phù hợp với file phân tách; FixedLengthTokenizer phù hợp với file fixed-width; composite mapper có thể xử lý nhiều loại record trong cùng file.

Hãy đặt tên trường rõ ràng, parse ngày/số theo format tường minh, giữ mapper stateless và để lỗi parse mang theo số dòng cùng source reference. Gắn mapper vào FlatFileItemReader, xác định cách xử lý header và malformed line, rồi kiểm thử từ mapping đơn lẻ đến reader/restart integration. Khi phân tách rõ parsing, mapping và validation nghiệp vụ, pipeline flat-file dễ bảo trì và có thể truy vết dữ liệu lỗi chính xác.
