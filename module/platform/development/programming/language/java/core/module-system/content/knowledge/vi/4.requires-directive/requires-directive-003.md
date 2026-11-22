# `requires transitive` và phụ thuộc được truyền tiếp

Trong Java Platform Module System (JPMS), mỗi module khai báo các module mà nó cần đọc bằng directive `requires` trong `module-info.java`. Mặc định, một module chỉ nhận quyền đọc trực tiếp những module mà nó khai báo. Directive `requires transitive` mở rộng khả năng đọc đó cho các module ở phía sau: module nào yêu cầu module hiện tại cũng có thể đọc module được khai báo là phụ thuộc truyền tiếp.

Cơ chế này đặc biệt hữu ích khi API công khai của một module sử dụng kiểu dữ liệu được cung cấp bởi module khác. Người dùng API có thể làm việc với các kiểu đó mà không phải khai báo lại cùng một phụ thuộc trong mọi module tiêu thụ.

## 1. Phân biệt `requires` và `requires transitive`

Giả sử có ba module:

- `com.example.model` cung cấp kiểu dữ liệu `Customer`.
- `com.example.service.api` cung cấp API dịch vụ và dùng `Customer` trong chữ ký phương thức công khai.
- `com.example.app` sử dụng API dịch vụ.

Khi module dịch vụ khai báo:

    requires com.example.model;

thì `com.example.service.api` đọc được `com.example.model`. Tuy nhiên, một module khác chỉ khai báo `requires com.example.service.api;` sẽ không tự động có quyền đọc `com.example.model`.

Nếu module dịch vụ khai báo:

    requires transitive com.example.model;

thì module nào đọc `com.example.service.api` cũng được mở rộng khả năng đọc sang `com.example.model`. Vì vậy, ứng dụng có thể sử dụng các kiểu công khai của module model thông qua API dịch vụ mà không cần khai báo một directive `requires com.example.model;` riêng.

| Directive | Module khai báo đọc phụ thuộc | Module yêu cầu module hiện tại |
|---|---|---|
| `requires B;` | Đọc được B | Không tự động đọc B qua module hiện tại |
| `requires transitive B;` | Đọc được B | Được truyền khả năng đọc B |

Có thể biểu diễn quan hệ chính như sau:

    com.example.app
          |
          | requires
          v
    com.example.service.api
          |
          | requires transitive
          v
    com.example.model

Ứng dụng đọc module dịch vụ; vì module dịch vụ công bố phụ thuộc model theo dạng transitive, ứng dụng cũng đọc được module model.

## 2. Ví dụ ba module

Cấu trúc thư mục:

    src/
    ├── com.example.model/
    │   ├── module-info.java
    │   └── com/example/model/Customer.java
    ├── com.example.service.api/
    │   ├── module-info.java
    │   └── com/example/service/api/CustomerService.java
    └── com.example.app/
        ├── module-info.java
        └── com/example/app/Main.java

### Module model

File `src/com.example.model/module-info.java`:

    module com.example.model {
        exports com.example.model;
    }

Module model xuất package `com.example.model` để module đọc nó có thể truy cập các kiểu công khai trong package.

File `src/com.example.model/com/example/model/Customer.java`:

    package com.example.model;

    public record Customer(long id, String name) {
    }

### Module service API

File `src/com.example.service.api/module-info.java`:

    module com.example.service.api {
        requires transitive com.example.model;
        exports com.example.service.api;
    }

Module này đọc model và truyền khả năng đọc model cho các module yêu cầu nó.

File `src/com.example.service.api/com/example/service/api/CustomerService.java`:

    package com.example.service.api;

    import com.example.model.Customer;
    import java.util.Optional;

    public interface CustomerService {
        Optional<Customer> findById(long id);
    }

Kiểu `Customer` của module model xuất hiện trong chữ ký phương thức công khai `findById`. Đây là lý do phù hợp để service API khai báo `requires transitive`: module tiêu thụ API cũng cần đọc được kiểu `Customer` để sử dụng đầy đủ chữ ký đó.

### Module ứng dụng

File `src/com.example.app/module-info.java`:

    module com.example.app {
        requires com.example.service.api;
    }

Ứng dụng chỉ cần yêu cầu module service API. Không cần khai báo thêm `requires com.example.model;` để tham chiếu kiểu `Customer` được xuất bởi module model.

File `src/com.example.app/com/example/app/Main.java`:

    package com.example.app;

    import com.example.model.Customer;
    import com.example.service.api.CustomerService;

    public class Main {
        public static void printFirstCustomer(CustomerService service) {
            service.findById(1L)
                    .ifPresent(customer -> System.out.println(customer.name()));
        }
    }

Trong ví dụ này, ứng dụng import được cả `CustomerService` lẫn `Customer`. Quyền đọc module model được truyền từ module service API thông qua directive `requires transitive`.

## 3. Biên dịch ví dụ

Đặt ba module theo đúng cấu trúc thư mục ở trên, sau đó chạy lệnh từ thư mục chứa `src`:

    javac --module-source-path src -d out -m com.example.model,com.example.service.api,com.example.app

Lệnh biên dịch tìm source của ba module theo tên thư mục, biên dịch chúng và đặt kết quả vào `out`.

Có thể kiểm tra descriptor của module dịch vụ:

    jar --describe-module --file out/com.example.service.api/module-info.class

Trong thực tế, `jar --describe-module` thường được dùng với file JAR của module. Với cấu trúc output dạng exploded module, có thể kiểm tra bằng:

    java --module-path out --describe-module com.example.service.api

Kết quả mô tả module sẽ cho thấy `requires transitive com.example.model` cùng package được xuất.

## 4. Điều gì xảy ra nếu đổi thành `requires` thông thường?

Nếu sửa module dịch vụ thành:

    module com.example.service.api {
        requires com.example.model;
        exports com.example.service.api;
    }

thì service API vẫn đọc được `Customer` và vẫn biên dịch được chữ ký `Optional<Customer>`.

Nhưng module ứng dụng chỉ khai báo:

    module com.example.app {
        requires com.example.service.api;
    }

sẽ không đọc được module model. Khi `Main` import `com.example.model.Customer`, trình biên dịch báo package thuộc module `com.example.model` không được đọc bởi module `com.example.app`.

Để phiên bản dùng `requires` thông thường hoạt động, ứng dụng phải khai báo trực tiếp:

    module com.example.app {
        requires com.example.service.api;
        requires com.example.model;
    }

Điểm khác biệt nằm ở đồ thị readability của JPMS: `requires` tạo phụ thuộc trực tiếp cho module khai báo; `requires transitive` còn truyền khả năng đọc phụ thuộc đó đến các module yêu cầu module khai báo.

## 5. Readability và exports là hai việc khác nhau

Đây là điểm dễ nhầm nhất khi học `requires transitive`.

- **Readability** trả lời: module hiện tại có quyền đọc các kiểu của module kia hay không?
- **Exports** trả lời: module được đọc có cho phép truy cập package cụ thể hay không?

`requires transitive` truyền khả năng đọc module. Nó không tự xuất package, không mở package để reflection và không bỏ qua ranh giới đóng gói của module đích.

Trong ví dụ, `com.example.model` vẫn phải có:

    exports com.example.model;

Nếu bỏ dòng `exports` này, ứng dụng có thể đọc module model nhưng vẫn không thể truy cập kiểu công khai `Customer` trong package chưa được xuất. Muốn sử dụng một package, module tiêu thụ phải có readability tới module chứa package và package đó phải được xuất phù hợp.

## 6. Khi nào nên dùng `requires transitive`?

Hãy cân nhắc directive này khi một module công bố API mà kiểu từ module phụ thuộc xuất hiện trong các vị trí công khai, chẳng hạn:

- Kiểu tham số hoặc kiểu trả về của phương thức public.
- Kiểu generic trong chữ ký API, ví dụ `Optional<Customer>` hoặc `List<Customer>`.
- Kiểu cha hoặc interface mà người dùng API cần nhìn thấy để sử dụng hoặc triển khai hợp đồng.

Nếu module chỉ dùng thư viện trong phần triển khai nội bộ và không làm lộ kiểu của thư viện đó qua API công khai, `requires` thông thường thường là lựa chọn phù hợp hơn.

Không nên chuyển mọi phụ thuộc thành `requires transitive` theo thói quen. Mỗi directive transitive làm tăng số module mà người tiêu thụ có thể đọc và mở rộng bề mặt phụ thuộc công khai của module. Chỉ truyền tiếp những phụ thuộc thực sự là một phần của hợp đồng API.

## 7. Những điều `requires transitive` không có nghĩa

1. **Không phải là xuất lại package.** Package vẫn do module sở hữu quyết định bằng `exports`.
2. **Không phải là tự động thêm thư viện vào mọi cấu hình build.** JPMS điều khiển module readability trên module path; Gradle hoặc Maven vẫn quản lý việc tìm và cung cấp artifact.
3. **Không có nghĩa module tiêu thụ bắt buộc phải gọi API của module phụ thuộc.** Nó chỉ được cấp khả năng đọc theo đồ thị module.
4. **Không thay thế hoàn toàn khai báo phụ thuộc trực tiếp.** Nếu ứng dụng phụ thuộc trực tiếp vào model như một phần thiết kế của chính nó, khai báo `requires com.example.model;` vẫn có thể làm rõ hợp đồng của ứng dụng.
5. **Không biến một package không được xuất thành package công khai.** Readability và exports phải cùng thỏa mãn.

## 8. So sánh với dependency transitivity của Gradle/Maven

Tên gọi có vẻ giống nhau nhưng hai khái niệm nằm ở hai tầng khác nhau:

- Dependency transitivity của Gradle/Maven nói về cách công cụ build phân giải và đưa các artifact phụ thuộc vào cấu hình hoặc classpath/module path.
- `requires transitive` là chỉ thị trong `module-info.java`, xác định quan hệ readability giữa các named module theo JPMS.

Một thư viện có thể được Gradle/Maven phân giải thành công nhưng mã nguồn module vẫn không truy cập được package nếu module descriptor không khai báo quan hệ phù hợp. Ngược lại, directive trong `module-info.java` cũng không tự tải artifact còn thiếu về máy. Cần cấu hình build và module descriptor nhất quán.

## Ghi nhớ

Khi thấy:

    module A {
        requires transitive B;
    }

hãy hiểu rằng A đọc B, đồng thời module nào yêu cầu A cũng được truyền khả năng đọc B. Dùng `requires transitive` khi B là một phần của API mà A công bố. Sau đó kiểm tra thêm rằng B đã xuất package cần thiết bằng `exports`.

Câu hỏi kiểm tra nhanh: nếu `com.example.app` chỉ khai báo `requires com.example.service.api;`, tại sao nó vẫn import được `Customer` từ `com.example.model`? Vì `com.example.service.api` khai báo `requires transitive com.example.model;`, nên readability tới model được truyền cho ứng dụng.