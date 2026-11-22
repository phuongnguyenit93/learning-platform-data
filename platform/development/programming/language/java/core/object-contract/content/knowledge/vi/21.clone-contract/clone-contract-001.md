# clone() tạo bản sao và ý nghĩa sao chép phụ thuộc lớp

## 1. Clone là gì và cần hiểu đúng điều gì?

Trong Java, **clone()** thường được dùng để tạo một đối tượng mới từ trạng thái của đối tượng đang có. Nhưng tên phương thức **không bảo đảm đây là deep copy**: đối tượng mới có thể chia sẻ mảng, danh sách hoặc các object con với đối tượng gốc. Độ sâu sao chép, quy tắc giữ định danh nghiệp vụ, vòng đời tài nguyên và khả năng thay đổi của hai bản thể **phụ thuộc vào hợp đồng của lớp cụ thể**.

Ví dụ một đối tượng có **String name** và **int[] scores**. Name là String bất biến nên có thể chia sẻ tham chiếu an toàn. Scores là mảng mutable: nếu bản sao cùng trỏ đến mảng, sửa phần tử qua bản sao sẽ làm bản gốc quan sát thấy thay đổi. Nếu yêu cầu hai đối tượng độc lập về scores, cần sao chép riêng mảng.

Phân biệt ba khái niệm:

- **Shallow copy:** object ngoài là bản thể mới, nhưng các field tham chiếu thường tiếp tục trỏ tới object con cũ.
- **Deep copy:** các thành phần mutable có yêu cầu độc lập cũng được tạo bản sao. Độ sâu cần thiết phụ thuộc vào cấu trúc dữ liệu và chính sách chia sẻ của miền nghiệp vụ.
- **Immutable snapshot:** tạo một giá trị không đổi để lưu trạng thái ở một thời điểm, thường bằng copy constructor hoặc factory với dữ liệu đã sao chép/phong tỏa phù hợp.

Clone không nhất thiết đồng nghĩa với immutable, cũng không đồng nghĩa với một bản sao có cùng ID nghiệp vụ. Hãy xác định trước **những thứ được giữ**, **những thứ cần tách**, và **những thứ không được sao chép**.

## 2. Object.clone() và Cloneable thực sự hoạt động thế nào?

Trong **java.lang.Object** có phương thức:

~~~java
protected native Object clone() throws CloneNotSupportedException;
~~~

Đây là **chữ ký API**, không phải một chương trình Java độc lập. Object.clone được thiết kế để tạo một object mới và sao chép các giá trị field instance theo cách **nông**. Primitive được sao chép giá trị; field tham chiếu nhận lại cùng giá trị tham chiếu. Nó không gọi lần lượt clone của các object con.

**java.lang.Cloneable** là **marker interface**, không khai báo phương thức nào. Khi object không implements Cloneable, gọi Object.clone trên nó sẽ ném **CloneNotSupportedException**. Một lớp implements Cloneable vẫn **không tự xuất hiện phương thức clone() public** cho mã ngoài gọi, vì Object.clone vốn có mức truy cập protected. Muốn cung cấp API công khai, lớp thường override **public clone()**, có thể trả về chính kiểu lớp nhờ covariant return type.

Một mẫu thường gặp:

~~~java
@Override
public Widget clone() {
    try {
        return (Widget) super.clone();
    } catch (CloneNotSupportedException ex) {
        throw new AssertionError(ex);
    }
}
~~~

Đây là **đoạn trích trong lớp Widget implements Cloneable**, không phải file chạy độc lập. Mẫu này phù hợp khi phương thức gọi Object.clone với marker đã được bảo đảm. Một API khác có thể khai báo **throws CloneNotSupportedException** thay vì bắt.

### Các quy ước, không phải bảo đảm tuyệt đối

Tài liệu Object.clone mô tả những đặc tính **thường được kỳ vọng**:

~~~text
x.clone() != x
x.clone().getClass() == x.getClass()
x.clone().equals(x)
~~~

Những dòng trên **không phải ba yêu cầu bắt buộc cho mọi override clone()**. Chẳng hạn, lớp chưa override equals thì hai bản thể khác tham chiếu vẫn có thể trả false theo Object.equals. Một lớp copy tài nguyên có thể cố ý đặt ID mới, khiến equals theo ID trả false. Hợp đồng thực tế phải được tài liệu hóa ở lớp ấy.

## 3. Ví dụ Java 17: bản sao nông làm chia sẻ mảng

Tạo file **ShallowCloneDemo.java**:

~~~java
import java.util.Arrays;

public class ShallowCloneDemo {
    static final class Report implements Cloneable {
        private final String title;
        private int[] scores;

        Report(String title, int[] scores) {
            this.title = title;
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
    }

    public static void main(String[] args) {
        Report original = new Report("Daily", new int[]{10, 20});
        Report copy = original.clone();

        System.out.println("different object: " + (original != copy));
        System.out.println("same array: " +
            (original.scores == copy.scores));

        copy.scores[0] = 99;

        System.out.println("original: " +
            Arrays.toString(original.scores));
        System.out.println("copy: " +
            Arrays.toString(copy.scores));
        System.out.println("title: " + copy.title);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac ShallowCloneDemo.java
java ShallowCloneDemo
~~~

Kết quả:

~~~text
different object: true
same array: true
original: [99, 20]
copy: [99, 20]
title: Daily
~~~

Vì **super.clone()** chỉ copy tham chiếu **scores**, original và copy giữ cùng mảng. Việc cùng trỏ tới String title không thành vấn đề vì String bất biến. Nhưng với mảng scores, một thay đổi đã ảnh hưởng cả hai.

Đây là ví dụ **shallow copy**, không phải lỗi biên dịch. Nó chỉ không phù hợp nếu API hứa hẹn dữ liệu được tách độc lập. Ngoài ra, constructor ở ví dụ đang giữ nguyên tham chiếu mảng đầu vào; caller có thể sửa mảng gốc bên ngoài. Nếu muốn cách ly hoàn toàn từ lúc tạo, cần defensive copy cả trong constructor.

## 4. Tách field mutable sau super.clone()

Khi một lớp có mảng primitive một chiều, có thể gọi super.clone để tạo object rồi thay tham chiếu mảng của bản sao bằng một mảng mới. Tạo file **IndependentCloneDemo.java**:

~~~java
import java.util.Arrays;
import java.util.Objects;

public class IndependentCloneDemo {
    static final class Batch implements Cloneable {
        private final String id;
        private int[] values;

        Batch(String id, int[] values) {
            this.id = Objects.requireNonNull(id);
            this.values = Objects.requireNonNull(values).clone();
        }

        public int[] values() {
            return values.clone();
        }

        @Override
        public Batch clone() {
            try {
                Batch copy = (Batch) super.clone();
                copy.values = values.clone();
                return copy;
            } catch (CloneNotSupportedException ex) {
                throw new AssertionError(ex);
            }
        }

        @Override
        public boolean equals(Object obj) {
            return obj instanceof Batch other
                && id.equals(other.id)
                && Arrays.equals(values, other.values);
        }

        @Override
        public int hashCode() {
            return 31 * id.hashCode() + Arrays.hashCode(values);
        }
    }

    public static void main(String[] args) {
        Batch original = new Batch("B-1", new int[]{3, 5});
        Batch copy = original.clone();

        System.out.println("different object: " + (original != copy));
        System.out.println("same array: " + (original.values == copy.values));
        System.out.println("equal before: " + original.equals(copy));
        System.out.println("same hash before: " +
            (original.hashCode() == copy.hashCode()));

        copy.values[0] = 8;

        System.out.println("original: " + Arrays.toString(original.values));
        System.out.println("copy: " + Arrays.toString(copy.values));
        System.out.println("equal after: " + original.equals(copy));
    }
}
~~~

Chạy:

~~~bash
javac IndependentCloneDemo.java
java IndependentCloneDemo
~~~

Kết quả:

~~~text
different object: true
same array: false
equal before: true
same hash before: true
original: [3, 5]
copy: [8, 5]
equal after: false
~~~

Giải thích: **clone()** tạo object Batch mới, sau đó clone mảng values để tách trạng thái có thể thay đổi. **id** là String bất biến nên chia sẻ an toàn. Vì equals của Batch dựa trên **id và nội dung mảng**, trước khi sửa bản sao thì equals true và hashCode bằng nhau; sau khi bản sao bị sửa, hai giá trị khác nhau.

Field **values** không khai báo final vì phép gán **copy.values = ...** sau **super.clone()** phải hợp lệ. Nếu muốn field mảng là final và dữ liệu giá trị bất biến, **copy constructor** thường thuận tiện hơn. Đừng kết luận một lần clone mảng là “deep copy vĩnh viễn”: khi cấu trúc có thêm object mutable lồng bên trong, cách này có thể không còn đủ.

## 5. Không implements Cloneable thì chuyện gì xảy ra?

Tạo file **CloneMarkerDemo.java**:

~~~java
public class CloneMarkerDemo {
    static final class NoMarker {
        Object attemptClone() throws CloneNotSupportedException {
            return super.clone();
        }
    }

    static final class WithMarker implements Cloneable {
        private final int code;

        WithMarker(int code) {
            this.code = code;
        }

        @Override
        public WithMarker clone() {
            try {
                return (WithMarker) super.clone();
            } catch (CloneNotSupportedException ex) {
                throw new AssertionError(ex);
            }
        }
    }

    public static void main(String[] args) {
        try {
            new NoMarker().attemptClone();
        } catch (CloneNotSupportedException ex) {
            System.out.println("without marker: " +
                ex.getClass().getSimpleName());
        }

        WithMarker first = new WithMarker(42);
        WithMarker copy = first.clone();

        System.out.println("new object: " + (first != copy));
        System.out.println("copied code: " + copy.code);
    }
}
~~~

Chạy:

~~~bash
javac CloneMarkerDemo.java
java CloneMarkerDemo
~~~

Kết quả:

~~~text
without marker: CloneNotSupportedException
new object: true
copied code: 42
~~~

**NoMarker** có thể gọi protected Object.clone từ một phương thức của lớp, nhưng Object.clone từ chối vì object không implements Cloneable. **WithMarker** vừa có marker vừa public override, nên caller gọi được và nhận bản sao.

Chú ý tính **checked** của CloneNotSupportedException: lời gọi có chữ ký throws phải được bắt hoặc khai báo. Khi bản thân lớp kiểm soát Cloneable, mẫu bắt exception rồi ném AssertionError có thể dùng để bộc lộ tình huống không đúng như bất biến thiết kế.

## 6. Object.clone không gọi constructor cho bản sao

Đối với cơ chế Object.clone, object mới nhận trạng thái được sao chép mà không chạy constructor của class một lần nữa. Đây là khác biệt thiết yếu với **new** hoặc copy constructor.

Tạo file **ConstructorCloneDemo.java**:

~~~java
public class ConstructorCloneDemo {
    private static int constructorCalls;

    static final class Ticket implements Cloneable {
        private final int number;

        Ticket(int number) {
            constructorCalls++;
            this.number = number;
        }

        @Override
        public Ticket clone() {
            try {
                return (Ticket) super.clone();
            } catch (CloneNotSupportedException ex) {
                throw new AssertionError(ex);
            }
        }
    }

    public static void main(String[] args) {
        Ticket first = new Ticket(7);
        Ticket copy = first.clone();

        System.out.println("constructor calls: " + constructorCalls);
        System.out.println("different object: " + (first != copy));
        System.out.println("number: " + copy.number);
    }
}
~~~

Chạy:

~~~bash
javac ConstructorCloneDemo.java
java ConstructorCloneDemo
~~~

Kết quả:

~~~text
constructor calls: 1
different object: true
number: 7
~~~

Điều này có thể bỏ qua các bước xác thực, đăng ký listener, tạo lock/tài nguyên, sinh ID hay tính trường phụ trong constructor. Khi lớp có các **invariant** phụ thuộc constructor, phải thiết kế clone để kết quả luôn hợp lệ. Không thể mặc định clone một socket, file handle, stream, thread hay database connection theo nghĩa tạo thêm một tài nguyên độc lập.

## 7. Clone mảng một chiều và mảng lồng nhau

Mảng Java hỗ trợ **clone()**. Với **int[]**, mảng mới chứa các giá trị int được sao chép. Với **StringBuilder[]**, mảng mới chứa lại các tham chiếu tới cùng StringBuilder. Mảng ngoài được tạo mới, nhưng element object thường chưa được clone.

Với **int[][]**, mảng ngoài chứa các tham chiếu **int[]**. Gọi clone trên mảng ngoài chưa copy từng hàng.

Tạo file **MatrixCloneDemo.java**:

~~~java
import java.util.Arrays;

public class MatrixCloneDemo {
    public static void main(String[] args) {
        int[][] original = {{1, 2}, {3, 4}};
        int[][] shallow = original.clone();

        int[][] independent = new int[original.length][];
        for (int i = 0; i < original.length; i++) {
            independent[i] = original[i].clone();
        }

        System.out.println("same outer: " + (original == shallow));
        System.out.println("shared row: " + (original[0] == shallow[0]));

        shallow[0][0] = 9;
        System.out.println("original after shallow: " +
            Arrays.deepToString(original));

        independent[1][0] = 7;
        System.out.println("original after independent: " +
            Arrays.deepToString(original));
        System.out.println("independent snapshot: " +
            Arrays.deepToString(independent));
    }
}
~~~

Chạy:

~~~bash
javac MatrixCloneDemo.java
java MatrixCloneDemo
~~~

Kết quả:

~~~text
same outer: false
shared row: true
original after shallow: [[9, 2], [3, 4]]
original after independent: [[9, 2], [3, 4]]
independent snapshot: [[1, 2], [7, 4]]
~~~

Independent sao chép từng hàng **trước khi** shallow sửa dữ liệu ban đầu, nên nó giữ snapshot giá trị ban đầu. Nếu một hàng có thể null, phải xử lý trước khi gọi **original[i].clone()**. Nếu phần tử bên trong là object mutable chứ không phải primitive, clone từng tầng mảng vẫn giữ object lá được chia sẻ.

**Arrays.copyOf** và **System.arraycopy** cũng sao chép phần tử mà không tự động clone mọi object phần tử. Chọn cách copy theo ngữ nghĩa cần đạt, không dựa vào tên phương thức.

## 8. Clone collection cũng cần xem tài liệu lớp cụ thể

Interface **List**, **Set**, **Map** không bắt buộc cung cấp clone. Một số lớp cụ thể, ví dụ **ArrayList**, có phương thức clone tạo **bản sao nông** của cấu trúc danh sách. Các phần tử vẫn là tham chiếu tới object cũ.

Tạo file **ListCloneDemo.java**:

~~~java
import java.util.ArrayList;

public class ListCloneDemo {
    public static void main(String[] args) {
        ArrayList<StringBuilder> first = new ArrayList<>();
        first.add(new StringBuilder("A"));

        @SuppressWarnings("unchecked")
        ArrayList<StringBuilder> second =
            (ArrayList<StringBuilder>) first.clone();

        System.out.println("same list: " + (first == second));
        System.out.println("same element: " +
            (first.get(0) == second.get(0)));

        second.get(0).append("!");
        System.out.println("first value: " + first.get(0));
        System.out.println("second value: " + second.get(0));
    }
}
~~~

Chạy:

~~~bash
javac ListCloneDemo.java
java ListCloneDemo
~~~

Kết quả:

~~~text
same list: false
same element: true
first value: A!
second value: A!
~~~

**new ArrayList<>(first)** cũng sao chép cấu trúc nhưng không clone từng phần tử. **List.copyOf(first)** tạo danh sách không thể sửa cấu trúc, song object phần tử mutable vẫn được chia sẻ. “Collection không sửa được” khác với “đồ thị object hoàn toàn bất biến”.

## 9. Kế thừa làm hợp đồng clone phức tạp hơn

Một lớp cha có thể override clone và đảm bảo copy đúng các trường của chính nó. Nhưng khi lớp con bổ sung một mảng hoặc List mutable, bản sao do clone kế thừa tạo ra có thể vẫn đúng **kiểu runtime** nhưng chia sẻ field mới với bản gốc.

Nếu lớp con override clone:

- Nó phải tôn trọng cơ chế sao chép đã được lớp cha thiết kế.
- Nó cần xử lý những field mutable mới nếu contract yêu cầu độc lập.
- Nếu clone gọi **super.clone()**, cần phân biệt lớp cha gọi Object.clone và lớp cha đã tự thực hiện thêm bước clone field của mình.
- Các **final field** trỏ tới object mutable khiến phương án “super.clone rồi gán lại field” khó áp dụng; một constructor/factory tạo mới có thể là thiết kế phù hợp hơn.
- Với cây kế thừa mở, các subclass tương lai có thể làm hợp đồng sao chép trước đó không còn đúng.

Do đó việc override **clone()** nên gắn với **tài liệu rõ ràng về độ sâu, kiểu runtime, chia sẻ tài nguyên, và trách nhiệm của subclass**. Nếu không kiểm soát được cây kế thừa, một API copy riêng hoặc lớp final bất biến thường dễ xác minh hơn.

## 10. Copy constructor và kiểu bất biến là lựa chọn khác

Với code mới, **copy constructor** hoặc **static copy factory** có thể diễn tả chính xác các thành phần phải sao chép, đồng thời cho phép thiết lập field final và chạy validation thông thường.

Tạo file **CopyConstructorDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class CopyConstructorDemo {
    static final class Snapshot {
        private final String id;
        private final List<String> tags;

        Snapshot(String id, List<String> tags) {
            this.id = Objects.requireNonNull(id);
            this.tags = List.copyOf(Objects.requireNonNull(tags));
        }

        Snapshot(Snapshot source) {
            this(source.id, source.tags);
        }

        List<String> tags() {
            return tags;
        }
    }

    public static void main(String[] args) {
        List<String> input = new ArrayList<>(List.of("READY"));
        Snapshot original = new Snapshot("S-1", input);
        Snapshot copy = new Snapshot(original);

        input.add("DONE");

        System.out.println("different object: " + (original != copy));
        System.out.println("original: " + original.tags());
        System.out.println("copy: " + copy.tags());

        try {
            copy.tags().add("LATER");
        } catch (UnsupportedOperationException ex) {
            System.out.println("copy list cannot be modified");
        }
    }
}
~~~

Chạy:

~~~bash
javac CopyConstructorDemo.java
java CopyConstructorDemo
~~~

Kết quả:

~~~text
different object: true
original: [READY]
copy: [READY]
copy list cannot be modified
~~~

Ở đây **List.copyOf** tạo biểu diễn không thể thay đổi cấu trúc và các phần tử String là bất biến. Với **List<MutableItem>**, một List không cho phép add/remove **vẫn có thể quan sát thay đổi trong MutableItem**. Muốn bất biến sâu phải thiết kế riêng cho kiểu phần tử.

**Record** cũng thường không cần Cloneable. Với record chứa các giá trị immutable như int, String hoặc Instant, có thể dựng giá trị mới bằng canonical constructor:

~~~java
record Point(int x, int y) {}

Point p = new Point(1, 2);
Point q = new Point(p.x(), p.y());
~~~

Đây là đoạn minh họa, không phải file chương trình độc lập. Hai Point có giá trị equals nhau; với record có mảng hay object mutable, constructor/accessor/equals/hashCode phải được thiết kế đồng bộ để giữ hợp đồng giá trị khi sao chép.

## 11. Quan hệ giữa clone, equals và hashCode

**clone()** xử lý cách tạo object; **equals()** xử lý khi nào hai object tương đương; **hashCode()** phải nhất quán với equals. Không suy ra một hợp đồng từ hợp đồng còn lại.

Nếu lớp dùng **Object.equals** theo danh tính, một bản sao object mới có thể **không equals** object gốc. Nếu lớp có equals theo tất cả field giá trị và clone giữ nguyên các field ấy, clone thường equals bản gốc. Khi equals trả true, hashCode phải bằng nhau.

Đừng dùng hashCode như **ID duy nhất** của object hoặc của bản sao. HashCode là int và có thể va chạm. Nếu clone tạo ID mới theo nghiệp vụ, cả equals lẫn hashCode có thể thay đổi; việc đó phải nằm trong hợp đồng của class thay vì phát sinh ngầm.

Đối với object mutable được dùng làm khóa HashMap/HashSet, sửa field tham gia equals/hashCode sau khi đã chèn có thể khiến tra cứu sai. Có một bản clone độc lập không thay đổi quy tắc: **khóa đang nằm trong cấu trúc băm phải ổn định**.

## 12. Clone phức tạp của đồ thị object và tài nguyên

Một object có thể tham chiếu đến nhiều object con cùng dùng chung một node; đồ thị có thể có chu kỳ. Nếu yêu cầu deep copy đúng đồ thị:

1. Cần xác định node nào được tạo bản sao và node nào được chia sẻ.
2. Cần giữ mối quan hệ aliasing có chủ đích: hai field trỏ cùng node trong đồ thị gốc có phải cùng trỏ một node clone trong đồ thị mới không?
3. Với chu kỳ A → B → A, phải theo dõi các node đã sao chép để tránh đệ quy vô hạn.
4. Nên có ánh xạ object gốc → object clone trong quá trình duyệt đồ thị khi cần bảo toàn cấu trúc.
5. Phải có chính sách riêng cho resource có danh tính và vòng đời: stream, lock, socket, thread, transaction, native handle hoặc listener.

Không thể giải quyết các yêu cầu này chỉ bằng việc gọi **clone()** đệ quy tùy tiện. Thông thường cần một thuật toán copy theo mô hình dữ liệu hoặc một kiểu snapshot riêng.

## 13. Lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Nghĩ **implements Cloneable** tự sinh public clone | Caller không có API clone công khai | Override public clone hoặc dùng API copy |
| Chỉ gọi **super.clone()** với field mutable | Hai bản thể chia sẻ object con | Sao chép thêm các field cần độc lập |
| Clone mảng ngoài của ma trận | Các hàng vẫn được chia sẻ | Sao chép từng tầng cần thiết |
| Clone ArrayList và nghĩ phần tử cũng được clone | Thay đổi object phần tử xuất hiện ở cả hai list | Copy phần tử theo đúng contract |
| Quên checked **CloneNotSupportedException** | Lỗi biên dịch hoặc API khó dùng | Bắt exception hoặc khai báo throws |
| Dựa vào constructor trong object clone | Invariant hoặc resource chưa được thiết lập lại | Kiểm tra invariant và cân nhắc copy constructor |
| Thêm field mutable ở subclass nhưng không sửa clone | Bản sao chia sẻ state mới | Thiết kế và kiểm tra từng tầng kế thừa |
| Dùng final với chiến lược gán lại field sau super.clone | Không thể gán lại final field theo cách thông thường | Constructor/factory tạo bản sao mới |
| Tuyên bố “deep immutable” sau **List.copyOf** | Object lá mutable vẫn có thể đổi | Copy/đóng băng object phần tử |
| Tin **clone.equals(original)** luôn bắt buộc | Test thất bại dù clone đúng theo contract lớp | Kiểm tra trước tiêu chí equals của lớp |

## 14. Checklist kiểm thử hợp đồng sao chép

Khi một lớp cho phép clone, nên có các phép kiểm thử sau:

1. **Danh tính:** clone có phải object mới theo cam kết? Nếu có, **original != copy**.
2. **Kiểu:** bản sao có đúng runtime class, nhất là với subclass?
3. **Trạng thái ban đầu:** dữ liệu có ý nghĩa được giữ, trừ những trường được tài liệu quy định đặt lại.
4. **Equals/hashCode:** nếu clone equals original thì hashCode bắt buộc giống nhau; không tự yêu cầu equals true với mọi loại clone.
5. **Sửa clone:** thay đổi từng field mutable của clone và quan sát original.
6. **Sửa original:** kiểm tra clone có bị ảnh hưởng ở những tham chiếu lẽ ra đã độc lập không.
7. **Sao chép sâu:** kiểm tra mảng lồng nhau, List object mutable, các node dùng chung, object null và dữ liệu rỗng.
8. **Constructor/invariant:** object clone còn hợp lệ không, có thiếu lock/cache/resource được tạo bởi constructor không?
9. **Kế thừa:** subclass thêm trường có thay đổi kết quả sao chép không?
10. **HashMap/HashSet:** không sửa các field tham gia equals/hashCode của khóa đã được lưu.
11. **Vòng đời tài nguyên:** không vô tình nhân đôi hoặc chia sẻ tài nguyên chỉ được phép sở hữu một lần.
12. **Độ sâu theo nghiệp vụ:** tài liệu và test phải cùng xác định rõ chỗ nào chia sẻ, chỗ nào độc lập.

## 15. Chọn giải pháp phù hợp

| Tình huống | Lựa chọn thường hợp lý |
| --- | --- |
| Tất cả state là primitive/immutable | Shallow copy có thể đủ; thậm chí có thể dùng chung giá trị immutable |
| Có một mảng primitive mutable | Object copy + clone mảng; bảo vệ constructor/getter khi cần |
| Mảng nhiều chiều | Copy từng mảng con cần thiết |
| Collection có các phần tử immutable | Copy collection hoặc cấu trúc không sửa đổi được |
| Collection có phần tử mutable | Copy collection và từng phần tử theo contract |
| Cây kế thừa mở, nhiều subclass | Xác lập cơ chế copy ở mọi tầng hoặc cân nhắc factory |
| Class có resource hoặc invariant constructor phức tạp | API copy riêng, copy constructor, hoặc không hỗ trợ copy |
| Kiểu giá trị record/final immutable | Constructor, factory, hoặc sử dụng trực tiếp giá trị |

**Ghi nhớ:** **Object.clone()** cho một bản sao **nông** khi class thực sự hỗ trợ Cloneable, còn ý nghĩa của một bản sao dùng được trong ứng dụng **do chính class định nghĩa**. Khi object chứa state mutable, kế thừa hoặc tài nguyên có vòng đời, hãy xác định độ sâu sao chép và kiểm thử khả năng độc lập. Nếu khó bảo đảm hợp đồng đó, copy constructor, factory hoặc mô hình immutable thường dễ hiểu và an toàn hơn.

Tham khảo: [Object.clone trong Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html#clone()) và [Cloneable trong Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Cloneable.html).
