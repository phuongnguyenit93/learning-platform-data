# Thiết kế migration boundary cho hệ thống legacy

## 1. Migration boundary là gì?

Khi chuyển một hệ thống Java legacy từ classpath sang Java Platform Module System (JPMS), không nhất thiết phải modular hóa toàn bộ ứng dụng trong một lần. Có thể xác định các **migration boundary**: ranh giới giữa phần đã được tổ chức thành module và phần vẫn chạy theo mô hình classpath cũ.

Một migration boundary tốt xác định rõ:

- Phần nào của hệ thống đã có module descriptor và được quản lý bằng module graph.
- Phần nào vẫn thuộc unnamed module trên classpath.
- API nào được phép đi qua ranh giới giữa hai phần.
- Thư viện nào là phụ thuộc dùng chung, thư viện nào thuộc riêng một module.
- Cách xử lý reflection, service discovery, resource và class loading khi hai mô hình cùng tồn tại.
- Điều kiện để một phần legacy được chuyển tiếp thành named module hoặc được loại bỏ.

Mục tiêu là giảm rủi ro khi chuyển đổi mà vẫn giữ được khả năng build, triển khai và vận hành. Ranh giới phải có thể kiểm tra được bằng cấu trúc source, module descriptor, cấu hình build và kiểm thử.

Không nên xem migration boundary chỉ là việc đặt một số JAR lên module path. Ranh giới còn là hợp đồng kiến trúc: module nào sở hữu dữ liệu, API nào được công khai, ai được phép gọi implementation và cách thay đổi được triển khai an toàn.

## 2. Bắt đầu bằng bản đồ phụ thuộc của hệ thống

Trước khi chia boundary, hãy lập danh sách các thành phần:

- Các ứng dụng hoặc service có thể build và deploy độc lập.
- Các thư viện dùng chung và các phiên bản đang được sử dụng.
- Package được nhiều module truy cập trực tiếp.
- Các luồng gọi xuyên tầng, đặc biệt là truy cập database hoặc dùng class implementation của module khác.
- Cơ chế plugin, reflection, ServiceLoader, resource lookup và dynamic class loading.
- Các phụ thuộc vào API nội bộ của JDK hoặc thư viện cũ.
- Các module có thể tạo thành vòng phụ thuộc nếu tách riêng.

Có thể bắt đầu từ dependency tree của build tool, sau đó dùng jdeps để phân tích phụ thuộc bytecode:

~~~bash
jdeps --summary build/libs/legacy-app.jar
jdeps --verbose:package build/libs/legacy-app.jar
jdeps --jdk-internals build/libs/legacy-app.jar
~~~

Nếu artifact cần thêm thư viện ngoài, cung cấp classpath hoặc module path phù hợp để kết quả phân tích đầy đủ hơn. jdeps giúp phát hiện tham chiếu tĩnh; reflection theo tên class, tên resource lấy từ cấu hình và plugin được nạp động vẫn cần được kiểm kê riêng.

Bản đồ phụ thuộc nên thể hiện cả phụ thuộc kỹ thuật và phụ thuộc nghiệp vụ. Hai package có thể nằm trong cùng một JAR nhưng thuộc hai trách nhiệm khác nhau; ngược lại, hai module có thể được build riêng nhưng vẫn phụ thuộc chặt vào cùng một schema hoặc database transaction.

## 3. Chọn boundary theo trách nhiệm và API

Một boundary hữu ích thường đi theo capability hoặc trách nhiệm nghiệp vụ, ví dụ:

~~~text
legacy-system/
  app/
  customer/
  billing/
  reporting/
  integration/
  shared/
~~~

Trong giai đoạn đầu, các thư mục này có thể vẫn là package hoặc project trong một build. Khi đã hiểu quan hệ phụ thuộc, có thể chuyển từng capability thành named module.

Một cấu trúc modular minh họa:

~~~text
modules/
  com.example.customer.api/
  com.example.customer.core/
  com.example.billing.api/
  com.example.billing.core/
  com.example.legacy.adapter/
  com.example.application/
~~~

Mỗi boundary nên có một API nhỏ, ổn định. Ví dụ module billing cần thông tin khách hàng thì nên gọi API customer được công khai, thay vì import trực tiếp các class implementation, entity nội bộ hoặc repository của customer.

Module API có thể chứa interface và kiểu dữ liệu dùng chung:

~~~java
module com.example.customer.api {
    exports com.example.customer.api;
}
~~~

Module implementation phụ thuộc vào API:

~~~java
module com.example.customer.core {
    requires com.example.customer.api;
}
~~~

Module tiêu thụ chỉ cần đọc API:

~~~java
module com.example.billing.core {
    requires com.example.customer.api;
}
~~~

Cách tổ chức này giảm phụ thuộc ngược vào implementation. Nó cũng tạo vị trí rõ ràng để thay đổi cách triển khai customer mà không buộc billing phải biết chi tiết bên trong.

Không nên tạo module API cho mọi class. Chỉ tách API khi có hợp đồng thực sự cần được nhiều thành phần sử dụng hoặc cần ổn định qua nhiều lần triển khai. Việc tách quá nhỏ làm tăng số module và chi phí quản lý graph mà không cải thiện boundary.

## 4. Dùng classpath làm vùng tương thích trong giai đoạn chuyển tiếp

Một hệ thống có thể chạy named module cùng thư viện legacy trên classpath. Các class trên classpath thuộc **unnamed module** của classloader tương ứng.

Đây là vùng tương thích hữu ích khi thư viện chưa có module descriptor hoặc chưa thể chuyển đổi ngay. Named module có thể đọc unnamed module, nhưng named module không thể khai báo tên một unnamed module trong requires. Vì vậy, nếu một named module cần API của thư viện legacy, cần xác định cách tổ chức phụ thuộc phù hợp thay vì cố viết requires cho một module không có tên.

Ví dụ, thư viện legacy có thể tiếp tục được nạp qua classpath trong lúc phần ứng dụng đã modular hóa. Cần giữ cấu hình runtime nhất quán giữa môi trường phát triển, kiểm thử và production.

Một số thư viện JAR không có module descriptor có thể được nhận diện như **automatic module** khi đặt trên module path. Automatic module có tên suy ra từ metadata hoặc tên JAR, trừ khi manifest cung cấp Automatic-Module-Name. Nó có thể giúp tạo bước chuyển tiếp, nhưng không phải lúc nào cũng là boundary cuối cùng tốt.

Khi dùng automatic module:

- Kiểm tra tên module thực tế bằng jar --describe-module.
- Ưu tiên tên module ổn định do thư viện công bố.
- Theo dõi các package được export và các phụ thuộc mà module tự động đọc.
- Tránh dựa vào hành vi rộng của automatic module như thể đó là API được thiết kế có chủ đích.
- Lập kế hoạch chuyển sang named module có descriptor rõ ràng nếu thư viện thuộc quyền kiểm soát của dự án.

Classpath, automatic module và named module có thể cùng xuất hiện trong quá trình migration. Điều quan trọng là ghi rõ trạng thái của từng thư viện và không để cùng một JAR xuất hiện đồng thời trên nhiều đường nạp.

## 5. Thiết kế adapter cho legacy API

Một cách tạo boundary an toàn là đặt một adapter ở giữa hệ thống mới và thư viện cũ. Adapter chuyển đổi mô hình dữ liệu, xử lý khác biệt API và cô lập các quy tắc legacy.

Ví dụ hệ thống cũ cung cấp API:

~~~java
public class LegacyCustomerService {
    public LegacyCustomer findCustomer(String id) {
        // Legacy implementation
        return null;
    }
}
~~~

Module mới định nghĩa hợp đồng:

~~~java
package com.example.customer.api;

public interface CustomerLookup {
    CustomerView findById(String id);
}
~~~

Adapter triển khai API mới bằng cách gọi hệ thống cũ:

~~~java
package com.example.legacy.adapter;

public class LegacyCustomerAdapter implements CustomerLookup {
    private final LegacyCustomerService legacy;

    public LegacyCustomerAdapter(LegacyCustomerService legacy) {
        this.legacy = legacy;
    }

    @Override
    public CustomerView findById(String id) {
        LegacyCustomer oldValue = legacy.findCustomer(id);
        if (oldValue == null) {
            return null;
        }

        return new CustomerView(oldValue.getId(), oldValue.getName());
    }
}
~~~

Trong thực tế, cần bổ sung xử lý lỗi, nullability, transaction, mapping và logging phù hợp. Ví dụ minh họa tập trung vào việc chuyển đổi kiểu dữ liệu và giữ legacy class ở phía adapter.

Module chứa adapter có thể phụ thuộc API mới và thư viện legacy theo cách build đang hỗ trợ:

~~~java
module com.example.legacy.adapter {
    requires com.example.customer.api;
}
~~~

Nếu legacy library ở classpath, cấu hình build và runtime phải cung cấp class đó cho adapter. Nếu thư viện đã được chuyển thành module, adapter có thể khai báo requires tên module tương ứng.

Adapter nên là nơi duy nhất biết các chi tiết legacy cần thay đổi. Không để class legacy lan rộng vào API public của module mới, vì điều đó khiến boundary phụ thuộc ngược vào implementation cũ.

## 6. Tránh split package khi chuyển sang named module

Một package được phân tán qua nhiều JAR trên classpath có thể đã tồn tại nhiều năm mà không gây lỗi rõ ràng. Khi đưa các JAR đó thành named module, **split package** thường gây vấn đề vì cùng một package không thể được phân chia tùy ý giữa nhiều named module trong cùng module layer.

Ví dụ hai thư viện đều chứa:

~~~text
com/example/shared/Util.class
~~~

Nếu cả hai trở thành named module riêng, module system có thể từ chối phân giải graph do package bị chia sẻ. Ngay cả khi một số tình huống classpath cũ vẫn chạy, không nên coi split package là cấu trúc modular hợp lệ.

Cách xử lý thường gồm:

1. Xác định JAR nào sở hữu package và class thực sự.
2. Chọn một module làm chủ package đó.
3. Chuyển class dùng chung vào một module API hoặc module nền tảng có trách nhiệm rõ ràng.
4. Cập nhật import và dependency để các module còn lại dùng API được export.
5. Loại bỏ bản class trùng khỏi artifact khác.
6. Kiểm tra lại package list và module graph sau khi đóng gói.

Không nên tạo một module shared chứa mọi class chỉ để xóa cảnh báo split package. Module dùng chung cần có phạm vi trách nhiệm rõ, nếu không nó sẽ trở thành điểm phụ thuộc tập trung và làm các boundary mới tiếp tục dính chặt với nhau.

## 7. Kiểm soát vòng phụ thuộc

Một boundary không tốt thường xuất hiện khi module A cần implementation của B, còn B lại cần implementation của A. Nếu hai module phải khai báo requires lẫn nhau, module graph không thể phân giải vòng phụ thuộc đó như một quan hệ module hợp lệ.

Có thể phá vòng bằng một API hoặc SPI:

~~~text
com.example.order.api
       ^          ^
       |          |
order.core    inventory.core
~~~

Module API chứa interface và kiểu dữ liệu ổn định. Hai module implementation phụ thuộc vào API theo chiều phù hợp, thay vì import trực tiếp class của nhau.

Ví dụ module order khai báo service interface:

~~~java
package com.example.order.api;

public interface StockReservation {
    boolean reserve(String productId, int quantity);
}
~~~

Module order sử dụng SPI:

~~~java
module com.example.order.core {
    requires com.example.order.api;
    uses com.example.order.api.StockReservation;
}
~~~

Module inventory cung cấp implementation:

~~~java
module com.example.inventory.core {
    requires com.example.order.api;

    provides com.example.order.api.StockReservation
        with com.example.inventory.core.InventoryReservation;
}
~~~

Cần đặt service API ở module có trách nhiệm rõ ràng và tránh để API đó phụ thuộc ngược vào implementation. Nếu quan hệ nghiệp vụ thực sự có vòng, hãy xem lại cách chia capability hoặc xác định một orchestration module điều phối hai phía.

## 8. Quản lý reflection và deep access qua boundary

Framework legacy có thể dùng reflection để truy cập field private, constructor hoặc package nội bộ. Khi chuyển class sang named module, các thao tác này chịu quy tắc exports và opens.

Nếu module chỉ công khai API public, dùng exports:

~~~java
module com.example.customer.core {
    exports com.example.customer.api;
}
~~~

Nếu framework cần deep reflection vào package entity, mở đúng package cho module framework:

~~~java
module com.example.customer.core {
    exports com.example.customer.api;

    opens com.example.customer.entity
        to com.example.orm;
}
~~~

Nếu framework chạy trên classpath, caller thuộc unnamed module. Có thể dùng --add-opens ở runtime trong giai đoạn chuyển tiếp:

~~~bash
java \
  --add-opens com.example.customer.core/com.example.customer.entity=ALL-UNNAMED \
  -m com.example.application/com.example.application.Main
~~~

Đây nên là cấu hình có chủ đích và được ghi nhận trong deployment. Tránh mở toàn bộ module hoặc nhiều package JDK chỉ để làm một framework cũ tiếp tục chạy.

Một boundary bền vững nên cung cấp API hoặc factory thay vì buộc module tiêu thụ truy cập private field của implementation. Nếu cần ORM hoặc serializer, hãy xác định package nào phải mở và cho module nào ngay từ thiết kế.

## 9. ServiceLoader và plugin qua boundary

Nếu hệ thống legacy tìm plugin bằng cách quét classpath, có thể chuyển dần sang ServiceLoader khi đã có SPI rõ ràng.

Consumer module khai báo uses:

~~~java
module com.example.application {
    requires com.example.plugin.api;

    uses com.example.plugin.api.Plugin;
}
~~~

Provider module khai báo provides:

~~~java
module com.example.plugin.csv {
    requires com.example.plugin.api;

    provides com.example.plugin.api.Plugin
        with com.example.plugin.csv.CsvPlugin;
}
~~~

ServiceLoader tìm provider theo metadata service. Với provider trên classpath, dùng file META-INF/services tương ứng. Với named module, khai báo trong module-info.java.

Nếu plugin được nạp trong ModuleLayer riêng, hãy tìm provider trong đúng layer:

~~~java
ServiceLoader<Plugin> plugins =
    ServiceLoader.load(pluginLayer, Plugin.class);
~~~

Khi tạo runtime image bằng jlink, --bind-services có thể liên kết provider module được khai báo cho service và các phụ thuộc cần thiết. Provider được chọn bằng cấu hình hoặc reflection động có thể không được jlink suy ra; cần đưa module phù hợp vào graph bằng cấu hình link.

ServiceLoader phù hợp cho SPI có hợp đồng ổn định. Nếu framework vẫn cần annotation scanning cho component khác, hãy kiểm tra framework có hỗ trợ module path và module layer hay không. Không giả định scanner classpath sẽ tự nhìn thấy mọi named module.

## 10. Resource lookup và cấu hình qua boundary

Resource nội bộ nên được đọc theo module sở hữu nó. Nếu resource nằm cạnh class:

~~~java
InputStream input =
    ConfigReader.class.getResourceAsStream("defaults.properties");
~~~

Hoặc dùng đường dẫn từ gốc package/module:

~~~java
InputStream input =
    ConfigReader.class.getResourceAsStream(
        "/com/example/customer/config/defaults.properties"
    );
~~~

API Module.getResourceAsStream cũng cho phép chỉ rõ module chứa resource. Resource trong package của named module có thể chịu quy tắc đóng gói; nếu module khác cần truy cập resource nội bộ, cân nhắc mở đúng package hoặc cung cấp API đọc resource.

Phân biệt resource mặc định với cấu hình môi trường:

- Template, schema hoặc dữ liệu mặc định có thể được đóng gói trong module.
- Cấu hình theo môi trường nên được cung cấp từ filesystem, biến môi trường hoặc hệ thống cấu hình triển khai.
- Bí mật và thông tin xác thực không nên nhúng vào JAR.
- Không để module tiêu thụ tự đọc trực tiếp file nội bộ của module khác nếu có thể cung cấp API cấu hình rõ ràng.

Khi chuyển resource từ classpath sang module, hãy kiểm tra đường dẫn tương đối, tên resource, package sở hữu và classloader. Một file có thể còn trong JAR nhưng không còn được tìm thấy bằng cách quét URL như trước.

## 11. Tổ chức build và deployment trong giai đoạn hỗn hợp

Trong giai đoạn migration, build cần mô tả rõ phần nào là module source, phần nào là modular JAR, automatic module hoặc classpath library.

Ví dụ biên dịch named module với thư viện trên module path:

~~~bash
javac \
  --module-path lib \
  --module-source-path src \
  -d out \
  -m com.example.application
~~~

Chạy module:

~~~bash
java \
  --module-path "out:lib" \
  -m com.example.application/com.example.application.Main
~~~

Trên Windows, dấu phân cách module path là dấu chấm phẩy thay vì dấu hai chấm.

Nếu vẫn còn legacy JAR trên classpath, cấu hình runtime cần thể hiện rõ cả hai đường nạp. Tránh đặt cùng một thư viện trên classpath và module path. Trùng lặp class hoặc tên module có thể gây lỗi khó chẩn đoán.

Trong CI, nên có các bước riêng:

1. Build và test phần legacy theo cách hiện tại.
2. Build named module và kiểm tra module descriptor.
3. Chạy integration test qua boundary thật.
4. Đóng gói đúng JAR/module sẽ triển khai.
5. Chạy kiểm thử trên module path hoặc runtime image.
6. Kiểm tra cấu hình JVM như add-opens, service provider và resource.
7. Lưu module graph, dependency tree và phiên bản toolchain.

Đừng chỉ kiểm thử trong IDE nếu IDE đang tự thêm classpath, module path hoặc VM options khác production.

## 12. Định nghĩa tiêu chí hoàn tất cho từng boundary

Một phần legacy chỉ nên được coi là đã chuyển đổi khi có thể chứng minh các điều kiện cần thiết:

- Module hoặc project có owner và trách nhiệm rõ.
- API công khai đã được xác định; implementation nội bộ không bị import tùy tiện.
- Module descriptor khai báo đúng requires, exports, opens, uses và provides.
- Không còn split package hoặc phụ thuộc vòng không hợp lệ.
- Reflection và resource lookup hoạt động trên cấu hình module thực tế.
- Service provider được tìm thấy trong đúng module layer.
- Integration test xác nhận dữ liệu và hành vi qua boundary.
- Build và deployment tái lập được từ artifact đã đóng gói.
- Các tùy chọn runtime tạm thời như add-opens có owner và kế hoạch loại bỏ.
- Dependency cũ không còn được sử dụng đã được loại khỏi build.

Tiêu chí hoàn tất nên gắn với capability hoặc module cụ thể. Không cần chờ toàn hệ thống chuyển đổi mới ghi nhận một boundary đã ổn định.

## 13. Lộ trình migration theo từng bước

Một lộ trình thực tế có thể gồm:

1. **Inventory:** thu thập dependency tree, package, reflection, service, resource và classloader.
2. **Choose boundary:** chọn một capability ít phụ thuộc chéo, có API tương đối rõ.
3. **Define contract:** tạo API hoặc SPI, tách DTO cần dùng khỏi implementation legacy.
4. **Add adapter:** cô lập legacy API, mapping và lỗi chuyển đổi.
5. **Modularize:** thêm module descriptor, khai báo requires và exports.
6. **Resolve runtime access:** cấu hình opens có mục tiêu, ServiceLoader và resource lookup.
7. **Build and test:** chạy compile, integration test và packaged runtime test.
8. **Deploy gradually:** phát hành theo service hoặc capability, theo dõi log và lỗi tương thích.
9. **Remove transitional paths:** khi không còn consumer cũ, loại bỏ adapter, automatic module hoặc add-opens tạm thời.
10. **Repeat:** chọn boundary tiếp theo dựa trên dependency graph đã cập nhật.

Bắt đầu với boundary có ít rủi ro và ít phụ thuộc ngược để xác nhận quy trình. Sau khi build, test và deployment hoạt động ổn định, có thể áp dụng cùng cách làm cho các capability phức tạp hơn.

## 14. Ghi nhớ

- Migration boundary xác định ranh giới giữa phần modular và phần legacy, cùng API được phép đi qua ranh giới.
- Classpath có thể tiếp tục tồn tại trong giai đoạn chuyển đổi; unnamed module không được khai báo bằng requires.
- Automatic module là bước tương thích hữu ích nhưng cần có kế hoạch chuyển sang descriptor rõ ràng.
- Adapter giúp cô lập legacy API và chuyển đổi mô hình dữ liệu.
- Split package và vòng phụ thuộc cần được xử lý ở cấp kiến trúc, không chỉ bằng tùy chọn dòng lệnh.
- Reflection cần exports hoặc opens đúng mục đích; ServiceLoader cần uses/provides; resource cần được đọc từ đúng module.
- Kiểm thử phải chạy trên artifact và cấu hình gần production.
- Mỗi boundary nên có tiêu chí hoàn tất và kế hoạch loại bỏ cấu hình chuyển tiếp.

Một migration boundary tốt giúp hệ thống chuyển đổi từng phần mà vẫn giữ được hợp đồng giữa các thành phần. Hãy ưu tiên API ổn định, adapter rõ trách nhiệm, module graph có thể phân giải và kiểm thử qua ranh giới thật. Khi một capability đã độc lập và được triển khai ổn định, có thể tiếp tục chuyển boundary kế tiếp mà không cần viết lại toàn bộ hệ thống cùng lúc.
