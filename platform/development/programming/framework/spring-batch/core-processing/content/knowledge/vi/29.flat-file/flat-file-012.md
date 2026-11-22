# Encoding và newline

Trong Spring Batch, xử lý flat file không chỉ là đọc đúng từng cột. Ứng dụng còn phải hiểu **encoding** của nội dung và **newline** dùng để phân tách các record. Hai yếu tố này quyết định cách byte trong file được chuyển thành ký tự, cách reader xác định ranh giới dòng và cách writer tạo output mà hệ thống khác có thể đọc được.

Một Job có thể chạy đúng trên máy developer nhưng thất bại ở production nếu file được tạo bằng charset khác, có BOM, dùng CRLF thay vì LF, hoặc chứa record nhiều dòng. Output cũng có thể bị consumer từ chối nếu writer tạo newline không đúng hợp đồng file.

Khi làm việc với flat file, cần xác định rõ:

- Charset của file đầu vào và đầu ra.
- File có BOM hay không.
- Quy ước newline: LF, CRLF hay CR.
- Mỗi dòng vật lý có phải một record logic hay không.
- Dữ liệu có chứa newline bên trong field được quote không.
- Hệ thống downstream yêu cầu newline và encoding nào.
- Cấu hình đó có giữ nguyên qua restart hay không.

Spring Batch cung cấp các thuộc tính encoding và line separator cho flat-file reader/writer. Hãy cấu hình theo hợp đồng dữ liệu thay vì phụ thuộc vào mặc định của máy chạy.

## 1. Encoding là gì?

File trên filesystem là một dãy byte. Encoding, hay charset, quy định cách chuyển dãy byte đó thành ký tự Unicode và ngược lại.

Ví dụ cùng một ký tự có thể được biểu diễn bằng số byte khác nhau trong các charset khác nhau:

- UTF-8 dùng từ 1 đến 4 byte cho một Unicode code point.
- UTF-16 dùng các code unit 16 bit và có thể dùng một cặp surrogate cho ký tự ngoài Basic Multilingual Plane.
- Windows-1252 dùng một byte cho các ký tự trong bảng mã của nó.
- ISO-8859-1 có tập ký tự giới hạn khác Windows-1252.

Nếu file được tạo bằng Windows-1252 nhưng reader giải mã như UTF-8, ký tự có dấu có thể bị lỗi, thay bằng ký tự thay thế hoặc làm phát sinh lỗi decode tùy decoder và nội dung cụ thể.

~~~text
File bytes
    |
    v
Charset decoder
    |
    v
Java String / Unicode characters
    |
    v
LineTokenizer / FieldSetMapper
    |
    v
Domain object
~~~

Encoding phải khớp với cách file thực sự được tạo. Không thể sửa dữ liệu sai encoding chỉ bằng cách thay tên file hoặc đổi newline.

## 2. UTF-8 thường là lựa chọn tốt cho trao đổi dữ liệu

UTF-8 được dùng rộng rãi cho CSV, TSV, JSON và nhiều định dạng trao đổi hiện đại. Nó biểu diễn được Unicode và tương thích tốt với nhiều hệ thống.

Ví dụ reader cấu hình UTF-8:

~~~java
@Bean
@StepScope
public FlatFileItemReader<CustomerInput> customerReader(
        @Value("#{jobParameters['inputFile']}") Resource inputFile) {

    return new FlatFileItemReaderBuilder<CustomerInput>()
            .name("customerReader")
            .resource(inputFile)
            .encoding("UTF-8")
            .linesToSkip(1)
            .delimited()
            .names("id", "name", "email")
            .targetType(CustomerInput.class)
            .saveState(true)
            .build();
}
~~~

Việc khai báo encoding tường minh giúp Job có cùng hành vi khi chạy trên Windows, Linux, container hoặc máy có cấu hình charset mặc định khác nhau.

Nếu hợp đồng file quy định một charset legacy như Windows-1252 hoặc ISO-8859-1, hãy khai báo chính xác charset đó. Không chọn UTF-8 chỉ vì nó phổ biến nếu byte nguồn không phải UTF-8.

## 3. Không phụ thuộc vào platform default charset

Tránh để reader hoặc custom code phụ thuộc vào charset mặc định của JVM.

Ví dụ không nên:

~~~java
new InputStreamReader(inputStream);
new FileReader(file);
~~~

Các constructor không chỉ định charset có thể sử dụng default charset của runtime. Hành vi này phụ thuộc Java version và cấu hình môi trường; từ Java 18, UTF-8 là default charset theo JEP 400 trong phần lớn môi trường, nhưng vẫn nên khai báo rõ để thể hiện hợp đồng dữ liệu.

Cách rõ ràng hơn:

~~~java
new InputStreamReader(
        inputStream,
        StandardCharsets.UTF_8);

Files.newBufferedReader(
        path,
        StandardCharsets.UTF_8);
~~~

Đối với Spring Batch, cấu hình encoding ngay trên FlatFileItemReader hoặc FlatFileItemWriter. Với custom reader/writer, dùng Charset hoặc StandardCharsets tường minh.

## 4. UTF-8, UTF-16 và charset legacy

Chọn charset theo nguồn dữ liệu và consumer:

| Charset | Đặc điểm | Khi sử dụng |
|---|---|---|
| UTF-8 | Unicode, 1–4 byte mỗi code point | Định dạng trao đổi phổ biến |
| UTF-16LE | UTF-16 little-endian | Hệ thống yêu cầu byte order little-endian |
| UTF-16BE | UTF-16 big-endian | Hệ thống yêu cầu byte order big-endian |
| Windows-1252 | Bảng mã một byte của Windows Tây Âu | Tích hợp hệ thống legacy |
| ISO-8859-1 | Bảng mã một byte giới hạn | Hệ thống legacy có hợp đồng rõ ràng |

Không dùng tên mơ hồ như "ANSI" trong cấu hình kỹ thuật nếu không biết code page thực tế. Trên Windows, "ANSI" có thể chỉ code page theo locale của máy và không phải một charset duy nhất.

Nếu nhận file từ đối tác, hãy yêu cầu họ xác nhận charset. Có thể kiểm tra byte đầu file hoặc dùng công cụ phân tích, nhưng không nên đoán encoding chỉ từ việc nhìn một vài ký tự.

## 5. BOM là gì?

BOM (Byte Order Mark) là một dấu ở đầu stream có thể dùng để nhận diện encoding hoặc byte order. Một số công cụ thêm BOM khi xuất file; một số consumer không mong đợi ký tự này.

Các byte BOM thường gặp:

| Encoding | BOM bytes |
|---|---|
| UTF-8 | EF BB BF |
| UTF-16LE | FF FE |
| UTF-16BE | FE FF |

UTF-8 không cần BOM để xác định byte order, nhưng một số công cụ Windows vẫn tạo file UTF-8 có BOM.

Nếu reader giải mã UTF-8 và BOM không được loại bỏ, ký tự U+FEFF có thể xuất hiện ở đầu record đầu tiên. Khi đó field đầu tiên có thể chứa BOM ở đầu chuỗi. Ví dụ giá trị mong đợi là ORD-001 nhưng thực tế chuỗi bắt đầu bằng U+FEFF, làm phép so sánh hoặc validation thất bại.

## 6. Xử lý BOM khi đọc file

Trước tiên hãy xác định hợp đồng nguồn: file có BOM hay không, BOM có bắt buộc hay chỉ là tùy chọn.

Có một số cách xử lý:

- Dùng BOM-aware input stream nếu ứng dụng có Apache Commons IO hoặc thư viện phù hợp.
- Bỏ BOM ở đầu stream trước khi đưa vào reader.
- Nếu dùng LineMapper tùy chỉnh, loại bỏ U+FEFF ở đầu record đầu tiên.
- Chuẩn hóa file tại bước ingest trước khi Job xử lý.

Ví dụ helper loại bỏ BOM ở đầu chuỗi:

~~~java
static String stripLeadingBom(String value) {
    if (value != null && !value.isEmpty()
            && value.charAt(0) == '\uFEFF') {
        return value.substring(1);
    }
    return value;
}
~~~

Nếu tự xây dựng LineMapper, có thể áp dụng helper cho dòng đầu tiên trước khi parse:

~~~java
LineMapper<CustomerInput> delegate = createLineMapper();

LineMapper<CustomerInput> bomAwareMapper =
        (line, lineNumber) ->
                delegate.mapLine(
                        stripLeadingBom(line),
                        lineNumber);
~~~

Trong ví dụ này cần gắn bomAwareMapper vào reader thay cho mapper ban đầu. Nếu header được skip trước khi LineMapper xử lý, BOM có thể nằm trong dòng header đã bị bỏ qua; nhưng nếu file không có header hoặc header được parse, cần xử lý BOM tương ứng.

Không loại bỏ mọi ký tự U+FEFF ở giữa nội dung. BOM chỉ được kỳ vọng ở đầu stream; ký tự tương tự ở vị trí khác có thể là dữ liệu cần giữ hoặc cần validation riêng.

## 7. BOM khi ghi file

Phần lớn output UTF-8 hiện đại không cần BOM. Nếu consumer yêu cầu UTF-8 BOM, hãy ghi đúng một lần ở đầu file.

Với FlatFileItemWriter, có thể dùng header callback hoặc một lớp output chuyên trách để ghi BOM cùng header theo đúng format. Ví dụ về nội dung header:

~~~java
.headerCallback(writer ->
        writer.write("\uFEFFid,customerName,email"))
~~~

Cấu hình cụ thể cần được kiểm tra với phiên bản Spring Batch đang dùng và cách writer mở lại file khi restart. Đừng ghi BOM ở mỗi lần write(chunk), vì khi đó BOM sẽ xuất hiện giữa các record.

Nếu không có header nhưng vẫn cần BOM, có thể dùng custom writer hoặc bước tạo file có kiểm soát để ghi BOM trước khi bắt đầu ghi record. Hãy kiểm tra byte đầu output thay vì chỉ mở file bằng editor, vì một số editor tự ẩn BOM.

## 8. Newline là gì?

Newline là ký tự hoặc chuỗi ký tự dùng để phân tách các dòng trong file text.

Ba quy ước thường gặp:

| Tên | Ký hiệu | Byte trong UTF-8 |
|---|---|---|
| LF | \n | 0A |
| CRLF | \r\n | 0D 0A |
| CR | \r | 0D |

- Linux và Unix hiện đại thường dùng LF.
- Windows thường dùng CRLF.
- Một số định dạng hoặc hệ thống cũ dùng CR.

Newline là một phần của cấu trúc file. Nếu consumer yêu cầu CRLF mà writer tạo LF, nội dung có thể vẫn đọc được trong nhiều công cụ nhưng không đáp ứng hợp đồng tích hợp hoặc kiểm tra byte chính xác.

Đừng nhầm newline với encoding. Encoding quy định cách biểu diễn ký tự thành byte; newline quy định ký tự nào kết thúc record. Cả hai cần được cấu hình độc lập.

## 9. BufferedReader và cách Java đọc newline

Các API đọc dòng phổ biến của Java như BufferedReader.readLine() nhận biết LF, CRLF và CR làm dấu kết thúc dòng. Ký tự kết thúc dòng không được trả về trong chuỗi dòng.

Ví dụ file:

~~~text
A<CR><LF>
B<LF>
C<CR>
~~~

Reader dòng có thể trả về ba chuỗi A, B và C. Tuy nhiên, việc API chấp nhận nhiều kiểu newline không có nghĩa mọi định dạng nghiệp vụ đều cho phép trộn chúng.

Với file cần tuân thủ một chuẩn cố định, có thể kiểm tra newline trước khi chạy Job hoặc chuẩn hóa file tại bước ingest. Việc trộn CRLF và LF có thể gây khó khăn cho công cụ khác, checksum, line number hoặc xử lý byte-level.

## 10. FlatFileItemReader và record separator

FlatFileItemReader đọc text theo record và sử dụng cơ chế record separation trước khi chuyển nội dung cho LineMapper.

Cấu hình đơn giản:

~~~java
@Bean
@StepScope
public FlatFileItemReader<OrderInput> orderReader(
        @Value("#{jobParameters['inputFile']}") Resource resource) {

    return new FlatFileItemReaderBuilder<OrderInput>()
            .name("orderReader")
            .resource(resource)
            .encoding("UTF-8")
            .linesToSkip(1)
            .delimited()
            .names("id", "orderNumber", "amount")
            .targetType(OrderInput.class)
            .saveState(true)
            .build();
}
~~~

Reader xử lý các dòng vật lý theo cấu hình record separator. Với file một record trên mỗi dòng, đây thường là mô hình phù hợp.

Cần phân biệt:

- Physical line: một dòng được phân tách bởi newline trong file.
- Logical record: một bản ghi nghiệp vụ mà ứng dụng muốn parse.
- Field: một giá trị trong record.

Với CSV thông thường, một logical record thường nằm trên một physical line. Nhưng CSV có thể cho phép newline nằm trong field được quote. Khi đó một record logic có thể trải qua nhiều physical line.

## 11. CSV có newline bên trong field được quote

Ví dụ CSV:

~~~csv
id,comment
1,"First line
Second line"
2,"Normal comment"
~~~

Dòng comment của record 1 chứa newline bên trong cặp quote. Nếu reader mặc định coi mỗi physical line là một record độc lập, record có thể bị parse sai hoặc phát sinh lỗi.

Khi format cho phép multiline field, cần cấu hình RecordSeparatorPolicy phù hợp với quy tắc quote của file hoặc dùng parser CSV hiểu đầy đủ cú pháp. Không nên tự nối mọi dòng bị lỗi một cách tùy tiện; cần biết khi nào record bắt đầu và kết thúc.

Một RecordSeparatorPolicy có thể:

- Xác định record đã kết thúc hay còn tiếp tục.
- Tiền xử lý từng đoạn dòng trước khi ghép.
- Hậu xử lý record hoàn chỉnh trước khi chuyển cho LineMapper.

Với CSV phức tạp, hãy cân nhắc parser chuyên dụng hỗ trợ RFC 4180 hoặc dialect cụ thể của đối tác. DelimitedLineTokenizer không tự động thay thế một parser CSV hoàn chỉnh cho mọi trường hợp multiline, escape và quote.

## 12. Newline trong dữ liệu và newline phân tách record

Có hai ý nghĩa khác nhau:

1. Newline bên ngoài record dùng để kết thúc record.
2. Newline nằm trong giá trị field, được giữ như một phần dữ liệu.

Với CSV, newline trong field thường phải được đặt trong quote và quote bên trong field phải được escape theo dialect.

Ví dụ:

~~~csv
id,description
10,"Address:
12 Main Street
District 1"
~~~

Nếu writer tạo CSV, line aggregator phải thực hiện đúng quy tắc quote/escape của định dạng. Chỉ cấu hình lineSeparator không đủ để bảo vệ newline nằm trong field.

Nếu downstream không hỗ trợ multiline field, hãy thay newline trong dữ liệu bằng một biểu diễn được thống nhất, chẳng hạn khoảng trắng hoặc chuỗi escape. Không tự ý thay thế nếu nội dung gốc cần được bảo toàn.

## 13. Cấu hình newline cho FlatFileItemWriter

FlatFileItemWriter cho phép chỉ định line separator. Nên khai báo rõ khi output phải tuân theo một chuẩn tích hợp.

Ví dụ tạo file UTF-8 dùng LF:

~~~java
@Bean
@StepScope
public FlatFileItemWriter<OrderResult> orderWriter(
        @Value("#{jobParameters['outputFile']}") Resource outputFile) {

    return new FlatFileItemWriterBuilder<OrderResult>()
            .name("orderWriter")
            .resource(outputFile)
            .encoding("UTF-8")
            .lineSeparator("\n")
            .delimited()
            .names("id", "orderNumber", "status")
            .headerCallback(writer ->
                    writer.write("id,orderNumber,status"))
            .saveState(true)
            .build();
}
~~~

Nếu consumer yêu cầu CRLF, cấu hình:

~~~java
.lineSeparator("\r\n")
~~~

Nếu dùng System.lineSeparator(), output phụ thuộc hệ điều hành chạy ứng dụng. Điều đó có thể không phù hợp khi cùng một Job chạy ở Windows trong development và Linux trong production nhưng downstream yêu cầu định dạng cố định.

Line separator được writer thêm giữa các record. Hãy kiểm tra chính xác hành vi với header, footer, restart và file rỗng theo phiên bản Spring Batch đang dùng.

## 14. Newline cuối file

Một file text có thể kết thúc bằng newline hoặc không. Nhiều công cụ Unix và hệ thống xử lý dòng mong đợi newline ở cuối file; một số giao thức chỉ quan tâm các record được phân tách ở giữa.

Cần xác định hợp đồng:

- Mỗi record kết thúc bằng newline, kể cả record cuối.
- Record cuối không có newline.
- File rỗng có header hay không.
- Header và footer có được tính như record không.

FlatFileItemWriter thường ghi line separator sau mỗi record theo cấu hình. Nếu consumer yêu cầu không có newline cuối file, hãy kiểm tra writer và có thể cần bước finalize riêng. Không chỉnh file bằng thao tác cắt byte sau khi Job hoàn tất nếu chưa hiểu tác động tới restart và tính toàn vẹn.

Đối với file trao đổi, việc luôn kết thúc bằng newline thường dễ tương thích hơn, nhưng phải tuân theo đặc tả của hệ thống đích.

## 15. Không dùng System.lineSeparator nếu format cố định

System.lineSeparator() trả về newline theo hệ điều hành runtime. Ví dụ:

- Windows thường trả về CRLF.
- Linux thường trả về LF.

Nếu output được gửi cho một đối tác yêu cầu CRLF, hãy cấu hình CRLF tường minh. Nếu yêu cầu LF, cấu hình LF tường minh.

Một Job có thể chạy trên nhiều môi trường. Nếu để mặc định, cùng JobParameters có thể tạo file khác byte chỉ vì hệ điều hành khác nhau. Điều này ảnh hưởng checksum, chữ ký số, diff, test snapshot và parser strict.

Nên đặt encoding và lineSeparator cùng một nơi cấu hình, có thể theo từng loại file hoặc đối tác.

## 16. Encoding và newline trong custom reader

Nếu viết reader thủ công, mở stream với charset cụ thể:

~~~java
try (BufferedReader reader = Files.newBufferedReader(
        inputPath,
        StandardCharsets.UTF_8)) {

    String line;
    while ((line = reader.readLine()) != null) {
        // Parse một logical record đơn giản trên mỗi dòng.
    }
}
~~~

readLine() loại bỏ dấu kết thúc dòng, nên code không biết dòng nguồn ban đầu dùng LF hay CRLF chỉ từ giá trị trả về.

Nếu cần phát hiện newline gốc hoặc giữ nguyên byte, hãy đọc ở cấp byte hoặc dùng parser có khả năng ghi nhận delimiter. Đừng dùng readLine() rồi giả định có thể tái tạo chính xác byte gốc.

Với custom reader triển khai ItemStreamReader, hãy kết hợp encoding/newline handling với checkpoint. Nếu reader restart từ vị trí byte, cần tính toán offset theo byte của encoding chứ không phải số ký tự Java.

## 17. Byte offset khác character offset

Đây là điểm quan trọng với UTF-8 và fixed-width file.

Một ký tự ASCII trong UTF-8 thường chiếm một byte, nhưng ký tự có dấu hoặc ký tự ngoài ASCII có thể chiếm nhiều byte. Java String dùng UTF-16 code unit; String.length() không phải số byte UTF-8 và cũng không luôn bằng số Unicode code point.

Ví dụ:

~~~java
String value = "café";

int utf16Length = value.length();

int utf8ByteLength =
        value.getBytes(StandardCharsets.UTF_8).length;
~~~

Hai độ dài có thể khác nhau.

Nếu đặc tả fixed-width nói mỗi field chiếm 20 byte, không được dùng String.substring(0, 20) rồi cho rằng đã lấy đúng 20 byte UTF-8. Cần parse theo byte trước khi decode hoặc dùng một quy tắc encoding/field width được xác định rõ.

Nếu đặc tả nói 20 ký tự Unicode, cần định nghĩa "ký tự" là code point hay grapheme cluster và chọn cách cắt tương ứng. Đừng dùng thuật ngữ byte và character thay thế cho nhau.

## 18. Newline và fixed-width file

Với fixed-width file, record thường có độ dài cố định, nhưng newline có thể nằm ngoài độ dài record hoặc được tính riêng theo đặc tả.

Ví dụ:

~~~text
Record bytes: 100 bytes
Delimiter: CRLF (2 bytes)
Next record begins after delimiter
~~~

Nếu tính offset theo byte, cần cộng cả độ dài delimiter. Với LF, delimiter chiếm một byte; với CRLF, hai byte trong UTF-8.

Nếu dùng FlatFileItemReader và FixedLengthTokenizer, tokenizer làm việc trên chuỗi đã decode. Điều này phù hợp khi field range được định nghĩa theo vị trí ký tự mà parser sử dụng. Nếu hệ thống nguồn định nghĩa cột theo byte, đặc biệt khi có multibyte encoding, cần byte-aware parsing trước khi chuyển sang String.

Hãy lấy ví dụ file thực tế và xác nhận offset của từng field, byte order, charset và delimiter. Một ký tự tiếng Việt có dấu có thể làm sai cột phía sau nếu code cắt theo byte/character không đúng quy ước.

## 19. Kiểm tra encoding và newline của file nguồn

Có thể kiểm tra byte đầu và một số byte đại diện bằng công cụ hệ điều hành:

~~~bash
file -bi orders.csv
xxd -l 32 orders.csv
od -An -tx1 -N64 orders.csv
~~~

Các công cụ này giúp quan sát MIME/charset được suy đoán và byte thực tế. Kết quả file -bi là phỏng đoán, không phải bằng chứng tuyệt đối về encoding.

Trong PowerShell:

~~~powershell
Format-Hex -Path 'D:\batch\input\orders.csv' -Count 32
~~~

Để xác định newline, có thể kiểm tra byte 0A và 0D 0A. Cần tránh chỉ nhìn file trong editor vì editor có thể tự chuyển newline hoặc hiển thị nội dung đã decode theo charset được đoán.

Với file lớn, không cần đọc toàn bộ vào memory chỉ để kiểm tra BOM hoặc một số byte đầu. Có thể đọc prefix và dùng streaming validator.

## 20. Chuẩn hóa newline trước khi xử lý

Nếu nguồn đến từ nhiều hệ thống và newline không ổn định, có thể chuẩn hóa tại bước ingest:

~~~text
File nhận từ đối tác
        |
        v
Kiểm tra charset và BOM
        |
        v
Kiểm tra record separator
        |
        v
Chuẩn hóa sang UTF-8 + LF
        |
        v
Lưu file bất biến trong staging
        |
        v
Spring Batch reader xử lý
~~~

Ưu điểm:

- Reader có cấu hình nhất quán.
- Dễ kiểm thử và tái tạo input.
- Checksum có thể được tính trên file đã chuẩn hóa.
- Hệ thống downstream không phụ thuộc máy gửi file.

Tuy nhiên, normalization phải bảo toàn dữ liệu. Nếu newline nằm trong field được quote, không được thay mọi CRLF thành LF một cách mù quáng nếu điều đó làm thay đổi nội dung field hoặc quy tắc record. Cần dùng parser hiểu format hoặc chỉ chuẩn hóa delimiter ngoài record.

Giữ file gốc nếu cần audit hoặc đối soát. Có thể lưu cả original file và normalized artifact với checksum, encoding và phiên bản quy tắc chuyển đổi.

## 21. Encoding và newline ảnh hưởng restart

Reader có thể lưu checkpoint theo item count, dòng hoặc state nội bộ. Khi restart, reader mở lại nguồn và định vị theo state đã lưu.

Nếu file thay đổi giữa lần chạy và restart, checkpoint có thể không còn trỏ tới cùng record:

- File được chuyển từ LF sang CRLF.
- File được convert từ Windows-1252 sang UTF-8.
- BOM được thêm hoặc loại bỏ.
- Dòng bị chèn hoặc xóa.
- Nội dung record được thay thế.
- File bị ghi đè bằng một phiên bản mới cùng tên.

Một thay đổi về encoding hoặc newline có thể làm vị trí dòng/record hoặc byte offset thay đổi. Job có thể bỏ sót hoặc đọc trùng dữ liệu.

Để restart nhất quán:

- Giữ input file bất biến.
- Lưu checksum hoặc version của file.
- Lưu charset và format version như một phần cấu hình đầu vào.
- Không thay đổi line separator trong lúc restart cùng JobInstance.
- Dùng JobParameters hoặc ExecutionContext để giữ metadata cần thiết.
- Xác minh fingerprint khi reader mở lại.

Checkpoint không phải snapshot của nội dung file. Nó chỉ có ý nghĩa khi nguồn và quy tắc đọc vẫn tương thích.

## 22. Writer restart và output encoding

FlatFileItemWriter có thể lưu state để tiếp tục output sau restart. Tên writer phải ổn định và saveState cần được bật nếu muốn khôi phục state.

Encoding, line separator, header và cách format field phải giữ nhất quán giữa lần chạy đầu và lần restart.

Ví dụ lần đầu ghi UTF-8 + LF nhưng lần restart đổi sang UTF-16LE + CRLF. File output sẽ chứa các phần có encoding/newline khác nhau, khiến consumer không thể parse ổn định.

Đối với output cần độ tin cậy cao:

- Dùng output file riêng cho JobInstance hoặc execution.
- Không cho consumer đọc file tạm khi Job chưa hoàn tất.
- Giữ writer name và cấu hình format ổn định.
- Bật saveState nếu writer hỗ trợ restart.
- Chỉ publish file cuối sau khi Step/Job thành công.
- Nếu cần đổi format, tạo một output mới thay vì tiếp tục file đang dở bằng cấu hình khác.

## 23. Header, footer và newline

FlatFileItemWriter có thể ghi header và footer thông qua callback. Header/footer cũng phải tuân thủ encoding và newline của file.

Ví dụ:

~~~java
.headerCallback(writer ->
        writer.write("id,orderNumber,status"))
.footerCallback(writer ->
        writer.write("END"))
~~~

Line separator của writer được áp dụng theo lifecycle ghi dòng. Hãy kiểm tra output byte thực tế để xác nhận header, từng record và footer được ngăn cách đúng. Không tự thêm CRLF trong callback rồi đồng thời cấu hình writer thêm CRLF nếu không muốn có dòng trống.

Nếu header có BOM, BOM phải nằm trước ký tự đầu tiên của file, không phải trước mỗi chunk. Footer chỉ nên được ghi theo lifecycle hoàn tất của writer; test restart để bảo đảm không xuất hiện nhiều footer hoặc header trùng.

## 24. Locale không phải encoding

Locale ảnh hưởng cách định dạng số, ngày, tiền tệ và dấu phân cách thập phân. Encoding quyết định cách chuyển ký tự thành byte.

Ví dụ:

- Locale vi-VN có thể dùng dấu phẩy hoặc quy ước định dạng số theo cấu hình formatter.
- Locale en-US có thể dùng dấu chấm cho phần thập phân.
- UTF-8 có thể biểu diễn cả hai cách viết.
- Thay encoding không tự thay dấu thập phân.
- Thay locale không tự thay newline.

Nếu file dùng dấu phẩy làm delimiter và dấu phẩy thập phân theo locale, cần quy định rõ cách quote hoặc định dạng số. Đừng dùng encoding để giải quyết lỗi parse do locale.

Trong Spring Batch, hãy cấu hình formatter/FieldExtractor hoặc conversion service theo format hợp đồng. Charset và locale nên được quản lý như hai thuộc tính riêng.

## 25. CSV quoting, escaping và newline

CSV có nhiều dialect. Các hệ thống có thể khác nhau về:

- Delimiter là dấu phẩy, dấu chấm phẩy hay tab.
- Quote character là dấu nháy kép hay ký tự khác.
- Cách escape quote bên trong field.
- Có cho phép newline bên trong quoted field không.
- Có yêu cầu CRLF hay LF không.
- Có BOM hay không.

Ví dụ một field chứa dấu phẩy và dấu quote:

~~~csv
id,comment
1,"Customer said ""hello, team"""
~~~

Writer phải escape quote theo dialect. Nếu field chứa newline, nó phải được quote đúng cách nếu format cho phép. Một line aggregator đơn giản chỉ nối các field bằng dấu phẩy có thể tạo file không hợp lệ.

Hãy ghi rõ dialect trong hợp đồng dữ liệu và test bằng parser của consumer hoặc parser tương thích. Không dựa vào việc file trông đúng khi mở trong Excel.

## 26. Kiểm thử encoding

Nên tạo fixture có các ký tự đại diện cho dữ liệu thực tế:

- ASCII.
- Tiếng Việt có dấu.
- Ký tự Unicode ngoài Latin.
- Ký tự supplementary nếu có.
- Dữ liệu có BOM và không BOM.
- Byte sequence không hợp lệ theo charset.

Kiểm thử reader cần xác nhận giá trị Java String sau khi decode, không chỉ xác nhận số item đã đọc.

Ví dụ:

~~~java
@Test
void readsUtf8VietnameseText() throws Exception {
    Path file = tempDir.resolve("customers.csv");

    Files.writeString(
            file,
            "id,name\n1,Nguyễn Ánh\n",
            StandardCharsets.UTF_8);

    CustomerInput item = readFirstItem(file);

    assertEquals("Nguyễn Ánh", item.name());
}
~~~

Nếu cần test file có BOM, tạo byte prefix EF BB BF rồi nối nội dung UTF-8. Xác nhận BOM không còn trong field đầu tiên theo policy của ứng dụng.

Với charset legacy, tạo fixture bằng charset đúng và xác nhận reader dùng cùng encoding. Không tạo fixture bằng platform default vì test có thể cho kết quả khác giữa máy.

## 27. Kiểm thử newline

Tạo fixture cho từng quy ước:

~~~text
LF:    record1<LF>record2<LF>
CRLF:  record1<CR><LF>record2<CR><LF>
CR:    record1<CR>record2<CR>
~~~

Kiểm thử:

- Reader đọc đúng số logical record.
- Không để ký tự CR cuối dòng lọt vào field.
- Blank line được xử lý theo policy.
- Record cuối không có newline vẫn được xử lý đúng nếu format cho phép.
- Newline trong quoted field không bị tách thành hai record.
- Line number trong lỗi parse phản ánh đúng physical line.
- Writer tạo đúng byte delimiter đã cấu hình.

Với writer, đọc lại output dưới dạng byte và kiểm tra chuỗi delimiter. Không chỉ dùng readAllLines vì API đó chuẩn hóa việc đọc dòng và có thể che giấu newline gốc.

## 28. Kiểm thử output byte chính xác

Nếu downstream yêu cầu UTF-8 + CRLF, test có thể xác nhận byte đầu và delimiter:

~~~java
byte[] output = Files.readAllBytes(outputPath);

assertEquals(
        (byte) 0x0D,
        output[indexOfFirstRecordSeparator]);

assertEquals(
        (byte) 0x0A,
        output[indexOfFirstRecordSeparator + 1]);
~~~

Trong test thực tế, nên tìm vị trí delimiter bằng cách đọc byte stream hoặc so sánh toàn bộ output với expected bytes được tạo bằng StandardCharsets.UTF_8 và chuỗi CRLF.

Nếu output yêu cầu BOM, xác nhận ba byte đầu là EF BB BF. Nếu không yêu cầu BOM, xác nhận file không bắt đầu bằng prefix đó.

Đừng chỉ so sánh String sau khi decode; một số khác biệt byte có thể biến mất khi đọc lại và chuẩn hóa newline.

## 29. Những lỗi thường gặp

### Reader dùng sai charset

Ký tự có dấu bị lỗi hoặc field đầu tiên chứa ký tự lạ. Khai báo encoding đúng với nguồn.

### Phụ thuộc default charset

Job chạy khác nhau giữa máy hoặc Java runtime. Cấu hình UTF-8 hay charset hợp đồng một cách tường minh.

### BOM xuất hiện trong business key

Reader không loại bỏ BOM đầu file. Dùng BOM-aware input hoặc strip BOM đúng vị trí.

### Writer tạo newline theo hệ điều hành

Output thay đổi giữa Windows và Linux. Cấu hình lineSeparator theo hợp đồng.

### Trộn LF và CRLF

Một số consumer hoặc checksum strict có thể thất bại. Chuẩn hóa nguồn hoặc từ chối file không đúng format.

### CSV có field nhiều dòng nhưng reader tách theo physical line

Một logical record bị chia thành nhiều item. Dùng RecordSeparatorPolicy hoặc parser CSV hỗ trợ multiline.

### Cắt fixed-width theo String.length

UTF-8 có ký tự nhiều byte. Xác định field width theo byte hay ký tự và parse đúng đơn vị.

### Thay đổi file trước khi restart

Checkpoint không còn trỏ tới cùng dữ liệu. Giữ input bất biến và xác minh checksum/version.

### Thêm BOM nhiều lần khi restart hoặc ghi chunk

BOM xuất hiện giữa file. Chỉ ghi BOM một lần ở đầu output và test restart.

### Chỉ kiểm tra file bằng editor

Editor có thể tự đoán encoding hoặc chuẩn hóa newline. Kiểm tra byte thực tế khi format yêu cầu chính xác.

## 30. Quy trình thiết kế encoding và newline

Khi xây dựng một Job đọc/ghi flat file, hãy xác định:

1. Charset đầu vào được đối tác hoặc hệ thống nguồn công bố là gì?
2. File có BOM hay không?
3. Reader có cần loại bỏ BOM trước khi parse không?
4. Newline đầu vào là LF, CRLF hay CR?
5. Có record logic trải qua nhiều physical line không?
6. CSV dialect có quy định quote và escape thế nào?
7. Fixed-width column được tính theo byte hay ký tự?
8. Reader đã khai báo encoding tường minh chưa?
9. Writer đã khai báo encoding và lineSeparator tường minh chưa?
10. Header/footer có tuân theo cùng format không?
11. Input và output có bất biến hoặc ổn định qua restart không?
12. Test có kiểm tra cả giá trị Unicode và byte output không?

Encoding quyết định cách byte trở thành ký tự; newline quyết định cách record được phân tách. Spring Batch cần reader/writer được cấu hình theo đúng hợp đồng của file, đặc biệt với BOM, multiline CSV và fixed-width data. Khi khai báo charset và line separator tường minh, giữ nguồn ổn định qua restart và kiểm tra output ở cấp byte, Job sẽ tạo ra flat file nhất quán giữa các môi trường và tương thích với consumer.
