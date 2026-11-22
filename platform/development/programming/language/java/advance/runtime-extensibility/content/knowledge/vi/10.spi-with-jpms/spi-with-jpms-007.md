# Phân biệt khả năng đọc module, exports và opens cho truy cập phản chiếu

Trong **Java Platform Module System (JPMS)**, một class tồn tại trong module khác không có nghĩa là ứng dụng có quyền gọi class đó, và càng không có nghĩa là reflection có thể đọc mọi private field hay gọi private constructor. Để thiết kế SPI, framework tích hợp plugin và hệ thống nạp module đúng, cần phân biệt ba câu hỏi:

1. **Readability:** Module đang gọi có *đọc* module chứa kiểu cần dùng không?
2. **Exports:** Package chứa kiểu có *công bố API* cho module đang gọi không?
3. **Opens:** Package có *cho phép truy cập phản chiếu sâu* từ module đang thực hiện reflection không?

Ba yếu tố liên quan nhưng giải quyết các vấn đề khác nhau. Một câu lệnh requires không tự export các package. Một exports không tự mở private field cho reflection. Một opens không biến package thành API có thể import ở bước biên dịch.

## 1. Readability là quan hệ giữa hai module

Giả sử có hai named module:

~~~text
demo.consumer  --requires-->  demo.library
~~~

Trong **src/demo.consumer/module-info.java**:

~~~java
module demo.consumer {
    requires demo.library;
}
~~~

Khi module graph được giải quyết, module demo.consumer **reads** demo.library. Quan hệ đọc này cho phép compiler và runtime xét quyền sử dụng những kiểu từ demo.library, nhưng vẫn phải thỏa quyền truy cập package và quyền truy cập của Java như public/private.

Ví dụ nếu demo.library **không exports** package demo.library.internal, thì thêm requires demo.library ở consumer vẫn không đủ để viết:

~~~java
// Minh họa lỗi biên dịch: package internal không được exports.
import demo.library.internal.Secret;
~~~

Đây là **dòng minh họa bị cấm bởi biên module**, không phải đoạn source dùng trong chương trình chạy ở phần 5.

Các điểm cần nhớ:

- requires X biểu thị dependency của module hiện tại vào X và tạo cạnh đọc module theo JPMS; named module mặc định có khả năng đọc java.base mà không cần khai báo.
- requires transitive X làm khả năng đọc X lan tới module khác đang đọc module khai báo requires transitive; nó **không tự động exports** các package trong X.
- requires static X là dependency lúc biên dịch và tùy chọn lúc runtime; nó cũng không thay thế exports/opens.
- Module.canRead(other) giúp quan sát readability thực tế ở runtime. Quan hệ có thể được bổ sung động hoặc bằng launcher, nên cần phân biệt module-info.java với đồ thị runtime.
- Việc một module đọc được module khác không chứng minh class trong package bên kia được truy cập từ mã nguồn.

## 2. Exports công bố package làm API thông thường

Ví dụ trong **src/demo.library/module-info.java**:

~~~java
module demo.library {
    exports demo.library.api;
}
~~~

Directive exports demo.library.api khiến các **public type được phép truy cập** trong package đó, cùng public/protected member theo quy tắc truy cập Java, trở thành API cho những module thích hợp.

Để mã ở demo.consumer dùng trực tiếp một public class trong demo.library.api, cần đồng thời:

- demo.consumer đọc demo.library (ở đây qua requires demo.library);
- demo.library exports demo.library.api cho demo.consumer;
- class và member có mức truy cập Java phù hợp.

Một public class ở **package không exports** vẫn không tự trở thành public API bên ngoài module. Và exports không biến private field thành public field: private vẫn chịu các kiểm tra thông thường.

Có thể giới hạn exports theo danh sách module đích:

~~~java
module demo.library {
    exports demo.library.api to demo.consumer;
}
~~~

Đây là **qualified export**: công bố package cho demo.consumer nhưng không công bố cho mọi module. Không có nghĩa demo.consumer tự động đọc demo.library; consumer vẫn cần readability hợp lệ khi dùng API trong source.

### Public reflection qua package đã exports

Nếu package đã exports cho module phản chiếu, Java reflection thường có thể gọi **public constructor/method trên public class** theo quyền truy cập thông thường. Chẳng hạn:

~~~java
Class<?> type = Class.forName("demo.library.api.PublicApi");
Object object = type.getConstructor().newInstance();
Object result = type.getMethod("greet").invoke(object);
~~~

Đây là **đoạn minh họa đặt bên trong method có xử lý checked exceptions**, không phải chương trình độc lập. Nó giả định PublicApi có public constructor không tham số và public greet(). Nó chỉ sử dụng public member; không cần gọi setAccessible(true).

Ngược lại, exports **không đủ** để truy cập private constructor, private field hay private method của class nằm trong package ấy từ một module khác. Chuyển sang reflection không làm private access tự biến mất.

## 3. Opens cho phép reflection sâu mà không mở API lúc biên dịch

Directive opens khác exports về mục tiêu:

~~~java
module demo.library {
    exports demo.library.api;
    opens demo.library.internal to demo.consumer;
}
~~~

Trong ví dụ này:

- Package demo.library.api là API công khai cho mã Java thông thường.
- Package demo.library.internal vẫn không thể được demo.consumer import dùng trực tiếp khi biên dịch, vì package này **không exports theo descriptor**.
- Nhưng code **thực hiện reflection trong demo.consumer** có thể truy cập sâu vào member của class thuộc demo.library.internal, kể cả private member, thông qua API reflection phù hợp.

Một opens có thể viết không có to để mở package cho mọi module, hoặc viết opens package to module1,module2 để giới hạn đúng những module cần phản chiếu. Trường hợp package thực sự phải dùng làm API biên dịch **và** cần private reflection, có thể khai báo **cả exports và opens** cho nó.

Ngoài ra còn cú pháp mở toàn bộ module:

~~~java
open module demo.library {
    exports demo.library.api;
}
~~~

Khai báo open module làm **mọi package** trong module có thể được phản chiếu sâu ở runtime. Đây là lựa chọn rộng, cần cân nhắc kỹ vì công bố nhiều chi tiết triển khai. Không được đặt từng directive opens bên trong open module vì module đã mở toàn bộ.

### Exports không đồng nghĩa opens

| Cấu hình module cung cấp | Direct import public API từ module đọc được | Phản chiếu public member theo quyền truy cập thông thường | Phản chiếu sâu vào private member từ module khác |
| --- | --- | --- | --- |
| Không exports, không opens package | Không | Không được cấp quyền truy cập vào member | Không |
| exports package | Có | Có đối với public type/member phù hợp | Không chỉ nhờ exports |
| opens package | Không chỉ nhờ opens | Có ở runtime theo quy tắc reflection | Có đối với module được mở |
| exports và opens package | Có | Có | Có đối với module được mở |
| open module | Chỉ các package exports mới là API biên dịch | Các package được mở hỗ trợ reflection runtime | Có cho các package trong module |

Ở cột *direct import*, cần thêm điều kiện consumer đọc module cung cấp và class/member có Java visibility phù hợp. Ở cột reflection, cần phân biệt **biết tên một class**, **lấy metadata của class**, **gọi public member** và **bỏ kiểm tra truy cập để gọi private member**: đó không phải cùng một quyền.

Một lưu ý quan trọng: exports nói đến việc công bố các **public/protected** thành phần theo những điều kiện Java visibility; không biến protected hoặc package-private thành public đối với mọi code bên ngoài.

## 4. Reflection có quy tắc riêng: tìm class không phải được phép truy cập

Java reflection có thể tìm class bằng tên và trả về Class object, hoặc lấy danh sách member bằng getDeclaredFields/getDeclaredMethods, ngay cả khi các member đó **không truy cập được**. Việc tìm ra tên field không chứng minh có quyền lấy giá trị field.

Hai API thường bị hiểu sai:

- AccessibleObject.setAccessible(true) **cố gắng** bỏ kiểm tra access mặc định. Trên JDK 17, nếu module chưa mở package phù hợp và không có điều kiện khác cho phép, lời gọi có thể ném InaccessibleObjectException.
- AccessibleObject.trySetAccessible() thực hiện cố gắng tương tự, nhưng trong tình huống bị từ chối vì quy tắc module có thể trả false thay vì ném InaccessibleObjectException. Nó vẫn có thể phát sinh những lỗi khác trong một số điều kiện, nên không coi là phương thức "không bao giờ ném lỗi".

Một lời gọi như sau:

~~~java
Field field = PublicApi.class.getDeclaredField("token");
boolean allowed = field.trySetAccessible();
~~~

chỉ cho biết có thể bỏ kiểm tra truy cập **đối với field cụ thể** tại thời điểm gọi, chứ không phải cho biết mọi member trong module đều đã được mở.

### Readability và reflection: một ngoại lệ cần phân biệt

Trong Java core reflection, các kiểm tra truy cập phản chiếu có quy tắc **giả định readability** trong một số trường hợp; vì vậy không thể lấy một lời gọi Class.forName hoặc Method.invoke thành công để kết luận module đang gọi có cạnh đọc tĩnh requires tương ứng.

Ngược lại, khi biên dịch tham chiếu kiểu theo tên từ module khác, compiler kiểm tra readability cùng exports. Khi đánh giá module graph thực tế, hãy dùng Module.canRead() cho readability; khi đánh giá quyền private reflection, hãy dùng Module.isOpen(packageName, targetModule) và phép thử truy cập thật sự. Đây là các quan sát khác nhau.

Với MethodHandles.privateLookupIn, việc mở package cũng quan trọng và còn có các điều kiện về lookup/readability riêng; không suy luận rằng privateLookupIn và core reflection luôn có cùng tập tiền điều kiện.

## 5. Ví dụ chạy được: một thư viện modular và một consumer modular

Ví dụ dùng **JDK 17+**, biên dịch với --release 17, không có dependency ngoài JDK. Nó minh họa đúng một public API package được exports, một internal package không được exports, và hai private field mà host muốn đọc bằng reflection.

Ban đầu demo.library **chưa opens package nào**. Ta chạy ba lần: mặc định, mở riêng internal, rồi mở internal và api. Bằng cách này, chỉ thay **tham số launcher** mà không cần sửa mã nguồn hoặc thay bytecode.

### 5.1. Cấu trúc thư mục

~~~text
src/
  demo.library/
    module-info.java
    demo/library/api/PublicApi.java
    demo/library/internal/Secret.java
  demo.consumer/
    module-info.java
    demo/consumer/Main.java

mods/
  demo.library/          # kết quả javac
  demo.consumer/         # kết quả javac
~~~

### 5.2. module-info.java của thư viện

**src/demo.library/module-info.java**

~~~java
module demo.library {
    exports demo.library.api;
}
~~~

Chỉ package api được exports. Package internal vẫn đóng đối với code ở các module khác; không có opens nào trong phiên bản ban đầu.

### 5.3. Hai class thuộc hai package

**src/demo.library/demo/library/api/PublicApi.java**

~~~java
package demo.library.api;

public final class PublicApi {
    private final String token = "api-private";

    public String greet() {
        return "HELLO";
    }
}
~~~

**src/demo.library/demo/library/internal/Secret.java**

~~~java
package demo.library.internal;

public final class Secret {
    private final String token = "internal-private";

    private Secret() {}
}
~~~

PublicApi là public class thuộc package được exports, có public constructor ngầm định và một private field. Secret thuộc package không exports, có private constructor và một private field. Bên ngoài module, direct source access vào Secret không được phép theo JPMS.

### 5.4. Consumer khai báo readability

**src/demo.consumer/module-info.java**

~~~java
module demo.consumer {
    requires demo.library;
}
~~~

Nhờ requires, consumer đọc library; nhờ exports, consumer được import PublicApi. Không có requires thì mã consumer dùng PublicApi trực tiếp sẽ không biên dịch trong cấu hình named module thông thường.

### 5.5. Consumer thử gọi trực tiếp và reflection

**src/demo.consumer/demo/consumer/Main.java**

~~~java
package demo.consumer;

import demo.library.api.PublicApi;
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;

public final class Main {
    public static void main(String[] args) throws Exception {
        Module caller = Main.class.getModule();
        Module lib = PublicApi.class.getModule();

        System.out.println("reads library: " + caller.canRead(lib));
        System.out.println("api exported: " +
                lib.isExported("demo.library.api", caller));
        System.out.println("internal exported: " +
                lib.isExported("demo.library.internal", caller));
        System.out.println("internal open: " +
                lib.isOpen("demo.library.internal", caller));
        System.out.println("direct public call: " +
                new PublicApi().greet());

        Field apiField = PublicApi.class.getDeclaredField("token");
        boolean apiAccess = apiField.trySetAccessible();
        System.out.println("api private accessible: " + apiAccess);
        if (apiAccess) {
            System.out.println("api token: " +
                    apiField.get(new PublicApi()));
        }

        Class<?> hiddenType =
                Class.forName("demo.library.internal.Secret");
        Constructor<?> ctor = hiddenType.getDeclaredConstructor();
        boolean ctorAccess = ctor.trySetAccessible();
        System.out.println("internal ctor accessible: " + ctorAccess);
        if (ctorAccess) {
            Object instance = ctor.newInstance();
            Field field = hiddenType.getDeclaredField("token");
            boolean fieldAccess = field.trySetAccessible();
            System.out.println("internal field accessible: " + fieldAccess);
            if (fieldAccess) {
                System.out.println("internal token: " +
                        field.get(instance));
            }
        }
    }
}
~~~

Code cố ý dùng Class.forName với tên Secret bằng chuỗi. Trong ví dụ có module đã được giải quyết và class loader tìm được Secret, Class.forName trả về Class object. Nhưng muốn gọi private constructor, Main vẫn cần quyền reflection. trySetAccessible trả false nếu quyền đang bị từ chối, nên ứng dụng không cố gọi newInstance khi chưa được phép.

### 5.6. Biên dịch bằng PowerShell

Chạy từ thư mục chứa src (Windows PowerShell, JDK 17 trở lên):

~~~powershell
New-Item -ItemType Directory -Force -Path 'mods/demo.library','mods/demo.consumer' | Out-Null

javac --release 17 -encoding UTF-8 -d mods/demo.library src/demo.library/module-info.java src/demo.library/demo/library/api/PublicApi.java src/demo.library/demo/library/internal/Secret.java

javac --release 17 -encoding UTF-8 --module-path mods -d mods/demo.consumer src/demo.consumer/module-info.java src/demo.consumer/demo/consumer/Main.java
~~~

Mỗi module được biên dịch vào một thư mục riêng dưới mods. Với modular application, --module-path là nơi javac/java tìm những module đã biên dịch. Dòng thứ hai cần demo.library trên module path để xử lý requires demo.library và import PublicApi.

### 5.7. Chạy mặc định: chưa mở reflection sâu

~~~powershell
java --module-path mods -m demo.consumer/demo.consumer.Main
~~~

**Stdout chính xác:**

~~~text
reads library: true
api exported: true
internal exported: false
internal open: false
direct public call: HELLO
api private accessible: false
internal ctor accessible: false
~~~

Giải thích từng điểm:

- Consumer reads library vì requires demo.library.
- api exported: true vì thư viện exports demo.library.api.
- internal exported: false và internal open: false vì package không được exports/opens.
- Mã Java gọi PublicApi.greet() trực tiếp thành công.
- private token của PublicApi **không** được truy cập sâu chỉ nhờ exports package api.
- Class.forName có thể tìm Secret, nhưng không được gọi private constructor từ consumer khi package internal còn đóng.

### 5.8. Chỉ mở package internal cho consumer ở runtime

~~~powershell
java --module-path mods --add-opens demo.library/demo.library.internal=demo.consumer -m demo.consumer/demo.consumer.Main
~~~

**Stdout chính xác:**

~~~text
reads library: true
api exported: true
internal exported: true
internal open: true
direct public call: HELLO
api private accessible: false
internal ctor accessible: true
internal field accessible: true
internal token: internal-private
~~~

Lúc này Main được phép gọi private constructor và đọc private field của Secret. **Chỉ package internal được mở**, vì vậy private token thuộc api vẫn không truy cập được.

Một chi tiết dễ gây ngạc nhiên: sau --add-opens, **internal exported: true** dù module-info.java vẫn không có exports demo.library.internal. Đây không phải lỗi ví dụ. Theo tài liệu java.lang.Module, **package đang open cho module đích cũng được coi là exported cho module đó ở runtime**, do vậy Module.isExported(package, target) trả true. Điều đó **không** có nghĩa directive opens đã trở thành một exports compile-time trong source module-info.java.

Vì vậy, nếu cần biết **khai báo tĩnh ban đầu**, đọc ModuleDescriptor.exports()/opens(); nếu cần biết **quyền runtime hiện hành**, xem Module.isExported()/isOpen(). Hai nguồn có thể khác nhau do launcher flags hoặc thay đổi module graph động.

### 5.9. Mở cả api và internal để kiểm tra private reflection

~~~powershell
java --module-path mods --add-opens demo.library/demo.library.api=demo.consumer --add-opens demo.library/demo.library.internal=demo.consumer -m demo.consumer/demo.consumer.Main
~~~

**Stdout chính xác:**

~~~text
reads library: true
api exported: true
internal exported: true
internal open: true
direct public call: HELLO
api private accessible: true
api token: api-private
internal ctor accessible: true
internal field accessible: true
internal token: internal-private
~~~

So với lần chạy mặc định, lần này private field của PublicApi cũng truy cập được. Thay đổi đến từ --add-opens demo.library/demo.library.api=demo.consumer; exports api vốn có từ đầu **chưa đủ** cho deep reflection.

Cả ba lệnh chạy và kết quả stdout ở trên đã được kiểm tra bằng javac --release 17 và chạy JVM trên JDK mới hơn. Ví dụ tự biên dịch và chạy mà không cần thư viện bên thứ ba.

## 6. Sử dụng exports và opens trong thiết kế SPI/plugin

Với plugin dùng JPMS, nên xác định rõ **phần hợp đồng ổn định** và **phần implementation nội bộ**:

~~~text
Host module                   Plugin implementation module
    |                                      |
    | requires demo.plugin.api             | requires demo.plugin.api
    v                                      v
            demo.plugin.api
            exports demo.plugin.spi

Host có thể tìm provider qua ServiceLoader và interface chung.
Plugin implementation không cần exports mọi package nội bộ.
~~~

Một khai báo điển hình cho named module dùng service là:

**Module hợp đồng:**

~~~java
module demo.plugin.api {
    exports demo.plugin.spi;
}
~~~

**Module cung cấp plugin:**

~~~java
module demo.plugin.provider {
    requires demo.plugin.api;
    provides demo.plugin.spi.Plugin with
            demo.plugin.internal.PluginImpl;
}
~~~

**Module host:**

~~~java
module demo.plugin.host {
    requires demo.plugin.api;
    uses demo.plugin.spi.Plugin;
}
~~~

Đây là **minh họa module-info.java trong ba module khác nhau**; cần có interface Plugin và lớp PluginImpl thực tế mới biên dịch được. Ý chính: khi provider được khai báo bằng provides ... with ... trên module path, **ServiceLoader có cơ chế tìm và khởi tạo provider theo JPMS**, không bắt buộc phải exports hoặc opens package implementation cho host chỉ để khám phá service.

Nếu host còn muốn trực tiếp phản chiếu vào private field/constructor của plugin, đó là yêu cầu **khác** với ServiceLoader discovery. Khi ấy cần cân nhắc một API có phương thức cấu hình công khai, hoặc mở package chính xác cho module thực sự làm reflection.

Không nên vì lỗi reflection mà mở toàn bộ module chứa plugin. Mở quá rộng khiến host/framework có quyền phản chiếu sâu vào các cấu trúc không được thiết kế làm hợp đồng, làm tăng coupling và rủi ro khi refactor.

### Module nào thực sự cần được mở?

Hãy xác định **module của đoạn code trực tiếp thực hiện access check**. Nếu host gọi một thư viện framework làm reflection, module cần được mở thường là **module của framework**, chẳng hạn một serializer hoặc persistence framework, chứ không nhất thiết chỉ module host. Khai báo qualified opens cần nhắm đúng module sử dụng reflection.

Ví dụ:

~~~java
module demo.library {
    exports demo.library.api;
    opens demo.library.model to demo.serializer;
}
~~~

Khi compile module-info.java có qualified target, công cụ build có thể cảnh báo nếu module đích chưa nhìn thấy được; bảo đảm module path và môi trường build được thiết lập nhất quán. Tên module của thư viện/framework phải là **tên module thực tế ở runtime**, không đoán theo package name hoặc tên JAR.

## 7. Runtime options: kiểm tra đúng cánh cửa cần mở

Java launcher cung cấp các tùy chọn để quan sát/khắc phục một ràng buộc module, thường hữu ích khi chẩn đoán ứng dụng đã đóng gói:

| Tùy chọn | Tác dụng chính | Không tự giải quyết |
| --- | --- | --- |
| --add-reads A=B | Bổ sung cạnh readability từ A sang B | Quyền export/open của package |
| --add-exports B/p=A | Export package p của B cho A tại runtime | Private reflection trong p |
| --add-opens B/p=A | Mở package p cho deep reflection từ A tại runtime | Source import vào package p ở lúc compile chỉ nhờ opens |

Ví dụ khi bị từ chối private reflection từ demo.consumer vào internal:

~~~text
--add-opens demo.library/demo.library.internal=demo.consumer
~~~

Nếu code phản chiếu nằm trên **classpath / unnamed module**, target thường cần là ALL-UNNAMED thay vì tên module:

~~~text
--add-opens demo.library/demo.library.internal=ALL-UNNAMED
~~~

Các tùy chọn này có thể làm chương trình hoạt động tại runtime, nhưng nên xem chúng là **cấu hình triển khai rõ ràng hoặc biện pháp chẩn đoán**, không mặc định mở vô hạn để né thiết kế API. Tránh dùng ALL-UNNAMED khi có thể giới hạn vào named module chính xác.

Một điểm quan trọng nữa: --add-exports chỉ tăng quyền truy cập public API runtime; nếu package chứa private field vẫn chưa opens, setAccessible(true) vẫn có thể bị từ chối. Tương tự, --add-opens không làm cho compiler tự chấp nhận một import vốn không được module-info exports.

## 8. Lỗi phổ biến và cách đọc thông báo

| Hiện tượng | Giải thích thường gặp | Cách xử lý |
| --- | --- | --- |
| Compiler báo module không đọc dependency | Thiếu requires hoặc cạnh readability phù hợp | Kiểm tra module-info, requires transitive và module path |
| Compiler báo package không visible / not exported | Có readability nhưng package không exports cho consumer | Chỉ exports đúng package API cần công bố |
| IllegalAccessException khi invoke/construct qua reflection | Class/member không accessible theo Java visibility hoặc module boundary | Kiểm tra public/exports và nhu cầu opens |
| InaccessibleObjectException khi setAccessible(true) | Không được phép tắt kiểm tra access với member đó | Kiểm tra opens đúng package và module làm reflection |
| trySetAccessible() trả false | Quyền deep reflection chưa được cấp | Xem Module.isOpen và thực thể đang truy cập |
| ClassNotFoundException | Module/JAR chưa được resolve/nạp hoặc class loader không tìm được tên | Kiểm tra module path, layer, tên nhị phân, class loader |
| isExported() trả true nhưng compile import vẫn thất bại | Package được open ở runtime hoặc quyền động khác với descriptor compile-time | Phân biệt runtime isExported và exports trong module-info |
| ServiceLoader không tìm thấy plugin | Thiếu uses/provides hoặc module/layer/provider không được discover | Kiểm tra JPMS service declarations và nguồn resolution |

**Không dùng getDeclaredFields() thành công làm phép thử quyền đọc private data.** Phải thử một hành vi thật như trySetAccessible(), Field.get() hoặc Method.invoke() trong chính module thực hiện reflection.

**Không sửa bằng cách exports mọi package.** Exports mở public API, không mở private field. Nếu framework cần private reflection, một qualified opens hẹp thường đúng mục tiêu hơn.

**Không dùng open module như đáp án mặc định.** Open toàn bộ package làm tăng bề mặt reflection. Trên JDK 17, strong encapsulation của named module là một thuộc tính kiến trúc cần chủ động quản lý.

## 9. Quy trình chẩn đoán một lỗi module thực tế

Khi gặp lỗi module lúc tích hợp plugin/framework:

1. Ghi lại **module nguồn gọi**, **module chứa class**, **package**, **member** và hành động cụ thể (import compile, invoke public method hay đọc private field).
2. Kiểm tra đồ thị readability: requires, requires transitive, Module.canRead() và việc module có thật sự được resolve vào layer không.
3. Kiểm tra exports với **target module chính xác**. Module.isExported(package, target) là trạng thái runtime, còn ModuleDescriptor.exports() cho biết declaration.
4. Nếu hành động là deep reflection, kiểm tra opens với target module thực sự gọi reflection; dùng Module.isOpen(package, target).
5. Xác nhận Java visibility: public type/member hay private/package-private/protected; quyền JPMS không làm đổi mọi quy tắc Java language access.
6. Kiểm tra thực tế bằng trySetAccessible() hoặc lời gọi reflection tương ứng, kèm stack trace gốc.
7. Khi cần dùng --add-opens hoặc --add-exports tạm thời, viết lại policy trong module-info.java hoặc tài liệu deployment một cách tối thiểu và có kiểm thử; tránh mở rộng quyền theo phản xạ.

Một hệ thống SPI ổn định thường chỉ exports những package hợp đồng, dùng requires/uses/provides cho quan hệ module/service và chỉ opens những package cần framework làm reflection sâu. Nhờ đó, plugin có thể được khám phá đúng mà vẫn giữ được encapsulation của các phần implementation.

## 10. Câu hỏi tự kiểm tra

**Consumer đã requires một module nhưng vẫn không import được class public, tại sao?** Vì requires tạo readability; còn module cung cấp phải exports package chứa class đó cho consumer.

**Package đã exports, có thể đọc private field bằng setAccessible(true) không?** Không mặc nhiên. Private member từ module khác vẫn cần opens thích hợp (hoặc điều kiện quyền truy cập khác theo đặc tả).

**Package đã opens mà không exports, consumer có import trực tiếp public class từ package đó không?** Không chỉ nhờ opens. Opens cấp quyền reflection runtime, không cấp quyền import source ở compile time.

**Vì sao Module.isExported() trả true sau --add-opens?** Java coi package đang open cho target module là exported cho target đó ở runtime. Đây là trạng thái động, không phải directive exports trong module descriptor ban đầu.

**Phát hiện provider bằng ServiceLoader có cần opens package implementation không?** Thông thường không chỉ vì service discovery trong named module dùng provides ... with ... và uses; deep reflection vào private member của provider là nhu cầu riêng.

**Khi framework thực hiện reflection thay host thì opens to ai?** Đến module chứa code framework đang thực hiện kiểm tra truy cập, theo module name hiện hành.

### Tài liệu chuẩn

- Java Language Specification 17, §7.7.2 *Exported and Opened Packages*: https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html
- Java SE 17, java.lang.Module (canRead, isExported, isOpen): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html
- Java SE 17, java.lang.reflect.AccessibleObject: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AccessibleObject.html
- Java SE 17, java.util.ServiceLoader: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html
- Dev.java, *Reflective Access with Open Modules and Open Packages*: https://dev.java/learn/organizing/modules/opening-for-reflection/

**Cách phân biệt cần giữ vững:** readability trả lời "module A có đọc module B không"; exports trả lời "package nào là public API cho consumer"; opens trả lời "module nào được reflection sâu vào package". Để xử lý lỗi chính xác, phải xác định đúng *loại truy cập* và *module đang thực hiện truy cập*, sau đó kiểm tra từng quyền riêng rẽ.
