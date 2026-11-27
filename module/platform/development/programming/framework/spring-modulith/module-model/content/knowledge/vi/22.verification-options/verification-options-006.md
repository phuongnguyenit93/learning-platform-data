# VerificationDepth và mức nghiêm ngặt

`VerificationDepth` là lựa chọn mức độ nghiêm ngặt của các quy tắc kiến trúc Hexagonal do jMolecules cung cấp và Spring Modulith có thể tích hợp vào quá trình verification. Hai mức thường dùng là `LENIENT` và `STRICT`: mức lenient phù hợp khi nhóm đang đưa stereotype và port/adapter vào codebase hiện có; mức strict áp dụng các ràng buộc chặt hơn khi cấu trúc đã được tổ chức rõ.

Điều quan trọng là phân biệt hai lớp kiểm tra. `ApplicationModules.verify()` kiểm tra ranh giới application module của Spring Modulith, như dependency cycle, truy cập package nội bộ và `allowedDependencies`. `VerificationDepth` điều chỉnh quy tắc Hexagonal của jMolecules; nó không thay đổi độ sâu duyệt dependency của module graph và cũng không thay thế các kiểm tra cốt lõi của Spring Modulith.

Trong phạm vi **SPRING_MODULITH_MODULE_MODEL**, hai cơ chế này bổ sung cho nhau: Spring Modulith bảo vệ ranh giới giữa `orders`, `inventory`, `customers`; jMolecules kiểm tra cách các lớp bên trong một vùng code tuân theo vai trò application, port và adapter.

## 1. VerificationDepth thuộc jMolecules, không phải Spring Modulith core

`VerificationDepth` nằm trong API của jMolecules ArchUnit, thuộc package `org.jmolecules.archunit`. Nó được dùng khi tạo quy tắc kiến trúc, ví dụ quy tắc Hexagonal Architecture qua `JMoleculesArchitectureRules.ensureHexagonal(...)`.

Không nhầm `VerificationDepth` với:

- `ApplicationModules.verify()`: phương thức chạy các kiểm tra cấu trúc application module.
- `VerificationOptions`: cấu hình các kiểm tra bổ sung mà `ApplicationModules.verify(...)` hoặc `detectViolations(...)` thực thi.
- Dependency depth hoặc direct/transitive dependency: cách truy vấn các cạnh trong đồ thị module.

`VerificationDepth` điều chỉnh mức chặt của một nhóm quy tắc jMolecules. Nếu dự án không có jMolecules ArchUnit và các stereotype Hexagonal tương ứng trên classpath, cấu hình này không tự tạo ra các kiểm tra Hexagonal.

## 2. LENIENT và STRICT

API `VerificationDepth` cung cấp hai lựa chọn chính:

| Mức | Ý nghĩa thực hành | Khi phù hợp |
|---|---|---|
| `LENIENT` | Áp dụng quy tắc Hexagonal theo hướng khoan dung hơn, cho phép một số cách tổ chức hoặc tham chiếu chuyển tiếp khi code chưa được gắn stereotype đầy đủ | Bắt đầu áp dụng jMolecules cho legacy codebase hoặc migration theo từng module |
| `STRICT` | Siết các hướng dependency giữa application, port và adapter; giảm các đường truy cập trực tiếp không đi qua vai trò kiến trúc được khai báo | Codebase đã có ranh giới Hexagonal rõ và nhóm muốn ngăn regression chặt hơn |

Đây không phải thang đo chất lượng chung cho toàn ứng dụng. Nó quyết định mức ràng buộc của quy tắc Hexagonal được tạo ra. Một module có thể vượt qua kiểm tra Spring Modulith nhưng vẫn không vượt qua quy tắc Hexagonal strict, vì hai bộ quy tắc xem xét những khía cạnh khác nhau.

`LENIENT` không có nghĩa là bỏ qua mọi vi phạm. Nó vẫn kiểm tra những quan hệ mà quy tắc cho phép xác định rõ, chẳng hạn vai trò của primary adapter, secondary adapter và các port. Các kiểu chưa được gắn stereotype hoặc các lối đi trực tiếp được nới lỏng có thể được chấp nhận tùy theo phiên bản jMolecules và cách các lớp được phân loại.

Không nên diễn giải `LENIENT` thành “bỏ qua mọi class chưa có annotation”. Mỗi phiên bản jMolecules xây dựng tập layer được phép cho primary/secondary roles theo `VerificationDepth`; hãy đối chiếu Javadoc của đúng phiên bản và đọc nội dung violation thay vì suy luận chỉ từ tên mức.

`STRICT` cũng không tự sửa kiến trúc. Khi nâng từ lenient lên strict, các dependency vốn được chấp nhận trước đó có thể trở thành vi phạm. Nhóm cần đọc từng đường tham chiếu, xác định port còn thiếu hoặc stereotype chưa đúng, rồi điều chỉnh code.

## 3. Các vai trò Hexagonal mà quy tắc kiểm tra

jMolecules cung cấp stereotype để mô tả vai trò của các thành phần trong Hexagonal Architecture:

| Vai trò | Annotation tiêu biểu | Trách nhiệm |
|---|---|---|
| Application | `@Application` | Điều phối use case và quy tắc ứng dụng |
| Port | `@Port` | Hợp đồng giao tiếp giữa lõi ứng dụng và bên ngoài |
| Primary port | `@PrimaryPort` | Điểm vào use case từ actor hoặc hệ thống bên ngoài |
| Secondary port | `@SecondaryPort` | Hợp đồng mà lõi ứng dụng cần để gọi năng lực bên ngoài |
| Adapter | `@Adapter` | Thành phần kết nối ứng dụng với một công nghệ hoặc actor |
| Primary adapter | `@PrimaryAdapter` | Đưa yêu cầu từ HTTP, messaging, CLI hoặc actor khác vào primary port |
| Secondary adapter | `@SecondaryAdapter` | Triển khai secondary port bằng database, HTTP client, broker hoặc hệ thống ngoài |

Ví dụ về các kiểu trong module `orders` (mỗi kiểu được đặt trong file Java riêng):

```java
package com.acme.shop.orders;

import org.jmolecules.architecture.hexagonal.PrimaryPort;

@PrimaryPort
public interface PlaceOrder {

    void place(String orderId);
}
```

```java
package com.acme.shop.orders;

import org.jmolecules.architecture.hexagonal.SecondaryPort;

@SecondaryPort
public interface OrderRepository {

    void save(String orderId);
}
```

```java
package com.acme.shop.orders;

import org.jmolecules.architecture.hexagonal.Application;

@Application
public class PlaceOrderService implements PlaceOrder {

    private final OrderRepository repository;

    public PlaceOrderService(OrderRepository repository) {
        this.repository = repository;
    }

    @Override
    public void place(String orderId) {
        repository.save(orderId);
    }
}
```

Primary adapter có thể là controller gọi `PlaceOrder`; secondary adapter triển khai `OrderRepository` bằng JPA hoặc JDBC. Quy tắc Hexagonal kiểm tra các kiểu phụ thuộc giữa những vai trò này theo mức depth đã chọn.

## 4. Chọn LENIENT khi đang chuyển đổi dần

Một codebase cũ có thể chưa có đủ port. Ví dụ controller đang gọi application service trực tiếp, hoặc application service còn tham chiếu một số thành phần chưa được tách thành secondary port. Việc áp dụng strict ngay lập tức có thể tạo ra nhiều vi phạm cùng lúc và làm khó xác định thứ tự migration.

Có thể bắt đầu bằng `LENIENT` để đưa kiểm tra Hexagonal vào pipeline, sau đó xử lý các vùng code theo từng bước:

1. Gắn stereotype cho application, primary/secondary ports và adapters đã có vai trò rõ.
2. Xác định các dependency đang đi trực tiếp qua ranh giới mà lẽ ra cần một port.
3. Tách interface cần thiết về phía lõi ứng dụng.
4. Chuyển adapter hiện tại sang triển khai port.
5. Chạy lại verification và theo dõi số vi phạm còn lại.
6. Khi các đường dependency quan trọng đã rõ, chuyển cấu hình sang `STRICT`.

Ví dụ, trong giai đoạn đầu có thể dùng:

```java
import org.jmolecules.archunit.JMoleculesArchitectureRules;
import org.jmolecules.archunit.VerificationDepth;
import org.springframework.modulith.core.ApplicationModules;
import org.springframework.modulith.core.VerificationOptions;

var hexagonal = JMoleculesArchitectureRules.ensureHexagonal(
    VerificationDepth.LENIENT
);

var options = VerificationOptions.defaults()
    .withAdditionalVerifications(hexagonal);

ApplicationModules.of(ShopApplication.class).verify(options);
```

Ví dụ này dùng overload nhận `VerificationDepth` được các tài liệu Spring Modulith trước đây minh họa. Trong jMolecules từ 0.34, overload tiện ích này đã deprecated để chuyển sang `HexagonalVerificationOptions`; phần tiếp theo trình bày cách dùng API mới.

## 5. Dùng STRICT với API jMolecules hiện hành

Với jMolecules ArchUnit từ 0.34, nên tạo `HexagonalVerificationOptions`, đặt depth rồi truyền options vào `ensureHexagonal(...)`:

```java
import org.jmolecules.archunit.HexagonalVerificationOptions;
import org.jmolecules.archunit.JMoleculesArchitectureRules;
import org.jmolecules.archunit.VerificationDepth;
import org.springframework.modulith.core.ApplicationModules;
import org.springframework.modulith.core.VerificationOptions;

var hexagonalOptions = HexagonalVerificationOptions.defaults()
    .withDepth(VerificationDepth.STRICT);

var hexagonal = JMoleculesArchitectureRules.ensureHexagonal(hexagonalOptions);

var verificationOptions = VerificationOptions.defaults()
    .withAdditionalVerifications(hexagonal);

ApplicationModules.of(ShopApplication.class).verify(verificationOptions);
```

Trong ví dụ này:

1. `HexagonalVerificationOptions.defaults()` tạo cấu hình mặc định cho bộ kiểm tra Hexagonal.
2. `withDepth(VerificationDepth.STRICT)` chọn mức nghiêm ngặt.
3. `ensureHexagonal(...)` tạo ArchUnit rule tương ứng.
4. `VerificationOptions.defaults().withAdditionalVerifications(...)` gắn rule đó vào lần kiểm tra application module.
5. `verify(verificationOptions)` chạy kiểm tra Spring Modulith cùng rule bổ sung.

Khi dự án vẫn dùng jMolecules phiên bản cũ, kiểm tra Javadoc của dependency thực tế trước khi áp dụng API options mới. Không trộn ví dụ cũ và mới nếu classpath không có đúng phiên bản.

## 6. Phân biệt kiểm tra module và kiểm tra Hexagonal

Hai bộ quy tắc cùng chạy trong một lần verification nhưng bảo vệ các ranh giới khác nhau:

| Nội dung | Spring Modulith core | jMolecules Hexagonal với VerificationDepth |
|---|---|---|
| Dependency cycle giữa application module | Có | Không phải mục tiêu chính |
| Truy cập package nội bộ của module `CLOSED` | Có | Không thay thế quy tắc này |
| `allowedDependencies` | Có | Không thay thế allowlist module |
| Vai trò application, primary/secondary port, adapter | Không phân loại chi tiết theo stereotype Hexagonal | Có |
| Mức lenient/strict | Không dùng `VerificationDepth` | Có |
| Đơn vị kiểm tra | Application module và package | Quan hệ giữa các lớp theo stereotype kiến trúc |

Ví dụ, `orders` có thể chỉ phụ thuộc vào `inventory::api` và không tạo chu kỳ nên vượt qua các quy tắc module. Nhưng nếu controller trong `orders` gọi trực tiếp một secondary adapter thay vì đi qua primary port/application flow theo quy tắc Hexagonal, jMolecules vẫn có thể báo vi phạm.

Ngược lại, một cấu trúc lớp có thể tuân thủ các quy tắc Hexagonal nhưng `orders` lại import package `inventory.internal` của module `CLOSED`. Khi đó, Spring Modulith vẫn báo vi phạm module boundary.

## 7. jMolecules có thể được kích hoạt tự động theo classpath

Spring Modulith có thể tích hợp các quy tắc jMolecules ArchUnit. Tùy cấu hình và phiên bản dependency, các kiểm tra bổ sung được phát hiện từ classpath có thể tự động tham gia `ApplicationModules.verify()`.

Điều này có một số hệ quả:

- Thêm jMolecules ArchUnit hoặc các annotation kiến trúc có thể làm test verification bắt đầu phát hiện thêm vi phạm.
- Một test trước đây chỉ kiểm tra module boundary có thể thất bại vì quy tắc DDD hoặc Hexagonal được kích hoạt bổ sung.
- Cần đọc loại vi phạm và rule tạo ra nó để biết nên sửa package/module hay sửa vai trò của lớp.
- Không nên tắt tất cả additional verifications chỉ để làm test pass nếu mục tiêu của dự án là bảo vệ cả module và kiến trúc Hexagonal.

Nếu cần kiểm soát rõ những rule nào được chạy, tạo `VerificationOptions` tường minh. Có thể thêm rule Hexagonal cụ thể bằng `withAdditionalVerifications(...)`. Một số phiên bản cũng cung cấp lựa chọn loại bỏ additional verifications; chỉ dùng khi nhóm chủ động tách phạm vi kiểm tra và vẫn có test riêng cho các quy tắc đã bỏ.

## 8. Đọc và xử lý vi phạm khi tăng mức nghiêm ngặt

Khi chuyển từ `LENIENT` sang `STRICT`, đừng chỉ nhìn số lượng lỗi. Hãy phân loại theo hướng dependency:

| Dấu hiệu trong vi phạm | Câu hỏi cần đặt ra | Hướng xử lý thường gặp |
|---|---|---|
| Primary adapter tham chiếu trực tiếp implementation | Adapter có gọi đúng primary port không? | Đưa lời gọi qua primary port/use case |
| Application service tham chiếu concrete database adapter | Lõi ứng dụng có đang phụ thuộc công nghệ lưu trữ không? | Tạo secondary port và để adapter triển khai |
| Secondary adapter phụ thuộc ngược vào application implementation | Adapter có đang điều phối use case không? | Chuyển điều phối về application service hoặc port phù hợp |
| Class không có stereotype bị phân loại sai | Vai trò của class có rõ không? | Bổ sung stereotype hoặc sắp xếp lại package/role |
| Dependency giữa hai module sai API | Đây là vi phạm package boundary hay Hexagonal? | Kiểm tra cả `NamedInterface`, `allowedDependencies` và port/adapter |

Một vi phạm không phải lúc nào cũng được giải quyết bằng cách thêm annotation. Stereotype cần phản ánh đúng trách nhiệm thực tế. Nếu một class vừa là adapter vừa chứa use case, có thể cần tách trách nhiệm thay vì gắn thêm nhiều annotation.

Có thể gọi `detectViolations()` để lấy kết quả vi phạm phục vụ báo cáo hoặc lọc theo chính sách:

```java
var violations = ApplicationModules.of(ShopApplication.class)
    .detectViolations(verificationOptions);

System.out.println(violations);
violations.throwIfPresent();
```

`detectViolations(options)` thực thi kiểm tra với options đã chọn và trả về tập vi phạm. `throwIfPresent()` làm test thất bại nếu vẫn còn vi phạm. Trong pipeline chính, nên giữ hành vi fail khi có vi phạm không được chấp nhận.

## 9. Lộ trình nâng từ LENIENT lên STRICT

Có thể chia migration thành các giai đoạn có thể kiểm soát:

1. **Thiết lập baseline.** Bật rule Hexagonal ở mức `LENIENT` và lưu lại nhóm vi phạm ban đầu.
2. **Chuẩn hóa stereotype.** Gắn `@Application`, `@PrimaryPort`, `@SecondaryPort`, `@PrimaryAdapter` và `@SecondaryAdapter` theo đúng vai trò.
3. **Tách port.** Chuyển dependency từ application core tới công nghệ bên ngoài qua secondary port.
4. **Tách adapter.** Đảm bảo controller, message listener và adapter database không trộn lẫn use case với chi tiết tích hợp.
5. **Giải quyết vi phạm theo module.** Ưu tiên module nghiệp vụ có thay đổi thường xuyên hoặc có nhiều adapter.
6. **Thử strict trên một phạm vi.** Nếu options hỗ trợ scope, dùng phạm vi nhỏ để đánh giá trước; sau đó mở rộng dần.
7. **Chạy strict toàn ứng dụng.** Khi các module đã tuân thủ, đổi depth sang `STRICT` trong architecture test chính.
8. **Giữ kiểm tra trong CI.** Mỗi thay đổi dependency hoặc stereotype phải tiếp tục vượt qua verification.

Không nên giữ `LENIENT` vĩnh viễn mà không có mục tiêu chuyển đổi. Nếu dự án quyết định không áp dụng strict, hãy ghi rõ những quy tắc nào được nới lỏng và lý do kiến trúc.

## 10. Những ngộ nhận thường gặp

- **“VerificationDepth là enum của Spring Modulith.”** Nó thuộc jMolecules ArchUnit và được dùng để cấu hình các rule kiến trúc như Hexagonal Architecture.
- **“STRICT làm ApplicationModules kiểm tra sâu hơn dependency graph.”** Nó siết rule Hexagonal; các kiểm tra module cốt lõi vẫn là bộ quy tắc riêng.
- **“LENIENT không kiểm tra gì.”** Nó vẫn áp dụng các ràng buộc Hexagonal, nhưng cho phép một số quan hệ chuyển tiếp rộng hơn.
- **“STRICT chỉ cần thêm annotation.”** Annotation cần phản ánh đúng vai trò; dependency sai hướng thường cần tái cấu trúc port/adapter.
- **“ApplicationModules.verify() chỉ chạy rule của Spring Modulith.”** Nếu jMolecules integration có mặt và được cấu hình, các rule bổ sung có thể được thực thi cùng.
- **“Thêm jMolecules là tự động sửa kiến trúc.”** Thư viện chỉ phân tích và báo vi phạm; nhóm phải sửa code hoặc điều chỉnh policy có chủ đích.
- **“Overload ensureHexagonal(VerificationDepth) luôn là API mới nhất.”** jMolecules 0.34 đã deprecate overload này để dùng `HexagonalVerificationOptions`.
- **“Tắt additional verifications là cách xử lý mọi lỗi.”** Cách đó có thể bỏ luôn những kiểm tra DDD/Hexagonal mà nhóm muốn bảo vệ; hãy xác định đúng rule gây lỗi.

## Kết luận

`VerificationDepth` của jMolecules điều chỉnh mức nghiêm ngặt của các quy tắc Hexagonal Architecture, thường dùng `LENIENT` khi chuyển đổi codebase cũ và `STRICT` khi các port/adapter đã được tổ chức rõ. Nó không phải cấu hình độ sâu dependency của Spring Modulith. `ApplicationModules.verify()` tiếp tục bảo vệ dependency graph, API package và `allowedDependencies`; jMolecules bổ sung kiểm tra vai trò application, port và adapter. Với jMolecules 0.34 trở lên, ưu tiên cấu hình `HexagonalVerificationOptions.defaults().withDepth(...)` rồi gắn rule vào `VerificationOptions`. Hãy tăng strictness theo lộ trình, xử lý vi phạm bằng cách làm rõ hướng dependency và giữ cả hai nhóm kiểm tra trong CI.

## Tài liệu tham khảo

- [Spring Modulith 2.2 — Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html)
- [jMolecules Integrations — JMoleculesArchitectureRules source](https://github.com/xmolecules/jmolecules-integrations/blob/main/jmolecules-archunit/src/main/java/org/jmolecules/archunit/JMoleculesArchitectureRules.java)
- [jMolecules ArchUnit — HexagonalVerificationOptions API](https://javadoc.io/doc/org.jmolecules.integrations/jmolecules-archunit/latest/org/jmolecules/archunit/HexagonalVerificationOptions.html)
- [jMolecules ArchUnit — VerificationDepth API](https://javadoc.io/doc/org.jmolecules.integrations/jmolecules-archunit/latest/org/jmolecules/archunit/VerificationDepth.html)
