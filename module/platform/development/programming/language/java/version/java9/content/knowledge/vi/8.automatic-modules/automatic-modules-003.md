# Tên suy ra và thuộc tính `Automatic-Module-Name`

Khi một JAR chưa có `module-info.class` được đặt trên module path, JPMS có thể coi JAR đó là một automatic module. Mô-đun này cần một tên để các named module khác khai báo `requires`. Tên có thể được lấy từ thuộc tính manifest `Automatic-Module-Name`; nếu thuộc tính không có, JDK suy ra tên từ tên tệp JAR.

`Automatic-Module-Name` vẫn được JDK hiện hành hỗ trợ. Đây là cách hữu ích để một thư viện chưa thể cung cấp module descriptor vẫn có tên mô-đun ổn định cho ứng dụng modular. Thuộc tính này chỉ xác định tên; nó không biến JAR thành explicit module và không thay thế `module-info.java`.

## 1. Ba trường hợp xác định tên mô-đun

JPMS xác định tên theo thứ tự sau:

1. **JAR có `module-info.class`:** tên trong module descriptor là tên mô-đun. Đây là explicit module.
2. **JAR chưa có `module-info.class` nhưng manifest có `Automatic-Module-Name`:** giá trị thuộc tính là tên automatic module.
3. **Không có cả descriptor lẫn thuộc tính:** JDK suy ra tên từ tên tệp JAR.

Trường hợp thứ hai và thứ ba đều tạo automatic module khi JAR được đặt trên module path. Chỉ thêm `Automatic-Module-Name` không tạo ra các khai báo `requires`, `exports`, `opens`, `uses` hay `provides` như một module descriptor đầy đủ.

## 2. Cách JDK suy ra tên từ tên tệp JAR

JDK chuẩn hóa tên tệp để tạo một tên mô-đun hợp lệ. Quy tắc thực tế gồm các bước chính:

1. Bỏ phần mở rộng `.jar`.
2. Nếu tên có hậu tố phiên bản dạng `-` theo sau bởi chuỗi bắt đầu bằng chữ số và dấu chấm hoặc kết thúc tên, tách hậu tố đó làm phiên bản mô-đun.
3. Thay các ký tự không phải chữ hoặc số bằng dấu chấm.
4. Gộp các dấu chấm liên tiếp thành một dấu chấm và bỏ dấu chấm ở đầu/cuối.
5. Tên thu được vẫn phải gồm các thành phần hợp lệ theo quy tắc định danh Java; nếu không, JDK không thể tạo automatic module.

Ví dụ được kiểm tra bằng `jar --describe-module` trên JDK 24:

| Tên tệp JAR | Tên automatic module | Phiên bản mô-đun |
| --- | --- | --- |
| `alpha-utils-1.2.3.jar` | `alpha.utils` | `1.2.3` |
| `my_library-2.0.jar` | `my.library` | `2.0` |
| `foo..bar-3.4.jar` | `foo.bar` | `3.4` |
| `foo-1.2.3-SNAPSHOT.jar` | `foo` | `1.2.3-SNAPSHOT` |

Phiên bản được hiển thị riêng, ví dụ `alpha.utils@1.2.3 automatic`; phần `@1.2.3` không thuộc tên mô-đun mà consumer dùng trong `requires`.

### Tên tệp không phải lúc nào cũng tạo được tên mô-đun hợp lệ

Chuẩn hóa dấu phân cách không sửa được mọi tên không hợp lệ. Ví dụ `123-widget-1.0.jar` có thể tạo thành thành phần `123`, bắt đầu bằng chữ số; `foo-1x.jar` có thể tạo thành thành phần `1x`. JDK từ chối các tên này khi suy ra module descriptor.

Tên JAR còn có thể thay đổi theo classifier, cách đóng gói hoặc quy ước build. Nếu consumer dựa vào tên suy ra, đổi tên artifact có thể vô tình đổi tên mô-đun và làm hỏng dòng `requires` của ứng dụng.

## 3. Dùng `Automatic-Module-Name` để giữ tên ổn định

Đặt thuộc tính `Automatic-Module-Name` trong phần main attributes của manifest:

**`MANIFEST.MF`**

```text
Manifest-Version: 1.0
Automatic-Module-Name: com.example.codec

```

Giá trị phải là tên mô-đun hợp lệ. Nên dùng tên ổn định theo quy ước reverse-domain, chẳng hạn `com.example.codec`; không đưa phiên bản phát hành hoặc hậu tố `.jar` vào giá trị.

Giả sử artifact có tên `codec-5.2.jar` nhưng manifest khai báo `Automatic-Module-Name: com.example.codec`. JDK dùng `com.example.codec` làm tên mô-đun. Phiên bản `5.2` vẫn có thể được suy ra từ tên tệp và hiển thị riêng trong descriptor:

```text
No module descriptor found. Derived automatic module.

com.example.codec@5.2 automatic
requires java.base mandated
contains com.example.codec
```

Điểm quan trọng: thuộc tính manifest giữ ổn định tên mô-đun khi tên artifact thay đổi; nó không xóa thông tin phiên bản có thể suy ra từ tên JAR.

## 4. Ví dụ: ứng dụng named module dùng JAR có `Automatic-Module-Name`

Ví dụ tạo một thư viện chưa có `module-info.java`, đặt tên mô-đun bằng manifest và dùng thư viện từ một named module.

**`library-src/com/example/codec/Codec.java`**

```java
package com.example.codec;

public final class Codec {
    public String encode(String value) {
        return "encoded:" + value;
    }
}
```

Biên dịch thư viện và đóng gói JAR:

```powershell
New-Item -ItemType Directory -Force lib-classes, lib | Out-Null
javac --release 17 -d lib-classes library-src/com/example/codec/Codec.java
jar --create --file lib/codec-5.2.jar --manifest MANIFEST.MF -C lib-classes .
```

**`consumer-src/com.example.consumer/module-info.java`**

```java
module com.example.consumer {
    requires com.example.codec;
}
```

**`consumer-src/com.example.consumer/com/example/consumer/Main.java`**

```java
package com.example.consumer;

import com.example.codec.Codec;

public class Main {
    public static void main(String[] args) {
        System.out.println(new Codec().encode("hello"));
    }
}
```

Kiểm tra tên mô-đun được nhận diện:

```powershell
jar --describe-module --file lib/codec-5.2.jar
```

Biên dịch và chạy consumer trên Windows PowerShell:

```powershell
javac --release 17 --module-path lib/codec-5.2.jar --module-source-path consumer-src -d out -m com.example.consumer
java --module-path "lib/codec-5.2.jar;out" -m com.example.consumer/com.example.consumer.Main
```

STDOUT:

```text
encoded:hello
```

Consumer dùng `requires com.example.codec`, tức tên lấy từ manifest. Consumer không cần biết artifact hiện tại tên `codec-5.2.jar`; cũng không cần đặt `requires` theo tên package hoặc tên class.

## 5. Xác minh tên bằng công cụ JDK

`jar --describe-module` là cách trực tiếp để xem JDK nhận diện JAR như thế nào:

```powershell
jar --describe-module --file lib/codec-5.2.jar
```

Với automatic module, kết quả bắt đầu bằng `No module descriptor found. Derived automatic module.` rồi hiển thị tên, phiên bản nếu có, modifier `automatic` và các package được chứa.

Nếu JAR có module descriptor tường minh, công cụ hiển thị tên lấy từ `module-info.class`. Thử nghiệm với một JAR có `module-info.class` và manifest đặt tên khác cho thấy tên explicit trong descriptor được dùng; `Automatic-Module-Name` không ghi đè tên đó.

Vì vậy, khi đổi thư viện từ automatic module sang explicit module, tên trong `module-info.java` nên giữ đúng tên `Automatic-Module-Name` đã phát hành trước đó. Đổi tên ở bước này sẽ buộc mọi consumer sửa `requires` và có thể gây lỗi resolve.

## 6. Automatic module có phạm vi truy cập rộng

Automatic module là cơ chế tương thích khi đưa JAR chưa modular hóa lên module path. Trong cấu hình JPMS, automatic module đọc các mô-đun khác và export tất cả package của chính nó. Điều này giúp thư viện cũ dễ được dùng từ named module mà chưa phải khai báo ngay toàn bộ ranh giới.

Phạm vi rộng này cũng có nghĩa automatic module chưa cung cấp mức đóng gói mạnh như explicit module. Consumer có thể vô tình phụ thuộc vào package nội bộ mà thư viện chưa công bố như API. Khi thư viện bổ sung `module-info.class` và chỉ export package công khai, những truy cập trước đó có thể không còn biên dịch hoặc không còn được phép.

`Automatic-Module-Name` không thu hẹp các quyền này. Nó chỉ ổn định danh tính mô-đun; việc khai báo dependency và ranh giới package vẫn cần module descriptor tường minh.

## 7. Khi nào nên dùng và lộ trình chuyển đổi

- **Dùng `Automatic-Module-Name`** khi duy trì thư viện JAR chưa thể phát hành `module-info.class` nhưng muốn consumer trên module path có một tên ổn định.
- **Dùng tên reverse-domain cố định** và giữ nguyên tên qua các phiên bản tương thích; tên này là một phần hợp đồng mà consumer tham chiếu trong `requires`.
- **Kiểm tra bằng `jar --describe-module`** sau mỗi lần đóng gói để phát hiện tên suy ra ngoài dự kiến, sai manifest hoặc phiên bản được nhận diện khác dự tính.
- **Thử consumer trên module path** thay vì chỉ kiểm tra chạy trên classpath. Classpath đặt JAR vào unnamed module; `Automatic-Module-Name` không biến classpath thành named module.
- **Chuyển sang explicit module khi sẵn sàng:** thêm `module-info.java`, khai báo `requires`, `exports`, `uses` và `provides` đúng nhu cầu; giữ tên module descriptor khớp tên automatic đã công bố.

Không nên coi tên suy ra từ filename là hợp đồng dài hạn cho thư viện được phát hành rộng rãi. Một thay đổi quy ước đặt tên artifact có thể đổi module name dù mã nguồn và package không đổi. Với thư viện đang trong giai đoạn chuyển tiếp, `Automatic-Module-Name` tránh sự phụ thuộc đó; explicit module descriptor là bước hoàn thiện ranh giới JPMS.

## 8. Lỗi thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `module not found` khi consumer `requires` | Tên trong `requires` không trùng tên JDK nhận diện, JAR thiếu trên module path hoặc manifest không được đóng gói đúng. | Chạy `jar --describe-module`, kiểm tra manifest và module path. |
| Tên mô-đun thay đổi sau khi nâng phiên bản | Tên được suy ra từ filename và quy ước artifact đã thay đổi. | Phát hành `Automatic-Module-Name` ổn định hoặc module descriptor explicit. |
| `Invalid module name` | Filename sau chuẩn hóa tạo thành thành phần không phải định danh Java hợp lệ. | Đổi filename phù hợp hoặc khai báo `Automatic-Module-Name` hợp lệ. |
| Manifest có thuộc tính nhưng tên vẫn khác | JAR có `module-info.class`, hoặc manifest attribute không nằm trong main section/không có trong artifact thực tế. | Kiểm tra JAR đã đóng gói và chạy `jar --describe-module`. |
| Chạy được trên classpath nhưng không resolve trên module path | Classpath và module path có quy tắc mô-đun khác nhau; automatic module chỉ được tạo khi JAR được xử lý trên module path. | Kiểm tra lại module path, tên mô-đun và descriptor. |

## 9. Checklist phát hành thư viện

1. Chọn một tên mô-đun ổn định, hợp lệ và theo reverse-domain.
2. Đặt `Automatic-Module-Name` trong main section của manifest nếu JAR chưa có `module-info.class`.
3. Kiểm tra artifact đã đóng gói bằng `jar --describe-module`.
4. Biên dịch một consumer named module với `requires` đúng tên và chạy thử trên module path.
5. Không đổi tên mô-đun đã phát hành nếu không có kế hoạch tương thích cho consumer.
6. Khi phát hành explicit module descriptor, giữ tên descriptor khớp tên automatic đã công bố và kiểm thử lại các package được export.

Tên mô-đun là danh tính mà các mô-đun khác dùng trong `requires`. Tên suy ra từ filename thuận tiện cho việc chuyển tiếp nhưng phụ thuộc vào cách đặt tên artifact. `Automatic-Module-Name` cung cấp tên ổn định cho JAR chưa modular hóa; khi thư viện sẵn sàng, `module-info.class` sẽ xác định rõ dependency và ranh giới truy cập.