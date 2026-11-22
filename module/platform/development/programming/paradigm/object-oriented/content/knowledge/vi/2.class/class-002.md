# Khai báo lớp và tạo thể hiện trong Java

Trong lập trình hướng đối tượng (OOP), **lớp** (*class*) mô tả dữ liệu và hành vi chung của một nhóm đối tượng. **Thể hiện** (*instance*, hay đối tượng) là một đối tượng cụ thể được tạo theo định nghĩa của lớp đó.

Ví dụ, lớp `Workshop` có thể mô tả một buổi học gồm tên, sức chứa và số người đã đăng ký. Từ cùng một lớp, chương trình tạo hai thể hiện độc lập: một buổi “Java cơ bản” có hai chỗ và một buổi “Spring Boot” có một chỗ.

## 1. Khai báo một lớp

Cú pháp cơ bản:

~~~java
class TenLop {
    // Các trường (fields): lưu trạng thái
    // Constructor: thiết lập trạng thái khi tạo đối tượng
    // Các phương thức (methods): mô tả hành vi
}
~~~

Một lớp Java thường có ba thành phần:

| Thành phần | Vai trò | Ví dụ trong `Workshop` |
| --- | --- | --- |
| Trường (*field*) | Lưu dữ liệu thuộc từng đối tượng | `name`, `capacity`, `registeredCount` |
| Constructor | Kiểm tra và khởi tạo đối tượng | `Workshop(String name, int capacity)` |
| Phương thức (*method*) | Cho phép đối tượng thực hiện hành vi | `register()`, `remainingSeats()` |

Từ khóa `class` định nghĩa kiểu đối tượng mới. Tên lớp theo quy ước Java viết kiểu `PascalCase` (`Workshop`, `OrderItem`). Từ khóa `public` quy định phạm vi truy cập; một file nguồn thường chứa một lớp top-level `public`, và tên file phải trùng tên lớp đó (chẳng hạn `Main.java` cho `public class Main`).

**Khai báo lớp chưa tạo ra các thể hiện của lớp.** Các thể hiện chỉ xuất hiện khi chương trình thực hiện thao tác tạo đối tượng, điển hình là dùng `new`.

## 2. Tạo thể hiện bằng `new`

Một biểu thức điển hình:

~~~java
Workshop java = new Workshop("Java cơ bản", 2);
~~~

Đọc từ trái sang phải:

1. `Workshop` là **kiểu của biến**.
2. `java` là **biến tham chiếu** dùng để truy cập đối tượng.
3. `new Workshop(...)` tạo một thể hiện của `Workshop` và gọi constructor phù hợp.
4. `"Java cơ bản"` và `2` là các đối số để khởi tạo tên và sức chứa.
5. Toán tử gán `=` lưu **tham chiếu đến đối tượng** vào biến `java`.

Ta có thể khai báo tham chiếu rồi mới tạo đối tượng:

~~~java
Workshop course;                         // Chưa tham chiếu đến đối tượng nào
course = new Workshop("Java cơ bản", 2); // Bắt đầu trỏ đến thể hiện mới
~~~

Biến cục bộ `course` phải được gán giá trị trước khi sử dụng. Khác với biến cục bộ, một **trường tham chiếu** chưa khởi tạo tường minh có giá trị mặc định là `null`. Việc gọi phương thức thông qua tham chiếu `null` gây `NullPointerException`.

## 3. Ví dụ hoàn chỉnh: đăng ký buổi học

Đặt toàn bộ mã sau trong file **`Main.java`**. Ví dụ dùng Java 11 trở lên, vì có `String.isBlank()`.

~~~java
class Workshop {
    private final String name;
    private final int capacity;
    private int registeredCount;

    // Constructor: cùng tên với lớp, không khai báo kiểu trả về.
    Workshop(String name, int capacity) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("Tên buổi học không hợp lệ");
        }
        if (capacity <= 0) {
            throw new IllegalArgumentException("Sức chứa phải lớn hơn 0");
        }

        this.name = name;
        this.capacity = capacity;
        this.registeredCount = 0;
    }

    // Hành vi thay đổi trạng thái riêng của thể hiện hiện tại.
    boolean register() {
        if (registeredCount >= capacity) {
            return false;
        }
        registeredCount++;
        return true;
    }

    int remainingSeats() {
        return capacity - registeredCount;
    }

    String getName() {
        return name;
    }
}

public class Main {
    public static void main(String[] args) {
        Workshop java = new Workshop("Java cơ bản", 2);
        Workshop spring = new Workshop("Spring Boot", 1);

        System.out.println(java.getName());
        System.out.println(java.register());
        System.out.println(java.register());
        System.out.println(java.register());
        System.out.println(java.remainingSeats());
        System.out.println(spring.remainingSeats());

        Workshop alias = spring; // Thêm tham chiếu, không tạo đối tượng mới
        System.out.println(alias == spring);
        alias.register();
        System.out.println(spring.remainingSeats());

        Workshop separate = new Workshop("Spring Boot", 1);
        System.out.println(separate == spring);
        System.out.println(separate.remainingSeats());
    }
}
~~~

Chạy tại thư mục chứa `Main.java`:

~~~bash
javac Main.java
java Main
~~~

Kết quả:

~~~text
Java cơ bản
true
true
false
0
1
true
0
false
1
~~~

**Diễn giải:** Đối tượng `java` có hai chỗ, nên hai lần `register()` đầu thành công, lần thứ ba thất bại. Đối tượng `spring` vẫn còn một chỗ: trạng thái của `java` không làm thay đổi `spring`. Khi gọi `alias.register()`, số chỗ còn lại của `spring` thành 0 vì hai biến cùng tham chiếu một đối tượng. Sau đó, `new Workshop("Spring Boot", 1)` tạo một thể hiện *khác*, dù đối số giống lần tạo `spring`.

## 4. Constructor làm gì?

Constructor là điểm khởi tạo một thể hiện. Nó **cùng tên với lớp** và **không có kiểu trả về**, kể cả `void`. Trong ví dụ trên, constructor bắt buộc tên không trống và sức chứa dương, rồi gán các trường của thể hiện.

Từ khóa `this` chỉ đối tượng hiện tại. Ở câu lệnh `this.name = name;`, phía trái là trường `name` của đối tượng; phía phải là tham số `name` được truyền vào constructor. Cách viết này tránh nhầm lẫn khi tên trường và tên tham số trùng nhau.

Nếu không khai báo **bất kỳ constructor nào**, trình biên dịch cung cấp một constructor mặc định không tham số, với mức truy cập tương ứng mức truy cập của lớp. Nhưng **khi đã khai báo constructor có tham số**, Java không tự sinh thêm constructor không tham số:

~~~java
class Marker {
    String color;
}

Marker a = new Marker(); // Hợp lệ: constructor mặc định

// Với lớp Workshop ở ví dụ chính:
// new Workshop();        // Lỗi biên dịch: thiếu 2 đối số
~~~

Đoạn minh họa `Marker` là mã ví dụ độc lập, không chèn sau phần mã hoàn chỉnh bên ngoài phương thức `main`. Ta cũng có thể tự viết nhiều constructor khác chữ ký (*constructor overloading*) khi có nhiều cách khởi tạo hợp lệ, nhưng mỗi constructor phải bảo đảm trạng thái ban đầu hợp lệ.

## 5. Phân biệt lớp, thể hiện và tham chiếu

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Lớp | Bản định nghĩa về dữ liệu và hành vi | `class Workshop { ... }` |
| Thể hiện | Một đối tượng được tạo theo lớp | Đối tượng “Java cơ bản” |
| Biến tham chiếu | Biến dùng để truy cập đối tượng | `java`, `spring`, `alias` |
| `new` | Biểu thức tạo đối tượng và gọi constructor | `new Workshop("Spring Boot", 1)` |

Sau các phép gán trong ví dụ, quan hệ tham chiếu có thể hình dung như sau:

~~~mermaid
flowchart LR
    J["java"] --> W1["Workshop #1: Java cơ bản"]
    S["spring"] --> W2["Workshop #2: Spring Boot"]
    A["alias"] --> W2
    D["separate"] --> W3["Workshop #3: Spring Boot"]
~~~

Có ba đối tượng nhưng bốn biến tham chiếu. `spring` và `alias` cùng truy cập đối tượng #2; đối tượng #3 được tạo riêng.

- `Workshop alias = spring;` **không sao chép đối tượng**. Nó sao chép giá trị tham chiếu.
- `new Workshop(...)` thực hiện thêm một lần tạo thể hiện.
- `alias == spring` là `true` vì hai tham chiếu trỏ đến cùng đối tượng.
- `separate == spring` là `false` vì chúng là hai đối tượng khác nhau.
- Với đối tượng, `==` so sánh **đồng nhất tham chiếu**; `equals()` có thể biểu diễn bằng nhau theo nội dung nếu lớp định nghĩa lại nó. `Workshop` ở đây không định nghĩa lại `equals()`.

Không nên hình dung mỗi biến tham chiếu là một bản sao độc lập của đối tượng. Khi nhiều tham chiếu cùng trỏ đến một đối tượng có thể thay đổi, việc chỉnh sửa qua một tham chiếu sẽ được thấy qua các tham chiếu còn lại.

## 6. Phạm vi truy cập và tính đóng gói ngay từ lúc khai báo

Ba trường của `Workshop` được khai báo `private` để mã sử dụng không thể trực tiếp gán `registeredCount = 999` hoặc sửa sức chứa tùy tiện. Muốn đăng ký, chương trình gọi `register()`, nơi kiểm tra còn chỗ trước khi tăng số lượng.

`final` trên `name` và `capacity` buộc mỗi trường được gán một lần trong quá trình khởi tạo và không thể gán lại sau đó. Nó **không** có nghĩa toàn bộ đối tượng bất biến, bởi `registeredCount` vẫn có thể thay đổi.

Trong ví dụ, `Workshop` không có `public` nên chỉ truy cập được trong cùng package. Các phương thức cũng có quyền truy cập mặc định (package-private), đủ để `Main` sử dụng vì cả hai ở cùng file/package. Khi tổ chức dự án thành nhiều package, cần chọn mức truy cập `public` cho API cần sử dụng từ package khác.

## 7. Các lỗi thường gặp

| Tình huống | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `new Workshop()` không biên dịch | Lớp chỉ có constructor nhận hai tham số | Truyền đủ đối số hoặc tự khai báo constructor không tham số nếu phù hợp |
| `Workshop x;` rồi gọi `x.register()` | Biến cục bộ chưa được gán | Khởi tạo bằng `new` hoặc gán tham chiếu hợp lệ trước khi dùng |
| `Workshop x = null;` rồi gọi phương thức | `null` không trỏ đến đối tượng | Kiểm tra luồng khởi tạo, không gọi phương thức qua `null` |
| Nghĩ `Workshop b = a;` sẽ nhân bản dữ liệu | Phép gán chỉ sao chép tham chiếu | Tạo đối tượng mới và sao chép dữ liệu có chủ đích nếu cần |
| Khai báo `public class Workshop` ngay trong `Main.java` | Tên file không khớp tên lớp `public` | Đặt `Workshop` vào `Workshop.java`, hoặc giữ nó không `public` trong `Main.java` |
| Viết `void Workshop(...)` | Đây là phương thức tên `Workshop`, không phải constructor | Bỏ kiểu trả về để khai báo constructor |

## 8. Tự kiểm tra hiểu bài

1. Nếu tạo `Workshop a = new Workshop("A", 3);` và `Workshop b = new Workshop("B", 3);`, gọi `a.register()` có làm thay đổi `b.remainingSeats()` không? **Không**: đó là hai thể hiện độc lập.
2. Nếu tiếp tục viết `Workshop c = a;`, thì `c == a` có giá trị gì? **`true`**, vì cả hai trỏ đến cùng một thể hiện.
3. Muốn bảo đảm không tạo được buổi học với sức chứa bằng 0, kiểm tra ở đâu? **Trong constructor**, để từ đầu mỗi đối tượng được tạo hợp lệ.
4. `new Workshop("A", 3)` tạo lớp mới hay đối tượng mới? **Đối tượng mới** của lớp `Workshop` đã được định nghĩa.
5. Nếu chỉ viết `class Workshop { ... }` mà không thực hiện `new Workshop(...)`, đã có thể hiện `Workshop` nào do dòng khai báo ấy tạo ra chưa? **Chưa**.

**Ghi nhớ khi viết Java:** Khai báo `class` để định nghĩa cấu trúc và hành vi; dùng `new` kèm constructor để tạo đối tượng; giữ tham chiếu để gọi phương thức; mỗi lần tạo thể hiện mới có trạng thái riêng, còn phép gán tham chiếu có thể khiến nhiều biến cùng truy cập một thể hiện.