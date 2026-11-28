# Kiểm soát lưu lịch sử và nội dung log

Spring Shell có thể lưu lại câu lệnh người dùng đã nhập để hỗ trợ gọi lại lệnh ở phiên sau. Spring Boot đồng thời ghi log vận hành của ứng dụng. Hai loại dữ liệu này có mục đích khác nhau, nhưng đều có thể chứa tên tài khoản, mã tài nguyên, đường dẫn, tham số hoặc thông tin nhạy cảm.

Kiểm soát lịch sử và log cần trả lời bốn câu hỏi:

1. Ứng dụng đang lưu loại dữ liệu nào?
2. Dữ liệu được lưu ở đâu và trong bao lâu?
3. Ai có thể đọc, sửa hoặc xuất dữ liệu đó?
4. Những trường nào phải loại bỏ, che hoặc chuẩn hóa trước khi ghi?

Bài học tập trung vào Spring Shell 3.x, các thuộc tính cấu hình history, lệnh tích hợp `history` và `stacktrace`, cách tách log khỏi output terminal, cùng quy tắc ghi log an toàn.

## 1. Phân biệt command history, application log và terminal output

Không nên gom mọi dữ liệu được ghi ra màn hình hoặc file vào một khái niệm chung. Spring Shell và Spring Boot có các kênh khác nhau:

| Loại dữ liệu | Nội dung | Mục đích | Ví dụ |
|---|---|---|---|
| Command history | Dòng lệnh người dùng đã nhập | Gọi lại lệnh, tìm lệnh trước đó | `inventory list --warehouse HN` |
| Application log | Sự kiện do ứng dụng và thư viện ghi | Chẩn đoán, vận hành, kiểm toán | `command.completed`, thời gian xử lý |
| Terminal output | Kết quả command hiển thị cho người dùng | Phản hồi thao tác | `Đã cập nhật 12 sản phẩm.` |
| Stack trace | Chuỗi exception và vị trí phát sinh lỗi | Chẩn đoán lỗi kỹ thuật | Tên class, method, cause chain |
| Script file | Các command được lưu để chạy lại | Tự động hóa | `deploy.script` |

Command history thường chứa nguyên văn câu lệnh và đối số. Application log có thể chứa dữ liệu do code ghi qua SLF4J/Logback hoặc logging framework khác. Terminal output có thể bị lưu lại bởi terminal emulator, transcript, CI runner hoặc công cụ ghi màn hình.

**Tắt một kênh không tự động tắt các kênh còn lại.** Ví dụ, tắt history của Spring Shell không xóa command khỏi Bash history, PowerShell transcript hoặc log của pipeline đã gọi ứng dụng.

## 2. Spring Shell lưu command history như thế nào?

Trong Spring Shell 3.x, lịch sử command được bật mặc định và được lưu vào file. Lệnh tích hợp `history` hiển thị các command đã chạy; API của lệnh cũng hỗ trợ ghi history ra một file có thể đọc bởi lệnh `script`.

Các thuộc tính chính:

| Thuộc tính | Tác dụng |
|---|---|
| `spring.shell.history.enabled` | Bật hoặc tắt việc lưu history ra file; mặc định bật |
| `spring.shell.history.name` | Đặt tên file history |
| `spring.shell.config.location` | Chỉ định thư mục cấu hình, bao gồm vị trí file history |
| `spring.shell.command.history.enabled` | Bật hoặc tắt command tích hợp `history`; mặc định bật |

Nếu không cấu hình, tên file được suy ra từ `spring.application.name`; mặc định là `spring-shell.log`. File được tạo trong thư mục làm việc hiện tại. Có thể đổi thư mục bằng `spring.shell.config.location`; giá trị này hỗ trợ placeholder `{userconfig}` để dùng thư mục cấu hình chung của người dùng.

Ví dụ cấu hình cho ứng dụng quản lý kho:

~~~yaml
spring:
  application:
    name: inventory-shell
  shell:
    history:
      enabled: true
      name: inventory-shell.history
    config:
      location: "{userconfig}/inventory-shell"
~~~

Với cấu hình này, Spring Shell giữ history trong file có tên `inventory-shell.history` dưới thư mục cấu hình được chỉ định. Khi triển khai trên nhiều máy, hãy xác định rõ thư mục này nằm trên ổ đĩa nào, người dùng hệ điều hành nào sở hữu file và chính sách backup có bao gồm file history hay không.

## 3. Tắt lưu history và tắt lệnh history là hai việc khác nhau

Khi ứng dụng xử lý dữ liệu nhạy cảm hoặc chạy trong môi trường dùng chung, có thể cần tắt lưu history:

~~~yaml
spring:
  shell:
    history:
      enabled: false
~~~

Thuộc tính trên điều khiển việc lưu history ra file. Nếu chỉ muốn ẩn lệnh tích hợp `history`, dùng:

~~~yaml
spring:
  shell:
    command:
      history:
        enabled: false
~~~

Hai thuộc tính có mục đích khác nhau:

| Cấu hình | Tác động |
|---|---|
| `spring.shell.history.enabled=false` | Tắt lưu command history ra file |
| `spring.shell.command.history.enabled=false` | Không đăng ký command `history` |
| Cả hai cùng `false` | Không lưu history ra file và không cung cấp command xem/xuất history |

Ẩn lệnh `history` không đồng nghĩa history không còn được lưu. Ngược lại, tắt lưu file không nhất thiết đồng nghĩa command `history` bị ẩn khỏi danh sách lệnh. Hãy chọn đúng cấu hình theo mục tiêu.

Nếu file history cũ đã được tạo trước khi tắt tính năng, thay đổi cấu hình không tự xóa file đó. Cần xử lý file cũ theo chính sách lưu giữ: xác định người sở hữu, giới hạn quyền đọc, xóa hoặc lưu trữ đúng thời hạn và kiểm tra cả bản sao lưu.

## 4. Bảo vệ file history

File history có thể chứa nhiều thông tin hơn dự kiến. Một dòng lệnh có thể chứa mã khách hàng, tên máy chủ, đường dẫn nội bộ, tên người dùng hoặc token được truyền trực tiếp dưới dạng đối số.

Ví dụ không an toàn:

~~~text
shell:>auth login --username operator --password P@ssw0rd!
shell:>cloud deploy --api-token eyJhbGciOi...
~~~

Nếu các dòng này được lưu nguyên văn, người có quyền đọc file history có thể lấy được thông tin xác thực. Cần áp dụng các biện pháp sau:

- Đặt file trong thư mục riêng của người dùng hoặc ứng dụng.
- Chỉ cấp quyền đọc/ghi cho tài khoản vận hành cần thiết.
- Không đặt file history trong thư mục chia sẻ, thư mục public hoặc thư mục phục vụ web.
- Kiểm tra quyền của file sau khi cài đặt, nâng cấp và phục hồi backup.
- Quy định thời hạn lưu giữ và quy trình xóa history cũ.
- Nếu thiết bị hỗ trợ, dùng mã hóa ổ đĩa hoặc mã hóa vùng lưu trữ.
- Hạn chế việc xuất history ra file khác; bảo vệ file export giống file history gốc.

Trên Linux, quyền `600` là một ví dụ giới hạn quyền đọc/ghi cho chủ sở hữu:

~~~bash
chmod 600 ~/.config/inventory-shell/inventory-shell.history
~~~

Trên Windows, cấu hình ACL để chỉ tài khoản chạy ứng dụng và nhóm quản trị được phép đọc file. Không dựa vào việc thư mục có tên ẩn hoặc nằm dưới thư mục người dùng để thay thế kiểm soát quyền.

## 5. Không truyền secret trực tiếp trong command line

Biện pháp hiệu quả nhất là thiết kế command sao cho secret không xuất hiện trong dòng lệnh được nhập. Ví dụ, thay vì nhận password hoặc API token như option, command có thể:

- Yêu cầu người dùng nhập secret qua một prompt riêng có che ký tự.
- Đọc secret từ secret manager hoặc credential provider đã được cấu hình.
- Dùng danh tính workload hoặc cơ chế xác thực của môi trường triển khai.
- Nhận một tham chiếu đến secret, sau đó lấy giá trị thật từ kho bí mật ở phía service.

Ví dụ cách gọi không đưa token vào command:

~~~text
shell:>cloud deploy --environment staging --credential-ref production-deployer
~~~

Command chỉ nhận tham chiếu `production-deployer`; service lấy credential từ nơi lưu trữ được bảo vệ. Không ghi giá trị secret vào command history, application log, exception message hoặc output.

Đối với command được gọi từ OS shell, còn có rủi ro từ history của Bash/PowerShell, process arguments, CI/CD command echo và script file. Tắt `spring.shell.history.enabled` không xử lý các kênh này. Hãy thiết kế cách truyền credential phù hợp với môi trường chạy và giới hạn quyền truy cập của tiến trình.

### 5.1. Che input không đồng nghĩa với che history

Một prompt có thể che ký tự khi người dùng nhập password. Tuy nhiên, nếu command chính vẫn nhận secret như một đối số của dòng lệnh, giá trị đó có thể đã xuất hiện trong command history trước khi phần xử lý password bắt đầu.

JLine có API `MaskingCallback` trong các phiên bản hỗ trợ, cho phép biến đổi nội dung hiển thị và nội dung được thêm vào history. Phương thức `display()` quyết định nội dung người dùng nhìn thấy; `history()` quyết định nội dung được lưu. Khi tích hợp trực tiếp JLine, callback có thể thay secret bằng dấu che hoặc trả về `null`/chuỗi rỗng để bỏ dòng khỏi history.

Không giả định callback này tự động áp dụng cho mọi command của Spring Shell. Nó phải được gắn vào đúng `LineReader` đang nhận input; cần xác nhận phiên bản JLine và cách cấu hình reader của ứng dụng. Với ứng dụng Spring Shell thông thường, lựa chọn an toàn là không đặt secret trong command line.

## 6. Lệnh history có thể xuất dữ liệu

Lệnh tích hợp `history` hiển thị những command đã chạy và có thể nhận file để lưu history. API `History.history(File file)` mô tả rõ chức năng hiển thị hoặc ghi history ra file có thể đọc bởi `Script`.

Việc xuất history hữu ích khi cần tái hiện thao tác hoặc chuyển một chuỗi lệnh thành script. Nhưng file xuất có thể chứa nguyên văn các đối số nhạy cảm và được chia sẻ qua email, ticket, chat hoặc hệ thống lưu artifact.

Trước khi chia sẻ file history:

1. Mở và kiểm tra nội dung.
2. Loại bỏ password, token, session ID, thông tin cá nhân và dữ liệu nội bộ không cần thiết.
3. Thay secret bằng placeholder hoặc tham chiếu secret.
4. Xác nhận script sau khi làm sạch vẫn không vô tình thực hiện thao tác phá hủy.
5. Lưu file trong kho có quyền truy cập và thời hạn lưu giữ phù hợp.

Không dùng file history như một script triển khai chính thức nếu chưa rà soát. Lịch sử phản ánh thao tác đã nhập, không phải một quy trình tự động hóa đã được kiểm thử và phê duyệt.

## 7. Kiểm soát command stacktrace

Khi command phát sinh exception, Spring Shell thường hiển thị một thông báo ngắn. Framework ghi nhớ exception gần nhất để người dùng có thể gọi command `stacktrace` và xem toàn bộ chi tiết.

Stack trace có thể chứa:

- Tên package, class, method và cấu trúc nội bộ.
- Đường dẫn file hoặc máy chủ nội bộ.
- Câu SQL, URL, query string hoặc tên bucket.
- Giá trị được đưa vào exception message.
- Dữ liệu từ hệ thống bên ngoài xuất hiện trong cause chain.

Trong môi trường phát triển, command `stacktrace` hữu ích để chẩn đoán. Trong môi trường production dùng chung, có thể tắt command này:

~~~yaml
spring:
  shell:
    command:
      stacktrace:
        enabled: false
~~~

Tắt command `stacktrace` chỉ ngăn người dùng gọi lệnh tích hợp để in chi tiết lỗi. Nó không thay thế việc kiểm soát log, exception handler hoặc quyền đọc file log.

Spring Shell 3.x cũng có command tích hợp `history`; có thể tắt riêng từng command theo thuộc tính `spring.shell.command.<command>.enabled`. Hãy kiểm tra danh sách command thực tế bằng `help` sau khi cấu hình.

## 8. Tách log khỏi output của shell

Spring Boot mặc định ghi log ra console. Khi ứng dụng chạy REPL, log có thể chen vào prompt hoặc trộn với output của command, làm người dùng khó đọc và khiến script nhận dữ liệu không đúng định dạng.

Spring Shell 3.2.8 hướng dẫn có thể làm console log im lặng bằng cách đặt `logging.pattern.console` thành chuỗi rỗng và ghi log vào file bằng `logging.file.name`.

~~~yaml
logging:
  pattern:
    console: ""
  file:
    name: logs/inventory-shell.log
  level:
    root: INFO
    org.springframework.shell: INFO
~~~

Với cấu hình này, log ứng dụng được ghi vào file, còn console không in pattern log mặc định. Command vẫn có thể trả kết quả cho người dùng qua cơ chế output của Spring Shell.

Trong quá trình phát triển, có thể tăng log level cho package cần kiểm tra:

~~~yaml
logging:
  level:
    org.springframework.shell: DEBUG
    com.example.inventory: DEBUG
~~~

Không để `DEBUG` hoặc `TRACE` rộng trên production nếu chưa kiểm tra nội dung mà các logger ghi ra. Thư viện hoặc code nội bộ có thể log payload, header, câu lệnh, tham số hoặc exception message.

Khi bật file log, cần bảo vệ thư mục và file log bằng quyền hệ điều hành. Đặt đường dẫn lưu trữ rõ ràng, thiết lập rotation/giới hạn dung lượng và chính sách retention. Nếu file log nằm trên volume dùng chung, quyền truy cập cần được kiểm soát theo danh tính của ứng dụng.

## 9. Chọn nội dung log theo mục đích

Log vận hành và log kiểm toán có thể cần mức chi tiết khác nhau. Log vận hành giúp chẩn đoán hiệu năng và lỗi; log kiểm toán ghi nhận ai đã thực hiện hành động quan trọng, trên đối tượng nào và kết quả ra sao.

Nên ghi các sự kiện có ý nghĩa như:

- Xác thực thành công hoặc thất bại.
- Truy cập bị từ chối hoặc vi phạm quyền.
- Thay đổi cấu hình, quyền truy cập hoặc thông tin quan trọng.
- Xóa, xuất, nhập hoặc thay đổi hàng loạt dữ liệu.
- Command thất bại do validation hoặc lỗi hệ thống.
- Tác vụ chạy lâu, bị hủy hoặc hoàn tất với kết quả bất thường.

Các trường log thường hữu ích:

| Trường | Mục đích | Lưu ý |
|---|---|---|
| `timestamp` | Thời điểm sự kiện | Dùng định dạng thống nhất và đồng bộ thời gian |
| `event` | Tên sự kiện ổn định | Ví dụ `inventory.delete.completed` |
| `command` | Command đã gọi | Dùng tên command cố định, không ghi raw command line |
| `actorRef` | Tham chiếu người thực hiện | Dùng ID nội bộ hoặc giá trị giả danh phù hợp |
| `resourceRef` | Đối tượng bị tác động | Chỉ ghi định danh cần thiết |
| `outcome` | Kết quả | `SUCCESS`, `REJECTED`, `FAILED` |
| `durationMs` | Thời gian xử lý | Hữu ích cho vận hành |
| `correlationId` | Liên kết các log cùng một thao tác | Không dùng token hoặc session secret làm correlation ID |

Không ghi toàn bộ object request, map tất cả option, raw command line hoặc payload chỉ vì chúng tiện lấy. Chọn trường theo mục đích điều tra và kiểm toán.

## 10. Dữ liệu không nên ghi vào log

Không ghi trực tiếp các dữ liệu sau:

- Password, PIN, API key, access token, refresh token và private key.
- Cookie, session token và credential của dịch vụ.
- Chuỗi kết nối cơ sở dữ liệu có chứa username/password.
- Nội dung file, payload hoặc query có dữ liệu nhạy cảm nếu không cần thiết.
- Thông tin cá nhân không phục vụ mục đích vận hành hoặc kiểm toán.
- Dữ liệu thanh toán, định danh chính phủ hoặc dữ liệu thuộc nhóm phân loại cao.
- Exception message có thể chứa secret hoặc payload do hệ thống ngoài cung cấp.

Nếu cần liên kết các sự kiện mà không lưu dữ liệu gốc, cân nhắc dùng ID giả danh, hash có khóa hoặc mã tham chiếu. Hash không có khóa trên giá trị có miền nhỏ hoặc dễ đoán vẫn có thể bị dò ngược; không dùng hash thường để thay thế bảo vệ secret.

Thông báo cho người dùng và log nội bộ cũng có mục đích khác nhau. Người dùng có thể nhận thông báo ngắn cùng mã tham chiếu lỗi; log được bảo vệ có thể chứa stack trace đã được rà soát để phục vụ chẩn đoán.

## 11. Ghi log an toàn trong Java

Dùng logger có message template cố định và tham số riêng:

~~~java
private static final Logger log =
        LoggerFactory.getLogger(InventoryCommands.class);

log.info(
        "inventory.delete.completed actorRef={} itemCount={} durationMs={}",
        actorRef,
        deletedCount,
        durationMs);
~~~

Không nối chuỗi trực tiếp từ dữ liệu không tin cậy:

~~~java
// Không nên: dữ liệu đầu vào có thể chứa CR/LF.
log.warn("Command rejected: " + userSuppliedReason);

// Tốt hơn: dùng message template cố định và chuẩn hóa dữ liệu.
log.warn("command.rejected command={} reason={}",
        "inventory import",
        safeLogField(userSuppliedReason));
~~~

Hàm chuẩn hóa ví dụ:

~~~java
private static String safeLogField(String value) {
    if (value == null) {
        return "(none)";
    }

    String normalized = value
            .replace('\r', ' ')
            .replace('\n', ' ');

    int maxLength = 160;
    return normalized.length() <= maxLength
            ? normalized
            : normalized.substring(0, maxLength);
}
~~~

Việc dùng placeholder của SLF4J giúp message template ổn định, nhưng tự nó không loại bỏ hoàn toàn log injection. Ký tự CR/LF trong dữ liệu vẫn có thể làm giả thêm dòng log ở một số formatter. Hãy chuẩn hóa dữ liệu không tin cậy và dùng encoder có escaping phù hợp với định dạng log.

Nếu hệ thống hỗ trợ log có cấu trúc, ghi sự kiện thành các trường JSON riêng thay vì ghép thành một chuỗi tùy ý. Giữ tên trường ổn định, giới hạn độ dài input và tránh đưa nguyên văn dữ liệu người dùng vào message.

## 12. Ghi nhận exception mà không làm lộ dữ liệu

Khi log exception, cần cân nhắc cả message và cause chain. Exception có thể mang URL có query string, câu SQL, payload hoặc dữ liệu xác thực trong message.

Ví dụ ghi mã tham chiếu và loại lỗi:

~~~java
try {
    inventoryService.delete(itemId);
}
catch (InventoryAccessException ex) {
    String errorRef = UUID.randomUUID().toString();

    log.error(
            "inventory.delete.failed errorRef={} itemRef={} exceptionType={}",
            errorRef,
            itemRef,
            ex.getClass().getSimpleName());

    return "Không thể xóa dữ liệu. Mã lỗi: " + errorRef;
}
~~~

Nếu cần stack trace để điều tra, chỉ ghi nó vào log được bảo vệ sau khi xác định exception và dữ liệu trong cause chain không làm lộ secret. Không đưa `ex.getMessage()` hoặc `ex.toString()` vào output của người dùng nếu chưa kiểm soát nội dung.

Một số sự kiện cần lưu stack trace đầy đủ; một số sự kiện chỉ cần loại lỗi và mã tham chiếu. Hãy chọn mức chi tiết theo loại sự kiện, không bật ghi toàn bộ stack trace cho mọi lỗi đầu vào.

## 13. Quyền truy cập, tính toàn vẹn và thời hạn lưu giữ

Log và history đều là dữ liệu cần bảo vệ:

**Tính bí mật:** giới hạn người đọc file, thư mục, bản sao lưu và hệ thống log tập trung. Tài khoản ứng dụng chỉ cần quyền ghi log thì không nhất thiết phải có quyền đọc toàn bộ log cũ.

**Tính toàn vẹn:** hạn chế quyền sửa/xóa log, theo dõi thao tác truy cập và thay đổi, cân nhắc lưu bản sao bất biến hoặc cơ chế phát hiện sửa đổi khi log phục vụ kiểm toán.

**Tính sẵn sàng:** cấu hình rotation, giới hạn dung lượng và cảnh báo khi ghi log thất bại hoặc đĩa gần đầy. Log không được tăng vô hạn đến mức làm đầy ổ đĩa và khiến ứng dụng không thể hoạt động.

**Retention:** xác định thời hạn lưu giữ theo nhu cầu vận hành, điều tra, hợp đồng và quy định pháp luật. Không giữ log mãi mãi; cũng không xóa log trước khi hết thời hạn bắt buộc.

**Truyền log:** nếu gửi log qua mạng không tin cậy, dùng giao thức truyền an toàn và xác minh nguồn dữ liệu. Không gửi log có secret tới dịch vụ bên ngoài khi chưa có phê duyệt và đánh giá dữ liệu.

## 14. Ví dụ cấu hình cho môi trường production

Ví dụ sau giữ history theo thư mục cấu hình người dùng, đổi tên file history, ẩn hai command có thể xuất dữ liệu nhạy cảm và ghi application log ra file:

~~~yaml
spring:
  application:
    name: inventory-shell
  shell:
    history:
      enabled: true
      name: inventory-shell.history
    config:
      location: "{userconfig}/inventory-shell"
    command:
      history:
        enabled: false
      stacktrace:
        enabled: false

logging:
  pattern:
    console: ""
  file:
    name: logs/inventory-shell.log
  level:
    root: INFO
    org.springframework.shell: INFO
    com.example.inventory: INFO
~~~

Trong cấu hình này:

- History vẫn được lưu ra file theo tên và thư mục đã đặt.
- Command tích hợp `history` không xuất hiện.
- Command `stacktrace` không cho người dùng in đầy đủ exception ra terminal.
- Log Spring Boot được chuyển vào file, tránh trộn với output của shell.
- Log level mặc định là `INFO`.

Nếu ứng dụng không cần lưu command history, đặt `spring.shell.history.enabled: false`. Nếu cần history để hỗ trợ vận hành, giữ file ở vị trí được bảo vệ và đảm bảo command không nhận secret trực tiếp.

Đây là cấu hình mẫu; quyền file, rotation, backup và retention vẫn cần được thiết lập ở môi trường triển khai.

## 15. Kiểm thử history và log

Kiểm thử không chỉ xác nhận file có được tạo hay không. Cần xác minh nội dung, quyền truy cập, hành vi khi tắt tính năng và dữ liệu nhạy cảm không xuất hiện.

| Kịch bản | Điều cần xác nhận |
|---|---|
| Chạy command thông thường | History ghi command theo cấu hình |
| Đặt `spring.shell.history.enabled=false` | Không tạo hoặc cập nhật file history persistence |
| Đặt `spring.shell.command.history.enabled=false` | Command `history` không còn trong danh sách |
| Đặt `spring.shell.command.stacktrace.enabled=false` | Command `stacktrace` không còn trong danh sách |
| Cấu hình `spring.shell.history.name` | File history dùng tên đã đặt |
| Cấu hình `spring.shell.config.location` | File được tạo trong thư mục đã chỉ định |
| Xuất history | File export được kiểm tra và bảo vệ như history gốc |
| Nhập secret | Secret không xuất hiện trong history, log, exception hoặc output |
| Console logging bị tắt | Log không chen vào prompt hoặc output command |
| File logging được bật | Sự kiện cần thiết vẫn được ghi vào file |
| Input có CR/LF | Log không bị tách dòng hoặc giả mạo event |
| Log vượt giới hạn dung lượng | Rotation/retention hoạt động và ứng dụng xử lý phù hợp |
| Người dùng không có quyền đọc log | Hệ điều hành từ chối truy cập file |

Nên dùng một chuỗi canary giả lập như `TEST_SECRET_DO_NOT_LOG_123` trong test. Sau khi chạy command và đóng ứng dụng, kiểm tra history, file log, output và file export để chắc chắn chuỗi canary không xuất hiện ở nơi không được phép.

## 16. Lỗi thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Chỉ tắt command `history` | History vẫn có thể được lưu ra file | Tắt thêm `spring.shell.history.enabled` nếu cần |
| Chỉ tắt history file | Người dùng vẫn có thể gọi command `history` trong phiên | Tắt riêng `spring.shell.command.history.enabled` |
| Nghĩ tắt history Spring Shell là đủ | Bash, PowerShell, CI hoặc terminal transcript vẫn có thể lưu lệnh | Thiết kế cách truyền secret và cấu hình các kênh bên ngoài |
| Lưu password trong option | Password xuất hiện trong history hoặc process arguments | Dùng prompt riêng hoặc secret provider |
| Xuất history rồi gửi nguyên file | Lộ tham số và thông tin nội bộ | Rà soát, làm sạch và bảo vệ file export |
| In stack trace trong môi trường dùng chung | Lộ package, đường dẫn và dữ liệu trong exception | Tắt command stacktrace; ghi chẩn đoán vào log được bảo vệ |
| Log toàn bộ command line | Ghi cả secret và dữ liệu cá nhân | Log tên command và các trường đã allow-list |
| Chỉ dùng SLF4J placeholder | Vẫn có nguy cơ log injection qua CR/LF | Chuẩn hóa input và dùng encoder có escaping |
| Không giới hạn kích thước log | Có thể làm đầy đĩa hoặc tăng chi phí lưu trữ | Cấu hình rotation, giới hạn dung lượng và retention |
| Đặt log file trong thư mục dùng chung | Người dùng khác có thể đọc dữ liệu vận hành | Dùng thư mục riêng và ACL/quyền tối thiểu |
| Tắt console log nhưng quên file log | Mất thông tin chẩn đoán cần thiết | Xác minh file logging hoạt động trước khi triển khai |

## 17. Quy trình triển khai

1. Liệt kê các kênh có thể lưu command hoặc output: Spring Shell history, OS history, script, CI log, terminal transcript và application log.
2. Xác định command nào có thể nhận dữ liệu nhạy cảm; chuyển secret sang prompt riêng hoặc secret provider.
3. Chọn chính sách history: tắt persistence hoặc lưu trong thư mục riêng có quyền hạn chế.
4. Cấu hình `spring.shell.history.name` và `spring.shell.config.location` nếu cần đổi vị trí.
5. Quyết định có cung cấp command `history` và `stacktrace` trong production hay không.
6. Tách log khỏi output terminal bằng cấu hình console/file phù hợp.
7. Thiết kế event schema và allow-list các trường được ghi.
8. Chuẩn hóa dữ liệu không tin cậy, giới hạn độ dài và dùng structured encoder khi có thể.
9. Thiết lập quyền file, rotation, backup và thời hạn lưu giữ.
10. Kiểm thử bằng canary secret, CR/LF, file export và người dùng không có quyền.

## 18. Tổng kết

Command history và application log là hai loại dữ liệu riêng. Spring Shell 3.x bật lưu history ra file theo mặc định; dùng `spring.shell.history.enabled` để kiểm soát persistence, `spring.shell.history.name` để đổi tên file và `spring.shell.config.location` để đổi thư mục. Thuộc tính `spring.shell.command.history.enabled` chỉ điều khiển command `history`, còn `spring.shell.command.stacktrace.enabled` điều khiển command in chi tiết exception.

Không truyền secret trực tiếp trong command line, vì giá trị có thể xuất hiện trong history, process arguments, script hoặc CI log. Log ứng dụng chỉ nên ghi sự kiện và các trường cần thiết; loại bỏ hoặc che credential, giới hạn dữ liệu người dùng, chuẩn hóa CR/LF và bảo vệ file log bằng quyền truy cập, rotation và retention. Kiểm thử cả nội dung lẫn quyền truy cập để đảm bảo history và log hỗ trợ vận hành mà không làm lộ dữ liệu.

## Tài liệu tham khảo

- [Spring Shell 3.3 — History](https://docs.spring.io/spring-shell/reference/3.3/commands/builtin/history.html) — bật/tắt history persistence, tên file và vị trí lưu.
- [Spring Shell 3.2.8 — Logging](https://docs.spring.io/spring-shell/reference/3.2/customization/logging.html) — tắt console log và chuyển log sang file bằng thuộc tính Spring Boot.
- [Spring Shell 3.3.0 History API](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/standard/commands/History.html) — command history và khả năng xuất ra file.
- [Spring Shell 3.3.0 History.Command API](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/standard/commands/History.Command.html) — marker interface để thay thế command history và thuộc tính tắt command.
- [Spring Shell 3.3.0 StandardCommandsAutoConfiguration API](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/boot/StandardCommandsAutoConfiguration.html) — điều kiện đăng ký các command tích hợp như history và stacktrace.
- [Spring Shell 3.3 — Stacktrace](https://docs.spring.io/spring-shell/reference/3.3/commands/builtin/stacktrace.html) — cách Spring Shell lưu exception gần nhất và hiển thị stack trace.
- [Spring Boot Logging](https://docs.spring.io/spring-boot/reference/features/logging.html) — cấu hình logging framework, console và file output.
- [JLine 3.x History](https://jline.org/versions/3.x/docs/history/) — cơ chế history, lọc và quản lý dữ liệu lệnh đã nhập.
- [JLine 3.30.6 LineReader API](https://javadoc.io/static/org.jline/jline/3.30.6/org/jline/reader/LineReader.html) — overload `readLine(...)` nhận `MaskingCallback`.
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html) — dữ liệu cần loại bỏ, log injection, quyền truy cập, tính toàn vẹn và retention.
