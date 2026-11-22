# Sealed class và sealed interface trong Java

## 1. Sealed hierarchy là gì?

Trong Java, lớp thông thường có thể được kế thừa bởi các lớp con mà tác giả lớp cha không liệt kê trước (miễn là không có rào cản khác như `final` hoặc quyền truy cập). Một `interface` thông thường cũng có thể được nhiều lớp triển khai. Điều này tốt cho hệ thống cần mở rộng tự do, nhưng gây bất tiện khi **miền nghiệp vụ chỉ có một số biến thể được phép**.

**Sealed class** và **sealed interface** giúp khai báo rõ những kiểu nào được phép **kế thừa hoặc triển khai trực tiếp** một kiểu cha. Từ Java 17, cả hai là tính năng chính thức của ngôn ngữ (JEP 409). Đây là cách mô hình hóa một *type hierarchy* có kiểm soát, thường được gọi là *sealed hierarchy*.

Ví dụ một kết quả xử lý nghiệp vụ chỉ được phép là thành công hoặc thất bại:

```java
sealed interface Result permits Success, Failure {}

record Success(int value) implements Result {}

record Failure(String message) implements Result {}
```

Đây là một **mảnh mã minh họa**, đặt các khai báo trong cùng một compilation unit và dùng Java 17+. Ở đây, chỉ `Success` và `Failure` được phép triển khai `Result` **trực tiếp**. Mỗi `record` tự nó là một kiểu `final`, không thể bị lớp khác kế thừa.

Lợi ích chính:

- **Ràng buộc mô hình:** Tập các biến thể trực tiếp được công bố trong mã nguồn.
- **Dễ đọc thiết kế:** Nhìn vào `permits` là biết các nhánh con trực tiếp mà tác giả cho phép.
- **Hỗ trợ pattern matching:** Từ Java 21, `switch` có thể phân tích tập biến thể của kiểu sealed để kiểm tra **exhaustiveness** (đã bao quát đầy đủ các trường hợp hay chưa).
- **Giảm phần mở rộng ngoài ý muốn:** Bên ngoài tập kiểu được phép không thể tùy ý kế thừa trực tiếp.
- **Không thay thế kiểm tra dữ liệu:** Sealed hạn chế cấu trúc phân cấp kiểu; nó **không chứng minh một đối tượng hoặc component không thể là `null`**, cũng không bảo đảm thuộc tính nghiệp vụ của đối tượng hợp lệ.

Bài này tập trung vào **cú pháp, nguyên tắc kế thừa và điểm khác nhau giữa sealed class và sealed interface**; phần pattern matching được trình bày để thấy mục đích thực tế của thiết kế.

## 2. Điều kiện phiên bản và kiến thức nền

| Thành phần | Phiên bản ổn định đầu tiên | Ghi chú |
| --- | --- | --- |
| `sealed`, `permits`, `non-sealed` | Java 17 | Tính năng chính thức, không cần preview |
| `record` | Java 16 | Có thể `implements` một sealed interface và mặc định là `final` |
| `instanceof Type name` | Java 16 | Có thể dùng với sealed class/interface từ Java 17 |
| Pattern matching trong `switch` | Java 21 | Cho phép các case theo kiểu, `when`, record pattern và kiểm tra tính đầy đủ |
| Record pattern như `case Success(int n)` | Java 21 | Tách dữ liệu của record trong pattern |

Trong ví dụ, JDK 17 là đủ cho việc định nghĩa sealed hierarchy. Các đoạn có `switch` pattern dùng Java 21 trở lên và chỉ sử dụng tính năng đã chính thức.

Kiểm tra JDK đang dùng:

```bash
java -version
javac -version
```

Lệnh `javac --release 17` giúp kiểm tra phần Java 17; `javac --release 21` dùng cho ví dụ pattern `switch` Java 21. Một JDK mới hơn không có nghĩa dự án cấu hình `--release 17` sẽ tự hỗ trợ cú pháp Java 21.

## 3. Khai báo sealed class

Cú pháp tổng quát:

```java
public abstract sealed class Shape permits Circle, Rectangle {
    public abstract double area();
}
```

Đây là một **khai báo minh họa**, cần định nghĩa các lớp con `Circle` và `Rectangle` trực tiếp kế thừa `Shape` trong điều kiện module/package hợp lệ. Các thành phần:

- `sealed`: lớp giới hạn các **lớp con trực tiếp**.
- `permits Circle, Rectangle`: nêu tên những lớp được quyền `extends Shape` trực tiếp.
- `abstract`: tùy chọn; lớp sealed **có thể abstract hoặc concrete**, không buộc phải abstract.
- Phương thức `area()` cho thấy sealed class vẫn là một lớp Java thông thường về field, constructor và hành vi.

Một cách triển khai hợp lệ:

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

Đây là mảnh code Java 17 hợp lệ **khi các khai báo nằm trong cùng một tệp nguồn phù hợp**. `Circle` và `Rectangle` là hai con trực tiếp được phép; chúng chọn `final` để ngăn tiếp tục kế thừa.

**Cần phân biệt:** Nếu `Shape` là `abstract` thì bản thân `Shape` không thể được khởi tạo. Tuy nhiên, `sealed` tự nó **không đồng nghĩa abstract**. Có thể có một sealed class concrete có constructor và được tạo trực tiếp, miễn các ràng buộc khai báo còn lại được đáp ứng.

Một class chỉ được `extends` **một** lớp cha trực tiếp; đây vẫn là quy tắc kế thừa đơn của Java, không thay đổi bởi `sealed`.

## 4. Khai báo sealed interface

Với interface, dạng tương ứng là:

```java
sealed interface Event permits Login, Logout {}

record Login(String username) implements Event {}

record Logout() implements Event {}
```

Ở đây:

- `Event` định nghĩa hợp đồng và giới hạn **kiểu triển khai trực tiếp**.
- `Login` và `Logout` là hai record triển khai `Event`.
- Hai record có thể chứa component và accessor riêng.
- Khác sealed class, một lớp có thể triển khai **nhiều interface** (theo quy tắc Java), dù mỗi sealed interface cần cấp quyền phù hợp cho kiểu triển khai trực tiếp.

Một sealed interface có thể có **interface con trực tiếp** qua `extends`, không chỉ các class/record qua `implements`:

```java
sealed interface Command permits Read, Write {}

record Read(String key) implements Command {}

non-sealed interface Write extends Command {}

final class Save implements Write {}
```

Đây là khai báo minh họa Java 17 trong cùng compilation unit. `Read` là biến thể trực tiếp đã đóng vì record là `final`. `Write` là một interface con trực tiếp **`non-sealed`**, nên `Save` có thể triển khai `Write` mà không cần xuất hiện trong `permits` của `Command`. `Save` không triển khai `Command` trực tiếp về mặt cú pháp khai báo, mà nhận quan hệ với `Command` thông qua `Write`.

**Quan trọng:** `sealed interface` không thể `final` như class. Interface có thể được phép mở rộng bởi interface khác với `sealed` hoặc `non-sealed`; class triển khai trực tiếp phải tuân theo lựa chọn được yêu cầu cho kiểu con. Record đã `final` ngầm định nên không cần và không được khai báo thêm từ khóa `final` vào record.

## 5. Sealed class và sealed interface khác nhau thế nào?

| Tiêu chí | Sealed class | Sealed interface |
| --- | --- | --- |
| Mục tiêu | Kiểm soát các **lớp con trực tiếp** | Kiểm soát các **class/record/enum triển khai trực tiếp và interface con trực tiếp** |
| Cách tạo quan hệ trực tiếp | `extends` | Class/record dùng `implements`; interface con dùng `extends` |
| Kế thừa | Một class chỉ có một superclass | Một class có thể implements nhiều interface |
| Trạng thái (state) | Có thể có instance fields, constructor, triển khai dùng chung | Có constants, abstract/default/static/private methods theo quy tắc interface, không có instance fields |
| Có thể abstract? | Có, nhưng không bắt buộc | Interface vốn thể hiện hợp đồng trừu tượng |
| Có thể `final` ở gốc? | Không thể vừa `final` vừa `sealed` | Interface không có modifier `final` |
| Hợp với thiết kế | Muốn chia sẻ trạng thái/logic chung, constructor hoặc template behavior | Muốn mô hình hóa nhóm biến thể có hợp đồng chung, kể cả `record`, tránh áp đặt lớp cha |
| Tương tác với pattern matching | `switch`/`instanceof` có thể xét kiểu con | Tương tự; đặc biệt hợp với các record làm biến thể |

Ví dụ về lựa chọn:

- Dùng `sealed abstract class Document` nếu mọi loại tài liệu cần dùng chung một trường lưu trạng thái, constructor xác thực và phương thức triển khai chung.
- Dùng `sealed interface Message` nếu các biến thể `TextMessage`, `ImageMessage` và `SystemMessage` có cấu trúc khác nhau, thích hợp là record, và chỉ chia sẻ hợp đồng.
- Nếu muốn dự án bên thứ ba được tự ý tạo kiểu triển khai mới, **sealed có thể không phù hợp**; xem xét interface thông thường hoặc một nhánh `non-sealed` mở có chủ đích.

Sealed không tự quyết định giữa class và interface. Hãy chọn theo **quan hệ “là một”**, nhu cầu state/code dùng chung và quyền mở rộng mong muốn.

## 6. Ba lựa chọn bắt buộc cho kiểu con trực tiếp

Các **kiểu con trực tiếp được liệt kê hoặc suy ra là permitted** phải diễn đạt rõ chúng xử lý khả năng mở rộng tiếp như thế nào. Với class được phép, ba lựa chọn là:

### 6.1. final — đóng tại nhánh con

```java
sealed class Root permits Terminal {}

final class Terminal extends Root {}
```

`Terminal` là con trực tiếp được phép và **không cho kế thừa tiếp**.

### 6.2. sealed — đóng tiếp ở tầng sau

```java
sealed class Root permits Middle {}

sealed class Middle extends Root permits Leaf {}

final class Leaf extends Middle {}
```

`Middle` vừa được `Root` cấp phép, vừa **tự giới hạn** tập con trực tiếp ở tầng kế tiếp. `Leaf` là class cuối nhánh.

### 6.3. non-sealed — mở lại nhánh con

```java
sealed class Root permits ExtensionPoint {}

non-sealed class ExtensionPoint extends Root {}

class CustomExtension extends ExtensionPoint {}
```

`ExtensionPoint` được cho phép làm con trực tiếp, rồi chủ động **mở lại** nhánh cho các class khác có thể kế thừa nó theo các quy tắc Java thông thường. `CustomExtension` **không phải** là con trực tiếp của `Root`, nên không cần tên trong `Root permits`.

Mô hình:

```text
Root (sealed)
  |
  +-- Terminal (final)       -> dừng
  |
  +-- Middle (sealed)        -> tiếp tục liệt kê tập con trực tiếp
  |      |
  |      +-- Leaf (final)
  |
  +-- ExtensionPoint (non-sealed) -> các lớp khác có thể kế thừa nhánh này
           |
           +-- CustomExtension
```

Đây là sơ đồ, không phải cú pháp Java. **Tập con trực tiếp đóng** không nhất thiết đồng nghĩa với **tập mọi hậu duệ ở runtime đóng**, bởi `non-sealed` có thể mở một nhánh.

### Với interface con

Một interface trực tiếp `extends` sealed interface có thể là `sealed` hoặc `non-sealed`; **interface không được final**. Lớp trực tiếp `implements` sealed interface có thể là `final`, `sealed` hoặc `non-sealed`. Record tự nó `final`, vì thế là lựa chọn đặc biệt gọn cho biến thể dữ liệu.

Trong mã thực tế, hãy chọn `non-sealed` có chủ đích: nó làm mất khả năng liệt kê trước toàn bộ kiểu ở nhánh đó, dù tập nhánh trực tiếp của sealed root vẫn được kiểm soát.

## 7. Quy tắc permits: được phép trực tiếp, không phải mọi hậu duệ

### 7.1. Permitted subclass phải trực tiếp kế thừa/triển khai

Nếu `Parent` là sealed:

```java
sealed class Parent permits DirectChild {}

non-sealed class DirectChild extends Parent {}

final class Grandchild extends DirectChild {}
```

`DirectChild` là **direct subclass**. `Grandchild` chỉ là **hậu duệ gián tiếp**; nó không cần và không được liệt kê như một permitted direct subclass của `Parent` khi không trực tiếp `extends Parent`.

Ví dụ cố ý sai:

```java
// SAI: Other chưa trực tiếp extends Parent.
sealed class Parent permits DirectChild, Other {}

final class DirectChild extends Parent {}

final class Other {}
```

Thêm tên vào `permits` **không tự tạo quan hệ kế thừa**. Mỗi kiểu được liệt kê phải khai báo `extends`/`implements` cha theo cách hợp lệ.

### 7.2. Có thể bỏ permits khi cùng compilation unit

Java cho phép **suy ra** danh sách permitted direct subclasses khi các class/interface con trực tiếp được khai báo trong **cùng compilation unit (cùng tệp nguồn)** với kiểu sealed:

```java
sealed interface Job {}

record PrintJob(String text) implements Job {}

record SaveJob(int id) implements Job {}
```

Đây là một mảnh code Java 17, ba khai báo cùng trong một tệp; `permits` có thể bỏ vì compiler xác định `PrintJob` và `SaveJob` là các direct implementors ngay trong compilation unit.

Trong dự án dùng **nhiều tệp**, nên viết `permits` tường minh để hợp đồng dễ thấy và không phụ thuộc vào suy luận của một tệp duy nhất.

### 7.3. Quy tắc module và package

Không thể dùng `permits` để cấp phép tùy ý cho một kiểu trong bất kỳ module/package nào:

- Trong **named module**, các permitted direct subclasses/interfaces phải thuộc **cùng module** với sealed type. Chúng có thể nằm ở package khác nhau nhưng vẫn trong cùng module, với quan hệ truy cập và khai báo hợp lệ.
- Trong **unnamed module** (phổ biến khi chạy dự án trên classpath mà không có module descriptor), các permitted direct subclasses phải ở **cùng package** với sealed type.
- Quy tắc kiểm soát kế thừa vẫn bị chi phối bởi quyền truy cập thông thường (public/package-private, v.v.), khả năng biên dịch và tính hợp lệ của quan hệ kiểu.

Ví dụ dự án không dùng Java modules, có `package app.model; sealed interface Result ...` thì kiểu `app.external.ResultImpl` ở package khác **không thể** được cho phép làm con trực tiếp chỉ bằng cách liệt kê tên nó trong `permits`.

Đây là **giới hạn của định nghĩa sealed**, không phải cơ chế phân quyền bảo mật dữ liệu hay thay thế hệ thống module Java.

### 7.4. Từ khóa non-sealed không dùng độc lập

`non-sealed` chỉ hợp lệ cho class/interface có **superclass hoặc superinterface trực tiếp là sealed**. Không thể tùy tiện thêm `non-sealed` vào một lớp gốc thông thường chỉ để diễn đạt “muốn mở”:

```java
// SAI: không có sealed superclass hoặc superinterface trực tiếp.
non-sealed class ArbitraryRoot {}
```

Lớp mặc định không `final` đã cho phép kế thừa theo quy tắc Java; `non-sealed` tồn tại để **mở lại nhánh bên dưới sealed parent**.

## 8. Ví dụ Java 17 hoàn chỉnh: cả sealed class lẫn sealed interface

Tạo file **`SealedClassAndInterface17.java`** với nội dung sau:

```java
public class SealedClassAndInterface17 {

    static abstract sealed class Vehicle
            permits Car, Bike, OtherVehicle {}

    static final class Car extends Vehicle {
        final String plate;

        Car(String plate) {
            this.plate = plate;
        }
    }

    static abstract sealed class Bike extends Vehicle
            permits RoadBike, MountainBike {}

    static final class RoadBike extends Bike {}

    static final class MountainBike extends Bike {}

    static non-sealed class OtherVehicle extends Vehicle {}

    static final class Boat extends OtherVehicle {}

    static String vehicleName(Vehicle value) {
        if (value == null) {
            return "missing";
        }
        if (value instanceof Car car) {
            return "car:" + car.plate;
        }
        if (value instanceof RoadBike) {
            return "road-bike";
        }
        if (value instanceof MountainBike) {
            return "mountain-bike";
        }
        if (value instanceof Boat) {
            return "boat";
        }
        return "other-vehicle";
    }

    sealed interface Event permits LoginEvent, LogoutEvent {}

    record LoginEvent(String user) implements Event {}

    record LogoutEvent() implements Event {}

    static String eventName(Event event) {
        if (event instanceof LoginEvent login) {
            return "login:" + login.user();
        }
        if (event instanceof LogoutEvent) {
            return "logout";
        }
        return "missing";
    }

    public static void main(String[] args) {
        System.out.println(vehicleName(new Car("ABC")));
        System.out.println(vehicleName(new RoadBike()));
        System.out.println(vehicleName(new MountainBike()));
        System.out.println(vehicleName(new Boat()));
        System.out.println(vehicleName(new OtherVehicle()));
        System.out.println(vehicleName(null));
        System.out.println(eventName(new LoginEvent("Lan")));
        System.out.println(eventName(new LogoutEvent()));
        System.out.println(eventName(null));
    }
}
```

Biên dịch/chạy bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 --release 17 SealedClassAndInterface17.java
java SealedClassAndInterface17
```

**Kết quả chính xác:**

```text
car:ABC
road-bike
mountain-bike
boat
other-vehicle
missing
login:Lan
logout
missing
```

**Phân tích cấu trúc:**

1. `Vehicle` là **abstract sealed class** với ba con trực tiếp: `Car`, `Bike`, `OtherVehicle`.
2. `Car` là `final`, nên không có lớp nào kế thừa nó.
3. `Bike` tiếp tục `sealed` ở tầng thứ hai, cho phép hai lớp `RoadBike` và `MountainBike`. Cả hai đều `final`.
4. `OtherVehicle` là `non-sealed`, nên `Boat` được kế thừa nó dù không có tên trong `Vehicle permits`.
5. `Event` là **sealed interface**, được hai record `LoginEvent` và `LogoutEvent` triển khai trực tiếp.
6. Trong Java 17, dùng `instanceof` type pattern để nhận biết biến thể. Ví dụ `event instanceof LoginEvent login` vừa kiểm tra kiểu vừa tạo biến `login`.
7. `null` không khớp bất kỳ type pattern nào của `instanceof`, nên ví dụ kiểm tra null riêng hoặc trả kết quả dự phòng.

Đoạn mã không dùng `switch` pattern vì Java 17 chưa có tính năng đó ở trạng thái chính thức. Điều này chứng minh **sealed hierarchy dùng được độc lập với pattern matching trong switch**.

## 9. Sealed hierarchy hỗ trợ switch exhaustive trong Java 21

Một trong những lợi ích thiết thực nhất của sealed interface là compiler có thể biết **tập kiểu con được phép** của selector và kiểm tra các nhánh `switch` có đủ hay không.

Tạo file **`SealedSwitch21.java`**:

```java
public class SealedSwitch21 {

    sealed interface Result permits Success, Failure {}

    record Success(int value) implements Result {}

    record Failure(String message) implements Result {}

    static String render(Result result) {
        return switch (result) {
            case null -> "missing";

            case Success(int value) when value >= 0 ->
                    "ok=" + value;

            case Success(int value) ->
                    "invalid=" + value;

            case Failure(String message) ->
                    "error=" + message;
        };
    }

    public static void main(String[] args) {
        System.out.println(render(new Success(5)));
        System.out.println(render(new Success(-2)));
        System.out.println(render(new Failure("timeout")));
        System.out.println(render(null));
    }
}
```

Biên dịch/chạy bằng JDK 21 trở lên:

```bash
javac -encoding UTF-8 --release 21 SealedSwitch21.java
java SealedSwitch21
```

Kết quả:

```text
ok=5
invalid=-2
error=timeout
missing
```

**Vì sao switch expression không cần `default`?**

- `Result` chỉ có hai kiểu triển khai trực tiếp: `Success` và `Failure`. Hai record là `final`, vì vậy không có lớp con mới ở dưới chúng.
- `case Success(int value)` không guard bao phủ mọi `Success` còn lại, kể cả khi nhánh guard `value >= 0` phía trước không được chọn.
- `case Failure(String message)` bao phủ nhánh còn lại của hierarchy theo hợp đồng đã khai báo.
- `case null` nêu rõ lựa chọn xử lý selector bằng `null`, thay vì nhầm rằng `default` tự bắt null.
- Với kiểu selector `Result`, compiler có thể chứng minh các biến thể hợp lệ của hierarchy được xử lý và chấp nhận `switch expression` không có `default`.

Nếu bạn thêm `Pending` làm biến thể trực tiếp mới và cập nhật `permits`:

```java
// Minh họa thay đổi có chủ đích; đây không phải phần
// cần chèn nguyên xi vào ví dụ chạy ở trên.
sealed interface Result permits Success, Failure, Pending {}

record Pending() implements Result {}
```

mà không bổ sung case `Pending` cho `render`, compiler sẽ yêu cầu xử lý biến thể thiếu vì `switch expression` không còn exhaustive.

**Lưu ý:** `when` giới hạn tập giá trị của một case. Chỉ có `case Success(int value) when value >= 0` sẽ **không** bao quát `Success(-2)`. Vì thế ví dụ có nhánh `Success` không guard ở phía sau. Case tổng quát đặt trước case có guard cùng kiểu có thể tạo lỗi **dominance**.

### Null không tự được bảo đảm bởi sealed

Kiểu biến `Result` vẫn có thể là `null` nếu không có kiểm tra khác. Chỉ vì các biến thể là sealed/record không có nghĩa biến tham chiếu luôn tồn tại. Trong Java 21, pattern `switch` với selector `null` sẽ ném `NullPointerException` nếu không có cơ chế xử lý null thích hợp. Ví dụ này dùng `case null` để thể hiện hành vi mong muốn.

Nếu miền nghiệp vụ **cấm** null, có thể đặt `Objects.requireNonNull(result)` ở ranh giới của API, hoặc dùng `case null -> throw new IllegalArgumentException(...)` thay vì kết quả `"missing"`.

## 10. Sealed class/interface và instanceof không tự kiểm tra đủ biến thể

Trên Java 17, `instanceof` nhận biết đối tượng tại thời điểm chạy:

```java
static String status(Object value) {
    if (value instanceof String text) {
        return "text=" + text;
    }
    if (value instanceof Integer number) {
        return "integer=" + number;
    }
    return "other";
}
```

Đây là phương thức minh họa Java 17, không tự liên quan sealed hierarchy. Nếu selector là một interface sealed, bạn cũng có thể viết chuỗi `instanceof` theo từng kiểu con. Tuy nhiên, compiler **không tự kiểm tra tính đầy đủ của toàn bộ chuỗi `if/else`** giống cách nó phân tích `switch` pattern với selector sealed trên Java 21.

Lợi ích của sealed không phải `instanceof` “nhận diện mọi kiểu nhanh hơn”, mà là thiết kế kiểu **đóng rõ ràng** để Java và người bảo trì hiểu các biến thể có thể xảy ra.

Với đoạn `instanceof` nhiều nhánh, vẫn cần quyết định xử lý trường hợp không khớp và `null`. Nếu logic lặp ở nhiều nơi, cân nhắc `switch` exhaustive (Java 21) hoặc phương thức đa hình thay vì sao chép nhiều chuỗi `if`.

## 11. Sealed không có nghĩa mọi đường kế thừa đều bị khóa

Hãy xem sơ đồ sau:

```text
Vehicle (sealed)
 ├── Car (final)
 ├── Bike (sealed)
 │    ├── RoadBike (final)
 │    └── MountainBike (final)
 └── OtherVehicle (non-sealed)
      ├── Boat (final)
      └── ... các lớp con khác
```

- Các con **trực tiếp** của `Vehicle` vẫn giới hạn ở `Car`, `Bike` và `OtherVehicle`.
- Ở nhánh `Car` không thêm được lớp con.
- Ở nhánh `Bike` chỉ được kế thừa theo tập con đã khai báo.
- Ở nhánh `OtherVehicle` có thể có những hậu duệ mới mà `Vehicle` không liệt kê.

Điều này có hai hệ quả đối với pattern matching:

1. Nếu xử lý `Vehicle` trong Java 21, một nhánh `case OtherVehicle v` có thể bao quát cả `Boat` và các hậu duệ chưa biết phía dưới `OtherVehicle`.
2. **Không thể** dùng sealed root để kết luận toàn bộ hậu duệ runtime là một danh sách bất biến nếu có nhánh `non-sealed`.

Ví dụ, nếu nghiệp vụ muốn xử lý mọi phương tiện thuộc nhánh mở theo cùng logic, điều đó ổn. Nhưng nếu chỉ cho phép các loại phương tiện cố định tuyệt đối, đừng mở `non-sealed` tại một nhánh cốt lõi.

## 12. Những giới hạn và lỗi biên dịch thường gặp

### Lỗi 1 — Con trực tiếp không chọn final/sealed/non-sealed

```java
// CỐ Ý SAI: Child là direct subclass của sealed Parent
// nhưng không khai báo modifier phù hợp.
sealed class Parent permits Child {}

class Child extends Parent {}
```

Sửa thành `final class Child extends Parent {}`, hoặc `sealed`/`non-sealed` cùng quan hệ và các permitted descendants hợp lệ.

### Lỗi 2 — Không có tên trong permits

```java
sealed class Parent permits Allowed {}

final class Allowed extends Parent {}

// CỐ Ý SAI: Forbidden không được Parent cho phép.
final class Forbidden extends Parent {}
```

Với `permits` tường minh, chỉ các tên đã cho phép có thể là direct subclass. Việc class ở cùng package chưa đủ để tự động được thêm khi danh sách đã ghi tường minh.

### Lỗi 3 — Permitted type không thực sự là con trực tiếp

```java
// CỐ Ý SAI: NotChild không extends Parent.
sealed class Parent permits Allowed, NotChild {}

final class Allowed extends Parent {}

final class NotChild {}
```

Thay đổi một dòng trong `permits` không tạo quan hệ kiểu. Kiểm tra đúng `extends` hoặc `implements`.

### Lỗi 4 — Kết hợp final và sealed cho cùng class

```java
// CỐ Ý SAI: final cấm kế thừa, sealed định nghĩa các con được phép.
final sealed class Contradiction {}
```

Hai lựa chọn này trái vai trò nhau. Chọn `final` nếu muốn **không có lớp con**; chọn `sealed` nếu muốn có **tập lớp con cụ thể**.

### Lỗi 5 — Dùng non-sealed không có cha sealed trực tiếp

```java
// CỐ Ý SAI:
non-sealed class FreeClass {}
```

`non-sealed` chỉ là modifier để mở lại nhánh bên dưới kiểu sealed trực tiếp. Một class bình thường không `final` đã có khả năng được kế thừa theo quy tắc thông thường.

### Lỗi 6 — Nghĩ record được extends class

```java
// CỐ Ý SAI: record không thể extends class do người dùng định nghĩa.
sealed class Message permits TextMessage {}

record TextMessage(String text) extends Message {}
```

Record kế thừa ngầm định từ `java.lang.Record`, không thể `extends Message`. Nếu muốn dùng record làm biến thể, thường chọn **sealed interface**:

```java
sealed interface Message permits TextMessage {}

record TextMessage(String text) implements Message {}
```

### Lỗi 7 — Đặt kiểu con được cho phép sai module/package

Nếu dùng classpath/unnamed module, permitted direct subclass phải nằm **cùng package** với sealed type. Với named module, phải nằm **cùng module**. Đừng mong `permits` vượt các giới hạn đó.

### Lỗi 8 — Quên thêm case khi mở rộng hierarchy

Với Java 21, `switch expression` đã từng exhaustive có thể không còn exhaustive khi thêm permitted direct subclass mới. Khi đó cần xem lại logic từng vị trí dùng pattern switch. Điều này có chủ đích: **thay đổi cấu trúc miền dữ liệu kéo theo yêu cầu xem lại xử lý**.

### Lỗi 9 — Tưởng sealed là cơ chế chống mọi runtime subclass

`non-sealed` có thể cho hậu duệ mở rộng. Hơn nữa, sealed class/interface là **ràng buộc mô hình và kế thừa của ngôn ngữ**, không thay thế kiểm tra quyền truy cập đối tượng, validation, an ninh API hay kiểm soát dữ liệu từ bên ngoài.

## 13. Sealed hierarchy, polymorphism và tổ chức mã

Một sealed hierarchy có thể được xử lý bằng nhiều chiến lược:

**Chiến lược 1 — Đa hình:** Định nghĩa phương thức hành vi chung, mỗi biến thể tự triển khai. Ví dụ `Shape.area()` trên `Circle` và `Rectangle`. Cách này hợp khi hành vi là đặc trưng ổn định của từng kiểu và sẽ được gọi ở nhiều nơi. Nó vẫn dùng được với sealed type.

**Chiến lược 2 — Pattern switch (Java 21):** Dùng `switch (shape)` ở một nơi muốn biến đổi/hiển thị/kết xuất dữ liệu theo các biến thể. Cách này hợp khi cần **một phép biến đổi bên ngoài** từng kiểu và muốn compiler kiểm tra đủ nhánh.

**Chiến lược 3 — Visitor hoặc bộ xử lý riêng:** Có thể phù hợp với mã có nhiều phép xử lý, cần tách lớp domain khỏi xử lý hoặc phải hỗ trợ phiên bản Java cũ. Sealed giúp giới hạn mô hình, nhưng không tự thay visitor.

Không có chiến lược nào tốt trong mọi tình huống. Nếu mọi phép xử lý đều là một `switch` lớn đặt trong hàng chục phương thức, cân nhắc đa hình. Ngược lại, nếu bạn có một số bộ chuyển đổi dữ liệu độc lập, một `switch` exhaustive thường rõ ràng và ít boilerplate.

### Phân biệt đóng dữ liệu và đóng hành vi

`sealed` “đóng” **tập kiểu con trực tiếp**, không đóng giá trị của các field. Ví dụ `record Success(int value)` cho phép nhiều giá trị `value`; `record Failure(String message)` có thể chứa một chuỗi hoặc giá trị `null` nếu không có validation riêng. Muốn đảm bảo dữ liệu hợp lệ, dùng constructor/compact constructor, kiểm tra bất biến và unit tests.

Tập con được phép cũng không tự giới hạn số lượng đối tượng được khởi tạo. Có thể tạo nhiều `Success` với những giá trị khác nhau; sealed không làm các đối tượng biến thành singleton.

## 14. Thiết kế sealed hierarchy theo từng bước

Một quy trình giúp tránh lựa chọn modifier ngẫu nhiên:

1. **Liệt kê các biến thể thực sự của miền nghiệp vụ.** Ví dụ `Success`, `Failure`, `Pending`. Kiểm tra xem tập đó có dự kiến được mở rộng bởi plugin hoặc đối tác không.
2. **Chọn sealed class hay sealed interface.** Cần constructor, state, mã dùng chung và một superclass có ý nghĩa? Cân nhắc sealed class. Cần nhiều record/kiểu triển khai độc lập và đa hợp đồng? Cân nhắc sealed interface.
3. **Vẽ cây kiểu con trực tiếp và gián tiếp.** Không liệt kê hậu duệ vào `permits` của ông/bà nếu chúng không trực tiếp kế thừa.
4. **Đặt chính sách cho mỗi con trực tiếp.** `final` để đóng, `sealed` để phân cấp có kiểm soát ở tầng sau, `non-sealed` để mở nhánh có chủ đích.
5. **Kiểm tra vị trí module/package.** Trên classpath, các permitted direct subclasses phải cùng package; trong named module, phải cùng module.
6. **Nếu muốn bỏ permits, kiểm tra compilation unit.** Khi direct subclasses khai báo chung một file, Java có thể suy ra; ở hệ nhiều file nên viết rõ.
7. **Xác định quy ước null và validation.** Chọn lỗi hay trạng thái khi đầu vào null, validation của record components, tính bất biến cần có.
8. **Chọn logic sử dụng biến thể.** Đa hình, `instanceof` (Java 17), pattern `switch` exhaustive (Java 21) hoặc một API riêng.
9. **Kiểm thử thêm subtype.** Thử thêm direct subclass không được phép để xác nhận lỗi compile, thêm permitted subtype để xem các `switch` exhaustive yêu cầu cập nhật, và kiểm tra nhánh `non-sealed` nếu có.

Đừng sealed chỉ để dùng một cú pháp mới. Chọn sealed khi **những biến thể được phép là một phần thiết kế công khai của miền dữ liệu**.

## 15. Bài tập thực hành

### Bài 1 — Sealed class với hai tầng

Tạo `abstract sealed class Payment permits Cash, Card, Gift`. Định nghĩa `Cash` là `final`, `Card` là `sealed` có hai subtype `DebitCard` và `CreditCard` (đều `final`), còn `Gift` là `non-sealed`. Vẽ cây kế thừa, tạo thêm `PartnerGift extends Gift` và giải thích tại sao nó không xuất hiện trong `Payment permits`.

### Bài 2 — Chuyển class sang sealed interface

Tạo `sealed interface Notification permits Email, Sms` cùng hai `record`. Viết phương thức nhận `Notification` và dùng `instanceof` Java 17 để trả mô tả. Sau đó so sánh mức tiện lợi của record/constructor khi dùng sealed interface thay vì sealed class.

### Bài 3 — Quan hệ con trực tiếp

Với hierarchy:

```text
Root
  -> Branch
       -> Leaf
```

Nếu `Root` sealed và `Branch` sealed, hãy xác định danh sách `permits` chính xác của hai loại. Vì sao `Leaf` không được liệt kê trong `Root permits` trừ khi nó thực sự là con trực tiếp?

### Bài 4 — Bỏ permits và compilation unit

Đặt `sealed interface Job`, `record Upload` và `record Download` cùng một file; thử bỏ `permits`. Sau đó tách sang nhiều tệp trong cùng package và bổ sung `permits` rõ ràng. Chú ý sự khác nhau giữa **cùng package** với **cùng compilation unit**.

### Bài 5 — Exhaustive switch trong Java 21

Chạy `SealedSwitch21`. Thêm `record Pending() implements Result` và đưa nó vào `Result permits`. Quan sát lỗi biên dịch ở `render`; bổ sung `case Pending p -> "pending"`, rồi xác nhận lại kết quả.

### Bài 6 — Guard không bao phủ toàn bộ biến thể

Trong `render`, thử bỏ case `Success(int value)` không guard, chỉ giữ case `when value >= 0`. Vì sao `Success(-2)` chưa được xử lý? Giải thích tại sao sealed không làm guard tự bao quát các giá trị còn lại.

### Bài 7 — Quyết định non-sealed có chủ đích

Bạn thiết kế hệ thông báo cho thư viện bên thứ ba được bổ sung kiểu mới, nhưng vẫn muốn nhóm `SystemNotification` được giới hạn. Hãy đề xuất interface `sealed` gốc, một nhánh `sealed` cho hệ thống và một nhánh `non-sealed` cho phần mở rộng. Chỉ ra các hệ quả cho `switch` exhaustive.

### Bài 8 — Sửa lỗi biên dịch

Giải thích và sửa bốn lỗi: permitted class không trực tiếp kế thừa, direct subclass thiếu `final`/`sealed`/`non-sealed`, record dùng `extends` một class do người dùng định nghĩa, và `non-sealed` trên lớp không có sealed parent trực tiếp.

## 16. Câu hỏi tự đánh giá

1. `sealed` đóng những kiểu con nào: trực tiếp hay mọi hậu duệ? Một nhánh `non-sealed` thay đổi câu trả lời ra sao?
2. Điểm khác biệt quan trọng nhất giữa `sealed class` và `sealed interface` khi muốn dùng `record` là gì?
3. Vì sao một permitted direct class phải chọn `final`, `sealed` hoặc `non-sealed`? Interface con có thể `final` không?
4. Từ khóa `permits` có thể bỏ trong điều kiện nào? “Cùng package” có tự đủ để bỏ `permits` không?
5. Có thể cấp phép direct subclass ở module khác không? Quy tắc giữa named module và unnamed module khác nhau như thế nào?
6. Sealed class có bắt buộc `abstract` không? `final sealed class` có hợp lệ không?
7. Thêm subtype vào sealed hierarchy sẽ ảnh hưởng thế nào tới `switch` expression exhaustive Java 21 không có `default`?
8. Tại sao guard `when` chỉ phủ một tập con không thể mặc nhiên thay thế case bao quát?
9. Vì sao kiểm tra `null` và tính hợp lệ của record component vẫn cần thiết khi dùng sealed?
10. Trong bài toán của bạn, logic nên đặt ở phương thức đa hình hay `switch` pattern? Vì sao?

Hoàn thành bài khi bạn có thể **viết hai dạng khai báo sealed, xác định đúng các permitted direct subclasses, giải thích ba lựa chọn modifier của từng nhánh và xây dựng `switch` exhaustive** trên sealed interface ở Java 21.

## 17. Nguồn chính thức

- [JEP 409 — Sealed Classes](https://openjdk.org/jeps/409): mục tiêu, cú pháp và quy tắc giới hạn kiểu con, chính thức từ Java 17.
- [Java Language Specification, Java SE 17 — `8.1.1.2 sealed, non-sealed and final Classes](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.1.1.2): quy tắc khai báo class, permitted subclasses và modifier.
- [Java Language Specification, Java SE 17 — `9.1.1.4 sealed and non-sealed Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.1.1.4): điều kiện sealed interface và interface con.
- [JEP 395 — Records](https://openjdk.org/jeps/395): record là kiểu class có cấu trúc cố định, hữu ích khi triển khai sealed interface.
- [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394): `instanceof` type pattern dùng từ Java 16.
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441): `switch` theo pattern, tính đầy đủ và guard chính thức từ Java 21.
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440): dùng record pattern để tách component trong `switch` từ Java 21.

**Ghi nhớ:** Sealed là công cụ **kiểm soát kiến trúc kế thừa và mô hình miền dữ liệu**, không phải cơ chế validation tự động. `sealed class` phù hợp khi cần lớp cha chia sẻ state/hành vi, còn `sealed interface` linh hoạt cho tập các biến thể dữ liệu và `record`. Lợi ích kiểm tra đủ nhánh bằng pattern `switch` thể hiện rõ nhất từ Java 21.
