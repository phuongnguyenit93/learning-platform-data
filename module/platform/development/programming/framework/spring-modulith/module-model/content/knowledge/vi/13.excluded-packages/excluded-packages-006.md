# Loại trừ generated code có kiểm soát

Code được sinh tự động từ OpenAPI, Protocol Buffers, jOOQ hoặc công cụ mapping thường chứa nhiều class phục vụ kỹ thuật. Những class này có thể làm kết quả kiểm tra kiến trúc khó đọc, tạo thêm dependency mà nhóm không trực tiếp thiết kế hoặc khiến mô hình module phản ánh cấu trúc của generator thay vì ranh giới nghiệp vụ. Spring Modulith cho phép truyền một predicate để loại một số Java type hoặc package khỏi quá trình application module inspection.

Trong phạm vi **SPRING_MODULITH_MODULE_MODEL**, việc loại trừ generated code cần có phạm vi rõ ràng. Ta muốn giảm nhiễu do mã được sinh, đồng thời vẫn kiểm tra các module nghiệp vụ và các hợp đồng mà chúng thực sự sử dụng. Loại trừ quá rộng có thể che khuất dependency quan trọng; loại trừ có kiểm soát giúp giữ mô hình `ApplicationModules` tập trung vào phần kiến trúc mà nhóm chịu trách nhiệm.

## 1. Vì sao generated code có thể gây nhiễu?

Một ứng dụng Spring Boot có thể chứa các nhóm code được tạo bởi công cụ:

| Nguồn sinh code | Ví dụ kiểu được tạo | Đặc điểm thường gặp |
|---|---|---|
| OpenAPI Generator | API client, request/response model, delegate interface | Nhiều DTO và interface phản ánh schema HTTP |
| Protocol Buffers / gRPC | message, builder, stub | Nhiều class lồng nhau và kiểu hỗ trợ serialization |
| jOOQ | record, table, DAO, routine | Kiểu Java phản ánh schema database và metadata SQL |
| JAXB / XSD | XML binding classes | Class và annotation phản ánh cấu trúc XML |
| MapStruct | mapper implementation | Implementation được tạo trong quá trình compile |

Ví dụ, package của một module có thể trông như sau:

```text
com.acme.shop
└── orders
    ├── OrderManagement.java
    ├── api
    │   └── OrderFacade.java
    ├── internal
    │   └── OrderRepository.java
    └── generated
        ├── OrderApi.java
        ├── CreateOrderRequest.java
        └── CreateOrderResponse.java
```

Các class trong `generated` có thể được tạo lại mỗi lần schema hoặc specification thay đổi. Nếu chúng không phải là hợp đồng kiến trúc mà nhóm muốn kiểm tra, việc đưa tất cả vào phân tích module có thể làm tăng nhiễu trong dependency report. Trường hợp khác là code generator tạo package cấp cao riêng, khiến package đó bị nhận diện như một application module theo cấu trúc package mặc định.

Không phải mọi generated code đều cần loại trừ. Một kiểu được sinh tự động vẫn có thể là API nghiệp vụ mà module khác chủ động sử dụng. Quyết định cần dựa vào vai trò của kiểu đó trong kiến trúc, không chỉ dựa vào việc nó được tạo bằng công cụ.

## 2. Exclusion predicate của ApplicationModules

Spring Modulith cung cấp overload nhận `DescribedPredicate` để chỉ định Java type và package cần bỏ qua khi tạo mô hình:

```java
import com.tngtech.archunit.core.domain.JavaClass;
import org.springframework.modulith.core.ApplicationModules;

var generatedCode = JavaClass.Predicates.resideInAPackage(
    "com.acme.shop.orders.generated.."
);

ApplicationModules modules = ApplicationModules.of(
    ShopApplication.class,
    generatedCode
);

modules.verify();
```

`JavaClass.Predicates.resideInAPackage(...)` tạo predicate dựa trên tên package theo cú pháp matcher của ArchUnit. `ApplicationModules.of(ShopApplication.class, generatedCode)` dùng predicate đó để loại các kiểu phù hợp khỏi application module inspection. Sau đó `verify()` kiểm tra mô hình đã áp dụng exclusion.

Đây là cấu hình cho mô hình kiến trúc được tạo bởi Spring Modulith. Nó không xóa source file, không bỏ class khỏi output build và không thay đổi package mà Spring Boot component scanning nhìn thấy. Generated code vẫn được compiler và runtime sử dụng theo cấu hình thông thường của ứng dụng.

## 3. Hiểu chính xác package pattern

Pattern package quyết định phạm vi bị loại. Hai cách viết gần giống nhau có kết quả khác nhau:

| Pattern | Phạm vi khớp | Khi dùng |
|---|---|---|
| `com.acme.shop.generated` | Chỉ package `com.acme.shop.generated` | Generated type đều nằm ngay trong package này |
| `com.acme.shop.generated..` | Package `generated` và mọi package con | Generator tạo thêm package con như `generated.dto` hoặc `generated.client` |
| `com.acme.shop.orders.generated..` | Chỉ generated code thuộc module `orders` | Muốn loại code sinh của một module cụ thể |
| `..generated..` | Các package có segment `generated` ở nhiều vị trí trong cây package | Chỉ dùng khi quy ước đặt tên được áp dụng nhất quán và không có package hợp lệ trùng tên |

Ví dụ, nếu code sinh nằm ở:

```text
com.acme.shop.orders.generated
com.acme.shop.orders.generated.dto
com.acme.shop.inventory.generated.client
```

thì pattern `com.acme.shop.orders.generated..` loại package `orders.generated` cùng các package con của nó. Nó không loại `inventory.generated.client`.

Để tránh loại nhầm, hãy bắt đầu bằng package đầy đủ có phạm vi hẹp. Pattern tổng quát như `..generated..` tiện lợi nhưng có thể khớp cả package được nhóm sử dụng có chủ đích nếu package đó cũng mang tên `generated`.

## 4. Loại trừ nhiều package generated

Nếu nhiều generator tạo code ở các package riêng, dùng `resideInAnyPackage(...)`:

```java
import com.tngtech.archunit.core.domain.JavaClass;
import org.springframework.modulith.core.ApplicationModules;

var generatedCode = JavaClass.Predicates.resideInAnyPackage(
    "com.acme.shop.orders.generated..",
    "com.acme.shop.inventory.generated..",
    "com.acme.shop.persistence.jooq..",
    "com.acme.shop.integration.grpc.generated.."
);

ApplicationModules modules = ApplicationModules.of(
    ShopApplication.class,
    generatedCode
);

modules.verify();
```

Predicate khớp một trong các package được liệt kê sẽ được xem là cần loại trừ. Cách này dễ rà soát hơn việc viết một pattern rộng cho toàn bộ ứng dụng, vì mỗi package generated đều có thể được giải thích theo generator hoặc module sở hữu.

Nếu chỉ có một package cần loại, `resideInAPackage(...)` là đủ. Nếu có nhiều package, giữ danh sách trong một hằng số hoặc helper dùng chung để verification, architecture test và các tác vụ phân tích khác sử dụng cùng quy tắc.

## 5. Ví dụ với OpenAPI Generator trong một module

Giả sử `orders` dùng OpenAPI Generator để tạo DTO và API interface từ file specification. Phần nghiệp vụ do nhóm viết nằm ngoài package `generated`:

```text
com.acme.shop.orders
├── OrderManagement.java
├── api
│   └── OrderFacade.java
├── internal
│   └── PlaceOrderService.java
└── generated
    ├── api
    │   └── OrdersApi.java
    └── model
        ├── CreateOrderRequest.java
        └── CreateOrderResponse.java
```

Ta có thể loại riêng package được sinh:

```java
var generatedCode = JavaClass.Predicates.resideInAPackage(
    "com.acme.shop.orders.generated.."
);

ApplicationModules modules = ApplicationModules.of(
    ShopApplication.class,
    generatedCode
);

modules.verify();
```

Trong trường hợp này, `OrderManagement`, `OrderFacade` và `PlaceOrderService` vẫn nằm trong mô hình. Các class generated bị bỏ khỏi phần inspection theo predicate. Nếu `CreateOrderRequest` là hợp đồng mà module khác phải sử dụng trực tiếp, hãy cân nhắc đặt hợp đồng đó trong package API do nhóm quản lý hoặc không loại nó khỏi inspection. Không nên loại một kiểu công khai chỉ vì nó có nguồn gốc từ generator.

## 6. Generated code không có package riêng

Một số generator ghi class vào cùng package với code viết tay. Khi đó, loại cả package sẽ bỏ luôn các class nghiệp vụ trong package đó. Ví dụ:

```text
com.acme.shop.orders
├── OrderManagement.java              // handwritten
├── OrderController.java               // handwritten
├── CreateOrderRequestGenerated.java   // generated
└── CreateOrderResponseGenerated.java  // generated
```

Trong tình huống này, không nên dùng `resideInAPackage("com.acme.shop.orders")`, vì nó sẽ khớp cả class viết tay. Ưu tiên cấu hình generator ghi output vào package riêng như `com.acme.shop.orders.generated`.

Nếu không thể thay đổi package đầu ra, có thể xây dựng predicate theo quy ước tên class hoặc marker annotation ổn định mà generator tạo ra. Trước khi dựa vào annotation, hãy kiểm tra retention của annotation và bảo đảm metadata còn tồn tại trong class file mà ArchUnit đọc được. Annotation chỉ tồn tại ở source level sẽ không đủ để nhận diện class từ bytecode.

Predicate theo tên class cũng cần thận trọng: hậu tố `Generated` có thể được dùng bởi class viết tay hoặc không được áp dụng nhất quán cho mọi output của generator. Hãy có test xác nhận predicate khớp đúng các class dự kiến và không loại nhầm class nghiệp vụ.

## 7. Không nhầm exclusion với các cơ chế lọc khác

Spring Modulith và ArchUnit có một số cơ chế khác nhau, mỗi cơ chế kiểm soát một phạm vi riêng:

| Cơ chế | Phạm vi tác động | Ví dụ |
|---|---|---|
| `ApplicationModules.of(..., ignored)` | Java type/package được đưa vào application module inspection | Bỏ package generated khỏi mô hình module |
| ArchUnit `ImportOption` | Nguồn class file được ArchUnit import | Loại một nhóm location hoặc classpath entry khỏi lần import |
| Maven/Gradle source set hoặc plugin | Quá trình sinh code và biên dịch | Cấu hình output directory của OpenAPI Generator |
| Spring component scanning | Bean được phát hiện và đăng ký trong application context | `@ComponentScan`, `@SpringBootApplication` |
| Java access modifier | Khả năng truy cập kiểu/thành viên ở cấp ngôn ngữ | `public`, package-private, `private` |

Loại package bằng `ApplicationModules.of(..., ignored)` không ngăn Spring tạo bean, không thay đổi Java visibility và không làm generator ngừng chạy. Nếu muốn thay đổi build output hoặc component scanning, phải dùng cấu hình tương ứng của build tool hoặc Spring Boot.

## 8. Rủi ro khi loại trừ quá rộng

Exclusion làm giảm phạm vi code mà mô hình kiến trúc xem xét. Nếu loại nhầm code nghiệp vụ hoặc một hợp đồng công khai, một số dependency có thể không còn được kiểm tra đầy đủ.

Các rủi ro thường gặp:

- **Che dependency xuyên module:** code viết tay tham chiếu generated type thuộc module khác, nhưng generated type bị loại khỏi inspection nên quan hệ đó không còn được phản ánh đầy đủ.
- **Che API không được quản lý:** consumer sử dụng trực tiếp generated DTO hoặc repository mà nhóm chưa xác định là hợp đồng công khai.
- **Loại cả module:** nếu package generated nằm ở cấp module và toàn bộ package bị loại, module đó có thể không còn xuất hiện trong mô hình.
- **Pattern khớp nhầm:** `..generated..` có thể loại package hợp lệ ở một module khác.
- **Quy tắc lỗi thời:** generator đổi package nhưng predicate không được cập nhật, khiến code mới lọt vào inspection hoặc code cũ vẫn bị loại sai.

Vì vậy, chỉ loại những package mà nhóm có thể chứng minh là chi tiết sinh tự động nằm ngoài ranh giới cần kiểm chứng. Nếu generated code tạo ra API được các module khác phụ thuộc, hãy quản lý API đó như hợp đồng thật hoặc bọc nó bằng facade/adapter do module sở hữu cung cấp.

## 9. Kiểm thử để bảo vệ exclusion predicate

Không nên chỉ xác nhận `verify()` không ném exception. Hãy kiểm tra các class quan trọng vẫn nằm trong mô hình và class generated dự kiến đã bị loại:

```java
import static org.assertj.core.api.Assertions.assertThat;

import com.tngtech.archunit.core.domain.JavaClass;
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModuleInspectionTests {

    private static final ApplicationModules MODULES = ApplicationModules.of(
        ShopApplication.class,
        JavaClass.Predicates.resideInAnyPackage(
            "com.acme.shop.orders.generated..",
            "com.acme.shop.persistence.jooq.."
        )
    );

    @Test
    void keepsHandwrittenTypesInTheModel() {
        assertThat(MODULES.contains(OrderManagement.class)).isTrue();
        assertThat(MODULES.contains(InventoryOperations.class)).isTrue();
    }

    @Test
    void ignoresGeneratedTypesFromInspection() {
        assertThat(MODULES.contains(CreateOrderRequest.class)).isFalse();
        assertThat(MODULES.contains(OrdersRecord.class)).isFalse();
    }

    @Test
    void verifiesTheRemainingModuleStructure() {
        MODULES.verify();
    }
}
```

Ví dụ giả định `CreateOrderRequest` nằm trong package `orders.generated` và `OrdersRecord` nằm trong package `persistence.jooq`. `contains(Class<?>)` cho biết type có thuộc mô hình `ApplicationModules` hay không. Các assertion giúp phát hiện khi generator đổi package hoặc khi predicate vô tình loại class viết tay.

Nên giữ cùng predicate trong một helper hoặc factory để các test kiến trúc không tự định nghĩa danh sách package khác nhau:

```java
final class ModuleInspection {

    private ModuleInspection() {}

    static ApplicationModules create() {
        return ApplicationModules.of(
            ShopApplication.class,
            JavaClass.Predicates.resideInAnyPackage(
                "com.acme.shop.orders.generated..",
                "com.acme.shop.persistence.jooq.."
            )
        );
    }
}
```

Khi package generated thay đổi, cập nhật một nơi và chạy lại các test kiểm tra inclusion/exclusion cùng `verify()`.

## 10. Quy trình áp dụng exclusion có kiểm soát

Khi thêm một generator hoặc điều chỉnh output package, hãy thực hiện theo thứ tự:

1. **Xác định output thực tế.** Ghi nhận package của các class được sinh và package của class viết tay.
2. **Phân loại vai trò.** Xác định generated type nào chỉ là adapter/DTO kỹ thuật và kiểu nào là API được module khác sử dụng.
3. **Ưu tiên package riêng.** Cấu hình generator ghi output vào package có tên rõ ràng như `generated`, `jooq` hoặc `protobuf` bên trong module sở hữu.
4. **Viết predicate hẹp.** Dùng `resideInAPackage` cho một package hoặc `resideInAnyPackage` cho một danh sách package cụ thể; chỉ dùng pattern rộng khi quy ước toàn dự án bảo đảm an toàn.
5. **Tạo mô hình với predicate.** Truyền predicate vào overload `ApplicationModules.of(...)` được dùng trong architecture test.
6. **Kiểm tra type được giữ và type bị loại.** Assertion `contains(...)` cho cả hai nhóm.
7. **Chạy verification.** Gọi `verify()` trên mô hình đã áp dụng exclusion.
8. **Rà soát khi generator đổi phiên bản.** Kiểm tra package output và cập nhật predicate nếu cấu trúc generated code thay đổi.
9. **Ghi lý do loại trừ.** Tài liệu hóa generator, package, owner và phạm vi exclusion để nhóm khác không mở rộng pattern một cách tùy tiện.

## 11. Checklist trước khi chấp nhận generated package exclusion

- [ ] Package generated có quy ước tên riêng và không trộn với class viết tay.
- [ ] Pattern dùng đúng package đầy đủ và phạm vi `..` cần thiết.
- [ ] Không loại nhầm module hoặc API nghiệp vụ được công khai.
- [ ] Generated type không bị consumer phụ thuộc trực tiếp ngoài ý muốn.
- [ ] `ApplicationModules.contains(...)` xác nhận type viết tay vẫn được giữ.
- [ ] `ApplicationModules.contains(...)` xác nhận generated type mục tiêu bị loại.
- [ ] `ApplicationModules.verify()` chạy trên mô hình đã áp dụng predicate.
- [ ] Predicate được dùng thống nhất trong các architecture test liên quan.
- [ ] Có người sở hữu việc cập nhật predicate khi generator hoặc package output thay đổi.

## Kết luận

Spring Modulith cho phép loại Java type hoặc package khỏi application module inspection bằng overload `ApplicationModules.of(...)` nhận `DescribedPredicate`. Với generated code, hãy ưu tiên package output riêng, dùng pattern hẹp và kiểm tra rõ kiểu nào được giữ hoặc bị loại. Exclusion chỉ tác động đến mô hình kiểm tra kiến trúc; nó không xóa code, bỏ compile hay ngăn Spring component scanning. Hãy bảo vệ các module và hợp đồng nghiệp vụ bằng assertion `contains(...)` cùng `verify()`, đồng thời rà soát predicate mỗi khi generator thay đổi cấu trúc package.

## Tài liệu tham khảo

- [Spring Modulith — Fundamentals: Excluding Packages](https://docs.spring.io/spring-modulith/reference/fundamentals.html#modules.excluding-packages)
- [Javadoc: ApplicationModules](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModules.html)
- [ArchUnit — JavaClass.Predicates](https://www.javadoc.io/doc/com.tngtech.archunit/archunit/latest/com/tngtech/archunit/core/domain/JavaClass.Predicates.html)
- [ArchUnit — PackageMatcher](https://www.javadoc.io/doc/com.tngtech.archunit/archunit/latest/com/tngtech/archunit/core/domain/PackageMatcher.html)
