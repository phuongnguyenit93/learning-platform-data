# @Arguments, tập giá trị còn lại và giới hạn arity trong 4.x

Spring Shell 4 cung cấp annotation **@Arguments** để gom nhiều positional argument vào cùng một tham số Java. Tham số được đánh dấu phải có kiểu mảng hoặc collection, chẳng hạn **String[]** hoặc **List<String>**. Khi không giới hạn số lượng, annotation thu thập các positional argument còn lại của command. Khi cần chia đầu vào thành nhiều nhóm, thuộc tính **arity** giới hạn số giá trị mà từng tham số **@Arguments** nhận.

Tính năng này hữu ích với những command nhận danh sách file, tên module, người dùng, môi trường hoặc các giá trị đầu vào có số lượng thay đổi. Ví dụ, command **delete file1 file2 file3** tự nhiên hơn khi danh sách file là positional arguments thay vì buộc người dùng truyền một option chứa cả danh sách.

Bài này tập trung vào mô hình annotation của Spring Shell 4.x, sử dụng package **org.springframework.shell.core.command.annotation**. Trong 4.x, **@Arguments.arity** là giới hạn tối đa số positional argument được gom vào tham số. Nó không đặt số lượng tối thiểu. Nếu nghiệp vụ yêu cầu chính xác một số lượng giá trị, command cần kiểm tra kích thước mảng hoặc collection sau khi nhận dữ liệu.

## 1. Phân biệt @Option, @Argument và @Arguments

Ba annotation phục vụ ba kiểu đầu vào khác nhau:

| Annotation | Kiểu dữ liệu | Cách xác định giá trị | Ví dụ |
|---|---|---|---|
| **@Option** | Một giá trị có tên | Theo short name hoặc long name | **--environment=staging** |
| **@Argument** | Một giá trị vị trí | Theo index bắt đầu từ 0 | **deploy staging** |
| **@Arguments** | Nhiều giá trị vị trí | Gom các positional argument còn lại theo arity | **delete file1 file2 file3** |

Option phù hợp với dữ liệu có ý nghĩa rõ ràng và có thể xuất hiện ở nhiều vị trí trong dòng lệnh. Argument phù hợp với một giá trị đơn có vị trí cố định. **@Arguments** phù hợp khi command nhận một danh sách các giá trị cùng vai trò.

Ví dụ, lệnh xóa nhiều file có thể nhận option **--force** và danh sách file:

~~~java
import org.springframework.shell.core.command.annotation.Arguments;
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.Option;
import org.springframework.stereotype.Component;

@Component
class DeleteCommands {

    @Command(name = "delete", description = "Xóa một hoặc nhiều file.")
    public String delete(
            @Option(longName = "force", defaultValue = "false") boolean force,
            @Arguments(description = "Các đường dẫn file cần xóa") String[] paths) {

        if (paths.length == 0) {
            return "Bạn chưa cung cấp file cần xóa.";
        }

        return "Sẽ xóa " + paths.length + " file, force=" + force;
    }
}
~~~

Có thể gọi:

~~~text
delete report.csv metrics.csv archive.zip
delete --force report.csv metrics.csv archive.zip
delete report.csv --force metrics.csv archive.zip
~~~

Option được nhận diện theo tên; các tên file là positional arguments và được gom vào mảng **paths**. Vị trí của option không làm nó trở thành phần tử trong mảng.

## 2. @Arguments phải dùng với mảng hoặc collection

**@Arguments** đánh dấu một method parameter nhận nhiều positional arguments. Kiểu tham số phải là array hoặc collection. Một số kiểu thường dùng:

~~~java
@Arguments String[] names
@Arguments List<String> names
@Arguments Set<String> names
~~~

Mảng là lựa chọn đơn giản khi command cần duyệt danh sách theo thứ tự. **List** cũng phù hợp khi cần các thao tác collection. **Set** có ngữ nghĩa tập hợp: phần tử trùng nhau không được giữ như các phần tử riêng biệt; nếu thứ tự là một phần của hợp đồng CLI, nên chọn array hoặc List.

Về tương thích phiên bản, **@Arguments** có từ Spring Shell 4.0.0; thuộc tính **arity** có từ 4.0.2; thuộc tính **description** có từ 4.0.4. Các ví dụ dùng **description** trong bài nhắm đến Spring Shell 4.0.4. Nếu ứng dụng đang ở 4.0.2 hoặc 4.0.3, bỏ thuộc tính **description** và vẫn có thể dùng **arity**.

Ví dụ command chào nhiều người:

~~~java
import java.util.List;
import org.springframework.shell.core.command.annotation.Arguments;
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.Option;
import org.springframework.stereotype.Component;

@Component
class GreetingCommands {

    @Command(name = "greet-many", description = "Chào nhiều người.")
    public String greetMany(
            @Option(longName = "suffix", defaultValue = "!") String suffix,
            @Arguments(description = "Tên của những người cần chào") List<String> names) {

        if (names.isEmpty()) {
            return "Chưa có tên nào được cung cấp.";
        }

        return "Xin chào " + String.join(", ", names) + suffix;
    }
}
~~~

Lệnh:

~~~text
greet-many An Binh Chi
greet-many --suffix=. An Binh Chi
greet-many "Nguyen Van An" "Tran Thi Binh"
~~~

Ở lệnh thứ ba, mỗi giá trị được đặt trong dấu nháy để giữ tên đầy đủ thành một positional argument. Mảng hoặc collection nhận hai phần tử: **Nguyen Van An** và **Tran Thi Binh**, không phải sáu từ riêng biệt.

## 3. Mặc định: gom các positional argument còn lại

Nếu không chỉ định **arity**, Spring Shell gom tất cả positional argument còn lại vào tham số **@Arguments**. Giá trị mặc định của thuộc tính **arity** là **Integer.MAX_VALUE**, tức không đặt giới hạn thực tế cho số lượng phần tử được gom.

~~~java
@Command(name = "tag")
public String tag(@Arguments(description = "Các tag cần gắn") String[] tags) {
    return "Tags: " + String.join(", ", tags);
}
~~~

Ví dụ:

~~~text
tag backend spring java cli
~~~

Method nhận mảng **tags** gồm bốn phần tử: **backend**, **spring**, **java** và **cli**. Các option có tên vẫn được parser nhận diện riêng, dù chúng xuất hiện trước, giữa hoặc sau các positional argument.

Đây là cách khai báo phù hợp khi command chỉ có một danh sách positional argument ở cuối. Nếu command có nhiều nhóm positional argument, cần đặt giới hạn cho các nhóm đứng trước để phần giá trị còn lại có thể được phân cho tham số tiếp theo.

## 4. Giới hạn arity cho một nhóm giá trị

Thuộc tính **arity** xác định số positional argument tối đa được thu thập vào một tham số **@Arguments**. Thuộc tính này được bổ sung trong Spring Shell 4.0.2.

Ví dụ command triển khai module có hai nhóm đầu vào: tối đa hai module chính và các bước kiểm tra bổ sung:

~~~java
import org.springframework.shell.core.command.annotation.Arguments;
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.Option;
import org.springframework.stereotype.Component;

@Component
class DeploymentCommands {

    @Command(name = "deploy-batch", description = "Triển khai module theo nhóm.")
    public String deployBatch(
            @Option(longName = "environment", required = true) String environment,
            @Arguments(arity = 2, description = "Hai module chính") String[] modules,
            @Arguments(description = "Các bước kiểm tra sau triển khai") String[] checks) {

        if (modules.length != 2) {
            throw new IllegalArgumentException("Cần cung cấp đúng hai module chính.");
        }

        return "Môi trường: " + environment
                + "; module: " + String.join(", ", modules)
                + "; kiểm tra: " + String.join(", ", checks);
    }
}
~~~

Gọi command:

~~~text
deploy-batch --environment=staging billing catalog smoke health regression
~~~

Các giá trị được phân bổ theo thứ tự tham số:

| Tham số | Arity | Giá trị nhận được |
|---|---:|---|
| **environment** | Một option có tên | **staging** |
| **modules** | Tối đa 2 | **billing**, **catalog** |
| **checks** | Không giới hạn | **smoke**, **health**, **regression** |

Tham số **modules** lấy hai positional argument đầu tiên. Tham số **checks** nhận các positional argument tiếp theo. Option **--environment** được parse riêng và không chiếm một vị trí trong hai nhóm này.

Các nhóm được chia theo vị trí, không theo ý nghĩa của từ. Nếu người dùng bỏ sót một module chính nhưng vẫn nhập một bước kiểm tra, từ đó có thể bị gom vào nhóm **modules**. Khi các nhóm có thể bị nhầm lẫn như vậy, hãy mô tả thứ tự thật rõ trong help hoặc dùng option có tên cho nhóm cần phân biệt.

## 5. Nhiều tham số @Arguments được phân bổ tuần tự

Khi một method có nhiều tham số **@Arguments**, Spring Shell phân bổ positional argument theo thứ tự khai báo của các tham số trong method. Mỗi tham số nhận các giá trị tiếp theo, bắt đầu sau số positional argument đã được xử lý. **arity** giới hạn số giá trị mà nhóm hiện tại tiêu thụ.

Ví dụ:

~~~java
@Command(name = "release")
public String release(
        @Arguments(arity = 2, description = "Hai module chính") String[] primaryModules,
        @Arguments(description = "Các module bổ sung") String[] additionalModules) {

    return "Module chính: " + String.join(", ", primaryModules)
            + "; module bổ sung: " + String.join(", ", additionalModules);
}
~~~

Với đầu vào:

~~~text
release billing catalog analytics reporting
~~~

Kết quả phân bổ:

~~~text
primaryModules    = ["billing", "catalog"]
additionalModules = ["analytics", "reporting"]
~~~

Tham số **primaryModules** giới hạn tối đa hai phần tử. Tham số **additionalModules** không khai báo arity nên nhận tất cả giá trị positional còn lại.

Nếu tham số **@Arguments** đầu tiên không đặt arity, nó mặc định thu thập toàn bộ positional argument còn lại. Các tham số **@Arguments** đứng sau vì thế không còn giá trị để nhận. Khi chia một dòng lệnh thành nhiều nhóm, hãy đặt arity rõ ràng cho từng nhóm có giới hạn; thường để nhóm cuối cùng nhận phần còn lại.

### 5.1. Kết hợp @Argument với @Arguments

Một command có thể nhận một positional argument đơn rồi gom phần còn lại vào collection:

~~~java
@Command(name = "copy-to", description = "Sao chép file đến nhiều đích.")
public String copyTo(
        @Argument(index = 0, description = "File nguồn") String source,
        @Arguments(description = "Các thư mục đích") String[] destinations) {

    if (destinations.length == 0) {
        throw new IllegalArgumentException("Cần cung cấp ít nhất một thư mục đích.");
    }

    return "Sao chép " + source + " đến " + String.join(", ", destinations);
}
~~~

Gọi:

~~~text
copy-to report.csv archive/ backup/ shared/
~~~

**source** nhận positional argument ở index 0. **destinations** nhận các positional argument tiếp theo. Index của **@Argument** bắt đầu từ 0 và chỉ đếm positional arguments, không đếm các option có tên.

## 6. Arity là giới hạn tối đa, không phải số lượng bắt buộc

Đây là điểm cần nhớ khi thiết kế command. API mô tả **arity** là số lượng positional argument tối đa được thu thập. Ví dụ **@Arguments(arity = 3)** cho phép tham số nhận tối đa ba giá trị; nếu chỉ có một hoặc hai giá trị còn lại, tham số có thể nhận số lượng tương ứng.

Annotation **@Arguments** không có thuộc tính **arityMin**. Vì vậy, không nên hiểu:

~~~java
@Arguments(arity = 3) String[] values
~~~

là yêu cầu người dùng bắt buộc phải nhập chính xác ba giá trị. Nếu nghiệp vụ cần chính xác ba giá trị, hãy kiểm tra độ dài sau khi nhận tham số:

~~~java
@Command(name = "set-coordinates")
public String setCoordinates(@Arguments(arity = 3) double[] coordinates) {
    if (coordinates.length != 3) {
        throw new IllegalArgumentException("Cần đúng ba tọa độ: x, y và z.");
    }

    return "Đã nhận tọa độ " + coordinates[0]
            + ", " + coordinates[1]
            + ", " + coordinates[2];
}
~~~

Nếu có các tham số **@Arguments** tiếp theo, những positional argument vượt quá giới hạn của nhóm trước sẽ được phân cho nhóm sau. Nếu không có tham số nào nhận các giá trị dư, parser có thể từ chối dòng lệnh vì còn positional argument chưa được ánh xạ.

Các điều kiện cần phân biệt:

| Yêu cầu | Cách thực hiện |
|---|---|
| Nhận tất cả giá trị còn lại | **@Arguments** không khai báo arity |
| Nhận tối đa N giá trị | **@Arguments(arity = N)** |
| Nhận một nhóm tối đa N, rồi nhóm tiếp theo nhận phần dư | Nhiều **@Arguments**, nhóm đầu đặt arity |
| Bắt buộc ít nhất N giá trị | Kiểm tra **length** hoặc **size()** trong command/service |
| Bắt buộc chính xác N giá trị | Kiểm tra kích thước bằng N trong command/service |

## 7. Options có thể xuất hiện xen giữa positional arguments

Spring Shell parse option theo tên và positional argument theo vị trí. Vì vậy, option có thể xuất hiện trước, giữa hoặc sau các giá trị được gom:

~~~text
deploy-batch --environment=staging billing catalog smoke
deploy-batch billing --environment=staging catalog smoke
deploy-batch billing catalog smoke --environment=staging
~~~

Trong cả ba trường hợp, **--environment** được ánh xạ vào option tương ứng, còn các giá trị **billing**, **catalog**, **smoke** được xử lý như positional arguments. Không tính option vào arity của **@Arguments**.

Đối với option kiểu boolean, Spring Shell 4 hỗ trợ cờ không có giá trị như **--verbose** để đặt thành **true**. Các option khác cần giá trị theo cú pháp option. Không nên dùng **@Arguments** để gom option có tên; annotation này dành cho positional argument.

## 8. Giá trị chứa khoảng trắng và dấu nháy

Parser tách đầu vào theo khoảng trắng. Nếu một positional argument chứa khoảng trắng, đặt toàn bộ giá trị trong dấu nháy. Mỗi cặp dấu nháy tạo ra một argument duy nhất:

~~~text
greet-many "Nguyen Van An" "Tran Thi Binh"
~~~

Mảng **names** nhận hai phần tử, mỗi phần tử là một tên đầy đủ. Nếu bỏ dấu nháy:

~~~text
greet-many Nguyen Van An Tran Thi Binh
~~~

parser nhìn thấy sáu positional argument riêng. Khi command cần tên người, đường dẫn hoặc chuỗi có khoảng trắng, hãy trích dẫn từng giá trị riêng biệt.

Spring Shell hỗ trợ nháy đơn và nháy kép. Loại dấu nháy còn lại có thể nằm bên trong giá trị được trích dẫn; nếu cần chứa chính loại dấu nháy bao ngoài, escape nó bằng dấu gạch chéo ngược. Một dấu gạch chéo ngược thực sự bên trong giá trị đã trích dẫn được viết thành hai dấu gạch chéo ngược.

## 9. Mô tả @Arguments trong help

Trong Spring Shell 4.0.4, **@Arguments** có thuộc tính **description** để mô tả danh sách positional argument. Mô tả này được đưa vào help của command:

- Trong phần **SYNOPSIS**, Spring Shell thể hiện phần tử theo kiểu dữ liệu của array hoặc collection, thay vì tên kiểu array/collection.
- Trong phần **ARGUMENTS**, framework hiển thị một mục riêng cho nhóm giá trị.

Ví dụ:

~~~java
@Command(
        name = "delete",
        description = "Xóa nhiều file.",
        help = "Xóa các file được cung cấp trên dòng lệnh."
)
public String delete(
        @Arguments(description = "Danh sách đường dẫn file cần xóa") String[] paths) {
    // Xử lý danh sách paths
    return "Số file nhận được: " + paths.length;
}
~~~

Hãy viết description theo vai trò của các giá trị. Ví dụ **Các đường dẫn file cần xóa**, **Tên module cần triển khai** hoặc **Các địa chỉ nhận thông báo** giúp người dùng hiểu thứ tự và ý nghĩa của từng phần tử.

## 10. Khác biệt với arity của option trong Spring Shell 3.x

Spring Shell 3.x hỗ trợ đầu vào nhiều giá trị chủ yếu qua arity của option. Khi chuyển sang 4.x, mô hình này thay đổi:

| Spring Shell 3.x | Spring Shell 4.x |
|---|---|
| Multi-value input thường được mô tả bằng option có arity | Multi-value positional input được mô tả bằng **@Arguments** |
| **@ShellOption** hoặc **@Option** của mô hình 3.x có thể dùng arity | **@Option** 4.x là option có tên nhận một giá trị |
| Chưa có annotation plural cho positional arguments | Có **@Arguments** cho array hoặc collection |
| Logic arity gắn với option | **@Arguments.arity** giới hạn số positional argument được gom |

Ví dụ, một lệnh xóa nhiều file thường phù hợp với:

~~~text
delete file1.txt file2.txt file3.txt
~~~

Trong Spring Shell 4, khai báo:

~~~java
@Command(name = "delete")
public String delete(@Arguments String[] files) {
    return "Số file: " + files.length;
}
~~~

Không chuyển máy móc một option nhiều giá trị từ 3.x thành **@Option** trong 4.x. Hãy xem dữ liệu đó có thực chất là một danh sách positional argument không. Nếu đúng, chuyển sang **@Arguments** và xác định arity phù hợp. Nếu giá trị cần có tên, giữ nó là option đơn và thiết kế giao diện command rõ ràng cho từng giá trị.

## 11. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Không bind được danh sách vào tham số | Dùng **@Arguments** với kiểu scalar như **String** hoặc **int** | Dùng array hoặc collection |
| Tham số danh sách sau luôn rỗng | Nhóm **@Arguments** trước không giới hạn arity nên đã gom hết giá trị | Đặt arity cho nhóm trước |
| Thiếu phần tử nhưng command vẫn chạy | **arity** chỉ đặt giới hạn tối đa, không đặt số lượng tối thiểu | Kiểm tra **length** hoặc **size()** |
| Dư positional argument | Không có tham số nào tiếp nhận phần giá trị còn lại | Thêm nhóm **@Arguments** tiếp theo hoặc điều chỉnh cú pháp |
| Tên có khoảng trắng bị tách thành nhiều phần tử | Không đặt tên trong dấu nháy | Trích dẫn từng positional argument |
| Option bị đưa nhầm vào danh sách | Nhập giá trị option như positional argument hoặc khai báo sai tên option | Dùng short/long name đã khai báo trong **@Option** |
| Chuyển code 3.x nhưng option không còn nhận nhiều giá trị | Đang dùng arity của option theo mô hình cũ | Chuyển danh sách sang **@Arguments** trong 4.x |
| Help không mô tả nhóm danh sách | Thiếu description hoặc đang dùng phiên bản chưa có thuộc tính này | Dùng **@Arguments(description = "...")** trên Spring Shell 4.0.4 trở lên |

## 12. Kiểm thử command có @Arguments

Kiểm thử nên bao phủ cả việc gom dữ liệu lẫn giới hạn số lượng:

1. **Không có positional argument:** xác định command xử lý mảng/collection rỗng như thế nào.
2. **Một phần tử:** kiểm tra giá trị được chuyển đổi đúng kiểu.
3. **Nhiều phần tử:** kiểm tra tất cả phần tử được nhận đúng thứ tự.
4. **Giá trị có khoảng trắng:** kiểm tra dấu nháy giữ mỗi giá trị thành một phần tử.
5. **Option xen giữa positional argument:** xác minh option được bind riêng và không chiếm arity.
6. **Arity giới hạn:** xác minh nhóm đầu chỉ nhận số giá trị tối đa đã khai báo.
7. **Nhiều nhóm @Arguments:** xác minh mỗi nhóm nhận đúng phần positional argument kế tiếp.
8. **Thiếu số lượng bắt buộc:** xác minh command báo lỗi dễ hiểu từ phần kiểm tra kích thước.
9. **Dư positional argument:** xác minh giá trị dư được nhóm tiếp theo nhận hoặc parser báo lỗi nếu không có tham số tương ứng.
10. **Help output:** xác minh synopsis và mô tả nhóm argument có ý nghĩa.

Ví dụ kiểm thử đơn vị cho command chia nhóm:

~~~java
@Test
void shouldReceivePrimaryAndAdditionalModules() {
    String[] primaryModules = { "billing", "catalog" };
    String[] additionalModules = { "analytics", "reporting" };

    String result = commands.release(primaryModules, additionalModules);

    assertThat(result)
            .contains("billing, catalog")
            .contains("analytics, reporting");
}
~~~

Đây là kiểm thử logic của method sau khi dữ liệu đã được bind. Để xác minh parser và arity hoạt động đúng từ dòng lệnh, cần thêm kiểm thử tích hợp qua **ShellTestClient**: gửi chuỗi command thực tế, kiểm tra output và lỗi khi thiếu hoặc thừa positional argument.

## 13. Chọn cách khai báo

- Dùng **@Option** cho một giá trị có tên, chẳng hạn môi trường hoặc chế độ chạy.
- Dùng **@Argument(index = ...)** cho một positional argument đơn, có vị trí cố định.
- Dùng **@Arguments** cho danh sách positional argument còn lại.
- Dùng **@Arguments(arity = N)** khi cần giới hạn một nhóm và dành phần positional argument tiếp theo cho tham số sau.
- Dùng nhiều **@Arguments** khi command có các nhóm giá trị khác vai trò; đặt arity cho các nhóm đứng trước.
- Kiểm tra **length** hoặc **size()** khi nghiệp vụ yêu cầu số lượng tối thiểu hoặc chính xác.

Một command dễ sử dụng khi mỗi nhóm argument có vai trò rõ ràng và help mô tả được thứ tự đầu vào. Nếu người dùng khó phân biệt hai nhóm positional argument, hãy cân nhắc chuyển một nhóm thành option có tên.

## Tài liệu tham khảo

- [Spring Shell 4.0.4 — Command Syntax](https://docs.spring.io/spring-shell/reference/commands/syntax.html) — cách khai báo **@Arguments**, collection nhiều giá trị, arity, option và positional argument.
- [Spring Shell 4.0.4 API — Arguments](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/annotation/Arguments.html) — kiểu tham số hợp lệ, thuộc tính **arity** và **description**.
- [Spring Shell v4 Migration Guide — Command option arity changes](https://github.com/spring-projects/spring-shell/wiki/v4-migration-guide#command-option-arity-changes) — thay đổi từ option arity trong 3.x sang multi-valued positional arguments trong 4.x.
- [Spring Shell 4.0.2 — Add ability to specify argument arity](https://github.com/spring-projects/spring-shell/commit/a72c76e5e4b0cc388e6a95f0c500f2d3c7b6fb03) — bổ sung **@Arguments.arity** và ví dụ kiểm thử phân chia các nhóm positional argument.
- [Spring Shell 4.0.2 release notes](https://github.com/spring-projects/spring-shell/releases/tag/v4.0.2) — phiên bản bổ sung hỗ trợ arity cho multi-valued arguments.
