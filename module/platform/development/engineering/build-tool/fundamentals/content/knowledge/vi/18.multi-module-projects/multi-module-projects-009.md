# Thay đổi một mô-đun ảnh hưởng đến phạm vi kiểm chứng nào

Trong dự án Java nhiều mô-đun, một thay đổi thường bắt đầu ở một mô-đun nhưng tác động có thể lan sang các mô-đun khác. Nếu `app` sử dụng API của `domain`, thay đổi trong `domain` có thể làm `app` không biên dịch được hoặc hoạt động sai dù mã nguồn `app` không thay đổi. Ngược lại, nếu chỉ sửa một chi tiết nội bộ không ảnh hưởng hợp đồng của `domain`, phạm vi kiểm chứng có thể nhỏ hơn.

Vì vậy, sau mỗi thay đổi cần xác định **phạm vi bị ảnh hưởng** (*change impact scope*) rồi chọn các bước kiểm chứng tương ứng. Chỉ chạy test trong mô-đun vừa sửa có thể bỏ sót lỗi ở consumer. Chạy toàn bộ build cho mọi thay đổi lại có thể tốn thời gian và làm chậm phản hồi. Mục tiêu là kiểm chứng đủ các quan hệ có thể bị ảnh hưởng, dựa trên dependency graph, loại thay đổi và mức độ rủi ro.

## 1. Mô-đun thay đổi và mô-đun tiêu thụ

Một mô-đun thường cung cấp một phần chức năng hoặc một API cho các mô-đun khác. Mô-đun sử dụng nó được gọi là consumer (mô-đun tiêu thụ). Quan hệ này tạo thành dependency graph.

Ví dụ:

```text
                 :app
                   |
                   v
               :service
                   |
                   v
                :domain
                   ^
                   |
             :batch-worker
```

Trong sơ đồ, `:service` và `:batch-worker` phụ thuộc vào `:domain`; `:app` phụ thuộc vào `:service`. Nếu `:domain` thay đổi, các consumer trực tiếp là `:service` và `:batch-worker`. Consumer gián tiếp là `:app`, vì nó phụ thuộc vào `:service` mà `:service` lại phụ thuộc vào `:domain`.

Khi một mô-đun thay đổi, cần nhìn theo chiều ngược của quan hệ phụ thuộc để tìm những mô-đun có thể bị tác động:

- **Dependency/prerequisite:** mô-đun mà mô-đun đang xét sử dụng.
- **Direct dependent:** mô-đun phụ thuộc trực tiếp vào mô-đun đang xét.
- **Transitive dependent:** mô-đun phụ thuộc thông qua một hoặc nhiều mô-đun trung gian.
- **Affected set:** tập hợp mô-đun, task và kiểm thử cần xem xét do thay đổi có thể ảnh hưởng đến chúng.

Không phải mọi dependent đều chắc chắn bị lỗi. Dependency graph giúp tìm vùng có liên quan; loại thay đổi và hợp đồng API giúp quyết định cần kiểm chứng sâu đến đâu.

## 2. Vì sao chỉ kiểm thử mô-đun đã sửa có thể chưa đủ?

Giả sử `domain` có lớp:

```java
package com.example.domain;

public class Order {
    public String getNumber() {
        return "A-100";
    }
}
```

`service` sử dụng API đó:

```java
package com.example.service;

import com.example.domain.Order;

public class OrderService {
    public String displayNumber(Order order) {
        return order.getNumber();
    }
}
```

Nếu đổi tên `getNumber()` thành `number()` trong `domain` mà không giữ phương thức cũ, test bên trong `domain` vẫn có thể thành công. Nhưng `service` không còn biên dịch được vì nó vẫn gọi `getNumber()`.

Đây là lỗi ở ranh giới giữa các mô-đun. Để phát hiện, cần biên dịch ít nhất các consumer chịu ảnh hưởng, sau đó chạy test phù hợp của chúng.

Một tình huống khác: API vẫn biên dịch nhưng ý nghĩa thay đổi. `getNumber()` trước đây trả về mã đơn hàng đã chuẩn hóa; sau thay đổi lại trả về giá trị chưa chuẩn hóa. Consumer có thể vẫn biên dịch nhưng logic nghiệp vụ hoặc integration test thất bại. Vì vậy, kiểm chứng không chỉ gồm compile; cần xét cả hành vi.

## 3. Phân loại thay đổi trước khi chọn phạm vi kiểm chứng

Loại thay đổi là yếu tố quan trọng để ước lượng vùng bị ảnh hưởng.

| Loại thay đổi | Ví dụ | Phạm vi cần xem xét |
|---|---|---|
| Thay đổi implementation nội bộ | Tối ưu thuật toán private, sửa điều kiện bên trong method | Test mô-đun thay đổi; test consumer theo rủi ro hành vi |
| Thay đổi public API | Đổi tên method, kiểu tham số, kiểu trả về hoặc visibility | Compile và test các direct/transitive consumer có sử dụng API |
| Thay đổi ngữ nghĩa API | Giữ chữ ký nhưng đổi quy tắc tính toán hoặc lỗi trả về | Unit test mô-đun, consumer test, contract/integration test liên quan |
| Thay đổi dependency | Nâng version thư viện hoặc đổi scope | Compile/test module dùng dependency và các consumer bị ảnh hưởng bởi API/metadata |
| Thay đổi resource/configuration | Đổi tên file, key cấu hình, schema hoặc template | Test nơi đọc resource, module triển khai và integration test |
| Thay đổi generated code | Sửa schema, generator hoặc annotation processor | Generator task, compile source được sinh và consumer của API sinh ra |
| Thay đổi test/build logic | Sửa test framework, convention plugin, task hoặc compiler option | Các module chịu cấu hình đó; có thể là toàn build |
| Thay đổi contract dùng chung | Schema REST, event, database migration hoặc message format | Producer, consumer, integration/contract test và triển khai liên quan |

Một thay đổi có thể thuộc nhiều loại. Ví dụ, đổi version BOM vừa là thay đổi dependency vừa có thể thay đổi public API được expose bởi module thư viện.

## 4. Phân biệt implementation detail và public API

Không phải mọi thay đổi trong một mô-đun đều có tác động giống nhau.

### Thay đổi implementation detail

Ví dụ:

```java
public class PriceCalculator {
    public Money calculate(Order order) {
        return applyDiscount(order);
    }

    private Money applyDiscount(Order order) {
        // Thay đổi thuật toán nội bộ tại đây.
        return order.total();
    }
}
```

Nếu chỉ sửa `applyDiscount` mà không thay đổi chữ ký hoặc hợp đồng của `calculate`, consumer có thể không cần biên dịch lại về mặt tương thích API. Tuy nhiên, hành vi của consumer có thể thay đổi, nên cần test mô-đun và những consumer phụ thuộc vào kết quả đó ở mức phù hợp.

### Thay đổi public API

Nếu đổi chữ ký:

```java
// Trước
public Money calculate(Order order)

// Sau
public CalculationResult calculate(Order order, PricingContext context)
```

consumer có thể cần sửa mã nguồn. Phạm vi kiểm chứng phải bao gồm các mô-đun gọi API này, cả trực tiếp lẫn gián tiếp nếu API được truyền qua lớp trung gian.

### API công khai có thể được phơi bày qua dependency

Với Gradle `java-library`, `api` và `implementation` giúp thể hiện dependency nào thuộc compile API của thư viện. Nếu một kiểu từ dependency xuất hiện trong public signature, consumer có thể cần dependency đó trên compile classpath.

Ví dụ:

```groovy
plugins {
    id 'java-library'
}

dependencies {
    api 'com.google.guava:guava:33.3.1-jre'
    implementation 'com.fasterxml.jackson.core:jackson-databind:2.17.2'
}
```

Nếu public API trả về `ImmutableList` của Guava, Guava là một phần của compile API và có thể cần khai báo bằng `api`. Jackson chỉ được dùng bên trong implementation thì có thể để `implementation`.

Khi thay đổi dependency scope hoặc kiểu được expose, consumer compile classpath có thể thay đổi dù mã nguồn consumer không được sửa. Vì vậy, thay đổi build metadata cũng cần được tính vào impact analysis.

## 5. Xây dựng phạm vi ảnh hưởng từ dependency graph

Trước khi chạy kiểm chứng, hãy xác định:

1. Mô-đun nào được sửa trực tiếp?
2. Mô-đun đó phụ thuộc vào những mô-đun nào?
3. Những mô-đun nào phụ thuộc trực tiếp vào nó?
4. Có consumer gián tiếp nào nhận API hoặc hành vi qua mô-đun trung gian không?
5. Có build logic, plugin, resource hoặc contract dùng chung nào bị thay đổi không?
6. Có hệ thống bên ngoài hoặc module triển khai nào tiêu thụ artifact này không?

Ví dụ dependency graph:

```text
                 :web-app
                    |
                    v
                 :orders
                 /     \
                v       v
           :domain   :persistence
                ^       ^
                 \     /
                :batch
```

Nếu `:domain` thay đổi, `:orders` và `:batch` là consumer trực tiếp. `:web-app` là consumer gián tiếp qua `:orders`. `:persistence` có thể không phụ thuộc vào `:domain` theo sơ đồ, nhưng nếu cả hai cùng dùng một schema hoặc contract bên ngoài, vẫn cần xem xét mối liên hệ đó.

Dependency graph chỉ mô tả quan hệ build được khai báo. Nó không tự phát hiện mọi quan hệ ở runtime, qua database, message broker, file cấu hình hoặc hệ thống khác. Người phát triển cần bổ sung hiểu biết về kiến trúc và contract của hệ thống.

## 6. Phạm vi kiểm chứng theo các lớp

Có thể chia việc kiểm chứng thành các lớp từ gần đến xa.

### Lớp 1: kiểm chứng mô-đun thay đổi

- Biên dịch mã nguồn chính.
- Chạy unit test.
- Kiểm tra resource và generated source liên quan.
- Chạy static analysis hoặc kiểm tra đặc thù của module nếu được yêu cầu.

Đây là phạm vi cơ bản cho hầu hết thay đổi.

### Lớp 2: kiểm chứng direct consumers

Biên dịch các mô-đun phụ thuộc trực tiếp để phát hiện lỗi chữ ký, classpath, resource hoặc dependency metadata. Nếu hành vi của API thay đổi, chạy test của các consumer đó.

### Lớp 3: kiểm chứng transitive consumers

Nếu public API hoặc hành vi được truyền qua nhiều tầng, mở rộng sang mô-đun phụ thuộc gián tiếp. Không nhất thiết mọi thay đổi implementation nhỏ đều phải chạy toàn bộ transitive consumer, nhưng thay đổi contract hoặc API chung thường cần phạm vi rộng hơn.

### Lớp 4: kiểm chứng tích hợp và hệ thống

Chạy integration test, contract test, end-to-end test hoặc smoke test cho những đường đi sử dụng chức năng đã thay đổi. Lớp này đặc biệt quan trọng khi thay đổi ảnh hưởng đến database, HTTP API, event, message schema hoặc cấu hình triển khai.

### Lớp 5: kiểm chứng toàn build hoặc release

Áp dụng khi thay đổi build logic dùng chung, toolchain, plugin, dependency platform/BOM, cấu hình repository, packaging hoặc các contract rộng. Có thể cần full build, toàn bộ test suite, package verification và kiểm tra artifact cuối.

```text
Module thay đổi
      |
      v
Compile + unit test
      |
      v
Direct consumers
      |
      v
Transitive consumers
      |
      v
Integration / contract / E2E
      |
      v
Full build / release verification
```

Không phải thay đổi nào cũng cần đi qua mọi lớp. Chọn điểm dừng dựa trên hợp đồng bị ảnh hưởng và mức rủi ro.

## 7. Chọn phạm vi kiểm chứng theo loại thay đổi

Bảng sau là gợi ý để lập kế hoạch; cần điều chỉnh theo kiến trúc thực tế.

| Thay đổi | Module đã sửa | Direct consumers | Transitive consumers | Integration/Full build |
|---|---|---|---|---|
| Sửa private method, giữ nguyên hợp đồng | Compile + unit test | Theo rủi ro hành vi | Thường chọn lọc | Nếu logic quan trọng hoặc có side effect |
| Sửa public method signature | Compile + unit test | Compile + test | Compile/test theo đường API | Thường cần integration test liên quan |
| Đổi ngữ nghĩa public method | Unit + contract test | Test hành vi | Test đường đi liên quan | Nên chạy integration/E2E phù hợp |
| Thêm dependency implementation-only | Compile + test | Kiểm tra runtime nếu dependency ảnh hưởng hành vi | Theo graph thực tế | Khi thay đổi runtime/packaging |
| Đổi dependency `api` hoặc public type | Compile + test | Compile + test | Theo API được truyền tiếp | Thường kiểm chứng tích hợp |
| Đổi resource key hoặc schema | Resource test | Consumer đọc resource | Consumer gián tiếp | Nên chạy integration test |
| Sửa shared convention plugin | Các module áp dụng plugin | Tất cả module dùng convention | Tùy plugin áp dụng | Thường cần full build đại diện hoặc toàn build |
| Nâng BOM/platform chung | Module dùng dependency | Module tiêu thụ API liên quan | Theo graph | Thường cần full verification |
| Sửa database migration | Module migration | Module truy cập dữ liệu | Service liên quan | Cần integration test trên database tương ứng |

## 8. Kiểm chứng trong Gradle multi-project

Gradle biểu diễn project dependency trong build model. Ví dụ `settings.gradle`:

```groovy
rootProject.name = 'commerce'
include 'domain', 'service', 'app'
```

`service/build.gradle`:

```groovy
dependencies {
    implementation project(':domain')
}
```

`app/build.gradle`:

```groovy
dependencies {
    implementation project(':service')
}
```

Quan hệ là:

```text
:app -> :service -> :domain
```

### Chạy kiểm chứng mô-đun thay đổi

```bash
./gradlew :domain:check
```

Task `check` của project `:domain` thường gom các kiểm tra được plugin áp dụng đăng ký, bao gồm test nếu cấu hình Java tiêu chuẩn được dùng. Nó cũng có thể chạy các task prerequisite cần thiết của `domain`.

### Chạy compile/test của consumer

```bash
./gradlew :service:compileJava :service:test
./gradlew :app:compileJava :app:test
```

Các lệnh này kiểm tra consumer trực tiếp và consumer tiếp theo trong ví dụ. Có thể ghép task vào cùng một lần chạy:

```bash
./gradlew :domain:check :service:check :app:check
```

Lệnh trên yêu cầu Gradle thực hiện các task `check` của ba project đã chọn. Gradle sẽ xử lý các prerequisite theo task graph.

### Một điểm quan trọng: task của dependency không tự chạy consumer

Khi chạy:

```bash
./gradlew :domain:build
```

Gradle xây dựng `:domain` và các dependency cần thiết của nó. Lệnh này không tự động chạy `:service:test` hoặc `:app:test` chỉ vì những project đó phụ thuộc vào `:domain`.

Quan hệ project dependency chủ yếu cho biết consumer cần artifact của producer. Task graph được tạo từ những task được yêu cầu và các prerequisite của chúng; nó không tự mở rộng sang tất cả project phụ thuộc ngược lại. Do đó, nếu cần kiểm chứng consumer, phải yêu cầu task của consumer một cách rõ ràng hoặc dùng workflow/CI có logic xác định affected projects.

### Xem dependency của một configuration

```bash
./gradlew :service:dependencies --configuration compileClasspath
```

Lệnh này giúp xem `:service` nhận dependency nào trên compile classpath. Khi cần hiểu một dependency cụ thể đến từ đâu:

```bash
./gradlew :service:dependencyInsight \
  --dependency domain \
  --configuration compileClasspath
```

Với project dependency, output có thể giúp thấy đường dependency và phiên bản/variant được chọn theo Gradle model. Cấu hình có thể khác tùy plugin và loại project.

### Xem task graph trước khi chạy

```bash
./gradlew :domain:check :service:check :app:check --dry-run
```

`--dry-run` hiển thị các task sẽ được xem xét mà không thực thi action của chúng. Đây là cách kiểm tra sơ bộ phạm vi task được đưa vào graph. Nó không chứng minh test sẽ pass và cũng không tự tìm mọi consumer bị ảnh hưởng.

## 9. Kiểm chứng trong Maven multi-module

Maven reactor quản lý các module được khai báo trong POM gốc và sắp xếp thứ tự build theo quan hệ giữa chúng.

Ví dụ root `pom.xml`:

```xml
<packaging>pom</packaging>

<modules>
    <module>domain</module>
    <module>service</module>
    <module>app</module>
</modules>
```

`service` khai báo dependency tới `domain`, còn `app` khai báo dependency tới `service`.

### Chọn module bằng `-pl`

```bash
mvn -pl domain test
```

`-pl` (*projects list*) chọn project/module cần build trong reactor. Lệnh này yêu cầu Maven chạy mục tiêu `test` cho module được chọn, nhưng nếu module cần một artifact reactor chưa được build hoặc cài đặt, có thể cần thêm tùy chọn chọn prerequisite.

### Thêm các dependency module bằng `-am`

```bash
mvn -pl domain -am verify
```

`-am` (*also make*) yêu cầu Maven đưa cả những project mà module được chọn phụ thuộc vào vào reactor build. Đây là hướng mở rộng về phía dependency/prerequisite.

### Thêm các module phụ thuộc vào module được chọn bằng `-amd`

```bash
mvn -pl domain -amd verify
```

`-amd` (*also make dependents*) yêu cầu Maven đưa các project phụ thuộc vào module được chọn vào reactor build. Đây là hướng mở rộng về phía consumer.

### Kết hợp dependency và dependent

```bash
mvn -pl domain -am -amd verify
```

Kết hợp hai tùy chọn có thể mở rộng reactor sang các prerequisite và dependent liên quan. Phạm vi cuối cùng phụ thuộc vào module được chọn, quan hệ reactor và cấu hình Maven. Hãy xem log reactor để xác nhận những project nào thực sự được đưa vào build.

Với một thay đổi API trong `domain`, `-amd` đặc biệt hữu ích vì nó giúp kiểm chứng các module tiêu thụ. Nếu các module đó lại cần prerequisite khác trong reactor, thêm `-am` để Maven có đủ đầu vào.

## 10. Phân biệt dependency graph với test dependency graph

Một module có thể phụ thuộc vào `domain` ở compile/runtime nhưng không có nghĩa mọi test trong `domain` tự động chạy khi test consumer.

Ví dụ:

```text
:app:test
   |
   +--> cần artifact của :service
             |
             +--> cần artifact của :domain
```

Khi chạy `:app:test`, Gradle cần các artifact prerequisite phù hợp. Điều đó không đồng nghĩa task `:domain:test` hoặc `:service:test` luôn được chạy. Test task của từng project là task riêng và chỉ chạy khi task graph đưa chúng vào.

Vì vậy, nếu muốn kiểm chứng unit test của cả chuỗi, hãy yêu cầu rõ:

```bash
./gradlew :domain:test :service:test :app:test
```

Maven `verify` trên reactor có thể chạy lifecycle cho các module đã được đưa vào reactor, nhưng cần chọn đúng tập module bằng `-pl`, `-am` và `-amd`.

## 11. Thay đổi public API cần kiểm chứng rộng hơn implementation detail

Hãy xét ví dụ `domain` đổi API:

```java
// Phiên bản cũ
public Order findById(String id)

// Phiên bản mới
public Optional<Order> findById(OrderId id)
```

Những tác động có thể xảy ra:

- `service` không biên dịch vì truyền `String` thay vì `OrderId`.
- `service` biên dịch sau khi sửa nhưng xử lý trường hợp không tìm thấy order khác trước.
- `app` có thể không gọi trực tiếp `domain`, nhưng vẫn bị ảnh hưởng qua thay đổi của `service`.
- Test fixture, mock hoặc test data builder dùng chữ ký cũ cần cập nhật.
- Module khác trong repository có thể sử dụng API thông qua test dependency hoặc plugin mà compile graph chính không thể hiện rõ.

Vì vậy, thay đổi public API nên kéo theo:

1. Compile mô-đun cung cấp API.
2. Compile direct consumers.
3. Compile transitive consumers có đường API bị ảnh hưởng.
4. Chạy unit test của các module liên quan.
5. Chạy contract/integration test của các đường nghiệp vụ sử dụng API.
6. Xác nhận artifact được publish hoặc đóng gói có metadata/API đúng.

Nếu API được nhiều dự án ngoài repository sử dụng, cần xem xét compatibility test hoặc kiểm tra consumer representative; dependency graph nội bộ không thể liệt kê mọi consumer bên ngoài.

## 12. Thay đổi implementation nội bộ có thể cần phạm vi nhỏ hơn

Giả sử chỉ tối ưu một private method trong `domain`, không đổi public signature, không đổi dữ liệu persistence và không đổi kết quả theo contract. Phạm vi cơ bản có thể gồm:

- Compile `domain`.
- Chạy unit test của `domain`.
- Chạy test của một số consumer quan trọng nếu logic mới có thể ảnh hưởng hành vi.
- Chạy integration test khi thay đổi liên quan đến I/O, transaction, concurrency hoặc hiệu năng có ý nghĩa.

Không nên mặc định mọi thay đổi private đều an toàn. Một thuật toán private có thể ảnh hưởng tới kết quả public, dữ liệu lưu trữ, thứ tự xử lý hoặc timing. Phạm vi kiểm chứng cần dựa vào hành vi bị tác động, không chỉ dựa vào modifier `private`.

## 13. Thay đổi resource và configuration có thể ảnh hưởng đến consumer runtime

Không phải thay đổi nào cũng thể hiện qua Java public API.

Ví dụ `domain` cung cấp một schema hoặc file cấu hình:

```text
domain/src/main/resources/
└── order-statuses.json
```

`service` đọc file theo đường dẫn cố định. Nếu đổi tên thành `statuses.json`, `service` vẫn có thể biên dịch nhưng runtime không tìm thấy resource.

Những thay đổi cần xem xét:

- Đổi tên hoặc di chuyển resource.
- Đổi key trong `application.yml` hoặc properties.
- Thay schema JSON/XML/Avro/Protobuf.
- Thay template, message bundle hoặc file SQL migration.
- Thay default value hoặc quy tắc phân giải cấu hình.

Phạm vi kiểm chứng nên bao gồm module đọc resource, module đóng gói resource, consumer runtime và integration test tương ứng. Compile-only checks không đủ để phát hiện mọi lỗi kiểu này.

## 14. Thay đổi generated source và annotation processor

Một module có thể tạo mã nguồn từ schema hoặc annotation processor. Thay đổi đầu vào generator có thể làm API được sinh ra đổi theo.

```text
schema / annotations
        |
        v
    generator task
        |
        v
generated Java source
        |
        v
    compile module
        |
        v
  downstream consumers
```

Nếu generator đổi tên method hoặc kiểu dữ liệu trong mã sinh, các consumer có thể bị ảnh hưởng dù file Java được viết tay không thay đổi.

Phạm vi kiểm chứng nên gồm:

- Chạy task sinh mã.
- Kiểm tra output được cập nhật và không còn file cũ mồ côi.
- Biên dịch module chứa mã sinh.
- Biên dịch/test consumer sử dụng API sinh ra.
- Chạy integration/contract test nếu schema là giao diện giữa các thành phần.

Nếu chỉ sửa implementation của generator nhưng output không thay đổi, vẫn cần test generator và một số build representative để xác nhận tính ổn định.

## 15. Thay đổi dependency hoặc version platform

Nâng một thư viện trong module có thể ảnh hưởng đến:

- Compile API mà module expose.
- Runtime behavior.
- Dependency bắc cầu và version được chọn.
- Service provider, reflection hoặc serialization.
- Packaging và kích thước artifact.
- Các module khác dùng cùng platform/BOM.

Nếu thay đổi chỉ trong một module, xem compile/runtime classpath của module đó và consumer liên quan. Nếu thay đổi BOM/platform ở root hoặc module platform chung, phạm vi có thể là mọi module import platform.

Gradle:

```bash
./gradlew :service:dependencies --configuration compileClasspath
./gradlew :service:dependencies --configuration runtimeClasspath
```

Maven:

```bash
mvn -pl service dependency:tree
```

Sau khi nâng version, nên chạy test module và consumer, đồng thời kiểm tra dependency graph để phát hiện version conflict hoặc dependency bị loại bỏ.

## 16. Thay đổi build logic dùng chung có thể ảnh hưởng toàn build

Một thay đổi ở root build, `buildSrc`, included build hoặc convention plugin có thể ảnh hưởng nhiều module dù không sửa source code của chúng.

Ví dụ:

- Thay compiler arguments hoặc Java toolchain.
- Thay cấu hình test framework hoặc test task.
- Đổi repository hoặc dependency resolution rule.
- Thay cách đóng gói JAR/WAR.
- Sửa convention plugin được nhiều module áp dụng.
- Nâng Gradle wrapper hoặc Maven plugin version dùng chung.
- Thay cấu hình annotation processor hoặc generated source.

Trong trường hợp này, affected set được xác định bởi những project áp dụng logic đó, không chỉ bởi project chứa file build logic. Nếu convention plugin được tất cả module Java sử dụng, cần kiểm chứng đại diện hoặc toàn bộ các module bị tác động theo mức rủi ro.

## 17. Contract bên ngoài dependency graph

Một mô-đun có thể không có project dependency trực tiếp tới consumer nhưng vẫn trao đổi dữ liệu qua:

- REST/HTTP API.
- Message queue hoặc event stream.
- Database schema.
- File exchange hoặc object storage.
- Shared cache hoặc protocol.
- Scheduled batch và hệ thống downstream.

Ví dụ, module `orders` đổi tên trường `orderNumber` thành `reference` trong JSON response. Một service khác trong repository có thể không được khai báo là Gradle project dependency vì nó chạy ở deployment độc lập. Dependency graph không phát hiện mối quan hệ đó.

Với contract change, phạm vi kiểm chứng phải dựa trên danh sách producer/consumer trong kiến trúc, schema registry, API contract hoặc deployment map. Cần kiểm tra tính tương thích ngược, khả năng triển khai theo từng bước và phiên bản consumer đang chạy.

Một cách giảm rủi ro là dùng contract test để xác nhận provider vẫn đáp ứng kỳ vọng của consumer, và consumer-driven contract test khi hệ thống có nhiều bên tích hợp độc lập.

## 18. Phạm vi kiểm chứng theo mức độ rủi ro

Không phải mọi thay đổi cùng loại đều có rủi ro như nhau. Có thể phân loại:

| Mức rủi ro | Dấu hiệu | Phạm vi gợi ý |
|---|---|---|
| Thấp | Refactor nội bộ, không đổi hành vi hoặc dependency | Compile và unit test module thay đổi |
| Trung bình | Đổi implementation ảnh hưởng kết quả, resource hoặc dependency nội bộ | Module thay đổi, direct consumers quan trọng, integration test liên quan |
| Cao | Đổi public API, schema, database, event hoặc shared dependency | Direct/transitive consumers, contract/integration test và full build phù hợp |
| Rất cao | Thay build logic toàn cục, toolchain, release plugin hoặc nền tảng dùng chung | Toàn bộ project chịu ảnh hưởng, clean/CI build và release verification đại diện |

Đây là hướng dẫn lập kế hoạch, không phải nhãn tự động. Một private method xử lý tiền tệ hoặc xác thực bảo mật có thể có rủi ro cao dù phạm vi code nhỏ. Ngược lại, một thay đổi tài liệu có thể không cần chạy test.

## 19. Không nhầm incremental build với phạm vi kiểm chứng

Gradle và Maven có thể bỏ qua một số công việc khi đầu vào không thay đổi hoặc kết quả được khôi phục từ cache. Điều đó giúp tiết kiệm thời gian nhưng không tự quyết định rằng những consumer nào cần được kiểm chứng.

**Incremental build** trả lời câu hỏi: task nào cần thực thi lại dựa trên input/output và trạng thái build.

**Change impact analysis** trả lời câu hỏi: những module, contract và hành vi nào có thể bị ảnh hưởng bởi thay đổi.

**Test selection** trả lời câu hỏi: test nào cần chạy để cung cấp bằng chứng phù hợp.

Ba khái niệm phối hợp nhưng không thay thế nhau. Một task có thể được đánh dấu `UP-TO-DATE`, trong khi test của consumer vẫn cần chạy vì hành vi mà test xác minh có thể bị ảnh hưởng. Ngược lại, một full build có thể chạy nhiều task nhưng không có nghĩa mọi test tích hợp bên ngoài đã được thực hiện.

## 20. Thiết kế CI theo phạm vi thay đổi

CI có thể sử dụng changed files, dependency graph và metadata module để chọn job phù hợp. Một pipeline có thể có các tầng:

```text
Pull request
    |
    v
Xác định module/file thay đổi
    |
    v
Phân loại thay đổi và tìm dependents
    |
    v
Compile + unit test module liên quan
    |
    v
Compile/test consumers bị ảnh hưởng
    |
    v
Contract/integration test theo rủi ro
    |
    v
Full verification trên nhánh chính hoặc release
```

Một số nguyên tắc:

- Nếu không thể xác định chắc chắn affected set, mở rộng phạm vi thay vì bỏ qua consumer có thể bị ảnh hưởng.
- Thay đổi shared build logic hoặc version platform thường cần phạm vi rộng.
- Giữ full verification định kỳ hoặc trên nhánh chính để phát hiện lỗi mà selective testing bỏ sót.
- Lưu lại module và test đã chọn để reviewer biết CI đã kiểm chứng phần nào.
- Không xem một job selective pass là bằng chứng toàn hệ thống đã được kiểm thử.

## 21. Ví dụ: sửa `domain` trong Gradle build

Giả sử build có:

```text
commerce/
├── settings.gradle
├── domain/
├── service/
├── batch-worker/
└── web-app/
```

Dependency:

```text
web-app -> service -> domain
batch-worker -> domain
```

### Trường hợp A: sửa private method trong `domain`

Chạy tối thiểu:

```bash
./gradlew :domain:check
```

Nếu method ảnh hưởng logic mà `service` và `batch-worker` sử dụng, thêm test của hai consumer:

```bash
./gradlew :service:test :batch-worker:test
```

Nếu logic đi qua endpoint của `web-app`, chạy thêm integration test hoặc test liên quan ở `web-app`.

### Trường hợp B: đổi public API của `domain`

Chạy:

```bash
./gradlew :domain:check \
  :service:compileJava :service:test \
  :batch-worker:compileJava :batch-worker:test \
  :web-app:compileJava :web-app:test
```

Lệnh này yêu cầu compile/test các consumer trực tiếp và gián tiếp đã biết trong sơ đồ. Nếu có integration test task riêng, cần gọi thêm task đó.

### Trường hợp C: sửa convention plugin áp dụng cho tất cả module Java

Không nên chỉ chạy `:domain:check`. Cần xác định mọi project áp dụng convention plugin và chạy các kiểm tra đại diện hoặc toàn bộ build, ví dụ:

```bash
./gradlew check
```

Nếu `check` của root không aggregate các project theo cách dự án mong đợi, hãy xác nhận cấu hình root hoặc gọi task theo từng project. Task graph thực tế là bằng chứng để kiểm tra phạm vi được chạy.

## 22. Ví dụ: sửa `domain` trong Maven reactor

Giả sử reactor có `domain`, `service`, `batch-worker` và `web-app`.

Chạy module thay đổi cùng prerequisite:

```bash
mvn -pl domain -am verify
```

Chạy module thay đổi cùng các dependent:

```bash
mvn -pl domain -amd verify
```

Kết hợp cả dependency và dependent:

```bash
mvn -pl domain -am -amd verify
```

Maven sẽ xây dựng các project được chọn theo thứ tự reactor. Kiểm tra log để xác nhận module nào đã được đưa vào và goal nào được thực thi. Nếu muốn chỉ chạy compile hoặc test thay vì toàn lifecycle `verify`, chọn goal phù hợp với mức kiểm chứng cần thiết.

Nếu module consumer không nằm trong cùng reactor, Maven không thể tự đưa nó vào bằng `-amd`. Cần build repository consumer riêng hoặc dùng pipeline phối hợp giữa các repository.

## 23. Các bước lập kế hoạch kiểm chứng cho một thay đổi

Một quy trình thực tế:

1. **Đọc phạm vi diff.** Xác định source, resource, test, build script, schema và dependency nào thay đổi.
2. **Xác định contract bị tác động.** Public API, event, database, resource path, configuration key hay build convention?
3. **Tìm consumer.** Dùng Gradle/Maven dependency graph và hiểu biết kiến trúc để liệt kê direct/transitive consumers.
4. **Phân loại rủi ro.** Đánh giá tác động đến compile, runtime, dữ liệu và triển khai.
5. **Chọn lớp kiểm chứng.** Module unit test, consumer compile/test, integration/contract test hoặc full build.
6. **Chạy kiểm chứng gần trước.** Bắt đầu với module thay đổi, sau đó mở rộng sang consumer và integration.
7. **Xem task graph/log.** Xác nhận các task cần thiết thực sự được đưa vào và thực thi hoặc được cache hợp lệ.
8. **Lưu bằng chứng.** Ghi lại command, module, test report, commit và kết quả.
9. **Ghi rõ giới hạn.** Nếu không chạy được một consumer hoặc môi trường tích hợp, nêu rõ phạm vi chưa được kiểm chứng.

## 24. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| Sửa module nào thì chỉ cần test module đó | Consumer có thể bị ảnh hưởng bởi API, hành vi, resource hoặc metadata của module đã sửa. |
| Gradle tự chạy mọi project phụ thuộc vào project được build | Gradle chạy task được yêu cầu và prerequisite; consumer task cần được yêu cầu rõ. |
| `:domain:build` kiểm chứng toàn bộ ứng dụng | Nó build project `domain` và prerequisite của nó, không tự test mọi dependent. |
| Mọi thay đổi private đều rủi ro thấp | Implementation private có thể thay đổi hành vi public, dữ liệu hoặc timing. |
| Compile consumer thành công nghĩa là hành vi đúng | Cần test hành vi và integration/contract test khi ngữ nghĩa thay đổi. |
| Dependency graph thể hiện mọi quan hệ hệ thống | Quan hệ database, HTTP, message và deployment có thể nằm ngoài build graph. |
| Maven `-am` và `-amd` giống nhau | `-am` thêm prerequisite; `-amd` thêm dependent. |
| Incremental build tự chọn đủ test cần thiết | Incremental task execution không thay thế change impact analysis hoặc test selection. |
| Chạy full build một lần chứng minh mọi môi trường đều đúng | Cần kiểm tra toolchain, cấu hình và môi trường triển khai phù hợp. |

## 25. Checklist xác định phạm vi kiểm chứng

Trước khi kết luận một thay đổi đã được kiểm chứng, hãy xác định:

- Module và file nào thay đổi?
- Thay đổi là implementation, public API, resource, dependency, generated code hay build logic?
- Direct consumers là những module nào?
- Có transitive consumers hoặc consumer bên ngoài repository không?
- Có contract database, HTTP, event hoặc message bị ảnh hưởng không?
- Compile của consumer đã được kiểm tra chưa?
- Unit test và integration/contract test nào cần chạy?
- Có module nào dùng shared convention plugin, BOM hoặc toolchain vừa thay đổi không?
- Task graph/ reactor thực tế có chứa các module cần kiểm chứng không?
- Báo cáo/log nào chứng minh các bước đã chạy?
- Phần nào chưa được kiểm chứng và vì sao?

## 26. Nguyên tắc áp dụng trong nhóm

Phạm vi kiểm chứng nên được xác định từ quan hệ giữa thay đổi và những thành phần tiêu thụ nó. Với thay đổi implementation hẹp, kiểm tra mô-đun và các hành vi liên quan có thể đủ. Với thay đổi public API, dependency metadata, resource contract hoặc schema, cần mở rộng sang consumer trực tiếp và gián tiếp. Với thay đổi build logic dùng chung hoặc nền tảng version, phạm vi thường rộng hơn nhiều và có thể cần full verification.

Dependency graph cung cấp điểm xuất phát để tìm module liên quan, nhưng kiến trúc runtime và contract bên ngoài cũng phải được xem xét. Gradle và Maven có lệnh chọn module và mở rộng phạm vi theo dependency/dependent; người phát triển cần hiểu hướng mở rộng của từng công cụ và xác nhận task thực tế đã chạy.

Một báo cáo kiểm chứng tốt cần nói rõ thay đổi nào đã được kiểm tra, module/test nào đã chạy và phần nào còn nằm ngoài phạm vi. Điều đó giúp reviewer đánh giá rủi ro dựa trên bằng chứng, đồng thời giữ thời gian build phù hợp với mức độ ảnh hưởng của thay đổi.
