# Phân biệt retry với skip

Trong Spring Batch, **retry** và **skip** đều là cơ chế xử lý lỗi trong chunk-oriented step, nhưng chúng giải quyết hai vấn đề khác nhau. Retry yêu cầu thử lại một thao tác vì lỗi có thể chỉ là tạm thời. Skip chấp nhận bỏ qua item không thể xử lý và tiếp tục với các item khác theo chính sách đã định.

Phân biệt đúng hai cơ chế giúp tránh hai kiểu sai lầm phổ biến: bỏ qua lỗi hạ tầng rồi tạo ra một batch thiếu dữ liệu, hoặc retry mãi một lỗi dữ liệu cố định khiến job không thể tiến lên. Trong thực tế, một step có thể dùng cả retry và skip: thử lại lỗi tạm thời trước, sau đó chỉ skip nếu nghiệp vụ cho phép bỏ qua item khi đã hết retry.

## 1. Retry là gì?

Retry là việc thử thực hiện lại thao tác sau khi gặp exception được xác định là có khả năng phục hồi. Ví dụ, writer cập nhật database gặp deadlock. Database rollback một transaction để giải quyết xung đột; nếu ứng dụng thử lại sau một khoảng chờ, thao tác có thể thành công.

Một số lỗi có thể cân nhắc retry:

- Deadlock hoặc lock acquisition failure có tính tạm thời.
- Kết nối database bị gián đoạn trong thời gian ngắn.
- Timeout khi gọi dịch vụ ngoài, nếu có thể xác định hoặc chống được request trùng.
- Một số lỗi tạm thời từ object storage, message broker hoặc hệ thống mạng.

Retry không loại bỏ item khỏi luồng xử lý. Mục tiêu của nó là hoàn thành thao tác cho chính item hoặc chunk đang gặp lỗi.

```text
Item được xử lý
      |
      v
Thao tác phát sinh exception tạm thời
      |
      v
Retry theo policy
      |
      +---- thành công ----> tiếp tục / commit
      |
      +---- vẫn lỗi ------> thử lại trong giới hạn
```

Nếu thao tác thành công ở lần thử sau, item tiếp tục được xử lý như bình thường. Việc đã retry không có nghĩa item bị skip.

## 2. Skip là gì?

Skip là việc cho phép bỏ qua item hoặc lỗi đọc/ghi cụ thể khi exception thuộc loại được chính sách cho phép. Step tiếp tục xử lý các item khác thay vì dừng ngay tại item đó.

Ví dụ, một file nhập đơn hàng có một dòng chứa ngày sai định dạng. Nếu nghiệp vụ cho phép loại riêng dòng lỗi và ghi nhận để sửa sau, ứng dụng có thể cấu hình skip cho exception phân tích dòng đó.

```text
Đọc item A ----> xử lý và ghi thành công
Đọc item B ----> lỗi dữ liệu, được skip
Đọc item C ----> xử lý và ghi thành công
Đọc item D ----> xử lý và ghi thành công
```

Skip không cố làm cho item lỗi thành công. Nó chấp nhận rằng item đó không đi tiếp qua pipeline trong lần chạy này. Vì vậy, skip phải gắn với một quyết định nghiệp vụ: dữ liệu đó có thể bị loại riêng hay không, ai sẽ xử lý lại, và cần lưu dấu vết gì?

## 3. So sánh nhanh retry và skip

| Tiêu chí | Retry | Skip |
|---|---|---|
| Mục tiêu | Thử lại thao tác để xử lý thành công cùng item/chunk. | Bỏ qua item/lỗi được cho phép để tiếp tục item khác. |
| Khi phù hợp | Lỗi tạm thời, có khả năng biến mất sau một khoảng chờ. | Lỗi riêng của item mà nghiệp vụ cho phép loại bỏ hoặc xử lý sau. |
| Kết quả nếu lần sau thành công | Item được xử lý bình thường. | Không áp dụng; skip không phải cơ chế thử lại. |
| Kết quả nếu vẫn thất bại | Tiếp tục retry trong giới hạn; sau đó áp dụng nhánh xử lý tiếp theo. | Item được tính là skip nếu exception được cho phép và chưa vượt giới hạn. |
| Giới hạn | Retry limit / retry policy. | Skip limit / skip policy. |
| Theo dõi | Cần log/metric retry attempt hoặc listener phù hợp. | Có counter skip trong `StepExecution` và callback `SkipListener`. |
| Nguy cơ khi cấu hình sai | Retry lỗi cố định, gây chậm hoặc tạo request lặp. | Bỏ qua lỗi hệ thống, làm thiếu dữ liệu mà job vẫn hoàn tất. |

Có thể ghi nhớ: **retry hỏi “có nên thử lại không?”, skip hỏi “nếu không xử lý được thì có được bỏ qua không?”**

## 4. Retry policy và skip policy là hai quyết định độc lập

Spring Batch cho phép cấu hình retry và skip cho cùng một step. Hai policy phân loại exception theo mục đích riêng. Một exception có thể retryable, skippable, cả hai hoặc không thuộc nhóm nào.

| Retry policy | Skip policy | Hành vi thường gặp |
|---|---|---|
| Retry | Không skip | Thử lại trong giới hạn; nếu vẫn lỗi, step thất bại. |
| Không retry | Skip | Bỏ qua item nếu skip limit còn cho phép. |
| Retry | Skip | Thử lại trước; nếu lỗi vẫn tồn tại sau retry, item có thể được skip nếu policy cho phép. |
| Không retry | Không skip | Exception làm step thất bại ngay theo cơ chế lỗi của step. |

Ví dụ:

- `DeadlockLoserDataAccessException`: có thể retry vì deadlock thường tạm thời. Nếu retry hết mà lỗi vẫn xảy ra, ứng dụng có thể để step thất bại; chỉ skip nếu nghiệp vụ thực sự cho phép bỏ qua thao tác đó.
- `InvalidOrderException`: thường không có ích khi retry vì dữ liệu đầu vào không tự thay đổi. Có thể skip nếu đơn hàng lỗi độc lập và được ghi nhận để xử lý sau.
- `FileNotFoundException`: thường không nên retry hoặc skip trong một job bắt buộc phải có file; nên làm job thất bại để sửa đầu vào.

Không nên dùng một danh sách exception chung cho cả retry và skip chỉ vì cả hai đều liên quan đến lỗi. Cần quyết định theo nguyên nhân và tác động nghiệp vụ.

## 5. Retry limit và skip limit

Retry limit giới hạn số lần thử lại cho exception thuộc retry policy. Skip limit giới hạn tổng số lỗi được bỏ qua trong step.

Ví dụ cấu hình:

```java
return new StepBuilder("importOrdersStep", jobRepository)
        .<OrderInput, Order>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .retry(DeadlockLoserDataAccessException.class)
        .retryLimit(3)
        .skip(InvalidOrderException.class)
        .skip(FlatFileParseException.class)
        .skipLimit(50)
        .build();
```

Trong ví dụ:

- Deadlock được thử lại theo retry policy.
- Đơn hàng không hợp lệ hoặc dòng file parse lỗi có thể bị skip.
- Tổng skip của các giai đoạn read, process và write không được vượt quá 50.
- Nếu deadlock vẫn xảy ra sau retry mà không thuộc skip policy, step thất bại.

`retryLimit` và `skipLimit` không thay thế nhau. Một retry attempt không tự động được tính là skip. Một item bị skip không có nghĩa framework đã retry nó trước đó.

Khi cần biết chính xác tổng số lần gọi thao tác, hãy xác nhận semantics của `retryLimit` ở phiên bản Spring Batch/Spring Retry đang dùng và bổ sung log/metric attempt. Đừng suy ra số lần gọi chỉ từ `skipCount`.

## 6. Điều gì xảy ra khi retry hết?

Khi exception được retry policy chấp nhận nhưng thao tác vẫn thất bại sau giới hạn, retry không tiếp tục. Spring Batch xem xét các quy tắc fault tolerance còn lại.

Thông thường có hai khả năng:

1. Exception cũng được skip policy cho phép và skip limit chưa bị vượt: item có thể được bỏ qua, listener được gọi để ghi nhận và step tiếp tục.
2. Exception không được phép skip hoặc đã vượt skip limit: exception thoát ra, transaction hiện tại được rollback theo transaction manager và step thất bại.

Sơ đồ:

```text
Exception xảy ra
       |
       v
Có thuộc retry policy?
   |             |
  Không          Có
   |             |
   |       Còn retry attempt?
   |          |       |
   |         Có      Không
   |          |       |
   |        Retry    +----------------+
   |                                 |
   +---------------+-----------------+
                   v
          Có được skip không?
             |          |
            Có         Không
             |          |
       Còn skip limit?  |
         |       |      |
        Có      Không   |
         |       |      |
        Skip   Step FAILED
```

Nếu exception không thuộc retry policy nhưng thuộc skip policy, framework có thể skip mà không cần retry trước. Retry exhaustion không phải điều kiện bắt buộc để skip.

## 7. Ví dụ chọn retry cho lỗi tạm thời

Giả sử writer ghi đơn hàng vào database và đôi khi gặp deadlock do nhiều transaction cập nhật các hàng liên quan. Lỗi này có thể biến mất sau khi transaction khác hoàn tất.

```java
return new StepBuilder("writeOrdersStep", jobRepository)
        .<OrderInput, Order>chunk(100, transactionManager)
        .reader(orderReader)
        .processor(orderProcessor)
        .writer(orderWriter)
        .faultTolerant()
        .retry(DeadlockLoserDataAccessException.class)
        .retryLimit(3)
        .build();
```

Ở đây không cấu hình skip cho deadlock. Nếu retry thành công, chunk có thể commit. Nếu retry hết mà deadlock vẫn xảy ra, step thất bại để người vận hành điều tra lock contention, thứ tự cập nhật hoặc index.

Đây thường là lựa chọn an toàn khi lỗi cho thấy database đang gặp vấn đề và việc bỏ qua một số đơn hàng sẽ làm sai kết quả batch.

## 8. Ví dụ chọn skip cho lỗi dữ liệu

Giả sử một file có nhiều đơn hàng độc lập. Một số dòng có mã khách hàng không tồn tại. Nghiệp vụ cho phép bỏ qua các dòng đó và lưu thông tin để đối soát sau.

```java
return new StepBuilder("validateOrdersStep", jobRepository)
        .<OrderInput, Order>chunk(100, transactionManager)
        .reader(orderReader)
        .processor(orderProcessor)
        .writer(orderWriter)
        .faultTolerant()
        .skip(UnknownCustomerException.class)
        .skipLimit(100)
        .listener(orderSkipListener)
        .build();
```

Không cấu hình retry cho `UnknownCustomerException` vì việc lặp lại cùng một kiểm tra với cùng dữ liệu thường không thay đổi kết quả. Listener ghi nhận order ID và nguyên nhân để đội nghiệp vụ bổ sung dữ liệu khách hàng hoặc xử lý lại sau.

Nếu lỗi khách hàng không tồn tại thực chất do dịch vụ tra cứu đang tạm thời không khả dụng, exception cần phản ánh lỗi hạ tầng riêng và có thể retry. Không nên dùng cùng một exception cho “không tìm thấy khách hàng” và “dịch vụ không phản hồi”.

## 9. Dùng cả retry và skip cho cùng một exception

Có trường hợp nghiệp vụ chấp nhận bỏ qua item nếu lỗi tạm thời vẫn tiếp diễn sau vài lần thử. Ví dụ, một item độc lập được gửi đến hệ thống đối tác; nếu đối tác timeout nhiều lần, ứng dụng có thể ghi nhận item vào hàng đợi xử lý sau thay vì dừng cả batch.

```java
return new StepBuilder("publishOrdersStep", jobRepository)
        .<Order, PartnerRequest>chunk(50, transactionManager)
        .reader(orderReader)
        .processor(requestProcessor)
        .writer(partnerWriter)
        .faultTolerant()
        .retry(ResourceAccessException.class)
        .retryLimit(3)
        .skip(ResourceAccessException.class)
        .skipLimit(25)
        .listener(partnerSkipListener)
        .build();
```

Ở cấu hình này, exception timeout được retry trước. Nếu vẫn thất bại, skip policy có thể cho phép bỏ qua item trong giới hạn. Cách làm chỉ phù hợp khi:

- Mỗi request độc lập, không phụ thuộc vào thứ tự hoặc kết quả của request khác.
- Có cơ chế lưu request chưa gửi được để xử lý lại.
- Có idempotency key ổn định vì timeout không cho biết chắc đối tác đã xử lý request hay chưa.
- Việc tiếp tục batch khi một số request chưa publish được là yêu cầu nghiệp vụ đã chấp nhận.

Nếu API đối tác là một phần bắt buộc của giao dịch, hoặc database/đối tác đang gặp sự cố diện rộng, nên để step thất bại thay vì skip hàng loạt.

## 10. Phân biệt skip với filter

Skip thường bị nhầm với filter vì cả hai đều khiến item không đến writer. Tuy nhiên, chúng có ý nghĩa khác nhau.

| Cơ chế | Cách thực hiện | Counter liên quan |
|---|---|---|
| Filter | `ItemProcessor` trả về `null` | `filterCount` |
| Skip | Exception được skip policy cho phép | `readSkipCount`, `processSkipCount`, `writeSkipCount`, `skipCount` |

Ví dụ filter:

```java
@Bean
ItemProcessor<OrderInput, Order> processor() {
    return input -> {
        if (input.status() == OrderStatus.CANCELLED) {
            return null;
        }
        return mapToOrder(input);
    };
}
```

Đơn hàng đã hủy bị loại theo quy tắc bình thường, không phải exception. Vì vậy nó được tính là filter.

Ví dụ skip:

```java
@Bean
ItemProcessor<OrderInput, Order> processor() {
    return input -> {
        if (input.customerId() == null) {
            throw new InvalidOrderException("customerId is required");
        }
        return mapToOrder(input);
    };
}
```

Nếu `InvalidOrderException` được cấu hình skippable, item được ghi nhận skip. Đây là trường hợp dữ liệu không hợp lệ phát sinh exception.

Không nên trả `null` để che giấu lỗi dữ liệu hoặc exception. Filter nên biểu diễn quyết định nghiệp vụ có chủ đích; skip nên biểu diễn lỗi đã được chính sách cho phép bỏ qua.

## 11. Retry và skip ở ba giai đoạn read, process, write

Exception có thể xảy ra ở bất kỳ giai đoạn nào của chunk processing. Cách retry/skip cần xét giai đoạn cụ thể.

| Giai đoạn | Ví dụ lỗi | Retry có thể phù hợp khi | Skip có thể phù hợp khi |
|---|---|---|---|
| Read | Lỗi kết nối database khi đọc | Lỗi kết nối tạm thời và reader có thể đọc lại an toàn. | Một record/file line lỗi định dạng, có thể loại riêng. |
| Process | Lỗi khi gọi service làm giàu dữ liệu | Service timeout tạm thời và thao tác đọc có thể lặp. | Item vi phạm quy tắc dữ liệu cố định, không cần thử lại. |
| Write | Deadlock hoặc timeout database | Transaction có thể rollback và ghi lại an toàn. | Một item gây lỗi riêng, có thể lưu rejected và bỏ qua theo nghiệp vụ. |

Đặc biệt với writer, một lần gọi thường nhận cả chunk. Nếu một item làm writer thất bại, framework cần xác định item lỗi để áp dụng skip. Hành vi cụ thể phụ thuộc writer, exception và cách Spring Batch xử lý chunk. Không nên giả định mọi write exception đều có thể skip chính xác một item.

## 12. Transaction và rollback khi retry hoặc skip

Trong chunk-oriented step, mỗi chunk thường được xử lý trong transaction. Nếu một thao tác thất bại, transaction hiện tại có thể rollback trước khi framework retry hoặc áp dụng skip policy.

Ví dụ:

```text
BEGIN chunk transaction
  read A, B, C
  process A, B, C
  writer ghi A, B, C
  writer lỗi ở B
ROLLBACK chunk

Framework áp dụng retry/skip policy
  -> thử lại theo cấu hình
  -> hoặc xác định item có thể skip
  -> ghi lại phần còn lại và commit khi hợp lệ
```

Rollback database chỉ hoàn tác các thay đổi thuộc transaction đó. Email đã gửi, HTTP request đã được đối tác xử lý hoặc message đã publish sang broker không tự động bị thu hồi. Vì vậy, retry một thao tác ngoài database có thể tạo tác dụng phụ lặp.

Khi dùng retry cho lời gọi bên ngoài, hãy cân nhắc idempotency key, outbox, tra cứu trạng thái trước khi gửi lại hoặc một cơ chế bù trừ. Với writer database, unique constraint và upsert có thể giúp xử lý việc ghi lại an toàn.

## 13. Retry và skip không đảm bảo exactly-once

Retry có thể khiến thao tác được thực hiện nhiều lần. Skip có thể khiến một item không được xử lý trong batch hiện tại. Cả hai không tự bảo đảm toàn bộ job có semantics exactly-once.

Ví dụ, API đối tác đã nhận yêu cầu thanh toán nhưng client timeout trước khi nhận response. Nếu retry bằng request mới, có thể tạo hai thanh toán. Nếu skip ngay sau timeout, batch có thể bỏ qua một thanh toán thực tế chưa rõ đã thành công hay chưa.

Các biện pháp bảo vệ thường cần có:

- Idempotency key ổn định theo batch ID và item ID.
- Unique constraint cho khóa nghiệp vụ ở database.
- Bảng rejected item hoặc outbox để ghi nhận yêu cầu chưa xử lý được.
- Quy trình đối soát trạng thái với hệ thống ngoài.
- Checkpoint và nguồn dữ liệu bất biến để restart có thể tái lập.

Retry/skip là quyết định điều khiển luồng xử lý; idempotency và đối soát mới giúp kiểm soát tác dụng phụ khi lặp.

## 14. Theo dõi retry và skip

`StepExecution` có counter cho skip:

```java
long readSkip = stepExecution.getReadSkipCount();
long processSkip = stepExecution.getProcessSkipCount();
long writeSkip = stepExecution.getWriteSkipCount();
long totalSkip = stepExecution.getSkipCount();
```

Các counter này cho biết số item/lỗi đã được skip ở từng giai đoạn. Chúng không phải bộ đếm số lần retry. Muốn theo dõi retry attempt, có thể dùng listener, log hoặc metric từ retry infrastructure phù hợp với phiên bản đang sử dụng.

`SkipListener` ghi nhận item bị bỏ qua:

```java
public class OrderSkipListener implements SkipListener<OrderInput, Order> {

    @Override
    public void onSkipInRead(Throwable throwable) {
        // Reader lỗi trước khi tạo được item.
    }

    @Override
    public void onSkipInProcess(OrderInput item, Throwable throwable) {
        // Ghi nhận khóa item và nguyên nhân.
    }

    @Override
    public void onSkipInWrite(Order item, Throwable throwable) {
        // Ghi nhận item đầu ra không ghi được.
    }
}
```

Khi phân tích sự cố, nên xem cả retry attempt, exception cuối cùng, skip counter, filter count, rollback count và trạng thái step. Chỉ nhìn tổng skip không cho biết có bao nhiêu lần retry trước đó.

## 15. `noRetry` và `noSkip`

Trong fault-tolerant step, có thể loại trừ một số exception khỏi retry hoặc skip policy bằng các cấu hình tương ứng.

Ví dụ:

```java
return new StepBuilder("importOrdersStep", jobRepository)
        .<OrderInput, Order>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .retry(TransientDataAccessException.class)
        .retryLimit(3)
        .noRetry(InvalidOrderException.class)
        .skip(Exception.class)
        .noSkip(FileNotFoundException.class)
        .skipLimit(20)
        .build();
```

Ví dụ này chỉ minh họa khả năng cấu hình loại trừ. Trong thực tế, `.skip(Exception.class)` là cấu hình rất rộng và thường không nên dùng vì có thể bỏ qua cả lỗi hạ tầng hoặc lỗi lập trình. Tốt hơn là liệt kê exception cụ thể được phép skip và chỉ dùng `noSkip` khi cần làm rõ ngoại lệ khỏi một quy tắc rộng hơn.

Tương tự, `.noRetry(...)` hữu ích khi một loại lỗi không thể phục hồi bằng thử lại, dù một lớp exception cha có thể được cấu hình retry.

## 16. Chọn chiến lược theo loại lỗi

Một bảng quyết định thực tế có thể giúp đội phát triển thống nhất cách xử lý:

| Tình huống | Retry | Skip | Hành động thường phù hợp |
|---|---:|---:|---|
| Deadlock ngắn hạn khi update | Có | Thường không | Retry có giới hạn và backoff; nếu hết retry, làm step thất bại để điều tra. |
| Dòng CSV sai định dạng | Không | Có thể | Skip, lưu dòng lỗi và số dòng để đối soát. |
| Thiếu file đầu vào bắt buộc | Không | Không | Làm job thất bại và yêu cầu cung cấp file. |
| API tra cứu tạm thời timeout | Có | Tùy nghiệp vụ | Retry; nếu hết retry, có thể lưu pending hoặc làm step thất bại. |
| Khách hàng không tồn tại | Thường không | Có thể | Skip hoặc cách ly item nếu nghiệp vụ cho phép. |
| Database mất kết nối diện rộng | Có giới hạn | Thường không | Retry ngắn có backoff; sau đó dừng để tránh bỏ qua hàng loạt. |
| Duplicate key do request lặp | Không nhất thiết | Không mặc định | Kiểm tra idempotency/unique key và xác định bản ghi đã tồn tại có cùng nội dung không. |
| Dữ liệu vi phạm quy tắc nghiệp vụ cố định | Không | Có thể | Skip hoặc rejected store, tùy nghĩa vụ nghiệp vụ. |

Không có bảng quyết định chung đúng cho mọi ứng dụng. Cùng một exception có thể mang ý nghĩa khác nhau tùy nguồn và ngữ cảnh. Hãy phân biệt lỗi riêng của item với lỗi hệ thống.

## 17. Kiểm thử retry và skip

Kiểm thử nên chứng minh rõ hai cơ chế có hành vi khác nhau:

1. **Retry thành công:** lần đầu ném exception transient, lần sau thành công; item được ghi và skip count không tăng.
2. **Retry hết, không skip:** mọi lần thử đều lỗi; chunk rollback và step kết thúc `FAILED`.
3. **Không retry, có skip:** exception skippable xảy ra; item được bỏ qua và counter skip tương ứng tăng.
4. **Retry hết rồi skip:** exception được cấu hình cả retry và skip; sau khi retry hết, item được skip nếu còn giới hạn.
5. **Vượt skip limit:** số skip vượt ngưỡng; step thất bại.
6. **Filter:** processor trả `null`; filter count tăng nhưng skip count không tăng.
7. **Tác dụng phụ lặp:** writer/API được gọi lại; idempotency key ngăn tạo kết quả nghiệp vụ trùng.

Với unit test, có thể dùng mock để mô phỏng exception theo từng lần gọi và xác nhận số lần gọi. Với integration test, dùng JobRepository và transaction manager thật trong môi trường test để xác nhận trạng thái, rollback, counter và restart.

## 18. Những lỗi cấu hình thường gặp

| Vấn đề | Nguyên nhân | Hướng xử lý |
|---|---|---|
| Retry dữ liệu sai nhiều lần | Cấu hình retry cho exception không thể tự phục hồi. | Bỏ retry cho lỗi dữ liệu; dùng skip hoặc fail theo nghiệp vụ. |
| Database lỗi nhưng job vẫn COMPLETED | Skip policy quá rộng, bỏ qua lỗi hạ tầng. | Thu hẹp exception được skip; lỗi hệ thống nên làm step thất bại. |
| Item bị mất sau retry exhaustion | Không có skip/rejected path và người vận hành không theo dõi lỗi. | Để step fail hoặc lưu rejected item theo transaction phù hợp. |
| Skip count bằng 0 dù item không đến writer | Processor trả `null` nên item được filter. | Kiểm tra `filterCount` và điều kiện processor. |
| Ghi trùng khi retry | Tác dụng phụ không idempotent hoặc không có unique key. | Dùng idempotency key, upsert, outbox hoặc đối soát. |
| Retry storm | Nhiều worker retry ngay lập tức khi downstream đang quá tải. | Dùng backoff/jitter, giới hạn concurrency và timeout. |
| Không biết item bị skip | Chỉ xem `skipCount`, không có listener hoặc bảng lỗi. | Dùng `SkipListener` và lưu business key/exception. |
| Retry và skip cùng áp dụng nhưng hành vi khó hiểu | Không phân loại exception hoặc không kiểm thử tổ hợp policy. | Viết ma trận lỗi và test từng nhánh. |

## 19. Quy trình thiết kế retry/skip cho một step

Khi xây dựng fault-tolerant step, hãy làm rõ các câu hỏi theo thứ tự:

1. **Phân loại exception:** lỗi nào là tạm thời, lỗi nào là dữ liệu, lỗi nào là cấu hình/hạ tầng?
2. **Chọn retry policy:** chỉ retry các lỗi có khả năng phục hồi; đặt giới hạn và backoff phù hợp.
3. **Chọn skip policy:** chỉ skip lỗi item mà nghiệp vụ cho phép loại bỏ; đặt tổng skip limit.
4. **Quyết định sau retry exhaustion:** skip, cách ly item hay làm step thất bại?
5. **Ghi nhận lỗi:** lưu item key, giai đoạn read/process/write, exception và execution ID.
6. **Kiểm soát tác dụng phụ:** bảo đảm retry/restart không tạo giao dịch, message hoặc email trùng.
7. **Kiểm tra transaction:** xác định chunk nào rollback, chunk nào đã commit và tài nguyên ngoài transaction nào có thể đã thay đổi.
8. **Kiểm thử các nhánh:** retry thành công, retry hết, skip, vượt limit và lỗi không được skip.
9. **Thiết kế vận hành:** xác định ai xử lý rejected item và cách restart sau khi sửa nguyên nhân.

Đừng bắt đầu bằng cách tăng `retryLimit` hoặc `skipLimit` cho đến khi job chạy qua. Các giới hạn phải phản ánh thời gian phục hồi có thể chấp nhận và mức lỗi dữ liệu nghiệp vụ cho phép.

## 20. Những điểm cần ghi nhớ

- Retry thử lại thao tác để xử lý thành công cùng item/chunk; skip chấp nhận bỏ qua item lỗi và tiếp tục.
- Retry phù hợp với lỗi tạm thời; skip phù hợp với lỗi item mà nghiệp vụ cho phép loại bỏ hoặc xử lý sau.
- Retry policy và skip policy độc lập; exception có thể retry, skip, cả hai hoặc không thuộc policy nào.
- Khi retry hết, item chỉ được skip nếu exception được skip policy cho phép và skip limit chưa bị vượt; nếu không, step thất bại.
- Exception skippable nhưng không retryable có thể bị skip mà không cần thử lại.
- `retryLimit` giới hạn attempt theo retry policy; `skipLimit` giới hạn tổng skip của read, process và write.
- Filter bằng cách processor trả `null` khác với skip do exception; chúng có counter riêng.
- Retry/skip không tự bảo đảm exactly-once; writer và tích hợp bên ngoài cần idempotency, unique key hoặc outbox.
- `SkipListener` giúp ghi nhận item bị skip; retry attempt cần được theo dõi bằng listener/log/metric phù hợp.
- Lỗi hệ thống diện rộng như database unavailable thường nên làm step thất bại sau retry có giới hạn thay vì skip hàng loạt.
- Kiểm thử từng tổ hợp retry/skip, đặc biệt trường hợp retry hết rồi skip hoặc retry hết rồi fail.

Khi thiết kế Spring Batch, hãy coi retry là cơ hội phục hồi thao tác và skip là quyết định chấp nhận loại bỏ item. Chọn hai policy dựa trên loại exception, ý nghĩa nghiệp vụ và tác dụng phụ có thể xảy ra. Khi có giới hạn rõ, ghi nhận item lỗi và bảo vệ writer bằng idempotency, job sẽ vừa có khả năng tự phục hồi trước lỗi tạm thời vừa giữ được tính minh bạch khi dữ liệu không thể xử lý.
