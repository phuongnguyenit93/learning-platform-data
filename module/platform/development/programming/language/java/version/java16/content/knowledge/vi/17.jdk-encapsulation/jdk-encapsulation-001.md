# Strong encapsulation mặc định từ Java 16 và ý nghĩa của JEP 396

Java 16 thay đổi cách JDK đóng gói các API nội bộ: **strong encapsulation trở thành mặc định**. Các package nội bộ vốn từng có thể được truy cập nhờ cơ chế tương thích của các phiên bản JDK trước không còn tự động mở cho mã ứng dụng. Đây là thay đổi được mô tả trong JEP 396.

Điều này làm rõ ranh giới giữa API công khai được Java hỗ trợ và chi tiết triển khai nội bộ của JDK. Ứng dụng nên dùng API công khai, được tài liệu hóa. Nếu thư viện cũ cần truy cập nội bộ để hoạt động, hãy xác định package và mục đích truy cập cụ thể, sau đó lập kế hoạch di trú. Các cờ mở quyền truy cập rộng chỉ nên được xem là biện pháp chuyển tiếp.

Trong Java 17, JEP 403 tiếp tục hoàn tất quá trình đóng gói mạnh các internals của JDK. Vì vậy, khi phát triển hoặc nâng cấp ứng dụng hiện đại, không nên dựa vào cách mở lại hàng loạt package nội bộ từng tồn tại ở các JDK cũ.

## 1. Strong encapsulation là gì?

Encapsulation (đóng gói) giới hạn những thành phần mà mã bên ngoài có thể truy cập. Trong Java Platform Module System (JPMS), một module có thể khai báo package nào được công khai cho module khác và package nào được mở cho reflection.

JDK cũng được chia thành các module như:

- `java.base`: các API nền tảng như `java.lang`, `java.util`, `java.io` và nhiều package cốt lõi.
- `java.sql`: API JDBC.
- `java.logging`: API logging.
- `java.net.http`: HTTP Client API.
- `jdk.unsupported`: một số API nội bộ quan trọng còn được duy trì vì lý do tương thích.

Một package thuộc module JDK có thể là:

- **Exported package:** các kiểu public trong package được module khác truy cập theo quy tắc JPMS.
- **Open package:** mã khác được phép dùng reflection sâu để truy cập thành viên không public theo các quy tắc truy cập của Java.
- **Non-exported và non-open package:** mã bên ngoài không được truy cập trực tiếp như một API module thông thường, cũng không được tự do dùng deep reflection vào package đó.

Strong encapsulation nghĩa là ranh giới module được thực thi rõ ràng ở compile time và runtime. Một lớp nằm trong JDK không mặc nhiên là API công khai chỉ vì nó có thể được tìm thấy trong thư viện runtime hoặc tên package trông có vẻ quen thuộc.

## 2. Vì sao JDK cần đóng gói các API nội bộ?

Trước hệ thống module, nhiều ứng dụng và thư viện đã truy cập các lớp không phải API công khai của JDK. Chúng có thể gọi trực tiếp các lớp trong package nội bộ hoặc dùng reflection để sửa trạng thái bên trong đối tượng JDK.

Cách làm này tạo ra một số vấn đề:

- **Phụ thuộc implementation:** mã ứng dụng gắn với cách JDK hiện thực một tính năng thay vì hợp đồng API công khai.
- **Khó nâng cấp:** JDK có thể thay đổi hoặc xóa lớp nội bộ mà không phải giữ tương thích như API công khai.
- **Khó bảo trì:** thư viện bên thứ ba phải xử lý khác biệt giữa nhiều phiên bản và nhà cung cấp JDK.
- **Khó tối ưu:** JDK bị hạn chế khi thay đổi cấu trúc nội bộ vì ứng dụng đang dựa vào chi tiết không được hỗ trợ.
- **Khó kiểm soát reflection:** framework có thể truy cập sâu vào trường và phương thức nội bộ mà module sở hữu không chủ định công khai.

Đóng gói mạnh giúp JDK có thể thay đổi implementation mà không phải duy trì mọi chi tiết nội bộ như một cam kết tương thích.

## 3. JEP 396 thay đổi điều gì trong Java 16?

Từ Java 9, JPMS đã thiết lập ranh giới module và cung cấp cơ chế encapsulation. Tuy nhiên, các phiên bản đầu vẫn có một chế độ tương thích để ứng dụng cũ tiếp tục truy cập một số API nội bộ từng được sử dụng rộng rãi.

JEP 396 thay đổi mặc định đó trong Java 16:

- Strong encapsulation của các package nội bộ JDK trở thành chế độ mặc định.
- Cơ chế tương thích rộng của các JDK trước không còn được bật mặc định.
- Ứng dụng có thể cần sửa dependency hoặc cấu hình truy cập nếu còn dùng internals.
- Các trường hợp cần truy cập cụ thể có thể được xử lý bằng các tùy chọn module hẹp trong giai đoạn di trú.

JEP 396 cũng deprecate tùy chọn `--illegal-access`, vì đây chỉ là cơ chế tương thích tạm thời. Tùy chọn này vẫn có thể được dùng trong Java 16 để hỗ trợ một số ứng dụng cũ, nhưng không nên trở thành cấu hình lâu dài.

JEP 396 vẫn để lại một số ngoại lệ cho các API nội bộ quan trọng vì lý do tương thích, ví dụ `sun.misc.Unsafe`. Việc một API đặc biệt vẫn truy cập được không biến nó thành API công khai được khuyến nghị cho ứng dụng mới.

Điểm cần nhớ là Java 16 thay đổi **mặc định truy cập**. Đây không phải thay đổi cú pháp ngôn ngữ Java và cũng không có nghĩa mọi package trong JDK đều bị đóng. Các API công khai đã export vẫn hoạt động theo hợp đồng của chúng.

## 4. JEP 396 và JEP 403 trong các JDK hiện đại

Hai JEP liên quan nhưng đánh dấu các giai đoạn khác nhau:

| JEP | Phiên bản | Ý nghĩa |
|---|---:|---|
| JEP 396 | Java 16 | Strong encapsulation trở thành mặc định; có thể dùng các tùy chọn chuyển tiếp để xử lý ứng dụng cũ |
| JEP 403 | Java 17 | Hoàn tất việc đóng gói mạnh các internals của JDK; cơ chế mở rộng tương thích cũ không còn là cách khôi phục quyền truy cập |

JEP 403 tiếp tục chính sách đã bắt đầu từ Java 16. Trên Java 17 trở lên, không thể dựa vào cờ `--illegal-access` để mở hàng loạt package nội bộ theo cơ chế cũ. Cờ này không còn tác dụng mở quyền truy cập như trước và chỉ phát cảnh báo về việc nó đã lỗi thời.

Đối với ứng dụng chạy trên JDK hiện đại, hãy xử lý dependency nội bộ bằng API công khai hoặc cấu hình mở đúng package và đúng module cần thiết. Không lấy hành vi của Java 8 hoặc Java 11 làm giả định cho runtime mới.

## 5. API công khai và API nội bộ của JDK khác nhau thế nào?

Một API công khai được JDK tài liệu hóa và cam kết hỗ trợ theo chính sách tương thích của nền tảng. API nội bộ là chi tiết triển khai hoặc API không được công bố như một phần ổn định của Java SE.

Ví dụ về lựa chọn nên dùng:

| Nhu cầu | API công khai nên ưu tiên | Phụ thuộc nội bộ cần tránh |
|---|---|---|
| HTTP client | `java.net.http.HttpClient` | Lớp triển khai HTTP nội bộ của JDK |
| Xử lý ngày giờ | `java.time` | Lớp lịch hoặc định dạng nội bộ |
| Collection | `java.util` | Cấu trúc triển khai cụ thể như package nội bộ |
| Reflection | `java.lang.reflect` và `java.lang.invoke` | Truy cập private field của JDK bằng cách mở rộng |
| Quản lý tiến trình | `java.lang.ProcessBuilder` | API nội bộ dùng để khởi chạy process |
| File và I/O | `java.nio.file`, `java.nio.channels` | Lớp provider hoặc implementation nội bộ |

Tên package không đủ để kết luận một API là công khai. Hãy xem tài liệu Java SE và module descriptor của JDK đang dùng. Các package thuộc namespace như `sun.*` hoặc các package triển khai bên trong module thường là dấu hiệu cần kiểm tra kỹ, nhưng quyết định cuối cùng phải dựa trên tài liệu và trạng thái export thực tế.

Không nên dùng reflection để truy cập trường private của một lớp JDK chỉ vì cách đó đang chạy trên một phiên bản cụ thể. Implementation có thể thay đổi và quyền truy cập có thể bị JPMS chặn.

## 6. Exports và opens trong JPMS

Hai khái niệm này phục vụ hai loại quyền truy cập khác nhau:

- `exports` cho phép module khác truy cập các kiểu public trong package được export.
- `opens` cho phép reflection sâu vào package, kể cả các thành viên không public, theo quy tắc truy cập của Java.

Ví dụ module ứng dụng công khai một package API và mở một package model cho framework serialization:

```java
module com.example.orders {
    exports com.example.orders.api;

    opens com.example.orders.model to com.example.json;
}
```

Trong ví dụ:

- Module `com.example.json` có thể truy cập các kiểu public trong package `com.example.orders.api` vì package này được export, với điều kiện module gọi cũng đọc được `com.example.orders`.
- Framework trong module `com.example.json` có thể dùng deep reflection vào package `com.example.orders.model` vì package được mở có mục tiêu.
- Các package khác của module `com.example.orders` vẫn được đóng theo mặc định nếu không có chỉ thị phù hợp.

Tên package trong `exports` và `opens` là package chính xác; chúng không tự động bao gồm package con.

Nếu chỉ cần mở một package cho một framework cụ thể, dùng qualified opens với tên module đích sẽ giới hạn phạm vi tốt hơn mở toàn bộ module.

## 7. Phân biệt exports với opens

Không thay `exports` bằng `opens` hoặc ngược lại:

| Nhu cầu | exports | opens |
|---|---|---|
| Truy cập kiểu public từ module khác theo JPMS | Có | Không tự cấp quyền truy cập compile-time |
| Deep reflection vào private field/method | Không | Có |
| Dùng trong module descriptor | Có | Có |
| Mở toàn bộ module cho reflection | Không | Dùng `open module` |
| Công khai API cho người dùng module | Phù hợp | Không thay thế exports |

Một module có thể export package API nhưng không mở package đó cho deep reflection. Đây là cấu hình thường phù hợp với thư viện công khai: người dùng có thể gọi API public, nhưng không thể tùy ý sửa trạng thái nội bộ qua reflection.

Ngược lại, một package model có thể được mở cho framework serialization mà không cần export như API công khai. Framework chỉ cần quyền reflection; người dùng module khác không nhất thiết được phép tham chiếu các kiểu trong package đó ở compile time.

## 8. open module không đồng nghĩa export mọi package

Có thể khai báo một module là open:

```java
open module com.example.legacy.model {
    requires com.example.json;
}
```

Một open module mở tất cả package của nó cho deep reflection. Tuy nhiên, điều này **không tự động export tất cả package** để module khác sử dụng kiểu public ở compile time.

Chỉ dùng open module khi toàn bộ package thực sự cần mở cho reflection, chẳng hạn một ứng dụng legacy phụ thuộc framework reflection rộng. Với thiết kế mới, ưu tiên mở có mục tiêu:

```java
module com.example.orders {
    requires com.example.json;

    opens com.example.orders.model to com.example.json;
}
```

Cấu hình có mục tiêu giúp giới hạn bề mặt truy cập và làm rõ framework nào cần quyền reflection.

## 9. Vì sao setAccessible(true) có thể thất bại?

Trước khi có JPMS, nhiều framework dùng `AccessibleObject.setAccessible(true)` để truy cập private field hoặc method. Từ hệ thống module, thao tác này còn phải tuân theo việc package có được mở cho module gọi hay không.

Ví dụ:

```java
import java.lang.reflect.Field;

Field valueField = SomeType.class.getDeclaredField("value");
valueField.setAccessible(true);
```

Nếu `SomeType` thuộc một module không mở package chứa lớp đó cho module gọi, lệnh `setAccessible(true)` có thể ném `InaccessibleObjectException`.

Có thể dùng `trySetAccessible()` khi muốn kiểm tra khả năng mở quyền truy cập mà không bắt buộc phải ném exception trong trường hợp bị từ chối:

```java
import java.lang.reflect.Field;

Field valueField = SomeType.class.getDeclaredField("value");

if (valueField.trySetAccessible()) {
    Object value = valueField.get(instance);
} else {
    // Không có quyền deep reflection; dùng API công khai hoặc báo lỗi.
}
```

`trySetAccessible()` trả về `false` nếu không thể bật quyền truy cập. Nó không phải cách vượt qua strong encapsulation; nó chỉ cho phép ứng dụng xử lý kết quả bị từ chối một cách tường minh.

Nếu `SomeType` thuộc module của ứng dụng, hãy cân nhắc mở package cần thiết trong `module-info.java`. Nếu lớp thuộc JDK, ưu tiên API công khai thay vì mở package nội bộ.

## 10. --add-exports dùng khi nào?

`--add-exports` thêm một quan hệ export ở thời điểm chạy hoặc biên dịch cho một package cụ thể. Nó hữu ích trong giai đoạn di trú khi một ứng dụng cũ cần truy cập kiểu public trong package của module khác mà module đó không export mặc định.

Cú pháp tổng quát:

```bash
--add-exports module/package=target-module
```

Ví dụ cú pháp với module ứng dụng có tên:

```bash
javac --add-exports java.base/some.internal.package=com.example.app ...
```

Và khi chạy:

```bash
java --add-exports java.base/some.internal.package=com.example.app -m com.example.app/com.example.Main
```

Tên `some.internal.package` trong ví dụ là placeholder; thay bằng package thực tế mà công cụ phân tích đã xác định. Không sao chép nguyên văn placeholder vào lệnh chạy.

Nếu mã nằm trên classpath và thuộc unnamed module, target có thể là `ALL-UNNAMED`:

```bash
java --add-exports java.base/some.internal.package=ALL-UNNAMED -jar app.jar
```

`--add-exports` chỉ cho phép truy cập các kiểu public trong package được chỉ định. Nó không cho phép reflection sâu vào private field hoặc private method. Nó cũng không biến package nội bộ thành API ổn định được JDK cam kết duy trì.

Nếu cần truy cập kiểu ở compile time, phải truyền tùy chọn tương ứng cho `javac`; nếu chỉ thêm ở runtime, mã đã biên dịch có thể vẫn không biên dịch được từ đầu.

## 11. --add-opens dùng khi nào?

`--add-opens` mở một package của module nguồn cho reflection sâu từ module đích tại runtime. Đây là lựa chọn chuyển tiếp khi framework cũ cần truy cập private field hoặc method qua reflection.

Cú pháp:

```bash
--add-opens module/package=target-module
```

Ví dụ:

```bash
java --add-opens java.base/java.lang=com.example.framework -m com.example.app/com.example.Main
```

Ví dụ này mở package `java.lang` của module `java.base` cho module `com.example.framework`. Chỉ dùng nếu framework thực sự cần deep reflection vào package đó và chưa có phiên bản mới giải quyết bằng API được hỗ trợ.

Nếu framework chạy trên classpath:

```bash
java --add-opens java.base/java.lang=ALL-UNNAMED -jar app.jar
```

`--add-opens` là tùy chọn runtime. Nó không làm cho mã nguồn có thể import các kiểu trong package chưa export ở compile time. Nó cũng không cấp quyền cho mọi module trừ khi target là `ALL-UNNAMED` hoặc module đích được chỉ định phù hợp.

## 12. So sánh --add-exports và --add-opens

Hai cờ này không thể thay thế nhau:

| Tiêu chí | `--add-exports` | `--add-opens` |
|---|---|---|
| Mục đích | Cho phép truy cập kiểu public trong package | Cho phép deep reflection vào package |
| Compile time | Có thể dùng với `javac` | Không thay thế export lúc biên dịch |
| Runtime | Có | Có |
| Private field/method qua reflection | Không cấp quyền deep reflection | Có |
| Phạm vi | Một package tới module đích | Một package tới module đích |
| Cách dùng hiện đại | Workaround chuyển tiếp có kiểm soát | Workaround chuyển tiếp cho framework reflection |

Nếu lỗi biên dịch nói package không được export hoặc không hiển thị, hãy kiểm tra nhu cầu `--add-exports` hoặc thay API nội bộ bằng API công khai.

Nếu lỗi runtime là `InaccessibleObjectException` khi framework truy cập private member, hãy kiểm tra nhu cầu `--add-opens`. Đừng thêm cả hai cờ một cách máy móc.

## 13. Vì sao --illegal-access không còn là giải pháp hiện đại?

Các JDK trước Java 16 có tùy chọn `--illegal-access` để hỗ trợ ứng dụng cũ truy cập một số package nội bộ. JEP 396 thay đổi mặc định trong Java 16 và đánh dấu cơ chế này là hướng chuyển tiếp.

Đến Java 17, JEP 403 khiến `--illegal-access` không còn khả năng mở lại hàng loạt package như các phiên bản cũ. Trên JDK 17 trở lên, cờ này chỉ phát cảnh báo rằng nó đã lỗi thời và không khôi phục cơ chế truy cập cũ.

Không nên thêm các lệnh như:

```bash
java --illegal-access=permit -jar app.jar
```

vào cấu hình production hiện đại với kỳ vọng chúng sửa được lỗi strong encapsulation. Hãy nâng cấp thư viện, chuyển sang API công khai hoặc dùng đúng một tùy chọn `--add-exports`/`--add-opens` có phạm vi hẹp trong thời gian di trú.

Các cờ mở package vẫn có thể hữu ích cho tương thích có kiểm soát, nhưng chúng làm giảm encapsulation và có thể phải thay đổi khi nâng cấp JDK. Cần ghi rõ lý do, module/package đích và kế hoạch loại bỏ.

## 14. Tìm dependency vào JDK internals bằng jdeps

`jdeps` là công cụ phân tích dependency trong JDK. Tùy chọn `--jdk-internals` giúp tìm các tham chiếu bytecode tới API nội bộ của JDK trong file class hoặc JAR.

Ví dụ:

```bash
jdeps --jdk-internals app.jar
```

Có thể dùng với các artifact của ứng dụng và thư viện phụ thuộc:

```bash
jdeps --jdk-internals application.jar libraries/legacy-library.jar
```

Kết quả giúp xác định thư viện nào tham chiếu package nội bộ và gợi ý hướng thay thế khi công cụ nhận diện được API tương ứng.

Cần hiểu giới hạn của phân tích tĩnh:

- `jdeps` có thể phát hiện tham chiếu lớp/phương thức thể hiện trong bytecode.
- Nó không thể bảo đảm phát hiện mọi truy cập reflection được tạo từ tên chuỗi lúc runtime.
- Framework có thể tạo tên lớp hoặc field động, vì vậy cần đọc cấu hình và chạy integration test.
- Một dependency có thể nằm sâu trong cây thư viện, không nằm trong source code ứng dụng.

Hãy chạy công cụ trên toàn bộ artifact cần triển khai, không chỉ trên module chính. Khi nâng cấp dependency, kiểm tra lại để xác nhận tham chiếu nội bộ đã được loại bỏ.

## 15. Quy trình di trú khi gặp lỗi strong encapsulation

Khi ứng dụng chuyển lên Java 16 hoặc JDK mới hơn và gặp lỗi truy cập nội bộ, xử lý theo thứ tự:

1. **Xác định lớp và package gây lỗi.** Đọc stack trace, đặc biệt tên module nguồn, package và module gọi.
2. **Tìm thư viện sở hữu đoạn truy cập.** Lỗi có thể đến từ framework hoặc dependency, không phải mã trực tiếp của ứng dụng.
3. **Kiểm tra phiên bản mới của thư viện.** Ưu tiên nâng cấp lên bản đã hỗ trợ JPMS và JDK mục tiêu.
4. **Tìm API công khai thay thế.** Xem Java SE API hoặc API được nhà cung cấp JDK tài liệu hóa.
5. **Nếu reflection nằm trong module của ứng dụng,** khai báo `opens` có mục tiêu trong module descriptor khi phù hợp.
6. **Nếu cần workaround với JDK internals,** xác định đúng package và module đích rồi dùng `--add-exports` hoặc `--add-opens` tối thiểu.
7. **Chạy test trên JDK triển khai.** Bao gồm unit test, integration test và luồng thực tế có framework reflection.
8. **Ghi lại workaround.** Có owner, lý do, phạm vi, phiên bản dependency cần nâng cấp và điều kiện xóa cờ.

Không nên xử lý bằng cách mở tất cả package của JDK. Một workaround rộng có thể che giấu nhiều dependency nội bộ và khiến việc nâng cấp về sau khó khăn hơn.

## 16. Ví dụ xử lý một thư viện cần deep reflection

Giả sử ứng dụng có module `com.example.app` và framework `com.example.framework` cần truy cập private field trong package model của ứng dụng.

Cấu hình có mục tiêu:

```java
module com.example.app {
    requires com.example.framework;

    opens com.example.app.model to com.example.framework;
}
```

Framework chỉ được mở reflection vào package `com.example.app.model`. Các package còn lại của ứng dụng vẫn được đóng.

Nếu framework cần reflection vào một package của JDK, không thể sửa module descriptor của `java.base` trong source ứng dụng. Trong thời gian di trú, có thể truyền một `--add-opens` cụ thể ở runtime nếu có lý do tương thích rõ ràng:

```bash
java --add-opens java.base/java.lang=com.example.framework -m com.example.app/com.example.Main
```

Sau đó, nâng cấp framework hoặc thay đổi cách tích hợp để loại bỏ cờ này. Không giữ workaround vô thời hạn mà không có kiểm tra tương thích.

## 17. Strong encapsulation không phải sandbox bảo mật

JPMS kiểm soát khả năng truy cập giữa các module và giúp bảo vệ ranh giới implementation. Tuy nhiên, module system không phải sandbox để chạy mã không đáng tin cậy.

Không nên suy luận rằng:

- Module không export package là đã cô lập hoàn toàn mã độc.
- `opens` có thể thay thế kiểm soát quyền hệ điều hành.
- Strong encapsulation tự xác thực danh tính peer hoặc bảo vệ dữ liệu trên mạng.
- Việc dùng module descriptor thay thế các biện pháp bảo mật ứng dụng.

Đây là cơ chế thiết kế và kiểm soát truy cập API trong nền tảng Java. Bảo mật ứng dụng vẫn cần xác thực, phân quyền, kiểm tra đầu vào, quản lý secret và cấu hình hệ điều hành phù hợp.

## 18. Những lỗi thường gặp

**Cho rằng mọi lớp có trong JDK đều là API công khai.** Chỉ dùng API được tài liệu hóa và export phù hợp; lớp nội bộ không có cam kết tương thích như Java SE API.

**Nghĩ JEP 396 thay đổi cú pháp Java.** Đây là thay đổi mặc định encapsulation của JDK, không phải thay đổi cú pháp ngôn ngữ.

**Dùng --illegal-access=permit trên JDK hiện đại.** Cờ này không còn khôi phục cơ chế mở rộng cũ từ Java 17. Hãy xử lý dependency hoặc dùng tùy chọn cụ thể khi thật sự cần.

**Dùng --add-exports để truy cập private field.** Export cấp quyền truy cập kiểu public, không cấp deep reflection. Reflection sâu cần package được mở.

**Dùng --add-opens để sửa lỗi compile-time package not exported.** Opens dành cho runtime reflection; nó không thay thế exports khi biên dịch.

**Mở toàn bộ module cho framework dù chỉ một package cần thiết.** Dùng qualified opens để giới hạn phạm vi.

**Cho rằng jdeps phát hiện được mọi reflection.** Phân tích tĩnh không bảo đảm nhận diện truy cập được tạo động; cần test và kiểm tra cấu hình framework.

**Coi --add-exports hoặc --add-opens là API ổn định.** Chúng là tùy chọn cấu hình truy cập, không biến JDK internal thành API được hỗ trợ lâu dài.

**Bắt InaccessibleObjectException rồi tiếp tục như không có lỗi.** Nếu framework không đọc/ghi được dữ liệu, ứng dụng có thể tạo trạng thái sai. Hãy nâng cấp thư viện hoặc báo lỗi cấu hình rõ ràng.

**Coi strong encapsulation là sandbox bảo mật.** JPMS kiểm soát truy cập module, không thay thế cơ chế bảo mật ở tầng ứng dụng và hệ điều hành.

## 19. Ghi nhớ

- JEP 396 đưa strong encapsulation thành mặc định trong Java 16.
- JEP 403 tiếp tục hoàn tất đóng gói mạnh JDK trong Java 17.
- API công khai được tài liệu hóa là lựa chọn ổn định cho ứng dụng.
- `exports` cho phép module khác truy cập kiểu public trong package; `opens` cho phép deep reflection.
- `open module` mở mọi package cho reflection nhưng không tự export mọi package.
- `setAccessible(true)` có thể thất bại với `InaccessibleObjectException` nếu package không được mở.
- `trySetAccessible()` cho phép kiểm tra khả năng deep reflection và trả về `false` khi không thể mở.
- `--add-exports` phục vụ truy cập kiểu public trong package được chỉ định; `--add-opens` phục vụ deep reflection tại runtime.
- `--illegal-access` là cơ chế chuyển tiếp cũ và không còn mở package theo cách cũ trên JDK 17 trở lên.
- `jdeps --jdk-internals` giúp tìm tham chiếu bytecode tới JDK internals, nhưng không phát hiện chắc chắn mọi reflection động.
- Khi di trú, nâng cấp dependency và thay API nội bộ trước; chỉ dùng workaround hẹp khi chưa thể loại bỏ ngay.
- Strong encapsulation là ranh giới module, không phải sandbox bảo mật.

Strong encapsulation giúp ứng dụng phụ thuộc vào hợp đồng API rõ ràng và giúp JDK tự do cải tiến implementation. Hiểu sự khác nhau giữa exports, opens và các tùy chọn module giúp xử lý lỗi nâng cấp đúng nguyên nhân, đồng thời giữ mã Java hiện đại ổn định qua các phiên bản JDK.

## Tài liệu tham khảo

- [JEP 396 – Strongly Encapsulate JDK Internals by Default](https://openjdk.org/jeps/396) — thay đổi mặc định strong encapsulation trong Java 16.
- [JEP 403 – Strongly Encapsulate JDK Internals](https://openjdk.org/jeps/403) — hoàn tất quá trình đóng gói mạnh trong Java 17.
- [Java Platform Module System – Module Declaration](https://docs.oracle.com/javase/specs/jls/se16/html/jls-7.html#jls-7.7) — cú pháp `exports`, `opens` và module declaration.
- [Java SE 16 – jdeps tool](https://docs.oracle.com/en/java/javase/16/docs/specs/man/jdeps.html) — phân tích dependency và tham chiếu tới JDK internals.
- [Java SE 16 – java launcher](https://docs.oracle.com/en/java/javase/16/docs/specs/man/java.html) — tùy chọn `--add-exports`, `--add-opens` và `--illegal-access`.

