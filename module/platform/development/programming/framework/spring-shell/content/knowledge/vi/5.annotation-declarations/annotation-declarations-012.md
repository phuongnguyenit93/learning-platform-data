# Kiểu trả về, phương thức `void` và cách quan sát đầu ra

Một command Spring Shell có thể thực hiện công việc và trả về kết quả để người dùng quan sát. Kiểu trả về của phương thức command là một phần trong hợp đồng của command: nó cho biết phương thức cung cấp dữ liệu gì cho lớp xử lý kết quả sau khi nghiệp vụ hoàn tất. Với phương thức `void`, command không cung cấp giá trị trả về; nếu cần thông báo cho người dùng, ứng dụng phải chọn một cách xuất thông tin phù hợp.

Hiểu rõ sự khác nhau giữa giá trị trả về, nội dung được hiển thị, log và trạng thái thành công giúp command dễ dùng trong terminal, dễ kiểm thử và có thể tái sử dụng trong script. Bài học này tập trung vào mô hình command annotation của Spring Shell, đồng thời lưu ý rằng cách render một kiểu dữ liệu cụ thể phụ thuộc result handler và cấu hình của phiên bản ứng dụng.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích vai trò của kiểu trả về trong phương thức command.
- Chọn giữa `String`, kiểu dữ liệu đơn giản, đối tượng có cấu trúc và `void`.
- Phân biệt giá trị trả về với output hiển thị, log và exit code.
- Thiết kế command `void` khi thao tác không cần trả dữ liệu và cung cấp phản hồi khi cần.
- Quan sát output trong terminal, khi chuyển hướng luồng chuẩn và trong kiểm thử.
- Tránh phụ thuộc vào cách hiển thị mặc định của đối tượng Java khi output là một phần giao diện người dùng.

## 1. Giá trị trả về là một phần hợp đồng của command

Trong mô hình annotation, một command thường là phương thức Java được Spring Shell phát hiện và đăng ký. Khi người dùng gọi command, framework liên kết input với tham số, gọi phương thức và tiếp nhận kết quả mà phương thức trả về.

Ví dụ:

```java
import org.springframework.shell.command.annotation.Command;

@Command
public class GreetingCommands {

    @Command(command = "hello", description = "Hiển thị lời chào")
    public String hello() {
        return "Xin chào!";
    }
}
```

Phương thức `hello()` trả về một `String`. Giá trị này được đưa qua cơ chế xử lý kết quả của Spring Shell để hiển thị cho người dùng theo cấu hình hiện tại. Phương thức không cần tự quản lý prompt hoặc vòng lặp nhập lệnh.

Có thể nhìn hợp đồng command qua ba phần:

1. **Input:** tên command, argument và option mà người dùng cung cấp.
2. **Execution:** phần thân phương thức thực hiện công việc hoặc gọi service nghiệp vụ.
3. **Result:** giá trị trả về, lỗi hoặc tác động phụ mà ứng dụng tạo ra.

Kiểu trả về nên phản ánh điều command muốn cung cấp. Command tìm kiếm thường có dữ liệu để trả về; command làm mới cache có thể chỉ cần thực hiện tác động; command xuất báo cáo có thể trả về thông tin tóm tắt hoặc vị trí file đã tạo.

## 2. Các kiểu trả về thường gặp

### 2.1. `String`: thông báo trực tiếp cho người dùng

`String` phù hợp khi command cần hiển thị một thông điệp ngắn, trạng thái hoặc nội dung đã được định dạng.

```java
@Command
public class CacheCommands {

    private final CacheService cacheService;

    public CacheCommands(CacheService cacheService) {
        this.cacheService = cacheService;
    }

    @Command(command = "cache clear", description = "Xóa cache ứng dụng")
    public String clear() {
        int removed = cacheService.clear();
        return "Đã xóa " + removed + " mục khỏi cache.";
    }
}
```

Với ví dụ này, phương thức trả về một thông báo đã chứa số lượng mục được xóa. Đây là lựa chọn dễ hiểu cho command tương tác vì người dùng nhận được kết quả ngay sau khi gọi lệnh.

Khi tạo thông báo, hãy dùng nội dung ổn định, ngắn gọn và không tiết lộ thông tin nội bộ. Nếu kết quả có thể được dùng trong script, tránh thêm những dòng trang trí không cần thiết vào dữ liệu mà script cần phân tích.

### 2.2. Kiểu dữ liệu đơn giản

Một command có thể trả về số lượng, trạng thái hoặc giá trị đơn giản nếu result handling được cấu hình để biểu diễn kiểu đó.

```java
@Command
public class CustomerCommands {

    private final CustomerService customerService;

    public CustomerCommands(CustomerService customerService) {
        this.customerService = customerService;
    }

    @Command(command = "customer count", description = "Đếm số khách hàng")
    public long count() {
        return customerService.count();
    }
}
```

Giá trị `long` thể hiện dữ liệu đếm một cách rõ ràng ở tầng Java. Lớp xử lý kết quả quyết định cách biểu diễn giá trị đó trong phiên shell. Nếu ứng dụng cần định dạng cụ thể, chẳng hạn thêm đơn vị hoặc nhãn, có thể trả về chuỗi đã định dạng thay vì phụ thuộc vào cách hiển thị mặc định.

### 2.3. Đối tượng có cấu trúc

Khi command trả về nhiều trường dữ liệu, có thể dùng DTO hoặc record để biểu diễn kết quả có cấu trúc:

```java
public record CustomerSummary(long total, long active, long inactive) {
}
```

```java
@Command
public class CustomerSummaryCommands {

    private final CustomerService customerService;

    public CustomerSummaryCommands(CustomerService customerService) {
        this.customerService = customerService;
    }

    @Command(command = "customer summary", description = "Tóm tắt khách hàng")
    public CustomerSummary summary() {
        return customerService.summarize();
    }
}
```

Đối tượng `CustomerSummary` giữ dữ liệu độc lập với cách trình bày. Đây là cách tổ chức hữu ích khi nhiều lớp có thể sử dụng cùng kết quả hoặc khi ứng dụng có nhiều kiểu hiển thị.

Tuy nhiên, không nên mặc định mọi đối tượng Java đều tự động được hiển thị thành bảng đẹp. Kết quả cuối cùng phụ thuộc result handler được đăng ký và cấu hình. Một handler có thể hỗ trợ một số kiểu cụ thể; kiểu chưa được hỗ trợ có thể không được biểu diễn như mong muốn. Khi output là giao diện công khai, hãy định nghĩa rõ cách render thay vì dựa vào `toString()` mặc định của DTO.

### 2.4. `void`: command không trả về giá trị

`void` phù hợp khi mục tiêu chính của command là tạo tác động, chẳng hạn gửi một yêu cầu, làm mới dữ liệu hoặc kích hoạt một quy trình.

```java
@Command
public class IndexCommands {

    private final SearchIndexService indexService;

    public IndexCommands(SearchIndexService indexService) {
        this.indexService = indexService;
    }

    @Command(command = "index rebuild", description = "Xây dựng lại chỉ mục tìm kiếm")
    public void rebuild() {
        indexService.rebuild();
    }
}
```

Phương thức `rebuild()` không trả về giá trị. Spring Shell vì thế không có result object từ phương thức này để chuyển cho result handler. Người dùng có thể thấy prompt trở lại mà không có thông báo thành công tự động từ giá trị trả về.

Điều đó không có nghĩa command không làm gì. Tác động của nó có thể là dữ liệu được cập nhật, file được tạo hoặc một tác vụ được gửi đến hệ thống khác. Nếu người dùng cần biết thao tác đã hoàn tất, hãy cung cấp phản hồi phù hợp hoặc để trạng thái được quan sát qua một command khác.

## 3. Khi nào nên dùng `void`, khi nào nên trả kết quả?

Hãy quyết định theo thông tin mà người dùng cần sau khi command chạy.

| Nhu cầu | Kiểu trả về gợi ý | Lý do |
|---|---|---|
| Hiển thị thông báo ngắn | `String` | Nội dung đã được kiểm soát và dễ đọc |
| Trả một giá trị đếm hoặc trạng thái đơn giản | Kiểu số, boolean hoặc kiểu tương ứng | Giữ đúng kiểu dữ liệu ở tầng Java |
| Trả nhiều trường dữ liệu | DTO hoặc record | Tách dữ liệu khỏi cách render |
| Thực hiện tác động mà không cần kết quả | `void` | Thể hiện rõ command không cung cấp result value |
| Tạo báo cáo hoặc file | DTO hoặc `String` mô tả kết quả | Có thể trả đường dẫn, số bản ghi hoặc thông tin tóm tắt |

Ví dụ, `index rebuild` có thể trả `void` nếu quy trình chạy âm thầm và người vận hành sẽ kiểm tra bằng `index status`. Nếu command được gọi trực tiếp trong terminal và người dùng cần xác nhận, trả về một thông điệp như `Đã gửi yêu cầu xây dựng lại chỉ mục.` hoặc `Đã xây dựng lại chỉ mục với 12.450 tài liệu.` sẽ hữu ích hơn.

Không nên trả về một chuỗi thành công trước khi thao tác thực sự thành công. Nếu command chỉ gửi một tác vụ chạy nền, thông báo phải nói rõ yêu cầu đã được tiếp nhận, tránh tạo cảm giác tác vụ đã hoàn tất.

## 4. Cách quan sát đầu ra trong Spring Shell

Đầu ra mà người dùng nhìn thấy có thể đến từ nhiều nguồn. Cần phân biệt chúng để chọn đúng cách triển khai và kiểm thử.

### 4.1. Giá trị trả về được xử lý bởi Spring Shell

Đây là đường đi tự nhiên cho kết quả của command: phương thức trả về một giá trị, runtime tiếp nhận giá trị đó và result handler phù hợp chịu trách nhiệm trình bày.

Với thông điệp văn bản, trả về `String` giúp nội dung rõ ràng. Với dữ liệu có cấu trúc, cần chọn hoặc cấu hình cách render phù hợp với kiểu dữ liệu. Nếu ứng dụng có nhiều dạng kết quả, hãy thống nhất quy ước hiển thị để người dùng không phải học một kiểu output khác nhau cho mỗi command.

### 4.2. Ghi log để phục vụ vận hành

Log dành cho người vận hành hoặc người phát triển điều tra hoạt động của ứng dụng. Log có thể ghi thời điểm bắt đầu, thời lượng, số bản ghi xử lý, mã tương quan hoặc lỗi kỹ thuật.

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

@Command
public class ImportCommands {

    private static final Logger log =
            LoggerFactory.getLogger(ImportCommands.class);

    private final ImportService importService;

    public ImportCommands(ImportService importService) {
        this.importService = importService;
    }

    @Command(command = "data import", description = "Nhập dữ liệu")
    public String runImport() {
        log.info("Starting data import");
        int imported = importService.run();
        log.info("Data import completed: {} records", imported);
        return "Đã nhập " + imported + " bản ghi.";
    }
}
```

Ở đây log ghi nhận sự kiện kỹ thuật, còn giá trị trả về là thông báo dành cho người đang dùng CLI. Hai nội dung có thể liên quan nhưng phục vụ hai mục đích khác nhau.

Không dùng log thay cho phản hồi command nếu người dùng cần biết kết quả ngay. Tùy cấu hình logging, log có thể được ghi vào file, hệ thống tập trung hoặc một luồng khác; người dùng ở terminal chưa chắc nhìn thấy nó.

### 4.3. Ghi trực tiếp ra terminal

Một số tình huống cần hiển thị tiến độ trong lúc command đang chạy lâu. Khi đó, ứng dụng có thể dùng abstraction giao tiếp terminal hoặc API UI mà phiên bản Spring Shell và adapter đang dùng cung cấp.

Ghi trực tiếp bằng `System.out.println()` thường không phải lựa chọn đầu tiên vì nó bỏ qua lớp result handling, có thể trộn lẫn với prompt hoặc output khác và làm kiểm thử khó hơn. Nó cũng không đảm bảo hoạt động giống nhau khi chạy trong môi trường không có terminal.

Nếu cần cập nhật tiến độ, hãy chọn một cơ chế output phù hợp với adapter đang dùng, xác định rõ cách flush và cách xử lý khi người dùng chuyển hướng output. API cụ thể phụ thuộc phiên bản và cấu hình terminal; tránh gắn command nghiệp vụ trực tiếp với một đối tượng terminal nếu phần nghiệp vụ có thể trả trạng thái tiến độ qua abstraction riêng.

## 5. Phân biệt output, log, exception và exit code

Bốn khái niệm này thường bị nhầm lẫn:

| Khái niệm | Ý nghĩa | Người nhận chính |
|---|---|---|
| Output | Kết quả hoặc thông tin command trình bày | Người dùng CLI hoặc script |
| Log | Sự kiện và chẩn đoán trong quá trình chạy | Người vận hành, đội phát triển |
| Exception | Biểu thị một tình huống lỗi trong luồng thực thi | Runtime và cơ chế xử lý lỗi |
| Exit code | Mã trạng thái khi tiến trình kết thúc | Shell hệ điều hành, script, CI pipeline |

Trả về chuỗi `"Có lỗi"` không tự động làm tiến trình có exit code khác `0`. Đó vẫn chỉ là một kết quả văn bản, trừ khi ứng dụng có quy tắc riêng để diễn giải nó. Tương tự, ghi log `ERROR` không tự động khiến command thất bại theo hợp đồng của CLI.

Nếu command không thể hoàn thành do input không hợp lệ, dịch vụ không sẵn sàng hoặc thao tác thất bại, hãy dùng cơ chế exception/error handling thích hợp của ứng dụng. Nếu cần truyền trạng thái thất bại về script, ứng dụng phải ánh xạ lỗi đó sang exit code ở lớp điều phối tiến trình.

Không nên bắt mọi exception rồi trả về một chuỗi chung chung như `Đã xảy ra lỗi`. Cách đó làm mất thông tin cần thiết cho cơ chế xử lý lỗi và có thể khiến script hiểu nhầm rằng command đã thành công. Có thể ghi log lỗi có ngữ cảnh, sau đó để lỗi đi qua exception handling đã cấu hình và hiển thị thông báo an toàn cho người dùng.

## 6. Định dạng kết quả có cấu trúc

Khi command trả về nhiều giá trị, có ba lựa chọn thường gặp.

**Trả về DTO hoặc record:** giữ dữ liệu có kiểu, phù hợp khi ứng dụng có result handler riêng hoặc khi kết quả được nhiều lớp sử dụng.

**Trả về văn bản đã định dạng:** phù hợp với output terminal đơn giản, khi định dạng cần kiểm soát chặt và không cần tái sử dụng dữ liệu như một object.

**Dùng result handler chuyên biệt:** phù hợp khi nhiều command trả về cùng một kiểu dữ liệu và cần hiển thị nhất quán, chẳng hạn danh sách kết quả thành bảng hoặc một đối tượng trạng thái thành các dòng có nhãn.

Ví dụ định dạng văn bản tường minh:

```java
public record IndexStatus(boolean running, long documents, String updatedAt) {
}
```

```java
@Command
public class IndexStatusCommands {

    private final SearchIndexService indexService;

    public IndexStatusCommands(SearchIndexService indexService) {
        this.indexService = indexService;
    }

    @Command(command = "index status", description = "Xem trạng thái chỉ mục")
    public String status() {
        IndexStatus status = indexService.status();
        return "Đang chạy: " + (status.running() ? "có" : "không")
                + System.lineSeparator()
                + "Số tài liệu: " + status.documents()
                + System.lineSeparator()
                + "Cập nhật lúc: " + status.updatedAt();
    }
}
```

Định dạng này tạo output có thể đọc trực tiếp trong terminal. Nếu cần hỗ trợ nhiều định dạng như text, JSON và CSV, nên tách bước chuyển đổi dữ liệu khỏi command method. Command có thể trả về dữ liệu có cấu trúc; một lớp trình bày hoặc result handler chọn định dạng theo option và cấu hình.

Với dữ liệu máy đọc, cần bảo đảm output không bị trộn với prompt, log hoặc thông báo trang trí. Có thể chuyển log sang `stderr` hoặc file và dành `stdout` cho dữ liệu theo hợp đồng của CLI, tùy cách ứng dụng được triển khai.

## 7. Quan sát output trong các môi trường khác nhau

Output có thể được xem theo nhiều cách, tùy cách khởi chạy ứng dụng.

### 7.1. Trong phiên terminal tương tác

Người dùng nhập command, quan sát kết quả, rồi tiếp tục với prompt. Hãy bảo đảm thông báo đủ rõ để người dùng hiểu command đã hoàn thành, đang chạy nền hay chỉ mới tiếp nhận yêu cầu.

### 7.2. Qua chuyển hướng luồng chuẩn

Shell của hệ điều hành có thể chuyển hướng output ra file hoặc nối vào chương trình khác. Ví dụ với PowerShell:

```powershell
java -jar support-cli.jar customer count > customer-count.txt
```

Và với Bash:

```bash
java -jar support-cli.jar customer count > customer-count.txt
```

Đây là ví dụ minh họa cách chuyển hướng `stdout` của tiến trình. Cú pháp command một lần và cách ứng dụng nhận command phụ thuộc cấu hình chạy của CLI. Nếu ứng dụng đang mở phiên REPL, dữ liệu nhập và output có thể được xử lý khác với chế độ chạy một command rồi kết thúc.

`stderr` thường được dùng cho chẩn đoán và lỗi, còn `stdout` thường dành cho kết quả. Nếu script cần phân tích output, hãy giữ output ổn định, tránh in banner hoặc prompt vào cùng luồng dữ liệu.

### 7.3. Trong kiểm thử

Có thể kiểm tra output ở nhiều mức:

- **Unit test phương thức command:** gọi trực tiếp phương thức và kiểm tra giá trị trả về; với `void`, xác minh service được gọi hoặc tác động mong đợi xảy ra.
- **Command integration test:** khởi tạo runtime với cấu hình command và xác nhận command được đăng ký, được gọi và kết quả đi qua result handling đúng cách.
- **Process test:** chạy ứng dụng như tiến trình con, gửi input theo giao thức của ứng dụng, thu `stdout` và `stderr`, sau đó kiểm tra exit code.

Ví dụ unit test cho phương thức trả về chuỗi:

```java
@Test
void returnsMessageWithRemovedCount() {
    when(cacheService.clear()).thenReturn(3);

    String result = commands.clear();

    assertEquals("Đã xóa 3 mục khỏi cache.", result);
}
```

Với command `void`, kiểm tra hành vi thay vì kiểm tra một result value:

```java
@Test
void rebuildsSearchIndex() {
    commands.rebuild();

    verify(indexService).rebuild();
}
```

Hai ví dụ trên là unit test cho phương thức Java. Chúng không thay thế kiểm thử tích hợp để xác nhận Spring Shell đã render output đúng hoặc command được phát hiện trong runtime.

Khi kiểm tra nội dung terminal, tránh phụ thuộc vào mã màu ANSI, khoảng trắng trang trí hoặc prompt nếu những chi tiết đó không thuộc hợp đồng cần kiểm chứng. Tập trung vào nội dung và trạng thái có ý nghĩa với người dùng.

## 8. Thiết kế output tốt cho người dùng và script

Một command có thể được gọi bằng tay hoặc từ script. Output nên được thiết kế dựa trên người nhận.

Với người dùng tương tác:

- Dùng câu ngắn, nêu rõ hành động và kết quả.
- Hiển thị số lượng, đơn vị và định danh cần thiết.
- Khi tác vụ chạy nền, phân biệt trạng thái đã tiếp nhận với trạng thái hoàn tất.
- Khi có lỗi, nêu điều người dùng có thể sửa mà không tiết lộ stack trace hoặc bí mật.

Với script:

- Duy trì định dạng ổn định qua các lần phát hành.
- Tránh trộn log, prompt và banner vào luồng dữ liệu máy đọc.
- Chọn JSON, CSV hoặc một định dạng có hợp đồng rõ nếu dữ liệu cần được xử lý tiếp.
- Dùng exit code để biểu diễn thành công hoặc thất bại, không buộc script phải suy luận từ câu chữ.
- Tài liệu hóa encoding, dấu phân cách, header và quy tắc escape nếu output là CSV hoặc văn bản có cấu trúc.

Không nên để command vừa thực hiện nghiệp vụ vừa tự quyết định quá nhiều chi tiết terminal. Có thể trả dữ liệu rõ ràng từ service, sau đó để command hoặc result handler chịu trách nhiệm chuyển dữ liệu thành nội dung dành cho người dùng.

## 9. Các lỗi thường gặp

### Phương thức `void` nhưng người dùng mong có thông báo

Phương thức không trả result value nên không có nội dung tự động được tạo từ giá trị trả về. Hãy trả một thông báo, dùng output abstraction thích hợp hoặc cung cấp command trạng thái riêng.

### Trả DTO nhưng terminal hiển thị nội dung khó đọc

Kiểm tra result handler đang xử lý kiểu đó. Đừng dựa vào `toString()` mặc định cho output công khai. Tạo định dạng rõ ràng hoặc đăng ký handler phù hợp.

### Log có nhưng người dùng không thấy kết quả

Kiểm tra cấu hình logging và nơi log được ghi. Nếu người dùng cần phản hồi trực tiếp, trả result value hoặc dùng kênh output dành cho terminal.

### Trả chuỗi lỗi nhưng script nhận exit code thành công

Chuỗi là output; nó không tự quyết định trạng thái tiến trình. Dùng exception/error handling và ánh xạ kết quả sang exit code ở lớp launcher hoặc cơ chế điều phối phù hợp.

### Output bị lẫn prompt và log

Xác định rõ dữ liệu nào thuộc `stdout`, dữ liệu chẩn đoán nào thuộc `stderr` hoặc log file. Khi chạy script, cân nhắc chế độ không tương tác và tránh ghi prompt vào luồng dữ liệu máy đọc.

### Dùng `System.out.println()` ở nhiều command

Output trực tiếp phân tán khiến định dạng khó thống nhất và khó kiểm thử. Ưu tiên trả kết quả để result handling xử lý hoặc tập trung output qua abstraction chung.

## 10. Checklist thiết kế kiểu trả về và output

- [ ] Kiểu trả về thể hiện đúng dữ liệu hoặc trạng thái command cần cung cấp.
- [ ] Dùng `void` khi command không cần trả result value.
- [ ] Nếu dùng `void`, đã xác định cách người dùng nhận biết kết quả khi cần.
- [ ] Đã kiểm tra result handler hỗ trợ kiểu dữ liệu trả về.
- [ ] Output công khai không phụ thuộc vào `toString()` mặc định của object.
- [ ] Log phục vụ chẩn đoán và không thay thế phản hồi trực tiếp.
- [ ] Exception và exit code biểu diễn lỗi theo hợp đồng rõ ràng.
- [ ] `stdout` và `stderr` được dùng nhất quán khi có script xử lý output.
- [ ] Unit test kiểm tra return value hoặc side effect tương ứng.
- [ ] Integration/process test xác nhận nội dung hiển thị và exit code nếu cần.

## 11. Tự kiểm tra

**Câu 1.** Khi một command trả về `String`, giá trị đó được dùng như thế nào?

**Gợi ý trả lời:** Spring Shell tiếp nhận giá trị và chuyển qua cơ chế xử lý kết quả để hiển thị theo result handler và cấu hình của ứng dụng.

**Câu 2.** Phương thức command trả về `void` có nghĩa là command không thực hiện tác động nào không?

**Gợi ý trả lời:** Không. Command vẫn có thể cập nhật dữ liệu hoặc gọi service. `void` chỉ có nghĩa phương thức không cung cấp result value cho lớp xử lý kết quả.

**Câu 3.** Vì sao không nên dựa vào `toString()` mặc định của DTO để làm output CLI?

**Gợi ý trả lời:** Cách biểu diễn có thể không thân thiện, không ổn định hoặc làm lộ chi tiết nội bộ. Output công khai cần định dạng có chủ đích.

**Câu 4.** Log ghi `ERROR` có tự động làm tiến trình trả exit code khác `0` không?

**Gợi ý trả lời:** Không. Logging và exit code là hai cơ chế riêng. Ứng dụng phải chuyển trạng thái lỗi sang exception handling hoặc exit code theo hợp đồng.

**Câu 5.** Nên kiểm tra command `void` bằng cách nào trong unit test?

**Gợi ý trả lời:** Xác minh service được gọi hoặc side effect mong đợi xảy ra, thay vì kiểm tra giá trị trả về.

## Kết luận

Kiểu trả về của command xác định dữ liệu mà phương thức cung cấp cho cơ chế xử lý kết quả. `String` phù hợp với thông báo trực tiếp, kiểu dữ liệu đơn giản hoặc DTO giữ kết quả có cấu trúc, còn `void` thể hiện command không cung cấp result value. Khi dùng `void`, hãy chủ động quyết định cách người dùng quan sát trạng thái nếu cần.

Output, log, exception và exit code phục vụ những mục đích khác nhau. Hãy định dạng kết quả rõ ràng, kiểm tra result handler, giữ luồng dữ liệu máy đọc ổn định và kiểm thử cả giá trị trả về lẫn tác động của command. Nhờ đó, command Spring Shell dễ hiểu trong phiên tương tác và đáng tin cậy khi được gọi từ script hoặc pipeline.
