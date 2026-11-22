# `read()` trả về `null` để báo hết input

Trong Spring Batch, `ItemReader` cung cấp từng item cho một Step xử lý theo chunk. Hợp đồng của phương thức `read()` quy định một ý nghĩa đặc biệt: khi reader trả về một item, Step tiếp tục xử lý item đó; khi reader trả về `null`, Spring Batch hiểu rằng nguồn input đã hết và không còn item nào để đọc trong lần thực thi hiện tại.

Giá trị `null` vì vậy là tín hiệu kết thúc dữ liệu (end of input hoặc end of file), không phải một bản ghi rỗng và cũng không phải cách báo lỗi. Nếu reader gặp lỗi khi truy cập nguồn dữ liệu, nó nên ném exception phù hợp để Spring Batch xử lý theo cấu hình retry, skip hoặc fail của Step.

## 1. Hợp đồng của ItemReader.read()

Interface `ItemReader<T>` có phương thức chính:

```java
public interface ItemReader<T> {
    T read() throws Exception;
}
```

Mỗi lần được gọi, `read()` trả về một item tiếp theo thuộc kiểu `T`, hoặc trả về `null` khi không còn item nào. Reader thường duy trì vị trí đọc nội bộ để mỗi lần gọi tiếp theo lấy được item kế tiếp.

Ví dụ nguồn input có ba bản ghi:

```text
Lần gọi read()     Giá trị trả về
---------------------------------
Lần 1              item-A
Lần 2              item-B
Lần 3              item-C
Lần 4              null  -> hết input
```

Khi reader đã hết dữ liệu, các lần gọi tiếp theo trong cùng lần thực thi cũng phải tiếp tục biểu thị rằng không còn item nào. Reader không được quay lại item đầu tiên hoặc tự tạo dữ liệu mới sau khi đã báo EOF, trừ khi đó là một nguồn được thiết kế với cơ chế vòng lặp riêng và có hợp đồng khác.

Điều quan trọng là `read()` trả về **một item mỗi lần gọi**, không trả về cả chunk. Spring Batch chịu trách nhiệm gọi reader nhiều lần để lấy đủ item cho chunk theo commit interval đã cấu hình.

## 2. Spring Batch sử dụng tín hiệu `null` như thế nào?

Trong chunk-oriented processing, Step gọi `ItemReader.read()` lặp lại cho đến khi đạt kích thước chunk hoặc reader trả về `null`.

Ví dụ Step có chunk size là 4 và reader chỉ còn 6 item:

```text
Chunk 1
  read() -> A
  read() -> B
  read() -> C
  read() -> D
  ItemProcessor -> xử lý A, B, C, D
  ItemWriter    -> ghi chunk 1
  Commit

Chunk 2
  read() -> E
  read() -> F
  read() -> null  (EOF)
  ItemProcessor -> xử lý E, F
  ItemWriter    -> ghi chunk 2
  Commit

Không còn item -> Step kết thúc đọc input
```

Chunk cuối cùng có thể nhỏ hơn commit interval. Khi reader trả về `null` sau khi đã cung cấp một số item cho chunk hiện tại, Spring Batch vẫn xử lý và ghi những item còn lại trong chunk đó. Sau khi chunk cuối hoàn tất, Step kết thúc phần đọc dữ liệu.

Nếu reader trả về `null` ngay lần gọi đầu tiên, nguồn input rỗng. Step có thể hoàn tất bình thường với `readCount` bằng 0; đây không tự động được xem là lỗi. Nếu nghiệp vụ yêu cầu phải có ít nhất một bản ghi, ứng dụng cần kiểm tra điều kiện đó bằng validator, listener hoặc logic nghiệp vụ riêng.

## 3. Ví dụ một ItemReader đơn giản

Giả sử ứng dụng có danh sách dữ liệu đã được nạp vào bộ nhớ. Reader có thể dùng iterator để trả từng phần tử:

```java
public class ListItemReader<T> implements ItemReader<T> {

    private final Iterator<T> iterator;

    public ListItemReader(List<T> items) {
        this.iterator = items.iterator();
    }

    @Override
    public T read() {
        if (iterator.hasNext()) {
            return iterator.next();
        }

        return null;
    }
}
```

Khi iterator còn phần tử, reader trả về phần tử kế tiếp. Khi `hasNext()` trả về `false`, reader trả về `null` để báo hết input.

Đây là ví dụ tối giản cho mục đích học tập. Với dữ liệu lớn, không nên nạp toàn bộ nguồn vào `List` chỉ để dùng reader này vì có thể tiêu tốn nhiều heap. Trong production, nên đọc theo luồng, cursor hoặc từng trang phù hợp với nguồn dữ liệu.

Reader không nên trả về `null` như một item hợp lệ. Nếu danh sách có phần tử `null`, đoạn code trên sẽ khiến Spring Batch hiểu nhầm rằng nguồn đã kết thúc tại vị trí đó. Hãy kiểm tra và loại bỏ dữ liệu null không hợp lệ từ trước, hoặc biểu diễn trường dữ liệu tùy chọn bên trong một object không null.

## 4. Ví dụ với FlatFileItemReader

Với file văn bản, `FlatFileItemReader` quản lý việc đọc dòng và ánh xạ mỗi dòng thành một object. Khi không còn dòng nào để đọc, reader trả về `null` theo hợp đồng `ItemReader`.

Ví dụ cấu hình reader trong Spring Batch 5:

```java
@Bean
@StepScope
FlatFileItemReader<CustomerInput> customerReader(
        @Value("#{jobParameters['inputFile']}") String inputFile) {

    return new FlatFileItemReaderBuilder<CustomerInput>()
            .name("customerReader")
            .resource(new FileSystemResource(inputFile))
            .delimited()
            .names("customerId", "fullName", "email")
            .targetType(CustomerInput.class)
            .build();
}
```

Trong ví dụ này:

- Reader mở file được chỉ định bởi JobParameter `inputFile`.
- Mỗi dòng dữ liệu hợp lệ được ánh xạ thành một `CustomerInput`.
- Reader tiếp tục trả về từng object cho đến khi hết file.
- Khi hết file, reader trả về `null`, báo cho Step dừng việc lấy thêm item.

Nếu file không tồn tại, không thể mở hoặc có lỗi đọc/parse, reader có thể ném exception. Đây là tình huống khác với file tồn tại nhưng không có dòng dữ liệu: EOF là kết thúc bình thường, còn lỗi truy cập hoặc parse là lỗi cần được xử lý theo chính sách của Job.

## 5. Phân biệt `null` từ ItemReader và `null` từ ItemProcessor

Đây là hai ý nghĩa khác nhau, dù cùng sử dụng giá trị `null`.

| Thành phần | Khi trả về `null` | Ý nghĩa |
|---|---|---|
| `ItemReader.read()` | Không còn item để đọc | Kết thúc input; Step không yêu cầu thêm item từ reader |
| `ItemProcessor.process(item)` | Item đầu vào bị loại khỏi luồng xử lý | Filter item; reader vẫn có thể tiếp tục đọc item tiếp theo |

Ví dụ, nguồn có 5 khách hàng. Reader trả về cả 5 item, nhưng processor lọc bỏ khách hàng không hoạt động bằng cách trả về `null`:

```java
@Bean
ItemProcessor<CustomerInput, Customer> activeCustomerProcessor() {
    return input -> {
        if (!input.isActive()) {
            return null; // Chỉ loại item hiện tại
        }

        return new Customer(input.customerId(), input.fullName());
    };
}
```

Trong trường hợp này, reader vẫn được gọi cho những bản ghi tiếp theo. `null` từ processor không báo hết file hoặc hết database result set; nó chỉ có nghĩa item hiện tại không được chuyển tới writer. Bộ đếm `filterCount` có thể tăng tương ứng.

Ngược lại, khi `ItemReader.read()` trả về `null`, Spring Batch hiểu rằng không còn item đầu vào để yêu cầu nữa. Vì vậy, không được dùng `null` từ reader để biểu thị một bản ghi cần bỏ qua.

## 6. Phân biệt EOF với lỗi khi đọc

Reader có thể gặp hai nhóm tình huống:

**Kết thúc bình thường:** nguồn đã được đọc hết. Reader trả về `null`; Step kết thúc việc đọc và hoàn tất chunk cuối cùng nếu có item còn lại.

**Lỗi khi đọc:** nguồn không thể truy cập, dữ liệu hỏng, kết nối database mất hoặc định dạng không thể parse. Reader ném exception; Step xử lý lỗi theo cấu hình retry, skip hoặc fail.

Ví dụ:

```java
@Override
public CustomerInput read() throws Exception {
    try {
        String line = bufferedReader.readLine();

        if (line == null) {
            return null; // EOF bình thường
        }

        return parseCustomer(line);
    } catch (IOException ex) {
        throw new ItemStreamException("Cannot read input", ex);
    }
}
```

Đoạn code chỉ minh họa cách phân biệt EOF với lỗi I/O. Reader thực tế cần quản lý việc mở và đóng resource, trạng thái đọc và exception phù hợp với loại nguồn. Nếu `parseCustomer()` phát hiện một dòng không hợp lệ, ứng dụng cần quyết định đó là lỗi khiến Step dừng hay một lỗi có thể skip theo cấu hình. Không nên đổi mọi exception thành `null`, vì như vậy Job sẽ kết thúc như thể input đã hết và có thể bỏ sót dữ liệu chưa đọc.

## 7. Nguồn tạm thời chưa có dữ liệu không đồng nghĩa với EOF

Một điểm quan trọng khi đọc queue, API phân trang hoặc nguồn dữ liệu phát sinh liên tục là phân biệt **hiện tại chưa có dữ liệu** với **nguồn input đã kết thúc**.

Theo hợp đồng của `ItemReader`, trả về `null` có nghĩa reader đã hết input cho lần thực thi hiện tại. Nếu reader đang đọc một queue và tạm thời queue rỗng, trả về `null` sẽ khiến Step hiểu rằng công việc đã hoàn tất. Các message đến sau đó có thể không được đọc trong lần chạy Job này.

Nếu yêu cầu nghiệp vụ là chờ dữ liệu mới, cần thiết kế reader hoặc kiến trúc xử lý phù hợp:

- Poll nguồn trong một khoảng thời gian xác định trước khi kết luận không còn dữ liệu.
- Dùng timeout và chính sách chờ/retry rõ ràng.
- Xác định điều kiện kết thúc theo watermark, batch ID, thời điểm đóng lô hoặc tín hiệu kết thúc từ hệ thống nguồn.
- Với luồng dữ liệu liên tục, cân nhắc consumer hoặc streaming architecture thay vì một Job batch có điểm kết thúc không xác định.

Không nên trả về `null` chỉ vì một lần gọi API không tìm thấy bản ghi ở thời điểm hiện tại nếu Job còn phải chờ dữ liệu trong tương lai.

## 8. `null` và checkpoint khi restart

Với reader hỗ trợ `ItemStream`, Spring Batch có thể lưu trạng thái đọc vào `ExecutionContext` để phục vụ restart. Các callback thường gặp là:

- `open(ExecutionContext)`: mở resource và khôi phục trạng thái đã lưu nếu có.
- `update(ExecutionContext)`: lưu trạng thái hiện tại, chẳng hạn vị trí đọc, vào context.
- `close()`: giải phóng resource khi Step kết thúc.

Một reader tùy chỉnh cần triển khai `ItemStream` nếu muốn lưu và khôi phục vị trí đọc. Ví dụ, reader đọc file có thể lưu số dòng hoặc vị trí byte đã xử lý. Khi restart, nó dùng checkpoint để tiếp tục từ vị trí phù hợp.

```text
Input: A B C D E F G H
Chunk size: 3

Chunk 1: A B C -> COMMIT, lưu checkpoint sau C
Chunk 2: D E F -> lỗi trước COMMIT
                 |
                 v
              Restart
                 |
                 v
        Khôi phục checkpoint sau C
        Đọc lại phần chưa commit theo trạng thái reader
```

Nếu reader không lưu trạng thái, restart có thể bắt đầu đọc lại từ đầu hoặc không thể khôi phục đúng vị trí. Cách xử lý cụ thể phụ thuộc reader và nguồn dữ liệu. Dù reader có checkpoint, các tác dụng phụ bên ngoài transaction vẫn cần cơ chế idempotency vì một item có thể được đọc hoặc xử lý lại.

Việc reader trả về `null` khi thực sự hết dữ liệu vẫn giữ nguyên ý nghĩa trong lần chạy được restart. Checkpoint xác định vị trí tiếp tục; `null` báo rằng từ vị trí đó không còn item nào nữa.

## 9. Những lỗi thường gặp khi triển khai ItemReader

**Trả về `null` cho bản ghi lỗi:** Spring Batch hiểu đó là EOF và kết thúc đọc, khiến phần dữ liệu phía sau không được xử lý. Hãy ném exception hoặc dùng cơ chế skip phù hợp.

**Trả về `null` khi nguồn tạm thời rỗng:** Step kết thúc sớm dù dữ liệu có thể đến sau. Hãy xác định rõ điều kiện chờ và điều kiện kết thúc nguồn.

**Trả về một object rỗng thay cho EOF:** Spring Batch coi object đó là một item hợp lệ và chuyển nó tới processor/writer. Hãy dùng `null` đúng lúc nguồn đã hết.

**Đưa `null` vào collection nguồn:** reader dựa trên iterator có thể trả về `null` ở giữa dữ liệu, khiến framework dừng sớm và bỏ sót các item phía sau. Hãy xác thực dữ liệu trước khi đọc.

**Bắt mọi exception rồi trả `null`:** lỗi I/O hoặc lỗi parse bị che giấu như EOF, làm Job có thể báo hoàn tất dù dữ liệu chưa được xử lý đầy đủ.

**Không giải phóng resource:** file handle, cursor hoặc connection có thể bị giữ sau khi Step kết thúc. Reader quản lý resource cần đóng chúng trong `close()` hoặc cơ chế lifecycle phù hợp.

**Không lưu trạng thái reader cần restart:** sau lỗi, reader có thể đọc lại từ đầu hoặc tiếp tục sai vị trí. Hãy triển khai `ItemStream` và checkpoint nếu yêu cầu khôi phục.

## 10. Tóm tắt luồng quyết định của read()

Khi triển khai một reader, có thể dùng logic khái quát sau:

```text
read() được gọi
      |
      v
Nguồn còn item?
   /       \
 Có         Không
 |            |
 v            v
Đọc item    return null
 |            |
 v            v
Item hợp lệ?  Step biết input đã hết
 /      \
Có       Không
|          |
v          v
return     Ném exception hoặc áp dụng
item       chính sách xử lý lỗi phù hợp
```

Quy tắc này giúp giữ đúng ranh giới trách nhiệm: reader chịu trách nhiệm cung cấp item và báo hết input; processor quyết định biến đổi hoặc lọc item; writer ghi những item còn lại của chunk. Khi reader phân biệt rõ EOF với lỗi và dữ liệu tạm thời chưa sẵn sàng, Spring Batch có thể điều khiển vòng lặp chunk, thống kê và restart một cách đáng tin cậy.

## Kết luận

`ItemReader.read()` trả về một item cho mỗi lần gọi và trả về `null` khi không còn input trong lần thực thi hiện tại. Spring Batch dùng tín hiệu này để kết thúc việc đọc, xử lý chunk cuối cùng nếu còn item và hoàn tất Step. `null` từ reader khác với `null` từ processor: reader báo EOF, còn processor lọc bỏ item hiện tại. Hãy dùng exception cho lỗi đọc, không dùng `null` để che giấu lỗi hoặc biểu thị nguồn tạm thời rỗng, và triển khai checkpoint qua `ItemStream` khi Job cần restart từ vị trí đã lưu.
