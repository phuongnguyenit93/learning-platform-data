# Kế thừa mô hình

Trong thiết kế mô hình trừu tượng, **kế thừa mô hình** (*model inheritance*) là cách xây dựng một mô hình mới dựa trên một mô hình đã có. Mô hình mới nhận lại những cấu trúc và quy tắc được định nghĩa ở mô hình cha, sau đó có thể bổ sung hoặc chuyên biệt hóa chúng để biểu diễn một trường hợp cụ thể hơn.

Kế thừa giúp tránh lặp lại các thành phần chung, thể hiện quan hệ tổng quát – chuyên biệt và tạo một hệ thống mô hình có thể mở rộng. Trong bối cảnh DSL (*Domain-Specific Language* – ngôn ngữ chuyên biệt theo miền), kế thừa có thể xuất hiện ở mô hình miền, metamodel, kiểu dữ liệu, khai báo tài nguyên hoặc các cấu trúc mà DSL cho phép mở rộng.

Ví dụ, một mô hình `Vehicle` có thể mô tả những đặc điểm chung của phương tiện như mã định danh, nhãn hiệu và năm sản xuất. Mô hình `Car` kế thừa `Vehicle`, nhận các đặc điểm chung đó rồi bổ sung số cửa và loại nhiên liệu. Mô hình `ElectricCar` có thể tiếp tục chuyên biệt hóa `Car` bằng dung lượng pin và phạm vi di chuyển.

## 1. Mô hình cha và mô hình con

Trong quan hệ kế thừa, mô hình cung cấp cấu trúc chung được gọi là **mô hình cha** (*parent*, *base* hoặc *supermodel*). Mô hình nhận lại cấu trúc đó được gọi là **mô hình con** (*child*, *derived* hoặc *submodel*).

Quan hệ thường được diễn đạt là “mô hình con là một dạng của mô hình cha” (*is-a*). Ví dụ:

```text
Vehicle
   ├── Car
   │    └── ElectricCar
   └── Motorcycle
```

- `Vehicle` mô tả khái niệm phương tiện nói chung.
- `Car` là một loại `Vehicle`.
- `ElectricCar` là một loại `Car`.
- `Motorcycle` cũng là một loại `Vehicle`, nhưng không phải là `Car`.

Nếu `Vehicle` định nghĩa thuộc tính `manufacturer`, các mô hình con có thể sử dụng thuộc tính đó mà không cần khai báo lại. Mỗi mô hình con chỉ bổ sung những đặc điểm riêng của nó.

### 1.1. Kế thừa là quan hệ giữa các định nghĩa

Kế thừa thường được xác định giữa các kiểu hoặc định nghĩa mô hình, không có nghĩa một đối tượng cụ thể được sao chép thành một đối tượng khác. Một đối tượng `ElectricCar` có thể được xem như một `Car` hoặc `Vehicle` theo quan hệ kiểu, trong khi nó vẫn là cùng một đối tượng.

Ví dụ:

```text
vehicle = ElectricCar(
    manufacturer = "Example Motors",
    model = "E1",
    batteryCapacity = 75
)
```

Đối tượng trên có các đặc điểm được khai báo trong `Vehicle`, `Car` và `ElectricCar`. Nó không phải là ba đối tượng riêng biệt chỉ vì mô hình có ba cấp kế thừa.

### 1.2. Kế thừa và chuyên biệt hóa

Mô hình con thường chuyên biệt hóa mô hình cha bằng một hoặc nhiều cách:

- Bổ sung thuộc tính hoặc quan hệ mới.
- Bổ sung ràng buộc chặt hơn phù hợp với trường hợp cụ thể.
- Cung cấp cách triển khai hoặc hành vi cụ thể cho một thao tác đã được khai báo ở mô hình cha.
- Thu hẹp tập giá trị hợp lệ nếu điều đó vẫn giữ được tính thay thế theo hợp đồng của mô hình cha.

Mục tiêu là biểu diễn phần khác biệt mà không phải lặp lại toàn bộ cấu trúc chung.

## 2. Thành phần nào có thể được kế thừa?

Kế thừa không chỉ giới hạn ở thuộc tính. Một hệ thống mô hình có thể quy định nhiều loại thành phần được truyền từ mô hình cha sang mô hình con.

### 2.1. Thuộc tính

Mô hình con nhận các thuộc tính đã được khai báo ở mô hình cha, cùng kiểu dữ liệu và các metadata liên quan.

Ví dụ:

```text
abstract model Person {
    id: Identifier
    fullName: String
    birthDate: Date
}

model Employee extends Person {
    employeeCode: String
    startDate: Date
}
```

`Employee` có `id`, `fullName`, `birthDate` cùng hai thuộc tính riêng `employeeCode` và `startDate`.

### 2.2. Quan hệ và liên kết

Mô hình cha có thể khai báo quan hệ với các mô hình khác. Nếu quy tắc DSL cho phép, mô hình con kế thừa quan hệ đó.

Ví dụ:

```text
model Person {
    address: Address
}

model Employee extends Person {
    department: Department
}
```

`Employee` có quan hệ `address` được nhận từ `Person`, đồng thời có quan hệ riêng với `Department`.

Khi kế thừa quan hệ, cần làm rõ bội số, chiều điều hướng, quyền sở hữu, vòng đời và các ràng buộc liên quan. Không nên chỉ sao chép tên thuộc tính mà bỏ qua ngữ nghĩa của liên kết.

### 2.3. Ràng buộc và bất biến

Mô hình cha có thể quy định những điều kiện mọi mô hình con phải tuân theo. Ví dụ, một `Person` luôn cần mã định danh và tên hợp lệ. Mô hình `Employee` phải giữ các điều kiện đó, ngoài các quy tắc riêng như ngày bắt đầu làm việc không được trước ngày sinh.

```text
abstract model Person {
    id: Identifier required
    fullName: String required

    invariant validName:
        length(fullName) > 0
}

model Employee extends Person {
    startDate: Date required

    invariant adultAtEmployment:
        yearsBetween(birthDate, startDate) >= 18
}
```

Cú pháp trên là ví dụ minh họa. Một DSL cụ thể có thể dùng annotation, biểu thức ràng buộc, ngôn ngữ quy tắc hoặc validator riêng.

Thông thường, ràng buộc bắt buộc của mô hình cha tiếp tục áp dụng cho mô hình con. Nếu mô hình con có thể vô hiệu hóa tùy ý một bất biến quan trọng của mô hình cha, ý nghĩa của quan hệ kế thừa sẽ trở nên không đáng tin cậy.

### 2.4. Hành vi và thao tác

Nếu mô hình có khai báo hành vi hoặc thao tác, mô hình con có thể nhận các thao tác đó. Nó có thể dùng cách triển khai được kế thừa hoặc cung cấp cách triển khai chuyên biệt nếu DSL hỗ trợ ghi đè.

Ví dụ theo phong cách hướng đối tượng:

```java
abstract class Vehicle {
    abstract int rangeInKm();
}

class ElectricCar extends Vehicle {
    private final int batteryKwh;
    private final int kmPerKwh;

    ElectricCar(int batteryKwh, int kmPerKwh) {
        this.batteryKwh = batteryKwh;
        this.kmPerKwh = kmPerKwh;
    }

    @Override
    int rangeInKm() {
        return batteryKwh * kmPerKwh;
    }
}
```

`Vehicle` xác định hợp đồng rằng một phương tiện có thể cung cấp phạm vi di chuyển. `ElectricCar` triển khai thao tác đó dựa trên dung lượng pin và hiệu suất. Đây là ví dụ trong Java để minh họa khái niệm; một DSL mô hình có thể biểu diễn thao tác theo cách khai báo khác.

### 2.5. Metadata và cấu hình

Mô hình cha có thể cung cấp nhãn, mô tả, quyền truy cập, quy tắc lưu trữ hoặc metadata cho công cụ sinh mã. Cần quy định rõ metadata nào được kế thừa, metadata nào được thay thế và metadata nào được kết hợp.

Ví dụ, một mô hình cơ sở có thể khai báo `auditable = true`. Mô hình con có thể nhận cấu hình đó, nhưng không nên tự động thay đổi nó nếu hệ thống yêu cầu mọi đối tượng thuộc miền phải có nhật ký kiểm toán.

## 3. Mô hình trừu tượng và mô hình cụ thể

Một mô hình cha thường biểu diễn khái niệm tổng quát. Nó có thể không đủ thông tin để tạo một đối tượng hoàn chỉnh và chỉ đóng vai trò nền tảng cho các mô hình con.

**Mô hình trừu tượng** (*abstract model*) không được khởi tạo trực tiếp nếu DSL quy định như vậy. Nó định nghĩa thuộc tính, quan hệ, ràng buộc hoặc hành vi chung.

**Mô hình cụ thể** (*concrete model*) có thể được sử dụng để tạo đối tượng hoặc sinh cấu hình thực thi.

Ví dụ:

```text
abstract model PaymentMethod {
    id: Identifier
    owner: Customer
    amount: Money
}

model BankTransfer extends PaymentMethod {
    bankAccount: BankAccount
    bankCode: String
}

model CardPayment extends PaymentMethod {
    cardToken: Secret
    lastFourDigits: String
}
```

`PaymentMethod` xác định phần chung của phương thức thanh toán. `BankTransfer` và `CardPayment` mô tả các trường hợp cụ thể với dữ liệu riêng.

### 3.1. Vì sao dùng mô hình trừu tượng?

- Tránh tạo đối tượng ở mức quá tổng quát, thiếu dữ liệu hoặc hành vi cần thiết.
- Gom các thuộc tính và ràng buộc chung vào một nơi.
- Cho phép các mô hình con được xử lý thông qua một kiểu chung.
- Thể hiện rõ phần nào là hợp đồng chung và phần nào phải do mô hình con cung cấp.

### 3.2. Phương thức hoặc thuộc tính trừu tượng

Một mô hình trừu tượng có thể khai báo thành phần chưa có giá trị hoặc cách triển khai hoàn chỉnh. Mô hình con phải cung cấp phần còn thiếu trước khi trở thành mô hình cụ thể.

Ví dụ:

```text
abstract model Document {
    title: String
    abstract operation render(): Output
}

model PdfDocument extends Document {
    operation render(): Output = renderPdf()
}
```

Nếu `PdfDocument` không triển khai `render`, nó chỉ có thể tiếp tục là mô hình trừu tượng nếu DSL cho phép. Nếu nó được khai báo là cụ thể, validator cần báo lỗi thiếu thành phần bắt buộc.

## 4. Kế thừa đơn và kế thừa nhiều

### 4.1. Kế thừa đơn

Kế thừa đơn (*single inheritance*) cho phép mỗi mô hình có tối đa một mô hình cha trực tiếp.

```text
Vehicle
   └── Car
        └── ElectricCar
```

Ưu điểm:

- Cấu trúc quan hệ đơn giản.
- Thứ tự tra cứu thuộc tính và hành vi dễ xác định.
- Ít xảy ra xung đột giữa các mô hình cha.
- Công cụ kiểm tra và hiển thị cây mô hình dễ triển khai hơn.

Hạn chế là một mô hình có thể cần tái sử dụng đặc điểm từ nhiều khái niệm độc lập. Ví dụ, `AmphibiousVehicle` vừa có đặc điểm của phương tiện đường bộ vừa có đặc điểm của phương tiện đường thủy. Kế thừa đơn có thể buộc người thiết kế tạo thêm các lớp trung gian hoặc chuyển một số quan hệ sang composition.

### 4.2. Kế thừa nhiều

Kế thừa nhiều (*multiple inheritance*) cho phép một mô hình có nhiều mô hình cha trực tiếp.

```text
LandVehicle      WaterVehicle
       \          /
        AmphibiousVehicle
```

`AmphibiousVehicle` có thể nhận các đặc điểm chung từ cả `LandVehicle` và `WaterVehicle`.

Ví dụ DSL giả định:

```text
model AmphibiousVehicle
    extends LandVehicle, WaterVehicle {
    waterDepthLimit: Meter
}
```

Kế thừa nhiều có thể tăng khả năng tái sử dụng, nhưng tạo ra những câu hỏi cần giải quyết:

- Hai mô hình cha có cùng tên thuộc tính hay thao tác không?
- Nếu cùng tên nhưng khác kiểu, mô hình con phải làm gì?
- Nếu cả hai mô hình cha cùng định nghĩa một hành vi, cách triển khai nào được chọn?
- Một mô hình cha chung có bị kế thừa qua nhiều nhánh hay không?
- Thứ tự tra cứu và quy tắc ghi đè được xác định như thế nào?

Nếu DSL hỗ trợ kế thừa nhiều, những quy tắc này phải được đặc tả rõ ràng. Nếu không có nhu cầu thực tế, kế thừa đơn thường dễ hiểu và dễ bảo trì hơn.

## 5. Đồ thị kế thừa và thứ tự xử lý

Các quan hệ kế thừa tạo thành một đồ thị có hướng. Một cạnh `A -> B` có thể được hiểu là `B` kế thừa `A`.

Ví dụ:

```text
           Entity
          /      \
      Person     Organization
          \      /
         Customer
```

Nếu `Customer` kế thừa cả `Person` và `Organization`, mô hình có thể gặp xung đột nếu hai nhánh định nghĩa cùng một thành phần. Đồ thị cũng cần được kiểm tra để tránh chu trình.

### 5.1. Không cho phép chu trình kế thừa

Một mô hình không thể kế thừa chính nó, trực tiếp hoặc gián tiếp.

Ví dụ không hợp lệ:

```text
ModelA extends ModelB
ModelB extends ModelC
ModelC extends ModelA
```

Quan hệ này tạo chu trình, khiến việc xác định mô hình cha, thành phần được kế thừa và thứ tự phân giải trở nên vô hạn hoặc không xác định.

Khi nạp mô hình, công cụ nên phát hiện chu trình bằng thuật toán duyệt đồ thị hoặc sắp xếp topo. Nếu phát hiện, diagnostic cần chỉ ra chuỗi mô hình tham gia chu trình.

### 5.2. Thứ tự xử lý mô hình cha trước mô hình con

Để xây dựng mô hình con, công cụ thường cần xử lý các mô hình cha trước. Một thứ tự topo có thể bảo đảm rằng mọi mô hình cha đã được phân tích và kiểm tra trước khi tổng hợp thành phần kế thừa vào mô hình con.

Ví dụ:

```text
BaseModel -> SharedModel -> ConcreteModel
```

Công cụ có thể:

1. Phân tích `BaseModel`.
2. Kiểm tra và hoàn thiện `SharedModel` dựa trên `BaseModel`.
3. Hoàn thiện `ConcreteModel` dựa trên `SharedModel`.

Với kế thừa nhiều, thứ tự topo cần bảo đảm tất cả cha trực tiếp và gián tiếp được xử lý trước mô hình con.

## 6. Quy tắc ghi đè (overriding)

Mô hình con đôi khi cần cung cấp phiên bản chuyên biệt của một thành phần được kế thừa. Việc thay thế định nghĩa ở mô hình cha được gọi là **ghi đè** (*overriding*).

Ví dụ:

```text
abstract model Report {
    operation format(): String
}

model CsvReport extends Report {
    override operation format(): String = "CSV"
}

model JsonReport extends Report {
    override operation format(): String = "JSON"
}
```

Mỗi mô hình con cung cấp cách định dạng riêng trong khi vẫn tuân theo hợp đồng `format()` của `Report`.

### 6.1. Ghi đè thao tác

Nếu mô hình cha khai báo thao tác có thể ghi đè, mô hình con cần giữ đúng chữ ký và hợp đồng theo quy tắc của DSL. Một số hệ thống yêu cầu kiểu trả về giống hệt; một số cho phép kiểu trả về chuyên biệt hơn (*covariant return type*).

Không nên cho phép mô hình con thay đổi tùy ý số lượng tham số, kiểu tham số hoặc ý nghĩa của thao tác nếu điều đó làm các nơi sử dụng kiểu cha không còn hoạt động.

### 6.2. Ghi đè thuộc tính

Ghi đè thuộc tính phức tạp hơn ghi đè hành vi vì thuộc tính có thể ảnh hưởng đến lưu trữ, kiểu dữ liệu, schema, ràng buộc và công cụ sinh mã.

Ví dụ, mô hình cha khai báo:

```text
abstract model Account {
    balance: Money
}
```

Mô hình con không nên tùy tiện đổi `balance` thành `String` hoặc đổi ý nghĩa từ số dư hiện tại thành hạn mức tín dụng. Nếu cần chuyên biệt hóa, DSL phải định nghĩa rõ kiểu tương thích và cách kết hợp ràng buộc.

Nhiều DSL chọn không cho ghi đè thuộc tính đã khai báo; mô hình con chỉ được bổ sung thuộc tính mới. Đây là cách đơn giản để tránh thay đổi schema khó dự đoán.

### 6.3. Phân biệt ghi đè và che khuất tên

**Ghi đè** thường thay thế hành vi được kế thừa theo một hợp đồng xác định. **Che khuất tên** (*shadowing*) xảy ra khi một khai báo mới cùng tên làm cho khai báo cũ không còn được tra cứu ở một phạm vi.

Hai khái niệm có thể trông giống nhau nhưng ý nghĩa khác nhau. DSL nên quy định rõ khai báo cùng tên ở mô hình con là override hợp lệ, shadowing hay lỗi trùng định nghĩa.

## 7. Xung đột trong kế thừa nhiều

Khi nhiều mô hình cha cung cấp cùng một tên thành phần, mô hình con có thể gặp xung đột.

Ví dụ:

```text
model Camera {
    resolution: Integer
}

model Display {
    resolution: String
}

model SmartDevice extends Camera, Display {
}
```

`SmartDevice` nhận hai định nghĩa `resolution` có kiểu khác nhau. Công cụ không nên tự chọn một kiểu mà không có quy tắc rõ.

Các chiến lược có thể dùng:

- **Từ chối xung đột:** báo lỗi và yêu cầu mô hình con giải quyết.
- **Yêu cầu khai báo lại:** mô hình con cung cấp định nghĩa thống nhất nếu DSL cho phép.
- **Quy tắc ưu tiên cha:** chọn định nghĩa theo thứ tự cha đã khai báo. Cách này dễ gây bất ngờ nếu không được tài liệu hóa rõ.
- **Namespace:** giữ các thành phần trong phạm vi riêng và yêu cầu tham chiếu có tên đầy đủ.
- **Hợp nhất có điều kiện:** chỉ hợp nhất khi kiểu và hợp đồng tương thích theo quy tắc được xác định.

Với DSL hướng đến khả năng dự đoán, từ chối xung đột không rõ ràng thường là lựa chọn an toàn.

### 7.1. Vấn đề kim cương (diamond problem)

Vấn đề kim cương xảy ra khi hai mô hình cha cùng kế thừa một mô hình gốc, rồi một mô hình con kế thừa cả hai nhánh.

```text
          Base
         /    \
      Left    Right
         \    /
         Child
```

Nếu `Base` định nghĩa thuộc tính hoặc hành vi `id`, `Child` nhận `id` một lần hay hai lần? Nếu `Left` và `Right` ghi đè khác nhau, phiên bản nào có hiệu lực?

Các ngôn ngữ và hệ mô hình giải quyết vấn đề này theo nhiều cách: hợp nhất mô hình gốc, quy tắc tuyến tính hóa thứ tự tra cứu, yêu cầu override tường minh hoặc từ chối cấu trúc gây xung đột. Không nên giả định mọi hệ thống đều dùng cùng một chiến lược.

### 7.2. Tuyến tính hóa thứ tự tra cứu

Một số hệ thống tạo một thứ tự tuyến tính từ đồ thị kế thừa để xác định nơi tra cứu thuộc tính và hành vi. Thứ tự này cần nhất quán với quan hệ cha – con và quy tắc của ngôn ngữ.

Nếu DSL dùng thứ tự khai báo cha để giải quyết xung đột, thay đổi thứ tự `extends A, B` thành `extends B, A` có thể làm thay đổi hành vi. Đây là rủi ro cần được nêu rõ trong đặc tả và kiểm thử.

## 8. Kế thừa ràng buộc và bất biến

Ràng buộc là một phần quan trọng của mô hình trừu tượng. Nếu mô hình cha xác định một điều kiện mà mọi đối tượng thuộc kiểu đó phải thỏa mãn, mô hình con thông thường phải tiếp tục bảo đảm điều kiện đó.

Ví dụ:

```text
abstract model Vehicle {
    weight: Kilogram required

    invariant positiveWeight:
        weight > 0
}

model ElectricVehicle extends Vehicle {
    batteryCapacity: KilowattHour required

    invariant positiveBattery:
        batteryCapacity > 0
}
```

Một `ElectricVehicle` phải thỏa cả `positiveWeight` lẫn `positiveBattery`.

### 8.1. Kết hợp ràng buộc

Một quy tắc thường gặp là các bất biến của mô hình cha và mô hình con cùng được áp dụng. Nếu cha có điều kiện `P` và con thêm điều kiện `Q`, đối tượng con cần thỏa:

\[
P \land Q
\]

Điều này làm miền hợp lệ của mô hình con hẹp hơn hoặc bằng miền hợp lệ của mô hình cha.

### 8.2. Tiền điều kiện và hậu điều kiện

Với thao tác có thể ghi đè, cần xem xét hợp đồng:

- **Tiền điều kiện** (*precondition*): điều kiện cần đúng trước khi gọi.
- **Hậu điều kiện** (*postcondition*): điều kiện được bảo đảm sau khi gọi thành công.

Theo nguyên tắc thay thế kiểu, mô hình con không nên yêu cầu tiền điều kiện mạnh hơn khiến lời gọi hợp lệ với kiểu cha lại thất bại ở kiểu con. Mô hình con cũng không nên làm yếu hậu điều kiện mà kiểu cha cam kết.

Ví dụ, nếu `PaymentMethod.pay(amount)` cho phép mọi khoản tiền không âm, mô hình `CardPayment` không nên bất ngờ yêu cầu khoản tiền phải lớn hơn 1.000.000 nếu nơi gọi chỉ biết nó là `PaymentMethod`, trừ khi hợp đồng chung đã quy định giới hạn đó.

### 8.3. Ràng buộc kiểu và miền giá trị

Khi mô hình con chuyên biệt hóa kiểu thuộc tính, cần xác định việc thu hẹp miền giá trị có làm vi phạm khả năng thay thế hay không. Ví dụ, nếu kiểu cha cho phép mọi số nguyên dương, kiểu con chỉ cho phép số nguyên từ 1 đến 10 có thể làm một số thao tác hợp lệ theo kiểu cha trở nên không hợp lệ ở kiểu con.

Với mô hình dữ liệu, thu hẹp ràng buộc đôi khi là chủ ý nghiệp vụ. Nhưng nếu mô hình con được dùng ở nơi mong đợi mô hình cha, hệ thống cần bảo đảm hợp đồng vẫn được giữ.

## 9. Kế thừa mô hình và tính thay thế

Nguyên tắc thay thế Liskov (*Liskov Substitution Principle – LSP*) nói rằng một đối tượng thuộc kiểu con phải có thể được sử dụng ở nơi mong đợi kiểu cha mà không làm sai tính đúng đắn theo hợp đồng của kiểu cha.

Ví dụ, nếu một hàm nhận `Vehicle`, nó nên hoạt động với `Car` hoặc `Motorcycle` mà không cần giả định mọi phương tiện đều có số cửa hoặc pin.

```java
void inspect(Vehicle vehicle) {
    System.out.println(vehicle.manufacturer());
}
```

Hàm `inspect` chỉ sử dụng đặc điểm mà hợp đồng `Vehicle` bảo đảm. Nếu hàm ép kiểu sang `ElectricCar` để truy cập `batteryCapacity`, nó đã phụ thuộc vào loại cụ thể thay vì mô hình cha.

Trong DSL mô hình, LSP có ý nghĩa tương tự: mọi mô hình con cần đáp ứng hợp đồng chung mà mô hình cha công bố. Nếu không, quan hệ kế thừa có thể chỉ là tái sử dụng cú pháp mà không phải quan hệ kiểu đúng nghĩa.

## 10. Kế thừa và composition

Không phải mọi quan hệ tái sử dụng đều nên được mô hình hóa bằng kế thừa. Một lựa chọn khác là **composition** (*kết hợp thành phần*), trong đó một mô hình chứa hoặc tham chiếu đến mô hình khác như một phần của cấu trúc.

Kế thừa biểu diễn quan hệ “là một dạng của” (*is-a*). Composition thường biểu diễn quan hệ “có một” (*has-a*) hoặc “được cấu thành từ”.

Ví dụ:

```text
Car extends Vehicle
```

`Car` là một loại `Vehicle`.

```text
Car contains Engine
```

`Car` có một `Engine`; động cơ không phải là một loại xe.

### 10.1. So sánh

| Tiêu chí | Kế thừa | Composition |
|---|---|---|
| Quan hệ | Is-a | Has-a / part-of |
| Tái sử dụng | Nhận cấu trúc và hợp đồng từ mô hình cha | Kết hợp các thành phần độc lập |
| Phụ thuộc | Mô hình con phụ thuộc vào hợp đồng của cha | Thành phần có thể được thay thế qua giao diện |
| Mở rộng | Thêm cấp hoặc nhánh trong hệ kế thừa | Thêm, thay hoặc kết hợp thành phần |
| Rủi ro | Cây kế thừa sâu, xung đột và thay đổi lan truyền | Quản lý liên kết và vòng đời thành phần |

### 10.2. Khi nào nên dùng composition?

Composition thường phù hợp khi:

- Một mô hình sử dụng khả năng của mô hình khác nhưng không phải là một dạng của nó.
- Các thành phần có thể thay đổi hoặc được tái sử dụng độc lập.
- Muốn tránh cây kế thừa quá sâu.
- Hành vi cần được lắp ghép linh hoạt theo cấu hình.

Ví dụ, thay vì tạo `CarWithDieselEngine`, `CarWithElectricEngine`, `TruckWithDieselEngine` và nhiều lớp con khác, có thể mô hình hóa `Vehicle` chứa một thành phần `Engine`. Loại động cơ có thể được chọn hoặc thay thế theo cấu hình.

## 11. Kế thừa trong metamodel của DSL

Trong kỹ thuật DSL, cần phân biệt **mô hình miền** (*domain model*) với **metamodel**. Mô hình miền mô tả các khái niệm của một ứng dụng hoặc lĩnh vực. Metamodel định nghĩa những loại phần tử, thuộc tính, quan hệ và quy tắc mà mô hình hợp lệ có thể sử dụng.

Kế thừa có thể được dùng ở cả hai cấp:

- Trong mô hình miền, `ElectricCar` kế thừa `Vehicle`.
- Trong metamodel, kiểu phần tử `ElectricCar` kế thừa kiểu `Vehicle`, nhờ đó nhận lại các thuộc tính và quan hệ được định nghĩa trong metamodel.

Ví dụ theo phong cách metamodel:

```text
abstract meta-class NamedElement {
    name: String
}

meta-class Service extends NamedElement {
    replicas: Integer
}

meta-class Database extends NamedElement {
    engine: DatabaseEngine
}
```

`Service` và `Database` cùng kế thừa thuộc tính `name` từ `NamedElement`. Mô hình DSL tạo ra có thể sử dụng các loại phần tử đó.

### 11.1. Kế thừa metaclass và kế thừa đối tượng mô hình

Kế thừa metaclass làm thay đổi tập loại phần tử mà DSL hiểu. Kế thừa đối tượng mô hình là quan hệ giữa các định nghĩa hoặc phần tử cụ thể trong một mô hình.

Hai cấp này có thể cùng tồn tại nhưng không nên nhầm lẫn. Thay đổi metamodel có thể ảnh hưởng đến parser, validator, editor và code generator; thay đổi một mô hình miền có thể chỉ ảnh hưởng đến một dự án hoặc một tập cấu hình.

### 11.2. Ví dụ với hệ sinh thái mô hình hóa

Trong các framework metamodel như EMF/Ecore, một `EClass` có thể khai báo `ESuperTypes` để kế thừa cấu trúc từ lớp khác. Các thuộc tính và tham chiếu kế thừa được đưa vào mô hình kiểu theo quy tắc của framework.

Ví dụ khái niệm:

```text
EClass NamedElement
    EAttribute name : EString

EClass Service
    ESuperType NamedElement
    EAttribute replicas : EInt
```

Đây là mô tả khái quát, không phải cú pháp Ecore đầy đủ. Trong một dự án thực tế, công cụ sinh mã và validator sẽ dựa trên metamodel để tạo hoặc kiểm tra các đối tượng mô hình.

## 12. Quy trình xây dựng mô hình kế thừa

Khi thiết kế hệ thống mô hình, có thể thực hiện theo các bước sau:

1. **Xác định khái niệm tổng quát:** tìm các thuộc tính, quan hệ, quy tắc và hành vi thực sự chung cho nhiều loại.
2. **Xác định quan hệ is-a:** chỉ dùng kế thừa nếu mô hình con thực sự là một dạng hợp lệ của mô hình cha.
3. **Tạo mô hình cha:** gom phần chung vào mô hình cơ sở; đánh dấu trừu tượng nếu không muốn tạo trực tiếp.
4. **Tạo mô hình con:** khai báo mô hình cha và bổ sung phần chuyên biệt.
5. **Định nghĩa quy tắc override:** quy định thành phần nào được ghi đè, kiểu nào tương thích và cách giải quyết tên trùng.
6. **Kết hợp ràng buộc:** bảo đảm mô hình con tiếp tục thỏa bất biến của mô hình cha.
7. **Kiểm tra đồ thị:** phát hiện chu trình, mô hình cha không tồn tại và xung đột kế thừa.
8. **Kiểm thử khả năng thay thế:** dùng mô hình con ở nơi mong đợi mô hình cha để xác nhận hợp đồng.
9. **Tài liệu hóa:** mô tả thành phần được kế thừa, quyền override và hành vi khi có thay đổi phiên bản.

## 13. Ví dụ tổng hợp: mô hình đơn hàng

Giả sử một hệ thống thương mại điện tử có nhiều loại đơn hàng. Các đơn hàng đều có mã, ngày tạo, khách hàng và trạng thái. Một số loại có thêm dữ liệu riêng.

```text
abstract model Order {
    id: OrderId required
    createdAt: DateTime required
    customer: Customer required
    status: OrderStatus required

    invariant hasIdentity:
        id != null
}

model OnlineOrder extends Order {
    shippingAddress: Address required
    deliveryMethod: DeliveryMethod
}

model StorePickupOrder extends Order {
    pickupStore: Store required
    pickupCode: String required
}
```

`Order` giữ các thành phần chung. `OnlineOrder` bổ sung địa chỉ và phương thức giao hàng. `StorePickupOrder` bổ sung cửa hàng nhận và mã lấy hàng.

Một dịch vụ có thể nhận kiểu `Order` để xử lý các thao tác chung:

```java
void recordCreation(Order order) {
    audit(order.id(), order.createdAt(), order.customer());
}
```

Dịch vụ không cần biết đơn hàng được giao tận nơi hay nhận tại cửa hàng. Khi cần xử lý riêng, hệ thống có thể dùng thao tác đa hình, pattern matching hoặc cơ chế phân loại mà DSL hỗ trợ.

Nếu một đơn hàng luôn cần địa chỉ giao hàng, đặt thuộc tính đó ở `Order` sẽ không đúng với `StorePickupOrder`. Kế thừa cho phép đặt phần chung ở cha và phần đặc thù ở từng con mà không buộc mọi loại đơn hàng mang dữ liệu không phù hợp.

## 14. Thay đổi mô hình cha và ảnh hưởng lan truyền

Một thay đổi ở mô hình cha có thể ảnh hưởng đến mọi mô hình con trực tiếp và gián tiếp. Vì vậy, mô hình cha thường trở thành hợp đồng có phạm vi ảnh hưởng rộng.

Ví dụ, thêm thuộc tính bắt buộc `tenantId` vào `Entity` có thể khiến tất cả mô hình con cần cung cấp giá trị. Đổi kiểu một thuộc tính chung có thể ảnh hưởng đến schema, validator, mã sinh ra và dữ liệu đã lưu.

Khi thay đổi mô hình cha, nên xem xét:

- Những mô hình con nào bị ảnh hưởng.
- Thuộc tính mới có bắt buộc hay có giá trị mặc định.
- Ràng buộc mới có loại bỏ dữ liệu trước đây hợp lệ không.
- Override hiện tại có còn tương thích không.
- Code generator và API sinh ra có thay đổi không.
- Dữ liệu đã lưu có cần migration không.

Một hệ thống có thể dùng versioning cho metamodel hoặc mô hình cơ sở để quản lý thay đổi phá vỡ tương thích. Công cụ migration có thể giúp chuyển các mô hình cũ sang cấu trúc mới.

## 15. Những sai lầm thường gặp

**Dùng kế thừa chỉ để tránh vài dòng lặp.** Nếu quan hệ is-a không đúng, composition hoặc một thành phần dùng chung có thể phù hợp hơn.

**Tạo mô hình cha quá tổng quát.** Một base model chứa nhiều thuộc tính không liên quan đến tất cả mô hình con sẽ tạo ra hợp đồng khó hiểu và dữ liệu thừa.

**Cây kế thừa quá sâu.** Nhiều cấp trung gian làm người đọc khó xác định thuộc tính hoặc hành vi đến từ đâu, đồng thời tăng ảnh hưởng lan truyền khi sửa mô hình cha.

**Ghi đè không có hợp đồng.** Nếu mô hình con thay đổi kiểu hoặc ý nghĩa thao tác tùy ý, mã dùng kiểu cha có thể hoạt động sai.

**Không xử lý xung đột kế thừa nhiều.** Hai mô hình cha có thể khai báo cùng tên với kiểu hoặc ý nghĩa khác nhau. Công cụ cần phát hiện và có quy tắc rõ.

**Bỏ qua chu trình kế thừa.** Chu trình làm cho quan hệ cha – con không thể được phân giải hữu hạn và cần được phát hiện khi nạp mô hình.

**Nhầm kế thừa metamodel với kế thừa mô hình miền.** Hai cấp có phạm vi ảnh hưởng và công cụ xử lý khác nhau.

**Không kiểm tra khả năng thay thế.** Một mô hình con phải đáp ứng hợp đồng mà mô hình cha công bố nếu nó được sử dụng thay thế kiểu cha.

## 16. Ghi nhớ

- Kế thừa mô hình cho phép mô hình con nhận cấu trúc và quy tắc từ mô hình cha rồi chuyên biệt hóa.
- Mô hình cha thường chứa thuộc tính, quan hệ, bất biến hoặc hành vi chung; mô hình con bổ sung phần đặc thù.
- Mô hình trừu tượng định nghĩa hợp đồng chung nhưng không nhất thiết được tạo trực tiếp.
- Kế thừa đơn dễ phân giải hơn; kế thừa nhiều cần quy tắc rõ cho xung đột và vấn đề kim cương.
- Ghi đè phải giữ hợp đồng của mô hình cha; không nên nhầm override với shadowing.
- Chu trình kế thừa phải bị từ chối hoặc được xử lý theo một quy tắc rõ ràng; cách phổ biến là cấm chu trình.
- Kế thừa biểu diễn quan hệ is-a; composition phù hợp hơn cho quan hệ has-a hoặc part-of.
- Trong DSL, kế thừa có thể xuất hiện ở mô hình miền và metamodel; hai cấp không nên bị nhầm lẫn.
- Thay đổi mô hình cha có thể ảnh hưởng đến toàn bộ mô hình con, validator, code generator và dữ liệu.

## 17. Câu hỏi tự kiểm tra

1. Kế thừa mô hình là gì và mô hình cha khác mô hình con ở điểm nào?
2. Vì sao quan hệ kế thừa thường được mô tả bằng quan hệ is-a?
3. Những thành phần nào của mô hình cha có thể được kế thừa?
4. Mô hình trừu tượng khác mô hình cụ thể như thế nào?
5. Nêu một ưu điểm và một hạn chế của kế thừa nhiều.
6. Vấn đề kim cương xuất hiện trong cấu trúc nào? Vì sao cần quy tắc phân giải?
7. Phân biệt overriding và shadowing.
8. Vì sao mô hình con cần giữ các bất biến của mô hình cha?
9. Phân biệt kế thừa với composition bằng ví dụ `Car`, `Vehicle` và `Engine`.
10. Kế thừa trong metamodel khác kế thừa giữa các mô hình miền ở điểm nào?
11. Vì sao công cụ DSL cần phát hiện chu trình trong đồ thị kế thừa?
12. Khi thêm thuộc tính bắt buộc vào mô hình cha, những thành phần nào của hệ thống có thể cần cập nhật?
