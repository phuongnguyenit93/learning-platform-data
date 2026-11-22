# Parameter validation trong Spring Batch

**JobParameters** là dữ liệu đầu vào được truyền khi khởi chạy một Job. Chúng thường xác định lô cần xử lý, chẳng hạn ngày nghiệp vụ, đường dẫn file, mã khách hàng hoặc phạm vi dữ liệu. Trước khi Job thực hiện các Step, ứng dụng cần xác nhận các tham số này đầy đủ, đúng kiểu, đúng định dạng và phù hợp với quy tắc nghiệp vụ.

Spring Batch cung cấp cơ chế **JobParametersValidator** để kiểm tra tham số ở cấp Job. Validator giúp từ chối một lần chạy ngay khi đầu vào không hợp lệ, trước khi Job đi vào luồng xử lý dữ liệu. Bài học này trình bày cách kiểm tra tham số bắt buộc, tham số tùy chọn, kiểu và giá trị, cách gắn validator vào Job, cũng như cách kiểm thử và xử lý tham số khi restart.

## 1. JobParameters là gì?

JobParameters là tập hợp các cặp tên và giá trị được truyền cho Job khi khởi chạy. Ví dụ, một Job nhập dữ liệu khách hàng có thể nhận:

| Tên tham số | Ví dụ | Mục đích |
|---|---|---|
| **inputFile** | **data/customers.csv** | File cần nhập |
| **businessDate** | **2026-11-15** | Ngày nghiệp vụ của lô |
| **region** | **APAC** | Phạm vi khu vực |
| **maxRows** | **50000** | Giới hạn số dòng xử lý |
| **dryRun** | **true** | Chạy thử theo chế độ không ghi dữ liệu chính thức |

Các tham số này được dùng để cấu hình công việc tại thời điểm chạy. Chúng giúp cùng một Job definition có thể xử lý nhiều file, ngày hoặc phạm vi dữ liệu khác nhau.

JobParameters là dữ liệu đầu vào của Job, không phải dữ liệu của từng item. Ví dụ:

- **businessDate** là tham số của cả lần chạy.
- Mã khách hàng trong mỗi dòng CSV là dữ liệu item.
- Quy tắc kiểm tra **businessDate** thuộc phạm vi JobParameters validation.
- Quy tắc kiểm tra mã khách hàng trên từng dòng thuộc xử lý item, thường nằm trong ItemProcessor hoặc thành phần xác thực dữ liệu.

### JobParameters và JobInstance

Spring Batch dùng tên Job cùng các **identifying JobParameters** để xác định JobInstance. Một JobInstance đại diện cho một lần xử lý logic, ví dụ nhập dữ liệu cho một ngày nghiệp vụ.

Một JobInstance có thể có nhiều JobExecution nếu lần chạy đầu thất bại và sau đó được restart. Các lần restart sử dụng cùng bộ identifying parameters để tiếp tục đúng instance đã có.

~~~mermaid
flowchart TD
    A["Job name + identifying JobParameters"] --> B["JobInstance"]
    B --> C["JobExecution lần 1"]
    B --> D["JobExecution lần restart"]
    B --> E["JobExecution tiếp theo"]
~~~

Điều này có nghĩa là lựa chọn tham số nào mang tính identifying ảnh hưởng trực tiếp đến cách Spring Batch nhận diện lần chạy. Validator kiểm tra tính hợp lệ của giá trị; cờ identifying quyết định giá trị đó tham gia nhận diện JobInstance hay không.

## 2. Vì sao cần kiểm tra JobParameters?

Nếu Job chạy với tham số thiếu hoặc sai, lỗi có thể chỉ xuất hiện khi Step bắt đầu đọc file, truy vấn database hoặc ghi dữ liệu. Khi đó, hệ thống đã tạo metadata và có thể đã thực hiện một phần công việc trước khi phát hiện vấn đề.

Parameter validation giúp phát hiện lỗi đầu vào sớm hơn.

Ví dụ, Job nhập dữ liệu yêu cầu **inputFile** và **businessDate**. Nếu thiếu **inputFile**, reader có thể thất bại khi mở resource. Nếu **businessDate** sai định dạng, processor hoặc câu truy vấn có thể thất bại khi chuyển đổi giá trị.

Một validator ở cấp Job có thể kiểm tra các điều kiện trước khi các Step bắt đầu:

- Tham số bắt buộc phải có.
- Tên tham số phải nằm trong tập cho phép.
- Giá trị không được rỗng hoặc chỉ chứa khoảng trắng.
- Giá trị phải đúng định dạng.
- Giá trị số phải nằm trong giới hạn.
- Ngày bắt đầu không được sau ngày kết thúc.
- Các tham số liên quan phải được cung cấp cùng nhau.
- Chế độ xử lý phải thuộc danh sách được hỗ trợ.

Nhờ đó, lỗi đầu vào được báo bằng một thông điệp rõ ràng và không bị nhầm với lỗi đọc dữ liệu hoặc lỗi hạ tầng.

## 3. Cơ chế JobParametersValidator

Spring Batch định nghĩa giao diện **JobParametersValidator**:

~~~java
public interface JobParametersValidator {
    void validate(JobParameters parameters)
        throws JobParametersInvalidException;
}
~~~

Validator nhận **JobParameters** và kiểm tra toàn bộ tập tham số. Nếu tham số hợp lệ, phương thức kết thúc bình thường. Nếu không hợp lệ, validator ném **JobParametersInvalidException** kèm thông tin giải thích.

Ví dụ một validator đơn giản:

~~~java
public class RequiredInputValidator
        implements JobParametersValidator {

    @Override
    public void validate(JobParameters parameters)
            throws JobParametersInvalidException {

        String inputFile = parameters.getString("inputFile");

        if (inputFile == null || inputFile.isBlank()) {
            throw new JobParametersInvalidException(
                "Tham số inputFile là bắt buộc."
            );
        }
    }
}
~~~

Validator này yêu cầu tham số **inputFile** phải tồn tại và có nội dung. Khi không đáp ứng điều kiện, Job bị từ chối với lỗi tham số không hợp lệ.

### Validator được gọi ở đâu?

Validator được gắn vào Job. Spring Batch thực hiện việc kiểm tra tham số ở cấp Job trước khi luồng Step bắt đầu xử lý. Vì vậy, đây là nơi thích hợp để kiểm tra các điều kiện đầu vào chung cho toàn bộ Job.

~~~mermaid
flowchart TD
    A["Nhận JobParameters"] --> B["JobParametersValidator"]
    B --> C{"Tham số hợp lệ?"}
    C -- "Không" --> D["JobParametersInvalidException"]
    C -- "Có" --> E["Bắt đầu Job flow"]
    E --> F["Step 1"]
    F --> G["Step tiếp theo"]
~~~

Nếu validator ném exception, Job không đi vào các Step theo luồng bình thường. Ứng dụng có thể bắt lỗi ở nơi gọi Job để trả thông báo phù hợp cho người dùng hoặc hệ thống lập lịch.

Validator không tự sửa giá trị, tự thêm tham số còn thiếu hoặc thay đổi JobParameters. Hãy chuẩn hóa và bổ sung giá trị mặc định ở lớp tạo tham số hoặc trước khi gọi Job nếu nghiệp vụ cho phép.

## 4. Kiểm tra tham số bắt buộc và tùy chọn bằng DefaultJobParametersValidator

Với các quy tắc đơn giản về tên tham số, Spring Batch cung cấp **DefaultJobParametersValidator**.

Validator này cho phép khai báo:

- **Required keys:** các tên tham số bắt buộc phải có.
- **Optional keys:** các tên tham số được phép có nhưng không bắt buộc.

Ví dụ, Job cần **inputFile** và **businessDate**, đồng thời cho phép **region** và **maxRows**:

~~~java
@Bean
JobParametersValidator importParametersValidator() {
    return new DefaultJobParametersValidator(
        new String[] {
            "inputFile",
            "businessDate"
        },
        new String[] {
            "region",
            "maxRows"
        }
    );
}
~~~

Gắn validator vào Job:

~~~java
@Bean
Job importCustomersJob(
        JobRepository jobRepository,
        Step importCustomersStep,
        JobParametersValidator importParametersValidator) {

    return new JobBuilder("importCustomersJob", jobRepository)
        .validator(importParametersValidator)
        .start(importCustomersStep)
        .build();
}
~~~

Với cấu hình trên:

| Bộ tham số nhận được | Kết quả |
|---|---|
| **inputFile**, **businessDate** | Hợp lệ về tên và sự hiện diện |
| Có thêm **region** | Được phép |
| Có thêm **maxRows** | Được phép |
| Thiếu **inputFile** | Không hợp lệ |
| Thiếu **businessDate** | Không hợp lệ |
| Có **unexpectedKey** | Không hợp lệ vì không thuộc danh sách cho phép |

**DefaultJobParametersValidator** phù hợp khi cần kiểm tra tập tên tham số và sự hiện diện của chúng. Nó không kiểm tra các quy tắc nghiệp vụ phức tạp như ngày có đúng định dạng hay không, số lượng có lớn hơn không, file có đọc được không hoặc hai ngày có đúng thứ tự hay không.

Nếu Job có cả quy tắc về tên và quy tắc về giá trị, hãy dùng validator tùy chỉnh hoặc kết hợp các kiểm tra trong một lớp validator chuyên biệt.

## 5. Viết custom validator cho quy tắc nghiệp vụ

Một custom validator triển khai **JobParametersValidator** và kiểm tra các giá trị cụ thể. Ví dụ, Job nhập dữ liệu yêu cầu:

- **inputFile:** đường dẫn file đầu vào, không được rỗng.
- **businessDate:** ngày theo định dạng ISO **yyyy-MM-dd**.
- **mode:** chỉ nhận **FULL** hoặc **DELTA**.
- **maxRows:** nếu được cung cấp thì phải lớn hơn 0.

~~~java
public class CustomerImportParametersValidator
        implements JobParametersValidator {

    @Override
    public void validate(JobParameters parameters)
            throws JobParametersInvalidException {

        String inputFile = parameters.getString("inputFile");
        String businessDate = parameters.getString("businessDate");
        String mode = parameters.getString("mode");
        Long maxRows = parameters.getLong("maxRows");

        if (inputFile == null || inputFile.isBlank()) {
            throw new JobParametersInvalidException(
                "inputFile không được để trống."
            );
        }

        if (businessDate == null || businessDate.isBlank()) {
            throw new JobParametersInvalidException(
                "businessDate là tham số bắt buộc."
            );
        }

        try {
            LocalDate.parse(businessDate);
        } catch (DateTimeParseException ex) {
            throw new JobParametersInvalidException(
                "businessDate phải có định dạng yyyy-MM-dd."
            );
        }

        if (mode != null
                && !mode.equals("FULL")
                && !mode.equals("DELTA")) {
            throw new JobParametersInvalidException(
                "mode chỉ nhận FULL hoặc DELTA."
            );
        }

        if (maxRows != null && maxRows <= 0) {
            throw new JobParametersInvalidException(
                "maxRows phải lớn hơn 0."
            );
        }
    }
}
~~~

Đăng ký validator thành bean:

~~~java
@Bean
JobParametersValidator customerImportParametersValidator() {
    return new CustomerImportParametersValidator();
}
~~~

Sau đó gắn nó vào Job bằng **.validator(...)** như ví dụ ở phần trước.

### Vì sao cần kiểm tra từng điều kiện?

**Kiểm tra sự hiện diện**

**getString("inputFile")** trả về **null** khi tham số không có. Kiểm tra thêm **isBlank()** để từ chối chuỗi rỗng hoặc chỉ có khoảng trắng.

**Kiểm tra định dạng**

**LocalDate.parse(...)** kiểm tra ngày theo định dạng ISO mặc định. Các giá trị như **15/11/2026** hoặc **2026-13-40** không được chấp nhận trong ví dụ này.

**Kiểm tra miền giá trị**

**mode** chỉ nhận hai giá trị nghiệp vụ được hỗ trợ. Điều này ngăn một giá trị tùy ý đi sâu vào các Step rồi tạo ra hành vi không xác định.

**Kiểm tra giới hạn**

**maxRows** là tham số tùy chọn. Nếu có mặt, giá trị phải lớn hơn 0. Nếu không có, Job có thể dùng giới hạn mặc định được cấu hình ở một thành phần khác.

### Gộp nhiều lỗi hay dừng ở lỗi đầu tiên?

Ví dụ trên ném exception ngay khi gặp điều kiện sai đầu tiên. Cách này đơn giản và phù hợp với nhiều Job.

Nếu muốn báo nhiều lỗi cùng lúc, validator có thể thu thập các thông báo vào danh sách rồi ném một **JobParametersInvalidException** chứa toàn bộ kết quả. Cách này giúp người gọi sửa nhiều tham số trong một lần, nhưng thông báo phải rõ ràng và không tiết lộ dữ liệu nhạy cảm.

## 6. Kiểm tra tham số theo quan hệ với nhau

Nhiều quy tắc không thể kiểm tra bằng cách xem từng tham số độc lập. Ví dụ:

- **fromDate** phải nhỏ hơn hoặc bằng **toDate**.
- **region** bắt buộc khi **mode** là **REGIONAL**.
- **maxRows** chỉ được dùng khi **dryRun** bật.
- **inputFile** và **sourceSystem** phải cùng có mặt.
- Chỉ cho phép một trong **customerId** hoặc **allCustomers**.

Validator tùy chỉnh có thể kiểm tra các quan hệ này:

~~~java
public class DateRangeParametersValidator
        implements JobParametersValidator {

    @Override
    public void validate(JobParameters parameters)
            throws JobParametersInvalidException {

        String fromValue = parameters.getString("fromDate");
        String toValue = parameters.getString("toDate");

        if (fromValue == null || toValue == null) {
            throw new JobParametersInvalidException(
                "Cần cung cấp cả fromDate và toDate."
            );
        }

        final LocalDate fromDate;
        final LocalDate toDate;

        try {
            fromDate = LocalDate.parse(fromValue);
            toDate = LocalDate.parse(toValue);
        } catch (DateTimeParseException ex) {
            throw new JobParametersInvalidException(
                "fromDate và toDate phải theo định dạng yyyy-MM-dd."
            );
        }

        if (fromDate.isAfter(toDate)) {
            throw new JobParametersInvalidException(
                "fromDate không được sau toDate."
            );
        }
    }
}
~~~

Ở đây, validator kiểm tra cả sự hiện diện, định dạng và quan hệ thứ tự. Các điều kiện được đặt cạnh nhau nên người đọc có thể hiểu hợp đồng đầu vào của Job.

Với nhiều tham số có quan hệ phức tạp, nên tách từng nhóm quy tắc thành phương thức riêng như **validateDateRange(...)**, **validateMode(...)** hoặc **validateInputSource(...)**. Điều này giúp validator dễ đọc và dễ kiểm thử.

## 7. Phân biệt kiểm tra tên, kiểu và giá trị

Một JobParameters có thể chứa nhiều loại giá trị. Cần phân biệt ba lớp kiểm tra:

| Lớp kiểm tra | Câu hỏi cần trả lời | Ví dụ |
|---|---|---|
| Tên tham số | Có đúng tập tham số được phép không? | **inputFile** có được hỗ trợ không? |
| Kiểu dữ liệu | Giá trị có đúng kiểu cần dùng không? | **maxRows** có phải số nguyên dài không? |
| Giá trị và nghiệp vụ | Giá trị có hợp lệ theo quy tắc không? | **maxRows** có lớn hơn 0 không? |

**DefaultJobParametersValidator** chủ yếu giải quyết lớp tên và sự hiện diện. Custom validator có thể đọc giá trị theo kiểu phù hợp, kiểm tra định dạng và quy tắc nghiệp vụ.

Nên dùng kiểu dữ liệu phù hợp khi xây dựng JobParameters thay vì luôn chuyển tất cả thành chuỗi. Spring Batch hỗ trợ các kiểu tham số chuẩn như String, Long, Double và Date; mô hình JobParameter cũng lưu thông tin kiểu cùng cờ identifying. Khi nhận dữ liệu từ hệ thống bên ngoài, hãy chuyển đổi và báo lỗi ở lớp tiếp nhận tham số nếu giá trị không thể chuyển sang kiểu mong muốn.

Ví dụ xây dựng tham số:

~~~java
JobParameters parameters = new JobParametersBuilder()
    .addString("inputFile", "data/customers.csv", true)
    .addString("businessDate", "2026-11-15", true)
    .addLong("maxRows", 50000L, false)
    .addString("region", "APAC", false)
    .toJobParameters();
~~~

Trong ví dụ:

- **inputFile** và **businessDate** được đánh dấu identifying.
- **maxRows** và **region** không tham gia nhận diện JobInstance.
- **toJobParameters()** tạo tập tham số dùng khi khởi chạy Job.

Cờ identifying phải được chọn theo ý nghĩa nghiệp vụ. Nếu một tham số làm thay đổi đơn vị dữ liệu hoặc kết quả logic của lần chạy, có thể cần đưa nó vào định danh. Nếu tham số chỉ điều chỉnh cách vận hành mà không tạo ra một công việc logic mới, có thể không cần identifying.

## 8. Identifying parameters và restart

Parameter validation không thay thế quy tắc nhận diện JobInstance. Một bộ tham số có thể hợp lệ nhưng vẫn không tạo ra JobInstance mới nếu các identifying parameters không thay đổi.

Ví dụ, Job nhập dữ liệu theo ngày:

~~~java
JobParameters parameters = new JobParametersBuilder()
    .addString("businessDate", "2026-11-15", true)
    .addString("inputFile", "data/customers-20261115.csv", true)
    .addString("notificationEmail", "ops@example.com", false)
    .toJobParameters();
~~~

Nếu lần chạy thất bại và cần restart, hãy dùng cùng các identifying parameters để Spring Batch tìm đúng JobInstance. Có thể thay đổi một tham số không identifying nếu điều đó phù hợp với thiết kế, nhưng phải chắc chắn thay đổi đó không làm thay đổi ý nghĩa xử lý hoặc gây sai lệch khi restart.

Một số nguyên tắc:

- Dùng identifying parameters để xác định lô hoặc đơn vị công việc logic.
- Giữ nguyên identifying parameters khi restart một JobInstance đã thất bại hoặc dừng.
- Chỉ tạo identifying parameter mới khi thực sự muốn tạo một JobInstance mới.
- Không thêm timestamp hoặc UUID mới vào identifying parameters trong mỗi lần thử restart.
- Nếu tham số vận hành không identifying nhưng ảnh hưởng đến kết quả nghiệp vụ, hãy xem xét lại thiết kế định danh.

Ví dụ, nếu mỗi lần chạy thêm một timestamp identifying, lần restart sẽ trở thành một JobInstance mới. Job có thể bắt đầu lại từ đầu thay vì khôi phục checkpoint của instance trước.

Validator nên kiểm tra tham số cần thiết cho logic Job, còn quyết định restart hay tạo instance mới thuộc về cách xây dựng JobParameters và cơ chế JobRepository.

## 9. Giá trị mặc định và chuẩn hóa tham số

Không phải tham số nào cũng bắt buộc người gọi phải cung cấp. Một số tham số có thể có giá trị mặc định, chẳng hạn:

- **mode** mặc định là **FULL**.
- **maxRows** mặc định là 100000.
- **region** mặc định là vùng được cấu hình cho tenant.
- **dryRun** mặc định là **false**.

Có hai cách phổ biến để xử lý:

**Cách 1: bổ sung giá trị mặc định trước khi tạo JobParameters.**

Lớp nhận request hoặc dịch vụ khởi chạy Job có thể chuẩn hóa đầu vào, bổ sung giá trị mặc định rồi tạo JobParameters. Validator nhận được bộ tham số đã chuẩn hóa.

**Cách 2: xử lý giá trị thiếu trong thành phần sử dụng tham số.**

Nếu tham số là tùy chọn, validator có thể chấp nhận giá trị **null**, còn Step hoặc một bean cấu hình có thể dùng giá trị mặc định.

Không nên để nhiều thành phần tự chọn các giá trị mặc định khác nhau. Hãy quy định một nơi chịu trách nhiệm chuẩn hóa để hành vi của Job nhất quán giữa các cách khởi chạy.

Ví dụ xử lý mặc định trong validator:

~~~java
String mode = parameters.getString("mode");

if (mode != null
        && !mode.equals("FULL")
        && !mode.equals("DELTA")) {
    throw new JobParametersInvalidException(
        "mode chỉ nhận FULL hoặc DELTA."
    );
}
~~~

Trong trường hợp này, **null** được chấp nhận và thành phần thực thi có thể hiểu nó là **FULL**. Nếu muốn giá trị mặc định xuất hiện rõ ràng trong metadata và có ý nghĩa đối với việc nhận diện, hãy bổ sung nó vào JobParameters trước khi khởi chạy thay vì chỉ ngầm hiểu trong Step.

## 10. Parameter validation và kiểm tra tài nguyên đầu vào

Một tham số có thể đúng định dạng nhưng tài nguyên mà nó trỏ đến lại không tồn tại hoặc không truy cập được.

Ví dụ, **inputFile** có thể là chuỗi hợp lệ nhưng file đã bị xóa. Có thể kiểm tra sự tồn tại và quyền đọc của file trong validator:

~~~java
String inputFile = parameters.getString("inputFile");

if (inputFile == null || inputFile.isBlank()) {
    throw new JobParametersInvalidException(
        "inputFile là bắt buộc."
    );
}

try {
    Path path = Path.of(inputFile);

    if (!Files.isRegularFile(path) || !Files.isReadable(path)) {
        throw new JobParametersInvalidException(
            "File đầu vào không tồn tại hoặc không đọc được."
        );
    }
} catch (InvalidPathException ex) {
    throw new JobParametersInvalidException(
        "inputFile không phải đường dẫn hợp lệ."
    );
}
~~~

Tuy nhiên, cần phân biệt hai nhóm kiểm tra:

- **Kiểm tra tham số:** giá trị có mặt, đúng định dạng và đáp ứng hợp đồng đầu vào.
- **Kiểm tra tài nguyên:** file, database, API hoặc hệ thống nguồn có sẵn sàng tại thời điểm thực thi không.

Kiểm tra tài nguyên trong validator có thể hữu ích với file cục bộ đơn giản. Với nguồn từ xa, kiểm tra mạng hoặc truy vấn lớn, không nên làm validator quá chậm hoặc tạo side effect. Tài nguyên có thể thay đổi trạng thái giữa thời điểm validation và lúc Step thực sự sử dụng.

Có thể tổ chức một Step chuẩn bị đầu vào để kiểm tra sâu hơn:

1. Validator xác nhận tham số bắt buộc và định dạng.
2. Step kiểm tra file, quyền truy cập, schema hoặc trạng thái nguồn.
3. Step nhập dữ liệu chỉ bắt đầu khi kiểm tra tài nguyên thành công.

Cách phân chia này giúp validator giữ trách nhiệm kiểm tra hợp đồng tham số, còn Step chịu trách nhiệm kiểm tra điều kiện thực thi.

## 11. Đọc JobParameters trong Step

Sau khi tham số đã được kiểm tra, các thành phần trong Step có thể sử dụng chúng. Với bean cần giá trị tại thời điểm chạy, Spring Batch cung cấp **@StepScope** và late binding.

Ví dụ reader nhận đường dẫn file:

~~~java
@Bean
@StepScope
FlatFileItemReader<CustomerInput> customerReader(
        @Value("#{jobParameters['inputFile']}") String inputFile) {

    return new FlatFileItemReaderBuilder<CustomerInput>()
        .name("customerReader")
        .resource(new FileSystemResource(inputFile))
        .encoding(StandardCharsets.UTF_8.name())
        .build();
}
~~~

Khi Step bắt đầu, Spring Batch tạo bean theo scope và inject giá trị **inputFile** từ JobParameters. Validator đã kiểm tra tham số này có mặt và không rỗng trước khi Step đi vào xử lý.

Có thể đọc các tham số khác theo cách tương tự:

~~~java
@Value("#{jobParameters['businessDate']}")
String businessDate
~~~

Không nên dùng **@StepScope** chỉ để thay thế mọi cấu hình bean. Chỉ dùng khi bean cần truy cập JobParameters, StepExecutionContext hoặc JobExecutionContext tại runtime.

Validator cấp Job nên kiểm tra tham số trước khi chúng được sử dụng trong các bean có late binding. Điều này giúp tránh lỗi khó hiểu khi bean được tạo mà tham số không tồn tại.

## 12. Kết hợp validator mặc định và quy tắc tùy chỉnh

Trong một Job thực tế, có thể cần cả kiểm tra tập tên tham số lẫn kiểm tra giá trị. Có thể tạo một validator điều phối hai phần:

~~~java
public class CombinedImportParametersValidator
        implements JobParametersValidator {

    private final JobParametersValidator keysValidator =
        new DefaultJobParametersValidator(
            new String[] {"inputFile", "businessDate"},
            new String[] {"mode", "maxRows"}
        );

    private final JobParametersValidator valuesValidator =
        new CustomerImportParametersValidator();

    @Override
    public void validate(JobParameters parameters)
            throws JobParametersInvalidException {

        keysValidator.validate(parameters);
        valuesValidator.validate(parameters);
    }
}
~~~

Sau đó gắn **CombinedImportParametersValidator** vào Job.

Thứ tự kiểm tra có ý nghĩa: kiểm tra tập tên và sự hiện diện trước, sau đó mới đọc và kiểm tra giá trị. Nếu tham số bắt buộc bị thiếu, lỗi được báo ngay tại bước đầu.

Với một validator kết hợp, hãy bảo đảm custom validator xử lý đúng trường hợp tham số tùy chọn không có mặt. Tránh giả định một tham số luôn tồn tại nếu nó không được khai báo là required.

## 13. Thông báo lỗi validation

Thông báo lỗi nên giúp người vận hành biết cần sửa tham số nào và vì sao. Tránh thông báo quá chung như **Invalid parameters** nếu có thể nêu điều kiện cụ thể.

Ví dụ:

| Tình huống | Thông báo phù hợp |
|---|---|
| Thiếu **inputFile** | **inputFile là tham số bắt buộc.** |
| Ngày sai định dạng | **businessDate phải có định dạng yyyy-MM-dd.** |
| **mode** không hỗ trợ | **mode chỉ nhận FULL hoặc DELTA.** |
| **maxRows** bằng 0 | **maxRows phải lớn hơn 0.** |
| Thiếu một đầu của khoảng ngày | **Cần cung cấp cả fromDate và toDate.** |
| Khoảng ngày không hợp lệ | **fromDate không được sau toDate.** |

Không đưa toàn bộ giá trị tham số vào log một cách mặc định. Một số tham số có thể chứa thông tin cá nhân, token, đường dẫn nhạy cảm hoặc mã tham chiếu nội bộ. Nên log tên tham số và nguyên nhân, đồng thời che hoặc loại bỏ giá trị nhạy cảm.

Ở lớp khởi chạy Job, có thể bắt **JobParametersInvalidException** để chuyển thành phản hồi phù hợp:

~~~java
try {
    jobLauncher.run(importCustomersJob, parameters);
} catch (JobParametersInvalidException ex) {
    // Trả lỗi đầu vào cho caller hoặc ghi nhận request không hợp lệ.
    throw ex;
}
~~~

Đây là ví dụ minh họa ranh giới xử lý lỗi. Cách trả HTTP status, ghi log hoặc báo lỗi cho scheduler phụ thuộc vào ứng dụng gọi Job.

## 14. Kiểm thử JobParametersValidator

Validator là một thành phần Java độc lập nên có thể kiểm thử mà không cần chạy toàn bộ Job. Nên có các trường hợp hợp lệ, thiếu tham số, sai định dạng, sai miền giá trị và sai quan hệ giữa các tham số.

Ví dụ kiểm thử custom validator bằng JUnit:

~~~java
class CustomerImportParametersValidatorTest {

    private final CustomerImportParametersValidator validator =
        new CustomerImportParametersValidator();

    @Test
    void acceptsValidParameters() {
        JobParameters parameters = new JobParametersBuilder()
            .addString("inputFile", "data/customers.csv")
            .addString("businessDate", "2026-11-15")
            .addString("mode", "FULL")
            .addLong("maxRows", 1000L)
            .toJobParameters();

        assertDoesNotThrow(() -> validator.validate(parameters));
    }

    @Test
    void rejectsMissingInputFile() {
        JobParameters parameters = new JobParametersBuilder()
            .addString("businessDate", "2026-11-15")
            .toJobParameters();

        assertThrows(
            JobParametersInvalidException.class,
            () -> validator.validate(parameters)
        );
    }

    @Test
    void rejectsInvalidBusinessDate() {
        JobParameters parameters = new JobParametersBuilder()
            .addString("inputFile", "data/customers.csv")
            .addString("businessDate", "15/11/2026")
            .toJobParameters();

        assertThrows(
            JobParametersInvalidException.class,
            () -> validator.validate(parameters)
        );
    }

    @Test
    void rejectsUnsupportedMode() {
        JobParameters parameters = new JobParametersBuilder()
            .addString("inputFile", "data/customers.csv")
            .addString("businessDate", "2026-11-15")
            .addString("mode", "UNKNOWN")
            .toJobParameters();

        assertThrows(
            JobParametersInvalidException.class,
            () -> validator.validate(parameters)
        );
    }
}
~~~

Các bài kiểm thử trên tập trung vào hợp đồng đầu vào. Với **DefaultJobParametersValidator**, nên kiểm thử thêm:

- Đủ tất cả required keys.
- Thiếu từng required key.
- Chỉ có optional keys.
- Có key ngoài danh sách required và optional.
- Cấu hình required/optional không hợp lệ.

Ngoài kiểm thử validator riêng, cần có kiểm thử tích hợp để xác nhận Job thực sự sử dụng validator đã cấu hình. Một validator viết đúng nhưng không được gắn vào Job sẽ không bảo vệ được luồng khởi chạy.

### Kiểm thử ở cấp Job

Có thể dùng tiện ích kiểm thử của Spring Batch hoặc khởi chạy Job trong test context để xác nhận:

- Tham số hợp lệ cho phép Job đi vào Step.
- Tham số không hợp lệ làm Job bị từ chối trước khi Step xử lý dữ liệu.
- Các identifying parameters tạo đúng JobInstance.
- Cùng identifying parameters có thể được dùng khi restart theo trạng thái của instance.
- Các tham số không identifying không vô tình tạo JobInstance mới.

Không chỉ kiểm tra exception. Hãy xác nhận Step không được thực thi khi validation thất bại, ví dụ bằng một listener, mock hoặc trạng thái dữ liệu đầu ra.

## 15. Những lỗi thiết kế thường gặp

### Không gắn validator vào Job

Tạo một lớp triển khai **JobParametersValidator** không có nghĩa Spring Batch tự động sử dụng nó. Phải gắn validator vào Job bằng **.validator(...)** hoặc cấu hình tương ứng.

### Chỉ kiểm tra tham số trong reader

Nếu kiểm tra tham số bắt buộc bên trong reader, Job có thể bắt đầu và một phần vòng đời Step đã diễn ra trước khi lỗi được phát hiện. Những điều kiện đầu vào chung nên được kiểm tra ở cấp Job.

### Dùng DefaultJobParametersValidator để kiểm tra giá trị

Validator mặc định chủ yếu kiểm tra tên tham số bắt buộc và tùy chọn. Nó không thay thế custom validator cho định dạng ngày, giới hạn số hoặc quan hệ giữa các tham số.

### Coi chuỗi không rỗng là giá trị hợp lệ

Một chuỗi có thể có nội dung nhưng sai định dạng hoặc không có ý nghĩa nghiệp vụ. Ví dụ **businessDate=tomorrow** không phải ngày ISO hợp lệ. Cần kiểm tra cả định dạng và miền giá trị.

### Đặt tất cả tham số thành identifying

Nếu mỗi lần chạy đều thêm một timestamp hoặc UUID identifying, Spring Batch sẽ tạo JobInstance mới thay vì restart instance cũ. Chỉ đánh dấu identifying cho các tham số thực sự xác định đơn vị công việc logic.

### Đặt tham số ảnh hưởng kết quả thành non-identifying mà không xem xét

Nếu hai lần chạy cùng JobInstance nhưng **mode** hoặc **inputFile** thay đổi theo cách làm thay đổi dữ liệu cần xử lý, restart có thể tiếp tục với đầu vào khác với lần chạy ban đầu. Cần chọn định danh phù hợp và giữ tham số nhất quán trong vòng đời JobInstance.

### Validator thực hiện side effect

Không nên để validator ghi dữ liệu nghiệp vụ, gửi thông báo hoặc thay đổi trạng thái nguồn. Validator nên kiểm tra và từ chối đầu vào. Side effect thuộc các Step hoặc dịch vụ chuyên trách.

### Validator quá chậm hoặc phụ thuộc dịch vụ không ổn định

Nếu validator gọi nhiều API hoặc truy vấn lớn, thời gian khởi chạy Job có thể tăng và lỗi hạ tầng bị nhầm thành lỗi tham số. Hãy giữ kiểm tra ở cấp Job nhanh, xác định; đưa kiểm tra tài nguyên chuyên sâu vào Step chuẩn bị khi phù hợp.

### Thông báo lỗi làm lộ dữ liệu

Không ghi nguyên văn mọi JobParameters vào log. Hãy bảo vệ token, thông tin cá nhân, đường dẫn nhạy cảm và dữ liệu nội bộ.

## 16. Quy trình xây dựng parameter validation

Khi thêm validation cho một Job mới, có thể thực hiện theo trình tự:

1. **Liệt kê tham số:** ghi rõ tên, kiểu, ý nghĩa và tham số nào bắt buộc.
2. **Xác định định danh:** quyết định tham số nào tham gia nhận diện JobInstance.
3. **Định nghĩa giá trị hợp lệ:** định dạng ngày, miền số, danh sách enum và giới hạn.
4. **Định nghĩa quan hệ:** quy tắc giữa các tham số như khoảng ngày hoặc chế độ xử lý.
5. **Chọn validator:** dùng DefaultJobParametersValidator cho required/optional keys và custom validator cho quy tắc giá trị.
6. **Gắn validator vào Job:** cấu hình **.validator(...)** trong JobBuilder.
7. **Chuẩn hóa mặc định:** xử lý giá trị mặc định ở một nơi thống nhất trước khi khởi chạy.
8. **Kiểm thử:** kiểm tra trường hợp hợp lệ, thiếu, sai định dạng, sai quan hệ và restart.
9. **Quan sát lỗi:** bảo đảm thông báo rõ ràng và không làm lộ dữ liệu nhạy cảm.

Một bảng hợp đồng tham số có thể giúp nhóm phát triển và vận hành thống nhất cách gọi Job:

| Tham số | Kiểu | Bắt buộc | Identifying | Quy tắc |
|---|---|---:|---:|---|
| **inputFile** | String | Có | Có | Đường dẫn hoặc mã nguồn đầu vào hợp lệ |
| **businessDate** | String | Có | Có | Ngày ISO **yyyy-MM-dd** |
| **mode** | String | Không | Tùy nghiệp vụ | **FULL** hoặc **DELTA** |
| **maxRows** | Long | Không | Thường không | Lớn hơn 0 |
| **notificationEmail** | String | Không | Không | Địa chỉ email hợp lệ nếu có |

Bảng này là ví dụ. Mỗi Job cần định nghĩa hợp đồng tham số theo đúng nghiệp vụ, cách restart và cách hệ thống bên ngoài khởi chạy Job.

## 17. Những điểm cần nhớ

- JobParameters là tập dữ liệu đầu vào của một lần chạy Job.
- JobParametersValidator kiểm tra tham số ở cấp Job trước khi luồng Step bắt đầu.
- **DefaultJobParametersValidator** kiểm tra required keys và optional keys.
- Custom validator kiểm tra định dạng, kiểu, miền giá trị và quan hệ giữa các tham số.
- Validator ném **JobParametersInvalidException** khi đầu vào không hợp lệ.
- Phải gắn validator vào Job bằng **.validator(...)** để Spring Batch sử dụng.
- Identifying parameters quyết định JobInstance; chúng phải nhất quán khi restart.
- Giá trị mặc định nên được chuẩn hóa tại một nơi thống nhất.
- Kiểm tra tham số khác với kiểm tra tài nguyên và xác thực từng item.
- Validator nên nhanh, xác định, không có side effect và không ghi lộ dữ liệu nhạy cảm.
- Kiểm thử validator độc lập và kiểm thử tích hợp để bảo đảm Job thực sự áp dụng quy tắc.

Parameter validation giúp Job chỉ bắt đầu khi đầu vào đáp ứng hợp đồng đã định nghĩa. Khi kiểm tra đúng ở cấp Job và thiết kế identifying parameters nhất quán, ứng dụng Spring Batch sẽ giảm lỗi phát sinh muộn, dễ vận hành và hỗ trợ restart đáng tin cậy hơn.

