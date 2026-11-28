# Mảng, Collection và cách phân tách nhiều giá trị

Một command Spring Shell có thể nhận nhiều giá trị theo hai cách chính: thu thập nhiều argument vị trí vào một mảng hoặc Collection bằng `@Arguments`, hoặc nhận một chuỗi từ option rồi tự phân tách chuỗi đó theo dấu phân cách đã quy ước.

Hai cách này giải quyết hai nhu cầu khác nhau. `@Arguments` thu thập nhiều token mà người dùng nhập trên dòng lệnh; cách phân tách chuỗi xử lý một giá trị duy nhất có nội dung như `backend,urgent,release`. Chọn đúng cách giúp hợp đồng CLI rõ ràng, dễ kiểm tra và dễ dùng trong script.

Bài học sử dụng annotation declarative của Spring Shell 4.x, với API được đối chiếu theo tài liệu 4.0.4.

## 1. Khi nào cần nhận nhiều giá trị?

Một command thường nhận một option hoặc argument đơn lẻ, chẳng hạn tên project hay mã người dùng. Một số thao tác cần nhận nhiều phần tử:

- Gửi thông báo cho nhiều người nhận.
- Gắn nhiều nhãn cho một issue.
- Chọn nhiều mã sản phẩm để xuất dữ liệu.
- Tính toán trên một dãy số.
- Nhận nhiều file đầu vào trong một lần chạy.

Ví dụ, người dùng muốn truyền ba tên project:

```text
project export alpha beta gamma
```

Hoặc muốn truyền danh sách nhãn qua một option:

```text
issue create --tags=backend,urgent,release
```

Ở lệnh đầu, các giá trị là nhiều token vị trí. Ở lệnh thứ hai, option `tags` nhận một chuỗi duy nhất chứa dấu phẩy; ứng dụng sẽ tách chuỗi đó thành danh sách nhãn.

## 2. Dùng @Arguments để thu thập nhiều argument vị trí

Spring Shell 4.x cung cấp annotation `@Arguments` cho tham số phương thức có kiểu mảng hoặc Collection. Framework thu thập các token argument còn lại của command và chuyển chúng thành các phần tử của tham số đó.

Ví dụ dùng mảng:

```java
import java.util.Arrays;

import org.springframework.shell.core.command.annotation.Arguments;
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.stereotype.Component;

@Component
public class ProjectCommands {

    @Command(
        name = "project export",
        description = "Xuất dữ liệu của nhiều project"
    )
    public String export(
            @Arguments(description = "Các mã project cần xuất")
            String[] projectCodes) {

        return "Exporting: " + Arrays.toString(projectCodes);
    }
}
```

Người dùng gọi:

```text
project export alpha beta gamma
```

Tham số `projectCodes` nhận mảng:

```text
["alpha", "beta", "gamma"]
```

`@Arguments` phù hợp khi command cần thu thập một số lượng argument thay đổi theo đầu vào. Với kiểu mảng, dùng `Arrays.toString(...)` để hiển thị nội dung; nối trực tiếp mảng vào chuỗi sẽ hiển thị kiểu và địa chỉ tham chiếu thay vì các phần tử.

## 3. Dùng Collection như List hoặc Set

Tham số đánh dấu `@Arguments` cũng có thể dùng kiểu Collection, chẳng hạn `List<String>` hoặc `Set<String>`.

Ví dụ dùng `List<String>`:

```java
import java.util.List;

import org.springframework.shell.core.command.annotation.Arguments;
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.stereotype.Component;

@Component
public class NotificationCommands {

    @Command(
        name = "notify",
        description = "Gửi thông báo cho nhiều người nhận"
    )
    public String notify(
            @Arguments(description = "Danh sách người nhận")
            List<String> recipients) {

        if (recipients.isEmpty()) {
            throw new IllegalArgumentException(
                "Cần cung cấp ít nhất một người nhận"
            );
        }

        return "Recipients: " + String.join(", ", recipients);
    }
}
```

Lệnh gọi:

```text
notify alice@example.com bob@example.com carol@example.com
```

Kết quả:

```text
Recipients: alice@example.com, bob@example.com, carol@example.com
```

Chọn kiểu dữ liệu theo yêu cầu xử lý:

| Kiểu tham số | Khi phù hợp |
|---|---|
| `String[]` | Cần mảng có kích thước cố định sau khi nhận dữ liệu hoặc dùng API yêu cầu mảng |
| `List<String>` | Cần giữ thứ tự nhập và có thể thêm, xóa hoặc duyệt phần tử |
| `Set<String>` | Cần tập phần tử duy nhất, không muốn giữ các giá trị trùng lặp |

Nếu thứ tự người dùng nhập có ý nghĩa, ưu tiên mảng hoặc `List`. `Set` loại bỏ phần tử trùng theo quy tắc equality của phần tử; không nên chọn Set nếu cần giữ nguyên mọi lần xuất hiện của giá trị.

## 4. Kiểm soát số lượng bằng arity

Mặc định, `@Arguments` thu thập tất cả argument còn lại của command. Thuộc tính `arity` cho phép giới hạn số token tối đa được thu thập vào tham số đó.

Ví dụ:

```java
@Command(name = "math sum-pair")
public double sumPair(
        @Arguments(arity = 2) double[] numbers) {

    if (numbers.length != 2) {
        throw new IllegalArgumentException(
            "Cần truyền đúng hai số"
        );
    }

    return numbers[0] + numbers[1];
}
```

Lệnh gọi:

```text
math sum-pair 12 30
```

Kết quả:

```text
42.0
```

Với `@Arguments(arity = 2)`, framework thu thập tối đa hai argument cho tham số đó. `arity` là giới hạn trên của số argument được thu thập; nếu nghiệp vụ yêu cầu chính xác hai giá trị, command vẫn nên kiểm tra số phần tử nhận được.

Thuộc tính `arity` được bổ sung từ Spring Shell 4.0.2. Nếu dự án dùng bản 4.0.0 hoặc 4.0.1, hãy kiểm tra API của bản đang dùng trước khi sử dụng thuộc tính này.

### 4.1. Chia nhiều nhóm giá trị bằng nhiều tham số @Arguments

Có thể khai báo nhiều tham số `@Arguments` khi mỗi tham số có giới hạn arity riêng. Cách này hữu ích khi command nhận các nhóm giá trị có ý nghĩa khác nhau.

Ví dụ tính phần thực của tích hai số phức:

```java
import org.springframework.shell.core.command.annotation.Arguments;
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.stereotype.Component;

@Component
public class ComplexNumberCommands {

    @Command(name = "complex real-product")
    public double realPartOfProduct(
            @Arguments(arity = 2) double[] realParts,
            @Arguments(arity = 2) double[] imaginaryParts) {

        if (realParts.length != 2 || imaginaryParts.length != 2) {
            throw new IllegalArgumentException(
                "Cần truyền hai phần thực và hai phần ảo"
            );
        }

        return realParts[0] * realParts[1]
                - imaginaryParts[0] * imaginaryParts[1];
    }
}
```

Lệnh gọi:

```text
complex real-product 1 2 3 4
```

Hai phần tử đầu được đưa vào `realParts`; hai phần tử tiếp theo được đưa vào `imaginaryParts`. Kết quả là:

```text
-10.0
```

Khi dùng nhiều tham số `@Arguments`, hãy đặt arity rõ ràng để ranh giới giữa các nhóm không mơ hồ. Không nên để nhiều tham số cùng thu thập toàn bộ argument còn lại.

## 5. Kết hợp @Arguments với @Option

Argument vị trí và option có tên có thể cùng xuất hiện trong một command. Spring Shell cho phép option và argument xuất hiện theo nhiều thứ tự; `@Arguments` thu thập các token vị trí còn lại.

Ví dụ, cho phép người dùng chọn kênh gửi thông báo và truyền nhiều người nhận:

```java
import java.util.List;

import org.springframework.shell.core.command.annotation.Arguments;
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.Option;
import org.springframework.stereotype.Component;

@Component
public class NotificationCommands {

    @Command(name = "notify")
    public String notify(
            @Option(
                longName = "channel",
                defaultValue = "email",
                description = "Kênh gửi thông báo"
            ) String channel,
            @Arguments(description = "Danh sách người nhận")
            List<String> recipients) {

        if (recipients.isEmpty()) {
            throw new IllegalArgumentException(
                "Cần ít nhất một người nhận"
            );
        }

        return "Channel: " + channel
                + "; recipients: " + String.join(", ", recipients);
    }
}
```

Hai cách gọi sau đều có thể dùng:

```text
notify --channel=email alice@example.com bob@example.com
notify alice@example.com bob@example.com --channel=email
```

`@Option` đại diện cho giá trị có tên; `@Arguments` đại diện cho các giá trị vị trí. Nên dùng option cho cấu hình có ý nghĩa rõ ràng như kênh gửi, định dạng hoặc chế độ thực thi; dùng arguments cho danh sách phần tử chính mà command thao tác.

## 6. Tách nhiều giá trị từ một option bằng dấu phân cách

Không phải lúc nào người dùng cũng muốn gõ mỗi phần tử thành một token riêng. Đôi khi một option cần nhận một chuỗi có nhiều giá trị, ví dụ:

```text
issue create --tags=backend,urgent,release
```

Trong trường hợp này, `@Option` nhận một giá trị chuỗi. Ứng dụng tự tách chuỗi theo dấu phẩy và chuyển thành Collection.

Trong annotation API Spring Shell 4.0.4, `@Option` không có thuộc tính `arity`. Không sao chép trực tiếp ví dụ `@ShellOption(arity = ...)` từ mô hình legacy vào `@Option` của 4.x. Với nhiều argument vị trí, dùng `@Arguments`; với một option chứa danh sách trong cùng chuỗi, nhận `String` rồi tách theo delimiter do ứng dụng quy định.

Ví dụ:

```java
import java.util.ArrayList;
import java.util.List;

import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.Option;
import org.springframework.stereotype.Component;

@Component
public class IssueCommands {

    @Command(name = "issue create")
    public String create(
            @Option(longName = "tags", required = true)
            String rawTags) {

        List<String> tags = new ArrayList<>();

        for (String token : rawTags.split(",", -1)) {
            String tag = token.trim();

            if (tag.isEmpty()) {
                throw new IllegalArgumentException(
                    "Danh sách tags không được chứa phần tử rỗng"
                );
            }

            tags.add(tag);
        }

        return "Tags: " + String.join(", ", tags);
    }
}
```

Lệnh gọi:

```text
issue create --tags="backend, urgent, release"
```

Sau khi tách và loại bỏ khoảng trắng ở hai đầu, ứng dụng nhận:

```text
["backend", "urgent", "release"]
```

Trong ví dụ này:

- `rawTags` là một chuỗi duy nhất mà parser chuyển vào tham số option.
- `split(",", -1)` tách chuỗi theo dấu phẩy và giữ lại phần tử rỗng ở cuối để có thể kiểm tra dữ liệu sai.
- `trim()` loại bỏ khoảng trắng thừa quanh từng phần tử.
- Kiểm tra `isEmpty()` giúp phát hiện đầu vào như `backend,,release` hoặc `backend,`.

Dấu phẩy không tự động biến một option đơn thành nhiều tham số Java. Việc tách là quy tắc do ứng dụng định nghĩa. Nếu chọn dấu phẩy làm delimiter, hãy ghi rõ trong mô tả hoặc help của command để người dùng biết cách nhập.

## 7. Chọn delimiter phù hợp

Delimiter là ký tự hoặc chuỗi phân cách các phần tử trong một giá trị. Dấu phẩy thường dễ đọc, nhưng không phù hợp với mọi loại dữ liệu.

| Delimiter | Ví dụ đầu vào | Khi phù hợp |
|---|---|---|
| Dấu phẩy | `--tags=backend,urgent,release` | Tên nhãn ngắn, không chứa dấu phẩy |
| Dấu chấm phẩy | `--paths=src;test;docs` | Dữ liệu thường có dấu phẩy bên trong |
| Dấu hai chấm | `--coordinates=10:20:30` | Chuỗi có cấu trúc cố định, không chứa dấu hai chấm |
| Token khoảng trắng | `command one two three` | Muốn mỗi phần tử là một argument riêng, dùng `@Arguments` |

Không chọn delimiter chỉ vì nó dễ gõ. Hãy xét xem dữ liệu thực tế có thể chứa delimiter đó hay không. Nếu giá trị phần tử có thể chứa chính delimiter, cần định nghĩa quy tắc escape hoặc dùng định dạng có cấu trúc như JSON.

Lưu ý rằng `String.split()` nhận biểu thức chính quy, không nhận delimiter dạng ký tự thuần. Với delimiter có ý nghĩa đặc biệt trong regex như dấu chấm hoặc dấu gạch đứng, hãy dùng `Pattern.quote(delimiter)`:

```java
String[] values = rawValue.split(Pattern.quote(delimiter), -1);
```

Đoạn mã này cần import `java.util.regex.Pattern`. Với dấu phẩy hoặc dấu chấm phẩy, có thể truyền trực tiếp vào `split()` như các ví dụ trước.

### 7.1. Giới hạn của cách split đơn giản

Ví dụ `--tags=backend,urgent,release` có thể tách bằng `split(",")` vì mỗi nhãn không chứa dấu phẩy. Nhưng nếu một giá trị hợp lệ là `"customer, priority"`, cách split đơn giản sẽ chia nó thành hai phần tử.

Dấu nháy của command parser chỉ giúp giữ khoảng trắng trong một option value; nó không tự động biến dấu phẩy thành delimiter có khả năng escape. Nếu cần hỗ trợ delimiter nằm bên trong dữ liệu, hãy thiết kế một định dạng rõ ràng, chẳng hạn:

- Dùng JSON array: `--tags='["backend","customer, priority"]'`.
- Dùng dấu phân cách khác mà dữ liệu không sử dụng.
- Định nghĩa cú pháp escape và viết parser cho định dạng đó.

Với JSON, ứng dụng cần parse chuỗi bằng thư viện JSON và xử lý lỗi định dạng. Không nên dùng `split(",")` cho một định dạng lồng nhau hoặc có quy tắc escape phức tạp.

## 8. Phân biệt nhiều token và một chuỗi chứa delimiter

Hai lệnh dưới đây có thể biểu diễn cùng một danh sách, nhưng hợp đồng đầu vào khác nhau:

```text
project export alpha beta gamma
project export --codes=alpha,beta,gamma
```

| Tiêu chí | `@Arguments` | Option có delimiter |
|---|---|---|
| Đầu vào | Nhiều token vị trí | Một chuỗi option |
| Cách khai báo | `@Arguments String[]` hoặc Collection | `@Option String` |
| Tách phần tử | Spring Shell thu thập token | Ứng dụng tự tách chuỗi |
| Giữ thứ tự | Có với array/List | Có nếu ứng dụng dùng List |
| Kiểm tra phần tử rỗng | Kiểm tra Collection sau khi bind | Kiểm tra sau khi split |
| Dữ liệu có delimiter bên trong | Không liên quan đến delimiter chuỗi | Cần quy tắc escape hoặc định dạng khác |

Hãy chọn `@Arguments` khi mỗi phần tử tự nhiên là một token. Chọn delimiter khi muốn truyền cả danh sách qua một option duy nhất, đặc biệt khi option đó là một phần của cấu hình command.

## 9. Dùng dấu nháy khi phần tử chứa khoảng trắng

Spring Shell tách input thành các từ dựa trên khoảng trắng. Nếu một phần tử có khoảng trắng, hãy đặt phần tử đó trong dấu nháy đơn hoặc nháy kép.

Ví dụ dùng `@Arguments List<String>`:

```text
notify "Alice Nguyen" "Bob Tran"
```

Danh sách nhận được gồm hai phần tử:

```text
["Alice Nguyen", "Bob Tran"]
```

Ví dụ dùng option chứa chuỗi delimiter:

```text
issue create --tags="backend, customer priority, release"
```

Sau khi parser bỏ dấu nháy bao quanh, giá trị option là:

```text
backend, customer priority, release
```

Ứng dụng tách theo dấu phẩy thành ba phần tử, trong đó `customer priority` vẫn là một nhãn. Dấu nháy giữ nguyên khoảng trắng; delimiter mới quyết định ranh giới các phần tử.

## 10. Validation và xử lý danh sách

Sau khi nhận mảng hoặc Collection, ứng dụng vẫn cần xác định các quy tắc dữ liệu:

- Danh sách có được để trống không?
- Có giới hạn số phần tử tối đa không?
- Phần tử có được phép trùng lặp không?
- Có cần loại bỏ khoảng trắng đầu/cuối không?
- Có cần kiểm tra định dạng từng phần tử không?
- Có cần xác thực phần tử có tồn tại trong hệ thống không?

Ví dụ kiểm tra danh sách mã project:

```java
private void validateProjectCodes(List<String> codes) {
    if (codes.isEmpty()) {
        throw new IllegalArgumentException(
            "Cần chọn ít nhất một project"
        );
    }

    if (codes.size() > 20) {
        throw new IllegalArgumentException(
            "Chỉ được chọn tối đa 20 project"
        );
    }

    for (String code : codes) {
        if (code.isBlank()) {
            throw new IllegalArgumentException(
                "Mã project không được để trống"
            );
        }
    }
}
```

Với danh sách lấy từ delimiter, kiểm tra phần tử rỗng ngay sau bước split. Với `@Arguments`, kiểm tra kích thước Collection trước khi gọi service nghiệp vụ.

Không nên chỉ kiểm tra số lượng phần tử ở command handler nếu quy tắc đó cũng cần được bảo vệ khi use case được gọi từ REST API hoặc tác vụ nền. Các quy tắc nghiệp vụ quan trọng nên nằm trong application service hoặc domain.

## 11. Lỗi thường gặp

**Dùng @Argument thay vì @Arguments.** `@Argument` ánh xạ một vị trí argument; `@Arguments` thu thập nhiều argument vào mảng hoặc Collection.

**Khai báo @Arguments với kiểu không phải mảng hoặc Collection.** Tham số phải có kiểu mảng hoặc Collection, ví dụ `String[]`, `List<String>` hoặc `Set<String>`.

**Quên rằng @Arguments mặc định thu thập tất cả argument còn lại.** Nếu command còn có các nhóm argument khác, hãy đặt `arity` rõ ràng để chia ranh giới.

**Nhầm arity là số phần tử tối thiểu và tối đa.** Trong API `@Arguments` 4.x, `arity` xác định số lượng tối đa được thu thập vào tham số đó. Nếu cần chính xác một số lượng, kiểm tra kích thước sau khi bind.

**Kỳ vọng option đơn tự tách thành Collection.** `@Option` nhận giá trị theo hợp đồng option. Nếu người dùng truyền `--tags=a,b,c`, ứng dụng phải tự định nghĩa cách tách chuỗi thành danh sách.

**Dùng split(",") mà không xử lý phần tử rỗng.** Đầu vào như `a,,b,` có thể tạo dữ liệu không hợp lệ. Dùng `split(",", -1)` để giữ phần tử rỗng và kiểm tra chúng.

**Không xử lý phần tử có delimiter bên trong.** Nếu dữ liệu có thể chứa dấu phẩy, delimiter đơn giản sẽ làm mất ranh giới mong muốn. Hãy dùng escape hoặc định dạng có cấu trúc.

**Dùng Set khi thứ tự có ý nghĩa.** Set phù hợp để loại bỏ phần tử trùng; nếu cần giữ thứ tự người dùng nhập, dùng array hoặc List.

**Không kiểm tra danh sách rỗng hoặc quá dài.** Collection có thể hợp lệ về cú pháp nhưng không hợp lệ theo nghiệp vụ. Xác định giới hạn và thông báo lỗi rõ ràng.

## 12. Checklist thiết kế command nhận nhiều giá trị

- [ ] Dùng `@Arguments` cho nhiều argument vị trí.
- [ ] Chọn mảng, List hoặc Set theo yêu cầu về thứ tự và tính duy nhất.
- [ ] Đặt `arity` khi cần giới hạn số token cho từng nhóm argument.
- [ ] Nhớ rằng `arity` của `@Arguments` là giới hạn tối đa.
- [ ] Dùng `@Option` cho cấu hình có tên.
- [ ] Nếu option chứa danh sách trong một chuỗi, công bố delimiter rõ ràng.
- [ ] Tách chuỗi và kiểm tra phần tử rỗng, khoảng trắng và dữ liệu trùng.
- [ ] Dùng dấu nháy cho phần tử có khoảng trắng.
- [ ] Định nghĩa escape hoặc định dạng có cấu trúc nếu phần tử có thể chứa delimiter.
- [ ] Kiểm tra số lượng phần tử và quy tắc nghiệp vụ trước khi gọi service.
- [ ] Dùng named option khi cần tránh nhầm lẫn với argument vị trí.

## 13. Tài liệu tham khảo chính thức

- [Spring Shell 4.0.4 — Command Syntax](https://docs.spring.io/spring-shell/reference/commands/syntax.html): khai báo option, argument, `@Arguments`, arity, thứ tự token, quoting và escaping.
- [Spring Shell 4.0.4 — Arguments API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/annotation/Arguments.html): kiểu tham số được hỗ trợ, giới hạn arity và description.
- [Spring Shell 4.0.4 — Option API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/annotation/Option.html): tên option, required và default value.

Khi command cần nhiều giá trị, hãy xác định người dùng đang truyền nhiều token hay một chuỗi chứa danh sách. `@Arguments` xử lý trường hợp đầu bằng cách bind các token vào mảng hoặc Collection; delimiter xử lý trường hợp sau và cần được ứng dụng tách, kiểm tra theo một quy ước rõ ràng.

