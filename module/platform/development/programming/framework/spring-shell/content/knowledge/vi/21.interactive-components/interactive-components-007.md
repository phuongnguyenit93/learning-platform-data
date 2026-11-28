# SingleItemSelector cho một lựa chọn

Khi command cần người dùng chọn đúng một mục trong danh sách, Spring Shell 3.x cung cấp `SingleItemSelector`. Thành phần này hiển thị các lựa chọn trong terminal, cho phép người dùng di chuyển đến mục mong muốn và xác nhận một lựa chọn. Command nhận lại item đã chọn qua `SingleItemSelectorContext` rồi tiếp tục xử lý nghiệp vụ.

Bài học thuộc chương **Thành phần tương tác 3.x**. Nội dung tập trung vào cách tạo danh sách `SelectorItem`, khởi tạo `SingleItemSelector`, hiển thị lựa chọn mặc định, vô hiệu hóa item, đọc kết quả và tùy chỉnh cách selector trình bày dữ liệu.

Sau bài học, bạn có thể:

- Giải thích vai trò của `SingleItemSelector` trong command tương tác.
- Tạo lựa chọn bằng `SelectorItem.of(name, item)`.
- Phân biệt tên hiển thị với giá trị nghiệp vụ được trả về.
- Khởi tạo selector bằng terminal, danh sách item và comparator.
- Đặt item mặc định và giới hạn số hàng hiển thị.
- Đọc kết quả an toàn qua `Optional`.
- Chuẩn bị selector cho terminal, template và môi trường kiểm thử.

## SingleItemSelector giải quyết vấn đề gì?

Nếu một command yêu cầu người dùng nhập tên môi trường, tên vùng triển khai hoặc loại báo cáo bằng văn bản tự do, người dùng có thể nhập sai chính tả hoặc chọn một giá trị không hợp lệ. Selector thay thế bước nhập tự do bằng một danh sách lựa chọn có sẵn.

Ví dụ command triển khai cần chọn một môi trường:

```text
Chọn môi trường triển khai

  > Development
    Staging
    Production
```

Người dùng chọn đúng một mục. Command nhận giá trị tương ứng, ví dụ `dev`, `stage` hoặc `prod`, rồi truyền giá trị đó cho service triển khai.

`SingleItemSelector<T, I>` là component chọn một item. `T` là kiểu dữ liệu nghiệp vụ của item; `I` là kiểu item hiển thị, phải triển khai các hợp đồng `Nameable`, `Matchable`, `Enableable`, `Selectable` và `Itemable<T>`. `SelectorItem<T>` là implementation có sẵn để tạo item nhanh.

## Dependency và môi trường chạy

Trong ứng dụng Spring Boot dùng Spring Shell 3.3.x, dependency `spring-shell-starter` cung cấp các thành phần shell cần thiết, bao gồm terminal dựa trên JLine:

```xml
<dependency>
    <groupId>org.springframework.shell</groupId>
    <artifactId>spring-shell-starter</artifactId>
</dependency>
```

Quản lý phiên bản bằng Spring Shell dependency BOM hoặc cấu hình phiên bản tương ứng với Spring Boot của dự án. `SingleItemSelector` cần terminal có khả năng đọc input tương tác; chạy component trong terminal thật khi kiểm tra hành vi bàn phím và render.

## Tạo SelectorItem

`SelectorItem.of(name, item)` tạo một lựa chọn gồm hai phần:

- `name`: nhãn hiển thị trong danh sách.
- `item`: giá trị thực tế mà command nhận sau khi người dùng chọn.

Ví dụ:

```java
import org.springframework.shell.component.support.SelectorItem;

SelectorItem<String> development =
    SelectorItem.of("Development", "dev");

SelectorItem<String> staging =
    SelectorItem.of("Staging", "stage");

SelectorItem<String> production =
    SelectorItem.of("Production", "prod");
```

Tên hiển thị có thể thân thiện với người dùng, trong khi giá trị item giữ mã ổn định để service xử lý. Không nên dùng nhãn hiển thị làm khóa nghiệp vụ nếu nhãn có thể thay đổi theo ngôn ngữ hoặc cách trình bày.

### Trạng thái enabled và selected

`SelectorItem.of` có overload nhận thêm hai cờ:

```java
SelectorItem<String> production =
    SelectorItem.of("Production", "prod", true, true);

SelectorItem<String> maintenance =
    SelectorItem.of("Maintenance", "maintenance", false, false);
```

Tham số thứ ba là `enabled`: `false` đánh dấu item không khả dụng để chọn. Tham số thứ tư là `selected`: biểu thị trạng thái được đánh dấu chọn ban đầu của item. Nếu muốn chủ động đưa một item lên vị trí được expose khi selector bắt đầu, có thể dùng `setDefaultExpose(...)` trên selector.

Chỉ vô hiệu hóa item khi có lý do nghiệp vụ rõ ràng, chẳng hạn môi trường đang bảo trì hoặc người dùng không có quyền triển khai. Service vẫn phải kiểm tra quyền và trạng thái trước khi thực hiện hành động; trạng thái disabled trong giao diện không thay thế kiểm tra ở tầng nghiệp vụ.

## Khởi tạo SingleItemSelector

Constructor nhận bốn tham số:

```java
new SingleItemSelector<>(terminal, items, name, comparator)
```

| Tham số | Ý nghĩa |
| --- | --- |
| `terminal` | JLine `Terminal` dùng để đọc phím và hiển thị component. |
| `items` | Danh sách item có thể chọn. |
| `name` | Tên component, dùng trong context/template. |
| `comparator` | Comparator tùy chọn để sắp xếp item. |

Trong command Spring Shell 3.x, lớp command có thể kế thừa `AbstractShellComponent` để lấy các dependency cần thiết như terminal, resource loader và template executor.

## Ví dụ hoàn chỉnh trong command

Ví dụ sau tạo selector cho ba môi trường và trả về mã môi trường đã chọn:

```java
import java.util.Arrays;
import java.util.List;
import java.util.Optional;

import org.springframework.shell.component.SingleItemSelector;
import org.springframework.shell.component.SingleItemSelector.SingleItemSelectorContext;
import org.springframework.shell.component.support.SelectorItem;
import org.springframework.shell.standard.AbstractShellComponent;
import org.springframework.shell.standard.ShellComponent;
import org.springframework.shell.standard.ShellMethod;

@ShellComponent
public class DeploymentCommands extends AbstractShellComponent {

    @ShellMethod(key = "deploy choose", value = "Chọn môi trường triển khai")
    public String chooseEnvironment() {
        SelectorItem<String> development =
            SelectorItem.of("Development", "dev");
        SelectorItem<String> staging =
            SelectorItem.of("Staging", "stage");
        SelectorItem<String> production =
            SelectorItem.of("Production", "prod");

        List<SelectorItem<String>> items = Arrays.asList(
            development, staging, production);

        SingleItemSelector<String, SelectorItem<String>> selector =
            new SingleItemSelector<>(getTerminal(), items, "environment", null);

        selector.setResourceLoader(getResourceLoader());
        selector.setTemplateExecutor(getTemplateExecutor());

        SingleItemSelectorContext<String, SelectorItem<String>> context =
            selector.run(SingleItemSelectorContext.empty());

        Optional<String> selected = context.getResultItem()
            .map(SelectorItem::getItem);

        return selected
            .map(value -> "Môi trường được chọn: " + value)
            .orElse("Bạn chưa chọn môi trường");
    }
}
```

Khi gọi `deploy choose`, component bắt đầu vòng lặp đọc phím trên terminal. Sau khi người dùng xác nhận, `run(...)` trả về context chứa kết quả. `getResultItem()` trả về `Optional` của item được chọn; gọi `getItem()` trên item để lấy giá trị nghiệp vụ.

Trong ví dụ, `comparator` là `null`, nên ứng dụng không truyền comparator tùy chỉnh. Nếu cần sắp xếp theo tên hoặc quy tắc nghiệp vụ, hãy cung cấp comparator phù hợp.

## Đọc kết quả và xử lý trường hợp không chọn

`SingleItemSelectorContext` cung cấp hai cách đọc kết quả:

| Phương thức | Giá trị trả về | Khi sử dụng |
| --- | --- | --- |
| `getResultItem()` | `Optional<I>` | Cần truy cập cả item, nhãn và giá trị nghiệp vụ. |
| `getValue()` | `Optional<String>` | Cần chuỗi kết quả được component ánh xạ. |

Ví dụ lấy item và giá trị:

```java
Optional<SelectorItem<String>> resultItem = context.getResultItem();
Optional<String> selectedValue = resultItem.map(SelectorItem::getItem);
Optional<String> selectedName = resultItem.map(SelectorItem::getName);
```

Không gọi `.get()` trên `Optional` khi chưa xác định có kết quả. Người dùng có thể thoát component hoặc không tạo ra lựa chọn hợp lệ. Hãy xử lý trường hợp rỗng bằng thông báo, giá trị mặc định hoặc nhánh nghiệp vụ phù hợp.

Ví dụ dùng `getValue()`:

```java
String value = context.getValue()
    .orElse("not-selected");
```

`getResultItem()` phù hợp khi cần lấy object đã chọn. `getValue()` phù hợp khi component đã cấu hình item mapper hoặc khi command chỉ cần chuỗi kết quả.

## Đặt lựa chọn mặc định

Nếu command có một lựa chọn thường dùng, có thể expose item đó khi selector khởi động. Người dùng chỉ cần xác nhận nếu lựa chọn mặc định là phù hợp.

```java
SingleItemSelector<String, SelectorItem<String>> selector =
    new SingleItemSelector<>(getTerminal(), items, "environment", null);

selector.setDefaultExpose(staging);
```

Trong ví dụ, `staging` được đưa ra làm lựa chọn mặc định. Hãy chọn default theo chính sách an toàn. Với thao tác có tác động lớn như triển khai production hoặc xóa dữ liệu, không nên chọn mặc định một giá trị nguy hiểm chỉ để giảm số lần nhấn phím.

Có thể tạo item đã được đánh dấu selected bằng overload `SelectorItem.of(name, item, enabled, selected)`. `setDefaultExpose(...)` có mục đích rõ ràng hơn khi muốn chỉ định item mặc định được expose lúc component bắt đầu.

## Giới hạn số item hiển thị

Khi danh sách dài, selector có thể giới hạn số hàng được hiển thị cùng lúc bằng `setMaxItems(int)`:

```java
selector.setMaxItems(6);
```

Giới hạn này giúp giao diện không chiếm toàn bộ terminal. Người dùng vẫn thao tác trong danh sách item; component quản lý phần hiển thị theo giới hạn đã đặt.

Chọn giá trị phù hợp với chiều cao terminal. Nếu có rất nhiều lựa chọn, hãy cân nhắc lọc danh sách trước khi tạo selector thay vì chỉ tăng số hàng hiển thị.

## Sắp xếp và ánh xạ item

Constructor nhận một `Comparator<I>` để xác định thứ tự item. Ví dụ, nếu muốn sắp xếp theo tên:

```java
import java.util.Comparator;

Comparator<SelectorItem<String>> byName =
    Comparator.comparing(SelectorItem::getName);

SingleItemSelector<String, SelectorItem<String>> selector =
    new SingleItemSelector<>(getTerminal(), items, "environment", byName);
```

Nếu thứ tự nghiệp vụ đã được xác định sẵn, có thể truyền `null` như ví dụ cơ bản để không yêu cầu comparator riêng.

`setItemMapper(Function<T, String>)` cho phép cung cấp hàm ánh xạ giá trị item sang chuỗi. Sử dụng khi biểu diễn hoặc chuỗi dùng để so khớp cần được điều chỉnh so với `toString()` mặc định của giá trị. Ví dụ:

```java
selector.setItemMapper(value -> value.toUpperCase());
```

Chỉ dùng mapper khi cần một quy tắc biểu diễn nhất quán. Đừng biến mapper thành nơi thực hiện truy vấn hoặc thay đổi dữ liệu nghiệp vụ; hãy chuẩn bị item trước khi mở selector.

## Tùy chỉnh template và renderer

`SingleItemSelector` kế thừa khả năng cấu hình template và renderer từ `AbstractComponent`. Trong ví dụ Spring Shell 3.x, cần cung cấp `ResourceLoader` và `TemplateExecutor` để component có thể tải và xử lý template:

```java
selector.setResourceLoader(getResourceLoader());
selector.setTemplateExecutor(getTemplateExecutor());
```

Context của selector cung cấp các biến template:

| Biến | Ý nghĩa |
| --- | --- |
| `value` | Giá trị được trả về khi component có kết quả. |
| `rows` | Các item đang hiển thị; mỗi hàng có thông tin tên và trạng thái chọn. |
| `model` | Các biến context cha được kế thừa từ selector context. |

Có thể đặt template riêng bằng `setTemplateLocation(...)` hoặc đặt renderer bằng `setRenderer(...)`. Khi tùy chỉnh giao diện, cần giữ rõ trạng thái item hiện tại, trạng thái selected/disabled và hướng dẫn thao tác để người dùng hiểu cách chọn.

## Vòng đời component và handler

`AbstractComponent` cung cấp handler trước và sau khi component chạy:

```java
selector.addPreRunHandler(context -> {
    // Chuẩn bị dữ liệu hoặc ghi nhận thời điểm bắt đầu.
});

selector.addPostRunHandler(context -> {
    // Ghi nhận kết quả sau khi selector kết thúc.
});
```

Pre-run handler phù hợp để chuẩn bị context trước khi hiển thị; post-run handler phù hợp để ghi nhận kết quả hoặc dọn dẹp tài nguyên. Giữ handler ngắn và tránh thực hiện tác vụ mạng kéo dài trong lúc giao diện đang chờ người dùng.

Lớp nền `AbstractComponent` có phương thức `hasTty()` ở mức `protected` để implementation component kiểm tra TTY. `SingleItemSelector` là thành phần tương tác cần đọc phím; vì vậy nên dùng trong phiên terminal có khả năng nhập liệu. Với script, CI hoặc môi trường không có TTY, hãy cung cấp lựa chọn qua command option, argument hoặc cấu hình thay vì chờ người dùng điều hướng selector.

## Trải nghiệm bàn phím

Selector dùng JLine để đọc thao tác terminal. Các thao tác điều hướng, xác nhận và thoát được ánh xạ thành những operation riêng như `UP`, `DOWN`, `SELECT` và `EXIT` trong component API.

Trong terminal thông thường, người dùng điều hướng bằng phím mũi tên, xác nhận lựa chọn bằng Enter và thoát bằng phím thoát được key map hỗ trợ. Cách ánh xạ cụ thể có thể phụ thuộc terminal và key map; hãy kiểm tra trong môi trường triển khai thực tế và cung cấp hướng dẫn thao tác trên màn hình.

Nếu phím điều hướng không hoạt động, hãy kiểm tra terminal/JLine có được khởi tạo đúng, phiên chạy có TTY và input không bị một tiến trình khác đọc trước component.

## Khi nào nên dùng SingleItemSelector?

| Tình huống | Có phù hợp? | Lý do |
| --- | --- | --- |
| Chọn một môi trường triển khai | Có | Người dùng chỉ được chọn một môi trường. |
| Chọn một profile hoặc cấu hình | Có | Danh sách hữu hạn, một lựa chọn duy nhất. |
| Chọn nhiều module cùng lúc | Không | Dùng `MultiItemSelector`. |
| Chạy command tự động trong CI không có TTY | Không | Nên truyền giá trị bằng option hoặc cấu hình. |
| Danh sách có hàng nghìn mục | Cần cân nhắc | Lọc hoặc tìm kiếm trước khi tạo danh sách hiển thị. |

Selector phù hợp với tương tác thủ công trong terminal. Nếu cần một command có thể chạy đồng nhất cả trong terminal lẫn script, hãy thiết kế option để bỏ qua bước tương tác:

```text
deploy choose --environment prod
```

Khi không có option, ứng dụng có thể mở selector nếu đang chạy trong terminal tương tác. Khi có option, command dùng trực tiếp giá trị đã cung cấp và không cần hỏi người dùng.

## Kiểm thử SingleItemSelector

Nên kiểm tra các phần độc lập:

1. Danh sách item được tạo với đúng nhãn và giá trị nghiệp vụ.
2. Item disabled không thể được chọn trong giao diện.
3. Item mặc định được expose đúng khi gọi `setDefaultExpose(...)`.
4. Kết quả xác nhận trả đúng item và `getItem()` trả đúng giá trị.
5. Trường hợp người dùng thoát hoặc không có kết quả được xử lý an toàn.
6. Danh sách dài tuân theo `setMaxItems(...)`.
7. Template hoặc renderer tùy chỉnh hiển thị đúng tên và trạng thái item.
8. Command có phương án non-interactive khi chạy trong CI hoặc script.

Với kiểm thử tích hợp, dùng terminal kiểm thử/JLine test support để mô phỏng thao tác bàn phím và xác nhận kết quả context. Ngoài ra, kiểm tra command trong một terminal thật để phát hiện khác biệt về phím điều hướng, TTY và cách render.

## Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Không hiển thị selector | Terminal chưa được inject hoặc không có TTY phù hợp. | Kiểm tra `getTerminal()` và chạy trong terminal tương tác. |
| `NullPointerException` khi render template | Chưa đặt `ResourceLoader` hoặc `TemplateExecutor`. | Gọi `setResourceLoader(...)` và `setTemplateExecutor(...)`. |
| Nhận mã thay vì nhãn mong muốn | Command đọc `getItem()` trong khi cần `getName()`. | Chọn đúng trường: `getName()` cho nhãn, `getItem()` cho giá trị. |
| `NoSuchElementException` khi đọc kết quả | Gọi `Optional.get()` mà không kiểm tra kết quả. | Dùng `map`, `orElse` hoặc `ifPresent`. |
| Item không thể chọn | Item được tạo với `enabled=false`. | Kiểm tra trạng thái enabled trước khi thêm vào danh sách. |
| Lựa chọn mặc định không xuất hiện | Chưa gọi `setDefaultExpose(...)` hoặc truyền item không thuộc danh sách. | Dùng đúng instance item có trong danh sách selector. |
| Danh sách chiếm quá nhiều terminal | Không giới hạn số hàng hiển thị. | Dùng `setMaxItems(...)` và lọc dữ liệu trước khi tạo selector. |
| Script/CI bị chờ nhập liệu | Command luôn gọi selector dù không có terminal. | Cung cấp option/argument và chỉ mở selector khi chạy tương tác. |

## Checklist trước khi phát hành command

- [ ] Mỗi item có nhãn hiển thị dễ hiểu và giá trị nghiệp vụ ổn định.
- [ ] Item disabled và selected được thiết lập đúng.
- [ ] Default item phù hợp với chính sách nghiệp vụ.
- [ ] `ResourceLoader` và `TemplateExecutor` đã được cấu hình.
- [ ] Kết quả được đọc qua `Optional` và có xử lý trường hợp rỗng.
- [ ] Danh sách dài có giới hạn hiển thị hoặc được lọc trước.
- [ ] Terminal thực tế hỗ trợ nhập phím và hiển thị component.
- [ ] Command có đường chạy non-interactive cho script/CI.
- [ ] Service vẫn xác thực quyền và trạng thái trước khi thực hiện hành động.

## Ghi nhớ

`SingleItemSelector` trong Spring Shell 3.x hiển thị một danh sách để người dùng chọn đúng một item. `SelectorItem` tách nhãn hiển thị khỏi giá trị nghiệp vụ; `setDefaultExpose(...)` đặt item mặc định; `setMaxItems(...)` giới hạn số hàng; `SingleItemSelectorContext` trả kết quả qua `Optional`. Khi tích hợp vào command, lấy terminal, resource loader và template executor từ `AbstractShellComponent`, rồi xử lý trường hợp không có kết quả. Đây là component dành cho terminal tương tác; command dùng trong script hoặc CI nên có option để cung cấp lựa chọn trực tiếp.

## Tài liệu tham khảo

- [Spring Shell 3.3.4 — Single Select](https://docs.spring.io/spring-shell/reference/3.3/components/ui/singleselect.html): ví dụ chính thức, template variables và lựa chọn mặc định.
- [Spring Shell 3.3.0 API — `SingleItemSelector`](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/component/SingleItemSelector.html): constructor, `run` và các phương thức kế thừa.
- [Spring Shell 3.3.0 API — `SelectorItem`](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/component/support/SelectorItem.html): tạo item, nhãn, giá trị, trạng thái enabled và selected.
- [Spring Shell 3.3.0 API — `SingleItemSelectorContext`](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/component/SingleItemSelector.SingleItemSelectorContext.html): `getResultItem()`, `getValue()` và context.
- [Spring Shell 3.3.0 API — `AbstractSelectorComponent`](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/component/support/AbstractSelectorComponent.html): `setDefaultExpose`, `setMaxItems` và item mapper.
- [Spring Shell 3.3.0 API — `AbstractShellComponent`](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/standard/AbstractShellComponent.html): truy cập terminal, resource loader và template executor.
- [Spring Shell 3.3.0 API — `AbstractComponent`](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/component/support/AbstractComponent.html): lifecycle, TTY, renderer, template và pre/post-run handler.
