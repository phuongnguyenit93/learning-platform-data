# Automatic module làm lộ split package

Split package xảy ra khi cùng một package Java được chứa trong nhiều module. Trên classpath, nhiều JAR có thể cùng chứa class thuộc một package; class loader thường tìm class theo thứ tự classpath và ứng dụng có thể chạy dù cấu trúc đó không rõ ràng. Khi chuyển các JAR sang module path, mỗi JAR có thể trở thành một module riêng. Module system khi đó có thể phát hiện package bị chia giữa các module và từ chối resolve cấu hình.

Automatic module thường làm vấn đề này lộ ra trong quá trình migration. Một JAR chưa có module-info.class khi đặt trên module path có thể được coi là automatic module. Nó có tên module, có thể được yêu cầu bằng requires, đọc các module khác và export các package của mình. Nhưng việc trở thành automatic module không hợp nhất package của JAR đó với package cùng tên trong dependency khác.

Bài viết này giải thích vì sao lỗi xuất hiện khi chuyển từ classpath sang module path, cách tìm module gây trùng package và các hướng xử lý an toàn.

## 1. Split package là gì?

Giả sử có hai thư viện:

~~~text
lib/
|-- customer-api.jar
|   |-- com/example/model/Customer.class
|   |-- com/example/model/Address.class
|
|-- customer-legacy.jar
    |-- com/example/model/LegacyCustomer.class
    |-- com/example/model/CustomerMapper.class
~~~

Cả hai JAR đều chứa package com.example.model. Trên classpath, class loader có thể nạp các class từ hai JAR theo thứ tự tìm kiếm. Việc này có thể hoạt động, nhưng quyền sở hữu package bị chia cho hai artifact. Kết quả phụ thuộc vào cách đóng gói, thứ tự classpath và class nào được nạp trước.

Nếu hai JAR được nhận diện thành hai module riêng trên module path, module system phải xác định package thuộc module nào. Một cấu hình module không thể dựa vào việc hai module cùng sở hữu một package để tạo ra một package thống nhất. Quá trình resolve có thể thất bại với lỗi split package, thường được báo qua ResolutionException hoặc thông báo module chứa cùng package.

Split package không chỉ là vấn đề trùng tên class. Hai JAR có thể chứa các class khác nhau nhưng cùng package; như vậy vẫn là split package. Ngược lại, hai JAR có cùng tên class nhưng ở package khác nhau không tạo ra split package theo nghĩa này.

## 2. Vì sao automatic module làm lỗi xuất hiện?

Một JAR chưa có module descriptor có thể được module finder coi là automatic module khi đặt trên module path. Tên module có thể lấy từ thuộc tính Automatic-Module-Name trong manifest; nếu không có, tên có thể được suy ra từ tên file JAR theo quy tắc đặt tên automatic module.

Ví dụ:

~~~text
customer-api.jar
    Automatic-Module-Name: com.example.customer.api

customer-legacy-2.4.jar
    (không có module-info.class)
    (không có Automatic-Module-Name)
~~~

Khi đặt các JAR này trên module path, chúng có thể được nhận diện thành các module riêng. Nếu cả hai chứa package com.example.model và cùng nằm trong cấu hình được resolve, package trùng lặp sẽ bị phát hiện.

Automatic module có một số đặc điểm đặc biệt:

- Có tên module và có thể được tham chiếu bằng requires.
- Đọc tất cả các module khác trong cấu hình theo quy tắc dành cho automatic module.
- Export tất cả package của mình.
- Có thể dùng để chuyển tiếp các thư viện cũ trong giai đoạn migration.
- Không biến các package trùng tên trong những JAR khác thành một package duy nhất.

Do automatic module export tất cả package, một module named có thể đọc các package của nó. Điều đó không có nghĩa hai automatic module được phép cùng sở hữu một package trong cùng cấu hình module.

Automatic-Module-Name chỉ ổn định tên module khi tên file thay đổi. Nó không sửa split package, không hợp nhất hai JAR và không thay thế module descriptor.

## 3. Tình huống thường gặp khi chuyển từ classpath sang module path

Trước khi modular hóa, ứng dụng có thể chạy với:

~~~bash
java -cp "app.jar;lib/*" com.example.app.Main
~~~

Trên Windows, dấu chấm phẩy phân tách classpath. Trên Linux và macOS, dùng dấu hai chấm.

Khi chuyển thư viện lên module path:

~~~bash
java --module-path "mods;lib" \
     --module com.example.app/com.example.app.Main
~~~

Một JAR cũ không có module-info.class có thể trở thành automatic module. Nếu dependency graph chứa hai JAR cùng package, module resolution có thể thất bại trước khi main method được gọi.

Điều này giải thích vì sao một ứng dụng chạy bình thường trên classpath nhưng không khởi động được trên module path. Module path áp dụng quy tắc về module identity, readability và package ownership chặt chẽ hơn.

Không phải mọi JAR trong thư mục lib đều tự động trở thành module. Chỉ những artifact được tìm thấy theo quy tắc module path và được đưa vào cấu hình mới tham gia resolution. Một JAR vẫn nằm trên classpath thuộc unnamed module và có phạm vi truy cập khác.

## 4. Cách đọc lỗi split package

Thông báo lỗi thường nêu tên package và hai module cùng chứa package đó. Ví dụ minh họa:

~~~text
java.lang.module.ResolutionException:
Module com.example.customer.api contains package
com.example.model, module customer.legacy exports package
com.example.model to com.example.customer.api
~~~

Tên module và cách diễn đạt cụ thể phụ thuộc JDK, cấu hình và giai đoạn phát hiện. Hãy lấy package được nêu trong lỗi làm điểm bắt đầu.

Khi đọc lỗi:

1. Ghi lại package trùng, ví dụ com.example.model.
2. Ghi lại tất cả module được nhắc tới.
3. Xác định mỗi module đến từ JAR hoặc thư mục nào trên module path.
4. Kiểm tra dependency tree để biết tại sao cả hai artifact cùng được đưa vào.
5. Xác định class nào thực sự thuộc về từng artifact và module nào nên sở hữu package đó.

Đừng vội thêm --add-exports hoặc --add-reads. Các tùy chọn này điều chỉnh quyền truy cập và quan hệ readability; chúng không hợp nhất package và không giải quyết xung đột package ownership.

## 5. Tìm package trùng bằng công cụ JDK

### Kiểm tra module descriptor của từng JAR

Dùng jar --describe-module để xem tên module, package và thông tin descriptor của từng archive:

~~~bash
jar --describe-module --file lib/customer-api.jar
jar --describe-module --file lib/customer-legacy-2.4.jar
~~~

Nếu JAR là automatic module, đầu ra có thể cho biết tên automatic module và package mà công cụ nhận diện. Nếu JAR có module-info.class, đầu ra hiển thị module descriptor.

Kiểm tra manifest để biết tên automatic module có được khai báo ổn định hay không:

~~~bash
unzip -p lib/customer-api.jar META-INF/MANIFEST.MF
~~~

Tìm thuộc tính Automatic-Module-Name. Thuộc tính này giúp tên module không phụ thuộc vào cách đặt tên file, nhưng không thay đổi danh sách package.

### Xác thực module path

Dùng Java launcher để kiểm tra cấu hình module:

~~~bash
java --module-path "mods;lib" --validate-modules
~~~

Lệnh này kiểm tra tính hợp lệ của các module quan sát được trên module path và báo các xung đột mà module system phát hiện. Điều chỉnh dấu phân cách path theo hệ điều hành.

Để xem module được resolve khi khởi chạy ứng dụng:

~~~bash
java --show-module-resolution \
     --module-path "mods;lib" \
     --module com.example.app/com.example.app.Main
~~~

Nếu resolution thất bại trước khi ứng dụng chạy, dùng thông tin lỗi cùng đầu ra jar --describe-module để xác định các JAR liên quan.

### Kiểm tra dependency của ứng dụng

jdeps giúp xem module phụ thuộc vào module nào:

~~~bash
jdeps --module-path "mods;lib" --print-module-deps app.jar
~~~

Có thể dùng:

~~~bash
jdeps --module-path "mods;lib" --check com.example.app
~~~

Kết quả hỗ trợ xác định dependency không cần thiết, dependency bắc cầu và module nào đang tham gia cấu hình. jdeps không thay thế việc kiểm tra package trong từng JAR; kết hợp nó với jar --describe-module và --validate-modules.

## 6. Tự động tìm package trùng bằng ModuleFinder

Nếu có nhiều JAR và cần báo cáo package nào xuất hiện ở nhiều module, có thể viết công cụ nhỏ dùng ModuleFinder và ModuleDescriptor.packages().

Ví dụ:

~~~java
import java.lang.module.ModuleDescriptor;
import java.lang.module.ModuleFinder;
import java.lang.module.ModuleReference;
import java.nio.file.Path;
import java.util.HashMap;
import java.util.Map;

public class FindSplitPackages {

    public static void main(String[] args) {
        ModuleFinder finder = ModuleFinder.of(
                Path.of("lib/customer-api.jar"),
                Path.of("lib/customer-legacy-2.4.jar"));

        Map<String, String> packageOwners = new HashMap<>();

        for (ModuleReference reference : finder.findAll()) {
            ModuleDescriptor descriptor = reference.descriptor();
            String moduleName = descriptor.name();

            for (String packageName : descriptor.packages()) {
                String previous = packageOwners.putIfAbsent(
                        packageName, moduleName);

                if (previous != null && !previous.equals(moduleName)) {
                    System.out.printf(
                            "Split package %s: %s and %s%n",
                            packageName, previous, moduleName);
                }
            }
        }
    }
}
~~~

Đoạn code này lập bản đồ package sang module đầu tiên nhìn thấy. Khi một package xuất hiện trong module khác, chương trình in ra xung đột tiềm năng.

Đây là phép rà soát tĩnh trên các artifact được đưa vào ModuleFinder. Nó không thay thế module resolution thực tế: một số module có thể không cùng được đưa vào cấu hình cuối cùng, và kết quả thực tế còn phụ thuộc root modules, module path, upgrade module path cùng quan hệ dependency.

Với automatic module, packages() phản ánh package được nhận diện từ nội dung archive. Với explicit module, descriptor có danh sách package của module. Hãy dùng đúng tập JAR mà ứng dụng thực sự đưa lên module path.

## 7. Các cách xử lý split package

Không có một tùy chọn launcher chung để biến hai module cùng sở hữu package thành một module hợp lệ. Chọn cách xử lý dựa trên quyền sở hữu package và khả năng thay đổi dependency.

### Ưu tiên nâng cấp hoặc thay thế dependency

Kiểm tra xem nhà cung cấp đã phát hành phiên bản mới loại bỏ package trùng, hợp nhất artifact hoặc thay đổi cách đóng gói chưa.

Nếu hai thư viện cùng chứa package do một bản phát hành cũ bị chia nhỏ, nâng cấp lên phiên bản đã sửa có thể giải quyết triệt để. Kiểm tra release notes và dependency tree trước khi nâng cấp.

Không chỉ nâng version một cách ngẫu nhiên. Hai thư viện có thể phụ thuộc vào các phiên bản API khác nhau; cần chạy test tương thích và xác nhận binary linkage.

### Loại bỏ dependency trùng không cần thiết

Một dependency có thể được kéo vào gián tiếp qua thư viện khác. Nếu ứng dụng đã có artifact cung cấp các class tương ứng, có thể exclude dependency dư thừa khỏi Maven hoặc Gradle.

Với Maven, exclusion minh họa:

~~~xml
<dependency>
    <groupId>com.example</groupId>
    <artifactId>customer-client</artifactId>
    <version>3.0</version>
    <exclusions>
        <exclusion>
            <groupId>com.example</groupId>
            <artifactId>customer-legacy</artifactId>
        </exclusion>
    </exclusions>
</dependency>
~~~

Sau khi loại bỏ, kiểm tra dependency tree và chạy test. Chỉ exclude khi chắc chắn ứng dụng không cần class hoặc resource chỉ có trong artifact bị loại bỏ.

### Hợp nhất package vào một module

Nếu hai artifact thực chất là các phần của cùng một thành phần và package cần được chia sẻ, giải pháp kiến trúc có thể là hợp nhất các class vào một module duy nhất.

Ví dụ:

~~~text
Trước:
customer-api.jar       -> com.example.model
customer-legacy.jar    -> com.example.model

Sau:
customer-module.jar    -> com.example.model
~~~

Việc hợp nhất có thể cần thay đổi build, module descriptor và quy trình phát hành. Nếu không thể sửa artifact gốc, có thể tạo một module nội bộ đóng gói lại các class cần thiết, nhưng phải kiểm soát license, service metadata, resource và binary compatibility.

### Relocate package của một dependency

Nếu một thư viện mang theo package nội bộ chỉ dùng bên trong và không cần chia sẻ kiểu với ứng dụng, có thể dùng shading/relocation để chuyển package sang namespace riêng.

Ví dụ:

~~~text
Trước:
com.example.model.LegacyCustomer

Sau:
com.example.shaded.legacy.model.LegacyCustomer
~~~

Relocation làm thay đổi tên binary class. Cần kiểm tra reflection, serialization, resource path, service provider configuration, annotation processor và các chuỗi class name được lưu trong cấu hình. Không relocate package API mà consumer phải tương tác trực tiếp nếu không có kế hoạch tương thích rõ ràng.

### Giữ một số dependency trên classpath trong giai đoạn chuyển đổi

Có thể để một thư viện cũ trên classpath để nó thuộc unnamed module, trong khi các module đã modular hóa nằm trên module path. Đây có thể là bước chuyển tiếp cho thành phần chưa sẵn sàng modular hóa.

Tuy nhiên, named module không đọc được unnamed module theo cơ chế readability thông thường. Nếu named module cần trực tiếp các class từ thư viện classpath, việc đặt thư viện ở classpath không giải quyết được dependency đó. Cần một adapter hoặc ranh giới tích hợp phù hợp.

Giải pháp classpath cũng không làm split package biến mất về mặt thiết kế; nó chỉ giữ các JAR trong một không gian class loader/unnamed module thay vì đưa từng JAR thành module riêng.

## 8. Vai trò của --patch-module và các tùy chọn add-*

--patch-module có thể thêm class hoặc resource vào một module hiện có:

~~~bash
java --patch-module com.example.customer=patches/customer \
     --module-path mods \
     --module com.example.app/com.example.app.Main
~~~

Nội dung patch được xem như một phần của module đích. Đây là cơ chế hữu ích cho kiểm thử, instrumentation hoặc trường hợp có chủ đích ghép nội dung module. Nó không phải giải pháp mặc định để che giấu hai thư viện độc lập đang sở hữu cùng package.

Các tùy chọn khác có phạm vi khác:

| Tùy chọn | Điều chỉnh | Có giải quyết split package không? |
|---|---|---|
| --add-exports | Cho phép module khác truy cập package public được export bổ sung | Không |
| --add-opens | Mở package cho deep reflection | Không |
| --add-reads | Bổ sung quan hệ readability giữa hai module | Không |
| --patch-module | Bổ sung class/resource vào module đích | Có thể dùng trong trường hợp đóng gói lại có chủ đích, nhưng cần thiết kế cẩn thận |

Không dùng add-exports, add-opens hoặc add-reads để xử lý lỗi package trùng. Chúng thay đổi quyền truy cập, không thay đổi việc package được chứa trong module nào.

## 9. Quy trình migration đề xuất

Khi một ứng dụng bắt đầu báo split package sau khi chuyển dependency sang module path, thực hiện theo thứ tự:

1. **Giữ nguyên log lỗi:** ghi lại tên package và các module được nêu.
2. **Xác định artifact:** dùng jar --describe-module để ánh xạ module name về JAR.
3. **Kiểm tra package:** xem package xuất hiện trong descriptor của module nào; có thể dùng ModuleFinder để tự động rà soát.
4. **Tìm nguồn dependency:** dùng dependency tree của build tool và jdeps để xác định dependency trực tiếp/bắc cầu.
5. **Chọn owner:** quyết định module nào là chủ sở hữu hợp lý của package.
6. **Sửa dependency hoặc đóng gói:** nâng cấp, exclude, hợp nhất hoặc relocate package tùy trường hợp.
7. **Validate lại:** chạy java --validate-modules và khởi động ứng dụng với --show-module-resolution.
8. **Kiểm thử chức năng:** xác minh API, service loading, reflection, serialization và binary compatibility.
9. **Cố định tên module:** với automatic module còn phải giữ lại, khai báo Automatic-Module-Name ổn định nếu có thể.
10. **Lập kế hoạch loại bỏ automatic module:** chuyển dần sang explicit module descriptor và dependency graph có chủ đích.

## 10. Những lỗi thường gặp

- **Chỉ đổi tên JAR:** tên file mới có thể đổi tên automatic module nhưng không thay đổi package bên trong.
- **Thêm Automatic-Module-Name và kỳ vọng hết lỗi:** thuộc tính này chỉ ổn định module name, không sửa package trùng.
- **Thêm --add-exports hoặc --add-reads:** các tùy chọn này không thay đổi package ownership.
- **Chỉ kiểm tra tên class:** split package có thể xảy ra dù hai JAR chứa các class khác nhau.
- **Chỉ kiểm tra một JAR:** cần so sánh package trên toàn bộ module path có liên quan.
- **Exclude dependency mà không kiểm thử:** có thể làm mất class hoặc resource cần thiết ở runtime.
- **Relocate package API:** có thể phá vỡ binary compatibility, reflection hoặc serialization.
- **Nhầm classpath với module path:** trên classpath, các JAR thường cùng thuộc unnamed module; trên module path, JAR có thể trở thành các module riêng.
- **Coi automatic module là module hoàn chỉnh:** automatic module là cầu nối migration; tên, package và dependency của nó vẫn cần được kiểm soát.

## 11. Ghi nhớ

Automatic module giúp đưa thư viện cũ lên module path mà chưa cần module-info.class, nhưng nó không hợp nhất các package bị chia giữa nhiều JAR. Khi các JAR trở thành module riêng, module resolution có thể phát hiện split package và từ chối cấu hình.

Hãy xác định package và các module sở hữu nó bằng jar --describe-module, jdeps, --validate-modules hoặc ModuleFinder. Sau đó chọn một chủ sở hữu package rõ ràng: nâng cấp dependency, loại bỏ bản trùng, hợp nhất artifact hoặc relocate package nội bộ. Các tùy chọn add-exports/add-opens/add-reads không giải quyết xung đột package ownership.

## Tài liệu tham khảo

- Java Platform Module System — ModuleFinder và Configuration API: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/module/package-summary.html
- Java Launcher — --validate-modules, --module-path và --show-module-resolution: https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html
- The jar Command — --describe-module: https://docs.oracle.com/en/java/javase/26/docs/specs/man/jar.html
- jdeps — Java Dependency Analysis Tool: https://docs.oracle.com/en/java/javase/26/docs/specs/man/jdeps.html
