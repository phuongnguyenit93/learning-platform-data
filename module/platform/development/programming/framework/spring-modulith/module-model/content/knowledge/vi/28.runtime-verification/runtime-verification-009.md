# Rủi ro ứng dụng không khởi động vì violation

Spring Modulith có thể kiểm tra cấu trúc application module ngay khi ứng dụng khởi động. Nếu bật runtime verification và mô hình module có vi phạm, Spring Boot sẽ dừng quá trình khởi động thay vì đưa một ứng dụng có ranh giới kiến trúc sai vào phục vụ request. Cơ chế này giúp phát hiện lỗi sớm ở môi trường chạy, nhưng cũng tạo ra rủi ro vận hành: một vi phạm kiến trúc chưa được xử lý có thể khiến instance không khởi động được.

Runtime verification không tự bật chỉ vì dự án có các annotation như @ApplicationModule hoặc @NamedInterface. Để kích hoạt, ứng dụng cần có artifact spring-modulith-runtime trên runtime classpath và cấu hình spring.modulith.runtime.verification-enabled=true. Giá trị mặc định của property này là false. Vì vậy, cần phân biệt rõ kiểm tra trong test, kiểm tra khi khởi động và các lỗi khởi tạo Spring thông thường.

Trong SPRING_MODULITH_MODULE_MODEL, bài học này giải thích điều kiện khiến violation chặn startup, các loại vi phạm có thể được phát hiện, cách chẩn đoán log và cách triển khai runtime verification an toàn qua CI, staging và production.

## 1. Phân biệt verification trong test và verification lúc runtime

Spring Modulith cung cấp ApplicationModules.verify() để kiểm tra mô hình application module. Cách dùng phổ biến là gọi phương thức này trong một JUnit test:

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

Trong cách dùng này, vi phạm làm test thất bại. Nó không tự làm ứng dụng production dừng khởi động, vì test thường chạy trong test task hoặc CI chứ không nằm trong runtime classpath của ứng dụng.

Runtime verification là lựa chọn riêng. Khi bật tính năng runtime support, Spring Modulith tự động tạo bộ kiểm tra module trong quá trình bootstrap. Nếu bộ kiểm tra phát hiện violation, nó ném lỗi và Spring Boot không hoàn tất khởi động ứng dụng.

| Cách kiểm tra | Thời điểm | Hậu quả khi có violation |
|---|---|---|
| ApplicationModules.verify() trong JUnit | Khi chạy test | Test thất bại; build/CI có thể bị chặn |
| Runtime verification | Trong quá trình ứng dụng khởi động | Startup bị abort; instance không sẵn sàng phục vụ |
| Spring context test | Khi test tạo ApplicationContext | Test thất bại nếu bean hoặc cấu hình không khởi tạo được |
| Runtime bean initialization | Khi Spring tạo bean | Ứng dụng có thể dừng vì lỗi dependency injection hoặc cấu hình |

Không nên suy luận rằng mọi module violation đều tự động làm ứng dụng không khởi động. Hậu quả đó xảy ra khi runtime verification được kích hoạt hoặc khi ứng dụng tự gọi verify trong một hook khởi động.

## 2. Hai điều kiện để bật runtime verification

Runtime verification cần cả thư viện runtime và property bật tính năng.

### Thêm spring-modulith-runtime

Với Gradle Kotlin DSL:

~~~kotlin
dependencies {
    runtimeOnly("org.springframework.modulith:spring-modulith-runtime")
}
~~~

Với Maven:

~~~xml
<dependency>
    <groupId>org.springframework.modulith</groupId>
    <artifactId>spring-modulith-runtime</artifactId>
    <scope>runtime</scope>
</dependency>
~~~

Hãy để Spring Modulith BOM hoặc dependency management của dự án quản lý phiên bản đồng bộ giữa các artifact Spring Modulith.

### Bật property

Trong application.yml:

~~~yaml
spring:
  modulith:
    runtime:
      verification-enabled: true
~~~

Property đầy đủ là spring.modulith.runtime.verification-enabled. Mặc định là false. Khi runtime artifact có mặt và property được bật, auto-configuration đăng ký RuntimeApplicationModuleVerifier để xác minh module arrangement khi ứng dụng khởi động.

Hai trường hợp cần phân biệt:

| Runtime artifact | Property | Kết quả |
|---|---|---|
| Không có | false hoặc true | Không có runtime verifier do Spring Modulith runtime cung cấp; property cần artifact này để có tác dụng |
| Có | false | Runtime support có thể được cấu hình, nhưng module verification lúc startup vẫn tắt |
| Có | true | Module arrangement được kiểm tra khi startup; violation làm startup abort |

Chỉ thêm dependency runtime chưa có nghĩa ứng dụng sẽ bị chặn bởi module violation. Property bật verification mới là công tắc quyết định.

## 3. Từ phiên bản nào có runtime verification?

Runtime verification qua property spring.modulith.runtime.verification-enabled thuộc dòng Spring Modulith 2.0 trở lên. Các dự án dùng Spring Modulith 1.x không nên giả định property này có sẵn hoặc có cùng hành vi.

Trước khi bật:

- Kiểm tra phiên bản Spring Modulith thực tế do BOM quản lý.
- Đọc tài liệu runtime tương ứng với phiên bản đang dùng.
- Không nâng riêng spring-modulith-runtime lệch phiên bản với các artifact Spring Modulith khác.
- Nếu đang ở dòng 1.x, tiếp tục bảo vệ module structure bằng JUnit architecture test cho tới khi dự án nâng cấp phù hợp.

Nếu cấu hình property nhưng artifact hoặc phiên bản không hỗ trợ runtime verifier, đừng kết luận rằng ứng dụng đang được bảo vệ. Hãy xác nhận dependency runtime và hành vi thực tế theo tài liệu của phiên bản.

## 4. Runtime verifier kiểm tra những violation nào?

Runtime verifier sử dụng mô hình application module và các quy tắc verification của Spring Modulith. Các nhóm quy tắc cốt lõi gồm:

| Nhóm violation | Ví dụ | Vì sao cần xử lý |
|---|---|---|
| Dependency cycle | order → inventory → catalog → order | Các module tạo thành vòng phụ thuộc, khó thay đổi độc lập |
| Truy cập internal package | order import inventory.internal.InventoryRepository | Consumer phụ thuộc vào chi tiết triển khai chưa được provider công bố |
| Dependency ngoài whitelist | order chỉ cho phép inventory nhưng tham chiếu trực tiếp payment | Quan hệ module vượt khỏi dependency đã khai báo |
| Quy tắc kiến trúc bổ sung | jMolecules rule được kích hoạt khi integration tương ứng có trên classpath | Các ràng buộc bổ sung cũng có thể góp phần tạo verification failure |

### Dependency cycle

Ví dụ:

~~~mermaid
flowchart LR
    Order["order"] --> Inventory["inventory"]
    Inventory --> Catalog["catalog"]
    Catalog --> Order
~~~

Đường đi order → inventory → catalog → order là một chu kỳ. Cần lần từng cạnh để xác định reference tạo ra quan hệ ngược và tái cấu trúc quyền sở hữu hợp đồng hoặc hướng giao tiếp.

### Truy cập internal package

Một kiểu public nằm trong package con chưa expose vẫn có thể vi phạm encapsulation:

~~~java
package com.example.shop.order.internal;

import com.example.shop.inventory.internal.InventoryRepository;

class PlaceOrderService {
    private final InventoryRepository repository;

    PlaceOrderService(InventoryRepository repository) {
        this.repository = repository;
    }
}
~~~

Nếu inventory là closed module, order cần sử dụng API package gốc hoặc Named Interface mà inventory công bố, thay vì import repository nội bộ.

### Dependency không nằm trong allowedDependencies

Nếu order khai báo:

~~~java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "inventory"
)
package com.example.shop.order;
~~~

nhưng code của order tham chiếu trực tiếp kiểu thuộc payment, verification sẽ phát hiện dependency không nằm trong whitelist. Nếu dependency có chủ đích, hãy khai báo đúng module identifier hoặc named interface. Nếu không, loại bỏ reference hoặc chuyển trách nhiệm về đúng module.

## 5. Vì sao violation có thể làm startup thất bại?

Khi runtime verification được bật, Spring Modulith tạo mô hình module từ ứng dụng và chạy các quy tắc verification trong quá trình bootstrap. Nếu có violation, verifier không cho ứng dụng tiếp tục khởi động như thể cấu trúc đã hợp lệ.

Luồng khái quát:

~~~mermaid
flowchart TD
    A["Spring Boot bắt đầu bootstrap"] --> B["Runtime auto-configuration"]
    B --> C["Tạo ApplicationModules model"]
    C --> D["RuntimeApplicationModuleVerifier"]
    D --> E{"Có violation?"}
    E -->|Không| F["Tiếp tục startup"]
    E -->|Có| G["Ném verification failure"]
    G --> H["Spring Boot báo lỗi và abort startup"]
~~~

Điều này là fail-fast có chủ đích. Ứng dụng không được đưa vào trạng thái sẵn sàng nếu mô hình module vi phạm các quy tắc mà nhóm đã yêu cầu runtime kiểm tra.

Hệ quả vận hành có thể gồm:

- Instance mới không thể chuyển sang trạng thái ready.
- Deployment rollout bị đình trệ nếu instance mới không khởi động được.
- Orchestrator có thể restart container nhiều lần nếu restart policy tiếp tục áp dụng.
- Nếu thay thế toàn bộ replica cũ trước khi instance mới healthy, dịch vụ có nguy cơ mất khả năng phục vụ.
- Một cấu hình sai được triển khai đồng loạt có thể làm nhiều instance cùng fail startup.

Vì vậy, runtime verification nên được xem là một startup gate có ảnh hưởng trực tiếp tới khả năng triển khai.

## 6. Violation không giống lỗi tạo Spring bean

Không phải mọi lỗi khiến ứng dụng không khởi động đều là module violation. Hãy phân biệt nguyên nhân:

| Loại lỗi | Ví dụ | Cách kiểm tra |
|---|---|---|
| Module verification failure | Dependency cycle, internal package access, whitelist violation | ApplicationModules.verify() hoặc runtime verifier |
| Bean creation failure | Không tìm được bean phù hợp để inject | Spring context test, đọc BeanCreationException |
| Configuration failure | Thiếu property hoặc cấu hình không hợp lệ | Kiểm tra configuration binding và active profile |
| Infrastructure failure | Không kết nối được database hoặc broker | Kiểm tra kết nối và health của hạ tầng |
| Classpath/version failure | Thiếu class hoặc dependency không tương thích | Kiểm tra dependency management và runtime classpath |

Ví dụ, một module có thể tuân thủ toàn bộ module boundary nhưng Spring context vẫn thất bại vì thiếu bean PaymentGateway. Ngược lại, Spring có thể tạo được tất cả bean nhưng runtime module verifier vẫn từ chối ứng dụng vì một module import internal package của module khác.

Đọc root cause và loại exception trước khi sửa. Không nên thêm whitelist hoặc mở module khi nguyên nhân thật sự là thiếu bean hay cấu hình database.

## 7. Cấu hình runtime verification theo môi trường

Property có thể được quản lý theo profile hoặc external configuration. Ví dụ, bật trong môi trường staging:

~~~yaml
spring:
  config:
    activate:
      on-profile: staging
  modulith:
    runtime:
      verification-enabled: true
~~~

Nếu production cũng bật runtime verification, hãy bảo đảm cùng bộ kiểm tra đã chạy thành công ở CI và staging trước khi rollout. Không nên dựa vào việc chỉ staging có property nếu production cần được bảo vệ bằng cùng một gate.

Quản lý cấu hình cần chú ý:

- Kiểm tra profile thực sự được kích hoạt khi deploy.
- Kiểm tra environment variable hoặc command-line argument có ghi đè property không.
- Tránh để các replica trong cùng một deployment dùng cấu hình verification khác nhau ngoài chủ đích.
- Ghi nhận rõ môi trường nào bật runtime verification.
- Giữ cấu hình test architecture độc lập với property runtime.

Spring Boot có thể nhận property từ nhiều nguồn. Khi một môi trường bất ngờ không khởi động, hãy xác minh effective configuration thay vì chỉ nhìn application.yml mặc định.

## 8. Chẩn đoán startup failure do module violation

Khi ứng dụng không khởi động, bắt đầu từ log của lần bootstrap thất bại:

1. Xác nhận runtime verification có được bật hay không.
2. Tìm thông báo Spring Modulith runtime verification hoặc lỗi có cause là Violations.
3. Đọc toàn bộ danh sách violation, không chỉ dòng stack trace đầu tiên.
4. Ghi lại consumer, provider và type/package liên quan.
5. Phân loại cycle, internal access, dependency ngoài whitelist hoặc rule bổ sung.
6. Tìm source reference gây ra cạnh dependency.
7. Kiểm tra module metadata, Named Interface và allowedDependencies.
8. Sửa nguyên nhân rồi chạy architecture test trước khi deploy lại.

Ở các phiên bản hiện hành có runtime failure analyzer chuyên biệt, Spring Boot có thể đưa ra phần Failure Analysis dễ đọc hơn cho lỗi verification. Analyzer không thay thế việc đọc danh sách Violations và truy tìm source reference.

Một stack trace trỏ tới RuntimeApplicationModuleVerifier chỉ cho biết nơi kiểm tra thất bại. Vị trí code gây violation thường nằm trong một lớp ở module consumer, không phải trong verifier của framework.

## 9. Ví dụ phân tích một lần startup bị chặn

Giả sử production được cấu hình:

~~~yaml
spring:
  modulith:
    runtime:
      verification-enabled: true
~~~

Runtime classpath có spring-modulith-runtime. Khi khởi động, verifier phát hiện:

~~~text
Module 'order' depends on non-exposed type
'com.example.shop.inventory.internal.InventoryRepository'
~~~

Đây là thông báo minh họa để giải thích cách phân tích; định dạng thực tế phụ thuộc phiên bản và failure analyzer.

Phân tích:

| Thành phần | Giá trị |
|---|---|
| Consumer | order |
| Provider | inventory |
| Reference | InventoryRepository |
| Package | inventory.internal |
| Loại lỗi | Truy cập internal package |
| Điều kiện gây lỗi | inventory là closed và package internal chưa được expose |

Hướng sửa:

1. Xác định khả năng nghiệp vụ mà order thực sự cần.
2. Công bố interface ổn định, ví dụ InventoryAvailability, tại API package của inventory.
3. Để implementation và InventoryRepository ở package internal.
4. Thay dependency trong order để chỉ tham chiếu InventoryAvailability.
5. Chạy ApplicationModules.verify() trong test.
6. Chạy Spring context test để xác nhận bean implementation được inject qua interface.
7. Triển khai lại sau khi CI và staging đã xác nhận cấu trúc mới.

Không nên chuyển inventory thành OPEN chỉ để startup qua nếu order chỉ cần một capability nhỏ.

## 10. Dùng architecture test làm hàng rào trước runtime

Runtime verification nên là lớp bảo vệ bổ sung. Cách phát hiện sớm và ít rủi ro vận hành hơn là chạy module verification trong CI:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    @Test
    void verifiesModuleStructure() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

Khi test này chạy ở mỗi pull request hoặc pipeline build, violation được phát hiện trước khi artifact được đưa tới staging hoặc production.

Một pipeline hợp lý:

~~~mermaid
flowchart LR
    A["Code change"] --> B["Compile"]
    B --> C["Architecture test"]
    C --> D["Unit and integration tests"]
    D --> E["Build artifact"]
    E --> F["Deploy staging"]
    F --> G["Runtime verification"]
    G --> H["Deploy production"]
~~~

Runtime verification bảo vệ cả những đường triển khai mà test có thể không chạy hoặc cấu hình môi trường có thể khác. Tuy nhiên, không nên dùng runtime gate thay thế architecture test trong CI.

## 11. Triển khai runtime verification an toàn

Trước khi bật property trong môi trường có traffic, hãy thực hiện rollout có kiểm soát:

1. **Xác nhận phiên bản.** Dùng phiên bản Spring Modulith có runtime verification.
2. **Xác nhận dependency.** spring-modulith-runtime có trên runtime classpath.
3. **Bật trong môi trường phát triển.** Phát hiện vi phạm khi developer chạy ứng dụng.
4. **Bật trong CI hoặc staging.** Kiểm tra cùng source và cấu hình detection như production.
5. **Đánh giá log và startup time.** Xác nhận verifier hoàn thành và không tạo ra chậm trễ bất thường.
6. **Kiểm tra readiness.** Bảo đảm deployment chỉ chuyển instance sang ready sau khi startup hoàn tất.
7. **Rollout từng bước.** Theo dõi instance mới trước khi thay toàn bộ replica.
8. **Chuẩn bị rollback cấu hình hoặc artifact.** Nếu phát hiện một violation ngoài dự kiến, có thể quay lại phiên bản đã biết hoạt động theo quy trình vận hành.
9. **Giữ architecture test trong CI.** Không bỏ kiểm tra tĩnh sau khi đã bật runtime verification.

Nếu cần tắt tạm runtime gate để khôi phục dịch vụ, hãy xem đó là biện pháp giảm thiểu sự cố có kiểm soát. Ghi nhận lý do, phạm vi và thời hạn; tiếp tục sửa violation và bật lại kiểm tra. Không biến việc tắt verification thành cách xử lý lâu dài.

## 12. Detection strategy phải nhất quán giữa test và runtime

Runtime verification xây dựng module model từ production runtime configuration. Nếu test và runtime dùng các quy tắc phát hiện module khác nhau, hai nơi có thể nhìn thấy mô hình khác nhau.

Ví dụ:

- Test có custom ApplicationModuleDetectionStrategy nhưng cấu hình chỉ nằm trong test source.
- Production không có package metadata cần thiết cho explicit module detection.
- Root application class trong runtime khác với class được dùng trong test.
- Một số package bị ignored trong test nhưng không bị ignored trong runtime, hoặc ngược lại.

Tài liệu runtime của Spring Modulith lưu ý rằng customizations cho module detection cần được đặt trong production sources để các tính năng runtime sử dụng được, trừ khi chúng đã hiện diện ở đó.

Hãy xác nhận:

- Cùng root application class được sử dụng.
- Detection strategy giống nhau.
- @ApplicationModule và @NamedInterface có trong production artifact.
- Các customizations cần thiết không chỉ tồn tại trong test.
- Runtime classpath chứa các module và package cần được kiểm tra.

Nếu CI xanh nhưng runtime fail, khác biệt giữa test model và production model là một trong những điểm đầu tiên cần kiểm tra.

## 13. Kiểm tra phạm vi verification và rule bổ sung

Ngoài các quy tắc module cốt lõi, Spring Modulith có thể tích hợp thêm các rule kiến trúc từ jMolecules nếu dependency tương ứng hiện diện. Khi đó, runtime verification có thể phát hiện thêm violation theo các rule được kích hoạt.

Vì vậy, khi kết quả test và runtime khác nhau, hãy kiểm tra:

- Runtime classpath có dependency jMolecules mà test classpath không có hoặc ngược lại không?
- Có VerificationOptions tùy chỉnh trong test nhưng runtime dùng mặc định không?
- Có package/type bị loại trừ khỏi test model nhưng vẫn xuất hiện trong runtime model không?
- Có cấu hình detection hoặc module metadata chỉ tồn tại trong test source không?

Không nên kết luận rằng mọi lỗi bổ sung đều là lỗi Spring Modulith core. Hãy xác định rule nào phát ra violation và dependency nào kích hoạt rule đó.

## 14. Runtime verification ảnh hưởng thế nào tới deployment?

Khi property được bật, một module violation trở thành điều kiện không cho instance khởi động. Điều này có lợi cho tính toàn vẹn kiến trúc nhưng cần được tính vào chiến lược triển khai.

| Tình huống | Tác động có thể xảy ra | Biện pháp |
|---|---|---|
| Deploy artifact mới có violation | Instance mới fail startup | Chặn artifact từ CI architecture test |
| Cấu hình property bật nhầm ở production | Ứng dụng bắt đầu kiểm tra và có thể fail ngay | Review profile và effective configuration |
| Các replica dùng cấu hình khác nhau | Hành vi startup không nhất quán | Đồng bộ deployment configuration |
| Module detection khác giữa test và runtime | CI xanh nhưng production fail | Đưa customization vào production sources |
| Thêm dependency jMolecules làm phát sinh rule | Runtime có thêm verification failure | Review classpath và rule bổ sung |
| Rollout thay toàn bộ replica quá sớm | Nguy cơ giảm hoặc mất capacity phục vụ | Dùng rolling/canary rollout và readiness gate |

Runtime verification không tự thay thế health check, readiness probe hoặc rollback strategy. Nó chỉ quyết định mô hình module có vượt qua các quy tắc được cấu hình trước khi ứng dụng tiếp tục khởi động hay không.

## 15. Những cách xử lý sai cần tránh

| Cách xử lý | Rủi ro | Cách xử lý phù hợp |
|---|---|---|
| Tắt property vĩnh viễn ngay khi gặp violation | Mất lớp bảo vệ runtime mà không giải quyết kiến trúc | Dùng tắt tạm có thời hạn, sửa lỗi và bật lại |
| Chuyển module thành OPEN để bỏ lỗi internal access | Expose nhiều package hơn nhu cầu | Dùng API package gốc hoặc Named Interface |
| Thêm tất cả module vào allowedDependencies | Whitelist không còn thể hiện thiết kế | Chỉ cho phép dependency trực tiếp có chủ đích |
| Ignore toàn bộ violation | Che giấu dependency sai | Xử lý từng violation và chỉ ngoại lệ có lý do rõ |
| Chỉ chạy runtime verification, bỏ architecture test | Phát hiện quá muộn ở thời điểm deploy/startup | Giữ test verification trong CI |
| Sửa log hoặc failure analyzer thay vì source | Không loại bỏ dependency vi phạm | Lần về consumer và reference gây lỗi |
| Giả định CI xanh bảo đảm runtime không fail | Test/runtime model hoặc classpath có thể khác | Đồng bộ detection, dependencies và production metadata |

## 16. Checklist trước khi bật runtime verification

- [ ] Dự án dùng phiên bản Spring Modulith hỗ trợ runtime verification.
- [ ] spring-modulith-runtime có trên runtime classpath.
- [ ] Property spring.modulith.runtime.verification-enabled được đặt có chủ đích.
- [ ] Nhóm hiểu property mặc định là false.
- [ ] ApplicationModules.verify() đã chạy trong architecture test của CI.
- [ ] Không còn dependency cycle.
- [ ] Không còn truy cập internal package trái quy tắc.
- [ ] allowedDependencies khớp với dependency trực tiếp.
- [ ] Named Interface được khai báo và tham chiếu đúng.
- [ ] Runtime và test dùng cùng root application class/detection strategy.
- [ ] Custom module detection nằm trong production sources.
- [ ] Các rule bổ sung trên runtime classpath đã được hiểu rõ.
- [ ] Staging khởi động thành công với cùng cấu hình verification.
- [ ] Readiness và rollout strategy đã tính tới trường hợp startup abort.
- [ ] Có quy trình rollback và khôi phục cấu hình được kiểm soát.

## 17. Checklist khi ứng dụng không khởi động

- [ ] Xác nhận runtime verification có thực sự được bật không.
- [ ] Xác nhận spring-modulith-runtime có trong runtime classpath không.
- [ ] Tìm RuntimeApplicationModuleVerifier hoặc Violations trong log.
- [ ] Đọc toàn bộ danh sách violation và loại rule.
- [ ] Ghi lại consumer, provider và kiểu/package liên quan.
- [ ] Phân biệt module violation với BeanCreationException, configuration error hoặc infrastructure failure.
- [ ] So sánh module detection giữa test và runtime.
- [ ] Kiểm tra profile, environment variable và property override.
- [ ] Sửa source/API/dependency metadata theo nguyên nhân.
- [ ] Chạy architecture test và context test trước khi deploy lại.
- [ ] Theo dõi readiness và log của instance mới trong rollout.

## 18. Kết luận

Một application module violation có thể làm ứng dụng không khởi động nếu runtime verification được bật. Điều kiện cần là artifact spring-modulith-runtime có trên runtime classpath và property spring.modulith.runtime.verification-enabled được đặt thành true; mặc định property là false. Khi được kích hoạt, RuntimeApplicationModuleVerifier kiểm tra module arrangement trong startup và abort nếu phát hiện violation.

Các lỗi thường gặp gồm dependency cycle, truy cập internal package và dependency trực tiếp ngoài allowedDependencies. Hãy phân biệt chúng với lỗi Spring bean creation hoặc hạ tầng, đọc đầy đủ diagnostic và lần về consumer/provider/reference gây ra violation. Để giảm rủi ro triển khai, chạy ApplicationModules.verify() trong CI, đồng bộ module detection giữa test và runtime, bật runtime gate ở staging trước production và có kế hoạch rollback rõ ràng. Runtime verification là lớp bảo vệ bổ sung cho ranh giới kiến trúc; nó cần đi cùng test tự động và quy trình rollout có kiểm soát.

## Tài liệu tham khảo

- [Spring Modulith — Runtime Support](https://docs.spring.io/spring-modulith/reference/runtime.html)
- [Spring Modulith — Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html)
- [Spring Modulith — Configuration Properties](https://docs.spring.io/spring-modulith/reference/appendix.html)
- [Spring Modulith — Runtime Failure Analyzer API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/runtime/autoconfigure/FailedModuleVerificationFailureAnalyzer.html)
