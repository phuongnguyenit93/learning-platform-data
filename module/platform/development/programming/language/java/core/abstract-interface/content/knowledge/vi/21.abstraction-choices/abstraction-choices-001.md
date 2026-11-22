# So sánh abstract class và interface theo mục tiêu thiết kế

Trong Java, `abstract class` và `interface` đều giúp mô tả những hành vi mà một lớp cụ thể phải cung cấp. Điểm khác nhau cốt lõi nằm ở mục tiêu thiết kế: **abstract class** phù hợp khi các lớp thuộc cùng một họ cần chia sẻ trạng thái, quy tắc và phần triển khai; **interface** phù hợp khi muốn định nghĩa một vai trò hoặc khả năng mà nhiều lớp khác nhau có thể cùng đảm nhận.

Các ví dụ dưới đây dùng Java 17 trở lên.

## 1. So sánh nhanh

| Tiêu chí | Abstract class | Interface |
|---|---|---|
| Mục tiêu chính | Chia sẻ nền tảng triển khai giữa các lớp có quan hệ cùng họ | Mô tả hợp đồng hoặc khả năng mà lớp có thể đảm nhận |
| Kế thừa/triển khai | Một lớp chỉ có thể `extends` một lớp trực tiếp | Một lớp có thể `implements` nhiều interface |
| Trạng thái đối tượng | Có thể có field instance mutable hoặc immutable | Không có field instance; field được khai báo trong interface là hằng `public static final` |
| Khởi tạo | Có constructor để thiết lập trạng thái chung; không thể `new` trực tiếp abstract class | Không có constructor và không thể khởi tạo interface trực tiếp |
| Phương thức | Có thể có phương thức concrete, abstract, final, protected và các mức truy cập lớp cho phép | Có phương thức abstract, `default`, `static`, và `private` (private method trong interface từ Java 9) |
| Mức truy cập | Phương thức có thể là public, protected, package-private hoặc private tùy mục đích | Hợp đồng được công khai qua phương thức public; phương thức private chỉ là helper bên trong interface |
| Thay đổi hợp đồng | Có thể thêm logic chung, trạng thái hoặc hook; thay đổi vẫn cần đánh giá ảnh hưởng đến lớp con | Có thể thêm default method để mở rộng hành vi, nhưng cần xem xét xung đột và thay đổi ngữ nghĩa |
| Khi phù hợp | Template method, trạng thái và invariant chung, khung xử lý có phần bắt buộc ghi đè | Vai trò độc lập, capability, API mở cho nhiều kiểu triển khai, kết hợp nhiều hợp đồng |

Không nên chọn chỉ dựa vào việc có hay không có phương thức đã triển khai. Interface hiện đại có thể chứa `default` và `static` method; abstract class có thể không chứa trạng thái. Hãy bắt đầu từ quan hệ và trách nhiệm mà mô hình cần thể hiện.

## 2. Chọn abstract class khi cần nền tảng chung

Một abstract class hữu ích khi các lớp con thực sự thuộc cùng một họ và cần chia sẻ dữ liệu hoặc quy tắc không nên lặp lại. Nó có thể:

- Giữ trạng thái đối tượng bằng field instance.
- Khởi tạo và xác thực trạng thái qua constructor.
- Cung cấp phương thức dùng chung để các lớp con không tự triển khai lại.
- Khai báo abstract method làm điểm mở rộng bắt buộc.
- Đóng một phần quy tắc bằng phương thức `final`, đồng thời cho phép lớp con tùy biến các bước được thiết kế để mở rộng.

Ví dụ, các loại tài liệu có cùng mã định danh, quy tắc kiểm tra và vòng đời có thể kế thừa một lớp nền `Document`. Lớp nền giữ mã định danh và xác thực dữ liệu một lần; từng loại tài liệu tự định nghĩa cách kết xuất nội dung.

Mẫu này thường hợp lý khi quan hệ là “là một loại của” và các lớp cần kế thừa một phần triển khai thực chất. Đừng tạo abstract class chỉ để gom những phương thức tiện ích không có quan hệ mô hình rõ ràng.

### Template method

Abstract class cũng có thể giữ thứ tự các bước của một thuật toán, trong khi giao việc cụ thể cho các phương thức abstract hoặc protected hook. Nếu thứ tự đó là invariant, một phương thức điều phối có thể là `final` để lớp con không vô tình phá vỡ quy trình. Chỉ dùng cách này khi các bước chung thực sự thuộc về một quy trình ổn định.

## 3. Chọn interface khi cần mô tả vai trò hoặc capability

Interface phù hợp khi người gọi chỉ cần biết một đối tượng **có thể làm gì**, không cần biết đối tượng được xây dựng ra sao hoặc nó thuộc cây kế thừa nào.

Ví dụ, `Comparable<T>`, `Runnable` và `AutoCloseable` mô tả những hợp đồng khác nhau. Các lớp không cùng một lớp cha vẫn có thể thực hiện cùng một interface. Một lớp có thể đồng thời đảm nhận nhiều vai trò, chẳng hạn vừa có tên, vừa có thể xuất dữ liệu.

Ưu tiên interface khi:

- Muốn API nhận nhiều cách triển khai khác nhau mà không phụ thuộc lớp cụ thể.
- Muốn kết hợp nhiều capability trên cùng một lớp.
- Muốn dễ thay thế implementation trong kiểm thử hoặc cấu hình ứng dụng.
- Muốn xác định hợp đồng ở ranh giới giữa các module hoặc thành phần.
- Không cần lưu trạng thái instance chung hay ép mọi implementation dùng chung một thuật toán nền.

Một interface có thể cung cấp `default` method khi có hành vi mặc định hợp lý cho tất cả hoặc phần lớn implementation. Tuy nhiên, `default` method không thay thế được trạng thái instance, constructor hay mọi nhu cầu của một lớp nền.

## 4. Những giới hạn và quy tắc cần nhớ

**Java chỉ cho một lớp kế thừa trực tiếp một lớp khác.** Vì vậy, nếu lớp đã `extends` một abstract class, nó không thể thêm một lớp cha thứ hai để lấy code dùng chung. Nó vẫn có thể `implements` nhiều interface.

**Một interface không thể `extends` class.** Interface có thể `extends` một hoặc nhiều interface khác; một lớp có thể `extends` một lớp và `implements` nhiều interface.

**Field của interface là hằng.** Field khai báo trong interface ngầm định là `public static final`. Không dùng interface để lưu trạng thái riêng của từng đối tượng. Nếu các implementation cần trạng thái riêng, hãy để trạng thái đó trong lớp hoặc một đối tượng cộng tác.

**Abstract class có thể chứa constructor nhưng không thể được khởi tạo trực tiếp.** Constructor của nó chạy khi lớp con được khởi tạo và giúp bảo đảm trạng thái chung hợp lệ. Lớp con concrete phải triển khai các abstract method còn thiếu.

**Interface method không phải lúc nào cũng abstract.** Interface có thể khai báo abstract method, `default` method, `static` method và private helper method. Tuy vậy, các phương thức hợp đồng public vẫn cần được triển khai phù hợp bởi lớp cụ thể.

**Default method có thể phát sinh xung đột.** Nếu một lớp kế thừa hai interface không liên quan có cùng một default method, lớp thường phải override để quyết định hành vi. Phương thức instance phù hợp trong lớp cha cũng có độ ưu tiên cao hơn default method của interface. Vì vậy, việc thêm default method vào một API công khai cần xem xét các implementation hiện có.

**Abstract class và interface không loại trừ lẫn nhau.** Abstract class có thể `implements` một hoặc nhiều interface. Đây thường là thiết kế tốt: interface thể hiện hợp đồng, còn lớp trừu tượng cung cấp một implementation nền cho những lớp muốn tái sử dụng.

## 5. Ví dụ Java hoàn chỉnh

Trong ví dụ này, `Named` mô tả capability đặt tên, `Exportable` mô tả khả năng xuất dữ liệu, còn abstract class `Task` giữ trạng thái và quy tắc chung của một tác vụ. `BuildTask` kế thừa phần nền từ `Task` và đồng thời triển khai `Exportable`.

Lưu thành `DesignChoiceDemo.java`:

~~~java
interface Named {
    String name();

    default String label() {
        return name().trim();
    }
}

interface Exportable {
    String export();
}

abstract class Task implements Named {
    private final String name;

    protected Task(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("name must not be blank");
        }
        this.name = name.trim();
    }

    @Override
    public final String name() {
        return name;
    }

    public abstract String execute();
}

final class BuildTask extends Task implements Exportable {
    private final int steps;

    BuildTask(String name, int steps) {
        super(name);
        if (steps < 0) {
            throw new IllegalArgumentException("steps must be non-negative");
        }
        this.steps = steps;
    }

    @Override
    public String execute() {
        return "Built " + name() + " in " + steps + " steps";
    }

    @Override
    public String export() {
        return name() + "," + steps;
    }
}

public class DesignChoiceDemo {
    public static void main(String[] args) {
        Task task = new BuildTask("Java", 3);

        System.out.println(task.label());
        System.out.println(task.execute());

        Exportable exportable = (Exportable) task;
        System.out.println(exportable.export());
    }
}
~~~

Biên dịch và chạy:

~~~text
javac DesignChoiceDemo.java
java DesignChoiceDemo
~~~

Stdout chính xác:

~~~text
Java
Built Java in 3 steps
Java,3
~~~

Ví dụ cho thấy mỗi kiểu chịu trách nhiệm khác nhau:

- `Task` giữ trạng thái `name`, kiểm tra dữ liệu đầu vào, cung cấp `name()` và buộc lớp con triển khai `execute()`.
- `Named` mô tả hợp đồng đặt tên và cung cấp cách tạo nhãn mặc định mà không lưu trạng thái riêng.
- `Exportable` cho phép bên gọi xuất dữ liệu mà không cần biết lớp cụ thể là `BuildTask`.
- `BuildTask` kết hợp một lớp nền với một capability bổ sung. Bên gọi có thể làm việc qua kiểu `Task` hoặc `Exportable` tùy mục tiêu.

Phép ép kiểu trong ví dụ an toàn vì đối tượng thực tế là `BuildTask`, lớp này implements `Exportable`. Trong code ứng dụng, nếu không biết chắc đối tượng có capability đó, hãy nhận một tham chiếu `Exportable` từ nơi tạo đối tượng hoặc kiểm tra kiểu trước khi ép kiểu.

## 6. Các lựa chọn thiết kế thường gặp

| Nhu cầu | Lựa chọn thường phù hợp | Lý do |
|---|---|---|
| Nhiều implementation không cùng cây kế thừa nhưng cần cùng một hợp đồng | Interface | Không buộc chúng có chung lớp cha |
| Các lớp con cần cùng trạng thái và constructor để bảo đảm invariant | Abstract class | Đặt trạng thái và quy tắc chung tại một nơi |
| Một lớp cần đảm nhận nhiều vai trò độc lập | Nhiều interface | Java cho phép một lớp triển khai nhiều interface |
| Muốn chia sẻ một thuật toán khung với một vài bước tùy biến | Abstract class | Có thể giữ thứ tự xử lý và định nghĩa hook |
| Chỉ muốn định nghĩa API mà code gọi không phụ thuộc implementation | Interface | Phân tách hợp đồng khỏi lớp cụ thể |
| Muốn cung cấp hành vi mặc định nhỏ cho capability | Interface với default method | Cho phép implementation kế thừa hành vi nếu không cần override |
| Muốn tái sử dụng code nhưng không có quan hệ “là một loại của” hợp lý | Ưu tiên composition | Đối tượng cộng tác thường tránh được sự phụ thuộc cứng vào cây kế thừa |

## 7. Composition là lựa chọn thứ ba

Không phải mọi phần code dùng chung đều nên đặt trong abstract class. Nếu hai lớp chỉ cần dùng chung một dịch vụ hoặc thuật toán nhưng không phải cùng một họ khái niệm, hãy cân nhắc composition: chuyển phần logic đó thành một đối tượng riêng và truyền hoặc inject vào nơi cần dùng.

Composition giúp thay đổi hành vi trong runtime dễ hơn, tránh giới hạn kế thừa đơn của Java và giảm sự phụ thuộc vào chi tiết lớp cha. Đổi lại, nó có thể cần thêm một đối tượng hoặc một lớp cộng tác; hãy chọn theo độ phức tạp thực tế thay vì tạo abstraction quá sớm.

Ví dụ, nhiều loại thông báo có thể dùng chung một `Formatter` thông qua composition, trong khi các loại tác vụ thực sự chia sẻ trạng thái và invariant có thể hợp lý khi kế thừa `Task`.

## 8. Quy trình ra quyết định

1. Xác định điều code gọi cần biết: một hợp đồng/capability hay một nền tảng triển khai có trạng thái.
2. Nếu nhiều lớp cần cùng dữ liệu, constructor, invariant hoặc template method, cân nhắc abstract class.
3. Nếu các kiểu khác nhau cần cùng vai trò, hoặc một lớp cần nhiều vai trò, ưu tiên interface.
4. Nếu chỉ muốn tái sử dụng logic giữa các lớp không cùng một họ, cân nhắc composition.
5. Kiểm tra khả năng mở rộng: Java chỉ cho một lớp cha; interface cho phép kết hợp nhiều hợp đồng, nhưng default method có thể xung đột.
6. Để code gọi phụ thuộc vào interface khi có lợi cho khả năng thay thế implementation; chỉ phụ thuộc vào abstract class khi hành vi nền của nó thực sự là một phần quan trọng của thiết kế.
7. Viết ví dụ nhỏ và kiểm tra constructor, khả năng thay thế, các trường hợp lỗi, cùng hành vi khi thêm implementation mới.

Không có quy tắc rằng interface luôn tốt hơn hoặc abstract class luôn mạnh hơn. Thiết kế tốt chọn abstraction thể hiện đúng mục tiêu, giữ trách nhiệm rõ ràng và không khóa các implementation vào một quan hệ kế thừa không cần thiết.
