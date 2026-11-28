# ConfirmationInput cho lựa chọn xác nhận

Khi command sắp thực hiện một thao tác có tác động lớn, ứng dụng có thể hỏi người dùng xác nhận trước khi tiếp tục. Spring Shell 3.x cung cấp `ConfirmationInput`, một thành phần tương tác đơn giản với lựa chọn có hoặc không. Kết quả là một giá trị Boolean để command quyết định có gọi nghiệp vụ hay hủy thao tác.

Ví dụ phù hợp gồm xóa môi trường, ghi đè file, thu hồi quyền, hủy đơn hàng hoặc áp dụng cấu hình lên hệ thống thật. Với hành động có thể gây mất dữ liệu, nên đặt mặc định là `false` để người dùng phải chủ động xác nhận.

## 1. ConfirmationInput là gì?

`ConfirmationInput` thuộc package `org.springframework.shell.component`. Thành phần này đặt một câu hỏi xác nhận dạng yes/no và trả về `Boolean`. Nó phù hợp khi command cần hỏi một quyết định nhị phân ngay trong phiên shell tương tác.

| Thành phần | Vai trò |
|---|---|
| `ConfirmationInput` | Hiển thị câu hỏi và nhận lựa chọn xác nhận |
| `Terminal` | Cung cấp terminal để đọc và hiển thị tương tác |
| `name` | Tên hoặc nội dung nhận diện câu hỏi được hiển thị |
| `defaultValue` | Lựa chọn mặc định: `true` hoặc `false` |
| `ConfirmationInputContext` | Context truyền vào khi chạy và chứa kết quả |
| `getResultValue()` | Lấy kết quả Boolean sau khi component kết thúc |

Thành phần này chỉ trả lời người dùng có đồng ý hay không. Nó không tự xóa dữ liệu, kiểm tra quyền, xác thực tên môi trường hoặc gọi service. Command vẫn chịu trách nhiệm xử lý kết quả và thực hiện nghiệp vụ đúng thứ tự.

## 2. Lấy các dependency cần thiết

Trong mô hình legacy annotation của Spring Shell 3.1.x, lớp command có thể kế thừa `AbstractShellComponent`. Lớp cơ sở này cung cấp các thành phần mà `ConfirmationInput` cần:

- `getTerminal()` trả về terminal của shell.
- `getResourceLoader()` cung cấp resource loader cho template.
- `getTemplateExecutor()` cung cấp bộ thực thi template.

Các import chính:

~~~java
import org.springframework.shell.component.ConfirmationInput;
import org.springframework.shell.component.ConfirmationInput.ConfirmationInputContext;
import org.springframework.shell.standard.AbstractShellComponent;
import org.springframework.shell.standard.ShellComponent;
import org.springframework.shell.standard.ShellMethod;
import org.springframework.shell.standard.ShellOption;
~~~

`ConfirmationInput` cần terminal để nhận thao tác của người dùng. Sau khi tạo component, ví dụ chính thức của Spring Shell cũng gắn `ResourceLoader` và `TemplateExecutor` trước khi gọi `run(...)`, để component tải và dựng giao diện từ template có sẵn.

## 3. Tạo một câu hỏi xác nhận

Constructor thường dùng nhận terminal, tên câu hỏi và giá trị mặc định:

~~~java
ConfirmationInput confirmation = new ConfirmationInput(
        getTerminal(),
        "Bạn có muốn tiếp tục?",
        false);
~~~

Tham số cuối là `defaultValue`:

- `true`: lựa chọn mặc định là đồng ý.
- `false`: lựa chọn mặc định là không đồng ý.

Với thao tác xóa hoặc ghi đè, dùng `false`. Với thao tác ít rủi ro và có thể đảo ngược, ứng dụng có thể chọn mặc định khác nếu phù hợp với quy trình.

Sau khi tạo component, cấu hình resource loader và template executor rồi chạy:

~~~java
confirmation.setResourceLoader(getResourceLoader());
confirmation.setTemplateExecutor(getTemplateExecutor());

ConfirmationInputContext context =
        confirmation.run(ConfirmationInputContext.empty());

Boolean accepted = context.getResultValue();
~~~

`run(...)` bắt đầu vòng tương tác, hiển thị trạng thái của câu hỏi và trả về `ConfirmationInputContext` sau khi hoàn tất. `getResultValue()` trả về lựa chọn Boolean. Context cũng cung cấp `defaultValue` và `model` để template hoặc renderer có thể đọc trạng thái.

## 4. Dùng kết quả để bảo vệ thao tác xóa

Ví dụ sau hỏi xác nhận trước khi xóa một môi trường. Service chỉ được gọi khi kết quả là `true`:

~~~java
@ShellComponent
public class EnvironmentCommands extends AbstractShellComponent {

    private final EnvironmentService environmentService;

    public EnvironmentCommands(EnvironmentService environmentService) {
        this.environmentService = environmentService;
    }

    @ShellMethod(
            key = "environment delete",
            value = "Xóa một môi trường sau khi xác nhận.")
    public String delete(
            @ShellOption(value = "--name") String environmentName) {

        ConfirmationInput confirmation = new ConfirmationInput(
                getTerminal(),
                "Xác nhận xóa môi trường " + environmentName + "?",
                false);

        confirmation.setResourceLoader(getResourceLoader());
        confirmation.setTemplateExecutor(getTemplateExecutor());

        ConfirmationInputContext context =
                confirmation.run(ConfirmationInputContext.empty());

        if (!Boolean.TRUE.equals(context.getResultValue())) {
            return "Đã hủy thao tác xóa môi trường " + environmentName + ".";
        }

        environmentService.delete(environmentName);
        return "Đã xóa môi trường " + environmentName + ".";
    }
}
~~~

Quy trình thực thi:

1. Parser nhận `--name` và truyền tên môi trường vào command.
2. Command hiển thị câu hỏi xác nhận với mặc định `false`.
3. Người dùng chọn đồng ý hoặc từ chối.
4. Nếu kết quả không phải `true`, command trả thông báo hủy và không gọi service.
5. Nếu kết quả là `true`, command mới gọi `environmentService.delete(...)`.

`Boolean.TRUE.equals(...)` giúp nhánh quyết định an toàn khi giá trị trả về có thể là `null`: chỉ giá trị `true` mới cho phép thao tác tiếp tục. Đây là cách phù hợp cho các thao tác có side effect khó đảo ngược.

## 5. Chọn giá trị mặc định phù hợp

Giá trị mặc định ảnh hưởng trực tiếp đến cách người dùng xác nhận. Hãy chọn theo mức độ rủi ro của hành động:

| Thao tác | Giá trị mặc định gợi ý | Lý do |
|---|---|---|
| Xóa môi trường | `false` | Có thể làm mất tài nguyên hoặc dữ liệu |
| Ghi đè file cấu hình | `false` | Có thể thay thế nội dung hiện tại |
| Thu hồi quyền truy cập | `false` | Có thể làm gián đoạn người dùng hoặc dịch vụ |
| Hủy đơn hàng đã xác nhận | `false` | Có thể ảnh hưởng quy trình kinh doanh |
| Mở trang trợ giúp hoặc xem trước | `true` có thể phù hợp | Hành động không thay đổi dữ liệu |

Không nên chọn mặc định `true` chỉ để giảm số lần nhấn phím. Người dùng có thể chấp nhận giá trị mặc định mà không đọc kỹ câu hỏi; với hành động nguy hiểm, mặc định từ chối giúp giảm nguy cơ thao tác nhầm.

## 6. Dùng ConfirmationInput trong ComponentFlow

Khi cần nhiều bước tương tác, có thể ghép xác nhận với các component khác bằng `ComponentFlow`. Spring Shell 3.1.3 minh họa `withConfirmationInput(id)` trong builder cùng với các component nhập chuỗi, chọn đường dẫn và selector.

~~~java
ComponentFlow flow = componentFlowBuilder.clone()
        .reset()
        .withStringInput("environment")
            .name("Tên môi trường")
            .and()
        .withConfirmationInput("confirmDelete")
            .name("Xác nhận xóa môi trường?")
            .and()
        .build();

ComponentFlow.ComponentFlowResult result = flow.run();
~~~

Mỗi component có một ID để flow nhận diện. Thứ tự khai báo là thứ tự chạy thông thường; có thể dùng hàm `next(...)` trên component hỗ trợ điều hướng để chọn bước kế tiếp dựa trên kết quả trước đó. `flow.run()` trả về `ComponentFlowResult` để command xử lý kết quả của toàn bộ luồng.

Với một câu hỏi đơn giản, tạo `ConfirmationInput` trực tiếp thường ngắn gọn hơn. Dùng `ComponentFlow` khi cần kết hợp nhiều bước nhập liệu hoặc điều hướng giữa các bước.

## 7. Phân biệt xác nhận với option Boolean

Một option Boolean như `--yes` và `ConfirmationInput` phục vụ hai tình huống khác nhau:

| Cách nhận lựa chọn | Phù hợp khi |
|---|---|
| `ConfirmationInput` | Người dùng đang ở terminal tương tác và cần trả lời tại thời điểm command chạy |
| Option `--yes` | Script, CI/CD hoặc người gọi command đã quyết định trước và cần chạy không tương tác |

`ConfirmationInput` mở vòng đọc đầu vào của terminal. Không nên gọi nó trong một tác vụ non-interactive hoặc script tự động vì không có người dùng để trả lời và tiến trình có thể chờ đầu vào. Với quy trình tự động, hãy thiết kế command yêu cầu cờ xác nhận rõ ràng như `--yes`, kiểm tra cờ trước khi thực hiện side effect và trả lỗi hướng dẫn nếu cờ chưa được cung cấp.

Không nên tự động coi việc thiếu input là đồng ý. Nếu không có câu trả lời hợp lệ, thao tác cần dừng lại.

## 8. Những lưu ý khi thiết kế câu hỏi

**Nêu rõ hành động và đối tượng.** Câu hỏi `Bạn có chắc chắn?` không cho biết điều gì sẽ xảy ra. Câu `Xác nhận xóa môi trường staging?` cụ thể hơn.

**Đặt câu hỏi ngay trước side effect.** Không hỏi xác nhận quá sớm rồi thực hiện nhiều bước khác trước khi xóa; trạng thái có thể thay đổi trong khoảng thời gian đó.

**Kiểm tra điều kiện nghiệp vụ trước khi hỏi.** Xác thực tên môi trường, quyền của người dùng và trạng thái hiện tại trước khi yêu cầu xác nhận. Câu hỏi xác nhận không thay thế validation hoặc authorization.

**Không lặp lại thao tác sau khi từ chối.** Nhánh từ chối nên trả thông báo rõ ràng và kết thúc command mà không gọi service.

**Không coi xác nhận là cơ chế bảo mật.** `ConfirmationInput` chỉ ghi nhận lựa chọn của người đang dùng terminal. Nó không chứng minh danh tính, quyền truy cập hoặc ý định của một người cụ thể.

## 9. Kiểm thử command có xác nhận

Nên kiểm tra cả hai nhánh quyết định và xác minh service không bị gọi khi người dùng từ chối:

| Kịch bản | Kết quả mong đợi |
|---|---|
| Người dùng xác nhận `true` | Service được gọi đúng một lần với đúng đối tượng |
| Người dùng chọn `false` | Command trả thông báo hủy; service không được gọi |
| Giá trị kết quả là `null` | Command không thực hiện side effect |
| Mặc định là `false` | Câu hỏi bắt đầu với lựa chọn mặc định không đồng ý |
| Tên đối tượng không hợp lệ | Validation từ chối trước khi thực hiện thao tác |
| Chạy non-interactive mà không có `--yes` | Command dừng và yêu cầu xác nhận tường minh; không chờ terminal input |

Có thể tách phần quyết định thành một phương thức nhỏ để unit test mà không cần terminal. Sau đó, kiểm thử tương tác trên terminal hoặc bằng test support của Spring Shell để xác nhận component được hiển thị và kết quả được chuyển vào đúng nhánh.

## 10. Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Component không hiển thị đúng template | Chưa đặt `ResourceLoader` hoặc `TemplateExecutor` | Cấu hình cả hai trước `run(...)` |
| Không đọc được lựa chọn | Chưa gọi `run(...)` hoặc chưa lấy `getResultValue()` | Chạy component và đọc kết quả từ context |
| Thao tác vẫn xảy ra khi người dùng từ chối | Service được gọi trước khi kiểm tra Boolean | Chỉ gọi service trong nhánh xác nhận `true` |
| Hành động nguy hiểm được chấp nhận ngay | Giá trị mặc định là `true` | Đặt mặc định `false` |
| Script tự động bị chờ vô hạn | Command gọi component tương tác khi không có người trả lời | Dùng option xác nhận tường minh như `--yes` cho non-interactive |
| Câu hỏi khó hiểu | Nội dung chỉ hỏi chung chung | Ghi rõ hành động và đối tượng sẽ bị tác động |
| Dùng xác nhận thay cho kiểm tra quyền | Nhầm lựa chọn đồng ý với authorization | Kiểm tra quyền trong service hoặc security layer trước side effect |

## 11. Khác biệt package khi nâng lên Spring Shell 4.x

Bài học này dùng API thành phần tương tác của Spring Shell 3.x:

~~~java
import org.springframework.shell.component.ConfirmationInput;
~~~

Trong Spring Shell 4.x, component JLine được chuyển sang package `org.springframework.shell.jline.tui.component` và module JLine được tách khỏi `spring-shell-core`. Ứng dụng cần dùng đúng dependency JLine và package của phiên bản 4.x:

~~~java
import org.springframework.shell.jline.tui.component.ConfirmationInput;
~~~

Đừng trộn `ConfirmationInput` của package 3.x với component context hoặc lớp hỗ trợ của package 4.x. Khi nâng cấp, cập nhật import, dependency và chạy lại kiểm thử tương tác trên đúng terminal runner mà ứng dụng sử dụng.

## 12. Quy trình triển khai

1. Xác định thao tác cần người dùng xác nhận và kiểm tra xem có thể đảo ngược hay không.
2. Chọn câu hỏi nêu rõ hành động cùng đối tượng bị tác động.
3. Tạo `ConfirmationInput` với `Terminal`, nội dung câu hỏi và giá trị mặc định.
4. Gắn `ResourceLoader` và `TemplateExecutor`.
5. Gọi `run(ConfirmationInputContext.empty())` và đọc `getResultValue()`.
6. Chỉ gọi service khi kết quả là `true`; nếu từ chối, trả thông báo hủy.
7. Với script và CI/CD, dùng option xác nhận tường minh thay vì mở prompt tương tác.
8. Kiểm thử cả nhánh đồng ý, từ chối, mặc định và môi trường non-interactive.

## 13. Tổng kết

`ConfirmationInput` là component yes/no của Spring Shell 3.x. Nó nhận terminal, tên câu hỏi và giá trị mặc định, sau đó chạy với `ConfirmationInputContext` để trả về một giá trị Boolean. Command cần cấu hình resource loader và template executor, đọc kết quả bằng `getResultValue()` rồi mới quyết định có thực hiện nghiệp vụ hay không.

Với thao tác phá hủy dữ liệu hoặc khó đảo ngược, nên mặc định `false`, kiểm tra `Boolean.TRUE` trước side effect và trả thông báo rõ ràng khi người dùng từ chối. Component này dành cho tương tác terminal; script tự động nên dùng option xác nhận tường minh như `--yes`. Khi nâng lên Spring Shell 4.x, cập nhật package component sang module JLine tương ứng.

## Tài liệu tham khảo

- [Spring Shell 3.1.3 Reference Documentation — Confirmation](https://docs.spring.io/spring-shell/docs/3.1.3/docs/index.html) — mục 8.2.5 Confirmation, ví dụ tạo component, chạy context và lấy kết quả.
- [Spring Shell 3.1.x ConfirmationInput API](https://docs.spring.io/spring-shell/docs/3.1.x/api/org/springframework/shell/component/package-summary.html) — package chứa `ConfirmationInput` và `ConfirmationInputContext`.
- [Spring Shell 3.1.x AbstractShellComponent API](https://docs.spring.io/spring-shell/docs/3.1.x/api/org/springframework/shell/standard/AbstractShellComponent.html) — truy cập `Terminal`, `ResourceLoader` và `TemplateExecutor`.
- [Spring Shell 3.1.3 Reference Documentation — Component Flow](https://docs.spring.io/spring-shell/docs/3.1.3/docs/index.html) — mục 8.1 Flow, ví dụ `withConfirmationInput(...)` trong luồng tương tác.
- [Spring Shell 4.0.2 Confirmation Documentation](https://docs.spring.io/spring-shell/reference/components/ui/confirmation.html) — cách sử dụng component xác nhận trong nhánh 4.x.
- [Spring Shell 4.x Migration Guide](https://github.com/spring-projects/spring-shell/wiki/v4-migration-guide) — thay đổi module JLine và dependency khi nâng từ 3.x lên 4.x.
