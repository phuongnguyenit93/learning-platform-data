# `Cloneable` là marker interface và không tự khai báo phương thức `clone()`

Trong Java, tên `Cloneable` và `clone()` rất giống nhau nhưng thuộc **hai nơi khác nhau**:

- `java.lang.Cloneable` là **marker interface**: một interface rỗng dùng để đánh dấu rằng một đối tượng cho phép cơ chế `Object.clone()` tạo bản sao theo từng trường (*field-for-field copy*).
- `clone()` là phương thức được khai báo trong `java.lang.Object`, với dạng gốc `protected Object clone() throws CloneNotSupportedException`. **Không có phương thức `clone()` nào được khai báo trong `Cloneable`.**

Chỉ viết `implements Cloneable` **không tự sinh phương thức `public clone()`**, không mở rộng phạm vi truy cập của `Object.clone()` và không bảo đảm rằng bên ngoài lớp có thể gọi `object.clone()`. Muốn cung cấp API sao chép cho người dùng lớp, lập trình viên thường phải **ghi đè `clone()`**, xác định kiểu trả về và mức truy cập, đồng thời quyết định cách xử lý trạng thái có thể thay đổi.

## 1. Marker interface là gì?

Marker interface là interface không có phương thức trừu tượng nào cần triển khai; việc một kiểu `implements` interface đó cung cấp **thông tin đánh dấu** cho cơ chế khác kiểm tra. Với `Cloneable`, tín hiệu này được `Object.clone()` sử dụng.

Có thể hình dung đơn giản:

~~~java
// Chỉ để hiểu cấu trúc; không khai báo lại java.lang.Cloneable.
public interface Cloneable {
    // Không có phương thức clone().
}
~~~

Mã trên là **mô hình minh họa**, không phải một interface cần tạo trong dự án. Java đã có sẵn `java.lang.Cloneable`.

Ví dụ một lớp chỉ mang marker:

~~~java
final class MarkerOnly implements Cloneable {
    private int value = 10;
}
~~~

Lớp này hợp lệ; nó **không phải** viết thân cho phương thức nào của `Cloneable` vì interface không yêu cầu phương thức. Tuy vậy, đoạn mã sau ở một lớp gọi thông thường sẽ không biên dịch:

~~~java
MarkerOnly value = new MarkerOnly();
value.clone(); // Lỗi truy cập: Object.clone() vẫn là protected.
~~~

Chú ý: đoạn trên chỉ là **mảnh mã cố ý sai** để giải thích phạm vi truy cập, không ghép vào ví dụ chạy được. Từ khóa `implements Cloneable` không giống một lời hứa rằng lớp đã có API `public clone()`.

### Bảng phân biệt

| Thành phần | Khai báo ở đâu? | Vai trò | Có thể gọi trực tiếp từ mã bên ngoài? |
| --- | --- | --- | --- |
| `Cloneable` | Interface `java.lang.Cloneable` | Đánh dấu tính tương thích với cơ chế `Object.clone()` | Không có phương thức nào để gọi |
| `Object.clone()` | Lớp `java.lang.Object` | Thực hiện bản sao theo từng trường khi điều kiện cho phép | Thường **không**, vì `protected` |
| `public MyType clone()` | Do lớp của bạn override | Cung cấp API sao chép với kiểu trả về rõ ràng | **Có**, nếu chính lớp công khai phương thức đó |
| Copy constructor/factory | Do lớp thiết kế, chẳng hạn `new MyType(original)` | Cách sao chép chủ động, không dựa vào marker | Có, theo mức truy cập được khai báo |

**Dấu hiệu khác chức năng:** marker `Cloneable` ảnh hưởng đến cách **implementation của `Object.clone()`** kiểm tra đối tượng, nhưng không tự thêm một phương thức vào interface để người gọi sử dụng.

## 2. `Object.clone()` có chữ ký và phạm vi truy cập ra sao?

Trong Java 17, khai báo của phương thức gốc là:

~~~java
protected Object clone() throws CloneNotSupportedException
~~~

Có bốn điểm cần phân biệt:

1. `protected`: phương thức gốc không phải API public tùy ý gọi trên mọi `Object`. Quy tắc truy cập `protected` của Java còn liên quan đến package và quan hệ kế thừa; không nên hiểu rằng vì một lớp là `Cloneable` thì mã bất kỳ ở bên ngoài được gọi `clone()`.
2. `Object`: kiểu trả về của phương thức gốc rất rộng. Khi override, một lớp có thể dùng **kiểu trả về hiệp biến** (*covariant return type*), chẳng hạn `public Account clone()`.
3. `throws CloneNotSupportedException`: đây là checked exception của phương thức gốc. Một override có thể tiếp tục khai báo ngoại lệ này, hoặc thu hẹp/bỏ checked exception trong chữ ký public.
4. `Object.clone()` là phương thức **instance**; nó sao chép đối tượng hiện tại, chứ không phải factory static nằm trong `Cloneable`.

Khi một lớp override phương thức gốc để công khai API:

~~~java
final class Account implements Cloneable {
    private final String id;

    Account(String id) {
        this.id = id;
    }

    @Override
    public Account clone() {
        try {
            return (Account) super.clone();
        } catch (CloneNotSupportedException e) {
            throw new AssertionError(e);
        }
    }
}
~~~

Đây là **một lớp minh họa có thể biên dịch trong chương trình phù hợp**, với giả định khóa `id` không `null` được kiểm tra ở tầng nghiệp vụ. `@Override` giúp trình biên dịch xác nhận phương thức ghi đè `Object.clone()`; `public` mở quyền gọi; `Account` là kiểu trả về cụ thể. Vì lớp `Account` là `final` và triển khai `Cloneable`, lời gọi `super.clone()` bình thường không ném `CloneNotSupportedException`; nhánh `AssertionError` chỉ báo một vi phạm bất thường đối với giả định này.

Không nhất thiết phải dùng đúng mẫu trên: một lớp có thể định nghĩa copy constructor hoặc một phương thức `copy()`; và một override `clone()` cũng có thể dùng cách sao chép riêng mà không gọi `super.clone()`. Do đó, **`Cloneable` là tín hiệu dành cho cơ chế `Object.clone()`**, không phải quy tắc chung rằng mọi phương thức tên `clone` đều bắt buộc có marker.

## 3. Marker cho phép điều gì khi gọi `super.clone()`?

Cơ chế `Object.clone()` có các bước/đặc điểm đáng nhớ:

- Khi được gọi trên instance có kiểu runtime **không triển khai `Cloneable`**, implementation của `Object.clone()` ném `CloneNotSupportedException`.
- Khi điều kiện marker được đáp ứng, `Object.clone()` tạo đối tượng khác có **cùng lớp runtime** và sao chép nội dung trường hiện có theo phép gán; nó không lần lượt gọi constructor để khởi tạo lại các trường như tạo object bằng `new`.
- Trường kiểu nguyên thủy (`int`, `double`, `boolean`, …) nhận bản sao giá trị.
- Trường kiểu tham chiếu (`List`, mảng, đối tượng mutable, …) nhận **bản sao tham chiếu**. Hai object khác nhau có thể vẫn cùng trỏ đến một object con.
- Đây là **shallow copy** (*sao chép nông*). Nó không tự sao chép đệ quy toàn bộ cấu trúc đối tượng.

Chẳng hạn sau khi `super.clone()` thực hiện, object nguồn và object bản sao có thể là hai `Bag` khác nhau nhưng trường `items` đều trỏ tới **cùng một `ArrayList`**. Nếu một bên sửa list đó, bên kia quan sát được nội dung đã đổi.

### Nếu không có marker thì sao?

Ví dụ:

~~~java
final class NotMarked {
    @Override
    public NotMarked clone() throws CloneNotSupportedException {
        return (NotMarked) super.clone();
    }
}
~~~

Đây là lớp minh họa độc lập với mẫu `Account`. Nó **có public `clone()`** và override đúng `Object.clone()`, nhưng không `implements Cloneable`. Vì phương thức ủy quyền cho `super.clone()`, lời gọi sẽ ném `CloneNotSupportedException` trên một instance `NotMarked`.

Điều này cho thấy **override phương thức** và **đặt marker** là hai việc khác nhau: với cách cài đặt dựa trên `Object.clone()`, cần cả quyền truy cập phù hợp lẫn điều kiện marker.

Phân biệt thêm: nếu lớp tự viết `clone()` bằng `new NotMarked(...)` mà **không gọi `Object.clone()`**, nó có thể tự tạo bản sao mà không cần marker. Vì vậy câu “không implements `Cloneable` thì không bao giờ có thể có phương thức sao chép” là khẳng định quá rộng. Điều được `Object` quy định là hành vi của **chính `Object.clone()`**.

## 4. Ví dụ Java 17 chạy được: marker, protected, checked exception và shallow copy

Tạo tệp **`CloneableMarkerDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public class CloneableMarkerDemo {

    // Có marker nhưng không công khai clone().
    static final class MarkerOnly implements Cloneable {
        private final int value = 7;
    }

    // Công khai clone() nhưng không có marker:
    // super.clone() sẽ ném CloneNotSupportedException.
    static final class NotMarked {
        @Override
        public NotMarked clone() throws CloneNotSupportedException {
            return (NotMarked) super.clone();
        }
    }

    // Trường nguyên thủy: shallow copy đủ cho ví dụ này.
    static final class Point implements Cloneable {
        private final int x;

        Point(int x) {
            this.x = x;
        }

        @Override
        public Point clone() {
            try {
                return (Point) super.clone();
            } catch (CloneNotSupportedException e) {
                throw new AssertionError(e);
            }
        }
    }

    // Trường tham chiếu là danh sách mutable.
    static final class Bag implements Cloneable {
        private final List<String> items;

        Bag(List<String> input) {
            this.items = new ArrayList<>(input);
        }

        @Override
        public Bag clone() {
            try {
                return (Bag) super.clone(); // Sao chép nông.
            } catch (CloneNotSupportedException e) {
                throw new AssertionError(e);
            }
        }

        Bag copyWithSeparateList() {
            return new Bag(items); // Tạo danh sách riêng bằng constructor.
        }
    }

    public static void main(String[] args) {
        MarkerOnly marker = new MarkerOnly();
        System.out.println("marker present: "
                + (marker instanceof Cloneable));
        System.out.println("Cloneable declared methods: "
                + Cloneable.class.getDeclaredMethods().length);

        try {
            new NotMarked().clone();
        } catch (CloneNotSupportedException e) {
            System.out.println("not marked: "
                    + e.getClass().getSimpleName());
        }

        Point point = new Point(7);
        Point pointCopy = point.clone();
        System.out.println("point distinct: " + (point != pointCopy));
        System.out.println("point x equal: " + (point.x == pointCopy.x));
        System.out.println("point equals copy: " + point.equals(pointCopy));

        Bag original = new Bag(List.of("A"));
        Bag shallow = original.clone();
        Bag separate = original.copyWithSeparateList();

        System.out.println("shallow distinct bag: "
                + (original != shallow));
        System.out.println("shallow shares list: "
                + (original.items == shallow.items));
        System.out.println("separate shares list: "
                + (original.items == separate.items));

        original.items.add("B");
        System.out.println("shallow items: " + shallow.items);
        System.out.println("separate items: " + separate.items);

        int[] numbers = {1, 2};
        int[] numbersCopy = numbers.clone();
        System.out.println("array distinct: " + (numbers != numbersCopy));
        System.out.println("array same contents: "
                + Arrays.equals(numbers, numbersCopy));

        int[][] matrix = {{1, 2}};
        int[][] matrixCopy = matrix.clone();
        System.out.println("inner array shared: "
                + (matrix[0] == matrixCopy[0]));
    }
}
~~~

Biên dịch/chạy trong thư mục chứa tệp (JDK 17 trở lên):

~~~bash
javac CloneableMarkerDemo.java
java CloneableMarkerDemo
~~~

**Đầu ra dự kiến:**

~~~text
marker present: true
Cloneable declared methods: 0
not marked: CloneNotSupportedException
point distinct: true
point x equal: true
point equals copy: false
shallow distinct bag: true
shallow shares list: true
separate shares list: false
shallow items: [A, B]
separate items: [A]
array distinct: true
array same contents: true
inner array shared: true
~~~

Diễn giải theo nhóm:

1. `MarkerOnly` triển khai marker, nhưng interface `Cloneable` có **0 phương thức được khai báo**. Chương trình không gọi `marker.clone()`, bởi `Object.clone()` vẫn là `protected` trong trường hợp này.
2. `NotMarked` có override public nhưng gọi `super.clone()` khi thiếu marker, nên nhận checked exception `CloneNotSupportedException`.
3. `Point.clone()` dùng `super.clone()` để tạo instance mới. Hai `x` bằng nhau vì kiểu nguyên thủy được sao chép theo giá trị. Nhưng `point.equals(pointCopy)` là `false`, vì lớp `Point` **không override `equals()`**, nên kế thừa equality theo identity từ `Object`.
4. `Bag.clone()` tạo đối tượng `Bag` khác nhưng **cùng `items`** (shallow copy). Trong khi đó `copyWithSeparateList()` dùng constructor để tạo `ArrayList` khác. Khi sửa list nguồn, bản sao nông thấy `[A, B]` còn bản sao với list riêng giữ `[A]`.
5. `int[].clone()` tạo mảng một chiều khác có cùng các phần tử nguyên thủy. `int[][].clone()` chỉ tạo **mảng ngoài** khác; các mảng con bên trong vẫn được chia sẻ.

Trong ví dụ `Bag` chỉ chứa `String` (bất biến), nên sao chép riêng `ArrayList` đủ để cách ly thao tác thêm/xóa chuỗi. Nếu list chứa các đối tượng mutable, `new ArrayList<>(items)` vẫn chỉ sao chép **cấu trúc danh sách**, chưa sao chép bản thân từng phần tử.

## 5. Vì sao `Cloneable reference = ...` không có `clone()`?

Vì `Cloneable` rỗng, một biến được khai báo với kiểu tĩnh `Cloneable` không có phương thức `clone()` trong tập API của interface:

~~~java
Cloneable value = new Point(7);

// value.clone(); // Không biên dịch: Cloneable không khai báo clone().
~~~

Đây là đoạn minh họa dùng kiểu `Point` ở chương trình trước. Ngay cả khi instance runtime là `Point` đã có `public Point clone()`, **kiểu tĩnh** của biến `value` không cho phép gọi `value.clone()`. Có thể gọi `((Point) value).clone()` khi đã biết chắc kiểu runtime và thiết kế cho phép, nhưng không nên dựa vào cast như một cơ chế sao chép tổng quát.

Muốn thiết kế một API generic để client gọi sao chép mà không biết concrete class, hãy khai báo **một interface riêng có phương thức sao chép rõ ràng**:

~~~java
interface Copyable<T> {
    T copy();
}
~~~

Đây là interface minh họa. Các lớp triển khai tự quyết định ngữ nghĩa của `copy()` (sao chép nông, sao chép cấu trúc hay tạo đối tượng giá trị mới) và viết tài liệu rõ ràng. **Không** nhầm interface `Copyable<T>` tự tạo với `java.lang.Cloneable`.

## 6. Vai trò của `@Override`, kiểu trả về và ngoại lệ

Việc override chính xác quan trọng như với các phương thức khác của `Object`:

~~~java
@Override
public Point clone() {
    try {
        return (Point) super.clone();
    } catch (CloneNotSupportedException e) {
        throw new AssertionError(e);
    }
}
~~~

- `@Override` đảm bảo trình biên dịch nhận ra đây là ghi đè `Object.clone()`, không phải overload vô tình thêm tham số.
- `public` mở rộng phạm vi truy cập từ `protected`; một override không được thu hẹp quyền so với phương thức cha.
- `Point` là kiểu trả về hiệp biến tương thích với `Object`, giúp client không phải ép kiểu sau khi gọi `point.clone()`.
- Không khai báo checked exception trong override là hợp lệ: phương thức ghi đè được phép bỏ `throws CloneNotSupportedException`. Chỉ khi gọi `super.clone()` trong thân phương thức mới cần xử lý ngoại lệ được khai báo bởi phương thức gốc.
- `super.clone()` tạo shallow copy bằng cơ chế kế thừa; nó **không gọi `Point()`** để chạy lại logic khởi tạo thông thường.

Nếu một lớp **không phải `final`**, subclass và quy ước kế thừa cần được xem xét kỹ. `super.clone()` sử dụng kiểu runtime của instance và có thể sao chép trường của subclass theo cùng quy tắc nông. Một subclass chứa tài nguyên mutable hoặc bất biến nghiệp vụ phức tạp có thể cần sửa cấu trúc con sau khi sao chép. Không nên mở rộng khả năng clone tùy tiện trong một hệ phân cấp mà chưa thiết kế rõ ai chịu trách nhiệm sao chép từng tầng.

## 7. Sao chép nông, sao chép sâu và lựa chọn thay thế

| Cách làm | Cái gì được tạo mới? | Điều cần lưu ý |
| --- | --- | --- |
| `super.clone()` trên class hợp lệ | Instance bên ngoài và bản sao giá trị trường; reference field giữ nguyên tham chiếu | **Shallow copy**, có thể chia sẻ object con |
| `array.clone()` | Một mảng mới ở tầng ngoài | Mảng đa chiều vẫn chia sẻ các mảng con |
| `new ArrayList<>(oldList)` | Cấu trúc list mới | Phần tử object trong hai list có thể vẫn cùng tham chiếu |
| Copy constructor `new Type(original)` | Theo logic constructor do lập trình viên định nghĩa | Có thể chủ động sao chép sâu một số trường và giữ các trường bất biến |
| Static factory `Type.copyOf(original)` | Theo hợp đồng factory được định nghĩa | Tên `copyOf` không tự bảo đảm bản sao luôn khác instance |
| Thiết kế object immutable | Có thể chia sẻ an toàn trạng thái bất biến | Giảm nhu cầu clone; cần bảo đảm bất biến cả ở cấu trúc con |

**Deep copy** không phải một nút bật sẵn của `Cloneable`. Muốn sao chép sâu một object graph có mảng, list, map và đối tượng lồng nhau, phải xác định cách nhân bản từng thành phần cần tách riêng. Cần cân nhắc aliasing (hai đường trong object graph trỏ cùng object), cycle (tham chiếu vòng), tài nguyên ngoài JVM (socket/file handle), và bất biến nghiệp vụ. Việc làm sâu hoàn toàn đôi khi không khả thi hoặc không đúng mục tiêu.

Nếu kiểu dữ liệu chứa chủ yếu giá trị bất biến như `String`, `LocalDate` hoặc các record chứa toàn thành phần bất biến, **copy constructor/factory** thường dễ hiểu hơn `Cloneable`. Với object immutable, việc tạo bản sao riêng có thể không cần thiết vì hai bên có thể chia sẻ cùng dữ liệu bất biến một cách an toàn.

## 8. Những hiểu nhầm thường gặp

| Hiểu nhầm | Sự thật |
| --- | --- |
| “`implements Cloneable` tự cung cấp `public clone()`.” | `Cloneable` không khai báo phương thức; `Object.clone()` vốn là `protected` |
| “Interface `Cloneable` định nghĩa `clone()`.” | `clone()` được khai báo trong `Object` |
| “Cứ gọi `clone()` qua biến `Cloneable`.” | Kiểu tĩnh `Cloneable` không có API `clone()` |
| “Override `clone()` gọi `super.clone()` là đủ cho mọi lớp.” | Có thể phải sao chép riêng trạng thái mutable để tránh chia sẻ ngoài ý muốn |
| “Không implements `Cloneable` thì mọi phương thức tự viết tên `clone` đều thất bại.” | Chỉ cơ chế `Object.clone()` kiểm tra marker; cách sao chép thủ công có thể khác |
| “`clone()` luôn làm `clone.equals(original)` là `true`.” | Không bắt buộc; ví dụ `Point` mặc định so identity cho kết quả `false` |
| “Clone gọi lại constructor như `new`.” | `Object.clone()` sao chép trạng thái trường, không dùng constructor theo luồng khởi tạo thông thường |
| “`int[][]` được clone toàn bộ tới từng hàng.” | `matrix.clone()` chỉ nhân bản mảng ngoài |
| “Sao chép list là sao chép sâu mọi phần tử.” | `new ArrayList<>(...)` là bản sao cấu trúc list, phần tử mutable có thể dùng chung |

## 9. Tự kiểm tra kiến thức

1. **`Cloneable` khai báo bao nhiêu phương thức?** — Không có phương thức; đây là marker interface.
2. **Một class `implements Cloneable` nhưng không override `clone()` có chắc client bên ngoài gọi được không?** — Không. `Object.clone()` vẫn có quyền truy cập `protected`.
3. **Ai thực hiện sao chép trường nếu viết `return (Type) super.clone();`?** — Implementation của `Object.clone()`.
4. **Điều gì xảy ra nếu `super.clone()` được gọi trên runtime class không triển khai `Cloneable`?** — `CloneNotSupportedException`.
5. **Khi field là `List<String>`, `super.clone()` có tự tạo list mới không?** — Không; hai object chia sẻ tham chiếu list trừ khi override/cách sao chép tự sửa lại.
6. **Tại sao mảng `int[][]` vẫn chia sẻ hàng sau `clone()`?** — Vì mảng ngoài được copy nông, từng phần tử của nó là tham chiếu mảng con.
7. **Nếu cần một API sao chép dễ gọi, nên làm gì?** — Công khai phương thức/copy constructor/factory rõ hợp đồng, quyết định độ sâu sao chép theo dữ liệu; chỉ chọn `Cloneable`/`Object.clone()` khi hiểu rõ tính năng và giới hạn.

**Ghi nhớ:** `Cloneable` chỉ là **tín hiệu cho cơ chế của `Object.clone()`**. Nó không định nghĩa một phương thức trong interface, không tự làm `clone()` thành public và không tự cung cấp deep copy. Hãy phân biệt ba câu hỏi: **đối tượng có marker không?**, **client có quyền gọi phương thức sao chép nào?**, và **những phần dữ liệu nào thật sự được nhân bản?**

### Tài liệu gốc

- [Java SE 17 — Cloneable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Cloneable.html)
- [Java SE 17 — Object.clone()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html#clone())
- [Java Language Specification 17 — Array Members `10.7`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-10.html#jls-10.7)