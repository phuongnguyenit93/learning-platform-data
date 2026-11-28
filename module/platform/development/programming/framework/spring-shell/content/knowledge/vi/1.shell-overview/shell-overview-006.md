# Vai trò của Spring IoC, Spring Boot và JLine

Khi xây dựng ứng dụng dòng lệnh bằng Spring Shell, ta cần giải quyết ba nhóm vấn đề khác nhau: quản lý các đối tượng và dịch vụ của ứng dụng, khởi tạo và cấu hình toàn bộ chương trình, và tương tác trực tiếp với người dùng qua terminal. Spring IoC, Spring Boot và JLine đảm nhiệm ba nhóm việc đó. Spring Shell kết nối chúng thành một môi trường để khai báo, phân tích và thực thi command.

Hiểu đúng ranh giới giữa các thành phần giúp thiết kế ứng dụng CLI dễ mở rộng, dễ kiểm thử và dễ vận hành. Một command có thể gọi dịch vụ nghiệp vụ, dịch vụ có thể phụ thuộc repository hoặc client HTTP, trong khi người dùng vẫn thao tác với chương trình bằng prompt, phím tắt, lịch sử lệnh và gợi ý hoàn thành.

## 1. Bức tranh tổng thể

Có thể hình dung một ứng dụng Spring Shell qua bốn thành phần:

- **Spring IoC Container** quản lý vòng đời các object của ứng dụng, tạo bean và kết nối các dependency.
- **Spring Boot** khởi động ứng dụng, nạp cấu hình và tự động thiết lập các thành phần hạ tầng phù hợp.
- **JLine** cung cấp lớp tương tác với terminal như đọc dòng lệnh, di chuyển con trỏ, lịch sử lệnh, completion và hiển thị prompt.
- **Spring Shell** cung cấp mô hình command và runtime để ánh xạ lệnh người dùng nhập thành lời gọi method trong ứng dụng.

Ba công nghệ được đề cập không thay thế nhau. Spring IoC không phải bộ đọc command; Spring Boot không phải thư viện chỉnh sửa dòng nhập; JLine không quản lý service nghiệp vụ. Spring Shell đứng ở lớp ứng dụng CLI, sử dụng các khả năng nền tảng này để tạo thành trải nghiệm thống nhất.

~~~mermaid
flowchart TB
    U["Người dùng tại terminal"] --> J["JLine<br/>Đọc dòng nhập và hiển thị"]
    J --> S["Spring Shell<br/>Phân tích và phân phối command"]
    S --> C["Command bean"]
    C --> V["Service nghiệp vụ"]
    V --> R["Repository / API / tài nguyên"]
    B["Spring Boot<br/>Khởi động và cấu hình"] --> I["Spring IoC Container"]
    I -. quản lý bean .-> C
    I -. quản lý bean .-> V
    B -. thiết lập runtime .-> S
    B -. tích hợp terminal .-> J
~~~

Sơ đồ thể hiện hai luồng liên quan. Luồng khởi động do Spring Boot điều phối và tạo Spring ApplicationContext. Trong context đó, Spring IoC quản lý các bean, bao gồm command và service. Khi ứng dụng đã sẵn sàng, luồng tương tác nhận dữ liệu từ terminal, chuyển qua Spring Shell để tìm command phù hợp và gọi method tương ứng.

## 2. Spring IoC: quản lý object và dependency

### 2.1. Vấn đề khi tự tạo object

Giả sử ứng dụng có command tra cứu khách hàng. Command cần một CustomerService; service lại cần CustomerRepository để đọc dữ liệu.

Nếu tự khởi tạo object bằng toán tử new, command phải biết cách tạo service, service phải biết cách tạo repository. Khi cấu trúc ứng dụng lớn lên, việc khởi tạo bị phân tán ở nhiều nơi:

~~~java
CustomerRepository repository = new CustomerRepository();
CustomerService service = new CustomerService(repository);
CustomerCommands commands = new CustomerCommands(service);
~~~

Cách làm này có thể hoạt động trong ví dụ nhỏ, nhưng các lớp dần phụ thuộc vào cách tạo cụ thể của nhau. Việc thay repository thật bằng repository giả khi kiểm thử, thay cấu hình kết nối theo môi trường, hoặc quản lý tài nguyên cần đóng sẽ khó hơn.

### 2.2. Inversion of Control và Dependency Injection

Inversion of Control (IoC) là nguyên tắc chuyển quyền điều phối việc tạo và kết nối object từ mã ứng dụng sang một thành phần quản lý bên ngoài. Trong Spring, thành phần đó là IoC Container, thường được truy cập thông qua ApplicationContext.

Các object do Spring quản lý được gọi là **bean**. Container có thể:

1. Phát hiện bean từ component scanning, chẳng hạn các lớp có annotation như **@Component**, **@Service** hoặc **@Repository**.
2. Tạo bean từ các phương thức **@Bean** trong lớp cấu hình.
3. Tìm dependency phù hợp và inject vào bean cần sử dụng.
4. Quản lý callback vòng đời, scope và các xử lý liên quan đến bean.
5. Cung cấp bean cho những thành phần khác trong ứng dụng.

Dependency Injection (DI) là một cách thực hiện IoC: thay vì một lớp tự tìm hoặc tự tạo dependency, dependency được truyền vào từ bên ngoài. Constructor injection thường là lựa chọn rõ ràng vì dependency bắt buộc được thể hiện ngay trong constructor.

~~~java
@Service
public class CustomerService {
    private final CustomerRepository repository;

    public CustomerService(CustomerRepository repository) {
        this.repository = repository;
    }

    public Optional<Customer> findById(long id) {
        return repository.findById(id);
    }
}
~~~

Spring tạo CustomerService và truyền một bean CustomerRepository phù hợp vào constructor. CustomerService chỉ cần biết hợp đồng mà nó sử dụng; nó không cần biết repository được tạo ra ở đâu hoặc cấu hình kết nối thế nào.

### 2.3. IoC trong ứng dụng Spring Shell

Command cũng là một thành phần của ứng dụng và có thể được Spring quản lý như bean. Khi command cần service, ta khai báo dependency qua constructor:

~~~java
@ShellComponent
public class CustomerCommands {
    private final CustomerService customerService;

    public CustomerCommands(CustomerService customerService) {
        this.customerService = customerService;
    }

    @ShellMethod(key = "customer find", value = "Tra cứu khách hàng theo mã")
    public String find(@ShellOption(value = "--id") long id) {
        return customerService.findById(id);
    }
}
~~~

Trong ví dụ này, Spring Shell nhận diện method là một command thông qua annotation. Spring IoC chịu trách nhiệm tạo CustomerCommands và inject CustomerService. Khi người dùng chạy command, Spring Shell gọi method trên bean đã được quản lý.

Điều này mang lại một số lợi ích:

- **Tách trách nhiệm:** command xử lý giao tiếp đầu vào/đầu ra; service xử lý nghiệp vụ.
- **Dễ kiểm thử:** có thể tạo command với một service giả hoặc mock, hoặc kiểm thử service độc lập.
- **Dễ thay thế implementation:** cấu hình bean có thể thay đổi theo môi trường mà command không cần biết chi tiết.
- **Quản lý vòng đời tập trung:** các dependency dùng chung như repository, client hoặc cấu hình được quản lý nhất quán.

IoC Container không phân tích chuỗi lệnh mà người dùng nhập. Nó bảo đảm các object mà Spring Shell cần gọi đã được tạo và kết nối đúng.

## 3. Spring Boot: khởi động và cấu hình ứng dụng

Spring Framework cung cấp IoC Container và nhiều cơ chế nền tảng, nhưng một ứng dụng vẫn cần mã khởi động, cấu hình và cách tích hợp các thư viện. Spring Boot giảm phần cấu hình thủ công này bằng cơ chế auto-configuration, starter và các quy ước khởi tạo.

### 3.1. Điểm vào của chương trình

Một ứng dụng Spring Boot thường bắt đầu tại method main:

~~~java
@SpringBootApplication
public class CustomerCliApplication {
    public static void main(String[] args) {
        SpringApplication.run(CustomerCliApplication.class, args);
    }
}
~~~

**@SpringBootApplication** kết hợp các chức năng thường dùng: đánh dấu lớp cấu hình, bật auto-configuration và kích hoạt component scanning từ package của lớp ứng dụng. **SpringApplication.run(...)** khởi tạo môi trường chạy, tạo ApplicationContext, nạp cấu hình và làm cho các bean sẵn sàng hoạt động.

Khi tích hợp Spring Shell, các cấu hình tự động và bean do thư viện cung cấp giúp ứng dụng thiết lập command runtime cùng các thành phần terminal cần thiết. Người phát triển tập trung vào command và nghiệp vụ thay vì phải tự dựng toàn bộ hạ tầng khởi động.

### 3.2. Những việc Spring Boot đảm nhiệm

**Khởi tạo ApplicationContext.** Spring Boot tạo và làm mới context, từ đó Spring IoC quản lý các bean trong ứng dụng.

**Auto-configuration.** Boot dựa trên classpath, bean hiện có và cấu hình để lựa chọn các thiết lập phù hợp. Khi thêm starter tương ứng, ứng dụng có thể nhận được cấu hình tích hợp mà không cần khai báo từng thành phần bằng tay.

**Quản lý cấu hình bên ngoài.** Các giá trị như địa chỉ API, thông tin kết nối, chế độ hoạt động hoặc mức log có thể được đưa vào file cấu hình, biến môi trường hay tham số khởi động. Nhờ đó, cùng một gói ứng dụng có thể chạy ở nhiều môi trường với cấu hình khác nhau.

**Quản lý dependency và đóng gói.** Hệ sinh thái starter và cơ chế quản lý dependency giúp chọn các thư viện tương thích. Ứng dụng cũng có thể được đóng gói và chạy theo cách triển khai của Spring Boot.

**Tích hợp các thành phần hạ tầng.** Boot tạo nền tảng để Spring Shell đăng ký command, thiết lập runtime và tích hợp với terminal.

### 3.3. Boot không thay thế Spring Shell

Spring Boot giúp ứng dụng Spring khởi động thuận tiện, nhưng bản thân Boot không định nghĩa ý nghĩa của một command như customer find, cũng không cung cấp đầy đủ mô hình khai báo command của Spring Shell.

Có thể phân biệt như sau:

| Câu hỏi | Thành phần chính |
|---|---|
| Ứng dụng bắt đầu chạy từ đâu? | Spring Boot |
| Bean nào cần được tạo và kết nối với nhau? | Spring IoC Container |
| Chuỗi customer find --id 1001 tương ứng với method nào? | Spring Shell |
| Người dùng di chuyển con trỏ, dùng lịch sử hoặc nhận gợi ý trong terminal ra sao? | JLine |

## 4. JLine: lớp tương tác với terminal

### 4.1. Terminal cần nhiều hơn việc đọc một chuỗi

Một chương trình CLI đơn giản có thể đọc dữ liệu bằng Scanner hoặc System.in. Tuy nhiên, trải nghiệm tương tác tốt thường cần nhiều khả năng hơn:

- Người dùng có thể di chuyển con trỏ, sửa một phần dòng lệnh và xóa ký tự.
- Lệnh đã chạy được lưu trong history để gọi lại.
- Khi gõ command hoặc tham số, chương trình có thể gợi ý phần còn lại.
- Prompt, màu sắc và ký tự điều khiển được hiển thị phù hợp với terminal.
- Chương trình xử lý khác biệt giữa các môi trường terminal và hệ điều hành.

JLine là thư viện Java cung cấp các API để làm việc với terminal và dòng nhập tương tác. Spring Shell sử dụng JLine làm một phần nền tảng cho trải nghiệm shell.

### 4.2. Các khả năng thường gặp của JLine

**Line editing:** hỗ trợ sửa dòng đang nhập, di chuyển con trỏ, chọn và xóa nội dung theo các thao tác bàn phím.

**Command history:** lưu các dòng đã nhập để người dùng duyệt lại và chạy lại lệnh trước đó.

**Completion:** hiển thị gợi ý khi người dùng nhấn phím hoàn thành. Trong ứng dụng Spring Shell, metadata của command và tham số có thể được dùng để cung cấp các gợi ý phù hợp.

**Prompt và hiển thị terminal:** hỗ trợ xây dựng prompt, định dạng văn bản và sử dụng các khả năng hiển thị của terminal.

**Terminal abstraction:** cung cấp lớp trừu tượng để ứng dụng làm việc với nhiều loại terminal mà không phải tự xử lý toàn bộ chi tiết nền tảng.

### 4.3. JLine phối hợp với Spring Shell

JLine xử lý tương tác ở lớp terminal. Spring Shell hiểu cấu trúc command của ứng dụng và điều phối việc thực thi. Ví dụ, khi người dùng nhập:

~~~text
shell:> customer find --id 1001
~~~

JLine thu nhận dòng nhập. Spring Shell phân tích tên command và đối số, tìm command tương ứng, chuyển giá trị 1001 vào tham số id, rồi gọi method trên command bean. Method sử dụng service để xử lý nghiệp vụ và trả kết quả. Spring Shell đưa kết quả ra terminal thông qua lớp tương tác.

Như vậy, JLine không cần biết khách hàng là gì hoặc quy tắc tra cứu ra sao. Nó tập trung vào thao tác terminal. Spring Shell xử lý ý nghĩa của command và lời gọi. Các bean nghiệp vụ vẫn được Spring IoC quản lý.

Khi sử dụng Spring Shell, phần lớn ứng dụng không cần tự tạo và quản lý Terminal hay LineReader của JLine. Chỉ nên làm việc trực tiếp với API JLine khi có yêu cầu terminal đặc thù mà abstraction sẵn có của Spring Shell chưa đáp ứng.

## 5. Luồng khởi động và thực thi một command

Hai luồng dưới đây cho thấy vai trò của từng thành phần trong vòng đời một ứng dụng CLI.

### 5.1. Luồng khởi động

1. JVM gọi method main của lớp ứng dụng.
2. SpringApplication.run(...) của Spring Boot bắt đầu quá trình khởi động.
3. Boot đọc cấu hình, áp dụng auto-configuration và tạo ApplicationContext.
4. Spring IoC phát hiện hoặc đăng ký các bean, sau đó tạo và inject dependency.
5. Cấu hình Spring Shell thiết lập command runtime; các thành phần terminal như JLine được tích hợp.
6. Ứng dụng sẵn sàng nhận lệnh theo chế độ chạy đã cấu hình.

~~~mermaid
sequenceDiagram
    participant Main as main()
    participant Boot as Spring Boot
    participant IoC as Spring IoC
    participant Shell as Spring Shell
    participant JLine
    Main->>Boot: SpringApplication.run()
    Boot->>IoC: Tạo ApplicationContext
    IoC->>IoC: Tạo bean và inject dependency
    Boot->>Shell: Khởi tạo command runtime
    Shell->>JLine: Thiết lập tương tác terminal
    JLine-->>Shell: Terminal sẵn sàng
    Shell-->>Main: Ứng dụng sẵn sàng
~~~

### 5.2. Luồng thực thi command tương tác

1. Người dùng nhập một dòng lệnh tại prompt.
2. JLine đọc và hỗ trợ chỉnh sửa dòng nhập.
3. Spring Shell phân tích command, đối số và tùy chọn.
4. Spring Shell xác định method command tương ứng và chuyển đổi dữ liệu đầu vào sang kiểu tham số.
5. Method command gọi service đã được inject bởi Spring IoC.
6. Service thực hiện nghiệp vụ và trả kết quả.
7. Spring Shell hiển thị kết quả cho người dùng qua terminal.

~~~mermaid
sequenceDiagram
    actor User as Người dùng
    participant JLine
    participant Shell as Spring Shell
    participant Command as Command bean
    participant Service as Service bean
    User->>JLine: customer find --id 1001
    JLine->>Shell: Dòng lệnh đã nhập
    Shell->>Shell: Phân tích command và đối số
    Shell->>Command: Gọi method find(id=1001)
    Command->>Service: findById(1001)
    Service-->>Command: Kết quả nghiệp vụ
    Command-->>Shell: Chuỗi kết quả
    Shell-->>JLine: Nội dung cần hiển thị
    JLine-->>User: Hiển thị kết quả
~~~

Trong luồng này, Spring IoC đã hoàn thành việc tạo command và service từ trước khi method được gọi. Việc gọi command không đồng nghĩa với việc tạo lại toàn bộ dependency ở mỗi lần người dùng nhập lệnh.

## 6. Ví dụ kết hợp các thành phần

Ví dụ sau minh họa cách tổ chức một command tra cứu khách hàng. Các import được lược bỏ để tập trung vào quan hệ giữa các lớp.

Lớp khởi động:

~~~java
@SpringBootApplication
public class CustomerCliApplication {
    public static void main(String[] args) {
        SpringApplication.run(CustomerCliApplication.class, args);
    }
}
~~~

Service chứa logic ứng dụng:

~~~java
@Service
public class CustomerService {
    public String findById(long id) {
        if (id == 1001L) {
            return "1001 - Nguyen An";
        }
        return "Không tìm thấy khách hàng có mã " + id;
    }
}
~~~

Command công bố giao diện cho người dùng:

~~~java
@ShellComponent
public class CustomerCommands {
    private final CustomerService customerService;

    public CustomerCommands(CustomerService customerService) {
        this.customerService = customerService;
    }

    @ShellMethod(key = "customer find", value = "Tra cứu khách hàng theo mã")
    public String find(@ShellOption(value = "--id") long id) {
        return customerService.findById(id);
    }
}
~~~

Khi ứng dụng chạy, Spring Boot khởi tạo context. Spring IoC phát hiện CustomerService và CustomerCommands, tạo hai bean và inject CustomerService vào constructor của CustomerCommands. Spring Shell nhận diện method find là command customer find. JLine cung cấp trải nghiệm nhập lệnh trong phiên terminal tương tác.

Ví dụ phiên chạy:

~~~text
shell:> customer find --id 1001
1001 - Nguyen An

shell:> customer find --id 2002
Không tìm thấy khách hàng có mã 2002
~~~

Các lớp có ranh giới trách nhiệm rõ ràng: lớp main khởi động ứng dụng, command nhận và trình bày yêu cầu, service xử lý nghiệp vụ. Khi thay cách lưu trữ khách hàng, có thể bổ sung repository và inject vào service mà không cần thay đổi cách JLine đọc dòng lệnh.

Ví dụ dùng mô hình annotation command phổ biến của Spring Shell. Khi triển khai, cần sử dụng API và cấu hình phù hợp với phiên bản Spring Shell được chọn trong dự án.

## 7. Chế độ tương tác và chế độ chạy command/script

Ứng dụng CLI có thể được sử dụng theo nhiều cách. Trong phiên **interactive**, người dùng làm việc liên tục tại prompt. Các tính năng line editing, history và completion của JLine có giá trị rõ rệt.

Trong chế độ **non-interactive** hoặc khi chạy command/script, đầu vào có thể được cung cấp sẵn từ tham số, script hay tiến trình gọi chương trình. Khi đó, trải nghiệm chỉnh sửa dòng lệnh tương tác có thể không xuất hiện hoặc không cần thiết. Tuy nhiên, mô hình bean, dependency injection và logic command vẫn thuộc ứng dụng Spring.

Điểm cần nhớ là ba thành phần vẫn giữ vai trò riêng:

- Spring Boot chuẩn bị ứng dụng và cấu hình runtime.
- Spring IoC cung cấp command bean cùng các dependency của chúng.
- Spring Shell điều phối command trong cả quy trình thực thi phù hợp.
- JLine hỗ trợ trải nghiệm terminal tương tác khi chế độ chạy cần đến nó.

Khi thiết kế command dùng được cả từ người dùng trực tiếp lẫn script, nên ưu tiên tham số rõ ràng, kết quả có cấu trúc ổn định và mã thoát phù hợp. Không nên để logic nghiệp vụ phụ thuộc vào thao tác bàn phím hoặc trạng thái hiển thị của terminal.

## 8. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| Spring IoC đọc và phân tích command. | Spring IoC quản lý bean và dependency; Spring Shell phân tích và phân phối command. |
| Spring Boot chính là framework CLI. | Boot khởi động và cấu hình ứng dụng; Spring Shell cung cấp mô hình và runtime cho command. |
| JLine xử lý nghiệp vụ của command. | JLine xử lý terminal và dòng nhập; nghiệp vụ thuộc service của ứng dụng. |
| Mỗi lần gọi command phải tạo mới service. | Bean do Spring quản lý thường được tạo theo scope đã cấu hình; command sử dụng dependency được inject. |
| Dùng Spring Shell thì luôn phải gọi trực tiếp API JLine. | Spring Shell đã tích hợp JLine cho các chức năng terminal thông dụng; chỉ dùng trực tiếp khi có nhu cầu đặc thù. |
| Chạy script cần toàn bộ tính năng tương tác của JLine. | Script và non-interactive thường không cần line editing hoặc prompt tương tác. |

Một lỗi thiết kế phổ biến là đặt toàn bộ truy cập dữ liệu và quy tắc nghiệp vụ trực tiếp trong method command. Cách đó khiến command khó kiểm thử và khó tái sử dụng. Nên giữ command mỏng, chuyển nghiệp vụ sang service và để Spring IoC kết nối các thành phần.

Một lỗi khác là tự khởi tạo dependency bằng new bên trong command trong khi dependency đó đã được cấu hình như bean Spring. Việc này có thể bỏ qua cấu hình, proxy hoặc vòng đời do container quản lý. Hãy ưu tiên constructor injection cho dependency thuộc ứng dụng Spring.

## 9. Kiểm thử theo đúng ranh giới trách nhiệm

Phân tách ba lớp cũng giúp chọn cách kiểm thử phù hợp:

- **Service:** kiểm thử độc lập quy tắc nghiệp vụ bằng unit test. Không cần khởi động terminal hay Spring Shell nếu logic không phụ thuộc chúng.
- **Command:** kiểm tra việc nhận tham số, gọi đúng service và định dạng kết quả. Có thể cung cấp service giả để kiểm soát đầu vào và đầu ra.
- **Tích hợp Spring:** dùng kiểm thử context khi cần xác minh component scanning, bean wiring hoặc cấu hình auto-configuration.
- **Terminal/JLine:** kiểm tra tích hợp terminal khi ứng dụng có cấu hình prompt, completion hoặc hành vi nhập liệu tùy biến.

Không nên dùng kiểm thử terminal để xác minh mọi quy tắc nghiệp vụ. Kiểm thử ở đúng lớp giúp xác định lỗi nhanh hơn: lỗi tạo bean thuộc cấu hình Spring, lỗi ánh xạ command thuộc Spring Shell, lỗi nhập liệu thuộc lớp terminal, còn lỗi xử lý dữ liệu thuộc service.

## 10. Kết luận

Trong một ứng dụng Spring Shell, Spring IoC, Spring Boot và JLine tạo thành nền tảng cho các trách nhiệm khác nhau. Spring IoC quản lý object và dependency; Spring Boot khởi động, cấu hình và tích hợp ứng dụng; JLine cung cấp trải nghiệm làm việc với terminal. Spring Shell kết nối các khả năng đó bằng cách biến method của bean thành command có thể gọi từ dòng lệnh.

Khi hiểu rõ sự phối hợp này, ta có thể tổ chức ứng dụng theo hướng command mỏng, service tập trung nghiệp vụ và dependency được quản lý qua container. Cách tổ chức đó hỗ trợ cả phiên CLI tương tác lẫn quy trình chạy command/script, đồng thời giúp ứng dụng dễ mở rộng và kiểm thử.

