# Đăng ký mục tiêu bằng `@EnableCommand` hoặc `@CommandScan` trong Spring Shell 3.x

Khai báo một command bằng annotation mới chỉ mô tả command đó. Để người dùng thực sự gọi được command, ứng dụng còn phải bật cơ chế đăng ký và bảo đảm các lớp chứa command được phát hiện trong phạm vi phù hợp. Trong mô hình annotation command của Spring Shell 3.x, `@EnableCommand` và `@CommandScan` là những điểm cấu hình liên quan đến việc đưa command vào runtime.

Hiểu đúng phạm vi của hai annotation giúp tránh tình trạng command đã viết nhưng không xuất hiện trong trợ giúp, command bị đăng ký trùng hoặc một cấu hình quét quá rộng làm ứng dụng khó kiểm soát. Bài học tập trung vào cách chọn điểm kích hoạt và phạm vi phát hiện command; cú pháp chi tiết cần đối chiếu với minor version Spring Shell 3.x mà dự án đang dùng.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích vì sao khai báo command và đăng ký command là hai bước khác nhau.
- Mô tả vai trò của `@EnableCommand` và `@CommandScan` trong cấu hình ứng dụng.
- Chọn phạm vi package phù hợp để phát hiện các lớp command.
- Phân biệt command scanning với component scanning thông thường của Spring.
- Phát hiện và xử lý các vấn đề như command không được tìm thấy, đăng ký trùng và quét nhầm phạm vi.
- Kiểm chứng command đã được runtime nhận diện bằng cách khởi động và thử gọi command.

## 1. Khai báo command chưa đồng nghĩa command đã được đăng ký

Một lớp Java có thể mô tả command bằng annotation, nhưng runtime chỉ có thể thực thi command nếu cơ chế đăng ký của ứng dụng phát hiện và kết nối mô tả đó với bộ thực thi.

Hãy phân biệt ba khái niệm:

1. **Khai báo:** nhà phát triển gắn annotation vào lớp hoặc phương thức để mô tả command, tên lệnh, mô tả và tham số.
2. **Phát hiện:** cơ chế scan hoặc cấu hình tìm các khai báo command trong những package hoặc nguồn đã chọn.
3. **Đăng ký:** runtime tạo metadata hoặc đối tượng command cần thiết và đưa command vào tập lệnh có thể gọi.

Nếu chỉ có bước khai báo, lớp command có thể tồn tại trong source code nhưng người dùng vẫn không gọi được. Ngược lại, bật cơ chế scan mà không có lớp command hợp lệ cũng không tạo ra command nghiệp vụ.

Ví dụ, một ứng dụng có cấu trúc:

```text
com.acme.support
├── SupportApplication.java
├── commands
│   └── CustomerCommands.java
└── service
    └── CustomerService.java
```

`CustomerCommands` có thể chứa command `customer list`, nhưng runtime cần được cấu hình để tìm lớp này. Nếu phạm vi scan chỉ bao gồm `com.acme.support.admin`, lớp nằm trong `com.acme.support.commands` sẽ không được phát hiện.

## 2. Vai trò của `@EnableCommand`

`@EnableCommand` là điểm kích hoạt cấu hình command annotation trong ứng dụng. Có thể hiểu đây là tín hiệu cho biết ứng dụng muốn bật hạ tầng cần thiết để nhận diện và đăng ký các command được khai báo theo mô hình tương ứng.

Một cấu hình tối thiểu có thể được biểu diễn như sau:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.shell.command.annotation.EnableCommand;

@Configuration
@EnableCommand
public class ShellCommandConfiguration {
}
```

Ví dụ này minh họa vị trí đặt annotation trên một lớp cấu hình Spring. Annotation bật cơ chế hỗ trợ command; nó không tự định nghĩa các thao tác nghiệp vụ như `customer list` hoặc `report generate`. Những command đó vẫn phải được khai báo trong các lớp command của ứng dụng.

Khi dùng `@EnableCommand`, cần xác định rõ cách phiên bản Spring Shell đang dùng phát hiện các lớp command. Một số cấu hình có thể dựa vào phạm vi mặc định hoặc cơ chế đăng ký đã được thiết lập; nếu cần giới hạn package, hãy dùng cơ chế scan tương ứng được phiên bản đó hỗ trợ.

Không nên đặt `@EnableCommand` rải rác trên nhiều lớp cấu hình chỉ vì command được chia thành nhiều nhóm. Hãy có một điểm cấu hình dễ tìm, trừ khi ứng dụng thực sự có nhiều context độc lập với trách nhiệm đăng ký riêng.

## 3. Vai trò của `@CommandScan`

`@CommandScan` dùng để xác định phạm vi tìm kiếm các khai báo command. Thay vì để việc phát hiện phụ thuộc vào phạm vi mặc định hoặc cấu hình tổng quát của ứng dụng, ta có thể chỉ rõ package chứa các lớp command.

Ví dụ minh họa:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.shell.command.annotation.CommandScan;

@Configuration
@CommandScan(basePackages = "com.acme.support.commands")
public class ShellCommandConfiguration {
}
```

Trong ví dụ, phạm vi scan được giới hạn vào `com.acme.support.commands`. Những lớp command thuộc package này và các package con theo quy tắc scan của framework có thể được phát hiện. Lớp ở package ngoài phạm vi đó sẽ không tự động được đưa vào chỉ vì nó nằm trong cùng repository.

Tên thuộc tính, cách xác định package mặc định và mối quan hệ cấu hình giữa `@CommandScan` với `@EnableCommand` cần được xác nhận theo API của minor version đang sử dụng. Không nên sao chép thuộc tính của một bản 3.x sang bản khác nếu IDE hoặc tài liệu API của dự án không xác nhận thuộc tính đó tồn tại.

### 3.1. Chọn package scan theo cấu trúc module

Một phạm vi scan tốt thường phản ánh ranh giới chức năng của CLI:

```text
com.acme.support
├── SupportApplication.java
├── shell
│   ├── customer
│   │   └── CustomerCommands.java
│   ├── report
│   │   └── ReportCommands.java
│   └── system
│       └── SystemCommands.java
└── service
    ├── CustomerService.java
    └── ReportService.java
```

Với cấu trúc này, có thể chọn `com.acme.support.shell` làm vùng chứa command. Cách tổ chức đó giúp người đọc phân biệt lớp giao tiếp CLI với service nghiệp vụ và tránh quét toàn bộ các package không liên quan.

Nếu command được chia thành nhiều module độc lập, hãy xác định rõ module nào được phép cung cấp command cho ứng dụng hiện tại. Một module chỉ chứa domain service không nhất thiết phải tham gia command scan.

## 4. Phân biệt `@EnableCommand` và `@CommandScan`

Hai annotation liên quan đến cùng quá trình đăng ký nhưng diễn đạt hai ý định cấu hình khác nhau:

| Annotation | Ý định cấu hình | Câu hỏi cần trả lời |
|---|---|---|
| `@EnableCommand` | Kích hoạt hạ tầng hỗ trợ command annotation | Ứng dụng có bật mô hình đăng ký command này không? |
| `@CommandScan` | Xác định phạm vi phát hiện lớp command | Runtime cần tìm command trong package nào? |

Trong một số cách cấu hình, việc scan có thể đồng thời kích hoạt hạ tầng cần thiết hoặc được kết hợp với annotation enablement. Vì vậy không nên mặc định hai annotation luôn là hai lựa chọn loại trừ nhau, cũng không nên gắn cả hai ở mọi nơi mà chưa hiểu cách chúng phối hợp trong đúng phiên bản.

Hãy kiểm tra tài liệu API và ví dụ cấu hình của minor version cụ thể để biết `@CommandScan` đã bao hàm bước enablement hay cần có `@EnableCommand` ở lớp cấu hình. Mục tiêu là có một cấu hình rõ ràng, tránh đăng ký lặp hoặc tạo nhiều registrar cho cùng một tập command.

## 5. Một ví dụ command và cách phát hiện

Giả sử ứng dụng quản lý khách hàng. Lớp command mô tả thao tác CLI và ủy quyền nghiệp vụ cho service:

```java
import org.springframework.shell.command.annotation.Command;

@Command
public class CustomerCommands {

    private final CustomerService customerService;

    public CustomerCommands(CustomerService customerService) {
        this.customerService = customerService;
    }

    @Command(command = "customer list", description = "Liệt kê khách hàng")
    public String list() {
        return customerService.listCustomers();
    }
}
```

`CustomerService` là service nghiệp vụ của ứng dụng. Lớp command làm nhiệm vụ nhận yêu cầu từ CLI và gọi service. Cách khai báo command cụ thể, package annotation và cơ chế tạo bean phải khớp với API của Spring Shell 3.x mà dự án sử dụng.

Sau khi cấu hình điểm đăng ký và phạm vi scan đúng, runtime có thể phát hiện `CustomerCommands` và cung cấp command `customer list`. Khi ứng dụng chưa bật hoặc chưa cấu hình scan đúng, command sẽ không xuất hiện dù code Java vẫn biên dịch thành công.

Ví dụ trên cố ý giữ phần tham số đơn giản để làm rõ quá trình phát hiện. Các bài về argument, option, validation và kiểu kết quả sẽ đi sâu vào hợp đồng của từng command.

## 6. Command scan khác component scan như thế nào?

Spring Framework có cơ chế component scanning để phát hiện các lớp được đánh dấu như `@Component`, `@Service`, `@Repository` hoặc các stereotype tương ứng. Ứng dụng Spring Boot thường có phạm vi component scan bắt đầu từ package chứa lớp ứng dụng chính, trừ khi được cấu hình khác.

Command scanning giải quyết một mục đích chuyên biệt: tìm các khai báo command theo mô hình annotation mà Spring Shell cung cấp. Vì vậy hai cơ chế không nên bị xem là cùng một khái niệm.

| Cơ chế | Đối tượng quan tâm | Kết quả mong đợi |
|---|---|---|
| Component scan | Bean và stereotype của Spring | Bean được đưa vào ApplicationContext |
| Command scan | Lớp hoặc khai báo command theo mô hình Spring Shell | Command được phát hiện và đăng ký với runtime |
| Cấu hình enable command | Hạ tầng hỗ trợ command annotation | Cơ chế đăng ký command được bật theo cấu hình |

Một lớp có thể đồng thời tham gia cấu hình bean và cung cấp command, tùy mô hình lập trình của phiên bản. Tuy nhiên, việc một lớp được component scan phát hiện không tự động chứng minh command đã được đăng ký trong command registry. Hãy xác minh cả bean lẫn command runtime khi cần.

## 7. Chọn phạm vi scan đúng

Phạm vi scan ảnh hưởng trực tiếp đến khả năng tìm thấy command, độ rõ ràng của kiến trúc và nguy cơ xung đột.

### 7.1. Scan quá hẹp

Nếu package được chỉ định không bao gồm lớp command, command sẽ không xuất hiện. Ví dụ:

```text
@CommandScan(basePackages = "com.acme.support.admin")

com.acme.support
├── admin
│   └── AdminCommands.java
└── customer
    └── CustomerCommands.java
```

Với phạm vi minh họa trên, `AdminCommands` nằm trong vùng scan còn `CustomerCommands` ở ngoài. Nếu người dùng gọi `customer list`, runtime có thể báo không tìm thấy command.

### 7.2. Scan quá rộng

Quét từ package gốc quá rộng có thể đưa vào những lớp command không dành cho ứng dụng hiện tại. Điều này đặc biệt dễ xảy ra khi nhiều module chia sẻ chung package gốc hoặc cùng nằm trên classpath.

Hậu quả có thể gồm:

- Command thử nghiệm hoặc command nội bộ xuất hiện trong bản phân phối.
- Hai module đăng ký command có cùng tên hoặc alias.
- Ứng dụng khởi tạo thêm dependency chỉ phục vụ một nhóm command không được dùng.
- Khó xác định module nào chịu trách nhiệm cho command cụ thể.

Hãy scan các package command có chủ đích, đồng thời giữ cấu trúc package phản ánh ranh giới module. Không dùng package scan như một cách thay thế cho thiết kế module rõ ràng.

### 7.3. Package con và cấu hình mặc định

Một số cơ chế scan mặc định lấy package của lớp cấu hình làm gốc và đi xuống các package con; một số cấu hình khác cho phép chỉ định package rõ ràng. Không nên đoán hành vi mặc định từ cách hoạt động của `@ComponentScan` hoặc một annotation khác.

Khi cần chắc chắn, hãy khai báo phạm vi scan tường minh theo API thực tế và viết một kiểm thử xác nhận command ở package dự kiến được phát hiện, trong khi command ngoài phạm vi không xuất hiện.

## 8. Xử lý đăng ký trùng và xung đột command

Khi ứng dụng phát hiện command từ nhiều package hoặc module, có thể xảy ra xung đột tên command. Ví dụ:

```text
module-customer: customer list
module-legacy:   customer list
```

Nếu cả hai cùng được đăng ký trong một runtime, kết quả phụ thuộc quy tắc xung đột của phiên bản và cơ chế đăng ký. Ứng dụng có thể báo lỗi khi khởi tạo, từ chối một khai báo hoặc áp dụng một quy tắc ưu tiên cụ thể. Không nên dựa vào thứ tự scan hoặc thứ tự classpath để quyết định command nào thắng.

Để tránh xung đột:

- Quy hoạch tên command theo miền nghiệp vụ, ví dụ `customer list`, `legacy customer list`.
- Chỉ scan module thật sự cần cung cấp command.
- Dùng một nơi quản lý quy ước tên command và alias.
- Kiểm tra log khởi tạo và thông báo lỗi đăng ký khi ứng dụng bắt đầu.
- Viết kiểm thử xác nhận tên command được đăng ký đúng một lần.

Nếu hai command thực sự có cùng mục đích, hãy hợp nhất hành vi hoặc chọn một implementation thông qua cấu hình module. Không nên giữ hai command trùng chỉ vì cả hai lớp đều hợp lệ về cú pháp Java.

## 9. Kiểm chứng cấu hình đăng ký command

Không nên dừng ở việc ứng dụng khởi động thành công. Một cấu hình scan có thể không phát hiện command nào mà vẫn không làm context lỗi. Cần kiểm tra hành vi thực tế.

Một quy trình xác minh hữu ích:

1. Khởi động ứng dụng bằng cấu hình Spring Shell 3.x đang dùng.
2. Mở trợ giúp hoặc danh sách command theo cơ chế của phiên bản.
3. Xác nhận command mong đợi, ví dụ `customer list`, xuất hiện.
4. Gọi command với dữ liệu phù hợp và xác nhận service được thực thi.
5. Xác nhận command nằm ngoài phạm vi scan không xuất hiện nếu ứng dụng có ranh giới module cần bảo vệ.
6. Kiểm tra log hoặc lỗi khởi tạo để phát hiện command trùng và bean thiếu dependency.

Khi viết kiểm thử, nên có trường hợp dương và âm:

| Trường hợp | Điều cần xác nhận |
|---|---|
| Command trong package được scan | Được phát hiện và gọi được |
| Command ngoài package được scan | Không được đưa vào runtime nếu phạm vi yêu cầu loại trừ |
| Hai command có cùng key | Ứng dụng phát hiện xung đột theo quy tắc đã định |
| Command cần service chưa được cấu hình | Lỗi khởi tạo nêu được dependency còn thiếu |
| Thay đổi package của lớp command | Kiểm thử phát hiện cấu hình scan không còn bao phủ lớp |

Để kiểm thử đơn vị, có thể kiểm tra riêng phương thức command và service. Để kiểm thử scan, cần tạo context với cấu hình tương ứng và xác minh registry hoặc giao diện trợ giúp theo API công khai của phiên bản. Tránh phụ thuộc vào class nội bộ của registrar nếu framework đã cung cấp API kiểm tra ổn định hơn.

## 10. Lỗi thường gặp và cách tìm nguyên nhân

### Command đã biên dịch nhưng không xuất hiện trong help

Kiểm tra lớp command có dùng đúng annotation của mô hình đang chọn không; cấu hình enablement đã được nạp chưa; package của lớp có nằm trong phạm vi scan không; và ứng dụng có chạy đúng Spring Shell runtime không.

### Command xuất hiện ở môi trường phát triển nhưng biến mất trong bản đóng gói

Kiểm tra package hoặc module chứa command có được đưa vào artifact và runtime classpath không. Kiểm tra cấu hình profile, cấu hình scan theo môi trường và việc tách module khi đóng gói.

### Một command xuất hiện hai lần hoặc ứng dụng báo xung đột

Kiểm tra có hai lớp command cùng key hay không, package bị scan từ nhiều cấu hình hay không, và module nào được kéo vào qua dependency. Hợp nhất hoặc đổi key theo quy ước trước khi thay đổi thứ tự scan.

### Bean được tìm thấy nhưng command không được đăng ký

Component scan và command scan có thể có phạm vi cũng như mục tiêu khác nhau. Xác minh command annotation đúng, hạ tầng command được bật và cơ chế đăng ký của Spring Shell được cấu hình đúng.

### Cấu hình annotation không biên dịch

Kiểm tra import có đến đúng package của Spring Shell 3.x không, dependency có đúng artifact không và thuộc tính annotation có tồn tại trong minor version đang dùng không. Không giải quyết lỗi bằng cách sao chép import từ một ví dụ thuộc phiên bản khác.

## 11. Quy tắc tổ chức cấu hình trong dự án

Một cấu hình dễ bảo trì nên trả lời được ba câu hỏi khi người khác mở source code:

1. Ứng dụng bật mô hình command annotation ở đâu?
2. Các package nào được phép cung cấp command?
3. Tên command và module sở hữu được quản lý theo quy ước nào?

Có thể đặt cấu hình tại lớp cấu hình CLI hoặc lớp ứng dụng chính, miễn là nó được nạp vào đúng Spring context. Đối với ứng dụng lớn, tách cấu hình command khỏi cấu hình hạ tầng giúp thay đổi phạm vi scan dễ theo dõi hơn.

Ví dụ bố cục:

```text
com.acme.support
├── SupportApplication.java
├── configuration
│   └── ShellCommandConfiguration.java
├── shell
│   ├── customer
│   │   └── CustomerCommands.java
│   └── report
│       └── ReportCommands.java
└── service
    ├── CustomerService.java
    └── ReportService.java
```

Trong bố cục này, `ShellCommandConfiguration` là nơi tập trung cấu hình enablement hoặc scan; các lớp trong `shell` chỉ mô tả command; các service trong `service` xử lý nghiệp vụ. Sự phân chia này giúp tránh để lớp command tự tạo kết nối, truy vấn hoặc thực hiện quá nhiều logic.

## 12. Tự kiểm tra

**Câu 1.** Vì sao một lớp đã khai báo command vẫn có thể không gọi được từ Spring Shell?

**Gợi ý trả lời:** Vì khai báo mới mô tả command. Ứng dụng còn phải bật hạ tầng đăng ký và phát hiện lớp đó trong phạm vi scan được cấu hình.

**Câu 2.** `@EnableCommand` và `@CommandScan` diễn đạt hai ý định cấu hình nào?

**Gợi ý trả lời:** `@EnableCommand` liên quan đến việc kích hoạt hạ tầng command annotation; `@CommandScan` xác định phạm vi tìm kiếm các lớp command. Cách phối hợp chính xác phải theo API của minor version.

**Câu 3.** Vì sao command scanning không nên bị đồng nhất với component scanning?

**Gợi ý trả lời:** Component scan tìm bean theo stereotype của Spring; command scan tìm các khai báo command để đăng ký với runtime. Một bean được phát hiện không tự động chứng minh command đã được đăng ký.

**Câu 4.** Nếu `CustomerCommands` chuyển từ `com.acme.support.commands` sang `com.acme.support.shell.customer`, cần kiểm tra điều gì?

**Gợi ý trả lời:** Kiểm tra package mới có còn nằm trong phạm vi `@CommandScan` hay không, sau đó khởi động và xác nhận command xuất hiện trong runtime.

**Câu 5.** Cách xử lý an toàn khi hai module cùng khai báo `customer list` là gì?

**Gợi ý trả lời:** Xác định module sở hữu command, đổi key hoặc hợp nhất implementation, giới hạn phạm vi scan và kiểm thử để bảo đảm command chỉ được đăng ký một lần.

## Kết luận

Để command annotation hoạt động trong Spring Shell 3.x, ứng dụng phải cấu hình cơ chế phát hiện và đăng ký command. `@EnableCommand` thể hiện ý định bật hạ tầng command annotation; `@CommandScan` giúp xác định phạm vi tìm kiếm các lớp command theo API của phiên bản.

Hãy đặt cấu hình ở một nơi dễ tìm, giới hạn package scan theo ranh giới chức năng, phân biệt command scan với component scan và kiểm chứng kết quả trong runtime. Khi nâng cấp hoặc thay đổi minor version, đối chiếu import, thuộc tính annotation và cách phối hợp enablement/scan với tài liệu đúng phiên bản để tránh cấu hình hợp lệ về mặt cú pháp nhưng không đăng ký được command như mong đợi.
