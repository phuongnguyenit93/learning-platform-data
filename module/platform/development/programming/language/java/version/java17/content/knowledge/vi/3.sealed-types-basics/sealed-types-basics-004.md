# Quy tắc kiểu con trực tiếp và quan hệ `extends`, `implements` trong sealed types — Java 17

Từ **Java 17**, `sealed class` và `sealed interface` là tính năng chính thức để giới hạn **những kiểu con trực tiếp nào được phép** xuất hiện trong một hệ phân cấp. Trọng tâm của cơ chế này nằm ở cách Java hiểu các mối quan hệ `extends`, `implements` và danh sách `permits`.

Một sealed type **không nhất thiết giới hạn mọi hậu duệ ở mọi cấp**. Nó giới hạn **các khai báo nối trực tiếp với nó**. Nhánh con sau đó có thể tiếp tục đóng bằng `final`, kiểm soát tiếp bằng `sealed` hoặc mở ra bằng `non-sealed`.

## 1. Thế nào là kiểu con trực tiếp?

Quan sát:

```java
sealed class Vehicle permits Car {}

non-sealed class Car extends Vehicle {}

class ElectricCar extends Car {}
```

Sơ đồ:

```text
Vehicle (sealed)
└── Car (non-sealed)      [extends trực tiếp Vehicle]
    └── ElectricCar      [extends trực tiếp Car]
```

Ở đây:

- `Car` là **direct subclass** của `Vehicle` vì khai báo `Car` nêu `extends Vehicle`.
- `ElectricCar` là subclass **gián tiếp** của `Vehicle` vì đi qua `Car`.
- `Vehicle permits Car` là đầy đủ. `ElectricCar` không được và không cần đưa vào `permits` của `Vehicle`.
- `Car` là `non-sealed` nên `ElectricCar` có thể là class thông thường, không cần modifier liên quan đến sealed.

Vẫn có thể viết:

```java
Vehicle vehicle = new ElectricCar(); // Hợp lệ
```

Đó là **quan hệ gán kiểu** theo tính bắc cầu, không làm `ElectricCar` trở thành direct subclass của `Vehicle`.

**Nguyên tắc:** để biết một kiểu có là con *trực tiếp* của sealed type nào hay không, xem danh sách superclass và superinterfaces được nêu ngay trong khai báo của nó, không suy từ việc biến có thể nhận một đối tượng kiểu đó.

## 2. Ma trận `extends` và `implements`

| Khai báo kiểu con | Cú pháp | Kiểu cha trực tiếp | Có thể là con trực tiếp của |
|---|---|---|---|
| `class` | `class Child extends Parent` | Một `class` | `sealed class Parent` |
| `class` hoặc `record` | `class Child implements Role` | Một hoặc nhiều `interface` | `sealed interface Role` |
| `interface` | `interface Child extends Role` | Một hoặc nhiều `interface` | `sealed interface Role` |
| `interface` | `interface Child implements Role` | Không hợp lệ | Không có |
| `interface` | `interface Child extends ParentClass` | Không hợp lệ | Không có |
| `class` | `class Child extends SomeInterface` | Không hợp lệ | Không có |

Ví dụ Java 17:

```java
sealed class Base permits Derived {}
final class Derived extends Base {}

sealed interface Task permits DirectTask, SpecializedTask {}
final class DirectTask implements Task {}
non-sealed interface SpecializedTask extends Task {}
```

Ở dòng `final class Derived extends Base`, từ khóa `extends` nối **class với class**. Ở dòng `final class DirectTask implements Task`, `implements` nối **class với interface**. Ở dòng `non-sealed interface SpecializedTask extends Task`, `extends` nối **interface với interface**.

Một class chỉ có **một direct superclass** nhưng có thể có **nhiều direct superinterfaces**. Một interface có thể `extends` nhiều interface.

**`permits` không tự tạo ra mối quan hệ kế thừa.** Nó liệt kê các kiểu đã (hoặc sẽ) khai báo `extends`/`implements` trực tiếp với sealed type. Phải khớp **hai chiều**: con phải nêu đúng cha và cha phải cho phép con.

## 3. Sealed class: quyền trực tiếp đi qua `extends`

Ví dụ một kiểu trừu tượng dành cho hình học:

```java
abstract sealed class Shape permits Circle, Rectangle {
    abstract double area();
}

final class Circle extends Shape {
    private final double radius;

    Circle(double radius) {
        this.radius = radius;
    }

    @Override
    double area() {
        return Math.PI * radius * radius;
    }
}

final class Rectangle extends Shape {
    private final double width;
    private final double height;

    Rectangle(double width, double height) {
        this.width = width;
        this.height = height;
    }

    @Override
    double area() {
        return width * height;
    }
}
```

`Circle` và `Rectangle` là các class trực tiếp `extends Shape` nên phải được `Shape` cho phép. `final` đóng mỗi nhánh, ngăn class khác `extends Circle` hoặc `extends Rectangle`.

`abstract sealed` là kết hợp hợp lệ:

- `abstract`: không thể tạo trực tiếp `new Shape()` và có thể khai báo phương thức trừu tượng.
- `sealed`: kiểm soát những lớp nào được phép `extends Shape`.

Một interface **không thể** trở thành con trực tiếp của `Shape`, vì Java không cho interface `extends` class. Nếu cần cả class lẫn interface làm con trực tiếp, loại cha phải là **sealed interface**.

## 4. Sealed interface: class dùng `implements`, interface dùng `extends`

`sealed interface` có thể cho phép cả class và interface làm direct subtype. Một ví dụ gồm cả hai dạng:

```java
sealed interface Payment permits CardPayment, CashPayment, VoucherPayment {
    long amount();
}

final class CardPayment implements Payment {
    private final long cents;

    CardPayment(long cents) {
        this.cents = cents;
    }

    @Override
    public long amount() {
        return cents;
    }
}

record CashPayment(long amount) implements Payment {}

non-sealed interface VoucherPayment extends Payment {
    String code();
}
```

Sơ đồ:

```text
Payment (sealed interface)
├── CardPayment    (final class)          -- implements Payment
├── CashPayment    (record, final ngầm)   -- implements Payment
└── VoucherPayment (non-sealed interface) -- extends Payment
```

`Payment permits` chứa đúng **ba kiểu con trực tiếp** dù chúng có cú pháp khai báo không giống nhau.

### Vì sao kiểu con gián tiếp không cần `permits` từ ông/bà?

`VoucherPayment` được phép `extends Payment` và lại là `non-sealed`. Do đó ta có thể viết:

```java
final class GiftVoucher implements VoucherPayment {
    @Override
    public long amount() {
        return 50_000;
    }

    @Override
    public String code() {
        return "WELCOME";
    }
}

Payment payment = new GiftVoucher(); // Hợp lệ
```

`GiftVoucher` trực tiếp `implements VoucherPayment`. Nó là kiểu con của `Payment` **thông qua** `VoucherPayment`, do đó **không cần** `Payment permits GiftVoucher`.

Nhưng nếu thay khai báo thành:

```java
// Sai nếu GiftVoucher không có trong Payment permits:
// final class GiftVoucher implements VoucherPayment, Payment { ... }
```

thì `GiftVoucher` đã nêu trực tiếp tên `Payment` trong `implements`, tạo thêm một **quan hệ trực tiếp**. Khi đó nó phải có trong danh sách `Payment permits`, dù vẫn triển khai `Payment` gián tiếp qua `VoucherPayment`.

Kết luận thực hành: `permits` chỉ được đối chiếu với những quan hệ **trực tiếp thực sự xuất hiện trong khai báo**; một kiểu có thể đồng thời có quan hệ trực tiếp và gián tiếp với cùng interface nếu người viết nêu thêm interface đó.

## 5. Một class có thể có nhiều sealed type cha trực tiếp

### Hai sealed interfaces

```java
sealed interface Auditable permits Receipt {}
sealed interface Printable permits Receipt {}

final class Receipt implements Auditable, Printable {}
```

`Receipt` trực tiếp `implements` **cả hai interface**. Hai danh sách `permits` phải đều chứa `Receipt`. Thiếu ở một bên thì khai báo con không hợp lệ.

### Một sealed class và một sealed interface

```java
sealed class Entity permits User {}
sealed interface Identifiable permits User {}

final class User extends Entity implements Identifiable {}
```

`User` trực tiếp `extends Entity` đồng thời trực tiếp `implements Identifiable`. Vì vậy nó cần xuất hiện ở **cả hai `permits`**.

Không nên kiểm tra phép gán kiểu rồi đoán `permits`. Hãy nhìn **danh sách `extends`/`implements` của chính từng kiểu con**, và kiểm tra quyền cho mỗi sealed supertype được nêu.

## 6. Ba trạng thái bắt buộc của class con trực tiếp

Khi class trực tiếp `extends` một sealed class **hoặc** trực tiếp `implements` một sealed interface, nó phải chọn một trong ba hướng sau:

| Modifier | Ý nghĩa | Có được khai báo lớp con tiếp không? |
|---|---|---|
| `final` | Kết thúc nhánh | Không |
| `sealed` | Giới hạn tiếp các kiểu con trực tiếp của chính nhánh đó | Có, nhưng chỉ những kiểu nhánh đó cho phép |
| `non-sealed` | Mở nhánh trở lại | Có, theo quy tắc kế thừa Java thông thường |

Ví dụ nhiều tầng:

```java
sealed class Message permits TextMessage, AttachmentMessage, CustomMessage {}

final class TextMessage extends Message {}

sealed class AttachmentMessage extends Message
        permits ImageMessage, VideoMessage {}

final class ImageMessage extends AttachmentMessage {}

final class VideoMessage extends AttachmentMessage {}

non-sealed class CustomMessage extends Message {}

class BusinessMessage extends CustomMessage {}
```

Sơ đồ:

```text
Message (sealed)
├── TextMessage (final)                  [kết thúc]
├── AttachmentMessage (sealed)           [kiểm soát tầng sau]
│   ├── ImageMessage (final)
│   └── VideoMessage (final)
└── CustomMessage (non-sealed)           [mở nhánh]
    └── BusinessMessage (class thường)
```

Có ba nhận xét cốt lõi:

1. `Message` chỉ cho phép ba **class trực tiếp**: `TextMessage`, `AttachmentMessage` và `CustomMessage`.
2. `AttachmentMessage` phải **tự** `permits ImageMessage, VideoMessage` vì chính nó `sealed` và là direct superclass của hai lớp này.
3. `BusinessMessage` không cần xuất hiện trong `Message permits`, cũng không cần mang modifier `non-sealed`.

`abstract` không thay thế `final`/`sealed`/`non-sealed`: class có thể là `abstract sealed` hoặc `abstract non-sealed`, nhưng không thể là `abstract final`.

## 7. Nếu kiểu con trực tiếp là interface thì sao?

Một interface `extends` trực tiếp sealed interface phải chọn **`sealed` hoặc `non-sealed`**:

```java
sealed interface Notification
        permits EmailNotification, ExtensionNotification {}

sealed interface EmailNotification extends Notification
        permits TransactionEmail {}

non-sealed interface ExtensionNotification extends Notification {}

final class TransactionEmail implements EmailNotification {}
```

- `EmailNotification` giữ quy tắc kiểm soát và liệt kê con trực tiếp của **nó**.
- `ExtensionNotification` mở nhánh, cho phép class/interface khác triển khai hoặc kế thừa.
- **Interface không thể `final`**. Muốn kết thúc một nhánh interface, thường dùng một `final class` hoặc `record` triển khai interface đó.

### `record` có cần ghi `final`?

Không. Record trong Java 17 có tính chất **`final` ngầm định**, nên có thể là direct subtype của sealed interface mà không cần viết modifier:

```java
sealed interface Result permits Success, Failure {}

record Success(String value) implements Result {}
record Failure(String reason) implements Result {}
```

`enum` cũng có thể trực tiếp triển khai sealed interface; Java quy định enum ngầm `final` hoặc `sealed` tùy việc enum constant có thân class riêng hay không. Trong bài căn bản, record là ví dụ ngắn gọn để nhận biết class có `final` ngầm định.

### `non-sealed` không phải modifier dùng tùy ý

Một class/interface chỉ được khai báo `non-sealed` nếu có **ít nhất một sealed supertype trực tiếp**. Ví dụ:

```java
class OpenBase {}

// Sai: OpenBase không sealed.
// non-sealed class Extra extends OpenBase {}

// Đúng:
class Extra extends OpenBase {}
```

Nói cách khác, `non-sealed` là quyết định **mở lại một ranh giới sealed ở cấp trực tiếp**, không phải cách viết thông thường của mọi class cho phép kế thừa.

## 8. `permits` phải thỏa những điều kiện nào?

### 8.1. Mỗi tên phải trỏ tới kiểu con trực tiếp thật sự

Đây là sai:

```java
// Sai: Other không extends Base.
// sealed class Base permits Other {}
// final class Other {}
```

Dòng `permits Other` không biến `Other` thành subclass. Để hợp lệ, `Other` phải thực sự khai báo `extends Base` và tuân theo các quy tắc khác.

Tương tự:

```java
// Sai: LogEntry không implements Event.
// sealed interface Event permits LogEntry {}
// final class LogEntry {}
```

### 8.2. Kiểu con trực tiếp ngoài danh sách bị từ chối

```java
sealed class Account permits PersonalAccount {}

final class PersonalAccount extends Account {}

// Sai: không được Account cho phép.
// final class BusinessAccount extends Account {}
```

Đây là **lỗi lúc biên dịch**; không cần chờ chạy ứng dụng.

### 8.3. `permits` không nhận trùng kiểu

```java
// Sai: trùng One.
// sealed class Base permits One, One {}
// final class One extends Base {}
```

`One` và tên đầy đủ package của `One` vẫn chỉ là **một kiểu**: không được liệt kê hai lần. Ngoài ra, class/interface có `permits` mà **không** khai báo `sealed` cũng là lỗi.

### 8.4. Không liệt kê hậu duệ gián tiếp

Sai:

```java
// Sai: Leaf chỉ trực tiếp extends Middle.
// sealed class Root permits Middle, Leaf {}
// non-sealed class Middle extends Root {}
// final class Leaf extends Middle {}
```

Đúng:

```java
sealed class Root permits Middle {}

non-sealed class Middle extends Root {}

final class Leaf extends Middle {}
```

Nếu `Middle` cũng là `sealed`, danh sách `permits Leaf` thuộc về **Middle**, không thuộc về `Root`.

### 8.5. Giới hạn vị trí khai báo: named module và unnamed module

Những kiểu con được `permits` cho phép phải nằm trong cùng phạm vi quản lý phù hợp:

| Ngữ cảnh của sealed type | Phạm vi permitted direct subtypes |
|---|---|
| **Named module** (dùng JPMS với `module-info.java`) | Các kiểu phải thuộc **cùng named module**; có thể khác package nếu đủ khả năng truy cập |
| **Unnamed module** (classpath thông thường) | Các kiểu phải ở **cùng package** với sealed type |

Ví dụ trên classpath:

```java
// File: com/example/model/Action.java
package com.example.model;

public sealed interface Action permits SaveAction {}
```

```java
// File: com/example/model/SaveAction.java
package com.example.model;

public final class SaveAction implements Action {}
```

Hai file cùng package nên không vi phạm ràng buộc của unnamed module. Nếu chuyển `SaveAction` sang package khác, **chỉ sửa `permits` bằng tên có package đầy đủ không đủ** để bỏ ràng buộc cùng package trong unnamed module.

Trong named module, có thể đặt sealed type và permitted direct subtype tại hai package khác nhau **trong cùng module**, miễn kiểu con truy cập được kiểu cha và khai báo hợp lệ.

## 9. `permits` có thể bỏ qua khi compiler suy luận được

Java 17 có thể suy luận permitted direct subtypes nếu sealed type **không khai báo `permits`** và có các kiểu con trực tiếp **trong cùng compilation unit** (cùng tệp nguồn `.java`).

Ví dụ một tệp `Operation.java`:

```java
sealed interface Operation {}

record Add(int a, int b) implements Operation {}

record Multiply(int a, int b) implements Operation {}
```

Trình biên dịch suy ra `Add` và `Multiply` là hai permitted direct subtypes của `Operation`.

Phần **cùng tệp nguồn** là điểm quan trọng: cùng package nhưng **khác tệp `.java`** thì không được tự động suy luận theo cách này. Khi tách file, viết tường minh:

```java
// Operation.java
sealed interface Operation permits Add, Multiply {}
```

```java
// Add.java
record Add(int a, int b) implements Operation {}
```

```java
// Multiply.java
record Multiply(int a, int b) implements Operation {}
```

Ba file trên giả định thuộc cùng package. Khi `permits` bị lược bỏ, compiler chỉ suy luận các kiểu trực tiếp có **canonical name** cùng compilation unit (ví dụ top-level/member type); **local** và **anonymous** class không được suy luận theo cách đó. Không được để một sealed type thiếu `permits` và cũng không có kiểu con trực tiếp hợp lệ để suy luận.

Nên viết `permits` tường minh khi muốn người đọc nhìn ngay hệ phân cấp hoặc khi các kiểu được tách thành nhiều file.

## 10. Phân biệt quan hệ gián tiếp qua class và interface

### 10.1. Gián tiếp qua non-sealed class

```java
sealed class Parent permits OpenChild {}

non-sealed class OpenChild extends Parent {}

class GrandChild extends OpenChild {}
```

`GrandChild` là con gián tiếp của `Parent`; nó không cần `Parent permits GrandChild`.

### 10.2. Gián tiếp qua non-sealed interface

```java
sealed interface BaseRole permits ExtendedRole {}

non-sealed interface ExtendedRole extends BaseRole {}

final class Person implements ExtendedRole {}
```

`Person` trực tiếp triển khai `ExtendedRole`, gián tiếp thuộc `BaseRole`. Chỉ `ExtendedRole` cần nằm trong `BaseRole permits`.

### 10.3. Gián tiếp qua superclass có implements

```java
sealed interface Identified permits BaseEntity {}

non-sealed class BaseEntity implements Identified {}

class Customer extends BaseEntity {}
```

`Customer` kế thừa quan hệ triển khai `Identified` qua superclass `BaseEntity`; `Customer` không trực tiếp `implements Identified`. Do đó `Identified` chỉ cần cho phép `BaseEntity`.

**Tình huống đặc biệt:** Nếu `Customer` vừa `extends BaseEntity` vừa viết thêm `implements Identified`, nó tự tạo quan hệ trực tiếp tới `Identified`. Trường hợp đó cần được `Identified` cho phép riêng và cần modifier phù hợp cho một class có sealed direct superinterface.

## 11. Các lỗi phổ biến và cách đọc nguyên nhân

Các đoạn mã có chú thích “sai” bên dưới được viết để minh họa lỗi, không phải ví dụ chạy đồng thời.

| Cú pháp/tình huống | Sai ở đâu? | Hướng sửa |
|---|---|---|
| `class Child extends SealedClass` nhưng `Child` không được `permits` | Bị chặn direct superclass | Cho phép `Child` nếu phù hợp với thiết kế |
| `class Impl implements SealedInterface` nhưng `Impl` không được `permits` | Bị chặn direct superinterface | Cho phép `Impl` |
| `interface Child extends SealedInterface` nhưng không được `permits` | Bị chặn direct superinterface | Cho phép `Child` |
| `permits GrandChild` dù `GrandChild` chỉ `extends Child` | Không phải con trực tiếp | Bỏ `GrandChild` khỏi permits của ông/bà |
| `class Child extends SealedParent {}` | Thiếu `final`/`sealed`/`non-sealed` | Chọn một modifier cho class |
| `interface Child extends SealedParent {}` | Thiếu `sealed`/`non-sealed` | Chọn modifier cho interface |
| `final interface Child` | Interface không thể `final` | Dùng `sealed`/`non-sealed` đúng mục đích |
| `non-sealed class Child extends OpenBase` | Cha trực tiếp không sealed (và không có sealed direct superinterface) | Dùng `class` thông thường |
| `permits A, A` | Trùng tên cùng kiểu | Liệt kê một lần |
| `permits` trên class/interface không `sealed` | Thiếu điều kiện cho phép cú pháp `permits` | Khai báo `sealed` nếu muốn giới hạn cây |
| Hai package khác nhau trong unnamed module | Vượt phạm vi permitted direct subtype | Đặt kiểu trực tiếp cùng package hoặc thiết kế named module thích hợp |

### Ví dụ lỗi: thiếu modifier của direct subtype

```java
// Sai: Leaf không final/sealed/non-sealed.
// sealed class Node permits Leaf {}
// class Leaf extends Node {}
```

Sửa:

```java
sealed class Node permits Leaf {}
final class Leaf extends Node {}
```

### Ví dụ lỗi: `extends` nhầm với `implements`

```java
// Sai: class không thể extends interface.
// sealed interface Service permits HttpService {}
// final class HttpService extends Service {}
```

Sửa:

```java
sealed interface Service permits HttpService {}
final class HttpService implements Service {}
```

### Ví dụ lỗi: thêm `non-sealed` ở tầng đã mở

```java
// sealed class Root permits Branch {}
// non-sealed class Branch extends Root {}
// non-sealed class Next extends Branch {} // Sai: Branch không sealed
```

Sửa thành `class Next extends Branch {}` hoặc `final class Next extends Branch {}`, tùy có muốn cho phép kế thừa `Next` tiếp hay không.

## 12. Bài thực hành: xác định direct subtype

Hãy đọc đoạn Java 17:

```java
sealed interface Document permits PdfDocument, EditableDocument {}

final class PdfDocument implements Document {}

non-sealed interface EditableDocument extends Document {}

class TextDocument implements EditableDocument {}

final class RichTextDocument extends TextDocument {}
```

**Câu hỏi 1.** Kiểu nào là con trực tiếp của `Document`?

**Trả lời:** `PdfDocument` vì `implements Document`; `EditableDocument` vì `extends Document`. Đây là đúng hai tên trong `permits`.

**Câu hỏi 2.** `TextDocument` và `RichTextDocument` có phải là kiểu con của `Document` không?

**Trả lời:** Có, theo quan hệ bắc cầu, nhưng chúng là kiểu con **gián tiếp**: `TextDocument` đi qua `EditableDocument`, còn `RichTextDocument` đi qua `TextDocument` và `EditableDocument`.

**Câu hỏi 3.** Có cần đưa `TextDocument`, `RichTextDocument` vào `Document permits` không?

**Trả lời:** Không. Chúng không trực tiếp khai báo `extends`/`implements Document`, nên việc đưa tên vào sẽ không phù hợp với điều kiện direct subtype.

**Câu hỏi 4.** Nếu sửa `TextDocument` thành `class TextDocument implements EditableDocument, Document` thì sao?

**Trả lời:** Khi đó `TextDocument` trực tiếp `implements Document`; nó phải được thêm vào `Document permits` và phải khai báo một trong `final`, `sealed`, `non-sealed`. Nếu vẫn muốn `RichTextDocument extends TextDocument`, có thể chọn `non-sealed class TextDocument implements EditableDocument, Document {}`.

**Câu hỏi 5.** Nếu muốn `EditableDocument` tiếp tục `sealed` và chỉ cho `TextDocument` trực tiếp triển khai nó, phải viết sao?

```java
sealed interface Document permits PdfDocument, EditableDocument {}

final class PdfDocument implements Document {}

sealed interface EditableDocument extends Document
        permits TextDocument {}

non-sealed class TextDocument implements EditableDocument {}

final class RichTextDocument extends TextDocument {}
```

Lúc này `EditableDocument` tự giới hạn kiểu con trực tiếp; `TextDocument` chọn `non-sealed` để cho phép `RichTextDocument` kế thừa sau đó.

## 13. Cách tự phân tích cây sealed không bị nhầm

Đối với mỗi sealed class/interface, trả lời ba câu hỏi theo thứ tự:

1. **Ai trực tiếp nêu tên kiểu này trong `extends` hoặc `implements`?** Chỉ xét một bước kế thừa.
2. **Những kiểu đó có được cho phép không?** So `permits` tường minh, hoặc danh sách suy luận từ cùng compilation unit.
3. **Kiểu con trực tiếp chặn, kiểm soát tiếp hay mở ra?** Class chọn `final`, `sealed`, `non-sealed`; interface chọn `sealed`, `non-sealed`; record ngầm `final`.

Nếu gặp nhánh `sealed`, tiếp tục phân tích tương tự **từ nhánh đó**. Nếu gặp nhánh `non-sealed`, các hậu duệ ở dưới không cần được sealed ancestor liệt kê, miễn chúng không tự khai báo thêm một quan hệ trực tiếp bị hạn chế.

## Tài liệu Java 17

- [JLS 17 — `8.1.1.2`: `sealed`, `non-sealed`, `final` với class](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.1.1.2)
- [JLS 17 — `8.1.4`: Superclasses and Subclasses](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.1.4)
- [JLS 17 — `8.1.5`: Superinterfaces của class](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.1.5)
- [JLS 17 — `8.1.6`: Permitted Direct Subclasses](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.1.6)
- [JLS 17 — `9.1.1.4`: Sealed và Non-Sealed Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.1.1.4)
- [JLS 17 — `9.1.3` và `9.1.4`: Direct Subinterfaces và Permits](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.1.4)
- [JEP 409 — Sealed Classes: tính năng chính thức trong Java 17](https://openjdk.org/jeps/409)

