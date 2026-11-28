# Giới hạn của command availability và lệnh bị ẩn

Spring Shell có hai cơ chế thường được dùng để kiểm soát cách người dùng nhìn thấy và gọi command: **availability** và **hidden command**. Availability cho biết command đã đăng ký có thể thực thi trong trạng thái hiện tại hay không. Hidden command hạn chế việc command xuất hiện trong các kênh khám phá như trợ giúp và tự hoàn thành.

Hai cơ chế này cải thiện trải nghiệm CLI và giúp tổ chức command theo trạng thái hoặc mục đích sử dụng. Tuy nhiên, chúng không phải hàng rào bảo mật. Một command bị ẩn vẫn có thể được gọi nếu người dùng biết tên và option; một command đang available vẫn có thể bị gọi trong lúc quyền hoặc trạng thái nghiệp vụ vừa thay đổi. Quyền truy cập phải được kiểm tra ở service hoặc domain layer ngay khi thực hiện hành động.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt command unavailable, command hidden và command không được đăng ký.
- Giải thích phạm vi ảnh hưởng của Availability đối với việc thực thi command.
- Khai báo command ẩn bằng annotation model và programmatic model phù hợp với phiên bản.
- Biết những nơi hidden command không xuất hiện: help, completion và các bề mặt khám phá được hỗ trợ.
- Giải thích vì sao hidden không bảo vệ command khỏi người biết tên lệnh.
- Nhận biết giới hạn thời gian giữa kiểm tra availability và lúc thực thi.
- Đặt authorization và kiểm tra nghiệp vụ ở đúng tầng.
- Viết thông báo availability an toàn, không làm lộ thông tin nhạy cảm.
- Kiểm thử riêng khả năng khám phá, khả năng thực thi và quyền truy cập.

## 1. Ba trạng thái cần phân biệt

Một command có thể ở một trong ba tình trạng sau:

| Tình trạng | Ý nghĩa | Kết quả thường thấy |
|---|---|---|
| Không được đăng ký | Runtime không có command tương ứng | Không tìm thấy command |
| Đã đăng ký nhưng unavailable | Command tồn tại, điều kiện trạng thái hiện tại chưa thỏa | Khi gọi, shell từ chối và đưa ra lý do |
| Đã đăng ký và hidden | Command tồn tại nhưng bị loại khỏi các bề mặt khám phá | Không xuất hiện trong help/completion theo hành vi hidden; vẫn có thể gọi nếu biết tên |

Availability trả lời câu hỏi “command có thể chạy ngay bây giờ không?”. Thuộc tính hidden trả lời câu hỏi “command có nên được quảng bá trong danh sách và gợi ý không?”. Việc command không được đăng ký lại là vấn đề khác: runtime không có registration để phân giải.

Ví dụ, một công cụ vận hành có:

- server connect: thiết lập kết nối.
- server download: chỉ hoạt động khi đã kết nối.
- internal cache-reset: lệnh hỗ trợ nội bộ, không muốn đưa vào help công khai.

Khi chưa kết nối, server download vẫn có thể xuất hiện trong help cùng lý do chưa khả dụng. internal cache-reset có thể bị ẩn khỏi help và completion. Cả hai command vẫn đã được đăng ký trong ứng dụng.

## 2. Giới hạn của command availability

Spring Shell cung cấp Availability.available() và Availability.unavailable(reason). Availability provider đánh giá trạng thái command tại thời điểm được gọi:

~~~java
Availability availability = connected
        ? Availability.available()
        : Availability.unavailable("you are not connected; run connect first");
~~~

Nếu command unavailable, Spring Shell không cho command tiếp tục thực thi và thông báo lý do. Thông tin availability cũng được dùng trong trợ giúp tích hợp, giúp người dùng biết command tồn tại nhưng cần điều kiện nào trước khi chạy. [Command Availability — Spring Shell 3.4](https://docs.spring.io/spring-shell/reference/3.4-SNAPSHOT/commands/availability.html).

Availability hữu ích cho những điều kiện phụ thuộc trạng thái chung của ứng dụng:

- Chưa có phiên kết nối tới máy chủ.
- Chưa chọn workspace hoặc môi trường triển khai.
- Một tác vụ độc quyền đang chạy.
- Dữ liệu cấu hình bắt buộc chưa được nạp.
- Dịch vụ phụ thuộc đang tạm thời không sẵn sàng.

Tuy nhiên, availability chỉ là một quyết định tại thời điểm kiểm tra. Nó không bảo đảm trạng thái vẫn giữ nguyên khi command bắt đầu thực thi.

## 3. Availability không phải authorization

Không dùng availability làm cơ chế phân quyền. Một provider có thể trả unavailable khi người dùng chưa đăng nhập, nhưng điều đó không thay thế việc kiểm tra quyền trong service. Command có thể được gọi từ nhiều nguồn hoặc trạng thái có thể thay đổi giữa lần kiểm tra và lần thực thi.

Ví dụ, availability provider kiểm tra người dùng đã đăng nhập:

~~~java
@Bean
AvailabilityProvider deleteAvailability(SessionState session) {
    return () -> session.isAuthenticated()
            ? Availability.available()
            : Availability.unavailable("you must sign in first");
}
~~~

Đây là phản hồi hữu ích cho CLI. Nhưng service xóa khách hàng vẫn phải xác minh người dùng có quyền xóa khách hàng cụ thể:

~~~java
@Service
public class CustomerService {

    private final AuthorizationService authorization;
    private final CustomerRepository customers;

    public CustomerService(
            AuthorizationService authorization,
            CustomerRepository customers) {
        this.authorization = authorization;
        this.customers = customers;
    }

    public void delete(CustomerId customerId, UserIdentity actor) {
        if (!authorization.canDeleteCustomer(actor, customerId)) {
            throw new AccessDeniedException("Not permitted to delete this customer");
        }

        customers.deleteById(customerId);
    }
}
~~~

AuthorizationService đại diện cho cơ chế phân quyền của ứng dụng. Trong hệ thống thật, việc kiểm tra cần dựa trên danh tính đã xác thực, vai trò, phạm vi tài nguyên và chính sách hiện hành.

Ngay cả khi availability đã kiểm tra quyền, service vẫn phải xác minh lại lúc thực thi. Đây là nguyên tắc bảo vệ mọi caller: CLI, REST API, scheduler hoặc thành phần nội bộ đều phải đi qua cùng quy tắc nghiệp vụ.

## 4. Khoảng thời gian giữa kiểm tra và thực thi

Một giới hạn quan trọng là trạng thái có thể thay đổi sau khi provider trả về available. Đây là tình huống thường được gọi là *time-of-check to time-of-use* (TOCTOU).

~~~mermaid
sequenceDiagram
    participant CLI as Spring Shell
    participant Provider as Availability provider
    participant Service as Service nghiệp vụ
    participant State as Trạng thái hệ thống
    CLI->>Provider: Kiểm tra command
    Provider->>State: Đọc trạng thái
    State-->>Provider: Available
    Provider-->>CLI: Availability.available()
    Note over State: Trạng thái hoặc quyền thay đổi
    CLI->>Service: Thực thi command
    Service->>State: Kiểm tra lại quyền và điều kiện
    State-->>Service: Không còn hợp lệ
    Service-->>CLI: Từ chối thao tác
~~~

Ví dụ, deploy được đánh giá là available khi môi trường đang mở. Ngay sau đó, quản trị viên khóa môi trường. Nếu command chỉ tin kết quả availability cũ, nó có thể triển khai vào môi trường đã bị khóa.

Để xử lý đúng:

1. Dùng availability để thông báo sớm cho người dùng.
2. Kiểm tra lại quyền và trạng thái trong service ngay trước hành động.
3. Dùng transaction, khóa hoặc cơ chế đồng bộ phù hợp nếu nhiều tiến trình có thể tranh chấp cùng tài nguyên.
4. Xử lý trường hợp trạng thái thay đổi như một lỗi nghiệp vụ có thông báo an toàn.

Với thao tác nhạy cảm như xóa dữ liệu, thay đổi quyền, triển khai hoặc thanh toán, kiểm tra tại service là bắt buộc. Availability không thể bảo đảm tính nguyên tử cho hành động.

## 5. Availability không nên thực hiện nghiệp vụ

Availability provider có thể được gọi nhiều lần khi shell kiểm tra trạng thái command hoặc dựng thông tin trợ giúp. Vì vậy, provider cần nhanh, có thể gọi lặp lại và không tạo tác dụng phụ.

Nên:

- Đọc trạng thái từ session manager hoặc state service.
- Dùng dữ liệu đã được theo dõi/cached nếu việc kiểm tra từ xa tốn thời gian.
- Trả về reason ngắn, đủ để người dùng biết bước tiếp theo.
- Đặt timeout nếu phải truy vấn một hệ thống bên ngoài.
- Xử lý lỗi khi không xác định được trạng thái.

Không nên:

- Tự kết nối máy chủ trong availability provider.
- Bắt đầu hoặc hủy một tác vụ.
- Thay đổi cấu hình hay ghi database.
- Thực hiện thao tác có thể bị lặp lại mỗi lần shell kiểm tra.
- Để truy vấn mạng không giới hạn làm chậm help hoặc trải nghiệm CLI.

Ví dụ provider chỉ đọc trạng thái:

~~~java
@Bean
AvailabilityProvider exportAvailability(ExportState state) {
    return () -> state.isRunning()
            ? Availability.unavailable("another export is already running")
            : Availability.available();
}
~~~

Service thực hiện export vẫn phải khóa hoặc kiểm tra trạng thái trong vùng thực thi an toàn. Hai tiến trình có thể cùng thấy isRunning() == false trước khi một tiến trình bắt đầu; chỉ provider không giải quyết được cuộc đua này.

## 6. Lý do unavailable có thể làm lộ thông tin

Reason được hiển thị cho người dùng khi command không khả dụng và có thể xuất hiện trong trợ giúp. Vì vậy, không đưa dữ liệu nhạy cảm hoặc chi tiết vận hành nội bộ vào chuỗi này.

Không nên trả về:

~~~text
tenant acme is blocked by fraud rule FR-9281 for account 004812
~~~

Thông báo an toàn hơn:

~~~text
this operation is currently unavailable; contact an administrator
~~~

Nếu người dùng có thể tự khắc phục, nêu hành động phù hợp:

~~~text
you must select an environment first
~~~

Nếu cần chẩn đoán chi tiết, ghi thông tin vào log có kiểm soát và áp dụng chính sách bảo vệ log. Không hiển thị token, password, session identifier, chuỗi kết nối hoặc chi tiết quy tắc bảo mật cho mọi người dùng CLI.

Với thông báo mặc định của Spring Shell 3.x, reason được nối sau từ “because”. Viết reason như một cụm bắt đầu bằng chữ thường và không có dấu chấm cuối để câu hiển thị tự nhiên. [Tài liệu Availability](https://docs.spring.io/spring-shell/reference/3.4-SNAPSHOT/commands/availability.html).

## 7. Hidden command có tác dụng gì?

Hidden command là command đã đăng ký nhưng không được quảng bá trong các bề mặt khám phá. Tài liệu Spring Shell 3.x mô tả command hidden bị loại khỏi:

- Danh sách trong help.
- Trang trợ giúp chi tiết của command; tra cứu command hidden được trả như command không xác định.
- Completion tương tác.
- Bash completion.

Tuy nhiên, người dùng vẫn có thể thực thi command nếu biết tên command và các option cần thiết. Đây là giới hạn quan trọng nhất: **ẩn command không đồng nghĩa vô hiệu hóa command**. [Hidden Command — Spring Shell 3.2](https://docs.spring.io/spring-shell/reference/3.2-SNAPSHOT/commands/hidden.html).

Hidden phù hợp khi:

- Command phục vụ chẩn đoán nội bộ và không muốn xuất hiện trong help thông thường.
- Command hỗ trợ migration hoặc bảo trì, chỉ dùng trong quy trình có tài liệu riêng.
- Command chưa sẵn sàng để quảng bá nhưng vẫn cần giữ trong ứng dụng thử nghiệm.
- Command phụ trợ được gọi bởi script hoặc một quy trình khác đã biết tên.

Hidden không phù hợp để bảo vệ thao tác quản trị, dữ liệu riêng tư hoặc chức năng chỉ dành cho một nhóm người dùng. Nếu một người dùng có thể gửi tên command trực tiếp, command vẫn có thể được gọi.

## 8. Khai báo command ẩn trong Spring Shell 3.x

### 8.1. Annotation model mới

Trong annotation model mới của Spring Shell 3.4, @Command có thuộc tính hidden. Thuộc tính này có thể đặt ở cấp lớp hoặc cấp phương thức; cấu hình cấp lớp được kế thừa bởi các command method bên trong và có thể được ghi đè ở cấp phương thức.

Ví dụ:

~~~java
import org.springframework.shell.command.annotation.Command;
import org.springframework.stereotype.Component;

@Component
@Command(hidden = true)
public class InternalCommands {

    @Command(command = "cache inspect")
    public String inspectCache() {
        return "Cache diagnostics";
    }

    @Command(command = "cache reset", hidden = false)
    public String resetCache() {
        return "Cache reset requested";
    }
}
~~~

Trong ví dụ, command ở lớp này mặc định được đánh dấu hidden. cache reset đặt hidden = false để hiển thị lại theo metadata method-level. Cần kiểm tra kết quả thực tế bằng help và completion của phiên bản đang sử dụng.

### 8.2. Programmatic model

Với CommandRegistration, dùng .hidden() hoặc .hidden(boolean):

~~~java
@Bean
CommandRegistration internalStatus(
        CommandRegistration.BuilderSupplier builders) {
    return builders.get()
            .command("internal status")
            .hidden()
            .withTarget()
                .function(context -> "Internal status: ready")
                .and()
            .build();
}
~~~

Có thể truyền cờ boolean:

~~~java
.hidden(true)
~~~

hoặc:

~~~java
.hidden(false)
~~~

API CommandRegistration.Builder của Spring Shell 3.4 cung cấp cả hidden() và hidden(boolean). [CommandRegistration.Builder API](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/command/CommandRegistration.Builder.html).

### 8.3. Mô hình annotation legacy

Không nên mặc định rằng mọi phiên bản và mọi mô hình annotation đều có cùng khả năng khai báo hidden. Tài liệu hidden command của các bản Spring Shell 3.0–3.2 ghi nhận tính năng này không được hỗ trợ trong annotation-based configuration ở mô hình được tài liệu đó mô tả. Khi dùng @ShellMethod/@ShellOption legacy, hãy xác nhận API đúng minor version; nếu không có thuộc tính tương ứng, dùng programmatic registration hoặc một cách tổ chức command phù hợp.

## 9. Hidden command trong Spring Shell 4.x

Spring Shell 4.x tiếp tục có metadata hidden. Annotation org.springframework.shell.core.command.annotation.Command có thuộc tính hidden, còn interface Command cung cấp isHidden(). Programmatic builder cũng hỗ trợ .hidden(boolean).

Ví dụ annotation model 4.x:

~~~java
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.stereotype.Component;

@Component
public class InternalCommandsV4 {

    @Command(name = "internal diagnostics", hidden = true)
    public String diagnostics() {
        return "Diagnostics complete";
    }
}
~~~

Ví dụ programmatic model 4.x:

~~~java
@Bean
Command internalDiagnostics() {
    return Command.builder()
            .name("internal diagnostics")
            .description("Internal diagnostics")
            .hidden(true)
            .execute(context -> {
                context.outputWriter().println("Diagnostics complete");
                return ExitStatus.OK;
            })
            .build();
}
~~~

API 4.x xác nhận metadata hidden qua @Command(hidden = true) và Command.isHidden(). Vì chi tiết lọc của help, completion hoặc adapter có thể thay đổi theo minor version, hãy kiểm thử từng bề mặt trong phiên bản thực tế thay vì dựa hoàn toàn vào hành vi được mô tả cho 3.x. [Spring Shell 4.0.3 @Command API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/annotation/Command.html), [Spring Shell 4.0.3 Command API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/Command.html).

## 10. Availability và hidden có thể kết hợp nhưng không thay thế nhau

Hai thuộc tính thể hiện hai chiều khác nhau:

| Cấu hình | Khả năng khám phá | Khả năng thực thi |
|---|---|---|
| Visible + available | Có thể xuất hiện trong help/completion | Có thể chạy nếu các kiểm tra khác cho phép |
| Visible + unavailable | Có thể xuất hiện cùng lý do chưa khả dụng | Bị từ chối bởi availability |
| Hidden + available | Bị loại khỏi các bề mặt khám phá được hỗ trợ | Có thể chạy nếu biết tên và vượt qua các kiểm tra khác |
| Hidden + unavailable | Bị ẩn khỏi khám phá; availability vẫn là điều kiện thực thi | Bị từ chối khi trạng thái chưa thỏa |

Ví dụ, command internal rebuild-index có thể bị ẩn vì chỉ dành cho runbook nội bộ. Nó cũng có thể unavailable khi hệ thống đang xử lý một đợt indexing khác. Ẩn command không làm cho trạng thái unavailable trở thành một cơ chế phân quyền; ngược lại, availability cũng không làm command biến mất khỏi danh sách khám phá.

Nếu kết hợp hai thuộc tính, hãy kiểm thử cả việc command có bị lọc khỏi help/completion và việc lời gọi trực tiếp có bị availability từ chối hay không. Không suy luận kết quả chỉ từ việc command không xuất hiện trong help.

## 11. Khi nào nên ẩn, khi nào nên trả unavailable, khi nào nên gỡ đăng ký?

Chọn cơ chế theo mục đích thực tế:

| Nhu cầu | Cơ chế phù hợp | Lý do |
|---|---|---|
| Người dùng cần biết command có tồn tại nhưng cần kết nối trước | Availability | Help có thể giải thích điều kiện còn thiếu |
| Command dành cho quy trình nội bộ và không muốn quảng bá | Hidden | Loại khỏi các bề mặt khám phá |
| Chức năng không tồn tại trong bản triển khai này | Không đăng ký command | Runtime không cung cấp chức năng |
| Chỉ quản trị viên được thực hiện thao tác | Authorization trong service | Kiểm tra danh tính và quyền tại thời điểm thực thi |
| Tính năng được bật/tắt theo cấu hình triển khai | Conditional registration hoặc feature configuration | Không đăng ký chức năng khi deployment không hỗ trợ |
| Command phụ thuộc dữ liệu/trạng thái thay đổi | Availability kết hợp kiểm tra service | Phản hồi sớm và bảo vệ lại khi thực thi |

Không dùng hidden để thay thế feature flag nếu mục tiêu là loại bỏ hẳn chức năng khỏi bản triển khai. Không dùng unavailable để thay authorization. Không dùng việc không đăng ký command như cách phân quyền theo người dùng nếu command vẫn có thể được gọi qua service hoặc API khác.

## 12. Các rủi ro khi xem hidden như biện pháp bảo mật

Ẩn command chỉ giảm khả năng người dùng vô tình khám phá chức năng. Nó không bảo vệ khỏi những tình huống sau:

- Người dùng biết tên command từ tài liệu nội bộ, log, script hoặc mã nguồn.
- Người dùng thử các tên command phổ biến như admin, debug, internal hoặc reset.
- Alias của command bị lộ qua một tài liệu hoặc một wrapper khác.
- Command được gọi trực tiếp qua process arguments thay vì nhập trong prompt tương tác.
- Một phiên bản hoặc adapter khác không lọc hidden giống cách mong đợi.

Không nên đưa thông tin bí mật vào tên command với suy nghĩ rằng tên khó đoán sẽ bảo vệ thao tác. Cũng không nên dùng hidden để che một command có khả năng đọc/xóa dữ liệu mà không có authorization.

Nếu command thực sự nguy hiểm:

1. Xác thực danh tính người gọi.
2. Kiểm tra quyền theo hành động và tài nguyên.
3. Kiểm tra trạng thái nghiệp vụ tại thời điểm thực thi.
4. Ghi audit event phù hợp.
5. Giới hạn tác động và yêu cầu xác nhận bổ sung nếu quy trình cần.

Hidden có thể được dùng thêm để giữ help gọn, nhưng không thay thế các bước bảo vệ này.

## 13. Kiểm thử availability

Nên kiểm thử provider độc lập và kiểm thử qua command runtime.

**Unit test provider** cần xác nhận:

- Khi điều kiện thỏa, provider trả Availability.available().
- Khi điều kiện không thỏa, provider trả Availability.unavailable(reason) với lý do an toàn.
- Sau khi state thay đổi, lần gọi provider tiếp theo phản ánh trạng thái mới.
- Provider không thay đổi state hoặc thực hiện tác dụng phụ.

**Integration test** cần xác nhận:

- Command available có thể tiếp tục thực thi.
- Command unavailable bị từ chối trước khi target/service chạy.
- Thông báo có reason phù hợp.
- Help thể hiện trạng thái unavailable theo template.
- Khi trạng thái thay đổi, command có thể trở nên available.
- Service vẫn từ chối caller không có quyền dù provider trước đó trả available.

Ví dụ ma trận:

| Trạng thái | Lệnh | Kết quả mong đợi |
|---|---|---|
| Chưa kết nối | download | Bị từ chối với lý do chưa kết nối |
| Đã kết nối | download | Đi tiếp vào command |
| Mất kết nối sau availability check | download | Service kiểm tra lại và từ chối an toàn |
| Người dùng không có quyền | customer delete | Service từ chối dù command đang available |
| Provider không đọc được trạng thái | Command phụ thuộc trạng thái | Áp dụng chính sách fail-closed hoặc fallback đã định nghĩa |

Với hành động nhạy cảm, kiểm thử thêm hai lời gọi đồng thời để xác nhận transaction hoặc khóa nghiệp vụ ngăn thao tác trùng và tranh chấp.

## 14. Kiểm thử hidden command

Không chỉ xác nhận command biến mất khỏi help. Cần kiểm tra cả khả năng gọi trực tiếp để hiểu đúng giới hạn của metadata hidden.

| Kiểm tra | Kết quả mong đợi theo hành vi hidden 3.x |
|---|---|
| help | Không liệt kê command hidden |
| help <hidden-command> | Được xử lý như command không xác định |
| Nhấn Tab tại command prefix | Không gợi ý command hidden |
| Bash completion | Không gợi ý command hidden |
| Gõ chính xác tên command cùng option hợp lệ | Command vẫn có thể được thực thi |
| Gọi command hidden nhưng thiếu input bắt buộc | Parser/validation vẫn xử lý theo hợp đồng input |
| Gọi command hidden và unavailable | Kiểm tra availability từ lời gọi trực tiếp; không dựa vào việc command bị ẩn |

Với Spring Shell 4.x, API vẫn có metadata hidden/isHidden, nhưng cần chạy các kiểm thử trên với đúng phiên bản, runner và completion adapter của ứng dụng.

Nếu command hidden được dùng trong runbook, hãy kiểm thử chính câu lệnh trong runbook và quyền của tài khoản vận hành. Không coi việc không thấy command trong help là bằng chứng người dùng không thể gọi nó.

## 15. Những lỗi thường gặp

### Dùng Availability để phân quyền

Provider có thể trả available trước khi quyền thay đổi hoặc khi caller khác gọi service. Đặt authorization ở service/domain layer và kiểm tra lại ngay khi thực hiện.

### Ẩn command rồi nghĩ rằng không ai gọi được

Hidden chỉ ảnh hưởng khám phá. Người biết tên command và option vẫn có thể gọi. Bảo vệ thao tác bằng xác thực, authorization và kiểm tra nghiệp vụ.

### Nghĩ command unavailable sẽ biến mất khỏi help

Unavailable và hidden là hai thuộc tính khác nhau. Spring Shell 3.4 dùng thông tin unavailable trong help để người dùng thấy command cùng lý do chưa chạy được.

### Dùng reason chứa chi tiết nội bộ

Reason có thể hiển thị cho người dùng. Chỉ cung cấp nguyên nhân ở mức cần thiết; log chi tiết theo chính sách riêng.

### Provider truy vấn hệ thống chậm mỗi lần được gọi

Availability có thể được đánh giá nhiều lần. Dùng state được theo dõi hoặc cache phù hợp, đặt timeout và giữ provider nhẹ.

### Chỉ kiểm thử help mà không thử gọi trực tiếp

Một command ẩn có thể không xuất hiện trong help nhưng vẫn thực thi được. Hãy thử cả đường gọi trực tiếp và xác minh authorization.

### Giả định mọi annotation model đều hỗ trợ hidden như nhau

Khả năng khai báo hidden khác nhau giữa legacy annotation và annotation model mới, cũng như giữa các minor version. Kiểm tra API thực tế hoặc dùng programmatic registration nếu phù hợp.

### Dùng trạng thái availability làm khóa đồng thời

Hai tiến trình có thể cùng nhận available trước khi một tiến trình thay đổi state. Dùng transaction, lock hoặc cơ chế đồng bộ ở tầng nghiệp vụ để bảo vệ thao tác.

## 16. Checklist bảo mật và an toàn

- [ ] Đã xác định command cần visible, hidden, unavailable hay không đăng ký.
- [ ] Không dùng hidden làm cơ chế bảo vệ dữ liệu hoặc thao tác quản trị.
- [ ] Không dùng availability thay authorization.
- [ ] Service/domain layer kiểm tra danh tính và quyền tại thời điểm thực thi.
- [ ] Điều kiện phụ thuộc trạng thái được kiểm tra lại trong service.
- [ ] Thao tác cạnh tranh có transaction, lock hoặc cơ chế đồng bộ phù hợp.
- [ ] Availability provider nhanh, có thể gọi lặp lại và không có tác dụng phụ.
- [ ] Reason không tiết lộ token, password, session hoặc dữ liệu nhạy cảm.
- [ ] Help và completion được kiểm tra để xác nhận hành vi hidden.
- [ ] Đã thử gọi trực tiếp command hidden bằng tên chính xác.
- [ ] Đã kiểm thử hidden kết hợp với unavailable nếu ứng dụng dùng cả hai.
- [ ] Đã xác nhận API hidden theo đúng major/minor version.
- [ ] Có audit log phù hợp cho thao tác quản trị hoặc thao tác nhạy cảm.

## 17. Tự kiểm tra

**Câu 1.** Command unavailable khác command hidden như thế nào?

**Gợi ý trả lời:** Unavailable là command đã đăng ký nhưng điều kiện hiện tại chưa cho phép thực thi; hidden là command không được quảng bá trong các bề mặt khám phá như help hoặc completion.

**Câu 2.** Người dùng có thể gọi command hidden nếu biết tên không?

**Gợi ý trả lời:** Có. Hidden không vô hiệu hóa command; người dùng biết tên và option vẫn có thể gọi nếu các điều kiện thực thi khác cho phép.

**Câu 3.** Vì sao availability không thay thế authorization?

**Gợi ý trả lời:** Trạng thái có thể thay đổi sau lần kiểm tra và service có thể được gọi từ nhiều nguồn. Quyền phải được xác minh tại service/domain layer khi thực hiện hành động.

**Câu 4.** Hidden command trong Spring Shell 3.x bị loại khỏi những bề mặt nào?

**Gợi ý trả lời:** Theo tài liệu 3.x, command bị loại khỏi help listing, trang help chi tiết, interactive completion và Bash completion.

**Câu 5.** Nếu provider trả available nhưng quyền bị thu hồi ngay sau đó, service cần làm gì?

**Gợi ý trả lời:** Service phải kiểm tra lại authorization tại thời điểm thực thi và từ chối hành động nếu caller không còn quyền.

**Câu 6.** Có nên gọi API từ xa không giới hạn thời gian trong availability provider không?

**Gợi ý trả lời:** Không. Provider có thể được gọi nhiều lần và làm chậm shell. Ưu tiên state đã theo dõi/cache, đặt timeout và không thực hiện tác dụng phụ.

## Kết luận

Availability và hidden giải quyết hai nhu cầu khác nhau. Availability cho biết command đã đăng ký có thể chạy trong trạng thái hiện tại hay không và cung cấp lý do khi bị khóa. Hidden giảm khả năng khám phá command bằng cách loại nó khỏi help và completion theo hành vi của phiên bản. Command hidden vẫn có thể được gọi nếu người dùng biết tên và option.

Không dùng hai cơ chế này để thay thế xác thực hoặc phân quyền. Trạng thái có thể thay đổi sau khi availability được kiểm tra; command có thể được gọi từ nhiều đường khác nhau; người dùng có thể biết tên command ẩn. Hãy kiểm tra quyền và điều kiện nghiệp vụ trong service ngay khi thực thi, bảo vệ thao tác đồng thời bằng cơ chế phù hợp và giữ reason an toàn. Khi đó, metadata Spring Shell cải thiện trải nghiệm CLI mà không tạo cảm giác bảo mật sai.

## Tài liệu tham khảo

- [Spring Shell 3.4 — Command Availability](https://docs.spring.io/spring-shell/reference/3.4-SNAPSHOT/commands/availability.html)
- [Spring Shell 3.2 — Hidden Command](https://docs.spring.io/spring-shell/reference/3.2-SNAPSHOT/commands/hidden.html)
- [Spring Shell 3.4 — Command API](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/command/annotation/Command.html)
- [Spring Shell 3.4 — CommandRegistration.Builder API](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/command/CommandRegistration.Builder.html)
- [Spring Shell 4.0.3 — Command annotation API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/annotation/Command.html)
- [Spring Shell 4.0.3 — Command API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/Command.html)
