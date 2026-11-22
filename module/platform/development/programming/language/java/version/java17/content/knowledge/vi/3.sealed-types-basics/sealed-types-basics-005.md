# Sealed Java 17: điều kiện cùng *named module* hoặc cùng package trong *unnamed module*

Trong Java 17, `sealed` cho phép một lớp hoặc interface **giới hạn trực tiếp những kiểu nào được kế thừa hoặc triển khai nó**. Danh sách các kiểu được phép thường nằm sau từ khóa `permits`. Tuy nhiên, việc liệt kê một kiểu trong `permits` **chưa đủ**: vị trí của kiểu đó trong **module** hoặc **package** còn phải hợp lệ.

Quy tắc cốt lõi:

> Nếu kiểu `sealed` thuộc **named module**, mọi kiểu kế thừa/triển khai **trực tiếp** được cho phép phải ở **cùng named module** đó. Nếu kiểu `sealed` thuộc **unnamed module**, mọi kiểu được cho phép trực tiếp phải ở **cùng package** với kiểu `sealed`.

Quy tắc áp dụng cho cả `sealed class` và `sealed interface`. Đây là ràng buộc của ngôn ngữ Java 17, được trình biên dịch kiểm tra; không phải một thiết lập có thể bỏ qua bằng cách thêm `import`, `exports` hay sửa `PATH`.

## 1. Những khái niệm cần phân biệt

### `sealed` và `permits`

Ví dụ một interface cho phép đúng hai kiểu triển khai trực tiếp:

```java
package example.payment;

public sealed interface Payment permits CashPayment, CardPayment {
    String description();
}
```

`CashPayment` và `CardPayment` là **permitted direct subtypes** (các kiểu con trực tiếp được phép). Chúng phải thực sự `implements Payment`, không chỉ xuất hiện trong danh sách `permits`. Với lớp `sealed`, kiểu được phép phải trực tiếp `extends` lớp đó; với interface `sealed`, kiểu được phép phải trực tiếp `extends` (interface con) hoặc `implements` (class triển khai) interface đó.

Các kiểu con trực tiếp cũng phải khai báo cách tiếp tục hệ phân cấp, chẳng hạn:

```java
package example.payment;

public final class CashPayment implements Payment {
    @Override
    public String description() {
        return "Thanh toán tiền mặt";
    }
}
```

Một class con trực tiếp thường phải dùng một trong ba modifier `final`, `sealed` hoặc `non-sealed` (các ngoại lệ cú pháp cho kiểu có tính chất đặc biệt như `record` được Java xử lý tương ứng). Một interface con trực tiếp có thể dùng `sealed` hoặc `non-sealed`, vì interface không thể là `final`.

### Package và module là hai cấp tổ chức khác nhau

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Package** | Nhóm các kiểu Java theo tên khai báo `package`. | `example.payment`, `example.payment.impl` là **hai package khác nhau**. |
| **Named module** | Module có tên, thường được khai báo trong `module-info.java` của dự án JPMS. Một module có thể chứa nhiều package. | `module example.billing { ... }` |
| **Unnamed module** | Module không có tên, thường chứa các lớp được nạp từ **classpath** theo mô hình ứng dụng không dùng named module. | Các file `.class` chạy bằng `java -cp out ...` mà không có module descriptor. |

**Đừng nhầm *unnamed module* với *unnamed/default package*.** Bạn vẫn có thể khai báo `package example.payment;` và chạy mã trong unnamed module. Ngược lại, tên package trông có cấu trúc không tự biến dự án thành named module: thông tin module phụ thuộc cách tổ chức, biên dịch và nạp mã.

## 2. Bảng quy tắc dành cho các kiểu con trực tiếp

| Kiểu `sealed` được khai báo trong | Kiểu được ghi ở `permits` phải ở đâu? | Có thể khác package không? | Có thể khác module không? |
| --- | --- | --- | --- |
| **Named module** | **Cùng named module** với kiểu `sealed`. | **Có**, nếu khả năng truy cập kiểu trong Java vẫn hợp lệ. | **Không**. |
| **Unnamed module** | **Cùng package** với kiểu `sealed`. | **Không**. | Không được dùng việc ở module khác để vượt qua yêu cầu cùng package. |

Ví dụ minh họa:

```text
Named module: example.billing
├── package example.billing.api
│   └── Payment (sealed)
└── package example.billing.impl
    ├── CashPayment (final)   ✓ khác package, cùng module
    └── CardPayment (final)   ✓ khác package, cùng module

Unnamed module (classpath)
├── package example.payment
│   ├── Payment (sealed)
│   ├── CashPayment (final)   ✓ cùng package
│   └── CardPayment (final)   ✓ cùng package
└── package example.payment.impl
    └── MobilePayment (final) ✗ không thể là con trực tiếp
                                    được permits bởi Payment
```

Những hạn chế này chỉ nói về **quan hệ kế thừa/triển khai trực tiếp** được kiểm soát bởi kiểu `sealed`. Một kiểu con `non-sealed` có thể mở lại quyền kế thừa cho cấp sau; cấp sau không phải từng được ghi vào `permits` của tổ tiên `sealed`.

## 3. Ví dụ hợp lệ: named module, khác package nhưng cùng module

Giả sử chúng ta xây dựng ứng dụng Java 17 có module `demo.sealed`. Các kiểu con nằm trong package `demo.impl`, còn interface gốc ở `demo.api`.

### Cấu trúc thư mục

```text
project/
└── src/
    └── demo.sealed/
        ├── module-info.java
        └── demo/
            ├── Main.java
            ├── api/
            │   └── Payment.java
            └── impl/
                ├── CashPayment.java
                └── CardPayment.java
```

**`src/demo.sealed/module-info.java`**

```java
module demo.sealed {
    exports demo.api;
}
```

Module chỉ xuất package API cho module khác sử dụng. `demo.impl` không cần `exports` để `Payment` cho phép hai lớp bên trong **cùng module**.

**`src/demo.sealed/demo/api/Payment.java`**

```java
package demo.api;

public sealed interface Payment
        permits demo.impl.CashPayment, demo.impl.CardPayment {
    String description();
}
```

`permits` ở đây dùng **tên đầy đủ** của hai kiểu ở package khác. Điều đó giúp chỉ rõ chúng nằm ở đâu; nó không thay thế điều kiện cùng module.

**`src/demo.sealed/demo/impl/CashPayment.java`**

```java
package demo.impl;

import demo.api.Payment;

public final class CashPayment implements Payment {
    @Override
    public String description() {
        return "Cash";
    }
}
```

**`src/demo.sealed/demo/impl/CardPayment.java`**

```java
package demo.impl;

import demo.api.Payment;

public final class CardPayment implements Payment {
    @Override
    public String description() {
        return "Card";
    }
}
```

**`src/demo.sealed/demo/Main.java`**

```java
package demo;

import demo.api.Payment;
import demo.impl.CashPayment;

public class Main {
    public static void main(String[] args) {
        Payment payment = new CashPayment();
        System.out.println(payment.description());
    }
}
```

Từ thư mục `project`, biên dịch toàn bộ named module và chạy lớp `Main`:

```bash
javac --module-source-path src -d out -m demo.sealed
java --module-path out -m demo.sealed/demo.Main
```

Kết quả:

```text
Cash
```

**Vì sao hợp lệ?** `Payment`, `CashPayment` và `CardPayment` đều thuộc **module `demo.sealed`**, dù `demo.api` và `demo.impl` là hai package riêng. Mọi lớp con được phép đều `implements Payment` trực tiếp và được đánh dấu `final`. Trong cùng module, lớp `Main` còn sử dụng được `demo.impl` dù package đó không được xuất cho module bên ngoài.

### `exports` có ý nghĩa gì trong ví dụ này?

`exports demo.api` điều khiển khả năng truy cập **public type** trong `demo.api` từ module khác. Nó **không mở quyền** cho lớp ở module khác trở thành kiểu con trực tiếp của một kiểu `sealed` ở `demo.sealed`. Tương tự, `requires` làm module đọc module khác, nhưng không thay đổi luật `permits`.

Muốn `demo.impl` được code từ module khác gọi trực tiếp, có thể cần xuất package đó theo thiết kế API. Tuy vậy, **không cần** xuất `demo.impl` chỉ để cho phép hai kiểu con trong **cùng module** triển khai `Payment`.

## 4. Ví dụ hợp lệ: unnamed module, các kiểu con cùng package

Với ứng dụng Java 17 chạy trên **classpath**, không khai báo `module-info.java`, các kiểu con được liệt kê trong `permits` phải cùng package với kiểu `sealed`.

### Cấu trúc thư mục

```text
project/
└── src/
    └── sample/
        └── payment/
            ├── Payment.java
            ├── CashPayment.java
            ├── CardPayment.java
            └── Main.java
```

**`src/sample/payment/Payment.java`**

```java
package sample.payment;

public sealed interface Payment permits CashPayment, CardPayment {
    String description();
}
```

**`src/sample/payment/CashPayment.java`**

```java
package sample.payment;

public final class CashPayment implements Payment {
    @Override
    public String description() {
        return "Cash";
    }
}
```

**`src/sample/payment/CardPayment.java`**

```java
package sample.payment;

public final class CardPayment implements Payment {
    @Override
    public String description() {
        return "Card";
    }
}
```

**`src/sample/payment/Main.java`**

```java
package sample.payment;

public class Main {
    public static void main(String[] args) {
        Payment payment = new CardPayment();
        System.out.println(payment.description());
    }
}
```

Từ thư mục `project`, sử dụng `-cp` để chạy trên classpath:

```bash
javac -d out src/sample/payment/Payment.java src/sample/payment/CashPayment.java src/sample/payment/CardPayment.java src/sample/payment/Main.java
java -cp out sample.payment.Main
```

Kết quả:

```text
Card
```

**Vì sao hợp lệ?** `Payment`, `CashPayment` và `CardPayment` cùng khai báo `package sample.payment;`. Dự án này không định nghĩa named module, vì vậy yêu cầu **cùng package** được đáp ứng. Các file có thể nằm ở nhiều vị trí trên đĩa khi cấu hình biên dịch phức tạp, nhưng điều kiện là **package được khai báo trong mã Java**, không chỉ tên folder.

Lưu ý: `sample.payment` và `sample.payment.impl` là **hai package độc lập**. Trong Java, package con theo tên không được xem là "nằm trong" package cha về mặt quan hệ ngôn ngữ; cùng tiền tố tên không đủ để thỏa điều kiện của `sealed`.

## 5. Các trường hợp không hợp lệ và cách sửa

### Trường hợp A: unnamed module nhưng lớp con khác package

**`sample/api/Action.java`**

```java
package sample.api;

public sealed interface Action permits sample.impl.RunAction {
}
```

**`sample/impl/RunAction.java`**

```java
package sample.impl;

import sample.api.Action;

public final class RunAction implements Action {
}
```

Hai file ở các package khác nhau (`sample.api` và `sample.impl`). Nếu chúng được biên dịch trong unnamed module trên classpath, khai báo này **không hợp lệ**, kể cả khi `RunAction` là `public`, có `import` đúng và được ghi trong `permits`.

**Cách sửa:** Chuyển `RunAction` về cùng `package sample.api` **hoặc** tổ chức chúng trong một **named module** duy nhất nếu dự án thực sự cần tách package. Không cần loại bỏ `sealed` chỉ để giữ class con ở một package khác khi có thể dùng named module phù hợp.

### Trường hợp B: hai named module khác nhau

Giả sử:

```text
module sales.core
└── package sales.api
    └── sealed interface Order

module sales.extensions
└── package sales.impl
    └── class OnlineOrder implements Order
```

Dù `sales.extensions` khai báo `requires sales.core` và `sales.core` xuất `sales.api`, `OnlineOrder` **không thể là kiểu con trực tiếp được `Order` cho phép** vì hai lớp nằm ở hai named module khác nhau. `requires`/`exports` giải quyết việc module nhìn thấy API của nhau, không nới lỏng ranh giới `sealed`.

**Cách sửa:** Đặt các kiểu được phép trực tiếp trong cùng named module với `Order`. Nếu mong muốn các module ngoài tự định nghĩa nhiều kiểu con, cần thiết kế lại điểm mở rộng, ví dụ đặt một lớp/interface trung gian `non-sealed` được cho phép **trong `sales.core`**, rồi cho kiểu ở module ngoài kế thừa/triển khai trung gian khi quyền truy cập cho phép:

```java
// Trong named module sales.core, package sales.api
public sealed interface Order permits ExtensibleOrder {
}

// Trong cùng named module sales.core, package sales.api
public non-sealed interface ExtensibleOrder extends Order {
}
```

Một lớp ở module khác có thể `implements ExtensibleOrder` nếu module và kiểu được công khai/truy cập đúng cách. Lớp đó **không phải kiểu con trực tiếp của `Order`**, nên không cần và không thể được thêm trực tiếp vào `Order`'s `permits` từ module khác.

### Trường hợp C: chỉ khai báo `permits`, thiếu quan hệ kế thừa trực tiếp

```java
package sample.payment;

public sealed interface Payment permits VoucherPayment {
}

final class VoucherPayment { // Sai: không implements Payment
}
```

Hai kiểu nằm cùng package nhưng `VoucherPayment` chưa `implements Payment`; việc xuất hiện trong `permits` không tự tạo quan hệ kế thừa. Cách sửa là thêm `implements Payment` vào `VoucherPayment` (và khai báo các phương thức bắt buộc, nếu có).

### Trường hợp D: thiếu `final`, `sealed` hoặc `non-sealed` ở con trực tiếp

```java
package sample.payment;

public sealed interface Payment permits VoucherPayment {
}

class VoucherPayment implements Payment { // Sai: chưa xác định cách mở rộng tiếp
}
```

Một class bình thường trực tiếp triển khai `sealed interface` cần ghi rõ lựa chọn: `final class VoucherPayment`, `sealed class VoucherPayment permits ...` hoặc `non-sealed class VoucherPayment`. Vị trí module/package đúng vẫn chưa đủ nếu quy tắc modifier không được đáp ứng.

## 6. `permits` tường minh và trường hợp Java tự suy ra

Để dễ đọc, các ví dụ trước đều khai báo `permits` rõ ràng. Trong Java 17, nếu các kiểu con trực tiếp được khai báo **trong cùng compilation unit (cùng file nguồn Java)** với kiểu `sealed`, trình biên dịch có thể **suy ra danh sách permitted subtypes** mà không cần viết `permits`.

Ví dụ một file `Vehicle.java`:

```java
package sample.transport;

public sealed interface Vehicle {
}

final class Bicycle implements Vehicle {
}

final class Scooter implements Vehicle {
}
```

Hai lớp cùng file `Vehicle.java` và cùng package nên `Vehicle` có thể bỏ `permits`. Đây là tiện ích cú pháp, **không phải ngoại lệ cho quy tắc module/package**. Khi các kiểu con được đặt ở những file riêng, thông thường bạn cần liệt kê chúng trong `permits` của kiểu `sealed`.

## 7. Khi nào áp dụng ràng buộc cho cấp con tiếp theo?

Xét phân cấp:

```java
package app.api;

public sealed interface Event permits InternalEvent, ExternalEvent {
}

final class InternalEvent implements Event {
}

non-sealed interface ExternalEvent extends Event {
}
```

`InternalEvent` và `ExternalEvent` là **hai kiểu con trực tiếp** của `Event`, nên tuân thủ điều kiện cùng module/package. Sau khi `ExternalEvent` được khai báo `non-sealed`, các lớp **triển khai `ExternalEvent`** ở cấp sau có thể được mở rộng theo các quy tắc module, package và khả năng truy cập thông thường. Nếu `ExternalEvent` có thể truy cập từ module khác, các class ở module đó có thể triển khai `ExternalEvent`, dù không nằm trong `permits Event`.

Ngược lại, nếu `ExternalEvent` tiếp tục được khai báo `sealed`, chính nó lại phải thiết lập tập con trực tiếp được phép, và các con đó phải tuân theo điều kiện named module/unnamed module tương ứng với nơi `ExternalEvent` được khai báo.

Như vậy, hãy hỏi **“Kiểu này kế thừa trực tiếp từ kiểu `sealed` nào?”** khi xác định liệu quy tắc còn áp dụng ở một cấp nào đó hay không.

## 8. Cách nhận diện và xử lý lỗi khi thực hành

| Tình huống | Điều cần xem | Cách xử lý |
| --- | --- | --- |
| Class được ghi trong `permits` nhưng vẫn bị báo sai package. | Có `module-info.java` thực sự được biên dịch theo named module hay mã đang chạy ở classpath/unnamed module? | Khi dùng unnamed module, đưa con trực tiếp vào **cùng package** với kiểu sealed. |
| Hai kiểu cùng tiền tố package nhưng bị từ chối. | `a.b` và `a.b.impl` là hai package khác nhau. | Dùng tên package giống **hệt nhau** hoặc đặt cả hai trong một named module. |
| Kiểu con khác package trong named module không truy cập được. | Kiểu có `public` không, tên dùng trong `permits` có đúng không, import có hợp lệ không? | Sửa quy tắc truy cập và tên kiểu; **cùng module** cho phép khác package nhưng không bỏ qua quy tắc `public`/package-private. |
| Kiểu ở module khác vẫn không được phép dù đã `exports` và `requires`. | Hai kiểu có thật sự nằm cùng named module không? | Chuyển con trực tiếp về cùng module hoặc thiết kế điểm mở rộng qua `non-sealed`. |
| Kiểu con nằm đúng chỗ nhưng vẫn lỗi. | Có `extends`/`implements` **trực tiếp** và modifier thích hợp chưa? | Bổ sung quan hệ kế thừa đúng, khai báo `final`, `sealed` hoặc `non-sealed` phù hợp. |
| Không hiểu vì sao ví dụ chạy bằng `-cp` khác ví dụ chạy bằng `--module-path`. | Kiểu đang thuộc unnamed module hay named module? | Dùng `module-info.java` và biên dịch/chạy theo module nếu cần mô hình named module; dùng classpath nếu đang học ví dụ unnamed module. |

**Lưu ý về đường dẫn chạy:** `-cp`/`--class-path` chỉ định classpath; `--module-path` chỉ định nơi tìm module. Một số JAR không có `module-info.class` có thể trở thành **automatic module** khi đặt trên module path, nên đừng kết luận module của một kiểu chỉ qua tên JAR hoặc tên package. Hai ví dụ chính phía trên cố ý sử dụng một named module có `module-info.java` và một ứng dụng classpath để phân biệt quy tắc rõ ràng.

## 9. Ghi nhớ qua ba câu hỏi

**1. `sealed interface` trong named module A có thể `permits` lớp ở package khác nhưng vẫn thuộc module A không?** Có, nếu kiểu con truy cập hợp lệ và trực tiếp `implements`/`extends` interface; khác package không cản trở trong cùng named module.

**2. `sealed class` trên classpath thuộc package `com.shop.core` có thể cho phép lớp con ở `com.shop.core.impl` không?** Không. Đây là hai package khác nhau; trong unnamed module, con trực tiếp phải ở `com.shop.core`.

**3. Thêm `exports`, `requires` hoặc `import` có giúp `permits` một kiểu con trực tiếp ở module khác không?** Không. Chúng ảnh hưởng đến khả năng nhìn thấy và sử dụng kiểu, không thay đổi ràng buộc cùng named module của sealed.

### Tài liệu tham khảo

- [JEP 409 — Sealed Classes (được hoàn thiện ở Java 17)](https://openjdk.org/jeps/409)
- [Java Language Specification 17 — §8.1.6 Sealed Classes](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.1.6)
- [Java Language Specification 17 — §9.1.4 Sealed Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.1.4)
- [Java Language Specification 17 — Modules](https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html#jls-7.7)
