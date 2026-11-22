# Bỏ qua dòng header

File CSV hoặc file text dạng bảng thường có một dòng đầu mô tả tên cột, ví dụ `orderId,customerId,amount`. Dòng này giúp người đọc hiểu cấu trúc file, nhưng thường không phải dữ liệu nghiệp vụ cần đưa vào processor hoặc writer. Nếu reader coi header là một record thông thường, ứng dụng có thể parse sai kiểu dữ liệu, tạo bản ghi rác hoặc thất bại ngay ở item đầu tiên.

Trong Spring Batch, `FlatFileItemReader` hỗ trợ bỏ qua một số dòng đầu file bằng thuộc tính **`linesToSkip`**. Có thể kết hợp `skippedLinesCallback` để đọc, kiểm tra hoặc ghi log các dòng bị bỏ qua. Cấu hình này hữu ích khi file có header cố định, nhưng cần hiểu rõ số dòng bị bỏ qua, thời điểm callback chạy, hành vi khi restart và trường hợp đọc nhiều file.

## 1. Vì sao cần bỏ qua header?

Giả sử file đầu vào có nội dung:

```csv
orderId,customerId,amount
1001,C001,250.00
1002,C002,175.50
1003,C003,420.00
```

Dòng đầu tiên là tên cột. Các dòng sau mới là dữ liệu đơn hàng. Nếu reader gửi cả header vào `LineMapper`, `FieldSetMapper` có thể cố chuyển chuỗi `orderId` thành kiểu `Long`, hoặc tạo một object với giá trị không hợp lệ.

Bỏ qua header giúp:

- Chỉ chuyển các dòng dữ liệu thành item.
- Tránh header bị ghi vào bảng hoặc file output như một record.
- Giữ logic mapping tập trung vào cấu trúc dữ liệu thực tế.
- Cho phép kiểm tra header trước khi xử lý dữ liệu nếu cần.
- Phân biệt rõ metadata mô tả file với record nghiệp vụ.

Header vẫn có giá trị kiểm tra. Nếu ứng dụng bỏ qua nó mà không xác minh tên và thứ tự cột, một file có schema thay đổi có thể được map sai mà không phát hiện sớm.

## 2. Cấu hình linesToSkip

`FlatFileItemReader` cung cấp `setLinesToSkip(int)` để chỉ định số dòng đầu cần bỏ qua khi mở resource. Builder cũng cung cấp phương thức `.linesToSkip(int)`.

Với file chỉ có một dòng header, cấu hình đơn giản là:

```java
@Bean
@StepScope
public FlatFileItemReader<OrderInput> orderReader(
        @Value("#{jobParameters['inputFile']}") String inputFile) {

    return new FlatFileItemReaderBuilder<OrderInput>()
            .name("orderFileReader")
            .resource(new FileSystemResource(inputFile))
            .encoding(StandardCharsets.UTF_8.name())
            .linesToSkip(1)
            .delimited()
            .delimiter(",")
            .names("orderId", "customerId", "amount")
            .targetType(OrderInput.class)
            .saveState(true)
            .build();
}
```

Với cấu hình trên:

- `linesToSkip(1)` bỏ qua dòng vật lý đầu tiên của file.
- `delimited()` cấu hình tokenizer cho dữ liệu phân tách bằng delimiter.
- `names(...)` khai báo tên field dùng để ánh xạ dữ liệu.
- `targetType(...)` yêu cầu builder tạo object theo kiểu đích.
- `saveState(true)` cho phép reader lưu state phục vụ restart.
- `encoding(...)` chỉ định encoding đầu vào rõ ràng.

Header không được trả về như một item. Reader bắt đầu trả item từ dòng dữ liệu đầu tiên.

Nếu file không có header, phải để `linesToSkip(0)` hoặc bỏ cấu hình skip. Nếu vẫn đặt `1`, record dữ liệu đầu tiên sẽ bị bỏ mất.

## 3. linesToSkip đếm dòng, không đếm item nghiệp vụ

`linesToSkip` là số dòng đầu file được đọc bỏ qua trước khi mapping item. Nó không phải số item cần skip theo `SkipPolicy`, cũng không phải số record cần loại bỏ do lỗi nghiệp vụ.

| Cơ chế | Mục đích | Ví dụ |
|---|---|---|
| `linesToSkip(1)` | Bỏ qua một dòng đầu khi mở file | Header CSV |
| `SkipPolicy` / `.skip(...)` | Bỏ qua item phát sinh exception được phép skip | Một record có ngày sai định dạng |
| `ItemProcessor` trả `null` | Lọc item hợp lệ nhưng không cần ghi output | Bỏ đơn hàng đã hủy theo quy tắc |
| `LineCallbackHandler` | Nhận nội dung các dòng bị bỏ qua | Kiểm tra hoặc log header |

Dòng header không được đọc thành item, vì vậy nó không làm tăng `readCount`, `processCount` hoặc `writeCount` như một record bình thường. Nó cũng không đi qua `ItemProcessor` và không được xử lý như một item skip thông thường.

Nếu header không hợp lệ, callback có thể ném exception khi reader mở file, làm step thất bại. Đây là lỗi cấu trúc file, khác với việc skip một record dữ liệu sau khi reader đã trả item.

## 4. Bỏ qua nhiều dòng đầu

Một số file có phần mô tả hoặc thông tin xuất báo cáo trước header:

```text
Report: Daily Orders
Business date: 2026-11-15
orderId,customerId,amount
1001,C001,250.00
1002,C002,175.50
```

Trong ví dụ này, cần bỏ qua hai dòng metadata và một dòng header, tức ba dòng đầu:

```java
reader.setLinesToSkip(3);
```

`linesToSkip` chỉ đếm số dòng đầu cần bỏ qua. Nếu muốn kiểm tra riêng dòng header nằm ở vị trí thứ ba, callback phải biết vị trí của từng dòng bị bỏ qua hoặc ứng dụng nên dùng một bước preflight/parser riêng.

Không nên đặt `linesToSkip` theo số dòng metadata ước lượng nếu file có thể thay đổi. Nếu phần mở đầu có độ dài động, hãy dùng một reader/parser chuyên biệt để tìm header theo marker hoặc định dạng đã quy định, sau đó bắt đầu đọc dữ liệu từ vị trí đúng.

## 5. Dùng skippedLinesCallback để quan sát header

`FlatFileItemReader` hỗ trợ `LineCallbackHandler` thông qua `setSkippedLinesCallback(...)`. Callback được gọi với nội dung mỗi dòng bị bỏ qua.

Ví dụ chỉ ghi log header:

```java
FlatFileItemReader<OrderInput> reader = new FlatFileItemReader<>();
reader.setName("orderFileReader");
reader.setResource(new FileSystemResource(inputFile));
reader.setLinesToSkip(1);
reader.setSkippedLinesCallback(line ->
        log.info("Skipped file header: {}", line));
```

Callback nhận raw line đã được reader đọc, trước khi các dòng dữ liệu được map thành item. Nó không thay thế `LineMapper` và không nhận `FieldSet` đã được ánh xạ cho record dữ liệu.

Nếu `linesToSkip(3)`, callback được gọi cho từng dòng trong ba dòng bị bỏ qua. Vì vậy, đừng giả định callback chỉ nhận header nếu file còn có phần preamble.

Callback phù hợp để:

- Ghi log header phục vụ audit.
- Xác nhận header đúng schema mong đợi.
- Đọc metadata đơn giản ở đầu file.
- Chuẩn bị thông tin mapping nếu ứng dụng hỗ trợ schema động.

Không dùng callback để xử lý toàn bộ dữ liệu nghiệp vụ. Các dòng sau phần header vẫn thuộc trách nhiệm của tokenizer, line mapper và processor.

## 6. Kiểm tra header có đúng schema mong đợi

Bỏ qua header mà không xác minh có thể che giấu lỗi schema. Ví dụ, ứng dụng mong đợi `orderId,customerId,amount`, nhưng file thực tế đổi thành `customerId,orderId,amount`. Nếu mapping dựa trên vị trí cột, giá trị có thể bị gán nhầm field.

Có thể xác nhận header trong callback:

```java
private static final String EXPECTED_HEADER =
        "orderId,customerId,amount";

reader.setLinesToSkip(1);
reader.setSkippedLinesCallback(header -> {
    if (!EXPECTED_HEADER.equals(header)) {
        throw new IllegalStateException(
                "Unexpected CSV header. Expected: " + EXPECTED_HEADER);
    }
});
```

Nếu header không khớp, reader không nên tiếp tục map dữ liệu theo schema cũ. Exception phát sinh trong callback thường làm quá trình mở reader/step thất bại; nó không được xem như một item lỗi để `skip(...)` tự động bỏ qua.

So sánh chuỗi nguyên văn phù hợp khi định dạng header được chuẩn hóa tuyệt đối. Nếu file có thể thay đổi khoảng trắng, BOM hoặc cách viết hoa/thường, hãy chuẩn hóa trước khi so sánh nhưng không được làm mất khác biệt có ý nghĩa.

## 7. Xác thực thứ tự cột

Nếu mapping dựa trên vị trí, cần kiểm tra cả tên lẫn thứ tự cột. Ví dụ:

```text
Expected: orderId,customerId,amount
Actual:   customerId,orderId,amount
```

Hai header có cùng tập tên nhưng thứ tự khác nhau. Nếu tokenizer vẫn dùng `.names("orderId", "customerId", "amount")`, giá trị đầu tiên trong dòng dữ liệu có thể bị gán vào `orderId` dù thực tế là `customerId`.

Khi so sánh header, nên:

1. Parse header thành danh sách tên cột.
2. Chuẩn hóa theo quy ước của hệ thống, ví dụ trim khoảng trắng.
3. Kiểm tra số lượng cột.
4. Kiểm tra tên cột và thứ tự.
5. Từ chối file nếu có cột thiếu, thừa hoặc trùng tên mà ứng dụng không hỗ trợ.

Không nên chỉ kiểm tra header có chứa các tên mong đợi. Một file có thêm cột trùng hoặc cột sai vị trí vẫn có thể gây mapping sai.

## 8. Header có delimiter hoặc dấu nháy

CSV cho phép giá trị header có dấu nháy và delimiter nằm trong tên cột, ví dụ:

```csv
"order,id","customer,name",amount
1001,"Smith, John",250.00
```

Không nên dùng `String.split(",")` để parse header trong trường hợp CSV có quoting. `split` không hiểu quy tắc dấu nháy và có thể chia một tên cột thành nhiều phần.

Hãy dùng cùng loại tokenizer CSV với phần dữ liệu để parse header. Ví dụ minh họa:

```java
DelimitedLineTokenizer headerTokenizer = new DelimitedLineTokenizer();
headerTokenizer.setDelimiter(",");

reader.setLinesToSkip(1);
reader.setSkippedLinesCallback(headerLine -> {
    FieldSet headerFields = headerTokenizer.tokenize(headerLine);
    String[] columnNames = headerFields.getValues();

    if (!Arrays.equals(
            new String[] {"order,id", "customer,name", "amount"},
            columnNames)) {
        throw new IllegalStateException("Unexpected header columns");
    }
});
```

Đây là ví dụ minh họa việc dùng tokenizer để parse header. Cần cấu hình tokenizer phù hợp với dialect CSV thực tế, gồm delimiter, quote character, escape rules và strictness. Nếu thư viện/phiên bản đang dùng yêu cầu cấu hình thêm, hãy giữ cùng quy tắc parse giữa header và data.

## 9. Header BOM và encoding

Một số file UTF-8 được tạo bởi công cụ spreadsheet có thể bắt đầu bằng byte order mark (BOM). Khi đọc dưới dạng text, ký tự BOM có thể xuất hiện trước tên cột đầu tiên, khiến so sánh header thất bại dù file nhìn bằng mắt có vẻ đúng.

Ví dụ giá trị thực tế của cột đầu có thể là `\uFEFForderId` thay vì `orderId`.

Các lưu ý:

- Chỉ định encoding rõ ràng, thường là UTF-8 nếu hợp đồng file quy định UTF-8.
- Kiểm tra BOM ở đầu file khi header không khớp bất thường.
- Nếu cần loại BOM, chỉ loại ở đầu file và chỉ khi đúng là BOM; không trim hoặc thay đổi nội dung tùy tiện.
- Không dùng encoding mặc định của máy vì môi trường development và production có thể khác nhau.
- Kiểm thử file có và không có BOM nếu nguồn đầu vào có thể tạo cả hai dạng.

`linesToSkip` bỏ qua dòng theo nội dung text reader nhận được; nó không tự xác thực encoding hay chuẩn hóa BOM cho ứng dụng.

## 10. Header và dòng trống

Một số file có dòng trống trước header hoặc giữa phần preamble và header. `linesToSkip` đếm dòng đầu theo vị trí, kể cả dòng trống. Nó không tìm dòng đầu tiên không rỗng để tự nhận diện header.

Ví dụ:

```text

orderId,customerId,amount
1001,C001,250.00
```

Nếu cấu hình `linesToSkip(1)`, reader bỏ dòng trống đầu tiên và có thể trả header thành item. Nếu cấu hình `linesToSkip(2)`, reader bỏ cả dòng trống và header.

Nếu file có số dòng trống đầu không cố định, hãy dùng preflight/parser để xác định cấu trúc hoặc chuẩn hóa nguồn trước khi chạy. Không chọn một con số skip cố định nếu dữ liệu đầu vào không bảo đảm cấu trúc đó.

## 11. Header nhiều dòng và preamble

Một số định dạng file có nhiều dòng mô tả:

```text
Company: Example Ltd
Report: Orders
Date: 2026-11-15
orderId,customerId,amount
1001,C001,250.00
```

Nếu ba dòng đầu là metadata và dòng thứ tư là header, có thể bỏ qua bốn dòng. Nhưng nếu cần xác thực riêng dòng thứ tư, callback phải phân biệt vị trí dòng. Có thể dùng bộ đếm cục bộ trong callback:

```java
AtomicInteger skippedLineNumber = new AtomicInteger();

reader.setLinesToSkip(4);
reader.setSkippedLinesCallback(line -> {
    int lineNumber = skippedLineNumber.incrementAndGet();

    if (lineNumber == 4 && !EXPECTED_HEADER.equals(line)) {
        throw new IllegalStateException("Invalid header at line 4");
    }
});
```

Đoạn mã minh họa giả định callback được gọi tuần tự trong quá trình mở reader cho các dòng bị skip. Nếu reader được mở lại trong cùng instance hoặc callback có thể chạy nhiều lần theo lifecycle cụ thể, bộ đếm phải được khởi tạo/reset phù hợp. Với định dạng phức tạp, một bước preflight chuyên biệt dễ kiểm soát hơn.

## 12. Bỏ qua header khác với comment lines

Header là phần mô tả schema thường nằm ở đầu file. Comment là các dòng ghi chú có marker, ví dụ `# generated by system`.

Hai trường hợp không nên nhầm lẫn:

- `linesToSkip` bỏ qua một số dòng đầu cố định.
- Cấu hình comment của `FlatFileItemReader` nhận diện các dòng comment theo prefix được cấu hình trong quá trình đọc.

Ví dụ:

```text
# generated at 2026-11-15
orderId,customerId,amount
1001,C001,250.00
```

Nếu comment luôn có ở dòng đầu và header ở dòng thứ hai, có thể dùng `linesToSkip(2)` và callback kiểm tra từng dòng. Nếu comment có thể xuất hiện ở nhiều vị trí, hãy dùng cơ chế comment phù hợp thay vì tăng `linesToSkip` để bỏ một số dòng đầu.

Không nên bỏ qua mọi dòng bắt đầu bằng một ký tự nếu dữ liệu hợp lệ cũng có thể bắt đầu bằng ký tự đó.

## 13. MultiResourceItemReader và header của nhiều file

Khi dùng `MultiResourceItemReader` để đọc nhiều file, mỗi resource có thể có header riêng. Reader delegate thường được mở lại cho từng resource. Nếu delegate là `FlatFileItemReader` và cấu hình `linesToSkip(1)`, dòng đầu của mỗi file được mở sẽ bị bỏ qua.

Ví dụ:

```text
part-001.csv:
orderId,customerId,amount
1001,C001,250.00

part-002.csv:
orderId,customerId,amount
1002,C002,175.50
```

Nếu cả hai file đều có header, cấu hình skip một dòng cho mỗi resource là phù hợp.

Nhưng nếu chỉ file đầu tiên có header:

```text
part-001.csv:
orderId,customerId,amount
1001,C001,250.00

part-002.csv:
1002,C002,175.50
```

thì delegate với `linesToSkip(1)` sẽ bỏ mất item dữ liệu đầu tiên của `part-002.csv`. Cần một chiến lược khác, ví dụ tiền xử lý file, dùng reader delegate có cấu hình skip thay đổi theo resource, hoặc đảm bảo upstream tạo các file cùng một định dạng.

Nếu header của các file có thể khác nhau, callback nên xác thực từng resource và ghi nhận tên resource trong thông báo lỗi. Không nên chỉ xác minh file đầu tiên rồi giả định tất cả file còn lại có cùng schema.

## 14. Header thay đổi theo phiên bản schema

Một hệ thống có thể thay đổi file schema theo thời gian, ví dụ thêm cột `currency` hoặc đổi tên `customerId` thành `clientId`. Bỏ qua header cố định mà không kiểm tra có thể khiến job vẫn chạy nhưng ánh xạ dữ liệu sai.

Có thể xử lý theo một trong các hướng:

- **Schema cố định:** so sánh header với danh sách cột kỳ vọng và từ chối nếu khác.
- **Schema có version:** đọc dòng metadata/version rồi chọn tokenizer và mapper tương ứng.
- **Schema linh hoạt:** parse header thành map tên cột sang index và dùng mapper theo tên.
- **Chuẩn hóa đầu vào:** chuyển file của các phiên bản khác nhau về một định dạng chuẩn trước khi chạy batch chính.

Nếu schema thay đổi làm thay đổi ý nghĩa dữ liệu, không nên âm thầm bỏ qua cột mới hoặc cột bị thiếu. Hãy xác định rõ cột bắt buộc, cột tùy chọn và giá trị mặc định.

## 15. Ví dụ header động theo tên cột

Với schema động, callback có thể parse header và cấu hình tokenizer cho các dòng dữ liệu tiếp theo. Ý tưởng là dùng một tokenizer để đọc header thành danh sách tên, rồi gán danh sách đó vào tokenizer dữ liệu.

Ví dụ khung:

```java
DelimitedLineTokenizer headerTokenizer = new DelimitedLineTokenizer();
headerTokenizer.setDelimiter(",");

DelimitedLineTokenizer dataTokenizer = new DelimitedLineTokenizer();
dataTokenizer.setDelimiter(",");

DefaultLineMapper<FieldSet> lineMapper = new DefaultLineMapper<>();
lineMapper.setLineTokenizer(dataTokenizer);
lineMapper.setFieldSetMapper(fieldSet -> fieldSet);

FlatFileItemReader<FieldSet> reader = new FlatFileItemReader<>();
reader.setName("dynamicHeaderReader");
reader.setResource(new FileSystemResource(inputFile));
reader.setLinesToSkip(1);
reader.setLineMapper(lineMapper);
reader.setSkippedLinesCallback(headerLine -> {
    String[] names = headerTokenizer.tokenize(headerLine).getValues();
    validateAllowedColumns(names);
    dataTokenizer.setNames(names);
});
```

Đây là khung minh họa, cần bổ sung hàm `validateAllowedColumns` và mapper nghiệp vụ. Trong ứng dụng thực tế, nên kiểm tra trùng tên cột, cột bắt buộc, cột lạ và thứ tự theo schema version. Nếu `LineMapper` hoặc tokenizer được chia sẻ giữa nhiều step/job execution, phải bảo đảm cấu hình động không bị rò sang execution khác; dùng bean step-scoped riêng cho reader và tokenizer có state.

Nếu header chỉ dùng để xác thực một schema cố định, cấu hình `.names(...)` tĩnh đơn giản và an toàn hơn.

## 16. Restart khi reader bỏ qua header

`FlatFileItemReader` hỗ trợ lưu state thông qua `ItemStream`. Khi restart, reader sử dụng checkpoint đã lưu để tiếp tục từ vị trí tương ứng. Việc bỏ qua header là một phần của cách reader mở và định vị file.

Để restart đúng:

- Giữ tên reader ổn định.
- Giữ cùng file đầu vào và nội dung file qua lần restart.
- Giữ cấu hình `linesToSkip` không thay đổi giữa các execution của cùng instance.
- Bật `saveState(true)` nếu cần khôi phục vị trí đọc.
- Không tự bỏ qua thêm header trong custom restart code ngoài cơ chế của reader.
- Không thay đổi số dòng preamble/header trong file sau khi checkpoint đã được lưu.

Ví dụ, lần chạy đầu dùng `linesToSkip(1)` và đã commit 500 item. Nếu file được thay đổi bằng cách thêm một dòng metadata ở đầu trước khi restart, checkpoint theo số item có thể trỏ tới vị trí khác. Điều này có thể làm reader bỏ sót hoặc đọc trùng record.

Callback cho dòng bị skip chủ yếu phục vụ xử lý các dòng bị bỏ qua khi reader mở resource. Không nên dùng callback làm nơi duy nhất lưu trạng thái nghiệp vụ cần khôi phục qua restart. Nếu header chứa version hoặc checksum cần kiểm tra, hãy lưu thông tin đó vào execution context/manifest sau khi xác nhận và xác minh lại nguồn khi restart.

## 17. Header callback và lỗi khi mở reader

Callback được thực hiện trong quá trình reader bỏ qua các dòng đầu. Nếu callback phát hiện header sai và ném exception, reader không thể mở thành công theo cấu hình đó và step sẽ thất bại.

Đây thường là hành vi mong muốn vì schema không hợp lệ thì không nên tiếp tục xử lý. Tuy nhiên, cần hiểu:

- Lỗi callback không phải lỗi của một item đã được trả về.
- `skip(InvalidRecordException.class)` không phải cách chung để bỏ qua header sai.
- `SkipListener` không nhận header như một item nghiệp vụ.
- Nếu muốn tạo báo cáo validation chi tiết, có thể dùng một bước preflight riêng trước import.

Nếu callback chỉ log header và không validate, job có thể tiếp tục dù schema sai. Hãy chọn rõ mục tiêu: chỉ quan sát hay thực sự xác thực.

## 18. Encoding, line ending và nội dung header

Header có thể không khớp do khác biệt định dạng file:

- UTF-8 BOM ở đầu file.
- Windows CRLF và Unix LF.
- Khoảng trắng ở đầu/cuối tên cột.
- Chữ hoa/chữ thường khác nhau.
- Dấu nháy CSV quanh tên cột.
- Delimiter khác dấu phẩy, ví dụ tab hoặc semicolon.

Hãy xác định hợp đồng file và cấu hình reader/tokenizer tương ứng:

```java
reader.setEncoding("UTF-8");
reader.setLinesToSkip(1);
```

Với file TSV, cấu hình delimiter là tab. Với file dùng semicolon, cấu hình `;`. Không tự động thay delimiter dựa trên một dòng bất kỳ nếu chưa có quy tắc xác định.

Nếu normalize header, chỉ chuẩn hóa những khác biệt được hợp đồng cho phép. Ví dụ trim khoảng trắng có thể hợp lý, nhưng chuyển mọi tên cột về lowercase có thể che giấu hai tên cột khác nhau trong một schema phân biệt chữ hoa/thường.

## 19. Bảo đảm mỗi resource có header đúng một lần

Đối với một file đơn, cấu hình `linesToSkip(1)` giả định header nằm ở dòng đầu. Nếu file có nhiều header lặp giữa các trang hoặc do upstream nối file, `linesToSkip` không tự bỏ các header xuất hiện giữa file.

Ví dụ file bị nối từ hai export:

```csv
orderId,customerId,amount
1001,C001,250.00
1002,C002,175.50
orderId,customerId,amount
1003,C003,420.00
```

Header thứ hai sẽ được đọc như một dòng dữ liệu. Nếu không muốn điều này, hãy sửa upstream để tạo một header duy nhất hoặc dùng một line mapper/processor có quy tắc nhận diện header lặp rõ ràng. Không dùng `linesToSkip(2)` vì nó sẽ bỏ mất record dữ liệu đầu tiên.

Nếu file được tạo từ nhiều resource, nên ưu tiên một header cho mỗi resource và dùng `MultiResourceItemReader` với delegate skip một dòng, hoặc chuẩn hóa file trước khi import. Hợp đồng đầu vào cần nói rõ header nằm ở đầu mỗi file hay chỉ đầu tập hợp.

## 20. Header và comment trong MultiResourceItemReader

Khi đọc nhiều file, có thể mỗi file có phần metadata và header riêng. Delegate `FlatFileItemReader` được mở lại theo resource, vì vậy `linesToSkip` và callback áp dụng theo từng lần mở delegate.

Nếu cấu trúc mỗi file giống nhau:

```text
part-001.csv: metadata, header, data...
part-002.csv: metadata, header, data...
part-003.csv: metadata, header, data...
```

delegate có thể bỏ qua cùng số dòng ở mỗi file. Nếu file đầu có metadata nhưng các file sau không có, một số dòng dữ liệu có thể bị bỏ nhầm. Hãy thống nhất định dạng nguồn hoặc chọn chiến lược reader theo resource.

Với nhiều file, nên đưa resource filename vào log/correlation context để khi header sai có thể biết chính xác file nào không hợp lệ.

## 21. Kiểm thử bỏ qua header

Test nên xác nhận reader trả đúng item và header không xuất hiện trong output.

Các trường hợp cơ bản:

1. File có một header và nhiều record: chỉ record được trả về.
2. File không có header nhưng cấu hình skip một dòng: xác nhận test phát hiện record đầu bị mất hoặc validator từ chối cấu hình.
3. Header sai tên cột: callback từ chối mở reader.
4. Header sai thứ tự cột: validation phát hiện thay đổi schema.
5. File có BOM hoặc encoding khác: kiểm tra hành vi chuẩn hóa theo hợp đồng.
6. File rỗng hoặc chỉ có header: reader trả hết dữ liệu hợp lệ mà không tạo item.
7. File ngắn hơn `linesToSkip`: xác nhận ứng dụng xử lý rõ ràng trường hợp thiếu header/preamble.
8. Multi-resource: mỗi file có header thì chỉ header bị bỏ, không mất record đầu.
9. Restart sau một số chunk đã commit: reader tiếp tục đúng vị trí và không xử lý header thành item.
10. File bị thay đổi trước restart: validation phát hiện checksum/version khác nếu ứng dụng yêu cầu nguồn bất biến.

Ví dụ unit/integration test dùng `FlatFileItemReader` trực tiếp:

```java
FlatFileItemReader<String> reader = new FlatFileItemReader<>();
reader.setName("testReader");
reader.setResource(new ByteArrayResource(
        ("orderId,amount\n1001,250.00\n1002,175.50\n")
                .getBytes(StandardCharsets.UTF_8)));
reader.setLinesToSkip(1);
reader.setLineMapper((line, lineNumber) -> line);

reader.open(new ExecutionContext());
assertEquals("1001,250.00", reader.read());
assertEquals("1002,175.50", reader.read());
assertNull(reader.read());
reader.close();
```

Ví dụ kiểm tra cơ chế skip cơ bản. Trong test thực tế nên dùng `try/finally` để đóng reader nếu assertion thất bại và có thể dùng `skippedLinesCallback` để xác nhận header được nhận đúng.

## 22. Ví dụ kiểm tra header và dữ liệu cùng lúc

Một test có thể xác nhận callback nhận header và reader chỉ trả các dòng dữ liệu:

```java
AtomicReference<String> capturedHeader = new AtomicReference<>();

reader.setLinesToSkip(1);
reader.setSkippedLinesCallback(capturedHeader::set);

reader.open(new ExecutionContext());
try {
    assertEquals("orderId,amount", capturedHeader.get());
    assertEquals("1001,250.00", reader.read());
    assertEquals("1002,175.50", reader.read());
    assertNull(reader.read());
} finally {
    reader.close();
}
```

Đây là khung test; cần cấu hình resource và line mapper trước khi mở reader. Nếu có nhiều dòng skip, callback sẽ được gọi nhiều lần và test cần kiểm tra danh sách các dòng thay vì một giá trị đơn.

## 23. Các lỗi cấu hình thường gặp

| Tình huống | Nguyên nhân | Cách xử lý |
|---|---|---|
| Header bị map thành item | Không cấu hình `linesToSkip` | Dùng `linesToSkip(1)` khi file có một header |
| Mất record dữ liệu đầu tiên | Cấu hình skip dù file không có header hoặc skip quá nhiều | Xác định hợp đồng số dòng đầu trước khi chạy |
| Header sai nhưng job vẫn chạy | Chỉ bỏ qua header, không xác thực schema | Dùng `skippedLinesCallback` để kiểm tra |
| Cột bị map nhầm | Header đổi thứ tự nhưng mapper vẫn dùng vị trí cũ | So sánh cả tên và thứ tự cột |
| Header có dấu phẩy trong tên bị parse sai | Dùng `String.split` thay cho CSV tokenizer | Parse bằng tokenizer có hỗ trợ quote |
| Header không khớp dù nhìn giống nhau | BOM, encoding hoặc whitespace | Chỉ định encoding và chuẩn hóa có kiểm soát |
| Header lặp giữa file trở thành item | `linesToSkip` chỉ áp dụng cho phần đầu file | Chuẩn hóa nguồn hoặc nhận diện header lặp riêng |
| Multi-file mất dòng dữ liệu đầu file sau | Delegate skip header cho mỗi file nhưng file sau không có header | Chuẩn hóa cấu trúc hoặc thay đổi chiến lược theo resource |
| Callback chạy nhiều lần ngoài dự kiến | Có nhiều dòng skip hoặc nhiều resource | Theo dõi vị trí dòng và tên resource |
| Restart đọc sai dữ liệu | File hoặc số dòng header thay đổi sau checkpoint | Giữ input bất biến, ổn định `linesToSkip` và lưu source version |
| Header lỗi bị xử lý như item skip | Nhầm callback/open exception với item exception | Xử lý validation header ở callback/preflight step |

## 24. Quy trình thiết kế header handling

1. **Xác định định dạng nguồn:** CSV, TSV, fixed-width hay text có preamble.
2. **Xác định vị trí header:** đầu mỗi file, đầu toàn bộ tập hợp hay vị trí động.
3. **Cấu hình `linesToSkip`:** dùng đúng số dòng vật lý đầu cần bỏ qua.
4. **Quyết định có cần callback không:** chỉ skip hay cần log/validate/đọc metadata.
5. **Xác thực schema:** kiểm tra tên, số lượng, thứ tự và cột bắt buộc.
6. **Cấu hình encoding/delimiter/quote:** bảo đảm header và data được parse cùng quy tắc.
7. **Xử lý nhiều resource:** xác định mỗi file có header hay chỉ file đầu tiên.
8. **Giữ nguồn ổn định qua restart:** không thay đổi header, thứ tự dòng hoặc nội dung file sau checkpoint.
9. **Kiểm thử trường hợp biên:** file rỗng, chỉ header, BOM, header sai và header lặp.
10. **Theo dõi lỗi theo resource:** ghi tên file và thông tin dòng để dễ điều tra.

## 25. Những nguyên tắc cần nhớ

- `linesToSkip(n)` bỏ qua `n` dòng đầu của resource; nó không phải skip policy cho item.
- Với file có một header ở đầu, dùng `linesToSkip(1)`.
- `skippedLinesCallback` nhận từng dòng bị bỏ qua, phù hợp để log hoặc xác thực header.
- Header bị bỏ qua không đi qua processor/writer và không được tính như item đọc thông thường.
- Nếu header sai, callback có thể làm reader/step thất bại; đây là lỗi cấu trúc file, không phải item skip.
- Kiểm tra cả tên, số lượng và thứ tự cột nếu mapping dựa trên vị trí.
- Dùng tokenizer CSV phù hợp thay cho `String.split` khi header có quoting hoặc delimiter trong tên cột.
- Chỉ định encoding rõ ràng và chú ý BOM.
- `linesToSkip` đếm dòng vật lý cố định; nó không tự tìm header sau các dòng trống/preamble động.
- Với `MultiResourceItemReader`, delegate có thể bỏ header ở mỗi resource; bảo đảm mọi file có cùng quy ước.
- Header lặp giữa file không được xử lý bởi `linesToSkip` ở đầu file.
- Giữ cấu hình skip và input ổn định qua restart; reader cần lưu state để tiếp tục đúng checkpoint.
- Kiểm thử header cùng dữ liệu đầu ra, không chỉ kiểm tra job kết thúc thành công.

Bỏ qua dòng header là cấu hình nhỏ nhưng ảnh hưởng trực tiếp đến tính đúng đắn của file import. Khi dùng `linesToSkip` đúng số dòng, tận dụng callback để xác thực schema khi cần và giữ cấu trúc nguồn ổn định qua restart, `FlatFileItemReader` có thể xử lý dữ liệu mà không đưa metadata của file vào pipeline nghiệp vụ hoặc vô tình bỏ mất record đầu tiên.
