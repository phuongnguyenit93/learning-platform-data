# Tách module hợp đồng, module ứng dụng chủ và module provider trong Java JPMS

## 1. Mục tiêu kiến trúc

Với Java Platform Module System (JPMS), một hệ thống plugin có thể phân chia rõ ba trách nhiệm: **module hợp đồng (service API)** định nghĩa interface ổn định; **module ứng dụng chủ (consumer/host)** cần dùng dịch vụ mà không phụ thuộc implementation; **module provider** triển khai và đăng ký implementation. Kiến trúc này cho phép thay hoặc bổ sung provider mà không sửa source của host, đồng thời để JPMS kiểm tra quan hệ module lúc biên dịch và chạy.

Mô hình phụ thuộc:

```text
                 requires
app.host ----------------------> app.contract
    |                                 ^
    | uses contract.Greeting          | requires
    |                                 |
    +-- ServiceLoader ---------- app.provider.en
                          provider đăng ký bằng provides ... with ...
```

Điểm cốt lõi: **host không viết `requires app.provider.en`** chỉ để dùng dịch vụ. Host chỉ `requires app.contract` và `uses` service; provider `requires app.contract` rồi `provides` implementation. Việc có module provider trong runtime configuration là trách nhiệm của cách launch/module resolution.

## 2. Vai trò và ranh giới của từng module

| Module | Sở hữu | module-info.java | Không nên làm |
| --- | --- | --- | --- |
| `app.contract` | Service interface, DTO và các kiểu thuộc API chung | `exports contract;` | Biết concrete provider hoặc gọi trực tiếp host |
| `app.host` | Điều phối, lựa chọn và sử dụng provider | `requires app.contract; uses contract.Greeting;` | `new` implementation hoặc hard-code tên provider |
| `app.provider.en` | Implementation và dependency nội bộ của plugin | `requires app.contract; provides contract.Greeting with en.EnglishGreeting;` | Buộc host import package implementation |

Module hợp đồng cần được giữ gọn và có chính sách version/compatibility rõ ràng: đổi chữ ký interface có thể làm provider đã biên dịch trước không còn tương thích. `exports` chỉ công khai package API cho các module đọc được nó; không buộc phải export package implementation của provider.

Module provider có thể có nhiều implementation cho cùng service, hoặc có nhiều module provider độc lập cùng đăng ký một service. Ứng dụng host phải định nghĩa cách chọn hoặc sử dụng chúng; thứ tự khám phá không phải thứ tự ưu tiên nghiệp vụ.

## 3. Ví dụ hoàn chỉnh Java 17+: ba named module

Cấu trúc thư mục:

```text
demo/
  src/
    app.contract/
      module-info.java
      contract/Greeting.java
    app.host/
      module-info.java
      host/Main.java
    app.provider.en/
      module-info.java
      en/EnglishGreeting.java
```

### Module hợp đồng `app.contract`

`src/app.contract/module-info.java`:

```java
module app.contract {
    exports contract;
}
```

`src/app.contract/contract/Greeting.java`:

```java
package contract;

public interface Greeting {
    String name();
    String greet(String person);
}
```

Package `contract` được export để cả host và provider có thể tham chiếu `Greeting`. Không đặt concrete plugin vào module này.

### Module ứng dụng chủ `app.host`

`src/app.host/module-info.java`:

```java
module app.host {
    requires app.contract;
    uses contract.Greeting;
}
```

`src/app.host/host/Main.java`:

```java
package host;

import contract.Greeting;
import java.util.ArrayList;
import java.util.List;
import java.util.ServiceLoader;

public final class Main {
    public static void main(String[] args) {
        List<Greeting> providers = new ArrayList<>();
        for (Greeting provider : ServiceLoader.load(Greeting.class)) {
            providers.add(provider);
        }
        if (providers.isEmpty()) {
            throw new IllegalStateException("No Greeting provider resolved");
        }
        for (Greeting provider : providers) {
            System.out.println(provider.name() + ": "
                    + provider.greet("Java"));
        }
    }
}
```

`uses contract.Greeting;` khai báo module này tiêu thụ service. Khi gọi `ServiceLoader.load(Greeting.class)` từ code của named module, thiếu `uses` có thể gây `ServiceConfigurationError`; vì vậy phải khai báo ở module host, không chỉ import interface trong Java source.

### Module provider `app.provider.en`

`src/app.provider.en/module-info.java`:

```java
module app.provider.en {
    requires app.contract;
    provides contract.Greeting with en.EnglishGreeting;
}
```

`src/app.provider.en/en/EnglishGreeting.java`:

```java
package en;

import contract.Greeting;

public final class EnglishGreeting implements Greeting {
    public EnglishGreeting() {}

    @Override
    public String name() {
        return "english";
    }

    @Override
    public String greet(String person) {
        return "Hello, " + person;
    }
}
```

`provides ... with ...` đăng ký implementation để `ServiceLoader` khám phá trong module configuration. Vì đây là public provider class có public no-arg constructor, nó đáp ứng cơ chế provider class của named module. JPMS cũng hỗ trợ cơ chế static provider method trong một số trường hợp, nhưng không cần cho ví dụ này. Package `en` **không cần `exports`** chỉ để được `ServiceLoader` khởi tạo qua service binding.

## 4. Biên dịch và chạy trên module path

Đứng trong thư mục `demo`, dùng JDK 17+ với multi-module source layout:

```bash
javac --module-source-path src -d mods --module app.contract,app.host,app.provider.en
java --module-path mods --add-modules app.provider.en --module app.host/host.Main
```

Output kỳ vọng:

```text
english: Hello, Java
```

Ở lệnh chạy, `--module-path mods` làm các module có thể được quan sát; `--add-modules app.provider.en` yêu cầu đưa module provider vào module graph để chắc chắn minh họa hoạt động không phụ thuộc vào suy luận resolution của launcher. Với service binding của JPMS, provider có thể cũng được giải quyết thông qua cơ chế service binding khi áp dụng; nhưng câu lệnh minh họa cố tình nêu rõ module provider để dễ xác minh.

Không trộn `-cp` với `--module-path` một cách tùy tiện. Class trên classpath thuộc unnamed module và chịu cơ chế readability khác named module. Với ví dụ này, cả ba đều là named module.

### Đóng gói từng module thành modular JAR

Sau khi biên dịch:

```bash
mkdir -p dist
jar --create --file dist/app.contract.jar -C mods/app.contract .
jar --create --file dist/app.host.jar -C mods/app.host .
jar --create --file dist/app.provider.en.jar -C mods/app.provider.en .
java --module-path dist --add-modules app.provider.en --module app.host/host.Main
```

Lệnh cuối vẫn in `english: Hello, Java`. Bây giờ runtime dùng đúng JAR phân phối thay cho thư mục `mods`. Nếu không có module provider trên module path hoặc không được resolve vào layer phù hợp, host sẽ không tìm thấy implementation này. Nếu có provider khác đã được resolve, số lượng/kết quả có thể khác; test nên assert tập provider kỳ vọng của bản phân phối.

Kiểm tra module descriptors:

```bash
jar --describe-module --file dist/app.contract.jar
jar --describe-module --file dist/app.host.jar
jar --describe-module --file dist/app.provider.en.jar
```

Kết quả cần thấy các quan hệ `exports contract`, `requires app.contract`, `uses contract.Greeting`, `provides contract.Greeting with en.EnglishGreeting` tương ứng. Kiểm tra artifact cuối để phát hiện `module-info.class` bị mất khi shade/package.

## 5. Tại sao host không trực tiếp phụ thuộc provider?

Giả sử host viết:

```java
import en.EnglishGreeting;
Greeting greeting = new EnglishGreeting();
```

Đây chỉ là đoạn minh họa (không phải class độc lập). Để mã này compile trong named module, host phải đọc module provider và package `en` phải được export. Điều này gắn host với implementation và thường làm hỏng mục tiêu thay plugin độc lập.

Với SPI, host chỉ biết `Greeting` và sử dụng `ServiceLoader`; provider module có thể được thay bằng `app.provider.vi` mà không sửa `app.host`, miễn là provider đáp ứng cùng hợp đồng API và được resolve ở runtime.

Đường phụ thuộc mong muốn là một chiều:

```text
host ----requires----> contract <----requires---- provider
host ----uses-------> contract.Greeting
provider --provides--> contract.Greeting
```

Đừng để module hợp đồng `requires app.host` hoặc `requires app.provider.en`; như vậy làm mất tính độc lập và có thể tạo vòng phụ thuộc module.

## 6. Mở rộng sang nhiều provider

Muốn bổ sung một provider tiếng Việt, tạo module mới:

```java
module app.provider.vi {
    requires app.contract;
    provides contract.Greeting with vi.VietnameseGreeting;
}
```

Đây là descriptor minh họa; cần thêm class `vi.VietnameseGreeting` thực thi `contract.Greeting` rồi biên dịch và đặt JAR vào module path. Host không cần thay đổi `module-info.java` nếu vẫn dùng `Greeting`.

Với nhiều provider, `ServiceLoader` cho phép duyệt chúng nhưng không đảm bảo thứ tự nghiệp vụ mong muốn. Nếu cần chọn provider theo `name()`, region, capacity hoặc priority, xây dựng chính sách lựa chọn độc lập (lọc, xếp hạng, xử lý khi hòa và khi thiếu provider). Tránh dùng phần tử đầu tiên của iterator làm lựa chọn mặc định một cách ngầm định.

Trong modular architecture, một provider có thể không public-export implementation package mà vẫn được đăng ký. Consumer không nên dùng reflection để bypass encapsulation; `provides ... with ...` mới là hợp đồng dịch vụ.

## 7. Module resolution, module layer và runtime discovery

**Có mặt trên module path** không đồng nghĩa module provider luôn được resolve vào layer mà loader đang tìm. JPMS giải quyết module graph dựa vào root modules, requirements và service binding theo chế độ launch/layer; khi tạo layer động, ứng dụng phải đưa module vào configuration phù hợp.

Đối với module layer do host tạo, có thể dùng `ServiceLoader.load(layer, Greeting.class)` để khám phá provider trong layer phù hợp. Ví dụ ngắn (minh họa trong method đã có `ModuleLayer layer`):

```java
ServiceLoader<Greeting> loader = ServiceLoader.load(layer, Greeting.class);
for (Greeting provider : loader) {
    System.out.println(provider.name());
}
```

Không suy luận rằng `ServiceLoader.load(Greeting.class)` trên thread context classloader sẽ tự tìm provider trong mọi layer do ứng dụng tạo. Cần chọn overload đúng với kiến trúc loader/layer và test bằng artifact cuối.

**Readability và accessibility:** `requires app.contract` cho phép module phụ thuộc đọc API module; `exports contract` cho phép các module khác truy cập public types trong package `contract`. Không cần `opens en` để service provider bình thường được nạp bằng cơ chế JPMS `provides`, và không nên mở rộng `opens` chỉ để “sửa” service lookup mà chưa xác định nguyên nhân.

## 8. API compatibility và quản lý version

Ranh giới hợp đồng là nơi cần quản lý thay đổi thận trọng:

- Thêm abstract method vào interface có thể phá binary/source compatibility của provider cũ; cân nhắc default method khi phù hợp, hoặc version hóa hợp đồng có kiểm soát.
- Đổi package/name của service interface làm thay đổi service identity; cả `uses` lẫn `provides` và các implementation phải được cập nhật.
- Để host và provider dùng cùng một runtime class `contract.Greeting`. Nếu nhiều bản API được nạp bằng các loader/layer khác nhau, có thể có type mismatch dù tên class giống nhau.
- Không cho provider JAR đóng gói bản sao tùy tiện của contract API trong một kiến trúc chia sẻ interface.
- Dùng test tương thích với các phiên bản plugin được hỗ trợ; compile thành công chỉ là một bước, phải gọi hành vi thực tế.

Với JPMS, module version không tự tạo một resolver nâng cấp tương thích semantic versioning. Nhà phát triển vẫn phải quản lý version dependency và hợp đồng phát hành.

## 9. Các lỗi phổ biến

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `ServiceLoader` trả 0 provider | Module provider không nằm trong layer/module graph đã resolve | Kiểm tra `--module-path`, roots, service binding hoặc `--add-modules` |
| `ServiceConfigurationError` khi load service | Host thiếu `uses`, provider sai hợp đồng hoặc lỗi khởi tạo | Kiểm tra `module-info.java`, stacktrace và provider |
| Compile báo package không visible | API package chưa `exports` hoặc thiếu `requires` | Chỉnh descriptor đúng ranh giới |
| Host phải import implementation | Thiết kế còn phụ thuộc provider | Chuyển sang SPI và `uses`/`provides` |
| `ClassCastException`/`not a subtype` | Service API bị nạp khác runtime identity | Chỉ dùng một API identity trong graph/loader boundary |
| Chạy trên classpath được, module path thất bại | Cơ chế resource/descriptor và module resolution khác | Test đúng named modules; kiểm tra `module-info.class` |
| Tự thêm `opens` cho mọi package | Hiểu sai service lookup hoặc muốn bypass encapsulation | Giữ `exports`/`opens` tối thiểu và dùng `provides` |

## 10. Chiến lược kiểm thử ba module

1. **Unit test contract:** kiểm tra semantics của API và định dạng input/output.
2. **Integration test host–provider:** chạy host với một provider đã resolve, assert số lượng/tên và kết quả.
3. **Negative test:** chạy host khi thiếu provider, xác nhận lỗi rõ ràng thay vì âm thầm tiếp tục.
4. **Multi-provider test:** bổ sung provider thứ hai, xác minh cả hai được tìm thấy; kiểm tra chính sách chọn độc lập với thứ tự.
5. **Artifact test:** sử dụng `dist/*.jar` trên module path, đọc `jar --describe-module` và chạy lệnh launch đúng như production.
6. **Compatibility test:** xác nhận provider cũ vẫn hoạt động với phiên bản contract mới khi hệ thống tuyên bố hỗ trợ.

Trong CI, nên build và test đúng các modular JAR cuối cùng. Test trên classpath IDE có thể không phát hiện lỗi thiếu `module-info.class` hay provider không được resolve.

## 11. Checklist thiết kế

- [ ] Contract module chỉ chứa API dùng chung và `exports` đúng package.
- [ ] Host `requires` contract, khai báo `uses`, và không import concrete provider.
- [ ] Provider `requires` contract, khai báo `provides ... with ...`, implementation hợp lệ.
- [ ] Đặt provider module trong module graph/module layer runtime.
- [ ] Kiểm tra `ServiceLoader` với overload và classloader/layer đúng.
- [ ] Quản lý compatibility của API và không nhân đôi service interface ở runtime.
- [ ] Chọn provider theo chính sách ứng dụng thay vì thứ tự khám phá.
- [ ] Test bằng modular JAR phát hành, không chỉ classes trong IDE.

**Ghi nhớ:** module hợp đồng sở hữu *dịch vụ là gì*, host sở hữu *khi nào và vì sao dùng dịch vụ*, provider sở hữu *cách thực hiện dịch vụ*. JPMS thể hiện ranh giới qua `requires`, `exports`, `uses` và `provides`; `ServiceLoader` nối các thành phần tại runtime.
