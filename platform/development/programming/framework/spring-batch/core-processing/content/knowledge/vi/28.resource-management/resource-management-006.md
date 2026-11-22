# Encoding file

Trong Spring Batch, file reader và writer làm việc với hai dạng dữ liệu khác nhau: file lưu **byte**, còn phần lớn API xử lý record làm việc với **ký tự** và String. Encoding xác định cách chuyển đổi giữa byte và ký tự. Nếu chọn sai encoding, một file vẫn có thể mở và đọc được nhưng nội dung tiếng Việt, ký tự đặc biệt hoặc dữ liệu nhiều ngôn ngữ bị sai.

Trong chương Resource management, encoding là một phần của cấu hình resource đầu vào và đầu ra. Cần xác định charset của file nguồn, cấu hình rõ charset cho reader/writer, xử lý BOM nếu có, và kiểm thử dữ liệu sau khi chuyển đổi. Không nên phụ thuộc vào charset mặc định của máy chạy vì môi trường development, container và production có thể khác nhau.

## 1. Encoding là gì?

File văn bản lưu các byte. Ứng dụng cần biết quy tắc ánh xạ byte thành ký tự để hiểu nội dung. Quy tắc đó là character encoding, thường được gọi ngắn là encoding hoặc charset.

Ví dụ, cùng một ký tự tiếng Việt có thể được biểu diễn bằng một chuỗi byte khác nhau tùy encoding. Nếu file được tạo bằng UTF-8 nhưng reader giải mã bằng Windows-1252, các ký tự có dấu có thể hiển thị thành chuỗi ký tự sai.

~~~text
File bytes
    |
    v
Charset decoder
    |
    v
Java characters / String
    |
    v
FlatFileItemReader parser
    |
    v
Item object
~~~

Khi ghi file, chiều chuyển đổi ngược lại:

~~~text
Item object
    |
    v
LineAggregator
    |
    v
Java String
    |
    v
Charset encoder
    |
    v
File bytes
~~~

Encoding không phải định dạng record. CSV, fixed-width, delimiter, quote và line separator mô tả cách chia record/field. UTF-8, UTF-16 và Windows-1252 mô tả cách mã hóa ký tự thành byte.

## 2. Các charset thường gặp

Một số charset có thể gặp khi tích hợp hệ thống:

| Charset | Đặc điểm | Tình huống thường gặp |
| --- | --- | --- |
| UTF-8 | Unicode, độ dài byte thay đổi từ 1 đến 4 byte cho mỗi code point | Trao đổi file hiện đại, API và hệ thống đa ngôn ngữ |
| UTF-16LE / UTF-16BE | Unicode dùng đơn vị mã 16 bit, có thứ tự byte little-endian hoặc big-endian | Một số hệ thống Windows, export hoặc ứng dụng legacy |
| ISO-8859-1 | Bộ ký tự 8 bit giới hạn, không bao phủ tiếng Việt đầy đủ | Hệ thống cũ chủ yếu dùng ký tự Tây Âu |
| Windows-1252 | Bộ ký tự 8 bit thường gặp trên Windows ở một số ứng dụng legacy | File CSV cũ tạo từ phần mềm Windows |
| Shift_JIS | Encoding legacy thường dùng cho tiếng Nhật | Trao đổi dữ liệu với hệ thống Nhật cũ |

Với file mới, UTF-8 thường là lựa chọn phù hợp vì hỗ trợ nhiều ngôn ngữ và được dùng rộng rãi. Tuy nhiên, không được tự giả định file legacy là UTF-8. Hãy xác nhận contract của hệ thống tạo file.

Tên charset cần được JVM nhận diện. Có thể kiểm tra bằng Java:

~~~java
Charset charset = Charset.forName("UTF-8");
boolean supported = Charset.isSupported("Windows-1252");
~~~

Nên dùng tên charset chuẩn hoặc hằng số trong StandardCharsets khi có sẵn. Ví dụ:

~~~java
StandardCharsets.UTF_8
StandardCharsets.UTF_16LE
StandardCharsets.ISO_8859_1
~~~

## 3. Vì sao phải khai báo encoding tường minh?

Nếu không cấu hình, reader/writer có thể dùng charset mặc định của JVM hoặc giá trị mặc định của implementation. Charset mặc định có thể phụ thuộc hệ điều hành, locale, runtime và cấu hình môi trường.

Một file chạy đúng trên laptop có thể bị lỗi khi chuyển sang Linux container hoặc máy chủ khác:

~~~text
Developer workstation
  default charset = Windows-1252
  -> đọc file legacy đúng

Production container
  default charset = UTF-8
  -> cùng file có thể được giải mã khác
~~~

Hãy khai báo encoding theo hợp đồng dữ liệu, không theo máy chạy:

- Reader phải giải mã đúng charset mà hệ thống nguồn dùng.
- Writer phải mã hóa đúng charset mà hệ thống nhận yêu cầu.
- Cấu hình phải giống nhau giữa local, test, staging và production.
- Charset nên được quản lý trong cấu hình ứng dụng hoặc metadata của file nếu nhiều nguồn dùng encoding khác nhau.

Không dùng một charset toàn cục cho mọi file nếu các đối tác có contract khác nhau.

## 4. Cấu hình encoding cho FlatFileItemReader

Spring Batch cung cấp FlatFileItemReader để đọc từng dòng và ánh xạ thành item. Có thể khai báo encoding bằng builder:

~~~java
@Bean
@StepScope
public FlatFileItemReader<OrderInput> orderReader(
        @Value("#{jobParameters['inputFile']}") Resource inputFile) {

    return new FlatFileItemReaderBuilder<OrderInput>()
            .name("orderReader")
            .resource(inputFile)
            .encoding("UTF-8")
            .delimited()
            .names("orderId", "customerName", "amount")
            .targetType(OrderInput.class)
            .linesToSkip(1)
            .saveState(true)
            .build();
}
~~~

Trong ví dụ:

- Resource xác định file đầu vào.
- encoding("UTF-8") chỉ định cách giải mã byte thành ký tự.
- delimited() cấu hình cách tách các field.
- linesToSkip(1) bỏ qua dòng header.
- saveState(true) cho phép reader lưu trạng thái để restart.

Encoding được áp dụng trước khi parser xử lý từng dòng. Nếu charset sai, LineTokenizer hoặc FieldSetMapper có thể nhận String đã sai ngay từ đầu. Sửa mapping field sẽ không khôi phục được ký tự đã giải mã sai.

### Cấu hình bằng setter

Nếu tạo reader trực tiếp thay vì builder, có thể cấu hình:

~~~java
FlatFileItemReader<OrderInput> reader = new FlatFileItemReader<>();
reader.setName("orderReader");
reader.setResource(inputFile);
reader.setEncoding("UTF-8");
reader.setLineMapper(orderLineMapper);
reader.setSaveState(true);
~~~

Không cấu hình encoding sau khi reader đã mở resource. Hãy thiết lập đầy đủ trước khi Step bắt đầu.

## 5. Cấu hình encoding cho FlatFileItemWriter

Khi ghi file, FlatFileItemWriter chuyển item thành dòng String rồi mã hóa String thành byte. Hãy cấu hình encoding đầu ra theo yêu cầu của hệ thống nhận:

~~~java
@Bean
public FlatFileItemWriter<Order> orderWriter(
        Resource outputFile) {

    return new FlatFileItemWriterBuilder<Order>()
            .name("orderWriter")
            .resource(outputFile)
            .encoding("UTF-8")
            .lineAggregator(order ->
                    order.getOrderId() + ","
                    + order.getCustomerName() + ","
                    + order.getAmount())
            .headerCallback(writer ->
                    writer.write("orderId,customerName,amount"))
            .shouldDeleteIfExists(true)
            .build();
}
~~~

Trong ví dụ, lineAggregator tạo một dòng String. Writer mã hóa dòng đó thành byte theo UTF-8. Header cũng được ghi bằng cùng encoding.

Nếu hệ thống đích yêu cầu Windows-1252 hoặc một charset legacy khác, cần cấu hình đúng charset đó và kiểm tra các ký tự đầu ra có biểu diễn được hay không.

### Encoding không thay thế escaping CSV

Encoding chỉ quyết định cách mã hóa ký tự. Nó không tự xử lý dấu phẩy, dấu nháy kép hoặc xuống dòng bên trong field.

Ví dụ tên khách hàng có dấu phẩy:

~~~text
orderId,customerName,amount
1001,"Nguyen, An",250000
~~~

LineAggregator phải tạo CSV hợp lệ theo quy tắc quote/escape. Một dòng UTF-8 đúng charset nhưng không escape dấu phẩy vẫn có thể bị parser phía nhận đọc sai cột.

## 6. Encoding, delimiter và line ending là ba vấn đề khác nhau

Khi tích hợp file, cần phân biệt:

| Thuộc tính | Ví dụ | Vai trò |
| --- | --- | --- |
| Encoding | UTF-8 | Chuyển byte thành ký tự |
| Delimiter | Dấu phẩy, tab, dấu chấm phẩy | Phân tách field trong record |
| Quote/escape | Dấu nháy kép | Bảo vệ delimiter hoặc ký tự đặc biệt trong field |
| Line separator | LF hoặc CRLF | Phân tách các record |
| Record layout | CSV hoặc fixed-width | Xác định cấu trúc một record |

File có thể dùng UTF-8 nhưng line ending là CRLF. File khác có thể dùng Windows-1252 với line ending LF. Không nên suy ra encoding từ line ending hoặc delimiter.

FlatFileItemReader xử lý dòng theo cơ chế đọc text của Java/Spring Batch. Nếu file có record nhiều dòng được quote theo quy tắc CSV, cần cấu hình RecordSeparatorPolicy phù hợp để reader không coi mọi newline là kết thúc record.

## 7. UTF-8 và ký tự tiếng Việt

UTF-8 hỗ trợ đầy đủ ký tự tiếng Việt có dấu. Ví dụ một số chuỗi:

~~~text
Nguyễn Văn An
Đơn hàng mới
Thành phố Hồ Chí Minh
~~~

Khi đọc file UTF-8 bằng reader cấu hình UTF-8, parser nhận được String Unicode tương ứng. Khi ghi file UTF-8, writer chuyển String thành byte UTF-8.

Không nên chuyển String sang byte bằng charset mặc định ở một phần khác của ứng dụng rồi lại giải mã bằng UTF-8. Ví dụ sau có thể làm mất dữ liệu:

~~~java
byte[] bytes = value.getBytes();
String restored = new String(bytes, StandardCharsets.UTF_8);
~~~

getBytes() không chỉ định charset sẽ dùng default charset của JVM. Hãy chỉ định cùng charset ở cả hai chiều nếu thật sự cần chuyển byte:

~~~java
byte[] bytes = value.getBytes(StandardCharsets.UTF_8);
String restored = new String(bytes, StandardCharsets.UTF_8);
~~~

Trong luồng FlatFileItemReader/Writer, nên để Spring Batch thực hiện chuyển đổi thông qua cấu hình encoding thay vì tự chuyển byte/String trong từng processor.

## 8. Xử lý UTF-8 BOM

Một số công cụ xuất file UTF-8 thêm byte order mark (BOM) ở đầu file. BOM UTF-8 thường được biểu diễn bằng ba byte EF BB BF và có thể được giải mã thành ký tự U+FEFF ở đầu chuỗi.

Nếu reader không loại bỏ BOM, field đầu tiên có thể nhận thêm ký tự vô hình. Ví dụ:

~~~text
Expected header: orderId,customerName,amount
Actual first field may begin with: U+FEFF + orderId
~~~

Điều này có thể làm header mapping, so sánh tên cột hoặc validation thất bại dù file nhìn bằng text editor có vẻ bình thường.

Có thể xử lý BOM ở lớp đọc dòng. Ví dụ dùng LineMapper bọc quanh mapper chính:

~~~java
DefaultLineMapper<OrderInput> delegate = new DefaultLineMapper<>();
delegate.setLineTokenizer(orderTokenizer);
delegate.setFieldSetMapper(orderFieldSetMapper);

LineMapper<OrderInput> bomAwareMapper = (line, lineNumber) -> {
    String normalizedLine = line;
    if (lineNumber == 1 && line.startsWith("\uFEFF")) {
        normalizedLine = line.substring(1);
    }
    return delegate.mapLine(normalizedLine, lineNumber);
};
~~~

Đây là cách xử lý ở tầng dòng nếu BOM đã được decoder chuyển thành U+FEFF. Một lựa chọn khác là dùng resource/input stream wrapper hoặc thư viện BOM-aware để loại bỏ BOM trước khi giải mã.

Chỉ loại bỏ BOM ở đầu file. Không xóa mọi ký tự U+FEFF ở mọi vị trí vì ký tự này có thể xuất hiện trong dữ liệu thực tế. Kiểm thử cả file có BOM và không có BOM.

## 9. UTF-16 và thứ tự byte

UTF-16 dùng các code unit 16 bit và có biến thể little-endian hoặc big-endian. Một file UTF-16 có thể chứa BOM để chỉ thứ tự byte. Nếu biết rõ contract, hãy khai báo charset tương ứng, ví dụ UTF-16LE hoặc UTF-16BE.

Không nên chọn UTF-16 chung chung khi hệ thống yêu cầu một thứ tự byte cụ thể mà không kiểm tra BOM và hành vi decoder. Nếu file có BOM nhưng cấu hình reader không xử lý theo cách mong muốn, ký tự BOM có thể xuất hiện trong dữ liệu hoặc nội dung bị giải mã sai.

Ví dụ:

~~~java
return new FlatFileItemReaderBuilder<CustomerInput>()
        .name("customerReader")
        .resource(inputFile)
        .encoding("UTF-16LE")
        .delimited()
        .names("customerId", "customerName")
        .targetType(CustomerInput.class)
        .build();
~~~

Charset phải khớp với cách hệ thống tạo file. Không dùng UTF-16LE chỉ vì file được tạo trên Windows; cần xác nhận định dạng thực tế.

## 10. Encoding không tương thích và ký tự bị lỗi

Một charset có thể không biểu diễn được mọi ký tự trong String. Ví dụ Windows-1252 không thể biểu diễn toàn bộ ký tự tiếng Việt hoặc ký tự thuộc nhiều hệ chữ khác.

Khi ghi một ký tự không biểu diễn được, encoder có thể thay bằng ký tự thay thế tùy cấu hình. Khi đọc byte không hợp lệ, decoder có thể thay thế hoặc báo lỗi tùy cách khởi tạo. Nếu không phát hiện, file đầu ra có thể chứa dấu hỏi hoặc ký tự thay thế mà Job vẫn hoàn tất.

Các biểu hiện thường gặp:

- Ký tự tiếng Việt thành dấu hỏi.
- Một ký tự hiển thị thành chuỗi mojibake.
- Field đầu tiên có ký tự lạ do BOM.
- Parser báo lỗi vì ký tự điều khiển hoặc byte không hợp lệ.
- File đầu ra không thể được hệ thống nhận giải mã.

### Kiểm tra charset có hỗ trợ ký tự hay không

Java có thể kiểm tra khả năng encode:

~~~java
CharsetEncoder encoder =
        Charset.forName("Windows-1252").newEncoder();

boolean canEncode = encoder.canEncode("Nguyen Van An");
boolean canEncodeVietnamese =
        encoder.canEncode("Nguyễn Văn An");
~~~

Nếu canEncode trả false, charset đó không thể biểu diễn đầy đủ chuỗi. Không nên âm thầm thay thế ký tự nếu dữ liệu nghiệp vụ cần giữ nguyên.

### Xử lý nghiêm ngặt dữ liệu lỗi

Khi cần phát hiện byte không hợp lệ thay vì âm thầm thay thế, có thể dùng CharsetDecoder với CodingErrorAction.REPORT trong một input layer tùy chỉnh:

~~~java
CharsetDecoder decoder = StandardCharsets.UTF_8.newDecoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);

Reader reader = new InputStreamReader(
        inputStream,
        decoder);
~~~

Với FlatFileItemReader, có thể cung cấp BufferedReaderFactory tùy chỉnh để kiểm soát cách tạo Reader. Cần quản lý đóng stream đúng lifecycle và chuyển IOException thành lỗi đọc phù hợp. Cấu hình encoding của builder thông thường không cung cấp đầy đủ mọi tùy chọn CodingErrorAction.

Không nên dùng chế độ thay thế mặc định nếu yêu cầu dữ liệu đòi hỏi phát hiện và từ chối byte sai. Ngược lại, với nguồn legacy có contract cho phép thay thế một số ký tự, hãy ghi rõ quy tắc và kiểm thử.

## 11. Chuẩn hóa Unicode

Hai chuỗi có thể nhìn giống nhau nhưng có biểu diễn Unicode khác nhau. Ví dụ một ký tự có dấu có thể được biểu diễn bằng:

- Một code point dựng sẵn.
- Một ký tự cơ sở cộng với combining mark.

UTF-8 có thể mã hóa cả hai biểu diễn. Encoding không tự chuẩn hóa Unicode.

Nếu hệ thống so sánh chuỗi, tìm kiếm hoặc dùng tên làm khóa, hai biểu diễn khác nhau có thể không bằng nhau dù hiển thị giống nhau. Có thể chuẩn hóa theo Unicode NFC khi contract nghiệp vụ yêu cầu:

~~~java
String normalized = Normalizer.normalize(
        input,
        Normalizer.Form.NFC);
~~~

Không chuẩn hóa tùy tiện nếu dữ liệu cần giữ nguyên byte hoặc có yêu cầu đối soát chính xác với nguồn. Chuẩn hóa là bước xử lý nội dung, khác với giải mã encoding.

## 12. Encoding và restart

Reader có thể lưu checkpoint để restart. Tuy nhiên, checkpoint chỉ có ý nghĩa khi resource và cách giải mã vẫn nhất quán.

Nếu lần chạy đầu đọc file bằng UTF-8 nhưng lần restart đổi sang Windows-1252, cùng vị trí byte có thể tạo ra String khác. Nếu file bị thay thế hoặc encoding thay đổi, reader có thể tiếp tục sai dữ liệu.

Nên giữ ổn định:

- Resource hoặc input file ID.
- Charset.
- Quy tắc BOM.
- Delimiter, quote và line separator.
- Record layout và field mapping.
- Các tham số lọc dữ liệu.

Có thể lưu charset như một JobParameter identifying hoặc metadata gắn với input file nếu cùng Job có thể đọc nhiều loại encoding. Khi restart, dùng lại cùng giá trị để đảm bảo giải mã nhất quán.

Nếu file mới có encoding khác, hãy coi đó là một input/version mới theo quy tắc nghiệp vụ thay vì tái sử dụng checkpoint cũ.

## 13. Encoding với MultiResourceItemReader

Khi đọc nhiều file, MultiResourceItemReader thường dùng một delegate reader để đọc từng resource. Encoding cần được cấu hình trên delegate reader:

~~~java
@Bean
@StepScope
public FlatFileItemReader<OrderInput> orderDelegateReader() {
    return new FlatFileItemReaderBuilder<OrderInput>()
            .name("orderDelegateReader")
            .encoding("UTF-8")
            .delimited()
            .names("orderId", "customerName", "amount")
            .targetType(OrderInput.class)
            .saveState(true)
            .build();
}

@Bean
public MultiResourceItemReader<OrderInput> multiOrderReader(
        Resource[] inputResources,
        FlatFileItemReader<OrderInput> orderDelegateReader) {

    return new MultiResourceItemReaderBuilder<OrderInput>()
            .name("multiOrderReader")
            .resources(inputResources)
            .delegate(orderDelegateReader)
            .saveState(true)
            .build();
}
~~~

Ví dụ giả định tất cả resource dùng cùng UTF-8. Nếu các file có encoding khác nhau, một delegate reader với charset cố định không đủ. Cần phân nhóm file theo encoding hoặc dùng reader/decorator chọn charset dựa trên metadata đã được xác thực cho từng resource.

Khi restart, thứ tự resource và nội dung file cần ổn định để trạng thái resource index và trạng thái delegate không bị áp dụng sai file.

## 14. Kiểm thử encoding đầu vào

Nên tạo fixture file với đúng byte encoding, không chỉ lưu nội dung text theo encoding mặc định của IDE.

Các tình huống cần kiểm tra:

- UTF-8 có dấu tiếng Việt.
- UTF-8 không BOM.
- UTF-8 có BOM.
- UTF-16LE hoặc UTF-16BE nếu hệ thống nhận loại file này.
- Charset legacy được đối tác yêu cầu.
- Byte sequence không hợp lệ.
- Ký tự không thể biểu diễn trong charset được chọn.
- CRLF và LF.
- Field chứa delimiter, quote hoặc ký tự Unicode.

Ví dụ tạo file UTF-8 trong test:

~~~java
Path input = tempDir.resolve("orders.csv");
Files.writeString(
        input,
        "orderId,customerName,amount\n"
                + "1001,Nguyễn Văn An,250000\n",
        StandardCharsets.UTF_8);
~~~

Đọc file bằng reader cấu hình UTF-8 rồi xác nhận field customerName giữ nguyên nội dung:

~~~java
assertEquals("Nguyễn Văn An", item.getCustomerName());
~~~

Với BOM, fixture có thể ghi byte BOM trước nội dung UTF-8 hoặc lấy file mẫu từ hệ thống nguồn. Kiểm tra field đầu tiên sau parse để chắc chắn không còn ký tự U+FEFF ngoài ý muốn.

## 15. Kiểm thử encoding đầu ra

Đối với writer, không chỉ kiểm tra String trước khi ghi. Hãy đọc lại byte file bằng đúng charset mà hệ thống nhận sẽ sử dụng:

~~~java
String content = Files.readString(
        output,
        StandardCharsets.UTF_8);

assertTrue(content.contains("Nguyễn Văn An"));
~~~

Nếu contract yêu cầu Windows-1252 hoặc UTF-16, hãy đọc lại bằng đúng charset đó. Có thể so sánh byte fixture hoặc kiểm tra charset encoder có biểu diễn đầy đủ nội dung.

Một bài kiểm thử round-trip hữu ích:

1. Tạo item có ký tự Unicode đại diện.
2. Ghi item bằng FlatFileItemWriter với encoding đã chọn.
3. Đọc file bằng cùng encoding.
4. So sánh các field sau parse với item ban đầu.
5. Kiểm tra header, delimiter, quote và line ending.

Round-trip bằng cùng một charset chưa đủ để chứng minh tương thích với đối tác. Nếu có thể, kiểm thử file bằng công cụ hoặc parser của hệ thống nhận.

## 16. Quản lý encoding qua cấu hình

Không nên hard-code encoding rải rác ở nhiều reader/writer nếu ứng dụng có nhiều đối tác. Có thể tập trung cấu hình bằng một properties class:

~~~java
@ConfigurationProperties(prefix = "batch.files")
public class BatchFileProperties {

    private String inputEncoding = "UTF-8";
    private String outputEncoding = "UTF-8";

    public String getInputEncoding() {
        return inputEncoding;
    }

    public void setInputEncoding(String inputEncoding) {
        this.inputEncoding = inputEncoding;
    }

    public String getOutputEncoding() {
        return outputEncoding;
    }

    public void setOutputEncoding(String outputEncoding) {
        this.outputEncoding = outputEncoding;
    }
}
~~~

Đưa properties vào reader:

~~~java
@Bean
@StepScope
public FlatFileItemReader<OrderInput> orderReader(
        Resource inputFile,
        BatchFileProperties properties) {

    return new FlatFileItemReaderBuilder<OrderInput>()
            .name("orderReader")
            .resource(inputFile)
            .encoding(properties.getInputEncoding())
            .delimited()
            .names("orderId", "customerName", "amount")
            .targetType(OrderInput.class)
            .build();
}
~~~

Ứng dụng cần đăng ký BatchFileProperties bằng cơ chế configuration properties phù hợp, chẳng hạn configuration properties scanning hoặc enable configuration properties. Nếu encoding phụ thuộc đối tác hoặc từng file, hãy xác thực giá trị trước khi tạo reader. Không nhận một tên charset tùy ý từ file input rồi sử dụng mà không có allowlist, vì cấu hình phải thuộc contract được hệ thống tin cậy.

Ghi log tên charset đã chọn cùng input ID để điều tra, nhưng không cần log toàn bộ payload hoặc dữ liệu cá nhân.

## 17. Những lỗi thường gặp

### Dùng charset mặc định của JVM

Kết quả có thể khác giữa local và production. Khai báo encoding tường minh cho reader và writer.

### Cấu hình encoding đúng ở reader nhưng sai ở writer

File đọc được không bảo đảm file xuất ra đúng contract. Cấu hình riêng input encoding và output encoding.

### Nhầm encoding với delimiter

UTF-8 không sửa được lỗi CSV có dấu phẩy trong field nhưng thiếu quote. Kiểm tra cả charset và record format.

### Bỏ qua BOM

BOM có thể trở thành ký tự đầu field hoặc header. Kiểm tra file có BOM và xử lý đúng ở đầu input.

### Giải mã file UTF-8 bằng charset legacy

Ký tự có dấu có thể thành mojibake. Xác nhận charset thực tế của nguồn và cấu hình reader trùng khớp.

### Ghi ký tự không biểu diễn được

Charset đầu ra giới hạn có thể thay ký tự không hỗ trợ. Kiểm tra khả năng encode và quyết định reject, transliterate hoặc thay thế theo contract.

### Nghĩ encoding tự chuẩn hóa Unicode

Hai chuỗi hiển thị giống nhau có thể có biểu diễn code point khác nhau. Chỉ chuẩn hóa NFC/NFD khi yêu cầu nghiệp vụ quy định.

### Đổi encoding khi restart

Checkpoint cũ có thể không còn tương ứng với nội dung được giải mã. Giữ charset và resource ổn định trong cùng JobInstance.

### Dùng một charset cho nhiều file không cùng contract

MultiResourceItemReader delegate có thể đọc sai một số file. Nhóm file theo charset hoặc chọn reader phù hợp từng resource.

### Chỉ kiểm tra file bằng text editor

Editor có thể tự đoán encoding hoặc thay thế ký tự lỗi. Kiểm thử byte, charset và round-trip bằng Java.

## 18. Quy trình cấu hình encoding cho Spring Batch

Khi xây dựng file pipeline, hãy xác định:

1. Hệ thống nguồn tạo file bằng charset nào?
2. Hệ thống đích yêu cầu charset nào?
3. File có BOM không, và reader có cần loại bỏ BOM không?
4. Dữ liệu có thể chứa ký tự ngoài repertoire của charset legacy không?
5. Có cần báo lỗi với malformed hoặc unmappable input thay vì thay thế ký tự không?
6. Delimiter, quote, escape và line ending được quy định thế nào?
7. Multi-resource reader có phải xử lý file với nhiều charset khác nhau không?
8. Encoding có được giữ ổn định qua restart không?
9. Test có fixture byte đúng charset và ký tự đại diện không?
10. File output có được đọc lại bằng đúng charset của đối tác không?

Nên kiểm thử trên cùng JDK và cấu hình runtime dự kiến triển khai. Ghi rõ encoding trong contract trao đổi file và đưa charset vào cấu hình có kiểm soát.

## Kết luận

Encoding quyết định cách chuyển đổi byte của file thành ký tự và ngược lại. Với Spring Batch, hãy cấu hình encoding tường minh trên FlatFileItemReader và FlatFileItemWriter theo contract của nguồn và đích; UTF-8 thường phù hợp cho file mới, còn file legacy cần dùng đúng charset đã xác nhận. Cần xử lý BOM, phân biệt encoding với delimiter và line ending, phát hiện ký tự không hợp lệ hoặc không biểu diễn được, giữ charset ổn định khi restart và kiểm thử round-trip bằng byte thực tế. Không phụ thuộc charset mặc định của JVM vì điều đó có thể làm cùng một Job cho kết quả khác nhau giữa các môi trường.
