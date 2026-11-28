# Kiểm tra đầy đủ dữ liệu trước khi áp dụng thay đổi

## 1. Thu thập dữ liệu và áp dụng thay đổi là hai giai đoạn khác nhau

Một wizard thường hỏi người dùng nhiều thông tin liên quan với nhau. Ví dụ, khi tạo một project triển khai, người dùng có thể nhập tên project, email chủ sở hữu, vùng triển khai, ngày bắt đầu và ngày kết thúc.

Mỗi component chỉ biết dữ liệu của bước hiện tại. `StringInput` có thể nhận một chuỗi, selector có thể trả về một lựa chọn, còn confirmation component nhận yes/no. Nhưng quy tắc nghiệp vụ thường phụ thuộc vào nhiều trường cùng lúc. Ví dụ:

- Tên project phải đúng định dạng và chưa được sử dụng.
- Email chủ sở hữu phải hợp lệ.
- Vùng triển khai phải được bật cho loại project đã chọn.
- Ngày bắt đầu phải đứng trước ngày kết thúc.
- Tổng hợp các trường phải thỏa chính sách triển khai hiện hành.

Vì vậy, không nên gọi service tạo hoặc cập nhật dữ liệu ngay sau khi một component riêng lẻ trả kết quả. Hãy thu thập đủ dữ liệu, kiểm tra toàn bộ bản nháp, hiển thị tất cả lỗi có thể sửa, rồi mới yêu cầu xác nhận và áp dụng thay đổi.

## 2. Luồng xử lý an toàn

Với Spring Shell 3.x, `ComponentFlow.run()` trả về `ComponentFlowResult`. Kết quả này cung cấp `ComponentContext` tổng hợp, nơi lưu dữ liệu của các component theo ID nếu `storeResult` được bật (mặc định là `true`).

Luồng đề xuất:

~~~mermaid
flowchart TD
    A[Người dùng bắt đầu wizard] --> B[ComponentFlow thu thập tất cả trường]
    B --> C[Đọc ComponentFlowResult.getContext]
    C --> D[Tạo bản nháp bất biến]
    D --> E[Kiểm tra từng trường và quy tắc liên trường]
    E --> F{Có lỗi?}
    F -->|Có| G[Hiển thị toàn bộ lỗi]
    G --> H[Cho nhập lại dữ liệu]
    H --> B
    F -->|Không| I[Hiển thị tóm tắt và hỏi xác nhận]
    I --> J{Người dùng xác nhận?}
    J -->|Không| K[Kết thúc, không thay đổi dữ liệu]
    J -->|Có| L[Service kiểm tra lại quy tắc có thẩm quyền]
    L --> M[Transaction áp dụng thay đổi]
    M --> N[Thông báo kết quả]
~~~

Điểm kiểm soát quan trọng là service ghi dữ liệu chỉ được gọi sau khi toàn bộ dữ liệu đã hợp lệ và người dùng đã xác nhận. Các bước kiểm tra trước đó nên không có tác dụng phụ.

## 3. ComponentFlow chỉ thu thập dữ liệu; ứng dụng chịu trách nhiệm kiểm tra tổng thể

Builder của `ComponentFlow` hỗ trợ các component như:

- `withStringInput(id)` để nhập văn bản.
- `withPathInput(id)` để nhập đường dẫn.
- `withConfirmationInput(id)` để nhận xác nhận.
- `withSingleItemSelector(id)` để chọn một mục.
- `withMultiItemSelector(id)` để chọn nhiều mục.

Mỗi component có thể lưu kết quả vào context chung bằng ID được truyền khi tạo component. Ví dụ, `withStringInput("projectName")` lưu kết quả dưới key `projectName`; sau khi flow hoàn tất, có thể đọc bằng `result.getContext().get("projectName", String.class)`.

`preHandler` và `postHandler` của từng component nhận context riêng của component đó. Chúng phù hợp để thiết lập message, điều chỉnh trạng thái hiển thị hoặc ghi nhận sự kiện nhẹ. Nếu cần kiểm tra nhiều trường cùng lúc, hãy lấy context tổng hợp sau `flow.run()`; không cố kiểm tra quy tắc liên trường trong post-handler của một input riêng lẻ.

## 4. Khai báo flow thu thập một bản nháp

Ví dụ dưới đây thu thập năm trường cho yêu cầu tạo project. Các lựa chọn vùng được cung cấp dưới dạng `Map`, trong đó key là nhãn hiển thị và value là mã vùng được lưu vào context.

~~~java
import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.shell.component.flow.ComponentFlow;

private ComponentFlow buildProjectFlow(ProjectDraft previous) {
    Map<String, String> regions = new LinkedHashMap<>();
    regions.put("Singapore", "ap-southeast-1");
    regions.put("Tokyo", "ap-northeast-1");
    regions.put("Sydney", "ap-southeast-2");

    return componentFlowBuilder.clone()
            .reset()
            .withStringInput("projectName")
                .name("Tên project")
                .defaultValue(previous == null ? "" : previous.projectName())
                .and()
            .withStringInput("ownerEmail")
                .name("Email chủ sở hữu")
                .defaultValue(previous == null ? "" : previous.ownerEmail())
                .and()
            .withSingleItemSelector("region")
                .name("Vùng triển khai")
                .selectItems(regions)
                .and()
            .withStringInput("startsOn")
                .name("Ngày bắt đầu (yyyy-MM-dd)")
                .defaultValue(previous == null ? "" : previous.startsOn())
                .and()
            .withStringInput("endsOn")
                .name("Ngày kết thúc (yyyy-MM-dd)")
                .defaultValue(previous == null ? "" : previous.endsOn())
                .and()
            .build();
}
~~~

`componentFlowBuilder` là `ComponentFlow.Builder` được inject từ Spring. Gọi `clone().reset()` để tạo builder riêng cho lần chạy hiện tại. Khi người dùng cần nhập lại sau khi validation thất bại, có thể truyền bản nháp trước đó vào `buildProjectFlow(...)`; các trường văn bản sẽ hiển thị giá trị cũ làm mặc định để người dùng sửa. Selector vùng được hiển thị lại để người dùng xác nhận lựa chọn.

Ví dụ dùng `selectItems(Map<String, String>)`, API có sẵn trong Spring Shell 3.4. Có thể dùng `SelectItem.of(name, item)` nếu muốn tạo danh sách item tường minh.

## 5. Đọc toàn bộ context và tạo đối tượng bản nháp

Sau khi flow chạy xong, chuyển context thành một kiểu dữ liệu rõ ràng. Không truyền `ComponentContext` sâu vào tầng nghiệp vụ vì như vậy service sẽ phụ thuộc vào giao diện terminal.

~~~java
import org.springframework.shell.component.context.ComponentContext;
import org.springframework.shell.component.flow.ComponentFlow.ComponentFlowResult;

private ProjectDraft readDraft(ComponentFlow flow) {
    ComponentFlowResult result = flow.run();
    ComponentContext<?> context = result.getContext();

    return new ProjectDraft(
            context.get("projectName", String.class),
            context.get("ownerEmail", String.class),
            context.get("region", String.class),
            context.get("startsOn", String.class),
            context.get("endsOn", String.class));
}

private record ProjectDraft(
        String projectName,
        String ownerEmail,
        String region,
        String startsOn,
        String endsOn) {
}
~~~

`ProjectDraft` là bản nháp dùng trong lớp giao diện. Nó giữ nguyên dữ liệu người dùng nhập để validation có thể báo lỗi theo từng trường. Sau khi hợp lệ, ứng dụng chuyển bản nháp thành request nghiệp vụ có kiểu ngày tháng rõ ràng.

## 6. Kiểm tra tất cả trường và quy tắc liên trường

Hàm validation nên thu thập nhiều lỗi trong một lần chạy thay vì dừng ở lỗi đầu tiên. Điều này giúp người dùng sửa nhiều trường trong cùng một lượt.

~~~java
import java.time.LocalDate;
import java.time.format.DateTimeParseException;
import java.util.ArrayList;
import java.util.List;
import java.util.Set;

private static final Set<String> ALLOWED_REGIONS = Set.of(
        "ap-southeast-1",
        "ap-northeast-1",
        "ap-southeast-2");

private List<String> validate(ProjectDraft draft) {
    List<String> errors = new ArrayList<>();

    String projectName = clean(draft.projectName());
    String ownerEmail = clean(draft.ownerEmail());
    String region = clean(draft.region());
    String startsOn = clean(draft.startsOn());
    String endsOn = clean(draft.endsOn());

    if (!projectName.matches("[a-z][a-z0-9-]{2,29}")) {
        errors.add("Tên project phải có 3-30 ký tự, bắt đầu bằng chữ thường và chỉ chứa chữ thường, số hoặc dấu gạch ngang.");
    }

    if (!ownerEmail.matches("^[^\\s@]+@[^\\s@]+\\.[^\\s@]+$")) {
        errors.add("Email chủ sở hữu không đúng định dạng.");
    }

    if (!ALLOWED_REGIONS.contains(region)) {
        errors.add("Vùng triển khai không được hỗ trợ.");
    }

    LocalDate start = parseDate(startsOn, "Ngày bắt đầu", errors);
    LocalDate end = parseDate(endsOn, "Ngày kết thúc", errors);

    if (start != null && end != null && !start.isBefore(end)) {
        errors.add("Ngày bắt đầu phải trước ngày kết thúc.");
    }

    return errors;
}

private LocalDate parseDate(String value, String field, List<String> errors) {
    try {
        return LocalDate.parse(value);
    }
    catch (DateTimeParseException | NullPointerException ex) {
        errors.add(field + " phải theo định dạng yyyy-MM-dd.");
        return null;
    }
}

private String clean(String value) {
    return value == null ? "" : value.trim();
}
~~~

Validation gồm hai nhóm:

- **Kiểm tra từng trường:** tên project, email, vùng và định dạng ngày.
- **Kiểm tra liên trường:** ngày bắt đầu phải trước ngày kết thúc.

Hàm `validate(...)` chỉ đọc bản nháp và trả danh sách lỗi. Nó không lưu project, đặt trước tài nguyên, gửi email hoặc thay đổi cấu hình. Trong ứng dụng thực tế, có thể bổ sung các kiểm tra đọc dữ liệu như tên project đã tồn tại hay vùng có đang được phép tạo project hay không; các kiểm tra này vẫn chưa thay thế việc xác nhận lại trong service ghi dữ liệu.

## 7. Hiển thị tất cả lỗi và cho người dùng nhập lại

Khi có lỗi, in toàn bộ danh sách, giữ bản nháp cũ làm giá trị mặc định và chạy lại flow. Không gọi service áp dụng thay đổi trong nhánh này.

~~~java
private ProjectDraft collectValidDraft() {
    ProjectDraft previous = null;

    while (true) {
        ProjectDraft draft = readDraft(buildProjectFlow(previous));
        List<String> errors = validate(draft);

        if (errors.isEmpty()) {
            return draft;
        }

        terminal.writer().println("Dữ liệu chưa hợp lệ:");
        errors.forEach(error -> terminal.writer().println(" - " + error));
        terminal.writer().println("Hãy nhập lại các trường cần sửa.");
        terminal.flush();

        previous = draft;
    }
}
~~~

`terminal` là JLine `Terminal` được inject vào command. Nếu người dùng nhập sai cả email và ngày, họ nhận được cả hai thông báo trong cùng lượt. Khi chạy lại, các trường văn bản được điền sẵn từ bản nháp trước để người dùng chỉ cần sửa nội dung chưa đúng.

Vòng lặp này tiếp tục đến khi bản nháp hợp lệ. Nếu muốn hỗ trợ hủy wizard, hãy bổ sung một bước lựa chọn hủy hoặc xử lý tín hiệu thoát theo quy ước của ứng dụng; không coi một giá trị mặc định rỗng là dữ liệu hợp lệ.

## 8. Chỉ hỏi xác nhận sau khi validation thành công

Confirmation nên xuất hiện sau khi tất cả kiểm tra đầu vào đã đạt. Khi đó người dùng có thể xem lại dữ liệu cuối cùng trước khi hệ thống thay đổi trạng thái.

~~~java
private boolean confirm(ProjectDraft draft) {
    terminal.writer().println("Thông tin project sẽ được tạo:");
    terminal.writer().println("Name: " + clean(draft.projectName()));
    terminal.writer().println("Owner: " + clean(draft.ownerEmail()));
    terminal.writer().println("Region: " + clean(draft.region()));
    terminal.writer().println("Start: " + clean(draft.startsOn()));
    terminal.writer().println("End: " + clean(draft.endsOn()));
    terminal.flush();

    ComponentFlow confirmationFlow = componentFlowBuilder.clone()
            .reset()
            .withConfirmationInput("confirm")
                .name("Áp dụng thay đổi này?")
                .defaultValue(false)
                .and()
            .build();

    return Boolean.TRUE.equals(confirmationFlow.run()
            .getContext().get("confirm", Boolean.class));
}
~~~

Đặt mặc định `false` để thao tác an toàn khi người dùng chỉ nhấn Enter. Nếu họ từ chối, command kết thúc mà không gọi service ghi dữ liệu.

Không nên đưa confirmation vào trước validation rồi coi câu trả lời “yes” là bằng chứng dữ liệu hợp lệ. Confirmation chỉ thể hiện ý định của người dùng; ứng dụng vẫn phải kiểm tra dữ liệu trước đó.

## 9. Chuyển bản nháp thành request nghiệp vụ và áp dụng thay đổi

Khi bản nháp hợp lệ và được xác nhận, chuyển nó thành kiểu dữ liệu nghiệp vụ. Ví dụ:

~~~java
import java.time.LocalDate;

private ProjectRequest toRequest(ProjectDraft draft) {
    return new ProjectRequest(
            clean(draft.projectName()),
            clean(draft.ownerEmail()),
            clean(draft.region()),
            LocalDate.parse(clean(draft.startsOn())),
            LocalDate.parse(clean(draft.endsOn())));
}

public record ProjectRequest(
        String projectName,
        String ownerEmail,
        String region,
        LocalDate startsOn,
        LocalDate endsOn) {
}
~~~

Phương thức command có thể kết nối các giai đoạn như sau:

~~~java
@ShellMethod(key = "project provision", value = "Tạo project sau khi kiểm tra toàn bộ dữ liệu")
public String provision() {
    ProjectDraft draft = collectValidDraft();

    if (!confirm(draft)) {
        return "Đã hủy. Không có thay đổi nào được áp dụng.";
    }

    ProjectRequest request = toRequest(draft);
    ProjectReceipt receipt = projectProvisioningService.provision(request);

    return "Đã tạo project " + receipt.projectId();
}
~~~

`ProjectProvisioningService` và `ProjectReceipt` là kiểu nghiệp vụ của ứng dụng ví dụ. Điểm quan trọng là chỉ có một vị trí gọi `provision(...)`, nằm sau khi dữ liệu hợp lệ và được xác nhận.

## 10. Kiểm tra lại quy tắc trong service ghi dữ liệu

Validation ở command cải thiện trải nghiệm người dùng, nhưng không phải hàng rào bảo vệ cuối cùng. Giữa lúc flow kiểm tra dữ liệu và lúc service lưu dữ liệu, trạng thái hệ thống có thể thay đổi. Ví dụ, tên project có thể vừa được một người dùng khác tạo hoặc vùng triển khai vừa bị quản trị viên tắt.

Service cần kiểm tra lại các quy tắc có thẩm quyền trong transaction trước khi ghi:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ProjectProvisioningService {

    private final ProjectRepository projectRepository;
    private final RegionPolicy regionPolicy;

    public ProjectProvisioningService(
            ProjectRepository projectRepository,
            RegionPolicy regionPolicy) {
        this.projectRepository = projectRepository;
        this.regionPolicy = regionPolicy;
    }

    @Transactional
    public ProjectReceipt provision(ProjectRequest request) {
        if (projectRepository.existsByProjectName(request.projectName())) {
            throw new ProjectAlreadyExistsException(request.projectName());
        }

        if (!regionPolicy.isEnabled(request.region())) {
            throw new RegionUnavailableException(request.region());
        }

        if (!request.startsOn().isBefore(request.endsOn())) {
            throw new InvalidProjectPeriodException();
        }

        Project project = Project.create(request);
        Project saved = projectRepository.save(project);
        return new ProjectReceipt(saved.getId());
    }
}
~~~

Các repository, policy, entity và exception là thành phần của ứng dụng ví dụ. Với quy tắc duy nhất như tên project, nên có thêm unique constraint ở database để bảo vệ trước race condition giữa hai request đồng thời. Transaction giúp gom các thao tác ghi liên quan; nó không tự bảo đảm mọi quy tắc nghiệp vụ nếu service không kiểm tra chúng.

## 11. Phân biệt lỗi nhập liệu và lỗi nghiệp vụ tại thời điểm ghi

Không phải lỗi nào cũng có thể phát hiện trong wizard:

| Loại lỗi | Thời điểm phát hiện | Cách xử lý |
|---|---|---|
| Thiếu tên hoặc email sai định dạng | Sau khi thu thập flow | Hiển thị lỗi theo trường và cho nhập lại. |
| Ngày bắt đầu sau ngày kết thúc | Sau khi thu thập flow | Hiển thị lỗi liên trường và cho nhập lại. |
| Project đã tồn tại | Có thể kiểm tra trước, nhưng phải kiểm tra lại khi ghi | Service từ chối và command hiển thị thông báo nghiệp vụ. |
| Vùng vừa bị vô hiệu hóa | Tại thời điểm service thực thi | Service từ chối; không áp dụng thay đổi. |
| Lỗi database hoặc lỗi hạ tầng | Trong transaction | Rollback theo transaction và báo lỗi phù hợp. |

Nếu service từ chối vì trạng thái hệ thống vừa thay đổi, không nên âm thầm bỏ qua hoặc dùng lại kết quả kiểm tra cũ. Hãy thông báo nguyên nhân và yêu cầu người dùng chạy lại wizard nếu cần.

## 12. Những lỗi thiết kế thường gặp

**Ghi dữ liệu trong postHandler của một component:** post-handler chỉ nhận context của component đó. Nếu ghi dữ liệu ở đây, những trường phía sau chưa được thu thập và kiểm tra. Hãy để handler xử lý message hoặc trạng thái giao diện; thực hiện mutation sau khi flow hoàn tất.

**Dùng `next(...)` để thay thế validation liên trường:** `next(...)` quyết định component tiếp theo dựa trên context của component hiện tại. Nó phù hợp để điều hướng nhánh wizard, nhưng không thay thế việc kiểm tra đầy đủ context tổng hợp sau `run()`.

**Dừng ở lỗi đầu tiên:** người dùng phải chạy wizard nhiều lần để phát hiện từng lỗi. Hãy gom lỗi vào danh sách và hiển thị tất cả lỗi có thể xác định cùng lúc.

**Coi confirmation là validation:** người dùng có thể xác nhận một bản nháp sai. Luôn kiểm tra trước, xác nhận sau.

**Chỉ kiểm tra ở command:** command có thể được gọi từ một đường khác hoặc dữ liệu hệ thống thay đổi sau validation. Service phải bảo vệ quy tắc nghiệp vụ tại điểm ghi.

**Đưa `ComponentContext` vào service:** service sẽ phụ thuộc Spring Shell và cấu trúc giao diện. Hãy chuyển context thành record/request thuần trước khi gọi service.

**Tạo tác dụng phụ trong hàm validate:** validation có thể chạy lại nhiều lần. Hàm này nên thuần hoặc chỉ thực hiện các truy vấn đọc; không gửi email, tạo resource, giữ chỗ hoặc ghi database.

## 13. Kiểm thử quy trình validate trước mutation

Nên kiểm tra thứ tự gọi và bảo đảm service không được gọi khi có lỗi:

1. Tất cả trường hợp lệ: flow trả request đúng và service chỉ được gọi sau confirmation.
2. Một trường sai: hiển thị lỗi và không gọi service.
3. Nhiều trường sai: hiển thị tất cả lỗi trong cùng một lượt và không gọi service.
4. Lỗi liên trường: ngày bắt đầu bằng hoặc sau ngày kết thúc bị từ chối.
5. Nhập lại: giá trị cũ được đề xuất để người dùng sửa, validation được chạy lại trên bản nháp mới.
6. Người dùng từ chối confirmation: service không được gọi.
7. Dữ liệu hợp lệ nhưng service phát hiện project đã tồn tại: mutation bị từ chối và lỗi nghiệp vụ được hiển thị.
8. Hai request tạo cùng tên đồng thời: ràng buộc duy nhất ở database bảo vệ dữ liệu.
9. Lỗi khi lưu: transaction rollback và command không báo thành công.

Trong unit test, dùng mock service để xác nhận `provision(...)` không được gọi ở mọi nhánh lỗi hoặc hủy. Trong integration test, kiểm tra dữ liệu cuối cùng trong database và các ràng buộc đồng thời.

## 14. Checklist trước khi áp dụng thay đổi

- [ ] Đã thu thập mọi trường cần thiết.
- [ ] Đã chuyển kết quả flow thành một request hoặc draft có kiểu rõ ràng.
- [ ] Đã kiểm tra định dạng và giá trị từng trường.
- [ ] Đã kiểm tra các quy tắc phụ thuộc nhiều trường.
- [ ] Đã hiển thị tất cả lỗi có thể sửa cùng lúc.
- [ ] Các bước validation không tạo tác dụng phụ.
- [ ] Người dùng đã xem lại và xác nhận dữ liệu hợp lệ.
- [ ] Service đã kiểm tra lại các quy tắc có thẩm quyền ngay trước khi ghi.
- [ ] Các thay đổi liên quan được thực hiện trong transaction phù hợp.
- [ ] Có ràng buộc ở database cho các bất biến cần bảo vệ trước request đồng thời.

## Kết luận

`ComponentFlow` giúp thu thập dữ liệu qua nhiều bước và gom kết quả vào `ComponentContext`. Để áp dụng thay đổi an toàn, hãy đợi `flow.run()` hoàn tất, chuyển context thành một bản nháp có kiểu, kiểm tra tất cả trường cùng quy tắc liên trường, hiển thị toàn bộ lỗi và cho nhập lại. Chỉ sau khi bản nháp hợp lệ mới hiển thị confirmation và gọi service ghi dữ liệu. Service vẫn phải kiểm tra lại các bất biến có thẩm quyền trong transaction vì trạng thái hệ thống có thể thay đổi sau lần validation ở giao diện.

## Tài liệu tham khảo

- [Spring Shell 3.4 – Component Flow](https://docs.spring.io/spring-shell/reference/3.4/components/flow/index.html)
- [Spring Shell 3.4 API – ComponentFlow](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/component/flow/ComponentFlow.html)
- [Spring Shell 3.4 API – ComponentFlow.Builder](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/component/flow/ComponentFlow.Builder.html)
- [Spring Shell 3.4 API – ComponentFlowResult](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/component/flow/ComponentFlow.ComponentFlowResult.html)
- [Spring Shell 3.4 API – ComponentContext](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/component/context/ComponentContext.html)
- [Spring Shell 3.4 API – StringInputSpec](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/component/flow/StringInputSpec.html)
- [Spring Shell 3.4 API – SingleItemSelectorSpec](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/component/flow/SingleItemSelectorSpec.html)
- [Spring Shell 3.4 API – ConfirmationInputSpec](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/component/flow/ConfirmationInputSpec.html)
