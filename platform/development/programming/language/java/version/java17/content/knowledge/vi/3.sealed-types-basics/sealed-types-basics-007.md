# Vai trò của `final`, `sealed` và `non-sealed` ở lớp con trong Java 17

Khi một lớp hoặc interface được khai báo `sealed`, Java chỉ cho phép những kiểu được chỉ định kế thừa hoặc triển khai trực tiếp kiểu đó. Nhưng việc kiểm soát **không dừng ở danh sách `permits`**: mỗi lớp con trực tiếp còn phải thể hiện rõ nhánh kế thừa của mình sẽ **kết thúc**, **tiếp tục bị giới hạn**, hay **được mở rộng tự do**. Đó là vai trò của ba modifier `final`, `sealed` và `non-sealed`.

Tính năng *sealed classes and interfaces* đã **chính thức từ Java 17** ([JEP 409](https://openjdk.org/jeps/409)). Những ví dụ trong bài sử dụng cú pháp ổn định của Java 17, không cần `--enable-preview`.

## 1. Nhìn tổng thể: ba cách quyết định số phận một nhánh kế thừa

Giả sử hệ thống định nghĩa:

```java
sealed interface Payment
        permits CashPayment, BankTransfer, GatewayPayment {
}
```

`Payment` chỉ cho phép **ba kiểu trực tiếp**: `CashPayment`, `BankTransfer` và `GatewayPayment`. Tại các kiểu được cấp quyền này, người viết chương trình phải quyết định nhánh tiếp theo:

| Modifier của kiểu con | Ý nghĩa | Hệ quả đối với việc kế thừa tiếp |
|---|---|---|
| `final` | **Đóng nhánh** | Không lớp nào được `extends` lớp đó nữa. |
| `sealed` | **Giữ nhánh có kiểm soát** | Chỉ những lớp/interface được cho phép ở cấp tiếp theo mới được kế thừa hoặc triển khai trực tiếp. |
| `non-sealed` | **Mở lại nhánh** | Các kiểu khác có thể kế thừa hoặc triển khai nhánh này theo quy tắc thông thường của Java; không cần được liệt kê trong `permits` của tổ tiên. |

Sơ đồ:

```text
Payment (sealed interface)
│
├── CashPayment (final class)
│   └── [Không được tạo lớp con]
│
├── BankTransfer (sealed abstract class)
│   ├── DomesticTransfer (final class)
│   │   └── [Không được tạo lớp con]
│   └── ForeignTransfer (non-sealed class)
│       ├── PriorityForeignTransfer (class thông thường)
│       └── ... (các lớp con hợp lệ khác)
│
└── GatewayPayment (non-sealed class)
    ├── CustomGatewayPayment (class thông thường)
    └── ... (các lớp con hợp lệ khác)
```

Điểm then chốt: **`sealed` giới hạn kiểu con trực tiếp, không tự động khóa tất cả các kiểu con ở mọi độ sâu.** Một khi nhánh trực tiếp được khai báo `non-sealed`, các lớp cháu trong nhánh đó không còn cần được tổ tiên `sealed` liệt kê.

## 2. Ví dụ đầy đủ chạy trên JDK 17

Tạo file **`SealedChildRoles.java`**:

```java
sealed interface Payment
        permits CashPayment, BankTransfer, GatewayPayment {

    String description();
}

// Nhánh 1: kết thúc tại đây.
final class CashPayment implements Payment {
    @Override
    public String description() {
        return "Thanh toán tiền mặt";
    }
}

// Nhánh 2: tiếp tục giới hạn các lớp con trực tiếp.
abstract sealed class BankTransfer implements Payment
        permits DomesticTransfer, ForeignTransfer {
}

final class DomesticTransfer extends BankTransfer {
    @Override
    public String description() {
        return "Chuyển khoản nội địa";
    }
}

non-sealed class ForeignTransfer extends BankTransfer {
    @Override
    public String description() {
        return "Chuyển khoản quốc tế";
    }
}

// Hợp lệ: ForeignTransfer đã mở nhánh.
class PriorityForeignTransfer extends ForeignTransfer {
}

// Nhánh 3: cho phép những lớp khác mở rộng.
non-sealed class GatewayPayment implements Payment {
    @Override
    public String description() {
        return "Thanh toán qua đối tác";
    }
}

// Hợp lệ dù tên lớp không xuất hiện trong Payment.permits.
class CustomGatewayPayment extends GatewayPayment {
}

public class SealedChildRoles {
    public static void main(String[] args) {
        Payment[] payments = {
            new CashPayment(),
            new DomesticTransfer(),
            new ForeignTransfer(),
            new PriorityForeignTransfer(),
            new CustomGatewayPayment()
        };

        for (Payment payment : payments) {
            System.out.println(payment.description());
        }
    }
}
```

Biên dịch và chạy bằng **JDK 17**:

```bash
javac --release 17 SealedChildRoles.java
java SealedChildRoles
```

Đầu ra:

```text
Thanh toán tiền mặt
Chuyển khoản nội địa
Chuyển khoản quốc tế
Chuyển khoản quốc tế
Thanh toán qua đối tác
```

Đọc theo từng cấp:

1. `Payment` là `sealed interface`, chỉ cấp quyền trực tiếp cho `CashPayment`, `BankTransfer` và `GatewayPayment`.
2. `CashPayment` dùng `final`, vì vậy không thể có `class SpecialCashPayment extends CashPayment`.
3. `BankTransfer` dùng `sealed` để chỉ cho phép `DomesticTransfer` và `ForeignTransfer` kế thừa trực tiếp.
4. `DomesticTransfer` dùng `final`, chặn kế thừa tiếp.
5. `ForeignTransfer` dùng `non-sealed`, vì vậy `PriorityForeignTransfer` được phép kế thừa mà không phải có trong `permits` của `BankTransfer`.
6. `GatewayPayment` dùng `non-sealed`, do đó `CustomGatewayPayment` được phép mở rộng và **vẫn là một `Payment`** theo quan hệ kế thừa gián tiếp.

Mặc dù `PriorityForeignTransfer` và `CustomGatewayPayment` không xuất hiện trong danh sách `permits` của `Payment`, chúng đều hợp lệ vì không phải kiểu con **trực tiếp** của `Payment`.

## 3. `final`: chủ động kết thúc một nhánh

### 3.1. Khi nào dùng `final`?

Một lớp con trực tiếp của kiểu `sealed` dùng `final` khi tác giả muốn tuyên bố kiểu đó là điểm cuối của cây kế thừa.

```java
sealed interface Payment permits CashPayment {
}

final class CashPayment implements Payment {
}
```

Không thể tạo lớp con mới từ `CashPayment`:

```java
// Không hợp lệ: CashPayment đã là final.
class SpecialCashPayment extends CashPayment {
}
```

`final` không cấm tạo đối tượng của chính lớp đó. Nếu lớp có constructor có thể truy cập, ta vẫn có thể gọi `new CashPayment()`.

### 3.2. `final` không đồng nghĩa bất biến dữ liệu

`final class` chỉ chặn **kế thừa**. Trạng thái bên trong đối tượng vẫn có thể thay đổi nếu lớp cung cấp các trường hoặc phương thức cho phép:

```java
final class Counter {
    private int value;

    void increment() {
        value++;
    }

    int value() {
        return value;
    }
}
```

Một `Counter` vẫn tăng được `value`, dù không lớp nào được kế thừa nó. Tương tự, `final` cho biến và `final` cho phương thức có ý nghĩa khác; bài này tập trung vào **`final` trên lớp**.

### 3.3. Lưu ý với `record` và `enum`

`record` **mặc định là `final`**, nên một `record` được phép trực tiếp triển khai `sealed interface` mà không cần viết modifier `final`:

```java
sealed interface Result permits Success, Failure {
}

record Success(String data) implements Result {
}

record Failure(String reason) implements Result {
}
```

Đây là mã hợp lệ trong Java 17. Không cần ghi `final` trước `record` vì ngôn ngữ đã ngầm định điều đó, dù Java vẫn cho phép ghi `final` tường minh (dư thừa). Ngược lại, `record` không được khai báo `sealed` hoặc `non-sealed`. Một `record` có thể triển khai `sealed interface`, nhưng không thể `extends` một lớp `sealed` bất kỳ vì `record` có cấu trúc kế thừa lớp riêng của ngôn ngữ.

`enum` cũng có quy tắc ngầm định của ngôn ngữ: tùy cấu trúc, một enum được coi là `final` hoặc `sealed`, nên có thể được phép trực tiếp triển khai `sealed interface` mà không phải tự ghi một trong ba modifier. Với **lớp thông thường**, hãy khai báo rõ modifier cần dùng.

## 4. `sealed`: tiếp tục kiểm soát những cấp kế thừa sau

Nếu một nhánh cần phân rã thành các loại con đã biết và bạn vẫn muốn kiểm soát danh sách đó, hãy khai báo lớp con là `sealed`:

```java
sealed interface Message permits SystemMessage {
}

abstract sealed class SystemMessage implements Message
        permits WarningMessage, InformationMessage {
}

final class WarningMessage extends SystemMessage {
}

final class InformationMessage extends SystemMessage {
}
```

Ở đây có **hai cửa kiểm soát riêng biệt**:

- `Message` quyết định loại nào trực tiếp triển khai `Message`: chỉ có `SystemMessage`.
- `SystemMessage` quyết định lớp nào trực tiếp kế thừa nó: `WarningMessage` và `InformationMessage`.

Một lớp khác không được tự ý `extends SystemMessage` nếu nó không nằm trong `permits` của `SystemMessage`. Mỗi lớp con trực tiếp lại phải chọn `final`, `sealed` hoặc `non-sealed` (trừ trường hợp ngôn ngữ quy định modifier ngầm định).

### `sealed` có bắt buộc đi cùng `abstract`?

**Không.** Một `sealed class` có thể là lớp cụ thể hoặc lớp trừu tượng, tùy mô hình dữ liệu.

- `abstract sealed class` thích hợp khi lớp cha chỉ đại diện cho khái niệm chung và không được tạo đối tượng trực tiếp.
- `sealed class` (không `abstract`) vẫn có thể khởi tạo nếu constructor cho phép; `sealed` chỉ giới hạn lớp con.

Ngược lại, **`final` và `abstract` không thể cùng áp dụng cho một lớp** vì lớp trừu tượng cần có khả năng được hoàn thiện bằng lớp con, trong khi `final` cấm mọi lớp con.

### `sealed` interface hoạt động tương tự

Một interface con trực tiếp của `sealed interface` có thể tiếp tục là `sealed`:

```java
sealed interface Device permits NetworkDevice {
}

sealed interface NetworkDevice extends Device
        permits Router, Switch {
}

final class Router implements NetworkDevice {
}

final class Switch implements NetworkDevice {
}
```

Interface không được khai báo `final`. Nếu interface là kiểu con trực tiếp của một `sealed interface`, nó chọn **`sealed` hoặc `non-sealed`** để xác định cách các interface/lớp khác được tiếp tục triển khai.

## 5. `non-sealed`: mở lại khả năng mở rộng

Khi muốn cho người sử dụng thư viện hoặc các module ứng dụng khác tạo thêm kiểu con trong một nhánh, một lớp hoặc interface được cấp quyền trực tiếp có thể dùng `non-sealed`.

```java
sealed interface Notification
        permits SystemNotification, ExtensionNotification {
}

final class SystemNotification implements Notification {
}

// Mở nhánh cho các kiểu thông báo do ứng dụng định nghĩa.
non-sealed class ExtensionNotification implements Notification {
}

class EmailExtension extends ExtensionNotification {
}

class SmsExtension extends ExtensionNotification {
}
```

`SystemNotification` bị đóng ở cấp kế thừa tiếp. `ExtensionNotification` lại cho phép tạo thêm các kiểu như `EmailExtension` và `SmsExtension` mà không phải sửa `Notification`.

### Mở nhánh không đồng nghĩa mọi lớp ở mọi nơi đều có thể kế thừa

`non-sealed` **gỡ hạn chế do tổ tiên `sealed` đặt ra tại nhánh này**, nhưng các quy tắc Java khác vẫn áp dụng: quyền truy cập `public`/`package-private`, khả năng truy cập constructor, yêu cầu triển khai phương thức trừu tượng, giới hạn module, v.v.

Ngoài ra, **lớp con của một `non-sealed class` không phải tiếp tục ghi `non-sealed`** nếu nó không có một lớp cha hoặc interface trực tiếp khác được `sealed`. Chẳng hạn:

```java
class EmailExtension extends ExtensionNotification {
}

// Sai nếu chỉ kế thừa ExtensionNotification:
// non-sealed class SmsExtension extends ExtensionNotification { }
```

`non-sealed` không có nghĩa là “một class bình thường được phép có con”. Đây là modifier dùng **riêng tại vị trí cần tuyên bố mở lại một nhánh chịu ràng buộc trực tiếp bởi kiểu `sealed`**.

Một lớp con sâu hơn vẫn có thể tự khai báo `final` để dừng kế thừa, hoặc `sealed` cùng `permits` để kiểm soát **các lớp con trực tiếp của chính nó**. Tuy nhiên, việc đó không đóng lại tất cả các nhánh khác đã được mở từ `ExtensionNotification`.

### `non-sealed` trên interface

`non-sealed` không chỉ dùng với class:

```java
sealed interface Event permits InternalEvent, PublicEvent {
}

record InternalEvent(String id) implements Event {
}

non-sealed interface PublicEvent extends Event {
}

// Không cần modifier vì PublicEvent đã là non-sealed.
interface PartnerEvent extends PublicEvent {
}

class PartnerCreatedEvent implements PartnerEvent {
}
```

`PartnerCreatedEvent` vẫn là một `Event`, nhưng nó đi qua nhánh `PublicEvent` đã được mở.

## 6. Tại sao Java buộc lớp con trực tiếp phải chọn trạng thái?

Giả sử Java cho phép mã này:

```java
// VÍ DỤ SAI — không biên dịch được trên Java 17.
sealed interface Task permits BackgroundTask {
}

class BackgroundTask implements Task {
}
```

Nếu `BackgroundTask` mặc nhiên được mở rộng như một lớp bình thường, người tạo `Task` có thể vô tình cho phép các lớp cháu phát triển mà không chủ động thiết kế. Java 17 yêu cầu lớp con trực tiếp phải nói rõ ý định, chẳng hạn:

```java
final class BackgroundTask implements Task {
}
```

hoặc:

```java
non-sealed class BackgroundTask implements Task {
}
```

Nếu muốn kiểm soát tiếp, hãy dùng `sealed` và định nghĩa lớp con của `BackgroundTask`.

Quy tắc này khiến quyết định thiết kế có thể đọc được ngay trong khai báo kiểu: người đọc biết nhánh được đóng, được kiểm soát hay đã mở lại.

## 7. Các quy tắc quan trọng đi kèm `permits`

### 7.1. Chỉ liệt kê kiểu con trực tiếp

```java
sealed class Parent permits Child {
}

non-sealed class Child extends Parent {
}

class Grandchild extends Child {
}
```

`Parent` cần cho phép `Child`; **không cần liệt kê `Grandchild`**. `Grandchild` không trực tiếp `extends Parent`.

Ngược lại, ghi tên một kiểu **không kế thừa trực tiếp** trong `permits` không biến nó thành kiểu con trực tiếp hợp lệ.

### 7.2. Vị trí module/package của kiểu được cấp quyền

Các kiểu con trực tiếp được phép phải tuân theo vị trí mà Java quy định:

- Nếu kiểu `sealed` thuộc **named module**, các kiểu được cấp quyền phải thuộc **cùng module**. Chúng có thể ở các package khác nhau bên trong module đó, miễn các quy tắc truy cập được đáp ứng.
- Nếu kiểu `sealed` thuộc **unnamed module**, các kiểu được cấp quyền phải ở **cùng package**.

Vì vậy, `permits` không phải cơ chế để mở trực tiếp một `sealed class` cho lớp bất kỳ trong module bên ngoài. Nếu muốn cho ứng dụng khác mở rộng, có thể thiết kế một nhánh `non-sealed` làm điểm mở rộng.

### 7.3. Khi nào có thể bỏ `permits`?

Nếu các kiểu con trực tiếp được khai báo **cùng compilation unit (cùng file nguồn)** với kiểu `sealed`, Java có thể suy ra danh sách cho phép khi bạn bỏ `permits`:

```java
sealed interface EventType {
}

final class Created implements EventType {
}

non-sealed class Updated implements EventType {
}
```

Trong ví dụ này, compiler suy ra `Created` và `Updated` là các kiểu được phép. Với mã trải ở nhiều file, hãy khai báo `permits` rõ ràng để xác định hợp đồng kế thừa. Cách khai báo tường minh thường dễ đọc hơn khi cây kế thừa có nhiều nhánh.

### 7.4. Không kết hợp các modifier loại trừ nhau

Với một lớp, `final`, `sealed`, `non-sealed` là ba lựa chọn loại trừ nhau cho chính sách kế thừa. Không thể khai báo cùng lúc như `final sealed class ...` hoặc `sealed non-sealed class ...`.

Một lớp thông thường **không có cha/interface trực tiếp nào `sealed`** cũng không được tự ý khai báo `non-sealed`. Nếu không cần kiểm soát, hãy dùng `class` bình thường.

## 8. Lỗi thường gặp và cách sửa

Các đoạn trong cột “không hợp lệ” là minh họa lỗi riêng lẻ, không phải một file để biên dịch cùng nhau.

| Tình huống | Vì sao không hợp lệ hoặc dễ hiểu sai | Cách xử lý |
|---|---|---|
| `class Child extends SealedParent` dù đã nằm trong `permits` | `Child` là lớp con trực tiếp nhưng chưa chọn trạng thái kế thừa | Thêm **một** trong `final`, `sealed`, `non-sealed` |
| `class Stranger extends SealedParent` nhưng không nằm trong `permits` | `sealed` cấm kiểu con trực tiếp không được cấp quyền | Cập nhật thiết kế/danh sách `permits` hợp lệ, hoặc đi qua nhánh `non-sealed` thích hợp |
| `class Child extends FinalChild` | `final` cấm mọi lớp con | Dùng quan hệ khác phù hợp; không kế thừa lớp `final` |
| `non-sealed class Ordinary { }` | Không có supertype trực tiếp `sealed` | Dùng `class Ordinary { }` |
| `final interface Sub extends SealedInterface` | Interface không hỗ trợ `final` | Dùng `sealed interface` hoặc `non-sealed interface` |
| `sealed class Child extends Parent { }` nhưng không có kiểu con được phép | `sealed` cần xác định tập con trực tiếp hợp lệ | Khai báo `permits` và các kiểu con, hoặc đổi `Child` thành `final`/`non-sealed` theo mục đích |
| Đặt kiểu trực tiếp được cấp quyền ở module khác | Quy tắc cùng named module hoặc cùng package trong unnamed module không được đáp ứng | Chuyển kiểu về phạm vi hợp lệ hoặc mở rộng qua một nhánh `non-sealed` có thể truy cập |
| Dùng `--enable-preview` để chạy ví dụ `sealed` Java 17 | Gây nhầm lẫn về trạng thái tính năng | Bỏ cờ preview; sealed đã chính thức ở Java 17 |

**Mẹo đọc lỗi:** Khi gặp thông báo biên dịch liên quan `sealed`, hãy kiểm tra lần lượt: kiểu cha có `permits` cho lớp con không, có quan hệ kế thừa **trực tiếp** không, kiểu con đã chọn trạng thái chưa, và có vi phạm ranh giới module/package không.

## 9. Thiết kế cây kế thừa phù hợp

Không nên mặc định rằng cả cây phải đóng hoặc cả cây phải mở. Một cây `sealed` có thể chứa đồng thời nhiều chính sách:

| Nhu cầu nghiệp vụ | Chọn tại lớp/interface con | Lý do |
|---|---|---|
| Kiểu nghiệp vụ đã hoàn thiện, không cần biến thể kế thừa | `final class` hoặc `record` khi phù hợp | Giữ một nhánh kết thúc rõ ràng |
| Còn một số kiểu con được kiểm soát chặt | `sealed class/interface` | Mở một cấp kế thừa mới với danh sách cho phép |
| Phải hỗ trợ extension/plugin hoặc loại dữ liệu do bên tích hợp định nghĩa | `non-sealed class/interface` | Cho phép mở rộng nhánh một cách chủ động |
| Lớp con là khái niệm trừu tượng, chưa muốn tạo instance | `abstract sealed class` hoặc `abstract non-sealed class` | Vừa thể hiện tính trừu tượng vừa kiểm soát/mở rộng kế thừa |
| Chỉ cần lớp cha kế thừa thông thường mà không cần một tập kiểu đóng | `class`/`interface` thông thường | Tránh thêm ràng buộc `sealed` không cần thiết |

### Tác động khi thay đổi cây kế thừa

Danh sách `permits` và modifier của lớp con là một phần của **thiết kế API công khai**. Chuyển `non-sealed` thành `final` hoặc `sealed` có thể làm mã của người dùng không còn khả năng mở rộng như trước. Thêm kiểu mới vào một cây `sealed` cũng có thể ảnh hưởng đến những nơi xử lý đầy đủ các trường hợp.

Ở các bản Java hiện đại, cây `sealed` đặc biệt hữu ích với việc kiểm tra tính đầy đủ của pattern matching trong `switch`. Tuy nhiên, cần phân biệt phiên bản: **pattern matching for `switch` ở Java 17 vẫn là preview**, trong khi sealed classes đã là chính thức; pattern matching for `switch` chỉ chính thức từ Java 21 ([JEP 441](https://openjdk.org/jeps/441)). Ví dụ trong bài không dựa vào preview feature nào.

## 10. Bài tập áp dụng

### Bài 1 — Chọn modifier

Cho `sealed interface Command permits Start, Stop, PluginCommand`:

1. `Start` không cho phép tạo loại con mới.
2. `Stop` chỉ được có hai biến thể con `GracefulStop` và `ForceStop`.
3. `PluginCommand` cần cho các plugin tự định nghĩa thêm lệnh.

**Gợi ý:** Lần lượt chọn `final`, `sealed`, `non-sealed`. Với `Stop` phải khai báo `permits GracefulStop, ForceStop`, đồng thời hai lớp con đó cũng phải có modifier phù hợp.

### Bài 2 — Tìm lỗi

```java
sealed interface ApiResult permits OkResult, ErrorResult {
}

class OkResult implements ApiResult {
}

non-sealed class ErrorResult implements ApiResult {
}

non-sealed class CustomError extends ErrorResult {
}
```

Có hai lỗi cần phát hiện:

1. `OkResult` là lớp con trực tiếp của `ApiResult` nhưng không khai báo `final`, `sealed` hoặc `non-sealed`.
2. `CustomError` không được khai báo `non-sealed` chỉ vì nó kế thừa `ErrorResult`; lớp cha trực tiếp `ErrorResult` hiện là `non-sealed` và không có superinterface trực tiếp nào `sealed` trong khai báo này.

Một cách sửa là khai báo `final class OkResult` và `class CustomError extends ErrorResult`.

### Bài 3 — Giải thích quan hệ kế thừa gián tiếp

Vì sao `CustomGatewayPayment` trong ví dụ chính vẫn là một `Payment` dù không nằm trong `Payment.permits`?

**Đáp án:** `CustomGatewayPayment extends GatewayPayment`, còn `GatewayPayment implements Payment` và được `Payment` cấp quyền trực tiếp. `GatewayPayment` là `non-sealed`, nên lớp con gián tiếp được tạo hợp lệ.

## 11. Ghi nhớ qua ba câu hỏi

Đối với **mỗi kiểu con trực tiếp** của một `sealed class/interface`, hãy tự hỏi:

1. **Có muốn chặn kế thừa tiếp không?** Dùng `final` cho class (hoặc `record` có tính `final` ngầm định khi phù hợp).
2. **Có muốn cho kế thừa nhưng chỉ trong danh sách kiểm soát không?** Dùng `sealed` và danh sách `permits` phù hợp.
3. **Có muốn người khác tạo thêm kiểu con không?** Dùng `non-sealed`, với lưu ý rằng các quy tắc truy cập Java vẫn còn hiệu lực.

Ba quyết định này giúp hợp đồng kế thừa vừa rõ ràng tại từng cấp, vừa linh hoạt ở đúng nhánh được thiết kế để mở rộng.

## 12. Tài liệu tham khảo

- [Oracle Java 17 — Sealed Classes](https://docs.oracle.com/en/java/javase/17/language/sealed-classes-and-interfaces.html): quy tắc `permits`, `final`, `sealed`, `non-sealed`, `record` và ranh giới module/package.
- [Oracle Java 17 — Java Language Changes](https://docs.oracle.com/en/java/javase/17/language/java-language-changes-release.html): xác nhận sealed classes là tính năng chính thức từ Java 17.
- [OpenJDK JEP 409 — Sealed Classes](https://openjdk.org/jeps/409): mục tiêu thiết kế và các quy tắc ngôn ngữ.
- [Java Language Specification 17 — Classes](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html): đặc tả lớp, kế thừa và modifier.
- [OpenJDK JEP 441 — Pattern Matching for `switch`](https://openjdk.org/jeps/441): thông tin khi nghiên cứu thêm cách dùng sealed hierarchies ở các bản Java có pattern matching cho `switch` đã chính thức.

