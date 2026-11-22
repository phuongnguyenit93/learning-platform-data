# Kiến thức tiên quyết và trình tự học đề xuất — Abstract Class & Interface (Java)

## 1. Mục tiêu học tập

Đây là lộ trình để chuẩn bị và học chủ đề `abstract class` và `interface` một cách có thứ tự. Trọng tâm là **học gì trước, học gì sau, vì sao cần kiến thức đó và khi nào đủ vững để chuyển bước**. Người mới chưa cần hiểu sẵn hai khái niệm này.

Sau lộ trình, bạn cần tự giải thích được mối liên hệ giữa kế thừa, ghi đè, đa hình, lớp trừu tượng và giao diện; viết được ví dụ hoạt động trên JDK 17+; và có căn cứ khi chọn dùng một lớp cha, một interface hay kết hợp chúng.

## 2. Kiến thức tiên quyết

| Chủ điểm | Cần biết trước | Cách kiểm tra |
| --- | --- | --- |
| Cú pháp Java và công cụ | Khai báo biến, kiểu dữ liệu, `if`, phương thức, tên tệp trùng tên `public class`, dùng `javac`/`java`. | Tạo, biên dịch, chạy một chương trình `Hello`. |
| Class và object | `class`, `new`, field, method, constructor, `this`; phân biệt định nghĩa kiểu và đối tượng ở runtime. | Viết `Student` có tên, constructor và phương thức đọc tên. |
| Đóng gói | `private`, `protected`, `public`, package-private; trách nhiệm quản lý trạng thái. | Ẩn một field với `private`, cung cấp phương thức truy cập hợp lý. |
| Kế thừa lớp | `extends`, quan hệ “là một” (is-a), `super(...)`, phần thành viên được kế thừa. | Viết `Dog extends Animal`, gọi constructor của `Animal`. |
| Ghi đè phương thức | `@Override`, chữ ký phương thức; phân biệt overriding với overloading. | Ghi đè `sound()` ở `Dog`; giải thích vì sao tạo phương thức `sound(int)` là nạp chồng. |
| Đa hình | `Animal a = new Dog();`; kiểu tham chiếu chi phối API nhìn thấy lúc biên dịch, đối tượng thực quyết định phương thức instance ghi đè được chạy. | Dự đoán kết quả `a.sound()` và chạy để xác nhận. |

**Thứ tự ôn tập tối thiểu:** cú pháp Java → class/object → constructor và đóng gói → kế thừa → override → đa hình. Nếu không giải thích được `Animal a = new Dog();`, nên củng cố phần đó trước khi học abstract class hoặc interface.

**Chưa bắt buộc:** generics, collection nâng cao, stream, reflection, Spring, dependency injection, design pattern. Những kiến thức này hữu ích về sau nhưng không phải điều kiện khởi đầu.

### Ba ý nền tảng cần phân biệt

- **Lớp/kiểu và đối tượng:** `Animal a` là biến tham chiếu kiểu `Animal`; `new Dog()` tạo đối tượng kiểu `Dog`. Một đối tượng có thể được tham chiếu qua các kiểu cha/giao diện mà nó đáp ứng.
- **Override và overload:** override cung cấp triển khai mới cho phương thức instance được kế thừa với chữ ký tương ứng; overload là những phương thức cùng tên nhưng danh sách tham số khác nhau.
- **Trừu tượng hóa và đa hình:** trừu tượng hóa xác định những khả năng cần có, còn đa hình giúp cùng một lời gọi có cách thực hiện khác nhau tùy đối tượng cụ thể. Cần hiểu cả hai, thay vì chỉ thuộc cú pháp `abstract` và `interface`.

## 3. Trình tự học đề xuất

| Giai đoạn | Nội dung | Dấu hiệu có thể chuyển bước |
| --- | --- | --- |
| 0. Công cụ và OOP cơ bản | Chạy Java 17+, class, object, constructor, field, method, đóng gói. | Tự biên dịch một ví dụ nhỏ không cần sao chép lệnh lỗi. |
| 1. Kế thừa và đa hình | `extends`, `super`, `@Override`, kiểu tham chiếu cha, dispatch ở runtime. | Giải thích chính xác phương thức nào được gọi qua `Animal a = new Dog();`. |
| 2. Nhu cầu về hợp đồng | Xác định hành vi chung mà mỗi kiểu cụ thể phải thực hiện khác nhau. | Mô tả được “mọi phương tiện di chuyển, nhưng cách di chuyển tùy phương tiện”. |
| 3. Abstract class | `abstract class`, phương thức abstract, constructor, trạng thái và phương thức có sẵn. | Tạo lớp con cụ thể hiện thực đủ các phương thức abstract. |
| 4. Interface | `interface`, `implements`, một lớp hiện thực nhiều interface, biến và tham số kiểu interface. | Cho hai lớp độc lập cùng đáp ứng một hợp đồng. |
| 5. Kết hợp và lựa chọn | Một lớp `extends` một class và `implements` nhiều interface; so sánh với composition. | Giải thích được vì sao chọn mỗi cơ chế trong một thiết kế cụ thể. |
| 6. Tính năng Java hiện đại | Interface `default`, `static`, `private`; xung đột default; functional interface khi học lambda. | Đọc được code hiện đại mà không nhầm hợp đồng với trạng thái instance. |
| 7. Thực hành tích hợp | Thiết kế ví dụ từ đầu, dự đoán output, sửa lỗi biên dịch, đánh giá thiết kế. | Viết/chạy/giải thích được lời giải của chính mình. |

Đây là **trình tự phụ thuộc kiến thức**, không cần chia thời lượng bằng nhau. Có thể học vài bước trong một buổi nếu đã chắc OOP; khi chưa đạt dấu hiệu ở cột cuối, nên luyện thêm trước khi sang bước tiếp theo.

### Giai đoạn 1–2: Tại sao học đa hình trước?

Bắt đầu bằng hai lớp thông thường `Animal` và `Dog`; cho `Dog` ghi đè `sound()`. Với `Animal a = new Dog();`, lời gọi `a.sound()` sử dụng triển khai ghi đè của `Dog`. Trình biên dịch kiểm tra việc gọi dựa trên kiểu `Animal`; khi chạy, JVM chọn phiên bản phương thức instance phù hợp với đối tượng thực.

Từ đó đặt câu hỏi: nếu mọi phương tiện đều phải có `move()` nhưng không có cách di chuyển chung hợp lý, làm sao khai báo yêu cầu đó mà không viết một thân phương thức giả? Đây là lý do học phương thức abstract.

### Giai đoạn 3: Học abstract class

Một **lớp trừu tượng** phù hợp khi các loại đối tượng thuộc cùng họ có khung chung (trạng thái, constructor, phương thức dùng chung), nhưng vẫn có phần hành vi phải để lớp con quyết định.

Nắm chắc các điểm sau:

1. `abstract class Vehicle` có thể chứa field, constructor, phương thức có thân và phương thức `abstract` không có thân.
2. Không thể khởi tạo trực tiếp bằng `new Vehicle(...)`, nhưng có thể khai báo biến kiểu `Vehicle` tham chiếu một đối tượng lớp con.
3. Constructor lớp trừu tượng được gọi trong quá trình xây dựng đối tượng lớp con; `super(...)` cho phép khởi tạo phần chung.
4. Lớp con **không abstract** phải hiện thực các phương thức abstract được thừa kế mà còn thiếu.
5. `abstract` và `final` không dùng đồng thời cho một class: class final không cho phép kế thừa.

**Mốc đạt:** tự viết `abstract class Shape` với phương thức `abstract double area()` rồi tạo `Rectangle` và `Circle` triển khai diện tích. Giải thích được vì sao `Shape s = new Rectangle(...)` hợp lệ dù `new Shape()` không hợp lệ.

### Giai đoạn 4: Học interface

Một **interface** biểu diễn hợp đồng khả năng của nhiều loại đối tượng. Ví dụ, phương tiện, kiện hàng hay thiết bị đều có thể có mã định danh mà không cần chung một lớp cha nghiệp vụ. `Identifiable` với phương thức `id()` mô tả khả năng đó.

Các quy tắc cần nhớ:

- Class dùng `implements` để hiện thực interface. Một class Java chỉ trực tiếp `extends` tối đa một class, nhưng có thể `implements` nhiều interface. Interface có thể `extends` nhiều interface.
- Phương thức abstract thông thường của interface là `public abstract` ngầm định; lớp hiện thực không được giảm mức truy cập của nó.
- Field khai báo trong interface là `public static final` ngầm định (hằng số), không phải field riêng có thể thay đổi của từng instance.
- Interface không có constructor như class để trực tiếp tạo đối tượng; biến kiểu interface tham chiếu đối tượng của lớp hiện thực.
- Interface có thể có phương thức `default`, `static` (Java 8+) và `private` (Java 9+). Học các dạng này **sau** khi hiểu `implements` và đa hình cơ bản.

**Mốc đạt:** viết `interface Printable { void print(); }`, cho `Invoice` và `Report` cùng hiện thực, rồi truyền mỗi đối tượng vào phương thức nhận tham số `Printable`. Người gọi chỉ cần biết hợp đồng `print()`, không cần biết lớp cụ thể.

### Giai đoạn 5: Kết hợp trong ví dụ Java 17 chạy được

Tạo tệp **`LearningPathDemo.java`** và lưu UTF-8:

```java
interface Identifiable {
    String id();

    default String label() {
        return "ID-" + id();
    }
}

abstract class Vehicle {
    private final String name;

    protected Vehicle(String name) {
        this.name = name;
    }

    public String name() {
        return name;
    }

    public abstract String move();
}

final class Bicycle extends Vehicle implements Identifiable {
    private final String id;

    Bicycle(String name, String id) {
        super(name);
        this.id = id;
    }

    @Override
    public String move() {
        return name() + " đang chạy bằng sức người";
    }

    @Override
    public String id() {
        return id;
    }
}

public class LearningPathDemo {
    public static void main(String[] args) {
        Bicycle bicycle = new Bicycle("Xe đạp", "B01");
        Vehicle vehicle = bicycle;
        Identifiable identifiable = bicycle;

        System.out.println(vehicle.move());
        System.out.println(identifiable.label());
    }
}
```

Biên dịch và chạy tại thư mục chứa tệp:

```bash
javac -encoding UTF-8 LearningPathDemo.java
java LearningPathDemo
```

Output:

```text
Xe đạp đang chạy bằng sức người
ID-B01
```

Giải thích từng vai trò:

- `Vehicle` giữ trạng thái tên và hợp đồng `move()` cho cùng một họ phương tiện. `Bicycle` gọi constructor lớp cha qua `super(name)` và hiện thực `move()`.
- `Identifiable` mô tả khả năng có mã nhận diện, độc lập với họ phương tiện. Phương thức `label()` được triển khai sẵn bằng `default`.
- `Bicycle` đồng thời là một `Vehicle` và một `Identifiable`. Các biến `bicycle`, `vehicle`, `identifiable` đều tham chiếu **cùng một đối tượng**.
- Lời gọi `vehicle.move()` thực thi triển khai của `Bicycle` nhờ ghi đè và đa hình. `identifiable.label()` chạy phương thức mặc định, rồi gọi `id()` trên đối tượng `Bicycle`.
- Ví dụ này cố ý có cả abstract class và interface để luyện tập. Thiết kế thực tế có thể chỉ cần một interface hoặc chỉ cần class thông thường.

Nếu sửa code và có lỗi, đọc thông báo đầu tiên của `javac` trước: những lỗi thường gặp là thiếu `public` khi hiện thực phương thức interface, thiếu `@Override` đúng chữ ký, chưa hiện thực đủ phương thức abstract hoặc sai tên tệp `public class`.

### Giai đoạn 6: Mở rộng theo thứ tự hợp lý

1. **`default` method:** có thân và cung cấp triển khai mặc định cho instance; lớp hiện thực có thể ghi đè.
2. **`static` method:** gắn với interface và gọi qua tên interface, không phải phương thức instance kế thừa theo cách thông thường.
3. **`private` method:** dùng tái sử dụng logic nội bộ giữa các phương thức có thân trong interface; không phải phần hợp đồng công khai.
4. **Xung đột default:** hai interface cung cấp default cùng chữ ký thường buộc lớp hiện thực tự ghi đè để phân giải. Một phương thức instance cụ thể phù hợp từ superclass được ưu tiên hơn default từ interface.
5. **Functional interface và lambda:** một interface có đúng một phương thức trừu tượng phù hợp với lambda; `@FunctionalInterface` giúp kiểm tra ý định đó lúc biên dịch. Đây là kiến thức tiếp nối, chưa cần để hiểu interface cơ bản.
6. **Sau cùng**, tìm hiểu `sealed` class/interface (Java 17), thiết kế các hợp đồng nhỏ và các nguyên lý như SOLID nếu phạm vi bài học yêu cầu.

## 4. Nguyên tắc lựa chọn khi thực hành

| Tình huống | Hướng cân nhắc |
| --- | --- |
| Các lớp cùng một họ có trạng thái, điều kiện hợp lệ và xử lý chung. | `abstract class` có thể cung cấp khung chung và điểm mở rộng. |
| Các đối tượng khác họ cần công khai cùng một khả năng. | `interface` biểu diễn hợp đồng độc lập. |
| Một lớp cần phần dùng chung từ cha, đồng thời đáp ứng nhiều khả năng khác nhau. | `extends` một class và `implements` nhiều interface. |
| Chỉ cần tái sử dụng một chức năng, không có quan hệ is-a thật sự. | Cân nhắc **composition/delegation** thay vì ép kế thừa. |
| Code sử dụng chỉ cần vài thao tác được đảm bảo, không quan tâm lớp hiện thực. | Dùng tham số hoặc biến theo interface khi phù hợp. |

Không có quy tắc tuyệt đối “abstract class luôn tốt hơn” hoặc “interface luôn tốt hơn”. Hãy trả lời: **cái gì là bản chất chung của họ đối tượng, cái gì chỉ là khả năng, và việc nào thật sự cần chia sẻ triển khai/trạng thái?** Việc interface hỗ trợ `default` không biến field interface thành trạng thái riêng của instance.

## 5. Bài tập tăng dần và tiêu chí hoàn thành

**Bài 1 — Ôn đa hình:** Viết `Animal` có `sound()`, hai lớp `Cat` và `Dog` ghi đè. Cho biến `Animal` lần lượt tham chiếu hai đối tượng, dự đoán và kiểm chứng output. Đạt khi giải thích được runtime dispatch.

**Bài 2 — Lớp trừu tượng:** Viết `Shape`, `Rectangle`, `Circle` như trên. Thêm constructor lớp cha và một phương thức có thân dùng chung. Đạt khi giải thích được phần nào dùng chung, phần nào mỗi lớp con phải hiện thực.

**Bài 3 — Giao diện:** Viết `Printable`, `Invoice`, `Report` và hàm `runPrint(Printable item)`. Đạt khi thêm loại tài liệu mới mà không cần sửa phần gọi `runPrint`.

**Bài 4 — Kết hợp:** Thêm `Car extends Vehicle implements Identifiable` vào ví dụ `LearningPathDemo`. Nếu cần biểu diễn khả năng sạc, tạo `Rechargeable` chỉ cho lớp phù hợp. Đạt khi giải thích tại sao không phải mọi `Vehicle` đều `Rechargeable`.

**Bài 5 — Bài toán thiết kế:** Với (a) phương tiện có chung luật kiểm tra vận tốc, (b) hóa đơn và báo cáo cùng có khả năng xuất PDF, (c) một đối tượng cần chức năng ghi log, hãy chọn abstract class, interface hoặc composition và nêu lý do dựa trên miền nghiệp vụ.

## 6. Các nhầm lẫn cần phát hiện sớm

- Gọi interface chỉ là “class không có phương thức có thân”: interface hiện đại có `default`, `static`, `private`; giá trị chính vẫn là hợp đồng kiểu.
- Dùng `extends` cho interface được class hiện thực: class **`implements` interface**; interface `extends` interface.
- Cho rằng abstract class vô dụng vì không thể `new`: lớp con vẫn sử dụng constructor, state và phương thức cụ thể từ nó.
- Viết triển khai interface với mức truy cập mặc định: phương thức công khai của interface phải được hiện thực bằng phương thức `public`.
- Nhầm kiểu tham chiếu với kiểu đối tượng thực: kiểu tham chiếu giới hạn API lúc biên dịch; lời gọi phương thức instance ghi đè phụ thuộc đối tượng thực.
- Cố biến hằng số trong interface thành field riêng của đối tượng: field interface luôn là `public static final`.
- Dùng kế thừa chỉ để tiết kiệm vài dòng code: dễ tạo quan hệ is-a sai; cân nhắc composition.
- Học ngay default conflict, lambda hoặc sealed types trước khi hiểu `implements` và đa hình: dễ bị chi tiết nâng cao che mất nền tảng.

## 7. Tự đánh giá trước khi sang bài tiếp theo

Hãy tự trả lời (và chứng minh bằng code nếu cần):

1. Vì sao một abstract class có constructor nhưng không khởi tạo trực tiếp được?
2. Một lớp concrete phải làm gì khi nhận phương thức abstract chưa được hiện thực?
3. Vì sao một đối tượng `Bicycle` gán được vào biến `Vehicle` và `Identifiable`?
4. `extends` một class khác với `implements` interface ở ý nghĩa nào?
5. Khi nào cần hợp đồng độc lập, khi nào thật sự cần chia sẻ trạng thái của lớp cha?
6. `default` method có thay đổi quy tắc field interface không?
7. Bạn có thể dự đoán đúng output, biên dịch và giải thích ví dụ `LearningPathDemo` không?

Nếu chưa trả lời được, quay lại đúng mắt xích gần nhất trong chuỗi **class/object → kế thừa/đa hình → abstract class → interface → kết hợp**. Nếu trả lời được, bạn đã sẵn sàng học sâu cú pháp, giới hạn kế thừa, xung đột phương thức và thiết kế API bằng abstraction.
