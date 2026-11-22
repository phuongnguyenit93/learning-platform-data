# ClassCastException và giới hạn ép kiểu không hợp lệ trong Java

## 1. Ép kiểu tham chiếu không biến đổi đối tượng

Trong Java, **kiểu tĩnh (static type)** của biểu thức được kiểm tra khi biên dịch; **kiểu thực tế (runtime type)** của đối tượng quyết định phép downcast có thành công và phương thức đa hình nào được gọi.

`ClassCastException` là ngoại lệ runtime xảy ra khi một phép ép kiểu tham chiếu được chấp nhận lúc biên dịch nhưng đối tượng thực tế không tương thích với kiểu đích. Ép kiểu chỉ yêu cầu Java kiểm tra hoặc xem một tham chiếu theo kiểu khác; nó không biến đối tượng `Bicycle` thành `Car` và không gọi constructor để chuyển đổi đối tượng.

| Trường hợp | Ví dụ | Kết quả |
| --- | --- | --- |
| Upcasting lên lớp cha/interface | `Vehicle v = new Car();` | Tự động, an toàn theo quan hệ kiểu |
| Downcasting xuống lớp con | `Car c = (Car) v;` | Tường minh; có thể thất bại khi chạy |
| Hai lớp không liên quan | `Car c = (Car) new Bicycle();` | Lỗi biên dịch nếu hai lớp không có quan hệ kiểu hợp lệ |

Một biến kiểu `Vehicle` có thể trỏ đến `Car` hoặc `Bicycle`. Do đó `(Car) vehicle` có thể thành công nếu đối tượng thật là `Car`, nhưng ném `ClassCastException` nếu đối tượng thật là `Bicycle`.

## 2. Compile-time và runtime kiểm tra điều gì?

1. **Compile-time:** Trình biên dịch xét các kiểu tĩnh và quan hệ giữa chúng. Nếu phép chuyển đổi tham chiếu không hợp lệ theo luật Java, mã bị từ chối ngay; chương trình không chạy và không có ngoại lệ runtime.
2. **Runtime:** Với phép downcast mà compiler cho phép, JVM kiểm tra kiểu thực tế của đối tượng. Nếu đối tượng không phải kiểu đích hoặc một lớp con tương thích, phép cast ném `ClassCastException`.

Ví dụ biên dịch được nhưng ném ngoại lệ khi chạy:

~~~java
Vehicle vehicle = new Bicycle("B-2");
Car car = (Car) vehicle;
~~~

`vehicle` có kiểu tĩnh `Vehicle`, nên compiler biết nó có thể tham chiếu một `Car`. Tuy nhiên, đối tượng được tạo thực sự là `Bicycle`; cast không thể thay đổi điều đó.

Đoạn sau bị lỗi biên dịch khi `Car` và `Bicycle` là hai lớp không liên quan:

~~~java
Car car = (Car) new Bicycle("B-2"); // Compile-time error
~~~

Kiểu tĩnh của biểu thức đã là `Bicycle`, nên compiler biết nó không thể là `Car`. Việc gán đối tượng ấy cho biến kiểu chung `Vehicle` không đổi kiểu thực tế; nó chỉ khiến phép cast sau đó có thể qua kiểm tra kiểu tĩnh, rồi vẫn thất bại khi chạy.

## 3. Ví dụ Java 17+: downcast an toàn bằng instanceof

Lưu mã sau vào **CastSafetyDemo.java**:

~~~java
abstract class Vehicle {
    private final String id;

    protected Vehicle(String id) {
        this.id = id;
    }

    public final String id() {
        return id;
    }

    abstract String kind();
}

final class Car extends Vehicle {
    Car(String id) {
        super(id);
    }

    @Override
    String kind() {
        return "Car";
    }

    String honk() {
        return "beep";
    }
}

final class Bicycle extends Vehicle {
    Bicycle(String id) {
        super(id);
    }

    @Override
    String kind() {
        return "Bicycle";
    }
}

public class CastSafetyDemo {
    public static void main(String[] args) {
        Vehicle first = new Car("C-7");
        System.out.println("Kind: " + first.kind());

        if (first instanceof Car car) {
            System.out.println("Car id: " + car.id());
            System.out.println("Sound: " + car.honk());
        }

        Vehicle second = new Bicycle("B-2");
        System.out.println("Kind: " + second.kind());

        try {
            Car wrong = (Car) second;
            System.out.println(wrong.honk());
        } catch (ClassCastException error) {
            System.out.println("Rejected: Bicycle is not a Car");
        }

        Object value = "hello";
        try {
            Integer number = (Integer) value;
            System.out.println(number);
        } catch (ClassCastException error) {
            System.out.println("Rejected: String is not an Integer");
        }

        Object nothing = null;
        Car absent = (Car) nothing;
        System.out.println("Null cast: " + (absent == null));
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac CastSafetyDemo.java
java CastSafetyDemo
~~~

Đầu ra chính xác:

~~~text
Kind: Car
Car id: C-7
Sound: beep
Kind: Bicycle
Rejected: Bicycle is not a Car
Rejected: String is not an Integer
Null cast: true
~~~

Giải thích:

- `first.kind()` gọi phương thức của `Car` qua đa hình. Không cần downcast để gọi hành vi đã có trong lớp cha.
- `first instanceof Car car` vừa kiểm tra kiểu thực tế vừa tạo biến mẫu `car` trong nhánh đúng. Cú pháp pattern matching cho `instanceof` có từ Java 16, nên dùng được ở Java 17.
- `(Car) second` biên dịch được do kiểu tĩnh là `Vehicle`, nhưng thất bại vì đối tượng thật là `Bicycle`. Dòng gọi `wrong.honk()` không chạy.
- `(Integer) value` thất bại vì đối tượng thực tế là `String`, dù biến có kiểu tĩnh `Object`.
- Ép `null` sang `Car` không gây `ClassCastException`. Kết quả vẫn là `null`; nếu gọi phương thức trên biến đó thì sẽ gây `NullPointerException`.

## 4. Dùng instanceof hoặc đa hình thay cho cast mù

Nếu thật sự cần hành vi riêng của một lớp con, hãy kiểm tra kiểu trước:

~~~java
if (vehicle instanceof Car car) {
    System.out.println(car.honk());
} else {
    System.out.println("Vehicle is not a Car");
}
~~~

Trong Java cũ hơn có thể viết:

~~~java
if (vehicle instanceof Car) {
    Car car = (Car) vehicle;
    System.out.println(car.honk());
}
~~~

`instanceof` trả về `false` khi tham chiếu là `null`. Biến mẫu giúp tránh việc kiểm tra một biến rồi vô tình cast một tham chiếu khác. Không nên dùng `try/catch` như cách dò loại đối tượng thông thường; hãy kiểm tra trước khi sử dụng.

Dù vậy, **không cần downcast nếu hành vi thuộc hợp đồng chung**:

~~~java
Vehicle vehicle = new Car("C-8");
System.out.println(vehicle.kind());
~~~

`kind()` được khai báo trên `Vehicle` nên đa hình xử lý đúng. Chỉ cast khi cần hành vi đặc thù chưa có trên lớp cha/interface. Nếu mã chứa quá nhiều nhánh `instanceof`, cân nhắc chuyển hành vi vào các lớp con hoặc thiết kế lại abstraction.

## 5. Interface, mảng và generic: các trường hợp dễ nhầm

Quy tắc cast cũng áp dụng cho interface. Một phép cast có thể được compiler chấp nhận dựa trên kiểu tĩnh chung, nhưng thất bại vì đối tượng không triển khai interface đích:

~~~java
Object value = "hello";
Runnable task = (Runnable) value; // ClassCastException khi chạy
~~~

`String` không triển khai `Runnable`. Với một kiểu tĩnh cụ thể hơn, compiler có thể từ chối phép cast ngay nếu không tồn tại quan hệ kiểu hợp lệ.

Một số trường hợp cần phân biệt:

- **Primitive cast:** Ép `int` sang `byte` có thể mất dữ liệu nhưng không gây `ClassCastException`. Đây là chuyển đổi số, không phải cast tham chiếu.
- **Mảng:** Mảng Java có covariance. `Object[] values = new String[1]; values[0] = 42;` ném `ArrayStoreException` khi lưu `Integer` vào mảng thực tế là `String[]`; ngoại lệ này khác `ClassCastException`.
- **Generic và type erasure:** Kiểu tham số generic thường không được giữ đầy đủ để kiểm tra ở runtime. Cast sang kiểu generic có thể chỉ kiểm tra kiểu thô, rồi lỗi xảy ra khi lấy phần tử.
- **Unchecked cast:** Compiler có thể cảnh báo rằng nó không thể xác minh kiểu tham số. Cảnh báo không có nghĩa phép cast an toàn.

Ví dụ generic sau là mã minh họa riêng, không nằm trong `CastSafetyDemo`:

~~~java
import java.util.List;

Object value = List.of("text");
@SuppressWarnings("unchecked")
List<Integer> numbers = (List<Integer>) value;
Integer first = numbers.get(0); // ClassCastException khi lấy phần tử
~~~

Phép cast sang `List<Integer>` có thể chỉ kiểm tra rằng đối tượng là `List`. Danh sách thật chứa `String`; khi kết quả `get(0)` được chuyển thành `Integer`, cast mà compiler chèn để đáp ứng kiểu đích sẽ thất bại. Trong mã sản xuất, không dùng `@SuppressWarnings` để che giả định chưa được xác minh; tránh raw type và kiểm tra dữ liệu đầu vào.

## 6. Xử lý ClassCastException có chủ đích

Ưu tiên ngăn cast sai trước khi xảy ra thay vì bắt ngoại lệ để dò kiểu.

- Dùng lớp cha/interface và đa hình nếu hành vi đã thuộc hợp đồng chung.
- Với dữ liệu có kiểu tĩnh quá rộng như `Object`, kiểm tra bằng `instanceof` trước khi gọi hành vi riêng.
- Với API hoặc dữ liệu ngoài hệ thống, xác định rõ các kiểu được phép và từ chối dữ liệu không đáp ứng hợp đồng.
- Chỉ bắt `ClassCastException` khi có lý do nghiệp vụ cụ thể; không nuốt ngoại lệ rồi tiếp tục như thể thao tác thành công.
- Đừng dùng tên lớp hoặc chuỗi hiển thị thay cho kiểm tra kiểu.

Phân biệt **casting** với **conversion**: cast tham chiếu kiểm tra tính tương thích của đối tượng. Chuyển đổi thật sự, chẳng hạn phân tích chuỗi thành số bằng `Integer.parseInt(text)`, dùng API chuyển đổi và có thể ném `NumberFormatException` nếu chuỗi không hợp lệ.

## 7. Checklist và lỗi phổ biến

Trước mỗi phép cast, hãy hỏi:

1. Kiểu tĩnh của biểu thức là gì?
2. Compiler có cho phép phép chuyển đổi không? Nếu không, đó là lỗi biên dịch, không phải ngoại lệ runtime.
3. Kiểu thực tế có thể là kiểu đích không? Nếu chưa chắc, dùng `instanceof` hoặc sửa thiết kế.
4. Có thể gọi phương thức qua lớp cha/interface để bỏ cast không?
5. Với generic/raw type, kiểm tra runtime có thực sự bảo đảm kiểu phần tử không?
6. Khi thất bại, chương trình sẽ từ chối dữ liệu rõ ràng hay âm thầm tiếp tục?

Lỗi thường gặp là nghĩ cast biến đổi đối tượng, giả định mọi tham chiếu lớp cha đều trỏ đến cùng một lớp con, nhầm compile-time error với `ClassCastException`, bỏ qua cảnh báo unchecked cast, hoặc bắt ngoại lệ quá rộng.

**Ghi nhớ:** Upcasting thường tự động và an toàn; downcasting cần căn cứ vào kiểu thực tế. Compiler kiểm tra phép cast theo các kiểu tĩnh, còn JVM kiểm tra đối tượng khi chạy. Dùng đa hình khi có thể và `instanceof` trước khi cần hành vi chuyên biệt.
