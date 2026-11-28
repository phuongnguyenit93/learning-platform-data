# MultiItemSelector cho nhiều lựa chọn

Khi một command cần người dùng chọn nhiều giá trị từ một danh sách, nhập một chuỗi phân tách bằng dấu phẩy thường dễ sai và khó khám phá. Spring Shell 3.x cung cấp `MultiItemSelector` để hiển thị danh sách tương tác, cho phép di chuyển qua các mục, đánh dấu nhiều mục và xác nhận tập lựa chọn.

`MultiItemSelector` là component terminal thuộc package `org.springframework.shell.component`. Nó nhận một `Terminal`, danh sách item, tên hiển thị và comparator tùy chọn; sau khi chạy, component trả về `MultiItemSelectorContext` chứa các item đã chọn. Bài viết hướng dẫn cách tạo item, chạy selector trong command, đọc kết quả có kiểu, xử lý hủy và các trường hợp biên.

## 1. Khi nào nên dùng MultiItemSelector?

Multi-item selection phù hợp khi người dùng cần chọn một tập con từ danh sách có sẵn, ví dụ:

- Chọn nhiều quyền cần gán cho một tài khoản.
- Chọn nhiều module cần bật trong một lần triển khai.
- Chọn nhiều file hoặc tác vụ cần đưa vào hàng đợi.
- Chọn nhiều môi trường hoặc nhóm tài nguyên để áp dụng một thao tác.
- Chọn nhiều mục cấu hình để xuất báo cáo.

Nếu chỉ có một lựa chọn, `SingleItemSelector` đơn giản hơn. Nếu dữ liệu chỉ có vài giá trị và người dùng đã biết chúng, một option dạng list hoặc enum có thể đủ. `MultiItemSelector` phù hợp khi cần khám phá danh sách trực tiếp trên terminal và chọn nhiều item bằng thao tác tương tác.

## 2. Các kiểu dữ liệu của MultiItemSelector

Khai báo tổng quát của component:

```java
MultiItemSelector<T, I>
```

Trong đó:

- `T` là kiểu dữ liệu nghiệp vụ được lưu trong mỗi item, ví dụ `String`, `Permission` hoặc `DeploymentTarget`.
- `I` là kiểu item hiển thị và tương tác. Kiểu này phải triển khai `Nameable`, `Matchable`, `Enableable`, `Selectable` và `Itemable<T>`.
- `SelectorItem<T>` là implementation có sẵn, đáp ứng các interface trên và có factory method `of(...)` để tạo item.

Các thành phần chính:

| Thành phần | Vai trò |
|---|---|
| `Terminal` | Nhận input bàn phím và render giao diện |
| `List<I>` | Danh sách item người dùng có thể duyệt |
| `name` | Tiêu đề hoặc tên của selector |
| `Comparator<I>` | Thứ tự sắp xếp item; có thể truyền `null` nếu không cần comparator riêng |
| `MultiItemSelectorContext<T,I>` | Trạng thái và kết quả sau khi component chạy |

`MultiItemSelector` kế thừa `AbstractSelectorComponent`, vì vậy có thêm các khả năng chung như đặt resource loader, template executor, renderer, giới hạn số item hiển thị và handler trước/sau khi chạy.

## 3. Tạo danh sách SelectorItem

`SelectorItem.of(name, item)` tạo item có tên hiển thị và giá trị nghiệp vụ. Ví dụ danh sách quyền:

```java
import java.util.List;

import org.springframework.shell.component.support.SelectorItem;

List<SelectorItem<String>> permissions = List.of(
        SelectorItem.of("Read reports", "reports:read"),
        SelectorItem.of("Export reports", "reports:export"),
        SelectorItem.of("Manage users", "users:manage"),
        SelectorItem.of("Manage settings", "settings:manage")
);
```

Hai giá trị trong mỗi item có mục đích khác nhau:

- `name` là nhãn dễ đọc được hiển thị trong danh sách.
- `item` là giá trị được trả về cho command sau khi người dùng chọn.

Nên dùng mã nghiệp vụ ổn định làm `item`, chẳng hạn permission code hoặc ID. Không nên dùng nhãn hiển thị làm định danh nếu nhãn có thể đổi theo ngôn ngữ hoặc quy tắc sản phẩm.

### Trạng thái enabled và selected ban đầu

Factory method thứ hai nhận thêm hai cờ:

```java
SelectorItem.of(name, item, enabled, selected)
```

| Tham số | Ý nghĩa |
|---|---|
| `enabled` | `true` nếu người dùng có thể thay đổi trạng thái chọn của item |
| `selected` | `true` nếu item được đánh dấu chọn ngay khi selector bắt đầu |

Ví dụ:

```java
List<SelectorItem<String>> permissions = List.of(
        SelectorItem.of("Read reports", "reports:read", true, true),
        SelectorItem.of("Export reports", "reports:export", true, false),
        SelectorItem.of("Manage users", "users:manage", false, false)
);
```

Trong ví dụ này, `Read reports` được chọn sẵn, `Export reports` chưa được chọn nhưng có thể thay đổi, còn `Manage users` bị vô hiệu hóa. Giá trị `selected` chỉ là trạng thái ban đầu của giao diện; service vẫn phải kiểm tra lại quy tắc nghiệp vụ khi nhận kết quả.

## 4. Chạy MultiItemSelector trong command

Một cách đơn giản trong Spring Shell 3.x là tạo command bean kế thừa `AbstractShellComponent`. Lớp cơ sở này cung cấp `getTerminal()`, `getResourceLoader()` và `getTemplateExecutor()` để khởi tạo component.

```java
import java.util.List;
import java.util.stream.Collectors;

import org.springframework.shell.component.MultiItemSelector;
import org.springframework.shell.component.MultiItemSelector.MultiItemSelectorContext;
import org.springframework.shell.component.support.SelectorItem;
import org.springframework.shell.standard.AbstractShellComponent;
import org.springframework.shell.standard.ShellComponent;
import org.springframework.shell.standard.ShellMethod;

@ShellComponent
public class PermissionCommands extends AbstractShellComponent {

    @ShellMethod(key = "permission select", value = "Select multiple permissions")
    public String selectPermissions() {
        List<SelectorItem<String>> items = List.of(
                SelectorItem.of("Read reports", "reports:read"),
                SelectorItem.of("Export reports", "reports:export"),
                SelectorItem.of("Manage users", "users:manage"),
                SelectorItem.of("Manage settings", "settings:manage")
        );

        MultiItemSelector<String, SelectorItem<String>> selector =
                new MultiItemSelector<>(getTerminal(), items, "Choose permissions", null);
        selector.setResourceLoader(getResourceLoader());
        selector.setTemplateExecutor(getTemplateExecutor());

        MultiItemSelectorContext<String, SelectorItem<String>> context =
                selector.run(MultiItemSelectorContext.empty());

        if (!context.isResult()) {
            return "Permission selection was cancelled.";
        }

        List<String> selected = context.getResultItems().stream()
                .map(SelectorItem::getItem)
                .collect(Collectors.toList());

        if (selected.isEmpty()) {
            return "No permission selected.";
        }

        return "Selected permissions: " + String.join(", ", selected);
    }
}
```

Ví dụ dùng `Collectors.toList()`; với Java 17 có thể thay bằng `.toList()` nếu muốn.

Các bước khởi tạo quan trọng:

1. Tạo danh sách `SelectorItem`.
2. Khởi tạo `MultiItemSelector` với terminal, danh sách, tiêu đề và comparator.
3. Gắn `ResourceLoader` và `TemplateExecutor` của Spring Shell để component tải template mặc định.
4. Gọi `run(MultiItemSelectorContext.empty())` để mở giao diện và nhận context kết quả.
5. Kiểm tra `isResult()` trước khi đọc và sử dụng lựa chọn.

## 5. Thao tác trong danh sách nhiều lựa chọn

Selector hiển thị các item và trạng thái đã chọn. Người dùng di chuyển con trỏ, bật/tắt trạng thái của item hiện tại rồi xác nhận tập lựa chọn.

Các thao tác bàn phím thường dùng trong giao diện selector:

| Phím | Hành động |
|---|---|
| Mũi tên lên/xuống | Di chuyển con trỏ giữa các item |
| Space | Bật hoặc tắt trạng thái chọn của item đang đứng |
| Enter | Xác nhận tập lựa chọn |
| Phím thoát của component (thường là Esc) | Rời thao tác mà không xác nhận kết quả |

Key map và cách hiển thị hướng dẫn có thể phụ thuộc template, JLine và terminal. Hãy thử trên terminal mục tiêu của ứng dụng và để người dùng nhìn thấy hướng dẫn phím khi giao diện được mở.

`enabled=false` khiến item không thể được chọn hoặc bỏ chọn bằng thao tác thông thường. Điều này hữu ích khi muốn hiển thị các lựa chọn bị khóa để người dùng hiểu vì sao chúng không thể thay đổi.

## 6. Đọc kết quả từ MultiItemSelectorContext

Sau khi component kết thúc, context cung cấp nhiều cách truy cập dữ liệu:

| Phương thức | Dữ liệu |
|---|---|
| `isResult()` | `true` nếu context đang chứa kết quả đã xác nhận |
| `getResultItems()` | Danh sách item đã chọn, giữ nguyên kiểu `I` |
| `getValues()` | Danh sách giá trị dạng `String` được ánh xạ từ các item |
| `getItems()` | Danh sách item nguồn của selector |
| `getItemStates()` | Trạng thái của các item trong selector |
| `getCursorRow()` | Vị trí hàng con trỏ hiện tại |

Khi item chứa object nghiệp vụ, ưu tiên `getResultItems()` để không mất kiểu dữ liệu:

```java
List<Permission> selectedPermissions = context.getResultItems().stream()
        .map(SelectorItem::getItem)
        .collect(Collectors.toList());
```

Khi item chỉ chứa chuỗi và cần danh sách giá trị nhanh, có thể dùng:

```java
List<String> values = context.getValues();
```

Không nên xử lý kết quả trước khi kiểm tra `context.isResult()`. Hủy selector và xác nhận một danh sách rỗng là hai tình huống khác nhau:

- **Cancelled:** người dùng rời thao tác mà không xác nhận.
- **Confirmed but empty:** người dùng xác nhận nhưng không chọn item nào.

Ứng dụng có thể xử lý hai tình huống này khác nhau, ví dụ hủy toàn bộ command ở trường hợp đầu và yêu cầu chọn ít nhất một item ở trường hợp thứ hai.

## 7. Dùng object nghiệp vụ thay vì chỉ dùng String

`MultiItemSelector` có generic type `T`, vì vậy item có thể giữ object domain thay vì mã chuỗi. Cách này tránh phải tra cứu lại object sau khi người dùng chọn.

Ví dụ model:

```java
public record DeploymentTarget(String id, String environment, String region) {
}
```

Tạo selector item:

```java
List<SelectorItem<DeploymentTarget>> targets = deployments.stream()
        .map(target -> SelectorItem.of(
                target.environment() + " / " + target.region(), target))
        .collect(Collectors.toList());

MultiItemSelector<DeploymentTarget, SelectorItem<DeploymentTarget>> selector =
        new MultiItemSelector<>(getTerminal(), targets, "Choose deployment targets", null);
selector.setResourceLoader(getResourceLoader());
selector.setTemplateExecutor(getTemplateExecutor());

MultiItemSelectorContext<DeploymentTarget, SelectorItem<DeploymentTarget>> context =
        selector.run(MultiItemSelectorContext.empty());

if (context.isResult()) {
    List<DeploymentTarget> selectedTargets = context.getResultItems().stream()
            .map(SelectorItem::getItem)
            .collect(Collectors.toList());
}
```

Nhãn hiển thị có thể chứa tên môi trường và region, trong khi giá trị trả về vẫn là object `DeploymentTarget` đầy đủ. Không đưa token, password hoặc dữ liệu bí mật vào nhãn vì nội dung selector được hiển thị trên terminal.

## 8. Sắp xếp danh sách và giới hạn số item hiển thị

Constructor nhận `Comparator<I>` để sắp xếp item. Có thể truyền `null` để dùng hành vi sắp xếp mặc định của component. Nếu muốn sắp xếp theo nhãn không phân biệt chữ hoa/chữ thường:

```java
Comparator<SelectorItem<DeploymentTarget>> byName =
        Comparator.comparing(
                SelectorItem::getName,
                String.CASE_INSENSITIVE_ORDER);

MultiItemSelector<DeploymentTarget, SelectorItem<DeploymentTarget>> selector =
        new MultiItemSelector<>(getTerminal(), targets, "Choose targets", byName);
```

Selector kế thừa `setMaxItems(int)`, cho phép giới hạn số item được hiển thị trong vùng danh sách tại một thời điểm:

```java
selector.setMaxItems(8);
```

Lưu ý: `setMaxItems(8)` là giới hạn số item hiển thị trong danh sách, không phải giới hạn tổng số lựa chọn mà người dùng được phép chọn. Nếu nghiệp vụ chỉ cho phép tối đa ba mục, hãy kiểm tra số phần tử trong `getResultItems()` sau khi người dùng xác nhận và thông báo lỗi nếu vượt giới hạn.

## 9. Kiểm tra kết quả theo quy tắc nghiệp vụ

Selector chịu trách nhiệm thu thập lựa chọn. Command hoặc service vẫn phải xác thực kết quả trước khi thực hiện side effect.

Ví dụ chỉ cho phép chọn tối đa ba môi trường:

```java
if (!context.isResult()) {
    return "Selection cancelled.";
}

List<DeploymentTarget> selectedTargets = context.getResultItems().stream()
        .map(SelectorItem::getItem)
        .collect(Collectors.toList());

if (selectedTargets.isEmpty()) {
    return "Choose at least one deployment target.";
}

if (selectedTargets.size() > 3) {
    return "You can choose at most 3 targets.";
}

deploymentService.deploy(selectedTargets);
```

Với thao tác nhạy cảm, kiểm tra thêm:

- Item có còn tồn tại tại thời điểm thực thi không?
- Người dùng có quyền trên từng item không?
- Các item có thuộc cùng tenant hoặc cùng nhóm tài nguyên không?
- Tập lựa chọn có vi phạm quy tắc loại trừ hoặc phụ thuộc lẫn nhau không?
- Trạng thái tài nguyên có thay đổi kể từ khi danh sách được tải không?

Không xem một item xuất hiện trong selector là bằng chứng người dùng được phép thực hiện thao tác trên item đó. Danh sách có thể cũ và quyền có thể thay đổi trong lúc người dùng đang chọn.

## 10. Tích hợp với ComponentFlow

Spring Shell 3.x còn có `ComponentFlow` để ghép nhiều thành phần nhập liệu thành một wizard. Khi command cần vừa nhập thông tin, vừa chọn nhiều item, có thể dùng builder `withMultiItemSelector(...)` thay vì tự chạy một component độc lập.

Ví dụ khung cấu hình flow:

```java
import java.util.List;

import org.springframework.shell.component.flow.ComponentFlow;
import org.springframework.shell.component.flow.SelectItem;
import org.springframework.stereotype.Component;

@Component
public class PermissionWizard {

    private final ComponentFlow.Builder componentFlowBuilder;

    public PermissionWizard(ComponentFlow.Builder componentFlowBuilder) {
        this.componentFlowBuilder = componentFlowBuilder;
    }

    public ComponentFlow.ComponentFlowResult run() {
        List<SelectItem> selectItems = List.of(
                SelectItem.of("Read reports", "reports:read"),
                SelectItem.of("Export reports", "reports:export"),
                SelectItem.of("Manage users", "users:manage")
        );

        ComponentFlow flow = componentFlowBuilder.clone()
                .reset()
                .withMultiItemSelector("permissions")
                    .name("Choose permissions")
                    .selectItems(selectItems)
                    .and()
                .build();

        return flow.run();
    }
}
```

`MultiItemSelectorSpec` trong flow cho phép cấu hình danh sách `SelectItem`, tên, comparator, renderer, template, pre/post handler, `resultMode`, `resultValues` và số item hiển thị. Kết quả được lưu trong `ComponentFlowResult` theo ID của component nếu cấu hình lưu kết quả được bật.

Với cấu hình mặc định `storeResult(true)`, flow lưu kết quả selector vào context theo ID `permissions`. Có thể đọc context sau khi `run()` trả về:

```java
Object selectedPermissions = result.getContext().get("permissions");
```

Kiểu dữ liệu thực tế phụ thuộc cấu hình `resultMode` và `resultValues`; hãy kiểm tra hoặc chuyển đổi kiểu trước khi dùng. Nếu cần làm việc trực tiếp với `MultiItemSelectorContext` và item domain có kiểu, cách khởi tạo selector độc lập ở các phần trước rõ ràng hơn.

Chọn cách dùng:

- Dùng trực tiếp `MultiItemSelector` khi một command chỉ cần một màn hình chọn nhiều item.
- Dùng `ComponentFlow` khi cần nhiều bước nhập liệu và điều hướng giữa các bước.

Không trộn API của `MultiItemSelector` trực tiếp với builder `MultiItemSelectorSpec`. Hai API có mục đích liên quan nhưng cách khởi tạo và kiểu context khác nhau.

## 11. Terminal và giới hạn của interactive component

`MultiItemSelector` cần đọc input từ terminal và render giao diện tương tác. Vì vậy, nó phù hợp với interactive shell có TTY.

Không nên gọi selector trong:

- Command chạy non-interactive trong CI hoặc cron.
- Script cần chạy hoàn toàn không có input của người dùng.
- Pipeline nơi stdin/stdout được chuyển hướng và không có terminal tương tác.
- Automated test tạo application context nhưng không cấp dữ liệu bàn phím cho component.

Với automation, cung cấp lựa chọn bằng command option, file cấu hình hoặc dữ liệu đầu vào có cấu trúc. Có thể dùng cùng một service cho cả hai đường: interactive command thu thập danh sách bằng selector, còn non-interactive command nhận danh sách ID từ option/file rồi gọi service.

Ví dụ hai command có thể cùng gọi `permissionService.assign(...)`:

- `permission select`: mở selector để người dùng chọn.
- `permission assign --codes=reports:read,reports:export`: nhận danh sách mã từ script.

Như vậy, logic nghiệp vụ không phụ thuộc vào việc dữ liệu được thu thập từ giao diện tương tác hay từ automation.

## 12. Kiểm thử MultiItemSelector

Nên tách kiểm thử dữ liệu và quy tắc nghiệp vụ khỏi kiểm thử bàn phím/terminal.

| Trường hợp | Điều cần xác nhận |
|---|---|
| Danh sách có nhiều item | Mọi item hiển thị và có thể duyệt |
| Item chọn sẵn | Trạng thái ban đầu được phản ánh đúng |
| Item bị disable | Người dùng không thể thay đổi trạng thái chọn |
| Chọn nhiều item | `getResultItems()` chứa đúng các item đã xác nhận |
| Xác nhận danh sách rỗng | `isResult()` đúng và danh sách kết quả rỗng |
| Hủy selector | Command không gọi service có side effect |
| Danh sách dài | Cuộn/giới hạn hiển thị hoạt động đúng |
| Comparator | Danh sách hiển thị theo thứ tự mong muốn |
| Object nghiệp vụ | Kết quả giữ đúng object và định danh |
| Không có TTY | Command không cố mở selector trong non-interactive mode |
| Quyền bị thu hồi | Service từ chối item không còn được phép truy cập |
| Vượt giới hạn lựa chọn | Validation từ chối trước khi thực hiện nghiệp vụ |

Với test tương tác, dùng công cụ kiểm thử terminal của Spring Shell 3.x để cấp chuỗi phím và kiểm tra màn hình/kết quả. Với unit test service, truyền trực tiếp danh sách item đã chọn để kiểm tra giới hạn, quyền và quy tắc nghiệp vụ mà không cần mở terminal.

## 13. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Không hiển thị selector | Chưa cung cấp `ResourceLoader` hoặc `TemplateExecutor` | Gắn hai dependency từ `AbstractShellComponent` |
| Không đọc được kết quả | Chỉ đọc `getValues()` trong khi cần object gốc | Dùng `getResultItems()` và `SelectorItem.getItem()` |
| Người dùng hủy nhưng command vẫn ghi dữ liệu | Không kiểm tra `context.isResult()` | Phân biệt cancel và confirmed result trước khi gọi service |
| Danh sách rỗng gây lỗi | Giả định luôn có item được chọn | Kiểm tra `getResultItems().isEmpty()` |
| Item bị khóa vẫn xuất hiện | `enabled=false` chỉ vô hiệu hóa lựa chọn, không ẩn item | Hiển thị lý do hoặc lọc khỏi danh sách nếu không muốn người dùng thấy |
| `setMaxItems(5)` nhưng vẫn chọn được nhiều hơn năm mục | Nhầm số item hiển thị với số item được chọn | Tự kiểm tra số kết quả sau khi xác nhận |
| Thứ tự item không ổn định | Danh sách đầu vào không có thứ tự hoặc comparator không rõ | Sắp xếp dữ liệu trước hoặc truyền comparator |
| CI bị treo khi chạy command | Component chờ input từ TTY | Dùng option/file cho non-interactive mode |
| Quyền sai vẫn được áp dụng | Tin rằng item trong selector luôn hợp lệ | Kiểm tra quyền và trạng thái tài nguyên tại service |
| Giao diện khó dùng với danh sách lớn | Nạp quá nhiều item hoặc nhãn quá dài | Lọc trước, sắp xếp, giới hạn vùng hiển thị và dùng nhãn ngắn |

## 14. Checklist trước khi sử dụng MultiItemSelector

- [ ] Đã xác định đây là command cần tương tác trên TTY.
- [ ] Đã tạo `SelectorItem` với nhãn dễ đọc và giá trị nghiệp vụ ổn định.
- [ ] Đã xác định rõ item nào enabled và item nào được chọn sẵn.
- [ ] Đã truyền terminal, danh sách, tên selector và comparator phù hợp.
- [ ] Đã gắn `ResourceLoader` và `TemplateExecutor`.
- [ ] Đã gọi `run(MultiItemSelectorContext.empty())`.
- [ ] Đã kiểm tra `context.isResult()` trước khi đọc kết quả.
- [ ] Đã dùng `getResultItems()` nếu cần object nghiệp vụ có kiểu.
- [ ] Đã phân biệt cancel với xác nhận danh sách rỗng.
- [ ] Không nhầm `setMaxItems()` với giới hạn số lựa chọn.
- [ ] Đã kiểm tra quyền và trạng thái item tại service.
- [ ] Đã có đường chạy non-interactive không phụ thuộc selector.
- [ ] Đã kiểm thử chọn nhiều mục, item disabled, cancel, danh sách dài và không có TTY.

## Tài liệu tham khảo

1. [Spring Shell 3.3 – MultiItemSelector API](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/component/MultiItemSelector.html) – constructor, generic type và context của multi-item selector.
2. [Spring Shell 3.3 – MultiItemSelectorContext API](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/component/MultiItemSelector.MultiItemSelectorContext.html) – `getValues()` và context khởi tạo rỗng.
3. [Spring Shell 3.3 – SelectorItem API](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/component/support/SelectorItem.html) – tạo item, enabled state, selected state và giá trị gốc.
4. [Spring Shell 3.3 – AbstractSelectorComponent API](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/component/support/AbstractSelectorComponent.html) – selector context, item state, giới hạn item hiển thị và default expose.
5. [Spring Shell 3.3 – AbstractComponent API](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/component/support/AbstractComponent.html) – `run()`, terminal, renderer, resource loader và template executor.
6. [Spring Shell 3.3 – AbstractShellComponent API](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/standard/AbstractShellComponent.html) – các tiện ích truy cập terminal và template trong command bean.
7. [Spring Shell 3.0.2 – Reference Documentation](https://docs.spring.io/spring-shell/docs/3.0.2/docs/index.html) – phần Multi Select minh họa tạo item, chạy `MultiItemSelector` và đọc kết quả.

`MultiItemSelector` giúp command thu thập nhiều lựa chọn bằng một giao diện terminal có trạng thái rõ ràng. Hãy tách nhãn hiển thị khỏi giá trị nghiệp vụ, đọc kết quả qua context, xử lý riêng thao tác hủy và luôn kiểm tra lại quy tắc nghiệp vụ trước khi áp dụng lựa chọn.
