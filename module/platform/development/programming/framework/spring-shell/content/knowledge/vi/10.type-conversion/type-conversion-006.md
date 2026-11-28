# Spring ConversionService và phạm vi tích hợp theo phiên bản

Khi người dùng nhập một command, Spring Shell nhận các token dưới dạng văn bản. Để gọi method có tham số kiểu ProjectId, LocalDate, Duration hoặc một kiểu miền nghiệp vụ riêng, shell cần chuyển chuỗi đầu vào sang kiểu Java tương ứng. Spring Framework cung cấp cơ chế chuyển đổi này qua ConversionService và các SPI như Converter, ConverterFactory và GenericConverter.

Spring Shell tích hợp cơ chế chuyển đổi của Spring vào quá trình phân giải tham số command. Tuy nhiên, phạm vi tích hợp thay đổi theo thế hệ API và cách command được đăng ký. Spring Shell 3.x có ShellConversionServiceSupplier và các argument resolver; Spring Shell 4.x dùng mô hình command mới và adapter thực thi method với ConfigurableConversionService. Vì vậy, khi thêm converter tùy chỉnh, cần xác định đúng pipeline mà phiên bản ứng dụng đang sử dụng.

Bài học này giải thích vai trò của ConversionService, cách tạo converter cho kiểu dữ liệu riêng, cách Spring Shell sử dụng converter khi binding tham số và những điểm khác nhau giữa Spring Shell 3.x, 4.0.0–4.0.2 và 4.0.3 trở lên.

## 1. Vì sao command cần chuyển đổi kiểu?

Một command line chủ yếu chứa văn bản. Ví dụ:

~~~text
project show --id 1042
report export --since 2026-01-01 --format csv
task schedule --delay 15m
~~~

Trong khi đó, method Java có thể khai báo tham số bằng kiểu mạnh:

~~~java
public String show(ProjectId id) { ... }

public String export(LocalDate since, ReportFormat format) { ... }

public String schedule(Duration delay) { ... }
~~~

Nếu không có cơ chế chuyển đổi, mỗi command phải tự đọc chuỗi, gọi parseLong, LocalDate.parse, tự kiểm tra enum hoặc viết logic phân tích thời lượng. Cách đó làm lặp mã và khiến việc xử lý lỗi không thống nhất.

ConversionService cung cấp một điểm truy cập chung để chuyển một giá trị từ kiểu nguồn sang kiểu đích. Trong Spring Shell, service này được dùng trong quá trình phân giải giá trị option và argument trước khi gọi method command.

Có thể hình dung luồng xử lý:

~~~mermaid
flowchart TD
    A["Người dùng nhập command"] --> B["Parser tách command, option, argument"]
    B --> C["Resolver lấy giá trị văn bản"]
    C --> D["ConversionService tìm converter phù hợp"]
    D --> E{"Chuyển đổi thành công?"}
    E -- "Không" --> F["Báo lỗi chuyển đổi"]
    E -- "Có" --> G["Giá trị có kiểu Java"]
    G --> H["Validation"]
    H --> I{"Hợp lệ?"}
    I -- "Không" --> J["Báo lỗi validation"]
    I -- "Có" --> K["Gọi command method"]
~~~

Parser xác định token thuộc command và tham số nào. ConversionService biến giá trị văn bản thành kiểu Java. Validation kiểm tra giá trị sau khi chuyển đổi có đáp ứng ràng buộc hay không. Cuối cùng, Spring Shell mới gọi method command.

## 2. ConversionService của Spring Framework

ConversionService thuộc package org.springframework.core.convert. Đây là API dùng để kiểm tra và thực hiện chuyển đổi giữa các kiểu dữ liệu.

Các phương thức thường dùng:

~~~java
public interface ConversionService {

    boolean canConvert(Class<?> sourceType, Class<?> targetType);

    <T> T convert(Object source, Class<T> targetType);

    boolean canConvert(
            TypeDescriptor sourceType,
            TypeDescriptor targetType);

    Object convert(
            Object source,
            TypeDescriptor sourceType,
            TypeDescriptor targetType);
}
~~~

Hai nhóm phương thức đầu làm việc với Class. Hai nhóm sau dùng TypeDescriptor để giữ thêm thông tin về kiểu generic, trường, method parameter hoặc annotation liên quan đến dữ liệu.

Ví dụ sử dụng:

~~~java
ConversionService conversionService = ...;

boolean supported = conversionService.canConvert(
        String.class,
        Integer.class);

Integer quantity = conversionService.convert("25", Integer.class);
~~~

Nếu service có converter phù hợp, kết quả là số nguyên 25. Nếu không có converter phù hợp hoặc dữ liệu không thể chuyển đổi, thao tác có thể ném exception.

### 2.1. ConversionService và ConverterRegistry

ConversionService tập trung vào việc kiểm tra và thực hiện chuyển đổi. Việc đăng ký converter thuộc về ConverterRegistry.

Nhiều implementation của Spring như GenericConversionService đồng thời triển khai cả hai vai trò. Vì vậy, một đối tượng có thể được sử dụng để convert dữ liệu và đăng ký thêm converter.

Một số implementation thường gặp:

| Implementation | Vai trò |
|---|---|
| DefaultConversionService | Cung cấp tập converter mặc định cho các kiểu phổ biến |
| GenericConversionService | Bộ máy chuyển đổi tổng quát, cho phép đăng ký converter |
| FormattingConversionService | Mở rộng cơ chế chuyển đổi với formatter và parser |
| ApplicationConversionService | Tập hợp converter và formatter thường dùng trong ứng dụng Spring Boot |

Không nên tạo một ConversionService mới cho mỗi lần gọi command. Spring thiết kế service này theo hướng stateless để có thể được khởi tạo khi ứng dụng bắt đầu và dùng chung giữa nhiều luồng.

### 2.2. Chuyển đổi có hỗ trợ kiểu generic

TypeDescriptor hữu ích khi kiểu đích không chỉ là một class đơn giản. Ví dụ, ứng dụng có thể cần chuyển một danh sách chuỗi thành danh sách số nguyên.

~~~java
List<String> rawValues = List.of("10", "20", "30");

TypeDescriptor sourceType = TypeDescriptor.collection(
        List.class,
        TypeDescriptor.valueOf(String.class));

TypeDescriptor targetType = TypeDescriptor.collection(
        List.class,
        TypeDescriptor.valueOf(Integer.class));

Object converted = conversionService.convert(
        rawValues,
        sourceType,
        targetType);
~~~

Nếu service có converter cho phần tử và converter tổng hợp cho collection, kết quả có thể là List<Integer>. TypeDescriptor giúp Spring biết kiểu phần tử thay vì chỉ thấy cả hai phía đều là List.

## 3. Các SPI để xây dựng converter

Spring Framework cung cấp nhiều mức mở rộng. Nên bắt đầu với SPI đơn giản nhất đáp ứng được yêu cầu.

### 3.1. Converter<S, T>

Converter<S, T> dùng khi cần chuyển một kiểu nguồn cụ thể sang một kiểu đích cụ thể.

~~~java
public interface Converter<S, T> {
    T convert(S source);
}
~~~

Ví dụ chuyển chuỗi thành ProjectId:

~~~java
public record ProjectId(long value) {

    public ProjectId {
        if (value <= 0) {
            throw new IllegalArgumentException(
                    "Project ID must be greater than zero");
        }
    }
}
~~~

~~~java
@Component
public class StringToProjectIdConverter
        implements Converter<String, ProjectId> {

    @Override
    public ProjectId convert(String source) {
        try {
            return new ProjectId(Long.parseLong(source.trim()));
        }
        catch (NumberFormatException ex) {
            throw new IllegalArgumentException(
                    "Project ID must be a positive integer", ex);
        }
    }
}
~~~

Converter này nhận một chuỗi như 1042 và tạo ProjectId(1042). Chuỗi rỗng, chữ hoặc số không hợp lệ sẽ khiến quá trình chuyển đổi thất bại với thông báo rõ ràng.

Theo hợp đồng của Spring, source truyền vào Converter.convert không phải null. Converter có thể ném exception unchecked khi giá trị nguồn không hợp lệ; IllegalArgumentException là cách phù hợp để báo dữ liệu không thể chuyển đổi. Implementation nên an toàn khi được gọi đồng thời và không giữ trạng thái thay đổi giữa các lần convert.

### 3.2. ConverterFactory<S, R>

ConverterFactory phù hợp khi một kiểu nguồn có thể chuyển sang nhiều kiểu đích thuộc cùng một hệ phân cấp.

Ví dụ, chuyển chuỗi thành nhiều loại enum. Thay vì viết riêng một converter cho String -> ReportFormat, String -> UserRole và String -> TaskStatus, có thể tạo một factory cho hệ enum:

~~~java
public interface ConverterFactory<S, R> {
    <T extends R> Converter<S, T> getConverter(Class<T> targetType);
}
~~~

Factory nhận class đích để tạo converter phù hợp. Spring có thể sử dụng cùng một factory cho nhiều enum type khác nhau.

Nên dùng ConverterFactory khi logic chuyển đổi chung cho một họ kiểu đích. Nếu chỉ có một cặp kiểu cụ thể, Converter<S, T> đơn giản và dễ đọc hơn.

### 3.3. GenericConverter

GenericConverter linh hoạt hơn. Nó có thể hỗ trợ nhiều cặp kiểu nguồn/đích và nhận TypeDescriptor ở cả hai phía.

~~~java
public interface GenericConverter {

    Set<ConvertiblePair> getConvertibleTypes();

    Object convert(
            Object source,
            TypeDescriptor sourceType,
            TypeDescriptor targetType);
}
~~~

Ví dụ, một converter tổng quát có thể xử lý nhiều định dạng định danh khác nhau hoặc cần đọc metadata từ annotation trên tham số đích.

~~~java
@Component
public class StringToProjectIdGenericConverter
        implements GenericConverter {

    @Override
    public Set<ConvertiblePair> getConvertibleTypes() {
        return Set.of(
                new ConvertiblePair(String.class, ProjectId.class));
    }

    @Override
    public Object convert(
            Object source,
            TypeDescriptor sourceType,
            TypeDescriptor targetType) {

        return new ProjectId(
                Long.parseLong(((String) source).trim()));
    }
}
~~~

Trong ví dụ này chỉ có một cặp kiểu, vì vậy Converter<String, ProjectId> sẽ ngắn gọn hơn. Chỉ chọn GenericConverter khi cần khả năng tổng quát của nó.

### 3.4. ConditionalGenericConverter

Nếu converter chỉ phù hợp trong một số điều kiện, có thể triển khai ConditionalGenericConverter. Interface này bổ sung phương thức matches(sourceType, targetType) để quyết định converter có áp dụng cho cặp kiểu cụ thể hay không.

Ví dụ, một converter có thể chỉ áp dụng khi tham số đích được đánh dấu bằng annotation riêng. Điều này hữu ích khi cùng một kiểu Java có nhiều cách biểu diễn tùy theo ngữ cảnh.

Không nên dùng điều kiện phức tạp nếu một Converter riêng đã đủ rõ ràng. Quy tắc chọn converter càng đơn giản thì việc kiểm thử và bảo trì càng dễ.

## 4. Converter mặc định và kiểu dữ liệu phổ biến

Spring có sẵn nhiều converter cho các kiểu thường gặp. Tùy implementation và phiên bản, các nhóm kiểu phổ biến bao gồm:

| Kiểu nguồn | Kiểu đích | Ví dụ |
|---|---|---|
| String | Integer, Long, Double | "42" thành 42 |
| String | Boolean | "true" thành true |
| String | Enum | "CSV" thành ReportFormat.CSV |
| String | Character | "A" thành ký tự A |
| String | Locale | "vi-VN" thành locale tương ứng |
| Collection | Collection | Chuyển đổi từng phần tử khi có converter phù hợp |
| Array | Array | Chuyển đổi phần tử của mảng |

Đừng mặc định mọi chuỗi ngày giờ đều được parse theo một định dạng tùy ý. Các kiểu ngày giờ có thể cần định dạng hoặc converter phù hợp với format đầu vào. Nếu CLI yêu cầu ngày theo dạng ISO, hãy ghi rõ cú pháp đó trong help và kiểm thử với dữ liệu thực tế.

Ví dụ command nhận enum:

~~~java
public enum ReportFormat {
    CSV,
    JSON,
    XML
}
~~~

~~~java
@ShellMethod("Export a report.")
public String export(ReportFormat format) {
    return "Export format: " + format;
}
~~~

Người dùng có thể nhập giá trị enum theo quy tắc chuyển đổi mà service hỗ trợ. Cần xác minh chính xác cách xử lý chữ hoa/chữ thường trên phiên bản dự án; nếu CLI cần chấp nhận nhiều dạng, có thể viết converter riêng để chuẩn hóa đầu vào.

## 5. Spring Shell sử dụng ConversionService ở đâu?

Spring Shell không chuyển toàn bộ dòng command trực tiếp thành object. Parser trước tiên nhận diện tên command, option và argument. Sau đó, lớp phân giải tham số lấy giá trị văn bản và yêu cầu ConversionService chuyển thành kiểu của method parameter.

Ví dụ:

~~~java
@ShellComponent
public class ProjectCommands {

    @ShellMethod("Show a project by ID.")
    public String show(
            @ShellOption(value = "--id") ProjectId id) {
        return "Project ID: " + id.value();
    }
}
~~~

Khi người dùng nhập:

~~~text
shell:> project show --id 1042
~~~

Spring Shell nhận giá trị văn bản 1042, xác định tham số đích là ProjectId, rồi tìm converter String -> ProjectId. Nếu chuyển đổi thành công, method nhận object ProjectId. Command không cần tự gọi Long.parseLong.

Nếu không có converter phù hợp, hoặc converter từ chối giá trị, Spring Shell không thể tạo tham số theo kiểu yêu cầu và command method không được gọi.

### 5.1. Phân biệt parsing, conversion và validation

| Giai đoạn | Công việc | Ví dụ |
|---|---|---|
| Parsing | Tách tên command, option và argument | Nhận diện --id 1042 |
| Conversion | Chuyển chuỗi thành kiểu Java | "1042" thành ProjectId |
| Validation | Kiểm tra ràng buộc dữ liệu | ID phải lớn hơn 0 |
| Business logic | Thực hiện nghiệp vụ | Tìm project trong repository |

Converter nên xử lý việc chuyển biểu diễn dữ liệu sang kiểu đích. Không nên biến converter thành nơi thực hiện toàn bộ nghiệp vụ.

Ví dụ, StringToProjectIdConverter chỉ nên parse số và tạo value object. Việc project có tồn tại hay người dùng có quyền truy cập project hay không thuộc service hoặc validation nghiệp vụ.

## 6. Phạm vi tích hợp trong Spring Shell 3.x

Spring Shell 3.x có mô hình annotation legacy như @ShellComponent, @ShellMethod và @ShellOption. Trong pipeline này, argument resolver sử dụng ConversionService để chuyển giá trị chuỗi đã phân giải sang kiểu tham số method.

API 3.1.x thể hiện rõ quan hệ này:

- AbstractArgumentMethodArgumentResolver nhận một ConversionService trong constructor và dùng nó để chuyển giá trị String sang kiểu tham số đích.
- OptionMethodArgumentResolver cũng nhận ConversionService.
- ParameterResolverAutoConfiguration tạo bộ argument resolver dựa trên ShellConversionServiceSupplier.
- ShellConversionServiceSupplier là interface cung cấp ConversionService dành riêng cho Spring Shell.

Vì vậy, trong Spring Shell 3.x, cần phân biệt ConversionService dùng cho shell argument binding với các điểm sử dụng conversion khác trong cùng Spring ApplicationContext.

### 6.1. Đăng ký Converter dưới dạng Spring bean

Tài liệu Spring Shell 3.0 mô tả cách tùy biến conversion bằng cách đưa bean thuộc loại Converter, GenericConverter hoặc ConverterFactory vào ApplicationContext. Cơ chế shell-specific conversion service sẽ sử dụng các converter phù hợp để xử lý tham số command.

Ví dụ:

~~~java
@Component
public class StringToProjectIdConverter
        implements Converter<String, ProjectId> {

    @Override
    public ProjectId convert(String source) {
        return new ProjectId(Long.parseLong(source.trim()));
    }
}
~~~

Command legacy có thể khai báo trực tiếp kiểu ProjectId:

~~~java
@ShellComponent
public class ProjectCommands {

    @ShellMethod("Show a project.")
    public String show(
            @ShellOption(value = "--id") ProjectId projectId) {
        return "Project ID: " + projectId.value();
    }
}
~~~

Với cấu hình Spring Shell 3.x mặc định, converter được đăng ký như một bean để shell có thể sử dụng. Hãy xác minh bằng một kiểm thử shell thực tế thay vì chỉ kiểm tra converter có được Spring tạo bean hay không.

### 6.2. ShellConversionServiceSupplier

ShellConversionServiceSupplier thuộc package org.springframework.shell.config và cung cấp một ConversionService dành cho shell.

Trong Spring Shell 3.1.x, auto-configuration dùng supplier này để tạo các argument resolver. Nếu cần thay đổi cách shell cung cấp conversion service, có thể xem xét cung cấp implementation riêng của interface này.

Khi thay thế supplier mặc định, cần bảo đảm conversion service mới vẫn có các converter cơ bản mà command đang sử dụng. Nếu tạo một service rỗng và chỉ thêm converter tùy chỉnh, các chuyển đổi chuẩn như số, boolean hoặc enum có thể không còn hoạt động như trước.

Không nên override supplier chỉ để thêm một converter đơn lẻ nếu cấu hình mặc định đã tự nhận converter bean. Hãy kiểm tra hành vi hiện tại trước, sau đó chỉ thay đổi supplier khi thật sự cần kiểm soát tập converter hoặc cách khởi tạo service.

### 6.3. CommandParser trong mô hình đăng ký bằng mã

Spring Shell 3.1.x còn cung cấp CommandParser.of(conversionService, registrations, config). Điều này cho thấy parser programmatic cũng nhận ConversionService để xử lý dữ liệu theo metadata của CommandRegistration.

Ví dụ khái quát:

~~~java
CommandParser parser = CommandParser.of(
        conversionService,
        commandRegistrations,
        parserConfig);
~~~

Nếu ứng dụng tự tạo parser hoặc command runtime, hãy truyền đúng conversion service mà ứng dụng muốn sử dụng. Một parser tự tạo với service khác có thể cho kết quả khác với shell runtime mặc định.

## 7. Phạm vi tích hợp trong Spring Shell 4.x

Spring Shell 4.x đã loại bỏ các annotation legacy như @ShellComponent, @ShellMethod và @ShellOption. Command được khai báo bằng @Command, tham số dùng @Option hoặc @Argument.

Với Spring Shell 4.0.3, MethodInvokerCommandAdapter nhận một ConfigurableConversionService cùng Validator để chuyển đổi và xác thực tham số method. Do đó, conversion vẫn thuộc cơ chế Spring Framework nhưng được gắn với pipeline thực thi command mới.

Ví dụ:

~~~java
package com.example.customercli.command;

import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.Option;
import org.springframework.stereotype.Component;

@Component
public class ProjectCommands {

    @Command(name = "project show", description = "Show a project")
    public String show(
            @Option(longName = "id", required = true) ProjectId projectId) {
        return "Project ID: " + projectId.value();
    }
}
~~~

Converter vẫn là một Spring bean:

~~~java
@Component
public class StringToProjectIdConverter
        implements Converter<String, ProjectId> {

    @Override
    public ProjectId convert(String source) {
        return new ProjectId(Long.parseLong(source.trim()));
    }
}
~~~

Trong Spring Shell 4.0.3, release notes ghi nhận một lỗi khiến custom converter không hoạt động với command khai báo bằng @Command và xác nhận lỗi này đã được sửa. Vì vậy, nếu ứng dụng dùng custom converter với annotation command, cần kiểm tra phiên bản cụ thể và ưu tiên kiểm thử trên 4.0.3 trở lên.

Không nên lấy ví dụ import hoặc cấu hình từ 3.x rồi áp dụng nguyên trạng cho 4.x. Package annotation, command adapter và cơ chế khởi tạo shell đã thay đổi. ConversionService của Spring Framework vẫn là nền tảng, nhưng điểm tích hợp với Spring Shell phụ thuộc thế hệ API.

## 8. Phân biệt Spring ConversionService với Spring Boot property conversion

Spring Boot cũng sử dụng conversion khi bind giá trị cấu hình bên ngoài vào @ConfigurationProperties. Tuy nhiên, đây là một pipeline khác với việc chuyển tham số command trong Spring Shell.

Ví dụ, một converter có thể được đánh dấu @ConfigurationPropertiesBinding để phục vụ cấu hình:

~~~java
@Component
@ConfigurationPropertiesBinding
public class StringToRegionConverter
        implements Converter<String, Region> {

    @Override
    public Region convert(String source) {
        return Region.valueOf(source.trim().toUpperCase(Locale.ROOT));
    }
}
~~~

Annotation @ConfigurationPropertiesBinding chỉ ra phạm vi dùng cho configuration properties binding. Không nên xem annotation này là một cách thay thế cho việc kiểm tra shell conversion pipeline.

Spring Boot có thể yêu cầu bean tên conversionService rất sớm trong quá trình khởi động để bind cấu hình. Vì thế, conversion service dùng cho property binding cần tránh phụ thuộc vào các bean chưa khởi tạo hoặc các dịch vụ nặng.

| Nơi sử dụng | Mục đích | Điểm cần kiểm tra |
|---|---|---|
| Spring Framework ConversionService | Chuyển đổi kiểu trong container và khi gọi API trực tiếp | Bean/service đang được inject |
| Spring Boot property binding | Chuyển giá trị cấu hình sang kiểu của @ConfigurationProperties | Bean conversionService, converter binding và thời điểm khởi tạo |
| Spring Shell 3.x | Chuyển option/argument thành tham số command | ShellConversionServiceSupplier và argument resolver |
| Spring Shell 4.x | Chuyển tham số command method | ConfigurableConversionService trong method adapter và phiên bản Spring Shell |

Một converter có thể được dùng ở nhiều nơi nếu được đăng ký vào đúng registry tương ứng. Nhưng việc một bean converter tồn tại trong ApplicationContext không đủ để kết luận mọi pipeline conversion đều sử dụng nó theo cùng cách.

## 9. Chọn SPI phù hợp với yêu cầu

| Nhu cầu | SPI nên chọn | Ví dụ |
|---|---|---|
| Một cặp kiểu nguồn và đích | Converter<S, T> | String -> ProjectId |
| Nhiều kiểu đích cùng một hệ phân cấp | ConverterFactory<S, R> | String -> các enum |
| Nhiều cặp kiểu và cần TypeDescriptor | GenericConverter | Chuyển đổi dựa trên generic metadata |
| Converter chỉ áp dụng khi đủ điều kiện | ConditionalGenericConverter | Chỉ convert khi tham số có annotation |
| Định dạng nhập/xuất theo locale | Formatter<T> trong formatting registry phù hợp | Ngày tháng hoặc số theo locale |

Ưu tiên Converter cho trường hợp thông thường. GenericConverter và ConditionalGenericConverter có nhiều khả năng hơn nhưng cũng khiến logic đăng ký và lựa chọn phức tạp hơn.

Nếu cần định dạng dữ liệu theo locale, hãy xem xét Formatter và FormattingConversionService. Không nên nhầm formatter với converter cơ bản: formatter thường có cả hai chiều parse và print, còn converter tập trung vào chuyển đổi một chiều giữa hai kiểu.

## 10. Thiết kế converter an toàn và dễ bảo trì

Một converter được gọi trong lúc Spring Shell chuẩn bị tham số cho command. Vì vậy, converter nên nhẹ, xác định và không tạo tác dụng phụ.

### 10.1. Chỉ chuyển đổi biểu diễn dữ liệu

Converter nên biến chuỗi thành kiểu dữ liệu:

~~~text
"1042" -> ProjectId(1042)
~~~

Không nên thực hiện truy vấn repository trong converter:

~~~java
// Không nên: converter truy cập database để tải entity
Project project = projectRepository.findById(Long.parseLong(source))
        .orElseThrow(...);
~~~

Nếu converter truy cập database, việc parse một tham số có thể trở thành thao tác I/O, phụ thuộc transaction và gây lỗi khó dự đoán. Thay vào đó, hãy convert thành ProjectId, sau đó để service tìm project:

~~~java
@Service
public class ProjectService {

    private final ProjectRepository repository;

    public ProjectService(ProjectRepository repository) {
        this.repository = repository;
    }

    public Project find(ProjectId id) {
        return repository.findById(id.value())
                .orElseThrow(() ->
                        new IllegalArgumentException("Project not found"));
    }
}
~~~

### 10.2. Chuẩn hóa đầu vào có chủ đích

Nếu muốn chấp nhận khoảng trắng đầu/cuối hoặc không phân biệt chữ hoa/chữ thường, hãy chuẩn hóa rõ ràng trong converter:

~~~java
String normalized = source.trim().toUpperCase(Locale.ROOT);
~~~

Không nên tự động xóa ký tự hoặc biến đổi chuỗi theo cách làm thay đổi ý nghĩa. Với mã định danh có phân biệt hoa/thường, giữ nguyên case có thể là yêu cầu nghiệp vụ.

### 10.3. Thông báo lỗi phải giúp người dùng sửa lệnh

Thay vì để lỗi kỹ thuật như NumberFormatException xuất hiện trực tiếp, converter có thể ném IllegalArgumentException với thông báo ngắn:

~~~java
throw new IllegalArgumentException(
        "Project ID must be a positive integer");
~~~

Người dùng có thể hiểu cần nhập số nguyên dương. Tránh đưa thông tin nội bộ hoặc stack trace dài vào thông báo lỗi thông thường.

### 10.4. Giữ converter stateless và thread-safe

Spring có thể dùng chung conversion service giữa nhiều command và nhiều luồng. Vì vậy:

- Không giữ giá trị đầu vào của lần convert trước trong field mutable.
- Không thay đổi registry trong lúc command đang chạy.
- Không dùng biến static làm cache không được đồng bộ.
- Nếu cần cache, chọn cơ chế có giới hạn và thread-safe.
- Không giữ tài nguyên mở như stream hoặc connection sau khi convert.

## 11. Conversion không thay thế validation

Một chuỗi có thể chuyển đổi thành kiểu Java nhưng vẫn không hợp lệ về nghiệp vụ.

Ví dụ:

- "0" chuyển thành ProjectId(0) nếu constructor cho phép, nhưng ID phải lớn hơn 0.
- "2026-02-31" không phải ngày hợp lệ nên parse thất bại.
- "999999" là số nguyên hợp lệ nhưng không tồn tại project tương ứng.
- "admin" có thể chuyển thành enum Role.ADMIN, nhưng người dùng hiện tại không được phép cấp quyền đó.

Nên phân chia trách nhiệm:

1. Converter xác định chuỗi có biểu diễn được kiểu đích không.
2. Constructor hoặc value object bảo vệ bất biến cơ bản của kiểu.
3. Bean Validation kiểm tra constraint của tham số hoặc object.
4. Service kiểm tra sự tồn tại, quyền và quy tắc nghiệp vụ.

Không nên dùng converter để kiểm tra quyền hoặc quyết định trạng thái nghiệp vụ.

## 12. Kiểm thử converter và tích hợp Spring Shell

Một converter nên được kiểm thử độc lập trước khi đưa vào command.

### 12.1. Unit test cho converter

~~~java
class StringToProjectIdConverterTests {

    private final StringToProjectIdConverter converter =
            new StringToProjectIdConverter();

    @Test
    void convertsPositiveInteger() {
        ProjectId result = converter.convert("1042");

        assertThat(result.value()).isEqualTo(1042);
    }

    @Test
    void rejectsNonNumericValue() {
        assertThatThrownBy(() -> converter.convert("abc"))
                .isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void rejectsZero() {
        assertThatThrownBy(() -> converter.convert("0"))
                .isInstanceOf(IllegalArgumentException.class);
    }
}
~~~

Unit test xác minh logic chuyển đổi, nhưng chưa xác nhận Spring Shell đã dùng converter đó.

### 12.2. Kiểm thử ConversionService

Nếu đang kiểm tra service cụ thể, có thể xác minh khả năng chuyển đổi:

~~~java
assertThat(conversionService.canConvert(
        String.class,
        ProjectId.class)).isTrue();

ProjectId projectId = conversionService.convert(
        "1042",
        ProjectId.class);

assertThat(projectId.value()).isEqualTo(1042);
~~~

Cần lấy đúng service mà ứng dụng muốn kiểm tra. Nếu inject một ConversionService tổng quát của Spring nhưng shell dùng shell-specific service khác, test này chưa chứng minh command runtime sẽ chuyển đổi được.

### 12.3. Integration test qua shell

Với Spring Shell 4.x, dùng @ShellTest và ShellTestClient để gửi command qua pipeline thực tế:

~~~java
@ShellTest
@ContextConfiguration(classes = CustomerCliApplication.class)
class ProjectCommandConversionTests {

    @Autowired
    private ShellTestClient client;

    @Test
    void convertsProjectIdForCommandParameter() throws Exception {
        ShellScreen screen = client.sendCommand(
                "project show --id 1042");

        ShellAssertions.assertThat(screen)
                .containsText("Project ID: 1042");
    }
}
~~~

Test tích hợp cần xác minh:

- Converter bean được phát hiện.
- Shell conversion pipeline nhận converter.
- Tham số command được binding thành đúng kiểu.
- Command method nhận đúng giá trị.
- Giá trị sai tạo thông báo lỗi phù hợp.
- Hành vi giống nhau khi chạy ở chế độ tương tác và non-interactive nếu ứng dụng hỗ trợ cả hai.

Với Spring Shell 3.x, dùng bộ công cụ test của phiên bản đó và bảo đảm test thực sự đi qua argument resolver. Không chỉ gọi trực tiếp converter.convert() rồi kết luận tích hợp shell đã đúng.

## 13. Ma trận kiểm thử theo phiên bản

| Phiên bản | Mô hình command | Điểm tích hợp conversion | Việc cần xác minh |
|---|---|---|---|
| Spring Shell 3.0.x | @ShellComponent, @ShellMethod | Spring ConversionService trong method argument resolver | Converter bean có được đưa vào shell conversion service |
| Spring Shell 3.1.x–3.4.x | Legacy annotation và mô hình @Command/registration theo phiên bản | ShellConversionServiceSupplier, resolver và parser | Đúng supplier, đúng parser, converter hoạt động với kiểu tham số |
| Spring Shell 4.0.0–4.0.2 | Annotation mới @Command, @Option, @Argument | ConfigurableConversionService của method command adapter | Có thể gặp lỗi tích hợp custom converter với @Command |
| Spring Shell 4.0.3 trở lên | Annotation mới | Method adapter dùng ConfigurableConversionService | Lỗi custom converter với @Command đã được ghi nhận là sửa trong 4.0.3; vẫn cần test theo dependency thực tế |

Một vài điểm cần nhớ:

- Spring Shell 3.1.x có ShellConversionServiceSupplier để cung cấp service dành riêng cho shell.
- Spring Shell 4.x loại bỏ annotation legacy; dùng annotation mới trong package org.springframework.shell.core.command.annotation.
- Release Spring Shell 4.0.3 ghi nhận sửa lỗi custom converter không hoạt động với @Command annotations.
- Spring Boot property binding và Spring Shell command argument binding là hai điểm sử dụng conversion khác nhau.
- Khi nâng phiên bản Spring Shell, cần chạy lại integration test cho converter tùy chỉnh.

## 14. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Command nhận kiểu mặc định hoặc lỗi không tìm thấy converter | Converter chưa được đăng ký vào service mà shell sử dụng | Kiểm tra converter bean và shell-specific service |
| ConversionService.canConvert() trả true nhưng command vẫn lỗi | Đang kiểm tra service khác với service của shell | Dùng ShellTestClient để kiểm tra pipeline thực |
| Converter hoạt động với legacy annotation nhưng không hoạt động với @Command | Khác biệt phiên bản hoặc lỗi tích hợp | Kiểm tra Spring Shell 4.0.3 trở lên |
| Boot bind property thành công nhưng command không convert được | Hai pipeline conversion khác nhau | Kiểm tra shell supplier và command adapter |
| Converter ném lỗi khó hiểu | Không chuẩn hóa hoặc không xử lý dữ liệu sai | Ném IllegalArgumentException với thông báo rõ |
| Chuyển đổi làm phát sinh truy vấn database | Converter đang chứa nghiệp vụ | Chuyển việc tra cứu sang service |
| Collection không convert như mong đợi | Thiếu converter phần tử hoặc metadata generic | Kiểm tra TypeDescriptor và converter tổng hợp |
| Converter hoạt động không ổn định khi nhiều command chạy | Converter có trạng thái mutable hoặc không thread-safe | Thiết kế converter stateless |
| Định dạng ngày giờ không nhất quán | Chưa xác định format đầu vào hoặc locale | Dùng converter/formatter có format rõ ràng |
| Dùng @ConfigurationPropertiesBinding nhưng shell không nhận converter | Annotation thuộc pipeline property binding | Đăng ký và kiểm thử theo shell conversion pipeline |

## 15. Bài thực hành: chuyển đổi ProjectId trong command

Tạo một ứng dụng Spring Shell có kiểu miền ProjectId và command:

~~~text
project show --id 1042
~~~

Yêu cầu:

1. Tạo ProjectId dưới dạng record hoặc value object.
2. Tạo Converter<String, ProjectId>.
3. Đăng ký converter thành Spring bean.
4. Khai báo command nhận tham số ProjectId.
5. Xác minh giá trị hợp lệ được chuyển đổi.
6. Xác minh chuỗi không phải số tạo lỗi conversion rõ ràng.
7. Xác minh ID bằng 0 hoặc số âm bị từ chối.
8. Chuyển việc tìm project sang ProjectService.
9. Viết unit test cho converter.
10. Viết integration test qua shell để xác nhận pipeline thật.

Kịch bản mong đợi:

~~~text
shell:> project show --id 1042
Project ID: 1042

shell:> project show --id abc
Project ID must be a positive integer

shell:> project show --id 0
Project ID must be greater than zero
~~~

Sau đó chạy cùng test trên phiên bản Spring Shell mà dự án đang sử dụng. Nếu ứng dụng nâng cấp từ 3.x lên 4.x, hãy cập nhật annotation và kiểm tra lại custom converter trên phiên bản 4.0.3 trở lên.

## 16. Checklist khi tích hợp ConversionService

- [ ] Xác định kiểu nguồn và kiểu đích cần chuyển đổi.
- [ ] Ưu tiên Converter<S, T> nếu chỉ có một cặp kiểu.
- [ ] Chọn ConverterFactory cho một họ kiểu đích.
- [ ] Chỉ dùng GenericConverter khi cần nhiều cặp kiểu hoặc TypeDescriptor.
- [ ] Giữ converter stateless, thread-safe và không thực hiện I/O.
- [ ] Đăng ký converter trong ApplicationContext đúng cách.
- [ ] Xác định shell-specific conversion service của phiên bản Spring Shell.
- [ ] Không mặc định Boot conversionService và shell conversion service là cùng một instance.
- [ ] Phân biệt conversion, validation và business logic.
- [ ] Kiểm tra custom converter qua command integration test.
- [ ] Xác minh hành vi với đúng annotation model của phiên bản.
- [ ] Kiểm tra release note khi nâng cấp Spring Shell.
- [ ] Với Spring Shell 4.x, xác minh custom converter trên 4.0.3 trở lên.

## 17. Kết luận

ConversionService là API chung của Spring Framework để chuyển đổi giá trị giữa các kiểu dữ liệu. Các SPI Converter, ConverterFactory, GenericConverter và ConditionalGenericConverter cho phép mở rộng tập chuyển đổi khi command cần nhận kiểu miền nghiệp vụ.

Spring Shell sử dụng conversion trong quá trình binding option và argument vào tham số method. Ở Spring Shell 3.x, ShellConversionServiceSupplier và các argument resolver là điểm tích hợp quan trọng. Ở Spring Shell 4.x, method command adapter nhận ConfigurableConversionService; release 4.0.3 đã sửa lỗi custom converter không hoạt động với annotation @Command.

Điều quan trọng là kiểm tra đúng service mà shell thực sự sử dụng. Việc một converter bean tồn tại hoặc một ConversionService khác trong Spring Boot chuyển đổi được dữ liệu chưa đủ chứng minh command runtime hoạt động. Hãy xác minh bằng integration test qua shell, giữ converter tập trung vào chuyển đổi và để validation cùng nghiệp vụ ở đúng lớp.

## Tài liệu tham khảo

- [Spring Framework Reference: Spring Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation/convert.html)
- [Spring Shell 3.0 Reference: Customizing Arguments Conversion](https://docs.spring.io/spring-shell/docs/3.0.0-M1/site/reference/htmlsingle/)
- [Spring Shell 3.1 API: ShellConversionServiceSupplier](https://docs.spring.io/spring-shell/docs/3.1.x/api/org/springframework/shell/config/ShellConversionServiceSupplier.html)
- [Spring Shell 3.1 API: SpringShellAutoConfiguration](https://docs.spring.io/spring-shell/docs/3.1.x/api/org/springframework/shell/boot/SpringShellAutoConfiguration.html)
- [Spring Shell 3.1 API: AbstractArgumentMethodArgumentResolver](https://docs.spring.io/spring-shell/docs/3.1.x/api/org/springframework/shell/support/AbstractArgumentMethodArgumentResolver.html)
- [Spring Shell 3.1 API: OptionMethodArgumentResolver](https://docs.spring.io/spring-shell/docs/3.1.x/api/org/springframework/shell/command/annotation/support/OptionMethodArgumentResolver.html)
- [Spring Shell 3.1 API: CommandParser](https://docs.spring.io/spring-shell/docs/3.1.x/api/org/springframework/shell/command/CommandParser.html)
- [Spring Shell 4.0.3 API: Command annotations](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/annotation/package-summary.html)
- [Spring Shell 4.0.3 API: MethodInvokerCommandAdapter](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/adapter/MethodInvokerCommandAdapter.html)
- [Spring Shell 4.0.3 release notes](https://github.com/spring-projects/spring-shell/releases)
- [Spring Shell v4 Migration Guide](https://github.com/spring-projects/spring-shell/wiki/v4-migration-guide)
- [Spring Boot 3.1.3 Reference: Properties Conversion](https://docs.spring.io/spring-boot/docs/3.1.3/reference/htmlsingle/)

