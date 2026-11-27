# Tắt hoặc thay đổi verification tích hợp

Spring Modulith cung cấp cơ chế kiểm tra mô hình mô-đun thông qua `ApplicationModules`. Lệnh `verify()` kiểm tra các quy tắc kiến trúc cốt lõi: module graph không có chu trình, mô-đun chỉ truy cập package API của mô-đun khác và các dependency phải nằm trong allow-list nếu mô-đun khai báo danh sách đó. Nếu jMolecules ArchUnit có trên classpath, Spring Modulith còn có thể chạy các verification bổ sung của thư viện này.

Khi cần thay đổi cách xác minh, hãy phân biệt quy tắc cốt lõi của Spring Modulith với nhóm verification bổ sung. `VerificationOptions` điều chỉnh nhóm bổ sung; API `detectViolations()` cho phép xử lý có chọn lọc các vi phạm. Các cơ chế này có phạm vi khác nhau và không phải cách để biến một module graph có chu trình thành hợp lệ.

## 1. Verification mặc định được kích hoạt tường minh

Một bài kiểm tra kiến trúc thường có dạng:

```java
package com.acme.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    @Test
    void verifiesModuleStructure() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
```

`ApplicationModules.of(ShopApplication.class)` tạo mô hình từ package gốc của ứng dụng. `verify()` thực hiện các kiểm tra tích hợp và ném lỗi nếu phát hiện vi phạm. Khi test thất bại, thông tin vi phạm giúp xác định mô-đun nguồn, mô-đun đích và quan hệ gây lỗi.

Nên đặt bài kiểm tra này trong source set test và chạy nó trong CI. Khi đó, thay đổi làm phát sinh dependency không hợp lệ sẽ bị phát hiện trong quá trình kiểm tra mã nguồn, trước khi artifact được phát hành.

## 2. Tạm thời không chạy verification

Vì verification được gọi tường minh, một test không gọi `verify()` sẽ không thực hiện các kiểm tra tích hợp của Spring Modulith:

```java
package com.acme.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModuleInspectionTests {

    @Test
    void inspectsModulesWithoutRunningVerification() {
        ApplicationModules modules = ApplicationModules.of(ShopApplication.class);

        // Cố ý không gọi modules.verify().
    }
}
```

Đây là khác biệt giữa tạo mô hình và xác minh mô hình. `ApplicationModules.of(…)` giúp tạo mô hình mô-đun; `verify()` mới thực thi bộ quy tắc tích hợp. Nếu bỏ `verify()`, test trên không còn bảo đảm module graph tuân thủ các quy tắc kiến trúc. Việc bỏ lời gọi chỉ ảnh hưởng tới lần test đó; nếu dự án có một cơ chế xác minh khác, chẳng hạn kiểm tra trong runtime support hoặc một test riêng, cơ chế đó vẫn có thể chạy.

Trong một số tình huống, nhóm có thể cần tạm ngừng chạy architecture test để điều tra lỗi hoặc thực hiện một bước chuyển đổi lớn. Hãy quản lý việc đó ở cấp test runner hoặc CI, ghi rõ lý do và thời điểm bật lại. Không nên xóa test hoặc bỏ lời gọi `verify()` âm thầm vì các thay đổi tiếp theo sẽ không còn được bảo vệ.

## 3. Truyền VerificationOptions khi gọi verify

Spring Modulith cung cấp `VerificationOptions` để biểu diễn các tùy chọn dùng trong quá trình xác minh. Có thể truyền options tường minh vào `verify(…)`:

```java
package com.acme.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;
import org.springframework.modulith.core.VerificationOptions;

class ModularityTests {

    @Test
    void verifiesModuleStructureWithExplicitOptions() {
        ApplicationModules modules = ApplicationModules.of(ShopApplication.class);

        modules.verify(VerificationOptions.defaults());
    }
}
```

`VerificationOptions.defaults()` tạo options mặc định. Từ Spring Modulith 1.4, API cung cấp các phương thức để thay đổi nhóm verification bổ sung:

```java
var options = VerificationOptions.defaults()
        .withoutAdditionalVerifications();

ApplicationModules.of(ShopApplication.class).verify(options);
```

`withoutAdditionalVerifications()` tắt các verification bổ sung được đăng ký mặc định, ví dụ các quy tắc jMolecules khi thư viện đó có trên classpath. Phương thức này không tắt ba quy tắc cốt lõi của Spring Modulith: kiểm tra chu trình, truy cập API và dependency được cho phép.

Nếu muốn thay nhóm verification bổ sung mặc định bằng một nhóm riêng, dùng `withAdditionalVerifications(…)`. Nếu muốn giữ nhóm mặc định và thêm quy tắc mới, dùng `andAdditionalVerifications(…)`:

```java
var hexagonal = JMoleculesArchitectureRules.ensureHexagonal(VerificationDepth.STRICT);

var replaceDefaults = VerificationOptions.defaults()
        .withAdditionalVerifications(hexagonal);

var extendDefaults = VerificationOptions.defaults()
        .andAdditionalVerifications(hexagonal);

ApplicationModules.of(ShopApplication.class).verify(replaceDefaults);
ApplicationModules.of(ShopApplication.class).verify(extendDefaults);
```

Ví dụ jMolecules yêu cầu dependency tương ứng của jMolecules ArchUnit và các import `JMoleculesArchitectureRules`, `VerificationDepth` từ thư viện đó. Nếu thư viện không có trên classpath, các verification jMolecules mặc định cũng không được kích hoạt. `withAdditionalVerifications(…)` thay thế nhóm bổ sung mặc định; `andAdditionalVerifications(…)` cộng thêm quy tắc vào nhóm đó.

Không nên tự đặt tên system property hoặc giả định có một cờ chung như `verification.enabled=false`. `VerificationOptions` điều khiển nhóm verification bổ sung; để điều chỉnh quy tắc module cốt lõi, hãy sửa metadata mô-đun hoặc hợp đồng kiến trúc tương ứng.

## 4. Lọc vi phạm có chủ đích bằng detectViolations

Thông thường, `verify()` ném exception khi có bất kỳ vi phạm kiến trúc nào. Nếu cần xử lý hoặc bỏ qua một số vi phạm cụ thể trong một giai đoạn chuyển tiếp, dùng `detectViolations()` để lấy tập vi phạm, lọc rồi mới quyết định có ném lỗi hay không:

```java
var violations = ApplicationModules.of(ShopApplication.class)
        .detectViolations()
        .filter(violation -> shouldFailBuild(violation));

violations.throwIfPresent();
```

`shouldFailBuild(…)` ở đây là predicate do dự án định nghĩa: trả về `true` cho vi phạm cần tiếp tục làm test thất bại. Hãy giới hạn ngoại lệ theo đúng vi phạm đã biết, kèm lý do và thời hạn loại bỏ. Không lọc theo chuỗi thông báo quá rộng vì một thay đổi wording có thể khiến quy tắc bỏ qua hoạt động ngoài dự kiến.

Có thể truyền `VerificationOptions` vào `detectViolations(…)` giống như với `verify(…)`. Cách này hữu ích khi muốn kiểm soát verification bổ sung và đồng thời xử lý kết quả vi phạm theo chính sách của dự án.

## 5. Thay đổi quy tắc kiến trúc thay vì che lỗi

Nhiều trường hợp tưởng như cần tắt verification thực ra là do mô hình mô-đun chưa mô tả đúng ý định kiến trúc. Khi đó, hãy sửa metadata hoặc hợp đồng của mô-đun để quy tắc phản ánh đúng thiết kế.

**Cho phép một dependency có chủ đích.** Nếu `orders` thực sự cần API của `inventory`, khai báo dependency trong `package-info.java` của `orders`:

```java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "inventory"
)
package com.acme.shop.orders;
```

Nếu chỉ cần một Named Interface, hãy khai báo đúng tên, ví dụ `inventory::api`. Việc này làm rõ quan hệ được cho phép thay vì bỏ kiểm tra dependency.

**Công khai hợp đồng cần chia sẻ.** Nếu mô-đun khác cần một package con, đánh dấu package đó bằng `@NamedInterface` và chỉ cho phép consumer phụ thuộc vào named interface phù hợp. Không mở toàn bộ package nội bộ chỉ để làm cho test qua.

**Điều chỉnh module detection khi cấu trúc package khác quy ước mặc định.** Nếu package gốc của các mô-đun không được tổ chức theo cấu trúc mặc định, hãy cung cấp `ApplicationModuleDetectionStrategy` phù hợp. Detection strategy thay đổi cách Spring Modulith nhận diện mô-đun; nó không phải công tắc bỏ qua verification.

**Loại trừ đúng phần mã nằm ngoài phạm vi kiến trúc.** Nếu một số lớp kỹ thuật thực sự không thuộc mô hình cần kiểm tra, có thể dùng predicate exclusion khi tạo `ApplicationModules`. Chọn pattern package đủ hẹp để không bỏ sót lớp nghiệp vụ. Exclusion làm các lớp khớp predicate nằm ngoài phạm vi inspection, vì vậy cần ghi rõ lý do.

## 6. Phân biệt VerificationOptions, metadata mô-đun và exclusion

Các cơ chế này giải quyết những vấn đề khác nhau:

| Cơ chế | Vai trò | Khi sử dụng |
|---|---|---|
| `VerificationOptions` | Thay thế, mở rộng hoặc tắt nhóm verification bổ sung | Khi cần điều chỉnh các quy tắc bổ sung, ví dụ tích hợp jMolecules |
| `detectViolations()` | Trả về tập vi phạm để lọc trước khi ném lỗi | Khi cần miễn trừ một số vi phạm đã xác định trong giai đoạn chuyển tiếp |
| `@ApplicationModule` và `allowedDependencies` | Mô tả quan hệ phụ thuộc được kiến trúc cho phép | Khi một dependency giữa hai mô-đun là chủ đích và cần được khai báo |
| `@NamedInterface` | Xác định package con nào là API được công khai | Khi consumer chỉ nên sử dụng một nhóm hợp đồng cụ thể |
| `ApplicationModuleDetectionStrategy` | Xác định package nào được nhận diện là mô-đun | Khi cấu trúc package không phù hợp với detection mặc định |
| Predicate exclusion | Loại lớp khớp điều kiện khỏi phạm vi inspection | Khi mã kỹ thuật cụ thể nằm ngoài phạm vi cần kiểm tra |

Không nên dùng một cơ chế thay cho cơ chế khác. Ví dụ, `allowedDependencies` không làm một package nội bộ trở thành public API; `@NamedInterface` không cho phép một dependency chưa được khai báo; exclusion không sửa quan hệ phụ thuộc sai.

## 7. Giữ architecture test có giá trị trong CI

Khi thay đổi verification options hoặc điều chỉnh cách chạy test, hãy bảo đảm CI vẫn thực hiện kiểm tra kiến trúc trên đúng source set và artifact cần phát hành.

Một cấu hình test tối thiểu có thể giữ lời gọi `verify()` trong một lớp test riêng:

```java
package com.acme.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModuleArchitectureTests {

    @Test
    void applicationModulesMustBeValid() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
```

Đặt tên test thể hiện rõ đây là architecture gate. Nếu CI có nhiều nhóm test, có thể gắn tag hoặc phân nhóm để chạy riêng, nhưng pipeline bảo vệ nhánh chính vẫn phải thực thi nhóm test này. Khi một bước tạm thời bỏ qua test, hãy theo dõi việc bật lại và không coi build đó là đã xác minh đầy đủ kiến trúc.

Khi test thất bại, hãy ưu tiên sửa nguyên nhân: điều chỉnh API, Named Interface, allow-list, chiều dependency hoặc detection strategy. Chỉ thay đổi tùy chọn verification khi có lý do cụ thể và đã hiểu phần kiểm tra nào bị ảnh hưởng.

## 8. Quy trình lựa chọn cách điều chỉnh

Khi một architecture test thất bại, hãy làm theo trình tự:

1. Đọc toàn bộ thông báo vi phạm và xác định rule đang thất bại.
2. Kiểm tra dependency hoặc package gây vi phạm có đúng với ý định kiến trúc không.
3. Nếu dependency là hợp lệ, khai báo nó bằng `allowedDependencies` và công khai đúng API bằng package gốc hoặc Named Interface.
4. Nếu Spring nhận diện sai module base package, điều chỉnh detection strategy.
5. Nếu một nhóm lớp thật sự nằm ngoài phạm vi kiểm tra, cân nhắc predicate exclusion có phạm vi hẹp.
6. Chỉ thay đổi `VerificationOptions` khi cần tùy chỉnh lần verification và đã xác nhận API trong phiên bản đang dùng.
7. Chạy lại architecture test và các test liên quan; xác nhận CI vẫn thực hiện kiểm tra này.

Không nên bỏ toàn bộ verification chỉ vì một dependency chưa được mô tả đúng. Việc tắt kiểm tra có thể khiến chu trình, truy cập package nội bộ hoặc dependency ngoài dự kiến tồn tại lâu dài mà không bị phát hiện.

## 9. Bài tập tự kiểm tra

Với ứng dụng `com.acme.shop`, hãy chọn cơ chế phù hợp cho từng trường hợp:

| Tình huống | Cơ chế nên xem xét | Lý do |
|---|---|---|
| Muốn kiểm tra các quy tắc kiến trúc mặc định trong CI | `ApplicationModules.verify()` | Kích hoạt bộ verification tích hợp |
| Muốn tắt verification bổ sung mặc định từ classpath | `VerificationOptions.defaults().withoutAdditionalVerifications()` | Giữ nguyên các quy tắc cốt lõi của Spring Modulith |
| Muốn thay verification bổ sung mặc định bằng quy tắc riêng | `withAdditionalVerifications(…)` | Thay thế nhóm bổ sung mặc định |
| Muốn thêm quy tắc vào nhóm verification bổ sung mặc định | `andAdditionalVerifications(…)` | Giữ nhóm mặc định và mở rộng kiểm tra |
| Muốn lọc một số vi phạm cụ thể trước khi làm test thất bại | `detectViolations().filter(…).throwIfPresent()` | Chỉ miễn trừ các vi phạm được predicate xác định |
| Một dependency tới `inventory` là hợp lệ và cần được ghi rõ | `allowedDependencies` | Mô tả dependency được phép |
| Consumer chỉ cần package `inventory.api` | `@NamedInterface` và allow-list tương ứng | Công khai hợp đồng có phạm vi cụ thể |
| Package nghiệp vụ không được nhận diện theo cấu trúc mặc định | `ApplicationModuleDetectionStrategy` | Điều chỉnh cách phát hiện module |
| Một package kỹ thuật cụ thể nằm ngoài phạm vi inspection | Predicate exclusion | Bỏ qua đúng các lớp được chọn |
| Muốn tạm ngừng chạy architecture test trong một lần điều tra | Cấu hình test runner/CI có kiểm soát | Verification là lời gọi tường minh trong test |

Hãy tạo một architecture test gọi `verify()`, sau đó thử thay đổi một dependency có chủ đích bằng `allowedDependencies`. Quan sát sự khác biệt giữa việc khai báo đúng quan hệ và việc bỏ qua verification. Cuối cùng, kiểm tra lại pipeline để chắc chắn architecture test vẫn chạy trong luồng CI thông thường.
