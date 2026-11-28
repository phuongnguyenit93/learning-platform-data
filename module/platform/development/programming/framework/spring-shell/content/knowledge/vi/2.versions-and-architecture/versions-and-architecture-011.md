# Chọn một mô hình khai báo nhất quán cho từng phần của ứng dụng

Spring Shell cung cấp cách mô tả command để ứng dụng biết lệnh nào tồn tại, người dùng truyền option và argument ra sao, cách gọi phần xử lý và cách giới thiệu lệnh trong trợ giúp. Trong quá trình phát triển, bạn có thể gặp hai cách khai báo phổ biến: đặt annotation trực tiếp trên lớp và phương thức Java, hoặc đăng ký command bằng API `CommandRegistration` thông qua cấu hình Spring.

Hai cách này cùng phục vụ một mục tiêu nhưng có cách tổ chức mã nguồn khác nhau. Annotation đặt thông tin command gần phương thức xử lý. `CommandRegistration` mô tả command tường minh bằng một cấu hình có cấu trúc. Chọn mô hình phù hợp cho từng phần ứng dụng giúp nhóm phát triển đọc, sửa và kiểm thử command theo một quy ước ổn định.

Điểm cần thống nhất là phạm vi sở hữu command. Một nhóm lệnh thuộc cùng tính năng nên có cách khai báo dễ nhận biết và không bị đăng ký trùng. Toàn bộ ứng dụng có thể có nhiều nhóm với mô hình khác nhau khi việc kết hợp đó là chủ ý, có ranh giới rõ ràng và phù hợp với phiên bản Spring Shell đang sử dụng.

## Hai mô hình khai báo command

### Mô hình annotation

Với mô hình annotation, Spring Shell phát hiện component và các phương thức được đánh dấu để tạo command. Những annotation thường gặp gồm:

- `@ShellComponent` đánh dấu lớp chứa các command.
- `@ShellMethod` khai báo phương thức là một command, đồng thời cung cấp tên và mô tả.
- `@ShellOption` mô tả option, giá trị mặc định và các đặc điểm đầu vào của tham số.

Ví dụ một command chào người dùng:

```java
@ShellComponent
public class GreetingCommands {

    private final GreetingService greetingService;

    public GreetingCommands(GreetingService greetingService) {
        this.greetingService = greetingService;
    }

    @ShellMethod(key = "greet", value = "Gửi lời chào")
    public String greet(
            @ShellOption(value = "--name", defaultValue = "World") String name) {
        return greetingService.greet(name);
    }
}
```

Người dùng có thể gọi `greet` hoặc `greet --name Linh`. Tên command, mô tả và option nằm ngay cạnh phương thức xử lý, nên người đọc dễ theo dõi một command từ khai báo đến lời gọi nghiệp vụ. `GreetingService` vẫn là thành phần riêng; phương thức command chỉ chuyển đầu vào và trả kết quả.

Mô hình annotation thường phù hợp khi tập command được xác định trong mã nguồn, mỗi command gắn tự nhiên với một phương thức Java và nhóm muốn khai báo ngắn gọn. Nó cũng thuận tiện khi dự án hiện tại đã có nhiều command theo quy ước này và chưa có nhu cầu thay đổi cách đăng ký.

### Mô hình đăng ký bằng `CommandRegistration`

Với mô hình đăng ký tường minh, command được tạo bằng builder và thường được cung cấp dưới dạng bean cấu hình Spring. Tên lệnh, mô tả, option và hàm xử lý được khai báo trong cùng một cấu trúc:

```java
@Configuration
public class GreetingCommandConfiguration {

    private final GreetingService greetingService;

    public GreetingCommandConfiguration(GreetingService greetingService) {
        this.greetingService = greetingService;
    }

    @Bean
    CommandRegistration greetingCommand() {
        return CommandRegistration.builder()
                .command("greet")
                .description("Gửi lời chào")
                .withOption()
                    .longNames("name")
                    .description("Tên người nhận")
                    .type(String.class)
                    .defaultValue("World")
                    .and()
                .withTarget()
                    .function(context -> {
                        String name = context.getOptionValue("name");
                        return greetingService.greet(name);
                    })
                    .and()
                .build();
    }
}
```

Command vẫn có thể được gọi bằng `greet` hoặc `greet --name Linh`. Khác biệt nằm ở cách mô tả: builder thể hiện từng phần của command một cách tường minh, thay vì suy ra cấu trúc từ annotation trên phương thức.

Mô hình này hữu ích khi cần kiểm soát quá trình đăng ký command bằng cấu hình, tạo command theo điều kiện hoặc dữ liệu cấu hình, hay gom metadata của command tại một điểm. Nó cũng có thể phù hợp với những nhóm muốn nhìn thấy rõ cấu trúc option và target trong cấu hình thay vì đặt metadata rải trên chữ ký phương thức.

API builder và khả năng kết hợp các thành phần phụ thuộc vào phiên bản Spring Shell. Ví dụ trên minh họa cấu trúc của `CommandRegistration`; hãy đối chiếu tên phương thức, kiểu dữ liệu và cách lấy giá trị option với tài liệu của đúng phiên bản trong dự án trước khi áp dụng.

## So sánh để chọn mô hình

| Tiêu chí | Annotation | `CommandRegistration` |
| --- | --- | --- |
| Cách mô tả | Annotation trên lớp và phương thức Java | Builder tạo đối tượng đăng ký command |
| Vị trí metadata | Gần phương thức xử lý | Trong cấu hình đăng ký |
| Độ ngắn gọn | Thường ít mã hơn với command tĩnh | Tường minh hơn, có thể dài hơn |
| Tập command thay đổi theo cấu hình | Thường cần tổ chức component và điều kiện quét phù hợp | Thuận tiện khi tạo đăng ký từ cấu hình hoặc điều kiện |
| Phù hợp với | Nhóm command ổn định, khai báo gắn với phương thức | Nhóm cần cấu hình đăng ký rõ ràng hoặc linh hoạt |
| Điểm cần kiểm soát | Component scanning và quy ước annotation | Cấu trúc builder, bean đăng ký và logic tạo command |

Không có mô hình nào tự động làm cho nghiệp vụ tốt hơn. Chất lượng kiến trúc còn phụ thuộc vào việc command có giữ vai trò adapter hay không, quy tắc nghiệp vụ có được đặt đúng lớp hay không và các command có được kiểm thử hay không.

Khi lựa chọn, hãy xem xét các câu hỏi sau:

1. **Command có ổn định trong mã nguồn không?** Nếu tên, option và handler thay đổi chủ yếu qua các lần phát hành phần mềm, annotation thường đơn giản và dễ đọc. Nếu tập command cần được lắp ghép theo cấu hình hoặc điều kiện, đăng ký tường minh có thể thuận tiện hơn.
2. **Nhóm đã có quy ước nào?** Nếu phần lớn command của một tính năng đã dùng annotation và hoạt động ổn định, tiếp tục theo quy ước đó giúp giảm chi phí bảo trì. Chỉ đổi mô hình khi có lợi ích cụ thể.
3. **Ai chịu trách nhiệm đăng ký command?** Nếu command thuộc một component nghiệp vụ rõ ràng, annotation giúp giữ khai báo cạnh handler. Nếu command được tập hợp bởi một lớp cấu hình hoặc một module tích hợp, `CommandRegistration` có thể làm ranh giới này rõ hơn.
4. **Phiên bản hiện tại hỗ trợ gì?** Kiểm tra phiên bản Spring Shell, Spring Boot, Java và API có trong dependency thực tế. Không chọn mô hình chỉ dựa trên một ví dụ thuộc phiên bản khác.
5. **Cách nào dễ kiểm thử và vận hành hơn trong dự án?** Đánh giá khả năng xác minh tên command, option, giá trị mặc định, trợ giúp và hành vi khi đầu vào không hợp lệ.

## Nhất quán theo phạm vi tính năng

Nhất quán không có nghĩa là mọi command trong toàn bộ ứng dụng bắt buộc phải dùng một cách khai báo duy nhất. Với ứng dụng lớn hoặc đang chuyển đổi, có thể đặt quy ước theo module hoặc nhóm tính năng. Điều quan trọng là người phát triển biết command thuộc nhóm nào, nơi nào đăng ký nó và cách thêm command mới vào nhóm đó.

Ví dụ, một ứng dụng có thể tổ chức như sau:

| Phạm vi | Mô hình được chọn | Lý do |
| --- | --- | --- |
| `customer` | Annotation | Các command cố định, handler nằm trong component của tính năng |
| `maintenance` | `CommandRegistration` | Danh sách command được tạo theo cấu hình môi trường |
| `reporting` | Annotation | Các command báo cáo có cấu trúc ổn định và ít thay đổi |

Đây là một cách tổ chức minh họa. Dự án nhỏ có thể chỉ cần một mô hình cho toàn bộ command. Dự án đang chuyển đổi có thể duy trì hai mô hình trong các phạm vi riêng, miễn là việc kết hợp được ghi nhận rõ ràng và có kiểm soát.

Hãy xác định một số quy ước cụ thể cho mỗi phạm vi:

- Package hoặc module nào sở hữu các command.
- Mô hình khai báo được dùng cho command mới.
- Quy tắc đặt tên command, option, alias và mô tả trợ giúp.
- Nơi đặt xử lý đầu vào, định dạng kết quả và ánh xạ lỗi.
- Cách kiểm thử command và cách phát hiện đăng ký trùng.

Tránh khai báo cùng một tên command ở cả component annotation và bean `CommandRegistration`. Khi nhiều nguồn đăng ký cùng một tên, kết quả có thể gây xung đột hoặc khó xác định command nào được sử dụng, tùy cơ chế xử lý của phiên bản. Mỗi command cần một nơi sở hữu duy nhất.

## Giữ kiến trúc nghiệp vụ độc lập với mô hình khai báo

Hai mô hình chỉ quyết định cách Spring Shell nhận biết và đăng ký command. Chúng không nên quyết định vị trí của quy tắc nghiệp vụ.

Trong cả hai trường hợp, command adapter nên làm những việc sau:

- Nhận option và argument từ người dùng.
- Chuyển dữ liệu đầu vào thành request của ca sử dụng.
- Gọi application service thông qua dependency injection.
- Chuyển kết quả thành nội dung phù hợp với terminal.
- Xử lý những lỗi đã biết ở ranh giới giao diện và trả kết quả lỗi phù hợp.

Các quy tắc như kiểm tra quyền, tính toán, thay đổi trạng thái và phối hợp repository thuộc lớp ứng dụng hoặc miền nghiệp vụ. Không đưa những quy tắc đó vào annotation, lambda đăng ký command hay lớp cấu hình chỉ vì mô hình khai báo cho phép viết logic tại đó.

Ví dụ, cả hai mô hình đều có thể gọi cùng một service:

```java
@Service
public class GreetingService {

    public String greet(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("Tên không được để trống");
        }
        return "Xin chào, " + name.trim() + "!";
    }
}
```

Nếu sau này thay đổi cách khai báo từ annotation sang `CommandRegistration`, `GreetingService` không cần thay đổi. Tương tự, có thể thêm một REST adapter hoặc một tiến trình nền gọi cùng service mà không phụ thuộc vào Spring Shell.

## Chuyển đổi mô hình có kiểm soát

Khi một phần ứng dụng cần đổi mô hình, hãy chuyển theo từng nhóm command và giữ nguyên hành vi quan sát được của chúng.

1. **Kiểm kê command hiện có.** Ghi nhận tên, alias, mô tả, option, kiểu dữ liệu, giá trị mặc định, tính bắt buộc và handler tương ứng.
2. **Xác nhận phiên bản đích.** Kiểm tra dependency và tài liệu phiên bản Spring Shell mà ứng dụng đang dùng; xác định API đích có hỗ trợ đầy đủ những khả năng command hiện tại cần.
3. **Chọn một phạm vi nhỏ.** Chọn một nhóm command có ranh giới rõ, không chuyển toàn bộ ứng dụng cùng lúc nếu chưa cần thiết.
4. **Chuyển metadata và handler.** Giữ nguyên tên command, option, alias, mặc định, mô tả và cách xử lý đầu vào. Tiếp tục gọi cùng application service.
5. **Kiểm thử trước khi bỏ khai báo cũ.** Xác minh command xuất hiện đúng một lần, trợ giúp phản ánh đúng metadata, đầu vào hợp lệ và không hợp lệ cho kết quả như trước.
6. **Gỡ đăng ký cũ và cập nhật quy ước.** Khi nhóm mới hoạt động, loại bỏ nguồn đăng ký cũ của các command đã chuyển và ghi rõ mô hình được dùng cho command tiếp theo.

Không nên để hai bản đăng ký của cùng command tồn tại trong thời gian dài như một cách dự phòng. Nếu cần chạy song song để so sánh trong môi trường kiểm thử, hãy dùng tên command tách biệt và xác định rõ thời điểm loại bỏ bản cũ.

## Kiểm thử tính nhất quán

Kiểm thử nên xác minh cả hành vi của command và quy ước đăng ký:

| Nội dung cần kiểm tra | Câu hỏi xác minh |
| --- | --- |
| Đăng ký | Mỗi command dự kiến có xuất hiện đúng một lần không? |
| Tên và alias | Tên lệnh, alias có giữ nguyên sau khi chuyển mô hình không? |
| Option và argument | Kiểu dữ liệu, tính bắt buộc và giá trị mặc định có đúng không? |
| Trợ giúp | Tên và mô tả command, option có đủ và dễ hiểu không? |
| Đầu vào sai | Lỗi chuyển đổi hoặc thiếu option được báo theo cách dự kiến không? |
| Nghiệp vụ | Command có gọi đúng use case và trình bày đúng kết quả không? |
| Mã thoát | Khi gọi từ script, thành công và thất bại có được biểu diễn bằng mã thoát phù hợp không? |

Unit test của application service xác minh quy tắc nghiệp vụ mà không cần khởi động Spring Shell. Kiểm thử tích hợp command xác minh quá trình đăng ký, phân tích đầu vào, gọi handler và trình bày kết quả. Cả hai lớp kiểm thử đều cần thiết vì command có thể đăng ký đúng nhưng gọi sai service, hoặc service đúng nhưng metadata đầu vào bị khai báo sai.

## Những lỗi thường gặp khi chọn mô hình

| Cách làm | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Chọn mô hình khác nhau tùy theo sở thích của từng người trong cùng nhóm command | Cấu trúc khó dự đoán và khó hướng dẫn người mới | Thống nhất quy ước theo module hoặc tính năng |
| Đăng ký cùng một command qua cả annotation và builder | Có thể phát sinh tên trùng hoặc hành vi đăng ký khó hiểu | Chỉ định một nguồn sở hữu cho mỗi command |
| Chuyển mô hình nhưng làm thay đổi option hoặc mặc định | Script và người dùng hiện tại có thể bị ảnh hưởng | Lập danh sách metadata và kiểm thử tương thích trước khi chuyển |
| Đưa nghiệp vụ vào lambda cấu hình hoặc phương thức command | Logic khó tái sử dụng và kiểm thử độc lập | Chuyển logic vào application service hoặc domain model |
| Dùng API theo ví dụ của phiên bản khác | Lỗi biên dịch hoặc khác biệt hành vi lúc chạy | Đối chiếu dependency và tài liệu đúng phiên bản |
| Duy trì hai cách đăng ký mà không có quy tắc sở hữu | Người phát triển không biết nơi thêm hoặc sửa command | Ghi rõ phạm vi và mô hình áp dụng trong cấu trúc module |

## Quy ước trước khi thêm command mới

Trước khi tạo command, hãy xác định module sở hữu nó và kiểm tra quy ước của nhóm command đó. Dùng mô hình đã chọn cho phạm vi này, đặt tên và metadata theo quy ước, sau đó gọi application service qua dependency injection. Nếu có lý do kỹ thuật cần đổi mô hình, hãy cập nhật quy ước của phạm vi và chuyển các command liên quan bằng một thay đổi có kiểm thử.

Việc chọn mô hình khai báo nhất quán giúp command dễ tìm, dễ mở rộng và dễ chuyển giao giữa các thành viên. Khi ranh giới command được giữ rõ ràng, nhóm có thể thay đổi cách đăng ký theo nhu cầu và phiên bản Spring Shell mà không làm lan thay đổi sang phần nghiệp vụ của ứng dụng.
