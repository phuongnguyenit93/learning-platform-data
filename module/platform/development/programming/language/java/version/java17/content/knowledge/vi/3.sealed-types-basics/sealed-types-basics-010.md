# Lỗi biên dịch thường gặp với `sealed` trong Java 17 và ví dụ đối chiếu

`sealed` là cơ chế **giới hạn những kiểu nào được phép kế thừa một lớp hoặc triển khai một interface**. Đây là tính năng chính thức của Java 17. Khi một `sealed class` hoặc `sealed interface` khai báo tập các kiểu con trực tiếp được phép, trình biên dịch có thể phát hiện sớm nhiều lỗi trong thiết kế hệ phân cấp kiểu.

Bài này tập trung vào **những lỗi biên dịch thường gặp** và cách đối chiếu giữa **mã sai** với **mã đúng**, trong phạm vi Java 17. Các đoạn mã đánh dấu “Sai” được cố ý viết để gây lỗi; mỗi ví dụ nên được thử riêng vì những ví dụ đó không thể biên dịch chung.

## 1. Nhắc lại quy tắc cần nhớ trước khi xem lỗi

Một kiểu được khai báo `sealed` sẽ đặt ra các quy tắc cho **kiểu con trực tiếp** của nó:

1. Kiểu con trực tiếp phải thuộc danh sách trong mệnh đề `permits`, hoặc thuộc danh sách được trình biên dịch suy ra trong cùng một *compilation unit* (thường là cùng tệp `.java`).
2. Một `class` kế thừa trực tiếp `sealed class` hoặc triển khai trực tiếp `sealed interface` phải khai báo rõ một trong ba trạng thái **`final`**, **`sealed`**, **`non-sealed`**; riêng `record` vốn đã ngầm định `final`.
3. Các kiểu con được phép phải thực sự `extends` hoặc `implements` **trực tiếp** kiểu `sealed` đó.
4. Nếu thuộc **named module**, các kiểu con trực tiếp phải nằm trong **cùng module** với kiểu `sealed`. Nếu thuộc **unnamed module** (dự án không khai báo module), các kiểu con trực tiếp phải nằm trong **cùng package**.

Ý nghĩa của ba lựa chọn cho kiểu con trực tiếp:

| Từ khóa | Ý nghĩa | Có thể mở rộng tiếp không? |
| --- | --- | --- |
| `final` | Khóa nhánh kế thừa ở lớp con đó. | Không thể có lớp kế thừa tiếp từ lớp `final`. |
| `sealed` | Tiếp tục kiểm soát danh sách kiểu con trực tiếp ở cấp kế tiếp. | Có, nhưng chỉ với các kiểu con được phép tại cấp đó. |
| `non-sealed` | Mở lại khả năng kế thừa/triển khai thông thường cho nhánh đó. | Có, theo các quy tắc kế thừa Java thông thường. |

> `permits` chỉ kiểm soát **quan hệ kế thừa hoặc triển khai trực tiếp**. Nó không liệt kê mọi kiểu con gián tiếp trong toàn bộ cây kế thừa.

## 2. Mẫu hợp lệ làm mốc đối chiếu

Lưu mã dưới đây vào tệp **`SealedDemo.java`**:

```java
sealed interface Payment permits CashPayment, CardPayment, PartnerPayment {
}

record CashPayment(int amount) implements Payment {
    // record ngầm định final nên không cần ghi "final".
}

final class CardPayment implements Payment {
}

non-sealed class PartnerPayment implements Payment {
}

final class FastPartnerPayment extends PartnerPayment {
    // Đây là con gián tiếp của Payment; không cần nằm trong permits.
}

public class SealedDemo {
    public static void main(String[] args) {
        Payment[] payments = {
                new CashPayment(100),
                new CardPayment(),
                new PartnerPayment(),
                new FastPartnerPayment()
        };

        for (Payment payment : payments) {
            System.out.println(payment.getClass().getSimpleName());
        }
    }
}
```

Biên dịch và chạy bằng JDK 17 hoặc một JDK hỗ trợ đích Java 17:

```bash
mkdir out
javac --release 17 -encoding UTF-8 -d out SealedDemo.java
java -cp out SealedDemo
```

Kết quả dự kiến:

```text
CashPayment
CardPayment
PartnerPayment
FastPartnerPayment
```

Lưu ý các chi tiết sau:

- `Payment` là `sealed interface`, chỉ cho phép ba kiểu triển khai **trực tiếp**: `CashPayment`, `CardPayment` và `PartnerPayment`.
- `CashPayment` là `record`, được coi là `final`; có thể trực tiếp triển khai `sealed interface` mà không cần viết thêm `final`.
- `CardPayment` dùng `final` để kết thúc nhánh.
- `PartnerPayment` dùng `non-sealed`, nên `FastPartnerPayment` được phép kế thừa nó. `FastPartnerPayment` không triển khai `Payment` trực tiếp, vì vậy không xuất hiện trong `permits`.

Các ví dụ lỗi dưới đây lần lượt thay đổi từng quy tắc của mẫu này.

## 3. Lỗi 1: Kiểu con trực tiếp không có trong `permits`

**Sai — `TextFile` triển khai trực tiếp `FileType` nhưng không được cho phép:**

```java
sealed interface FileType permits PdfFile {
}

final class PdfFile implements FileType {
}

final class TextFile implements FileType { // LỖI
}
```

`TextFile` triển khai trực tiếp `FileType`, trong khi danh sách `permits` chỉ chứa `PdfFile`. Trình biên dịch từ chối vì `TextFile` không phải một kiểu con được phép. Thông báo lỗi có thể có nội dung tương đương `class is not allowed to extend sealed class`; cách diễn đạt phụ thuộc JDK và môi trường biên dịch.

**Đúng — bổ sung kiểu con trực tiếp vào danh sách:**

```java
sealed interface FileType permits PdfFile, TextFile {
}

final class PdfFile implements FileType {
}

final class TextFile implements FileType {
}
```

**Cách nhận diện:** Nếu thấy lỗi về một kiểu không được phép kế thừa `sealed`, hãy xem ngay khai báo `extends`/`implements` của kiểu đó và đối chiếu với `permits` của kiểu cha.

## 4. Lỗi 2: Quên `final`, `sealed` hoặc `non-sealed` ở kiểu con trực tiếp

**Sai — lớp `EmailTask` chưa nêu cách xử lý nhánh kế thừa tiếp theo:**

```java
sealed interface Task permits EmailTask {
}

class EmailTask implements Task { // LỖI
}
```

Một lớp trực tiếp triển khai `sealed interface` không được để trạng thái kế thừa ở dạng mặc định. Trình biên dịch yêu cầu lớp này khai báo một trong ba từ khóa: `final`, `sealed` hoặc `non-sealed`.

**Đúng — nếu không muốn có lớp con:**

```java
sealed interface Task permits EmailTask {
}

final class EmailTask implements Task {
}
```

**Đúng — nếu muốn mở nhánh kế thừa:**

```java
sealed interface Task permits EmailTask {
}

non-sealed class EmailTask implements Task {
}

class ScheduledEmailTask extends EmailTask {
}
```

**Đúng — nếu muốn kiểm soát thêm một cấp:**

```java
sealed interface Task permits EmailTask {
}

sealed class EmailTask implements Task permits ScheduledEmailTask {
}

final class ScheduledEmailTask extends EmailTask {
}
```

Nếu trực tiếp triển khai `sealed interface` bằng `record`, không cần ba từ khóa trên vì `record` vốn là kiểu `final`:

```java
sealed interface Task permits EmailTask {
}

record EmailTask(String recipient) implements Task {
}
```

## 5. Lỗi 3: Đưa một kiểu vào `permits` nhưng kiểu đó không kế thừa trực tiếp

**Sai — `Printer` được nêu trong `permits` nhưng không `extends Device`:**

```java
sealed class Device permits Printer {
}

final class Printer { // LỖI
}
```

Khai báo `permits Printer` không tự tạo quan hệ kế thừa. Danh sách `permits` chỉ xác nhận **kiểu nào được phép** kế thừa; bản thân kiểu đó vẫn phải khai báo quan hệ `extends` hoặc `implements`.

**Đúng:**

```java
sealed class Device permits Printer {
}

final class Printer extends Device {
}
```

Cùng nguyên tắc áp dụng với interface:

```java
sealed interface Device permits Printer {
}

final class Printer implements Device {
}
```

Một lỗi liên quan là đưa **cháu** (kiểu con gián tiếp) vào `permits` của ông/bà dù cháu không trực tiếp kế thừa. Mỗi cấp `sealed` chỉ khai báo các kiểu con **trực tiếp của chính cấp đó**.

## 6. Lỗi 4: Kết hợp các modifier kế thừa xung đột

Các trạng thái `final`, `sealed` và `non-sealed` biểu thị những chính sách khác nhau, vì vậy không dùng đồng thời hai trạng thái đó cho cùng một lớp.

**Sai — cùng lúc đóng hoàn toàn và tiếp tục niêm phong một lớp:**

```java
final sealed class Message permits TextMessage { // LỖI
}

final class TextMessage extends Message {
}
```

**Đúng — chọn một chính sách:**

```java
sealed class Message permits TextMessage {
}

final class TextMessage extends Message {
}
```

Tương tự, `final non-sealed class` và `sealed non-sealed class` là tổ hợp modifier không hợp lệ.

Cần phân biệt với `abstract`: một lớp `sealed` **có thể đồng thời là `abstract`**, vì hai modifier đó không mâu thuẫn:

```java
abstract sealed class Message permits TextMessage {
    abstract String content();
}

final class TextMessage extends Message {
    @Override
    String content() {
        return "Hello";
    }
}
```

`abstract` quy định lớp không thể khởi tạo trực tiếp và có thể khai báo phương thức trừu tượng; `sealed` quy định ai được phép kế thừa lớp.

## 7. Lỗi 5: Dùng `non-sealed` khi không có cha trực tiếp `sealed`

`non-sealed` không phải một modifier tùy ý dùng với mọi lớp. Nó chỉ phù hợp với một lớp hoặc interface là **kiểu con trực tiếp của một kiểu `sealed`**.

**Sai:**

```java
class Base {
}

non-sealed class Child extends Base { // LỖI
}
```

`Base` là lớp thông thường; `Child` không có cha trực tiếp nào là `sealed`, nên `non-sealed` không hợp lệ.

**Đúng — nếu chỉ muốn kế thừa thông thường:**

```java
class Base {
}

class Child extends Base {
}

class Grandchild extends Child {
}
```

**Đúng — nếu thực sự đang mở lại nhánh từ kiểu `sealed`:**

```java
sealed class Base permits Child {
}

non-sealed class Child extends Base {
}

class Grandchild extends Child {
}
```

Với interface, quy tắc cũng tương tự:

```java
sealed interface Plugin permits ExternalPlugin {
}

non-sealed interface ExternalPlugin extends Plugin {
}

class CustomPlugin implements ExternalPlugin {
}
```

## 8. Lỗi 6: Hiểu sai phạm vi `permits` đối với kiểu con gián tiếp

Xét cây kế thừa:

```text
sealed interface Operation
       |
       +-- final class SaveOperation
       |
       +-- non-sealed class CustomOperation
                    |
                    +-- final class AuditOperation
```

**Đúng — kiểu con gián tiếp không cần kê khai trong `Operation.permits`:**

```java
sealed interface Operation permits SaveOperation, CustomOperation {
}

final class SaveOperation implements Operation {
}

non-sealed class CustomOperation implements Operation {
}

final class AuditOperation extends CustomOperation {
}
```

**Sai — `AuditOperation` cố triển khai `Operation` trực tiếp ngoài danh sách cho phép:**

```java
sealed interface Operation permits SaveOperation, CustomOperation {
}

final class SaveOperation implements Operation {
}

non-sealed class CustomOperation implements Operation {
}

final class AuditOperation implements Operation { // LỖI
}
```

Sự khác biệt là quan hệ `extends CustomOperation` so với `implements Operation`. Một nhánh `non-sealed` có thể có nhiều lớp con, nhưng lớp mới không được bỏ qua nhánh trung gian để trở thành một kiểu con trực tiếp chưa được cấp phép.

Ngoài ra, nếu nhánh trực tiếp khai báo `final` thay vì `non-sealed`, mọi nỗ lực `extends` lớp `final` đó sẽ tạo một lỗi kế thừa riêng (`cannot inherit from final`).

## 9. Lỗi 7: Khai báo `sealed` mà không có kiểu con hợp lệ để cho phép

Khi không viết `permits`, `javac` chỉ có thể suy ra các kiểu con trực tiếp được khai báo **trong cùng compilation unit** với kiểu `sealed`.

**Sai — hai tệp nguồn khác nhau mà không khai báo `permits`:**

Tệp `Animal.java`:

```java
public sealed interface Animal {
}
```

Tệp `Dog.java`:

```java
public final class Dog implements Animal {
}
```

Dù biên dịch hai tệp cùng lúc, `Animal` vẫn không có danh sách kiểu con được phép hợp lệ: không có `permits` tường minh và `Dog` không nằm trong cùng compilation unit. Lỗi có thể được báo ở `Animal` và/hoặc quan hệ `implements` của `Dog`.

**Đúng — hai tệp riêng, khai báo tường minh:**

`Animal.java`:

```java
public sealed interface Animal permits Dog {
}
```

`Dog.java`:

```java
public final class Dog implements Animal {
}
```

**Đúng — một compilation unit, có thể bỏ `permits`:**

Tệp `Animal.java`:

```java
public sealed interface Animal {
}

final class Dog implements Animal {
}
```

Trường hợp sau dùng tính năng **suy ra danh sách kiểu con**, không phải mở quyền triển khai vô hạn. Khi chuyển kiểu con sang tệp khác, nên thêm `permits` một cách tường minh.

## 10. Lỗi 8: Kiểu con nằm sai package hoặc module

Một trong những lỗi khó nhận biết là tập kiểu con đã đúng tên nhưng đặt ở phạm vi không cho phép.

### 10.1. Dự án dùng unnamed module: yêu cầu cùng package

**Sai — hai package khác nhau trong dự án không khai báo `module-info.java`:**

`src/api/Request.java`:

```java
package api;

public sealed interface Request permits impl.HttpRequest {
}
```

`src/impl/HttpRequest.java`:

```java
package impl;

public final class HttpRequest implements api.Request {
}
```

Mặc dù `HttpRequest` có trong `permits` và triển khai `Request` trực tiếp, Java 17 không chấp nhận vì hai kiểu thuộc **hai package khác nhau trong unnamed module**.

**Đúng — đặt cùng package:** 

`src/api/Request.java`:

```java
package api;

public sealed interface Request permits HttpRequest {
}
```

`src/api/HttpRequest.java`:

```java
package api;

public final class HttpRequest implements Request {
}
```

Biên dịch:

```bash
javac --release 17 -d out src/api/Request.java src/api/HttpRequest.java
```

Cả hai thuộc package `api` nên đáp ứng điều kiện của unnamed module.

### 10.2. Named module: có thể khác package, nhưng phải cùng module

Nếu dự án **có module được khai báo tường minh**, kiểu `sealed` và các kiểu con trực tiếp được phép nằm trong các package khác nhau **miễn là cùng named module**.

Cấu trúc ví dụ:

```text
src/
├── module-info.java
└── shop/
    ├── api/
    │   └── Request.java
    └── impl/
        └── HttpRequest.java
```

`src/module-info.java`:

```java
module shop.core {
    exports shop.api;
}
```

`src/shop/api/Request.java`:

```java
package shop.api;

public sealed interface Request permits shop.impl.HttpRequest {
}
```

`src/shop/impl/HttpRequest.java`:

```java
package shop.impl;

public final class HttpRequest implements shop.api.Request {
}
```

Biên dịch:

```bash
javac --release 17 -d out src/module-info.java src/shop/api/Request.java src/shop/impl/HttpRequest.java
```

Trong ví dụ này, `shop.api.Request` và `shop.impl.HttpRequest` cùng thuộc module `shop.core`. Không thể chuyển riêng `HttpRequest` sang một **named module khác** rồi vẫn xem nó là con trực tiếp hợp lệ của `Request`.

## 11. Lỗi 9: Đánh dấu `sealed` ở cấp tiếp theo nhưng quên khai báo nhánh tiếp theo

Một kiểu con trực tiếp có thể tiếp tục khai báo `sealed`. Tuy nhiên, ở cấp mới đó, chính kiểu con lại phải có danh sách con trực tiếp hợp lệ.

**Sai — `Approved` là `sealed` nhưng không có kiểu con được phép:**

```java
sealed interface Review permits Approved {
}

sealed class Approved implements Review { // LỖI
}
```

`Approved` chưa có nhánh con nào cùng compilation unit để suy ra và cũng không khai báo `permits` riêng.

**Đúng — nếu đây là nhánh cuối cùng, dùng `final`:**

```java
sealed interface Review permits Approved {
}

final class Approved implements Review {
}
```

**Đúng — nếu cần niêm phong thêm một cấp:**

```java
sealed interface Review permits Approved {
}

sealed class Approved implements Review permits AutoApproved {
}

final class AutoApproved extends Approved {
}
```

Lưu ý: `AutoApproved` là con trực tiếp của `Approved`, không phải con trực tiếp của `Review`, nên không xuất hiện trong danh sách `Review.permits`.

## 12. Lỗi 10: Biên dịch sealed với mức ngôn ngữ không hỗ trợ Java 17

`sealed` và `non-sealed` trở thành tính năng ngôn ngữ **chính thức trong Java 17**. Nếu đặt mức phát hành cũ, trình biên dịch không chấp nhận mã sealed theo quy tắc Java 17.

Ví dụ sau giả sử đã tạo tệp `SealedDemo.java` ở phần 2:

```bash
# Sai mục tiêu phát hành cho ví dụ Java 17:
javac --release 11 -d out SealedDemo.java

# Đúng mục tiêu:
javac --release 17 -d out SealedDemo.java
```

Nếu lệnh dùng `--release 17` lại báo `release version 17 not supported`, nguyên nhân là **phiên bản `javac` đang được gọi không hỗ trợ đích 17**; hãy kiểm tra:

```bash
javac -version
javac --help
```

Chọn một JDK hỗ trợ `--release 17` và bảo đảm terminal/IDE/build tool thực sự đang dùng đúng JDK đó.

## 13. Dễ nhầm với lỗi của `switch` sử dụng pattern matching

Một người học có thể tạo sealed hierarchy đúng nhưng sau đó viết `switch` xử lý theo kiểu và thấy lỗi biên dịch. Lúc này lỗi có thể đến từ **cú pháp `switch`**, không phải từ `sealed`.

Ví dụ:

```java
sealed interface Shape permits Circle, Rectangle {
}

record Circle(double radius) implements Shape {
}

record Rectangle(double width, double height) implements Shape {
}

class ShapePrinter {
    static String describe(Shape shape) {
        return switch (shape) {
            case Circle c -> "Circle: " + c.radius();
            case Rectangle r -> "Rectangle: " + r.width();
        };
    }
}
```

Ở **Java 17**, pattern matching trong `switch` vẫn là tính năng *preview*, vì vậy đoạn này không biên dịch bằng lệnh Java 17 thông thường nếu không bật preview. Việc `Shape` là `sealed` không tự bật preview hay biến mọi mẫu `switch` thành cú pháp chính thức của Java 17.

**Cách viết phù hợp với Java 17, không cần preview:** dùng pattern matching với `instanceof`, vốn đã là tính năng chính thức:

```java
sealed interface Shape permits Circle, Rectangle {
}

record Circle(double radius) implements Shape {
}

record Rectangle(double width, double height) implements Shape {
}

class ShapePrinter {
    static String describe(Shape shape) {
        if (shape instanceof Circle c) {
            return "Circle: " + c.radius();
        }

        if (shape instanceof Rectangle r) {
            return "Rectangle: " + r.width();
        }

        throw new IllegalArgumentException("Unexpected shape: " + shape);
    }
}
```

Trong phiên bản `if` này, trình biên dịch **không kiểm tra tính đầy đủ của các nhánh theo cách một `switch` hỗ trợ exhaustive pattern matching có thể làm**. Nếu sau này thêm một kiểu `Shape` mới được phép, lập trình viên cần xem lại logic xử lý thủ công. Đây là khác biệt giữa quy tắc đóng hệ phân cấp bằng `sealed` và quy tắc kiểm soát nhánh của từng cấu trúc điều khiển.

## 14. Bảng tra nhanh: lỗi nào thì xem quy tắc nào?

| Dấu hiệu lỗi | Nguyên nhân nên kiểm tra | Hướng sửa phổ biến |
| --- | --- | --- |
| `class is not allowed to extend sealed class` hoặc tương đương | Một kiểu con trực tiếp không nằm trong `permits` hợp lệ. | Thêm đúng kiểu vào `permits` hoặc sửa quan hệ kế thừa. |
| Thiếu một trong các modifier `final`, `sealed`, `non-sealed` | Một lớp trực tiếp kế thừa/triển khai `sealed` vẫn để trạng thái kế thừa mặc định. | Chọn chính sách kế thừa của lớp con. |
| `invalid permits clause` | Tên trong `permits` không phải kiểu con trực tiếp hợp lệ, hoặc phạm vi module/package không cho phép. | Đối chiếu `extends`/`implements` và tổ chức source/module. |
| `non-sealed modifier not allowed here` | `non-sealed` không gắn với kiểu có cha trực tiếp `sealed`. | Bỏ `non-sealed` hoặc sửa quan hệ với cha `sealed` thật sự. |
| `illegal combination of modifiers` | Ghép `final`, `sealed`, `non-sealed` không hợp lệ. | Chỉ chọn một chính sách kế thừa phù hợp. |
| `sealed class must have subclasses` hoặc tương đương | Không có kiểu con trực tiếp được phép tường minh hoặc suy ra hợp lệ. | Thêm kiểu con và `permits` phù hợp, hoặc cân nhắc bỏ `sealed`. |
| Không được mở rộng ở package khác | Dùng unnamed module mà kiểu con trực tiếp ở package khác. | Đặt cùng package hoặc thiết kế named module phù hợp. |
| `preview features are disabled by default` tại `switch` | Viết pattern matching cho `switch` trên Java 17 mà chưa bật preview. | Dùng `instanceof` pattern matching nếu muốn mã Java 17 không phụ thuộc preview. |
| `release version 17 not supported` | `javac` được chọn không hỗ trợ mức đích 17. | Dùng JDK có hỗ trợ `--release 17`. |

Nội dung thông báo có thể thay đổi giữa các bản `javac`; cách xác định nguyên nhân vẫn dựa vào **kiểu con trực tiếp**, **modifier**, **`permits`** và **phạm vi module/package**.

## 15. Cách tự cô lập lỗi khi thực hành

Khi có một ví dụ sealed không biên dịch, thay vì sửa nhiều nơi cùng lúc, hãy kiểm tra theo thứ tự:

1. **Phiên bản Java:** Kiểm tra `javac -version` và biên dịch theo `--release 17`.
2. **Quan hệ trực tiếp:** Xác định kiểu đang dùng `extends` hoặc `implements` trỏ đến kiểu `sealed` nào.
3. **Danh sách kiểu cho phép:** Kiểm tra `permits` của kiểu `sealed` đó; nếu không có `permits`, kiểm tra điều kiện suy ra trong cùng compilation unit.
4. **Modifier của lớp con:** Chọn một trạng thái `final`, `sealed` hoặc `non-sealed`; với `record` thì trạng thái `final` đã có sẵn.
5. **Cấp niêm phong tiếp theo:** Nếu lớp con lại `sealed`, đảm bảo nó có kiểu con trực tiếp hợp lệ của riêng nó.
6. **Package/module:** Với unnamed module, phải cùng package; với named module, phải cùng module.
7. **Tính năng ngôn ngữ khác:** Nếu lỗi nằm ở `switch` hoặc một cú pháp mới, tách biệt lỗi đó với các quy tắc của `sealed`.

Để thực hành đối chiếu, hãy lưu từng ví dụ “Sai” vào tệp độc lập, quan sát thông báo của `javac`, sau đó thay bằng biến thể “Đúng” ngay phía dưới và biên dịch lại. Không ghép tất cả ví dụ vào cùng thư mục/package cùng lúc vì nhiều ví dụ cố ý trùng tên kiểu (`Task`, `Request`, `Shape`, v.v.).

Nắm vững ba câu hỏi — **“Ai được phép làm con trực tiếp?”**, **“Con đó tiếp tục kế thừa theo cách nào?”** và **“Các kiểu có nằm đúng module/package không?”** — sẽ giúp xác định phần lớn lỗi biên dịch liên quan tới `sealed` trong Java 17.
