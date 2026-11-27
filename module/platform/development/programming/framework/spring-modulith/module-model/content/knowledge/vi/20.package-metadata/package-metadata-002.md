# `@PackageInfo` cung cấp metadata rõ ràng

Trong Java, `package-info.java` là nơi đặt tài liệu và annotation ở cấp package. Spring Modulith sử dụng metadata package để hiểu cấu trúc module, chẳng hạn package nào là module, package nào là named interface và package nào được đánh dấu rõ ràng trong mô hình kiến trúc.

Một package có thể chưa chứa class Java thông thường nhưng vẫn cần có tài liệu hoặc metadata riêng. `@PackageInfo` là marker của Spring Modulith dành cho `package-info.java` trong trường hợp đó. Nó giúp package metadata được giữ lại và nhận diện như một phần của mô hình, thay vì chỉ tồn tại dưới dạng một file tài liệu không có type tương ứng.

Bài học này giải thích vai trò của `package-info.java`, cách sử dụng `@PackageInfo`, cách phối hợp marker này với `@ApplicationModule` và `@NamedInterface`, cùng những giới hạn cần nhớ khi thiết kế metadata package.

## Mục tiêu

Sau bài học, bạn có thể:

- Giải thích vì sao Java có `package-info.java` và metadata package được lưu ở đâu.
- Dùng `@PackageInfo` để đánh dấu package chỉ có metadata hoặc tài liệu.
- Phân biệt `@PackageInfo` với `@ApplicationModule` và `@NamedInterface`.
- Tổ chức metadata module tại đúng package gốc hoặc package con.
- Viết tài liệu package giúp người đọc hiểu trách nhiệm và phạm vi của package.
- Kiểm tra metadata package có được giữ và phản ánh đúng trong mô hình Spring Modulith.

## `package-info.java` dùng để làm gì?

Java cho phép khai báo annotation và Javadoc ở cấp package thông qua file có tên `package-info.java`. File này nằm trong thư mục tương ứng với package và có khai báo `package` ở cuối phần Javadoc hoặc sau các annotation.

Ví dụ:

```java
/**
 * Public API for order management.
 *
 * <p>Clients use the interfaces in this package to create and query orders.
 */
package com.acme.orders;
```

Javadoc ở đây mô tả mục đích của package `com.acme.orders`. Nếu cần khai báo metadata kiến trúc, có thể thêm annotation trước dòng `package`:

```java
@org.springframework.modulith.ApplicationModule(
    id = "orders",
    displayName = "Quản lý đơn hàng"
)
package com.acme.orders;
```

Annotation package-level là metadata gắn với package. Nó không phải một class nghiệp vụ và không cần được tạo thành object để sử dụng. Các công cụ đọc bytecode hoặc mô hình package có thể tra cứu metadata này sau khi mã nguồn được biên dịch.

## Vai trò của `@PackageInfo`

`@PackageInfo` là marker annotation thuộc Spring Modulith, được đặt trong `package-info.java`:

```java
@org.springframework.modulith.PackageInfo
package com.acme.orders.integration;
```

Hoặc dùng import tường minh:

```java
@PackageInfo
package com.acme.orders.integration;

import org.springframework.modulith.PackageInfo;
```

Marker này hữu ích khi package chưa có class Java thông thường nhưng nhóm vẫn muốn package tồn tại rõ ràng trong metadata. Ví dụ, nhóm có thể tạo trước package `integration` để ghi tài liệu về trách nhiệm tích hợp hoặc xác định một vùng package sẽ được bổ sung adapter sau này.

Khi biên dịch, thông tin package được biểu diễn qua `package-info.class`. `@PackageInfo` đánh dấu rõ ràng file package-info cần được giữ lại như một phần metadata của package, ngay cả khi package chưa có type nghiệp vụ thông thường. Nhờ vậy, các công cụ phân tích có thể nhận diện package và metadata đi kèm.

`@PackageInfo` không phải nơi khai báo tên module, không tự tạo module, không tự công bố package thành API và cũng không thay thế Javadoc. Nó là marker cho sự hiện diện của package metadata. Ý nghĩa kiến trúc cụ thể vẫn đến từ các annotation chuyên biệt như `@ApplicationModule`, `@NamedInterface` hoặc nội dung tài liệu package.

## Khi nào nên dùng marker?

Hãy dùng `@PackageInfo` khi package cần được mô tả hoặc đánh dấu trong mô hình dù chưa có class thông thường. Một số trường hợp:

- Package được tạo trước để xác định ranh giới một nhóm adapter hoặc integration.
- Package chứa tài liệu kiến trúc quan trọng nhưng implementation sẽ được bổ sung sau.
- Package được dùng làm vị trí khai báo metadata package-level.
- Nhóm muốn giữ một package có chủ đích trong cấu trúc source code và công cụ phân tích.

Nếu package đã có class Java thông thường và không có nhu cầu đặc biệt về việc giữ package rỗng, thường không cần thêm marker chỉ để trang trí. Chỉ thêm annotation khi có lý do cụ thể để người đọc hiểu tại sao package metadata phải tồn tại.

## Kết hợp `@PackageInfo` với metadata module

`@ApplicationModule` mô tả metadata của application module. Annotation này thường được đặt trong `package-info.java` của package gốc:

```java
@ApplicationModule(
    id = "orders",
    displayName = "Quản lý đơn hàng"
)
package com.acme.orders;

import org.springframework.modulith.ApplicationModule;
```

Ở đây, `@ApplicationModule` cung cấp metadata nhận diện module `orders`. Package gốc cũng là vị trí mặc định của API mà module công bố.

Nếu muốn mô tả một package con rỗng dành cho integration, có thể tạo file riêng:

```java
/**
 * Integration adapters that connect the orders module to external systems.
 * Implementations remain internal to the orders module.
 */
@PackageInfo
package com.acme.orders.integration;

import org.springframework.modulith.PackageInfo;
```

Trong ví dụ này, package `integration` được ghi nhận như một package có chủ đích. Marker không biến nó thành một application module độc lập; nó vẫn nằm trong phạm vi module `orders` theo cấu trúc package.

Nếu sau này package chứa adapter, các class đó có thể được thêm vào mà không cần đổi ý nghĩa của package metadata. Nếu package cần trở thành một API bổ sung, hãy đánh dấu bằng named interface một cách tường minh.

## Kết hợp với `@NamedInterface`

`@NamedInterface` công bố một package con như một phần API mà module khác được phép sử dụng. Ví dụ, module `orders` có package `events`:

```java
@NamedInterface("events")
package com.acme.orders.events;

import org.springframework.modulith.NamedInterface;
```

Package này có thể chứa event type mà module khác cần tham chiếu. Khi package có type thực tế, annotation `@NamedInterface` mô tả rõ hợp đồng được công bố.

Trong một package chỉ có metadata và chưa có type thông thường, có thể kết hợp marker `@PackageInfo` với annotation named interface nếu mục đích là giữ package metadata:

```java
/**
 * Public event contracts published by the orders module.
 */
@PackageInfo
@NamedInterface("events")
package com.acme.orders.events;

import org.springframework.modulith.NamedInterface;
import org.springframework.modulith.PackageInfo;
```

Hai annotation có trách nhiệm khác nhau:

- `@PackageInfo` đánh dấu sự hiện diện của package metadata.
- `@NamedInterface("events")` đặt tên cho API package được công bố.

Khi thêm event type, chúng nằm trong package đã được công bố. Module tiêu thụ có thể giới hạn dependency bằng `allowedDependencies = "orders :: events"` ở package metadata của chính nó.

Không nên dùng `@PackageInfo` thay cho `@NamedInterface`. Nếu mục đích là công bố API, phải khai báo đúng metadata named interface. Ngược lại, không cần tạo named interface cho package chỉ dùng để nhóm implementation nội bộ.

## Ví dụ tổ chức package metadata

Một module `orders` có thể được tổ chức như sau:

```text
com.acme.orders
├── package-info.java          # @ApplicationModule
├── OrderManagement.java       # Public API
├── events
│   ├── package-info.java       # @NamedInterface("events")
│   └── OrderSubmitted.java
├── integration
│   └── package-info.java       # @PackageInfo + package documentation
└── internal
    ├── DefaultOrderManagement.java
    └── JpaOrderRepository.java
```

Các file metadata minh họa:

**`com.acme.orders/package-info.java`**

```java
@ApplicationModule(
    id = "orders",
    displayName = "Quản lý đơn hàng"
)
package com.acme.orders;

import org.springframework.modulith.ApplicationModule;
```

**`com.acme.orders.events/package-info.java`**

```java
@NamedInterface("events")
package com.acme.orders.events;

import org.springframework.modulith.NamedInterface;
```

**`com.acme.orders.integration/package-info.java`**

```java
/**
 * Adapters for external order-related systems.
 */
@PackageInfo
package com.acme.orders.integration;

import org.springframework.modulith.PackageInfo;
```

Ở đây, module root, named interface và package integration có vai trò riêng. Package `internal` chứa implementation không được công bố. Package `integration` được ghi nhận để mô tả cấu trúc nhưng không tự trở thành API.

## Tài liệu package giúp giảm mơ hồ kiến trúc

Javadoc trong `package-info.java` nên trả lời những câu hỏi mà tên package không thể hiện:

- Package này chịu trách nhiệm cho phần nào của module?
- Những type nào được phép đặt ở đây?
- Package có phải API công khai hay chỉ chứa implementation?
- Nếu package chứa adapter, nó kết nối với hệ thống bên ngoài nào và ai sở hữu cấu hình?
- Những dependency nào được phép xuất hiện trong package?

Ví dụ, tài liệu `com.acme.orders.integration` có thể ghi rằng package chứa adapter kết nối với hệ thống vận chuyển bên ngoài, được module `orders` sở hữu và không phải API cho module khác. Điều này giúp thành viên mới hiểu vai trò package trước khi thêm class.

Tài liệu nên mô tả quy ước hiện tại, không hứa hẹn những khả năng chưa được triển khai. Khi trách nhiệm package thay đổi, hãy cập nhật Javadoc cùng thay đổi mã nguồn.

## Kiểm chứng package metadata

Sau khi tạo hoặc sửa `package-info.java`, hãy kiểm tra ba lớp thông tin:

1. **Source:** file nằm đúng thư mục package, khai báo đúng package name và import đúng annotation.
2. **Bytecode:** quá trình biên dịch tạo `package-info.class` cho package cần giữ metadata.
3. **Mô hình kiến trúc:** Spring Modulith nhận diện module, named interface và package theo đúng chủ đích.

Có thể kiểm tra mô hình module bằng test:

```java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    @Test
    void verifiesApplicationModuleStructure() {
        ApplicationModules.of(Application.class).verify();
    }
}
```

`verify()` tập trung vào quy tắc module và dependency. Nó không thay thế việc review nội dung Javadoc hoặc đảm bảo mọi package rỗng đều được tài liệu hóa đúng ý định. Với package metadata quan trọng, hãy kiểm tra thêm kết quả biên dịch và module arrangement được Spring Modulith phát hiện.

Nếu một package không xuất hiện như mong đợi, hãy xác minh package-info có được biên dịch, annotation có đúng target và package có nằm trong phạm vi scan của ứng dụng hay không. Kiểm tra đúng cấu hình module detection đang được sử dụng.

## Những lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Tạo `package-info.java` nhưng không ghi đúng package declaration | Metadata gắn vào package khác hoặc source không biên dịch | Đặt file trong đúng thư mục và kiểm tra khai báo package |
| Nghĩ `@PackageInfo` tự tạo application module | Nhầm marker với cơ chế module detection | Dùng `@ApplicationModule` hoặc detection strategy cho module |
| Dùng `@PackageInfo` để công bố API | Package vẫn không được định nghĩa là named interface | Dùng `@NamedInterface` cho package API |
| Thêm marker vào mọi package một cách máy móc | Metadata thừa, khó hiểu mục đích | Chỉ dùng khi package cần được giữ rõ dù không có type thông thường |
| Không kiểm tra `package-info.class` sau build | Package metadata có thể không hiện diện như mong đợi | Xác nhận output biên dịch và module model |
| Javadoc mô tả trách nhiệm đã lỗi thời | Người phát triển hiểu sai phạm vi package | Cập nhật tài liệu cùng thay đổi cấu trúc |

## Quy trình tạo package metadata

Khi cần tạo một package mới chỉ chứa metadata, hãy làm theo các bước:

1. Xác định package thuộc module nào và trách nhiệm của nó.
2. Tạo đúng đường dẫn `package-info.java`.
3. Viết Javadoc giải thích mục đích và phạm vi package.
4. Thêm `@PackageInfo` nếu package cần được giữ lại dù chưa có class Java thông thường.
5. Thêm annotation chuyên biệt như `@ApplicationModule` hoặc `@NamedInterface` nếu package thực sự cần ngữ nghĩa đó.
6. Biên dịch và xác nhận `package-info.class` được tạo.
7. Kiểm tra module arrangement và chạy `ApplicationModules.verify()`.
8. Review xem metadata có mô tả đúng trách nhiệm và mức độ công khai của package không.

## Bài tập tự đánh giá

Một nhóm tạo package `com.acme.billing.spi` để chuẩn bị cho extension point tính phí. Hiện package chỉ có `package-info.java`, chưa có interface nào. Nhóm muốn ghi tài liệu cho package, giữ nó trong metadata và công bố nó như named interface `spi` khi hợp đồng được thống nhất.

Hãy trả lời:

1. Vì sao `package-info.java` có ích khi package chưa có class thông thường?
2. `@PackageInfo` giải quyết vấn đề gì trong tình huống này?
3. Annotation nào biểu thị package là named interface `spi`?
4. Vì sao `@PackageInfo` không tự công bố package thành API?
5. Bạn sẽ kiểm tra điều gì sau khi biên dịch và khi chạy `ApplicationModules.verify()`?

Một cách khai báo phù hợp cho giai đoạn chuẩn bị là:

```java
/**
 * Extension contracts for billing policies.
 */
@PackageInfo
@NamedInterface("spi")
package com.acme.billing.spi;

import org.springframework.modulith.NamedInterface;
import org.springframework.modulith.PackageInfo;
```

`@PackageInfo` giữ metadata package; `@NamedInterface("spi")` xác định hợp đồng package được công bố. Khi interface được thêm vào, nó thuộc named interface này và có thể được module khác tham chiếu theo dependency rule.

## Kết luận

`package-info.java` là nơi mô tả và khai báo metadata ở cấp package. `@PackageInfo` là marker giúp package metadata được giữ rõ ràng khi package chưa có class Java thông thường. Marker này không thay thế `@ApplicationModule` để xác định module hoặc `@NamedInterface` để công bố API. Kết hợp đúng các annotation chuyên biệt với Javadoc rõ ràng giúp mô hình package dễ hiểu, dễ kiểm chứng và duy trì cùng ranh giới module.

## Tài liệu tham khảo

- [Spring Modulith Reference — Fundamentals](https://docs.spring.io/spring-modulith/reference/fundamentals.html)
- [Spring Modulith API — `PackageInfo`](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/PackageInfo.html)
- [Spring Modulith API — `ApplicationModule`](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/ApplicationModule.html)
- [Spring Modulith API — `NamedInterface`](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/NamedInterface.html)
- [Java Language Specification — Package Declarations](https://docs.oracle.com/javase/specs/jls/se21/html/jls-7.html#jls-7.4)
