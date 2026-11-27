# Model và tests

## Giữ test kiến trúc ổn định trong CI

Test kiến trúc chỉ có giá trị khi cho kết quả nhất quán trên máy lập trình viên và trong CI. Với Spring Modulith, có thể biến các quy tắc về ranh giới mô-đun, API công khai và phụ thuộc thành một bài kiểm tra tự động bằng `ApplicationModules.verify()`. Bài kiểm tra này phân tích cấu trúc ứng dụng, vì vậy nên được thiết kế độc lập với database, cấu hình môi trường và trạng thái của Spring application context.

Một pipeline ổn định cần xác định rõ package gốc của ứng dụng, dùng phiên bản dependency có thể tái lập, chạy cùng một lệnh kiểm tra trên mọi pull request và xử lý vi phạm như một lỗi cần được xem xét trong thay đổi mã nguồn.

### 1. Tạo một bài kiểm tra cấu trúc mô-đun

Giả sử ứng dụng có lớp khởi động tại package gốc:

```text
com.acme
├── Application.java
├── orders
│   ├── OrderService.java
│   └── internal
├── inventory
│   ├── InventoryApi.java
│   └── internal
└── customers
```

Đặt một test class gọi `ApplicationModules.of(Application.class).verify()`:

```java
package com.acme;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    @Test
    void verifiesApplicationModuleStructure() {
        ApplicationModules.of(Application.class).verify();
    }
}
```

`Application.class` là điểm bắt đầu để Spring Modulith xác định package ứng dụng và phân tích các application module. Dùng cùng một lớp gốc trong mọi môi trường giúp phạm vi kiểm tra không thay đổi theo working directory, profile hay máy chạy CI.

`verify()` kiểm tra các quy tắc kiến trúc mà mô hình Spring Modulith biết, bao gồm:

- Các application module không tạo thành dependency cycle.
- Một module chỉ truy cập API công khai của module khác, thông qua package gốc hoặc named interface được công khai.
- Các dependency tuân thủ danh sách `allowedDependencies` nếu module khai báo giới hạn đó.
- Những loại dependency được Spring Modulith nhận diện từ mã nguồn, bao gồm quan hệ phát sinh qua event listener, được đưa vào quá trình kiểm tra.

Khi có vi phạm, `verify()` ném exception chứa thông tin về các dependency không hợp lệ. JUnit xem exception đó là test failure, khiến task test trả về trạng thái thất bại và CI có thể chặn pull request.

### 2. Giữ test kiến trúc độc lập với môi trường

`ApplicationModules.of(…)` tạo mô hình từ các kiểu và metadata của mã nguồn. Bài test cấu trúc thông thường không cần khởi động Spring `ApplicationContext`. Vì vậy, không nên gắn các phụ thuộc runtime vào bài test này.

Một bài kiểm tra có tính ổn định thường có những đặc điểm sau:

| Quyết định | Cách làm ổn định | Lý do |
|---|---|---|
| Điểm bắt đầu | Truyền lớp `@SpringBootApplication` cố định | Phạm vi package được phân tích không thay đổi giữa các môi trường |
| Dữ liệu kiểm tra | Dùng metadata và cấu trúc mã nguồn | Không phụ thuộc dữ liệu bên ngoài hoặc thứ tự chạy test |
| Spring profile | Không chọn module dựa trên profile của CI | Static model không phải kết quả khởi tạo context theo profile |
| Database và dịch vụ ngoài | Không kết nối database, broker hoặc HTTP service trong test cấu trúc | Giảm lỗi do môi trường và giúp test chạy nhanh |
| Kết quả | Để vi phạm làm test thất bại | CI có thể nhận biết chính xác thay đổi phá vỡ quy tắc |

Ví dụ, tránh viết test kiến trúc chỉ chạy khi một biến môi trường được đặt:

```java
// Không nên: cùng một commit có thể được kiểm tra khác nhau
// tùy biến môi trường của máy chạy.
@Test
@EnabledIfSystemProperty(named = "RUN_ARCHITECTURE_CHECKS", matches = "true")
void verifiesModulesOnlyWhenEnabled() {
    ApplicationModules.of(Application.class).verify();
}
```

Thay vào đó, chạy test này trong bộ test mặc định. Nếu cần kiểm tra hành vi khởi tạo bean, transaction hoặc tích hợp sự kiện, tạo bài integration test riêng. Việc tách hai mục tiêu giúp lỗi kiến trúc không bị che khuất bởi một service ngoài đang tạm thời không khả dụng.

### 3. Quản lý dependency và phiên bản có thể tái lập

Test phải dùng một phiên bản Spring Modulith tương thích với Spring Boot và các thư viện khác của dự án. Nên quản lý phiên bản tập trung bằng Spring Modulith BOM hoặc cơ chế dependency management của dự án. Tránh khai báo phiên bản động như `+` hoặc `latest.release`, vì hai lần build có thể tải về các bộ thư viện khác nhau.

Ví dụ dependency Gradle khi phiên bản đã được quản lý bằng BOM:

```kotlin
dependencies {
    testImplementation("org.springframework.modulith:spring-modulith-core")
    testImplementation("org.junit.jupiter:junit-jupiter")
}
```

Nếu dự án dùng Spring Boot dependency management, hãy cấu hình BOM Spring Modulith theo hướng dẫn tương ứng với phiên bản Spring Boot đang sử dụng. Không khai báo một phiên bản Spring Modulith tùy tiện chỉ trong test source set.

Đảm bảo Gradle Wrapper hoặc Maven Wrapper được commit cùng dự án. Wrapper cố định phiên bản build tool để local và CI thực thi cùng một phiên bản Gradle hoặc Maven. Java toolchain cũng nên được khai báo rõ ràng, đồng bộ với phiên bản JDK trên CI.

Các yếu tố nên được cố định trong repository gồm:

- Phiên bản Spring Boot và Spring Modulith tương thích.
- Phiên bản JDK hoặc Java toolchain.
- Phiên bản Gradle/Maven thông qua wrapper.
- Dependency lock hoặc quy tắc dependency management nếu dự án cần kiểm soát chặt việc phân giải thư viện.
- Cấu hình test task để dùng JUnit Platform khi dự án sử dụng JUnit 5.

Ví dụ cấu hình Gradle:

```kotlin
tasks.test {
    useJUnitPlatform()
}
```

Khi các phiên bản được cố định, một thay đổi kiến trúc sẽ ít bị nhầm lẫn với khác biệt do toolchain hoặc dependency mới được tải tự động.

### 4. Chạy test kiến trúc trong CI

Đưa bài `ModularityTests` vào source set test thông thường để lệnh `test` chạy nó cùng các unit test. Với Gradle Wrapper, lệnh kiểm tra cơ bản là:

```bash
./gradlew test
```

Nếu muốn chạy riêng bài kiểm tra kiến trúc khi điều tra lỗi:

```bash
./gradlew test --tests "com.acme.ModularityTests"
```

Một workflow GitHub Actions tối giản có thể chạy cùng lệnh trên mỗi pull request:

```yaml
name: Build and architecture tests

on:
  pull_request:
  push:
    branches: [ main ]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '21'

      - uses: gradle/actions/setup-gradle@v4

      - name: Run tests
        run: ./gradlew test
```

Điều chỉnh JDK theo Java toolchain của dự án. Với môi trường yêu cầu kiểm soát chuỗi cung ứng nghiêm ngặt, hãy pin GitHub Actions theo commit SHA đã được kiểm duyệt. Có thể dùng Maven Wrapper thay cho Gradle Wrapper nếu dự án sử dụng Maven; điểm quan trọng là CI chạy đúng wrapper đã được commit.

Đặt job này thành required status check trong quy tắc bảo vệ nhánh. Như vậy, pull request không thể được merge khi test kiến trúc thất bại hoặc chưa chạy.

### 5. Tách structural verification và module integration test

Spring Modulith cung cấp nhiều mức kiểm tra. Không nên dùng một integration test nặng để thay thế việc xác minh cấu trúc.

| Loại kiểm tra | Công cụ | Mục tiêu | Phụ thuộc runtime |
|---|---|---|---|
| Kiểm tra cấu trúc | `ApplicationModules.verify()` | Ranh giới, API, dependency cycle và quy tắc phụ thuộc | Không cần khởi động application context |
| Kiểm tra module | `@ApplicationModuleTest` | Hành vi bean và tương tác trong phạm vi một module | Có khởi tạo Spring context theo bootstrap mode đã chọn |
| Kiểm tra tích hợp toàn ứng dụng | `@SpringBootTest` | Tương tác giữa nhiều thành phần và cấu hình runtime | Có thể cần database, broker hoặc dịch vụ phụ trợ |

Ví dụ kiểm tra cấu trúc nên được giữ nhỏ và nhanh:

```java
class ModularityTests {

    @Test
    void verifiesApplicationModuleStructure() {
        ApplicationModules.of(Application.class).verify();
    }
}
```

Một module integration test có thể kiểm tra hành vi của `orders` trong phạm vi module:

```java
package com.acme.orders;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.test.ApplicationModuleTest;

@ApplicationModuleTest
class OrdersModuleTests {

    @Test
    void loadsOrdersModule() {
        // Thêm assertion cho hành vi của module orders.
    }
}
```

`@ApplicationModuleTest` khởi tạo Spring context theo phạm vi module và chế độ bootstrap được cấu hình. Nếu test cần dependency bên ngoài module, hãy khai báo rõ cách đưa dependency đó vào context hoặc chọn bootstrap mode phù hợp. Tránh biến test cấu trúc thành bài test phụ thuộc database chỉ để xác minh một quy tắc package.

### 6. Xử lý vi phạm kiến trúc có chủ đích

Khi test thất bại, không nên tắt test, bắt exception rồi bỏ qua, hoặc thêm điều kiện để CI luôn xanh. Hãy đọc dependency được báo cáo, xác định module nào đang truy cập thành phần nào và sửa thiết kế hoặc khai báo hợp đồng phù hợp.

Ví dụ, nếu `orders` cần gọi API của `inventory`, hãy đặt interface cần dùng trong package công khai của `inventory`. Nếu API được tổ chức trong package riêng, đánh dấu named interface để Spring Modulith nhận diện đúng. Nếu một dependency giữa hai module là một phần của thiết kế được chấp thuận, khai báo nó trong `allowedDependencies` của module phụ thuộc và xem xét liệu hợp đồng đó có nên được công khai qua named interface hay không.

Khi xuất hiện dependency cycle, hãy xem lại chiều phụ thuộc và trách nhiệm nghiệp vụ. Với giao tiếp bất đồng bộ, có thể chuyển sang mô hình phát hành domain event và xử lý qua listener nếu phù hợp với nghiệp vụ. Lưu ý rằng listener cũng tạo ra quan hệ dependency mà Spring Modulith có thể nhận diện; event không làm biến mất mọi quan hệ kiến trúc.

Mọi ngoại lệ kiến trúc cần được biểu đạt bằng cấu hình hoặc API rõ ràng, có lý do và được review cùng thay đổi. Không nên tạo một danh sách bỏ qua chung trong test vì nó làm mất ý nghĩa của required status check.

### 7. Chẩn đoán lỗi CI và tái hiện ở local

Khi CI báo test kiến trúc thất bại, thực hiện theo thứ tự sau:

1. Chạy đúng lệnh wrapper của CI tại local, với cùng JDK và profile build.
2. Đọc danh sách dependency vi phạm do `verify()` báo cáo.
3. Kiểm tra package của kiểu được truy cập, API package và named interface của module đích.
4. Kiểm tra `allowedDependencies` nếu module đã giới hạn dependency.
5. Sửa quan hệ phụ thuộc hoặc cập nhật hợp đồng module, rồi chạy lại test.

Nếu local pass nhưng CI fail, so sánh phiên bản JDK, wrapper, dependency lock, commit đang được build và source set được biên dịch. Kiểm tra cả việc CI có đang chạy một profile hoặc task khác với local hay không. Với lỗi nghi ngờ do output build cũ, chạy lại từ trạng thái sạch bằng wrapper, ví dụ `./gradlew clean test`, sau khi xác nhận vấn đề có thể tái hiện.

Đừng chỉ dựa vào việc một lần chạy local thành công. Required check cần chạy trên chính commit được đề xuất merge và lưu log test để reviewer xem được nguyên nhân nếu thất bại.

### 8. Checklist cho một pipeline ổn định

- [ ] Có một bài `ModularityTests` gọi `ApplicationModules.of(Application.class).verify()`.
- [ ] Lớp ứng dụng gốc được chỉ định rõ ràng và thống nhất.
- [ ] Bài kiểm tra cấu trúc không cần database, broker hoặc biến môi trường tùy chọn.
- [ ] Phiên bản Spring Modulith, Spring Boot, JDK và build tool được quản lý nhất quán.
- [ ] CI chạy wrapper của repository trên pull request.
- [ ] Architecture test là required status check.
- [ ] Vi phạm được sửa bằng thay đổi thiết kế hoặc khai báo dependency có chủ đích.
- [ ] Integration test của module được tổ chức riêng với structural verification.

Khi được duy trì theo cách này, test kiến trúc trở thành một phần thường xuyên của vòng đời pull request. Nhóm có thể phát hiện sớm dependency cycle, truy cập API nội bộ và dependency ngoài hợp đồng, trong khi kết quả CI vẫn dễ tái hiện và không phụ thuộc vào các dịch vụ runtime không liên quan.

### Tài liệu tham khảo

- [Spring Modulith — Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html)
- [Spring Modulith — Testing Application Modules](https://docs.spring.io/spring-modulith/reference/testing.html)
- [Spring Modulith — Fundamentals](https://docs.spring.io/spring-modulith/reference/fundamentals.html)
- [Spring Boot — Build Systems and Dependency Management](https://docs.spring.io/spring-boot/reference/using/build-systems.html)
- [GitHub Actions — Building and testing Java with Gradle](https://docs.github.com/en/actions/automating-builds-and-tests/building-and-testing-java-with-gradle)
