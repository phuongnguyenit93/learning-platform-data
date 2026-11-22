# Mapping input model sang output model

Trong Spring Batch, `ItemProcessor` thường được dùng để chuyển một item vừa đọc thành một item có cấu trúc phù hợp với bước ghi dữ liệu. Đây là nơi ứng dụng có thể **mapping input model sang output model**: nhận dữ liệu theo định dạng của nguồn, kiểm tra và chuẩn hóa nó, rồi tạo ra một mô hình đầu ra phù hợp với nghiệp vụ hoặc hệ thống đích.

Ví dụ, một tệp CSV chứa `customer_code`, `first_name`, `last_name`, `birth_date` và `status`. Reader ánh xạ mỗi dòng thành `CustomerInput`. Processor chuyển đổi thành `CustomerRecord` với tên đầy đủ, ngày sinh kiểu `LocalDate`, trạng thái enum và các trường chuẩn hóa. Writer sau đó ghi `CustomerRecord` vào database.

Mapping không chỉ là sao chép tên trường. Nó còn phải xác định quy tắc chuyển đổi kiểu, xử lý giá trị thiếu, chuẩn hóa dữ liệu, kiểm tra điều kiện nghiệp vụ và quyết định item nào được chuyển tiếp.

## 1. Input model và output model có vai trò khác nhau

Hai mô hình đại diện cho hai ranh giới khác nhau trong pipeline:

- **Input model** mô tả dữ liệu reader nhận từ nguồn. Cấu trúc thường phụ thuộc CSV, JSON, XML, database hoặc API.
- **Output model** mô tả dữ liệu processor cung cấp cho writer. Cấu trúc thường phụ thuộc quy tắc nghiệp vụ hoặc schema của hệ thống đích.

Ví dụ:

| Input model (`CustomerInput`) | Output model (`CustomerRecord`) |
|---|---|
| `customer_code: String` | `customerId: Long` |
| `first_name: String` | `fullName: String` |
| `last_name: String` | `fullName: String` |
| `birth_date: String` | `birthDate: LocalDate` |
| `status: String` | `status: CustomerStatus` |
| `country_code: String` | `country: Country` hoặc mã quốc gia chuẩn hóa |

Input model có thể chứa dữ liệu thô như chuỗi ngày tháng hoặc mã trạng thái. Output model nên thể hiện dữ liệu đã được chuyển đổi theo kiểu và quy tắc mà hệ thống đích mong đợi.

Giữ hai mô hình riêng giúp ứng dụng tránh phụ thuộc trực tiếp vào cấu trúc của tệp đầu vào. Nếu đối tác thay đổi tên cột hoặc định dạng ngày, có thể điều chỉnh reader hoặc mapping mà không nhất thiết phải thay đổi toàn bộ mô hình nghiệp vụ và writer.

## 2. ItemProcessor là vị trí tự nhiên để mapping

Spring Batch định nghĩa `ItemProcessor<I, O>` với kiểu đầu vào `I` và kiểu đầu ra `O`:

```java
public interface ItemProcessor<I, O> {
    O process(I item) throws Exception;
}
```

Hai tham số kiểu có thể khác nhau. Ví dụ:

```java
ItemProcessor<CustomerInput, CustomerRecord> processor;
```

Điều này có nghĩa reader cung cấp `CustomerInput`, processor tạo `CustomerRecord`, và writer nhận các `CustomerRecord`.

Luồng dữ liệu:

```mermaid
flowchart LR
    A[CSV / JSON / Database] --> B[ItemReader]
    B --> C[CustomerInput]
    C --> D[ItemProcessor]
    D --> E[Validate and map]
    E --> F[CustomerRecord]
    F --> G[ItemWriter]
    G --> H[Database / Output file]
```

Processor được gọi cho từng item. Nó có thể trả về output đã mapping, trả về `null` để lọc item, hoặc ném exception để báo lỗi. Quyết định nào được dùng cần phản ánh đúng ý nghĩa nghiệp vụ.

## 3. Ví dụ input model và output model

Có thể dùng Java record để biểu diễn các mô hình dữ liệu bất biến nếu phiên bản Java của ứng dụng hỗ trợ:

```java
public record CustomerInput(
        String customerCode,
        String firstName,
        String lastName,
        String birthDate,
        String status,
        String countryCode) {
}

public record CustomerRecord(
        Long customerId,
        String fullName,
        LocalDate birthDate,
        CustomerStatus status,
        String countryCode) {
}

public enum CustomerStatus {
    ACTIVE,
    INACTIVE,
    SUSPENDED
}
```

`CustomerInput` giữ dữ liệu gần với định dạng nguồn. `CustomerRecord` dùng kiểu cụ thể hơn để biểu diễn dữ liệu sau khi chuyển đổi. Nếu dự án dùng Java phiên bản cũ, có thể thay record bằng class có constructor, getter và các phương thức cần thiết.

## 4. Mapping thủ công trong ItemProcessor

Với mapping đơn giản, có thể viết trực tiếp trong processor. Cách này dễ đọc và phù hợp khi quy tắc chuyển đổi ít trường.

```java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

import org.springframework.batch.item.ItemProcessor;
import org.springframework.stereotype.Component;

@Component
public class CustomerProcessor
        implements ItemProcessor<CustomerInput, CustomerRecord> {

    private static final DateTimeFormatter DATE_FORMAT =
            DateTimeFormatter.ofPattern("dd/MM/uuuu", Locale.ROOT);

    @Override
    public CustomerRecord process(CustomerInput input) {
        if (input == null) {
            throw new IllegalArgumentException("Customer input is required");
        }

        String customerCode = requireText(input.customerCode(), "customerCode");
        Long customerId = Long.valueOf(customerCode);

        String fullName = normalizeName(input.firstName(), input.lastName());
        LocalDate birthDate = LocalDate.parse(input.birthDate(), DATE_FORMAT);
        CustomerStatus status = CustomerStatus.valueOf(
                input.status().trim().toUpperCase(Locale.ROOT));

        return new CustomerRecord(
                customerId,
                fullName,
                birthDate,
                status,
                normalizeCountryCode(input.countryCode())
        );
    }

    private String requireText(String value, String fieldName) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(fieldName + " is required");
        }
        return value.trim();
    }

    private String normalizeName(String firstName, String lastName) {
        String first = firstName == null ? "" : firstName.trim();
        String last = lastName == null ? "" : lastName.trim();
        return (first + " " + last).trim().replaceAll("\\s+", " ");
    }

    private String normalizeCountryCode(String countryCode) {
        return countryCode == null
                ? null
                : countryCode.trim().toUpperCase(Locale.ROOT);
    }
}
```

Đoạn mã minh họa cách chuyển chuỗi sang số, ghép tên, parse ngày và chuyển trạng thái sang enum. Trong ứng dụng thật, cần xác định rõ định dạng dữ liệu đầu vào và các quy tắc nghiệp vụ. Ví dụ, chỉ chuyển `customerCode` thành `Long` nếu mã khách hàng thực sự là số và không cần giữ số 0 ở đầu.

Mapping thủ công có ưu điểm là kiểm soát rõ ràng, không cần thêm thư viện. Tuy nhiên, nếu model có nhiều trường lồng nhau hoặc nhiều mapping dùng chung, processor có thể trở nên dài và khó bảo trì. Khi đó nên tách mapping sang một mapper riêng.

## 5. Tách mapping thành mapper riêng

Processor nên điều phối các bước xử lý của một item. Logic chuyển đổi có thể được tách thành một thành phần mapper để dễ kiểm thử và tái sử dụng.

```java
public interface CustomerMapper {
    CustomerRecord toRecord(CustomerInput input);
}
```

Triển khai thủ công:

```java
@Component
public class DefaultCustomerMapper implements CustomerMapper {

    @Override
    public CustomerRecord toRecord(CustomerInput input) {
        Long customerId = Long.valueOf(input.customerCode().trim());
        String fullName = (input.firstName() + " " + input.lastName()).trim();
        LocalDate birthDate = LocalDate.parse(input.birthDate());
        CustomerStatus status = CustomerStatus.valueOf(
                input.status().trim().toUpperCase(Locale.ROOT));

        return new CustomerRecord(
                customerId,
                fullName,
                birthDate,
                status,
                input.countryCode());
    }
}
```

Processor sử dụng mapper:

```java
@Component
public class CustomerProcessor
        implements ItemProcessor<CustomerInput, CustomerRecord> {

    private final CustomerMapper mapper;

    public CustomerProcessor(CustomerMapper mapper) {
        this.mapper = mapper;
    }

    @Override
    public CustomerRecord process(CustomerInput input) {
        validate(input);
        return mapper.toRecord(input);
    }

    private void validate(CustomerInput input) {
        if (input == null || input.customerCode() == null
                || input.customerCode().isBlank()) {
            throw new IllegalArgumentException("Missing customer code");
        }
    }
}
```

Trong cấu trúc này, processor quyết định luồng xử lý và gọi mapper để chuyển đổi. Mapper tập trung vào việc tạo output model. Có thể thay implementation mapper mà không phải viết lại toàn bộ processor.

## 6. Dùng MapStruct cho mapping nhiều trường

Với model lớn hoặc nhiều mapping lặp lại, có thể dùng thư viện mapping như MapStruct. MapStruct tạo mã mapping tại thời điểm compile, giúp tránh phải viết nhiều câu lệnh gán thủ công.

Ví dụ:

```java
import org.mapstruct.Mapper;
import org.mapstruct.Mapping;

@Mapper(componentModel = "spring")
public interface CustomerMapStructMapper {

    @Mapping(target = "customerId", source = "customerCode")
    @Mapping(target = "fullName", expression = "java(joinName(input))")
    @Mapping(target = "birthDate", source = "birthDate", dateFormat = "dd/MM/yyyy")
    @Mapping(target = "status", source = "status")
    @Mapping(target = "countryCode", source = "countryCode")
    CustomerRecord toRecord(CustomerInput input);

    default String joinName(CustomerInput input) {
        String first = input.firstName() == null ? "" : input.firstName().trim();
        String last = input.lastName() == null ? "" : input.lastName().trim();
        return (first + " " + last).trim().replaceAll("\\s+", " ");
    }
}
```

Ví dụ trên minh họa cách khai báo mapping. Khi dùng MapStruct với enum, kiểu số, ngày tháng hoặc record, cần cấu hình conversion phù hợp với model và phiên bản thư viện. Nếu có quy tắc nghiệp vụ phức tạp, nên đặt quy tắc đó trong phương thức riêng thay vì cố nhồi vào annotation.

Ưu điểm của MapStruct:

- Mã mapping được sinh tại compile time.
- Phát hiện nhiều trường hợp không khớp kiểu ngay khi build.
- Hỗ trợ mapping nested object, collection và tên trường khác nhau.
- Giảm lượng mã gán lặp lại trong ứng dụng có nhiều model.

Đánh đổi là dự án cần cấu hình annotation processor và quản lý thêm dependency. Với mapping nhỏ, viết mapper thủ công có thể đơn giản hơn.

## 7. Mapping kiểu dữ liệu và chuẩn hóa giá trị

Phần khó của mapping thường nằm ở việc chuyển đổi dữ liệu thô sang kiểu đích đúng và nhất quán.

### String sang số

Nếu input chứa số dưới dạng chuỗi, cần kiểm tra định dạng trước khi parse. Ví dụ, `"00125"` có thể là mã định danh cần giữ nguyên, trong khi `"125"` có thể là số lượng cần tính toán.

Không nên parse tất cả trường số thành `Long` hoặc `Double` theo thói quen. Hãy xác định ý nghĩa của trường trước khi chọn kiểu.

### String sang ngày tháng

Ngày đầu vào cần có định dạng rõ ràng. `15/11/2026` và `11/15/2026` có thể được hiểu khác nhau. Dùng `DateTimeFormatter` với pattern và locale xác định, tránh phụ thuộc locale mặc định của JVM.

Nếu output model lưu ngày lịch, `LocalDate` thường phù hợp hơn `Date`. Nếu dữ liệu biểu diễn một thời điểm, cần parse offset hoặc timezone theo hợp đồng dữ liệu.

### String sang enum

Giá trị trạng thái nên được chuẩn hóa trước khi gọi `Enum.valueOf`, ví dụ trim và chuyển về chữ hoa theo `Locale.ROOT`. Cần quy định cách xử lý giá trị không nhận diện được: lỗi dữ liệu, trạng thái mặc định hay bản ghi cần cách ly.

### Số thập phân và tiền tệ

Không dùng `Double` cho phép tính tiền cần độ chính xác thập phân. Dùng `BigDecimal`, xác định scale và rounding mode theo quy tắc nghiệp vụ. Nếu input dùng dấu phẩy làm dấu thập phân, cần parse theo locale hoặc định dạng được quy định, không thay thế ký tự một cách tùy tiện.

### Null và giá trị mặc định

Không nên tự động đổi mọi `null` thành chuỗi rỗng hoặc số 0. `null`, chuỗi rỗng và giá trị 0 có thể mang ý nghĩa khác nhau. Output model cần thể hiện rõ trường nào bắt buộc, trường nào có thể vắng mặt và trường nào có giá trị mặc định được nghiệp vụ cho phép.

## 8. Validation trước và trong khi mapping

Mapping thường đi cùng validation, nhưng hai việc có mục tiêu khác nhau:

- **Validation** xác định input có thỏa điều kiện cần thiết hay không.
- **Mapping** chuyển input hợp lệ thành output model.

Ví dụ, `customerCode` phải có giá trị, `birthDate` phải đúng định dạng, `status` phải thuộc danh sách cho phép và `countryCode` phải theo chuẩn mà hệ thống đích chấp nhận.

Có thể dùng Bean Validation (`jakarta.validation`) trên input model hoặc viết validator riêng. Nếu validation thất bại, ứng dụng cần quyết định:

1. Ném exception để step thất bại.
2. Cấu hình exception đó là skippable để bỏ qua item và tiếp tục.
3. Tạo một output/rejection record riêng để ghi nhận dữ liệu lỗi theo một luồng được thiết kế rõ ràng.

Không nên trả về `null` chỉ vì dữ liệu không hợp lệ. Trong Spring Batch, processor trả về `null` có nghĩa là **filter item**, không phải báo lỗi. Nếu muốn bỏ qua do exception, hãy dùng chính sách skip; nếu muốn lưu lỗi, hãy xây dựng cơ chế ghi nhận lỗi riêng.

## 9. Filter item trong lúc mapping

`ItemProcessor` có thể trả về `null` khi input hợp lệ nhưng không thuộc phạm vi cần xử lý.

Ví dụ, job chỉ xuất các khách hàng đang hoạt động:

```java
@Override
public CustomerRecord process(CustomerInput input) {
    if ("INACTIVE".equalsIgnoreCase(input.status())) {
        return null;
    }

    return mapper.toRecord(input);
}
```

Item bị filter:

- Đã được reader đọc.
- Không được chuyển tới writer.
- Được phản ánh trong `filterCount` của `StepExecution`.
- Không làm tăng skip count chỉ vì processor trả về `null`.

Nếu lý do loại item cần được kiểm toán, hãy ghi nhận mã định danh và lý do filter qua cơ chế logging hoặc audit phù hợp. Không nên dùng exception cho một điều kiện loại dữ liệu bình thường nếu không cần thiết.

## 10. Cấu hình processor với chunk-oriented step

Trong Spring Batch 5, step có thể khai báo input và output type rõ ràng:

```java
@Bean
public Step importCustomersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<CustomerInput> customerReader,
        ItemProcessor<CustomerInput, CustomerRecord> customerProcessor,
        ItemWriter<CustomerRecord> customerWriter) {

    return new StepBuilder("importCustomersStep", jobRepository)
            .<CustomerInput, CustomerRecord>chunk(500, transactionManager)
            .reader(customerReader)
            .processor(customerProcessor)
            .writer(customerWriter)
            .build();
}
```

Kiểu generic tại `.<CustomerInput, CustomerRecord>chunk(...)` xác định kiểu đầu vào của reader và kiểu đầu ra của processor/writer. Nếu reader, processor hoặc writer không khớp kiểu, lỗi thường được phát hiện ngay khi biên dịch hoặc khi cấu hình bean.

Không cần processor nếu dữ liệu đầu vào đã có đúng kiểu và cấu trúc mà writer cần. Tuy nhiên, nếu cần mapping, validation hoặc enrichment, processor là vị trí phù hợp để thực hiện trước khi ghi.

## 11. Mapping theo nhiều bước với CompositeItemProcessor

Khi xử lý có nhiều giai đoạn, có thể tách thành các processor nhỏ rồi nối chúng bằng `CompositeItemProcessor`.

Ví dụ pipeline:

1. Chuẩn hóa chuỗi và mã đầu vào.
2. Kiểm tra quy tắc nghiệp vụ.
3. Mapping sang output model.
4. Làm giàu output bằng dữ liệu tham chiếu.

Các processor nối tiếp cần có kiểu đầu ra của bước trước khớp kiểu đầu vào của bước sau.

```java
ItemProcessor<CustomerInput, CustomerInput> normalizer;
ItemProcessor<CustomerInput, CustomerInput> validator;
ItemProcessor<CustomerInput, CustomerRecord> mapper;

CompositeItemProcessor<CustomerInput, CustomerRecord> processor =
        new CompositeItemProcessor<>();
processor.setDelegates(List.of(normalizer, validator, mapper));
```

Đây là ví dụ về quan hệ kiểu giữa các delegate. Trong cấu hình Spring thực tế, nên khai báo composite processor như bean và cấu hình danh sách delegate theo phiên bản Spring Batch đang dùng.

Tách processor giúp mỗi thành phần có trách nhiệm nhỏ và dễ kiểm thử. Tuy nhiên, không nên chia thành quá nhiều lớp chỉ để biến mỗi phép gán trường thành một component riêng. Hãy tách theo ranh giới xử lý có ý nghĩa.

## 12. Enrichment khác mapping như thế nào?

Mapping chuyển đổi cấu trúc hoặc kiểu dữ liệu từ input sang output. Enrichment bổ sung dữ liệu từ một nguồn khác để output đầy đủ hơn.

Ví dụ:

- Input có `productCode`; processor tra cứu tên và nhóm sản phẩm từ bảng tham chiếu.
- Input có `branchId`; processor bổ sung thông tin khu vực của chi nhánh.
- Input có `countryCode`; processor chuyển mã sang tên quốc gia chuẩn.

Enrichment có thể cần gọi database hoặc service. Cần chú ý tránh N+1 query: nếu mỗi item tạo một truy vấn riêng, job có thể chậm khi dữ liệu lớn. Có thể dùng cache có giới hạn, đọc trước dữ liệu tham chiếu theo nhóm, join ngay trong reader hoặc dùng lookup theo batch.

Nếu enrichment phụ thuộc dữ liệu có thể thay đổi trong khi job chạy, cần xác định job dùng snapshot nào. Cùng một input được xử lý lại sau restart không nên bất ngờ nhận một bộ dữ liệu tham chiếu khác nếu điều đó làm thay đổi kết quả nghiệp vụ.

## 13. Giữ processor stateless và an toàn khi chạy song song

Processor thường nên là thành phần stateless: không giữ trạng thái thay đổi theo từng item trong field của singleton bean. Spring có thể tái sử dụng cùng processor cho nhiều item, step execution hoặc luồng xử lý tùy cấu hình.

Nên:

- Dùng biến local cho dữ liệu của item hiện tại.
- Inject mapper hoặc service có hành vi an toàn với cách thực thi đã chọn.
- Tránh giữ `currentCustomer`, bộ đếm mutable hoặc danh sách kết quả chung trong field của processor.
- Nếu cần cache, chọn cache thread-safe, có giới hạn và có chính sách hết hạn phù hợp.
- Không ghi tác dụng phụ không thể lặp lại an toàn trong processor nếu step có thể retry item.

Khi step chạy nhiều luồng, processor có thể được gọi đồng thời. Mapping thuần túy từ input sang output thường dễ làm thread-safe hơn. Nếu processor truy cập tài nguyên ngoài, cần kiểm soát concurrency, timeout và tính idempotent.

## 14. Kiểm thử mapping độc lập với job

Mapper và processor có thể được kiểm thử bằng unit test mà không cần khởi chạy toàn bộ job.

Ví dụ kiểm tra mapper:

```java
@Test
void mapsInputToCustomerRecord() {
    CustomerInput input = new CustomerInput(
            "1205", "An", "Nguyen", "15/11/1995", "active", "vn");

    CustomerRecord result = mapper.toRecord(input);

    assertEquals(1205L, result.customerId());
    assertEquals("An Nguyen", result.fullName());
    assertEquals(LocalDate.of(1995, 11, 15), result.birthDate());
    assertEquals(CustomerStatus.ACTIVE, result.status());
    assertEquals("VN", result.countryCode());
}
```

Những trường hợp nên được kiểm thử:

- Giá trị hợp lệ và mapping bình thường.
- Trường bắt buộc bị thiếu hoặc chỉ chứa khoảng trắng.
- Chuỗi ngày sai định dạng hoặc ngày không tồn tại.
- Enum không được nhận diện.
- Mã số có số 0 ở đầu hoặc vượt phạm vi kiểu số.
- Giá trị thập phân có locale khác nhau.
- Quy tắc filter trả về `null` đúng trường hợp.
- Mapping nested object hoặc collection nếu output có cấu trúc lồng nhau.

Unit test giúp phát hiện lỗi chuyển đổi sớm. Integration test của step vẫn cần thiết khi muốn xác nhận reader, processor, writer và transaction phối hợp đúng, nhưng trách nhiệm kiểm thử đó nằm ngoài logic mapping thuần túy.

## 15. Lỗi thường gặp khi mapping input sang output

| Tình huống | Nguyên nhân | Cách xử lý |
|---|---|---|
| Output thiếu trường | Mapper quên ánh xạ hoặc nguồn không có giá trị | Xác định trường bắt buộc và viết mapping tường minh |
| Parse ngày thất bại | Định dạng input không thống nhất | Dùng formatter rõ ràng và validate trước khi parse |
| Mất số 0 ở đầu mã | Chuyển mã định danh sang kiểu số | Giữ mã dưới dạng `String` |
| Sai số tiền tệ | Dùng `Double` cho phép tính tài chính | Dùng `BigDecimal` với scale và rounding mode rõ ràng |
| Item không đến writer nhưng không có exception | Processor trả về `null` | Kiểm tra quy tắc filter và `filterCount` |
| Job dừng vì một bản ghi sai | Exception không nằm trong skip policy | Quyết định lỗi nào phải fail, lỗi nào có thể skip hoặc cách ly |
| Kết quả khác nhau giữa các lần chạy | Enrichment đọc dữ liệu tham chiếu thay đổi hoặc mapping phụ thuộc môi trường | Chốt snapshot và quy tắc chuẩn hóa |
| Lỗi khi chạy nhiều luồng | Processor hoặc mapper dùng state mutable chung | Thiết kế stateless hoặc đồng bộ tài nguyên phù hợp |
| Mapping quá khó bảo trì | Logic parse, validate, filter và enrichment dồn vào một phương thức | Tách trách nhiệm theo các bước có ý nghĩa |

## 16. Ví dụ end-to-end: chuyển dữ liệu khách hàng

Một tệp CSV có các cột:

```csv
customer_code,first_name,last_name,birth_date,status,country_code
00125,An,Nguyen,15/11/1995,ACTIVE,VN
00126,Binh,Tran,02/03/1990,INACTIVE,VN
00127,Chi,Le,31/02/1998,ACTIVE,VN
```

Reader ánh xạ từng dòng thành `CustomerInput`. Processor thực hiện các việc:

1. Chuẩn hóa khoảng trắng và mã quốc gia.
2. Xác thực trường bắt buộc.
3. Chuyển ngày sinh thành `LocalDate`.
4. Chuyển trạng thái sang enum.
5. Tạo `CustomerRecord` với các trường mà writer cần.
6. Lọc khách hàng `INACTIVE` nếu yêu cầu nghiệp vụ chỉ nhập khách hàng đang hoạt động.

Trong ví dụ, `customer_code` có số 0 ở đầu nên phải giữ dưới dạng `String` nếu số 0 là một phần của mã. Ngày `31/02/1998` không hợp lệ; processor có thể ném exception để step áp dụng skip policy hoặc thất bại theo yêu cầu. Bản ghi `INACTIVE` có thể được filter bằng cách trả về `null`.

Output model có thể là:

```java
public record CustomerRecord(
        String customerCode,
        String fullName,
        LocalDate birthDate,
        CustomerStatus status,
        String countryCode) {
}
```

Writer chỉ nhận những `CustomerRecord` được processor trả về. Nhờ đó, writer không cần hiểu cấu trúc CSV, cách ghép tên hoặc định dạng ngày thô.

## 17. Những nguyên tắc cần nhớ

- Input model biểu diễn dữ liệu reader nhận; output model biểu diễn dữ liệu writer cần.
- `ItemProcessor<I, O>` cho phép input và output có kiểu khác nhau.
- Mapping có thể bao gồm đổi tên trường, đổi kiểu, chuẩn hóa, validate và tạo cấu trúc lồng nhau.
- Tách mapper riêng khi logic chuyển đổi cần tái sử dụng hoặc có nhiều trường.
- Dùng MapStruct hoặc công cụ tương tự khi mapping lớn; viết thủ công khi mapping đơn giản và cần kiểm soát trực tiếp.
- `null` từ processor có nghĩa filter item; lỗi dữ liệu cần exception/skip hoặc luồng ghi nhận riêng.
- Chọn kiểu dữ liệu theo ý nghĩa: giữ mã định danh có số 0 đầu dưới dạng chuỗi, dùng `LocalDate` cho ngày lịch, `BigDecimal` cho tiền tệ.
- Enrichment cần kiểm soát truy vấn, cache, snapshot và khả năng chạy lại.
- Processor nên stateless hoặc thread-safe khi step chạy song song; tránh giữ trạng thái thay đổi theo item trong field dùng chung.
- Kiểm thử mapper và processor độc lập để phát hiện lỗi chuyển đổi trước khi chạy job lớn.

Mapping input model sang output model giúp tách định dạng nguồn khỏi mô hình mà hệ thống đích cần. Khi đặt mapping trong `ItemProcessor`, ứng dụng có một điểm rõ ràng để chuẩn hóa, kiểm tra và chuyển đổi từng item trước khi ghi, đồng thời giữ reader và writer tập trung vào nhiệm vụ đọc và ghi dữ liệu.
