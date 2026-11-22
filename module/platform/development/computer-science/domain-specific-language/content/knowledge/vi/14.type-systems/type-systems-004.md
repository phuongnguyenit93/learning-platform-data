# Kiểu con và đa hình trong hệ kiểu DSL

Một DSL thường mô hình hóa khái niệm của miền bằng kiểu dữ liệu. Khi miền có nhiều loại đối tượng liên quan, hệ kiểu cần diễn đạt quan hệ giữa chúng và cho phép một thao tác làm việc với nhiều loại giá trị phù hợp. Hai khái niệm quan trọng là **kiểu con** (*subtyping*) và **đa hình** (*polymorphism*).

Kiểu con cho biết một giá trị thuộc kiểu cụ thể có thể được dùng ở nơi yêu cầu kiểu tổng quát hơn hay không. Đa hình cho phép cùng một giao diện hoặc đoạn chương trình làm việc với nhiều dạng giá trị. Trong DSL, hai cơ chế này giúp một quy tắc vận chuyển nhận nhiều loại phương tiện, một workflow xử lý nhiều loại sự kiện, hoặc một biểu thức làm việc với nhiều kiểu đối tượng cùng tuân theo một hợp đồng.

Ví dụ, miền vận chuyển có kiểu `Vehicle` và các kiểu chuyên biệt `Car`, `Truck`, `Motorbike`. Một hàm tính phí nhận `Vehicle` có thể nhận một `Car` nếu `Car` là kiểu con hợp lệ của `Vehicle`.

## 1. Kiểu con là gì?

**Subtyping** là quan hệ giữa hai kiểu, cho biết giá trị thuộc kiểu này có thể được dùng an toàn ở vị trí yêu cầu kiểu kia hay không.

Ký hiệu:

```text
S <: T
```

đọc là “S là kiểu con của T”. Nếu `S <: T`, giá trị kiểu S có thể được chấp nhận ở nơi yêu cầu T, theo quy tắc của hệ kiểu.

Ví dụ:

```text
Car <: Vehicle
Truck <: Vehicle
Motorbike <: Vehicle
```

- **Supertype:** kiểu tổng quát được dùng làm hợp đồng chung.
- **Subtype:** kiểu chuyên biệt thỏa hợp đồng của supertype và có thể bổ sung thuộc tính hoặc hành vi.
- **Subtype relation:** quan hệ xác định kiểu nào có thể thay thế kiểu nào.

Không phải mọi quan hệ liên quan trong nghiệp vụ đều là quan hệ kiểu con. `Engine` là một thành phần của `Car`, nhưng không vì thế mà `Engine <: Car`. Quan hệ thành phần (*has-a*) khác quan hệ kiểu con (*is-a*).

### Các tính chất thường gặp

**Reflexivity:** mọi kiểu là kiểu con của chính nó.

```text
T <: T
```

**Transitivity:** nếu S là kiểu con của T và T là kiểu con của U thì S cũng là kiểu con của U.

```text
S <: T
T <: U
---------
S <: U
```

Ví dụ `ElectricCar <: Car` và `Car <: Vehicle` suy ra `ElectricCar <: Vehicle`.

Trong một hệ kiểu được chuẩn hóa, nếu hai kiểu là kiểu con của nhau thì chúng thường được xem là tương đương về mặt quan hệ thứ tự. Bí danh và kiểu tương đương có thể khiến danh tính kiểu phức tạp hơn, nhưng hệ thống cần tránh các chu trình quan hệ gây mơ hồ.

## 2. Kiểu con khác kế thừa lớp như thế nào?

**Class inheritance** là cơ chế trong đó lớp con kế thừa trường hoặc phương thức từ lớp cha. **Subtyping** là quan hệ của hệ kiểu: giá trị kiểu con có thể được dùng tại vị trí yêu cầu kiểu cha.

Hai khái niệm thường đi cùng nhau nhưng không đồng nhất:

- Một lớp con thường tạo quan hệ kiểu con với lớp cha.
- Interface hoặc protocol có thể tạo quan hệ kiểu con mà không cần kế thừa trạng thái hay mã cài đặt.
- Hệ structural có thể xác định kiểu con từ các thành viên được hỗ trợ, không cần khai báo kế thừa.
- Kế thừa mã cài đặt không tự bảo đảm hành vi của kiểu con đáp ứng hợp đồng của kiểu cha.

Ví dụ, `JsonRecord` và `DatabaseRow` có thể cùng cung cấp `getField(name)`. Một DSL structural có thể xem cả hai là kiểu con của `FieldReadable` dù chúng không kế thừa từ cùng một lớp.

## 3. Nominal và structural subtyping

### Nominal subtyping – kiểu con theo khai báo

Trong **nominal subtyping**, quan hệ kiểu con được xác lập bằng khai báo tường minh như `extends` hoặc `implements`.

```text
type Vehicle {
    field registrationNumber: String
    function move(): Unit
}

type Car extends Vehicle {
    field seatCount: Integer
}
```

`Car` là kiểu con của `Vehicle` vì khai báo `extends Vehicle` nói rõ quan hệ đó.

Ưu điểm là quan hệ kiểu dễ tra cứu, dễ giải thích và tránh việc hai kiểu tình cờ có cùng trường bị xem là thay thế cho nhau. Đổi lại, kiểu phải khai báo quan hệ tương thích; một kiểu có đủ thành viên vẫn không tự động trở thành subtype.

### Structural subtyping – kiểu con theo cấu trúc

Trong **structural subtyping**, một kiểu là subtype nếu cấu trúc của nó đáp ứng yêu cầu của kiểu tổng quát.

```text
type Movable {
    function move(): Unit
}
```

Một kiểu có phương thức `move(): Unit` có thể thỏa `Movable` mà không cần khai báo implements.

Cách này thuận tiện khi tích hợp record, schema và dữ liệu từ nhiều nguồn. Tuy nhiên, quan hệ có thể phát sinh ngoài dự kiến khi các kiểu tình cờ có cùng cấu trúc; thay đổi thành viên cũng có thể làm thay đổi quan hệ kiểu con.

| Tiêu chí | Nominal | Structural |
|---|---|---|
| Cơ sở | Tên và khai báo quan hệ | Thành viên và kiểu của chúng |
| Tính tường minh | Cao | Có thể ngầm định |
| Tái sử dụng | Cần khai báo tương thích | Có thể dùng kiểu không liên quan về tên |
| Rủi ro | Khai báo quan hệ nhưng hành vi không phù hợp | Quan hệ phát sinh ngoài dự kiến |
| Phù hợp | Phân cấp miền rõ ràng | Record, schema, protocol và tích hợp dữ liệu |

Một DSL có thể kết hợp cả hai: nominal subtyping cho entity nghiệp vụ, structural typing cho record hoặc object literal.

## 4. Substitutability và Liskov Substitution Principle

Mục tiêu quan trọng của kiểu con là **substitutability**: giá trị kiểu con có thể thay thế giá trị kiểu cha mà không phá vỡ tính đúng đắn theo hợp đồng của kiểu cha.

Nếu `Car <: Vehicle`, hàm nhận `Vehicle` phải xử lý được `Car` theo những cam kết mà Vehicle công bố.

```text
function dispatch(vehicle: Vehicle): Route {
    return vehicle.planRoute()
}
```

**Liskov Substitution Principle (LSP)** yêu cầu đối tượng của kiểu con có thể thay thế đối tượng kiểu cha mà không làm sai tính đúng đắn của chương trình.

Một số hệ quả thực tế:

- Kiểu con không nên yêu cầu điều kiện đầu vào mạnh hơn hợp đồng của kiểu cha.
- Kiểu con không nên làm suy yếu cam kết đầu ra của kiểu cha.
- Kiểu con phải duy trì invariant mà kiểu cha yêu cầu.
- Kiểu con không nên tạo ngoại lệ hoặc hành vi trái với hợp đồng đã công bố.

Các khái niệm liên quan:

- **Precondition:** điều kiện người gọi phải đáp ứng trước khi gọi thao tác.
- **Postcondition:** điều mà thao tác cam kết sau khi hoàn thành.
- **Invariant:** điều kiện phải luôn đúng đối với trạng thái hợp lệ.

Khi override, kiểu con không nên làm precondition chặt hơn. Nó có thể chấp nhận ít nhất mọi đầu vào mà kiểu cha chấp nhận; postcondition cần giữ hoặc tăng cường cam kết của kiểu cha.

Ví dụ, nếu `Vehicle.move()` được cam kết gọi được trên mọi phương tiện, một kiểu con không nên luôn ném lỗi “không thể di chuyển”. Nếu một đối tượng không có hành vi di chuyển theo nghĩa của miền, nên mô hình hóa hợp đồng khác thay vì ép nó vào Vehicle.

## 5. Polymorphism – đa hình

**Polymorphism** là khả năng dùng cùng một giao diện, biểu thức hoặc đoạn chương trình với nhiều dạng giá trị. Trong **subtype polymorphism**, biến hoặc tham số có kiểu tổng quát có thể tham chiếu đến các giá trị thuộc nhiều kiểu con.

```text
function describe(vehicle: Vehicle): String {
    return vehicle.description()
}

describe(Car(...))
describe(Truck(...))
describe(Motorbike(...))
```

Hàm describe khai báo một lần với kiểu Vehicle và có thể nhận nhiều subtype. Đa hình giúp tái sử dụng logic, mở rộng miền bằng kiểu con mới và tách hợp đồng chung khỏi cách triển khai cụ thể.

### Các dạng đa hình

**Subtype polymorphism:** giá trị kiểu con được dùng ở nơi yêu cầu kiểu cha; lời gọi phương thức có thể được dispatch theo kiểu thực tế.

**Parametric polymorphism:** hàm hoặc kiểu được tham số hóa theo kiểu khác.

```text
type Box<T> {
    value: T
}

function identity<T>(value: T): T {
    return value
}
```

`Box<T>` có thể chứa nhiều kiểu giá trị; identity làm việc với T mà không cần biết T cụ thể. Cơ chế này thường được triển khai bằng generics.

**Ad hoc polymorphism:** cùng tên thao tác có nhiều triển khai tùy kiểu đối số, thường qua overloading hoặc type class.

```text
format(Integer) -> "42"
format(Date)    -> "2026-11-15"
format(Money)   -> "$42.00"
```

**Coercion:** hệ thống tự chuyển một giá trị từ kiểu này sang kiểu khác theo quy tắc. Coercion không đồng nghĩa với subtyping: một giá trị có thể được chấp nhận nhờ chuyển đổi mà không phải subtype của kiểu đích.

| Dạng | Cơ chế | Ví dụ |
|---|---|---|
| Subtype | Dùng giá trị kiểu con ở vị trí kiểu cha | Car truyền vào Vehicle |
| Parametric | Tham số hóa theo kiểu | Box<T> |
| Ad hoc | Chọn triển khai theo kiểu đối số | Overload format |
| Coercion | Chuyển đổi giá trị | Integer sang Decimal |

## 6. Static type, dynamic type và dispatch

- **Static type:** kiểu được xác định từ khai báo và phân tích trước khi chạy.
- **Dynamic type:** kiểu cụ thể của object tại thời điểm chạy.

```text
let vehicle: Vehicle = Car(...)
```

Trong ví dụ, static type của vehicle là Vehicle; dynamic type của object là Car. Type checker chỉ cho phép truy cập các thành viên của Vehicle, trừ khi có narrowing hợp lệ.

**Dynamic dispatch** chọn implementation dựa trên kiểu thực tế của object lúc chạy. **Static dispatch** chọn implementation dựa trên kiểu tĩnh và chữ ký đã biết.

**Method overriding** là khi kiểu con cung cấp implementation thay thế cho phương thức của kiểu cha. **Overloading** là khi có nhiều hàm cùng tên nhưng khác chữ ký và thường được phân giải dựa trên kiểu tĩnh.

```text
type Vehicle {
    function fare(distance: Decimal): Money
}

type Car extends Vehicle {
    override function fare(distance: Decimal): Money {
        return distance * 2.5
    }
}

type Truck extends Vehicle {
    override function fare(distance: Decimal): Money {
        return distance * 5.0
    }
}

function calculate(vehicle: Vehicle, distance: Decimal): Money {
    return vehicle.fare(distance)
}
```

Lời gọi `vehicle.fare` có thể chạy implementation của Car hoặc Truck tùy dynamic type. Không phải mọi hàm đều cần dynamic dispatch; DSL có thể dùng static dispatch cho hàm thuần hoặc overload và dynamic dispatch cho phương thức virtual/interface.

## 7. Interface, abstract type và protocol

Một DSL có thể mô hình hóa hợp đồng chung bằng interface, abstract type hoặc protocol.

```text
interface Payable {
    function amountDue(): Money
    function pay(method: PaymentMethod): Receipt
}
```

Các kiểu Invoice, Subscription và Order có thể thỏa Payable nếu cung cấp các thao tác cần thiết.

- **Interface:** mô tả chữ ký hoặc tập hành vi mà kiểu triển khai phải cung cấp.
- **Abstract type/class:** kiểu tổng quát không nhất thiết tạo instance trực tiếp; có thể cung cấp một phần triển khai.
- **Protocol:** mô tả tập hành vi mà một kiểu phải đáp ứng. Trong structural typing, kiểu có thể thỏa protocol mà không cần khai báo kế thừa.

Interface và protocol hữu ích khi một kiểu có nhiều khả năng độc lập, chẳng hạn Payable, Auditable và Cancellable, thay vì ép mọi khả năng vào một cây kế thừa sâu.

## 8. Type checking cho quan hệ kiểu con

Type checker xác định giá trị có thể được dùng ở vị trí yêu cầu kiểu khác hay không.

Quy tắc gán cơ bản:

```text
Γ ⊢ value : S
S <: T
----------------
Γ ⊢ value : T
```

`Γ` là môi trường kiểu; `Γ ⊢ value : S` nghĩa là value có kiểu S trong môi trường đó. Nếu S là subtype của T, value có thể được xem là T.

Ví dụ:

```text
let car: Car = Car(...)
let vehicle: Vehicle = car
```

Phép gán hợp lệ khi `Car <: Vehicle`.

Với hàm:

```text
function dispatch(vehicle: Vehicle): Unit
```

lời gọi `dispatch(Car(...))` hợp lệ nếu Car là subtype của Vehicle. Nếu Engine không phải subtype, type checker cần từ chối trừ khi có conversion được định nghĩa.

Một hàm khai báo trả về Vehicle có thể trả về Car vì kiểu trả về thực tế là subtype của kiểu công bố.

Khi kiểm tra override, type checker cần kiểm tra chữ ký, số lượng tham số, kiểu trả về, khả năng override của phương thức cha, visibility và quy tắc variance của ngôn ngữ. Kiểm tra kiểu không tự chứng minh mọi hành vi nghiệp vụ; LSP còn cần hợp đồng và kiểm thử hành vi.

## 9. Variance – tính biến thiên của kiểu tham số

Khi generic type chứa tham số kiểu T, cần xác định quan hệ kiểu con có được truyền qua tham số hóa hay không. Đó là **variance**.

Giả sử:

```text
Cat <: Animal
```

### Covariance – đồng biến

Generic type covariant nếu quan hệ subtype được giữ cùng chiều:

```text
Cat <: Animal
Source<Cat> <: Source<Animal>
```

Điều này phù hợp với cấu trúc chỉ cung cấp T để đọc. Kotlin dùng `out`:

```kotlin
interface Source<out T> {
    fun get(): T
}
```

Source<Cat> có thể được dùng như Source<Animal> vì nó chỉ trả ra T.

### Contravariance – nghịch biến

Generic type contravariant nếu quan hệ subtype bị đảo chiều:

```text
Cat <: Animal
Consumer<Animal> <: Consumer<Cat>
```

Một consumer nhận được mọi Animal thì có thể nhận Cat. Kotlin dùng `in`:

```kotlin
interface Consumer<in T> {
    fun accept(value: T)
}
```

### Invariance – bất biến theo tham số

Generic type invariant nếu không suy ra quan hệ subtype giữa các phiên bản tham số hóa:

```text
Cat <: Animal
MutableBox<Cat> </: MutableBox<Animal>
MutableBox<Animal> </: MutableBox<Cat>
```

Container vừa đọc vừa ghi thường cần invariant. Nếu MutableBox<Cat> được dùng như MutableBox<Animal>, người gọi có thể ghi Dog vào nơi chỉ được chứa Cat.

Java generics mặc định invariant. Wildcard hỗ trợ variance tại vị trí sử dụng:

```java
void copy(
    List<? extends Number> source,
    List<? super Number> destination
) {
    for (Number value : source) {
        destination.add(value);
    }
}
```

Nguyên tắc PECS: Producer Extends khi đọc giá trị từ collection; Consumer Super khi ghi giá trị vào collection. Đây là use-site variance của Java, khác declaration-site variance `out` và `in` của Kotlin.

| Variance | Quan hệ | Dùng khi |
|---|---|---|
| Covariant | Cùng chiều | Producer chỉ trả T |
| Contravariant | Đảo chiều | Consumer chỉ nhận T |
| Invariant | Không suy ra quan hệ | Container đọc và ghi T |

## 10. Variance của function type

Một function type `(A) -> R` nhận A và trả về R. Tham số hàm thường contravariant, kết quả thường covariant:

```text
If A2 <: A1 and R1 <: R2
then (A1 -> R1) <: (A2 -> R2)
```

Hàm nhận A1 có thể nhận A2 nếu A2 là subtype của A1. Hàm trả về R1 có thể dùng ở nơi mong đợi R2 nếu R1 là subtype của R2.

Ví dụ:

```text
(Animal -> Cat) <: (Cat -> Animal)
```

Hàm bên trái nhận được Cat vì Cat là Animal và trả về Cat, vốn cũng là Animal. Quy tắc này hữu ích khi DSL hỗ trợ callback, handler, rule function hoặc function value.

## 11. Multiple inheritance và xung đột interface

Một kiểu có thể đáp ứng nhiều hợp đồng:

```text
type SmartDevice implements Connectable, Measurable, Auditable
```

Điều này linh hoạt nhưng có thể tạo xung đột nếu nhiều interface cung cấp phương thức mặc định cùng tên. DSL cần quy định:

- Có cho phép nhiều supertype không?
- Nếu nhiều supertype khai báo cùng phương thức, implementation nào được chọn?
- Có bắt buộc kiểu con override để giải quyết xung đột không?
- Có method resolution order không?
- Một kiểu có thể thỏa nhiều protocol structural cùng lúc không?

**Diamond problem** xuất hiện khi một kiểu kế thừa qua nhiều nhánh cùng dẫn tới một ancestor:

```text
        Entity
       /      \
   Auditable  Versioned
       \      /
     Document
```

Nếu các nhánh cung cấp implementation mặc định khác nhau, Document có thể gặp xung đột. Ngôn ngữ cần quy tắc chọn implementation hoặc yêu cầu override tường minh.

## 12. Union type, intersection type và type narrowing

### Union type – kiểu hợp

Union `A | B` biểu diễn giá trị thuộc A hoặc B:

```text
type PaymentResult = Success | Declined | Pending
```

Khi xử lý, DSL có thể yêu cầu pattern matching để phân biệt trường hợp.

### Intersection type – kiểu giao

Intersection `A & B` biểu diễn giá trị đồng thời thỏa cả hai kiểu:

```text
type ManagedResource = Resource & Auditable
```

Một giá trị ManagedResource phải đáp ứng cả hợp đồng Resource và Auditable.

### Top và bottom type

- **Top type:** kiểu tổng quát nhất, mọi giá trị có thể được xem là thuộc kiểu này; ví dụ Any hoặc Object trong một số ngôn ngữ với semantics riêng.
- **Bottom type:** kiểu không có giá trị bình thường hoặc subtype của mọi kiểu khác; ví dụ Nothing hoặc Never.

Không nên giả định Any, Object, Null và Never đồng nghĩa giữa các DSL.

**Type narrowing** thu hẹp kiểu có thể có dựa trên một điều kiện:

```text
function estimate(vehicle: Vehicle): Decimal {
    if vehicle is Truck {
        return vehicle.loadCapacity * 1.5
    }
    return vehicle.baseRate()
}
```

Trong nhánh kiểm tra, type checker có thể xem vehicle là Truck và cho phép truy cập loadCapacity. Với union type đóng, pattern matching có thể được kiểm tra tính đầy đủ; nếu thêm trường hợp mới mà chưa xử lý, compiler có thể cảnh báo.

## 13. Mô hình hóa kiểu con và đa hình trong DSL

Một DSL có thể định nghĩa kiểu và hợp đồng bằng cú pháp riêng:

```text
interface DeliveryVehicle {
    function estimateHours(distance: Decimal): Decimal
}

type Bicycle implements DeliveryVehicle {
    override function estimateHours(distance: Decimal): Decimal {
        return distance / 15
    }
}

type Van implements DeliveryVehicle {
    override function estimateHours(distance: Decimal): Decimal {
        return distance / 40
    }
}

type Truck implements DeliveryVehicle {
    override function estimateHours(distance: Decimal): Decimal {
        return distance / 30
    }
}

function deliveryEstimate(
    vehicle: DeliveryVehicle,
    distance: Decimal
): Decimal {
    return vehicle.estimateHours(distance)
}
```

Hàm deliveryEstimate không cần biết object là Bicycle, Van hay Truck. Nó dựa trên hợp đồng DeliveryVehicle và runtime dispatch tới implementation tương ứng.

Khi thêm ElectricVan, chỉ cần triển khai hợp đồng nếu semantics phù hợp. Hàm dùng chung vẫn hoạt động mà không cần thêm nhánh kiểm tra từng kiểu.

Người thiết kế DSL cần xác định rõ:

- interface tạo kiểu trừu tượng hay hợp đồng.
- implements xác lập quan hệ nominal hay structural.
- override có bắt buộc không.
- Kiểu tham số và kết quả của override phải tương thích thế nào.
- Lời gọi phương thức dùng static hay dynamic dispatch.
- Cách tạo instance và lưu dynamic type.
- Cách giải quyết xung đột khi có nhiều supertype.

Nếu DSL không có object-oriented runtime, đa hình vẫn có thể được mô hình hóa bằng tagged union, record variant hoặc dispatch table. Điều quan trọng là semantics của việc chọn hành vi phải xác định.

## 14. Những lỗi thiết kế thường gặp

**Nhầm kế thừa với kiểu con hợp lệ.** Chia sẻ mã không tự bảo đảm substitutability.

**Dùng quan hệ has-a như is-a.** Engine là thành phần của Car, không vì vậy mà là subtype của Car.

**Tạo phân cấp quá sâu.** Nhiều tầng kế thừa làm semantics và method resolution khó hiểu; interface hoặc composition có thể phù hợp hơn.

**Vi phạm LSP.** Kiểu con yêu cầu đầu vào chặt hơn, làm suy yếu kết quả hoặc ném lỗi trái hợp đồng.

**Nhầm overriding với overloading.** Overriding thay implementation trong phân cấp; overloading chọn hàm theo chữ ký.

**Cho phép covariance trên container mutable.** Có thể ghi giá trị sai kiểu vào cấu trúc; container đọc/ghi thường invariant.

**Không quy định dispatch.** Cùng một biểu thức có thể có hành vi khó dự đoán nếu không rõ static hay dynamic dispatch.

**Bỏ qua xung đột nhiều interface.** Cần quy tắc ưu tiên hoặc yêu cầu override.

**Dùng type check thủ công ở mọi nơi.** Nhiều nhánh kiểm tra có thể cho thấy hợp đồng chung chưa được mô hình hóa. Pattern matching vẫn hữu ích khi xử lý các trường hợp đóng.

**Cho rằng coercion là subtype.** Chuyển đổi kiểu là cơ chế riêng, không nên trộn với quan hệ kiểu con.

## 15. Nguyên tắc thiết kế hệ kiểu con cho DSL

- Xác định hợp đồng và hành vi chung trước khi tạo phân cấp.
- Tạo supertype khi có hợp đồng thực sự chung, không chỉ vì các kiểu có vài trường giống nhau.
- Giữ kiểu con có thể thay thế kiểu cha theo LSP.
- Dùng interface hoặc protocol cho các khả năng độc lập.
- Chọn nominal hay structural subtyping có chủ đích.
- Công bố quy tắc variance; container mutable thường cần invariant.
- Quy định dispatch, overload resolution và xung đột nhiều interface.
- Hỗ trợ diagnostics nêu kiểu mong đợi, kiểu nhận được và quan hệ kiểu con còn thiếu.
- Cân nhắc sealed hierarchy hoặc union type nếu tập trường hợp đóng; hierarchy mở phù hợp hơn khi cần plugin mở rộng.

## 16. Quy trình phân tích kiểu con và đa hình

1. Liệt kê các kiểu miền và hành vi chung.
2. Xác định quan hệ is-a thực sự giữa các kiểu.
3. Tạo supertype hoặc protocol cho hợp đồng chung.
4. Chọn nominal hay structural subtyping.
5. Kiểm tra substitutability theo LSP.
6. Xác định thao tác nào cần subtype polymorphism.
7. Quy định static type, dynamic type và dispatch.
8. Phân biệt overriding, overloading, parametric polymorphism và coercion.
9. Xác định variance cho generic type và function type.
10. Kiểm tra an toàn của collection mutable và trạng thái.
11. Quy định multiple inheritance, interface conflict và type narrowing.
12. Viết ví dụ hợp lệ, ví dụ vi phạm LSP và ví dụ lỗi type checking.
13. Tài liệu hóa quan hệ kiểu và thông báo lỗi.

## 17. Câu hỏi tự kiểm tra

1. Subtyping là gì? Ký hiệu `S <: T` có ý nghĩa gì?
2. Phân biệt supertype, subtype và class inheritance.
3. Nominal subtyping khác structural subtyping như thế nào?
4. Substitutability và Liskov Substitution Principle có vai trò gì?
5. Vì sao kiểu con không nên yêu cầu precondition mạnh hơn kiểu cha?
6. Subtype polymorphism khác parametric polymorphism và ad hoc polymorphism ra sao?
7. Static type khác dynamic type như thế nào?
8. Dynamic dispatch khác static dispatch và method overloading ra sao?
9. Covariance, contravariance và invariance khác nhau thế nào?
10. Vì sao mutable collection thường invariant?
11. Function type có variance như thế nào ở tham số và kiểu trả về?
12. Union type và intersection type biểu diễn những tập giá trị nào?
13. Type narrowing giúp ích gì khi xử lý union hoặc supertype?
14. DSL cần quy định những gì khi một kiểu triển khai nhiều interface?
15. Hãy thiết kế hệ kiểu phương tiện gồm Vehicle, Car và Truck, sau đó viết hàm nhận Vehicle và giải thích cách dispatch.

Khi nắm được kiểu con và đa hình, người học có thể thiết kế hệ kiểu biểu đạt quan hệ giữa các khái niệm miền, tái sử dụng logic qua hợp đồng chung và kiểm soát cách các kiểu cụ thể thay thế hoặc mở rộng kiểu tổng quát trong DSL.
