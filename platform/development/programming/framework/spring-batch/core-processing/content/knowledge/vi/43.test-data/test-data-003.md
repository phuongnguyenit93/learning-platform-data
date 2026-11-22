# Dữ liệu file test nhỏ và rõ trong Spring Batch Core Processing

Khi kiểm thử một batch job đọc dữ liệu từ file, một file test tốt thường chỉ có **vài dòng**, nhưng mỗi dòng phải có lý do tồn tại. Dữ liệu đủ nhỏ giúp người đọc nhìn ngay ra đầu vào, quy tắc xử lý và kết quả mong đợi; dữ liệu đủ rõ giúp xác định lỗi xuất phát từ cấu trúc file, việc ánh xạ trường, nghiệp vụ, ranh giới chunk hay cách khởi động lại job.

Trong Spring Batch, file test không chỉ phục vụ `FlatFileItemReader`. Nó còn là đầu vào cho việc kiểm thử `ItemProcessor`, `ItemWriter`, cơ chế skip/retry, checkpoint và kết quả của cả `Step`. Bài này trình bày cách thiết kế các **test fixture** dạng file nhỏ, dễ bảo trì và có kỳ vọng kiểm thử tường minh, sử dụng CSV làm ví dụ xuyên suốt.

## 1. File test nhỏ và rõ có nghĩa là gì?

**Test fixture** là dữ liệu được chuẩn bị trước để chạy một ca kiểm thử với kết quả có thể dự đoán. Với batch đọc file, fixture có thể là `.csv`, `.txt` cố định độ rộng, JSON, XML hoặc định dạng riêng của hệ thống.

Một fixture tốt trả lời được bốn câu hỏi:

1. **File đang mô phỏng điều gì?** Ví dụ: ba đơn hàng hợp lệ, một dòng sai số tiền, một file chỉ có header.
2. **Dòng nào kiểm tra quy tắc nào?** Ví dụ: dòng 3 chứa tên có dấu phẩy để kiểm tra quy tắc CSV quoting.
3. **Job phải tạo kết quả gì?** Ví dụ: ghi đúng ba đơn hàng, giữ nguyên tên khách có dấu phẩy và không tạo bản ghi thứ tư.
4. **Khi lỗi xuất hiện, lỗi thuộc tầng nào?** Ví dụ: cột số tiền không thể parse là lỗi đọc/ánh xạ; số tiền âm có thể là lỗi validation nghiệp vụ nếu hệ thống quy định như vậy.

Mục tiêu không phải là tạo file nhỏ bằng mọi giá. Mục tiêu là **ít dòng nhất nhưng vẫn phân biệt được hành vi cần kiểm chứng**. Một bài test chỉ cần ba dòng thì không nên mang theo 10.000 dòng sản xuất đã ẩn danh; ngược lại, kiểm thử phân trang hoặc tải lớn cần bộ dữ liệu phù hợp với bài toán ấy.

| Dữ liệu test khó hiểu | Dữ liệu test rõ ý đồ |
|---|---|
| Một file `sample.csv` chứa 500 dòng không có mô tả. | `orders-valid.csv` có 3 dòng, mỗi dòng đại diện một trường hợp xác định. |
| Giá trị ngẫu nhiên, ngày tháng lấy từ đồng hồ hiện tại. | ID ổn định, số tiền và ngày cố định. |
| Nhiều lỗi lẫn trong một file, không biết lỗi nào được xử lý trước. | Mỗi file lỗi tập trung vào một quy tắc đang được kiểm tra. |
| Chỉ kiểm tra “job thành công”. | Kiểm tra bản ghi đầu ra, số lượng đọc/ghi/skip phù hợp và trạng thái step. |
| Test phụ thuộc đường dẫn cá nhân hoặc file bên ngoài repository. | Fixture trong `src/test/resources`, được nạp bằng classpath resource. |

## 2. Xác định hợp đồng dữ liệu trước khi tạo file

Giả sử một batch job nhận danh sách đơn hàng CSV với bốn trường:

| Cột | Kiểu mong đợi | Quy tắc của ví dụ |
|---|---|---|
| `order_id` | Chuỗi | Không rỗng; là định danh đơn hàng ổn định. |
| `customer` | Chuỗi UTF-8 | Có thể chứa khoảng trắng hoặc dấu phẩy khi được đặt trong dấu nháy kép theo cú pháp CSV. |
| `amount` | Số thập phân | Không âm; dấu chấm là dấu thập phân, không dùng dấu phân cách hàng nghìn. |
| `order_date` | Ngày | Chuẩn ISO `yyyy-MM-dd`; không phụ thuộc locale của máy chạy test. |

Quy ước nhập liệu trong ví dụ:

- File được lưu dưới mã hóa **UTF-8**, có dòng header ở đầu.
- Dấu phẩy `,` phân tách trường; dấu nháy kép `"` bao trường có chứa dấu phẩy.
- Mỗi dòng dữ liệu tương ứng một `OrderRow`; thứ tự dòng giữ nguyên theo file.
- `amount = 0.00` được coi là hợp lệ; `amount < 0` không hợp lệ theo quy tắc nghiệp vụ *của ví dụ*.
- Reader được cấu hình bỏ qua **một dòng header** bằng `linesToSkip(1)`.

Các quy tắc cần được phát biểu ngay trong bài test hoặc tài liệu cạnh fixture. Nếu không có hợp đồng, file chứa `0`, trường trống hoặc dấu phẩy trong tên có thể bị hiểu khác nhau bởi người viết test và người sửa processor.

## 3. Tổ chức fixture thành các file riêng, tên nói rõ mục đích

Cấu trúc minh họa cho dự án dùng Maven hoặc Gradle:

~~~text
src/
  test/
    resources/
      batch/
        orders/
          orders-valid.csv
          orders-invalid-amount.csv
          orders-missing-column.csv
          orders-header-only.csv
          orders-duplicate-id.csv
        expected/
          orders-valid-output.csv
~~~

**Không cần tạo mọi file ở mọi dự án.** Chỉ bổ sung file nào có ca kiểm thử thực sự dùng đến. Việc đặt fixture dưới `src/test/resources` giúp chúng được đóng gói vào test classpath, không phải phụ thuộc vào đường dẫn tuyệt đối trên máy lập trình viên.

### 3.1. Fixture hợp lệ có ba dòng

`src/test/resources/batch/orders/orders-valid.csv`:

~~~csv
order_id,customer,amount,order_date
O-001,Lan,125000.50,2026-02-01
O-002,"Trần, An",0.00,2026-02-02
O-003,Mai,7500.00,2026-02-03
~~~

Ý đồ của từng dòng:

| Dòng vật lý trong file | Nội dung đáng chú ý | Điều cần kiểm tra |
|---|---|---|
| 1 | Header với bốn tên cột | Reader bỏ qua header đúng một lần. |
| 2 | `O-001`, số tiền có hai chữ số thập phân | Parser ánh xạ đúng ID, tên, tiền và ngày. |
| 3 | `O-002`, tên `"Trần, An"`, tiền bằng 0 | Dấu phẩy trong tên không bị tách thành cột mới; Unicode và giá trị biên được giữ đúng. |
| 4 | `O-003` | Reader trả đủ ba item rồi kết thúc bằng `null`. |

Một file ba dòng còn phù hợp để kiểm tra ranh giới chunk khi `chunkSize = 2`: hai item thuộc chunk đầu, item cuối thuộc chunk tiếp theo. Không cần sinh hàng trăm bản ghi chỉ để thấy có hơn một chunk.

### 3.2. Fixture lỗi số tiền

`src/test/resources/batch/orders/orders-invalid-amount.csv`:

~~~csv
order_id,customer,amount,order_date
O-004,Binh,abc,2026-02-04
~~~

Trong hợp đồng trên, `abc` không chuyển được sang `BigDecimal`. Khi reader ánh xạ dòng này, lỗi phát sinh ở tầng đọc/parse (thường được `FlatFileItemReader` bọc trong `FlatFileParseException`), trước khi processor có thể kiểm tra quy tắc số tiền âm.

File này chỉ có **một lỗi có chủ đích**. Nếu đồng thời đổi ngày thành `tomorrow`, xóa ID và làm hỏng dấu nháy, kết quả bài test sẽ phụ thuộc vào lỗi nào được phát hiện trước, khiến nguyên nhân thất bại kém rõ.

### 3.3. Fixture thiếu cột

`src/test/resources/batch/orders/orders-missing-column.csv`:

~~~csv
order_id,customer,amount,order_date
O-005,Hoa,100.00
~~~

Dòng dữ liệu chỉ có ba trường trong khi cấu hình tokenizer yêu cầu bốn trường. Với `DelimitedLineTokenizer` ở chế độ strict mặc định, sự không khớp số trường sẽ dẫn tới lỗi parse. Đây là ca kiểm thử cấu trúc file, khác với lỗi kiểu dữ liệu ở `orders-invalid-amount.csv`.

### 3.4. Fixture chỉ có header

`src/test/resources/batch/orders/orders-header-only.csv`:

~~~csv
order_id,customer,amount,order_date
~~~

Đầu ra mong đợi: reader không trả item nào sau khi bỏ qua header, step không ghi đơn hàng nào. File này hữu ích khi kiểm tra job xử lý đầu vào không có dữ liệu. Nó **khác** file hoàn toàn rỗng (0 byte): việc có bắt buộc phải có header hay không phụ thuộc vào cách ta xác thực định dạng, không tự được đảm bảo chỉ bằng `linesToSkip(1)`.

### 3.5. Fixture trùng khóa nghiệp vụ

`src/test/resources/batch/orders/orders-duplicate-id.csv`:

~~~csv
order_id,customer,amount,order_date
O-006,An,100.00,2026-02-05
O-006,An,100.00,2026-02-05
~~~

Hai dòng giống hệt nhau giúp đặt câu hỏi rõ ràng: writer sẽ ghi trùng, từ chối vì ràng buộc unique, hay thực hiện UPSERT idempotent? Không thể suy ra hành vi chỉ từ file; bài test phải nêu chính sách nghiệp vụ và xác nhận trạng thái đầu ra tương ứng.

## 4. Nối fixture với FlatFileItemReader

Một test tốt phải dùng parser gần với parser production để dữ liệu fixture thật sự kiểm chứng quy tắc đọc file. Ví dụ sau dùng Spring Batch 5.x, Java 17+ và `FlatFileItemReaderBuilder`:

~~~java
import java.math.BigDecimal;
import java.time.LocalDate;

import org.springframework.batch.item.file.FlatFileItemReader;
import org.springframework.batch.item.file.builder.FlatFileItemReaderBuilder;
import org.springframework.core.io.ClassPathResource;

record OrderRow(
    String orderId,
    String customer,
    BigDecimal amount,
    LocalDate orderDate
) {}

class OrderReaderFactory {

    static FlatFileItemReader<OrderRow> fromTestResource(String filename) {
        return new FlatFileItemReaderBuilder<OrderRow>()
            .name("ordersTestReader")
            .resource(new ClassPathResource("batch/orders/" + filename))
            .linesToSkip(1)
            .delimited()
            .delimiter(",")
            .names("order_id", "customer", "amount", "order_date")
            .fieldSetMapper(fields -> new OrderRow(
                fields.readString("order_id"),
                fields.readString("customer"),
                fields.readBigDecimal("amount"),
                LocalDate.parse(fields.readString("order_date"))
            ))
            .build();
    }
}
~~~

Các điểm cần hiểu:

- `ClassPathResource` tải file trong `src/test/resources`, nên test chạy được từ IDE và CI mà không cần đường dẫn tuyệt đối.
- `linesToSkip(1)` bỏ dòng đầu tiên; **không tự xác minh tên cột của header**. Nếu tên và thứ tự cột là hợp đồng bắt buộc, cần thêm logic kiểm tra header (ví dụ `skippedLinesCallback` hoặc cơ chế đọc/kiểm tra riêng).
- `.names(...)` trong cấu hình trên quy định cách ánh xạ các **cột theo vị trí**. Nếu file thật đổi thứ tự cột nhưng vẫn có header, mapper vẫn có thể đọc sai nếu không kiểm tra header.
- `fields.readBigDecimal(...)` và `LocalDate.parse(...)` khiến lỗi kiểu dữ liệu bộc lộ ngay khi đọc item.
- `FlatFileItemReader` là thành phần có trạng thái: khi dùng trực tiếp trong test, cần `open(ExecutionContext)` trước khi đọc và `close()` trong `finally`.

Khi ứng dụng có sẵn bean reader cho production, nên ưu tiên kiểm thử cấu hình thực tế đó, hoặc dùng factory chung có thể thay `Resource`. Ví dụ trên là một cấu hình tự chứa để minh họa cách fixture được đọc; nó không thay thế việc kiểm tra bean reader production trong tích hợp.

## 5. Kiểm thử trực tiếp vài dòng bằng JUnit 5

Không phải mọi bài test dữ liệu file đều cần khởi động toàn bộ job. Kiểm tra tokenizer và mapping có thể thực hiện ở cấp reader, giúp lỗi dễ định vị. Ví dụ dùng JUnit 5 và AssertJ:

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.batch.item.ExecutionContext;
import org.springframework.batch.item.file.FlatFileItemReader;
import org.springframework.batch.item.file.FlatFileParseException;

class OrderFileReaderTest {

    @Test
    void readsThreeValidRowsExactly() throws Exception {
        FlatFileItemReader<OrderRow> reader =
            OrderReaderFactory.fromTestResource("orders-valid.csv");

        List<OrderRow> actual = new ArrayList<>();
        reader.open(new ExecutionContext());
        try {
            OrderRow row;
            while ((row = reader.read()) != null) {
                actual.add(row);
            }
        } finally {
            reader.close();
        }

        assertThat(actual).containsExactly(
            new OrderRow("O-001", "Lan",
                new BigDecimal("125000.50"), LocalDate.of(2026, 2, 1)),
            new OrderRow("O-002", "Trần, An",
                new BigDecimal("0.00"), LocalDate.of(2026, 2, 2)),
            new OrderRow("O-003", "Mai",
                new BigDecimal("7500.00"), LocalDate.of(2026, 2, 3))
        );
    }

    @Test
    void reportsInvalidAmountAsParseFailure() throws Exception {
        FlatFileItemReader<OrderRow> reader =
            OrderReaderFactory.fromTestResource("orders-invalid-amount.csv");

        reader.open(new ExecutionContext());
        try {
            assertThatThrownBy(reader::read)
                .isInstanceOf(FlatFileParseException.class);
        } finally {
            reader.close();
        }
    }

    @Test
    void headerOnlyFileHasNoItems() throws Exception {
        FlatFileItemReader<OrderRow> reader =
            OrderReaderFactory.fromTestResource("orders-header-only.csv");

        reader.open(new ExecutionContext());
        try {
            assertThat(reader.read()).isNull();
        } finally {
            reader.close();
        }
    }
}
~~~

Ưu điểm của cách viết này là mỗi khẳng định có thể đối chiếu trực tiếp với ba hoặc bốn dòng trong file. Ví dụ, nếu phép tách CSV làm mất tên `Trần, An`, test sẽ hiển thị giá trị đọc thực tế và giá trị mong đợi ngay tại dòng thứ hai.

Lưu ý: trong Spring Batch, ngoại lệ phát sinh từ `LineMapper` thường được reader đóng gói vào `FlatFileParseException` với thông tin dòng đọc. Nếu thử trực tiếp tokenizer mà không qua `FlatFileItemReader`, có thể nhận loại exception thấp hơn khác; test nên khẳng định lỗi ở **tầng đang được kiểm tra**.

## 6. Viết kỳ vọng đầu ra rõ như đầu vào

File test tự nó chưa tạo thành một bài test có giá trị nếu không biết kết quả nào là đúng. Với `orders-valid.csv`, có thể định nghĩa đầu ra sau processor như sau:

Giả sử processor chuẩn hóa tên khách bằng `trim()`, giữ nguyên số tiền và ngày, đồng thời writer ghi từng đơn hàng vào bảng `processed_order` theo `order_id`.

| `order_id` | `customer` mong đợi | `amount` mong đợi | `order_date` mong đợi |
|---|---|---|---|
| `O-001` | `Lan` | `125000.50` | `2026-02-01` |
| `O-002` | `Trần, An` | `0.00` | `2026-02-02` |
| `O-003` | `Mai` | `7500.00` | `2026-02-03` |

Nếu đầu ra cũng là CSV, có thể lưu fixture mong đợi riêng:

`src/test/resources/batch/expected/orders-valid-output.csv`:

~~~csv
order_id,customer,amount,order_date
O-001,Lan,125000.50,2026-02-01
O-002,"Trần, An",0.00,2026-02-02
O-003,Mai,7500.00,2026-02-03
~~~

Cần phân biệt **so sánh byte** và **so sánh nội dung**:

- Khi định dạng byte là một phần hợp đồng (ví dụ chuẩn UTF-8, dấu kết thúc dòng, thứ tự cột, quoting chính xác), so sánh toàn bộ file có thể hữu ích.
- Khi mục tiêu là dữ liệu nghiệp vụ, nên parse file đầu ra trở lại thành các record rồi so sánh giá trị. Khi ấy CRLF/LF hoặc cách biểu diễn tương đương của số thập phân không gây thất bại ngoài mục tiêu kiểm tra.
- Khi output không có bảo đảm thứ tự (ví dụ ghi song song, truy vấn DB không có `ORDER BY`), nên so sánh theo khóa hoặc tập bản ghi, không mặc định thứ tự là cố định.

Không được “chấp nhận mọi kết quả” bằng cách chỉ khẳng định file tồn tại hay có ít nhất một dòng. Test cần chỉ rõ **số bản ghi và giá trị có thể kiểm chứng**.

## 7. File test và ranh giới chunk

Spring Batch thường xử lý đọc → xử lý → ghi theo từng chunk. Dữ liệu file nhỏ vẫn có thể minh họa các trường hợp quan trọng:

| Mục tiêu | Số item nên có | Ví dụ cấu hình |
|---|---:|---|
| File không có dữ liệu | 0 | Header-only; khẳng định không item nào được ghi. |
| Ít hơn một chunk | 1 | `chunkSize = 2`, một đơn hàng hợp lệ. |
| Đúng một chunk | 2 | `chunkSize = 2`, hai đơn hàng. |
| Vượt ranh giới chunk | 3 | `chunkSize = 2`, ba đơn hàng. |
| Lỗi ngay đầu input | 1 lỗi | Xác nhận lỗi parse/validation và trạng thái step. |
| Lỗi sau chunk đầu đã commit | 2 hợp lệ + 1 lỗi | `chunkSize = 2`; kiểm tra tác động của chunk đã commit và xử lý lỗi chunk sau. |

Với fixture ba dòng ở mục 3 và `chunkSize = 2`, một lần chạy thành công có thể xử lý hai item ở chunk đầu và một item ở chunk cuối. Điều này đủ để nghiên cứu **ranh giới logic của dữ liệu**, nhưng không nên suy diễn chính xác số transaction/commit của mọi framework setup chỉ từ số dòng; việc đo lường cần dựa vào cấu hình step và `StepExecution` thực tế.

Nếu muốn kiểm tra rollback hoặc restart:

1. Dùng fixture có ID cố định `O-001`, `O-002`, `O-003` để biết chính xác item nào đã ghi.
2. Tạo lỗi có chủ đích ở item nằm sau ranh giới chunk, bằng fixture hoặc dependency kiểm thử có hành vi xác định.
3. Sau khi step thất bại, truy vấn DB để kiểm tra dữ liệu của chunk đã commit và chunk đã rollback.
4. Restart cùng `JobInstance` theo đúng cơ chế Spring Batch và kiểm tra tổng thể đầu ra **không trùng và không mất**.

Tránh dùng “đọc 100.000 dòng để xác suất cao gặp lỗi”; kiểm thử restart cần **vị trí lỗi xác định** và cách tái hiện nhất quán.

## 8. Tách lỗi định dạng, lỗi parse và lỗi nghiệp vụ

Các loại lỗi khác nhau nên có fixture riêng vì chúng đi qua các nhánh khác nhau của Spring Batch:

| File tình huống | Ví dụ giá trị | Tầng thường phát hiện | Kỳ vọng cần định nghĩa |
|---|---|---|---|
| Thiếu trường | `O-005,Hoa,100.00` | Tokenizer/reader | Parse thất bại hoặc skip đọc nếu được cấu hình. |
| Số tiền không hợp lệ | `amount=abc` | FieldSetMapper/reader | Exception chuyển đổi dữ liệu. |
| Ngày không hợp lệ | `2026-02-30` | Mapper/reader | Exception parse ngày. |
| Giá trị tiền âm | `amount=-1.00` | Processor/validator nếu định nghĩa quy tắc ở đó | Reject, filter hoặc skip theo hợp đồng nghiệp vụ. |
| Trùng ID | Hai dòng có cùng `order_id` | Writer/database hoặc logic kiểm tra trùng | Một bản ghi, lỗi unique hay chính sách xử lý trùng cụ thể. |
| Trường có dấu phẩy được quote | `"Trần, An"` | Tokenizer | Một giá trị customer duy nhất. |
| Dòng trắng | Dòng rỗng giữa các item | Reader/record separator theo cấu hình | Phải xác định có bỏ qua, báo lỗi hay coi là item trống. |

Ví dụ, kiểm thử `skip(FlatFileParseException.class)` không đồng nghĩa với kiểm thử `skip(ValidationException.class)`. Nếu parser thất bại trước, processor chưa được gọi. Tách fixture khiến test phản ánh chính xác nhánh xử lý đang được kiểm chứng.

Với một file chứa cả dòng hợp lệ và một dòng lỗi, nên mô tả rõ kỳ vọng **sau khi skip**: số dòng đã đọc, số skip thuộc read/process/write, và danh sách ID thực tế đã được ghi. Các bộ đếm phụ thuộc vào cách Spring Batch định nghĩa từng giai đoạn; đừng gộp mọi loại lỗi thành một số “records failed” mơ hồ.

## 9. Những chi tiết nhỏ dễ làm file test thiếu ổn định

### 9.1. Mã hóa và ký tự Unicode

Tạo fixture ở UTF-8; nếu reader production cấu hình encoding cụ thể, test phải dùng đúng encoding đó. Những giá trị như `Nguyễn`, `Trần, An` giúp phát hiện trường hợp mất dấu hoặc xử lý separator sai. Việc có **UTF-8 BOM** hay không cũng cần được quyết định rõ, bởi BOM có thể làm thay đổi token đầu tiên nếu không được xử lý đúng.

Không cần đặt tất cả biến thể Unicode trong một file. Có thể giữ một fixture chuẩn có dấu tiếng Việt và một fixture riêng cho BOM nếu đó là yêu cầu giao tiếp thực tế.

### 9.2. Ký tự phân tách, quote và xuống dòng

Một tên `"Trần, An"` kiểm tra quy tắc dấu phẩy được quote; giá trị chứa dấu nháy kép có thể cần viết theo quy tắc escape CSV, chẳng hạn `"An ""VIP"""` nếu định dạng dùng cách nhân đôi dấu nháy. Không nên xây test bằng cách `split(",")` vì thao tác này sẽ tách sai trường có dấu phẩy được quote.

CRLF và LF thường có thể được reader xử lý như những kiểu kết thúc dòng phổ biến, nhưng bài test kiểm tra đúng **bytes xuất file** phải xác định kiểu cần xuất. Nếu kiểm thử nghiệp vụ không quan tâm tới line ending, tránh so sánh byte nguyên văn.

### 9.3. Khoảng trắng và trường trống

Phân biệt rõ ba trường hợp:

~~~csv
order_id,customer,amount,order_date
O-011," An ",1.00,2026-02-11
O-012,,1.00,2026-02-12
O-013,"",1.00,2026-02-13
~~~

Ví dụ thứ nhất chứa khoảng trắng trong chuỗi, hai ví dụ còn lại có thể đều được ánh xạ thành chuỗi rỗng tùy parser. Nếu nghiệp vụ cần phân biệt `null` với chuỗi rỗng, cần quy định và kiểm thử cách biểu diễn trong file một cách riêng biệt; CSV thuần không tự có khái niệm `null` chuẩn áp dụng cho mọi hệ thống.

### 9.4. Giá trị cố định và độc lập môi trường

Không nên tạo file test dựa trên:

- Thời gian hiện tại (`now()`), timezone hoặc locale mặc định.
- UUID và giá trị ngẫu nhiên không có seed cố định.
- Đường dẫn kiểu `C:\Users\...\orders.csv` hoặc một file chia sẻ có thể bị thay đổi.
- Dữ liệu thật chứa thông tin cá nhân/kinh doanh nhạy cảm.
- Kết quả chạy test trước hoặc database chung chưa được dọn dẹp.

Dùng ID giả lập, ngày cố định, số tiền tường minh. Nếu tính chất kiểm thử đòi hỏi bộ dữ liệu sinh ngẫu nhiên, hãy cố định seed, kiểm soát phạm vi và ghi rõ khi cần tái hiện trường hợp thất bại.

### 9.5. File đầu vào là bất biến

Fixture trong `src/test/resources` nên được xem như **đầu vào chỉ đọc**. Writer của test phải ghi ra thư mục tạm (ví dụ JUnit `@TempDir`) hoặc cơ sở dữ liệu test được cô lập; không ghi đè fixture trong repository. Điều này tránh việc lần chạy thứ hai thấy dữ liệu đã bị sửa bởi lần chạy thứ nhất.

Nếu nhiều test dùng cùng một file fixture, chúng vẫn có thể chạy độc lập khi mỗi test tạo reader instance mới, có `ExecutionContext` riêng và đầu ra riêng. Không nên dùng chung một `FlatFileItemReader` đang mở cho các test chạy song song.

## 10. Cách thiết kế bộ fixture theo từng tầng kiểm thử

Không phải tầng nào cũng cần cùng số lượng dữ liệu:

| Tầng test | Dữ liệu thích hợp | Điều quan trọng |
|---|---|---|
| Unit test cho tokenizer/mapper | 1–3 dòng | Cột, quote, kiểu dữ liệu, line number khi lỗi. |
| Unit test cho processor | Đối tượng Java tạo trực tiếp hoặc 1–2 dòng đọc từ fixture | Quy tắc nghiệp vụ: chuẩn hóa, lọc, validation. |
| Test tích hợp reader + processor | 2–4 dòng | Kết quả biến đổi theo từng dòng, không sót item. |
| Test tích hợp step | 3–5 dòng với chunk size nhỏ | Đầu ra cuối, rollback/skip, trạng thái step. |
| Test restart/idempotency | Ít dòng, vị trí gây lỗi cố định | Đã commit gì trước crash và xử lý lại thế nào. |
| Test hiệu năng/tải | Dữ liệu lớn hoặc generator riêng | Throughput, bộ nhớ, I/O; không ép fixture nhỏ làm nhiệm vụ đo tải. |

Các con số là **quy tắc kinh nghiệm**, không phải giới hạn do Spring Batch đặt ra. Với tình huống có yêu cầu nhiều trường hợp độc lập, có thể dùng nhiều fixture nhỏ cùng test parameterized thay vì một file khổng lồ.

### Một ma trận ca kiểm thử dễ bảo trì

| Tên test gợi ý | Fixture | Kỳ vọng chủ đạo |
|---|---|---|
| `readsThreeValidRowsExactly` | `orders-valid.csv` | Ba đối tượng được ánh xạ đúng, đúng thứ tự. |
| `readsQuotedCustomerName` | `orders-valid.csv` | `Trần, An` là một trường. |
| `rejectsInvalidAmount` | `orders-invalid-amount.csv` | Lỗi parse khi đọc dòng có `abc`. |
| `rejectsMissingColumn` | `orders-missing-column.csv` | Phát hiện số trường không hợp lệ. |
| `handlesHeaderOnlyInput` | `orders-header-only.csv` | Không item đầu ra. |
| `handlesDuplicateOrderIdAccordingToPolicy` | `orders-duplicate-id.csv` | Hành vi trùng khóa đúng thiết kế writer. |
| `processesPartialLastChunk` | `orders-valid.csv`, chunk size 2 | Cả ba item được xử lý, kể cả item trong chunk cuối chỉ có một dòng. |

Tên test nên nói về **hành vi**. Tên file nên nói về **tình huống dữ liệu**. Hai yếu tố kết hợp giúp người sửa code hiểu tác động của thay đổi mà không phải đọc hàng trăm dòng dữ liệu.

## 11. Khi nào nên tạo dữ liệu bằng code thay vì lưu file?

Fixture nhỏ trong repository đặc biệt tốt khi đang kiểm tra cú pháp **file thật**: delimiters, header, encoding, escaping và line endings. Tuy nhiên, không phải mọi dữ liệu test đều phải là file:

- Kiểm thử thuật toán trong `ItemProcessor`: có thể tạo `OrderRow` trực tiếp trong code, nhanh và dễ đọc hơn.
- Kiểm thử nhiều giá trị biên của một trường: có thể dùng JUnit parameterized test trên một tập vài đối số.
- Kiểm thử một triệu dòng hoặc throughput: sinh file test trong thư mục tạm với seed cố định, không cần commit file lớn.
- Kiểm thử writer/database: có thể seed database test bằng dữ liệu nhỏ và kiểm tra trực tiếp trạng thái bảng.

Quy tắc lựa chọn là **đặt dữ liệu ở dạng phản ánh đúng phần hệ thống đang kiểm tra**. Nếu lỗi cần bắt là quoting CSV, dùng file CSV thực. Nếu lỗi cần bắt là tính tiền, một đối tượng Java biểu diễn số tiền và loại đơn hàng thường rõ hơn việc đi qua toàn bộ pipeline đọc file.

## 12. Một ví dụ diễn giải ca kiểm thử từ đầu đến cuối

Giả sử bước `importOrdersStep` làm ba việc: đọc file CSV, kiểm tra `amount >= 0`, ghi bản ghi hợp lệ vào database. Để kiểm tra đường đi thành công với `chunkSize = 2`:

**Đầu vào:** `orders-valid.csv` gồm ba dòng dữ liệu với ID `O-001`, `O-002`, `O-003`.

**Kỳ vọng trước khi chạy:** database test chưa có các ID trên; reader dùng đúng resource; mã hóa UTF-8 và quy tắc tokenizer đã được xác định.

**Kỳ vọng sau khi chạy:**

1. Step kết thúc với `BatchStatus.COMPLETED`.
2. Bảng đích có đúng ba đơn hàng theo ID và số tiền mong đợi.
3. Tên `Trần, An` được bảo toàn, `amount = 0.00` không bị loại vì quy tắc cho phép bằng 0.
4. Không xuất hiện dòng header như một đơn hàng.
5. Không có bản ghi thứ tư hoặc bản ghi trùng ID.

Với ca lỗi `orders-invalid-amount.csv`, có thể kiểm tra step thất bại hoặc skip theo chính sách cấu hình. Không nên dùng một test rồi khẳng định “hoặc FAILED hoặc COMPLETED đều đúng”; mỗi bài test cần một kết quả cụ thể, gắn với cấu hình retry/skip thực sự của step.

Khi mở rộng sang restart, hãy tạo một ca riêng, dùng dữ liệu đủ ít để người đọc có thể liệt kê chính xác các bản ghi đã commit trước lỗi và các bản ghi cần có sau restart. Cách này phân biệt lỗi dữ liệu, lỗi điều phối chunk và lỗi idempotency.

## 13. Nguyên tắc thực hành khi chuẩn bị file test

Trước khi thêm fixture mới, hãy trả lời:

1. **Một file có một mục đích dễ gọi tên không?** Nếu có nhiều lỗi không liên quan, hãy tách.
2. **Người đọc có dự đoán được kết quả chỉ bằng vài giây nhìn vào file không?** Nếu không, giảm số dòng hoặc ghi rõ kỳ vọng.
3. **Dữ liệu có phân biệt đúng ranh giới cần kiểm tra không?** Ví dụ muốn test chunk size 2 thì ba dòng có thể đủ.
4. **Từng trường có kiểu và quy tắc biểu diễn cố định không?** Ngày ISO, dấu thập phân, encoding, header, quote và trường trống.
5. **File có chạy ổn định trên CI và máy khác không?** Dùng classpath resource, dữ liệu giả lập cố định, tránh đường dẫn và trạng thái chung.
6. **Kỳ vọng có kiểm chứng đúng nghiệp vụ không?** So sánh ID, số lượng và nội dung đầu ra; kiểm tra skip/restart khi liên quan.

**Ghi nhớ:** Một file test hiệu quả cho Spring Batch không cần nhiều bản ghi. Một CSV ba dòng với mục đích rõ ràng, hợp đồng cột xác định và kỳ vọng đầu ra cụ thể thường giúp phát hiện lỗi chính xác hơn một file lớn khó kiểm soát. Khi kiểm thử batch có chunk, rollback, skip hoặc restart, hãy thiết kế thêm các fixture nhỏ đặt lỗi ở vị trí biết trước; chính khả năng giải thích từng dòng và tái hiện kết quả làm nên chất lượng của test data.
