# String, Long, Double và Date parameter

`JobParameters` là tập hợp các giá trị đầu vào được truyền khi khởi chạy một job Spring Batch. Những giá trị này cho biết job cần xử lý dữ liệu nào và có thể cung cấp thông tin vận hành như tên tệp, mã khách hàng, ngày nghiệp vụ hoặc tỷ giá áp dụng. Spring Batch lưu các tham số cùng metadata thực thi trong `JobRepository`, nhờ đó có thể tra cứu lịch sử và xác định một lần chạy có phải là lần restart của công việc trước đó hay không.

Mỗi job parameter có tên, giá trị, kiểu dữ liệu và cờ `identifying`. Bốn kiểu thường gặp là `String`, `Long`, `Double` và `Date`. Chọn đúng kiểu giúp ứng dụng truyền dữ liệu rõ ràng, tránh phải tự phân tích chuỗi trong từng step và kiểm soát chính xác định danh của `JobInstance`.

## 1. JobParameters dùng để làm gì?

Một job thường được thiết kế để chạy nhiều lần với các đầu vào khác nhau. Ví dụ, `dailyReportJob` có thể tạo báo cáo cho từng ngày; `customerImportJob` có thể nhập các tệp khác nhau; `recalculateAccountJob` có thể xử lý một nhóm tài khoản.

Thay vì viết một job riêng cho mỗi ngày hoặc mỗi tệp, ứng dụng định nghĩa một job và truyền `JobParameters` cho từng lần khởi chạy.

Ví dụ:

| Parameter | Giá trị ví dụ | Mục đích |
|---|---|---|
| `inputFile` | `file:/data/customers-2026-11-15.csv` | Tệp cần nhập |
| `tenantId` | `1205` | Phạm vi khách hàng của tenant |
| `exchangeRate` | `1.08` | Tỷ giá được dùng trong phép tính |
| `businessDate` | `2026-11-15` | Ngày nghiệp vụ cần xử lý |

Những giá trị này có thể ảnh hưởng đến dữ liệu được chọn, quy tắc xử lý và kết quả đầu ra. Chúng cũng được lưu trong metadata để người vận hành biết job đã chạy với bộ đầu vào nào.

## 2. JobParameter có kiểu dữ liệu và cờ identifying

Một `JobParameter` không chỉ là một chuỗi văn bản. Nó bao gồm:

- **Tên (name):** khóa để step hoặc job truy xuất giá trị, ví dụ `businessDate`.
- **Giá trị (value):** dữ liệu được truyền, ví dụ ngày 15 tháng 11 năm 2026.
- **Kiểu (type):** lớp Java của giá trị, ví dụ `String`, `Long`, `Double` hoặc `Date`.
- **Identifying:** cờ xác định tham số có tham gia tạo định danh `JobInstance` hay không.

`JobParameters` là đối tượng bất biến sau khi được tạo. Khi cần một bộ tham số khác, ứng dụng tạo một `JobParameters` mới thay vì sửa bộ tham số đã dùng cho execution.

Hai nhóm tham số thường gặp:

| Nhóm | Vai trò | Ví dụ |
|---|---|---|
| Identifying parameter | Xác định công việc nghiệp vụ cụ thể và tham gia tạo `JobInstance` | `businessDate`, `inputFile`, `tenantId` |
| Non-identifying parameter | Bổ sung thông tin cho lần chạy nhưng không làm thay đổi định danh instance | `requestedBy`, `notificationEmail`, `traceLabel` |

Ví dụ, nếu `businessDate` là identifying và `requestedBy` là non-identifying, hai yêu cầu chạy `dailyReportJob` với cùng ngày nghiệp vụ nhưng do hai người khác nhau gửi vẫn trỏ tới cùng `JobInstance`.

Việc chọn identifying cần dựa vào ý nghĩa nghiệp vụ. Nếu `tenantId` và `businessDate` xác định một báo cáo riêng cho mỗi tenant mỗi ngày, cả hai nên là identifying. Nếu `requestedBy` chỉ dùng để ghi audit, thường không cần đưa vào định danh.

## 3. Tạo JobParameters bằng JobParametersBuilder

`JobParametersBuilder` là cách thuận tiện để tạo một bộ tham số có kiểu. Các phương thức `addString`, `addLong`, `addDouble` và `addDate` nhận giá trị tương ứng và có overload cho phép chỉ định cờ identifying.

Ví dụ kết hợp cả bốn kiểu:

```java
import java.util.Date;

import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;

Date businessDate = new Date();

JobParameters parameters = new JobParametersBuilder()
        .addString("inputFile", "file:/data/customers.csv", true)
        .addLong("tenantId", 1205L, true)
        .addDouble("exchangeRate", 1.08D, false)
        .addDate("businessDate", businessDate, true)
        .addString("requestedBy", "scheduler", false)
        .toJobParameters();
```

Trong ví dụ:

- `inputFile` là `String`, xác định nguồn dữ liệu cần nhập.
- `tenantId` là `Long`, xác định tenant cần xử lý.
- `exchangeRate` là `Double`, cung cấp tỷ giá nhưng không tham gia định danh instance.
- `businessDate` là `Date`, xác định ngày hoặc thời điểm nghiệp vụ theo cách ứng dụng quy ước.
- `requestedBy` là `String` để ghi nhận nguồn yêu cầu và không làm thay đổi định danh instance.

Tham số identifying hay non-identifying được chỉ rõ bằng đối số boolean cuối cùng. Nên truyền rõ giá trị này thay vì dựa vào overload mặc định, vì cờ identifying ảnh hưởng trực tiếp đến việc Spring Batch xem hai lần khởi chạy có cùng `JobInstance` hay không.

Sau khi tạo, truyền bộ tham số cho `JobLauncher`:

```java
JobExecution execution = jobLauncher.run(myJob, parameters);
```

`JobLauncher` sử dụng job name và identifying parameters để tìm hoặc tạo `JobInstance`, sau đó tạo `JobExecution` nếu trạng thái instance cho phép.

## 4. String parameter

`String` phù hợp với giá trị dạng văn bản hoặc định danh có cấu trúc chuỗi, chẳng hạn:

- Đường dẫn hoặc tên tệp đầu vào.
- Mã tenant, mã chi nhánh hoặc mã nghiệp vụ nếu hệ thống định nghĩa chúng là chuỗi.
- Ngôn ngữ hoặc định dạng báo cáo.
- Tên vùng dữ liệu, loại nghiệp vụ hoặc nhãn yêu cầu.

Tạo tham số:

```java
JobParameters parameters = new JobParametersBuilder()
        .addString("inputFile", "file:/data/orders.csv", true)
        .addString("requestedBy", "nightly-scheduler", false)
        .toJobParameters();
```

Đọc tham số:

```java
String inputFile = parameters.getString("inputFile");
String requestedBy = parameters.getString("requestedBy");
```

Một số lưu ý khi dùng `String`:

- Không nên biến mọi giá trị thành chuỗi chỉ vì chuỗi dễ truyền. Mã số cần tính toán hoặc so sánh số học nên dùng kiểu số phù hợp.
- Chuẩn hóa giá trị có ý nghĩa định danh. Ví dụ, `orders.csv` và `./orders.csv` có thể cùng trỏ đến một tệp nhưng là hai chuỗi khác nhau; nếu dùng làm identifying parameter, chúng có thể tạo định danh khác nhau.
- Xác định rõ quy tắc chữ hoa/chữ thường, khoảng trắng và chuẩn hóa Unicode nếu giá trị tham gia định danh.
- Không truyền mật khẩu, access token hoặc dữ liệu bí mật vào `JobParameters`, vì metadata được lưu để theo dõi và có thể được hiển thị trong công cụ vận hành hoặc log.

## 5. Long parameter

`Long` là kiểu số nguyên 64-bit có dấu trong Java. Nó phù hợp với giá trị số nguyên có thể vượt phạm vi của `Integer`, ví dụ:

- ID của tenant, khách hàng hoặc tài khoản.
- Số thứ tự bản ghi hoặc checkpoint dạng số.
- Số lượng item, số trang hoặc giới hạn xử lý.
- Mốc thời gian dạng epoch nếu ứng dụng quy ước dùng số nguyên.

Tạo và đọc tham số:

```java
JobParameters parameters = new JobParametersBuilder()
        .addLong("tenantId", 1205L, true)
        .addLong("pageSize", 500L, false)
        .toJobParameters();

Long tenantId = parameters.getLong("tenantId");
Long pageSize = parameters.getLong("pageSize");
```

Hậu tố `L` làm rõ literal là kiểu `long`. Khi giá trị đến từ API hoặc cấu hình bên ngoài, cần kiểm tra chuỗi đầu vào có thể chuyển thành số nguyên hợp lệ và nằm trong phạm vi của `Long`.

Không nên dùng `Long` cho mã có số 0 ở đầu nếu số 0 đó là một phần của mã. Ví dụ, mã khách hàng `001205` có thể phải giữ nguyên dưới dạng `String`; chuyển thành `Long` sẽ làm mất số 0 đầu tiên và thay đổi giá trị định danh.

## 6. Double parameter

`Double` là kiểu số thực dấu phẩy động 64-bit theo chuẩn IEEE 754. Nó phù hợp với một số giá trị đo lường hoặc tham số tính toán xấp xỉ, ví dụ:

- Tỷ lệ chuyển đổi hoặc tỷ lệ phần trăm.
- Hệ số mô phỏng.
- Ngưỡng đo lường có phần thập phân.
- Hệ số điều chỉnh không yêu cầu biểu diễn thập phân chính xác tuyệt đối.

Ví dụ:

```java
JobParameters parameters = new JobParametersBuilder()
        .addDouble("exchangeRate", 1.08D, false)
        .addDouble("threshold", 0.75D, false)
        .toJobParameters();

Double exchangeRate = parameters.getDouble("exchangeRate");
Double threshold = parameters.getDouble("threshold");
```

`Double` có thể biểu diễn một số số thập phân dưới dạng gần đúng. Chẳng hạn, nhiều giá trị như `0.1` không có biểu diễn nhị phân hữu hạn chính xác. Vì vậy, không nên dùng `Double` cho tiền tệ, số dư hoặc phép tính tài chính cần chính xác đến từng đơn vị nhỏ nhất.

Với tiền tệ, hãy cân nhắc truyền giá trị theo đơn vị nhỏ nhất dưới dạng `Long` (ví dụ số cent) hoặc dùng `BigDecimal` khi phiên bản và cấu hình Spring Batch hỗ trợ kiểu parameter tùy chỉnh cùng cơ chế chuyển đổi bền vững. Nếu dùng `BigDecimal`, cần bảo đảm converter và định dạng lưu/đọc ổn định giữa các lần chạy và các phiên bản ứng dụng.

## 7. Date parameter

`Date` trong Java thường chỉ `java.util.Date`, đại diện cho một thời điểm trên trục thời gian với độ chính xác mili giây. Nó không lưu tên múi giờ như `Asia/Ho_Chi_Minh`; về bản chất, nó biểu diễn một instant. Múi giờ chỉ được dùng khi chuyển instant thành chuỗi ngày giờ cho người dùng hoặc khi diễn giải ngày nghiệp vụ.

Tạo tham số:

```java
import java.time.LocalDate;
import java.time.ZoneId;
import java.util.Date;

Date businessDate = Date.from(
        LocalDate.of(2026, 11, 15)
                .atStartOfDay(ZoneId.of("Asia/Ho_Chi_Minh"))
                .toInstant()
);

JobParameters parameters = new JobParametersBuilder()
        .addDate("businessDate", businessDate, true)
        .toJobParameters();
```

Đọc tham số:

```java
Date businessDate = parameters.getDate("businessDate");
```

### Date khác ngày nghiệp vụ như thế nào?

Một `Date` là thời điểm, trong khi nghiệp vụ có thể chỉ quan tâm đến một ngày lịch như “ngày 15 tháng 11”. Nếu tạo `Date` ở múi giờ của máy chủ, cùng một ngày lịch có thể chuyển thành instant khác khi ứng dụng chạy trên máy chủ ở múi giờ khác.

Để tránh sai lệch:

1. Xác định rõ ngày nghiệp vụ thuộc múi giờ nào.
2. Chuyển ngày lịch thành instant bằng `ZoneId` được quy định, không dựa vào múi giờ mặc định của máy chủ.
3. Giữ cùng quy tắc chuyển đổi ở mọi node khởi chạy job.
4. Nếu tham số thực sự là ngày không có giờ, ưu tiên kiểu biểu diễn ngày thuần như `LocalDate` khi phiên bản Spring Batch đang dùng hỗ trợ typed parameter đó.

Trong các phiên bản Spring Batch hỗ trợ Java Time parameters, `JobParametersBuilder` có các phương thức như `addLocalDate`, `addLocalDateTime` và `addLocalTime`. Ví dụ:

```java
JobParameters parameters = new JobParametersBuilder()
        .addLocalDate("businessDate", LocalDate.of(2026, 11, 15), true)
        .toJobParameters();
```

API Java Time và kiểu tham số được hỗ trợ phụ thuộc phiên bản Spring Batch. Nếu dự án dùng phiên bản cũ chỉ hỗ trợ `Date`, cần thống nhất múi giờ và cách chuẩn hóa instant giữa các môi trường.

## 8. Đọc JobParameters trong job và step

Sau khi launcher truyền tham số, các thành phần trong job có thể truy xuất giá trị qua `JobParameters`. Ví dụ, từ `JobExecution`:

```java
public void printParameters(JobExecution jobExecution) {
    JobParameters parameters = jobExecution.getJobParameters();

    String inputFile = parameters.getString("inputFile");
    Long tenantId = parameters.getLong("tenantId");
    Double exchangeRate = parameters.getDouble("exchangeRate");
    Date businessDate = parameters.getDate("businessDate");

    // Sử dụng các giá trị trong logic nghiệp vụ.
}
```

Các getter trả về `null` nếu tham số không tồn tại hoặc không có giá trị. Vì vậy, nếu tham số là bắt buộc, hãy kiểm tra ngay khi job bắt đầu và báo lỗi tham số rõ ràng thay vì để `NullPointerException` xuất hiện ở giữa step.

Có thể dùng `JobParametersValidator` để kiểm tra đầu vào trước khi job thực thi. Validator có thể xác nhận tham số bắt buộc, miền giá trị, quan hệ giữa các tham số và định dạng nghiệp vụ.

Ví dụ kiểm tra đơn giản:

```java
public void validate(JobParameters parameters) {
    String inputFile = parameters.getString("inputFile");
    Long tenantId = parameters.getLong("tenantId");

    if (inputFile == null || inputFile.isBlank()) {
        throw new IllegalArgumentException("inputFile is required");
    }

    if (tenantId == null || tenantId <= 0) {
        throw new IllegalArgumentException("tenantId must be positive");
    }
}
```

Đoạn mã trên minh họa logic kiểm tra; trong ứng dụng thực tế nên triển khai theo interface `JobParametersValidator` và ném `JobParametersInvalidException` cho lỗi tham số không hợp lệ.

## 9. Kiểu dữ liệu ảnh hưởng đến JobInstance như thế nào?

Các identifying parameters tham gia tạo định danh của `JobInstance`. Do đó, tên, kiểu và giá trị cần được tạo nhất quán mỗi lần khởi chạy.

Ví dụ, các bộ tham số sau không nên được xem là tương đương nếu ứng dụng tạo chúng với kiểu khác nhau:

```java
// Bộ tham số thứ nhất
new JobParametersBuilder()
        .addString("tenantId", "1205", true)
        .toJobParameters();

// Bộ tham số thứ hai
new JobParametersBuilder()
        .addLong("tenantId", 1205L, true)
        .toJobParameters();
```

Một bộ dùng `String`, bộ còn lại dùng `Long`. Mặc dù con người có thể đọc cả hai thành số 1205, chúng có kiểu khác nhau và không nên dựa vào việc chúng tạo cùng một định danh instance. Hãy thống nhất kiểu tham số ngay từ thiết kế job và giữ ổn định giữa các phiên bản triển khai.

Một số tình huống thường gây ra instance ngoài ý muốn:

- Một node gửi `tenantId` dưới dạng `Long`, node khác gửi dưới dạng `String`.
- Ngày nghiệp vụ được chuyển thành `Date` theo múi giờ mặc định của từng máy chủ.
- Chuỗi đường dẫn có hoặc không có dấu `./`, khác chữ hoa/chữ thường hoặc khác cách chuẩn hóa.
- Một tham số `run.id` được thêm vào identifying parameters mỗi lần launch.
- Một tham số vận hành như `requestedBy` bị đánh dấu identifying dù không đại diện cho công việc nghiệp vụ mới.

Nếu cùng một kỳ nghiệp vụ phải được coi là cùng instance, tất cả launcher phải thống nhất tên, kiểu, giá trị chuẩn hóa và cờ identifying của các tham số liên quan.

## 10. JobParameters và restart

Khi job thất bại hoặc dừng, Spring Batch có thể restart cùng `JobInstance` bằng cách khởi chạy lại với cùng identifying parameters, nếu job cho phép restart và trạng thái execution phù hợp.

Ví dụ, lần chạy đầu tiên dùng:

```text
jobName = dailyReportJob
businessDate = 2026-11-15 (identifying Date hoặc LocalDate)
tenantId = 1205 (identifying Long)
requestedBy = scheduler (non-identifying String)
```

Nếu lần chạy thất bại, yêu cầu restart phải giữ nguyên các identifying parameters. Thay đổi `businessDate` hoặc `tenantId` có thể tạo `JobInstance` khác thay vì restart instance trước đó.

Các tham số non-identifying có thể thay đổi mà không làm thay đổi định danh instance, nhưng cần cân nhắc ý nghĩa vận hành. Ví dụ, thay `requestedBy` từ `scheduler` thành `operator` có thể vẫn trỏ tới cùng instance; tuy nhiên, các step không nên dựa vào một non-identifying parameter có thể thay đổi giữa các lần restart để quyết định dữ liệu nghiệp vụ cốt lõi.

Không dùng tham số có giá trị thay đổi mỗi lần gọi như timestamp hiện tại làm identifying nếu mục tiêu là restart cùng công việc. Nếu cần tạo một lần xử lý mới có chủ đích, hãy dùng một tham số nghiệp vụ thể hiện rõ lần reprocess hoặc phiên bản xử lý.

## 11. Truyền tham số từ dòng lệnh và hệ thống điều phối

Ứng dụng có thể nhận job parameters từ REST API, scheduler, command line hoặc hệ thống điều phối. Dù nguồn đầu vào là gì, ứng dụng cần chuyển giá trị sang kiểu Java mong muốn trước khi tạo `JobParameters`.

Ví dụ một API nhận payload:

```json
{
  "inputFile": "file:/data/customers.csv",
  "tenantId": 1205,
  "exchangeRate": 1.08,
  "businessDate": "2026-11-15"
}
```

Không nên mặc định rằng giá trị JSON hoặc chuỗi command line đã có kiểu đúng trong `JobParameters`. Ứng dụng cần parse và validate dữ liệu, đặc biệt là số, ngày tháng và múi giờ. Một chuỗi ngày như `15/11/2026` có thể được hiểu khác nhau tùy locale; định dạng ISO như `2026-11-15` dễ trao đổi và kiểm tra hơn.

Với tham số `Date`, cần quy định chuỗi đầu vào biểu diễn ngày lịch hay thời điểm có múi giờ. Nếu biểu diễn một instant, nên dùng định dạng có offset hoặc UTC rõ ràng. Nếu biểu diễn ngày nghiệp vụ, dùng quy ước ngày và múi giờ cố định.

## 12. Kiểu tùy chỉnh và khả năng chuyển đổi

Các kiểu `String`, `Long`, `Double` và `Date` là những kiểu phổ biến, dễ hiểu và thường được hỗ trợ trực tiếp bởi các phiên bản Spring Batch. Các phiên bản mới của Spring Batch hỗ trợ typed `JobParameter` linh hoạt hơn, cho phép dùng kiểu khác nếu có cơ chế chuyển đổi chuỗi và lưu/đọc tương ứng.

Nếu muốn dùng `BigDecimal`, `UUID`, `LocalDate` hoặc một kiểu nghiệp vụ riêng, cần xác nhận phiên bản Spring Batch và cấu hình conversion service. Cần bảo đảm:

- Giá trị có thể chuyển đổi từ dạng lưu trữ về đúng kiểu Java.
- Dạng biểu diễn ổn định và không phụ thuộc locale hoặc timezone mặc định.
- Mọi node trong môi trường phân tán dùng cùng converter và cùng quy tắc chuẩn hóa.
- Job có thể đọc lại metadata cũ sau khi ứng dụng được nâng cấp.

Không nên dùng một đối tượng phức tạp tùy chỉnh làm identifying parameter nếu chưa xác định rõ cách tạo key ổn định. Đối với định danh instance, những giá trị đơn giản, bất biến và có biểu diễn chuẩn thường dễ vận hành hơn.

## 13. Lỗi thường gặp khi dùng các kiểu parameter

| Tình huống | Nguyên nhân | Cách xử lý |
|---|---|---|
| Không đọc được tham số bằng getter mong muốn | Tên parameter sai hoặc kiểu Java không đúng | Kiểm tra tên, kiểu khi tạo và dùng getter tương ứng |
| Cùng dữ liệu nhưng tạo JobInstance mới | Kiểu hoặc giá trị identifying khác nhau | Chuẩn hóa kiểu, giá trị và cờ identifying ở mọi launcher |
| Mất số 0 ở đầu mã | Dùng `Long` cho mã định danh dạng chuỗi | Dùng `String` nếu số 0 là một phần của mã |
| Kết quả tiền tệ sai lệch nhỏ | Dùng `Double` cho phép tính cần chính xác thập phân | Dùng số nguyên theo đơn vị nhỏ nhất hoặc `BigDecimal` với converter phù hợp |
| Job xử lý lệch ngày giữa các node | Tạo `Date` theo timezone mặc định khác nhau | Dùng timezone nghiệp vụ cố định hoặc `LocalDate` nếu được hỗ trợ |
| Restart không tìm thấy instance cũ | Identifying parameter bị thay đổi hoặc thêm timestamp/run ID | Khôi phục đúng identifying parameters của instance trước |
| Step phát sinh NullPointerException | Tham số bắt buộc không được truyền | Validate tham số trước khi thực thi job |
| Sau nâng cấp không đọc được parameter cũ | Converter hoặc kiểu lưu trữ thay đổi | Duy trì tương thích converter và kiểm tra metadata trước khi nâng cấp |

## 14. Ví dụ hoàn chỉnh: nhập dữ liệu theo tenant và ngày nghiệp vụ

Giả sử hệ thống cần nhập dữ liệu đơn hàng từ tệp CSV cho một tenant trong một ngày. Job dùng các tham số:

| Tên | Kiểu | Identifying | Ý nghĩa |
|---|---|---|---|
| `inputFile` | `String` | Có | Tệp đầu vào cụ thể |
| `tenantId` | `Long` | Có | Tenant cần nhập |
| `businessDate` | `Date` | Có | Ngày nghiệp vụ đã chuẩn hóa theo timezone quy định |
| `exchangeRate` | `Double` | Không | Tỷ giá dùng cho tính toán phụ trợ |
| `requestedBy` | `String` | Không | Nguồn yêu cầu để audit |

Tạo tham số:

```java
Date businessDate = Date.from(
        LocalDate.of(2026, 11, 15)
                .atStartOfDay(ZoneId.of("Asia/Ho_Chi_Minh"))
                .toInstant()
);

JobParameters parameters = new JobParametersBuilder()
        .addString("inputFile", "file:/data/orders-2026-11-15.csv", true)
        .addLong("tenantId", 1205L, true)
        .addDate("businessDate", businessDate, true)
        .addDouble("exchangeRate", 1.08D, false)
        .addString("requestedBy", "nightly-scheduler", false)
        .toJobParameters();

JobExecution execution = jobLauncher.run(importOrdersJob, parameters);
```

Khi job bắt đầu, ứng dụng có thể đọc tham số và xác thực:

```java
JobParameters parameters = jobExecution.getJobParameters();

String inputFile = parameters.getString("inputFile");
Long tenantId = parameters.getLong("tenantId");
Date businessDate = parameters.getDate("businessDate");
Double exchangeRate = parameters.getDouble("exchangeRate");

if (inputFile == null || tenantId == null || businessDate == null) {
    throw new IllegalArgumentException("Missing required job parameter");
}
```

Nếu scheduler gửi lại đúng bộ identifying parameters, Spring Batch nhận diện đó là cùng công việc nghiệp vụ. Nếu execution trước thất bại và job cho phép restart, lần khởi chạy tiếp theo có thể restart instance. Nếu ngày nghiệp vụ hoặc tenant thay đổi, đó là một instance khác. `exchangeRate` và `requestedBy` không làm thay đổi định danh trong ví dụ này, nhưng ứng dụng vẫn phải quyết định liệu việc thay đổi chúng giữa các lần restart có phù hợp với quy tắc nghiệp vụ hay không.

## 15. Những nguyên tắc cần nhớ

- `JobParameters` là tập hợp tham số có tên, giá trị, kiểu dữ liệu và cờ identifying.
- `String` phù hợp với văn bản, đường dẫn và mã cần giữ nguyên ký tự như số 0 đầu.
- `Long` phù hợp với ID số nguyên, số lượng hoặc giá trị nguyên 64-bit.
- `Double` phù hợp với số thực xấp xỉ; tránh dùng cho tiền tệ cần độ chính xác thập phân.
- `Date` biểu diễn một instant, không tự mang timezone hoặc ý nghĩa ngày lịch; cần chuẩn hóa theo timezone nghiệp vụ.
- `JobParametersBuilder` giúp tạo tham số có kiểu và chỉ rõ identifying/non-identifying.
- Chỉ identifying parameters tham gia xác định `JobInstance`; thay đổi chúng có thể tạo instance mới thay vì restart.
- Các launcher trong môi trường nhiều node phải thống nhất kiểu, giá trị chuẩn hóa và cờ identifying.
- Validate tham số bắt buộc trước khi job chạy để lỗi đầu vào được phát hiện sớm.
- Với kiểu tùy chỉnh hoặc Java Time, kiểm tra hỗ trợ của phiên bản Spring Batch và bảo đảm converter ổn định qua restart/nâng cấp.

Chọn đúng `String`, `Long`, `Double` và `Date` giúp `JobParameters` thể hiện rõ dữ liệu đầu vào, hỗ trợ kiểm tra và lưu metadata chính xác, đồng thời giữ cho định danh `JobInstance` ổn định giữa các lần launch và restart.
