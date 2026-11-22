# Giới hạn kế thừa và tạo đối tượng enum

## 1. Enum biểu diễn một tập hằng, không phải lớp để tạo tùy ý nhiều đối tượng

Xét:

```java
enum Mode {
    FAST,
    SAFE
}
```

`FAST` và `SAFE` là các đối tượng hằng được khai báo trong kiểu `Mode`. Người dùng lấy chúng bằng `Mode.FAST`, `Mode.SAFE` hoặc các API tìm hằng phù hợp.

Không được viết:

```java
// Mode another = new Mode(); // Khong bien dich
```

Cũng không thể tạo một lớp con bên ngoài để bổ sung `TURBO` vào chính kiểu `Mode`.

Đây là một phần ý nghĩa của enum: tập hằng được xác định bởi khai báo enum và được ngôn ngữ bảo vệ. Nếu một mô hình cần tạo vô số đối tượng từ dữ liệu runtime, enum thường chỉ nên giữ một phần phân loại, còn dữ liệu cấu hình nằm ở một đối tượng khác.

Bài sử dụng những quy tắc của Java hiện nay và ví dụ chạy trên JDK 17 trở lên.

## 2. Enum đã có lớp cha do ngôn ngữ xác định

Với một enum tên `Mode`, lớp cha trực tiếp của **lớp enum** là:

```text
java.lang.Enum<Mode>
```

Vì vậy, enum không có chỗ để khai báo thêm một lớp cha theo ý người dùng.

Các ý tưởng sau đều không phải cú pháp kế thừa enum hợp lệ:

```java
// enum Mode extends BaseTask { FAST, SAFE }
// enum MoreMode extends Mode { TURBO }
```

Các dòng chỉ minh họa cách khai báo không hợp lệ, được chú thích để không bị hiểu là mã chạy.

Java không cho enum một mệnh đề `extends`. Người viết cũng không được tạo một lớp thông thường trực tiếp `extends Enum<...>` để tự mô phỏng lại enum.

### Không thể bỏ quy tắc enum chỉ vì Enum là một lớp

`java.lang.Enum` là lớp cơ sở của các enum do ngôn ngữ tạo ra. Việc nó có các thành viên `protected` không có nghĩa người dùng được tự viết một lớp con trực tiếp theo mô hình lớp bình thường.

Compiler kiểm tra một quy tắc riêng: lớp thông thường không được trực tiếp mở rộng `java.lang.Enum`.

Các quy tắc lớp cha và hạn chế tạo thể hiện được định nghĩa tại [JLS: Enum Classes](https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.9).

## 3. Enum có thể implements interface

Mặc dù không thể chọn một lớp cha khác, enum vẫn có thể thực hiện interface:

```java
interface Task {
    String run();
}

enum BasicMode implements Task {
    FAST,
    SAFE;

    @Override
    public String run() {
        return name().toLowerCase(java.util.Locale.ROOT);
    }
}
```

Đây là các khai báo minh họa có thể đặt trong một tệp phù hợp.

Người gọi có thể sử dụng:

```java
Task task = BasicMode.FAST;
String result = task.run();
```

Interface tạo một hợp đồng chung cho nhiều cách cài đặt. Nó không biến tập hằng của enum thành một tập có thể được nối thêm từ bên ngoài.

Một enum khác hoặc một lớp thông thường có thể thực hiện cùng `Task`. Chúng dùng chung hành vi theo interface nhưng không trở thành các hằng mới của `BasicMode`.

## 4. Không thể kế thừa enum từ bên ngoài, nhưng có thân lớp riêng của hằng

Một hằng có thể có phần thân riêng:

```java
FAST {
    @Override
    public String run() {
        return "fast";
    }
}
```

Đây là một hằng được trích từ enum trong chương trình đầy đủ, không phải lớp độc lập.

Phần thân này ngầm khai báo một lớp con vô danh của enum. Nó là cơ chế được ngôn ngữ dành riêng cho hằng, không phải quyền cho người dùng tự viết lớp con tùy ý ở nơi khác.

Mô hình:

```text
Enum<Mode>
    |
    v
  Mode
    |
    +-- lop vo danh cua FAST
    |
    +-- lop vo danh cua SAFE
```

Lớp enum `Mode` mở rộng `Enum<Mode>`. Đối tượng hằng có thân riêng có thể thuộc một lớp con vô danh mở rộng `Mode`.

### Quy tắc final và sealed trong Java hiện hành

- Enum không có hằng nào mang thân lớp riêng là enum ngầm `final`.
- Enum có ít nhất một hằng mang thân lớp riêng là enum ngầm `sealed`.
- Các lớp con trực tiếp được phép là những lớp vô danh do các hằng có thân riêng khai báo ngầm.

Vì vậy, không nên giải thích bằng một câu tuyệt đối rằng “mọi enum luôn final nên không hề có lớp con”. Cơ chế thân riêng là một phần của mô hình enum hiện tại.

Tuy nhiên, enum ngầm sealed vẫn không cho người dùng thêm một lớp con có tên hoặc một enum con ở bên ngoài danh sách đó.

Không tự ghi `abstract`, `final`, `sealed` hoặc `non-sealed` vào khai báo enum. Các trạng thái liên quan được ngôn ngữ xác định theo quy tắc riêng.

## 5. Constructor enum thiết lập dữ liệu cho các hằng đã khai báo

Enum có thể có constructor và tham số:

```java
enum Level {
    LOW(1),
    HIGH(3);

    private final int value;

    private Level(int value) {
        this.value = value;
    }

    public int value() {
        return value;
    }
}
```

Các đối số `1` và `3` được dùng khi khởi tạo các hằng `LOW` và `HIGH`.

Các quy tắc cần giữ:

- Constructor enum không được là `public` hoặc `protected`.
- Nếu không ghi mức truy cập, constructor có phạm vi `private`.
- Có thể ghi `private` tường minh.
- Có thể có nhiều constructor và ủy quyền constructor theo các quy tắc phù hợp.
- Không tự gọi constructor bằng `new`, kể cả từ bên trong enum.
- Không gọi tường minh constructor lớp cha `Enum` để tự cung cấp tên và ordinal.

### Có private chưa phải toàn bộ lý do cấm new

Với một lớp bình thường, constructor private vẫn có thể được gọi từ những vị trí được phép bên trong thiết kế lớp đó.

Enum có thêm một giới hạn ngôn ngữ: không được tạo thể hiện enum bằng biểu thức `new`. Nó không trở thành hợp lệ chỉ vì dòng `new` nằm trong chính enum và có thể nhìn thấy constructor private.

Constructor chỉ phục vụ cơ chế khởi tạo các hằng đã được khai báo, không mở một API tạo đối tượng theo yêu cầu.

Quy tắc constructor nằm ở [JLS: Enum Body Declarations](https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.9.2).

## 6. Chương trình đầy đủ: quan sát khởi tạo và giới hạn mở rộng

Ví dụ dưới đây minh họa:

- Enum đơn giản ngầm final.
- Enum có thân riêng ngầm sealed.
- Constructor được dùng để tạo các hằng trong quá trình khởi tạo lớp enum.
- Truy cập lại và factory không tạo hằng mới.
- Interface cho phép chia sẻ hợp đồng với một enum khác và một lớp cấu hình thông thường.

Lưu thành `EnumConstructionLimitsDemo.java`:

```java
import java.lang.reflect.Modifier;

public class EnumConstructionLimitsDemo {
    interface Task {
        String run();
    }

    enum Simple {
        ONE,
        TWO
    }

    enum Mode implements Task {
        FAST(1) {
            @Override
            public String run() {
                return "fast";
            }
        },
        SAFE(3) {
            @Override
            public String run() {
                return "safe";
            }
        };

        private final int level;

        private Mode(int level) {
            this.level = level;
            System.out.println("construct " + name() + " level=" + level);
        }

        public int level() {
            return level;
        }

        public static Mode fromLevel(int level) {
            for (Mode mode : values()) {
                if (mode.level == level) {
                    return mode;
                }
            }
            throw new IllegalArgumentException("unknown level: " + level);
        }

        @Override
        public abstract String run();
    }

    enum ExtraMode implements Task {
        BALANCED;

        @Override
        public String run() {
            return "balanced";
        }
    }

    record ConfiguredTask(String label) implements Task {
        @Override
        public String run() {
            return label;
        }
    }

    public static void main(String[] args) {
        System.out.println("before enum use");
        Mode first = Mode.FAST;
        Mode again = Mode.FAST;
        Mode parsed = Mode.valueOf("FAST");
        Mode selected = Mode.fromLevel(1);

        System.out.println("same access = " + (first == again));
        System.out.println("valueOf returns existing = " + (first == parsed));
        System.out.println("factory returns existing = " + (first == selected));
        System.out.println("mode count = " + Mode.values().length);
        System.out.println("base class is Enum = "
                + (Mode.class.getSuperclass() == Enum.class));
        System.out.println("Simple is final = "
                + Modifier.isFinal(Simple.class.getModifiers()));
        System.out.println("Mode is sealed = " + Mode.class.isSealed());
        System.out.println("body class extends Mode = "
                + (first.getClass().getSuperclass() == Mode.class));
        System.out.println("declaring enum is Mode = "
                + (first.getDeclaringClass() == Mode.class));

        Task[] tasks = {
                Mode.FAST,
                ExtraMode.BALANCED,
                new ConfiguredTask("custom")
        };
        for (Task task : tasks) {
            System.out.println("task = " + task.run());
        }

        try {
            Mode.fromLevel(2);
        } catch (IllegalArgumentException exception) {
            System.out.println("unknown level does not create a mode");
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -Xlint:all -Werror EnumConstructionLimitsDemo.java
java EnumConstructionLimitsDemo
```

Stdout:

```text
before enum use
construct FAST level=1
construct SAFE level=3
same access = true
valueOf returns existing = true
factory returns existing = true
mode count = 2
base class is Enum = true
Simple is final = true
Mode is sealed = true
body class extends Mode = true
declaring enum is Mode = true
task = fast
task = balanced
task = custom
unknown level does not create a mode
```

Các dòng `construct ...` chỉ để quan sát thời điểm khởi tạo trong ví dụ. Không cần thêm tác dụng phụ ghi log vào mọi constructor enum thực tế để sử dụng enum.

## 7. Cách đọc các hành vi đã kiểm chứng

### 7.1. Các hằng được khởi tạo khi kiểu enum được khởi tạo

Sau dòng `before enum use`, lần sử dụng `Mode.FAST` dẫn tới khởi tạo kiểu Mode trong chương trình. Constructor chạy cho cả `FAST` và `SAFE` theo thứ tự khai báo.

Các lần tiếp theo lấy `Mode.FAST` không gọi constructor thêm lần nữa.

Không hiểu enum như một factory tạo một đối tượng mới khi đọc trường hằng. Hằng là một đối tượng đã được cơ chế khởi tạo của kiểu tạo và giữ lại.

Thời điểm khởi tạo lớp trong một chương trình khác có thể bị ảnh hưởng bởi những lần sử dụng trước đó. Ví dụ cố ý chưa chạm tới Mode trước dòng thông báo đầu để hành vi quan sát được rõ ràng.

### 7.2. valueOf và factory trả hằng có sẵn

`Mode.valueOf("FAST")` trả đúng hằng `FAST` đã có.

`Mode.fromLevel(1)` là factory do ví dụ tự viết, nhưng nó cũng chỉ tìm và trả một trong các hằng sẵn có. Tên “factory” không có nghĩa phương thức đó được phép phá giới hạn và gọi `new Mode(...)`.

Nếu không có mức `2`, ví dụ báo `IllegalArgumentException`. Nó không tự tạo một hằng mới với dữ liệu `2`.

### 7.3. Lớp enum và lớp thực tế của hằng có thể khác nhau

`Mode.class.getSuperclass() == Enum.class` là `true`: đó là lớp cha trực tiếp của lớp enum.

`Mode.FAST.getClass().getSuperclass() == Mode.class` cũng là `true` trong ví dụ: đối tượng FAST thuộc lớp con vô danh do thân riêng tạo ra.

`getDeclaringClass()` của hằng vẫn trả `Mode.class`. Khi cần xác định enum mà một hằng thuộc về, đây là API diễn tả đúng ý hơn việc mặc định lớp runtime luôn chính là lớp enum.

### 7.4. Interface mở rộng tập cách cài đặt, không mở tập hằng Mode

Mảng `Task[]` chứa:

- `Mode.FAST`.
- `ExtraMode.BALANCED`.
- Một `ConfiguredTask` mới.

Cả ba dùng được qua `Task.run()`. Nhưng `Mode.values()` vẫn chỉ có hai hằng của chính Mode.

Một hợp đồng interface và danh sách hằng của một enum là hai tập khái niệm khác nhau. Dùng chung interface không gộp các enum thành một kiểu enum lớn hơn.

## 8. Có tạo thêm enum bằng reflection hoặc clone được không?

Các API Java thông thường tiếp tục bảo vệ mô hình tập hằng:

- Tạo thể hiện enum bằng reflection qua `Constructor.newInstance` bị cấm.
- `Enum.clone()` là `final` và ném `CloneNotSupportedException`, không tạo bản sao hằng.
- Cơ chế tuần tự hóa chuẩn có xử lý riêng để giữ định danh hằng enum khi khôi phục, thay vì tạo thêm một đối tượng hằng độc lập như một lớp thông thường.

Hợp đồng reflection có quy định từ chối constructor của enum; xem [Constructor.newInstance](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/Constructor.html#newInstance(java.lang.Object...)) và [Enum.clone](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Enum.html#clone()).

Việc có thể đọc metadata constructor bằng reflection không cấp quyền tạo thêm hằng. Thay đổi khả năng truy cập của một constructor cũng không biến enum thành lớp có thể khởi tạo tùy ý theo hợp đồng API đó.

Không thiết kế chức năng thêm lựa chọn runtime dựa trên ý tưởng “sẽ tìm cách gọi constructor enum”. Nếu yêu cầu là một tập lựa chọn mở, chọn một mô hình mở phù hợp.

### “Một đối tượng cho mỗi hằng” có phạm vi kiểu được nạp

Các phép so sánh trong chương trình nói về cùng một kiểu enum đã được nạp trong cùng ngữ cảnh lớp.

Không nên dùng mô hình này để khẳng định mọi tiến trình hoặc mọi ngữ cảnh class loader trên toàn hệ thống chia sẻ duy nhất một đối tượng Java. Khi đi qua ranh giới tiến trình, dữ liệu cần định danh theo một giao thức thích hợp, không phải chia sẻ trực tiếp địa chỉ đối tượng.

## 9. Không có quyền tạo tùy ý không có nghĩa enum tự bất biến

Mỗi hằng được dùng lại, nhưng enum vẫn có thể khai báo trường có thể thay đổi nếu người viết chọn như vậy.

Nếu đặt một bộ đếm mutable trong `Mode.FAST`, nhiều lời gọi sử dụng FAST có thể cùng quan sát bộ đếm đó. Không có một bản trạng thái mới tự xuất hiện cho mỗi thao tác.

Ví dụ giữ `level` là `final` và các hàm `run` không sửa trạng thái dùng chung. Điều này làm vòng đời của dữ liệu phù hợp với vòng đời của hằng.

Nếu cần trạng thái theo từng yêu cầu hoặc người dùng, nên tách thành một đối tượng thường:

```java
record Job(Mode mode, int retryLimit)
```

Đây là hình dạng một kiểu dữ liệu minh họa. Một `Job` mới giữ một lựa chọn Mode cùng cấu hình riêng; nó không tạo thêm hằng Mode.

Cách tách này cho phép một tập chế độ đóng kết hợp với nhiều yêu cầu cấu hình khác nhau.

## 10. Nếu cần mở rộng, chọn đúng mức mô hình

| Yêu cầu | Hướng thiết kế |
| --- | --- |
| Một tập tên cố định trong mã nguồn | Enum |
| Mỗi tên có dữ liệu cố định | Enum có constructor và trường |
| Mỗi hằng có hành vi khác nhau | Thân riêng của hằng hoặc phương thức chung phù hợp |
| Nhiều cách cài đặt độc lập cùng giao diện | Interface |
| Tạo đối tượng theo tham số runtime | Lớp hoặc record với hợp đồng constructor/factory |
| Chế độ cố định kết hợp dữ liệu theo yêu cầu | Enum nằm trong một đối tượng cấu hình |
| Các lựa chọn do người dùng hoặc plugin bổ sung động | Registry hoặc cơ chế đăng ký dựa trên hợp đồng mở |

Không tạo một enum thứ hai rồi cố cho nó `extends` enum cũ. Nếu hai tập đều thực hiện một interface, mã nhận interface có thể dùng cả hai.

Đổi lại, ở mức interface sẽ không tự có một phương thức `values()` chung liệt kê mọi cách cài đặt. Nếu nghiệp vụ cần một danh sách các lựa chọn đang đăng ký, phải quản lý danh sách đó tường minh.

Không phải mọi yêu cầu mở rộng đều cần một hệ thống plugin. Một interface và vài lớp thông thường có thể đã đủ. Điều quan trọng là không gán một yêu cầu tập mở cho enum vốn có tập hằng đóng.

## 11. Một số giới hạn khác dễ bị hiểu sai

### Không khai báo enum theo cách lớp abstract thông thường

Enum có thể có phương thức abstract nếu các hằng cung cấp phần triển khai cụ thể theo quy tắc enum. Nhưng không được thêm từ khóa `abstract` trước `enum`.

Điều này khác với một lớp abstract có thể được mở rộng bằng các lớp con đặt tên ở bên ngoài.

### Không dùng constructor của thân hằng như một lớp đặt tên

Thân riêng là một lớp vô danh được khai báo ngầm. Truyền tham số vào hằng để gọi constructor enum; không tự đặt một constructor có tên riêng trong thân đó.

### Không cần đối tượng bao ngoài cho enum lồng nhau

Enum lồng nhau có tính `static` ngầm định theo quy tắc ngôn ngữ. Các enum trong chương trình minh họa không cần một đối tượng `EnumConstructionLimitsDemo` để lấy hằng.

Điều này vẫn không tạo quyền gọi `new` với enum. Nó chỉ mô tả quan hệ của kiểu lồng nhau với đối tượng bao ngoài.

### Không nên gọi phương thức ghi đè quá sớm từ constructor

Một hằng có thân riêng có thể có trạng thái instance riêng. Nếu constructor enum gọi một phương thức bị thân đó ghi đè trong quá trình khởi tạo, phần triển khai lớp con có thể chạy khi dữ liệu riêng chưa sẵn sàng.

Trong ví dụ, constructor chỉ nhận dữ liệu, gán trường và in thông tin quan sát bằng `name()`. Các hành vi đa hình `run` được gọi sau khi hằng đã khởi tạo.

## 12. Những lỗi biên dịch tiêu biểu

### Cố new enum

```java
enum ClosedMode {
    A
}

// ClosedMode value = new ClosedMode(); // Khong bien dich
```

Không thể tạo thêm một đối tượng như cách tạo lớp thông thường.

### Cố kế thừa enum

```java
// class ExternalChild extends ClosedMode { } // Khong bien dich
```

Với enum đơn giản, compiler có thể báo không được kế thừa lớp final cùng các lỗi liên quan tới quy tắc enum. Với enum có thân riêng, việc tự thêm một lớp con ngoài cơ chế cho phép cũng không hợp lệ.

### Cố mở constructor public

```java
// enum PublicMode {
//     A;
//     public PublicMode() { } // Khong bien dich
// }
```

Không thể sửa bằng cách đổi phạm vi constructor để tạo một API new công khai.

### Cố kế thừa Enum trực tiếp

Một lớp thông thường `extends Enum<...>` không được ngôn ngữ cho phép. Đừng coi chữ ký constructor `Enum(String, int)` trong tài liệu là một API để tự cung cấp tên và ordinal cho một enum tự chế.

Khi thử các ví dụ lỗi, đọc nguyên nhân chính thay vì phụ thuộc chính xác số lượng hoặc câu chữ thông báo. Một khai báo vi phạm có thể sinh nhiều lỗi liên quan trên một phiên bản compiler.

## 13. Thực hành tự kiểm tra

### Bài 1: Lớp cha

Một enum Mode có thể `extends BaseTask` nếu BaseTask cung cấp mã dùng chung không?

**Đáp án:** không. Lớp enum đã có lớp cha `Enum<Mode>` theo quy tắc ngôn ngữ. Có thể dùng thành phần bên trong hoặc interface phù hợp để chia sẻ hành vi.

### Bài 2: Private constructor

Nếu viết `new Mode(...)` bên trong một phương thức của chính enum, có hợp lệ vì constructor private nhìn thấy được không?

**Đáp án:** không. Enum có một lệnh cấm khởi tạo tường minh bằng new ngoài câu chuyện quyền truy cập constructor.

### Bài 3: Enum có lớp con không?

Một hằng có thân riêng có mâu thuẫn với giới hạn kế thừa không?

**Đáp án:** không. Đó là lớp con vô danh được cơ chế enum khai báo ngầm. Nó không cho phép người dùng tự tạo lớp con bên ngoài.

### Bài 4: final hay sealed?

Enum không có thân riêng của hằng và enum có ít nhất một thân riêng có cùng trạng thái ngầm không?

**Đáp án:** không. Trường hợp đầu ngầm final; trường hợp sau ngầm sealed với các lớp con được phép do thân riêng của hằng tạo ra.

### Bài 5: Factory

`Mode.fromLevel(2)` có thể tạo một hằng mới khi chưa có mức 2 không?

**Đáp án:** không theo mô hình enum. Factory có thể trả hằng có sẵn, báo lỗi hoặc dùng một kết quả khác được hợp đồng quy định. Nếu cần một giá trị cấu hình tùy ý, trả một kiểu đối tượng phù hợp.

### Bài 6: Mở rộng hành vi

Nếu muốn một enum khác và một lớp cấu hình đều dùng qua cùng API, có cần kế thừa enum gốc không?

**Đáp án:** không. Cùng thực hiện một interface, như Task trong ví dụ, rồi để mã sử dụng nhận interface đó.

Enum phù hợp khi tập hằng được xác định trong khai báo và các đối tượng ấy có vòng đời được ngôn ngữ kiểm soát. Giữ mô hình đóng đó cho phần phân loại; dùng interface, lớp và thành phần cấu hình khi yêu cầu là tạo hoặc mở rộng các đối tượng khác.
