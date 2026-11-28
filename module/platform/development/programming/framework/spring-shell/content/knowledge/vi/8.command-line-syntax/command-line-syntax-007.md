# Giá trị bắt đầu bằng dấu gạch nối và số âm

Trong Spring Shell, dấu gạch nối ở đầu token thường biểu thị một option: `-n` là dạng ngắn và `--name` là dạng dài. Vì vậy, khi giá trị của option cũng bắt đầu bằng dấu gạch nối, người đọc và parser có thể khó phân biệt đâu là tên option, đâu là dữ liệu.

Cách viết rõ ràng nhất là gắn giá trị với option bằng dấu bằng (`=`):

- Số âm: `--amount=-12`
- Chuỗi bắt đầu bằng một dấu gạch nối: `--label=-draft`
- Chuỗi bắt đầu bằng hai dấu gạch nối: `--label=--dry-run`

Spring Shell hỗ trợ cả dạng `--key=value` và `--key value`, nhưng dạng có dấu bằng đặc biệt hữu ích khi giá trị tự nó bắt đầu bằng `-`. Bài học này giải thích cách phân biệt cú pháp với dữ liệu, cách truyền số âm và chuỗi có tiền tố dấu gạch nối, cùng các trường hợp cần kiểm tra parser.

## 1. Vì sao dấu gạch nối dễ gây nhầm lẫn?

Trong cú pháp dòng lệnh, dấu gạch nối được dùng để nhận diện option:

| Cách viết | Ý nghĩa thường gặp |
|---|---|
| `-n` | Option dạng ngắn |
| `--name` | Option dạng dài |
| `--name=Lan` | Option `name` có giá trị `Lan` |
| `--name Lan` | Option `name` nhận giá trị ở token kế tiếp |

Khi token kế tiếp bắt đầu bằng dấu gạch nối, chẳng hạn `-12` hoặc `--dry-run`, token đó có hình thức giống một option khác. Điều này đặc biệt dễ gặp khi giá trị là:

- Số âm như `-1`, `-12`, `-3.5`.
- Tên cờ hoặc tham số được lưu dưới dạng chuỗi như `--dry-run`, `--no-cache`.
- Tên file hoặc đường dẫn tương đối bắt đầu bằng dấu gạch nối như `-backup.csv`.
- Mẫu, biểu thức hoặc chuỗi cấu hình có ký tự đầu tiên là `-`.

Cần phân biệt hai lớp xử lý. Parser trước hết xác định cấu trúc command và option; sau đó Spring Shell mới chuyển giá trị đã nhận được sang kiểu Java như `int`, `double` hoặc `String`. Một số âm hợp lệ về mặt số học vẫn có thể gây nhầm lẫn ở bước phân tích cú pháp nếu được đặt sai vị trí.

## 2. Cú pháp option được Spring Shell hỗ trợ

Default parser của Spring Shell 4 hỗ trợ option dạng dài và dạng ngắn:

| Dạng | Cú pháp | Ví dụ |
|---|---|---|
| Option dài, gắn giá trị bằng dấu bằng | `--key=value` | `--name=Lan` |
| Option dài, giá trị ở token sau | `--key value` | `--name Lan` |
| Option ngắn, gắn giá trị bằng dấu bằng | `-k=value` | `-n=Lan` |
| Option ngắn, giá trị ở token sau | `-k value` | `-n Lan` |

Các option và argument có thể xuất hiện theo nhiều thứ tự. Tuy nhiên, khi một token dữ liệu cũng bắt đầu bằng dấu gạch nối, nên dùng dạng gắn trực tiếp bằng dấu bằng để thể hiện ranh giới rõ ràng giữa tên option và giá trị.

Ví dụ:

```text
--amount=-12
--label=--dry-run
-n=-draft
```

Trong mỗi trường hợp, parser nhận diện phần bên trái dấu bằng là option và phần bên phải là giá trị của option. Dấu gạch nối bên trong giá trị không còn đứng ở vị trí bắt đầu của một token độc lập.

## 3. Truyền số âm cho option kiểu số

Giả sử ứng dụng có command nhận một giá trị điều chỉnh kiểu `int`:

```java
package com.example.projectcli.command;

import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.Option;
import org.springframework.stereotype.Component;

@Component
public class NumericCommands {

    @Command(
        name = "math adjust",
        description = "Hiển thị giá trị điều chỉnh"
    )
    public String adjust(
            @Option(longName = "amount", shortName = 'a', required = true)
            int amount) {
        return "amount = " + amount;
    }
}
```

Có thể gọi command bằng option dài hoặc ngắn:

```text
math adjust --amount=-12
math adjust -a=-12
```

Kết quả:

```text
amount = -12
```

Dấu bằng giúp parser gắn `-12` với option `amount`. Sau khi parser tách được giá trị, bộ chuyển đổi kiểu mới chuyển chuỗi `"-12"` thành số nguyên `-12`.

Với kiểu `double`, cách viết tương tự:

```text
math adjust --amount=-3.75
```

Nếu dùng dạng tách token `--amount -12`, token `-12` có hình thức giống một short option theo quy tắc parser. Vì vậy, không nên dựa vào cách viết này khi cần bảo đảm giá trị âm được hiểu là dữ liệu. Hãy ưu tiên `--amount=-12`.

### 3.1. Giá trị âm vẫn phải hợp lệ theo quy tắc nghiệp vụ

Parser và bộ chuyển đổi kiểu chỉ xác định cú pháp và kiểu dữ liệu. Chúng không quyết định số âm có được phép trong nghiệp vụ hay không.

Ví dụ, một command có thể chấp nhận số âm để biểu diễn độ lệch hoặc khoản điều chỉnh. Một command khác có thể yêu cầu số lượng lớn hơn hoặc bằng 0. Nếu có ràng buộc như vậy, hãy khai báo validation tương ứng:

```java
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.Option;
import org.springframework.stereotype.Component;

@Component
public class InventoryCommands {

    @Command(name = "inventory reserve")
    public String reserve(
            @Option(longName = "quantity", required = true)
            @jakarta.validation.constraints.Positive int quantity) {
        return "Reserved " + quantity;
    }
}
```

Trong trường hợp này, `--quantity=-2` được viết đúng cú pháp của option có giá trị âm, nhưng bị từ chối bởi quy tắc validation vì số lượng phải dương. Đây là hai kết quả khác nhau: lỗi cú pháp và lỗi dữ liệu nghiệp vụ.

## 4. Truyền chuỗi bắt đầu bằng một hoặc hai dấu gạch nối

Với option kiểu `String`, giá trị bắt đầu bằng dấu gạch nối vẫn là dữ liệu hợp lệ nếu được gắn rõ với option.

Ví dụ:

```java
@Component
public class LabelCommands {

    @Command(
        name = "label set",
        description = "Thiết lập nhãn"
    )
    public String set(
            @Option(longName = "value", required = true)
            String value) {
        return "label = [" + value + "]";
    }
}
```

Gọi command:

```text
label set --value=-draft
label set --value=--dry-run
```

Kết quả:

```text
label = [-draft]
label = [--dry-run]
```

Đây là cách phù hợp khi giá trị chuỗi là tên cờ, tên tham số hoặc một chuỗi cần giữ nguyên tiền tố dấu gạch nối. Không bỏ dấu gạch nối khỏi giá trị chỉ để làm parser dễ nhận diện, vì như vậy sẽ thay đổi dữ liệu mà command nhận được.

Một số ví dụ khác:

| Giá trị cần truyền | Cách gọi rõ ràng |
|---|---|
| `-draft` | `label set --value=-draft` |
| `--dry-run` | `label set --value=--dry-run` |
| `-backup.csv` | `label set --value=-backup.csv` |
| `--no-cache` | `label set --value=--no-cache` |

## 5. Giá trị bắt đầu bằng dấu gạch nối và có khoảng trắng

Nếu giá trị có khoảng trắng, cần đặt toàn bộ giá trị trong dấu nháy đơn hoặc nháy kép. Có thể kết hợp cách này với dấu bằng:

```text
label set --value="-draft mode"
label set --value='--dry run'
```

Parser loại bỏ cặp dấu nháy bao quanh, nên command nhận được các giá trị:

```text
-draft mode
--dry run
```

Dấu nháy có nhiệm vụ giữ khoảng trắng bên trong một giá trị thành một đơn vị. Dấu bằng có nhiệm vụ gắn giá trị với option. Hai cơ chế giải quyết hai vấn đề khác nhau và có thể dùng cùng nhau.

Nếu cần đưa dấu nháy vào bên trong giá trị, hãy dùng ký tự escape theo quy tắc trích dẫn của parser. Ví dụ, khi toàn bộ giá trị được bao bởi dấu nháy kép, dấu nháy kép nằm bên trong cần được escape bằng dấu gạch chéo ngược:

```text
label set --value="--message=\"draft\""
```

Giá trị chuỗi mà command nhận được là:

```text
--message="draft"
```

Quy tắc escape chỉ nên áp dụng khi thật sự cần. Với các giá trị có nhiều dấu nháy hoặc dấu gạch chéo, hãy kiểm tra kết quả nhận được bằng một command đơn giản trước khi đưa vào script.

## 6. Giá trị bắt đầu bằng dấu gạch nối trong argument vị trí

Argument vị trí không có tên option đi kèm. Ví dụ một command có thể khai báo:

```java
import org.springframework.shell.core.command.annotation.Argument;
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.stereotype.Component;

@Component
public class MathCommands {

    @Command(name = "math absolute")
    public int absolute(@Argument(index = 0) int value) {
        return Math.abs(value);
    }
}
```

Một lời gọi như:

```text
math absolute 12
```

có thể được hiểu rõ là argument vị trí thứ nhất. Nhưng token `-12` bắt đầu bằng dấu gạch nối, trùng với tiền tố của short option theo cú pháp parser.

Vì vậy, không nên mặc định rằng:

```text
math absolute -12
```

luôn được hiểu là argument số âm. Cần kiểm tra hành vi của parser và cấu hình command trong phiên bản Spring Shell đang dùng. Nếu có thể thay đổi hợp đồng CLI, hãy chuyển giá trị đó thành named option:

```text
math absolute --value=-12
```

và khai báo `@Option(longName = "value")` tương ứng. Named option thể hiện rõ dữ liệu đang được gán vào tham số nào.

Không nên tự giả định rằng token `--` luôn là dấu kết thúc danh sách option trong Spring Shell. Tài liệu cú pháp của DefaultCommandParser mô tả option và argument nhưng không công bố `--` như một dấu phân cách kết thúc option. Nếu ứng dụng cần quy tắc đó, hãy kiểm tra parser cụ thể hoặc triển khai một `CommandParser` tùy chỉnh.

## 7. Phân biệt các tình huống và cách xử lý

| Tình huống | Cách viết nên dùng | Lý do |
|---|---|---|
| Option số nguyên nhận số âm | `--amount=-12` | Giá trị được gắn trực tiếp với option |
| Option số thực nhận số âm | `--ratio=-0.75` | Không để token âm đứng độc lập |
| Option chuỗi nhận `-draft` | `--value=-draft` | Dấu gạch nối thuộc về dữ liệu |
| Option chuỗi nhận `--dry-run` | `--value=--dry-run` | Tránh bị hiểu là một option khác |
| Giá trị có dấu gạch nối và khoảng trắng | `--value="-draft mode"` | Dấu nháy giữ giá trị thành một token |
| Argument vị trí là số âm | Kiểm tra parser; cân nhắc chuyển thành named option | Token âm có thể trùng cú pháp short option |

Một quy tắc thực hành dễ nhớ: khi giá trị bắt đầu bằng `-`, gắn nó trực tiếp với option bằng `=`. Khi giá trị có khoảng trắng, thêm dấu nháy bao quanh toàn bộ giá trị. Nếu giá trị là argument vị trí, cần xác minh rõ cách parser nhận diện token âm.

## 8. Kiểm tra khi command không nhận đúng giá trị

Khi một command nhận sai giá trị hoặc báo lỗi không mong muốn, hãy kiểm tra theo thứ tự:

1. **Kiểm tra dấu gạch nối.** Dùng dấu gạch nối ASCII `-` (U+002D). Không thay bằng dấu trừ toán học `−` hoặc en dash `–`.
2. **Kiểm tra ranh giới option và giá trị.** Thử dạng `--option=-12` hoặc `--option=--dry-run`.
3. **Kiểm tra khoảng trắng.** Nếu giá trị chứa khoảng trắng, bao toàn bộ giá trị trong dấu nháy.
4. **Kiểm tra kiểu tham số.** Chuỗi `"-12"` phải được chuyển sang kiểu số phù hợp; chuỗi `"--dry-run"` chỉ có thể được giữ nguyên nếu tham số là `String` hoặc converter tương ứng.
5. **Kiểm tra validation.** Giá trị có thể được parse thành công nhưng vẫn vi phạm ràng buộc như `@Positive`, `@Min` hoặc quy tắc nghiệp vụ.
6. **Kiểm tra phiên bản.** Đối chiếu với cú pháp và parser của đúng phiên bản Spring Shell mà ứng dụng đang dùng.
7. **Kiểm tra cách chạy.** Khi chạy command qua script hoặc qua terminal hệ điều hành, lớp shell bên ngoài cũng có thể xử lý dấu nháy và escape. Hãy phân biệt lỗi do shell bên ngoài với lỗi do Spring Shell.

Nếu cú pháp mặc định không đáp ứng hợp đồng CLI cần thiết, Spring Shell 4 cung cấp extension point `CommandParser`. Ứng dụng có thể triển khai parser riêng và đăng ký thành bean trong ApplicationContext để điều chỉnh cách phân biệt option và argument. Chỉ nên làm vậy khi đã xác định rõ quy tắc cần thay đổi và có kiểm thử cho các trường hợp nhập hợp lệ lẫn không hợp lệ.

## 9. Checklist thiết kế command có giá trị bắt đầu bằng dấu gạch nối

- [ ] Giá trị âm được truyền qua named option khi có thể.
- [ ] Option và giá trị được nối bằng dấu bằng khi giá trị bắt đầu bằng `-`.
- [ ] Chuỗi như `--dry-run` được giữ nguyên khi command nhận kiểu `String`.
- [ ] Giá trị có khoảng trắng được bao bằng dấu nháy.
- [ ] Dùng dấu gạch nối ASCII, tránh ký tự gạch ngang thay thế.
- [ ] Kiểu Java phù hợp với giá trị được truyền.
- [ ] Validation phản ánh đúng quy tắc nghiệp vụ đối với số âm.
- [ ] Argument vị trí bắt đầu bằng dấu gạch nối đã được kiểm tra với parser thực tế.
- [ ] Script và cách gọi từ terminal bên ngoài đã được kiểm tra riêng.
- [ ] Parser tùy chỉnh chỉ được bổ sung khi cú pháp mặc định không đáp ứng yêu cầu.

## 10. Tài liệu tham khảo

- [Spring Shell — Command Syntax](https://docs.spring.io/spring-shell/reference/commands/syntax.html): quy tắc phân tích option dạng dài, dạng ngắn, argument và khả năng thay thế DefaultCommandParser.
- [Spring Shell — DefaultCommandParser API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/DefaultCommandParser.html): cú pháp mặc định và phương thức `parse(String)`.
- [Spring Shell — CommandParser API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/CommandParser.html): extension point để ứng dụng tự định nghĩa cách phân tích command.
- [Spring Shell — Option annotation API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/annotation/Option.html): khai báo tên ngắn, tên dài, kiểu bắt buộc và giá trị mặc định.

Khi truyền số âm hoặc chuỗi bắt đầu bằng dấu gạch nối, hãy làm rõ ranh giới giữa option và dữ liệu. Cú pháp `--option=value` là lựa chọn dễ đọc và ít mơ hồ nhất cho các trường hợp này; dấu nháy được thêm khi giá trị có khoảng trắng. Với argument vị trí bắt đầu bằng dấu gạch nối, cần xác minh hành vi parser hoặc chuyển sang named option để hợp đồng CLI rõ ràng hơn.

