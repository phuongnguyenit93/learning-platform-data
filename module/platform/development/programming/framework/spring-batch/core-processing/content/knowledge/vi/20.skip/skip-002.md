# Skip limit

Trong Spring Batch, một Step có thể được cấu hình để bỏ qua một số item gặp lỗi và tiếp tục xử lý những item còn lại. `skipLimit` đặt giới hạn tổng số item được phép bỏ qua trong một Step. Khi số lần skip vượt giới hạn, Step thất bại thay vì tiếp tục bỏ qua dữ liệu.

Skip limit giúp cân bằng giữa khả năng chịu lỗi và tính đầy đủ của dữ liệu. Một vài bản ghi đầu vào sai định dạng có thể chấp nhận được trong một Job import lớn, nhưng nếu hàng nghìn bản ghi bị bỏ qua thì kết quả có thể không còn đáng tin cậy. Vì vậy, cần chọn giới hạn dựa trên quy tắc nghiệp vụ, khối lượng dữ liệu và tỷ lệ lỗi chấp nhận được.

## 1. Skip và skip limit là gì?

Trong chunk-oriented processing, Spring Batch đọc item, xử lý item qua processor nếu có, rồi ghi các item đầu ra bằng writer. Nếu một exception xảy ra, Step có thể được cấu hình để retry, skip hoặc thất bại.

**Skip** là quyết định bỏ qua một item do lỗi được phân loại là có thể skip. **Skip limit** là số lượng skip tối đa mà Step được phép chấp nhận trong lần thực thi logic đó.

Ví dụ, một Job import 10.000 khách hàng có thể cho phép bỏ qua tối đa 20 bản ghi sai định dạng:

```java
.faultTolerant()
.skip(FlatFileParseException.class)
.skipLimit(20)
```

Nếu có 12 dòng bị lỗi parse và được skip, Step vẫn có thể hoàn tất. Nếu có lần skip thứ 21, giới hạn bị vượt và Step thất bại.

Skip limit không phải số item được đọc, số item bị filter hoặc số lần retry. Nó chỉ đếm các item thực sự được bỏ qua theo skip policy.

## 2. Skip limit áp dụng cho cả ba giai đoạn

Spring Batch có thể skip lỗi phát sinh ở ba giai đoạn của chunk:

- **Read skip:** reader không thể đọc một item, ví dụ dòng file không thể parse.
- **Process skip:** processor nhận item nhưng không thể xử lý, ví dụ dữ liệu không thỏa quy tắc nghiệp vụ.
- **Write skip:** writer không thể ghi item, ví dụ bản ghi vi phạm một quy tắc dữ liệu có thể bỏ qua.

`skipLimit` áp dụng cho tổng số skip ở cả ba giai đoạn, không phải một giới hạn riêng cho từng giai đoạn.

Ví dụ Step có `skipLimit(10)`:

| Giai đoạn | Số item bị skip |
|---|---:|
| Read | 3 |
| Process | 4 |
| Write | 3 |
| **Tổng** | **10** |

Step đã sử dụng hết giới hạn nhưng vẫn có thể tiếp tục nếu không phát sinh thêm skip. Nếu có thêm một item bị skip ở bất kỳ giai đoạn nào, tổng sẽ thành 11 và Step thất bại.

Các bộ đếm tương ứng được lưu trong `StepExecution`: `readSkipCount`, `processSkipCount` và `writeSkipCount`. Tổng skip có thể được xem là tổng của ba bộ đếm này.

## 3. Giá trị mặc định và cách đếm giới hạn

Nếu không cấu hình skip limit, mặc định Step không cho phép skip. Có thể hiểu giá trị mặc định là 0: lần đầu tiên một exception cần được skip sẽ làm vượt giới hạn và Step thất bại.

Với `skipLimit(10)`, Spring Batch cho phép tối đa 10 skip. Lần skip tiếp theo là lần thứ 11 sẽ vượt giới hạn.

| Cấu hình | Số skip được chấp nhận tối đa | Kết quả khi có thêm một skip |
|---|---:|---|
| Không cấu hình skip limit | 0 | Step thất bại khi phát sinh skip |
| `skipLimit(1)` | 1 | Skip thứ 2 làm Step thất bại |
| `skipLimit(10)` | 10 | Skip thứ 11 làm Step thất bại |
| `skipLimit(100)` | 100 | Skip thứ 101 làm Step thất bại |

Giới hạn được áp dụng cho toàn bộ Step, cộng dồn read, process và write skip. Không nên hiểu `skipLimit(10)` là cho phép 10 lỗi đọc, cộng thêm 10 lỗi xử lý và 10 lỗi ghi.

## 4. Cấu hình skip limit trong Spring Batch 5

Với Java configuration, dùng `faultTolerant()`, khai báo exception được phép skip và đặt `skipLimit()`:

```java
@Bean
Step importCustomersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<CustomerInput> reader,
        ItemProcessor<CustomerInput, Customer> processor,
        ItemWriter<Customer> writer) {

    return new StepBuilder("importCustomersStep", jobRepository)
            .<CustomerInput, Customer>chunk(500, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .faultTolerant()
            .skip(FlatFileParseException.class)
            .skip(InvalidCustomerException.class)
            .skipLimit(50)
            .build();
}
```

Trong ví dụ:

- `FlatFileParseException` đại diện cho lỗi parse dòng file.
- `InvalidCustomerException` đại diện cho lỗi dữ liệu khách hàng theo nghiệp vụ.
- `skipLimit(50)` cho phép tổng cộng tối đa 50 item bị skip ở read, process và write.
- Các exception không được phân loại là skippable vẫn có thể làm Step thất bại.

Chỉ thêm những exception mà nghiệp vụ thực sự cho phép bỏ qua. Không nên cấu hình skip rộng chỉ để Job luôn chạy đến cuối.

## 5. Khai báo loại exception được skip

`skip(ExceptionType.class)` khai báo một loại exception và các lớp con phù hợp là skippable. Có thể khai báo nhiều loại exception:

```java
.faultTolerant()
.skip(FlatFileParseException.class)
.skip(InvalidCustomerException.class)
.skip(InvalidAddressException.class)
.skipLimit(100)
```

Ví dụ này cho phép bỏ qua lỗi parse file, lỗi dữ liệu khách hàng và lỗi địa chỉ, trong giới hạn tổng cộng 100 item.

### Loại trừ exception bằng `noSkip()`

Trong một số trường hợp, có thể khai báo một nhóm exception rộng là skippable rồi loại trừ các loại nguy hiểm bằng `noSkip()`:

```java
.faultTolerant()
.skip(Exception.class)
.noSkip(DeadlockLoserDataAccessException.class)
.noSkip(DataAccessResourceFailureException.class)
.skipLimit(20)
```

Ví dụ trên chỉ nhằm minh họa cách khai báo. Trong production, skip mọi `Exception` thường quá rộng và dễ che giấu lỗi lập trình hoặc lỗi hạ tầng. Thông thường nên khai báo cụ thể các exception nghiệp vụ được phép skip.

Khi quy tắc skip và no-skip cùng khớp do quan hệ kế thừa, Spring Batch dùng cơ chế phân loại exception theo loại cụ thể và quan hệ superclass để quyết định. Nên tránh cấu hình các quy tắc chồng lấn khó hiểu; hãy kiểm tra loại exception thực tế và viết kiểm thử cho các trường hợp biên.

## 6. Skip limit khác retry limit

Skip limit và retry limit thường xuất hiện cùng nhau trong fault-tolerant Step nhưng kiểm soát hai hành vi khác nhau.

| Tiêu chí | Skip limit | Retry limit |
|---|---|---|
| Mục đích | Giới hạn số item bị bỏ qua | Giới hạn số lần thử lại thao tác/item gặp lỗi |
| Khi nào tăng? | Khi item thực sự được skip | Khi một lần thử gặp exception retryable |
| Kết quả cuối | Item bị loại khỏi luồng xử lý | Item có thể thành công sau retry hoặc cuối cùng bị skip/fail |
| Ví dụ | Bản ghi có ngày không hợp lệ | Deadlock tạm thời hoặc timeout ngắn hạn |

Ví dụ cấu hình cả retry và skip:

```java
return new StepBuilder("importOrdersStep", jobRepository)
        .<OrderInput, Order>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .retry(TransientDataAccessException.class)
        .retryLimit(3)
        .skip(InvalidOrderException.class)
        .skipLimit(25)
        .build();
```

Trong ví dụ, lỗi truy cập dữ liệu tạm thời được thử lại theo retry policy; lỗi đơn hàng không hợp lệ được phép skip trong giới hạn 25. Cần phân loại exception sao cho một lỗi không bị retry hoặc skip ngoài ý muốn.

Nếu exception vừa retryable vừa skippable, Spring Batch có thể retry trước theo chính sách retry; khi retry không thành công, quyết định tiếp theo phụ thuộc skip policy và cấu hình fault tolerance. Hãy kiểm thử hành vi của loại exception đó thay vì chỉ nhìn vào tên các phương thức cấu hình.

## 7. Skip limit khác filter

Processor có thể trả về `null` để chủ động loại một item khỏi output. Đây là **filter**, không phải skip vì không có exception.

```java
@Bean
ItemProcessor<OrderInput, Order> orderProcessor() {
    return input -> {
        if (input.isCancelled()) {
            return null; // Filter có chủ đích
        }

        return convert(input);
    };
}
```

Item bị filter được tính vào `filterCount`, không làm tăng skip count và không tiêu thụ skip limit.

Ngược lại, nếu processor ném `InvalidOrderException` và exception đó được cấu hình skippable, item bị bỏ qua do lỗi. Trường hợp này làm tăng `processSkipCount` và tiêu thụ skip limit.

| Tình huống | Cơ chế | Ảnh hưởng đến skip limit |
|---|---|---|
| Processor trả `null` | Filter | Không |
| Reader ném exception skippable | Read skip | Có |
| Processor ném exception skippable | Process skip | Có |
| Writer ném exception skippable và item được cô lập/bỏ qua | Write skip | Có |
| Exception được retry rồi thành công | Retry thành công | Không |
| Exception không retry/skip được | Step thất bại | Không được chấp nhận như một skip thành công |

## 8. Khi vượt skip limit thì điều gì xảy ra?

Khi số skip tiếp theo làm tổng số skip vượt giới hạn, Spring Batch ném `SkipLimitExceededException` và Step thất bại. Framework không tiếp tục bỏ qua item đó.

Ví dụ `skipLimit(3)`:

```text
Skip 1 -> được chấp nhận
Skip 2 -> được chấp nhận
Skip 3 -> được chấp nhận
Skip 4 -> vượt limit
           |
           v
      Step FAILED
```

Khi Step thất bại do vượt limit:

- Job thường chuyển sang `FAILED` nếu flow không có transition xử lý trạng thái đó.
- Các chunk đã commit trước đó vẫn được giữ lại.
- Transaction của chunk hiện tại được xử lý theo rollback policy.
- Các item tiếp theo chưa được xử lý trong lần execution đó.
- Metadata StepExecution lưu trạng thái và các bộ đếm liên quan để điều tra.

Không nên coi việc vượt skip limit là một lỗi có thể tự động bỏ qua. Đây là tín hiệu rằng chất lượng dữ liệu hoặc điều kiện vận hành đã vượt ngưỡng được chấp nhận.

## 9. SkipListener và skip limit

`SkipListener` được gọi khi một item thực sự được skip theo policy. Nó có ba callback:

- `onSkipInRead(Throwable t)` khi reader gặp lỗi và item bị skip.
- `onSkipInProcess(T item, Throwable t)` khi processor không xử lý được item và item bị skip.
- `onSkipInWrite(S item, Throwable t)` khi writer không ghi được item và item bị skip.

Ví dụ:

```java
@Component
public class CustomerSkipListener
        implements SkipListener<CustomerInput, Customer> {

    private final SkippedCustomerService skippedCustomerService;

    public CustomerSkipListener(
            SkippedCustomerService skippedCustomerService) {
        this.skippedCustomerService = skippedCustomerService;
    }

    @Override
    public void onSkipInRead(Throwable t) {
        skippedCustomerService.recordReadError(t);
    }

    @Override
    public void onSkipInProcess(CustomerInput item, Throwable t) {
        skippedCustomerService.recordProcessError(item.customerId(), t);
    }

    @Override
    public void onSkipInWrite(Customer item, Throwable t) {
        skippedCustomerService.recordWriteError(item.customerId(), t);
    }
}
```

Đăng ký listener cùng cấu hình skip:

```java
return new StepBuilder("importCustomersStep", jobRepository)
        .<CustomerInput, Customer>chunk(500, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .skip(InvalidCustomerException.class)
        .skipLimit(50)
        .listener(customerSkipListener)
        .build();
```

Listener giúp lưu business key và nguyên nhân để xử lý lại sau này. Tuy nhiên, khi skip limit đã bị vượt, item tiếp theo không được chấp nhận là một skip hợp lệ; không nên dựa vào `SkipListener` để ghi nhận như thể mọi lỗi đều đã được bỏ qua.

## 10. Ghi nhận tỷ lệ skip thay vì chỉ nhìn số tuyệt đối

Một skip limit cố định có thể không phù hợp với mọi quy mô dữ liệu. Ví dụ, 20 lỗi trên 100 bản ghi là tỷ lệ 20%, trong khi 20 lỗi trên 1.000.000 bản ghi chỉ là 0,002%.

Nên theo dõi cả:

- Tổng số item bị skip.
- Số skip theo read, process và write.
- Tổng số item đọc hoặc số lượng item dự kiến.
- Tỷ lệ skip trên tổng số item.
- Nhóm exception và nguồn dữ liệu gây lỗi.
- Xu hướng skip qua các lần chạy.

Ví dụ:

| Job | Read count | Total skip | Skip rate |
|---|---:|---:|---:|
| Import A | 100 | 20 | 20% |
| Import B | 1.000 | 20 | 2% |
| Import C | 1.000.000 | 20 | 0,002% |

Spring Batch cung cấp skip limit theo số lượng. Nếu nghiệp vụ yêu cầu ngưỡng theo tỷ lệ, có thể dùng listener hoặc Step tổng hợp để kiểm tra các bộ đếm và quyết định trạng thái cuối. Cần lưu ý việc kiểm tra tỷ lệ ở cuối Step có thể xảy ra sau khi dữ liệu đã được commit; nếu phải ngăn ghi dữ liệu ngay khi tỷ lệ vượt ngưỡng, cần thiết kế policy hoặc kiểm tra theo từng chunk phù hợp.

## 11. Dùng SkipPolicy tùy chỉnh

Khi quy tắc skip không thể biểu diễn gọn bằng danh sách `.skip()` và `.noSkip()`, có thể triển khai `SkipPolicy`.

Interface có dạng:

```java
public interface SkipPolicy {
    boolean shouldSkip(Throwable t, long skipCount)
            throws SkipLimitExceededException;
}
```

`shouldSkip()` nhận exception và số lượng skip hiện tại. Trả về `true` nếu exception có thể được skip; trả về `false` nếu không được skip. Policy cũng có thể ném `SkipLimitExceededException` khi vượt ngưỡng.

Ví dụ policy có giới hạn và chỉ chấp nhận một số lỗi nghiệp vụ:

```java
public class CustomerSkipPolicy implements SkipPolicy {

    private final long limit;

    public CustomerSkipPolicy(long limit) {
        this.limit = limit;
    }

    @Override
    public boolean shouldSkip(Throwable t, long skipCount)
            throws SkipLimitExceededException {

        if (t instanceof InvalidCustomerException
                || t instanceof FlatFileParseException) {
            if (skipCount < limit) {
                return true;
            }
            throw new SkipLimitExceededException(
                    "Customer skip limit exceeded", t);
        }

        return false;
    }
}
```

**Lưu ý:** Cách đếm `skipCount` và thời điểm policy được gọi thuộc hợp đồng của Spring Batch. Khi viết policy tùy chỉnh, hãy kiểm tra đúng phiên bản API và kiểm thử ranh giới limit, đặc biệt là trường hợp skip cuối cùng được phép và lần skip tiếp theo.

Đăng ký policy:

```java
.faultTolerant()
.skipPolicy(new CustomerSkipPolicy(50))
```

Khi dùng `SkipPolicy`, policy chịu trách nhiệm quyết định loại exception và giới hạn. Tránh đồng thời khai báo nhiều quy tắc `.skip()`, `.noSkip()` và custom policy theo cách chồng lấn khiến người đọc không biết quy tắc nào quyết định cuối cùng.

## 12. Chọn skip limit theo yêu cầu nghiệp vụ

Không có một giá trị skip limit tối ưu cho mọi Job. Có thể cân nhắc các yếu tố sau:

### Mức độ quan trọng của dữ liệu

Với dữ liệu tài chính, số dư hoặc giao dịch, một item bị skip có thể làm sai kết quả tổng hợp. Skip limit nên rất thấp hoặc không cho phép skip, tùy quy trình đối soát và khả năng xử lý lỗi riêng.

Với dữ liệu tham chiếu hoặc import danh mục, một tỷ lệ nhỏ bản ghi không hợp lệ có thể được chấp nhận nếu được ghi vào dead-letter store và có quy trình xử lý bù.

### Quy mô và chất lượng nguồn

Nguồn dữ liệu ổn định, đã được kiểm tra trước có thể dùng giới hạn thấp. Nguồn bên ngoài có lịch sử lỗi định dạng có thể cần giới hạn phù hợp hơn, nhưng không nên tăng ngưỡng chỉ để Job luôn hoàn tất.

### Khả năng xử lý lại

Nếu mọi item bị skip đều được lưu với business key, nguyên nhân và nguồn, việc cho phép skip có thể an toàn hơn. Nếu không thể khôi phục hoặc tái tạo item, nên đặt giới hạn chặt chẽ.

### SLO và batch window

Nếu Job phải hoàn tất trong một khoảng thời gian, có thể cần cho phép một lượng lỗi nhất định để các item hợp lệ vẫn được xử lý. Tuy nhiên, kết quả cần được đánh dấu có lỗi và không được công bố như dữ liệu hoàn toàn sạch.

## 13. Xử lý khi Job vượt skip limit

Khi Step vượt skip limit, quy trình vận hành nên giúp xác định nguyên nhân và chạy lại an toàn:

1. Xem JobExecution và StepExecution để biết Step nào thất bại.
2. Kiểm tra `readSkipCount`, `processSkipCount`, `writeSkipCount` và exception cuối cùng.
3. Tra cứu dead-letter/audit record để biết item nào đã bị bỏ qua trước khi limit bị vượt.
4. Phân loại lỗi dữ liệu, lỗi nguồn, lỗi lập trình hay lỗi hạ tầng.
5. Sửa dữ liệu hoặc nguồn đầu vào, hoặc điều chỉnh policy nếu quy tắc nghiệp vụ thực sự thay đổi.
6. Restart cùng JobInstance khi mục tiêu là tiếp tục công việc đã thất bại và reader hỗ trợ checkpoint.
7. Nếu cần một lần chạy nghiệp vụ mới với dữ liệu hoặc phạm vi khác, tạo identifying JobParameters phù hợp.
8. Đối soát kết quả đã commit và các tác dụng phụ bên ngoài trước khi chạy lại.

Không nên sửa trực tiếp các bảng metadata `BATCH_*` để tăng skip count hoặc ép Step thành `COMPLETED`. Metadata được Spring Batch sử dụng để điều khiển restart; thay đổi thủ công có thể làm trạng thái execution không nhất quán.

## 14. Restart và skip limit

Skip count được lưu trong metadata của StepExecution. Khi một Step thất bại và được restart, Spring Batch sử dụng trạng thái execution và checkpoint đã lưu để tiếp tục theo cơ chế restart của Step. Các chunk đã commit vẫn được giữ; các item chưa commit có thể được đọc hoặc xử lý lại tùy reader và transaction behavior.

Vì vậy, khi vận hành cần hiểu skip limit gắn với trạng thái thực thi của Step và cách framework khôi phục StepExecution. Không nên coi restart như một Job hoàn toàn mới với bộ đếm skip tự động bằng 0. Nếu cần chạy lại như một đơn vị nghiệp vụ mới, phải xác định JobInstance mới bằng identifying parameters phù hợp.

Reader hỗ trợ `ItemStream` có thể lưu checkpoint trong StepExecutionContext. Tuy nhiên, việc lưu checkpoint không làm cho tác dụng phụ bên ngoài transaction trở nên idempotent. Writer và service ngoài vẫn cần cơ chế chống trùng nếu item có thể được thực hiện lại.

## 15. Skip limit trong writer và hành vi cô lập item lỗi

Writer nhận một chunk gồm nhiều item. Nếu một thao tác ghi thất bại, Spring Batch có thể cần xác định item cụ thể gây lỗi để áp dụng skip. Tùy cấu hình và kiểu writer, framework có thể thử ghi lại các nhóm nhỏ hơn hoặc từng item để cô lập lỗi.

Điều này có một số hệ quả:

- Writer có thể được gọi nhiều lần trong quá trình xác định item lỗi.
- Các thao tác ghi cần tham gia transaction hoặc có khả năng retry an toàn.
- Không nên gửi email, gọi API tạo giao dịch hoặc thực hiện tác dụng phụ không idempotent trong writer mà không có cơ chế bảo vệ.
- Một exception ở writer không tự động đồng nghĩa toàn bộ chunk được skip; item cụ thể phải được xác định và exception phải được policy cho phép.

Với writer có thể ghi một phần chunk trước khi lỗi, rollback thường rất quan trọng để giữ tính nguyên tử. Chỉ dùng no-rollback cho exception đã được phân loại rõ và chắc chắn không có partial write cần hoàn tác.

## 16. Theo dõi và cảnh báo skip limit

Nên xây dựng dashboard hoặc cảnh báo dựa trên số lượng và tỷ lệ skip. Một số chỉ số hữu ích:

| Chỉ số | Mục đích |
|---|---|
| `readSkipCount` | Theo dõi lỗi đọc nguồn |
| `processSkipCount` | Theo dõi lỗi validation/chuyển đổi |
| `writeSkipCount` | Theo dõi lỗi ghi dữ liệu đích |
| Total skip | Đánh giá mức sử dụng skip limit |
| Skip rate | So sánh chất lượng dữ liệu giữa các lần chạy |
| Skip limit exceeded count | Phát hiện Job thất bại do vượt ngưỡng |
| Dead-letter backlog | Theo dõi item đang chờ xử lý lại |

Có thể cảnh báo trước khi đạt giới hạn, chẳng hạn khi tổng skip đạt 70% hoặc 90% ngưỡng. Với Job có dữ liệu quan trọng, cảnh báo sớm giúp người vận hành điều tra trước khi Step thất bại.

Không nên chỉ dựa vào trạng thái Job `COMPLETED`. Một Job có thể hoàn tất với số skip khác 0. Hệ thống cần công bố số lượng item bị bỏ qua và chính sách chấp nhận kết quả có lỗi.

## 17. Các lỗi thường gặp

**Hiểu `skipLimit(10)` là 10 skip cho mỗi giai đoạn:** giới hạn áp dụng cho tổng read, process và write skip của Step.

**Cho rằng mặc định có thể skip một số lỗi:** mặc định skip limit là 0; cần cấu hình skip policy và giới hạn.

**Nhầm skip limit với retry limit:** retry là số lần thử lại, skip limit là số item bị bỏ qua.

**Nhầm filter với skip:** processor trả `null` làm tăng filter count, không tiêu thụ skip limit.

**Cấu hình `skip(Exception.class)` quá rộng:** có thể bỏ qua lỗi hạ tầng hoặc lỗi lập trình và làm dữ liệu thiếu.

**Chỉ đăng ký SkipListener mà không khai báo skip:** listener không tự cho phép bỏ qua exception.

**Tăng skip limit để Job luôn thành công:** Job có thể hoàn tất nhưng kết quả thiếu dữ liệu hoặc sai nghiệp vụ.

**Không lưu item bị skip:** sau khi Job kết thúc, khó điều tra hoặc xử lý lại dữ liệu lỗi.

**Cho rằng vượt limit chỉ làm item cuối bị bỏ qua:** khi vượt ngưỡng, Step thất bại và không tiếp tục skip như bình thường.

**Không tính đến restart:** cần kiểm tra metadata, checkpoint và tác dụng phụ đã commit trước khi chạy lại.

## Kết luận

`skipLimit` đặt số lượng item tối đa mà một Step được phép bỏ qua. Giới hạn này được tính chung cho lỗi ở reader, processor và writer; mặc định là 0 nếu không cấu hình. Với `skipLimit(10)`, tối đa 10 item được skip và lần skip thứ 11 làm Step thất bại. Hãy khai báo cụ thể exception có thể skip, dùng `noSkip()` cho những lỗi cần dừng khi thật sự cần, phân biệt skip với retry và filter, đồng thời ghi nhận item lỗi qua `SkipListener` hoặc dead-letter store. Chọn giới hạn theo mức độ quan trọng của dữ liệu và khả năng xử lý lại, theo dõi cả số lượng lẫn tỷ lệ skip, và kiểm thử restart để bảo đảm dữ liệu đã commit không bị xử lý trùng.
