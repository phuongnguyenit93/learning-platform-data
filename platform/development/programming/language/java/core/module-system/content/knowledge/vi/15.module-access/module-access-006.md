# IllegalAccessError, IllegalAccessException và InaccessibleObjectException

Ba kiểu lỗi này đều liên quan đến quyền truy cập class, method, field hoặc constructor trong Java, nhưng chúng xuất hiện ở những thời điểm khác nhau và có cách xử lý khác nhau. Khi làm việc với Java Platform Module System (JPMS), cần phân biệt quyền truy cập thông thường của Java, quyền truy cập giữa các module và quyền truy cập sâu qua reflection.

- `IllegalAccessError` là một **Error** xảy ra khi JVM thực thi hoặc liên kết bytecode nhưng phát hiện code không có quyền truy cập.
- `IllegalAccessException` là một **checked exception**, thường gặp khi reflection cố gọi hoặc đọc một thành viên mà caller không được phép truy cập.
- `InaccessibleObjectException` là một **unchecked exception** xuất hiện khi reflection cố bật quyền truy cập bị hạn chế, thường do package của module không được mở cho module đang gọi.

## 1. So sánh nhanh

| Đặc điểm | IllegalAccessError | IllegalAccessException | InaccessibleObjectException |
|---|---|---|---|
| Loại | Error | Checked exception | Unchecked exception |
| Phân cấp | `IncompatibleClassChangeError → LinkageError → Error` | `ReflectiveOperationException → Exception` | `RuntimeException` |
| Thời điểm thường gặp | JVM liên kết hoặc thực thi bytecode | Reflection thực hiện thao tác nhưng access check thất bại | Reflection gọi `setAccessible(true)` nhưng module không cho phép |
| Ngữ cảnh phổ biến | Truy cập class/member không được export hoặc thay đổi quyền truy cập sau khi biên dịch | `Field.get`, `Method.invoke`, `Constructor.newInstance` | `AccessibleObject.setAccessible` |
| Cách xử lý chính | Sửa module descriptor, module graph hoặc quyền truy cập binary | Kiểm tra quyền truy cập; dùng API công khai hoặc mở package nếu cần reflection sâu | Dùng API công khai, khai báo `opens` hoặc cấu hình `--add-opens` phù hợp |

Không nên bắt cả ba loại bằng một khối catch chung rồi bỏ qua. Chúng biểu thị ba tình huống khác nhau: lỗi liên kết bytecode, thao tác reflection bị từ chối và yêu cầu reflection sâu không được module cho phép.

## 2. IllegalAccessError

`IllegalAccessError` thuộc nhóm `LinkageError`. JVM ném lỗi này khi code đã được biên dịch tham chiếu tới một class hoặc thành viên, nhưng tại thời điểm chạy, quyền truy cập thực tế không cho phép thao tác đó.

Một số nguyên nhân thường gặp:

- Một class hoặc member từng là public nhưng thư viện được thay thế bằng phiên bản đã giảm quyền truy cập.
- Code được biên dịch khi package được export, nhưng module descriptor tại runtime không còn export package đó cho module gọi.
- Ứng dụng được biên dịch với tùy chọn `--add-exports` nhưng khi chạy lại thiếu cấu hình export tương ứng.
- Một module có thể đọc module khác nhưng package cần dùng không được export cho module gọi.

### Ví dụ với JPMS

Giả sử thư viện khai báo module:

```java
module com.acme.library {
    // Package com.acme.library.internal không được export.
}
```

Một ứng dụng khác có thể khai báo:

```java
module com.acme.application {
    requires com.acme.library;
}
```

Mệnh đề `requires` tạo quan hệ readability: module ứng dụng có thể đọc module thư viện. Tuy nhiên, điều đó không tự động làm mọi package của thư viện trở nên accessible. Nếu bytecode của ứng dụng tham chiếu tới class trong `com.acme.library.internal` mà package này không được export cho ứng dụng, JVM có thể ném `IllegalAccessError` khi liên kết hoặc thực thi tham chiếu đó.

Để cho phép truy cập trực tiếp tới các kiểu public trong package, module thư viện có thể export package:

```java
module com.acme.library {
    exports com.acme.library.api;
    exports com.acme.library.internal to com.acme.application;
}
```

Dòng thứ hai là **qualified export**: chỉ module `com.acme.application` được truy cập trực tiếp các kiểu public trong package internal. Nếu package chỉ dành cho một module cụ thể, cách này giúp giới hạn phạm vi API được công khai.

Trong tình huống cần kiểm tra nhanh hoặc tương thích với thư viện chưa thể sửa, có thể dùng tùy chọn launcher:

```bash
java --add-exports=com.acme.library/com.acme.library.internal=com.acme.application \
     -m com.acme.application/com.acme.application.Main
```

Nếu cần biên dịch code tham chiếu package chưa export, cấu hình `--add-exports` tương ứng cũng phải được truyền cho compiler. Cấu hình ở thời điểm biên dịch và runtime cần nhất quán.

`IllegalAccessError` thường chỉ ra module descriptor, phiên bản thư viện hoặc cấu hình module path ở runtime không khớp với giả định khi biên dịch. Hãy kiểm tra class và member được truy cập, module chứa chúng, package có được export cho caller hay không và các tùy chọn JVM thực tế.

## 3. IllegalAccessException

`IllegalAccessException` là checked exception trong nhóm `ReflectiveOperationException`. Nó thường xuất hiện khi một thao tác reflection cố đọc field, gọi method hoặc tạo object qua constructor mà caller không có quyền truy cập.

Ví dụ, một class có field private:

```java
package com.acme.model;

public class Account {
    private String secret = "internal-value";
}
```

Một class khác thử đọc field bằng reflection:

```java
import java.lang.reflect.Field;
import com.acme.model.Account;

public class ReflectionExample {
    public static void main(String[] args) throws Exception {
        Account account = new Account();

        Field field = Account.class.getDeclaredField("secret");
        Object value = field.get(account); // IllegalAccessException
    }
}
```

`getDeclaredField` tìm được field, kể cả khi field là private. Tuy nhiên, tìm thấy thành viên không đồng nghĩa với việc caller được phép đọc nó. Khi `field.get(account)` thực hiện access check, Java có thể ném `IllegalAccessException`.

Các thao tác reflection thường có thể ném lỗi này gồm:

- `Field.get` và `Field.set` khi caller không được phép đọc hoặc ghi field.
- `Method.invoke` khi caller không được phép gọi method.
- `Constructor.newInstance` khi caller không được phép gọi constructor.
- Một số thao tác tra cứu hoặc gọi method handle thông qua `MethodHandles.Lookup` khi lookup không có đủ quyền.

### Cách xử lý

Ưu tiên dùng API công khai được class hoặc thư viện cung cấp. Nếu thực sự cần reflection, hãy xác định quyền truy cập của member và của class chứa member.

Trong trường hợp package đã được module mở cho module gọi, có thể bật quyền truy cập sâu trước khi đọc field:

```java
Field field = Account.class.getDeclaredField("secret");

if (field.trySetAccessible()) {
    Object value = field.get(account);
    System.out.println(value);
} else {
    System.out.println("Không thể bật quyền truy cập field");
}
```

`trySetAccessible()` trả về `true` nếu có thể bật quyền truy cập và `false` nếu không thể. Phương thức này được bổ sung từ Java 9. Nếu bỏ qua bước bật quyền truy cập hoặc bước đó không thành công, thao tác reflection tiếp theo vẫn có thể ném `IllegalAccessException`.

Một lưu ý quan trọng với `Method.invoke`: nếu method đích tự ném exception, reflection thường bọc exception đó trong `InvocationTargetException`. Đây là lỗi khác với `IllegalAccessException`, vốn biểu thị caller không được phép gọi method.

## 4. InaccessibleObjectException

`InaccessibleObjectException` là unchecked exception thuộc `java.lang.reflect`, được bổ sung từ Java 9 cùng với hệ thống module. Nó xuất hiện khi code yêu cầu reflection bỏ qua access check nhưng JPMS không cho phép mở quyền đó.

Ví dụ, ứng dụng muốn đọc field private của `Account`:

```java
Field field = Account.class.getDeclaredField("secret");
field.setAccessible(true); // Có thể ném InaccessibleObjectException
```

Nếu `com.acme.model` là package trong một named module và module đó không mở package cho module của ứng dụng, lời gọi `setAccessible(true)` có thể thất bại bằng `InaccessibleObjectException`.

Điểm khác biệt với `IllegalAccessException` là thời điểm lỗi:

- `IllegalAccessException` xảy ra khi thao tác reflection thực tế bị access check từ chối.
- `InaccessibleObjectException` xảy ra ngay khi yêu cầu bật chế độ bỏ qua access check không được chấp nhận.

### Vì sao exports chưa đủ?

Trong JPMS, `exports` và `opens` phục vụ hai mục đích khác nhau:

- `exports` cho phép module khác truy cập các kiểu public trong package theo quy tắc truy cập Java thông thường.
- `opens` cho phép reflection truy cập sâu vào các thành viên, kể cả private, của package tại runtime.

Vì vậy, export một package không có nghĩa là cho phép framework truy cập private field bằng `setAccessible(true)`. Khi cần reflection sâu, module chứa class phải mở package cho module đang gọi.

### Mở package bằng module-info.java

Có thể mở một package cho tất cả module khác:

```java
module com.acme.model {
    exports com.acme.model.api;
    opens com.acme.model.internal;
}
```

Hoặc chỉ mở package cho một framework cụ thể:

```java
module com.acme.model {
    opens com.acme.model.internal to com.acme.framework;
}
```

Đây là **qualified opens**. Chỉ module được nêu trong khai báo mới được cấp quyền reflection sâu đối với package đó.

Nếu cần mở mọi package của module cho reflection, có thể khai báo module là open module:

```java
open module com.acme.model {
    requires java.sql;
}
```

Một open module mở tất cả package cho reflection tại runtime. Không cần và không được kết hợp từ khóa `open` với các khai báo `opens` riêng trong cùng module descriptor. Hãy chỉ chọn phạm vi mở rộng cần thiết.

### Dùng --add-opens khi chạy

Khi không thể sửa module descriptor của thư viện, có thể mở package bằng tùy chọn JVM:

```bash
java --add-opens=com.acme.model/com.acme.model.internal=com.acme.framework \
     -m com.acme.application/com.acme.application.Main
```

Nếu code reflection chạy trong classpath, caller thuộc unnamed module. Khi đó có thể dùng:

```bash
java --add-opens=com.acme.model/com.acme.model.internal=ALL-UNNAMED \
     -jar application.jar
```

`--add-opens` là cấu hình mở package cho reflection ở runtime. Nó không thay thế `--add-exports` để cho phép code thông thường tham chiếu trực tiếp tới kiểu public trong package chưa export.

## 5. Đặt ba lỗi vào cùng một tình huống

Giả sử module `com.acme.model` chứa class `com.acme.model.internal.Account` với field private `secret`. Module `com.acme.application` cần làm việc với class đó.

| Thao tác | Kết quả có thể gặp | Lý do |
|---|---|---|
| Bytecode truy cập trực tiếp class trong package không export | `IllegalAccessError` | JVM từ chối quyền truy cập giữa module |
| Reflection gọi `field.get(account)` mà chưa bật quyền truy cập và access check thất bại | `IllegalAccessException` | Reflection không có quyền đọc field |
| Reflection gọi `field.setAccessible(true)` trong khi package chưa được mở | `InaccessibleObjectException` | JPMS không cho phép bỏ qua access check |

Một module có thể đồng thời cần cả quyền truy cập trực tiếp và reflection sâu. Khi đó, hãy xác định đúng mục tiêu:

- Truy cập public API từ module khác: dùng `requires` và `exports`.
- Reflection vào private member: dùng `opens`.
- Truy cập package nội bộ bằng bytecode: xem lại ranh giới module; nếu thật sự cần, dùng qualified export.
- Reflection vào package nội bộ của module khác: mở package có giới hạn cho module framework cần dùng.

## 6. Quy trình xử lý khi gặp lỗi

### Bước 1: Xác định lỗi và dòng phát sinh

Đọc tên exception/error đầy đủ và stack trace. Xác định lỗi xuất hiện ở thao tác liên kết bytecode, gọi reflection hay bật quyền truy cập reflection.

Không suy luận chỉ từ tên class được truy cập. Cùng một class có thể gây ra các lỗi khác nhau tùy thao tác và cấu hình module.

### Bước 2: Xác định module của caller và module chứa class

Kiểm tra:

- Class đang chạy thuộc named module hay unnamed module.
- Class đích thuộc module nào.
- Package đích có được export cho caller hay không.
- Package đích có được open cho caller hay không.
- Module caller đã đọc module đích bằng `requires` hay chưa.

Có thể dùng lệnh sau để xem thông tin module trong JAR:

```bash
jar --describe-module --file libs/model.jar
```

Với module đang chạy, tùy chọn `--show-module-resolution` có thể giúp quan sát quá trình phân giải module:

```bash
java --show-module-resolution -m com.acme.application/com.acme.application.Main
```

### Bước 3: Chọn đúng cơ chế

- Nếu gặp `IllegalAccessError`, kiểm tra quyền truy cập của bytecode, các khai báo `exports`, module path và cấu hình `--add-exports`.
- Nếu gặp `IllegalAccessException`, kiểm tra quyền truy cập thông thường của reflection và xem có thực sự cần bật quyền truy cập sâu hay không.
- Nếu gặp `InaccessibleObjectException`, kiểm tra package đã được mở cho đúng module caller chưa; cân nhắc `opens` hoặc `--add-opens`.

### Bước 4: Ưu tiên sửa ở ranh giới API

Nếu một ứng dụng thường xuyên phải truy cập private field của module khác, đó có thể là dấu hiệu API chưa cung cấp thao tác cần thiết. Hãy cân nhắc bổ sung method hoặc interface công khai phù hợp, thay vì mở toàn bộ package nội bộ.

Nếu framework cần reflection để thực hiện dependency injection, serialization hoặc mapping, hãy mở đúng package cho đúng module framework. Hạn chế dùng `ALL-UNNAMED` hoặc mở toàn module khi chỉ một package và một caller cần quyền.

### Bước 5: Kiểm tra cả compile-time và runtime

Tùy chọn dùng khi biên dịch không tự động được giữ lại khi chạy ứng dụng. Kiểm tra lệnh build, cấu hình plugin, module path và lệnh launcher thực tế. Sau khi sửa, chạy lại đúng cách triển khai ứng dụng để xác nhận lỗi đã hết.

## 7. Những nhầm lẫn thường gặp

- **Cho rằng `requires` đồng nghĩa với quyền truy cập mọi package:** `requires` tạo readability, còn `exports` kiểm soát truy cập trực tiếp tới public types của package.
- **Cho rằng `exports` cho phép reflection vào private member:** cần `opens` cho reflection sâu.
- **Dùng `--add-opens` để sửa `IllegalAccessError` khi truy cập bytecode:** `--add-opens` dành cho reflection; truy cập trực tiếp cần export package thích hợp.
- **Dùng `--add-exports` để sửa `InaccessibleObjectException`:** export package không cấp quyền bỏ qua access check đối với private member.
- **Cho rằng `setAccessible(true)` luôn thành công:** từ Java 9, strong encapsulation của JPMS có thể từ chối yêu cầu và ném `InaccessibleObjectException`.
- **Bắt `IllegalAccessError` như một checked exception:** đây là Error thuộc nhóm linkage, không phải `IllegalAccessException`.
- **Nhầm exception của method đích với lỗi quyền truy cập:** exception do method được gọi ném ra thường được bọc trong `InvocationTargetException`.

## 8. Checklist chẩn đoán

Khi xử lý một trong ba lỗi, hãy kiểm tra:

- [ ] Đã xác định chính xác là `IllegalAccessError`, `IllegalAccessException` hay `InaccessibleObjectException`.
- [ ] Đã xác định module caller và module chứa class hoặc member đích.
- [ ] Đã kiểm tra `requires` để bảo đảm caller đọc được module cần dùng.
- [ ] Đã kiểm tra `exports` nếu code cần truy cập trực tiếp public type.
- [ ] Đã kiểm tra `opens` nếu framework cần reflection sâu.
- [ ] Đã chọn đúng `--add-exports` hoặc `--add-opens` cho trường hợp tương ứng.
- [ ] Đã kiểm tra cấu hình ở cả lúc biên dịch và runtime.
- [ ] Đã cân nhắc dùng public API thay cho truy cập nội bộ bằng reflection.

Hãy bắt đầu từ thao tác gây lỗi và quyền mà thao tác đó cần. Khi phân biệt rõ truy cập bytecode, reflection thông thường và reflection sâu, việc chọn giữa `exports`, `opens`, `--add-exports` và `--add-opens` sẽ chính xác hơn, đồng thời giúp giữ ranh giới module rõ ràng.