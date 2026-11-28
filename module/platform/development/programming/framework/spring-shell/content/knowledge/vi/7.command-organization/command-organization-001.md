# Đặt tên lệnh theo hành động và tài nguyên

Tên command là một phần giao diện mà người dùng nhìn thấy, ghi nhớ, nhập trong terminal và có thể lưu vào script. Một tên tốt cho biết **người dùng muốn thực hiện hành động gì trên tài nguyên nào**. Trong ứng dụng Spring Shell, có thể biểu diễn ý nghĩa đó bằng tên ghép như `list-products`, hoặc bằng nhóm tài nguyên và subcommand như `product list`.

Bài viết xây dựng quy tắc đặt tên nhất quán cho CLI: chọn động từ rõ nghĩa, gọi đúng tài nguyên, phân biệt một đối tượng với một tập hợp, dùng alias có kiểm soát và tổ chức command theo nhóm. Các ví dụ dùng annotation API của Spring Shell 4.x, phù hợp với phạm vi xây dựng CLI tương tác, chạy script, trợ giúp và tự hoàn thành của module Spring Shell.

## 1. Tên command cần diễn đạt điều gì?

Một command thường có ba thành phần về mặt ý nghĩa:

1. **Hành động:** thao tác người dùng muốn thực hiện, ví dụ `list`, `show`, `create`, `update`, `delete`, `export`.
2. **Tài nguyên:** đối tượng hoặc nhóm dữ liệu chịu tác động, ví dụ `product`, `user`, `report`, `configuration`.
3. **Phạm vi hoặc biến thể:** thông tin giúp phân biệt trường hợp cụ thể, ví dụ `report export monthly` hoặc `user disable`.

Ví dụ:

| Tên command | Hành động | Tài nguyên | Ý nghĩa |
|---|---|---|---|
| `list-products` | `list` | `products` | Liệt kê nhiều sản phẩm |
| `show-product` | `show` | `product` | Hiển thị một sản phẩm |
| `create-user` | `create` | `user` | Tạo người dùng mới |
| `update-user` | `update` | `user` | Sửa thông tin người dùng hiện có |
| `delete-user` | `delete` | `user` | Xóa người dùng |
| `export-report` | `export` | `report` | Xuất báo cáo |

Khi đọc tên, người dùng có thể đoán được command làm gì trước khi mở phần trợ giúp. Đây cũng là cơ sở để nhóm các command liên quan và tạo tên nhất quán khi CLI phát triển thêm chức năng.

## 2. Chọn động từ mô tả chính xác hành động

Động từ nên nói rõ kết quả mà command tạo ra. Tránh dùng một động từ chung cho nhiều thao tác khác nhau.

| Động từ | Khi nên dùng | Ví dụ |
|---|---|---|
| `list` | Trả về danh sách nhiều tài nguyên | `list-users` |
| `show` | Hiển thị chi tiết một tài nguyên | `show-user` |
| `create` | Tạo một tài nguyên mới | `create-user` |
| `update` | Sửa một tài nguyên đã tồn tại | `update-user` |
| `delete` | Xóa tài nguyên theo nghiệp vụ | `delete-user` |
| `enable` / `disable` | Bật hoặc tắt một tính năng/trạng thái | `disable-user` |
| `start` / `stop` | Bắt đầu hoặc dừng một tiến trình, dịch vụ | `start-job` |
| `import` / `export` | Đưa dữ liệu vào hoặc xuất dữ liệu ra | `export-report` |
| `validate` | Kiểm tra tính hợp lệ theo quy tắc | `validate-config` |
| `check` | Kiểm tra một điều kiện hoặc trạng thái | `check-connection` |

Một số cặp động từ có ý nghĩa gần nhau nhưng không nên hoán đổi tùy tiện:

- `show` thường trả về chi tiết một đối tượng; `list` trả về tập hợp. Dùng `show-user --id=42` và `list-users` để phân biệt rõ.
- `create` diễn tả việc tạo mới; `update` diễn tả việc thay đổi đối tượng đã tồn tại. Nếu một command vừa tạo vừa sửa tùy tình trạng, tên như `save-user` có thể phù hợp, nhưng cần mô tả rõ hành vi trong help.
- `delete` thường thể hiện thao tác xóa theo nghiệp vụ. `remove` phù hợp hơn khi gỡ một thành viên khỏi nhóm hoặc loại một mục khỏi danh sách mà tài nguyên gốc vẫn tồn tại, ví dụ `remove-user-from-group`.
- `validate` đánh giá dữ liệu có thỏa quy tắc hay không; `fix` hoặc `repair` hàm ý có thay đổi để khắc phục. Không đặt tên `validate-config` nếu command thực tế tự sửa file cấu hình.
- `run` chỉ nên dùng khi khái niệm nghiệp vụ thực sự là chạy một job hoặc tác vụ, chẳng hạn `run-migration`. Tránh tên chung như `run-command` hoặc `process-data` nếu có thể nêu hành động cụ thể hơn.

Nếu một command có tác động phá hủy hoặc không dễ hoàn tác, tên phải thể hiện rõ hành động như `delete`, `reset` hoặc `purge`. Đừng dùng một từ nhẹ nghĩa như `clean` nếu command thực sự xóa dữ liệu.

## 3. Gọi đúng tài nguyên và dùng số ít, số nhiều nhất quán

Tài nguyên trong tên command nên là danh từ quen thuộc với người dùng CLI và trùng với thuật ngữ nghiệp vụ của ứng dụng. Nếu hệ thống gọi đối tượng là `product`, không nên lúc thì dùng `item`, lúc lại dùng `goods` cho cùng một loại dữ liệu.

Một quy ước dễ hiểu là:

- Dùng danh từ số nhiều khi hành động nhắm đến một tập hợp: `list-products`, `export-users`.
- Dùng danh từ số ít khi hành động nhắm đến một đối tượng: `show-product`, `update-user`, `delete-report`.
- Với subcommand theo nhóm tài nguyên, dùng tên nhóm ở dạng số ít và đặt động từ ở subcommand: `product list`, `product show`, `product delete`.

Ví dụ một CLI quản lý catalog:

```text
product list
product show --id=42
product create --name=Keyboard
product update --id=42 --name=Mechanical-Keyboard
product delete --id=42
```

Nhóm `product` cho người dùng biết tất cả command bên dưới làm việc với tài nguyên sản phẩm. Subcommand mô tả hành động. Tên tài nguyên nhất quán giúp người dùng dự đoán command tiếp theo mà không cần ghi nhớ một tập tên rời rạc.

Không nên để danh từ quá chung như `data`, `object`, `record` hoặc `thing` đứng một mình nếu CLI có thể dùng thuật ngữ cụ thể hơn. Ví dụ, `export-report` nói rõ hơn `export-data` khi tác vụ chỉ xuất báo cáo.

## 4. Chọn một kiểu tên: command ghép hoặc nhóm tài nguyên

Spring Shell hỗ trợ command nhiều token. Bạn có thể đặt tên ghép với dấu gạch nối, hoặc tổ chức theo prefix và subcommand. Cả hai đều hợp lệ; điều quan trọng là chọn quy ước phù hợp và dùng nhất quán trong cùng CLI.

### Kiểu A: tên ghép theo hành động và tài nguyên

Với kiểu này, tên command là một chuỗi kebab-case:

```text
list-products
show-product
create-product
update-product
delete-product
export-report
```

Khai báo bằng Spring Shell 4:

```java
@Component
public class ProductCommands {

    @Command(name = "list-products", description = "List products.")
    public String listProducts() {
        return "Product list";
    }

    @Command(name = "show-product", description = "Show one product.")
    public String showProduct(@Option(longName = "id") String id) {
        return "Product " + id;
    }
}
```

Người dùng gọi `list-products` hoặc `show-product --id=42`. Cách này phù hợp với CLI nhỏ, nơi số lượng tài nguyên và command chưa quá lớn.

### Kiểu B: nhóm tài nguyên và subcommand

Khi có nhiều hành động trên cùng tài nguyên, gom chúng dưới một prefix:

```text
product list
product show --id=42
product create --name=Keyboard
product update --id=42 --name=Mechanical-Keyboard
product delete --id=42
```

Spring Shell 4 cung cấp `@CommandGroup` để đặt tên nhóm và prefix chung:

```java
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.CommandGroup;
import org.springframework.shell.core.command.annotation.Option;
import org.springframework.stereotype.Component;

@Component
@CommandGroup(name = "Product commands", prefix = "product")
public class ProductCommands {

    @Command(name = "list", description = "List products.")
    public String list() {
        return "Product list";
    }

    @Command(name = "show", description = "Show one product.")
    public String show(@Option(longName = "id") String id) {
        return "Product " + id;
    }

    @Command(name = "create", description = "Create a product.")
    public String create(@Option(longName = "name") String name) {
        return "Created " + name;
    }

    @Command(name = "delete", description = "Delete a product.")
    public String delete(@Option(longName = "id") String id) {
        return "Deleted " + id;
    }
}
```

`prefix` xác định phần đầu của command, còn `name` trên method xác định subcommand. `name` của nhóm là nhãn nhóm trong màn hình trợ giúp; nó không phải prefix dùng để gọi command. Khi cần ghi đè nhóm hiển thị cho một command, có thể đặt `group` trực tiếp trên `@Command`.

### Chọn kiểu nào?

| Tiêu chí | Tên ghép | Nhóm tài nguyên và subcommand |
|---|---|---|
| Cách gọi | `create-product` | `product create` |
| Phù hợp | CLI ít command, tác vụ độc lập | CLI có nhiều hành động trên từng tài nguyên |
| Khả năng mở rộng | Tên command tăng theo từng hành động | Prefix tạo không gian tên chung cho tài nguyên |
| Tổ chức code | Có thể gom theo class nghiệp vụ | Thường gom class theo tài nguyên và dùng `@CommandGroup` |
| Điều cần giữ nhất quán | Thứ tự động từ – tài nguyên | Prefix tài nguyên – subcommand hành động |

Không cần áp dụng cả hai kiểu cho cùng một nhóm hành động. Ví dụ, nếu đã chọn `product list`, không nên thêm `show-product` và `product delete` trong cùng một nhóm mà không có lý do rõ ràng.

## 5. Dùng tên nhiều token trực tiếp trong `@Command`

Ngoài `@CommandGroup`, Spring Shell 4 cho phép khai báo tên command bằng nhiều token trong thuộc tính `name`. Có thể truyền chuỗi có dấu cách hoặc mảng chuỗi:

```java
@Command(name = "report export", description = "Export a report.")
public String exportReport(@Option(longName = "format") String format) {
    return "Export as " + format;
}
```

Hoặc:

```java
@Command(name = {"report", "export"}, description = "Export a report.")
public String exportReport(@Option(longName = "format") String format) {
    return "Export as " + format;
}
```

Hai cách biểu diễn này tạo tên command nhiều thành phần như `report export`. API của `@Command` cũng cho phép đặt alias dưới dạng một hoặc nhiều tên thay thế. Khi sử dụng tên nhiều token, hãy kiểm tra cách gọi bằng `help` và command completion để người dùng nhận được đúng cấu trúc đã định.

## 6. Đặt tên alias có kiểm soát

Alias là tên thay thế để gọi cùng một command. Alias hữu ích khi cần giữ tương thích với script cũ, hỗ trợ một cách gọi ngắn hoặc chuyển dần từ thuật ngữ cũ sang thuật ngữ mới.

Ví dụ:

```java
@Component
public class ProductCommands {

    @Command(
            name = "list-products",
            alias = {"products"},
            description = "List products."
    )
    public String listProducts() {
        return "Product list";
    }
}
```

Người dùng có thể gọi `list-products` hoặc `products`; cả hai đều chạy cùng một command.

Nên áp dụng các nguyên tắc sau:

- Chọn một tên canonical duy nhất để tài liệu, ví dụ và script mới sử dụng.
- Chỉ thêm alias khi có lý do: tương thích ngược, cách viết tắt quen thuộc hoặc tên cũ cần thời gian chuyển đổi.
- Alias phải dễ nhớ, không trùng với command khác và không làm người dùng nhầm với một hành động khác.
- Mô tả alias trong tài liệu help hoặc hướng dẫn nâng cấp; nếu alias chỉ tồn tại tạm thời, cần có kế hoạch loại bỏ.
- Không tạo nhiều alias chỉ là biến thể chính tả không có giá trị sử dụng.

Trước khi đổi tên một command đã được dùng trong script, hãy xem tên đó như một phần hợp đồng giao diện. Có thể giữ tên cũ làm alias trong một giai đoạn chuyển tiếp, cập nhật tài liệu và thông báo thời điểm ngừng hỗ trợ alias.

## 7. Tên command và tên option phải bổ sung ý nghĩa cho nhau

Tên command mô tả hành động chính. Option mô tả cách thực hiện hoặc phạm vi cụ thể của hành động đó. Tránh đưa mọi chi tiết thành một phần của tên command.

Ví dụ:

```text
report export --period=monthly --format=csv
user list --status=active --page-size=50
backup create --target=database --compress=true
```

Các thành phần có vai trò khác nhau:

- `report export` xác định hành động xuất báo cáo.
- `--period` xác định khoảng báo cáo.
- `--format` xác định định dạng đầu ra.
- `user list` xác định hành động liệt kê người dùng.
- `--status` và `--page-size` điều chỉnh tập kết quả.

Spring Shell phân biệt option có tên với argument vị trí. Khi command có nhiều tham số hoặc subcommand, ưu tiên option có tên như `--id`, `--format`, `--page-size` để lời gọi dễ đọc và tránh phụ thuộc vào thứ tự tham số. Chọn tên option theo cùng một kiểu kebab-case, chẳng hạn `--created-after`, `--include-disabled`.

Không tạo nhiều command chỉ khác nhau bởi một giá trị option. Ví dụ, `export-report-csv` và `export-report-json` có thể được thay bằng `export-report --format=csv` và `export-report --format=json`, trừ khi hai thao tác thực sự có quy trình hoặc quyền hạn khác nhau.

## 8. Viết description giúp người dùng hiểu command

Tên ngắn gọn cần đi cùng description rõ ràng. Spring Shell hiển thị mô tả trong trợ giúp, vì vậy description nên nói command làm gì và tác động lên tài nguyên nào.

Ví dụ:

```java
@Command(
        name = "delete-user",
        description = "Delete a user by identifier.",
        help = "Deletes the selected user. This operation cannot be undone."
)
public String deleteUser(@Option(longName = "id") String id) {
    return "Deleted user " + id;
}
```

Nên viết description bằng câu ngắn, bắt đầu bằng động từ và dùng thuật ngữ nhất quán với tên command. Với thao tác nhạy cảm hoặc phá hủy, phần help cần giải thích tác động, điều kiện và ví dụ sử dụng. Tên command và help cùng trả lời hai câu hỏi: thao tác nào đang được gọi và thao tác đó ảnh hưởng đến điều gì.

## 9. Những kiểu đặt tên nên tránh

| Tên chưa rõ nghĩa | Vấn đề | Tên đề xuất |
|---|---|---|
| `process` | Không nói rõ xử lý việc gì | `process-payment`, `import-orders` |
| `manage-user` | Bao hàm quá nhiều hành động | `user list`, `user create`, `user update` |
| `data` | Không chỉ ra hành động hoặc loại dữ liệu | `export-report`, `validate-config` |
| `user-update` và `user delete` trong cùng nhóm | Trộn hai quy ước tên | Chọn `update-user`/`delete-user` hoặc `user update`/`user delete` |
| `remove-user` khi thực tế xóa tài khoản vĩnh viễn | Động từ làm nhẹ mức độ tác động | `delete-user` |
| `do-export` | Từ `do` không bổ sung ý nghĩa | `export-report` |
| `product-list-all-active` | Nhồi điều kiện truy vấn vào tên command | `product list --status=active` |

Tên command cũng không nên phụ thuộc vào chi tiết nội bộ như tên class Java, tên repository, tên bảng SQL hoặc tên endpoint HTTP. Người dùng cần biết thao tác nghiệp vụ, không cần biết lớp nào thực thi thao tác đó.

## 10. Checklist rà soát bộ tên command

- [ ] Mỗi command có một động từ diễn tả rõ hành động.
- [ ] Tài nguyên được gọi bằng thuật ngữ thống nhất với nghiệp vụ.
- [ ] Danh từ số ít/số nhiều phản ánh đúng thao tác trên một đối tượng hay tập hợp.
- [ ] Tên ghép dùng một quy tắc nhất quán, ví dụ `verb-resource` với kebab-case.
- [ ] Nếu dùng prefix và subcommand, nhóm tài nguyên và động từ được sắp xếp nhất quán.
- [ ] Không có command chung chung như `process`, `manage` hoặc `do` khi có thể dùng động từ cụ thể.
- [ ] Alias có lý do rõ ràng, không xung đột và trỏ về đúng một command.
- [ ] Option thể hiện điều kiện hoặc cách thực thi, không làm tên command phình to.
- [ ] Description và help nói rõ tác động, có ví dụ cho command quan trọng.
- [ ] Đã kiểm tra `help`, gọi command trực tiếp và tự hoàn thành tên command trong shell.
- [ ] Tên command được xem như giao diện ổn định khi có script hoặc người dùng tự động hóa phụ thuộc vào nó.

## Tài liệu tham khảo

1. [Spring Shell 4 – Command Syntax](https://docs.spring.io/spring-shell/reference/commands/syntax.html) – cấu trúc command, subcommand, argument và option.
2. [Spring Shell 4 – Organizing Commands](https://docs.spring.io/spring-shell/reference/commands/organize.html) – nhóm command, `@CommandGroup`, prefix và group.
3. [Spring Shell 4 – `@Command` API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/annotation/Command.html) – thuộc tính `name`, `alias`, `description`, `group` và `help`.
4. [Command Line Interface Guidelines](https://clig.dev/) – nguyên tắc thiết kế giao diện dòng lệnh, cách đặt cấu trúc command và giảm sự mơ hồ khi sử dụng.

Hãy bắt đầu từ cách người dùng diễn đạt công việc: họ muốn làm gì và làm trên tài nguyên nào. Sau đó chọn một quy ước tên ghép hoặc nhóm tài nguyên, áp dụng nhất quán cho command mới và giữ alias có kiểm soát để CLI dễ học, dễ trợ giúp và ổn định khi được gọi từ script.
