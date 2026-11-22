# Reflection access tới private member

Reflection cho phép chương trình kiểm tra class, field, method và constructor khi chạy. Trong nhiều tình huống, framework cần đọc hoặc gọi member không public để thực hiện dependency injection, ánh xạ object, serialization hay binding dữ liệu.

Từ Java 9, JPMS đặt các module vào những boundary rõ ràng. Vì vậy, việc một class có private field không còn là chuyện chỉ phụ thuộc vào `setAccessible(true)`: module sở hữu package phải cho phép module gọi reflection truy cập sâu vào package đó.

Cần phân biệt hai quyền:

- **Java access control:** `private`, package-private, `protected`, `public` quyết định code Java thông thường có được truy cập member hay không.
- **Module encapsulation:** `exports` và `opens` quyết định module khác có thể truy cập package ở mức API thông thường hoặc reflection sâu hay không.

## 1. Vì sao reflection cần quyền truy cập riêng?

Xét một class có field private:

~~~java
package com.acme.domain.internal;

public final class Customer {
    private final String email;

    public Customer(String email) {
        this.email = email;
    }

    public String getEmail() {
        return email;
    }
}
~~~

Code cùng class có thể đọc `email` trực tiếp. Code ngoài class không thể truy cập field này bằng Java thông thường:

~~~java
Customer customer = new Customer("user@example.com");
String email = customer.email; // Compile error: email is private
~~~

Reflection cho phép tìm field theo tên:

~~~java
Field field = customer.getClass().getDeclaredField("email");
~~~

Nhưng việc lấy được đối tượng `Field` chưa đồng nghĩa đã được phép đọc private value. Mặc định, `Field.get` vẫn áp dụng kiểm tra truy cập. Muốn bỏ qua kiểm tra truy cập Java thông thường, chương trình có thể yêu cầu bật quyền truy cập:

~~~java
field.setAccessible(true);
String email = (String) field.get(customer);
~~~

Trong ứng dụng không dùng JPMS hoặc khi hai class nằm trong cùng module, thao tác này có thể hoạt động theo các quy tắc truy cập tương ứng. Với hai named module khác nhau, module system còn kiểm tra package chứa member có được **open** cho module gọi reflection hay không.

Nếu package chưa mở, `setAccessible(true)` có thể ném `InaccessibleObjectException`. API `trySetAccessible()` trả về `false` khi không thể bật quyền truy cập.

## 2. exports và opens giải quyết hai nhu cầu khác nhau

Giả sử module domain muốn công khai API cho ứng dụng nhưng giữ package nội bộ:

~~~java
module com.acme.domain {
    exports com.acme.domain.api;
}
~~~

`exports` cho phép module đọc `com.acme.domain` sử dụng các kiểu public trong package `com.acme.domain.api`. Nó không tự động cho phép framework truy cập private field trong package đó.

Nếu một framework trong module `com.acme.mapper` cần reflection sâu vào package `com.acme.domain.internal`, module domain có thể khai báo:

~~~java
module com.acme.domain {
    exports com.acme.domain.api;
    opens com.acme.domain.internal to com.acme.mapper;
}
~~~

Ý nghĩa:

- `exports com.acme.domain.api` công khai API thông thường.
- `opens com.acme.domain.internal to com.acme.mapper` cho phép module mapper truy cập sâu bằng reflection vào package internal.
- Package internal vẫn không được export để code Java của mapper import và sử dụng trực tiếp các kiểu trong package đó.

Đây là một boundary hữu ích: ứng dụng sử dụng API công khai, còn framework được cấp quyền reflection đúng package mà nó cần.

### So sánh nhanh

| Khai báo | Truy cập API Java thông thường | Reflection tới public member | Reflection sâu tới private member |
| --- | --- | --- | --- |
| Không export, không open | Không | Bị giới hạn bởi module boundary | Không |
| `exports p` | Có, với kiểu public trong package | Có thể truy cập public member | Không tự cho phép |
| `opens p` | Không làm package thành API compile-time | Có thể truy cập bằng reflection | Có, cho module được mở |
| `exports p; opens p` | Có | Có | Có |
| `exports p to m` | Có cho module đích `m` | Có cho module đích | Không tự cho phép |
| `opens p to m` | Không | Có qua reflection cho `m` | Có cho `m` |

`exports` và `opens` không thay thế nhau. Một package có thể được export mà không open, open mà không export, hoặc vừa export vừa open nếu kiến trúc thật sự cần cả hai.

## 3. Ví dụ: mở một package cho framework mapper

Giả sử có hai module:

~~~text
src/
├── com.acme.domain/
│   ├── module-info.java
│   └── com/acme/domain/
│       ├── api/
│       │   ├── CustomerView.java
│       │   └── CustomerFactory.java
│       └── internal/
│           └── Customer.java
└── com.acme.mapper/
    ├── module-info.java
    └── com/acme/mapper/
        └── CustomerInspector.java
~~~

Module domain công khai API và mở riêng package internal cho mapper:

`com.acme.domain/module-info.java`:

~~~java
module com.acme.domain {
    exports com.acme.domain.api;
    opens com.acme.domain.internal to com.acme.mapper;
}
~~~

API công khai:

~~~java
package com.acme.domain.api;

public interface CustomerView {
    String id();
}
~~~

~~~java
package com.acme.domain.api;

public final class CustomerFactory {
    private CustomerFactory() {
    }

    public static CustomerView sample() {
        return new com.acme.domain.internal.Customer(
            "C-100",
            "customer@example.com"
        );
    }
}
~~~

Implementation nội bộ:

~~~java
package com.acme.domain.internal;

import com.acme.domain.api.CustomerView;

public final class Customer implements CustomerView {
    private final String id;
    private final String email;

    public Customer(String id, String email) {
        this.id = id;
        this.email = email;
    }

    @Override
    public String id() {
        return id;
    }
}
~~~

Package `com.acme.domain.internal` không export. Consumer chỉ nhìn thấy `CustomerView` và `CustomerFactory`, còn object thực tế được tạo ra có runtime class là `Customer`.

Module mapper:

~~~java
module com.acme.mapper {
    requires com.acme.domain;
}
~~~

Class mapper đọc private field bằng reflection:

~~~java
package com.acme.mapper;

import com.acme.domain.api.CustomerFactory;
import com.acme.domain.api.CustomerView;

import java.lang.reflect.Field;

public class CustomerInspector {
    public static void main(String[] args) throws ReflectiveOperationException {
        CustomerView customer = CustomerFactory.sample();

        Field emailField = customer.getClass().getDeclaredField("email");

        if (!emailField.trySetAccessible()) {
            throw new IllegalStateException(
                "Module domain has not opened its internal package to mapper"
            );
        }

        String email = (String) emailField.get(customer);
        System.out.println(email);
    }
}
~~~

Biên dịch cả hai module:

~~~bash
javac --module-source-path src -d out \
  -m com.acme.domain,com.acme.mapper
~~~

Chạy module mapper:

~~~bash
java --module-path out \
  --module com.acme.mapper/com.acme.mapper.CustomerInspector
~~~

Kết quả:

~~~text
customer@example.com
~~~

Mapper không import hoặc gọi trực tiếp class `Customer` ở compile-time. Nó chỉ nhận `CustomerView` từ API và dùng runtime class để tìm field. Việc đọc private field thành công vì module domain đã mở package `com.acme.domain.internal` cho đúng module `com.acme.mapper`.

Ví dụ chỉ minh họa cơ chế reflection. Trong ứng dụng thực tế, nếu mapper chỉ cần email, nên cân nhắc đưa một accessor phù hợp vào API. Reflection sâu thường được dành cho framework hoặc thư viện tổng quát cần xử lý nhiều kiểu object mà không thể viết accessor riêng cho từng kiểu.

## 4. Dùng opens không giới hạn và open module

Có ba cách thường gặp để mở package.

**Mở một package cho mọi module:**

~~~java
module com.acme.domain {
    opens com.acme.domain.internal;
}
~~~

Mọi module có thể thực hiện deep reflection trên package đó, tùy theo các điều kiện truy cập khác của JVM.

**Mở package cho một module cụ thể:**

~~~java
module com.acme.domain {
    opens com.acme.domain.internal to com.acme.mapper;
}
~~~

Đây thường là lựa chọn rõ ràng hơn vì quyền reflection chỉ cấp cho module cần dùng.

**Mở toàn bộ module:**

~~~java
open module com.acme.domain {
    exports com.acme.domain.api;
}
~~~

Một `open module` mở tất cả package cho deep reflection khi chạy. Nó không tự export tất cả package cho code Java thông thường. Các package muốn trở thành API compile-time vẫn cần khai báo `exports`.

Khi đã dùng `open module`, không khai báo thêm các directive `opens` bên trong cùng module declaration. Chọn cách mở theo đúng phạm vi framework cần, tránh mở rộng quyền reflection không cần thiết.

## 5. Mở package bằng tùy chọn launcher

Đôi khi không thể sửa descriptor của thư viện, chẳng hạn một dependency cũ hoặc ứng dụng cần thử nghiệm một framework. Có thể cấp quyền mở package ở runtime bằng `--add-opens`:

~~~bash
java \
  --add-opens com.acme.domain/com.acme.domain.internal=com.acme.mapper \
  --module-path out \
  --module com.acme.mapper/com.acme.mapper.CustomerInspector
~~~

Cú pháp:

~~~text
--add-opens source-module/package=target-module
~~~

Trong đó:

- `source-module` là module sở hữu package.
- `package` là package cần mở.
- `target-module` là module được phép deep reflection.

Với thư viện chạy trên classpath (unnamed module), có thể dùng `ALL-UNNAMED` làm target:

~~~bash
java --add-opens java.base/java.lang=ALL-UNNAMED -jar legacy-app.jar
~~~

Đây là cách tương thích hữu ích khi chuyển ứng dụng cũ sang Java mới hoặc chẩn đoán lỗi reflection. Với module do mình kiểm soát, nên khai báo `opens` phù hợp trong `module-info.java` để cấu hình quyền truy cập được quản lý cùng source.

`--add-exports` có mục đích khác: nó cho phép truy cập API public trong package chưa export. Nó không thay thế `--add-opens` khi cần đọc hoặc sửa private member.

## 6. Xử lý lỗi truy cập reflection

Hai API thường được sử dụng là `setAccessible(true)` và `trySetAccessible()`.

### setAccessible(true)

~~~java
Field field = target.getClass().getDeclaredField("secret");
field.setAccessible(true);
Object value = field.get(target);
~~~

Nếu module boundary không cho phép bật quyền truy cập, lệnh `setAccessible(true)` có thể ném `InaccessibleObjectException`. Đây là lỗi runtime liên quan đến việc không thể bỏ qua kiểm tra truy cập.

### trySetAccessible()

~~~java
Field field = target.getClass().getDeclaredField("secret");

if (field.trySetAccessible()) {
    Object value = field.get(target);
} else {
    // Chọn API công khai hoặc báo cấu hình module chưa mở package
}
~~~

`trySetAccessible()` giúp kiểm tra trước và nhận `false` nếu không thể bật quyền truy cập. Cách này phù hợp khi thư viện cần đưa ra thông báo rõ ràng hoặc có phương án dự phòng.

Nếu quyền truy cập đã được bật nhưng code vẫn gọi `Field.get` trên đối tượng không phù hợp, hoặc kiểu dữ liệu không tương thích, lỗi khác vẫn có thể xảy ra. Mở package chỉ giải quyết module access; nó không bỏ qua mọi quy tắc của reflection.

### Kiểm tra trạng thái module

Có thể kiểm tra package có đang mở cho module gọi hay không:

~~~java
Module sourceModule = target.getClass().getModule();
Module callerModule = CustomerInspector.class.getModule();

boolean opened = sourceModule.isOpen(
    "com.acme.domain.internal",
    callerModule
);
~~~

`Module.isOpen(packageName, otherModule)` trả lời câu hỏi package có mở cho module đích hay không. Đây là cách chẩn đoán hữu ích khi framework báo lỗi reflection.

## 7. MethodHandles và privateLookupIn

Reflection không phải API duy nhất để làm việc với member không public. `MethodHandles` cung cấp cơ chế truy cập method, field và constructor thông qua `Lookup`.

Ví dụ:

~~~java
MethodHandles.Lookup lookup = MethodHandles.lookup();

MethodHandles.Lookup privateLookup =
    MethodHandles.privateLookupIn(
        target.getClass(),
        lookup
    );
~~~

`privateLookupIn` có thể tạo lookup với quyền truy cập private vào target class nếu các điều kiện module và lookup được đáp ứng. Trong trường hợp target nằm ở module khác, package của target phải được mở cho module của caller và caller phải đọc được target module.

Nó không phải cách né module encapsulation. `opens` vẫn là một phần của hợp đồng truy cập. Method handles hữu ích khi cần call site có kiểu rõ ràng, hiệu năng tốt trong một số tình huống hoặc tích hợp sâu với API động.

## 8. Nguyên tắc thiết kế boundary an toàn

Khi thiết kế module có framework dùng reflection, hãy áp dụng các nguyên tắc sau:

1. **Ưu tiên API công khai:** nếu consumer cần một giá trị hoặc hành vi ổn định, cung cấp method hoặc interface thay vì yêu cầu consumer đọc private field.
2. **Chỉ mở package cần thiết:** dùng `opens package to framework.module` thay vì mở toàn bộ module.
3. **Giữ package nội bộ không export:** reflection access không yêu cầu package phải trở thành API Java thông thường.
4. **Không mở package chỉ để che lỗi thiết kế:** xem lại dependency và API trước khi cấp thêm quyền.
5. **Giữ reflection ở adapter/framework layer:** code nghiệp vụ nên gọi abstraction có kiểu rõ ràng.
6. **Kiểm tra trên runtime thực tế:** module path, tên module và tùy chọn launcher có thể khác giữa môi trường local, test và production.
7. **Đừng sửa private state tùy tiện:** reflection để đọc dữ liệu phục vụ framework thường ít rủi ro hơn việc thay đổi trạng thái nội bộ hoặc final field.

Một module có thể mở package cho ORM hoặc serializer mà vẫn giữ API công khai nhỏ. Điều quan trọng là quyền reflection phải được cấp có chủ đích và được ghi nhận rõ trong descriptor hoặc cấu hình khởi chạy.

## 9. Checklist khi gặp InaccessibleObjectException

Khi framework không truy cập được private member, hãy kiểm tra:

- Member nằm trong package nào và module nào sở hữu package đó?
- Module gọi reflection là named module hay unnamed module?
- Package đã được mở cho đúng module gọi chưa?
- `opens` trong descriptor có đúng package và đúng target module name không?
- Ứng dụng có đang chạy đúng artifact/module descriptor mới nhất không?
- Có thể thay reflection bằng API công khai hoặc constructor/factory phù hợp không?

Nếu cần mở tạm thời bằng launcher, hãy xác nhận chính xác source module, package và target module trước khi dùng `--add-opens`. Tránh dùng `ALL-UNNAMED` nếu chỉ một named module cụ thể cần quyền đó.

## Kết luận

Reflection tới private member trong JPMS chịu sự kiểm soát của cả Java access control và module encapsulation. `exports` công khai API cho code Java thông thường; `opens` cho phép deep reflection. `trySetAccessible()` giúp phát hiện sớm việc không thể bật quyền truy cập, còn `--add-opens` là phương án runtime khi cần tương thích hoặc chẩn đoán.

Một boundary tốt chỉ công khai API mà consumer cần, giữ implementation bên trong và mở đúng package cho đúng framework. Thiết kế như vậy vừa giảm coupling, vừa tránh biến reflection thành một cánh cửa mở rộng cho toàn bộ module.
