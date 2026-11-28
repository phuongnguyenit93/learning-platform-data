# Xử lý truyền lặp một tùy chọn theo quy tắc của parser

Trong nhiều công cụ dòng lệnh, người dùng có thể lặp lại cùng một option để truyền nhiều giá trị, chẳng hạn `--tag java --tag spring`. Tuy nhiên, không phải parser nào cũng cộng dồn các lần xuất hiện của cùng một key. Với Spring Shell, cần phân biệt **lặp lại key** với **một key nhận nhiều value theo arity**. Hai cách viết này có hình thức gần nhau nhưng là hai hợp đồng cú pháp khác nhau.

Ở mô hình command của Spring Shell 3.x, cách khai báo một option nhận nhiều giá trị là dùng kiểu mảng hoặc collection kết hợp với arity phù hợp. Parser đọc một lần xuất hiện của option và thu thập số value được cho phép. Tài liệu Spring Shell legacy cũng cảnh báo key không nên được lặp trong cách truyền tham số theo tên. Vì vậy, ứng dụng cần công bố rõ cú pháp được hỗ trợ và kiểm thử bằng parser thực tế.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt truyền lặp key với truyền nhiều value cho một lần xuất hiện của option.
- Giải thích vai trò của arity trong quá trình parser thu thập value.
- Khai báo option nhận nhiều giá trị bằng `@Option`, mảng hoặc collection trong Spring Shell 3.x.
- Chọn `ZERO_OR_MORE`, `ONE_OR_MORE` hoặc giới hạn min/max theo yêu cầu command.
- Hiểu vì sao `--tag a --tag b` không mặc nhiên tạo thành một danh sách.
- Phân biệt alias của option với nhiều lần xuất hiện của cùng option.
- Viết kiểm thử xác nhận parser xử lý đúng số lượng value, lỗi thiếu value và lỗi vượt giới hạn.

## 1. Hai ý nghĩa khác nhau của việc truyền nhiều giá trị

Giả sử command `artifact publish` nhận nhiều tag để gắn vào một artifact. Người dùng có thể nghĩ đến hai cách viết:

**Lặp key cho từng value:**

```text
artifact publish --tag stable --tag preview --tag latest
```

**Một key nhận nhiều value:**

```text
artifact publish --tag stable preview latest
```

Hai dòng trên không tự động có cùng ý nghĩa. Dòng đầu chứa ba lần xuất hiện của key `tag`. Dòng thứ hai chứa một lần xuất hiện của key `tag`, theo sau là ba value. Parser cần có quy tắc rõ ràng để quyết định value nào thuộc option và khi nào dừng thu thập.

Trong Spring Shell 3.x, arity định nghĩa số lượng value mà parser nhận cho một option. Khi tham số là mảng hoặc collection, các value được thu thập có thể được chuyển thành một cấu trúc dữ liệu. Đây là cơ chế phù hợp để biểu diễn một option đa giá trị.

Không nên giả định rằng parser sẽ tự cộng dồn nhiều lần xuất hiện của một key giống một số CLI framework khác. Tài liệu Spring Shell legacy ghi rõ key không nên được lặp trong cách truyền tham số theo tên; ví dụ `--numbers 1 --numbers 2 --numbers 3` được nêu là không hoạt động. Với phiên bản và mô hình command đang dùng, hãy tuân theo hợp đồng được tài liệu hóa và xác nhận bằng kiểm thử.

## 2. Arity là số value, không phải số lần lặp key

Arity trả lời câu hỏi: **sau khi parser gặp một option, option đó nhận bao nhiêu value?** Nó không có nghĩa là parser cho phép key xuất hiện bao nhiêu lần.

Ví dụ, với option `--tag`:

| Cấu hình arity | Số value trong một lần xuất hiện |
|---|---:|
| `ZERO` | 0 |
| `ZERO_OR_ONE` | 0 hoặc 1 |
| `EXACTLY_ONE` | Đúng 1 |
| `ZERO_OR_MORE` | 0 hoặc nhiều |
| `ONE_OR_MORE` | Ít nhất 1 |

Nếu option cần từ một đến nhiều tag, `ONE_OR_MORE` diễn đạt đúng yêu cầu. Nếu option có thể không nhận tag nào hoặc nhận nhiều tag, `ZERO_OR_MORE` có thể phù hợp. Nếu cần đúng hai value, có thể đặt `arityMin = 2` và `arityMax = 2` trong annotation model mới hoặc dùng `.arity(2, 2)` ở mô hình programmatic.

Ví dụ cú pháp một lần xuất hiện với nhiều value:

```text
artifact publish --tag stable preview latest
```

Với arity `ONE_OR_MORE`, parser thu thập các value của option theo quy tắc phân tích lệnh, đến khi đạt giới hạn hoặc gặp ranh giới token mà parser nhận diện là thành phần tiếp theo của command. Nếu có thêm option khác, hãy viết rõ ràng và kiểm thử thứ tự kết hợp.

## 3. Khai báo option đa giá trị bằng annotation trong Spring Shell 3.x

Trong annotation model mới, `@Option` có thể khai báo arity. Khi tham số là mảng hoặc collection, Spring Shell chuyển các value đã parse thành cấu trúc tương ứng.

Ví dụ command nhận một hoặc nhiều tag:

```java
import org.springframework.shell.command.CommandRegistration.OptionArity;
import org.springframework.shell.command.annotation.Command;
import org.springframework.shell.command.annotation.Option;
import org.springframework.stereotype.Component;

@Component
public class ArtifactCommands {

    @Command(command = "artifact publish")
    public String publish(
            @Option(
                    longNames = "tag",
                    arity = OptionArity.ONE_OR_MORE) String[] tags) {
        return "Tags: " + String.join(", ", tags);
    }
}
```

Người dùng có thể gọi:

```text
shell:> artifact publish --tag stable preview latest
Tags: stable, preview, latest
```

`String[]` nhận các value đã được parser thu thập. `OptionArity.ONE_OR_MORE` yêu cầu ít nhất một value và cho phép nhiều value. Đây là một lần xuất hiện của `--tag` với nhiều value theo arity.

Có thể dùng `List<String>` hoặc kiểu collection phù hợp nếu kiểu generic được Spring chuyển đổi đúng trong phiên bản dự án. Mảng thường là ví dụ dễ nhìn và dễ kiểm tra hơn khi bắt đầu.

## 4. Giới hạn số lượng value

Không phải option đa giá trị nào cũng nên nhận vô hạn value. Ví dụ, một lệnh so sánh cần ít nhất hai nhãn và nhiều nhất ba nhãn. Khi đó hãy đặt giới hạn cụ thể.

```java
import org.springframework.shell.command.annotation.Command;
import org.springframework.shell.command.annotation.Option;

@Command(command = "environment compare")
public String compare(
        @Option(
                longNames = "target",
                arityMin = 2,
                arityMax = 3) String[] targets) {
    return "Comparing: " + String.join(" vs ", targets);
}
```

Các cách gọi hợp lệ theo hợp đồng trên:

```text
environment compare --target dev staging
environment compare --target dev staging production
```

Trường hợp thiếu value:

```text
environment compare --target dev
```

Trường hợp vượt giới hạn:

```text
environment compare --target dev staging production qa
```

Parser có thể báo lỗi thiếu hoặc thừa value trước khi command method được gọi. Đây là lợi ích của việc khai báo arity: giới hạn được kiểm tra tại lớp phân tích đầu vào, thay vì để command nhận một mảng có kích thước ngoài mong đợi.

## 5. Khai báo bằng `CommandRegistration`

Nếu command được tạo bằng cấu hình programmatic, arity được đặt trên `OptionSpec`. Cách này hữu ích khi command được đăng ký từ bean hoặc cần được xây dựng theo cấu hình.

```java
import org.springframework.shell.command.CommandRegistration;
import org.springframework.shell.command.CommandRegistration.OptionArity;

CommandRegistration registration = CommandRegistration.builder()
        .command("artifact publish")
        .withOption()
            .longNames("tag")
            .type(String[].class)
            .arity(OptionArity.ONE_OR_MORE)
            .and()
        .withTarget()
            .function(context -> {
                String[] tags = context.getOptionValue("tag");
                return "Tags: " + String.join(", ", tags);
            })
            .and()
        .build();
```

Ở đây, `.type(String[].class)` mô tả kiểu dữ liệu của option; `.arity(OptionArity.ONE_OR_MORE)` mô tả số value mà parser thu thập. Hai cấu hình bổ sung cho nhau: kiểu dữ liệu nói kết quả có dạng gì, arity nói parser phải lấy bao nhiêu value.

Có thể giới hạn bằng min/max:

```java
.withOption()
    .longNames("target")
    .type(String[].class)
    .arity(2, 3)
    .and()
```

Cách khai báo programmatic có thể biểu diễn đầy đủ min/max. Với annotation model mới, dùng `arityMin` và `arityMax` khi cần giới hạn riêng hai đầu.

## 6. Vì sao `--tag a --tag b` không phải cách tích lũy mặc định?

Khi parser gặp một key, nó cần xác định option đó nhận value theo arity đã khai báo. Một lần xuất hiện của `--tag` đã có một nhóm value gắn với nó. Việc cùng key xuất hiện lần nữa tạo ra một trường hợp lặp mà parser phải có quy tắc riêng: cộng dồn, ghi đè, từ chối hay xử lý như một lỗi cú pháp.

Spring Shell không nên được giả định là tự chọn quy tắc cộng dồn giống các framework khác. Tài liệu Spring Shell legacy nêu rõ rằng khi dùng tham số theo tên, key không được lặp. Do đó, không thiết kế API của ứng dụng dựa trên kỳ vọng `--tag a --tag b` sẽ trở thành `List.of("a", "b")`.

Ví dụ không nên dùng làm hợp đồng đa giá trị nếu chưa có parser tùy chỉnh được kiểm chứng:

```text
artifact publish --tag stable --tag preview --tag latest
```

Hãy dùng cú pháp một key với nhiều value theo arity:

```text
artifact publish --tag stable preview latest
```

Nếu ứng dụng bắt buộc phải hỗ trợ lặp key cho từng value vì tương thích với script hoặc quy ước CLI đã tồn tại, hãy xác định rõ hành vi mong muốn rồi kiểm tra khả năng của parser trong đúng phiên bản. Với Spring Shell 4.x, tài liệu cung cấp điểm mở rộng `CommandParser` để thay đổi quy tắc phân tích khi parser mặc định không đáp ứng yêu cầu. Parser tùy chỉnh cần định nghĩa rõ cách xử lý key lặp, value thiếu, value rỗng và lỗi trùng lặp.

## 7. Alias không phải là nhiều lần xuất hiện

Một option có thể có tên dài và tên ngắn cùng trỏ đến một tham số:

```java
@Option(
        longNames = {"tag", "label"},
        shortNames = {'t'},
        arity = OptionArity.ONE_OR_MORE) String[] tags
```

Trong đó `--tag`, `--label` và `-t` là các cách gọi của cùng một option. Chúng là tên chính và bí danh, không phải ba trường dữ liệu độc lập.

Ví dụ:

```text
artifact publish --tag stable preview
artifact publish --label stable preview
artifact publish -t stable preview
```

Mỗi dòng dùng một cách gọi của option. Không nên viết:

```text
artifact publish --tag stable --label preview
```

với kỳ vọng `--tag` và `--label` là hai phần tử được cộng dồn. Vì chúng là alias của cùng một option, parser không có lý do mặc định để coi chúng là hai danh sách riêng.

## 8. Phân biệt arity với `@Arguments`

Option đa giá trị vẫn là dữ liệu có tên, được nhận diện qua key như `--tag`. `@Arguments` lại dùng để thu thập các argument vị trí chưa được ánh xạ vào option.

Trong Spring Shell 4.x, có thể khai báo một tham số `@Arguments` với kiểu mảng hoặc collection để nhận các argument vị trí còn lại:

```java
import org.springframework.shell.core.command.annotation.Arguments;
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.Option;

@Command(name = "artifact inspect")
public String inspect(
        @Option(longName = "format", shortName = 'f') String format,
        @Arguments String[] names) {
    return "format=" + format + "; names=" + String.join(", ", names);
}
```

Ví dụ này thu thập các argument vị trí như `artifact inspect alpha beta --format json`. Nó không có nghĩa `@Arguments` sẽ gom các lần xuất hiện `--tag` thành một option đa giá trị.

Không thay option bằng `@Arguments` nếu người dùng cần một key có tên rõ ràng. Hai cơ chế thể hiện hai hợp đồng đầu vào khác nhau.

## 9. Legacy annotation và giới hạn arity

Một số ứng dụng Spring Shell 3.x vẫn dùng mô hình cũ `@ShellMethod` và `@ShellOption`. Mô hình này có thuộc tính `arity` dạng số nguyên, nhưng tài liệu Spring Shell chỉ ra legacy annotation không hỗ trợ đầy đủ cách đặt min arity như annotation model mới và programmatic model.

Ví dụ legacy cho tham số nhận ba value:

```java
import org.springframework.shell.standard.ShellComponent;
import org.springframework.shell.standard.ShellMethod;
import org.springframework.shell.standard.ShellOption;

@ShellComponent
public class LegacyTagCommands {

    @ShellMethod(key = "tag join")
    public String join(
            @ShellOption(value = "--tag", arity = 3) String[] tags) {
        return String.join(", ", tags);
    }
}
```

Trong mô hình legacy, `arity` điều khiển số từ mà tham số nhận theo API cũ. Nếu cần arity biến thiên hoặc cần kiểm soát min/max rõ ràng, ưu tiên annotation model mới hoặc `CommandRegistration` trong Spring Shell 3.x. Không trộn `@ShellOption` với `@Option` trong cùng một ví dụ vì chúng thuộc hai mô hình annotation khác nhau.

## 10. Cách biểu diễn danh sách khi không dùng arity

Một lựa chọn khác là truyền danh sách thành một value duy nhất có dấu phân cách, ví dụ:

```text
artifact publish --tags=stable,preview,latest
```

Khi đó command nhận một chuỗi và tự tách theo quy tắc của ứng dụng, hoặc dựa vào converter được cấu hình cho kiểu mảng/collection. Cách này khác với việc parser nhận nhiều token theo arity.

Nếu tự tách chuỗi, cần quy định rõ:

- Dấu phân cách có thể xuất hiện bên trong một phần tử hay không.
- Khoảng trắng quanh từng phần tử được giữ hay loại bỏ.
- Phần tử rỗng có hợp lệ không, ví dụ `stable,,latest`.
- Cách escape dấu phẩy nếu tên tag có dấu phẩy.
- Giá trị trùng lặp có được giữ nguyên thứ tự hay loại bỏ.

Chỉ dùng định dạng phân cách khi hợp đồng dữ liệu được công bố và kiểm thử. Với danh sách đơn giản cần nhập trực tiếp trong shell, option có arity rõ ràng thường dễ đọc và ít phải tự xử lý hơn.

## 11. Thứ tự option và ranh giới thu thập value

Khi option nhận nhiều value, người viết command cần xác định ranh giới giữa danh sách đó và các option khác.

Ví dụ:

```text
artifact publish --tag stable preview --channel production
```

Ý định là `tag` nhận `stable`, `preview`, còn `channel` nhận `production`. Parser phải nhận diện `--channel` là option kế tiếp thay vì một value của `tag`.

Với option arity có giới hạn, parser dừng khi đạt số value tối đa. Với `ONE_OR_MORE` hoặc `ZERO_OR_MORE`, ranh giới thường được xác định bởi option tiếp theo hoặc kết thúc dòng lệnh. Hãy kiểm thử thứ tự khi có nhiều option và positional argument vì cách phân giải argument vị trí có thể phụ thuộc parser và cấu hình.

Để giảm mơ hồ:

- Đặt option đa giá trị ở vị trí dễ đọc.
- Dùng tên option rõ nghĩa.
- Đặt option đơn trị kế tiếp sau danh sách nhiều value.
- Không đặt positional argument xen giữa một option đang thu thập nhiều value nếu chưa xác nhận parser hỗ trợ.
- Dùng arity hữu hạn nếu command có số lượng tối đa hợp lý.

## 12. Kiểm thử hành vi parser

Kiểm thử trực tiếp command method chỉ xác nhận code nghiệp vụ nhận một mảng hoặc collection như mong muốn. Nó không chứng minh parser đã tách dòng lệnh và binding value đúng. Cần có kiểm thử command qua parser hoặc Spring Shell runtime.

Với option `--tag` khai báo `ONE_OR_MORE`, có thể lập ma trận sau:

| Input | Kết quả mong đợi |
|---|---|
| `artifact publish --tag stable` | Nhận một phần tử `stable` |
| `artifact publish --tag stable preview` | Nhận hai phần tử theo đúng thứ tự |
| `artifact publish --tag stable preview --channel prod` | `tag` nhận hai phần tử; `channel` nhận `prod` |
| `artifact publish` | Báo thiếu option/value nếu option bắt buộc |
| `artifact publish --tag` | Báo thiếu ít nhất một value |
| `artifact publish --tag stable preview latest qa` với max = 3 | Báo vượt số value tối đa |
| `artifact publish --tag stable --tag preview` | Xác nhận parser không tự tích lũy lặp key theo hợp đồng ứng dụng |

Nên kiểm thử cả thứ tự option:

```text
artifact publish --tag stable preview --channel prod
artifact publish --channel prod --tag stable preview
```

Nếu cả hai cách đều được tài liệu hóa là hợp lệ, kiểm thử phải xác nhận kết quả giống nhau. Nếu parser không hỗ trợ một thứ tự nào đó, tài liệu help và ví dụ cần nêu rõ quy tắc.

Với parser tùy chỉnh, bổ sung kiểm thử cho các trường hợp:

- Cùng một key xuất hiện nhiều lần.
- Alias khác nhau của cùng option xuất hiện trong một dòng.
- Một lần xuất hiện có value thiếu.
- Một lần xuất hiện có value rỗng.
- Giá trị bắt đầu bằng dấu gạch ngang.
- Giá trị chứa khoảng trắng hoặc dấu phân cách.
- Option lặp với giá trị trùng nhau.
- Option đa giá trị nằm trước và sau option đơn trị.

## 13. Thiết kế quy tắc xử lý trùng lặp trong nghiệp vụ

Ngay cả khi parser không cộng dồn repeated key, command vẫn cần quyết định cách xử lý phần tử trùng trong một danh sách hợp lệ. Ví dụ:

```text
artifact publish --tag stable preview stable
```

Danh sách có hai lần `stable`. Tùy nghiệp vụ, ứng dụng có thể:

- Giữ nguyên mọi phần tử và thứ tự.
- Loại phần tử trùng nhưng giữ lần xuất hiện đầu tiên.
- Báo lỗi để người dùng sửa input.
- Chuẩn hóa chữ hoa/chữ thường trước khi so sánh.

Đây là quy tắc nghiệp vụ sau khi parser đã tạo danh sách. Không nên nhầm nó với hành vi lặp key của parser. Hãy tách hai câu hỏi: parser nhận được bao nhiêu value, và command xử lý các value trùng như thế nào.

Ví dụ kiểm tra và chuẩn hóa trong command:

```java
import java.util.Arrays;
import java.util.LinkedHashSet;
import java.util.Set;

@Command(command = "artifact publish")
public String publish(
        @Option(
                longNames = "tag",
                arity = OptionArity.ONE_OR_MORE) String[] tags) {
    Set<String> uniqueTags = new LinkedHashSet<>(Arrays.asList(tags));
    return "Tags: " + String.join(", ", uniqueTags);
}
```

`LinkedHashSet` loại giá trị trùng nhưng giữ thứ tự xuất hiện đầu tiên. Nếu yêu cầu nghiệp vụ là báo lỗi khi trùng, hãy kiểm tra kích thước collection trước và ném lỗi phù hợp thay vì tự loại bỏ.

## 14. Những lỗi thường gặp

### Lặp `--tag` và mong parser tự tạo danh sách

Không dựa vào hành vi tích lũy lặp key nếu parser không tài liệu hóa điều đó. Dùng một key với nhiều value theo arity hoặc tự định nghĩa parser có hợp đồng rõ ràng.

### Khai báo mảng nhưng không đặt arity phù hợp

Kiểu `String[]` cho biết dạng dữ liệu, nhưng parser vẫn cần biết cách thu thập value. Khai báo arity phù hợp với số lượng phần tử mong đợi.

### Nhầm alias với một option độc lập

`--tag` và `-t` có thể là hai tên của cùng một option. Dùng chúng như các cách gọi thay thế, không coi là hai danh sách riêng.

### Dùng `ONE_OR_MORE` nhưng mong option có thể rỗng

`ONE_OR_MORE` yêu cầu ít nhất một value. Nếu danh sách được phép rỗng, cân nhắc `ZERO_OR_MORE` và quy tắc `required` phù hợp.

### Dùng arity quá lớn

Một option tham lam có thể thu thập các token mà người dùng định dành cho argument hoặc phần khác của command. Đặt max hợp lý hoặc thiết kế ranh giới cú pháp rõ ràng.

### Kiểm thử command method mà không kiểm thử parser

Gọi trực tiếp phương thức Java không xác nhận cú pháp `--tag a b` hoặc lỗi khi thiếu value. Cần kiểm thử ở lớp thực thi command.

### Nhầm lỗi parser với lỗi nghiệp vụ

Lỗi thiếu value hoặc vượt arity xuất hiện trong giai đoạn parse. Lỗi như tag không tồn tại hoặc trùng theo quy tắc nghiệp vụ chỉ được phát hiện sau khi command nhận được danh sách.

## 15. Lưu ý khi chuyển sang Spring Shell 4.x

Spring Shell 4.x thay đổi mô hình command và parser. Annotation `@Option` của 4.x có các thuộc tính tên đơn như `longName` và `shortName`; API `@Option` 4.0.3 không còn khai báo `arity` như annotation model 3.x. `@Arguments` trong 4.x dùng để gom các argument vị trí vào mảng hoặc collection, không phải để lặp key có tên.

Tài liệu 4.x cung cấp `CommandParser` như một điểm mở rộng để tùy chỉnh cách phân tích command line. Nếu yêu cầu của ứng dụng là cú pháp `--tag a --tag b` phải cộng dồn thành một danh sách, hãy xác định semantics cụ thể và triển khai/đăng ký parser tùy chỉnh theo API của đúng phiên bản. Đừng chuyển nguyên `@Option(arity = ...)` từ 3.x sang 4.x.

## 16. Checklist thiết kế option đa giá trị

- [ ] Đã xác định ứng dụng dùng Spring Shell 3.x hay 4.x.
- [ ] Đã phân biệt yêu cầu lặp key với yêu cầu một key nhận nhiều value.
- [ ] Đã chọn arity phù hợp với số value tối thiểu và tối đa.
- [ ] Tham số dùng mảng hoặc collection phù hợp với kiểu dữ liệu.
- [ ] Đã xác định ranh giới giữa danh sách value và option kế tiếp.
- [ ] Đã xác định quy tắc khi option vắng mặt hoặc thiếu value.
- [ ] Đã quy định cách xử lý value trùng trong nghiệp vụ.
- [ ] Không dùng alias như cách thêm phần tử vào cùng danh sách.
- [ ] Đã kiểm thử repeated key để xác nhận parser không có hành vi ngoài hợp đồng.
- [ ] Đã kiểm thử qua parser/runtime, không chỉ gọi trực tiếp command method.
- [ ] Nếu cần repeated-key accumulation, đã định nghĩa và kiểm thử parser tùy chỉnh.

## 17. Tự kiểm tra

**Câu 1.** `--tag stable preview` khác `--tag stable --tag preview` như thế nào?

**Gợi ý trả lời:** Dạng đầu là một lần xuất hiện của option với hai value theo arity. Dạng sau lặp key; Spring Shell không mặc nhiên cộng dồn hai lần xuất hiện thành một collection.

**Câu 2.** Arity trả lời câu hỏi nào?

**Gợi ý trả lời:** Arity xác định số value mà parser thu thập cho một option occurrence, không xác định số lần key có thể lặp.

**Câu 3.** Khi nào dùng `ONE_OR_MORE` và khi nào dùng `ZERO_OR_MORE`?

**Gợi ý trả lời:** `ONE_OR_MORE` yêu cầu ít nhất một value; `ZERO_OR_MORE` cho phép không có value hoặc có nhiều value.

**Câu 4.** `--tag` và `-t` được khai báo làm alias có phải là hai option riêng không?

**Gợi ý trả lời:** Không. Chúng là hai cách gọi của cùng một option và cùng ánh xạ đến một tham số.

**Câu 5.** Nếu sản phẩm bắt buộc hỗ trợ `--tag a --tag b`, cần làm gì?

**Gợi ý trả lời:** Xác nhận parser hiện tại có hỗ trợ hay không. Nếu không, định nghĩa rõ quy tắc tích lũy và dùng parser tùy chỉnh ở phiên bản có điểm mở rộng phù hợp; đồng thời kiểm thử các trường hợp lặp, thiếu value và alias.

## Kết luận

Trong Spring Shell, truyền nhiều value cho một option và lặp lại key là hai hành vi khác nhau. Arity điều khiển số value mà một lần xuất hiện của option nhận; nó không biến nhiều lần xuất hiện của cùng key thành một danh sách. Với Spring Shell 3.x, hãy dùng kiểu mảng hoặc collection kết hợp `OptionArity` hay min/max arity để mô tả option đa giá trị. Không dựa vào cú pháp repeated-key để tích lũy giá trị nếu parser không công bố hỗ trợ.

Hãy công bố rõ grammar của command, đặt giới hạn arity phù hợp, phân biệt alias với option độc lập và kiểm thử parser qua các tình huống biên. Nếu ứng dụng cần semantics lặp key riêng, hãy triển khai nó như một quy tắc parser có chủ đích thay vì để hành vi phụ thuộc vào suy đoán của người dùng.

## Tài liệu tham khảo

- [Spring Shell 3.1.3 — Arity và option parsing](https://docs.spring.io/spring-shell/docs/3.1.3/docs/index.html)
- [Spring Shell 3.4 — `@Option` API](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/command/annotation/Option.html)
- [Spring Shell 3.4 — `CommandRegistration.OptionArity` API](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/command/CommandRegistration.OptionArity.html)
- [Spring Shell 3.4 — `CommandRegistration` API](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/command/CommandRegistration.html)
- [Spring Shell 4.x — Command Syntax](https://docs.spring.io/spring-shell/reference/commands/syntax.html)
- [Spring Shell 4.x — `@Option` API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/annotation/Option.html)
