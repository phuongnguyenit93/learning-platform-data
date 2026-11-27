# Khi nào một package nên trở thành module?

Một package nên trở thành module khi nó đại diện cho một năng lực nghiệp vụ có trách nhiệm rõ ràng, có thể tự quản lý phần triển khai bên trong và có một hợp đồng đủ ổn định để các phần khác của ứng dụng sử dụng. Ranh giới đó cần giúp nhóm hiểu ai sở hữu quy tắc nào, dữ liệu nào và những phụ thuộc nào được phép tồn tại.

Trong Spring Modulith, module là một ranh giới kiến trúc bên trong một ứng dụng Spring Boot. Ứng dụng vẫn có thể được triển khai như một khối duy nhất, nhưng mã nguồn được chia thành các module nghiệp vụ có API và quy tắc phụ thuộc rõ ràng. Vì vậy, quyết định tạo module không nên dựa riêng vào số lượng class hay độ dài của package. Hãy dựa vào trách nhiệm nghiệp vụ, mức độ gắn kết và cách các phần của hệ thống cần cộng tác.

## 1. Package và module là hai khái niệm khác nhau

Package là cơ chế tổ chức mã nguồn của Java. Nó giúp đặt tên, nhóm class và kiểm soát một phần khả năng truy cập. Bản thân việc tạo package mới chưa tạo ra một ranh giới kiến trúc có ý nghĩa.

Module là một đơn vị kiến trúc có:

- **Trách nhiệm riêng:** giải quyết một nhóm vấn đề nghiệp vụ có liên quan.
- **Quyền sở hữu:** chịu trách nhiệm với quy tắc và dữ liệu thuộc phạm vi của nó.
- **Giao diện công khai:** công bố những thao tác hoặc kiểu dữ liệu mà module khác được phép sử dụng.
- **Phần triển khai nội bộ:** giữ chi tiết thay đổi thường xuyên ở bên trong.
- **Quan hệ phụ thuộc có chủ đích:** biết module nào được phép gọi module nào.

Một module thường bao gồm package gốc và các package con. Không phải package con nào cũng là module độc lập. Chẳng hạn, `order.internal` có thể chỉ là nơi tổ chức phần triển khai nội bộ của module `order`.

Điểm quan trọng là ranh giới module phải diễn tả được một quyết định thiết kế. Nếu đổi tên hoặc di chuyển package mà không làm thay đổi cách hệ thống phân chia trách nhiệm, package đó có thể chỉ đang phục vụ việc sắp xếp file.

## 2. Cách Spring Modulith nhận diện module

Theo quy ước mặc định, Spring Modulith xem các package con trực tiếp của package gốc ứng dụng là các application module. Ví dụ:

```text
com.acme.shop
├── ShopApplication.java
├── order
│   ├── OrderManagement.java
│   ├── OrderPlaced.java
│   └── internal
│       ├── OrderRepository.java
│       └── OrderService.java
├── inventory
│   ├── InventoryManagement.java
│   └── internal
│       ├── StockRepository.java
│       └── StockReservationService.java
└── payment
    ├── PaymentManagement.java
    └── internal
        └── PaymentService.java
```

Trong cấu trúc này, `order`, `inventory` và `payment` là ba module. Package `internal` là package con thuộc module tương ứng, không tự động trở thành một module nghiệp vụ mới.

Mặc định, package gốc của module là nơi công bố API. Các package con được xem là nội bộ, trừ khi một package con được khai báo rõ ràng là named interface. Điều đó tạo ra một quy ước dễ hiểu:

- Module khác có thể sử dụng kiểu và thao tác công khai trong `com.acme.shop.order`.
- Module khác không nên phụ thuộc vào `com.acme.shop.order.internal`.
- Nếu cần công bố một giao diện ở package con, hãy khai báo nó có chủ đích bằng named interface.

Có thể đánh dấu module và giới hạn các module mà nó được phép phụ thuộc bằng `@ApplicationModule` trong `package-info.java`:

```java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "inventory"
)
package com.acme.shop.order;
```

Ví dụ trên diễn tả rằng module `order` được phép phụ thuộc vào module `inventory`. Tên module trong cấu hình phải khớp với tên package module mà Spring Modulith nhận diện.

Nếu muốn công bố một giao diện có tên ở package con, có thể khai báo `@NamedInterface`:

```java
@org.springframework.modulith.NamedInterface("spi")
package com.acme.shop.inventory.spi;
```

Khi đó, module khác có thể khai báo phụ thuộc cụ thể vào giao diện `spi` của `inventory`, ví dụ `inventory::spi`. Named interface nên được dùng khi có nhu cầu thực sự cần công bố một phần API nằm ngoài package gốc; không nên đánh dấu mọi package con là công khai.

## 3. Sáu dấu hiệu cho thấy một package nên trở thành module

### 3.1. Package đại diện cho một năng lực nghiệp vụ có tên gọi rõ ràng

Hãy thử mô tả package bằng một câu bắt đầu với “chịu trách nhiệm về”. Nếu có thể nói package chịu trách nhiệm về việc đặt hàng, quản lý tồn kho, xử lý thanh toán hoặc quản lý vận chuyển, đó là một tín hiệu tốt.

Một năng lực nghiệp vụ thường chứa nhiều hành vi liên quan. Ví dụ, module `order` có thể chịu trách nhiệm:

- Tiếp nhận yêu cầu tạo đơn.
- Kiểm tra trạng thái và quy tắc của đơn hàng.
- Tính toán tổng tiền ở cấp đơn hàng theo chính sách thuộc phạm vi của nó.
- Quản lý vòng đời đơn hàng.
- Phát sự kiện khi đơn hàng chuyển sang một trạng thái có ý nghĩa.

Ngược lại, package `utils`, `common` hoặc `helpers` thường không mô tả một năng lực nghiệp vụ. Chúng dễ trở thành nơi chứa những thứ chưa biết đặt ở đâu. Một package như vậy chỉ nên được nâng thành module khi nó có trách nhiệm ổn định, phạm vi rõ và hợp đồng riêng; tên gọi chung chung không đủ để chứng minh điều đó.

### 3.2. Các thành phần bên trong có mức độ gắn kết cao

Các class nên nằm cùng module khi chúng thường xuyên cộng tác để hoàn thành cùng một quy trình nghiệp vụ hoặc cùng bảo vệ một nhóm quy tắc.

Ví dụ, `OrderService`, `OrderRepository`, `OrderPolicy` và `OrderState` có thể thuộc cùng module nếu chúng cùng thực hiện và bảo vệ vòng đời đơn hàng. Chúng có thể thay đổi cùng nhau khi quy tắc đặt hàng thay đổi.

Hãy quan sát cả hai chiều:

- **Gắn kết bên trong (cohesion):** các thành phần trong package có cùng phục vụ một trách nhiệm không?
- **Liên kết bên ngoài (coupling):** package có phải biết quá nhiều chi tiết của các package khác để hoạt động không?

Một module tốt thường có mức gắn kết bên trong cao và số lượng phụ thuộc bên ngoài vừa đủ. Nếu các class trong package hiếm khi làm việc cùng nhau, thuộc các quy trình khác nhau và thay đổi vì những lý do khác nhau, có thể package đang gom nhiều trách nhiệm vào một chỗ.

### 3.3. Module có thể sở hữu quy tắc và dữ liệu của mình

Ranh giới trở nên có ý nghĩa khi có thể chỉ ra module nào là nơi có thẩm quyền đối với một nhóm quy tắc và dữ liệu.

Ví dụ:

| Phạm vi | Module có thể sở hữu | Module khác nên yêu cầu điều gì? |
| --- | --- | --- |
| Đơn hàng | Trạng thái đơn, quy tắc chuyển trạng thái, thông tin dòng hàng của đơn | Tạo đơn, hủy đơn hoặc truy vấn thông tin được công bố |
| Tồn kho | Số lượng khả dụng, quy tắc giữ hàng, giải phóng hàng | Yêu cầu giữ hàng hoặc giải phóng hàng |
| Thanh toán | Giao dịch, kết quả thanh toán, quy tắc hoàn tiền | Khởi tạo thanh toán hoặc yêu cầu hoàn tiền |

Module sở hữu dữ liệu nên kiểm soát cách dữ liệu đó được thay đổi. Module khác không nên bỏ qua API để gọi thẳng repository, cập nhật entity hoặc dựa vào bảng cơ sở dữ liệu nội bộ của module sở hữu.

Nếu hai nhóm chức năng luôn phải đọc và ghi trực tiếp cùng một nhóm dữ liệu để hoàn thành một quy trình, hãy xem lại ranh giới. Có thể chúng thực sự thuộc cùng một module, hoặc cần thiết kế lại hợp đồng giữa chúng. Việc chỉ chia package trong khi quyền sở hữu dữ liệu vẫn bị chia sẻ sẽ tạo ra một ranh giới hình thức.

### 3.4. Có thể xác định một API công khai nhỏ và dễ hiểu

Module cần cung cấp cách sử dụng mà không buộc module gọi phải hiểu cấu trúc nội bộ. API tốt thể hiện ý định nghiệp vụ, chẳng hạn:

```java
package com.acme.shop.inventory;

public interface InventoryManagement {

    ReservationResult reserve(ReserveStockCommand command);

    void release(ReleaseStockCommand command);
}
```

Module `order` chỉ cần biết nó có thể yêu cầu giữ hàng hoặc giải phóng hàng. Nó không cần biết module `inventory` dùng repository nào, lưu dữ liệu ra sao hoặc chia service nội bộ thế nào.

API nên được thiết kế theo nhu cầu của bên sử dụng và ngôn ngữ nghiệp vụ. Tránh công bố repository, entity persistence, implementation class hoặc hàng loạt getter chỉ vì chúng đang tồn tại. Khi chi tiết nội bộ được đưa vào API, thay đổi nhỏ bên trong cũng có thể buộc nhiều module khác sửa theo.

Nếu chưa thể xác định bên ngoài cần gọi thao tác nào, kiểu dữ liệu nào và module sẽ bảo vệ quy tắc gì, có thể package chưa có ranh giới đủ rõ để trở thành module.

### 3.5. Các phụ thuộc có thể diễn tả thành hướng đi rõ ràng

Một module độc lập tương đối vẫn có thể phụ thuộc module khác. Điều cần tránh là phụ thuộc vòng và việc truy cập xuyên qua các phần triển khai nội bộ.

Ví dụ, quy trình đặt hàng có thể yêu cầu module tồn kho giữ hàng:

```text
order ───────► inventory
   │
   └─────────► phát OrderPlaced
                    │
                    ▼
                  payment
```

Trong một thiết kế phù hợp, `order` gọi API công khai của `inventory` khi cần kết quả giữ hàng ngay trong quy trình. Module `payment` có thể lắng nghe sự kiện `OrderPlaced` nếu việc khởi tạo thanh toán là phản ứng với một sự kiện nghiệp vụ và không cần nằm trong lời gọi đồng bộ của `order`.

Hãy cảnh giác với các dấu hiệu sau:

- `order` gọi `inventory.internal.StockRepository`.
- `inventory` gọi ngược vào service nội bộ của `order`.
- Hai module cần import entity nội bộ của nhau.
- Một thay đổi nhỏ trong một module khiến nhiều module khác phải sửa cùng lúc.

Các dấu hiệu đó cho thấy hợp đồng hoặc hướng phụ thuộc chưa được thiết kế tốt. Nếu quan hệ phụ thuộc vòng là cần thiết để hệ thống hoạt động, hãy xem lại trách nhiệm của hai module trước khi thêm ngoại lệ.

### 3.6. Ranh giới giúp thay đổi và kiểm thử có phạm vi rõ hơn

Một module có giá trị khi người phát triển có thể thay đổi một quy tắc nghiệp vụ mà ít làm ảnh hưởng đến phần còn lại. Họ có thể kiểm thử hành vi của module thông qua API công khai, đồng thời kiểm tra các quy tắc nội bộ mà không phải khởi động hoặc hiểu toàn bộ ứng dụng.

Hãy xem lịch sử thay đổi hoặc các tình huống phát triển thực tế:

- Những class nào thường được sửa cùng nhau?
- Khi thay đổi quy tắc tồn kho, có phải sửa code đặt hàng và thanh toán không?
- Có thể kiểm thử quy tắc của module bằng dữ liệu và API của chính nó không?
- Một người hoặc một nhóm có thể hiểu và chịu trách nhiệm về module mà không cần nắm toàn bộ chi tiết của module khác không?

Nếu ranh giới package giúp thu hẹp phạm vi thay đổi và làm rõ trách nhiệm, việc nâng nó thành module có lợi ích thực tế. Nếu việc tách chỉ tạo thêm nhiều lời gọi qua lại, nhiều DTO trung gian và nhiều bước phối hợp mà không làm giảm phụ thuộc, hãy xem lại quyết định.

## 4. Khi nào chưa nên tách package thành module?

Không phải mọi package đều cần trở thành module. Một package thường nên tiếp tục là package nội bộ khi có một hoặc nhiều tình huống sau:

1. **Chỉ là nhóm kỹ thuật:** package gom controller, mapper, validator hoặc cấu hình dùng chung nhưng không sở hữu một năng lực nghiệp vụ riêng.
2. **Quá nhỏ và chưa có trách nhiệm độc lập:** package chỉ bọc một class hoặc chuyển tiếp lời gọi sang nơi khác, không tạo ra hợp đồng hay quyền sở hữu mới.
3. **Hai nhóm chức năng luôn thay đổi cùng nhau:** chúng cùng bảo vệ một quy trình và không có ranh giới nghiệp vụ ổn định để tách.
4. **Không thể xác định quyền sở hữu dữ liệu:** nhiều package cùng sửa trực tiếp một nhóm dữ liệu và không có bên nào chịu trách nhiệm cuối cùng.
5. **Phụ thuộc chéo quá nhiều:** mỗi bên cần gọi nhiều chi tiết nội bộ của bên kia để hoàn thành tác vụ.
6. **API chỉ phơi bày chi tiết triển khai:** bên sử dụng phải biết repository, entity hoặc cấu trúc service nội bộ để làm việc.

Đặc biệt, không nên chia ứng dụng thành các module ngang theo tầng kỹ thuật như `controller`, `service`, `repository`. Cách chia đó khiến một thay đổi nghiệp vụ thường phải đi qua nhiều module kỹ thuật, trong khi không có module nào sở hữu trọn vẹn hành vi nghiệp vụ.

Ví dụ, cấu trúc sau thường không tạo ra các module nghiệp vụ tốt:

```text
com.acme.shop
├── controller
├── service
├── repository
└── entity
```

Một cấu trúc theo năng lực nghiệp vụ thường dễ hiểu hơn:

```text
com.acme.shop
├── order
│   ├── OrderManagement.java
│   └── internal
├── inventory
│   ├── InventoryManagement.java
│   └── internal
└── payment
    ├── PaymentManagement.java
    └── internal
```

Trong cấu trúc thứ hai, mỗi module có thể tự tổ chức controller, service, repository và entity bên trong phạm vi của mình khi cần.

## 5. Ví dụ quyết định ranh giới: Order và Inventory

Giả sử ứng dụng bán hàng ban đầu có package `order` chứa cả xử lý đơn hàng và số lượng tồn kho. Khi hệ thống phát triển, nhóm nhận thấy quy tắc giữ hàng có vòng đời riêng: một mặt hàng có thể được giữ tạm thời, hết hạn giữ hàng, giải phóng hoặc xác nhận xuất kho. Các quy tắc này được nhiều quy trình khác sử dụng, không chỉ quy trình tạo đơn.

Đây là cơ sở tốt để cân nhắc tách `inventory` thành module riêng:

- **Trách nhiệm khác nhau:** `order` quản lý vòng đời đơn hàng; `inventory` quản lý lượng hàng khả dụng và việc giữ hàng.
- **Quy tắc riêng:** thời hạn giữ hàng và tính khả dụng thuộc `inventory`; điều kiện hủy hoặc xác nhận đơn thuộc `order`.
- **API có ý nghĩa:** `order` yêu cầu `inventory` giữ hàng bằng một lệnh nghiệp vụ.
- **Dữ liệu có chủ sở hữu:** chỉ `inventory` thay đổi trạng thái giữ hàng và số lượng khả dụng.
- **Phụ thuộc một chiều:** `order` sử dụng API của `inventory`; `inventory` không cần truy cập vào cấu trúc nội bộ của `order`.

Một luồng đơn giản có thể là:

1. Khách hàng gửi yêu cầu tạo đơn.
2. Module `order` kiểm tra dữ liệu và quy tắc tạo đơn.
3. Module `order` gọi API công khai của `inventory` để yêu cầu giữ hàng.
4. Nếu giữ hàng thành công, module `order` lưu đơn và công bố sự kiện `OrderPlaced`.
5. Module `payment` nhận sự kiện và bắt đầu quy trình thanh toán theo chính sách của nó.

Nếu bước giữ hàng cần trả kết quả ngay để quyết định có tạo đơn hay không, một lời gọi API đồng bộ là hợp lý. Nếu thanh toán chỉ cần phản ứng sau khi đơn được tạo, sự kiện có thể giảm sự phụ thuộc trực tiếp. Không nên biến mọi lời gọi giữa module thành event; hãy chọn cơ chế theo yêu cầu về kết quả, thứ tự xử lý và tính nhất quán của nghiệp vụ.

Nếu việc tách `inventory` khiến hai bên liên tục gọi ngược cho nhau, cùng sửa một entity hoặc cần chia sẻ transaction nội bộ theo cách không thể diễn đạt thành hợp đồng rõ ràng, cần đánh giá lại ranh giới. Có thể việc tách đang quá sớm, hoặc quy trình nghiệp vụ cần được thiết kế lại.

## 6. Quy trình thực tế để quyết định và tạo module

Có thể áp dụng các bước sau cho một package đang phát triển:

### Bước 1: Mô tả trách nhiệm bằng ngôn ngữ nghiệp vụ

Viết một câu ngắn mô tả package chịu trách nhiệm về điều gì. Dùng động từ và danh từ nghiệp vụ cụ thể. Nếu chỉ mô tả được bằng tên tầng kỹ thuật như “xử lý service” hoặc “lưu repository”, hãy tìm lại năng lực nghiệp vụ mà các class đang phục vụ.

### Bước 2: Gom các thành phần có lý do thay đổi giống nhau

Nhìn vào use case, quy tắc, dữ liệu và lịch sử thay đổi. Những thành phần cùng thực hiện một trách nhiệm và cùng bảo vệ các quy tắc liên quan nên được đặt gần nhau. Không gom class chỉ vì chúng có cùng hậu tố như `Service` hoặc `Repository`.

### Bước 3: Xác định dữ liệu và quy tắc thuộc quyền sở hữu

Ghi rõ module nào được phép tạo, cập nhật và xác nhận dữ liệu. Những module khác cần dùng API hoặc sự kiện đã công bố để yêu cầu hành vi. Nếu không xác định được chủ sở hữu, chưa nên chốt ranh giới.

### Bước 4: Thiết kế API trước khi phơi bày triển khai

Liệt kê các thao tác mà module khác thực sự cần. Tạo các command, result hoặc event thể hiện ý định nghiệp vụ. Giữ repository, entity persistence và implementation trong package nội bộ nếu bên ngoài không có lý do chính đáng để sử dụng chúng.

### Bước 5: Vẽ hướng phụ thuộc

Vẽ các mũi tên từ module gọi sang module được sử dụng. Kiểm tra xem có vòng lặp hay không và mỗi phụ thuộc có đi qua API công khai không. Với những giao diện bổ sung ở package con, cân nhắc named interface và khai báo rõ module nào được phép phụ thuộc vào chúng.

### Bước 6: Để Spring Modulith kiểm chứng cấu trúc

Có thể thêm một bài kiểm thử kiến trúc để phát hiện phụ thuộc vòng hoặc truy cập trái phép vào package nội bộ:

```java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    @Test
    void verifiesApplicationModuleStructure() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
```

Phương thức `verify()` kiểm tra cấu trúc module mà Spring Modulith nhận diện theo cấu hình và quy ước của ứng dụng. Bài kiểm thử này nên chạy cùng bộ kiểm thử tự động để thay đổi về sau không vô tình tạo phụ thuộc sai. Nó hỗ trợ kiểm tra ranh giới kiến trúc; nó không thể tự quyết định hai nhóm chức năng có thực sự thuộc cùng một năng lực nghiệp vụ hay không.

### Bước 7: Đánh giá lại bằng thay đổi thực tế

Sau khi tách, quan sát các thay đổi tiếp theo. Nếu một thay đổi trong module thường xuyên buộc phải sửa chi tiết nội bộ của module khác, hãy xem lại API và quyền sở hữu. Ranh giới module có thể được điều chỉnh khi hiểu biết về nghiệp vụ và cách hệ thống vận hành tốt hơn.

## 7. Checklist trước khi nâng một package thành module

Trước khi quyết định, hãy trả lời các câu hỏi sau:

| Câu hỏi | Dấu hiệu của một ranh giới tốt |
| --- | --- |
| Package đại diện cho năng lực nghiệp vụ nào? | Có thể mô tả bằng một trách nhiệm cụ thể, dễ hiểu |
| Các thành phần bên trong có gắn kết không? | Cùng phục vụ một nhóm use case hoặc quy tắc |
| Module sở hữu dữ liệu và quy tắc nào? | Có thể xác định rõ bên chịu trách nhiệm thay đổi |
| Bên ngoài cần API nào? | Hợp đồng nhỏ, hướng nghiệp vụ, không lộ chi tiết triển khai |
| Phụ thuộc đi theo hướng nào? | Có hướng rõ ràng, không cần truy cập package nội bộ |
| Có thể kiểm thử độc lập ở mức hợp lý không? | Có thể kiểm tra hành vi qua API và quy tắc của module |
| Việc tách có giảm phạm vi thay đổi không? | Thay đổi thường tập trung hơn, ít ảnh hưởng lan truyền |

Không cần mọi module phải có cùng kích thước hoặc số lượng class. Một module có thể nhỏ nếu nó đại diện cho một năng lực độc lập với hợp đồng rõ ràng. Một module cũng có thể lớn nếu các thành phần bên trong vẫn gắn kết và thay đổi cùng nhau. Điều cần đạt là ranh giới có ý nghĩa và giúp quản lý sự phụ thuộc.

## 8. Kết luận

Hãy nâng một package thành module khi package đó có thể sở hữu một năng lực nghiệp vụ, bảo vệ quy tắc và dữ liệu của mình, cung cấp API rõ ràng và duy trì các phụ thuộc có hướng. Ranh giới tốt làm cho phần bên trong có thể thay đổi với ít ảnh hưởng đến phần còn lại của ứng dụng.

Với Spring Modulith, có thể biểu diễn ranh giới đó bằng package module, API ở package gốc, package nội bộ, named interface khi thật sự cần và các quy tắc phụ thuộc được kiểm chứng bằng `ApplicationModules.verify()`. Hãy bắt đầu từ trách nhiệm nghiệp vụ và quyền sở hữu; cấu trúc package là cách thể hiện quyết định kiến trúc đó trong mã nguồn.
