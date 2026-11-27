# Đọc log startup để khoanh vùng

## Mục tiêu

Khi một ứng dụng Spring Boot khởi động không thành công, log startup thường chứa đủ dấu vết để xác định lỗi nằm ở cấu hình, tạo bean, kết nối hạ tầng hay bước kiểm tra kiến trúc. Tuy nhiên, log có thể dài và một ngoại lệ ở cuối stack trace chưa chắc là nguyên nhân đầu tiên. Đọc log theo thứ tự khởi động và theo mối quan hệ giữa các thông báo giúp rút ngắn thời gian tìm lỗi.

Trong ứng dụng modular monolith sử dụng Spring Modulith, việc khoanh vùng còn cần phân biệt lỗi khởi tạo Spring ApplicationContext với lỗi xác minh mô hình module. `ApplicationModules.verify()` kiểm tra cấu trúc module khi ứng dụng hoặc bài test gọi phương thức này. Spring Boot không tự động chạy kiểm tra kiến trúc đó trong mọi lần khởi động chỉ vì dự án có dependency Spring Modulith. Vì vậy, người đọc log cần biết bước xác minh được gọi ở đâu và vào thời điểm nào.

Sau bài học, bạn có thể:

- Nhận biết các mốc chính trong log startup của Spring Boot.
- Tìm lỗi đầu tiên, lần theo `Caused by` và xác định thành phần khởi tạo thất bại.
- Phân biệt lỗi cấu hình, bean, kết nối và lỗi từ `ApplicationModules.verify()`.
- Bật log chi tiết có chọn lọc để thu thập thêm bằng chứng.
- Dùng tên package, class, profile và thời điểm để khoanh vùng module liên quan.
- Ghi lại kết quả chẩn đoán có thể lặp lại sau khi sửa lỗi.

## 1. Hiểu trình tự khởi động trước khi đọc log

Một lần khởi động Spring Boot thường đi qua các giai đoạn sau:

1. JVM chạy phương thức `main` và `SpringApplication.run(...)`.
2. Spring Boot đọc tham số dòng lệnh, cấu hình, biến môi trường và profile đang hoạt động.
3. ApplicationContext được tạo và các cấu hình tự động được đánh giá.
4. Bean được đăng ký, khởi tạo và tiêm phụ thuộc; các callback và listener vòng đời được thực thi.
5. Web server được khởi động nếu ứng dụng có cấu hình web.
6. Ứng dụng phát thông báo `Started ...` khi quá trình khởi động hoàn tất.

Một thành phần có thể thất bại ở bất kỳ giai đoạn nào. Ví dụ, thiếu biến môi trường có thể làm cấu hình DataSource thất bại trước khi bean nghiệp vụ được tạo. Một bean listener có thể thất bại trong lúc ApplicationContext khởi tạo. Một kiểm tra kiến trúc được gọi từ `ApplicationRunner` có thể thất bại sau khi context đã được tạo nhưng trước khi `SpringApplication.run(...)` trả về.

Hãy dùng các mốc trong log để xác định ứng dụng đã đi đến đâu. Nếu có dòng `Started ShopApplication`, context đã hoàn tất quá trình khởi động theo luồng thông thường. Nếu lỗi xuất hiện trước dòng này, hãy tập trung vào giai đoạn khởi tạo. Nếu lỗi xuất hiện sau đó, có thể đó là lỗi của request, tác vụ nền hoặc listener sự kiện trong lúc ứng dụng đang chạy.

## 2. Nhận diện các dòng log quan trọng

Log mặc định của Spring Boot thường chứa thời gian, mức log, process ID, thread, logger và thông điệp. Ví dụ minh họa:

```text
2026-11-27T08:30:10.125+07:00  INFO 18420 --- [main] c.a.shop.ShopApplication : Starting ShopApplication using Java 21
2026-11-27T08:30:10.412+07:00  INFO 18420 --- [main] c.a.shop.ShopApplication : The following 1 profile is active: "dev"
2026-11-27T08:30:12.031+07:00  INFO 18420 --- [main] o.s.b.w.embedded.tomcat.TomcatWebServer : Tomcat initialized with port 8080 (http)
2026-11-27T08:30:12.894+07:00  INFO 18420 --- [main] c.a.shop.ShopApplication : Started ShopApplication in 2.91 seconds
```

Các dòng này cho biết:

- **`Starting ShopApplication`:** tiến trình đã bắt đầu chạy lớp ứng dụng nào.
- **Java version:** phiên bản JVM đang chạy, hữu ích khi lỗi phụ thuộc vào phiên bản Java.
- **Profile active:** profile quyết định các cấu hình và bean có điều kiện được sử dụng.
- **Server initialized:** web server đã được cấu hình và chuẩn bị mở cổng.
- **`Started ShopApplication`:** mốc khởi động thành công thường dùng để phân biệt lỗi startup với lỗi runtime xảy ra sau đó.

Đừng chỉ tìm chữ `ERROR`. Một thông báo `WARN` trước đó có thể chỉ ra cấu hình đang dùng giá trị mặc định hoặc một thành phần không được kích hoạt. Ngược lại, một số lỗi nghiêm trọng được in ra dưới dạng stack trace sau thông báo `APPLICATION FAILED TO START`.

## 3. Tìm điểm thất bại và lần theo nguyên nhân gốc

Khi ứng dụng không khởi động, hãy đọc log theo trình tự sau:

1. Tìm thông báo `APPLICATION FAILED TO START` hoặc dòng `ERROR` đầu tiên trong lần chạy.
2. Đọc phần `Description` và `Action` nếu Spring Boot in ra báo cáo lỗi cấu hình.
3. Tìm stack trace ngay sau thông báo đó.
4. Lần theo các đoạn `Caused by:` để tìm ngoại lệ cụ thể nhất giải thích được lỗi.
5. Ghi lại class, package, bean name hoặc resource được nhắc đến trong ngoại lệ.
6. Đối chiếu thời điểm lỗi với giai đoạn startup để biết thành phần nào đang được khởi tạo.

Ví dụ:

```text
APPLICATION FAILED TO START

Description:

Parameter 0 of constructor in com.acme.shop.orders.OrderService
required a bean of type 'com.acme.shop.inventory.InventoryReservation'
that could not be found.

Action:

Consider defining a bean of type
'com.acme.shop.inventory.InventoryReservation' in your configuration.
```

Thông báo này cho biết `OrderService` cần một bean `InventoryReservation`, nhưng Spring không tìm thấy bean phù hợp. Đây là lỗi wiring của Spring. Nó có thể liên quan đến việc module `inventory` chưa khai báo implementation, component scan không bao phủ package, profile không kích hoạt bean hoặc cấu hình điều kiện không thỏa mãn. Chỉ riêng thông báo này chưa chứng minh rằng ranh giới module bị vi phạm.

### Đọc `Caused by` đúng cách

Một ngoại lệ có thể được bọc nhiều lớp. Ví dụ `BeanCreationException` có thể chứa `UnsatisfiedDependencyException`, rồi đến `NoSuchBeanDefinitionException`. Hãy tìm nguyên nhân cụ thể nhất và đọc cả các frame gần nơi lỗi được phát sinh.

Không phải lúc nào dòng `Caused by` sâu nhất cũng là nguyên nhân cần sửa. Một `SQLException` có thể là nguyên nhân gốc khi không kết nối được database; nhưng nếu nó xuất hiện vì cấu hình URL sai, thông tin cấu hình mới là điều cần sửa. Hãy kết hợp ngoại lệ với bean hoặc resource đang được tạo tại thời điểm đó.

## 4. Phân loại lỗi thường gặp từ log startup

| Dấu hiệu | Ý nghĩa thường gặp | Hướng khoanh vùng |
|---|---|---|
| `NoSuchBeanDefinitionException` | Không có bean phù hợp với kiểu được yêu cầu | Kiểm tra implementation, component scan, profile và điều kiện tạo bean |
| `NoUniqueBeanDefinitionException` | Có nhiều bean cùng thỏa mãn kiểu injection | Kiểm tra `@Qualifier`, `@Primary` và các cấu hình khai báo bean |
| `UnsatisfiedDependencyException` | Một bean không thể nhận đủ dependency | Lần theo constructor hoặc field được nêu và đọc ngoại lệ nguyên nhân bên trong |
| `BeanCreationException` | Bean thất bại trong lúc khởi tạo | Đọc bean name, factory method và `Caused by` |
| `BeanCurrentlyInCreationException` | Có thể có vòng tham chiếu trong quá trình tạo bean | Vẽ lại chuỗi bean phụ thuộc và xem xét trách nhiệm giữa các module |
| `ClassNotFoundException` hoặc `NoClassDefFoundError` | Thiếu class ở classpath hoặc lỗi nạp class | Kiểm tra dependency, phiên bản và runtime classpath |
| `NoSuchMethodError` | Mã đã biên dịch với API khác phiên bản đang chạy | Kiểm tra dependency tree và xung đột phiên bản |
| `Connection refused`, timeout hoặc lỗi xác thực | Không kết nối được dịch vụ hạ tầng | Kiểm tra host, port, credential, network và trạng thái dịch vụ |
| `ApplicationModules` hoặc `Violations` trong stack trace | Có thể bước xác minh mô hình module đã phát hiện vi phạm | Tìm nơi gọi `verify()` và đọc từng vi phạm được liệt kê |

Các dấu hiệu trên là điểm bắt đầu để điều tra, không phải kết luận tự động. Ví dụ `BeanCreationException` có thể do thiếu cấu hình, lỗi truy cập database hoặc lỗi trong constructor của bean. Cần dùng thông tin bean và nguyên nhân lồng bên trong để phân biệt.

## 5. Nhận biết lỗi xác minh Spring Modulith

Spring Modulith cung cấp mô hình module thông qua `ApplicationModules`. Một bài test hoặc một đoạn mã ứng dụng có thể tạo mô hình từ lớp ứng dụng và gọi `verify()`:

```java
ApplicationModules modules = ApplicationModules.of(ShopApplication.class);
modules.verify();
```

Khi `verify()` phát hiện vi phạm, nó ném lỗi `Violations` chứa thông tin về các vấn đề trong mô hình module. Log hoặc kết quả test có thể cho thấy các loại vấn đề như:

- Module truy cập kiểu thuộc package nội bộ của module khác.
- Hai hoặc nhiều module tạo thành dependency cycle.
- Một module phụ thuộc vào module hoặc Named Interface không nằm trong `allowedDependencies`.
- Cấu trúc package hoặc Named Interface không khớp với hợp đồng kiến trúc đã khai báo.

Ví dụ minh họa khi ứng dụng gọi kiểm tra kiến trúc trong một bước startup:

```text
ERROR ... o.s.boot.SpringApplication : Application run failed
org.springframework.modulith.core.Violations: Module 'orders' depends on ...
    at org.springframework.modulith.core.ApplicationModules.verify(...)
    at com.acme.shop.ModuleArchitectureStartupCheck.run(...)
    at org.springframework.boot.SpringApplication.callRunner(...)
```

Trong ví dụ này, frame `ModuleArchitectureStartupCheck.run(...)` cho biết kiểm tra được gọi từ `ApplicationRunner`. Hãy đọc phần thông báo vi phạm phía trên stack trace để xác định module nguồn, module đích và kiểu/package liên quan.

**Lưu ý về thời điểm chạy:** Spring Modulith không tự động gọi `ApplicationModules.verify()` trong mọi lần Spring Boot khởi động chỉ vì dependency đã có mặt. Nhiều dự án chạy kiểm tra này trong JUnit test. Nếu log startup có `Violations`, hãy tìm lời gọi tường minh trong ứng dụng hoặc integration đang chạy. Nếu không có log về `verify()`, không thể kết luận rằng cấu trúc module đã được xác minh thành công.

### Khi nào nên gọi verify trong startup?

Thông thường, giữ `ApplicationModules.verify()` trong architecture test để build kiểm tra cấu trúc trước khi triển khai. Trong môi trường phát triển, nhóm có thể muốn chạy kiểm tra khi ứng dụng khởi động để nhận phản hồi ngay. Nếu chọn cách này, hãy làm rõ profile nào kích hoạt nó và hiểu rằng lỗi xác minh sẽ khiến ứng dụng không hoàn tất startup.

Ví dụ một startup check có điều kiện theo profile:

```java
package com.acme.shop;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;
import org.springframework.modulith.core.ApplicationModules;

@Component
@Profile("architecture-check")
class ModuleArchitectureStartupCheck implements ApplicationRunner {

    @Override
    public void run(ApplicationArguments args) {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
```

Khi bật profile `architecture-check`, runner gọi xác minh sau khi ApplicationContext đã khởi tạo. Có thể kích hoạt cùng profile `dev` khi chạy cục bộ:

```bash
java -jar app.jar --spring.profiles.active=dev,architecture-check
```

Đây là một lựa chọn để minh họa thời điểm kiểm tra. Với pipeline CI, architecture test vẫn là cách rõ ràng để bảo vệ kiến trúc mà không buộc mọi instance production phải quét và xác minh lại mô hình ở mỗi lần khởi động.

## 6. Bật log chi tiết có chọn lọc

Nếu log mặc định chưa đủ thông tin, tăng mức log cho đúng package thay vì bật DEBUG cho toàn bộ ứng dụng.

Trong `application.yml` của môi trường cần chẩn đoán:

```yaml
logging:
  level:
    root: INFO
    org.springframework.boot: INFO
    org.springframework.context: INFO
    org.springframework.modulith: DEBUG
    com.acme.shop: DEBUG
```

Ý nghĩa:

- `root: INFO` giữ mức log chung ở mức vừa phải.
- `org.springframework.boot` giúp quan sát các thông báo thuộc Spring Boot.
- `org.springframework.context` có thể bổ sung dấu vết về ApplicationContext và bean lifecycle khi thư viện phát log ở mức tương ứng.
- `org.springframework.modulith` bật DEBUG cho logger thuộc package Spring Modulith nếu thành phần tương ứng có phát log ở mức này.
- `com.acme.shop` giúp theo dõi log do chính các module nghiệp vụ ghi ra.

Việc đặt mức DEBUG không bảo đảm mọi thư viện sẽ in thêm thông tin. Nếu một thành phần không phát log ở mức đó, bạn sẽ không thấy dòng mới. Khi cần biết một bean được tạo từ cấu hình nào, có thể dùng thêm báo cáo điều kiện của Spring Boot.

Chạy ứng dụng với `--debug`:

```bash
java -jar app.jar --debug
```

Hoặc truyền mức log theo từng package:

```bash
java -jar app.jar --logging.level.org.springframework.modulith=DEBUG --logging.level.com.acme.shop=DEBUG
```

`--debug` của Spring Boot chủ yếu bật condition evaluation report để giải thích các cấu hình tự động được áp dụng hoặc không được áp dụng. Nó không tương đương với việc đặt mọi logger của ứng dụng và framework thành DEBUG.

Sau khi thu thập đủ bằng chứng, đưa logger về mức phù hợp. Log quá chi tiết có thể làm tín hiệu quan trọng bị chìm trong lượng thông tin lớn.

## 7. Lọc log để tìm đúng thông tin

Với file log lớn, tìm theo nhóm từ khóa trước rồi đọc vùng dòng xung quanh kết quả. Trên Windows PowerShell có thể dùng `Select-String`:

```powershell
Select-String -Path .\logs\application.log -Pattern 'APPLICATION FAILED TO START|Caused by:|Exception|ERROR|ApplicationModules|Violations|Started .*Application'
```

Nếu máy đã có ripgrep, có thể dùng:

```bash
rg -n -i "APPLICATION FAILED TO START|Caused by:|Exception|ERROR|ApplicationModules|Violations|Started .*Application" ./logs/application.log
```

Sau khi tìm được dòng liên quan:

1. Ghi lại số dòng hoặc timestamp.
2. Đọc một đoạn trước và sau dòng đó để thấy thông báo mở đầu và stack trace đầy đủ.
3. Tìm lần xuất hiện đầu tiên của bean hoặc class được nhắc đến.
4. Đối chiếu logger name với package để biết log đến từ Spring Boot, Spring Framework, Spring Modulith hay mã ứng dụng.
5. Nếu log chứa nhiều lần khởi động, tách theo process ID, container hoặc timestamp để tránh ghép các sự kiện từ những lần chạy khác nhau.

Không nên chỉ sao chép một dòng `ERROR` rồi kết luận. Một dòng đơn lẻ thường thiếu nguyên nhân lồng bên trong hoặc thiếu thông tin về profile và bean đang được tạo.

## 8. Dùng package và profile để khoanh vùng module

Trong modular monolith, package thường cho biết module sở hữu lớp. Khi log nhắc đến `com.acme.shop.orders.OrderService`, hãy bắt đầu từ module `orders`. Khi log nhắc đến `com.acme.shop.inventory.internal.StockRepository`, hãy xác định đó là chi tiết nội bộ của `inventory`.

Tuy nhiên, class được nhắc đến không nhất thiết là nơi gây ra lỗi gốc. Ví dụ `OrderService` có thể thất bại khi tiêm `InventoryReservation`; lỗi có thể nằm ở cấu hình hoặc implementation của `inventory`. Hãy phân biệt:

- **Bean yêu cầu dependency:** class có constructor hoặc field đang cần một bean.
- **Bean cung cấp dependency:** implementation hoặc factory method tạo bean đó.
- **Nguyên nhân gốc:** lỗi khiến bean cung cấp không được tạo hoặc không được đăng ký.

Profile cũng là bằng chứng quan trọng. Nếu bean chỉ được khai báo với `@Profile("dev")` nhưng log cho thấy profile đang hoạt động là `prod`, Spring sẽ không đăng ký bean đó. Khi thấy `NoSuchBeanDefinitionException`, hãy kiểm tra profile trước khi thay đổi package hoặc thêm một implementation mới.

Với cấu hình có điều kiện, báo cáo `--debug` giúp xem các auto-configuration nào match hoặc không match. Dùng báo cáo này để kiểm tra giả thuyết, chẳng hạn một DataSource hoặc integration bean không được tạo vì thiếu property.

## 9. Phân biệt lỗi startup với lỗi sau startup

Không phải mọi lỗi xuất hiện gần thời điểm khởi động đều là lỗi startup.

| Thời điểm và dấu hiệu | Cách hiểu | Hướng xử lý |
|---|---|---|
| Trước `Started ...`, có `Application run failed` | Quá trình khởi động thất bại | Đọc ngoại lệ đầu tiên và chuỗi `Caused by` |
| Có `Started ...`, sau đó request trả lỗi | Ứng dụng đã khởi động; lỗi có thể nằm trong controller, service hoặc dependency runtime | Dùng timestamp, request ID và stack trace của request |
| Có `Started ...`, sau đó listener ghi lỗi | Lỗi xử lý sự kiện hoặc tác vụ nền | Xác định listener, payload, publication và chính sách phục hồi |
| Có `Started ...`, sau đó mất kết nối database | Lỗi hạ tầng trong thời gian chạy | Kiểm tra pool, network, credential và trạng thái database |
| Test thất bại tại `ApplicationModules.verify()` nhưng ứng dụng chạy bình thường | Architecture test phát hiện vi phạm mô hình module | Đọc báo cáo test và sửa cạnh phụ thuộc hoặc hợp đồng module |

Nếu listener bất đồng bộ thất bại sau khi ứng dụng đã chạy, Spring Boot có thể không dừng toàn bộ process. Hãy xem log của listener và cơ chế theo dõi publication mà ứng dụng đã cấu hình. Không coi dòng `Started ...` là bằng chứng mọi luồng nghiệp vụ hoặc listener đều hoạt động đúng.

## 10. Quy trình khoanh vùng có thể lặp lại

Áp dụng quy trình này mỗi khi gặp lỗi startup hoặc runtime verification:

1. **Ghi nhận môi trường:** phiên bản Java, phiên bản ứng dụng, profile, command line và instance/container đang chạy.
2. **Xác định mốc:** tìm `Starting`, profile active, server startup, `Started` hoặc `Application run failed`.
3. **Chọn lỗi đầu tiên có liên quan:** tìm thông báo đầu tiên gắn với lần chạy hiện tại, không chỉ lấy dòng cuối cùng.
4. **Lần theo nguyên nhân:** đọc bean, class, resource và các đoạn `Caused by`.
5. **Phân loại:** cấu hình, bean wiring, classpath, hạ tầng, kiểm tra module hay lỗi runtime sau startup.
6. **Ánh xạ về module:** dùng package và class để xác định module sở hữu; lần tiếp dependency đến bean hoặc API được yêu cầu.
7. **Tạo giả thuyết cụ thể:** ví dụ profile không kích hoạt bean, component scan sai package, dependency version lệch hoặc module truy cập API nội bộ.
8. **Thu thập bằng chứng bổ sung:** bật DEBUG có chọn lọc, dùng `--debug` khi cần condition report và lọc log theo timestamp.
9. **Sửa nguyên nhân:** thay đổi cấu hình, wiring hoặc hợp đồng module tương ứng.
10. **Chạy lại cùng điều kiện:** giữ nguyên profile và tham số liên quan để xác nhận lỗi biến mất và startup đi đến `Started ...`.
11. **Kiểm tra hành vi sau startup:** nếu thay đổi liên quan event listener hoặc tác vụ nền, xác nhận kết quả nghiệp vụ và log xử lý tương ứng.

Giữ lại command, profile, thông báo lỗi chính, nguyên nhân gốc và kết quả sau sửa trong ghi chú xử lý sự cố. Điều này giúp người khác tái hiện vấn đề mà không phải đoán lại môi trường.

## 11. Ví dụ phân tích một lỗi hoàn chỉnh

Giả sử ứng dụng khởi động với profile `dev` và log có đoạn sau:

```text
INFO  ... The following 1 profile is active: "dev"
WARN  ... Exception encountered during context initialization - cancelling refresh attempt
ERROR ... Application run failed
org.springframework.beans.factory.UnsatisfiedDependencyException:
  Error creating bean with name 'orderService'
Caused by: org.springframework.beans.factory.NoSuchBeanDefinitionException:
  No qualifying bean of type 'com.acme.shop.inventory.InventoryReservation' available
```

Một cách phân tích hợp lý:

1. Profile `dev` đã được kích hoạt, nên kiểm tra bean có điều kiện theo profile khác.
2. ApplicationContext dừng trong lúc khởi tạo, vì vậy đây là lỗi startup.
3. Bean không khởi tạo được là `orderService`.
4. `OrderService` yêu cầu `InventoryReservation` nhưng Spring không tìm thấy bean tương ứng.
5. Kiểm tra module `inventory`: có implementation nào được đăng ký bằng `@Component` hoặc `@Bean` không, implementation có bị giới hạn bởi profile khác không, và package có nằm trong phạm vi component scan không.
6. Nếu implementation tồn tại nhưng module khác không được phép sử dụng package đó, phân biệt lỗi wiring với lỗi kiến trúc. API công khai nên nằm ở package được module công khai; implementation vẫn thuộc module sở hữu.
7. Sau khi sửa, chạy lại ứng dụng với cùng profile `dev` và xác nhận có dòng `Started ShopApplication`.

Nếu sau đó architecture test vẫn thất bại với `Violations`, đó là một vấn đề khác: cấu trúc phụ thuộc cần được xem xét theo quy tắc Spring Modulith. Một ứng dụng có thể tạo được bean và khởi động thành công nhưng vẫn có kiến trúc module không hợp lệ nếu bài kiểm tra `verify()` chưa được chạy hoặc chưa được đặt đúng trong pipeline.

## 12. Mẫu ghi nhận kết quả chẩn đoán

Sau khi khoanh vùng, ghi lại kết quả theo mẫu ngắn sau:

| Trường | Giá trị cần ghi |
|---|---|
| Thời điểm | Timestamp và timezone của lần chạy lỗi |
| Môi trường | Java version, application version, profile và instance |
| Mốc startup | Lỗi xảy ra trước hay sau `Started ...` |
| Thành phần | Bean, class, package hoặc listener liên quan |
| Ngoại lệ chính | Loại exception và thông điệp nguyên nhân |
| Module liên quan | Module sở hữu class và module gọi nó |
| Giả thuyết | Nguyên nhân cụ thể cần kiểm chứng |
| Bằng chứng | Dòng log, condition report, stack trace hoặc test result |
| Cách sửa | Thay đổi cấu hình, wiring hoặc hợp đồng kiến trúc |
| Kết quả | Log sau sửa và hành vi đã được xác nhận |

Một ghi nhận tốt có thể được người khác dùng để tái hiện và kiểm chứng. Tránh ghi kết luận mơ hồ như “Spring lỗi” hoặc “Modulith không chạy”; hãy chỉ ra class, exception và giai đoạn xảy ra.

## 13. Bài tập thực hành

Thực hiện với ứng dụng cửa hàng có package gốc `com.acme.shop` và các module `orders`, `inventory`, `payments`.

**Nhiệm vụ A — Đọc startup thành công**

1. Chạy ứng dụng với profile `dev`.
2. Ghi lại dòng `Starting`, profile active, thông báo web server và `Started`.
3. Giải thích ứng dụng đã đi qua những giai đoạn nào.

**Nhiệm vụ B — Khoanh vùng lỗi bean**

1. Tạm thời bỏ đăng ký implementation cung cấp `InventoryReservation` trong môi trường thử nghiệm.
2. Khởi động ứng dụng và tìm `APPLICATION FAILED TO START` hoặc `Application run failed`.
3. Ghi lại bean yêu cầu dependency, exception nguyên nhân và package liên quan.
4. Khôi phục bean và xác nhận ứng dụng khởi động thành công.

**Nhiệm vụ C — Phân biệt lỗi kiến trúc**

1. Tạo một architecture test gọi `ApplicationModules.of(ShopApplication.class).verify()`.
2. Tạm thời tạo một phụ thuộc trái với quy tắc module đã thiết kế.
3. Chạy test và ghi lại nội dung `Violations`.
4. Giải thích vì sao lỗi này khác với `NoSuchBeanDefinitionException`.
5. Sửa phụ thuộc và chạy lại test.

**Nhiệm vụ D — Bật log có chọn lọc**

1. Đặt logger `com.acme.shop` và `org.springframework.modulith` ở mức DEBUG trong môi trường phát triển.
2. Chạy ứng dụng với `--debug` và quan sát condition evaluation report.
3. Lọc file log theo `ERROR`, `Caused by`, `ApplicationModules` và `Started`.
4. Ghi lại thông tin mới thu được và giải thích thông tin nào thực sự giúp khoanh vùng.
5. Đưa mức log về cấu hình bình thường sau khi hoàn thành.

## 14. Tiêu chí hoàn thành

- Xác định đúng profile, phiên bản Java và mốc startup của lần chạy đang điều tra.
- Phân biệt được lỗi trước `Started ...` với lỗi runtime xảy ra sau startup.
- Tìm được bean hoặc class liên quan và ngoại lệ nguyên nhân phù hợp.
- Phân biệt lỗi Spring wiring với lỗi kiến trúc từ `ApplicationModules.verify()`.
- Biết bật log chi tiết theo package và hiểu phạm vi của `--debug`.
- Ánh xạ được class hoặc package về module sở hữu và dependency liên quan.
- Có ghi nhận chẩn đoán gồm bằng chứng, giả thuyết, cách sửa và kết quả chạy lại.

Đọc log startup có hệ thống giúp nhóm xác định ứng dụng dừng ở giai đoạn nào, thành phần nào thất bại và module nào cần được kiểm tra. Khi kết hợp log Spring Boot với kiểm thử `ApplicationModules.verify()`, nhóm có thể tách bạch vấn đề khởi tạo runtime và vấn đề về ranh giới kiến trúc, từ đó sửa đúng nguyên nhân và giữ modular monolith ổn định khi phát triển.
