# LineCallbackHandler

Trong Spring Batch, `LineCallbackHandler` là callback được `FlatFileItemReader` sử dụng để xử lý những dòng được cấu hình bỏ qua ở đầu file. Trường hợp thường gặp nhất là file CSV có một hoặc nhiều dòng header chứa tên cột, thông tin phiên bản hoặc metadata của lần export. Reader không chuyển những dòng này thành item, nhưng ứng dụng vẫn có thể cần đọc chúng để ghi log, kiểm tra định dạng hoặc chuẩn bị thông tin cho bước mapping.

`LineCallbackHandler` nhận nội dung một dòng dưới dạng `String` và thực hiện một hành động phụ. Nó không trả về item, không thay thế `LineMapper` và không phải cơ chế skip exception của chunk processing. Trong `FlatFileItemReader`, callback được đăng ký cùng `linesToSkip` để xử lý từng dòng đầu file bị bỏ qua.

## 1. LineCallbackHandler giải quyết vấn đề gì?

Một file đầu vào có thể chứa header trước phần dữ liệu:

```text
orderId,customerId,amount,currency
1001,C001,250000,VND
1002,C002,175000,VND
1003,C003,99000,VND
```

Nếu reader dùng `LineMapper` để parse từng dòng thành `OrderInput`, dòng đầu tiên không phải một đơn hàng. Có thể cấu hình reader bỏ qua một dòng đầu và gọi callback để ghi nhận header.

```text
FlatFileItemReader mở file
          |
          v
Đọc số dòng được cấu hình trong linesToSkip
          |
          +--> Gọi LineCallbackHandler cho từng dòng bị bỏ qua
          |
          v
Đọc các dòng dữ liệu còn lại
          |
          v
LineMapper.mapLine(...)
          |
          v
OrderInput
```

Như vậy, header không đi vào pipeline item thông thường. Callback cho phép ứng dụng quan sát hoặc trích xuất thông tin từ header trước khi reader trả về các item dữ liệu.

## 2. Interface LineCallbackHandler

Interface nằm trong package `org.springframework.batch.item.file` và có một phương thức:

```java
package org.springframework.batch.item.file;

@FunctionalInterface
public interface LineCallbackHandler {
    void handleLine(String line);
}
```

Phương thức `handleLine` nhận nội dung dòng bị bỏ qua. Nó không nhận `StepExecution`, số dòng hoặc `ExecutionContext`; nếu cần những thông tin đó, callback có thể dùng collaborator được inject hoặc state theo scope của Step.

Vì interface chỉ có một phương thức, có thể triển khai bằng class riêng, method reference hoặc lambda:

```java
LineCallbackHandler callback = line ->
        log.info("Skipped header line: {}", line);
```

Callback phù hợp với thao tác nhỏ, đồng bộ và nhanh như ghi log, kiểm tra header hoặc lưu metadata vào một object theo Step. Không nên thực hiện một công việc dài, gọi hệ thống ngoài hoặc ghi dữ liệu nghiệp vụ không idempotent trong callback này.

## 3. Cấu hình với FlatFileItemReaderBuilder

Trong Spring Batch 5, `FlatFileItemReaderBuilder` cung cấp hai cấu hình liên quan:

- `linesToSkip(int)`: số dòng ở đầu file cần bỏ qua.
- `skippedLinesCallback(LineCallbackHandler)`: callback được gọi cho từng dòng bị bỏ qua.

Ví dụ reader bỏ qua một dòng header:

```java
@Bean
@StepScope
FlatFileItemReader<OrderInput> orderReader(
        @Value("#{jobParameters['input.file']}") String inputFile) {

    return new FlatFileItemReaderBuilder<OrderInput>()
            .name("orderReader")
            .resource(new FileSystemResource(inputFile))
            .linesToSkip(1)
            .skippedLinesCallback(line ->
                    log.info("Input header: {}", line))
            .delimited()
            .names("orderId", "customerId", "amount", "currency")
            .targetType(OrderInput.class)
            .saveState(true)
            .build();
}
```

Trong ví dụ:

- Reader mở file được truyền qua JobParameter `input.file`.
- Dòng đầu tiên được bỏ qua vì `linesToSkip(1)`.
- `skippedLinesCallback` nhận nguyên văn nội dung dòng header để ghi log.
- Các dòng còn lại được tokenizer và mapper chuyển thành `OrderInput`.
- `saveState(true)` cho phép reader lưu trạng thái đọc để hỗ trợ restart.

Nếu không cấu hình `skippedLinesCallback`, các dòng được chỉ định bỏ qua vẫn bị bỏ qua; ứng dụng chỉ không nhận callback để xử lý chúng.

## 4. Bỏ qua nhiều dòng header

Một số file có nhiều dòng metadata trước dòng tiêu đề cột:

```text
Exported by: Order Management System
Export version: 3
Business date: 2026-11-15
orderId,customerId,amount,currency
1001,C001,250000,VND
1002,C002,175000,VND
```

Có thể bỏ qua bốn dòng đầu và xử lý từng dòng qua callback:

```java
@Bean
@StepScope
FlatFileItemReader<OrderInput> orderReader(
        @Value("#{jobParameters['input.file']}") String inputFile) {

    return new FlatFileItemReaderBuilder<OrderInput>()
            .name("orderReader")
            .resource(new FileSystemResource(inputFile))
            .linesToSkip(4)
            .skippedLinesCallback(line ->
                    log.debug("Skipped file metadata: {}", line))
            .delimited()
            .names("orderId", "customerId", "amount", "currency")
            .targetType(OrderInput.class)
            .build();
}
```

`linesToSkip` là số dòng được bỏ qua ở đầu resource. Callback được gọi một lần cho mỗi dòng trong nhóm đó khi reader mở resource. Nếu số dòng header thay đổi theo định dạng file, cần xác định cách nhận biết header trước khi cấu hình reader; không nên dùng một số cố định nếu file không có hợp đồng định dạng ổn định.

## 5. Dùng callback để ghi nhận header

Ngoài logging, callback có thể trích xuất metadata từ header. Ví dụ file export có dòng chứa ngày nghiệp vụ và mã tenant:

```text
# businessDate=2026-11-15;tenantId=42
orderId,customerId,amount
1001,C001,250000
```

Có thể dùng một collaborator giữ metadata trong phạm vi Step:

```java
public class InputFileMetadata {

    private LocalDate businessDate;
    private Long tenantId;

    public void capture(String line) {
        if (!line.startsWith("#")) {
            return;
        }

        for (String token : line.substring(1).split(";")) {
            String[] pair = token.split("=", 2);
            if (pair.length != 2) {
                throw new IllegalArgumentException(
                        "Invalid metadata header: " + line);
            }

            switch (pair[0].trim()) {
                case "businessDate" ->
                        businessDate = LocalDate.parse(pair[1].trim());
                case "tenantId" ->
                        tenantId = Long.valueOf(pair[1].trim());
                default -> throw new IllegalArgumentException(
                        "Unknown header field: " + pair[0]);
            }
        }
    }

    public LocalDate getBusinessDate() {
        return businessDate;
    }

    public Long getTenantId() {
        return tenantId;
    }
}
```

Đăng ký object theo Step scope và truyền method reference cho callback:

```java
@Bean
@StepScope
InputFileMetadata inputFileMetadata() {
    return new InputFileMetadata();
}

@Bean
@StepScope
FlatFileItemReader<OrderInput> orderReader(
        @Value("#{jobParameters['input.file']}") String inputFile,
        InputFileMetadata metadata) {

    return new FlatFileItemReaderBuilder<OrderInput>()
            .name("orderReader")
            .resource(new FileSystemResource(inputFile))
            .linesToSkip(2)
            .skippedLinesCallback(metadata::capture)
            .delimited()
            .names("orderId", "customerId", "amount")
            .targetType(OrderInput.class)
            .saveState(true)
            .build();
}
```

Ở đây, `InputFileMetadata` chỉ tồn tại trong StepExecution tương ứng. Một Step khác có thể inject cùng bean StepScope proxy để đọc metadata đã capture trong lần mở reader đó. Nếu dữ liệu cần được dùng sau khi Step kết thúc hoặc phải tồn tại qua restart, hãy lưu các giá trị cần thiết vào Job/Step `ExecutionContext` hoặc một nơi lưu trữ bền vững; field của object trong bộ nhớ không phải checkpoint.

### Kiểm tra header trước khi xử lý item

Nếu header là một phần của hợp đồng file, callback nên xác thực format và từ chối file sai ngay khi reader mở. Ví dụ:

```java
private void validateColumnHeader(String line) {
    List<String> columns = Arrays.stream(line.split(",", -1))
            .map(String::trim)
            .toList();

    List<String> expected = List.of(
            "orderId", "customerId", "amount", "currency");

    if (!columns.equals(expected)) {
        throw new IllegalArgumentException(
                "Unexpected CSV columns: " + line);
    }
}
```

Nếu callback ném runtime exception, thao tác mở reader có thể thất bại và Step không tiếp tục đọc item. Đây là lỗi hợp đồng/định dạng file ở giai đoạn khởi tạo reader, không phải một item đã được đọc rồi bị skip. Hãy tạo failure message đủ rõ để người vận hành xác định file và header lỗi.

## 6. Callback không thay thế LineMapper

`LineCallbackHandler` và `LineMapper` đều làm việc với dòng text, nhưng có vai trò khác nhau:

| Thành phần | Khi nào được dùng | Đầu vào | Kết quả |
|---|---|---|---|
| `LineCallbackHandler` | Với các dòng đầu file được cấu hình bỏ qua | Một `String` | `void`; có thể log hoặc lưu metadata. |
| `LineMapper<T>` | Với dòng dữ liệu reader thực sự đọc thành item | Dòng text và line number | Trả về object `T`. |
| `FieldSetMapper<T>` | Bên trong mapping khi dùng tokenization | `FieldSet` đã tách cột | Trả về object `T`. |
| `ItemReadListener<T>` | Quanh thao tác đọc item | Item hoặc exception | Callback quan sát read lifecycle. |

Ví dụ `LineMapper` xử lý dòng dữ liệu:

```java
public class OrderLineMapper implements LineMapper<OrderInput> {

    @Override
    public OrderInput mapLine(String line, int lineNumber) {
        String[] fields = line.split(",", -1);
        if (fields.length != 3) {
            throw new IllegalArgumentException(
                    "Invalid order row at line " + lineNumber);
        }

        return new OrderInput(
                fields[0].trim(),
                fields[1].trim(),
                new BigDecimal(fields[2].trim()));
    }
}
```

`LineMapper` xử lý từng dòng dữ liệu để tạo item. Callback header không tạo `OrderInput`, không thay đổi nội dung dòng tiếp theo và không tham gia mapping các record thông thường.

## 7. Callback không phải SkipListener

Tên “skipped line” dễ gây nhầm với skip trong fault tolerance. Hai khái niệm này khác nhau:

- `LineCallbackHandler` xử lý các dòng ở đầu file mà ứng dụng chủ động cấu hình bỏ qua bằng `linesToSkip`.
- `SkipListener` được gọi khi một item bị bỏ qua vì exception được cho phép bởi skip policy trong chunk Step.

Ví dụ:

| Tình huống | Cơ chế |
|---|---|
| Bỏ qua dòng tên cột ở đầu CSV | `linesToSkip` + `LineCallbackHandler`. |
| Bỏ qua dòng metadata export ở đầu file | `linesToSkip` + `LineCallbackHandler`. |
| Dòng dữ liệu thứ 50 không parse được và được phép skip | `.skip(...)` + `SkipListener.onSkipInRead(...)` nếu reader phát sinh exception tương ứng. |
| Processor ném `InvalidOrderException` và item được skip | `SkipListener.onSkipInProcess(...)`. |
| Writer không ghi được một item và item được skip | `SkipListener.onSkipInWrite(...)`. |

`LineCallbackHandler` không tiêu thụ `skipLimit`, không tăng `readSkipCount` và không đại diện cho một lỗi item. Các dòng header được bỏ qua theo cấu hình không phải là item bị skip do exception.

## 8. Callback không thay thế ItemReadListener

`ItemReadListener` quan sát vòng đời đọc item, ví dụ trước khi đọc, sau khi đọc thành công hoặc khi reader ném exception. `LineCallbackHandler` chỉ xử lý dòng đầu file được cấu hình bỏ qua.

| Callback | Mục đích |
|---|---|
| `LineCallbackHandler.handleLine(line)` | Đọc/kiểm tra dòng header bị bỏ qua. |
| `ItemReadListener.beforeRead()` | Quan sát trước khi đọc item. |
| `ItemReadListener.afterRead(item)` | Quan sát item đã được đọc thành công. |
| `ItemReadListener.onReadError(exception)` | Quan sát lỗi trong thao tác đọc item. |

Nếu cần metric số item đã đọc, dùng `ItemReadListener` hoặc StepExecution counters. Không dùng callback header để đếm record dữ liệu.

## 9. Callback được gọi khi nào?

Trong vòng đời `FlatFileItemReader`, reader mở resource rồi xử lý số dòng đầu được cấu hình bỏ qua. Với mỗi dòng trong nhóm này, nếu callback đã được đăng ký thì `handleLine` được gọi. Sau đó reader mới chuyển sang đọc các record còn lại qua `LineMapper`.

Các điểm cần nhớ:

- `linesToSkip(0)` là mặc định nếu không cấu hình; không có dòng header nào được xử lý qua callback.
- `linesToSkip(1)` bỏ qua dòng đầu; `linesToSkip(3)` bỏ qua ba dòng đầu.
- Callback chỉ được gọi nếu có cấu hình callback và reader thực sự đọc được các dòng tương ứng.
- Nếu resource không tồn tại và reader được cấu hình strict, reader thất bại khi mở resource; callback không thể xử lý một dòng không đọc được.
- Callback nhận nội dung dòng, không nhận line number hoặc resource path.
- Callback được gọi trong quá trình mở reader, trước khi reader trả các item dữ liệu.

Nếu cần ghi nhận số thứ tự của header line, có thể dùng counter trong collaborator StepScope và tăng sau mỗi callback. Nếu cần xác định tên file khi dùng nhiều resource, hãy truyền thông tin resource qua một collaborator phù hợp hoặc dùng reader wrapper; callback chỉ nhận chuỗi dòng nên không tự cung cấp tên file.

## 10. Restart và tính idempotent của callback

`FlatFileItemReader` là reader có state. Khi Step restart, reader mở resource lại, khôi phục checkpoint và tiếp tục từ vị trí đã lưu. Các dòng được cấu hình `linesToSkip` được xử lý ở giai đoạn mở reader; vì vậy callback header có thể được gọi lại khi reader mở lại ở lần restart hoặc khi resource được mở lại.

Điều này có một hệ quả quan trọng: không nên coi callback là sự kiện “chỉ xảy ra một lần cho cả JobInstance”. Thiết kế callback sao cho có thể gọi nhiều lần mà không tạo side effect trùng.

Các hành động thường an toàn:

- Ghi log có thông tin JobExecution/StepExecution.
- Parse header vào object StepScope mới của lần mở reader.
- Kiểm tra phiên bản file và từ chối header không hợp lệ.
- Ghi nhận metric về định dạng file nếu metric được thiết kế chịu được callback lặp.

Các hành động cần thận trọng:

- Gửi email hoặc message mỗi khi callback chạy.
- Tạo một bản ghi nghiệp vụ mới mà không có unique key.
- Tăng bộ đếm bên ngoài mà không có deduplication.
- Di chuyển hoặc xóa file input ngay trong callback.

Nếu cần lưu metadata header bền vững, dùng key ổn định theo JobInstance/Step và thao tác upsert hoặc kiểm tra dữ liệu đã tồn tại. Nếu cần chia sẻ header với Step sau, đưa giá trị cần thiết vào ExecutionContext bằng một listener hoặc thành phần điều phối phù hợp thay vì dựa vào object trong bộ nhớ sau khi scope kết thúc.

## 11. Nhiều file với MultiResourceItemReader

Khi dùng `MultiResourceItemReader` để đọc nhiều file, reader delegate thường được mở cho từng resource. Nếu delegate là `FlatFileItemReader` có `linesToSkip` và `skippedLinesCallback`, header callback có thể chạy cho mỗi file được mở.

Ví dụ cấu hình khái niệm:

```java
@Bean
@StepScope
MultiResourceItemReader<OrderInput> multiFileReader(
        @Value("#{jobParameters['input.pattern']}") Resource[] resources,
        FlatFileItemReader<OrderInput> orderFileDelegate) {

    return new MultiResourceItemReaderBuilder<OrderInput>()
            .name("multiFileReader")
            .resources(resources)
            .delegate(orderFileDelegate)
            .saveState(true)
            .build();
}
```

Trong trường hợp nhiều file, mỗi file có thể có header riêng hoặc format khác nhau. Nếu callback chỉ ghi log, cần thêm ngữ cảnh tên file ở tầng phù hợp. Nếu callback trích xuất metadata, phải quyết định metadata nào áp dụng cho từng file và metadata nào áp dụng cho toàn Job.

Không giả định header của file đầu tiên đại diện cho mọi file. Có thể cần xác thực schema/version cho từng resource trước khi xử lý item của file đó.

## 12. Xử lý dòng header không hợp lệ

Callback có thể kiểm tra:

- Số lượng cột.
- Tên cột và thứ tự cột.
- Encoding hoặc ký tự BOM nếu hệ thống nguồn có quy ước.
- Phiên bản định dạng file.
- Business date hoặc tenant ID trong metadata.
- File có thuộc đúng JobParameters hay không.

Ví dụ kiểm tra header cột:

```java
private static final List<String> EXPECTED_COLUMNS = List.of(
        "orderId", "customerId", "amount");

private void validateHeader(String line) {
    List<String> actual = Arrays.stream(line.split(",", -1))
            .map(String::trim)
            .toList();

    if (!EXPECTED_COLUMNS.equals(actual)) {
        throw new IllegalArgumentException(
                "Unsupported input header: " + line);
    }
}
```

Nếu file có BOM ở đầu UTF-8, ký tự BOM có thể xuất hiện trước tên cột đầu tiên tùy cách reader/encoding xử lý. Khi gặp trường hợp này, cần chuẩn hóa BOM có chủ đích trước khi so sánh header. Không nên xóa mọi ký tự điều khiển hoặc trim dữ liệu tùy tiện vì có thể che giấu lỗi format.

Nếu header không hợp lệ, thường nên fail Step/Job sớm thay vì coi header như một item có thể skip. Header xác định cách diễn giải toàn bộ file; bỏ qua header sai có thể làm mọi record sau đó bị parse theo schema không đúng.

## 13. Encoding và nội dung dòng

`LineCallbackHandler` nhận chuỗi đã được reader đọc và giải mã theo encoding cấu hình. Nếu file dùng UTF-8, hãy cấu hình encoding rõ ràng để tránh đọc sai tên cột hoặc metadata có dấu:

```java
return new FlatFileItemReaderBuilder<OrderInput>()
        .name("orderReader")
        .resource(new FileSystemResource(inputFile))
        .encoding(StandardCharsets.UTF_8.name())
        .linesToSkip(1)
        .skippedLinesCallback(this::validateHeader)
        .delimited()
        .names("orderId", "customerId", "amount")
        .targetType(OrderInput.class)
        .build();
```

Encoding phải khớp với file nguồn. Nếu file thực tế là Windows-1258, UTF-16 hoặc một encoding khác, cấu hình UTF-8 có thể tạo ký tự sai và làm callback xác thực header thất bại.

Callback nhận nội dung dòng, không phải raw byte. Nếu cần kiểm tra byte-level signature hoặc checksum toàn file, thực hiện ở bước kiểm tra resource trước khi mở reader.

## 14. XML configuration

Với cấu hình XML, `FlatFileItemReader` có thể nhận `linesToSkip` và bean `LineCallbackHandler` qua property:

```xml
<bean id="headerCallback"
      class="com.example.batch.HeaderLineCallback"/>

<bean id="orderReader"
      class="org.springframework.batch.item.file.FlatFileItemReader">
    <property name="resource" value="file:/data/orders.csv"/>
    <property name="linesToSkip" value="1"/>
    <property name="skippedLinesCallback" ref="headerCallback"/>
    <property name="lineMapper" ref="orderLineMapper"/>
</bean>
```

Class callback:

```java
public class HeaderLineCallback implements LineCallbackHandler {

    @Override
    public void handleLine(String line) {
        if (!line.equals("orderId,customerId,amount")) {
            throw new IllegalArgumentException("Unexpected header: " + line);
        }
    }
}
```

Ví dụ XML minh họa cách wiring property. Trong ứng dụng thực tế, resource thường được inject bằng placeholder/configuration hoặc JobParameters thông qua scope phù hợp; không nên hardcode đường dẫn môi trường trong cấu hình triển khai.

## 15. Kiểm thử LineCallbackHandler

Có thể kiểm thử reader độc lập với một resource nhỏ trong bộ nhớ. Test nên xác nhận callback nhận đúng dòng header và reader chỉ trả về dòng dữ liệu.

```java
@Test
void callbackReceivesSkippedHeaderAndReaderReturnsDataLines() throws Exception {
    List<String> headers = new ArrayList<>();

    String content = "orderId,amount\n1001,250000\n1002,175000\n";
    Resource resource = new ByteArrayResource(
            content.getBytes(StandardCharsets.UTF_8));

    FlatFileItemReader<String> reader =
            new FlatFileItemReaderBuilder<String>()
                    .name("testReader")
                    .resource(resource)
                    .linesToSkip(1)
                    .skippedLinesCallback(headers::add)
                    .lineMapper((line, lineNumber) -> line)
                    .build();

    reader.open(new ExecutionContext());
    try {
        assertThat(reader.read()).isEqualTo("1001,250000");
        assertThat(reader.read()).isEqualTo("1002,175000");
        assertThat(reader.read()).isNull();
    } finally {
        reader.close();
    }

    assertThat(headers).containsExactly("orderId,amount");
}
```

Các import chính gồm `FlatFileItemReader`, `FlatFileItemReaderBuilder`, `LineCallbackHandler`, `ExecutionContext`, `ByteArrayResource`, `Resource`, `StandardCharsets` và các assertion của thư viện test. Tùy phiên bản và cách khởi tạo reader, có thể cần gọi `afterPropertiesSet()` trước `open()` khi cấu hình reader thủ công ngoài Spring container.

### Những trường hợp nên kiểm thử

- `linesToSkip(0)`: callback không được gọi.
- `linesToSkip(1)`: callback nhận đúng dòng đầu.
- `linesToSkip(2)`: callback nhận đúng hai dòng theo thứ tự.
- Header sai định dạng: callback báo lỗi và reader không tiếp tục trả item.
- Resource rỗng hoặc thiếu dòng header: xác nhận hành vi theo strict/resource policy của reader.
- Restart/reopen: callback có thể được gọi lại; không tạo side effect trùng.
- Multi-resource: xác nhận callback chạy cho từng file và metadata không bị lẫn.
- Encoding: header có dấu hoặc BOM được xử lý đúng theo định dạng nguồn.

## 16. Những lỗi thường gặp

### Cấu hình callback nhưng quên linesToSkip

Callback chỉ được dùng cho các dòng mà reader được cấu hình bỏ qua. Nếu `linesToSkip` là 0, callback không nhận header. Hãy cấu hình số dòng phù hợp với hợp đồng file.

### Nghĩ callback xử lý mọi dòng bị lỗi

Callback không xử lý dòng dữ liệu parse lỗi ở giữa file. Dùng `LineMapper`, exception classification và skip policy cho những trường hợp đó.

### Dùng callback để tạo item

`handleLine` trả về `void`. Nếu cần chuyển header thành một item hoặc dữ liệu đầu vào riêng, hãy dùng một reader/Tasklet chuyên biệt hoặc lưu metadata vào collaborator phù hợp.

### Nhầm với SkipListener

Header bị bỏ qua theo cấu hình không tiêu thụ skip limit. SkipListener xử lý item bị skip vì exception theo fault tolerance.

### Gửi side effect trong callback

Callback có thể chạy lại khi reader mở lại sau restart. Không gửi email, message hoặc tạo record nghiệp vụ không idempotent trong callback.

### Lưu metadata chỉ trong field singleton

Nhiều Step hoặc Job có thể dùng chung singleton, làm lẫn header giữa các execution. Dùng collaborator `@StepScope` hoặc lưu giá trị cần restart vào ExecutionContext.

### Cho rằng callback chạy đúng một lần

Reader có thể mở lại khi restart; callback xử lý dòng header có thể chạy lại. Thiết kế callback idempotent.

### Xóa hoặc di chuyển file trong callback

Reader vẫn cần file để đọc phần dữ liệu còn lại. Chỉ quản lý vòng đời file ở bước phù hợp sau khi resource không còn được sử dụng.

### Bỏ qua header không hợp lệ

Header xác định schema của cả file. Nếu header không đúng, thường nên fail sớm thay vì tiếp tục parse theo mapping sai.

## 17. Quy trình sử dụng LineCallbackHandler

Khi xử lý file có header hoặc metadata ở đầu, có thể thực hiện theo trình tự:

1. Xác định chính xác số dòng đầu file cần bỏ qua.
2. Xác định callback cần log, validate hay trích xuất metadata.
3. Cấu hình encoding và `linesToSkip` cho `FlatFileItemReader`.
4. Đăng ký callback bằng `.skippedLinesCallback(...)`.
5. Dùng `@StepScope` cho collaborator có state theo từng lần thực thi.
6. Dùng `LineMapper`/`FieldSetMapper` để chuyển các dòng dữ liệu còn lại thành item.
7. Fail sớm nếu header vi phạm hợp đồng định dạng.
8. Giữ callback nhanh, đồng bộ và không tạo side effect khó lặp.
9. Kiểm tra callback có thể chạy lại khi reader reopen/restart.
10. Nếu cần metadata qua Step hoặc restart, lưu vào ExecutionContext hoặc storage bền vững.
11. Kiểm thử nhiều dòng header, file rỗng, encoding, restart và nhiều resource.

| Nhu cầu | Cơ chế phù hợp |
|---|---|
| Bỏ qua một dòng tên cột | `linesToSkip(1)` |
| Ghi log các dòng header bị bỏ qua | `skippedLinesCallback(line -> ...)` |
| Xác thực tên/thứ tự cột | `LineCallbackHandler` |
| Lưu metadata header theo Step | Callback + collaborator `@StepScope` |
| Chuyển dòng dữ liệu thành object | `LineMapper`/`FieldSetMapper` |
| Xử lý dòng dữ liệu lỗi ở giữa file | Exception policy và `SkipListener` nếu được skip |
| Quan sát item đọc thành công/thất bại | `ItemReadListener` |

## Kết luận

`LineCallbackHandler` là callback của `FlatFileItemReader` dùng để xử lý từng dòng đầu file được bỏ qua qua `linesToSkip`. Nó phù hợp để ghi log, xác thực header hoặc trích xuất metadata trước khi các dòng dữ liệu được chuyển qua `LineMapper`. Callback nhận một chuỗi và trả về `void`; nó không tạo item, không thay thế `ItemReadListener` và không phải `SkipListener` của fault tolerance. Hãy dùng scope phù hợp cho state theo Step, giữ callback nhanh và idempotent vì nó có thể được gọi lại khi reader mở lại sau restart, đồng thời lưu metadata cần khôi phục vào `ExecutionContext` hoặc storage bền vững.
