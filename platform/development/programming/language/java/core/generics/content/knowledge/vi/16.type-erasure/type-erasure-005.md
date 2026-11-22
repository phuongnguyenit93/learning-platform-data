# Phép ép kiểu được trình biên dịch chèn vào khi đọc dữ liệu trong Java Generics

## 1. Vì sao đọc List<String> vẫn có thể gây ClassCastException?

Giả sử chương trình khai báo:

~~~java
List<String> words = new ArrayList<>();
words.add("Java");
String first = words.get(0);
~~~

Ở **mã nguồn**, phương thức get được nhìn như trả về String vì biến words có kiểu List<String>. Tuy nhiên, cách Java triển khai generics chủ yếu dựa trên **type erasure (xóa kiểu)**: trong bytecode, phương thức get của List có kiểu trả về đã xóa là Object. Khi giá trị từ lời gọi đó cần được sử dụng như một String, trình biên dịch có thể chèn lệnh kiểm tra và ép kiểu ở **vị trí sử dụng kết quả**.

Sơ đồ ý tưởng:

~~~text
Mã nguồn:       String first = words.get(0);
Kiểu tĩnh:      words.get(0) được kiểm tra như String
Sau xóa kiểu:   List.get(int) trả Object
Bytecode:       gọi List.get(int), checkcast String, lưu vào first
~~~

Lệnh JVM tương ứng là **checkcast**. Nó kiểm tra tại thời điểm chạy rằng giá trị tham chiếu nhận được là null hoặc tương thích với lớp/kiểu được kiểm tra. Nếu một đối tượng khác kiểu thực sự được dùng thay String, JVM ném ClassCastException.

Điều quan trọng: **generics được kiểm tra ở thời điểm biên dịch, còn checkcast thực hiện kiểm tra runtime tại nơi kết quả bị xóa kiểu được sử dụng với kiểu cụ thể.** Hai cơ chế phối hợp để giữ cú pháp generic thuận tiện mà vẫn duy trì tính tương thích với mã Java trước khi có generics.

Bài này tập trung vào **phép ép kiểu do compiler chèn khi đọc hoặc sử dụng dữ liệu generic**, không nhằm mô tả mọi dạng bytecode hay mọi lý do phát sinh ClassCastException.

## 2. Kiểu ở nguồn và kiểu sau khi xóa

Hãy xét interface và class đơn giản:

~~~java
interface Store<T> {
    T get();
}

final class Box<T> implements Store<T> {
    private final T value;

    Box(T value) {
        this.value = value;
    }

    @Override
    public T get() {
        return value;
    }
}
~~~

Khi viết:

~~~java
Store<String> store = new Box<>("Generics");
String content = store.get();
~~~

trình biên dịch biết giá trị cần đọc có kiểu **String**. Nhưng giới hạn trên của T trong Store<T> là Object nếu không có bound tường minh, nên chữ ký JVM sau xóa kiểu của get về cơ bản trả **Object**. Ở chỗ gán cho content, có thể cần kiểm tra Object thành String.

Để tư duy, có thể so sánh với dạng *gần tương đương* sau khi xóa kiểu (đây **không phải** chính xác toàn bộ source code mà javac tự tạo):

~~~java
interface Store {
    Object get();
}

final class Box implements Store {
    private final Object value;

    Box(Object value) {
        this.value = value;
    }

    @Override
    public Object get() {
        return value;
    }
}

// Tại phía gọi:
Store store = new Box("Generics");
String content = (String) store.get();
~~~

Mã bên trên chỉ giúp hiểu hình dạng API bị xóa generic và vị trí cast. Trong chương trình thật, compiler cũng có thể phát sinh bridge method, thay đổi descriptor theo bound, hoặc tối ưu bytecode tùy ngữ cảnh; không được xem mã minh họa này là bản decompile chính xác.

### Vì sao có lúc thấy cast, có lúc không?

So sánh:

~~~java
List<String> names = new ArrayList<>();
names.add("Java");

Object asObject = names.get(0);
String asString = names.get(0);
~~~

Trong trường hợp asObject, kết quả trả về Object của List.get có thể được nhận trực tiếp vào biến Object; **không cần checkcast String** chỉ để thực hiện phép gán đó.

Ở dòng asString, compiler phải bảo đảm kết quả phù hợp với String nên chèn **checkcast java/lang/String** theo dạng bytecode thông thường.

Như vậy, phát biểu “đọc List<String> luôn chèn một cast String” là **quá tuyệt đối**. Compiler dựa trên cách giá trị được sử dụng; nó có thể chèn cast khi kiểu đã xóa không đủ cho kiểu mong muốn. Thêm nữa, mức độ cast thực tế phụ thuộc những phép kiểm tra đã có và các quyết định sinh mã của compiler.

## 3. Nguồn gốc checkcast: chữ ký List.get sau erasure

Khai báo nguồn khái niệm của List có:

~~~java
interface List<E> {
    E get(int index);
}
~~~

Trong JVM, do E không có giới hạn trên cụ thể, kiểu trả về ở method descriptor bị xóa thành Object:

~~~text
get(int) → Object
JVM descriptor: (I)Ljava/lang/Object;
~~~

Generic signature bổ sung thông tin E trong metadata của class file cho compiler và công cụ, nhưng **method descriptor dùng khi thực thi** vẫn nói Object. JVM không dựa trên generic signature để xác minh rằng mọi phần tử của một List<String> là String ngay lúc gọi List.get.

Khi javac phân tích câu:

~~~java
String value = names.get(0);
~~~

nó dùng generic signature để biết kết quả có kiểu tĩnh String, rồi phát sinh bytecode có thể được hình dung như:

~~~text
aload        names
iconst_0
invokeinterface java/util/List.get:(I)Ljava/lang/Object;
checkcast    java/lang/String
astore       value
~~~

Đây là dạng mô tả **lược giản** các opcode, không chứa offset và constant-pool index chính xác. Dùng javap -c -p trên chương trình của bạn sẽ thấy lệnh thực tế của phiên bản javac đang chạy.

### Checkcast không tạo đối tượng mới

checkcast **không chuyển đổi nội dung** từ Integer thành String, không gọi toString() và cũng không sao chép đối tượng. Với một tham chiếu hợp lệ, nó giữ nguyên tham chiếu. Nếu kiểu đối tượng không tương thích với loại được kiểm tra, nó ném ClassCastException. Vì vậy:

~~~java
Object value = Integer.valueOf(17);
// String text = (String) value; // Chạy tới đây sẽ ném ClassCastException.
String text = value.toString();  // Chuyển nội dung thành "17", là thao tác khác.
~~~

Mảnh mã này chỉ nhằm phân biệt **cast tham chiếu** và **chuyển đổi biểu diễn dữ liệu**.

## 4. Ví dụ đầy đủ: compiler kiểm tra kiểu dù dữ liệu bị nhiễm

Lưu chương trình sau thành **ErasureCastDemo.java**. Đây là chương trình hoàn chỉnh, chạy trên Java 17+.

~~~java
import java.util.ArrayList;
import java.util.List;

public class ErasureCastDemo {
    static <T> T identity(T value) {
        return value;
    }

    static final class Holder<T> {
        private final T value;

        Holder(T value) {
            this.value = value;
        }

        T get() {
            return value;
        }
    }

    public static void main(String[] args) {
        List<String> names = new ArrayList<>();
        names.add("Java");

        String name = names.get(0);
        System.out.println("name=" + name);

        Holder<String> holder = new Holder<>("Generics");
        String fromHolder = holder.get();
        System.out.println("holder=" + fromHolder);

        String text = identity("Typed");
        System.out.println("identity=" + text);

        List<String> contaminated = new ArrayList<>();

        // Raw reference làm mất kiểm tra kiểu tham số khi gọi add.
        List raw = contaminated;
        raw.add(42); // javac -Xlint:unchecked phát cảnh báo.

        Object first = contaminated.get(0);
        System.out.println("asObject=" + first);

        try {
            String failing = contaminated.get(0);
            System.out.println(failing);
        } catch (ClassCastException error) {
            System.out.println("asString=ClassCastException");
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -Xlint:unchecked ErasureCastDemo.java
java ErasureCastDemo
~~~

Trong lúc biên dịch, javac phát **unchecked warning** tại dòng raw.add(42) vì gọi add trên raw List. Cảnh báo là thông báo của compiler; không thuộc stdout của chương trình.

**Stdout chính xác khi chạy:**

~~~text
name=Java
holder=Generics
identity=Typed
asObject=42
asString=ClassCastException
~~~

Giải thích diễn biến:

1. names là List<String>, chứa đúng chuỗi Java nên phép lấy ra và sử dụng như String thành công.
2. Holder<String> có get() trả T tại source, nhưng T không có bound cụ thể nên descriptor của get trả Object sau erasure. Caller dùng String cần kiểm tra cast tương ứng.
3. Phương thức identity cũng trả T ở source và Object ở descriptor đã xóa. Caller vẫn có thể sử dụng kết quả như String khi type inference suy ra T là String.
4. contaminated ban đầu có kiểu List<String> và trỏ đến một ArrayList; alias raw cùng trỏ đến **chính đối tượng đó**. raw.add(42) vượt qua kiểm tra generic của lời gọi add, tạo tình trạng **heap pollution**: giá trị runtime trong cấu trúc không khớp với kiểu tham số hóa mà một tham chiếu khác đang khai báo.
5. Khi đọc vào Object, số nguyên đóng hộp Integer vẫn là một Object hợp lệ, nên chương trình in asObject=42.
6. Khi đọc vào String, compiler phát sinh cast cần thiết, JVM phát hiện Integer không phải String và ném ClassCastException; catch in dòng xác nhận lỗi.

Cần nhìn đúng nguồn lỗi: **ArrayList.get không tự đòi phần tử là String tại runtime**. Lỗi xuất hiện khi kết quả Object được dùng như String. Nếu không có raw alias hoặc đường không an toàn tương đương, compiler sẽ chặn việc thêm Integer trực tiếp vào List<String>.

### Thử thay raw bằng lời gọi generic an toàn

~~~java
List<String> safe = new ArrayList<>();
safe.add("hello");
// safe.add(42); // Không biên dịch: int không chuyển được thành String.
~~~

Lệnh bị comment là ví dụ **cố ý không hợp lệ**. Với List<String>, lời gọi add thông thường được kiểm tra ở compile time. Không có bất kỳ nhu cầu tự ép kiểu Integer thành String nào.

## 5. Kiểm tra bytecode bằng javap

Sau khi chạy javac, dùng công cụ đi kèm JDK:

~~~bash
javap -c -p ErasureCastDemo
javap -c -p 'ErasureCastDemo$Holder'
~~~

Lệnh thứ nhất hiển thị bytecode của main. Hãy tìm đoạn gọi List.get và lời gọi Holder.get, identity. Ở các trường hợp kết quả được nhận dưới dạng String, có thể quan sát opcode checkcast với lớp java/lang/String. Trong đoạn đọc vào Object, không cần cast String ở vị trí phép gán đó.

Lệnh thứ hai hiển thị method descriptor hoặc kiểu đã xóa của get trong Holder: nó trả Object vì T không có bound tường minh. Khi muốn xem thêm generic signature, dùng:

~~~bash
javap -v -p 'ErasureCastDemo$Holder'
~~~

Thông tin Signature trong class file có thể mô tả kiểu generic T, còn bytecode và descriptor dùng kiểu đã xóa. **Signature không phải runtime type check**.

Đối với PowerShell, cmd hoặc bash, quy tắc quote tên nested class có thể khác nhau. Với bash và các shell POSIX, dấu nháy đơn ở ví dụ trên bảo vệ ký tự $. Nếu dùng cmd.exe trên Windows, có thể nhập tên lớp trong dấu nháy kép thay vì dấu nháy đơn. Mục đích chính là tránh để shell diễn giải ký tự $ trước khi javap nhận tên lớp.

Không nên khẳng định số offset bytecode hay thứ tự chỉ thị luôn giống nhau giữa các bản JDK; hãy kiểm tra chính file .class mà compiler tạo ra.

## 6. Bound của T thay đổi kiểu bị xóa và vị trí cast

Khi T có giới hạn trên cụ thể, erasure không nhất thiết là Object.

~~~java
class NumberBox<T extends Number> {
    private final T value;

    NumberBox(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }
}
~~~

Dạng nhìn tương đương sau erasure:

~~~text
NumberBox.get() trả Number
Nếu caller muốn Number: không cần cast Integer
Nếu caller muốn Integer: có thể cần checkcast Integer
~~~

Ví dụ sử dụng:

~~~java
NumberBox<Integer> box = new NumberBox<>(123);

Number asNumber = box.get();   // Giá trị trả về sau erasure là Number.
Integer asInteger = box.get(); // Có thể cần checkcast Integer.
~~~

**Quy tắc tổng quát:** erasure của một type variable lấy cận trái nhất trong các giới hạn của nó (nếu không có bound, dùng Object). Kiểu được trả về hoặc nhận vào sau erasure là cơ sở để compiler quyết định những phép chuyển đổi cần được thực hiện ở nơi sử dụng.

Không nên ghi nhớ rằng mọi T luôn thành Object. Với T extends Number, T ở đây bị xóa thành Number. Với tham số có nhiều bound, thứ tự bound quan trọng đối với erasure và giới hạn được phép ghi cũng có quy tắc của Java.

## 7. Generic method, biến cục bộ và kiểu mà người đọc “thấy”

Một generic method có thể suy luận T từ đối số và/hoặc kiểu đích:

~~~java
static <T> T first(T left, T right) {
    return left;
}
~~~

Nếu viết:

~~~java
String x = first("A", "B");
~~~

compiler cho phép kết quả sử dụng như String. Tuy nhiên descriptor của generic method khi T không có bound vẫn trả Object; bytecode ở caller có thể phải kiểm tra cast String.

Tương tự:

~~~java
var x = first("A", "B"); // x có kiểu tĩnh String.
~~~

var suy luận kiểu biến cục bộ từ biểu thức khởi tạo, **không khiến generic được giữ lại ở runtime**. Nếu kết quả generic đã xóa thành Object cần dùng như String, cast vẫn có thể được chèn vào vị trí thích hợp.

### Một Object variable không đổi thành String nhờ gán sau đó

~~~java
Object x = first("A", "B");
// String y = x;     // Không biên dịch.
String y = (String) x; // Có explicit checked cast.
~~~

Ở đây compiler không tự biến kiểu tĩnh Object của x thành String chỉ vì ta muốn khai báo biến y. Cần ép kiểu tường minh khi chỉ biết x là Object.

Vì vậy hãy phân biệt:

- **Cast ẩn do compiler chèn** để thực thi việc dùng kết quả generic sau xóa kiểu, khi kiểu tĩnh nguồn hợp lệ.
- **Cast tường minh do người lập trình viết** khi biểu thức đang có kiểu Object/supertype và cần dùng như kiểu con.
- **Unchecked cast** sang một kiểu tham số hóa mà runtime không thể kiểm tra đầy đủ, ví dụ chuyển raw List thành List<String>.

Ba trường hợp không có cùng ý nghĩa an toàn.

## 8. Checked cast và unchecked cast khác nhau thế nào?

Ví dụ:

~~~java
Object value = "text";
String s = (String) value; // Runtime kiểm tra đối tượng có là String không.
~~~

Dạng cast đến String là **reifiable type**, có thể được JVM kiểm tra tại runtime. Nếu value thực sự chứa Integer, cast ném ClassCastException.

Ngược lại:

~~~java
List raw = new ArrayList();
List<String> strings = (List<String>) raw; // Unchecked cast.
~~~

Runtime có thể kiểm tra đối tượng là List, nhưng **không thể xác minh mọi phần tử là String** chỉ bằng phép cast List<String>, do tham số generic thường bị xóa. javac có thể cảnh báo unchecked. Nếu trong raw có phần tử Integer, lấy phần tử ra dùng như String mới có thể phát sinh ClassCastException.

Sự khác biệt thực chất:

| Phép chuyển đổi | Kiểm tra gì tại runtime? | Nguy cơ |
| --- | --- | --- |
| Object → String | Kiểu runtime của tham chiếu có phù hợp String? | Có thể ném ClassCastException ngay khi cast. |
| Raw List → List<String> | Thường chỉ kiểm tra được lớp/interface List; không kiểm chứng String cho phần tử | Có thể gây heap pollution và lỗi khi lấy phần tử ra. |
| Đọc List<String>.get vào String | Kiểu runtime của giá trị lấy ra có tương thích String? | Lỗi nếu phần tử thực tế sai kiểu. |
| Đọc List<String>.get vào Object | Không cần kiểm tra String để dùng dưới dạng Object | Phần tử sai kiểu vẫn đọc được như Object. |

Hãy bật -Xlint:unchecked và xử lý cảnh báo tại nguồn. Đừng sử dụng SuppressWarnings chỉ để ẩn dấu hiệu dữ liệu không phù hợp với khai báo generic.

## 9. Vì sao lỗi có thể xuất hiện muộn?

Heap pollution thường tạo ra lỗi ở một vị trí **khác nơi dữ liệu bị đưa vào**:

~~~java
List<String> values = new ArrayList<>();
List raw = values;
raw.add(10);          // Gốc gây nhiễm dữ liệu; unchecked warning.

Object ok = values.get(0);   // Vẫn hợp lệ, vì Integer là Object.
// String bad = values.get(0); // Khi chạy sẽ ném ClassCastException.
~~~

Phép gán vào List<String> ban đầu **không tự bảo đảm runtime phần tử luôn là String** nếu mã khác đã có quyền truy cập qua raw type, unchecked conversion, reflection hoặc những đường không an toàn khác.

Mẫu lỗi này dễ làm lập trình viên truy nguyên sai chỗ: stack trace trỏ vào dòng đọc nhưng nguyên nhân nằm ở lệnh ghi trước đó. Vì vậy, khi gặp lỗi ClassCastException tại thao tác get, hãy kiểm tra cả các đường thêm dữ liệu và các cast/alias liên quan.

### Không thể tự “cứu” bằng instanceof List<String>

Do generics không reifiable theo cách thông thường, không được viết:

~~~java
// if (obj instanceof List<String>) { } // Không biên dịch.
~~~

Có thể kiểm tra:

~~~java
if (obj instanceof List<?> list) {
    // Chỉ biết đây là List với kiểu phần tử chưa xác định.
}
~~~

Nhưng List<?> không chứng minh mọi phần tử là String. Để bảo đảm dữ liệu thực sự là chuỗi, cần kiểm tra từng phần tử hoặc sử dụng API xác thực dữ liệu tại ranh giới tin cậy.

Ví dụ kiểm tra bằng vòng lặp:

~~~java
static List<String> copyStrings(List<?> input) {
    List<String> result = new ArrayList<>();

    for (Object element : input) {
        if (!(element instanceof String s)) {
            throw new IllegalArgumentException("Expected String");
        }
        result.add(s);
    }

    return result;
}
~~~

Ví dụ này dùng pattern matching cho instanceof có trong Java 17. Nó tạo một danh sách mới chỉ chứa chuỗi sau khi kiểm tra từng phần tử. Nếu ứng dụng cần chấp nhận null, phải xác định và xử lý chính sách null riêng vì điều kiện instanceof String ở trên không chấp nhận null.

## 10. Kiểm tra với lớp generic do mình định nghĩa

Một chương trình có thể có:

~~~java
class ValueHolder<T> {
    T value;

    ValueHolder(T value) {
        this.value = value;
    }

    T read() {
        return value;
    }
}
~~~

Khi được khởi tạo:

~~~java
ValueHolder<String> holder = new ValueHolder<>("OK");
String result = holder.read();
~~~

type erasure khiến trường value và kiểu trả về của read có descriptor Object, còn compiler vẫn kiểm tra holder là ValueHolder<String>. Phép lấy dữ liệu để dùng như String có thể phải nhận một cast tại nơi gọi, giống List.get.

Điểm cần chú ý: **không có một bản class riêng dành cho từng loại tham số String/Integer của ValueHolder** trong cơ chế generic thông thường. Runtime class về cơ bản là cùng một ValueHolder, còn compile time sử dụng generic signature để ngăn những phép gán không an toàn.

### Trường hợp kiểu dữ liệu sai được tạo bằng cách nào?

Nếu người lập trình chỉ dùng API được tham số hóa đúng, họ không thể viết:

~~~java
ValueHolder<String> box = new ValueHolder<>("OK");
// box.value = Integer.valueOf(7); // Không biên dịch.
~~~

Một lệnh sai kiểu muốn lọt qua thường phải đi qua raw type, unchecked operation, reflection, hoặc mã/thư viện vi phạm hợp đồng generic. Cast tại điểm đọc là **lớp phòng vệ cuối** trước lúc sử dụng dữ liệu theo kiểu cụ thể; nó không thay thế việc ngăn dữ liệu sai kiểu ngay từ đầu.

## 11. Khác biệt giữa cast tại nơi đọc và bridge method

Cả hai có thể xuất hiện vì type erasure nhưng mục đích khác nhau:

- **Cast tại caller khi dùng giá trị:** kiểm tra kết quả đã xóa kiểu, ví dụ Object từ List.get phải được dùng như String.
- **Bridge method do compiler tạo:** giữ tương thích và đa hình cho phương thức được ghi đè/triển khai khi chữ ký erasure của chúng khác với chữ ký cụ thể.

Ví dụ minh họa bridge:

~~~java
interface Provider<T> {
    T get();
}

final class TextProvider implements Provider<String> {
    @Override
    public String get() {
        return "Hello";
    }
}
~~~

Do interface có get() trả Object sau erasure, compiler có thể sinh bridge method get() trả Object trong TextProvider, chuyển tiếp đến get() trả String để bảo toàn cơ chế dispatch.

Bridge method **không phải** phép cast String được chèn tại mọi chỗ gọi List.get. Một bytecode listing có thể đồng thời có cả bridge và checkcast, nhưng cần đọc từng method và từng call site để hiểu chúng đang giải quyết vấn đề gì.

## 12. Những hiểu lầm phổ biến

### “Compiler lưu String bên trong ArrayList nên get trả String trực tiếp”

Không đúng ở method descriptor runtime của List.get: phương thức vẫn trả Object sau erasure. Generic signature giúp compiler hiểu phần tử là String ở compile time, rồi chèn cast khi nơi sử dụng đòi hỏi.

### “Đã khai báo List<String> thì chắc chắn runtime chỉ chứa String”

Không hoàn toàn đúng nếu có raw alias, unchecked conversion, reflection hoặc mã không tuân thủ hợp đồng. Một List<String> thuần được thao tác qua API generic đúng sẽ được compiler kiểm tra khi thêm, nhưng erasure không tạo kiểm tra String tại mọi lệnh add của raw List.

### “ClassCastException chứng minh dòng get sai”

Lỗi thường lộ ở chỗ đọc và cast, trong khi đối tượng sai có thể đã được đưa vào collection từ trước. Hãy lần theo cả bên ghi lẫn bên đọc.

### “Cast Object thành List<String> chắc chắn đã kiểm tra kiểu mọi phần tử”

Sai. Phần runtime của generic parameter thường không có đủ thông tin để kiểm tra danh sách đã đúng kiểu phần tử chưa. Đó là lý do unchecked cast/heap pollution nguy hiểm.

### “Tất cả generic type parameter đều bị xóa thành Object”

Không. Tham số kiểu có bound như T extends Number bị xóa về Number. Các bridge method, cast cần thiết và descriptor sẽ phụ thuộc quan hệ bound, override và nơi sử dụng cụ thể.

### “Compiler tự chèn cast khi đọc nên không cần quan tâm warning”

Cast được chèn là cơ chế thực thi kiểm tra kiểu ở điểm dùng; nếu dữ liệu bị sai kiểu, chương trình vẫn có thể ném ClassCastException. Sửa unchecked warning ở đường ghi là biện pháp phòng ngừa quan trọng.

## 13. Quy trình đọc lỗi ClassCastException trong mã generic

1. **Xác định kiểu tĩnh của biểu thức đọc**: ví dụ List<String>.get trả String trong mắt compiler.
2. **Tìm method descriptor sau erasure**: List.get trả Object, Holder<T>.get có thể trả Object hoặc bound tương ứng.
3. **Xem giá trị được dùng dưới dạng gì**: gán vào Object hay String, truyền đến API nào, có explicit cast hay không.
4. **Kiểm tra bytecode nếu cần**: dùng javap -c -p để tìm checkcast sau lời gọi generic.
5. **Truy ngược đường ghi**: raw collection, unchecked conversion, alias, reflectively added value hoặc dữ liệu từ nguồn khác.
6. **Giữ lại thông tin kiểu tĩnh chính xác**: tránh raw type, dùng List<T> hoặc List<?> thay vì ép thành tham số giả định.
7. **Xác thực dữ liệu ở ranh giới**: với nguồn không đáng tin, kiểm tra phần tử trước khi xem như List<String>.
8. **Chạy lại ví dụ với -Xlint:unchecked** và loại bỏ nguyên nhân warning phù hợp.

Khi đọc kết quả javap, nhớ rằng công cụ mô tả bytecode do compiler tạo cho phiên bản đang chạy. Các vị trí cast có thể phụ thuộc ngữ cảnh hoặc tối ưu compiler, nhưng **ý nghĩa ngữ nghĩa** về kiểm tra kiểu khi dùng kết quả generic phải được bảo toàn.

## 14. Câu hỏi tự kiểm tra

**1.** Vì sao Object obj = listOfStrings.get(0) có thể chạy được khi phần tử thật là Integer, còn String s = listOfStrings.get(0) ném ClassCastException?

**Đáp án:** List.get trả Object sau erasure. Dùng dưới dạng Object không cần kiểm tra String; dùng dưới dạng String cần kiểm tra tương thích runtime, thất bại đối với Integer.

**2.** Compiler có thêm cast trong định nghĩa phương thức get của ArrayList không?

**Đáp án:** Không nên hiểu theo cách đó. Ở các vị trí caller dùng kết quả trả Object đã bị xóa kiểu như String, compiler có thể chèn checkcast. Nội bộ phương thức get không phải nơi tự động xác nhận generic parameter String cho mọi instance.

**3.** Với T extends Number, kiểu đã xóa của T là gì và khi nào cần cast Integer?

**Đáp án:** T bị xóa về Number. Dùng kết quả dưới dạng Number không cần cast Integer chỉ để gán; dùng kết quả như Integer có thể cần checkcast Integer.

**4.** Vì sao phép ép raw List sang List<String> phát cảnh báo unchecked dù cast đến String là runtime-checked?

**Đáp án:** Runtime xác minh đối tượng là List, nhưng không thể xác minh mọi phần tử có kiểu String thông qua generic parameter bị xóa. Với Object → String, lớp String là kiểu có thể kiểm tra được trực tiếp.

**5.** Khi stack trace báo ClassCastException ở dòng đọc từ List<String>, điểm đầu tiên nên kiểm tra là gì?

**Đáp án:** Xem lệnh nào đã đưa phần tử sai kiểu vào danh sách, đặc biệt raw alias, unchecked cast, API bên ngoài hoặc reflection. Dòng đọc thường là chỗ lỗi bị phát hiện, không nhất thiết là chỗ phát sinh dữ liệu sai.

**Ghi nhớ:** Java Generics bảo vệ kiểu phần lớn ở compile time. Vì erasure loại bỏ phần lớn thông tin tham số generic khỏi method descriptor runtime, **javac chèn những cast cần thiết ở vị trí dùng giá trị generic như kiểu cụ thể**. Một chương trình tuân thủ generic contract sẽ đi qua các cast đó an toàn; dữ liệu bị nhiễm bởi thao tác unchecked có thể làm chúng thất bại ở runtime.
