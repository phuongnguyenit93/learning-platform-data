# OOP dựa trên lớp và OOP dựa trên nguyên mẫu (Class-based vs. Prototype-based OOP)

Khi nghe “lập trình hướng đối tượng”, nhiều người hình dung trước tiên một **lớp (class)** chứa thuộc tính và phương thức, rồi dùng `new` để tạo **đối tượng (object)**. Đó là mô hình **OOP dựa trên lớp (class-based OOP)** rất quen thuộc với người học Java. Tuy nhiên, tổ chức phần mềm theo đối tượng **không bắt buộc phải dựa vào class**: một mô hình khác cho phép đối tượng sử dụng trực tiếp một đối tượng đã tồn tại làm **nguyên mẫu (prototype)** để tìm và tái sử dụng hành vi.

Sự khác biệt này xuất hiện ngay ở câu hỏi: *Khi một đối tượng được yêu cầu thực hiện một phương thức mà bản thân nó không trực tiếp khai báo, chương trình tìm phương thức ấy ở đâu?*

- Với Java, ta nhìn vào **kiểu lớp** của đối tượng và các phương thức được kế thừa/ghi đè theo quan hệ lớp.
- Với mô hình nguyên mẫu trong JavaScript, ta nhìn vào **đối tượng đó** và đi tiếp theo **chuỗi nguyên mẫu (prototype chain)** cho đến khi tìm thấy thuộc tính/phương thức phù hợp.

Cả hai đều có thể biểu diễn trạng thái, hành vi, cộng tác giữa các đối tượng và cung cấp đa hình. Khác biệt nằm ở **cơ chế tổ chức và tái sử dụng hành vi**, chứ không phải mô hình nào “hướng đối tượng thật” hơn.

## 1. Hai cách hình thành đối tượng: bản thiết kế và đối tượng làm mẫu

**Mô hình dựa trên lớp** xem class là định nghĩa của một loại đối tượng. Class mô tả dữ liệu mà instance có thể chứa, constructor giúp thiết lập trạng thái ban đầu, và phương thức biểu diễn hành vi. Hai instance của cùng một class có trạng thái riêng, còn các hành vi tuân theo định nghĩa lớp và các lớp cha liên quan.

**Mô hình dựa trên nguyên mẫu** cho phép tạo một đối tượng rồi liên kết đối tượng khác với nó. Khi thuộc tính/phương thức không có trên đối tượng hiện tại, chương trình có thể tìm tiếp ở nguyên mẫu. Nguyên mẫu cũng là một **đối tượng đang tồn tại**, không nhất thiết là một “class” hay bản sao bất biến.

| Câu hỏi | Dựa trên lớp: Java | Dựa trên nguyên mẫu: JavaScript |
| --- | --- | --- |
| Nguồn mô tả hành vi | Class và hệ phân cấp kiểu; interface là hợp đồng hành vi. | Thuộc tính/phương thức ở object hiện tại hoặc các object nằm trong prototype chain. |
| Tạo đối tượng phổ biến | `new SomeClass(...)`; cũng có factory. | Object literal `{}`, `Object.create(proto)`, factory, constructor, cú pháp `class`/`new`. |
| Tái sử dụng hành vi | Method của class, kế thừa `extends`, interface và composition. | Ủy quyền tìm kiếm thuộc tính qua prototype chain; cũng có composition. |
| Thay đổi nơi tìm phương thức | Quan hệ superclass đã được định nghĩa trong kiểu lớp; không thay superclass của một Java object đang chạy. | Có thể thay đổi thuộc tính ở object nguyên mẫu, hoặc cấu hình prototype link của object (nên hạn chế sửa link khi đang chạy). |
| Kiểu dữ liệu | Java kiểm tra phần lớn quan hệ kiểu tại thời điểm biên dịch. | JavaScript có kiểu động; lookup theo object và prototype ở runtime. |
| Đa hình | Dynamic dispatch đối với instance method được override; cũng có đa hình qua interface. | Nhiều object cùng đáp ứng lời gọi nhưng tìm ra hàm khác nhau nhờ thuộc tính và prototype chain. |

**Cảnh báo về cách so sánh:** “dựa trên lớp” không đồng nghĩa với “kiểu tĩnh”, còn “dựa trên nguyên mẫu” không đồng nghĩa với “kiểu động”. Đây là hai trục khái niệm khác nhau. Bảng chọn Java và JavaScript vì chúng là ví dụ tiêu biểu, không phải vì ngôn ngữ kiểu động thì bắt buộc phải dùng prototype.

## 2. OOP dựa trên lớp: đọc cấu trúc Java trước khi chạy chương trình

Giả sử ứng dụng giao hàng có hai hình thức:

- **Tiêu chuẩn**: phí gốc 20.000 đồng, thêm 5.000 đồng mỗi kg.
- **Hỏa tốc**: phí gốc 40.000 đồng, thêm 12.000 đồng mỗi kg.

Chúng cùng nhận đầu vào là cân nặng, cùng phải từ chối cân nặng không hợp lệ, nhưng tính phí khác nhau. Trong Java, ta có thể biểu diễn một **class cha trừu tượng** và các **class con**.

### Ví dụ Java có thể chạy độc lập

Lưu thành `Main.java` và chạy bằng Java 17 trở lên (ví dụ chỉ dùng các tính năng cũng có ở nhiều bản Java cũ hơn):

~~~java
import java.util.List;

// Class cha định nghĩa một loại phương thức giao hàng.
abstract class DeliveryMethod {
    private final String name;
    private final long baseFee;

    protected DeliveryMethod(String name, long baseFee) {
        if (name == null || name.isBlank() || baseFee < 0) {
            throw new IllegalArgumentException("Invalid delivery method");
        }
        this.name = name;
        this.baseFee = baseFee;
    }

    public final String name() {
        return name;
    }

    // Template method: phần quy tắc chung không để lớp con bỏ qua.
    public final long quote(int kilograms) {
        if (kilograms <= 0) {
            throw new IllegalArgumentException("Weight must be positive");
        }
        return Math.addExact(baseFee, variableFee(kilograms));
    }

    protected abstract long variableFee(int kilograms);
}

final class StandardDelivery extends DeliveryMethod {
    StandardDelivery() {
        super("Standard", 20_000);
    }

    @Override
    protected long variableFee(int kilograms) {
        return Math.multiplyExact(5_000L, kilograms);
    }
}

final class ExpressDelivery extends DeliveryMethod {
    ExpressDelivery() {
        super("Express", 40_000);
    }

    @Override
    protected long variableFee(int kilograms) {
        return Math.multiplyExact(12_000L, kilograms);
    }
}

public class Main {
    public static void main(String[] args) {
        List<DeliveryMethod> methods = List.of(
            new StandardDelivery(),
            new ExpressDelivery()
        );

        for (DeliveryMethod method : methods) {
            System.out.println(method.name() + ": " + method.quote(2));
        }

        try {
            methods.get(0).quote(0);
        } catch (IllegalArgumentException ex) {
            System.out.println("Rejected invalid weight");
        }
    }
}
~~~

Chạy:

~~~bash
javac Main.java
java Main
~~~

Kết quả:

~~~text
Standard: 30000
Express: 64000
Rejected invalid weight
~~~

### Đối tượng được tạo ra và method được chọn ra sao?

Với câu lệnh `DeliveryMethod method = new ExpressDelivery();`:

1. **`ExpressDelivery` là một class** được định nghĩa với quan hệ `extends DeliveryMethod`.
2. **`new ExpressDelivery()` tạo instance** thuộc lớp `ExpressDelivery`. Instance có những trạng thái riêng, gồm `name = "Express"` và `baseFee = 40000` do constructor lớp cha thiết lập.
3. Biến `method` có **kiểu khai báo** `DeliveryMethod`, còn đối tượng thực tế có **kiểu runtime** `ExpressDelivery`.
4. Khi gọi `method.quote(2)`, Java sử dụng method `quote()` chung ở lớp cha; method này kiểm tra cân nặng.
5. Lời gọi `variableFee(2)` trong `quote()` được **dynamic dispatch** tới phần ghi đè của `ExpressDelivery`: `12000 × 2 = 24000`.
6. Phí cuối cùng là `40000 + 24000 = 64000`.

Với `StandardDelivery`, phần logic chung không thay đổi; Java chọn phần ghi đè tương ứng và trả `20000 + 5000 × 2 = 30000`.

~~~mermaid
classDiagram
    class DeliveryMethod {
      -String name
      -long baseFee
      +name() String
      +quote(int kilograms) long
      #variableFee(int kilograms) long
    }
    class StandardDelivery {
      #variableFee(int kilograms) long
    }
    class ExpressDelivery {
      #variableFee(int kilograms) long
    }
    DeliveryMethod <|-- StandardDelivery
    DeliveryMethod <|-- ExpressDelivery
~~~

Trong sơ đồ, mũi tên hướng về `DeliveryMethod` biểu diễn **kế thừa lớp**. Chúng ta định nghĩa quan hệ giữa các lớp **trong mã nguồn**. Một instance Java có thể đổi các giá trị được thiết kế là mutable, nhưng không thể tự chuyển sang kế thừa một superclass khác khi đang chạy.

Ví dụ này chỉ là *một cách* thiết kế class-based OOP. Hoàn toàn có thể dùng `interface DeliveryMethod` rồi cài đặt riêng hai class; hoặc dùng composition với một đối tượng tính phí. Class-based OOP không bắt buộc phải xây dựng cây kế thừa nhiều tầng.

## 3. OOP dựa trên nguyên mẫu: hành vi được tìm qua đối tượng khác

JavaScript giúp ta quan sát trực tiếp cơ chế nguyên mẫu bằng `Object.create(proto)`. Lệnh này **tạo một đối tượng mới và đặt prototype của nó trỏ tới `proto`**; nó **không sao chép toàn bộ thuộc tính/phương thức của `proto` thành thuộc tính riêng**.

Dùng lại bài toán giao hàng để so sánh với ví dụ Java.

### Ví dụ JavaScript: tạo object từ một prototype đã tồn tại

Lưu thành `delivery.js`, chạy với Node.js hiện đại:

~~~javascript
"use strict";

// Một object chứa hành vi được chia sẻ.
const deliveryBehavior = {
  quote(kilograms) {
    if (!Number.isInteger(kilograms) || kilograms <= 0) {
      throw new Error("Weight must be a positive integer");
    }
    return this.baseFee + this.feePerKg * kilograms;
  }
};

// Standard có các thuộc tính riêng và ủy quyền tìm method cho deliveryBehavior.
const standard = Object.create(deliveryBehavior);
standard.name = "Standard";
standard.baseFee = 20_000;
standard.feePerKg = 5_000;

// Express dùng chính standard làm prototype, nhưng đặt lại giá trị riêng.
const express = Object.create(standard);
express.name = "Express";
express.baseFee = 40_000;
express.feePerKg = 12_000;

console.log(standard.quote(2));  // 30000
console.log(express.quote(2));   // 64000

console.log(Object.hasOwn(express, "quote")); // false
console.log(Object.hasOwn(express, "baseFee")); // true
console.log(Object.getPrototypeOf(express) === standard); // true
console.log(Object.getPrototypeOf(standard) === deliveryBehavior); // true

// Economy nhận name và baseFee riêng nhưng kế thừa feePerKg từ standard.
const economy = Object.create(standard);
economy.name = "Economy";
economy.baseFee = 15_000;

console.log(economy.quote(2)); // 25000

// Sửa thuộc tính trên prototype mà economy đang thừa hưởng.
standard.feePerKg = 6_000;

console.log(economy.quote(2));  // 27000
console.log(express.quote(2));  // 64000: express có feePerKg riêng

// Input không hợp lệ vẫn được từ chối bởi cùng method dùng chung.
try {
  economy.quote(0);
} catch (error) {
  console.log("Rejected invalid weight");
}
~~~

Kết quả:

~~~text
30000
64000
false
true
true
true
25000
27000
64000
Rejected invalid weight
~~~

Mấu chốt ở đây là đối tượng `express` **không có thuộc tính riêng `quote`**. Nhưng `express.quote(2)` vẫn chạy được nhờ JavaScript lần lượt kiểm tra các đối tượng trong prototype chain.

~~~mermaid
flowchart TD
    E["express: own name, baseFee, feePerKg"]
    S["standard: own name, baseFee, feePerKg"]
    B["deliveryBehavior: own quote()"]
    O["Object.prototype"]
    N["null: kết thúc chuỗi"]
    E -->|"[[Prototype]]"| S
    S -->|"[[Prototype]]"| B
    B -->|"[[Prototype]]"| O
    O -->|"[[Prototype]]"| N
~~~

Đọc chuỗi từ `express` lên trên:

1. JavaScript tìm thuộc tính `quote` trên chính `express`: **không có**.
2. Nó theo liên kết prototype đến `standard`: **cũng không có `quote` riêng**.
3. Nó đi tiếp đến `deliveryBehavior`: **có `quote`**, nên sử dụng hàm này.
4. Khi gọi dưới dạng `express.quote(2)`, `this` bên trong method là **`express`**. Vì vậy `this.baseFee` lấy `40000` và `this.feePerKg` lấy `12000` từ chính `express`.

Đây là điểm dễ hiểu sai nhất: **method được tìm thấy trên prototype không có nghĩa `this` trỏ về prototype**. Với cú pháp gọi method thông thường `receiver.method()`, `this` phụ thuộc vào đối tượng làm *receiver* của lời gọi (ngoại trừ các quy tắc riêng của arrow function, binding, v.v.).

### Cùng method, nhưng dữ liệu được tra cứu từ object đang nhận lời gọi

| Biểu thức | Tìm `quote` tại | `this` khi thực thi | Phí 2 kg |
| --- | --- | --- | --- |
| `standard.quote(2)` | `deliveryBehavior` | `standard` | 30.000 |
| `express.quote(2)` | `deliveryBehavior` qua `standard` | `express` | 64.000 |
| `economy.quote(2)` lúc đầu | `deliveryBehavior` qua `standard` | `economy` | 25.000 |
| `economy.quote(2)` sau khi sửa `standard.feePerKg` | Vẫn `deliveryBehavior` | `economy` | 27.000 |

`economy` không có `feePerKg` riêng nên đọc giá trị từ `standard`. Khi `standard.feePerKg` thay đổi từ 5.000 thành 6.000, kết quả của `economy` cũng đổi. Còn `express` có thuộc tính `feePerKg` riêng nên giá trị của `standard` bị **che khuất (shadowing)** đối với `express`.

Đây là sự **ủy quyền (delegation)** rất đặc trưng của mô hình prototype-based: đối tượng có thể tìm đến đối tượng khác để lấy hành vi và dữ liệu mà nó chưa sở hữu.

## 4. “Nguyên mẫu” là đối tượng liên kết, không mặc nhiên là bản sao

Từ *prototype* đôi khi được dịch là “vật mẫu”, dễ khiến người học hiểu rằng đối tượng mới nhận một bản sao tất cả dữ liệu của vật mẫu. Với `Object.create(proto)`, điều đó **không đúng**.

Xem ví dụ ngắn:

~~~javascript
const prototypeUser = { role: "viewer" };
const alice = Object.create(prototypeUser);
const bob = Object.create(prototypeUser);

console.log(alice.role); // "viewer": tìm thấy trên prototype

alice.role = "admin";     // Tạo own property trên alice.
console.log(alice.role); // "admin"
console.log(bob.role);   // "viewer"

prototypeUser.role = "editor";
console.log(bob.role);   // "editor": bob đọc từ prototype.
console.log(alice.role); // "admin": own property che khuất prototype.

delete alice.role;       // Xóa own property.
console.log(alice.role); // "editor": lookup lại tiếp tục đi tới prototype.
~~~

Thực chất:

- `Object.create(prototypeUser)` thiết lập **liên kết nguyên mẫu**, không tạo một bản sao sâu của `prototypeUser`.
- Đọc `alice.role` có thể đến giá trị trên nguyên mẫu nếu `alice` không có own property.
- Gán `alice.role = "admin"` trong tình huống thông thường tạo một **thuộc tính riêng**, không sửa `prototypeUser.role`. Các trường hợp getter/setter, descriptor chỉ đọc hoặc proxy có quy tắc riêng.
- `delete alice.role` chỉ xóa thuộc tính riêng (nếu xóa được), không xóa thuộc tính trên prototype.

Nếu mục tiêu là **sao chép dữ liệu thành một object khác**, cần nghĩ đến `Object.assign`, spread syntax hoặc kỹ thuật sao chép thích hợp. Sao chép nông hay sâu là một quyết định khác, tách biệt với việc đặt prototype.

## 5. Trạng thái riêng và nguy cơ chia sẻ trạng thái qua prototype

Dùng chung method là điều thường mong muốn. Nhưng đặt **mảng hoặc object có thể thay đổi** trên prototype có thể khiến nhiều instance vô tình chia sẻ cùng một dữ liệu.

~~~javascript
const userBehavior = {
  tags: [], // Một mảng nằm trên chính prototype.

  addTag(tag) {
    this.tags.push(tag);
  }
};

const alice = Object.create(userBehavior);
const bob = Object.create(userBehavior);

alice.addTag("vip");
console.log(bob.tags); // ["vip"] — ngoài mong đợi!
~~~

Tại sao? `alice` chưa có `tags` riêng, nên `this.tags` tìm thấy **cùng một mảng** trên `userBehavior`. Phương thức `push()` sửa *nội dung mảng được tham chiếu*, không tạo một own property mới trên `alice`.

Cách sửa là **khởi tạo trạng thái mutable riêng cho từng đối tượng**:

~~~javascript
function createUser() {
  const user = Object.create(userBehavior);
  user.tags = []; // Mỗi user có một mảng riêng.
  return user;
}

const user1 = createUser();
const user2 = createUser();

user1.addTag("vip");
console.log(user1.tags); // ["vip"]
console.log(user2.tags); // []
~~~

Bài học thiết kế: khi dùng prototype, hãy phân biệt **hành vi có thể chia sẻ** (method) và **trạng thái cần sở hữu riêng** (mảng, object mutable, dữ liệu nghiệp vụ). Trong class-based OOP, quy tắc tương tự cũng quan trọng khi phân biệt **instance field** với **static field** hoặc đối tượng tham chiếu dùng chung.

## 6. Ghi đè (override) hoạt động như thế nào ở hai mô hình?

Trong Java, lớp con có thể **override instance method** của lớp cha. Việc chọn implementation thực tế khi gọi thông qua kiểu cha là **dynamic method dispatch**. Ví dụ `ExpressDelivery` override `variableFee()` của `DeliveryMethod`. Một đối tượng Java không thể tự gán một function mới vào `object.variableFee` để thay việc cài đặt method theo từng instance theo cú pháp Java thông thường.

Trong JavaScript, object có thể **che khuất (shadow)** phương thức của prototype bằng một **thuộc tính riêng** cùng tên chứa hàm:

~~~javascript
const formatter = {
  format(value) {
    return String(value);
  }
};

const simple = Object.create(formatter);
const upper = Object.create(formatter);

upper.format = function (value) {
  return String(value).toUpperCase();
};

console.log(simple.format("hello")); // "hello"
console.log(upper.format("hello"));  // "HELLO"
console.log(Object.hasOwn(upper, "format")); // true
~~~

Cả `simple` và `upper` đều dùng chung prototype `formatter`, nhưng `upper` có `format` riêng nên chuỗi tìm kiếm **dừng ngay tại `upper`**.

Cách mô tả **“override method”** là hợp lý ở mức hành vi, nhưng về cơ chế của prototype-based OOP, ta đang **đặt một own property che thuộc tính kế thừa**. Điều này khác với quy tắc override của class Java có kiểm tra chữ ký, khả năng truy cập và quan hệ kiểu.

Đặc biệt, trong JavaScript cần chú ý **arrow function không có `this` riêng**. Nếu viết `upper.format = (value) => this...` với mong muốn `this` là `upper`, kết quả có thể sai vì arrow function lấy `this` từ phạm vi từ vựng. Dùng cú pháp method thông thường hoặc function khi cần `this` là receiver.

## 7. JavaScript có `class` thì còn gọi là prototype-based được không?

**Có.** JavaScript hiện đại hỗ trợ cú pháp `class`/`extends`/`new` để khai báo constructor, methods và quan hệ kế thừa rõ ràng hơn. Tuy nhiên, việc tìm instance method vẫn liên quan đến **prototype chain**.

Ví dụ:

~~~javascript
class StandardDelivery {
  constructor() {
    this.baseFee = 20_000;
    this.feePerKg = 5_000;
  }

  quote(kilograms) {
    return this.baseFee + this.feePerKg * kilograms;
  }
}

const standard = new StandardDelivery();

console.log(standard.quote(2)); // 30000
console.log(
  Object.getPrototypeOf(standard) === StandardDelivery.prototype
); // true
console.log(
  Object.hasOwn(standard, "quote")
); // false
console.log(
  Object.hasOwn(StandardDelivery.prototype, "quote")
); // true
~~~

Method `quote` được định nghĩa trong thân class theo cú pháp trên nằm ở **`StandardDelivery.prototype`**, còn `baseFee` và `feePerKg` được tạo trên từng instance trong constructor. Khi `standard.quote(2)` chạy, JavaScript có thể tìm method thông qua prototype.

Có ba tên dễ nhầm:

| Cú pháp/khái niệm | Vai trò |
| --- | --- |
| `Object.getPrototypeOf(standard)` | Trả về đối tượng là **`[[Prototype]]` nội bộ** của instance `standard`. |
| `StandardDelivery.prototype` | Thuộc tính `prototype` trên hàm/class constructor; thường là object trở thành `[[Prototype]]` của instance tạo bởi `new`. |
| `Object.create(proto)` | Tạo object mới với `[[Prototype]]` được chỉ định trực tiếp là `proto`. |

**`[[Prototype]]` và thuộc tính có tên `prototype` không phải một thứ.** Hầu hết object đều có liên kết nguyên mẫu nội bộ (có thể là `null`), còn không phải object nào cũng có own property tên `prototype`. Phương thức `Object.getPrototypeOf()` thường rõ ràng hơn truy cập `__proto__` cũ.

Một điều tinh tế: nói “`class` chỉ là cú pháp đường” giúp nhớ cơ chế prototype cơ bản, nhưng không nên hiểu **mọi tính năng `class` đều thay thế nguyên xi bằng cú pháp constructor cũ**. Class còn có semantics riêng, như yêu cầu gọi bằng `new`, các quy tắc `super`, private fields `#field`, và những đặc điểm khác.

## 8. Sơ đồ nhìn song song để tránh nhầm hai loại quan hệ

### Java: instance có class; các class có quan hệ kế thừa

~~~mermaid
flowchart TD
    J1["standard : StandardDelivery"] -. "instance of" .-> J2["class StandardDelivery"]
    J3["express : ExpressDelivery"] -. "instance of" .-> J4["class ExpressDelivery"]
    J2 -->|"extends"| J5["abstract class DeliveryMethod"]
    J4 -->|"extends"| J5
~~~

Class xác định những method nào khả dụng; phần override có thể được chọn dựa theo runtime class của đối tượng.

### JavaScript: object tra cứu qua prototype chain

~~~mermaid
flowchart TD
    P1["express (object)"] -->|"[[Prototype]]"| P2["standard (object)"]
    P2 -->|"[[Prototype]]"| P3["deliveryBehavior (object)"]
    P3 -->|"[[Prototype]]"| P4["Object.prototype"]
    P4 -->|"[[Prototype]]"| P5["null"]
~~~

Các node `express`, `standard`, `deliveryBehavior` đều là **object cụ thể**. Với `Object.create`, liên kết giữa chúng có thể được chỉ định mà không cần khai báo một class mới.

Hai sơ đồ minh họa **cơ chế nổi bật của mỗi mô hình**, không có nghĩa Java hoàn toàn không biết ủy quyền cho một object khác hay JavaScript không có cú pháp lớp.

## 9. Cả hai có đa hình, nhưng “cách tìm method” khác nhau

Đa hình cho phép chương trình xử lý nhiều đối tượng qua một cách yêu cầu thống nhất.

Trong Java:

~~~java
DeliveryMethod method = new ExpressDelivery();
long fee = method.quote(2);
~~~

Compiler kiểm tra `quote(int)` khả dụng trên kiểu khai báo `DeliveryMethod`. Khi method được override hoặc gọi vào hook override, runtime chọn triển khai phù hợp với object thực tế.

Trong JavaScript:

~~~javascript
function printFee(method, kilograms) {
  console.log(method.quote(kilograms));
}

printFee(standard, 2);
printFee(express, 2);
~~~

Hàm `printFee` chỉ gọi thuộc tính `quote` của object được nhận. Object có thể có method riêng hoặc tìm method qua prototype chain. JavaScript thường gọi cách sử dụng này là **duck typing** ở cấp độ giao tiếp: nếu object cung cấp hành vi mong đợi thì dùng được. Nếu object không có `quote` là callable function, lời gọi sẽ lỗi lúc chạy.

Do đó, **class-based OOP và prototype-based OOP không khác nhau ở chỗ một bên có đa hình còn bên kia không**. Cả hai đều có thể có đa hình; chúng khác nhau về cách biểu diễn, tìm và kiểm tra hành vi.

## 10. Ưu điểm, giới hạn và khi nên chọn cách tư duy nào

| Khía cạnh | Class-based OOP | Prototype-based OOP |
| --- | --- | --- |
| **Nhìn vào mô hình nghiệp vụ** | Class/interface giúp thể hiện loại, hợp đồng, quan hệ kế thừa rõ ràng. | Có thể bắt đầu từ các object cụ thể và hành vi cần chia sẻ, ít yêu cầu định nghĩa loại upfront. |
| **Kiểm tra trước khi chạy** | Với Java, compiler giúp phát hiện nhiều lỗi kiểu và chữ ký method. | Với JavaScript thuần, nhiều lỗi truy cập property/callable được phát hiện khi chạy; TypeScript có thể bổ sung kiểm tra tĩnh. |
| **Linh hoạt từng object** | Hành vi thường được tổ chức ở cấp class, interface hay đối tượng chiến lược. | Mỗi object có thể có own methods/properties và chuỗi nguyên mẫu riêng. |
| **Khả năng dự đoán** | Quan hệ kiểu tương đối tường minh; quá nhiều lớp/extends vẫn có thể gây phức tạp. | Lookup động linh hoạt nhưng có thể bất ngờ khi prototype có thay đổi hoặc chia sẻ trạng thái mutable. |
| **Tái sử dụng** | Kế thừa, composition và interface. | Delegation qua prototype, composition, function/factory. |
| **Bảo trì** | Cây kế thừa sâu dễ tạo phụ thuộc chặt và hành vi ghi đè khó theo dõi. | Chuỗi prototype quá sâu, thay đổi prototype khi chạy hoặc shadowing nhiều tầng dễ gây khó hiểu. |

**Trong dự án Java/Spring Boot**, bạn thường thiết kế type bằng class và interface, rồi quyết định rõ trách nhiệm của từng loại. Không cần ép mọi sự tái sử dụng qua `extends`: composition, strategy, dependency injection và các interface nhỏ thường phù hợp hơn với hệ thống có nhiều thay đổi.

**Trong dự án JavaScript/Node.js**, prototype luôn là phần nền tảng của hệ đối tượng JavaScript, ngay cả khi bạn dùng cú pháp `class`. Bạn có thể dùng object literal/factory cho object nhỏ, hoặc class khi cần định nghĩa cấu trúc, khởi tạo, private fields và hệ phân cấp dễ đọc. Không có quy tắc “JavaScript thì tuyệt đối tránh class” hay “prototype thuần luôn tốt hơn class”.

Một lựa chọn tốt phụ thuộc vào **độ rõ của mô hình, bất biến cần bảo vệ, khả năng thay đổi và kinh nghiệm nhóm**, thay vì chỉ dựa vào tên paradigm.

## 11. Đừng nhầm prototype-based OOP với Prototype Design Pattern

Từ **Prototype** còn xuất hiện trong nhóm *creational design patterns* của GoF. Hai ý tưởng này có liên hệ về từ vựng nhưng **không phải một khái niệm**:

- **Prototype-based OOP** là một *mô hình đối tượng*: một object có thể ủy quyền việc truy tìm thuộc tính/hành vi qua prototype object khác.
- **Prototype Design Pattern** là một *mẫu thiết kế tạo đối tượng*, thường tạo đối tượng mới bằng cách **sao chép một đối tượng có sẵn**, có thể dùng cả trong Java vốn là ngôn ngữ class-based.

Ví dụ Java:

~~~java
final class ReportConfig {
    private final String format;

    ReportConfig(String format) {
        this.format = format;
    }

    ReportConfig copy() {
        return new ReportConfig(this.format);
    }
}
~~~

`copy()` minh họa việc tạo cấu hình mới từ cấu hình cũ. Nó **không làm Java trở thành ngôn ngữ prototype-based**, vì các instance vẫn thuộc lớp `ReportConfig` và không có cơ chế property lookup qua một object nguyên mẫu như `Object.create` trong JavaScript.

Với object chứa collection hoặc tham chiếu mutable, thiết kế copy còn phải quyết định **sao chép nông hay sâu**, điều hoàn toàn riêng với chuỗi nguyên mẫu.

## 12. Tự kiểm tra bằng các tình huống cụ thể

**Tình huống 1.** Hai Java object `new StandardDelivery()` có phải cùng một instance không?

**Trả lời:** Không. Chúng là hai instance riêng của cùng class. Cấu trúc/hành vi theo class có thể giống nhau, nhưng danh tính object khác nhau.

**Tình huống 2.** Sau `const child = Object.create(parent)`, `child` có tự động sở hữu bản sao toàn bộ thuộc tính của `parent` không?

**Trả lời:** Không. `child` liên kết đến `parent` làm nguyên mẫu. Nó có thể *đọc được* thuộc tính ở `parent` thông qua lookup nhưng không vì thế mà sở hữu các thuộc tính ấy.

**Tình huống 3.** Với `const x = Object.create(proto)` và `proto.say = function() { return this.name; }`, khi gọi `x.say()` thì `this` là gì?

**Trả lời:** `this` là `x` trong lời gọi method thông thường. Nơi method được tìm thấy không quyết định receiver.

**Tình huống 4.** Vì sao `economy.quote(2)` đổi từ 25.000 thành 27.000 khi thay `standard.feePerKg`?

**Trả lời:** Vì `economy` không có `feePerKg` riêng, nên tra cứu lên `standard`. Đây là hiệu ứng **đọc giá trị kế thừa qua prototype**.

**Tình huống 5.** Vì sao `express.quote(2)` vẫn là 64.000 trong cùng tình huống?

**Trả lời:** Vì `express` có own property `feePerKg = 12000`, che thuộc tính tương ứng của `standard`.

**Tình huống 6.** JavaScript có cú pháp `class` và `extends`. Vậy JavaScript không còn dựa trên prototype?

**Trả lời:** Sai. Instance methods khai báo theo cú pháp class thường được đặt trên `Constructor.prototype` và lookup vẫn dựa vào prototype chain.

**Tình huống 7.** Mỗi object cần danh sách `tags` riêng. Đặt `tags: []` trên prototype rồi gọi `this.tags.push(...)` có an toàn không?

**Trả lời:** Không. Các object có thể cùng sửa một mảng được kế thừa. Hãy khởi tạo mảng riêng ở mỗi object hoặc dùng một cấu trúc bất biến thích hợp.

**Tình huống 8.** Java dùng Prototype Design Pattern để tạo bản sao cấu hình; điều đó có giống cơ chế `Object.create(proto)` không?

**Trả lời:** Không. Sao chép object là kỹ thuật tạo object, còn `Object.create(proto)` chủ yếu tạo *liên kết nguyên mẫu*, không tự sao chép tất cả thuộc tính.

## 13. Cách tự giải thích lại mà không học thuộc định nghĩa

Bạn có thể dùng cùng một câu hỏi thực tế: “Tại sao hai đối tượng đều gọi được `quote(2)` nhưng kết quả khác nhau?”

Ở **Java**, hãy lần theo: *instance được tạo từ class nào → class có quan hệ kiểu nào → method chung và phần override nào được chọn ở runtime → trạng thái riêng của instance đóng góp gì vào kết quả?*

Ở **JavaScript**, hãy lần theo: *object hiện tại có own property `quote` không → nếu không, đi qua prototype nào → method được tìm thấy ở đâu → receiver `this` là object nào → các giá trị `baseFee` và `feePerKg` được lookup từ đâu?*

Nếu giải thích được đường đi đó và dự đoán đúng kết quả trước/sau khi thay đổi một thuộc tính trên prototype, bạn đã nắm được **sự khác biệt cốt lõi giữa OOP dựa trên lớp và OOP dựa trên nguyên mẫu**.