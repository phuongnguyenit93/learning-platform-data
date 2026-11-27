# ApplicationModuleDetectionStrategy giải quyết bài toán nào?

Bài này thuộc chương **Custom detection** của module **SPRING_MODULITH_MODULE_MODEL**. Spring Modulith mô hình hóa một ứng dụng Spring Boot thành các application module để làm rõ ranh giới nghiệp vụ, API công khai và quan hệ phụ thuộc giữa các package. Để tạo mô hình đó, framework phải biết package nào là điểm bắt đầu của từng module.

Chiến lược mặc định phù hợp khi các module là package con trực tiếp của application base package. Nhưng ứng dụng legacy hoặc codebase có quy ước package đặc thù có thể tổ chức module ở vị trí khác. **`ApplicationModuleDetectionStrategy` cho phép thay đổi cách Spring Modulith chọn module base package**, để mô hình phát hiện phù hợp với cấu trúc thực tế của ứng dụng.

## 1. Bài toán: package hiện tại không khớp chiến lược mặc định

Theo chiến lược mặc định, Spring Modulith lấy các package con trực tiếp của application base package làm application module.

Ví dụ, nếu lớp `@SpringBootApplication` nằm trong `com.acme.shop`:

~~~text
com.acme.shop
├── ShopApplication.java
├── order
├── inventory
└── shipping
~~~

Các package `order`, `inventory` và `shipping` là module cấp cao theo quy ước mặc định.

Tuy nhiên, một ứng dụng legacy có thể được tổ chức như sau:

~~~text
com.acme.shop
├── ShopApplication.java
├── features
│   ├── order
│   ├── inventory
│   └── shipping
├── integrations
│   ├── payment
│   └── tax
└── shared
~~~

Với cấu trúc này, các package con trực tiếp của `com.acme.shop` là `features`, `integrations` và `shared`. Nhưng các capability mà nhóm muốn mô hình hóa lại nằm sâu hơn, chẳng hạn `features.order` hoặc `integrations.payment`.

Nếu giữ chiến lược mặc định, mô hình module có thể không trùng với ranh giới logic mà nhóm mong muốn. Nhóm có thể tổ chức lại package để đưa capability lên cấp trực tiếp, hoặc định nghĩa chiến lược phát hiện phù hợp với quy ước hiện có.

## 2. ApplicationModuleDetectionStrategy làm nhiệm vụ gì?

`ApplicationModuleDetectionStrategy` là một SPI (Service Provider Interface) cho phép xác định **những package nào được chọn làm module base package** bên dưới application base package.

Nó tập trung trả lời một câu hỏi:

> Với package gốc của ứng dụng này, những package nào cần được xem là điểm bắt đầu của application module?

Chiến lược này không tự thiết kế capability, không quyết định API nào được công khai và cũng không khai báo các dependency được phép. Nó chỉ quyết định cách tìm ra package gốc của từng module.

Sau khi module được phát hiện, các quy tắc khác của Spring Modulith tiếp tục áp dụng: package gốc module là API mặc định, package con thường là nội bộ, named interface xác định phần API được công khai thêm và dependency rules kiểm soát hướng phụ thuộc.

## 3. Khi nào chiến lược mặc định là đủ?

Nếu ứng dụng đã tổ chức package theo capability ngay dưới application base package, chiến lược mặc định thường là lựa chọn đơn giản nhất:

~~~text
com.acme.shop
├── ShopApplication.java
├── order
├── inventory
├── customer
└── payment
~~~

Không cần viết một chiến lược tùy chỉnh chỉ để lặp lại quy tắc package con trực tiếp. Dùng mặc định giúp cấu trúc dễ dự đoán và giảm cấu hình riêng.

Spring Modulith cũng có chiến lược phát hiện dựa trên annotation `@ApplicationModule` hoặc annotation module của jMolecules. Chiến lược này phù hợp khi nhóm muốn đánh dấu rõ các package module thay vì dựa hoàn toàn vào vị trí package.

Chỉ nên tạo custom strategy khi quy tắc mặc định hoặc chiến lược đánh dấu tường minh có sẵn không thể mô tả hợp lý cấu trúc module của ứng dụng.

## 4. Những tình huống custom strategy hữu ích

Một chiến lược tùy chỉnh có thể phù hợp trong các trường hợp:

- **Legacy có một package trung gian:** module nằm dưới `features/*`, `domains/*` hoặc một package phân nhóm tương tự.
- **Nhiều nhóm package có quy ước khác nhau:** một phần module nằm dưới `features`, phần khác nằm dưới `integrations`.
- **Tổ chức mã nguồn theo convention riêng:** nhóm đã có quy tắc ổn định để xác định module base package và muốn Spring Modulith áp dụng đúng quy tắc đó.
- **Migration theo giai đoạn:** nhóm cần giữ cấu trúc hiện tại trong khi từng bước chuyển module về package layout chuẩn hơn.
- **Chỉ chọn một tập package nhất định:** không phải mọi package con trực tiếp đều đại diện cho capability cần kiểm tra.

Ví dụ, nếu nhóm muốn xem các package con của `features` là module, một custom strategy có thể chọn các package đó thay vì chọn chính `features`.

## 5. Cách viết một chiến lược tùy chỉnh

`ApplicationModuleDetectionStrategy` cung cấp phương thức `getModuleBasePackages(` để nhận package gốc ứng dụng và trả về luồng các package được chọn làm module base package.

Ví dụ, chọn các package con trực tiếp bên dưới package `features`:

~~~java
package com.acme.shop.architecture;

import java.util.stream.Stream;

import org.springframework.modulith.core.ApplicationModuleDetectionStrategy;
import org.springframework.modulith.core.JavaPackage;

public class FeaturesModuleDetectionStrategy
        implements ApplicationModuleDetectionStrategy {

    @Override
    public Stream<JavaPackage> getModuleBasePackages(JavaPackage basePackage) {

        return basePackage.getSubpackages()
                .filter(it -> it.getName().endsWith(".features"))
                .flatMap(JavaPackage::getSubpackages);
    }
}
~~~

Giải thích:

1. `basePackage` là package gốc ứng dụng mà Spring Modulith đang khám phá.
2. `getSubpackages()` lấy các package con trực tiếp của package đó.
3. `filter(...)` chọn package trung gian có tên kết thúc bằng `.features`.
4. `flatMap(JavaPackage::getSubpackages)` lấy các package con của `features`, chẳng hạn `features.order`, `features.inventory`.

Với cây package ví dụ, chiến lược trả về các module base package tương ứng với order, inventory và shipping nằm dưới features.

Đây là ví dụ theo một convention cụ thể. Nếu ứng dụng có nhiều package trung gian hoặc nhiều cấp lồng nhau, hãy viết điều kiện chọn rõ ràng để không vô tình đưa package tiện ích, package cấu hình hoặc package kỹ thuật thành module.

## 6. Đăng ký custom strategy

Sau khi triển khai lớp chiến lược, đăng ký nó qua cơ chế Spring factories.

Tạo file:

`src/main/resources/META-INF/spring.factories`

với nội dung:

~~~properties
org.springframework.modulith.core.ApplicationModuleDetectionStrategy=\
com.acme.shop.architecture.FeaturesModuleDetectionStrategy
~~~

Tên lớp ở vế phải phải là tên đầy đủ của implementation thực tế. Khi Spring Modulith tải chiến lược, implementation đã đăng ký sẽ được dùng để xác định module base package.

Giữ lớp strategy ở package cấu hình kiến trúc riêng, có tên dễ hiểu và có tài liệu mô tả quy ước mà nó thực thi. Nếu dự án có nhiều module build độc lập hoặc nhiều file metadata, hãy bảo đảm registration nằm trong artifact được đưa vào classpath khi xây dựng mô hình.

## 7. So sánh các lựa chọn phát hiện module

| Lựa chọn | Cách chọn module base package | Khi phù hợp |
|---|---|---|
| Chiến lược mặc định | Chọn package con trực tiếp của application base package. | Package đã được tổ chức theo capability. |
| Phát hiện tường minh | Chọn package được đánh dấu bằng `@ApplicationModule` hoặc `@Module`. | Nhóm muốn đánh dấu module rõ ràng trong code. |
| Custom strategy | Chọn package theo quy tắc do nhóm triển khai. | Cấu trúc legacy hoặc convention riêng không khớp hai lựa chọn trên. |

Custom strategy đem lại tính linh hoạt, nhưng cũng thêm một quy tắc riêng mà nhóm phải duy trì. Nếu có thể đạt cùng mục tiêu bằng cách tổ chức lại package hoặc dùng chiến lược phát hiện tường minh, hãy cân nhắc các cách đó trước.

## 8. Thiết kế custom strategy có kiểm soát

Một custom strategy tốt cần có các đặc điểm:

- **Xác định rõ đầu vào:** hiểu package gốc mà Spring Modulith truyền vào.
- **Trả về đúng module base package:** mỗi phần tử trong kết quả phải thực sự là gốc của một application module.
- **Có tính xác định:** cùng một cấu trúc package phải cho cùng một tập module, không phụ thuộc thứ tự file hoặc trạng thái runtime.
- **Không chọn package quá rộng:** tránh trả về package chứa nhiều capability không liên quan chỉ vì nó nằm trong nhánh phù hợp.
- **Không bỏ sót module:** mọi capability cần được kiểm tra phải được phát hiện.
- **Có thể giải thích:** thành viên nhóm có thể hiểu vì sao một package được chọn làm module.

Tránh dùng quy tắc quá phụ thuộc vào tên lớp, suffix kỹ thuật hoặc các điều kiện thay đổi thường xuyên. Ví dụ, chọn mọi package kết thúc bằng `.service` có thể khiến module được phát hiện theo technical layer thay vì theo nghiệp vụ.

Nếu chiến lược chọn package từ nhiều nhánh, hãy biểu diễn rõ từng nhánh trong code và ghi lại ý nghĩa của chúng. Khi convention thay đổi, strategy và các bài kiểm tra kiến trúc cần được cập nhật cùng nhau.

## 9. Những giới hạn cần hiểu đúng

`ApplicationModuleDetectionStrategy` chỉ quyết định cách phát hiện module. Nó không thay thế những quyết định kiến trúc khác.

| Vấn đề | Cơ chế liên quan |
|---|---|
| Package nào là module? | `ApplicationModuleDetectionStrategy`. |
| Package nào là API mặc định? | Quy ước package của application module. |
| Package con nào được công khai? | `@NamedInterface`. |
| Module được phép phụ thuộc vào đâu? | `@ApplicationModule(allowedDependencies = ...)`. |
| Module có phụ thuộc vi phạm hay không? | `ApplicationModules.verify()`. |
| Capability được chia có đúng nghiệp vụ không? | Phân tích miền và quyết định của nhóm. |

Một strategy có thể giúp framework nhận diện `features.order` là module. Nhưng strategy không tự xác định order cần công khai hợp đồng nào, có nên phụ thuộc vào inventory hay dữ liệu nào thuộc quyền sở hữu của order. Những câu hỏi đó vẫn cần được xử lý trong thiết kế module.

## 10. Kiểm chứng kết quả phát hiện

Sau khi đăng ký strategy, tạo mô hình ứng dụng và chạy kiểm tra kiến trúc:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    @Test
    void verifiesApplicationModuleStructure() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

Kiểm tra này giúp phát hiện các vấn đề trong mô hình module đã tạo, chẳng hạn dependency vào package nội bộ, dependency không được phép hoặc vòng phụ thuộc.

Khi kết quả không như mong muốn, kiểm tra theo thứ tự:

1. Package của lớp ứng dụng có đúng là application base package dự kiến không?
2. Custom strategy có lọc đúng package trung gian không?
3. Strategy có trả về package gốc của từng capability không?
4. Có package nào bị chọn nhầm hoặc bị bỏ sót không?
5. Các package nội bộ và API công khai có được tổ chức đúng sau khi module được phát hiện không?
6. Các dependency rules có phản ánh đúng hướng phụ thuộc đã thống nhất không?

Nên đưa kiểm tra kiến trúc vào test suite và CI để thay đổi package hoặc strategy được phát hiện sớm. Với custom strategy, hãy bổ sung test tập trung cho quy tắc chọn package nếu logic lọc có nhiều nhánh hoặc điều kiện.

## 11. Quy trình quyết định có cần custom strategy

1. **Xác định application base package.** Chọn package chứa lớp ứng dụng Spring Boot.
2. **Quan sát cấu trúc hiện tại.** Liệt kê package con trực tiếp và các package lồng bên dưới.
3. **So sánh với capability mong muốn.** Kiểm tra kết quả mặc định có trùng với ranh giới module nghiệp vụ không.
4. **Thử chiến lược có sẵn.** Nếu muốn đánh dấu rõ module, cân nhắc chiến lược explicitly annotated.
5. **Chỉ viết custom strategy khi cần.** Mô tả quy tắc chọn module base package bằng code dễ đọc và xác định.
6. **Đăng ký strategy.** Đưa implementation vào Spring factories metadata theo cơ chế của Spring Modulith.
7. **Kiểm tra mô hình.** Chạy `ApplicationModules.verify()` và xem lại tập module được phát hiện.
8. **Duy trì convention.** Khi package layout thay đổi, cập nhật strategy và kiểm tra kiến trúc tương ứng.

Đừng tạo custom strategy chỉ để tránh sửa một cấu trúc package chưa hợp lý. Một strategy riêng nên giải quyết một quy ước có chủ đích, tồn tại ổn định và được nhóm hiểu rõ.

## Ghi nhớ

`ApplicationModuleDetectionStrategy` giải quyết bài toán **chọn module base package theo cấu trúc thực tế của ứng dụng**. Nó hữu ích khi package layout legacy hoặc convention riêng không phù hợp với chiến lược mặc định dựa trên package con trực tiếp hay chiến lược đánh dấu tường minh.

Hãy dùng custom strategy để biểu diễn một quy tắc phát hiện rõ ràng, xác định và dễ duy trì. Sau khi module được nhận diện, tiếp tục kiểm soát API, named interface và dependency bằng các cơ chế tương ứng của Spring Modulith, rồi xác minh toàn bộ mô hình bằng `ApplicationModules.verify()`.
