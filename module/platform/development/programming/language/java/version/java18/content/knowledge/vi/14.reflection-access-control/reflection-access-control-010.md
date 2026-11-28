# Qualified opens trong module-info.java để giới hạn bên được reflection truy cập

> **Phạm vi:** Bài thuộc chương **Quyền reflection** của module `JAVA_VERSION_JAVA18`. Khi học những thay đổi từ Java 18 còn áp dụng trên JDK hiện đại, cần hiểu JEP 416 đã thay đổi cách JDK triển khai core reflection, còn hợp đồng truy cập giữa các named module vẫn tuân theo Java Platform Module System (JPMS). Bài này hướng dẫn dùng **qualified `opens`** trong `module-info.java` để cho phép **một số module được chỉ định** thực hiện deep reflection trên một package, kèm ví dụ kiểm chứng và chẩn đoán lỗi. Chỉ sử dụng cơ chế Java được hỗ trợ chính thức.

## 1. Vấn đề: có metadata chưa chắc được phép truy cập

Giả sử thư viện domain đóng gói trong một **named module** và khai báo lớp:

~~~java
package demo.domain.internal;

public final class InternalConfig {
    private final String region;

    private InternalConfig(String region) {
        this.region = region;
    }

    private String describe() {
        return "region=" + region;
    }
}
~~~

Một framework hoặc công cụ kiểm tra metadata có thể muốn dùng reflection để tìm constructor, đọc trường hoặc gọi phương thức private:

~~~java
Class<?> type = Class.forName("demo.domain.internal.InternalConfig");
var constructor = type.getDeclaredConstructor(String.class);
~~~

Việc `getDeclaredConstructor` trả về metadata **không có nghĩa** code từ module khác có quyền gọi constructor. Nếu gọi `constructor.setAccessible(true)` khi package không mở phù hợp, JDK có thể ném `java.lang.reflect.InaccessibleObjectException`. Nếu gọi `constructor.trySetAccessible()`, API có thể trả `false`.

JPMS cho phép người sở hữu module quyết định rõ **module nào** được quyền truy cập sâu vào package của mình thông qua khai báo:

~~~java
opens demo.domain.internal to demo.inspector;
~~~

Đây là **qualified opens**: package `demo.domain.internal` được mở cho module mang tên `demo.inspector`. Những module khác không nhận quyền deep reflection chỉ vì package đã được mở cho `demo.inspector`.

### Ba câu hỏi cần tách bạch

1. **Có nạp được lớp không?** Phụ thuộc khả năng tìm lớp và module/class loader, cùng cách module tham gia module graph.
2. **Có lấy được metadata không?** `getDeclaredField` / `getDeclaredMethod` có thể tìm thành viên private được khai báo, nhưng chưa cấp quyền thực thi.
3. **Có được nới kiểm tra truy cập để gọi/đọc/ghi không?** Phụ thuộc access control thông thường và module/package có mở cho đúng caller hay không.

`opens` giải quyết câu hỏi thứ ba trong phạm vi module system; nó không làm xuất hiện lớp hoặc giải quyết lỗi chữ ký, đối số, constructor, dependency.

## 2. Cú pháp qualified opens và các tên phải khớp

Ví dụ `module-info.java` thuộc module sở hữu dữ liệu:

~~~java
module demo.domain {
    opens demo.domain.internal to demo.inspector;
}
~~~

Trong khai báo trên:

| Thành phần | Ý nghĩa |
|---|---|
| `demo.domain` sau `module` | Tên **module sở hữu** package và lớp cần truy cập |
| `demo.domain.internal` sau `opens` | Tên **package chính xác** được mở để reflection ở runtime |
| `demo.inspector` sau `to` | Tên **named module nhận quyền** truy cập sâu |
| Từ khóa `opens` | Cho phép deep reflection theo phạm vi được quy định bởi JPMS |
| Từ khóa `to` | Giới hạn việc mở package đến các module được liệt kê |

Có thể cấp cho nhiều module:

~~~java
module demo.domain {
    opens demo.domain.internal
            to demo.inspector, demo.serializer;
}
~~~

Danh sách sau `to` chứa **tên module**, không phải tên package, tên Maven artifact, tên lớp Java hoặc chuỗi `groupId:artifactId`. Tên module của một thư viện bên thứ ba phải kiểm tra từ cách thư viện thực sự được triển khai trên module path; không suy ra từ tên file JAR.

Qualified opens giới hạn theo **package và target module**:

- Mở `demo.domain.internal` không tự mở package con `demo.domain.internal.extra`.
- Không thể mở một lớp hoặc một field duy nhất bằng `opens`; phạm vi nhỏ nhất của directive là **package**.
- Module tên `demo.inspector` được quyền thực hiện deep reflection trên package được mở; không có cú pháp `opens ... to <tên lớp>`.
- Danh sách target là các **named module**. Code chạy trong unnamed module trên classpath không có module name để ghi trực tiếp trong `to`.

Nếu code gọi reflection đã chạy trong chính module sở hữu class, nó có những khả năng truy cập nội bộ khác theo API reflection; bài này tập trung vào **caller ở module khác**.

## 3. `exports`, `opens`, `open module` khác nhau như thế nào?

Chọn directive dựa trên nhu cầu của người sử dụng package.

| Khai báo trong module sở hữu | Ai được hưởng | Mục đích chính | Quyền deep reflection với private member |
|---|---|---|---|
| `exports p;` | Các module khác, theo quy tắc module system | Cho phép dùng public types trong `p` như API ở compile time và runtime | Không được cấp chỉ bởi `exports` |
| `exports p to a;` | Named module `a` | Giới hạn bên được sử dụng public API của `p` | Không được cấp chỉ bởi `exports ... to` |
| `opens p;` | Các module khác ở runtime | Mở package cho deep reflection một cách rộng | Có thể được cho phép theo quy tắc reflection |
| `opens p to a;` | Named module `a` ở runtime | Mở package có chọn lọc cho framework/caller cụ thể | Có thể được cho phép đối với `a` |
| `open module m { ... }` | Các module khác ở runtime | Mở các package của module theo phạm vi rộng | Rộng hơn nhu cầu chỉ mở một package |

Trong bảng, `p` là package và `a` là named module minh họa.

Điểm cần nắm:

- **`exports`** phục vụ việc công bố **public API** cho code của module khác sử dụng theo quy tắc Java. `exports` đơn thuần không cho phép truy cập private members từ module khác bằng `setAccessible(true)`.
- **`opens`** phục vụ **runtime reflection**, bao gồm yêu cầu bỏ kiểm tra truy cập Java thông thường khi module system cho phép. Nó không làm package trở thành API công khai cho việc import/biên dịch source của module khác.
- **Qualified opens** là lựa chọn phù hợp khi framework cần đọc private field hoặc gọi non-public constructor, trong khi ứng dụng không muốn công bố package đó như API để compile.
- Không cần `exports` cùng một package chỉ để một named module dùng **deep reflection** trên package đó. Nếu bên nhận đồng thời phải import các public types từ package trong source, bài toán có thể cần thêm `exports` phù hợp.
- `open module` mở phạm vi lớn; không dùng kiểu khai báo rộng đó khi yêu cầu chỉ là cho phép một framework truy cập một package xác định.

Ví dụ một module vừa công bố public API, vừa mở model nội bộ cho một module framework:

~~~java
module demo.domain {
    exports demo.domain.api;
    opens demo.domain.model to demo.inspector;
}
~~~

Code trong `demo.inspector` có thể dùng public API tại `demo.domain.api` nếu phụ thuộc module được khai báo đầy đủ, và có thể deep-reflect package `demo.domain.model`. Việc mở package model không đồng nghĩa code trong `demo.inspector` được `import demo.domain.model.SomeClass;` nếu package model không được export phù hợp.

## 4. Ví dụ hoàn chỉnh với hai named module

Ví dụ dùng **JDK 18 trở lên**, chỉ cần `javac` và `java`. Ta tạo module `demo.domain` chứa lớp nội bộ cùng module `demo.inspector` sử dụng reflection. Package cần mở **không được export**; caller dùng tên lớp dạng chuỗi để phân tích.

### 4.1. Cấu trúc dự án

~~~text
qualified-opens-demo/
├── src/
│   ├── demo.domain/
│   │   ├── module-info.java
│   │   └── demo/domain/internal/InternalConfig.java
│   └── demo.inspector/
│       ├── module-info.java
│       └── demo/inspector/Main.java
└── out/                         # Tạo sau khi biên dịch
~~~

Thư mục `src/<module-name>/` phù hợp với tùy chọn `--module-source-path src` của `javac` trong ví dụ. Không cần Maven, Gradle hoặc dependency ngoài JDK để thử cơ chế này.

### 4.2. Module sở hữu: `demo.domain`

Tệp `src/demo.domain/module-info.java`:

~~~java
module demo.domain {
    opens demo.domain.internal to demo.inspector;
}
~~~

Tệp `src/demo.domain/demo/domain/internal/InternalConfig.java`:

~~~java
package demo.domain.internal;

public final class InternalConfig {
    private final String region;

    private InternalConfig(String region) {
        this.region = region;
    }

    private String describe() {
        return "region=" + region;
    }
}
~~~

Constructor, field và method đều `private` để thấy rõ việc cần **deep reflection**. Bản thân class là `public`, nhưng package của nó không được export.

### 4.3. Module được phép: `demo.inspector`

Tệp `src/demo.inspector/module-info.java`:

~~~java
module demo.inspector {
    requires demo.domain;
}
~~~

`requires demo.domain` giúp mô tả phụ thuộc module và bảo đảm module domain được giải quyết trong module graph khi chạy ví dụ. Nó **không tự cấp** quyền deep reflection; quyền tương ứng nằm trong `opens ... to demo.inspector` của `demo.domain`.

Tệp `src/demo.inspector/demo/inspector/Main.java`:

~~~java
package demo.inspector;

import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.Method;

public final class Main {
    public static void main(String[] args)
            throws ReflectiveOperationException {

        // Nạp bằng binary name, không import package internal.
        Class<?> type =
                Class.forName("demo.domain.internal.InternalConfig");

        Module owner = type.getModule();
        Module caller = Main.class.getModule();

        System.out.println("Owner module: " + owner.getName());
        System.out.println("Caller module: " + caller.getName());
        System.out.println("Open to caller: " +
                owner.isOpen("demo.domain.internal", caller));

        Constructor<?> constructor =
                type.getDeclaredConstructor(String.class);
        if (!constructor.trySetAccessible()) {
            throw new IllegalStateException(
                    "Constructor access denied by module rules");
        }
        Object config = constructor.newInstance("ap-southeast");

        Field region = type.getDeclaredField("region");
        if (!region.trySetAccessible()) {
            throw new IllegalStateException(
                    "Field access denied by module rules");
        }
        System.out.println("Private field: " + region.get(config));

        Method describe = type.getDeclaredMethod("describe");
        if (!describe.trySetAccessible()) {
            throw new IllegalStateException(
                    "Method access denied by module rules");
        }
        System.out.println("Private method: " +
                describe.invoke(config));
    }
}
~~~

Ba phương thức `trySetAccessible()` kiểm chứng cụ thể rằng caller có được nới kiểm tra quyền truy cập đối với các member private hay không. `Module.isOpen(packageName, callerModule)` giúp chẩn đoán cấu hình mở package trước khi thực hiện các phép gọi.

Ở đây chỉ có class name dưới dạng chuỗi; `demo.inspector.Main` không truy cập các kiểu thuộc `demo.domain.internal` tại compile time.

### 4.4. Biên dịch và chạy

Từ thư mục `qualified-opens-demo`, dùng PowerShell trên Windows:

~~~powershell
javac -encoding UTF-8 --module-source-path src -d out -m "demo.domain,demo.inspector"

java --module-path out -m demo.inspector/demo.inspector.Main
~~~

Trên Linux/macOS, các lệnh tương đương:

~~~sh
javac -encoding UTF-8 --module-source-path src -d out -m demo.domain,demo.inspector
java --module-path out -m demo.inspector/demo.inspector.Main
~~~

Dự kiến:

~~~text
Owner module: demo.domain
Caller module: demo.inspector
Open to caller: true
Private field: ap-southeast
Private method: region=ap-southeast
~~~

**Diễn giải:**

1. `demo.domain` sở hữu class `InternalConfig` và mở đúng package của nó cho `demo.inspector`.
2. `Main` gọi `Class.forName` và lấy metadata constructor, field, method từ lớp sở hữu.
3. `trySetAccessible()` thành công nhờ directive `opens ... to demo.inspector`.
4. Reflection tạo instance với constructor private, đọc field private và gọi method private.
5. Kết quả chỉ chứng minh quyền truy cập trong **cấu hình module hiện tại**. Nó không cho phép suy ra một module khác sẽ có cùng quyền.

Bài này ghi ví dụ hoàn chỉnh để bạn tự kiểm chứng trên JDK đang dùng. Trong STEP 4, nội dung được kiểm tra bằng đọc lại tệp; bước chạy biên dịch và Content QA sẽ được tiến hành theo quy trình kiểm thử tương ứng.

## 5. Kiểm chứng quyền bị từ chối khi thiếu qualified opens

Để hiểu rõ tác dụng của directive, trong dự án minh họa **tạm thời** thay nội dung `src/demo.domain/module-info.java` thành:

~~~java
module demo.domain {
    // Không mở demo.domain.internal cho demo.inspector.
}
~~~

Biên dịch và chạy lại hai module bằng cùng các lệnh ở mục 4.4. Lúc này, dòng:

~~~text
Open to caller: false
~~~

cho biết package không được mở cho caller. Khi tới:

~~~java
if (!constructor.trySetAccessible()) {
    throw new IllegalStateException(
            "Constructor access denied by module rules");
}
~~~

`trySetAccessible()` trả `false`; ví dụ chủ động ném `IllegalStateException` kèm thông báo để không tiếp tục gọi constructor private.

Nếu thay bằng `constructor.setAccessible(true)`, khi module system từ chối nới quyền, lời gọi có thể ném:

~~~text
java.lang.reflect.InaccessibleObjectException
~~~

Đây là khác biệt giữa hai cách yêu cầu suppress access check:

| API | Khi quyền được phép | Khi module không cho phép |
|---|---|---|
| `trySetAccessible()` | Trả `true` và đặt flag accessible khi phù hợp | Trả `false` nếu không thể nới quyền |
| `setAccessible(true)` | Đặt flag accessible khi được phép | Có thể ném `InaccessibleObjectException` |
| `canAccess(receiver)` | Kiểm tra khả năng truy cập hiện thời từ caller | Trả `false` nếu caller chưa có quyền với member phù hợp |

`canAccess` cần truyền receiver phù hợp khi kiểm tra instance field/method; dùng `null` cho static member và constructor theo hợp đồng API. Không nên viết `trySetAccessible()` rồi bỏ qua giá trị trả về để thực hiện lời gọi như thể đã có quyền.

Khôi phục directive `opens demo.domain.internal to demo.inspector;` sau thử nghiệm để quay lại trường hợp thành công.

## 6. Cách chứng minh giới hạn đúng bên nhận

Giả sử ứng dụng có thêm named module `demo.audit` muốn kiểm tra `InternalConfig`. Nếu module domain chỉ ghi:

~~~java
module demo.domain {
    opens demo.domain.internal to demo.inspector;
}
~~~

thì deep reflection từ `demo.audit` không tự được cấp phép bởi khai báo dành cho `demo.inspector`.

Muốn cho phép cả hai, người sở hữu module cần quyết định mở rộng cụ thể:

~~~java
module demo.domain {
    opens demo.domain.internal to demo.inspector, demo.audit;
}
~~~

Đây là thay đổi quyền có chủ đích trên **module descriptor**. Việc hai module cùng `requires demo.domain` chỉ thể hiện quan hệ phụ thuộc, không khiến cả hai được phép deep reflection trên mọi package của domain.

Nếu không muốn cấp quyền cho `demo.audit`, giữ nguyên qualified opens ban đầu. Module sở hữu kiểm soát tập module được mở, không phụ thuộc vào thứ tự chạy của các framework hoặc thứ tự classpath.

### Những gì qualified opens không thể giới hạn

- **Không giới hạn đến một field hoặc một method.** Cấp quyền theo package; caller được phép có thể truy cập sâu những member thuộc package đó theo cơ chế reflection.
- **Không tự mở package con.** `demo.domain.internal.extra` vẫn là package riêng.
- **Không phân biệt từng class cùng một named module nhận quyền.** Khi một module được chỉ định, code thuộc module đó có thể sử dụng quyền phù hợp với phạm vi đã mở.
- **Không tạo hàng rào bảo mật tuyệt đối.** Người kiểm soát cách khởi động JVM hoặc thay đổi module graph có thể có những quyền vận hành khác; `opens` là cơ chế encapsulation và điều phối quyền truy cập của module system, không phải sandbox cho mã không đáng tin.

Để giảm phạm vi truy cập, nên thiết kế package dành riêng cho dữ liệu/framework cần reflection thay vì tập trung cả lớp quan trọng lẫn lớp không liên quan trong một package quá rộng.

## 7. Tích hợp framework: xác định module name trước khi cấu hình

Framework serialization, dependency injection, ORM hoặc kiểm thử đôi khi cần truy cập constructor/field không public. Khi framework hoạt động dưới dạng **named module**, có thể mở đúng package cho tên module của framework.

Ví dụ module ứng dụng có package `example.order.model` và framework chạy trong named module `example.mapper`:

~~~java
module example.order {
    opens example.order.model to example.mapper;
}
~~~

Đây là **tên module minh họa**. Khi làm việc với thư viện thực tế, cần xác định tên module từ `module-info.class` của JAR hoặc cấu hình module chính thức của thư viện; không tự thay `example.mapper` bằng tên Maven artifact rồi giả định sẽ chạy.

Một số trường hợp cần lưu ý:

| Bối cảnh | Hành động phù hợp |
|---|---|
| Framework là named module, package model là nơi duy nhất cần deep reflection | `opens model.package to framework.module;` |
| Nhiều named module thực sự cần truy cập | Liệt kê các tên module cần thiết sau `to` |
| Caller chỉ dùng public API, không cần đọc private state | Ưu tiên `exports` public API và lời gọi thông thường |
| Framework cần import public types ở compile time và cũng cần deep reflection | Xem xét `exports` và `opens` riêng theo từng nhu cầu |
| Framework hiện chạy trên classpath/unnamed module | Qualified `opens ... to ...` không thể chỉ đích danh unnamed module bằng tên module |
| Tên module đích đổi sau nâng cấp thư viện | Kiểm tra lại descriptor, packaging, runtime module path |

### Framework nằm trên classpath thì sao?

Một JAR được đưa lên **classpath** thông thường thuộc **unnamed module**. Vì unnamed module không có tên để ghi trong `opens ... to ...`, không thể viết một qualified directive trong `module-info.java` với tên `ALL-UNNAMED` như thể đó là named module thông thường.

Nếu môi trường triển khai buộc framework nằm trên classpath và module domain vẫn là named module, tùy chọn Java launcher được hỗ trợ có thể mở package cho các unnamed modules ở runtime:

~~~shell
java --module-path out --add-opens demo.domain/demo.domain.internal=ALL-UNNAMED ...
~~~

Dấu `...` ở cuối chỉ biểu thị các tham số khởi chạy ứng dụng thực tế; **không phải** lệnh đầy đủ để chạy ví dụ hai named module trong mục 4. `ALL-UNNAMED` ở đây là đích đặc biệt của **tùy chọn launcher** `--add-opens`; nó không phải tên named module trong `module-info.java`. Quyền cấp cho mọi unnamed module rộng hơn việc chỉ định một named module cụ thể.

Khi có thể chủ động cấu trúc hệ thống, dùng các named module và qualified opens trong descriptor giúp chính sách quyền dễ đánh giá hơn. `--add-opens` là cơ chế runtime chính thức khi cần cấu hình bổ sung trong môi trường triển khai, nhưng nên giới hạn đúng module/package/đích và ghi lại trong cấu hình chạy.

## 8. `Module.isOpen` và kiểm tra runtime có ý nghĩa gì?

API `java.lang.Module` giúp ứng dụng quan sát trạng thái module:

~~~java
Module owner = type.getModule();
Module caller = Main.class.getModule();

String pkg = type.getPackageName();
boolean allowed = owner.isOpen(pkg, caller);
System.out.println("Package open to caller: " + allowed);
~~~

Trong ví dụ này, cả `type` và `Main` đều là biến/kiểu đã được giới thiệu ở mục 4. `Module.isOpen(String, Module)` trả về kết quả về **mối quan hệ mở package** cho module được chỉ định. Dùng API này để xác định vấn đề cấu hình package/module, nhưng đừng coi đây là thay thế cho kiểm tra truy cập trên thành viên cụ thể.

Ví dụ:

- `isOpen` có thể cho biết package được mở cho caller nhưng thao tác vẫn thất bại vì sai chữ ký constructor/method.
- `trySetAccessible` có thể thành công nhưng `Method.invoke` vẫn ném `IllegalArgumentException` do receiver hoặc tham số không đúng.
- `InvocationTargetException` sau khi `Method.invoke` cho biết code đích đã ném exception; không nên nhầm với lỗi mở package.
- Việc class/module được tìm thấy không có nghĩa member mặc nhiên được nới quyền truy cập.

Khi cần trace thực tế, ghi lại **module sở hữu**, **module caller**, **package**, **member signature** và **exception/cause**, tránh log giá trị private field hoặc dữ liệu nhạy cảm.

## 9. Phân biệt lỗi module với lỗi reflection thông thường

| Triệu chứng | Khả năng nguyên nhân | Cách kiểm chứng |
|---|---|---|
| `ClassNotFoundException` tại `Class.forName` | Tên binary sai, module chưa được resolve hoặc class loader không tìm được lớp | Kiểm tra tên package/class, module graph và cách chạy `--module-path` |
| `NoSuchMethodException` khi tìm constructor/method | Sai kiểu tham số, tên member hoặc nhầm public/declared | Dùng đúng `getDeclaredConstructor`, `getDeclaredMethod` và chữ ký chính xác |
| `NoSuchFieldException` | Field không được khai báo ở lớp đang tra cứu, hoặc sai tên | Kiểm tra `getDeclaredField` đối với lớp khai báo |
| `trySetAccessible()` trả `false` | Package không mở phù hợp cho caller, hoặc quyền truy cập không thể nới | Kiểm tra `Module.isOpen`, `module-info.java` và tên module thực tế |
| `InaccessibleObjectException` tại `setAccessible(true)` | JPMS từ chối nới quyền deep reflection | Mở đúng package cho đúng module, tránh mở toàn bộ module |
| `IllegalAccessException` tại `newInstance`, `invoke`, `get` | Caller không có quyền truy cập thực tế với member | Kiểm tra modifier, module, receiver và quyết định nới quyền |
| `IllegalArgumentException` tại `invoke` | Sai số lượng/kiểu đối số hoặc receiver | Kiểm tra `getParameterTypes()`, static/instance và luật conversion |
| `InvocationTargetException` | Code trong constructor hoặc method đích ném exception | Đọc `getCause()`, kiểm tra lỗi nghiệp vụ |
| Chạy trên classpath được, chuyển sang module path thì lỗi | Quy tắc encapsulation của named module thay đổi bối cảnh | Kiểm tra caller là named hay unnamed module, `requires`, `exports` và `opens` |
| Có `opens` nhưng sai đối tượng được cấp quyền | Tên target module không đúng tên runtime của thư viện | Xác minh module name, cấu hình module path và dependency |

### Không chọn giải pháp nới toàn bộ quyền trước khi xác định nguyên nhân

Chẳng hạn lỗi `NoSuchMethodException` do một constructor nhận `String` nhưng ta tìm bằng `Object.class` sẽ **không thể sửa** bằng `opens`. Tương tự, `InvocationTargetException` từ code đích không phải là lý do để mở thêm package.

Quy trình chẩn đoán hiệu quả:

1. Kiểm tra tên lớp, module của lớp và module của caller.
2. Xác minh kiểu member và **chữ ký chính xác**.
3. Kiểm tra package có mở cho caller hay không bằng `Module.isOpen`.
4. Gọi `trySetAccessible()` có kiểm tra kết quả khi thực sự cần deep reflection.
5. Gọi thành viên; phân loại lỗi do access, kiểu đối số hoặc exception từ code đích.
6. Chỉ sửa phạm vi `opens` khi nguyên nhân đúng là **quyền truy cập package**.

## 10. Lưu ý khi đóng gói, nâng cấp và kiểm thử

### 10.1. Named module là điều kiện để chỉ định đích bằng tên

Module name có thể đến từ descriptor `module-info.class` của JAR hoặc từ cách JAR được xử lý như một module trên module path. Không nên suy tên đích từ đường dẫn thư mục hay package. Trong demo, tên `demo.inspector` được khai báo tường minh, giúp qualified opens có mục tiêu rõ.

Nếu cùng một thư viện chạy theo hai chế độ classpath và module path, cần kiểm chứng riêng; tên module và quy tắc mở package không nhất thiết giống nhau.

### 10.2. Quyền mở là thuộc tính của package, không của tên file

Chuyển lớp sang package khác có thể làm thay đổi phạm vi mở dù tên class đơn giản không đổi. Khi refactor package hoặc tách module, phải xem lại `opens` và điều chỉnh theo package mới.

Nếu thay đổi cấu hình triển khai làm module được nhận quyền đổi tên, cần cập nhật qualifier. Không cần mở rộng sang `opens package;` chỉ vì module name ban đầu chưa đúng.

### 10.3. Tránh khởi tạo hoặc đọc dữ liệu thật khi chỉ xác minh quyền

Ví dụ ở mục 4 cố ý dùng dữ liệu giả `"ap-southeast"` để minh họa. Trong hệ thống thật, kiểm tra quyền bằng metadata và các đối tượng thử nghiệm riêng nếu có thể; không ghi ra log secret/private field trong môi trường production.

### 10.4. Cần phân biệt API được hỗ trợ với chi tiết triển khai

JEP 416 (Java 18) tái triển khai core reflection trên nền method handles, nhưng không thay thế quy tắc `opens` của JPMS. Không dựa vào `sun.*`, `jdk.internal.*`, giả định truy cập ngầm vào các package của JDK, hoặc cờ cấu hình lỗi thời. Khả năng sử dụng `Method.invoke` và `trySetAccessible` phải được đánh giá theo hợp đồng public API của JDK đang chạy.

### 10.5. Kiểm chứng bằng một JVM mới sau khi sửa module descriptor

Sau khi đổi `module-info.java`, phải biên dịch lại để tạo `module-info.class` mới và chạy lại ứng dụng. Quyền module của JVM đã chạy không tự cập nhật khi bạn sửa source hoặc thay file JAR trên đĩa. Để so sánh trường hợp cho phép và từ chối, hãy kiểm thử bằng các lần chạy JVM riêng.

## 11. Checklist trước khi đưa qualified opens vào sản phẩm

| Kiểm tra | Điều cần xác nhận |
|---|---|
| Module sở hữu | Đúng named module chứa package cần deep reflection |
| Tên package | Khớp **toàn bộ** tên package, kể cả các cấp lồng nhau |
| Module nhận quyền | Là tên named module thực tế của caller/framework |
| Nhu cầu | Caller thực sự cần deep reflection, không chỉ public API |
| Phạm vi | Chỉ mở các package cần thiết, tránh `open module` hoặc `opens p;` không cần thiết |
| Source/descriptor | `opens p to m;` nằm trong đúng `module-info.java` của module sở hữu |
| Module graph | Các module cần thiết được resolve khi khởi chạy |
| Runtime check | `owner.isOpen(packageName, callerModule)` cho kết quả kỳ vọng |
| Thành viên | `trySetAccessible()` được kiểm tra; receiver và chữ ký phù hợp |
| Kiểm thử trường hợp từ chối | Một module không được cấp quyền không thể mặc nhiên deep-reflect package |
| Build/đóng gói | `module-info.class` mới được đóng vào artifact khi thay descriptor |
| Nâng cấp | Kiểm tra lại tên module framework và phạm vi package sau thay đổi |

## 12. Câu hỏi và bài tập tự kiểm tra

1. Vì sao `getDeclaredField("region")` có thể trả metadata nhưng `Field.get` vẫn thất bại nếu module không mở package?
2. Với `opens demo.domain.internal to demo.inspector;`, module `demo.audit` có tự được quyền deep reflection không? Nếu muốn cấp quyền cho cả hai module, cần thay đổi khai báo thế nào?
3. `exports demo.domain.internal to demo.inspector;` có thay thế cho qualified `opens` khi cần gọi constructor private không? Giải thích.
4. Vì sao `opens demo.domain.internal` và `opens demo.domain.internal to demo.inspector` có phạm vi khác nhau?
5. Nếu class được chuyển từ `demo.domain.internal` sang `demo.domain.internal.extra`, directive cũ còn cấp quyền cho package mới không?
6. Module nào phải chứa directive `opens ... to ...`: module sở hữu class hay module framework gọi reflection?
7. Vì sao `requires demo.domain` trong module inspector không đủ để gọi một private constructor thuộc module domain?
8. Sự khác biệt giữa `trySetAccessible()` trả `false` và `setAccessible(true)` ném `InaccessibleObjectException` là gì?
9. Khi thư viện framework đang chạy trên classpath, vì sao không thể ghi tên `ALL-UNNAMED` sau `to` như một named module thông thường? Tùy chọn launcher hiện đại nào có thể dùng khi cần cấu hình runtime cho unnamed modules?
10. Nếu `Method.invoke` ném `InvocationTargetException`, có nên thêm `opens` ngay không? Hãy nêu phép kiểm tra cần làm trước.
11. Khi cấp qualified opens cho package model, có thể giới hạn cho đúng một trường `private String region` không? Cần thay đổi cách phân chia package nào nếu muốn thu hẹp quyền?
12. Hãy chạy demo ở mục 4, bỏ dòng `opens` và chạy lại để xác nhận `isOpen` cùng `trySetAccessible` thay đổi. Sau đó khôi phục directive.

**Ghi nhớ:** Qualified opens dùng cú pháp **`opens ten.package to ten.module;`** trong `module-info.java` của **module sở hữu**. Nó cho phép named module được chỉ định thực hiện deep reflection trên package ở runtime, vẫn giữ khả năng kiểm soát public API bằng `exports` độc lập. Để kiểm chứng chính xác, xác định đúng tên module/package, dùng `Module.isOpen` và kiểm tra kết quả `trySetAccessible`; việc đọc metadata không thay thế kiểm tra quyền trước khi gọi động.

## Tài liệu tham khảo chính thức

- [Java Language Specification, `7.7.2 — Module Declarations: `exports` và `opens`](https://docs.oracle.com/javase/specs/jls/se25/html/jls-7.html#jls-7.7.2).
- [Java SE 25: `Module` — `isOpen`, module relationships](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Module.html).
- [Java SE 25: `AccessibleObject` — `canAccess`, `trySetAccessible`, `setAccessible`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/AccessibleObject.html).
- [Java SE 25: `InaccessibleObjectException`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/InaccessibleObjectException.html).
- [Java SE 25: `java` launcher — `--add-opens`](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html).
- [OpenJDK JEP 416 — Reimplement Core Reflection with Method Handles](https://openjdk.org/jeps/416).
- [OpenJDK JEP 403 — Strongly Encapsulate JDK Internals](https://openjdk.org/jeps/403).

