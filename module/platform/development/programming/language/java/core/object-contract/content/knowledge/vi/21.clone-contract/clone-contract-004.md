# `CloneNotSupportedException` khi `Object.clone()` không được phép

## Mục tiêu

Trong Java, `Object.clone()` là cơ chế hỗ trợ tạo bản sao đối tượng, nhưng không phải đối tượng Java nào cũng có thể được clone bằng cơ chế này. Nếu `Object.clone()` được gọi trên một instance của lớp **không triển khai `Cloneable`**, phương thức sẽ ném `CloneNotSupportedException`. Muốn xử lý đúng, bạn cần hiểu cả **điều kiện chạy** của cơ chế clone, **quyền truy cập phương thức** và **checked exception**.

Sau bài học, bạn sẽ:

- Giải thích được chính xác khi nào `Object.clone()` ném `CloneNotSupportedException`.
- Hiểu vì sao `Cloneable` là marker interface và không tự cung cấp phương thức `clone()` công khai.
- Viết được một lớp gọi `super.clone()` an toàn khi có `implements Cloneable`.
- Phân biệt lỗi biên dịch do `protected` hoặc checked exception với `CloneNotSupportedException` xảy ra khi chạy.
- Phân tích trường hợp lớp con, mảng, bản sao nông, và phương thức `clone()` ghi đè.
- Quyết định khi nào nên dùng constructor sao chép hay phương thức `copy()` thay cho `Object.clone()`.

## 1. `Object.clone()` và điều kiện được phép tạo bản sao

Tất cả lớp Java thông thường kế thừa `java.lang.Object` trực tiếp hoặc gián tiếp. `Object` khai báo:

```java
protected Object clone() throws CloneNotSupportedException
```

Có ba yếu tố quan trọng:

1. **`protected`**: phương thức `clone()` mặc định không được gọi tùy ý trên bất kỳ đối tượng nào từ mã bên ngoài. Lớp có thể ghi đè để cung cấp API `public`.
2. **`throws CloneNotSupportedException`**: đây là **checked exception**. Mã gọi một phương thức có khai báo có thể ném exception này phải bắt nó hoặc khai báo tiếp bằng `throws`, trừ khi đã xử lý qua một API khác không khai báo exception.
3. **Điều kiện `Cloneable` ở thời điểm chạy**: khi triển khai `Object.clone()` thực sự được sử dụng cho một object không có marker `java.lang.Cloneable`, lời gọi thất bại bằng `CloneNotSupportedException`.

Điều kiện thứ ba áp dụng theo **lớp chạy thực tế của đối tượng** (runtime class). Nếu đối tượng kế thừa từ một lớp đã triển khai `Cloneable`, nó cũng là một `Cloneable` theo quan hệ kế thừa interface.

### Marker interface là gì?

`java.lang.Cloneable` là một **marker interface**, nghĩa là nó không định nghĩa phương thức nào. Viết:

```java
class Draft implements Cloneable {
    private int version;
}
```

giúp instance của `Draft` đáp ứng dấu hiệu mà `Object.clone()` nhận biết. Nhưng chỉ riêng dòng `implements Cloneable` **không tạo ra một phương thức `public clone()` trong lớp**. `clone()` vẫn là phương thức `protected` kế thừa từ `Object` nếu lớp không ghi đè.

Điều này phân biệt hai câu hỏi:

- **Có đủ điều kiện về marker để `Object.clone()` hỗ trợ sao chép?** Có nếu runtime object là `Cloneable`.
- **Mã gọi hiện tại có nhìn thấy một phương thức `clone()` để gọi không?** Phụ thuộc phạm vi truy cập và cách lớp khai báo API.

Một đối tượng có marker `Cloneable` nhưng không mở API clone công khai có thể không gọi được `obj.clone()` từ mã client, dù bản thân đối tượng đủ điều kiện khi một phương thức hợp lệ trong lớp gọi `super.clone()`.

## 2. Vì sao `CloneNotSupportedException` được ném?

Ví dụ sau minh họa chính xác trường hợp thất bại: lớp `Plain` **không** triển khai `Cloneable` nhưng vẫn khai báo một phương thức `public clone()` và gọi `super.clone()`.

```java
class Plain {
    private final int id;

    Plain(int id) {
        this.id = id;
    }

    @Override
    public Plain clone() throws CloneNotSupportedException {
        return (Plain) super.clone();
    }
}
```

Mã trên có thể **biên dịch hợp lệ**: lớp được phép ghi đè `Object.clone()` và gọi `super.clone()` từ bên trong phương thức instance của chính lớp. Tuy nhiên:

```java
Plain original = new Plain(7);
Plain copy = original.clone(); // Ném CloneNotSupportedException khi chạy
```

Đây là đoạn trong một phương thức có xử lý hoặc khai báo checked exception. Lúc gọi `super.clone()`, cơ chế trong `Object.clone()` kiểm tra object hiện tại và nhận thấy `Plain` không triển khai `Cloneable`. Vì thế exception được ném **trước khi nhận được bản sao**.

Phân biệt rõ: phương thức `clone()` được khai báo `public` ở đây **không phải** bằng chứng đối tượng clone được. Cách ghi đè chỉ mở quyền gọi; marker `Cloneable` mới là tín hiệu mà `Object.clone()` sử dụng.

### Exception có nghĩa gì?

`CloneNotSupportedException` là lớp exception trong `java.lang`, kế thừa `Exception` và thuộc nhóm checked exception. Nó biểu thị rằng một thao tác clone đã được yêu cầu nhưng không được hỗ trợ bởi cơ chế đang dùng.

Với `Object.clone()`, trường hợp chuẩn là lớp chạy thực tế của đối tượng không triển khai `Cloneable`. Tuy nhiên một lớp **tự ghi đè** `clone()` vẫn có thể chủ động ném exception vì chính sách riêng. Không nên xem mọi lần gặp exception cùng tên là bằng chứng duy nhất rằng class chắc chắn thiếu marker; cần kiểm tra stack trace và phương thức triển khai đang chạy.

## 3. Sửa trường hợp chuẩn: triển khai `Cloneable` và gọi `super.clone()`

Một mẫu clone truyền thống là:

```java
class CloneReady implements Cloneable {
    private final int id;

    CloneReady(int id) {
        this.id = id;
    }

    @Override
    public CloneReady clone() throws CloneNotSupportedException {
        return (CloneReady) super.clone();
    }
}
```

Trong trường hợp này:

- `implements Cloneable` cấp marker cho runtime object.
- `@Override public CloneReady clone()` mở API công khai và dùng **kiểu trả về hiệp biến** (`covariant return type`) thay vì `Object`.
- `super.clone()` dùng cơ chế sao chép của `Object`. Do instance là `Cloneable`, thao tác thông thường được cho phép.
- Ép kiểu `(CloneReady)` hợp lệ với bản sao của instance `CloneReady`; phương thức trả về đúng kiểu cho người gọi.

Một số lớp có thể xử lý `CloneNotSupportedException` ngay bên trong vì chúng biết marker luôn có mặt theo thiết kế. Nhưng nếu phương thức vẫn khai báo `throws` như ví dụ, mã client phải bắt hoặc khai báo exception tương ứng.

**Giới hạn:** `super.clone()` thực hiện bản sao **nông** (shallow copy) đối với các trường tham chiếu: đối tượng gốc và bản sao có hai identity khác nhau nhưng một số trường có thể cùng trỏ đến các đối tượng con. Marker `Cloneable` không tự sinh “deep copy”.

## 4. Chương trình Java 17+ hoàn chỉnh: clone thất bại, clone thành công và copy thủ công

Lưu tệp sau dưới tên `ClonePermissionDemo.java`:

```java
import java.util.Arrays;

public class ClonePermissionDemo {
    static final class Plain {
        private final int id;

        Plain(int id) {
            this.id = id;
        }

        @Override
        public Plain clone() throws CloneNotSupportedException {
            return (Plain) super.clone();
        }
    }

    static class CloneReady implements Cloneable {
        private final int id;
        private final int[] scores;

        CloneReady(int id, int[] scores) {
            this.id = id;
            this.scores = scores;
        }

        @Override
        public CloneReady clone() throws CloneNotSupportedException {
            return (CloneReady) super.clone();
        }

        int id() {
            return id;
        }

        int[] scores() {
            return scores;
        }
    }

    static final class Child extends CloneReady {
        Child(int id, int[] scores) {
            super(id, scores);
        }
    }

    static final class ManualCopy {
        private final int id;

        ManualCopy(int id) {
            this.id = id;
        }

        ManualCopy copy() {
            return new ManualCopy(id);
        }

        int id() {
            return id;
        }
    }

    public static void main(String[] args) throws CloneNotSupportedException {
        Plain plain = new Plain(7);
        try {
            plain.clone();
            System.out.println("unexpected success");
        } catch (CloneNotSupportedException ex) {
            System.out.println("plain rejected: "
                    + ex.getClass().getSimpleName());
        }

        CloneReady original = new CloneReady(11, new int[] {2, 3});
        CloneReady copy = original.clone();
        System.out.println("different instances: " + (original != copy));
        System.out.println("copied id: " + copy.id());
        System.out.println("same scores array: "
                + (original.scores() == copy.scores()));

        original.scores()[0] = 99;
        System.out.println("copy sees changed score: "
                + copy.scores()[0]);

        Child child = new Child(12, new int[] {4});
        CloneReady clonedChild = child.clone();
        System.out.println("child clone retains type: "
                + (clonedChild instanceof Child));

        int[] numbers = {5, 6};
        int[] numbersCopy = numbers.clone();
        System.out.println("array clone: "
                + (numbers != numbersCopy));
        System.out.println("array contents: "
                + Arrays.equals(numbers, numbersCopy));

        ManualCopy manual = new ManualCopy(15);
        ManualCopy manualCopy = manual.copy();
        System.out.println("manual copy works: "
                + (manual != manualCopy
                   && manual.id() == manualCopy.id()));
    }
}
```

Lệnh biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac ClonePermissionDemo.java
java ClonePermissionDemo
```

Đầu ra dự kiến:

```text
plain rejected: CloneNotSupportedException
different instances: true
copied id: 11
same scores array: true
copy sees changed score: 99
child clone retains type: true
array clone: true
array contents: true
manual copy works: true
```

### Phân tích từng kết quả

- `Plain.clone()` gọi `Object.clone()` khi instance không triển khai `Cloneable`; exception được bắt để chương trình có thể tiếp tục.
- `CloneReady` triển khai marker và có một phương thức clone hợp lệ. `original != copy` là `true` vì bản sao là một instance mới.
- `id` là `int`, nên giá trị 11 được sao chép vào đối tượng mới.
- `scores` là `int[]`; `Object.clone()` sao chép **tham chiếu** đến mảng con. Hai instance cùng giữ một mảng. Khi sửa `original.scores()[0]`, đọc từ `copy.scores()[0]` cũng thấy 99.
- `Child` kế thừa từ `CloneReady`, nên runtime object `Child` cũng triển khai `Cloneable`. `super.clone()` tạo bản sao giữ đúng lớp chạy thực tế `Child`, dù phương thức có kiểu trả về khai báo là `CloneReady`.
- Mảng Java có cơ chế `clone()` được hỗ trợ sẵn; `numbers.clone()` tạo một mảng riêng với cùng phần tử nguyên thủy.
- `ManualCopy` dùng constructor để tạo một object mới. Nó không cần `implements Cloneable` vì **không sử dụng `Object.clone()`**.

Chú ý đây là ví dụ học cơ chế, không phải mô hình encapsulation an toàn cho dữ liệu mutable: `CloneReady.scores()` trả trực tiếp tham chiếu mảng. Nếu mục tiêu là bản sao độc lập, cần có chính sách sao chép mảng/đối tượng con rõ ràng.

## 5. Ba trường hợp dễ nhầm: lỗi biên dịch, checked exception và exception lúc chạy

Không phải tình huống nào có chữ `clone` cũng dẫn đến `CloneNotSupportedException` ở runtime.

| Tình huống | Kết quả điển hình | Nguyên nhân |
| --- | --- | --- |
| Gọi `new Plain(1).clone()`, trong đó `Plain` có `public clone()` gọi `super.clone()` nhưng không có `Cloneable` | Ném `CloneNotSupportedException` khi chạy | `Object.clone()` từ chối runtime object |
| Lớp chỉ `implements Cloneable`, không mở `public clone()`, mã client gọi `instance.clone()` | Lỗi biên dịch do quyền truy cập | `Object.clone()` vẫn `protected` |
| Có `public clone() throws CloneNotSupportedException` nhưng người gọi không bắt hoặc khai báo | Lỗi biên dịch về checked exception | Java kiểm tra khai báo `throws` |
| Lớp `implements Cloneable` và gọi `super.clone()` hợp lệ | Tạo object mới | Marker thỏa điều kiện của `Object.clone()` |
| Lớp dùng `new` trong `copy()`, không gọi `Object.clone()` | Tạo object mới | Không phụ thuộc marker clone |
| Một mảng gọi `array.clone()` | Clone được hỗ trợ | Mảng Java hỗ trợ clone theo cơ chế ngôn ngữ |

### Lỗi `protected` khác exception hỗ trợ clone

```java
class MarkerOnly implements Cloneable {
    private int value;
}

class Example {
    void demo() {
        MarkerOnly x = new MarkerOnly();
        // x.clone(); // KHÔNG biên dịch: Object.clone() là protected
    }
}
```

Đoạn minh họa trên có hai lớp và chỉ dùng để chỉ ra quyền truy cập. `implements Cloneable` không tự chuyển `clone()` thành public.

### Checked exception phải được xử lý

```java
// Đặt trong một phương thức có thể gọi CloneReady.clone():
try {
    CloneReady cloned = original.clone();
    // Sử dụng cloned tại đây.
} catch (CloneNotSupportedException ex) {
    throw new IllegalStateException("Unexpected clone failure", ex);
}
```

Đây là snippet minh họa bên trong một phương thức, với `original` kiểu `CloneReady` và `CloneReady` được định nghĩa như ví dụ phần 4. Lớp có thể lựa chọn khai báo `throws CloneNotSupportedException` thay vì `try/catch` nếu contract API cho phép lỗi được xử lý ở cấp gọi phía trên.

**Không che giấu lỗi tùy tiện:** nếu exception thực sự có thể phát sinh vì thiết kế thiếu marker, bắt rồi trả về `null` sẽ chuyển lỗi thành một lỗi khác khó phát hiện hơn. Chọn cách xử lý phù hợp: sửa contract, thông báo lỗi, hoặc dùng cơ chế sao chép riêng.

## 6. `Cloneable` xét theo lớp chạy thực tế

Khi gọi `super.clone()`, kiểm tra marker không chỉ dựa trên tên biến tham chiếu. Nó liên quan đến đối tượng thực sự đang được sao chép.

Ví dụ, nếu `Base implements Cloneable` và `Derived extends Base`, instance `Derived` vẫn là một `Cloneable` ngay cả khi khai báo lớp con không nhắc lại tên interface. Ngược lại, nếu `Base` không triển khai `Cloneable`, nhưng `Derived` **có** triển khai, lời gọi `Object.clone()` từ một phương thức được kế thừa khi thực hiện trên instance `Derived` có thể được phép.

Minh họa:

```java
class Base {
    @Override
    public Base clone() throws CloneNotSupportedException {
        return (Base) super.clone();
    }
}

class Derived extends Base implements Cloneable {}

class Demo {
    static void check() throws CloneNotSupportedException {
        Base base = new Base();
        Derived derived = new Derived();

        // base.clone(); // Sẽ ném CloneNotSupportedException nếu được gọi
        Base copied = derived.clone(); // Thành công: runtime là Derived
        System.out.println(copied instanceof Derived); // true
    }
}
```

Đây là đoạn minh họa độc lập về lớp và phương thức `check()`; muốn chạy, cần một `main` gọi `Demo.check()`. Quy tắc thể hiện ở đây: **điều kiện Cloneable phụ thuộc runtime class**, không chỉ phụ thuộc lớp khai báo phương thức `clone()`.

Nó cũng cho thấy lời gọi `super.clone()` **không chỉ đơn giản tạo `new Base()`**. Khi được cho phép, đối tượng kết quả giữ đúng kiểu chạy thực tế.

## 7. Nếu đã triển khai `Cloneable`, có chắc mọi `clone()` đều thành công?

**Không có bảo đảm chung rằng mọi phương thức tên `clone()` ở mọi lớp đều thành công.** `Cloneable` là tín hiệu đặc biệt cho thao tác `Object.clone()`, nhưng một lớp có thể ghi đè `clone()` và thực hiện logic khác, bao gồm việc từ chối clone theo chính sách riêng.

Ví dụ một lớp có thể quyết định không hỗ trợ sao chép ở API công khai:

```java
class ForbiddenCopy implements Cloneable {
    @Override
    public ForbiddenCopy clone() throws CloneNotSupportedException {
        throw new CloneNotSupportedException("Copy forbidden by policy");
    }
}
```

Khi gọi `new ForbiddenCopy().clone()`, exception vẫn xảy ra **dù lớp triển khai `Cloneable`**, vì phương thức ghi đè chủ động ném ngoại lệ và không gọi `Object.clone()`. Đó là chính sách của lớp, khác với kiểm tra marker của `Object.clone()`.

Một số thư viện cũng cung cấp phương thức `clone()` tự cài đặt mà không gọi `super.clone()`. Khi đó marker `Cloneable` không phải yếu tố quyết định toàn bộ hành vi. Muốn kết luận nguyên nhân lỗi, đọc implementation và stack trace của phương thức thực sự được gọi.

## 8. Clone nông là điều kiện cần hiểu trước khi đưa vào ứng dụng

Ngay cả khi `Object.clone()` chạy thành công, kết quả không tự động là **bản sao sâu** (deep copy). Theo cơ chế mặc định, các trường nguyên thủy được sao chép giá trị; các trường tham chiếu được sao chép **tham chiếu**, không clone đệ quy từng đối tượng con.

```text
Bản gốc CloneReady          Bản sao CloneReady
  id = 11                      id = 11
  scores ──────┐               scores ──────┐
               │                           │
               └────► int[] {2, 3} ◄───────┘

Hai CloneReady khác nhau; mảng scores chỉ có một.
```

Đây là lý do ví dụ phần 4 in:

```text
same scores array: true
copy sees changed score: 99
```

Khi cần bản sao độc lập, lớp có thể triển khai sau `super.clone()` hoặc dùng constructor copy để tạo bản sao các trường mutable. Ví dụ phương pháp sau thường dễ đọc khi các trường có cấu trúc đơn giản:

```java
final class DataSnapshot {
    private final int[] values;

    DataSnapshot(int[] values) {
        this.values = values.clone();
    }

    DataSnapshot copy() {
        return new DataSnapshot(values);
    }

    int[] values() {
        return values.clone();
    }
}
```

Đoạn này minh họa một lớp không dùng `Object.clone()`: constructor và accessor sao chép mảng để tránh chia sẻ mảng mutable ra ngoài. Với một đồ thị chứa các đối tượng phức tạp hoặc chu trình tham chiếu, chính sách sao chép sâu cần được thiết kế riêng.

### Tại sao array `clone()` không ném `CloneNotSupportedException`?

Mảng Java hỗ trợ clone và có phương thức `clone()` phù hợp do ngôn ngữ cung cấp. Mảng là `Cloneable`, nên `array.clone()` tạo một mảng mới. Phần tử kiểu nguyên thủy được sao chép giá trị; với mảng đối tượng, tham chiếu phần tử được sao chép, vì thế bản sao vẫn là sao chép nông ở mức phần tử tham chiếu.

```java
StringBuilder[] builders = {new StringBuilder("A")};
StringBuilder[] copied = builders.clone();

System.out.println(builders != copied);       // true
System.out.println(builders[0] == copied[0]); // true
```

Các dòng nằm trong một phương thức. Mảng ngoài được clone thành object mới, nhưng hai mảng cùng giữ tham chiếu đến một `StringBuilder`.

## 9. Thiết kế API sao chép khi không muốn phụ thuộc vào `Object.clone()`

`Cloneable` và `Object.clone()` là cơ chế có từ lâu trong Java, nhưng không phải lúc nào cũng là lựa chọn tốt nhất cho mô hình nghiệp vụ. Các phương án phổ biến khác:

**Copy constructor:**

```java
final class PointData {
    private final int x;
    private final int y;

    PointData(int x, int y) {
        this.x = x;
        this.y = y;
    }

    PointData(PointData source) {
        this(source.x, source.y);
    }
}
```

**Factory hoặc phương thức `copy()`** có tên rõ ràng:

```java
final class UserSettings {
    private final String theme;

    UserSettings(String theme) {
        this.theme = theme;
    }

    UserSettings copy() {
        return new UserSettings(theme);
    }
}
```

Hai đoạn trên là khai báo lớp độc lập làm ví dụ. Cả hai kỹ thuật hoạt động mà không cần `implements Cloneable`. Chúng cho phép constructor kiểm tra invariant, quyết định sao chép sâu/nông và thiết kế API rõ ràng cho người dùng.

Với một **record bất biến đúng nghĩa** chứa các giá trị bất biến, đôi khi không cần tạo bản sao: cùng dữ liệu đã có thể được dùng lại theo thiết kế. Nếu record chứa đối tượng con mutable như mảng, cần xem xét defensive copy riêng. Không nên cố dùng `Object.clone()` chỉ vì muốn “copy một thứ gì đó”.

Các phương án này không làm thay đổi nguyên nhân của `CloneNotSupportedException`: exception vẫn xảy ra nếu bạn thực sự gọi `Object.clone()` với đối tượng không đáp ứng điều kiện marker.

## 10. Lỗi thường gặp

1. **Quên `implements Cloneable` nhưng vẫn gọi `super.clone()`.** Lớp có thể biên dịch, nhưng `Object.clone()` sẽ ném `CloneNotSupportedException` khi runtime object không có marker.
2. **Nghĩ `implements Cloneable` tự tạo `public clone()`.** Không đúng; `Cloneable` không khai báo phương thức. Nếu không ghi đè, phương thức kế thừa từ `Object` vẫn `protected`.
3. **Nhầm lỗi access với exception hỗ trợ clone.** Một lời gọi bị chặn bởi `protected` thất bại ở giai đoạn biên dịch, không phải đợi chạy để ném `CloneNotSupportedException`.
4. **Không bắt hoặc khai báo checked exception.** Nếu signature `clone()` khai báo `throws CloneNotSupportedException`, người gọi phải xử lý theo quy tắc Java.
5. **Cho rằng một lớp con không tự viết `implements Cloneable` thì chắc chắn clone thất bại.** Marker được kế thừa qua phân cấp kiểu.
6. **Cho rằng phương thức `clone()` ghi đè không thể từ chối khi class là `Cloneable`.** Lớp có thể định nghĩa chính sách riêng và ném exception.
7. **Cho rằng clone thành công là deep copy.** `Object.clone()` sao chép nông; các tham chiếu đến object mutable có thể còn chia sẻ.
8. **Bắt lỗi rồi bỏ qua hoặc trả `null`.** Cách này che mất nguyên nhân và có thể gây `NullPointerException` về sau. Cần sửa contract hoặc xác định chiến lược xử lý rõ ràng.
9. **Dùng clone khi chỉ cần một object mới từ dữ liệu đã biết.** Copy constructor hoặc factory thường đơn giản hơn và tránh yêu cầu marker/checked exception.
10. **Cho rằng mọi method tên `clone()` đều gọi `Object.clone()`.** Hãy xem mã ghi đè; một method có thể tự tạo object mới hoặc từ chối mà không gọi `super.clone()`.

## 11. Bài tập tự kiểm tra

### Câu 1 — Dự đoán nguyên nhân

Cho đoạn:

```java
class Document {
    @Override
    public Document clone() throws CloneNotSupportedException {
        return (Document) super.clone();
    }
}
```

Khi gọi `new Document().clone()` trong một `try/catch` hợp lệ, kết quả là gì?

**Đáp án:** `CloneNotSupportedException` vì `Document` không triển khai `Cloneable` nhưng gọi tới `Object.clone()`.

### Câu 2 — Marker nhưng không có API public

```java
class Document implements Cloneable {
    private String text;
}
```

Mã client ở lớp không có quyền truy cập `protected` có gọi trực tiếp `document.clone()` được không?

**Đáp án:** Không. `Cloneable` không khai báo một phương thức `clone()` public. Cần lớp công khai API sao chép hoặc dùng phương thức khác do lớp cung cấp.

### Câu 3 — Lớp con

```java
class Parent implements Cloneable {
    @Override
    public Parent clone() throws CloneNotSupportedException {
        return (Parent) super.clone();
    }
}

class Child extends Parent {}
```

Nếu `Child child = new Child();`, việc gọi `Parent p = child.clone();` có thể thành công không, và `p instanceof Child` là gì?

**Đáp án:** Có, vì `Child` kế thừa marker `Cloneable` và phương thức clone public. `p instanceof Child` là `true` vì cơ chế `Object.clone()` sao chép đúng lớp runtime.

### Câu 4 — Sao chép theo chính sách riêng

Một lớp không muốn đối tượng mutable bị chia sẻ sau khi copy thì chỉ thêm `implements Cloneable` đã đủ chưa?

**Đáp án:** Chưa. Cần kiểm soát sao chép các trường tham chiếu mutable, dùng clone/copy constructor có defensive copy hoặc một cách tạo bản sao sâu được thiết kế cho cấu trúc dữ liệu cụ thể.

## Ghi nhớ

`CloneNotSupportedException` xảy ra trong trường hợp tiêu biểu khi **`Object.clone()` được yêu cầu sao chép một runtime object không triển khai `Cloneable`**. `Cloneable` là marker interface, không cung cấp sẵn `public clone()`; phương thức `Object.clone()` gốc là `protected` và khai báo checked exception. Muốn mở API clone theo cơ chế mặc định, lớp cần hỗ trợ marker và thường ghi đè `clone()` để gọi `super.clone()` hợp lệ. Sau khi clone thành công, hãy nhớ đó vẫn có thể là bản sao nông; khi cần chính sách sao chép rõ ràng, copy constructor hoặc `copy()` là phương án phù hợp.