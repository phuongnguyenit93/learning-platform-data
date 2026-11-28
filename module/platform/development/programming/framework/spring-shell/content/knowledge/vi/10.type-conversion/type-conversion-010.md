# Chuẩn hóa đầu vào khác với âm thầm thay đổi ý nghĩa dữ liệu

Khi người dùng nhập một giá trị vào Spring Shell, framework cần chuyển chuỗi đầu vào thành kiểu Java mà command yêu cầu. Quá trình này có thể bao gồm đọc cú pháp, chuẩn hóa cách biểu diễn, chuyển đổi kiểu và kiểm tra tính hợp lệ. Những bước đó có liên quan nhưng không đồng nghĩa với nhau.

**Chuẩn hóa** đưa các cách biểu diễn được quy định là tương đương về một dạng thống nhất. **Chuyển đổi kiểu** biến một giá trị từ dạng này sang dạng khác, chẳng hạn chuỗi "42" thành số nguyên 42. **Validation** quyết định giá trị sau khi chuyển đổi có đáp ứng ràng buộc của command và nghiệp vụ hay không.

Ranh giới quan trọng là không được tự ý sửa dữ liệu để làm cho nó có vẻ hợp lệ. Nếu một mã tài khoản phân biệt chữ hoa và chữ thường, tự động đổi chữ thường thành chữ hoa có thể trỏ sang một tài khoản khác. Nếu một số tiền dùng dấu phẩy làm dấu thập phân, xóa mọi dấu phẩy có thể biến 12,50 thành 1250. Nếu một giá trị boolean bị gõ sai, biến nó thành false sẽ che giấu lỗi đầu vào.

Bài này dùng Spring Shell 4.x và Spring ConversionService. Ví dụ tập trung vào command nhận dữ liệu có kiểu rõ ràng, custom converter và những quy tắc cần công bố trước khi chuẩn hóa.

## 1. Phân biệt cú pháp, chuẩn hóa, chuyển đổi và validation

Một giá trị đi từ dòng lệnh vào nghiệp vụ thường trải qua các bước:

~~~mermaid
flowchart TD
    A["Chuỗi người dùng nhập"] --> B["Spring Shell phân tích option/argument"]
    B --> C["Chuẩn hóa theo hợp đồng dữ liệu"]
    C --> D["ConversionService chuyển thành kiểu Java"]
    D --> E["Bean Validation và kiểm tra nghiệp vụ"]
    E --> F["Command gọi application service"]
    D -->|Không chuyển đổi được| G["Lỗi đầu vào rõ ràng"]
    E -->|Không thỏa ràng buộc| H["Lỗi validation"]
~~~

| Bước | Câu hỏi | Ví dụ |
|---|---|---|
| Phân tích cú pháp | Token nào là option, token nào là argument? | --quantity 12 |
| Chuẩn hóa | Những khác biệt biểu diễn nào được hợp đồng cho phép bỏ qua? | Bỏ khoảng trắng ở hai đầu mã môi trường nếu quy định cho phép |
| Chuyển đổi kiểu | Chuỗi này biểu diễn được kiểu Java nào? | "12" thành Integer.valueOf(12) |
| Validation | Giá trị đã có kiểu có thỏa giới hạn không? | Số lượng phải lớn hơn 0 |
| Kiểm tra nghiệp vụ | Giá trị có hợp lệ trong trạng thái hệ thống hiện tại không? | Kho còn đủ số lượng để xuất không? |

Không phải command nào cũng cần bước chuẩn hóa. Nếu cú pháp đầu vào đã rõ và dữ liệu phải được giữ nguyên, chuyển đổi trực tiếp rồi validation là đủ. Nếu cần chuẩn hóa, hãy nêu rõ quy tắc và phạm vi áp dụng.

## 2. Chuẩn hóa biểu diễn không phải sửa nội dung tùy ý

Một số thao tác thường được gọi chung là "làm sạch dữ liệu", nhưng chúng có thể làm thay đổi ý nghĩa:

| Thao tác | Khi có thể phù hợp | Rủi ro nếu áp dụng mặc định |
|---|---|---|
| strip() khoảng trắng đầu/cuối | Hợp đồng nói khoảng trắng bao quanh không có ý nghĩa | Mất dữ liệu nếu khoảng trắng là một phần của giá trị |
| Chuyển chữ hoa/thường | Tên enum hoặc mã được định nghĩa không phân biệt hoa/thường | Thay đổi ID phân biệt hoa/thường |
| Xóa dấu phân cách | Định dạng đầu vào quy định chính xác dấu phân cách nào là ký hiệu nhóm | Ghép nhầm chữ số hoặc đổi dấu thập phân |
| Làm tròn số | Nghiệp vụ quy định rõ phương pháp và thời điểm làm tròn | Thay đổi số tiền hoặc số đo |
| Đoán định dạng ngày | Có một định dạng duy nhất được công bố | Đọc nhầm ngày/tháng |
| Chuẩn hóa Unicode | Hợp đồng định nghĩa các dạng Unicode tương đương | Gộp những chuỗi cần được phân biệt |
| Thay giá trị lỗi bằng mặc định | Giá trị mặc định là hành vi nghiệp vụ đã công bố | Che giấu lỗi nhập liệu và tạo hành động ngoài ý muốn |

Hãy đặt một câu hỏi trước mỗi phép biến đổi: **Hai biểu diễn này có được nghiệp vụ xác định là cùng một giá trị không?** Nếu không có câu trả lời rõ ràng, không nên tự động chuẩn hóa.

Ví dụ, nếu hợp đồng cho phép khoảng trắng quanh tên môi trường, " staging " có thể được chuẩn hóa thành "staging". Nhưng nếu người dùng nhập "stagng", converter phải báo lỗi. Không nên tự đoán rằng họ muốn nói "staging".

## 3. Spring Shell chuyển chuỗi thành kiểu Java như thế nào?

Các tham số method command được khai báo bằng **@Option**, **@Argument** hoặc **@Arguments**. Spring Shell 4 dùng cơ chế chuyển đổi kiểu của Spring để cung cấp giá trị có kiểu cho method. Những kiểu thông dụng như chuỗi, số, enum và collection được hỗ trợ thông qua các converter tương ứng.

Spring Framework định nghĩa **Converter<S, T>** cho một phép chuyển đổi có kiểu nguồn và kiểu đích. Ví dụ:

~~~java
public interface Converter<S, T> {
    T convert(S source);
}
~~~

Converter<String, Integer> nhận chuỗi và trả về số nguyên. Nếu nguồn không thể chuyển đổi, converter nên ném IllegalArgumentException để báo giá trị đầu vào không hợp lệ. Converter được dùng chung giữa các luồng nên cần tránh giữ trạng thái thay đổi theo từng lần gọi.

Trong Spring Shell 4, method command được thực thi qua **MethodInvokerCommandAdapter**. Adapter nhận một **ConfigurableConversionService** để chuyển đổi tham số và một **Validator** để kiểm tra ràng buộc. Nếu cần chỉ định rõ converter cho một method-backed command, ứng dụng có thể tạo adapter bằng mã và truyền conversion service đã cấu hình vào constructor.

### 3.1. Ví dụ custom converter có quy tắc rõ ràng

Giả sử lệnh triển khai nhận đích theo định dạng:

~~~text
<environment>@<region>
~~~

Hợp đồng của ví dụ quy định:

- Khoảng trắng ở hai đầu toàn bộ giá trị được bỏ qua.
- Tên môi trường không phân biệt chữ hoa/thường và được chuẩn hóa thành chữ thường.
- Region phải được nhập theo dạng chữ thường chuẩn; converter không tự đổi region.
- Chỉ chấp nhận các môi trường dev, staging và prod.
- Sai cú pháp hoặc giá trị không được hỗ trợ thì báo lỗi; không tự chọn môi trường mặc định.

Đầu tiên, tạo kiểu dữ liệu thể hiện đích triển khai:

~~~java
public record DeploymentTarget(String environment, String region) {
}
~~~

Converter chịu trách nhiệm thực hiện đúng hợp đồng trên:

~~~java
import java.util.Locale;
import java.util.Set;
import java.util.regex.Pattern;

import org.springframework.core.convert.converter.Converter;
import org.springframework.stereotype.Component;

@Component
public class DeploymentTargetConverter
        implements Converter<String, DeploymentTarget> {

    private static final Set<String> ENVIRONMENTS =
            Set.of("dev", "staging", "prod");

    private static final Pattern REGION_PATTERN =
            Pattern.compile("[a-z]{2}-[a-z]+-\\d+");

    @Override
    public DeploymentTarget convert(String source) {
        String value = source.strip();
        String[] parts = value.split("@", -1);

        if (parts.length != 2) {
            throw new IllegalArgumentException(
                    "Dùng định dạng <environment>@<region>, ví dụ staging@ap-southeast-1"
            );
        }

        String environment = parts[0].toLowerCase(Locale.ROOT);
        String region = parts[1];

        if (!ENVIRONMENTS.contains(environment)) {
            throw new IllegalArgumentException(
                    "Environment phải là dev, staging hoặc prod"
            );
        }

        if (!REGION_PATTERN.matcher(region).matches()) {
            throw new IllegalArgumentException(
                    "Region phải dùng dạng chữ thường, ví dụ ap-southeast-1"
            );
        }

        return new DeploymentTarget(environment, region);
    }
}
~~~

Kết quả:

| Đầu vào | Kết quả |
|---|---|
| staging@ap-southeast-1 | DeploymentTarget("staging", "ap-southeast-1") |
| " STAGING@ap-southeast-1 " | Cùng giá trị đích với dòng trên theo hợp đồng đã công bố |
| stagng@ap-southeast-1 | Báo lỗi vì environment không được hỗ trợ |
| staging@AP-SOUTHEAST-1 | Báo lỗi vì region không đúng định dạng chuẩn |
| staging | Báo lỗi vì thiếu region |

Ở đây, converter chỉ thay đổi hai điều được hợp đồng cho phép: khoảng trắng ngoài cùng và kiểu chữ của environment. Nó không sửa lỗi chính tả, không đổi region và không tự suy đoán phần bị thiếu.

### 3.2. Đưa converter vào adapter thực thi command

Để minh họa rõ conversion service mà command sử dụng, ví dụ sau tạo **DefaultConversionService**, thêm **DeploymentTargetConverter** rồi truyền service đó vào **MethodInvokerCommandAdapter**. Adapter vẫn gọi method Java thông thường và dùng các annotation trên tham số để đọc option:

~~~java
import java.lang.reflect.Method;

import jakarta.validation.Validator;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.convert.support.DefaultConversionService;
import org.springframework.shell.core.command.Command;
import org.springframework.shell.core.command.adapter.MethodInvokerCommandAdapter;

@Configuration
class DeploymentCommandConfiguration {

    @Bean
    Command deployCommand(
            DeploymentCommands target,
            DeploymentTargetConverter deploymentTargetConverter,
            Validator validator) throws NoSuchMethodException {

        DefaultConversionService conversionService =
                new DefaultConversionService();
        conversionService.addConverter(deploymentTargetConverter);

        Method method = DeploymentCommands.class.getMethod(
                "deploy", DeploymentTarget.class);

        return new MethodInvokerCommandAdapter(
                "deploy",
                "Triển khai ứng dụng.",
                "Deployment",
                "Dùng --target=<environment>@<region>.",
                false,
                method,
                target,
                conversionService,
                validator
        );
    }
}
~~~

**DefaultConversionService** đã đăng ký các phép chuyển đổi thông dụng của Spring; lệnh gọi **addConverter()** bổ sung phép chuyển đổi cho **DeploymentTarget**. Bean kiểu **Command** được Spring Shell 4 tự đưa vào **CommandRegistry**. Nếu ứng dụng đã có một adapter hoặc conversion service dùng chung, hãy bổ sung converter vào service đó thay vì tạo một bộ quy tắc chuyển đổi khác nhau cho cùng một loại dữ liệu.

Method đích được giữ trong một Spring bean:

~~~java
import org.springframework.shell.core.command.annotation.Option;
import org.springframework.stereotype.Component;

@Component
class DeploymentCommands {

    private final DeploymentService deploymentService;

    DeploymentCommands(DeploymentService deploymentService) {
        this.deploymentService = deploymentService;
    }

    public String deploy(
            @Option(longName = "target", required = true)
            DeploymentTarget target) {

        deploymentService.deploy(target);
        return "Đã gửi yêu cầu triển khai tới "
                + target.environment() + "@" + target.region();
    }
}
~~~

Người dùng gọi:

~~~text
deploy --target=staging@ap-southeast-1
~~~

Method nhận một đối tượng có cấu trúc thay vì tự tách chuỗi ở mọi command. Nhờ vậy, quy tắc parse và chuẩn hóa được tập trung, có thể kiểm thử độc lập.

## 4. Những trường hợp chuẩn hóa dễ làm thay đổi ý nghĩa

### 4.1. Khoảng trắng: strip hay giữ nguyên?

**strip()** loại bỏ khoảng trắng ở đầu và cuối chuỗi theo định nghĩa whitespace của Java. Nó không xóa khoảng trắng ở giữa chuỗi:

~~~java
String input = "  North  Zone  ";
String normalized = input.strip();
// "North  Zone"
~~~

Điều đó phù hợp với mã môi trường hoặc tên option nếu hợp đồng nói khoảng trắng ngoài cùng không có ý nghĩa. Với mật khẩu, token, khóa API, chữ ký hoặc giá trị mà từng ký tự đều có ý nghĩa, không được tự động strip.

Nếu một tên hiển thị cần loại bỏ khoảng trắng lặp, đó là một quy tắc khác. Ví dụ "North  Zone" thành "North Zone" làm thay đổi chuỗi bên trong, nên chỉ thực hiện nếu sản phẩm đã quy định rõ.

### 4.2. Chữ hoa/thường và Locale

Nếu một giá trị được định nghĩa không phân biệt hoa/thường, hãy dùng locale ổn định:

~~~java
String normalized = input.toLowerCase(Locale.ROOT);
~~~

Không dùng toLowerCase() không tham số cho định danh kỹ thuật, vì nó phụ thuộc locale mặc định của máy chạy. Quy tắc chuyển chữ trong một số ngôn ngữ có thể khác nhau; ví dụ chữ I trong locale Thổ Nhĩ Kỳ.

Chỉ áp dụng case folding cho loại dữ liệu được quy định là không phân biệt hoa/thường. Mã khách hàng, tên file, tên người dùng hoặc khóa tài nguyên có thể phân biệt chữ hoa/thường. Đổi chữ mà không có hợp đồng có thể khiến một định danh khác được truy cập.

### 4.3. Unicode và ký tự nhìn giống nhau

Một ký tự hiển thị có thể được biểu diễn bằng một code point hoặc bằng nhiều code point kết hợp. Unicode normalization dạng **NFC** có thể đưa các chuỗi tương đương về dạng chuẩn thống nhất.

Tuy nhiên, **NFKC** còn có thể gộp một số ký tự tương thích, chẳng hạn dạng full-width và dạng thông thường. Đây không chỉ là thay đổi cách lưu biểu diễn; nó có thể làm hai chuỗi vốn được hệ thống phân biệt trở thành một.

Chỉ chuẩn hóa Unicode khi hợp đồng của định danh quy định rõ dạng chuẩn. Cần đặc biệt thận trọng với mật khẩu, token, chữ ký số, nội dung đã ký hoặc dữ liệu cần bảo toàn byte/code point gốc. Khi cần lưu dấu vết nhập liệu, có thể giữ chuỗi gốc cùng giá trị chuẩn hóa đã được tạo ra.

### 4.4. Số và dấu phân cách thập phân

**BigDecimal** có thể chuyển chuỗi thập phân dùng dấu chấm:

~~~java
import java.math.BigDecimal;

BigDecimal amount = new BigDecimal("1250.75");
~~~

Không xóa dấu phẩy theo cách tổng quát:

~~~java
// Không làm như sau nếu chưa xác định quy ước đầu vào:
String normalized = input.replace(",", "");
~~~

Với dữ liệu "1,25", dấu phẩy có thể là dấu thập phân trong một locale. Xóa dấu phẩy sẽ tạo ra 125, khác hoàn toàn 1.25. Với "1,250", dấu phẩy có thể là dấu nhóm hàng nghìn. Không thể biết ý nghĩa chỉ bằng cách nhìn dấu câu mà không có quy tắc locale/format.

Đối với tiền tệ hoặc số đo, nên công bố một định dạng CLI ổn định, ví dụ dấu chấm là dấu thập phân và không chấp nhận dấu nhóm. Nếu cần hỗ trợ locale, hãy nhận locale rõ ràng hoặc cấu hình locale của command; parser phải kiểm tra toàn bộ chuỗi đã được đọc, không chấp nhận một tiền tố hợp lệ rồi bỏ phần còn lại.

Không dùng double cho phép tính tiền tệ cần độ chính xác thập phân. Dùng BigDecimal, quy định scale và chỉ làm tròn theo chính sách nghiệp vụ. setScale(2, RoundingMode.HALF_UP) là một quyết định nghiệp vụ; không nên đặt nó âm thầm trong converter dùng chung.

### 4.5. Ngày, giờ và múi giờ

Ngày dạng 03/04/2026 có thể được hiểu là ngày 3 tháng 4 hoặc ngày 4 tháng 3. Không tự đoán định dạng dựa trên locale máy chủ.

Với ngày không chứa thời điểm, dùng định dạng rõ ràng như ISO:

~~~java
import java.time.LocalDate;

LocalDate date = LocalDate.parse("2026-04-03");
~~~

Với một thời điểm cần xác định trên toàn hệ thống, yêu cầu timezone hoặc offset:

~~~java
import java.time.Instant;
import java.time.OffsetDateTime;

Instant timestamp = Instant.parse("2026-04-03T10:15:30Z");
OffsetDateTime eventTime =
        OffsetDateTime.parse("2026-04-03T17:15:30+07:00");
~~~

Không tự gán múi giờ mặc định của máy cho một giá trị không có timezone nếu nghiệp vụ cần một thời điểm tuyệt đối. **LocalDate** biểu diễn ngày lịch, còn **Instant** biểu diễn một thời điểm trên trục thời gian; chuyển giữa chúng cần một múi giờ cụ thể.

### 4.6. Boolean và giá trị mặc định

**Boolean.parseBoolean()** trả về true nếu chuỗi bằng "true" không phân biệt hoa/thường; các chuỗi khác đều trả về false. Vì vậy, nếu custom converter hoặc logic tự parse gọi phương thức này, "treu", "yes" hoặc chuỗi rỗng có thể biến thành false mà không báo lỗi.

Nếu hợp đồng chỉ cho phép true và false, hãy parse nghiêm ngặt:

~~~java
static boolean parseStrictBoolean(String source) {
    String value = source.strip();

    if ("true".equalsIgnoreCase(value)) {
        return true;
    }
    if ("false".equalsIgnoreCase(value)) {
        return false;
    }

    throw new IllegalArgumentException(
            "Giá trị boolean chỉ nhận true hoặc false"
    );
}
~~~

Không dùng giá trị mặc định để che lỗi nhập. Nếu command tự parse cờ force và người dùng nhập --force=treu, logic parse phải báo lỗi thay vì âm thầm hiểu là false.

## 5. Chuyển đổi kiểu và validation giải quyết hai vấn đề khác nhau

Converter trả lời câu hỏi: **Chuỗi này có biểu diễn được kiểu đích không?** Validation trả lời câu hỏi: **Giá trị đã có kiểu có thỏa ràng buộc không?**

Ví dụ:

- "12" chuyển đổi được thành số nguyên 12.
- 12 có thể chuyển đổi thành công nhưng không đạt giới hạn số lượng tối thiểu là 20.
- "twelve" không thể chuyển đổi thành số nguyên, vì vậy validation của @Min không có số nguyên để kiểm tra.

Spring Shell 4 tích hợp Bean Validation và chạy validation trên tham số command trước khi thực thi method. Có thể khai báo ràng buộc trực tiếp:

~~~java
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.Option;

@Command(name = "set-limit", description = "Thiết lập giới hạn xử lý.")
public String setLimit(
        @Option(longName = "name", required = true)
        @NotBlank
        String name,
        @Option(longName = "quantity", required = true)
        @Min(1)
        int quantity) {

    limitService.update(name, quantity);
    return "Đã cập nhật giới hạn";
}
~~~

Trong ví dụ, converter chịu trách nhiệm chuyển quantity thành int. Bean Validation kiểm tra số lượng ít nhất là 1 và name không rỗng. Service vẫn kiểm tra các điều kiện phụ thuộc trạng thái, chẳng hạn tên giới hạn đã tồn tại hoặc người dùng có quyền cập nhật hay chưa.

Không đặt truy vấn database, gọi API hoặc kiểm tra quyền phức tạp trong converter. Converter nên là phép biến đổi xác định từ biểu diễn sang kiểu dữ liệu. Quy tắc nghiệp vụ phụ thuộc trạng thái thuộc application service hoặc domain model.

## 6. Những dữ liệu không nên chuyển thành số

Một chuỗi chỉ chứa chữ số chưa chắc là số dùng để tính toán. Các loại sau thường là định danh:

| Dữ liệu | Vì sao nên giữ dạng chuỗi hoặc value object |
|---|---|
| Mã tài khoản 001234 | Số 0 đầu có ý nghĩa và phải được giữ |
| Số điện thoại 0901234567 | Không thực hiện phép cộng/trừ; số 0 đầu có thể quan trọng |
| Mã bưu chính 01234 | Số 0 đầu thuộc định danh |
| SKU 00042-A | Có thể chứa chữ, số và quy tắc phân biệt hoa/thường |
| Mã khách hàng | Có thể không liên tục và không mang ý nghĩa số học |
| Phiên bản 1.10 | Không tương đương số thập phân 1.1 trong quy tắc so sánh phiên bản |

Nếu ép mã tài khoản 001234 thành Integer, giá trị trở thành 123; thông tin ban đầu đã mất và không thể khôi phục chắc chắn. Hãy tạo kiểu **AccountId**, **PhoneNumber** hoặc **PostalCode** nếu cần hành vi riêng, nhưng không coi chúng là số học chỉ vì có chữ số.

## 7. Thiết kế converter an toàn

Một converter dùng được lâu dài nên có các đặc điểm:

1. **Hợp đồng rõ ràng:** mô tả định dạng chấp nhận, khoảng trắng, chữ hoa/thường, locale và alias.
2. **Chuyển đổi xác định:** cùng đầu vào và cùng quy tắc tạo ra cùng kết quả.
3. **Không có side effect:** không ghi database, gọi dịch vụ từ xa hoặc thay đổi trạng thái ứng dụng.
4. **Lỗi rõ ràng:** giá trị không hợp lệ phải tạo lỗi thay vì trả về giá trị mặc định.
5. **Bảo toàn dữ liệu:** chỉ chuẩn hóa những khác biệt được hợp đồng xác nhận là không có ý nghĩa.
6. **An toàn đa luồng:** converter không giữ dữ liệu tạm của từng lần gọi trong field có thể bị thay đổi.
7. **Có thể kiểm thử độc lập:** kiểm tra trực tiếp các đầu vào hợp lệ, không hợp lệ và trường hợp biên.

Nếu cần hỗ trợ nhiều định dạng đầu vào cũ, hãy định nghĩa alias rõ ràng:

~~~java
import java.util.Locale;

enum Environment {
    DEV, STAGING, PROD
}

static Environment parseEnvironment(String source) {
    return switch (source.strip().toLowerCase(Locale.ROOT)) {
        case "dev", "development" -> Environment.DEV;
        case "staging", "stage" -> Environment.STAGING;
        case "prod", "production" -> Environment.PROD;
        default -> throw new IllegalArgumentException(
                "Environment phải là dev, staging hoặc prod"
        );
    };
}
~~~

Các alias trên là một phần của hợp đồng CLI. Nếu sau này cần bỏ alias cũ, có thể phát cảnh báo deprecation trước khi loại bỏ. Không dùng fuzzy matching để tự sửa những giá trị gần giống nhau, vì nó có thể chọn nhầm môi trường hoặc tài nguyên.

## 8. Lỗi thường gặp khi chuẩn hóa đầu vào

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Mã tài khoản mất số 0 đầu | Chuyển identifier thành số nguyên | Giữ chuỗi hoặc tạo value object |
| Người dùng nhập boolean sai nhưng command vẫn chạy | Boolean.parseBoolean() coi mọi chuỗi khác true là false | Parse nghiêm ngặt và báo lỗi |
| Số tiền thay đổi sau khi bỏ dấu phẩy | Không xác định locale và dấu thập phân | Công bố grammar số hoặc yêu cầu locale rõ ràng |
| Số tiền bị thay đổi phần lẻ | Converter tự làm tròn | Giữ BigDecimal, làm tròn tại bước nghiệp vụ theo chính sách |
| Ngày bị đảo ngày/tháng | Dùng định dạng mơ hồ hoặc locale máy | Dùng định dạng ISO hoặc yêu cầu pattern rõ ràng |
| Tên người dùng không còn phân biệt hoa/thường | Tự động gọi toLowerCase() | Chỉ case-fold khi định danh được định nghĩa không phân biệt hoa/thường |
| Converter chấp nhận một phần chuỗi | Parser không kiểm tra toàn bộ đầu vào | Yêu cầu parse toàn chuỗi và từ chối phần dư |
| Lỗi nhập liệu biến thành hành động mặc định | Catch exception rồi trả về giá trị fallback | Giữ lỗi chuyển đổi và hiển thị thông báo sửa lệnh |
| Mật khẩu bị đổi trước khi xác thực | Áp dụng strip() hoặc Unicode normalization chung | Bảo toàn chính xác đầu vào theo chính sách xác thực |
| Converter lúc đúng lúc sai giữa các command | Lưu trạng thái lần gọi trước trong field dùng chung | Viết converter stateless hoặc bảo đảm thread-safe |

## 9. Kiểm thử chuẩn hóa và chuyển đổi

Không chỉ kiểm thử một chuỗi hợp lệ. Hãy kiểm tra cả dữ liệu biên và xác nhận converter không thay đổi phần dữ liệu cần bảo toàn.

Với **DeploymentTargetConverter**, có thể dùng các ca sau:

| Nhóm | Đầu vào | Kết quả mong đợi |
|---|---|---|
| Hợp lệ chuẩn | staging@ap-southeast-1 | Tạo target staging |
| Hợp lệ có khoảng trắng ngoài | " staging@ap-southeast-1 " | Chuẩn hóa theo hợp đồng |
| Hợp lệ khác kiểu chữ environment | STAGING@ap-southeast-1 | Chuẩn hóa environment thành staging |
| Environment không tồn tại | stagng@ap-southeast-1 | Ném lỗi |
| Region sai kiểu chữ | staging@AP-SOUTHEAST-1 | Ném lỗi |
| Thiếu region | staging@ | Ném lỗi |
| Thừa dấu phân cách | staging@ap-southeast-1@extra | Ném lỗi |
| Chuỗi rỗng | khoảng trắng | Ném lỗi |

Ví dụ kiểm thử:

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatIllegalArgumentException;

import org.junit.jupiter.api.Test;

class DeploymentTargetConverterTests {

    private final DeploymentTargetConverter converter =
            new DeploymentTargetConverter();

    @Test
    void normalizesOnlyTheAllowedParts() {
        DeploymentTarget target =
                converter.convert(" STAGING@ap-southeast-1 ");

        assertThat(target.environment()).isEqualTo("staging");
        assertThat(target.region()).isEqualTo("ap-southeast-1");
    }

    @Test
    void rejectsUnknownEnvironment() {
        assertThatIllegalArgumentException()
                .isThrownBy(() -> converter.convert("stagng@ap-southeast-1"));
    }

    @Test
    void rejectsNonCanonicalRegion() {
        assertThatIllegalArgumentException()
                .isThrownBy(() -> converter.convert("staging@AP-SOUTHEAST-1"));
    }
}
~~~

Ngoài unit test cho converter, cần có kiểm thử tích hợp command để xác minh Spring Shell dùng đúng **ConversionService**, truyền kiểu **DeploymentTarget** vào method và hiển thị lỗi đầu vào khi chuyển đổi thất bại. Kiểm thử validation riêng các ràng buộc sau khi chuyển đổi. Cuối cùng, kiểm tra service để bảo đảm quy tắc nghiệp vụ vẫn được thực thi.

Một bộ kiểm thử đầy đủ nên phân biệt:

- Chuỗi sai cú pháp: converter từ chối.
- Chuỗi đúng cú pháp nhưng không chuyển đổi được: converter từ chối với thông báo phù hợp.
- Giá trị chuyển đổi được nhưng vi phạm constraint: Bean Validation từ chối trước khi command thực thi.
- Giá trị hợp lệ về kiểu và constraint nhưng không hợp lệ trong trạng thái hệ thống: application service từ chối.
- Giá trị hợp lệ hoàn toàn: command gọi service và trả kết quả.

## 10. Quy trình quyết định trước khi chuẩn hóa

Trước khi thêm strip(), toLowerCase(), thay dấu phân cách hoặc làm tròn, hãy thực hiện các bước:

1. **Xác định loại dữ liệu.** Đây là số để tính toán, ngày giờ, mã định danh, nội dung hiển thị hay bí mật xác thực?
2. **Công bố grammar.** Giá trị có khoảng trắng không? Phân biệt hoa/thường không? Dấu thập phân là gì? Có alias nào được hỗ trợ?
3. **Chọn kiểu đích.** Dùng Integer, BigDecimal, LocalDate, Instant, enum hoặc value object phù hợp với ý nghĩa dữ liệu.
4. **Chuẩn hóa có điều kiện.** Chỉ bỏ qua khác biệt đã được định nghĩa là không có ý nghĩa.
5. **Chuyển đổi nghiêm ngặt.** Parse toàn bộ chuỗi; từ chối phần dư hoặc giá trị không rõ nghĩa.
6. **Validation.** Kiểm tra ràng buộc cấu trúc và giới hạn trước khi thực thi.
7. **Kiểm tra nghiệp vụ.** Xác minh quyền và trạng thái hệ thống trong service.
8. **Lưu dấu vết khi cần.** Nếu cần kiểm toán, giữ giá trị gốc cùng giá trị chuẩn hóa và quy tắc đã áp dụng.

Chuẩn hóa tốt làm cho dữ liệu nhất quán mà vẫn giữ đúng ý nghĩa. Nếu một phép biến đổi có thể khiến hai đầu vào khác nhau trở thành cùng một giá trị, đó là quyết định về hợp đồng dữ liệu và cần được công bố, kiểm thử và xem xét như một phần của thiết kế CLI.

## Tài liệu tham khảo

- [Spring Shell 4.0.4 — Command Syntax](https://docs.spring.io/spring-shell/reference/commands/syntax.html) — khai báo option/argument và cách Spring Shell ánh xạ tham số command.
- [Spring Shell 4.0.4 — Option Validation](https://docs.spring.io/spring-shell/reference/commands/validation.html) — Bean Validation trên tham số command trước khi thực thi.
- [Spring Shell 4.0.4 — Command Registration](https://docs.spring.io/spring-shell/reference/commands/registration.html) — đăng ký command từ bean và mô hình programmatic.
- [Spring Shell 4.0.4 API — MethodInvokerCommandAdapter](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/adapter/MethodInvokerCommandAdapter.html) — constructor nhận method, target bean, ConfigurableConversionService và Validator.
- [Spring Framework 7 — Spring Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation/convert.html) — Converter, ConverterFactory, GenericConverter và ConversionService.
- [Java SE — BigDecimal](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/BigDecimal.html) — số thập phân chính xác và scale.
- [Java SE — DateTimeFormatter](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatter.html) — định dạng và phân tích ngày giờ.
