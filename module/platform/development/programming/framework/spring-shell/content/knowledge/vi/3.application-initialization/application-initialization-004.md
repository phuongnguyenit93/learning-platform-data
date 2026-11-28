# Tổ chức package để lớp khai báo lệnh được nhận diện

Trong ứng dụng Spring Shell sử dụng mô hình khai báo lệnh bằng annotation, một method chỉ trở thành command khi Spring Shell nhận được bean chứa method đó. Vì vậy, việc đặt lớp command vào đúng package và để Spring quản lý lớp đó là một phần quan trọng của quá trình khởi tạo ứng dụng.

Thông thường, Spring Boot dùng component scanning để tìm các lớp được đánh dấu bằng annotation như @Component, @Service và các stereotype liên quan. Spring Shell cung cấp @ShellComponent cho lớp chứa các method khai báo lệnh. Khi lớp này nằm trong phạm vi quét và được tạo thành bean, Spring Shell có thể nhận diện các method có @ShellMethod để đưa vào command runtime.

Bài học này tập trung vào cách tổ chức package cho ứng dụng Spring Shell, cách xác định phạm vi component scanning, cách xử lý command nằm ngoài package gốc và cách kiểm tra command đã được đăng ký. Mục tiêu là giúp ứng dụng nhận diện command ổn định khi số lượng command, service và module tăng lên.

## 1. Vì sao tổ chức package ảnh hưởng đến việc nhận diện command?

Java dùng package để định danh lớp và tổ chức mã nguồn. Spring dùng package làm một trong những căn cứ để tìm bean thông qua component scanning. Spring Shell tiếp tục sử dụng các bean command đã được đăng ký trong Spring context để xây dựng khả năng thực thi lệnh.

Có thể mô tả quá trình này qua các bước:

1. Spring Boot khởi động ứng dụng và tạo ApplicationContext.
2. Component scanning tìm các lớp nằm trong phạm vi package được cấu hình.
3. Các lớp phù hợp với bộ lọc component được đăng ký thành bean.
4. Spring Shell nhận diện bean command, đọc metadata từ các annotation khai báo lệnh và đăng ký command tương ứng.
5. Khi ứng dụng sẵn sàng, người dùng có thể gọi command theo tên đã khai báo.

~~~mermaid
flowchart TD
    A["Spring Boot khởi động"] --> B["Xác định package được quét"]
    B --> C["Component scanning tìm lớp"]
    C --> D{"Lớp có stereotype phù hợp?"}
    D -- "Không" --> E["Không tạo bean từ lớp này"]
    D -- "Có" --> F["Đăng ký bean trong ApplicationContext"]
    F --> G{"Lớp command có cấu hình Spring Shell?"}
    G -- "Không" --> H["Bean được quản lý nhưng không tạo command annotation"]
    G -- "Có" --> I["Spring Shell đọc @ShellMethod"]
    I --> J["Command được đưa vào runtime"]
    J --> K["Người dùng gọi lệnh"]
~~~

Vì thế, chỉ tạo file Java trong một thư mục có tên command hoặc commands chưa đủ để Spring nhận diện nó. Điều quan trọng là package trong khai báo Java, phạm vi quét của Spring và các annotation cần thiết.

Cần phân biệt ba khái niệm:

- **Package Java:** tên package được khai báo ở đầu file nguồn, ví dụ com.example.customercli.command.
- **Component scanning:** cơ chế Spring tìm và đăng ký các lớp được đánh dấu phù hợp trong những package được chỉ định.
- **Command discovery:** quá trình Spring Shell nhận diện các bean có khai báo command và đưa chúng vào cơ chế thực thi.

Spring Shell không tự động quét mọi thư mục trong dự án chỉ vì tên thư mục chứa từ command. Nó làm việc dựa trên các bean đã được Spring đăng ký và mô hình khai báo command của phiên bản thư viện đang sử dụng.

## 2. Đặt lớp khởi động ở package gốc của ứng dụng

Với một ứng dụng Spring Boot thông thường, cách tổ chức dễ hiểu nhất là đặt lớp có @SpringBootApplication tại package gốc, sau đó đặt command, service, repository và cấu hình trong các package con.

Ví dụ cấu trúc:

~~~text
src/main/java/
└── com/example/customercli/
    ├── CustomerCliApplication.java
    ├── command/
    │   ├── CustomerCommands.java
    │   └── ReportCommands.java
    ├── service/
    │   ├── CustomerService.java
    │   └── ReportService.java
    ├── repository/
    │   └── CustomerRepository.java
    └── config/
        └── ShellConfiguration.java
~~~

Các file khai báo package tương ứng:

~~~java
// CustomerCliApplication.java
package com.example.customercli;
~~~

~~~java
// CustomerCommands.java
package com.example.customercli.command;
~~~

~~~java
// CustomerService.java
package com.example.customercli.service;
~~~

Khi ứng dụng khởi động từ lớp CustomerCliApplication, component scanning mặc định của @SpringBootApplication bắt đầu từ package chứa lớp này và tìm trong các package con. Vì vậy, các lớp command, service và cấu hình nằm dưới com.example.customercli có thể được tìm thấy theo cơ chế mặc định.

Lớp khởi động có thể viết như sau:

~~~java
package com.example.customercli;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CustomerCliApplication {

    public static void main(String[] args) {
        SpringApplication.run(CustomerCliApplication.class, args);
    }
}
~~~

Với cách bố trí này, ứng dụng thường không cần khai báo thêm @ComponentScan. Spring Boot đã thiết lập phạm vi quét dựa trên package của lớp ứng dụng.

### 2.1. Quy tắc package cha và package con

Giả sử lớp khởi động thuộc package com.example.customercli. Những package sau nằm trong phạm vi package con:

- com.example.customercli.command
- com.example.customercli.service
- com.example.customercli.repository
- com.example.customercli.config
- com.example.customercli.command.admin

Những package sau không phải package con của com.example.customercli:

- com.example.commands
- com.example.shared.shell
- com.example.customercli_tools

Điểm cuối cần chú ý: tên package có quan hệ theo từng thành phần phân cách bằng dấu chấm. com.example.customercli_tools là một package khác, không nằm dưới com.example.customercli.

### 2.2. Tránh đặt lớp khởi động trong package quá sâu

Nếu lớp khởi động nằm trong com.example.customercli.bootstrap, phạm vi quét mặc định bắt đầu từ package bootstrap và các package con của nó. Các package sibling như com.example.customercli.command hoặc com.example.customercli.service sẽ không tự động được quét.

Do đó, nên đặt CustomerCliApplication ở package gốc com.example.customercli. Cấu trúc này cũng giúp các thành phần khác của ứng dụng có một điểm quy chiếu rõ ràng.

Không nên đặt lớp khởi động vào default package, tức là file Java không có khai báo package. Việc quét từ default package có thể khiến Spring xem xét phạm vi classpath quá rộng và tạo ra các vấn đề khó kiểm soát.

## 3. Khai báo lớp command đúng cách

Sau khi package đã nằm trong phạm vi quét, lớp command vẫn cần được khai báo theo mô hình Spring Shell mà dự án sử dụng.

Trong mô hình annotation-based, @ShellComponent đánh dấu lớp chứa command. Các method được công bố cho người dùng bằng @ShellMethod.

Ví dụ:

~~~java
package com.example.customercli.command;

import com.example.customercli.service.CustomerService;
import org.springframework.shell.standard.ShellComponent;
import org.springframework.shell.standard.ShellMethod;
import org.springframework.shell.standard.ShellOption;

@ShellComponent
public class CustomerCommands {

    private final CustomerService customerService;

    public CustomerCommands(CustomerService customerService) {
        this.customerService = customerService;
    }

    @ShellMethod(
        key = "customer find",
        value = "Tra cứu khách hàng theo mã"
    )
    public String find(
            @ShellOption(value = "--id") long customerId) {
        return customerService.findById(customerId);
    }
}
~~~

Lớp CustomerCommands nằm trong package com.example.customercli.command, là package con của package gốc. Annotation @ShellComponent giúp lớp được Spring nhận diện như một component. Constructor injection cung cấp CustomerService do Spring quản lý. Annotation @ShellMethod mô tả command mà người dùng có thể gọi.

Service có thể nằm trong package con khác:

~~~java
package com.example.customercli.service;

import org.springframework.stereotype.Service;

@Service
public class CustomerService {

    public String findById(long customerId) {
        if (customerId == 1001L) {
            return "1001 - Nguyen An";
        }

        return "Không tìm thấy khách hàng có mã " + customerId;
    }
}
~~~

Khi Spring khởi tạo context, component scanning tìm thấy cả CustomerCommands và CustomerService. Spring tạo bean và inject service vào command. Spring Shell sau đó nhận metadata command từ bean đã được đăng ký.

Một lớp có @ShellComponent nhưng không nằm trong phạm vi quét sẽ không được đăng ký theo cách này. Ngược lại, một lớp được quét và tạo bean nhưng không khai báo command theo mô hình phù hợp vẫn chưa chắc tạo ra command có thể gọi.

## 4. Khi lớp command nằm ngoài package gốc

Trong dự án lớn, command có thể được đặt trong một package dùng chung hoặc một module riêng. Khi đó, package của command có thể nằm ngoài package gốc của lớp khởi động.

Ví dụ:

~~~text
src/main/java/
├── com/example/customercli/
│   ├── CustomerCliApplication.java
│   └── service/
│       └── CustomerService.java
└── com/example/shared/shell/
    └── SharedCommands.java
~~~

Nếu ứng dụng chỉ quét com.example.customercli, lớp SharedCommands trong com.example.shared.shell sẽ không được tìm thấy theo mặc định. Ta cần mở rộng phạm vi component scanning.

### 4.1. Sử dụng scanBasePackages

Có thể khai báo nhiều package gốc bằng thuộc tính scanBasePackages của @SpringBootApplication:

~~~java
package com.example.customercli;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication(
    scanBasePackages = {
        "com.example.customercli",
        "com.example.shared.shell"
    }
)
public class CustomerCliApplication {

    public static void main(String[] args) {
        SpringApplication.run(CustomerCliApplication.class, args);
    }
}
~~~

Spring sẽ tìm component trong cả hai package và các package con của chúng. Cách này phù hợp khi package cần quét đã được xác định rõ và ít thay đổi.

Tên package truyền dưới dạng chuỗi cần được cập nhật khi refactor. Nếu viết sai tên package hoặc package không tồn tại trên runtime classpath, lớp command vẫn không được phát hiện.

### 4.2. Sử dụng scanBasePackageClasses

Một lựa chọn an toàn hơn khi refactor là dùng scanBasePackageClasses. Ta tạo một lớp hoặc interface đánh dấu nằm trong package cần quét.

Ví dụ, trong package com.example.shared.shell có một marker interface:

~~~java
package com.example.shared.shell;

public interface SharedShellPackage {
}
~~~

Lớp khởi động sử dụng các class làm mốc package:

~~~java
package com.example.customercli;

import com.example.shared.shell.SharedShellPackage;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication(
    scanBasePackageClasses = {
        CustomerCliApplication.class,
        SharedShellPackage.class
    }
)
public class CustomerCliApplication {

    public static void main(String[] args) {
        SpringApplication.run(CustomerCliApplication.class, args);
    }
}
~~~

Spring sử dụng package chứa mỗi class được truyền vào làm package gốc để quét. Cách này tránh lỗi chính tả trong tên package dạng chuỗi và giúp IDE hỗ trợ refactor tốt hơn.

Marker interface không cần chứa logic nghiệp vụ. Nhiệm vụ của nó là đại diện cho package để cấu hình scanning.

### 4.3. Sử dụng @ComponentScan trong lớp cấu hình

Trong một số cấu trúc, ta có thể khai báo phạm vi quét trực tiếp bằng @ComponentScan:

~~~java
@Configuration
@ComponentScan(basePackages = {
    "com.example.customercli",
    "com.example.shared.shell"
})
public class ComponentScanConfiguration {
}
~~~

Lớp cấu hình này phải được Spring phát hiện, chẳng hạn nằm dưới package gốc của ứng dụng hoặc được import rõ ràng. Tránh cấu hình component scanning ở nhiều nơi với phạm vi chồng lấn khó kiểm soát. Hãy chọn một cách thể hiện phạm vi quét rõ ràng để người bảo trì dễ hiểu.

### 4.4. Dùng @Import cho một số component cụ thể

Nếu chỉ có một vài lớp cần đăng ký tường minh, @Import có thể được dùng để đưa lớp vào Spring context:

~~~java
@Configuration
@Import(SharedCommands.class)
public class ShellCommandConfiguration {
}
~~~

Cách này hữu ích khi muốn đăng ký một tập hợp component cố định. Với số lượng command lớn hoặc package dùng chung, component scanning thường dễ mở rộng hơn.

Không nên đăng ký cùng một lớp bằng cả component scanning và @Import nếu không có lý do rõ ràng. Cấu hình chồng lấn có thể dẫn đến đăng ký trùng hoặc xung đột tên bean tùy cách khai báo.

## 5. Tổ chức package trong dự án nhiều module

Khi ứng dụng Spring Shell được chia thành nhiều module, việc đặt package cần đi cùng cách quản lý dependency giữa các module.

Ví dụ một dự án có cấu trúc:

~~~text
customer-platform/
├── customer-cli/
│   └── src/main/java/com/example/customercli/
│       ├── CustomerCliApplication.java
│       └── command/
│           └── CustomerCommands.java
├── customer-core/
│   └── src/main/java/com/example/customer/core/
│       └── CustomerService.java
└── shared-shell/
    └── src/main/java/com/example/shared/shell/
        └── SharedCommands.java
~~~

Module customer-cli là module ứng dụng có lớp main. Module customer-core chứa nghiệp vụ. Module shared-shell chứa các command dùng chung nếu kiến trúc thực sự cần chia sẻ chúng.

Để lớp command trong shared-shell được phát hiện, cần đồng thời thỏa mãn các điều kiện:

1. Module chứa lớp command phải được khai báo là dependency của module chạy ứng dụng.
2. Class của module đó phải có mặt trên runtime classpath.
3. Package của lớp command phải thuộc phạm vi component scanning hoặc được đăng ký tường minh.
4. Lớp command phải có annotation và dependency hợp lệ để Spring tạo bean.
5. Các dependency của command phải có thể được Spring cung cấp.

Component scanning không tự tải module còn thiếu vào ứng dụng. Nếu thư viện chưa được khai báo trong dependency của module chạy, việc thêm package vào scanBasePackages cũng không giúp tìm thấy class không có trên classpath.

Nếu nhiều module cùng cung cấp command, nên quy định rõ module nào sở hữu nhóm command nào. Tránh để nhiều module khai báo command trùng tên hoặc cùng đăng ký một lớp command qua nhiều cơ chế.

## 6. Phân biệt component scanning với các cơ chế quét khác

Thuộc tính scanBasePackages của @SpringBootApplication là cấu hình component scanning. Nó không tự động thay đổi mọi phạm vi quét của các tích hợp Spring khác.

Ví dụ, một ứng dụng có thể cần các cơ chế riêng:

- @EntityScan để chỉ định package chứa entity JPA.
- @EnableJpaRepositories để chỉ định package chứa Spring Data repository.
- Các cấu hình riêng của thư viện khác để tìm mapper, plugin hoặc tài nguyên.

Vì vậy, nếu command được phát hiện nhưng repository hoặc entity không được tìm thấy, cần kiểm tra cơ chế quét tương ứng thay vì mặc định cho rằng component scanning của ứng dụng đã cấu hình sai.

Đây là điểm quan trọng khi tổ chức ứng dụng nhiều module: mỗi loại thành phần có thể có cơ chế đăng ký và phạm vi quét riêng.

## 7. Những điều kiện khiến command không được nhận diện

Khi một command không xuất hiện trong ứng dụng, hãy kiểm tra lần lượt các lớp nguyên nhân.

| Nguyên nhân | Biểu hiện | Cách xử lý |
|---|---|---|
| Lớp command nằm ngoài package được quét | Ứng dụng chạy nhưng command không xuất hiện | Đặt lớp dưới package gốc hoặc mở rộng scanBasePackages |
| Package khai báo trong file Java không đúng | Đường dẫn thư mục nhìn có vẻ đúng nhưng scanning không tìm thấy lớp | Kiểm tra dòng package và package sau khi biên dịch |
| Thiếu @ShellComponent trong mô hình annotation-based | Lớp có thể không được đăng ký như command component | Đánh dấu lớp bằng annotation phù hợp của Spring Shell |
| Method thiếu @ShellMethod | Bean tồn tại nhưng method không được công bố như command annotation | Kiểm tra annotation và cấu hình method |
| Module chứa command không nằm trên runtime classpath | IDE có thể mở được mã nhưng ứng dụng không nạp được lớp | Kiểm tra dependency của module chạy |
| Bộ lọc component loại trừ lớp | Package nằm trong phạm vi quét nhưng bean vẫn không được tạo | Kiểm tra includeFilters, excludeFilters và useDefaultFilters |
| Điều kiện profile hoặc điều kiện cấu hình không thỏa mãn | Bean chỉ tồn tại ở một số môi trường | Kiểm tra @Profile và các điều kiện tạo bean |
| Dependency của command không tạo được | Ứng dụng có thể thất bại khi khởi động | Kiểm tra lỗi tạo bean và constructor dependency |
| Có cấu hình đăng ký chồng lấn | Có thể gặp xung đột tên bean hoặc command | Loại bỏ cấu hình đăng ký trùng và đặt tên command rõ ràng |

Một lưu ý khác là Spring cần tạo bean thành công trước khi Spring Shell có thể sử dụng nó. Vì vậy, thông báo lỗi có thể xuất hiện ở dependency của command chứ không trực tiếp nhắc đến package scanning. Hãy đọc phần nguyên nhân gốc trong stack trace, đặc biệt các lỗi liên quan đến bean creation hoặc dependency resolution.

## 8. Kiểm tra Spring đã đăng ký lớp command chưa

Không nên chỉ nhìn vào cấu trúc thư mục để kết luận command đã được phát hiện. Cần xác minh từ Spring ApplicationContext và từ khả năng sử dụng command.

### 8.1. Kiểm tra bean trong ApplicationContext

Có thể viết một bài kiểm thử Spring Boot để xác nhận lớp command đã được tạo thành bean:

~~~java
@SpringBootTest
class CommandDiscoveryTest {

    @Autowired
    private ApplicationContext applicationContext;

    @Test
    void customerCommandsShouldBeRegistered() {
        Map<String, CustomerCommands> commands =
                applicationContext.getBeansOfType(CustomerCommands.class);

        assertThat(commands).hasSize(1);
    }
}
~~~

Nếu kết quả là một bean, điều đó xác nhận Spring đã đăng ký lớp command. Nếu map rỗng, hãy kiểm tra package scanning, annotation và dependency module.

Bài kiểm thử này xác minh bean tồn tại. Nó chưa chứng minh mọi method command đã được Spring Shell đăng ký thành công. Cần kiểm tra thêm command runtime theo API của phiên bản Spring Shell mà dự án đang sử dụng.

### 8.2. Kiểm tra command từ giao diện shell

Trong chế độ tương tác, có thể sử dụng nhóm lệnh trợ giúp của Spring Shell để xem các command đã được công bố. Với command mẫu, cần xác nhận command customer find xuất hiện và có mô tả tương ứng.

Sau đó thực hiện một lần gọi thử:

~~~text
shell:> customer find --id 1001
1001 - Nguyen An
~~~

Nếu bean đã tồn tại nhưng command không có trong danh sách trợ giúp, hãy kiểm tra annotation command, cấu hình Spring Shell và cách đăng ký command của phiên bản đang sử dụng.

### 8.3. Kiểm tra khi chạy test và khi đóng gói

Một command có thể hoạt động trong môi trường IDE nhưng không hoạt động sau khi đóng gói nếu module chứa command bị thiếu khỏi runtime dependency hoặc cấu hình chạy khác với cấu hình kiểm thử.

Nên kiểm tra ít nhất ba tình huống:

- Khởi động ứng dụng từ lớp main trong môi trường phát triển.
- Chạy kiểm thử tích hợp Spring context.
- Chạy gói ứng dụng được đóng gói bằng đúng cấu hình triển khai dự kiến.

Nếu command nằm trong thư viện dùng chung, hãy xác minh dependency được đóng gói đúng và package vẫn nằm trong phạm vi quét khi chạy ứng dụng thực tế.

## 9. Quy ước tổ chức package nên áp dụng

Một cấu trúc package tốt cần giúp người phát triển tìm thấy command, hiểu quan hệ phụ thuộc và mở rộng ứng dụng mà không phải sửa nhiều cấu hình.

Có thể áp dụng các quy ước sau:

**Đặt lớp main ở package gốc.** Đây là cách đơn giản để phạm vi quét mặc định bao phủ các thành phần của ứng dụng.

**Tách command khỏi service.** Package command chứa lớp nhận đầu vào và trình bày kết quả. Package service chứa logic nghiệp vụ. Điều này giúp command không trở thành nơi chứa toàn bộ xử lý ứng dụng.

**Nhóm command theo lĩnh vực nghiệp vụ.** Khi số lượng command tăng, có thể chia thành customer, report, user hoặc admin bên dưới package command. Các package con vẫn nằm trong phạm vi quét mặc định nếu lớp main đặt đúng vị trí.

**Dùng package chung cho component thực sự dùng chung.** Chỉ đưa command sang module shared khi có nhu cầu tái sử dụng rõ ràng. Khi đó, cấu hình dependency và phạm vi quét cần được thể hiện minh bạch.

**Hạn chế quét quá rộng.** Quét toàn bộ package của nhiều thư viện có thể tạo bean ngoài ý muốn, tăng nguy cơ xung đột và khiến thời gian khởi động khó dự đoán. Hãy chọn các package gốc của ứng dụng và các module cần thiết.

**Không dùng tên thư mục để thay cho khai báo package.** Khi di chuyển file hoặc đổi package, cần kiểm tra cả package declaration và cấu hình component scanning.

**Không đăng ký trùng một command.** Dùng một cơ chế đăng ký rõ ràng cho mỗi lớp command, tránh quét chồng lấn và import lặp lại.

## 10. Ví dụ hoàn chỉnh về cấu trúc và cách nhận diện

Giả sử ứng dụng Customer CLI có các thành phần sau:

~~~text
src/main/java/
└── com/example/customercli/
    ├── CustomerCliApplication.java
    ├── command/
    │   └── CustomerCommands.java
    └── service/
        └── CustomerService.java
~~~

Lớp khởi động:

~~~java
package com.example.customercli;

@SpringBootApplication
public class CustomerCliApplication {

    public static void main(String[] args) {
        SpringApplication.run(CustomerCliApplication.class, args);
    }
}
~~~

Service:

~~~java
package com.example.customercli.service;

@Service
public class CustomerService {

    public String findById(long id) {
        return id == 1001L
                ? "1001 - Nguyen An"
                : "Không tìm thấy khách hàng có mã " + id;
    }
}
~~~

Command:

~~~java
package com.example.customercli.command;

@ShellComponent
public class CustomerCommands {

    private final CustomerService customerService;

    public CustomerCommands(CustomerService customerService) {
        this.customerService = customerService;
    }

    @ShellMethod(
        key = "customer find",
        value = "Tra cứu khách hàng theo mã"
    )
    public String find(@ShellOption("--id") long id) {
        return customerService.findById(id);
    }
}
~~~

Cả ba lớp đều thuộc package gốc hoặc package con của com.example.customercli. Vì vậy, Spring Boot có thể tìm thấy các component theo cơ chế mặc định. Spring IoC tạo CustomerService và CustomerCommands, sau đó inject service vào command. Spring Shell nhận metadata của method find và công bố command customer find.

Người dùng có thể gọi:

~~~text
shell:> customer find --id 1001
1001 - Nguyen An

shell:> customer find --id 2002
Không tìm thấy khách hàng có mã 2002
~~~

Nếu sau này CustomerCommands được chuyển sang com.example.shared.shell, ta phải cập nhật phạm vi component scanning hoặc đăng ký bean tường minh. Việc chỉ di chuyển file vào một thư mục khác trong IDE sẽ không tự làm Spring quét package mới.

Ví dụ minh họa sử dụng mô hình command khai báo bằng annotation. Nếu dự án sử dụng API đăng ký command trực tiếp hoặc mô hình Command/CommandRegistration của phiên bản Spring Shell khác, cần tuân theo cơ chế tạo bean và đăng ký command của API đó. Nguyên tắc chung vẫn là: thành phần cần hoạt động phải được tạo và đăng ký trong application context hoặc command runtime theo đúng cơ chế mà ứng dụng lựa chọn.

## 11. Checklist khi thêm một lớp command mới

Trước khi kết luận một command đã sẵn sàng, hãy kiểm tra:

- [ ] Dòng package trong file Java khớp với cấu trúc package dự kiến.
- [ ] Package nằm dưới package gốc của lớp main hoặc đã được khai báo trong phạm vi scanning.
- [ ] Module chứa lớp command có trong runtime classpath.
- [ ] Lớp command dùng annotation hoặc cơ chế đăng ký phù hợp với phiên bản Spring Shell.
- [ ] Các method command có metadata khai báo hợp lệ.
- [ ] Constructor dependency đều có bean tương ứng.
- [ ] Không có bộ lọc hoặc profile loại trừ component ngoài ý muốn.
- [ ] ApplicationContext chứa bean command.
- [ ] Command xuất hiện trong trợ giúp của shell hoặc command registry tương ứng.
- [ ] Command hoạt động khi chạy gói ứng dụng thực tế.

## 12. Kết luận

Để Spring Shell nhận diện lớp khai báo lệnh theo mô hình annotation, lớp command phải được Spring đăng ký thành bean và có cấu hình command phù hợp. Cách tổ chức đơn giản nhất là đặt lớp khởi động Spring Boot tại package gốc, sau đó đặt command, service, repository và cấu hình trong các package con.

Khi command nằm ngoài package gốc, cần mở rộng component scanning bằng scanBasePackages, scanBasePackageClasses, @ComponentScan hoặc đăng ký tường minh bằng @Import. Với dự án nhiều module, còn phải bảo đảm module chứa command có mặt trên runtime classpath.

Hiểu rõ mối liên hệ giữa package Java, component scanning, bean registration và command discovery giúp chẩn đoán lỗi nhanh hơn, tránh cấu hình quét quá rộng và giữ cho ứng dụng CLI có cấu trúc dễ bảo trì khi phát triển thêm command.

