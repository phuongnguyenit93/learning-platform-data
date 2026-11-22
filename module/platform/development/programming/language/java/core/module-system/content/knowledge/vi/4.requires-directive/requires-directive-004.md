# requires static cho phụ thuộc chỉ cần lúc biên dịch

Trong Java Platform Module System (JPMS), chỉ thị **requires static** dùng để khai báo một dependency bắt buộc phải có khi biên dịch nhưng có thể vắng mặt ở runtime. Đây là cách mô tả những thư viện hỗ trợ compile-time, chẳng hạn annotation, metadata hoặc tích hợp tùy chọn mà ứng dụng không cần nạp trong mọi lần chạy.

Điểm quan trọng là từ khóa static chỉ làm cho dependency trở thành tùy chọn ở giai đoạn chạy. Nó không làm dependency tùy chọn ở giai đoạn biên dịch, không tự tải thư viện khi cần và cũng không bảo vệ mã khỏi lỗi liên kết nếu chương trình thực sự sử dụng lớp của dependency đang vắng mặt.

## 1. Cú pháp và ý nghĩa

Cú pháp trong module-info.java:

~~~java
module com.example.orders {
    requires static com.example.annotations;
}
~~~

Mô-đun orders cần đọc mô-đun annotations để biên dịch. Khi khởi chạy, bộ phân giải mô-đun không bắt buộc phải tìm thấy annotations chỉ vì có khai báo requires static.

So sánh với requires thông thường:

| Khai báo | Khi biên dịch | Khi chạy |
| --- | --- | --- |
| requires module.name | Dependency phải có và được phân giải | Dependency phải có để mô-đun được phân giải. |
| requires static module.name | Dependency phải có và được phân giải | Dependency có thể vắng mặt nếu không được yêu cầu bởi quan hệ khác. |

Ví dụ:

~~~java
module com.example.orders {
    requires com.example.customer.api;
    requires static com.example.annotations;
}
~~~

Ở đây:

- com.example.customer.api là dependency thông thường. Thiếu nó, mô-đun orders không thể được phân giải đúng.
- com.example.annotations là dependency compile-time. Nó phải có trên module path khi biên dịch orders, nhưng có thể không cần trong cấu hình runtime.

requires static vẫn tạo quan hệ đọc mô-đun trong quá trình biên dịch. Do đó, mã nguồn có thể tham chiếu các kiểu thuộc dependency đó và trình biên dịch vẫn kiểm tra được chúng.

## 2. Vì sao cần dependency chỉ ở compile-time?

Không phải thư viện nào xuất hiện trong mã nguồn cũng cần được đóng gói cùng ứng dụng lúc chạy. Một số dependency chỉ cung cấp thông tin cho compiler hoặc công cụ build.

Các trường hợp thường gặp:

- **Annotation compile-time:** đánh dấu mã để compiler, annotation processor hoặc công cụ sinh mã xử lý.
- **Metadata:** cung cấp kiểu hoặc thông tin mô tả chỉ được dùng khi biên dịch.
- **Tích hợp tùy chọn:** một mô-đun có thể biên dịch với API mở rộng nhưng bản chạy cơ bản không kích hoạt phần tích hợp đó.
- **API hỗ trợ:** thư viện cần biết một kiểu ở thời điểm biên dịch, nhưng phần triển khai runtime được cung cấp bởi môi trường khác hoặc không được sử dụng trong cấu hình tối giản.

Ví dụ một annotation đánh dấu lớp cần được công cụ build xử lý:

~~~java
package com.example.annotations;

import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

@Retention(RetentionPolicy.CLASS)
public @interface GenerateMetadata {
}
~~~

Mô-đun sử dụng annotation:

~~~java
module com.example.orders {
    requires static com.example.annotations;
}
~~~

Lớp trong mô-đun:

~~~java
package com.example.orders.model;

import com.example.annotations.GenerateMetadata;

@GenerateMetadata
public class Order {
    private long id;
}
~~~

Compiler cần nhìn thấy kiểu GenerateMetadata để kiểm tra mã nguồn. Nếu annotation có retention là CLASS, metadata annotation được lưu trong bytecode nhưng không yêu cầu ứng dụng phải đọc annotation bằng reflection ở runtime.

Nếu một công cụ runtime cần tìm và xử lý annotation đó, dependency chứa annotation phải có mặt ở runtime và package/type phải truy cập được theo các quy tắc tương ứng. requires static không làm cho annotation runtime tự xuất hiện khi JAR đã bị loại khỏi cấu hình chạy.

## 3. Dependency vẫn bắt buộc khi biên dịch

Một hiểu nhầm phổ biến là dùng requires static để bỏ qua một thư viện bị thiếu trong lúc build. Điều đó không đúng.

Khi biên dịch, mô-đun được khai báo sau requires static vẫn phải quan sát được trên module path. Ví dụ:

~~~java
module com.example.orders {
    requires static com.example.annotations;
}
~~~

Nếu compiler không tìm thấy com.example.annotations, quá trình biên dịch sẽ báo lỗi module not found.

Lệnh biên dịch có thể chỉ rõ module path:

~~~bash
javac --module-path libs --module-source-path src -d out -m com.example.orders
~~~

Trong đó thư mục libs phải chứa mô-đun annotations hoặc một JAR có thể được nhận diện thành mô-đun phù hợp.

Có thể kiểm tra tên mô-đun của JAR:

~~~bash
jar --describe-module --file libs/example-annotations.jar
~~~

Không nên suy đoán module name từ tên file. Với JAR modular, tên được khai báo trong module-info.class; với automatic module, tên có thể đến từ Automatic-Module-Name hoặc được suy ra từ tên JAR.

## 4. Dependency có thể vắng mặt ở runtime trong trường hợp nào?

Giả sử ứng dụng chỉ dùng annotation để đánh dấu mã và không cần đọc annotation khi chạy. Khi đó dependency annotation có thể không được đưa vào runtime image.

Cấu hình module:

~~~java
module com.example.orders {
    requires static com.example.annotations;
}
~~~

Lúc biên dịch, annotations phải có mặt. Lúc chạy, nếu annotations không được mô-đun khác yêu cầu và không được thêm làm root module, bộ phân giải có thể bỏ qua dependency static này.

Điều đó không có nghĩa mọi tham chiếu đến kiểu trong dependency đều an toàn khi thư viện bị loại khỏi runtime. Nếu chương trình thực sự cần nạp, liên kết, khởi tạo hoặc gọi một kiểu thuộc dependency bị thiếu, lỗi như NoClassDefFoundError hoặc ClassNotFoundException có thể xuất hiện.

Ví dụ, đoạn mã sau có tham chiếu trực tiếp đến một lớp của dependency:

~~~java
package com.example.orders;

import com.example.optional.Client;

public class OptionalGateway {
    public void connect() {
        Client client = new Client();
        client.open();
    }
}
~~~

Nếu mô-đun chứa Client không có ở runtime nhưng nhánh connect vẫn được thực thi, ứng dụng không thể thực hiện lời gọi đó. requires static không tự biến lời gọi thành tùy chọn.

Muốn phần tích hợp thực sự có thể bật/tắt, cần thiết kế đường chạy riêng: tách implementation sang mô-đun adapter, kiểm tra khả năng có mặt của implementation hoặc sử dụng một SPI. Không nên để phần lõi luôn gọi trực tiếp các lớp chỉ có trong dependency tùy chọn.

## 5. requires static và annotation

Annotation là trường hợp dễ gặp nhất vì nhiều annotation chỉ phục vụ compiler hoặc công cụ phân tích mã.

Ví dụ:

~~~java
module com.example.domain {
    requires static com.example.validation.annotations;
}
~~~

Một lớp sử dụng annotation:

~~~java
package com.example.domain.model;

import com.example.validation.NotBlank;

public class Customer {
    @NotBlank
    private String name;
}
~~~

Nếu annotation chỉ được đọc ở compile-time hoặc công cụ xử lý bytecode sau khi biên dịch, ứng dụng có thể không cần thư viện annotation trong runtime image.

Cần phân biệt retention:

| Retention | Nơi lưu annotation | Khả năng sử dụng |
| --- | --- | --- |
| SOURCE | Chỉ trong mã nguồn, bị loại khỏi bytecode | Compiler hoặc annotation processor xử lý khi biên dịch. |
| CLASS | Được lưu trong class file, không yêu cầu reflection runtime nhìn thấy | Công cụ đọc bytecode có thể xử lý sau biên dịch. |
| RUNTIME | Được lưu trong class file và có thể đọc bằng reflection | Nếu ứng dụng/framework cần đọc annotation, kiểu annotation phải sẵn có và truy cập được lúc chạy. |

Nếu annotation có RetentionPolicy.RUNTIME và framework dùng reflection để tìm annotation, đừng loại thư viện annotation khỏi runtime mà không kiểm tra hành vi của framework. Dependency compile-time-only chỉ phù hợp khi phần chạy không cần nạp kiểu annotation đó.

Một annotation processor cũng là một công cụ chạy trong tiến trình compiler. Dependency của processor và dependency của mã sản phẩm có thể là hai nhóm khác nhau; không nên nhầm requires static trong module descriptor của ứng dụng với cấu hình processor path của build tool.

## 6. requires static kết hợp transitive

Có thể kết hợp hai modifier:

~~~java
module com.example.api {
    requires static transitive com.example.annotations;
}
~~~

Hai modifier có ý nghĩa riêng:

- **static:** dependency bắt buộc khi biên dịch nhưng tùy chọn khi chạy.
- **transitive:** truyền quan hệ readability tới các mô-đun đọc mô-đun hiện tại trong ngữ cảnh phân giải tương ứng.

Khai báo này phù hợp khi kiểu từ dependency xuất hiện trong API công khai và dependency chỉ cần thiết ở compile-time.

Ví dụ một thư viện API dùng annotation để đánh dấu kiểu trả về hoặc tham số:

~~~java
module com.example.customer.api {
    requires static transitive com.example.contract.annotations;
    exports com.example.customer.api;
}
~~~

Các mô-đun biên dịch dựa trên customer.api có thể đọc contract.annotations thông qua quan hệ transitive. Tuy nhiên, nếu annotation không cần ở runtime, cấu hình runtime vẫn có thể không chứa mô-đun đó.

Chỉ dùng dạng kết hợp này khi cả hai ý định đều đúng. Nếu dependency chỉ được sử dụng bên trong và không phải phần của API công khai, requires static thông thường là đủ.

## 7. Khác biệt với các cách đánh dấu dependency tùy chọn khác

requires static là một chỉ thị của JPMS trong module descriptor. Nó mô tả quan hệ giữa các mô-đun ở cấp nền tảng Java.

Các build tool có cấu hình dependency riêng. Ví dụ, Gradle có cấu hình compileOnly để cung cấp dependency khi biên dịch nhưng không đưa nó vào runtime classpath mặc định. Khi dùng modular JAR, cấu hình build và module descriptor phải nhất quán: compiler cần thấy mô-đun trong module path để thỏa mãn requires static.

Trong Maven, optional dependency điều khiển việc dependency có được truyền tiếp tới người dùng của artifact hay không; nó không đồng nghĩa trực tiếp với requires static. Scope provided cũng có quy tắc phân phối và runtime riêng. Hãy xem dependency graph và classpath/module path thực tế thay vì suy luận chỉ từ tên cấu hình.

Một checklist ngắn:

- Module descriptor có requires static cho dependency chỉ cần compile-time.
- Build tool cung cấp dependency đó trong compile module path.
- Runtime configuration loại dependency khi thật sự không cần.
- Mã thực thi không gọi trực tiếp lớp thuộc dependency đã loại.
- Annotation/framework không cần đọc kiểu annotation ở runtime nếu dependency vắng mặt.

## 8. Khi dependency optional cần được sử dụng lúc runtime

Nếu tính năng optional cần gọi thư viện tại runtime, có một số cách thiết kế.

### Cách A: tách adapter thành mô-đun riêng

Giữ mô-đun lõi không phụ thuộc thư viện optional:

~~~java
module com.example.orders {
    exports com.example.orders.api;
}
~~~

Tạo adapter:

~~~java
module com.example.orders.audit {
    requires com.example.orders;
    requires com.example.audit.client;
}
~~~

Ứng dụng nào cần audit mới thêm mô-đun adapter vào runtime. Cách này giữ dependency rõ ràng và tránh để lớp lõi tham chiếu trực tiếp API tùy chọn.

### Cách B: dùng SPI

Mô-đun lõi khai báo một interface do chính nó sở hữu, consumer/provider được kết nối qua uses và provides. Mô-đun adapter phụ thuộc vào thư viện ngoài và cung cấp implementation của interface đó.

Nhờ vậy, mô-đun lõi chỉ biết hợp đồng service. Khi provider không được cài đặt, ứng dụng có thể không kích hoạt tính năng optional mà không cần nạp lớp của thư viện ngoài.

### Cách C: nạp lớp theo nhu cầu

Một số tích hợp có thể kiểm tra sự hiện diện của lớp bằng reflection hoặc class loader. Cách này phù hợp với adapter rất nhỏ, nhưng cần xử lý tên lớp, class loader, module readability và lỗi khởi tạo. Không nên coi Class.forName là giải pháp chung cho mọi dependency tùy chọn.

Trong hệ thống modular, tách adapter hoặc dùng SPI thường giúp mô tả dependency rõ hơn so với việc rải kiểm tra reflection trong mã nghiệp vụ.

## 9. Những lỗi thường gặp với requires static

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| module not found khi compile | Dependency static không có trên module path lúc biên dịch | Thêm dependency vào compile module path. |
| NoClassDefFoundError khi chạy | Nhánh mã đã sử dụng lớp thuộc dependency bị loại | Đưa dependency vào runtime hoặc tách đường chạy optional. |
| Annotation không được framework nhận diện | Annotation dependency không có ở runtime hoặc retention không phù hợp | Kiểm tra retention và cấu hình runtime của framework. |
| Consumer không thấy kiểu trong API | Thiếu exports hoặc readability | Kiểm tra requires và exports ở cả hai mô-đun. |
| Dependency vẫn xuất hiện ở runtime | Nó được yêu cầu bởi mô-đun khác hoặc được thêm như root module | Kiểm tra module resolution và runtime dependency graph. |

Một dependency được khai báo static vẫn có thể xuất hiện ở runtime nếu nó được yêu cầu theo một đường khác hoặc được đưa trực tiếp vào cấu hình khởi chạy. Từ khóa static không phải lệnh loại bỏ JAR khỏi mọi runtime image.

## 10. Kiểm tra hành vi compile-time và runtime

Dùng lệnh mô tả JAR để xác nhận module name:

~~~bash
jar --describe-module --file libs/example-annotations.jar
~~~

Biên dịch mô-đun với dependency có trên module path:

~~~bash
javac --module-path libs --module-source-path src -d out -m com.example.orders
~~~

Xem các mô-đun trong runtime:

~~~bash
java --list-modules
~~~

Xem quá trình phân giải mô-đun khi chạy ứng dụng:

~~~bash
java --show-module-resolution --module-path out -m com.example.orders/com.example.orders.Main
~~~

Nếu dependency static vắng mặt, cần xác minh ứng dụng vẫn chạy được trên đúng lệnh khởi chạy dự kiến và các đường mã optional không bị gọi. Nếu dependency xuất hiện do một mô-đun khác yêu cầu, hãy kiểm tra lại module graph để biết đường phụ thuộc thực tế.

## 11. Nguyên tắc sử dụng

- Dùng requires static khi dependency cần cho compile-time nhưng không bắt buộc cho runtime của cấu hình ứng dụng.
- Đảm bảo dependency vẫn có mặt trên module path khi biên dịch.
- Không dùng static để che giấu dependency bị thiếu trong build.
- Không gọi trực tiếp lớp optional trên đường chạy có thể được kích hoạt khi dependency vắng mặt.
- Với annotation, kiểm tra retention và xem framework có đọc annotation bằng reflection ở runtime không.
- Dùng requires static transitive khi dependency vừa optional ở runtime vừa là phần của hợp đồng API cần truyền tiếp readability.
- Với tích hợp runtime có thể bật/tắt, ưu tiên tách adapter hoặc dùng SPI để dependency không lan vào mô-đun lõi.

Giá trị của requires static nằm ở việc mô tả chính xác thời điểm một dependency là bắt buộc. Khi compile-time và runtime được thiết kế rõ ràng, dự án có thể giữ các công cụ hỗ trợ và tích hợp tùy chọn mà không buộc mọi cấu hình chạy phải mang theo chúng.
