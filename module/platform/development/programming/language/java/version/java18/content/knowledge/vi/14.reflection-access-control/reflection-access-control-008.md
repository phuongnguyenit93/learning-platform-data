# Named module, unnamed module và cấu hình package mở có chủ đích

## Mục tiêu bài học

Trong Java hiện đại, việc tìm được một `Field` hoặc `Method` bằng Core Reflection **không đồng nghĩa** với việc được đọc, ghi hoặc gọi member đó. Ngoài mức truy cập `public`, `protected`, package-private và `private`, Java Platform Module System (JPMS) còn xác định package nào được **export** để sử dụng API công khai và package nào được **open** để thực hiện *deep reflection*.

Bài học thuộc chương **Quyền reflection** của module `JAVA_VERSION_JAVA18`. Module tìm hiểu những thay đổi từ Java 18 vẫn hữu ích trên JDK hiện đại, gồm UTF-8 mặc định, Simple Web Server, Javadoc snippets, phân giải tên, Reflection và MethodHandle. Trong phạm vi bài này, ta dùng hợp đồng JPMS/Core Reflection hiện hành, không dùng thủ thuật đột nhập nội bộ JDK hoặc cơ chế nới lỏng truy cập đã lỗi thời. JEP 416 của Java 18 đã thay đổi cách triển khai Core Reflection dựa trên method handles nhưng không loại bỏ các quy tắc module-access công khai được giải thích dưới đây.

Sau bài học, bạn có thể:

- Phân biệt **named module**, **unnamed module** và **automatic module**.
- Giải thích vai trò của `requires`, `exports`, `opens` và `open module` trong các tầng truy cập.
- Phân biệt quyền gọi public API với quyền truy cập private member qua reflection.
- Cấu hình `opens package to named.module` theo nguyên tắc cấp quyền tối thiểu.
- Dùng `--add-opens source.module/package=target.module` và `ALL-UNNAMED` một cách có chủ đích khi cần.
- Kiểm tra module và trạng thái mở package bằng `Class.getModule()`, `Module.isNamed()` và `Module.isOpen()`.
- Phân biệt `canAccess`, `trySetAccessible`, `setAccessible`, `IllegalAccessException` và `InaccessibleObjectException`.
- Tự biên dịch một ví dụ hai named modules và so sánh kết quả trước/sau khi mở package.

## 1. Module là đơn vị đóng gói quyền truy cập

Một lớp Java ở runtime thuộc về một đối tượng `java.lang.Module`. Có thể hỏi trực tiếp:

~~~java
Module module = String.class.getModule();
System.out.println(module.getName());  // java.base
System.out.println(module.isNamed());  // true
~~~

`java.base` là **named module** của JDK. Nếu một class ứng dụng được biên dịch và chạy theo **class path** theo cách thông thường, class đó thường thuộc **unnamed module** của class loader tương ứng:

~~~java
Module ownModule = MyMain.class.getModule();
System.out.println(ownModule.isNamed()); // false, nếu MyMain nằm trên class path
System.out.println(ownModule.getName()); // null, nếu là unnamed module
~~~

Không có nghĩa tất cả code trên classpath luôn chia sẻ đúng một `Module` trên mọi class loader: có thể có nhiều unnamed modules, mỗi class loader có thể định nghĩa một unnamed module. Cũng không được nhầm **unnamed module** với **unnamed package**: một class nằm trong package có tên vẫn có thể thuộc unnamed module.

### 1.1. Ba nhóm thường gặp

| Loại module | Cách thường xuất hiện | Đặc điểm đối với package |
| --- | --- | --- |
| Named module tường minh | Có `module-info.java` hoặc descriptor tương ứng trên module path | Quyền truy cập phụ thuộc các `exports` và `opens` được khai báo hoặc cấu hình bổ sung |
| Unnamed module | Code trên class path, không được gán tên JPMS | Mọi package của module được export và open; tương thích tốt với code không modular |
| Automatic module | JAR không có `module-info.class` được xử lý như module tự động trên module path | **Có tên module**, nhưng mọi package được export và open để hỗ trợ chuyển đổi dần sang JPMS |

Automatic module **không phải** unnamed module. `Module.isNamed()` trả `true` cho automatic module, mặc dù khả năng export/open rộng hơn một named module tường minh được đóng gói chặt.

### 1.2. Readability và visibility không giống nhau

Trong `module-info.java`:

~~~java
module demo.inspector {
    requires demo.domain;
}
~~~

`requires demo.domain` làm module `demo.inspector` **đọc được** module `demo.domain` theo graph phụ thuộc. Nhưng nó **không** tự cấp quyền truy cập tất cả package/class/member của `demo.domain`.

Tầng truy cập còn phụ thuộc package có được export/open cho module đang gọi hay không và member có mức truy cập nào. Với Core Reflection, đặc tả `AccessibleObject` có một điểm tinh tế: khi kiểm tra quyền phản chiếu của member, các phép kiểm tra ngôn ngữ Java được thực hiện với giả định readability, chứ không đơn giản áp dụng toàn bộ quy tắc `requires` của phép liên kết thông thường. Điều này **không** có nghĩa là `requires` hay khả năng resolve module có thể bị bỏ qua khi biên dịch/chạy một ứng dụng modular.

## 2. `exports` khác `opens` như thế nào?

Hãy xem module cung cấp domain object:

~~~java
module demo.domain {
    exports demo.api;
    opens demo.model to demo.inspector;
}
~~~

Hai chỉ thị này phục vụ hai mục đích khác nhau.

### 2.1. `exports`: cung cấp public API

~~~java
exports demo.api;
~~~

Code trong module khác có thể tham chiếu các kiểu `public` của `demo.api` bằng tên ở compile time, nếu các yêu cầu về module readability được đáp ứng. Các thành viên `public` được truy cập theo quy tắc Java, gồm cả qua reflection thông thường.

Tuy nhiên, **export package không cấp quyền deep reflection vào private field/private method** của các class trong package đó cho caller ở module khác. Nếu bạn có một `private String token` trong public class của package chỉ được export, `Field.trySetAccessible()` từ module khác thường không thể bật bypass chỉ dựa trên `exports`.

### 2.2. `opens`: cho phép deep reflection lúc chạy

~~~java
opens demo.model to demo.inspector;
~~~

Cấu hình này cho phép module `demo.inspector` thực hiện deep reflection vào các class/member trong package `demo.model`, theo hợp đồng `AccessibleObject`. Nó **không** biến các class trong package thành API có thể import bình thường từ module `demo.inspector` ở compile time.

Dạng không chỉ định đích:

~~~java
opens demo.model;
~~~

mở package đó cho **mọi module**. Dạng có `to`:

~~~java
opens demo.model to demo.inspector;
~~~

chỉ mở cho module được nêu tên (có thể liệt kê nhiều tên, phân tách bằng dấu phẩy). Khi biết rõ framework hoặc tool nào cần deep reflection, ưu tiên dạng **qualified opens** để hạn chế phạm vi.

### 2.3. Bảng quyết định

| Cấu hình package `demo.model` | Import public type từ module khác | Deep reflection vào private member từ module khác |
| --- | --- | --- |
| Không export, không open | Không | Không |
| `exports demo.model;` | Có, nếu module dependency phù hợp | Không chỉ vì export |
| `exports demo.model to demo.client;` | Chỉ những module được nêu tên | Không chỉ vì export |
| `opens demo.model;` | Không chỉ nhờ `opens` ở compile time | Có, khi tuân thủ hợp đồng Reflection |
| `opens demo.model to demo.inspector;` | Không chỉ nhờ `opens` ở compile time | Có cho `demo.inspector` |
| Vừa `exports` vừa `opens` | Public API truy cập được theo export | Deep reflection theo đối tượng được mở |

**Lưu ý:** `opens` cũng ảnh hưởng quyền truy cập reflective vào public types ở runtime. Bảng này nhấn mạnh sự khác biệt quan trọng nhất giữa *compile-time public API* và *deep reflection*. Không nên diễn giải “không export” thành “không bao giờ có thể truy cập bằng reflection”: một package được open có thể được phản chiếu dù không được export.

### 2.4. `open module` mở rộng hơn từng `opens`

Có thể viết:

~~~java
open module demo.domain {
    exports demo.api;
}
~~~

Khi đó **mọi package** trong module được mở cho deep reflection. Đây là lựa chọn rộng hơn rất nhiều so với `opens demo.model to demo.inspector`. Trong `open module`, không được khai báo thêm chỉ thị `opens` riêng: ngữ pháp module cấm điều đó.

`open module` hữu ích cho những module được thiết kế cố ý để framework reflective truy cập rộng, nhưng không phải thiết lập mặc định tốt cho thư viện muốn encapsulation rõ ràng.

## 3. Các API kiểm tra quyền hiện hành

Các API công khai giúp kiểm tra mà không phải dựa vào trường nội bộ của JDK:

~~~java
Class<?> type = ...;
Module owner = type.getModule();
Module caller = Inspector.class.getModule();

System.out.println(owner.isNamed());
System.out.println(owner.getName());
System.out.println(owner.isOpen(type.getPackageName(), caller));
System.out.println(owner.isExported(type.getPackageName(), caller));
~~~

### 3.1. `Module.isOpen(package, target)` và `Module.isOpen(package)`

- `isOpen(package, target)` trả lời liệu package có mở ít nhất cho module `target` hay không.
- `isOpen(package)` chỉ kiểm tra việc mở **không giới hạn đích**.
- `opens demo.model to demo.inspector` có thể khiến `isOpen("demo.model", inspectorModule)` trả `true`, trong khi `isOpen("demo.model")` trả `false`.
- Với unnamed module, các package được mở rộng cho mọi module; các phương thức `isOpen` tương ứng trả `true`.
- `isOpen` không kiểm tra target có đọc được owner module hay không.

Vì vậy, không dùng duy nhất `owner.isOpen(package)` để kết luận một named caller có được cấp quyền qualified opens hay chưa.

### 3.2. `canAccess`, `trySetAccessible`, `setAccessible`

~~~java
Field field = target.getClass().getDeclaredField("note");

System.out.println(field.canAccess(target)); // quyền dùng hiện tại của caller
boolean enabled = field.trySetAccessible();   // cố bật bypass nếu hợp đồng cho phép
if (enabled) {
    System.out.println(field.get(target));
}
~~~

| API | Vai trò | Khi thất bại |
| --- | --- | --- |
| `AccessibleObject.canAccess(receiver)` | Kiểm tra caller hiện tại có thể dùng reflected member này không | Trả `false` nếu không truy cập được; ném `IllegalArgumentException` nếu receiver không hợp lệ |
| `trySetAccessible()` | Cố bật cờ bỏ qua kiểm tra Java language access | Trả `false` nếu không thể bật do giới hạn access/module |
| `setAccessible(true)` | Yêu cầu bật cùng cơ chế, không tự động được phép | Ném `InaccessibleObjectException` nếu không thể bật |
| `Field.get(receiver)` hoặc `Method.invoke(receiver, ...)` | Thực hiện hành động phản chiếu | Có thể ném `IllegalAccessException` nếu không đủ quyền và chưa bật bypass |

Một vài điểm tinh tế:

1. `getDeclaredField()` có thể tìm được metadata của private field, nhưng tìm được không đồng nghĩa có quyền đọc nó.
2. `trySetAccessible()` thay đổi cờ truy cập của **reflected object** (nếu được phép), không đổi `private` thành `public` trong source, cũng không sửa module-info.
3. Một package được open cho module caller **cho phép** bật bypass; nó không khiến mọi private field đột nhiên vượt qua kiểm tra access trước khi gọi `trySetAccessible()`.
4. Với instance field/method, `canAccess(receiver)` cần receiver phù hợp. Với static field/method hoặc constructor, phải truyền `null`.
5. `AccessibleObject.isAccessible()` là API deprecated vì tên dễ gây hiểu nhầm: nó phản ánh cờ bypass, **không** phải phép kiểm tra quyền truy cập của caller. Trên JDK hiện đại nên dùng `canAccess` và `trySetAccessible`.

## 4. Ví dụ hoàn chỉnh: hai named modules, mở đúng package cho đúng caller

Ví dụ có hai module:

- `demo.domain` cung cấp public factory ở package `demo.api` và giữ class chứa dữ liệu trong package `demo.model`.
- `demo.inspector` dùng public factory để nhận object, sau đó đọc private field qua reflection.

Chúng ta **không export package `demo.model`**. Thay vào đó, package ấy được **open có điều kiện** cho module inspector.

### 4.1. Cấu trúc nguồn

~~~text
src/
├── demo.domain/
│   ├── module-info.java
│   └── demo/
│       ├── api/
│       │   └── CustomerFactory.java
│       └── model/
│           └── Customer.java
└── demo.inspector/
    ├── module-info.java
    └── demo/
        └── inspector/
            └── InspectMain.java
~~~

### 4.2. Module cung cấp dữ liệu

`src/demo.domain/module-info.java`:

~~~java
module demo.domain {
    exports demo.api;
    opens demo.model to demo.inspector;
}
~~~

`src/demo.domain/demo/model/Customer.java`:

~~~java
package demo.model;

public final class Customer {
    private final String note;

    public Customer(String note) {
        this.note = note;
    }
}
~~~

`src/demo.domain/demo/api/CustomerFactory.java`:

~~~java
package demo.api;

import demo.model.Customer;

public final class CustomerFactory {
    private CustomerFactory() {
    }

    public static Object create() {
        return new Customer("example-only");
    }
}
~~~

Lưu ý: `demo.api` được export, nên module inspector có thể `import demo.api.CustomerFactory`. `demo.model` không export, do đó module inspector không thể import `demo.model.Customer` làm dependency thông thường, dù class `Customer` được khai báo `public`.

Factory trả `Object` để code phía ngoài không cần gọi tên `Customer`. Đối tượng thật vẫn có thể được kiểm tra bằng `getClass()`.

### 4.3. Module kiểm tra reflection

`src/demo.inspector/module-info.java`:

~~~java
module demo.inspector {
    requires demo.domain;
}
~~~

`src/demo.inspector/demo/inspector/InspectMain.java`:

~~~java
package demo.inspector;

import demo.api.CustomerFactory;
import java.lang.reflect.Field;

public final class InspectMain {

    public static void main(String[] args)
            throws ReflectiveOperationException {

        Object customer = CustomerFactory.create();
        Class<?> type = customer.getClass();

        Module owner = type.getModule();
        Module caller = InspectMain.class.getModule();

        System.out.println("owner: " + owner.getName());
        System.out.println("caller: " + caller.getName());
        System.out.println("named: " + owner.isNamed());
        System.out.println("open to caller: "
                + owner.isOpen("demo.model", caller));
        System.out.println("open to all: "
                + owner.isOpen("demo.model"));

        Field note = type.getDeclaredField("note");

        System.out.println("canAccess before: "
                + note.canAccess(customer));

        boolean enabled = note.trySetAccessible();
        System.out.println("trySetAccessible: " + enabled);

        System.out.println("canAccess after: "
                + note.canAccess(customer));

        if (enabled) {
            System.out.println("note: " + note.get(customer));
        }
    }
}
~~~

### 4.4. Biên dịch và chạy

Từ thư mục chứa `src/`:

~~~bash
javac --module-source-path src -d mods -m demo.domain,demo.inspector
java --module-path mods -m demo.inspector/demo.inspector.InspectMain
~~~

Kết quả dự kiến:

~~~text
owner: demo.domain
caller: demo.inspector
named: true
open to caller: true
open to all: false
canAccess before: false
trySetAccessible: true
canAccess after: true
note: example-only
~~~

Giải thích:

1. `owner.isNamed()` đúng vì `Customer` thuộc named module `demo.domain`.
2. `isOpen("demo.model", caller)` đúng vì package được mở cho `demo.inspector`.
3. `isOpen("demo.model")` sai vì package **không** mở không điều kiện cho mọi module.
4. `Field.getDeclaredField("note")` tìm được metadata của field private.
5. `canAccess(customer)` ban đầu sai vì member vẫn `private` và chưa bật cờ bypass.
6. `trySetAccessible()` thành công nhờ qualified opens.
7. Sau khi bật cờ, `Field.get(customer)` đọc được dữ liệu ví dụ.

**Điểm cần nhớ:** mở package không tự thay đổi modifier của member. Nó cho phép caller dùng API hỗ trợ bypass khi thật sự cần và được phép.

### 4.5. Bỏ `opens` để quan sát lỗi

Thử đổi descriptor của `demo.domain` thành:

~~~java
module demo.domain {
    exports demo.api;
    // Không opens demo.model.
}
~~~

Biên dịch và chạy lại hai lệnh ở mục 4.4. Kết quả quan trọng sẽ đổi:

~~~text
open to caller: false
open to all: false
canAccess before: false
trySetAccessible: false
canAccess after: false
~~~

Không có dòng `note: example-only` do ví dụ kiểm tra `enabled` trước khi đọc field. Nếu thay `trySetAccessible()` bằng `setAccessible(true)` trong tình huống này, lệnh có thể ném `InaccessibleObjectException`. Nếu thử `note.get(customer)` khi chưa được phép bypass, có thể nhận `IllegalAccessException`.

Lỗi không nằm ở `getDeclaredField()`; metadata vẫn có thể được tìm thấy. Điều bị từ chối là **deep access** từ module khác vào package chưa mở.

## 5. Cấu hình `--add-opens` khi chưa thể sửa module-info

Đôi khi bạn sở hữu một tool, một framework hoặc cấu hình triển khai nhưng không thể sửa `module-info.java` của module cung cấp dữ liệu. Java launcher có tùy chọn:

~~~text
--add-opens source.module/package=target.module
~~~

Ví dụ, sau khi bỏ chỉ thị `opens` khỏi `demo.domain`, có thể cho phép inspector của chúng ta bằng runtime option:

~~~bash
java --module-path mods --add-opens demo.domain/demo.model=demo.inspector -m demo.inspector/demo.inspector.InspectMain
~~~

Khi đó package `demo.model` được mở thêm cho `demo.inspector` **trong lần chạy này**, dù không có chỉ thị `opens` trong module-info.

### 5.1. Mở cho code trên class path

`ALL-UNNAMED` là giá trị đặc biệt chỉ **tất cả các unnamed modules**, thường gồm code chạy trên class path:

~~~bash
java --add-opens demo.domain/demo.model=ALL-UNNAMED ...
~~~

Giá trị này **không** có nghĩa “mọi module”: một tool chạy trong named module `demo.inspector` không được phép deep reflection chỉ vì bạn đã mở cho `ALL-UNNAMED`.

Nếu chỉ một named module cần quyền, cấu hình chính xác tên đó:

~~~text
--add-opens demo.domain/demo.model=demo.inspector
~~~

Nếu cả framework có tên và thư viện classpath cần quyền, có thể cấu hình các target cần thiết. Tuy nhiên, hãy coi mọi khoản mở quyền là một quyết định thiết kế và bảo trì, không phải mẹo để bỏ qua vấn đề phân quyền.

### 5.2. Phân biệt ba option hay bị nhầm

| Cơ chế | Cấp quyền gì? | Có giải quyết deep reflection vào private field không? |
| --- | --- | --- |
| `requires demo.domain;` | Quan hệ đọc module, phục vụ phụ thuộc Java module | Không |
| `--add-exports demo.domain/demo.model=demo.inspector` | Cho module đích dùng các public type/member của package theo điều kiện truy cập | Không chỉ nhờ export |
| `--add-opens demo.domain/demo.model=demo.inspector` | Mở package cho reflective access của module đích | Có thể cho phép `trySetAccessible()` vào private member theo hợp đồng |

`--add-exports` không phải từ đồng nghĩa của `--add-opens`. Nếu lỗi là `InaccessibleObjectException` khi cố mở private member trong package thuộc named module, **bổ sung export không giải quyết bản chất thiếu quyền deep reflection**.

### 5.3. Không quay lại cơ chế đã lỗi thời

Trên JDK hiện đại, không dựa vào `--illegal-access` để mở hàng loạt internal JDK packages: tùy chọn này đã trở nên lỗi thời và không còn là công cụ nới lỏng truy cập hữu hiệu. Nếu một dependency vẫn yêu cầu phản chiếu sâu vào JDK internals, hãy ưu tiên nâng cấp nó để dùng public API; chỉ dùng `--add-opens` ở mức package cụ thể nếu có lý do tương thích rõ ràng và hiểu rủi ro.

Cũng không nên mở bừa các package nội bộ JDK chỉ vì một test thất bại. Bài học tập trung vào package ứng dụng của chính bạn, với quyền truy cập được cấp có chủ đích.

## 6. Unnamed module: dễ phản chiếu vào chính package của mình nhưng không phá được mọi named module

Để thấy unnamed module hoạt động thế nào, tạo ví dụ riêng trên class path.

`src-plain/demo/classpath/ClassPathMain.java`:

~~~java
package demo.classpath;

import java.lang.reflect.Field;

public final class ClassPathMain {
    public static void main(String[] args) throws Exception {
        PlainBox box = new PlainBox();
        Module owner = PlainBox.class.getModule();

        System.out.println("module named: " + owner.isNamed());
        System.out.println("module name: " + owner.getName());
        System.out.println("package open: "
                + owner.isOpen("demo.classpath"));

        Field note = PlainBox.class.getDeclaredField("note");
        System.out.println("before: " + note.canAccess(box));
        System.out.println("enabled: " + note.trySetAccessible());
        System.out.println("after: " + note.canAccess(box));
        System.out.println("note: " + note.get(box));
    }
}

final class PlainBox {
    private final String note = "sample";
}
~~~

Biên dịch và chạy theo class path:

~~~bash
javac -d out src-plain/demo/classpath/ClassPathMain.java
java -cp out demo.classpath.ClassPathMain
~~~

Kết quả dự kiến:

~~~text
module named: false
module name: null
package open: true
before: false
enabled: true
after: true
note: sample
~~~

Giải thích:

- `PlainBox` thuộc unnamed module vì được chạy trên class path.
- Unnamed module export và open các package của nó cho mọi module. Trong ví dụ này, caller còn nằm cùng unnamed module nên `trySetAccessible()` có thể thành công.
- Field `note` vẫn là `private`. Nó chỉ được đọc sau khi bật bypass.
- Khi code trên class path cố deep reflection **vào một named module khác**, quyền truy cập lại phụ thuộc **module sở hữu target** có mở package cho unnamed caller hay không.

Ví dụ này không chứng minh rằng “classpath luôn được phép đọc mọi field trong JDK hoặc mọi named module”. Nó chỉ minh họa các quy tắc áp dụng cho package **nằm trong unnamed module**.

## 7. Kiểm chứng `ALL-UNNAMED` bằng caller trên class path

Từ ví dụ hai named modules ở mục 4, giữ `demo.domain` với descriptor:

~~~java
module demo.domain {
    exports demo.api;
    opens demo.model to demo.inspector;
}
~~~

Lúc này `demo.model` chỉ mở cho **named module `demo.inspector`**, không mở cho tất cả code classpath.

Tạo một chương trình thứ ba ở **unnamed module** có thể gọi public factory nhưng muốn phản chiếu private field.

`src-plain/demo/classpath/ClasspathInspect.java`:

~~~java
package demo.classpath;

import demo.api.CustomerFactory;
import java.lang.reflect.Field;

public final class ClasspathInspect {

    public static void main(String[] args)
            throws ReflectiveOperationException {

        Object customer = CustomerFactory.create();
        Class<?> type = customer.getClass();

        Module owner = type.getModule();
        Module caller = ClasspathInspect.class.getModule();

        System.out.println("caller named: " + caller.isNamed());
        System.out.println("owner open to caller: "
                + owner.isOpen("demo.model", caller));

        Field note = type.getDeclaredField("note");
        boolean enabled = note.trySetAccessible();
        System.out.println("enabled: " + enabled);

        if (enabled) {
            System.out.println("note: " + note.get(customer));
        }
    }
}
~~~

### 7.1. Biên dịch classpath caller

Giả sử module `demo.domain` đã được biên dịch vào `mods/demo.domain` như mục 4:

~~~bash
javac --module-path mods --add-modules demo.domain -d out src-plain/demo/classpath/ClasspathInspect.java
~~~

`--add-modules demo.domain` bảo đảm module được đưa vào graph và public package `demo.api` sẵn dùng cho classpath caller.

### 7.2. Chạy khi chưa mở cho unnamed module

~~~bash
java --module-path mods --add-modules demo.domain -cp out demo.classpath.ClasspathInspect
~~~

Kết quả:

~~~text
caller named: false
owner open to caller: false
enabled: false
~~~

Dù `CustomerFactory` là public API được export, private member của `Customer` trong package `demo.model` vẫn chưa mở cho unnamed caller. Điều này thể hiện rằng **unnamed module mở các package của chính nó cho mọi module**, chứ không được tự ý deep-reflect vào mọi named module khác.

### 7.3. Chạy khi mở có chủ đích cho `ALL-UNNAMED`

~~~bash
java --module-path mods --add-modules demo.domain --add-opens demo.domain/demo.model=ALL-UNNAMED -cp out demo.classpath.ClasspathInspect
~~~

Kết quả:

~~~text
caller named: false
owner open to caller: true
enabled: true
note: example-only
~~~

Chỉ một package của `demo.domain` được mở thêm cho unnamed modules. Đây là điều khác hoàn toàn với việc biến `demo.domain` thành `open module`, vì `open module` mở **mọi** package.

**Lưu ý về quyền rộng:** `ALL-UNNAMED` không chỉ định một JAR cụ thể. Nó bao gồm mọi unnamed module phù hợp trong quá trình thực thi, kể cả các thư viện classpath không phải tool dự định ban đầu. Khi có thể, chuyển tool cần deep reflection thành named module rồi dùng qualified opens tới chính module ấy.

## 8. Automatic module là named module, không phải unnamed module

Khi một JAR không có module descriptor được đưa vào **module path** theo cơ chế automatic module, JVM có thể xem nó là một **named module tự động**.

Đặc tính quan trọng:

- `Module.isNamed()` là `true`.
- Tên có thể lấy từ `Automatic-Module-Name` trong manifest hoặc được suy từ tên JAR theo quy tắc module path.
- Automatic module có thể được nhắc tên trong `requires` của module khác.
- Nó thường đọc các module khác trong configuration, bao gồm unnamed modules.
- Các package của automatic module được **export và open** rộng cho mục tiêu chuyển đổi dần sang JPMS.

Do đó:

| Đặc điểm | Unnamed module | Automatic module |
| --- | --- | --- |
| Có tên JPMS | Không | Có |
| `Module.isNamed()` | `false` | `true` |
| `Module.getName()` | `null` | Tên module |
| Package export/open | Mọi package | Mọi package |
| Có thể được nêu tên trong `requires` | Không | Có |
| Cấu hình `opens p to named.target` qua `module-info.java` | Không | Chỉ khi chuyển sang named module tường minh có descriptor |
| Phù hợp để áp dụng chính sách mở tối thiểu | Không theo `module-info` | Cần chuyển thành named module tường minh |

**Automatic module là bước chuyển tiếp**, không phải bằng chứng rằng thư viện đã được đóng gói chặt. Đặt một JAR thông thường lên module path có thể làm thay đổi module identity, dù các package vẫn được export/open rộng.

Có thể quan sát module identity:

~~~java
Module module = SomeLibraryClass.class.getModule();

System.out.println(module.isNamed());
System.out.println(module.getName());

if (module.getDescriptor() != null) {
    System.out.println(module.getDescriptor().isAutomatic());
}
~~~

Đối với unnamed module, `getDescriptor()` trả `null`; với named module tường minh, `isAutomatic()` trả `false`. Tên `SomeLibraryClass` ở đây là placeholder cho một class của thư viện thực tế, không phải class do JDK cung cấp.

## 9. Thiết kế cấu hình mở package theo nguyên tắc cấp quyền tối thiểu

Một ứng dụng có thể sử dụng Reflection trong nhiều tình huống: ORM đọc entity private field, dependency injection gọi constructor, serializer truy xuất property, test framework truy cập state, hoặc plugin manager đọc annotation. Không phải mọi tình huống đều cần deep reflection.

### 9.1. Hỏi trước khi mở

1. Framework cần truy cập **public API** hay **private/package-private member**?
2. Class đích thuộc module nào? Dùng `targetClass.getModule()` để kiểm tra, không đoán từ package name.
3. Caller thực hiện reflection đang nằm trong named, automatic hay unnamed module?
4. Có thể dùng public constructor, getter, factory, interface hoặc API có chủ đích thay cho private reflection không?
5. Nếu phải dùng deep reflection, **package nào** chứa member cần truy cập?
6. Có thể chỉ mở cho **một named module** bằng `opens package to framework.module` không?
7. Có cần cấp quyền trong source descriptor hay chỉ tạm thời qua launcher option?
8. Có kế hoạch kiểm tra lại và thu hẹp những `--add-opens` đang dùng không?

### 9.2. Những cấu hình thường thấy

| Nhu cầu | Lựa chọn ưu tiên | Tránh |
| --- | --- | --- |
| Công khai thư viện API | `exports demo.api;` | `opens` mọi package chỉ để expose public API |
| Framework có tên cần private field | `opens demo.model to framework.module;` | `opens demo.model;` nếu không cần mở cho mọi caller |
| Tool classpath cần deep reflection tạm thời | `--add-opens demo.domain/demo.model=ALL-UNNAMED` có kiểm soát | Mở nhiều package/JDK internals vô điều kiện |
| Chưa biết package nào cần reflection | Đo lỗi thực tế và xem tài liệu framework | Tự động chuyển cả module thành `open module` |
| Code cùng module đọc private member bằng reflection | `trySetAccessible()` sau khi đánh giá nhu cầu | Mở package ra ngoài module khi không cần |

### 9.3. `Module.addOpens` không phải “mở mọi module tùy ý”

`Module.addOpens(package, targetModule)` có thể cập nhật quyền mở package lúc runtime trong những điều kiện hợp lệ, nhưng nó không cho phép bất kỳ caller nào tự động mở package bí mật của một module khác theo ý mình. API này có hợp đồng kiểm tra caller và module sở hữu package.

Nếu bạn kiểm soát source của module cung cấp, `module-info.java` thường rõ ràng và dễ review nhất. Nếu một framework hỗ trợ cơ chế tự đăng ký/mở có kiểm soát, hãy đánh giá dựa trên API công khai và hợp đồng của framework, không dùng hành vi nội bộ không được tài liệu hóa.

### 9.4. Opens không cho phép mọi kiểu thao tác

Cấp quyền deep reflection **không đồng nghĩa** tất cả thao tác đều được phép:

- `Field.get` và `Field.set` còn phụ thuộc loại member, kiểu dữ liệu, receiver và các hạn chế riêng.
- Một số `final` field không thể được thay đổi bằng reflective write access ngay cả khi cờ bypass đã được bật; chính sách với final fields tiếp tục được tăng cường trong JDK hiện đại.
- `Method.invoke` có thể ném exception do method đích thực thi, hoặc báo lỗi đối số/receiver.
- `MethodHandles.privateLookupIn` liên quan đến khả năng mở package nhưng có điều kiện về `Lookup` và module khác, không phải một cách bỏ qua JPMS.

Ví dụ trong bài **chỉ đọc** một private field. Đây là kiểm chứng đủ rõ quyền open package mà không phải dựa vào thay đổi giá trị của final field.

## 10. Quy trình chẩn đoán lỗi Reflection theo từng bước

Khi gặp `InaccessibleObjectException` hoặc `IllegalAccessException`, đừng vội thêm `--add-opens` không giới hạn.

### Bước 1 — Xác định owner của member

~~~java
Class<?> targetType = target.getClass();
Module source = targetType.getModule();

System.out.println("module=" + source.getName());
System.out.println("package=" + targetType.getPackageName());
~~~

Nếu đang kiểm tra `Method`/`Field` thuộc lớp cha hoặc interface, dùng `member.getDeclaringClass()` để xác định **module chứa class khai báo member**, thay vì mặc định dùng module của receiver.

### Bước 2 — Xác định module thực sự đang gọi Reflection

~~~java
Module callingModule = InspectMain.class.getModule();
System.out.println("caller=" + callingModule.getName());
System.out.println("named=" + callingModule.isNamed());
~~~

Với framework, caller thực tế có thể là class trong thư viện framework, không phải lớp business code tạo instance. Hãy tìm **module của code gọi `trySetAccessible()`**, không tự suy từ class ứng dụng.

### Bước 3 — Kiểm tra package có open cho caller không

~~~java
Class<?> declaringClass = field.getDeclaringClass();
Module owner = declaringClass.getModule();
Module caller = InspectMain.class.getModule();

System.out.println(owner.isOpen(
        declaringClass.getPackageName(), caller));
~~~

Nếu kết quả `false` và bạn thực sự cần private access từ module khác, cân nhắc `opens package to caller.module` hoặc một `--add-opens` giới hạn đúng package/target.

### Bước 4 — Kiểm tra quyền trực tiếp và bypass

~~~java
boolean direct = field.canAccess(receiver);
boolean enabled = field.trySetAccessible();

System.out.println("direct=" + direct);
System.out.println("enabled=" + enabled);
~~~

Đừng gọi `field.get(receiver)` sau khi `enabled=false` nếu caller không có quyền trực tiếp. Phân nhánh xử lý hoặc báo lỗi cấu hình rõ ràng.

### Bước 5 — Phân loại lỗi chính xác

| Hiện tượng | Ý nghĩa thường gặp | Hướng xử lý |
| --- | --- | --- |
| `getDeclaredField` tìm thấy nhưng `canAccess` false | Metadata có thể đọc, hành động trực tiếp bị chặn | Xét modifier, receiver và module |
| `trySetAccessible` false | Không thể bật bypass theo quyền hiện tại | Kiểm tra package mở cho caller |
| `setAccessible(true)` ném `InaccessibleObjectException` | Yêu cầu bypass bị từ chối | Không thêm cờ ngẫu nhiên; xác định owner package/target |
| `Field.get` ném `IllegalAccessException` | Hành động truy cập member không được phép | Xét access và trạng thái bypass |
| `canAccess` ném `IllegalArgumentException` | Receiver không đúng loại hoặc dùng `null` sai | Instance member dùng đúng object; static/constructor dùng `null` |
| `NoSuchFieldException` | Không tìm thấy member được yêu cầu ở class được tra cứu | Kiểm tra tên, class khai báo, kế thừa và cách dùng `getDeclaredField` |
| Lỗi compile khi import class package unexported | Thiếu export hoặc dùng API nội bộ không phải public contract | Dùng public API có chủ đích, không đổi `opens` thay cho `exports` |

### Bước 6 — Kiểm tra hậu quả và giới hạn quyền

Sau khi thêm `opens` hoặc `--add-opens`, chạy lại test và xác nhận:

- Chỉ những module cần thiết được cấp quyền.
- Package nội bộ không bị export rộng hơn ngoài dự kiến.
- Code bình thường vẫn truy cập qua public API thay vì private reflection.
- Những lỗi khác như sai kiểu đối số hoặc thiếu member không bị che bởi cấu hình quyền.
- Với test framework hoặc serializer, testcase chạy trong đúng class loader và runtime module graph giống môi trường thực tế.

## 11. Những nhầm lẫn thường gặp

| Nhầm lẫn | Vì sao sai | Cách đúng |
| --- | --- | --- |
| “Có `requires` thì đọc được mọi private field của dependency.” | `requires` chỉ xác định quan hệ đọc module. | Kiểm tra quyền `opens` và `AccessibleObject`. |
| “`exports` và `opens` giống nhau.” | Export phục vụ public API; opens phục vụ reflective access lúc chạy. | Chọn đúng cơ chế theo nhu cầu. |
| “Package được export thì `setAccessible(true)` vào private member luôn thành công.” | Export không đủ để deep-reflect private member từ module khác. | Chỉ mở đúng package khi thực sự cần. |
| “`opens p to inspector` cũng mở cho mọi classpath code.” | Qualified opens chỉ cấp cho named module được nêu tên. | Dùng `ALL-UNNAMED` nếu caller là unnamed module và có lý do xác đáng. |
| “`ALL-UNNAMED` bao gồm cả mọi named module.” | Giá trị này chỉ nhắm unnamed modules. | Named caller phải được nêu đúng tên. |
| “Class thuộc package có tên thì chắc thuộc named module.” | Named package khác named module. | Dùng `Class.getModule().isNamed()`. |
| “Automatic module chính là unnamed module.” | Automatic module có tên và có thể được `requires`. | Kiểm tra descriptor và module identity. |
| “`Module.isOpen(p)` false nghĩa là không ai được deep-reflect.” | Một package có thể được mở có điều kiện cho module khác. | Dùng `isOpen(p, callerModule)`. |
| “`trySetAccessible()` thay private member thành public.” | Nó chỉ bật bypass trên reflected object nếu được phép. | Không coi đây là sửa modifier hoặc module descriptor. |
| “Tìm được `Field` nghĩa là đọc được giá trị.” | Metadata discovery và field access là hai bước khác nhau. | Kiểm tra `canAccess` và `trySetAccessible`. |
| “`--add-exports` chữa được mọi `InaccessibleObjectException`.” | Deep reflection cần quyền mở package, không chỉ public export. | Dùng `--add-opens` đúng package/target nếu cần. |
| “`open module` có thể khai báo thêm `opens p`.” | Ngữ pháp Java không cho phép `opens` bên trong `open module`. | Chọn một trong hai chiến lược. |
| “`--illegal-access` là giải pháp hiện đại để mở JDK internals.” | Tùy chọn đã lỗi thời và không nới lỏng quyền trên JDK hiện đại. | Nâng cấp dependency; chỉ dùng `--add-opens` có chủ đích khi cần. |
| “Opens nghĩa là có thể thay mọi `final` field.” | Quyền deep reflection và quyền reflective mutation khác nhau. | Không phụ thuộc reflective writes vào final fields. |

## 12. Bài tập tự đánh giá

### Bài 1 — Public API có cần opens không?

Module:

~~~java
module demo.lib {
    exports demo.api;
}
~~~

`demo.client` đã `requires demo.lib`, chỉ cần gọi public method của public class ở `demo.api`. Có cần thêm `opens demo.api`?

**Đáp án:** Không. Export đã phục vụ public API. Chỉ xét opens nếu phải thực hiện deep reflection vào member không public từ module khác.

### Bài 2 — Export đã đủ cho private reflection?

Package `demo.api` được export, nhưng `public class Service` có `private String key`. Caller ở module khác tìm được field bằng `getDeclaredField("key")`. Chỉ nhờ export, `trySetAccessible()` có chắc thành công không?

**Đáp án:** Không. Việc tìm thấy metadata không cấp quyền deep access. Package phải được mở cho caller (hoặc thỏa một điều kiện khác của hợp đồng `AccessibleObject`, chẳng hạn cùng module).

### Bài 3 — Qualified opens

~~~java
module demo.domain {
    opens demo.model to demo.inspector;
}
~~~

Giả sử `owner` là `demo.domain`, `inspector` là module `demo.inspector`, `other` là một named module khác:

~~~java
owner.isOpen("demo.model", inspector); // ?
owner.isOpen("demo.model", other);     // ?
owner.isOpen("demo.model");            // ?
~~~

**Đáp án:** Lần lượt `true`, `false`, `false`. Đó là qualified opens, không phải mở vô điều kiện.

### Bài 4 — Classpath caller

Một tool chạy từ classpath cần private reflection vào `demo.domain/demo.model`, nhưng package chỉ mở cho named `demo.inspector`. Tool có quyền tự động không?

**Đáp án:** Không. Nếu được phê duyệt, dùng runtime option:

~~~text
--add-opens demo.domain/demo.model=ALL-UNNAMED
~~~

`ALL-UNNAMED` rộng hơn việc cấp cho một named module duy nhất, nên cần ghi rõ lý do.

### Bài 5 — Automatic module

Một JAR không có `module-info.class` được xử lý như automatic module trên module path. `Module.isNamed()` trả gì? Package của nó có export/open rộng không?

**Đáp án:** `true` và có. Automatic module có tên, nhưng mọi package được export/open để hỗ trợ chuyển đổi dần sang JPMS.

### Bài 6 — Trước và sau bypass

Package `demo.model` được open cho `demo.inspector`. Field `Customer.note` là private. Trước khi dùng `trySetAccessible()`, `field.canAccess(customer)` từ inspector có phải chắc chắn `true` không?

**Đáp án:** Không. Trong ví dụ, `canAccess` ban đầu là `false`. `trySetAccessible()` thành công nhờ opens, sau đó mới có thể đọc field trên reflected object.

### Bài 7 — Hai ngoại lệ

Nêu hai trường hợp khác nhau:

1. `setAccessible(true)` không thể bật bypass vì JPMS.
2. `Field.get(receiver)` được gọi khi caller không đủ quyền và chưa bật bypass.

**Đáp án:** Trường hợp thứ nhất có thể ném `InaccessibleObjectException`; trường hợp thứ hai có thể ném `IllegalAccessException`.

### Bài 8 — Chọn cấu hình tối thiểu

Framework `demo.inspector` chỉ cần private access vào `demo.model`. Nên chọn cấu hình nào?

~~~java
open module demo.domain {
    exports demo.api;
}
~~~

hay:

~~~java
module demo.domain {
    exports demo.api;
    opens demo.model to demo.inspector;
}
~~~

**Đáp án:** Cấu hình thứ hai cấp quyền theo đúng package và target module. `open module` mở rộng tất cả package cho mọi module.

### Bài 9 — Module của class runtime hay member khai báo?

Object runtime thuộc subclass, nhưng private field được khai báo ở superclass. Để xác định module/package cần mở, dùng `receiver.getClass()` hay `field.getDeclaringClass()`?

**Đáp án:** Dùng `field.getDeclaringClass()` rồi lấy `getModule()` và `getPackageName()`. Quyền của field phụ thuộc lớp **khai báo member**, không phải mặc nhiên module của receiver.

### Bài 10 — Package mở rồi, mọi thao tác đều thành công?

`source.isOpen(packageName, caller)` trả `true`. Có thể khẳng định mọi `Method.invoke` và `Field.set` đều thành công không?

**Đáp án:** Không. Vẫn cần receiver/arguments hợp lệ, trạng thái bypass phù hợp nếu truy cập non-public member, cùng các điều kiện khác của member. Mở package cũng không bảo đảm có thể sửa final field.

## 13. Checklist trước khi mở package

- [ ] Đã xác định module của **class khai báo member**, không đoán từ class runtime.
- [ ] Đã biết caller gọi reflection nằm trong named, automatic hay unnamed module.
- [ ] Đã phân biệt nhu cầu public API (`exports`) và private reflection (`opens`).
- [ ] Đã ưu tiên public API, factory hoặc interface nếu có thể.
- [ ] Nếu cần opens, đã chọn **package cụ thể** và **target cụ thể**.
- [ ] Nếu dùng `ALL-UNNAMED`, đã hiểu phạm vi bao gồm nhiều thư viện trên classpath.
- [ ] Đã kiểm chứng bằng `Module.isOpen(package, caller)` và `trySetAccessible()`.
- [ ] Không dùng `isAccessible()` deprecated hay `--illegal-access` lỗi thời.
- [ ] Đã xác nhận các thao tác reflective vẫn tuân thủ giới hạn của member.
- [ ] Có phép thử khi được mở và khi bị từ chối.
- [ ] Nếu sử dụng `--add-opens`, đã ghi lại lý do, nơi cấu hình và thời điểm cần xem xét thu hẹp.

## Tổng kết

- **Named module** có chính sách export/open tường minh. **Unnamed module** export/open package của chính nó; **automatic module** có tên nhưng export/open các package rộng.
- `requires` tạo quan hệ đọc module; `exports` phục vụ public API; `opens` cho phép reflective access, gồm khả năng bật deep access khi thỏa hợp đồng.
- `opens p to target.module` giới hạn quyền theo caller. `opens p` mở cho mọi module; `open module` mở mọi package và không dùng thêm chỉ thị `opens`.
- `getDeclaredField` đọc metadata, `canAccess` kiểm tra quyền hiện tại, `trySetAccessible` thử bật bypass, còn `setAccessible(true)` có thể ném `InaccessibleObjectException` khi bị cấm.
- `Module.isOpen(package, caller)` là phép kiểm tra đúng cho qualified opens; `isOpen(package)` không thể hiện toàn bộ quyền dành riêng cho named callers.
- `--add-opens source/package=target` là cấu hình runtime hữu ích khi cần, nhưng `ALL-UNNAMED` không có nghĩa mọi named module.
- Không nhầm `--add-exports` với `--add-opens`, không dùng `--illegal-access` đã lỗi thời và không mở toàn module chỉ để xử lý một private field.
- Hãy ưu tiên API công khai, cấu hình mở package tối thiểu và kiểm tra trên đúng module graph/class loader của ứng dụng.
- Các hợp đồng JPMS/Core Reflection vẫn áp dụng trên JDK hiện đại; không cần dựa vào chi tiết triển khai Reflection cũ trước JEP 416.

## Nguồn tham khảo chính thức

1. [Oracle — Java Language Specification, Java SE 26, mục 7.7 Module Declarations](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-7.html#jls-7.7): named/unnamed modules, `requires`, `exports`, `opens` và `open module`.
2. [Oracle — AccessibleObject, Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/reflect/AccessibleObject.html): `canAccess`, `trySetAccessible`, `setAccessible` và quyền phản chiếu theo caller.
3. [Oracle — Module, Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Module.html): `isNamed`, `getName`, `isOpen`, `isExported` và `addOpens`.
4. [Oracle — ModuleDescriptor, Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/module/ModuleDescriptor.html): normal/open/automatic modules và các package được export/open.
5. [Oracle — Migrating from JDK 8 to Later JDK Releases, Java SE 26](https://docs.oracle.com/en/java/javase/26/migrate/migrating-from-jdk-8-later-jdk-releases.html): cách dùng `--add-opens` và `--add-exports` khi chuyển đổi ứng dụng.
6. [Oracle — The java Command, Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html): module path, `--add-modules` và launcher options.
7. [OpenJDK — JEP 403: Strongly Encapsulate JDK Internals](https://openjdk.org/jeps/403): strong encapsulation và việc loại bỏ cơ chế nới lỏng rộng đã lỗi thời.
8. [OpenJDK — JEP 416: Reimplement Core Reflection with Method Handles](https://openjdk.org/jeps/416): thay đổi triển khai Core Reflection trong Java 18, không làm mất hợp đồng API công khai.
