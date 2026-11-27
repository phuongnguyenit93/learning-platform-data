# Đưa verify vào test suite

Các quy tắc kiến trúc của modular monolith chỉ có giá trị khi được kiểm tra thường xuyên. Nếu nhóm phát hiện phụ thuộc vòng hoặc truy cập package nội bộ trong lúc review thủ công, lỗi có thể đã lan sang nhiều module. Spring Modulith cung cấp `ApplicationModules.verify()` để biến việc kiểm tra ranh giới module thành một bài test tự động trong test suite.

Ta chỉ cần tạo mô hình từ lớp ứng dụng rồi gọi `verify()` trong một test JUnit. Bài test này có thể chạy cùng các unit test và integration test hiện có, đồng thời trở thành một cổng kiểm tra kiến trúc trong quy trình build và CI.

## 1. Vì sao nên đưa verify vào test suite?

Khi nhiều nhóm cùng phát triển một ứng dụng Spring Boot, một thay đổi nhỏ có thể tạo ra phụ thuộc ngoài ý muốn. Ví dụ, module `shipping` import repository nội bộ của module `inventory` vì lớp đó đang có sẵn và được khai báo `public`. Mã nguồn có thể biên dịch, nhưng thiết kế module đã bị phá vỡ.

`ApplicationModules.verify()` phân tích cấu trúc module và kiểm tra các quy tắc kiến trúc Spring Modulith nhận diện, bao gồm:

- Phụ thuộc vòng giữa các application module.
- Truy cập package nội bộ của module khác thay vì API công khai hoặc named interface.
- Phụ thuộc không nằm trong danh sách `allowedDependencies` khi module khai báo giới hạn này.
- Các quy tắc xác minh bổ sung được cấu hình trong dự án, nếu có.

Đặt lời gọi `verify()` trong test giúp mọi thay đổi được kiểm tra bằng cùng một tiêu chuẩn. Khi vi phạm xuất hiện, test thất bại và báo các quan hệ phụ thuộc cần xem xét.

## 2. Tạo một architecture test

Giả sử lớp Spring Boot chính nằm trong package gốc `com.example`:

```text
src
├── main
│   └── java
│       └── com/example
│           ├── Application.java
│           ├── inventory
│           └── shipping
└── test
    └── java
        └── com/example
            └── ModularityTests.java
```

Tạo `ModularityTests.java` trong source set test:

```java
package com.example;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    @Test
    void verifiesApplicationModuleStructure() {
        ApplicationModules.of(Application.class).verify();
    }
}
```

`ApplicationModules.of(Application.class)` sử dụng lớp ứng dụng làm điểm bắt đầu để khám phá các module trong package tương ứng. `verify()` thực hiện các kiểm tra kiến trúc trên mô hình đó. Nếu phát hiện vi phạm, phương thức ném lỗi xác minh và JUnit đánh dấu test thất bại.

Đây là một test JUnit thông thường. Nó không cần `@SpringBootTest`, không cần khởi tạo `ApplicationContext`, không kết nối database và không chạy server. Việc xác minh dựa trên mô hình package và các kiểu trong ứng dụng, nên có thể chạy nhanh như một phần của test suite.

## 3. Đảm bảo test được build tool phát hiện

Đặt test trong `src/test/java` và đặt tên theo quy ước mà cấu hình test của dự án đang sử dụng, ví dụ `ModularityTests`. Với JUnit Jupiter, bảo đảm JUnit nằm trên test classpath và test engine được cấu hình trong build.

Artifact chứa `ApplicationModules` (thường là `spring-modulith-core`, trực tiếp hoặc thông qua dependency khác) cũng phải có trên test classpath. Dùng phiên bản Spring Modulith đồng bộ với các dependency Spring Modulith còn lại của ứng dụng.

Khi cấu hình test đúng, bài kiểm tra kiến trúc được chạy cùng lệnh test thông thường:

```bash
# Maven Wrapper
./mvnw test

# Gradle Wrapper
./gradlew test
```

Không cần tạo một bước kiểm tra kiến trúc thủ công riêng trong CI nếu pipeline đã chạy đầy đủ test task. Điều cần xác nhận là pipeline không loại trừ `ModularityTests` bằng pattern include/exclude hoặc cấu hình test riêng.

## 4. Giữ một điểm kiểm tra kiến trúc rõ ràng

Thông thường, một test class chuyên trách là đủ để kiểm tra toàn bộ mô hình module của ứng dụng:

```java
package com.example;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ArchitectureTests {

    private final ApplicationModules modules =
            ApplicationModules.of(Application.class);

    @Test
    void moduleDependenciesAreValid() {
        modules.verify();
    }
}
```

Giữ test này tập trung vào kiến trúc giúp người đọc dễ nhận ra vai trò của nó và tránh lặp lại cùng một lần xác minh trong nhiều test class. Nếu ứng dụng có nhiều entry point hoặc nhiều mô hình module độc lập, có thể tạo test riêng cho từng mô hình và chỉ rõ lớp gốc tương ứng.

Không nên đặt `verify()` trong từng unit test nghiệp vụ. Unit test cần kiểm tra hành vi của một thành phần; architecture test kiểm tra quan hệ giữa các module trên toàn ứng dụng. Tách trách nhiệm như vậy giúp test suite dễ bảo trì và tránh chi phí xác minh lặp lại.

## 5. Đọc và xử lý khi test thất bại

Ví dụ, module `shipping` phụ thuộc trực tiếp vào implementation nội bộ của `inventory`:

```java
package com.example.shipping;

import com.example.inventory.internal.InventoryService;
import org.springframework.stereotype.Service;

@Service
class ShippingService {

    private final InventoryService inventory;

    ShippingService(InventoryService inventory) {
        this.inventory = inventory;
    }
}
```

Nếu `InventoryService` nằm trong package nội bộ không được công khai, `ApplicationModules.verify()` sẽ báo vi phạm khi phân tích phụ thuộc. Cách sửa là để module `inventory` công khai một hợp đồng phù hợp, chẳng hạn `InventoryOperations` trong package gốc hoặc trong named interface `inventory::api`, rồi inject hợp đồng đó vào `ShippingService`.

Khi test thất bại, xử lý theo trình tự:

1. Đọc danh sách vi phạm để xác định module nguồn, module đích và kiểu/package gây phụ thuộc.
2. Xác định phụ thuộc có phản ánh một nhu cầu nghiệp vụ hợp lệ hay là truy cập nhầm chi tiết nội bộ.
3. Nếu nhu cầu hợp lệ, bổ sung hoặc điều chỉnh API công khai tại module sở hữu; nếu phụ thuộc không cần thiết, loại bỏ nó.
4. Nếu module có `allowedDependencies`, cập nhật quy tắc chỉ khi quan hệ đó được kiến trúc cho phép và có lý do rõ ràng.
5. Chạy lại architecture test và các test nghiệp vụ liên quan.

Không nên tắt test hoặc nới lỏng toàn bộ quy tắc chỉ để build xanh. Mỗi ngoại lệ làm yếu đi khả năng bảo vệ ranh giới module và cần được cân nhắc như một quyết định kiến trúc.

## 6. Kết hợp verify với các loại test khác

`verify()` và test tích hợp module phục vụ các mục tiêu khác nhau:

| Loại test | Mục tiêu | Có cần khởi tạo Spring context? |
|---|---|---|
| Architecture test với `ApplicationModules.verify()` | Kiểm tra cấu trúc package, API và quan hệ phụ thuộc giữa module | Không |
| Unit test | Kiểm tra hành vi của một lớp hoặc một đơn vị nhỏ | Thường không |
| Module integration test, ví dụ dùng `@ApplicationModuleTest` | Kiểm tra cách các bean và thành phần trong một module phối hợp | Có, theo cấu hình test |
| End-to-end test | Kiểm tra luồng nghiệp vụ qua nhiều thành phần của ứng dụng | Thường có |

Một module có thể có unit test và module integration test riêng. Architecture test vẫn nên chạy ở cấp ứng dụng để phát hiện phụ thuộc giữa các module, kể cả khi từng module riêng lẻ đều có test hành vi đầy đủ.

## 7. Dùng VerificationOptions khi cần quy tắc bổ sung

Nếu dự án đã định nghĩa các quy tắc ArchUnit bổ sung hoặc cần tùy chỉnh nhóm kiểm tra, có thể truyền `VerificationOptions` vào `verify()`:

```java
package com.example;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;
import org.springframework.modulith.core.VerificationOptions;

class ArchitectureTests {

    @Test
    void verifiesModulesWithProjectRules() {
        var options = VerificationOptions.defaults();

        ApplicationModules.of(Application.class).verify(options);
    }
}
```

Ví dụ dùng options mặc định để thể hiện điểm mở rộng. Khi đã có quy tắc riêng, hãy tạo options dùng chung ở một lớp hỗ trợ test và thêm các quy tắc đó theo chủ đích. Dùng `andAdditionalVerifications(…)` nếu muốn giữ các kiểm tra bổ sung mặc định; `withAdditionalVerifications(…)` thay thế nhóm kiểm tra bổ sung mặc định bằng nhóm được truyền vào.

Nếu dự án không có quy tắc bổ sung, lời gọi `verify()` đơn giản là đủ. Chỉ thêm cấu hình khi nó bảo vệ một quy ước kiến trúc thực sự cần thiết.

## 8. Đưa architecture test vào CI

Một pipeline CI nên chạy test suite trên mỗi thay đổi có thể ảnh hưởng đến cấu trúc module. Khi `ModularityTests` là một test JUnit thông thường, nó sẽ được chạy cùng test task mà pipeline vốn sử dụng.

Ví dụ luồng kiểm tra:

```text
Developer tạo commit hoặc pull request
                |
                v
       Build và compile test
                |
                v
       Chạy toàn bộ test suite
                |
                v
       ModularityTests.verify()
                |
          +-----+-----+
          |           |
       Hợp lệ      Có vi phạm
          |           |
          v           v
      CI tiếp tục   Test thất bại,
      các bước sau  xem lại phụ thuộc
```

Để test thực sự bảo vệ kiến trúc, hãy bảo đảm:

- Test class được build tool phát hiện và không bị loại khỏi CI.
- Pipeline thực hiện test task, không chỉ compile hoặc đóng gói artifact.
- Lỗi từ architecture test làm job thất bại như các test khác.
- Khi thay đổi package hoặc API module, pull request có cập nhật mã nguồn và các quyết định kiến trúc liên quan.

## 9. Bài tập thực hành

1. Tạo `ModularityTests` trong `src/test/java` cùng package gốc với lớp `Application`.
2. Gọi `ApplicationModules.of(Application.class).verify()` trong một phương thức `@Test`.
3. Chạy test suite bằng build tool của dự án và xác nhận test kiến trúc xuất hiện trong kết quả.
4. Tạm tạo một phụ thuộc từ module này đến package nội bộ của module khác và quan sát test thất bại.
5. Chuyển phụ thuộc sang package gốc hoặc named interface được công khai, sau đó chạy lại test.
6. Xác nhận CI chạy test task và coi lỗi kiến trúc là lỗi build.

Sau bài tập, bạn cần giải thích được vì sao `verify()` nên nằm trong một architecture test cấp ứng dụng, test này khác gì với module integration test, và cách nó ngăn phụ thuộc không hợp lệ quay trở lại trong các thay đổi sau này.

## Tài liệu tham khảo

- [Verifying Application Module Structure – Spring Modulith Reference](https://docs.spring.io/spring-modulith/reference/verification.html)
- [ApplicationModules API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModules.html)
- [Application Module Tests – Spring Modulith Reference](https://docs.spring.io/spring-modulith/reference/testing.html)
- [VerificationOptions API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/VerificationOptions.html)
