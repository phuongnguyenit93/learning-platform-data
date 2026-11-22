# Ghi đè `clone()` thành `public` và dùng kiểu trả về cụ thể trong Java

## 1. Bối cảnh: `Object.clone()` không phải API sao chép công khai

Mọi class Java đều kế thừa `java.lang.Object`. `Object` khai báo phương thức:

```java
protected native Object clone() throws CloneNotSupportedException;
```

Đây là **chữ ký API minh họa**, không phải một phương thức người học cần tự định nghĩa. Có ba đặc điểm quan trọng:

- **`protected`**: phương thức `clone()` của `Object` không được gọi tùy ý từ mọi nơi. Mã ứng dụng bên ngoài không thể viết `someObject.clone()` chỉ vì biến có kiểu `Object`.
- **Kiểu trả về `Object`**: ở chữ ký gốc, muốn dùng kết quả như kiểu cụ thể cần ép kiểu. Java cho phép override bằng **kiểu trả về hiệp biến (covariant return type)** để tránh ép kiểu ở phía người gọi.
- **`throws CloneNotSupportedException`**: triển khai của `Object.clone()` kiểm tra đối tượng thực tế có thực hiện marker interface `Cloneable` hay không; nếu không, lời gọi có thể ném ngoại lệ checked này.

Bài học tập trung vào cách một lớp **tự công bố khả năng clone một cách tường minh**, thường bằng `implements Cloneable`, `public T clone()`, gọi `super.clone()` và xử lý trường tham chiếu có thể thay đổi khi cần.

Lưu ý: `Cloneable` chỉ là **marker interface**, không khai báo phương thức `clone()`. Việc viết `implements Cloneable` không tự làm `clone()` trở thành `public`. Đây là một hạn chế của thiết kế API clone truyền thống của Java; với mã mới, copy constructor hoặc static factory thường là lựa chọn dễ kiểm soát hơn.

## 2. Từ `protected Object clone()` sang `public T clone()`

Một mẫu thường gặp:

```java
public class Point implements Cloneable {
    private final int x;
    private final int y;

    public Point(int x, int y) {
        this.x = x;
        this.y = y;
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
```

Đây là một lớp có thể biên dịch trong tệp `Point.java` trên Java 17+. Các quyết định có ý nghĩa rõ ràng:

1. **`implements Cloneable`** đánh dấu đối tượng có thể được `Object.clone()` sao chép theo cơ chế chuẩn.
2. **`@Override`** kiểm tra đúng chữ ký phương thức được override; giúp phát hiện sai tên/tham số.
3. **`public`** mở rộng mức truy cập của phương thức kế thừa `protected`. Java cho phép mở rộng quyền truy cập khi override; **không** cho giảm từ `protected` xuống `private` hoặc mặc định package-private.
4. **`Point` làm kiểu trả về** thay vì `Object`. Vì `Point` là subtype của `Object`, đây là *covariant return type* hợp lệ. Phía gọi có thể viết `Point copy = original.clone();` mà không cần cast.
5. **`super.clone()`** thực hiện bản sao nông của đối tượng. Nó trả `Object` theo chữ ký gốc nên trong thân phương thức vẫn cần ép kiểu `(Point)`; loại bỏ cast **ở người gọi**, không nhất thiết loại bỏ cast **bên trong implementation**.
6. **Khối `catch`** chuyển một ngoại lệ được dự kiến không xảy ra thành `AssertionError`, bởi class trực tiếp triển khai `Cloneable`. Có thể chọn công bố `throws CloneNotSupportedException` thay vì bắt, nhưng khi đó người dùng API phải xử lý ngoại lệ.

Với `Point` chỉ chứa hai `int`, sao chép nông đã đủ: mỗi bản sao giữ bản sao riêng của các giá trị nguyên thủy.

### Vì sao đổi kiểu trả về là hợp lệ?

Java hỗ trợ override một phương thức trả về kiểu tham chiếu bằng phương thức trả về subtype. `Object.clone()` trả `Object`, còn `Point.clone()` trả `Point`, nên hợp lệ. Tương tự, nếu `Report extends Document`, `Report.clone()` có thể trả `Report` khi `Document.clone()` trả `Document`. Cơ chế này gọi là **kiểu trả về hiệp biến**.

Không thể tùy tiện thay kiểu trả về bằng kiểu không liên quan, chẳng hạn từ `Object` thành `int`. Và việc covariant return chỉ áp dụng đúng quy tắc override; không phải một cách tạo overload riêng.

### Phải dùng `public` ở đâu?

Khi API cần cho mã bên ngoài gọi `clone()`, đặt `public` trên **phương thức override**. Nếu một class chỉ `implements Cloneable` nhưng không viết phương thức công khai, mã bên ngoài class không thể gọi `clone()` thông qua reference kiểu class đó theo cách thông thường, vì chỉ còn phiên bản `protected` kế thừa từ `Object`.

`Cloneable` cũng **không phải** kiểu có thể gọi `clone()` trực tiếp: biến kiểu `Cloneable` không có phương thức `clone` trong interface. Chính class cần công khai phương thức; hoặc ứng dụng nên cung cấp một API sao chép có tên và hợp đồng rõ ràng hơn.

## 3. Quy tắc `Cloneable` và ngoại lệ

`Object.clone()` mặc định thực hiện kiểm tra marker `Cloneable` trên kiểu runtime, rồi tạo một đối tượng mới có cùng kiểu runtime và sao chép các field. Không có marker, nó ném `CloneNotSupportedException`.

Hai lựa chọn xử lý ngoại lệ trong override:

**Cách A — để checked exception trong API:**

```java
@Override
public Point clone() throws CloneNotSupportedException {
    return (Point) super.clone();
}
```

Đây là **mảnh mã minh họa** đặt bên trong một lớp `Point implements Cloneable`. Người gọi phải bắt hoặc khai báo `CloneNotSupportedException`. Override có thể giữ checked exception theo hợp đồng của `Object.clone()`.

**Cách B — ẩn checked exception vì class bảo đảm Cloneable:**

```java
@Override
public Point clone() {
    try {
        return (Point) super.clone();
    } catch (CloneNotSupportedException e) {
        throw new AssertionError("Unexpected clone failure", e);
    }
}
```

Đây cũng là **mảnh mã đặt trong class**, chưa phải chương trình độc lập. Vì class đang xét đã implements `Cloneable`, khối `catch` thường là cách phản ánh lỗi lập trình bất thường, thay vì bắt người gọi xử lý checked exception vốn không dự kiến xảy ra với cơ chế `Object.clone()` chuẩn.

Dù theo lựa chọn nào, **không nuốt ngoại lệ rồi trả `null`**: như vậy các lời gọi sau có thể gặp `NullPointerException` ở vị trí xa nguyên nhân thật, và người gọi không thể tin vào hợp đồng trả bản sao.

## 4. Bản sao nông: `super.clone()` sao chép những gì?

`Object.clone()` thông thường tạo một **đối tượng mới cùng kiểu runtime** và sao chép giá trị các field:

- Với `int`, `boolean`, `double` và primitive khác: giá trị được sao chép.
- Với field tham chiếu như `String`, `List`, mảng hoặc object tùy chỉnh: **tham chiếu được sao chép**, không tự nhân bản đối tượng mà tham chiếu đó trỏ tới.
- Nếu tham chiếu trỏ tới object **bất biến** như `String`, việc chia sẻ object thường an toàn.
- Nếu tham chiếu trỏ tới object **mutable** như `int[]` hoặc `ArrayList`, clone và bản gốc có thể nhìn thấy thay đổi của nhau qua tham chiếu chung.

`super.clone()` không tự gọi constructor công khai của chính lớp đang clone như một lệnh `new T(...)` bình thường; vì vậy không thể dựa vào logic constructor để tự tái tạo hoặc sao chép lại các thành phần mutable. Mọi bất biến và ràng buộc với trạng thái sau clone phải được xét trong override.

Ví dụ, nếu class có field `int[] scores` và chỉ gọi `super.clone()`, cả bản gốc lẫn bản sao ban đầu cùng giữ tham chiếu đến **một mảng**. Muốn hai đối tượng chỉnh sửa mảng độc lập, sau khi clone phải tạo bản sao mảng:

```java
@Override
public Report clone() {
    Report copy = (Report) super.clone();
    copy.scores = scores.clone();
    return copy;
}
```

Đoạn mã này giả định class `Report` có field `int[] scores` không final và `super.clone()` gọi tới một override hợp lệ, trả về object runtime là `Report`. Nếu `scores` có thể null thì phải xử lý trường hợp null. Đối với mảng của các đối tượng mutable, `scores.clone()` (nếu là mảng tham chiếu) **chỉ nhân bản mảng**, vẫn chia sẻ các phần tử; muốn deep copy phải xác định cách sao chép từng phần tử.

**Đặc biệt:** `final` field tham chiếu không thể gán lại sau `super.clone()` từ bên trong clone bình thường. Nếu cần clone sâu đối tượng có các field `final` mutable, copy constructor hoặc factory thường tự nhiên hơn `Object.clone()`.

## 5. Java 17: chương trình chạy được với lớp cha và lớp con

Ví dụ sau minh họa cùng lúc: public clone, kiểu trả về cụ thể, covariant return trong lớp con, và tự nhân bản một mảng mutable. Tạo tệp `PublicCloneDemo.java`:

```java
import java.util.Arrays;

public class PublicCloneDemo {
    static class Document implements Cloneable {
        private final String title;

        Document(String title) {
            this.title = title;
        }

        @Override
        public Document clone() {
            try {
                return (Document) super.clone();
            } catch (CloneNotSupportedException e) {
                throw new AssertionError(e);
            }
        }

        public String title() {
            return title;
        }
    }

    static final class Report extends Document {
        private int[] scores;

        Report(String title, int[] scores) {
            super(title);
            this.scores = scores.clone();
        }

        @Override
        public Report clone() {
            Report copy = (Report) super.clone();
            copy.scores = scores.clone();
            return copy;
        }

        public void setFirstScore(int score) {
            scores[0] = score;
        }

        public int firstScore() {
            return scores[0];
        }

        public int[] scoresSnapshot() {
            return scores.clone();
        }
    }

    public static void main(String[] args) {
        Document source = new Document("Guide");
        Document clonedDocument = source.clone();

        System.out.println("document different reference: "
                + (source != clonedDocument));
        System.out.println("document title: " + clonedDocument.title());

        Report report = new Report("Metrics", new int[] {2, 4});
        Report clonedReport = report.clone();

        System.out.println("report different reference: "
                + (report != clonedReport));
        System.out.println("same runtime type: "
                + (report.getClass() == clonedReport.getClass()));
        System.out.println("before: "
                + report.firstScore() + "/" + clonedReport.firstScore());

        report.setFirstScore(9);
        System.out.println("after: "
                + report.firstScore() + "/" + clonedReport.firstScore());
        System.out.println("copy scores: "
                + Arrays.toString(clonedReport.scoresSnapshot()));
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 PublicCloneDemo.java
java PublicCloneDemo
```

Kết quả chuẩn:

```text
document different reference: true
document title: Guide
report different reference: true
same runtime type: true
before: 2/2
after: 9/2
copy scores: [2, 4]
```

Diễn giải:

1. `Document implements Cloneable` và công khai `public Document clone()`. Phía gọi gán trực tiếp `Document clonedDocument = source.clone();`, không cần ép kiểu.
2. `Report` kế thừa chính sách clone của `Document`. `Report.clone()` override và **thu hẹp kiểu trả về** từ `Document` thành `Report`, nên `Report clonedReport = report.clone();` hợp lệ.
3. Bên trong `Document.clone()`, lệnh `Object.clone()` tạo đối tượng **cùng kiểu runtime** với receiver. Khi receiver là `Report`, đối tượng được tạo vẫn là `Report`. Vì thế phép ép kiểu `(Report) super.clone()` trong `Report.clone()` là hợp lệ theo cấu trúc này.
4. Dữ liệu `title` là `String` bất biến nên chia sẻ tham chiếu an toàn cho ví dụ. Ngược lại, `scores` là mảng mutable; `Report.clone()` tạo mảng riêng bằng `scores.clone()`.
5. Sau khi thay điểm đầu của bản gốc thành `9`, bản sao vẫn giữ `2`. Đây là bằng chứng cho việc copy đã độc lập ở **cấp mảng `int[]`**, không phải khẳng định `Object.clone()` luôn thực hiện deep copy.

Nếu bỏ dòng `copy.scores = scores.clone();`, phần tử đầu của mảng trong hai object sẽ cùng thay đổi vì cả hai cùng trỏ vào mảng cũ. Nếu array chứa object có thể thay đổi, việc clone mảng cũng chưa sao chép sâu từng object bên trong.

## 6. Kiểu trả về hiệp biến và vai trò của thừa kế

Xét hệ phân cấp:

```text
Object.clone(): Object
    ↓ override
Document.clone(): Document
    ↓ override
Report.clone(): Report
```

Mỗi mức override được phép trả về subtype của kiểu ở mức cha. Đây là quy tắc của Java, không phải phép ép kiểu runtime tự phát. Các phương thức đều tên `clone`, không có tham số và override nhau; `@Override` giúp trình biên dịch kiểm tra.

Điều này cải thiện trải nghiệm người dùng API:

```java
Report report = new Report("Metrics", new int[] {2, 4});
Report copied = report.clone(); // Không cần (Report)
```

Đây là đoạn code giả định các lớp từ `PublicCloneDemo` ở trên. Nếu biến được khai báo dưới kiểu tĩnh `Document`:

```java
Document baseView = report;
Document copiedThroughBase = baseView.clone();
```

Biểu thức `baseView.clone()` có **kiểu trả về tại thời điểm biên dịch** là `Document` do chữ ký trên `Document`; tại runtime Java vẫn dispatch tới override `Report.clone()`. Muốn biến kiểu `Report` mà không cast, cần giữ reference có kiểu tĩnh `Report` hoặc thiết kế factory/API với typing phù hợp. Covariant return không khiến trình biên dịch đoán một subtype từ đối tượng runtime khi kiểu tĩnh rộng hơn.

Ở cấp bytecode, trình biên dịch có thể sinh **bridge method** để bảo đảm hành vi override và tương thích lời gọi qua kiểu cha. Đây là chi tiết triển khai, không làm thay đổi quy tắc viết code Java bên trên.

## 7. Bảo vệ hợp đồng clone với lớp có thể kế thừa

Với class **không final**, thiết kế clone phải cân nhắc lớp con. Một override gọi `super.clone()` thường tạo đối tượng của lớp runtime thực sự, kể cả nếu code đang nằm trong lớp cha. Lớp con có trạng thái mutable mới nên tự override `clone()` để hoàn tất việc copy; nếu không, bản sao của lớp con có thể chia sẻ các đối tượng mutable với bản gốc.

Với class `final`, bạn không phải xử lý subclass trong tương lai và có thể xác định chính xác tập field cần sao chép. Với class cho phép kế thừa, hãy ghi rõ hợp đồng: subclass có được phép override không, phải làm gì với mutable field và có cần bảo toàn trạng thái đặc biệt không.

Không nên tuyên bố `Cloneable` đồng nghĩa mọi clone là **deep copy**. `Cloneable` chỉ báo khả năng thực hiện cơ chế copy bằng `Object.clone()`; lớp tự chịu trách nhiệm ý nghĩa sao chép của dữ liệu mà nó quản lý.

Một số nguyên tắc cho API clone công khai:

- **Không trả `this`** nếu giao ước mong một instance mới; với mutable object thông thường, hai biến trỏ cùng đối tượng không phải bản sao.
- **Không tự động gọi constructor**: kiểm tra invariants nếu trạng thái bình thường được tạo bởi constructor, validation hoặc liên kết giữa các field.
- **Đảm bảo các field liên quan nhất quán**: một clone có thể cần khởi tạo lại cache, lock, handle hệ thống hoặc ID tài nguyên thay vì chia sẻ trực tiếp.
- **Ghi rõ copy là nông hay sâu đến mức nào**: “deep copy” phải định nghĩa theo cấu trúc dữ liệu cụ thể, không chỉ dựa trên việc gọi `clone()` nhiều lần.
- **Tránh clone object sở hữu tài nguyên ngoài JVM** nếu không có chính sách sao chép rõ ràng; socket, file descriptor, transaction, thread và resource handle không mặc nhiên có thể nhân bản an toàn.

## 8. `clone()` khác copy constructor và factory

Java không yêu cầu mọi object phải hỗ trợ clone. Một phương án đơn giản hơn là copy constructor hoặc một phương thức static rõ tên:

```java
public final class Settings {
    private final String name;
    private final java.util.List<String> tags;

    public Settings(String name, java.util.List<String> tags) {
        this.name = java.util.Objects.requireNonNull(name);
        this.tags = java.util.List.copyOf(tags);
    }

    public Settings(Settings original) {
        this(original.name, original.tags);
    }

    public static Settings copyOf(Settings original) {
        return new Settings(original);
    }
}
```

Đây là class `Settings.java` hợp lệ trong Java 17. Bản sao dùng constructor có thể giữ field `final`, kiểm tra input và sao chép danh sách bất biến từ đầu. Với `List<String>` (và chuỗi bất biến), mô hình an toàn hơn việc dùng `Object.clone()` rồi phải gán lại field `final`.

| Lựa chọn | Đặc điểm | Phù hợp |
| --- | --- | --- |
| `public T clone()` + `Cloneable` | Tận dụng `Object.clone()`; kiểu trả về cụ thể; cần quản lý shallow/deep copy và checked exception | API cũ hoặc kiểu đã có quy ước clone rõ |
| Copy constructor `new T(original)` | Gọi constructor, cho phép kiểm tra invariant và làm bản sao theo chính sách đã xác định | Value object hoặc đối tượng quản lý field `final` |
| Static factory `T.copyOf(source)` | Tên API diễn đạt ý định, có thể tái dùng đối tượng bất biến nếu hợp đồng cho phép | API ứng dụng mới, kiểu bất biến |

Với record hoặc đối tượng immutable, đôi khi **không cần bản sao mới**: có thể chia sẻ cùng instance an toàn nếu chỉ cần giữ giá trị. Nếu API yêu cầu danh tính object khác nhau thì phải nói rõ yêu cầu đó.

## 9. Những lỗi thường gặp

### Chỉ viết `implements Cloneable` mà không override `clone()`

Marker không thêm một `public clone()` vào lớp. Vì `Object.clone()` là `protected`, người dùng bên ngoài vẫn không gọi được `obj.clone()` qua API công khai thông thường. Muốn hỗ trợ tính năng, công bố phương thức với mức truy cập phù hợp.

### Override nhưng tiếp tục trả `Object`

`public Object clone()` là một override hợp lệ về kiểu nhưng khiến người gọi cần cast về kiểu đích. Khi class trả về chính subtype của nó, khai báo `public T clone()` thường thân thiện và kiểm tra kiểu tốt hơn.

### Quên `Cloneable`

Gọi `super.clone()` trong một class không thực hiện `Cloneable` thường dẫn đến `CloneNotSupportedException` khi thực thi. Phải hiểu rằng clone là một hợp đồng opt-in; không thể chỉ tăng quyền truy cập và mong cơ chế copy tự hoạt động.

### Không xử lý `CloneNotSupportedException`

Nếu gọi trực tiếp `super.clone()`, lập trình viên phải bắt hoặc khai báo checked exception theo luật Java. Với class implements `Cloneable`, mẫu bắt và chuyển thành `AssertionError` thường được dùng khi ngoại lệ được xem là bất thường.

### Tưởng `super.clone()` là deep copy

Bản sao nông giữ chung tham chiếu field với object gốc. Với list, array, map hoặc đối tượng trạng thái thay đổi, hai bản có thể ảnh hưởng nhau. Cần copy tiếp theo mục tiêu, hoặc dùng constructor/factory.

### Bỏ qua lớp con

Một lớp cha `clone()` công khai có thể sao chép đúng field của cha nhưng để field mutable thêm bởi subclass bị chia sẻ. Vì vậy subclass thường phải override và trả về kiểu subclass, sao chép bổ sung trạng thái mà nó sở hữu.

### Clone class có invariant hoặc tài nguyên đặc biệt

`Object.clone()` không chạy lại constructor của class được clone để tái thiết lập mọi điều kiện. Với object có resource, handle, cache phụ thuộc trạng thái hoặc quan hệ giữa nhiều trường, clone nông có thể không hợp lệ. Định nghĩa chính sách copy cụ thể hoặc tránh cơ chế clone cho kiểu đó.

## 10. Checklist khi triển khai `public T clone()`

1. Xác định **vì sao** đối tượng cần clone: phải tạo object khác reference, giữ cùng giá trị, hay cần hai trạng thái độc lập?
2. Nếu sử dụng `Object.clone()`, kiểm tra lớp thuộc nhánh thực hiện `Cloneable`.
3. Override bằng **`@Override public T clone()`** và bảo đảm `T` là kiểu trả về hiệp biến hợp lệ.
4. Gọi `super.clone()` và xử lý `CloneNotSupportedException`, hoặc khai báo checked exception trong API nếu phù hợp.
5. Kiểm tra field primitive, immutable và mutable: field mutable nào cần sao chép cấp phát riêng?
6. Với mảng các đối tượng mutable hoặc collection lồng nhau, kiểm tra cả **phần tử**, không dừng ở `array.clone()` hoặc `new ArrayList<>(list)`.
7. Với subclass, cân nhắc `super.clone()` và bổ sung sao chép field riêng; kiểm tra kiểu runtime thực của clone.
8. Thử `original != clone`, so dữ liệu ban đầu và sửa mutable state ở một phía để xác minh mức độ độc lập.
9. Nếu class chứa field `final`, invariant phức tạp hoặc resource ngoại vi, đánh giá copy constructor/static factory trước.
10. Ghi rõ hành vi clone trong tài liệu API; đừng suy diễn từ marker `Cloneable` rằng clone chắc chắn sâu hay an toàn.

**Kết luận:** Muốn người dùng class gọi `clone()` trực tiếp và nhận đúng kiểu, thường viết `public T clone()` để override `Object.clone()` với **quyền truy cập rộng hơn** và **kiểu trả về hiệp biến**. Khi dùng cơ chế `super.clone()`, cần `Cloneable`, xử lý ngoại lệ và hiểu mặc định đây là **shallow copy**. Khả năng copy sâu hay bảo toàn bất biến của đối tượng là trách nhiệm riêng của thiết kế lớp, không phải kết quả tự động của `public` hoặc covariant return.
