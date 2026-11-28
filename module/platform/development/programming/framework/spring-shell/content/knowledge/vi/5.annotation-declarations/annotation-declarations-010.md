# `@Argument` và `@Arguments` cho đối số vị trí ở Spring Shell 4.x

Một command dòng lệnh thường nhận hai loại dữ liệu: option có tên như `--format json` và đối số vị trí như `copy source.txt backup/source.txt`. Spring Shell 4.x dùng `@Option` để khai báo option có tên, `@Argument` để nhận một đối số vị trí tại chỉ số xác định và `@Arguments` để gom nhiều đối số vị trí vào một mảng hoặc collection.

Hai annotation `@Argument` và `@Arguments` giải quyết hai nhu cầu khác nhau. Dùng `@Argument` khi mỗi vị trí có ý nghĩa riêng, chẳng hạn nguồn và đích của thao tác sao chép. Dùng `@Arguments` khi command nhận một danh sách giá trị có cùng vai trò, chẳng hạn nhiều tên file hoặc nhiều tên người dùng. Bài học này xây dựng các ví dụ theo mô hình annotation mới của Spring Shell 4.x.

## 1. Xác định đúng mô hình annotation của Spring Shell 4

Spring Shell 4 đã loại bỏ các annotation cũ `@ShellComponent`, `@ShellMethod`, `@ShellOption` và các annotation liên quan. Mô hình khai báo mới dùng `@Command`, `@Option`, `@Argument`, `@Arguments` cùng những annotation trong package `org.springframework.shell.core.command.annotation`.

Trong ứng dụng Spring Boot, các phương thức được đánh dấu `@Command` phải nằm trong một Spring-managed bean, thường là lớp có `@Component`. `@Command` được đặt trên phương thức để khai báo command; không đặt `@Command` lên lớp như một số ví dụ cũ ở Spring Shell 3. Khi dùng Spring Boot, việc quét command được tự động cấu hình.

Ví dụ khung command 4.x:

```java
import org.springframework.shell.core.command.annotation.Argument;
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.Option;
import org.springframework.stereotype.Component;

@Component
public class GreetingCommands {

    @Command(name = "hello", description = "Chào một người")
    public String hello(
            @Argument(index = 0, description = "Tên người cần chào") String name) {
        return "Xin chào, " + name + "!";
    }
}
```

Ví dụ này khai báo một command tên `hello`, có một đối số vị trí tại index `0`. Có thể chạy:

```text
hello Ada
```

Kết quả là lời chào dành cho Ada. Những ví dụ trong bài dùng package annotation của Spring Shell 4 và không trộn annotation của mô hình cũ.

## 2. Phân biệt đối số vị trí và option có tên

Đối số vị trí được nhận diện theo thứ tự xuất hiện trong danh sách đối số. Người gọi không cần viết tên cho từng giá trị. Option có tên được nhận diện bằng tên ngắn hoặc dài, vì vậy người gọi có thể diễn đạt rõ ý nghĩa và thường thay đổi thứ tự option mà không ảnh hưởng cách bind.

| Loại | Ví dụ | Annotation | Đặc điểm |
| --- | --- | --- | --- |
| Đối số vị trí đơn | `copy source.txt backup.txt` | `@Argument` | Ý nghĩa được xác định bằng vị trí |
| Nhiều đối số vị trí | `delete a.txt b.txt c.txt` | `@Arguments` | Gom nhiều token vào mảng hoặc collection |
| Option có tên | `--overwrite true` | `@Option` | Có tên rõ ràng, có thể đặt trước hoặc sau đối số |

Đối số vị trí phù hợp với những giá trị chính, ngắn gọn và có thứ tự tự nhiên như `source` rồi `destination`, hoặc danh sách file cần xử lý. Khi command có nhiều tham số tùy chọn, có ý nghĩa dễ nhầm lẫn hoặc thường xuyên mở rộng, hãy ưu tiên option có tên. Tài liệu hướng dẫn CLI cũng khuyến nghị hạn chế positional arguments khi có thể gây mơ hồ, đặc biệt với subcommand.

## 3. Dùng `@Argument` cho từng vị trí cụ thể

`@Argument` đánh dấu một tham số phương thức là một đối số vị trí của command. Annotation yêu cầu thuộc tính `index`, là chỉ số bắt đầu từ `0` trong danh sách đối số vị trí. Annotation cũng có `description` để mô tả đối số và `defaultValue` để khai báo giá trị mặc định.

Ví dụ command sao chép file:

```java
@Component
public class FileCommands {

    @Command(name = "copy-file", description = "Sao chép file đến vị trí đích")
    public String copyFile(
            @Argument(index = 0, description = "Đường dẫn file nguồn") String source,
            @Argument(index = 1, description = "Đường dẫn file đích") String destination,
            @Option(longName = "overwrite", defaultValue = "false") boolean overwrite) {

        // Gọi service để kiểm tra file và thực hiện sao chép.
        return "Đã yêu cầu sao chép " + source + " đến " + destination
                + "; overwrite=" + overwrite;
    }
}
```

Các cách gọi:

```text
copy-file report.txt archive/report.txt
copy-file --overwrite true report.txt archive/report.txt
copy-file report.txt archive/report.txt --overwrite=true
```

Trong cả ba cách gọi, `report.txt` vẫn là đối số ở index `0`, `archive/report.txt` vẫn ở index `1`. Option `--overwrite` không chiếm một vị trí trong danh sách positional arguments. Spring Shell 4 cho phép đặt option và đối số ở các vị trí khác nhau trong dòng lệnh.

Nếu bỏ qua đối số có `index = 0` hoặc `index = 1` mà không có giá trị mặc định, command không có đủ dữ liệu để thực hiện. Hãy mô tả rõ trong help và kiểm thử trường hợp thiếu đối số.

## 4. Giá trị mặc định cho `@Argument`

Khi một đối số cuối có thể bỏ qua, có thể đặt `defaultValue`. Ví dụ command chào người dùng với tên mặc định:

```java
@Component
public class GreetingCommands {

    @Command(name = "greet", description = "Chào một người")
    public String greet(
            @Argument(index = 0,
                    description = "Tên người cần chào",
                    defaultValue = "bạn") String name) {
        return "Xin chào, " + name + "!";
    }
}
```

Có thể gọi:

```text
greet
greet Minh
greet "Nguyễn An"
```

Lệnh đầu dùng giá trị mặc định `bạn`; lệnh thứ hai và thứ ba dùng giá trị người gọi truyền vào. Đối với chuỗi có dấu cách, đặt toàn bộ giá trị trong cặp dấu nháy để parser nhận đó là một token. Spring Shell hỗ trợ dấu nháy đơn và dấu nháy kép; dấu nháy bao ngoài được loại khỏi giá trị sau khi phân tích.

Không đặt giá trị mặc định tùy tiện cho đối số mà việc thiếu nó có thể khiến thao tác nguy hiểm hoặc sai mục đích. Với thao tác xóa, ghi đè hay triển khai, nên yêu cầu người dùng cung cấp rõ dữ liệu cần thiết và có thể bổ sung một option xác nhận riêng.

## 5. Dùng `@Arguments` để nhận một danh sách

`@Arguments` đánh dấu một tham số nhận nhiều positional arguments. Kiểu tham số phải là mảng hoặc collection, chẳng hạn `String[]`, `List<String>` hoặc một collection phù hợp khác. Nếu không chỉ định `arity`, annotation gom tất cả token đối số còn lại vào tham số đó.

Ví dụ lệnh chào nhiều người:

```java
@Component
public class GreetingCommands {

    @Command(name = "greet-many", description = "Chào nhiều người")
    public String greetMany(
            @Option(shortName = 's', longName = "suffix", defaultValue = "!") String suffix,
            @Arguments String[] names) {

        if (names.length == 0) {
            return "Hãy cung cấp ít nhất một tên.";
        }
        return "Xin chào, " + String.join(", ", names) + suffix;
    }
}
```

Ví dụ gọi:

```text
greet-many Ada Grace Linh
greet-many --suffix "?" "Ada Lovelace" "Grace Hopper"
```

Trong ví dụ thứ hai, hai tên có dấu cách được đặt trong dấu nháy, vì vậy mỗi tên vẫn là một đối số. `@Arguments` nhận danh sách các token sau khi parser đã tách dòng lệnh. Với danh sách có thứ tự, `List<String>` hoặc mảng thường phù hợp hơn `Set`, vì `Set` có thể loại phần tử trùng và không phải lúc nào cũng bảo toàn thứ tự.

Do `@Arguments` mặc định gom tất cả token còn lại, hãy đặt nó ở vị trí thiết kế phù hợp. Nếu command cần nhận thêm một đối số vị trí riêng phía sau danh sách, hãy cân nhắc dùng `arity` để giới hạn số token được gom hoặc đổi phần dữ liệu đó thành option có tên.

## 6. Giới hạn số lượng bằng `arity`

Thuộc tính `arity` của `@Arguments` xác định số lượng tối đa token được gom vào tham số collection hoặc mảng đó. Nếu không khai báo, giá trị mặc định cho phép thu thập tất cả đối số còn lại. `arity` được bổ sung từ Spring Shell 4.0.2.

Ví dụ dùng hai nhóm số để tính phần thực của tích hai số phức:

```java
@Component
public class MathCommands {

    @Command(name = "real-part", description = "Tính phần thực của tích hai số phức")
    public double realPartOfProduct(
            @Arguments(arity = 2) double[] realParts,
            @Arguments(arity = 2) double[] imaginaryParts) {

        if (realParts.length != 2 || imaginaryParts.length != 2) {
            throw new IllegalArgumentException("Cần cung cấp đủ bốn giá trị a b c d.");
        }

        // (a + bi)(c + di) có phần thực là ac - bd.
        return realParts[0] * realParts[1]
                - imaginaryParts[0] * imaginaryParts[1];
    }
}
```

Gọi command:

```text
real-part 1 2 3 4
```

Nhóm thứ nhất nhận hai token `1` và `2`; nhóm thứ hai nhận `3` và `4`. Kết quả là `1 × 2 - 3 × 4 = -10`.

Điểm cần nhớ: `arity` được mô tả là số lượng tối đa được thu thập. Không nên xem nó như một khai báo rằng người dùng chắc chắn đã cung cấp đủ số lượng. Nếu nghiệp vụ đòi hỏi đúng N giá trị, hãy kiểm tra độ dài collection/mảng trước khi truy cập phần tử. Kiểm thử cả trường hợp thiếu và thừa token để bảo đảm parser phân phối dữ liệu theo đúng ý định.

## 7. Chỉ số và quy tắc phân tích dòng lệnh

Spring Shell 4 đánh chỉ số positional arguments từ `0`, chỉ tính các đối số vị trí trong danh sách, không tính tên command, tên subcommand hay giá trị của option. Ví dụ:

```text
copy-file --overwrite true "report final.pdf" archive/report.pdf
```

Trong lệnh trên:

- `--overwrite` là option có tên; `true` là giá trị của option.
- `report final.pdf` là đối số vị trí index `0`.
- `archive/report.pdf` là đối số vị trí index `1`.

Parser hỗ trợ dạng option dài `--key=value` hoặc `--key value`, và dạng ngắn `-k=value` hoặc `-k value`. Option và đối số có thể xuất hiện theo thứ tự khác nhau. Tuy nhiên, khi một option được khai báo, nó luôn cần một giá trị, kể cả option kiểu boolean. Vì vậy, dùng `--overwrite true` hoặc `--overwrite=false`; không giả định `--overwrite` đứng một mình là cờ bật. Các option ngắn cũng không được ghép nhóm như `-abc`.

Với chuỗi có khoảng trắng, dùng dấu nháy đơn hoặc kép:

```text
search-files "annual report" "final version"
```

Nếu cần chứa chính dấu nháy bao ngoài trong giá trị, escape bằng dấu gạch chéo ngược theo quy tắc parser. Một dấu nháy không cân bằng sẽ khiến dòng lệnh bị từ chối. Khi viết ví dụ trong README, nên kiểm tra cú pháp trên shell thực tế để tránh nhầm quy tắc quoting của Bash hoặc PowerShell với parser bên trong Spring Shell.

## 8. Chọn `@Argument` hay `@Arguments`?

Hãy quyết định dựa trên ý nghĩa dữ liệu mà command cần nhận:

| Nhu cầu | Cách khai báo phù hợp | Lý do |
| --- | --- | --- |
| Một giá trị có vai trò riêng | `@Argument(index = 0)` | Vị trí xác định, mô tả riêng |
| Hai giá trị nguồn và đích | Hai `@Argument` với index `0`, `1` | Mỗi vị trí có ý nghĩa khác nhau |
| Danh sách file cần xóa | `@Arguments List<String>` | Các giá trị cùng vai trò và số lượng thay đổi |
| Một nhóm có số lượng giới hạn | `@Arguments(arity = N)` | Chỉ gom tối đa N token vào nhóm |
| Nhiều nhóm positional có ranh giới rõ | Nhiều `@Arguments` với `arity` phù hợp | Mỗi nhóm nhận một phần token liên tiếp |
| Giá trị tùy chọn, có nhiều tham số cùng kiểu | `@Option` | Tên option làm rõ ý nghĩa và tránh phụ thuộc thứ tự |

Không nên dùng positional arguments cho một command có quá nhiều chuỗi hoặc số cùng kiểu. Ví dụ `deploy app staging 3 true` khó đọc hơn `deploy --app app --environment staging --replicas 3 --dry-run true`. Option có tên giúp người dùng, help và script dễ hiểu hơn.

Đặc biệt thận trọng với subcommand. Khi lệnh có nhiều cấp như `remote add`, `remote remove`, một chuỗi token có thể mang ý nghĩa khác nhau tùy cấp. Dùng option có tên cho những giá trị có thể gây nhầm lẫn và mô tả rõ synopsis của từng command.

## 9. Kiểu dữ liệu và validation

Đối số bắt đầu dưới dạng token văn bản. Spring Shell phối hợp cơ chế chuyển đổi kiểu để bind token vào kiểu Java của tham số. Ví dụ, `@Argument(index = 0) long id` nhận giá trị số; `@Arguments List<String>` nhận danh sách chuỗi. Với kiểu phức tạp hoặc converter tùy chỉnh, cần kiểm tra cấu hình conversion service của ứng dụng.

Chuyển đổi kiểu thành công không đồng nghĩa dữ liệu hợp lệ về nghiệp vụ. Ví dụ, `-5` có thể chuyển thành `int` nhưng không phải số lượng file hợp lệ. Hãy kiểm tra điều kiện miền trước khi gọi service:

```java
@Component
public class BatchCommands {

    @Command(name = "repeat", description = "Lặp lại một thông điệp")
    public String repeat(
            @Argument(index = 0, description = "Số lần lặp") int count,
            @Argument(index = 1, description = "Thông điệp") String message) {

        if (count < 1 || count > 20) {
            throw new IllegalArgumentException("count phải nằm trong khoảng 1 đến 20.");
        }
        if (message == null || message.isBlank()) {
            throw new IllegalArgumentException("message không được để trống.");
        }

        return String.join(System.lineSeparator(),
                java.util.Collections.nCopies(count, message));
    }
}
```

Trong ứng dụng thực tế, quy tắc nghiệp vụ quan trọng vẫn phải được kiểm tra trong service hoặc domain để những đường gọi khác CLI cũng được bảo vệ. Thông báo lỗi nên chỉ rõ vị trí hoặc tên tham số, giá trị mong đợi và giới hạn được chấp nhận.

Với `@Arguments`, kiểm tra số lượng phần tử trước khi truy cập mảng hoặc collection. Với danh sách file, còn cần kiểm tra từng đường dẫn, quyền truy cập và quy tắc xử lý file trùng tên. Không giả định rằng parser đã kiểm tra những điều kiện này.

## 10. Trợ giúp và tài liệu command

Mô tả trong `@Command` và `@Argument` giúp người dùng hiểu mục đích command cũng như vai trò của từng vị trí. Hãy dùng tên đối số dễ hiểu trong mô tả, giải thích thứ tự và cung cấp ví dụ có cả trường hợp chứa dấu cách.

Ví dụ help nên cho người dùng thấy rõ:

```text
copy-file <source> <destination> [--overwrite <value>]

Arguments:
  source       Đường dẫn file nguồn
  destination  Đường dẫn file đích

Options:
  --overwrite  Cho phép ghi đè file đích (mặc định false)
```

Định dạng help thực tế do Spring Shell tạo và có thể khác theo phiên bản hoặc renderer. Hãy chạy `help copy-file` trong ứng dụng để kiểm tra synopsis được tạo từ metadata annotation. Nếu help chưa diễn đạt đủ quy tắc, bổ sung mô tả command và ví dụ sử dụng.

Đối với `@Arguments`, khả năng khai báo `description` có thay đổi theo phiên bản: thuộc tính `description` của `@Arguments` được bổ sung từ 4.0.4. Nếu dự án đang dùng bản ổn định 4.0.3, không dùng thuộc tính này trong source vì API đó chưa có ở bản này. Có thể mô tả danh sách trong `@Command(description = ...)` hoặc `help` cho đến khi nâng cấp lên phiên bản có hỗ trợ.

## 11. Kiểm thử binding đối số

Nên kiểm tra cả phương thức Java và cách Spring Shell phân tích dòng lệnh. Unit test gọi trực tiếp phương thức chỉ kiểm tra logic của phương thức; nó không xác minh index, parser, quoting hoặc binding của annotation.

Các ca kiểm thử quan trọng:

| Nhóm | Trường hợp |
| --- | --- |
| `@Argument` | Truyền đủ các vị trí và xác nhận mỗi tham số nhận đúng token |
| Index | Bỏ một đối số, đảo thứ tự giá trị và xác nhận lỗi hoặc kết quả đúng |
| Default value | Bỏ qua đối số có mặc định và xác nhận fallback |
| `@Arguments` | Không truyền, truyền một phần tử và truyền nhiều phần tử |
| `arity` | Truyền ít hơn, đúng và nhiều hơn số lượng giới hạn |
| Option xen kẽ | Đặt option trước, giữa và sau positional arguments |
| Quoting | Chuỗi có dấu cách, dấu nháy và ký tự escape |
| Conversion | Số hợp lệ, số sai định dạng và kiểu tùy chỉnh |
| Validation | Giá trị chuyển đổi được nhưng vi phạm quy tắc nghiệp vụ |

Trong integration test, khởi động Spring context và thực thi command bằng test support tương ứng của phiên bản Spring Shell đang dùng. Kiểm tra cả nội dung kết quả và lỗi parser. Có thể bổ sung end-to-end test chạy executable JAR để xác nhận cách người dùng thực sự nhập command từ terminal.

Với danh sách positional arguments, hãy kiểm tra thứ tự phần tử sau khi bind. Nếu command xử lý nhiều file, dùng dữ liệu test có tên file dễ phân biệt để phát hiện trường hợp parser gom nhầm hoặc đảo thứ tự.

## 12. Lỗi thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Dùng `@ShellComponent` hoặc `@ShellMethod` trong Spring Shell 4 | Đang dùng annotation cũ đã bị loại bỏ | Chuyển sang `@Component` và `@Command` trên phương thức |
| Thiếu index khi khai báo `@Argument` | `index` là thuộc tính bắt buộc | Khai báo index bắt đầu từ `0` |
| Đối số bị gán sai vị trí | Hiểu nhầm option hoặc giá trị option cũng chiếm index | Chỉ đếm positional arguments; kiểm tra cú pháp thực tế |
| Một `@Arguments` nuốt hết token còn lại | Không đặt `arity` nên mặc định gom tất cả | Dùng `arity` từ 4.0.2 hoặc đổi phần dữ liệu còn lại thành option |
| Truy cập phần tử mảng bị lỗi | Số token thực tế ít hơn giả định | Kiểm tra độ dài trước khi truy cập |
| Chuỗi có dấu cách bị tách thành nhiều phần tử | Không đặt dấu nháy quanh toàn bộ giá trị | Dùng dấu nháy đơn hoặc kép |
| `@Arguments(arity = ...)` không biên dịch | Đang dùng Spring Shell 4.0.0 hoặc 4.0.1 | Nâng lên 4.0.2+ hoặc thiết kế lại command không dùng thuộc tính này |
| `@Arguments(description = ...)` không biên dịch | API này có từ 4.0.4 | Bỏ thuộc tính hoặc nâng lên phiên bản hỗ trợ |

Khi gặp lỗi binding, hãy kiểm tra phiên bản Spring Shell, kiểu tham số, index, cú pháp command và output của `help`. Đừng sửa bằng cách thêm option tùy tiện nếu vấn đề thực sự nằm ở thứ tự hoặc số lượng positional arguments.

## 13. Bài thực hành tổng hợp

Tạo nhóm command quản lý file với các yêu cầu sau:

1. Tạo `copy-file` nhận `source` tại index `0`, `destination` tại index `1` và option `--overwrite`.
2. Tạo `delete-files` nhận nhiều đường dẫn qua `@Arguments List<String>` hoặc `String[]`.
3. Tạo `greet` nhận một đối số `name` với giá trị mặc định.
4. Tạo `real-part` dùng hai nhóm `@Arguments(arity = 2)` để nhận bốn số và tính phần thực của tích hai số phức.
5. Kiểm tra đường dẫn, số lượng đối số và quyền truy cập trong tầng phù hợp trước khi thay đổi file.
6. Bổ sung mô tả command, mô tả từng positional argument và ví dụ chuỗi có dấu cách.
7. Viết unit test cho logic và integration test cho binding, default value, arity, option xen kẽ và quoting.

Khi hoàn thành, bạn cần giải thích được vì sao `@Argument` cần index, `@Arguments` nhận một collection, `arity` giới hạn số token thế nào và khi nào nên chuyển một positional argument thành option có tên.

## 14. Tiêu chí hoàn thành

| Năng lực | Tiêu chí |
| --- | --- |
| Mô hình 4.x | Dùng `@Command` trên phương thức của Spring bean và annotation đúng package |
| Đối số đơn | Khai báo index 0-based và mô tả đúng ý nghĩa từng vị trí |
| Giá trị mặc định | Bỏ qua đối số tùy chọn và nhận đúng fallback |
| Danh sách đối số | Bind nhiều token vào array hoặc collection theo thứ tự |
| Arity | Hiểu giới hạn số token và kiểm tra số lượng theo yêu cầu nghiệp vụ |
| Parser | Xử lý đúng option xen kẽ, quoting và escaping |
| Thiết kế CLI | Chọn positional arguments cho dữ liệu có thứ tự rõ; dùng option cho giá trị dễ nhầm lẫn |
| Kiểm thử | Có test cho binding, conversion, default, arity và trường hợp lỗi |

## Tài liệu tham khảo

- [Spring Shell 4.0.3 — Command Syntax](https://docs.spring.io/spring-shell/reference/commands/syntax.html)
- [Spring Shell API — `@Argument`](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/annotation/Argument.html)
- [Spring Shell API — `@Arguments`](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/annotation/Arguments.html)
- [Spring Shell — v4 Migration Guide](https://github.com/spring-projects/spring-shell/wiki/v4-migration-guide)
