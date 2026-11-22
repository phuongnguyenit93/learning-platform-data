# Vì sao một package không được chia giữa named module

## 1. Mục tiêu

Trong Java Platform Module System (JPMS), package là đơn vị tổ chức class và interface; module là đơn vị gom nhiều package thành một thành phần có ranh giới dependency và encapsulation. Một package có thể chứa nhiều compilation unit, nhưng khi đưa các module vào cùng một ứng dụng modular, package cần có nguồn hiển thị rõ ràng đối với từng module sử dụng.

Tình huống thường gây lỗi là **split package**: cùng một tên package, ví dụ com.acme.shared, xuất hiện trong nhiều named module. Một module tiêu thụ đọc cả hai module và cả hai cùng export package đó. Khi ấy compiler và module resolver không thể coi package là một tập type duy nhất có nguồn sở hữu rõ ràng.

Bài này giải thích:

- Vì sao package cần có một nguồn hiển thị duy nhất đối với từng consumer.
- Quy tắc chính xác của JPMS và những trường hợp tạo xung đột.
- Vì sao exports, requires và class loader có liên quan.
- Cách phát hiện, sửa split package khi tách một thư viện lớn thành nhiều module.
- Những ngoại lệ runtime cần phân biệt để không hiểu quy tắc quá tuyệt đối.

**Lưu ý về phạm vi:** JPMS không đơn giản cấm mọi trường hợp hai module ở bất kỳ đâu có cùng tên package. Quy tắc quan trọng là package phải uniquely visible đối với module đang biên dịch. Tuy nhiên, trong kiến trúc ứng dụng thông thường, nên thiết kế để một package thuộc về một named module duy nhất; cách này tránh xung đột khi module graph thay đổi và tương thích với cách tạo layer dùng chung một class loader.

## 2. Phân biệt package và module

Package nhóm các type theo tên đầy đủ:

~~~java
package com.acme.shared;

public final class Ids {
    private Ids() {}

    public static String newId() {
        return java.util.UUID.randomUUID().toString();
    }
}
~~~

Một module có thể chứa nhiều package:

~~~text
com.acme.orders
  ├── com.acme.orders.api
  ├── com.acme.orders.domain
  └── com.acme.orders.internal
~~~

Module descriptor xác định dependency và package nào được công khai:

~~~java
module com.acme.orders {
    requires com.acme.customer.api;

    exports com.acme.orders.api;
}
~~~

Tên package và tên module là hai namespace khác nhau:

- **com.acme.orders** có thể là tên module.
- **com.acme.orders.api** là tên package.
- Module com.acme.orders có thể chứa nhiều package, trong đó một số được export và số khác được giữ internal.

Tên package có dấu chấm thể hiện cấu trúc tên. Package con không tự động là một phần của package cha. Ví dụ com.acme.shared và com.acme.shared.internal là hai package khác nhau. Vì vậy, việc một module chứa com.acme.shared còn module khác chứa com.acme.shared.internal không tự nó tạo split package.

## 3. Split package là gì?

Giả sử một thư viện cũ chứa hai nhóm class trong cùng package:

~~~text
legacy-library/
  com/acme/shared/
    Ids.java
    StringUtils.java
    DateUtils.java
    JsonSupport.java
    XmlSupport.java
~~~

Khi tách thành hai module theo chức năng, người phát triển có thể chia file như sau:

~~~text
module com.acme.shared.core
  com.acme.shared.Ids
  com.acme.shared.StringUtils
  com.acme.shared.DateUtils

module com.acme.shared.formats
  com.acme.shared.JsonSupport
  com.acme.shared.XmlSupport
~~~

Cả hai module đều chứa package com.acme.shared. Đây là split package.

Nếu cả hai module export package này:

~~~java
module com.acme.shared.core {
    exports com.acme.shared;
}
~~~

~~~java
module com.acme.shared.formats {
    exports com.acme.shared;
}
~~~

và ứng dụng đọc cả hai:

~~~java
module com.acme.application {
    requires com.acme.shared.core;
    requires com.acme.shared.formats;
}
~~~

thì application nhìn thấy package com.acme.shared được export từ hai module. Package không còn uniquely visible đối với application. Module resolution thất bại thay vì chọn ngẫu nhiên một nguồn.

Điểm cần hiểu là lỗi không đơn thuần do hai thư mục trên ổ đĩa có cùng tên. Nó xuất phát từ module graph và quan hệ exports/readability: module consumer nhìn thấy cùng một package từ nhiều module.

## 4. Quy tắc uniquely visible trong JLS

JLS Java SE 21, mục **7.4.3 — Package Observability and Visibility**, định nghĩa khi nào một package uniquely visible đối với module M.

Có hai trường hợp:

1. Một compilation unit thuộc module M khai báo package đó, và M không đọc module nào khác export package đó cho M.
2. Không có compilation unit nào thuộc M khai báo package đó, và M đọc chính xác một module khác export package đó cho M.

Nếu không thỏa một trong hai trường hợp, package không uniquely visible đối với M.

Có thể diễn giải bằng bảng:

| Tình huống đối với module consumer M | Kết quả |
|---|---|
| M tự chứa package p, không có module đọc được nào khác export p cho M | p uniquely visible từ M |
| M không tự chứa p và chỉ một module được M đọc export p cho M | p uniquely visible từ module đó |
| M không tự chứa p và hai module được M đọc cùng export p cho M | Xung đột, không uniquely visible |
| M tự chứa p và một module khác mà M đọc cũng export p cho M | Xung đột, không uniquely visible |

Module resolution có consistency check tương ứng. Resolution thất bại nếu hai hay nhiều module trong configuration export cùng một package cho một module đọc được cả hai. Trường hợp module M tự chứa package p nhưng lại đọc một module khác export p cho M cũng thuộc nhóm xung đột.

Điều này giải thích vì sao một module có thể biên dịch riêng nhưng khi ghép vào ứng dụng lớn lại lỗi: module mới được đặt trong một graph có thêm dependency, khiến một package trước đó uniquely visible nay có nhiều nguồn.

## 5. Vì sao JPMS cần quy tắc này?

### Tránh tên package có nhiều nguồn trong cùng compilation context

Khi source trong module M viết:

~~~java
import com.acme.shared.Ids;
~~~

compiler cần xác định package com.acme.shared và type Ids đến từ đâu. Nếu M đọc hai module đều export package này, việc phân giải tên không có một nguồn package duy nhất theo quy tắc của JLS.

Không nên dựa vào thứ tự module path, thứ tự JAR hoặc thứ tự dependency để quyết định type nào thắng. JPMS yêu cầu module graph rõ ràng thay vì cho phép một classpath search order ngầm quyết định API.

### Giữ ranh giới module có ý nghĩa

Module được thiết kế để nhóm các package liên quan thành một thành phần. Nếu cùng một package bị chia giữa nhiều module, người sử dụng khó biết module nào sở hữu API, module nào chịu trách nhiệm tương thích và module nào cần được nâng cấp cùng module còn lại.

Một package duy nhất trong một module giúp descriptor xác định rõ:

- Module nào sở hữu các type của package.
- Module nào có thể đọc package thông qua requires.
- Module nào được truy cập public type thông qua exports.
- Các implementation nội bộ nào vẫn được giữ kín trong module.

### Tránh phụ thuộc vào cách nạp class

Một class loader cần tìm được module chịu trách nhiệm cho package khi nạp type. Nếu nhiều module cùng được định nghĩa cho một class loader nhưng chứa cùng package, việc ánh xạ package sang module trở nên mơ hồ.

API **ModuleLayer.defineModulesWithOneLoader** từ chối tạo layer khi hai hoặc nhiều module trong configuration có package trùng nhau. Đây là một ràng buộc runtime cụ thể của mô hình dùng chung một class loader.

Với nhiều class loader, runtime có thể cô lập các module có package trùng tên trong những trường hợp nâng cao. Điều đó không biến chúng thành một package chung và cũng không loại bỏ các consistency check về exports/readability trong module configuration.

## 6. requires và exports kết hợp tạo ra xung đột ra sao?

Hai directive có vai trò khác nhau:

- **requires** tạo dependency và readability từ module khai báo tới module được yêu cầu.
- **exports** cho phép các module phù hợp truy cập public type trong package.

Ví dụ:

~~~java
module com.acme.lib.one {
    exports com.acme.shared;
}
~~~

~~~java
module com.acme.lib.two {
    exports com.acme.shared;
}
~~~

~~~java
module com.acme.application {
    requires com.acme.lib.one;
    requires com.acme.lib.two;
}
~~~

Application đọc cả lib.one và lib.two; cả hai export com.acme.shared cho application. Đây là xung đột.

Nếu chỉ một module export package cho application, module đó có thể là nguồn duy nhất mà application nhìn thấy. Tuy nhiên, giữ một package vật lý trong nhiều module vẫn là thiết kế mong manh: thêm một requires, đổi qualified exports thành unqualified exports hoặc đổi cách tạo layer có thể làm graph chuyển sang trạng thái xung đột.

### requires transitive có thể làm xung đột xuất hiện gián tiếp

Giả sử application chỉ yêu cầu facade:

~~~java
module com.acme.application {
    requires com.acme.facade;
}
~~~

Nhưng facade khai báo:

~~~java
module com.acme.facade {
    requires transitive com.acme.lib.one;
    requires transitive com.acme.lib.two;
}
~~~

Application đọc cả lib.one và lib.two do các cạnh transitive. Nếu hai module export cùng package cho application, xung đột vẫn xảy ra dù application không khai báo requires trực tiếp từng module.

Khi điều tra split package, phải xem toàn bộ readability graph, bao gồm requires transitive, chứ không chỉ nhìn module-info.java của ứng dụng.

## 7. Qualified exports có giải quyết được không?

Qualified export chỉ export package cho một nhóm module cụ thể:

~~~java
module com.acme.lib.one {
    exports com.acme.shared to com.acme.application;
}
~~~

~~~java
module com.acme.lib.two {
    exports com.acme.shared to com.acme.plugin;
}
~~~

Nếu application chỉ đọc lib.one và không nhận export com.acme.shared từ lib.two, package có thể uniquely visible đối với application từ lib.one.

Tuy nhiên, qualified exports chỉ giới hạn ai nhìn thấy package. Nó không hợp nhất hai phần package, không làm package-private member dùng chung giữa hai module và không tự giải quyết mọi cấu hình consumer khác.

Không nên dùng qualified exports để che một split package không có ranh giới thiết kế rõ ràng. Nó có thể phù hợp trong kiến trúc có chủ ý với nhiều module consumer được cô lập, nhưng cần kiểm soát graph của từng consumer.

### opens không thay thế exports

**opens** phục vụ deep reflection ở runtime. Nó không làm package trở thành package được export cho truy cập Java thông thường khi biên dịch. Vì vậy, thêm opens không phải cách sửa lỗi package không uniquely visible trong source compilation.

## 8. Tại sao không thể dựa vào package-private để chia package?

Trong một package Java thông thường, các type và member không có modifier truy cập thường có package access. Điều này thường khiến người phát triển muốn chia các class cùng package thành nhiều module để giữ quyền truy cập nội bộ.

Ví dụ:

~~~java
package com.acme.shared;

final class InternalCache {
    static Object load() {
        return new Object();
    }
}
~~~

~~~java
package com.acme.shared;

public final class PublicFacade {
    public Object get() {
        return InternalCache.load();
    }
}
~~~

Trong mô hình một module, PublicFacade có thể sử dụng InternalCache vì cả hai thuộc cùng package của module.

Khi tách hai class sang hai named module, cùng viết dòng package com.acme.shared không biến hai module thành một package nội bộ chung. Module boundaries và class loader/module identity vẫn có hiệu lực; package-private access không phải cơ chế chia sẻ API giữa hai module.

Nếu class ở module khác cần được gọi, hãy thiết kế public API rõ ràng trong package được export. Nếu một implementation phải dùng package-private internals của facade, hãy giữ các class đó trong cùng module.

## 9. Subpackage có thể nằm ở module khác không?

Có. Package cha và subpackage là hai package khác nhau.

Ví dụ:

~~~text
module com.acme.shared.api
  com.acme.shared.api

module com.acme.shared.internal
  com.acme.shared.internal
~~~

Module API:

~~~java
module com.acme.shared.api {
    exports com.acme.shared.api;
}
~~~

Module internal:

~~~java
module com.acme.shared.internal {
    requires com.acme.shared.api;
}
~~~

Đây không phải split package vì hai tên package khác nhau. Package com.acme.shared.api và com.acme.shared.internal có quan hệ tên phân cấp nhưng không có quan hệ package-private access đặc biệt.

Việc chia subpackage theo module là một cách tổ chức hợp lệ, miễn là dependency và exports được khai báo rõ ràng. Không nên giả định rằng code trong com.acme.shared.internal tự động truy cập package-private members của com.acme.shared.api.

## 10. Trường hợp runtime layer và class loader

Cần phân biệt hai câu hỏi:

1. **Module resolution:** package có uniquely visible đối với các module consumer theo readability và exports không?
2. **Layer/class loader:** các module đã resolve có thể được ánh xạ vào class loader được chọn để nạp type không?

Khi dùng:

~~~java
ModuleLayer.defineModulesWithOneLoader(
        configuration,
        List.of(ModuleLayer.boot()),
        ClassLoader.getSystemClassLoader());
~~~

mọi module trong configuration được định nghĩa cho cùng một class loader. API quy định thao tác có thể thất bại với **LayerInstantiationException** nếu hai hay nhiều module có package trùng nhau.

Với:

~~~java
ModuleLayer.defineModulesWithManyLoaders(
        configuration,
        ClassLoader.getSystemClassLoader());
~~~

mỗi module được định nghĩa trong class loader riêng. Điều này có thể cô lập package trùng tên giữa các module trong các trường hợp runtime nâng cao. Tuy nhiên:

- Mỗi module vẫn là một module riêng.
- Type có cùng tên đầy đủ nhưng được nạp từ module/class loader khác nhau không trở thành cùng một type.
- Consumer vẫn phải thỏa các quy tắc readability và exports.
- Một consumer không thể đọc hai module cùng export package đó cho nó mà vẫn có package uniquely visible.

Do đó, nhiều class loader là cơ chế cô lập runtime, không phải cách thiết kế một package dùng chung giữa các module.

## 11. Automatic modules và thư viện cũ

Khi một JAR không có module-info.class được đặt trên module path, nó có thể trở thành automatic module. Automatic module có một số quy tắc rộng:

- Module name được suy ra từ tên JAR hoặc metadata tương ứng.
- Automatic module đọc các module được enumerated trong configuration.
- Các package trong automatic module được export theo quy tắc automatic module.

Điều này có thể làm split package cũ dễ lộ ra khi chuyển thư viện từ classpath sang module path. Hai thư viện cũ có thể cùng chứa package com.vendor.common; trên classpath, class loader search order có thể khiến ứng dụng vẫn chạy. Khi trở thành automatic modules và các module cùng được đọc, exports rộng có thể tạo xung đột.

Khi modularize thư viện cũ:

1. Kiểm tra package thực tế trong từng JAR.
2. Xác định package nào trùng giữa các dependency.
3. Xác định module consumer có đọc cả các module đó không.
4. Ưu tiên nâng cấp hoặc thay thế thư viện có package trùng.
5. Nếu cần, relocate package của một thư viện bằng shading/bytecode relocation trước khi đưa vào module path.
6. Chỉ dùng classpath hoặc automatic module như bước chuyển tiếp có chủ đích, không coi đó là giải pháp kiến trúc dài hạn.

## 12. Cách phát hiện split package

### Kiểm kê package trong JAR

Liệt kê nội dung JAR:

~~~text
jar --list --file library-one.jar
jar --list --file library-two.jar
~~~

Tìm các đường dẫn package trùng nhau, ví dụ:

~~~text
com/acme/shared/Ids.class
com/acme/shared/StringUtils.class
~~~

Có thể dùng script hoặc công cụ build để tạo danh sách package từ các entry .class, bỏ qua META-INF và module-info.class khi thống kê type package.

### Xem module descriptor

~~~text
jar --describe-module --file library-one.jar
jar --describe-module --file library-two.jar
~~~

Lệnh này cho biết tên module, requires, exports, opens, uses và provides. Với automatic module, output có thể hiển thị các package mà module chứa.

### Kiểm tra module graph

Đọc tất cả module-info.java và xác định consumer đọc module nào. Tính cả requires transitive và các root module được launcher/build tool chọn.

Tìm các trường hợp:

- Hai module export cùng package cho một consumer.
- Consumer tự chứa package và đồng thời đọc module khác export package đó cho consumer.
- Automatic module làm cho nhiều module được đọc và export package rộng hơn dự kiến.

Có thể dùng:

~~~text
java --validate-modules --module-path mods
~~~

để yêu cầu launcher kiểm tra module path và các module có thể resolve theo cấu hình tương ứng. Với dự án thực tế, hãy chạy bằng đúng module path, root modules và JDK mà ứng dụng sẽ sử dụng; một lệnh kiểm tra trên tập module khác không chứng minh deployment graph hợp lệ.

## 13. Cách sửa split package

### Cách 1 — Gộp các class cùng package về một module

Nếu các class cần chia sẻ package-private API hoặc tạo thành một đơn vị logic, giữ toàn bộ package trong một module:

~~~text
module com.acme.shared
  com.acme.shared.Ids
  com.acme.shared.StringUtils
  com.acme.shared.JsonSupport
  com.acme.shared.XmlSupport
~~~

Các module khác chỉ đọc module shared và dùng API public được export. Đây thường là lựa chọn ít rủi ro nhất khi package vốn được thiết kế như một đơn vị.

### Cách 2 — Đổi package name theo trách nhiệm

Nếu hai nhóm class thực sự là hai API độc lập, đổi package để thể hiện ranh giới:

~~~text
module com.acme.shared.core
  com.acme.shared.core.Ids
  com.acme.shared.core.StringUtils

module com.acme.shared.formats
  com.acme.shared.formats.json.JsonSupport
  com.acme.shared.formats.xml.XmlSupport
~~~

Module descriptor:

~~~java
module com.acme.shared.core {
    exports com.acme.shared.core;
}
~~~

~~~java
module com.acme.shared.formats {
    requires com.acme.shared.core;

    exports com.acme.shared.formats.json;
    exports com.acme.shared.formats.xml;
}
~~~

Consumer có thể đọc cả hai mà không có package collision:

~~~java
module com.acme.application {
    requires com.acme.shared.core;
    requires com.acme.shared.formats;
}
~~~

Việc đổi package là thay đổi API. Cần cập nhật import, reflection string, service metadata, serialization config, framework scanning, test và tài liệu.

### Cách 3 — Tạo API module riêng

Nếu nhiều implementation cần chia sẻ contract, đưa interface và public type vào một API module:

~~~text
com.acme.codec.api
  com.acme.codec.Codec
  com.acme.codec.CodecException

com.acme.codec.json
  com.acme.codec.json.JsonCodec

com.acme.codec.xml
  com.acme.codec.xml.XmlCodec
~~~

API module:

~~~java
module com.acme.codec.api {
    exports com.acme.codec;
}
~~~

Provider module:

~~~java
module com.acme.codec.json {
    requires com.acme.codec.api;

    provides com.acme.codec.Codec
        with com.acme.codec.json.JsonCodec;
}
~~~

Các implementation dùng package riêng. Consumer phụ thuộc API module và tìm implementation qua ServiceLoader hoặc cấu hình injection. Cách này tách contract khỏi implementation mà không chia package.

### Cách 4 — Relocate package của dependency bên thứ ba

Nếu hai thư viện bên thứ ba chứa cùng package nhưng không thể sửa source, có thể dùng shading/relocation để đổi package của một dependency khi đóng gói.

Ví dụ, relocate:

~~~text
com.vendor.common
~~~

thành:

~~~text
com.acme.internal.shaded.vendor.common
~~~

Relocation phải cập nhật cả bytecode reference và metadata liên quan. Hãy kiểm tra reflection, service provider file, resource path, serialization, native integration và license obligations. Không chỉ đổi tên folder trong JAR vì bytecode vẫn tham chiếu tên cũ.

### Cách 5 — Patch một module trong tình huống có chủ đích

Tùy chọn **--patch-module** cho phép bổ sung class/resource vào một named module đã tồn tại. Các class được patch trở thành nội dung của module đích theo cơ chế patch.

Ví dụ:

~~~text
javac
  --patch-module com.acme.shared=patches/shared
  -d build/test-patch
  ...
~~~

Cơ chế này hữu ích cho test, instrumentation hoặc migration có kiểm soát. Nó không tạo ra hai owner module cho cùng package; mục đích là bổ sung nội dung vào một module đã chọn. Không dùng patch module như cách lắp ghép tùy tiện nhiều thư viện production có package collision.

## 14. Vì sao đổi module name không đủ?

Giả sử đổi:

~~~text
com.acme.shared.core
com.acme.shared.extra
~~~

thành hai module name khác nhưng cả hai vẫn chứa package:

~~~text
com.acme.shared
~~~

thì package collision vẫn còn. Module name chỉ thay đổi định danh module; nó không đổi package name hoặc quy tắc uniquely visible.

Tương tự, đổi tên artifact Maven/Gradle, đổi tên JAR hoặc đặt file trong thư mục khác không giải quyết split package nếu module graph vẫn export cùng package cho một consumer.

Muốn giải quyết, cần thay đổi ít nhất một yếu tố có ý nghĩa:

- Package name.
- Module ownership của các class.
- Quan hệ readability/exports theo một thiết kế có chủ đích.
- Cách cô lập runtime layer/class loader trong kiến trúc plugin đặc biệt.

## 15. Quy trình thiết kế package khi tách module

1. Liệt kê package và type của thư viện hiện tại.
2. Gom các type theo trách nhiệm và mức độ gắn kết; xác định những type cần package-private access.
3. Gán mỗi package vào một module sở hữu.
4. Tạo module-info.java với requires và exports tối thiểu.
5. Đổi package nếu hai nhóm class cần thuộc các module độc lập.
6. Tách public API thành module API nếu nhiều implementation cùng dùng contract.
7. Kiểm tra requires transitive và automatic modules để phát hiện readability gián tiếp.
8. Kiểm tra các JAR đầu vào để tìm package trùng.
9. Resolve module graph với đúng root modules của ứng dụng.
10. Tạo runtime layer theo chiến lược class loader thực tế.
11. Chạy test compile-time và runtime trên module path, không chỉ trên classpath.
12. Kiểm tra các đường dẫn reflection, ServiceLoader, resource và serialization sau khi đổi package.

## 16. Các hiểu nhầm thường gặp

### Nghĩ chỉ cần đổi tên module

Không đủ. Xung đột liên quan tới package được export và visibility đối với consumer. Hai module name khác nhau vẫn có thể export cùng một package.

### Nghĩ package cha và subpackage là một package

Không đúng. com.acme và com.acme.internal là hai package riêng. Chúng có quan hệ phân cấp về tên, nhưng không chia sẻ package-private access.

### Nghĩ mọi package trùng tên ở mọi module đều bị cấm tuyệt đối

Cần diễn đạt chính xác hơn. JLS đặt quy tắc uniquely visible đối với từng module consumer; module resolution kiểm tra xung đột exports/readability. Ngoài ra, cách tạo layer có thể đặt ràng buộc riêng. Ví dụ defineModulesWithOneLoader từ chối overlapping packages trong configuration, trong khi mô hình nhiều class loader có thể cô lập module theo cách khác. Với ứng dụng modular thông thường, vẫn nên tránh split package để graph dễ hiểu và ổn định.

### Nghĩ opens có thể thay exports

Không. opens phục vụ deep reflection ở runtime; exports mới là cơ chế công khai package cho truy cập Java thông thường giữa module.

### Nghĩ requires transitive chỉ ảnh hưởng compile-time API

Nó còn ảnh hưởng readability graph của module tiêu thụ. Vì vậy, nó có thể làm consumer nhìn thấy thêm một module export package trùng.

### Nghĩ đặt một JAR lên classpath là đã sửa package collision

Classpath có thể làm thay đổi cách module được quan sát, nhưng đưa thư viện ra unnamed module cũng thay đổi encapsulation và dependency model. Hãy dùng như giải pháp chuyển tiếp được kiểm soát, không phải cách làm package dùng chung giữa named modules.

## 17. Bài tập tự kiểm tra và đáp án

### Bài 1 — Hai module cùng export một package

Module A và B đều export com.acme.shared. Module C requires cả A và B. Điều gì xảy ra?

**Đáp án:** Package com.acme.shared được export tới C từ hai module mà C đọc. Package không uniquely visible và module resolution thất bại.

### Bài 2 — Consumer chỉ đọc một module

A và B cùng chứa com.acme.shared, nhưng chỉ A export package cho C; C chỉ đọc A. Có nhất thiết xảy ra xung đột exports đối với C không?

**Đáp án:** Không. Theo quy tắc uniquely visible, nếu C không tự chứa package và chỉ đúng một module C đọc export package đó cho C, package có thể uniquely visible từ A. Tuy nhiên, cần xem toàn bộ graph và cách tạo runtime layer.

### Bài 3 — Package con

Module A chứa com.acme.shared.api; module B chứa com.acme.shared.internal. Đây có phải split package không?

**Đáp án:** Không. Hai tên đầy đủ là hai package khác nhau. Package hierarchy không tạo quan hệ package-private access.

### Bài 4 — requires transitive

C chỉ requires A. A khai báo requires transitive B. Nếu A và B đều export cùng package p cho C, vì sao C vẫn có thể gặp lỗi?

**Đáp án:** C đọc B gián tiếp qua cạnh transitive. Module resolution xét readability graph cuối cùng, không chỉ requires trực tiếp trong module-info.java của C.

### Bài 5 — opens

Nếu B opens com.acme.shared cho C nhưng không exports package này, điều đó có tạo package visibility cho source C không?

**Đáp án:** Không. opens cho phép deep reflection ở runtime; nó không thay thế exports trong quy tắc truy cập source/module.

### Bài 6 — Một class loader

Hai module trong cùng configuration chứa package com.acme.shared. Có thể tạo layer bằng defineModulesWithOneLoader không?

**Đáp án:** Không. API ModuleLayer quy định layer dùng chung một class loader không thể được tạo nếu các module có overlapping packages; thao tác ném LayerInstantiationException.

### Bài 7 — Nhiều class loader

Dùng defineModulesWithManyLoaders có biến hai package trùng tên thành một package dùng chung không?

**Đáp án:** Không. Mỗi module có class loader riêng; đây là cơ chế cô lập. Quy tắc readability/exports của module configuration vẫn áp dụng.

### Bài 8 — Cách sửa phù hợp

Hai nhóm class cần được phát hành và nâng cấp độc lập, không cần package-private access giữa chúng. Nên làm gì?

**Đáp án:** Tách thành các package có tên riêng theo trách nhiệm, sau đó export API cần thiết và khai báo requires. Nếu nhiều implementation cùng chia sẻ contract, tạo API module riêng.

## 18. Checklist khi review split package

- Đã kiểm kê đầy đủ package trong từng named module/JAR chưa?
- Hai module có cùng chứa một package đầy đủ không?
- Consumer nào đọc các module đó, kể cả qua requires transitive?
- Có hai module cùng export package cho một consumer không?
- Consumer có tự chứa package và đồng thời đọc module khác export package đó không?
- Có automatic module nào làm readability hoặc exports rộng hơn dự kiến không?
- Có nhầm package cha với subpackage không?
- Các type cần package-private access đã được giữ trong cùng module chưa?
- Có thể đổi package, gộp module hoặc tạo API module riêng không?
- Nếu dùng nhiều ModuleLayer/class loader, ranh giới và type identity đã được thiết kế rõ chưa?
- Đã kiểm tra đúng module path và root modules của deployment chưa?
- Có test compile-time và runtime sau khi chuyển từ classpath sang module path không?

**Ghi nhớ:** Một package cần có nguồn hiển thị duy nhất đối với từng module consumer. Xung đột xảy ra khi consumer nhìn thấy cùng package được export từ nhiều module, hoặc package nội bộ của nó bị trùng với package được module khác export cho nó. Hãy gán package theo ranh giới module, dùng package name riêng cho các thành phần độc lập và chỉ dùng nhiều class loader khi thực sự cần cô lập module.

## Tài liệu tham khảo

- Java Language Specification, Java SE 21 — 7.4.3 Package Observability and Visibility: https://docs.oracle.com/javase/specs/jls/se21/html/jls-7.html#jls-7.4.3
- Oracle Java SE 21 API — java.lang.module package summary, Module Resolution: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/module/package-summary.html
- Oracle Java SE 21 API — ModuleLayer, defineModulesWithOneLoader và defineModulesWithManyLoaders: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ModuleLayer.html
- Oracle Java SE 21 API — Configuration: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/module/Configuration.html
- OpenJDK JEP 261 — Module System: https://openjdk.org/jeps/261
