# Từ cách sắp xếp mã đến mô hình module trong bộ nhớ

Trong một ứng dụng Spring Boot, ta thường bắt đầu tổ chức mã bằng package. Các package gom những lớp có liên quan vào cùng một khu vực, giúp dự án dễ tìm kiếm và bảo trì hơn. Nhưng một cây package đẹp chưa chắc đã tạo thành kiến trúc mô-đun tốt: một package có thể gọi sâu vào phần triển khai của package khác, nhiều package có thể phụ thuộc vòng tròn, và ranh giới nghiệp vụ có thể chỉ tồn tại trong suy nghĩ của nhóm phát triển.

Spring Modulith giúp biến cách tổ chức package thành một mô hình kiến trúc có thể phân tích và kiểm chứng. Với module Spring Modulith, mục tiêu là nhận diện ranh giới nghiệp vụ, xác định API công khai, nhìn thấy quan hệ phụ thuộc giữa các package và đặt quy tắc để giữ cho ứng dụng modular monolith không bị mất tính mô-đun khi phát triển.

Điểm chuyển quan trọng là: package vẫn là cấu trúc vật lý trong mã nguồn, còn Spring Modulith đọc cấu trúc đó để xây dựng một mô hình module trong bộ nhớ. Mô hình này cho ta biết ứng dụng được chia thành những module nào, mỗi module công khai phần nào và module nào đang phụ thuộc vào module nào.

## 1. Package là cách sắp xếp mã; module là một ranh giới kiến trúc

Java package trước hết là một cơ chế đặt tên và tổ chức lớp. Ta có thể tạo package orders, catalog hay customers, nhưng chỉ tên gọi không ngăn được mã trong orders truy cập trực tiếp vào một lớp triển khai nội bộ của catalog.

Ví dụ, ứng dụng bán hàng có cấu trúc:

~~~text
com.acme.shop
├── ShopApplication.java
├── catalog
│   ├── CatalogQuery.java
│   └── internal
│       └── JpaCatalogRepository.java
├── orders
│   ├── OrderManagement.java
│   └── internal
│       └── OrderRepository.java
└── customers
    ├── CustomerProfile.java
    └── internal
        └── CustomerRepository.java
~~~

Ở đây, com.acme.shop là package gốc của ứng dụng, nơi đặt lớp khởi động Spring Boot. Các package con trực tiếp catalog, orders và customers là những ứng viên module theo quy ước mặc định của Spring Modulith.

Mỗi module đại diện cho một phần chức năng của ứng dụng. Chẳng hạn:

- catalog chịu trách nhiệm về danh mục sản phẩm.
- orders chịu trách nhiệm về đơn hàng.
- customers chịu trách nhiệm về hồ sơ khách hàng.

Ranh giới module có ý nghĩa kiến trúc: nó giúp ta trả lời phần nào thuộc trách nhiệm của module, phần nào module khác được phép sử dụng và những phụ thuộc nào cần được kiểm soát.

Spring Modulith không tự hiểu ý nghĩa nghiệp vụ chỉ từ tên package. Nhóm phát triển vẫn phải chọn cách phân chia chức năng hợp lý. Framework dùng cấu trúc package và các khai báo bổ sung để nhận diện, biểu diễn rồi kiểm tra ranh giới mà nhóm đã thiết kế.

## 2. ApplicationModules chuyển cây package thành mô hình trong bộ nhớ

Spring Modulith cung cấp lớp ApplicationModules làm điểm bắt đầu để khám phá mô hình module của ứng dụng. Ta truyền vào lớp khởi động Spring Boot:

~~~java
ApplicationModules modules = ApplicationModules.of(ShopApplication.class);
~~~

Lệnh này yêu cầu Spring Modulith phân tích ứng dụng bắt đầu từ package chứa ShopApplication. Theo quy ước mặc định, các package con trực tiếp của package gốc được nhận diện là các application module.

Kết quả là một đối tượng ApplicationModules đại diện cho tập hợp module của ứng dụng. Bên trong mô hình đó, mỗi module được biểu diễn bằng thông tin tương ứng, chẳng hạn tên module, package gốc, các giao diện được công khai và những quan hệ phụ thuộc mà framework phát hiện.

Có thể hình dung quá trình như sau:

~~~mermaid
flowchart TD
    A["Lớp khởi động ShopApplication"] --> B["Package gốc com.acme.shop"]
    B --> C["Khám phá các package con trực tiếp"]
    C --> D["Module catalog"]
    C --> E["Module orders"]
    C --> F["Module customers"]
    D --> G["Mô hình ApplicationModules trong bộ nhớ"]
    E --> G
    F --> G
~~~

Điều này tạo ra một bước chuyển từ cấu trúc thư mục sang cấu trúc kiến trúc:

1. Package cho biết lớp đang nằm ở đâu.
2. Quy ước nhận diện module cho biết nhóm package nào tạo thành một module.
3. Khai báo giao diện module cho biết phần nào được phép sử dụng từ bên ngoài.
4. Phân tích phụ thuộc cho biết module nào đang tham chiếu đến module nào.

Mô hình trong bộ nhớ là kết quả phân tích kiến trúc. Nó không phải một cơ chế nạp module động, không tạo classloader riêng cho từng module và cũng không biến mỗi module thành một tiến trình độc lập. Ứng dụng vẫn có thể chạy như một ứng dụng Spring Boot thống nhất.

Ta có thể dùng mô hình này trong kiểm thử, kiểm tra kiến trúc hoặc các tác vụ hỗ trợ phát triển. Nhờ đó, kiến trúc module trở thành thứ có thể biểu diễn và kiểm tra bằng mã thay vì chỉ nằm trong tài liệu thiết kế.

## 3. Mỗi module có phần công khai và phần triển khai nội bộ

Nhận diện được module mới chỉ là bước đầu. Một ranh giới hữu ích còn phải xác định module khác được phép truy cập vào đâu.

Theo quy ước mặc định của Spring Modulith, package gốc của module tạo thành API công khai của module. Các package con nằm bên dưới được xem là phần nội bộ, trừ khi chúng được khai báo rõ ràng là một named interface.

Ví dụ:

~~~text
com.acme.shop
├── catalog
│   ├── CatalogQuery.java
│   ├── spi
│   │   └── CatalogLookup.java
│   └── internal
│       ├── JpaCatalogRepository.java
│       └── CatalogQueryImpl.java
└── orders
    └── PlaceOrder.java
~~~

Trong cấu trúc này:

- com.acme.shop.catalog là package gốc của module catalog.
- CatalogQuery nằm ngay trong package gốc, nên thuộc API mặc định của module.
- catalog.internal là package nội bộ, không dành cho module khác truy cập trực tiếp.
- catalog.spi là package con; nếu muốn module khác sử dụng nó, ta cần công khai package này có chủ đích.

Spring Modulith hỗ trợ việc đó bằng annotation @NamedInterface. Ta có thể đặt annotation trong file package-info.java của package muốn công khai:

~~~java
@org.springframework.modulith.NamedInterface("spi")
package com.acme.shop.catalog.spi;
~~~

Khai báo này đánh dấu package catalog.spi là một named interface có tên spi. Khi mô hình module được xây dựng, Spring Modulith nhận biết đây là một phần API được công khai của module catalog.

Một named interface hữu ích khi module cần công khai nhiều nhóm hợp đồng với mục đích khác nhau. Ví dụ, module có thể cung cấp API chính cho nghiệp vụ và một giao diện SPI cho các thành phần tích hợp. Việc đặt tên giúp người đọc nhận biết mục đích của từng bề mặt công khai.

Hãy chú ý sự khác biệt giữa hai trường hợp:

~~~text
orders -> catalog.spi       Hợp lệ nếu catalog.spi được công khai
orders -> catalog.internal  Vi phạm ranh giới module
~~~

Nếu module orders cần tra cứu sản phẩm, nó nên phụ thuộc vào hợp đồng được module catalog công khai. Nó không nên tạo phụ thuộc trực tiếp vào repository hay lớp triển khai lưu trữ dữ liệu của catalog. Nhờ vậy, module catalog có thể thay đổi cách lưu trữ hoặc tổ chức nội bộ mà không buộc orders phải thay đổi theo.

Named interface không tự sinh ra API, không chuyển lớp thành public trong Java và cũng không thay thế kiểm soát truy cập của ngôn ngữ. Nó cung cấp thông tin kiến trúc để Spring Modulith hiểu package nào là bề mặt giao tiếp được phép dùng giữa các module.

## 4. Từ các tham chiếu lớp đến đồ thị phụ thuộc module

Sau khi xác định module và API công khai, Spring Modulith có thể phân tích các tham chiếu giữa các lớp để hình thành quan hệ phụ thuộc giữa module.

Giả sử:

- PlaceOrder trong module orders cần CatalogLookup do module catalog công khai.
- Một dịch vụ của orders cũng cần CustomerProfile từ module customers.

Mô hình phụ thuộc có thể được biểu diễn như sau:

~~~mermaid
flowchart LR
    Orders["orders"] --> Catalog["catalog"]
    Orders --> Customers["customers"]
~~~

Mũi tên đi từ module sử dụng sang module mà nó phụ thuộc. Vì vậy, orders -> catalog có nghĩa là module orders phụ thuộc vào module catalog, không phải ngược lại.

Đồ thị này giúp nhóm phát triển nhìn thấy cấu trúc liên kết giữa các phần chức năng. Khi số lượng module tăng lên, nó có thể bộc lộ những vấn đề khó nhận ra nếu chỉ đọc từng package:

- Một module phụ thuộc vào quá nhiều module khác.
- Hai module phụ thuộc lẫn nhau, tạo thành chu trình.
- Một module truy cập trực tiếp vào package nội bộ của module khác.
- Một thay đổi trong API có thể ảnh hưởng đến nhiều module phụ thuộc.

Cần hiểu đúng phạm vi của phân tích này: quan hệ phụ thuộc phản ánh các tham chiếu mà Spring Modulith phát hiện trong cấu trúc mã. Nó không phải bản ghi toàn bộ lời gọi hàm xảy ra khi ứng dụng đang chạy, không mô tả trình tự xử lý của một nghiệp vụ và cũng không tự suy luận mọi tương tác ẩn qua reflection, tên lớp dạng chuỗi hoặc hệ thống bên ngoài.

Do đó, đồ thị phụ thuộc là một mô hình kiến trúc tĩnh rất hữu ích, nhưng vẫn cần được đọc cùng thiết kế nghiệp vụ và cách ứng dụng thực sự vận hành.

## 5. Dùng mô hình để kiểm chứng quy tắc kiến trúc

Nếu mô hình chỉ giúp quan sát mà không thể kiểm tra, nhóm vẫn có nguy cơ vô tình phá vỡ ranh giới trong những lần thay đổi sau. Spring Modulith cho phép kiểm chứng mô hình bằng phương thức verify().

Ví dụ, ta có thể viết một bài kiểm thử kiến trúc:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    @Test
    void verifiesModuleStructure() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

Khi kiểm thử chạy, Spring Modulith phân tích các module và kiểm tra những quy tắc kiến trúc mặc định, trong đó có các vấn đề như:

- Module truy cập vào package nội bộ của module khác.
- Các module tạo thành chu trình phụ thuộc.

Nếu phát hiện vi phạm, bước kiểm chứng sẽ báo lỗi để nhóm xử lý. Ta có thể đưa bài kiểm thử này vào quy trình build để thay đổi làm hỏng ranh giới module được phát hiện sớm.

Với những hệ thống cần kiểm soát chặt hơn, nhóm có thể khai báo các phụ thuộc được phép bằng metadata module, chẳng hạn thuộc tính allowedDependencies trong @ApplicationModule. Khi đó, nhóm có thể diễn đạt chính sách như: module orders chỉ được phụ thuộc vào những module đã được cho phép. Việc khai báo chính sách giúp giới hạn đồ thị phụ thuộc theo kiến trúc mong muốn, thay vì chỉ kiểm tra một số lỗi cấu trúc phổ biến.

Quy tắc chỉ có giá trị khi được thực thi thường xuyên. Vì vậy, hãy đặt kiểm thử kiến trúc ở vị trí phù hợp trong bộ kiểm thử của dự án và bảo đảm nó chạy trong CI.

## 6. Đọc mô hình theo một trình tự nhất quán

Khi tiếp cận một ứng dụng chưa quen thuộc, ta có thể đọc mô hình Spring Modulith theo trình tự sau:

1. **Tìm package gốc.** Xác định lớp @SpringBootApplication và package chứa lớp đó.
2. **Nhận diện module.** Liệt kê các package con trực tiếp và xem chúng có phản ánh các nhóm chức năng nghiệp vụ hợp lý không.
3. **Xác định API công khai.** Kiểm tra lớp nằm trong package gốc của module và các package được đánh dấu @NamedInterface.
4. **Xem phụ thuộc.** Đọc quan hệ giữa các module, chú ý chiều của mũi tên và những phụ thuộc không mong muốn.
5. **Kiểm chứng quy tắc.** Chạy ApplicationModules.of(...).verify() để phát hiện vi phạm ranh giới và chu trình phụ thuộc.

Trình tự này cũng cho thấy vai trò của từng khái niệm:

~~~mermaid
flowchart TD
    A["Cây package trong mã nguồn"] --> B["Nhận diện application module"]
    B --> C["Xác định API và phần nội bộ"]
    C --> D["Phân tích phụ thuộc"]
    D --> E["Mô hình module trong bộ nhớ"]
    E --> F["Kiểm chứng kiến trúc"]
~~~

Mỗi bước bổ sung một lớp thông tin. Chỉ nhìn cây package, ta biết mã được sắp xếp ra sao. Khi có mô hình module, ta biết ranh giới chức năng. Khi có named interface, ta biết hợp đồng được công khai. Khi có đồ thị phụ thuộc và kiểm chứng, ta có thể đánh giá liệu mã hiện tại có tuân thủ kiến trúc đã chọn hay không.

## 7. Những điều không nên nhầm lẫn

**Module Spring Modulith không đồng nghĩa với Maven hoặc Gradle module.** Một ứng dụng có thể được chia thành nhiều Spring Modulith module nhưng vẫn được biên dịch và triển khai như một đơn vị duy nhất. Việc chia thành module build riêng là một quyết định cấu trúc dự án khác.

**Package có tên nghiệp vụ chưa chắc đã là ranh giới tốt.** Framework nhận diện module từ cấu trúc package, nhưng chất lượng của ranh giới phụ thuộc vào cách nhóm phân chia trách nhiệm và thiết kế hợp đồng giữa các phần chức năng.

**Public trong Java không đồng nghĩa với API module được công khai.** Một lớp Java có thể khai báo public nhưng vẫn nằm trong package nội bộ. Quy tắc module của Spring Modulith giúp kiểm tra cách các module sử dụng những package đó.

**Đồ thị phụ thuộc không phải đồ thị luồng nghiệp vụ.** Nó cho biết module nào tham chiếu đến module nào theo phân tích mã. Nó không mô tả đầy đủ chuỗi sự kiện, giao dịch hay trình tự gọi hàm trong một ca sử dụng.

**Có mô hình không có nghĩa là kiến trúc tự được bảo vệ.** Nhóm cần duy trì các quy tắc, chạy kiểm thử và xử lý vi phạm khi mã thay đổi. Giá trị của Spring Modulith nằm ở việc biến ý định kiến trúc thành điều có thể kiểm tra lặp lại.

## Kết luận

Spring Modulith bắt đầu từ cấu trúc package của ứng dụng Spring Boot, nhận diện các module theo quy ước, xác định bề mặt API công khai, phân tích quan hệ phụ thuộc và đưa những thông tin đó vào mô hình ApplicationModules trong bộ nhớ. Từ mô hình này, nhóm có thể kiểm tra các ranh giới module bằng verify() và bổ sung quy tắc phụ thuộc phù hợp với kiến trúc.

Khi hiểu được bước chuyển từ package sang mô hình module, ta sẽ nhìn ứng dụng modular monolith như một tập hợp các phần chức năng có trách nhiệm, giao diện và quan hệ phụ thuộc rõ ràng. Đó là nền tảng để tổ chức mã theo nghiệp vụ và giữ cho kiến trúc tiếp tục có tính mô-đun khi hệ thống lớn dần.
