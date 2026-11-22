# Cú pháp khai báo `abstract class` trong Java

## 1. Ý nghĩa của `abstract class`

`abstract class` (lớp trừu tượng) là lớp được đánh dấu bằng từ khóa `abstract`. Lớp này có thể cung cấp dữ liệu và hành vi dùng chung cho các lớp con, đồng thời có thể khai báo những phương thức mà lớp con phải hoàn thiện.

Hai quy tắc cơ bản:

- **Không thể tạo đối tượng trực tiếp** bằng `new` từ lớp `abstract`. Tuy nhiên, có thể khai báo biến, tham số hoặc kiểu trả về là lớp trừu tượng và dùng chúng để tham chiếu đến đối tượng của lớp con cụ thể.
- **Lớp trừu tượng không bắt buộc có phương thức trừu tượng.** Ngược lại, bất kỳ lớp nào trực tiếp khai báo một phương thức `abstract` đều phải được khai báo `abstract`.

Dùng lớp trừu tượng khi các lớp con chia sẻ trạng thái, constructor hoặc cách xử lý chung nhưng một số hành vi vẫn khác nhau theo từng lớp con.

## 2. Mẫu cú pháp khai báo

Mẫu tổng quát (các phần trong dấu `[ ]` là tùy chọn, không phải mã Java để biên dịch nguyên dạng):

~~~text
[access-modifier] abstract class ClassName
        [extends ParentClass]
        [implements Interface1, Interface2, ...] {
    // fields, constructors, concrete methods, abstract methods...
}
~~~

Ví dụ đơn giản nhất:

~~~java
abstract class Shape {
}
~~~

Ví dụ có phương thức trừu tượng:

~~~java
abstract class Shape {
    abstract double area();
}
~~~

Phần `abstract double area();` **không có thân hàm** và kết thúc bằng dấu chấm phẩy `;`. Phương thức đang có phạm vi package-private. Với API cần được lớp con thuộc package khác triển khai, thường dùng `public` hoặc `protected`.

| Thành phần | Ý nghĩa và quy tắc |
|---|---|
| `abstract` | Từ khóa đánh dấu lớp trừu tượng; đứng trước `class`. |
| `class ClassName` | Tên lớp tuân theo cú pháp đặt tên lớp Java. |
| `public` (tùy chọn) | Lớp top-level có thể khai báo `public` hoặc không ghi modifier (package-private). |
| `extends ParentClass` | Kế thừa tối đa **một** lớp cha. |
| `implements Interface1, ...` | Có thể thực hiện **nhiều** interface, tách bằng dấu phẩy. |
| `{ ... }` | Thân lớp có thể chứa field, constructor, phương thức thường, phương thức trừu tượng và các thành viên hợp lệ khác. |

**Quy tắc về modifier và tệp:** lớp top-level không được khai báo `private` hoặc `protected`; hai modifier này chỉ có thể dùng cho lớp lồng trong khi hợp lệ. Nếu lớp top-level khai báo `public abstract class Shape`, mã phải nằm trong `Shape.java`. Viết `public abstract class` là quy ước thường gặp; `abstract public class` cũng hợp lệ, nhưng ít được dùng.

## 3. Ví dụ hoàn chỉnh chạy với Java 17+

Lớp `Vehicle` khai báo trường dữ liệu, constructor, phương thức đã cài đặt và phương thức trừu tượng. `ElectricCar` triển khai phương thức trừu tượng và trở thành lớp cụ thể.

Lưu toàn bộ mã sau vào **`Demo.java`**:

~~~java
abstract class Vehicle {
    private final String brand;

    protected Vehicle(String brand) {
        this.brand = brand;
    }

    public final String getBrand() {
        return brand;
    }

    public abstract String start();

    public void stop() {
        System.out.println("Xe đã dừng.");
    }
}

final class ElectricCar extends Vehicle {
    public ElectricCar(String brand) {
        super(brand);
    }

    @Override
    public String start() {
        return getBrand() + " khởi động bằng điện.";
    }
}

public class Demo {
    public static void main(String[] args) {
        Vehicle vehicle = new ElectricCar("VinFast");
        System.out.println(vehicle.start());
        vehicle.stop();
    }
}
~~~

Biên dịch và chạy trong thư mục chứa tệp:

~~~bash
javac Demo.java
java Demo
~~~

Kết quả stdout chính xác:

~~~text
VinFast khởi động bằng điện.
Xe đã dừng.
~~~

Giải thích:

1. `abstract class Vehicle` là lớp cha trừu tượng, **vẫn có thể** có field `brand` và phương thức đã cài đặt `stop()`.
2. `protected Vehicle(String brand)` là constructor hợp lệ. Lệnh `super(brand)` từ constructor `ElectricCar` gọi constructor lớp cha và khởi tạo trạng thái chung.
3. `public abstract String start();` khai báo phương thức instance chưa có thân. Lớp con cụ thể `ElectricCar` ghi đè phương thức này bằng triển khai hoàn chỉnh.
4. `@Override` giúp trình biên dịch kiểm tra việc ghi đè. Phương thức `getBrand()` được khai báo `final`, nên các lớp con không được ghi đè chính phương thức đó.
5. `final class ElectricCar` vẫn hợp lệ: modifier `final` áp dụng cho **lớp con cụ thể**, không áp dụng chung với `abstract` trên cùng một lớp.
6. Biến `Vehicle vehicle` dùng kiểu tham chiếu trừu tượng nhưng giữ đối tượng `ElectricCar`. Lời gọi `vehicle.start()` chạy phiên bản của `ElectricCar`, thể hiện đa hình.

Thử thay `new ElectricCar("VinFast")` bằng `new Vehicle("VinFast")` sẽ gây lỗi biên dịch, vì không thể khởi tạo lớp trừu tượng trực tiếp.

## 4. Cú pháp phương thức `abstract`

Trong lớp trừu tượng, có thể khai báo các phương thức instance `abstract`:

~~~java
abstract class Task {
    protected abstract void execute();

    public abstract int priority();

    public void printStatus() {
        System.out.println("Ready");
    }
}
~~~

`execute()` và `priority()` chỉ có chữ ký và dấu `;`, trong khi `printStatus()` có thân bình thường. Chú ý các ràng buộc:

- Phương thức `abstract` **không có dấu ngoặc nhọn thân hàm**. Muốn có thân, bỏ từ khóa `abstract` khỏi phương thức.
- Phương thức `abstract` không thể kết hợp với `private`, `static` hoặc `final`: `private` không cho phép ghi đè, `static` không phải phương thức instance được override, và `final` cấm ghi đè. `abstract` cũng không kết hợp với modifier `native` hoặc `synchronized` trên cùng phương thức.
- Khi override, phương thức triển khai không được thu hẹp quyền truy cập. Ví dụ, một phương thức `protected abstract` ở lớp cha có thể được lớp con override thành `protected` hoặc `public`.
- Nếu lớp con không khai báo `abstract`, nó phải hiện thực tất cả phương thức trừu tượng còn thiếu trong chuỗi kế thừa, trừ các phương thức đã có một triển khai cụ thể kế thừa phù hợp.
- Lớp `abstract` có thể chứa phương thức thường, phương thức `static` có thân và phương thức `final` có thân; chỉ riêng **một phương thức** không thể vừa `abstract` vừa `static` hoặc `final`.

## 5. Cú pháp và nghĩa vụ của lớp con

Khai báo `abstract class` cho phép một lớp giữ lại những phương thức trừu tượng được kế thừa trong khi lớp trung gian tiếp tục định nghĩa trạng thái hoặc hành vi dùng chung. Lớp chỉ được bỏ `abstract` khi mọi nghĩa vụ còn thiếu đã có triển khai cụ thể hợp lệ. Phần theo dõi nghĩa vụ qua nhiều tầng được giải thích ở bài về chuỗi kế thừa; ở đây không cần lặp lại một ví dụ kế thừa khác.

## 6. Kết hợp `extends`, `implements` và kiểu generic

`extends` phải nằm **trước** `implements`. Một lớp `abstract` có thể không triển khai hết các phương thức do interface yêu cầu:

~~~java
interface Printable {
    void print();
}

interface Resettable {
    void reset();
}

class Parent {
    void ping() {
        System.out.println("pong");
    }
}

abstract class AbstractPrinter extends Parent
        implements Printable, Resettable {

    @Override
    public void print() {
        System.out.println("print");
    }

    // reset() chưa được triển khai.
}
~~~

`AbstractPrinter` vẫn hợp lệ vì được khai báo `abstract`. Lớp con **cụ thể** phải cài đặt `reset()` nếu không có triển khai phù hợp nào được kế thừa. Lưu ý phương thức cài đặt cho một phương thức `public` trong interface cũng phải khai báo `public`.

Một lớp `abstract` có thể dùng tham số kiểu như lớp Java thông thường:

~~~java
abstract class Repository<T> {
    abstract T findById(long id);
}
~~~

`T` là tham số kiểu; tính chất generic không làm thay đổi cách khai báo `abstract class` hoặc quy tắc phương thức trừu tượng.

## 7. Lỗi cú pháp thường gặp

| Khai báo sai | Vì sao sai | Cách sửa |
|---|---|---|
| `class Shape abstract {}` | Modifier đặt sai vị trí. | `abstract class Shape {}` |
| `abstract class {}` | Thiếu tên lớp. | `abstract class Shape {}` |
| `class Shape { abstract double area(); }` | Lớp trực tiếp khai báo phương thức `abstract` nhưng không phải lớp `abstract`. | Thêm `abstract` vào lớp hoặc cung cấp thân cho phương thức. |
| `abstract class Shape { abstract double area() {} }` | Phương thức `abstract` không được có thân. | Kết thúc khai báo bằng `;` hoặc bỏ `abstract` khỏi phương thức. |
| `private abstract class Shape {}` ở cấp top-level | Lớp top-level không được khai báo `private` hoặc `protected`. | Dùng package-private hoặc `public`. |

Nếu lớp top-level là `public`, tên tệp nguồn phải khớp với tên lớp. Các tổ hợp modifier mâu thuẫn như `abstract final` được phân tích riêng trong bài về modifier; không cần lặp lại toàn bộ ma trận ở bài cú pháp.

## 8. Ghi nhớ và áp dụng

Khi khai báo một lớp cha trừu tượng, hãy xác định phần **dùng chung** (field, constructor, phương thức thường) và phần **mỗi lớp con phải quyết định** (phương thức `abstract`). Sau đó kiểm tra lớp con cụ thể đã triển khai đủ các phương thức còn thiếu.

Mẫu ngắn để ghi nhớ:

~~~java
public abstract class AbstractService {
    protected AbstractService() {
    }

    public abstract void execute();

    public void printStatus() {
        System.out.println("Ready");
    }
}
~~~

Đây là khai báo lớp hợp lệ nếu lưu ở `AbstractService.java`; không có `main()` để chạy riêng. Lớp có constructor, phương thức thường có thân và phương thức trừu tượng kết thúc bằng `;`.

Nếu chỉ muốn quy định hợp đồng cho nhiều kiểu không chung trạng thái hoặc hệ kế thừa, cân nhắc `interface`. Java interface cũng có thể có phương thức `default` và `static` có thân, nên không nên phân biệt hai loại bằng kết luận đơn giản rằng interface “không chứa code”.

**Cốt lõi của cú pháp:** `abstract` đặt trước `class` để khai báo lớp trừu tượng; `abstract` đặt trên phương thức để yêu cầu lớp con hiện thực; phương thức này kết thúc bằng `;`; và `new` chỉ dùng với một lớp cụ thể có thể khởi tạo.
