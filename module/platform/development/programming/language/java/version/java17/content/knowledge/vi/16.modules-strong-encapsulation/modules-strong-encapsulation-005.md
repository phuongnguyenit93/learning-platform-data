# Phân biệt IllegalAccessError và InaccessibleObjectException trong Java 17

**Chủ đề:** Java 17  
**Chương:** Module và đóng gói mạnh  
**Bài học:** Phân biệt IllegalAccessError và InaccessibleObjectException

Từ Java 9, hệ thống module của Java Platform (JPMS) bổ sung ranh giới truy cập giữa các module. Một package có thể được xuất công khai cho module khác bằng `exports`, hoặc được mở cho reflection bằng `opens`. Hai cơ chế này phục vụ những kiểu truy cập khác nhau. Khi chương trình, thư viện hoặc framework vượt qua ranh giới module không được phép, Java có thể báo lỗi ở thời điểm liên kết hoặc khi reflection cố gắng bỏ qua kiểm tra truy cập.

Hai tên lỗi dễ bị nhầm là:

- **`IllegalAccessError`**: một `LinkageError` (lỗi liên kết) xảy ra khi mã đã được biên dịch cố truy cập một class, method hoặc field mà JVM xác định là không được phép truy cập trong môi trường chạy hiện tại.
- **`InaccessibleObjectException`**: một `RuntimeException` xảy ra khi reflection cố gắng bật quyền truy cập bị hạn chế, chẳng hạn gọi `setAccessible(true)`, nhưng Java không cho phép bỏ qua kiểm tra truy cập.

Điểm phân biệt cốt lõi là **cách truy cập thất bại**. `IllegalAccessError` thường liên quan đến truy cập trực tiếp được mã bytecode yêu cầu khi liên kết hoặc thực thi. `InaccessibleObjectException` liên quan đến việc reflection muốn mở một thành viên vốn không thể truy cập theo quy tắc hiện hành.

Java 17 áp dụng strong encapsulation cho các API nội bộ của JDK. Vì vậy, thư viện cũ dựa vào reflection trên các package nội bộ có thể gặp `InaccessibleObjectException`; mã phụ thuộc vào package không được export cũng có thể gặp lỗi liên kết. Bài học này tập trung vào API module và reflection còn áp dụng trong Java 17, không dựa vào các tùy chọn nới lỏng truy cập đã lỗi thời.

## 1. Hai lỗi nằm ở đâu trong hệ thống exception?

Mặc dù cả hai đều liên quan đến quyền truy cập, chúng thuộc hai nhánh khác nhau trong hệ thống kiểu của Java.

```text
Throwable
├── Exception
│   └── RuntimeException
│       └── InaccessibleObjectException
│
└── Error
    └── LinkageError
        └── IncompatibleClassChangeError
            └── IllegalAccessError
```

| Đặc điểm | `IllegalAccessError` | `InaccessibleObjectException` |
|---|---|---|
| Phân cấp | `Error` → `LinkageError` | `RuntimeException` |
| Nhóm vấn đề | Liên kết/truy cập của mã đã biên dịch | Reflection không thể bỏ qua kiểm tra truy cập |
| Thời điểm thường gặp | Khi JVM liên kết hoặc thực thi truy cập trực tiếp | Khi gọi API reflection như `setAccessible(true)` |
| Cơ chế thường liên quan | Quy tắc truy cập class/member và ranh giới module | `AccessibleObject`, `Field`, `Method`, `Constructor` |
| Có phải checked exception? | Không | Không |
| Cách xử lý chính | Sửa module dependency, export package hoặc cấu hình runtime đúng | Mở package có chủ đích hoặc ngừng deep reflection |

### 1.1. IllegalAccessError là lỗi liên kết

`IllegalAccessError` thuộc nhánh `LinkageError`. Nó xuất hiện khi JVM gặp một truy cập mà mã đã biên dịch yêu cầu, nhưng class hoặc thành viên đích không thể được truy cập trong môi trường chạy.

Một tình huống điển hình:

1. Mã ứng dụng được biên dịch khi package thư viện được export hoặc được cấp quyền bằng tùy chọn biên dịch.
2. Khi chạy, module descriptor hoặc cấu hình module khác với lúc biên dịch.
3. JVM cố liên kết tham chiếu đến class/member trong package không được export cho module ứng dụng.
4. JVM ném `IllegalAccessError`.

Vì đây là `Error`, không nên xem nó như lỗi nhập liệu thông thường và bắt `Exception` để tiếp tục chạy. Cần sửa cấu hình module hoặc dependency tạo ra truy cập không hợp lệ.

### 1.2. InaccessibleObjectException là lỗi của thao tác reflection

`InaccessibleObjectException` thuộc package `java.lang.reflect`. Nó được ném khi một thao tác reflection cố gắng làm cho một đối tượng `AccessibleObject` bỏ qua kiểm tra truy cập, nhưng việc đó không được phép.

Ví dụ:

```java
import java.lang.reflect.Field;

public class StringReflectionDemo {
    public static void main(String[] args) throws Exception {
        Field valueField = String.class.getDeclaredField("value");

        valueField.setAccessible(true); // Java 17: có thể ném
                                      // InaccessibleObjectException
    }
}
```

Trong JDK 17, package `java.lang` thuộc module `java.base` không được mở mặc định cho deep reflection từ ứng dụng. Vì vậy, việc bật truy cập vào field private của `String` bị từ chối.

Điều này không có nghĩa field không tồn tại. `getDeclaredField("value")` có thể tìm thấy field, nhưng bước yêu cầu bỏ qua kiểm tra truy cập bị module system từ chối.

## 2. Nền tảng cần hiểu: exports và opens

JPMS phân biệt quyền truy cập API thông thường với quyền truy cập reflection sâu (*deep reflection*).

### 2.1. exports: cho phép module khác sử dụng API công khai

Một module có thể export package trong `module-info.java`:

```java
module com.example.model {
    exports com.example.model.api;
}
```

Module đọc `com.example.model` có thể truy cập các kiểu public trong package `com.example.model.api`, nếu các điều kiện truy cập Java khác cũng được thỏa mãn.

`exports` chủ yếu hỗ trợ việc sử dụng API công khai thông thường:

```java
package com.example.model.api;

public class User {
    public String displayName() {
        return "An";
    }
}
```

Ứng dụng khác có thể khai báo:

```java
module com.example.app {
    requires com.example.model;
}
```

và sử dụng:

```java
import com.example.model.api.User;

public class Main {
    public static void main(String[] args) {
        User user = new User();
        System.out.println(user.displayName());
    }
}
```

Package được export không làm cho mọi thành viên private trở thành public. Quy tắc truy cập của Java vẫn áp dụng.

### 2.2. opens: cho phép reflection truy cập sâu lúc chạy

Nếu framework cần truy cập private field, private constructor hoặc private method bằng reflection, module chứa class cần mở package tương ứng:

```java
module com.example.model {
    exports com.example.model.api;
    opens com.example.model.api to com.example.app;
}
```

- `exports` cho phép `com.example.app` sử dụng API public của package.
- `opens` cho phép reflection từ `com.example.app` truy cập sâu vào các thành viên của package tại runtime.

Hai directive không thay thế nhau. `opens` không tự làm package trở thành API có thể import và dùng trực tiếp khi biên dịch. Ngược lại, `exports` không mặc nhiên cho phép reflection bỏ qua kiểm tra truy cập trên private member.

### 2.3. Qualified exports và qualified opens

Có thể cấp quyền cho một module cụ thể:

```java
module com.example.model {
    exports com.example.model.api to com.example.app;
    opens com.example.model.api to com.example.json;
}
```

Trong ví dụ:

- Chỉ `com.example.app` được dùng API public của package.
- Chỉ `com.example.json` được phép deep reflection vào package.

Cấp quyền theo module đích giúp giới hạn bề mặt truy cập. Không nên mở package rộng cho mọi module nếu chỉ một framework cần sử dụng.

### 2.4. open module mở toàn bộ package cho reflection

Một module có thể khai báo:

```java
open module com.example.model {
    exports com.example.model.api;
}
```

Module dạng `open` mở tất cả package của nó cho deep reflection tại runtime. Tuy nhiên, điều đó không có nghĩa tất cả package tự động được export để module khác truy cập API khi biên dịch.

Vì phạm vi mở rộng, `open module` chỉ phù hợp khi thiết kế thực sự cần reflection sâu trên toàn module. Nếu chỉ một package cần thiết, `opens package to module` thường thể hiện ý định chính xác hơn.

## 3. Ví dụ: exports không đủ để truy cập private field bằng reflection

Giả sử có hai module:

```text
project/
├── com.example.model/
│   ├── module-info.java
│   └── com/example/model/api/User.java
└── com.example.app/
    ├── module-info.java
    └── com/example/app/Main.java
```

Module `com.example.model` export package API:

```java
module com.example.model {
    exports com.example.model.api;
}
```

Class `User`:

```java
package com.example.model.api;

public class User {
    private final String secret = "internal-value";

    public String name() {
        return "An";
    }
}
```

Module ứng dụng:

```java
module com.example.app {
    requires com.example.model;
}
```

Ứng dụng thử truy cập field private:

```java
package com.example.app;

import com.example.model.api.User;
import java.lang.reflect.Field;

public class Main {
    public static void main(String[] args) throws Exception {
        User user = new User();

        System.out.println(user.name()); // API public: hoạt động

        Field secret = User.class.getDeclaredField("secret");
        secret.setAccessible(true);      // Không được mở package: lỗi
        System.out.println(secret.get(user));
    }
}
```

Kết quả mong đợi:

- Lời gọi `user.name()` hoạt động vì package được export và method là public.
- `getDeclaredField("secret")` tìm thấy field.
- `setAccessible(true)` bị từ chối vì package chưa được mở cho module ứng dụng; Java ném `InaccessibleObjectException`.

Để cho phép deep reflection từ `com.example.app`, module model có thể bổ sung:

```java
module com.example.model {
    exports com.example.model.api;
    opens com.example.model.api to com.example.app;
}
```

Sau khi biên dịch và chạy lại với module descriptor này, `setAccessible(true)` có thể bật truy cập vào field private theo quyền mở package.

**Điểm cần nhớ:** `exports` phục vụ API công khai; `opens` phục vụ reflection sâu. Nếu framework cần đọc private field, chỉ thêm `exports` thường chưa đủ.

## 4. IllegalAccessError trong bối cảnh module

Một lỗi truy cập thông thường được phát hiện ngay lúc biên dịch sẽ là lỗi compiler. Ví dụ, module ứng dụng import package không được export có thể bị báo package không hiển thị. `IllegalAccessError` xuất hiện khi việc truy cập không được phát hiện hoặc cấu hình đã thay đổi giữa biên dịch và runtime.

### 4.1. Cấu hình module thay đổi sau khi biên dịch

Giả sử thư viện ban đầu có:

```java
module com.example.library {
    exports com.example.internal;
}
```

Ứng dụng đã biên dịch và sử dụng class public trong package `com.example.internal`.

Sau đó thư viện thay đổi module descriptor:

```java
module com.example.library {
    // com.example.internal không còn được export.
}
```

Nếu ứng dụng cũ vẫn chạy với bytecode tham chiếu đến class trong package đó, JVM có thể ném `IllegalAccessError` khi liên kết hoặc thực thi truy cập.

Đây là ví dụ điển hình về việc **môi trường biên dịch và runtime không còn cùng hợp đồng module**. Việc chỉ thêm `requires com.example.library` không cấp quyền truy cập vào mọi package của thư viện.

### 4.2. Dùng --add-exports ở giai đoạn biên dịch và runtime

Trong một số tình huống chuyển đổi ứng dụng cũ sang module, có thể tạm cấp quyền export bằng tùy chọn dòng lệnh:

```bash
javac --module-path mods \
  --add-exports com.example.library/com.example.internal=com.example.app \
  -d mods/com.example.app \
  src/com.example.app/module-info.java \
  src/com.example.app/com/example/app/Main.java
```

Khi chạy, quyền tương ứng cũng phải có trong cấu hình runtime:

```bash
java --module-path mods \
  --add-exports com.example.library/com.example.internal=com.example.app \
  -m com.example.app/com.example.app.Main
```

`--add-exports` cấp quyền truy cập API công khai của package cho module đích. Nó không cho phép deep reflection vào private member; trường hợp đó cần `opens` hoặc `--add-opens`.

Nếu biên dịch với quyền bổ sung nhưng chạy mà thiếu quyền cần thiết, JVM có thể từ chối truy cập và ném `IllegalAccessError`.

### 4.3. Không nhầm lỗi biên dịch với IllegalAccessError

| Tình huống | Kết quả thường gặp |
|---|---|
| Source code import package của module khác nhưng package không export | Lỗi biên dịch: package không hiển thị |
| Bytecode đã được biên dịch trong môi trường có quyền, nhưng runtime không còn export | Có thể gặp `IllegalAccessError` |
| Reflection gọi `setAccessible(true)` vào private member của package không mở | `InaccessibleObjectException` |
| Reflection gọi `Field.get()` mà không có quyền truy cập và chưa bật accessible | `IllegalAccessException` |

Không nên gọi mọi vấn đề module là `IllegalAccessError`. Hãy xem lỗi xuất hiện ở compiler, ở thao tác reflection hay khi JVM liên kết mã bytecode.

## 5. InaccessibleObjectException và các API reflection

Java Reflection API cung cấp nhiều phương thức kiểm tra và điều chỉnh khả năng truy cập. Cần hiểu sự khác nhau giữa chúng để xử lý đúng.

### 5.1. setAccessible(true)

`AccessibleObject.setAccessible(true)` yêu cầu JVM bỏ qua các kiểm tra truy cập ngôn ngữ Java đối với object reflection đó, trong phạm vi mà module system cho phép.

Ví dụ:

```java
Field field = User.class.getDeclaredField("secret");
field.setAccessible(true);
String value = (String) field.get(user);
```

Nếu package của class khai báo không mở cho module gọi, thao tác `setAccessible(true)` có thể ném `InaccessibleObjectException`.

Phương thức này không phải cách vượt qua mọi giới hạn của module system. Java 17 vẫn áp dụng quy tắc mở package.

### 5.2. trySetAccessible()

Nếu muốn kiểm tra khả năng bật truy cập mà không nhận `InaccessibleObjectException` trong trường hợp package không được mở, dùng `trySetAccessible()`:

```java
Field field = User.class.getDeclaredField("secret");

if (field.trySetAccessible()) {
    String value = (String) field.get(user);
    System.out.println(value);
} else {
    System.out.println("Module chưa mở package cho reflection");
}
```

Kết quả:

- `true`: thao tác bật accessible thành công; có thể tiếp tục dùng reflection theo quyền được cấp.
- `false`: Java không thể bật truy cập theo quy tắc hiện tại; không nên gọi tiếp `get()` như thể đã có quyền.

`trySetAccessible()` đặc biệt hữu ích cho thư viện cần hỗ trợ nhiều môi trường module khác nhau.

### 5.3. canAccess() kiểm tra quyền truy cập hiện tại

`canAccess(Object)` cho biết caller hiện tại có thể truy cập đối tượng reflection hay không, xét theo trạng thái accessible và quy tắc truy cập.

```java
Field field = User.class.getDeclaredField("secret");

boolean accessible = field.canAccess(user);
System.out.println(accessible);
```

Đối với field instance, truyền object đích; với static member, truyền `null`. Phương thức này không tự mở package hoặc bật quyền truy cập.

Có thể kết hợp:

```java
if (!field.canAccess(user) && !field.trySetAccessible()) {
    throw new IllegalStateException("Cannot access field through reflection");
}

String secret = (String) field.get(user);
```

Ví dụ giả định class và object đã được tạo, đồng thời đoạn code nằm trong ngữ cảnh có thể bắt các checked exception do reflection khai báo.

### 5.4. IllegalAccessException là một lỗi khác

Không nên nhầm `InaccessibleObjectException` với `IllegalAccessException`.

Ví dụ, nếu field private không thể truy cập và chưa gọi `setAccessible(true)`, thao tác đọc field có thể ném checked exception:

```java
Field field = User.class.getDeclaredField("secret");

// Không gọi setAccessible/trySetAccessible.
String secret = (String) field.get(user); // IllegalAccessException
```

Trong khi đó:

```java
Field field = User.class.getDeclaredField("secret");
field.setAccessible(true); // InaccessibleObjectException nếu module không mở
```

- `IllegalAccessException`: thao tác reflection như `Field.get()`, `Method.invoke()` hoặc `Constructor.newInstance()` không được phép truy cập thành viên.
- `InaccessibleObjectException`: yêu cầu thay đổi trạng thái accessible bị module system từ chối.

Cả hai đều có thể xuất hiện trong cùng một câu chuyện reflection, nhưng xảy ra ở các bước khác nhau và có cách xử lý khác nhau.

## 6. Strong encapsulation trong Java 17

Java Platform Module System được giới thiệu trong Java 9. Một mục tiêu quan trọng là đóng gói mạnh các package nội bộ của JDK, để ứng dụng chỉ dựa vào API công khai được hỗ trợ.

Trong các phiên bản chuyển tiếp trước Java 17, một số truy cập reflection vào API nội bộ từng có cơ chế tương thích và cảnh báo. Từ Java 17, JEP 403 hoàn tất strong encapsulation của các phần tử nội bộ trong JDK, trừ những package được mở rõ ràng theo cấu hình.

Điều đó có nghĩa:

- Không nên phụ thuộc vào class, field hoặc method nội bộ trong package như `sun.*` hoặc implementation nội bộ của JDK.
- Reflection vào private member của package JDK không mở có thể thất bại với `InaccessibleObjectException`.
- Một thư viện cũ có thể cần nâng cấp nếu nó dùng deep reflection vào JDK internals.
- API công khai được export vẫn có thể dùng bình thường theo hợp đồng của nó.

### 6.1. Ví dụ với private field của String

Trong JDK 17, `String` có field nội bộ tên `value`. Đây là chi tiết triển khai, không phải API mà ứng dụng nên phụ thuộc.

```java
import java.lang.reflect.Field;

public class StringInternals {
    public static void main(String[] args) throws Exception {
        Field value = String.class.getDeclaredField("value");

        System.out.println(value.getName());

        value.setAccessible(true); // Java 17: InaccessibleObjectException
    }
}
```

Có thể tìm thấy field bằng reflection, nhưng không được mặc định có quyền mở nó. Nội bộ của `String` cũng có thể thay đổi giữa các phiên bản JDK; ứng dụng không nên dựa vào kiểu hoặc nội dung của field này.

### 6.2. Không dựa vào --illegal-access

Tùy chọn `--illegal-access` từng hỗ trợ quá trình chuyển đổi module ở các phiên bản JDK trước. Trong Java 17, tùy chọn này không còn cung cấp cơ chế nới lỏng truy cập như trước.

Không nên hướng dẫn người dùng thêm `--illegal-access=permit` để sửa lỗi trên Java 17. Với trường hợp thật sự cần tương thích tạm thời, hãy cấp quyền cụ thể bằng `--add-opens` hoặc `--add-exports`, rồi lên kế hoạch loại bỏ sự phụ thuộc nội bộ.

## 7. --add-opens và --add-exports khác nhau thế nào?

Hai tùy chọn dòng lệnh này thường được nhắc đến khi khắc phục lỗi truy cập module, nhưng chúng có mục đích khác nhau.

| Tùy chọn | Quyền được cấp | Dùng cho |
|---|---|---|
| `--add-exports module/package=target` | Export package cho module đích | Truy cập API public của package chưa export |
| `--add-opens module/package=target` | Open package cho module đích | Deep reflection vào thành viên không public lúc runtime |

### 7.1. Ví dụ --add-opens

Để cho phép ứng dụng classpath (unnamed module) reflection sâu vào package `java.lang` của `java.base`, có thể chạy:

```bash
java --add-opens java.base/java.lang=ALL-UNNAMED \
  -cp out demo.StringReflectionDemo
```

Nếu ứng dụng là named module, chỉ định tên module đích:

```bash
java --add-opens java.base/java.lang=com.example.app \
  --module-path mods \
  -m com.example.app/com.example.app.Main
```

`--add-opens` là quyền ở runtime; nó không làm package trở thành API có thể import khi biên dịch.

### 7.2. Ví dụ --add-exports

Khi cần truy cập một API public trong package không export, có thể cấp quyền export có mục tiêu:

```bash
java --add-exports java.base/sun.nio.ch=ALL-UNNAMED \
  -cp out demo.LegacyApplication
```

Đây là ví dụ về cơ chế cấp quyền, không phải khuyến nghị phụ thuộc vào `sun.nio.ch`. Các package nội bộ có thể thay đổi hoặc biến mất; nên chuyển sang API công khai được hỗ trợ.

### 7.3. Chỉ cấp quyền cần thiết

Nếu framework `com.example.json` cần reflection vào package model, ưu tiên mở đúng package cho đúng module:

```java
module com.example.model {
    opens com.example.model.dto to com.example.json;
}
```

Tránh mở toàn bộ JDK hoặc toàn bộ ứng dụng cho `ALL-UNNAMED` nếu chỉ một module cụ thể cần quyền. Quyền càng rộng thì ranh giới đóng gói càng yếu.

## 8. Cách nhận diện lỗi từ stack trace

Khi gặp lỗi truy cập, hãy đọc loại exception/error và dòng đầu tiên thuộc code ứng dụng hoặc thư viện.

### 8.1. Dấu hiệu của IllegalAccessError

Stack trace có thể bắt đầu:

```text
java.lang.IllegalAccessError: class com.example.app.Main
cannot access class com.example.internal.Secret
because module com.example.library does not export
com.example.internal to module com.example.app
```

Thông điệp cụ thể phụ thuộc JDK và hoàn cảnh, nhưng thường liên quan đến truy cập trực tiếp vào class/member không được phép.

Hướng điều tra:

1. Xác định class/member được nhắc trong thông báo.
2. Tìm module sở hữu package đó.
3. Kiểm tra `module-info.java` của module sở hữu.
4. Xác định package có được export cho module gọi không.
5. So sánh cấu hình module lúc compile với lúc runtime.
6. Kiểm tra các tùy chọn `--add-exports` được truyền vào cả hai giai đoạn nếu đang dùng giải pháp tương thích.

### 8.2. Dấu hiệu của InaccessibleObjectException

Stack trace có thể có dạng:

```text
java.lang.reflect.InaccessibleObjectException:
Unable to make field private ... accessible:
module java.base does not "opens java.lang" to
unnamed module ...
```

Dấu hiệu thường gặp:

- Có `java.lang.reflect.InaccessibleObjectException`.
- Stack trace đi qua `AccessibleObject.setAccessible(...)` hoặc `trySetAccessible()`.
- Thông báo nói module không `opens` package cho module gọi.

Hướng điều tra:

1. Xác định field/method/constructor mà thư viện muốn truy cập.
2. Xác định module chứa class khai báo thành viên.
3. Xác định module gọi reflection.
4. Kiểm tra package có được `opens` cho module gọi hay không.
5. Ưu tiên API công khai hoặc phiên bản thư viện không cần deep reflection.
6. Chỉ dùng `--add-opens` có mục tiêu nếu chưa thể loại bỏ phụ thuộc.

### 8.3. Dấu hiệu của IllegalAccessException

Nếu stack trace báo `java.lang.IllegalAccessException`, hãy kiểm tra thao tác reflection thực tế (`Field.get`, `Method.invoke`, `Constructor.newInstance`) và trạng thái `canAccess()`. Đây là checked exception từ API reflection, khác với lỗi bật accessible.

## 9. Cách khắc phục theo nguyên nhân

Không có một cờ JVM duy nhất giải quyết mọi lỗi truy cập. Hãy chọn cách sửa đúng với loại truy cập.

### 9.1. Khi gặp IllegalAccessError

- Đảm bảo module chứa package đã export package đó cho module gọi.
- Nếu API không nên được dùng trực tiếp, thay bằng public API được hỗ trợ.
- Kiểm tra module descriptor và cấu hình module path trong môi trường chạy.
- Nếu dùng `--add-exports` để chuyển tiếp, truyền quyền phù hợp ở runtime và cả compile nếu compiler cần.
- Cập nhật hoặc biên dịch lại thư viện phụ thuộc nếu nó được tạo với giả định module cũ.

Ví dụ module descriptor:

```java
module com.example.library {
    exports com.example.publicapi;
}
```

Ứng dụng chỉ nên sử dụng class trong package `com.example.publicapi` nếu đó là API mà thư viện cam kết hỗ trợ.

### 9.2. Khi gặp InaccessibleObjectException

- Kiểm tra framework có phiên bản hỗ trợ Java 17 và JPMS hay không.
- Nếu đang reflection vào class của ứng dụng, mở package cần thiết bằng `opens package to framework.module`.
- Nếu truy cập một JDK internal package, tìm API công khai thay thế.
- Nếu cần giải pháp chuyển tiếp, dùng `--add-opens` cho đúng module/package/target.
- Không gọi `setAccessible(true)` một cách vô điều kiện; dùng `trySetAccessible()` khi quyền có thể khác nhau giữa môi trường.

### 9.3. Khi gặp IllegalAccessException

- Kiểm tra member có `public` hay không và class/package có cho phép truy cập hay không.
- Kiểm tra caller có đúng module/package theo quy tắc Java không.
- Nếu thật sự cần deep reflection, kiểm tra `opens` và dùng `trySetAccessible()`.
- Nếu không cần reflection sâu, sử dụng method hoặc constructor public.

## 10. Thiết kế module để hạn chế lỗi truy cập

Một module tốt nên công bố API nhỏ, rõ ràng và giữ implementation ở package không export.

Ví dụ:

```java
module com.example.billing {
    exports com.example.billing.api;
}
```

Cấu trúc package:

```text
com.example.billing
├── api
│   ├── InvoiceService.java
│   └── Invoice.java
└── internal
    ├── InvoiceRepository.java
    └── TaxCalculator.java
```

Các module khác chỉ truy cập package `api`. Package `internal` không được export nên không phải API công khai.

Nếu một framework cần reflection vào DTO hoặc entity, chỉ mở package đó:

```java
module com.example.billing {
    exports com.example.billing.api;
    opens com.example.billing.api to com.example.json;
}
```

Không cần mở toàn bộ package `internal` chỉ vì một framework cần đọc một vài field DTO.

### 10.1. Ưu tiên constructor, accessor và public API

Nếu ứng dụng tự thiết kế class, hãy cung cấp API rõ ràng thay vì bắt thư viện truy cập private field bằng reflection:

```java
package com.example.billing.api;

public final class Invoice {
    private final String number;

    public Invoice(String number) {
        this.number = number;
    }

    public String number() {
        return number;
    }
}
```

Framework hoặc caller có thể dùng constructor và accessor công khai. Nếu thư viện hỗ trợ constructor binding hoặc record binding, đây thường là hướng ít phụ thuộc implementation hơn.

### 10.2. Chỉ mở package cho framework thật sự cần

Một số framework serialization, dependency injection, ORM hoặc testing có thể cần reflection. Khi đó, module descriptor nên nêu rõ module đích:

```java
module com.example.domain {
    exports com.example.domain.api;
    opens com.example.domain.entity to org.example.orm;
}
```

Tên module framework phải khớp tên module thực tế của dependency. Nếu thư viện chạy trên classpath, caller có thể là unnamed module; khi đó `ALL-UNNAMED` chỉ nên dùng như cấu hình tương thích có phạm vi được cân nhắc.

## 11. Công cụ hỗ trợ điều tra

### 11.1. Kiểm tra module descriptor

Dùng `jar --describe-module` để xem descriptor của một JAR:

```bash
jar --describe-module --file library.jar
```

Kết quả cho biết tên module, các package được export/open và các yêu cầu module. Đây là bước hữu ích khi source code của dependency không có sẵn.

### 11.2. Phân tích phụ thuộc vào JDK internals bằng jdeps

```bash
jdeps --jdk-internals application.jar
```

`jdeps --jdk-internals` giúp phát hiện tham chiếu tĩnh đến API nội bộ của JDK trong artifact được phân tích. Công cụ không phát hiện được mọi hành vi reflection được tạo động, nhưng có thể chỉ ra nhiều dependency cần thay thế trước khi nâng cấp JDK.

### 11.3. Tìm tên module và package

Khi thông báo lỗi nói package không mở hoặc không export, cần xác định chính xác:

- Module chứa class đích.
- Package chứa member.
- Module thực hiện truy cập.
- Package đó đang `exports`, `opens` hay không có directive nào.

Có thể dùng `jar --describe-module`, module descriptor trong source và stack trace để ghép các thông tin này.

## 12. Những hiểu nhầm thường gặp

### 12.1. Cả hai đều là IllegalAccessException

Sai. `IllegalAccessError` là `Error`, `InaccessibleObjectException` là `RuntimeException`, còn `IllegalAccessException` là checked exception.

### 12.2. Thêm exports là reflection được private field

Sai. `exports` cho phép truy cập API công khai; deep reflection vào private member cần package được mở (`opens`).

### 12.3. Thêm opens là code có thể import class ở package đó

Sai. `opens` phục vụ reflection tại runtime. Muốn dùng public type trực tiếp từ module khác, package phải được export.

### 12.4. setAccessible(true) luôn hoạt động nếu field tồn tại

Sai. Module system có thể từ chối yêu cầu bỏ qua access checks và ném `InaccessibleObjectException`.

### 12.5. trySetAccessible() ném cùng exception

Không trong trường hợp không thể bật quyền truy cập theo quy tắc module: phương thức trả về `false`. Nó được thiết kế để caller kiểm tra khả năng trước khi đọc/invoke.

### 12.6. IllegalAccessError chỉ xảy ra khi dùng reflection

Sai. Đây là lỗi liên kết có thể xảy ra với truy cập trực tiếp từ bytecode, chẳng hạn khi module không export package ở runtime.

### 12.7. InaccessibleObjectException chỉ xảy ra với class của JDK

Sai. Nó có thể xảy ra với class trong ứng dụng hoặc thư viện của bên thứ ba nếu package không mở cho module thực hiện deep reflection.

### 12.8. --add-opens và --add-exports giống nhau

Sai. Một cái mở deep reflection; cái còn lại export API public. Dùng sai tùy chọn sẽ không giải quyết đúng vấn đề.

### 12.9. Mọi lỗi truy cập đều nên catch rồi bỏ qua

Sai. Bỏ qua có thể làm chương trình tiếp tục với dữ liệu thiếu hoặc trạng thái sai. Hãy sửa hợp đồng module hoặc thiết kế API.

### 12.10. --illegal-access=permit là cách sửa cho Java 17

Sai. Trong Java 17, tùy chọn này không còn cung cấp cơ chế nới lỏng truy cập như các phiên bản chuyển tiếp trước đó. Hãy dùng `opens` hoặc `--add-opens` có mục tiêu nếu thật sự cần deep reflection.

## 13. Bảng quyết định nhanh

| Dấu hiệu | Chẩn đoán ưu tiên | Hướng xử lý |
|---|---|---|
| `IllegalAccessError` khi gọi class/member từ package khác module | Package không được export hoặc cấu hình runtime không giống compile | Kiểm tra `exports`, module path và `--add-exports` |
| `InaccessibleObjectException` tại `setAccessible(true)` | Package không được mở cho module reflection | Kiểm tra `opens`, `--add-opens`, hoặc bỏ deep reflection |
| `trySetAccessible()` trả `false` | Java không cho phép bật quyền truy cập sâu | Dùng public API hoặc mở package có mục tiêu |
| `IllegalAccessException` tại `Field.get()`/`Method.invoke()` | Access check của reflection thất bại | Kiểm tra `canAccess`, `opens` và cách truy cập |
| Lỗi compiler báo package không visible | Package chưa export trong module descriptor | Sửa `exports` hoặc dùng API public khác |

## 14. Bài tập tự luyện

### Bài 1. Phân biệt loại lỗi

Một thư viện gọi `field.setAccessible(true)` trên private field của class trong module không mở package.

**Câu hỏi:** Lỗi nào có thể xuất hiện?

**Đáp án:** `InaccessibleObjectException`, vì yêu cầu bỏ qua access checks bị module system từ chối.

### Bài 2. Truy cập trực tiếp vào package không export

Một ứng dụng đã biên dịch khi package thư viện được export, nhưng runtime dùng module descriptor không còn export package đó.

**Câu hỏi:** Lỗi nào có thể xuất hiện khi JVM liên kết truy cập?

**Đáp án:** `IllegalAccessError`, vì bytecode yêu cầu truy cập class/member không được phép trong môi trường runtime hiện tại.

### Bài 3. Chọn directive

Một framework `com.example.json` cần đọc private field trong package `com.example.model.dto`. Cần dùng directive nào?

**Đáp án:** `opens com.example.model.dto to com.example.json;`. Nếu ứng dụng cũng cần import và gọi public API trong package đó, thêm `exports` riêng.

### Bài 4. Kiểm tra reflection an toàn hơn

Hoàn thiện đoạn code để chỉ đọc field nếu có thể bật accessible:

```java
Field field = User.class.getDeclaredField("secret");

if (field.trySetAccessible()) {
    System.out.println(field.get(user));
} else {
    System.out.println("Access is not available");
}
```

**Đáp án:** Đoạn code đã hoàn chỉnh. `trySetAccessible()` trả `true` khi bật được quyền, `false` khi không thể. Phương thức `get()` vẫn có thể ném `IllegalAccessException` và cần xử lý theo chữ ký của method chứa đoạn code.

### Bài 5. exports hay opens?

Một module cần cho module khác gọi method public `User.name()`, không cần truy cập private field.

**Đáp án:** `exports` package chứa `User` là đủ nếu các quy tắc truy cập Java khác được thỏa mãn. Không cần mở package cho deep reflection.

### Bài 6. Phân biệt IllegalAccessException

`Field.get(user)` ném `IllegalAccessException` khi field private chưa được mở accessible.

**Câu hỏi:** Đây có phải `InaccessibleObjectException` không?

**Đáp án:** Không. `IllegalAccessException` phát sinh khi thao tác đọc field không được phép; `InaccessibleObjectException` phát sinh khi yêu cầu bật bỏ qua kiểm tra truy cập bị từ chối.

### Bài 7. Chọn tùy chọn JVM

Một thư viện cũ trên classpath cần deep reflection vào package `java.base/java.lang` trong lúc chuyển đổi ứng dụng.

**Đáp án:** Có thể dùng `--add-opens java.base/java.lang=ALL-UNNAMED` như biện pháp tương thích tạm thời. Nên nâng cấp hoặc thay thư viện để loại bỏ phụ thuộc vào JDK internals.

### Bài 8. Tại sao không dùng --illegal-access=permit?

**Đáp án:** Trong Java 17, tùy chọn này không còn cung cấp cơ chế nới lỏng truy cập như các phiên bản chuyển tiếp trước đó. Dùng `opens` hoặc `--add-opens` có mục tiêu nếu thật sự cần deep reflection.

## 15. Tài liệu tham khảo chính thức

- [JDK 17 API — InaccessibleObjectException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/InaccessibleObjectException.html): exception khi không thể bỏ qua access checks bằng reflection.
- [JDK 17 API — AccessibleObject](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AccessibleObject.html): `setAccessible`, `trySetAccessible`, `canAccess` và quy tắc module.
- [JDK 17 API — IllegalAccessError](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/IllegalAccessError.html): lỗi liên kết khi truy cập class/member không được phép.
- [JDK 17 API — IllegalAccessException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/IllegalAccessException.html): checked exception từ thao tác reflection không được phép.
- [Java Language Specification 17 — Modules](https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html): khai báo module, `requires`, `exports` và `opens`.
- [JDK 17 API — Module](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html): API runtime để kiểm tra và thao tác thông tin module.
- [OpenJDK JEP 403 — Strongly Encapsulate JDK Internals](https://openjdk.org/jeps/403): strong encapsulation được áp dụng trong Java 17 và trạng thái của `--illegal-access`.
- [OpenJDK JEP 261 — Module System](https://openjdk.org/jeps/261): thiết kế hệ thống module của Java.

**Ghi nhớ:** `IllegalAccessError` là lỗi liên kết khi bytecode truy cập class/member không được phép trong runtime. `InaccessibleObjectException` là lỗi runtime khi reflection yêu cầu bỏ qua kiểm tra truy cập nhưng package không được mở. `exports` cấp quyền dùng API public; `opens` cấp quyền deep reflection. Khi điều tra, hãy xác định module sở hữu package, module gọi, loại thao tác truy cập và cấu hình runtime trước khi chọn cách sửa.
