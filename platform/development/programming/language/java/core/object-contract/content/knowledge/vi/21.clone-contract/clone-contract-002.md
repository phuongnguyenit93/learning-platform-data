# `Object.clone()` có quyền truy cập `protected` trong Java

`clone()` là phương thức do `java.lang.Object` khai báo, nhưng khác với `equals()`, `hashCode()` và `toString()`, **`Object.clone()` có mức truy cập `protected`**, không phải `public`. Điều này ảnh hưởng trực tiếp đến việc lớp nào được phép gọi phương thức, cách xây dựng API sao chép cho người dùng bên ngoài và lý do một đối tượng `implements Cloneable` vẫn chưa chắc gọi được `.clone()` từ mã phía khách hàng.

Bài học giải thích **hai điều kiện độc lập**: *quyền truy cập khi biên dịch* và *khả năng clone khi chạy*. Cũng cần hiểu `Object.clone()` tạo bản sao nông, các mảng có quy tắc đặc biệt, và trong nhiều trường hợp **copy constructor** hoặc **factory method** dễ bảo trì hơn.

## 1. Chữ ký và ý nghĩa của `Object.clone()`

Trong API của `Object`, chữ ký tương đương:

```java
protected native Object clone()
        throws CloneNotSupportedException;
```

`native` là chi tiết khai báo của triển khai JDK phổ biến; trọng tâm hợp đồng ở đây là `protected`, kiểu trả về `Object` và checked exception `CloneNotSupportedException`.

Theo hợp đồng của `Object.clone()`:

- Nếu lớp của đối tượng thực thi **không triển khai `java.lang.Cloneable`**, lời gọi mặc định ném `CloneNotSupportedException`.
- Nếu đối tượng hỗ trợ cách clone mặc định, phương thức tạo một đối tượng mới cùng lớp runtime và sao chép giá trị các trường của đối tượng gốc. Các trường tham chiếu **vẫn trỏ tới cùng đối tượng được tham chiếu**: đó là **shallow copy (sao chép nông)**.
- Việc tạo bản sao này **không gọi constructor của lớp được clone** theo cách khởi tạo một instance mới bằng `new`.
- `Object.clone()` trả về `Object`. Một lớp ghi đè có thể dùng **covariant return type** để trả về kiểu cụ thể hơn, chẳng hạn `AccountKey clone()`.

Một số kỳ vọng thường gặp là `x.clone() != x`, `x.clone().getClass() == x.getClass()` và `x.clone().equals(x)`; nhưng đó không phải các định luật áp dụng được cho **mọi** triển khai clone tùy chỉnh. Phần quan trọng là kiểu có thể cung cấp hợp đồng sao chép cụ thể, và người dùng cần biết nó sao chép những gì.

`Object.clone()` khác `Object.equals()` ở hai khía cạnh: quyền truy cập (`protected` thay vì `public`) và checked exception. Nó cũng khác một copy constructor, vốn có chữ ký và chính sách sao chép do chính lớp thiết kế.

## 2. `protected` cho phép gọi `clone()` ở đâu?

Trong Java, thành viên `protected` có thể được truy cập từ **các lớp trong cùng package với lớp khai báo**, và từ **lớp con ở package khác**, nhưng trường hợp lớp con ở package khác còn chịu điều kiện về ngữ cảnh truy cập/kiểu biểu thức nhận.

`Object` được khai báo trong `java.lang`. Mã ứng dụng thường không thuộc `java.lang`, vì thế không thể tùy ý gọi phương thức `Object.clone()` trên một biến bất kỳ:

```java
Object obj = new Object();
// obj.clone(); // LỖI BIÊN DỊCH: clone() has protected access in Object.
```

Đây là **đoạn minh họa không chạy độc lập**; dòng lỗi được đặt trong comment để phân biệt với code Java hợp lệ. Việc mọi lớp Java đều kế thừa `Object` **không có nghĩa bất kỳ đoạn code nào cũng được gọi `clone()` trên mọi đối tượng**.

Trong một lớp con của `Object`, lời gọi `super.clone()` nằm **bên trong thân phương thức của chính lớp con** có thể hợp lệ về quyền truy cập:

```java
class Draft implements Cloneable {
    public Draft copy() throws CloneNotSupportedException {
        return (Draft) super.clone();
    }
}
```

Đây là **đoạn khai báo lớp**, có thể biên dịch khi đặt trong file Java phù hợp. Dòng `super.clone()` được phép gọi vì phương thức đang được viết trong lớp con; dấu `implements Cloneable` giúp việc clone mặc định có thể thành công lúc chạy.

### 2.1. Ghi đè thành `public` nếu muốn công khai thao tác clone

Ví dụ:

```java
final class Document implements Cloneable {
    @Override
    public Document clone() {
        try {
            return (Document) super.clone();
        } catch (CloneNotSupportedException ex) {
            throw new AssertionError(ex);
        }
    }
}
```

Đây là **mảnh khai báo**, chưa phải chương trình có `main`. `Document.clone()` được công bố `public`, nên mã khác có thể gọi phương thức trên biểu thức có kiểu tĩnh `Document`. Lớp được đánh dấu `Cloneable`, vì vậy với cấu trúc không thay đổi, việc `super.clone()` ném `CloneNotSupportedException` là tình huống bất thường và được chuyển thành `AssertionError`.

**Lưu ý quan trọng:** kiểm tra quyền truy cập ở thời điểm biên dịch dựa trên **kiểu tĩnh của biểu thức gọi**. Nếu viết:

```java
Document doc = new Document();
Document copy = doc.clone();  // Hợp lệ: Document.clone() public.

Object obj = doc;
// obj.clone();               // Không hợp lệ: Object.clone() protected.
Document copy2 = ((Document) obj).clone(); // Hợp lệ sau cast.
```

Cả ba dòng trên là **đoạn minh họa**; muốn chạy độc lập cần bao chúng trong `main` cùng khai báo `Document`. Dù `obj` trỏ tới `Document`, biến có kiểu tĩnh `Object` không làm cho `Object.clone()` thành công khai.

**Không thể giảm quyền khi override:** nếu một lớp cha đã công bố `public clone()`, lớp con ghi đè nó phải tiếp tục công bố `public`. Ngược lại, Java cho phép override phương thức `protected` thành `public`, như ví dụ trên.

### 2.2. Hai package và quy tắc truy cập dễ nhầm

Giả sử lớp `LibraryItem` nằm trong package `library`:

```java
// Tệp library/LibraryItem.java
package library;

public class LibraryItem implements Cloneable {
    @Override
    protected LibraryItem clone()
            throws CloneNotSupportedException {
        return (LibraryItem) super.clone();
    }
}
```

Còn mã gọi nằm trong package `app`:

```java
// Tệp app/UseItem.java
package app;
import library.LibraryItem;

public class UseItem {
    public static void main(String[] args) throws Exception {
        LibraryItem item = new LibraryItem();
        // item.clone(); // LỖI: protected, khác package.
    }
}
```

Đây là **hai file minh họa theo đúng đường dẫn**, trong đó lệnh gây lỗi được comment. Từ `app`, dù `LibraryItem` triển khai `Cloneable`, lời gọi `item.clone()` vẫn không hợp lệ do `clone()` chỉ `protected`.

Một lớp con của `LibraryItem` ở package `app` có thể gọi `super.clone()` **trong chính phương thức của lớp con**. Tuy nhiên, không nên suy rộng quyền truy cập đó thành việc gọi `clone()` tùy ý trên một biến `LibraryItem` khác ở cùng package `app`. Với protected member có khai báo gốc ở package khác, Java giới hạn cách truy cập qua biểu thức nhận, ngoài việc lớp gọi phải là subclass phù hợp.

Với public API cần sao chép, giải pháp thông dụng là **công bố một phương thức `public` rõ ràng** trên kiểu hoặc dùng copy constructor/factory thay vì buộc mã khách hàng dựa vào quy tắc protected.

## 3. `Cloneable` không khai báo phương thức `clone()`

`java.lang.Cloneable` là **marker interface**: nó không có phương thức `clone()` để gọi. Nó thông báo cho `Object.clone()` rằng đối tượng cho phép thao tác clone mặc định.

Phân biệt:

| Câu hỏi | Cơ chế quyết định |
| --- | --- |
| Có gọi được `x.clone()` từ vị trí mã nguồn này không? | **Quy tắc quyền truy cập của Java**, kiểu tĩnh của `x`, phương thức đã được override công khai chưa |
| `super.clone()` có ném `CloneNotSupportedException` không? | Đối tượng runtime có triển khai `Cloneable` (hoặc lớp có phương thức clone tùy chỉnh với hợp đồng khác) |
| Giá trị được sao chép thế nào? | Hợp đồng `Object.clone()` là **shallow copy**; lớp ghi đè có thể chủ động sao chép thêm |
| Bản sao trả về có kiểu khai báo gì? | Kiểu trả về của phương thức clone có thể là `Object` hoặc kiểu cụ thể hơn qua covariant return |

Chỉ viết:

```java
class MarkerOnly implements Cloneable {
    private int value;
}
```

không tạo ra một **public `clone()`**. Mã khác package không thể viết `new MarkerOnly().clone()` chỉ nhờ `implements Cloneable`. Interface `Cloneable` không có phương thức nào tên `clone()` để bảo đảm giao diện gọi công khai.

Ngược lại, một lớp có thể tự viết `public T copy()` sử dụng constructor để tạo bản sao mà **không** triển khai `Cloneable`. Vì vậy cần tránh đánh đồng “có API sao chép” và “cho phép `Object.clone()`”.

## 4. Chương trình Java 17+ phân biệt quyền truy cập và khả năng clone khi chạy

Tạo file **`CloneAccessDemo.java`**:

```java
public class CloneAccessDemo {
    static final class WithoutMarker {
        private final int id;

        WithoutMarker(int id) {
            this.id = id;
        }

        WithoutMarker copyUsingSuper()
                throws CloneNotSupportedException {
            return (WithoutMarker) super.clone();
        }
    }

    static final class WithMarker implements Cloneable {
        private final int id;

        WithMarker(int id) {
            this.id = id;
        }

        @Override
        public WithMarker clone() {
            try {
                return (WithMarker) super.clone();
            } catch (CloneNotSupportedException ex) {
                throw new AssertionError(ex);
            }
        }

        int id() {
            return id;
        }
    }

    public static void main(String[] args) {
        WithoutMarker a = new WithoutMarker(7);
        try {
            a.copyUsingSuper();
            System.out.println("unexpected success");
        } catch (CloneNotSupportedException ex) {
            System.out.println("without marker: not supported");
        }

        WithMarker original = new WithMarker(42);
        WithMarker copy = original.clone();

        System.out.println("same instance: "
                + (original == copy));
        System.out.println("same id: "
                + (original.id() == copy.id()));
        System.out.println("copy class: "
                + copy.getClass().getSimpleName());
    }
}
```

Biên dịch và chạy:

```bash
javac CloneAccessDemo.java
java CloneAccessDemo
```

Stdout:

```text
without marker: not supported
same instance: false
same id: true
copy class: WithMarker
```

**Giải thích:**

1. `WithoutMarker.copyUsingSuper()` nằm bên trong lớp con của `Object`, nên `super.clone()` **hợp lệ lúc biên dịch**, nhưng instance **không triển khai `Cloneable`**, vì vậy `Object.clone()` ném `CloneNotSupportedException`.
2. `WithMarker` triển khai `Cloneable` và ghi đè `clone()` thành `public`: mã ở `main` gọi được, kết quả là instance khác nhưng giữ lại trường `id`.
3. Kiểu trả về là `WithMarker`, không phải `Object`, nhờ **covariant return type**, nên caller không cần cast.
4. Dùng `getSimpleName()` để trình bày kiểu kết quả; đây không phải bằng chứng độc lập rằng bản sao đã sao chép sâu các trường tham chiếu.

Mã trên giải quyết **hai vấn đề khác nhau**: quyền gọi được mở rộng bằng override `public`; khả năng `super.clone()` hoạt động nhờ marker `Cloneable`.

## 5. `Object.clone()` thực hiện shallow copy

Khi mặc định sao chép các trường, biến nguyên thủy được sao chép **giá trị**; còn trường kiểu tham chiếu được sao chép **tham chiếu**. Điều này dẫn đến hiện tượng bản gốc và bản clone cùng giữ một đối tượng con mutable.

Tạo file **`ShallowCloneDemo.java`**:

```java
public class ShallowCloneDemo {
    static final class Report implements Cloneable {
        private final String name;
        private int[] scores;

        Report(String name, int[] scores) {
            this.name = name;
            this.scores = scores;
        }

        @Override
        public Report clone() {
            try {
                return (Report) super.clone();
            } catch (CloneNotSupportedException ex) {
                throw new AssertionError(ex);
            }
        }

        int[] scores() {
            return scores;
        }
    }

    public static void main(String[] args) {
        Report first = new Report("Q1", new int[] {2, 4});
        Report second = first.clone();

        System.out.println("same report: "
                + (first == second));
        System.out.println("same scores array: "
                + (first.scores() == second.scores()));

        second.scores()[0] = 9;
        System.out.println("first score: "
                + first.scores()[0]);

        int[][] grid = {{1, 2}, {3}};
        int[][] gridCopy = grid.clone();

        System.out.println("same outer array: "
                + (grid == gridCopy));
        System.out.println("same inner row: "
                + (grid[0] == gridCopy[0]));
    }
}
```

Chạy:

```bash
javac ShallowCloneDemo.java
java ShallowCloneDemo
```

Kết quả:

```text
same report: false
same scores array: true
first score: 9
same outer array: false
same inner row: true
```

`Report.clone()` tạo đối tượng `Report` mới, nhưng `scores` của cả hai instance cùng trỏ tới **một mảng `int[]`**. Vì vậy thay đổi mảng qua `second` được nhìn thấy qua `first`.

**Điểm đặc biệt về mảng:** mảng Java cung cấp thao tác `clone()` **công khai** dù `Object.clone()` là `protected`; bản sao là mảng mới cùng loại runtime. Mảng nguyên thủy một chiều sao chép các giá trị nguyên thủy nên độc lập về nội dung phần tử. Nhưng `int[][]` là mảng gồm các phần tử `int[]`: `grid.clone()` chỉ sao chép mảng ngoài, **các hàng vẫn là tham chiếu chung**. Mảng cũng triển khai `Cloneable` và `Serializable`; không cần tự viết override.

Lưu ý rằng ví dụ `Report` cố ý để lộ mảng mutable qua `scores()` để chứng minh shallow copy. Đây không phải thiết kế đóng gói dữ liệu được khuyến nghị cho mọi ứng dụng.

## 6. Nếu cần tách dữ liệu mutable, clone phải có chính sách sao chép rõ ràng

Một lớp chứa mảng mutable có thể ghi đè `clone()` để clone mảng con sau khi gọi `super.clone()`. Tạo file **`IndependentCloneDemo.java`**:

```java
public class IndependentCloneDemo {
    static final class ScoreCard implements Cloneable {
        private int[] scores;

        ScoreCard(int[] input) {
            scores = input.clone();
        }

        int get(int index) {
            return scores[index];
        }

        void set(int index, int value) {
            scores[index] = value;
        }

        @Override
        public ScoreCard clone() {
            try {
                ScoreCard copy = (ScoreCard) super.clone();
                copy.scores = scores.clone();
                return copy;
            } catch (CloneNotSupportedException ex) {
                throw new AssertionError(ex);
            }
        }
    }

    public static void main(String[] args) {
        ScoreCard original = new ScoreCard(new int[] {2, 4});
        ScoreCard copied = original.clone();

        copied.set(0, 99);
        System.out.println("original score: " + original.get(0));
        System.out.println("copied score: " + copied.get(0));
        System.out.println("same instance: "
                + (original == copied));
    }
}
```

Lệnh:

```bash
javac IndependentCloneDemo.java
java IndependentCloneDemo
```

Stdout:

```text
original score: 2
copied score: 99
same instance: false
```

Ở đây lớp sao chép mảng đầu vào để tránh chia sẻ ngoài ý muốn, sau đó `clone()` sao chép thêm mảng `scores`. Bản clone và bản gốc có thể được chỉnh sửa độc lập.

**Những giới hạn cần hiểu:**

- Với mảng chứa **đối tượng mutable**, gọi `array.clone()` chỉ tách mảng ngoài, các phần tử vẫn là cùng tham chiếu. Muốn deep copy phải xác định cách sao chép **từng phần tử** phù hợp với ngữ nghĩa nghiệp vụ.
- Với trường tham chiếu `final`, không thể gán lại nó thành bản sao riêng bên trong `clone()` như `copy.scores = ...` nếu `scores` là `final`. Cố ép thiết kế clone sâu vào một đối tượng bất biến phức tạp có thể không phù hợp; thường nên chọn copy constructor/factory.
- Đối với tài nguyên như lock, socket, thread, file handle hoặc kết nối cơ sở dữ liệu, **không được mặc nhiên sao chép tham chiếu** hay coi có thể nhân bản đối tượng. Cần định nghĩa chính sách sở hữu và vòng đời tài nguyên.
- Nếu đối tượng có invariant cần thiết lập trong constructor, `Object.clone()` không chạy constructor nên có thể không thích hợp để khởi tạo lại invariant đó.

Phân biệt **sao chép sâu** và **bất biến**: một value object chỉ tham chiếu tới các thành phần thực sự bất biến có thể sử dụng shallow copy mà vẫn an toàn về ngữ nghĩa, vì các thành phần chia sẻ không thể bị sửa. Không nhất thiết phải deep copy mọi trường.

## 7. Checked exception và chữ ký khi override

`Object.clone()` khai báo `throws CloneNotSupportedException`. Lớp con khi ghi đè có ba lựa chọn phổ biến:

1. **Giữ checked exception** nếu muốn cho người gọi xử lý trường hợp không thể clone.
2. **Không khai báo checked exception** khi class đã chủ động triển khai `Cloneable`, `super.clone()` được kỳ vọng luôn thành công theo thiết kế hiện tại; bắt và chuyển thành `AssertionError` như ví dụ.
3. **Không sử dụng `Object.clone()`** và công bố một thao tác sao chép khác (`copy()` hoặc copy constructor), tùy ý định API.

Một override không thể mở rộng tập checked exception so với phương thức cha; có thể thu hẹp hoặc bỏ khai báo checked exception. `@Override` giúp trình biên dịch xác nhận đúng chữ ký. **Ném `CloneNotSupportedException` là cơ chế của `Object.clone()`**, không phải lỗi quyền truy cập protected: lỗi truy cập thường bị phát hiện **ngay lúc biên dịch**.

Trong một hệ phân cấp thừa kế, `super.clone()` gọi triển khai clone của lớp cha gần nhất; nếu lớp cha ghi đè clone và thêm hành vi thì kết quả phụ thuộc hợp đồng đó. Việc subclass cần clone đúng còn phụ thuộc cấu trúc trường và invariant của từng lớp trên chuỗi thừa kế.

## 8. Khi nào nên dùng copy constructor hoặc `copy()`?

`Cloneable`/`Object.clone()` có một số điểm gây khó dùng:

- Interface `Cloneable` không cung cấp một phương thức `public clone()` trong contract của nó.
- `Object.clone()` là `protected`, cần override hoặc phương thức công khai khác để người gọi bên ngoài dùng.
- Clone mặc định là shallow; với dữ liệu lồng, cần tự định nghĩa độ sâu và xử lý tài nguyên.
- `Object.clone()` không gọi constructor theo cách tạo instance bình thường, có thể xung đột với bất biến và chính sách khởi tạo.
- Một hệ phân cấp có cả class mutable/final fields có thể khó định nghĩa nhất quán cách clone mở rộng.

Một copy constructor giúp chủ động chọn trường nào được sao chép, cách tạo dữ liệu mới, cách kiểm tra invariant và cách đặt tên:

```java
final class Labels {
    private final String[] values;

    Labels(String[] input) {
        values = input.clone();
    }

    Labels(Labels other) {
        this(other.values);
    }

    String[] valuesCopy() {
        return values.clone();
    }
}
```

Đây là **mảnh khai báo lớp**, không phải chương trình có `main`. Đầu vào được giả định khác `null`; nếu API cho phép null cần thêm kiểm tra hoặc chính sách chuẩn hóa. Với mảng `String[]` (các phần tử `String` bất biến), clone mảng đủ để tách khả năng thay đổi vị trí phần tử. Khi phần tử là đối tượng mutable, cần quy tắc sao chép tiếp.

Copy constructor có thể gọi constructor thường, xác thực invariant theo cùng một lộ trình. Tuy nhiên, copy constructor cũng không tự tạo deep copy nếu chỉ gán chung các tham chiếu; **độ sâu sao chép phải được thiết kế** ở bất kỳ API nào.

Nếu một đối tượng thực sự **bất biến**, việc trả lại chính instance trong một phương thức định nghĩa là lấy giá trị bất biến có thể là chính sách hợp lý, nhưng không nên giả sử đó là hành vi mặc định của `Object.clone()`.

## 9. Quy trình chọn API sao chép cho lớp mới

**Bước 1 — Xác định nhu cầu sao chép.** Người gọi có cần một instance khác hay chỉ cần một giá trị tương đương? Dữ liệu con có được phép chia sẻ không?

**Bước 2 — Xác định khả năng truy cập.** Mã gọi có ở package khác không? Nếu công bố API clone, override `public` và cân nhắc kiểu trả về cụ thể.

**Bước 3 — Chọn hỗ trợ `Cloneable` có chủ đích.** Đánh dấu `implements Cloneable` nếu lớp dự định gọi `Object.clone()`; chỉ có interface marker không đủ để công bố clone.

**Bước 4 — Chọn độ sâu sao chép.** Dữ liệu chỉ gồm primitive và immutable value có thể chấp nhận shallow; mảng/list/map mutable hoặc tài nguyên cần quyết định sao chép/chia sẻ/từ chối rõ ràng.

**Bước 5 — Kiểm tra invariant, lớp cha và subclass.** Mỗi lớp trên chuỗi thừa kế có thể có trạng thái cần xử lý. `final` fields, constructor và quyền truy cập clone cần được cân nhắc cùng nhau.

**Bước 6 — Kiểm tra ngoại lệ và hợp đồng public API.** Nếu không muốn người gọi xử lý checked exception, chỉ loại bỏ `throws CloneNotSupportedException` khi có phương án xử lý hợp lý trong override.

**Bước 7 — Đánh giá copy constructor hoặc factory.** Nếu clone đòi hỏi nhiều thao tác khởi tạo phức tạp, một phương thức sao chép có chủ đích thường dễ kiểm tra và bảo trì.

## 10. Những lỗi thường gặp

| Nhận định hoặc cách viết | Vấn đề | Cách làm phù hợp |
| --- | --- | --- |
| “Mọi object đều gọi được `.clone()`.” | `Object.clone()` là `protected` | Chỉ gọi theo quy tắc truy cập, hoặc cung cấp API `public` |
| “`implements Cloneable` tạo public `clone()`.” | `Cloneable` là marker interface, không khai báo phương thức | Override `public clone()` nếu cần |
| “`super.clone()` biên dịch được tức là chạy thành công.” | Chưa triển khai `Cloneable` có thể ném checked exception | Xác định cả quyền gọi và marker |
| “Gọi `obj.clone()` được vì runtime là lớp có public clone.” | Kiểu tĩnh `Object` khiến chỉ thấy `Object.clone()` protected | Dùng kiểu API thích hợp hoặc cast có kiểm soát |
| “Clone bản ghi có mảng là clone sâu.” | `Object.clone()` sao chép tham chiếu | Sao chép thành phần mutable khi cần |
| “Mảng hai chiều `clone()` sao chép mọi hàng.” | Chỉ sao chép mảng ngoài | Sao chép từng hàng nếu muốn độc lập |
| “Clone gọi constructor nên invariant tự khởi tạo lại.” | Object.clone không đi qua constructor bình thường | Chọn cơ chế sao chép cho phép xác thực invariant |
| “Dùng clone là tốt nhất cho mọi đối tượng.” | Khó xác định sâu/nông, vòng đời tài nguyên và thừa kế | Cân nhắc copy constructor/factory |
| “`CloneNotSupportedException` là lỗi protected.” | Đó là ngoại lệ runtime từ thao tác clone, không phải lỗi truy cập compile time | Phân biệt hai giai đoạn |
| “Sao chép `final` reference là bảo đảm độc lập.” | Object tham chiếu bên trong vẫn có thể mutable | Kiểm tra bất biến sâu hoặc copy có chủ đích |

## 11. Checklist code review

- [ ] Có phân biệt rõ **phạm vi truy cập `protected`** và **điều kiện `Cloneable`**?
- [ ] Người gọi ở package khác có truy cập được phương thức công khai dành cho việc sao chép?
- [ ] Override `clone()` có đúng chữ ký, kiểu trả về và mức truy cập không?
- [ ] `super.clone()` có được sử dụng ở nơi hợp lệ về mặt truy cập Java?
- [ ] Nếu `CloneNotSupportedException` có thể xảy ra, chính sách xử lý đã rõ?
- [ ] Độ sâu sao chép của từng trường primitive, mảng, collection, object mutable và tài nguyên đã được xác định?
- [ ] Với mảng nhiều chiều, các hàng có còn chia sẻ sau `clone()` không? Điều đó có đúng yêu cầu?
- [ ] Constructor/invariant, `final` fields và hợp đồng lớp cha có được tôn trọng?
- [ ] Có bài kiểm thử cho việc bản gốc và clone là hai instance khác nhau và cho các thay đổi độc lập khi cần?
- [ ] Có nên dùng `copy()` hoặc copy constructor để API rõ ràng hơn không?

**Ghi nhớ:** `Object.clone()` là **`protected`**, còn `Cloneable` chỉ là dấu hiệu hỗ trợ clone mặc định. Muốn người gọi bên ngoài thực hiện sao chép, lớp thường cần công bố API `public` với hợp đồng độ sâu và ngoại lệ rõ ràng. `super.clone()` chủ yếu tạo **shallow copy**; nếu dữ liệu chứa thành phần mutable, thiết kế phải quyết định chính xác phần nào được chia sẻ và phần nào được nhân bản.
