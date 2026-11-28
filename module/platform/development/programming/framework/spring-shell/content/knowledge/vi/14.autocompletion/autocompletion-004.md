# ValueProvider gắn với @ShellOption trong mô hình legacy 3.x

Khi người dùng nhập một option rồi nhấn Tab, Spring Shell có thể đề xuất các giá trị phù hợp để họ chọn thay vì phải nhớ và gõ toàn bộ. Ví dụ, command triển khai ứng dụng có option `--environment`; khi người dùng bắt đầu gõ `sta`, shell có thể gợi ý `staging`. Với command tìm khách hàng, shell có thể đề xuất các mã khách hàng đang hoạt động theo phần đầu vào đã nhập.

Trong mô hình annotation legacy của Spring Shell 3.x, cơ chế cung cấp giá trị gợi ý cho một tham số được thực hiện qua interface `ValueProvider`. Ta gắn lớp triển khai vào option bằng thuộc tính `valueProvider` của `@ShellOption`. Provider nhận `CompletionContext` và trả về danh sách `CompletionProposal`; Spring Shell sử dụng các proposal đó khi xử lý thao tác hoàn thành trong phiên shell tương tác.

`ValueProvider` chỉ cung cấp gợi ý cho thao tác nhập. Nó không xác nhận giá trị hợp lệ, không cấp quyền sử dụng giá trị và không thay thế validation khi command được thực thi. Command và service vẫn phải kiểm tra đầu vào thật, vì người dùng có thể tự gõ một giá trị không nằm trong danh sách hoặc gọi command từ script.

Sau bài này, bạn có thể:

- Giải thích vai trò của `ValueProvider`, `CompletionContext` và `CompletionProposal`.
- Viết provider triển khai `complete()` để đề xuất giá trị cho một option.
- Đăng ký provider thành Spring bean và gắn vào `@ShellOption`.
- Lọc đề xuất theo phần người dùng đang gõ.
- Lấy dữ liệu gợi ý từ service hoặc repository một cách hiệu quả.
- Phân biệt hoàn thành giá trị option với hoàn thành tên command và tên option.
- Kiểm tra giới hạn của `ValueProvider` trong Spring Shell 3.x và hướng chuyển đổi khi nâng cấp lên 4.x.

> Bài này chỉ dùng API legacy `@ShellComponent`, `@ShellMethod`, `@ShellOption` và `org.springframework.shell.standard.ValueProvider` của Spring Shell 3.x. Không áp dụng nguyên xi cho mô hình annotation mới hoặc Spring Shell 4.x.

## 1. ValueProvider hoạt động ở đâu?

Trong một command legacy, `@ShellOption` mô tả option gắn với tham số của phương thức. Khi option có thuộc tính `valueProvider`, Spring Shell biết lớp nào chịu trách nhiệm tạo danh sách giá trị gợi ý cho tham số đó.

Luồng xử lý khái quát:

~~~mermaid
flowchart TD
    A[Người dùng nhập command] --> B[Nhập một phần giá trị option]
    B --> C[Nhấn Tab]
    C --> D[Spring Shell tạo CompletionContext]
    D --> E[Gọi ValueProvider.complete]
    E --> F[Provider trả List CompletionProposal]
    F --> G[Shell hiển thị hoặc chèn đề xuất]
    G --> H[Người dùng chọn hoặc tiếp tục nhập]
    H --> I[Thực thi command]
    I --> J[Command và service vẫn validation đầu vào]
~~~

Các thành phần có trách nhiệm riêng:

| Thành phần | Trách nhiệm |
|---|---|
| `@ShellOption(valueProvider = ...)` | Chỉ định provider cho một tham số trong command legacy |
| `ValueProvider` | Tạo danh sách giá trị có thể gợi ý |
| `CompletionContext` | Cung cấp thông tin về buffer đang nhập, vị trí con trỏ, command và option hiện tại |
| `CompletionProposal` | Biểu diễn một giá trị gợi ý có thể được hiển thị và chèn vào dòng lệnh |
| Spring bean container | Cung cấp instance của provider cho Spring Shell |

Provider được gọi trong quá trình hoàn thành, không phải lúc command thực thi. Người dùng có thể nhấn Tab nhiều lần khi đang sửa cùng một dòng, vì vậy `complete()` cần nhanh, có thể được gọi lặp lại và không tạo side effect.

`ValueProvider` phục vụ completion trong phiên shell tương tác, nơi người dùng đang nhập và nhấn Tab. Hoàn thành command line của hệ điều hành, chẳng hạn gợi ý khi gõ `java -jar app.jar ...` trong Bash, là cơ chế riêng cần tích hợp với shell hệ điều hành qua built-in `completion` command. Không giả định đăng ký `ValueProvider` sẽ tự tạo script completion cho Bash hoặc PowerShell.

Ngoài ra, `ValueProvider` cung cấp **giá trị của option**. Việc gợi ý tên option như `--environment` thuộc cơ chế hoàn thành option name của command catalog; đây là một nhiệm vụ khác.

## 2. Hợp đồng của ValueProvider

Interface `ValueProvider` có một phương thức:

~~~java
public interface ValueProvider {
    List<CompletionProposal> complete(CompletionContext completionContext);
}
~~~

Phương thức nhận một `CompletionContext` và trả về danh sách `CompletionProposal`. Khi không có giá trị phù hợp, trả về danh sách rỗng:

~~~java
return List.of();
~~~

Không trả `null`, vì shell cần một danh sách kết quả để xử lý. Nếu provider có lỗi khi truy vấn dữ liệu, hãy xử lý theo chính sách của ứng dụng: ghi log phù hợp và trả danh sách rỗng nếu không thể đưa ra gợi ý an toàn; không biến lỗi hoàn thành thành thao tác ghi hoặc thay đổi dữ liệu.

Các kiểu quan trọng nằm trong package:

~~~java
import org.springframework.shell.CompletionContext;
import org.springframework.shell.CompletionProposal;
import org.springframework.shell.standard.ValueProvider;
~~~

`CompletionProposal` có thể được tạo đơn giản bằng constructor nhận chuỗi:

~~~java
new CompletionProposal("staging")
~~~

Chuỗi này là giá trị được đề xuất cho đầu vào. Trong các trường hợp cần thêm thông tin hiển thị, API proposal của phiên bản có thể cung cấp metadata như mô tả hoặc category; ví dụ cơ bản trong bài chỉ cần giá trị để giữ code rõ ràng.

## 3. Đăng ký provider thành Spring bean

Spring Shell cần lấy được provider từ application context. Chỉ triển khai interface rồi tham chiếu class trong annotation là chưa đủ nếu instance đó không được đăng ký thành bean.

Cách thông dụng là dùng `@Component`:

~~~java
import java.util.List;
import java.util.Locale;

import org.springframework.shell.CompletionContext;
import org.springframework.shell.CompletionProposal;
import org.springframework.shell.standard.ValueProvider;
import org.springframework.stereotype.Component;

@Component
public class EnvironmentValueProvider implements ValueProvider {

    private static final List<String> ENVIRONMENTS =
            List.of("development", "test", "staging", "production");

    @Override
    public List<CompletionProposal> complete(CompletionContext context) {
        String prefix = context.currentWordUpToCursor();
        if (prefix == null) {
            prefix = "";
        }

        String normalizedPrefix = prefix.toLowerCase(Locale.ROOT);

        return ENVIRONMENTS.stream()
                .filter(value -> value.toLowerCase(Locale.ROOT)
                        .startsWith(normalizedPrefix))
                .map(CompletionProposal::new)
                .toList();
    }
}
~~~

`@Component` đăng ký `EnvironmentValueProvider` thành bean nếu package của lớp nằm trong phạm vi component scan. Nếu dự án không dùng component scan cho package này, có thể khai báo một bean bằng `@Bean` trong lớp cấu hình.

Provider trên dùng danh sách tĩnh để minh họa. Với dữ liệu thay đổi theo môi trường, nên lấy danh sách từ một service được inject thay vì truy vấn database hoặc gọi API từ terminal trực tiếp trong provider.

## 4. Gắn provider vào @ShellOption

Sau khi provider đã là bean, tham chiếu lớp đó trong thuộc tính `valueProvider`:

~~~java
import org.springframework.shell.standard.ShellComponent;
import org.springframework.shell.standard.ShellMethod;
import org.springframework.shell.standard.ShellOption;

@ShellComponent
public class DeploymentCommands {

    @ShellMethod(key = "deploy create", value = "Tạo yêu cầu triển khai.")
    public String create(
            @ShellOption(
                    value = {"-e", "--environment"},
                    valueProvider = EnvironmentValueProvider.class,
                    help = "Môi trường triển khai.") String environment) {
        return "Đã nhận yêu cầu triển khai tới " + environment;
    }
}
~~~

Giờ người dùng có thể nhập một phần giá trị và nhấn Tab:

~~~text
shell:>deploy create --environment sta<Tab>
~~~

Provider lọc danh sách theo tiền tố `sta` và trả về `staging`. Cách hiển thị chính xác, việc tự chèn candidate hay hiển thị danh sách phụ thuộc terminal/JLine và cấu hình completion của ứng dụng.

`valueProvider` chỉ áp dụng cho tham số được đánh dấu. Nếu command có ba option cần gợi ý riêng, mỗi option có thể tham chiếu một provider tương ứng. Trong mô hình legacy, provider được gắn ở cấp tham số, vì vậy logic thường được chia theo từng option.

## 5. Đọc CompletionContext để hiểu phần người dùng đang nhập

`CompletionContext` đại diện cho trạng thái buffer tại thời điểm completion được yêu cầu. Trong Spring Shell 3.x, các thông tin hữu ích gồm:

| Phương thức | Ý nghĩa |
|---|---|
| `getWords()` | Các từ trong buffer, không bao gồm tên command |
| `getWordIndex()` | Vị trí chỉ số của từ nơi con trỏ đang đứng |
| `getPosition()` | Vị trí con trỏ trong từ hiện tại |
| `currentWord()` | Toàn bộ từ hiện tại; có thể là `null` nếu con trỏ ở sau từ cuối |
| `currentWordUpToCursor()` | Phần từ hiện tại tính từ đầu từ đến vị trí con trỏ |
| `upToCursor()` | Phần buffer từ đầu dòng đến vị trí con trỏ |
| `getCommandOption()` | Metadata option hiện tại |
| `getCommandRegistration()` | Registration của command đang được hoàn thành |

Ví dụ, khi người dùng đang nhập:

~~~text
deploy create --environment sta
~~~

`currentWordUpToCursor()` thường trả về phần đang nhập ở vị trí con trỏ, trong trường hợp này là `sta`. Provider có thể dùng chuỗi đó để lọc đề xuất.

Không nên tự phân tích toàn bộ dòng bằng cách tách chuỗi theo dấu cách nếu chỉ cần tiền tố hiện tại. Parser phải xử lý quote, escape và cú pháp option; `CompletionContext` đã cung cấp các trường liên quan để provider sử dụng. Khi cần dựa trên các từ đã nhập trước đó, hãy đọc `getWords()` và kiểm tra chỉ số/vị trí trước khi truy cập phần tử.

## 6. Gợi ý động từ service

Danh sách môi trường tĩnh phù hợp với ví dụ nhỏ. Trong ứng dụng thực tế, command có thể cần gợi ý mã khách hàng, tên project, tên branch hoặc resource đang tồn tại. Provider có thể inject service Spring để lấy dữ liệu.

Giả sử ứng dụng có service trả về các mã khách hàng đang hoạt động theo tiền tố:

~~~java
public interface CustomerQueryService {
    List<String> findActiveCodesStartingWith(String prefix, int limit);
}
~~~

Provider sử dụng service:

~~~java
import java.util.List;

import org.springframework.shell.CompletionContext;
import org.springframework.shell.CompletionProposal;
import org.springframework.shell.standard.ValueProvider;
import org.springframework.stereotype.Component;

@Component
public class CustomerCodeValueProvider implements ValueProvider {

    private final CustomerQueryService customerQueryService;

    public CustomerCodeValueProvider(CustomerQueryService customerQueryService) {
        this.customerQueryService = customerQueryService;
    }

    @Override
    public List<CompletionProposal> complete(CompletionContext context) {
        String prefix = context.currentWordUpToCursor();
        if (prefix == null) {
            prefix = "";
        }

        return customerQueryService
                .findActiveCodesStartingWith(prefix, 20)
                .stream()
                .map(CompletionProposal::new)
                .toList();
    }
}
~~~

Gắn provider vào tham số:

~~~java
import org.springframework.shell.standard.ShellComponent;
import org.springframework.shell.standard.ShellMethod;
import org.springframework.shell.standard.ShellOption;

@ShellComponent
public class CustomerCommands {

    private final CustomerService customerService;

    public CustomerCommands(CustomerService customerService) {
        this.customerService = customerService;
    }

    @ShellMethod(key = "customer show", value = "Hiển thị thông tin khách hàng.")
    public String show(
            @ShellOption(value = "--code",
                    valueProvider = CustomerCodeValueProvider.class) String code) {
        return customerService.describe(code);
    }
}
~~~

Ở đây, provider chỉ truy vấn tối đa 20 mã phù hợp. Giới hạn kết quả giúp completion không phải tải một danh sách quá lớn mỗi khi người dùng nhấn Tab. Service có thể tận dụng index, cache hoặc lọc ở database để giảm độ trễ.

### Những nguyên tắc khi truy vấn dữ liệu gợi ý

- Chỉ đọc dữ liệu; không tạo, sửa hoặc xóa bản ghi.
- Giới hạn số lượng kết quả.
- Lọc theo tiền tố để tránh trả toàn bộ danh sách.
- Tránh gọi API mạng chậm đồng bộ trong mỗi lần nhấn Tab.
- Nếu dữ liệu ít thay đổi, cân nhắc cache và thời gian hết hạn phù hợp.
- Xử lý tình huống không có quyền xem dữ liệu hoặc service tạm thời không sẵn sàng.
- Không ghi token, thông tin bí mật hoặc dữ liệu nhạy cảm vào candidate hay log.

Completion có thể được gọi nhiều lần khi người dùng di chuyển con trỏ hoặc tiếp tục gõ. Vì vậy, provider nên có chi phí thấp và không giả định mỗi lần gọi tương ứng với một command execution.

## 7. Phân biệt ValueProvider với các provider có sẵn

Spring Shell 3.x có một số lớp triển khai `ValueProvider` có sẵn:

| Provider | Mục đích |
|---|---|
| `EnumValueProvider` | Gợi ý các giá trị của kiểu enum |
| `FileValueProvider` | Gợi ý tên file cục bộ, theo đường dẫn tuyệt đối hoặc tương đối với thư mục làm việc hiện tại |
| `CommandValueProvider` | Gợi ý tên các command đã đăng ký |

Nếu hành vi có sẵn đáp ứng yêu cầu, hãy ưu tiên dùng chúng thay vì viết provider riêng. Provider tùy chỉnh phù hợp khi danh sách phụ thuộc dữ liệu ứng dụng, chính sách hoặc điều kiện riêng.

Ví dụ enum:

~~~java
public enum DeploymentRegion {
    AP_SOUTHEAST_1,
    AP_NORTHEAST_1,
    EU_WEST_1
}
~~~

Với tham số enum, `EnumValueProvider` có thể đề xuất các hằng số hợp lệ. Với option nhận file, `FileValueProvider` hỗ trợ gợi ý tên file trong filesystem cục bộ. Các provider có sẵn vẫn chỉ hỗ trợ người dùng chọn nhanh; command cần xử lý lỗi nếu file bị xóa hoặc quyền thay đổi trước lúc thực thi.

## 8. ValueProvider không phải validation

Một gợi ý chỉ là một lựa chọn thuận tiện. Người dùng vẫn có thể nhập thủ công giá trị bất kỳ:

~~~text
deploy create --environment unknown-env
~~~

Nếu `unknown-env` không hợp lệ, command phải từ chối khi thực thi. Không được giả định giá trị truyền vào chắc chắn nằm trong danh sách provider đã trả về.

Validation cần đặt tại command hoặc service, tùy quy tắc:

~~~java
public String create(String environment) {
    if (!environmentService.isSupported(environment)) {
        throw new IllegalArgumentException(
                "Môi trường không được hỗ trợ: " + environment);
    }
    deploymentService.create(environment);
    return "Đã tạo yêu cầu triển khai tới " + environment;
}
~~~

Nếu quy tắc môi trường được dùng bởi REST API, batch hoặc message consumer, hãy đặt kiểm tra trong service/domain để mọi kênh gọi đều áp dụng cùng quy tắc. Provider chỉ giúp người dùng khám phá các giá trị có thể dùng tại thời điểm nhập.

Danh sách gợi ý cũng có thể cũ. Một mã khách hàng được đề xuất lúc 10 giờ có thể bị vô hiệu hóa trước khi người dùng nhấn Enter. Service phải kiểm tra lại trạng thái tại thời điểm thực thi.

## 9. Giới hạn của mô hình legacy 3.x

Trong mô hình legacy, `ValueProvider` được khai báo trên từng `@ShellOption`. Cách này phù hợp khi mỗi option có danh sách gợi ý độc lập. Tuy nhiên, khi một option cần đề xuất dựa trên nhiều option khác, việc phối hợp dữ liệu có thể trở nên khó khăn vì provider được gắn riêng theo tham số.

Ví dụ, danh sách version triển khai có thể phụ thuộc vào project đã chọn:

~~~text
deploy create --project payments --version <Tab>
~~~

Provider cho `--version` có thể cần đọc các token trước đó trong `CompletionContext`, sau đó tự xác định project. Việc tự phân tích trạng thái command phức tạp làm code dễ phụ thuộc cú pháp nhập và khó bảo trì. Nếu completion cần phối hợp nhiều option, cân nhắc thiết kế lại command hoặc nâng cấp sang cơ chế completion tập trung.

Trong Spring Shell 3.x, mô hình programmatic `CommandRegistration` có thể cấu hình completion trực tiếp trên từng option bằng callback `.completion(...)`. Cơ chế này khác với `ValueProvider` gắn trên `@ShellOption`; không dùng lẫn hai cách trong một ví dụ rồi giả định chúng có cùng vòng đời.

## 10. Khác biệt khi nâng cấp lên Spring Shell 4.x

Spring Shell 4.x đã loại bỏ các annotation legacy như `@ShellComponent`, `@ShellMethod` và `@ShellOption`. Vì vậy, `@ShellOption(valueProvider = ...)` không còn là cách khai báo completion ở phiên bản 4.x.

Trong Spring Shell 4.x, completion được tập trung ở cấp command thông qua `CompletionProvider`. Provider nhận completion context của command, có thể xem option hiện tại và các dữ liệu liên quan để tạo đề xuất. Thiết kế này giúp hỗ trợ completion phụ thuộc nhiều option tốt hơn so với mô hình per-option của legacy 3.x.

Khi nâng cấp:

1. Thay command legacy bằng mô hình `@Command`, `@Option` và API tương ứng của 4.x.
2. Chuyển logic tạo candidate từ `ValueProvider.complete(...)` sang `CompletionProvider`.
3. Xem lại cách lấy option và trạng thái command từ completion context mới.
4. Kiểm thử lại việc quote, chèn candidate và completion theo nhiều option.
5. Không giữ import `org.springframework.shell.standard.ValueProvider` hoặc `@ShellOption` trong code 4.x.

Hãy xem migration guide và API của đúng phiên bản Spring Shell trước khi chuyển đổi; package, kiểu context và cách đăng ký completion đã thay đổi.

## 11. Kiểm thử ValueProvider

Nên kiểm thử provider riêng với các trường hợp:

| Trường hợp | Đầu vào mô phỏng | Kết quả mong đợi |
|---|---|---|
| Không nhập tiền tố | Chuỗi hiện tại rỗng | Trả danh sách giới hạn các giá trị mặc định |
| Có tiền tố khớp | `sta` | Chỉ trả các giá trị bắt đầu bằng `sta` |
| Không có giá trị khớp | `xyz` | Trả danh sách rỗng |
| Khác chữ hoa/thường | `STA` | Kết quả theo chính sách không phân biệt hoa thường của provider |
| Con trỏ ở giữa từ | Tiền tố đến vị trí con trỏ | Đề xuất dựa trên phần trước con trỏ |
| Service không khả dụng | Truy vấn phát sinh lỗi dự kiến | Provider xử lý theo chính sách, không làm phát sinh thao tác nghiệp vụ |
| Danh sách rất lớn | Nhiều nghìn candidate | Kết quả bị giới hạn và truy vấn được tối ưu |

Có thể dùng mock `CompletionContext` để kiểm thử logic lọc tiền tố mà không cần khởi chạy terminal:

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import java.util.List;

import org.springframework.shell.CompletionContext;
import org.springframework.shell.CompletionProposal;

CompletionContext context = mock(CompletionContext.class);
when(context.currentWordUpToCursor()).thenReturn("sta");

List<CompletionProposal> proposals = provider.complete(context);

assertThat(proposals)
        .extracting(CompletionProposal::value)
        .containsExactly("staging");
~~~

Ngoài unit test, hãy kiểm tra thủ công trong interactive shell: gõ một phần option rồi nhấn Tab, chọn candidate, nhấn Enter và xác nhận command nhận đúng giá trị. Unit test xác nhận logic provider; kiểm tra tương tác xác nhận parser, JLine và đăng ký bean phối hợp đúng.

## 12. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Nhấn Tab không có gợi ý | Provider chưa được đăng ký thành bean hoặc chưa gắn vào đúng tham số | Kiểm tra `@Component`/`@Bean`, component scan và `valueProvider` |
| Không tạo được provider | Constructor provider cần dependency nhưng bean chưa được cấu hình | Đăng ký dependency và provider trong application context |
| Provider chạy nhưng danh sách rỗng | Prefix lọc sai, dữ liệu không có hoặc truy vấn trả rỗng | Log số lượng kết quả ở mức debug và kiểm tra `currentWordUpToCursor()` |
| Candidate bị lặp | Nguồn dữ liệu có giá trị trùng | Loại trùng trước khi tạo `CompletionProposal` |
| Nhấn Tab làm shell chậm | Truy vấn database/API đồng bộ hoặc trả quá nhiều kết quả | Lọc, giới hạn, cache và tối ưu truy vấn |
| Giá trị được gợi ý nhưng command từ chối | Gợi ý không phải validation hoặc dữ liệu đã thay đổi | Kiểm tra lại ở service khi thực thi |
| Provider không hoạt động sau nâng cấp 4.x | Legacy `@ShellOption` và `ValueProvider` đã bị loại bỏ | Chuyển sang `CompletionProvider` của mô hình 4.x |
| Giá trị có dấu cách được chèn sai | Candidate tự chứa quote/escape không phù hợp | Trả giá trị thuần; để parser và completion xử lý quoting theo API |

## 13. Checklist triển khai

- Dự án đang dùng Spring Shell 3.x và mô hình legacy annotation.
- Provider triển khai đúng `org.springframework.shell.standard.ValueProvider`.
- Phương thức `complete(CompletionContext)` trả về `List<CompletionProposal>`.
- Provider được đăng ký thành Spring bean.
- `@ShellOption(valueProvider = ProviderClass.class)` được đặt trên đúng tham số.
- Candidate phản ánh đúng giá trị cần chèn, không chỉ là nhãn hiển thị.
- Danh sách được lọc theo phần người dùng đang gõ và giới hạn số lượng.
- Provider nhanh, chỉ đọc và an toàn khi được gọi nhiều lần.
- Command/service vẫn validation giá trị khi thực thi.
- Đã kiểm tra trong interactive shell với thao tác Tab thực tế.
- Đã xác định kế hoạch chuyển sang `CompletionProvider` nếu nâng cấp lên 4.x.

## 14. Bài tập thực hành

Tạo command `deploy create` với các option:

1. `--environment`: gợi ý `development`, `test`, `staging`, `production` bằng `EnvironmentValueProvider`.
2. `--region`: gợi ý các vùng triển khai bằng một provider riêng hoặc `EnumValueProvider`.
3. `--project`: gợi ý mã project đang hoạt động từ `ProjectQueryService`.
4. Giới hạn danh sách project ở 20 kết quả và lọc theo tiền tố đang nhập.
5. Đăng ký từng provider thành Spring bean và gắn đúng vào `@ShellOption`.
6. Nhấn Tab với tiền tố có và không có kết quả; thử chữ hoa/thường.
7. Tự gõ một environment không được hỗ trợ và xác nhận command/service vẫn từ chối.
8. Viết unit test cho logic lọc và integration test hoặc kiểm tra thủ công cho luồng Tab hoàn chỉnh.
9. Giải thích những khó khăn nếu `--region` phải phụ thuộc vào `--environment`, và đề xuất cách tổ chức completion khi nâng cấp lên Spring Shell 4.x.

## Tài liệu tham khảo

- [Spring Shell 3.3 – Completion](https://docs.spring.io/spring-shell/reference/3.3/completion.html): `ValueProvider`, `CompletionContext`, `CompletionProposal` và cách gắn provider với `@ShellOption`.
- [Spring Shell 3.3 – ValueProvider API](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/standard/ValueProvider.html): hợp đồng `complete(CompletionContext)`.
- [Spring Shell 3.3 – CompletionContext API](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/CompletionContext.html): thông tin buffer, từ hiện tại, vị trí con trỏ, command và option.
- [Spring Shell 3.3 – ShellOption API](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/standard/ShellOption.html): thuộc tính `valueProvider` của annotation legacy.
- [Spring Shell 4 Migration Guide](https://github.com/spring-projects/spring-shell/wiki/v4-migration-guide): thay đổi từ completion theo từng option sang `CompletionProvider` ở cấp command.
