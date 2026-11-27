# Đánh đổi giữa mô-đun hóa, tốc độ thay đổi và độ phức tạp

Mô-đun hóa giúp một ứng dụng Spring Boot phát triển lâu dài bằng cách chia hệ thống thành những phần có trách nhiệm và ranh giới rõ ràng. Tuy nhiên, mỗi ranh giới đều có chi phí: nhóm phải thiết kế API, quản lý phụ thuộc, phối hợp khi thay đổi hợp đồng và kiểm chứng kiến trúc. Vì vậy, thêm nhiều mô-đun không tự động làm ứng dụng dễ bảo trì hoặc giúp nhóm phát triển nhanh hơn.

Trong phạm vi **SPRING_MODULITH_MODULE_MODEL**, ta dùng mô hình mô-đun của Spring Modulith để nhận diện ranh giới nghiệp vụ, API công khai và phụ thuộc giữa các package trong một ứng dụng Spring Boot. Các công cụ như `ApplicationModules`, `Named Interface`, quy tắc phụ thuộc và kiểm chứng kiến trúc giúp biến những ranh giới đó thành quy ước có thể kiểm tra. Mục tiêu là chọn mức mô-đun hóa làm giảm chi phí thay đổi tổng thể, thay vì chỉ làm cấu trúc thư mục trông có vẻ ngăn nắp.

## 1. Ba yếu tố luôn tác động lẫn nhau

### Mô-đun hóa tạo ranh giới và tạo thêm trách nhiệm

Một mô-đun tốt gom những phần cùng phục vụ một năng lực nghiệp vụ, đồng thời hạn chế việc mô-đun khác biết chi tiết triển khai bên trong. Ví dụ, mô-đun `orders` sở hữu quy tắc tạo và quản lý đơn hàng; mô-đun `inventory` sở hữu quy tắc giữ và giải phóng tồn kho.

Ranh giới có ích khi nó làm rõ:

- Phần nghiệp vụ nào chịu trách nhiệm cho một quy tắc hoặc dữ liệu.
- Những kiểu và thao tác nào mô-đun khác được phép sử dụng.
- Những phụ thuộc nào hợp lệ và chiều phụ thuộc được tổ chức ra sao.
- Thay đổi nào có thể thực hiện bên trong một mô-đun mà không buộc các mô-đun khác sửa theo.

Đổi lại, nhóm phải duy trì hợp đồng công khai, xử lý thay đổi hợp đồng có chủ đích, viết kiểm thử cho ranh giới và giải quyết các trường hợp một nghiệp vụ đi qua nhiều mô-đun. Nếu ranh giới không phản ánh một trách nhiệm thực tế, chi phí này trở thành thủ tục thừa.

### Tốc độ thay đổi phụ thuộc vào phạm vi ảnh hưởng

Tốc độ không chỉ là số dòng code được sửa trong một lần làm việc. Một thay đổi nhanh ở một package nhưng buộc nhiều package khác cập nhật có thể làm toàn nhóm chậm lại. Ngược lại, một mô-đun có API ổn định cho phép nhóm thay đổi triển khai nội bộ mà ít ảnh hưởng đến phần còn lại của ứng dụng.

Mô-đun hóa thường cải thiện tốc độ khi:

- Phần lớn thay đổi liên quan đến một năng lực nghiệp vụ có thể nằm trong một mô-đun.
- API công khai thay đổi ít hơn phần triển khai bên trong.
- Nhóm có thể kiểm thử mô-đun riêng và phát hiện vi phạm phụ thuộc sớm.
- Các nhóm hoặc người phụ trách khác nhau có thể làm việc song song mà không liên tục sửa cùng một vùng code.

Nó có thể làm giảm tốc độ khi một thay đổi thường xuyên phải đi qua quá nhiều API, khi hợp đồng công khai thay đổi liên tục, hoặc khi một quy trình nghiệp vụ bị chia cắt qua những mô-đun không có ranh giới rõ ràng.

### Độ phức tạp không biến mất, nó chuyển vị trí

Gọi trực tiếp một service khác thường dễ hiểu và dễ lần theo luồng xử lý. Nhưng nếu gọi trực tiếp vào repository hoặc lớp nội bộ của mô-đun khác, mã nguồn sẽ phụ thuộc vào chi tiết triển khai của mô-đun đó.

Sự kiện nghiệp vụ có thể giảm phụ thuộc trực tiếp: mô-đun phát sự kiện mà không cần biết tất cả bên nhận. Tuy nhiên, nếu xử lý bất đồng bộ, hệ thống phải quan tâm thêm đến thời điểm xử lý, giao dịch, thử lại, tính lặp an toàn, khả năng quan sát và trạng thái nhất quán trong khoảng chờ. Sự kiện không miễn phí hơn lời gọi trực tiếp; nó phù hợp với loại phụ thuộc khác.

## 2. Chọn kích thước mô-đun phù hợp

Hai thái cực đều có vấn đề:

| Cách chia | Lợi ích thường thấy | Chi phí và rủi ro |
|---|---|---|
| Ít mô-đun, mỗi mô-đun lớn | Ít hợp đồng phải quản lý, luồng gọi đơn giản, dễ thực hiện thay đổi xuyên suốt một vùng lớn | Trách nhiệm dễ phình to, phụ thuộc nội bộ khó nhận ra, nhiều thay đổi không liên quan cùng tác động vào một mô-đun |
| Nhiều mô-đun nhỏ | Phạm vi trách nhiệm có thể rõ, dễ cô lập một số quy tắc và kiểm thử | Nhiều API và phụ thuộc cần quản lý, luồng gọi dài, thay đổi đơn giản cũng có thể phải sửa nhiều mô-đun |

Không có số lượng lớp hay package cố định để xác định một mô-đun có kích thước đúng. Hãy nhóm các phần có **mức gắn kết nghiệp vụ cao** và hạn chế phụ thuộc giữa các nhóm. Những phần thường thay đổi cùng nhau, cùng thực thi một tập quy tắc và cùng chịu trách nhiệm về một dữ liệu thường có lý do để ở gần nhau.

Một mô-đun có thể đang quá lớn nếu nhiều năng lực nghiệp vụ ít liên quan cùng phụ thuộc vào nó, các thay đổi độc lập liên tục gây xung đột, hoặc một nhóm không thể hiểu và kiểm thử phần mình phụ trách mà không khởi động gần như toàn bộ hệ thống. Một mô-đun có thể đang quá nhỏ nếu hầu hết thay đổi đều phải sửa đồng thời nó và mô-đun bên cạnh, API giữa chúng chỉ chuyển tiếp dữ liệu, hoặc các mô-đun không có trách nhiệm nghiệp vụ độc lập.

Chỉ nên tách một mô-đun khi có lý do vận hành hoặc nghiệp vụ cụ thể, chẳng hạn trách nhiệm và quyền sở hữu khác nhau, vòng đời thay đổi khác nhau, quy tắc cần bảo vệ riêng, hoặc một hợp đồng ổn định có thể được xác định. Không nên tách chỉ vì một package có nhiều lớp.

## 3. Ranh giới package trong Spring Modulith

Spring Modulith mô hình hóa application module dựa trên cấu trúc package của ứng dụng. Theo quy ước mặc định, các package con trực tiếp của package gốc ứng dụng được nhận diện là các mô-đun. Package gốc của một mô-đun là bề mặt API cơ bản; các package con thường được xem là phần triển khai nội bộ, trừ khi được công khai rõ ràng qua named interface.

Ví dụ, một ứng dụng bán hàng có thể tổ chức như sau:

```text
com.acme.shop
├── ShopApplication.java
├── orders
│   ├── package-info.java
│   ├── OrderManagement.java
│   └── internal
│       ├── OrderRepository.java
│       └── OrderPolicy.java
└── inventory
    ├── package-info.java
    ├── api
    │   ├── package-info.java
    │   └── InventoryOperations.java
    └── internal
        └── InventoryRepository.java
```

`orders` và `inventory` là hai mô-đun ở cùng cấp. Lớp `OrderManagement` có thể là điểm vào công khai của `orders`; repository và policy nằm trong package `internal` là chi tiết mà mô-đun khác không nên sử dụng trực tiếp. Mô-đun `inventory` chủ động công khai hợp đồng `InventoryOperations` qua named interface `api`.

Khai báo named interface trong `inventory/api/package-info.java`:

```java
@NamedInterface("api")
package com.acme.shop.inventory.api;

import org.springframework.modulith.NamedInterface;
```

Mô-đun `orders` có thể giới hạn phụ thuộc vào named interface đó trong `orders/package-info.java`:

```java
@ApplicationModule(allowedDependencies = "inventory::api")
package com.acme.shop.orders;

import org.springframework.modulith.ApplicationModule;
```

Khai báo này diễn đạt một quyết định kiến trúc: `orders` được phép dùng hợp đồng `api` của `inventory`. Nó không nên truy cập trực tiếp `InventoryRepository` hoặc các lớp nội bộ khác. Nhờ vậy, `inventory` có thể thay đổi cách lưu trữ hay tính toán tồn kho mà không buộc `orders` biết về cách triển khai đó.

Named interface chỉ nên được tạo khi có một nhóm hợp đồng cần công khai riêng. Nếu mọi package nhỏ đều trở thành named interface, nhóm sẽ phải quản lý quá nhiều bề mặt API và làm mất ý nghĩa của việc đóng gói.

## 4. Chọn lời gọi trực tiếp hay sự kiện nghiệp vụ

Giả sử quy trình tạo đơn hàng cần tương tác với tồn kho. Có hai kiểu giao tiếp phổ biến, với đặc tính khác nhau.

**Lời gọi trực tiếp qua API công khai** phù hợp khi bên gọi cần kết quả ngay để quyết định bước tiếp theo. Ví dụ, `orders` gọi `InventoryOperations.reserve(...)` để biết yêu cầu giữ hàng có được chấp nhận hay không. Luồng xử lý dễ theo dõi và có thể nằm trong cùng một ranh giới giao dịch nếu thiết kế ứng dụng cho phép. Đổi lại, `orders` có phụ thuộc trực tiếp vào hợp đồng của `inventory` và cần xử lý trường hợp mô-đun đó từ chối hoặc phát sinh lỗi.

**Sự kiện nghiệp vụ** phù hợp khi bên phát không cần biết tất cả bên nhận hoặc khi tác vụ có thể diễn ra sau. Ví dụ, sau khi đơn hàng được xác nhận, ứng dụng có thể phát `OrderConfirmed` để các mô-đun thông báo hoặc phân tích xử lý. Mô-đun `orders` không cần gọi từng mô-đun đó. Nếu người nhận chạy bất đồng bộ, cần thiết kế rõ cách xử lý lỗi, thử lại, chống xử lý trùng và theo dõi sự kiện chưa hoàn tất.

Không nên chuyển một quyết định cần kết quả tức thời thành sự kiện bất đồng bộ chỉ để giảm số mũi tên phụ thuộc. Chẳng hạn, nếu việc xác nhận đơn hàng bắt buộc phải biết hàng đã được giữ hay chưa, quy trình phải có cơ chế điều phối và xử lý nhất quán phù hợp. Việc phát sự kiện đơn thuần không giải quyết được yêu cầu đó.

## 5. Kiểm chứng ranh giới thay vì chỉ dựa vào quy ước

Ranh giới chỉ có giá trị khi được duy trì trong code. Spring Modulith cung cấp `ApplicationModules` để khám phá mô hình mô-đun và kiểm tra các quy tắc kiến trúc. Có thể thêm kiểm tra vào bộ kiểm thử của ứng dụng:

```java
import org.springframework.modulith.core.ApplicationModules;
import org.junit.jupiter.api.Test;

class ModularityTests {

    @Test
    void verifiesApplicationModuleStructure() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
```

Kiểm tra này giúp phát hiện những vấn đề như chu trình phụ thuộc giữa các mô-đun hoặc truy cập vượt qua ranh giới API được mô hình cho phép. Nó biến quy tắc kiến trúc thành một phần có thể chạy lại trong quá trình phát triển và tích hợp.

Kiểm chứng cấu trúc không thay thế kiểm thử nghiệp vụ. Một mô-đun có thể tuân thủ hoàn toàn quy tắc package nhưng vẫn có API khó dùng, quy trình phối hợp sai hoặc sở hữu dữ liệu không rõ. Vì thế, nên kết hợp kiểm tra kiến trúc với kiểm thử hành vi của mô-đun và kiểm thử tích hợp cho các luồng nghiệp vụ đi qua nhiều mô-đun.

## 6. Quy trình ra quyết định khi thiết kế hoặc tái cấu trúc

Khi cân nhắc tách, gộp hoặc thay đổi ranh giới, hãy đi theo các bước sau:

1. **Bắt đầu từ năng lực nghiệp vụ.** Xác định phần nào chịu trách nhiệm cho một quy tắc, dữ liệu và quyết định nghiệp vụ. Tránh chia theo tầng kỹ thuật như `controller`, `service`, `repository` nếu cách chia đó khiến một năng lực bị rải khắp ứng dụng.
2. **Xem các thay đổi thực tế.** Quan sát những phần thường được sửa cùng nhau, những nơi hay phát sinh xung đột và các thay đổi thường buộc nhiều nhóm phối hợp. Đây là tín hiệu để đánh giá lại ranh giới.
3. **Xác định hợp đồng tối thiểu.** Chọn những thao tác và kiểu dữ liệu mà mô-đun khác thực sự cần. Giữ repository, entity nội bộ và quy tắc triển khai ở bên trong khi chúng không phải là một phần hợp đồng.
4. **Chọn cơ chế giao tiếp theo yêu cầu nghiệp vụ.** Dùng lời gọi API khi cần kết quả trực tiếp; dùng sự kiện khi muốn thông báo một sự kiện và cho phép bên nhận xử lý độc lập. Đánh giá giao dịch và nhất quán dữ liệu trước khi chọn xử lý bất đồng bộ.
5. **Mã hóa quy tắc và kiểm thử.** Dùng `ApplicationModules` để kiểm chứng mô hình, khai báo `allowedDependencies` hoặc `Named Interface` khi cần giới hạn API, rồi kiểm thử các hành vi quan trọng ở từng mô-đun.
6. **Đánh giá lại sau các thay đổi lớn.** Nếu một hợp đồng liên tục thay đổi cùng với bên sử dụng, có thể hai phần đang bị chia tách quá sớm. Nếu một mô-đun tích tụ nhiều trách nhiệm và nhiều nhóm phải sửa cùng một vùng, có thể cần tách nó theo năng lực nghiệp vụ.

Một số tín hiệu hữu ích để theo dõi là số mô-đun bị tác động bởi một thay đổi nghiệp vụ, tần suất hợp đồng công khai phải sửa, số phụ thuộc vòng, số lần phải truy cập package nội bộ và thời gian cần để kiểm thử một mô-đun. Không nên tối ưu một chỉ số riêng lẻ: giảm số phụ thuộc nhưng làm quy trình nghiệp vụ khó hiểu hơn cũng không phải là cải thiện.

## 7. Những ngộ nhận cần tránh

- **“Càng nhiều mô-đun càng tốt.”** Số lượng mô-đun không đo được chất lượng ranh giới. Mô-đun nhỏ nhưng luôn thay đổi cùng nhau có thể chỉ làm tăng chi phí phối hợp.
- **“Cùng một ứng dụng thì có thể dùng mọi package.”** Cùng chạy trong một tiến trình không có nghĩa là các chi tiết nội bộ nên trở thành API. Phụ thuộc trực tiếp vào package nội bộ làm giảm khả năng thay đổi độc lập.
- **“Dùng sự kiện là đã giảm độ phức tạp.”** Sự kiện giảm sự phụ thuộc trực tiếp giữa bên phát và bên nhận, nhưng có thể thêm độ phức tạp về giao dịch, thời điểm xử lý, thử lại và nhất quán.
- **“Kiểm tra kiến trúc là đủ.”** `ApplicationModules.verify()` giúp bảo vệ cấu trúc phụ thuộc; nó không chứng minh mô hình nghiệp vụ hoặc API đã được thiết kế đúng.
- **“Tách mô-đun là bước chuẩn bị để chuyển sang microservices.”** Một modular monolith có thể là kiến trúc đích lâu dài. Chỉ cân nhắc tách tiến trình khi có nhu cầu độc lập về triển khai, mở rộng, độ tin cậy hoặc quyền sở hữu đủ rõ để bù chi phí vận hành phân tán.

## Kết luận

Mức mô-đun hóa phù hợp là mức làm cho thay đổi nghiệp vụ thường ngày có phạm vi rõ, hợp đồng đủ ổn định và phụ thuộc có thể kiểm chứng, trong khi nhóm vẫn hiểu được luồng xử lý tổng thể. Spring Modulith hỗ trợ thực thi những quyết định đó ngay trong một ứng dụng Spring Boot. Hãy bắt đầu từ trách nhiệm nghiệp vụ và mẫu thay đổi thực tế, sau đó dùng `ApplicationModules`, `Named Interface` và quy tắc phụ thuộc để bảo vệ các ranh giới có ích. Khi chi phí duy trì một ranh giới lớn hơn lợi ích nó mang lại, hãy xem xét đơn giản hóa hoặc gộp lại.
