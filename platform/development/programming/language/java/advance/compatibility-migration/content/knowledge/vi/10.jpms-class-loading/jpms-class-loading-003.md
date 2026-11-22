# `requires`, `exports` và `opens` trong hợp đồng truy cập

Khi một ứng dụng Java chuyển từ classpath truyền thống sang **Java Platform Module System (JPMS)**, việc một class có modifier `public` không còn là điều kiện đủ để mã trong thành phần khác sử dụng nó. Ở ranh giới giữa các module, JVM và compiler còn cần biết module nào **đọc được** module nào, package nào được **xuất ra làm API**, và package nào được **mở cho reflection**. Ba chỉ thị cốt lõi trong `module-info.java` là `requires`, `exports` và `opens`.

Đây không chỉ là cú pháp tổ chức source code. Ba chỉ thị tạo thành một phần của **hợp đồng truy cập** giữa các module: một thư viện công bố API nào, ứng dụng được phép phụ thuộc vào module nào, và framework được phép quan sát hoặc thao tác sâu với những lớp nào. Khi nâng cấp JDK hoặc điều chỉnh `module-info.java`, thay đổi một dòng `exports` hay `opens` có thể khiến code trước đây biên dịch và chạy bình thường phát sinh lỗi truy cập, dù tên class và method không thay đổi.

Bài học tập trung vào cách các chỉ thị này vận hành, cách phối hợp chúng trong ứng dụng thực tế và cách đánh giá ảnh hưởng đến tương thích khi di chuyển sang JPMS.

## 1. Từ classpath sang hợp đồng truy cập ở mức module

Trong mô hình classpath truyền thống, các class thường được đặt trong JAR hoặc thư mục. Nếu một class là `public` và nằm trên classpath, mã ở package khác thường có thể tham chiếu nó theo quy tắc truy cập thông thường của Java.

Trong JPMS, một **named module** khai báo danh tính và các quan hệ phụ thuộc của nó bằng `module-info.java`. Ví dụ:

```java
module com.example.orders {
    requires java.sql;
    exports com.example.orders.api;
    opens com.example.orders.persistence;
}
```

Module `com.example.orders` trong ví dụ này có ba cam kết:

- Nó cần đọc module `java.sql` để sử dụng các kiểu được cung cấp theo hợp đồng truy cập của module đó.
- Nó công bố các kiểu public trong package `com.example.orders.api` như một phần API có thể truy cập từ module đọc được nó.
- Nó cho phép deep reflection đối với package `com.example.orders.persistence`, kể cả các thành viên không public theo điều kiện của reflection API.

Không có dòng nào trong ba dòng trên có nghĩa toàn bộ class của module đều công khai. `requires` chỉ liên quan đến quan hệ đọc module, `exports` mở đường truy cập thông thường tới các kiểu public trong package và `opens` phục vụ truy cập phản chiếu ở runtime.

### 1.1. Ba lớp kiểm soát khi mã ở module khác gọi API

Giả sử `com.example.app` muốn gọi một method public trong `com.example.orders.api.OrderService`. Để lời gọi thông thường hợp lệ, cần đồng thời đáp ứng các điều kiện:

1. **Readability:** module ứng dụng đọc được module thư viện, thường bằng `requires` hoặc quan hệ đọc được tạo ra theo quy tắc JPMS.
2. **Package export:** package chứa kiểu public được export cho module ứng dụng, bằng `exports` không giới hạn hoặc `exports ... to ...` có bao gồm nó.
3. **Java access control:** class, constructor và method phải có quyền truy cập phù hợp, chẳng hạn `public` đối với lời gọi từ package khác.

Có thể hình dung các cổng truy cập:

```text
com.example.app
      |
      | (1) đọc được module?
      v
com.example.orders
      |
      | (2) package được exports cho app?
      v
com.example.orders.api
      |
      | (3) class/member có quyền Java phù hợp?
      v
OrderService.submit()
```

Nếu bất kỳ điều kiện nào không được đáp ứng, code có thể bị compiler từ chối hoặc binary đã biên dịch có thể gặp lỗi truy cập khi JVM liên kết. Việc lớp có tên đầy đủ (*fully qualified name*) và tồn tại trong JAR không tự vượt qua các cổng này.

### 1.2. Reflection là một hợp đồng khác

Framework ORM, dependency injection hoặc serializer có thể cần đọc field private, gọi constructor không public hoặc thay đổi khả năng truy cập bằng `setAccessible(true)`. Đây là dạng **deep reflection**, khác với việc một client gọi method public thông thường.

Trong JPMS, `opens` điều khiển khả năng truy cập sâu kiểu này. Một package chỉ được `exports` không tự động cho phép framework thao tác với mọi private field. Ngược lại, một package chỉ được `opens` không tự trở thành package có thể import công khai trong source code của module khác.

## 2. `requires`: khai báo module phụ thuộc và quan hệ đọc

`requires` đặt trong `module-info.java` để khai báo rằng module hiện tại phụ thuộc vào một named module khác. Ví dụ:

```java
module com.example.app {
    requires com.example.orders;
    requires java.sql;
}
```

Module `com.example.app` đọc được các module `com.example.orders` và `java.sql`, miễn là cấu hình module được giải quyết thành công. Nhưng quyền đọc không có nghĩa mọi package bên trong hai module đều truy cập được. Module đích vẫn phải export package cần dùng.

### 2.1. `requires` thông thường

Đây là phụ thuộc bắt buộc trong cấu hình module:

```java
module com.example.billing {
    requires com.example.contracts;
}
```

Ở runtime, nếu `com.example.contracts` là một dependency bắt buộc mà hệ thống module không thể tìm hoặc phân giải, quá trình tạo cấu hình module có thể thất bại, thường với lỗi liên quan tới `java.lang.module.FindException` hoặc `ResolutionException`. Đó là vấn đề **phân giải module**, khác với `ClassNotFoundException` trong một lời gọi nạp class bằng tên.

Khi khai báo `requires`, cần đảm bảo module đích được cung cấp qua runtime image, module path hoặc cơ chế phân phối tương ứng. Chỉ có dependency trong file cấu hình build không bảo đảm artifact runtime đã đóng gói đúng.

### 2.2. `requires transitive`: công bố phụ thuộc để consumer đọc gián tiếp

Giả sử module `com.example.facade` cung cấp API công khai dựa trên các kiểu nằm trong module `com.example.contracts`:

```java
module com.example.facade {
    requires transitive com.example.contracts;
    exports com.example.facade.api;
}
```

Module client chỉ khai báo:

```java
module com.example.client {
    requires com.example.facade;
}
```

Nhờ `requires transitive`, client đọc `com.example.contracts` gián tiếp qua `com.example.facade`. Điều này hữu ích khi API của facade có tham số hoặc kiểu trả về thuộc module contracts.

```text
com.example.client
        |
        | requires
        v
com.example.facade
        |
        | requires transitive
        v
com.example.contracts

=> client có quan hệ đọc gián tiếp với contracts
```

Tuy nhiên, **readability không thay thế exports**. Để client thực sự sử dụng một public type trong `com.example.contracts`, package chứa type đó vẫn phải được module contracts export theo quy tắc JPMS.

Sử dụng `requires transitive` có cân nhắc: nó mở rộng hợp đồng phụ thuộc mà consumer nhìn thấy. Nếu facade chỉ sử dụng một module trong implementation nội bộ, `requires` thông thường thường thể hiện đúng ý nghĩa hơn.

### 2.3. `requires static`: phụ thuộc cần ở compile time nhưng tùy chọn ở runtime

Một số dependency phục vụ annotation hoặc chức năng tích hợp tùy chọn. JPMS hỗ trợ:

```java
module com.example.model {
    requires static com.example.annotations;
    exports com.example.model.api;
}
```

`requires static` cho biết module đích cần tồn tại khi compile nhưng không bắt buộc phải có trong quá trình giải quyết cấu hình ở runtime. Đây không phải chỉ thị bảo đảm mọi mã sử dụng dependency đó sẽ chạy an toàn khi dependency vắng mặt.

Nếu code thật sự gọi hoặc cần tải một class thuộc module tùy chọn trong lúc chạy, việc module không hiện diện vẫn có thể gây lỗi. Cần bảo đảm các đường chạy phụ thuộc vào module này được điều kiện hóa phù hợp và được kiểm thử cả khi có lẫn khi không có dependency.

### 2.4. Bảng so sánh ba dạng `requires`

| Chỉ thị | Ý nghĩa chính | Điều cần lưu ý |
|---|---|---|
| `requires m;` | Phụ thuộc và đọc trực tiếp module `m` | Module phải được giải quyết phù hợp; package cần dùng vẫn phải export. |
| `requires transitive m;` | Phụ thuộc vào `m` và truyền quan hệ đọc cho các module đọc module hiện tại | Không tự export package của `m`; dùng khi API công khai phơi bày dependency. |
| `requires static m;` | Yêu cầu module ở compile time, không bắt buộc hiện diện ở runtime | Mã gọi class của `m` lúc chạy vẫn cần dependency thực tế. |

Một module thường đọc `java.base` mặc nhiên nên không cần ghi `requires java.base;`. Điều này không có nghĩa mọi module trong JDK đều tự động được đọc theo cách tương tự.

## 3. `exports`: công bố package như một phần API

`exports` khai báo package có các public type có thể được mã ở module khác truy cập bằng các cơ chế Java thông thường, khi quan hệ readability và quyền Java cũng hợp lệ.

Ví dụ:

```java
module com.example.orders {
    exports com.example.orders.api;
}
```

Giả sử package đó chứa:

```java
package com.example.orders.api;

public class OrderService {
    public String status() {
        return "READY";
    }

    private void refreshInternalCache() {
        // Chi tiết triển khai
    }
}
```

Consumer đọc được `com.example.orders` có thể gọi method `status()` nếu đáp ứng quy tắc truy cập thông thường. Nhưng `exports` **không làm method private trở thành public**. Nó cũng không biến class package-private trong cùng package thành kiểu public.

### 3.1. Export không giới hạn

```java
exports com.example.orders.api;
```

Chỉ thị này cho phép các module khác có quan hệ đọc hợp lệ truy cập những public type trong package được export. Đây thường là lựa chọn cho API thư viện mà nhiều consumer bên ngoài cần dùng.

Module vẫn có thể giữ implementation ở package khác không export:

```text
com.example.orders
  +-- com.example.orders.api          (exports)
  |       +-- OrderService.java
  +-- com.example.orders.internal     (không exports)
          +-- OrderRepositoryImpl.java
```

Điều này cho phép nhà phát triển thay đổi implementation mà không hứa hẹn tương thích truy cập công khai cho các class nội bộ.

### 3.2. Qualified exports: chỉ export cho module được chỉ định

JPMS cho phép giới hạn những module nào được truy cập một package:

```java
module com.example.orders {
    exports com.example.orders.api;
    exports com.example.orders.integration to com.example.billing;
}
```

Package `com.example.orders.integration` chỉ được export cho module `com.example.billing` theo khai báo này. Một module khác, dù có `requires com.example.orders;`, vẫn không được import public type từ package đó theo truy cập Java thông thường.

Đây là cách thiết kế một API dành cho consumer xác định, chẳng hạn tích hợp nội bộ giữa các module trong cùng hệ thống. Tuy nhiên, tên module đích là một phần của cấu hình truy cập. Nếu module consumer đổi tên, tách module hoặc chuyển hình thức đóng gói, cần cập nhật cả qualified exports.

### 3.3. `exports` không có nghĩa code bên ngoài truy cập được mọi member

Hãy tách ba tình huống:

| Thành phần trong package đã `exports` | Module khác đọc được module nguồn | Có thể dùng thông thường? |
|---|---:|---|
| `public class` với `public` method | Có | Có, khi không có ràng buộc truy cập khác. |
| `public class` với `private` field | Có | Không thể đọc trực tiếp private field. |
| Class package-private | Có | Không thể truy cập trực tiếp từ package khác. |
| `protected` member | Có | Chỉ trong phạm vi quy tắc protected của Java. |

Một thay đổi access modifier ở cấp class/member có thể phá vỡ client dù `exports` không đổi. Ngược lại, thu hồi một dòng `exports` cũng có thể phá vỡ client dù mọi class và method vẫn giữ nguyên `public`.

## 4. `opens`: cho phép truy cập sâu bằng reflection

Reflection cho phép chương trình khám phá class, constructor, method và field ở runtime. Nhiều framework phải thao tác với các member không public, ví dụ ORM cần gán giá trị vào field private hoặc serializer cần gọi constructor không công khai.

Nếu package thuộc một named module và không được mở cho module framework, việc gọi `setAccessible(true)` để bỏ qua access checks có thể bị chặn. `opens` là chỉ thị dùng để công bố quyền truy cập phản chiếu phù hợp.

### 4.1. Mở package cho mọi module có nhu cầu reflection

```java
module com.example.orders {
    exports com.example.orders.api;
    opens com.example.orders.persistence;
}
```

Package `com.example.orders.persistence` được mở để deep reflection từ các module khác. Nhưng package này **không được export** chỉ vì có `opens`. Một ứng dụng bình thường vẫn không thể import kiểu từ package đó nếu không có export phù hợp.

### 4.2. Qualified opens: chỉ mở cho framework hoặc module xác định

```java
module com.example.orders {
    exports com.example.orders.api;
    opens com.example.orders.persistence to com.example.orm;
}
```

Chỉ module `com.example.orm` được quyền deep reflection theo cấu hình mở package này. Điều này giảm phạm vi phơi bày implementation so với mở package cho tất cả module.

Tên trong mệnh đề `to` phải tương ứng với tên module thực tế của framework hoặc consumer. Một số dependency cũ chạy trên classpath thuộc *unnamed module*, hoặc JAR trên module path có tên *automatic module*; cần xác định chính xác mô hình triển khai trước khi viết qualified opens.

### 4.3. `open module`: mở mọi package cho reflection

JPMS còn hỗ trợ:

```java
open module com.example.legacy {
    requires java.sql;
    exports com.example.legacy.api;
}
```

`open module` khiến tất cả package trong module được mở cho deep reflection. Đây có thể là bước chuyển tiếp cho ứng dụng phụ thuộc nhiều vào reflection, nhưng phạm vi mở rộng hơn cần thiết và có thể làm yếu tính đóng gói mong muốn.

Một `open module` không được viết thêm các chỉ thị `opens` riêng lẻ. Việc mở toàn bộ package cũng **không tự động export** chúng cho truy cập source code thông thường; `exports` vẫn có ý nghĩa độc lập.

### 4.4. Khi nào cần `opens` thay vì `exports`?

| Nhu cầu | Chỉ thị thường phù hợp | Giải thích |
|---|---|---|
| Ứng dụng import một public class và gọi public method | `exports` + quan hệ đọc | Cấp quyền truy cập Java thông thường. |
| ORM gán field private của entity bằng reflection | `opens` cho module ORM | Hỗ trợ deep reflection ở runtime. |
| Serializer đọc constructor private bằng reflection | `opens` cho module serializer | Truy cập cần vượt kiểm tra Java access thông thường. |
| Module tích hợp cần gọi public helper trong package riêng | `exports ... to ...` | Cung cấp API công khai cho consumer được chỉ định. |
| Vừa cần public API vừa cần deep reflection | `exports` và `opens` cho cùng package nếu cần | Hai mục đích truy cập khác nhau, có thể cùng tồn tại. |

Lưu ý: các public member của một package đã được export có thể được dùng theo nhiều thao tác reflection công khai thông thường mà không cần `opens`. `opens` đặc biệt quan trọng khi muốn *suppress* các kiểm tra truy cập để vào thành viên không public hoặc thực hiện deep reflection.

## 5. Ví dụ đầy đủ: một thư viện vừa có API public vừa có model cho reflection

Xét hai module:

```text
src/
  com.example.library/
    module-info.java
    com/example/library/api/GreetingService.java
    com/example/library/internal/SecretRecord.java
  com.example.client/
    module-info.java
    com/example/client/Main.java
```

### 5.1. Module thư viện

File `src/com.example.library/module-info.java`:

```java
module com.example.library {
    exports com.example.library.api;
    opens com.example.library.internal to com.example.client;
}
```

File `src/com.example.library/com/example/library/api/GreetingService.java`:

```java
package com.example.library.api;

public class GreetingService {
    public String greet(String name) {
        return "Xin chào, " + name;
    }
}
```

File `src/com.example.library/com/example/library/internal/SecretRecord.java`:

```java
package com.example.library.internal;

public class SecretRecord {
    private final String code = "CODE-42";

    public SecretRecord() {
    }
}
```

`SecretRecord` là một public class theo ngôn ngữ Java, nhưng package của nó không export. Vì vậy, code của client không thể import class này theo đường truy cập thông thường. Qualified opens chỉ cung cấp khả năng deep reflection cho `com.example.client`.

### 5.2. Module client

File `src/com.example.client/module-info.java`:

```java
module com.example.client {
    requires com.example.library;
}
```

File `src/com.example.client/com/example/client/Main.java`:

```java
package com.example.client;

import com.example.library.api.GreetingService;

import java.lang.reflect.Field;

public class Main {
    public static void main(String[] args) throws Exception {
        GreetingService service = new GreetingService();
        System.out.println(service.greet("Java"));

        Class<?> type = Class.forName(
            "com.example.library.internal.SecretRecord"
        );

        var constructor = type.getDeclaredConstructor();
        constructor.setAccessible(true);
        Object record = constructor.newInstance();

        Field code = type.getDeclaredField("code");
        code.setAccessible(true);
        System.out.println(code.get(record));
    }
}
```

Ở đây có hai kiểu truy cập khác nhau. `GreetingService` được import và gọi nhờ `requires` kết hợp với `exports`. `SecretRecord` không được import trực tiếp; client tìm class theo tên, sau đó đọc field private bằng reflection nhờ package được `opens` cho module client.

### 5.3. Biên dịch và chạy ví dụ

Trong thư mục gốc chứa `src/`, với JDK hỗ trợ JPMS:

```bash
javac --module-source-path src -d out \
  --module com.example.library,com.example.client

java --module-path out \
  --module com.example.client/com.example.client.Main
```

Các lệnh minh họa sử dụng ký tự nối dòng `\` của shell kiểu Unix. Trên Windows PowerShell, có thể nhập mỗi lệnh trên một dòng hoặc dùng cách nối dòng tương ứng của shell. Điều quan trọng là cả hai module nằm trong module path khi chạy.

Nếu xóa `requires com.example.library;` khỏi client, compiler sẽ không có quan hệ đọc cần thiết để import public API của thư viện. Nếu xóa `exports com.example.library.api;` khỏi thư viện, client vẫn khai báo requires nhưng không còn quyền truy cập source tới package API. Nếu xóa `opens com.example.library.internal to com.example.client;`, lời gọi deep reflection như `setAccessible(true)` có thể thất bại với lỗi module access ở runtime.

Ví dụ thể hiện rõ: ba chỉ thị xử lý ba điều kiện khác nhau. Sửa một chỉ thị không tự động giải quyết hai điều kiện còn lại.

## 6. Các lỗi điển hình khi hợp đồng truy cập không khớp

### 6.1. Module không đọc dependency

Nếu module client dùng class từ một module khác nhưng không có quan hệ đọc phù hợp, compiler có thể báo thông tin như package thuộc module mà module hiện tại không đọc được.

```text
package com.example.library.api is not visible
  (package ... is declared in module com.example.library,
   but module com.example.client does not read it)
```

Hướng xử lý là xác định consumer có thực sự cần phụ thuộc module này hay không, rồi khai báo `requires` hoặc điều chỉnh kiến trúc module. Không nên dùng `exports` để chữa thiếu readability: module library không thể tự thay thế khai báo phụ thuộc của client bằng export.

### 6.2. Package không được export

Nếu client có `requires` nhưng package của thư viện không được export cho nó, compiler có thể báo:

```text
package com.example.library.internal is not visible
  (package ... is declared in module com.example.library,
   which does not export it)
```

Hãy xác định package đó có nên là public API hay không. Nếu là API được hỗ trợ, bổ sung `exports` hoặc `exports ... to ...` có chủ đích. Nếu chỉ là implementation, sửa client để sử dụng API công khai thay vì export toàn bộ nội bộ chỉ để build thành công.

### 6.3. Deep reflection bị chặn

Nếu framework gọi `setAccessible(true)` trên private field nằm trong package chưa open cho module gọi, runtime có thể ném `java.lang.reflect.InaccessibleObjectException`, với thông báo cho biết module nguồn không `opens` package tương ứng cho module đích.

Ví dụ khái quát:

```text
java.lang.reflect.InaccessibleObjectException:
  Unable to make field private ... accessible:
  module com.example.library does not "opens"
  com.example.library.internal to module com.example.client
```

Đây không phải `NoSuchFieldError`: field có thể vẫn tồn tại, nhưng hành động truy cập sâu không được phép. Hãy xác định module của framework thực sự đang gọi reflection và mở đúng package cần thiết, hoặc nâng framework để nó dùng API công khai khi phù hợp.

### 6.4. Binary cũ gặp `IllegalAccessError`

Nếu consumer đã được biên dịch với một version module thư viện có package được export nhưng phiên bản thư viện mới thu hồi export, source consumer mới sẽ bị compiler từ chối. Binary consumer cũ không tự biên dịch lại và vẫn giữ các tham chiếu đến public class/method trước đây; khi liên kết, JVM có thể phát hiện không còn quyền truy cập và ném `IllegalAccessError`.

Việc giữ nguyên tên, package và method descriptor không bảo đảm tương thích nhị phân nếu hợp đồng module bị thu hẹp. Cần phân biệt lỗi access check này với `NoSuchMethodError`, vốn thường cho biết method có tên và descriptor tương ứng không còn được tìm thấy.

### 6.5. Thiếu module khi khởi động

Nếu một module yêu cầu dependency bằng `requires` mà runtime không cung cấp module đó, module resolution có thể thất bại trước khi ứng dụng vào `main()`:

```text
java.lang.module.FindException:
  Module com.example.library not found,
  required by com.example.client
```

Hãy kiểm tra module path, tên module và packaging. Không nên tìm sửa `exports` hoặc `opens` khi lỗi thực chất là module bắt buộc không có trong cấu hình runtime.

| Triệu chứng | Câu hỏi cần kiểm tra trước | Thay đổi thường liên quan |
|---|---|---|
| Client không đọc module khác | Có quan hệ module readability chưa? | `requires`, `requires transitive` hoặc cấu hình đặc biệt |
| Import public class vẫn bị từ chối | Package đã export cho client chưa? | `exports` hoặc qualified exports |
| Reflection trên private field thất bại | Package đã open cho module gọi chưa? | `opens` hoặc qualified opens |
| Binary cũ lỗi truy cập sau khi thay JAR | Export/access modifier có bị thu hẹp không? | Hợp đồng binary/module compatibility |
| Runtime báo missing module | Module có mặt trên module path/resolution không? | Packaging, module name và `requires` |

## 7. Tương thích khi nâng cấp JDK và thay đổi module descriptor

Một module descriptor là một phần của API contract. Khi thay đổi nó, không nên chỉ nhìn vào các method Java còn hay mất.

### 7.1. Bỏ `exports` là thay đổi có thể phá vỡ consumer

Giả sử phiên bản 1:

```java
module com.example.library {
    exports com.example.library.api;
    exports com.example.library.legacy;
}
```

Ở phiên bản 2, tác giả bỏ export của package legacy:

```java
module com.example.library {
    exports com.example.library.api;
}
```

Ngay cả khi các class trong `com.example.library.legacy` vẫn là public và không đổi descriptor, consumer ở module khác có thể mất quyền truy cập. Cần coi đây là thay đổi hợp đồng và kiểm tra cả source compatibility lẫn binary compatibility.

Nếu mục tiêu là loại bỏ API legacy, nên công bố lộ trình, giữ API thay thế trong một giai đoạn và chỉ thu hồi quyền trong một đợt breaking change có kế hoạch.

### 7.2. Thu hẹp `exports` thành qualified exports

Đổi:

```java
exports com.example.library.api;
```

thành:

```java
exports com.example.library.api to com.example.partner;
```

có nghĩa chỉ module `com.example.partner` còn quyền truy cập qua export đó. Những consumer khác từng sử dụng package này có thể bị chặn. Đây là thay đổi tương thích dù package và code bên trong không đổi.

Qualified exports hữu ích khi xác định rõ nhóm consumer, nhưng không nên dùng để hạn chế API đã công bố rộng rãi mà không đánh giá các ứng dụng hiện tại.

### 7.3. Bỏ `opens` có thể phá vỡ framework ở runtime

Nếu một entity package từng được mở cho framework ORM và sau đó bị đóng, ứng dụng có thể compile thành công nhưng ORM thất bại khi dựng entity, đọc field hoặc khởi tạo proxy bằng reflection.

Lỗi có thể chỉ xuất hiện ở một luồng xử lý database cụ thể, không nhất thiết ngay lúc khởi động. Vì vậy, ngoài compile, cần integration test các framework sử dụng reflection và kiểm tra hành vi trên đúng module path của production.

### 7.4. Thay `requires transitive` thành `requires`

Khi một module ngừng công bố quan hệ đọc phụ thuộc, consumer trước đây tận dụng readability gián tiếp có thể không còn compile hoặc truy cập được kiểu trong module phụ thuộc. Ngay cả khi code implementation của module đầu tiên vẫn hoạt động, các consumer của API công khai có thể cần bổ sung `requires` trực tiếp.

Đây là lý do `requires transitive` cần được xem như một quyết định thiết kế hợp đồng API, không chỉ là cú pháp để làm compiler hết cảnh báo.

### 7.5. Thay tên module cũng ảnh hưởng đến hợp đồng

Consumer khai báo `requires` bằng **module name**, không phải nhất thiết bằng tên file JAR. Nếu module đổi tên, consumer có thể gặp lỗi module resolution. Các qualified exports và qualified opens cũng cần được cập nhật theo tên module mới.

Khi chuyển một JAR truyền thống sang explicit named module, hãy xác định tên module ổn định và kế hoạch chuyển đổi. Tên automatic module suy ra từ JAR hoặc lấy từ `Automatic-Module-Name` có thể khác tên explicit module mà thư viện chọn sau này; cần kiểm tra thay vì suy luận.

## 8. Classpath, unnamed module và automatic module

Khi migration, một ứng dụng có thể chưa chuyển toàn bộ thư viện sang JPMS. Hiểu các vùng chuyển tiếp giúp tránh lỗi do cấu hình không đồng nhất.

### 8.1. Unnamed module của classpath

Code đặt trên classpath thuộc unnamed module thay vì có descriptor `module-info.java` riêng. Đây là cơ chế giúp ứng dụng legacy tiếp tục hoạt động trong môi trường JDK có JPMS.

Tuy nhiên, một named module không tự động coi mọi class trên classpath là dependency hợp lệ. Khi chuyển dần sang named module, cần xem hướng phụ thuộc và cách đóng gói, vì named module không thể đơn giản khai báo `requires` tới unnamed module như với một named module thông thường.

### 8.2. Automatic module

Một JAR không có `module-info.class` nhưng được đặt trên module path có thể được xem là automatic module. Đây là cơ chế chuyển tiếp giúp JAR legacy tham gia hệ module; nó có tên module và phạm vi đọc/export rộng hơn explicit module.

Automatic module không thay thế việc thiết kế module descriptor ổn định. Khi thư viện chuyển sang explicit module, các package nội bộ có thể không còn được export rộng rãi. Consumer phụ thuộc vào sự mở rộng mặc định trước đó sẽ cần điều chỉnh để dùng API chính thức.

### 8.3. Split package và module path

JPMS có các ràng buộc với trường hợp nhiều named module chứa cùng package (*split package*). Một cấu trúc từng hoạt động trên classpath có thể không còn dễ giải quyết khi các JAR được chuyển lên module path.

Khi gặp lỗi module resolution liên quan đến package bị trùng, cần kiểm tra cách chia package trong các JAR, dependency bắc cầu và chiến lược modularization. Thêm `requires` hay `exports` không giải quyết được một thiết kế split package không hợp lệ.

## 9. Các tùy chọn chuyển tiếp: `--add-reads`, `--add-exports`, `--add-opens`

Trong migration, đôi khi không thể sửa ngay module descriptor của thư viện hoặc nâng framework trong cùng một đợt. JVM và compiler có một số tùy chọn hỗ trợ điều chỉnh quan hệ truy cập theo cấu hình.

### 9.1. `--add-reads`

```bash
--add-reads com.example.app=com.example.library
```

Tùy chọn này bổ sung quan hệ readability từ module nguồn tới module đích trong cấu hình phù hợp. Nó giải quyết vấn đề **đọc module**, không tự export package đang bị đóng.

### 9.2. `--add-exports`

```bash
--add-exports com.example.library/com.example.library.internal=com.example.app
```

Tùy chọn này export một package từ module nguồn cho module đích xác định để phục vụ truy cập Java thông thường tới public type. Nó không tự cho phép deep reflection vào mọi private field.

Trong một số migration, có thể cần export cho code trên classpath bằng đích đặc biệt `ALL-UNNAMED`, ví dụ:

```bash
--add-exports com.example.library/com.example.library.internal=ALL-UNNAMED
```

Đây là tùy chọn chuyển tiếp, không phải lý do để biến một API nội bộ thành phụ thuộc lâu dài.

### 9.3. `--add-opens`

```bash
--add-opens com.example.library/com.example.library.internal=com.example.framework
```

Tùy chọn này mở package cho deep reflection từ module đích. Khi framework chạy trên classpath, có thể gặp dạng:

```bash
--add-opens com.example.library/com.example.library.internal=ALL-UNNAMED
```

Chỉ mở đúng package và đúng module tiêu thụ. Không nên thêm hàng loạt `--add-opens` theo một danh sách sao chép từ Internet mà không xác định đường truy cập thực tế.

### 9.4. Ba tùy chọn không thay thế nhau

| Tùy chọn | Điều chỉnh | Không tự giải quyết |
|---|---|---|
| `--add-reads` | Module nào được đọc | Package chưa được export hoặc mở. |
| `--add-exports` | Package public API có thể được truy cập thông thường | Deep reflection vào member không public. |
| `--add-opens` | Package được mở cho deep reflection | Quan hệ import/compile và export API thông thường. |

Những tùy chọn này có thể xuất hiện ở compile time hoặc runtime tùy mục tiêu, nhưng cấu hình của một giai đoạn không tự động áp dụng cho giai đoạn kia. Nếu dùng flag để compile, vẫn phải đảm bảo runtime có quan hệ truy cập phù hợp. Nếu runtime cần flag, hãy đặt ở lệnh khởi động production hoặc nơi tạo tiến trình JVM tương ứng, không chỉ trong task test.

Trong các JDK hiện đại có strong encapsulation, không nên dựa vào các cơ chế nới lỏng cũ như `--illegal-access` để thay thế một kế hoạch nâng framework/API. Những cấu hình chuyển tiếp cần có owner, lý do, giới hạn và thời điểm gỡ bỏ.

## 10. Kiểm tra và chẩn đoán hợp đồng truy cập

Để biết sự cố nằm ở `requires`, `exports` hay `opens`, cần kết hợp kiểm tra descriptor, runtime và stack trace.

### 10.1. Xem module descriptor

Với một JAR có module descriptor hoặc tên module có thể suy ra, có thể dùng:

```bash
jar --describe-module --file library.jar
```

Đối với các module có sẵn trong runtime, có thể liệt kê:

```bash
java --list-modules
```

Hoặc xem mô tả một module đang được runtime nhận diện:

```bash
java --describe-module java.sql
```

Khi kiểm tra một module trên module path, cần cấu hình `--module-path` phù hợp. Hãy dựa vào output để xác nhận tên module, các requires, exports, qualified exports và opens thực tế. Không chỉ suy luận từ tên file JAR hoặc từ mã nguồn của phiên bản khác.

### 10.2. Phân tích dependency bằng `jdeps`

`jdeps` có thể hỗ trợ xem phụ thuộc tĩnh giữa các JAR, package hoặc module. Ví dụ:

```bash
jdeps --module-path mods --summary app.jar
```

Kết quả giúp tìm module hoặc package mà code tham chiếu theo phân tích tĩnh. Nhưng `jdeps` không nhìn thấy đầy đủ mọi phụ thuộc được nạp qua tên chuỗi, service loader, plugin hoặc reflection. Vì vậy, không thể dùng một kết quả `jdeps` sạch để kết luận mọi `opens` đang dùng đều không cần thiết.

### 10.3. Đọc đúng phần thông báo lỗi

Các thông điệp thường cho biết rất nhiều về cổng truy cập bị thiếu:

- **“module A does not read module B”**: kiểm tra quan hệ readability, `requires` và các cấu hình module.
- **“module B does not export package p to module A”**: kiểm tra `exports` hoặc qualified exports.
- **“module B does not open package p to module A”**: kiểm tra `opens`/qualified opens cho deep reflection.
- **“Module X not found, required by Y”**: kiểm tra module path, tên module và phụ thuộc bắt buộc.

Nếu lỗi xuất hiện khi khởi tạo bean, serialize object hoặc tạo proxy, hãy đọc sâu chuỗi `Caused by`. Exception của framework có thể bọc `InaccessibleObjectException` hoặc `IllegalAccessException` liên quan module.

### 10.4. Xác định module thực sự của caller

Một JAR trên classpath và cùng JAR trên module path có thể có vị trí module khác nhau. Nếu framework được chạy như automatic module, tên module cũng có thể khác tên artifact mà người vận hành dự đoán.

Khi cần, có thể in thông tin module của một class:

```java
Module module = SomeFrameworkClass.class.getModule();
System.out.println(module.getName());
```

Với unnamed module, `getName()` trả về `null`. Đây là một trong các cách xác nhận đối tượng cần được qualified `opens` hoặc đích runtime flag tương ứng.

## 11. Thiết kế hợp đồng truy cập bền vững khi migration

Một module tốt không nhất thiết là module export và open ít package nhất trong mọi tình huống. Mục tiêu là công bố đúng API cần được hỗ trợ, cho phép các framework vận hành theo nhu cầu và tránh làm consumer phụ thuộc vào chi tiết nội bộ.

### 11.1. Công bố API nhỏ, rõ ràng và ổn định

Nên đưa API được hỗ trợ vào những package có tên rõ nghĩa, chẳng hạn `api`, `spi` hoặc `contracts`. Chỉ export những package thực sự dành cho consumer. Các class implementation nên nằm trong package không export nếu client không cần truy cập trực tiếp.

Nếu một package đã được export rộng rãi từ lâu, việc thu hồi export cần có kế hoạch migration tương ứng với breaking API change. Không nên tùy tiện bỏ export chỉ vì package có tên `internal`.

### 11.2. Dùng `requires transitive` theo hợp đồng API

Nếu public API của module A có tham số hoặc trả về kiểu thuộc module B, `requires transitive B` thường phản ánh đúng sự phụ thuộc mà consumer cần nhìn thấy. Nếu B chỉ được dùng trong implementation của A, `requires B` giúp tránh lan truyền quan hệ đọc không cần thiết.

Việc thay đổi giữa hai dạng này cần được xem xét từ góc nhìn client đã triển khai, không chỉ từ việc module A tự compile được.

### 11.3. Mở package cho framework theo phạm vi tối thiểu

ORM, serializer hoặc dependency injection framework có thể cần deep reflection. Thay vì `open module` hoặc `opens p;` toàn hệ thống, ưu tiên `opens p to module.framework;` nếu xác định được module đích và cách triển khai phù hợp.

Nếu framework chạy trên classpath hoặc có nhiều module đích, cần chọn cấu hình thực tế hoạt động và ghi rõ lý do. Phạm vi mở quá hẹp có thể làm framework lỗi runtime; phạm vi mở quá rộng khiến tính đóng gói của module kém hiệu quả.

### 11.4. Không dùng flags để che lấp thiết kế lỗi

Các JVM flags là công cụ hữu ích để duy trì khả năng vận hành trong một giai đoạn chuyển đổi, nhưng cần được theo dõi như khoản nợ migration:

| Thông tin | Ví dụ cần ghi |
|---|---|
| Flag | `--add-opens module/package=consumer` |
| Nguyên nhân | Framework cũ truy cập field private bằng reflection. |
| Phạm vi | Chỉ package entity, chỉ JVM chạy dịch vụ A. |
| Owner | Nhóm sở hữu framework và quá trình migration. |
| Kế hoạch | Nâng framework, cập nhật descriptor hoặc thay cách ánh xạ. |
| Điều kiện gỡ bỏ | Integration test đạt khi bỏ flag trên JDK đích. |

Một build chạy được nhờ các flag không đồng nghĩa hợp đồng module đã được thiết kế hoàn chỉnh. Trước khi phát hành, cần kiểm thử cả cấu hình production và cơ chế chuyển tiếp được ghi nhận.

## 12. Quy trình kiểm thử tương thích cho ba chỉ thị

Khi nâng JDK hoặc thay `module-info.java`, hãy xác minh riêng từng lớp truy cập.

### Bước 1: Lập danh sách các consumer và module

Xác định tên module chính thức, các JAR trên module path, thư viện vẫn chạy trên classpath và framework dùng reflection. Ghi nhận phiên bản JDK/build và phiên bản dependency.

### Bước 2: Kiểm tra readability với `requires`

Biên dịch các module tiêu thụ API với module descriptor mục tiêu. Xác định những đường phụ thuộc trực tiếp, những đường cần transitive và những dependency tùy chọn chỉ dùng compile time.

### Bước 3: Kiểm tra package API với `exports`

Với mỗi public API được công bố, tạo client test bên ngoài module và biên dịch trên module path. Nếu dùng qualified exports, kiểm tra cả consumer được cho phép và consumer không nằm trong danh sách.

### Bước 4: Kiểm tra reflection với `opens`

Chạy integration test cho ORM, mapper, serializer và dependency injection. Không chỉ kiểm tra class có được tìm thấy; cần thực sự gọi constructor, đọc/ghi field và thực hiện các thao tác deep reflection mà framework sử dụng.

### Bước 5: Chạy binary consumer đã biên dịch trước đó

Khi đánh giá tương thích nhị phân, giữ nguyên artifact consumer được biên dịch với thư viện cũ rồi thay thư viện/module descriptor bằng phiên bản mới. Chạy những đường truy cập API quan trọng để phát hiện `IllegalAccessError` và các linkage error có thể bị che khi chỉ biên dịch lại source.

### Bước 6: Kiểm tra đóng gói và runtime thực tế

Chạy trên đúng module path, container image và lệnh khởi động của production. Đảm bảo các runtime flags được áp dụng cho đúng tiến trình Java. Một test chạy trên classpath không bảo đảm một ứng dụng modular chạy trên module path sẽ có cùng kết quả.

### Bước 7: Ghi nhận bằng chứng và quyết định

Với mỗi thay đổi, lưu module descriptor cũ/mới, danh sách module consumer, lỗi/stack trace nếu có, test xác nhận và kế hoạch xử lý. Chỉ coi thay đổi là an toàn trong phạm vi các consumer và đường chạy đã được kiểm chứng.

## 13. Những nhầm lẫn thường gặp

**“Có `requires` thì dùng được mọi class của dependency.”** Không. Module nguồn còn phải export package phù hợp và class/member cần có quyền Java thích hợp.

**“Class public nghĩa là module khác luôn import được.”** Không. Public visibility không vượt qua ranh giới package export và readability của JPMS.

**“`exports` cho phép framework truy cập private field.”** Không. Truy cập sâu bằng reflection thường cần package được open cho module gọi.

**“`opens` có nghĩa package đó là API public.”** Không. Opens dành cho reflection, không tự công bố package cho import/call thông thường.

**“`requires transitive` đồng thời export mọi package của dependency.”** Không. Nó truyền quan hệ đọc; module dependency vẫn kiểm soát exports của các package của chính nó.

**“`requires static` đảm bảo không cần dependency ở runtime.”** Không. Nó không bắt buộc module ở giai đoạn giải quyết runtime; code thực thi mà dùng class của dependency vẫn cần class đó hiện diện.

**“Chỉ cần thêm `--add-opens` là sửa mọi lỗi module.”** Không. Lỗi thiếu readability, thiếu export, thiếu module bắt buộc và lỗi reflection cần những hướng xử lý khác nhau.

**“Nếu không sửa source và method descriptor thì binary chắc chắn tương thích.”** Không. Thu hồi `exports`, đổi qualified exports hoặc thu hẹp Java access modifier có thể khiến binary cũ gặp lỗi truy cập khi liên kết.

**“Chạy test trên classpath là đủ.”** Không. Nếu production sử dụng module path, phải kiểm tra đúng cấu hình module, tên module và runtime flags thực tế.

## 14. Checklist trước khi chấp nhận một thay đổi JPMS

- [ ] Đã xác định tên module nguồn, module đích và các consumer thực tế.
- [ ] Đã kiểm tra `requires` và phân biệt phụ thuộc trực tiếp, transitive, static.
- [ ] Đã đối chiếu những public package cần được export với API hỗ trợ chính thức.
- [ ] Đã kiểm tra qualified exports không vô tình loại consumer hợp lệ.
- [ ] Đã xác định framework nào cần deep reflection và package nào phải open.
- [ ] Đã phân biệt `exports`, `opens` và `open module` trong thiết kế.
- [ ] Đã kiểm tra classpath/unnamed module và automatic module ở các thành phần legacy.
- [ ] Đã xác minh module name, `module-info.java` và module path của artifact thực tế.
- [ ] Đã kiểm tra các JVM flags chuyển tiếp, phạm vi và kế hoạch gỡ bỏ.
- [ ] Đã biên dịch source consumer với module descriptor mới.
- [ ] Đã chạy integration test cho reflection, ORM, serializer và plugin liên quan.
- [ ] Đã chạy binary consumer cũ với module thư viện mới khi cần giữ tương thích nhị phân.
- [ ] Đã lưu kết quả kiểm thử, lỗi còn tồn tại và người phụ trách xử lý.

## 15. Kết luận

`requires`, `exports` và `opens` là ba phần độc lập nhưng liên quan chặt chẽ trong hợp đồng truy cập của JPMS. **`requires` quyết định quan hệ đọc giữa các module; `exports` công bố package có thể dùng như API Java thông thường; `opens` cho phép truy cập sâu bằng reflection ở runtime.** Muốn gọi API từ module khác, cần đồng thời thỏa readability, package export và Java access control. Muốn truy cập private member bằng reflection, cần xem thêm quyền mở package cho caller.

Trong migration, thay đổi module descriptor có thể phá vỡ source compatibility, binary compatibility hoặc tích hợp framework ngay cả khi class và method trong thư viện vẫn tồn tại. Vì vậy, không nên xem `module-info.java` chỉ là cấu hình nội bộ. Hãy thiết kế module dựa trên consumer thực tế, công bố API có chủ đích, mở quyền reflection theo phạm vi tối thiểu và kiểm thử cả code mới lẫn artifact đã biên dịch trước khi thay đổi hợp đồng truy cập trên production.
