# Parameter converter

Trong Spring Batch, `JobParameters` là tập tham số đầu vào xác định cách một `Job` được chạy và, với các parameter identifying, xác định logical `JobInstance` nào sẽ được sử dụng. Khi tham số đến từ dòng lệnh, file cấu hình hoặc một giao diện vận hành, dữ liệu ban đầu thường là các chuỗi. `JobParametersConverter` chuyển đổi dữ liệu dạng `Properties` thành `JobParameters` có kiểu dữ liệu và cờ identifying phù hợp; nó cũng có thể chuyển `JobParameters` ngược lại thành `Properties`.

Parameter converter tạo cầu nối giữa cách người vận hành truyền tham số và mô hình tham số có kiểu của Spring Batch. Nhờ vậy, job có thể nhận ngày nghiệp vụ, số lượng, cờ hoặc các kiểu dữ liệu khác theo quy ước thống nhất, thay vì tự phân tích chuỗi ở từng reader, processor hay tasklet.

## JobParametersConverter làm nhiệm vụ gì?

`JobParametersConverter` là interface trong Spring Batch, cung cấp hai chiều chuyển đổi:

```java
public interface JobParametersConverter {
    JobParameters getJobParameters(Properties properties);

    Properties getProperties(JobParameters parameters);
}
```

Tên phương thức thể hiện rõ hai hướng:

- `getJobParameters(Properties)`: đọc các property đầu vào và tạo `JobParameters`.
- `getProperties(JobParameters)`: biểu diễn các parameter hiện có thành `Properties`, thường hữu ích khi hiển thị, lưu hoặc truyền lại tham số.

Ví dụ, một giao diện vận hành gửi các giá trị `businessDate`, `maxRows` và `requestedBy`. Converter có thể chuyển các giá trị đó thành tham số có kiểu `String`, `Long` và cờ identifying tương ứng. Khi job chạy, các thành phần batch đọc giá trị từ `JobParameters` thay vì phải biết dữ liệu ban đầu được nhập từ CLI, file hay API.

Luồng xử lý khái quát:

```text
CLI / file / giao diện vận hành
              |
              v
       Properties (String values)
              |
              v
     JobParametersConverter
              |
              v
       JobParameters
              |
              v
       JobLauncher.run(...)
              |
              v
 JobRepository / JobInstance / JobExecution
```

Converter chịu trách nhiệm về biểu diễn và chuyển kiểu. `JobLauncher` dùng `JobParameters` để khởi chạy job; `JobRepository` dùng identifying parameters cùng tên job để nhận diện `JobInstance`.

## DefaultJobParametersConverter

Spring Batch cung cấp `DefaultJobParametersConverter` làm implementation mặc định. Converter này hỗ trợ biểu diễn parameter bằng property key và value, trong đó value có thể chứa thông tin kiểu dữ liệu và identifying flag theo cú pháp mà phiên bản Spring Batch sử dụng.

Với cú pháp thông dụng của `DefaultJobParametersConverter`, một parameter có thể được biểu diễn như sau:

```text
parameterName=parameterValue,fully.qualified.TypeName,identifying
```

Trong đó:

- `parameterName` là tên parameter.
- `parameterValue` là giá trị dạng chuỗi cần chuyển đổi.
- `fully.qualified.TypeName` là tên đầy đủ của kiểu dữ liệu đích, nếu cú pháp phiên bản đang dùng yêu cầu khai báo kiểu.
- `identifying` cho biết parameter có tham gia nhận diện `JobInstance` hay không.

Ví dụ minh họa:

```properties
businessDate=2026-11-15,java.lang.String,true
maxRows=5000,java.lang.Long,false
requestedBy=night-scheduler,java.lang.String,false
```

Trong ví dụ này, `businessDate` là identifying parameter vì nó xác định ngày nghiệp vụ cần xử lý. `maxRows` và `requestedBy` là non-identifying theo giả định rằng thay đổi giới hạn vận hành hoặc người khởi chạy không tạo ra một logical job mới. Quyết định identifying phải dựa trên nghiệp vụ thực tế, không chỉ dựa vào kiểu dữ liệu.

Định dạng cụ thể và tập kiểu dữ liệu có thể chuyển đổi phụ thuộc phiên bản Spring Batch cùng `ConversionService` được cấu hình. Khi sử dụng cú pháp này trong command line hoặc file properties, hãy đối chiếu tài liệu đúng phiên bản của dự án; không giả định mọi phiên bản đều hỗ trợ cùng kiểu hoặc cùng quy tắc mặc định.

### Chuyển Properties thành JobParameters

Ví dụ sử dụng converter trực tiếp:

```java
Properties properties = new Properties();
properties.setProperty(
        "businessDate",
        "2026-11-15,java.lang.String,true");
properties.setProperty(
        "maxRows",
        "5000,java.lang.Long,false");
properties.setProperty(
        "requestedBy",
        "night-scheduler,java.lang.String,false");

JobParametersConverter converter = new DefaultJobParametersConverter();
JobParameters parameters = converter.getJobParameters(properties);
```

Sau khi chuyển đổi, job nhận các giá trị có kiểu:

```java
String businessDate = parameters.getString("businessDate");
Long maxRows = parameters.getLong("maxRows");
String requestedBy = parameters.getString("requestedBy");
```

`JobParameters` lưu giá trị cùng kiểu dữ liệu và identifying flag. Nhờ đó, các thành phần batch có thể truy cập parameter theo kiểu mong muốn và repository có đủ thông tin để nhận diện instance.

### Chuyển JobParameters thành Properties

Chiều ngược lại hữu ích khi cần hiển thị hoặc truyền bộ parameter đã tạo:

```java
Properties properties = converter.getProperties(parameters);
properties.forEach((name, value) ->
        System.out.println(name + "=" + value));
```

Kết quả biểu diễn phụ thuộc implementation và phiên bản. Với converter mặc định, thông tin kiểu và identifying được biểu diễn theo định dạng mà converter có thể đọc lại. Nếu ứng dụng tự định nghĩa converter, cần thiết kế hai phương thức theo hướng tương thích: dữ liệu do `getProperties` tạo ra phải có thể được `getJobParameters` đọc lại mà không làm thay đổi kiểu hoặc identifying flag.

## Converter và JobParametersBuilder khác nhau thế nào?

Hai công cụ đều tạo `JobParameters`, nhưng phục vụ hai cách nhập dữ liệu khác nhau.

| Công cụ | Đầu vào | Cách sử dụng phù hợp |
| --- | --- | --- |
| `JobParametersConverter` | `Properties`, thường có giá trị dạng chuỗi | Chuyển tham số từ CLI, file cấu hình hoặc giao diện vận hành |
| `JobParametersBuilder` | Giá trị Java đã có kiểu | Tạo tham số trực tiếp trong mã ứng dụng |
| `JobParametersValidator` | Một bộ `JobParameters` đã tạo | Kiểm tra tính hợp lệ và quy tắc nghiệp vụ trước khi xử lý |
| `JobParametersIncrementer` | Bộ parameter hiện tại hoặc trạng thái khởi tạo | Tạo bộ parameter tiếp theo, thường dùng khi cần instance mới |

Ví dụ, khi một service nhận `LocalDate` từ request đã được framework web parse sẵn, có thể dùng `JobParametersBuilder` để tạo parameter. Nếu một batch operator nhập `businessDate=2026-11-15` qua CLI, converter phù hợp hơn để chuyển chuỗi sang mô hình tham số của Spring Batch.

Converter không thay thế validator. Một chuỗi ngày có thể chuyển thành `String` thành công nhưng vẫn không hợp lệ theo nghiệp vụ, ví dụ ngày nằm ngoài kỳ được phép quyết toán. Việc kiểm tra các điều kiện như khoảng ngày, sự tồn tại của tệp nguồn hoặc quyền chạy job thuộc trách nhiệm validator hoặc lớp nghiệp vụ.

## Kiểu dữ liệu và ConversionService

Parameter có kiểu giúp job tránh phải tự parse chuỗi ở nhiều nơi. Các kiểu thường dùng gồm `String`, `Long`, `Double` và các kiểu ngày tháng được hỗ trợ bởi phiên bản Spring Batch hoặc conversion service cấu hình.

Ví dụ về cách chọn kiểu:

| Giá trị nghiệp vụ | Kiểu parameter gợi ý | Lý do |
| --- | --- | --- |
| Ngày xử lý `2026-11-15` | `String` theo ISO hoặc kiểu ngày được hỗ trợ | Biểu diễn ngày rõ ràng, dễ truyền qua CLI |
| Số bản ghi tối đa `5000` | `Long` | Có thể dùng trực tiếp như một số nguyên |
| Ngưỡng tỷ lệ `0.95` | `Double` | Phù hợp giá trị số thập phân khi độ chính xác nghiệp vụ cho phép |
| Mã khách hàng `000123` | `String` | Giữ các số 0 ở đầu, tránh bị hiểu thành số |
| Chế độ chạy `dry-run` | `String` hoặc enum qua converter riêng | Chuyển thành lựa chọn nghiệp vụ có kiểm soát |

Không nên chuyển một mã định danh thành số chỉ vì nó chứa chữ số. Ví dụ `000123` nếu chuyển thành `Long` sẽ mất các số 0 ở đầu. Cũng cần thận trọng khi dùng `Double` cho tiền tệ hoặc số cần độ chính xác thập phân; các trường hợp đó thường nên dùng biểu diễn decimal phù hợp hoặc chuỗi có quy tắc parse rõ ràng.

### Kiểu ngày tháng

Đối với ngày nghiệp vụ, nên dùng định dạng ổn định như ISO-8601, ví dụ `2026-11-15`. Nếu converter mặc định của phiên bản dự án không hỗ trợ trực tiếp kiểu `LocalDate`, có thể giữ parameter ở dạng `String` rồi parse một lần ở lớp cấu hình/validator, hoặc cung cấp converter tùy chỉnh để chuyển sang `LocalDate`.

Với timestamp, cần quy định rõ múi giờ và định dạng. Một giá trị như `2026-11-15T09:30:00` không chứa offset nên có thể được hiểu khác nhau ở các môi trường. Nếu thời điểm phải nhất quán giữa các node, hãy truyền timestamp có offset hoặc chuẩn hóa UTC.

### Đăng ký chuyển đổi kiểu riêng

Nếu cần kiểu dữ liệu không được converter mặc định hỗ trợ, có thể mở rộng `ConversionService` mà `DefaultJobParametersConverter` sử dụng (API cấu hình cụ thể phụ thuộc phiên bản). Một hướng khác là triển khai `JobParametersConverter` riêng để kiểm soát hoàn toàn cú pháp và quy tắc chuyển đổi.

Ví dụ về ý tưởng chuyển một giá trị ISO date thành `LocalDate` trong converter tùy chỉnh:

```java
LocalDate businessDate = LocalDate.parse(dateText);
```

Ở bước xây dựng `JobParameters`, phiên bản Spring Batch hỗ trợ parameter có kiểu tùy chỉnh có thể lưu trực tiếp `LocalDate` cùng identifying flag. Nếu dự án đang dùng phiên bản chỉ hỗ trợ một tập kiểu cố định, hãy giữ parameter ở dạng `String` hoặc dùng kiểu được phiên bản đó hỗ trợ; đừng giả định chỉ cần parse trong một chỗ là mọi API metadata đều có thể lưu kiểu mới.

## Tự triển khai JobParametersConverter

Khi định dạng đầu vào của ứng dụng khác cú pháp mặc định, có thể triển khai interface `JobParametersConverter`. Ví dụ, một hệ thống chỉ cho phép hai tham số đã biết: `businessDate` và `maxRows`. Converter dưới đây thể hiện cách kiểm soát schema tham số một cách tường minh.

```java
public class SettlementParametersConverter implements JobParametersConverter {

    @Override
    public JobParameters getJobParameters(Properties properties) {
        JobParametersBuilder builder = new JobParametersBuilder();

        String businessDate = properties.getProperty("businessDate");
        if (businessDate != null && !businessDate.isBlank()) {
            builder.addString("businessDate", businessDate, true);
        }

        String maxRows = properties.getProperty("maxRows");
        if (maxRows != null && !maxRows.isBlank()) {
            builder.addLong("maxRows", Long.valueOf(maxRows), false);
        }

        return builder.toJobParameters();
    }

    @Override
    public Properties getProperties(JobParameters parameters) {
        Properties properties = new Properties();

        JobParameter<?> businessDate =
                parameters.getParameters().get("businessDate");
        if (businessDate != null) {
            properties.setProperty(
                    "businessDate",
                    businessDate.getValue().toString());
        }

        JobParameter<?> maxRows = parameters.getParameters().get("maxRows");
        if (maxRows != null) {
            properties.setProperty("maxRows", maxRows.getValue().toString());
        }

        return properties;
    }
}
```

Đây là converter theo schema cố định của ví dụ: `businessDate` luôn là identifying `String`, còn `maxRows` luôn là non-identifying `Long`. Phương thức `getProperties` trả về các giá trị ở dạng chuỗi theo đúng tên property. Khi mở rộng converter cho nhiều parameter, cần quyết định rõ cách xử lý property không biết, giá trị trống, kiểu sai, identifying flag và việc bảo toàn thông tin khi chuyển đổi hai chiều.

Trong mã thực tế, cần bổ sung xử lý lỗi có thông điệp rõ ràng. Ví dụ `maxRows=abc` sẽ gây lỗi parse `Long`; nên ánh xạ lỗi đó thành lỗi tham số dễ hiểu để người vận hành biết tên property và định dạng được yêu cầu. Không nên âm thầm thay giá trị sai bằng `0` hoặc một mặc định có thể làm thay đổi phạm vi xử lý.

### Quy tắc thiết kế converter tùy chỉnh

- Định nghĩa tên property và kiểu dữ liệu được hỗ trợ rõ ràng.
- Quy định identifying flag theo ý nghĩa nghiệp vụ.
- Dùng định dạng ngày, số và boolean ổn định giữa các môi trường.
- Quyết định rõ có từ chối property không được biết hay bỏ qua chúng.
- Bảo toàn thông tin cần thiết khi chuyển `JobParameters` ngược về `Properties`.
- Không ghi thông tin bí mật vào log hoặc biểu diễn tham số có thể được hiển thị cho người vận hành.
- Viết lỗi parse dễ hiểu, chỉ rõ property và định dạng mong đợi.

## Sử dụng converter với cơ chế khởi chạy job

Converter chỉ được sử dụng khi thành phần khởi chạy cần chuyển đầu vào dạng `Properties` sang `JobParameters`. Các launcher hoặc runner nhận tham số từ dòng lệnh thường có một điểm cấu hình converter. Ứng dụng cũng có thể gọi converter trực tiếp trước khi gọi `JobLauncher`.

Ví dụ tích hợp thủ công:

```java
Properties input = new Properties();
input.setProperty("businessDate", "2026-11-15");
input.setProperty("maxRows", "5000");

JobParametersConverter converter = new SettlementParametersConverter();
JobParameters parameters = converter.getJobParameters(input);

JobExecution execution = jobLauncher.run(settlementJob, parameters);
```

Trong trường hợp này, service kiểm soát rõ nguồn property và converter. Nếu dùng `CommandLineJobRunner`, Spring Boot runner hoặc một launcher infrastructure khác, hãy cấu hình converter tại extension point mà phiên bản đó cung cấp. Cơ chế auto-configuration và tên bean có thể khác giữa các phiên bản; không nên giả định chỉ khai báo một bean bất kỳ thì mọi runner đều tự động dùng nó.

Khi gọi `JobLauncher.run(job, parameters)` với `JobParameters` đã được tạo trực tiếp bằng `JobParametersBuilder`, converter không tự động chạy lại. Hai cách tạo tham số là những lựa chọn riêng tùy nguồn đầu vào.

## Identifying parameter và danh tính JobInstance

Converter có thể gán identifying flag cho từng parameter. Cờ này có ảnh hưởng trực tiếp đến cách `JobRepository` xác định `JobInstance`.

Ví dụ:

```properties
businessDate=2026-11-15,java.lang.String,true
requestedBy=operator-01,java.lang.String,false
```

Hai lần khởi chạy cùng job với `businessDate=2026-11-15` nhưng `requestedBy` khác nhau vẫn có cùng danh tính `JobInstance`, nếu `requestedBy` là non-identifying. Nếu `businessDate` thay đổi, Spring Batch xem đó là logical job khác.

Việc đánh dấu sai có thể gây hai loại vấn đề:

- Đánh dấu một parameter vận hành là identifying khiến mỗi giá trị mới tạo một `JobInstance` mới ngoài ý muốn. Ví dụ thêm timestamp mới mỗi lần retry có thể làm lần chạy mới không còn là restart của instance cũ.
- Đánh dấu một parameter nghiệp vụ là non-identifying khiến hai yêu cầu xử lý dữ liệu khác nhau bị xem là cùng logical job. Điều này có thể gây xung đột khi chạy đồng thời hoặc restart.

Converter nên tập trung chuyển đổi dữ liệu theo quy ước. Quy tắc identifying cần được thống nhất với thiết kế nghiệp vụ và luồng restart của job.

## Converter không thay thế JobParametersValidator

Chuyển đổi thành công chỉ cho biết dữ liệu có thể được biểu diễn thành kiểu parameter. Nó không đảm bảo giá trị phù hợp với nghiệp vụ.

Ví dụ, `maxRows=0` có thể parse thành `Long` hợp lệ nhưng job không cho phép giới hạn bằng 0. `businessDate=2099-01-01` có thể đúng định dạng nhưng nằm ngoài kỳ dữ liệu mà hệ thống cho phép. Những điều kiện này cần được kiểm tra bằng `JobParametersValidator` hoặc lớp nghiệp vụ trước khi job xử lý.

Ví dụ validator:

```java
public class SettlementParametersValidator implements JobParametersValidator {

    @Override
    public void validate(JobParameters parameters)
            throws JobParametersInvalidException {

        String businessDate = parameters.getString("businessDate");
        if (businessDate == null || businessDate.isBlank()) {
            throw new JobParametersInvalidException(
                    "businessDate is required");
        }

        Long maxRows = parameters.getLong("maxRows");
        if (maxRows != null && maxRows <= 0) {
            throw new JobParametersInvalidException(
                    "maxRows must be greater than zero");
        }
    }
}
```

Validator kiểm tra quy tắc nghiệp vụ trên `JobParameters` đã tạo. Converter xử lý cú pháp, kiểu dữ liệu và identifying flag. Tách hai trách nhiệm giúp lỗi định dạng và lỗi nghiệp vụ được xử lý rõ ràng.

## Lỗi thường gặp khi chuyển đổi parameter

### Không chuyển được kiểu dữ liệu

Giá trị đầu vào không phù hợp kiểu được khai báo, ví dụ `maxRows=abc` nhưng kiểu đích là `Long`. Kiểm tra định dạng, tên kiểu đầy đủ và khả năng chuyển đổi của `ConversionService`.

### Thiếu parameter bắt buộc

Property không có trong đầu vào hoặc tên bị viết sai. Converter có thể tạo bộ parameter thiếu giá trị nếu thiết kế cho phép; validator nên phát hiện tham số bắt buộc chưa được cung cấp và báo lỗi cụ thể.

### Giá trị có dấu phẩy hoặc ký tự đặc biệt

Nếu cú pháp converter dùng dấu phẩy để phân tách value, type và identifying flag, giá trị chứa dấu phẩy có thể bị parse sai nếu không có cơ chế escape được hỗ trợ. Hãy dùng định dạng đã quy định, tránh tự ghép chuỗi tùy ý hoặc viết converter riêng với quy tắc escaping rõ ràng.

### Sai identifying flag

Một parameter bị đánh dấu identifying ngoài ý muốn có thể tạo instance mới cho mỗi lần gọi. Kiểm tra biểu diễn parameter, mặc định identifying của converter và cách `JobParameters` được tạo.

### Chuyển đổi hai chiều không tương thích

Converter đọc một định dạng nhưng `getProperties` xuất ra định dạng khác hoặc bỏ mất type/identifying flag. Khi cần round-trip, hãy bảo đảm biểu diễn đầu ra có thể được đọc lại mà không thay đổi ý nghĩa parameter.

### Thay đổi kiểu parameter giữa các lần triển khai

Nếu một job đã lưu metadata với kiểu parameter cũ rồi ứng dụng thay đổi converter sang kiểu mới, cần đánh giá khả năng đọc lại các execution cũ và danh tính instance. Hãy duy trì quy ước tương thích hoặc có kế hoạch migration; không đổi kiểu identifying một cách tùy tiện giữa các lần triển khai.

### Lộ dữ liệu nhạy cảm

Tham số truyền trên command line có thể xuất hiện trong process list, shell history hoặc log tùy môi trường. Không truyền mật khẩu, access token hay bí mật trực tiếp qua job parameters. Hãy truyền một định danh tham chiếu an toàn tới secret manager hoặc cấu hình được bảo vệ.

## Kiểm thử converter

Converter là thành phần chuyển đổi dữ liệu đầu vào, vì vậy có thể kiểm thử độc lập mà không cần chạy toàn bộ job.

Ví dụ kiểm thử cơ bản với JUnit:

```java
@Test
void convertsPropertiesToTypedJobParameters() {
    Properties properties = new Properties();
    properties.setProperty("businessDate", "2026-11-15");
    properties.setProperty("maxRows", "5000");

    JobParametersConverter converter = new SettlementParametersConverter();
    JobParameters parameters = converter.getJobParameters(properties);

    assertEquals("2026-11-15", parameters.getString("businessDate"));
    assertEquals(5000L, parameters.getLong("maxRows"));
    assertTrue(parameters.getParameters().get("businessDate").isIdentifying());
    assertFalse(parameters.getParameters().get("maxRows").isIdentifying());
}
```

Nên kiểm tra thêm các trường hợp:

- Property không có hoặc có giá trị rỗng.
- Giá trị số không hợp lệ hoặc vượt giới hạn.
- Property không được hỗ trợ.
- Kiểu dữ liệu không có converter tương ứng.
- Identifying flag được giữ nguyên khi chuyển đổi hai chiều.
- Giá trị ngày tháng có định dạng hoặc timezone không hợp lệ.
- Giá trị chứa dấu phân tách hoặc ký tự đặc biệt theo cú pháp đã chọn.

Với converter mặc định, kiểm thử cần dùng cú pháp và kiểu được hỗ trợ bởi đúng phiên bản Spring Batch của dự án. Với converter tùy chỉnh, kiểm thử hợp đồng hai chiều giúp tránh thay đổi ngoài ý muốn khi sửa định dạng đầu vào.

## Gợi ý chọn cách chuyển đổi

| Nguồn tham số | Cách tiếp cận |
| --- | --- |
| Java service đã có giá trị kiểu mạnh | Dùng `JobParametersBuilder` |
| CLI hoặc file properties theo cú pháp chuẩn | Dùng `DefaultJobParametersConverter` |
| API nhận JSON có schema riêng | Parse và validate request, sau đó dùng builder hoặc converter riêng |
| Cần kiểu nghiệp vụ tùy chỉnh | Mở rộng `ConversionService` hoặc triển khai `JobParametersConverter` |
| Cần kiểm tra giá trị theo nghiệp vụ | Dùng `JobParametersValidator` sau khi chuyển đổi |

Chọn converter mặc định khi cú pháp và kiểu dữ liệu của nó đáp ứng nhu cầu. Chỉ triển khai converter riêng khi cần quy ước đầu vào khác, ánh xạ alias, kiểu dữ liệu đặc thù hoặc kiểm soát nghiêm ngặt schema parameter. Converter càng đơn giản và ổn định thì việc vận hành, restart và hỗ trợ người dùng càng dễ dàng.

## Ghi nhớ

`JobParametersConverter` chuyển đổi giữa `Properties` và `JobParameters`. `DefaultJobParametersConverter` đáp ứng cú pháp tham số phổ biến, trong khi converter tùy chỉnh cho phép kiểm soát kiểu dữ liệu, tên property và identifying flag theo quy ước của ứng dụng. Converter xử lý biểu diễn và chuyển kiểu; `JobParametersValidator` kiểm tra tính hợp lệ nghiệp vụ; `JobParametersBuilder` phù hợp khi tạo parameter trực tiếp từ mã Java. Hãy giữ định dạng ổn định, bảo toàn identifying flag, kiểm thử chuyển đổi hai chiều và tránh truyền bí mật qua tham số dòng lệnh.
