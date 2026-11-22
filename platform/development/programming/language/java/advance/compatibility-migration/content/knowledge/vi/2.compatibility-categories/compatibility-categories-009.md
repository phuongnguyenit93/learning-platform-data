# Xác định ranh giới hợp đồng được hỗ trợ và chi tiết triển khai

Trong một đợt nâng cấp Java, không phải mọi lớp, method, package hay cấu hình đang tồn tại đều có mức cam kết tương thích như nhau. Có thành phần là hợp đồng mà consumer được quyền dựa vào; có thành phần chỉ là cách module thực hiện hợp đồng đó ở phiên bản hiện tại. Xác định ranh giới giữa hai nhóm giúp đội phát triển biết phần nào phải được bảo vệ khi chuyển đổi, phần nào có thể thay đổi nội bộ và cách thông báo khi cần thay đổi một cam kết đã công bố.

Nếu không xác định ranh giới này, hai tình huống đều dễ xảy ra. Một mặt, nhóm phát triển có thể vô tình phá vỡ API mà ứng dụng khác đang sử dụng. Mặt khác, nhóm có thể tự ràng buộc mình với mọi lớp phụ trợ, tên biến, cấu trúc dữ liệu và chi tiết thuật toán chỉ vì chúng từng xuất hiện trong mã nguồn. Cả hai đều làm quá trình migration khó dự đoán và tốn kém.

## 1. Hợp đồng được hỗ trợ là gì?

Hợp đồng được hỗ trợ là tập hợp các điểm tương tác, quy tắc và hành vi mà nhà cung cấp module công bố hoặc xác nhận rằng consumer có thể dựa vào trong phạm vi hỗ trợ đã nêu. Hợp đồng có thể được thể hiện qua API Java, cấu hình, giao thức, định dạng dữ liệu, plugin, task build, extension point hoặc hành vi runtime.

Một hợp đồng thường trả lời được các câu hỏi:

- Consumer được phép gọi, triển khai, kế thừa, cấu hình hoặc mở rộng thành phần nào?
- Đầu vào nào được chấp nhận và kết quả nào được cam kết?
- Điều kiện lỗi, exception, vòng đời và giới hạn sử dụng được quy định ra sao?
- Những phiên bản Java, framework, Gradle hoặc dependency nào nằm trong phạm vi hỗ trợ?
- Khi hợp đồng thay đổi, consumer được thông báo và có bao lâu để chuyển đổi?

Hợp đồng không chỉ là danh sách method `public`. Một property trong `application.yml`, một tên topic Kafka, một schema JSON, một task Gradle được tài liệu hóa hoặc một quy tắc về thứ tự callback đều có thể là hợp đồng nếu consumer được hướng dẫn hoặc được phép dựa vào chúng.

Ngược lại, một lớp `public` vẫn có thể là chi tiết nội bộ nếu nhà cung cấp ghi rõ nó không thuộc API được hỗ trợ, không xuất nó qua module boundary và có chính sách thay đổi phù hợp. Tuy nhiên, chỉ gọi một lớp là “internal” trong suy nghĩ của nhóm phát triển không đủ để loại bỏ rủi ro khi consumer thực tế đang sử dụng nó.

## 2. Chi tiết triển khai là gì?

Chi tiết triển khai là cách module hiện thực hóa hợp đồng mà không được cam kết như một điểm tương tác ổn định cho consumer. Nhóm phát triển có thể thay đổi những chi tiết này để cải thiện hiệu năng, độ tin cậy, khả năng bảo trì hoặc cấu trúc nội bộ, miễn là vẫn giữ các hợp đồng liên quan.

Ví dụ về chi tiết triển khai thường gặp:

- Tên biến cục bộ, cách chia method private và cấu trúc helper nội bộ.
- Cấu trúc dữ liệu nội bộ như `HashMap`, `ArrayList`, cache hoặc hàng đợi được dùng phía sau API.
- Thuật toán sắp xếp, chiến lược retry hoặc cách tối ưu truy vấn khi kết quả quan sát được vẫn đúng hợp đồng.
- Lớp triển khai cụ thể đứng sau một interface công khai.
- Package nội bộ, lớp package-private và resource không được công bố cho consumer.
- Cách tổ chức source set, module con hoặc file cấu hình nội bộ của quá trình build.

Một chi tiết chỉ thực sự nằm ngoài hợp đồng khi consumer không được cam kết dựa vào nó và việc thay đổi nó không phá vỡ một hành vi đã cam kết. Chẳng hạn, thứ tự phần tử trong một collection có thể là chi tiết triển khai nếu API không cam kết thứ tự. Nếu tài liệu nói kết quả được sắp xếp tăng dần, thứ tự đó đã trở thành hợp đồng hành vi dù cách sắp xếp cụ thể vẫn là chi tiết triển khai.

## 3. Phân biệt quyền truy cập Java và cam kết hỗ trợ

Java có các mức truy cập `public`, `protected`, package-private và `private`. Chúng kiểm soát khả năng truy cập ở cấp ngôn ngữ, nhưng không tự mô tả đầy đủ chính sách hỗ trợ của một thư viện hoặc nền tảng.

| Dấu hiệu trong Java | Ý nghĩa về quyền truy cập | Điều cần xác định thêm về hỗ trợ |
|---|---|---|
| `public` | Có thể được truy cập từ nơi phù hợp với classpath/module boundary | Có phải API công khai được hỗ trợ hay chỉ là kiểu cần public để framework hoặc cơ chế khác sử dụng? |
| `protected` | Có thể được truy cập từ subclass và các lớp cùng package theo quy tắc Java | Consumer có được phép kế thừa hoặc override không? Method có phải extension point ổn định không? |
| Package-private | Chỉ truy cập được trong cùng package theo quy tắc ngôn ngữ | Có package nội bộ nào được quản lý như một phần implementation riêng không? |
| `private` | Chỉ truy cập trực tiếp trong phạm vi lớp khai báo | Thường là chi tiết triển khai, nhưng reflection, serialization hoặc framework có thể tạo phụ thuộc ngoài dự kiến. |

Ví dụ, một thư viện có thể có lớp `public` để framework tạo instance, nhưng không muốn consumer khởi tạo trực tiếp hoặc phụ thuộc vào constructor của lớp đó. Nếu muốn giữ quyền thay đổi constructor, cần công bố factory hoặc interface được hỗ trợ, đồng thời ghi rõ lớp triển khai không phải API dành cho consumer.

Java Platform Module System (JPMS) bổ sung ranh giới module. Trong `module-info.java`, `exports` cho biết package được module khác truy cập theo quy tắc module; `opens` cho phép truy cập reflective trong phạm vi đã khai báo. Đây là cơ chế kỹ thuật hữu ích để thu hẹp bề mặt truy cập, nhưng bản thân `exports` cũng không thay thế tài liệu và chính sách tương thích. Một package được export vẫn cần được phân loại rõ là supported, experimental hay internal.

Ví dụ:

```java
module com.example.customer {
    exports com.example.customer.api;

    // Package implementation không được export cho consumer thông thường.
}
```

Trong ví dụ này, `com.example.customer.api` là ranh giới truy cập dự kiến. Nhóm vẫn cần công bố các kiểu và hành vi nào trong package là hợp đồng được hỗ trợ, phiên bản Java tối thiểu và cách xử lý khi API thay đổi.

## 4. Những nơi có thể chứa hợp đồng được hỗ trợ

### 4.1. API Java công khai

API Java gồm lớp, interface, enum, record, annotation, constructor, method và field mà consumer được phép sử dụng. Cần xác định cả khả năng gọi API lẫn khả năng mở rộng API.

Ví dụ, một thư viện công bố interface sau:

```java
package com.example.customer.api;

public interface CustomerLookup {
    Customer findById(String customerId);
}
```

Consumer có thể gọi `findById`. Nếu thư viện cũng cho phép consumer tự triển khai `CustomerLookup`, thì interface này còn là một extension point. Khi đó, thêm một method trừu tượng mới có thể làm mã nguồn consumer không biên dịch được hoặc làm implementation cũ không còn đáp ứng hợp đồng.

Những yếu tố cần ghi nhận trong hợp đồng API gồm:

- Kiểu tham số, kiểu trả về, generic bounds và các overload được hỗ trợ.
- Khả năng truyền `null`, giá trị mặc định và điều kiện đầu vào hợp lệ.
- Exception có thể phát sinh và điều kiện phát sinh.
- Quy tắc ownership và vòng đời của object, stream hoặc resource trả về.
- Thread-safety, khả năng gọi đồng thời và quy tắc callback nếu có cam kết.
- Interface mà consumer được phép triển khai, lớp mà consumer được phép kế thừa và method được phép override.
- Annotation, reflection metadata hoặc tên thành phần mà framework/consumer được hướng dẫn sử dụng.

Không phải mọi thay đổi `public` đều có cùng mức độ ảnh hưởng. Đổi tên method thường phá vỡ source compatibility và có thể phá vỡ binary compatibility. Thay đổi cách xử lý `null` có thể giữ nguyên chữ ký nhưng phá vỡ behavioral compatibility. Vì vậy, cần đánh giá từng chiều tương thích thay vì chỉ so sánh chữ ký method.

### 4.2. SPI và extension point

Service Provider Interface (SPI) cho phép consumer cung cấp implementation để module sử dụng. Các interface, abstract class, callback, plugin hook và cơ chế `ServiceLoader` thường tạo thành hợp đồng mở rộng.

Ví dụ:

```java
public interface PaymentGateway {
    PaymentResult charge(PaymentRequest request);
}
```

Nếu consumer tự triển khai `PaymentGateway`, nhóm phát triển phải xem xét ảnh hưởng của việc thêm method, đổi kiểu tham số, đổi thứ tự callback hoặc thay đổi điều kiện gọi. Nếu interface chỉ dành cho implementation nội bộ, cần tránh vô tình biến nó thành SPI công khai qua tài liệu, package export hoặc ví dụ dành cho người dùng.

Với `ServiceLoader`, các tên service, vị trí khai báo provider và quy tắc khởi tạo cũng có thể là hợp đồng. Khi chuyển đổi Java hoặc module system, cần xác nhận provider vẫn được phát hiện và khởi tạo đúng cách.

### 4.3. Cấu hình và biến môi trường

Tên property, kiểu dữ liệu, giá trị mặc định, đơn vị đo và cách ưu tiên giữa các nguồn cấu hình đều có thể là hợp đồng. Ví dụ:

```yaml
customer:
  client:
    connect-timeout: 2s
    retry-count: 3
```

Consumer có thể đã dựa vào `customer.client.connect-timeout` và `customer.client.retry-count`. Đổi tên property, đổi đơn vị từ giây sang mili giây hoặc thay đổi giá trị mặc định có thể làm hệ thống chạy khác đi dù toàn bộ Java API vẫn giữ nguyên.

Khi xác định ranh giới cấu hình, cần nêu rõ:

- Tên và kiểu của từng property được hỗ trợ.
- Property bắt buộc hay tùy chọn; giá trị mặc định và giới hạn hợp lệ.
- Đơn vị đo, định dạng và cách parse.
- Nguồn cấu hình được hỗ trợ và thứ tự ưu tiên.
- Cách xử lý property cũ, property không hợp lệ và property không còn được hỗ trợ.

### 4.4. Giao thức, schema và dữ liệu

HTTP endpoint, mã trạng thái, header, message broker topic, event name, JSON/XML schema, định dạng file, serialization và schema database đều có thể là hợp đồng giữa các hệ thống.

Ví dụ, một service trả về JSON với trường `customerId` dạng chuỗi. Đổi tên trường thành `id` có thể làm consumer không đọc được dữ liệu. Tương tự, đổi enum value, timezone, quy tắc làm tròn hoặc cách biểu diễn giá trị thiếu đều có thể gây incompatibility mà compiler Java không phát hiện.

Với dữ liệu lưu trữ, hợp đồng còn bao gồm khả năng đọc dữ liệu do phiên bản trước ghi ra và khả năng tương thích trong thời gian phiên bản cũ, mới cùng tồn tại. Migration schema cần xét cả ứng dụng đang chạy và công cụ đọc/ghi dữ liệu khác.

### 4.5. Hợp đồng build-time và công cụ phát triển

Một module có thể cung cấp Gradle plugin, convention plugin, task, extension DSL, annotation processor hoặc code generator. Consumer sử dụng những thành phần này trong build script hoặc pipeline CI.

Ví dụ:

```kotlin
plugins {
    id("com.example.java-conventions")
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(21))
    }
}
```

Nếu plugin công bố plugin ID, extension `java`, task hoặc property cấu hình, những tên và quy tắc được tài liệu hóa có thể là hợp đồng build-time. Thay đổi tên task, kiểu extension, thứ tự task hoặc cách áp dụng plugin có thể làm build của consumer hỏng dù ứng dụng chưa chạy.

Phạm vi hợp đồng cần được xác định cho từng loại consumer: người dùng plugin, người gọi task trực tiếp, người đọc output do task tạo ra hay chỉ pipeline nội bộ của nhà cung cấp. Không phải task nội bộ nào cũng cần giữ tên hoặc output ổn định.

### 4.6. Hành vi runtime và giới hạn vận hành

Hợp đồng có thể quy định hành vi quan sát được như thứ tự xử lý, tính idempotent, timeout, retry, transaction boundary, thread-safety, lifecycle hoặc cách giải phóng resource. Một số giới hạn hiệu năng và tài nguyên cũng có thể là cam kết nếu đã được công bố trong SLA hoặc tài liệu vận hành.

Ví dụ, nếu API cam kết xử lý theo thứ tự FIFO, đổi cấu trúc hàng đợi nhưng vẫn giữ FIFO là thay đổi triển khai; đổi sang xử lý không bảo đảm thứ tự là thay đổi hợp đồng. Nếu API không hề cam kết thứ tự, consumer không nên dựa vào thứ tự tình cờ của một implementation cụ thể.

## 5. Phân loại mức độ hỗ trợ

Một chính sách rõ ràng nên phân biệt ít nhất các nhóm sau. Tên nhãn có thể khác nhau giữa các dự án, nhưng ý nghĩa và cách xử lý cần nhất quán.

| Nhóm | Ý nghĩa | Quy tắc thay đổi |
|---|---|---|
| Supported | Hợp đồng chính thức, consumer được phép dựa vào | Thay đổi phải tuân theo chính sách tương thích, thông báo và lộ trình migration. |
| Experimental / Preview | Được cung cấp để thử nghiệm, chưa cam kết ổn định | Có thể thay đổi nhanh hơn; phải ghi rõ giới hạn và phạm vi áp dụng. |
| Deprecated | Hợp đồng cũ vẫn tồn tại nhưng đã có hướng thay thế | Thông báo phiên bản đánh dấu deprecated, hướng dẫn thay thế và thời điểm dự kiến loại bỏ nếu đã xác định. |
| Internal / Unsupported | Chi tiết nội bộ hoặc bề mặt không được hỗ trợ cho consumer | Có thể thay đổi theo nhu cầu implementation; không hứa giữ tương thích. |

Không nên chỉ dựa vào nhãn trong tên package hoặc comment. Chính sách cần được thể hiện ở tài liệu API, hướng dẫn sử dụng, release notes và cách đóng gói artifact. Nếu có nhãn `@Internal` hoặc annotation nội bộ, cần định nghĩa rõ ý nghĩa và bảo đảm công cụ build, tài liệu và nhóm phát triển áp dụng nhất quán.

Ví dụ annotation có thể ghi nhận thời điểm API được đưa vào hoặc deprecated:

```java
/** Supported API for looking up a customer. */
public interface CustomerLookup {
    Customer findById(String customerId);
}

/** @deprecated Use CustomerLookup.findById instead. */
@Deprecated(since = "4.2", forRemoval = true)
public Customer findCustomer(String customerId) {
    return customerLookup.findById(customerId);
}
```

`@Deprecated` giúp compiler và IDE cảnh báo consumer, nhưng không tự tạo ra toàn bộ chính sách deprecation. Tài liệu vẫn cần nói API thay thế là gì, API cũ còn được hỗ trợ trong bao lâu và phiên bản nào có thể loại bỏ.

## 6. Thiết kế ranh giới để có thể thay đổi implementation

Một cách hữu ích là để consumer phụ thuộc vào abstraction được hỗ trợ, còn implementation cụ thể nằm phía sau abstraction đó. Ví dụ:

```java
package com.example.customer.api;

public interface CustomerLookup {
    Customer findById(String customerId);
}
```

```java
package com.example.customer.internal;

final class DefaultCustomerLookup implements CustomerLookup {
    @Override
    public Customer findById(String customerId) {
        // Implementation có thể thay đổi theo phiên bản.
        return loadCustomerFromCacheOrDatabase(customerId);
    }

    private Customer loadCustomerFromCacheOrDatabase(String customerId) {
        // Chi tiết truy cập cache/database nằm trong nội bộ.
        return null;
    }
}
```

Trong thiết kế này, consumer chỉ cần biết `CustomerLookup`. Nhà cung cấp có thể đổi cache, database access, cấu trúc lớp, chiến lược retry hoặc thuật toán bên trong mà không yêu cầu consumer thay đổi, miễn là giữ hành vi đã cam kết.

Một số nguyên tắc thiết kế giúp ranh giới rõ hơn:

1. **Công bố abstraction có mục đích.** Chỉ export hoặc publish những kiểu mà consumer cần dùng; giữ implementation cụ thể ở package nội bộ khi phù hợp.
2. **Hạn chế để kiểu nội bộ lọt vào chữ ký công khai.** Nếu kiểu trả về hoặc tham số là lớp nội bộ, consumer có thể bị buộc phụ thuộc vào implementation.
3. **Định nghĩa extension point có chủ đích.** Chỉ cho phép consumer kế thừa hoặc triển khai những kiểu mà nhóm sẵn sàng duy trì như hợp đồng.
4. **Quy định hành vi quan sát được.** Nêu rõ điều gì được bảo đảm, điều gì không được bảo đảm và các điều kiện biên.
5. **Giữ dependency nội bộ sau abstraction.** Thay đổi thư viện hỗ trợ hoặc cách triển khai không nên buộc consumer phải khai báo những dependency không cần thiết.
6. **Tách API công khai khỏi cấu hình nội bộ.** Không để consumer phải chỉnh sửa các cờ hoặc class name chỉ nhằm điều khiển một chi tiết implementation không được hỗ trợ.

Với Gradle Java Library, cấu hình `api` và `implementation` giúp kiểm soát dependency nào được đưa ra compile classpath của consumer. Đây là công cụ quản lý bề mặt dependency, không phải bằng chứng duy nhất để kết luận một lớp hoặc package là API được hỗ trợ. Cần kết hợp dependency exposure với tài liệu và chính sách API.

## 7. Cách xác định ranh giới trong một module hiện có

Với module đã được sử dụng, ranh giới không phải lúc nào cũng được thiết kế rõ ngay từ đầu. Cần kết hợp hợp đồng đã công bố với cách consumer thực tế đang sử dụng.

### Bước 1: Thu thập bề mặt có thể được consumer truy cập

Liệt kê package export, lớp và member `public`/`protected`, interface, abstract class, annotation, service provider, resource, cấu hình, task/plugin build và giao thức bên ngoài. Đây là danh sách ứng viên, chưa phải kết luận rằng tất cả đều được hỗ trợ.

### Bước 2: Đọc tài liệu và dấu hiệu hỗ trợ

Tìm API reference, README, ví dụ tích hợp, migration guide, release notes, deprecation notice và phạm vi phiên bản được hỗ trợ. Thành phần xuất hiện trong tài liệu sử dụng chính thức thường có khả năng là hợp đồng hơn thành phần chỉ được nhắc trong tài liệu debug nội bộ.

### Bước 3: Tìm consumer và cách họ phụ thuộc

Kiểm tra source code, dependency graph, build script, cấu hình, reflection, serialization, resource lookup và workflow. Xác định consumer chỉ gọi API được công bố hay còn truy cập implementation class, package nội bộ, task ẩn hoặc giá trị mặc định tình cờ.

### Bước 4: Phân loại từng điểm tương tác

Gán nhãn Supported, Experimental, Deprecated hoặc Internal/Unsupported. Với mỗi điểm, ghi rõ bằng chứng, consumer đang sử dụng, phạm vi phiên bản và chủ sở hữu quyết định. Nếu chưa đủ thông tin, đánh dấu chưa xác định thay vì tự xếp vào nhóm internal.

### Bước 5: Xác định các chiều tương thích

Đối với mỗi hợp đồng, đánh giá source compatibility, binary compatibility, behavioral compatibility, runtime compatibility, configuration/data compatibility và build-time compatibility nếu có liên quan. Một điểm có thể tương thích ở một chiều nhưng không tương thích ở chiều khác.

### Bước 6: Xác nhận với consumer đại diện

Chạy compile test, binary compatibility check, integration test hoặc build test trên consumer thực tế. Kiểm thử phải phản ánh cách sử dụng đã được hỗ trợ và những consumer quan trọng đã phát hiện trong quá trình khảo sát.

## 8. Đánh giá thay đổi khi migration

Khi một thay đổi được đề xuất, trước hết xác định nó tác động đến hợp đồng hay implementation. Sau đó xem xét các chiều tương thích và consumer bị ảnh hưởng.

| Thay đổi | Nếu nằm trong implementation | Nếu nằm trong hợp đồng được hỗ trợ |
|---|---|---|
| Đổi cấu trúc collection nội bộ | Có thể thực hiện nếu kết quả quan sát được giữ nguyên | Phải giữ thứ tự, tính duy nhất hoặc đặc tính collection đã cam kết. |
| Đổi tên lớp | Có thể thực hiện với lớp nội bộ không được consumer sử dụng | Có thể phá vỡ import, chữ ký API, reflection hoặc serialization; cần kế hoạch migration. |
| Đổi thuật toán retry | Có thể thực hiện nếu giữ các hành vi đã hứa | Phải đánh giá số lần retry, khoảng chờ, timeout và tác dụng phụ mà consumer dựa vào. |
| Đổi property cấu hình | Có thể thực hiện nếu property hoàn toàn nội bộ | Cần hỗ trợ alias/deprecation hoặc cung cấp bước chuyển đổi. |
| Thay dependency | Có thể thực hiện nếu dependency không lộ ra ngoài và hành vi vẫn tương thích | Phải kiểm tra API type, version alignment và runtime của consumer. |
| Đổi schema hoặc event | Có thể thực hiện với định dạng nội bộ không có consumer bên ngoài | Cần chiến lược tương thích dữ liệu, versioning và chuyển tiếp giữa producer/consumer. |

Một thay đổi trong implementation vẫn có thể làm hỏng hợp đồng gián tiếp. Ví dụ, thay `HashMap` bằng cấu trúc khác là thay đổi nội bộ; nhưng nếu việc đó vô tình đổi thứ tự trả về mà API đã cam kết giữ thứ tự, thay đổi tổng thể vẫn là breaking change.

### 8.1. Nếu consumer đang dùng chi tiết nội bộ

Trong hệ thống lâu năm, consumer đôi khi phụ thuộc vào lớp hoặc hành vi chưa từng được cam kết. Không nên kết luận rằng mọi phụ thuộc như vậy tự động trở thành hợp đồng vĩnh viễn; cũng không nên bỏ qua chúng trong một đợt migration.

Hãy ghi nhận:

- Consumer nào đang sử dụng chi tiết đó và sử dụng để làm gì.
- Mức độ phổ biến và mức độ quan trọng của consumer.
- Có API được hỗ trợ nào thay thế được không.
- Chi phí sửa consumer và rủi ro nếu thay đổi ngay.
- Có cần một giai đoạn chuyển tiếp hay không.

Sau đánh giá, nhóm có thể giữ tạm hành vi, bổ sung API thay thế, đưa cảnh báo, phát hành migration guide hoặc thống nhất thời điểm loại bỏ. Nếu cần nâng mức hỗ trợ của một chi tiết đang được dùng rộng rãi, quyết định đó phải được ghi rõ thay vì để hợp đồng phát triển ngầm.

## 9. Ví dụ: thay đổi lớp triển khai mà không phá vỡ API

Giả sử phiên bản đầu của thư viện sử dụng một implementation truy vấn dữ liệu trực tiếp:

```java
public interface CustomerLookup {
    Customer findById(String customerId);
}

final class JdbcCustomerLookup implements CustomerLookup {
    @Override
    public Customer findById(String customerId) {
        // Truy vấn JDBC trực tiếp.
        return queryDatabase(customerId);
    }
}
```

Ở phiên bản sau, nhóm muốn thêm cache để giảm tải database:

```java
final class CachedCustomerLookup implements CustomerLookup {
    private final CustomerRepository repository;
    private final CustomerCache cache;

    @Override
    public Customer findById(String customerId) {
        Customer cached = cache.get(customerId);
        if (cached != null) {
            return cached;
        }

        Customer loaded = repository.findById(customerId);
        if (loaded != null) {
            cache.put(customerId, loaded);
        }
        return loaded;
    }
}
```

Nếu consumer chỉ sử dụng `CustomerLookup`, nhóm có thể thay `JdbcCustomerLookup` bằng `CachedCustomerLookup` mà không buộc consumer đổi mã nguồn. Tuy nhiên, nhóm vẫn phải kiểm tra hợp đồng hành vi: dữ liệu có bị cũ quá thời hạn cho phép không, kết quả khi không tìm thấy customer có giữ nguyên không, lỗi repository có được truyền ra giống trước không và thao tác cập nhật dữ liệu có làm cache nhất quán không.

Ví dụ này cho thấy abstraction tạo điều kiện thay đổi implementation, nhưng không tự động bảo đảm tương thích. Hợp đồng hành vi vẫn phải được kiểm tra sau khi thay đổi.

## 10. Kiểm thử và tài liệu hóa ranh giới hợp đồng

Ranh giới chỉ hữu ích khi có thể kiểm chứng. Tùy module, có thể dùng các loại bằng chứng sau:

| Bằng chứng | Mục tiêu |
|---|---|
| API documentation và API diff | Nhìn thấy bề mặt public/protected và thay đổi chữ ký. |
| Binary compatibility checker | Phát hiện thay đổi có thể làm bytecode consumer cũ không liên kết được. |
| Consumer compile test | Xác nhận mã nguồn consumer mẫu vẫn biên dịch với phiên bản mới. |
| Contract test | Kiểm tra hành vi mà provider cam kết với consumer. |
| Integration test | Kiểm tra cấu hình, giao thức, dữ liệu và tương tác giữa các thành phần. |
| Build plugin test | Kiểm tra plugin ID, extension, task và cấu hình mà build của consumer sử dụng. |
| Schema compatibility test | Kiểm tra producer và consumer cũ/mới có thể trao đổi dữ liệu trong giai đoạn chuyển tiếp. |
| Migration guide và release notes | Giúp consumer nhận biết thay đổi, cách nâng cấp và thời điểm ngừng hỗ trợ. |

Một bản ghi hợp đồng có thể dùng mẫu sau:

| Trường | Nội dung cần ghi |
|---|---|
| Contract ID | Mã hoặc tên ổn định để tham chiếu. |
| Surface | Java API, SPI, config, protocol, data, build plugin hay runtime behavior. |
| Support level | Supported, Experimental, Deprecated hoặc Internal/Unsupported. |
| Consumer | Nhóm project hoặc hệ thống sử dụng. |
| Compatibility scope | JDK, framework, dependency và phiên bản được hỗ trợ. |
| Behavior | Đầu vào, kết quả, exception, giới hạn và điều kiện biên. |
| Change policy | Quy tắc versioning, deprecation, thời gian chuyển tiếp và loại bỏ. |
| Verification | Test hoặc bằng chứng dùng để xác nhận hợp đồng. |

Ví dụ một mục đã được ghi nhận:

```yaml
contract:
  id: customer-lookup-api
  surface: java-api
  supportLevel: supported
  package: com.example.customer.api
  compatibility:
    java: "17+"
  behavior:
    input: customerId must be non-blank
    missingCustomer: returns null
  verification:
    - customer-lookup-contract-test
    - consumer-compile-test
```

Đây là ví dụ minh họa cách mô tả hợp đồng. Trong dự án thực tế, cần dùng định dạng và quy tắc đã được nhóm thống nhất; đặc biệt phải xác định rõ ý nghĩa của `null`, exception và phiên bản Java theo đúng hành vi module.

## 11. Checklist trước khi thay đổi trong migration

- [ ] Đã xác định điểm tương tác mà consumer có thể truy cập.
- [ ] Đã phân biệt quyền truy cập Java với mức độ hỗ trợ chính thức.
- [ ] Đã kiểm tra API, SPI, cấu hình, giao thức, dữ liệu và build-time surface liên quan.
- [ ] Đã phân loại Supported, Experimental, Deprecated hoặc Internal/Unsupported bằng bằng chứng.
- [ ] Đã tìm consumer thực tế, kể cả consumer đang phụ thuộc vào chi tiết nội bộ.
- [ ] Đã xác định source, binary, behavioral, runtime và các chiều tương thích khác bị tác động.
- [ ] Đã chọn kiểm thử phù hợp với hợp đồng và consumer đại diện.
- [ ] Đã chuẩn bị deprecation hoặc migration guide nếu cần thay đổi hợp đồng.
- [ ] Đã cập nhật tài liệu và release notes để phản ánh chính sách hỗ trợ hiện hành.

## Kết luận

Ranh giới hợp đồng được hỗ trợ xác định điều gì consumer có thể dựa vào và điều gì nhà cung cấp phải duy trì theo chính sách tương thích. Chi tiết triển khai mô tả cách module thực hiện hợp đồng và có thể thay đổi khi hành vi đã cam kết vẫn được giữ nguyên. Ranh giới này phải được xác định từ API, SPI, cấu hình, giao thức, dữ liệu, build-time surface, tài liệu và cách consumer thực tế sử dụng. Khi migration, phân loại rõ từng điểm tương tác và kiểm chứng bằng consumer test giúp thay đổi nội bộ có kiểm soát, đồng thời giảm nguy cơ phá vỡ những cam kết mà hệ thống khác đang phụ thuộc.
