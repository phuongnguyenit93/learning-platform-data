# RecordSeparatorPolicy

Trong Spring Batch, file đầu vào thường được đọc theo từng dòng vật lý. Tuy nhiên, một **record nghiệp vụ** không phải lúc nào cũng nằm trên đúng một dòng. Ví dụ, một trường CSV được đặt trong dấu nháy có thể chứa newline; một file fixed-width có thể dùng ký hiệu continuation để nối nhiều dòng; hoặc một định dạng trao đổi có quy tắc riêng để xác định khi nào một record đã hoàn chỉnh.

`RecordSeparatorPolicy` cho phép `FlatFileItemReader` xác định các dòng vật lý nào thuộc cùng một record logic. Policy quyết định khi nào record đã kết thúc và có thể biến đổi nội dung trước hoặc sau khi ghép dòng. Sau khi record hoàn chỉnh, reader mới chuyển record đó tới `LineMapper` để token hóa và ánh xạ thành object.

Điểm quan trọng là `RecordSeparatorPolicy` giải quyết **ranh giới record**, không thực hiện parse toàn bộ định dạng CSV, JSON hay fixed-width. Việc xác định field, kiểu dữ liệu và validation vẫn thuộc `LineTokenizer`, `FieldSetMapper`, `LineMapper` hoặc logic ứng dụng.

## Dòng vật lý và record logic

Một dòng vật lý là một đoạn văn bản được kết thúc bởi line separator của file, chẳng hạn LF hoặc CRLF. Một record logic là đơn vị dữ liệu mà ứng dụng muốn xử lý như một item.

Với file đơn giản, một dòng vật lý tương ứng một record:

```text
O-1001,An,120.50
O-1002,Binh,90.00
O-1003,Chi,75.00
```

Nhưng CSV có thể chứa newline bên trong trường được quote:

```csv
orderId,customerName,note
O-1001,An,"Giao hàng tại cổng A"
O-1002,Binh,"Khách yêu cầu gọi trước
khi giao hàng"
O-1003,Chi,"Để hàng tại quầy lễ tân"
```

Trong ví dụ trên, record `O-1002` trải qua hai dòng vật lý nhưng vẫn là một record logic. Nếu reader coi mỗi dòng vật lý là một record độc lập, dòng `khi giao hàng"` sẽ bị parse như một item riêng và có thể gây lỗi số cột hoặc dữ liệu sai.

```text
Physical lines:
  line 1: orderId,customerName,note
  line 2: O-1001,An,"Giao hàng tại cổng A"
  line 3: O-1002,Binh,"Khách yêu cầu gọi trước
  line 4: khi giao hàng"
  line 5: O-1003,Chi,"Để hàng tại quầy lễ tân"

Logical records:
  record 1 = line 1
  record 2 = line 2
  record 3 = line 3 + line 4
  record 4 = line 5
```

`RecordSeparatorPolicy` là nơi mô tả quy tắc ghép line 3 và line 4 thành một record trước khi mapper parse dữ liệu.

## RecordSeparatorPolicy làm gì?

`RecordSeparatorPolicy` nằm trong package `org.springframework.batch.item.file.separator`. Interface cung cấp ba phương thức:

```java
public interface RecordSeparatorPolicy {

    String preProcess(String record);

    boolean isEndOfRecord(String record);

    String postProcess(String record);
}
```

Ý nghĩa tổng quát:

| Phương thức | Vai trò |
| --- | --- |
| `preProcess(record)` | Biến đổi nội dung record đang được ghép trước khi reader tiếp tục kiểm tra ranh giới |
| `isEndOfRecord(record)` | Trả về `true` khi nội dung hiện tại đã đủ để tạo một record logic hoàn chỉnh |
| `postProcess(record)` | Biến đổi record sau khi policy xác định record đã kết thúc, trước khi chuyển cho bước mapping |

`isEndOfRecord` là quyết định chính. Nếu trả về `false`, reader tiếp tục lấy dòng vật lý tiếp theo và ghép vào record đang xây dựng. Khi trả về `true`, reader hoàn tất record và chuyển nội dung đã xử lý tới `LineMapper`.

`preProcess` và `postProcess` có thể trả nguyên nội dung nếu không cần biến đổi. Một policy chỉ cần xác định ranh giới record có thể để hai phương thức này pass-through.

## RecordSeparatorPolicy trong FlatFileItemReader

`FlatFileItemReader` đọc resource theo từng dòng, sử dụng `RecordSeparatorPolicy` để gom các dòng thành record. Sau khi có record hoàn chỉnh, reader gọi `LineMapper` để chuyển chuỗi thành item.

```text
Resource / file
      |
      v
Đọc physical line
      |
      v
RecordSeparatorPolicy
      |
      +-- isEndOfRecord = false
      |        |
      |        +--> đọc line tiếp theo và ghép vào record
      |
      +-- isEndOfRecord = true
               |
               v
        postProcess(record)
               |
               v
          LineMapper
               |
               v
          ItemReader trả item
```

Policy được cấu hình trực tiếp trên reader. Ví dụ với Spring Batch 5:

```java
@Bean
@StepScope
FlatFileItemReader<OrderInput> orderReader(
        @Value("#{jobParameters['inputFile']}") String inputFile,
        RecordSeparatorPolicy orderRecordSeparatorPolicy) {

    return new FlatFileItemReaderBuilder<OrderInput>()
            .name("orderReader")
            .resource(new FileSystemResource(inputFile))
            .recordSeparatorPolicy(orderRecordSeparatorPolicy)
            .lineMapper(orderLineMapper())
            .saveState(true)
            .build();
}
```

Trong ví dụ, reader dùng policy để xác định ranh giới record, sau đó `orderLineMapper()` ánh xạ record hoàn chỉnh thành `OrderInput`. `RecordSeparatorPolicy` không thay thế `LineMapper`.

Nếu không cần xử lý record nhiều dòng, có thể dùng policy đơn giản phù hợp với định dạng một dòng một record. Spring Batch cung cấp các implementation mặc định trong package `separator`; cần chọn implementation theo semantics của phiên bản đang dùng và định dạng file thực tế.

## Phân biệt RecordSeparatorPolicy và LineMapper

Hai thành phần này xử lý hai tầng khác nhau:

| Thành phần | Trách nhiệm | Ví dụ |
| --- | --- | --- |
| `RecordSeparatorPolicy` | Xác định một record gồm những physical line nào | Nối hai dòng CSV khi trường quote chưa đóng |
| `LineMapper` | Chuyển một record logic thành object | Ánh xạ `O-1002,Binh,"..."` thành `OrderInput` |
| `LineTokenizer` | Tách record thành các field | Phân tách CSV hoặc fixed-width columns |
| `FieldSetMapper` | Chuyển field thành object có kiểu | Tạo `OrderInput` và parse amount thành `BigDecimal` |

Nếu `LineMapper` nhận một chuỗi bị cắt giữa record, mapper không thể tự biết dòng tiếp theo thuộc record trước hay record mới, trừ khi ứng dụng tự xây dựng logic đặc biệt. Việc xác định ranh giới nên được giải quyết trước ở `RecordSeparatorPolicy`.

Ngược lại, nếu ranh giới record đã đúng nhưng số cột hoặc kiểu dữ liệu sai, lỗi thuộc tokenizer/mapper hoặc validation. Không nên làm policy phức tạp để che lỗi dữ liệu field.

## Policy mặc định và policy đơn giản

Spring Batch có các implementation `RecordSeparatorPolicy` trong package `org.springframework.batch.item.file.separator`. Một policy đơn giản coi mỗi dòng được đọc là một record hoàn chỉnh; policy hỗ trợ continuation có thể coi một dòng chưa hoàn tất khi nó kết thúc bằng ký hiệu nối dòng. Tùy phiên bản, reader builder có thể cung cấp policy mặc định nếu ứng dụng không chỉ định.

Không nên dựa vào giả định về default mà không kiểm tra phiên bản Spring Batch và format input. Nếu file có quy tắc multiline cụ thể, hãy cấu hình policy tường minh và kiểm thử với các mẫu file thật, bao gồm record lỗi và ký tự escape.

### Khi nào dùng policy đơn giản?

Policy coi mỗi physical line là một record phù hợp khi:

- Mỗi dòng chứa đúng một record.
- Field không chứa newline.
- Producer bảo đảm không chia một record qua nhiều dòng.
- Các dòng continuation không xuất hiện trong format.

Với file như vậy, không cần custom policy. Dùng policy đơn giản giữ reader dễ hiểu và tránh việc ghép nhầm nhiều dòng khi file bị lỗi.

### Khi nào cần custom policy?

Custom policy phù hợp khi:

- Một field có thể chứa newline.
- Record dùng dấu quote hoặc dấu escape để xác định phần tiếp tục.
- Một ký hiệu ở cuối dòng báo rằng record chưa hoàn tất.
- Record có terminator riêng thay vì line separator thông thường.
- Format legacy có quy tắc ghép dòng đặc biệt.

Chỉ triển khai custom policy khi định dạng nguồn có quy tắc rõ ràng. Không nên đoán ranh giới record dựa trên số dòng hoặc độ dài chuỗi nếu format không bảo đảm điều đó.

## Ví dụ: CSV có trường quote nhiều dòng

Giả sử định dạng CSV sử dụng dấu `"` để bao trường và escape dấu quote bên trong bằng hai dấu quote liên tiếp (`""`). Một record kết thúc khi mọi trường quote đã được đóng.

Ví dụ:

```csv
id,description,amount
1,"Giao hàng tại tầng 2",100.00
2,"Khách ghi chú: ""gọi trước""
và giao sau 17:00",250.00
3,"Không có ghi chú",80.00
```

Record thứ hai gồm hai physical line. Hai dấu quote liên tiếp bên trong trường biểu diễn một dấu quote dữ liệu, không phải đóng/mở field.

### Custom policy minh họa

Một policy có thể quét record tích lũy để xác định trạng thái quote. Ví dụ sau giả định format CSV kiểu RFC 4180 đơn giản: delimiter là dấu phẩy, quote chỉ bắt đầu field tại đầu field và quote bên trong field được escape bằng `""`.

```java
public class QuotedCsvRecordSeparatorPolicy
        implements RecordSeparatorPolicy {

    @Override
    public String preProcess(String record) {
        return record;
    }

    @Override
    public boolean isEndOfRecord(String record) {
        return !hasOpenQuotedField(record);
    }

    @Override
    public String postProcess(String record) {
        return record;
    }

    private boolean hasOpenQuotedField(String record) {
        boolean inQuotes = false;
        boolean atFieldStart = true;

        for (int i = 0; i < record.length(); i++) {
            char current = record.charAt(i);

            if (inQuotes) {
                if (current == '"') {
                    if (i + 1 < record.length()
                            && record.charAt(i + 1) == '"') {
                        i++; // escaped quote: ""
                    } else {
                        inQuotes = false;
                    }
                }
            } else if (current == ',') {
                atFieldStart = true;
            } else if (current == '"' && atFieldStart) {
                inQuotes = true;
                atFieldStart = false;
            } else if (current != '\r' && current != '\n') {
                atFieldStart = false;
            }
        }

        return inQuotes;
    }
}
```

Policy này trả `false` khi đang ở trong một field quote chưa đóng; reader tiếp tục ghép physical line tiếp theo. Khi quote được đóng, policy trả `true` và record được chuyển cho mapper.

Đây là ví dụ minh họa cho một dialect CSV cụ thể, không phải parser CSV đầy đủ. Nó giả định quote chỉ xuất hiện ở đầu field và dùng `""` để escape. Nếu producer cho phép whitespace trước quote, delimiter khác, escape character khác hoặc quote không chuẩn, cần điều chỉnh thuật toán theo format thực tế. Với CSV phức tạp, hãy cân nhắc dùng parser chuyên dụng có hỗ trợ multiline thay vì tự viết một parser không đầy đủ.

### Cấu hình policy cho reader

```java
@Bean
RecordSeparatorPolicy quotedCsvRecordSeparatorPolicy() {
    return new QuotedCsvRecordSeparatorPolicy();
}

@Bean
@StepScope
FlatFileItemReader<OrderInput> multilineOrderReader(
        @Value("#{jobParameters['inputFile']}") String inputFile,
        RecordSeparatorPolicy quotedCsvRecordSeparatorPolicy,
        LineMapper<OrderInput> orderLineMapper) {

    return new FlatFileItemReaderBuilder<OrderInput>()
            .name("multilineOrderReader")
            .resource(new FileSystemResource(inputFile))
            .recordSeparatorPolicy(quotedCsvRecordSeparatorPolicy)
            .lineMapper(orderLineMapper)
            .saveState(true)
            .build();
}
```

Reader vẫn cần một `LineMapper`/tokenizer có cùng quy tắc quote và escape. Policy chỉ bảo đảm toàn bộ nội dung của một record được gom trước khi mapping.

## Ví dụ: continuation marker ở cuối dòng

Một số định dạng legacy dùng ký tự `\` ở cuối dòng để báo record còn tiếp tục. Ví dụ:

```text
CUSTOMER|1001|Nguyen Van A|Ha Noi\
|10000000|ACTIVE
CUSTOMER|1002|Tran Thi B|Da Nang\
|8000000|ACTIVE
```

Theo format này, dòng kết thúc bằng một backslash chưa phải record hoàn chỉnh. Dòng tiếp theo được ghép vào record; ký hiệu continuation có thể cần được loại bỏ trước khi mapper parse.

Một policy có thể kiểm tra ký tự continuation ở cuối record và loại bỏ marker cùng line break theo cách reader ghép chuỗi của phiên bản đang dùng. Vì cách nối physical line và ký tự line separator phụ thuộc implementation, hãy kiểm tra input thực tế bằng test trước khi triển khai. Nếu dùng policy continuation có sẵn của Spring Batch và semantics phù hợp, ưu tiên tái sử dụng thay vì viết lại.

Ví dụ logic cốt lõi cho format đơn giản:

```java
public class BackslashContinuationPolicy implements RecordSeparatorPolicy {

    @Override
    public String preProcess(String record) {
        return record;
    }

    @Override
    public boolean isEndOfRecord(String record) {
        return !endsWithContinuationMarker(record);
    }

    @Override
    public String postProcess(String record) {
        return removeContinuationSeparators(record);
    }

    private boolean endsWithContinuationMarker(String record) {
        int last = record.length() - 1;
        return last >= 0 && record.charAt(last) == '\\';
    }

    private String removeContinuationSeparators(String record) {
        return record.replace("\\\r\n", "")
                .replace("\\\n", "");
    }
}
```

Đây là skeleton cho format có quy tắc nối dòng rất cụ thể. Nếu record tích lũy không giữ line separator theo dạng `\n` hoặc `\r\n`, cần điều chỉnh `postProcess`. Cũng cần phân biệt một backslash continuation thực sự với hai backslash dữ liệu ở cuối dòng; ví dụ trên chưa xử lý mọi quy tắc escape có thể có.

## preProcess và postProcess nên làm gì?

Hai method này cho phép policy chuẩn hóa nội dung record trong quá trình ghép dòng.

### preProcess

Có thể dùng `preProcess` để xử lý nội dung trước khi tiếp tục xác định ranh giới. Ví dụ format legacy có marker cần bỏ hoặc chuẩn hóa line fragment trước khi ghép. Việc biến đổi phải giữ đúng thông tin cần cho `isEndOfRecord`.

Không nên loại bỏ ký tự quote hoặc delimiter quá sớm nếu chính những ký tự đó được dùng để xác định record đã kết thúc. Nếu xóa quote trước khi kiểm tra trạng thái quote, policy có thể kết luận sai rằng record đã hoàn chỉnh.

### isEndOfRecord

Đây là phương thức quyết định reader có cần đọc thêm physical line không. Logic nên:

- Có tính xác định với cùng nội dung record.
- Không phụ thuộc trạng thái mutable toàn cục giữa các item.
- Xử lý đúng escape/quote/continuation theo format.
- Có hành vi rõ ràng khi record malformed hoặc quá dài.
- Không thực hiện I/O hoặc gọi service bên ngoài.

Vì method có thể được gọi nhiều lần trong quá trình reader ghép record, không nên tăng counter nghiệp vụ hoặc ghi database ở đây.

### postProcess

Có thể dùng `postProcess` để loại bỏ continuation marker hoặc chuẩn hóa phần phân cách sau khi record đã hoàn chỉnh. Nội dung trả về sẽ được dùng ở bước mapping.

Không nên dùng `postProcess` để che lỗi dữ liệu bằng cách tự động sửa một record malformed mà không có quy tắc nghiệp vụ rõ ràng. Nếu record không hợp lệ, hãy để mapper/validator báo lỗi phù hợp hoặc ghi nhận reject theo policy riêng.

## Record không bao giờ kết thúc

Nếu file có dấu quote mở nhưng không có quote đóng, `isEndOfRecord` có thể luôn trả `false` cho tới EOF. Đây là lỗi dữ liệu cần được xử lý rõ ràng.

Ví dụ:

```csv
id,description
1,"Nội dung bắt đầu nhưng không đóng quote
2,Record tiếp theo
```

Nếu policy chỉ chờ quote đóng, dòng thứ hai có thể bị ghép vào record đầu và reader tiếp tục chờ đến EOF. Tùy implementation và phiên bản, reader có thể ném lỗi khi EOF tới mà record chưa hoàn chỉnh. Không nên tự động coi EOF là kết thúc hợp lệ nếu format yêu cầu quote phải đóng.

Các cách xử lý:

- Fail step với lỗi parse rõ ràng để operator sửa file.
- Đưa file vào khu vực quarantine/error để điều tra.
- Ghi nhận file identity, record/line position và nguyên nhân lỗi.
- Chỉ áp dụng quy tắc recover nếu nghiệp vụ định nghĩa cách khôi phục record malformed.

Không nên đặt một giới hạn số dòng rồi tự cắt record mà không báo lỗi; điều đó có thể tạo dữ liệu sai nhưng trông có vẻ hợp lệ.

## Giới hạn độ dài record

Record nhiều dòng có thể trở nên rất lớn nếu nguồn lỗi hoặc producer không đóng quote. Một policy cần có chiến lược giới hạn để tránh giữ chuỗi tăng không kiểm soát trong memory.

Có thể thiết kế policy wrapper theo giới hạn ký tự hoặc số dòng tích lũy, rồi ném exception chuyên biệt khi vượt ngưỡng. Cần hiểu rằng `RecordSeparatorPolicy` interface không cung cấp một callback riêng cho physical line count; nếu cần giới hạn số dòng, có thể phải theo dõi thông tin trong policy hoặc triển khai reader/wrapper phù hợp với version và lifecycle. Nếu dùng mutable counter trong policy, cần bảo đảm policy instance không bị chia sẻ đồng thời giữa nhiều reader/step.

Giới hạn nên dựa trên hợp đồng file, ví dụ tối đa 20 dòng cho một record hoặc tối đa 1 MB nội dung. Khi vượt giới hạn, fail sớm với thông tin đủ để tìm record lỗi; không để một record kéo dài tới hết file và chiếm bộ nhớ lớn.

## RecordSeparatorPolicy và lỗi parse

Lỗi có thể phát sinh ở hai tầng:

| Tầng | Ví dụ | Thành phần chịu trách nhiệm |
| --- | --- | --- |
| Ranh giới record | Quote chưa đóng, continuation marker không hợp lệ, record không kết thúc | `RecordSeparatorPolicy` / reader |
| Nội dung record | Thiếu cột, amount không phải số, ngày sai định dạng | `LineMapper`, tokenizer, `FieldSetMapper` hoặc processor |

Không phải mọi lỗi parse đều cần sửa trong policy. Nếu record đã được tách đúng nhưng dữ liệu field sai, giữ logic validation ở tầng mapping/processing để có thông báo lỗi cụ thể.

Có thể dùng exception riêng cho lỗi ranh giới record:

```java
public class InvalidRecordBoundaryException extends RuntimeException {
    public InvalidRecordBoundaryException(String message) {
        super(message);
    }
}
```

Tùy cách policy được gọi và reader xử lý exception trong phiên bản Spring Batch, exception có thể được bọc trong lỗi đọc file. Test nên kiểm tra cause chain và record/file identity thay vì phụ thuộc vào message cố định.

## Skip và retry khi RecordSeparatorPolicy phát hiện lỗi

`RecordSeparatorPolicy` tham gia quá trình đọc file, nên lỗi ở tầng này thường được nhìn nhận như lỗi đọc. Nếu muốn skip một record malformed, cần xác định reader có thể khôi phục ranh giới record tiếp theo một cách đáng tin cậy hay không.

Nếu quote chưa đóng, reader không biết dòng nào là đầu record tiếp theo. Bỏ qua chuỗi hiện tại có thể đồng nghĩa bỏ nhiều record hợp lệ. Vì vậy, không nên cấu hình skip rộng cho mọi lỗi separator chỉ để job tiếp tục.

Retry cũng không giúp ích cho file malformed bất biến; thử đọc lại cùng nội dung thường tạo cùng lỗi. Retry chỉ phù hợp nếu lỗi có khả năng tạm thời, ví dụ resource chưa sẵn sàng hoặc I/O gián đoạn. Với lỗi format cố định, fail và đưa file vào quarantine thường an toàn hơn.

## Checkpoint và restart với record nhiều dòng

`FlatFileItemReader` có thể lưu state để restart, nhưng record nhiều dòng làm ranh giới giữa physical line và logical item trở nên quan trọng. Checkpoint phải đại diện cho record đã được reader xử lý/commit theo lifecycle của reader.

Các nguyên tắc:

- Dùng reader có hỗ trợ `ItemStream` và `saveState(true)` khi cần restart.
- Đặt tên reader ổn định để key trong `ExecutionContext` không đổi.
- Giữ nguyên file path và nội dung nguồn qua restart; tốt nhất dùng file immutable hoặc version/checksum.
- Không thay đổi `RecordSeparatorPolicy` giữa lần chạy đầu và restart nếu format/semantics có thể khác.
- Nếu đổi thuật toán tách record, đánh giá khả năng tương thích với checkpoint cũ.
- Không sửa hoặc truncate file nguồn trong lúc job đang chạy hoặc còn có thể restart.

Ví dụ reader:

```java
@Bean
@StepScope
FlatFileItemReader<OrderInput> orderReader(
        @Value("#{jobParameters['inputFile']}") String inputFile,
        RecordSeparatorPolicy recordSeparatorPolicy,
        LineMapper<OrderInput> lineMapper) {

    return new FlatFileItemReaderBuilder<OrderInput>()
            .name("orderReader")
            .resource(new FileSystemResource(inputFile))
            .recordSeparatorPolicy(recordSeparatorPolicy)
            .lineMapper(lineMapper)
            .saveState(true)
            .build();
}
```

Nếu file được thay thế sau khi checkpoint đã lưu, reader có thể tiếp tục tại vị trí cũ nhưng dữ liệu phía sau đã thay đổi. Dùng immutable input hoặc xác minh checksum/version trước khi restart.

## Physical line number và logical record number

Khi record trải qua nhiều dòng, số thứ tự dòng vật lý khác với số thứ tự record. Ví dụ record thứ 10 có thể bắt đầu ở physical line 14 và kết thúc ở line 16.

Điều này ảnh hưởng tới log và xử lý lỗi:

- Thông báo “record 10 lỗi” hữu ích cho ứng dụng nghiệp vụ.
- Thông báo “physical line 16” hữu ích khi mở file trong editor.
- Nếu chỉ log một số dòng mà không phân biệt, operator có thể tìm sai vị trí.

Nên ghi cả file identity, record index và physical line range nếu reader/mapper có thể cung cấp. `RecordSeparatorPolicy` chỉ quyết định ranh giới; nó không nhất thiết tự cung cấp đầy đủ metadata dòng cho ứng dụng. Nếu cần line range chính xác, có thể dùng wrapper/reader tùy chỉnh hoặc bổ sung tracking phù hợp với API của phiên bản đang dùng.

## Header, comment và blank line

`RecordSeparatorPolicy` không thay thế cấu hình header, comment hoặc blank line của reader.

- `linesToSkip(...)` dùng để bỏ qua một số dòng đầu, thường là header.
- `skippedLinesCallback(...)` có thể nhận nội dung các dòng bị bỏ qua.
- `setComments(...)` cấu hình prefix comment theo reader API phù hợp.
- Blank line có thể được xử lý theo quy tắc reader/mapper.

Nếu file có header nhiều dòng, cần xác định cách skip header có tương thích với record separator hay không. Đừng giả định `linesToSkip(1)` luôn bỏ đúng một logical record nếu header có thể trải qua nhiều physical line. Hãy kiểm thử file thật và dùng reader/callback phù hợp.

## Thread safety và scope của policy

Một policy thường chỉ thực hiện phép kiểm tra chuỗi, nên có thể stateless và an toàn khi dùng chung nếu implementation không giữ mutable state. Tuy nhiên, nếu policy giữ counter, buffer hoặc thông tin giữa các lần gọi, không nên chia sẻ cùng instance cho nhiều reader/step chạy đồng thời.

Các nguyên tắc:

- Ưu tiên policy stateless: quyết định dựa trên chuỗi record được truyền vào.
- Nếu cần state, tạo instance theo reader/step scope hoặc bảo đảm đồng bộ rõ ràng.
- Không lưu dữ liệu của record trước trong singleton field nếu nhiều job có thể chạy cùng lúc.
- Không gọi database hoặc API trong `isEndOfRecord`.
- Không dùng `ThreadLocal` để truyền record state giữa callback nếu không có lifecycle cleanup rõ ràng.

Với partitioned step, mỗi partition có thể đọc file hoặc vùng file khác nhau. Nếu cùng dùng một policy stateful, state có thể bị trộn. Tốt nhất dùng policy stateless hoặc instance riêng cho từng reader.

## Hiệu năng khi ghép record nhiều dòng

`FlatFileItemReader` cần giữ record hiện tại trong memory cho tới khi policy xác định record hoàn chỉnh. Record nhiều dòng hoặc rất lớn làm tăng allocation và chi phí quét chuỗi.

Để giữ hiệu năng:

- Dùng thuật toán tuyến tính theo độ dài record; tránh quét lại nhiều lần không cần thiết.
- Không dùng regex phức tạp có nguy cơ backtracking trên chuỗi dài.
- Đặt giới hạn record size theo hợp đồng file.
- Tránh log toàn bộ record lỗi nếu record có thể lớn hoặc chứa dữ liệu nhạy cảm.
- Dùng parser chuyên dụng khi format có nhiều quy tắc quote/escape phức tạp.
- Đo throughput với record bình thường và record nhiều dòng gần giới hạn.

Nếu policy quét toàn bộ chuỗi tích lũy sau mỗi physical line, record gồm N dòng có thể bị quét lặp nhiều lần. Với record rất dài, tổng công việc có thể tăng đáng kể. Nếu cần tối ưu, cân nhắc parser/reader có thể duy trì trạng thái incremental, nhưng vẫn phải bảo đảm tương thích với contract `RecordSeparatorPolicy` và lifecycle của reader.

## Kiểm thử RecordSeparatorPolicy

Nên kiểm thử policy độc lập bằng unit test, sau đó kiểm thử tích hợp với `FlatFileItemReader`. Unit test xác nhận quy tắc quote/continuation; integration test chứng minh reader thực sự gom physical line trước khi gọi mapper.

### Unit test các trường hợp ranh giới

Với quote-aware policy, tối thiểu cần có:

| Input record đang tích lũy | `isEndOfRecord` mong đợi | Lý do |
| --- | --- | --- |
| `1,An,100` | `true` | Không có field quote đang mở |
| `2,Binh,"ghi chú` | `false` | Quote chưa đóng |
| `2,Binh,"ghi chú\nphần tiếp"` | `true` | Quote đã đóng |
| `3,Chi,"nói ""xin chào"""` | `true` | Quote escape hợp lệ |
| `4,Du,"mở quote` | `false` | Record chưa hoàn chỉnh |

Ví dụ JUnit:

```java
class QuotedCsvRecordSeparatorPolicyTest {

    private final QuotedCsvRecordSeparatorPolicy policy =
            new QuotedCsvRecordSeparatorPolicy();

    @Test
    void completesSingleLineRecord() {
        assertTrue(policy.isEndOfRecord("1,An,100"));
    }

    @Test
    void waitsForClosingQuote() {
        assertFalse(policy.isEndOfRecord("2,Binh,\"ghi chú"));
        assertTrue(policy.isEndOfRecord(
                "2,Binh,\"ghi chú\nphần tiếp\""));
    }

    @Test
    void acceptsEscapedQuoteInsideQuotedField() {
        assertTrue(policy.isEndOfRecord(
                "3,Chi,\"nói \"\"xin chào\"\"\""));
    }
}
```

Các test này dựa trên dialect được mô tả trong ví dụ. Nếu delimiter/escape khác, fixture cần thay đổi tương ứng.

### Kiểm thử preProcess và postProcess

Nếu policy biến đổi record, cần xác nhận:

- `preProcess` không xóa ký tự cần cho việc xác định ranh giới.
- `postProcess` chỉ loại bỏ marker hợp lệ.
- Dữ liệu field không bị mất hoặc thay đổi ngoài ý muốn.
- Hai lần gọi với cùng input cho cùng kết quả nếu policy được thiết kế stateless.

### Integration test với FlatFileItemReader

Tạo file tạm có một record nhiều dòng, cấu hình reader với custom policy và `LineMapper` test ghi nhận chuỗi nhận được. Xác nhận reader trả về đúng số item và record thứ hai chứa newline nội bộ theo mong đợi.

Ví dụ cấu trúc test:

```java
@Test
void readerMapsMultilineCsvAsOneItem() throws Exception {
    Path file = tempDir.resolve("orders.csv");
    Files.writeString(file, """
            1,An,"Giao tại cổng A"
            2,Binh,"Gọi trước
            khi giao"
            3,Chi,"Để tại quầy"
            """);

    FlatFileItemReader<String> reader =
            new FlatFileItemReaderBuilder<String>()
                    .name("multilineTestReader")
                    .resource(new FileSystemResource(file))
                    .recordSeparatorPolicy(
                            new QuotedCsvRecordSeparatorPolicy())
                    .lineMapper((line, lineNumber) -> line)
                    .build();

    reader.open(new ExecutionContext());
    try {
        assertEquals("1,An,\"Giao tại cổng A\"", reader.read());
        assertEquals(
                "2,Binh,\"Gọi trước\nkhi giao\"",
                reader.read());
        assertEquals("3,Chi,\"Để tại quầy\"", reader.read());
        assertNull(reader.read());
    } finally {
        reader.close();
    }
}
```

Ví dụ giả định reader giữ newline giữa các physical line theo cách được kiểm tra trong phiên bản đang dùng. Nếu implementation chuẩn hóa line separator khác, điều chỉnh expected value theo contract thực tế. Test tích hợp quan trọng hơn việc chỉ gọi trực tiếp `isEndOfRecord`, vì nó xác nhận reader và policy phối hợp đúng.

### Kiểm thử EOF khi quote chưa đóng

Tạo file kết thúc khi record vẫn còn quote mở. Xác nhận reader báo lỗi theo hành vi đã định nghĩa và không trả một item giả có nội dung bị cắt. Nếu ứng dụng có quy trình quarantine, kiểm tra file được chuyển sang khu vực lỗi và metadata lưu nguyên nhân.

### Kiểm thử restart

Cho reader xử lý một số record, dừng step và restart cùng `JobInstance`. Xác nhận:

- Reader name không đổi.
- `saveState(true)` được bật.
- Input file không bị sửa giữa hai lần chạy.
- Policy và line mapping giữ cùng semantics.
- Reader tiếp tục đúng logical record, kể cả khi record trước đó trải qua nhiều physical line.
- Không bị bỏ sót hoặc lặp record đã commit.

### Kiểm thử hiệu năng và giới hạn

Tạo record nhiều dòng gần giới hạn cho phép và xác nhận thời gian xử lý/bộ nhớ nằm trong mức chấp nhận. Tạo record không kết thúc để kiểm tra policy không giữ dữ liệu tăng vô hạn và báo lỗi rõ ràng.

## Lỗi thường gặp

### Coi mỗi physical line là một record

Record multiline bị tách thành các item riêng, làm sai số field hoặc gây parse exception. Dùng policy phù hợp với format.

### Dùng RecordSeparatorPolicy để parse field

Policy chỉ xác định ranh giới record. Tách cột và chuyển kiểu thuộc `LineMapper`, tokenizer và mapper.

### Đếm quote quá đơn giản

Chỉ đếm số ký tự quote có thể sai khi có escaped quote, quote nằm trong dữ liệu không được quote hoặc dialect riêng. Xác định quy tắc quote chính xác và kiểm thử edge case.

### Xóa quote trong preProcess quá sớm

Policy mất thông tin để biết field đã đóng hay chưa. Giữ delimiter/quote cần thiết cho đến khi `isEndOfRecord` quyết định xong.

### Không xử lý quote mở tới EOF

Reader có thể ghép phần còn lại của file thành một record lớn hoặc báo lỗi muộn. Xác định hành vi malformed record và giới hạn kích thước.

### Retry lỗi format bất biến

Thử đọc lại cùng file không sửa được quote thiếu hoặc continuation marker sai. Fail/quarantine thường phù hợp hơn retry vô hạn.

### Chia sẻ policy stateful giữa nhiều reader

Mutable state có thể bị trộn giữa các job/partition. Ưu tiên policy stateless hoặc instance riêng theo reader.

### Thay đổi policy giữa restart

Checkpoint cũ có thể không còn tương thích với cách ghép record mới. Giữ semantics ổn định hoặc tạo logical job mới có chủ đích.

### Chỉ unit test policy mà không test reader

Reader có thể ghép line, xử lý EOF hoặc chuẩn hóa separator theo cách ảnh hưởng kết quả. Có integration test với file tạm và `FlatFileItemReader`.

## Nguyên tắc thiết kế

Khi sử dụng `RecordSeparatorPolicy`, hãy xác định:

1. Định dạng nguồn định nghĩa physical line và logical record như thế nào?
2. Một record có thể trải qua bao nhiêu dòng và điều kiện kết thúc là gì?
3. Quote, escape, continuation marker và delimiter được quy định ra sao?
4. `preProcess` và `postProcess` có cần biến đổi nội dung không?
5. Policy có stateless và xác định khi được gọi nhiều lần không?
6. Điều gì xảy ra khi record malformed hoặc quote chưa đóng tới EOF?
7. Có giới hạn record length/line count để tránh tiêu thụ bộ nhớ không kiểm soát không?
8. `LineMapper` và tokenizer có cùng dialect với policy không?
9. Reader có lưu state và restart trên cùng input version không?
10. Test đã bao gồm multiline, escaped quote, EOF lỗi, restart và record lớn chưa?

Với file một dòng một record, dùng policy đơn giản. Với file multiline, viết policy theo format được tài liệu hóa và giữ logic mapping ở tầng riêng. Ưu tiên parser chuẩn khi format phức tạp, không đoán ranh giới bằng heuristic. Bảo đảm reader, policy, mapper và checkpoint dùng cùng một cách hiểu về record để restart không bỏ sót hoặc lặp dữ liệu.

## Ghi nhớ

`RecordSeparatorPolicy` cho `FlatFileItemReader` biết khi nào các physical line đã tạo thành một logical record. `isEndOfRecord` quyết định có cần đọc thêm dòng; `preProcess` và `postProcess` cho phép chuẩn hóa nội dung trước/sau khi xác định ranh giới. Policy không parse field và không thay thế `LineMapper` hoặc tokenizer. Dùng policy đơn giản khi một dòng là một record; dùng custom policy cho multiline quote hoặc continuation marker theo format cụ thể. Xử lý rõ quote chưa đóng tới EOF, record quá lớn, escape và line ending. Giữ policy semantics ổn định qua restart, bật reader state phù hợp và kiểm thử end-to-end với `FlatFileItemReader` để bảo đảm record không bị cắt, ghép nhầm hoặc lặp.
