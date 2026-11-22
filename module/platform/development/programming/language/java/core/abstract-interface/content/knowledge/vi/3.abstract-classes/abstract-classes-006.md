# Thành viên `static`, `final` và `private` trong lớp trừu tượng (Java 17+)

## 1. Bối cảnh và mục tiêu

Trong Java, `abstract class` là lớp không thể khởi tạo trực tiếp bằng `new`. Lớp này thường giữ trạng thái và hành vi chung, đồng thời có thể khai báo phương thức trừu tượng để lớp con triển khai. **Một lớp trừu tượng vẫn có đầy đủ thành viên thông thường**: thuộc tính, phương thức có thân, constructor, khối khởi tạo và lớp lồng nhau. Ba từ khóa `static`, `final`, `private` vẫn áp dụng theo quy tắc chung của Java, nhưng cách kết hợp của chúng với `abstract` cần hiểu chính xác.

Sau bài này, bạn có thể:
- Xác định thành viên thuộc về lớp hay đối tượng, thành viên nào được phép ghi đè và thành viên nào chỉ dùng nội bộ.
- Giải thích vì sao `static abstract`, `final abstract` và `private abstract` không hợp lệ.
- Thiết kế lớp trừu tượng với trạng thái được đóng gói, các bước xử lý cố định và phần mở rộng cho lớp con.
- Phân biệt **method hiding** ở phương thức `static` với **overriding** ở phương thức instance.

Ví dụ khởi đầu:

~~~java
abstract class Document {
    private final String title;
    private static int created;

    protected Document(String title) {
        this.title = title;
        created++;
    }

    public final String title() {
        return title;
    }

    public static int createdCount() {
        return created;
    }

    public abstract String render();
}
~~~

`Document` chưa định nghĩa `render()` nên là lớp trừu tượng. Tuy vậy, `title`, `created`, constructor, `title()` và `createdCount()` đều hợp lệ. Một lớp con cụ thể phải triển khai `render()` (hoặc vẫn khai báo chính mình là `abstract`).

## 2. Bảng quy tắc nhanh

| Khai báo trong `abstract class` | Hợp lệ? | Ý nghĩa |
| --- | --- | --- |
| `static` field/method | Có | Thành viên gắn với lớp khai báo, không gắn với từng instance. |
| `final` field | Có | Biến chỉ được gán một lần theo quy tắc definite assignment. |
| `final` instance method có thân | Có | Lớp con không thể override phương thức này. |
| `private` field/method có thân | Có | Chỉ truy cập theo phạm vi `private` của Java; không tạo hợp đồng override cho lớp con. |
| `private static final` field | Có | Cách khai báo phổ biến cho hằng số hoặc tham chiếu dùng nội bộ. |
| `private final` method có thân | Có | Hợp lệ nhưng `final` thường thừa vì phương thức `private` vốn không thể override. |
| `abstract` instance method (không có thân) | Có | Lớp con cụ thể phải cung cấp triển khai còn thiếu; các tổ hợp modifier mâu thuẫn được tập trung trong bài về `abstract` và `final`. |

Các cột “Có” và “Không” nói về cú pháp và quy tắc ngôn ngữ; việc **nên** dùng tổ hợp nào còn phụ thuộc thiết kế.

## 3. `static`: thành viên thuộc về lớp trừu tượng

### 3.1. Trường `static` là trạng thái dùng chung

Trường `static` được gắn với lớp khai báo. Nếu `Document` có `private static int created`, mỗi lần constructor của `Document` được gọi thông qua constructor lớp con, biến `created` của `Document` được tăng lên. Các instance của những lớp con khác nhau vẫn dùng chung **một trường `Document.created`**. Trường này không được tạo lại riêng cho từng đối tượng.

Truy cập nên thể hiện rõ lớp sở hữu: `Document.createdCount()` thay vì gọi phương thức `static` qua một tham chiếu đối tượng. Nếu nhiều luồng cùng tăng một biến `static int`, thao tác `++` không tự động an toàn cho đồng thời; có thể cần đồng bộ hoặc `AtomicInteger`, tùy bài toán.

### 3.2. Phương thức `static` không override

Phương thức `static` có thể khai báo trong lớp trừu tượng và được gọi mà không cần tạo instance của chính lớp trừu tượng: `Document.createdCount()`. Phương thức này **không thể mang `abstract`**. Một lớp con có thể khai báo phương thức `static` cùng chữ ký phù hợp để *hide* phương thức của lớp cha; lựa chọn phương thức dựa trên kiểu tại thời điểm biên dịch, không dựa trên kiểu thực của đối tượng.

Không được dùng `@Override` cho phương thức `static`, và phương thức `static` không thể thay thế phương thức instance cùng chữ ký qua kế thừa (hoặc ngược lại).

### 3.3. Lưu ý về khởi tạo

Trường `static` được khởi tạo khi lớp tương ứng được khởi tạo theo quy tắc JVM; constructor của từng instance là chuyện khác. Một trường `static final` có thể nhận giá trị ngay tại khai báo hoặc trong khối khởi tạo `static`, miễn đáp ứng quy tắc gán một lần. Không được mặc định rằng mọi trường `static final` đều là hằng số thời gian biên dịch: `static final int LIMIT = 10` có thể là *constant variable*, còn `static final Object LOCK = new Object()` thì không.

## 4. `final`: kiểm soát gán biến, override và kế thừa

### 4.1. Trường instance `final`

`private final String title` phải được gán đúng quy tắc trước khi constructor hoàn tất; với một *blank final instance field*, đường đi khởi tạo bình thường phải bảo đảm biến được gán đúng một lần. Nhờ vậy lớp con không thể gán lại trường này sau khi khởi tạo.

Tuy nhiên, **`final` khóa tham chiếu, không làm đối tượng được tham chiếu bất biến**:

~~~java
import java.util.ArrayList;
import java.util.List;

abstract class TaggedItem {
    private final List<String> tags = new ArrayList<>();

    public void addTag(String tag) {
        tags.add(tag); // Hợp lệ: thay đổi nội dung List.
    }

    public List<String> tags() {
        return List.copyOf(tags); // Trả về bản sao không sửa được.
    }
}
~~~

`tags = new ArrayList<>()` lần nữa trong một phương thức instance sẽ là lỗi biên dịch, nhưng `tags.add(...)` là hợp lệ. Nếu cần bất biến thực sự, thiết kế phải kiểm soát cả khả năng thay đổi nội dung và khả năng lộ tham chiếu.

### 4.2. Phương thức `final`

Một phương thức instance có thân được đánh dấu `final` không thể bị lớp con override. Đây là công cụ giữ cố định một quy trình chung, ví dụ `execute()` thực hiện kiểm tra đầu vào, ghi log hoặc gọi các bước cho phép mở rộng. Một phương thức `final` vẫn có thể **gọi** phương thức `abstract`: phần khung cố định do lớp cha quyết định; chi tiết biến thiên do lớp con triển khai. Đây là ý tưởng gần với *Template Method*.

Phương thức `abstract` không có thân và cần được lớp con thực hiện, vì vậy `abstract final` không hợp lệ. Phương thức `static final` có thân cũng hợp lệ; `final` trong trường hợp này cấm lớp con hide phương thức `static` cùng chữ ký phù hợp.

### 4.3. `final` trên lớp

`abstract class Base` có thể có lớp con `final class Concrete extends Base`. Lớp con `Concrete` không thể được kế thừa tiếp, nhưng vẫn kế thừa từ `Base` hợp lệ. Ngược lại, **một lớp không thể vừa `abstract` vừa `final`**.

## 5. `private`: đóng gói trong lớp trừu tượng

`private` thường bảo vệ bất biến nội bộ như số lượng đối tượng đã tạo, dữ liệu xác thực hoặc các hàm tiện ích không nên trở thành API cho lớp con.

- **Trường `private`**: lớp con không truy cập trực tiếp bằng tên trường; thay bằng constructor và các phương thức `protected`/`public` thích hợp để duy trì bất biến. Không nên biến trường thành `protected` chỉ để tránh viết API.
- **Phương thức `private` có thân**: dùng nội bộ lớp khai báo, có thể là instance hoặc `static`. Phương thức này không được kế thừa để override; một phương thức cùng tên và tham số ở lớp con là phương thức riêng khác, không phải override.
- **Phương thức `private abstract`**: bất hợp lệ vì lớp con không thể thực hiện một hợp đồng override mà nó không có quyền truy cập.
- **Constructor `private`**: một lớp `abstract` có thể khai báo constructor `private` về mặt cú pháp, nhưng lớp con bình thường ở bên ngoài lớp bao không thể gọi constructor đó. Thông thường dùng constructor `protected` hoặc constructor có quyền truy cập phù hợp để cho phép kế thừa có kiểm soát.

`private` và `final` giải quyết hai câu hỏi khác nhau: “Ai được truy cập?” và “Có được override/gán lại không?”. Ví dụ `private final` field vừa ẩn khỏi mã bên ngoài vừa chỉ được gán theo quy tắc `final`. Với phương thức `private final`, `final` ít mang thêm giá trị vì overriding đã không áp dụng.

## 6. Ví dụ chạy được: kết hợp cả ba từ khóa

Lưu toàn bộ đoạn sau thành **`TaskDemo.java`**. Mã gồm một lớp trừu tượng, một lớp con cụ thể và một lớp chứa `main`; chúng cùng nằm trong một tệp, và chỉ `TaskDemo` là `public`.

~~~java
abstract class Task {
    private static int createdCount = 0;
    private static final String PREFIX = "[task] ";
    private final String name;

    protected Task(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("name must not be blank");
        }
        this.name = name;
        createdCount++;
    }

    public static int totalCreated() {
        return createdCount;
    }

    public final String getName() {
        return name;
    }

    private String displayLabel() {
        return PREFIX + getName();
    }

    public final void execute() {
        System.out.println(displayLabel() + ": " + doWork());
    }

    protected abstract String doWork();
}

final class PrintTask extends Task {
    public PrintTask(String name) {
        super(name);
    }

    @Override
    protected String doWork() {
        return "xong";
    }
}

public class TaskDemo {
    public static void main(String[] args) {
        Task first = new PrintTask("Alpha");
        Task second = new PrintTask("Beta");

        System.out.println(Task.totalCreated());
        first.execute();
        second.execute();
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac -encoding UTF-8 TaskDemo.java
java TaskDemo
~~~

Kết quả chuẩn:

~~~text
2
[task] Alpha: xong
[task] Beta: xong
~~~

Giải thích theo dòng chảy:
1. `new PrintTask(...)` gọi `super(name)`. Constructor của `Task` lưu `name` qua trường `private final` và tăng biến `private static createdCount`. Sau hai lần tạo, bộ đếm bằng `2`.
2. `Task.totalCreated()` đọc dữ liệu thuộc lớp mà không cần truy cập trường `private` từ ngoài.
3. `execute()` là instance method `final` nên `PrintTask` không thể thay đổi thứ tự hoạt động của nó. Phương thức này gọi trợ giúp `private displayLabel()` rồi gọi `doWork()`.
4. `doWork()` là `protected abstract`; tại runtime, lời gọi trên `first` và `second` tìm triển khai `PrintTask.doWork()`. Kết quả `"xong"` được in ra.
5. `PrintTask` là `final` nhưng vẫn được phép kế thừa `Task`. Hệ thống có thể thêm **một lớp con khác của `Task`** nếu muốn cách làm việc khác.

Đây là mẫu tổ chức hữu ích khi cần bắt buộc mọi tác vụ tuân theo khung xử lý chung nhưng vẫn cho phép thay đổi bước chuyên biệt.

## 7. Ví dụ chạy được: hiding (`static`) và overriding (`abstract`) khác nhau thế nào?

Lưu thành **`BindingDemo.java`**:

~~~java
abstract class Animal {
    public static String category() {
        return "Animal";
    }

    public abstract String sound();
}

class Cat extends Animal {
    public static String category() {
        return "Cat";
    }

    @Override
    public String sound() {
        return "meow";
    }
}

public class BindingDemo {
    public static void main(String[] args) {
        Animal pet = new Cat();

        System.out.println(Animal.category());
        System.out.println(Cat.category());
        System.out.println(pet.category()); // Hợp lệ nhưng nên tránh cách gọi này.
        System.out.println(pet.sound());
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 BindingDemo.java
java BindingDemo
~~~

Kết quả chuẩn:

~~~text
Animal
Cat
Animal
meow
~~~

Ở `pet.category()`, kiểu **khai báo** của biến `pet` là `Animal` nên trình biên dịch chọn `Animal.category()`. Đây là hiding, không phải đa hình. Ở `pet.sound()`, JVM sử dụng kiểu đối tượng thực `Cat` để chọn phương thức instance override nên kết quả là `meow`. Viết `Animal.category()` hoặc `Cat.category()` sẽ làm ý định rõ hơn và tránh nhầm lẫn.

## 8. Các lỗi biên dịch dễ mắc

Các tổ hợp như `abstract final class`, `static abstract`, `private abstract` và `final abstract` là các lỗi cần nhận diện; ma trận đầy đủ, bao gồm khác biệt giữa lớp top-level và lớp thành viên cùng các modifier `sealed`, được tập trung trong bài về xung đột `abstract`/`final`. Phần còn lại của bài này minh họa các hành vi riêng của `final`, `private` và `static` như override, truy cập thành viên và trạng thái mutable.

## 9. Cách lựa chọn trong thiết kế

| Nhu cầu | Cách dùng gợi ý | Lý do |
| --- | --- | --- |
| Trạng thái riêng của mỗi đối tượng, được gán khi khởi tạo | `private final` field | Giữ bất biến tham chiếu/trị số và hạn chế quyền sửa trực tiếp. |
| Hằng số nội bộ của lớp | `private static final` field | Thể hiện giá trị dùng chung và tránh công khai chi tiết triển khai. |
| Đếm hoặc quản lý trạng thái chung | `private static` field, API truy cập rõ ràng | Tránh lớp con tự thay đổi trạng thái chung; cân nhắc an toàn luồng. |
| Hàm phụ trợ chỉ lớp cha dùng | `private` method | Giảm bề mặt API và ràng buộc không cần thiết với lớp con. |
| Quy trình không cho phép lớp con sửa | `public/protected final` instance method | Giữ khung thực thi nhất quán. |
| Bước phải do lớp con triển khai | `protected/public abstract` instance method | Tạo hợp đồng đa hình hợp lệ. |
| Lớp triển khai cuối cùng, không cho kế thừa tiếp | `final class Concrete extends AbstractBase` | Khóa việc mở rộng từ lớp cụ thể. |

Không đặt `static` cho phương thức khi bạn muốn cách xử lý phụ thuộc kiểu thực của đối tượng. Không dùng `protected` một cách máy móc để lộ dữ liệu; nên cân nhắc API hành vi. Không dùng `final` như lời đảm bảo thread safety: một đối tượng vẫn có thể chứa trạng thái mutable, và biến `static` dùng chung vẫn có thể xảy ra race condition.

## 10. Tự kiểm tra

1. **Có thể gọi phương thức `static` của lớp `abstract` mà không tạo instance không?** Có; ví dụ `Task.totalCreated()`. Việc gọi phương thức không có nghĩa có thể `new Task()`.
2. **Vì sao `private abstract` sai?** Vì lớp con không thể override phương thức `private`; hợp đồng abstract sẽ không thể được thực hiện.
3. **Vì sao `final` instance method vẫn gọi được `abstract` method?** Vì `final` chỉ cấm override chính phương thức `final`; lời gọi nội bộ sang hook trừu tượng vẫn được dispatch động đến lớp con.
4. **`private static final List<?>` có bất biến không?** Chỉ tham chiếu trường không được gán lại; các phần tử hoặc danh sách vẫn có thể thay đổi nếu đối tượng cho phép và mã có đường truy cập thích hợp.
5. **`Animal pet = new Cat(); pet.category()` dùng phương thức nào?** `Animal.category()`, vì `category()` là `static` và lựa chọn dựa trên kiểu biểu thức tại lúc biên dịch. `pet.sound()` thì dùng `Cat.sound()` vì đó là instance method được override.

**Ghi nhớ:** `static` xác định thành viên cấp lớp và không tham gia overriding; `final` giới hạn việc gán lại hoặc override; `private` giới hạn truy cập và loại phương thức khỏi hợp đồng override. Trong lớp trừu tượng, bộ ba này phối hợp tốt với một số phương thức `protected abstract` để tạo thiết kế đóng gói và mở rộng có kiểm soát.
