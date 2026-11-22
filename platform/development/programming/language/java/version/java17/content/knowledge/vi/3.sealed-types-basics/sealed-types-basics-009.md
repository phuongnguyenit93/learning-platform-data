# Phân biệt phạm vi truy cập với quyền kế thừa trong Java 17

## 1. Hai câu hỏi khác nhau khi thiết kế một kiểu dữ liệu

Khi đọc một khai báo Java, cần tách hai câu hỏi:

1. **Ai có thể nhìn thấy và sử dụng kiểu hoặc thành viên này?** Đây là câu hỏi về **phạm vi truy cập** (*accessibility*), được điều khiển bằng `public`, `protected`, `private`, quyền truy cập mặc định theo package và, ở ranh giới module, khai báo `exports`.
2. **Kiểu nào được phép kế thừa hoặc triển khai trực tiếp kiểu này?** Đây là câu hỏi về **quyền kế thừa** (*inheritance permission*), được điều khiển bằng `final`, `sealed`, `permits`, `non-sealed`, cùng với những quy tắc khác của Java về kiểu cha và kiểu con.

Hai nhóm quy tắc cùng phải được thỏa mãn. Một lớp có thể **nhìn thấy** một lớp/interface `public` mà vẫn **không được phép extends/implements** kiểu `sealed` đó. Ngược lại, tên kiểu con được ghi trong `permits` cũng không được miễn các yêu cầu về khả năng truy cập, tính hợp lệ của quan hệ kế thừa hoặc phạm vi package/module.

Ví dụ tư duy:

> Một thư viện công bố `public sealed interface Result` để mọi ứng dụng đều có thể dùng `Result`. Nhưng thư viện chỉ cho phép vài kiểu kết quả được liệt kê trong `permits` triển khai trực tiếp interface này. **Công khai để sử dụng** không đồng nghĩa với **mở rộng tự do**.

Đây là ý nghĩa chính của `sealed` trong Java 17: giúp tác giả mô hình kiểm soát **tập kiểu con trực tiếp**, trong khi vẫn thiết kế API nhìn thấy được từ bên ngoài theo nhu cầu.

## 2. Phạm vi truy cập điều khiển điều gì?

### 2.1. Các mức truy cập quen thuộc

| Mức truy cập | Có thể áp dụng ở đâu? | Quy tắc chính |
|---|---|---|
| `public` | Kiểu top-level, kiểu lồng nhau, thành viên | Có thể truy cập từ nơi khác nếu kiểu bao ngoài và ranh giới module cũng cho phép |
| `protected` | Thành viên và kiểu thành viên lồng nhau (không dùng cho kiểu top-level) | Truy cập trong cùng package; ngoài package có quyền dành cho lớp con với những hạn chế về cách truy cập |
| *package-private* (không ghi modifier) | Kiểu top-level, kiểu lồng nhau, thành viên | Truy cập từ các lớp trong cùng package |
| `private` | Thành viên và kiểu lồng nhau (không dùng cho kiểu top-level) | Chỉ truy cập trong phạm vi khai báo/nest theo quy tắc ngôn ngữ |

**Chú ý:** đây là bảng quyền *truy cập tên kiểu hoặc thành viên*, không phải bảng quy định ai có quyền trở thành kiểu con.

Ví dụ một lớp thông thường:

```java
package demo.api;

public class Account {
    private long balance;

    public long balance() {
        return balance;
    }

    protected void validateChange(long amount) {
        if (amount < 0) {
            throw new IllegalArgumentException("Negative amount");
        }
    }
}
```

Mã bên ngoài package có thể dùng `Account` vì lớp `public` (nếu module có thể truy cập). Không thể đọc `balance` trực tiếp vì trường đó `private`. Một lớp con hợp lệ ở package khác có thể dùng `validateChange` theo quy tắc `protected`; nhưng `protected` không cho phép gọi phương thức này qua mọi đối tượng `Account` tùy ý từ bên ngoài package.

### 2.2. `public` còn chịu ảnh hưởng của Java Platform Module System

Trong dự án dùng **named module** (`module-info.java`), việc một kiểu khai báo `public` chưa đủ để mọi module khác dùng được. Package chứa kiểu đó còn phải được module xuất ra bằng `exports` (hoặc một cơ chế truy cập phù hợp).

```java
module example.api {
    exports demo.api;
}
```

Module khác phụ thuộc vào `example.api` mới có thể sử dụng những kiểu `public` trong `demo.api` theo quy tắc module. Quy tắc `exports` điều khiển **khả năng truy cập API qua ranh giới module**, không thay thế `sealed` hay tự động cấp quyền kế thừa.

Với ứng dụng chạy trên **classpath** (unnamed module), quy tắc package và các modifier vẫn áp dụng; không cần `module-info.java` để học sealed cơ bản.

## 3. Quyền kế thừa: `final`, `sealed`, `non-sealed`

Java 17 hỗ trợ `sealed` cho **class** và **interface** như một tính năng ngôn ngữ ổn định. Ba hướng thiết kế thông dụng:

| Khai báo | Ý nghĩa đối với việc tạo kiểu con |
|---|---|
| Lớp thông thường, không `final` và không `sealed` | Có thể được kế thừa nếu lớp con truy cập được và đáp ứng các quy tắc Java khác |
| `final class` | Không lớp nào được extends lớp đó |
| `sealed class` hoặc `sealed interface` | Chỉ những kiểu được phép mới có thể trực tiếp extends/implements |
| `non-sealed class` hoặc `non-sealed interface` | Mở lại khả năng tạo kiểu con ở nhánh đó; chỉ hợp lệ khi trực tiếp kế thừa/triển khai một kiểu `sealed` |

Với `sealed`, từ khóa `permits` liệt kê **các kiểu con trực tiếp được cho phép**. Mỗi kiểu con trực tiếp phải tự khai báo rõ hướng tiếp theo:

- **`final`**: đóng nhánh ở lớp con đó. Áp dụng với class; interface không được khai báo `final`.
- **`sealed`**: tiếp tục giới hạn tập kiểu con của nhánh.
- **`non-sealed`**: mở nhánh, cho các kiểu con tiếp theo kế thừa/triển khai theo những quy tắc Java thông thường.

Record class mặc nhiên là `final`; vì thế record có thể triển khai trực tiếp một sealed interface mà không cần thêm một modifier đóng nhánh. Tuy nhiên record không được extends một lớp nghiệp vụ tùy ý, vì record đã kế thừa `java.lang.Record`.

Ví dụ tổng quát:

```text
Payment (public sealed interface)
├── CashPayment (final class)
├── CardPayment (sealed interface)
│   ├── CreditCard (final class)
│   └── DebitCard (final class)
└── ExtensionPayment (non-sealed interface)
    └── ExternalPayment (class bất kỳ triển khai ExtensionPayment)
```

Danh sách `permits` của `Payment` chỉ cần nêu **ba nhánh trực tiếp**. `CreditCard`, `DebitCard` và `ExternalPayment` không phải là kiểu con trực tiếp của `Payment`.

### Điểm cần nhớ

`sealed` **không có nghĩa** là lớp tự động `private`, `final` hoặc `abstract`. Một lớp `sealed` bình thường vẫn có thể được khởi tạo trực tiếp nếu nó không `abstract` và có constructor truy cập được. Ngược lại, một lớp `abstract` không thể được tạo trực tiếp nhưng vẫn có thể mở quyền kế thừa nếu nó không bị `sealed` hoặc các giới hạn khác.

## 4. Ví dụ cốt lõi: kiểu `public`, implementation chỉ được chọn lọc

Giả sử ta công bố interface cho loại sự kiện của ứng dụng. Mã sau đặt trong tệp **`Event.java`**:

```java
package demo.events;

public sealed interface Event permits Started, Finished {
    String message();

    static Event started() {
        return new Started();
    }

    static Event finished() {
        return new Finished();
    }
}

final class Started implements Event {
    @Override
    public String message() {
        return "Started";
    }
}

final class Finished implements Event {
    @Override
    public String message() {
        return "Finished";
    }
}
```

Trong ví dụ này:

1. `Event` là `public`: mã ở package khác có thể khai báo biến, tham số và kiểu trả về `Event` khi package có thể truy cập.
2. `Event` là `sealed`: chỉ `Started` và `Finished` được triển khai **trực tiếp** `Event`.
3. `Started` và `Finished` là *package-private*: mã bên ngoài `demo.events` không được truy cập trực tiếp tên của hai lớp này, dù chúng nằm trong `permits`.
4. Hai lớp con là `final`, đáp ứng yêu cầu khai báo nhánh kế thừa của kiểu `sealed` và ngăn việc extends tiếp từ chúng.
5. Hai factory method `started()` và `finished()` của `Event` cung cấp đối tượng cho bên ngoài mà không buộc phải công khai các lớp implementation.

Ở một tệp **`App.java`** thuộc package khác:

```java
package demo.client;

import demo.events.Event;

public class App {
    public static void main(String[] args) {
        Event event = Event.started();     // Hợp lệ
        System.out.println(event.message());

        // new Started();                  // Không truy cập được lớp package-private
    }
}
```

Kết quả in ra là `Started`. Ví dụ làm rõ hai lớp kiểm soát độc lập: người dùng API được **nhận và xử lý một `Event`**, nhưng không thể tùy ý **tự thêm kiểu triển khai trực tiếp** vào tập kiểu do tác giả đã đóng.

### Điều gì xảy ra nếu `public` mà không nằm trong `permits`?

Ngay cả khi tạo lớp trong **cùng package**:

```java
package demo.events;

// Minh họa lỗi biên dịch: Unknown không nằm trong permits của Event.
public final class Unknown implements Event {
    @Override
    public String message() {
        return "Unknown";
    }
}
```

`Unknown` truy cập được `Event`, nhưng **không được phép triển khai trực tiếp** interface này. Việc đặt cùng package hoặc khai báo `public` không thay đổi danh sách `permits`.

Để cấp quyền, tác giả `Event` phải sửa chính thiết kế của sealed hierarchy (và tuân theo quy tắc package/module). Không có access modifier nào trên `Unknown` có thể tự vượt qua `permits`.

## 5. Quyền nhìn thấy kiểu không tự tạo quyền kế thừa

Xem bảng tình huống sau, giả sử không có các rào cản constructor, module hay giới hạn ngữ cảnh khác ngoài những điều được ghi:

| Kiểu cha | Mã bên ngoài package có thể dùng tên kiểu? | Có thể tạo lớp triển khai/kế thừa trực tiếp tùy ý? |
|---|---|---|
| `public interface Service` thông thường | Có, nếu package được truy cập | Thông thường có |
| `public sealed interface Service permits A, B` | Có, nếu package được truy cập | **Không**; chỉ `A`, `B` trực tiếp |
| `interface Service` package-private | Không | Chỉ từ nơi truy cập được interface, nếu interface không có giới hạn khác |
| `public final class Value` | Có, nếu package được truy cập | **Không**; `final` đóng mọi nhánh |
| `public non-sealed interface Extension` trực tiếp extends sealed interface | Có, nếu package được truy cập | Thông thường có; nhánh này đã mở |

**Mấu chốt:** `public` trả lời “ai dùng được kiểu?”, còn `sealed` và `permits` trả lời “ai được làm kiểu con trực tiếp?”. Quyền nhìn thấy kiểu cũng chỉ là một **điều kiện cần** để tạo lớp con; constructor, loại class/interface, quy tắc module và những điều kiện ngôn ngữ khác vẫn phải hợp lệ.

### Phân biệt thêm `protected` với `permits`

`protected` là access modifier cho thành viên/kiểu lồng nhau. Nó **không phải** cách liệt kê lớp con hợp lệ. Một constructor `protected` có thể cho phép lớp con gọi constructor của lớp cha, nhưng lớp con vẫn bị loại nếu không nằm trong `permits` của một lớp cha `sealed`.

```java
package demo.documents;

public sealed abstract class Document permits PdfDocument {
    protected Document() {}
}

final class PdfDocument extends Document {
    PdfDocument() {
        super(); // Truy cập được protected constructor.
    }
}
```

Ở đây có **hai điều kiện khác nhau**:

- `PdfDocument` được quyền `extends Document` do `Document` đã liệt kê nó trong `permits`.
- Constructor của `PdfDocument` gọi được `super()` do quy tắc truy cập `protected`.

Nếu một lớp khác không được liệt kê thử `extends Document`, constructor `protected` không giúp lớp đó vượt qua kiểm soát của `sealed`.

## 6. Ranh giới package và module của kiểu được `permits`

Không thể tùy ý đặt những kiểu con được phép ở bất kỳ đâu. Java 17 yêu cầu các **permitted direct subclasses/subinterfaces** nằm trong một phạm vi gắn với sealed type:

| Nơi khai báo sealed type | Vị trí hợp lệ của kiểu con trực tiếp được phép |
|---|---|
| Trong **named module** | Cùng **named module** với sealed type; có thể ở package khác nếu việc truy cập kiểu cha hợp lệ |
| Trong **unnamed module** (ví dụ classpath thông thường) | Cùng **package** với sealed type |

Đây là **ràng buộc riêng của `sealed`**, không phải quy tắc mà mọi lớp `public` thông thường đều gặp.

### 6.1. Ứng dụng classpath: cùng package

```java
// demo/shapes/Shape.java
package demo.shapes;

public sealed interface Shape permits Circle, Rectangle {}
```

```java
// demo/shapes/Circle.java
package demo.shapes;

public final class Circle implements Shape {}
```

```java
// demo/shapes/Rectangle.java
package demo.shapes;

public final class Rectangle implements Shape {}
```

Các lớp cùng package, nằm trong `permits` và có modifier nhánh thích hợp.

Một lớp ở `demo.external` không thể tự implements trực tiếp `Shape` dù `Shape` là `public`. Nếu sửa `permits` để nhắc tên một lớp ở package khác nhưng vẫn chạy trong **unnamed module**, khai báo vẫn vi phạm ràng buộc cùng package.

### 6.2. Named module: cùng module, có thể khác package

Trong một named module, ví dụ:

```text
src/main/java/
├── module-info.java
├── demo/api/Operation.java
└── demo/internal/DefaultOperation.java
```

`module-info.java`:

```java
module demo.module {
    exports demo.api;
}
```

`demo/api/Operation.java`:

```java
package demo.api;

public sealed interface Operation permits demo.internal.DefaultOperation {
    void run();
}
```

`demo/internal/DefaultOperation.java`:

```java
package demo.internal;

public final class DefaultOperation implements demo.api.Operation {
    @Override
    public void run() {
        System.out.println("Running");
    }
}
```

Hai kiểu ở package khác nhau nhưng **cùng named module**. `Operation` là `public`, nên `DefaultOperation` truy cập được nó trong module. Một module khách hàng có thể truy cập `demo.api.Operation` qua `exports demo.api`, song không thể tự đăng ký một lớp triển khai trực tiếp mới: lớp của module đó nằm **ngoài module đã khai báo `Operation`**.

Lưu ý tinh tế: `DefaultOperation` được khai báo `public` để có thể tham gia quan hệ implements qua package, nhưng package `demo.internal` không được `exports`; mã trong module khác thường không thể sử dụng tên `demo.internal.DefaultOperation` trực tiếp. **`public` của kiểu**, **`exports` của package** và **`permits` của sealed type** là ba tầng kiểm soát khác nhau.

Nếu dự án chưa dùng named module, chỉ cần hiểu và áp dụng quy tắc **cùng package**; không phải chuyển toàn bộ dự án sang module system chỉ để sử dụng sealed.

## 7. `permits` chỉ quản lý cấp kế thừa trực tiếp

Ví dụ một API cần cho phép bên thứ ba viết các loại plugin nhưng vẫn giữ lõi API đóng:

```java
package demo.payments;

public sealed interface Payment permits CashPayment, ExtensionPayment {}

final class CashPayment implements Payment {}

public non-sealed interface ExtensionPayment extends Payment {}
```

Đoạn trên biểu thị ý tưởng; trong Java mỗi kiểu top-level `public` phải nằm trong tệp nguồn có tên tương ứng. Vì vậy, nếu viết thành mã nguồn thật, cần tách `Payment` và `ExtensionPayment` vào `Payment.java` và `ExtensionPayment.java` (và để `CashPayment` ở một tệp hợp lệ hoặc cùng tệp có một `public` type).

Một lớp có thể ở package khác và triển khai **`ExtensionPayment`**, nếu kiểu này truy cập được:

```java
package demo.plugins;

import demo.payments.ExtensionPayment;

public final class MobilePayment implements ExtensionPayment {}
```

`MobilePayment` không được khai báo trong `Payment.permits`, bởi nó **không trực tiếp implements `Payment`**; nhánh được phép trực tiếp là `ExtensionPayment`, và nhánh này đã được mở bằng `non-sealed`. Việc `MobilePayment` gián tiếp là một `Payment` hoàn toàn hợp lệ.

Điều này cho thấy sealed hierarchy có thể vừa đóng phần lõi, vừa chủ động tạo “điểm mở rộng” ở một nhánh được chỉ định. Nếu không muốn bất kỳ kiểu kế thừa tiếp nào, thay nhánh bằng một `final class` (đối với class) hoặc tiếp tục một interface `sealed` với danh sách con rõ ràng.

## 8. Các lỗi nhầm lẫn thường gặp

### Nhầm lẫn 1: “`public` nghĩa là ai cũng có thể `extends`”

**Sai.** `public` nói về khả năng truy cập. `public final class` không thể được kế thừa; `public sealed class` chỉ cho phép các kiểu trong `permits`; `public sealed interface` không thể được triển khai trực tiếp tùy ý.

### Nhầm lẫn 2: “Cứ đặt tên vào `permits` là xong”

**Chưa đủ.** Kiểu con phải thực sự extends/implements **trực tiếp**, phải truy cập được kiểu cha, ở cùng phạm vi package/module theo quy tắc sealed, và phải có modifier xác định trạng thái nhánh (`final`, `sealed` hoặc `non-sealed`, với ngoại lệ cú pháp phù hợp cho một số kiểu như record).

### Nhầm lẫn 3: “`private` hoặc `protected` tương đương `sealed`”

**Sai.** Access modifier quyết định khả năng gọi, nhìn thấy hoặc kế thừa được thành viên trong ngữ cảnh cụ thể; nó không tạo **danh sách định danh kiểu con được phép**. Ngay cả khi constructor có thể gọi được, `sealed` vẫn có thể chặn việc khai báo một kiểu con không được phép.

### Nhầm lẫn 4: “Lớp con được phép thì mọi lớp cháu đều phải có trong `permits`”

**Sai.** `permits` chỉ liệt kê kiểu con **trực tiếp**. Nếu một nhánh được khai báo `non-sealed`, các kiểu con gián tiếp của sealed root không cần xuất hiện trong danh sách của root.

### Nhầm lẫn 5: “`sealed` bảo vệ toàn bộ trạng thái đối tượng”

**Sai.** `sealed` kiểm soát **cây kế thừa**, không tự biến các field thành `private`, không đảm bảo bất biến, không thay thế validation, authorization hoặc bảo mật đầu vào. Một sealed class vẫn có thể chứa trạng thái mutable nếu tác giả thiết kế như vậy.

### Nhầm lẫn 6: “Có thể dùng pattern matching cho `switch` mặc định trong Java 17”

**Không đúng với chương trình Java 17 thông thường.** Ở Java 17, pattern matching cho `switch` vẫn thuộc nhóm preview; không nên đưa vào ví dụ yêu cầu Java 17 ổn định mà không nói rõ điều kiện bật preview. Sealed types bản thân đã là tính năng **final** trong Java 17. Khi cần phân loại đối tượng trong ví dụ Java 17, có thể dùng pattern matching cho `instanceof` (đã ổn định từ Java 16).

## 9. Bài tập thực hành

### Bài 1: Xác định lỗi theo đúng nhóm quy tắc

Giả sử hai lớp ở cùng package:

```java
public sealed interface Message permits TextMessage {}

final class TextMessage implements Message {}
```

Xét các tình huống:

1. Một lớp ở package khác khai báo biến `Message msg;`.
2. Một lớp ở package khác thử `new TextMessage()`.
3. Một lớp ở cùng package khai báo `final class ImageMessage implements Message {}`.
4. Một phương thức `public static Message text()` nằm trong `Message` trả về `new TextMessage()`.

**Lời giải:**

1. Được, nếu `Message` truy cập được từ package đó; biến có kiểu `Message` không làm phát sinh kiểu con mới.
2. Không được, vì `TextMessage` có phạm vi truy cập mặc định trong package; lỗi thuộc **accessibility**.
3. Không được, vì `ImageMessage` không được `permits`; lỗi thuộc **quyền kế thừa**, dù cùng package.
4. Được, vì factory nằm ở nơi truy cập được `TextMessage` và trả về kiểu `Message` công khai.

### Bài 2: Thiết kế API đóng với điểm mở rộng

Yêu cầu: loại `Response` công khai, chỉ có hai nhóm trực tiếp: `Success` do thư viện quản lý và `CustomResponse` cho extension. Người dùng được triển khai các kiểu thuộc nhánh extension mà không sửa mã lõi.

Một phương án:

```java
// Response.java
package demo.response;
public sealed interface Response permits Success, CustomResponse {}
```

```java
// Success.java
package demo.response;
public final class Success implements Response {}
```

```java
// CustomResponse.java
package demo.response;
public non-sealed interface CustomResponse extends Response {}
```

```java
// Ngoài package demo.response, có quyền truy cập CustomResponse
package client;
import demo.response.CustomResponse;
public final class PartnerResponse implements CustomResponse {}
```

Giải thích: `Response` cho mọi người **sử dụng** kiểu gốc; hai nhánh `Success` và `CustomResponse` được **phép trực tiếp**; `Success` đóng, `CustomResponse` mở. `PartnerResponse` triển khai `CustomResponse`, trở thành `Response` gián tiếp.

### Bài 3: Đọc khai báo trước khi quyết định mở rộng

Khi nhìn thấy một API sealed, lần lượt trả lời:

1. Kiểu cha có truy cập được ở package/module đang viết mã không?
2. Muốn extends/implements **trực tiếp** hay thông qua một nhánh `non-sealed`?
3. Nếu trực tiếp, tên kiểu mới có trong `permits` không và có nằm đúng package/module không?
4. Kiểu con là class, interface hay record; modifier nhánh có hợp lệ không?
5. Nếu là class, constructor của lớp cha có gọi được không?

Trả lời theo thứ tự giúp phân biệt lỗi do **không nhìn thấy API**, lỗi do **không được phép kế thừa** và lỗi do **điều kiện khác của ngôn ngữ**.

## 10. Khi nào nên sử dụng `sealed`?

Sealed type phù hợp khi miền nghiệp vụ có **một tập nhánh cốt lõi được kiểm soát**: kết quả xử lý thành công/thất bại, trạng thái giao dịch, biểu thức trong cây cú pháp hoặc nhóm thông điệp có định nghĩa rõ ràng. Nó giúp người đọc hiểu những khả năng triển khai trực tiếp mà thư viện công nhận; tác giả có thể công bố API gốc mà vẫn kiểm soát cách mở rộng cấu trúc kiểu.

Không nhất thiết dùng `sealed` cho mọi interface. Nếu mục tiêu thực sự là cho người dùng tạo implementation mới ở bất kỳ dự án nào, một interface thông thường hoặc một nhánh `non-sealed` được chủ động công khai thường phù hợp hơn. Còn nếu cần ngăn mọi lớp con của một implementation, dùng `final class`.

Cần cân nhắc khả năng phát triển thư viện: thêm một nhánh vào `permits`, thay đổi nhánh từ `final` sang `non-sealed` hoặc thay đổi public API có thể ảnh hưởng đến mã phụ thuộc. Chọn sealed hierarchy theo hợp đồng dài hạn của miền dữ liệu, thay vì chỉ vì cú pháp mới.

## 11. Ghi nhớ và tài liệu tra cứu

- **Access modifier**: ai có thể truy cập kiểu, thành viên, constructor?
- **`exports` của module**: package nào được công bố cho module khác?
- **`sealed` + `permits`**: những kiểu nào được phép kế thừa/triển khai **trực tiếp**?
- **`final` / `sealed` / `non-sealed` tại kiểu con**: nhánh đó sẽ đóng, tiếp tục giới hạn hay mở rộng?
- **Ranh giới Java 17**: các quy tắc sealed ở đây là tính năng ổn định trong Java 17; không cần tính năng preview.

Để đọc quy tắc ngôn ngữ gốc, xem [Java Language Specification 17 — Classes](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html), [Java Language Specification 17 — Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html), [Java Language Specification 17 — Modules and Packages](https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html) và [OpenJDK JEP 409: Sealed Classes](https://openjdk.org/jeps/409).
